# Token khác session và cookie như thế nào?

Khi đăng nhập vào một ứng dụng, trình duyệt có thể giữ cookie, máy chủ có thể tạo session, còn API có thể yêu cầu access token. Ba khái niệm này thường xuất hiện cùng nhau nên dễ bị gọi thay thế cho nhau. Tuy nhiên, chúng trả lời **ba câu hỏi khác nhau**:

- **Session:** Ứng dụng duy trì trạng thái đăng nhập hoặc trạng thái tương tác của người dùng bằng cách nào?
- **Token:** Client trình ra bằng chứng/giá trị ủy quyền gì để máy chủ xác thực và quyết định quyền truy cập?
- **Cookie:** Trình duyệt lưu và tự gửi một giá trị tới máy chủ qua HTTP bằng cơ chế nào?

Một hệ thống có thể dùng cả ba cùng lúc: server giữ session, trình duyệt giữ **session ID** trong cookie, và backend dùng **access token** để gọi một API khác. Vì vậy, việc chọn “session hay cookie hay token” thường là một câu hỏi chưa đúng: cần xác định **trạng thái**, **thông tin xác thực** và **cách truyền/lưu** trước.

## 1. Hiểu chính xác ba khái niệm

### 1.1. Session: một phiên làm việc, thường gắn với trạng thái phía server

Session là ngữ cảnh của một chuỗi tương tác: ví dụ “người dùng A đã đăng nhập lúc 09:00, session hết hạn sau 30 phút không hoạt động”. Trong kiến trúc **server-side session**, máy chủ tạo một định danh ngẫu nhiên khó đoán (session ID) và giữ bản ghi tương ứng:

~~~text
Session store
  sessionId = "v7N...ngẫu nhiên..."
    userId      = 42
    loginAt     = 2026-11-23T09:00:00+07:00
    expiresAt   = ...
    privileges  = ...
~~~

Mỗi request mang session ID sẽ được server tra cứu để xác định session còn hiệu lực và người dùng có quyền gì. Bản thân session ID thường không chứa tên, vai trò hay mật khẩu; đó là **khóa tra cứu**, nhưng ai đánh cắp được một session ID đang hiệu lực thường có thể sử dụng nó như một bearer credential.

Từ “session” còn có nghĩa rộng là *phiên đăng nhập logic*, kể cả khi ứng dụng dùng token tự chứa và không lưu một bản ghi session riêng. Vì vậy, **session không bắt buộc đồng nghĩa với cookie** hoặc một bảng dữ liệu trên server. Trong bài này, “server-side session” chỉ rõ mô hình server lưu trạng thái.

### 1.2. Token: giá trị làm bằng chứng cho một mục đích bảo mật

Token là giá trị mà client cung cấp để thực hiện một tác vụ bảo mật, thường dùng cho xác thực hoặc ủy quyền. Ý nghĩa token tùy loại và bên phát hành:

| Loại token/định danh | Dùng để làm gì? | Bên tiếp nhận chính |
| --- | --- | --- |
| **Session ID** | Xác định session đang lưu trên server | Web server có session store |
| **Access token** | Cho phép truy cập tài nguyên/API trong giới hạn được cấp | Resource server/API |
| **Refresh token** | Xin access token mới theo chính sách của authorization server | Authorization server |
| **ID token (OIDC)** | Truyền thông tin xác thực người dùng cho client OIDC | OIDC client |
| **CSRF token** | Gắn request thay đổi trạng thái với phiên/trang hợp lệ để chống CSRF | Ứng dụng web |

**Token không phải lúc nào cũng là JWT.** Có hai dạng thường gặp:

- **Opaque token:** Chuỗi khó đoán, client không suy ra nội dung. Máy chủ tra cứu hoặc dùng introspection để biết hiệu lực, chủ thể, scope và các thuộc tính liên quan.
- **JWT (JSON Web Token):** Token có các phần biểu diễn bằng Base64url, thường gồm header, payload và signature. Với JWT đã ký (JWS), resource server có thể kiểm tra chữ ký và claims mà không cần truy vấn session store cho mỗi request, nếu kiến trúc cho phép. **Payload của JWT đã ký không mặc định được mã hóa**: ai có token thường có thể giải mã và đọc claims.

