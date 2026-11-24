# Federation logout

## 1. Federation logout là gì?

**Federation logout (đăng xuất liên kết)** là quá trình kết thúc các phiên đăng nhập có liên quan giữa nhiều bên trong một hệ thống xác thực liên kết, thường gồm **Identity Provider (IdP/OpenID Provider - OP)** và một hoặc nhiều **Relying Party (RP)/ứng dụng dịch vụ**. Khi người dùng đăng xuất ở một bên, hệ thống có thể thông báo cho các bên còn lại để họ thu hồi session tương ứng.

Ví dụ: nhân viên đăng nhập cổng công ty bằng tài khoản tập trung, sau đó mở hệ thống nhân sự, quản lý chi phí và wiki nội bộ. Các ứng dụng này có thể tạo session riêng dù cùng dùng một IdP. Khi nhân viên chọn “Đăng xuất khỏi tài khoản công ty”, hệ thống cần xác định session nào phải kết thúc ở từng ứng dụng và liệu session IdP có cần đóng hay không.

**Đăng xuất khỏi một ứng dụng không mặc nhiên đăng xuất khỏi IdP hoặc mọi ứng dụng khác.** Mỗi RP thường có session cục bộ riêng; IdP cũng có session riêng trong browser. Federation logout là tập hợp giao thức và cơ chế phối hợp để kết thúc các session có liên quan.

| Thành phần | Phiên hoặc trách nhiệm |
| --- | --- |
| **IdP / OpenID Provider (OP)** | Xác thực người dùng và duy trì phiên đăng nhập tại nhà cung cấp danh tính. |
| **RP / Service Provider (SP)** | Tạo session cục bộ sau khi xác minh assertion hoặc token. |
| **Browser** | Mang cookie, điều hướng hoặc tải thông điệp logout trong front-channel. |
| **Back-channel endpoint** | Nhận thông điệp logout trực tiếp từ server của bên liên kết. |
| **Session registry** | Ánh xạ session cục bộ với subject, issuer và session identifier để thu hồi đúng phiên. |

Trong module `SECURITY_AUTHENTICATION_FUNDAMENTALS`, federation logout nối quá trình xác thực liên kết với vòng đời session: thông báo logout, thu hồi token, xử lý nhiều thiết bị và khôi phục khi một bên liên kết không phản hồi.

## 2. Vì sao logout liên kết khó hơn logout cục bộ?

Trong ứng dụng đơn lẻ, server có thể vô hiệu hóa session ID rồi xóa cookie trình duyệt. Trong federation, một lần đăng nhập có thể tạo nhiều trạng thái độc lập:

- Cookie/session tại IdP.
- Cookie/session tại từng RP.
- Access token và refresh token.
- Session trên thiết bị hoặc ứng dụng native.
- Cache session ở API gateway và dịch vụ phía sau.

Ví dụ, người dùng đăng xuất khỏi ứng dụng A. Nếu chỉ xóa cookie A, session IdP vẫn còn; khi truy cập lại A hoặc ứng dụng B, browser có thể được IdP xác thực im lặng và tạo session mới mà không yêu cầu nhập mật khẩu. Ngược lại, nếu IdP kết thúc session nhưng RP B chưa nhận được thông báo, B có thể tiếp tục chấp nhận session cục bộ cho đến khi hết hạn hoặc bị thu hồi.

Cần phân biệt:

1. **Local logout:** kết thúc session tại ứng dụng hiện tại.
2. **IdP/OP logout:** kết thúc session tại nhà cung cấp danh tính.
3. **Federated logout:** gửi hoặc nhận thông điệp để các bên liên kết kết thúc session tương ứng.
4. **Token revocation:** vô hiệu hóa refresh token hoặc token theo cơ chế được hỗ trợ.
5. **Device/global sign-out:** thu hồi nhiều session và thiết bị theo một phạm vi được định nghĩa.

Một nút “Sign out everywhere” cần có ngữ nghĩa rõ: mọi session của ứng dụng, mọi RP trong federation, mọi thiết bị hay cả token đã cấp? Không nên hứa phạm vi rộng hơn những gì hệ thống thực sự thực hiện.

## 3. Mô hình session trong federation

