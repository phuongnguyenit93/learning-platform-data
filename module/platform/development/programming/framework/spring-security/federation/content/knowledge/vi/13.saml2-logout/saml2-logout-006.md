# Ký, xác minh chữ ký và kiểm tra đích của thông điệp đăng xuất SAML2

Trong **SAML 2.0 Single Logout (SLO)**, việc một người dùng bấm nút “Đăng xuất” không đơn thuần là xóa cookie ứng dụng. Service Provider (SP, hay Relying Party/RP) và Identity Provider (IdP, hay Asserting Party/AP) có thể trao đổi **`LogoutRequest`** và **`LogoutResponse`** thông qua trình duyệt để thông báo và xác nhận kết thúc phiên liên kết. Các thông điệp này phải được **xác thực nguồn phát**, **bảo vệ tính toàn vẹn** và **gửi đúng bên nhận**. Nếu thiếu các kiểm tra đó, một bên giả mạo có thể ép đăng xuất, sửa phản hồi hoặc lợi dụng nhầm endpoint để làm sai trạng thái đăng xuất.

Bài này tập trung vào ba yêu cầu của chủ đề **Đăng xuất SAML2**: (1) SP/IdP **ký đúng thông điệp bằng private key thuộc về mình**, (2) bên nhận **kiểm chữ ký bằng chứng thư công khai của đối tác đã được tin cậy**, và (3) bên nhận **kiểm tra đích của thông điệp (`Destination`)** và các ràng buộc giao thức khác, đặc biệt `Issuer`, `InResponseTo`, `NameID`, `SessionIndex`, trạng thái `StatusCode` và anti-replay.

**Nguyên tắc xuyên suốt:** một chữ ký mật mã hợp lệ trên nội dung SAML vẫn **không đủ** để quyết định đăng xuất: cần đúng issuer, đúng registration, đúng SLO endpoint, đúng giao dịch và đúng phiên/người dùng theo hợp đồng giữa SP–IdP. Không dùng kết quả HTTP 200 hoặc 302 để thay cho kiểm tra giao thức.

## 1. Phân biệt Local Logout và SAML Single Logout

| Hoạt động | Local logout | SAML2 Single Logout |
| --- | --- | --- |
| Mục tiêu | Kết thúc phiên của một ứng dụng | Phối hợp kết thúc phiên liên kết ở SP, IdP và có thể các SP khác |
| Nơi khởi tạo | Người dùng/ứng dụng SP | SP (*RP-initiated*) hoặc IdP (*AP-initiated*) |
| Có `LogoutRequest`? | Không bắt buộc | Có trong luồng giao thức |
| Có `LogoutResponse`? | Không | Thường dùng để báo kết quả xử lý request |
| Chứng thư chữ ký SAML | Không cần | Cần khi SLO sử dụng các binding/chính sách ký liên quan |
| Điều kiện thành công | Session/cookie nội bộ đã bị thu hồi | Các thông điệp SAML hợp lệ và kết quả từ các bên đã được xác minh |
| Có bảo đảm tất cả SP đã logout? | Không | **Không tuyệt đối**: có thể trả `PartialLogout` hoặc xảy ra lỗi mạng |

Ví dụ người dùng đăng nhập Portal A bằng IdP B. Nếu Portal A chỉ xóa session của chính mình, phiên ở IdP B có thể vẫn còn; lần tiếp theo user truy cập Portal A, IdP có thể SSO trở lại mà không yêu cầu nhập mật khẩu. Với SLO, SP thông báo đăng xuất tới IdP và IdP có thể phối hợp với những SP khác, nhưng mức độ hoàn tất phụ thuộc IdP, binding, trạng thái giao dịch và các đối tác.

**Đừng coi SLO là một phép hủy toàn cầu có bảo đảm tuyệt đối.** Ứng dụng phải biết phân biệt local logout đã xảy ra với kết quả liên kết `Success`, `PartialLogout` hoặc failure và không nói với người dùng “đã đăng xuất mọi hệ thống” khi không có bằng chứng.

## 2. Vai trò của LogoutRequest và LogoutResponse

`<samlp:LogoutRequest>` là yêu cầu chấm dứt một hoặc nhiều phiên đã liên kết. Thông tin quan trọng:

- `ID`: định danh duy nhất của request, dùng đối chiếu khi nhận response.
- `IssueInstant`: thời điểm phát message.
- `Destination`: nơi thông điệp được gửi tới, phải phù hợp điểm tiếp nhận SLO đã thống nhất.
- `Issuer`: Entity ID của bên gửi message.
- `NameID`, `BaseID` hoặc `EncryptedID`: nhận diện principal theo SAML; không nhất thiết là username nội bộ của SP.
- `SessionIndex`: giúp xác định phiên cần thu hồi khi có; không mặc định mọi SAML message đều có trường này.
- `NotOnOrAfter`: giới hạn thời gian request khi được cung cấp.

`<samlp:LogoutResponse>` là kết quả của một LogoutRequest:

- `ID`: định danh response riêng.
- `InResponseTo`: phải liên hệ với **ID của LogoutRequest tương ứng** khi có giao dịch request-response.
- `Issuer`: định danh bên gửi response.
- `Destination`: endpoint SLO nhận response theo metadata/hợp đồng.
- `Status/StatusCode`: phân biệt `Success`, `PartialLogout`, lỗi hoặc các trạng thái profile khác.

**Không nhầm `Response@InResponseTo` với `Assertion@AudienceRestriction` của Web SSO login.** LogoutRequest/LogoutResponse là thông điệp giao thức logout, không phải Assertion xác thực login. Không tự copy quy tắc `SubjectConfirmationData@Recipient` từ SAML login vào cấu trúc LogoutRequest: trường `Recipient` đó thuộc bearer subject confirmation của Assertion, còn **đích logout** chủ yếu được biểu diễn bởi `Destination`, metadata SLO endpoints và binding cụ thể.

## 3. Sơ đồ hai luồng Single Logout

### 3.1. RP-initiated: SP phát LogoutRequest, IdP gửi LogoutResponse

~~~mermaid
sequenceDiagram
    participant U as Trình duyệt
    participant SP as Portal A (SP)
    participant IdP as Identity Provider B
    U->>SP: POST /logout (với CSRF token phù hợp)
    SP->>SP: Xử lý local logout và lưu correlation SLO
    SP->>SP: Tạo và ký LogoutRequest bằng khóa SP
    SP-->>U: Redirect/POST SAMLRequest tới IdP SLO
    U->>IdP: Gửi LogoutRequest đã ký
    IdP->>IdP: Kiểm chữ ký SP, Issuer, Destination, NameID
    IdP->>IdP: Đăng xuất và điều phối các phiên liên quan
    IdP-->>U: LogoutResponse được IdP ký
    U->>SP: Gửi SAMLResponse về SP SLO endpoint
    SP->>SP: Kiểm chữ ký IdP, Destination, InResponseTo, Status
    SP-->>U: Kết quả logout sau khi xác minh
~~~

Ở luồng này **khóa riêng SP** ký LogoutRequest và **chứng thư công khai SP** được IdP dùng để kiểm. Khi IdP trả LogoutResponse, vai trò đổi chiều: **khóa riêng IdP** ký và **public certificate IdP** được SP dùng kiểm.

