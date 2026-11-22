# Thời hạn phiên ứng dụng, thời hạn assertion và phiên IdP độc lập

**Module:** Spring Security – federation  
**Chủ đề cha:** Phiên và trình duyệt  
**Bối cảnh:** SAML 2.0 Web Browser SSO, Spring Boot 3.x, Spring Security 6.x, Java 17+.

## 1. Vấn đề quan trọng nhất: một lần SSO có nhiều “đồng hồ”

Trong SAML 2.0, người dùng đăng nhập tại **Identity Provider (IdP)** rồi đi vào **Service Provider (SP)** qua một SAML Response/Assertion đã được xác minh. Thoạt nhìn, người dùng chỉ “đăng nhập một lần”, nhưng hệ thống thực tế duy trì nhiều trạng thái và thời hạn riêng biệt:

1. **Thời hạn của SAML Assertion:** khoảng thời gian SP được phép **chấp nhận chứng cứ xác thực** nhận từ IdP khi xử lý SAMLResponse, thông qua **Conditions.NotBefore/NotOnOrAfter** và **SubjectConfirmationData.NotOnOrAfter**.
2. **Thời hạn phiên ứng dụng tại SP:** khoảng thời gian SP tiếp tục nhận diện người dùng thông qua **SecurityContext + HttpSession** hoặc kho phiên tương ứng; gồm **idle timeout**, có thể có **absolute lifetime** do ứng dụng tự đặt.
3. **Thời hạn phiên SSO tại IdP:** khoảng thời gian IdP tiếp tục xem browser đã xác thực với IdP để cấp SAMLResponse mới mà không yêu cầu thao tác xác thực đầy đủ; IdP có cookie/trạng thái phiên riêng.
4. **AuthnStatement.SessionNotOnOrAfter (nếu có):** một giới hạn phiên được IdP công bố trong **SAML AuthnStatement**; không được tự đồng nhất nó với timeout HttpSession tại SP hoặc với tuổi thọ cookie IdP.

Ba chiếc đồng hồ đầu tiên **không tự khóa chặt vào nhau**. SAML assertion hết hạn sau 5 phút **không có nghĩa** HttpSession SP sẽ tự hết hạn ở phút thứ 5; phiên IdP hết hạn **không có nghĩa** session SP đang hoạt động tự biến mất. Ngược lại, session SP hết hạn không chứng minh phiên IdP cũng đã hết.

**Kết luận ban đầu:** Tại thời điểm SP nhận SAMLResponse, phải kiểm tra assertion **đang còn hợp lệ**; sau khi login được chấp nhận, việc duy trì truy cập phụ thuộc **chính sách phiên SP**. Muốn đồng bộ hạn phiên hoặc yêu cầu xác thực lại phải thiết kế **chính sách bổ sung**, không suy diễn tự động từ giao thức.

## 2. Bảng so sánh bốn lớp thời gian

| Khái niệm | Bên kiểm soát | Trường/cấu hình | Điều gì hết hạn? | Có tự chấm dứt phiên SP? |
| --- | --- | --- | --- | --- |
| **SAML Assertion validity** | IdP phát biểu, SP xác minh | **Conditions.NotBefore / NotOnOrAfter**, bearer **SubjectConfirmationData.NotOnOrAfter** | Khả năng chấp nhận assertion ở bước login | **Không mặc định** sau khi login đã tạo session |
| **SP idle timeout** | SP/Servlet/Spring Session | **server.servlet.session.timeout**, **HttpSession.maxInactiveInterval** | HttpSession không được truy cập trong khoảng đặt trước | **Có** khi session SP bị expire |
| **SP absolute lifetime** | Policy SP, thường do ứng dụng tự thực thi | **authenticatedAt + maxLifetime** | Giới hạn tuyệt đối từ lúc xác thực, kể cả có hoạt động liên tục | **Có nếu ứng dụng thực thi** |
| **IdP SSO session** | IdP | IdP cookie + server-side session, IdP policy | Khả năng tái sử dụng đăng nhập tại IdP | **Không tự động** |
| **AuthnStatement.SessionNotOnOrAfter** | IdP phát biểu, SP cần diễn giải/chính sách | **saml:AuthnStatement SessionNotOnOrAfter** | Giới hạn session giữa subject và authentication authority được công bố trong assertion | **Không nên giả định Spring tự map thành HttpSession timeout** |
| **AuthnStatement.AuthnInstant** | IdP phát biểu | **saml:AuthnStatement AuthnInstant** | Không phải hạn; ghi lại thời điểm xác thực | **Không** |
| **SAML Response IssueInstant** | IdP phát biểu | **samlp:Response IssueInstant** | Thời điểm tạo Response, không tự là expiry | **Không** |
| **SAML metadata validUntil** | Nhà phát hành metadata | **EntityDescriptor.validUntil** | Hiệu lực metadata tin cậy, **không phải phiên của user** | **Không trực tiếp** |

**Không đánh đồng:** “assertion hợp lệ đến 08:05”, “IdP session đến 08:30” và “SP idle timeout 30 phút” là ba phát biểu khác nhau, ở ba lớp khác nhau. Quy trình kiểm tra ở mỗi lớp cũng khác nhau.

## 3. SAML XML: xác định chính xác từng mốc

Mảnh XML dưới đây chỉ để **đọc cấu trúc**. Nó thiếu chữ ký và nhiều thành phần của một SAML Response hợp lệ, **không được đưa trực tiếp vào production**:

~~~xml
<saml:Assertion
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    ID="_assertion_1"
    Version="2.0"
    IssueInstant="2026-11-07T08:01:00Z">
  <saml:Issuer>https://idp.example.org/saml/company</saml:Issuer>

  <saml:Subject>
    <saml:NameID>employee-847</saml:NameID>
    <saml:SubjectConfirmation
        Method="urn:oasis:names:tc:SAML:2.0:cm:bearer">
      <saml:SubjectConfirmationData
          InResponseTo="_authn_req_123"
          Recipient="https://portal.example.org/login/saml2/sso/company"
          NotOnOrAfter="2026-11-07T08:05:00Z"/>
    </saml:SubjectConfirmation>
  </saml:Subject>

  <saml:Conditions
      NotBefore="2026-11-07T08:00:00Z"
      NotOnOrAfter="2026-11-07T08:05:00Z">
    <saml:AudienceRestriction>
      <saml:Audience>https://portal.example.org/saml/sp/company</saml:Audience>
    </saml:AudienceRestriction>
  </saml:Conditions>

  <saml:AuthnStatement
      AuthnInstant="2026-11-07T07:45:00Z"
      SessionIndex="idp-session-index-77"
      SessionNotOnOrAfter="2026-11-07T08:30:00Z">
    <saml:AuthnContext>
      <saml:AuthnContextClassRef>
        urn:oasis:names:tc:SAML:2.0:ac:classes:PasswordProtectedTransport
      </saml:AuthnContextClassRef>
    </saml:AuthnContext>
  </saml:AuthnStatement>
</saml:Assertion>
~~~

### 3.1. Conditions.NotBefore và Conditions.NotOnOrAfter

