# Ai phát hành token và ai xác minh token?

Khi một API nhận được chuỗi `Authorization: Bearer ...`, câu hỏi bảo mật đầu tiên không phải là “chuỗi này có giải mã được không?”, mà là: **Ai có quyền phát hành token này, API dựa vào đâu để tin token, và token được phép dùng cho việc gì?** Đây là ranh giới tin cậy cốt lõi trong bảo mật token.

Trong OAuth 2.0 và OpenID Connect (OIDC), bên **phát hành** và bên **xác minh/sử dụng** token thường là hai thành phần khác nhau. Đặc biệt, **một chữ ký hợp lệ chưa đủ để cấp quyền truy cập**: token còn phải đúng nguồn phát hành, đúng đối tượng nhận, còn hiệu lực và có quyền phù hợp với tài nguyên được yêu cầu.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Chỉ ra ai phát hành access token, refresh token và ID token; phân biệt vai trò của **Authorization Server**, **OpenID Provider**, **Client** và **Resource Server**.
- Giải thích API kiểm tra access token kiểu JWT bằng khóa công khai, hoặc kiểm tra opaque token qua introspection.
- Xác định ranh giới tin cậy bằng `iss` (issuer), `aud` (audience), thời hạn, scope và quyền thực tế trên tài nguyên.
- Nhận biết vì sao ID token, refresh token hoặc token dành cho API khác không được dùng thay access token của API hiện tại.
- Thiết kế các biện pháp căn bản để hạn chế token bị đánh cắp, phát lại, thu hồi không kịp thời và cấu hình sai khóa xác minh.

## 2. Các vai trò trong mô hình tin cậy

| Vai trò | Nhiệm vụ chính | Điều được tin cậy, và giới hạn |
|---|---|---|
| **Resource Owner / End User** | Người dùng hoặc chủ sở hữu tài nguyên cấp quyền theo luồng phù hợp. | Đăng nhập thành công không có nghĩa mọi API đều phải cho phép mọi thao tác. |
| **Client** | Ứng dụng web, mobile, backend hoặc dịch vụ yêu cầu token để gọi API. | Client **nhận và sử dụng** token theo giao thức; bình thường client không tự phát hành access token có giá trị với API khác. |
| **Authorization Server (AS)** | Xác thực/ủy quyền theo luồng OAuth 2.0, phát hành access token và có thể phát hành refresh token; quản lý chính sách, khóa và vòng đời token. | Là nguồn phát hành mà Resource Server đã chủ động cấu hình để tin. |
| **OpenID Provider (OP)** | Nhà cung cấp danh tính trong OIDC, phát hành **ID token** cho OIDC Client và thường kiêm vai trò Authorization Server. | ID token chứng minh kết quả xác thực cho đúng client, không tự nhiên là vé truy cập mọi API. |
| **Resource Server (RS)** | API chứa dữ liệu/nghiệp vụ được bảo vệ; nhận access token và ra quyết định nhận hoặc từ chối yêu cầu. | Xác minh tính hợp lệ của token **và** kiểm tra quyền trên endpoint/tài nguyên. |
| **API Gateway** (nếu có) | Có thể kiểm tra token tại biên và chuyển ngữ cảnh xác thực cho dịch vụ phía sau. | Chỉ đáng tin nếu đường đi nội bộ được bảo vệ, header không thể bị client giả mạo và các dịch vụ áp dụng chính sách phù hợp. |

Ví dụ hệ thống gồm:

- Authorization Server: `https://auth.example.com`.
- API đơn hàng: `https://orders.example.com`, định danh audience là `orders-api`.
- API thanh toán: `https://payments.example.com`, định danh audience là `payments-api`.
- Ứng dụng: `shop-web`, đăng nhập người dùng và gọi các API được phép.

**Quan hệ tin cậy phải được cấu hình trước.** API đơn hàng tin các access token do `https://auth.example.com` phát hành **cho audience `orders-api`**, với chính sách quyền riêng của API đơn hàng. Một JWT do hệ thống khác ký đúng bằng khóa của hệ thống đó vẫn không được API đơn hàng mặc nhiên chấp nhận.

### Bên nào là “issuer”?