~~~mermaid
flowchart TD
    U["Người dùng / Browser"] --> OP["IdP / OpenID Provider"]
    OP -->|Authentication response / token| A["RP A"]
    OP -->|Authentication response / token| B["RP B"]
    OP -->|Authentication response / token| C["RP C"]
    A --> SA["Local session A"]
    B --> SB["Local session B"]
    C --> SC["Local session C"]
    OP --> SO["IdP session"]
    SO -. "Logout event" .-> A
    SO -. "Logout event" .-> B
    SO -. "Logout event" .-> C
~~~

Mỗi RP phải có cách ánh xạ thông điệp logout về session của chính mình. IdP không thể chỉ gửi thông báo “người dùng X logout” rồi giả định mọi session của X đều phải kết thúc: người dùng có thể có nhiều session, thiết bị hoặc browser khác nhau.

Các định danh có thể dùng để tương quan:

- **Subject/NameID:** xác định danh tính người dùng tại issuer.
- **Session ID / sid:** nhận diện một phiên tại IdP hoặc trong giao thức cụ thể.
- **SAML SessionIndex:** liên kết một phiên đăng nhập SAML với session ở SP.
- **RP local session ID:** mã phiên do ứng dụng tự tạo.

RP cần lưu ánh xạ phù hợp khi tạo session. Không dùng email làm khóa tương quan duy nhất nếu email có thể thay đổi, tái sử dụng hoặc không được issuer bảo đảm duy nhất. Nên dùng cặp issuer và subject ổn định, cùng session identifier khi giao thức cung cấp.

## 4. Các kiểu khởi tạo federation logout

### 4.1. RP-initiated logout

Người dùng chọn đăng xuất tại một ứng dụng. RP kết thúc session cục bộ rồi gửi yêu cầu logout tới IdP/OP để kết thúc hoặc điều phối session liên quan.

Đây là luồng thường gặp khi người dùng chọn nút “Đăng xuất” trong một ứng dụng. RP cần xử lý rõ trường hợp IdP không sẵn sàng hoặc browser không còn cookie IdP.

### 4.2. IdP-initiated logout

Người dùng đăng xuất trực tiếp tại IdP, hoặc IdP/quản trị viên yêu cầu kết thúc session. IdP gửi thông điệp tới các RP đã tham gia phiên đó để họ thu hồi session cục bộ.

Ví dụ: nhân viên bấm “Sign out” trên cổng tài khoản công ty. IdP thông báo cho ứng dụng nhân sự và wiki rằng session liên quan đã kết thúc.

### 4.3. Front-channel logout

Front-channel logout dùng browser làm trung gian. IdP điều hướng browser hoặc tải các trang/iframe logout của các RP. RP nhận thông điệp trong ngữ cảnh trình duyệt rồi kết thúc session hoặc cookie phù hợp.

Ưu điểm là tận dụng browser để liên lạc với nhiều RP mà không yêu cầu IdP có kết nối mạng trực tiếp tới từng RP. Hạn chế là việc gửi cookie phụ thuộc chính sách cookie, browser privacy, third-party cookie blocking, iframe, tab đang đóng và mạng. Vì vậy, front-channel logout có thể không đến được mọi RP hoặc không hoàn tất như mong đợi.

### 4.4. Back-channel logout

Back-channel logout gửi thông điệp trực tiếp từ server IdP tới endpoint của RP qua kênh server-to-server. Browser không cần tham gia để chuyển thông điệp.

Ưu điểm là ít phụ thuộc third-party cookie và trạng thái browser. Hạn chế là cần endpoint có thể truy cập, xác minh issuer/chữ ký, quản lý retry, timeout, replay và tính sẵn sàng giữa các tổ chức.

| Cách thức | Kênh | Rủi ro vận hành chính |
| --- | --- | --- |
| RP-initiated | RP điều hướng hoặc gọi IdP/OP | Redirect URI, tương quan request, cookie IdP và trạng thái phiên. |
| IdP-initiated | IdP gửi thông điệp tới RP | Xác minh thông điệp, ánh xạ đúng session, xử lý lặp. |
| Front-channel | Browser điều hướng/iframe giữa các bên | Cookie bị chặn, browser đóng, mạng và giới hạn third-party context. |
| Back-channel | Server-to-server | Endpoint, xác thực thông điệp, timeout, retry và replay protection. |

