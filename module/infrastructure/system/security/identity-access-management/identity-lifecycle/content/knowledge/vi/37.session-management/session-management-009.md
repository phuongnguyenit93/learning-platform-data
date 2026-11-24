# Session fixation trong IAM: cố định phiên đăng nhập và cách phòng ngừa

> **Chương:** Session management  
> **Bài:** Session fixation  
> **Module:** SECURITY_IDENTITY_ACCESS_MANAGEMENT_IDENTITY_LIFECYCLE  
> **Bối cảnh:** Quản lý vòng đời danh tính trong IAM theo mô hình **Joiner–Mover–Leaver**, liên kết xác minh danh tính, IdP, SSO, SCIM, RBAC/ABAC, tài khoản dịch vụ, kiểm toán và thu hồi quyền truy cập tồn dư.

## 1. Session fixation là gì?

Một người dùng mở ứng dụng quản trị và chưa đăng nhập. Server đã tạo một **anonymous session** để lưu giao diện, giỏ hàng hoặc bước khởi tạo đăng nhập. Một kẻ tấn công biết trước ID của phiên đó và tìm cách khiến trình duyệt nạn nhân sử dụng chính ID ấy. Sau khi nạn nhân đăng nhập, ứng dụng **không thay session ID**, mà chỉ thêm trạng thái authenticated vào phiên cũ. Kẻ tấn công tiếp tục gửi ID mà mình đã biết để được server nhận diện như phiên của nạn nhân.

Đó là **session fixation (tấn công cố định phiên)**: kẻ tấn công thiết lập, kiểm soát hoặc biết trước một định danh phiên trước khi nạn nhân xác thực; nếu ứng dụng giữ định danh đó sau khi xác thực, quyền của phiên đã xác thực có thể bị sử dụng thông qua ID đã biết.

Session fixation thường xuất hiện tại **ranh giới chuyển mức tin cậy**, đặc biệt từ anonymous sang authenticated. Vấn đề không nhất thiết là thuật toán sinh session ID yếu: ngay cả ID ngẫu nhiên mạnh cũng nguy hiểm nếu kẻ tấn công đã biết nó từ trước và server tái sử dụng nó sau login.

### 1.1. Các yếu tố cần có trong một tình huống điển hình

- Ứng dụng có phiên hoặc cơ chế nhận diện request liên tục.
- Kẻ tấn công biết hoặc có khả năng áp đặt một session ID mà server chấp nhận.
- Nạn nhân sử dụng session ID ấy trước khi xác thực.
- Sau khi nạn nhân xác thực, server không tách phiên đã xác thực khỏi ID mà kẻ tấn công biết.
- Session đó còn hiệu lực và các kiểm soát bổ sung không chặn việc tái sử dụng.

Không phải cứ thấy một cookie tên JSESSIONID hoặc SESSION là hệ thống có lỗ hổng. Phải xem **ID trước và sau authentication, mapping phía server và khả năng tái sử dụng ID cũ**.

### 1.2. Tại sao đây là vấn đề của IAM?

IAM quản lý danh tính và phiên để áp dụng quyền. Nếu kẻ tấn công chiếm được **authenticated session**, các kiểm tra RBAC/ABAC thường nhìn thấy identity của nạn nhân, dù request không phải do người ấy thực hiện. Session fixation có thể biến một yêu cầu có vẻ như hợp lệ thành hành động trái phép dưới quyền victim.

Tác động có thể lớn khi victim có entitlement cao, chẳng hạn người phê duyệt thanh toán, quản trị IdP hoặc cloud role. Vì vậy phòng ngừa session fixation là một phần của **authentication, authorization, privileged session management và JML deprovisioning**.

## 2. Session ID, session object và cookie là ba khái niệm khác nhau

| Khái niệm | Vai trò | Ví dụ |
|---|---|---|
| **Session object** | Dữ liệu trạng thái phiên mà server lưu hoặc ánh xạ | Identity, MFA level, CSRF state |
| **Session ID** | Giá trị opaque giúp server tìm phiên | Chuỗi ngẫu nhiên không mang ý nghĩa nghiệp vụ |
| **Session cookie** | Phương tiện browser gửi session ID | Cookie SESSION hoặc JSESSIONID |
| **Authenticated session** | Phiên đã ràng buộc với principal và mức assurance | Phiên của nhân viên sau login |
| **Anonymous session** | Phiên chưa ràng buộc với người dùng xác thực | Trước login |
| **Access token** | Token truy cập resource theo OAuth profile | Bearer token API, không mặc nhiên là session cookie |
| **SSO session** | Trạng thái đăng nhập tại IdP hoặc federation | Phiên đăng nhập trung tâm |
| **Application session** | Phiên riêng của một ứng dụng/RP/SP | Phiên ERP sau OIDC/SAML login |

Một hệ thống có thể lưu session phía server trong memory, Redis hoặc database, cũng có thể dùng cơ chế cookie chứa trạng thái đã được ký/mã hóa. Với mô hình **server-side session ID**, server tra cứu ID và dữ liệu phiên; phòng ngừa fixation thường yêu cầu **đổi ID tại ranh giới xác thực**.

### 2.1. ID là một dạng bearer secret

Khi server coi ai sở hữu ID là người được phép dùng phiên, session ID có tác dụng như một **bearer credential**. Phải bảo vệ giá trị khỏi lộ, áp dụng entropy đủ mạnh, cookie transport an toàn, thời hạn phù hợp và đổi ID khi cấp quyền đăng nhập.

### 2.2. Principal khác session

Principal có thể là nhân viên An với ID bất biến. Phiên chỉ là một trong nhiều cách An đang truy cập. Khi phiên bị hủy, identity An vẫn còn; khi An Leaver, nhiều phiên và token ở nhiều hệ thống có thể cần bị thu hồi đồng thời.

### 2.3. Đăng nhập không đồng nghĩa giữ phiên cũ

Ứng dụng có thể giữ dữ liệu không nhạy cảm như lựa chọn ngôn ngữ hoặc giỏ hàng từ trước login, nhưng **không được dùng tiếp session identifier cũ mà attacker đã biết** để đại diện cho trạng thái authenticated.

## 3. Luồng tấn công Session fixation ở mức khái niệm

Sơ đồ dưới đây mô tả một kịch bản **giả lập để nhận diện và phòng thủ**, không sử dụng tài khoản, domain hoặc token thật.

~~~mermaid
sequenceDiagram
    participant A as Attacker
    participant B as Victim Browser
    participant App as Application
    participant Store as Session Store
    A->>App: Tạo một phiên anonymous hợp lệ
    App-->>A: Session ID S0
    Note over A,B: Attacker tìm cách khiến browser dùng S0
    B->>App: Truy cập trước login với S0
    App->>Store: Tra cứu anonymous session S0
    B->>App: Gửi thông tin xác thực hợp lệ
    App->>Store: Gắn principal của victim lên S0 (lỗi)
    App-->>B: Giữ nguyên cookie S0
    A->>App: Gửi request dùng lại S0
    App->>Store: Tra cứu S0 đã authenticated
    App-->>A: Response theo quyền của victim
~~~

**Điểm lỗi quyết định:** ID S0 vẫn là chìa khóa của phiên sau khi victim xác thực. Nếu ứng dụng phát một ID mới S1 và khiến S0 không còn tham chiếu đến phiên authenticated, chuỗi tấn công này bị phá vỡ.

### 3.1. Tại sao attacker có thể biết S0?

Có nhiều khả năng về mặt mô hình:

- Attacker tự tạo một anonymous session hợp lệ rồi tìm cách buộc victim dùng ID ấy.
- Một lớp ứng dụng/proxy tin session ID do client truyền trước khi xác thực.
- Một thành phần hoặc subdomain kém tin cậy có thể ảnh hưởng cookie trên miền được dùng chung.
- Hệ thống cũ chấp nhận session ID trong URL hay tham số.
- Một lỗ hổng injection hoặc client-side script can thiệp vào trạng thái tiền đăng nhập.

Không phải mọi khả năng đều tồn tại ở mọi ứng dụng. Khả năng đặt cookie thường bị giới hạn bởi các quy tắc browser về domain, path, prefix, Secure và nguồn phát; cần đánh giá chính xác từng môi trường thay vì giả định attacker luôn đặt được cookie.

### 3.2. Không cần biết mật khẩu nạn nhân

Nạn nhân có thể tự đăng nhập chính xác qua IdP và MFA. Nếu RP/ứng dụng giữ nguyên ID pre-auth đã bị cố định, attacker có thể tìm cách sử dụng phiên hậu xác thực. **MFA làm tăng độ tin cậy của đăng nhập nhưng không tự sửa lỗi tái sử dụng session ID**.

### 3.3. Không phải tất cả request dùng cùng cookie là tấn công

Browser thường gửi cùng một anonymous cookie qua nhiều lần tải trang. Điều đáng chú ý là **ranh giới authentication** và **liệu ID cũ còn có thể truy cập trạng thái authenticated hay không**.

