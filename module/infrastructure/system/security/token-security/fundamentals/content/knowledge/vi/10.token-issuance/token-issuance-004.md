# Điểm cuối cấp token

## Mục tiêu học tập

Sau bài học này, bạn có thể:

- Giải thích **token endpoint** của OAuth 2.0 là gì, vai trò của nó trong ranh giới tin cậy giữa **client**, **Authorization Server** và **Resource Server**.
- Phân biệt **authorization endpoint**, **token endpoint**, **introspection endpoint**, **revocation endpoint** và **JWKS endpoint**; hiểu vì sao chúng không thay thế nhau.
- Mô tả yêu cầu và phản hồi của token endpoint với các grant phổ biến: **authorization_code + PKCE**, **refresh_token** và **client_credentials**.
- Nhận diện những điểm bảo mật bắt buộc: TLS, xác thực/ràng buộc client, code sử dụng một lần, redirect URI, PKCE, scope, audience, thời hạn, hạn chế cấp quyền và bảo vệ token.
- Phân tích lỗi khi đổi token, kiểm soát refresh token rotation, phát hiện tái sử dụng và giám sát hoạt động cấp token mà không làm lộ credential.

## 1. Token endpoint là đâu trong mô hình OAuth 2.0?

Trong OAuth 2.0, **Authorization Server (AS)** cung cấp một **token endpoint** để client gửi yêu cầu lấy access token bằng grant phù hợp. Đây là một giao diện thuộc **máy chủ cấp token**, không phải endpoint nghiệp vụ của API.

Ví dụ trong một hệ thống:

~~~text
Authorization Server:
    https://identity.example.test/oauth2/authorize
    https://identity.example.test/oauth2/token

Resource Server:
    https://orders.example.test/api/orders
~~~

Các URL này **chỉ dùng để minh họa**. Đường dẫn cụ thể phụ thuộc nhà cung cấp, cấu hình máy chủ và metadata giao thức; chuẩn OAuth không bắt buộc mọi hệ thống phải dùng đúng đường dẫn **/oauth2/token**.

Ba vai trò có trách nhiệm khác nhau:

| Thành phần | Trách nhiệm chính | Thông tin thường xử lý |
| --- | --- | --- |
| **Client** | Yêu cầu ủy quyền và sử dụng token theo phạm vi được cấp. | Authorization code, code verifier, access/refresh token và thông tin xác thực client phù hợp. |
| **Authorization Server** | Xác minh grant/client, đánh giá chính sách và cấp token. | Cấu hình client, phiên, sự ủy quyền, scope, audience, khóa ký, trạng thái refresh token. |
| **Resource Server** | Nhận access token và quyết định truy cập tài nguyên. | Issuer, audience, chữ ký/trạng thái token, scope, permission và ngữ cảnh tài nguyên. |

**Token endpoint không tự thay Resource Server quyết định người dùng có được sửa đơn hàng #123 hay không.** AS quyết định có thể phát hành token gì cho client dựa trên grant và chính sách. API vẫn phải kiểm token và phân quyền khi xử lý từng yêu cầu quan trọng.

Một access token do token endpoint phát hành có thể là **JWT** hoặc **opaque token**. Hình thức biểu diễn không thay đổi vai trò của token endpoint: đây vẫn là nơi **phát hành/đổi token theo giao thức**, không phải nơi client dùng refresh token để trực tiếp truy cập dữ liệu nghiệp vụ.

## 2. Phân biệt các điểm cuối dễ nhầm

| Điểm cuối | Chủ thể thường gọi | Mục đích | Không nên dùng để |
| --- | --- | --- | --- |
| **Authorization endpoint** | User agent/trình duyệt theo luồng tương tác | Khởi động yêu cầu ủy quyền, xử lý đăng nhập/consent và trả kết quả như authorization code. | Gửi trực tiếp refresh token để đổi access token. |
| **Token endpoint** | OAuth client | Đổi grant hợp lệ thành token hoặc xin token mới theo giao thức. | Gửi access token vào để đọc dữ liệu đơn hàng. |
| **Introspection endpoint** | Resource Server hoặc bên được AS cho phép | Hỏi trạng thái/thuộc tính token theo RFC 7662. | Phát hành access token như một token grant. |
| **Revocation endpoint** | Client được phép hoặc thành phần tương ứng | Yêu cầu thu hồi token theo RFC 7009. | Coi việc thu hồi RT là bảo đảm tức thì mọi JWT đã cấp bị từ chối. |
| **JWKS endpoint** | Bên xác minh chữ ký/token | Công bố khóa công khai phục vụ xác minh theo cấu hình tin cậy. | Nhận username/password hoặc grant để cấp token. |
| **UserInfo endpoint (OIDC)** | Client được ủy quyền | Lấy thông tin claim về End-User theo OIDC. | Làm token endpoint hoặc thay access token bằng ID token. |

Tổ chức có thể triển khai một số điểm cuối tùy loại giao thức và tính năng; không phải dịch vụ OAuth nào cũng công bố tất cả endpoint nói trên.

### Tìm token endpoint đúng bằng metadata

Khi Authorization Server hỗ trợ **OAuth 2.0 Authorization Server Metadata (RFC 8414)**, client có thể lấy cấu hình được công bố, trong đó có trường **token_endpoint**. Với OIDC, client có thể dùng **OpenID Provider Configuration** phù hợp.

Ví dụ JSON metadata minh họa:

~~~json
{
  "issuer": "https://identity.example.test",
  "authorization_endpoint": "https://identity.example.test/oauth2/authorize",
  "token_endpoint": "https://identity.example.test/oauth2/token",
  "jwks_uri": "https://identity.example.test/.well-known/jwks.json",
  "grant_types_supported": [
    "authorization_code",
    "refresh_token",
    "client_credentials"
  ],
  "token_endpoint_auth_methods_supported": [
    "client_secret_basic",
    "private_key_jwt"
  ]
}
~~~