Spring Security mô tả `Saml2RelyingPartyInitiatedLogoutSuccessHandler` dùng `Saml2LogoutRequestResolver` để tạo/ký/serialize request, sau đó `Saml2LogoutResponseFilter` dùng `Saml2LogoutResponseValidator` để kiểm response. Spring lưu request ban đầu bằng repository để đối chiếu `InResponseTo` và `RelayState`.

### 3.2. AP-initiated: IdP phát LogoutRequest, SP gửi LogoutResponse

~~~mermaid
sequenceDiagram
    participant U as Trình duyệt
    participant IdP as Identity Provider B
    participant SP as Portal A (SP)
    U->>IdP: Đăng xuất tại IdP
    IdP->>IdP: Tạo và ký LogoutRequest bằng khóa IdP
    IdP-->>U: Chuyển SAMLRequest về SP SLO endpoint
    U->>SP: Gửi LogoutRequest tới /logout/saml2/slo
    SP->>SP: Kiểm chữ ký IdP, Issuer, Destination, principal/session
    SP->>SP: Thu hồi local session phù hợp nếu hợp lệ
    SP->>SP: Tạo/ký LogoutResponse bằng khóa SP
    SP-->>U: Chuyển LogoutResponse tới IdP endpoint
    U->>IdP: Nhận LogoutResponse từ SP
    IdP->>IdP: Xác minh chữ ký SP, Destination, InResponseTo
~~~

Ở AP-initiated, SP cần **kiểm request trước khi thực hiện hành động phá hủy phiên dựa trên yêu cầu ngoài**. Spring Security dùng `Saml2LogoutRequestFilter` và `Saml2LogoutRequestValidator` cho request vào, rồi `Saml2LogoutResponseResolver` để tạo/ký response. Trạng thái cookie/sessions bị thu hồi theo chính sách, không được hủy một tài khoản khác chỉ vì NameID do browser cung cấp.

## 4. Ai ký, ai kiểm chữ ký?

| Hướng trao đổi | Message | Private key dùng ký | Public certificate dùng verify |
| --- | --- | --- | --- |
| SP → IdP (RP-initiated) | `LogoutRequest` | **SP private signing key** | **SP public certificate** được IdP tin |
| IdP → SP (RP-initiated trả kết quả) | `LogoutResponse` | **IdP private signing key** | **IdP public certificate** được SP tin |
| IdP → SP (AP-initiated) | `LogoutRequest` | **IdP private signing key** | **IdP public certificate** được SP tin |
| SP → IdP (AP-initiated trả kết quả) | `LogoutResponse` | **SP private signing key** | **SP public certificate** được IdP tin |

**Quy tắc an toàn về ownership:**

- SP giữ bí mật `private key` của SP, chỉ công bố phần certificate/public key trong **SP metadata** khi cần.
- IdP giữ bí mật `private key` của IdP, công bố certificate phù hợp trong **IdP metadata**.
- SP cấu hình `RelyingPartyRegistration.signingX509Credentials` cho thông điệp SAML nó ký.
- SP cấu hình/đọc `AssertingPartyMetadata.verificationX509Credentials` từ nguồn IdP **đã được phê duyệt** để kiểm chữ ký đến từ IdP.
- Không dùng **verification certificate của IdP** như private key ký của SP. Không đưa private key vào YAML commit, log hoặc SAML metadata công khai.
- Nếu IdP xoay chứng thư, SP phải cập nhật trust anchors/metadata theo quy trình, có giai đoạn overlap khi cần. Không lấy certificate bất kỳ từ SAML message rồi tự tin đó là IdP B.

TLS bảo vệ kênh HTTP, nhưng **không thay thế** kiểm chữ ký SAML ở tầng thông điệp khi profile/binding yêu cầu. Browser là bên vận chuyển, không phải nguồn tin cậy.

## 5. Sự khác biệt chữ ký ở HTTP-Redirect và HTTP-POST bindings

SAML hỗ trợ nhiều binding, nhưng Spring Security SAML2 SLO trên Servlet thường thao tác **HTTP-Redirect** và **HTTP-POST**. Cơ chế ký khác nhau:

### A. HTTP-Redirect binding

Dữ liệu `LogoutRequest` hoặc `LogoutResponse` thường được DEFLATE, Base64 và URL encode vào query parameter `SAMLRequest` hoặc `SAMLResponse`. Khi ký theo Redirect binding, URL chứa `SigAlg` và `Signature`; chữ ký áp trên **chuỗi tham số được chuẩn hóa theo quy tắc của binding**, không phải tùy tiện ký raw XML.

Hình thức mô tả:

~~~text
GET https://idp.partner-b.example/saml/slo?
  SAMLRequest=<deflated-base64-url-encoded-message>
  &RelayState=<url-encoded-state>
  &SigAlg=<url-encoded-algorithm-uri>
  &Signature=<url-encoded-signature>

Khi là LogoutResponse, dùng SAMLResponse thay SAMLRequest.
~~~

**Nguy cơ:** nếu lập lại query theo thứ tự khác, decode-encode không nhất quán, thêm/bớt RelayState hoặc kiểm chữ ký trên XML thay vì chuỗi đã ký, verify có thể sai. Không tự viết bộ tạo/kiểm chữ ký Redirect binding. Dùng Spring Security/OpenSAML và kiểm chính xác `Saml2MessageBinding.REDIRECT` với metadata đối tác.

### B. HTTP-POST binding

Message SAML thường là XML Base64 trong HTTP POST body. Chữ ký dùng XML Digital Signature, có thể là `<ds:Signature>` trên phần tử phù hợp. XML signature đòi hỏi kiểm canonicalization, signed reference, ID và chống signature wrapping. Không thể đơn giản Base64-decode rồi so một chuỗi byte hoặc lấy certificate trong chính XML làm bằng chứng trust.

Hình thức minh họa:

~~~text
POST /logout/saml2/slo
Content-Type: application/x-www-form-urlencoded

SAMLRequest=<base64-encoded-xml>
RelayState=<opaque-value-when-present>
~~~

**Chữ ký có thể nằm trong XML**, không nhất thiết có `Signature` query parameter giống Redirect binding. Cả chữ ký của XML và chữ ký query binding đều có quy tắc xác minh riêng. Một request “nhìn thấy `ds:Signature`” không có nghĩa chữ ký hợp lệ; phải kiểm bằng key đã trust và tham chiếu tới đúng thông điệp.

**Quy tắc vận hành:** đối chiếu binding tại `SingleLogoutService/@Binding` trong IdP/SP metadata. Sử dụng SHA-256/thuật toán hiện đại theo chính sách, không tùy tiện cho phép SHA-1 hoặc thuật toán yếu. Nếu gặp message được ký theo kiểu không phù hợp với binding, fail closed; không bỏ verify để “tương thích”.

## 6. Kiểm Destination: "đã ký đúng" vẫn có thể gửi nhầm nơi

`Destination` là địa chỉ mà người gửi dự kiến thông điệp **được nhận**. Với SLO:

| Message | Hướng | Destination mong đợi |
| --- | --- | --- |
| RP LogoutRequest | SP → IdP | **IdP SLO request endpoint** trong IdP metadata |
| AP LogoutResponse | IdP → SP | **SP SLO response endpoint** công bố tại SP |
| AP LogoutRequest | IdP → SP | **SP SLO request endpoint** công bố tại SP |
| RP LogoutResponse | SP → IdP | **IdP SLO response endpoint** trong IdP metadata; có thể khác request URL |

