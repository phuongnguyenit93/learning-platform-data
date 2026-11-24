# Vai trò authorization server

## Mục tiêu học tập

Sau bài học này, bạn có thể:

- Nêu đúng vai trò của **Authorization Server (AS)** trong bốn vai trò nền tảng của OAuth 2.0: **Resource Owner**, **Client**, **Authorization Server** và **Resource Server**.
- Phân biệt trách nhiệm **phát hành và quản lý token** của AS với trách nhiệm **kiểm tra token và quyết định truy cập tài nguyên** của Resource Server.
- Mô tả cách AS xác minh client, đánh giá sự ủy quyền, kiểm **grant**, xác định **scope/audience**, phát hành access token và quản lý refresh token.
- Hiểu các điểm cuối của AS như **authorization endpoint**, **token endpoint**, **revocation**, **introspection**, **metadata/JWKS** cùng các ranh giới tin cậy tương ứng.
- Phân biệt **OAuth Authorization Server**, **Identity Provider (IdP)** và **OpenID Provider (OP)** trong OIDC; hiểu vì sao **ID token không thay access token**.
- Áp dụng nguyên tắc an toàn với **Authorization Code + PKCE**, client authentication, token lifetime, key rotation, refresh token rotation, sender-constraining và kiểm soát cấp quyền tối thiểu.

## 1. Authorization Server đứng ở đâu trong OAuth 2.0?

OAuth 2.0 là một **khung ủy quyền**: một client được cấp quyền truy cập có giới hạn vào tài nguyên được bảo vệ, thông qua các credential và quy trình do một Authorization Server kiểm soát.

Bốn vai trò lõi:

| Vai trò | Câu hỏi nó giải quyết | Ví dụ |
| --- | --- | --- |
| **Resource Owner** | Ai sở hữu hoặc có khả năng cho phép truy cập tài nguyên theo mô hình OAuth? | Một người dùng có dữ liệu đơn hàng; hoặc một thực thể tổ chức được đại diện theo chính sách. |
| **Client** | Ứng dụng nào yêu cầu được truy cập tài nguyên? | Web dashboard, mobile app, batch worker. |
| **Authorization Server (AS)** | Ai xử lý sự ủy quyền, xác minh grant/client, quyết định phát hành token và quản lý vòng đời token? | Dịch vụ identity/authorization tại identity.example.test. |
| **Resource Server (RS)** | API nào chứa dữ liệu cần bảo vệ và kiểm xem request có được phép thực hiện hay không? | Orders API, Payments API. |

Sơ đồ minh họa:

~~~mermaid
flowchart LR
    RO["Resource Owner / End-User"] -->|"Cấp sự ủy quyền khi luồng yêu cầu"| AS["Authorization Server"]
    C["OAuth Client"] -->|"Yêu cầu ủy quyền / đổi grant"| AS
    AS -->|"Cấp access token (và RT khi phù hợp)"| C
    C -->|"Access token + request"| RS["Resource Server"]
    RS -->|"Kiểm token / trạng thái (khi cần)"| AS
    RS -->|"Chỉ trả tài nguyên được phép"| C
~~~

Các mũi tên là **mô hình trách nhiệm**, không có nghĩa mọi request API phải gọi AS trực tiếp. Với JWT được ký và RS đã có khóa tin cậy, RS có thể xác minh nhiều thuộc tính **ngoại tuyến**. Với opaque token, RS thường cần tra cứu/introspection theo hợp đồng.

**Tóm tắt một câu:** Authorization Server **phát hành và quản lý sự ủy quyền được thể hiện bằng token**, còn Resource Server **thực thi kiểm soát truy cập tài nguyên** khi nhận yêu cầu.

## 2. AS giải quyết vấn đề gì?

Trước khi có OAuth, một ứng dụng bên thứ ba có thể bị yêu cầu giữ mật khẩu người dùng để gọi API thay người đó. Cách này làm lộ credential gốc, khó giới hạn hành động được phép và khó thu hồi quyền cho từng ứng dụng.

OAuth thay đổi ranh giới tin cậy:

1. **Client không cần nhận mật khẩu người dùng** trong luồng Authorization Code chuẩn.
2. AS xác thực người dùng khi luồng và chính sách yêu cầu, rồi xử lý sự ủy quyền.
3. Client nhận **access token** có phạm vi, đối tượng nhận và thời hạn được giới hạn.
4. RS nhận access token và thực thi giới hạn truy cập.
5. Sự ủy quyền/refresh token có thể được quản lý, hết hạn hoặc thu hồi mà không cần đổi mật khẩu người dùng.

AS là nơi tập trung các chính sách **phát hành token**, chẳng hạn:

- Client nào đã đăng ký và được dùng grant nào?
- Người dùng hoặc resource owner đã ủy quyền những phạm vi nào?
- Client được nhận scope và audience nào?
- Token dành cho resource nào, hiệu lực đến bao giờ?
- Có cấp refresh token không? Với ràng buộc nào?
- Có cần xác thực lại người dùng, step-up hay kiểm điều kiện rủi ro không?
- Khi grant/phiên bị thu hồi, token mới có còn được cấp không?

Đồng thời, AS **không mặc nhiên biết** mọi điều kiện nghiệp vụ trong Orders API, ví dụ đơn hàng đang bị khóa, người tạo không được tự duyệt, hoặc tenant của tài nguyên có thay đổi.

## 3. Authentication và authorization ở AS khác nhau thế nào?

Trong một luồng có người dùng, AS có thể cần xác minh danh tính người đó bằng session đăng nhập, mật khẩu, passkey, MFA hoặc một IdP liên kết. Đó là **authentication**: xác định và kiểm chứng chủ thể.

Sau đó, AS đánh giá **authorization**: client có được cấp quyền theo yêu cầu hay không, với scope, resource và điều kiện nào.

Ví dụ:

~~~text
Người dùng: nhân viên A
Client: dashboard-web
Requested scope: "orders:read payments:refund"
AS policy:
    dashboard-web được phép yêu cầu orders:read
    dashboard-web không được phép nhận payments:refund
Grant result:
    cấp access token chỉ với "orders:read", hoặc từ chối theo policy
~~~

Việc người dùng xác thực thành công **không có nghĩa AS phải cấp mọi scope mà client xin**. Việc người dùng nhấn đồng ý (**consent**) cũng không tự mở rộng quyền vượt chính sách của tổ chức.

### Không phải luồng nào cũng có người dùng đang đăng nhập

Với **client_credentials**, client xin token theo quyền của chính ứng dụng hoặc workload:

~~~text
Client: nightly-report-worker
Grant: client_credentials
Requested resource: reports-api
Requested scope: "reports:generate"
End-User tương tác: không bắt buộc có
~~~

AS lúc này xác minh client và chính sách cấp quyền máy–máy; không nên tự dựng một người dùng giả chỉ vì một vài token profile có claim **sub**.

**AS có thể làm việc với cả ủy quyền có End-User và ủy quyền của client**, tùy grant. OAuth 2.0 không đồng nghĩa với “đăng nhập bằng OAuth” trong mọi tình huống.

## 4. Phân biệt Authorization Server, Identity Provider và OpenID Provider

