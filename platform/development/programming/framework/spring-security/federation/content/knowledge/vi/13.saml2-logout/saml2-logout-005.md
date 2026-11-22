# NameID, SessionIndex và xác định phiên cần kết thúc trong SAML 2.0 Single Logout

Trong **SAML 2.0 Single Logout (SLO)**, một `LogoutRequest` không chỉ có nghĩa “người dùng muốn thoát”. Bên nhận cần biết **đúng chủ thể nào**, **phiên đăng nhập liên kết nào** và **những phiên ứng dụng nào tương ứng** cần bị kết thúc. Hai dữ kiện cốt lõi để xác định phạm vi là **`NameID`** (định danh principal trong quan hệ liên kết) và **`SessionIndex`** (định danh phiên được Identity Provider/Session Authority gắn vào `AuthnStatement`).

Một sai lầm có thể gây hậu quả bảo mật ở cả hai hướng: chỉ xóa **một** session trình duyệt trong khi yêu cầu logout bao trùm nhiều session, hoặc xóa **tất cả** session có cùng email dù LogoutRequest chỉ yêu cầu kết thúc một phiên cụ thể. Bài học này giải thích quy tắc SAML, cách lưu thông tin từ lúc login, cơ chế match phiên trong hệ thống có nhiều nút và cách áp dụng vào **Spring Security Servlet**.

**Kết luận trước:** không dùng một mình `NameID`, `SessionIndex`, email hay cookie `JSESSIONID` để quyết định hủy phiên. Cần dựa vào **issuer/IdP đã xác minh + registration/SP + NameID và thuộc tính phạm vi + danh sách SessionIndex (nếu có) + chính sách SLO**, rồi mới xác định các local session cần thu hồi.

## 1. Phân biệt các đối tượng định danh và phiên

| Dữ kiện | Xuất hiện ở đâu? | Ý nghĩa | Không đồng nghĩa với |
| --- | --- | --- | --- |
| **`NameID`** | SAML assertion `Subject`; `LogoutRequest` (hoặc `BaseID`/`EncryptedID`). | Định danh principal được IdP và SP hiểu trong phạm vi federation. | Email, local account ID, Servlet session ID. |
| **`NameID@Format`** | Thuộc tính định danh. | Cách diễn giải định danh: `persistent`, `transient`, `emailAddress`, `unspecified`... | Đảm bảo giá trị không bao giờ thay đổi. |
| **`NameQualifier`, `SPNameQualifier`** | Thuộc tính tùy chọn của `NameID`. | Phạm vi nhà cung cấp định danh và SP mà một NameID được hiểu trong đó. | Các tham số trang trí có thể tùy ý bỏ qua. |
| **`AuthnStatement@SessionIndex`** | Assertion do IdP phát khi login. | Chỉ số phiên xác thực liên kết do session authority quản lý; dùng trong SLO. | `Assertion@ID`, `Response@ID`, `AuthnRequest@ID` hoặc `JSESSIONID`. |
| **`LogoutRequest/SessionIndex`** | Một hay nhiều phần tử `<samlp:SessionIndex>` trong thông điệp logout. | Chỉ rõ các phiên liên kết muốn kết thúc khi profile yêu cầu/chấp nhận chỉ số. | Tên tài khoản hoặc ID giao dịch logout. |
| **`LogoutRequest@ID`** | Thuộc tính của chính LogoutRequest. | Định danh giao dịch logout để correlation/replay; `LogoutResponse@InResponseTo` trỏ về đây. | SessionIndex của phiên đăng nhập. |
| **`HttpSession` của SP** | Máy chủ ứng dụng Servlet/Spring Session. | Phiên HTTP của một trình duyệt với SP. | Phiên SSO tại IdP. |
| **Session cookie tại IdP** | Trình duyệt và IdP. | Phiên SSO do IdP quản lý. | Cookie hay session ID do SP sở hữu. |

**Ví dụ:** hai trình duyệt của cùng một người dùng có thể có hai `JSESSIONID` khác nhau nhưng cùng một `SessionIndex` do IdP gắn vào hai lần tham gia cùng phiên SSO, tùy mô hình của IdP. Ngược lại, người đó có thể xác thực lại với hai phiên IdP và nhận hai SessionIndex khác nhau. Vì thế một `SessionIndex` có thể ánh xạ tới **nhiều** local HTTP sessions tại cùng SP, còn một `NameID` có thể liên quan tới nhiều SessionIndex.

Một LogoutRequest cần được diễn giải theo **quan hệ phiên liên kết**, không phải chỉ một request HTTP callback.

## 2. Dữ liệu SLO xuất phát từ lúc SAML login

SP chỉ có thể kết thúc đúng phiên nếu lúc nhận `SAMLResponse` nó đã giữ lại thông tin cần cho SLO.

### 2.1. `AuthnStatement@SessionIndex` được phát từ assertion

Ví dụ rút gọn, chỉ cho thấy cấu trúc định danh và session (đã lược chữ ký, conditions và các trường bắt buộc khác nên **không phải assertion hợp lệ để đăng nhập thật**):

~~~xml
<saml:Assertion
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    ID="_assertion-42" Version="2.0"
    IssueInstant="2026-11-07T03:00:00Z">
  <saml:Issuer>urn:example:idp:corporate</saml:Issuer>
  <saml:Subject>
    <saml:NameID
        Format="urn:oasis:names:tc:SAML:2.0:nameid-format:persistent"
        NameQualifier="urn:example:idp:corporate"
        SPNameQualifier="urn:example:sp:portal">principal-83917</saml:NameID>
  </saml:Subject>
  <saml:AuthnStatement
      AuthnInstant="2026-11-07T02:58:00Z"
      SessionIndex="idp-session-7e3"
      SessionNotOnOrAfter="2026-11-07T11:00:00Z">
    <saml:AuthnContext>
      <saml:AuthnContextClassRef>
        urn:oasis:names:tc:SAML:2.0:ac:classes:PasswordProtectedTransport
      </saml:AuthnContextClassRef>
    </saml:AuthnContext>
  </saml:AuthnStatement>
</saml:Assertion>
~~~

Phân biệt các mốc:

- `Assertion@ID="_assertion-42"`: ID của assertion, liên quan chống replay assertion, **không** phải SessionIndex.
- `AuthnStatement@SessionIndex="idp-session-7e3"`: chỉ số phiên được dùng khi định danh phiên SLO.
- `SessionNotOnOrAfter`: giới hạn vòng đời phiên xác thực được tuyên bố, **không** phải ID phiên, cũng không đồng nghĩa thời điểm SP bắt buộc xóa mọi local cookie.
- `Subject/NameID`: principal theo quan hệ IdP/SP; cần lưu cả format và qualifiers có ý nghĩa.

SAML Core cho phép `SessionIndex` trong `AuthnStatement` là tùy chọn theo cấu trúc chung. Tuy nhiên, theo **Web Browser SSO Profile được chỉnh lý trong OASIS Errata 05**, nếu IdP hỗ trợ Single Logout, `AuthnStatement` có liên quan phải có `SessionIndex` để SP có thể yêu cầu logout đúng phiên. **Không được suy luận rằng mọi assertion trên Internet đều có SessionIndex**; phải kiểm tra khả năng/profile và cách IdP phát hành thực tế.

### 2.2. SP cần lưu gì sau khi xác thực thành công?

