# Device authorization endpoint

## 1. Endpoint này giải quyết vấn đề gì?

Trong chương **Device authorization** của module `SECURITY_TOKEN_SECURITY_FUNDAMENTALS`, **device authorization endpoint** là điểm khởi đầu của **OAuth 2.0 Device Authorization Grant (RFC 8628)**. Nó cho phép một client trên thiết bị **có khả năng nhập liệu hoặc trình duyệt hạn chế** — ví dụ TV, đầu phát, máy in, thiết bị phòng họp hoặc CLI chạy trên máy không có browser — yêu cầu authorization server (AS) tạo **giao dịch ủy quyền qua thiết bị khác**.

Ví dụ: Alice muốn đăng nhập ứng dụng `living-room-tv` để xem thư viện video riêng. TV có kết nối mạng nhưng việc nhập username, mật khẩu hoặc mã MFA bằng remote rất bất tiện. TV không nên yêu cầu Alice đọc mật khẩu cho chính ứng dụng TV hoặc gửi mật khẩu đến một endpoint tự chế. Thay vào đó:

1. TV (OAuth client) gọi **device authorization endpoint** của AS `https://auth.example.test`.
2. AS cấp một `device_code` bí mật cho TV, một `user_code` dễ nhập và `verification_uri` để người dùng mở trên điện thoại/laptop.
3. TV hiển thị hướng dẫn: “Mở trang được chỉ định và nhập mã này”.
4. Alice dùng **trình duyệt trên thiết bị thứ hai**, đăng nhập trực tiếp với AS, xem đúng client/quyền được yêu cầu và xác nhận hoặc từ chối.
5. TV không nhận token từ device authorization endpoint; TV dùng `device_code` để **poll token endpoint** theo khoảng thời gian AS quy định. Chỉ sau khi AS ghi nhận quyền hợp lệ, token endpoint mới có thể cấp access token.

> **Phân biệt trọng tâm:** **Device authorization endpoint khởi tạo giao dịch và trả mã/hướng dẫn**, **verification URI phục vụ người dùng**, còn **token endpoint mới cấp token**. Không dùng `user_code` hoặc `device_code` trực tiếp làm access token gọi resource server.

Trong module về mô hình tin cậy và vòng đời token, lựa chọn này nối ba lớp bảo mật: **AS** xác thực user và ra quyết định authorization; **OAuth client** chỉ dùng credential của flow; **resource server (RS)** xác minh access token sau khi được cấp (JWT hoặc opaque), kiểm tra issuer, audience, scope, thời hạn và quyền trên tài nguyên.

### Mục tiêu học tập

Sau bài, bạn có thể:

- Xác định khi nào nên dùng Device Authorization Grant thay vì Authorization Code + PKCE hoặc Client Credentials.
- Gửi đúng HTTP request tới **device authorization endpoint** và diễn giải mọi trường response theo RFC 8628.
- Phân biệt `device_code`, `user_code`, `verification_uri`, `verification_uri_complete`, `expires_in` và `interval`.
- Triển khai và kiểm tra polling tại **token endpoint** mà không vi phạm rate limit hoặc vô tình nhân bản request.
- Thiết kế AS lưu transaction, bind client, giới hạn thử mã, expiry, chống device-code phishing và chống phát lại.
- Gắn quyền được cấp với client, user, scope, audience và vòng đời access/refresh token; áp dụng Java/Spring và bộ kiểm thử bảo mật.

## 2. Bốn vai trò OAuth và ba endpoint phải tách bạch

Device Authorization Grant **không thay thế** bốn vai trò OAuth:

| Vai trò | Trách nhiệm trong ví dụ |
| --- | --- |
| **Resource Owner** | Alice quyết định có cho TV truy cập dữ liệu của mình hay không, trong giới hạn quyền Alice đang có |
| **Client** | Ứng dụng `living-room-tv` gửi request bắt đầu flow, hiển thị mã và poll lấy token |
| **Authorization Server (AS)** | Xác thực Alice tại verification URI, đánh giá client/scope/resource/consent và phát token tại token endpoint |
| **Resource Server (RS)** | `media-api` nhận access token từ TV, xác minh token và thực thi quyền đọc nội dung |

Ba endpoint/URI chính:

| Nơi | Ai truy cập? | Tác dụng | Có cấp access token ở đây không? |
| --- | --- | --- | --- |
| **Device authorization endpoint** | Device client gọi bằng HTTPS POST | Tạo giao dịch, trả `device_code`, `user_code`, `verification_uri`, thời hạn/poll interval | **Không** |
| **Verification URI** | Alice mở bằng browser trên thiết bị khác | Đăng nhập, nhập/xác nhận mã, xem client/quyền và approve/deny | **Không gửi token về TV từ trang này** |
| **Token endpoint** | TV gọi HTTPS POST định kỳ với `device_code` | Kiểm tra trạng thái pending/approved/denied/expired, cấp AT nếu đủ điều kiện | **Có, khi grant hợp lệ** |

Với AS dùng OAuth Authorization Server Metadata (RFC 8414), metadata có thể công bố endpoint riêng qua khóa `device_authorization_endpoint`. Nó **không đồng nghĩa** `authorization_endpoint` của Authorization Code flow và **không** phải `token_endpoint`.

### 2.1. Luồng đầy đủ

~~~mermaid
sequenceDiagram
    autonumber
    actor U as Alice
    participant TV as TV / OAuth Client
    participant AS as Authorization Server
    participant BR as Browser điện thoại
    participant RS as media-api / RS
    TV->>AS: POST device_authorization (client_id, scope)
    AS->>AS: Kiểm tra client, policy; tạo transaction
    AS-->>TV: device_code, user_code, verification_uri, expires_in, interval
    TV-->>U: Hiển thị URL và user_code
    TV->>AS: POST /token (device_code, grant type)
    AS-->>TV: authorization_pending
    U->>BR: Mở verification_uri từ AS
    BR->>AS: Nhập user_code; login/MFA nếu cần
    AS->>U: Hiển thị client, quyền, xác nhận thiết bị
    U-->>AS: Approve hoặc deny
    TV->>AS: POST /token sau interval
    alt User approve, grant hợp lệ
        AS-->>TV: access_token (+ refresh_token nếu policy)
        TV->>RS: Authorization: Bearer access_token
        RS->>RS: Verify iss, aud, exp, scope, domain ACL
        RS-->>TV: Dữ liệu được phép
    else User deny hoặc code expired
        AS-->>TV: access_denied / expired_token
        TV->>TV: Dừng polling, hủy transaction
    end
~~~

**Chú ý:** TV có thể poll **trước** khi Alice mở trang; `authorization_pending` lúc đó là phản hồi bình thường. TV không được poll liên tục không giới hạn chỉ vì chưa nhận được token.

### 2.2. Device flow không tự chứng minh danh tính thiết bị

Một `client_id` của public client thường không bí mật và không đủ để chứng minh phần mềm/thiết bị vật lý là “TV chính hãng”. Device Authorization Grant tạo một mối liên hệ giữa **giao dịch trên device** và **hành động của user tại AS**. Nếu ứng dụng cần quản lý thiết bị đã đăng ký, attestation, mTLS hoặc workload identity, đó là **lớp bổ sung có policy riêng**, không phải đặc tính mặc định của `device_code`.

Đồng thời, việc Alice approve trên điện thoại không chứng minh TV được phép truy cập mọi API. AS còn phải quyết định **scope và audience**, RS tiếp tục thực thi authorization.

## 3. Khi nào nên dùng device authorization endpoint?

| Tình huống | Lựa chọn phù hợp để đánh giá | Vì sao |
| --- | --- | --- |
| TV có remote, không có browser nhập liệu đầy đủ | **Device Authorization Grant** nếu AS hỗ trợ | User hoàn tất login trên thiết bị khác |
| CLI từ phiên SSH/headless, có user chủ động login | **Device Authorization Grant** hoặc Authorization Code qua browser/loopback nếu khả dụng | Không thu password trên CLI |
| Mobile/desktop có external system browser | **Authorization Code + PKCE** thường phù hợp hơn | Có user-agent và redirect nhận code |
| Web backend/BFF có browser và session | **Authorization Code + PKCE**, OIDC nếu cần login | Backend giữ token, user login tại AS |
| SPA thuần browser | **Authorization Code + PKCE** | Public client vẫn có thể dùng code flow |
| Batch job không có end-user tham gia | **Client Credentials** hoặc workload federation | Quyền của service, không yêu cầu user nhập code |
| Service A muốn gọi service B thay Alice | **Token Exchange/OBO** nếu AS hỗ trợ | Giữ chính sách delegation subject/actor/audience |

**Không chọn device flow** chỉ vì muốn né MFA, consent, redirect validation hoặc client registration. Device Grant phù hợp với khả năng nhập liệu của thiết bị, **không phải flow ít kiểm tra hơn**.

### 3.1. Device client public hay confidential?

Một TV/desktop app phân phối tới người dùng thường là **public client**: secret hardcode trong firmware/binary có thể bị trích xuất. Khi đó request khởi tạo dùng `client_id` công khai và token endpoint phải kiểm tra binding theo flow, **không giả định có secret bí mật**.

Một client chạy trên backend kiểm soát được credential có thể là confidential và xác thực client theo registration/AS policy. RFC 8628 cho phép client có khả năng xác thực tự thực hiện client authentication theo OAuth; tuy nhiên **không yêu cầu mọi device client có client secret** và không dùng public `client_id` thay client authentication của confidential client.

### 3.2. Điều kiện tối thiểu từ authorization server

Trước khi triển khai, cần xác nhận:

1. AS hỗ trợ **Device Authorization Grant (RFC 8628)** và đã cho client sử dụng grant tương ứng.
2. AS công bố/cấu hình **device authorization endpoint**, `token_endpoint` và `verification_uri` tin cậy.
3. Client được phép xin scope/resource phù hợp; AS có chính sách consent, user authentication và rủi ro thiết bị.
4. TLS, certificate/hostname validation, retry/rate-limit và trạng thái transaction được triển khai.
5. Resource server có validation độc lập (JWT/JWKS hoặc opaque introspection), expected audience và authorization theo user/tenant/object.

## 4. Xác định device authorization endpoint đáng tin

Một AS có thể hỗ trợ metadata ở:

~~~text
https://auth.example.test/.well-known/oauth-authorization-server
~~~

Một metadata response minh họa:

~~~json
{
  "issuer": "https://auth.example.test",
  "authorization_endpoint": "https://auth.example.test/oauth2/authorize",
  "token_endpoint": "https://auth.example.test/oauth2/token",
  "device_authorization_endpoint": "https://auth.example.test/oauth2/device_authorization",
  "jwks_uri": "https://auth.example.test/oauth2/jwks",
  "grant_types_supported": [
    "authorization_code",
    "urn:ietf:params:oauth:grant-type:device_code"
  ]
}
~~~

Đây là **ví dụ**, không phải một AS thật hoặc path bắt buộc của RFC. Một OpenID Provider có thể công bố thông tin qua OIDC Discovery theo cơ chế của mình; cần áp chính sách discovery và trust phù hợp.

### 4.1. Metadata phải gắn với issuer được phê duyệt

- **Issuer URL** đến từ client registration hoặc cấu hình quản trị được tin cậy, không phải query parameter do người dùng nhập.
- Client fetch metadata qua **HTTPS với certificate và hostname validation**, xác minh `issuer` khớp issuer kỳ vọng.
- Device authorization endpoint và token endpoint lấy từ metadata **đã được tin cậy**, không phải URL tùy ý trong device response/QR code.
- Không tự gửi `client_secret`, `device_code` hay access token theo redirect sang host lạ.
- Khi multi-tenant/multi-AS, ràng buộc mỗi transaction với **issuer, client registration, requested scope/resource và endpoints của chính AS đó** để tránh mix-up.

Một endpoint HTTPS có cert hợp lệ của **attacker-owned host** không mặc nhiên là AS được quyền nhận client credential. TLS xác minh host đích, còn cấu hình issuer xác định **host nào được phép nhận**.

### 4.2. Không nhầm `verification_uri` với `device_authorization_endpoint`

`verification_uri` được AS trả về sau khi bắt đầu flow, để **người dùng mở trên browser**. TV không gửi device authorization request tới verification URI. Ngược lại, user không cần gõ URL của token endpoint hoặc nhập `device_code`; họ chỉ tương tác với trang chính thức và `user_code`.

Nếu thiết bị hiển thị QR code, QR phải mã hóa **`verification_uri` hoặc `verification_uri_complete` đã được xác nhận từ AS tin cậy**, không tự trỏ sang trang của bên thứ ba.

## 5. HTTP POST khởi tạo tại device authorization endpoint

Theo RFC 8628 mục Device Authorization Request, client gửi request **HTTP POST** với entity body kiểu `application/x-www-form-urlencoded`, encoding UTF-8. Các tham số cốt lõi:

| Tham số | Yêu cầu theo RFC 8628 | Ý nghĩa |
| --- | --- | --- |
| `client_id` | **REQUIRED** | Định danh OAuth client đã đăng ký |
| `scope` | **OPTIONAL** | Danh sách scopes client yêu cầu, được AS đánh giá theo policy |
| Các extension như `resource` | Nếu AS hỗ trợ profile tương ứng | Không tự có hiệu lực chỉ vì client gửi |

Ví dụ:

~~~http
POST /oauth2/device_authorization HTTP/1.1
Host: auth.example.test
Content-Type: application/x-www-form-urlencoded
Accept: application/json

client_id=living-room-tv&scope=openid%20media.read
~~~

Trong form encoding, dấu cách giữa scopes được encode phù hợp; không dùng JSON body nếu AS tuân RFC 8628 form request và không có profile JSON riêng.

### 5.1. Client authentication khi cần

RFC 8628 cho phép client có khả năng xác thực thực hiện client authentication theo cơ chế OAuth đã đăng ký. Với confidential client, ví dụ `client_secret_basic` có thể dùng `Authorization: Basic ...`, hoặc AS hỗ trợ `private_key_jwt`, mTLS/other registered method. Public client **không gửi một secret hardcode trong ứng dụng** và kỳ vọng nó là bí mật.

AS phải kiểm tra đúng client registration, grant types, scopes và audience/resource policy. Không được cấp `media.admin` chỉ vì request đưa `scope=media.admin` hoặc client gửi một `client_id` đã biết.

### 5.2. Request không phải consent và không cấp token

Ngay cả khi request device authorization hợp lệ, AS chỉ đang xác nhận **client có thể khởi tạo một authorization transaction**. User chưa được xác thực/chấp thuận ở bước này. AS không được trả access token/refresh token trong response khởi tạo và không được tự cấp tất cả scope khi chưa đánh giá grant.

### 5.3. Chống lạm dụng khởi tạo

Device authorization endpoint có thể bị bot gọi hàng loạt để tạo device/user codes. AS nên có:

- Rate limit theo client, nguồn mạng, rủi ro và tenant; có giới hạn chi phí tạo bản ghi.
- Quota số transaction pending cho mỗi client/device/user-context phù hợp.
- `expires_in` ngắn, dọn bản ghi hết hạn và chống lưu mã vô thời hạn.
- Giới hạn scopes/resource và client registrations được phép dùng device flow.
- Telemetry phát hiện đợt phát hành code bất thường, nhưng **không log raw `device_code`**.

Nếu client bị rate limit hoặc endpoint lỗi, TV cần phản hồi hợp lý và backoff; không tạo request mới mỗi 100 ms chỉ vì chưa có code.

## 6. Response của device authorization endpoint

Ví dụ HTTP response thành công:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store
Pragma: no-cache

{
  "device_code": "example-device-code-high-entropy",
  "user_code": "K7PD-3HFX",
  "verification_uri": "https://auth.example.test/activate",
  "verification_uri_complete": "https://auth.example.test/activate?user_code=K7PD-3HFX",
  "expires_in": 900,
  "interval": 5
}
~~~

Các mã và tên miền trên **chỉ để học**, không có giá trị xác thực. Trong production, `device_code` phải do CSPRNG tạo với entropy đủ mạnh và không đoán được; `user_code` có thể ngắn hơn để người dùng gõ nhưng cần bảo vệ bằng chống đoán, rate limiting và expiration.

| Trường | RFC 8628 | Ai dùng? | Ý nghĩa / lưu ý |
| --- | --- | --- | --- |
| `device_code` | **REQUIRED** | **Device client → token endpoint** | Credential bí mật, dùng để định danh transaction khi polling; không trình cho người dùng |
| `user_code` | **REQUIRED** | **User → verification URI** | Mã ngắn dễ nhập, ánh xạ tới transaction pending; không phải access token |
| `verification_uri` | **REQUIRED** | User mở trên browser | Trang AS để nhập/xác nhận code, dùng HTTPS và trusted origin |
| `verification_uri_complete` | **OPTIONAL** | QR/link/shortcut mở trên browser | URI đã gồm code hoặc thông tin tương đương; vẫn cần hiển thị/xác nhận mã rõ ràng |
| `expires_in` | **REQUIRED** | Device tính expiry, AS kiểm soát | Số giây device_code và user_code còn hiệu lực, không phải TTL access token |
| `interval` | **OPTIONAL** | Device polling token endpoint | Khoảng tối thiểu tính bằng giây giữa các lần polling; **mặc định 5 giây** nếu vắng |

### 6.1. `device_code` khác `user_code`

**`device_code`** là credential có giá trị tại token endpoint, cần entropy cao và giữ bí mật tương tự một handle nhạy cảm. **`user_code`** được cố ý hiển thị để user nhập; vì thường ngắn và dễ nhớ hơn, AS phải giới hạn số lần thử, tốc độ thử và thời hạn.

**Không thay thế vị trí của nhau:**

~~~text
TV lưu:       device_code (secret for polling)
TV hiển thị: verification_uri và user_code
User nhập:    user_code trên trang AS
TV gửi /token: device_code, không phải user_code
~~~

Một lỗi nghiêm trọng là hiển thị `device_code` dài trên màn hình hoặc đưa nó vào QR/link có thể chụp lại, rồi để token endpoint chấp nhận `user_code` như device credential.

### 6.2. `verification_uri_complete` là tiện ích, không tự chứng minh consent

AS có thể cung cấp `verification_uri_complete` để user quét QR và không cần tự nhập mã. Nhưng người dùng vẫn nên được xem **mã và thông tin thiết bị/client** để nhận diện có đúng phiên do mình khởi động không. Khi QR trỏ tới một URI có sẵn code, AS phải áp **chính sách chống phishing/session swapping và xác nhận rõ ràng**, không chỉ thấy user đang đăng nhập SSO thì âm thầm approve.

Không gửi `device_code` trong `verification_uri_complete`. Trường này phục vụ việc truyền **user code hoặc thông tin tương đương cho browser**, không phải credential bí mật của device poller.

### 6.3. Ý nghĩa thời gian

Giả sử AS trả `expires_in=900` và `interval=5` lúc 10:00:

~~~text
10:00:00  TV nhận response, tạo mốc expiry cục bộ dự phòng 15 phút
10:00:05  Poll đầu tiên (theo interval 5 giây)
10:00:10  Poll tiếp theo nếu chưa có kết quả
...       AS có thể trả authorization_pending hoặc slow_down
10:15:00  Không dùng device_code/user_code đã hết hạn
~~~

Đây là timeline minh họa, không bảo đảm AS sẽ cấp token trong 15 phút. `expires_in` của **device authorization response** khác `expires_in` trong **access token response**, và khác `exp` của JWT. Device client phải dựa vào cả thời hạn cục bộ **và** response của AS: nếu nhận `expired_token`, dừng ngay.

## 7. Trên thiết bị của user: verification_uri và quyết định cấp quyền

Device client chỉ nên hiển thị hướng dẫn rõ và giữ màn hình ở trạng thái chờ. **User không xác thực vào ứng dụng TV qua mật khẩu**; user mở **trang AS tin cậy** trên điện thoại/laptop, và AS thực hiện những bước authentication/consent theo chính sách.

### 7.1. Giao diện phía device

Một nội dung an toàn:

~~~text
Kết nối tài khoản trên TV

1. Dùng điện thoại hoặc laptop của bạn.
2. Mở: https://auth.example.test/activate
3. Nhập mã: K7PD-3HFX
4. Kiểm tra ứng dụng "Living Room TV" và quyền được yêu cầu.
5. Chỉ chọn Cho phép nếu bạn đang chủ động đăng nhập TV này.

Mã hết hạn sau khoảng 15 phút.
Đang chờ xác nhận...
~~~

Lời nhắc cần đủ rõ để user **không đưa mật khẩu cho TV**, không nhập mã vào một site giả, và không chia sẻ code với người lạ. Nếu có QR, vẫn hiển thị tên miền chính thức và mã để user đối chiếu.

### 7.2. Giao diện xác minh của AS

Khi người dùng mở verification URI:

1. AS xác minh URL/phương thức là trang hợp lệ của mình và chống CSRF/XSS, clickjacking theo yêu cầu.
2. AS yêu cầu **đăng nhập** nếu user chưa có SSO session hợp lệ; có thể yêu cầu MFA/step-up cho quyền nhạy cảm.
3. User nhập `user_code` (hoặc trang nhận code qua `verification_uri_complete`), AS tra **transaction chưa hết hạn**.
4. AS hiển thị **ứng dụng/client**, loại thiết bị và thông tin liên quan có thể xác minh, scopes/resource/cảnh báo phù hợp để user quyết định.
5. User chọn **Cho phép** hoặc **Từ chối**; không approve tự động chỉ vì user đã đăng nhập.
6. AS ghi quyết định vào transaction của `device_code` tương ứng, theo đúng client và grant policy.

Không có bước nào ở đây đòi AS chuyển access token đến browser dùng để xác minh. Browser chỉ tương tác với quyền xác thực/cho phép; **TV** nhận token sau đó qua **token endpoint** và `device_code` mà TV đang giữ.

### 7.3. Consent không vượt quyền của user

Giả sử device client xin `media.read media.admin`, nhưng client registration chỉ cho phép `media.read`. Dù Alice nhấn “Cho phép” trên trang xác minh, AS **không được cấp** `media.admin` trái policy. Tương tự, Alice chỉ được xem thư viện tenant A thì scope `media.read` không mở quyền sang tenant B. Quyết định cuối về object cụ thể vẫn thuộc **RS**.

AS phải xác định chính xác:

~~~text
requested_scope    = "media.read"
allowed_client     = living-room-tv
resource/audience  = media-api
authenticated_user = Alice (nếu user-delegated)
approved_scope     = policy-approved subset or an error
grant_state        = APPROVED / DENIED
~~~

`user_code` không phải giấy ủy quyền tự thân. **Đúng code chỉ chọn đúng transaction**; user authentication, client verification và consent/policy mới tạo ra grant.

## 8. Token endpoint: poll bằng device_code, không dùng user_code

Sau khi khởi tạo thành công, device gọi **token endpoint** được tin cậy. Device code grant có định danh chuẩn:

~~~text
urn:ietf:params:oauth:grant-type:device_code
~~~

### 8.1. Request token của public device client

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.test
Content-Type: application/x-www-form-urlencoded
Accept: application/json

grant_type=urn%3Aietf%3Aparams%3Aoauth%3Agrant-type%3Adevice_code&device_code=<opaque-device-code>&client_id=living-room-tv
~~~

`client_id` là định danh public client; theo RFC 8628, khi client không được xác thực qua phương thức khác, token request cần xác định client. Nếu AS/client sử dụng client authentication, phải làm đúng phương thức đã đăng ký.

Đối với confidential client, xác thực client tiếp tục là yêu cầu độc lập — có `device_code` không đồng nghĩa client đã được xác thực bằng secret/private key. AS phải bind `device_code` vào **đúng client đã khởi tạo** và policy grant.

### 8.2. Các phản hồi trong giai đoạn pending

User chưa xác minh, AS có thể trả:

~~~http
HTTP/1.1 400 Bad Request
Content-Type: application/json
Cache-Control: no-store
Pragma: no-cache

{"error":"authorization_pending"}
~~~

Nếu client poll quá nhanh:

~~~json
{"error":"slow_down"}
~~~

Các lỗi có ý nghĩa theo RFC 8628:

| `error` tại token endpoint | Ý nghĩa | Device phải làm gì |
| --- | --- | --- |
| `authorization_pending` | User chưa hoàn tất xác thực/chấp thuận | Tiếp tục polling **đúng khoảng thời gian** |
| `slow_down` | Polling quá nhanh, AS yêu cầu chậm lại | **Tăng interval ít nhất 5 giây** cho các lần sau |
| `access_denied` | User đã từ chối yêu cầu | **Dừng polling** và dọn transaction |
| `expired_token` | Device code hết hạn | **Dừng polling**, không dùng lại mã cũ |
| `invalid_client` | Client authentication không hợp lệ | Dừng/xử lý cấu hình; không bỏ client auth |
| `invalid_grant` hoặc `invalid_request` | Binding, mã hoặc request không hợp lệ theo profile | Không coi là pending; báo lỗi an toàn |
| `temporarily_unavailable`, mạng timeout, `5xx` | AS không thể xử lý/không có kết quả rõ | Backoff, giới hạn retry và expiry; không flood endpoint |

Không phải mọi lỗi OAuth của RFC 6749 đều nhất thiết có trong mọi triển khai device flow; **xử lý chính xác lỗi dựa trên token endpoint contract**, nhưng bốn lỗi chuẩn `authorization_pending`, `slow_down`, `access_denied`, `expired_token` có semantics quan trọng riêng.

### 8.3. Khoảng polling đúng RFC 8628

Nếu AS trả `interval` trong response ban đầu, client phải chờ ít nhất khoảng đó giữa các token requests. **Nếu `interval` không có, mặc định 5 giây.** Khi nhận `slow_down`, tăng interval tối thiểu thêm **5 giây** cho lần tiếp theo và những lần sau trong transaction đó.

Ví dụ:

~~~text
T0:   Device authorization response: interval = 5s.
T+5:  POST /token → authorization_pending.
T+10: POST /token → slow_down.
      Interval mới >= 10s.
T+20: POST /token → authorization_pending.
T+30: POST /token → success, nếu user đã approve và grant hợp lệ.
      Dừng polling.
~~~

Lịch trên là ví dụ không có jitter hoặc sự cố; nếu AS trả `slow_down` nhiều lần, phải tăng dần theo yêu cầu. Nếu timeout mạng, RFC 8628 khuyến nghị giảm tốc độ polling, ví dụ exponential backoff; không tăng tốc để “bắt kịp”.

**Không gửi nhiều token requests song song cho cùng `device_code`.** Việc client chạy nhiều thread/Pod không làm tăng tốc user approval, chỉ làm phức tạp race, giới hạn tốc độ và kết quả token issuance.

### 8.4. Khi user approve

Token endpoint có thể trả:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store
Pragma: no-cache

{
  "access_token": "<bearer-access-token-for-media-api>",
  "token_type": "Bearer",
  "expires_in": 300,
  "scope": "media.read",
  "refresh_token": "<optional-refresh-token>"
}
~~~

Đây là token response minh họa. `refresh_token` chỉ có khi AS **thực sự cấp** theo grant/client/user policy, không phải trường bắt buộc. Nếu OIDC được hỗ trợ và flow được cấp `openid`, response có thể có `id_token` theo profile. **ID token không phải access token** để gửi tới `media-api`.

### 8.5. Token sau khi cấp phải đúng resource

TV gọi API:

~~~http
GET /v1/library HTTP/1.1
Host: media.example.test
Authorization: Bearer <access-token>
~~~

RS cần xác minh:

1. Token đúng **access-token type/profile**, không phải `device_code`, `user_code`, ID token, refresh token.
2. JWT được xác minh chữ ký và trusted issuer/JWKS, hoặc opaque token có introspection `active` đáng tin.
3. `aud` chứa expected audience của **`media-api`**, không phải `client_id=living-room-tv` nếu token contract quy định audience API.
4. `exp`/`nbf`, scopes và quyền user/service/tenant/object phù hợp.
5. Nếu token sender-constrained, xác minh DPoP/mTLS proof/binding theo profile.

**Device flow không thay thế API authorization.** Một TV đã được Alice approve `media.read` vẫn không được truy cập nội dung của user khác hoặc chuyển token của media sang payments API.

## 9. AS state machine: transaction phải có vòng đời xác định

Device authorization endpoint khởi tạo trạng thái mà **verification URI và token endpoint cùng tham chiếu**. Một mô hình logic:

~~~mermaid
stateDiagram-v2
    [*] --> PENDING: Device authorization request hợp lệ
    PENDING --> PENDING: Poll interval hợp lệ / authorization_pending
    PENDING --> APPROVED: User authenticated + consent/policy approved
    PENDING --> DENIED: User denies
    PENDING --> EXPIRED: expires_in passed
    APPROVED --> EXPIRED: Deadline passed before redemption
    APPROVED --> CONSUMED: Token endpoint redeems atomically
    DENIED --> [*]
    EXPIRED --> [*]
    CONSUMED --> [*]
~~~

Tên trạng thái chỉ là ví dụ triển khai; RFC 8628 không yêu cầu database phải dùng enum như vậy. Mọi nhánh phải tránh **token issuance sau DENIED/EXPIRED** và tránh việc cùng `device_code` cấp nhiều bộ token do race. Việc AS cho phép one-time token redemption và xử lý response bị mất cần được định nghĩa rõ.

### 9.1. Các thông tin cần liên kết

Một transaction model có thể chứa:

~~~json
{
  "id": "<internal-transaction-reference>",
  "device_code_hash": "<hash-or-secure-lookup>",
  "user_code_lookup": "<protected-index>",
  "client_id": "living-room-tv",
  "requested_scope": ["media.read"],
  "resource": "media-api",
  "status": "PENDING",
  "created_at": "2026-11-23T09:00:00Z",
  "expires_at": "2026-11-23T09:15:00Z",
  "interval_seconds": 5,
  "last_poll_at": null,
  "approved_subject": null,
  "approved_scope": null
}
~~~

Đây là **minh họa** về dữ liệu nội bộ, không phải JSON response chuẩn. Những giá trị có tính credential nên được bảo vệ khi lưu: hạn chế quyền đọc, cân nhắc hash/HMAC cho lookup, không log raw device code. **Hash của user code không thay thế rate limiting** vì user code có entropy thấp hơn để tiện nhập.

AS cần giữ đủ dữ liệu để ràng buộc:

| Trường/binding | Lỗi nếu thiếu |
| --- | --- |
| Client ID và cách xác thực client | Device code của client A bị client B sử dụng |
| User code ↔ đúng transaction | User approve nhầm device hoặc approval gắn code không đúng |
| Requested/granted scopes và audience | Sau approval AS cấp token rộng hơn client/user đã được phép |
| Expiry và trạng thái | Mã đã hết hạn, bị từ chối hoặc consumed vẫn dùng được |
| Poll interval/rate state | Bị flood token endpoint hoặc brute force |
| User/tenant/consent context | Client được cấp quyền của người khác/tenant khác |
| Atomic consume/issuance | Hai polls đồng thời cùng mint token |

### 9.2. Đánh dấu consumed nguyên tử