JWT mô tả **định dạng**; access token, ID token và refresh token mô tả **vai trò**. Một access token có thể là JWT hoặc opaque. Một JWT có thể được đặt trong cookie hoặc trong header HTTP. Không nên suy luận “có JWT thì chắc chắn là OAuth” hay “dùng JWT thì không có session”.

### 1.3. Cookie: cơ chế lưu và gửi dữ liệu của trình duyệt

Cookie là cặp tên–giá trị cùng các thuộc tính như phạm vi host/path, thời hạn và cờ bảo vệ. Server thường gửi cookie qua header <code>Set-Cookie</code>; với các request phù hợp, trình duyệt tự thêm header <code>Cookie</code>.

Cookie có thể chứa session ID, một token, lựa chọn ngôn ngữ hoặc dữ liệu khác. **Cookie tự nó không xác thực người dùng.** Server phải hiểu giá trị được gửi, xác minh tính hợp lệ và kiểm tra quyền.

“Session cookie” trong thuật ngữ trình duyệt còn có thể chỉ **cookie không khai báo <code>Expires</code> hoặc <code>Max-Age</code>**, thường được giữ đến khi phiên trình duyệt kết thúc; cơ chế khôi phục phiên của trình duyệt có thể làm nó tồn tại lâu hơn dự kiến. Khái niệm này **khác** với “session đăng nhập trên server”, vốn có chính sách hết hạn riêng.

### 1.4. Đối chiếu ở đúng từng lớp

| Khía cạnh | Server-side session | Token truy cập API | Cookie |
| --- | --- | --- | --- |
| Bản chất | Trạng thái/phiên và định danh phiên | Credential mang quyền truy cập có giới hạn | Cơ chế trình duyệt lưu/gửi giá trị |
| Giá trị phía client thường thấy | Session ID ngẫu nhiên | Access token opaque hoặc JWT | Một cặp tên–giá trị, có thể chứa session ID/token |
| Vị trí trạng thái/quyền | Chủ yếu trong session store | Có thể ở server (opaque) hoặc trong claims JWT đã được ký | Cookie không quyết định quyền |
| Cách đưa vào request | Thường nằm trong cookie | Thường qua <code>Authorization: Bearer ...</code>; cũng có thể nằm trong cookie | Trình duyệt tự gắn <code>Cookie</code> theo chính sách |
| Kiểm tra | Tra cứu session ID, hạn và quyền | Kiểm tra chữ ký/claims hoặc introspection, rồi kiểm tra scope/audience | Server tự kiểm tra giá trị nhận được |
| Thu hồi | Có thể xóa/vô hiệu hóa session trên server | Phụ thuộc loại token và cơ chế thu hồi | Xóa cookie chỉ loại bỏ bản sao ở trình duyệt đó |
| Rủi ro chính | Đánh cắp/fixation session ID, session còn tồn tại quá lâu | Rò rỉ/replay token, sai audience/scope, token tồn tại sau logout | CSRF khi cookie tự gửi; cấu hình cookie yếu |

Điểm mấu chốt: **session ID cũng là một dạng token theo nghĩa bearer credential**. Sự phân biệt hữu ích trong thiết kế thường là “session được server lưu trạng thái” so với “access token được resource server xác minh”, chứ không phải hai tập khái niệm hoàn toàn tách biệt.

## 2. Ba luồng hoạt động thường gặp

### 2.1. Đăng nhập web bằng server-side session và cookie

~~~mermaid
sequenceDiagram
    autonumber
    participant B as Trình duyệt
    participant W as Web server
    participant S as Session store
    B->>W: POST /login (thông tin đăng nhập)
    W->>W: Xác thực và tạo session ID ngẫu nhiên mới
    W->>S: Lưu session ID → user, hạn, trạng thái
    W-->>B: Set-Cookie: __Host-session=<sid>; ...
    B->>W: GET /profile + Cookie: __Host-session=<sid>
    W->>S: Tra cứu session và kiểm tra hiệu lực
    S-->>W: userId và trạng thái
    W-->>B: Hồ sơ hoặc 401
    B->>W: POST /logout (cookie tự đính kèm)
    W->>S: Vô hiệu hóa session
    W-->>B: Xóa cookie bằng Set-Cookie
