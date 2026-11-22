# Phân biệt đăng xuất cục bộ với Single Logout liên kết trong SAML 2.0

> **Chủ đề:** Spring Security – federation · **Nhóm:** Đăng xuất SAML2. Bài học giải thích ranh giới giữa **local logout** tại một Service Provider và **SAML 2.0 Single Logout (SLO)** trên toàn quan hệ liên kết, cách Spring Security Servlet xử lý hai luồng, các trường NameID/SessionIndex, metadata và chứng thư cần thiết, giới hạn của “đăng xuất mọi nơi”, cách kiểm thử và xử lý sự cố.

## 1. Vì sao “Đăng xuất” là một quyết định kiến trúc?

Một người dùng đăng nhập vào **ứng dụng A** (Spring Security Service Provider, SP A) thông qua **Identity Provider (IdP)** và đồng thời vào **ứng dụng B** (SP B) cùng IdP. Lúc đó có thể tồn tại ba phiên khác nhau:

- **Phiên cục bộ ở SP A:** thường gắn với HttpSession/cookie, Spring SecurityContext và Authentication đã được tạo từ SAML Assertion.
- **Phiên SSO ở IdP:** cho phép IdP xác thực người dùng trong một thời gian nhất định, kể cả khi một SP đã xóa phiên riêng.
- **Phiên cục bộ ở SP B:** do SP B sở hữu, có cookie, TTL và session repository riêng.

Nếu A chỉ xóa phiên của mình, IdP và B **có thể vẫn còn đăng nhập**. Khi quay lại A, trình duyệt đi tới IdP và IdP có thể phát SAMLResponse mới không yêu cầu người dùng nhập lại mật khẩu. Do đó người dùng dễ nghĩ “tôi đã logout mà lại tự đăng nhập”.

Ngược lại, **SAML Single Logout** là **giao thức hợp tác**, trong đó SP và IdP gửi các thông điệp `LogoutRequest`/`LogoutResponse` để cố gắng đóng các phiên liên quan. SLO không phải phương thức để JavaScript xóa cookie của mọi domain và không mặc định thu hồi mọi JWT/API token hay mọi phiên trên thiết bị khác.

**Ghi nhớ:**
- **Local logout = kết thúc Authentication/phiên ở đúng ứng dụng SP hiện tại.**
- **Federated Single Logout = yêu cầu các bên tham gia quan hệ SAML đóng những phiên tương ứng; kết quả phụ thuộc khả năng xử lý và trạng thái phản hồi của từng bên.**

Một sản phẩm tốt nên ghi rõ người dùng đang **“Đăng xuất khỏi ứng dụng này”** hay **“Đăng xuất khỏi phiên SSO liên kết”**.

## 2. Các thuật ngữ và đối tượng phiên

| Thuật ngữ | Định nghĩa thực tế |
|---|---|
| **Service Provider (SP/Relying Party)** | Ứng dụng Java Spring Security xác thực qua Assertion từ IdP |
| **Identity Provider (IdP/Asserting Party)** | Hệ thống xác thực người dùng và điều phối SSO/SLO nếu hỗ trợ |
| **Local Logout** | Chạy logout handlers, chấm dứt session/SecurityContext của SP |
| **SAML 2.0 Single Logout (SLO)** | Giao thức yêu cầu chấm dứt những SAML sessions liên quan |
| **RP-initiated SLO** | SP khởi tạo, gửi LogoutRequest tới IdP |
| **AP-initiated SLO** | IdP khởi tạo, gửi LogoutRequest tới SP |
| **`LogoutRequest`** | Thông điệp logout có Issuer, ID, NameID, SessionIndex và các trường protocol |
| **`LogoutResponse`** | Kết quả phản hồi có StatusCode và thường có InResponseTo |
| **`NameID`** | Định danh chủ thể được IdP dùng trong SAML Assertion và logout |
| **`SessionIndex`** | Chỉ số phiên SAML trong AuthnStatement, có thể dùng để chọn phiên cần logout |
| **`InResponseTo`** | Tham chiếu ID của LogoutRequest mà LogoutResponse trả lời |
| **`RelayState`** | Tham số binding giúp giữ state/correlation, không phải URL tự động đáng tin |
| **`SingleLogoutService`** | Endpoint/binding được công bố trong metadata SAML |
| **`PartialLogout`** | Trạng thái báo quy trình không chấm dứt được tất cả participant |
| **`RelyingPartyRegistration`** | Đăng ký trust SP↔IdP, SLO endpoint và credentials trong Spring Security |

**Quan trọng:** `SessionIndex` **không phải** `JSESSIONID` hoặc `HttpSession.getId()` của ứng dụng. `LogoutRequest.ID` cũng không phải SessionIndex. Chúng dùng cho các trách nhiệm khác nhau; trộn lẫn khiến logout sai người dùng hoặc không tương quan được response.

## 3. Bảng so sánh Local Logout và SAML SLO

| Tiêu chí | Local Logout | Federated SAML Single Logout |
|---|---|---|
| Điểm khởi tạo | Nút logout trong một SP | SP hoặc IdP theo profile SLO |
| Thông điệp SAML | Không bắt buộc | LogoutRequest và LogoutResponse |
| Phiên hiện tại tại SP | Thường bị invalidate | Bị invalidate như một phần của quy trình |
| Phiên SSO của IdP | Thường **giữ nguyên** | IdP được yêu cầu chấm dứt phiên phù hợp |
| Phiên ở SP khác | Thường **giữ nguyên** | Có thể được IdP thông báo và yêu cầu đóng |
| Có phụ thuộc IdP SLO support? | Không | Có |
| Có cần signing credential SAML? | Không riêng cho local logout | Thường cần cho request/response đã ký |
| Có cần NameID/SessionIndex? | Không riêng cho local logout | Có để xác định chủ thể/phiên |
| Có xác nhận SLO status? | Không | Có thể có Success/PartialLogout/failure/không phản hồi |
| Phụ thuộc browser và nhiều endpoint | Ít hơn | Có; nhất là front-channel Redirect/POST |
| Đăng nhập lại im lặng qua IdP | Có thể xảy ra | Ít hơn nếu IdP session thực sự kết thúc |
| Thu hồi mọi access token/JWT? | Không tự động | Cũng không tự động |
| Xóa phiên các thiết bị khác? | Không | Không được mặc định bảo đảm |
| Thông báo UI chính xác | “Đã đăng xuất khỏi ứng dụng này” | “Đã xác nhận/đang xử lý/chưa hoàn tất đăng xuất liên kết”, tùy kết quả |

Từ “**Single**” trong Single Logout nói tới **một quy trình phối hợp** trong federation, không phải lời hứa mật mã rằng mọi ứng dụng, mọi browser và mọi token đã mất hiệu lực.

## 4. Local logout ở Spring Security Servlet hoạt động ra sao?

### 4.1. Điều gì xảy ra khi POST /logout?