## 4. Phân biệt Session fixation, session hijacking và CSRF

| Khái niệm | Điều xảy ra | Điểm khác biệt |
|---|---|---|
| **Session fixation** | Attacker biết/áp đặt ID trước khi victim login và ID tiếp tục có quyền sau login | Vấn đề **không đổi/tách ID tại auth boundary** |
| **Session hijacking** | Attacker dùng phiên authenticated của người khác | Khái niệm rộng, có thể do fixation hoặc token bị đánh cắp |
| **Session theft** | ID/cookie đã authenticated bị lấy qua XSS, log, network, malware | Attacker **lấy** bí mật đang có |
| **CSRF** | Victim browser bị khiến gửi thao tác không mong muốn trong phiên của chính mình | Attacker thường **không cần biết session ID** |
| **Login CSRF** | Victim browser bị đăng nhập vào account do attacker chọn | Có thể không cần cùng một session ID đã biết |
| **Session replay** | Một session token/cookie bị sử dụng lại | Hình thức sử dụng lại token; nguồn gốc có thể khác nhau |
| **Session prediction** | Attacker đoán ID do entropy/pattern yếu | Vấn đề sinh ID, có thể dẫn tới chiếm phiên |

### 4.1. CSRF token không tự giải quyết fixation

CSRF token bảo vệ việc gửi thao tác giả mạo theo mô hình đe dọa của nó. Nếu session ID đã được cố định và trở thành authenticated, việc CSRF token được lưu cùng session không nhất thiết chặn attacker đã có khả năng dùng session ấy. Cần **session ID rotation** đúng lúc, không thay bằng CSRF token.

### 4.2. SameSite không phải giải pháp hoàn chỉnh

Cookie SameSite giúp giảm một số cross-site request scenarios. Nó **không bảo đảm** browser không thể được dẫn đến một phiên đã biết, không đổi ID khi login và không bảo vệ trước mọi kịch bản cùng site/subdomain. Phòng chống fixation cần kiểm soát session lifecycle.

### 4.3. HttpOnly không đủ một mình

HttpOnly hạn chế JavaScript đọc session cookie, nhưng không thay đổi rủi ro khi server giữ ID đã được biết từ pre-auth. Một số kiểu can thiệp cookie hoặc nguồn khác vẫn có thể ảnh hưởng cách browser gửi session ID. Cần nhiều lớp, đặc biệt **rotate ID tại xác thực**.

### 4.4. Session fixation khác account takeover toàn phần

Việc dùng một phiên victim không có nghĩa attacker biết password, được cấp refresh token hoặc chiếm identity vĩnh viễn. Tuy vậy, trong phạm vi phiên ấy, attacker có thể thực hiện hành động theo quyền victim nếu không có kiểm soát bổ sung.

## 5. Những điểm ứng dụng dễ tạo fixation

### 5.1. Tạo session trước khi login

Ứng dụng lưu ngôn ngữ, giỏ hàng, flash messages, OAuth state hoặc preference trong anonymous session. Sau khi login, code chỉ thêm principal ID vào cùng session mà không đổi ID.

### 5.2. Tin session ID do client tự đặt

Một framework hoặc ứng dụng legacy chấp nhận ID chưa tồn tại trong session store rồi gắn session mới vào ID ấy. Đây là rủi ro khác với việc nhận ID do server tự sinh; không nên tin một string bất kỳ làm identity của phiên.

### 5.3. URL-based session tracking

Nếu session ID có thể xuất hiện trong URL, query, path parameter, bookmark, log hoặc Referer, việc vô tình tiết lộ và áp đặt ID có thể dễ hơn. Hạn chế/không dùng session ID trong URL; dùng cookie an toàn và chuyển tiếp bằng state/nonce phù hợp.

### 5.4. Cookie domain quá rộng

Cookie được phát với Domain bao trùm nhiều subdomains có thể tạo bề mặt ảnh hưởng từ một sibling subdomain kém tin cậy. Khi có thể, dùng host-only cookie và prefix phù hợp để hạn chế cookie injection/collision.

### 5.5. HTTP không bảo vệ kết nối

Nếu request hoặc response chứa session cookie đi qua HTTP không được bảo vệ, attacker trên đường truyền có thể quan sát hoặc tác động trong những điều kiện cụ thể. HTTPS, Secure cookie và HSTS giúp giảm nhóm rủi ro này nhưng **không thay session rotation**.

### 5.6. XSS và lỗi client-side

XSS có thể cho attacker can thiệp hành vi browser, thay đổi trạng thái hoặc khai thác quyền của victim trực tiếp. Dù HttpOnly giảm khả năng đọc cookie, XSS vẫn nghiêm trọng; cần output encoding, CSP thích hợp và giảm bề mặt injection.

### 5.7. Tích hợp IdP/SSO tự viết

Ứng dụng tự xử lý OIDC callback/SAML response nhưng quên thiết lập phiên ứng dụng mới sau authentication. IdP có thể xác thực đúng mà RP vẫn mang session fixation ở lớp riêng.

## 6. Điểm phòng thủ trọng tâm: đổi session identifier khi xác thực

Một quy tắc nền tảng:

> Khi anonymous session chuyển thành authenticated session, ứng dụng phải tạo một **session identifier mới, không dự đoán được**, và đảm bảo **ID cũ không còn tra cứu được trạng thái đã xác thực**.

Có thể giữ lại một số dữ liệu pre-auth an toàn nhưng không giữ khóa phiên cũ. Cách thực hiện cụ thể tùy servlet container, framework và thiết kế session store.

### 6.1. Luồng bảo vệ đúng

~~~mermaid
sequenceDiagram
    participant B as Victim Browser
    participant App as Application
    participant Store as Session Store
    B->>App: Truy cập trước login, cookie S0
    App->>Store: Anonymous state dưới S0
    B->>App: Login thành công
    App->>App: Xác minh authentication thành công
    App->>Store: Rotate session ID từ S0 sang S1
    Store-->>App: S0 không còn tham chiếu tới auth state
    App->>Store: Gắn principal và mức assurance với S1
    App-->>B: Set-Cookie phiên mới S1
    B->>App: Request protected resource với S1
    App->>Store: Kiểm tra S1 và authorization
    App-->>B: PERMIT/DENY theo principal và resource
    Note over Store: S0 không truy cập auth state của S1
~~~

### 6.2. Thứ tự quan trọng

Phiên cần được chuyển đổi theo ngữ nghĩa an toàn của framework, không tạo khoảng trống trong đó ID cũ và mới cùng tham chiếu tới authenticated state. Tốt nhất dựa vào session fixation protection được hỗ trợ và đã kiểm thử của framework, tránh tự viết cơ chế copy session ID hoặc thao tác session store thiếu transaction.

### 6.3. Chỉ thay tên cookie không đủ

Đổi cookie name SESSION thành MYSESSION không làm ID được rotate. Giá trị mới phải được server sinh an toàn, mapping cũ phải bị loại khỏi quyền authenticated và client phải nhận được cookie mới.

### 6.4. Không tái sử dụng ID cũ làm alias

Nếu server cho cả S0 và S1 tìm tới authenticated principal để tương thích backward, attacker dùng S0 vẫn thành công. Test cần xác nhận **ID cũ bị từ chối hoặc chỉ truy cập trạng thái anonymous không quyền**.

## 7. Rotation tại những ranh giới tăng mức tin cậy

Thời điểm quan trọng nhất là **login thành công**. Một số ranh giới khác có thể cần thay identifier, tạo phiên riêng hoặc xác minh lại theo threat model:

| Sự kiện | Điều nên cân nhắc |
|---|---|
| Anonymous → authenticated | Rotate ID, tách khỏi pre-auth session |
| Đăng nhập tài khoản khác | Không dùng lại session authenticated của người trước |
| Reauthentication sau timeout | Rebind/rotate theo framework và risk policy |
| MFA step-up | Đổi hoặc nâng phiên theo chính sách, không mặc định chỉ gắn cờ |
| Chuyển role/đặc quyền | Đánh giá session lifecycle, authorization freshness |
| Impersonation/delegation | Identity nguồn, actor và target phải được phân biệt rõ |
| Vào khu vực PAM/admin | Có thể yêu cầu privileged session riêng, JIT và giới hạn thời gian |
| Logout | Invalidate server session và xóa cookie phù hợp |
| Leaver/incident revoke | Terminate sessions và chặn các đường token khác theo SLA |

### 7.1. Không coi mọi role change là login mới

Một người chuyển team có thể đang ở session còn hợp lệ. Thay ID đơn độc không đủ nếu role/entitlement cache vẫn là quyền cũ. Cần phối hợp update authorization, session revocation hoặc step-up phù hợp.

### 7.2. Step-up MFA không tự gia hạn mọi quyền

Nâng authentication assurance không có nghĩa principal được tự động tăng role hoặc hết hạn entitlement được gia hạn. Authorization vẫn phải kiểm tra RBAC/ABAC, grant validity và resource scope.