**Issuer** là định danh của hệ thống có thẩm quyền phát hành token. Với JWT, claim `iss` thường mang định danh này. Nó không đồng nghĩa với người dùng đăng nhập (`sub`), ứng dụng gọi API (`client_id`/`azp` tùy hồ sơ token), hay API nhận token (`aud`).

Trong hệ thống có nhiều nhà cung cấp danh tính, một ứng dụng có thể chấp nhận nhiều issuer, nhưng **mỗi issuer phải được khai báo rõ cùng bộ khóa, audience và chính sách tương ứng**. Không nên nhìn vào `iss` trong token chưa xác minh rồi tự động tin bất kỳ URL/keyset nào mà token chỉ tới.

## 3. Ai phát hành và ai xác minh từng loại token?

| Loại token | Ai phát hành? | Ai nhận và kiểm tra? | Mục đích chính |
|---|---|---|---|
| **Access token dạng JWT** | Authorization Server | Resource Server (API), hoặc thành phần bảo vệ API được ủy thác | Cho phép gọi một tập API/hành động theo audience, scope và chính sách. |
| **Access token dạng opaque** | Authorization Server | Resource Server kiểm tra thông qua **token introspection** hoặc cơ chế tra cứu đáng tin cậy | Cùng mục đích access token JWT, nhưng bản thân chuỗi không cung cấp claims cho API đọc trực tiếp. |
| **Refresh token** | Authorization Server | **Authorization Server** khi client đổi lấy access token mới | Duy trì phiên cấp quyền; không dùng để gọi API nghiệp vụ. |
| **ID token (OIDC)** | OpenID Provider | **OIDC Client** có `client_id` tương ứng, theo quy tắc OIDC | Thông tin kết quả xác thực người dùng cho client; không thay access token. |
| **Session cookie** của ứng dụng | Ứng dụng quản lý phiên (hoặc hệ thống phiên liên quan) | Chính ứng dụng hoặc lớp session tương ứng | Theo dõi phiên ứng dụng; không mặc nhiên là OAuth access token. |

Lưu ý quan trọng:

1. **JWT** là một định dạng token có thể chứa claims và được ký (JWS) hoặc mã hóa (JWE); **opaque** mô tả token mà bên nhận không cần hoặc không thể giải nghĩa cục bộ. **Access** và **refresh** mô tả *mục đích sử dụng*. Hai cách phân loại này độc lập: access token có thể là JWT hoặc opaque; refresh token thông thường nên được client xem như chuỗi bí mật không cần giải nghĩa.
2. OAuth 2.0 **không bắt buộc** access token phải là JWT. Không được dựa vào dấu chấm trong chuỗi hoặc việc giải mã Base64URL để kết luận token hợp lệ.
3. Có token được phát hành **thay mặt người dùng** (ví dụ authorization code flow), cũng có token cấp **cho chính ứng dụng/dịch vụ** (ví dụ `client_credentials`). Trong trường hợp sau, đừng mặc định `sub` đại diện cho một end user.
4. Kể cả khi cùng một Authorization Server phát hành ID token và access token, **đối tượng nhận và tập quy tắc xác minh vẫn khác nhau**.

## 4. Luồng điển hình: ai làm gì theo thứ tự?

Sơ đồ sau minh họa ứng dụng dùng **Authorization Code + PKCE**, một access token JWT và API sử dụng khóa công khai do issuer công bố.

~~~mermaid
sequenceDiagram
    autonumber
    actor U as Người dùng
    participant C as Client (ứng dụng)
    participant AS as Authorization Server / OP
    participant API as Resource Server (API)
    U->>C: Chọn đăng nhập
    C->>AS: Yêu cầu authorize (scope, state, PKCE challenge)
    AS->>U: Xác thực và xử lý cấp quyền
    AS-->>C: Authorization code qua redirect
    C->>AS: Đổi code + PKCE verifier (+ xác thực client nếu cần)
    AS-->>C: Access token, có thể kèm refresh/ID token
    C->>API: GET /orders + Bearer access token
    API->>API: Kiểm chữ ký, iss, aud, exp/nbf, scope
    Note over API,AS: API dùng khóa đã cấu hình/tải qua JWKS đáng tin cậy
    API-->>C: 200 nếu token hợp lệ và đủ quyền; ngược lại 401/403
~~~

Đọc sơ đồ theo ranh giới tin cậy:

1. **Client không phát hành access token**. Client yêu cầu token; AS quyết định có cấp hay không, dựa trên kiểu grant, danh tính client, quyền được cấp và chính sách.
2. **API không tin client chỉ vì client nói “đã đăng nhập”**. API xác minh bằng bằng chứng do AS phát hành và bằng chính sách của mình.
3. Nếu access token là JWT ký bất đối xứng, API thường kiểm tra chữ ký **cục bộ** bằng public key của issuer. Không bắt buộc gửi token về AS ở mỗi request.
4. **Khóa phát hành (private key) ở AS**; public key chỉ dùng để xác minh. Việc phân phối public key qua JWKS giúp nhiều API cùng xác minh mà không nắm bí mật ký.
5. PKCE ràng buộc lần đổi authorization code với client bắt đầu luồng, giúp giảm nguy cơ code bị chặn và đổi trái phép; PKCE **không tự giải quyết** việc access token đã cấp bị đánh cắp.

Trong OpenID Connect, nếu request có scope `openid` và quy trình đáp ứng điều kiện cấp ID token, OP có thể phát hành thêm ID token **cho client**. Client xác minh ID token theo OIDC, còn API tiếp tục dùng access token dành riêng cho API.

## 5. Access token JWT: Resource Server xác minh những gì?

Một access token JWT thường có cấu trúc `header.payload.signature` nếu ở dạng JWS compact serialization. Phần header và payload là Base64URL encoding, **không phải mã hóa bảo mật thông tin**.

Ví dụ payload đã giải mã, dùng giá trị minh họa:

~~~json
{
  "iss": "https://auth.example.com",
  "sub": "user-742",
  "aud": ["orders-api"],
  "client_id": "shop-web",
  "scope": "orders:read orders:create",
  "iat": 1893452400,
  "nbf": 1893452400,
  "exp": 1893456000,
  "jti": "access-93c8"
}
~~~

Các claim phụ thuộc vào hồ sơ token và hợp đồng của hệ thống. Không phải mọi access token đều có tất cả trường trên; `scope` có thể được biểu diễn dưới dạng khác, và `client_id` không phải claim bắt buộc trong mọi JWT. Hãy kiểm tra dựa trên cấu hình issuer, quy ước token thực tế và chuẩn hồ sơ đang áp dụng, chẳng hạn JWT Profile for OAuth 2.0 Access Tokens (RFC 9068).

### 5.1. Các bước kiểm tra nên thực hiện

| Điều kiện | Câu hỏi API phải trả lời | Nếu sai |
|---|---|---|
| **Nguồn khóa và thuật toán** | Token được ký bằng thuật toán cho phép, với khóa xác minh được gắn với **issuer đáng tin cậy**? | Từ chối |
| **Chữ ký / tính toàn vẹn** | Nội dung claims có bị sửa đổi sau khi ký không? | Từ chối |
| **`iss`** | Issuer có nằm trong danh sách nguồn phát hành API chấp nhận không? | Từ chối |
| **`aud`** | API này có thật sự là đối tượng nhận token không? | Từ chối |
| **`exp`, `nbf`, thời gian** | Token chưa hết hạn và đã tới thời điểm có hiệu lực? | Từ chối |
| **Loại token, hồ sơ token** | Đây là **access token** phù hợp API, không phải ID/refresh token? | Từ chối |
| **`scope` và quyền chi tiết** | Token có quyền cần thiết cho endpoint, và chủ thể có quyền với tài nguyên cụ thể? | Từ chối nếu thiếu quyền |
| **Chính sách bổ sung** | Tenant, client, trạng thái tài khoản, ràng buộc thiết bị, denylist... có đạt yêu cầu không? | Tùy chính sách, thường từ chối |

Ví dụ `GET /orders/42` yêu cầu scope `orders:read`. Token ở trên có scope này, nhưng API **vẫn phải kiểm tra** đơn hàng 42 thuộc người dùng `user-742` hoặc người dùng có quyền xem đơn đó. Scope cho phép một **loại hành động**; nó không thay thế kiểm tra quyền trên từng đối tượng dữ liệu.

Phân biệt rõ các trục:

- **Authentication**: token thể hiện chủ thể/phiên xác thực nào theo ngữ nghĩa giao thức?
- **Token validation**: token có do nguồn tin cậy phát hành, còn hiệu lực và dành cho API này không?
- **Authorization**: chủ thể, client, scope, vai trò và quan hệ với tài nguyên có cho phép thao tác cụ thể không?

### 5.2. Đặt niềm tin vào đúng public key

AS có thể cung cấp **JWKS** (JSON Web Key Set) chứa public key và `kid` (key ID). Khi kiểm tra JWT:

1. Cấu hình **issuer tin cậy** và địa chỉ metadata/JWKS của issuer đó qua kênh có TLS, hoặc dùng cơ chế discovery đáng tin cậy đã ràng buộc với issuer.
2. Đọc `kid` để chọn khóa trong **bộ khóa đã tin cậy**. `kid` chỉ là gợi ý tìm khóa, không phải bằng chứng nguồn phát hành.
3. Cho phép rõ các thuật toán/kiểu khóa đúng với cấu hình. Không chấp nhận tùy ý `alg: none`, không để token quyết định chuyển giữa HMAC và RSA/ECDSA theo cách gây nhầm khóa.
4. Dùng thư viện chuẩn xác minh chữ ký, kiểm issuer/audience/thời gian và hồ sơ token, rồi mới dùng claims để quyết định quyền.
5. Cache JWKS với cơ chế cập nhật/rotation phù hợp. Khi AS đổi khóa, API phải có thể lấy khóa mới nhưng cũng xử lý giai đoạn chồng lấp khóa cũ và khóa mới.

**Không tải khóa trực tiếp từ một URL tùy ý trong header token** (chẳng hạn `jku` hoặc `x5u`) nếu chưa được ràng buộc chặt với nguồn đã tin cậy. Kẻ tấn công có thể tự ký token và chỉ API đến public key do chính kẻ đó kiểm soát.

Với token ký đối xứng (HMAC), issuer và verifier cùng biết secret. Cách này làm tăng phạm vi tin cậy: hệ thống có secret để xác minh cũng có khả năng **tự tạo chữ ký hợp lệ**. Đối với nhiều API độc lập, ký bất đối xứng thường giúp phân tách quyền phát hành và quyền xác minh rõ hơn.

### 5.3. Minh họa kiểm tra ở API

Pseudocode sau trình bày **thứ tự quyết định**, không phải hướng dẫn tự viết thư viện xử lý mật mã:

~~~text
accessToken = readBearerToken(request.Authorization)
if accessToken is missing:
    return 401

claims = trustedJwtLibrary.verify(
    token = accessToken,
    issuer = "https://auth.example.com",
    audience = "orders-api",
    allowedAlgorithms = configuredAlgorithms,
    trustedJwks = configuredIssuerJwks,
    requiredTokenProfile = configuredAccessTokenProfile
)
if verification fails:
    return 401

if "orders:read" not in claims.scopes:
    return 403

order = orderRepository.findById(42)
if order is absent:
    return 404
if not policy.canReadOrder(subject=claims.sub, order=order):
    return 403

return 200 with order
~~~

Một điểm dễ bỏ sót: thư viện xác minh chữ ký **có thể không tự kiểm audience hoặc scope** nếu bạn chưa cấu hình. Hãy xác định rõ validator nào đảm nhiệm `iss`, `aud`, thời gian và loại token; định nghĩa kiểm quyền ở Resource Server. Với Spring Security, cấu hình OAuth2 Resource Server có thể xác thực JWT, nhưng cần bổ sung audience validator và quy tắc phân quyền cho endpoint khi ứng dụng yêu cầu.

## 6. Opaque access token: xác minh bằng introspection

Opaque token có thể trông như chuỗi ngẫu nhiên `mQ2n...`. Resource Server không nên suy ra quyền từ chuỗi này. Nếu hệ thống dùng OAuth 2.0 Token Introspection (RFC 7662), API gọi endpoint introspection mà AS cung cấp.

~~~mermaid
sequenceDiagram
    autonumber
    participant C as Client
    participant API as Resource Server
    participant AS as Authorization Server
    C->>API: Bearer opaque access token
    API->>AS: Introspect token (kênh TLS, RS xác thực với AS)
    AS->>AS: Kiểm tồn tại, hiệu lực, trạng thái thu hồi
    AS-->>API: active + metadata (hoặc active:false)
    API->>API: Kiểm audience, scope, subject, chính sách nghiệp vụ
    API-->>C: Chấp nhận hoặc từ chối