Một hồ sơ phiên liên kết có thể có dạng:

~~~text
SamlSessionContext
  registrationId      = corporate
  trustedIdpEntityId  = urn:example:idp:corporate
  spEntityId          = urn:example:sp:portal
  nameId.value        = principal-83917
  nameId.format       = urn:oasis:names:tc:SAML:2.0:nameid-format:persistent
  nameId.nameQualifier   = urn:example:idp:corporate
  nameId.spNameQualifier = urn:example:sp:portal
  samlSessionIndex    = idp-session-7e3
  localAccountId      = user-42
  httpSessionId       = sp-session-A
  authenticatedAt     = 2026-11-07T03:00:00Z
  sessionActive       = true
~~~

Thông tin phải đến từ **SAML assertion đã được validator xác minh**, không phải tự đọc XML trước khi kiểm tra signature hoặc lấy từ HTTP query/RelayState. Khi không có SessionIndex, ghi rõ `missing` và chính sách xử lý tương ứng; **không chế ra một SessionIndex ngẫu nhiên** rồi gửi cho IdP như thể IdP từng phát hành nó.

Để hỗ trợ người dùng có nhiều trình duyệt hoặc nhiều pod Spring Boot, nên lưu ở shared session registry với các chỉ mục:

- Theo **local HTTP session ID** để thu hồi chính xác một session.
- Theo **(registration, trusted issuer, canonical NameID, SessionIndex)** để tìm mọi local session liên quan một phiên SAML.
- Theo **(registration, trusted issuer, canonical NameID)** để tìm các phiên liên quan principal khi nhận LogoutRequest hợp lệ **không có SessionIndex từ session authority**, theo phạm vi cho phép.
- Theo **local account ID** để thu hồi tất cả phiên vì chính sách khóa tài khoản (đây là nghiệp vụ khác SAML SLO).

Bảng nên bảo đảm namespace theo môi trường/tenant và tránh trùng `NameID` giữa hai IdP. Dữ liệu định danh nhạy cảm phải được bảo vệ truy cập, có TTL/cleanup nhất quán với session và được loại bỏ khi hủy phiên. Session index nên được lưu nguyên giá trị cần so khớp, không tự chuyển sang chữ hoa/thường hoặc trim nếu giao thức không cho phép.

## 3. LogoutRequest chứa NameID và SessionIndex như thế nào?

Theo **SAML Core §3.7.1**, `LogoutRequest` cần **một trong** `BaseID`, `NameID` hoặc `EncryptedID` để xác định principal; `SessionIndex` có thể xuất hiện **0 hoặc nhiều lần** ở tầng schema.

Ví dụ **SP-initiated LogoutRequest** nhằm vào một phiên IdP:

~~~xml
<samlp:LogoutRequest
    xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    ID="_logout-request-901"
    Version="2.0"
    IssueInstant="2026-11-07T03:30:00Z"
    NotOnOrAfter="2026-11-07T03:35:00Z"
    Destination="https://idp.example.org/saml/slo">
  <saml:Issuer>urn:example:sp:portal</saml:Issuer>
  <saml:NameID
      Format="urn:oasis:names:tc:SAML:2.0:nameid-format:persistent"
      NameQualifier="urn:example:idp:corporate"
      SPNameQualifier="urn:example:sp:portal">principal-83917</saml:NameID>
  <samlp:SessionIndex>idp-session-7e3</samlp:SessionIndex>
</samlp:LogoutRequest>
~~~

Ví dụ **IdP-initiated LogoutRequest** cùng principal nhưng yêu cầu nhiều phiên:

~~~xml
<samlp:LogoutRequest
    xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    ID="_logout-request-902"
    Version="2.0"
    IssueInstant="2026-11-07T04:00:00Z"
    Destination="https://sp.example.org/logout/saml2/slo">
  <saml:Issuer>urn:example:idp:corporate</saml:Issuer>
  <saml:NameID
      Format="urn:oasis:names:tc:SAML:2.0:nameid-format:persistent"
      NameQualifier="urn:example:idp:corporate"
      SPNameQualifier="urn:example:sp:portal">principal-83917</saml:NameID>
  <samlp:SessionIndex>idp-session-7e3</samlp:SessionIndex>
  <samlp:SessionIndex>idp-session-9f2</samlp:SessionIndex>
</samlp:LogoutRequest>
~~~

Đây là XML giải thích trường, **chưa có chữ ký/cơ chế bảo vệ binding** nên không thể dùng như LogoutRequest thực trong môi trường production. Thông điệp thực còn phải được bảo vệ phù hợp với binding và mối quan hệ tin cậy.

**Thứ tự ý nghĩa:**
1. `Issuer`: bên **phát hành yêu cầu logout**; xác minh xem có đúng đối tác/role đã đăng ký không.
2. `NameID` (cùng format/qualifiers): định danh **đúng principal** trong phạm vi federation.
3. Mỗi `SessionIndex`: chọn một phiên SAML thuộc principal đó. Nhiều chỉ số có nghĩa yêu cầu nhiều phiên, không phải request bị lỗi.
4. `LogoutRequest@ID`, `IssueInstant`, `NotOnOrAfter`, `Destination` và chữ ký: bảo vệ/giới hạn **giao dịch logout**, không phải khóa định danh phiên HTTP.

### 3.1. Quy tắc quan trọng của OASIS Errata 05 (E38)

Phải phân biệt **Session Participant** (thường là SP) và **Session Authority** (thường là IdP):

| Bên gửi LogoutRequest | Quy tắc SessionIndex trong SAML SLO Profile |
| --- | --- |
| **SP / session participant** | **MUST include ít nhất một `SessionIndex`** khi gửi yêu cầu logout phiên liên kết. |
| **IdP / session authority** hoặc bên được ủy quyền hợp lệ | **MAY không gửi SessionIndex** để biểu thị việc kết thúc **tất cả phiên áp dụng được của principal**. |
| Bất kỳ bên nào gửi một/many SessionIndex | Chỉ xử lý **những phiên khớp chỉ số**, trong phạm vi issuer, principal, registration và chính sách. |

Điểm dễ nhầm là **schema của phần tử cho phép 0 SessionIndex**, nhưng **profile đặt yêu cầu chặt hơn cho SP là session participant**. Nếu SP thiếu SessionIndex, không được tùy tiện coi đây là lệnh “logout mọi nơi”. Cần ghi nhận thiếu dữ liệu, kiểm tra khả năng SLO/phiên được lưu, và hoặc tạo LogoutRequest đúng, hoặc chỉ thực hiện **local logout** với trạng thái/hướng dẫn trung thực.

Ngược lại, **IdP đã được xác minh ở vai trò session authority** có thể gửi LogoutRequest không có SessionIndex; theo profile điều đó yêu cầu kết thúc **mọi phiên liên quan principal trong phạm vi tin cậy của yêu cầu**, không phải toàn bộ phiên của tất cả tài khoản trên SP hay toàn tổ chức.

### 3.2. NameID không phải chỉ một chuỗi text

`NameID` có thể có `Format`, `NameQualifier`, `SPNameQualifier`, `SPProvidedID`. Những giá trị này mang ngữ nghĩa định danh/phạm vi. Ví dụ:

~~~text
Value           = principal-83917
Format          = ...:nameid-format:persistent
NameQualifier   = urn:example:idp:corporate
SPNameQualifier = urn:example:sp:portal
~~~

Đừng chỉ so `NameID.value` với email local account: một IdP khác có thể dùng cùng chuỗi, hoặc cùng IdP cấp định danh khác nhau theo SP/tenant. Ngược lại, nếu NameID là **transient**, nó có thể thay đổi giữa các lần login; dùng email để “sửa” việc không match có thể dẫn tới logout nhầm người.

Cần có bộ **canonical identity matching theo hợp đồng IdP/SP**: so format và qualifiers với quy tắc được hai bên thống nhất, có namespace của issuer/registration, và giữ liên hệ NameID với local session tại thời điểm SAML login. Không tự hạ mức so khớp khi không nhận diện được NameID.

Với `EncryptedID`, giải mã bằng khóa private phù hợp **sau khi kiểm tra chính sách và chữ ký/nguồn**, rồi so với danh tính phiên đã lưu. Không log plaintext NameID, assertion XML hoặc các thông tin nhạy cảm của người dùng.

## 4. Bảng quyết định: chính xác phiên nào phải bị kết thúc?

Giả định SP đang có năm local sessions:

| Local HttpSession | Registration / IdP | NameID đã xác minh | SAML SessionIndex |
| --- | --- | --- | --- |
| `browser-A` | `corporate` / IdP-X | `principal-83917` | `idx-01` |
| `browser-B` | `corporate` / IdP-X | `principal-83917` | `idx-02` |
| `browser-C` | `corporate` / IdP-X | `principal-other` | `idx-01` |
| `browser-D` | `partner` / IdP-Y | `principal-83917` | `idx-01` |
| `browser-E` | `corporate` / IdP-X | `principal-83917` | `idx-01` |

`browser-A` và `browser-E` có thể là hai phiên HTTP khác nhau nhưng tham gia **cùng phiên SAML `idx-01`**.

| LogoutRequest đã được **xác minh** | Local session nên nhắm đến | Giải thích |
| --- | --- | --- |
| IdP-X, đúng NameID, `SessionIndex=idx-01`. | **A, E** | Cùng registration/issuer, NameID và SessionIndex. |
| IdP-X, đúng NameID, `SessionIndex=idx-02`. | **B** | Không được xóa A/E vì thuộc phiên SAML khác. |
| IdP-X, đúng NameID, indexes `idx-01`, `idx-02`. | **A, B, E** | Hợp của những phiên match, không xóa C/D. |
| IdP-X là **session authority đáng tin**, cùng NameID, **không có SessionIndex**. | **A, B, E** | Kết thúc mọi phiên liên quan principal trong đúng registration/issuer. |
| Một session participant gửi request **không có SessionIndex**. | **Từ chối xử lý như lệnh all-sessions** | Không đáp ứng SLO profile dành cho session participant. |
| IdP-X, NameID khác, `idx-01`. | **C** nếu đúng NameID đó | Index trùng không được dẫn tới xóa người khác. |
| IdP-Y, `principal-83917`, `idx-01`. | **D** | Cùng text NameID/index nhưng khác registration/issuer. |
| IdP-X, đúng NameID, `idx-unknown`. | **Không có session match** | Không được fallback thành “logout tất cả”. |

**Không bao giờ:** dùng một `SessionIndex` đơn lẻ để `DELETE FROM sessions WHERE session_index = ?` nếu bảng chứa nhiều IdP/SP; dùng tên người dùng/email để xóa mọi phiên khi request có index cụ thể; hoặc mặc nhiên diễn giải “không thấy SessionIndex” là “mọi phiên” bất kể bên phát hành.

### 4.1. Nhiều SessionIndex trong cùng yêu cầu

`LogoutRequest` cho phép nhiều `<SessionIndex>`. Thuật toán đúng về mặt phạm vi là:

~~~text
if issuer + registration + NameID không được xác minh:
    REJECT

if SessionIndex list không rỗng:
    targets = tất cả local sessions cùng scoped identity
              AND sessionIndex thuộc danh sách
else if requester là trusted Session Authority
        AND policy cho phép all applicable sessions:
    targets = tất cả local sessions của scoped identity
else:
    REJECT hoặc xử lý theo policy lỗi giao thức

revoke targets qua session store có thể thu hồi đa nút
audit outcome, gửi LogoutResponse đúng status
~~~

Trường hợp `targets` rỗng **không có nghĩa** nên hủy tất cả: có thể phiên đã hết hạn, bị thu hồi trước đó, NameID thay đổi hoặc request sai. Phải xác minh giao dịch và trả status/ghi log theo chính sách chứ không mở rộng phạm vi tự động.

### 4.2. SessionIndex không nhất thiết tương ứng một HttpSession

Một phiên IdP có thể được nhiều tab/trình duyệt/service node liên kết; một người dùng có thể có nhiều session tại SP cùng hoặc khác SAML index tùy lần login. Mô hình lưu trữ cần **một-nhiều**, không bắt buộc `UNIQUE(saml_session_index)` trên bảng HTTP session. Nếu SP chỉ nhớ một mapping `SessionIndex → JSESSIONID`, nó có thể hủy một phiên và bỏ sót các phiên khác được tạo bằng cùng SAML session.

Ngược lại, **`SessionIndex` không có ý nghĩa toàn cục**: phải gắn với issuer/NameID/registration để tránh collision.

## 5. RP-initiated logout: khi SP chủ động yêu cầu IdP kết thúc phiên

**Relying Party (RP)** là SP/ứng dụng đang cho người dùng sử dụng dịch vụ. Khi người dùng nhấn Logout, cần biết mục tiêu là **local logout** hay **federated SLO**:

~~~text
User -- POST /logout --> SP
      |
      +--> Local logout:
      |      hủy phiên HTTP của ứng dụng
      |      không yêu cầu IdP/xác nhận các SP khác logout
      |
      +--> RP-initiated SLO:
             lấy SAML identity context của phiên hiện tại
             hủy local session theo chính sách
             tạo LogoutRequest có NameID + SessionIndex phù hợp
             ký/bảo vệ thông điệp theo binding
             gửi tới IdP SingleLogoutService
             chờ LogoutResponse và xác minh
             hoàn tất flow / báo kết quả
~~~

### 5.1. Lấy đúng NameID và SessionIndex từ login gốc

RP-initiated SLO cần biết `Saml2AuthenticatedPrincipal` thuộc `RelyingPartyRegistration` nào và NameID, format/qualifier được IdP dùng khi đăng nhập. Nếu ứng dụng map `Authentication#getName()` sang `localUserId` hoặc email, không tự giả định chuỗi đó là `NameID` mà IdP sẽ chấp nhận cho logout. Tương tự, **không sinh SessionIndex mới ở lúc logout**; nó phải tương quan với `AuthnStatement@SessionIndex` ban đầu.

Theo Spring Security reference, resolver mặc định tạo LogoutRequest và cung cấp **Issuer** từ SP entityID, **NameID** từ `Authentication#getName()`, ID giao dịch, Destination từ IdP metadata. Tài liệu mặc định này **không nên được hiểu như bảo đảm tự động có mọi `NameID` qualifier hoặc `SessionIndex` phù hợp với mọi IdP**. Với IdP yêu cầu SessionIndex, cần kiểm tra SAML XML thật và tùy biến resolver theo API phiên bản đang dùng.