Ba nhãn này thường cùng xuất hiện trong một sản phẩm IAM nhưng **không đồng nghĩa hoàn toàn**.

| Khái niệm | Chức năng cốt lõi | Token/thông tin thường liên quan |
| --- | --- | --- |
| **OAuth 2.0 Authorization Server** | Xử lý grant và phát hành token phục vụ truy cập tài nguyên. | Access token, có thể có refresh token. |
| **Identity Provider (IdP)** | Dịch vụ xác thực/khẳng định danh tính theo một giao thức hoặc hệ thống định danh. | Phiên xác thực, assertions hoặc claims danh tính. |
| **OpenID Provider (OP) trong OIDC** | Cung cấp dịch vụ xác thực OIDC cho relying party; đồng thời có vai trò OAuth Authorization Server theo OIDC. | **ID token**, UserInfo và các token OAuth liên quan. |
| **Resource Server** | Bảo vệ tài nguyên API và thực thi quyền. | Kiểm access token, scope, audience và policy nghiệp vụ. |

Một sản phẩm có thể vừa làm AS vừa làm IdP/OP. Nhưng **OAuth AS không bắt buộc là OIDC OP**, và sự tồn tại của access token không tự chứng minh người dùng đã trải qua một sự kiện xác thực theo yêu cầu của client.

### Access token và ID token có đối tượng nhận khác nhau

Trong OIDC:

- **ID token** mô tả thông tin sự kiện xác thực End-User cho **client/relying party**. Client xác minh token theo quy tắc OIDC, gồm issuer, audience, thời gian và các ràng buộc khác.
- **Access token** được cấp để client gọi **Resource Server**. RS cần kiểm audience dành cho API, phạm vi và chính sách của tài nguyên.
- **Refresh token**, nếu cấp, được dùng ở **token endpoint** của AS để xin token mới; không gửi RT tới Resource Server.

Ví dụ một ID token có **aud=dashboard-web** không được dùng thay access token để gọi Orders API yêu cầu **aud=orders-api**.

## 5. Hai điểm cuối lõi của Authorization Server

AS thường công bố hai điểm cuối OAuth quan trọng nhất:

### 5.1 Authorization endpoint

**Authorization endpoint** tham gia vào luồng tương tác với user agent để xin sự ủy quyền. Trong luồng **Authorization Code**, client chuyển hướng trình duyệt đến endpoint của AS.

Request minh họa:

~~~http
GET /oauth2/authorize?response_type=code&client_id=dashboard-web&redirect_uri=https%3A%2F%2Fapp.example.test%2Fcallback&scope=orders%3Aread&state=EXAMPLE_RANDOM_STATE&code_challenge=EXAMPLE_CHALLENGE&code_challenge_method=S256 HTTP/1.1
Host: identity.example.test
~~~

Ví dụ rút gọn này dùng placeholder; **state**, **code_challenge** và giá trị ngẫu nhiên thật cần tạo theo giao thức chứ không cố định.

Tại đây AS có thể:

1. Nhận diện client và kiểm thông số request.
2. Xác minh **redirect_uri** với các URI đã đăng ký theo quy tắc áp dụng.
3. Kiểm client/grant/scope mà client được yêu cầu.
4. Xác thực resource owner khi luồng và chính sách yêu cầu.
5. Hiển thị consent hoặc áp sự ủy quyền hiện hành nếu phù hợp.
6. Phát hành **authorization code** ràng buộc với client, redirect URI, PKCE và sự ủy quyền.
7. Chuyển user agent về callback hợp lệ của client cùng kết quả phù hợp.

AS không nên chuyển authorization response chứa mã nhạy cảm sang một redirect URI chưa được xác minh. Không được biến redirect_uri hoặc tham số tiếp theo thành **open redirect**.

### 5.2 Token endpoint

**Token endpoint** xử lý việc client đổi một grant hợp lệ thành token, thông thường qua **HTTP POST** với **application/x-www-form-urlencoded** và **TLS**.

~~~http
POST /oauth2/token HTTP/1.1
Host: identity.example.test
Content-Type: application/x-www-form-urlencoded

grant_type=authorization_code&client_id=dashboard-web&code=EXAMPLE_CODE&redirect_uri=https%3A%2F%2Fapp.example.test%2Fcallback&code_verifier=EXAMPLE_VALID_VERIFIER
~~~

Request minh họa cho public client, lược bỏ chi tiết khác theo profile. Nếu client là **confidential client**, cần thêm xác thực client theo phương thức đã đăng ký. Public client không được coi một client secret nhúng trong JavaScript/app mobile là bí mật đáng tin.

Ở token endpoint, AS phải kiểm:

- Grant được AS phát hành và còn hiệu lực.
- Grant đúng client và đúng luồng đã đăng ký.
- Authorization code chưa bị dùng, chưa hết hạn và đúng redirect URI/ràng buộc.
- **PKCE code_verifier** khớp code_challenge khi yêu cầu.
- Xác thực client hoặc bằng chứng sender binding theo profile.
- Phạm vi ủy quyền, audience/resource đích và chính sách còn được cho phép.
- Token đầu ra có claims, TTL và loại token đúng hợp đồng.

Một client gửi đúng chuỗi **grant_type** không tự được cấp token. AS phải đánh giá **bằng chứng và sự ủy quyền** gắn với grant đó.

## 6. Luồng Authorization Code + PKCE: AS điều phối như thế nào?

Một luồng end-to-end:

~~~mermaid
sequenceDiagram
    participant U as End-User / Browser
    participant C as OAuth Client
    participant AS as Authorization Server
    participant RS as Orders API

    C->>C: Sinh state, PKCE code_verifier và code_challenge
    C->>U: Chuyển hướng tới authorization endpoint
    U->>AS: HTTPS GET /authorize
    AS->>AS: Kiểm client, redirect_uri, xác thực và consent/policy
    AS-->>U: Redirect về callback với authorization code và state
    U->>C: Code và state
    C->>C: Kiểm state, gắn code với phiên ban đầu
    C->>AS: HTTPS POST /token, code + verifier + client auth nếu cần
    AS->>AS: Kiểm code một lần, client, PKCE, redirect, grant/policy
    AS-->>C: Access token và RT/ID token nếu phù hợp
    C->>RS: HTTPS request + access token đúng audience
    RS->>RS: Kiểm token, scope, principal và quyền tài nguyên
    RS-->>C: Dữ liệu hoặc từ chối
~~~

### AS chịu trách nhiệm gì về authorization code?

Authorization code phải được ràng buộc với **client**, **redirect URI** và các điều kiện bảo mật của luồng. Code có thời hạn ngắn và **chỉ được đổi một lần**.

**PKCE (RFC 7636)** ràng buộc code với một **code_verifier** bí mật theo giao dịch; authorization request gửi **code_challenge**, token request gửi verifier để AS đối chiếu. PKCE giúp giảm nguy cơ kẻ tấn công chặn code rồi đổi code mà không có verifier.

**State** giúp client liên kết response với request gốc và chống các kiểu nhầm phiên/CSRF trong những mô hình áp dụng. Tùy profile, OIDC nonce và các cơ chế chống mix-up cũng có vai trò. **State, nonce và PKCE không thay thế nhau**.

