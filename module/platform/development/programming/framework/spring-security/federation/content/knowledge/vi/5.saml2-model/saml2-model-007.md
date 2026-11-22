# SubjectConfirmation, Recipient và InResponseTo trong SAML 2.0

## 1. Mục tiêu và bối cảnh

Khi **Service Provider (SP)** nhận **SAMLResponse** qua trình duyệt, một chữ ký số hợp lệ chưa đủ để kết luận rằng **Assertion này được phép dùng cho phiên đăng nhập hiện tại, tại endpoint hiện tại**. SP còn phải xác minh các ràng buộc của chủ thể (*subject confirmation*) và mối liên hệ với yêu cầu đăng nhập đã phát ra.

Ba khái niệm trọng tâm là:

1. **SubjectConfirmation**: cách SP xác nhận rằng đối tượng đang mang Assertion được phép trình Assertion đó để xác lập danh tính được nêu trong **Subject**. Với **SAML 2.0 Web Browser SSO**, phương thức thường dùng là **bearer**.
2. **Recipient**: thuộc tính của **SubjectConfirmationData**, chỉ đích danh **Assertion Consumer Service (ACS)** mà Assertion có thể được chuyển tới.
3. **InResponseTo**: ID dùng để liên kết phản hồi/chứng thực với **AuthnRequest** trước đó, giúp SP xác định phản hồi có thuộc giao dịch đăng nhập mà chính SP đã khởi tạo hay không.

**Bối cảnh học tập:** SAML 2.0 Web Browser SSO Profile, ứng dụng **Spring Security Servlet** đóng vai trò SP, và IdP doanh nghiệp đóng vai trò bên phát hành Assertion. Phân biệt quy tắc **giao thức OASIS** với **cấu hình, cách lưu request và hành vi cụ thể của Spring Security**.

Sau bài này, bạn cần giải thích được *vì sao* các trường tồn tại, *phải so sánh với giá trị nào*, *khi nào từ chối login*, và *cách kiểm tra lỗi khi triển khai thực tế*. Tuyệt đối không xây cơ chế login bằng cách tự parse Base64/XML rồi tự so vài chuỗi.

## 2. Subject, SubjectConfirmation và bearer khác nhau như thế nào?

Trong Assertion, **Subject** nói về **người dùng/đối tượng** được IdP xác thực, thường có **NameID**. Nhưng việc một tài liệu XML nhắc tới tên người dùng chưa chứng minh tài liệu ấy được phép dùng để đăng nhập SP.

**SubjectConfirmation** nằm trong **Subject** và mô tả điều kiện để một bên nhận có thể **xác nhận subject**. Mỗi phần tử có **Method**; giá trị điển hình trong Web Browser SSO là:

~~~text
urn:oasis:names:tc:SAML:2.0:cm:bearer
~~~

**Bearer** nghĩa là bên mang Assertion (trong luồng này, trình duyệt chuyển tiếp SAMLResponse) có thể trình nó để xác nhận subject **nếu toàn bộ ràng buộc bảo mật được đáp ứng**. Không cần trình duyệt chứng minh sở hữu khóa riêng. Vì vậy, **bearer Assertion phải được bảo vệ đặc biệt chống gửi sai đích, quá hạn và phát lại**.

Ví dụ phần tử mang ba trường chính, chỉ dùng để giải thích cấu trúc:

~~~xml
<saml:Subject xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion">
  <saml:NameID>employee-123</saml:NameID>
  <saml:SubjectConfirmation
      Method="urn:oasis:names:tc:SAML:2.0:cm:bearer">
    <saml:SubjectConfirmationData
        Recipient="https://app.example.com/login/saml2/sso/corp"
        InResponseTo="_req_A01"
        NotOnOrAfter="2026-11-07T09:05:00Z"/>
  </saml:SubjectConfirmation>
</saml:Subject>
~~~

Đây là **đoạn XML minh họa**, không phải Response đầy đủ/đã ký; **không thể dùng để đăng nhập**. Trong ví dụ, SP cần biết ACS mong đợi là URL nào, AuthnRequest đã phát có ID nào và thời gian hiện tại để kiểm tra ràng buộc.

### SubjectConfirmationData: nơi chứa điều kiện

**SubjectConfirmationData** cung cấp các dữ kiện giúp SP quyết định một SubjectConfirmation cụ thể có hợp lệ không.

| Thuộc tính | Vai trò đối với bearer Web Browser SSO | Ví dụ/ghi chú |
| --- | --- | --- |
| **Recipient** | Bắt buộc: ràng buộc Assertion vào ACS URL của SP nhận. | https://app.example.com/login/saml2/sso/corp |
| **NotOnOrAfter** | Bắt buộc: giới hạn thời điểm cuối cùng có thể xác nhận subject. | 2026-11-07T09:05:00Z |
| **InResponseTo** | Bắt buộc khớp **AuthnRequest.ID** khi Response đáp lại AuthnRequest; không xuất hiện trong phản hồi unsolicited theo Web Browser SSO Profile. | _req_A01 |
| **Address** | Có thể có: giới hạn địa chỉ mạng của user agent; kiểm tra tùy chính sách/profile. | Có thể không đáng tin nếu qua proxy, NAT hoặc mạng di động. |
| **NotBefore** | Kiểu dữ liệu SAML tổng quát cho phép, **nhưng Web Browser SSO bearer profile quy định không được đặt trong bearer SubjectConfirmationData**. | Không nhầm với **Conditions.NotBefore**. |

Điểm dễ sai: **SubjectConfirmationData.NotOnOrAfter không phải là thời hạn của session web ứng dụng**; nó chỉ nói Assertion có thể được trình để xác nhận subject trước thời điểm này. Phiên ứng dụng tạo sau khi login có vòng đời riêng.

Một Assertion có thể có **nhiều SubjectConfirmation**. Theo quy tắc Web Browser SSO và errata OASIS, **một bearer SubjectConfirmation thỏa tất cả điều kiện có thể đủ để xác nhận subject của Assertion đó**; nếu Response có nhiều Assertion được sử dụng, **mỗi Assertion vẫn phải được đánh giá độc lập**. Không nên viết logic “lấy phần tử đầu tiên và bỏ qua tất cả phần còn lại” một cách tùy tiện.

## 3. Recipient: ràng buộc đúng nơi tiêu thụ Assertion

**Recipient** nằm ở:

~~~text
Assertion
└── Subject
    └── SubjectConfirmation (Method=bearer)
        └── SubjectConfirmationData Recipient="..."
~~~

Nó phải chỉ **địa chỉ ACS thực tế của SP** mà Response được giao tới, ví dụ:

~~~text
https://app.example.com/login/saml2/sso/corp
~~~

