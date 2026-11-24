# SAML federation trong quản lý vòng đời danh tính IAM

**SAML federation** là mô hình liên kết tin cậy giữa hệ thống quản lý danh tính (**Identity Provider – IdP**) và ứng dụng sử dụng kết quả xác thực (**Service Provider – SP**) thông qua **Security Assertion Markup Language 2.0 (SAML 2.0)**. Thay vì mỗi ứng dụng tự yêu cầu và kiểm tra mật khẩu doanh nghiệp, SP có thể nhận một **SAML assertion** đã được IdP phát hành và bảo vệ bằng chữ ký số, sau đó tạo phiên đăng nhập cục bộ cho đúng người dùng.

Bài thuộc chương **Federation**, module **SECURITY_IDENTITY_ACCESS_MANAGEMENT_IDENTITY_LIFECYCLE**. Module tập trung quản lý vòng đời danh tính trong IAM theo **Joiner–Mover–Leaver (JML)**: xác minh danh tính, tạo account, cấp và rà soát quyền, thu hồi khi vai trò thay đổi hoặc chấm dứt quan hệ. SAML federation là một mảnh ghép của **IdP/SSO**, phải kết hợp với **SCIM provisioning**, phân quyền **RBAC/ABAC**, kiểm toán và quản trị tài khoản dịch vụ để tránh **quyền truy cập tồn dư**.

**Tình huống mở đầu:** Một nhân viên được cấp account trong IdP của công ty và đăng nhập vào ứng dụng quản lý nhân sự của nhà cung cấp SaaS. SP chuyển người dùng tới IdP; IdP xác thực bằng MFA rồi trả về SAML Response. SP kiểm tra thông điệp và tạo session. Nếu nhân viên chuyển bộ phận hoặc nghỉ việc, việc cập nhật role/disable ở IdP **không mặc nhiên xóa ngay local session hay tài khoản tại SaaS**. Vì vậy phải hiểu đồng thời cả **federation trust** và **identity lifecycle**.

## 1. SAML federation giải quyết vấn đề gì?

Trong kiến trúc có nhiều ứng dụng, cho mỗi hệ thống giữ một mật khẩu doanh nghiệp độc lập gây khó quản lý: khó triển khai MFA đồng nhất, khó thu hồi khi Leaver, tăng nguy cơ tái sử dụng mật khẩu và phân tán log.

SAML federation hỗ trợ:

- **Single Sign-On (SSO):** người dùng có thể sử dụng phiên xác thực tại IdP để vào nhiều SP mà không phải nhập lại password của từng ứng dụng, tùy chính sách phiên.
- **Trust giữa tổ chức và ứng dụng:** SP có thể tin assertion do IdP đã cấu hình phát hành, thay vì lưu và kiểm mật khẩu của người dùng.
- **Tách trách nhiệm:** IdP thực hiện xác thực và chính sách MFA; SP chịu trách nhiệm xác minh assertion, duy trì session và kiểm soát quyền trong ứng dụng.
- **Tích hợp đối tác:** nhà thầu hoặc người dùng doanh nghiệp liên kết có thể xác thực tại IdP được SP chấp thuận theo hợp đồng federation.
- **Kiểm toán tập trung một phần:** IdP có log sự kiện xác thực; SP có log session và quyền được sử dụng.

Tuy nhiên, **SAML không phải một cơ chế quản lý đầy đủ toàn bộ vòng đời tài khoản**. Việc tạo, cập nhật, disable hoặc xóa user tại SP có thể cần **SCIM/API/connector**, còn việc gỡ quyền chi tiết phụ thuộc mô hình phân quyền của ứng dụng.

### Federation khác với việc chia sẻ mật khẩu

SP không cần nhận mật khẩu doanh nghiệp của người dùng. Thay vào đó, SP nhận **khẳng định** từ IdP đáng tin rằng một chủ thể đã được xác thực theo ngữ cảnh cụ thể. SP phải xác minh thông điệp chặt chẽ; nó **không được tin** một trường email, role hoặc tên đăng nhập đơn lẻ do trình duyệt gửi lên.

## 2. Các thành phần và thuật ngữ cốt lõi

| Thuật ngữ | Vai trò | Ý nghĩa vận hành |
| --- | --- | --- |
| **Principal / subject** | Người dùng được xác thực. | Có thể là nhân viên, nhà thầu hoặc người dùng đối tác. |
| **Identity Provider (IdP)** | Xác thực người dùng và phát hành SAML assertion. | Quản lý MFA, session IdP, chính sách xác thực và signing key. |
| **Service Provider (SP)** | Ứng dụng dựa vào assertion để đăng nhập. | Kiểm chữ ký và các ràng buộc, liên kết user, tạo local session, kiểm quyền. |
| **Relying party / trust relationship** | Quan hệ các bên đồng ý tin khẳng định từ nguồn đã cấu hình. | Gắn với entityID, endpoint, chứng chỉ và policy cụ thể. |
| **AuthnRequest** | Yêu cầu xác thực do SP tạo trong SP-initiated SSO. | Mang request ID, issuer, ACS và tùy chọn ngữ cảnh xác thực. |
| **SAML Response** | Thông điệp IdP gửi tới SP. | Có thể mang một hoặc nhiều assertion, trạng thái xử lý và chữ ký. |
| **Assertion** | Bộ khẳng định về subject, authentication và/hoặc attributes. | Phải hợp lệ về chữ ký, thời gian, audience và subject confirmation. |
| **NameID** | Định danh của subject trong assertion. | Cần mapping ổn định và chính sách tránh gộp nhầm account. |
| **Assertion Consumer Service (ACS)** | Endpoint SP nhận SAML Response. | Phải thuộc endpoint hợp lệ được đăng ký và bảo vệ. |
| **Entity ID (entityID)** | Định danh logic duy nhất trong quan hệ federation. | Không nhất thiết là một URL có thể truy cập bằng trình duyệt. |
| **Metadata** | Tài liệu XML mô tả entity, endpoint, binding và khóa/chứng chỉ. | Cần kiểm soát nguồn, tính toàn vẹn và vòng đời certificate. |
| **Binding** | Cách vận chuyển thông điệp SAML. | Ví dụ HTTP-Redirect, HTTP-POST, HTTP-Artifact. |
| **RelayState** | Tham số để khôi phục trạng thái điều hướng hoặc yêu cầu tại SP. | Phải chống open redirect, tráo state và nhầm phiên. |

SAML còn có các mô hình khác như attribute query, nhưng với tình huống đăng nhập doanh nghiệp, trọng tâm là **SAML 2.0 Web Browser SSO Profile**.

## 3. Sơ đồ kiến trúc federation

~~~mermaid
flowchart LR
    H["HRIS / Sponsor<br/>Sự kiện JML"] --> IGA["IAM / IGA<br/>Lifecycle + approval"]
    IGA --> IDP["IdP<br/>Identity + MFA + SSO"]
    IGA --> PROV["SCIM / Provisioning connector"]
    U["Người dùng / Browser"] --> SP["SAML Service Provider<br/>SaaS / Web App"]
    SP -->|AuthnRequest| U
    U -->|Yêu cầu xác thực| IDP
    IDP -->|SAML Response qua browser| U
    U -->|POST đến ACS| SP
    PROV -->|Tạo / sửa / khóa user + nhóm| SP
    SP --> AUTHZ["SP Authorization<br/>RBAC / ABAC / ACL"]
    IDP --> AUD["Audit / SIEM"]
    SP --> AUD
    IGA --> AUD
~~~

Hai luồng cần phân biệt:

1. **Authentication federation:** IdP chứng minh một lần xác thực đã diễn ra; SP kiểm tra assertion để quyết định có lập phiên đăng nhập hay không.
2. **Identity provisioning:** IAM/IGA hoặc connector tạo, cập nhật và thu hồi account/role tại SP theo sự kiện JML. Luồng này **không tự động xuất hiện chỉ vì SAML SSO chạy thành công**.

