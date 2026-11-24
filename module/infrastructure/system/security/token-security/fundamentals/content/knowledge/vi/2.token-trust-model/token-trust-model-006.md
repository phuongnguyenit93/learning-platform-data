# Client authentication khác user authentication

Trong mô hình bảo mật token, một request có thể liên quan đến **hai chủ thể khác nhau**: **ứng dụng đang gửi request** và **người đang sử dụng ứng dụng**. Xác thực ứng dụng (*client authentication*) trả lời “ứng dụng/dịch vụ nào đang giao tiếp với hệ thống cấp token?”. Xác thực người dùng (*user authentication*) trả lời “người dùng nào vừa chứng minh danh tính?”. Hai việc có thể xuất hiện trong cùng một luồng OAuth 2.0/OpenID Connect (OIDC), nhưng **không chứng minh thay cho nhau**.

Ví dụ: một ứng dụng đặt hàng có backend `orders-web`. Khi khách hàng đăng nhập, hệ thống định danh xác thực **khách hàng** bằng mật khẩu và MFA. Lúc backend đổi authorization code lấy token, authorization server có thể xác thực **ứng dụng `orders-web`** bằng bí mật hoặc khóa riêng. Sau đó, API kiểm tra **access token** để quyết định request được phép đọc đơn hàng nào. Đây là ba quyết định ở những ranh giới tin cậy khác nhau.

## 1. Phân biệt danh tính, đối tượng được xác thực và mục tiêu

### 1.1. Client authentication: xác thực ứng dụng gọi tới authorization server

Trong OAuth 2.0, **client** là ứng dụng yêu cầu quyền truy cập tài nguyên. Client có thể là backend web, dịch vụ nền, ứng dụng mobile hoặc ứng dụng chạy trong trình duyệt. **Client authentication** là quá trình authorization server kiểm tra client có thực sự kiểm soát thông tin xác thực đã đăng ký hay không, khi luồng đó yêu cầu xác thực client.

Ví dụ:

- Backend `billing-service` gửi `client_id` và chứng minh sở hữu `client_secret` qua kết nối HTTPS tới token endpoint.
- Backend `orders-web` ký một JWT client assertion bằng khóa riêng đã đăng ký; authorization server kiểm tra chữ ký và các claims.
- Dịch vụ máy chủ xác thực bằng mutual TLS (mTLS) với chứng chỉ đã được liên kết với client.

**Điểm cần nhớ:** chứng minh “đây là client X” **không** chứng minh “người dùng A đã đăng nhập”. Một client có thể hoạt động hoàn toàn không có người dùng, chẳng hạn một tác vụ tổng hợp báo cáo chạy theo lịch.

### 1.2. User authentication: xác thực người dùng cuối

**User authentication** là quá trình xác nhận người dùng cuối (*end user*) thực sự là người mà họ tuyên bố. Hệ thống có thể dùng mật khẩu, passkey/WebAuthn, xác thực nhiều yếu tố (MFA), đăng nhập liên kết hoặc phương pháp phù hợp khác. Trong OIDC, **OpenID Provider (OP)** là bên xác thực người dùng và phát hành **ID token** để ứng dụng khách (*Relying Party/OIDC client*) nhận thông tin về sự kiện xác thực.

User authentication có thể diễn ra **trước** hoặc **bên ngoài** quá trình OAuth 2.0 cấp access token. Trong luồng đăng nhập OIDC, authorization server/OpenID Provider thường dùng session đăng nhập riêng để tránh yêu cầu người dùng nhập lại thông tin ở mọi lần ủy quyền.

**Điểm cần nhớ:** việc user đăng nhập thành công **không** biến ứng dụng chạy trong trình duyệt thành một confidential client và cũng không chứng minh ứng dụng đó có thể giữ `client_secret`.

### 1.3. Authorization: quyết định được làm gì sau khi đã xác thực

Xác thực (*authentication*) trả lời **“ai/đối tượng nào?”**; phân quyền (*authorization*) trả lời **“được làm gì, trên tài nguyên nào, trong ngữ cảnh nào?”**. OAuth 2.0 là framework **ủy quyền truy cập**; OIDC xây thêm lớp **xác thực danh tính người dùng** trên OAuth 2.0.

Một client được xác thực có thể **không có quyền** lấy một loại token nhất định. Một user được xác thực cũng có thể **không có quyền** xem hóa đơn của người khác. API phải kiểm tra token và quy tắc phân quyền thực tế; danh tính hợp lệ chưa đủ để cấp quyền.

