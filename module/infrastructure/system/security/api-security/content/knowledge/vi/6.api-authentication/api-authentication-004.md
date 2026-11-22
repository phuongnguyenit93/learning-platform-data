# OAuth 2.0, OIDC và machine-to-machine

API thường phải phục vụ cả người dùng đăng nhập qua ứng dụng và các hệ thống tự động gọi nhau. Một ứng dụng web cần truy cập API thay mặt người dùng đã đồng ý; một dịch vụ xử lý đơn hàng lại cần gọi dịch vụ kho mà không có người dùng đang ngồi trước màn hình. Hai tình huống này có danh tính, quyền và vòng đời thông tin xác thực khác nhau.

OAuth 2.0 cung cấp framework để cấp quyền truy cập có giới hạn thông qua access token. OpenID Connect (OIDC) bổ sung lớp xác thực danh tính người dùng trên OAuth 2.0. Với giao tiếp machine-to-machine (M2M), OAuth 2.0 Client Credentials cho phép một ứng dụng/dịch vụ xác thực chính nó và nhận token dành cho API đích. Chọn đúng giao thức và flow giúp giới hạn quyền, quản lý token, kiểm soát việc gọi thay mặt người dùng và giảm rủi ro lộ thông tin xác thực.

Trong phạm vi API Security, OAuth/OIDC là một phần của thiết kế bảo mật theo endpoint và luồng nghiệp vụ. Token hợp lệ chỉ cho biết một bên gọi đã được xác minh hoặc được cấp quyền ở một phạm vi nhất định; API vẫn phải kiểm tra quyền chức năng, quyền trên đối tượng dữ liệu, thuộc tính và trạng thái nghiệp vụ.

Sau bài học, người đọc có thể:

- Phân biệt OAuth 2.0 với OpenID Connect và hiểu vai trò của access token, ID token.
- Nhận diện các thành phần của authorization flow và chọn flow phù hợp cho ứng dụng có người dùng.
- Mô tả Authorization Code Flow với PKCE và các kiểm tra `state`, `nonce`, redirect URI.
- Dùng Client Credentials cho giao tiếp M2M, quản lý danh tính dịch vụ và giới hạn quyền.
- Xác minh JWT hoặc opaque token ở API, quản lý vòng đời token và giảm thiểu rủi ro lộ token.
- Tích hợp token với phân quyền endpoint, kiểm thử và giám sát.

## 1. OAuth 2.0 và OpenID Connect giải quyết vấn đề gì?

### 1.1. OAuth 2.0 là framework ủy quyền

OAuth 2.0 cho phép một client nhận quyền truy cập giới hạn tới tài nguyên được bảo vệ mà không cần biết mật khẩu của người dùng. Ví dụ, người dùng cho ứng dụng lịch truy cập danh sách sự kiện; ứng dụng nhận access token có scope phù hợp để gọi Calendar API. Mật khẩu người dùng được xử lý bởi hệ thống cấp quyền, không được chia sẻ cho ứng dụng client.

OAuth 2.0 trả lời câu hỏi: **client được phép truy cập tài nguyên nào, với phạm vi quyền nào và trong thời hạn nào?** OAuth 2.0 tự nó không phải giao thức đăng nhập người dùng và không quy định một cách chuẩn hóa để client nhận thông tin xác thực danh tính người dùng. Không nên chỉ nhìn thấy access token là kết luận người dùng đã đăng nhập theo một giao thức xác thực cụ thể.

### 1.2. OIDC bổ sung lớp xác thực danh tính

OpenID Connect là lớp nhận dạng (identity layer) xây dựng trên OAuth 2.0. OIDC định nghĩa ID token, các claim về người dùng và endpoint UserInfo để client có thể xác minh kết quả xác thực. Khi yêu cầu OIDC, client thường gửi scope `openid` cùng các scope tùy chọn như `profile` hoặc `email`.

OIDC trả lời câu hỏi: **người dùng đã xác thực với nhà cung cấp danh tính là ai?** Sau khi xác thực, client vẫn dùng access token để gọi API được bảo vệ. ID token được phát hành cho client để chứng minh sự kiện xác thực và chứa thông tin định danh theo hợp đồng OIDC; không dùng ID token thay cho access token khi gọi resource server.

| Thành phần | Mục đích | Bên thường sử dụng |
|---|---|---|
| Access token | Trình bày quyền truy cập tới API/resource server | Client gửi tới API |
| ID token | Mang kết quả xác thực và claim danh tính theo OIDC | OIDC client xác minh |
| Refresh token | Xin access token mới khi token cũ hết hạn, theo chính sách cấp quyền | Client gửi tới authorization server |
| Authorization code | Mã tạm thời đổi lấy token sau khi người dùng hoàn tất bước cấp quyền | Client gửi tới token endpoint |