Front-channel và back-channel có thể cùng tồn tại. Chúng không phải lựa chọn tương đương trong mọi môi trường; cần chọn theo giao thức, loại client, mức bảo đảm và khả năng triển khai.

## 5. Logout trong SAML 2.0

Trong SAML 2.0, **Single Logout (SLO)** cho phép một bên yêu cầu các bên liên quan kết thúc session. Thông điệp chính gồm `LogoutRequest` và `LogoutResponse`.

Một `LogoutRequest` thường xác định issuer, subject/NameID và có thể chứa `SessionIndex` để chỉ ra phiên cụ thể. Thông điệp cũng có thể mang destination, thời điểm và chữ ký theo binding/profile áp dụng. SP/IdP nhận thông điệp phải kiểm tra nguồn gửi, chữ ký, đối tượng và session được chỉ định trước khi thực hiện logout.

~~~mermaid
sequenceDiagram
    participant U as Browser
    participant SP as Service Provider
    participant IdP as Identity Provider
    U->>SP: Chọn đăng xuất
    SP->>SP: Xác định NameID và SessionIndex
    SP->>IdP: SAML LogoutRequest
    IdP->>IdP: Xác minh issuer, chữ ký và session
    IdP->>IdP: Kết thúc session IdP
    IdP-->>SP: SAML LogoutResponse
    IdP-->>U: Điều phối logout tới SP liên quan (nếu cấu hình)
    SP->>SP: Kết thúc session cục bộ
    SP-->>U: Trang đăng xuất
~~~

Đây là luồng khái niệm; thứ tự điều phối và vai trò của browser phụ thuộc binding và profile được triển khai. SAML SLO có thể sử dụng các binding như HTTP Redirect, HTTP POST hoặc SOAP trong cấu hình tương ứng.

### 5.1. SessionIndex và logout đúng phiên

Một người dùng có thể đăng nhập cùng SP trên nhiều browser hoặc nhiều thiết bị. Nếu SP chỉ xóa mọi session theo NameID, một logout có thể vô tình kết thúc tất cả session của người dùng dù chỉ yêu cầu kết thúc một phiên.

Khi có `SessionIndex`, SP nên lưu nó cùng session cục bộ để ánh xạ `LogoutRequest` đến đúng phiên. Nếu giao thức hoặc IdP không cung cấp SessionIndex, chính sách xử lý nhiều phiên phải được thống nhất rõ giữa các bên.

### 5.2. Xác minh SAML LogoutRequest

Không nên kết thúc session chỉ vì nhận một XML có `NameID` hoặc `SessionIndex`. RP/SP cần kiểm tra theo profile SAML đã thỏa thuận:

- Issuer thuộc IdP được tin cậy và đúng đối tác đã cấu hình.
- Chữ ký XML hợp lệ theo trust configuration, certificate/key được phép và quy tắc signature wrapping được thư viện xử lý an toàn.
- Destination/endpoint và binding phù hợp.
- Thời điểm và điều kiện hiệu lực của thông điệp hợp lệ.
- NameID và SessionIndex ánh xạ tới session của đúng issuer.
- Request ID/correlation được xử lý theo quy tắc giao thức để chống nhầm hoặc replay.

Nên dùng thư viện SAML được duy trì, cấu hình kiểm tra chữ ký và XML an toàn. Không tự parse XML rồi chỉ so sánh vài trường trước khi xóa session.

## 6. Logout trong OpenID Connect

OAuth 2.0 core không tự định nghĩa một giao thức logout chung cho mọi authorization server. **OpenID Connect (OIDC)** bổ sung các cơ chế liên quan đến logout, trong đó có RP-Initiated Logout và các cơ chế front-channel/back-channel logout.

### 6.1. RP-Initiated Logout

RP có thể điều hướng user agent tới `end_session_endpoint` của OP. Yêu cầu thường có thể bao gồm:

- `id_token_hint`: ID Token trước đó để OP nhận diện session/subject liên quan.
- `post_logout_redirect_uri`: URI quay về sau khi logout, phải được đăng ký hoặc cho phép theo chính sách OP.
- `state`: giá trị do RP tạo để tương quan phản hồi và bảo vệ trạng thái luồng quay về.

Các tham số cụ thể và yêu cầu kiểm tra phụ thuộc OIDC specification và cấu hình OP. RP không nên tự nối URL logout tùy ý hoặc chấp nhận post-logout redirect từ input không tin cậy.

~~~mermaid
sequenceDiagram
    participant U as Browser
    participant RP as Relying Party
    participant OP as OpenID Provider
    U->>RP: Chọn logout
    RP->>RP: Thu hồi local session và chuẩn bị state
    RP-->>U: Redirect tới end_session_endpoint
    U->>OP: Logout request + id_token_hint (nếu dùng)
    OP->>OP: Kiểm tra request và session OP
    OP->>OP: Kết thúc session OP theo policy
    OP-->>U: Redirect về post_logout_redirect_uri hợp lệ
    U->>RP: Trang xác nhận logout + state
~~~

Việc OP kết thúc session không đảm bảo mọi RP khác đã thu hồi session cục bộ. Nếu OP hỗ trợ back-channel hoặc front-channel logout, RP cần đăng ký endpoint và triển khai xử lý thông điệp tương ứng.

### 6.2. OIDC Back-Channel Logout

Trong back-channel logout, OP gửi một **Logout Token** tới back-channel logout URI đã đăng ký của RP. Logout Token là JWT được ký, chứa các claim để RP xác định issuer, audience, thời điểm, sự kiện logout và session/subject liên quan.

RP cần xác minh theo đặc tả:

- Chữ ký và thuật toán bằng khóa tin cậy của issuer; không chấp nhận thuật toán tùy ý.
- `iss` đúng OP được cấu hình.
- `aud` bao gồm client ID của RP.
- `iat` hợp lệ theo chính sách thời gian.
- `events` chứa sự kiện back-channel logout đúng URI chuẩn.
- Có `sid` hoặc `sub` theo yêu cầu đặc tả để xác định phạm vi session.
- `jti` được dùng để nhận diện token và hỗ trợ phát hiện replay.
- Không dùng token có `nonce` như một ID Token đăng nhập thông thường.

Sau khi xác minh, RP tìm các session gắn với issuer và `sid` hoặc subject tương ứng rồi thu hồi theo quy tắc. Nếu chỉ có subject mà không có sid, phạm vi logout có thể rộng hơn và phải tuân theo semantics của profile.

### 6.3. OIDC Front-Channel Logout

Trong front-channel logout, OP sử dụng browser để tải logout URI của các RP, thường qua iframe. RP nhận yêu cầu và kết thúc session liên quan.

Do browser có thể chặn third-party cookie hoặc hạn chế iframe, RP không nên giả định front-channel logout luôn thành công. Cần có session timeout, kiểm tra trạng thái khi cần, back-channel logout nếu phù hợp và cơ chế thu hồi phía server.

## 7. Thu hồi session và token sau logout

Logout không chỉ là xóa cookie ở browser. Một quy trình server-side cần:

1. Xác định session hiện tại và đánh dấu không còn hiệu lực trong session store.
2. Xóa hoặc thay cookie ở browser với cùng tên, Path và Domain phù hợp, kèm expiry trong quá khứ hoặc `Max-Age=0`.
3. Thu hồi refresh token hoặc token có thể thu hồi theo cơ chế của issuer.
4. Xử lý access token đã cấp: token opaque có thể được introspect; JWT access token tự chứa có thể vẫn hợp lệ tới khi hết hạn nếu resource server không kiểm tra trạng thái thu hồi hoặc denylist.
5. Xóa cache session/token ở gateway và dịch vụ phụ trợ nếu chúng duy trì trạng thái riêng.
6. Ghi audit event về logout và phạm vi đã thu hồi mà không ghi token/cookie bí mật.

Ví dụ xóa cookie:

~~~http
Set-Cookie: __Host-SessionID=; Path=/; Max-Age=0; Secure; HttpOnly; SameSite=Lax
~~~