- **NotBefore** (nếu được khai báo): thời điểm sớm nhất để assertion được xem là hợp lệ theo Conditions.
- **NotOnOrAfter** (nếu được khai báo): **tại đúng mốc này assertion đã không còn hợp lệ**; “on or after” nghĩa là không tính thời điểm bằng mốc.
- Conditions còn có **AudienceRestriction** và những điều kiện khác. Một assertion vẫn phải bị từ chối nếu sai Audience/Issuer/chữ ký, dù thời gian hợp lệ.

Trong ví dụ:

~~~text
08:00:00Z                  Conditions bắt đầu có hiệu lực
08:04:59Z                  Chưa quá NotOnOrAfter
08:05:00Z                  Đã ở mốc NotOnOrAfter -> không hợp lệ
08:05:01Z                  Không hợp lệ
~~~

Bộ xác minh thật có thể có **clock skew tolerance** giới hạn để chịu sai lệch đồng hồ giữa IdP và SP; không tự thêm “gia hạn 30 phút” vào assertion hoặc bỏ NotOnOrAfter vì browser chậm. Policy test phải tính đúng clock skew đã cấu hình và nhất quán với tiêu chuẩn SAML.

### 3.2. SubjectConfirmationData.NotOnOrAfter

Với bearer confirmation dùng trong **SAML Web Browser SSO Profile**, **SubjectConfirmationData** mang các ràng buộc riêng như:

- **Recipient:** ACS của SP phải nhận assertion.
- **InResponseTo:** liên hệ với AuthnRequest được SP lưu ở SP-initiated login.
- **NotOnOrAfter:** hạn chấp nhận bearer assertion cho việc xác nhận chủ thể.

SP phải kiểm tra **cả Conditions** và **bearer SubjectConfirmationData** theo profile, không chỉ chọn một giá trị NotOnOrAfter trông dài hơn. Với ví dụ chúng cùng kết thúc 08:05; nếu bearer NotOnOrAfter là **08:04** còn Conditions là **08:05**, giới hạn chấp nhận thực tế bị siết bởi **08:04**.

**Hết hạn bearer confirmation không được diễn giải là tự hủy HttpSession SP đã được tạo trước đó.** Nó ngăn **sử dụng lại assertion như chứng cứ ở bước xác thực**, kết hợp kiểm tra request correlation và replay.

### 3.3. AuthnInstant không phải Assertion IssueInstant

**AuthnInstant=07:45Z** có nghĩa IdP cho biết người dùng được xác thực lúc 07:45. **Assertion IssueInstant=08:01Z** là lúc assertion được phát hành. IdP có thể cấp một assertion mới từ **phiên IdP đã tồn tại**, nên AuthnInstant có thể cũ hơn IssueInstant.

Nếu nghiệp vụ yêu cầu “xác thực trong vòng 10 phút trước khi duyệt tiền”, chỉ nhìn Assertion IssueInstant mới không chứng minh user vừa xác thực lại. Cần chính sách **authentication freshness** dựa trên AuthnInstant/tín hiệu xác thực phù hợp, yêu cầu reauthentication có kiểm soát và kiểm tra IdP thực hiện đúng.

### 3.4. SessionNotOnOrAfter và SessionIndex

**AuthnStatement.SessionNotOnOrAfter** là ranh giới thời gian của **session được khai báo bởi authentication authority (IdP)**. Theo SAML Core, đây là giới hạn sau đó session giữa subject và authentication authority phải được coi là đã kết thúc. Trường này **có thể không có**.

**SessionIndex** là định danh phiên SAML phục vụ tương quan giữa IdP và SP, nhất là SAML Single Logout. Nó **không phải** JSESSIONID hay khóa session Redis của ứng dụng.

**Cẩn trọng:** SessionNotOnOrAfter được phát biểu trong assertion **không tự sửa maxInactiveInterval của HttpSession SP trong Spring Security 6**. Nếu chính sách SP yêu cầu phiên ứng dụng phải kết thúc ở mốc IdP công bố, phải lấy dữ liệu từ assertion đã được xác minh, lưu một giới hạn an toàn tại SP và chủ động thực thi. Không trích SessionNotOnOrAfter từ XML chưa verify.

## 4. Ba cookie/phiên trong browser: IdP và SP độc lập

Sau SSO, browser thường có:

~~~text
Browser
  |
  +-- IdP cookie (domain idp.example.org)
  |      -> IdP kiểm tra session SSO và thời gian đăng nhập
  |
  +-- SP cookie (domain portal.example.org)
  |      -> SP/Servlet/Spring Session tìm HttpSession
  |      -> SecurityContext chứa Authentication của user
  |
  +-- SAMLResponse (chỉ đi qua callback ACS khi login)
         -> Không gửi lại assertion ở mỗi HTTP request thông thường
~~~

**IdP cookie và SP cookie khác domain và khác chủ sở hữu.** SP không đọc được cookie session IdP thông thường, cũng không thể dựa vào cookie SP để biết IdP đã hết phiên hay chưa. Việc IdP báo “SSO session expired” chỉ xuất hiện khi browser/flow thực sự tương tác lại với IdP hoặc có một kênh thông báo/thu hồi đã thiết kế.

Điều thường xảy ra:

1. User vào SP lần đầu, chưa có SP session → Spring bắt đầu SAML login.
2. Nếu browser còn phiên IdP hợp lệ, IdP có thể phát SAMLResponse mới mà không yêu cầu user nhập mật khẩu lại.
3. SP xác minh assertion tại ACS và tạo **Saml2Authentication**, lưu vào SecurityContext/HttpSession.
4. Những request đến SP tiếp theo chủ yếu sử dụng session cookie SP, không gọi IdP.
5. IdP session có thể hết hạn giữa bước 3 và 4 mà SP không nhận được sự kiện nào.

**Không đồng nhất “browser đóng tab” với logout.** Session cookie có thể được browser khôi phục, backend session vẫn còn, và IdP có thể có chính sách remember-me riêng. Chỉ session invalidation/expiration thực tế mới đảm bảo SP không dùng lại session đó.

## 5. SP idle timeout: “30 phút không hoạt động” là gì?

Trong ứng dụng Servlet, **HttpSession.maxInactiveInterval** biểu diễn khoảng **không có request truy cập session** trước khi session bị coi là hết hạn. Cấu hình Spring Boot thường dùng:

~~~yaml
server:
  servlet:
    session:
      timeout: 30m
~~~

Đây là **idle timeout**, không phải giới hạn tuyệt đối kể từ lúc người dùng login.

Ví dụ:

~~~text
08:01  Login SAML -> SP session đang hoạt động
08:10  GET /me -> session được truy cập
08:30  GET /dashboard -> session lại được truy cập
08:55  GET /reports -> session vẫn còn nếu idle timeout = 30m
09:24  GET /orders -> session vẫn còn nếu idle timeout = 30m
...
~~~

Nếu các request hợp lệ tiếp tục đến trước hạn idle, phiên có thể tồn tại rất lâu, trừ khi có **absolute lifetime, account revocation, logout, hệ thống session store TTL** hoặc policy khác.

**Lưu ý:** Đây là cách mô tả logic hoạt động; thời điểm container cập nhật lastAccessedTime, cơ chế session invalidation và expiration của Redis/DB có thể khác đôi chút. AJAX/polling/background requests của tab mở cũng có thể làm session tiếp tục được truy cập, không nhất thiết biểu diễn thao tác của người dùng thật.