Đây chỉ là **metadata ví dụ**, không phải cấu hình của một dịch vụ thật.

**Không lấy URL token endpoint từ một tham số không đáng tin do người dùng tự đưa vào rồi gửi client secret hoặc refresh token tới đó.** Client cần xác minh issuer/metadata theo cấu hình tin cậy và chống các kiểu giả mạo/nhầm Authorization Server.

## 3. Cấu trúc chung của yêu cầu token

Theo OAuth 2.0, token endpoint tiếp nhận **HTTP POST** với các tham số thường dùng ở định dạng **application/x-www-form-urlencoded**. Kết nối phải được bảo vệ bằng TLS.

Ví dụ khung giao thức:

~~~http
POST /oauth2/token HTTP/1.1
Host: identity.example.test
Content-Type: application/x-www-form-urlencoded

grant_type=...
~~~

Tham số **grant_type** cho biết cơ sở mà client muốn sử dụng để yêu cầu token, chẳng hạn:

- **authorization_code**: đổi authorization code nhận từ luồng ủy quyền.
- **refresh_token**: dùng refresh token còn hợp lệ để xin access token mới.
- **client_credentials**: client xin access token theo quyền của chính ứng dụng/dịch vụ.

Các grant khác có thể được hỗ trợ bởi profile hoặc extension, ví dụ **device_code grant** hay **token exchange**. Không nên coi mọi máy chủ đều hỗ trợ mọi grant.

**Lưu ý bảo mật:** Các ví dụ HTTP trong bài dùng hostname và giá trị giả. Mỗi loại grant vẫn cần xác thực/ràng buộc client, chính sách và các tham số riêng; gửi đúng chuỗi grant_type không tự đủ để được cấp token.

### Token endpoint không có nghĩa “nhập mật khẩu ở đây”

Một nhầm lẫn phổ biến là nghĩ mọi client nên gửi **username/password của người dùng** thẳng đến token endpoint. Đó không phải mô hình được khuyến nghị cho ứng dụng hiện đại. **Resource Owner Password Credentials grant** là mô hình cũ không được OAuth 2.0 Security Best Current Practice (RFC 9700) khuyến nghị sử dụng; ứng dụng có người dùng nên ưu tiên luồng phù hợp như **Authorization Code + PKCE**.

Ở luồng Authorization Code, việc người dùng xác thực và đồng ý thường diễn ra qua **Authorization Server**, không phải client thu thập mật khẩu rồi đổi token thay người dùng.

## 4. Luồng Authorization Code + PKCE và token endpoint

Đây là một luồng phổ biến cho ứng dụng đăng nhập tương tác. Client đưa người dùng tới authorization endpoint để nhận **authorization code**, rồi đổi code thành token tại token endpoint.

~~~mermaid
sequenceDiagram
    participant U as Người dùng
    participant C as OAuth Client
    participant AS as Authorization Server
    participant API as Orders API

    C->>C: Tạo code_verifier ngẫu nhiên và code_challenge
    C->>AS: Redirect /authorize với client_id, redirect_uri, scope, state, code_challenge
    AS->>U: Xác thực/consent theo chính sách
    AS-->>C: Redirect trở lại với code và state
    C->>C: Kiểm state và liên kết đúng phiên
    C->>AS: POST /token grant_type=authorization_code + code + code_verifier
    AS->>AS: Kiểm code, client, redirect_uri, PKCE và chính sách
    AS-->>C: Access token (+ refresh token/ID token nếu phù hợp)
    C->>API: Gửi access token đúng audience/scope
    API-->>C: Dữ liệu hoặc từ chối theo quyền hiện hành
~~~

**PKCE (Proof Key for Code Exchange, RFC 7636)** sử dụng một giá trị **code_verifier** bí mật theo từng phiên ủy quyền. Client gửi **code_challenge** (thường dùng phương thức **S256**) ở authorization request và cung cấp **code_verifier** khi đổi code tại token endpoint. AS đối chiếu chúng để hạn chế việc authorization code bị chặn và đổi bởi bên không có verifier.

### Ví dụ POST đổi code ở public client

~~~http
POST /oauth2/token HTTP/1.1
Host: identity.example.test
Content-Type: application/x-www-form-urlencoded

grant_type=authorization_code&client_id=dashboard-public&code=EXAMPLE_AUTHORIZATION_CODE&redirect_uri=https%3A%2F%2Fapp.example.test%2Fcallback&code_verifier=EXAMPLE_VALID_CODE_VERIFIER
~~~

Đây là request **minh họa về các trường**, không phải giá trị code_verifier đáp ứng đầy đủ yêu cầu độ dài/entropy. Trong thực tế, verifier cần được tạo ngẫu nhiên theo quy tắc PKCE; không dùng một chuỗi cố định cho mọi lần đăng nhập.

Public client có thể phải gửi **client_id** để AS biết client nào đang đổi code, nhưng **client_id không phải bí mật**. Public client không thể dựa vào client secret nhúng sẵn trong mã trình duyệt hoặc ứng dụng mobile như bằng chứng bí mật đáng tin.

### Những kiểm tra quan trọng ở AS

Khi nhận yêu cầu đổi authorization code, token endpoint cần xác minh:

1. Code được phát hành bởi chính AS theo luồng hợp lệ.
2. Code còn hiệu lực, **chưa từng được sử dụng** và gắn với client yêu cầu.
3. **redirect_uri** phù hợp với giá trị đã được dùng trong authorization request theo quy tắc của luồng/profile.
4. **code_verifier** khớp code_challenge đã đăng ký cho code và đáp ứng phương thức PKCE được hỗ trợ.
5. Client được phép sử dụng grant và được xác thực/ràng buộc theo loại client đã đăng ký.
6. Phạm vi ủy quyền, policy và trạng thái cần thiết vẫn cho phép phát hành token.
7. Access token mới có audience, scope và thời hạn đúng hợp đồng API; refresh token chỉ được cấp khi policy cho phép.

**Authorization code phải được xử lý như credential sử dụng một lần**, thường có thời hạn rất ngắn. Khi code bị dùng lại, AS phải từ chối và thực hiện phản ứng theo quy định giao thức/chính sách; không phát hành thêm token chỉ vì code vẫn có hình thức hợp lệ.

### Phân biệt state, PKCE và nonce

- **state** thường do client dùng để liên kết authorization response với request ban đầu và chống CSRF/nhầm phiên; client kiểm ở lúc nhận redirect, không gửi state như một bằng chứng thay cho PKCE.
- **code_verifier** dùng tại **token endpoint** để chứng minh client đang đổi code có verifier tương ứng với code_challenge.
- **nonce** thuộc những luồng OIDC phù hợp, giúp client liên kết ID token với phiên xác thực và giảm các kiểu phát lại/nhầm token theo quy tắc OIDC.

Ba giá trị giải quyết những vấn đề khác nhau và **không thay thế nhau**.

## 5. Xác thực client tại token endpoint

**Client authentication** là cách Authorization Server xác minh danh tính của một client có khả năng bảo vệ credential. Nó khác với việc xác thực người dùng cuối.

| Loại client | Đặc điểm | Hướng xử lý ở token endpoint |
| --- | --- | --- |
| **Confidential client** | Backend/server có thể bảo vệ secret, khóa riêng hoặc chứng chỉ. | Sử dụng cơ chế xác thực client đã đăng ký như client_secret_basic, private_key_jwt hoặc mTLS. |
| **Public client** | SPA, native/mobile app thường không thể giữ client secret nhúng khỏi người dùng/kẻ tấn công trên thiết bị. | Định danh bằng client_id, PKCE và biện pháp bảo vệ token/grant phù hợp; không coi secret nhúng là xác thực mạnh. |

Ví dụ một confidential client dùng HTTP Basic:

~~~http
POST /oauth2/token HTTP/1.1
Host: identity.example.test
Authorization: Basic EXAMPLE_BASE64_CLIENT_CREDENTIALS
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials&scope=reports%3Aread
~~~

**HTTP Basic được mã hóa dạng base64 không phải mã hóa bí mật.** TLS là yêu cầu quan trọng; credential cần được lưu an toàn và không ghi vào log. Đoạn minh họa không chứa thông tin thực.

Ngoài client_secret_basic, hệ thống có thể sử dụng các phương thức được tiêu chuẩn hóa và AS hỗ trợ, chẳng hạn:

- **private_key_jwt**: client chứng minh mình sở hữu khóa ký thông qua một client assertion JWT đúng audience, thời gian và quy tắc kiểm tra của AS.
- **mTLS client authentication**: AS xác minh chứng chỉ client và ràng buộc phù hợp.
- Những cách khác theo profile hoặc cấu hình nhà cung cấp.

**Không tự chấp nhận phương thức xác thực client do request khai báo** nếu client chưa đăng ký hoặc AS không hỗ trợ phương thức đó. Với client dùng khóa hoặc assertion, cần kiểm issuer/subject/audience/thời hạn và chống phát lại theo đặc tả tương ứng.

## 6. Grant client_credentials: phát hành token cho dịch vụ

Trong **client_credentials grant**, một ứng dụng hoặc workload xin token theo quyền của **chính client**, không nhất thiết nhân danh một người dùng.

Ví dụ, một worker lấy báo cáo định kỳ:

~~~text
Client: nightly-report-worker
Token endpoint: identity.example.test/oauth2/token
Grant type: client_credentials
Requested scope: reports:generate
Target Resource Server: reports-api
~~~

Một request token có thể sử dụng xác thực client bí mật, khóa ký hoặc mTLS như đã đăng ký. AS sẽ kiểm client được phép dùng grant và scope; nếu hợp lệ, cấp access token theo audience/resource đích và policy.

Không nên áp dụng role của người dùng đang đăng nhập cho token client_credentials nếu không có cơ chế ủy quyền/delegation rõ ràng. Với một số JWT access token profile, **sub** có thể đại diện client/workload, không phải user.

### Vì sao client_credentials thường không cần refresh token?

Client đã có phương tiện xác thực riêng để yêu cầu access token mới, do đó AS thường không cần phát hành refresh token cho grant này. Theo RFC 6749, refresh token **SHOULD NOT** được đưa vào phản hồi client_credentials.

Nếu một dịch vụ dùng client_credentials mà vẫn lưu refresh token được cấp từ một profile riêng, phải kiểm tra hợp đồng AS và rủi ro thực tế, không mặc định mô hình phiên người dùng áp dụng cho mọi workload.

## 7. Grant refresh_token: điểm cuối cấp lại access token

Một client có thể được AS cấp **refresh token** theo chính sách. Khi access token hết hạn hoặc sắp hết hạn, client gửi refresh token đến **token endpoint**, không phải Orders API:

~~~http
POST /oauth2/token HTTP/1.1
Host: identity.example.test
Content-Type: application/x-www-form-urlencoded

grant_type=refresh_token&refresh_token=EXAMPLE_REFRESH_TOKEN&client_id=dashboard-public
~~~

Request minh họa dùng public client và lược bỏ các bằng chứng ràng buộc như DPoP nếu được yêu cầu; với confidential client, phải áp dụng xác thực client tương ứng.