Ví dụ SP có địa chỉ SLO public:

~~~text
https://portal.example.com/logout/saml2/slo
~~~

Còn IdP B:

~~~text
IdP SLO request URL:
https://login.partner-b.example/saml2/slo/request

IdP SLO response URL:
https://login.partner-b.example/saml2/slo/response
~~~

Thì request từ SP tới IdP cần dùng đích `.../request`, response từ SP tới IdP sau AP-initiated có thể cần `.../response`. Không tự giả định request và response endpoint luôn cùng URL. `RelyingPartyRegistration` và `AssertingPartyMetadata` có các trường `singleLogoutServiceLocation` và `singleLogoutServiceResponseLocation` cho từng phía.

**Trường `Destination` trong SAML Core có quy tắc phụ thuộc binding/profile.** Trong môi trường Web SLO đã ký, app cần xác định chính xác URL nhận public được cho phép và kiểm field khi hiện diện/bắt buộc theo profile/chính sách. Không bỏ qua một Destination sai chỉ vì chữ ký đúng. Không chấp nhận `http://localhost:8080` thay cho `https://portal.example.com` trong môi trường production.

### Đừng nhầm Destination, Recipient và RelayState

- **`Destination`:** nơi nhận message logout.
- **`Recipient` của `SubjectConfirmationData`:** trường của bearer Assertion trong **login**, không phải một thuộc tính bắt buộc của LogoutRequest/LogoutResponse.
- **`RelayState`:** tham số trạng thái vận chuyển qua browser; dùng để đối chiếu giao dịch theo repository/session và binding. Nó không tự chứng minh message đến từ IdP đúng.
- **`InResponseTo`:** liên kết LogoutResponse với LogoutRequest trước đó; quan trọng khi xác minh kết quả RP-initiated hoặc AP-initiated.

Nếu custom validator chỉ so Destination mà bỏ issuer/signature, attacker vẫn có thể làm giả logout message gửi tới đúng URL. Nếu chỉ kiểm chữ ký mà không kiểm Destination, một thông điệp được ký cho một endpoint khác có thể bị xử lý nhầm trong ứng dụng.

## 7. Ví dụ LogoutRequest và LogoutResponse để đọc trường

### AP-initiated LogoutRequest gửi đến SP

~~~xml
<samlp:LogoutRequest
    xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    ID="_req-123"
    Version="2.0"
    IssueInstant="2026-11-07T10:00:00Z"
    Destination="https://portal.example.com/logout/saml2/slo">
  <saml:Issuer>https://login.partner-b.example/idp</saml:Issuer>
  <saml:NameID>employee-123</saml:NameID>
  <samlp:SessionIndex>session-b-456</samlp:SessionIndex>
</samlp:LogoutRequest>
~~~

### RP LogoutResponse trả về IdP

~~~xml
<samlp:LogoutResponse
    xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    ID="_resp-789"
    InResponseTo="_req-123"
    Version="2.0"
    IssueInstant="2026-11-07T10:00:01Z"
    Destination="https://login.partner-b.example/saml2/slo/response">
  <saml:Issuer>https://portal.example.com/sp/partner-b</saml:Issuer>
  <samlp:Status>
    <samlp:StatusCode
        Value="urn:oasis:names:tc:SAML:2.0:status:Success"/>
  </samlp:Status>
</samlp:LogoutResponse>
~~~

**Lưu ý:** hai fragment chỉ minh họa vị trí thuộc tính. Chúng **không có chữ ký**, ID ví dụ có thể bị dùng lặp và không có đầy đủ ngữ cảnh trust; **không phải message hợp lệ để triển khai**. Nếu dùng Redirect binding, chữ ký có thể nằm ở query parameters thay vì ngay trong XML. Nếu dùng POST XML signature, cần cấu trúc `ds:Signature` hợp lệ theo OpenSAML. Không sao chép đoạn XML này rồi chấp nhận trong production.

Phân tích:

1. SP nhìn `Issuer=https://login.partner-b.example/idp`: phải tra IdP B đã được đăng ký chứ không tin issuer do XML tự khai báo.
2. SP kiểm chữ ký request bằng public certificate **đã trust cho B**.
3. SP kiểm `Destination` trùng URL public SLO endpoint nhận request.
4. SP kiểm `NameID` / `SessionIndex` phù hợp phiên đang tồn tại theo profile.
5. SP chỉ thu hồi phiên thích hợp **sau khi request đã được chấp nhận**.
6. SP trả LogoutResponse có `InResponseTo="_req-123"` tới đúng endpoint response của IdP B và ký bằng private key của SP.
7. IdP kiểm issuer, signature, destination, correlation và `StatusCode` trước khi kết luận hoàn tất.

## 8. Ràng buộc Issuer và khóa được chọn: không tin một certificate bất kỳ

**`Issuer` là giá trị được khai báo trong message, chưa tự là bằng chứng mật mã.** Đúng cách:

1. Xác định `RelyingPartyRegistration` từ state/session, resolver hoặc thông tin issuer theo một quy trình có kiểm soát.
2. Lấy **Asserting Party Entity ID** mà registration đã cấu hình.
3. Lấy đúng `verificationX509Credentials` của IdP đó.
4. Kiểm signature trên **thông điệp/binding đã nhận**.
5. Kiểm issuer đã ký khớp Entity ID được trust.
6. Kiểm message Destination, correlation, NameID/session và các điều kiện áp dụng.
7. Chỉ sau đó xử lý logout/session.

**Lỗi nguy hiểm:** parse XML lấy certificate dưới `KeyInfo` (nếu có), tự dùng nó verify signature rồi coi IdP đã xác thực. Bất kỳ attacker nào cũng có thể tạo khóa riêng/công khai và ký thông điệp của chính họ. Chữ ký chỉ tạo được **authentication** khi public key được ràng buộc với issuer đã được **phê duyệt từ trước**.

Với nhiều IdP (corp, partner-b, partner-c), mỗi registration có thể có certificate khác. Một signature hợp lệ của IdP C không được phép đóng vai IdP B, ngay cả khi `NameID` và `Destination` trùng nhau. Trong rollover có thể tạm trust đồng thời khóa IdP cũ/mới theo metadata/chính sách đã xác minh, nhưng phải có thời điểm cắt chuyển và giám sát.

## 9. Kiểm InResponseTo, RelayState và chống phản hồi giả

Trong **RP-initiated SLO**, SP phát LogoutRequest `ID=_sp-req-001`. Sau đó IdP trả LogoutResponse chứa:

~~~text
InResponseTo = _sp-req-001
Issuer       = IdP B đã đăng ký
Destination  = SP SLO response URL
Status       = Success hoặc mã lỗi phù hợp
~~~

SP phải đối chiếu với request được lưu trước đó trong `Saml2LogoutRequestRepository`. Spring Security có `HttpSessionLogoutRequestRepository` để lưu request qua session, cho phép kiểm `RelayState` và `InResponseTo` khi response quay lại. Nếu tự thay repository, phải có TTL, session/browser binding, anti-replay và không để response của người dùng khác ghép với request hiện tại.

Kịch bản phải từ chối:

- `InResponseTo` không khớp ID request của SP.
- Không có request đã lưu nhưng response lại được nhận như kết quả RP-initiated.
- Response đã từng dùng bị gửi lại.
- Issuer khác IdP đã chọn cho request gốc.
- `Destination` là URL SLO của SP khác.
- Chữ ký không đúng certificate IdP tin cậy.
- `StatusCode` báo failure/`PartialLogout` nhưng ứng dụng tuyên bố hoàn tất mọi SP.

**RelayState không phải password hay token tự xác thực:** một attacker có thể tác động URL/form từ browser. Chỉ tin kết quả sau khi binding signature, request repository và SAML validation đúng. Không dùng `RelayState` để chọn IdP metadata URL tùy ý.

## 10. Kiểm NameID, SessionIndex và tình trạng phiên

Một LogoutRequest có `NameID` hoặc một loại định danh tương đương để chỉ chủ thể; `SessionIndex` (khi có) giúp chỉ phiên cần logout. Hai trường có ngữ nghĩa SAML:

- `NameID` của IdP có thể là persistent, transient hoặc một định danh scoped khác; **không nhất thiết trùng local username/email** của SP.
- `SessionIndex` do IdP liên kết với phiên xác thực; **không phải JSESSIONID** của app và không nhất thiết là ID session lưu trong Redis.
- Một user có thể có nhiều phiên khác nhau; logout một phiên không tự đồng nghĩa xóa mọi phiên nếu policy/protocol không nói vậy.
- `LogoutResponse` không được dùng như một lệnh tự động logout user bất kỳ; nó là phản hồi cho một request cụ thể.

Khi Spring Security 7 dùng custom principal/authority mapping, cần bảo toàn những dữ liệu SAML còn cần cho SLO. `Saml2AssertionAuthentication` và `Saml2ResponseAssertionAccessor` có thể giúp giữ thông tin assertion/registration mà logout cần. Nếu converter tạo một `UsernamePasswordAuthenticationToken` thuần rồi làm mất NameID/SessionIndex/registration, một bước login thành công vẫn có thể dẫn tới SLO thất bại.

**Bảo mật:** xác minh một AP-initiated LogoutRequest trước khi thu hồi session; yêu cầu đúng issuer/NameID/session theo trạng thái tin cậy. Không xóa mọi session của user chỉ dựa vào một NameID lấy từ XML chưa được xác minh.

## 11. Bước cấu hình tối thiểu trong Spring Boot

Spring Security SAML2 trên Servlet dùng dependency `spring-security-saml2-service-provider`, `RelyingPartyRegistrationRepository`, IdP metadata và credentials đúng phiên bản. Theo hướng dẫn chính thức, SLO cần:

1. IdP B thực sự hỗ trợ Single Logout, thường công bố `<SingleLogoutService>` trong metadata.
2. SP có **signing private key** dạng PKCS#8 và certificate tương ứng để ký message gửi đi.
3. SP biết **verification public certificate của IdP B** để kiểm message đến.
4. SP/IdP thống nhất URL SLO, bindings và signing policy.
5. `saml2Logout(...)` được bật ở `SecurityFilterChain`.

Ví dụ `application.yml` dành cho Spring Boot version có các properties này:

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          partner-b:
            entity-id: "https://portal.example.com/sp/partner-b"
            signing:
              credentials:
                - private-key-location: "classpath:credentials/sp-signing-private.key"
                  certificate-location: "classpath:credentials/sp-signing-public.crt"
            singlelogout:
              url: "https://portal.example.com/logout/saml2/slo"
            assertingparty:
              metadata-uri: "https://login.partner-b.example/metadata"
~~~

Đây là **ví dụ cấu hình**, không có private key/cert thật và miền `.example` không tồn tại. Trong môi trường production, private key phải đến từ cơ chế secret management/keystore được quản trị, không commit vào source. Metadata IdP phải được tải từ nguồn đáng tin và kiểm issuer/certificate; có thể cần cấu hình verification credentials tường minh nếu metadata không sẵn sàng hoặc chính sách doanh nghiệp yêu cầu.

Đường `singlelogout.url` là **SP SLO endpoint công bố**, không phải **IdP SLO destination**. Đích phía IdP thường được lấy từ `<SingleLogoutService>` trong IdP metadata hoặc cấu hình `AssertingPartyMetadata.singleLogoutServiceLocation` và `singleLogoutServiceResponseLocation`.

Khi thay `singlelogout.url`, phải đồng bộ **SP metadata, giao diện IdP và DSL logout endpoint**. Một đoạn YAML đúng riêng lẻ không đủ nếu proxy hoặc IdP vẫn dùng URL cũ.

## 12. Cấu hình SecurityFilterChain và đường SLO mặc định

Ví dụ JavaConfig trong project Spring Security Servlet với registration hợp lệ:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SamlSingleLogoutSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/health").permitAll()
                .anyRequest().authenticated())
            .saml2Login(Customizer.withDefaults())
            .saml2Logout(Customizer.withDefaults())
            .saml2Metadata(Customizer.withDefaults());

        return http.build();
    }
}
~~~

**Điều kiện:** đây là class trong ứng dụng Spring, không tự biên dịch bằng `javac` nếu không có dependencies. `saml2Logout` bật SAML2 SLO trên app; từng registration vẫn cần SLO location và signing credentials theo tài liệu Spring. `saml2Metadata` công bố SP metadata để đối tác đọc thông số SLO.

Trong tài liệu Spring Security SLO hiện hành, các endpoint thường gồm:

| Endpoint | Mục đích |
| --- | --- |
| `POST /logout` | User tại SP bắt đầu RP-initiated logout, theo CSRF/LogoutFilter policy |
| `POST /logout/saml2/slo` với `SAMLRequest` | Nhận IdP-initiated LogoutRequest |
| `POST /logout/saml2/slo` với `SAMLResponse` | Nhận LogoutResponse trả cho SP |
| `GET /saml2/metadata/{registrationId}` khi bật metadata | Xem SP metadata, bao gồm SLO service nếu được cấu hình |

**Lưu ý theo phiên bản:** có sự khác nhau giữa các trang overview/docs về alias SLO hoặc các phương thức GET/POST/bindings. Hãy lấy **version đã resolve** của Spring Security, Javadoc và metadata XML/HTTP request thực tế làm căn cứ cho triển khai; không hardcode một alias khác chỉ dựa vào một trang tutorial. `/logout/saml2/slo` trong bảng là URL được hướng dẫn SLO của Spring Security công bố, không khẳng định mọi custom filter hoặc reverse proxy có cùng route.

### Đổi URL nhận LogoutRequest và LogoutResponse

Ví dụ muốn dùng `/federation/saml/slo`:

~~~java
http.saml2Logout(saml -> saml
        .logoutRequest(request ->
                request.logoutUrl("/federation/saml/slo"))
        .logoutResponse(response ->
                response.logoutUrl("/federation/saml/slo")));
~~~

**Cần thay cả hai nơi** nếu request và response dùng chung URL mới. Đồng thời cập nhật `RelyingPartyRegistration.singleLogoutServiceLocation`, SP metadata và IdP application. Trong ví dụ, `logoutRequest(...).logoutUrl(...)` là nơi nhận **IdP→SP LogoutRequest**, còn `logoutResponse(...).logoutUrl(...)` là nơi nhận **IdP→SP LogoutResponse**; không nhầm với `saml2Logout(saml -> saml.logoutUrl("/saml2/logout"))` là URL **SP khởi tạo logout**.

