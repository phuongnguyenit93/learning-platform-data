# Giới hạn của SLO khi người dùng có nhiều ứng dụng, thiết bị hoặc phiên

**SAML 2.0 Single Logout (SLO)** là cơ chế phối hợp đăng xuất giữa Identity Provider (IdP/Asserting Party) và các Service Provider (SP/Relying Party) đã tham gia một ngữ cảnh đăng nhập liên kết. SLO giúp kết thúc các phiên có liên quan, nhưng **không phải nút “đăng xuất mọi ứng dụng, mọi trình duyệt, mọi thiết bị, mọi token” với kết quả luôn được bảo đảm**.

Khi một người dùng đồng thời sử dụng Portal, HRM, CRM trên máy tính, điện thoại và một trình duyệt khác, có thể tồn tại nhiều lớp session độc lập. Một `LogoutRequest` thường gắn với **NameID** và có thể chỉ rõ **SessionIndex** của một ngữ cảnh phiên IdP. Một quy trình SLO có thể hoàn tất tại IdP nhưng vẫn còn session ở SP không tham gia, ở thiết bị khác, trong ứng dụng dùng OAuth/OIDC hoặc trong những tab không nhận thông báo đúng cách.

**Thông điệp quan trọng nhất:** Phải phân biệt rõ **“đăng xuất khỏi ứng dụng hiện tại”**, **“SLO cho các bên tham gia cùng phiên IdP”** và **“thu hồi toàn bộ phiên/tokens của tài khoản trên mọi thiết bị”**. Ba mục tiêu khác nhau về giao thức, khả năng quan sát, mức độ bảo đảm và thiết kế hệ thống. Bài này thuộc **Spring Security – federation → Đăng xuất SAML2**, tập trung vào các giới hạn, cách cấu hình Spring Security, kiểm thử và biện pháp vận hành.

## 1. SLO là gì và giải quyết vấn đề nào?

Trong **SAML Web Browser SSO**, người dùng có thể vào App A và App B nhờ một lần xác thực ở IdP. Mỗi ứng dụng vẫn thiết lập **phiên cục bộ riêng** để bảo vệ các request tiếp theo. Khi đăng xuất ở một ứng dụng, chỉ xóa cookie/HttpSession của ứng dụng đó thì phiên IdP và App B có thể vẫn còn.

SLO bổ sung các thông điệp giao thức để điều phối việc kết thúc session:

| Đối tượng | Vai trò |
| --- | --- |
| `samlp:LogoutRequest` | Yêu cầu chấm dứt session SAML đối với subject/SessionIndex liên quan |
| `samlp:LogoutResponse` | Phản hồi kết quả xử lý yêu cầu đăng xuất |
| `saml:NameID` | Xác định subject trong federation theo định dạng/phạm vi đã thỏa thuận |
| `samlp:SessionIndex` | Cho biết một hoặc nhiều session SAML cần kết thúc theo quy tắc profile |
| `SingleLogoutService` trong metadata | Endpoint/binding mà bên kia hỗ trợ nhận thông điệp logout |
| Chữ ký XML hoặc chữ ký binding | Giúp kiểm chứng thông điệp do đúng đối tác tin cậy phát ra |

SLO là tính năng **tùy chọn** trong hệ sinh thái SAML; không phải mọi IdP/SP đều hỗ trợ hoặc hỗ trợ mọi binding. Việc cả hai bên hỗ trợ **SAML SSO** không đồng nghĩa họ cũng hỗ trợ **SAML SLO**.

**SLO không phát lệnh xóa cookie tùy ý trên mọi website.** Những cookie thuộc domain khác nhau và session server-side thuộc quyền quản lý riêng của từng ứng dụng. SLO phải dựa vào việc mỗi participant nhận, xác minh và thực hiện yêu cầu hợp lệ.

## 2. Ba lớp trạng thái phải phân biệt

Một người dùng có thể đồng thời sở hữu những loại trạng thái sau:

| Lớp | Ví dụ | Ai kiểm soát? | SLO có trực tiếp quản lý không? |
| --- | --- | --- | --- |
| **IdP SSO session** | Cookie/session ở `login.example.test` | IdP | IdP có thể kết thúc session thuộc phạm vi logout |
| **SP local web session** | `JSESSIONID`, Spring SecurityContext tại Portal | Từng SP | SP phải thực hiện local logout khi nhận thông điệp phù hợp |
| **SP application session bổ sung** | Session Redis, remember-me token, WebSocket, tài khoản lưu ở backend | SP | Không tự xóa nếu logout handlers/thiết kế không xử lý |
| **Phiên của ứng dụng khác** | HRM, CRM, Wiki | Từng participant | Chỉ khi nhận và xử lý SLO phù hợp |
| **Phiên trên thiết bị khác** | Điện thoại, trình duyệt riêng, private window | IdP và từng SP | Không mặc định nằm trong cùng SessionIndex/ngữ cảnh |
| **API access token/JWT** | Bearer token đã phát cho mobile/API | Authorization server/resource server | SAML SLO không tự thu hồi JWT độc lập |
| **OAuth/OIDC refresh token** | Token làm mới phiên app | Authorization server | Cần revoke/expiration/back-channel riêng |
| **Client cache/offline data** | LocalStorage, service worker cache, dữ liệu ứng dụng đã tải | Trình duyệt/ứng dụng | Không tự xóa bằng SLO |

Kết quả đăng xuất nên được báo cáo theo lớp, ví dụ **“Đã đăng xuất Portal”** và **“Đã gửi yêu cầu đăng xuất liên kết, một số ứng dụng có thể vẫn đang mở”**, thay vì khẳng định chắc chắn **“Bạn đã được đăng xuất khỏi mọi thiết bị”** khi không có bằng chứng.

## 3. RP-initiated và AP-initiated SLO

### 3.1. RP-initiated: từ ứng dụng gửi yêu cầu đến IdP

Người dùng bấm Đăng xuất trong Portal (SP). Nếu Portal được cấu hình tham gia SLO, Spring Security thực hiện local logout rồi tạo **LogoutRequest đã ký** tới IdP. IdP kiểm tra yêu cầu, xử lý session liên quan và có thể truyền logout tới những SP khác đã tham gia cùng phiên. Sau đó IdP có thể gửi **LogoutResponse** trở lại.

~~~text
Browser             Portal/SP             IdP               HRM/SP
   |                   |                   |                    |
   | POST /logout      |                   |                    |
   +------------------>|                   |                    |
   |               Local logout           |                    |
   |                   |---- LogoutRequest>|                    |
   |                   |                   |-- LogoutRequest -->|
   |                   |                   |             Local logout?
   |                   |                   |<-- LogoutResponse--|
   |                   |<-- LogoutResponse-|                    |
   |<-- kết quả -------|                   |                    |
~~~

**Hạn chế:** App HRM chỉ bị đăng xuất nếu IdP biết đây là participant của **ngữ cảnh phù hợp**, SLO của HRM đã được đăng ký/cho phép, request đến được HRM và HRM thực thi đúng. Nếu browser bị đóng, mạng mất kết nối hoặc một bên từ chối, chuỗi logout có thể dừng giữa chừng.

### 3.2. AP-initiated: IdP yêu cầu ứng dụng đăng xuất