Một SP có thể dùng **Just-In-Time (JIT) provisioning** để tạo account lúc đăng nhập SAML lần đầu. Tuy nhiên, JIT phải có mapping đáng tin, điều kiện tạo tài khoản và đặc biệt là cơ chế **deprovisioning** sau đó; không nên xem JIT là giải pháp hoàn chỉnh cho Leaver.

## 4. Thiết lập trust giữa IdP và SP

Trước lần đăng nhập đầu tiên, các bên cần cấu hình quan hệ tin cậy theo **đúng môi trường, ứng dụng và tenant**.

| Thuộc tính cấu hình | Ví dụ minh họa | Ý nghĩa bảo mật |
| --- | --- | --- |
| IdP entityID | https://idp.example.org/saml | Chỉ nhận assertion từ issuer được tin cậy. |
| SP entityID | urn:example:finance-saas:prod | Chỉ chấp nhận assertion dành cho đúng SP. |
| ACS URL | https://finance.example.org/saml/acs | Đích nhận response đã đăng ký; tránh gửi assertion sai nơi. |
| IdP SSO URL | https://idp.example.org/saml/sso | Endpoint trình duyệt gửi AuthnRequest. |
| Signing certificate/key | Chứng chỉ xác minh chữ ký IdP. | SP kiểm chữ ký bằng trust anchor được cấu hình. |
| SP request signing | Theo hợp đồng SP/IdP. | IdP có thể kiểm AuthnRequest nếu yêu cầu và cấu hình hỗ trợ. |
| Response/assertion signature requirement | Chính sách chữ ký của integration. | Định nghĩa cấu trúc XML nào phải được ký và kiểm như thế nào. |
| Encryption setting | Theo phân loại dữ liệu và chính sách. | Có thể mã hóa assertion cho SP; **không thay thế chữ ký**. |
| NameID format | Persistent hoặc format đã thỏa thuận. | Ổn định mapping và tránh gộp sai user. |
| Attribute contract | employeeId, department, role... nếu cần. | Quy định nguồn có thẩm quyền và ý nghĩa của từng thuộc tính. |
| Clock skew và validity window | Giá trị nhỏ, được phê duyệt. | Tránh dùng assertion ngoài thời gian hợp lệ. |
| SLO support | Có hoặc không, mức hỗ trợ thực tế. | Không hứa hủy tất cả session khi chưa được kiểm thử. |

Đây là **ví dụ cấu hình**, không phải các endpoint hoạt động thật.

### Metadata là hợp đồng kỹ thuật

SAML metadata thường chứa **EntityDescriptor**, **IDPSSODescriptor** hoặc **SPSSODescriptor**, **KeyDescriptor**, **SingleSignOnService**, **AssertionConsumerService** và các thuật toán/binding hoặc thuộc tính liên quan. Phía vận hành cần:

- Nhận metadata qua kênh đáng tin và xác minh nguồn/tính toàn vẹn theo trust policy.
- Kiểm tra **entityID**, endpoint, binding và certificate chính xác trước khi bật production.
- Không tự tin mọi chứng chỉ xuất hiện trong một XML mới tải về khi **nguồn metadata chưa được xác thực**.
- Theo dõi chứng chỉ sắp hết hạn, kế hoạch rotation và sự thay đổi endpoint bất thường.
- Tách cấu hình **dev/staging/prod**, tránh để một IdP thử nghiệm phát assertion được chấp nhận tại SP production.

Một chứng chỉ chứa trong metadata có thể được dùng như **khóa xác minh chữ ký được trust cấu hình**; không nên đánh đồng việc kiểm chữ ký SAML với việc yêu cầu chứng chỉ đó luôn được xác minh theo cùng mô hình public Web PKI của chứng chỉ HTTPS.

## 5. SP-initiated SAML SSO: luồng phổ biến

Trong **SP-initiated SSO**, người dùng bắt đầu từ ứng dụng và SP gửi yêu cầu xác thực tới IdP.

~~~mermaid
sequenceDiagram
    actor U as Người dùng
    participant B as Browser
    participant SP as Service Provider
    participant IDP as Identity Provider
    U->>B: Mở ứng dụng cần đăng nhập
    B->>SP: GET tài nguyên chưa có session
    SP->>SP: Sinh AuthnRequest ID và lưu state
    SP-->>B: Redirect / POST AuthnRequest
    B->>IDP: Chuyển AuthnRequest
    IDP->>IDP: Kiểm SP trust và request
    IDP->>U: Xác thực/MFA nếu cần
    IDP->>IDP: Phát hành Response + Assertion
    IDP-->>B: HTML form / SAMLResponse
    B->>SP: POST SAMLResponse đến ACS
    SP->>SP: Kiểm signature, issuer, audience,<br/>recipient, InResponseTo, time, replay
    SP->>SP: Map subject + kiểm trạng thái/quyền
    SP-->>B: Tạo session cục bộ an toàn
    B->>SP: Request ứng dụng đã xác thực
~~~

Các bước nghiệp vụ:

1. **SP khởi tạo request:** tạo ID khó đoán, lưu correlation với session/transaction và target resource hợp lệ; xác định ACS và issuer.
2. **Trình duyệt chuyển request:** thường sử dụng HTTP-Redirect binding hoặc HTTP-POST binding theo cấu hình.
3. **IdP xác minh request:** kiểm SP được phép, request signature khi policy yêu cầu, endpoint, chính sách xác thực và người dùng.
4. **Người dùng hoàn tất xác thực:** IdP có thể dùng phiên SSO sẵn có hoặc yêu cầu MFA/reauthentication.
5. **IdP phát hành SAML Response:** có thông tin chủ thể, audience, thời gian, subject confirmation, dữ liệu xác thực và chữ ký theo cấu hình tin cậy.
6. **Browser POST về ACS:** SP nhận response qua endpoint đã đăng ký.
7. **SP kiểm chứng theo giao thức:** không dùng assertion trước khi toàn bộ kiểm tra bắt buộc PASS.
8. **SP liên kết account:** dựa vào subject identifier đáng tin, không tự gộp theo tên/email không đủ căn cứ.
9. **SP thiết lập local session:** cookie được bảo vệ, gắn với danh tính đã kiểm tra; authorization vẫn được thực thi tại backend.

**Lưu ý:** IdP có thể tạo assertion trong lúc người dùng đã có session IdP, nên **mỗi lần nhận SAML Response không nhất thiết tương ứng với một lần nhập lại mật khẩu/MFA mới**.

## 6. IdP-initiated SSO và giới hạn bảo mật

Trong **IdP-initiated SSO**, người dùng bắt đầu từ portal IdP, chọn ứng dụng rồi IdP phát hành SAML Response trực tiếp tới ACS của SP. Thường **không có AuthnRequest do SP tạo**, nên SP có thể không có **InResponseTo** để đối chiếu với một request đã lưu.

| Khía cạnh | SP-initiated | IdP-initiated |
| --- | --- | --- |
| Nơi người dùng bắt đầu | SP. | Portal IdP. |
| Có AuthnRequest của SP | Thường có. | Thường không. |
| Kiểm InResponseTo | Có thể/bắt buộc với response unsolicited không được phép. | Không có request ID tương ứng như SP-initiated. |
| Tình trạng transaction tại SP | Có state ban đầu để liên kết. | Khó liên kết với một transaction được SP khởi tạo. |
| Mối quan tâm bổ sung | Phải kiểm request ID, state, response correlation. | Phải kiểm soát unsolicited response, replay, account linking và session confusion. |