Không nên đặt tên biến chung chung là `token` cho mọi loại token. Tách rõ access token, ID token và refresh token giúp tránh gửi nhầm token tới sai hệ thống.

### 1.3. Các vai trò trong OAuth 2.0

- **Resource Owner:** thường là người dùng có quyền cấp quyền truy cập tài nguyên của họ.
- **Client:** ứng dụng yêu cầu quyền truy cập, ví dụ web app, mobile app hoặc dịch vụ backend.
- **Authorization Server (AS):** xác thực client/người dùng, áp dụng chính sách cấp quyền và phát hành token.
- **Resource Server (RS):** API bảo vệ tài nguyên, nhận token và quyết định request có được phép tiếp tục hay không.

Trong hệ thống doanh nghiệp, authorization server thường là Identity Provider (IdP) hoặc nền tảng IAM. Một sản phẩm có thể triển khai AS và RS trong cùng hạ tầng, nhưng vai trò giao thức vẫn khác nhau.

## 2. Chọn flow theo loại client và danh tính cần sử dụng

Flow là cách client nhận token. Không có một flow phù hợp cho mọi ứng dụng. Hãy xác định client có người dùng tương tác hay không, client có thể giữ bí mật hay không và API cần biết danh tính người dùng hay danh tính dịch vụ.

| Tình huống | Flow thường phù hợp | Danh tính/quyền thể hiện |
|---|---|---|
| Web app hoặc ứng dụng mobile có người dùng đăng nhập | Authorization Code + PKCE, thường kết hợp OIDC | Người dùng đã xác thực; client được cấp quyền theo consent/policy |
| SPA gọi API trực tiếp | Authorization Code + PKCE | Người dùng; SPA là public client, không có client secret an toàn |
| Backend service gọi API bằng danh tính của chính service | Client Credentials | Danh tính ứng dụng/dịch vụ, không phải người dùng cuối |
| Dịch vụ cần gọi API thay mặt một người dùng | Flow delegated phù hợp hoặc token exchange/on-behalf-of theo nền tảng | Danh tính dịch vụ và ngữ cảnh ủy quyền của người dùng |
| Thiết bị có giới hạn nhập liệu và không có trình duyệt đầy đủ | Device Authorization Grant khi IdP hỗ trợ | Người dùng hoàn tất xác thực trên thiết bị khác |

Với ứng dụng mới, ưu tiên Authorization Code Flow có PKCE cho tương tác người dùng và Client Credentials cho M2M. Tránh các flow cũ hoặc rủi ro cao như Implicit Grant và Resource Owner Password Credentials (password grant). Không yêu cầu client thu thập mật khẩu người dùng để tự đổi lấy token.

## 3. Authorization Code Flow với PKCE

Authorization Code Flow tách bước tương tác với người dùng khỏi bước đổi code lấy token. Trình duyệt được chuyển tới authorization server; sau khi người dùng đăng nhập và cấp quyền, authorization server chuyển về redirect URI đã đăng ký với một authorization code ngắn hạn. Client đổi code ở token endpoint qua kênh back-channel.

PKCE (Proof Key for Code Exchange, RFC 7636) bổ sung bằng chứng để chỉ client giữ `code_verifier` ban đầu mới đổi được authorization code. PKCE đặc biệt quan trọng với public client như SPA và mobile app; cũng nên dùng cho confidential client. Chọn phương thức `S256`, không dùng `plain` khi có thể.

```mermaid
sequenceDiagram
    participant U as Người dùng
    participant C as Client
    participant A as Authorization Server
    participant R as Resource Server
    C->>C: Tạo state, nonce và code_verifier
    C->>C: Tính code_challenge = S256(code_verifier)
    C->>A: /authorize + client_id + redirect_uri + scope + state + nonce + code_challenge
    A->>U: Đăng nhập và xin cấp quyền
    U->>A: Xác thực / đồng ý
    A->>C: Redirect về callback với authorization code và state
    C->>C: So khớp state
    C->>A: /token + code + code_verifier (+ client authentication nếu confidential)
    A->>C: Access token + ID token (+ refresh token nếu được cấp)
    C->>C: Xác minh ID token theo OIDC
    C->>R: Gọi API với access token
    R->>R: Xác minh token và kiểm tra quyền
    R-->>C: Resource response
```

### 3.1. Bước 1: tạo tham số bảo vệ request

Trước khi chuyển hướng, client tạo các giá trị ngẫu nhiên khó đoán:

- `state`: liên kết response callback với request đăng nhập đã khởi tạo, giúp chống CSRF và response injection.
- `nonce`: giá trị dùng một lần để liên kết ID token nhận được với phiên xác thực OIDC hiện tại, giúp giảm nguy cơ replay.
- `code_verifier`: chuỗi ngẫu nhiên có entropy cao do client giữ kín đến bước đổi code.
- `code_challenge`: giá trị dẫn xuất từ verifier, gửi tới authorization endpoint. Với `S256`, challenge là phép biến đổi SHA-256 theo quy tắc PKCE.