Một cấu hình custom sai route có thể khiến response đã ký đến đúng public URL nhưng filter không xử lý, trả 404 hoặc redirect login. Không tắt signature validation để sửa mismatch endpoint.

## 13. Cách dựng cấu hình SLO với RelyingPartyRegistration.Builder

Ngoài YAML, JavaConfig có thể tải metadata IdP đã được phê duyệt và khai báo SLO ở phía SP:

~~~java
Saml2X509Credential signingCredential =
        Saml2X509Credential.signing(spPrivateKey, spCertificate);

RelyingPartyRegistration registration = RelyingPartyRegistrations
        .fromMetadataLocation(trustedIdpMetadataUrl)
        .registrationId("partner-b")
        .entityId("https://portal.example.com/sp/partner-b")
        .singleLogoutServiceLocation(
                "https://portal.example.com/logout/saml2/slo")
        .signingX509Credentials(credentials ->
                credentials.add(signingCredential))
        .build();
~~~

Đây là **fragment Java của project Spring**, cần `spPrivateKey`, `spCertificate`, `trustedIdpMetadataUrl` đã tải/xác minh an toàn, imports và repository bean. `Saml2X509Credential.signing` nhận private key + certificate của SP để tạo ký message. `fromMetadataLocation` chỉ nên nhận URL/file metadata được quản trị viên cấu hình, **không** URL do browser gửi vào để tránh SSRF/IdP giả mạo.

Nếu IdP metadata liệt kê các `SingleLogoutService` khác nhau cho request/response, builder hoặc `AssertingPartyMetadata.Builder` có thể tùy chỉnh `singleLogoutServiceLocation`, `singleLogoutServiceResponseLocation` và binding theo đúng phiên bản Spring Security đang chạy.

**Phân biệt:** `RelyingPartyRegistration.Builder.singleLogoutServiceLocation` mô tả SLO endpoint **của SP**, còn `AssertingPartyMetadata.Builder.singleLogoutServiceLocation` mô tả SLO endpoint **của IdP**. Không gán nhầm hai URL.

## 14. Kiểm chữ ký bằng validator chính thức, không viết parser XML thủ công

Spring Security cung cấp:

- `Saml2LogoutRequestFilter` để nhận IdP LogoutRequest.
- `Saml2LogoutResponseFilter` để nhận IdP LogoutResponse.
- `Saml2LogoutRequestValidator` và `Saml2LogoutResponseValidator` để đánh giá message.
- Ở Spring Security 7/OpenSAML 5, các implementation `OpenSaml5LogoutRequestValidator` và `OpenSaml5LogoutResponseValidator` phục vụ kiểm chữ ký, issuer, destination và các ràng buộc phù hợp từng loại message.
- `Saml2LogoutRequestResolver` / `Saml2LogoutResponseResolver` để tạo, ký và serialize message SP gửi ra.
- `Saml2LogoutRequestRepository` để lưu trạng thái request trước khi chờ response.

Tài liệu Spring hướng dẫn dùng validator mặc định và chỉ bổ sung policy riêng nếu thật cần:

~~~java
http.saml2Logout(saml -> saml
        .logoutRequest(request ->
                request.logoutRequestValidator(myRequestValidator))
        .logoutResponse(response ->
                response.logoutResponseValidator(myResponseValidator)));
~~~

Đây là **fragment tùy chỉnh**: `myRequestValidator` và `myResponseValidator` phải là các implementation thật; không có sẵn trong ví dụ. Nếu không có yêu cầu khác mặc định, **không cần cấu hình chúng**. Custom validator nên **ủy quyền cho validator chuẩn trước**, và **nếu nó trả lỗi thì từ chối**, rồi mới chạy thêm rule nghiệp vụ. Không thay validator bằng hàm luôn trả success vì như thế có thể bỏ chữ ký, issuer và destination check.

### Cần bổ sung kiểm nào?

Một ứng dụng B2B có thể yêu cầu:

- Chỉ IdP B được phép điều khiển session của tenant B.
- `NameID`/`SessionIndex` phải liên hệ với SAML-authenticated session đang tồn tại.
- Request quá cũ hoặc `NotOnOrAfter` hết hạn phải bị từ chối theo policy/binding.
- `LogoutResponse@InResponseTo` phải khớp request đã lưu, cùng issuer/registration.
- Chỉ một tập `StatusCode` được phép báo “completed”; `PartialLogout` cần hiển thị khác.
- Trạng thái metadata/certificate rotation không làm nhận các issuer lạ.
- Replay của message ID phải bị từ chối theo chính sách.

Các kiểm tra này là **bổ sung**, không thay việc verify signature và Destination của thư viện. Nếu viết custom parser XML, phải bảo vệ DTD/external entity, canonicalization và signature wrapping; tốt nhất **không tự viết** mà dựa trên API OpenSAML.

## 15. Vì sao chỉ nhìn StatusCode Success là chưa đủ?

Một `LogoutResponse` có:

~~~xml
<samlp:Status xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol">
  <samlp:StatusCode
      Value="urn:oasis:names:tc:SAML:2.0:status:Success"/>
</samlp:Status>
~~~

đã khai báo `Success`, nhưng bất kỳ người gửi chưa được tin cậy nào cũng có thể dựng XML trông như vậy. Muốn tin rằng đây là phản hồi của IdP B cho request của SP A, phải kiểm:

1. Chữ ký đúng IdP B/certificate đã trust.
2. `Issuer` khớp IdP B.
3. `Destination` khớp SLO response URL của SP.
4. `InResponseTo` khớp LogoutRequest ID đã lưu trong giao dịch đang chờ.
5. `RelayState`/browser session phù hợp, nếu được sử dụng.
6. Status được parse đúng chuẩn và phù hợp ngữ cảnh.
7. Message không bị replay và thời hạn/hệ thống không bất thường.

Không kết luận “logout toàn bộ thành công” từ `HTTP 302`, `StatusCode=Success` chưa được xác minh, hoặc chỉ từ việc session của SP đã bị invalidate. Khi IdP trả `PartialLogout`, cần phân biệt thông báo “đã đăng xuất ứng dụng hiện tại” với “đăng xuất tại mọi dịch vụ”.

## 16. Reverse proxy và hostname: nguyên nhân Destination sai phổ biến

Giả sử Java service chạy nội bộ ở:

~~~text
http://sp-backend:8080
~~~

Trong khi IdP biết URL công khai:

~~~text
https://portal.example.com/logout/saml2/slo
~~~

Nếu ứng dụng sinh `Destination` hay metadata từ `{baseUrl}` nội bộ, IdP có thể từ chối request gửi tới địa chỉ không đúng. Ngược lại, IdP gửi LogoutRequest với Destination public mà backend tự lấy Host header nội bộ để so sánh có thể dẫn tới lỗi nếu proxy forwarding không được cấu hình đúng.

Cách xử lý:

1. Chốt scheme/host/port/path public SLO ở cả SP và IdP.
2. Đặt `singleLogoutServiceLocation`/`ResponseLocation` theo public URL cố định hoặc placeholders đã kiểm tra.
3. Chỉ nhận `Forwarded`/`X-Forwarded-*` từ **reverse proxy tin cậy**, loại bỏ header do Internet tự gửi để tránh host-header injection.
4. Đảm bảo proxy chuyển đúng HTTP POST/Redirect binding, không xóa param `SAMLRequest`, `SAMLResponse`, `RelayState`, `SigAlg` hoặc `Signature`.
5. Với HTTP-Redirect signature, tránh mọi rewrite khiến query-encoding không còn giống chuỗi đã ký.
6. Kiểm SP metadata qua URL public, đối chiếu `<SingleLogoutService>` với IdP registration.
7. Test cả RP-initiated và AP-initiated sau deploy, không chỉ kiểm endpoint có HTTP 200.

**Không tắt Destination validation để “sửa” lỗi proxy.** Hãy sửa metadata, public URL và proxy forwarding/trust headers đúng cách.

## 17. Chứng thư, thuật toán ký và key rotation

Một triển khai production cần quy trình:

- **Key generation:** SP tạo private signing key trong HSM/keystore/vault phù hợp; certificate public được cung cấp cho IdP.
- **IdP trust:** SP lấy public signing certificates của IdP từ metadata được xác minh hoặc kênh chính thức.
- **Key rotation:** hỗ trợ khóa cũ/mới trong giai đoạn chuyển tiếp có giới hạn khi đối tác cho phép; có owner, lịch và rollback.
- **Algorithm policy:** ưu tiên thuật toán hiện đại phù hợp Spring/OpenSAML và IdP, không mở rộng tự do SigAlg/SHA-1 chỉ vì gặp lỗi.
- **Certificate expiration:** giám sát hạn certificate và chuỗi tin cậy theo chính sách, phân biệt lỗi chữ ký với lỗi hết hạn của chứng thư.
- **Secret handling:** không log private key, không commit vào repo, không đặt key trong một endpoint metadata public.
- **Multiple IdPs:** mỗi registration dùng đúng certificate issuer đã được phê duyệt.
- **Deployment consistency:** nhiều node SP phải dùng cùng cấu hình trust/keys cần thiết, tránh node A ký bằng key mới nhưng IdP chưa trust hoặc node B vẫn dùng metadata cũ.

Việc một certificate IdP vẫn xuất hiện trong metadata HTTP không tự đủ để tin: phải xác minh endpoint/metadata signature/trust channel. Nếu IdP bị thay đổi signing cert ngoài kế hoạch, đừng tự lấy certificate mới từ Response và chấp nhận ngay.

## 18. Java 17 độc lập: hiểu ký–kiểm chữ ký và Destination

Chương trình sau dùng **Java Cryptography Architecture (JCA)** để cho thấy: bên gửi ký một chuỗi bằng private key; bên nhận kiểm bằng public key đã được chọn trước; thay nội dung, đổi public key hoặc sai destination khiến kết quả kiểm thay đổi.

**Quan trọng:** đây là *demo giáo dục trên byte string*, **không phải SAML XML Signature hoặc chữ ký HTTP-Redirect binding**. Mã không parse SAML XML, không xử lý DEFLATE/Base64/RelayState, không kiểm SignedInfo/reference/canonicalization, không phải SLO implementation. Trong sản phẩm thật, bắt buộc dùng Spring Security/OpenSAML validators.

Tạo file `SamlLogoutSignatureDemo.java`:

~~~java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.PrivateKey;
import java.security.PublicKey;
import java.security.Signature;
import java.util.Objects;

public class SamlLogoutSignatureDemo {

    static byte[] sign(String payload, PrivateKey privateKey)
            throws GeneralSecurityException {
        Signature signature = Signature.getInstance("SHA256withRSA");
        signature.initSign(privateKey);
        signature.update(payload.getBytes(StandardCharsets.UTF_8));
        return signature.sign();
    }

    static boolean verify(
            String payload, byte[] signed, PublicKey publicKey)
            throws GeneralSecurityException {
        Signature signature = Signature.getInstance("SHA256withRSA");
        signature.initVerify(publicKey);
        signature.update(payload.getBytes(StandardCharsets.UTF_8));
        return signature.verify(signed);
    }

    static boolean correctDestination(
            String actual, String expectedPublicEndpoint) {
        return expectedPublicEndpoint.equals(actual);
    }

    static boolean correlates(
            String inResponseTo, String storedRequestId) {
        return storedRequestId != null
                && Objects.equals(inResponseTo, storedRequestId);
    }

    public static void main(String[] args)
            throws GeneralSecurityException {

        KeyPairGenerator generator = KeyPairGenerator.getInstance("RSA");
        generator.initialize(2048);

        KeyPair trustedIdp = generator.generateKeyPair();
        KeyPair unrelatedParty = generator.generateKeyPair();

        String destination =
                "https://portal.example.com/logout/saml2/slo";
        String logoutRequest = "LogoutRequest|ID=_idp-req-1"
                + "|Issuer=https://idp.partner-b.example"
                + "|Destination=" + destination;

        byte[] signed = sign(logoutRequest, trustedIdp.getPrivate());

        System.out.println("Trusted signature: " + verify(
                logoutRequest, signed, trustedIdp.getPublic()));

        System.out.println("Tampered message accepted: " + verify(
                logoutRequest + "|NameID=another-user",
                signed,
                trustedIdp.getPublic()));

        System.out.println("Wrong key accepted: " + verify(
                logoutRequest, signed, unrelatedParty.getPublic()));

        System.out.println("Expected destination: "
                + correctDestination(destination, destination));

        System.out.println("Wrong destination accepted: "
                + correctDestination(
                    "https://other-sp.example.com/logout/saml2/slo",
                    destination));

        System.out.println("Matching InResponseTo: "
                + correlates("_sp-req-100", "_sp-req-100"));

        System.out.println("Wrong InResponseTo accepted: "
                + correlates("_sp-req-999", "_sp-req-100"));
    }
}
~~~

Dùng JDK 17 trở lên:

~~~bash
javac SamlLogoutSignatureDemo.java
java SamlLogoutSignatureDemo
~~~

**Stdout chính xác** (RSA keys khác nhau mỗi lần chạy, nhưng kết quả Boolean giống nhau):

~~~text
Trusted signature: true
Tampered message accepted: false
Wrong key accepted: false
Expected destination: true
Wrong destination accepted: false
Matching InResponseTo: true
Wrong InResponseTo accepted: false
~~~

Giải thích:

- `Trusted signature: true`: chữ ký khớp **đúng public key** tương ứng private key đã ký.
- `Tampered message accepted: false`: sửa nội dung đã ký khiến kiểm chữ ký thất bại.
- `Wrong key accepted: false`: public key không thuộc signer không được chấp nhận.
- `Expected destination: true`: so khớp URL SLO public được cấu hình.
- `Wrong destination accepted: false`: destination của SP khác phải bị từ chối theo policy.
- `Matching InResponseTo: true`: phản hồi chỉ khớp với request đã lưu.
- `Wrong InResponseTo accepted: false`: một response liên hệ request khác không hợp lệ.

**Không được lấy `correctDestination` và `verify` của demo đem áp dụng trực tiếp cho production SAML.** URL canonicalization/forwarded headers, binding signature, XML ID/reference validation, issuer, time, replay và session được xử lý bởi thư viện SAML. Chương trình tạo RSA key tạm cho phép thử và không lưu private key xuống đĩa.