### Idle timeout không phải cookie Max-Age

Cookie session **không có Max-Age cố định** chỉ có nghĩa là browser xử lý theo session-cookie semantics. Nó không bảo đảm backend giữ session vĩnh viễn, cũng không chứng minh backend đã xóa session khi browser tắt. Ngược lại, cookie còn tồn tại không thể khôi phục HttpSession đã hết hạn.

**Đừng dùng cookie expiration làm nguồn duy nhất cho authorization.** Backend phải kiểm tra session tồn tại, SecurityContext còn hợp lệ, account/permission đã được duyệt và các giới hạn bổ sung của chính sách.

## 6. SP absolute lifetime: giới hạn dù user còn hoạt động

Nhiều ứng dụng tài chính, nhân sự hoặc quản trị cần giới hạn **thời gian tối đa sau xác thực**, ví dụ **8 giờ**, dù user click liên tục.

Chính sách minh họa:

~~~text
authenticatedAt = 08:01 UTC
idleTimeout = 30 phút
absoluteLifetime = 8 giờ

sessionActive(now) =
    now < authenticatedAt + 8 giờ
    AND now < lastActivityAt + 30 phút
    AND localAccountEnabled
    AND không bị revoked
~~~

**Absolute lifetime phải do ứng dụng triển khai** hoặc hệ thống quản lý phiên có khả năng hỗ trợ. Cấu hình **server.servlet.session.timeout** đơn thuần không tạo absolute lifetime. Có thể lưu một timestamp không thể bị client sửa **SP_AUTH_AT** trong server-side session, sau đó áp hạn ở filter/policy interceptor/authorization boundary.

Những điểm cần bảo vệ:

- Thời điểm authenticatedAt phải được ghi **sau SAML validation thành công**, không lấy từ HTTP request parameter.
- Không khởi động lại absolute lifetime chỉ vì user refresh trang; reset chỉ theo chính sách reauthentication mới đã được kiểm chứng.
- Sau khi hết absolute lifetime, **invalidate session** và xóa SecurityContext, không chỉ ẩn nút trên UI.
- Nếu nhiều node, lưu authenticatedAt trong shared session store phù hợp và dùng clock đồng bộ.
- Nếu có nhiều cơ chế đăng nhập, phân biệt thời điểm xác thực cho từng Authentication, không gán mọi anonymous session thành authenticated.
- Nếu có bước **MFA/step-up**, lưu thời điểm step-up riêng; không tự đồng nhất với thời điểm SP login đầu tiên.

### Không nên tự gán SessionNotOnOrAfter thành thời hạn SP

Một chính sách tổ chức có thể yêu cầu phiên SP không vượt thời hạn IdP công bố. Trong trường hợp đó, **mốc kết thúc phiên SP thực thi** là mốc sớm nhất của:

~~~text
spAbsoluteDeadline =
    min(
      spAuthenticatedAt + spAbsoluteLifetime,
      idpSessionNotOnOrAfter (nếu được xác minh và policy yêu cầu),
      userRevocationDeadline (nếu có)
    )
~~~

Ngoài ra vẫn có **idle timeout** độc lập. Đây là **quy tắc ứng dụng tùy chỉnh**, không phải hành vi mặc định mà SAML/Spring Boot tự suy ra. Khi IdP không cung cấp SessionNotOnOrAfter, cần một local absolute cap thay vì tự coi session IdP không bao giờ hết.

## 7. Khi IdP session hết hạn trong lúc SP session còn sống

Tình huống:

~~~text
08:00  User login ở IdP
08:01  IdP phát assertion (hợp lệ đến 08:05)
08:01  SP xác minh thành công và tạo phiên idle timeout 30m
08:30  Phiên IdP được coi là kết thúc theo policy/khai báo
08:31  User còn tương tác SP, phiên SP vẫn có thể hợp lệ
08:40  SP hết idle timeout nếu request cuối là 08:10
~~~

Tại **08:31**, nếu browser chỉ gọi tài nguyên SP và session SP còn active, Spring Security thường đọc **SecurityContext đã lưu trong HttpSession**. Nó **không tự gọi lại IdP mỗi request** để xem cookie IdP còn hiệu lực hay không.

Nếu SP session hết ở 08:40 và browser vào lại lúc 08:41:

- SP sẽ khởi động một SAML login mới.
- Nếu IdP session còn hợp lệ, IdP có thể SSO im lặng và trả assertion mới.
- Nếu IdP session đã hết, IdP có thể yêu cầu đăng nhập lại hoặc bước xác thực theo IdP policy.
- Dù IdP yêu cầu nhập lại mật khẩu hay không, SP vẫn phải **kiểm chứng một SAMLResponse mới** đúng quy tắc trước khi cấp phiên mới.

**IdP disable user** cũng không bắt buộc xóa tất cả SP sessions ngay lập tức. Nếu chính sách yêu cầu thu hồi gần thời gian thực, SP cần revalidation, local account status check, SLO/session revocation hoặc cơ chế sự kiện được thiết kế và kiểm thử. Không dựa hoàn toàn vào thời hạn assertion đã qua để hủy phiên.

## 8. Kịch bản ngược: SP timeout trước IdP

Ví dụ IdP SSO session còn đến 18:00 nhưng SP idle timeout chỉ 15 phút.

~~~text
09:00  Login IdP, SP tạo session
09:10  User ngừng dùng ứng dụng
09:25  SP session hết idle timeout
09:26  User mở /me, SP không còn SecurityContext
09:26  Browser được redirect sang IdP
09:26  IdP còn session SSO -> phát SAMLResponse mới
09:26  SP xác minh và tạo session mới
~~~

Người dùng có thể thấy một **vòng chuyển hướng nhanh**, tưởng “SP không logout” dù thực tế phiên SP cũ đã hết và một **giao dịch SAML login mới** vừa thành công. Muốn bắt người dùng nhập lại yếu tố xác thực, chỉ giảm idle timeout SP **chưa đủ**; phải yêu cầu **reauthentication** từ IdP theo policy.

SAML **AuthnRequest ForceAuthn=true** có thể yêu cầu IdP xác thực mới thay vì dùng ngầm phiên hiện có, với điều kiện IdP/profile hỗ trợ và thực thi. **ForceAuthn không đồng nghĩa chắc chắn có MFA hoặc chắc chắn yêu cầu mật khẩu**; mức xác thực cụ thể phụ thuộc AuthnContextRequested, IdP policy và giao thức liên kết. Nếu ứng dụng nhạy cảm cần fresh MFA, phải quy định assurance level và kiểm chứng AuthnInstant/AuthnContext sau callback.

## 9. Khi Assertion đã hết hạn nhưng phiên SP vẫn hoạt động

Đây là câu hỏi kiểm tra hiểu biết quan trọng nhất.

**Giả định** assertion có **Conditions.NotOnOrAfter=08:05**; SP nhận và xác minh hợp lệ lúc **08:01**, rồi lưu SecurityContext. Đến **08:20** browser truy cập /reports bằng cookie phiên SP còn hiệu lực.