~~~

Ví dụ phản hồi introspection khi token còn hoạt động:

~~~json
{
  "active": true,
  "iss": "https://auth.example.com",
  "sub": "user-742",
  "aud": "orders-api",
  "scope": "orders:read",
  "client_id": "shop-web",
  "exp": 1893456000
}
~~~

Các trường ngoài `active` phụ thuộc Authorization Server và chính sách công bố metadata. Với `active: false`, API phải từ chối, không suy đoán lý do hoặc tin dữ liệu quyền cũ. Với `active: true`, API **vẫn kiểm tra** token có dành cho mình và đủ quyền, theo dữ liệu introspection đã được hệ thống trả về.

Để tin phản hồi này, Resource Server cần tin **đúng endpoint AS**, bảo vệ kết nối bằng TLS và thường **xác thực chính Resource Server** khi introspect token. Cache phản hồi có thể giảm độ trễ nhưng làm chậm hiệu lực của thao tác thu hồi. API cần chọn thời gian cache phù hợp với mức độ rủi ro.

| Khía cạnh | JWT tự xác minh | Opaque + introspection |
|---|---|---|
| Cách API kiểm | Thư viện kiểm chữ ký/claims bằng khóa từ issuer | Hỏi Authorization Server và kiểm metadata nhận về |
| Phụ thuộc mạng tới AS mỗi request | Thường không, nếu đã có khóa | Thường có, trừ khi cache hoặc kiến trúc kiểm tra khác |
| Thu hồi sớm | Khó thấy ngay nếu không có denylist, danh sách trạng thái hoặc cơ chế bổ sung | Có thể thấy sớm hơn nếu introspection trả trạng thái mới; cache làm trễ |
| Metadata ở token phía client | JWT payload có thể đọc được khi không mã hóa | Chuỗi token thường không lộ claims |
| Độ phức tạp chính | Xác minh chuẩn, quản lý khóa, issuer/audience và vòng đời JWT | Tính sẵn sàng AS, quyền gọi introspection, độ trễ, cache và xử lý lỗi |

Không có định dạng nào tự động “an toàn hơn” trong mọi trường hợp. Lựa chọn phụ thuộc yêu cầu thu hồi, phân tán hệ thống, độ trễ, khả năng bảo vệ token và chính sách kiểm tra.

## 7. Refresh token và ID token có đường tin cậy khác

### 7.1. Refresh token: client gửi về Authorization Server

Refresh token được AS cấp cho client đủ điều kiện, nhằm đổi lấy access token mới khi token cũ hết hạn. Client gửi refresh token đến **token endpoint của AS**, theo cách phù hợp loại client và chính sách của AS. **Resource Server không nên chấp nhận refresh token như access token.**

~~~mermaid
sequenceDiagram
    autonumber
    participant C as Client
    participant AS as Authorization Server
    participant API as Resource Server
    C->>AS: Refresh token grant (+ xác thực client nếu áp dụng)
    AS->>AS: Kiểm refresh token, client, phiên và chính sách
    AS-->>C: Access token mới (+ refresh token xoay vòng nếu áp dụng)
    C->>API: Bearer access token mới
    API-->>C: Kết quả sau khi xác minh access token
~~~

Vì refresh token thường sống lâu hơn access token, cần bảo vệ nghiêm ngặt: lưu ở vị trí an toàn phù hợp môi trường chạy, hạn chế lộ qua JavaScript/XSS hoặc log, và sử dụng **refresh token rotation** hay **sender-constraining** theo mô hình client. Nếu bật rotation, lần đổi token hợp lệ có thể vô hiệu hóa refresh token cũ; tái sử dụng token đã xoay vòng là tín hiệu nghi ngờ đánh cắp và có thể dẫn tới thu hồi cả nhóm token.

### 7.2. ID token: OpenID Provider gửi cho đúng client

