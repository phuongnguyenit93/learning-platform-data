# Session identifier — Định danh phiên xác thực

## 1. Session identifier là gì?

**Session identifier** (định danh phiên, thường gọi là *session ID*) là một giá trị do hệ thống tạo ra để nhận diện một phiên tương tác cụ thể giữa client và server. Sau khi người dùng xác thực thành công, server có thể tạo session ID và gửi nó về trình duyệt dưới dạng cookie. Ở những request tiếp theo, trình duyệt gửi lại cookie; server dùng session ID để tra trạng thái phiên và xác định chủ thể, mức xác thực, thời hạn cùng các thuộc tính liên quan.

Ví dụ: nhân viên đăng nhập cổng quản trị bằng passkey. Server kiểm tra bằng chứng WebAuthn, sau đó tạo một session ID ngẫu nhiên và lưu bản ghi phiên gắn với tài khoản nhân viên. Trình duyệt nhận cookie chứa ID này. Khi nhân viên mở trang hồ sơ hoặc gọi API, server kiểm tra cookie, tra session store và áp dụng quyền tương ứng.

Trong chương **Session** của module **SECURITY_AUTHENTICATION_FUNDAMENTALS**, session identifier kết nối quá trình xác thực bằng credential, mật khẩu, MFA, passkey, chứng chỉ và danh tính liên kết với trạng thái đăng nhập được duy trì. Người học cần hiểu cách tạo, truyền, lưu trữ, xoay vòng và thu hồi định danh phiên để bảo vệ ranh giới tin cậy, chống session fixation, replay, session hijacking và lạm dụng đăng nhập.

**Session ID là một credential dạng bearer trong nhiều thiết kế.** Ai có được giá trị hợp lệ có thể sử dụng phiên tương ứng, trừ khi hệ thống bổ sung cơ chế ràng buộc khác. Vì vậy, session ID phải được bảo vệ như một bí mật xác thực, không phải mã định danh thông thường để hiển thị hoặc chia sẻ.

### Phân biệt session ID với các định danh khác

| Giá trị | Dùng để làm gì? | Có phải bí mật xác thực không? |
| --- | --- | --- |
| **User ID** | Nhận diện tài khoản trong hệ thống. | Thường không; biết user ID không được phép chứng minh đã đăng nhập. |
| **Session ID** | Tra cứu một phiên cụ thể đã được server tạo. | Có, nếu bên nắm giữ có thể dùng nó để tiếp tục phiên. |
| **Access token** | Trình bày quyền truy cập API trong phạm vi/thời hạn được cấp. | Thường có; bearer access token phải được bảo vệ như credential. |
| **Refresh token** | Yêu cầu cấp access token mới theo chính sách. | Có; thường nhạy cảm hơn access token do có thể kéo dài quyền truy cập. |
| **ID token OIDC** | Mang thông tin xác thực dành cho relying party. | Là token nhạy cảm; không đồng nghĩa với session ID của ứng dụng. |
| **Request ID / correlation ID** | Liên kết log và trace của một request. | Không; không được dùng làm bằng chứng đăng nhập. |
| **CSRF token** | Chứng minh request thay đổi trạng thái phù hợp với phiên/giao dịch. | Có thể cần bảo vệ, nhưng không thay thế session ID hoặc xác thực người dùng. |

Một ứng dụng có thể dùng session ID opaque, access token hoặc một token tự chứa để duy trì trạng thái đăng nhập. Tuy nhiên, cần phân biệt **định danh phiên** với **bằng chứng xác thực được gửi trong request** và với **định danh tài khoản**. Không dùng user ID, email hoặc request ID làm session ID có thể đoán.

## 2. Session ID hoạt động như thế nào?

Trong mô hình session phía server (*server-side session*), cookie chứa một ID ngẫu nhiên, còn trạng thái phiên được lưu ở server:

~~~mermaid
sequenceDiagram
    participant U as Người dùng
    participant B as Trình duyệt
    participant A as Ứng dụng / Auth server
    participant S as Session store
    U->>B: Gửi credential (mật khẩu/MFA/passkey)
    B->>A: Yêu cầu đăng nhập qua TLS
    A->>A: Xác minh credential và chính sách
    A->>S: Tạo session mới gắn với principal
    S-->>A: Session ID ngẫu nhiên + trạng thái
    A-->>B: Set-Cookie: session ID
    B-->>U: Hiển thị ứng dụng đã đăng nhập
    B->>A: Request tiếp theo + cookie
    A->>S: Tra cứu và kiểm tra session
    S-->>A: Principal, expiry, assurance, status
    A->>A: Kiểm tra authorization cho request
    A-->>B: Trả kết quả nếu hợp lệ
~~~

Luồng cơ bản:

1. Client gửi credential tới endpoint xác thực qua kênh bảo vệ.
2. Server xác minh credential, MFA hoặc kết quả federation theo chính sách.
3. Server tạo một session ID mới bằng bộ sinh số ngẫu nhiên mật mã.
4. Server lưu bản ghi session gắn với principal và các thuộc tính cần thiết.
5. Server gửi session ID về client, thường qua cookie bảo mật.
6. Client gửi cookie trong các request phù hợp; server tra cứu và kiểm tra trạng thái phiên.
7. Server kiểm tra quyền trên tài nguyên và hành động cụ thể trước khi trả dữ liệu.

Session ID thường không chứa tên, email, role hoặc dữ liệu cá nhân. Nó là một **opaque reference**: client không cần biết ý nghĩa bên trong; server mới là bên quản lý trạng thái.

### Một bản ghi session khái niệm

~~~text
SessionRecord
  session_id_verifier: <hash của ID ngẫu nhiên>
  principal_id:        user-1024
  tenant_id:           org-27
  authenticated_at:    <timestamp>
  last_seen_at:        <timestamp>
  idle_expires_at:     <timestamp>
  absolute_expires_at: <timestamp>
  assurance_level:     <mức xác thực đã đạt>
  auth_methods:        [passkey]
  status:              active | revoked | expired
  created_from:        <metadata đã giảm thiểu>
~~~

Đây là mô hình tham khảo. Có thể lưu thêm thiết bị, phiên bản chính sách hoặc thông tin step-up nếu thực sự cần. Không lưu credential thô, mật khẩu, OTP, khóa riêng hoặc token khác vào bản ghi session nếu không có lý do và biện pháp bảo vệ rõ ràng.

## 3. Session ID phải khó đoán

Nếu session ID tuần tự hoặc có cấu trúc dễ suy ra, kẻ tấn công có thể thử ID của người dùng khác. Session ID cần được tạo từ **cryptographically secure pseudorandom number generator (CSPRNG)**, với entropy đủ lớn và không phụ thuộc vào dữ liệu dễ đoán.

Một nguyên tắc thực tế là dùng ít nhất **128 bit ngẫu nhiên** cho một session ID mới trong hệ thống hiện đại, rồi mã hóa biểu diễn bằng Base64url hoặc encoding an toàn tương đương. Con số cụ thể cần được đánh giá cùng độ dài ID, khả năng đoán, tốc độ thử và cơ chế giới hạn truy cập; không dùng bộ sinh ngẫu nhiên thông thường cho credential.

Ví dụ khái niệm:

~~~text
session_id = base64url(CSPRNG(16 bytes))
~~~

16 byte ngẫu nhiên tương ứng 128 bit entropy trước khi encode. Giá trị được encode chỉ là cách biểu diễn; encoding không tạo thêm entropy.

### Những cách tạo ID không an toàn

~~~text
Không dùng:
  session_id = user_id
  session_id = user_id + timestamp
  session_id = sequential_counter
  session_id = MD5(email + current_time)
  session_id = random() của thư viện không bảo đảm mật mã
~~~

Hash dữ liệu dễ đoán không biến nó thành bí mật mạnh. Nếu đầu vào là email, user ID hoặc timestamp, kẻ tấn công có thể suy ra hoặc thử các khả năng. Dùng CSPRNG từ nền tảng hoặc thư viện mật mã được duy trì.

### Collision và uniqueness

Với ID có entropy cao, xác suất trùng rất nhỏ, nhưng hệ thống vẫn nên có ràng buộc duy nhất ở kho lưu trữ và xử lý trường hợp insert collision bằng cách sinh lại ID. Không được âm thầm ghi đè session hiện có nếu ID trùng. Khóa tra cứu phải được thiết kế để tránh va chạm giữa tenant hoặc namespace.

## 4. Session ID không nên chứa dữ liệu có ý nghĩa

Session ID nên là giá trị opaque, ngẫu nhiên và không tiết lộ:

- User ID, email, tên hoặc thông tin cá nhân.
- Vai trò, nhóm quyền, tenant hoặc mức bảo đảm xác thực.
- Thời gian đăng nhập, thời hạn hoặc vị trí.
- Password hash, API key, access token hay dữ liệu credential khác.

Nếu client cần biết tên hiển thị hoặc trạng thái giao diện, server có thể trả các thuộc tính đó qua API sau khi xác minh phiên và quyền. Không nhúng dữ liệu vào ID để client tự giải mã hoặc tự quyết định quyền.

Một JWT có thể chứa claim và chữ ký, nhưng đó là mô hình token tự chứa khác với opaque session ID. JWT đã ký vẫn không mặc nhiên được mã hóa; payload thường có thể đọc được. Không đặt secret hoặc dữ liệu nhạy cảm vào JWT chỉ vì nó có chữ ký.