| Câu hỏi | Client authentication | User authentication | Authorization tại API |
| --- | --- | --- | --- |
| **Xác minh ai?** | Ứng dụng/client đã đăng ký | Người dùng cuối | Principal và quyền trong ngữ cảnh request |
| **Bên kiểm tra thường gặp** | OAuth authorization server/token endpoint | Identity Provider/OP hoặc hệ thống đăng nhập | Resource server/API |
| **Chứng cứ thường gặp** | Client secret, JWT client assertion, chứng chỉ mTLS | Passkey, mật khẩu + MFA, session đăng nhập tại IdP | Access token hợp lệ và các chính sách quyền |
| **Kết quả** | Client được nhận diện/xác thực theo chính sách | User được xác thực, có thể có phiên đăng nhập/ID token | Cho phép hoặc từ chối hành động với tài nguyên |
| **Có cần user không?** | Không nhất thiết | Có | Tùy luồng; token có thể đại diện user hoặc ứng dụng |
| **Giá trị riêng lẻ chưa đủ** | `client_id` công khai | Tên người dùng/email | Chỉ có token mà thiếu audience/scope/quyền phù hợp |

## 2. Đặt các chủ thể vào đúng mô hình tin cậy

Các vai trò liên quan:

- **End user:** người tương tác và chứng minh danh tính; trong nhiều luồng ủy quyền, họ cũng là resource owner.
- **OAuth client:** ứng dụng yêu cầu token, có `client_id` và cấu hình đăng ký tại authorization server.
- **Authorization Server (AS)/OpenID Provider (OP):** phát hành token; có thể xác thực client và user, quản lý grant, consent và chính sách.
- **Resource Server (RS):** API nhận access token và áp dụng chính sách quyền lên tài nguyên.
- **Browser hoặc native app:** môi trường vận hành code phía người dùng; có các giới hạn tin cậy khác với backend.

~~~mermaid
flowchart LR
    U["Người dùng"] -->|"Đăng nhập / MFA"| AS["Authorization Server / OP"]
    B["Browser hoặc mobile app"] -->|"Yêu cầu ủy quyền, client_id + PKCE"| AS
    C["Backend client (nếu có)"] -->|"Client authentication tại token endpoint"| AS
    AS -->|"ID token cho OIDC client"| C
    AS -->|"Access token cho API"| C
    C -->|"Bearer access token"| API["Resource Server / API"]
    API -->|"Xác minh audience, scope và quyền"| API
~~~

Sơ đồ mô tả một cấu hình có backend; với **public client**, chính ứng dụng browser/mobile có thể thực hiện luồng Authorization Code + PKCE và không dùng client secret. Với hệ thống backend-for-frontend (BFF), trình duyệt có thể chỉ giữ session cookie, còn backend quản lý token.

Có ba **ranh giới tin cậy** cần kiểm tra riêng:

1. **User → OP:** phương pháp đăng nhập có đủ tin cậy và có đáp ứng yêu cầu MFA/reauthentication không?
2. **Client → AS:** client thuộc loại nào, có cần/có khả năng xác thực bằng credential bí mật hay không?
3. **Client → API:** token có được AS tin cậy phát hành, dành đúng API, chưa hết hạn và cấp đúng quyền không?

API không nên coi việc nhận một `client_id` trong request là bằng chứng ứng dụng đã được xác thực. Tương tự, client không nên coi việc API trả dữ liệu từ access token là bằng chứng đầy đủ cho danh tính user nếu chưa thực hiện đúng quy trình OIDC.

## 3. Confidential client khác public client

OAuth phân biệt client theo khả năng giữ kín credential; **không dựa đơn thuần vào việc client là web hay mobile**.

| Thuộc tính | Confidential client | Public client |
| --- | --- | --- |
| Môi trường điển hình | Backend chạy trên server với kho bí mật/khóa được bảo vệ | SPA JavaScript, native/mobile/desktop app được phân phối tới người dùng |
| Giữ `client_secret` an toàn? | Có thể, nếu cấu hình và vận hành đúng | Không đáng tin cậy: mã nguồn và secret có thể bị trích xuất |
| Client authentication tại token endpoint | Thường có, theo phương pháp đăng ký | Thường không có xác thực client dựa trên secret; gửi `client_id` để định danh |
| Giảm rủi ro authorization code bị đánh cắp | Dùng PKCE (khuyến nghị kể cả khi client được xác thực) | **Bắt buộc/chuẩn thực hành dùng Authorization Code + PKCE** |
| Token/secret thường lưu ở đâu | Secret/key và token ở backend theo phân quyền chặt | Token ở vùng lưu trữ phù hợp thiết bị; tránh phơi lộ, giới hạn thời gian |

