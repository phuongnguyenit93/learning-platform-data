# Logout failure — Xử lý đăng xuất thất bại và thu hồi phiên đáng tin cậy

> **Chương:** Đăng xuất  
> **Chủ đề:** Logout failure  
> **Phạm vi:** Bài học thuộc module SECURITY_AUTHENTICATION_FUNDAMENTALS, tìm hiểu nguyên lý xác thực danh tính từ credential, mật khẩu, MFA, passkey và chứng chỉ đến token, phiên, liên kết danh tính và khôi phục tài khoản. Bài này phân tích các nguyên nhân khiến đăng xuất không hoàn tất, phân biệt xóa trạng thái phía client với thu hồi trạng thái phía server, xử lý lỗi giữa nhiều service/IdP, và thiết kế retry, idempotency, audit cùng kiểm thử để bảo đảm credential phiên cũ không tiếp tục được chấp nhận.

## 1. Logout failure là gì?

**Logout failure (đăng xuất thất bại)** xảy ra khi một phần hoặc toàn bộ trạng thái xác thực vẫn có thể được sử dụng sau khi người dùng yêu cầu đăng xuất, hoặc giao diện thông báo đã đăng xuất trong khi server chưa thực sự vô hiệu phiên và credential liên quan.

Ví dụ, Mai bấm “Đăng xuất” trên cổng học tập. Trình duyệt xóa cookie session, nhưng server không nhận được request revoke do mạng bị ngắt. Một bản sao cookie đã bị đánh cắp trước đó vẫn còn hiệu lực ở máy khác. Nếu server chỉ dựa vào cookie browser đã xóa để kết luận logout hoàn tất, phiên bị đánh cắp vẫn có thể truy cập.

Đăng xuất thường liên quan nhiều trạng thái: cookie ở browser, session record ở server, access/refresh token, cache ở nhiều instance, phiên tại Identity Provider (IdP), các phiên ở ứng dụng liên kết (Relying Party/Service Provider) và thiết bị khác. Một bước thành công không đồng nghĩa mọi trạng thái đều đã được thu hồi.

**Mục tiêu bảo mật của local logout là làm cho server từ chối session hiện tại ở các request tiếp theo.** Nếu người dùng chọn logout all devices hoặc logout SSO, hệ thống còn cần xử lý những phiên và token khác trong phạm vi đã công bố.

### Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt xóa cookie, revoke server-side session, revoke token và Single Logout.
2. Nhận diện các dạng logout failure ở browser, backend, token service, cache và IdP.
3. Thiết kế logout endpoint an toàn, idempotent và chống CSRF.
4. Xử lý partial failure, retry, timeout và kết quả không xác định.
5. Bảo đảm revocation lan truyền giữa nhiều instance và region.
6. Phân biệt local logout, logout một thiết bị, logout all devices và logout federation.
7. Xử lý race condition với request đang chạy và cache/session replica.
8. Thiết kế audit, UX, recovery và test cho các tình huống lỗi.

## 2. Logout có nhiều phạm vi

Trước khi đánh giá thành công hay thất bại, cần xác định người dùng yêu cầu đăng xuất ở phạm vi nào.

| Phạm vi | Ý nghĩa | Trạng thái cần xử lý |
| --- | --- | --- |
| **Local logout** | Đăng xuất khỏi ứng dụng hiện tại | Local session, cookie và token do ứng dụng quản lý. |
| **Logout current device/session** | Thu hồi phiên đang dùng trên thiết bị hiện tại | Một session record và credential tham chiếu tới phiên đó. |
| **Logout all devices** | Thu hồi mọi phiên của account | Tất cả session, refresh token family và credential phiên liên quan. |
| **IdP logout** | Kết thúc phiên tại Identity Provider | IdP session và cookie thuộc miền IdP. |
| **Single Logout (SLO)** | Phối hợp đăng xuất giữa IdP và các RP/SP | Các phiên liên quan ở nhiều hệ thống theo giao thức hỗ trợ. |
| **Revoke token** | Vô hiệu token cụ thể hoặc token family | Access/refresh token theo cơ chế của authorization server. |

Một nút “Đăng xuất” thường có nghĩa local logout. Không được quảng bá local logout như logout khỏi mọi ứng dụng nếu hệ thống không thực hiện hoặc không thể xác nhận điều đó.

### Cam kết cần nói rõ

- “Đăng xuất khỏi ứng dụng này” nghĩa local session đã bị revoke.
- “Đăng xuất thiết bị này” cần xác định session nào thuộc thiết bị đó.
- “Đăng xuất khỏi mọi thiết bị” cần revoke toàn bộ session/token trong phạm vi account.
- “Đăng xuất khỏi tài khoản trường/doanh nghiệp” có thể cần IdP logout và SLO; RP không thể tự xóa cookie thuộc domain của IdP.