~~~

Ví dụ response sau đăng nhập qua HTTPS:

~~~http
HTTP/1.1 200 OK
Cache-Control: no-store
Set-Cookie: __Host-session=<session-id-ngau-nhien>; Path=/; Secure; HttpOnly; SameSite=Lax
Content-Type: application/json

{"message":"login successful"}
~~~

Request tiếp theo:

~~~http
GET /profile HTTP/1.1
Host: app.example.com
Cookie: __Host-session=<session-id-ngau-nhien>
~~~

Server không nên chỉ dựa vào việc cookie tồn tại. Nó phải tra session, kiểm tra hết hạn/vô hiệu hóa và quyền với tài nguyên đích. Khi đăng nhập thành công hoặc nâng quyền, cần **tạo/đổi session ID** để giảm session fixation. Khi logout, cần vô hiệu hóa session **ở server** và hướng dẫn trình duyệt xóa cookie. Xóa cookie đơn thuần không chặn được kẻ tấn công vẫn nắm bản sao session ID.

Trong ví dụ, tiền tố <code>__Host-</code> yêu cầu cookie được đặt qua HTTPS với <code>Secure</code>, có <code>Path=/</code> và **không có <code>Domain</code>**. <code>HttpOnly</code> ngăn JavaScript đọc cookie qua các API như <code>document.cookie</code>, nhưng vẫn cho phép trình duyệt tự gửi cookie khi request phù hợp.

### 2.2. Gọi API bằng OAuth 2.0 access token

Một ứng dụng có thể nhận access token từ authorization server theo luồng thích hợp, ví dụ **Authorization Code + PKCE** cho ứng dụng công khai. Nó gửi token tới **resource server/API**:

~~~mermaid
sequenceDiagram
    autonumber
    participant C as Client
    participant A as Authorization server
    participant R as Resource server/API
    C->>A: Hoàn thành luồng OAuth 2.0 phù hợp
    A-->>C: Access token (và có thể refresh token)
    C->>R: GET /orders + Authorization: Bearer <access-token>
    R->>R: Xác minh token, audience, scope và hạn
    R-->>C: 200 dữ liệu / 401 / 403
    opt Cần cấp lại access token
        C->>A: Gửi refresh token theo chính sách
        A-->>C: Access token mới và có thể refresh token mới
    end
~~~

~~~http
GET /orders HTTP/1.1
Host: api.example.com
Authorization: Bearer <access-token>
~~~

Khác với cookie, trình duyệt **không tự gắn** header <code>Authorization: Bearer</code> chỉ vì client đang có token. Ứng dụng hoặc thư viện HTTP chủ động đặt header này.

Với **JWT access token**, API tối thiểu cần xác minh chữ ký bằng khóa tin cậy và thuật toán được cho phép; kiểm tra <code>iss</code> (issuer), <code>aud</code> (đúng API đích), <code>exp</code> và các ràng buộc thời gian khác như <code>nbf</code> nếu có; sau đó kiểm tra scope/permission trên thao tác đang gọi. Cần bảo đảm token thực sự là **access token dành cho API đó**, tránh chấp nhận nhầm ID token hoặc token từ hệ thống khác. Việc chỉ decode phần payload rồi tin <code>sub</code> hay <code>role</code> là **không đủ**.

Ví dụ payload JWT **chỉ để minh họa** (đây không phải token hợp lệ):

~~~json
{
  "iss": "https://auth.example.com",
  "sub": "user-42",
  "aud": "https://api.example.com",
  "scope": "orders:read",
  "iat": 1795380000,
  "exp": 1795380900
}
~~~

Với **opaque access token**, resource server thường phải tra cứu dữ liệu token hoặc gọi endpoint introspection bảo mật để xác định token có active, audience, scope và thời hạn phù hợp hay không. Cả JWT lẫn opaque token đều cần được bảo vệ như bí mật nếu là bearer token.

**Access token, refresh token và ID token không dùng thay cho nhau:**