**`client_id` không phải mật khẩu.** Nó thường xuất hiện trong URL yêu cầu ủy quyền và không được xem là bí mật. Cặp `client_id` + `redirect_uri` có thể giúp AS xác định đăng ký ứng dụng, nhưng **không đủ** để chứng minh bên gọi kiểm soát một confidential client.

Đưa `client_secret` vào mã JavaScript, bundle mobile, ứng dụng desktop hoặc cấu hình có thể tải về **không khiến ứng dụng trở thành confidential client**. Secret bị nhúng trong ứng dụng phát cho người dùng cần được xem là có khả năng bị lộ.

**PKCE không phải client authentication.** PKCE ràng buộc lần đổi authorization code với bên khởi tạo yêu cầu thông qua `code_verifier` và `code_challenge`, giúp chống chặn/lấy trộm authorization code. Nó không chứng minh danh tính ứng dụng bằng bí mật được AS giữ riêng cho một client. Public client cần PKCE nhưng vẫn là public client.

## 4. Các phương thức client authentication thường gặp

| Phương thức tại token endpoint | Client chứng minh điều gì? | Lưu ý bảo mật |
| --- | --- | --- |
| **`client_secret_basic`** | Biết secret đã đăng ký, qua HTTP Basic Authentication | Chỉ dùng với TLS; secret phải ở backend; tránh ghi log header |
| **`client_secret_post`** | Gửi client secret trong body của token request | Được hỗ trợ ở một số AS nhưng thường kém ưu tiên hơn Basic vì dễ lọt vào log/body tracing |
| **`private_key_jwt`** | Sở hữu khóa riêng bằng JWT assertion có chữ ký | Kiểm tra chữ ký, `iss`, `sub`, `aud`, `exp`, `jti`/chống replay theo chính sách |
| **mTLS client authentication** | Sở hữu khóa riêng tương ứng với chứng chỉ client đã đăng ký | Quản lý PKI, hiệu lực/thu hồi chứng chỉ và cấu hình TLS đúng |
| **`none` (không xác thực client)** | Chỉ khai báo client identity trong request; không chứng minh sở hữu secret | Thường dùng cho public client; kết hợp PKCE, redirect URI registration và biện pháp khác |

Ví dụ một confidential client xin token theo **Client Credentials grant** (giả sử authorization server cho phép và client đã đăng ký):

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.com
Authorization: Basic <base64(client_id:client_secret)>
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials&scope=reports%3Aread
~~~

Header `Authorization: Basic` phải được tạo từ credential client đã đăng ký và gửi qua **HTTPS**. Ví dụ dùng placeholder; không đặt secret thật trong source code, URL hoặc log.

Ví dụ rút gọn với **`private_key_jwt`**:

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.com
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials&client_id=reports-service&client_assertion_type=urn%3Aietf%3Aparams%3Aoauth%3Aclient-assertion-type%3Ajwt-bearer&client_assertion=<signed-client-JWT>
~~~

JWT assertion được ký bằng **khóa riêng của client**, không phải access token hoặc ID token. Các claims thường có:

~~~json
{
  "iss": "reports-service",
  "sub": "reports-service",
  "aud": "https://auth.example.com/oauth2/token",
  "exp": 1795390000,
  "iat": 1795389940,
  "jti": "unique-one-time-id"
}
~~~

Trong phương thức client assertion này, `iss` và `sub` thường là **client ID**, còn `aud` trỏ đến authorization server/token endpoint theo yêu cầu của nhà cung cấp. Giá trị thời gian và `jti` chỉ mang tính minh họa; thực tế phải dùng thời gian hiện tại, thời hạn rất ngắn và ID chống replay duy nhất. AS phải kiểm tra cả chữ ký, thuật toán, khóa đăng ký và các claims.

**mTLS và DPoP không đồng nghĩa:** mTLS có thể dùng **để xác thực OAuth client** tại AS, đồng thời có thể dùng để ràng buộc access token với chứng chỉ. DPoP dùng bằng chứng sở hữu khóa để **ràng buộc token với bên gửi request**, nhưng không tự động xác thực danh tính OAuth client trong mọi cấu hình. Đó là các cơ chế/bước kiểm tra khác nhau.