### 5.2. Nếu không lưu được SessionIndex?

- Khi SAML login đã thành công nhưng thiếu `SessionIndex`, SP **không nên phát một LogoutRequest thiếu chỉ số rồi mô tả đây là per-session SLO tuân profile**.
- Có thể thực hiện **local logout** ngay, giải thích IdP SSO session có thể còn và người dùng có thể được đăng nhập lại tự động.
- Nếu IdP không hỗ trợ SLO, chỉ phát local logout; không gọi endpoint đoán từ UI.
- Khi buộc cần global logout theo chính sách doanh nghiệp, điều phối IdP qua API/administrative flow được quản trị riêng; **không giả định** một request SLO không chỉ số từ SP sẽ có nghĩa global logout.
- Bổ sung lưu `SessionIndex` từ lúc xác thực SAML trong các lần login sau; không “sửa” bằng cách dùng `JSESSIONID` thay thế.

### 5.3. Kết thúc local session trước hay sau LogoutResponse?

Tài liệu Spring Security mô tả **RP-initiated** bằng cách thực thi logout local/invalidating session rồi phát `LogoutRequest` tới IdP. Nếu IdP không phản hồi hoặc phản hồi lỗi, session SP đã có thể bị xóa. Cần mô tả rõ cho người dùng: **đã thoát ứng dụng hiện tại** không đồng nghĩa mọi SP khác/phiên IdP đều đã logout.

Vì `LogoutResponse` có thể quay về sau khi local HttpSession đã invalidated, framework cần cơ chế lưu `Saml2LogoutRequest`/RelayState và `InResponseTo` để correlation; đừng tự xóa toàn bộ state trước khi nhận phản hồi rồi bỏ verification.

## 6. IdP-initiated logout: SP nhận LogoutRequest

Khi IdP/session authority chủ động đăng xuất, nó gửi một `LogoutRequest` tới **SLO endpoint của SP**. Spring Security dùng `Saml2LogoutRequestFilter` cùng validator/resolver để xử lý.

~~~text
IdP -- signed LogoutRequest --> SP /logout/saml2/slo
                                  |
                                  v
                           Chọn registration tin cậy
                                  |
                         Verify issuer + signature
                         destination + thời gian + replay
                         NameID + SessionIndexes
                                  |
                                  v
                     Tìm các session trong shared registry
                                  |
                         +--------+----------+
                         |                   |
                       match                no match
                         |                   |
                  revoke chính xác      quyết định status
                  các session          theo chính sách
                         |                   |
                         +--------+----------+
                                  |
                         signed LogoutResponse
                                  |
                           gửi lại IdP SLO
~~~

### 6.1. Đừng dùng browser callback để suy ra toàn bộ phiên

**Một callback SLO chỉ đi kèm trình duyệt hiện tại**; nó có thể không mang cookie của tất cả session cần thu hồi. Nếu IdP yêu cầu kết thúc `idx-01`, nhiều HttpSession ở các browser/tab/node khác nhau có thể có cùng context SAML. Nếu chỉ gọi `request.getSession().invalidate()`, SP chỉ có thể hủy **session hiện gắn với request** (nếu có), và có thể bỏ sót những phiên khác.

Trong Spring Security, `saml2Logout` hỗ trợ giao thức và các filter cho SLO. **Không mặc định suy ra** rằng cấu hình `.saml2Logout(withDefaults())` sẽ thu hồi tất cả HTTP sessions ở mọi browser và mọi pod theo NameID/SessionIndex. Để thực hiện yêu cầu cấp hệ thống, cần thiết kế **shared session registry + revocation service** và tích hợp với validator/logout handlers tại đúng vị trí.

Đối với SLO tới SP, một số trình duyệt cross-site POST có thể thiếu cookie do `SameSite`, hoặc callback không hề có phiên HTTP ứng dụng đang hoạt động. Do đó không thể chỉ dựa vào current HttpSession để xác định principal; phải dùng request đã xác minh và registry đáng tin, đồng thời **không cho phép yêu cầu logout không xác minh được thu hồi phiên của người khác**.

### 6.2. Cách chọn target sessions khi có/không có index

1. **Xác minh nguồn:** issuer IdP đã đăng ký, chữ ký và binding, Destination trùng SLO URL, thời hạn/IssueInstant, chống phát lại ID request và trust registration.
2. **Xác minh principal:** NameID chính xác theo format/qualifier/issuer/SP scope. Với `EncryptedID`, giải mã hợp lệ trước khi match.
3. **Nếu có SessionIndex:** chọn mọi local sessions có đúng tuple `(registration, issuer, scopedNameID, sessionIndex)`; có thể có nhiều session HTTP.
4. **Nếu không có SessionIndex:** chỉ xử lý dưới nghĩa “mọi phiên liên quan principal” khi requester **đã xác minh là session authority** và chính sách SLO cho phép.
5. **Thực thi thu hồi:** invalidate những local sessions được chọn qua registry/kho chung, ghi audit; không xóa phiên của IdP/tenant/subject khác.
6. **Trả phản hồi:** tạo `LogoutResponse` tới IdP SLO endpoint, với `InResponseTo` đúng request ID và status phản ánh thực tế; xử lý partial failure.

**Không đối chiếu mỗi NameID một lần rồi logout người dùng bất kỳ có cùng tên/email.** Không coi SessionIndex không rõ/không match là giấy phép bỏ qua các giới hạn phạm vi.

## 7. LogoutResponse, correlation và trạng thái partial logout

Mẫu phản hồi SAML (rút gọn để giải thích, chưa có chữ ký):

~~~xml
<samlp:LogoutResponse
    xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    ID="_logout-response-902"
    InResponseTo="_logout-request-901"
    Version="2.0"
    IssueInstant="2026-11-07T03:30:10Z"
    Destination="https://sp.example.org/logout/saml2/slo">
  <saml:Issuer>urn:example:idp:corporate</saml:Issuer>
  <samlp:Status>
    <samlp:StatusCode
        Value="urn:oasis:names:tc:SAML:2.0:status:Success"/>
  </samlp:Status>
</samlp:LogoutResponse>
~~~

**`InResponseTo` trỏ về LogoutRequest ID, không phải SessionIndex.** SP cần biết mình đã gửi yêu cầu nào, cho IdP nào, theo binding và điểm nhận nào; sau đó xác minh phản hồi, chữ ký và status. Cơ chế `Saml2LogoutRequestRepository` trong Spring Security hỗ trợ lưu yêu cầu để so `RelayState` và `InResponseTo`.

Có thể xuất hiện **`PartialLogout`** hoặc tình huống một phần ứng dụng không thể kết thúc phiên. Không đánh dấu trạng thái “mọi phiên đã bị xóa” nếu shared registry bị lỗi, node khác chưa thu hồi session hay IdP không nhận phản hồi. Khi fail, ưu tiên **không tiếp tục chấp nhận phiên local đã biết cần thu hồi**, trả lỗi/status chính xác và dùng retry/audit theo quy trình vận hành.

**Hết SLO không đồng nghĩa mọi token/API key bị thu hồi.** SP có thể dùng JWT stateless hoặc refresh token sống lâu; muốn chấm dứt truy cập cần kiểm tra token revocation, TTL, session version hoặc account security state tương ứng.