Với Spring Security Servlet, URL xử lý SAMLResponse mặc định thường có dạng **/login/saml2/sso/{registrationId}**. Nếu registrationId là **corp**, ACS ở ví dụ phải được **IdP đăng ký chính xác** và **Spring Security** phải nhìn thấy cùng URL công khai.

### Recipient bảo vệ điều gì?

Giả sử cùng một IdP tin cậy hai SP:

- **SP A:** https://app-a.example.com/login/saml2/sso/corp
- **SP B:** https://app-b.example.com/login/saml2/sso/corp

Một Assertion do IdP phát hành với **Recipient của A** không được dùng để login **B**, ngay cả khi cả A và B đều tin cậy chữ ký của **cùng IdP**. Điều kiện này ngăn Assertion bị chuyển tới **đúng loại hệ thống, sai ứng dụng**.

Tương tự, hai ACS trên cùng host có thể là hai đích khác nhau:

- https://app.example.com/login/saml2/sso/corp
- https://app.example.com/login/saml2/sso/partner

Nếu token được cấp cho **corp**, không được chấp nhận nó ở endpoint **partner** chỉ vì hostname giống nhau.

### Recipient khác Response.Destination và Audience

| Trường | Nằm ở đâu? | So với giá trị nào? | Chức năng |
| --- | --- | --- | --- |
| **Recipient** | **SubjectConfirmationData** trong Assertion | ACS URL nơi bearer Assertion được giao. | Xác nhận **đích được phép nhận Assertion**. |
| **Destination** | Thuộc tính **Response** (protocol message) | Đích nhận Response theo binding, thường cũng là ACS URL. | Xác nhận **thông điệp giao thức được gửi đúng endpoint**. |
| **Audience** | **Conditions → AudienceRestriction → Audience** trong Assertion | **entityId của SP**. | Xác nhận **Assertion được phép dùng bởi RP nào**. |
| **Issuer** | Issuer của Response/Assertion | Định danh IdP/đối tác tin cậy trong registration. | Xác nhận **bên phát hành**. |

Ba trường **Recipient**, **Destination**, **Audience** đều quan trọng, nhưng **không thay thế được nhau**. Ví dụ entityId SP có thể là **https://app.example.com/saml/metadata**, còn ACS là **https://app.example.com/login/saml2/sso/corp**. Audience phải khớp entityId, Recipient phải khớp ACS.

Không dùng một phép kiểm tra “cùng hostname” chung cho Recipient và Audience. Cũng không tự chuẩn hóa URL khác nhau bằng cách tùy ý bỏ schema, port hoặc path. Hãy đối chiếu URL public trong SP metadata, IdP registration và giá trị XML thực tế theo quy tắc giao thức và thư viện.

### Lỗi điển hình khi có reverse proxy

SP chạy nội bộ tại **http://spring-internal:8080**, nhưng trình duyệt truy cập **https://app.example.com**. Nếu IdP gửi:

~~~xml
<saml:SubjectConfirmationData
    Recipient="https://app.example.com/login/saml2/sso/corp"
    NotOnOrAfter="2026-11-07T09:05:00Z"/>
~~~

trong khi ứng dụng xác định ACS mặc định là **http://spring-internal:8080/login/saml2/sso/corp**, bước so khớp có thể thất bại. Giải pháp là **đồng bộ URL công khai**: proxy headers đáng tin, base URL/entityId/ACS cấu hình đúng, IdP metadata và SP metadata khớp nhau. **Không** sửa lỗi bằng cách bỏ kiểm tra Recipient.

Nếu các bản ghi báo lỗi lúc thì dùng **http**, lúc **https**, hoặc thay đổi host theo load balancer, ưu tiên kiểm tra sơ đồ triển khai trước khi thay đổi validation.

## 4. InResponseTo: ràng buộc phản hồi với yêu cầu login

Trong **SP-initiated SSO**, ứng dụng tự tạo **AuthnRequest**. AuthnRequest có **ID duy nhất, khó đoán** cho giao dịch, ví dụ:

~~~xml
<samlp:AuthnRequest
    xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    ID="_req_A01"
    Version="2.0"
    IssueInstant="2026-11-07T09:00:00Z"
    Destination="https://idp.example.org/sso"
    AssertionConsumerServiceURL="https://app.example.com/login/saml2/sso/corp"/>
~~~

Ví dụ này lược bỏ các thành phần của AuthnRequest thực tế để nhấn mạnh **ID**; không phải bản tin hoàn chỉnh để gửi IdP. SP lưu **ngữ cảnh của yêu cầu đang chờ** ở kho trạng thái tương ứng, rồi trình duyệt chuyển hướng tới IdP.

Sau xác thực, IdP gửi **Response.InResponseTo** và **SubjectConfirmationData.InResponseTo** trỏ tới **cùng ID gốc**. Khi nhận callback, SP phải kiểm tra:

1. Có **AuthnRequest tương ứng** đã được **SP thực sự tạo và lưu** cho luồng/browser session này hay không?
2. **Response.InResponseTo** có khớp **AuthnRequest.ID** đã lưu không?
3. **SubjectConfirmationData.InResponseTo** của bearer confirmation được chọn có khớp **AuthnRequest.ID** không?
4. Yêu cầu đang chờ có phù hợp với **IdP, registration, endpoint, RelayState, phiên trình duyệt và chính sách one-time/expiry** không?
5. Response và Assertion có còn hợp lệ ở các kiểm tra độc lập như signature, issuer, audience, thời gian và recipient không?

**Không lấy InResponseTo làm bằng chứng duy nhất rằng phản hồi thuộc đúng phiên trình duyệt.** Attacker có thể biết hoặc gửi cùng một chuỗi ID; SP cần trạng thái request đã lưu **gắn đúng ngữ cảnh login** và các ràng buộc giao thức khác.

### Ba ID rất dễ bị nhầm

| Trường | Ví dụ | Nguồn tạo | Dùng để làm gì |
| --- | --- | --- | --- |
| **AuthnRequest.ID** | _req_A01 | SP | Định danh **yêu cầu login** đã phát. |
| **Response.ID** | _res_B52 | IdP | Định danh chính **Response** IdP gửi về; có thể dùng phục vụ logging/audit/chống replay. |
| **Assertion.ID** | _assert_C77 | IdP | Định danh **Assertion**; hữu ích khi áp dụng chính sách one-time/replay. |

Vì thế, **InResponseTo phải khớp _req_A01**, **không phải _res_B52 hay _assert_C77**. Nó cũng **không** phải SessionIndex, NameID, JSESSIONID, cookie, RelayState hoặc ID của người dùng.

### InResponseTo ở hai lớp

Có thể gặp **InResponseTo** tại:

- **Response.InResponseTo**: thuộc tính của **SAML protocol Response**, thể hiện Response trả lời yêu cầu nào.
- **SubjectConfirmationData.InResponseTo**: điều kiện của **bearer subject confirmation**, ràng buộc Assertion với cùng yêu cầu ban đầu.

