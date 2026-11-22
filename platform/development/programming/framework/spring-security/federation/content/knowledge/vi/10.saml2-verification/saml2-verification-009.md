# Phân biệt mã trạng thái lỗi từ IdP với lỗi xác minh tại ứng dụng Spring Security SAML 2.0

## 1. Mục tiêu: tìm đúng nơi phát sinh lỗi SSO

Một lần đăng nhập SAML 2.0 có thể thất bại tại **Identity Provider (IdP)**, trong quá trình trình duyệt chuyển thông điệp, hoặc khi **Service Provider (SP)** kiểm tra phản hồi. Người dùng cuối thường chỉ nhìn thấy một màn hình “Sign-in failed”, HTTP 302, 403 hay 500. Những biểu hiện đó **không đủ** để xác định ai phát sinh lỗi.

Bài học tập trung vào **Kiểm chứng SAML2** trong hệ thống **Spring Security - federation**. Đề bài chính là phân biệt:

1. **Mã trạng thái giao thức do IdP gửi trong `<samlp:Response>`**, ví dụ `Responder / NoPassive`, `Requester / InvalidNameIDPolicy`, `AuthnFailed`.
2. **Lỗi kiểm chứng tại ứng dụng SP/Spring Security**, ví dụ chữ ký không hợp lệ, issuer sai, audience sai, assertion hết hạn, decryption thất bại hoặc không tìm thấy AuthnRequest tương ứng.

Hai nhóm này có thể xuất hiện dưới **cùng một cơ chế xử lý thất bại đăng nhập ở Spring Security**, nhưng **nguồn dữ liệu và cách khắc phục khác nhau**. Mục tiêu không phải chỉ giải mã được XML, mà là có quy trình chứng cứ đáng tin để triage, không bỏ qua security validation.

Sau bài, người học có thể:

- Đọc `StatusCode`, nested `StatusCode`, `StatusMessage`, `StatusDetail` trong SAML Response.
- Biết bốn **top-level status** của SAML Core và các subcode đáng chú ý trong Web Browser SSO.
- Xây dựng bảng phân loại: lỗi IdP, lỗi truyền tải/trình duyệt, lỗi trust/validation tại SP, và lỗi authorization sau khi đăng nhập.
- Hiểu Spring Security Servlet xử lý `SAMLResponse` như thế nào và vai trò `Saml2AuthenticationException`, `Saml2Error`, failure handler.
- Chẩn đoán sự cố theo HTTP hop, server log, IdP log, correlation ID và điều kiện SAML đã được xác minh.
- Thiết kế thông báo lỗi/log không rò rỉ assertion, danh tính, cookie hoặc chứng chỉ riêng.
- Chạy ví dụ Java 17 độc lập để luyện phân loại mà không cố mô phỏng cơ chế xác minh XML Signature.
- Kiểm thử lỗi chủ động trong môi trường test và tránh “sửa” lỗi bằng cách tắt chữ ký, thời hạn hoặc kiểm tra `InResponseTo`.

Ví dụ dùng **Spring Boot 3.x / Spring Security 6.x Servlet/MVC, Java 17+**. Tên lớp Spring Security 7.x/OpenSAML 5 có thể khác dòng 6.x/OpenSAML 4; cần đối chiếu tài liệu đúng phiên bản. Các domain `*.example.org` và ID trong bài chỉ mang tính minh họa.

## 2. Cần phân biệt bốn lớp mã lỗi

Trước khi nhìn vào stack trace hoặc DevTools, hãy xác định **lớp nào tạo ra giá trị đang nhìn thấy**.

| Lớp | Đối tượng/mã quan sát | Ai tạo? | Ví dụ | Đó có phải SAML StatusCode từ IdP? |
| --- | --- | --- | --- | --- |
| **HTTP/network** | HTTP status/transport error | Browser, proxy, ingress, web server | 302, 400, 403, 404, 414, 500, timeout, TLS error | **Không** |
| **SAML protocol** | `<samlp:StatusCode Value="urn:oasis:...">` | IdP hoặc một SAML responder phát `Response` | `Success`, `Requester`, `Responder`, `NoPassive` | **Có**, khi thực sự nằm trong Response |
| **SP authentication validation** | Java exception/error code trong Spring Security | Ứng dụng SP sau khi nhận/kiểm tra response | `Saml2AuthenticationException`, error code nội bộ, signature invalid | **Không nhất thiết**; có thể là lỗi local hoặc chuyển tải lỗi protocol |
| **Application authorization/business** | 403/controller/domain exception sau login | Chính sách phân quyền, controller hoặc downstream service | User đã xác thực nhưng không có quyền xem đơn hàng | **Không** |

**Ví dụ quan trọng:** browser thấy HTTP **200** khi IdP trả trang HTML chứa form POST; form đó có thể mang **SAML Response với top-level `Responder`**. HTTP 200 không đồng nghĩa đăng nhập thành công. Ngược lại, SAML Response có `Success` nhưng chữ ký không hợp lệ thì Spring SP vẫn phải từ chối xác thực.

Vì vậy **không thể lập quy tắc “HTTP 4xx = lỗi IdP; HTTP 5xx = lỗi SP”**. Cả IdP lẫn SP/proxy đều có thể trả 4xx hoặc 5xx, và IdP có thể báo lỗi ở cấp SAML trong một HTML POST được trả bằng HTTP 200.

## 3. Luồng xác thực và vị trí các loại lỗi

~~~mermaid
sequenceDiagram
    participant B as Browser
    participant SP as Spring Security SP
    participant I as Identity Provider
    B->>SP: GET /portal/private
    SP-->>B: Redirect đến SAML login
    B->>SP: GET /saml2/authenticate/corp
    SP-->>B: AuthnRequest (Redirect hoặc POST binding)
    B->>I: Chuyển AuthnRequest
    alt IdP từ chối request / không xác thực được
        I-->>B: HTML form chứa SAMLResponse với Status lỗi
        B->>SP: POST SAMLResponse tới ACS
        SP->>SP: Nhận diện protocol status, xử lý authentication failure
        SP-->>B: Trang thất bại, không tạo Authentication
    else IdP xác thực thành công
        I-->>B: HTML form chứa SAMLResponse Status=Success
        B->>SP: POST SAMLResponse tới ACS
        alt Kiểm tra assertion hợp lệ
            SP->>SP: Verify trust, signature, issuer, audience, thời gian...
            SP-->>B: Thiết lập Authentication/phiên SP
        else SP phát hiện lỗi validation
            SP->>SP: Saml2AuthenticationException / failure handler
            SP-->>B: Đăng nhập thất bại, không tạo Authentication mới
        end
    end
~~~

Một đường lỗi thứ ba xảy ra khi **browser không bao giờ POST một SAMLResponse về ACS**: IdP có thể trả trang lỗi HTML, browser bị chặn cookie, SSO redirect sai, TLS hỏng, proxy trả 502 hoặc người dùng đóng trang. Trong trường hợp này **chưa chắc có SAML StatusCode để đọc**.

Dù nguyên nhân nào, chỉ cấp phiên SP sau khi pipeline SAML/ứng dụng đã kiểm tra thành công theo chính sách. Không xây một bộ phân loại dựa trên dữ liệu chưa tin rồi cho qua validation.

## 4. Cấu trúc <samlp:Status> trong SAML Response

SAML 2.0 Core định nghĩa `<Status>` cho nhiều response protocol. Đối với `<samlp:Response>`, phần trạng thái gồm:

- **`StatusCode` bắt buộc**: có thuộc tính `Value` là URI; mã ngoài cùng là **top-level**.
- **`StatusCode` lồng bên trong, tùy chọn**: subcode cụ thể hơn. Không phải IdP nào cũng trả subcode; chuẩn và errata cho phép bỏ subcode trong một số tình huống, kể cả tránh rò thông tin.
- **`StatusMessage`, tùy chọn**: text do responder cung cấp. Nó có thể thiếu, chứa văn bản vendor-specific, hoặc chứa nội dung không an toàn để trình bày trực tiếp.
- **`StatusDetail`, tùy chọn**: dữ liệu bổ sung có thể là XML extension; không có hợp đồng cố định cho mọi IdP.

Ví dụ minh họa **IdP không thể xác thực thụ động**:

~~~xml
<samlp:Response
    xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    ID="_resp-demo"
    Version="2.0"
    IssueInstant="2026-11-07T00:00:00Z"
    InResponseTo="_authn-demo"
    Destination="https://app.example.org/login/saml2/sso/corp">
  <saml:Issuer>https://idp.example.org/entity</saml:Issuer>
  <samlp:Status>
    <samlp:StatusCode
        Value="urn:oasis:names:tc:SAML:2.0:status:Responder">
      <samlp:StatusCode
          Value="urn:oasis:names:tc:SAML:2.0:status:NoPassive"/>
    </samlp:StatusCode>
    <samlp:StatusMessage>
      Passive authentication is not available
    </samlp:StatusMessage>
  </samlp:Status>
</samlp:Response>
~~~

Đây là XML **mô tả cấu trúc**, không phải SAMLResponse đã ký/được phép sử dụng. Không có assertion trong ví dụ vì responder báo lỗi; điều này **không tự làm status lỗi thành sai chuẩn**. Cách yêu cầu chữ ký cho response lỗi và mức trust đối với thông báo lỗi phải tuân theo profile, metadata, policy và khả năng sản phẩm.

Từ ví dụ:
- Top-level = **`Responder`**.
- Subcode = **`NoPassive`**.
- `StatusMessage` là câu chữ giải thích thêm, **không phải mã chuẩn**.
- Kết luận ban đầu là “IdP *báo cáo* không thể đáp ứng passive”, **không phải** “signature sai tại Spring SP”.

**Quan trọng về nguồn tin:** chỉ giải mã XML từ browser không khiến toàn bộ nội dung đã đáng tin. Nếu response lỗi không được xác minh bằng cơ chế phù hợp, log điều quan sát được như **reported/unverified status** và không dùng nó để bỏ qua security policy hay phân quyền.

## 5. Bốn top-level SAML StatusCode

Các URI chuẩn có tiền tố chung `urn:oasis:names:tc:SAML:2.0:status:`.

| Top-level code | Nghĩa theo SAML Core | Triage ban đầu |
| --- | --- | --- |
| **`Success`** | Yêu cầu SAML đã thành công ở mức xử lý protocol | Tiếp tục kiểm tra response, assertion, chữ ký, issuer, điều kiện; **chưa đủ để login SP thành công** |
| **`Requester`** | Request không thể được thực hiện do lỗi ở phía thực thể gửi request | Kiểm tra AuthnRequest, SP entity ID, policy, binding, signature, NameIDPolicy; **không quy về browser người dùng** |
| **`Responder`** | Request không thể được thực hiện do lỗi ở responder/SAML authority | Kiểm tra IdP policy, session, sự kiện đăng nhập, backend IdP và subcode có thể có |
| **`VersionMismatch`** | Responder không xử lý được vì phiên bản request không phù hợp | Kiểm tra Version/protocol và endpoint IdP thực tế |

Một cách hiểu sai: `Requester` được đặt tên theo **thực thể gửi SAML request**, thường là **SP** trong SP-initiated login, chứ không có nghĩa “người dùng nhập sai password”. Còn `Responder` không mặc nhiên đồng nghĩa IdP HTTP 500; một IdP có thể xử lý request một cách có kiểm soát và gửi status Responder qua một form POST bình thường.

Top-level `Success` có nghĩa responder **báo cáo** thành công theo giao thức. Spring SP vẫn phải xác minh toàn bộ Response/Assertion và policy của ứng dụng. Không dùng biểu thức “nếu status Success thì set SecurityContext” trong controller tự viết.

## 6. Các subcode thường gặp khi tích hợp Web Browser SSO

Subcode **không bắt buộc phải có**. OASIS định nghĩa một tập mã second-level, còn vendor có thể dùng URI khác theo thỏa thuận. Không hardcode rằng tất cả lỗi phải có hai tầng.

| Subcode | Ý nghĩa SAML điển hình | Hướng kiểm tra phù hợp |
| --- | --- | --- |
| **`AuthnFailed`** | Responder không xác thực được principal | Tài khoản/credential, MFA, risk policy, audit IdP; không tự kết luận sai password |
| **`NoPassive`** | Không thể đáp ứng xác thực passive được yêu cầu | `IsPassive=true`, IdP session và khả năng silent auth; fallback interactive nếu cho phép |
| **`NoAuthnContext`** | Không thể thỏa yêu cầu authentication context | `RequestedAuthnContext`, mức assurance/MFA và IdP policy |
| **`InvalidNameIDPolicy`** | IdP không thể/không muốn hỗ trợ `NameIDPolicy` | Đối chiếu `Format`, `SPNameQualifier`, `AllowCreate`, IdP config |
| **`RequestDenied`** | Responder có thể xử lý nhưng chọn không trả lời/yêu cầu bị từ chối | SP trust, request policy, chữ ký request, rate/risk policy, contract; không suy user bị lock ngay |
| **`RequestUnsupported`** | Loại request không được responder hỗ trợ | Gửi sai protocol/endpoint hoặc tính năng/binding không phù hợp |
| **`UnsupportedBinding`** | Responder không thể đáp ứng bằng binding đã chỉ định | IdP metadata SSO binding, SP ACS binding, HTTP-Redirect/POST |
| **`UnknownPrincipal`** | Responder không nhận ra principal mà request chỉ định hoặc ngụ ý | IdP user provisioning/directory, subject/name identifier; cẩn trọng user enumeration |
| **`NoAvailableIDP`, `NoSupportedIDP`** | Trường hợp federation proxy/discovery không có IdP phù hợp | IdPList, liên kết federation, routing sang upstream |
| **`ProxyCountExceeded`** | Không thể proxy AuthnRequest thêm vì giới hạn | Scoping/ProxyCount, chain IdP proxy |
| **`InvalidAttrNameOrValue`** | Attribute/AttributeValue không hợp lệ cho truy vấn/giao thức | Mapping và hỗ trợ attribute profile; không mặc nhiên là lỗi login thường |
| **`PartialLogout`** | Chỉ logout một phần các bên tham gia | **Single Logout**, không được coi là mã login success/failure thông thường |

Ngoài ra OASIS còn định nghĩa `RequestVersionDeprecated`, `RequestVersionTooHigh`, `RequestVersionTooLow`, `ResourceNotRecognized`, `TooManyResponses`, `UnknownAttrProfile`. Chúng có ý nghĩa theo protocol/request cụ thể, không nên liệt kê như lỗi login mà IdP nào cũng phải phát.

### Tránh suy diễn từ subcode

- `AuthnFailed` không đủ để nói “mật khẩu sai”; có thể do user bị chặn, MFA chưa đạt, policy rủi ro hoặc provider upstream.
- `InvalidNameIDPolicy` không đồng nghĩa token/assertion sai chữ ký.
- `NoAuthnContext` khác lỗi issuer/audience ở SP: nó cho biết IdP **không đáp ứng yêu cầu AuthnContext**, còn SP có thể riêng từ chối assertion vì context không đạt policy.
- `UnsupportedBinding` trong XML status nói về **responder báo không hỗ trợ binding**. HTTP 405/404 ở ACS lại là lỗi tuyến HTTP/filter mapping, chưa chắc đã có SAML response.
- `RequestDenied` có thể được dùng bởi IdP để tránh tiết lộ chi tiết nhạy cảm; không đòi IdP trả StatusMessage mô tả toàn bộ kiểm tra nội bộ.

## 7. Những gì **không phải** mã trạng thái từ IdP

Đây là chỗ nhiều đội phát triển chẩn đoán sai.

### HTTP status không phải SAML StatusCode

Một HTTP response có:

~~~http
HTTP/1.1 302 Found
Location: /login?error
~~~

nó cho biết browser được chuyển hướng sau một sự kiện, **không nói** SAML Response chứa `Responder` hay bị SP từ chối chữ ký. Cả hai tình huống đều có thể dẫn đến cùng redirect.

HTTP `403 Forbidden` tại `/login/saml2/sso/corp` có thể do CSRF configuration, filter chain, access control hoặc response error handling; **không suy được** top-level SAML `Requester`.

HTTP `403` tại `/portal/admin` sau khi người dùng có phiên SSO hợp lệ có thể là **authorization failure**, không phải SAML login failure.