AS cần đánh giá:

- Refresh token có tồn tại, chưa hết hạn/thu hồi và đúng trạng thái không?
- Token có được cấp cho **đúng client** và được sử dụng với ràng buộc/khóa cần thiết không?
- Client còn được phép nhận token theo sự ủy quyền, phiên và chính sách hiện hành không?
- Scope yêu cầu (nếu có) có nằm trong phạm vi đã được cấp không?
- Có áp dụng **refresh token rotation** hoặc sender-constraining không?
- Audience/resource mục tiêu có được chấp nhận theo hợp đồng không?

Với **refresh token rotation**, AS thường cấp refresh token mới khi refresh thành công, đồng thời vô hiệu refresh token cũ. Client phải cập nhật RT mới một cách nhất quán và tránh gửi nhiều refresh request song song với cùng RT. Việc dùng lại một RT đã vô hiệu có thể là tín hiệu bị lộ, nhưng cũng có thể phát sinh do request cạnh tranh hoặc sự cố mạng; chính sách phản ứng phải phù hợp.

**Refresh token không cho quyền truy cập API nghiệp vụ.** Nó chỉ là credential gửi tới AS để xin token mới khi được cho phép. Thu hồi refresh token không tự động làm mọi access token JWT đang lưu hành hết hiệu lực ngay nếu Resource Server chỉ xác minh chữ ký ngoại tuyến.

## 8. Phản hồi thành công: access_token, token_type, expires_in, scope

Khi token endpoint chấp thuận một yêu cầu cấp token, AS thường trả JSON tương tự:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store
Pragma: no-cache

{
  "access_token": "EXAMPLE_ACCESS_TOKEN",
  "token_type": "Bearer",
  "expires_in": 900,
  "scope": "orders:read",
  "refresh_token": "EXAMPLE_REFRESH_TOKEN"
}
~~~

Đây là **phản hồi minh họa**. Không phải grant nào cũng trả refresh token. Thời hạn 900 giây là một ví dụ, không phải mặc định của giao thức hoặc khuyến nghị chung.

| Trường | Ý nghĩa | Lưu ý |
| --- | --- | --- |
| **access_token** | Credential dùng tại Resource Server được cấp quyền nhận. | Phải được bảo vệ như bí mật; nội dung có thể là JWT hoặc opaque. |
| **token_type** | Cách sử dụng token theo profile, ví dụ Bearer. | Không tự ý dùng Bearer khi token được ràng buộc bên gửi và có cơ chế proof riêng. |
| **expires_in** | Thời hạn access token, tính theo giây như được quy định trong phản hồi OAuth. | Client có thể dùng biên an toàn nhỏ khi lập lịch refresh; RS vẫn phải tự xác minh hiệu lực. |
| **scope** | Scope liên quan đến access token được cấp. | Phải đọc **scope thực sự được cấp**, không đoán AS luôn đồng ý scope đã xin. |
| **refresh_token** | Token để xin access token mới khi policy cho phép. | Trường tùy điều kiện/grant; không dùng ở Resource Server, cần rotation/lưu trữ an toàn khi áp dụng. |

Theo OAuth 2.0, trong phản hồi token, **scope** là trường cần trả khi khác scope client đã yêu cầu (các trường hợp còn lại phụ thuộc đặc tả/profile). Với OIDC, phản hồi của luồng có thể có thêm **id_token** theo quy tắc OIDC. **ID token** phục vụ client xác minh sự kiện xác thực, không dùng làm access token cho API.

Dù token endpoint trả một JWT có thể đọc được, client không được tự tin rằng mọi claim là bằng chứng quyền vĩnh viễn. Resource Server phải xác minh issuer, audience, scope và chính sách hiện hành trên tài nguyên khi cần.

### Vì sao phải có Cache-Control: no-store?

Phản hồi chứa token là dữ liệu nhạy cảm; RFC 6749 quy định các header chống cache phù hợp cho phản hồi chứa token. Không nên để proxy, bộ nhớ đệm dùng chung hoặc log giữ bản sao response body. Với token có quyền cao, việc hạn chế nơi có thể lưu token là một phần của mô hình tin cậy.

## 9. Cấp scope, audience và claims theo quyền tối thiểu

Token endpoint không nên cấp toàn bộ scope chỉ vì client đã yêu cầu. Việc cấp phát cần dựa trên **client registration**, sự ủy quyền/consent (nếu có người dùng), chính sách và API/resource mục tiêu.

Giả sử client báo cáo xin:

~~~text
scope = "reports:read orders:write payments:refund"
~~~

Nhưng client chỉ được phép đọc báo cáo. AS phải **không phát hành quyền vượt cấu hình hoặc sự ủy quyền**; tùy chính sách, có thể cấp scope ít hơn hoặc trả lỗi. Client cần xử lý trường hợp không được cấp đầy đủ.

**Audience** giới hạn token dành cho Resource Server nào. Ví dụ một access token có **aud=reports-api** không nên được Orders API chấp nhận dù được cùng issuer ký. Nếu AS hỗ trợ **Resource Indicators for OAuth 2.0 (RFC 8707)**, client có thể chỉ rõ Resource Server đích trong yêu cầu theo hợp đồng.

Các claims trong JWT access token có thể bao gồm:

~~~json
{
  "iss": "https://identity.example.test",
  "sub": "user-42",
  "aud": "orders-api",
  "client_id": "dashboard-client",
  "scope": "orders:read",
  "iat": 1730000000,
  "nbf": 1730000000,
  "exp": 1730000900,
  "jti": "example-jti-42"
}
~~~