## 3. Phân biệt xóa cookie và thu hồi session

Hai thao tác này giải quyết hai phía khác nhau:

- **Xóa cookie ở client:** browser ngừng gửi cookie trong các request tiếp theo từ browser đó.
- **Thu hồi session ở server:** server đánh dấu session không còn active và từ chối mọi request sử dụng session ID đó, kể cả bản sao bị đánh cắp.

Ví dụ lỗi phổ biến:

~~~text
Browser A: có cookie session S1
Attacker B: đã sao chép cookie S1

Mai bấm logout:
  Browser A xóa cookie S1

Attacker B gửi lại S1:
  Server vẫn tìm thấy session S1 = ACTIVE
  -> Request vẫn được chấp nhận
~~~

Do đó, local logout cần revoke server-side record. Xóa cookie là bước dọn trạng thái ở browser, không thay thế revoke.

### Cookie phải được xóa đúng scope

Để browser xóa cookie, response cần dùng tên, Path và Domain phù hợp với cookie đã tạo; các thuộc tính khác nên nhất quán theo cấu hình. Ví dụ:

~~~http
Set-Cookie: __Host-app_session=; Path=/; Secure; HttpOnly; SameSite=Lax; Max-Age=0
~~~

Nếu cookie ban đầu được tạo với một Path/Domain khác, một lệnh xóa không khớp có thể để cookie cũ tồn tại. Với cookie prefix `__Host-`, Domain không được đặt và Path phải là `/` theo quy tắc của prefix.

Không dựa vào việc browser báo đã xóa cookie để kết luận server session đã bị thu hồi.

## 4. Các dạng logout failure thường gặp

| Dạng lỗi | Triệu chứng | Nguy cơ |
| --- | --- | --- |
| Client không gửi request | Browser đóng tab, script lỗi hoặc offline | Server session còn active. |
| Server không xử lý revoke | Timeout, exception hoặc database unavailable | Cookie bị xóa nhưng session vẫn dùng được ở nơi khác. |
| Cookie không bị xóa | Sai Path/Domain, response bị chặn hoặc nhiều cookie trùng tên | Browser tiếp tục gửi cookie. |
| Cache chưa invalidated | Instance A revoke, instance B còn cache active | Session tiếp tục được chấp nhận ở instance khác. |
| Refresh token chưa revoke | Local session kết thúc nhưng client còn xin access token mới | Truy cập API tiếp tục qua token. |
| IdP/SLO không phản hồi | IdP offline hoặc RP không nhận logout event | Phiên ở miền khác còn tồn tại. |
| Logout message giả/không hợp lệ | Endpoint nhận thông điệp không xác minh | Attacker có thể revoke nhầm phiên hoặc tạo DoS. |
| Race với request đang chạy | Request đã qua authentication tiếp tục commit sau logout | Side effect xảy ra sau khi người dùng đăng xuất. |
| Giao diện báo thành công quá sớm | UI chuyển về trang login trước khi server xác nhận | Người dùng tưởng đã revoke nhưng server chưa làm. |
| Browser cache/BFCache | Trang nhạy cảm vẫn hiện khi bấm Back | Nội dung cũ còn hiển thị dù session đã revoke. |

Một hệ thống cần xác định failure mode và trạng thái sau mỗi bước, thay vì chỉ trả một HTTP 200/500 chung chung.

## 5. Trình tự local logout an toàn

Một flow local logout có thể gồm:

1. Nhận yêu cầu logout qua endpoint có kiểm tra CSRF nếu cookie tự động được gửi.
2. Xác định session hiện tại từ cookie và tra trạng thái ở server.
3. Kiểm tra session/account context và quyền thực hiện thao tác.
4. Revoke session ở nguồn trạng thái có thẩm quyền.
5. Revoke refresh token hoặc token family liên quan nếu ứng dụng quản lý.
6. Phát response xóa cookie với đúng scope.
7. Ghi audit event không chứa raw session secret.
8. Trả trạng thái logout đã được server xác nhận.
9. Điều hướng browser về trang public/login.

~~~mermaid
sequenceDiagram
    participant B as Browser
    participant A as Application
    participant S as Session Store
    participant T as Token Service
    B->>A: POST /logout + CSRF token + session cookie
    A->>A: Validate request and resolve session
    A->>S: Revoke local session
    S-->>A: Revocation committed
    A->>T: Revoke linked refresh token (if applicable)
    T-->>A: Revocation result
    A-->>B: Expire session cookie + logout status
    B->>A: Request with old cookie (if copied)
    A->>S: Resolve session status
    S-->>A: REVOKED
    A-->>B: Reject / redirect to login
~~~