### Exception ở SP không tự là SAML StatusCode

Spring có thể ném:

~~~text
org.springframework.security.saml2.provider.service.authentication.Saml2AuthenticationException
~~~

Đây là **exception Java trong ứng dụng**. Nó có thể xuất hiện vì **IdP gửi status không thành công** hoặc vì **SP phát hiện lỗi local** khi phân tích/kiểm chứng response. **Chỉ nhìn tên exception là không đủ phân biệt nguyên nhân.**

Spring còn có `Saml2Error` và error code của **API framework** (ví dụ phân loại decryption, invalid response, missing subject tùy version). Những mã đó **không mặc nhiên** là URI `urn:oasis:names:tc:SAML:2.0:status:...` do IdP gửi.

### Spring controller/business error cũng không phải IdP status

Sau khi SAML login đã thành công, application service có thể:
- Không tìm thấy user trong database nội bộ;
- Từ chối truy cập role/group;
- Không ánh xạ được tài khoản với tenant;
- Trả 500 khi gọi downstream service;
- Trả 403 vì user chưa có quyền đối với một tài nguyên.

Đó là lỗi **provisioning/authorization/application**, cần sửa mapping và policy. Không thay chứng chỉ IdP hoặc tắt SAML validation để “chữa” lỗi nghiệp vụ.

## 8. IdP báo lỗi như thế nào khi không trả Assertion?

Một Response thất bại có thể chỉ chứa `Status` và **không có Assertion thành công**. Ví dụ:

~~~xml
<samlp:Response
    xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    ID="_response-failed-example"
    Version="2.0"
    IssueInstant="2026-11-07T00:00:00Z"
    InResponseTo="_request-example"
    Destination="https://app.example.org/login/saml2/sso/corp">
  <saml:Issuer>https://idp.example.org/entity</saml:Issuer>
  <samlp:Status>
    <samlp:StatusCode
        Value="urn:oasis:names:tc:SAML:2.0:status:Requester">
      <samlp:StatusCode
          Value="urn:oasis:names:tc:SAML:2.0:status:InvalidNameIDPolicy"/>
    </samlp:StatusCode>
  </samlp:Status>
</samlp:Response>
~~~

**Kết luận:** IdP *báo cáo* một lỗi request liên quan NameIDPolicy. SP không nên biến Response này thành authenticated user dù thông tin issuer/response metadata trông đúng. Ngược lại, nếu SP muốn xác minh rằng status này **thực sự đến từ IdP đáng tin**, phải dựa vào chữ ký/trust của response, kênh và cấu hình tương ứng; không hiển thị raw StatusMessage như nội dung an toàn.

Khi IdP không thể hoàn thành SAML request, cách phát lỗi còn phụ thuộc sản phẩm và profile:
- Có IdP **POST một SAML Response chứa Status lỗi** về ACS.
- Có IdP hiển thị trang lỗi HTML, không trả Response, hoặc chỉ ghi internal log.
- Có IdP dùng error URI/support code riêng thay vì subcode đầy đủ.
- Một reverse proxy có thể chặn/timeout trước khi IdP tạo bất kỳ SAML status nào.

**Vì vậy không tìm thấy StatusCode trong browser trace không đủ để khẳng định IdP xử lý thành công.**

## 9. SAML Response báo Success nhưng SP từ chối — vì sao?

Ví dụ Response chứa:

~~~xml
<samlp:Status
    xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol">
  <samlp:StatusCode
      Value="urn:oasis:names:tc:SAML:2.0:status:Success"/>
</samlp:Status>
~~~

Nghĩa của nó chỉ là **responder báo thành công về giao thức**. Dưới đây là những điểm SP vẫn phải kiểm tra:

1. **Parsing/encoding:** `SAMLResponse` Base64 có hợp lệ, XML có đọc được mà không chấp nhận XXE/entity expansion không?
2. **Relying Party registration:** response gắn với IdP/registration nào, metadata nào đã được phê duyệt?
3. **Response signature/Assertion signature:** chữ ký có hợp lệ bằng verification credentials đáng tin không? Theo triển khai/version, các phần cần ký và mức ràng buộc có quy tắc rõ.
4. **Issuer:** có khớp entity ID IdP được tin trong `RelyingPartyRegistration` không?
5. **Destination và Recipient:** Response/SubjectConfirmation có nhắm đúng public ACS URL của SP không?
6. **AudienceRestriction:** assertion có cấp cho SP entity ID chính xác không?
7. **InResponseTo:** response có liên hệ với AuthnRequest đã tạo trong phiên/browser theo SP-initiated flow không?
8. **Subject / SubjectConfirmationData:** có NameID/subject và phương thức xác nhận đủ theo policy không?
9. **NotBefore/NotOnOrAfter:** assertion/subject confirmation còn hiệu lực trong giới hạn clock skew đã được phép không?
10. **Replay/one-time use:** request/assertion/response ID có bị dùng lại hoặc vượt policy không?
11. **Decryption:** nếu IdP mã hóa assertion/attribute, SP có private key đúng để giải mã và giữ nguyên thứ tự xác minh phù hợp không?
12. **Mapping:** dữ liệu subject/attribute có đủ để tạo principal theo cấu hình framework mà không đưa role không được phép không?

**Chỉ một điểm không đạt là đủ để SP từ chối**, dù status IdP là `Success`. Không “đổi” status thành Responder vì kiểm chứng nội bộ thất bại: **IdP không phát status Responder trong tình huống này**.

## 10. Nhóm lỗi xác minh tại SP và hướng điều tra

| Lỗi local | Dấu hiệu ở SP | Nguyên nhân cần xem | Không nên kết luận |
| --- | --- | --- | --- |
| **Malformed/missing SAMLResponse** | Không lấy được tham số POST, Base64 lỗi, XML parser error | Binding sai, proxy/body giới hạn, request bất thường | “IdP trả AuthnFailed” khi chưa đọc status |
| **Invalid signature** | Provider từ chối XML Signature | IdP signing certificate, cert rollover, canonicalization, response bị sửa, trust config | “Đổi status code thành Success sẽ qua” |
| **Unknown registration** | Không tra được `registrationId`/`RelyingPartyRegistration` | ACS URL, RelayState, multi-IdP registration | “Người dùng sai mật khẩu” |
| **Issuer mismatch** | Response issuer khác entity ID tin cậy | Nhập nhầm IdP metadata, entity ID, multi-tenant | “IdP chỉ bị lỗi availability” |
| **Destination/Recipient mismatch** | Response nhắm URL khác ACS đang chạy | Reverse proxy, HTTP↔HTTPS, host/port/path, metadata SP | “Sửa browser redirect không cần IdP” |
| **Audience mismatch** | Assertion không dành cho SP hiện tại | SP entity ID sai hoặc IdP cấu hình nhầm audience | “Assertion ký rồi thì mọi SP đều được nhận” |
| **Expired assertion** | `NotOnOrAfter` quá hạn | Clock skew, server NTP, replay, IdP session timing | “Tăng clock skew không giới hạn” |
| **NotBefore in future** | Assertion chưa đến thời điểm hiệu lực | Đồng hồ lệch, cấp phát sai | “Bỏ kiểm tra thời gian” |
| **InResponseTo mismatch** | Không tìm thấy AuthnRequest phù hợp | Session/cookie SameSite, request repository, nhiều tab, IdP-initiated flow | “Bỏ correlation cho nhanh” |
| **Missing subject** | Không xác định được NameID/principal | IdP NameID/attribute mapping, encrypted ID | “Lỗi HTTP 500 ở IdP” |
| **Decrypt failed** | Không giải mã được EncryptedAssertion/ID/attribute | SP decryption key/cert/algorithm, wrong key rotation | “Chỉ cần tắt encryption” |
| **Replay detected** | Request/Assertion ID đã dùng | Callback lặp lại, attack replay, repository TTL | “Tăng TTL là an toàn” |
| **Response signed but assertion not acceptable** | Provider từ chối assertion policy | Conditions, subject confirmation, signature model, auth context | “Chữ ký response duy nhất luôn đủ mọi điều kiện” |

**Đừng nhầm sự kiện “issuer mismatch ở SP” với `Requester` do IdP gửi.** Một bên là **kiểm chứng response của local**, bên kia là **trạng thái protocol do responder phát**.