- **Access token** trình cho resource server để truy cập API; scope chỉ giới hạn khả năng được cấp, còn API phải kiểm tra quyền trên từng tài nguyên.
- **Refresh token** chỉ dùng với authorization server để xin token mới; không gửi refresh token tới resource API. Refresh token có giá trị lâu dài hơn thường cần bảo vệ mạnh, xoay vòng và phát hiện tái sử dụng theo loại client/chính sách.
- **ID token của OpenID Connect** chứng minh sự kiện xác thực cho **OIDC client**, với issuer, audience và các yêu cầu OIDC riêng; API không nên chấp nhận ID token thay cho access token.

Khi bearer access token thiếu, sai hoặc hết hạn, API thường trả **401 Unauthorized** (có thể kèm <code>WWW-Authenticate</code>); token hợp lệ nhưng thiếu quyền trên tài nguyên thường dẫn đến **403 Forbidden**.

### 2.3. JWT nằm trong cookie: vẫn là JWT và vẫn có đặc điểm của cookie

Một ứng dụng có thể phản hồi:

~~~http
Set-Cookie: __Host-auth=<jwt>; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

Lúc này **JWT là định dạng token**, còn **cookie là phương tiện lưu/truyền**. Server vẫn phải kiểm tra chữ ký, issuer, audience, thời hạn và quyền. Nếu API nhận JWT từ cookie tự gửi, nó vẫn chịu rủi ro **CSRF** như những cơ chế dựa vào cookie khác; việc chuyển session ID thành JWT **không tự loại bỏ CSRF**.

Một phương án khác là **Backend for Frontend (BFF)**: trình duyệt chỉ giữ session cookie bảo vệ bằng <code>HttpOnly</code>, BFF quản lý access/refresh token ở server và thay mặt trình duyệt gọi API. Mô hình này thường giúp giảm việc để token OAuth trực tiếp trong mã JavaScript của trình duyệt, nhưng vẫn đòi hỏi bảo vệ session cookie, CSRF và XSS.

## 3. “Stateful vs stateless” là một trục lựa chọn khác

Nói “cookie là stateful, JWT là stateless” là quá đơn giản:

| Cấu hình | Client giữ gì? | Server cần làm gì trên mỗi request? | Khả năng thu hồi ngay |
| --- | --- | --- | --- |
| Session ID trong cookie | Định danh opaque | Tra session store | Thường dễ: vô hiệu hóa bản ghi |
| Opaque access token trong Bearer header | Token opaque | Tra cứu hoặc introspection (có thể cache theo chính sách) | Phụ thuộc hệ thống phát hành và cache |
| JWT access token trong Bearer header | JWT đã ký | Kiểm tra chữ ký, claims và chính sách quyền | Khó hơn nếu chỉ kiểm tra JWT offline |
| JWT trong cookie | JWT đã ký | Kiểm tra JWT, có thể thêm kiểm tra trạng thái | Phụ thuộc cách xử lý thu hồi |
| BFF + session cookie | Session ID | Tra session; BFF quản lý token API | Có thể kết thúc session browser ngay |

**Stateless** ở đây thường chỉ việc resource server có thể xác minh JWT mà không cần lookup trạng thái của từng token trên mỗi request. Không có nghĩa là toàn hệ thống không lưu dữ liệu: authorization server vẫn quản lý người dùng, khóa ký, refresh token, consent, sự kiện thu hồi hoặc trạng thái phiên.

Hạn chế lớn của JWT tự kiểm tra offline là **token đã bị đánh cắp có thể tiếp tục dùng tới khi hết hạn**, trừ khi triển khai cơ chế bổ sung như denylist, phiên bản token, kiểm tra trạng thái hoặc hạn rất ngắn. Đổi khóa ký có thể làm vô hiệu hóa nhiều token đồng thời nên phải có quy trình phù hợp. Ngược lại, session ID hoặc opaque token tra cứu trạng thái thường thuận tiện hơn khi cần thu hồi tức thì, nhưng phải cân nhắc độ sẵn sàng, chi phí tra cứu và cache.

## 4. Sự khác biệt ảnh hưởng trực tiếp tới an toàn bảo mật

### 4.1. XSS và khả năng đọc credential