Phải hiểu đây là **hai vị trí khác nhau trong XML**. Đối với SP-initiated flow, việc một vị trí đúng **không tạo ngoại lệ** cho vị trí còn lại sai. Validator tuân thủ profile không nên chỉ kiểm tra trường Response rồi bỏ trường trong bearer SubjectConfirmationData.

## 5. Ví dụ XML thể hiện cả ba quy tắc

Giả sử:

- IdP entityId: **https://idp.example.org/metadata**
- SP entityId: **https://app.example.com/saml2/service-provider-metadata/corp**
- SP ACS: **https://app.example.com/login/saml2/sso/corp**
- SP vừa gửi AuthnRequest có ID **_req_A01**
- IdP phát hành Assertion tại **09:00:25 UTC**, hạn sử dụng bearer confirmation là **09:05:00 UTC**.

Đây là **sơ đồ XML giản lược** để học cấu trúc. Nó **chưa có XML Signature** và các trường chi tiết để xác minh profile nên **không phải một SAMLResponse hợp lệ để đăng nhập**. Trong hệ thống thật, IdP ký Response hoặc Assertion đúng yêu cầu trust và Spring Security/OpenSAML xác minh chữ ký.

~~~xml
<samlp:Response
    xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    ID="_res_B52"
    Version="2.0"
    IssueInstant="2026-11-07T09:00:25Z"
    Destination="https://app.example.com/login/saml2/sso/corp"
    InResponseTo="_req_A01">

  <saml:Issuer>https://idp.example.org/metadata</saml:Issuer>
  <samlp:Status>
    <samlp:StatusCode
        Value="urn:oasis:names:tc:SAML:2.0:status:Success"/>
  </samlp:Status>

  <saml:Assertion
      ID="_assert_C77"
      Version="2.0"
      IssueInstant="2026-11-07T09:00:25Z">
    <saml:Issuer>https://idp.example.org/metadata</saml:Issuer>

    <saml:Subject>
      <saml:NameID>employee-123</saml:NameID>
      <saml:SubjectConfirmation
          Method="urn:oasis:names:tc:SAML:2.0:cm:bearer">
        <saml:SubjectConfirmationData
            Recipient="https://app.example.com/login/saml2/sso/corp"
            InResponseTo="_req_A01"
            NotOnOrAfter="2026-11-07T09:05:00Z"/>
      </saml:SubjectConfirmation>
    </saml:Subject>

    <saml:Conditions
        NotBefore="2026-11-07T08:59:30Z"
        NotOnOrAfter="2026-11-07T09:05:00Z">
      <saml:AudienceRestriction>
        <saml:Audience>https://app.example.com/saml2/service-provider-metadata/corp</saml:Audience>
      </saml:AudienceRestriction>
    </saml:Conditions>

    <saml:AuthnStatement
        AuthnInstant="2026-11-07T09:00:10Z">
      <saml:AuthnContext>
        <saml:AuthnContextClassRef>
          urn:oasis:names:tc:SAML:2.0:ac:classes:PasswordProtectedTransport
        </saml:AuthnContextClassRef>
      </saml:AuthnContext>
    </saml:AuthnStatement>
  </saml:Assertion>
</samlp:Response>
~~~

Đọc từ ngoài vào:

1. **Response.InResponseTo=_req_A01**: phản hồi giao thức nhắm tới AuthnRequest của SP.
2. **Response.Destination=ACS**: bản tin Response được chuyển đến endpoint ACS hợp lệ.
3. **Assertion.Subject.NameID=employee-123**: subject được IdP mô tả, **chưa phải bằng chứng tự đủ**.
4. **SubjectConfirmation.Method=bearer**: cho phép xác nhận subject theo bearer profile.
5. **SubjectConfirmationData.Recipient=ACS**: chỉ endpoint này được xác nhận subject.
6. **SubjectConfirmationData.InResponseTo=_req_A01**: subject confirmation gắn với đúng yêu cầu ban đầu.
7. **SubjectConfirmationData.NotOnOrAfter=09:05 UTC**: sau thời điểm đó không được chấp nhận bearer confirmation, có xét sai lệch đồng hồ nhỏ theo chính sách.
8. **Conditions.Audience**: Assertion chỉ dành cho SP có entityId cụ thể.
9. **Chữ ký, issuer, status, thời gian, correlation, replay** vẫn phải được kiểm tra độc lập trước khi tạo Authentication.

### Nếu chỉ đổi Recipient thì điều gì xảy ra?

Giữ nguyên mọi trường khác nhưng đổi:

~~~xml
<saml:SubjectConfirmationData
    Recipient="https://other-app.example.com/login/saml2/sso/corp"
    InResponseTo="_req_A01"
    NotOnOrAfter="2026-11-07T09:05:00Z"/>
~~~

SP tại **app.example.com** phải từ chối dùng confirmation này vì **Recipient** không khớp **ACS nhận Response**. Nếu người nào đó sửa XML sau khi IdP ký, chữ ký cũng có thể hỏng; nhưng **không vì chữ ký hợp lệ ban đầu mà bỏ bước kiểm tra Recipient**. Hai cơ chế phòng ngự giải quyết các vấn đề khác nhau.

### Nếu chỉ đổi InResponseTo?

~~~xml
<saml:SubjectConfirmationData
    Recipient="https://app.example.com/login/saml2/sso/corp"
    InResponseTo="_req_KHAC"
    NotOnOrAfter="2026-11-07T09:05:00Z"/>
~~~

SP có request đang chờ là **_req_A01**, nên confirmation này không tương ứng với giao dịch login đó. Phải từ chối confirmation trong ngữ cảnh SP-initiated, dù **Recipient** khớp.

## 6. NotOnOrAfter: ranh giới thời gian không được bỏ qua

Web Browser SSO bearer profile yêu cầu **SubjectConfirmationData.NotOnOrAfter**. Nếu thời điểm hiện tại đã đạt hoặc vượt mốc này, confirmation **không còn hợp lệ** (trừ chênh lệch đồng hồ nhỏ được cấu hình hợp lý).

Ví dụ không xét clock skew:

| Thời điểm SP kiểm tra (UTC) | NotOnOrAfter | Bearer confirmation còn thời hạn? |
| --- | --- | --- |
| 09:04:59Z | 09:05:00Z | Có |
| 09:05:00Z | 09:05:00Z | **Không** – ranh giới **không bao gồm** chính thời điểm kết thúc |
| 09:05:01Z | 09:05:00Z | Không |
| 09:00:00Z | 09:05:00Z | Có về **thời gian**, nhưng còn phải kiểm tra mọi điều kiện khác |

Đừng nhầm:

- **Conditions.NotBefore / Conditions.NotOnOrAfter:** điều kiện thời gian chung để chấp nhận Assertion.
- **SubjectConfirmationData.NotOnOrAfter:** giới hạn xác nhận subject với bearer.
- **AuthnStatement.AuthnInstant:** thời điểm IdP đã xác thực người dùng.
- **AuthnStatement.SessionNotOnOrAfter:** giới hạn phiên liên quan AuthnStatement nếu có, cần được xử lý theo profile/policy; không thay cho SCD.NotOnOrAfter.
- **HttpSession timeout / JSESSIONID:** thời gian sống của phiên ứng dụng Spring; không phải thời hạn có thể dùng lại Assertion.

Đặc biệt, **NotBefore có thể xuất hiện trong Conditions**, nhưng theo quy tắc **Web Browser SSO bearer confirmation**, **không đặt NotBefore trên bearer SubjectConfirmationData**. Nếu IdP xuất dữ liệu không tương thích, nên sửa cấu hình/phát hành của IdP thay vì gỡ kiểm tra thời gian.

**Clock skew** chỉ dùng để chịu sai số đồng hồ nhỏ do hạ tầng, không dùng như mẹo gia hạn Assertion hàng giờ. Đồng bộ NTP cho SP và IdP; khi chỉnh skew phải kiểm tra ảnh hưởng đến mọi loại điều kiện thời gian và khả năng replay.

## 7. SP-initiated và IdP-initiated: InResponseTo có gì khác?

### 7.1. SP-initiated login

Ứng dụng Spring bắt đầu bằng:

~~~text
GET /saml2/authenticate/corp
    -> Spring tạo AuthnRequest ID=_req_A01
    -> lưu request đang chờ trong repository/phiên
    -> browser được điều hướng đến IdP
    -> IdP gửi Response InResponseTo=_req_A01
    -> bearer SubjectConfirmationData InResponseTo=_req_A01
    -> SP kiểm tra và tạo Authentication nếu tất cả điều kiện đạt
~~~

Mối liên kết phải là **AuthnRequest thực đã được SP phát** và **ngữ cảnh request thực đã được lưu**, chứ không chỉ hai giá trị trên hai XML tag tình cờ bằng nhau.

### 7.2. IdP-initiated / unsolicited Response

Một số IdP có portal cho phép người dùng bấm biểu tượng ứng dụng để IdP gửi Response **khi SP chưa phát AuthnRequest**. Đây là **unsolicited Response**.

Theo Web Browser SSO Profile, **Response unsolicited không chứa Response.InResponseTo**, và bearer SubjectConfirmationData cũng **không được dùng InResponseTo để giả làm một request chưa hề tồn tại**. SP phải có **chính sách chấp nhận unsolicited** riêng: đối tác được phép, ACS, recipient, audience, thời gian, chữ ký, replay, xử lý RelayState, login CSRF và điểm điều hướng an toàn.

**Không áp dụng máy móc quy tắc “InResponseTo luôn bắt buộc trong mọi SAMLResponse”.** Quy tắc đúng là:

| Loại flow | SP đã có AuthnRequest đang chờ? | Response.InResponseTo / SubjectConfirmationData.InResponseTo |
| --- | --- | --- |
| **SP-initiated** | Có | **Phải khớp** ID của AuthnRequest gốc theo profile. |
| **IdP-initiated (unsolicited)** | Không | Theo profile, **không hiện diện**; SP phải quyết định có hỗ trợ/cho phép flow này không. |

**Giảm bề mặt tấn công:** nếu ứng dụng không cần IdP-initiated login, hãy **từ chối unsolicited Responses** theo khả năng cấu hình/thiết kế của provider và kiểm thử điều này. Không tắt kiểm tra InResponseTo của SP-initiated chỉ để làm một portal IdP hoạt động.

### 7.3. RelayState không phải InResponseTo

**RelayState** là tham số đi kèm SAML binding để giữ ngữ cảnh/điều hướng hoặc hỗ trợ tra cứu giao dịch, phụ thuộc implementation. **AuthnRequest.ID/InResponseTo** là ràng buộc SAML trong thông điệp.

- **RelayState** có thể bị trình duyệt chuyển tiếp hoặc ảnh hưởng trong các mô hình lưu trạng thái khác nhau; chỉ dùng nó như **một thành phần của cơ chế lưu ngữ cảnh được bảo vệ**.
- **InResponseTo** phải liên hệ đúng ID của AuthnRequest ban đầu.
- Không coi việc RelayState “giống một token bí mật” là đủ để xác thực SAML Response.
- Nếu RelayState được dùng để chọn URL quay về, phải giới hạn URL được phép nhằm tránh **open redirect**.

Lưu request qua **session gắn với trình duyệt** thường giúp kiểm soát login CSRF. Nếu dùng kho phân tán và tra cứu bằng RelayState hoặc InResponseTo, cần thiết kế **binding với browser/session, TTL, tính ngẫu nhiên, one-time consumption và replay prevention** rõ ràng.

## 8. Quy trình kiểm tra đúng theo thứ tự tư duy

Thứ tự kỹ thuật cụ thể nằm trong provider, phụ thuộc việc ký Response hay Assertion và bước giải mã. **Không tự viết validator** theo danh sách dưới; dùng framework/ thư viện SAML đã được kiểm thử. Danh sách này giúp hiểu các nhóm điều kiện SP phải bảo đảm **trước khi tạo Authentication**.

1. **Nhận đúng endpoint và binding:** ACS đang xử lý SAMLResponse cho registration/IdP dự kiến; kích thước payload, parser XML và transport được kiểm soát.
2. **Xác định nguồn tin cậy:** dựa vào RelyingPartyRegistration và metadata/chứng chỉ đã được quản trị, không dựa vào trường issuer do trình duyệt gửi mà không xác minh.
3. **Xác minh chữ ký** theo policy SP và mô hình ký Response/Assertion; xử lý encrypted Assertion khi cấu hình và kiểm tra điều kiện chữ ký tương ứng.
4. **Response-level validation:** issuer, status thành công, Destination, thời gian/đặc tính message và **Response.InResponseTo** cho SP-initiated.
5. **Assertion-level validation:** issuer, chữ ký hoặc sự bao phủ bảo mật được policy chấp nhận, **Conditions**, **AudienceRestriction**, các giới hạn thời gian, AuthnStatement.
6. **SubjectConfirmation:** kiểm tra phương thức **bearer**, **Recipient**, **NotOnOrAfter**, **InResponseTo**, tùy chọn Address và các ràng buộc khác nếu profile yêu cầu.
7. **Correlation + replay:** liên kết request đã lưu trong ngữ cảnh đúng, dùng request/response/assertion một lần theo policy; từ chối phản hồi lặp hoặc bị chuyển phiên.
8. **Tạo Authentication:** chỉ sau khi có kết quả hợp lệ, cấp local SecurityContext/session và ánh xạ authority của ứng dụng. Kiểm tra authorization cho từng tài nguyên nội bộ vẫn cần thiết.