Đây là **payload giả**. Định nghĩa claims cụ thể phụ thuộc JWT access token profile và issuer. **sub** không luôn là End-User trong client_credentials; claims như role và tenant thường do hệ thống định nghĩa riêng.

AS cần kiểm tra trước khi ký/phát hành:

- **Issuer** và **key** được kiểm soát đúng.
- **Audience** tương ứng tài nguyên đích và không vô tình quá rộng.
- **Scope** đã thực sự được cấp; không sao chép nguyên scope mà client tự khai.
- **Thời hạn** phù hợp với rủi ro và chính sách thu hồi.
- **Subject/client identity** được xác minh từ grant, không lấy tùy tiện từ request.
- **Claims tối thiểu**: tránh nhúng mật khẩu, secret hoặc dữ liệu cá nhân không cần thiết.

JWT ký số **không đồng nghĩa mã hóa payload**. Client và bên giữ token thường có thể đọc claims JWS. Nếu muốn tránh bộc lộ dữ liệu, cần giảm claims hoặc chọn kiến trúc token phù hợp thay vì nghĩ ký số là giữ bí mật.

## 10. Token endpoint phải trả lỗi thế nào?

Không phải mọi request đến token endpoint đều được cấp token. Theo OAuth 2.0, server có các mã lỗi dạng JSON khi yêu cầu không hợp lệ hoặc không được cho phép.

Ví dụ:

~~~http
HTTP/1.1 400 Bad Request
Content-Type: application/json
Cache-Control: no-store
Pragma: no-cache

{
  "error": "invalid_grant"
}
~~~

Một số lỗi phổ biến:

| Mã lỗi | Ý nghĩa thường gặp | Ví dụ |
| --- | --- | --- |
| **invalid_request** | Request thiếu tham số bắt buộc, trùng hoặc sai định dạng theo giao thức. | Thiếu grant_type hoặc tham số bị lặp không hợp lệ. |
| **invalid_client** | Xác thực client thất bại hoặc không thể nhận diện client như yêu cầu. | Secret, assertion, chứng chỉ không hợp lệ. |
| **invalid_grant** | Grant không hợp lệ, hết hạn, thu hồi, không khớp client hoặc quy tắc khác. | Code bị dùng lại, code_verifier sai, RT đã vô hiệu. |
| **unauthorized_client** | Client không được phép dùng grant đã yêu cầu. | Public client không được cấu hình cho grant đó. |
| **unsupported_grant_type** | AS không hỗ trợ loại grant được yêu cầu. | Gửi một grant ngoài cấu hình. |
| **invalid_scope** | Scope yêu cầu không hợp lệ, không được chấp nhận hoặc vượt phạm vi theo chính sách. | Client đòi scope quản trị khi không được cấp. |

Một số lỗi xác thực client có thể dùng **HTTP 401** kèm **WWW-Authenticate** theo phương thức xác thực áp dụng. Không nên gán mọi lỗi token endpoint thành HTTP 401; phải theo quy tắc giao thức và profile.

**Bảo vệ thông tin lỗi:** Response nên đủ giúp client xử lý đúng nhưng không tiết lộ secret, refresh token, chi tiết nhạy cảm về người dùng hoặc nội bộ AS. Không đưa token thật vào trường error_description, log hoặc URL.

### Client nên phản ứng ra sao?

- Với **invalid_grant** do code/RT không còn dùng được: dừng dùng giá trị đó, xóa trạng thái không hợp lệ và khởi động lại luồng phù hợp nếu cần.
- Với **invalid_client**: kiểm cấu hình/secret/cert/client assertion; không lặp vô hạn cùng credential lỗi.
- Với **invalid_scope**: xin lại phạm vi đúng hợp đồng; không tự mở rộng quyền.
- Với lỗi mạng tạm thời: retry có giới hạn, backoff và quản lý request đồng thời; đặc biệt cẩn thận với RT rotation hoặc code sử dụng một lần.
- Không thay một grant thất bại bằng cách gửi mật khẩu người dùng lên token endpoint ngoài thiết kế.

## 11. Một thiết kế token endpoint an toàn cần kiểm tra gì?

Mã giả dưới đây mô tả luồng tổng quát ở **Authorization Server**, không phải code triển khai production hoặc một thứ tự thực thi bắt buộc:

~~~text
function handleTokenRequest(request):
    require request.method == POST
    require protectedTransportIsTLS(request)
    parameters = parseFormUrlEncodedStrictly(request)

    grantType = parameters.get("grant_type")
    client = resolveRegisteredClient(parameters, request.authentication)

    if grantType not in supportedGrantTypes:
        return oauthError("unsupported_grant_type")

    if not clientIsAllowedForGrant(client, grantType):
        return oauthError("unauthorized_client")

    if client.isConfidential:
        require validateRegisteredClientAuthentication(client, request)
    else:
        require applyPublicClientGrantProtections(client, parameters, request)

    grantContext = validateGrantByType(
        grantType,
        parameters,
        client,
        redirectUriAndPkceWhenRequired = true,
        refreshBindingAndRotationWhenRequired = true
    )
    if not grantContext.valid:
        return oauthError("invalid_grant")

    authorizedScope = determineAllowedScopes(
        client,
        grantContext,
        requestedScopes = parameters.scope
    )
    resourceAudience = determineAuthorizedAudience(
        client,
        grantContext,
        parameters.resource
    )

    if not policyPermitsIssuance(client, grantContext, authorizedScope):
        return appropriateOAuthError()

    accessToken = issueTokenAtomically(
        subject = grantContext.subjectAccordingToGrant,
        client = client,
        audience = resourceAudience,
        scope = authorizedScope,
        lifetime = chooseLifetimeByPolicy(),
        senderBinding = grantContext.senderBinding
    )

    optionalRefreshToken = maybeIssueOrRotateRefreshToken(
        client,
        grantType,
        grantContext,
        policy
    )

    return oauthTokenResponse(
        accessToken,
        optionalRefreshToken,
        noStoreHeaders = true
    )