Trong ứng dụng Spring Security Servlet, khi cấu hình logout thông thường và CSRF hoạt động, một `POST /logout` đã được cho phép thường:

1. Gọi các `LogoutHandler` của filter chain.
2. Invalidate HttpSession hiện hành, theo cấu hình mặc định của session-based authentication.
3. Xóa hoặc làm rỗng `SecurityContext` và Authentication gắn với phiên.
4. Xử lý CSRF token và những logout handlers khác.
5. Gọi `LogoutSuccessHandler` hoặc redirect đến URL thành công (ví dụ `/login?logout`).

Thành phần phổ biến có `SecurityContextLogoutHandler`, xử lý session invalidation/clear authentication. Nếu ứng dụng dùng custom cookies, remember-me hoặc tokens riêng, có thể cần các logout handlers chuyên biệt; **xóa SecurityContext không tự thu hồi toàn bộ token ngoài phiên**.

Không được mặc định rằng xóa HttpSession sẽ xóa cookie của browser ngay lập tức. Cookie `JSESSIONID` có thể còn trong browser nhưng tham chiếu một session đã vô hiệu hóa; ứng dụng có thể cấu hình cookie cleanup phù hợp. Đừng nhầm “cookie vẫn hiển thị” với “session vẫn sống”.

### 4.2. Sơ đồ local logout

~~~text
Browser                      Spring SP A                    IdP             SP B
   |                            |                           |               |
   | POST /logout + CSRF       |                           |               |
   +--------------------------->|                           |               |
   |                            | Invalidate HttpSession    |               |
   |                            | Clear SecurityContext     |               |
   |<---- /signed-out ----------+                           |               |
   |                                                        |               |
   |            Không gửi SAML LogoutRequest tới IdP        |               |
   |            IdP session / SP B session có thể còn sống  |               |
~~~

Nếu browser sau đó truy cập trang cần Authentication ở SP A, SP A có thể chuyển sang IdP và nhận Assertion mới bằng **SSO session còn sống**. Đây là lý do local logout không đáp ứng yêu cầu “đăng xuất mọi ứng dụng”.

### 4.3. Local logout phù hợp khi nào?

- Người dùng chỉ muốn thoát khỏi ứng dụng hiện tại, không làm gián đoạn các hệ thống khác.
- IdP không hỗ trợ SAML SLO hoặc hệ thống chưa xác minh SLO ổn định.
- Chính sách tổ chức cố tình tách hành vi “rời ứng dụng” khỏi “kết thúc toàn bộ phiên SSO”.
- Ứng dụng xử lý business session riêng và người dùng cần lưu phiên ở các trang khác.
- Có một nút riêng yêu cầu người dùng xác nhận nếu họ muốn chấm dứt các phiên liên kết.

**Giới hạn:** Nếu máy tính được chia sẻ hoặc yêu cầu an ninh là kết thúc IdP session, local logout một mình chưa đủ. Cần đánh giá SLO, IdP logout/session revocation, account/session policies và quản lý thiết bị.

## 5. Single Logout có hai hướng khởi tạo

Spring Security hỗ trợ SAML 2.0 SLO trong ứng dụng **Servlet Service Provider**, bao gồm **RP-initiated** và **AP-initiated** theo tài liệu.

### 5.1. RP-initiated: người dùng bắt đầu logout tại SP

Luồng khái quát:

~~~text
Browser                  Spring SP A                     IdP                 SP B
  |                          |                          |                   |
  | POST /saml2/logout      |                          |                   |
  +------------------------->|                          |                   |
  |                          | Clear A local session    |                   |
  |                          | Create/signed             |                   |
  |                          | LogoutRequest             |                   |
  |<----- Redirect / form ---+                          |                   |
  +------------------------------- LogoutRequest ------>|                   |
  |                                                     | Verify request    |
  |                                                     | End IdP session   |
  |                                                     +-- LogoutRequest ->|
  |                                                     |                   | Verify/clear
  |                                                     |<-- LogoutResponse-+
  |<-------------------- LogoutResponse -----------------+                   |
  +--- POST /logout/saml2/slo --> SP A                                      |
  |                                  Verify signature, status, correlation  |
  |<----------------------------- Final page (nếu callback hợp lệ) --------+
~~~

Theo Spring Security documentation, khi SLO **được bật theo cấu hình thông thường**, một `POST /logout` có thể **kích hoạt RP-initiated SLO**: SP chạy các logout handlers rồi tạo SAML LogoutRequest và chuyển sang IdP. Điều này khác với trường hợp chỉ cấu hình logout thường.

**Vì vậy:** Muốn cung cấp cả **local** và **federated logout**, hãy dùng **hai endpoint tách biệt**, như phần cấu hình ở mục 9.

### 5.2. AP-initiated: IdP yêu cầu SP logout

~~~text
IdP / Browser                   Spring SP A
    |                                 |
    +----- signed LogoutRequest ----->|
    |                                 | Verify issuer/signature
    |                                 | Validate destination,
    |                                 | NameID/SessionIndex, replay
    |                                 | Invalidate matching local session
    |                                 | Create signed LogoutResponse
    |<----------- LogoutResponse -----+
    |
    +----- IdP điều phối sang SP khác nếu có
~~~

SP nhận một LogoutRequest do IdP khởi tạo tại SLO endpoint, kiểm kỹ trước khi xóa session phù hợp. Sau khi SP trả LogoutResponse, **browser nằm dưới điều khiển của IdP**, nên không thể giả định redirect success page của SP sẽ là trang cuối người dùng nhìn thấy.

**Lưu ý triển khai:** Một số nhà cung cấp dùng HTTP-Redirect cho SLO, một số dùng HTTP-POST, có thể có back-channel SOAP. Không tất cả IdP/SP hỗ trợ cùng binding; phải đối chiếu metadata và tài liệu đối tác. Spring Security Servlet SLO là một tính năng cụ thể, không tự hỗ trợ mọi profile/binding có trong tiêu chuẩn.

## 6. LogoutRequest chứa gì?

Mẫu XML **rút gọn để minh họa trường**, không có chữ ký thực/metadata đủ nên **không dùng như SAML message production**:

~~~xml
<samlp:LogoutRequest
    xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    ID="_logout_request_001"
    Version="2.0"
    IssueInstant="2026-11-07T04:00:00Z"
    Destination="https://idp.example.org/saml/slo">
  <saml:Issuer>https://portal.example.org/saml/sp</saml:Issuer>
  <saml:NameID
      Format="urn:oasis:names:tc:SAML:2.0:nameid-format:persistent">
    stable-subject-id
  </saml:NameID>
  <samlp:SessionIndex>_session_100</samlp:SessionIndex>
</samlp:LogoutRequest>
~~~

Những thành phần cần hiểu:

| Trường | Ý nghĩa |
|---|---|
| `ID` | Định danh thông điệp để đối chiếu LogoutResponse, chống reuse/replay |
| `IssueInstant` | Thời điểm yêu cầu được phát |
| `Issuer` | EntityID của bên yêu cầu (SP hoặc IdP) |
| `Destination` | SLO endpoint của bên nhận đã đăng ký |
| `NameID` | Danh tính SAML cần đóng phiên, theo format/qualifiers phù hợp |
| `SessionIndex` | Một hoặc nhiều chỉ số phiên SAML tương ứng |
| `Reason` | Lý do logout nếu sender dùng |
| `NotOnOrAfter` | Giới hạn thời hạn xử lý nếu được đưa vào |
| Signature / integrity protection | Chứng minh requester và chống sửa thông điệp theo binding/profile |

**NameID phải khớp phiên đã đăng nhập.** Nếu IdP phát NameID dạng persistent/opaque nhưng SP tùy biến principal thành email hoặc mã nhân viên rồi dùng sai identifier để logout, IdP có thể không đối chiếu được phiên. Với session participant, SAML SLO profile có yêu cầu về dùng SessionIndex; cần đối chiếu profile thực tế chứ không gửi tùy tiện.

Chữ ký SAML qua **HTTP-Redirect** có thể được đặt ở tham số binding `Signature`/`SigAlg` của query, không nhất thiết dưới dạng thẻ XMLDSig giống HTTP-POST. Không tự coi XML sample thiếu ds:Signature là request đáng tin.

## 7. LogoutResponse: kết quả nào được phép tin?

Mẫu XML rút gọn, không có chữ ký thực:

~~~xml
<samlp:LogoutResponse
    xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    ID="_logout_response_001"
    Version="2.0"
    IssueInstant="2026-11-07T04:00:03Z"
    InResponseTo="_logout_request_001"
    Destination="https://portal.example.org/logout/saml2/slo">
  <saml:Issuer>https://idp.example.org/entity</saml:Issuer>
  <samlp:Status>
    <samlp:StatusCode
        Value="urn:oasis:names:tc:SAML:2.0:status:Success"/>
  </samlp:Status>
</samlp:LogoutResponse>
~~~

Những kiểm tra cần thiết ở SP:

1. Response do **IdP đã tin cậy** phát hành và bảo vệ chữ ký/binding integrity phù hợp.
2. `Issuer` trùng bên IdP của registration.
3. `Destination` đúng public SLO endpoint.
4. `InResponseTo` trùng `LogoutRequest.ID` còn được SP lưu cho luồng tương ứng.
5. `RelayState` được xác minh/đối chiếu khi binding/policy yêu cầu.
6. `StatusCode` thực sự hợp lệ và thuộc kết quả đã được xác thực.
7. Replay, hết hạn, trùng ID và state được kiểm theo profile, không tái sử dụng callback.

**Không thể tin một LogoutResponse chỉ vì có chuỗi `Success` trong XML**; browser có thể gửi payload bất kỳ. Chữ ký, trust, correlation và kết quả status phải đi cùng nhau.

### 7.1. Trạng thái SLO và cách báo kết quả trung thực

| Điều đã xảy ra | Ta có thể kết luận | Không nên kết luận |
|---|---|---|
| Spring đã invalidate local session | SP hiện tại đã logout | IdP và SP khác đã logout |
| Browser đã được chuyển tới IdP SLO URL | Đã khởi chạy chuyển thông điệp | IdP đã xử lý thành công |
| Có valid LogoutResponse Status=Success | IdP báo quy trình phù hợp thành công | Mọi thiết bị/token không thuộc SAML đã bị thu hồi |
| Có `PartialLogout` | Một phần liên kết chưa xác nhận hoàn tất | “Đã đăng xuất khỏi tất cả ứng dụng” |
| Không có LogoutResponse | Không biết outcome federation | IdP chắc chắn chưa logout |
| Response sai signature/InResponseTo | Không thể coi kết quả đáng tin | Thành công chỉ vì HTTP 200 |
| SP B offline/không có SLO | Không có bảo đảm B đã kết thúc phiên | SLO luôn xóa được mọi cookie |

Một response Status Success là kết quả giao thức **trong phạm vi IdP/participants có hỗ trợ**, không phải bằng chứng về API keys, phiên ở thiết bị khác hoặc các dịch vụ phi SAML.

## 8. SLO không bảo đảm đăng xuất tất cả nơi: lý do cụ thể

### 8.1. Federation chỉ điều phối các SP tham gia

IdP cần biết các SP có phiên liên quan và có khả năng gửi LogoutRequest cho họ. Một SP không triển khai SLO hoặc không thể nhận callback vẫn có thể giữ local session. IdP không thể trực tiếp xóa cookie của domain SP khác do giới hạn browser same-origin/cookie scoping.

### 8.2. Front-channel có thể bị gián đoạn

Khi SLO dùng browser redirect/POST, các yếu tố sau có thể làm luồng không hoàn thành:

- Browser đóng tab, mất mạng hoặc user chuyển trang giữa chừng.
- Cookie `SameSite`, `Secure`, cross-site POST hoặc browser privacy restrictions.
- Reverse proxy thay scheme/hostname/path gây `Destination` mismatch.
- SP/IdP có session timeouts khác nhau, session state bị xóa sớm.
- SP khác tạm downtime hoặc trả lỗi.
- Các bước chain logout dài làm phát sinh timeout hoặc PartialLogout.

Back-channel qua SOAP nếu được đối tác hỗ trợ có đặc tính khác, nhưng cũng phụ thuộc reachability/network trust và khả năng triển khai. Không giả định Spring mặc định hỗ trợ đủ mọi SLO binding mà tiêu chuẩn liệt kê.

### 8.3. Nhiều browser và nhiều thiết bị

Một NameID có thể gắn với nhiều SAML SessionIndex và nhiều HttpSession khác nhau. Một request logout chỉ có hiệu lực theo chủ thể/phiên được khớp, chính sách IdP và khả năng SP định vị các sessions tương ứng. Logout từ laptop A **không chắc** đã thu hồi session của điện thoại B hoặc một browser profile khác. Nếu cần “logout mọi thiết bị”, phải thiết kế server-side session invalidation/IdP session revocation riêng.

### 8.4. JWT, OAuth/OIDC và API keys ở ngoài phạm vi

Một ứng dụng có thể dùng SAML cho web login rồi tự phát JWT/access token cho SPA/API. SAML LogoutRequest **không tự thu hồi JWT đã phát**, refresh token, API keys hoặc phiên OIDC ở hệ thống khác. Cần TTL, revocation list, session versioning, introspection hoặc provider-specific logout APIs theo kiến trúc.

**Thực hành:** Trong UX và runbook, xác định chính xác “logout ảnh hưởng những phiên/token nào” thay vì chỉ ghi “logout global”.

## 9. Cấu hình Spring Security: tách local logout và SLO

### 9.1. Khi chỉ cần local logout

Đoạn Java sau là **method fragment** trong class cấu hình Spring Boot Servlet, cần imports tương ứng:

~~~java
@Bean
SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/", "/signed-out", "/error").permitAll()
            .anyRequest().authenticated())
        .saml2Login(Customizer.withDefaults())
        .logout(logout -> logout
            .logoutUrl("/logout")
            .logoutSuccessUrl("/signed-out"))
        .build();
}
~~~

Nếu **không** bật SAML SLO, `POST /logout` chỉ thực hiện local logout qua handlers. Một trang protected sau đó có thể đưa browser về IdP và SSO lại do IdP session còn.

### 9.2. Điều kiện cần để bật federated SLO

Tài liệu Spring Security yêu cầu các điều kiện:

1. IdP thật sự hỗ trợ SAML SLO và metadata có `SingleLogoutService`.
2. SP công bố SLO callback, thường `{baseUrl}/logout/saml2/slo` cho từng registration.
3. SP có **private signing key PKCS#8 + X.509 certificate** để tạo LogoutRequest/LogoutResponse có chữ ký.
4. IdP tin SP public signing cert; SP tin IdP signing verification cert.
5. Hai bên thống nhất binding và endpoint URL public.
6. Security filter chain bật `saml2Logout` và registration có SLO location.
7. Session, NameID, SessionIndex, LogoutRequest repository/RelayState phù hợp.

**Lưu ý:** Chỉ gọi `.saml2Logout(...)` trong code không đủ nếu registration và IdP metadata không có SLO support. Ngược lại, chỉ import metadata có SingleLogoutService không tự kích hoạt SLO nếu DSL/filter chưa bật.

### 9.3. Spring Boot YAML minh họa

Ví dụ cho registration `corporate`; URL và certificate đều **minh họa**, phải thay bằng cấu hình được hai bên xác minh:

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          corporate:
            entity-id: "https://portal.example.org/saml/sp"
            signing:
              credentials:
                - private-key-location: "file:/run/secrets/saml/sp-signing.key"
                  certificate-location: "file:/run/secrets/saml/sp-signing.crt"
            singlelogout:
              url: "{baseUrl}/logout/saml2/slo"
            assertingparty:
              metadata-uri: "https://idp.example.org/saml/metadata"
~~~

`signing.credentials`: SP giữ private key và cert, IdP nhận public cert để xác minh LogoutRequest/LogoutResponse. `singlelogout.url`: **protocol callback** nơi SP nhận LogoutRequest/LogoutResponse, khác user-trigger endpoint. `assertingparty.metadata-uri`: thông tin IdP tin cậy, gồm SLO service + IdP signing verification credentials.

Tên property có thể thay theo Spring Boot/Spring Security version; luôn kiểm `Saml2RelyingPartyProperties` và tài liệu version đang chạy. Nếu IdP cung cấp metadata không công bố SLO hoặc chỉ Redirect binding, cần kiểm tương thích; không tự chế endpoint/Signer hoặc tắt validation để né cấu hình.

### 9.4. Hai endpoint riêng: đây là cấu hình mấu chốt

Theo mục **Separating Local Logout from SAML 2.0 Logout** của Spring Security:

~~~java
http
    .logout(logout -> logout.logoutUrl("/logout"))
    .saml2Logout(saml2 -> saml2.logoutUrl("/saml2/logout"));
~~~

Hành vi khi có registration/IdP hợp lệ:

| HTTP request | Hành vi |
|---|---|
| **`POST /logout`** | Chỉ local logout; không phát SAML LogoutRequest |
| **`POST /saml2/logout`** | RP-initiated SLO: logout local và phát LogoutRequest |
| **`POST /logout/saml2/slo`** với `SAMLRequest` | AP-initiated SLO callback từ IdP |
| **`POST /logout/saml2/slo`** với `SAMLResponse` | RP-initiated SLO LogoutResponse callback |

**Rất dễ nhầm:** Nếu không tách URL, Spring Security với SLO được bật có thể dùng `POST /logout` để khởi chạy federated logout. Do đó không kết luận hành vi chỉ dựa tên endpoint; phải đọc DSL và registration thực tế.

### 9.5. Java Spring Boot Servlet: một class hoàn chỉnh

Ví dụ sau dành cho project Spring Boot có Spring MVC, Security và module SAML2 SP đã cấu hình IdP. Đây là class Java có import đầy đủ, nhưng **không chạy bằng `javac` đơn độc** khi thiếu các thư viện Spring.

Tệp `src/main/java/com/example/sso/LogoutModesApplication.java`:

~~~java
package com.example.sso;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class LogoutModesApplication {

    public static void main(String[] args) {
        SpringApplication.run(LogoutModesApplication.class, args);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/signed-out", "/error").permitAll()
                .anyRequest().authenticated())
            .saml2Login(Customizer.withDefaults())
            .logout(logout -> logout
                .logoutUrl("/logout")
                .logoutSuccessUrl("/signed-out"))
            .saml2Logout(saml2 -> saml2
                .logoutUrl("/saml2/logout"))
            .build();
    }

    @GetMapping("/")
    String home() {
        return "SAML SP ready";
    }

    @GetMapping("/private")
    String privatePage() {
        return "Authenticated";
    }

    @GetMapping("/signed-out")
    String signedOut() {
        return "Local session ended";
    }
}
~~~

Với project Maven có Maven Wrapper và cấu hình cần thiết:

~~~bash
./mvnw spring-boot:run
~~~

Khi server khởi động, `GET /` trả body `SAML SP ready` và `GET /signed-out` trả `Local session ended`. Với `/private`, cần SAML login thành công. Federated SLO có nhiều network hops, certificate và browser-specific behavior nên **không có stdout hoặc redirect endpoint cố định** có thể cam kết khi chưa chạy với IdP thật.

Mã trên chỉ tạo các user-trigger URLs; SLO protocol callback do Spring Security filter xử lý. **Không viết controller khác cùng path `/logout/saml2/slo`** trừ khi có thiết kế filter order cụ thể.

### 9.6. Phụ thuộc Maven

Đoạn sau nằm **bên trong `<dependencies>` của project Spring Boot đã có BOM hoặc parent**, không phải pom.xml hoàn chỉnh:

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

Chọn versions thống nhất qua Spring Boot BOM và tài liệu Spring Security/OpenSAML; tùy version/build có thể cần repository OpenSAML tương ứng. Tính năng `saml2Logout()` trong bài là **Servlet**, không thể copy nguyên sang `ServerHttpSecurity` WebFlux.

### 9.7. Giao diện hai nút đăng xuất

Ví dụ template Thymeleaf, **không phải HTML tĩnh dùng trực tiếp khi chưa có template engine**:

~~~html
<form th:action="@{/logout}" method="post">
  <button type="submit">Đăng xuất khỏi ứng dụng này</button>
</form>
<form th:action="@{/saml2/logout}" method="post">
  <button type="submit">Đăng xuất khỏi phiên SSO liên kết</button>
</form>
~~~

Với tích hợp Spring MVC/Thymeleaf/Spring Security, cần bảo đảm **CSRF token được render và gửi đúng** trong mỗi POST (template integration thường có CSRF hidden input được bổ sung). Nếu dùng SPA hoặc template khác, phải gửi token do Spring Security phát hành theo policy; không tắt CSRF toàn site chỉ để nút logout hoạt động.