Thứ tự cụ thể có thể thay đổi tùy transaction boundary. Nhưng server phải bảo đảm local session không còn được chấp nhận trước khi tuyên bố local logout đã hoàn tất. Việc gọi IdP logout có thể là bước tiếp theo hoặc workflow riêng; không nên để IdP unavailable làm local session tiếp tục active.

## 6. Logout endpoint cần chống CSRF

Vì browser tự gửi session cookie, attacker có thể dụ người dùng gửi request logout từ một website khác. Đây thường là logout CSRF. Nó có thể gây gián đoạn hoặc tạo điều kiện cho login CSRF/account confusion trong một số flow.

Kiểm soát:
- dùng POST hoặc phương thức thay đổi trạng thái phù hợp; không dùng GET để revoke;
- kiểm tra CSRF token gắn với session hoặc transaction;
- kiểm tra Origin/Referer theo policy;
- cấu hình SameSite phù hợp nhưng không coi đó là lớp duy nhất;
- không dùng URL logout có token bí mật dễ bị log/referrer leak;
- với logout all devices, yêu cầu xác nhận hoặc step-up nếu policy quy định.

Logout CSRF thường không trực tiếp chiếm account, nhưng vẫn là một hành động có side effect. Endpoint phải được thiết kế rõ và có thể audit.

## 7. Idempotency: logout có thể được gọi nhiều lần

Browser có thể retry do timeout, người dùng bấm nút nhiều lần hoặc một logout event được gửi lại. Logout nên có tính **idempotent**: gọi lại không làm trạng thái trở nên sai hoặc kích hoạt hành động phụ ngoài ý muốn.

Ví dụ:
- Session đang ACTIVE → chuyển REVOKED.
- Session đã REVOKED → trả kết quả tương đương đã đăng xuất.
- Session không tồn tại → không tạo session mới; có thể trả thông báo public trung tính.
- Logout event đã xử lý → không xử lý side effect lần hai.

Idempotency không có nghĩa bỏ qua xác minh. Với SLO, vẫn phải xác minh issuer, signature, audience, session mapping và replay policy trước khi áp dụng event. Chỉ sau khi xác minh mới xử lý lặp theo cách idempotent.

### Response không tiết lộ session tồn tại

Đối với client, có thể trả cùng kết quả “đã đăng xuất” khi session đã revoked hoặc không còn tồn tại, tránh lộ session ID hợp lệ. Internal audit vẫn có thể phân biệt reason code.

## 8. Timeout và kết quả không xác định

Một request logout có thể timeout ở client trong khi server đã commit revoke. Hoặc server có thể timeout khi gọi session store mà không biết thao tác đã commit hay chưa.

Đây là **ambiguous outcome**: client không biết thao tác đã thành công hay chưa.

Cách xử lý:
- thiết kế revoke idempotent;
- retry cùng session reference hoặc operation ID theo policy;
- khi server có thể tra trạng thái, kiểm tra lại session;
- không tự tạo session mới trong logout retry;
- không báo “đã revoke trên mọi thiết bị” khi chỉ biết cookie local đã xóa;
- lưu operation/audit reference để đối soát nếu workflow nhiều service.

Nếu client timeout sau khi server đã revoke, retry có thể trả “đã đăng xuất”. Nếu server chưa revoke, retry thực hiện revoke. Nếu session store không khả dụng và không thể xác định trạng thái, UI cần thông báo trạng thái chưa xác nhận, đồng thời có thể xóa cookie local như biện pháp giảm rủi ro phía browser. Nhưng việc xóa cookie local không được mô tả thành server-side revocation.

## 9. Xử lý lỗi session store và database

Session store là nguồn trạng thái có thẩm quyền hoặc một lớp cache có cơ chế nhất quán. Nếu store không khả dụng, server không thể giả định session đã revoke.

Các nguyên tắc:
- Nếu database/session store hỗ trợ transaction, cập nhật trạng thái revoke trong transaction.
- Với cache, ghi revoke vào nguồn bền vững trước hoặc dùng cơ chế đảm bảo không có cache active thắng trạng thái revoke.
- Không fail open bằng cách bỏ qua session status vì store lỗi.
- Có thể trả lỗi tạm thời và yêu cầu retry.
- Với thao tác nhạy cảm, không chấp nhận session nếu không thể xác minh trạng thái theo policy.
- Giám sát latency, error, replication lag và cache invalidation failure.

Một thiết kế có thể dùng session version hoặc revocation epoch ở account level. Khi tăng version, mọi session mang version cũ bị từ chối khi verifier kiểm tra version hiện tại. Cơ chế này hữu ích cho logout all devices nhưng cần kiểm soát cache freshness.

## 10. Logout trên nhiều instance và nhiều region