Cookie phải được xóa với đúng phạm vi cookie đã tạo. Nếu cookie ban đầu có Domain hoặc Path khác, một header xóa với phạm vi không khớp có thể để lại cookie cũ.

### 7.1. Access token tự chứa không biến mất chỉ vì browser logout

Một JWT access token đã được phát hành có thể tiếp tục được resource server chấp nhận tới `exp` nếu resource server chỉ xác minh chữ ký và claim tĩnh. Xóa cookie browser hoặc đóng session RP không tự làm token đó vô hiệu.

Các lựa chọn giảm thời gian tồn tại:

- Access token có thời hạn ngắn.
- Refresh token được thu hồi khi logout.
- Introspection hoặc session/token state được kiểm tra tại resource server.
- Denylist theo token ID hoặc session ID khi kiến trúc cần thu hồi tức thời.
- Sender-constrained token nếu hệ sinh thái hỗ trợ.

Không nên tuyên bố logout đã thu hồi mọi token nếu resource server vẫn chấp nhận access token tự chứa cho tới khi hết hạn.

## 8. Xử lý logout thất bại và bên liên kết không phản hồi

Một IdP có thể không liên lạc được với một RP do mạng lỗi, endpoint tắt, timeout hoặc RP đang bảo trì. Front-channel cũng có thể không chạy được vì browser chặn cookie/iframe. Federation logout cần xác định rõ cách xử lý lỗi:

- **Kết thúc local session trước:** khi người dùng yêu cầu logout khỏi ứng dụng, ứng dụng nên vô hiệu hóa session cục bộ ngay để không tiếp tục cấp quyền trong lúc chờ IdP.
- **Gửi thông báo có kiểm soát:** IdP/RP có thể retry theo chính sách, dùng request ID hoặc `jti` để nhận diện thông điệp lặp.
- **Xử lý idempotent:** nhận lại cùng logout message không được gây lỗi hoặc tạo side effect không mong muốn; nếu session đã kết thúc, trả kết quả phù hợp.
- **Không mở lại session:** lỗi khi gửi logout không được khiến session đã bị thu hồi sống lại.
- **Ghi nhận trạng thái từng RP:** hệ thống có thể báo logout đã hoàn tất ở RP nào và bên nào chưa xác nhận, nếu UX cần thông tin chi tiết.
- **Giới hạn retry:** tránh retry vô hạn gây tải hoặc khuếch đại sự cố.

Logout phân tán không thể bảo đảm mọi hệ thống bên ngoài cùng kết thúc session trong đúng một thời điểm. Thiết kế cần nêu rõ mức bảo đảm, thời gian lan truyền và hành vi khi một RP không phản hồi.

## 9. Bảo vệ endpoint và thông điệp logout

Logout message là một thao tác bảo mật có thể làm mất quyền truy cập. Attacker có thể lợi dụng endpoint logout để ép người dùng bị đăng xuất liên tục (logout denial of service), hoặc giả thông điệp để kết thúc session của người khác.

Các kiểm soát cần thiết:

1. Xác minh issuer, chữ ký, audience/destination và giao thức theo profile.
2. Ràng buộc thông điệp với đúng session/subject, không xóa mọi session chỉ từ email hoặc username.
3. Kiểm tra thời gian, request correlation và replay identifier.
4. Chỉ nhận back-channel message qua endpoint đã đăng ký; bảo vệ TLS và xác thực đối tác theo profile.
5. Với local logout do browser khởi tạo, bảo vệ CSRF và không để website khác ép logout ngoài chính sách.
6. Kiểm soát post-logout redirect bằng allowlist/URI đăng ký để tránh open redirect.
7. Không tiết lộ session tồn tại hay không qua phản hồi quá chi tiết cho bên không được tin cậy.
8. Giới hạn kích thước và tốc độ request; dùng thư viện xử lý JWT/XML an toàn.

Không nên coi logout endpoint là endpoint không nhạy cảm chỉ vì nó không cấp quyền. Một thông điệp logout giả có thể gây gián đoạn hoạt động hoặc phá phiên của nhiều người dùng.

## 10. Federation logout trong hệ thống nhiều RP