IdP có thể chủ động gửi **LogoutRequest** tới Portal khi người dùng bấm Sign out ở IdP hoặc khi chính sách IdP kết thúc session. Portal cần kiểm chứng thông điệp (đúng issuer/registration, signature, thời gian, đích, replay và điều kiện phù hợp), hủy local session liên quan rồi trả **LogoutResponse**.

~~~text
IdP                  Browser                 Portal/SP
 |                      |                        |
 |---- LogoutRequest -->|---- LogoutRequest ---->|
 |                      |             verify + local logout
 |<--- LogoutResponse --|<--- LogoutResponse ----|
 |                      |                        |
~~~

**Hạn chế:** “IdP đã gửi” không chứng minh SP đã nhận. Nếu request đi qua front-channel nhưng trình duyệt không tải endpoint/không có cookie phù hợp, có thể không xác định được đúng SP session cần hủy. Spring Security có SAML logout filter/validator, nhưng không tự có quyền xóa mọi session khác của cùng account ở các thiết bị.

### 3.3. Local-only logout

Nếu người dùng chỉ gọi endpoint local logout, Spring có thể xóa session Portal mà **không gửi LogoutRequest tới IdP**. Đăng nhập lại Portal ngay sau đó có thể diễn ra gần như tức thì vì IdP SSO cookie vẫn còn; đây không phải dấu hiệu chắc chắn logout code sai, mà là hậu quả của phạm vi logout chỉ ở SP.

## 4. Vì sao nhiều ứng dụng khiến SLO không chắc chắn hoàn tất?

Một IdP có thể biết Portal và HRM là hai **session participants**, nhưng trong thực tế chúng không nhất thiết cùng hỗ trợ SLO. Ví dụ:

| Ứng dụng | Cơ chế login | Cơ chế logout | Khi Portal khởi tạo SLO |
| --- | --- | --- | --- |
| Portal | SAML SSO | SAML SLO và local session | Portal có thể tự hủy phiên hiện tại |
| HRM | SAML SSO | SAML SLO đã cấu hình đúng | IdP có thể yêu cầu HRM hủy session liên quan |
| CRM | SAML SSO | Chỉ local logout | IdP có thể không có cách điều phối kết thúc CRM |
| BI | OIDC Login | OIDC logout riêng | Không tự nhận SAML LogoutRequest |
| API | OAuth2 JWT | TTL/revocation token | SAML SLO không tự làm JWT hết hiệu lực |

**Một IdP chung không đồng nghĩa mọi ứng dụng dùng chung một session store.** Trong hệ thống thật, app có thể nằm trên những domain, nền tảng, giao thức và chủ sở hữu vận hành khác nhau.

OASIS mô tả SLO như cơ chế giúp đăng xuất gần đồng thời khỏi các participants; đồng thời chỉ ra quy trình qua browser có thể bị người dùng ngắt nên **không thể bảo đảm tuyệt đối tất cả participant đã được ghé thăm**. Vì vậy sản phẩm cần phân biệt **SLO đã khởi tạo**, **SLO được IdP phản hồi**, **các SP xác nhận hoàn tất** và **bằng chứng thực tế của mọi session**.

### Một ví dụ dễ gặp

Người dùng mở Portal và HRM ở cùng trình duyệt. Portal nhận `LogoutResponse` từ IdP và hiển thị “Đã đăng xuất”. Nếu HRM đang offline lúc IdP truyền yêu cầu, HRM local session vẫn có thể tồn tại. Tên trạng thái “Success” ở một bước giao thức **không phải bằng chứng độc lập** rằng mọi phiên trong mọi ứng dụng đã bị hủy. IdP có thể phản hồi trạng thái **PartialLogout** khi không truyền được thông điệp tới tất cả participants.

## 5. Nhiều thiết bị: cùng tài khoản nhưng không nhất thiết cùng IdP session

Giả sử người dùng sử dụng ba môi trường:

~~~text
Tài khoản: user@example.test
     |
     +-- Laptop / Chrome -- IdP session S1
     |        +-- Portal session P1
     |        +-- HRM session H1
     |
     +-- Laptop / Firefox -- IdP session S2
     |        +-- Portal session P2
     |
     +-- Điện thoại -- IdP session S3
              +-- Portal session P3
              +-- Mobile API refresh token R3
~~~

Khi Chrome ở laptop khởi tạo SLO, **S1** có thể là phiên bị yêu cầu kết thúc. **S2** và **S3** là các phiên IdP riêng, có thể không nằm trong phạm vi LogoutRequest của S1; phiên Portal **P2**, **P3** và refresh token **R3** không tự bị thu hồi.

Kết luận phụ thuộc nhà cung cấp IdP: một số IdP có tính năng **logout all devices/sessions** riêng, có thể yêu cầu ứng dụng downstream chấm dứt các phiên liên quan; số khác chỉ kết thúc phiên hiện tại. Không thể suy đoán từ tên “Single Logout” rằng IdP luôn thực hiện account-wide logout.

**Điểm bảo mật:** Trong yêu cầu “khóa tài khoản bị lộ” hoặc “nhân viên nghỉ việc”, chỉ chạy SAML SLO là **không đủ** để bảo đảm mọi thiết bị bị chặn. Cần chính sách thu hồi toàn bộ IdP sessions, SP sessions, refresh tokens/API credentials và kiểm tra authorization ở backend.

## 6. Nhiều tab và nhiều cửa sổ trong cùng trình duyệt

Hai tab cùng origin thường chia sẻ cookie session. Nếu Portal xóa server-side HttpSession, request từ tab còn lại sẽ không còn phiên hợp lệ, dù giao diện tab đó vẫn hiện dữ liệu đã render trước đó. Điều này có nghĩa:

- **Server-side access mới** phải bị từ chối hoặc điều hướng login khi session hết hạn.
- **Dữ liệu đã hiển thị** trong tab cũ không biến mất chỉ vì server hủy session.
- **Frontend state** trong memory, localStorage, IndexedDB hoặc cache vẫn có thể tồn tại nếu ứng dụng không chủ động xóa.
- **WebSocket/SSE** có thể vẫn mở nếu hệ thống không gắn việc đóng kênh với invalidation của session.

Một UX tốt có thể dùng thông báo liên tab như `BroadcastChannel` hay storage events (phần frontend) để cập nhật giao diện ngay khi một tab logout. Nhưng những tín hiệu này **chỉ hỗ trợ UI**, không thay thế kiểm tra session và authorization ở server.

Nếu trình duyệt bị tắt hoặc chặn cookie trong luồng SLO, front-channel có thể bị dừng. Không nên coi việc **không có callback LogoutResponse** là bằng chứng mọi phiên đã bị hủy hoặc chưa hủy; hãy phân biệt trạng thái cục bộ với trạng thái liên kết.

## 7. SessionIndex: phạm vi phiên, không phải lệnh xóa mọi thiết bị

Trong SAML, một `AuthnStatement` có thể chứa `SessionIndex`; IdP và SP dùng nó để tương quan phiên SSO. Một `LogoutRequest` thường mang `NameID` và một hoặc nhiều `SessionIndex` để xác định những phiên cần kết thúc.

~~~xml
<samlp:LogoutRequest
    xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    ID="_logout-unique-id"
    Version="2.0"
    IssueInstant="2026-11-07T10:30:00Z"
    Destination="https://idp.example.test/slo">
  <saml:Issuer>https://portal.example.test/saml/sp</saml:Issuer>
  <saml:NameID>subject-example</saml:NameID>
  <samlp:SessionIndex>session-s1</samlp:SessionIndex>