Client lưu `state`, `nonce` và `code_verifier` theo đúng phiên giao dịch, không chia sẻ giữa các lần đăng nhập. Không dùng một giá trị tĩnh cho mọi người dùng.

### 3.2. Bước 2: chuyển người dùng tới authorization endpoint

Request minh họa:

```http
GET /authorize?
  response_type=code&
  client_id=web-portal&
  redirect_uri=https%3A%2F%2Fapp.example.com%2Foauth%2Fcallback&
  scope=openid%20profile%20orders.read&
  state=RANDOM_STATE&
  nonce=RANDOM_NONCE&
  code_challenge=BASE64URL_SHA256_CHALLENGE&
  code_challenge_method=S256 HTTP/1.1
Host: identity.example.com
```

Trong thực tế các tham số được gửi trên một dòng URL đã encode. Authorization server kiểm tra `client_id`, redirect URI, loại client, response type, scope, PKCE và các chính sách liên quan. Người dùng xác thực với authorization server, sau đó có thể được yêu cầu đồng ý cấp quyền tùy theo chính sách và quan hệ tin cậy.

Redirect URI phải được đăng ký trước và so khớp chính xác theo quy tắc của authorization server. Không dùng wildcard rộng hoặc lấy redirect URI tùy ý từ tham số không đáng tin cậy vì có thể tạo open redirect và làm lộ authorization code.

### 3.3. Bước 3: nhận authorization code

Sau khi hoàn tất, authorization server chuyển hướng về callback:

```text
https://app.example.com/oauth/callback?code=ONE_TIME_CODE&state=RANDOM_STATE
```

Client phải so sánh `state` nhận được với giá trị đã lưu trong phiên bắt đầu đăng nhập. Nếu thiếu hoặc không khớp, từ chối response và không đổi code. Authorization code có thời hạn ngắn, dùng một lần và gắn với client, redirect URI cùng PKCE challenge. Không ghi code hoặc toàn bộ callback URL vào log.

### 3.4. Bước 4: đổi code lấy token

Client gửi request tới token endpoint qua HTTPS:

```http
POST /token HTTP/1.1
Host: identity.example.com
Content-Type: application/x-www-form-urlencoded

grant_type=authorization_code&
code=ONE_TIME_CODE&
redirect_uri=https%3A%2F%2Fapp.example.com%2Foauth%2Fcallback&
client_id=web-portal&
code_verifier=ORIGINAL_CODE_VERIFIER
```

Confidential client còn phải xác thực client theo phương thức đã đăng ký, ví dụ `client_secret_basic`, `private_key_jwt` hoặc mutual TLS. Public client không thể giữ client secret an toàn; không nhúng secret vào mã JavaScript, mobile binary hoặc ứng dụng desktop rồi coi đó là bí mật.

Nếu thành công, token endpoint có thể trả access token, ID token và refresh token tùy scope, loại client và chính sách. Client cần xử lý lỗi `invalid_grant`, code hết hạn, code đã sử dụng hoặc PKCE verifier không khớp; không lặp vô hạn request đổi code.

### 3.5. Bước 5: xác minh ID token và gọi API

Với OIDC, client xác minh ID token trước khi sử dụng thông tin danh tính. Những kiểm tra cốt lõi gồm chữ ký, `iss` khớp issuer tin cậy, `aud` chứa client ID, `exp` còn hiệu lực và `nonce` khớp giá trị của phiên đăng nhập nếu đã gửi. Khi có nhiều audience, kiểm tra `azp` theo quy tắc OIDC. Không chỉ decode JWT rồi tin các claim vì phần payload của JWT có thể đọc được và chưa chắc đã được xác minh.

Khi gọi API, client gửi **access token**:

```http
GET /api/orders HTTP/1.1
Host: api.example.com
Authorization: Bearer ACCESS_TOKEN
Accept: application/json
```

Resource server xác minh access token theo hợp đồng của API và tiếp tục kiểm tra scope, quyền chức năng, quyền trên đối tượng và quy tắc nghiệp vụ. API không nên chấp nhận ID token chỉ vì nó cũng là JWT do cùng IdP phát hành.

## 4. OIDC: xác thực người dùng và xử lý ID token

OIDC định nghĩa cách client yêu cầu xác thực và nhận claim danh tính. Scope `openid` là điều kiện để yêu cầu OIDC; các scope `profile`, `email`, `address` hoặc `phone` có thể yêu cầu thêm claim tương ứng tùy provider và consent.

### 4.1. Các claim thường gặp trong ID token