~~~

Một triển khai thực tế phải thiết kế xử lý lỗi và thứ tự xác minh sao cho **không lộ thông tin khách hàng/credential**, chống race condition ở code sử dụng một lần hoặc refresh token rotation, bảo đảm ghi trạng thái cấp phát đúng khi trả response lỗi.

**Không nên cho phép client chọn issuer, thuật toán ký, khóa riêng, chủ thể sub hoặc audience bất kỳ chỉ bằng các tham số tự khai.** AS quyết định dựa trên dữ liệu đã xác minh và chính sách.

### Kiểm tra đầu vào và chống lạm dụng

- Giới hạn phương thức, content type, kích thước request và số lượng tham số; xử lý tham số trùng theo quy tắc nghiêm ngặt.
- Áp rate limiting, giám sát brute force và bảo vệ token endpoint trước tải bất thường.
- Xác minh client authentication theo **phương thức đã đăng ký**; khóa riêng/secret được lưu và xoay vòng an toàn.
- Không ghi nguyên văn body chứa **code**, **refresh token**, **client_secret** hoặc client assertion vào access log.
- Dùng TLS đúng cấu hình, không chuyển credential qua HTTP không an toàn.
- Thiết kế khả năng thay khóa ký/JWKS và lịch phát hành token mới có thể kiểm chứng.
- Thiết kế fail-safe khi kho grant, trạng thái refresh token hoặc chính sách không khả dụng.

## 12. Authorization code và refresh token là credential nhạy cảm

Hai grant có tính chất khác nhau nhưng đều cần chống sử dụng sai.

**Authorization code** thường có thời hạn rất ngắn, gắn với một client và redirect URI, chỉ được đổi **một lần**. Khi bị đánh cắp, PKCE giúp ngăn một bên không có code_verifier đổi code tại token endpoint. Tuy nhiên, PKCE không thay toàn bộ chống CSRF, bảo vệ redirect URI và kiểm client.

**Refresh token** có thể dùng để xin nhiều access token mới trong vòng đời được phép. Nó cần hạn tuyệt đối hoặc hạn không hoạt động theo chính sách, ràng buộc client, bảo vệ nơi lưu trữ, rotation/sender-constraining phù hợp và khả năng thu hồi.

### Đồng thời và refresh token rotation

Giả sử hai request refresh cùng dùng **RT-1**:

~~~text
Lần đầu:
    POST /token, grant_type=refresh_token, refresh_token=RT-1
    -> thành công: AT-2, RT-2
    -> RT-1 bị vô hiệu

Lần sau:
    POST /token, grant_type=refresh_token, refresh_token=RT-1
    -> RT-1 không còn hợp lệ; AS từ chối và có thể xử lý reuse
~~~

Client nên đồng bộ refresh theo cơ chế **single-flight** để tránh nhiều request cùng dùng một RT. AS nên có thao tác cấp phát và vô hiệu RT cũ **nhất quán/atomic**; quy tắc phát hiện reuse cần xét cả khả năng request trùng do sự cố mạng và nguy cơ bị đánh cắp.

Đổi RT-1 thành RT-2 **không tự thu hồi mọi access token đã cấp**. Access token có TTL và cơ chế kiểm tra/thu hồi riêng, đặc biệt khi Resource Server xác minh JWT ngoại tuyến.

## 13. Token endpoint có nên nằm trong trình duyệt không?

Câu trả lời phụ thuộc loại client, mô hình triển khai và CORS/policy của AS.

- **Backend/confidential client** thường gửi yêu cầu token từ phía server và giữ client credential, access/refresh token trong môi trường kiểm soát; trình duyệt quản lý phiên qua cookie an toàn nếu sử dụng BFF.
- **Public SPA** có thể tham gia luồng Authorization Code + PKCE và gọi token endpoint khi AS hỗ trợ và cho phép theo cấu hình CORS/phạm vi được công bố. Không bao giờ nhúng client secret thực sự vào JavaScript gửi cho mọi người dùng.
- **Native/mobile app** thường dùng Authorization Code + PKCE với trình duyệt hệ thống theo hướng dẫn OAuth native apps; lưu token bằng cơ chế an toàn của hệ điều hành khi phù hợp.
- **Service-to-service** thường dùng client credentials và gọi token endpoint trực tiếp bằng phương thức xác thực client đăng ký.

**CORS không phải cơ chế xác thực.** Việc trình duyệt có thể gọi endpoint hay không không chứng minh client đáng tin. Bảo mật thực sự đến từ grant, client binding/authentication, chính sách cấp quyền, token protection và kiểm chứng tại API.

Một token endpoint nội bộ có thể không cần cho browser truy cập; nếu thiết kế yêu cầu browser gọi trực tiếp, AS phải chủ động hỗ trợ và cấu hình an toàn, không bật CORS quá rộng chỉ để bỏ qua lỗi frontend.

## 14. Token endpoint, issuer và xác minh ở Resource Server

Sau khi token được cấp, Resource Server phải tiếp tục xác minh token đúng mục đích:

| Claim/thông tin | AS phải quyết định khi phát hành | RS phải kiểm khi sử dụng |
| --- | --- | --- |
| **iss** | Issuer đúng, khóa ký được kiểm soát. | Issuer nằm trong tập nguồn đáng tin. |
| **aud** | Token dành cho API/resource đích phù hợp. | API hiện tại thực sự nằm trong audience chấp nhận. |
| **sub** | Chủ thể được xác định từ grant/ủy quyền. | Diễn giải đúng loại principal; không tự suy token client là user. |
| **scope** | Chỉ cấp phạm vi đã được cho phép. | Scope endpoint yêu cầu có mặt theo phép so chính xác. |
| **exp, nbf, iat** | Thời gian được chọn theo chính sách. | Token còn hiệu lực, xử lý sai lệch đồng hồ hợp lý. |
| **jti/trạng thái** | Có thể hỗ trợ tracking/revocation nếu thiết kế. | Kiểm trạng thái/thu hồi khi profile hoặc mức rủi ro yêu cầu. |
| **sender binding** | Gắn token với khóa/chứng chỉ client khi áp dụng. | Kiểm bằng chứng sở hữu ở request theo profile. |

Một access token hợp lệ có **scope orders:read** vẫn chưa được phép đọc mọi đơn hàng. Resource Server cần kiểm **permission/role theo tenant, quyền sở hữu và điều kiện nghiệp vụ hiện hành**.

Nếu JWT được xác minh offline, việc rút role hoặc khóa tài khoản tại AS không tự làm JWT thay đổi. Nếu yêu cầu thu hồi nhanh, RS có thể cần kiểm trạng thái principal, introspection, danh sách thu hồi hoặc chính sách đồng bộ; token ngắn hạn giúp thu hẹp cửa sổ chấp nhận quyền cũ nhưng không bảo đảm chặn ngay.

## 15. Các kiểu tấn công liên quan token endpoint

| Rủi ro | Cách thất bại thường gặp | Biện pháp chính |
| --- | --- | --- |
| **Authorization code interception** | Kẻ tấn công lấy code trên đường redirect và cố đổi. | PKCE, redirect URI chặt, code một lần, bảo vệ luồng. |
| **Client impersonation** | AS tin client_id hoặc secret nhúng vào public app như chứng cứ mạnh. | Xác thực confidential client, PKCE/binding cho public client và cấu hình đăng ký. |
| **Token endpoint phishing** | Client gửi refresh token/secret tới URL do kẻ tấn công kiểm soát. | Chỉ tin issuer và metadata/endpoint được xác minh; TLS. |
| **Refresh token theft/replay** | Bản sao RT được dùng xin AT mới. | Lưu an toàn, rotation hoặc sender-constraining, thu hồi và phát hiện reuse. |
| **Over-privilege** | AS cấp scope/audience rộng theo yêu cầu client không được kiểm. | Allowlist theo client, policy, resource đích và quyền tối thiểu. |
| **Grant/code replay** | Code dùng lại nhưng AS vẫn phát token. | Sử dụng một lần, TTL ngắn và trạng thái tiêu thụ atomic. |
| **Credential leakage** | Body/header hoặc response token bị ghi log/cache. | Redaction, no-store, phân quyền log và quản trị secret. |
| **Token substitution** | API nhận token sai audience/loại vì cùng issuer. | RS kiểm token profile, audience, scope và sender proof. |
| **AS/RS policy drift** | AS vừa cấp token nhưng RS vẫn dùng role cũ hoặc bỏ kiểm quyền. | Hợp đồng rõ, đồng bộ chính sách, kiểm quyền theo tài nguyên và SLA thu hồi. |

Việc có **JWT signature** không tự giải quyết đánh cắp bearer token, grants sử dụng lại hoặc cấp scope quá rộng. Việc dùng **opaque access token** cũng không tự bảo đảm policy đúng. Phải bảo vệ cả quá trình phát hành lẫn kiểm tra sau cấp.

## 16. Kịch bản hoàn chỉnh: cấp token cho Dashboard và Orders API

Giả sử một nhân viên truy cập dashboard quản lý đơn hàng của **tenant-blue**.

**Điều kiện ban đầu:**

~~~text
Client: dashboard-public
Authorization Server: identity.example.test
Resource Server: orders-api
Requested scope: "orders:read orders:update"
Redirect URI đã đăng ký: https://app.example.test/callback
Client sử dụng Authorization Code + PKCE S256
~~~

Quá trình:

1. Dashboard tạo **code_verifier**, từ đó tạo **code_challenge** và đưa người dùng đến authorization endpoint đúng issuer.
2. AS xác thực người dùng theo chính sách và cấp **authorization code** cho client nếu được phép.
3. Dashboard nhận code qua redirect URI đã đăng ký, kiểm **state**, gửi code cùng code_verifier đến token endpoint.
4. AS kiểm code một lần, PKCE, client và sự ủy quyền, rồi quyết định chỉ cấp **orders:read** nếu người dùng/client không có quyền phạm vi ghi.
5. Dashboard xử lý **scope thực sự được cấp**, lưu access token bằng mô hình bảo vệ phù hợp.
6. Orders API nhận token, kiểm issuer/audience/hiệu lực và scope **orders:read**, sau đó kiểm nhân viên có được đọc **đơn hàng thuộc tenant-blue** hay không.
7. Nếu người dùng thử cập nhật đơn hàng, API từ chối do token không có **orders:update**, dù người dùng đã đăng nhập và token có chữ ký hợp lệ.
8. Khi AT hết hạn, dashboard chỉ có thể refresh nếu AS đã cấp RT và điều kiện RT vẫn hợp lệ; nếu không, client phải bắt đầu lại luồng phù hợp.

Điểm mấu chốt: **token endpoint quyết định phát hành access token với phạm vi nào; Resource Server quyết định yêu cầu cụ thể trên tài nguyên có được phép hay không.**

## 17. Checklist kiểm thử token endpoint

Nhóm triển khai nên có cả **positive tests** lẫn **negative tests**:

| Tình huống kiểm thử | Kết quả mong đợi |
| --- | --- |
| Authorization code hợp lệ, PKCE đúng, client đúng. | Token endpoint có thể phát token theo policy. |
| Authorization code đã được đổi một lần, gửi lại. | Từ chối, không phát token lần thứ hai. |
| Code_verifier sai hoặc thiếu khi được yêu cầu. | Từ chối grant. |
| Code thuộc client A nhưng client B đến đổi. | Từ chối theo ràng buộc client. |
| Redirect URI không phù hợp với authorization request. | Từ chối. |
| Confidential client không có credential hợp lệ. | Từ chối xác thực client. |
| Public client gửi client_secret cố định trong app. | Không coi secret nhúng như bằng chứng xác thực confidential client. |
| Client yêu cầu scope ngoài allowlist. | Không cấp vượt quyền; trả kết quả theo policy/chuẩn. |
| Client credentials xin token theo quyền user tùy ý. | Từ chối hoặc chỉ phát token theo principal và policy thực sự hợp lệ. |
| RT đã bị thu hồi/hết hạn. | Từ chối refresh, thường lỗi invalid_grant. |
| RT cũ được dùng sau rotation. | Từ chối và xử lý reuse theo chính sách. |
| Request đến token endpoint sai phương thức/content type. | Từ chối request không đúng hợp đồng. |
| AS hoặc kho trạng thái grant bị lỗi. | Không tự phát token khi thiếu kiểm tra bắt buộc. |
| API nhận access token sai audience. | Resource Server từ chối; không phải token endpoint cấp quyền cho API sai. |
| Response token bị cache/log. | Các lớp bảo vệ phải không lưu dữ liệu nhạy cảm trái chính sách. |

Nên đo thêm độ trễ cấp token, tải đột biến, tỷ lệ invalid_grant, số lỗi client authentication, phản ứng với refresh reuse và khả năng phục hồi khi AS có sự cố. Giám sát không được trở thành nguồn rò rỉ token.

## 18. Bài tập vận dụng

**Tình huống A.** Một SPA đã đăng ký Authorization Code + PKCE, nhận được authorization code nhưng gửi code thiếu code_verifier.

**Phân tích:** Nếu code gắn với PKCE, token endpoint phải từ chối vì không thể kiểm chứng bên đổi code sở hữu verifier hợp lệ. Không được cho qua chỉ vì có client_id hoặc token endpoint cùng domain.

**Tình huống B.** Một batch worker gọi token endpoint bằng client_credentials, yêu cầu scope **payments:refund** trong khi client chỉ được đăng ký **reports:read**.

**Phân tích:** AS phải không phát access token với payments:refund ngoài phạm vi cho phép. Client cần scope đúng mục đích; không thể coi client credentials như quyền quản trị tuyệt đối.

**Tình huống C.** Dashboard nhận access token với scope **orders:read** dù đã yêu cầu cả **orders:update**.

**Phân tích:** Đây có thể là quyết định giới hạn quyền của AS. Client phải nhận biết scope thực sự được cấp; không được âm thầm thực hiện thao tác cập nhật vì nó từng yêu cầu scope đó.

**Tình huống D.** Refresh token đã bị thu hồi, nhưng JWT access token trước đó còn hạn trong 10 phút.

**Phân tích:** Token endpoint không còn cấp token mới bằng refresh token ấy. Tuy nhiên, Resource Server xác minh JWT ngoại tuyến có thể vẫn chấp nhận access token cũ nếu chưa có cơ chế biết thu hồi. Cần thiết kế chính sách thu hồi và quyền hiện hành riêng.

**Tình huống E.** Gateway nhận ID token OIDC với audience là dashboard-client và chuyển nó tới Orders API.

**Phân tích:** API phải từ chối nếu yêu cầu access token đúng audience/orders-api. ID token không trở thành access token chỉ vì cùng issuer hoặc chứa subject.

## Kết luận

**Token endpoint là ranh giới phát hành token của Authorization Server**: nó nhận những grant hợp lệ qua giao thức được bảo vệ, kiểm tra client và sự ủy quyền, rồi phát hành access token với **scope, audience, chủ thể và thời hạn** theo chính sách. Với một số luồng, nó còn cấp hoặc xoay vòng refresh token; trong OIDC nó có thể trả thêm ID token theo quy tắc riêng.

Triển khai an toàn cần **Authorization Code + PKCE**, xác thực client theo loại client, code một lần, TLS, hạn chế scope/audience, bảo vệ refresh token và response, kiểm lỗi nghiêm ngặt và giám sát không lộ credential. Sau khi token được cấp, **Resource Server vẫn phải tự xác minh token và phân quyền theo tài nguyên hiện hành**. Tách đúng vai trò của hai phía giúp tránh nhầm xác thực với phân quyền và ngăn token trở thành bằng chứng truy cập vĩnh viễn.

### Tài liệu tham khảo

- [RFC 6749 — The OAuth 2.0 Authorization Framework, Section 3.2: Token Endpoint](https://www.rfc-editor.org/rfc/rfc6749#section-3.2)
- [RFC 6749 — Section 4.1.3: Access Token Request](https://www.rfc-editor.org/rfc/rfc6749#section-4.1.3)
- [RFC 6749 — Section 5: Issuing an Access Token](https://www.rfc-editor.org/rfc/rfc6749#section-5)
- [RFC 7636 — Proof Key for Code Exchange by OAuth Public Clients (PKCE)](https://www.rfc-editor.org/rfc/rfc7636)
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009)
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662)
- [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414)
- [RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens](https://www.rfc-editor.org/rfc/rfc8705)
- [RFC 8707 — Resource Indicators for OAuth 2.0](https://www.rfc-editor.org/rfc/rfc8707)
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068)
- [RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449)
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700)
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html)