Theo hướng dẫn OAuth 2.0 Security Best Current Practice, AS/client hiện đại cần hỗ trợ áp dụng PKCE phù hợp cả khi client có khả năng giữ secret, không mặc định “confidential client có secret thì không cần PKCE”.

### Một ví dụ phát hành có giới hạn

Giả sử người dùng yêu cầu đọc báo cáo và duyệt hoàn tiền:

~~~text
Client: dashboard-web
Requested scopes: "reports:read payments:refund"
Client allowlist: "reports:read"
User authorization/policy: chỉ cho đọc báo cáo

AS result:
    access token audience = reports-api
    granted scope = "reports:read"
~~~

AS có thể cấp một tập scope nhỏ hơn yêu cầu hoặc từ chối theo quy tắc giao thức và chính sách. Client phải dựa vào **scope thực sự được cấp**, không dùng danh sách đã xin để tự cấp quyền.

## 7. Grant type: AS kiểm bằng chứng khác nhau theo từng luồng

| Grant | Ai thường dùng? | AS phải kiểm điều gì? | Có người dùng tương tác mỗi request? |
| --- | --- | --- | --- |
| **authorization_code** | Ứng dụng web, SPA, mobile theo luồng có người dùng. | Code, client, redirect URI, PKCE, sự ủy quyền và client authentication nếu cần. | Có tương tác trong giai đoạn authorization, không bắt buộc ở token request. |
| **refresh_token** | Client có RT còn hiệu lực. | RT, client binding, trạng thái, sự ủy quyền còn hiệu lực, rotation và scope. | Không nhất thiết. |
| **client_credentials** | Backend/workload có quyền của chính client. | Xác thực client, grant allowlist, scope/resource/policy. | Không. |
| **Extension grant** | Các profile như device authorization hoặc token exchange khi AS hỗ trợ. | Theo tiêu chuẩn/profile extension và client policy. | Tùy extension. |

Không nên tự thêm grant mới bằng cách kiểm một tham số tự khai rồi cấp token; một grant là **hợp đồng giao thức và bảo mật**.

### 7.1 Authorization Code

AS phát code sau khi giải quyết tương tác ủy quyền và cấp access token khi code được đổi đúng. **Client không được tự chọn subject, scope hay audience cuối cùng** chỉ bằng cách thêm tham số không được phép vào token request.

### 7.2 Refresh Token

AS tiếp nhận RT tại token endpoint và đánh giá client/grant/policy trước khi cấp AT mới. **Refresh token không dùng tại RS**, và việc AT hết hạn không có nghĩa RT cũng hết hạn.

Với **refresh token rotation**, AS cấp RT mới và vô hiệu RT cũ theo chính sách. Nếu phát hiện một RT đã bị vô hiệu được dùng lại, AS có thể coi đây là tín hiệu rò rỉ và xử lý token family/phiên. Public client nhận RT cần bảo vệ theo OAuth 2.0 Security BCP bằng **rotation hoặc sender-constraining**.

### 7.3 Client Credentials

AS cấp token theo **quyền của client/workload**, không mặc định theo quyền của một End-User.

~~~http
POST /oauth2/token HTTP/1.1
Host: identity.example.test
Authorization: Basic EXAMPLE_CLIENT_AUTH
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials&scope=reports%3Agenerate
~~~

Credential là placeholder. Basic dùng biểu diễn Base64 cho thông tin xác thực client, **không phải mã hóa bí mật**; TLS bắt buộc. AS phải xác thực confidential client bằng phương thức đăng ký như client_secret_basic, private_key_jwt hoặc mTLS tùy profile.

Theo RFC 6749, AS **SHOULD NOT** cấp refresh token cho client_credentials. Không tạo RT cho các workload chỉ để tiện vận hành khi việc xin access token mới bằng client authentication là đủ.

### 7.4 Grant cũ không nên khuyến khích

**Resource Owner Password Credentials grant** cho client trực tiếp nhận mật khẩu người dùng là mô hình cũ và không phù hợp với hướng dẫn bảo mật hiện đại; RFC 9700 yêu cầu không dùng grant này. Với ứng dụng người dùng, hãy ưu tiên các luồng được khuyến nghị như Authorization Code + PKCE.

## 8. AS cấp loại token nào?

### Access token

Access token là credential để client trình bày với Resource Server theo hợp đồng. AS có thể phát token dạng:

- **JWT**: mang claims được ký (hoặc xử lý theo profile), cho phép RS xác minh một số thuộc tính tại chỗ.
- **Opaque/reference token**: chuỗi không cần được RS tự giải mã; RS có thể hỏi AS qua introspection hoặc hệ thống xác minh đã cấu hình.
- **Sender-constrained token**: token gắn với khóa/chứng chỉ theo profile như DPoP hoặc mTLS certificate-bound token.

Định dạng token **không tự quyết định quyền**. JWT có scope quá rộng vẫn là một rủi ro; opaque token cũng có thể bị cấp quyền sai.

### Refresh token

RT là credential cấp lại token tại AS theo sự ủy quyền và chính sách. AS quyết định:

- Có cấp RT hay không cho client và grant?
- RT gắn với client/grant/phiên/issuer nào?
- Thời hạn tuyệt đối và inactivity timeout ra sao?
- Có rotation hoặc sender-constraining nào?
- Điều kiện nào khiến RT bị thu hồi hoặc không được đổi tiếp?
- Scope được phép xin lại có còn phù hợp không?

RT phải được bảo vệ như bí mật và chỉ truyền qua HTTPS tới **token endpoint đúng issuer**. Không đưa RT vào access token audience API hoặc dùng RT để gọi Orders API.

### ID token trong OIDC

Nếu AS còn đóng vai trò **OpenID Provider** và client dùng OIDC, response của các luồng thích hợp có thể có **ID token** mô tả sự kiện xác thực End-User.

**ID token dành cho client/relying party**; nó không tự là bearer access token của API. RS phải chấp nhận **đúng loại token** mà API được cấu hình để nhận.

## 9. Claims mà AS phải phát hành đúng

Ví dụ payload **JWT access token minh họa**:

~~~json
{
  "iss": "https://identity.example.test",
  "sub": "user-42",
  "aud": "orders-api",
  "client_id": "dashboard-web",
  "scope": "orders:read",
  "iat": 1730000000,
  "nbf": 1730000000,
  "exp": 1730000900,
  "jti": "example-token-id-42"
}
~~~

Đây là **payload giả, không phải JWT hoàn chỉnh**. Các claims và yêu cầu cụ thể phụ thuộc profile, ví dụ RFC 9068 cho JWT access token OAuth.