ID token là token OIDC (thông thường JWT) mô tả sự kiện xác thực người dùng. Claim `aud` của nó thường hướng đến **OIDC client_id**, chẳng hạn `shop-web`, chứ không phải `orders-api`. Client cần xác minh đúng issuer, chữ ký, audience, thời gian; tùy luồng và ngữ cảnh OIDC còn cần kiểm `nonce`, `azp` và các điều kiện liên quan.

**Sai lầm phổ biến:** API nhận ID token vì thấy `sub` là người dùng thật và chữ ký của OP hợp lệ. Đây là nhầm **token dành cho client** thành **token ủy quyền cho API**; API phải yêu cầu access token phù hợp. Việc thêm `role` vào ID token cũng không biến nó thành access token.

## 8. Tình huống thực tế để kiểm tra ranh giới tin cậy

Giả sử API đơn hàng cần một access token từ `https://auth.example.com`, audience `orders-api` và scope `orders:read`.

| Tình huống | Quyết định | Giải thích |
|---|---|---|
| Đúng chữ ký, `iss`, `aud` và thời hạn; có `orders:read`; người dùng được xem đơn | **Cho phép** | Đủ điều kiện xác minh và phân quyền. |
| JWT ký đúng bởi issuer khác | **Từ chối** | Chữ ký hợp lệ với nguồn **không được API tin**. |
| JWT từ issuer đã tin nhưng `aud: payments-api` | **Từ chối** | Token dành cho API thanh toán, không dành cho đơn hàng. |
| Payload đổi `scope` thành `orders:admin` mà không ký lại | **Từ chối** | Xác minh chữ ký thất bại. |
| Token hết hạn nhưng từng có scope hợp lệ | **Từ chối** | Quyền cũ không kéo dài hiệu lực token. |
| Token còn hạn, chỉ có `orders:read` nhưng gọi `DELETE /orders/42` | **Từ chối** | Không đủ scope/hành động được cấp. |
| Token có scope đọc đơn nhưng đơn 42 thuộc người dùng khác | **Từ chối** | Kiểm quyền ở mức tài nguyên thất bại. |
| Client gửi ID token hoặc refresh token cho API | **Từ chối** | Sai mục đích và sai đối tượng nhận token. |
| JWT còn hạn, chữ ký hợp lệ nhưng người dùng vừa bị khóa | **Theo chính sách kiểm tra trạng thái** | Chữ ký JWT không tự biết việc khóa tài khoản; cần cơ chế trạng thái hoặc tuổi thọ token ngắn. |
| Access token bị đánh cắp và kẻ tấn công gửi lại nguyên vẹn | **Có thể vượt qua kiểm chữ ký** | Bearer token chứng minh người *cầm* token, không chứng minh ai là người cầm; cần phòng chống đánh cắp/phát lại. |

### Trường hợp nhiều tenant

Nếu API phục vụ nhiều tổ chức, một token có `aud` đúng vẫn chưa đủ. API cần bảo đảm issuer/tenant trong token phù hợp tenant được truy cập, và chủ thể có quan hệ được phép với dữ liệu tổ chức đó. Không chấp nhận việc client tự gửi `tenantId` trong URL rồi coi claim “đăng nhập hợp lệ” là đủ quyền truy cập tenant đó.

### Trường hợp API Gateway xác minh token

Một gateway có thể chặn request không hợp lệ trước khi tới microservice. Tuy nhiên, nếu service phía sau đọc các header `X-User-Id`/`X-Scope` do gateway gắn, phải có cách bảo đảm client bên ngoài **không thể tự đặt header đáng tin cậy**, kết nối nội bộ được xác thực và service chỉ tin gateway đã chỉ định. Các phép kiểm ownership, tenant và quyền nghiệp vụ thường vẫn thuộc về service sở hữu tài nguyên.

## 9. Thu hồi, hết hạn và chống phát lại

**Hết hạn (expiration)** và **thu hồi (revocation)** là hai sự kiện khác nhau:

- `exp` khiến bên xác minh từ chối sau thời điểm hết hạn, nếu đồng hồ và validator hoạt động đúng.
- Thu hồi là quyết định thay đổi trạng thái **trước** khi `exp`. Một JWT tự chứa đã phát hành thường không “biết” điều đó nếu API chỉ kiểm chữ ký và `exp`.
- Một opaque token được introspect có thể phản ánh trạng thái thu hồi sớm hơn; tuy nhiên cache introspection có thể kéo dài thời gian chấp nhận.