AS có thể dùng transaction DB hoặc compare-and-swap:

~~~text
BEGIN TRANSACTION
  row = loadByDeviceCodeForUpdate(deviceCode)
  require row.clientId matches authenticated/requesting client
  require row.status == APPROVED and now < row.expiresAt
  require approved grant and subject still eligible
  update row.status from APPROVED to CONSUMED
  persist issued-token/grant record consistently
COMMIT
return token response if successful
~~~

Không giữ lock mà không có timeout/chống deadlock; không đánh dấu consumed sau khi đã trả token cho client. AS phải xử lý crash/unknown outcome mà vẫn giữ **single-winner** và không để một mã được dùng vô hạn.

**Phân biệt:** Device client **poll nhiều lần khi đang PENDING** là hành vi giao thức bình thường. Ngược lại, nhiều request đồng thời khi transaction đã APPROVED/CONSUMED cần được xử lý bằng state/atomicity để tránh duplicate issuance.

### 9.3. Nhiều node và cache

Nếu AS triển khai nhiều instance, tất cả node phục vụ:

- `/device_authorization` (tạo record).
- `/activate` (user xác thực và approve/deny).
- `/token` (poll trạng thái và cấp token).

...phải nhìn thấy **trạng thái nhất quán**, kể cả expiry và consumed flag. Chỉ lưu transaction trong RAM của node tạo mã có thể làm user verification trên node khác không tìm thấy code. Nếu dùng cache phân tán, cần atomic operations hoặc coordination đủ mạnh cho kết quả approved/consumed, không đơn giản “read cache rồi write lại” dưới race.

### 9.4. TTL không được kéo dài tùy ý bằng polling

Đối với transaction đã tạo tại `t0`:

~~~text
expiresAt = t0 + expires_in
~~~

Mỗi lần token endpoint trả `authorization_pending` **không** tự gia hạn `expiresAt`. Nếu `device_code` hết hạn, client bắt đầu một device authorization request **mới** với user code mới. User không nên được yêu cầu nhập một mã mà AS đã hết hạn.

## 10. Các mối đe dọa gắn với device authorization endpoint

### 10.1. Remote phishing: người khác mời user approve device của attacker

Một attacker có thể **tự khởi tạo device flow** cho client/thiết bị do attacker kiểm soát, nhận `user_code`, rồi nhắn Alice: “Đây là mã bảo mật của công ty, vào trang AS và nhập ngay”. Nếu Alice nhập mã và bấm approve mà không biết, **attacker-controlled device** có thể lấy AT qua `device_code` mà attacker vẫn giữ.

~~~mermaid
sequenceDiagram
    autonumber
    participant X as Thiết bị của attacker
    participant AS as Authorization Server
    actor U as Alice
    X->>AS: Device authorization cho client do attacker điều khiển
    AS-->>X: device_code-X, user_code-X
    X-->>U: Lừa nhập user_code-X
    U->>AS: Truy cập verification_uri thật và nhập code-X
    AS->>U: Hiển thị rõ client/device/scopes và cảnh báo
    alt Alice nhận ra phiên lạ
        U-->>AS: Deny
        AS-->>X: access_denied ở lần poll kế tiếp
    else Alice approve nhầm
        U-->>AS: Approve
        AS-->>X: AT theo grant đã bị lừa cấp
    end
~~~

Đây không phải phishing chỉ xảy ra trên **website giả**. User có thể được dẫn tới **đúng trang AS** nhưng nhập **mã của thiết bị attacker**. Vì vậy bảo vệ bắt buộc ở **trang xác nhận quyền** là giúp user nhận biết client/thiết bị, hành động và không approve một phiên mình không chủ động bắt đầu.

### 10.2. Biện pháp chống phishing

1. Verification page hiển thị rõ **tên client, loại thiết bị** và scope/resource được yêu cầu; có thể hiển thị thông tin nhận diện đã đăng ký đáng tin.
2. User phải **chủ động chọn Approve**; không auto-approve vì đã có phiên SSO.
3. Màn hình device hiển thị mã để user **so khớp** với trang xác nhận.
4. User code có thời hạn ngắn; verification endpoint giới hạn số lần nhập mã sai, tốc độ, brute force.
5. Với scope nhạy cảm, AS có thể yêu cầu MFA, step-up, quản trị viên hoặc chính sách bổ sung.
6. Phát hiện số lượng device transactions bất thường, nhiều user nhập code của một client, hoạt động gian lận.

Hiển thị QR code là cải thiện UX, **không bảo đảm không phishing**. Nếu link đầy đủ đi tới trang AS và pre-fill code, AS vẫn nên yêu cầu xác nhận rõ device/grant. Không tin rằng “người dùng đã quét QR” tương đương consent.

### 10.3. `device_code` bị rò

Nếu attacker có `device_code` trong khi Alice đã approve transaction, họ có thể thử poll token endpoint thay TV. Với public client, `client_id` không phải bí mật. Vì thế:

- `device_code` phải đủ entropy, được lưu an toàn và **không hiển thị cho user**, không xuất ra QR/link.
- Client/AS phải bind code với đúng client; confidential client cần client authentication hợp lệ.
- AS phải áp expiry, polling rate limit, atomic consumed state và giám sát reuse bất thường.
- Khi cần assurance mạnh hơn, cân nhắc sender constraint, proof-of-possession, device registration/attestation riêng theo profile.

Một device code bị lộ có thể gây **token theft sau user approval**; không thể khắc phục chỉ bằng việc user code khó đoán nếu attacker đã lấy được device code.

### 10.4. User code guessing

Vì user code dễ nhập, không thể có entropy tương đương device code dài trong mọi thiết kế. Attacker có thể brute-force user code để gắn approval vào transaction khác hoặc gây DoS nếu verification endpoint không kiểm soát.

AS cần kết hợp:

- Bộ mã với entropy phù hợp độ dài mã người dùng và threat model, tránh phân phối quá thiên lệch.
- Thời hạn ngắn, giới hạn số transaction pending.
- Rate limiting theo IP/user/client và các chỉ dấu rủi ro; khóa/throttle khi thử sai nhiều.
- Transaction binding, consent rõ ràng, không lộ thông tin user/client không cần thiết khi nhập code sai.
- Không cho một `user_code` đồng thời ánh xạ đến hai giao dịch active.

Đừng tạo mã từ ngày giờ/ID tăng dần hoặc dùng 4 chữ số cố định cho hệ thống có số lượng user lớn mà không đánh giá entropy và công suất bảo vệ chống thử mã.

### 10.5. Trust boundary và SSRF/redirect

TV không nên nhận `device_authorization_endpoint` hoặc `token_endpoint` từ một URL do user/attacker cung cấp. Một HTTPS endpoint có cert hợp lệ vẫn có thể thuộc attacker; nếu client gửi client credentials hoặc device code tới đó, credential sẽ bị lộ.

Khi gateway, proxy hoặc service mesh tham gia:

- Mọi hop chứa `device_code`, bearer AT, RT, client secret phải có TLS và trust boundary phù hợp.
- Strip/redact `Authorization` và form bodies trong gateway/HTTP logs.
- Không tự follow HTTP redirect từ token endpoint sang host khác kèm credential.
- Không tin `X-Client-Id`/`X-User` do client gửi để thay xác thực/grant.

## 11. Java 17: client khởi tạo Device Authorization Grant

Ví dụ này sử dụng **Java `HttpClient`** và **Jackson `ObjectMapper`** để gửi form request rồi đọc JSON response. Trong ứng dụng thực, ưu tiên SDK OAuth được bảo trì và hỗ trợ Device Grant; ví dụ nhằm minh họa rõ **đúng endpoint, content type, response fields, URL trust và deadline**.

### 11.1. DTO không tự in credential ra log

~~~java
import java.net.URI;
import java.time.Duration;
import java.util.Optional;

public record DeviceAuthorization(
        String deviceCode,
        String userCode,
        URI verificationUri,
        Optional<URI> verificationUriComplete,
        Duration expiresIn,
        Duration pollingInterval) {

    @Override
    public String toString() {
        // Tránh record.toString() mặc định làm lộ deviceCode.
        return "DeviceAuthorization[userCode=<redacted>, deviceCode=<redacted>]";
    }
}
~~~

`deviceCode` vẫn tồn tại trong memory của JVM; override `toString` chỉ giảm một đường logging, không thay việc bảo vệ process memory, telemetry, dumps hay quyền truy cập. `userCode` chủ động hiển thị cho user qua UI, nhưng không cần xuất trong logs.

### 11.2. POST request và validate response

~~~java
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.net.URI;
import java.net.URLEncoder;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.Optional;

public final class DeviceAuthorizationClient {
    private final ObjectMapper mapper = new ObjectMapper();
    private final HttpClient http = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(5))
            .followRedirects(HttpClient.Redirect.NEVER)
            .build();

    // URL lấy từ issuer metadata tin cậy, không phải từ user input.
    private final URI endpoint = URI.create(
            "https://auth.example.test/oauth2/device_authorization");

    public DeviceAuthorization start(String clientId, String scope)
            throws Exception {

        String form = "client_id=" + encode(clientId)
                + "&scope=" + encode(scope);

        HttpRequest request = HttpRequest.newBuilder(endpoint)
                .header("Content-Type",
                        "application/x-www-form-urlencoded")
                .header("Accept", "application/json")
                .timeout(Duration.ofSeconds(10))
                .POST(HttpRequest.BodyPublishers.ofString(form))
                .build();

        HttpResponse<String> response = http.send(
                request, HttpResponse.BodyHandlers.ofString());

        if (response.statusCode() != 200) {
            // Không đưa raw body vào log: AS/proxy có thể echo credential.
            throw new IllegalStateException(
                    "Device authorization failed, HTTP "
                    + response.statusCode());
        }

        JsonNode json = mapper.readTree(response.body());
        String deviceCode = requiredText(json, "device_code");
        String userCode = requiredText(json, "user_code");
        URI verificationUri =
                requireHttps(URI.create(requiredText(
                        json, "verification_uri")));

        Optional<URI> complete = json.hasNonNull(
                "verification_uri_complete")
                ? Optional.of(requireHttps(
                        URI.create(requiredText(
                                json, "verification_uri_complete"))))
                : Optional.empty();

        long seconds = requiredPositiveLong(json, "expires_in");
        long interval = json.has("interval")
                ? requiredPositiveLong(json, "interval") : 5L;

        // Policy bổ sung: tránh transaction sống quá lâu,
        // field quá lớn hoặc polling quá thường xuyên.
        if (seconds > 3600 || interval > 300
                || deviceCode.length() > 4096
                || userCode.length() > 128) {
            throw new IllegalArgumentException(
                    "Device authorization response exceeds local policy");
        }

        return new DeviceAuthorization(
                deviceCode, userCode, verificationUri, complete,
                Duration.ofSeconds(seconds),
                Duration.ofSeconds(interval));
    }

    private static String encode(String text) {
        return URLEncoder.encode(text, StandardCharsets.UTF_8);
    }

    private static String requiredText(JsonNode json, String key) {
        JsonNode node = json.get(key);
        if (node == null || !node.isTextual()
                || node.textValue().isBlank()) {
            throw new IllegalArgumentException("Missing " + key);
        }
        return node.textValue();
    }

    private static long requiredPositiveLong(JsonNode json, String key) {
        JsonNode node = json.get(key);
        if (node == null || !node.isIntegralNumber()
                || !node.canConvertToLong()
                || node.longValue() <= 0) {
            throw new IllegalArgumentException(
                    "Invalid positive integer: " + key);
        }
        return node.longValue();
    }

    private static URI requireHttps(URI uri) {
        if (!"https".equalsIgnoreCase(uri.getScheme())
                || uri.getHost() == null
                || uri.getUserInfo() != null
                || uri.getFragment() != null) {
            throw new IllegalArgumentException(
                    "Unsupported verification URI");
        }
        return uri;
    }
}
~~~