</samlp:LogoutRequest>
~~~

**Đây là mảnh XML minh họa**, chưa có chữ ký số/binding encoding và không phải LogoutRequest dùng được trong hệ thống thật. `subject-example`, `session-s1` chỉ là dữ liệu mẫu, không phải thông tin người dùng thực.

Những điều cần phân biệt:

1. **NameID** gắn với subject trong một mối quan hệ federation, không mặc định là email hoặc user ID toàn cục.
2. **SessionIndex** liên quan session giữa subject và session authority; không phải `JSESSIONID`, UUID của mọi thiết bị hay ID của API token.
3. **SP-initiated SLO theo Web Browser SSO Profile** cần cung cấp SessionIndex phù hợp với AuthnStatement đã nhận. Errata E38 của OASIS làm rõ quy tắc này. Trong **Core LogoutRequest** phần tử này là optional, nhưng profile áp dụng có thể thêm yêu cầu bắt buộc.
4. **Khi session authority/IdP khởi tạo logout**, có thể không gửi SessionIndex để chỉ thị chấm dứt tất cả các phiên áp dụng của subject theo profile. Phạm vi cụ thể còn phụ thuộc định danh subject và cách SP/IdP triển khai.
5. Một user có thể có nhiều SessionIndex qua nhiều lần xác thực, trình duyệt, thiết bị hoặc application context; không dùng một index để kết luận đã revoke mọi phiên.
6. Nếu SP chỉ biết một `HttpSession` trong browser hiện tại, nó có thể không có registry để tìm và hủy mọi `HttpSession` khác tương ứng subject/SessionIndex.

**Không tự lấy SessionIndex từ URL do người dùng cung cấp** để hủy session của người khác. Chỉ dùng dữ liệu được lấy từ assertion đã xác minh và các thông điệp SLO đã được kiểm chứng, kèm scope theo issuer/registration.

## 8. Front-channel và back-channel: giới hạn khác nhau

SAML hỗ trợ các binding/luồng truyền thông điệp logout. Hai khái niệm chính:

| Kênh | Cách hoạt động | Lợi ích | Giới hạn |
| --- | --- | --- | --- |
| **Front-channel** | Browser chuyển qua các endpoint SLO bằng Redirect/POST | SP có thể nhìn thấy cookie session của chính browser | Người dùng đóng tab, JS/CSP, cookie/SameSite, browser privacy, timeout có thể ngắt |
| **Back-channel** | Server-to-server, ví dụ SOAP profile theo đặc tả/hỗ trợ vendor | Không phụ thuộc chuỗi browser navigation sau khi gửi | SP phải tìm đúng session trên server; backend/network/firewall/compatibility, không có sẵn mọi nơi |
| **Provider-specific logout API** | IdP/SP dùng API riêng để thu hồi phiên | Có thể nhắm tới thiết bị/tài khoản theo khả năng nhà cung cấp | Không phải SAML SLO chuẩn; cần tích hợp, quyền và audit riêng |

**Front-channel không thể xóa cookie của domain khác theo ý muốn**. Nó yêu cầu browser thật đi đến từng domain/endpoint. Cookie `SameSite` hoặc thiết lập third-party cookie ảnh hưởng đến việc request nào mang cookie. Một số IdP dùng iframe để điều phối; khả năng hoạt động phụ thuộc chính sách browser và cấu hình ứng dụng.

**Back-channel không phải thuốc chữa mọi vấn đề:** Nếu SP chỉ có session ID gắn với cookie browser và không duy trì mapping **(issuer, subject, SessionIndex) → session IDs**, một LogoutRequest server-to-server có thể không đủ để tìm đúng local sessions. Không nên hủy mọi session có email giống nhau mà không kiểm tra subject và scope.

Spring Security 6.5 cung cấp hỗ trợ SAML2 SLO qua HTTP POST/Redirect ở phần cấu hình mặc định đã được tài liệu hóa. Không giả định API đó tự có server-to-server SOAP orchestration cho mọi profile hoặc khả năng thu hồi mọi session.

## 9. SLO phụ thuộc khả năng hỗ trợ và metadata của từng đối tác

Để hai bên phối hợp SLO, metadata cần công bố đúng endpoint và binding:

- **IdP metadata:** `IDPSSODescriptor` có `SingleLogoutService` dùng cho LogoutRequest/LogoutResponse hướng đến IdP.
- **SP metadata:** `SPSSODescriptor` có `SingleLogoutService` để IdP có thể gửi LogoutRequest đến SP.
- **SP signing credentials:** public cert được IdP tin, private key được SP bảo vệ để ký messages khi yêu cầu.
- **IdP verification credentials:** SP dùng đúng certificates IdP để xác minh LogoutRequest/Response.
- **EntityIDs và URL:** issuer, destination, response location và base URL phải khớp thỏa thuận.
- **Chính sách thời gian và replay:** thông điệp cũ/trùng ID bị từ chối.
- **Binding tương thích:** Redirect/POST cần đúng cách ký/encode và gửi message.

Ví dụ một IdP **không công bố SingleLogoutService** hoặc không hỗ trợ SLO thì việc bật `.saml2Logout()` ở SP **không khiến IdP tự hỗ trợ**. Hãy kiểm tra tài liệu nhà cung cấp, metadata thật và thử tích hợp. Một số hệ thống chỉ hỗ trợ đăng xuất session tại IdP, không truyền yêu cầu tới mọi SP; đó là phạm vi tính năng khác với full SLO.

**Không sửa bằng cách** tắt signature validation của LogoutRequest/LogoutResponse, chấp nhận mọi Issuer hoặc cho redirect tới URL logout do browser tự chọn.

## 10. Spring Security: các thành phần tham gia SLO

Trong ứng dụng Servlet, những lớp/cấu hình sau cần được biết:

| Thành phần | Vai trò |
| --- | --- |
| `HttpSecurity.saml2Logout(...)` | Bật RP-initiated và AP-initiated SAML2 Logout theo cấu hình |
| `RelyingPartyRegistration` | Chứa SP/IdP entity, SLO endpoints, signing và verification credentials |
| `Saml2RelyingPartyInitiatedLogoutSuccessHandler` | Tạo luồng logout bắt đầu từ SP |
| `Saml2LogoutRequestResolver` | Dựng, ký và đóng gói LogoutRequest |
| `Saml2LogoutRequestRepository` | Lưu request đã phát để đối chiếu LogoutResponse/RelayState/InResponseTo |
| `Saml2LogoutRequestFilter` | Xử lý và xác minh yêu cầu từ IdP (AP-initiated) |
| `Saml2LogoutResponseFilter` | Xử lý và xác minh phản hồi logout từ IdP |
| `Saml2LogoutRequestValidator` | Xác minh yêu cầu logout theo thông điệp và registration |
| `Saml2LogoutResponseValidator` | Xác minh phản hồi logout |
| `LogoutHandler` | Thực hiện cleanup local như invalidating session/SecurityContext |
| `SecurityContextRepository` | Lưu/đọc context bảo mật của local web session |

**Đây là các phần để một SP tham gia giao thức, không phải một service toàn cục quản lý phiên của mọi ứng dụng.** Nếu cần thu hồi đồng thời mọi phiên trên cụm server hoặc mọi thiết bị, SP phải có session registry, storage và policy bổ sung.

### Hành vi RP-initiated