Một IdP có thể phục vụ hàng chục hoặc hàng trăm RP. Khi một session IdP kết thúc, OP có thể phải gửi logout tới nhiều bên. Thiết kế cần giải quyết:

- **Session mapping:** IdP lưu RP/client nào đã tham gia session và session identifier tương ứng.
- **Fan-out:** gửi thông điệp tới nhiều RP mà không để một endpoint chậm chặn toàn bộ quá trình.
- **Retry và deduplication:** gửi lại khi lỗi nhưng RP phải nhận diện thông điệp đã xử lý.
- **Partial failure:** một RP có thể offline; hệ thống ghi nhận trạng thái và retry có giới hạn.
- **Tenant isolation:** session của một tenant không được tác động session của tenant khác dù subject hoặc email giống nhau.
- **Privacy:** không gửi thêm thuộc tính cá nhân không cần thiết trong logout message.
- **Operational visibility:** đo thời gian lan truyền logout, tỷ lệ endpoint lỗi và số session còn hoạt động sau yêu cầu.

~~~mermaid
flowchart TD
    U["Người dùng logout tại OP"] --> OP["OP kết thúc IdP session"]
    OP --> Q["Tạo logout events cho các RP liên quan"]
    Q --> A["RP A: nhận và thu hồi session"]
    Q --> B["RP B: nhận và thu hồi session"]
    Q --> C["RP C: timeout / unavailable"]
    C --> R["Retry có giới hạn + ghi trạng thái lỗi"]
    A --> D["Kết quả theo từng RP"]
    B --> D
    R --> D
~~~

Với hệ thống quan trọng, có thể cần thêm cơ chế kiểm tra session khi sử dụng, token introspection hoặc thời hạn session ngắn để giảm cửa sổ khi thông điệp logout không đến được một RP.

## 11. Ví dụ thiết kế: đăng xuất khỏi cổng doanh nghiệp

Một nhân viên đăng nhập vào cổng doanh nghiệp qua OIDC. Cổng tạo session riêng và người dùng cũng đang có session ở wiki, hệ thống nhân sự và ứng dụng chi phí.

**Khi người dùng chọn logout tại cổng:**

1. Cổng xác thực yêu cầu logout của chính session hiện tại, bảo vệ CSRF cho thao tác do browser khởi tạo.
2. Cổng đánh dấu local session hết hiệu lực và xóa cookie bằng đúng Path/Domain/Secure attributes.
3. Cổng gửi RP-Initiated Logout tới OP với `id_token_hint`, `post_logout_redirect_uri` đã đăng ký và `state` tương quan.
4. OP kết thúc session IdP theo chính sách và điều phối thông điệp logout tới các RP đã đăng ký.
5. Wiki, HR và chi phí xác minh Logout Token/back-channel hoặc thông điệp front-channel theo profile, tìm đúng session và thu hồi.
6. Nếu wiki tạm thời không phản hồi, OP ghi nhận lỗi và retry theo chính sách. Cổng vẫn giữ local session đã kết thúc.
7. Nếu access token tự chứa còn hiệu lực, API resource server áp dụng TTL ngắn hoặc cơ chế kiểm tra trạng thái/revocation theo yêu cầu bảo mật.

**Khi nhân viên đăng xuất tại OP trực tiếp:** OP phát sự kiện tới các RP; mỗi RP thu hồi session tương ứng. Khi nhân viên quay lại cổng, nếu OP session đã kết thúc thì họ cần xác thực lại theo policy.

Ví dụ này giả định các bên đã đăng ký logout endpoint và chia sẻ cấu hình tin cậy. Chỉ có chung một IdP không tự đảm bảo SLO được bật hoặc mọi RP hỗ trợ cùng một kiểu logout.