**Điều đúng:** SP có thể cho phép request 08:20 theo **SecurityContext/session + authorization policy** mà không cần đòi assertion “08:05” còn sống. Assertion đã được sử dụng làm **chứng cứ xác thực ở một thời điểm**, không phải bearer access token phải gửi lại và validate mỗi request.

**Điều sai:** Cố lưu raw SAMLResponse làm credential rồi ở 08:20 replay nó để “refresh login” hoặc cấp OAuth token mới mà bỏ qua NotOnOrAfter/replay protection. Khi cần xác thực mới, phải thực hiện **giao dịch SAML mới** với Response mới hợp lệ, hoặc cơ chế refresh/re-auth được thiết kế rõ.

Trong tích hợp **OAuth2/OIDC**, access token và ID token lại có những mục đích, audience và expiration khác. Không bê logic “JWT access token exp” áp nguyên xi cho SAML Assertion tại ACS hoặc ngược lại.

## 10. Spring Security quản lý SecurityContext và HttpSession như thế nào?

Luồng điển hình:

~~~text
GET /private
  -> SecurityFilterChain
  -> chưa có Authentication trong SecurityContext
  -> AuthenticationEntryPoint khởi động SAML2 Login
  -> SP lưu AuthnRequest theo HttpSession
  -> browser đi IdP
  -> POST SAMLResponse tới ACS
  -> Saml2WebSsoAuthenticationFilter + AuthenticationManager
  -> verify signature/issuer/audience/recipient/time/correlation
  -> Saml2Authentication đã được xác thực
  -> SessionAuthenticationStrategy (session fixation protection)
  -> SecurityContextHolder
  -> SecurityContextRepository lưu context vào HttpSession
  -> các HTTP request sau khôi phục context từ HttpSession
~~~

**Quan trọng:** HttpSession **có thể được tạo trước khi user đăng nhập** để lưu AuthnRequest/SavedRequest. Một session tồn tại không có nghĩa user đã authenticated. Khi SAML login thành công, Spring Security thường **đổi session ID** để chống session fixation theo chiến lược mặc định trên Servlet 3.1+.

Spring Security 6 dùng **SecurityContextHolderFilter** và cơ chế explicit save theo mặc định; **saml2Login() chuẩn** tự xử lý persistence khi xác thực thành công. Custom code sửa Authentication phải gọi **SecurityContextRepository.saveContext(...)** nếu muốn trạng thái tồn tại qua request, nhưng **đừng tự viết filter xác minh SAMLResponse** chỉ để lưu phiên.

### SessionCreationPolicy nên chọn gì?

| Policy | Ý nghĩa ngắn | Đối với SAML2 browser |
| --- | --- | --- |
| **IF_REQUIRED** | Spring tạo session khi cần | Phù hợp cách triển khai session-based browser SSO |
| **ALWAYS** | Tạo session mỗi khi vào chain | Thường không cần; tăng tài nguyên |
| **NEVER** | Spring không chủ động tạo session nhưng có thể dùng session đang tồn tại | Có thể ảnh hưởng request correlation/đăng nhập, cần thử rất kỹ |
| **STATELESS** | Không dùng HttpSession cho SecurityContext | Không phù hợp mặc định với SAML2 browser SSO cần request correlation/session persistence |

**Không đặt STATELESS cho web SAML2 chain** chỉ vì muốn tối ưu RAM, trong khi AuthenticationRequestRepository vẫn dùng HttpSession. Với API Bearer JWT có thể tạo **SecurityFilterChain riêng** stateless; đừng áp nó lên ACS/browser login.

## 11. Ví dụ Spring Boot 3 + Java 17: SP session 30 phút độc lập IdP/Assertion

Ví dụ thực hành dưới đây cho **Spring MVC Servlet + SAML2 login**. Để hoàn tất đăng nhập thật cần **IdP có metadata XML hợp lệ**, SP entityID/ACS được đăng ký ở IdP, các signing/decryption credentials theo chính sách và HTTPS public domain. Tên miền **example.org** chỉ là ví dụ, không phải IdP đang hoạt động.

### 11.1. Dependencies

Trong phần dependencies của **pom.xml** dự án Maven có Spring Boot parent/BOM tương thích:

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

Nếu metadata IdP được lưu trong classpath, cần tệp **src/main/resources/metadata/company-idp.xml** đã được kiểm duyệt; không tự dùng một XML ví dụ không có chữ ký/chứng thư làm IdP thật. Dùng phiên bản dependency theo BOM của Boot, tránh trộn OpenSAML không tương thích.

### 11.2. application.yml

**src/main/resources/application.yml**

~~~yaml
app:
  saml:
    idp-metadata-location: classpath:metadata/company-idp.xml

server:
  servlet:
    session:
      timeout: 30m
~~~

**timeout: 30m** là SP HttpSession **idle timeout**. Nó **không** đặt assertion NotOnOrAfter, không thay đổi thời hạn cookie SSO tại IdP và không tự tạo absolute SP session lifetime.

Ví dụ production qua HTTPS thường cần cookie Secure/HttpOnly. Với IdP sử dụng **cross-site HTTP-POST binding** tới ACS, chính sách **SameSite** cũng phải được thử trong browser; **SameSite=Lax/Strict có thể chặn cookie phiên ở POST cross-site**. Nếu cần dùng **SameSite=None; Secure** trên HTTPS, vẫn phải bật CSRF protection cho thao tác ứng dụng (xem mục 15). Không tùy tiện bật Secure cookie khi đang debug thuần HTTP localhost.

### 11.3. Main class

**src/main/java/com/example/session/SessionLifecycleApplication.java**

~~~java
package com.example.session;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SessionLifecycleApplication {
    public static void main(String[] args) {
        SpringApplication.run(SessionLifecycleApplication.class, args);
    }
}
~~~

### 11.4. Spring Security configuration

**src/main/java/com/example/session/SamlSecurityConfig.java**

~~~java
package com.example.session;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.saml2.provider.service.registration.InMemoryRelyingPartyRegistrationRepository;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistration;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistrationRepository;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistrations;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SamlSecurityConfig {

    @Bean
    RelyingPartyRegistrationRepository relyingParties(
            @Value("${app.saml.idp-metadata-location}") String location) {

        RelyingPartyRegistration company =
            RelyingPartyRegistrations
                .fromMetadataLocation(location)
                .registrationId("company")
                .entityId("https://portal.example.org/saml/sp/company")
                .assertionConsumerServiceLocation(
                    "https://portal.example.org/login/saml2/sso/company")
                .build();

        return new InMemoryRelyingPartyRegistrationRepository(company);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated())
            .saml2Login(Customizer.withDefaults())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.IF_REQUIRED)
                .sessionFixation(fixation -> fixation.changeSessionId()))
            .logout(logout -> logout.logoutSuccessUrl("/"));

        return http.build();
    }
}
~~~

**Giải thích chính:**