Trong hệ thống scale-out, request logout có thể tới instance A trong khi request kế tiếp tới instance B. Nếu mỗi instance giữ session cache riêng và invalidation không lan truyền kịp, B có thể tiếp tục chấp nhận phiên.

Các lựa chọn:
- shared session store có consistency phù hợp;
- pub/sub invalidation kèm TTL ngắn và nguồn trạng thái authoritative;
- session version/account epoch được kiểm tra theo policy;
- route theo session key, nhưng vẫn cần xử lý failover và mất state;
- kiểm tra revocation gần điểm commit với hành động nhạy cảm.

Không coi eventual cache invalidation là revocation tức thời. Cần xác định SLA: ví dụ, sau khi logout server xác nhận, mọi instance phải từ chối session ở request tiếp theo hoặc trong một cửa sổ được công bố và chấp nhận về rủi ro.

~~~mermaid
flowchart LR
    B["Browser"] --> A["Instance A"]
    B --> C["Instance B"]
    A --> DB["Authoritative session store"]
    C --> DB
    A --> E["Revocation event"]
    E --> C
    DB --> C
    C --> X["Reject old session"]
~~~

Nếu một region bị partition khỏi nguồn trạng thái, policy phải xác định fail closed hay chế độ suy giảm có giới hạn. Đối với dữ liệu nhạy cảm và thao tác có side effect, không nên tiếp tục chấp nhận session chỉ vì region đó không nhận được revoke event.

## 11. Access Token và Refresh Token sau logout

Local session và OAuth tokens có thể có vòng đời khác nhau.

- Xóa session cookie không tự revoke Access Token đã phát hành.
- Access Token dạng JWT có thể tiếp tục được API chấp nhận đến khi hết hạn nếu API không kiểm tra revocation/introspection hoặc một cơ chế khác.
- Refresh Token nếu còn active có thể cấp Access Token mới.
- Một số hệ thống có token family rotation và reuse detection; logout cần revoke token family phù hợp.
- Token do IdP phát hành có thể nằm ngoài quyền quản lý trực tiếp của RP.

Khi logout:
1. Xác định token nào do ứng dụng/authorization server nào phát hành.
2. Thu hồi Refresh Token hoặc token family theo API/protocol hỗ trợ.
3. Xóa token khỏi storage phía client/backend.
4. API/resource server áp dụng expiry, introspection, denylist hoặc version policy phù hợp.
5. Không gửi Refresh Token tới endpoint resource server.
6. Không khẳng định access token đã bị vô hiệu tức thời nếu kiến trúc chỉ dựa trên TTL.

### Access Token ngắn hạn

TTL ngắn giảm cửa sổ sử dụng token bị đánh cắp nhưng không thay thế revoke khi cần logout khẩn cấp. Với API nhạy cảm, cân nhắc introspection hoặc kiểm tra session/account version. Lựa chọn phải cân bằng độ trễ, availability và yêu cầu thu hồi.

## 12. OIDC logout và lỗi Single Logout

OIDC có RP-Initiated Logout, Front-Channel Logout và Back-Channel Logout tùy khả năng OP/RP. Local logout tại RP vẫn phải được thực hiện độc lập.

### RP-Initiated Logout

RP có thể điều hướng browser tới end-session endpoint của OP theo metadata/cấu hình, kèm các tham số phù hợp như id_token_hint, post_logout_redirect_uri và state. Redirect hoặc trang hoàn tất từ OP không tự chứng minh mọi RP khác đã thu hồi session.

### Front-channel logout

OP dùng browser để thông báo cho RP. Cơ chế này phụ thuộc browser, cookie policy, iframe/navigation và các giới hạn third-party context. Một RP offline hoặc browser chặn request có thể không nhận event.

### Back-channel logout

OP gửi Logout Token trực tiếp tới endpoint backend của RP. RP cần xác minh chữ ký, issuer, audience, thời gian, logout event claim, jti và sid/sub theo đặc tả; sau đó ánh xạ đúng các local session cần revoke. Không tin một POST tới endpoint chỉ vì nó đến từ network nội bộ hoặc có subject trong payload.

### Khi IdP không khả dụng

Nếu người dùng yêu cầu local logout, RP vẫn phải revoke local session và xóa cookie dù OP không phản hồi. Có thể thông báo “Bạn đã đăng xuất khỏi ứng dụng này; phiên tại nhà cung cấp danh tính có thể vẫn còn” nếu cần làm rõ phạm vi. Không để external SLO timeout giữ local session active.

## 13. SAML Single Logout và lỗi correlation

SAML SLO dùng LogoutRequest/LogoutResponse để phối hợp logout giữa IdP và Service Provider. Khi xử lý, SP cần kiểm tra:
- chữ ký theo trust configuration;
- issuer và destination;
- NameID và SessionIndex theo session mapping;
- InResponseTo/correlation nếu có;
- thời hạn và replay;
- trạng thái session đang revoke.