**Không dùng GET để thực hiện logout thay đổi trạng thái.** Spring Security có thể trả trang confirmation khi GET `/logout`, nhưng thao tác thực thường là POST có CSRF.

## 10. Metadata và chứng thư: không thể bỏ bước đăng ký

### 10.1. IdP metadata cần chứa SingleLogoutService

Dạng XML **minh họa, chưa đầy đủ chữ ký/certificate**:

~~~xml
<md:EntityDescriptor
    xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"
    entityID="https://idp.example.org/entity">
  <md:IDPSSODescriptor
      protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol">
    <md:SingleLogoutService
        Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST"
        Location="https://idp.example.org/saml/slo"/>
  </md:IDPSSODescriptor>
</md:EntityDescriptor>
~~~

Dấu hiệu IdP hỗ trợ SLO là `SingleLogoutService` trong metadata, nhưng vẫn phải kiểm **binding, Location, signing cert, issuer và đăng ký SP**. Không tự suy ra SLO URL từ Login URL; cũng không lấy khóa tin cậy trực tiếp từ một SAMLRequest do browser gửi.

### 10.2. SP metadata cũng cần SLO callback

SP có thể công bố trong `SPSSODescriptor` một `SingleLogoutService` với Location như `https://portal.example.org/logout/saml2/slo` và Binding phù hợp. IdP phải được cập nhật để gửi LogoutRequest/LogoutResponse tới đúng URL public. Nếu ingress đổi hostname/path, metadata và config IdP phải đồng bộ.

Ba URL khác nhau:
- `/logout`: nút **local** theo cấu hình tách endpoint.
- `/saml2/logout`: nút **khởi tạo** SLO tại SP.
- `/logout/saml2/slo`: **protocol callback** xử lý SAMLRequest/SAMLResponse.

### 10.3. Vai trò signing keys

| Thông điệp | Private signing key | Public certificate bên nhận |
|---|---|---|
| SP → IdP LogoutRequest | SP giữ | IdP tin cert SP |
| IdP → SP LogoutRequest | IdP giữ | SP tin cert IdP |
| SP → IdP LogoutResponse | SP giữ | IdP tin cert SP |
| IdP → SP LogoutResponse | IdP giữ | SP tin cert IdP |

Thứ được gọi “signing cert SAML” **không tự là TLS certificate** của website. Với HTTP-Redirect, chữ ký có thể ở URL query parameters; với HTTP-POST có thể là XMLDSig. Luôn dùng verifier phù hợp binding, trusted metadata và policy, không tự tin `ds:KeyInfo` do client gửi.

**Key rollover:** Nếu IdP đổi signing certificate mà SP chưa cập nhật trust, incoming LogoutRequest/LogoutResponse sẽ fail. Nếu SP đổi signing certificate mà IdP chưa nhận public cert mới, IdP sẽ từ chối request. Lên kế hoạch overlap, test và rotation đồng bộ.

## 11. Validation bảo mật khi nhận LogoutRequest/LogoutResponse

### 11.1. AP-initiated LogoutRequest: phải kiểm trước khi xóa phiên

Nếu attacker tự tạo một XML LogoutRequest gắn NameID của người khác và POST vào SLO callback, SP **không được xóa session của nạn nhân** chỉ vì Request trông giống SAML. Phải:

1. Resolve đúng IdP/registration theo endpoint và thông điệp được kiểm.
2. Verify chữ ký/binding integrity với trusted public key của IdP.
3. Verify `Issuer`, `Destination`, thời gian, ID/replay policy.
4. Match **NameID, Format và SessionIndex** với phiên thực sự liên quan, không match tùy tiện qua email.
5. Chỉ sau khi validation pass mới invalidate session được nhắm tới.
6. Tạo phản hồi có chữ ký/status theo profile nếu giao thức yêu cầu.
7. Log các lỗi theo loại, không log nguyên XML/PII/public cookie.

**Không vô hiệu hóa signature validation** để “cho SLO chạy” khi metadata/certificate IdP sai. Trong Spring Security 7, migration docs lưu ý hành vi trả `LogoutResponse` lỗi cho LogoutRequest invalid được cải thiện; nên regression test response handling sau upgrade.

### 11.2. RP-initiated LogoutResponse: tương quan với request đã gửi

LogoutResponse cần được đối chiếu với LogoutRequest SP đã tạo, thường nhờ:
- `InResponseTo` trùng ID request chờ.
- `RelayState`/binding state đúng.
- IdP signer/issuer đúng.
- Destination phù hợp callback.
- StatusCode đã được xác minh và chưa bị replay.

Spring Security có `Saml2LogoutRequestRepository` để lưu request correlation; mặc định trong tài liệu gắn với session. Bởi local session có thể được invalidate trước khi Response về, phải dùng cơ chế framework hỗ trợ; nếu custom lưu request ở Redis/DB, cần xử lý TTL, tiêu thụ request một lần và ngữ cảnh tenant, tránh store state vô thời hạn hoặc nhầm user.

**Tuyệt đối không coi `StatusCode=Success` trong payload do browser gửi là bằng chứng thành công trước khi verify signature/trust/correlation.**

## 12. CSRF và cookie: hai hướng POST khác nhau

### 12.1. Người dùng POST logout tại SP

Local `POST /logout` và SP-trigger `POST /saml2/logout` là các thao tác state-changing do browser của người dùng yêu cầu. Chúng nên áp dụng CSRF protection do Spring Security quản lý. Không tạo logout GET chỉ để tránh token vì có nguy cơ **logout CSRF** hoặc forced logout.

### 12.2. IdP gửi POST SAML đến SLO callback

Incoming IdP LogoutRequest thường không mang CSRF token của form ứng dụng. Đó là một **SAML protocol callback** được xác thực bằng signature/trust/conditions. Tùy cấu hình Spring Security version, filter SLO và CSRF matcher được tích hợp chuyên biệt. Nếu phải cấu hình CSRF exceptions, chỉ giới hạn chính xác SLO callback, không disable cho mọi POST nghiệp vụ.

### 12.3. Cross-site browser state

Khi redirect/POST từ IdP về SP, trình duyệt có thể áp đặt:
- `SameSite`, `Secure`, domain/path của cookie.
- TLS termination ở proxy khiến URL public HTTPS khác HTTP nội bộ.
- Third-party-cookie restrictions, iframe restrictions.
- Session affinity trong cluster, request repository có hoặc không chia sẻ state.
- Callback tới node khác, session đã hết hạn.

Không “sửa” mất `InResponseTo` bằng cách bỏ correlation validation; phải sửa cookie/session/request repository và endpoint config.

## 13. NameID, SessionIndex và logout đúng phiên

### 13.1. NameID không phải luôn là email