## 19. Kiểm thử tích hợp để thực sự chứng minh SLO an toàn

Một bộ test cần bao gồm **cả hai chiều RP-initiated/AP-initiated** và nhiều phép thử âm tính:

| Test | Đầu vào | Kết quả kỳ vọng |
| --- | --- | --- |
| RP-initiated happy path | User đã SAML login, POST logout có CSRF | SP ký LogoutRequest, IdP verify, trả LogoutResponse hợp lệ |
| AP-initiated happy path | IdP ký LogoutRequest đúng issuer/đích | SP verify rồi logout đúng phiên, ký LogoutResponse |
| Signature của IdP sai | SAMLRequest bị sửa hoặc ký bằng key lạ | Từ chối, không thực hiện logout theo request giả |
| Signature của SP sai | IdP nhận request/response không khớp cert SP | IdP từ chối, cảnh báo cấu hình key |
| Redirect query thay đổi | Sửa `RelayState` hoặc `SigAlg` trong message đã ký | Chữ ký binding không hợp lệ, từ chối |
| POST XML signature wrapping | Message có payload sai tham chiếu signed element | Không chấp nhận nội dung giả/mạo |
| Issuer lạ | IdP C ký nhưng route/registration B | SP không coi là IdP B |
| Destination sai | Signed request của B gửi cho SP C | SP A từ chối |
| URL proxy sai | Destination `http://internal:8080` vs HTTPS public | Test fail, sửa public metadata/forwarding |
| Response correlation sai | `InResponseTo` khác stored request ID | Không coi logout của giao dịch này thành công |
| RelayState khác session | Response gửi tới browser khác | Không ghép sai giao dịch |
| Replay message | Dùng lại ID LogoutRequest/Response | Từ chối theo anti-replay policy |
| Sai NameID/SessionIndex | IdP B yêu cầu logout session không thuộc principal | Không hủy nhầm phiên/tài khoản |
| Status `PartialLogout` | Một SP khác không hoàn tất | Phân biệt incomplete với global success |
| Expired request | `NotOnOrAfter` đã qua nếu sử dụng | Bị từ chối theo profile/policy |
| IdP certificate rotation | Chuyển cert đã phê duyệt | Chỉ key trong trust set mới được chấp nhận |
| SP signing rotation | IdP cập nhật SP public cert | Verify request/response đúng sau cutover |
| POST/Redirect binding | Mỗi binding được đối tác hỗ trợ | Verify đúng loại signature và endpoint |
| SLO endpoint mới | DSL + metadata + IdP cùng URL | Request/response đến đúng filter |
| Logout không có SAML session | User local login/anonymous | Không gửi LogoutRequest không phù hợp |
| Local session đã hủy | IdP SLO failure/network timeout | App xử lý và báo khác kết quả global SLO |
| Nhiều IdP | User B/IdP C có NameID giống | Không logout hoặc gửi response sai đối tác |

**Kiểm thử "request có chữ ký" chưa đủ.** Cần tạo các SAML message được ký bằng cert hợp lệ nhưng gửi **sai destination**, **sai InResponseTo** hoặc **sai NameID**; như vậy mới chứng minh validator kiểm những phần ngoài chữ ký.

### Cách xác minh trong staging

1. Mở SP metadata `/saml2/metadata/partner-b` nếu đã bật; kiểm `SPSSODescriptor/SingleLogoutService` về binding và location.
2. Kiểm IdP metadata có `IDPSSODescriptor/SingleLogoutService` và certificate hợp lệ.
3. Login vào SP bằng IdP thử nghiệm để có SAML session đúng.
4. POST logout với CSRF token hợp lệ; dùng công cụ developer/test proxy có kiểm soát để xem luồng redirect/form.
5. Kiểm `SAMLRequest` gửi tới đúng IdP SLO request endpoint.
6. IdP verify signature và trả `SAMLResponse` có `InResponseTo` phù hợp.
7. SP xác minh bằng `Saml2LogoutResponseValidator`, xử lý status và redirect ứng dụng.
8. Lặp lại bằng IdP-initiated, sai chữ ký, sai destination và response replay.
9. Kiểm session app thực sự mất hiệu lực và những service liên kết khác trả trạng thái phù hợp.
10. Kiểm log chỉ ghi mã lỗi an toàn và correlation ID, không có raw SAML message chứa dữ liệu người dùng.

Mọi lệnh HTTP cần endpoint và certificate thật. `curl -i https://portal.example.com/saml2/metadata/partner-b` chỉ là ví dụ đọc metadata; không có XML stdout cố định để chép từ bài học.

## 20. Phân biệt CSRF với SAML signature

Có **hai lớp bảo vệ khác nhau**:

- **CSRF token** của ứng dụng bảo vệ lệnh logout nội bộ như `POST /logout` khỏi một trang web khác ép người dùng gửi request.
- **SAML signature** bảo vệ thông điệp SLO đi qua browser giữa SP và IdP, chứng minh bên ký có quyền và nội dung không bị sửa theo profile.

Khi IdP gửi `SAMLRequest` hoặc `SAMLResponse` tới SP SLO endpoint, đó là POST cross-site theo giao thức. Spring Security có logic xử lý SAML logout; nếu tùy chỉnh endpoint/CSRF policy, cần kiểm exception hẹp tương ứng, **không tắt CSRF toàn ứng dụng** chỉ để tránh lỗi 403.

Một attacker gửi `POST /logout/saml2/slo` giả mạo không được cho phép chỉ nhờ thiếu CSRF token: endpoint này bắt buộc phải **xác minh SAML signature, issuer và destination** theo policy. Ngược lại, một `POST /logout` có CSRF hợp lệ không tự chứng minh SLO từ IdP đã hoàn thành.

## 21. Lỗi thường gặp và hướng xử lý

| Triệu chứng | Nguyên nhân thường gặp | Xử lý đúng |
| --- | --- | --- |
| IdP không hỗ trợ SLO | Metadata không có `SingleLogoutService` | Xác minh khả năng, không tự hứa global logout |
| Không có LogoutRequest gửi tới IdP | Chưa bật `saml2Logout`, registration thiếu SLO, principal thiếu context | Kiểm filter chain, metadata và SAML Authentication |
| "Signature invalid" tại IdP | SP dùng key sai/đã rotate/binding ký sai | Đồng bộ public certificate SP và signing configuration |
| "Signature invalid" tại SP | IdP cert không khớp/đổi ngoài kế hoạch | Cập nhật verification creds từ metadata tin cậy |
| Redirect signed query lỗi | Proxy rewrite/encode lại tham số đã ký | Giữ đúng binding canonical input; test wire request |
| XML ký đúng key nhưng bị từ chối | Issuer, Destination, correlation hoặc status sai | Kiểm rule tương ứng, không tắt signature validation |
| Invalid Destination | Public URL và metadata/proxy sai | Đồng bộ SLO public host/path/binding |
| LogoutResponse không được xác minh | Mất request repository/session/RelayState hoặc InResponseTo sai | Kiểm request correlation và browser session |
| Logout nhầm user | Không kiểm NameID/SessionIndex hoặc tenant | Ràng buộc vào session đã xác minh |
| Local logout thành công nhưng IdP còn phiên | SLO không được bật hoặc network/IdP lỗi | Phân biệt local/global, xử lý fallback và thông báo trung thực |
| `PartialLogout` bị báo success | Chỉ xem HTTP status hay parse một string | Đánh giá StatusCode đã xác minh đúng chính sách |
| Endpoint logout 404/405 | SLO URL giữa DSL, metadata và IdP không đồng bộ | Cập nhật cả ba, test POST/Redirect |
| SLO chạy trên node A nhưng fail B | Key/trust metadata hoặc session repo không đồng bộ | Kiểm deploy/keystore/session sharing |
| SAMLResponse chứa data nhạy cảm trong log | Debug log raw payload | Rút log, audit và bảo vệ dữ liệu |
| User đã local logout nhưng bị SSO lại | IdP session còn sống | Xem RP-initiated SLO, không mặc định logout mọi nơi |