Các biện pháp nên kết hợp theo rủi ro:

1. **Access token sống ngắn**, audience và scope tối thiểu: giảm thời gian và phạm vi khai thác khi rò rỉ.
2. **Refresh token được bảo vệ, xoay vòng hoặc ràng buộc với client**: hạn chế khả năng lặp lại việc xin token.
3. **Thu hồi phiên hoặc token**: qua trạng thái ở AS, introspection, danh sách thu hồi/`jti`, token version hoặc cơ chế tương đương nếu yêu cầu vô hiệu hóa sớm.
4. **Sender-constrained access token** (ví dụ mTLS hoặc DPoP, khi kiến trúc hỗ trợ): API xác minh thêm bằng chứng sở hữu khóa của bên gửi. Điều này giảm khả năng dùng lại token bị sao chép đơn thuần, nhưng phải triển khai đúng quy tắc ràng buộc token, kiểm proof, timestamp, request target và chống replay.
5. **Bảo vệ đường truyền và lưu trữ**: luôn HTTPS; không đưa bearer token vào URL, log, analytics hoặc thông báo lỗi; kiểm soát XSS/CSRF và cơ chế lưu trữ theo loại client.
6. **Giới hạn thời gian lệch đồng hồ**: cho phép leeway nhỏ và có chủ đích, không nới thời hạn vô hạn; đồng bộ thời gian máy chủ.

Điểm then chốt: **Bearer token bị đánh cắp vẫn có thể được sử dụng trong thời gian hiệu lực** dù chữ ký hoàn toàn hợp lệ. Xác minh mật mã giúp xác nhận token do ai cấp và nội dung có bị sửa không; nó không tự xác nhận người gửi hiện tại là chủ thể hợp pháp.

## 10. Các lỗi thiết kế thường gặp

| Lỗi | Vì sao nguy hiểm? | Cách xử lý |
|---|---|---|
| Chỉ Base64URL-decode JWT rồi lấy `sub` và `roles` | Bất cứ ai cũng có thể tự tạo payload không ký. | Xác minh chữ ký bằng thư viện đáng tin cậy trước khi dùng claims. |
| Kiểm chữ ký nhưng bỏ `aud` | Token cấp cho hệ thống A có thể bị dùng ở hệ thống B. | Kiểm audience thuộc API hiện tại. |
| Tin URL khóa nằm ngay trong token chưa xác minh | Kẻ tấn công có thể trỏ tới khóa tự tạo. | Chỉ tin issuer/JWKS đã cấu hình hoặc discovery đã ràng buộc. |
| Cho token quyết định thuật toán xác minh | Có thể gây lỗ hổng `none` hoặc nhầm lẫn HMAC/khóa công khai. | Cấu hình whitelist thuật toán và đúng loại khóa. |
| Nhận ID token làm access token | Lẫn bằng chứng đăng nhập của client với quyền gọi API. | Tách validator, audience và token profile. |
| Nhận access token đúng scope nhưng bỏ kiểm ownership | Người dùng có thể đọc/sửa tài nguyên của người khác. | Kiểm quyền tài nguyên cụ thể tại backend. |
| Dùng JWT dài hạn và cho rằng logout sẽ thu hồi ngay | API có thể chấp nhận token cũ tới khi hết hạn. | Định nghĩa chiến lược hết hạn/thu hồi rõ ràng. |
| Ghi bearer token vào log hoặc URL | Lộ token qua hạ tầng quan sát, lịch sử, proxy, referrer. | Redact token, dùng header Authorization qua HTTPS. |
| Service tin mọi header danh tính do request gửi | Kẻ tấn công giả danh người dùng phía sau gateway. | Chặn/ghi đè header ngoài biên và xác thực nguồn gọi nội bộ. |
| Coi `client_credentials` là người dùng đã đăng nhập | Gán sai quyền người dùng cho danh tính máy. | Phân biệt principal của client và end user, cấp quyền tương ứng. |

## 11. Bài thực hành: lập chính sách tin cậy cho API

Giả sử bạn xây dựng API `inventory-api` và nhận access token từ một Authorization Server chung. Hãy viết cấu hình/chính sách theo mẫu:

~~~yaml
resourceServer: inventory-api
trustedIssuer: https://auth.example.com
acceptedAudience: inventory-api
tokenPurpose: access_token
jwtVerification:
  trustedKeys: issuer-managed-jwks
  allowedAlgorithms: [RS256]
  validate: [signature, iss, aud, exp, nbf, token_type]
routes:
  "GET /stock/{id}":
    requiredScope: stock:read
    extraChecks: caller_can_access_warehouse
  "POST /stock/{id}/adjust":
    requiredScope: stock:adjust
    extraChecks: caller_can_adjust_warehouse
~~~

Đây là **mẫu chính sách minh họa**, không phải cấu hình có thể nạp nguyên vẹn vào Spring Security hay một sản phẩm cụ thể. Các kiểm tra thực tế phải dựa trên thư viện và hồ sơ token của issuer.

**Tự trả lời ba câu hỏi:**

1. Token có chữ ký hợp lệ từ AS nhưng `aud` là `billing-api`: API kho có nhận không?  
   **Không.** Audience không phù hợp dù cùng issuer.
2. Token có `aud: inventory-api` và `scope: stock:read`, nhưng người dùng yêu cầu kho khác tổ chức: có cho đọc không?  
   **Không.** Scope không thay kiểm tra quyền trên kho thực tế.
3. Người dùng logout, access JWT còn hạn 10 phút, API chỉ xác minh cục bộ: token chắc chắn bị từ chối ngay không?  
   **Không chắc.** Cần cơ chế thu hồi hoặc kiểm trạng thái bổ sung, hoặc chấp nhận cửa sổ hiệu lực còn lại theo chính sách đã thiết kế.

## 12. Checklist khi triển khai

- [ ] Đã xác định rõ **ai phát hành** từng loại token và **ai là đối tượng nhận**.
- [ ] API chỉ chấp nhận issuer tin cậy, khóa tin cậy, thuật toán cho phép và đúng token profile.
- [ ] API kiểm chữ ký hoặc introspection, `iss`, `aud`, hiệu lực thời gian và các claim bắt buộc.
- [ ] API áp dụng scope/quyền theo endpoint và kiểm tra ownership/tenant ở mức dữ liệu.
- [ ] ID token và refresh token không được dùng làm access token.
- [ ] Đã thiết kế JWKS key rotation, thời gian cache và cách xử lý khi issuer/introspection gặp lỗi.
- [ ] Đã cân nhắc TTL, thu hồi, refresh token rotation, lưu trữ an toàn và bảo vệ token khỏi rò rỉ/phát lại.
- [ ] Có kiểm thử âm tính cho sai issuer, sai audience, sai chữ ký, hết hạn, thiếu quyền, khác tenant và token sai mục đích.
- [ ] Log chỉ chứa thông tin kiểm toán cần thiết (ví dụ mã lỗi, request ID, định danh đã được xử lý an toàn), không chứa nguyên văn token.

**Ghi nhớ:** Authorization Server/OpenID Provider có thẩm quyền **phát hành** token; Resource Server có trách nhiệm **xác minh access token và quyết định quyền truy cập tài nguyên**; OIDC Client xác minh **ID token**; Authorization Server kiểm **refresh token** khi đổi token mới. Mọi quyết định tin cậy đều phải dựa trên nguồn phát hành đã cấu hình, đối tượng nhận, hiệu lực và chính sách quyền cụ thể.

### Tài liệu chuẩn để tra cứu sâu

- **RFC 6749** — The OAuth 2.0 Authorization Framework: các vai trò, grant và access/refresh token.
- **RFC 6750** — OAuth 2.0 Bearer Token Usage: cách sử dụng bearer token và các nguy cơ phổ biến.
- **RFC 7636** — Proof Key for Code Exchange (PKCE).
- **RFC 7662** — OAuth 2.0 Token Introspection.
- **RFC 7519** — JSON Web Token (JWT); **RFC 7517** — JSON Web Key (JWK).
- **RFC 9068** — JWT Profile for OAuth 2.0 Access Tokens.
- **OpenID Connect Core 1.0** — ID token và quy tắc xác minh ID token.
- **RFC 9449** — OAuth 2.0 Demonstrating Proof of Possession (DPoP).
- **RFC 9700** — Best Current Practice for OAuth 2.0 Security.