**Tất cả điều kiện bảo mật cùng phải thỏa mãn theo profile.** Một chữ ký hợp lệ **không bỏ qua Recipient**, một Recipient đúng **không bỏ qua InResponseTo**, và một InResponseTo đúng **không bỏ qua signature/audience/expiry**.

### Hai tình huống tấn công cần hình dung

**Response bị chuyển sang ứng dụng khác.** IdP ký Assertion cho A; attacker cố gửi sang ACS của B. Nếu B chỉ xác minh chữ ký IdP mà không kiểm tra **Recipient/Audience**, nó có thể đăng nhập sai ứng dụng. Đây là lý do phải kiểm cả nơi nhận Assertion và định danh SP được phép dùng Assertion.

**Login CSRF / phản hồi không thuộc phiên.** Attacker khởi tạo login ở trình duyệt riêng, lấy Response hợp lệ của chính attacker rồi cố đẩy Response đó vào trình duyệt nạn nhân. Nếu SP chỉ tin chữ ký và NameID mà không gắn **InResponseTo với một request mà phiên nạn nhân đã khởi tạo**, nạn nhân có nguy cơ bị đăng nhập vào tài khoản attacker. Vì thế request correlation và session binding có ý nghĩa bảo mật riêng.

## 9. Spring Security Servlet thực hiện kiểm tra ở đâu?

Đối với SAML2 Service Provider, Spring Security cung cấp **saml2Login()**; thành phần xử lý chính gồm:

- **Saml2WebSsoAuthenticationRequestFilter**: tạo AuthnRequest và gửi tới IdP.
- **Saml2AuthenticationRequestRepository**: lưu ngữ cảnh AuthnRequest để đọc lại khi IdP gửi Response. Cấu hình mặc định phổ biến dùng **HttpSessionSaml2AuthenticationRequestRepository**.
- **Saml2WebSsoAuthenticationFilter**: nhận POST SAMLResponse tại ACS; chuyển sang AuthenticationConverter/AuthenticationManager.
- **Saml2AuthenticationTokenConverter**: xác định RelyingPartyRegistration và ngữ cảnh SAML Response; cách lookup có thể dùng request đã lưu, URL registrationId và issuer theo chiến lược được cấu hình.
- **OpenSAML authentication provider**: giải mã/xác minh Response và Assertion theo registration/trust/validation policy, sau đó tạo Authentication.

**Lưu ý về phiên bản:** Spring Security **6.x** có các API/provider dựa trên **OpenSAML 4** (và một số phiên bản 6.x hỗ trợ OpenSAML 5); tài liệu **Spring Security 7.x** trình bày **OpenSaml5AuthenticationProvider**. Khi tùy biến validator, **phải xem đúng phiên bản Spring Security/OpenSAML của dự án**, không sao chép import hay constructor từ tài liệu phiên bản khác. Phần lớn ứng dụng chỉ cần cấu hình đúng IdP và để các validation mặc định hoạt động; không nên thay toàn bộ AuthenticationManager khi không cần.

### Tại sao repository lưu AuthnRequest lại quan trọng?

Giả sử request có ID **_req_A01**. Spring phải có cách tìm lại **AuthnRequest gốc** sau khi browser đi qua IdP và quay lại ACS. Kho request lưu trong **HttpSession** giúp ràng buộc request tới phiên browser tương ứng, hỗ trợ chống login fixation/CSRF.

Những lỗi thường làm mất request gốc:

- Phiên browser bị mất do cookie SameSite, Secure, reverse proxy hoặc hostname không nhất quán.
- Session timeout trong lúc user đăng nhập/MFA tại IdP.
- Cluster nhiều Spring instances nhưng session chưa chia sẻ/định tuyến đúng.
- Người dùng mở nhiều tab, khởi động nhiều AuthnRequest song song, trong khi cơ chế lưu request tùy biến chỉ giữ một giao dịch.
- Kết quả callback đi đến registration khác hoặc ACS khác sau cấu hình IdP/proxy thay đổi.

**Cách xử lý đúng:** sửa session, request repository, cookie policy, reverse proxy và đăng ký IdP; đừng loại bỏ validation InResponseTo để che lỗi mất trạng thái.

### Authentication thành công không đồng nghĩa dùng lại SAMLResponse

SAMLResponse dùng để **thiết lập phiên** tại thời điểm callback. Sau đó ứng dụng thường có local session Spring Security riêng. Không lưu một SAMLResponse làm “cookie đăng nhập” để trình lại ở mọi HTTP request, và không dựa vào việc ID token/OAuth hay thông tin NameID tồn tại để bỏ các điều kiện SAML.

## 10. Ví dụ cấu hình tối thiểu phía Spring Security

Ví dụ thực hành dành cho **Spring Boot 3.3.5, Java 17**, sử dụng **IdP SAML thật**. Mục đích là để Spring Security **tự xác minh** các điều kiện SAML; không có custom code nào “bỏ qua” Recipient, InResponseTo hay chữ ký.

### 10.1. Maven dependencies

**pom.xml**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>saml-confirmation-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <repositories>
        <repository>
            <id>shibboleth-releases</id>
            <url>https://build.shibboleth.net/maven/releases/</url>
        </repository>
    </repositories>
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
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 10.2. Đăng ký đối tác IdP

**src/main/resources/application.yml**

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          corp:
            assertingparty:
              metadata-uri: ${SAML_IDP_METADATA_URI}
server:
  port: 8080
~~~

Đặt biến môi trường **SAML_IDP_METADATA_URI** thành metadata XML của một IdP thực tế, đáng tin cậy. Đăng ký SP ở IdP với **SP entityId/ACS** công khai khớp metadata ứng dụng. Dùng URL HTTPS khi triển khai thật. Nếu IdP đòi **signed AuthnRequest** hoặc mã hóa Assertion, cung cấp signing/decryption credentials của SP theo cấu hình Spring phù hợp; ví dụ tối giản không khai báo private key.

**registrationId = corp** xác định đối tác RP trong Spring, **không** phải subject/user ID.

### 10.3. Spring Boot application

**src/main/java/com/example/samlconfirmation/SamlConfirmationApplication.java**

~~~java
package com.example.samlconfirmation;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SamlConfirmationApplication {
    public static void main(String[] args) {
        SpringApplication.run(SamlConfirmationApplication.class, args);
    }
}
~~~

**src/main/java/com/example/samlconfirmation/SecurityConfig.java**

~~~java
package com.example.samlconfirmation;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated()
            )
            .saml2Login(Customizer.withDefaults())
            .saml2Metadata(Customizer.withDefaults());

        return http.build();
    }
}
~~~