## 12. Các lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Xóa cookie RP rồi gọi đó là global logout | Session IdP và các RP khác vẫn còn. | Nêu rõ local/federated/global scope; dùng cơ chế SLO phù hợp. |
| Chỉ logout IdP nhưng không thu hồi local session | RP vẫn chấp nhận session cục bộ. | Nhận logout message và thu hồi session ở RP. |
| Tin front-channel luôn chạy thành công | Browser có thể chặn iframe/cookie hoặc đóng tab. | Dùng back-channel khi phù hợp, session expiry và kiểm tra trạng thái. |
| Chấp nhận logout message không xác minh | Attacker có thể kết thúc session của người khác. | Kiểm tra issuer, chữ ký, audience/destination và session mapping. |
| Xóa mọi session của subject khi chỉ yêu cầu một phiên | Đăng xuất nhầm thiết bị/phiên khác. | Dùng SessionIndex hoặc sid khi có; định nghĩa phạm vi rõ. |
| Bỏ qua replay/correlation | Thông điệp lặp hoặc sai flow gây xử lý không đúng. | Kiểm tra request ID/jti, thời gian và xử lý idempotent. |
| Chấp nhận post-logout redirect tùy ý | Open redirect hoặc chuyển người dùng tới website giả. | Chỉ redirect tới URI đã đăng ký/allowlist. |
| Nghĩ access token JWT hết hiệu lực ngay khi logout | Resource server có thể tiếp tục chấp nhận token tới exp. | TTL ngắn, revoke/introspection/denylist phù hợp. |
| Logout thất bại làm local session tiếp tục hoạt động | Người dùng vẫn ở trong ứng dụng dù đã chọn logout. | Thu hồi local session trước, xử lý liên kết độc lập. |
| Không lưu ánh xạ IdP session với RP session | Không biết phải thu hồi phiên nào. | Lưu issuer, subject, sid/SessionIndex và local session mapping. |
| Dùng email làm khóa session duy nhất | Nhầm tài khoản, tenant hoặc email thay đổi. | Dùng issuer + subject ổn định và session identifier. |
| Không quan sát trạng thái fan-out | Không biết RP nào chưa logout. | Audit, metric, retry có giới hạn và xử lý partial failure. |

## 13. Checklist triển khai federation logout

Trước khi bật SLO, hãy kiểm tra:

1. **Ngữ nghĩa:** logout hiện tại là local, IdP, RP, federated hay global? Người dùng được thông báo chính xác phạm vi nào?
2. **Session mapping:** RP có lưu issuer, subject, sid/SessionIndex và local session ID cần thiết không?
3. **Protocol:** hệ thống dùng SAML SLO, OIDC RP-Initiated Logout, front-channel hay back-channel? Các bên có hỗ trợ cùng profile không?
4. **Message verification:** chữ ký, issuer, audience/destination, thời gian, correlation và replay identifier có được xác minh không?
5. **Scope:** thông điệp kết thúc đúng session/thiết bị/subject theo semantics, không xóa nhầm session khác không?
6. **Local logout:** session cục bộ có bị vô hiệu hóa ngay và cookie có được xóa với đúng Path/Domain không?
7. **Token lifecycle:** refresh token và access token được thu hồi hoặc giới hạn thời gian còn hiệu lực thế nào?
8. **Browser behavior:** front-channel có xét third-party cookie blocking, iframe restrictions và điều hướng không?
9. **Back-channel:** endpoint có TLS, xác minh issuer, timeout, retry, deduplication và idempotency không?
10. **Failure handling:** RP không phản hồi có làm local session sống lại không? Có trạng thái partial failure và retry giới hạn không?
11. **CSRF/open redirect:** local logout được bảo vệ và post-logout redirect chỉ dùng URI được phép không?
12. **Monitoring:** có log logout request/response, tỷ lệ thành công, thời gian lan truyền và lỗi theo RP mà không ghi token/session secret không?
13. **Testing:** đã kiểm thử logout từ RP và IdP, nhiều browser/device, session song song, replay, chữ ký sai, endpoint offline và access token còn hạn chưa?

**Kết luận:** Federation logout phối hợp việc kết thúc session giữa IdP/OP và các RP, nhưng mỗi bên vẫn quản lý trạng thái phiên riêng. SAML SLO và OIDC logout cung cấp cách trao đổi thông điệp qua front-channel hoặc back-channel; RP phải xác minh thông điệp, ánh xạ đúng session và thu hồi token/session theo chính sách. Vì browser, mạng và các RP có thể không phản hồi đồng thời, hệ thống cần xử lý partial failure, retry và idempotency rõ ràng, đồng thời không tuyên bố global logout nếu chỉ mới kết thúc session cục bộ.