Lỗi thường gặp:
- SP xóa local session trước nhưng IdP không nhận response;
- LogoutRequest hợp lệ nhưng SP không còn session mapping;
- request giả mạo làm revoke session của người khác;
- nhiều SessionIndex không được ánh xạ đầy đủ;
- một SP offline khiến SLO chỉ hoàn thành một phần.

Local logout vẫn nên hoàn tất ở SP. Với SLO, cần ghi nhận trạng thái từng participant, timeout/retry có giới hạn và không tuyên bố toàn bộ hệ thống đã logout nếu chỉ một phần thành công.

## 14. Logout all devices

Logout all devices thường là yêu cầu thu hồi mọi session và token của một account. Cách triển khai có thể:
- liệt kê và revoke từng session record;
- tăng account session version/revocation epoch;
- revoke mọi Refresh Token family;
- phát event tới các service giữ cache;
- invalidate API session/token theo policy.

Một transaction database có thể cập nhật account epoch và tạo outbox event. Các service nhận event sẽ invalidate cache và cập nhật trạng thái. Nếu event delivery bị lỗi, consumer cần retry và có dead-letter/alert; verifier vẫn phải có cách kiểm tra authoritative version.

Không chỉ revoke các session hiển thị trên trang “Thiết bị của tôi” nếu còn refresh token, API key hoặc session service khác nằm ngoài danh sách. Hãy định nghĩa rõ “all devices” bao gồm loại credential nào.

## 15. Race condition với request đang chạy

Một request có thể xác minh session thành công lúc T1, người dùng logout lúc T2, rồi request thực hiện side effect lúc T3. Nếu chỉ kiểm tra session ở đầu request, logout không nhất thiết dừng được request đã qua authentication.

Với thao tác nhạy cảm:
- kiểm tra session/account state gần điểm commit;
- dùng transaction hoặc version check để phát hiện revoke đồng thời;
- xác định rõ request đã được chấp nhận trước logout có được hoàn tất không;
- không hứa logout hủy mọi công việc đã bắt đầu;
- với tác vụ dài, kiểm tra cancellation/revocation signal ở checkpoint;
- audit thời điểm authentication, authorization, revoke và commit.

~~~text
T1: Request A kiểm tra session S1 = ACTIVE
T2: Người dùng logout, server đánh dấu S1 = REVOKED
T3: Request A cố commit chuyển tiền

Nếu policy yêu cầu:
  kiểm tra version/session status lại trước commit
  -> phát hiện S1 đã REVOKED
  -> dừng giao dịch

Nếu request đã commit trước T2:
  logout không thể đảo ngược side effect đã hoàn tất
~~~

Logout ngăn các request mới và có thể ngăn request chưa commit theo policy; nó không tự đảo ngược giao dịch đã hoàn tất.

## 16. Browser cache, nhiều tab và back navigation

Sau logout, người dùng có thể bấm Back và thấy nội dung đã tải trước đó. Đây có thể là nội dung trong browser memory/cache, không nhất thiết là server đã chấp nhận session cũ.

Biện pháp:
- response chứa dữ liệu nhạy cảm có thể dùng Cache-Control phù hợp, ví dụ `no-store` theo threat model;
- frontend kiểm tra trạng thái session khi khôi phục trang từ back-forward cache nếu phù hợp;
- nhiều tab nhận sự kiện logout để cập nhật UI;
- mọi API request vẫn phải được server xác minh;
- không coi ẩn giao diện hoặc redirect là revoke;
- xóa dữ liệu nhạy cảm trong client state khi logout.

Nếu browser hiển thị trang cũ, API mới vẫn phải từ chối session đã revoke. Cache control giảm việc dữ liệu nhạy cảm còn hiển thị, nhưng không thay thế server-side session invalidation.

## 17. Mobile app, offline và thiết bị bị mất

Ứng dụng mobile có thể lưu Refresh Token trong secure storage và Access Token trong memory hoặc storage phù hợp. Khi logout:
- gọi revoke endpoint khi có mạng;
- xóa local tokens và local app state;
- revoke server-side token/session;
- xử lý kết quả không xác định bằng retry/idempotency;
- không giữ refresh token trong backup không được bảo vệ;
- khi thiết bị mất, cung cấp logout/revoke từ một thiết bị khác.

Nếu app offline, nó có thể xóa credential cục bộ ngay nhưng chưa thể chứng minh server đã nhận revoke. UI cần phân biệt trạng thái local cleanup và server revocation pending. Khi có mạng lại, app có thể gửi yêu cầu revoke theo operation reference; server xử lý idempotently.

Đối với thiết bị bị mất, người dùng cần có cách revoke session/token từ account recovery hoặc trang bảo mật khác. Không yêu cầu phải cầm thiết bị mất để đăng xuất chính thiết bị đó.

