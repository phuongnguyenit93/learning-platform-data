# LogoutRequest, LogoutResponse và mối liên hệ giữa các thông điệp trong SAML 2.0

**Module:** Spring Security – federation  
**Chủ đề cha:** Đăng xuất SAML2  
**Phạm vi:** SAML 2.0 Single Logout (SLO), ứng dụng Spring Boot 3.x, Spring Security 6.x, Java 17+.

## 1. Tại sao cần SAML Single Logout?

**Single Sign-On (SSO)** cho phép một người đăng nhập ở Identity Provider (IdP) và truy cập nhiều Service Provider (SP) mà không nhập lại thông tin xác thực. Nhưng mỗi SP có thể duy trì **HttpSession/SecurityContext riêng**; đăng xuất khỏi một ứng dụng không tự động kết thúc mọi phiên còn lại.

**Single Logout (SLO)** là quy trình phối hợp giữa bên phát hành danh tính (**IdP**, trong Spring Security thường gọi *Asserting Party – AP*) và ứng dụng sử dụng danh tính (**SP/Relying Party – RP**) để yêu cầu kết thúc phiên SAML.

SLO xoay quanh **hai thông điệp khác nhau**:

- **samlp:LogoutRequest:** bên khởi tạo yêu cầu bên kia kết thúc phiên thuộc một danh tính SAML; có thể kèm **SessionIndex** để thu hẹp phiên cần đăng xuất.
- **samlp:LogoutResponse:** bên nhận trả kết quả xử lý LogoutRequest, có **Status** và, với response trả lời yêu cầu, **InResponseTo** trỏ lại **ID của LogoutRequest**.

SLO có hai hướng khởi tạo:

1. **SP/RP-initiated SLO:** người dùng nhấn đăng xuất tại ứng dụng; SP gửi LogoutRequest tới IdP; IdP có thể yêu cầu các SP khác đăng xuất, rồi trả LogoutResponse cho SP ban đầu.
2. **IdP/AP-initiated SLO:** người dùng đăng xuất tại IdP hoặc một SP khác làm IdP điều phối; IdP gửi LogoutRequest tới SP; SP kiểm tra request, xóa phiên liên quan và trả LogoutResponse cho IdP.

**Quy tắc thiết yếu:** SAML LogoutRequest/LogoutResponse **không giống** AuthnRequest/SAML login Response. Một thông điệp đăng xuất không xác thực người dùng để tạo phiên mới. Chữ ký hợp lệ, Issuer, Destination, correlation, NameID/SessionIndex và Status phải được đánh giá theo đúng vai trò mỗi thông điệp.

## 2. Phân biệt LogoutRequest, LogoutResponse và Response của SAML Login

| Thông điệp | Ai phát hành? | Ý nghĩa | Trường kết nối |
| --- | --- | --- | --- |
| **AuthnRequest** | SP khi bắt đầu SSO | Yêu cầu IdP xác thực người dùng | **AuthnRequest.ID** |
| **samlp:Response** chứa Assertion | IdP khi hoàn tất SSO | Chứng cứ về xác thực | **Response.InResponseTo = AuthnRequest.ID** ở SP-initiated login |
| **samlp:LogoutRequest** | SP **hoặc** IdP | Yêu cầu kết thúc phiên đăng nhập SAML | **LogoutRequest.ID**, NameID, SessionIndex |
| **samlp:LogoutResponse** | Bên nhận LogoutRequest | Thông báo kết quả xử lý yêu cầu đăng xuất | **LogoutResponse.InResponseTo = LogoutRequest.ID**; Status |

Điểm dễ nhầm: ở HTTP-POST binding, **form field** có thể là **SAMLRequest** hoặc **SAMLResponse**. Form field **SAMLResponse** chứa XML **LogoutResponse** khi gọi SLO endpoint, nhưng có thể chứa XML **Response** xác thực khi gọi ACS endpoint. Cùng tên trường HTTP không làm hai thông điệp có cùng ngữ nghĩa.

Một giao dịch điển hình:

~~~text
LogoutRequest.ID                 = _logout_req_123
LogoutResponse.ID                = _logout_resp_456
LogoutResponse.InResponseTo      = _logout_req_123
LogoutResponse.Status.StatusCode = Success
~~~

**Không so LogoutResponse.ID với LogoutRequest.ID.** LogoutResponse có ID độc lập; **InResponseTo** mới là tham chiếu đến request đã phát ra. **Status=Success** cũng không được kết luận chỉ từ việc InResponseTo khớp: chữ ký, Issuer, Destination và quy tắc chính sách vẫn cần đạt.

## 3. Cấu trúc LogoutRequest: những thông tin bên nhận cần xác minh

Mẫu **XML để đọc cấu trúc**, lược bỏ chữ ký, không phải request hoàn chỉnh dùng thực tế:

~~~xml
<samlp:LogoutRequest
    xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    ID="_logout_req_123"
    Version="2.0"
    IssueInstant="2026-11-07T08:00:00Z"
    Destination="https://idp.example.org/saml/logout"
    Reason="urn:oasis:names:tc:SAML:2.0:logout:user">
  <saml:Issuer>https://portal.example.org/saml/sp</saml:Issuer>
  <saml:NameID
      Format="urn:oasis:names:tc:SAML:2.0:nameid-format:persistent"
  >employee-847</saml:NameID>
  <samlp:SessionIndex>session-index-abc</samlp:SessionIndex>
</samlp:LogoutRequest>
~~~

### 3.1. Các trường quan trọng

| Trường | Ý nghĩa | Quy tắc xử lý |
| --- | --- | --- |
| **ID** | Định danh duy nhất của LogoutRequest | Dùng để đối chiếu **LogoutResponse.InResponseTo**, chống dùng lại theo policy |
| **Version** | Phiên bản giao thức, thường **2.0** | Không chấp nhận version không hỗ trợ |
| **IssueInstant** | Thời điểm phát hành | Kiểm tra tính hợp lý, độ lệch đồng hồ và cửa sổ chấp nhận theo chính sách |
| **Destination** | Endpoint dự định nhận thông điệp | Phải khớp SLO endpoint đáng tin và binding được cấu hình |
| **Issuer** | EntityID của bên yêu cầu logout | Phải là đối tác SAML được phê duyệt, không lấy tên miền tự khai từ XML làm trust |
| **NameID** | Chủ thể SAML cần logout | Phải khớp danh tính/phiên theo yêu cầu của quan hệ federation |
| **SessionIndex** | Chỉ số phiên SAML, có thể có nhiều; **không bắt buộc trong schema** | Giúp nhận diện phiên cần kết thúc; không phải JSESSIONID |
| **Reason** | Lý do yêu cầu đăng xuất | Có tính diễn giải, không thay xác minh/trust |
| **NotOnOrAfter** | Thời điểm sau đó request không còn được chấp nhận nếu được dùng | Không coi là session timeout của trình duyệt |