Một Assertion có thể mang:
- `persistent NameID`: định danh ổn định theo federation.
- `transient NameID`: ngắn hạn, chỉ hợp lệ ngữ cảnh nhất định.
- `emailAddress`: email có thể đổi/tái sử dụng.
- `unspecified`: hợp đồng IdP/SP quyết định format/ý nghĩa.

Nếu ứng dụng tùy biến principal thành `employeeCode` hay email nhưng IdP nhận LogoutRequest dùng NameID persistent, một custom resolver lấy thẳng `Authentication.getName()` có thể gửi sai identifier và IdP không xác định được session.

### 13.2. SessionIndex khác HTTP session

| ID | Bên quản lý | Ý nghĩa |
|---|---|---|
| `JSESSIONID/HttpSession ID` | SP web container | Phiên web cục bộ |
| `Authentication` | Spring Security SP | Ngữ cảnh xác thực và authorities |
| `NameID` | SAML/IdP | Chủ thể federated |
| `SessionIndex` | SAML AuthnStatement/IdP | Phiên IdP biết và có thể dùng cho SLO |
| `LogoutRequest.ID` | SAML sender | Correlation LogoutResponse |
| `RelayState` | HTTP binding | Khôi phục context được kiểm tra |

Một user có thể có nhiều SessionIndex. **Không gọi `getSessionIndexes().get(0)` nếu danh sách trống**, không assume một SessionIndex đồng nghĩa “mọi thiết bị”. Nếu SP phải vô hiệu hóa nhiều HttpSessions, cần thiết kế session registry hoặc store hỗ trợ tìm đúng sessions liên quan và test thực tế.

### 13.3. Spring Security 6.x so với 7.x

- Trong các API Spring Security 6.x, `Saml2AuthenticatedPrincipal` thường mang `getName()`, `getRelyingPartyRegistrationId()` và `getSessionIndexes()`.
- Trong Spring Security 7.x, tài liệu migration cho biết chi tiết Assertion được tách khỏi principal để phục vụ SLO với custom principal; `Saml2AssertionAuthentication`/`Saml2ResponseAssertionAccessor` được ưu tiên trong default flow.
- Các SLO resolver tùy biến từng cast `Saml2AuthenticatedPrincipal` trực tiếp có thể cần sửa khi nâng phiên bản.
- Test NameID/SessionIndex thực tế từ IdP và LogoutRequest được sinh, không chỉ compile thành công.

Không trộn sample legacy Spring SAML Extension với Spring Security hiện đại.

## 14. Các thành phần SLO trong Spring Security

| Thành phần | Nhiệm vụ |
|---|---|
| `Saml2RelyingPartyInitiatedLogoutSuccessHandler` | Bắt đầu RP-SLO sau khi local logout handlers chạy |
| `Saml2LogoutRequestResolver` | Tạo, ký, serialize LogoutRequest |
| `Saml2LogoutRequestRepository` | Lưu state để đối chiếu InResponseTo/RelayState |
| `Saml2LogoutRequestFilter` | Nhận/validate AP-initiated LogoutRequest |
| `Saml2LogoutRequestValidator` | Kiểm issuer, signature, destination, principal/policy |
| `Saml2LogoutResponseResolver` | Tạo, ký, serialize LogoutResponse |
| `Saml2LogoutResponseFilter` | Nhận LogoutResponse cho RP-SLO |
| `Saml2LogoutResponseValidator` | Kiểm response signature/issuer/status/correlation |
| `RelyingPartyRegistrationRepository` | Lưu metadata/trust/endpoint/signing creds |

Có thể tùy biến filters bằng DSL, ví dụ callback URL:

~~~java
http.saml2Logout(saml2 -> saml2
    .logoutRequest(req -> req.logoutUrl("/SLOService.saml2"))
    .logoutResponse(resp -> resp.logoutUrl("/SLOService.saml2"))
);
~~~

**Chỉ là method fragment**, không biên dịch độc lập. Khi đổi callback phải đổi luôn SP metadata, `RelyingPartyRegistration` và IdP stored Logout URL. Nếu chỉ đổi filter path sẽ nhận 404 hoặc Destination mismatch.

Ví dụ custom request repository:

~~~java
http.saml2Logout(saml2 -> saml2
    .logoutRequest(req -> req
        .logoutRequestRepository(myRepository))
);
~~~

Cần có một object `myRepository` thực sự implement interface repository đúng Spring Security version. Repository không được chỉ là Map trong memory của một node nếu callback có thể tới node khác.

## 15. Java 17 độc lập: mô phỏng các mức độ chắc chắn

Chương trình này **không ký/parse SAML**; nó mô phỏng cách trình bày kết quả theo **mức độ đã được bên ngoài xác minh**. Mục tiêu tránh câu “mọi nơi đã logout” khi chỉ biết local session đã bị xóa.

Tệp `LogoutScopeDemo.java`:

~~~java
public class LogoutScopeDemo {

    enum Mode { LOCAL, FEDERATED }
    enum Response { SUCCESS, PARTIAL, MISSING }

    static String describe(Mode mode, Response response) {
        if (mode == Mode.LOCAL) {
            return "LOCAL_DONE: only this SP session";
        }
        return switch (response) {
            case SUCCESS ->
                "SLO_REPORTED_SUCCESS: verify protocol scope";
            case PARTIAL ->
                "SLO_PARTIAL: some sessions may remain";
            case MISSING ->
                "SLO_UNKNOWN: only local logout is known";
        };
    }

    public static void main(String[] args) {
        System.out.println(describe(Mode.LOCAL, Response.MISSING));
        System.out.println(describe(Mode.FEDERATED, Response.SUCCESS));
        System.out.println(describe(Mode.FEDERATED, Response.PARTIAL));
        System.out.println(describe(Mode.FEDERATED, Response.MISSING));
    }
}
~~~

Chạy bằng JDK 17+:

~~~bash
javac LogoutScopeDemo.java
java LogoutScopeDemo
~~~

Stdout chính xác:

~~~text
LOCAL_DONE: only this SP session
SLO_REPORTED_SUCCESS: verify protocol scope
SLO_PARTIAL: some sessions may remain
SLO_UNKNOWN: only local logout is known
~~~

**Giải thích:**
1. Local mode luôn chỉ kết luận SP session đã chấm dứt; không cần LogoutResponse.
2. SUCCESS chỉ là trạng thái SLO **được bên tin cậy báo**. Chương trình giả định enum đã qua validation SAML thực tế, chứ không xác minh chữ ký.
3. PARTIAL cho biết chưa hoàn tất mọi bên.
4. MISSING là thiếu xác nhận cuối; IdP có thể đã xử lý hoặc chưa.
5. Không tự phục hồi session SP đã invalidated chỉ vì thiếu LogoutResponse; xử lý UX và logging phù hợp.

**Giới hạn:** Trong production, không tin enum từ query/HTTP client chưa xác minh. Dữ liệu phải đến từ Spring Security/OpenSAML SLO validator + request correlation.

## 16. Thực hành tích hợp: test IdP và hai SP

### 16.1. Môi trường