## 5. Khi cả client và user đều được xác thực: Authorization Code + OIDC

Xét website có backend `orders-web`; người dùng muốn đăng nhập và xem đơn hàng qua API.

~~~mermaid
sequenceDiagram
    autonumber
    actor U as Người dùng
    participant B as Trình duyệt
    participant C as Backend client
    participant AS as Authorization Server / OP
    participant API as Orders API
    U->>B: Chọn Đăng nhập
    B->>C: GET /login
    C-->>B: Redirect tới /authorize + client_id, state, PKCE
    B->>AS: Authorization request
    AS->>U: Yêu cầu đăng nhập, có thể MFA/consent
    U-->>AS: Hoàn thành user authentication
    AS-->>B: Redirect code + state về redirect_uri
    B->>C: Chuyển authorization code
    C->>C: Kiểm tra state, lấy code_verifier tương ứng
    C->>AS: POST /token + code, PKCE + client authentication
    AS->>AS: Kiểm tra code, verifier và client
    AS-->>C: Access token + ID token (OIDC) và có thể refresh token
    C->>C: Validate ID token, tạo session đăng nhập ứng dụng
    C->>API: GET /orders, Bearer access token
    API->>API: Validate access token, audience, scope, quyền sở hữu
    API-->>C: Dữ liệu được cấp quyền hoặc lỗi
~~~

Trong luồng này có **hai lần xác thực đối tượng khác nhau**:

1. **User authentication** xảy ra khi OP xác minh người dùng trong bước đăng nhập/MFA; kết quả liên quan user `sub`, thời điểm và cách xác thực.
2. **Client authentication** xảy ra khi backend đổi code tại token endpoint; AS xác nhận `orders-web` thực sự là client đã đăng ký, bằng secret/khóa hoặc phương thức tương ứng.

Ngoài ra còn có **validation/authorization** của API đối với access token. API kiểm tra token do issuer tin cậy phát hành, có đúng audience và scope/quyền hay không. Đây không nhất thiết là một lần đăng nhập lại của user hay một lần client authentication trực tiếp giữa API và OAuth client.

Ví dụ authorization request ở mức khái niệm:

~~~text
GET https://auth.example.com/authorize
  ?response_type=code
  &client_id=orders-web
  &redirect_uri=https%3A%2F%2Fapp.example.com%2Fcallback
  &scope=openid%20profile%20orders.read
  &state=<random-state>
  &code_challenge=<S256-code-challenge>
  &code_challenge_method=S256
~~~

`state` giúp client liên kết response với yêu cầu đã khởi tạo và chống một số dạng CSRF/mix-up theo triển khai; `code_challenge` là giá trị dẫn xuất từ `code_verifier` dùng trong PKCE. Trong ứng dụng OIDC, `nonce` cũng được dùng theo luồng/yêu cầu bảo mật để liên kết ID token với phiên xác thực; cần kiểm tra khi đã gửi. `redirect_uri` phải được đối chiếu đúng đăng ký và yêu cầu ban đầu.

Token request rút gọn:

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.com
Authorization: Basic <credentials-of-orders-web>
Content-Type: application/x-www-form-urlencoded

grant_type=authorization_code&code=<one-time-code>&redirect_uri=https%3A%2F%2Fapp.example.com%2Fcallback&code_verifier=<original-verifier>
~~~

Ở request này, `code_verifier` **bảo vệ authorization code**, còn HTTP Basic **xác thực confidential client**. User đã được xác thực trong bước tại OP; client không dùng mật khẩu người dùng để tự chứng minh danh tính ứng dụng.

### 5.1. Nếu client là SPA hoặc mobile app thì sao?

Public client cũng sử dụng **Authorization Code + PKCE** để user đăng nhập tại OP. Nó thường gửi `client_id` nhưng **không gửi client secret** tại token endpoint. Việc thiếu client authentication bằng secret là đặc điểm thiết kế hợp lệ của public client, không phải bỏ qua mọi kiểm tra. AS vẫn phải xác thực authorization code, `redirect_uri`, PKCE, hạn/single-use của code và chính sách cấp token.

Nếu ứng dụng muốn giảm việc token hiện diện trong browser JavaScript, có thể dùng **BFF**: backend thực hiện trao đổi token và giữ access/refresh token; trình duyệt chỉ mang session cookie được bảo vệ. Cookie chứng minh phiên đăng nhập tại ứng dụng thông qua việc server tra session, **không phải tự thân là bằng chứng client authentication của backend đối với AS**.