LogoutRequest theo SAML Core chứa một trong các định danh chủ thể **BaseID, NameID hoặc EncryptedID** và **có thể** chứa nhiều **SessionIndex**. XML mẫu dùng NameID phổ biến để dễ đọc. Một số IdP hỗ trợ/đòi hỏi SessionIndex, một số không; kiểm tra contract của từng IdP.

**SessionIndex ≠ HttpSession ID.** SessionIndex bắt nguồn từ **AuthnStatement/phiên SAML của IdP**, còn **JSESSIONID/SESSION** là định danh phiên HTTP do SP quản lý. Không gửi JSESSIONID vào phần SessionIndex, không suy đoán NameID= email.

### 3.2. Tính toàn vẹn và nguồn gốc

Một request có XML hợp lệ nhưng không được ký/xác minh theo profile và binding đã thống nhất **không đủ an toàn để hủy phiên**. Khi IdP gửi LogoutRequest tới SP, SP cần xác minh chữ ký theo **verification certificate của IdP đã được tin cậy**; khi SP gửi request tới IdP, dùng **SP signing private key** theo metadata/chính sách đã đăng ký.

**Bảo vệ phiên:** nếu chấp nhận LogoutRequest từ bất kỳ nguồn nào chỉ dựa vào NameID, attacker có thể cố gắng logout người dùng khác (logout CSRF/DoS). Việc xác minh signature + Issuer + đối tượng/phiên đích + thời gian và correlation cần được áp dụng độc lập.

## 4. Cấu trúc LogoutResponse: phản hồi cho request nào, kết quả ra sao?

Ví dụ **LogoutResponse** IdP gửi về SP sau khi SP phát LogoutRequest ở mục 3:

~~~xml
<samlp:LogoutResponse
    xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    ID="_logout_resp_456"
    Version="2.0"
    IssueInstant="2026-11-07T08:01:00Z"
    Destination="https://portal.example.org/logout/saml2/slo"
    InResponseTo="_logout_req_123">
  <saml:Issuer>https://idp.example.org/saml</saml:Issuer>
  <samlp:Status>
    <samlp:StatusCode
        Value="urn:oasis:names:tc:SAML:2.0:status:Success"/>
  </samlp:Status>
</samlp:LogoutResponse>
~~~

**Đây là XML minh họa, chưa có chữ ký**; không được dùng làm fixture “đăng xuất thành công” ở production.

### 4.1. Điều kiện tương quan

Đối với giao dịch đã phát **LogoutRequest.ID = _logout_req_123**, bên nhận LogoutResponse cần:

1. Tìm **pending LogoutRequest** đã lưu cho giao dịch và đúng đối tác.
2. So sánh **LogoutResponse.InResponseTo = LogoutRequest.ID**.
3. Kiểm tra Issuer trả lời là IdP/SP tương ứng, Destination là SLO response endpoint của mình và chữ ký hợp lệ.
4. Kiểm tra thời gian, binding, Status và replay/single-use.
5. Kết thúc trạng thái chờ theo policy và thông báo kết quả thực tế cho người dùng/giám sát.

**InResponseTo không tự chứng minh logout đã xong.** Nó chỉ trả lời “phản hồi này thuộc yêu cầu nào?”. Trạng thái **Status** và điều kiện xác minh khác mới quyết định thông điệp có thể được chấp nhận như kết quả giao dịch.

### 4.2. Các trạng thái SAML quan trọng

- **urn:oasis:names:tc:SAML:2.0:status:Success:** bên phản hồi báo thành công theo ngữ nghĩa của họ.
- **urn:oasis:names:tc:SAML:2.0:status:Responder:** lỗi ở phía xử lý response, có thể kèm StatusCode cấp dưới/StatusMessage.
- **urn:oasis:names:tc:SAML:2.0:status:Requester:** yêu cầu không được chấp nhận do vấn đề từ bên gửi.
- **urn:oasis:names:tc:SAML:2.0:status:PartialLogout:** chỉ một phần phiên/đối tác được logout khi điều phối toàn cục; **không coi là toàn bộ hệ thống đã logout hoàn toàn**.
- **StatusMessage:** tùy IdP có thể mô tả lỗi; không ghi thông điệp nhạy cảm ra giao diện công khai.

Trong hệ thống gồm nhiều SP, ngay cả khi IdP trả **Success**, ứng dụng vẫn cần hiểu phạm vi mà đối tác cam kết. SLO là quá trình phối hợp qua trình duyệt/mạng, không phải transaction ACID giữa các phiên của mọi SP; network interruption, tab đóng, IdP không hỗ trợ một binding hoặc SP thứ ba không phản hồi có thể khiến kết quả không hoàn toàn.

## 5. Luồng RP/SP-initiated SLO: trình tự A → B → A

Khi người dùng đăng xuất khỏi SP (ví dụ ứng dụng portal):

~~~text
Browser                 Spring Security SP                     SAML IdP
   |                            |                                 |
   | POST /logout (+ CSRF)      |                                 |
   |--------------------------->| LogoutHandler dọn phiên SP      |
   |                            | Saml2RelyingPartyInitiated...   |
   |                            | tạo LogoutRequest ID=_L1       |
   |                            | ký và lưu pending request       |
   |<---------------------------| redirect/POST tới IdP --------->|
   |                            |                                 | Kiểm tra
   |                            |                                 | NameID/SessionIndex
   |                            |                                 | Logout IdP và SP khác
   |                            |<--------------------------------|
   | POST /logout/saml2/slo     |                                 |
   | SAMLResponse:              |                                 |
   | LogoutResponse             |                                 |
   | InResponseTo=_L1           |                                 |
   |--------------------------->| Saml2LogoutResponseFilter       |
   |                            | verify + correlation + status   |
   |<---------------------------| landing page nếu hợp lệ        |
~~~

### Bước 1 – Người dùng yêu cầu logout tại SP

Thông thường browser gửi **POST /logout** với CSRF token hợp lệ. Spring Security gọi **LogoutHandler** để hủy/giải phóng trạng thái ứng dụng: **SecurityContext**, session, các thông tin local liên quan. Sau đó **Saml2RelyingPartyInitiatedLogoutSuccessHandler** khởi tạo SLO khi cấu hình **saml2Logout()** đúng.

**Không có nghĩa SP phải chờ IdP trả lời mới được xóa phiên local.** Spring Security có thể invalidation local session **trước** khi nhận phản hồi SLO. Nếu IdP bị mất kết nối sau đó, người dùng thường đã logout khỏi SP nhưng vẫn có thể còn phiên IdP hoặc SP khác.

### Bước 2 – SP tạo và lưu LogoutRequest