## 18. UX và thông báo khi logout không hoàn tất

Thông báo nên phản ánh đúng phạm vi và trạng thái.

| Tình trạng | Thông báo/hành vi phù hợp |
| --- | --- |
| Local session đã revoke, cookie đã xóa | “Bạn đã đăng xuất khỏi ứng dụng.” |
| Local revoke thành công, IdP logout timeout | “Bạn đã đăng xuất khỏi ứng dụng; phiên tại nhà cung cấp danh tính có thể vẫn còn.” |
| Browser đã xóa cookie nhưng server revoke chưa xác nhận | Không tuyên bố logout hoàn tất; thông báo trạng thái chưa xác nhận và hướng dẫn retry/kênh hỗ trợ. |
| Logout all devices đang xử lý | Hiển thị trạng thái pending, không nói mọi thiết bị đã bị thu hồi. |
| Một số RP chưa nhận SLO | Nêu rõ logout liên kết chưa hoàn tất nếu UI cam kết phạm vi đó. |
| Session đã revoked từ trước | Có thể trả thành công idempotent. |

Không hiển thị lỗi kỹ thuật chi tiết như tên database, session ID hoặc token. Internal telemetry ghi reason code để đội vận hành xử lý.

## 19. Audit và giám sát logout

Audit cần phân biệt yêu cầu, kết quả local revoke và kết quả federation/token revocation.

Trường dữ liệu có thể gồm:
- account ID nội bộ;
- session reference không phải raw session ID;
- phạm vi logout (local/current/all/federated);
- request/correlation/operation ID;
- thời điểm nhận yêu cầu và thời điểm revoke commit;
- actor và kênh khởi tạo;
- kết quả session store/token service;
- IdP/RP participant và trạng thái SLO;
- lý do lỗi, retry count và thời điểm hoàn tất;
- phiên bản/account epoch nếu dùng.

Không log raw cookie, session ID, authorization code, ID Token, Access Token, Refresh Token hoặc logout token. Bảo vệ audit log bằng access control, retention và integrity controls.

Các metric:
- tỷ lệ local logout thành công/thất bại;
- độ trễ từ request đến revoke commit;
- số session còn active sau logout;
- cache invalidation lag;
- token revocation failures;
- SLO completion theo IdP/RP;
- retry, timeout và dead-letter count;
- số request bị từ chối do session revoked;
- account/session version mismatch.

## 20. Pseudocode local logout

Ví dụ Java minh họa:

~~~java
LogoutResult logout(
        HttpRequest request,
        AuthenticatedSession session) {

    csrfVerifier.requireValid(request, session);

    // Revoke ở nguồn trạng thái có thẩm quyền.
    RevocationResult revoked = sessionStore.revokeOnce(
        session.id(),
        session.accountId(),
        clock.instant());

    // Token do ứng dụng quản lý được xử lý riêng.
    tokenRevocationService.revokeLinkedRefreshTokens(
        session.accountId(),
        session.tokenFamilyReferences());

    // Cookie được xóa với đúng scope trong response.
    audit.recordLogout(
        session.accountId(),
        session.auditReference(),
        LogoutScope.LOCAL,
        revoked.status());

    return LogoutResult.localRevoked();
}
~~~

Đây là pseudocode. Production cần xác định:
- transaction boundary giữa session store và token service;
- hành vi khi một service thành công còn service kia timeout;
- retry/idempotency cho mỗi thao tác;
- không log raw session/token;
- có xóa cookie dù một bước phụ như IdP logout thất bại hay không;
- chỉ trả “local revoked” khi session store đã xác nhận hoặc có bằng chứng authoritative tương đương.

### Partial failure

Nếu session revoke thành công nhưng refresh token revoke thất bại, local browser session có thể đã kết thúc trong khi token còn hiệu lực. Hệ thống cần ghi nhận token revocation pending, retry có giới hạn và alert; API phải áp dụng TTL/introspection/revocation policy để giới hạn truy cập. UI cần nói đúng phạm vi đã hoàn tất.

## 21. State machine cho logout workflow

Một workflow có thể biểu diễn:

~~~mermaid
stateDiagram-v2
    [*] --> REQUESTED
    REQUESTED --> LOCAL_REVOKED: session revoke committed
    REQUESTED --> LOCAL_FAILED: store unavailable / error
    LOCAL_FAILED --> RETRY_PENDING: retry scheduled
    RETRY_PENDING --> LOCAL_REVOKED: retry succeeds
    RETRY_PENDING --> LOCAL_FAILED: retry exhausted
    LOCAL_REVOKED --> COOKIE_CLEARED: response sent
    COOKIE_CLEARED --> TOKEN_REVOCATION_PENDING: token work remains
    COOKIE_CLEARED --> LOCAL_COMPLETE: no linked token work
    TOKEN_REVOCATION_PENDING --> LOCAL_COMPLETE: token revoke succeeds
    TOKEN_REVOCATION_PENDING --> PARTIAL_COMPLETE: retry exhausted
    LOCAL_COMPLETE --> FEDERATION_PENDING: SLO requested
    FEDERATION_PENDING --> GLOBAL_COMPLETE: all required participants complete
    FEDERATION_PENDING --> PARTIAL_COMPLETE: participant timeout/failure
    PARTIAL_COMPLETE --> [*]
    GLOBAL_COMPLETE --> [*]
    LOCAL_COMPLETE --> [*]
    LOCAL_FAILED --> [*]
~~~

Tên trạng thái là ví dụ; hệ thống cần xác định rõ “complete” theo phạm vi người dùng yêu cầu. Không gộp local completion và global SLO completion thành một boolean duy nhất.

## 22. Các lỗi triển khai thường gặp

| Lỗi | Hậu quả | Kiểm soát |
| --- | --- | --- |
| Chỉ xóa cookie client | Cookie bị sao chép vẫn được server chấp nhận | Revoke session server-side. |
| Gọi logout bằng GET | CSRF hoặc crawler kích hoạt side effect | Dùng POST và CSRF protection. |
| Báo thành công trước khi revoke commit | Người dùng hiểu sai trạng thái bảo mật | Chỉ xác nhận phạm vi server đã hoàn tất. |
| Revoke ở một instance nhưng cache nơi khác còn active | Session tiếp tục được chấp nhận | Shared store, invalidation và freshness SLA. |
| Không revoke Refresh Token | Client xin Access Token mới sau logout | Revoke token family và kiểm tra API policy. |
| Đợi IdP logout mới revoke local session | IdP outage làm local session còn active | Revoke local trước/độc lập với SLO. |
| Không xác minh Logout Token/Request | Logout giả có thể gây DoS hoặc revoke nhầm | Verify issuer, signature, audience, event và mapping. |
| Retry tạo side effect khác | Nhiều lần revoke/event không nhất quán | Idempotent operation và operation ID. |
| Không xử lý request đang chạy | Side effect commit sau logout | Recheck state/version gần commit. |
| Cookie xóa sai Path/Domain | Browser tiếp tục gửi cookie | Dùng đúng cookie scope. |
| Không xử lý back-forward cache | Dữ liệu cũ vẫn hiển thị sau logout | Cache policy và client state cleanup. |
| Logout all devices chỉ xóa browser hiện tại | Session/token ở thiết bị khác còn hoạt động | Account epoch và revoke mọi token/session. |
| Không có audit partial failure | Không biết participant nào chưa logout | Theo dõi từng bước và participant. |

## 23. Kiểm thử logout failure

| Ca kiểm thử | Kết quả mong đợi |
| --- | --- |
| Local logout bình thường | Server revoke session và browser nhận cookie expiry. |
| Cookie bị đánh cắp trước logout | Request dùng cookie cũ bị từ chối sau revoke commit. |
| Browser xóa cookie nhưng server revoke lỗi | Không tuyên bố server logout hoàn tất; retry/alert theo policy. |
| Session đã revoked trước request logout | Trả kết quả idempotent, không lỗi trạng thái. |
| Logout request thiếu CSRF token | Từ chối. |
| Logout endpoint gọi bằng GET | Không thực hiện revoke. |
| Cookie có Path/Domain khác | Test xác minh cookie cũ không còn được gửi; cấu hình xóa đúng scope. |
| Session store timeout trước commit | Không fail open; trạng thái chưa xác nhận. |
| Timeout sau khi revoke đã commit | Retry trả trạng thái đã revoked. |
| Instance A revoke, instance B nhận request tiếp theo | B từ chối session theo SLA. |
| Cache invalidation event bị mất | Nguồn authoritative/version vẫn ngăn chấp nhận phiên cũ. |
| Refresh token revoke thất bại | Ghi partial failure, retry; API có giới hạn TTL/revocation. |
| IdP không khả dụng | Local logout vẫn hoàn tất; SLO báo partial/pending. |
| OIDC logout token sai signature/audience | Không revoke session. |
| OIDC logout token hợp lệ lặp lại | Xử lý idempotently. |
| SAML LogoutRequest sai issuer/SessionIndex | Từ chối. |
| SLO một RP timeout | Báo partial completion, retry theo policy. |
| Logout all devices | Mọi session/token thuộc phạm vi bị revoke. |
| Hai request logout cùng lúc | Chỉ một chuyển trạng thái; cả hai nhận kết quả nhất quán. |
| Request nghiệp vụ đang chạy trong lúc logout | Áp dụng policy recheck tại commit. |
| Trang nhạy cảm được mở bằng Back sau logout | Không gọi API thành công; dữ liệu cache được xử lý theo policy. |
| Mobile app offline logout | Local secrets bị xóa; server revocation được đánh dấu pending nếu chưa gửi. |
| Account bị deprovision | Session/token được revoke theo SLA và mọi instance từ chối. |
| Audit/log review | Không có raw session, cookie, token hoặc logout token. |