- **RelyingPartyRegistrations.fromMetadataLocation(...)** lấy cấu hình IdP được tin cậy; **registrationId=company** là khóa quan hệ SP–IdP.
- **SP entityID/ACS** phải khớp đăng ký ở IdP. Nếu đang chạy localhost, ID/ACS example.org không thể tự callback về localhost.
- **saml2Login()** bật quy trình SAML Web Browser SSO và các checks của provider.
- **SessionCreationPolicy.IF_REQUIRED** cho phép Spring tạo HttpSession khi browser SAML flow cần.
- **sessionFixation().changeSessionId()** giúp đổi session ID khi xác thực thành công, tránh fixation.
- **logoutSuccessUrl("/")** định tuyến sau **local logout**, không đồng nghĩa đã bật **SAML Single Logout** tại IdP.
- **Không tắt CSRF toàn ứng dụng** để “sửa” callback, cũng không tự parse SAMLResponse tại controller.

### 11.5. Controller quan sát SP session, không đọc IdP cookie

**src/main/java/com/example/session/SessionController.java**

~~~java
package com.example.session;

import java.util.Map;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpSession;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.saml2.provider.service.authentication.Saml2AuthenticatedPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class SessionController {

    @GetMapping("/")
    public String home() {
        return "SAML session lifetime demo";
    }

    @GetMapping("/me")
    public Map<String, String> currentSession(
            Authentication authentication,
            @AuthenticationPrincipal Saml2AuthenticatedPrincipal principal,
            HttpServletRequest request) {

        HttpSession session = request.getSession(false);

        return Map.of(
            "authenticated", String.valueOf(authentication.isAuthenticated()),
            "registrationId", principal.getRelyingPartyRegistrationId(),
            "spSessionPresent", String.valueOf(session != null),
            "spIdleTimeoutSeconds", String.valueOf(
                session == null ? -1 : session.getMaxInactiveInterval())
        );
    }
}
~~~

**Tại sao dùng getSession(false)?** Hàm này chỉ đọc session hiện tại nếu có, **không tạo một session mới** trong phép quan sát. Còn **getMaxInactiveInterval()** trả idle interval cấu hình theo **giây**, không phải số giây còn lại của phiên; không tính TTL chính xác từ thuộc tính này.

Controller giả định **/me chỉ được vào bằng SAML2 Authentication** của ví dụ. Nếu có nhiều cơ chế login, cần kiểm tra null/type principal. Trong production không đưa session ID, raw SAMLResponse, cookie hoặc attributes nhận dạng nhạy cảm vào response/log; các giá trị hiển thị ở đây chỉ là thông số kỹ thuật.

### 11.6. Chạy và quan sát

Trong dự án Maven có JDK 17+ và metadata thật:

~~~bash
mvn spring-boot:run
~~~

Endpoint public sau khi app khởi động thành công:

~~~bash
curl -i http://localhost:8080/
~~~

Response body đúng theo controller:

~~~text
SAML session lifetime demo
~~~

Để kiểm chứng session thật:

1. Mở trang **/me** bằng public SP URL đã đăng ký với IdP.
2. Browser được chuyển tới IdP, xác thực và POST SAMLResponse hợp lệ về ACS.
3. SP tạo Authentication/HttpSession; **/me** có thể trả **authenticated=true, spSessionPresent=true, spIdleTimeoutSeconds=1800** theo cấu hình.
4. Reload /me trước khi idle timeout: SP khôi phục SecurityContext từ session cookie, không cần SAMLResponse mới.
5. Dừng truy cập đủ lâu cho session expire, rồi gọi /me: SP cần một vòng xác thực mới; IdP có thể SSO nhanh nếu session IdP còn.
6. Kiểm tra việc logout local, xóa cookie SP, hết IdP session và callback SAML mới như các tình huống riêng biệt.

Không có stdout JSON chính xác cho user/IdP, vì nó phụ thuộc môi trường và session thật. **1800** là số giây tương đương 30 phút theo cấu hình minh họa; container có thể ghi đè timeout bằng cấu hình khác nên phải kiểm tra runtime.

## 12. Java 17 runnable: ba đồng hồ không ràng buộc tự động

Chương trình Java 17 sau **chạy độc lập**, không cần Spring Boot/IdP/DB. Nó mô phỏng **thời hạn assertion**, **mốc IdP session** được cung cấp và **SP idle/absolute lifetime** dưới một tập thời điểm UTC cố định. Đây là bài tập logic chứ **không phải SAML signature validator** hoặc giải pháp session production.

**Tệp: SessionClockDemo.java**

~~~java
import java.time.Duration;
import java.time.Instant;

public final class SessionClockDemo {

    enum LocalStatus {
        ACTIVE,
        IDLE_EXPIRED,
        ABSOLUTE_EXPIRED
    }

    record LocalSession(
            Instant authenticatedAt,
            Instant lastSeenAt,
            Duration idleTimeout,
            Duration absoluteLifetime) {

        LocalStatus statusAt(Instant now) {
            if (!now.isBefore(authenticatedAt.plus(absoluteLifetime))) {
                return LocalStatus.ABSOLUTE_EXPIRED;
            }
            if (!now.isBefore(lastSeenAt.plus(idleTimeout))) {
                return LocalStatus.IDLE_EXPIRED;
            }
            return LocalStatus.ACTIVE;
        }
    }

    static boolean assertionValidAt(
            Instant now, Instant notBefore, Instant notOnOrAfter) {

        return !now.isBefore(notBefore)
            && now.isBefore(notOnOrAfter);
    }

    static boolean idpSessionValidAt(
            Instant now, Instant sessionNotOnOrAfter) {
        return now.isBefore(sessionNotOnOrAfter);
    }