Theo tài liệu Spring Security 6.5, khi cấu hình SAML SLO đúng, POST logout của người dùng đã xác thực bằng SAML có thể:

1. Chạy logout handlers, hủy session cục bộ.
2. Sinh LogoutRequest có chữ ký tới IdP theo registration.
3. Đợi/tiếp nhận LogoutResponse nếu IdP quay lại.
4. Kiểm tra LogoutResponse, correlation và xử lý điều hướng cuối.

Điểm dễ hiểu sai: **local session có thể đã bị hủy trước khi IdP hoàn tất việc truyền logout tới các ứng dụng khác**. Một trình duyệt bị ngắt sau bước 1 vẫn có thể đã logout Portal nhưng SLO toàn federation chưa hoàn thành.

### Hành vi AP-initiated

Khi IdP gửi một LogoutRequest đúng endpoint, Spring kiểm tra request và hủy local session trong ngữ cảnh request được xử lý, rồi tạo LogoutResponse. Đối với “logout mọi thiết bị”, phải xác định repository/session mapping của ứng dụng có thực sự tìm và xóa được **mọi session khác** hay không; không suy luận từ việc filter trả Success.

## 11. Ví dụ cấu hình SAML2 SLO trong Spring Boot 3 / Spring Security 6.x

Ví dụ cho ứng dụng **Spring Boot 3.x, Spring Security 6.x, Java 17+, Servlet MVC**. Mã cấu hình không chạy độc lập chỉ bằng `javac`; cần dependency Spring Security SAML service provider, metadata IdP thật, key/cert SP thật và SP đã đăng ký ở IdP.

Tệp `src/main/resources/application.yml`:

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          corp:
            assertingparty:
              metadata-uri: "classpath:saml/corp-idp-metadata.xml"
            signing:
              credentials:
                - private-key-location: "classpath:keys/sp-signing.key"
                  certificate-location: "classpath:keys/sp-signing.crt"
            singlelogout:
              url: "{baseUrl}/logout/saml2/slo"
~~~

**Yêu cầu bắt buộc trước khi dùng:**

1. `corp-idp-metadata.xml` phải thuộc IdP đã được tin và chứa endpoint `SingleLogoutService` với binding phù hợp, cùng keys xác minh chữ ký. Đây phải là metadata thật; không tự chế certificate rỗng.
2. SP ký LogoutRequest/LogoutResponse bằng private key/certificate do mình sở hữu; IdP phải biết public certificate SP. Tài liệu Spring Security hướng dẫn key PKCS#8 và X.509 certificate.
3. Entity ID SP, URL SLO, scheme/host HTTPS công khai và proxy forwarding phải khớp metadata được IdP đăng ký.
4. Signing requirement của cả hai phía, NameID/SessionIndex và response bindings phải được kiểm thử.
5. Các domain hoặc URL ví dụ trong bài không phải hệ thống có sẵn để truy cập.

Tệp `src/main/java/com/example/security/SamlSecurityConfig.java`:

~~~java
package com.example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SamlSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/healthz").permitAll()
                .anyRequest().authenticated())
            .saml2Login(Customizer.withDefaults())
            .saml2Logout(Customizer.withDefaults())
            .build();
    }
}
~~~

**`.saml2Logout(Customizer.withDefaults())` bật khả năng xử lý SLO tại ứng dụng**, không bảo đảm IdP và các SP khác đều hỗ trợ hay đã phối hợp thành công. Khi cấu hình này hoạt động với login SAML, Spring Security 6.5 mô tả endpoint khởi tạo RP-initiated thường là **POST `/logout`**, còn endpoint AP-initiated và nhận LogoutResponse mặc định là **`/logout/saml2/slo`**.

**CSRF:** với trình duyệt sử dụng Spring Security logout, kích hoạt qua POST phù hợp và bảo vệ CSRF như cấu hình. Không biến logout nhạy cảm thành GET từ một liên kết tùy ý chỉ để tiện triển khai, đặc biệt khi ứng dụng còn dùng các phiên local và liên kết cross-site. Luồng SAML message có validation/signature riêng, không thay thế chính sách bảo vệ endpoint người dùng.

## 12. Phân biệt local logout và SAML SLO bằng hai endpoint

Đôi khi UX cần cho phép người dùng **đăng xuất khỏi Portal nhưng giữ session IdP**, ví dụ rời máy tính dùng chung, trong khi một tính năng khác yêu cầu **đăng xuất liên kết**.

Với Spring Security 6.5, có thể cấu hình hai endpoint riêng:

~~~java
@Bean
SecurityFilterChain securityFilterChain(HttpSecurity http)
        throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .anyRequest().authenticated())
        .saml2Login(Customizer.withDefaults())
        .logout(logout -> logout
            .logoutUrl("/logout/local"))
        .saml2Logout(saml -> saml
            .logoutUrl("/logout/saml2"))
        .build();
}
~~~

**Đây là phương án thay thế method bean ở mục trước**, không phải khai báo thêm một SecurityFilterChain trùng phạm vi. Cần imports và class cấu hình ở mục 11. Khi đã có đầy đủ SAML SLO registration:

| Lệnh | Mục đích | Kỳ vọng |
| --- | --- | --- |
| POST `/logout/local` | Đăng xuất Portal | Hủy local SP session; không yêu cầu IdP truyền SLO |
| POST `/logout/saml2` | Khởi tạo RP-initiated SLO | Hủy local session, gửi LogoutRequest tới IdP |
| POST `/logout/saml2/slo` với SAMLRequest | IdP gửi AP-initiated logout | Xác minh request, cleanup local session và phản hồi |
| POST `/logout/saml2/slo` với SAMLResponse | IdP phản hồi RP-initiated logout | Xác minh response và kết thúc luồng |

Cần đảm bảo những URL đó không xung đột với endpoint ứng dụng hay policy CSRF, và metadata SP phải công bố đúng SLO endpoint nếu bạn đổi đường dẫn nhận request/response.

**Không hứa local-only logout làm user không thể login lại ngay.** IdP cookie vẫn còn có thể kích hoạt SSO tự động.

## 13. LogoutResponse, Success và PartialLogout

Không nên đánh đồng `LogoutResponse` với bằng chứng “mọi ứng dụng đã đóng”. Cần kiểm chứng:

1. LogoutResponse thật sự đến từ đúng IdP/registration với signature hợp lệ và endpoint hợp lệ.
2. `InResponseTo` khớp LogoutRequest đã gửi, không bị giả/replay.
3. `StatusCode` và status phụ được diễn giải theo SAML/profile/vendor.
4. Bản thân Portal đã hủy session cục bộ.
5. Có hay không bằng chứng IdP đã truyền đến các participants và nhận phản hồi.
6. Các ứng dụng/thiết bị ngoài phạm vi không bị hiểu lầm là đã logout.

SAML có status **`urn:oasis:names:tc:SAML:2.0:status:PartialLogout`** để chỉ trường hợp session authority **không truyền được logout tới tất cả participant**. Trạng thái có thể được biểu diễn như status phụ bên dưới status chính tùy thông điệp/vendor. UI không nên báo “Đã đăng xuất ở mọi nơi” nếu nhận PartialLogout.