**Saml2LogoutRequestResolver** xây XML, dùng registration liên quan tới **Saml2AuthenticatedPrincipal**, SP entityID, IdP SingleLogoutService endpoint và SP signing credentials. SP lưu thông tin request đang chờ thông qua **Saml2LogoutRequestRepository**; từ đó có thể xác minh **RelayState** và **LogoutResponse.InResponseTo** sau khi IdP phản hồi.

**Điểm khó trong implementation:** dù session đăng nhập local có thể đã bị invalidate, SLO framework cần bảo tồn thông tin correlation theo repository/session được quản lý phù hợp để xác minh phản hồi. Không tự xóa pending request hoặc thay logout success handler theo cách khiến LogoutResponse không còn gì để đối chiếu.

### Bước 3 – IdP xử lý và điều phối

IdP xác minh request đến từ đúng SP được phê duyệt, kiểm tra NameID/SessionIndex và kết thúc phiên theo policy. Nếu IdP biết có các SP khác trong cùng SSO session, nó có thể gửi **LogoutRequest mới** tới từng SP.

**Các LogoutRequest trung gian có ID riêng**, không phải dùng lại LogoutRequest.ID của SP khởi xướng. Các SP khác trả **LogoutResponse** cho IdP với **InResponseTo** trỏ tới request IdP dành cho chính SP đó.

### Bước 4 – IdP trả LogoutResponse cho SP khởi xướng

Cuối cùng, nếu browser/IdP hoàn tất flow và trả response:

- **Saml2LogoutResponseFilter** nhận **SAMLResponse** tại SLO endpoint.
- Filter deserializes/verifies **LogoutResponse** bằng **Saml2LogoutResponseValidator**.
- Correlation và Status được xử lý; nếu hợp lệ, có thể redirect đến trang kết thúc đăng xuất, thường **/login?logout** theo cấu hình.
- Nếu response không hợp lệ, Spring Security thường trả lỗi (ví dụ **HTTP 400**) thay vì tuyên bố toàn cục logout thành công.

**Browser có thể không trở lại SP.** Ví dụ người dùng đóng tab tại IdP, IdP giữ một interstitial page, bên thứ ba timeout, hoặc binding không tương thích. Ứng dụng phải có UX phân biệt **“đã kết thúc phiên tại ứng dụng”** với **“đã xác nhận logout ở toàn hệ sinh thái”**.

## 6. Luồng IdP/AP-initiated SLO: B → A → B

Khi người dùng đăng xuất tại IdP hoặc IdP nhận yêu cầu logout từ một SP khác:

~~~text
IdP/AP                         Browser                       Spring SP
  |                                |                              |
  | Tạo LogoutRequest ID=_I9      |                              |
  | Issuer=IdP, NameID, Index      |                              |
  |--------------------------------> POST /logout/saml2/slo ------>|
  |                                |                         Saml2LogoutRequestFilter
  |                                |                         validate ký/issuer/target
  |                                |                         LogoutHandler dọn phiên
  |<-------------------------------- response gửi qua browser <----|
  |  LogoutResponse               |                              |
  |  InResponseTo=_I9             |                              |
  |  Status=Success/Error          |                              |
~~~

### Điều gì diễn ra tại SP?

1. SP nhận **SAMLRequest** chứa **samlp:LogoutRequest** tại endpoint SLO.
2. **Saml2LogoutRequestFilter** phân tích và dùng **Saml2LogoutRequestValidator** kiểm tra chữ ký, Issuer, Destination, danh tính/phiên và các điều kiện phù hợp.
3. Nếu hợp lệ, các logout handlers kết thúc local session và SecurityContext tương ứng.
4. **Saml2LogoutResponseResolver** tạo **LogoutResponse mới** do SP phát hành.
5. SP trả qua binding đã cấu hình tới **SingleLogoutService response location** của IdP; response thường có **InResponseTo = LogoutRequest.ID** của IdP và Status thích hợp.

**Không khởi tạo một LogoutRequest thứ hai để trả lời trực tiếp một LogoutRequest.** Thông điệp trả lời chuẩn là **LogoutResponse**, không phải AuthnRequest và cũng không phải SAML assertion.

### Điều gì khác với SP-initiated?

| Tiêu chí | SP/RP-initiated | IdP/AP-initiated |
| --- | --- | --- |
| Nơi người dùng chọn logout đầu tiên | SP | IdP hoặc SP khác |
| Bên tạo LogoutRequest đầu tiên của giao dịch SP–IdP | SP | IdP |
| Bên phát LogoutResponse ở cặp giao dịch đó | IdP | SP |
| Filter xử lý **message đầu vào tại SP** | Saml2LogoutResponseFilter | Saml2LogoutRequestFilter |
| Chỗ lưu pending request SP phát | Saml2LogoutRequestRepository | Không có pending SP-request cho request mới do IdP gửi |
| Mối liên hệ InResponseTo | IdP response → SP request.ID | SP response → IdP request.ID |
| Local logout tại SP | Thường trước khi đi IdP | Sau khi kiểm tra request IdP hợp lệ |
| Khả năng SP điều khiển trang cuối | Có nếu IdP trả browser về | Browser do IdP dẫn hướng sau khi SP trả response |

**Không xác nhận mọi LogoutRequest IdP gửi đều đúng user:** phải ràng buộc danh tính/SessionIndex với phiên mà SP có thẩm quyền hủy và xác minh chữ ký/Issuer từ đúng IdP. Không duyệt request chỉ vì XML chứa NameID có vẻ giống user.

## 7. Mối liên hệ giữa các thông điệp khi có nhiều SP

Ví dụ một SSO session của người dùng đang mở ba ứng dụng: **portal-SP**, **reports-SP** và **billing-SP**.

~~~text
portal-SP                         IdP                        reports-SP
   |                               |                               |
   | LogoutRequest ID=_P1          |                               |
   |------------------------------>|                               |
   |                               | LogoutRequest ID=_I1          |
   |                               |------------------------------>|
   |                               |<------------------------------|
   |                               | LogoutResponse                |
   |                               | InResponseTo=_I1              |
   |                               |                               |
   |<------------------------------|                               |
   | LogoutResponse                |                               |
   | InResponseTo=_P1              |                               |
~~~

Một nhánh tương tự có thể diễn ra với billing-SP, với request ID khác, ví dụ **_I2**.

**Không có một InResponseTo chung cho mọi response trong toàn bộ cascade.** Mỗi LogoutResponse tham chiếu **request trực tiếp mà nó đang trả lời**:

- reports-SP trả IdP: **InResponseTo=_I1**.
- billing-SP trả IdP: **InResponseTo=_I2**.
- IdP trả portal-SP: **InResponseTo=_P1**.

Đây là lý do một hệ thống audit nhiều SP nên ghi **request ID + issuer/recipient + correlation state**, không chỉ một text chung như “logout request completed”.

### PartialLogout và lỗi từng SP