## 5. Truyền session ID: cookie, header và URL

### Cookie là lựa chọn phổ biến cho web

Một cookie phiên có thể được cấu hình như sau:

~~~http
Set-Cookie: __Host-session=<opaque-random-id>; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

| Thuộc tính | Ý nghĩa |
| --- | --- |
| **Secure** | Chỉ gửi cookie qua HTTPS. |
| **HttpOnly** | JavaScript thông thường không đọc được giá trị cookie qua \`document.cookie\`. |
| **SameSite** | Hạn chế một số request cross-site tự động gửi cookie; chọn Lax, Strict hoặc None theo luồng thực tế. |
| **Path=/** | Cookie áp dụng cho toàn ứng dụng theo path. |
| **__Host- prefix** | Trên trình duyệt hỗ trợ, yêu cầu Secure, Path=/ và không có Domain. |

Không nên đặt cookie ở domain cha nếu không cần chia sẻ với subdomain. Một subdomain yếu có thể tạo rủi ro cookie injection hoặc làm rộng phạm vi cookie. Path và Domain là thuộc tính định tuyến cookie, không phải ranh giới authorization đáng tin cậy.

### Không đặt session ID trong URL

Tránh các dạng:

~~~text
https://app.example.org/dashboard?sessionid=<secret>
https://app.example.org/path/<session-id>/profile
~~~

URL có thể xuất hiện trong browser history, access log, proxy log, analytics, screenshot, Referer header và hệ thống theo dõi. Nếu session ID nằm trong URL, người nhận liên kết hoặc bên thứ ba có thể lấy được credential.

### Với API không dùng cookie

Một số client gửi token trong header Authorization. Nếu dùng bearer token, cần bảo vệ token như secret: chỉ truyền qua TLS, không ghi log, không đưa vào URL và giới hạn scope/thời hạn. Không gửi session ID trong custom header rồi cho rằng header đó tự chống CSRF; nếu trình duyệt tự gửi cookie, CSRF vẫn cần được xử lý theo kiến trúc.

## 6. Session fixation và xoay vòng ID

**Session fixation** xảy ra khi kẻ tấn công khiến nạn nhân sử dụng một session ID mà kẻ tấn công đã biết. Nếu server giữ nguyên ID đó sau khi nạn nhân đăng nhập, kẻ tấn công có thể dùng lại ID để truy cập phiên đã xác thực.

Một ví dụ lỗi:

1. Người dùng truy cập ứng dụng và nhận session ID trước đăng nhập.
2. Kẻ tấn công biết hoặc kiểm soát được ID đó.
3. Người dùng đăng nhập; server nâng trạng thái của chính ID cũ thành authenticated.
4. Kẻ tấn công gửi lại ID đã biết và sử dụng phiên của nạn nhân.

### Biện pháp chính: regenerate session ID

- Sinh ID mới sau khi đăng nhập thành công.
- Vô hiệu hóa ID ẩn danh trước đăng nhập.
- Xoay ID khi nâng quyền hoặc hoàn tất step-up theo chính sách.
- Không cho client chọn session ID tùy ý.
- Hủy hoặc thu hồi ID cũ ở server; không chỉ thay cookie ở trình duyệt.

~~~mermaid
flowchart LR
    A["Anonymous session: S0"] --> B["Xác minh credential"]
    B --> C["Tạo session mới: S1"]
    C --> D["Thu hồi S0"]
    D --> E["Cookie chỉ chứa S1"]
    E --> F["Request tiếp theo dùng S1"]
~~~

Việc xoay ID cần xử lý request đang chạy và nhiều tab một cách nhất quán. Có thể có khoảng chuyển tiếp rất ngắn trong một số kiến trúc để tránh mất request hợp lệ, nhưng ID cũ không được tiếp tục đại diện cho phiên đã xác thực vô thời hạn.

## 7. Session lifecycle: idle timeout, absolute timeout và logout

Session ID có thể khó đoán nhưng vẫn nguy hiểm nếu tồn tại mãi. Một phiên cần chính sách vòng đời:

- **Idle timeout:** hết hạn sau khoảng thời gian không có hoạt động được tính là hợp lệ.
- **Absolute timeout:** hết hạn sau tổng thời gian tối đa kể từ khi phiên được tạo, dù có hoạt động liên tục.
- **Reauthentication interval:** khoảng thời gian tối đa kể từ lần xác thực mạnh gần nhất trước khi yêu cầu step-up cho hành động nhạy cảm.
- **Revocation:** trạng thái thu hồi do logout, nghi bị chiếm, quản trị hoặc tài khoản bị vô hiệu hóa.

~~~mermaid
stateDiagram-v2
    [*] --> Created
    Created --> Active: Session ID được cấp
    Active --> Active: Request hợp lệ / cập nhật idle time
    Active --> Rotated: Đăng nhập lại / step-up
    Rotated --> Active: ID mới được dùng
    Active --> Expired: Idle hoặc absolute TTL
    Active --> Revoked: Logout / incident / admin
    Expired --> [*]
    Revoked --> [*]
~~~

Thời hạn phải dựa trên mức nhạy cảm và cách sử dụng. Phiên quản trị hệ thống hoặc dịch vụ tài chính có thể cần idle timeout ngắn và step-up thường xuyên hơn một ứng dụng đọc nội dung ít nhạy cảm.

### Logout đúng cách

Logout nên:

1. Thu hồi hoặc xóa trạng thái session ở server.
2. Xóa cookie phía client với cùng Path/Domain và thuộc tính cần thiết.
3. Nếu có refresh token hoặc token liên quan, xử lý thu hồi theo chính sách.
4. Ghi audit event mà không lưu session ID thô.

Chỉ xóa cookie trên trình duyệt không làm bản sao session ID đã bị đánh cắp mất hiệu lực. Server cần từ chối ID đã thu hồi.

## 8. Server-side session store và triển khai phân tán

Trong hệ thống nhiều instance, mọi server cần đưa ra quyết định nhất quán về cùng một session ID. Một số lựa chọn:

| Kiến trúc | Cách hoạt động | Đánh đổi |
| --- | --- | --- |
| **In-memory per instance** | Session chỉ tồn tại trong bộ nhớ của một process. | Đơn giản nhưng mất khi restart; request tới instance khác có thể không nhận session. |
| **Sticky session** | Load balancer cố định client vào một instance. | Có thể giảm tra cứu chia sẻ nhưng phụ thuộc routing và khó failover; không thay thế quản lý thu hồi. |
| **Shared session store** | Redis/database hoặc dịch vụ session chung lưu trạng thái. | Nhiều instance tra cứu cùng nguồn; cần bảo vệ, scale và kiểm soát availability. |
| **Stateless signed token** | Client giữ token có chữ ký, server kiểm tra chữ ký/claim. | Giảm lookup nhưng thu hồi sớm và thay đổi trạng thái phức tạp hơn. |

Với server-side session store, record có thể được tra bằng session ID hoặc hash của session ID. Nếu lưu hash, server hash ID nhận được rồi tra record; cách này có thể giảm tác động nếu database bị đọc, nhưng không thay thế quyền truy cập database, mã hóa, backup và quản trị khóa.

### Cache và thu hồi

Nếu session status được cache tại nhiều instance, logout/revoke có thể bị trễ. Hệ thống cần:

- TTL cache giới hạn theo yêu cầu thu hồi.
- Event invalidation có retry và reconcile.
- Cơ chế kiểm tra trực tuyến cho hành động nhạy cảm khi cần hiệu lực nhanh.
- Telemetry đo thời gian từ revoke commit đến khi mọi verifier từ chối ID.
- Xử lý lỗi session store theo chính sách; không tự coi session hợp lệ khi không thể kiểm tra trạng thái mà hệ thống yêu cầu.

Sticky session không tự giải quyết vấn đề này. Nếu instance giữ session trong RAM và chưa nhận lệnh thu hồi, request vẫn có thể được chấp nhận.

## 9. Opaque session ID và JWT: lựa chọn thiết kế

| Tiêu chí | Opaque session ID | JWT / self-contained token |
| --- | --- | --- |
| Dữ liệu phía client | Một ID ngẫu nhiên không mang ý nghĩa. | Token chứa claim có thể đọc được và được ký (hoặc mã hóa nếu dùng JWE). |
| Kiểm tra | Tra session store hoặc verifier. | Kiểm tra chữ ký, issuer, audience, thời hạn và claim. |
| Thu hồi sớm | Thường dễ hơn vì server có trạng thái session. | Khó hơn nếu API chỉ xác minh chữ ký và \`exp\`; cần denylist, introspection, version hoặc TTL ngắn. |
| Cập nhật quyền/trạng thái | Có thể cập nhật server-side record. | Claim cũ còn nguyên đến khi hết hạn hoặc bị kiểm tra trạng thái bổ sung. |
| Khả năng mở rộng | Cần session store hoặc cache. | Có thể giảm lookup, nhưng cần quản lý khóa và revocation. |
| Rủi ro | ID bị đánh cắp vẫn là bearer credential. | Token bị đánh cắp cũng có thể dùng; payload không mặc nhiên bí mật. |

Không có lựa chọn tốt cho mọi hệ thống. Opaque session ID phù hợp khi cần trạng thái server-side và thu hồi nhanh. JWT có thể hữu ích trong kiến trúc phân tán, nhưng cần hiểu rõ trade-off về thu hồi, claim stale, quản lý khóa và audience.

**Không dùng ID token OIDC thay cho access token hoặc session ID một cách tùy tiện.** ID token dành cho RP xác minh sự kiện đăng nhập; access token dành cho resource server theo scope/audience. Ứng dụng có thể tạo phiên riêng sau khi xác minh OIDC.

## 10. Session assurance và step-up authentication

Một session record có thể lưu **mức bảo đảm xác thực** hoặc metadata về phương thức đã dùng, ví dụ:

- Thời điểm xác thực gần nhất.
- Phương thức: mật khẩu, TOTP, passkey, client certificate hoặc federation.
- Mức assurance theo chính sách nội bộ.
- Thời điểm step-up thành công.
- Phạm vi phiên hoặc tenant.

Không nên chỉ lưu một cờ \`mfa=true\` do client gửi. Server phải gắn mức bảo đảm với kết quả xác thực đã kiểm chứng. Với OIDC, các claim như \`amr\`, \`acr\`, \`auth_time\` chỉ được sử dụng theo ngữ nghĩa đã thỏa thuận với issuer và sau khi xác minh token.

### Khi nào cần step-up?

- Thêm/xóa passkey hoặc phương thức MFA.
- Thay đổi email/điện thoại khôi phục.
- Tạo API key hoặc chứng chỉ mới.
- Chuyển tiền, xuất dữ liệu nhạy cảm hoặc thay đổi quyền quản trị.
- Đăng nhập từ ngữ cảnh rủi ro cao.

Nếu session hiện tại không đạt yêu cầu, server có thể yêu cầu step-up. Trong lúc chờ, session không được nâng quyền; client chỉ nhận trạng thái pending phù hợp. Sau khi step-up thành công, server có thể xoay session ID để ràng buộc trạng thái mới.

## 11. Session identifier và CSRF

Với cookie session, trình duyệt tự gửi cookie trong các request phù hợp. Điều này tạo nguy cơ **Cross-Site Request Forgery (CSRF)**: trang bên ngoài khiến trình duyệt nạn nhân gửi request thay đổi trạng thái tới ứng dụng đang đăng nhập.

CSRF không yêu cầu kẻ tấn công biết session ID. Trình duyệt tự gửi cookie, còn kẻ tấn công cố làm nạn nhân thực hiện hành động ngoài ý muốn.

Biện pháp:

- CSRF token gắn với session/giao dịch và được kiểm tra ở server.
- SameSite phù hợp, thường Lax/Strict khi luồng ứng dụng cho phép; None chỉ khi thực sự cần cross-site và phải Secure.
- Kiểm tra Origin/Referer theo danh sách nguồn tin cậy.
- Không dùng GET cho thao tác thay đổi trạng thái.
- Xác thực lại/step-up cho thao tác nhạy cảm.

**HttpOnly không ngăn CSRF.** Thuộc tính này ngăn JavaScript thông thường đọc cookie, nhưng trình duyệt vẫn tự gửi cookie. SameSite là lớp bổ sung, không thay thế hoàn toàn CSRF protection.

## 12. Session hijacking và session fixation

### Session hijacking

Kẻ tấn công lấy được session ID/cookie/token hợp lệ rồi dùng nó để gửi request dưới danh nghĩa phiên của nạn nhân. Nguồn lộ có thể là:

- XSS hoặc mã độc trên thiết bị.
- Cookie truyền qua kênh không an toàn.
- Token xuất hiện trong URL, log, analytics hoặc crash report.
- Backup, extension hoặc kho lưu trữ client không được bảo vệ.
- Máy chủ/proxy bị xâm nhập.

### Session fixation

Kẻ tấn công biết trước session ID và khiến nạn nhân đăng nhập bằng chính ID đó. Nếu server không regenerate ID sau đăng nhập, kẻ tấn công có thể sử dụng lại ID.

### Kiểm soát theo nguyên nhân

| Nguy cơ | Lớp bảo vệ |
| --- | --- |
| Session ID dễ đoán | CSPRNG và entropy cao. |
| Session fixation | Regenerate ID sau đăng nhập/nâng quyền; thu hồi ID cũ. |
| Đánh cắp qua mạng | TLS toàn bộ, Secure cookie, HSTS. |
| XSS đọc cookie | HttpOnly, output encoding, CSP, quản lý script. |
| CSRF | CSRF token, SameSite, Origin/Referer và step-up. |
| Token leak | Không đưa token vào URL/log; bảo vệ storage và telemetry. |
| Phiên bị lạm dụng sau logout | Thu hồi server-side và cache invalidation. |

Các biện pháp bổ trợ nhau; không có một thuộc tính cookie nào giải quyết tất cả các con đường chiếm phiên.

## 13. Liên kết phiên với thiết bị và token binding

Một số hệ thống muốn giảm nguy cơ session ID bị sao chép bằng cách ràng buộc token với một khóa hoặc thiết bị. Ví dụ:

- **mTLS-bound token:** token được gắn với chứng chỉ client; resource server kiểm tra kết nối TLS và chứng chỉ tương ứng.
- **DPoP:** client tạo proof có chữ ký cho request bằng khóa riêng; server kiểm tra proof, method, URI, thời gian và định danh proof.
- **Device-bound credential:** khóa riêng được giữ trong phần cứng hoặc vùng bảo vệ của thiết bị, nếu nền tảng hỗ trợ.

Các cơ chế này có thể giảm giá trị của việc chỉ sao chép bearer token, nhưng không tự bảo vệ khi kẻ tấn công chiếm luôn private key, runtime hoặc thiết bị đang mở khóa. IP address, user agent và fingerprint trình duyệt chỉ là **tín hiệu rủi ro**, không phải bằng chứng thiết bị đáng tin tuyệt đối.

Không tự thêm ràng buộc cứng vào IP hoặc user agent nếu chưa đánh giá người dùng di động, VPN, proxy và thay đổi mạng. Ràng buộc sai có thể gây khóa nhầm trong khi không ngăn được kẻ tấn công cùng thiết bị/mạng.

## 14. Xử lý session khi credential thay đổi hoặc tài khoản gặp sự cố

Session được tạo từ một lần xác thực trước đó. Khi credential hoặc trạng thái tài khoản thay đổi, cần quyết định phiên nào còn hợp lệ:

- **Đổi mật khẩu:** cân nhắc thu hồi các phiên khác hoặc yêu cầu đăng nhập lại, nhất là sau sự cố lộ credential.
- **Thêm/xóa MFA hoặc passkey:** thông báo chủ tài khoản; xem xét thu hồi phiên cũ nếu thao tác xảy ra trong ngữ cảnh bất thường.
- **Thu hồi certificate/API key:** không giả định session/token đã phát hành tự động mất hiệu lực; xử lý theo quan hệ credential-session trong kiến trúc.
- **Tài khoản bị khóa/vô hiệu hóa:** verifier cần từ chối phiên hoặc kiểm tra trạng thái tài khoản theo chính sách.
- **Khôi phục tài khoản:** cấp phiên mới sau khi quy trình recovery đạt; xem xét thu hồi phiên cũ và token liên quan.
- **Nghi session hijacking:** thu hồi phiên cụ thể hoặc tất cả phiên của tài khoản, yêu cầu xác thực lại và kiểm tra thay đổi credential.

Một session có thể tồn tại lâu hơn credential đã dùng để tạo nó nếu hệ thống không liên kết trạng thái. Vì vậy, cần định nghĩa **credential revocation policy** và **session revocation policy** riêng, đồng thời quy định khi nào một sự kiện ở lớp credential buộc phải thu hồi phiên.

## 15. Mã giả: tạo, kiểm tra và thu hồi session ID

Mã giả dưới đây minh họa logic server-side session. Đây không phải code production:

~~~text
createAuthenticatedSession(principal, assurance):
    rawId = CSPRNG(16 bytes or more)
    verifier = secureSessionIdVerifier(rawId)

    record = {
        principalId: principal.id,
        tenantId: principal.tenantId,
        assurance: assurance,
        authenticatedAt: trustedClock.now(),
        lastSeenAt: trustedClock.now(),
        idleExpiresAt: calculateIdleExpiry(),
        absoluteExpiresAt: calculateAbsoluteExpiry(),
        status: "active"
    }

    sessionStore.insertUnique(verifier, record)
    return rawId

authenticateRequest(request):
    rawId = readSessionCookie(request)
    if rawId is missing:
        return unauthenticated()

    verifier = secureSessionIdVerifier(rawId)
    record = sessionStore.lookup(verifier)
    if record is missing or record.status != "active":
        return unauthenticated()

    if now >= record.idleExpiresAt or now >= record.absoluteExpiresAt:
        sessionStore.expireAtomically(verifier)
        return unauthenticated()

    if not accountIsActive(record.principalId):
        sessionStore.revokeAtomically(verifier)
        return unauthenticated()

    if policy.requiresStepUp(request, record.assurance, record.authenticatedAt):
        return stepUpRequired()

    if not authorizationAllows(record.principalId, request.resource, request.action):
        return forbidden()

    sessionStore.updateActivitySafely(verifier)
    return authenticatedPrincipal(record.principalId)

logout(request):
    rawId = readSessionCookie(request)
    if rawId exists:
        sessionStore.revokeAtomically(secureSessionIdVerifier(rawId))
    clearCookieWithMatchingAttributes()
    return success()
~~~

Trong triển khai thật:

- Dùng CSPRNG và API cookie của framework; không tự xây thuật toán tạo ID.
- Bảo vệ session store, backup và quyền đọc; có thể lưu verifier/hash thay vì ID thô.
- Kiểm tra thời hạn bằng clock đáng tin và xử lý cập nhật idle time đồng thời.
- Xoay ID khi đăng nhập hoặc nâng quyền; ID mới phải được lưu và phát hành có kiểm soát.
- Không ghi raw ID vào log; dùng correlation ID riêng để điều tra.
- Nếu dùng JWT/stateless token, áp dụng quy trình kiểm tra chữ ký/claim và cơ chế thu hồi phù hợp thay vì giả định có session store.

## 16. Tình huống thực tế: người dùng đăng nhập từ nhiều thiết bị

Một nhân viên dùng laptop công ty và điện thoại cá nhân để truy cập cổng nội bộ. Mỗi lần đăng nhập, server tạo một session ID riêng:

| Phiên | Thiết bị | Trạng thái | Quyền |
| --- | --- | --- | --- |
| \`S-A\` | Laptop công ty | Active | Đọc và cập nhật hồ sơ. |
| \`S-B\` | Điện thoại | Active | Đọc hồ sơ, không được xuất dữ liệu. |
| \`S-C\` | Laptop cũ bị mất | Revoked | Không được truy cập. |

Các session cần tách biệt để người dùng có thể thu hồi một thiết bị mà không nhất thiết đăng xuất mọi thiết bị. Nhưng nếu tài khoản bị chiếm hoặc có sự cố nghiêm trọng, quản trị viên có thể thu hồi tất cả session theo chính sách.

### Các quyết định thiết kế

1. **Mỗi lần đăng nhập tạo ID riêng:** không dùng chung một session ID cho mọi thiết bị.
2. **Gắn session với principal và assurance:** server biết phiên nào được xác thực bằng passkey, phiên nào cần step-up.
3. **Cho phép xem và thu hồi thiết bị:** hiển thị nhãn/metadata đã giảm thiểu, thời điểm hoạt động; không hiển thị session ID.
4. **Giới hạn số session nếu cần:** tránh tạo vô hạn phiên; không dùng giới hạn này làm cơ chế duy nhất chống tấn công.
5. **Thu hồi phía server:** khi người dùng chọn đăng xuất thiết bị cũ, record \`S-C\` chuyển revoked và mọi verifier phải áp dụng.
6. **Kiểm tra quyền từng request:** session của điện thoại không được tự nâng lên quyền laptop chỉ vì cùng principal.

### Nếu session store không sẵn sàng?

Nếu ứng dụng yêu cầu tra session store để xác minh, khi store không sẵn sàng server không thể chắc session còn active hay đã bị thu hồi. Với tài nguyên nhạy cảm, không nên fail-open bằng cách chấp nhận cookie mà không kiểm tra. Có thể trả lỗi tạm thời, cảnh báo vận hành và khôi phục dịch vụ. Với dữ liệu ít nhạy cảm, quyết định dự phòng vẫn phải được quy định trước trong risk policy, không tùy tiện trong lúc sự cố.

## 17. Kiểm thử và quan sát session identifier

Các kiểm thử quan trọng:

| Tình huống | Kết quả mong đợi |
| --- | --- |
| Session ID được sinh liên tiếp | Không có mẫu tuần tự hoặc quan hệ dễ đoán. |
| Đăng nhập với ID ẩn danh đã có | Server phát ID mới và thu hồi ID trước đăng nhập. |
| Client tự gửi ID do họ chọn | Server không chấp nhận ID chưa được server cấp. |
| Session ID xuất hiện trong URL | Kiểm thử phải phát hiện; thiết kế loại bỏ cách truyền này. |
| Cookie gửi qua HTTP | Secure cookie không được gửi; ứng dụng yêu cầu HTTPS. |
| JavaScript đọc cookie HttpOnly | Không đọc được giá trị bằng API thông thường. |
| Session hết idle/absolute TTL | Request bị từ chối và cần xác thực lại. |
| Logout rồi dùng lại cookie cũ | Server từ chối session đã thu hồi. |
| Hai instance nhận cùng session | Cùng áp dụng trạng thái authoritative, không tạo principal khác nhau. |
| Session hợp lệ nhưng account bị disabled | Request bị từ chối theo chính sách. |
| Session có assurance thấp gọi thao tác nhạy cảm | Yêu cầu step-up, không tự nâng quyền. |
| Cache chưa nhận revoke event | TTL/reconcile giới hạn thời gian chấp nhận trạng thái cũ. |
| Session ID bị ghi vào log | Pipeline/logging test phải phát hiện và loại bỏ. |

### Log và chỉ số

Có thể ghi các sự kiện:

- Session created, rotated, expired, revoked.
- Đăng nhập thành công/thất bại và phương thức xác thực ở mức metadata cần thiết.
- Session bị từ chối do hết hạn, thu hồi hoặc tài khoản bị vô hiệu hóa.
- Step-up requested/completed/failed.
- Logout thiết bị hiện tại hoặc thu hồi tất cả phiên.

Không ghi session ID, cookie, access token hoặc refresh token thô. Dùng request ID hoặc mã tham chiếu audit không có khả năng xác thực.

Chỉ số hữu ích:

- Số session active theo principal/tenant và thiết bị ở mức tổng hợp.
- Tỷ lệ session hết hạn theo idle/absolute timeout.
- Thời gian từ revoke commit tới khi mọi instance từ chối ID.
- Số request dùng session đã revoked/expired.
- Tỷ lệ step-up thành công/thất bại và tác động tới người dùng.
- Số sự cố session fixation/hijacking được xác nhận hoặc nghi ngờ.

IP, vị trí và user agent nên được giảm thiểu và dùng làm tín hiệu rủi ro, không làm định danh duy nhất của phiên.

## 18. Checklist thiết kế session identifier

- [ ] Session ID được tạo bằng CSPRNG, có entropy cao và không thể đoán.
- [ ] ID là opaque, không chứa user ID, email, role hoặc thông tin nhạy cảm.
- [ ] Session ID được coi là bearer credential và không ghi vào log/URL/analytics.
- [ ] Cookie web dùng Secure, HttpOnly, SameSite và phạm vi Domain/Path phù hợp.
- [ ] Toàn bộ luồng dùng HTTPS/TLS; không truyền cookie xác thực qua HTTP.
- [ ] ID được regenerate sau đăng nhập và nâng quyền; chống session fixation.
- [ ] Có idle timeout, absolute timeout và step-up interval theo rủi ro.
- [ ] Logout/thu hồi được thực thi ở server; cookie client được xóa phù hợp.
- [ ] Shared session store/cache có consistency, TTL và cơ chế invalidation rõ.
- [ ] Tài khoản bị vô hiệu hóa hoặc credential bị thu hồi có chính sách ảnh hưởng session.
- [ ] API xác thực session và kiểm tra authorization trên từng resource/action.
- [ ] Có CSRF protection nếu trình duyệt tự gửi cookie.
- [ ] Có khả năng xem/thu hồi session theo thiết bị và phản ứng sự cố.
- [ ] Kiểm thử replay, fixation, hijacking, timeout, cache lag và lỗi session store.

## 19. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao session ID không nên là user ID hoặc email?

**Gợi ý:** User ID/email thường không bí mật và dễ đoán; session ID là bearer credential cần ngẫu nhiên, khó đoán và không tiết lộ danh tính.

**Câu 2.** Vì sao server cần tạo session ID mới sau khi đăng nhập?

**Gợi ý:** Ngăn session fixation: kẻ tấn công không thể tiếp tục dùng ID ẩn danh đã biết sau khi nạn nhân xác thực.

**Câu 3.** HttpOnly có ngăn CSRF không?

**Gợi ý:** Không. Trình duyệt vẫn tự gửi cookie; cần CSRF token, SameSite và kiểm tra Origin/Referer phù hợp.

**Câu 4.** Vì sao logout phải thu hồi session ở server?

**Gợi ý:** Bản sao cookie đã bị đánh cắp vẫn có thể dùng nếu server tiếp tục chấp nhận session ID.

**Câu 5.** Opaque session ID và JWT khác nhau thế nào về thu hồi?

**Gợi ý:** Opaque ID thường tra trạng thái server-side nên thu hồi dễ hơn; JWT tự chứa có thể còn hợp lệ tới exp nếu không có denylist/introspection hoặc cơ chế trạng thái bổ sung.

**Câu 6.** Nếu session store gặp lỗi, tại sao không mặc định cho qua cookie?

**Gợi ý:** Server không thể kiểm tra trạng thái active/revoked/expired; fail-open có thể cho phép session đã bị thu hồi tiếp tục truy cập.

## 20. Ghi nhớ

**Session identifier là giá trị ngẫu nhiên do server cấp để nhận diện một phiên đã xác thực; trong mô hình bearer, ai nắm giữ ID hợp lệ có thể sử dụng phiên.** Vì vậy, ID phải khó đoán, opaque, được truyền qua TLS, lưu trong cookie bảo vệ, không xuất hiện trong URL/log, được xoay vòng sau đăng nhập/nâng quyền và có thể thu hồi phía server. Session cần idle/absolute timeout, kiểm tra quyền trên từng request, chống CSRF và cơ chế đồng bộ trạng thái trong hệ thống phân tán. Credential xác minh người dùng ở thời điểm đăng nhập; session ID duy trì trạng thái tin cậy sau đó và phải được bảo vệ như một credential riêng.