| Tình huống | Điều được phép khẳng định |
| --- | --- |
| Local SP session đã invalidated | Người dùng đã logout khỏi session Portal hiện tại |
| LogoutRequest đã gửi IdP | Đã bắt đầu yêu cầu SLO; kết quả các SP khác chưa xác minh |
| LogoutResponse thành công | IdP phản hồi giao thức hợp lệ; kiểm tra thêm phạm vi và participant status |
| PartialLogout | Có participant chưa xử lý được; thông báo giới hạn/đề nghị đóng app khác |
| Timeout/không nhận response | Không có xác nhận đầy đủ; trạng thái remote còn chưa biết |
| Browser đã đóng sau local logout | Local session có thể đã kết thúc; propagation chưa chắc hoàn thành |
| Token API vẫn có hạn | Chưa thể tuyên bố đã thu hồi token |

Lỗi sản phẩm thường gặp là thông báo “Đăng xuất mọi thiết bị thành công” ngay sau khi người dùng gọi logout tại một SP. Đây là một tuyên bố **vượt quá bằng chứng**.

## 14. Mất mạng, đóng tab, cookie và chính sách trình duyệt

SLO có thể thất bại do những lý do rất đời thường:

- Browser điều hướng tới IdP nhưng người dùng đóng tab.
- Mạng mất kết nối hoặc IdP SLO endpoint trả 5xx.
- Một SP đang bảo trì, server timeout, hoặc reverse proxy không chuyển được request.
- Cookie session không được gửi ở ngữ cảnh cross-site vì `SameSite`, third-party-cookie policy hoặc cách nhúng iframe.
- Security headers, CSP hoặc cấu hình JavaScript không phù hợp với form POST/Redirect của SLO.
- Domain/certificate/ACS/SLO URL thay đổi nhưng metadata hai phía chưa đồng bộ.
- Browser đã thực hiện logout ở tab A nhưng tab B vẫn hiển thị dữ liệu cũ.
- Request logout đến ứng dụng trước khi session index/association được lưu hoặc sau khi session cục bộ hết hạn.

**Không “chữa” lỗi bằng cách** vô hiệu hóa XML signature verification, chấp nhận mọi issuer, tự tin URL logout từ query string hay bỏ qua `InResponseTo`.

Thiết kế nên có **timeout hữu hạn**, quan sát được từng pha, thông báo kết quả trung thực và phương án cho người dùng tiếp tục thao tác an toàn. Các service có quyền quản trị/PII nhạy cảm nên xử lý logout failure theo chính sách rủi ro thay vì chỉ dựa vào UI.

## 15. Backend sessions nhiều node và đa thiết bị

Nếu Portal chạy trên nhiều node với session lưu ở Redis/Spring Session hoặc hệ thống riêng, việc hủy `HttpSession` trong một request thông thường chỉ nhắm tới session được nhận diện. Để thu hồi **tất cả local sessions** của một subject, ứng dụng phải có cơ chế:

- Nhận diện **issuer/registrationId + subject ID ổn định** (và SessionIndex nếu cần), tránh gộp tài khoản chỉ bằng email.
- Liệt kê **server-side session IDs** tương ứng phạm vi muốn thu hồi.
- Thực hiện invalidation đồng bộ qua các node hoặc hệ thống session tập trung.
- Ghi nhận session nào đã thu hồi/không tìm thấy/lỗi.
- Kiểm tra rằng request tiếp theo với cookie cũ bị 401/302/403 theo chính sách.
- Không để listener/cache được đồng bộ chậm giữ `Authentication` cũ có quyền nhạy cảm.
- Có TTL/ngăn replay, tránh thao tác dựa trên thông điệp logout chưa được kiểm chứng.

Spring Security có cơ chế session management và concurrent session control, nhưng **không mặc định map toàn bộ `SessionIndex` từ mọi IdP đến mọi thiết bị rồi thu hồi account-wide**. Cơ chế đó đòi kiến trúc và kiểm thử riêng; khi dùng Spring Session, phải đối chiếu khả năng tìm session theo principal và custom SAML identifier của hệ thống.

**Sai:** `LogoutRequest NameID = an@example.test` → xóa mọi session có cùng email trên mọi tenant. **Đúng:** kiểm tra issuer/NameID format/NameQualifier và scope đã được xác minh, tenant mapping, SessionIndex/chính sách rồi mới quyết định session nào được phép hủy.

## 16. Các loại token ngoài SAML session

Một ứng dụng có thể dùng SAML để login trang web nhưng sau đó phát các loại credential khác:

| Credential | SLO có tự làm nó vô hiệu không? | Biện pháp bổ sung |
| --- | --- | --- |
| SP session cookie | Chỉ khi SP invalidates đúng session | Logout handler/central session store |
| HTTP remember-me token | Không bảo đảm | Thu hồi remember-me token/cookie theo policy |
| JWT access token tự chứa | Không mặc định; có thể còn hợp lệ tới `exp` | TTL ngắn, denylist/revocation check khi cần |
| Opaque access token | Không tự động | Introspection/revocation tại authorization server |
| OAuth2 refresh token | Không tự động | Revoke refresh tokens/token family |
| Mobile long-lived session | Không tự động | Backend device-session registry và remote logout |
| WebSocket đã kết nối | Không chắc | Đóng/reauth kênh gắn với session bị thu hồi |
| Service-to-service token | Ngoài phạm vi user SAML SLO | Credential lifecycle độc lập |
| Offline cache | Không | Xóa theo client security policy, không xem là credential server |

**Đặc biệt:** việc xóa cookie IdP chỉ ngăn tái sử dụng IdP SSO session tương ứng. Nó không làm một JWT đã phát cho API bị mất hiệu lực nếu resource server vẫn xác minh chữ ký và `exp` mà không tra cứu revocation state. Hãy kiểm thử **sau logout còn gọi API được hay không** thay vì suy đoán.

SAML SLO không phải OIDC Front-Channel Logout, Back-Channel Logout hoặc OAuth Token Revocation. Trong hệ thống kết hợp nhiều giao thức, phải có kế hoạch logout tổng thể cho từng lớp, không lấy một LogoutResponse SAML làm chứng cứ cho toàn bộ.

## 17. Thiết kế chức năng “Đăng xuất khỏi tất cả thiết bị” thật sự

Khi nghiệp vụ yêu cầu **logout-all-devices**, thiết kế thường cần nhiều lớp:

1. **IdP:** sử dụng API/admin capability để thu hồi mọi phiên IdP của tài khoản trong phạm vi được cấp phép.
2. **Ứng dụng SP:** tìm và hủy mọi local sessions của account nội bộ qua backend session registry.
3. **Other SPs:** yêu cầu phối hợp theo SLO hoặc cơ chế quản trị/server-side revocation được hỗ trợ, nhận acknowledgement.
4. **OAuth/OIDC:** thu hồi refresh tokens, active grants và áp policy đối với access tokens.
5. **Ứng dụng mobile:** hủy device sessions và server-side refresh token families.
6. **Các phiên chưa liên hệ được:** đặt thời hạn ngắn, chặn request mới nhờ session version/revocation epoch ở backend.
7. **Audit:** ghi rõ từng scope, từng loại session, kết quả thành công/chưa rõ/thất bại.
8. **UX:** thông báo người dùng những phiên nào đã thoát và cần thao tác thủ công ở đâu, không tuyên bố quá mức.

**Ví dụ “session version”:** Mỗi account có `sessionVersion` hoặc `revokedBefore` do server quản lý. Khi logout-all, tăng version/cập nhật timestamp và mỗi request nhạy cảm kiểm tra session/token hiện tại có được phát trước mốc thu hồi hay không. Cần thiết kế chính xác consistency, race condition, đồng hồ, TTL, caching và đặc thù JWT; đây là **cơ chế bổ sung do ứng dụng xây**, không phải chức năng SAML SLO tự cung cấp.