| Claim | Ý nghĩa |
|---|---|
| `iss` | Issuer phát hành token |
| `sub` | Định danh ổn định của subject trong phạm vi issuer |
| `aud` | Audience, thường chứa client ID nhận ID token |
| `exp` | Thời điểm hết hạn |
| `iat` | Thời điểm phát hành |
| `nonce` | Giá trị liên kết token với authentication request khi được sử dụng |
| `auth_time` | Thời điểm người dùng được xác thực, nếu có |
| `acr` / `amr` | Thông tin về mức độ hoặc phương thức xác thực, nếu provider phát hành |
| `azp` | Authorized party trong trường hợp cần xác định client được ủy quyền |

Không nên dùng email làm khóa định danh duy nhất nếu hệ thống cần định danh ổn định. Email có thể thay đổi hoặc được xác minh theo chính sách khác nhau. Kết hợp `iss` và `sub` thường là cặp định danh subject phù hợp trong OIDC; phạm vi uniqueness của `sub` phụ thuộc issuer.

### 4.2. ID token không phải access token

ID token hướng tới OIDC client và có audience là client. Access token hướng tới resource server/API và có audience hoặc resource tương ứng theo hợp đồng cấp quyền. Hai token có mục đích và validation khác nhau.

| Tiêu chí | ID token | Access token |
|---|---|---|
| Dùng để | Client xác minh sự kiện xác thực và claim danh tính | Client truy cập API được bảo vệ |
| Audience | OIDC client | API/resource server |
| Bên xác minh chính | OIDC client | Resource server |
| Nội dung | Claim nhận dạng theo OIDC | Thông tin quyền hoặc định danh theo profile token của AS |
| Gửi tới API bằng Bearer | Không | Có, nếu API chấp nhận loại token đó |

Một API nhận ID token thay access token có thể chấp nhận nhầm token có audience không dành cho API. Đây là lỗi kiểm tra audience và phân biệt token type, không phải vấn đề chỉ cần kiểm tra chữ ký.

### 4.3. UserInfo và dữ liệu hồ sơ

OIDC UserInfo endpoint trả claim về người dùng khi client gửi access token hợp lệ. Client cần xác minh rằng `sub` trong UserInfo khớp `sub` trong ID token của phiên. Chỉ yêu cầu và lưu những claim thật sự cần cho chức năng; không mặc định rằng scope `profile` hoặc `email` có nghĩa ứng dụng được phép lưu mọi dữ liệu vô thời hạn.

OIDC giúp chuẩn hóa xác thực và trao đổi claim, nhưng quyền truy cập dữ liệu nghiệp vụ vẫn do API và chính sách ứng dụng quyết định. Có email hoặc claim vai trò trong ID token không tự động chứng minh người dùng được đọc mọi đơn hàng.

## 5. Machine-to-machine với Client Credentials

Trong M2M, một dịch vụ gọi API bằng danh tính của chính nó. Ví dụ, `order-service` gọi `inventory-service` để kiểm tra tồn kho. Không có người dùng cuối trực tiếp cấp quyền trong mỗi request; authorization server cấp token dựa trên danh tính client đã đăng ký và chính sách của hệ thống.

Client Credentials Grant dùng `grant_type=client_credentials`. Client xác thực tại token endpoint bằng credential đã đăng ký, đồng thời yêu cầu scope cần thiết.

```mermaid
sequenceDiagram
    participant S as order-service (Client)
    participant A as Authorization Server
    participant I as inventory-service (API)
    S->>A: POST /token (client authentication, grant_type=client_credentials, scope=inventory.read)
    A->>A: Xác minh client và policy cấp quyền
    A-->>S: Access token dành cho inventory API
    S->>I: GET /inventory/sku-100 (Bearer token)
    I->>I: Xác minh token, audience, scope và policy
    I-->>S: Kết quả tồn kho
```

### 5.1. Request Client Credentials

Ví dụ minh họa khi client sử dụng HTTP Basic để xác thực tại token endpoint:

```http
POST /token HTTP/1.1
Host: identity.example.com
Authorization: Basic BASE64_CLIENT_ID_AND_SECRET
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials&scope=inventory.read
```

Authorization server xác minh client ID và credential, kiểm tra client được phép dùng grant này và scope có nằm trong policy cấp quyền hay không. Response thường chứa access token và `expires_in`; Client Credentials thông thường không cấp refresh token. Khi token hết hạn, client xác thực lại để xin access token mới.

### 5.2. Danh tính dịch vụ khác danh tính người dùng

Access token từ Client Credentials đại diện cho client/service. Nó không chứng minh có người dùng cụ thể đã đăng nhập hoặc đồng ý cho thao tác. Nếu `order-service` dùng token của chính nó để gọi inventory, API đích cần hiểu đây là quyền của `order-service`.

Nếu nghiệp vụ yêu cầu `order-service` thực hiện thao tác thay mặt người dùng A, cần giữ lại ngữ cảnh ủy quyền của người dùng qua một flow delegated hoặc token exchange/on-behalf-of được nền tảng hỗ trợ. Không thay thế ngữ cảnh người dùng bằng một token M2M có quyền rộng rồi cho rằng hành động vẫn mang quyền của người dùng đó.