## 8. Triển khai ở ứng dụng nhiều node: session registry là nền tảng

Giả sử ứng dụng Spring Boot chạy sau load balancer với node A/B/C:

~~~text
                  IdP
                   |
             LogoutRequest
                   |
             Load Balancer
                   |
        +----------+----------+
        |                     |
      Node A                Node B
        |                     |
        +----------+----------+
                   |
       SHARED SESSION CONTEXT / INDEX
       key=(registration, issuer, NameID, SessionIndex)
           |             |
           v             v
     browser-A        browser-E
     HTTP session      HTTP session
           |             |
           +------ atomic revoke --------+
                                         |
                              HTTP sessions invalidated
                              or marked revoked in shared store
~~~

Cấu trúc logic có thể gồm:

~~~text
saml_session_binding
  registration_id
  idp_issuer
  sp_entity_id
  name_id_value_or_protected_key
  name_id_format
  name_qualifier
  sp_name_qualifier
  sp_provided_id
  saml_session_index
  http_session_id
  local_account_id
  created_at
  expires_at
  revoked_at
  UNIQUE(http_session_id, registration_id)

INDEX(registration_id, idp_issuer, scoped_name_id, saml_session_index)
INDEX(registration_id, idp_issuer, scoped_name_id)
~~~

Schema chỉ minh họa, không phải SQL migration. `scoped_name_id` có thể là khóa chuẩn hóa/HMAC nội bộ để giảm rò dữ liệu trong index; phải thiết kế cách đồng bộ format/qualifier và cơ chế rotation key. Không lưu NameID nhạy cảm dạng plaintext trong metric hoặc URL.

### 8.1. Chống race khi logout và khi login mới

Một nguy cơ thực tế:

~~~text
T0: IdP bắt đầu logout phiên idx-01.
T1: Node A đọc registry, thấy HTTP session A/E.
T2: Node B vừa tạo HTTP session F từ callback SAML cũ.
T3: Node A invalidate A/E, nhưng F vẫn còn hoạt động.
~~~

Để tránh bỏ sót, nên có **revocation marker** hoặc trạng thái phiên SAML chung:

- Đánh dấu tuple `(registration, issuer, scopedNameID, SessionIndex)` là `REVOKED` hoặc `LOGOUT_IN_PROGRESS` **trước/đồng thời với** việc chọn local sessions.
- Bất kỳ login/session mới nào dùng cùng phiên SAML đã thu hồi phải bị từ chối theo chính sách đến khi có chứng cứ một phiên IdP mới hợp lệ; **không mở lại** marker bằng một callback cũ.
- Tìm và thu hồi mọi local sessions match theo shared registry, kể cả những session được tạo sát thời điểm logout.
- Dùng transaction/CAS hoặc cơ chế nguyên tử/nhất quán phù hợp; giữa SQL/Redis/revocation store phải tránh gap cho phép quyền không còn hợp lệ.
- Nếu chưa chắc thu hồi xong mọi node, không báo toàn bộ SLO đã thành công. Ghi audit và bù trừ theo retry policy có idempotency.

**Không xem một lệnh `DEL sessionId` đơn lẻ là “distributed logout completed”.** Phải xác định session ID đó có gắn đúng SAML context nào, còn nơi phát token nào khác và có outstanding request nào giữ authentication snapshot hay không.

### 8.2. Redis/SQL hay Spring Session?

| Giải pháp | Làm được gì | Chưa tự giải quyết |
| --- | --- | --- |
| **Spring Session** với Redis/JDBC | Lưu HTTP sessions dùng chung, hỗ trợ invalidate session theo ID/cơ chế tìm session tùy cấu hình. | Không tự phát hiện SAML NameID/SessionIndex nếu chưa lưu mapping. |
| **Spring Security SessionRegistry** | Quản lý/tra phiên theo principal trong những cấu hình phù hợp. | Có thể không đủ scope theo IdP+NameID+SessionIndex, hoặc không chia sẻ nhiều node nếu chỉ memory. |
| **Bảng liên kết SAML session** trong DB | Query theo namespace/NameID/SessionIndex, audit và revocation. | Cần transaction và đồng bộ với HTTP session store. |
| **Redis index/sets** | Tra nhiều local session IDs nhanh, TTL, revocation marker. | Cần atomic update, cleanup, chính sách eviction/failover rõ. |
| **Chỉ `HttpServletRequest.getSession().invalidate()`** | Hủy local session gắn với request. | Không thu hồi session ở trình duyệt khác hoặc đúng nhiều SessionIndex có cùng NameID. |

Trong production, cần kiểm chứng xem `FindByIndexNameSessionRepository`/session indexing nào thật sự tồn tại trong phiên bản Spring Session đang dùng, quyền thao tác trên mọi node và chính sách phiên đã bị disable. Không tự thêm quyền admin cho mọi session có cùng email nhằm dễ query.

### 8.3. Nếu registry không sẵn sàng

Tình huống IdP yêu cầu hủy `idx-01` nhưng shared session store trả timeout: **không bỏ qua lỗi và vẫn trả “Success – tất cả đã xong”**. Ưu tiên cơ chế fail-safe cho quyền truy cập (đánh dấu revocation ở kho bền hoặc chặn tiếp nhận phiên liên quan), phản hồi trạng thái lỗi/partial phù hợp với hợp đồng SLO và cảnh báo vận hành. Nếu chỉ có thể local logout, phải nói rõ phạm vi còn chưa xác nhận.

## 9. Spring Security SAML 2.0 Logout: các thành phần cần biết

Spring Security Servlet cung cấp khả năng **RP-initiated** và **AP-/IdP-initiated** SAML SLO khi IdP hỗ trợ và registration đã được bật.

| Thành phần | Vai trò |
| --- | --- |
| `Saml2RelyingPartyInitiatedLogoutSuccessHandler` | Khi SP chủ động logout, tạo/gửi LogoutRequest tới IdP qua resolver đã cấu hình. |
| `Saml2LogoutRequestResolver` (ví dụ `OpenSaml5LogoutRequestResolver`) | Tạo, ký và serialize LogoutRequest, bao gồm các giá trị NameID/SessionIndex cần có theo IdP/profile. |
| `Saml2LogoutRequestFilter` | Xử lý LogoutRequest do IdP gửi tới SP. |
| `Saml2LogoutRequestValidator` | Kiểm tra request, có thể mở rộng để bảo đảm matching NameID/SessionIndex và policy. |
| `Saml2LogoutResponseResolver` | Sinh LogoutResponse ký hợp lệ tới đối tác. |
| `Saml2LogoutResponseFilter` | Nhận/kiểm tra LogoutResponse cho SP-initiated flow. |
| `Saml2LogoutRequestRepository` | Lưu outstanding LogoutRequest để xác minh response tương quan qua RelayState/InResponseTo. |
| `RelyingPartyRegistration` | Cấu hình IdP/entityIDs/metadata, SLO endpoints, signing/verification credentials và binding liên quan. |

### 9.1. Cấu hình tối thiểu (Spring Boot Servlet)

Ví dụ `application.yml` sử dụng **IdP metadata** giả định, SP có private key/certificate dùng ký LogoutRequest/LogoutResponse:

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          corporate:
            assertingparty:
              metadata-uri: https://idp.example.org/metadata
            signing:
              credentials:
                - private-key-location: classpath:credentials/sp-signing.key
                  certificate-location: classpath:credentials/sp-signing.crt
            singlelogout:
              url: "{baseUrl}/logout/saml2/slo"