**src/main/java/com/example/samlconfirmation/DemoController.java**

~~~java
package com.example.samlconfirmation;

import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.saml2.provider.service.authentication.Saml2AuthenticatedPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/")
    public String home() {
        return "SP ready";
    }

    @GetMapping("/me")
    public String me(@AuthenticationPrincipal Saml2AuthenticatedPrincipal principal) {
        return "NameID=" + principal.getName();
    }
}
~~~

Thiết lập biến môi trường, kiểm tra metadata IdP và chạy từ thư mục chứa **pom.xml**:

~~~bash
mvn spring-boot:run
~~~

**Kết quả kiểm tra hợp lệ:**

- **GET http://localhost:8080/** trả chính xác **SP ready**, không cần SAML login.
- **GET http://localhost:8080/saml2/metadata/corp** xuất **SP metadata XML** khi registration cấu hình thành công và endpoint được phép, giúp kiểm tra entityId và ACS của SP; không phải IdP metadata.
- **GET http://localhost:8080/saml2/authenticate/corp** tạo AuthnRequest để bắt đầu SAML login.
- **GET http://localhost:8080/me** khi chưa có phiên sẽ bắt đầu luồng login; nếu IdP phát hành Response/Assertion hợp lệ thì body dạng **NameID=<giá trị do IdP cấp>**. Giá trị subject không cố định.

Ứng dụng chỉ hoàn tất SSO khi có **IdP thật, trust certificate đúng, ACS/entityId đăng ký khớp**, IdP cấp Assertion với **Recipient, InResponseTo, expiry** và các yêu cầu khác hợp lệ. Đây là ví dụ dựa trên Spring Security 6.x; nếu triển khai phiên bản khác, giữ nguyên quy tắc giao thức và kiểm tra cấu hình/API theo tài liệu phiên bản đó.

**Không tự thêm controller xử lý POST ACS để gọi XML parser**. Spring Security/OpenSAML thực hiện việc xác minh SAML; mã ứng dụng nhận Authentication **sau** khi validation thành công.

## 11. Java 17: mô phỏng ba phép so sánh để ghi nhớ

Ví dụ **Java thuần**, có thể biên dịch/chạy độc lập, chỉ minh họa các điều kiện cơ bản **Recipient**, **InResponseTo**, **NotOnOrAfter** trong một SP-initiated flow. **Không được dùng đoạn này để xác thực SAML thực tế:** nó **không** giải mã SAML, không xác minh chữ ký, issuer, audience, response-level InResponseTo, XML schema, session binding, replay hay profile đầy đủ.

**ConfirmationRulesDemo.java**

~~~java
import java.time.Instant;

public class ConfirmationRulesDemo {
    private record Confirmation(
            String recipient,
            String inResponseTo,
            Instant notOnOrAfter) {}

    private static boolean matchesThreeFields(
            Confirmation data,
            String expectedAcs,
            String savedRequestId,
            Instant now) {

        return expectedAcs.equals(data.recipient())
                && savedRequestId.equals(data.inResponseTo())
                && now.isBefore(data.notOnOrAfter());
    }

    public static void main(String[] args) {
        String acs = "https://app.example.com/login/saml2/sso/corp";
        String requestId = "_req_A01";
        Instant now = Instant.parse("2026-11-07T09:00:00Z");
        Instant expiry = Instant.parse("2026-11-07T09:05:00Z");

        Confirmation valid = new Confirmation(acs, requestId, expiry);
        Confirmation wrongRecipient = new Confirmation(
                "https://other.example.com/login/saml2/sso/corp",
                requestId, expiry);
        Confirmation wrongRequest = new Confirmation(
                acs, "_req_OTHER", expiry);
        Confirmation expired = new Confirmation(acs, requestId, now);

        System.out.println("valid: "
                + matchesThreeFields(valid, acs, requestId, now));
        System.out.println("wrong recipient: "
                + matchesThreeFields(wrongRecipient, acs, requestId, now));
        System.out.println("wrong InResponseTo: "
                + matchesThreeFields(wrongRequest, acs, requestId, now));
        System.out.println("expired: "
                + matchesThreeFields(expired, acs, requestId, now));
    }
}
~~~

Biên dịch và chạy với JDK 17+:

~~~bash
javac ConfirmationRulesDemo.java
java ConfirmationRulesDemo
~~~

**stdout chính xác:**

~~~text
valid: true
wrong recipient: false
wrong InResponseTo: false
expired: false
~~~

Giải thích:

- **valid: true** nghĩa là **chỉ ba phép so sánh mô phỏng đều đạt**. Nó **không** có nghĩa một SAMLResponse thực đã an toàn để đăng nhập.
- **wrong recipient** sai vì Assertion được gửi cho ACS khác.
- **wrong InResponseTo** sai vì ID không khớp request ID đã lưu.
- **expired** sai vì thời điểm hiện tại **bằng** NotOnOrAfter, mà điều kiện cần là **trước** thời điểm ấy.

Trong ứng dụng thật, đừng lấy output boolean trên làm căn cứ cấp SecurityContext; phải để Spring Security/OpenSAML thực hiện đầy đủ validation.

## 12. Bảng thử nghiệm bảo mật và kết quả kỳ vọng

Làm các phép thử **trong sandbox có IdP/SP kiểm soát được**, tạo các SAMLResponse **được ký hợp lệ bằng khóa thử nghiệm** khi muốn kiểm tra riêng một điều kiện. Nếu sửa tay XML đã ký thì chữ ký sai sẽ khiến bài test chỉ chứng minh rằng **signature validation** hoạt động, không đo được validator Recipient/InResponseTo. Không đưa private key test vào hệ thống production.