## 6. Khi chỉ có client authentication: Client Credentials grant

Một dịch vụ thu thập số liệu chạy theo lịch có thể cần gọi API mà **không có người dùng hiện diện**. Nó dùng OAuth 2.0 Client Credentials grant nếu được authorization server hỗ trợ:

~~~mermaid
sequenceDiagram
    autonumber
    participant C as reports-service
    participant AS as Authorization Server
    participant API as Metrics API
    C->>AS: POST /token: client_credentials + client authentication
    AS->>AS: Kiểm tra client và quyền grant/scope
    AS-->>C: Access token dành cho Metrics API
    C->>API: GET /metrics + Bearer access token
    API->>API: Xác minh token, aud, scope và policy dịch vụ
    API-->>C: Dữ liệu hoặc 401/403
~~~

Ở đây:

- Client được xác thực (ví dụ bằng mTLS hoặc `private_key_jwt`).
- **Không có bước user authentication** và thường **không có ID token OIDC**.
- Access token đại diện cho **quyền của ứng dụng/dịch vụ** trong phạm vi grant, không phải hành động của một user bất kỳ.
- Một số định dạng JWT access token đặt `sub` là client ID trong client credentials grant; các hệ thống có thể biểu diễn principal theo cách khác. **Không suy ra có người dùng chỉ vì token có claim `sub`.**

Nếu một API yêu cầu quyền thao tác trên tài nguyên của user, **không tự lấy token của `client_credentials` rồi tự đặt `userId` để “thay mặt” user**. Cần một cơ chế ủy quyền phù hợp như user-delegated access token hoặc token exchange/on-behalf-of theo chính sách của hệ thống.

Ngược lại, việc user đã đăng nhập vào web app cũng **không cho phép** backend tùy ý dùng quyền ứng dụng để vượt qua phân quyền theo user. API phải xác định request thuộc ngữ cảnh **app-only** hay **delegated user** và thực hiện chính sách riêng.

## 7. Các token và claims phản ánh danh tính nào?

Không thể kết luận chỉ từ việc token là JWT. **JWT hay opaque** nói về hình thức token; **access token, refresh token và ID token** nói về vai trò; **client authentication và user authentication** nói về đối tượng được xác thực.

| Vật mang thông tin | Người/ứng dụng liên quan | Bên sử dụng đúng | Cần chú ý |
| --- | --- | --- | --- |
| **Client secret / client assertion** | Danh tính OAuth client | Authorization server | Không đem đi gọi resource API như access token |
| **Authorization code** | Yêu cầu ủy quyền đã khởi tạo của client/user | Token endpoint | Ngắn hạn, dùng một lần, ràng buộc redirect URI/PKCE và client |
| **Access token** | Quyền truy cập được cấp cho client; có thể là app-only hoặc delegated user | Resource server/API | Kiểm tra issuer, audience, thời hạn, scope và chính sách |
| **ID token (OIDC)** | Sự kiện xác thực **user** và danh tính user được trình cho OIDC client | OIDC client/Relying Party | `aud` là client, không dùng làm bearer access token cho API |
| **Refresh token** | Grant được phép tiếp tục cấp token cho client | Authorization server/token endpoint | Bảo vệ, giới hạn, rotation/revocation theo chính sách |
| **Session cookie** | Phiên đang được ứng dụng hoặc OP duy trì | Máy chủ sở hữu session | Không đồng nhất với client credential; bảo vệ XSS/CSRF/session hijacking |

### 7.1. ID token xác thực user với client

Ví dụ minh họa một ID token JWT do OP phát hành:

~~~json
{
  "iss": "https://auth.example.com",
  "sub": "user-42",
  "aud": "orders-web",
  "iat": 1795380000,
  "exp": 1795380600,
  "auth_time": 1795379980,
  "amr": ["pwd", "otp"]
}
~~~

`sub` là định danh ổn định trong phạm vi issuer cho **end user**; `aud` chỉ ra OIDC client được nhận ID token. Claims `auth_time` (thời điểm xác thực) và `amr` (phương thức xác thực) có thể có tùy yêu cầu/OP. Claim `acr` có thể biểu thị lớp ngữ cảnh/mức đảm bảo xác thực; **không tự diễn giải** `acr`/`amr` thành “đã MFA đủ chuẩn” nếu chưa có chính sách và hợp đồng ý nghĩa rõ ràng với OP.