### 5.3. Giới hạn quyền giữa các dịch vụ

Mỗi service nên có client identity riêng, scope tối thiểu và audience đúng API đích. Ví dụ:

| Client identity | API đích | Scope được cấp |
|---|---|---|
| `order-service` | Inventory API | `inventory.read`, `inventory.reserve` |
| `reporting-service` | Orders API | `orders.read` |
| `notification-service` | Profile API | `profile.contact.read` |

Không dùng một client ID/secret dùng chung cho toàn bộ microservice. Nếu một credential bị lộ, danh tính riêng giúp thu hồi hoặc giới hạn phạm vi ảnh hưởng. API đích vẫn phải kiểm tra scope và quyền theo đối tượng/tenant; scope `orders.read` không nhất thiết cho phép đọc mọi đơn hàng.

## 6. Xác thực client và quản lý credential M2M

Client authentication xác minh ứng dụng đang xin token là client đã đăng ký. Nó khác với việc người dùng xác thực qua OIDC. Cần chọn phương thức phù hợp với loại client và năng lực hạ tầng.

| Phương thức | Mô tả | Lưu ý bảo mật |
|---|---|---|
| `client_secret_basic` | Client gửi ID/secret qua HTTP Basic tại token endpoint | Chỉ dùng qua TLS; secret phải có entropy cao, lưu trong secret manager và luân chuyển |
| `client_secret_post` | Client gửi secret trong form body | Hạn chế sử dụng nếu có phương thức xác thực client tốt hơn; tránh log body |
| `private_key_jwt` | Client ký JWT assertion bằng private key đã đăng ký | Không gửi private key; quản lý `kid`, thời hạn assertion và luân chuyển khóa |
| Mutual TLS | Client chứng minh sở hữu chứng thư client khi bắt tay TLS | Cần quản lý vòng đời chứng thư và cấu hình proxy/tầng TLS nhất quán |

Với workload chạy trên cloud hoặc Kubernetes, ưu tiên workload identity/federation hoặc cơ chế cấp credential ngắn hạn nếu nền tảng hỗ trợ. Điều này giảm phụ thuộc vào secret tĩnh được nhúng trong image hoặc file cấu hình. Nếu phải dùng secret, lưu trong secret manager, phân quyền đọc hẹp, luân chuyển định kỳ và có quy trình thu hồi khi nghi ngờ lộ.

Không đặt client secret trong repository, Docker image, biến JavaScript phía trình duyệt, mobile app hoặc log CI. Một public client không thể giữ secret chỉ bằng cách mã hóa hoặc làm rối mã nguồn.

## 7. Access token: JWT và opaque token

OAuth 2.0 không bắt buộc access token phải có định dạng JWT. Authorization server có thể phát hành JWT tự chứa hoặc opaque token là chuỗi không mang cấu trúc có thể đọc được bởi client.

### 7.1. JWT access token

JWT thường gồm header, payload và chữ ký. Payload có thể decode được mà không cần secret, vì vậy không được đặt mật khẩu, private key hoặc dữ liệu bí mật vào claim chỉ vì token đã ký. Chữ ký bảo vệ tính toàn vẹn, không tự động mã hóa nội dung.

Resource server cần kiểm tra ít nhất:

- Chữ ký hợp lệ theo issuer và khóa được tin cậy; chỉ cho phép thuật toán đã cấu hình, không chấp nhận `alg=none` hoặc thuật toán do token tùy ý quyết định.
- `iss` khớp issuer đã cấu hình.
- `aud` chứa đúng API/resource server đang xử lý request.
- `exp` chưa hết hạn và `nbf` đã có hiệu lực nếu claim này được sử dụng.
- Token type/profile, client hoặc subject phù hợp với loại endpoint và chính sách.
- Scope/authority có đủ cho chức năng; claim cần thiết có kiểu và giá trị hợp lệ.

Khi dùng JWKS, API lấy public key từ endpoint tin cậy được cấu hình theo issuer, chọn khóa phù hợp qua `kid` và cache theo chính sách. Không tự tin vào `jku`, `x5u` hoặc URL khóa do token không đáng tin cậy cung cấp. Cần xử lý key rotation, cache miss và thời gian chờ cập nhật khóa.

### 7.2. Opaque access token và introspection

Với opaque token, resource server thường gọi introspection endpoint của authorization server để biết token còn active hay không và nhận metadata như subject, client, scope hoặc audience theo profile của hệ thống. Endpoint introspection phải được bảo vệ bằng xác thực client và chỉ cho phép resource server được đăng ký truy vấn.