Nếu yêu cầu pháp lý/an ninh là vô hiệu hóa ngay mọi quyền, phải đánh giá độ trễ của cache/edge/microservices. Không thể bảo đảm realtime chỉ với một browser redirect.

## 18. Java 17 độc lập: mô phỏng phạm vi SLO trên nhiều phiên

Ví dụ sau **biên dịch/chạy được với JDK 17+**, không dùng thư viện ngoài. Nó minh họa một quyết định chính sách: SLO khởi tạo cho IdP session **S1** có thể nhắm tới các participant đã tham gia S1; những phiên từ session **S2** và ứng dụng không hỗ trợ SLO nằm ngoài phạm vi. Một participant có thể nhận yêu cầu nhưng thất bại xử lý.

Tạo file **SloCoverageDemo.java**:

~~~java
import java.util.List;

public class SloCoverageDemo {

    record LocalSession(
            String app,
            String device,
            String idpSession,
            boolean sloParticipant,
            boolean deliverySucceeded) {}

    static String result(LocalSession local, String targetIdpSession) {
        if (!local.idpSession().equals(targetIdpSession)) {
            return "OUT_OF_SCOPE";
        }
        if (!local.sloParticipant()) {
            return "NOT_PARTICIPANT";
        }
        if (!local.deliverySucceeded()) {
            return "PENDING_OR_FAILED";
        }
        return "CLOSED";
    }

    public static void main(String[] args) {
        List<LocalSession> sessions = List.of(
            new LocalSession("Portal", "Laptop-Chrome", "S1", true, true),
            new LocalSession("HRM", "Laptop-Chrome", "S1", true, false),
            new LocalSession("CRM", "Laptop-Chrome", "S1", false, true),
            new LocalSession("Portal", "Mobile", "S2", true, true)
        );

        for (LocalSession session : sessions) {
            System.out.println(session.app() + " / " + session.device()
                    + ": " + result(session, "S1"));
        }
    }
}
~~~

Lệnh biên dịch và chạy:

~~~bash
javac SloCoverageDemo.java
java SloCoverageDemo
~~~

**Stdout chính xác:**

~~~text
Portal / Laptop-Chrome: CLOSED
HRM / Laptop-Chrome: PENDING_OR_FAILED
CRM / Laptop-Chrome: NOT_PARTICIPANT
Portal / Mobile: OUT_OF_SCOPE
~~~

Diễn giải:

- **Portal/Laptop-Chrome:** cùng IdP session S1, đã tham gia SLO và nhận được yêu cầu thành công.
- **HRM/Laptop-Chrome:** thuộc S1 và hỗ trợ SLO, nhưng request không hoàn tất; không thể khẳng định đã logout.
- **CRM/Laptop-Chrome:** không tham gia SLO nên SLO của S1 không tự làm CRM logout.
- **Portal/Mobile:** thuộc S2; LogoutRequest cho S1 không tự thu hồi session này.

**Mô hình này chỉ minh họa logic phạm vi**, không phân tích XML, không xác minh chữ ký, không dùng NameID/SessionIndex thật và không xóa session nào. Trong hệ thống thật, `deliverySucceeded` chưa đủ: phải biết SP đã thực sự invalidates phiên theo protocol và policy. Không lấy chuỗi S1/S2 từ tham số client chưa xác thực hoặc coi `CLOSED` của demo là bằng chứng sản xuất.

## 19. Thiết kế trải nghiệm người dùng không gây hiểu nhầm

Trên trang logout, sản phẩm nên phân biệt rõ ba lựa chọn (khi nền tảng thật sự hỗ trợ):

| Lựa chọn | Mục đích | Thông báo đúng phạm vi |
| --- | --- | --- |
| **Đăng xuất ứng dụng** | Hủy phiên Portal hiện tại | “Đã đăng xuất khỏi Portal trên trình duyệt này.” |
| **Đăng xuất liên kết SAML** | Yêu cầu IdP truyền logout cho participant của phiên hiện tại | “Đã yêu cầu đăng xuất các ứng dụng liên kết. Một số ứng dụng có thể chưa hoàn tất.” |
| **Đăng xuất mọi thiết bị** | Thực hiện account-wide backend session/token revocation | Chỉ thông báo đã hoàn tất khi có đủ bằng chứng từ từng hệ thống |

Nếu IdP trả PartialLogout hoặc một SP không phản hồi:

- Trình bày rõ **Portal đã thoát** hay chưa.
- Cho biết **các ứng dụng/thiết bị khác có thể vẫn đang đăng nhập**.
- Hướng dẫn đóng và logout thủ công tại ứng dụng không tham gia hoặc không phản hồi.
- Nếu người dùng đang xử lý mất thiết bị hoặc nghi lộ tài khoản, hướng dẫn quy trình thu hồi mọi phiên/tokens do tổ chức hỗ trợ.
- Không hiển thị tên tài khoản, SessionIndex, NameID hoặc dữ liệu nhạy cảm không cần thiết trên trang lỗi.

Cần lưu ý SLO request/response qua browser có thể chuyển quyền điều hướng sang IdP; Spring Security không thể luôn kiểm soát trang sẽ hiển thị sau AP-initiated logout.

## 20. Runbook ứng phó khi SLO chỉ hoàn tất một phần

### A. Người dùng báo “Đã logout Portal nhưng HRM vẫn mở”

1. Kiểm tra Portal thật sự hủy local session của browser tương ứng.
2. Xác nhận người dùng gọi **local logout** hay **RP-initiated SLO**.
3. Kiểm tra metadata của HRM và IdP có `SingleLogoutService` đúng.
4. Kiểm tra HRM có tham gia phiên IdP được nêu bởi SessionIndex hay không.
5. Xác minh IdP đã gửi LogoutRequest tới HRM, binding, thời điểm, issuer, destination.
6. Kiểm tra HRM nhận, xác minh và invalidates đúng local session; xem các lỗi cookie/session mapping.
7. Nếu chưa xử lý được, hướng dẫn logout HRM trực tiếp và ghi nhận sự cố.
8. Không chuyển sang bỏ kiểm tra chữ ký hoặc chấp nhận mọi SessionIndex.

### B. Browser đóng giữa quy trình

1. Ghi trạng thái **local logout** và **SLO propagation** riêng.
2. Nếu local session đã hủy, đảm bảo request mới đến Portal phải xác thực lại.
3. Không kết luận IdP hoặc các SP đã logout khi chưa có phản hồi.
4. Truy vấn telemetry của IdP/participant theo correlation ID và khoảng thời gian.
5. Nếu rủi ro cao, thực hiện server-side revocation bổ sung theo policy.

### C. Người dùng yêu cầu logout mọi thiết bị

1. Xác minh người yêu cầu và phạm vi tài khoản/tenant được phép quản lý.
2. Gọi cơ chế thu hồi **all IdP sessions** nếu IdP hỗ trợ.
3. Thu hồi sessions tại các ứng dụng do tổ chức quản lý qua session store/service.
4. Thu hồi refresh tokens/authorized grants và áp chiến lược đối với access tokens.
5. Kiểm tra truy cập từ thiết bị khác thật sự bị từ chối với cookies/tokens cũ.
6. Ghi những hệ thống chưa hỗ trợ hoặc chưa phản hồi; không tuyên bố “mọi nơi” khi còn ngoại lệ.
7. Theo dõi người dùng có thể đăng nhập lại bằng session khác chưa thu hồi hay không.