    public static void main(String[] args) {
        Instant before = Instant.parse("2026-11-07T08:00:00Z");
        Instant assertionEnd = Instant.parse("2026-11-07T08:05:00Z");
        Instant idpEnd = Instant.parse("2026-11-07T08:30:00Z");

        LocalSession sp = new LocalSession(
            Instant.parse("2026-11-07T08:01:00Z"),
            Instant.parse("2026-11-07T08:10:00Z"),
            Duration.ofMinutes(30),
            Duration.ofMinutes(90));

        System.out.println("assertionAt0804=" + assertionValidAt(
            Instant.parse("2026-11-07T08:04:00Z"),
            before, assertionEnd));
        System.out.println("assertionAt0805=" + assertionValidAt(
            assertionEnd, before, assertionEnd));
        System.out.println("spAt0820=" + sp.statusAt(
            Instant.parse("2026-11-07T08:20:00Z")));
        System.out.println("idpAt0831=" + idpSessionValidAt(
            Instant.parse("2026-11-07T08:31:00Z"), idpEnd));
        System.out.println("spAt0831=" + sp.statusAt(
            Instant.parse("2026-11-07T08:31:00Z")));
        System.out.println("spAt0840=" + sp.statusAt(
            Instant.parse("2026-11-07T08:40:00Z")));

        LocalSession busySp = new LocalSession(
            Instant.parse("2026-11-07T08:01:00Z"),
            Instant.parse("2026-11-07T09:20:00Z"),
            Duration.ofMinutes(30),
            Duration.ofMinutes(90));

        System.out.println("spAt0931=" + busySp.statusAt(
            Instant.parse("2026-11-07T09:31:00Z")));
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac SessionClockDemo.java
java SessionClockDemo
~~~

**Stdout chính xác với Java 17+:**

~~~text
assertionAt0804=true
assertionAt0805=false
spAt0820=ACTIVE
idpAt0831=false
spAt0831=ACTIVE
spAt0840=IDLE_EXPIRED
spAt0931=ABSOLUTE_EXPIRED
~~~

Giải thích:

- 08:04 assertion còn trong thời hạn; **08:05 bằng NotOnOrAfter** nên false.
- SP session được login lúc 08:01, truy cập cuối 08:10; tại 08:20 và **08:31** SP vẫn active theo idle 30 phút và absolute 90 phút.
- IdP session theo mốc minh họa **08:30** đã hết tại 08:31, nhưng **không tự làm SP session hết**.
- **08:40** đã đủ 30 phút từ lần truy cập cuối 08:10 → SP idle expired.
- Với một phiên khác vẫn có hoạt động đến 09:20, tại **09:31** đã đạt **90 phút kể từ login 08:01**, nên absolute expired, dù idle mới 11 phút.

**Ranh giới kỹ thuật:** Chương trình giả định instant của các trạng thái đã được một nguồn tin cậy cung cấp; nó không lấy IdP cookie thật và không parse SAML Response. Hãy dùng **Clock** được inject hoặc UTC time từ server đồng bộ trong production; không dùng timestamp tự truyền từ browser để kéo dài phiên. Khi IdP không gửi SessionNotOnOrAfter, phải sử dụng policy riêng thay vì giả định có một mốc tùy ý.

## 13. Thực thi absolute timeout trong ứng dụng thực

Spring Boot **không tự áp một absolute timeout của authenticated session chỉ bằng cấu hình idle timeout**. Để thực thi giới hạn 8 giờ, ứng dụng có thể:

1. Khi **SAML login thành công**, ghi một **authenticatedAt** từ đồng hồ server vào session, **sau** SAML validation và sau khi áp SessionAuthenticationStrategy. Không lấy từ query/header.
2. Trên mỗi request bảo vệ, dùng filter/authorization service đọc session đã tồn tại mà **không tự tạo session mới**, kiểm tra deadline.
3. Nếu đã đạt hạn, invalidate HttpSession, xóa SecurityContext theo cơ chế logout/repository của Spring và yêu cầu một chu kỳ xác thực mới.
4. Nếu cần giữ request gốc, sử dụng SavedRequest/request cache phù hợp, không redirect tới địa chỉ client tùy ý.
5. Chia sẻ authenticatedAt qua Spring Session/Redis khi nhiều node và kiểm soát phiên đồng thời.
6. Không reset authenticatedAt mỗi lần GET hoặc cứ mỗi lần IdP gửi assertion mới nếu chính sách bắt buộc liên tục/absolute bound từ lần đăng nhập ban đầu.
7. Kiểm thử sau logout, expired session, nhiều tab, browser restore, user bị khóa, chuyển node và step-up.

Ví dụ **mảnh logic chính sách** (không phải filter độc lập):

~~~java
Instant now = clock.instant();
Instant authenticatedAt =
    (Instant) session.getAttribute("SP_AUTHENTICATED_AT");

if (authenticatedAt == null
        || !now.isBefore(authenticatedAt.plus(Duration.ofHours(8)))) {
    // Trong flow production: dùng logout/session-invalidation
    // được Spring Security cấu hình để dọn context/session.
    session.invalidate();
    SecurityContextHolder.clearContext();
    response.sendRedirect(request.getContextPath() + "/reauth");
    return;
}
~~~

Đoạn này chỉ để **giải thích điểm đặt kiểm tra**: session, clock, response và security context đã được truyền vào một flow phù hợp; URL **/reauth** phải được cấu hình an toàn và tránh redirect loop. Trong ứng dụng thật, ưu tiên dùng **LogoutHandler/SecurityContextRepository** được Spring cấu hình để xóa trạng thái đầy đủ, không chỉ hai câu lệnh ở fragment.

**Phòng thủ sâu:** với thao tác rất nhạy cảm, quyết định authorization cũng nên kiểm tra **account enabled/permission** tại thời điểm thao tác. Kết thúc session vì thời gian là một điều kiện; việc cấp quyền không nên chỉ dựa trên “session chưa quá hạn”.

## 14. Kiểm soát phiên ở nhiều instance

Nếu ứng dụng có nhiều pod/node sau load balancer, mỗi node giữ session riêng có thể gây:

- AuthnRequest lưu ở node A nhưng SAMLResponse POST tới node B → mất request correlation.
- Login thành công ở node A, request tiếp theo tới B → mất SecurityContext.
- Absolute authenticatedAt chỉ lưu trong một node → mỗi node tính khác nhau.
- Session bị revoke tại A nhưng còn active tại B → không đáp ứng policy bảo mật.

**Spring Session** với Redis/DB là một phương án chia sẻ HttpSession qua nhiều instance, dùng session cookie logic và repository của Spring Security:

~~~xml
<dependency>
  <groupId>org.springframework.boot</groupId>
  <artifactId>spring-boot-starter-session-data-redis</artifactId>
</dependency>
~~~

Metadata/RelyingPartyRegistration phải thống nhất trên các node, Redis được bảo vệ bằng TLS/ACL, dữ liệu session có TTL/serializer phù hợp, đồng hồ đồng bộ, session invalidation được phát tán đúng. Sticky session có thể làm giảm chuyển node nhưng không thay thế tốt việc quản lý failover/revoke cần nhất quán.

**Không coi TTL Redis là session policy tuyệt đối** nếu adapter liên tục gia hạn TTL khi session được truy cập; cần một timestamp absolute riêng nếu nghiệp vụ yêu cầu. Không đưa session ID hoặc SAMLResponse vào log/URL.

## 15. Cookie và CSRF khi browser trở lại từ IdP

SAML Web Browser SSO thường dùng **HTTP-POST binding**: IdP trang khác domain POST SAMLResponse về **ACS** của SP. Khi AuthnRequest đã được lưu trong HttpSession, SP cần browser gửi đúng session cookie trên callback để đối chiếu **InResponseTo/RelayState**.

- **Secure**: cookie chỉ gửi qua HTTPS.
- **HttpOnly**: JavaScript không đọc được cookie.
- **SameSite**: **Lax/Strict có thể chặn cookie trong cross-site POST**. Nếu cần, với HTTPS production có thể dùng **SameSite=None; Secure**.
- **Domain/Path**: phải phù hợp public hostname/callback của SP; reverse proxy không được tạo cookie domain sai.
- **CSRF protection**: vẫn bắt buộc với POST/PUT/DELETE nghiệp vụ sử dụng session cookie; **không tắt CSRF toàn web** chỉ để sửa callback SAML.

Ví dụ cookie policy **chỉ cho môi trường production HTTPS đã kiểm thử cross-site POST**:

~~~yaml
server:
  servlet:
    session:
      cookie:
        http-only: true
        secure: true
        same-site: none
      timeout: 30m
~~~

Tùy Servlet container/Spring Session, tên cookie có thể là **JSESSIONID** hoặc **SESSION**. Browser có thể giữ cookie nhưng backend session đã hết; lúc đó request cần login lại, không thể “khôi phục” chỉ bằng cách giữ cookie cũ.

Nếu cookie bị thiếu ở ACS POST, đừng “chữa” bằng cách bỏ InResponseTo, Audience hoặc signature validation. Đó là mở rộng trust boundary để che một lỗi session/binding.

## 16. Logout local, SAML Single Logout và hết hạn IdP

**Local logout tại SP** (thường POST **/logout** có CSRF token hợp lệ) xóa SecurityContext và invalidates HttpSession cục bộ. Nó **không mặc nhiên** đăng xuất IdP hoặc các SP khác.

**SAML Single Logout** là flow riêng, cần bật **saml2Logout()**, endpoint SingleLogoutService và signing/verification credentials tương ứng khi IdP hỗ trợ. SP hoặc IdP có thể khởi tạo LogoutRequest; bên nhận trả LogoutResponse. Chỉ khi các bên phối hợp và browser/network không gián đoạn mới có thể kỳ vọng nhiều phiên kết thúc theo chính sách.

| Sự kiện | SP session | IdP session | SP khác |
| --- | --- | --- | --- |
| SP idle timeout | Hết | Có thể còn | Không tự bị ảnh hưởng |
| SP absolute timeout | Hết nếu đã triển khai | Có thể còn | Không tự bị ảnh hưởng |
| SAML assertion NotOnOrAfter đã qua sau khi login | Có thể còn | Không suy ra trạng thái | Không suy ra |
| User logout local tại SP | Bị xóa | Có thể còn | Có thể còn |
| User logout tại IdP, không có SLO tới SP | Có thể còn | Hết | Có thể còn |
| SLO hoàn tất thành công theo các bên | Phiên liên quan bị kết thúc | Theo kết quả của IdP | Theo những SP thực sự tham gia/xử lý thành công |

**Không dùng việc browser được chuyển hướng về /login?logout làm chứng cứ tất cả IdP/SP đã chấm dứt phiên.** Khi có PartialLogout hoặc browser đóng tab giữa cascade, kết quả có thể không toàn cục. Cần UX rõ ràng và session timeout/response handling làm phương án phòng thủ bổ sung.

## 17. Thời hạn xác thực cho thao tác nhạy cảm

Một chính sách phổ biến:

- **Xem dashboard:** SP session còn hợp lệ và có role.
- **Xem dữ liệu bảo mật:** SP session còn hợp lệ, account chưa revoked và DB permission còn hiệu lực.
- **Duyệt chuyển tiền:** SP session còn hợp lệ, **AuthnInstant gần đây** hoặc có bước xác thực mạnh/step-up, đáp ứng assurance level và phê duyệt nghiệp vụ.
- **Đổi mật khẩu/khóa API:** yêu cầu fresh authentication theo policy riêng, không dựa độc nhất vào session SP đã tồn tại lâu.

Phân biệt:

1. **Assertion IssueInstant:** lúc IdP phát assertion; có thể mới dù user đăng nhập IdP đã lâu.
2. **AuthnInstant:** IdP khẳng định lúc người dùng được xác thực; phù hợp hơn với kiểm tra freshness, nhưng phải được xác minh và diễn giải đúng context/issuer.
3. **ForceAuthn trong AuthnRequest:** tín hiệu yêu cầu xác thực mới tại IdP, không phải bằng chứng tự thân rằng MFA đã xảy ra.
4. **AuthnContextClassRef:** mô tả ngữ cảnh/mức xác thực theo IdP; phải có contract, không tự diễn giải “PasswordProtectedTransport” thành MFA.
5. **Local step-up timestamp:** chỉ đáng tin nếu ứng dụng lưu sau một bước xác thực mạnh được xác minh, không từ client tự khai.

Nếu policy yêu cầu IdP session được cắt ngắn để khớp SP, phải làm việc với IdP và thiết kế re-authentication/SLO. **Đừng đặt idle timeout SP = assertion lifetime** chỉ vì cả hai đều là thời gian.

## 18. Bảng tình huống kết luận đúng

| Tình huống | SP nên làm gì? |
| --- | --- |
| SAMLResponse đến ACS lúc **08:04**, NotOnOrAfter=08:05, mọi check khác hợp lệ | Có thể tạo session SP mới |
| SAMLResponse đến lúc **08:05** chính xác, bỏ qua clock skew minh họa | Từ chối assertion, không tạo Authentication từ response đó |
| User có session SP valid lúc **08:20**, assertion ban đầu hết 08:05 | Có thể tiếp tục sau khi kiểm tra session/authorization SP |
| IdP cookie hết lúc **08:30**, session SP vẫn valid | Không tự xóa SP session nếu không có policy/revoke/SLO |
| SP session hết lúc **08:40**, IdP session còn | Bắt đầu SAML login mới; IdP có thể SSO không cần mật khẩu |
| SP session hết và IdP session cũng hết | Bắt đầu SAML login mới, IdP có thể yêu cầu xác thực lại |
| Browser mất cookie SP nhưng IdP session còn | Tạo vòng login SAML mới, không khôi phục SP SecurityContext từ cookie không tồn tại |
| AuthnStatement SessionNotOnOrAfter=08:30 nhưng SP timeout được cấu hình 2 giờ | Không giả định Spring tự giới hạn SP 08:30; nếu policy yêu cầu, phải thực thi deadline đó |
| DB/IdP khóa user sau khi SP login | SP có thể không tự biết; cần revoke/revalidation/session policy |
| Đến absolute deadline dù người dùng vẫn click liên tục | Dừng phiên SP nếu absolute policy được triển khai |
| Người dùng logout local nhưng IdP session còn | Có thể SSO login trở lại nhanh; muốn liên kết phải cấu hình SLO |
| AuthnInstant quá cũ cho giao dịch nhạy cảm, Assertion IssueInstant mới | Yêu cầu fresh auth/step-up phù hợp; không đánh đồng IssueInstant với AuthnInstant |

## 19. Kiểm thử và chẩn đoán lỗi

### 19.1. Bộ test tối thiểu

1. **Assertion hết hạn ở ACS:** dùng SAML test IdP phát assertion đã quá NotOnOrAfter với signature hợp lệ; xác nhận fail, không chỉ sửa XML đã ký khiến signature fail trước.
2. **NotBefore tương lai:** bị từ chối trước thời điểm được phép, với clock skew đã cấu hình.
3. **Bearer SubjectConfirmationData hết trước Conditions:** từ chối tại hạn chặt hơn.
4. **Assertion hợp lệ để login nhưng sau đó hết:** session SP vẫn hoạt động theo policy độc lập.
5. **SP idle timeout:** ngừng request đủ thời gian, session hết.
6. **SP absolute timeout:** liên tục gửi request; đến absolute deadline vẫn hết.
7. **IdP session hết trước SP:** request SP vẫn theo phiên local, không tự redirect nếu không có trigger reauth.
8. **SP session hết trước IdP:** browser trải qua SAML login mới có thể không cần nhập mật khẩu.
9. **ForceAuthn/freshness:** kiểm tra AuthnInstant/AuthnContext của assertion mới, không chỉ redirect.
10. **User revoked tại IdP:** xác minh SLA phát hiện/thu hồi local session theo chính sách, không assume auto.
11. **Local logout:** session SP bị invalidate, nhưng IdP có thể còn.
12. **SLO:** kiểm tra khả năng IdP/SP thông báo và xử lý SessionIndex/LogoutRequest/Response.
13. **SameSite cookie:** ACS cross-site POST vẫn mang cookie cần để tìm AuthnRequest.
14. **Hai node:** login node A, request node B, session/deadline vẫn nhất quán.
15. **Đồng hồ lệch:** thử clock skew với biên NotBefore/NotOnOrAfter, không gia hạn vô hạn.
16. **Browser restore:** cookie cũ không phục hồi được một backend session đã expired.
17. **Nhiều tab:** một tab gửi keep-alive có thể gia hạn idle; absolute vẫn có giới hạn.
18. **Phân quyền sau login:** phiên hợp lệ nhưng role/DB grant bị thu hồi phải bị xử lý theo authorization policy.

### 19.2. Lỗi thường gặp

| Dấu hiệu | Nguyên nhân thường gặp | Hướng kiểm tra |
| --- | --- | --- |
| Login fail “assertion expired” | IdP/SP lệch giờ, network delay, NotOnOrAfter quá ngắn | NTP, UTC timestamps, đúng clock skew policy và test ACS |
| SP logout sớm hơn IdP | Idle/absolute timeout SP ngắn hơn IdP session | Xác minh chính sách từng bên, không gọi đó là IdP lỗi |
| SP vẫn active khi IdP hết phiên | SP HttpSession độc lập và chưa có SLO/revalidation | Thiết kế revocation/reauthentication nếu nghiệp vụ yêu cầu |
| User login lại ngay sau khi SP timeout | IdP session còn hiệu lực nên cấp assertion mới | Quan sát giao dịch SAML mới và AuthnInstant |
| Session tưởng không bao giờ hết | Heartbeat/AJAX liên tục làm mới idle | Kiểm tra network traffic, thêm absolute cap |
| SP session mất giữa SAML callback | SameSite, Secure, reverse proxy, multi-node | Cookie ACS POST, AuthnRequest repo và shared store |
| GET /me trả redirect liên tục | Cookie không được lưu/trả, session backend mất, ACS sai | Session cookie flags, backend session store, SAML validation |
| Cookie còn nhưng login mất | HttpSession expired hoặc bị revoke | Kiểm tra backend expiration, không chỉ DevTools cookie |
| IdP group bị gỡ nhưng SP role chưa đổi | Principal/SecurityContext là snapshot lúc login | Refresh/revoke authorities/session theo policy |
| Người dùng vừa logout nhưng bị login lại rất nhanh | Chỉ local logout, IdP session còn | Cấu hình SLO/re-auth theo nhu cầu |
| Test expiration thấy kết quả khác | Không tính timezone, skew, NotOnOrAfter exclusivity | Dùng Instant/UTC, Clock được kiểm soát và profile cụ thể |

Trong dev có thể bật DEBUG một cách tạm thời:

~~~yaml
logging:
  level:
    org.springframework.security: DEBUG
~~~

**Không ghi SAMLResponse, cookies, SessionIndex, JSESSIONID, private keys hay thông tin định danh không cần thiết** vào log, test report hoặc issue tracker. Dùng correlation ID và các mốc thời gian đã tối giản; đồng bộ thời gian máy chủ và có chỉ số giám sát session expiration/re-authentication failure.

## 20. Checklist production

- [ ] SAMLResponse được kiểm tra chữ ký, Issuer, AudienceRestriction, Recipient, InResponseTo và **các điều kiện thời gian** trước khi tạo Authentication.
- [ ] Phân biệt **Conditions.NotOnOrAfter** và **SubjectConfirmationData.NotOnOrAfter** với SP session lifetime.
- [ ] Không dùng **Assertion IssueInstant** thay **AuthnInstant** khi kiểm tra freshness.
- [ ] Hiểu **SessionNotOnOrAfter** là dữ liệu phiên từ IdP, không tự trở thành HttpSession timeout trong Spring.
- [ ] Có **SP idle timeout** phù hợp và bảo đảm browser/background requests không vô tình giữ phiên mãi.
- [ ] Nếu cần, có **SP absolute lifetime** thực thi phía server, không reset mỗi GET.
- [ ] Nếu policy ràng buộc phiên SP với IdP session deadline đã xác minh, đã triển khai giới hạn sớm nhất đúng cách.
- [ ] Có policy account disable/permission revoke khi SP session còn hoạt động.
- [ ] Browser SAML2 chain có **SecurityContextRepository/HttpSession** phù hợp; không vô tình bật STATELESS.
- [ ] Cookie dùng HTTPS Secure/HttpOnly và SameSite phù hợp POST callback; CSRF cho nghiệp vụ vẫn được bảo vệ.
- [ ] Khi nhiều node, session/reauth timestamp chia sẻ nhất quán và clock đồng bộ.
- [ ] Dùng local logout hoặc SAML Single Logout đúng nhu cầu; không báo tất cả IdP/SP đã logout nếu chỉ xóa SP session.
- [ ] Thiết kế fresh authentication/step-up cho thao tác nhạy cảm bằng AuthnInstant và assurance level đáng tin.
- [ ] Test biên NotBefore/NotOnOrAfter, idle, absolute, IdP expiry, ForceAuthn, session cookie và revocation.
- [ ] Không ghi raw SAML/XML, session IDs, SAML private keys và dữ liệu nhạy cảm vào log.
- [ ] Ghi tài liệu vận hành rõ **ai sở hữu mỗi “đồng hồ”**, phương án khi IdP outage và trạng thái UX khi cần login lại.

**Tóm tắt học tập:** **Assertion còn hạn** là điều kiện chấp nhận chứng cứ tại ACS; **SP session còn hạn** là điều kiện để các HTTP request sau được xem là đã đăng nhập; **IdP session còn hạn** ảnh hưởng việc IdP có thể cấp assertion mới mà không bắt user xác thực lại. Các đồng hồ này **độc lập theo mặc định**. Muốn chúng đồng bộ phải áp dụng chính sách xác minh, absolute session cap, reauthentication, revocation hoặc SAML Single Logout rõ ràng.

## 21. Tài liệu tham khảo

- [Spring Security – Authentication Persistence & Session Management](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html): SecurityContextRepository, SessionCreationPolicy, session timeout, session fixation, explicit save.
- [Spring Security – SAML2 Login Overview](https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html): SAMLResponse validation, Assertion Conditions và Authentication.
- [Spring Security – Authenticating SAML Responses](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html): response/assertion validator và Authentication conversion.
- [Spring Security – SAML2 Authentication Requests](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication-requests.html): AuthnRequest, SAML login flow, session correlation.
- [Spring Security – SAML2 Single Logout](https://docs.spring.io/spring-security/reference/servlet/saml2/logout.html): RP/AP-initiated logout và session state.
- [Spring Session – Boot/Redis](https://docs.spring.io/spring-session/reference/guides/boot-redis.html): lưu HttpSession chia sẻ giữa các instances.
- [OASIS – SAML 2.0 Core Specification](https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf): Conditions, SubjectConfirmationData, AuthnStatement, SessionNotOnOrAfter, AuthnInstant.
- [OASIS – SAML 2.0 Profiles Specification](https://docs.oasis-open.org/security/saml/v2.0/saml-profiles-2.0-os.pdf): Web Browser SSO Profile, bearer SubjectConfirmation rules.
- [OWASP – Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html): idle/absolute timeout, fixation, cookie và session lifecycle.