## 11. Một response có thể có cả status và lỗi local

Một pipeline thực tế có thể gặp:

**Kịch bản 1 — IdP báo lỗi rõ ràng, không có assertion:** Response chứa `Responder / NoPassive`. SP phải nhận diện thất bại, không tạo phiên và có thể hướng dẫn user thử đăng nhập tương tác mới. Dù vậy hãy đối chiếu nguồn/status theo trust policy.

**Kịch bản 2 — Response báo Success nhưng signature không hợp lệ:** Đây là **lỗi validation tại SP**. Cần giữ response bị từ chối; không bỏ signature verification vì status Success “trông tốt”.

**Kịch bản 3 — Response lỗi từ IdP cũng bị lỗi chữ ký/issuer:** Bạn có thể nhìn thấy subcode trong XML thô nhưng **không thể khẳng định đáng tin**. Triage chính nên phản ánh “message không được SP xác minh” cùng quan sát “có reported status chưa tin”; đừng cấp exception cho lỗi IdP dựa trên một giá trị do attacker có thể tạo.

**Kịch bản 4 — Response Success đã xác minh và authenticated nhưng route bị 403:** SAML authentication **thành công**, còn authorization fail. Cần xem application roles/tenant/provisioning, không thay SAML issuer, ACS hay chữ ký.

**Kịch bản 5 — Browser bị IdP trả HTTP 500, không có POST tới ACS:** Chưa có SAML status. Điều tra IdP HTTP layer và trace request, không tự gán `Responder` nếu IdP không gửi SAML Response.

**Kịch bản 6 — RelayState/cookie thất lạc:** Spring không tìm thấy AuthnRequest, có thể từ chối Response hợp lệ vì thiếu correlation. Đây là vấn đề **SP session/correlation/browser**; IdP có thể đã thành công theo góc nhìn của nó. Không biến thành lỗi “AuthnFailed”.

## 12. Cây quyết định để phân loại khi có ticket

~~~mermaid
flowchart TD
    A[Người dùng báo SSO thất bại] --> B{Browser có POST SAMLResponse đến ACS?}
    B -- Không --> C[Điều tra IdP page, redirect, TLS, proxy, cookie, network]
    B -- Có --> D{SP nhận và phân tích response an toàn?}
    D -- Không --> E[Lỗi transport, binding, parsing hoặc filter tại SP]
    D -- Có --> F{Response có SAML Status không-Success?}
    F -- Có --> G[IdP đã report protocol failure; đánh giá trust và subcode]
    F -- Không hoặc Success --> H{SP verification có pass?}
    H -- Không --> I[Local SAML authentication validation failure]
    H -- Có --> J{Đã tạo Authentication?}
    J -- Không --> K[Mapping, principal hoặc ứng dụng authentication pipeline]
    J -- Có --> L{Tài nguyên sau login có bị 403?}
    L -- Có --> M[Application authorization hoặc provisioning]
    L -- Không --> N[Login thành công; xem UX/redirect nếu vẫn có sự cố]
~~~

**Thận trọng:** nhánh đọc SAML status là **một bước chẩn đoán**, không phải cấp quyền. Response lỗi do IdP “reported” vẫn có thể không đạt các kiểm tra trust; cần xác thực nguồn theo policy trước khi coi nó là nguyên nhân được khẳng định. Khi nhiều lỗi cùng tồn tại, **không dùng thứ tự đọc XML để kết luận nguồn gốc duy nhất**; ghi cả quan sát, độ tin cậy, và bước kiểm tra local.

Cây trên không đề xuất tự giải mã assertion thành principal. Nhiệm vụ xác minh thuộc Spring Security/OpenSAML provider.

## 13. Spring Security xử lý callback SAMLResponse ra sao?

Với Spring Security Servlet SAML 2.0 Service Provider:

1. IdP tạo Response và browser thường **HTTP POST** trường `SAMLResponse` tới ACS mặc định `/login/saml2/sso/{registrationId}`.
2. `Saml2WebSsoAuthenticationFilter` xử lý callback (khi chain/matcher đúng).
3. Converter, thường `Saml2AuthenticationTokenConverter`, trích request và tìm `RelyingPartyRegistration`.
4. `AuthenticationManager` chuyển token tới provider Spring Security tích hợp OpenSAML: trong dòng **6.x** có `OpenSaml4AuthenticationProvider` tùy bộ thư viện; trong dòng **7.x** hướng dẫn hiện đại dùng `OpenSaml5AuthenticationProvider`.
5. Provider giải mã/parse, kiểm chứng theo trình tự phù hợp, có thể kiểm tra status, chữ ký, issuer/destination, conditions, subject, audience và decryption.
6. Nếu thành công, trả `Saml2Authentication` chứa `Saml2AuthenticatedPrincipal` và authorities; filter/chain thiết lập SecurityContext theo cấu hình.
7. Nếu thất bại, `AuthenticationException` được đưa tới cơ chế authentication failure/entry point; **không có authenticated principal mới**.

Tên API, validator và thứ tự chi tiết có thể thay đổi theo version/provider. Đừng dùng tên class của 7.x để import vào một dự án đang ở 6.x không hỗ trợ OpenSAML 5.

### Tại sao một exception không đủ nói nguồn lỗi?

`Saml2AuthenticationException` là lớp con của `AuthenticationException` cho những lỗi SAML-related, ví dụ:
- SAMLResponse thiếu hoặc sai XML;
- Chữ ký Response/Assertion thiếu, sai hoặc certificate không được tin;
- Assertion condition, subject hoặc thời hạn không đạt;
- Decryption không thực hiện được;
- Provider gặp protocol response không thành công.

Framework có thể đưa những lỗi khác nhau vào cùng nhánh failure handler để trả UX tương tự. Muốn phân loại, cần **căn cứ từ response status (nếu có và đáng tin), error code framework, bước xác minh và logs tương quan**, không regex chuỗi exception message rồi coi đó là mã chuẩn IdP.

## 14. <samlp:StatusCode> khác <Saml2Error.getErrorCode()>

Đây là điểm kỹ thuật quan trọng cho Java.

**SAML StatusCode** nằm trong XML dưới namespace:

~~~text
urn:oasis:names:tc:SAML:2.0:status:
~~~

Nó thuộc **protocol**, do IdP/SAML responder báo cáo.

**`Saml2Error`** là một đối tượng trong API Spring Security `org.springframework.security.saml2.core.Saml2Error`. Nó chứa `getErrorCode()` và `getDescription()`. `Saml2AuthenticationException#getSaml2Error()` cho phép đọc error mà Spring framework phát sinh trong authentication pipeline.

Một error code Spring có thể đại diện **lỗi nội bộ**, không phải OASIS StatusCode. Trong Spring Security 7.0+, có các factory như `invalidResponse()`, `malformedResponseData()`, `decryptionError()`, `relyingPartyRegistrationNotFound()` và `subjectNotFound()`. **Chúng không được coi như URI từ IdP.** Các mã/constant và API có thể thay đổi giữa phiên bản.

Ví dụ mã phân loại khi nhận một `AuthenticationException`:

~~~java
String diagnosticCode = "OTHER_AUTHENTICATION_FAILURE";
if (exception instanceof Saml2AuthenticationException samlException) {
    diagnosticCode = samlException.getSaml2Error().getErrorCode();
}
~~~

Đây chỉ là một **mảnh code trong failure handler có import phù hợp**. Biến `diagnosticCode` thể hiện **API framework**; nó **không đủ** để suy trực tiếp top-level `Responder`, subcode `NoPassive` hoặc signer của XML. Nếu cần một business event kiểu “IdP reported NoPassive”, hệ thống phải có chứng cứ protocol status với policy trust phù hợp, không đoán từ mọi error code.

## 15. Ví dụ Spring Security Java 17+: failure handler an toàn

Bên dưới là **lớp cấu hình đầy đủ** cho một dự án Spring Boot Servlet có các dependency Spring Security/SAML 2.0 tương thích và registration IdP hợp lệ. Nó không tự giải mã SAML XML, không thay provider validation, **không echo exception message ra browser**. Tệp:

`src/main/java/com/example/federation/SamlFailureConfiguration.java`

~~~java
package com.example.federation;