Nếu SP hỗ trợ IdP-initiated, phải **chủ động định nghĩa trust policy**, chỉ chấp nhận unsolicited response từ IdP được cấu hình, kiểm chữ ký, thời gian, issuer, audience, recipient, replay và chống login CSRF/session confusion. Với ứng dụng nhạy cảm hoặc khó bảo đảm correlation, nên cân nhắc **chỉ hỗ trợ SP-initiated**.

**Không áp dụng một quy tắc cứng “mọi response đều phải có InResponseTo”** cho cả IdP-initiated hợp lệ; thay vào đó cấu hình chính sách riêng, không vô tình mở đường unsolicited cho SP vốn chỉ cho phép SP-initiated.

## 7. Các thông điệp SAML quan trọng

### AuthnRequest

AuthnRequest mang yêu cầu xác thực từ SP. Ví dụ XML **rút gọn, không có chữ ký và chưa đủ để gửi production**:

~~~xml
<samlp:AuthnRequest
    xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    ID="_req-9f7a" Version="2.0"
    IssueInstant="2026-11-23T02:00:00Z"
    Destination="https://idp.example.org/saml/sso"
    AssertionConsumerServiceURL="https://finance.example.org/saml/acs">
  <saml:Issuer>urn:example:finance-saas:prod</saml:Issuer>
</samlp:AuthnRequest>
~~~

Các thuộc tính quan trọng có thể gồm **ID**, **Version**, **IssueInstant**, **Destination**, **Issuer**, **AssertionConsumerServiceURL** hoặc **AssertionConsumerServiceIndex**, **ProtocolBinding**, **ForceAuthn**, **IsPassive**, **RequestedAuthnContext**. Không phải mọi thuộc tính đều có trong từng yêu cầu.

**ForceAuthn** thể hiện SP yêu cầu IdP xác thực lại thay vì chỉ sử dụng phiên hiện tại nếu IdP xử lý theo ngữ nghĩa giao thức; ứng dụng vẫn phải kiểm kết quả và chính sách thực tế. **RequestedAuthnContext** mô tả ngữ cảnh xác thực được yêu cầu, nhưng chỉ có ý nghĩa với IdP và các ánh xạ assurance đã thỏa thuận.

### Response và Assertion

Ví dụ XML **cố ý giản lược và KHÔNG PHẢI assertion sử dụng được**:

~~~xml
<samlp:Response
    xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    ID="_res-7421" Version="2.0"
    InResponseTo="_req-9f7a"
    Destination="https://finance.example.org/saml/acs">
  <saml:Issuer>https://idp.example.org/saml</saml:Issuer>
  <samlp:Status>
    <samlp:StatusCode
        Value="urn:oasis:names:tc:SAML:2.0:status:Success"/>
  </samlp:Status>
  <saml:Assertion ID="_assert-3081" Version="2.0">
    <saml:Issuer>https://idp.example.org/saml</saml:Issuer>
    <saml:Subject>
      <saml:NameID>person-4821</saml:NameID>
      <!-- Thực tế cần SubjectConfirmation/SubjectConfirmationData phù hợp -->
    </saml:Subject>
    <!-- Thực tế cần các ràng buộc Conditions, AudienceRestriction,
         AuthnStatement, chữ ký và kiểm tra giao thức theo trust policy -->
  </saml:Assertion>
</samlp:Response>
~~~

**Không sao chép ví dụ này thành response hợp lệ**: thiếu thuộc tính và phần tử bảo mật bắt buộc theo profile, không có chữ ký số. XML phục vụ học cấu trúc mà không chứa dữ liệu nhạy cảm thật.

| Trường/thành phần | SP phải hiểu gì? |
| --- | --- |
| **Response/Assertion ID** | Dùng để nhận diện và chống phát lại theo phạm vi/time window. |
| **Issuer** | Bên phát hành có nằm trong quan hệ tin cậy được cấu hình? |
| **Signature** | Chữ ký bảo vệ chính phần XML được sử dụng ra quyết định có hợp lệ? |
| **Destination** | Response có gửi đến ACS của SP hiện tại không? |
| **InResponseTo** | Với SP-initiated, có khớp request chờ xử lý của đúng phiên không? |
| **Subject/NameID** | Chủ thể nào được xác nhận, mapping tới account SP ra sao? |
| **SubjectConfirmationData** | Recipient, thời hạn, InResponseTo và các điều kiện bearer confirmation có đạt không? |
| **Conditions** | Assertion có nằm trong cửa sổ thời gian và giới hạn sử dụng được phép không? |
| **AudienceRestriction** | Assertion có dành cho entityID của SP này không? |
| **AuthnStatement/AuthnContext** | IdP xác thực khi nào và theo ngữ cảnh nào? |
| **AttributeStatement** | Những thuộc tính được cấp, theo contract và nguồn nào? |

Một SAML Response có thể được ký ở **Response** hoặc **Assertion** tùy profile/trust configuration; phải kiểm đúng lớp chữ ký mà chính sách yêu cầu và bảo đảm **assertion SP sử dụng là phần nằm trong phạm vi dữ liệu đã được bảo vệ**.

## 8. Binding: thông điệp đi qua trình duyệt như thế nào?

| Binding | Mô tả | Điểm cần kiểm soát |
| --- | --- | --- |
| **HTTP-Redirect** | Thường dùng gửi AuthnRequest qua redirect URL, nén/encode theo đặc tả binding. | Chữ ký request trong query nếu sử dụng; độ dài URL; RelayState; không đưa secret vào query. |
| **HTTP-POST** | Thường dùng form POST chứa SAMLResponse base64-encoded XML tới ACS. | HTTPS, kiểm XML/chữ ký ở server, bảo vệ CSRF/login CSRF theo mô hình SAML. |
| **HTTP-Artifact** | Browser mang artifact thay vì toàn bộ assertion; SP giải quyết artifact qua back channel với IdP. | Bảo vệ back channel, endpoint, issuer, replay và thời hạn artifact. |

Một sơ đồ thường thấy: **AuthnRequest qua Redirect, SAMLResponse qua POST**. Nhưng đây không phải tổ hợp duy nhất; lựa chọn phụ thuộc metadata và cấu hình của hai bên.

### RelayState không phải giấy phép chuyển hướng bất kỳ

SP có thể lưu tham chiếu trạng thái điều hướng để trở lại tài nguyên ban đầu. Nếu RelayState chứa URL không kiểm soát, attacker có thể lợi dụng tạo **open redirect** sau đăng nhập. Nếu state không được ràng buộc với transaction, có thể xảy ra **login CSRF** hoặc nhầm phiên.

Thiết kế nên dùng **state/reference ngẫu nhiên phía server**, đối chiếu thời hạn và transaction, chỉ cho phép đường dẫn nội bộ hoặc đích trong allowlist; không tin một redirect URL do client tự định nghĩa.

## 9. Kiểm chứng SAML Response tại ACS: các điều kiện bắt buộc

Đây là phần quan trọng nhất của SAML federation. **SP không được tự xây parser XML và kiểm tra vài chuỗi ký tự rồi lập session**. Hãy sử dụng thư viện SAML bảo trì tốt, được cấu hình để áp đầy đủ hợp đồng tin cậy.

Checklist về mặt khái niệm:

1. **Đúng endpoint và binding:** chỉ xử lý SAMLResponse qua ACS/binding đã đăng ký với ứng dụng.
2. **Giới hạn đầu vào:** áp kích thước request, cơ chế giải mã/nén an toàn, chống XML entity expansion, XXE và DoS.
3. **Đúng định dạng và status:** parse XML theo schema/profile; kiểm Status và cấu trúc Response/Assertion hợp lệ.
4. **Xác thực chữ ký:** sử dụng khóa công khai đã tin cậy cho **IdP cụ thể** và chỉ chấp nhận thuật toán/canonicalization theo allowlist bảo mật.
5. **Không bị XML Signature Wrapping:** dữ liệu dùng cho quyết định danh tính/quyền phải chính là phần tử đã được ký và được thư viện xác minh, không tìm tùy tiện phần tử cùng tên ở nơi khác.
6. **Kiểm Issuer:** Response/Assertion phải đến từ đúng IdP đã cấu hình cho SP/tenant đang đăng nhập.
7. **Kiểm Destination và Recipient:** ACS hiện tại phù hợp với response và bearer subject confirmation.
8. **Kiểm AudienceRestriction:** assertion dành cho đúng SP entityID, không phải một ứng dụng khác.
9. **Kiểm InResponseTo/request correlation:** với SP-initiated, response phải khớp request đang chờ, đúng phiên và chưa xử lý; unsolicited chỉ theo policy riêng.
10. **Kiểm thời gian:** IssueInstant, Conditions NotBefore/NotOnOrAfter, SubjectConfirmationData NotOnOrAfter và clock skew trong giới hạn được phép.
11. **Chống replay:** lưu/kiểm Response ID và Assertion ID theo cơ chế phù hợp để không chấp nhận thông điệp dùng lại.
12. **Kiểm Subject và AuthnStatement:** đúng chủ thể, phương thức subject confirmation, context và mức assurance được SP yêu cầu.
13. **Mapping account tin cậy:** liên kết NameID/thuộc tính với tài khoản đúng người, đúng tenant; xử lý account chưa tồn tại theo policy.
14. **Kiểm trạng thái JML và quyền:** account còn active, quyền được phép, nguồn policy không quá hạn.
15. **Tạo session bảo vệ:** session ID mới, cookie Secure/HttpOnly/SameSite theo mô hình, thời hạn và audit; không tái sử dụng session không tin cậy.

**Chỉ cần một trong các điều kiện bắt buộc thất bại, SP phải từ chối đăng nhập và ghi sự kiện an toàn.**

### XML Signature Wrapping

Trong kiểu tấn công **XML Signature Wrapping**, attacker cố chèn một phần tử giả chứa danh tính/quyền mong muốn trong khi giữ một phần tử khác có chữ ký hợp lệ. Nếu server kiểm chữ ký ở phần tử A nhưng lấy NameID từ phần tử B chưa được bảo vệ, việc xác thực có thể bị vượt qua.

Do đó nên:

- Dùng thư viện có kiểm tra cấu trúc/ID và chính sách signature nghiêm ngặt.
- Chỉ tiêu thụ **đúng object đã được thư viện xác minh**.
- Chặn ID trùng/không hợp lệ, cấu trúc bất thường, thuật toán yếu và tham chiếu chữ ký không đúng.
- Không trộn một parser “lấy NameID” riêng với một validator chữ ký độc lập không có liên kết object.

### Chữ ký và mã hóa giải quyết hai vấn đề khác nhau

**XML digital signature** giúp kiểm **nguồn phát hành và tính toàn vẹn** của dữ liệu được ký. **XML encryption**, nếu áp dụng, nhằm giữ bí mật nội dung assertion đối với các bên không có khóa giải mã. Mã hóa **không thay thế** kiểm chữ ký; TLS cũng không thay thế chữ ký assertion khi SP dựa vào XML SAML đi qua browser.

## 10. Ví dụ backend Java: phân tách validation và account linking

Đoạn dưới đây là **pseudocode Java** mô tả thứ tự kiểm tra. Nó **không phải triển khai đầy đủ SAML** và không nên được dùng thay thư viện SAML đã được kiểm thử:

~~~java
// Pseudocode: bộ xác minh SAML chuyên dụng chịu trách nhiệm XML,
// signature, issuer, audience, recipient, time, replay và correlation.
LoginResult handleSamlAcs(
        HttpRequest request,
        ServerSideSsoTransaction transaction) {

    VerifiedSamlResult verified = samlLibrary.verifyResponse(
        request.body(),
        federationConfig.forTenant(transaction.tenantId()),
        transaction.expectedAuthnRequestId(),
        transaction.binding()
    );

    if (!verified.isValid()) {
        audit.recordSamlFailure(verified.safeErrorCode());
        throw new AuthenticationException("invalid_saml_response");
    }

    // Chỉ lấy principal/attributes từ verified object,
    // không parse lại XML theo đường khác.
    TrustedFederatedPrincipal principal = verified.principal();

    Account account = accountLinker.findByTrustedFederatedMapping(
        principal.issuer(),
        principal.subjectIdentifier(),
        transaction.tenantId()
    );

    if (account == null || !account.isActive()) {
        throw new AccessDeniedException("account_not_eligible");
    }

    if (!assurancePolicy.accepts(principal.authenticationContext())) {
        throw new StepUpRequiredException();
    }

    // RBAC/ABAC phải được kiểm riêng ở bước dùng tài nguyên.
    Session session = sessionService.createFreshSession(
        account.id(),
        principal.authenticationContext(),
        verified.authenticationTime()
    );
    audit.recordFederatedLogin(account.id(), principal.issuer());
    return LoginResult.withSession(session);
}
~~~

Những khả năng thư viện/verifier thực tế phải đảm nhiệm:

- Kiểm signature **đúng phần tử đã sử dụng** và trust key của IdP/tenant.
- Xác minh Response ID/Assertion ID không replay, expiry, ACS/recipient và SP audience.
- Với SP-initiated, liên kết response với request chờ và phiên SP; với IdP-initiated, áp policy unsolicited riêng.
- Bảo vệ XML parsing và kích thước/độ phức tạp đầu vào.
- Trả về một **verified principal** có nguồn gốc rõ; không cho ứng dụng đọc tùy tiện claim từ XML chưa tin cậy.
- Ngăn account linking khi issuer/NameID/tenant không khớp.

Nếu dùng thư viện Java như Spring Security SAML 2.0 hoặc một thư viện SAML tương thích trong hệ thống, cần kiểm **phiên bản, cấu hình validation và test tích hợp** của thư viện cụ thể. Đoạn minh họa trên **không phải API thật** của một thư viện đã nêu.

## 11. NameID, thuộc tính và account linking

Khi SP nhận assertion, nó cần xác định **đúng tài khoản nội bộ** tương ứng với chủ thể đã được IdP xác thực. Sai sót ở bước này có thể làm hai người nhập nhằng danh tính hoặc được cấp dữ liệu của nhau.

### NameID không nhất thiết là email

NameID có nhiều format: **persistent**, **transient**, email address hoặc format theo thỏa thuận. Với ứng dụng cần duy trì account xuyên suốt vòng đời, một định danh **ổn định và không dễ tái sử dụng** thường an toàn hơn email dùng làm khóa duy nhất.

| Phương án mapping | Lợi ích | Rủi ro cần kiểm soát |
| --- | --- | --- |
| **Issuer + persistent NameID + tenant** | Có thể giữ mapping ổn định khi đổi email. | Phải bảo đảm IdP duy trì định danh nhất quán và tách từng tenant. |
| **Issuer + employee/subject ID tin cậy** | Dễ liên kết HRIS/IGA và account đích. | Cần hợp đồng thuộc tính và không nhận ID do user tự khai. |
| **Email** | Tiện tích hợp SaaS đơn giản. | Email có thể đổi/tái sử dụng; dễ gộp nhầm account. |
| **Transient NameID** | Hạn chế liên kết qua phiên theo mô hình nhất định. | Không phù hợp nếu dùng đơn lẻ làm khóa account lâu dài. |

**Không tự động liên kết** một tài khoản quản trị tồn tại sẵn với assertion chỉ vì email trong attribute trùng. Cần bằng chứng liên kết từ nguồn quản lý danh tính và kiểm tra đúng issuer/tenant; trường hợp mâu thuẫn phải đưa vào **manual review**.

### Attribute contract