**Những điểm cần kiểm tra trước production:**

- Endpoint đã được lấy từ **metadata của issuer được phê duyệt**, và client vẫn phải verify certificate/hostname khi kết nối.
- `HttpClient.Redirect.NEVER` chặn tự chuyển credentials/transaction sang URL khác. Nếu AS yêu cầu thay endpoint, cần cập nhật metadata/cấu hình tin cậy.
- Response `200` không có nghĩa user đã approve; code này chỉ mô tả **khởi tạo transaction**.
- `requiredPositiveLong` và giới hạn kích thước là **policy bổ sung ở client**, không phải ngưỡng RFC bắt buộc. Thời hạn 3600 giây và interval 300 giây chỉ là ví dụ phòng lỗi; ứng dụng phải điều chỉnh theo AS hợp đồng.
- Client cần giới hạn **độ lớn response body** tại HTTP layer/proxy để chống DoS từ nội dung JSON lớn; ví dụ tối giản chưa thêm cơ chế này.
- `scope` có thể bỏ nếu không yêu cầu; đoạn code luôn gửi field để đơn giản hóa. AS quyết định granted scopes, không tin scope do client tự khai.
- Với confidential client, thêm đúng **client authentication method**; code public client trên **không** thể thay confidential client authentication.
- Đừng dùng `verification_uri_complete` để đọc response từ thiết bị khác; đây là URL dành cho **user browser**, không phải callback token.

### 11.3. Hiển thị URL và mã

~~~java
DeviceAuthorization challenge =
        new DeviceAuthorizationClient().start(
                "living-room-tv", "openid media.read");

System.out.println("Đăng nhập TV bằng điện thoại:");
System.out.println("Mở: " + challenge.verificationUri());
System.out.println("Nhập mã: " + challenge.userCode());
System.out.println("Thời hạn: "
        + challenge.expiresIn().toMinutes() + " phút (xấp xỉ)");
// Không println(challenge.deviceCode()).
// Không mở token polling song song trên nhiều worker.
~~~

CLI/TV nên dùng giao diện có khả năng hiển thị QR, mã rõ ràng và thông báo đúng trạng thái. `device_code` là một bí mật không dành cho người dùng, không phải dòng debug hiển thị trên màn hình.

## 12. Java: polling đúng interval và xử lý lỗi theo RFC 8628

Một polling loop chạy trên **worker thread** (không chặn UI thread) cần tuân thủ:

1. Chỉ một polling operation cho **một device authorization transaction**.
2. Chờ ít nhất `interval` giây trước lần poll tiếp theo.
3. Nếu nhận `authorization_pending`, tiếp tục ở tốc độ hiện tại.
4. Nếu nhận `slow_down`, cộng thêm **ít nhất 5 giây** vào interval.
5. Nếu mất mạng/timeout, tăng backoff có giới hạn, không tạo request mới liên tục.
6. Nếu hết hạn local, `expired_token`, `access_denied` hoặc success, **dừng**.

### 12.1. Pseudocode flow

~~~text
challenge = POST trusted device_authorization_endpoint
deadline = monotonicNow() + challenge.expires_in
interval = challenge.interval or 5 seconds

while monotonicNow() < deadline:
    sleepAtLeast(interval)
    if local transaction canceled or deadline reached:
        stop

    response = POST trusted token_endpoint(
        grant_type = device_code,
        device_code = challenge.device_code,
        client_id = registered_client_id)

    if response is successful token issuance:
        store AT/RT safely; clear challenge; stop
    else if response.error == authorization_pending:
        continue
    else if response.error == slow_down:
        interval = interval + atLeast(5 seconds)
        continue
    else if response.error in (access_denied, expired_token):
        clear challenge; stop
    else if network timeout / temporarily unavailable:
        interval = boundedBackoff(interval)
        continue only while code remains valid and policy allows
    else:
        clear or quarantine transaction; do not retry indefinitely
~~~

Trong ứng dụng có event loop hoặc Java reactive stack, nên dùng scheduler/asynchronous I/O thay `Thread.sleep`. **Không chạy polling trên UI main thread** vì sẽ làm treo giao diện.

### 12.2. Java worker poll một lần

~~~java
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.net.URI;
import java.net.URLEncoder;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;

public final class DeviceTokenPoller {
    private final ObjectMapper mapper = new ObjectMapper();
    private final HttpClient http = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(5))
            .followRedirects(HttpClient.Redirect.NEVER)
            .build();
    private final URI tokenEndpoint = URI.create(
            "https://auth.example.test/oauth2/token");

    public PollResult pollOnce(String deviceCode, String clientId)
            throws Exception {
        String form = "grant_type=" + encode(
                "urn:ietf:params:oauth:grant-type:device_code")
                + "&device_code=" + encode(deviceCode)
                + "&client_id=" + encode(clientId);

        HttpRequest request = HttpRequest.newBuilder(tokenEndpoint)
                .header("Content-Type",
                        "application/x-www-form-urlencoded")
                .header("Accept", "application/json")
                .timeout(Duration.ofSeconds(10))
                .POST(HttpRequest.BodyPublishers.ofString(form))
                .build();

        HttpResponse<String> response = http.send(
                request, HttpResponse.BodyHandlers.ofString());
        JsonNode body = mapper.readTree(response.body());

        if (response.statusCode() == 200
                && body.hasNonNull("access_token")) {
            // Không log response body/token.
            return new PollResult("SUCCESS", body);
        }

        if (body.hasNonNull("error")) {
            return new PollResult(
                    body.get("error").asText(), null);
        }
        throw new IllegalStateException(
                "Unrecognized token response, HTTP "
                + response.statusCode());
    }

    private static String encode(String value) {
        return URLEncoder.encode(value, StandardCharsets.UTF_8);
    }

    public record PollResult(String status, JsonNode tokenBody) {
        @Override
        public String toString() {
            // Không in tokenBody nếu result là SUCCESS.
            return "PollResult[" + status + "]";
        }
    }
}
~~~

**Giới hạn có chủ đích:** Phương thức `pollOnce` chỉ thực hiện **một lần** và trả trạng thái; nó **không tự điều khiển interval**. Vòng scheduler bên ngoài phải gọi theo thời gian đã được AS quy định. Code minh họa chưa giới hạn kích thước JSON body, chưa hỗ trợ registered confidential-client authentication và chưa chuẩn hóa mọi OAuth error/status; những chi tiết này cần bổ sung khi triển khai production. **Đừng** chuyển toàn bộ `tokenBody` sang logs hoặc HTTP response gửi tới browser.

### 12.3. Scheduler dùng đồng hồ monotonic

Hạn cuối local nên được đo từ khi client nhận device authorization response bằng **monotonic clock** (chẳng hạn `System.nanoTime()`) để tránh NTP clock adjustment làm polling kéo dài vô ý.

~~~java
Duration interval = challenge.pollingInterval();
long deadline = System.nanoTime()
        + challenge.expiresIn().toNanos();

while (System.nanoTime() < deadline) {
    // Chạy ở worker thread; production có thể dùng Scheduler.
    Thread.sleep(interval.toMillis());

    if (Thread.currentThread().isInterrupted()
            || System.nanoTime() >= deadline) {
        break;
    }

    var result = poller.pollOnce(
            challenge.deviceCode(), "living-room-tv");

    if ("SUCCESS".equals(result.status())) {
        // Validate token response, lưu token an toàn và thoát.
        break;
    }
    if ("authorization_pending".equals(result.status())) {
        continue;
    }
    if ("slow_down".equals(result.status())) {
        interval = interval.plusSeconds(5);
        continue;
    }
    // access_denied/expired_token và các lỗi khác:
    // dừng hoặc xử lý theo bảng lỗi; không poll vô hạn.
    break;
}
~~~

Đoạn scheduler là **minh họa có điều kiện**, không phải service production hoàn chỉnh. Cần kiểm tra `Duration` nằm trong ngưỡng hợp lý để tránh overflow, xử lý `InterruptedException` đúng (trả interrupt flag), cancellation, `Retry-After`/backoff khi lỗi 429/5xx, jitter phù hợp và client credentials nếu dùng. AS kiểm soát thời hạn thực tế; deadline local chỉ giúp dừng sớm, không cấp thêm quyền.

### 12.4. Tại sao không polling bằng cron toàn hệ thống?

Nếu 10.000 TV nhận `interval=5` và tất cả poll vào đúng giây chia hết cho 5, token endpoint có thể bị **thundering herd**. Có thể thêm jitter dương khi lên lịch poll và áp rate limiting/connection pooling, miễn là **không poll sớm hơn interval**. Không áp một cron toàn hệ thống tự gửi device code của mọi thiết bị trong một batch log được; mỗi transaction phải có isolation và secret handling riêng.

## 13. Spring Authorization Server: hỗ trợ endpoint và client registration

Với Java/Spring, nên sử dụng **Spring Authorization Server** hoặc AS/IAM hỗ trợ RFC 8628 thay vì tự dựng endpoint cấp mã bằng controller thiếu security checks. Các phiên bản Spring Authorization Server hỗ trợ Device Authorization Grant có thể cấu hình **device authorization endpoint**, **device verification endpoint**, **token endpoint**, registered clients và các authentication providers liên quan.