Nếu reports-SP logout thành công nhưng billing-SP offline, IdP có thể báo trạng thái lỗi hoặc **PartialLogout** theo implementation. SP khởi xướng cần diễn giải trạng thái trả về đúng: phiên tại portal có thể đã bị xóa, nhưng không có bằng chứng mọi phiên billing/report cũng đã kết thúc.

**LogoutResponse=Success của một nhánh** chỉ nói kết quả nhánh đó theo bên trả lời; nó không phải biên nhận vĩnh viễn cho toàn bộ các SP khi môi trường có giới hạn giao thức/network.

## 8. NameID và SessionIndex: xác định phiên nào cần xóa

### NameID

SAML LogoutRequest có thể chỉ định danh tính cần kết thúc bằng **NameID** (hoặc BaseID/EncryptedID). NameID có format/khuôn dạng và đôi khi NameQualifier/SPNameQualifier. Không tự chuyển NameID thành email rồi tìm session; nhiều IdP dùng NameID là chuỗi opaque/persistent hoặc transient.

**Đừng dựa duy nhất vào NameID** để hủy mọi phiên ứng dụng không liên quan, nhất là multi-tenant hoặc nhiều IdP. Cần issuer/trust đã xác minh và ranh giới phiên đáng tin.

### SessionIndex

IdP có thể gắn **SessionIndex** trong **AuthnStatement** khi người dùng đăng nhập. Khi logout, SessionIndex cho biết một phiên SAML cụ thể cần kết thúc. Một user có thể có nhiều session/thiết bị, nên SessionIndex giúp giảm phạm vi ảnh hưởng.

- **SessionIndex** là một định danh thuộc ngữ cảnh SAML/IdP; **không phải** JSESSIONID, Redis key hay OAuth session ID.
- LogoutRequest có thể **không chứa SessionIndex**, hoặc chứa nhiều giá trị; chính sách thực tế phụ thuộc IdP và profile.
- Nếu SP muốn hủy một tập phiên theo SessionIndex, phải có cơ chế ánh xạ được quản trị từ **(issuer, NameID/subject, SessionIndex)** đến local sessions.
- Một SP chỉ lưu một HttpSession hiện hành có thể không đủ để triển khai remote global logout cho mọi thiết bị nếu không có session registry/store.
- Kết quả xử lý phụ thuộc việc các phiên thật còn hoạt động hay đã hết hạn; ứng dụng nên trả status theo hành vi/contract, không giả vờ tìm được phiên khi không có.

### Các thời hạn khác nhau

- **IssueInstant** và **NotOnOrAfter của LogoutRequest** có vai trò kiểm tra tính mới của message.
- **SAML Assertion NotOnOrAfter** áp dụng điều kiện assertion khi login, **không phải thời hạn LogoutRequest**.
- **HttpSession timeout** là thời hạn idle session của SP.
- **IdP SSO session timeout** do IdP quản lý; hết IdP session không nhất thiết hủy ngay mọi SP session đã tạo.
- **LogoutRequest/Response IDs** nên được coi là unique và được chống replay trong cửa sổ cần thiết.

## 9. RelayState, binding và endpoint: thông điệp đi bằng đường nào?

### 9.1. HTTP-POST và HTTP-Redirect

SAML 2.0 hỗ trợ những binding khác nhau. Đối với SLO browser flows thường gặp:

| Binding | Hình thức HTTP | Điều cần lưu ý |
| --- | --- | --- |
| **HTTP-POST** | Form POST chứa **SAMLRequest** hoặc **SAMLResponse** đã mã hóa | Có thể dùng XML Signature của thông điệp, phụ thuộc profile/cấu hình |
| **HTTP-Redirect** | Query string chứa SAMLRequest/SAMLResponse, RelayState và chữ ký theo binding khi ký | Cần xác minh chữ ký trên dữ liệu query/binding chính xác, không chỉ base64-decoded XML |
| **SOAP/Back-channel** | Thông điệp gửi server-to-server trong một số profile | Khác browser session/cookie flow, Spring Security Servlet SLO mẫu tập trung browser |

**Không kết luận rằng mọi IdP đều hỗ trợ POST và Redirect cùng lúc.** Đọc phần **SingleLogoutService Binding/Location/ResponseLocation** trong IdP metadata và đối chiếu với Spring Security/version/IdP contract.

### 9.2. URL mặc định của Spring Security

Với **Spring Security 6.5 Servlet SAML2 SLO**, thường dùng:

- **POST /logout**: người dùng authenticated tại SP kích hoạt **SP-initiated** logout, với CSRF token nếu CSRF đang bật.
- **POST /logout/saml2/slo** chứa **SAMLRequest**: IdP-initiated LogoutRequest đi vào SP.
- **POST /logout/saml2/slo** chứa **SAMLResponse**: IdP gửi LogoutResponse cho LogoutRequest mà SP đã khởi tạo.

Trong endpoint SLO mặc định thường **không cần {registrationId}**, vì request có thể xác định registration thông qua principal hoặc thông điệp/giao dịch đã lưu. Nếu dùng nhiều IdP, việc chọn registration phải có cơ chế đáng tin, không dựa vào query parameter tùy ý.

**Không nhầm /logout/saml2/slo với /login/saml2/sso/{registrationId}.** ACS xử lý login SAML Response; SLO endpoint xử lý LogoutRequest/LogoutResponse.

### 9.3. RelayState dùng để làm gì?

**RelayState** là dữ liệu trạng thái theo HTTP binding. Trong SP-initiated SLO, repository có thể lưu LogoutRequest với RelayState và sử dụng nó để tìm/đối chiếu request lúc LogoutResponse đến.

**RelayState không phải chữ ký số**, không tự chứng minh danh tính và không nên biến trực tiếp thành URL redirect do client kiểm soát. Một mã RelayState tốt trong custom flow là giá trị không đoán được, có TTL, gắn giao dịch/phiên và chỉ dùng một lần. Mỗi LogoutResponse cần gắn với đúng LogoutRequest **và đúng IdP/registration**, không chỉ trùng một chuỗi RelayState.

## 10. Spring Security 6: các filter và repository liên quan

Spring Security cung cấp cơ chế chuẩn, không yêu cầu ứng dụng tự viết controller đọc XML logout:

| Thành phần | Vai trò |
| --- | --- |
| **saml2Logout()** | Kích hoạt hỗ trợ SAML Single Logout trong SecurityFilterChain |
| **Saml2RelyingPartyInitiatedLogoutSuccessHandler** | Xử lý bước sau local logout, khởi tạo SP-initiated LogoutRequest |
| **Saml2LogoutRequestResolver** | Tạo/ký/serialize LogoutRequest theo registration/phiên |
| **Saml2LogoutRequestRepository** | Lưu request SP đã phát để đối chiếu RelayState và LogoutResponse.InResponseTo |
| **Saml2LogoutResponseFilter** | Nhận/kiểm tra LogoutResponse trả về cho SP-initiated SLO |
| **Saml2LogoutResponseValidator** | Kiểm tra message SLO response (signature/issuer/destination/status và những ràng buộc khác) |
| **Saml2LogoutRequestFilter** | Nhận LogoutRequest IdP-initiated tại SP |
| **Saml2LogoutRequestValidator** | Kiểm tra LogoutRequest từ IdP trước khi kết thúc phiên local |
| **Saml2LogoutResponseResolver** | Tạo LogoutResponse trả lại IdP cho một AP-initiated LogoutRequest |
| **RelyingPartyRegistration** | Chứa cấu hình SP/IdP, SLO endpoints, signing/verification credentials |
| **LogoutHandler** | Xóa SecurityContext/HttpSession và tài nguyên local theo chính sách |

Spring Security documentation giải thích **LogoutRequest do SP gửi được lưu trong session** để so khớp RelayState và InResponseTo của LogoutResponse. Khi thay repository để hỗ trợ cluster, phải giữ khả năng correlation và single-use.

**Các validator tùy biến không được bỏ bước xác minh mặc định**. Nếu muốn bổ sung chính sách kiểm tra request/response, delegate tới validator của Spring/OpenSAML phù hợp phiên bản trước rồi thêm các điều kiện riêng. Không tự coi Status=Success hoặc Issuer text hợp lệ là đã xác minh chữ ký.

## 11. Ví dụ Spring Boot 3 + Spring Security 6: bật SLO đúng chỗ

Ví dụ dùng **Spring Boot 3.x tương thích Spring Security 6.x**, Java 17+, Servlet MVC. Để chạy end-to-end cần một IdP **thật có SingleLogoutService trong metadata**, SP đã đăng ký đúng entityID/SLO URL, private key SP **PKCS#8** và X.509 certificate tương ứng cho signing. Các tên miền **example.org** là minh họa, không phải dịch vụ công khai dùng để test.

### 11.1. Maven dependencies

Trong dự án Maven có Spring Boot parent/BOM, thêm:

~~~xml
<dependencies>
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
  </dependency>
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-security</artifactId>
  </dependency>
  <dependency>
    <groupId>org.springframework.security</groupId>
    <artifactId>spring-security-saml2-service-provider</artifactId>
  </dependency>
</dependencies>
~~~

Các artifact OpenSAML/transitive dependencies nên dùng phiên bản do Spring Security/Boot quản lý; không trộn tùy tiện Spring SAML Extension cũ với cấu hình **saml2Logout()** hiện đại.

### 11.2. application.yml

**src/main/resources/application.yml**:

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          company:
            assertingparty:
              metadata-uri: https://idp.example.org/metadata
            signing:
              credentials:
                - private-key-location: file:/run/secrets/sp-signing-pkcs8.pem
                  certificate-location: file:/run/secrets/sp-signing-cert.pem
            singlelogout:
              url: "{baseUrl}/logout/saml2/slo"

server:
  servlet:
    session:
      timeout: 30m
~~~

**Giải thích:**

- **registration.company** tạo một RelyingPartyRegistration với registrationId=company.
- **assertingparty.metadata-uri** là nơi lấy IdP metadata được kiểm soát, cần có **SingleLogoutService** để dùng SLO; IdP metadata còn công bố verification certificate.
- **signing.credentials** nạp private key/certificate SP để ký LogoutRequest/LogoutResponse. Private key phải do SP quản lý an toàn, không commit vào Git hoặc phân phối trong SPA/browser.
- **singlelogout.url** là endpoint SP nhận request/response SLO, cần công bố/đăng ký đúng ở IdP.
- **session.timeout** là thời gian idle local session, không phải quy tắc mặc định hoàn thành SLO toàn cục.

**Cảnh báo:** Đây là cấu hình **minh họa hình dạng thuộc tính**. Không khởi động được nếu metadata IdP không tồn tại, chứng thư/khóa không đọc được, metadata thiếu khả năng SLO hoặc application không được IdP đăng ký. Trong production, lấy khóa từ secret manager/keystore hoặc cơ chế quản lý khóa tin cậy, cấu hình HTTPS và public URLs chính xác.

### 11.3. Java application

**src/main/java/com/example/slo/SloApplication.java**:

~~~java
package com.example.slo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SloApplication {
    public static void main(String[] args) {
        SpringApplication.run(SloApplication.class, args);
    }
}
~~~

### 11.4. SecurityFilterChain.java

**src/main/java/com/example/slo/SamlSecurityConfig.java**:

~~~java
package com.example.slo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SamlSecurityConfig {

    @Bean
    SecurityFilterChain webSecurity(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated())
            .saml2Login(Customizer.withDefaults())
            .saml2Logout(Customizer.withDefaults());

        return http.build();
    }
}
~~~

**saml2Login()** bật đăng nhập SAML2. **saml2Logout()** bật RP- và AP-initiated SLO. Hai phương thức không thay thế nhau: muốn người dùng có phiên SAML tại SP để logout, trước đó cần đăng nhập hợp lệ.

**Không cần tự cấu hình LogoutRequest/LogoutResponse XML ở controller**: filter/resolver/validator của Spring Security thực thi giao thức. **Không tắt CSRF toàn ứng dụng** để làm POST /logout chạy; form nút Logout phải gửi CSRF token hợp lệ.

### 11.5. Controller xem trạng thái local session

**src/main/java/com/example/slo/SloController.java**:

~~~java
package com.example.slo;

import java.util.Map;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.saml2.provider.service.authentication.Saml2AuthenticatedPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class SloController {

    @GetMapping("/")
    public String home() {
        return "SAML SLO example ready";
    }

    @GetMapping("/me")
    public Map<String, String> whoAmI(
            @AuthenticationPrincipal Saml2AuthenticatedPrincipal user) {
        return Map.of(
            "subject", user.getName(),
            "registrationId", user.getRelyingPartyRegistrationId());
    }
}
~~~

Đây là controller trong ví dụ **chỉ một kiểu SAML login**. Nếu ứng dụng cho nhiều authentication mechanism, cần xử lý trường hợp principal không phải Saml2AuthenticatedPrincipal. Trong production không trả NameID/attribute nhạy cảm một cách vô điều kiện; endpoint chỉ để học/kiểm thử.

### 11.6. Chạy và thử đúng cách

Trong Maven project hợp lệ, với JDK 17+:

~~~bash
mvn spring-boot:run
~~~

Nếu ứng dụng khởi động được với metadata/credentials thật, endpoint public:

~~~bash
curl -i http://localhost:8080/
~~~

Body từ controller:

~~~text
SAML SLO example ready
~~~