IdP có thể gửi các attribute như **employeeId**, **department**, **costCenter**, **groups** hoặc **role**, nếu hai bên thỏa thuận. SP phải phân biệt:

- **Thuộc tính danh tính:** hỗ trợ mapping subject.
- **Thuộc tính hiển thị:** tên, email dùng trong giao diện.
- **Thuộc tính quyết định quyền:** role/group/department chỉ nên tin nếu phát hành từ nguồn có thẩm quyền, đủ mới và được mapping đúng policy.

Không dùng mọi attribute như một quyền. Một SAML assertion có thể được ký hợp lệ nhưng chứa vai trò **đã lỗi thời** do IdP chưa đồng bộ HRIS, hoặc có nhóm rộng hơn nhu cầu ứng dụng. Các quyền nhạy cảm cần được kiểm soát ở **IGA và backend authorization**, với cơ chế cập nhật/thu hồi riêng.

## 12. Authentication assurance và AuthnContext

SAML có các cấu trúc như **AuthnStatement**, **AuthnInstant**, **SessionIndex** và **AuthnContextClassRef** để biểu diễn việc IdP đã xác thực user và ngữ cảnh xác thực. SP có thể yêu cầu một ngữ cảnh qua **RequestedAuthnContext** trong AuthnRequest nếu tích hợp hỗ trợ.

Nhưng **không có một chuỗi AuthnContextClassRef bất kỳ nào tự chứng minh đạt AAL2/AAL3**. Ý nghĩa phải đến từ hợp đồng tin cậy, chính sách IdP, cấu hình MFA và tiêu chuẩn được tổ chức áp dụng.

| Trường hợp | Điều cần làm |
| --- | --- |
| IdP xác thực bằng mật khẩu nhưng SP cần phương thức chống phishing. | SP yêu cầu xác thực phù hợp/step-up hoặc từ chối, không tự nâng assurance. |
| IdP đã có session SSO từ vài giờ trước. | SP xem thời điểm **AuthnInstant** và reauthentication policy, không coi SAML Response mới là MFA mới. |
| SP yêu cầu ForceAuthn. | Kiểm cơ chế IdP xử lý và kết quả; không tin rằng yêu cầu chắc chắn được thực thi đúng nếu thiếu kiểm chứng. |
| Attribute role hợp lệ nhưng AuthnContext không đáp ứng policy. | Giữ điều kiện xác thực riêng với authorization; không cho thao tác nhạy cảm. |
| AuthnContext từ IdP đối tác chưa có ánh xạ bảo đảm được thỏa thuận. | Không suy assurance từ tên phương thức; áp profile thận trọng hoặc yêu cầu bổ sung trust. |

**MFA enrollment**, **identity proofing (IAL)**, **authentication assurance (AAL)** và **federation assurance (FAL)** là các khía cạnh liên quan nhưng khác nhau. SP phải biết **IdP đã xác thực thế nào** và **có thể tin assertion đến đâu**, sau đó **tự kiểm quyền** khi truy cập tài nguyên.

## 13. Session của IdP khác session của SP

Một điểm dễ nhầm trong SAML SSO là **IdP session** và **SP session** không phải cùng một phiên.

- **IdP session:** phiên đăng nhập của người dùng tại IdP; có thể giúp SSO sang nhiều SP.
- **SP session:** phiên cục bộ mà ứng dụng tạo sau khi chấp nhận assertion; có cookie, thời hạn và cơ chế logout riêng.
- **SAML assertion:** thông điệp dùng để lập phiên, thường ngắn hạn và có ràng buộc; không phải token được thiết kế để SP dùng gọi API thay cho mọi request.
- **Resource authorization:** kiểm tra quyền/đối tượng khi người dùng thao tác trong SP; không nên chỉ dựa vào role snapshot lúc SAML login.

### Single Logout (SLO) không tự bảo đảm toàn bộ phiên đã kết thúc

SAML 2.0 có **Single Logout profile** và các binding liên quan, nhưng hỗ trợ thực tế khác nhau giữa SP/IdP. Một số ứng dụng chỉ đăng xuất khỏi SP hiện tại; một số hỗ trợ SLO nhưng không thể liên lạc với mọi SP hoặc thiết bị.

Do đó:

1. Kiểm tra cả IdP và SP có hỗ trợ SLO không.
2. Cấu hình endpoint/certificate/chữ ký logout message theo hợp đồng.
3. Thử logout từ SP, từ IdP và trường hợp một SP không phản hồi.
4. Không coi trình duyệt chuyển hướng về trang login là bằng chứng tất cả phiên đã thu hồi.
5. Với **Leaver hoặc compromise**, chủ động dùng cơ chế khóa account, session revoke, SCIM deprovision và kiểm chứng quyền ở từng SP.

**Chữ ký SAML hợp lệ từ trước khi Leaver không tạo ra quyền truy cập vĩnh viễn.** SP phải quản lý session và xác minh trạng thái truy cập theo SLA, không dựa duy nhất vào thời điểm assertion được phát hành.

## 14. Tích hợp SAML với Joiner–Mover–Leaver

| Sự kiện | Công việc federation | Công việc provisioning/authorization | Kiểm chứng |
| --- | --- | --- | --- |
| **Joiner** | Liên kết account IdP với SP đúng người; cấu hình SSO, MFA theo policy. | Tạo/link user bằng SCIM/JIT có kiểm soát; cấp role nền đúng ngày hiệu lực. | Không tạo trùng, không link nhầm, không cấp quyền sớm. |
| **Mover** | Giữ identity liên kết nếu còn đúng; đánh giá lại AuthnContext/assurance cho role mới. | Gỡ group/role/ACL cũ; cập nhật thuộc tính HR/IGA; cấp quyền mới sau approval và SoD. | Phiên/attribute cũ không còn mở quyền không hợp lệ. |
| **Leaver** | Disable IdP, chặn đăng nhập mới, xử lý IdP/SP session và SLO nếu hỗ trợ. | SCIM/API deprovision user/role, revoke local sessions, API keys, ACL. | Readback và thử quyền bị từ chối ở các SP trọng yếu. |
| **Rehire** | Kiểm tra mapping cũ, nguồn danh tính và authenticator còn đáng tin. | Cấp lại entitlement cho quan hệ mới, không khôi phục role cũ một cách máy móc. | Không tái sử dụng account của người khác do email trùng. |
| **Ngừng liên kết đối tác** | Gỡ trust IdP/SP, certificate và endpoint tương ứng theo kế hoạch. | Thu hồi tài khoản/nhóm liên quan và kiểm tra dữ liệu/ownership. | Không còn assertion từ IdP cũ được SP chấp nhận. |

### Joiner: SAML SSO không thay thế identity proofing

Người dùng có thể được xác thực bởi IdP nhưng SP vẫn phải xác định account nào được phép truy cập. Với nhân viên, quá trình xác minh nguồn HR, approval, ngày bắt đầu và account mapping cần xảy ra trước hoặc đồng thời với provisioning theo chính sách.

Nếu dùng **JIT provisioning**, chỉ tạo account khi IdP đáng tin và subject mapping đủ điều kiện. Không tự cấp role cao chỉ vì attribute hoặc NameID trông giống email của quản trị viên cũ.

### Mover: tránh giữ quyền trong assertion/session cũ

Một người từ Sales chuyển sang Finance có thể vẫn giữ cùng SAML NameID, nhưng role/department, ACL và quyền theo tài nguyên thay đổi. Nếu ứng dụng cache groups trong session nhiều giờ, tài khoản có thể vẫn xem dữ liệu Sales sau khi IdP đã gỡ nhóm.

Để giảm rủi ro, cần:

- SCIM/connector cập nhật role và group tại SP.
- Thực thi **authorization hiện hành** trong backend cho tài nguyên nhạy cảm.
- Rút ngắn TTL hoặc chủ động revoke/re-evaluate session khi có thay đổi quyền lớn.
- Đối soát **effective access** thay vì chỉ kiểm assertion lúc đăng nhập.
- Ngăn xung đột **Separation of Duties** khi role mới và cũ không được phép chồng lấn.

### Leaver: SAML không tự động deprovision user

Disable IdP ngăn nhiều luồng đăng nhập mới nhưng **session SP cũ**, local password, personal API token và tài khoản ngoài federation vẫn có thể tồn tại. Phải có quy trình Leaver riêng: disable/deprovision qua SCIM/API, revoke token/phiên, gỡ quyền chia sẻ, kiểm tra đường API và lưu bằng chứng cuối đường.

## 15. SAML, SCIM, OIDC và OAuth 2.0 khác nhau ra sao?

| Công nghệ | Bài toán chính | Đối tượng điển hình | Không tự thay thế |
| --- | --- | --- | --- |
| **SAML 2.0** | Federation và SSO bằng XML assertion, thường cho web enterprise. | IdP ↔ SP qua trình duyệt. | Provisioning tài khoản và quyền chi tiết. |
| **OpenID Connect (OIDC)** | Lớp xác thực danh tính xây trên OAuth 2.0, thường dùng ID token và các endpoint liên quan. | Web/mobile app, IdP/RP. | Quản trị role ứng dụng hoặc lifecycle ngoài phạm vi giao thức. |
| **OAuth 2.0** | Ủy quyền truy cập tài nguyên qua access token trong các flow phù hợp. | Client ↔ authorization server ↔ resource server. | Tự nó không phải cơ chế xác thực danh tính người dùng đầy đủ. |
| **SCIM 2.0** | Tạo/cập nhật/vô hiệu user và group giữa các hệ thống. | IAM/IGA connector ↔ SaaS. | Xác thực phiên SSO, đóng session/token. |
| **RBAC/ABAC** | Xác định hành động nào được phép trên tài nguyên. | PDP/PEP trong ứng dụng hoặc API gateway. | Chữ ký/nguồn tin cậy của assertion. |

SAML không bắt buộc dùng OAuth 2.0 để đăng nhập; hai họ giao thức có mô hình riêng. **SAML assertion có thể chứa attributes**, nhưng một assertion không phải access token OAuth 2.0 để sử dụng tùy tiện ở các API.

Khi chọn SAML hay OIDC, cần xem xét năng lực hệ thống, loại ứng dụng, bảo đảm xác thực, phiên, khả năng vận hành, metadata, quản lý khóa và yêu cầu tương thích. Dù chọn giao thức nào, **JML và authorization tại ứng dụng vẫn cần thiết**.

## 16. Certificate rotation và quản lý vòng đời federation trust

SAML federation phụ thuộc nhiều vào **khóa ký của IdP** và metadata. Nếu signing certificate sắp hết hạn, bị thay không đồng bộ hoặc bị lộ private key, hàng loạt ứng dụng có thể bị gián đoạn hoặc bị mạo danh assertion.

### Quy trình rotation có kiểm soát

1. **Inventory:** liệt kê SP nào tin IdP nào, entityID/tenant/môi trường, certificate, chủ sở hữu và cơ chế lấy metadata.
2. **Thông báo và phê duyệt:** thống nhất ngày đổi, danh sách bên liên quan, thời hạn overlap và kế hoạch rollback.
3. **Chuẩn bị khóa mới an toàn:** tạo/bảo vệ private key đúng nền tảng, công bố public verification key qua metadata đáng tin.
4. **Cập nhật SP:** nếu hỗ trợ, cho phép tin **cả khóa cũ và khóa mới** trong giai đoạn chuyển; không chấp nhận khóa không rõ nguồn.
5. **Chuyển IdP sang khóa mới:** phát hành assertions ký bằng khóa mới sau khi SP đã sẵn sàng.
6. **Kiểm thử đăng nhập:** xác minh mỗi SP nhận assertion mới đúng entityID, audience, ACS và signature; kiểm đủ môi trường.
7. **Loại khóa cũ:** gỡ trust khi hết giai đoạn chuyển theo kế hoạch, ghi log và xác minh chữ ký khóa cũ không còn được chấp nhận.
8. **Cập nhật inventory/audit:** lưu thời điểm, thay đổi cấu hình, kết quả readback, lỗi và người phê duyệt.

Một số nền tảng cho phép nhiều certificate active, số khác có giới hạn. Cần dựa trên **khả năng thực tế và metadata contract**, không mặc định hỗ trợ overlap.

### Khi nghi signing key của IdP bị lộ

Ưu tiên kiểm soát sự cố: thông báo cho các SP, vô hiệu trust với khóa bị lộ theo kế hoạch khẩn, đổi khóa, đánh giá assertion giả và phiên đã tạo, kiểm tra log và quyết định cần thu hồi session nào. **Chỉ thay certificate trên IdP chưa đủ** nếu SP vẫn tiếp tục tin public key cũ.

### Metadata drift

Những thay đổi bất ngờ về **ACS URL, IdP SSO URL, entityID, certificate, algorithm hoặc attribute contract** có thể là lỗi cấu hình hoặc dấu hiệu tấn công. Nên diff metadata và yêu cầu xác minh thay đổi trước khi đưa vào production.

## 17. An toàn đa tenant và federation với đối tác

Một SaaS có thể phục vụ nhiều tổ chức, mỗi tổ chức dùng IdP riêng. SP phải ràng buộc **IdP trust, entityID, ACS, tenant và account mapping** chặt chẽ.

Ví dụ:

- Công ty A có IdP entityID A, người dùng có email user@partner.example.
- Công ty B có IdP entityID B, cũng có thể có userName hoặc NameID trùng về mặt văn bản.
- SP không được coi hai assertion có cùng email/NameID nhưng **khác issuer/tenant** là cùng một tài khoản.

**Quy tắc:** mapping nên bao gồm định danh IdP/issuer đáng tin + subject identifier + tenant theo mô hình. Khi chọn IdP cho request (home realm discovery), cần tránh tin domain/email hoặc header do client tự khai mà không có bước xác thực mối liên kết.

Với B2B:

1. Chỉ tiếp nhận IdP đã được sponsor/quản trị viên SP phê duyệt.
2. Xác định loại người dùng, tenant, phạm vi quyền và ngày hết hạn hợp đồng.
3. Ghi hợp đồng assurance, NameID, group/role và trách nhiệm support.
4. Chỉ JIT-provision khi thuộc phạm vi cho phép và có nguồn ownership rõ.
5. Khi hết hợp đồng, thu hồi tài khoản/quyền theo lifecycle; gỡ trust nếu hợp tác kết thúc.

Không gán quyền global admin cho tài khoản đối tác chỉ vì IdP bên họ gửi attribute có giá trị “admin”; ý nghĩa và quyền của các attribute phải được SP/IGA kiểm soát độc lập.

## 18. Các lỗi bảo mật và vận hành thường gặp