OIDC client phải kiểm tra ID token theo quy tắc của luồng tương ứng: issuer, audience, chữ ký/thuật toán khi yêu cầu, hạn, nonce khi áp dụng và các ràng buộc khác. Việc nhìn thấy email hoặc `sub` trong payload JWT **không đủ để xác thực user** nếu chưa kiểm tra tính hợp lệ của token.

### 7.2. Access token cấp quyền cho API, không mặc nhiên chứng minh phiên đăng nhập

Ví dụ minh họa JWT access token dành cho Orders API:

~~~json
{
  "iss": "https://auth.example.com",
  "sub": "user-42",
  "aud": "https://api.example.com/orders",
  "client_id": "orders-web",
  "scope": "orders.read",
  "iat": 1795380000,
  "exp": 1795380900
}
~~~

Đây chỉ là **một cách định nghĩa claims**, không phải mọi token đều có `client_id` hoặc cùng cấu trúc. Với một profile/token format cụ thể, có thể gặp `azp`, `client_id`, `appid` hoặc claim khác xác định client được cấp token. **API phải dựa trên profile và tài liệu của issuer**, không tự mặc định mọi `sub` đều là user hoặc `azp` luôn có ý nghĩa giống nhau.

Đối với JWT access token, API phải xác minh chữ ký với khóa/thuật toán được tin cậy, `iss`, `aud`, `exp`, `nbf` nếu có, mục đích token, scope và quyền trên đối tượng được yêu cầu. Đối với **opaque token**, API cần tra cứu/introspection qua kênh bảo mật hoặc theo giải pháp của AS để có trạng thái và metadata tương đương. Dù là loại token nào, **user authentication trước đó không loại bỏ kiểm tra authorization hiện tại**.

Ví dụ: claim `scope: orders.read` cho phép truy cập chức năng đọc đơn hàng, nhưng **không có nghĩa user-42 được đọc mọi đơn hàng**. API vẫn phải kiểm tra đơn hàng được yêu cầu có thuộc phạm vi quyền của user, tenant hoặc service principal đó hay không.

### 7.3. Một token hợp lệ không thay thế các bước xác thực còn lại

- **ID token hợp lệ:** cho OIDC client thông tin về user authentication, không tự thay client authentication tại token endpoint.
- **Client assertion hợp lệ:** chứng minh client sở hữu khóa, không chứng minh user đã đăng nhập.
- **Access token hợp lệ:** chứng minh yêu cầu có credential được cấp để truy cập API theo policy, nhưng không có nghĩa API được bỏ kiểm tra audience/scope/quyền hoặc tự dùng token đó để đăng nhập user vào ứng dụng khác.
- **Refresh token hợp lệ:** cho phép xin token mới khi thỏa chính sách, không phải credential gửi trực tiếp tới resource API.

## 8. Lỗi thiết kế thường gặp và cách xử lý

### 8.1. Đặt client secret trong SPA rồi gọi đó là “đã xác thực client”

**Sai:** secret trong bundle JavaScript có thể bị mọi người dùng tải và phân tích. Khi secret lộ, attacker có thể giả danh client ở những luồng cho phép.

**Đúng:** SPA được đăng ký như **public client**, dùng Authorization Code + PKCE, redirect URI và các ràng buộc cần thiết; hoặc chuyển phần cần secret về backend/BFF được kiểm soát.

### 8.2. Tin rằng login user thành công đồng nghĩa client đã được xác thực

**Sai:** người dùng đăng nhập với OP không chứng minh app có quyền dùng client identity đăng ký. Một trang giả có thể dụ user đăng nhập hoặc chiếm code nếu thiếu kiểm soát redirect/PKCE.

**Đúng:** AS kiểm tra riêng client registration, redirect URI, PKCE, grant và client authentication khi thích hợp; ứng dụng dùng ID token đúng cách để xác minh user.

### 8.3. Dùng client credentials để thực hiện quyền của user

**Sai:** token app-only không mang sự ủy quyền của một user cụ thể. Dùng token này để bỏ qua kiểm tra quyền trên hóa đơn, dữ liệu cá nhân hoặc tenant có thể tạo lỗ hổng leo thang quyền.

**Đúng:** tách endpoint/quyền dành cho dịch vụ khỏi endpoint yêu cầu delegated user. Kiểm tra principal type, scope/role, tenant và quyền trên từng tài nguyên; dùng quy trình delegation/on-behalf-of nếu có nhu cầu thay mặt user.