Không sửa sự cố bằng cách bỏ verify signature hoặc cho phép mọi Destination. Cần xác định **bước nào** thất bại: chọn registration, xác minh chữ ký, issuer/destination, request correlation, session mapping hay IdP SLO support.

## 22. Runbook triển khai an toàn

1. **Chốt contract SP–IdP:** Entity IDs, SLO request/response URLs, bindings, signing algorithms và các chứng thư tin cậy.
2. **Xác minh metadata:** IdP có SingleLogoutService; SP metadata công bố đúng SP endpoint.
3. **Quản lý secret:** SP private key dạng PKCS#8 có quy trình truy cập/rotation, chỉ public cert đưa đối tác.
4. **Bật SLO đúng Spring version:** dependency SAML2 SP, `RelyingPartyRegistrationRepository` và `saml2Logout`.
5. **Không mất SAML principal context:** giữ NameID/SessionIndex/accessor khi custom mapping đăng nhập.
6. **Test RP-initiated:** POST logout có CSRF; SP ký Request; IdP trả Response; SP verify/correlate/status.
7. **Test AP-initiated:** IdP ký Request; SP verify trước logout; SP ký Response về đúng IdP.
8. **Negative tests:** sai chữ ký/key/issuer/destination/response request ID/session/replay/algorithms.
9. **Kiểm reverse proxy:** HTTPS public URL, trusted forwarded headers, query string preservation.
10. **Theo dõi:** số lượng SLO success/failure/partial, lỗi signature và destination, thời gian chờ IdP.
11. **Rollback:** giữ cấu hình/cert cũ trong thời hạn được phê duyệt và cách chuyển endpoint.
12. **Thông báo kết quả chính xác:** local logout khác SLO toàn mạng; không khẳng định đã kết thúc các phiên không có xác nhận.

## 23. Những điểm dễ nhầm nhất — hỏi nhanh đáp gọn

**Hỏi:** LogoutRequest ký đúng có đủ để SP logout người dùng không?

**Đáp:** Không. Cần issuer được trust, Destination phù hợp, NameID/session đúng, lifetime/replay policy và các điều kiện profile. Chữ ký không tự chọn user nào bị logout.

**Hỏi:** SP có phải dùng certificate của IdP để ký LogoutResponse không?

**Đáp:** Không. SP dùng **private key SP** để ký; IdP dùng **public certificate SP** để verify. Certificate IdP được SP dùng verify message IdP gửi.

**Hỏi:** Vì sao LogoutRequest với `Destination=https://other-sp.example.com/slo` bị từ chối dù chữ ký IdP B hợp lệ?

**Đáp:** Message được ký **cho một đích khác**. SP A không được dùng nó như lệnh dành cho mình.

**Hỏi:** Có thể lấy certificate từ chính XML LogoutRequest để kiểm chữ ký không?

**Đáp:** Không thể dùng certificate đó làm trust anchor một cách tự động. Phải so với verification credentials của IdP đã đăng ký trước.

**Hỏi:** `Recipient` có nằm ở mọi LogoutRequest không?

**Đáp:** Không. `Recipient` thường được bàn tới ở bearer `SubjectConfirmationData` của Assertion đăng nhập. Với logout, kiểm `Destination` và SLO metadata/endpoint phù hợp.

**Hỏi:** LogoutResponse `StatusCode=Success` có chứng minh global SLO đã xong không?

**Đáp:** Chỉ sau khi kiểm chữ ký, issuer, destination, correlation và hiểu phạm vi response. Ngay cả khi IdP báo success, ứng dụng cần thông báo theo hợp đồng và không giả định mọi hệ thống ngoài phạm vi đều đã kết thúc phiên.

**Hỏi:** Có nên tự tạo XML Digital Signature để “chủ động” không?

**Đáp:** Không. XML signature và Redirect signature có nhiều quy tắc riêng, dễ dẫn đến signature wrapping hoặc sai canonicalization. Ưu tiên Spring Security/OpenSAML.

## 24. Tài liệu tham khảo chính thức

1. [Spring Security — Performing Single Logout](https://docs.spring.io/spring-security/reference/servlet/saml2/logout.html): cấu hình tối thiểu, RP/AP-initiated, request/response filter/resolver/validator, endpoints và request repository.
2. [Spring Security — SAML 2.0 Login Overview](https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html): chuỗi xác thực, registration và sự phân biệt SSO/SLO; đối chiếu URL với dòng version.
3. [Spring Security API — Saml2LogoutRequestFilter](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/saml2/provider/service/web/authentication/logout/Saml2LogoutRequestFilter.html): filter tiếp nhận IdP-initiated request.
4. [Spring Security API — Saml2LogoutRequestRepository](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/saml2/provider/service/web/authentication/logout/Saml2LogoutRequestRepository.html): lưu và tìm LogoutRequest cho correlation.
5. [Spring Security API — Saml2LogoutRequestResolver](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/saml2/provider/service/web/authentication/logout/Saml2LogoutRequestResolver.html): tạo, ký và serialize request gửi IdP.
6. [Spring Security API — RelyingPartyRegistration.Builder](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/saml2/provider/service/registration/RelyingPartyRegistration.Builder.html): SP SLO service locations/bindings và signing credentials.
7. [Spring Security API — AssertingPartyMetadata.Builder](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/saml2/provider/service/registration/AssertingPartyMetadata.Builder.html): IdP SLO request/response locations, bindings và verification certificates.
8. [OASIS — SAML 2.0 Technical Overview](https://docs.oasis-open.org/security/saml/Post2.0/sstc-saml-tech-overview-2.0.html): luồng Single Logout và vai trò ký, NameID, SessionIndex.
9. [OASIS — SAML 2.0 Core](https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf): LogoutRequest/LogoutResponse, `Destination`, `InResponseTo`, `StatusCode` và thời hạn request.
10. [OASIS — SAML 2.0 Bindings](https://docs.oasis-open.org/security/saml/v2.0/saml-bindings-2.0-os.pdf): HTTP-Redirect signature (`SigAlg`, `Signature`) và POST XML Signature.

**Ghi nhớ cuối cùng:** **ký** bảo vệ tính toàn vẹn và chứng minh bên gửi có private key; **xác minh bằng certificate tin cậy** ràng buộc message với đúng SP/IdP; **kiểm Destination** và `InResponseTo` bảo đảm message dành cho đúng endpoint và đúng giao dịch. Trong SAML2 SLO, ba lớp này phải phối hợp với issuer, NameID/SessionIndex, time/replay và trạng thái logout; không được bỏ một lớp để giải quyết lỗi tích hợp.