| # | Kịch bản | Kết quả mong đợi ở SP |
| --- | --- | --- |
| 1 | Signature/issuer/audience đúng; Recipient = ACS; InResponseTo ở cả Response và SCD = request đang chờ; thời gian hợp lệ | **Chấp nhận**, nếu tất cả validation còn lại cũng đạt. |
| 2 | Recipient là ACS của **SP khác** | **Từ chối** subject confirmation. |
| 3 | Recipient có hostname đúng nhưng path ACS khác | **Từ chối**. |
| 4 | Recipient dùng **http** thay vì **https** công khai của SP | **Từ chối** nếu không khớp ACS hợp lệ. |
| 5 | Response.InResponseTo không khớp AuthnRequest.ID | **Từ chối** SP-initiated response. |
| 6 | Response.InResponseTo đúng nhưng SCD.InResponseTo sai | **Từ chối** bearer confirmation không tương ứng request. |
| 7 | SCD.InResponseTo đúng nhưng Response.InResponseTo sai | **Từ chối** response không tương ứng request. |
| 8 | InResponseTo trỏ tới request **đã hết hạn/đã tiêu thụ** | **Từ chối** theo chính sách correlation/replay. |
| 9 | NotOnOrAfter **đã qua** hoặc thời gian bằng đúng mốc kết thúc, không xét skew | **Từ chối** confirmation. |
| 10 | SCD thiếu Recipient hoặc NotOnOrAfter của bearer Web Browser SSO | **Từ chối** do không đủ điều kiện profile. |
| 11 | Có NotBefore trong bearer SCD | **Không phù hợp Web Browser SSO bearer profile**; IdP cần sửa message. |
| 12 | Destination sai nhưng Recipient đúng | **Từ chối** Response do Destination không hợp lệ. |
| 13 | Audience không chứa SP entityId nhưng Recipient đúng | **Từ chối** Assertion do không được cấp cho SP này. |
| 14 | IdP-initiated unsolicited Response **không có InResponseTo** | Chỉ có thể xem xét nếu RP **chủ động cho phép unsolicited** và các kiểm tra khác đều đạt; nếu policy cấm thì **từ chối**. |
| 15 | IdP-initiated unsolicited Response tự gắn InResponseTo giả | **Từ chối** theo profile/policy; không tạo request đã không tồn tại. |
| 16 | Hai bearer confirmations: một hợp lệ, một không | Theo profile/errata, **một confirmation hợp lệ có thể đủ cho Assertion tương ứng**; vẫn kiểm tra các quy tắc khác và mỗi Assertion riêng. |
| 17 | Response/Assertion lặp lại sau khi đã dùng để tạo session | **Từ chối phát lại** theo cơ chế correlation/one-time/replay đang triển khai. |
| 18 | Spring SP chạy nhiều instance, callback không tìm được AuthnRequest vì không chia sẻ session | **Không chấp nhận response**; sửa session/repository. |
| 19 | IdP phát Response hợp lệ nhưng chữ ký không xác minh được theo trust SP | **Từ chối**, dù ba trường Recipient/InResponseTo/expiry đều đúng. |

**Không đặt mục tiêu “sửa để mọi case đều login được”.** Kiểm thử âm tính thành công khi SP **từ chối đúng** trường hợp sai.

### Thử ở nhiều tab và nhiều IdP

Đăng nhập cùng lúc hai tab có thể tạo hai AuthnRequest **_req_A01** và **_req_A02**. Mỗi Response chỉ được ràng buộc với request tương ứng; nếu framework/repository có giới hạn về nhiều request đồng thời, cần biết và kiểm thử hành vi thật, không cho phép callback A02 tự ghép vào request A01.

Nếu ứng dụng hỗ trợ nhiều IdP, ID của request phải được xác minh cùng **registration/IdP và ACS đúng**. Không được thấy Response mang issuer IdP X nhưng lại tin chứng chỉ IdP Y, hoặc lấy thông tin đăng ký từ một giá trị URL do attacker tùy ý chọn.

## 13. Chẩn đoán lỗi trong Spring Security

| Dấu hiệu | Nguyên nhân có thể | Hướng kiểm tra an toàn |
| --- | --- | --- |
| “Invalid Recipient” hoặc validation SubjectConfirmation thất bại | ACS trong Assertion không khớp SP URL/registration, host/port/path sai | Đối chiếu **Recipient**, ACS trong SP metadata, IdP app configuration và URL public của proxy. |
| “InResponseTo mismatch”, “No matching AuthnRequest” | Request đã lưu bị mất, ID sai, session/cookie không còn hoặc response unsolicited | Kiểm tra request repository, phiên browser, TTL và thứ tự callback; không tắt correlation. |
| Login sau MFA dài thì thất bại | Session request chờ hoặc NotOnOrAfter đã hết hạn | So timestamp UTC, timeout và chính sách IdP; đồng bộ NTP. |
| Chỉ lỗi khi chạy sau HTTPS reverse proxy | Spring sinh ACS nội bộ HTTP/hostname/port khác | Sửa forwarded headers, base URL công khai, SP metadata và cấu hình IdP. |
| Lỗi ở tab thứ hai | Hai request song song bị ghi đè/nhầm ID trong custom storage | Kiểm tra cách repository quản lý nhiều yêu cầu và liên kết phiên. |
| Assertion ký hợp lệ nhưng SP vẫn từ chối | Recipient, audience, issuer, InResponseTo, Conditions hoặc SCD expiration sai | Kiểm tra **từng nhóm validation**, đừng suy ra signature đúng thì login phải được. |
| Chỉ IdP portal launch lỗi | Chưa hỗ trợ unsolicited hoặc cấu hình RelayState/ACS sai | Chốt yêu cầu IdP-initiated, đánh giá login CSRF/replay, cấu hình rõ ràng. |
| SAMLResponse gửi lại lần thứ hai bị từ chối | Request đã được tiêu thụ hoặc phản hồi bị nhận diện là replay | Đây thường là **hành vi bảo mật mong muốn**. |
| SecurityContext có principal nhưng user không có quyền nghiệp vụ | SAML authentication xong, role/authority không ánh xạ đúng | Xử lý **authorization** riêng; không sửa SubjectConfirmation để cấp quyền. |

### Log thế nào để không rò rỉ dữ liệu?

Trong môi trường phát triển, log các thông tin đã **làm sạch** như: registrationId, correlation ID nội bộ, loại lỗi validation, mã lỗi, hostname ACS dự kiến/thực tế khi thích hợp. Có thể lưu **ID giao dịch** theo chính sách bảo mật, nhưng tránh log toàn bộ raw SAMLResponse, NameID nhạy cảm, Attributes cá nhân, cookie session, private key, chữ ký hoặc dữ liệu xác thực. Không gửi Base64 Assertion vào chat/ticket công khai.

Khi phân tích lỗi, **không** sửa tệp XML production rồi “bỏ qua chữ ký để xem chạy được không”. Test môi trường riêng với IdP thử nghiệm có thể phát hành response được ký đúng cho từng negative case.

## 14. Các nhầm lẫn phổ biến cần tránh