Nếu token nằm trong <code>localStorage</code> hoặc vùng lưu trữ JavaScript đọc được, mã JavaScript độc hại chạy trong cùng origin do XSS có thể lấy token và gửi ra ngoài. Giữ token chỉ trong bộ nhớ JavaScript có thể giảm thời gian tồn tại, nhưng không ngăn XSS đang chạy truy cập hoặc dùng token.

Cookie đặt <code>HttpOnly</code> giúp JavaScript không đọc trực tiếp giá trị cookie; tuy nhiên, **XSS vẫn có thể gửi request có cookie tự đính kèm, đọc dữ liệu phản hồi cùng origin hoặc thực hiện thao tác thay người dùng**. Bảo vệ XSS vẫn cần mã hóa đầu ra phù hợp ngữ cảnh, tránh đưa HTML không tin cậy vào DOM, kiểm soát thư viện phụ thuộc và cân nhắc CSP.

### 4.2. CSRF và việc trình duyệt tự gửi cookie

Với yêu cầu phù hợp host/path/SameSite, trình duyệt tự mang cookie theo request. Trang độc hại có thể cố khiến trình duyệt người dùng tạo request đến ứng dụng đã đăng nhập. Đây là cơ chế tạo nguy cơ **Cross-Site Request Forgery (CSRF)** khi server chỉ dựa vào cookie và không xác minh ý định của request.

Các biện pháp thường kết hợp:

- Dùng <code>SameSite=Lax</code> hoặc <code>Strict</code> khi phù hợp; <code>SameSite=None</code> bắt buộc đi cùng <code>Secure</code> trong trình duyệt hiện đại và cần có kiểm soát CSRF bổ sung nếu cookie được gửi xuyên site.
- Dùng **CSRF token** được server kiểm tra, hoặc cơ chế kiểm tra <code>Origin</code>/<code>Referer</code> theo chính sách đáng tin cậy, nhất là ở các endpoint thay đổi trạng thái.
- Chỉ sử dụng <code>GET</code> cho thao tác an toàn, không đổi trạng thái. Không mặc định cho rằng SameSite hoặc CORS có thể thay thế mọi kiểm soát CSRF.

Bearer token mà ứng dụng **chủ động** đặt vào header <code>Authorization</code> thường giảm dạng CSRF cổ điển do request từ site khác không tự có header đó. Tuy nhiên, **XSS, rò rỉ token và cấu hình CORS sai** vẫn có thể tạo rủi ro khác. “Cross-origin” và “cross-site” là hai khái niệm khác nhau; CORS điều khiển quyền truy cập cross-origin của script và không phải công tắc xác thực hoặc giải pháp CSRF đầy đủ.

### 4.3. Mất token và replay

Phần lớn session ID và OAuth access token kiểu Bearer đều có tính chất **“ai cầm được thì có thể sử dụng”** trong phạm vi token còn hiệu lực. Kẻ tấn công có thể gửi lại token ở request mới nếu không có ràng buộc bổ sung. Để hạn chế:

1. Bắt buộc HTTPS/TLS; không đặt access token/session ID trong URL hoặc log, analytics, message lỗi và lịch sử trình duyệt.
2. Tạo session ID và opaque token bằng nguồn ngẫu nhiên mật mã, đủ entropy; không dựa vào ID tăng dần hoặc thông tin người dùng có thể đoán.
3. Cấp access token **thời hạn ngắn, audience và scope tối thiểu**. API luôn kiểm tra đúng audience và quyền, kể cả sau khi token được xác thực.
4. Bảo vệ refresh token bằng lưu trữ phù hợp môi trường, rotation/reuse detection hoặc ràng buộc client theo chính sách; thu hồi khi phát hiện lạm dụng.
5. Khi cần giảm replay ở tình huống phù hợp, cân nhắc sender-constrained token như **DPoP** hoặc **mTLS**; các cơ chế này có yêu cầu triển khai riêng, không thay thế xác thực và kiểm tra quyền.

### 4.4. Hết hạn và logout không giống nhau giữa các thiết kế

Xét tình huống người dùng bấm logout lúc 10:00:

- **Server-side session:** backend vô hiệu hóa session trong store, rồi xóa cookie trình duyệt. Session ID cũ bị từ chối ngay ở nơi kiểm tra trạng thái cập nhật.
- **JWT access token tự kiểm tra offline:** nếu JWT còn hạn tới 10:15, xóa bản sao trong trình duyệt **không tự làm JWT hết hiệu lực** ở API. Muốn chặn ngay cần cơ chế thu hồi/kiểm tra trạng thái bổ sung.
- **Refresh token:** server cần hủy hoặc vô hiệu hóa grant/refresh token theo thiết kế. Hủy refresh token ngăn cấp token mới nhưng không nhất thiết làm access token đã phát hành trước đó mất hiệu lực tức thì.

Cookie hết hạn, token hết hạn và session trên server hết hạn là **ba đồng hồ độc lập**. Cần thiết kế chúng phối hợp để tránh trường hợp cookie còn nhưng session chết, hoặc cookie đã xóa nhưng access token bị đánh cắp vẫn được chấp nhận.

## 5. Chọn mô hình nào cho từng ứng dụng?

| Nhu cầu | Điểm khởi đầu hợp lý | Điều cần thiết kế kỹ |
| --- | --- | --- |
| Web app truyền thống render phía server | Server-side session + cookie bảo vệ | Session store, session fixation, CSRF, timeout và logout |
| Single-page app có backend riêng cùng hệ thống | Cân nhắc BFF + session cookie | CSRF, XSS, token OAuth được quản lý tại BFF, cấu hình cookie |
| Mobile/native app gọi API | OAuth 2.0 Authorization Code + PKCE, access token Bearer | Bảo vệ token trong cơ chế lưu trữ hệ điều hành, refresh và audience |
| Service-to-service API | Access token được cấp theo client credentials hoặc cơ chế định danh workload phù hợp | Audience, scope, khóa tin cậy, replay và vòng đời token |
| Nhiều API cần xác minh tại chỗ | JWT access token có chữ ký và validation chặt | Thu hồi sớm, key rotation, kiểm soát audience/scope |
| Hệ thống đòi hỏi thu hồi tức thì và kiểm soát tập trung | Session/opaque token có xác minh trạng thái | Độ trễ/caching của introspection, khả dụng của store |

Không có lựa chọn tốt nhất cho mọi hệ thống. Nên bắt đầu từ trust boundary: **ai phát hành credential, ai sử dụng, credential dùng để truy cập tài nguyên nào, lưu ở đâu, bao giờ hết hạn và thu hồi thế nào**. Sau đó mới quyết định JWT hay opaque, cookie hay header và có cần session store hay không.

## 6. Các nhầm lẫn thường gặp

| Phát biểu | Đánh giá và lý do |
| --- | --- |
| “Có cookie là có session đăng nhập.” | **Sai.** Cookie có thể chỉ chứa tùy chọn giao diện; session có thể dùng cơ chế khác để nhận diện. |
| “Session ID không phải token.” | **Không chính xác về bản chất bảo mật.** Session ID là một định danh thường đóng vai trò bearer credential. |
| “JWT an toàn hơn session vì không cần database.” | **Sai.** Khả năng tự xác minh không đồng nghĩa an toàn hơn; phải đánh giá bảo vệ, claims, thu hồi và vận hành. |
| “JWT đặt vào HttpOnly cookie sẽ không bị CSRF.” | **Sai.** Trình duyệt vẫn tự đính kèm cookie; HttpOnly chủ yếu chống JavaScript đọc giá trị. |
| “JWT đã ký thì payload được giữ bí mật.” | **Sai.** Chữ ký giúp phát hiện sửa đổi và xác thực nguồn ký, không tự mã hóa dữ liệu. |
| “Refresh token dùng như access token để gọi API.” | **Sai.** Refresh token thuộc luồng cấp mới token với authorization server. |
| “API có thể dùng ID token OIDC thay access token.” | **Sai trong thiết kế chuẩn.** ID token có audience/mục đích dành cho OIDC client. |
| “User logout thì mọi JWT đã cấp hết hiệu lực.” | **Không mặc nhiên.** Cần xét thời hạn và cơ chế revocation thực tế. |
| “Cookie có Secure và HttpOnly là đủ.” | **Sai.** Cần thêm chính sách SameSite, CSRF, XSS, session lifecycle và kiểm soát phía server. |