### 13.1. Ví dụ RegisteredClient public device

~~~java
RegisteredClient tvClient = RegisteredClient.withId(
                UUID.randomUUID().toString())
        .clientId("living-room-tv")
        .clientAuthenticationMethod(ClientAuthenticationMethod.NONE)
        .authorizationGrantType(AuthorizationGrantType.DEVICE_CODE)
        .scope("media.read")
        .clientSettings(ClientSettings.builder()
                .requireAuthorizationConsent(true)
                .build())
        .build();
~~~

Ví dụ giả định imports, `RegisteredClientRepository` và các bean của AS đã được cấu hình. **Kiểm tra phiên bản Spring Authorization Server**: tên API, endpoint mặc định, các bước verification và flow UI có thể thay đổi theo release. `ClientAuthenticationMethod.NONE` phù hợp public client không có secret; **không** áp cho confidential client nếu AS đã đăng ký client authentication riêng.

### 13.2. Những thành phần AS cần cấu hình

1. **Device authorization endpoint:** kiểm tra `client_id`, đăng ký `device_code` grant, scope/resource/client policy, sinh đủ mã và response metadata.
2. **Device verification endpoint:** màn hình nhập mã, user login/MFA/consent và anti-phishing UX, xác minh CSRF/session và client/device details.
3. **Token endpoint:** nhận device_code grant, xử lý pending/slow_down/denied/expired/success, xác thực client phù hợp và tiêu thụ code nguyên tử.
4. **Grant/authorization storage:** đồng nhất user code ↔ device code ↔ client ↔ subject ↔ scopes ↔ expiry ↔ consumed state trên mọi node.
5. **Token generation:** ký JWT hoặc phát opaque AT theo AS policy, audience hẹp, TTL, refresh rotation/revocation khi cấp RT.
6. **SecurityFilterChain:** bảo vệ verification browser sessions, login CSRF, rate limits và không để gateway/client tự spoof principal.

Không nghĩ rằng thêm `authorizationGrantType(DEVICE_CODE)` tự động giải quyết **phishing, approval UX, rate limit, key management hoặc object-level authorization**. Hãy xác nhận quy tắc endpoint bằng integration tests thực tế.

### 13.3. Tách user verification và token issuance

Giả sử controller ở trang verification nhận POST:

~~~text
POST /activate
  user_code = "K7PD-3HFX"
  decision  = "approve"
~~~

Nó không nên trả AT/RT trong HTML body hoặc redirect URL. Thay vào đó AS:

~~~text
require browser user authenticated with trusted session
require valid CSRF/session + verification transaction
lookup user_code; enforce rate limit and expiry
show/verify client and requested scope/resource
if user explicitly approves and AS policy allows:
    atomically set transaction APPROVED
    bind approved user, scopes and audience
else:
    mark DENIED (or allow retry under defined policy)

show "You can return to your device."
~~~

Đoạn trên là **pseudo-code logic**, không phải Spring MVC endpoint hoàn chỉnh. Nếu verification page chỉ dùng GET và tự approve mà không có hành động rõ ràng, một attacker có thể lừa user mở link và kích hoạt grant qua CSRF hoặc prefetch; cần bảo vệ theo kiến trúc AS và risk policy.

### 13.4. API không được nhận device_code thay access token

Spring Resource Server cấu hình JWT:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://auth.example.test
~~~

AS công bố issuer/JWKS đáng tin, còn `media-api` phải cấu hình expected audience và scope:

~~~java
@Bean
SecurityFilterChain mediaApiChain(HttpSecurity http) throws Exception {
    http.authorizeHttpRequests(auth -> auth
            .requestMatchers(HttpMethod.GET, "/v1/library/**")
                .hasAuthority("SCOPE_media.read")
            .anyRequest().denyAll());
    http.oauth2ResourceServer(oauth ->
            oauth.jwt(Customizer.withDefaults()));
    return http.build();
}
~~~

Ví dụ chưa thêm **audience validator** vào `JwtDecoder`; production phải bổ sung `aud=media-api` (và issuer/signature/time/token profile) theo hợp đồng AS. Route scope không tự xác minh user có quyền với từng video/order hoặc tenant. **JWT access token** có thể được RS kiểm tra offline, **opaque access token** qua trusted introspection; Device Grant không quyết định token format.

## 14. Lỗi vận hành và kết quả không chắc chắn

### 14.1. Device authorization request timeout

Client gửi `POST /device_authorization`, AS đã tạo transaction nhưng response bị mất. Client chưa biết `device_code`/`user_code` nên không thể trình đúng mã cho người dùng. Nó có thể yêu cầu **một transaction mới** với backoff theo policy, không được giả sử transaction cũ đã biến mất trong database; AS nên dọn pending records hết hạn.

Không retry liên tục hàng chục request/giây, vì mỗi request có thể tạo một user code mới và làm cạn quota.

### 14.2. Poll thành công nhưng response bị mất

TV gửi `POST /token` cho `device_code` đã APPROVED. AS tiêu thụ code và cấp AT, nhưng HTTP response không đến TV. Client retry cùng mã có thể nhận `expired_token` hoặc `invalid_grant` theo AS semantics, vì code đã consumed.

**Không yêu cầu AS bỏ atomic single-use** chỉ để client có thể retry mù quáng. Cần design recovery theo AS contract: có thể yêu cầu user bắt đầu flow mới nếu không thể khôi phục kết quả một cách an toàn.

### 14.3. AS outage trong lúc polling

User có thể đang hoàn tất login khi token endpoint tạm downtime. Client phải tuân thủ expiry và backoff, không mở nhiều concurrent pollers cho cùng code. Nếu hết hạn trước khi AS phục hồi, dừng và tạo giao dịch mới khi user chủ động retry.

### 14.4. User đóng verification page hoặc deny

Đóng trang trước khi approve có thể để transaction ở trạng thái **PENDING** cho đến khi hết hạn; user chọn Deny phải khiến token endpoint trả `access_denied`. Client nên hiển thị hướng dẫn khởi động lại rõ ràng; không tự chuyển sang password grant hoặc cấp app-only token để “đỡ bị từ chối”.

### 14.5. Kiểm soát đồng hồ và thời hạn

AS là nguồn thẩm quyền cho `expires_in` và trạng thái expired. Đồng hồ client có thể lệch; dùng monotonic deadline ở client, giới hạn timeouts và dừng khi AS trả `expired_token`. TTL của access token sau issuance **khác** TTL device code. Nếu AS cấp refresh token, refresh token có hạn/rotation và revocation policy riêng.

### 14.6. Phân biệt lỗi device endpoint và token endpoint

| Ở đâu | Ví dụ lỗi | Điều cần sửa |
| --- | --- | --- |
| Device authorization endpoint | `invalid_client` | Client authentication/registration không hợp lệ |
| Device authorization endpoint | `unauthorized_client` | Client không được dùng Device Grant theo AS policy |
| Device authorization endpoint | `invalid_scope` | Scope ngoài allowlist hoặc không hợp lệ |
| Device authorization endpoint | HTTP 429/5xx | Rate limit/AS outage; backoff, không flood |
| Token endpoint | `authorization_pending` | Chờ user; poll theo interval |
| Token endpoint | `slow_down` | Tăng interval ít nhất 5s |
| Token endpoint | `access_denied` | Dừng, user không approve |
| Token endpoint | `expired_token` | Dừng, khởi tạo transaction mới khi cần |
| Resource server | `invalid_token` | AT sai issuer/audience/expiry/chữ ký/introspection |
| Resource server | `insufficient_scope` | AT không được cấp đủ scope; AS policy/consent |

Không gọi `/device_authorization` lần nữa chỉ vì token endpoint trả `authorization_pending`. Hai endpoint có vai trò khác nhau; **vòng polling chỉ gửi tới token endpoint** bằng `device_code` đã nhận.

## 15. Bảo vệ access token, refresh token và quyền sau khi user approve

Khi Device Grant hoàn tất, AS có thể cấp:

- **Access token (AT):** credential gửi tới **resource server**, thường ngắn hạn; JWT hoặc opaque là lựa chọn riêng của AS/RS.
- **Refresh token (RT):** credential gửi tới **token endpoint** nếu AS cho phép client nhận RT để xin AT mới. Với thiết bị có lưu trữ yếu hoặc rủi ro mất cắp cao, AS có thể **không cấp RT** hoặc yêu cầu rotation/sender constraint và absolute lifetime.
- **ID token** khi OIDC được dùng và profile cấp ID token: client kiểm tra OIDC authentication assertion, không dùng ID token thay AT tại RS.

### 15.1. Không trộn các loại code/token

| Giá trị | Bên nhận hợp lệ | Khi hết hiệu lực | Không được dùng làm |
| --- | --- | --- | --- |
| `user_code` | Verification page của AS | Device transaction hết hạn/đã xử lý theo policy | Bearer AT, refresh token, mật khẩu |
| `device_code` | Token endpoint của AS | Transaction hết hạn/đã consumed/revoked | Authorization header tới RS hoặc mã hiển thị công khai |
| `access_token` | Resource server đúng audience | `exp`, revocation hoặc policy RS | Credential gửi đến device authorization endpoint |
| `refresh_token` | Token endpoint của AS | Expiry, rotation, revocation hoặc binding policy | AT gọi resource API |
| `id_token` (OIDC) | OIDC client đúng audience | OIDC token claims/session policy | OAuth access token tại API |

Một access token đã được cấp có thể bị lộ ở **điểm endpoint**, dù mọi request device authorization và token polling đều dùng TLS đúng. TTL ngắn giảm cửa sổ replay; DPoP/mTLS-bound AT nếu được hỗ trợ có thể giảm giá trị của chuỗi token bị sao chép mà không có khóa. Nhưng **không** thay `aud`, scope và object ACL.

### 15.2. Mất TV và logout

Nếu Alice làm mất thiết bị:

1. Ứng dụng/AS cần hỗ trợ **thu hồi phiên/RT/grant của thiết bị đó** theo scope policy, không mặc định revoke mọi thiết bị của Alice.
2. Xóa credential local khi logout nếu thiết bị còn truy cập được; không cho rằng việc xóa local sẽ xóa bản sao RT bị đánh cắp trước đó.
3. Với JWT AT verify offline, AT còn hạn có thể tiếp tục được chấp nhận nếu RS không có revocation state; cần đặt SLA logout theo rủi ro.
4. Với opaque AT qua introspection, AS có thể trả `active=false`; cache `active=true` tại RS có thể tạo độ trễ thu hồi.
5. Device enrollment/remote wipe hoặc attestation nếu được yêu cầu là **cơ chế quản lý thiết bị riêng**, không tự phát sinh từ RFC 8628.