| Lỗi | Hậu quả | Cách phòng tránh |
| --- | --- | --- |
| SP không kiểm SAML signature. | Assertion giả có thể đăng nhập. | Bắt buộc signature verification theo trust policy bằng thư viện đáng tin. |
| Tin chữ ký của bất kỳ certificate nằm trong response. | Attacker dùng certificate tự tạo để tự ký assertion. | Chỉ tin khóa đã cấu hình cho đúng IdP/tenant. |
| Bỏ qua audience, recipient hoặc destination. | Assertion cho SP khác có thể bị dùng sai nơi. | Kiểm ràng buộc đến đúng SP entityID/ACS. |
| Không kiểm InResponseTo cho SP-initiated. | Response injection/session confusion. | Gắn request ID với transaction và session; unsolicited chỉ theo policy. |
| Không chống replay Assertion/Response ID. | Một assertion có thể được gửi lại để tạo phiên khác. | Anti-replay cache và thời gian hợp lệ ngắn. |
| XML Signature Wrapping. | Chữ ký hợp lệ cho dữ liệu khác với subject được dùng. | Tiêu thụ đúng phần tử đã verified, validate cấu trúc và ID. |
| Tin NameID là email duy nhất toàn hệ thống. | Gộp nhầm account, đặc biệt multi-tenant/rehire. | Issuer + subject mapping ổn định + tenant. |
| Cấp role từ attribute chưa có hợp đồng. | Role escalation hoặc privilege creep. | Chỉ tin attribute có nguồn, mapping và approval đã xác minh. |
| Tin AuthnContext tên “MFA” là AAL cao. | Bypass step-up cho giao dịch nhạy cảm. | Assurance mapping được duyệt, kiểm thời điểm xác thực. |
| Metadata/ACS tự cập nhật không xác minh. | Gửi assertion tới đích sai hoặc tin khóa giả. | Change control và xác thực nguồn metadata. |
| Không có kế hoạch rotation. | Đăng nhập gián đoạn khi certificate thay/hết hạn. | Inventory, overlap nếu hỗ trợ, cảnh báo và test. |
| Nghĩ SLO chắc chắn đăng xuất mọi SP. | Phiên SaaS cũ còn hoạt động khi Leaver. | Session revoke/SCIM deprovision và kiểm chứng cuối đường. |
| Tin SAML SSO là provisioning. | User/role cục bộ không được thu hồi. | SCIM/API và JML reconciliation riêng. |
| Chỉ ẩn menu UI sau khi đổi role. | API backend vẫn cho truy cập tài nguyên. | RBAC/ABAC tại PEP, kiểm quyền theo object. |
| Không test link account hiện có. | User mới vô tình chiếm tài khoản của người khác. | Mapping đáng tin và manual review khi mâu thuẫn. |

## 19. Audit, giám sát và chỉ số vận hành

SAML federation cần audit ở **IdP**, **SP**, **IGA/SCIM** và điểm thực thi quyền. Log phải có đủ correlation để điều tra một sự kiện từ nguồn nhân sự đến session và truy cập ứng dụng.

| Loại sự kiện | Metadata hữu ích | Câu hỏi cần trả lời |
| --- | --- | --- |
| Trust configuration | IdP/SP entityID, environment, metadata version, certificate reference, owner. | SP đang tin IdP và khóa nào? |
| AuthnRequest | Request ID, SP issuer, ACS, binding, thời điểm. | Ai khởi tạo SSO và tới đâu? |
| SAML validation | Response/Assertion ID tham chiếu, issuer, audience, kết quả từng kiểm tra, error code. | Vì sao response được chấp nhận/từ chối? |
| User mapping | Stable subject ref, tenant, account ID SP, nguồn linking. | Assertion thuộc đúng user/account nào? |
| Assurance | AuthnInstant, context đã được trust, yêu cầu step-up, kết quả. | Phiên có đủ bảo đảm cho hành động không? |
| Session lifecycle | SP session ref, login/logout/revoke time, trạng thái. | Leaver còn phiên nào ở SP không? |
| Provisioning | SCIM User/Group ID, role, effectiveAt, readback và kết quả. | Quyền thực tế của user có khớp JML không? |
| Metadata/rotation | Khóa cũ/mới, thời gian đổi, người phê duyệt, test result. | Có thể phát hiện lỗi hoặc trust không mong muốn không? |

**Không lưu SAMLResponse nguyên bản chứa PII, session cookie, private key, mật khẩu, token thực hoặc secret vào log thông thường.** Chỉ lưu metadata và mã tham chiếu cần thiết theo chính sách bảo vệ dữ liệu; phân quyền truy cập log và retention phù hợp.

Chỉ số:

- **SAML login success/failure by IdP–SP:** phân biệt lỗi signature, audience, clock, NameID, metadata và session.
- **Certificate expiration horizon:** số ngày còn lại trước khi signing certificate cần thay, theo từng integration.
- **Federation drift:** khác biệt metadata, ACS, key, attribute contract so với cấu hình được phê duyệt.
- **Unmapped/duplicate identity rate:** số assertion không map được hoặc có mapping mâu thuẫn.
- **Assurance/step-up compliance:** tỷ lệ thao tác cần mức xác thực cao có context phù hợp.
- **Provisioning drift:** group/role tại SP khác desired state của IAM/IGA.
- **Residual SP session exposure:** cửa sổ phiên SP còn truy cập được sau Leaver/revoke.
- **Partner trust inventory coverage:** tỷ lệ tích hợp có owner, expiry và hồ sơ kiểm thử.

Không dùng **tỷ lệ SSO login thành công** làm chỉ số duy nhất cho bảo mật: một triển khai chấp nhận mọi assertion cũng có thể đạt login success 100% nhưng hoàn toàn không an toàn.

## 20. Ma trận kiểm thử SAML federation

Các test phải thực hiện **trong môi trường được phép** với assertion/identity thử nghiệm; không dùng tài khoản thật của người khác hoặc dữ liệu nhạy cảm để thử.

| ID | Tình huống | Kết quả kỳ vọng |
| --- | --- | --- |
| S01 | Response hợp lệ từ IdP đáng tin, đúng ACS/audience, request đang chờ. | SP xác minh và lập session cho đúng account được phép. |
| S02 | Response thiếu chữ ký bắt buộc theo trust policy. | Từ chối, không tạo session. |
| S03 | Response ký bằng khóa không thuộc IdP đã cấu hình. | Từ chối dù chữ ký tự nhất quán. |
| S04 | Assertion bị thay đổi NameID sau khi ký. | Signature validation thất bại. |
| S05 | XML có signed assertion hợp lệ nhưng chèn assertion chưa ký. | Không dùng dữ liệu chưa ký; chặn wrapping/ambiguity. |
| S06 | AudienceRestriction là entityID của ứng dụng khác. | Từ chối do sai audience. |
| S07 | Destination/SubjectConfirmationData Recipient không khớp ACS. | Từ chối. |
| S08 | SP-initiated response có InResponseTo sai/không có request tương ứng. | Từ chối theo policy SP-initiated. |
| S09 | IdP-initiated response đến SP chỉ cho phép SP-initiated. | Từ chối unsolicited response. |
| S10 | Assertion đã quá hạn hoặc chưa đến NotBefore. | Từ chối ngoài clock skew được phê duyệt. |
| S11 | Dùng lại cùng Assertion/Response ID trong cửa sổ hiệu lực. | Anti-replay chặn request lặp. |
| S12 | RelayState cố chuyển người dùng tới domain lạ. | Không redirect ngoài allowlist; kiểm state binding. |
| S13 | NameID/email trùng nhưng issuer hoặc tenant khác. | Không gộp account; mapping đúng và/hoặc manual review. |
| S14 | User account disabled do Leaver nhưng assertion còn hợp lệ. | Không mở session trái chính sách. |
| S15 | User chuyển role, assertion/session cũ chứa group Sales. | API không còn cho truy cập tài nguyên Sales sau mốc revoke theo SLA. |
| S16 | SAML SSO thành công nhưng SP chưa có account. | JIT chỉ khi được phép; nếu không, chặn và hướng dẫn provisioning. |
| S17 | Request yêu cầu phishing-resistant context nhưng IdP trả mức thấp hơn. | Step-up hoặc từ chối theo hợp đồng assurance. |
| S18 | IdP thay signing certificate theo kế hoạch. | Các SP chấp nhận khóa mới và loại khóa cũ đúng thời điểm. |
| S19 | IdP signing key bị lộ, khóa cũ đã bị gỡ trust. | Assertion mới ký bằng khóa cũ bị từ chối. |
| S20 | Người dùng logout IdP nhưng SP local session còn active. | Phát hiện giới hạn SLO; xử lý session theo policy. |
| S21 | SCIM disable thành công nhưng local API key vẫn dùng được. | Báo deprovision chưa hoàn tất; revoke key và verify. |
| S22 | Parser nhận XML có entity expansion/XXE hoặc kích thước bất thường. | Từ chối an toàn, không truy cập dữ liệu cục bộ/DoS. |