| Claim/thông tin | Trách nhiệm AS khi phát hành | Trách nhiệm RS khi nhận |
| --- | --- | --- |
| **iss** | Dùng định danh issuer đã cấu hình và khóa tin cậy phù hợp. | Chỉ tin issuer được cấu hình; không tin nguồn tùy ý do token tự khai. |
| **sub** | Xác định chủ thể theo grant/profile, không lấy từ user ID tự khai. | Hiểu subject theo issuer/profile; phân biệt user và service. |
| **aud** | Giới hạn token cho Resource Server/resource đích được phép. | Từ chối token không dành cho chính API. |
| **client_id** | Gắn client nhận sự ủy quyền khi profile áp dụng. | Có thể dùng để kiểm client được phép với hành động/API. |
| **scope** | Chỉ cấp scope đã được cho phép theo client và grant. | Kiểm scope chính xác; còn phải kiểm quyền tài nguyên. |
| **exp/nbf/iat** | Chọn thời hạn theo policy và đảm bảo claims hợp lý. | Kiểm mốc thời gian, clock skew trong giới hạn cho phép. |
| **jti** | Có thể hỗ trợ nhận diện/truy vết/thu hồi theo thiết kế. | Chỉ dùng cho revocation/replay policy nếu hệ thống định nghĩa cách kiểm. |
| **cnf hoặc binding metadata** | Ràng buộc sender-constrained token theo profile. | Kiểm bằng chứng khóa/chứng chỉ đúng loại token. |

**AS phát hành claims không có nghĩa RS được bỏ qua authorization**. Ví dụ token đúng chữ ký chứa scope **orders:write** vẫn không tự cho phép user sửa đơn hàng của tenant khác.

### Không sao chép claim do client tự khai

Một token endpoint không nên chấp nhận:

~~~text
POST /token
grant_type=client_credentials
sub=super-admin
scope=admin:all
aud=payments-api
~~~

rồi ký mọi trường client đưa vào. AS phải suy ra principal, scope, audience và những thuộc tính khác từ **grant hợp lệ, client registration và policy được tin cậy**.

## 10. Scope và audience: AS cấp quyền tối thiểu

**Scope** biểu thị phạm vi truy cập OAuth. **Audience** biểu thị đối tượng nhận token. AS cần giới hạn cả hai.

Ví dụ:

~~~text
Client: reporting-dashboard
Grant: authorization_code
Requested scope: "reports:read orders:write"
Requested resource: reports-api

AS policy:
  registered client only allowed reports:read on reports-api

Issued token:
  aud = reports-api
  scope = "reports:read"
~~~

Token này không nên được Orders API chấp nhận chỉ vì cùng issuer. Orders API phải kiểm audience của chính mình.

Nếu AS hỗ trợ **Resource Indicators for OAuth 2.0 (RFC 8707)**, client có thể chỉ rõ tài nguyên đích qua tham số resource theo hợp đồng. Việc AS sử dụng tham số đó không có nghĩa client được tùy ý chọn mọi API; AS vẫn phải áp policy và ràng buộc với client/grant.

### Scope không phải permission trên từng bản ghi

Một user có thể có:

~~~text
tenant-blue: order_manager
tenant-green: order_viewer
~~~

Nếu AS cấp token với scope **orders:write**, RS vẫn phải kiểm user có permission ghi tại **tenant thực của đơn hàng** hay không. Role theo tenant hoặc ownership có thể thay đổi sau khi token phát hành.

**AS giới hạn quyền cấp cho client/token; RS thực thi điều kiện nghiệp vụ theo tài nguyên hiện tại.** Hai bước bổ trợ nhau.

## 11. Client registration: AS phải biết đang cấp cho ai

AS không thể cấp token an toàn chỉ bằng việc thấy một chuỗi **client_id** hợp lệ. Nó cần hồ sơ đăng ký client và chính sách.

Thông tin thường liên quan:

| Thuộc tính client | Ý nghĩa bảo mật |
| --- | --- |
| **client_id** | Định danh client đã đăng ký; không mặc nhiên là bí mật. |
| **client type** | Public hay confidential, khả năng bảo vệ credential và phương thức được cho phép. |
| **redirect_uris** | Tập callback hợp lệ cho luồng có redirect; cần so khớp nghiêm ngặt. |
| **grant types** | Những luồng client được phép dùng. |
| **token endpoint auth method** | Cơ chế client authentication đã đăng ký, ví dụ client_secret_basic, private_key_jwt hoặc mTLS. |
| **allowed scopes/resources** | Giới hạn về hành động và API đích. |
| **PKCE/security requirements** | Yêu cầu proof và các ràng buộc chống code interception. |
| **lifetime/session policy** | Thời hạn và quy tắc cấp AT/RT cho client. |
| **rotation/binding policy** | Cách bảo vệ RT và sender-constrained tokens. |

### Public và confidential client

**Confidential client** có môi trường server có thể bảo vệ secret/khóa riêng theo điều kiện vận hành. **Public client** như SPA và native app thường không thể giữ một client secret nhúng trong mã khỏi người sở hữu thiết bị hoặc mã chạy trong trình duyệt.

AS cần phân biệt:

- **client_id** nhận diện client registration, không tự xác thực public client mạnh.
- **Client authentication** xác minh confidential client theo phương thức đã đăng ký.
- **PKCE** ràng buộc authorization code với phiên yêu cầu, không phải thay thế mọi chính sách client authentication.
- **Sender-constraining** như DPoP/mTLS ràng buộc token hoặc yêu cầu với một khóa/chứng chỉ khi profile cho phép.

Nếu AS cho phép một public client tự đổi loại thành confidential chỉ bằng cách gửi client_secret đã hardcode, mô hình tin cậy đã bị phá vỡ.

## 12. Những endpoint bổ trợ của AS

Không phải AS nào cũng triển khai mọi endpoint. Các điểm cuối dưới đây là **cơ chế tùy chức năng/profile**, không đồng nghĩa nhau.

| Endpoint | Tiêu chuẩn thường liên quan | Mục đích |
| --- | --- | --- |
| **Authorization endpoint** | RFC 6749 / OIDC | Xử lý yêu cầu ủy quyền qua user agent. |
| **Token endpoint** | RFC 6749 | Xác minh grant và cấp token. |
| **Token introspection** | RFC 7662 | Cho bên được phép hỏi trạng thái và thuộc tính token. |
| **Token revocation** | RFC 7009 | Nhận yêu cầu thu hồi token theo policy. |
| **Authorization Server metadata** | RFC 8414 | Công bố issuer, endpoint và các khả năng được hỗ trợ. |
| **JWKS URI** | JWK/JWKS standards và profile | Công bố khóa công khai để bên xác minh token/JWT lấy theo cấu hình đáng tin. |
| **UserInfo (OIDC OP)** | OIDC Core | Trả claims về End-User cho client được ủy quyền. |

### 12.1 Introspection

Với opaque token hoặc kiến trúc xác minh tập trung, RS có thể gọi **introspection endpoint**:

~~~http
POST /oauth2/introspect HTTP/1.1
Host: identity.example.test
Content-Type: application/x-www-form-urlencoded
Authorization: Basic EXAMPLE_RS_AUTH

token=EXAMPLE_OPAQUE_ACCESS_TOKEN
~~~

Phản hồi minh họa:

~~~json
{
  "active": true,
  "client_id": "dashboard-web",
  "sub": "user-42",
  "aud": "orders-api",
  "scope": "orders:read",
  "exp": 1730000900
}
~~~

**active=true** theo trạng thái AS tại thời điểm kiểm không tự cho phép mọi hành động. RS vẫn cần kiểm audience, scope, client/subject, loại token, policy của tài nguyên và giới hạn cache dữ liệu introspection.