Có thể cache kết quả introspection trong thời gian ngắn để giảm tải, nhưng TTL dài làm chậm khả năng thu hồi token. Cần cân bằng độ trễ, khả năng sẵn sàng và yêu cầu thu hồi. Khi AS không truy cập được, API cần có chính sách fail-closed phù hợp với mức nhạy cảm của tài nguyên.

### 7.3. Không nhầm decode với validate

Đọc được payload JWT không chứng minh token hợp lệ. Ví dụ, đoạn code chỉ gọi `decode()` rồi lấy `sub` hoặc `scope` mà không kiểm tra chữ ký, issuer, audience và thời hạn sẽ cho phép attacker tự tạo payload giả. Luôn dùng thư viện đã được kiểm chứng và cấu hình validator rõ ràng.

## 8. Scope, audience và quyền nghiệp vụ

Scope biểu đạt phạm vi quyền mà client được cấp trong quan hệ với API. Ví dụ `orders.read`, `orders.create` hoặc `inventory.reserve`. Scope nên được đặt tên theo hành động và tài nguyên, có tài liệu mô tả chính xác và theo nguyên tắc least privilege.

Scope không nhất thiết tương đương role của người dùng. Một người có vai trò `MANAGER` trong ứng dụng vẫn có thể chỉ nhận scope `orders.read` cho một client cụ thể; ngược lại, service có scope `inventory.reserve` chỉ được thực hiện hành động đó trong phạm vi dữ liệu mà policy cho phép.

Audience giới hạn token dành cho resource server nào. Nếu token được cấp cho Orders API, Inventory API không nên chấp nhận token đó chỉ vì chữ ký do cùng issuer phát hành. Cần cấu hình audience/resource indicator phù hợp và kiểm tra `aud` ở API.

Sau khi xác minh token, API cần tiếp tục đánh giá:

1. Quyền chức năng: caller có scope/authority để gọi endpoint không?
2. Quyền đối tượng: caller có quyền trên bản ghi, tenant, tài khoản hoặc tài nguyên cụ thể không?
3. Quyền thuộc tính: caller có được đọc hoặc thay đổi trường dữ liệu này không?
4. Quy tắc nghiệp vụ: trạng thái hiện tại có cho phép hành động không, có yêu cầu phân tách nhiệm vụ hay điều kiện bổ sung không?

Không đưa toàn bộ quyền quản trị vào token dài hạn chỉ để giảm số lần kiểm tra. Quyền có thể thay đổi trong thời gian token còn hiệu lực; với thao tác nhạy cảm, cân nhắc kiểm tra policy hiện thời ở resource server.

## 9. Vòng đời token và bảo vệ token

### 9.1. Access token ngắn hạn

Access token bearer có thể bị sử dụng bởi bất kỳ bên nào sở hữu nó. Giữ thời hạn token vừa đủ ngắn theo rủi ro và trải nghiệm; thời hạn chính xác phụ thuộc mức nhạy cảm, kiến trúc và khả năng xin token mới. Không cấp token có scope rộng và thời hạn dài nếu client chỉ cần một thao tác nhỏ.

JWT tự chứa thường khó thu hồi tức thì nếu API chỉ xác minh chữ ký offline. Các chiến lược giảm rủi ro gồm thời hạn ngắn, denylist/jti cho trường hợp cần thu hồi, introspection, hoặc sender-constrained token. Cần hiểu rõ trade-off giữa tính sẵn sàng và độ trễ thu hồi.

### 9.2. Refresh token

Refresh token dùng để xin access token mới mà không yêu cầu người dùng đăng nhập lại ngay. Đây là credential có giá trị cao, cần bảo vệ chặt hơn access token:

- Chỉ phát hành cho client và tình huống được policy cho phép; không mặc định mọi client đều cần refresh token.
- Lưu trữ an toàn, giới hạn scope/resource, gắn với client và phiên/ủy quyền tương ứng.
- Với public client, áp dụng refresh token rotation hoặc cơ chế sender-constrained phù hợp; phát hiện việc sử dụng lại refresh token cũ để nhận biết khả năng bị đánh cắp.
- Thu hồi refresh token khi người dùng đăng xuất, thu hồi consent, tài khoản bị khóa hoặc có sự cố theo chính sách.
- Không ghi refresh token vào log, analytics, URL hoặc báo cáo lỗi.

Client Credentials thông thường không dùng refresh token; khi access token hết hạn, service lấy token mới bằng client authentication.

### 9.3. Giảm nguy cơ token bị đánh cắp