~~~

Đường dẫn `credentials/...` là dữ liệu minh họa: hệ thống thật phải cung cấp khóa theo đúng định dạng (ví dụ PKCS#8) và bảo vệ private key. IdP metadata phải công bố `SingleLogoutService` phù hợp; SP phải có URL SLO được đăng ký tại IdP và bảo đảm kết nối HTTPS/certificate/issuer đúng.

Tệp `src/main/java/example/federation/SamlLogoutSecurityConfig.java`:

~~~java
package example.federation;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SamlLogoutSecurityConfig {

    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/**", "/error").permitAll()
                .anyRequest().authenticated())
            .saml2Login(Customizer.withDefaults())
            .saml2Logout(Customizer.withDefaults());
        return http.build();
    }
}
~~~

Đây là **mã cấu hình trong dự án Spring Boot**, **không thể biên dịch độc lập chỉ với JDK**; cần dependency `spring-security-saml2-service-provider`, IdP metadata và registration hợp lệ. **Quan trọng:** bật `saml2Logout` và có signing key **chỉ kích hoạt khả năng giao thức**, không chứng minh đã lưu `SessionIndex` từ login hoặc thu hồi được mọi HTTP sessions theo scope. Phải kiểm chứng bằng integration test và có thể cần tùy biến resolver/validator/session registry.

Đường dẫn thường gặp:
- **`POST /logout`**: yêu cầu SP logout; khi SLO được cấu hình và principal phù hợp, có thể phát LogoutRequest tới IdP.
- **`/logout/saml2/slo`**: SP nhận `SAMLRequest` hoặc `SAMLResponse` SLO qua binding đã cấu hình; thường dùng POST.
- **`/login/saml2/sso/{registrationId}`**: ACS nhận login SAMLResponse; **không phải** endpoint SLO.

Các route/binding có thể tùy chỉnh; phải đồng bộ runtime, IdP/SP metadata và `RelyingPartyRegistration`. Không tắt CSRF toàn ứng dụng để hỗ trợ SLO; chỉ mở đúng callback SAML đã được framework bảo vệ và tiếp tục xác minh chữ ký/nguồn.

### 9.2. Tùy chỉnh NameID và SessionIndex trong LogoutRequest

Tài liệu Spring Security hiện hành mô tả `OpenSaml5LogoutRequestResolver` có **`setParametersConsumer`** để bổ sung/sửa các trường trong LogoutRequest trước khi ký/serialize. Nếu ứng dụng dùng `OpenSaml4LogoutRequestResolver` hoặc bản Spring Security khác, API và kiểu dữ liệu có thể khác; phải bám đúng phiên bản.

Quy trình tùy biến **ở mức kiến trúc**:

~~~text
On SP logout:
  auth = current authenticated Saml2 principal
  reg  = trusted RelyingPartyRegistration attached to auth
  ctx  = server-side SamlSessionContext for this SP HTTP session

  verify ctx.registration and ctx.nameId against auth/reg
  require ctx.samlSessionIndex for per-session SP-initiated SLO

  buildLogoutRequestWithSpringResolver(reg)
  set NameID:
    value, Format, NameQualifier, SPNameQualifier, SPProvidedID
    from the verified original login context
  add samlp:SessionIndex using ctx.samlSessionIndex
  sign/serialize using framework with SP signing credentials
  send via registered IdP SingleLogoutService binding/location
~~~

Đây là **pseudocode**, không phải tên class/method có sẵn để copy vào project. Không tự ghép XML bằng string hay ký bằng một chứng thư lấy từ request. **Đừng thay NameID bằng email hoặc local account ID chỉ vì `Authentication#getName()` có giá trị đó.** Hãy xuất phát từ NameID đúng định dạng đã lưu khi SAML login và kiểm tra XML sau khi Spring resolver chạy.

Trường hợp nhiều `AuthnStatement`/SessionIndex trong cùng assertion, phải định nghĩa chiến lược theo profile của IdP và lưu **đầy đủ các chỉ số liên quan** thay vì lấy một giá trị tùy tiện. Khi gửi SLO từ SP cho một phiên, danh sách SessionIndex phải thể hiện đúng phiên/nhóm phiên mà SP định yêu cầu hủy.

### 9.3. Mở rộng xử lý IdP-initiated LogoutRequest

Khi custom matching/revocation, nên:

1. **Ủy quyền cho `Saml2LogoutRequestValidator` mặc định** của phiên bản để xác minh signature, issuer, destination và principal theo phạm vi có hỗ trợ.
2. Bổ sung điều kiện NameID qualifiers, session authority và danh sách SessionIndex; ghi từ chối khi không thể nhận diện đúng.
3. Ánh xạ sang shared session registry theo đúng key/namespace.
4. Thực hiện thu hồi ở điểm **sau khi request được xác minh, trước khi công bố LogoutResponse thành công**.
5. Hỗ trợ xử lý retry/idempotency có kiểm soát, chống replay LogoutRequest@ID.
6. Nếu không thể thu hồi đầy đủ, quyết định response status và báo cáo vận hành trung thực.

**Lưu ý triển khai:** `Saml2LogoutRequestValidator` chỉ xác thực thông điệp; việc tìm/hủy *nhiều* HttpSessions cần một **session-revocation service** riêng. Không biến validator thành thao tác ghi DB chưa có transaction hoặc âm thầm xử lý trước khi chữ ký hợp lệ. Tương tự, không giả định filter mặc định biết toàn bộ phiên của người dùng trên các pod khác.

## 10. Java 17: mô phỏng lựa chọn chính xác các phiên cần hủy

Chương trình sau **chạy độc lập bằng Java 17**. Nó minh họa thuật toán **chọn các local session** theo trusted registration, issuer, NameID và SessionIndex. Mã **không xác thực XML/chữ ký, không truy cập Redis/SQL và không thực sự invalidate HttpSession**. Tham số `verified`/role authority phải đến từ một `LogoutRequest` đã được Spring/OpenSAML validator xác minh; không dùng dữ liệu request HTTP tự khai để gọi hàm.

Tệp `SamlLogoutSessionSelectionDemo.java`:

~~~java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Objects;

public class SamlLogoutSessionSelectionDemo {
    record NameId(String value, String format,
                  String nameQualifier, String spNameQualifier) {}

    record LocalSession(String httpSessionId, String registration,
                        String trustedIdpIssuer, NameId nameId,
                        String samlSessionIndex) {}

    record Selection(boolean allowed, List<String> httpSessionIds) {}

    static Selection selectTargets(
            List<LocalSession> sessions,
            String registration,
            String verifiedIssuer,
            NameId verifiedNameId,
            List<String> requestedSessionIndexes,
            boolean trustedSessionAuthority) {

        // Session participant thiếu index: không biến thành all-sessions.
        if (requestedSessionIndexes.isEmpty() &&
                !trustedSessionAuthority) {
            return new Selection(false, List.of());
        }

        List<String> targets = new ArrayList<>();
        for (LocalSession session : sessions) {
            if (!session.registration().equals(registration)
                    || !session.trustedIdpIssuer().equals(verifiedIssuer)
                    || !Objects.equals(session.nameId(), verifiedNameId)) {
                continue;
            }

            boolean match = requestedSessionIndexes.isEmpty()
                    || requestedSessionIndexes.contains(
                        session.samlSessionIndex());

            if (match) {
                targets.add(session.httpSessionId());
            }
        }

        targets.sort(Comparator.naturalOrder());
        return new Selection(true, List.copyOf(targets));
    }

    public static void main(String[] args) {
        NameId alice = new NameId("principal-83917",
                "persistent", "idp-X", "sp-portal");
        NameId bob = new NameId("principal-other",
                "persistent", "idp-X", "sp-portal");

        List<LocalSession> sessions = List.of(
            new LocalSession("browser-A", "corporate",
                    "idp-X", alice, "idx-01"),
            new LocalSession("browser-B", "corporate",
                    "idp-X", alice, "idx-02"),
            new LocalSession("browser-C", "corporate",
                    "idp-X", bob, "idx-01"),
            new LocalSession("browser-D", "partner",
                    "idp-Y", alice, "idx-01"),
            new LocalSession("browser-E", "corporate",
                    "idp-X", alice, "idx-01")
        );

        System.out.println(selectTargets(sessions,
                "corporate", "idp-X", alice,
                List.of("idx-01"), false).httpSessionIds());

        System.out.println(selectTargets(sessions,
                "corporate", "idp-X", alice,
                List.of("idx-01", "idx-02"), false).httpSessionIds());

        System.out.println(selectTargets(sessions,
                "corporate", "idp-X", alice,
                List.of(), true).httpSessionIds());

        System.out.println(selectTargets(sessions,
                "corporate", "idp-X", alice,
                List.of(), false).allowed());

        System.out.println(selectTargets(sessions,
                "corporate", "idp-X", alice,
                List.of("idx-unknown"), false)
                .httpSessionIds().isEmpty());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac SamlLogoutSessionSelectionDemo.java
java SamlLogoutSessionSelectionDemo
~~~

**Kết quả xác định:**

~~~text
[browser-A, browser-E]
[browser-A, browser-B, browser-E]
[browser-A, browser-B, browser-E]
false
true
~~~

Giải thích:

1. Request có `idx-01` chỉ chọn **A và E** dù session **C** cũng có `idx-01`, vì C thuộc một NameID khác; D thuộc IdP/registration khác.
2. Danh sách hai index `idx-01`, `idx-02` chọn **A, B, E**.
3. Khi **đúng session authority đáng tin** không gửi SessionIndex, chọn **mọi local session thuộc principal đó trong scope**, không chọn C/D.
4. Session participant không gửi index nhận `allowed=false`, không tự chuyển sang logout toàn bộ.
5. Index lạ cho danh sách rỗng, không có fallback sang toàn bộ phiên.

**Giới hạn quan trọng:** demo dùng `NameId` có bốn trường để diễn giải scope; NameID thật còn có thể có `SPProvidedID` và quy tắc qualifier tùy hợp đồng IdP. Nó không xác minh issuer hay authority, không xử lý encrypted NameID, multi-node/race, thời gian, logout request replay và không thực thi invalidation. Ở production phải có trust evaluation trước, session registry dùng chung và cơ chế revocation nguyên tử phù hợp.

## 11. Kiểm thử bảo mật và tính chính xác

| Tình huống | Kết quả mong đợi |
| --- | --- |
| Một `LogoutRequest` hợp lệ có đúng issuer, NameID, `idx-01`. | Chỉ thu hồi các local sessions cùng scope và `idx-01`. |
| Có hai HTTP sessions cùng NameID và `idx-01`. | Thu hồi **cả hai** nếu thuộc cùng liên kết/phiên SAML được yêu cầu. |
| Cùng `idx-01` nhưng NameID khác. | **Không** xóa phiên của người khác. |
| Cùng NameID string và index nhưng issuer/registration khác. | **Không** xóa phiên của IdP/tenant khác. |
| `NameID@Format` hoặc qualifier không khớp. | Không tự chuyển về so email/giá trị string; xác minh theo contract. |
| Request có hai SessionIndex. | Thu hồi hợp các phiên khớp cả hai index, không chọn thêm index khác. |
| IdP session authority hợp lệ gửi request không có index. | Thu hồi mọi session liên quan principal trong đúng scope theo policy. |
| SP participant gửi request không có index. | Reject/non-compliant; không xử lý như all-sessions. |
| Request có index không tìm thấy. | Không tự mở rộng phạm vi; xử lý no-match/status theo policy. |
| `EncryptedID` không giải mã được. | Không xóa phiên; xử lý lỗi xác minh. |
| Chữ ký sai, issuer lạ hoặc Destination sai. | **Không** thực hiện invalidation. |
| LogoutRequest bị replay hoặc quá hạn. | Từ chối hoặc xử lý idempotent đúng policy, không cho tạo hành động sai. |
| LogoutResponse có `InResponseTo` không khớp. | Không xem là xác nhận logout của yêu cầu hiện hành. |
| IdP không phản hồi sau RP-initiated SLO. | Không tuyên bố mọi ứng dụng đã logout; local SP có thể đã logout. |
| Browser IdP-initiated callback không có cookie SP. | Dựa vào LogoutRequest đã xác minh và registry, không dựa duy nhất vào current HttpSession. |
| Một phiên bị hủy trong lúc node khác tạo phiên từ callback cũ. | Revocation marker bảo vệ, không có session mới thuộc phiên đã bị kết thúc. |
| Session store/registry bị lỗi một phần. | Không báo Success toàn bộ, fail-safe và audit. |
| SLO thu hồi local HTTP sessions nhưng JWT API vẫn sống. | Revocation/token policy phải ngăn tiếp tục sử dụng ngoài SLA. |
| LogoutResponse có `PartialLogout`. | Phản ánh một phần thành công, không che lỗi và không suy diễn hoàn tất tất cả nơi. |
| Người dùng có quyền admin và user cùng IdP nhưng session index khác. | Không xóa sai phiên; chính sách organization-wide revocation là tác vụ khác. |

### 11.1. Dữ liệu quan sát và điều tra sự cố

Nên lưu audit theo hướng tối thiểu:

~~~text
event=SAML_SLO_REQUEST_VERIFIED
time_utc=2026-11-07T03:30:00Z
registration=corporate
verified_issuer=urn:example:idp:corporate
nameid_scope_hash=sha256:ab12...
requested_session_indexes_count=2
selected_local_sessions=3
revoked_local_sessions=3
outcome=SUCCESS
correlation_id=slo-req-901
~~~

Dữ liệu trên chỉ là ví dụ thiết kế, **không phải metrics mặc định của Spring Security**. Không log nguyên NameID cá nhân, SessionIndex nhạy cảm, `SAMLRequest`/`SAMLResponse` thô, cookie, signing key hoặc thông tin người dùng ở audit công khai. Log số phiên được chọn/thu hồi, lỗi registry, correlation và trạng thái partial để đối chiếu với IdP.

## 12. Lỗi thường gặp và cách xử lý

| Sai lầm | Hậu quả | Cách đúng |
| --- | --- | --- |
| Dùng `NameID`/email đơn lẻ làm khóa global logout. | Xóa phiên nhầm người, nhầm IdP/tenant. | Scope theo registration, trusted issuer, NameID đầy đủ. |
| Dùng `SessionIndex` một mình làm khóa. | Collision giữa issuer, user, SP. | Kết hợp identity scope và SessionIndex. |
| Dùng `JSESSIONID` làm `SessionIndex`. | IdP không nhận diện phiên vì khác không gian định danh. | Lưu SessionIndex gốc từ AuthnStatement. |
| Dùng `AuthnRequest@ID` hoặc `Assertion@ID` làm chỉ số SLO. | Lệch ID giao dịch và ID phiên. | Trích `AuthnStatement@SessionIndex`. |
| Không thấy SessionIndex thì luôn logout tất cả. | Session participant có thể yêu cầu không tuân profile; logout quá rộng. | Phân biệt đúng session authority vs participant. |
| Mỗi SessionIndex chỉ có một HttpSession. | Bỏ sót browser khác dùng cùng phiên liên kết. | Registry một-nhiều, thu hồi toàn bộ target trong scope. |
| Chỉ `request.getSession().invalidate()` với IdP-initiated SLO. | Không xóa phiên ở browser khác, có thể thiếu cookie callback. | Shared session registry và revocation. |
| Chỉ bật `saml2Logout` rồi coi SLO toàn cụm là xong. | Chưa có mapping NameID/SessionIndex hay cross-node invalidation. | Tích hợp session index/revocation service, test thực tế. |
| Lấy NameID từ `Authentication#getName()` mà không so với IdP. | Có thể dùng local user ID/email thay NameID phiên SAML. | Giữ NameID gốc cùng Format/qualifiers. |
| Không kiểm tra chữ ký/trust của LogoutRequest. | Attacker có thể gửi SLO giả để logout người khác. | Default validator + policy, reject trước khi side effect. |
| Không kiểm tra `LogoutResponse@InResponseTo`. | Response giả/trễ có thể bị coi là giao dịch hiện tại. | Lưu request gốc và correlation một lần. |
| Tự xác nhận Success khi store timeout. | IdP nghĩ mọi phiên đã bị hủy nhưng phiên SP còn sống. | Fail-safe, PartialLogout/error, retry và audit. |
| Chỉ xóa cookie khi user logout. | JWT/refresh tokens và session ở browser khác còn sống. | Session/token revocation có phạm vi rõ. |
| Lưu NameID/SessionIndex và SAML XML nguyên bản vào URL/log. | Rò dữ liệu/PII, dễ bị tái sử dụng trong điều tra thiếu kiểm soát. | Bảo vệ session registry và log có che/mã hóa. |

## 13. Checklist triển khai production

1. IdP SAML metadata có `SingleLogoutService` đúng binding/location và chứng thư xác minh hợp lệ không?
2. SP có signing credentials, SLO callback thực tế và metadata SP nhất quán không?
3. Khi login, ứng dụng có lưu **trusted issuer/registration + đầy đủ NameID semantics + SessionIndex từ AuthnStatement** không?
4. Với RP-initiated SLO, LogoutRequest có NameID đúng và ít nhất một SessionIndex theo profile không?
5. Với IdP-initiated SLO không có SessionIndex, chính sách có xác minh session authority và chỉ thu hồi **applicable sessions** trong đúng scope không?
6. Với index có mặt, thuật toán có chọn **tất cả local sessions khớp tuple** và không xóa phiên cùng username nhưng index khác không?
7. Có xử lý một-nhiều `SessionIndex → HttpSession`, nhiều browser và nhiều node không?
8. Có xác minh signature/issuer/destination/IssueInstant/expiry/replay của LogoutRequest **trước khi thu hồi** không?
9. Có đối chiếu `LogoutResponse@InResponseTo`, RelayState, status và trust trước khi công bố SLO thành công không?
10. Shared session registry có hỗ trợ revocation nguyên tử, concurrency, failover, cleanup và audit không?
11. Khi registry lỗi hoặc partial logout, ứng dụng có fail-safe và báo trạng thái trung thực không?
12. Có chính sách thu hồi JWT/refresh tokens nếu dùng stateless API không?
13. Có test với session trùng NameID nhưng khác issuer/index, session cùng index ở hai browser và callback thiếu cookie không?
14. Có kiểm soát PII trong registry, log và dashboard không?

## 14. Tự kiểm tra kiến thức

1. **`NameID` trả lời câu hỏi gì?** — Ai là principal theo quan hệ IdP/SP và phạm vi format/qualifier.
2. **`SessionIndex` từ đâu?** — Từ `AuthnStatement@SessionIndex` của SAML assertion được IdP phát và đã được xác minh khi login.
3. **`LogoutRequest@ID` là SessionIndex?** — Không; nó là ID giao dịch logout, được `LogoutResponse@InResponseTo` tham chiếu.
4. **SP gửi LogoutRequest không có SessionIndex có tuân SLO profile không?** — Theo OASIS Errata 05 E38, session participant **phải có ít nhất một** SessionIndex.
5. **IdP có thể không gửi SessionIndex để làm gì?** — Khi là session authority hợp lệ, biểu thị logout **mọi phiên áp dụng được của principal** theo phạm vi và policy.
6. **Hai local sessions cùng SAML index có cùng `JSESSIONID` không?** — Không nhất thiết; có thể là hai HTTP sessions khác nhau.
7. **Có thể chỉ so email để quyết định ai logout không?** — Không; cần issuer, registration và NameID scoped.
8. **SLO callback IdP không có SP cookie thì có thể dùng registry không?** — Có, khi request đã được xác minh và registry lưu mapping đáng tin; không được tin dữ liệu chưa xác minh.
9. **Thấy một index lạ thì nên fallback logout mọi session?** — Không.
10. **Đã xóa session SP thì mọi JWT/token của API đã bị thu hồi?** — Không; cần cơ chế token revocation riêng.
11. **Bật Spring Security `saml2Logout` đồng nghĩa tự xử lý all browser sessions?** — Không nên giả định; phải kiểm thử/triển khai session indexing phù hợp.
12. **Không nhận được LogoutResponse có nghĩa local logout thất bại?** — Không nhất thiết; local session đã có thể bị hủy, chỉ là SLO toàn federation chưa xác nhận.

## Tài liệu tham khảo

- [OASIS SAML 2.0 Core — LogoutRequest, NameID và SessionIndex (§3.7.1)](https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf)
- [OASIS SAML 2.0 Profiles — Single Logout (§4.4), Web Browser SSO (§4.1)](https://docs.oasis-open.org/security/saml/v2.0/saml-profiles-2.0-os.pdf)
- [OASIS SAML 2.0 Errata 05 — E38: SessionIndex trong LogoutRequest và Session Authority](https://docs.oasis-open.org/security/saml/v2.0/errata05/os/saml-v2.0-errata05-os.html)
- [Spring Security — Performing Single Logout](https://docs.spring.io/spring-security/reference/servlet/saml2/logout.html)
- [Spring Security — SAML 2.0 Login Overview](https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html)
- [Spring Security API — Saml2LogoutRequestResolver](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/saml2/provider/service/web/authentication/logout/Saml2LogoutRequestResolver.html)
- [Spring Security API — SAML logout package và request/response filters](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/saml2/provider/service/web/authentication/logout/package-summary.html)
- [Spring Session — Redis-backed HttpSession](https://docs.spring.io/spring-session/reference/guides/boot-redis.html)