AS phải **xác thực/ủy quyền bên gọi introspection**, tránh để endpoint trở thành nơi mọi người có thể dò token hoặc lấy claims nhạy cảm. RS chỉ được nhận thông tin cần thiết theo chính sách.

### 12.2 Revocation

**Revocation endpoint** cho phép client hoặc bên có quyền yêu cầu thu hồi token theo RFC 7009. AS phải kiểm chính sách và cập nhật trạng thái token/grant thích hợp.

**Thu hồi refresh token không tự đảm bảo mọi JWT access token đã phát hành bị RS từ chối ngay** nếu RS chỉ kiểm JWT offline. Hiệu lực thu hồi phụ thuộc token format, TTL, introspection/cache hoặc cơ chế trạng thái/denylist/notification đã thiết kế.

### 12.3 Metadata và JWKS

Ví dụ metadata được công bố bởi một AS:

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
  ]
}
~~~

Đây là JSON giả để minh họa cách client/RS phát hiện cấu hình **khi AS hỗ trợ metadata**. URL và đường dẫn thực tế phụ thuộc triển khai.

Client/RS phải **ràng buộc discovery với issuer đã tin cậy**, xác minh TLS và không gửi client secret/RT tới token_endpoint chỉ vì URL xuất hiện trong dữ liệu không đáng tin.

**JWKS chứa khóa công khai** cho các thuật toán phù hợp; RS không được chấp nhận khóa ký hoặc URL JWKS tùy ý do JWT header đề xuất mà bỏ kiểm issuer/trust configuration.

## 13. Vòng đời token do AS quản lý

Một token không phải bằng chứng vĩnh viễn. AS cần quản lý từ **cấp phát → sử dụng → gia hạn → thu hồi hoặc hết hiệu lực**.

~~~mermaid
stateDiagram-v2
    [*] --> Authorized: Grant được AS chấp thuận
    Authorized --> Issued: Cấp AT và RT khi policy cho phép
    Issued --> Refreshed: RT hợp lệ được dùng tại token endpoint
    Refreshed --> Issued: Cấp AT mới / RT mới khi rotate
    Issued --> Expired: AT hết hạn
    Issued --> Revoked: Token/grant bị thu hồi
    Refreshed --> Revoked: RT reuse hoặc policy rút quyền
    Expired --> [*]
    Revoked --> [*]
~~~

Sơ đồ chỉ biểu diễn **trạng thái khái niệm**. AT và RT có vòng đời độc lập: AT có thể hết hạn nhưng RT vẫn còn; AS có thể thu hồi RT trong khi AT đã ký vẫn còn được API chấp nhận tới khi RS biết trạng thái hoặc AT hết hạn.

Những quyết định AS cần có:

1. **Thời hạn access token:** phù hợp rủi ro, audit và khả năng thu hồi.
2. **Thời hạn refresh token:** có thể có giới hạn tuyệt đối/inactivity, session policy và grant lifetime.
3. **Rotation hoặc sender-constraining:** đặc biệt với RT cấp cho public client.
4. **Revoke khi sự kiện rủi ro:** logout, mất thiết bị, thay đổi credential, grant bị rút hoặc phát hiện reuse.
5. **Phạm vi không được nâng trái phép:** refresh grant không tự tăng scope vượt sự ủy quyền gốc.
6. **Key rotation:** đổi khóa ký/phát hành token, cung cấp công khai khóa phù hợp để RS chuyển tiếp an toàn.

### Phân biệt key rotation với token revocation

- **Key rotation** thay đổi khóa mà AS dùng để ký hoặc bảo vệ token; đây là trách nhiệm quản trị mật mã.
- **Refresh token rotation** thay RT cũ bằng RT mới trong một grant/phiên.
- **Revocation** làm token/grant mất hiệu lực theo hệ thống kiểm trạng thái.

Xoay khóa ký **không nhất thiết đồng nghĩa thu hồi mọi token** đã ký bằng khóa cũ; RS có thể còn cần khóa công khai cũ để xác minh token còn hạn trong giai đoạn chuyển tiếp. Ngược lại, ngừng tin khóa vì bị lộ có thể ảnh hưởng nhiều token và cần quy trình sự cố riêng.

## 14. Ranh giới trách nhiệm giữa AS và Resource Server

Câu hỏi quan trọng: **AS đã ký và cấp token rồi thì RS còn phải làm gì?**

| Kiểm tra/quyết định | Authorization Server | Resource Server |
| --- | --- | --- |
| Xác minh client/grant khi cấp | **Chịu trách nhiệm**. | Thông thường không thực hiện lại grant flow. |
| Quyết định scope được cấp | **Chịu trách nhiệm tại thời điểm phát hành**. | Kiểm scope token phù hợp endpoint. |
| Chọn audience/TTL | **Chịu trách nhiệm khi phát hành**. | Kiểm audience, exp/nbf của token nhận được. |
| Ký hoặc quản lý trạng thái token | **Chịu trách nhiệm theo token format**. | Kiểm chữ ký hoặc introspection qua cấu hình tin cậy. |
| Quản lý RT, rotation, token endpoint | **Chịu trách nhiệm**. | Không nhận RT như credential API. |
| Trạng thái account/grant bị rút | AS có thể nắm và phản ánh tùy kiến trúc. | Cần đáp ứng yêu cầu freshness/revocation của policy. |
| Permission trên Order #123 | Có thể hỗ trợ claims/authorization data. | **Phải bảo đảm quyết định đúng trên tài nguyên hiện tại**. |
| Tenant của bản ghi nghiệp vụ | Không nhất thiết biết mọi bản ghi. | Kiểm từ dữ liệu phía server đáng tin. |
| Thao tác nghiệp vụ bị gửi lặp | Không trực tiếp biết trạng thái nghiệp vụ. | Thiết kế idempotency/transaction policy khi cần. |

Một token đúng chữ ký, **aud=orders-api** và **scope=orders:approve** vẫn có thể phải bị từ chối khi principal không có permission duyệt đơn hàng ở tenant hiện tại.

Để tránh **confused deputy/token substitution**, RS phải chấp nhận **đúng token profile, đúng issuer và đúng audience**, không coi mọi JWT được ký bởi cùng công ty đều có thể dùng ở mọi API.

## 15. Bảo vệ AS trước các mối đe dọa thường gặp

AS là **thành phần tin cậy cao** vì nó có thể phát hành credential mà nhiều Resource Server chấp nhận. Một lỗi ở AS có thể làm rủi ro lan rộng.