### D. IdP trả PartialLogout

1. Kiểm tra response đã được xác minh và `InResponseTo` đúng.
2. Xác định participant nào không được liên lạc hoặc không trả response.
3. Kiểm tra lỗi mạng, front-channel cookie, endpoint và metadata.
4. Không retry ồ ạt hoặc vô hạn; áp rate limits/backoff, ngăn replay.
5. Cân nhắc hướng dẫn logout thủ công hoặc xử lý backend hỗ trợ.
6. Tách **logout local PASS** với **federated propagation PARTIAL** trong audit.

## 21. Lỗi phổ biến và nguyên nhân

| Triệu chứng | Nguyên nhân khả dĩ | Hướng kiểm tra |
| --- | --- | --- |
| Logout Portal xong login lại không cần nhập mật khẩu | Chỉ local logout; IdP session vẫn tồn tại | Xem đúng endpoint đã gọi và IdP cookie |
| Logout ở App A nhưng App B vẫn đăng nhập | B không tham gia SLO, request thất bại hoặc session khác | Kiểm tra participants, LogoutRequest và local session B |
| Chỉ thiết bị vừa logout bị ảnh hưởng | SLO nhắm IdP SessionIndex của thiết bị đó | Không gọi đó là account-wide logout; có cơ chế remote revoke |
| IdP nói đã logout nhưng SP giữ phiên | SP không nhận request/không có session mapping | Kiểm tra binding, cookies, session registry và logs |
| `LogoutResponse` không tới Portal | Browser bị đóng, IdP không redirect, timeout | Tách trạng thái local/remote, không tự báo all-logout |
| `PartialLogout` | Một hoặc nhiều participants không xử lý | Xác định participant lỗi, hướng dẫn người dùng |
| SAML logout trả 400 | Signature/issuer/destination/status/correlation sai | So metadata, keys, `InResponseTo` và validation |
| SLO endpoint trả 404 | Sai URL hoặc chưa bật DSL | Kiểm tra `saml2Logout` và SingleLogoutService |
| POST logout trả 403 | CSRF token/config sai ở local user-triggered request | Dùng POST đúng CSRF; không tắt bảo vệ toàn ứng dụng |
| Có nhiều IdP, logout gửi nhầm IdP | Chọn registration sai | So principal/issuer/registration, không dùng URL từ client |
| App dùng JWT vẫn gọi API được sau SLO | JWT chưa hết hạn và không có revocation | Thiết kế revocation/introspection/TTL |
| Tab cũ vẫn thấy giao diện | SPA cache/local state vẫn còn | Đóng UI state và kiểm tra API ở server |
| Một node giữ session sau logout | Session storage/replication không đồng bộ | Kiểm tra distributed sessions và invalidation |
| User có hai phiên cùng email, logout nhầm người | Ghép tài khoản không dựa issuer/subject ổn định | Ràng buộc issuer/NameID/tenant/SessionIndex |
| Một SP không hỗ trợ SLO từ nhà cung cấp IdP | Profile/binding không tương thích | Đọc metadata, docs IdP và kiểm thử end-to-end |

**Lưu ý với bảo mật sự cố:** Không giải quyết bằng việc bỏ signature verification, tắt replay protection, tin mọi `NameID` hoặc xóa hàng loạt session người dùng khác do so email. Lỗi logout cần được phát hiện và xử lý trong **đúng scope**.

## 22. Ma trận kiểm thử thực tế

Tổ chức nên thử tối thiểu các trường hợp sau, dùng browser thật và IdP thử nghiệm có metadata/key đáng tin:

| Test | Bối cảnh | Kỳ vọng |
| --- | --- | --- |
| 01 | Một SP, một browser, RP-initiated SLO | Local session bị hủy, thông điệp hợp lệ, IdP phản hồi phù hợp |
| 02 | Hai SP cùng một IdP session, cả hai hỗ trợ SLO | Cả hai local sessions liên quan bị hủy nếu propagation hoàn tất |
| 03 | SP thứ hai không hỗ trợ SLO | Không báo “đã logout mọi ứng dụng” |
| 04 | Hai browser khác nhau với IdP sessions khác | Logout S1 không tự giả định S2 cũng bị thu hồi |
| 05 | Mobile API refresh token còn hiệu lực | Kiểm tra token vẫn dùng được hay đã revoke bởi cơ chế riêng |
| 06 | Browser bị đóng ngay khi gửi LogoutRequest | Local logout và remote SLO trạng thái tách biệt |
| 07 | IdP SLO endpoint trả 503 | Ứng dụng xử lý timeout/phản hồi an toàn |
| 08 | SP participant offline hoặc trả 500 | PartialLogout/unknown được phản ánh đúng |
| 09 | IdP-initiated LogoutRequest hợp lệ | SP hủy đúng session và trả response phù hợp |
| 10 | IdP-initiated LogoutRequest sai chữ ký | Từ chối, không cho kẻ lạ hủy session |
| 11 | LogoutResponse giả mạo hoặc replay | Bị từ chối theo signature và InResponseTo |
| 12 | SessionIndex không khớp | Không hủy nhầm session/tenant |
| 13 | SameSite/cookie policy khác nhau | Phát hiện browser-dependent failure, không bypass trust |
| 14 | Nhiều server/nhiều vùng | Session invalidation nhất quán |
| 15 | Hai IdP khác nhau | SLO chỉ tác động đúng federation link |
| 16 | SLO xong mở tab cũ gọi API | Request mới không được dùng session đã hủy |
| 17 | SP có WebSocket hoặc remember-me | Các credential phụ được cleanup/thu hồi theo chính sách |
| 18 | SP và IdP xoay chứng thư SLO signing | Request/Response mới được xác minh đúng key |
| 19 | Reverse proxy có HTTPS external host | Destination/Issuer/SLO URL khớp metadata |
| 20 | “Logout all devices” qua backend riêng | Mọi local sessions/tokens nằm trong scope được xác minh đã revoke |

Test chỉ nhìn thấy trang “Signed out” **không đủ**. Phải thử các request sau logout, kiểm tra session store/token introspection và telemetry từng participant.

## 23. Giám sát, audit và định nghĩa kết quả rõ ràng

Để không che giấu lỗi SLO, ghi các kết quả độc lập:

- **Local session invalidated:** true/false, session scope, thời điểm.
- **SLO initiated:** true/false; IdP entityID và registrationId đã xác minh.
- **LogoutRequest signed/dispatched:** true/false; binding và endpoint.
- **LogoutResponse verified:** success/failure/timeout/unknown.
- **Status code:** Success, PartialLogout hoặc lỗi khác theo đặc tả.
- **Participant outcome:** hoàn tất/thất bại/không hỗ trợ/chưa biết khi có dữ liệu đáng tin.
- **Account-wide revocation:** kết quả của cơ chế riêng, không gộp với SLO.
- **Post-logout access:** request từ session/token cũ có bị từ chối không?
- **Correlation:** ID request, thời gian, issuer và dấu vết bảo mật không chứa PII.