### 8.4. Dùng ID token để gọi API vì “nó có chữ ký và sub”

**Sai:** `aud` của ID token thường là OIDC client; API cần access token dành **đúng audience của API**. Chấp nhận nhầm token dẫn tới **token substitution/confused deputy**.

**Đúng:** API từ chối ID token và access token của resource khác, dù chữ ký hợp lệ. OIDC client kiểm tra ID token; resource server kiểm tra access token theo chuẩn/profile được thống nhất.

### 8.5. Tin client_id hoặc user_id được gửi trong body

~~~http
POST /orders/123/refund HTTP/1.1
Host: api.example.com
Authorization: Bearer <access-token>
Content-Type: application/json

{"userId": "admin", "client_id": "trusted-app"}
~~~

**Sai:** giá trị tự khai trong body/header/query không chứng minh danh tính hay quyền. **Đúng:** principal và quyền phải được rút ra từ credential đã được **xác minh**, đối chiếu với tài nguyên và chính sách; bỏ qua hoặc kiểm tra chặt các tham số có thể bị giả mạo.

### 8.6. Bỏ qua vòng đời credential và thu hồi

Rò rỉ **client secret/khóa riêng** có thể cho attacker giả danh ứng dụng để xin token mới theo grant được cấp. Rò rỉ **user session/access token** có thể dẫn đến giả danh user hoặc replay token còn hiệu lực. Rò rỉ **refresh token** có thể kéo dài khả năng truy cập nếu không có cơ chế phát hiện/thu hồi.

Biện pháp cần tương ứng với thứ bị lộ:

| Sự cố | Hành động liên quan |
| --- | --- |
| Lộ client secret/private key | Vô hiệu hóa/rotate client credential, kiểm tra token/grant liên quan, rà soát quyền client |
| Chiếm quyền user/session | Thu hồi session/refresh token theo chính sách, yêu cầu xác thực lại, điều tra đăng nhập bất thường |
| Lộ access token Bearer | Thu hồi nếu có thể; giảm thời hạn, scope và audience; xem xét sender-constrained token |
| Replay client assertion | Giới hạn `exp`, kiểm tra `aud`, dùng `jti` chống tái sử dụng và khóa tin cậy |
| Rò rỉ token trong log | Loại bỏ log credential, bảo vệ dữ liệu đã ghi, xoay credential/token khi cần |

**Logout user không tự động rotate client secret**; **rotate client secret không tự logout mọi user**; **thu hồi refresh token không nhất thiết vô hiệu ngay access token đã phát hành**. Vòng đời từng credential phải được thiết kế tường minh.

## 9. Lựa chọn mô hình theo tình huống

| Bối cảnh | Có user authentication? | Client authentication? | Cách điển hình |
| --- | --- | --- | --- |
| Website backend cho người dùng đăng nhập | Có, tại OP/IdP | Có, nếu backend là confidential client | OIDC Authorization Code + PKCE; client auth tại token endpoint; BFF/session cookie nếu phù hợp |
| SPA thuần frontend đăng nhập | Có | Không có secret-based client authentication | OIDC Authorization Code + PKCE, public client, xử lý token và redirect URI an toàn |
| Mobile app đăng nhập | Có | Thường không dựa trên client secret | OIDC Authorization Code + PKCE qua browser hệ thống, token storage theo nền tảng |
| Job/service gọi API nội bộ theo lịch | Không cần user | Có | OAuth Client Credentials, scope/audience cho dịch vụ |
| API nhận access token từ nhiều client | Không xác thực user trực tiếp ở mọi request | Không nhất thiết xác thực lại client trực tiếp ở mỗi request | Xác minh token từ AS, phân biệt app-only/delegated user và thực thi policy |
| User vào ứng dụng có session cookie | Đã xảy ra khi tạo phiên | Không suy ra có client authentication OAuth | Web server tra session và kiểm tra quyền; bảo vệ cookie/CSRF |

Các kết luận trong bảng là **mô hình thường gặp**, không phải luật tuyệt đối: nhà cung cấp định danh, yêu cầu bảo mật và cấu trúc triển khai có thể khác. Điều quan trọng là mô tả rõ ai xác thực ai, qua chứng cứ gì và với quyền hạn nào.

## 10. Tình huống tự kiểm tra