### 15.3. Refresh token rotation khác device authorization

Một Device Authorization transaction tạo điều kiện **cấp token ban đầu**:

~~~text
Device request -> user approve -> device_code -> AT-1 (+ RT-1 nếu cấp)
~~~

Sau đó nếu AS cấp RT và dùng rotation:

~~~text
RT-1 --refresh--> AT-2 + RT-2
RT-2 --refresh--> AT-3 + RT-3
~~~

Không bắt TV hiển thị `user_code` lại sau **mỗi AT refresh** nếu grant/RT còn hợp lệ theo chính sách. Ngược lại, nếu RT bị revoke/expired, client không được tự mint AT; nó phải thực hiện một authorization flow mới, có thể lại qua device authorization endpoint.

### 15.4. Client credentials không phải cách vượt user consent

Một số TV vendors có backend với app-only service credential. Backend đó có thể làm tác vụ hệ thống độc lập với quyền service, nhưng **không được** dùng client credentials mạnh để đọc thư viện của Alice khi Alice chưa ủy quyền. Nếu hoạt động nhạy cảm được thực hiện **thay mặt Alice**, AS/RS phải giữ user grant/subject/actor đủ rõ để tránh **confused deputy**.

## 16. Ma trận kiểm thử chức năng và bảo mật (45 ca)

Bộ test nên dùng **AS/IdP test riêng**, nhiều client registrations, simulated browser/device, token endpoint và ít nhất một RS giả lập. Có thể điều khiển đồng hồ, trạng thái transaction và barrier giữa các request để bắt race. Không đưa mã hay token production vào test/CI logs.

| ID | Trường hợp | Kết quả mong đợi |
| --- | --- | --- |
| D01 | Public client được đăng ký Device Grant POST `client_id` hợp lệ | AS trả response 200 với fields bắt buộc |
| D02 | Request dùng `application/json` thay form encoding, AS không hỗ trợ extension | Từ chối hoặc báo lỗi đúng contract; không ngầm parse tùy ý |
| D03 | Thiếu `client_id` | Từ chối device authorization request |
| D04 | `client_id` không được đăng ký | Từ chối; không cấp mã |
| D05 | Client tồn tại nhưng không được phép Device Grant | Từ chối `unauthorized_client` hoặc lỗi phù hợp |
| D06 | Confidential client không xác thực hợp lệ | Từ chối `invalid_client` |
| D07 | Public client không có client secret nhưng đăng ký cho phép | Có thể khởi tạo với `client_id`, không đòi secret giả |
| D08 | Xin `scope=media.admin` ngoài allowlist | AS từ chối hoặc áp scope policy, không cấp quyền trái phép |
| D09 | Request scope hợp lệ nhưng user chưa approve | Response chỉ chứa codes/URI, **không chứa AT/RT** |
| D10 | Response không có `device_code` | Client từ chối response không hợp lệ |
| D11 | Response không có `user_code` | Client từ chối |
| D12 | Response không có `verification_uri` | Client từ chối |
| D13 | Response không có `expires_in` hoặc giá trị 0/âm/sai kiểu | Client từ chối |
| D14 | Response thiếu `interval` | Client dùng mặc định **5 giây** |
| D15 | Response có `interval=10` | Client chờ ít nhất 10 giây giữa polls |
| D16 | Response có `verification_uri_complete` hợp lệ | Client có thể tạo QR, vẫn hiển thị mã/confirmation UX |
| D17 | Verification URI dùng HTTP hoặc host chưa tin | Client không khuyến khích user mở/không hiển thị như URI đáng tin |
| D18 | Device code sinh bằng CSPRNG đủ entropy và không trùng active | AS lưu mapping đúng, tránh predictable handle |
| D19 | Hai transaction đồng thời của một client | Có mã và state riêng, không overwrite |
| D20 | AS nhận request tạo mã vượt quota | Rate limit/backoff; không cạn storage |
| D21 | User code sai hoặc đoán hàng loạt tại verification URI | Throttle/rate limit/anti-enumeration |
| D22 | User code đúng nhưng hết hạn | Không approve hoặc cấp token |
| D23 | User đăng nhập browser nhưng chưa chọn approve | Token endpoint vẫn `authorization_pending` |
| D24 | User nhập đúng code rồi Deny | Token endpoint trả `access_denied`; không cấp token |
| D25 | User approve, scope được policy cho phép | Token endpoint có thể cấp AT đúng scope/audience |
| D26 | User approve scope nhưng user không có quyền object/tenant | RS từ chối truy cập object trái quyền |
| D27 | Device poll trước khi user hoàn thành | AS trả `authorization_pending`, không cấp token |
| D28 | Device poll nhanh hơn `interval` | AS trả `slow_down` hoặc rate response phù hợp |
| D29 | Sau `slow_down`, client tăng ít nhất 5 giây | Tốc độ polling đúng, không tiếp tục flood |
| D30 | Device poll sau `expired_token` | Client dừng, không retry cùng mã vô hạn |
| D31 | Device code thuộc client A nhưng token request từ client B | AS từ chối binding |
| D32 | Token request dùng `user_code` thay `device_code` | AS từ chối |
| D33 | Hai polls đồng thời khi APPROVED | **Tối đa một issuance thành công** theo state/AS contract |
| D34 | Token endpoint response success bị mất sau AS commit | Không mint AT thứ hai bằng replay không kiểm soát |
| D35 | Một node nhận device request, node khác nhận verification/poll | Transaction state nhất quán trên cluster |
| D36 | Device code bị rò, attacker thử poll từ client sai | Chặn client binding; phát hiện hoạt động bất thường |
| D37 | Attacker có device_code và public client_id, user approve | Test threat model chứng minh chỉ code secret có thể nguy hiểm; cần bảo vệ code |
| D38 | Attacker đưa user_code của device lạ cho nạn nhân | Verification UI hiển thị client/device và buộc approve chủ động |
| D39 | User quét QR có prefilled code | Không auto-consent chỉ từ GET/QR, vẫn xác nhận grant |
| D40 | JWKS/introspection TLS thất bại khi TV gọi API | RS không cho phép AT chưa xác minh |
| D41 | Token `aud=media-api` được gửi tới payments API | Payments từ chối sai audience |
| D42 | Refresh token của TV bị revoke nhưng AT còn hạn | RS thực thi TTL/revocation SLA thực tế, không đoán chặn ngay |
| D43 | Client nhầm ID token/device_code làm bearer access token | RS từ chối sai token purpose |
| D44 | Device client tự follow redirect /token đến host lạ | Không chuyển code/secret sang host chưa tin |
| D45 | Gateway/tracing bật ghi form `device_code` hoặc AT | Redaction test phát hiện; không có raw credential trong logs |

### 16.1. Dương tính và âm tính phải kiểm tra đúng nguyên nhân

Nếu test D31 từ chối vì **device code đã hết hạn**, không thể kết luận AS đang kiểm tra **cross-client binding**. Hãy tạo hai transaction mới với cùng điều kiện về time, scopes và grant, chỉ khác client ID:

~~~text
Client A khởi tạo code-A.
Client A poll code-A trước approve -> authorization_pending.
Client B poll code-A             -> bị từ chối do sai binding.
Alice approve code-A.
Client A poll code-A             -> có thể nhận token hợp lệ.
~~~

Tương tự khi kiểm tra RS audience: phải có ít nhất **một** AT hợp lệ được chấp nhận tại API đích, và AT tương tự có `aud` của API khác bị từ chối. Nếu cả hai request đều lỗi vì JWKS URL sai, chưa chứng minh audience validation.

### 16.2. Test ranh giới interval bằng fake clock

Không nên dùng `Thread.sleep` thực tế nhiều phút trong test. Dùng fake scheduler/clock để mô phỏng:

~~~text
T0:      AS trả expires_in=900, interval=5.
T0+4s:   Client KHÔNG gửi poll.
T0+5s:   Poll #1, AS trả authorization_pending.
T0+10s:  Poll #2, AS trả slow_down.
T0+19s:  Client KHÔNG gửi poll (interval nay >=10s).
T0+20s:  Poll #3.
T0+900s: Transaction hết hạn, không poll thêm.
~~~

Đây là một timeline lý tưởng; test scheduler có thể đưa jitter **dương** hoặc latency, nhưng không được rút ngắn interval tối thiểu. Test `slow_down` liên tiếp để bảo đảm interval không bị reset về 5 giây sau mỗi `authorization_pending`.

### 16.3. Test race bằng barrier

Tạo transaction APPROVED, rồi cho hai token requests dừng tại trước thao tác consume:

~~~text
Thread A: lookup APPROVED, wait barrier
Thread B: lookup APPROVED, wait barrier
Release barrier:
    only one atomic compare-and-consume succeeds
    the other receives a non-success response
Assert: number of issued grants/access tokens does not exceed policy
~~~

Không dùng synchronized lock chỉ trong một test JVM để giả lập multi-node AS. Thử cùng database/Redis/state store mà production sẽ dùng. Nếu response của một winner bị mất, phải chắc chắn nó không khiến loser mint token thứ hai.

## 17. Ba tình huống vận hành cần xử lý

### Tình huống A: TV hiện QR nhưng user bị lừa approve thiết bị lạ

Alice nhận tin nhắn “Đăng nhập TV bằng mã X”. Alice đang ở nhà nhưng **không khởi tạo flow trên TV**, lại thấy trang `auth.example.test` thật và nhập mã. Trang hiển thị client “Unknown Device” nhưng Alice nhấn Approve theo hướng dẫn attacker.

**Vấn đề:** Đây là **device authorization phishing**. Website thật và TLS hợp lệ không đồng nghĩa giao dịch do Alice chủ động khởi tạo. Attacker có thể giữ `device_code` và nhận AT khi user approve.

**Giải pháp:** Verification UI hiển thị rõ client, thiết bị, scope, cảnh báo “chỉ cho phép nếu bạn vừa khởi động đăng nhập trên thiết bị của mình”, yêu cầu tương tác xác nhận, rate-limit mã, risk-based MFA khi thích hợp. User nên đối chiếu mã trên TV thật; không approve chỉ vì có mã được gửi qua chat.

### Tình huống B: 50.000 thiết bị poll mỗi giây