Các tên metrics như `saml_slo_local_logout_total`, `saml_slo_partial_total`, `saml_slo_timeout_total`, `saml_slo_request_validation_failures_total` là **đề xuất để tự triển khai**, không phải mặc định Spring Security cung cấp.

**Không log** toàn bộ SAML LogoutRequest/LogoutResponse chứa NameID, SessionIndex hoặc private key. Nếu cần giám sát, dùng correlation ID và định danh đã rút gọn/ẩn thích hợp, cùng chính sách bảo vệ logs.

Một dashboard tốt phân tách **local logout rate**, **SLO protocol success rate**, **partial/unknown propagation** và **token/session revocation rate**, tránh trộn tất cả thành một ô xanh “Logout Success”.

## 24. Câu hỏi tự đánh giá

**1. SAML SLO có bảo đảm đăng xuất khỏi mọi ứng dụng và mọi thiết bị không?**  
Không. Nó điều phối những session participants thuộc phạm vi SAML SLO; quá trình có thể bị gián đoạn, một số app không tham gia hoặc dùng phiên IdP khác.

**2. Nếu Portal hủy local HttpSession rồi IdP không phản hồi, Portal đã logout chưa?**  
Có thể đã logout tại Portal; nhưng không đủ bằng chứng để khẳng định các ứng dụng khác đã logout.

**3. `SessionIndex` có phải `JSESSIONID` hoặc account ID không?**  
Không. Nó liên quan session SAML do session authority quản lý và phải được ràng buộc theo issuer/subject/registration.

**4. Một LogoutRequest từ SP cho SessionIndex S1 có chắc chắn hủy S2 trên điện thoại không?**  
Không. S2 có thể là IdP session khác; cần cơ chế account-wide nếu muốn thu hồi mọi thiết bị.

**5. App chỉ sử dụng OIDC/JWT có tự nhận SAML LogoutRequest không?**  
Không. Cần logout/revocation theo giao thức và khả năng app tương ứng.

**6. Vì sao front-channel SLO dễ không hoàn tất?**  
Nó phụ thuộc browser ghé thăm các endpoint, cookie, JS/CSP, mạng và việc user không dừng luồng giữa chừng.

**7. `PartialLogout` cho biết điều gì?**  
Session authority không truyền được logout tới tất cả participants; không được báo hoàn tất tuyệt đối.

**8. Đăng xuất Portal nhưng login lại lập tức là lỗi chắc chắn không?**  
Không. Nếu chỉ local logout mà IdP SSO session còn sống, đăng nhập lại có thể tự động.

**9. Bật `.saml2Logout(withDefaults())` có đủ để mọi ứng dụng ngoài Portal cùng logout không?**  
Không. Cần IdP hỗ trợ SLO, metadata, keys, endpoint/binding, các SP khác tham gia và xử lý thành công.

**10. Người dùng bị khóa tài khoản phải thu hồi mọi phiên ở đâu?**  
Ngoài SAML SLO, phải áp chính sách khóa tại IdP, hủy local SP sessions, revoke tokens và áp authorization hiện hành trong backend.

## 25. Checklist triển khai production

- [ ] Định nghĩa rõ tính năng là **local logout**, **SAML SLO** hay **logout-all-devices**.
- [ ] Kiểm tra IdP hỗ trợ SLO, metadata có SingleLogoutService và binding phù hợp.
- [ ] SP có signing credentials và IdP verification credentials cho LogoutRequest/Response.
- [ ] `RelyingPartyRegistration` chứa SLO URL, entity IDs và URL public nhất quán.
- [ ] Bật `saml2Logout` và phân biệt endpoint local/SAML nếu UX yêu cầu.
- [ ] Dùng POST và CSRF đúng cách ở user-triggered logout; không tự bỏ kiểm tra chữ ký SAML.
- [ ] Xác minh LogoutRequest/Response: issuer, signature, destination, replay, InResponseTo và status.
- [ ] Bảo toàn ràng buộc NameID + SessionIndex + IdP registration, tránh hủy nhầm tenant.
- [ ] Biết SP/IdP nào tham gia SLO và SP nào không hỗ trợ, không hứa full global logout.
- [ ] Kiểm thử nhiều tab, trình duyệt, điện thoại, IdP sessions và SP sessions khác nhau.
- [ ] Có cơ chế hủy mọi local sessions qua session registry khi yêu cầu account-wide.
- [ ] Có kế hoạch thu hồi OAuth/OIDC refresh tokens, JWT/API credentials, mobile sessions.
- [ ] Kiểm thử reverse proxy, cookies, SameSite, CSP, timeout và trường hợp user đóng tab.
- [ ] Hiển thị PartialLogout/unknown trung thực, không kết luận toàn bộ đã logout.
- [ ] Có telemetry theo từng pha, status, participant và bằng chứng kiểm thử access sau logout.
- [ ] Bảo vệ PII/NameID/SessionIndex trong logs, audit và UI.
- [ ] Có runbook khẩn cho mất thiết bị/lộ tài khoản, không phụ thuộc chỉ một browser redirect.

## 26. Kết luận

**SAML Single Logout giải quyết một phần bài toán đăng xuất liên kết, không phải công cụ bảo đảm thu hồi mọi phiên toàn hệ thống.** Với nhiều ứng dụng, chỉ những participant hỗ trợ SLO và thực sự nhận/xử lý thông điệp hợp lệ mới có thể kết thúc session tương ứng. Với nhiều trình duyệt hoặc thiết bị, các `SessionIndex` và IdP sessions có thể khác nhau nên logout của một phiên không mặc định bao phủ toàn bộ tài khoản. Với OAuth/OIDC/mobile/API, các token và sessions khác yêu cầu cơ chế thu hồi riêng.

Trong Spring Security, `saml2Logout` cung cấp các điểm nhận và phát LogoutRequest/Response cùng với local logout. Để xây chức năng an toàn, phải kiểm chứng thông điệp theo đúng IdP/registration, quản lý session ở server, tách trạng thái **local/remote/partial**, kiểm thử mất kết nối và truyền đạt giới hạn thật sự cho người dùng. **Đừng đánh đổi tính toàn vẹn SAML hoặc hứa đăng xuất toàn bộ nếu hệ thống không thể xác minh điều đó.**

### Tài liệu tham khảo chính thức

- Spring Security 6.5 — Performing Single Logout: https://docs.spring.io/spring-security/reference/6.5/servlet/saml2/logout.html
- Spring Security — Performing Single Logout (tài liệu phiên bản hiện hành): https://docs.spring.io/spring-security/reference/servlet/saml2/logout.html
- Spring Security — Handling Logouts: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/logout.html
- Spring Security — Authentication Persistence and Session Management: https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html
- OASIS — SAML V2.0 Technical Overview, Section 5.3: https://docs.oasis-open.org/security/saml/Post2.0/sstc-saml-tech-overview-2.0.html
- OASIS — SAML 2.0 Profiles, Single Logout Profile 4.4: https://docs.oasis-open.org/security/saml/v2.0/saml-profiles-2.0-os.pdf
- OASIS — SAML 2.0 Core, LogoutRequest/LogoutResponse/PartialLogout: https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf
- OASIS — SAML Version 2.0 Errata 05, E38 SessionIndex: https://docs.oasis-open.org/security/saml/v2.0/sstc-saml-approved-errata-2.0.html
- Okta — Configure Single Logout (ví dụ phạm vi device/session theo nhà cung cấp): https://developer.okta.com/docs/guides/single-logout/saml2/main/