Để kiểm thử SLO, **đăng nhập SAML thực sự trước** qua IdP đã cấu hình. Sau đó gửi **POST /logout** từ browser **có CSRF token thật và session cookie** để bắt đầu RP-initiated SLO. Không khuyến nghị thử POST thiếu token rồi hiểu HTTP 403 là lỗi SAML.

Các bước quan sát:

1. Network có POST /logout tại SP với CSRF hợp lệ.
2. SP tạo **LogoutRequest có ID riêng**, ký và gửi browser tới IdP SLO endpoint.
3. IdP xác minh, thực hiện logout và có thể gửi LogoutRequest tới SP khác.
4. IdP gửi **LogoutResponse** tới **/logout/saml2/slo** với InResponseTo trỏ ID của request SP đã tạo.
5. SP xác minh và chuyển đến trang thông báo kết quả, tùy Status và cấu hình.
6. Mở lại **/me**: nếu SP local session đã kết thúc, sẽ cần đăng nhập lại tại SP. Nếu IdP vẫn còn phiên SSO do SLO không hoàn tất, người dùng có thể được đăng nhập nhanh qua vòng SAML mới.

**Không có stdout cố định cho XML LogoutRequest/LogoutResponse** vì ID, IssueInstant, chữ ký, endpoint, NameID, SessionIndex đều phụ thuộc phiên thật. Không bao giờ copy một chuỗi Base64 SAMLResponse của người dùng từ production vào công cụ công khai để debug.

## 12. Phân biệt local logout và Single Logout trong Spring Security

### Chỉ local logout

Nếu cấu hình **.logout()** thông thường mà không bật saml2Logout() cho registration, POST /logout có thể:

- clear SecurityContext của SP;
- invalidate HttpSession;
- thực hiện các logout handlers nội bộ;
- điều hướng đến logout success URL.

Nó **không gửi LogoutRequest tới IdP**. Vì vậy IdP có thể vẫn giữ SSO session; người dùng vào lại SP có thể được cấp SAMLResponse mới mà không nhập mật khẩu.

### SLO đúng nghĩa

Khi SLO được cấu hình phù hợp, SP tạo **LogoutRequest**, IdP xác thực xử lý, và tùy flow có **LogoutResponse**. Đây là thông điệp giao thức, không chỉ xóa cookie.

Muốn tách đường dẫn **local logout** khỏi **SP-initiated SLO**, Spring Security hỗ trợ cấu hình theo hướng sau, là snippet thay thế trong cùng SecurityFilterChain:

~~~java
http
    .logout(logout -> logout.logoutUrl("/logout"))
    .saml2Logout(saml -> saml.logoutUrl("/saml2/logout"));
~~~

Đây là **fragment**, không phải class Java độc lập. Trong cấu hình đó **POST /logout** xóa phiên local còn **POST /saml2/logout** khởi tạo SLO theo chính sách. Cả hai đường dẫn phải có CSRF protection phù hợp; không dùng GET link thường thay cho hành động logout thay đổi trạng thái.

### Đừng hiểu sai kết quả

- **Local session SP đã xóa** không có nghĩa tất cả SP khác đã xóa.
- **LogoutResponse.InResponseTo trùng** không có nghĩa Status=Success.
- **Status=Success** từ một nhánh không tự chứng minh mọi browser, mọi thiết bị, mọi node đã kết thúc nếu triển khai không theo dõi các session đó.
- **LogoutRequest đã gửi** không có nghĩa IdP đã nhận và thực hiện.
- **Browser đóng tab giữa chừng** có thể khiến SLO cascade bị gián đoạn; cần UI, giám sát và chính sách phiên bổ sung.
- **Single Logout** khác **OIDC RP-initiated Logout**, OAuth token revocation và HTTP session invalidation; không dùng endpoint OIDC logout như SAML SLO endpoint.

## 13. Java 17 runnable: mô phỏng quan hệ request/response và chống replay

Mẫu dưới đây **không parse SAML XML và không xác minh chữ ký**, chỉ mô phỏng quy tắc:
**(1)** LogoutResponse.InResponseTo trùng pending LogoutRequest.ID; **(2)** Issuer là bên được chờ đợi; **(3)** chỉ xử lý một lần; **(4)** Status=Success mới cho kết luận thành công giao dịch minh họa.

**Tệp: LogoutMessageCorrelation.java**

~~~java
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

public final class LogoutMessageCorrelation {

    record Pending(String id, String expectedIssuer) { }

    record Reply(
        String id,
        String inResponseTo,
        String issuer,
        String status) { }

    private final Map<String, Pending> pending =
        new ConcurrentHashMap<>();

    void save(Pending request) {
        pending.put(request.id(), request);
    }

    boolean complete(Reply response) {
        if (response == null || response.inResponseTo() == null) {
            return false;
        }

        Pending request = pending.get(response.inResponseTo());

        if (request == null
                || !request.expectedIssuer().equals(response.issuer())
                || !"Success".equals(response.status())) {
            return false;
        }

        return pending.remove(request.id(), request);
    }

    public static void main(String[] args) {
        LogoutMessageCorrelation flow = new LogoutMessageCorrelation();
        flow.save(new Pending("_LOUT_1", "trusted-idp"));

        System.out.println("wrongRequest=" + flow.complete(
            new Reply("_R_1", "_OTHER", "trusted-idp", "Success")));
        System.out.println("wrongIssuer=" + flow.complete(
            new Reply("_R_2", "_LOUT_1", "other-idp", "Success")));
        System.out.println("success=" + flow.complete(
            new Reply("_R_3", "_LOUT_1", "trusted-idp", "Success")));
        System.out.println("replay=" + flow.complete(
            new Reply("_R_3", "_LOUT_1", "trusted-idp", "Success")));

        flow.save(new Pending("_LOUT_2", "trusted-idp"));
        System.out.println("partialSuccess=" + flow.complete(
            new Reply("_R_4", "_LOUT_2", "trusted-idp", "PartialLogout")));
    }
}
~~~

Biên dịch/chạy với JDK 17+:

~~~bash
javac LogoutMessageCorrelation.java
java LogoutMessageCorrelation
~~~

**Stdout xác định trước:**

~~~text
wrongRequest=false
wrongIssuer=false
success=true
replay=false
partialSuccess=false
~~~

Giải thích:

- **wrongRequest:** response trỏ request không có trong repository.
- **wrongIssuer:** InResponseTo đúng nhưng trả từ bên không được chờ.
- **success:** correlation và Status minh họa đều hợp lệ; pending request được consume bằng **remove(key, expected)**.
- **replay:** đã consume request nên response cũ không hoàn thành lần nữa.
- **partialSuccess:** không thể kết luận toàn bộ logout hoàn tất chỉ từ PartialLogout.