**Tình huống A.** Một ứng dụng mobile chứa `client_id=shop-mobile` và `client_secret=top-secret` hardcode. Nhà phát triển khẳng định chỉ người dùng ứng dụng chính hãng mới có thể gọi token endpoint vì đã có client secret.

**Phân tích:** Sai. Bí mật phân phối cùng ứng dụng có thể bị trích xuất. Cần đăng ký public client, dùng Authorization Code + PKCE và cơ chế bảo vệ phù hợp; các kỹ thuật attestation nếu áp dụng chỉ cung cấp tín hiệu bổ sung theo thiết kế.

**Tình huống B.** `inventory-service` dùng `private_key_jwt` để nhận access token theo client credentials. API thấy `sub=inventory-service` và trả về thông tin đơn hàng của `user-42` mà không kiểm tra quyền ứng dụng.

**Phân tích:** Đây là client authentication/app-only authorization, không có user authentication cho user-42. API phải kiểm tra scope, audience và quyền dịch vụ trên tài nguyên; không mặc định ứng dụng có thể hành động như user.

**Tình huống C.** OIDC client nhận ID token có `sub=user-42`, `aud=orders-web`. Một API khác `payments-api` chấp nhận ID token đó vì chữ ký đúng và user chưa hết hạn.

**Phân tích:** Sai audience và sai loại token cho mục tiêu API. `payments-api` phải yêu cầu access token dành cho chính nó và kiểm tra quyền, không sử dụng ID token của OIDC client để phân quyền API.

**Tình huống D.** Backend xác thực client bằng mTLS khi đổi authorization code, nhưng người dùng đã bị attacker chiếm session đăng nhập ở OP.

**Phân tích:** mTLS chứng minh client sở hữu khóa/chứng chỉ, **không bảo đảm user authentication trước đó không bị chiếm đoạt**. Cần bảo vệ session user, đánh giá mức đảm bảo đăng nhập/MFA, nonce/state/PKCE theo luồng và theo dõi sự kiện bất thường.

**Tình huống E.** SPA sử dụng PKCE và cho rằng có thể bỏ bước validation ID token vì “AS đã kiểm tra code_verifier”.

**Phân tích:** PKCE bảo vệ việc đổi code; nó không thay thế validation ID token hoặc kiểm tra issuer, audience, hạn và nonce khi áp dụng. Các bước giải quyết những nguy cơ khác nhau.

## 11. Checklist khi thiết kế OAuth 2.0/OIDC

1. **Gọi tên đúng principal:** request này đại diện user, app/service, hay cả hai ở những bước khác nhau?
2. **Đăng ký đúng loại client:** confidential hay public; secret/khóa có thực sự được bảo vệ ở backend không?
3. **Chọn luồng phù hợp:** user login thì OIDC Authorization Code + PKCE; job app-only có thể dùng Client Credentials theo chính sách.
4. **Chọn phương thức client auth:** secret, `private_key_jwt`, mTLS hoặc không có đối với public client; kiểm tra cấu hình token endpoint.
5. **Bảo vệ xác thực user:** chọn MFA/passkey khi phù hợp, quản lý session, đánh giá `auth_time`, `acr`/`amr` khi chính sách yêu cầu.
6. **Phân biệt credential:** ID token cho OIDC client, access token cho API, refresh token cho AS; không tái sử dụng sai mục đích.
7. **Kiểm tra access token tại API:** issuer tin cậy, chữ ký/introspection, audience, thời hạn, scope, principal type, tenant và quyền trên tài nguyên.
8. **Ngăn lộ và replay:** HTTPS, không nhúng secret vào public client, không log token, thời hạn ngắn, rotation/revocation và sender constraint khi cần.
9. **Thử các case âm:** client giả với `client_id` thật; PKCE sai; user chưa đăng nhập; token app-only giả user; ID token đưa vào API; sai `aud`/`scope`; replay assertion.

**Kết luận:** **Client authentication** xác thực ứng dụng với authorization server; **user authentication** xác thực con người với hệ thống định danh; **authorization** kiểm soát quyền đối với tài nguyên. OAuth 2.0/OIDC có thể kết hợp cả ba, nhưng mỗi bước đòi hỏi chứng cứ và quy tắc kiểm tra riêng. Nhận diện đúng **chủ thể, bên xác minh, loại token và ranh giới tin cậy** giúp tránh nhầm lẫn giữa quyền ứng dụng, phiên đăng nhập của user và quyền truy cập API.