| Nguy cơ | AS có thể thất bại ra sao? | Kiểm soát quan trọng |
| --- | --- | --- |
| **Redirect URI/open redirect** | Code/response được gửi tới nơi kẻ tấn công kiểm soát. | Đăng ký và so khớp redirect URI nghiêm ngặt, không nhận URL tùy tiện. |
| **Authorization code interception** | Bên khác lấy code và đổi được token. | PKCE, code một lần, ràng buộc client/redirect, TLS. |
| **Client impersonation** | Chỉ dựa vào client_id hoặc tin secret nhúng trong public app. | Client auth cho confidential client; grant/binding theo loại client. |
| **Scope escalation** | Cấp scope mà client hoặc grant không được phép. | Allowlist scopes/resources, policy và kiểm sự ủy quyền. |
| **Audience confusion** | Cấp token quá rộng hoặc RS dùng nhầm API đích. | Audience hẹp, resource binding và RS kiểm aud. |
| **Token replay/theft** | Bản sao bearer token tiếp tục dùng. | HTTPS, TTL hẹp, DPoP/mTLS khi phù hợp, revocation. |
| **Refresh token reuse** | RT cũ dùng lại nhưng AS không phản ứng theo policy. | Rotation/sender-constraining, phát hiện reuse và quản lý phiên. |
| **Signing-key compromise** | Attacker có thể tạo token giả được RS tin. | KMS/HSM, phân quyền key, rotation, incident response. |
| **Discovery/mix-up** | Client gửi grant/secret tới sai AS. | Ràng buộc issuer, metadata và endpoint tin cậy, kiểm state/issuer theo profile. |
| **Phishing login/consent** | Người dùng bị đưa tới giao diện giả. | Endpoint đúng issuer, TLS, chống redirect sai, truyền thông và chính sách UX. |
| **Credential/log leakage** | Code, RT, client secret hoặc AT bị ghi vào log. | Redaction, hạn quyền log, bảo vệ token endpoint responses. |
| **AS downtime** | Không refresh hoặc introspect được token. | HA, retry có giới hạn, cache có policy, fail-safe và giám sát. |

### TLS bảo vệ đường truyền nhưng không thay quyết định AS

AS phải sử dụng HTTPS/TLS phù hợp cho authorization/token/introspection/revocation và các luồng chứa credential. Client phải xác minh certificate/hostname và đúng token endpoint; không được gửi refresh token sang một URL do dữ liệu ngoài tự đưa vào.

Tuy nhiên, TLS không thay thế:

- Kiểm client auth, PKCE và grant.
- Scope/audience least privilege.
- Bảo vệ token ở DB/log/runtime.
- Phát hiện RT reuse và thu hồi.
- Quyền hiện hành tại Resource Server.

## 16. Pseudocode: AS quyết định phát hành token

Mã giả sau minh họa **trách nhiệm**; nó **không phải triển khai AS production** và không bao quát mọi grant/profile:

~~~text
function tokenEndpoint(request):
    requireHttpsAndValidServerConfiguration()
    requireHttpPostAndValidFormEncoding(request)

    requestedGrant = parseGrantType(request)
    clientRegistration = resolveClientRegistration(request)

    if not supported(requestedGrant):
        return oauthError("unsupported_grant_type")

    if not clientRegistration.allows(requestedGrant):
        return oauthError("unauthorized_client")

    if clientRegistration.isConfidential():
        if not authenticateByRegisteredMethod(clientRegistration, request):
            return oauthError("invalid_client")
    else:
        requirePublicClientProtectionsForGrant(
            clientRegistration, requestedGrant, request
        )

    context = validateGrantAtomically(
        grantType = requestedGrant,
        request = request,
        client = clientRegistration,
        codeIsOneTime = true,
        pkceAndRedirectBindingWhenRequired = true,
        refreshRotationAndSenderBindingWhenRequired = true
    )
    if not context.valid:
        return oauthError("invalid_grant")

    grantedScopes = authorizeScopes(
        client = clientRegistration,
        grant = context,
        requestedScopes = request.scope
    )
    audience = authorizeResource(
        client = clientRegistration,
        grant = context,
        requestedResource = request.resource
    )

    if not issuancePolicyAllows(context, grantedScopes, audience):
        return appropriateOAuthError()

    accessToken = issueAccessToken(
        issuer = trustedServerIssuer,
        subject = context.subjectAccordingToGrant,
        clientId = clientRegistration.id,
        audience = audience,
        scopes = grantedScopes,
        expiry = chooseExpiryByPolicy(),
        senderBinding = context.binding
    )

    refreshToken = maybeIssueOrRotateRefreshToken(
        grantType = requestedGrant,
        context = context,
        client = clientRegistration,
        policy = refreshTokenPolicy
    )

    return responseNoStore(
        access_token = accessToken,
        token_type = accessToken.profileType,
        expires_in = accessToken.lifetimeSeconds,
        scope = grantedScopes,
        optional_refresh_token = refreshToken
    )
~~~

**Những điểm phải giữ khi triển khai thật:**

- Parse input nghiêm ngặt, áp rate limit, chống replay, xử lý concurrency và phát hiện tham số không hợp lệ.
- Tài khoản, client, subject và quyền được suy từ **dữ liệu đã xác minh**, không từ claims tự khai của client.
- Authorization code phải **one-time**, refresh token rotation cần **atomicity** để hạn chế race và reuse.
- Response chứa credential cần **Cache-Control: no-store** và không bị ghi body vào logs.
- Key, issuer, audience, thuật toán và TTL phải đến từ **cấu hình/chính sách tin cậy**.
- Một lỗi ở DB/KMS/policy store không được biến thành nhánh “cấp token bỏ qua kiểm tra”.

### Phản hồi token minh họa

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

Phản hồi là **giả lập**. Không phải mọi grant đều cấp refresh_token. Thời hạn 900 giây chỉ là ví dụ, không phải giá trị mặc định của OAuth 2.0.

## 17. AS xử lý lỗi như thế nào?

Token endpoint không được phát hành token cho grant thiếu hoặc không hợp lệ. Một số lỗi OAuth 2.0 điển hình:

| Lỗi | Khi nào thường gặp? | Điều AS cần bảo đảm |
| --- | --- | --- |
| **invalid_request** | Thiếu tham số bắt buộc, sai định dạng hoặc tham số trùng không hợp lệ. | Không tiếp tục xử lý bằng cách đoán ý request. |
| **invalid_client** | Client authentication thất bại. | Không phát token; tránh lộ chi tiết secret/cert. |
| **invalid_grant** | Code/RT hết hạn, bị thu hồi, dùng lại, sai client hoặc verifier. | Không chấp nhận grant không hợp lệ. |
| **unauthorized_client** | Client không được dùng grant đang yêu cầu. | Kiểm client registration/grant allowlist. |
| **unsupported_grant_type** | AS không hỗ trợ grant. | Không tự fallback sang grant yếu hơn. |
| **invalid_scope** | Scope sai, vượt quyền hoặc không được chấp nhận theo policy. | Không mở quyền chỉ để đáp ứng client. |

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

Đối với **invalid_client**, response có thể dùng HTTP 401 cùng WWW-Authenticate theo phương thức xác thực áp dụng. Cần tuân thủ quy tắc giao thức cụ thể; không gán mọi lỗi thành 401.

AS không nên tiết lộ refresh token, code, client secret, private key, payload nhạy cảm hoặc thông tin account chi tiết qua error_description, logs và telemetry.

**Authorization endpoint** có cách trả lỗi liên quan đến redirect riêng; không chuyển hướng về redirect URI chưa được xác minh chỉ để hiển thị lỗi.

## 18. Kịch bản tổng hợp: Dashboard, Orders API và Payment API

Một doanh nghiệp có:

~~~text
OAuth Client:
    dashboard-web

Authorization Server:
    https://identity.example.test