Một phiên bản firmware lỗi gọi `POST /token` mỗi 200 ms ngay khi nhận `authorization_pending`. Token endpoint quá tải, user verification bị chậm, các client khác cũng không đăng nhập được.

**Vấn đề:** Device client không tuân thủ `interval` và không tăng interval với `slow_down`. Đây là lỗi **polling policy**, không phải cần tăng JWT TTL hay bỏ AS authentication.

**Giải pháp:** Client dùng scheduler một poller/giao dịch, khoảng tối thiểu từ `interval` hoặc 5 giây, `slow_down` cộng ít nhất 5 giây, tăng backoff khi lỗi mạng và dừng sau expiry. AS áp per-client/transaction rate limits, giám sát tỷ lệ pending/slow_down và triển khai quota cho device authorization requests.

### Tình huống C: User approve nhưng TV chưa có token

Alice xác nhận trên trang activation và thấy “Thành công”, nhưng TV vẫn báo chờ. Hai service instances của AS sử dụng storage không nhất quán: node xử lý verification ghi APPROVED vào RAM, node xử lý token polling chỉ thấy PENDING. Khi transaction hết hạn, TV thất bại.

**Vấn đề:** Những endpoint được triển khai như ba services độc lập nhưng không chia sẻ trạng thái transaction đúng cách. User approve không thể thay thế **binding ở token endpoint**.

**Giải pháp:** Shared transaction state/consistency, atomic state transition, expiry và mapping device/user code được kiểm tra đa node; đo delay từ user approval đến token issuance, có monitoring và safe retry khi AS outage. Không “chữa” bằng cách cấp AT trực tiếp từ trang verification cho TV qua QR/URL.

## 18. Checklist trước production

### 18.1. Khởi tạo giao dịch

1. **Đúng flow:** Thiết bị thật sự có browser/input hạn chế? Nếu có external browser, đã đánh giá Authorization Code + PKCE?
2. **Đúng issuer:** Trusted `device_authorization_endpoint` và `token_endpoint` lấy từ metadata/cấu hình đã phê duyệt, dùng HTTPS và cert/hostname validation?
3. **Đúng client:** AS kiểm tra `client_id`, registered grant type, client auth nếu confidential và scope/resource allowlist?
4. **Đúng request:** HTTP POST `application/x-www-form-urlencoded` UTF-8, `client_id` required, `scope` optional?
5. **Đúng response:** `device_code`, `user_code`, `verification_uri`, `expires_in` bắt buộc, `interval` optional default 5 giây?
6. **Mã bí mật:** `device_code` đủ entropy, không in ra UI/QR/log, được bind client và expiry; `user_code` dễ nhập nhưng được rate-limit?

### 18.2. User verification và polling

7. **Trang user:** Browser tới AS thật, login/MFA/consent rõ ràng, đúng client/device/scopes và không tự approve từ URL?
8. **QR:** `verification_uri_complete` chỉ chứa thông tin user cần, không chứa `device_code`; user vẫn đối chiếu phiên?
9. **Polling:** Chỉ poll token endpoint, đúng grant type và device_code, không gửi user_code làm token credential?
10. **Interval:** Không nhanh hơn `interval`, mặc định 5 giây nếu vắng; `slow_down` tăng ít nhất 5 giây?
11. **Stop conditions:** `access_denied`, `expired_token`, user cancellation, local expiry hoặc success đều kết thúc polling?
12. **AS cluster:** Pending/approved/denied/expired/consumed state và expiry nhất quán giữa các node; atomic single-winner issuance?
13. **Errors:** Timeout/5xx có backoff, không retry storm; unknown outcome không cấp token trùng trái policy?

### 18.3. Sau khi cấp token

14. **Token đúng mục đích:** Chỉ AT gửi RS, RT dùng token endpoint, ID token dùng OIDC client; device/user codes không dùng gọi API?
15. **RS verification:** JWT/JWKS hoặc opaque introspection từ AS tin cậy, kiểm tra `iss`, `aud`, `exp`, scope, tenant và object-level ACL?
16. **Lifecycle:** AT TTL ngắn theo rủi ro, RT rotation/sender constraint/expiry/revocation khi có cấp RT?
17. **Mất thiết bị:** Có phương thức revoke phiên/grant của device và xử lý AT còn hạn theo SLA?
18. **Logging:** Không ghi device code, AT/RT/client secret, login cookie vào logs/traces/debug?
19. **Abuse defense:** Rate limit device authorization/user-code input/token poll; nhận diện device-code phishing và bất thường?
20. **Tests:** Có positive/negative cases, fake clock, multi-AS issuer, multi-node state, race và quota/incident-response drills?

## 19. Câu hỏi tự kiểm tra

**Câu 1. Device authorization endpoint có trả access token không?**

Không. Endpoint này tạo giao dịch và trả `device_code`, `user_code`, `verification_uri`, `expires_in` cùng `interval` tùy chọn. Token chỉ được cấp **sau approval và kiểm tra grant hợp lệ** ở token endpoint.

**Câu 2. `device_code` và `user_code` khác nhau thế nào?**

`device_code` là credential bí mật mà device gửi đến token endpoint để poll. `user_code` là mã dễ nhập để user xác định giao dịch tại verification URI. Không hiển thị device code cho user và không dùng user code thay access token.

**Câu 3. Nếu response không có `interval`, device poll bao lâu một lần?**

Mặc định **5 giây** theo RFC 8628. Nếu nhận `slow_down` thì tăng interval ít nhất **5 giây** nữa cho các polls sau.

**Câu 4. Tại sao có `authorization_pending` dù người dùng đã nhìn thấy màn hình login?**

Việc **hiển thị** trang login không có nghĩa user đã xác thực và approve. AS giữ transaction pending cho đến khi verification/consent và policy hoàn thành.

**Câu 5. User có thể quét QR từ một người lạ và approve vì đó là trang AS thật không?**

Không nên. Đây là đường device-code phishing: attacker có thể tạo transaction và đưa mã cho user để nhận AT trên thiết bị của attacker. User chỉ approve phiên họ tự khởi tạo, sau khi xác minh client/device/scopes.

**Câu 6. Device Authorization Grant có thay thế Authorization Code + PKCE cho mọi mobile app không?**

Không. Native mobile có external browser thường phù hợp Authorization Code + PKCE. Device Grant dành cho thiết bị khó nhập liệu/không tiện dùng browser với user trên thiết bị khác.

**Câu 7. Khi người dùng approve, AS có thể cho cùng device_code nhận nhiều token do hai polls đồng thời không?**

Không nên. AS phải có state và atomic consume/issuance để tránh duplicate redemption/race. Poll lặp lúc pending là bình thường nhưng approved redemption phải tuân thủ policy single-use.

**Câu 8. TV nhận access token JWT đúng chữ ký từ AS, API còn cần check `aud` không?**

Có. JWT hợp lệ của issuer khác với token **dành cho chính resource API**. RS phải kiểm tra expected audience, scope, thời gian và object/tenant permission.

**Câu 9. User logout trên TV có làm mọi bearer AT bị sao chép trước đó lập tức mất hiệu lực không?**

Không mặc định. Thu hồi RT/grant ngăn lấy AT mới, còn JWT AT verify offline có thể tiếp tục được chấp nhận tới `exp` nếu RS không có revocation state. Cần SLA và cơ chế thu hồi thực tế.

**Câu 10. Device flow có dùng `grant_type=client_credentials` khi polling không?**

Không. Token endpoint dùng `urn:ietf:params:oauth:grant-type:device_code` và `device_code`. Client credentials là grant khác cho service hành động bằng quyền riêng, không biểu diễn user vừa approve thiết bị.

**Câu 11. Nếu token endpoint timeout sau khi user đã approve, có nên mở 10 pollers đồng thời để lấy token nhanh hơn không?**

Không. Phải tuân interval/backoff và tránh đồng thời; AS có thể đã consumed code dù response mất. Nhiều pollers gây race, thừa tải và không vượt qua được chính sách issuance.

**Câu 12. `verification_uri_complete` có luôn bắt buộc hoặc an toàn để auto-approve không?**

Không. Đây là trường **tùy chọn**, giúp truyền mã qua QR/link; AS vẫn phải hiển thị thông tin và có quyết định authorization rõ ràng, không tự approve chỉ từ việc người dùng mở link.

## 20. Tài liệu chuẩn tham khảo

- [RFC 8628 — OAuth 2.0 Device Authorization Grant](https://www.rfc-editor.org/rfc/rfc8628): device authorization endpoint, request/response fields, user verification, polling/errors và security considerations.
- [RFC 6749 — OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): OAuth roles, token endpoint, client authentication, scopes và access/refresh token.
- [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414): discovery metadata và issuer/endpoints.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700): refresh token, hạn chế replay, scopes và OAuth security BCP.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): gửi access token tới RS và rủi ro bearer token.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): JWT access token claims, issuer, audience, expiry.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662) và [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009): opaque access-token validation và thu hồi credential.
- [RFC 8707 — Resource Indicators for OAuth 2.0](https://www.rfc-editor.org/rfc/rfc8707): yêu cầu token cho resource/audience khi AS hỗ trợ.
- [RFC 8705 — OAuth 2.0 mTLS](https://www.rfc-editor.org/rfc/rfc8705) và [RFC 9449 — OAuth 2.0 DPoP](https://www.rfc-editor.org/rfc/rfc9449): sender-constrained token khi cần giảm replay.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): scope `openid`, ID token và authentication tại client.
- [Spring Authorization Server — Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html): device authorization/verification/token endpoint và tùy biến.
- [Spring Authorization Server — Core Model Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html): registered client, grant types, token/authorization settings.
- [Spring Security — OAuth 2.0 Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/index.html): xác minh access token ở API.

**Điểm cần ghi nhớ:** **Device authorization endpoint chỉ bắt đầu một giao dịch ủy quyền cho thiết bị có input/browser hạn chế.** Nó nhận `client_id` và optional `scope` qua HTTPS form POST, trả `device_code` **bí mật**, `user_code` **để user nhập**, `verification_uri`, `expires_in` và optional `interval`/`verification_uri_complete`. User xác thực/consent **trên AS qua thiết bị thứ hai**, trong khi device **poll token endpoint đúng interval** và tăng ít nhất 5 giây sau `slow_down`. Chỉ khi AS xác minh client, mã, expiry, user, scope/audience và consumed state, token endpoint mới cấp AT. Bảo mật thực tế còn cần chống device-code phishing, rate limiting, bảo vệ credential, atomic issuance, refresh-token lifecycle và kiểm tra issuer/audience/scope/ACL ở resource server.