- Chỉ truyền token qua HTTPS và dùng header `Authorization: Bearer`; không đặt token trong URL.
- Không ghi token vào log, tracing, exception, crash report hoặc telemetry. Mask header nhạy cảm ở proxy và API Gateway.
- Giới hạn nơi lưu token ở client. Với web app, cân nhắc Backend-for-Frontend (BFF) giữ token phía server và cấp session cookie `HttpOnly`, `Secure`, `SameSite` phù hợp; BFF vẫn phải có bảo vệ CSRF. Nếu SPA giữ token, tránh lưu credential dài hạn trong nơi có thể bị JavaScript đọc khi xảy ra XSS.
- Với mobile/native app, dùng system browser/external user-agent cho đăng nhập và PKCE; không nhúng client secret.
- Cân nhắc sender-constrained token như mTLS hoặc DPoP khi mức rủi ro và hệ sinh thái hỗ trợ. DPoP ràng buộc token với khóa của client ở tầng ứng dụng; mTLS ràng buộc với chứng thư client ở tầng TLS.
- Có quy trình phát hiện, thu hồi và luân chuyển khi token/credential bị lộ.

## 10. Tích hợp OAuth/OIDC với API và Spring Security

Một resource server Spring Boot thường được cấu hình để xác minh JWT do issuer tin cậy phát hành. Cấu hình dưới đây minh họa việc khai báo issuer và audience; chi tiết phụ thuộc phiên bản Spring Security và cách provider phát hành token.

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://identity.example.com/issuer
```

Ứng dụng cần thêm validator audience phù hợp, ánh xạ scope thành authority và áp dụng policy cho endpoint. Ví dụ minh họa:

```java
@RestController
@RequestMapping("/api/orders")
class OrderController {