Resource Servers:
    https://orders.example.test  (orders-api)
    https://payments.example.test (payments-api)

Người dùng:
    Alice, quyền xem đơn hàng tenant-blue
~~~

Nhu cầu: Alice mở dashboard và xem danh sách đơn hàng, không cần hoàn tiền.

### Luồng đúng

1. Dashboard tạo PKCE verifier/challenge và chuyển Alice tới authorization endpoint của AS.
2. AS xác thực Alice theo chính sách, kiểm client registration và sự ủy quyền.
3. AS chỉ cho phép **orders:read** với audience **orders-api**, không cấp **payments:refund**.
4. Dashboard đổi authorization code qua token endpoint với code_verifier và client authentication nếu là confidential client.
5. AS trả AT đúng audience/scope, có thể trả RT nếu chính sách cho phép.
6. Dashboard gọi Orders API qua HTTPS với AT.
7. Orders API xác minh **issuer, signature/active, audience, thời hạn, scope** rồi kiểm Alice được đọc các đơn thuộc **tenant-blue**.
8. Nếu dashboard gửi cùng AT sang Payments API, Payments API từ chối do sai audience và/hoặc scope.
9. Nếu Alice bị rút quyền truy cập, RS/AS phải thực thi chính sách độ mới của quyền và thu hồi đã được thiết kế; chữ ký AT không tự cập nhật role.
10. Nếu RT bị thu hồi, AS từ chối refresh. AT đang lưu hành có thể cần cơ chế riêng để bị từ chối trước exp.

### Luồng sai và nguyên nhân

**Sai A:** Dashboard yêu cầu **payments:refund** và AS cấp luôn vì Alice đã đăng nhập.

**Vấn đề:** Authentication không thay client allowlist và sự ủy quyền. AS đã cấp quá quyền.

**Sai B:** Orders API chấp nhận một ID token OIDC có audience **dashboard-web**.

**Vấn đề:** Sai loại token và audience, có thể gây token substitution.

**Sai C:** Payments API chấp nhận mọi JWT cùng issuer mà không kiểm **aud**.

**Vấn đề:** JWT hợp lệ theo chữ ký nhưng không dành cho Payments API.

**Sai D:** Dashboard gửi RT vào Authorization header khi gọi Orders API.

**Vấn đề:** RT dành cho token endpoint, không phải API dữ liệu; RS phải không xử lý RT như AT.

**Sai E:** AS cấp scope **admin:all** cho client_credentials của nightly-report-worker chỉ vì client có secret đúng.

**Vấn đề:** Client authentication không tự cấp quyền quản trị. AS còn phải kiểm grant policy, scope/resource và nguyên tắc least privilege.

## 19. Bảng kiểm thử trách nhiệm của Authorization Server

| Trường hợp kiểm thử | Kết quả mong đợi |
| --- | --- |
| Client đã đăng ký, code + PKCE đúng, grant hợp lệ. | AS có thể cấp token đúng scope/audience/policy. |
| Code đã đổi một lần, gửi lại. | Từ chối; không phát AT mới từ code cũ. |
| Code thuộc client A, client B cố đổi. | Từ chối theo binding. |
| Code verifier sai. | Từ chối, thường invalid_grant. |
| Redirect URI sai so với authorization request. | Từ chối, không cấp token. |
| Public client cố xác thực mạnh bằng secret hardcoded. | Không coi secret nhúng là confidential client authentication. |
| Confidential client không xác thực được. | Từ chối invalid_client theo quy tắc. |
| Client xin scope ngoài allowlist. | Không cấp quyền vượt cấu hình/chính sách. |
| Client xin audience API không được phép. | Từ chối hoặc giới hạn theo hợp đồng; không phát token dùng chung tùy tiện. |
| Client_credentials xin sub của một user tùy ý. | Không cấp dựa vào subject tự khai. |
| RT bị thu hồi/hết hạn. | Từ chối refresh. |
| RT cũ được dùng lại sau rotation. | Từ chối và xử lý reuse theo policy. |
| Token thiếu/sai exp theo profile. | AS không phát hành token sai schema; RS từ chối nếu nhận được. |
| RS hỏi introspection mà không có quyền. | AS từ chối tiết lộ trạng thái/claims token. |
| JWT access token đúng chữ ký nhưng sai audience API. | RS từ chối, dù AS phát hành hợp lệ cho API khác. |
| AS thay signing key. | RS vẫn xác minh token còn hợp lệ theo kế hoạch key rotation; không tin khóa tùy ý. |
| Client gửi token/RT qua URL HTTP. | Client/AS chặn credential trên kênh không an toàn theo chính sách. |
| Response token bị log nguyên văn. | Redaction và kiểm soát logs ngăn lộ credential. |
| AS policy store lỗi. | Không tự cấp token khi thiếu kiểm tra bắt buộc; xử lý fail-safe. |
| User bị khóa sau khi AT đã phát hành. | AS không cấp mới ngoài policy; RS đáp ứng SLA cập nhật quyền/thu hồi đã thiết kế. |

### Theo dõi vận hành nhưng không lộ bí mật

Một AS cần quan sát:

- Tỷ lệ cấp token theo **client, grant và scope**.
- Lỗi **invalid_grant**, **invalid_client**, scope vượt quyền và code reuse.
- Refresh token rotation/reuse detection, số phiên bị revoke.
- Thời hạn token được cấp, bất thường về audience hoặc client.
- Chất lượng TLS, key rotation, thời gian đáp ứng token/introspection endpoint.
- Độ trễ phản ánh thu hồi trên các RS và ảnh hưởng của cache introspection.

Không ghi **access token, refresh token, authorization code, client secret hoặc private key** nguyên văn trong logs/traces chỉ để thuận tiện debug.

## 20. Những ngộ nhận cần tránh

**“Authorization Server chính là Resource Server.”** Không phải về mặt vai trò. Một triển khai có thể gộp hai chức năng trên cùng hệ thống, nhưng trách nhiệm phát hành token và bảo vệ tài nguyên vẫn khác nhau.

**“AS xác thực người dùng rồi thì token đương nhiên có mọi quyền của user.”** Không. Client registration, scope, resource, sự ủy quyền và chính sách cấp phát tiếp tục giới hạn token.

**“Mọi OAuth token đều nói về người dùng.”** Không. Client credentials có thể đại diện client/workload mà không có End-User.

**“AS cấp AT có scope orders:write thì RS phải cho mọi lệnh ghi.”** Không. RS còn kiểm permission, tenant, ownership và trạng thái tài nguyên.

**“JWT có chữ ký hợp lệ nên có thể dùng ở API nào cũng được.”** Không. Audience, issuer, token type, thời hạn và policy phải đúng với từng RS.

**“Refresh token có thể gọi API hoặc được gia hạn mãi mãi.”** Không. RT dành cho AS, có ràng buộc client/grant và vòng đời/thu hồi theo chính sách.

**“Đã dùng HTTPS thì không cần PKCE hoặc chống replay.”** Không. TLS bảo vệ kênh; PKCE, code dùng một lần và sender-constraining giải quyết những nguy cơ khác.