- Test IdP hỗ trợ SAML login, RP-initiated và AP-initiated SLO theo binding phù hợp.
- SP A là ứng dụng Spring MVC/Security đã bật hai logout modes.
- SP B dùng cùng IdP, SLO endpoint đã cấu hình nếu cần test toàn federation.
- Một user test có NameID Format/SessionIndex đã thống nhất.
- Hai browser profiles tách biệt, có thể kiểm HTTP session.
- Có quyền xem log/metadata nhưng không dump raw PII vào log chung.

### 16.2. Positive tests

| Case | Hành động | Kết quả mong muốn |
|---|---|---|
| P1 Local | Login A/B, POST `/logout` tại A | A session kết thúc; B/IdP không mặc nhiên bị tác động |
| P2 SSO re-entry | Mở protected route của A sau P1 | Có thể SSO lại nếu IdP session còn |
| P3 RP-SLO | POST `/saml2/logout` tại A | A local logout và signed LogoutRequest tới IdP |
| P4 IdP fan-out | IdP nhận request hợp lệ | IdP điều phối logout tới SP B theo khả năng |
| P5 Peer response | SP B nhận LogoutRequest | SP B verify, đóng session tương ứng, trả LogoutResponse |
| P6 SP callback | A nhận LogoutResponse | Verify signature, issuer, InResponseTo, status |
| P7 AP-SLO | Bấm logout tại IdP | A nhận/verify LogoutRequest, đóng session, trả LogoutResponse |
| P8 Cluster | Callback quay về node khác | Correlation/state vẫn đúng nếu app hỗ trợ |
| P9 Multiple sessions | User có các browser/device khác nhau | Quan sát chính xác phạm vi session thực sự bị đóng |
| P10 Browser flow | Chạy với SameSite/HTTPS/proxy thực tế | Không mất state vì cookie/binding sai |

### 16.3. Negative tests

| Case | Thử lỗi | Kết quả mong muốn |
|---|---|---|
| N1 | IdP SLO không hỗ trợ hoặc thiếu SingleLogoutService | Không tuyên bố SLO thành công |
| N2 | SP ký bằng private key không khớp cert IdP tin | IdP từ chối request |
| N3 | IdP LogoutRequest có chữ ký giả | SP từ chối, không xóa sai session |
| N4 | Issuer/tenant IdP khác registration | SP từ chối |
| N5 | Destination không đúng SLO endpoint | SP từ chối |
| N6 | NameID/SessionIndex không khớp | Không logout nhầm người/phiên |
| N7 | Replay LogoutRequest cũ | Không xử lý thêm trái policy |
| N8 | LogoutResponse Status=Success nhưng chữ ký sai | Không xác nhận thành công |
| N9 | LogoutResponse InResponseTo không khớp request | Không xác nhận thành công |
| N10 | SP B offline | Partial/Unknown, không claim global completion |
| N11 | Browser tắt giữa RP-SLO | SP A local done; global status unknown |
| N12 | POST local logout thiếu CSRF token | Bị chặn theo CSRF policy |
| N13 | GET /logout tự thực hiện state change | Không nên được phép |
| N14 | IdP rotation signing cert chưa được SP trust | Fail an toàn |
| N15 | Logout request repository bị mất state ở node khác | Fail correlation, sửa store/session |
| N16 | JWT/API token vẫn hợp lệ sau SLO | Nhận ra đó là lifecycle riêng |
| N17 | IdP chỉ hỗ trợ Redirect, SP cấu hình POST không phù hợp | Sửa binding, không tắt validation |
| N18 | SP B không tham gia SLO nhưng vẫn giữ session | Báo đúng giới hạn federation |

Không chỉ dùng `MockMvc` với Authentication giả để kết luận SLO đầy đủ đã hoạt động. Unit test logout local là cần, nhưng SLO phải được kiểm với **test IdP và signed LogoutRequest/LogoutResponse thực**, các lỗi message và session correlation.

## 17. Troubleshooting theo đúng tầng

| Triệu chứng | Nguyên nhân khả dĩ | Cách kiểm/sửa |
|---|---|---|
| Local logout rồi SSO ngay | IdP session còn | Kiểm có thật gửi LogoutRequest không; mục tiêu chỉ local hay SLO? |
| POST /saml2/logout chỉ xóa session | DSL/per-registration SLO chưa đầy đủ | Kiểm `saml2Logout`, metadata, signing credential |
| IdP từ chối LogoutRequest | Signature, NameID, SessionIndex hoặc Destination sai | Kiểm signing public cert được IdP tin, profile/binding |
| Spring từ chối IdP LogoutRequest | IdP cert, issuer, destination, session mismatch | Kiểm validator, metadata và trust |
| 404 SLO callback | IdP gửi sai URL hoặc filter không bật | Kiểm `/logout/saml2/slo` / custom URL và ingress |
| Callback response HTTP 400 | Signature/issuer/InResponseTo/status invalid | Kiểm LogoutResponseValidator, request repository |
| LogoutResponse không về | Browser/network/IdP callback failure | Phân biệt local done và global unknown |
| SP A logout, SP B còn | B offline, không hỗ trợ, partial logout | Kiểm IdP logs và B's SLO endpoint |
| 403 khi người dùng POST /logout | Thiếu CSRF token | Kiểm form POST/Thymeleaf hoặc SPA CSRF integration |
| Logout thành công ở máy A nhưng máy B còn | Multi-device sessions không cùng logout scope | Thiết kế IdP/session invalidation đúng mục tiêu |
| SLO fail khi chạy sau proxy | External HTTPS URL khác internal HTTP URL | Trusted forwarded headers, Recipient/Destination |
| Request correlation mất ở cluster | Session/request state không chia sẻ | Spring Session hoặc custom repository có TTL |
| Login vẫn hoạt động, SLO fail | SLO là profile/endpoint/credentials riêng | Không lấy SSO success làm bằng chứng SLO đã sẵn sàng |
| Custom principal khiến IdP không nhận NameID | Dùng local user ID/email thay NameID gốc | Kiểm assertion accessor và SLO resolver đúng version |
| SLO hoàn tất nhưng API vẫn gọi được | Token ngoài HttpSession chưa thu hồi | TTL/revocation cho API tokens |
| Thay IdP signing key thì SLO fail | SP trust chưa cập nhật cert mới | Kế hoạch rotation metadata + validation |

Chẩn đoán theo trình tự: **logout mode → HTTP endpoint thực tế → local session → IdP SLO metadata/binding → SAML signing/trust → LogoutRequest → fan-out peers → LogoutResponse/correlation → session/token scopes**.

Không chữa bằng cách tắt signature validation hoặc cho phép mọi issuer, hoặc xóa toàn bộ user sessions nếu không xác định được subject.

## 18. Thiết kế trải nghiệm và thông báo đúng sự thật

### 18.1. Hai nút đúng mục đích