### Kiểm thử failure injection

Trong môi trường kiểm thử, mô phỏng:
- database/session store timeout;
- cache pub/sub mất message;
- token revocation endpoint trả 5xx;
- IdP không phản hồi;
- một RP offline;
- browser đóng tab ngay sau khi gửi logout;
- response bị mất sau khi server commit;
- request nghiệp vụ commit đồng thời với revoke.

Kiểm tra cả trạng thái lưu trữ và hành vi request sau đó. Một status code 200 không đủ chứng minh session/token đã bị vô hiệu trên mọi thành phần.

## 24. Bài tập tình huống

Một ứng dụng doanh nghiệp có ba API instance và dùng Redis cache cho session. Khi người dùng logout, instance A xóa cookie và xóa key trong Redis local. Instance B vẫn giữ session trong in-memory cache 60 phút. Refresh Token được lưu ở backend và không bị revoke. IdP đang bảo trì nên SLO timeout. Giao diện vẫn hiển thị “Đã đăng xuất khỏi tất cả thiết bị”.

**Yêu cầu phân tích:**

1. Những trạng thái nào thực sự đã được thu hồi?
2. Vì sao cookie deletion và cache local không đủ?
3. Instance B có thể tiếp tục chấp nhận session bằng cách nào?
4. Refresh Token còn active gây rủi ro gì?
5. IdP outage nên ảnh hưởng thế nào tới local logout?
6. Thiết kế lại logout all devices bằng session version/account epoch ra sao?
7. Giao diện và audit nên mô tả partial failure như thế nào?

**Hướng phân tích:** Local logout phải ghi revoke vào nguồn trạng thái authoritative, mọi instance kiểm tra trạng thái/version phù hợp. Cookie chỉ là cleanup. Refresh Token family cần revoke hoặc có cơ chế giới hạn TTL/introspection; thất bại phải được ghi pending và retry. IdP outage không được giữ local session active; chỉ SLO còn pending. UI không được nói all devices đã logout khi B hoặc token còn hiệu lực. Dùng account epoch, shared state, outbox/retry và test request tới từng instance.

## 25. Checklist review

- [ ] Phạm vi local/current device/all devices/IdP/SLO được định nghĩa rõ.
- [ ] Local logout revoke session server-side; không chỉ xóa cookie.
- [ ] Logout endpoint có CSRF protection và không dùng GET cho side effect.
- [ ] Cookie được xóa với đúng name, Path, Domain và attributes.
- [ ] Revoke operation idempotent và xử lý ambiguous timeout.
- [ ] Server không fail open khi session store không khả dụng.
- [ ] Mọi instance/region từ chối session revoked theo SLA.
- [ ] Refresh Token/token family được xử lý riêng; Access Token TTL/revocation được hiểu đúng.
- [ ] OIDC/SAML logout message được xác minh và ánh xạ đúng session.
- [ ] IdP/SLO failure không ngăn local logout hoàn tất.
- [ ] Logout all devices xử lý session, token và cache trên toàn phạm vi.
- [ ] Request đang chạy có policy race/commit rõ.
- [ ] Browser cache/multiple tabs/mobile offline được xử lý.
- [ ] UX phân biệt local complete, partial complete và global SLO complete.
- [ ] Audit ghi từng bước, participant, retry và reason code.
- [ ] Log không chứa cookie, session ID, authorization code hoặc token.
- [ ] Có failure-injection test cho store, cache, token service, IdP và downstream RP.

## 26. Ghi nhớ

**Đăng xuất chỉ thực sự có tác dụng khi server từ chối credential phiên cũ trong phạm vi đã cam kết.** Xóa cookie làm sạch browser nhưng không thu hồi bản sao bị đánh cắp; local session, refresh token, cache, IdP session và các RP session có vòng đời riêng. Thiết kế logout cần revoke server-side, idempotency, xử lý partial failure, lan truyền trạng thái nhất quán và thông báo chính xác phạm vi đã hoàn tất.

Khi review, hãy hỏi: **Session bị revoke ở nguồn nào? Nếu response timeout thì server đã commit hay chưa? Instance khác có thể chấp nhận cookie cũ không? Refresh Token còn xin token mới được không? IdP offline thì local logout có vẫn hoàn tất không? Người dùng có được thông báo đúng về partial failure và logout all devices không?**