    @GetMapping("/{id}")
    @PreAuthorize("hasAuthority('SCOPE_orders.read')")
    OrderResponse get(@PathVariable UUID id,
                      @AuthenticationPrincipal Jwt jwt) {
        String subject = jwt.getSubject();
        return orderService.getOrderVisibleTo(subject, id);
    }
}
```

`SCOPE_orders.read` chỉ minh họa quyền mức chức năng được ánh xạ từ scope. `orderService.getOrderVisibleTo` vẫn phải kiểm tra đối tượng, tenant và các điều kiện nghiệp vụ. Trong ứng dụng thực tế, không nên mặc định `sub` là user ID nội bộ nếu issuer có thể phát hành subject theo namespace khác; cần ánh xạ danh tính theo issuer và quy ước của hệ thống.

Với opaque token, Spring Security có thể dùng opaque token introspection thay vì JWT decoder. Khi đó cấu hình client để introspection endpoint xác minh token và resource server phải xử lý timeout, cache và tình huống AS không sẵn sàng theo chính sách.

Không chỉ cấu hình `issuer-uri` rồi coi API đã hoàn tất bảo mật. Hãy kiểm tra rõ issuer, audience, thuật toán/chữ ký, thời hạn, scope mapping, token type, quyền đối tượng và cách xử lý lỗi.

## 11. Mã lỗi xác thực và phân quyền

API nên phân biệt lỗi xác thực với lỗi phân quyền theo hợp đồng:

| Trường hợp | Response thường dùng | Ý nghĩa |
|---|---|---|
| Không có bearer token hoặc token không hợp lệ | `401 Unauthorized` | Request chưa có thông tin xác thực được chấp nhận; thường kèm `WWW-Authenticate: Bearer` |
| Token hết hạn hoặc sai audience/issuer | `401 Unauthorized` | Token không hợp lệ cho API này |
| Token hợp lệ nhưng thiếu scope/quyền chức năng | `403 Forbidden` | Caller đã xác thực nhưng không đủ quyền |
| Có scope nhưng không có quyền trên đối tượng | `403` hoặc `404` theo chính sách | Từ chối truy cập; có thể che giấu sự tồn tại của đối tượng |
| Authorization server tạm thời không sẵn sàng | Lỗi phụ thuộc theo chính sách, thường là `5xx` nếu không thể xác minh an toàn | Không được coi lỗi xác minh là token hợp lệ |

Không trả chi tiết nội bộ như khóa nào thất bại, claim bí mật hoặc cấu hình IdP. Có thể trả mã lỗi chung cho client và ghi nguyên nhân đã được giảm thiểu vào log bảo mật. Không chuyển lỗi introspection hoặc lỗi kiểm tra chữ ký thành quyền truy cập mặc định.

## 12. Kiểm thử và giám sát OAuth/OIDC/M2M

Kiểm thử cần bao gồm cả luồng thành công và tình huống token/request bị giả mạo hoặc không còn hiệu lực.

### 12.1. Kiểm thử Authorization Code + PKCE và OIDC

- Redirect URI không đăng ký hoặc chỉ khác một phần phải bị từ chối.
- `state` bị thiếu, sai hoặc dùng lại phải không tạo phiên đăng nhập hợp lệ.
- `code_verifier` không khớp `code_challenge` phải khiến token exchange thất bại.
- Authorization code hết hạn hoặc đã dùng không được đổi lần nữa.
- ID token sai chữ ký, issuer, audience, thời hạn hoặc nonce phải bị từ chối.
- Không chấp nhận ID token làm access token tại resource server.
- Kiểm tra logout, refresh token rotation, reuse detection và thu hồi theo chính sách.
- Kiểm tra callback không tạo open redirect và không làm lộ code/token qua log hoặc referrer.

### 12.2. Kiểm thử Client Credentials

- Client ID/secret sai, secret đã thu hồi hoặc assertion/chứng thư không hợp lệ phải bị từ chối.
- Client không được đăng ký Client Credentials grant không thể dùng grant này.
- Scope ngoài policy, audience không đúng hoặc token dành cho API khác phải bị từ chối.
- Service A không thể dùng credential của service B hoặc quyền của service B.
- Token M2M không được xem như danh tính người dùng cuối.
- Credential rotation và thu hồi được phản ánh đúng trong khoảng thời gian kỳ vọng.

### 12.3. Kiểm thử resource server

- JWT sai chữ ký, `alg` không được cho phép, `kid` không tồn tại, issuer/audience sai hoặc token hết hạn đều bị từ chối.
- Opaque token inactive hoặc introspection lỗi phải được xử lý theo chính sách fail-closed.
- Token hợp lệ nhưng thiếu scope, sai tenant hoặc truy cập object của người khác vẫn bị từ chối.
- Token có scope đọc không được thực hiện thao tác ghi/xóa/duyệt.
- API không làm lộ token, claim nhạy cảm hoặc nội dung authorization header trong log và response.

### 12.4. Giám sát

Theo dõi tỷ lệ token exchange thất bại, lỗi `invalid_client`/`invalid_grant`, số lần refresh token reuse, lỗi chữ ký/audience, request `401`/`403`, client/service gọi endpoint ngoài scope và các lần introspection timeout. Log nên ghi client ID hoặc service identity đã được kiểm soát, issuer, audience/route, scope decision, request ID và kết quả; không ghi raw access token, refresh token, client secret hoặc assertion.

Khi phát hiện credential bị lộ, xác định client/service bị ảnh hưởng, thu hồi hoặc luân chuyển credential, giới hạn scope/audience, đánh giá token đã phát hành còn hiệu lực bao lâu và kiểm tra log truy cập. Với sự cố liên quan refresh token, xem xét thu hồi cả chuỗi token/ủy quyền tương ứng theo khả năng của authorization server.

## 13. Checklist thiết kế và review

- [ ] Đã xác định API cần danh tính người dùng, danh tính service hay cả hai.
- [ ] Dùng OAuth 2.0 cho ủy quyền và OIDC khi client cần xác thực người dùng.
- [ ] Dùng Authorization Code + PKCE cho ứng dụng tương tác; không dùng Implicit hoặc password grant cho hệ thống mới.
- [ ] `state`, `nonce`, `code_verifier` được tạo ngẫu nhiên và kiểm tra đúng phiên.
- [ ] Redirect URI được đăng ký và so khớp chính xác; callback không tạo open redirect.
- [ ] ID token chỉ được OIDC client xác minh; API dùng access token dành cho đúng audience.
- [ ] M2M dùng Client Credentials hoặc workload identity phù hợp; mỗi service có client identity riêng.
- [ ] Client authentication dùng phương thức phù hợp; secret/private key không nằm trong mã nguồn hoặc image.
- [ ] Scope tối thiểu và audience giới hạn đúng resource server.
- [ ] Resource server kiểm tra chữ ký/issuer/audience/exp/nbf/token type và scope theo hợp đồng.
- [ ] Opaque token introspection có xác thực, timeout và cache phù hợp.
- [ ] Refresh token được bảo vệ, rotation/reuse detection/thu hồi được thiết kế khi cần.
- [ ] Token không xuất hiện trong URL, log, tracing hoặc telemetry.
- [ ] API vẫn kiểm tra quyền chức năng, đối tượng, thuộc tính và trạng thái nghiệp vụ sau khi xác minh token.
- [ ] Có test token sai, thiếu quyền, sai audience, token M2M và tình huống thu hồi.
- [ ] Có giám sát cho token exchange, refresh, lỗi xác thực và hành vi service bất thường.

## Kết luận

OAuth 2.0 cung cấp cách cấp quyền truy cập có giới hạn; OIDC bổ sung cách client xác minh danh tính người dùng; Client Credentials cung cấp danh tính ứng dụng cho giao tiếp M2M. Authorization Code + PKCE phù hợp cho luồng người dùng tương tác, còn M2M cần credential riêng, scope tối thiểu và audience đúng API. Dù token được phát hành theo flow nào, resource server vẫn phải xác minh token và áp dụng chính sách theo endpoint, đối tượng dữ liệu, thuộc tính và luồng nghiệp vụ. Đây là cách biến token thành một phần của hệ thống bảo mật API thay vì xem token là quyền truy cập tuyệt đối.