## 7. Tình huống kiểm tra hiểu biết

**Tình huống A.** Người dùng đăng nhập web, thấy header <code>Set-Cookie: __Host-session=abc...</code>. Request kế tiếp gửi <code>Cookie: __Host-session=abc...</code>. Trong database có bản ghi <code>abc... → user-42</code>. 

**Phân tích:** Đây là server-side session; cookie là phương tiện gửi session ID. Để logout an toàn, cần xóa/vô hiệu hóa bản ghi session và xóa cookie. Nếu chỉ xóa cookie, bản sao ID bị lộ vẫn có thể bị replay.

**Tình huống B.** Mobile app lưu access token, gọi API bằng <code>Authorization: Bearer ...</code>. API xác minh chữ ký JWT và từ chối khi <code>aud</code> khác API của nó.

**Phân tích:** Đây là access-token authorization dùng JWT; không đòi hỏi cookie. Xác minh <code>aud</code> chống dùng token được cấp cho một resource khác; API vẫn cần kiểm tra scope và quyền truy cập đối tượng cụ thể.

**Tình huống C.** SPA lưu JWT trong <code>localStorage</code>. XSS đọc token và gửi về server của kẻ tấn công. Đổi sang cookie <code>HttpOnly</code> sẽ khắc phục mọi hậu quả XSS?

**Phân tích:** Cookie HttpOnly giảm khả năng **đọc và lấy trực tiếp giá trị** qua JavaScript, nhưng XSS vẫn có thể gửi request đại diện người dùng. Vẫn phải xử lý nguồn XSS, CSRF và vòng đời token.

**Tình huống D.** Hệ thống thay session ID trong cookie bằng JWT có hạn 60 phút, không có denylist. Sau logout, attacker vẫn giữ JWT đã lấy cắp.

**Phân tích:** Nếu API chỉ kiểm tra chữ ký và <code>exp</code>, attacker có thể dùng lại JWT đến khi hết hạn. Logout phía trình duyệt không đồng nghĩa token được thu hồi tại API.

## 8. Checklist khi thiết kế cơ chế đăng nhập và token

1. **Xác định vai trò:** Đây là session ID, access token, refresh token hay ID token? Ai là issuer và audience?
2. **Xác định nơi đặt credential:** Cookie do browser tự gửi, header Bearer do client tự đặt hay BFF quản lý token?
3. **Xác định nơi lưu trạng thái:** Session store/introspection, xác minh JWT offline hay kết hợp? Khi store/issuer gián đoạn thì sao?
4. **Kiểm chứng khi nhận:** Không tin credential chỉ vì nó có mặt; kiểm tra chữ ký/trạng thái, issuer, audience, thời gian, scope và quyền theo tài nguyên.
5. **Giảm khả năng lộ/replay:** HTTPS, ID khó đoán, lưu trữ phù hợp, không log token, thời hạn ngắn và quyền tối thiểu.
6. **Bảo vệ browser:** Cookie <code>Secure</code>, <code>HttpOnly</code>, <code>SameSite</code> hợp lý; phòng XSS và CSRF theo kênh gửi credential.
7. **Thiết kế hết hạn và thu hồi:** Session expiry, cookie expiry, token expiry, rotation, logout và xử lý token bị đánh cắp phải nhất quán.
8. **Kiểm thử tình huống thất bại:** Token sai audience, hết hạn, thiếu quyền, replay sau logout, CSRF, session fixation, mất session store và thu hồi refresh token.

**Ghi nhớ:** Session nói về **phiên/trạng thái**, token nói về **giá trị được trình ra để xác thực hoặc cấp quyền**, còn cookie nói về **cách trình duyệt lưu và tự gửi dữ liệu**. Ba khái niệm giao nhau trong một kiến trúc bảo mật; hiểu đúng vai trò của từng lớp là bước đầu để thiết kế xác thực, phân quyền và vòng đời OAuth 2.0/OIDC an toàn.