**Cảnh báo:** Logic trên **không thay thế** SAML LogoutResponseValidator. Nó không kiểm tra signature, XML schema, binding, Destination, thời gian, RelayState, session binding, certificate rotation hoặc trạng thái nhiều SP. Chỉ gọi method complete sau khi một validator được tin cậy đã xác minh toàn bộ thông điệp; ứng dụng Spring Security thực nên dùng saml2Logout() chuẩn.

## 14. Replay protection và tương quan giao dịch

### 14.1. Vì sao cần lưu LogoutRequest?

Giả sử attacker lưu một LogoutResponse có chữ ký hợp lệ từ một giao dịch trước. Nếu SP chấp nhận lại response chỉ vì chữ ký đúng, nó có thể hiển thị “đăng xuất thành công” cho giao dịch không tồn tại, làm sai audit/flow và có thể gây tình trạng nhầm lẫn phiên.

Cách xử lý:

1. Khi **SP phát LogoutRequest**, lưu request ID, IdP/registration, binding, RelayState, thời điểm phát, hạn sử dụng và thông tin tối thiểu cần để verify.
2. Khi **LogoutResponse trở về**, xác minh chữ ký/issuer/destination và đối chiếu **InResponseTo** với đúng pending request.
3. **Consume** pending request một lần, chống đồng thời/replay theo khả năng repository.
4. Có chiến lược TTL/cache và cleanup cho request không bao giờ nhận response (người dùng đóng tab, IdP timeout).
5. Nếu nhiều node, pending request repository cần chia sẻ/đồng bộ và atomic operation phù hợp.
6. Chỉ thông báo SLO thành công khi đủ điều kiện cả về correlation và trạng thái được chấp nhận.

### 14.2. Đối với IdP-initiated request

SP không phải đã phát một LogoutRequest để đối chiếu. Lúc đó SP **xác minh LogoutRequest đầu vào**, issuer/registration, đối tượng phiên và replay ID của request do IdP phát. Sau khi thực hiện logout, SP tạo **LogoutResponse.InResponseTo = chính LogoutRequest.ID đó**.

Không nhét request IdP-initiated vào pending request repository dành cho request SP phát một cách không kiểm soát. Mỗi hướng có lưu lượng và chủ thể khởi tạo khác nhau.

### 14.3. Những sai lầm khi dùng RelayState

- Coi RelayState như username hoặc chứng cứ xác thực.
- Để browser chỉ định URL redirect sau logout không có allowlist.
- Truy tìm request bằng RelayState nhưng bỏ kiểm tra issuer/binding/ID.
- Lưu pending requests trong cache global mà không có ràng buộc giao dịch/phiên và TTL.
- Không xóa request sau khi đã sử dụng.
- Mất repository khi local session bị invalidate giữa bước gửi LogoutRequest và nhận LogoutResponse.

Với một triển khai custom, phải nắm rõ **vòng đời lưu request trong Spring** trước khi thay thành cache Redis/DB và không giả định rằng mọi hình thức lưu phân tán đều bảo mật tương đương HttpSession.

## 15. Các lỗi vận hành thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Đăng xuất ở SP nhưng IdP vẫn đăng nhập | Chỉ local logout; chưa bật SLO hoặc IdP không hỗ trợ | Xác nhận saml2Logout(), metadata SingleLogoutService, signing credentials |
| Bấm logout nhận 403 | Thiếu CSRF token khi POST /logout hoặc matcher security sai | Kiểm tra form/session/CSRF; không tắt CSRF toàn web |
| IdP từ chối LogoutRequest | SP signing key/certificate không được tin; Issuer/NameID/SessionIndex sai | Đối chiếu SP metadata, IdP registration và policy |
| SP nhận LogoutResponse nhưng trả 400 | Signature, issuer, destination, status hoặc InResponseTo không đạt | Xem lỗi validation đã được làm sạch, đối chiếu pending request |
| LogoutResponse.InResponseTo mismatch | Response thuộc request khác hoặc repository pending đã mất | Kiểm tra ID, RelayState, node/session, độ trễ, callback path |
| AP-initiated LogoutRequest bị từ chối | Chữ ký/Issuer/Destination không đúng; người dùng/phiên không phù hợp | Kiểm tra IdP metadata, SLO endpoint và session correlation |
| Sau logout thấy lại phiên nhanh | Local logout xong nhưng IdP session vẫn còn | Kiểm tra IdP SLO và trạng thái các SP; không dựa riêng vào UI |
| Một SP đã logout, SP khác vẫn active | IdP không điều phối thành công, SP thứ ba offline, browser dừng | Xử lý PartialLogout, policy timeout, cảnh báo người dùng |
| SessionIndex không khớp | Mất/thay đổi mapping session; IdP phát giá trị khác | Kiểm tra contract IdP/NameID/SessionIndex và session registry |
| SLO endpoint 404/405 | Binding/method sai hoặc endpoint không nằm trong SecurityFilterChain | Kiểm tra /logout/saml2/slo, SingleLogoutService và DSL |
| Chữ ký hợp lệ nhưng sai Issuer | Nhầm trust giữa IdP company/partner | Ràng buộc registration/issuer và certificate đúng đối tác |
| Trả LogoutResponse rồi browser không quay về SP | AP-initiated flow do IdP điều phối, browser rời SP | Không giả định success handler SP sẽ hiển thị landing page |
| Callback sau local session invalidation không tìm request | Repository/logout handler custom dọn luôn pending state | Dùng cách lưu request phù hợp vòng đời SLO chuẩn |
| 多 node có node logout nhưng node khác vẫn active | Session cục bộ, không đồng bộ logout | Spring Session/shared store, session registry, revoke policy |
| Reverse proxy khiến Destination không khớp | Public scheme/host/port khác nội bộ | Sửa forwarded headers qua proxy tin cậy, SLO URL public và metadata |

Trong log thật không nên dump **SAMLRequest**, **SAMLResponse**, XML chứa NameID/SessionIndex, signing private key, cookie/session ID hoặc các thông tin cá nhân khác. Dùng correlation ID, registrationId và trạng thái validation ở mức đã được giảm thiểu.

## 16. Các ca kiểm thử cần có

### 16.1. SP-initiated

1. User đã SAML login hợp lệ; **POST /logout** có CSRF đúng → local session bị invalidated, SP phát LogoutRequest signed.
2. LogoutRequest có **Issuer SP, Destination IdP SLO**, ID riêng và NameID/SessionIndex phù hợp khả năng IdP.
3. LogoutResponse của IdP có **InResponseTo đúng**, chữ ký và Status=Success → flow hoàn tất theo cấu hình.
4. **Sai InResponseTo**, dù message còn lại có chữ ký → phải từ chối.
5. **Sai Issuer/certificate** nhưng InResponseTo đúng → từ chối.
6. **Status=PartialLogout/Responder/Requester** → không hiển thị “mọi ứng dụng đã logout thành công”.
7. **Replay LogoutResponse** sau khi đã consume → từ chối/không xử lý trùng.
8. Browser đóng tab sau khi SP xóa phiên nhưng trước khi IdP phản hồi → SP vẫn local logout, trạng thái global không được cam kết.
9. IdP không có SingleLogoutService trong metadata → cấu hình không thể mặc định hoàn tất SLO.
10. SP signing key mới nhưng IdP chưa được cập nhật chứng thư → phát hiện/khôi phục qua rotation plan.