1. **“NameID đúng nên login được.”** Sai: NameID chỉ định danh Subject, còn SubjectConfirmation, chữ ký, audience, recipient, correlation và thời gian phải hợp lệ.
2. **“Recipient là URL IdP.”** Sai: trong bearer Web Browser SSO, Recipient trỏ tới **ACS của SP**. IdP SSO URL là đích của AuthnRequest, không phải đích Assertion được gửi về.
3. **“Audience và Recipient giống nhau.”** Sai: Audience thường là **SP entityId**, Recipient là **ACS URL**.
4. **“Response.InResponseTo đúng thì không cần SCD.InResponseTo.”** Sai: đây là hai lớp ràng buộc khác nhau; SP-initiated profile yêu cầu đối chiếu tương quan chính xác.
5. **“InResponseTo phải có cả với IdP-initiated login.”** Sai: unsolicited Response không có AuthnRequest gốc, nên phải có chính sách riêng thay vì tự tạo ra ID tưởng tượng.
6. **“RelayState có thể thay InResponseTo.”** Sai: RelayState hỗ trợ ngữ cảnh chuyển tiếp nhưng không phải bằng chứng thay thế cho request correlation và signature/trust.
7. **“Chỉ cần kiểm tra chữ ký là đủ.”** Sai: Assertion có chữ ký hợp lệ nhưng gửi nhầm SP, quá hạn hoặc không thuộc giao dịch hiện tại vẫn phải bị từ chối.
8. **“NotOnOrAfter là timeout của JSESSIONID.”** Sai: mốc này giới hạn quyền trình bearer confirmation, không phải vòng đời local web session.
9. **“Có NotBefore trong mọi SCD là tốt hơn.”** Sai: Web Browser SSO bearer profile **cấm NotBefore trong bearer SubjectConfirmationData**, dù Conditions.NotBefore vẫn hợp lệ theo giao thức.
10. **“Mất session thì cứ bỏ kiểm tra InResponseTo.”** Sai: làm vậy có thể làm mất bảo vệ chống login CSRF/correlation; phải sửa nơi lưu request và cookie/cluster.
11. **“Một SAMLResponse có nhiều confirmations thì chấp nhận cái đầu.”** Sai: phải đánh giá confirmation theo phương thức và điều kiện; theo errata, một bearer confirmation hợp lệ có thể đủ cho Assertion đó, nhưng không tùy tiện bỏ kiểm tra Assertion khác.
12. **“Tự so Recipient bằng string là đã tích hợp SAML.”** Sai: so ba trường chỉ là phần rất nhỏ. Phải dùng SAML library/validator được duy trì và đúng profile.

## 15. Câu hỏi thực hành

**Câu 1.** SP A có ACS **https://a.example.com/login/saml2/sso/corp**, còn IdP gửi Assertion với Recipient **https://b.example.com/login/saml2/sso/corp**. Chữ ký IdP hợp lệ. A có nên login?  
**Trả lời:** **Không**. Recipient ràng buộc Assertion với ACS B, không phải A. Chữ ký hợp lệ không thay đổi đối tượng nhận.

**Câu 2.** SP gửi AuthnRequest.ID **_req_123**, Response.InResponseTo là **_req_123**, còn SubjectConfirmationData.InResponseTo là **_req_999**. Có thể lấy Response.InResponseTo làm giá trị ưu tiên không?  
**Trả lời:** **Không**. Trong SP-initiated Web Browser SSO, bearer confirmation phải liên hệ đúng request đã lưu. Confirmation có InResponseTo sai không đáp ứng điều kiện xác nhận subject.

**Câu 3.** Người dùng bấm app icon tại IdP portal; SP chưa từng gửi AuthnRequest. Có nên tạo một ID giả ở SP để khớp InResponseTo?  
**Trả lời:** **Không**. Đó là unsolicited/IdP-initiated flow, cần chính sách hỗ trợ riêng. Nếu không có nhu cầu/đánh giá bảo mật, nên từ chối.

**Câu 4.** Recipient khớp ACS, InResponseTo khớp AuthnRequest, nhưng NotOnOrAfter đã qua 10 phút. Có chấp nhận không?  
**Trả lời:** **Không**. SubjectConfirmationData đã hết hạn. Cần xem đồng hồ, profile và khả năng cấp lại Response, không tăng skew tùy tiện.

**Câu 5.** Reverse proxy cho SP chạy HTTP nội bộ nhưng URL công khai HTTPS. IdP gửi Recipient HTTPS, Spring xác định ACS HTTP. Sửa gì trước?  
**Trả lời:** Sửa **forwarded headers/base URL/metadata/IdP registration** để SP và IdP dùng cùng ACS công khai. Không bỏ Recipient validation.

**Câu 6.** Có thể viết một Java method so ba chuỗi rồi trực tiếp đưa user vào SecurityContext không?  
**Trả lời:** **Không**. Thao tác đó thiếu signature/trust, issuer, audience, Conditions, response validation, chống replay, parser an toàn và liên kết phiên. Dùng Spring Security SAML2 SP/OpenSAML theo cấu hình hợp lệ.

## 16. Ghi nhớ và nguồn chuẩn

- **SubjectConfirmation** trả lời: “Có thể xác nhận subject khi Assertion này được trình trong hoàn cảnh nào?”
- **Recipient** trả lời: “Bearer Assertion này được phép tới **ACS của SP nào**?”
- **InResponseTo** trả lời: “Response/confirmation này thuộc **AuthnRequest nào do SP đã phát**?”
- Với **SP-initiated Web Browser SSO**, Response.InResponseTo và bearer SubjectConfirmationData.InResponseTo phải liên kết đúng **AuthnRequest.ID** đã lưu; với **unsolicited**, không có request gốc và cần policy riêng.
- **NotOnOrAfter** giới hạn thời gian bearer confirmation; phải tiếp tục kiểm tra signature, issuer, Destination, AudienceRestriction, Conditions, replay và tính đúng phiên.
- Trong Spring Security, giữ **Saml2AuthenticationRequestRepository**/session/cookie nhất quán, cấu hình **RelyingPartyRegistration**/ACS public chính xác và để **OpenSAML provider** thực hiện validation. Không khắc phục lỗi bằng cách tắt kiểm tra an ninh.

**Tài liệu tham khảo:**

1. [OASIS SAML 2.0 Profiles](https://docs.oasis-open.org/security/saml/v2.0/saml-profiles-2.0-os.pdf), mục **4.1 Web Browser SSO Profile**, nhất là **4.1.4.3 Response Processing Rules** và **4.1.5 Unsolicited Responses**.
2. [OASIS SAML 2.0 Approved Errata](https://docs.oasis-open.org/security/saml/v2.0/sstc-saml-approved-errata-2.0.html): giải thích bổ sung cách đánh giá nhiều bearer SubjectConfirmation và nhiều Assertion.
3. [Spring Security – SAML2 Login Overview](https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html): SP/RP, các filter và quá trình xác minh.
4. [Spring Security – Producing AuthnRequests](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication-requests.html): Saml2AuthenticationRequestRepository, session và bảo vệ correlation.
5. [Spring Security – Authenticating Responses](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html): response/assertion validator, correlation và cơ chế xử lý lỗi. Xem **tài liệu phiên bản khớp dependency** trước khi tùy biến API.

**Nguyên tắc cuối:** một người được IdP xác thực không có nghĩa **mọi SAML Assertion** nói về người đó đều được chấp nhận. SP chỉ cho phép đăng nhập khi Assertion được phát hành **cho đúng SP, tới đúng ACS, trong đúng giao dịch, vào đúng thời gian và theo đúng quan hệ tin cậy**.