### 7.3. Không mất dữ liệu pre-auth cần thiết

Ví dụ giỏ hàng có thể được chuyển sang phiên mới nếu được xác thực và validate lại. Tránh copy toàn bộ untrusted session attributes như roleFlag, accountId hoặc authorization decisions do client/anonymous state ảnh hưởng.

## 8. Cookie hardening: giảm khả năng cố định ID

Cookie attributes giúp giảm bề mặt tấn công nhưng **không thay việc rotate session ID tại authentication boundary**.

| Thuộc tính | Mục đích | Giới hạn |
|---|---|---|
| **Secure** | Browser chỉ gửi cookie qua kênh an toàn theo quy tắc | Không đổi ID đã bị cố định |
| **HttpOnly** | Ngăn JavaScript đọc cookie trực tiếp | Không ngăn mọi XSS abuse |
| **SameSite** | Giới hạn một số cross-site requests | Chủ yếu hỗ trợ CSRF; không thay rotation |
| **Path** | Quy định phạm vi đường dẫn browser gửi cookie | Không phải security boundary giữa apps cùng origin |
| **Domain** | Chọn host/domain scope | Domain rộng tăng bề mặt sibling subdomains |
| **Max-Age/Expires** | Hạn lưu cookie ở browser | Không thay server-side expiry/revoke |
| **Cookie prefix** | Browser áp các điều kiện đặt cookie | Chỉ hữu ích khi cấu hình và browser hỗ trợ |

### 8.1. Host-only cookie

Nếu không đặt thuộc tính Domain, cookie có phạm vi host đã phát. Điều này hạn chế nguy cơ từ subdomain khác so với cookie dùng chung domain cha.

~~~text
portal.example.test          Ứng dụng chính
files.example.test           Subdomain khác
legacy.example.test          Subdomain có bảo mật yếu hơn
~~~

Một subdomain kém tin cậy có thể tạo rủi ro nếu session cookie dùng chung phạm vi miền hoặc server không xử lý tốt cookie collisions. Khả năng tấn công cụ thể phụ thuộc cách browser thực thi cookie rules, cookie prefixes và cách ứng dụng chọn cookie.

### 8.2. Prefix __Host-

Trong browser hỗ trợ cookie prefixes, tên cookie bắt đầu bằng **__Host-** phải đáp ứng:

- Có thuộc tính **Secure**.
- **Không có Domain**.
- Có **Path=/**.
- Được đặt trong ngữ cảnh kết nối an toàn phù hợp.

~~~http
Set-Cookie: __Host-SESSION=<opaque-session-id>; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

HttpOnly là lớp bảo vệ bổ sung, **không phải điều kiện bắt buộc riêng của prefix __Host-**.

### 8.3. Prefix __Secure-

Prefix **__Secure-** yêu cầu Secure ở browser hỗ trợ, nhưng không buộc host-only hay Path=/ như __Host-. Khi không cần chia sẻ cookie giữa subdomains, __Host- thường giúp giảm nguy cơ cookie scope/collision nếu dùng đúng.

### 8.4. SameSite policy

- **Lax:** cho phép một số top-level navigation và thường ít ảnh hưởng trải nghiệm hơn Strict.
- **Strict:** hạn chế mạnh hơn nhưng có thể ảnh hưởng các luồng chuyển hướng SSO.
- **None:** cho phép cross-site sending theo mô hình cookie, với yêu cầu Secure ở browser hiện đại; vẫn chịu chính sách browser khác.

Chọn dựa trên luồng OIDC/SAML, frontend và threat model. SameSite **không thay CSRF token** hoặc session ID rotation.

### 8.5. Thời hạn browser khác hạn server

Cookie hết hạn trên browser giúp giảm thời gian sử dụng nhưng server vẫn phải có inactivity/absolute session timeout và cơ chế invalidate. Nếu attacker còn biết S0 và server vẫn chấp nhận S0, xóa cookie ở browser nạn nhân không đủ.

### 8.6. Cookie collisions

Browser có thể gửi nhiều cookies trùng tên với scope khác nhau. Không tin thứ tự các cookie làm bảo đảm an toàn; hạn chế cookie name/scope chồng lấn và kiểm tra container xử lý nhiều cookies cùng tên.

## 9. Rotation phải đúng cả phía server

Phát Set-Cookie mới chỉ là một phần. Session store phải đảm bảo **ID trước xác thực không còn tìm được trạng thái authenticated sau xác thực**.

### 9.1. Các phương pháp triển khai

Tùy framework/session store:

1. Thay identifier của session hiện có theo cơ chế an toàn.
2. Tạo session mới và chỉ chuyển các attributes đã kiểm tra.
3. Invalidate anonymous session rồi tạo authenticated session.
4. Sử dụng session fixation protection tích hợp của framework.

Ưu tiên cơ chế được hỗ trợ và đã kiểm thử. Không tự viết thuật toán copy session và để hai ID cùng tham chiếu tới principal đã xác thực.

### 9.2. Dữ liệu pre-auth cần thận trọng

Có thể muốn bảo toàn locale/giỏ hàng sau login, nhưng tránh mang vô điều kiện các giá trị như userId, roleFlag, isAdmin, authzCache, resetToken hoặc dữ liệu do anonymous request ảnh hưởng. **Rotation chống ID fixation, không tự làm sạch các session attributes không tin cậy**.

### 9.3. ID mới cần không dự đoán được

Framework nên dùng secure random generator thích hợp. Không tạo session ID từ username, email, timestamp hoặc số đếm.

### 9.4. Distributed session store

Nếu Redis/database dùng chung nhiều nodes, kiểm tra old ID mất hiệu lực trên mọi node. Đổi ID ở node A nhưng node B vẫn nhận old ID là chưa phòng thủ đầy đủ.

### 9.5. Định nghĩa rõ old ID bị xử lý thế nào

Tùy thiết kế, request dùng old ID có thể được cấp anonymous session mới hoặc bị từ chối. Điều bắt buộc là **không được truy cập authenticated principal thông qua old ID**.

## 10. Spring Security và Java Servlet

Spring Security có cơ chế session fixation protection; với servlet container hỗ trợ, có thể thay ID qua session-fixation strategy của framework thay vì tự code.

### 10.1. Cấu hình Spring Security minh họa

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class WebSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        http.authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/public/**").permitAll()
                .anyRequest().authenticated()
        );

        http.formLogin(Customizer.withDefaults());

        http.sessionManagement(session -> session
                .sessionFixation(fixation -> fixation.changeSessionId())
        );

        http.logout(logout -> logout
                .invalidateHttpSession(true)
                .clearAuthentication(true)
        );

        return http.build();
    }
}
~~~

**Lưu ý:** Cấu hình minh họa cho servlet session và API của các phiên bản Spring Security hỗ trợ cú pháp này. Nó không phải cấu hình production hoàn chỉnh. SSO/OIDC, Spring Session, custom authentication handlers và version khác nhau cần kiểm thử riêng; không mặc định mọi trường hợp đều đi qua strategy.

### 10.2. Servlet API changeSessionId

~~~java
String newSessionId = request.changeSessionId();
~~~

Ở container hỗ trợ, lệnh này thay ID cho HTTP session hiện hành. Không gọi nó trên mọi request một cách tùy tiện; nên để security framework gọi tại đúng ranh giới xác thực để tránh mất tương thích CSRF/correlation state.

### 10.3. Các thuộc tính cookie ở Spring Boot servlet

~~~properties
server.servlet.session.cookie.name=__Host-SESSION
server.servlet.session.cookie.secure=true
server.servlet.session.cookie.http-only=true
server.servlet.session.cookie.path=/
server.servlet.session.cookie.same-site=lax
server.servlet.session.tracking-modes=cookie
server.servlet.session.timeout=30m
~~~

Cần bảo đảm cookie __Host-SESSION **không có Domain**, HTTPS được dùng và Set-Cookie thực tế đúng. Properties hỗ trợ/semantics tùy phiên bản Spring Boot, servlet container và Spring Session. Timeout 30 phút chỉ là ví dụ.

### 10.4. Custom login logic

Nếu ứng dụng đặt SecurityContext thủ công hoặc có custom OIDC callback, cần xác minh session authentication strategy vẫn chạy. Đừng dựa vào sự tồn tại của cấu hình mà bỏ kiểm thử ID trước/sau login.

### 10.5. Stateless API

Nếu API dùng stateless authentication đúng nghĩa, không có server-side authenticated HTTP session theo mô hình trên để rotate. Nhưng bearer token có thể bị đánh cắp/replay, cookie token vẫn có scope/expiry issues. Stateless **không đồng nghĩa không cần quản lý token và quyền**.

## 11. Proxy, TLS và nhiều node

### 11.1. HTTPS, Secure và HSTS

HTTPS bảo vệ cookie khi truyền qua mạng; Secure hạn chế gửi cookie trên kênh không an toàn; HSTS giảm downgrade trong những điều kiện phù hợp. Các biện pháp này bổ trợ nhưng không thay rotation.

### 11.2. Trusted reverse proxy headers

Khi TLS được terminate tại reverse proxy, ứng dụng cần biết trusted external scheme/host để phát cookie chính xác. Không tin X-Forwarded-Proto hoặc Forwarded header do client tùy ý gửi; cấu hình trusted proxy boundary.

### 11.3. Tránh lộ session ID trong log

Không ghi nguyên Cookie, Set-Cookie, Authorization header, session ID trong URL, APM spans hay crash logs. Dùng correlation ID độc lập cho debug; không sử dụng session bearer secret làm tracking ID công khai.

### 11.4. Load balancer stickiness

Sticky routing cookie thường chỉ chọn backend node, không nhất thiết là session credential. Nhưng không được nhầm nó với session authentication cookie. Khi session store phân tán, kiểm tra cả old/new ID trên các nodes sau failover.

### 11.5. Rotation phải đồng nhất khi replication trễ

Nếu node A thay S0 bằng S1 nhưng node B vẫn thấy S0 có principal, cần điều chỉnh semantics của session store hoặc invalidation cho phù hợp. Kiểm thử concurrency và replica lag ở ranh giới login.

## 12. IdP/SSO và application session: hai lớp cần bảo vệ

Khi ứng dụng dùng Single Sign-On, có thể tồn tại:

1. **IdP session:** người dùng đã được xác thực tại Identity Provider.
2. **Relying Party / Service Provider session:** phiên nội bộ của ứng dụng sau khi nhận authentication response.

Một IdP bảo vệ tốt không đảm bảo RP tự động phòng ngừa Session fixation.

### 12.1. OIDC callback và session pre-auth

Ứng dụng thường tạo anonymous session để lưu state, nonce hoặc PKCE code verifier trước khi redirect sang IdP. Sau callback thành công:

1. Kiểm tra authorization response/correlation state theo OIDC.
2. Xác thực token issuer, audience, signature và các điều kiện profile.
3. Tiêu thụ correlation state, tránh replay.
4. **Rotate local session ID hoặc tạo authenticated session mới**.
5. Gắn principal vào session mới, không vào old ID đã biết.
6. Kiểm tra old ID không truy cập được quyền mới.

### 12.2. State và nonce có vai trò riêng

| Cơ chế | Mục tiêu |
|---|---|
| **OIDC state** | Liên kết response và authorization request, hỗ trợ chống login CSRF |
| **OIDC nonce** | Liên kết ID token và authentication request theo luồng phù hợp |
| **PKCE** | Ràng buộc authorization code với client giữ verifier |
| **Session ID rotation** | Tách authenticated RP session khỏi ID pre-auth |
| **CSRF token** | Chống request đổi trạng thái trái ý user theo mô hình CSRF |

Các lớp này bổ trợ, không thay thế nhau. Một ứng dụng xác minh OIDC state đúng vẫn có thể giữ old session ID qua callback nếu lập trình sai.

### 12.3. SAML cũng cần quản trị phiên RP

SAML có assertion, InResponseTo, RelayState và các quy tắc replay protection riêng. Nhưng sau khi xác nhận assertion, SP vẫn phải **không giữ attacker-known anonymous session ID làm authenticated session ID**.

### 12.4. SSO logout không tự làm mọi ứng dụng hết quyền

Người dùng logout tại IdP hoặc bị disable ở IdP chưa chắc mọi RP đã xóa session. Cần cơ chế session invalidation, front/back-channel logout theo khả năng, expiry và kiểm tra quyền trên resource. Không đồng nhất việc RP chống fixation lúc login với SSO single logout lúc kết thúc.

### 12.5. SSO có thể dùng nhiều cookie riêng

RP cookie, IdP cookie, proxy auth cookie và LB cookie có nguồn phát và lifetime riêng. Khi điều tra một session fixation, phải xác định **cookie nào thực sự chọn authenticated principal**; không chỉ tìm cookie có tên SESSION đầu tiên.

## 13. RBAC, ABAC, assurance và thời hạn quyền

Ngay cả khi session fixation được xử lý, ứng dụng vẫn cần authorization theo **principal, action, resource, context và thời gian**.

### 13.1. RBAC

Ví dụ nhân viên có role finance.viewer nhưng không có finance.export. Một session hợp lệ không tự cho quyền export.

~~~text
Principal: employee-1042
Session: authenticated with ID S1
Role: finance.viewer
Request: finance.report.export
Decision: DENY
~~~

Nếu session đã bị attacker chiếm, ít quyền hơn thường giảm tác động nhưng vẫn là lỗi an ninh; không lấy RBAC làm lý do bỏ qua rotation.

### 13.2. ABAC

Một policy logic:

~~~text
PERMIT khi:
    session.authenticated == true
    AND principal.status == ACTIVE
    AND session.principalId == principal.id
    AND principal.tenantId == resource.tenantId
    AND action IN effectiveGrants(principal, resource)
    AND now < session.absoluteExpiry
    AND now < applicableGrant.validUntil
    AND session.assurance >= requiredAssurance(action)
~~~

Các thuộc tính session/principal phải được ràng buộc với authentication tin cậy; resource/tenant và current entitlements không được lấy trực tiếp từ anonymous state do client kiểm soát.

### 13.3. MFA step-up có thể tạo trust boundary mới

Khi user truy cập chức năng chuyển tiền hoặc role admin, hệ thống có thể yêu cầu reauthentication/MFA. Cần ràng buộc kết quả step-up vào session và actor chính xác; đánh giá việc đổi ID hoặc tách privileged session theo framework và mức rủi ro.

**MFA không tự sửa session fixation** nếu ID cũ đã biết vẫn có quyền sau bước xác thực mạnh hơn.

### 13.4. Session role cache có thể stale

User Mover khỏi team Finance nhưng session vẫn giữ role Finance cũ. Dù rotate ID thành công, quyền vẫn tồn dư nếu không refresh/revoke authorization. Kết hợp entitlement version, policy data freshness và action-level checks.

### 13.5. Switching tenant không chỉ là thay một cookie

Một user có thể có quyền ở tenant A nhưng không phải tenant B. Không tin một tenantId được chọn trước login rồi giữ nguyên làm authority sau login. Khi chuyển tenant phải xác minh membership và resource policy; với tác vụ nhạy cảm có thể cần session binding/step-up.

## 14. Joiner–Mover–Leaver liên quan Session fixation thế nào?

Vòng đời danh tính không chỉ quản lý accounts/roles. **Phiên đang tồn tại** là một đường truy cập thực tế, có thể tiếp tục cho phép hành động sau khi chính sách hoặc quan hệ nhân sự đã thay đổi.

### 14.1. Joiner

Khi nhân viên mới được tạo identity và có lần login đầu:

- Account phải được xác minh từ nguồn nhân sự có thẩm quyền.
- Session trước login không được tự mang entitlement hay identity của người khác.
- Sau authentication thành công phải rotate session identifier.
- Mỗi application/RP cần thiết lập principal, scope và session policy đúng.
- Nếu account được provision trước ngày bắt đầu làm việc, không được mở quyền nhạy cảm trước thời điểm policy cho phép.

### 14.2. Mover

Nhân viên chuyển team, project, tenant hoặc mức đặc quyền:

- Thu hồi entitlements cũ theo thời điểm có hiệu lực.
- Cập nhật group/role qua IdP, SCIM hoặc API mục tiêu.
- Tái đánh giá session hiện hành: revoke/re-login/refresh authz tùy risk.
- Với role admin, cân nhắc privileged session riêng và JIT.
- Không để một session ID còn hợp lệ mặc định giữ cached Finance role sau khi user sang Operations.

Rotation không thay các bước revoke/grant thực tế ở target.

### 14.3. Leaver

Khi HRIS xác định Leaver effectiveAt:

1. Chặn xác thực mới ở IdP khi policy yêu cầu.
2. Thu hồi account/entitlements tại targets.
3. Vô hiệu những application sessions hiện còn hoạt động theo SLA.
4. Xử lý OAuth access/refresh tokens và SSO sessions theo cơ chế provider.
5. Xác minh local logins, service principals, delegation và share links liên quan.
6. Ghi thời điểm requested revoke, enforced revoke và verification.
7. Đánh dấu PARTIAL nếu target chưa kiểm chứng hoặc còn quyền tồn dư.

**Disable user ở IdP không chắc xóa RP session ngay**; một hệ thống có thể cần giải pháp logout propagation hoặc resource-side status checks.

### 14.4. Trường hợp user đang có phiên tại nhiều thiết bị

Một người có session trên laptop, điện thoại và trình duyệt khác. Việc logout trên một thiết bị không mặc nhiên chấm dứt tất cả. Với Leaver/compromise, cần chức năng revoke-all-sessions hoặc target-specific controls theo chính sách.

### 14.5. JML dành cho service accounts

Workload/service account thường dùng token, mTLS, API key hoặc workload federation thay vì browser session. Session fixation theo mẫu anonymous browser login có thể **không áp dụng trực tiếp** cho mọi M2M flow. Nhưng bài học về binding identity, token issuance, principal/credential lifetime và revocation vẫn quan trọng. Không gọi mọi credential replay của service account là Session fixation.

## 15. Session fixation và các tài khoản đặc quyền

Một admin console có thể tạo anonymous session trước login để hiển thị form. Nếu giữ cùng ID sau khi quản trị viên xác thực, attacker được lợi đặc biệt lớn vì session mang entitlement nhạy cảm.

### 15.1. Các lớp kiểm soát bổ trợ

- Rotate ID sau login và authentication step-up.
- Cookie host-only, Secure, HttpOnly và SameSite phù hợp.
- Reauthentication cho thao tác rủi ro.
- PAM session với access approval, JIT và timeout.
- RBAC/ABAC kiểm tra action/resource tại server.
- Device/risk signals nếu có và đúng privacy policy.
- Alert khi phiên thay đổi principal/assurance bất thường.
- Khả năng revoke nhanh khi nghi compromise.

### 15.2. MFA không đảm bảo tránh bị dùng session

Attacker có thể không biết OTP nhưng có session ID được tái sử dụng sau MFA. Đây là lý do phải bảo vệ trust transition ngay cả khi ứng dụng đã triển khai MFA.

### 15.3. Shared admin accounts làm audit khó hơn

Nếu nhiều người dùng cùng một admin account, server có thể không phân biệt ai đã tạo phiên; forensic và SoD kém hơn. Cần định danh quản trị cá nhân, JIT và privileged session riêng khi có thể.

## 16. Logout, idle timeout và absolute lifetime

Session fixation thường tập trung tại login nhưng **đóng phiên** cũng quan trọng để giảm khả năng ID cũ tiếp tục có hiệu lực.

| Kiểm soát | Tác dụng | Lưu ý |
|---|---|---|
| **Explicit logout** | Hủy phiên khi user kết thúc | Invalidate ở server, không chỉ xóa client cookie |
| **Idle timeout** | Hết hạn sau khoảng không hoạt động | Tính activity từ nguồn tin cậy |
| **Absolute timeout** | Giới hạn tổng thời gian sống | Không reset vô hạn theo activity |
| **Reauthentication** | Xác minh lại identity khi rủi ro thay đổi | Cân nhắc đổi session ID/binding |
| **Revoke all sessions** | Chặn nhiều thiết bị khi Leaver/incident | Cần biết tất cả RP/targets |
| **Session binding signals** | Phát hiện bất thường | Cẩn trọng false positive khi IP/device thay đổi |
| **Authorization freshness** | Chặn role bị thu hồi còn cache | Cần phiên bản entitlement và policy |

### 16.1. Chỉ xóa cookie ở browser chưa đủ

Nếu server còn mapping S0 và attacker đã biết S0, một browser khác có thể tiếp tục gửi ID. Logout cần invalidate session object/token server-side theo cơ chế, đồng thời xóa cookie phù hợp trên client.

### 16.2. Xóa cookie phải đúng scope

Cookie deletion thường cần trùng **name, path và domain semantics** với cookie gốc. Nếu sai, browser có thể giữ cookie cũ. Với cookie host-only, không thêm Domain khi xóa.

### 16.3. Idle timeout không thay revoke chủ động

Nếu user Leaver lúc 14:00 nhưng session sẽ tự hết lúc 18:00, không nên chờ bốn giờ nếu policy yêu cầu ngắt ngay. Timeout là một lớp; revocation theo lifecycle là lớp khác.

### 16.4. Token và session có thể hết hạn khác nhau

OAuth access token, refresh token, IdP session, RP session và PAM session là các đối tượng với lifetime/authority khác nhau. Cần inventory và khả năng revoke theo hợp đồng, không suy logout một cookie chặn tất cả đường.

## 17. Session fixation trong hệ thống dùng Redis/database session store

Một ứng dụng có nhiều pods có thể lưu session map tại Redis. Nếu old ID vẫn được đọc ở bất kỳ node nào sau login, rủi ro còn.

### 17.1. Những điều cần kiểm tra

- Sau login, ID mới có xuất hiện không?
- Old ID có còn key trong store không?
- Nếu old ID còn được lưu tạm, nó có tham chiếu tới authenticated principal không?
- Nếu có replication/latency, một node khác có nhận old ID không?
- Có TTL riêng cho anonymous/authenticated session không?
- Session serialization/migration có copy untrusted attributes không?
- Khi logout, session entries ở store có bị invalidate không?

### 17.2. Race condition tại ranh giới login

Hai request cùng dùng S0 ngay khi login có thể đến hai nodes. Một request xử lý authentication, request kia vẫn dùng S0. Cần semantics session transition không để S0 quan sát authenticated state. Không chỉ dựa vào trạng thái cookie client khi có request song song.

### 17.3. Session store failover

Nếu session store mất kết nối, không nên tự cấp quyền theo cookie ID không xác minh được. Lựa chọn fail-safe theo chính sách; với tài nguyên nhạy cảm thường không cho qua chỉ vì không truy xuất được session.

### 17.4. Session serialization và distributed cache

Không đưa session ID hay toàn bộ principal credentials vào logs để debug. Với distributed cache, kiểm tra TTL và serialization metadata phù hợp; stale authorization cache phải có invalidation khi RBAC/ABAC thay đổi.

## 18. Đăng nhập nhiều lần và chuyển tài khoản trên cùng browser

Người dùng có thể logout tài khoản A rồi login tài khoản B trên cùng trình duyệt.

### 18.1. Tránh session identity confusion

Nếu ứng dụng tái sử dụng session A và chỉ thay một trường userId khi login B, dữ liệu cũ như authzCache, selectedTenant, delegatedApprovals có thể vẫn thuộc A. Nên tạo/rotate authenticated session đúng boundary, loại bỏ các thuộc tính account-specific cũ.

### 18.2. Multiple tabs

Hai tabs có thể dùng chung cookie cùng origin. Nếu một tab login/logout, tab kia có thể gửi request với ID cũ hoặc mới tùy thời điểm. Server cần xử lý an toàn, không để request cũ truy cập quyền mới nhờ alias session.

### 18.3. Account switching không dùng cùng một principal context

Mỗi lần đổi principal cần kiểm tra identity binding, MFA/step-up và tenant; không chỉ thay avatar/username trên UI. Các API phải xác minh phiên và resource authorization độc lập.

## 19. Cách phát hiện bằng quan sát hành vi

Không thể kết luận chỉ bằng nhìn mã HTML hoặc cookie flag. Cần đo **session ID trước/sau auth** và old-ID access outcome.

### 19.1. Bằng chứng tối thiểu

1. Trước login có session ID S0 (nếu ứng dụng tạo session anonymous).
2. Login bằng test identity hợp lệ.
3. Sau login server phát/nhận session ID S1 khác S0.
4. S1 được nhận diện là authenticated test identity.
5. Request với S0 không được xác thực thành test identity.
6. Test qua mọi backend nodes/SSO callbacks có liên quan.
7. Khi logout, S1 không còn truy cập protected resource.
8. Sau Mover/Leaver, role/session còn hiệu lực được đánh giá đúng policy.

### 19.2. So sánh ID an toàn trong test

Không ghi raw session IDs vào báo cáo chia sẻ. Có thể dùng placeholder S0/S1 hoặc xác minh so sánh trực tiếp trong test process rồi xóa dữ liệu; không đưa session bearer secrets vào CI logs.

### 19.3. Không kiểm thử bằng tài khoản người khác

Chỉ dùng test accounts, môi trường được cho phép và không làm gián đoạn production. Kiểm tra fixation cần quyền kiểm thử và thao tác an toàn; không cần gửi session IDs thật trong ticket/chat.

## 20. Ma trận kiểm thử Session fixation

Ma trận dưới đây dành cho test accounts hoặc môi trường được phép. Mỗi trường hợp cần định nghĩa **ID cũ, ID mới, trạng thái xác thực và response từ protected resource**.

| Tình huống | Kết quả kỳ vọng |
|---|---|
| Anonymous session S0 trước login | Không có authenticated principal |
| Đăng nhập thành công với S0 | Phát ID mới S1 khác S0 |
| Request hợp lệ với S1 | Có thể truy cập đúng quyền test user |
| Request protected resource với S0 sau login | Không authenticated như test user |
| S0 không tồn tại trong store | Không tạo quyền mới cho S0 |
| S0 là ID do client tự chọn, chưa từng được server phát | Không nhận như authenticated session |
| Đăng nhập sai mật khẩu | Không gắn principal authenticated vào S0 |
| Login sau MFA | Không giữ attacker-known ID ở auth boundary |
| Step-up lên quyền nhạy cảm | Session/assurance binding đúng chính sách |
| Login qua OIDC callback | Rotate local RP session ID |
| Login qua SAML callback | Rotate hoặc tạo local authenticated session an toàn |
| OIDC state hợp lệ, nhưng S0 cũ được gửi lại | S0 không có authenticated RP state |
| OIDC state sai/hết hạn | Callback bị từ chối |
| Logout từ S1 | S1 không được dùng để truy cập protected resource |
| SSO logout khi còn RP session | Hành vi theo hợp đồng; không giả định tự ngắt |
| Cookie thiếu Secure trong production HTTPS | Báo cấu hình yếu |
| Cookie thiếu HttpOnly | Báo rủi ro đọc cookie bởi script |
| Cookie __Host- có Domain | Browser không chấp nhận prefix cookie theo chuẩn |
| Cookie __Host- không có Path=/ | Browser không chấp nhận đúng prefix |
| Cookie dùng Domain rộng | Đánh giá subdomain trust và collisions |
| URL chứa session ID | Phát hiện/lập kế hoạch loại bỏ |
| Có nhiều cookie cùng tên | Chọn session an toàn, không dựa thứ tự mơ hồ |
| Session timeout idle | Không truy cập protected resource sau timeout |
| Session timeout absolute | Không kéo dài vô hạn nhờ activity |
| Redis failover sau login | S0 vẫn không có principal authenticated |
| Request đồng thời S0/S1 | Không có cửa sổ S0 được cấp quyền |
| User chuyển tài khoản A → B | Không giữ authz state/tenant của A |
| User chuyển tenant A → B | Membership và resource authorization được kiểm tra |
| Mover làm mất Finance role | Phiên cũ không cho action Finance |
| Leaver disable ở IdP | RP/session/token được xử lý theo SLA |
| JWT access token còn hạn sau grant revoke | Quyền được chặn theo architecture/policy |
| Service principal M2M | Không gán nhãn browser session fixation cho mọi token issue |
| API direct bypass gateway | Có resource-side authz đúng |
| Old ID xuất hiện trong access log | Không để lộ bearer secret |
| Session cookie xóa nhưng server mapping còn | Test phát hiện revoke chưa đủ |

### 20.1. Kiểm thử phủ nhiều auth paths

Không chỉ thử form login; kiểm tra OIDC, SAML, account switch, password reset, reauthentication, MFA step-up và đường login tùy biến nếu có. Một framework config có thể an toàn với form login nhưng một custom callback lại tạo session khác không rotate.

### 20.2. Kiểm thử trước/sau bằng test fixture

S0 và S1 là **biến nội bộ của test**. Có thể assert chúng khác nhau mà không in ra log:

~~~text
testSessionFixationDefense():
    browser = newIsolatedTestClient()
    anonymous = browser.get("/public/session-start")
    S0 = browser.sessionCookie()

    loginResult = browser.loginWithApprovedTestUser()
    assert loginResult.authenticated

    S1 = browser.sessionCookie()
    assert S1 exists
    assert S1 != S0

    assert protectedRequest(cookie=S1).authorizedForTestUser
    assert not protectedRequest(cookie=S0).authorizedForTestUser

    browser.logout()
    assert not protectedRequest(cookie=S1).authorizedForTestUser
~~~

Nếu ứng dụng **không tạo anonymous session** trước login, test không nên cố đòi phải có S0. Có thể test rằng client-supplied unknown ID không được nâng thành authenticated identity, và login vẫn tạo session an toàn theo hợp đồng.

### 20.3. Kiểm thử ranh giới với pre-auth state

Nếu anonymous session lưu giỏ hàng, locale, OAuth state, cần test:

- Dữ liệu có thể giữ hợp lệ không bị mất vô ích.
- Account/role/authzCache không được copy trái phép.
- OIDC state/nonce không được tái sử dụng sau callback.
- S0 không có quyền post-login dù dữ liệu pre-auth được migrate.
- Role high-risk vẫn yêu cầu step-up/re-authentication theo policy.

### 20.4. Kết quả pass/fail phải dựa vào server

Chỉ thấy cookie mới trên browser chưa đủ. Nếu old ID vẫn tìm được principal ở backend, test phải fail. Ngược lại, việc framework tạo session object mới nhưng cookie browser chưa nhận/không gửi đúng cũng khiến login flow bị lỗi chức năng.

## 21. Bằng chứng audit và giám sát bất thường

Mục tiêu audit là chứng minh **authentication boundary đã chuyển phiên an toàn** và phát hiện session reuse/rủi ro, không lưu raw bearer secrets.

### 21.1. Sự kiện nên có

- Anonymous session created khi cần, không đính kèm principal.
- Authentication succeeded/failed.
- Session rotated: có correlation giữa old session record và new authenticated state mà không lộ raw IDs.
- MFA/step-up completed và assurance level.
- Principal/tenant switch.
- Session expired/invalidated/logout.
- Leaver/incident revoke events.
- Protected resource access denied sau revoked/stale ID.
- Session store errors/replica lag có thể ảnh hưởng verification.

### 21.2. Log minh họa không chứa session token

~~~json
{
  "eventType": "SESSION_ROTATED_AFTER_AUTH",
  "principalRef": "employee-1042",
  "application": "finance-portal",
  "authMethod": "OIDC",
  "reason": "ANONYMOUS_TO_AUTHENTICATED",
  "oldSessionInvalidated": true,
  "policyVersion": "session-policy-v7",
  "timestamp": "2026-11-23T09:15:00+07:00",
  "correlationId": "auth-flow-2841"
}
~~~

Ví dụ giả lập. Các trường oldSessionInvalidated chỉ nên ghi TRUE khi hệ thống có bằng chứng thực tế về session store/strategy, không đặt giá trị cố định cho đẹp dashboard.

### 21.3. Những chỉ số hữu ích

| Chỉ số | Tín hiệu |
|---|---|
| Tỷ lệ login thành công có ID rotation | Độ phủ kiểm soát fixation |
| Số old-ID requests sau login | Tìm request song song hoặc bất thường |
| Số old-ID requests được authenticated | Dấu hiệu lỗi nghiêm trọng |
| Số custom auth flows không qua strategy | Điểm mù framework |
| Tỷ lệ phiên có cookie flags đúng | Chất lượng cookie hardening |
| RP session còn active sau Leaver | Quyền truy cập tồn dư |
| Thời gian revoke-to-enforced | SLO session termination |
| Session invalidation failures | Lỗi hủy phiên/server store |
| Redis replication lag quanh auth boundary | Nguy cơ race |
| Số lần step-up cần MFA bị bypass | Rủi ro privileged access |
| Số login success với session anomaly | Ưu tiên điều tra |
| Dữ liệu token/cookie lọt logs | Credential leakage risk |

### 21.4. Kết quả false positives

User mở nhiều tab, mạng retry, proxy cache hoặc request đã gửi trước khi login hoàn tất có thể dẫn tới old-ID requests. Những request này **không được truy cập auth state**, nhưng việc xuất hiện old ID không tự chứng minh đã bị tấn công. Phân tích nguồn, timing và outcome.

### 21.5. Giữ audit theo nguyên tắc tối thiểu

Dùng correlation IDs, actor reference, policy version và time. Không lưu raw session ID, raw Cookie header, CSRF token, refresh token, password hoặc PII không cần thiết. Quyền xem logs cũng phải được giới hạn.

## 22. Ứng phó khi phát hiện Session fixation

Nếu có bằng chứng một session ID known-before-login vẫn dùng được sau authentication, đây có thể là sự cố truy cập trái phép hoặc điểm yếu nghiêm trọng cần khắc phục.

### 22.1. Bước giảm rủi ro

1. Xác minh hiện tượng trong môi trường được phép, tránh lan truyền session tokens thật.
2. Đánh giá hệ thống/endpoint/login flows bị ảnh hưởng.
3. Áp dụng session invalidation hoặc revoke affected sessions theo incident runbook.
4. Cân nhắc yêu cầu reauthentication cho người dùng bị ảnh hưởng.
5. Vá authentication boundary để rotate ID đúng cách.
6. Kiểm tra IdP/RP, cookie configuration và distributed session store.
7. Rà soát audit về session reuse và sensitive actions.
8. Nếu có nguy cơ bị chiếm quyền, đánh giá notification và các bước incident response theo chính sách.
9. Kiểm thử regression trên tất cả auth paths và nodes.
10. Theo dõi residual sessions sau triển khai vá.

### 22.2. Không chỉ đổi cookie name để chữa

Nếu code tiếp tục gắn authenticated principal vào pre-auth session identifier, đổi tên JSESSIONID sang APP_SESSION không giải quyết nguyên nhân.

### 22.3. Cẩn thận khi hủy tất cả sessions

Invalidate-all có thể làm người dùng bị đăng xuất, tác động vận hành. Tuy nhiên với lỗ hổng nghiêm trọng, containment có thể cần thiết. Quyết định theo severity, mức độ lộ và quyền của các phiên; có rollback và communication phù hợp.

### 22.4. Kiểm tra hành vi sau vá

Cần chứng minh với S0 old: không có quyền; với S1 new: có đúng quyền; sau logout S1 không còn quyền; sau Mover/Leaver quyền hiệu lực không vượt policy. Không đóng incident chỉ dựa vào việc deploy thành công.

## 23. Case study: Finance Portal dùng SSO và MFA

### 23.1. Bối cảnh

Doanh nghiệp có Finance Portal sau IdP dùng OIDC. Nhân viên An đăng nhập bằng SSO, MFA được yêu cầu cho export dữ liệu. Ứng dụng tạo anonymous session để lưu state trước redirect.

Mục tiêu thiết kế:

- Nạn nhân được bảo vệ khỏi session ID cố định trước login.
- RP kiểm tra OIDC state và token đúng hợp đồng.
- Phiên app mới được tạo sau authentication.
- Role finance.viewer/finance.export được phân quyền theo resource.
- Sau Leaver, RP sessions bị ngắt theo SLA.
- Audit có thể truy nguyên action mà không ghi session secret.

### 23.2. Luồng lỗi

~~~text
09:00  Browser vào /finance, có anonymous session S0
09:01  SSO redirect tới IdP
09:02  User xác thực và hoàn thành MFA
09:03  RP callback xác minh ID token
09:03  RP giữ session ID S0 và thêm principal=An   <-- LỖI
09:04  Một client khác dùng S0 để truy cập /reports/export
~~~

Nếu client khác đã biết S0 và request được server nhận như An, kết quả là session fixation exploit path.

### 23.3. Luồng đúng

~~~text
09:00  Anonymous session S0
09:02  IdP xác thực người dùng
09:03  RP verify state, issuer, audience, token profile
09:03  RP rotate/create session S1 và ràng buộc principal
09:03  Old S0 không tham chiếu authenticated principal
09:04  Client gửi S0 nhận unauthenticated/denied
09:04  Browser gửi S1 được xét RBAC/ABAC cho đúng report
~~~

### 23.4. Biến cố A: nhân viên chuyển phòng

Ngày hôm sau An không còn finance.export. Dù S1 còn active, API phải từ chối export theo role/entitlement mới. ID rotation tại login không thay authorization refresh khi Mover.

### 23.5. Biến cố B: account Leaver

HRIS ghi Leaver effectiveAt 17:00. Disable IdP có thể chặn login mới, nhưng portal vẫn có session nội bộ. IAM cần áp dụng revoke/logout propagation hoặc entitlement/status check đáp ứng SLA.

### 23.6. Biến cố C: portal chạy nhiều nodes

S0 trước login được lưu tại node A. Node B tiếp nhận callback và tạo S1. Test xác minh old S0 ở cả A/B không còn authenticated, kể cả khi Redis replication chậm hoặc browser gửi request đồng thời.

### 23.7. Điểm kiểm tra cuối

- ID sau auth khác ID pre-auth.
- OIDC state/nonce/callback validation đúng.
- Session old ID bị chặn tại resource API.
- Cookie có scope/flags phù hợp.
- MFA level và role không bị mượn qua old ID.
- Logout, Mover, Leaver và incident revoke có bằng chứng.

## 24. Những hiểu lầm thường gặp

**“ID session khó đoán thì không có fixation.”** Attacker có thể biết trước một ID hợp lệ do chính server phát mà không cần đoán.

**“HTTPS là đủ.”** HTTPS giảm nghe lén/injection đường truyền, nhưng không tự rotate ID khi login.

**“HttpOnly là đủ.”** HttpOnly giảm đọc cookie bằng script, không thay đổi authenticated ID mapping.

**“SameSite=Strict là giải pháp fixation.”** SameSite hỗ trợ cross-site request control, không thay session ID rotation.

**“Có CSRF token là không thể fixation.”** CSRF bảo vệ mục tiêu khác.

**“MFA chặn mọi chiếm quyền phiên.”** Nếu ID pre-auth đã biết tiếp tục được dùng sau MFA, rủi ro còn.

**“OIDC state đã xác minh nên RP session an toàn.”** State và ID rotation bảo vệ hai điều khác nhau.

**“Browser nhận cookie mới là đủ.”** Cần kiểm tra old ID không còn truy cập auth state ở server.

**“Session ID đổi bằng cách đổi cookie name.”** Cookie name không phải identifier được rotate.

**“Copy toàn bộ anonymous session là vô hại.”** Session attributes có thể chứa dữ liệu do attacker ảnh hưởng.

**“Đăng xuất xóa cookie là xong.”** Server phải invalidate hoặc revoke session/token phù hợp.

**“Disable IdP thì mọi SaaS session chết ngay.”** Không mặc định; cần xử lý session tại từng RP.

**“RBAC tốt thì không cần lo fixation.”** Nếu attacker dùng phiên victim, họ có thể có chính quyền victim.

**“Chỉ web form login mới có fixation.”** Custom OIDC/SAML callback hoặc tài khoản chuyển đổi cũng có thể xử lý session sai.

**“Stateless API luôn không bị chiếm quyền phiên.”** Không có server session fixation theo mẫu không đồng nghĩa token replay/theft được giải quyết.

**“Old ID được gửi lại nghĩa là chắc chắn có attacker.”** Có thể là tab/request retry; quan trọng là quyền old ID và bối cảnh.

**“Đổi ID mọi request càng an toàn.”** Rotation tùy tiện có thể gây race, mất state và lỗi ứng dụng; dùng đúng boundary.

## 25. Hướng dẫn đánh giá một hệ thống thực tế

Khi review một ứng dụng, không nên bắt đầu bằng giả định “có cookie SESSION là có fixation”. Thay vào đó, kiểm tra luồng **anonymous → authenticated → authorized → logout** trong boundary đã được phép.

### 25.1. Bước A — Xác định session mechanism

Câu hỏi:

- Phiên được lưu ở servlet session, Redis, database hay cookie chứa trạng thái?
- Ứng dụng dùng form login, OAuth/OIDC, SAML, reverse-proxy authentication hay nhiều loại?
- Có anonymous session trước login không?
- Cookie nào thực sự chọn authenticated principal?
- Có URL rewriting hoặc session token trong query/URL không?
- App chạy một node hay nhiều nodes?

**Đầu ra:** sơ đồ các session authorities và nơi ID được sinh/rotate/invalidated.

### 25.2. Bước B — Xác định trust transition

Ghi lại các điểm thay đổi:

~~~text
Anonymous --> Password authenticated
Password authenticated --> MFA completed
Normal user --> Privileged admin session
User A --> User B
Tenant A --> Tenant B
Authenticated --> Logged out
Active employee --> Mover / Leaver
~~~

Mỗi transition có yêu cầu khác nhau: có lúc phải rotate ID, có lúc cần reauthentication, có lúc cần refresh authorization, revoke hoặc tạo phiên mới. Không dùng một thao tác rotate để thay toàn bộ lifecycle policy.

### 25.3. Bước C — Đo old-ID behavior

Đối với test được ủy quyền:

1. Quan sát ID trước auth (nếu có).
2. Login qua từng luồng chính.
3. Quan sát ID sau auth.
4. Đảm bảo ID trước auth không được map tới principal đã đăng nhập.
5. Đánh giá trên tất cả nodes và session stores.
6. Logout và kiểm tra ID sau auth bị vô hiệu.
7. Test quyền khi Mover/Leaver hoặc grant revoked.

Không cần giữ lại raw IDs ngoài bộ nhớ test process. Báo cáo nên ghi PASS/FAIL và correlation IDs không nhạy cảm.

### 25.4. Bước D — Kiểm cookie và network boundary

Xem Set-Cookie thật qua HTTPS:

- Secure và HttpOnly đã có?
- SameSite phù hợp SSO flow?
- Cookie có Domain quá rộng không?
- Nếu dùng __Host-, đã có Secure/Path=/ và không có Domain?
- Cookie deletion có dùng đúng name/path/host scope?
- Có session ID trong URL, log hoặc analytics không?
- Proxy có phát sai cookie khi tin forwarded headers từ client không?

### 25.5. Bước E — Test authorization sau session transition

Sau khi xác nhận rotation:

- Request tới đúng tenant có đúng quyền.
- Request tới tenant khác bị từ chối.
- User bị thu hồi role không được dùng cached permission.
- MFA step-up không khiến session ID cũ được nâng privilege.
- RP session được chấm dứt theo Leaver policy.
- Audit đủ để chứng minh old ID không tiếp tục có quyền.

### 25.6. Báo cáo phát hiện cần cụ thể

Một finding hữu ích gồm:

| Thành phần | Ví dụ nội dung |
|---|---|
| Title | Authenticated session reuses pre-auth ID |
| Affected flow | OIDC callback của Finance Portal |
| Precondition | Browser có anonymous session hợp lệ |
| Observed behavior | Old ID vẫn map tới principal sau login |
| Expected behavior | ID thay đổi; old ID không có auth state |
| Business impact | Nguy cơ truy cập dưới quyền người đăng nhập |
| Severity factors | Admin scope, exploitability, session lifetime |
| Remediation | Session fixation protection + regression tests |
| Verification | Old/new ID checks trên mọi node |
| Evidence handling | Không lưu raw session cookie trong ticket |

Không ghi ID người dùng thực hoặc session token sản xuất vào báo cáo khi không cần thiết.

## 26. Các bài tập tình huống

### Bài tập A — Giỏ hàng cần giữ sau đăng nhập

Ứng dụng tạo session trước login để lưu giỏ hàng. Developer sợ mất giỏ nên giữ nguyên session ID sau login.

**Phân tích:** Dữ liệu giỏ hàng có thể cần được kiểm tra và chuyển sang session mới; không cần giữ ID cũ. Dùng cơ chế migration an toàn của framework, allowlist dữ liệu pre-auth và test S0 không còn authenticated.

### Bài tập B — SSO có MFA nhưng ứng dụng vẫn lỗi

IdP dùng MFA, OIDC callback xác minh ID token và state thành công. Tuy nhiên RP giữ anonymous session ID.

**Phân tích:** MFA và OIDC state giải quyết authentication/correlation, không thay session fixation defense tại RP. Rotate local session ID sau callback; old ID phải mất auth state.

### Bài tập C — App dùng cookie trên toàn domain

Finance portal và legacy upload app cùng dùng cookies trên domain cha. Upload app có lớp bảo vệ yếu hơn.

**Phân tích:** Rà cookie Domain/Path, cách browser xử lý cookie cùng tên, khả năng dùng host-only và __Host- prefix; kiểm tra session parser. Vẫn phải rotate ID sau login.

### Bài tập D — Spring Security đã cấu hình nhưng custom callback chưa an toàn

Team thấy cấu hình sessionFixation changeSessionId, nhưng login qua custom SSO callback không thực thi strategy.

**Phân tích:** Không kết luận dựa trên config text. Viết test cho callback thực, kiểm tra S0/S1 và old-ID outcome. Dùng framework-supported authentication flow thay tự gắn principal không qua security lifecycle.

### Bài tập E — User chuyển từ team Finance sang Ops

User đã login trước Mover. Session ID được rotate đúng lúc login nhưng cached Finance role còn sau Mover.

**Phân tích:** Đây là **authorization freshness/residual access** ngoài session fixation. Cần revoke entitlement, refresh policy/session hoặc terminate các phiên liên quan theo SLA, không chỉ rotate.

### Bài tập F — Logout chỉ xóa cookie

Ứng dụng trả cookie hết hạn nhưng session store vẫn giữ authenticated mapping.

**Phân tích:** Browser nạn nhân có thể không gửi cookie nữa, nhưng old ID bị biết trước vẫn có thể được dùng bởi client khác. Logout phải invalidate phía server và kiểm tra target/session controls.

### Bài tập G — Hai requests đồng thời lúc login

Request A và B đều dùng S0. A hoàn tất login và tạo S1; B đến node khác trong thời gian rất gần.

**Phân tích:** Server/store phải đảm bảo S0 không thể quan sát authenticated state. Test concurrency, shared store và consistency; không chỉ xác minh Set-Cookie S1 được phát.

### Bài tập H — M2M API dùng access token

Một service gửi OAuth access token tới API, không có anonymous browser session.

**Phân tích:** Không gắn nhãn mọi token replay là Session fixation. Hệ thống cần token verification, audience, issuer, scope, credential protection và revocation phù hợp, nhưng cách phòng ngừa khác mô hình giữ nguyên pre-auth session ID.

### Bài tập I — Cookie SameSite=Strict làm hỏng SSO

Team chuyển mọi cookies sang Strict, nhưng một số redirect/login flows không giữ được state.

**Phân tích:** Không đánh đổi chức năng bằng cấu hình cookie mù quáng. Kiểm tra flow cụ thể, lựa chọn SameSite hợp lệ và bảo vệ CSRF/correlation; vẫn bảo đảm ID rotation khi authentication hoàn tất.

### Bài tập J — Login lại account khác trên cùng browser

User A logout rồi login B. Server đổi tên hiển thị nhưng giữ authorization cache/tenant của A.

**Phân tích:** Có rủi ro principal/authorization confusion. Cần invalidate hoặc tách session state theo identity, rotate session ID, làm sạch attributes account-specific và reauthorize mọi resource.

## 27. Checklist triển khai Session fixation defense

1. **Inventory:** ứng dụng có server-side session, RP session, IdP session hay bearer tokens?
2. **Anonymous:** có tạo session trước login? Nó lưu những thuộc tính nào?
3. **Trust:** server có tin session ID do client tự chọn không?
4. **Rotation:** ID được đổi khi anonymous → authenticated?
5. **Invalidation:** old ID có còn map tới principal authenticated không?
6. **Framework:** có dùng session fixation protection chính thức?
7. **Custom authentication:** callback/form login đặc biệt vẫn đi qua strategy?
8. **ID entropy:** ID không dự đoán được, không chứa user/tenant/timestamp có nghĩa?
9. **Cookie scope:** không dùng Domain rộng nếu không cần?
10. **Prefix:** nếu dùng __Host-, đã thỏa Secure, Path=/, không Domain?
11. **Secure:** session cookie chỉ được gửi qua kênh an toàn?
12. **HttpOnly:** cookie tránh bị đọc bằng script khi thích hợp?
13. **SameSite:** tương thích SSO và có CSRF protection riêng?
14. **No URL tracking:** session ID không xuất hiện trong URL/bookmark/Referer?
15. **Proxy:** trusted Forwarded headers, canonical HTTPS origin?
16. **Store:** session old/new nhất quán trên mọi backend nodes?
17. **Race:** concurrent requests quanh login không mở quyền cho S0?
18. **Attributes:** không copy authz/identity data không tin cậy từ pre-auth?
19. **SSO:** RP rotation sau OIDC/SAML callback đã được test?
20. **OIDC:** state/nonce/PKCE đúng trách nhiệm, không thay rotation?
21. **MFA:** step-up được binding đúng principal/session/assurance?
22. **Role:** RBAC/ABAC được kiểm tra trên resource, không chỉ UI?
23. **Tenant:** session không đem tenant A access sang B sai quyền?
24. **Timeout:** có idle và absolute lifetime đúng policy?
25. **Logout:** server invalidate và browser clear cookie đúng scope?
26. **JML Joiner:** quyền không mở sớm trước ngày hiệu lực?
27. **JML Mover:** role cache được refresh/revoke đúng SLA?
28. **JML Leaver:** IdP và RP sessions được xử lý theo hệ thống?
29. **PAM:** admin/privileged sessions có step-up, JIT và time bound?
30. **Audit:** có evidence rotation/invalidation không chứa raw IDs?
31. **Monitoring:** old-ID authenticated reuse bị phát hiện/cảnh báo?
32. **Incident:** có chức năng revoke affected/all sessions theo policy?
33. **Tests:** S0/S1, OIDC, SAML, account switch, multi-node, logout được thử?
34. **Recovery:** failover/session-store outage không làm fail-open?
35. **Documentation:** owner, policy version, session lifecycle và expected behavior được ghi?
36. **Governance:** thay đổi login flow có regression test bắt buộc?

## 28. Tổng kết

**Session fixation** xuất hiện khi một session identifier đã được attacker biết hoặc có thể áp đặt **trước xác thực** tiếp tục được server sử dụng để nhận diện **phiên đã xác thực**. Lỗi nằm tại **ranh giới chuyển trạng thái tin cậy**, không chỉ ở cookie flags hay độ mạnh của mật khẩu.

Phòng ngừa cần phối hợp:

- **Rotate/create authenticated session ID mới** khi login thành công.
- **Làm mất hiệu lực ID pre-auth** đối với authenticated state ở mọi backend nodes.
- Dùng **cookie hardening** (Secure, HttpOnly, SameSite đúng ngữ cảnh, host-only và __Host- khi hỗ trợ).
- Kiểm soát **SSO/OIDC/SAML callback, MFA step-up, account switching và session attributes**.
- Xác minh **RBAC/ABAC, tenant boundary, grant freshness**, không chỉ trạng thái authenticated.
- **Invalidate phiên khi logout, Mover/Leaver/incident** theo SLA và khả năng của từng IdP/RP.
- Đo bằng **old/new-ID tests và bằng chứng server-side**, tránh log raw bearer secrets.

Trong IAM theo **Joiner–Mover–Leaver**, một danh tính được xác minh và cấp quyền đúng vẫn có thể gặp rủi ro nếu session lifecycle sai. Các hệ thống **IdP, SSO, SCIM, RBAC/ABAC, PAM và audit** cần phối hợp để quyền có hiệu lực đúng người, đúng phạm vi và không tồn dư sau khi thay đổi vai trò hoặc nghỉ việc.

**Ghi nhớ:** Không đủ để nói “đăng nhập đã thành công”. Phải bảo đảm **phiên sau đăng nhập không còn dùng identifier có thể đã bị biết trước** và **ID cũ không thể truy cập trạng thái authenticated**, đồng thời session/token/grants được thu hồi đúng khi không còn căn cứ.