### 16.2. IdP-initiated

1. IdP gửi **SAMLRequest** signed tới SP endpoint SLO; SP verify và logout đúng phiên, gửi LogoutResponse.
2. LogoutResponse của SP phải có **InResponseTo = ID của LogoutRequest từ IdP**, không phải ID của AuthnRequest lúc login.
3. Request có **NameID** không khớp session/cross-tenant → không hủy sai phiên.
4. Request có **SessionIndex** khác → xử lý theo profile và policy, không nhầm với JSESSIONID.
5. Request từ IdP **không được allowlist** → từ chối dù XML tự ký hợp lệ.
6. Replay LogoutRequest đã xử lý → không phá thêm session ngoài phạm vi.
7. Không có session local hoặc đã logout → đáp ứng status đúng contract, không giả mạo user.
8. POST callback cross-site mất cookie → kiểm tra SameSite và session binding; không bỏ chữ ký/authorization.
9. Nhiều phiên trên nhiều node/thiết bị → xác minh chính sách logout một phiên hay nhiều phiên, session store và registry.
10. IdP gửi request bằng binding SP không hỗ trợ → lỗi được xử lý tường minh và kiểm thử interoperability.

### 16.3. Độ tin cậy vận hành

- Thử **HTTP-POST vs Redirect binding** theo cấu hình IdP hỗ trợ, không suy đoán tất cả giống nhau.
- Đối chiếu public SLO URL, metadata SP, Issuer, Destination qua reverse proxy.
- Kiểm tra lỗi mạng giữa bước SP gửi request và IdP gửi response.
- Kiểm tra UX khi SP local logout đã xong nhưng global logout chưa được xác nhận.
- Kiểm tra session revoke trên **nhiều app instances**, không chỉ node xử lý request.
- Test certificate rollover (old/new verification certificates) và hết thời gian tin cậy.
- Giám sát số **SLO request**, **SLO success**, **validation failed**, **PartialLogout**, timeout và orphaned pending requests.

## 17. Checklist triển khai production

- [ ] IdP thật sự hỗ trợ **SAML Single Logout**, metadata có SingleLogoutService và binding tương thích.
- [ ] SP có **signing private key/certificate** hợp lệ và IdP đã tin certificate SP; SP tin IdP signing cert được duyệt.
- [ ] Bật **saml2Login()** và **saml2Logout()** trong đúng SecurityFilterChain cho browser.
- [ ] URL **/logout/saml2/slo**, SingleLogoutService, SP entityID, reverse proxy public scheme/host thống nhất.
- [ ] Phân biệt **SP-initiated** và **IdP-initiated**; LogoutRequest do ai phát thì người còn lại trả LogoutResponse.
- [ ] **LogoutResponse.InResponseTo** đúng **LogoutRequest.ID** tương ứng, không so với LogoutResponse.ID hay AuthnRequest.ID.
- [ ] Xác minh chữ ký, Issuer, Destination, binding, time, Status; đối chiếu NameID/SessionIndex theo contract.
- [ ] SP lưu/consume pending LogoutRequest phù hợp; RelayState có kiểm soát, replay không được chấp nhận.
- [ ] **SessionIndex** không bị nhầm với HttpSession ID; có session registry/shared store nếu cần logout đa phiên.
- [ ] Nếu IdP điều phối nhiều SP, hiểu **PartialLogout** và giới hạn tính toàn cục của trạng thái trả về.
- [ ] Không tự nới lỏng validation để “sửa” mismatch hoặc lỗi cookie/metadata.
- [ ] POST /logout có CSRF protection; không dùng GET logout shortcut hay mở redirect tùy ý.
- [ ] Local logout và global SLO có UX/audit khác nhau, không báo thành công toàn cục khi chưa có bằng chứng.
- [ ] Xây chính sách timeout, rollback, credential rotation, nhiều IdP/tenant và bất thường khi mất mạng.
- [ ] Test wrong InResponseTo, wrong issuer, wrong session, replay, partial status, IdP outage, proxy và multi-node.
- [ ] Không log raw SAML XML, NameID/SessionIndex/cookie/private key hoặc dữ liệu nhạy cảm.

**Ghi nhớ cuối bài:** Một **LogoutRequest** luôn có ID để biết yêu cầu nào đang được thực thi. **LogoutResponse.InResponseTo** phải trỏ **ID của LogoutRequest trực tiếp mà nó trả lời**, đồng thời mang **Status** phản ánh kết quả. SAML Single Logout có thể do **SP** hoặc **IdP** khởi xướng; trong cả hai trường hợp, chữ ký, issuer, đích nhận, phiên cần logout và correlation đều quan trọng. Spring Security cung cấp **saml2Logout()** và các filter/resolver/validator chuyên trách, nhưng ứng dụng vẫn phải hiểu giới hạn khi logout liên quan nhiều SP và mạng.

## 18. Tài liệu tham khảo

- [Spring Security 6.5 – Performing Single Logout](https://docs.spring.io/spring-security/reference/6.5/servlet/saml2/logout.html): RP/AP-initiated SLO, filter, endpoint, resolver, request repository, signing và validation.
- [Spring Security 6.5 – SAML2 Login Overview](https://docs.spring.io/spring-security/reference/6.5/servlet/saml2/login/overview.html): RelyingPartyRegistration, SAML principal và luồng login trước khi logout.
- [Spring Security 6.5 – SAML2 Metadata](https://docs.spring.io/spring-security/reference/6.5/servlet/saml2/metadata.html): SP/IdP metadata và thông tin endpoint.
- [OASIS – SAML 2.0 Core Specification](https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf): LogoutRequestType, LogoutResponse, status codes, NameID và SessionIndex.
- [OASIS – SAML 2.0 Profiles Specification](https://docs.oasis-open.org/security/saml/v2.0/saml-profiles-2.0-os.pdf): Web Browser Single Logout Profile, request/response requirements và binding.
- [OASIS – SAML Technical Overview (HTML)](https://docs.oasis-open.org/security/saml/Post2.0/sstc-saml-tech-overview-2.0.html): luồng SP-initiated logout qua nhiều SP.
- [Microsoft identity platform – SAML Single Sign-Out Protocol](https://learn.microsoft.com/en-us/entra/identity-platform/single-sign-out-saml-protocol): ví dụ LogoutRequest/LogoutResponse và InResponseTo.