### Cần kiểm tra cả positive control

Nếu một response thử nghiệm bị từ chối do SP đang downtime hoặc do cấu hình test sai, đó không phải bằng chứng kiểm soát chữ ký hoạt động. Hãy có **luồng SAML hợp lệ làm positive control**, sau đó thay đổi từng thuộc tính để xác nhận nguyên nhân từ chối là do validator chứ không phải lỗi môi trường.

## 21. Tình huống thực hành: kết nối Finance SaaS bằng SAML

### Bối cảnh

Một doanh nghiệp sử dụng IdP tập trung, dự kiến kết nối ứng dụng **Finance SaaS**. Nhân viên Finance cần đăng nhập SSO với MFA, chỉ xem hóa đơn thuộc tenant của mình; người có chức năng phê duyệt phải đạt assurance cao và có quyền được duyệt. Khi nhân viên chuyển bộ phận hoặc nghỉ việc, quyền ở SaaS cần được thu hồi đúng mốc.

### Bước 1 – Thiết lập hợp đồng federation

Nhóm IAM và nhà cung cấp xác nhận IdP/SP entityID, ACS URL, SSO URL, metadata signing certificate, yêu cầu chữ ký, NameID ổn định, attribute tối thiểu và các binding hỗ trợ. Cấu hình staging/prod riêng. Kế hoạch certificate rotation và incident response được ghi vào inventory.

### Bước 2 – Liên kết danh tính và provisioning

IAM chọn định danh ổn định **person-4821** liên kết nguồn HR, IdP và tài khoản Finance SaaS. Connector SCIM tạo user, đồng bộ nhóm được phê duyệt và đọc lại mapping. Không sử dụng email làm chứng cứ duy nhất để nối vào một local account có đặc quyền tồn tại trước đó.

### Bước 3 – Kiểm chứng luồng SAML

Người dùng vào Finance SaaS, nhận AuthnRequest, đăng nhập IdP bằng MFA. SaaS kiểm Response/Assertion bằng thư viện SAML: trust signature, issuer, audience, recipient, InResponseTo, thời hạn và replay. Sau khi map đúng subject, SaaS tạo local session.

### Bước 4 – Kiểm quyền nghiệp vụ

SaaS chỉ cho **InvoiceReader** đọc hóa đơn được duyệt thuộc đúng tenant. Với hành động duyệt thanh toán, kiểm role **PaymentApprover**, SoD và AuthnContext/độ mới theo chính sách. Một assertion hợp lệ nhưng không có role phù hợp **không được phép** vượt qua kiểm soát này.

### Bước 5 – Mover sang phòng khác

HR gửi Mover; IGA gỡ nhóm Finance và phân quyền ứng dụng. SaaS không chỉ nhận group thay đổi mà phải kiểm tra effective permission/session còn lại. Một phiên lập trước thời điểm chuyển không được tiếp tục cho phép truy cập hóa đơn sau SLA thu hồi của hệ thống.

### Bước 6 – Leaver và xác minh cuối đường

HR gửi Leaver; IdP disable account, revoke phiên phù hợp; SCIM khóa Finance SaaS user, gỡ role/ACL và xử lý local sessions/API keys. Nhóm IAM readback và thử quyền truy cập có kiểm soát. **Không đóng hồ sơ chỉ vì SAML SSO không cho đăng nhập mới** nếu API key hoặc phiên SaaS cũ vẫn hoạt động.

### Bước 7 – Kết thúc tích hợp

Nếu Finance SaaS bị thay thế, tổ chức thu hồi quyền và tài khoản ứng dụng, xử lý dữ liệu/ownership theo retention, gỡ trust IdP/SP và certificate theo kế hoạch, xác minh assertion từ liên kết cũ không còn được chấp nhận.

## 22. Câu hỏi tự kiểm tra

**Câu 1.** SAML federation có tự tạo và xóa account ở mọi ứng dụng khi nhân viên Joiner/Leaver không?

**Trả lời:** Không. SAML chủ yếu phục vụ federation/SSO. Tạo/cập nhật/disable account thường cần SCIM/API, JIT theo policy hoặc connector khác, cùng bước xác minh deprovisioning.

**Câu 2.** SP nhận assertion có XML signature hợp lệ với certificate đi kèm trong response. Có đủ để tin không?

**Trả lời:** Chưa. SP phải kiểm chữ ký bằng khóa đã **được trust cho đúng IdP/tenant**, đồng thời kiểm issuer, audience, recipient, thời gian, replay và các ràng buộc khác. Một khóa tự cung cấp không phải trust anchor.

**Câu 3.** Vì sao InResponseTo đặc biệt quan trọng với SP-initiated SSO?

**Trả lời:** Nó giúp liên kết SAML Response với AuthnRequest đang chờ do SP phát hành, tránh chấp nhận response không tương ứng hoặc nhầm phiên. IdP-initiated cần chính sách unsolicited riêng vì không có request chờ tương tự.

**Câu 4.** Một assertion dành cho SP A có thể dùng đăng nhập SP B không?

**Trả lời:** Không được nếu SP kiểm đúng **AudienceRestriction**, recipient và các ràng buộc khác. Assertion được phát cho SP nào chỉ được chấp nhận theo đúng phạm vi tin cậy đã định.

**Câu 5.** Vì sao không nên dùng email trong NameID làm khóa duy nhất vĩnh viễn?

**Trả lời:** Email có thể thay đổi, tái sử dụng hoặc trùng giữa tenants. Nên dùng mapping có issuer và subject identifier ổn định, kiểm liên kết với hồ sơ có thẩm quyền.

**Câu 6.** IdP đã khóa tài khoản Leaver. Có thể kết luận ngay local session của mọi SP đã hết hiệu lực?

**Trả lời:** Không. SP có thể giữ session và credential riêng. Cần cơ chế session revocation, SCIM deprovisioning, xử lý API key/ACL và xác minh quyền tại từng đích.

**Câu 7.** Vì sao một SAML Response được ký đúng vẫn không đủ để cho phép người dùng xuất dữ liệu khách hàng?

**Trả lời:** Chữ ký xác nhận nguồn và tính toàn vẹn assertion trong phạm vi được ký. Quyền **export** còn phải qua authorization tại SP dựa trên role, tenant, tài nguyên, chính sách và trạng thái nhân sự hiện hành.

**Câu 8.** Chỉ cần thay signing certificate ở IdP đã chặn hoàn toàn key cũ bị lộ chưa?

**Trả lời:** Chưa. Các SP có thể vẫn tin public key cũ. Phải cập nhật hoặc thu hồi trust ở từng SP, xem xét session/assertion có nguy cơ bị giả và lưu kết quả kiểm thử.

---

**Ghi nhớ:** SAML federation giúp **IdP phát hành bằng chứng xác thực để SP thực hiện SSO**, nhưng sự tin cậy chỉ hình thành khi SP kiểm đúng **signature, issuer, audience, ACS/recipient, correlation, thời hạn, replay và account mapping**. SAML không thay thế **SCIM provisioning, RBAC/ABAC, quản lý local session và deprovisioning**. Trong toàn bộ vòng đời **Joiner–Mover–Leaver**, quản trị federation phải đi cùng quản trị danh tính, quyền, certificate và bằng chứng kiểm toán để tránh đăng nhập nhầm, đặc quyền dư thừa và quyền truy cập tồn dư.