**“Đổi signing key là đã revoke mọi token bị lộ.”** Không nhất thiết. Rotation key và thu hồi token là những cơ chế khác nhau.

**“OAuth AS luôn là IdP/OP, nên access token luôn dùng làm token đăng nhập.”** Không. OAuth tập trung ủy quyền; OIDC xác định ID token và quy tắc xác thực client riêng.

## 21. Bài tập tự đánh giá

**Câu 1:** Client A đăng nhập người dùng thành công, rồi yêu cầu **payments:refund** nhưng client registration chỉ cho phép **orders:read**. AS nên làm gì?

**Trả lời:** Không cấp **payments:refund** ngoài allowlist và policy. Tùy hợp đồng, AS có thể giới hạn scope hoặc trả lỗi; việc user đăng nhập không tự cấp quyền.

**Câu 2:** Với **client_credentials**, AS có cần có End-User đăng nhập trong browser ở mỗi lần cấp token không?

**Trả lời:** Không. AS xác thực client/workload và áp chính sách grant/scope; token không nhất thiết đại diện người dùng cuối.

**Câu 3:** Nếu AS cấp JWT đúng chữ ký chứa **aud=reports-api**, Payments API có được chấp nhận không?

**Trả lời:** Không nếu Payments API yêu cầu audience **payments-api**. Resource Server phải kiểm đúng đối tượng nhận, không chỉ chữ ký.

**Câu 4:** Token endpoint nhận authorization code đã được đổi thành công trước đó. Có thể phát AT mới lần nữa từ code ấy không?

**Trả lời:** Không. Authorization code phải dùng một lần; việc tái sử dụng phải bị từ chối và xử lý theo bảo vệ của AS.

**Câu 5:** Khi người dùng rút quyền, AS thu hồi RT; AT JWT còn hạn có bị RS từ chối tức thì không?

**Trả lời:** Không nhất thiết. Cần cơ chế để RS biết trạng thái bị rút quyền, hoặc chấp nhận độ trễ tới khi AT hết hạn theo SLA.

**Câu 6:** Nếu AS đồng thời là OIDC OpenID Provider, ID token dùng để gọi Orders API được không?

**Trả lời:** Không dùng thay access token. ID token là bằng chứng xác thực dành cho client theo OIDC, audience/mục đích khác với access token của RS.

**Câu 7:** Nếu một API có permission nghiệp vụ phức tạp, nên nhúng toàn bộ điều kiện vào scope hay để RS kiểm?

**Trả lời:** AS giới hạn scope và audience, còn RS kiểm quyền theo tài nguyên/tenant/trạng thái hiện hành; không nên coi một scope tổng quát là thay cho toàn bộ policy động.

## 22. Checklist thiết kế và review Authorization Server

Trước khi triển khai hoặc tích hợp AS:

1. **Vai trò:** Đã phân biệt Resource Owner, Client, AS, RS và OIDC OP nếu dùng chưa?
2. **Client registration:** Có lưu loại client, redirect URIs, grant allowlist, auth method, allowed scopes/resources?
3. **Authorization flow:** Redirect URI được kiểm nghiêm ngặt, code một lần, PKCE, state/nonce theo profile và chống mix-up?
4. **Client authentication:** Confidential client dùng phương thức đã đăng ký, public client không được giả làm confidential?
5. **Grant validation:** Authorization code/refresh token/client credentials được kiểm riêng, không có grant tự chế thiếu chính sách?
6. **Scope:** Chỉ cấp scope được client/grant/owner/policy cho phép, không tin scope tự khai?
7. **Audience:** Access token dành cho đúng Resource Server, resource indicator được kiểm theo policy?
8. **Claims:** iss/sub/client_id/aud/exp/nbf/scope và loại token được phát theo profile đúng?
9. **Format:** JWT/opaque được lựa chọn theo nhu cầu kiểm trạng thái, privacy, revocation và khả năng RS?
10. **Token storage:** AS bảo vệ RT, client secret và signing keys trong KMS/HSM/secret store hoặc cơ chế phù hợp?
11. **Refresh:** RT có hạn, grant binding, rotation/sender-constraining và reuse detection theo loại client?
12. **Sender proof:** DPoP/mTLS khi dùng phải có kiểm chứng cả lúc cấp và sử dụng token theo profile?
13. **Revocation/introspection:** Có xác thực bên gọi, cung cấp trạng thái phù hợp và đo độ trễ cache/thu hồi?
14. **Discovery/JWKS:** Issuer, metadata, endpoint và public keys được phân phối với cấu hình tin cậy và kế hoạch key rotation?
15. **Resource Server:** Có kiểm chữ ký/trạng thái, issuer, audience, loại token, thời hạn, scope và permission tài nguyên độc lập?
16. **Vòng đời:** Có chính sách ngừng quyền khi logout, account bị khóa, revoke grant hoặc phát hiện token bị đánh cắp?
17. **TLS và logs:** Credential được truyền qua HTTPS và không bị ghi vào logs, trace, URL hoặc response lỗi?
18. **Thử nghiệm:** Có negative tests cho code replay, client spoofing, sai audience, scope escalation, RT reuse, key rotation và policy outage?
19. **Giám sát:** Có metrics theo grant/client/scope, audit tối thiểu và phản ứng sự cố rò rỉ/token signing key?
20. **Giới hạn bảo đảm:** Tài liệu có ghi rõ token được cấp khác với việc RS cho phép thao tác cuối cùng hay không?

## Kết luận

**Authorization Server là trung tâm phát hành và quản lý credential ủy quyền trong OAuth 2.0.** Nó kiểm client registration, xác minh grant, xử lý sự ủy quyền của resource owner khi phù hợp, áp chính sách scope/audience và cấp access token cùng refresh token (nếu được phép). Khi triển khai OIDC, nó có thể đồng thời là **OpenID Provider** và phát ID token cho client theo quy tắc xác thực riêng.

Tuy nhiên, **AS không thay thế Resource Server**. Một access token được phát hành hợp lệ chỉ là credential cho phép client **yêu cầu** truy cập trong phạm vi được cấp; RS còn phải kiểm token và quyết định theo quyền hiện hành, tenant, tài nguyên và nghiệp vụ. Phân biệt hai trách nhiệm này — cùng với Authorization Code + PKCE, giới hạn quyền, bảo vệ refresh token, key management, TLS và thu hồi — là nền tảng để token không trở thành “bằng chứng quyền vĩnh viễn”.

### Tài liệu tham khảo

- [RFC 6749 — The OAuth 2.0 Authorization Framework, Section 1.1: Roles](https://www.rfc-editor.org/rfc/rfc6749#section-1.1)
- [RFC 6749 — Section 3: Protocol Endpoints](https://www.rfc-editor.org/rfc/rfc6749#section-3)
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009)
- [RFC 7636 — Proof Key for Code Exchange (PKCE)](https://www.rfc-editor.org/rfc/rfc7636)
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662)
- [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414)
- [RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens](https://www.rfc-editor.org/rfc/rfc8705)
- [RFC 8707 — Resource Indicators for OAuth 2.0](https://www.rfc-editor.org/rfc/rfc8707)
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725)
- [RFC 9068 — JSON Web Token Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068)
- [RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449)
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700)
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html)