**“Đăng xuất khỏi ứng dụng này”**:
- POST local logout.
- Không yêu cầu IdP kết thúc SSO.
- Thông báo: “Đã kết thúc phiên tại ứng dụng này. Các ứng dụng khác có thể vẫn đang đăng nhập.”
- Nếu quay lại app, có thể login lại tự động.

**“Đăng xuất khỏi các ứng dụng liên kết”**:
- POST RP-initiated SLO.
- Xóa local session và yêu cầu IdP điều phối.
- Chỉ báo toàn bộ SLO thành công theo **verified response/policy scope**.
- Có nhánh PartialLogout/Unknown/Failure được giải thích rõ.

### 18.2. Máy công cộng, kiosks và logout mọi thiết bị

Nếu rủi ro là người tiếp theo sử dụng chung máy, không chỉ dựa vào local logout. Có thể cần đóng IdP SSO session và giải phóng browser context, đồng thời quản trị session/device theo chính sách. **Đóng tab không tự xóa cookie đăng nhập**, và SAML SLO không bảo đảm token ở điện thoại đã bị thu hồi. Các ứng dụng có compliance cao cần logout/revocation strategy đủ rộng hơn giao thức SAML.

## 19. Runbook vận hành và triển khai

### Trước khi bật SLO

1. Xác nhận IdP hỗ trợ SingleLogoutService và các bindings cụ thể.
2. Chốt SP public SLO callback, metadata, NameID format và SessionIndex policy.
3. Thiết lập SP signing private key / public certificate và IdP verification signing keys.
4. Cấu hình `.saml2Logout()` và per-registration SLO location, thử hai endpoints nếu cần tách.
5. Kiểm CSRF cho user-trigger logout và trust/signature cho IdP-trigger callback.
6. Kiểm SessionIndex/NameID không bị đổi khi custom principal.
7. Test IdP SLO response + error statuses, browser/cookies/cluster.
8. Cảnh báo timeout/PartialLogout và logging có correlation mà không lộ PII.
9. Có kế hoạch rotation key/metadata và rollback an toàn.
10. Chốt tài liệu cho người dùng: local vs linked logout, unknown scope.

### Khi xảy ra sự cố

- **Ưu tiên giữ local session đã bị invalidated**, không “đăng nhập lại” thay user.
- Báo chính xác chưa thể xác nhận global SLO nếu LogoutResponse thiếu/invalid.
- Đối chiếu SAML issuer/destination/trusted cert trước khi mở rộng quyền.
- Kiểm IdP logs và các SP participants, không chỉ log SP A.
- Không trả về raw SAML messages chứa NameID/PII cho người dùng trong trang lỗi.
- Với outage lớn, có thể tạm dùng local logout được mô tả rõ, **không lặng lẽ hiển thị là SLO thành công**.

## 20. Câu hỏi ôn tập

1. **Local logout xóa IdP SSO session không?** Không mặc định.
2. **Vì sao local logout rồi vào lại ứng dụng vẫn được SSO?** IdP cookie/session còn sống và có thể phát Assertion mới.
3. **SLO có xóa cookie SP B trực tiếp từ SP A không?** Không; SP B phải tham gia hoặc có cơ chế khác.
4. **RP-initiated và AP-initiated khác gì?** RP bắt đầu ở SP; AP bắt đầu từ IdP gửi LogoutRequest.
5. **LogoutRequest có các trường nào?** Issuer, ID, Destination, NameID, SessionIndex và integrity protection theo binding/profile.
6. **LogoutResponse cần kiểm gì?** Trusted signature/issuer, Destination, InResponseTo, StatusCode, replay/correlation.
7. **SessionIndex có phải JSESSIONID?** Không.
8. **Bật saml2Logout mặc định thì POST /logout có thể làm gì?** RP-initiated SLO, không chỉ local.
9. **Tách local và federated bằng cách nào?** Dùng `.logout(l -> l.logoutUrl("/logout"))` cùng `.saml2Logout(s -> s.logoutUrl("/saml2/logout"))` và registration/certs đúng.
10. **`/logout/saml2/slo` là endpoint nào?** Callback giao thức từ IdP, không phải nút người dùng bấm.
11. **Có thể gửi logout bằng GET để đơn giản?** Không nên; state-changing logout cần chống CSRF.
12. **Một LogoutResponse Status=Success chưa verify có đáng tin?** Không.
13. **PartialLogout nghĩa là gì?** Không thể xác nhận tất cả participants đã hoàn tất.
14. **Mất LogoutResponse có nghĩa IdP chắc chắn không logout?** Không; trạng thái cuối unknown.
15. **SLO có thu hồi mọi API token/JWT không?** Không tự động.
16. **Đổi IdP signing certificate có ảnh hưởng SLO?** Có, nếu SP chưa cập nhật trusted verification keys.
17. **Khi chạy nhiều node cần kiểm gì?** Session store, request repository, correlation/replay và invalidation.
18. **Vì sao login chạy nhưng SLO fail?** SLO cần endpoint, bindings, signing creds và metadata riêng.
19. **Có nên tự xóa mọi HttpSession khi nhận LogoutRequest có cùng email?** Không; phải verify và match issuer+NameID+SessionIndex đúng.
20. **Thành công được báo thế nào?** Chỉ trong phạm vi thông điệp SLO đã xác minh và các participant thực sự kết thúc, không tuyên bố mọi thiết bị/token hết hiệu lực.

## 21. Tài liệu chính thức

- Spring Security – Performing Single Logout: https://docs.spring.io/spring-security/reference/servlet/saml2/logout.html
- Spring Security – Handling Logout (Servlet): https://docs.spring.io/spring-security/reference/servlet/authentication/logout.html
- Spring Security – SAML 2.0 Login Overview: https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html
- Spring Security – SAML 2.0 Migrations (SLO error response, assertion accessor): https://docs.spring.io/spring-security/reference/migration/servlet/saml2.html
- Spring Security – CSRF Protection (Servlet): https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html
- Spring Security – Session Management: https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html
- OASIS – SAML 2.0 Profiles, Single Logout Profile: https://docs.oasis-open.org/security/saml/v2.0/saml-profiles-2.0-os.pdf
- OASIS – SAML Core, LogoutRequest/LogoutResponse and StatusCode: https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf
- OASIS – SAML Technical Overview (multiple SPs): https://docs.oasis-open.org/security/saml/Post2.0/sstc-saml-tech-overview-2.0.html
- OWASP – SAML Security Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/SAML_Security_Cheat_Sheet

**Tổng kết:** Local logout chỉ làm mất phiên của SP hiện tại; IdP session và SP khác có thể còn sống. SAML Single Logout cố gắng chấm dứt phiên SSO liên kết bằng các LogoutRequest/LogoutResponse được xác minh. Trong Spring Security, khi cần **hai mục đích tách biệt**, dùng **hai endpoint khác nhau** cho local và RP-initiated SLO, cộng metadata/signing cert và IdP support đầy đủ. Đừng đánh đồng “đã nhấn nút logout” với “toàn bộ federation và mọi token đã hết hiệu lực”.