import java.io.IOException;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.AuthenticationServiceException;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.saml2.provider.service.authentication.Saml2AuthenticationException;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SamlFailureConfiguration {

    private static final Logger log =
            LoggerFactory.getLogger(SamlFailureConfiguration.class);

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/auth/problem", "/error", "/public/**").permitAll()
                        .anyRequest().authenticated())
                .saml2Login(saml -> saml.failureHandler(this::onFailure))
                .build();
    }

    private void onFailure(
            HttpServletRequest request,
            HttpServletResponse response,
            AuthenticationException exception) throws IOException {

        String category = "OTHER_AUTHENTICATION_FAILURE";
        String internalCode = "none";

        if (exception instanceof Saml2AuthenticationException saml) {
            category = "SAML_AUTHENTICATION_FAILURE";
            String code = saml.getSaml2Error().getErrorCode();
            if (code != null && code.matches("[A-Za-z0-9_.:-]{1,100}")) {
                internalCode = code;
            }
        }
        else if (exception instanceof AuthenticationServiceException) {
            category = "AUTHENTICATION_SERVICE_FAILURE";
        }

        log.warn("SAML login failed; category={}, localCode={}",
                category, internalCode);

        response.sendRedirect(request.getContextPath() + "/auth/problem");
    }
}
~~~

**Lưu ý khi chạy:**
- Cần `spring-boot-starter-security`, `spring-security-saml2-service-provider`, Spring Web/Servlet, Java 17 và các dependency OpenSAML được resolve theo phiên bản Spring Security.
- Lớp này được component scan dưới một `@SpringBootApplication`. Đây **không** là chương trình độc lập dùng `javac SamlFailureConfiguration.java` với JDK trống.
- Tạo trang/controller công khai cho `/auth/problem` (không echo raw exception); nếu chưa có controller, URL đó có thể 404 dù handler đã chạy.
- `saml2Login(... failureHandler(...))` là hook **cho thất bại xác thực SAML** ở filter; một 403 authorization sau login hoặc 404 ở proxy không mặc nhiên qua handler này.
- `Saml2Error.getErrorCode()` được ghi dưới nhãn **`localCode`**, không đặt tên `idpStatus`. Regex chỉ giữ chuỗi kỹ thuật ngắn; trong sản phẩm thực còn cần chính sách log sampling/redaction và correlation ID.
- Mã không log username, XML, SAMLResponse, RelayState, cookie, header Authorization, `StatusMessage` hay exception message chưa khử nhạy cảm.
- Các tình huống failure ngoài phạm vi Spring filter (proxy, IdP HTML page, browser bị chặn cookie trước callback) **không kích hoạt** đoạn code này.

**Kết quả HTTP mong đợi khi handler được gọi:** browser nhận redirect tới trang lỗi chung `/auth/problem`; không có “stdout chuẩn” vì log là sự kiện runtime phụ thuộc request và provider. Không dùng việc redirect thành công để suy ra protocol status.

### Nếu cần mã hỗ trợ cho người dùng

Trang lỗi nên hiển thị thông điệp không tiết lộ:
> “Không thể hoàn tất đăng nhập. Vui lòng thử lại hoặc liên hệ hỗ trợ và cung cấp mã yêu cầu.”

Mã yêu cầu có thể là một **opaque request correlation ID** do server tạo, không phải SAMLResponse, NameID hoặc internal exception description. Trong server logs, đội vận hành dùng mã đó để nối dữ liệu từ SP và IdP (theo chính sách logging/privacy). Không tạo trang lỗi công khai chứa `getSaml2Error().getDescription()` vì mô tả có thể lộ chi tiết validation, endpoint, cert hoặc dữ liệu do đối tác gửi.

## 16. Cấu hình SAML SP tối thiểu để kiểm chứng trong lab

Trong một dự án Spring Boot 3.x Servlet đã có dependency, một registration có thể dùng metadata IdP đã thẩm định:

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

File `src/main/resources/saml/corp-idp.xml` phải là metadata hợp lệ từ IdP đã được kiểm chứng, chứa issuer, SSO endpoint và signing certificate. Không dùng host ví dụ hoặc certificate tự sinh ngẫu nhiên để gọi là trust production.

Trong Gradle đã dùng Boot BOM/dependency management:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.security:spring-security-saml2-service-provider'
}
~~~

Đây chỉ là đoạn `dependencies` để chèn vào project Boot hiện có; khi resolve OpenSAML có thể cần Shibboleth releases repository theo tài liệu Spring Security và chính sách build. Không gắn version không tương thích với Spring Boot BOM.

**Phân biệt cấu hình với vận hành:** dependency + metadata + filter chain đúng mới khởi động được flow; IdP còn phải đăng ký chính xác SP entity ID/ACS, signing policy và test user. Việc chạy build thành công không xác minh một status hay assertion nào.

## 17. Không dùng StatusMessage như nguồn thông tin đáng tin

`StatusMessage` là văn bản mà IdP/SAML responder có thể gửi. Ngay cả khi ký hợp lệ, nó có thể chứa:
- Username, email hoặc thông tin tenant;
- Tên nhóm bảo mật, policy MFA, account state;
- Thông tin nội bộ IdP;
- Văn bản tùy ý hoặc extension do một upstream IdP đưa tới.

Để an toàn:
1. **Không hiển thị nguyên văn cho người dùng** trong HTML mà không escaping. Tránh XSS và user enumeration.
2. **Không lưu toàn bộ vào log chung** nếu không có chính sách bảo vệ dữ liệu.
3. Không dựa vào text tiếng Anh/Vietnamese/vendor localization để tạo business branching.
4. **Ưu tiên code có cấu trúc**: top/sub StatusCode nếu đã được xác minh phù hợp; với lỗi local, dùng exception type và framework error code kèm bước validation.
5. Nếu log nguyên nhân vendor cần thiết cho hỗ trợ, giới hạn quyền truy cập, redaction và retention.
6. StatusDetail có thể chứa XML extension không hiểu; không tự parse bằng XML parser kém an toàn hoặc deserialize thành object tùy ý.

Một câu “User does not exist” trong StatusMessage có thể tiết lộ thông tin tài khoản. Trang đăng nhập công khai nên dùng thông báo chung, còn thông tin điều tra được giữ trong log đã kiểm soát.

## 18. Nhìn browser DevTools nhưng không bỏ qua server log

**Browser Network → Preserve log** cho thấy front-channel:
- Request ban đầu tới SP;
- GET/POST khởi tạo `/saml2/authenticate/corp`;
- Redirect/form sang IdP;
- SAMLResponse POST về SP ACS;
- Redirect tới trang thất bại hoặc tài nguyên;
- Cookie session có được gửi trong ACS POST không.

**Server log của Spring SP** cho biết kết quả xác minh và nguyên nhân local mà browser không thể biết:
- Lỗi parse Base64/XML;
- Không tìm thấy registration/issuer;
- Signature hoặc certificate mismatch;
- Audience/Destination/Recipient;
- Thời gian và correlation;
- Decryption, principal mapping;
- Failure handler được kích hoạt trước hay sau khi có Authentication.

**IdP audit/log** (nếu có quyền) cho biết:
- IdP đã nhận AuthnRequest nào;
- Cặp SP entity ID và IdP entity ID;
- User/session/method/policy (theo mức độ truy cập được cấp);
- Lý do trả SAML Status lỗi hoặc không tạo Response;
- Có MFA/ForceAuthn/IsPassive/RequestedAuthnContext được đáp ứng không;
- Có upstream proxy IdP nào liên quan.

**Không phải mọi sự cố có thể giải quyết bằng duy nhất một HAR**. Browser thấy status trong XML chưa chứng minh chữ ký; IdP logs thấy login success chưa chứng minh SP chấp nhận assertion.

## 19. Quy trình điều tra 12 bước có thể lặp lại

### Bước 1 — Chốt kịch bản

Ghi môi trường, thời điểm UTC, registration ID, public SP ACS, IdP issuer được phép, cách bắt đầu login (SP-initiated hay IdP-initiated), browser và tác vụ. Không ghi password hoặc full NameID vào ticket.

### Bước 2 — Tìm HTTP hop thất bại đầu tiên

Sử dụng DevTools/HAR đã khử dữ liệu nhạy cảm. Xác nhận có POST `SAMLResponse` tới ACS hay không. Nếu **không có**, điều tra IdP/network/browser/redirect trước khi đổ lỗi chữ ký assertion ở SP.

### Bước 3 — Xác định ai tạo HTTP status

HTTP 403 của `idp.example.org`, HTTP 403 của `app.example.org` và HTTP 403 của WAF ở trước SP là ba hệ thống khác nhau. Xem host/path/response headers có thể chia sẻ an toàn, proxy logs và trace ID.

### Bước 4 — Nếu có SAMLResponse, đọc Status một cách an toàn

Chỉ dùng môi trường test/công cụ được phép. Đọc top-level và subcode (nếu có); đặt nhãn **observed/reported** trước khi chứng minh trust. Nếu status không-Success, chưa có authenticated user mới.

### Bước 5 — Tìm sự kiện Spring authentication failure/success

Xem handler/provider logs. `Saml2AuthenticationException` có thể mô tả local validation; không suy source chỉ từ tên exception.

### Bước 6 — Kiểm chứng nguồn và registration

So `Issuer` (response/assertion) với IdP metadata đã được phê duyệt, `Destination` với ACS và `Audience` với SP entity ID. Nếu không khớp, đây là lỗi local hoặc cấu hình federation dù IdP có thể báo Success.

### Bước 7 — Kiểm chứng signature và certificates

Xem certificate trust, rollover, response/assertion signing policy. Không so Base64 string bằng mắt để kết luận chữ ký đúng. Đừng tự thêm mọi certificate từ SAMLResponse vào trust store.

### Bước 8 — Kiểm tra thời gian

Xem `IssueInstant`, `NotBefore`, `NotOnOrAfter`, SubjectConfirmation và đồng hồ NTP; đánh giá clock skew có giới hạn. Không mở rộng vài giờ chỉ vì muốn test qua.

### Bước 9 — Kiểm tra tương quan request

Với SP-initiated, so AuthnRequest ID với `InResponseTo` và session/request repository. Cookie SameSite có thể khiến IdP POST về SP mà browser không gửi session cần thiết.

### Bước 10 — Kiểm tra lỗi nghiệp vụ sau login

Nếu SP Authentication đã được tạo, request tài nguyên 403/404 tiếp theo thường là chuyện authorization, route, tenant, user provisioning hoặc downstream. Không sửa SAML StatusCode.

### Bước 11 — Ghép timeline SP–IdP

Liên hệ các mốc thời gian, SP request ID, IdP event ID và ứng dụng trace ID qua kênh log được phép. Đừng gửi assertion/raw HAR có dữ liệu cá nhân qua kênh chat công khai.

### Bước 12 — Ghi kết luận với mức độ chắc chắn

Dùng cấu trúc:

~~~text
Observed:
  - Browser posted a SAMLResponse to the expected ACS
  - The Response contains a reported top-level Responder
  - The subordinate code is NoPassive
Validated:
  - SP authentication was not established
  - The request had IsPassive=true
Attribution:
  - IdP reported inability to satisfy passive authentication
  - Signature/source verification is [verified | not verified]
Next action:
  - Check IdP passive policy and retry with a new interactive request if allowed
~~~

Đây là **template nội dung ticket**, không phải log mặc định Spring Security; không điền `verified` nếu chưa kiểm chứng. Nếu local validation fail, thay nhánh Attribution bằng chi tiết chính xác (ví dụ audience mismatch) và ghi kết quả IdP status như một quan sát riêng.

## 20. Bài thực hành Java 17 độc lập: phân loại theo chứng cứ

Chương trình này **không nhận hay xác minh SAML XML thật**. Nó chỉ mô phỏng việc phân loại dựa trên **các dữ kiện đã được quan sát/kiểm tra**: có callback đến ACS không, có status từ IdP không, kiểm tra SP có thất bại không, user đã được xác thực chưa, và sau đó có bị 403 ở ứng dụng không.

Tệp `SamlFailureTriageDemo.java`:

~~~java
public final class SamlFailureTriageDemo {

    record Evidence(
            boolean reachedAcs,
            String idpTopStatus,
            boolean localVerificationFailed,
            boolean authenticated,
            boolean accessDeniedAfterLogin) {
    }

    static String classify(Evidence evidence) {
        if (!evidence.reachedAcs()) {
            return "NO_SAML_RESPONSE_AT_ACS";
        }
        if (evidence.localVerificationFailed()) {
            return "SP_VERIFICATION_FAILED";
        }
        if (evidence.idpTopStatus() != null &&
                !"Success".equals(evidence.idpTopStatus())) {
            return "IDP_REPORTED_PROTOCOL_FAILURE";
        }
        if (evidence.authenticated() && evidence.accessDeniedAfterLogin()) {
            return "APPLICATION_AUTHORIZATION_FAILED";
        }
        if (evidence.authenticated()) {
            return "AUTHENTICATED";
        }
        return "INSUFFICIENT_EVIDENCE";
    }

    public static void main(String[] args) {
        System.out.println(classify(
                new Evidence(false, null, false, false, false)));
        System.out.println(classify(
                new Evidence(true, "Responder", false, false, false)));
        System.out.println(classify(
                new Evidence(true, "Success", true, false, false)));
        System.out.println(classify(
                new Evidence(true, "Success", false, true, true)));
        System.out.println(classify(
                new Evidence(true, "Success", false, true, false)));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac SamlFailureTriageDemo.java
java SamlFailureTriageDemo
~~~

Stdout **chính xác**:

~~~text
NO_SAML_RESPONSE_AT_ACS
IDP_REPORTED_PROTOCOL_FAILURE
SP_VERIFICATION_FAILED
APPLICATION_AUTHORIZATION_FAILED
AUTHENTICATED
~~~

**Giải thích:** dòng 1 chưa có Response; dòng 2 IdP *báo* Responder và local validation không được ghi nhận; dòng 3 IdP báo Success nhưng SP verification fail; dòng 4 SSO đã authenticated nhưng ứng dụng từ chối quyền; dòng 5 login qua được. Tham số là **dữ kiện đầu vào đã được xác nhận bên ngoài**, không phải giá trị mà mã Java này tự xác minh.

**Giới hạn bắt buộc:** nếu response chưa tin mà chứa status Responder và đồng thời lỗi signature, đặt `localVerificationFailed=true` để không coi giá trị status chưa đáng tin là nguyên nhân đã xác minh. Mã minh họa không thay đổi protocol semantics, không xử lý XML Signature, không kiểm tra OASIS schema, không phải trình SSO production.

## 21. Test matrix cho môi trường tích hợp

| Kịch bản test | Kỳ vọng IdP/browser | Kỳ vọng SP | Nhóm lỗi cần ghi |
| --- | --- | --- | --- |
| Login đúng, assertion hợp lệ | Status Success, POST Response | Tạo Authentication và phiên | Thành công |
| User không đáp ứng chính sách IdP | Có thể Response Responder/AuthnFailed hoặc IdP error page | Không tạo phiên mới | **IdP reported** nếu có status, hoặc lỗi IdP ngoài SAML |
| IsPassive=true nhưng không silent auth | Có thể Responder/NoPassive | Không tạo phiên, fallback an toàn | **IdP status**, không phải local signature error |
| RequestedAuthnContext quá cao | Có thể Responder/NoAuthnContext | Không cho phép task cần assurance | **IdP status/policy** |
| NameIDPolicy không tương thích | Có thể Requester/InvalidNameIDPolicy | Không tạo phiên | **IdP status** |
| AuthnRequest binding SP không được hỗ trợ | Có thể UnsupportedBinding, hoặc HTTP error trước ACS | Xử lý thất bại, không tự sửa binding | **IdP protocol hoặc HTTP** tùy chứng cứ |
| IdP Response Status Success nhưng ký bằng cert chưa được tin | HTTP POST Response tới ACS | Reject signature | **SP verification** |
| Status Success, Audience sai | Browser vẫn POST | Reject audience | **SP verification** |
| Status Success, Recipient/Destination sai | Browser POST nhầm hoặc đúng ACS nhưng XML destination khác | Reject | **SP verification** |
| Status Success, NotOnOrAfter hết hạn | Browser POST | Reject | **SP verification/time** |
| Status Success, InResponseTo không có request tương ứng | Browser POST | Reject tùy policy; không bỏ correlation | **SP verification/session** |
| Trống/malformed SAMLResponse | Browser POST nhưng field sai | Converter/provider fail, không tạo Authentication | **SP parsing/transport** |
| IdP HTTP 502, không có Response | Không có callback ACS | Không có Authentication mới | **IdP/proxy/network**, chưa có SAML status |
| SP authenticated rồi /admin bị 403 | Login thành công | AccessDeniedHandler/authorization | **Application authorization** |

Khi tạo test tiêu cực, chỉ dùng **test IdP/test SP** và dữ liệu mô phỏng đã được cấp quyền. Không thử sửa chữ ký người dùng thật rồi gửi vào production. Đối với kiểm tra chữ ký, dùng harness chính thức hoặc mock/test IdP với test certificate; không publish assertion, private keys và HAR chứa cookie.

## 22. Trường hợp “một mã lỗi, nhiều khả năng”

### 22.1 AuthnFailed

Một IdP có thể gửi subcode `AuthnFailed` khi:
- User nhập sai thông tin;
- User không hoàn thành MFA;
- Account bị khóa/không được phép theo policy;
- Upstream IdP trả lỗi;
- Risk engine từ chối phiên.

Đừng xuất nguyên trạng thái account cho user cuối. Lấy chi tiết từ **IdP audit** trong phạm vi quyền truy cập, không đoán từ SAML StatusCode.

### 22.2 Requester

Có thể do SP AuthnRequest không đúng chữ ký, NameIDPolicy, entity ID, binding, ACS mà IdP chấp nhận hoặc policy SP. Không kết luận rằng HTTP request từ browser là sai chỉ vì mã là Requester; **requester ở đây là SAML requester**.

### 22.3 Responder

Có thể do IdP không xử lý được yêu cầu, không có session/passive, lỗi dịch vụ, upstream identity hoặc policy. Nhưng một HTTP 502 của IdP không tự biến thành Responder nếu không phát SAML Response.

### 22.4 Success + login failure

Triage bắt đầu từ **SP verification and application pipeline**: signature, trust, issuer, audience, subject, time, correlation, decryption, principal mapping. Nếu IdP log ghi “success” chỉ phản ánh góc nhìn IdP.

### 22.5 Không có status

Lỗi xảy ra trước khi có SAML Response: browser đóng trang, CORS được chẩn đoán nhầm, cookie third-party, DNS, TLS, IdP HTML error, 404/405 ACS, WAF block. Không bịa một status như AuthnFailed trong báo cáo.

## 23. Lỗi cookie/RelayState thường bị gọi nhầm là lỗi IdP

Với SP-initiated SSO, Spring Security mặc định có thể lưu AuthnRequest trong HTTP session. Browser từ IdP thường **cross-site POST** SAMLResponse về ACS. Nếu cookie có `SameSite=Lax` hoặc `Strict`, browser có thể không gửi cookie SP trên POST đó theo chính sách, khiến Spring mất request correlation.

Các dấu hiệu:
- Browser đã POST response tới ACS đúng path.
- IdP audit có event xác thực thành công.
- Spring SP không tìm được request đã lưu, `InResponseTo` mismatch hoặc xử lý unsolicited response khác mong đợi.
- SAML status có thể Success nhưng SP từ chối do **thiếu trạng thái phiên/correlation local**.

Hướng xử lý:
1. Kiểm tra header `Set-Cookie` trước redirect và `Cookie` trên ACS POST trong môi trường test.
2. Đối chiếu SameSite/Secure/Domain/Path và public HTTPS URL/reverse proxy.
3. Xem sticky session/Spring Session/distributed store trong hệ nhiều replica.
4. Chọn chính sách cookie phù hợp với SSO cross-site mà vẫn bảo vệ CSRF/login fixation.
5. Không bỏ `InResponseTo` hoặc cho phép mọi unsolicited response chỉ để login chạy lại.

Đây là **lỗi nhận/kiểm chứng giao dịch tại SP/browser**, không có bằng chứng IdP đã trả `AuthnFailed`.

## 24. Lỗi mapping/authorization sau khi SP đã chấp nhận SAML

Một người dùng có SAML assertion đã xác minh, Spring đã tạo `Authentication` trong SecurityContext, rồi truy cập:

~~~http
GET /portal/admin HTTP/1.1
Host: app.example.org
~~~

Ứng dụng trả:

~~~http
HTTP/1.1 403 Forbidden
~~~

Đây có thể là Spring Security authorization do thiếu authority, role mapping chưa thiết lập, user chưa được provisioning hoặc tenant policy không cho phép. Không có lý do gì mặc định để đọc lại `Responder` ở IdP.

Giải thích:
- **Authentication:** IdP + SP xác định người dùng là ai.
- **Authorization:** ứng dụng quyết định user được phép làm gì.
- Mặc định Spring Security SAML provider có thể tạo authority cơ sở cho authenticated user; nó **không tự ánh xạ mọi group của IdP thành admin role**.
- Một `AttributeStatement` chứa group/role chưa được chuẩn hóa/trust theo policy không đủ để cấp quyền tùy ý.
- Nếu lỗi xảy ra trong `UserDetailsService` hoặc custom converter sau validation, vẫn có thể đi qua authentication failure. Cần phân biệt **custom local mapping** với IdP protocol status.

Đội vận hành nên kiểm tra `Authentication.isAuthenticated()`, authorities và rule của route **mà không log raw NameID/attributes**.

## 25. Ghi log và metric theo lớp nguyên nhân

Không dùng một metric `saml_error_total` rồi suy mọi lỗi là “IdP down”. Một taxonomy hữu ích:

| Nhóm metric/log | Định nghĩa | Ví dụ nhãn an toàn |
| --- | --- | --- |
| `idp_saml_status_reported` | Thực sự quan sát SAML StatusCode không-Success | topCode=`Responder`, subCode=`NoPassive`, trust=`verified/unverified` |
| `sp_saml_validation_failed` | Provider/validation local từ chối Response | category=`signature/issuer/audience/time/correlation/decryption/other` |
| `saml_transport_failed` | Không có Response hợp lệ tới ACS do HTTP/route/network | stage=`idp/acs/browser/proxy` |
| `app_authorization_denied` | Đã authenticated nhưng không có quyền route | routeGroup=`admin/orders/other` |
| `saml_login_success` | SP tạo Authentication sau validation | registrationId đã được giới hạn nhãn |

**Không đưa NameID, email, SAMLResponse, RelayState random hay ID phiên vào metric label**: chúng gây high cardinality và rủi ro thông tin cá nhân. Chi tiết request có thể lưu trong log hạn chế truy cập dưới correlation ID/timestamp và retention policy.

Phân biệt `reported` với `verified`. Một raw status quan sát được khi chữ ký không hợp lệ không nên được thống kê như **sự thật IdP đã quyết định**. Số lỗi validation đáng kể có thể là dấu hiệu cấu hình sai, cert rollover hoặc tấn công; đừng tự động coi là lỗi người dùng.

## 26. Quy tắc hiển thị lỗi cho người dùng cuối

Người dùng cần hướng tiếp theo chứ không cần stack trace SAML:

- Khi IdP báo `NoPassive` trong flow silent: có thể hiển thị “Không thể đăng nhập tự động; vui lòng chọn Đăng nhập để tiếp tục”, sau đó phát **request interactive mới** nếu được phép.
- Khi IdP báo `NoAuthnContext`: hiển thị “Không thể đáp ứng yêu cầu xác thực của dịch vụ; liên hệ bộ phận hỗ trợ”, không tiết lộ chi tiết chính sách MFA.
- Khi response bị SP từ chối chữ ký/issuer/audience: hiển thị lỗi chung với mã hỗ trợ; không nói chi tiết key/trust anchor cho client.
- Khi người dùng đã xác thực nhưng bị 403: hiển thị “Tài khoản hiện không có quyền truy cập tài nguyên này”; hướng yêu cầu quyền theo quy trình.
- Khi IdP không trả Response: hiển thị thử lại hoặc hỗ trợ sau khi xem network status; **không tuyên bố “sai tài khoản” nếu chưa có bằng chứng**.

Tránh mọi cách sửa nhanh phá an ninh:
- `csrf.disable()` trên toàn bộ app;
- Bỏ XML signature verification;
- Tin mọi certificate xuất hiện trong response;
- Bỏ Issuer/Audience/Recipient/InResponseTo validation;
- Chấp nhận assertion quá hạn vô điều kiện;
- Tăng clock skew thành vô hạn;
- Tạo `Authentication` chỉ vì status = Success;
- Log hoặc hiển thị raw `StatusMessage` chưa được xử lý.

## 27. Bài tập kèm đáp án

**Bài 1.** Browser nhận HTTP 200 từ IdP, trang trả form POST chứa `SAMLResponse` và XML bên trong có `Responder / NoPassive`. HTTP 200 chứng minh login thành công không?

**Đáp án:** không. 200 ở đây là HTTP chứa form; protocol status nói IdP báo không đáp ứng passive. SP không được cấp Authentication từ Response lỗi.

**Bài 2.** IdP audit ghi Success, browser POST SAMLResponse đến ACS, Spring log “invalid signature”. Đây là mã lỗi ở đâu?

**Đáp án:** lỗi **xác minh tại SP** (trust/chữ ký), dù IdP báo giao thức thành công. Kiểm tra signing cert/metadata/cert rotation/payload và policy; không đổi StatusCode.

**Bài 3.** XML có top-level `Requester` và nested `InvalidNameIDPolicy`. Có phải user nhập sai password?

**Đáp án:** không có bằng chứng. Đó là lỗi IdP báo request/policy NameID không phù hợp; điều tra AuthnRequest NameIDPolicy và IdP capability.

**Bài 4.** SAML Response báo Success và chữ ký hợp lệ nhưng audience là SP khác. Có được tạo Authentication không?

**Đáp án:** không. Assertion không cấp cho SP hiện tại; **SP audience validation fail**. Chữ ký không biến audience sai thành đúng.

**Bài 5.** Login thành công nhưng `GET /admin` trả HTTP 403. Nên phân loại thế nào?

**Đáp án:** nếu Authentication thật sự được tạo và còn hiệu lực, đây là **authorization/application failure**. Xem role mapping/quyền, không mặc định sửa IdP status.

**Bài 6.** `Saml2AuthenticationException` có `getSaml2Error().getErrorCode()`. Có thể coi mọi giá trị đó là OASIS StatusCode IdP không?

**Đáp án:** không. Đó là mã lỗi framework của Spring, có thể mô tả lỗi local. Chỉ gọi IdP status khi có chứng cứ XML SAML status từ responder và đã đánh giá trust phù hợp.

**Bài 7.** Browser không có POST SAMLResponse tới ACS; IdP trả HTML 500. Có thể kết luận top-level Responder không?

**Đáp án:** không. Chưa có Response chứa SAML StatusCode; điều tra HTTP/network/IdP service trước.

**Bài 8.** Người dùng có login mới từ IdP, nhưng Spring không tìm thấy `InResponseTo`. Có nên tắt correlation không?

**Đáp án:** không. Kiểm tra SP session cookie SameSite/Secure, request repository, browser và multi-node state. Correlation là một phần quan trọng chống login fixation/replay.

**Bài 9.** XML thô chứa `Responder / AuthnFailed` nhưng signature/issuer không hợp lệ. Báo cáo “IdP từ chối người dùng” có chắc chắn không?

**Đáp án:** không chắc. Giá trị status là **quan sát chưa được tin**; điều chắc chắn hơn là **SP không xác minh được response**. Phải xác minh nguồn/IdP logs trước khi gán nguyên nhân.

**Bài 10.** IdP báo `NoAuthnContext`, nhưng application log thêm lỗi “principal missing”. Nhóm nào cần ưu tiên đối chiếu?

**Đáp án:** nếu có chứng cứ status đáng tin, IdP báo không đáp ứng RequestedAuthnContext; không nên kỳ vọng principal từ một response thất bại. Đồng thời kiểm tra SP xử lý status, không cố tạo subject giả để qua.

**Bài 11.** Request từ SP tới IdP bị WAF chặn HTTP 414 do URL dài. Loại lỗi gì?

**Đáp án:** lỗi HTTP/transport/binding trước khi IdP phát SAML Response; chưa có top-level status để báo. Xem HTTP-Redirect URL limit và khả năng HTTP-POST AuthnRequest.

**Bài 12.** SP có nhiều IdP registration, response tới đúng ACS nhưng issuer là IdP B trong khi SP chọn registration A. Đây có phải IdP “AuthnFailed” không?

**Đáp án:** không. Đây là **SP registration/issuer trust mismatch** hoặc cấu hình federation sai; không chuyển registration theo issuer chưa xác minh một cách tùy tiện.

## 28. Checklist bàn giao sự cố SAML

- [ ] Xác định chính xác URL public của SP/ACS, registrationId và IdP issuer đã được phê duyệt.
- [ ] Có timeline HTTP: browser thực sự POST SAMLResponse tới ACS hay không.
- [ ] Không đồng nhất HTTP status, XML StatusCode, exception Java và authorization 403.
- [ ] Nếu có Response, đọc **top-level SAML status**, nested subcode nếu có; không đòi subcode bắt buộc.
- [ ] Ghi rõ status quan sát được là **verified** hay **unverified** theo nguồn tin cậy.
- [ ] Kiểm tra liệu IdP đã tạo Assertion thành công hay chỉ trả Response báo lỗi.
- [ ] Nếu top-level Success, vẫn xác minh signature, issuer, destination, audience, thời hạn, subject, replay, correlation và decryption.
- [ ] Nếu Spring báo `Saml2AuthenticationException`, lưu error code **framework** riêng với status **protocol**.
- [ ] Khi có 403 sau Authentication, kiểm tra role/authority/tenant/route, không gộp vào IdP failure.
- [ ] Đánh giá cookie SameSite/Secure, request repository và session khi InResponseTo mismatch.
- [ ] Có đối chiếu IdP audit trong trường hợp kết luận IdP policy/account/MFA.
- [ ] Không hiển thị hay log raw StatusMessage, SAMLResponse, assertion, cookie, RelayState hoặc dữ liệu cá nhân.
- [ ] Failure handler chỉ cung cấp thông báo chung/mã hỗ trợ, không tắt validation.
- [ ] Ghi hành động tiếp theo đúng chủ sở hữu: IdP team, SP/security team, network team hoặc application team.

## 29. Kết luận

**Lỗi do IdP báo qua SAML StatusCode và lỗi do Spring Security SP phát hiện khi xác minh là hai lớp thông tin khác nhau.** Một Response có thể mang `Responder / NoPassive` để thông báo IdP không thỏa yêu cầu; hoặc mang `Success` nhưng vẫn bị SP từ chối vì chữ ký, issuer, audience, điều kiện thời gian hay correlation không hợp lệ. Không có POST Response thì có thể **không tồn tại mã trạng thái SAML nào** để đọc; 403 sau đăng nhập cũng có thể chỉ là authorization.

Để điều tra có căn cứ, luôn ghép **HTTP trace + protocol status (với đánh giá trust) + SP verification logs + IdP audit + application authorization**. Giữ nguyên mọi kiểm tra bảo mật và trình bày lỗi cho người dùng bằng thông điệp phù hợp, không lộ nội dung SAML nhạy cảm.

### Tài liệu chính thức

1. OASIS — SAML V2.0 Core, mục 3.2.2 `StatusResponseType`, `Status`, `StatusCode` và tập top/sub codes: https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf
2. OASIS — SAML V2.0 Approved Errata (làm rõ second-level StatusCode có thể tùy chọn): https://docs.oasis-open.org/security/saml/v2.0/sstc-saml-approved-errata-2.0.pdf
3. Spring Security — SAML 2.0 Login Overview, filters và provider validation: https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html
4. Spring Security — Authenticating SAML Responses: https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html
5. Spring Security 6.5 — Authenticating SAML Responses (tham chiếu cho OpenSAML 4): https://docs.spring.io/spring-security/reference/6.5/servlet/saml2/login/authentication.html
6. Spring Security API — `Saml2AuthenticationException`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/saml2/provider/service/authentication/Saml2AuthenticationException.html
7. Spring Security API — `Saml2Error` (framework local error code): https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/saml2/core/Saml2Error.html
8. Spring Security — Producing AuthnRequests / request repository: https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication-requests.html
