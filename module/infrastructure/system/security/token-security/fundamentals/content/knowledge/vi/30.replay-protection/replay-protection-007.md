# Ràng buộc người gửi để chống replay

## 1. Vì sao chỉ kiểm tra token là chưa đủ?

Trong OAuth 2.0 và OpenID Connect (OIDC), một **access token** đại diện cho quyền truy cập mà authorization server đã cấp cho client. Resource server kiểm tra token và quyết định có cho phép gọi API hay không. **Refresh token** giúp client xin access token mới khi access token hết hạn. Cả hai đều là tài sản nhạy cảm: nếu chúng là **bearer token**, bất kỳ bên nào cầm được chuỗi token có thể thử sử dụng nó mà không cần chứng minh mình là bên đã nhận token ban đầu.

Ví dụ: ứng dụng hợp lệ lấy được access token AT và gọi API. Kẻ tấn công đọc được AT từ log, bộ nhớ hoặc một kênh bị xâm nhập rồi tự gửi yêu cầu với AT ấy. Dù AT là **JWT** có chữ ký hợp lệ hay **opaque token** được resource server introspect, nếu server chỉ hỏi “AT còn hiệu lực và có quyền hay không?” thì vẫn có thể chấp nhận lời gọi của kẻ tấn công.

**Sender-constrained token (token ràng buộc với người gửi)** giải quyết một phần vấn đề này: máy chủ cấp token cho một khóa hoặc chứng chỉ cụ thể, sau đó bên dùng token phải **chứng minh quyền sở hữu** khóa/chứng chỉ tương ứng tại thời điểm gửi request. Có token thôi chưa đủ.

Bài học này tập trung vào hai cơ chế OAuth quan trọng:

- **DPoP (Demonstrating Proof of Possession, RFC 9449):** ứng dụng ký một JWT proof bằng khóa riêng cho từng yêu cầu; server đối chiếu khóa công khai trong proof với khóa đã gắn vào token.
- **mTLS certificate-bound token (RFC 8705):** token gắn với chứng chỉ TLS client; server kiểm tra chứng chỉ mà bên gửi đã dùng trong kết nối mutual TLS.

Cả hai đều phục vụ **chống token bị sử dụng lại bởi bên khác**. Chúng bổ sung cho những kiểm tra không thể thiếu khác như issuer, audience, thời hạn, scope, client/phiên, chính sách thu hồi và giới hạn quyền truy cập.

## 2. Bearer token, sender-constrained token và replay khác nhau thế nào?

| Khái niệm | Điều kiện để sử dụng | Điều gì xảy ra nếu lộ chuỗi token? |
|---|---|---|
| Bearer access token | Trình được token hợp lệ | Bên đánh cắp có thể gọi API trong giới hạn quyền và thời hạn token |
| DPoP-bound access token | Có token **và** ký proof bằng đúng khóa riêng | Chỉ lộ token thường không đủ để gọi API |
| Certificate-bound access token (mTLS) | Có token **và** thực hiện TLS client authentication/binding với chứng chỉ khớp | Chỉ lộ token thường không đủ; cần khóa riêng/chứng chỉ tương ứng |
| Bearer refresh token | Gửi được refresh token hợp lệ đến token endpoint, đáp ứng kiểm tra client liên quan | Có thể đổi lấy token mới nếu không bị phát hiện/chặn |
| Sender-constrained refresh token | Có refresh token và chứng minh quyền sở hữu khóa/chứng chỉ đã ràng buộc | Lộ chuỗi refresh token đơn lẻ thường không đủ để làm mới |

**Replay** có nhiều lớp cần phân biệt:

1. **Replay access token:** kẻ tấn công gửi lại access token đã thấy. Sender-constraining khiến chuỗi token đơn lẻ không đủ.
2. **Replay một proof DPoP:** kẻ tấn công gửi lại nguyên JWT proof đã ký. Server phải kiểm tra tính mới của proof bằng thời gian, jti và, khi dùng, server nonce.
3. **Replay refresh token:** refresh token cũ bị dùng lại. Sender-constraining có thể chặn bên không giữ khóa/chứng chỉ; **refresh token rotation** còn giúp phát hiện việc token đã dùng được trình lại khi rotation đang áp dụng.

> Điểm cốt lõi: ràng buộc người gửi chứng minh rằng request đến từ **bên có khả năng sử dụng khóa**, không bảo đảm bên ấy luôn là người dùng hợp pháp hay request là hành động có chủ đích của người dùng. Nếu khóa riêng bị chiếm đoạt hoặc thiết bị bị điều khiển từ xa, kẻ tấn công vẫn có thể tạo proof hợp lệ.

## 3. Mô hình tin cậy: token phải được gắn với khóa bằng cách nào?

Mô hình ràng buộc có ba thành phần:

1. **Authorization server (AS)** kiểm tra bằng chứng sở hữu khóa/chứng chỉ khi cấp token và lưu thông tin ràng buộc.
2. **Client** giữ khóa riêng hoặc chứng chỉ/khóa riêng, dùng nó để chứng minh quyền sở hữu khi đổi token và/hoặc truy cập tài nguyên.
3. **Resource server (RS)** xác thực token theo chính sách OAuth rồi kiểm tra bằng chứng của người gửi có khớp ràng buộc token hay không.

Thông tin ràng buộc thường được biểu diễn qua **confirmation claim (cnf)**:

| Cơ chế | Giá trị ràng buộc thông dụng | Ý nghĩa |
|---|---|---|
| DPoP | cnf.jkt | JWK SHA-256 thumbprint của **khóa công khai** phía client |
| mTLS | cnf[“x5t#S256”] | SHA-256 thumbprint của chứng chỉ X.509 phía client |

Nếu access token là JWT, **cnf** có thể nằm trong các claims đã được AS ký. Nếu là opaque token, RS có thể nhận thông tin ràng buộc qua **introspection** hoặc cơ chế chia sẻ trạng thái tin cậy tương đương. Với refresh token, AS thường lưu ràng buộc trong trạng thái phía máy chủ, bất kể định dạng token.

**Không thể tin một trường cnf do client tự khai báo.** Ràng buộc phải xuất phát từ token hoặc trạng thái do authorization server kiểm soát và được xác thực. Việc có trường cnf trong token cũng chưa tự chặn replay: resource server phải thật sự thực thi bước đối chiếu chứng cứ sở hữu.

~~~mermaid
flowchart LR
    C[Client có khóa riêng K] -->|Bằng chứng sở hữu| AS[Authorization Server]
    AS -->|Token gắn khóa K| C
    C -->|Token và bằng chứng dùng K| RS[Resource Server]
    RS -->|Kiểm tra token, cnf, proof và replay| D{Cho phép?}
    D -->|Hợp lệ| OK[Truy cập tài nguyên]
    D -->|Sai hoặc thiếu| NO[Từ chối]
~~~

## 4. DPoP: chứng minh quyền sở hữu khóa trên từng yêu cầu HTTP

### 4.1. Phát hành token ràng buộc với DPoP

Client tạo cặp khóa bất đối xứng **Kpriv/Kpub**, giữ **Kpriv** bí mật và đặt **Kpub** vào header của DPoP proof JWT. Khi gọi token endpoint, client gửi proof được ký bằng Kpriv. AS kiểm tra chữ ký, yêu cầu HTTP và điều kiện proof; sau đó có thể cấp access token được ràng buộc với **JWK thumbprint** của Kpub.

Ví dụ luồng authorization code grant (lược bỏ những tham số OAuth khác để tập trung vào DPoP):

~~~http
POST /oauth2/token HTTP/1.1
Host: as.example.test
Content-Type: application/x-www-form-urlencoded
DPoP: <JWT_PROOF_SIGNED_BY_CLIENT_PRIVATE_KEY>

grant_type=authorization_code&code=<CODE>&redirect_uri=<REDIRECT_URI>
~~~

~~~json
{
  "access_token": "<ACCESS_TOKEN>",
  "token_type": "DPoP",
  "expires_in": 300,
  "refresh_token": "<REFRESH_TOKEN_IF_ISSUED>"
}
~~~

Giá trị **token_type = DPoP** cho biết access token cần được sử dụng theo cách DPoP thay vì cú pháp Bearer. Để tránh **authorization code injection**, hệ thống còn cần các biện pháp chuẩn như PKCE; trong triển khai hỗ trợ tính năng liên quan, DPoP key có thể được gắn với authorization code ngay từ đầu. Chỉ có proof ở token endpoint không thay thế được các kiểm tra của authorization code flow.

### 4.2. Bên trong một DPoP proof

DPoP proof là JWT được **ký bằng khóa riêng của client**. Ví dụ dưới đây minh họa header và payload **trước khi ký**, không phải token hoàn chỉnh có thể sử dụng:

~~~json
{
  "typ": "dpop+jwt",
  "alg": "ES256",
  "jwk": {
    "kty": "EC",
    "crv": "P-256",
    "x": "<PUBLIC_X>",
    "y": "<PUBLIC_Y>"
  }
}
~~~

~~~json
{
  "jti": "proof-unique-id-123",
  "htm": "GET",
  "htu": "https://api.example.test/v1/orders",
  "iat": 1795400000,
  "ath": "<BASE64URL_SHA256_ACCESS_TOKEN>"
}
~~~

| Thành phần | Vai trò | Lưu ý khi kiểm tra |
|---|---|---|
| typ = dpop+jwt | Phân biệt với JWT loại khác | Không chấp nhận JWT bất kỳ thay cho DPoP proof |
| alg + jwk | Thuật toán và **khóa công khai** dùng xác thực chữ ký | Chỉ chấp nhận thuật toán bất đối xứng được phép; không cho private JWK hoặc alg=none |
| htm | HTTP method | Phải khớp method thực tế của request |
| htu | HTTP URI đích | So khớp URI đích theo RFC 9449; không tính query và fragment |
| iat | Thời điểm phát hành proof | Phải nằm trong khoảng thời gian chấp nhận có giới hạn |
| jti | Mã định danh duy nhất cho **proof** | Dùng chống replay; trùng jti trong phạm vi kiểm tra phải bị từ chối |
| ath | Base64url của SHA-256 trên **access token** | Bắt buộc khi dùng DPoP-bound access token tại RS; gắn proof với đúng token |
| nonce | Giá trị thách thức do server cấp, khi được yêu cầu | Kiểm tra nonce do đúng server liên quan phát hành và còn hợp lệ |

**Phân biệt hai loại “mã định danh”:** jti trong DPoP proof là mã riêng của **mỗi lần tạo proof**; nó không phải jti của access token, refresh token hay session. Gửi một request mới cần proof mới với jti mới, kể cả khi vẫn dùng cùng một access token.

**Giới hạn quan trọng:** htu không bao gồm query string và fragment, còn DPoP proof không tự bảo vệ toàn bộ request body. Vì vậy DPoP không thay HTTPS/TLS, không phải chữ ký toàn vẹn cho mọi byte của HTTP request.

### 4.3. Resource server kiểm tra khi nhận request

Ví dụ client gọi API bằng DPoP-bound access token:

~~~http
GET /v1/orders?limit=10 HTTP/1.1
Host: api.example.test
Authorization: DPoP <ACCESS_TOKEN>
DPoP: <NEW_JWT_PROOF_SIGNED_BY_CLIENT_PRIVATE_KEY>
~~~

Resource server cần thực hiện **hai nhánh xác thực cùng lúc**:

- **Nhánh token:** kiểm tra JWT access token hoặc introspection opaque token; issuer, audience dành cho API, expiration/nbf, scope/quyền, trạng thái thu hồi nếu kiến trúc yêu cầu, và token type/binding.
- **Nhánh proof:** kiểm tra cấu trúc và chữ ký DPoP proof bằng khóa công khai trong header, htm/htu, iat, jti, nonce khi yêu cầu, ath; sau đó tính JWK thumbprint và đối chiếu với **cnf.jkt** đáng tin cậy của access token.

Nếu proof được ký đúng nhưng từ **một cặp khóa khác** với khóa ràng buộc token, request vẫn **bị từ chối**. Nếu token hợp lệ nhưng không có proof, request cũng **bị từ chối**. Tránh vô tình cho phép fallback sang Bearer đối với token mà AS đã yêu cầu DPoP.

~~~mermaid
sequenceDiagram
    participant C as Client giữ Kpriv
    participant AS as Authorization Server
    participant RS as Resource Server
    C->>AS: Token request + DPoP proof ký bởi Kpriv
    AS->>AS: Xác minh proof, lấy thumbprint Kpub
    AS-->>C: Access token có binding jkt
    C->>RS: Authorization: DPoP AT + proof mới
    RS->>RS: Kiểm tra claims, signature, htm/htu/iat/ath
    RS->>RS: So cnf.jkt với Kpub; chống replay jti
    RS-->>C: Kết quả API nếu hợp lệ
~~~

### 4.4. Kiểm tra replay của chính DPoP proof

Vì kẻ tấn công có thể sao chép **cả access token lẫn proof đã ký** từ một request, kiểm tra chữ ký và cnf.jkt **chưa đủ**. Server phải ngăn một proof cũ được sử dụng nhiều lần trong thời gian còn chấp nhận:

1. Giới hạn tuổi proof qua **iat**; đồng bộ thời gian và áp dụng sai số đồng hồ hợp lý.
2. Theo dõi **jti** của proof đã chấp nhận, gắn với khóa/proof context thích hợp, ví dụ thumbprint khóa + jti, trong khoảng thời gian đủ dài.
3. Dùng thao tác đánh dấu đã dùng **nguyên tử** (set-if-absent hoặc unique constraint) để hai instance không cùng chấp nhận một proof.
4. Nếu server yêu cầu **DPoP nonce**, phải kiểm tra proof chứa nonce hợp lệ được server cấp. Một nonce không tự thay thế kiểm tra jti.
5. Chỉ chấp nhận proof khi mọi điều kiện khác (chữ ký, method, URI, token binding) hợp lệ; có chính sách rõ ràng khi kho chống replay không sẵn sàng.

Ví dụ: cùng một DPoP proof P1 cho GET /v1/orders được gửi đến hai instance API cùng lúc. Nếu mỗi instance dùng cache riêng và đều thấy jti chưa xuất hiện, cả hai có thể cho qua. Hệ thống phân tán cần lưu trạng thái replay với **tính nhất quán đủ mạnh** trong phạm vi các instance cùng chấp nhận proof, hoặc thiết kế ràng buộc nonce/cơ chế chống replay tương đương theo chuẩn và chính sách được xác minh.

~~~text
replayKey = (issuer/resource-context, JWK-thumbprint, proof.jti)

if proof.iat không nằm trong cửa sổ thời gian hợp lệ:
    reject
if không kiểm tra được nonce bắt buộc:
    reject
if !replayStore.putIfAbsent(replayKey, TTL_phu_hop):
    reject  // proof jti đã được chấp nhận trước đó

accept proof sau khi các kiểm tra token, signature và binding đã PASS
~~~

Giả mã chỉ thể hiện phần chống replay; trong triển khai thực tế cần quản lý thứ tự xác minh để tránh yêu cầu không hợp lệ làm cạn bộ nhớ cache hoặc chiếm jti của request hợp lệ. **TTL lưu jti phải bao phủ toàn bộ khoảng mà proof có thể còn được chấp nhận**, kể cả sai số đồng hồ; nếu TTL quá ngắn, một proof có thể được phát lại sau khi bản ghi jti biến mất mà iat vẫn hợp lệ.

### 4.5. DPoP nonce dùng để làm gì?

Một server có thể yêu cầu client dùng nonce do server cấp để hạn chế khả năng proof được tạo quá sớm, giảm ảnh hưởng của lệch đồng hồ hoặc tăng tính mới của proof. Khi server phản hồi một thách thức yêu cầu nonce, client cần **tạo proof mới** chứa nonce nhận được rồi gửi lại request theo chính sách retry. Authorization server và resource server có thể có **nonce riêng**; không tự giả định nonce của AS dùng được ở RS.

Nonce không phải khóa riêng. Một bên có cả token và quyền ký proof vẫn có thể đáp ứng nonce challenge; server không được coi nonce như bằng chứng xác thực thay cho chữ ký và token binding.

## 5. mTLS certificate-bound token: ràng buộc vào kết nối TLS

Với **mutual TLS**, cả client và server đều tham gia xác thực qua TLS; client trình chứng chỉ và chứng minh quyền kiểm soát khóa riêng tương ứng trong quá trình handshake. Authorization server có thể cấp access token chứa **cnf.x5t#S256** ứng với thumbprint của chứng chỉ client. Khi client mang token đến RS qua mTLS, RS so thumbprint chứng chỉ đã dùng trên kết nối với giá trị ràng buộc.

~~~mermaid
sequenceDiagram
    participant C as Client có chứng chỉ và khóa riêng
    participant AS as Authorization Server
    participant RS as Resource Server
    C->>AS: Kết nối mTLS + token request
    AS->>AS: Xác minh chứng chỉ và thông tin ràng buộc
    AS-->>C: Access token có cnf.x5t#S256
    C->>RS: Kết nối mTLS + access token
    RS->>RS: Xác minh token và chứng chỉ tại TLS
    RS->>RS: So thumbprint TLS certificate với cnf
    RS-->>C: Cho phép nếu mọi kiểm tra hợp lệ
~~~

Cần phân biệt:

- **mTLS client authentication:** cách client được xác thực với authorization server bằng chứng chỉ, tùy cấu hình và kiểu client.
- **Certificate-bound access token:** cách một access token chỉ dùng được khi trình cùng chứng chỉ/khóa thích hợp tại resource server.

Hai chức năng có thể đi cùng nhưng **không tự động tương đương**. Việc token endpoint dùng mTLS **không bảo đảm** resource server đã kiểm tra cnf khi truy cập API.

Đặc biệt với kiến trúc **API gateway hoặc reverse proxy** kết thúc TLS, service phía sau thường không trực tiếp thấy chứng chỉ client. Gateway cần kiểm tra mTLS và truyền danh tính/chứng chỉ đã xác thực qua **kênh nội bộ đáng tin cậy**; service không được tin những header như X-Client-Cert do người gọi bên ngoài tự đặt. Nếu không có cơ chế truyền/đối chiếu đáng tin cậy, ràng buộc ở token có thể bị vô hiệu hóa tại resource server.

Việc gia hạn/thay chứng chỉ có thể thay đổi thumbprint. Access token cũ được ràng buộc với chứng chỉ cũ có thể không sử dụng được bằng chứng chỉ mới. Hệ thống phải hoạch định cấp lại token, triển khai chứng chỉ và thu hồi an toàn, thay vì bỏ kiểm tra thumbprint để tránh gián đoạn.

## 6. DPoP và mTLS: chọn cơ chế phù hợp

| Tiêu chí | DPoP | mTLS certificate-bound |
|---|---|---|
| Bằng chứng sở hữu | JWT proof ký bằng khóa riêng, gửi trong HTTP header | Chứng minh sở hữu khóa riêng khi bắt tay TLS |
| Ràng buộc thường gặp | JWK thumbprint cnf.jkt | Chứng chỉ thumbprint cnf.x5t#S256 |
| Hoạt động phổ biến | Public client, browser/native app hoặc môi trường khó quản lý mTLS end-to-end | Backend-to-backend, hạ tầng quản lý chứng chỉ |
| Chống replay bổ sung | iat, jti, nonce và kho ghi nhận proof đã dùng | Phụ thuộc kiểm tra mTLS trên từng kết nối; không có DPoP proof jti |
| Hạ tầng cần quản lý | Khóa client, bộ kiểm tra proof, replay store, nonce nếu dùng | PKI/chứng chỉ, vòng đời chứng chỉ, cấu hình TLS/gateway |
| Rủi ro triển khai | Bỏ ath hoặc cnf, cache jti không đồng bộ, htu sai | TLS termination làm mất chứng cứ, không kiểm tra cnf, cert rotation |

Không có cơ chế nào giải quyết hết mọi bài toán. Hãy chọn dựa trên kiểu client, nơi quản lý khóa, đường truyền đến RS, khả năng triển khai kiểm tra tại mọi điểm vào và yêu cầu vận hành.

## 7. Ràng buộc refresh token và quan hệ với rotation

Refresh token đặc biệt nhạy cảm vì cho phép client tiếp tục lấy access token mới trong thời gian dài. Theo **OAuth 2.0 Security Best Current Practice (RFC 9700)**, refresh token được cấp cho **public client** cần được bảo vệ bằng **sender-constraining hoặc refresh token rotation** nhằm ngăn/phát hiện việc sử dụng token bị lộ.

Hai cơ chế có mục tiêu bổ sung:

- **Sender-constraining** chặn việc đổi refresh token khi bên gọi không chứng minh được quyền sở hữu khóa/chứng chỉ đã ràng buộc.
- **Rotation** cấp refresh token mới mỗi lần sử dụng và vô hiệu hóa token cũ; khi token cũ được trình lại, AS có thể phát hiện reuse thông qua trạng thái token family.

Ví dụ:

~~~text
Phiên S: RT0 gắn với khóa K
Client + Kpriv sử dụng RT0 ---> RT1 gắn với K

Bên tấn công lấy được RT1, không có Kpriv:
  gửi RT1 + proof bằng khóa K2 ---> từ chối do binding mismatch

Bên tấn công lấy được cả RT0 và Kpriv:
  có thể tạo proof hợp lệ ---> sender-constraining đơn lẻ không đủ
  rotation + trạng thái USED/token family hỗ trợ phát hiện reuse
~~~

Nếu refresh token được ràng buộc bằng DPoP, token endpoint phải kiểm tra proof ký bởi **cùng khóa đã ràng buộc với refresh token** khi xử lý refresh grant. Proof tại token endpoint có **htm/htu** tương ứng token endpoint; trường **ath** là thành phần cần cho access token khi gọi resource server, không nên tự áp dụng công thức ath của access token cho refresh token. Nếu refresh token ràng buộc mTLS, AS kiểm tra chứng chỉ client đang dùng khớp binding đã lưu.

Token mới phải tiếp tục duy trì ràng buộc đúng với khóa/chứng chỉ được chính sách cho phép. Không được đổi một refresh token đã ràng buộc sang bearer refresh token chỉ vì client không gửi bằng chứng sở hữu trong lần refresh tiếp theo.

**Khi client mất khóa riêng**, ví dụ ứng dụng được cài lại hoặc khóa bị xóa, refresh token gắn với khóa đó thường không thể tiếp tục sử dụng. Quy trình khôi phục hợp lệ là thực hiện lại authorization/đăng nhập hoặc quy trình rebind có xác thực mạnh theo chính sách. Tránh cho client tự khai “khóa cũ đã mất” để đổi token sang khóa khác mà không chứng minh lại quyền.

## 8. Thuật toán kiểm tra phía resource server

Giả mã dưới đây mô tả pipeline cần thiết khi triển khai **DPoP-bound access token** trong một dịch vụ Java. Đây là thuật toán hướng dẫn, không phải API có thể dán chạy ngay:

~~~text
authorizeHttpRequest(req):
    token = requireAuthorizationHeaderWithScheme("DPoP")
    claims = verifyJwtOrIntrospect(token)

    require claims.active
    require validIssuer(claims.iss)
    require validAudience(claims.aud, THIS_RESOURCE_SERVER)
    require validLifetime(claims.exp, claims.nbf)
    require sufficientScopesAndPermissions(claims, req)
    require claims.cnf.jkt exists

    proof = parseDpopHeader(req.header("DPoP"))
    require proof.header.typ == "dpop+jwt"
    require allowedAsymmetricAlgorithm(proof.header.alg)
    require isPublicJwk(proof.header.jwk)
    require verifySignature(proof, proof.header.jwk)

    require proof.htm == req.method
    require canonicalHtu(proof.htu) == canonicalTargetUriWithoutQuery(req)
    require proof.iat within acceptedTimeWindow
    require proof.ath == base64url(sha256(asciiBytes(token)))
    require proof.nonce valid if resource server issued a nonce challenge

    keyThumbprint = jwkSha256Thumbprint(proof.header.jwk)
    require constantTimeEqual(keyThumbprint, claims.cnf.jkt)

    require replayStore.markIfNew(
        key = (THIS_RESOURCE_SERVER, keyThumbprint, proof.jti),
        ttl = fullProofAcceptanceWindow
    )

    return ALLOW
~~~

Các kiểm tra phải được thực hiện trên **giá trị request thực sự đến điểm bảo vệ**. Nếu gateway viết lại host/scheme/path, cần cấu hình chuẩn hóa URI rõ ràng và chỉ tin thông tin forwarding từ proxy đáng tin cậy; nếu không, htu có thể bị kiểm tra sai hoặc bị lợi dụng.

Trong Java/Spring Security, khả năng xác thực JWT/OAuth scope thông thường **không có nghĩa** hệ thống đã thực thi toàn bộ kiểm tra DPoP proof, cnf binding và replay. Cần xác minh chính xác hành vi của thư viện/phần mở rộng đang dùng; các điểm bảo vệ trong gateway, filter chain và service nội bộ phải thống nhất.

Với **opaque access token**, giá trị cnf cần đến từ kết quả introspection đáng tin cậy. Không được bỏ qua việc ràng buộc chỉ vì RS không tự giải mã được token.

## 9. Các kiểu tấn công và giới hạn bảo vệ

| Tình huống | Kết quả kỳ vọng |
|---|---|
| Kẻ tấn công chỉ có access token DPoP-bound | Bị từ chối vì không ký proof bằng khóa đã ràng buộc |
| Kẻ tấn công có token và proof P1 đã bị dùng | Bị từ chối do jti P1 đã ghi nhận |
| Kẻ tấn công có token và proof P1 chưa đến RS lần nào | Có thể xảy ra tranh đua gửi trước; DPoP không chứng minh “ý định người dùng” |
| Kẻ tấn công có cả token lẫn khóa riêng | Có thể tạo proof mới; cần phát hiện xâm nhập, thu hồi, bảo vệ khóa và giới hạn quyền |
| XSS chạy mã trong ứng dụng web có khóa WebCrypto không xuất được | Có thể vẫn lạm dụng ứng dụng để ký proof/gửi request dù không xuất được khóa |
| Proof ký cho GET /v1/orders được dùng cho POST /v1/orders | Bị từ chối vì htm sai |
| Proof ký cho api.example.test được dùng cho api.other.test | Bị từ chối vì htu sai |
| Proof dùng access token AT1 nhưng Authorization chứa AT2 | Bị từ chối vì ath không khớp |
| Gateway mất thông tin chứng chỉ mTLS hoặc tin header người dùng tự đặt | Có nguy cơ phá vỡ cơ chế binding; phải sửa kiến trúc trust |
| AS/RS kiểm tra chữ ký JWT token nhưng bỏ cnf | Token bị đối xử như bearer, mất tác dụng ràng buộc |

DPoP bảo vệ tốt trước trường hợp **lộ token nhưng chưa lộ khóa riêng**. Nó không làm request an toàn tuyệt đối khi máy client bị chiếm quyền, khóa bị lộ hoặc một request hợp lệ đã ký bị lấy cắp trước khi tới RS. mTLS cũng có giới hạn tương tự nếu chứng chỉ/khóa riêng bị lộ hay bị sử dụng trái phép.

## 10. Bảo vệ khóa và vận hành

### 10.1. Quản lý khóa của client

- Tạo khóa bằng bộ sinh ngẫu nhiên mật mã và thuật toán bất đối xứng được hỗ trợ; khóa riêng **không được nằm trong DPoP proof JWT**.
- Trên thiết bị di động, ưu tiên Android Keystore/iOS Keychain hoặc phần cứng bảo vệ khóa khi phù hợp. Trên web, có thể dùng WebCrypto với khóa không xuất được, nhưng vẫn phải chống XSS và các lệnh ký bị lạm dụng.
- Với backend, lưu khóa riêng/chứng chỉ trong keystore, secret manager, KMS/HSM hoặc giải pháp quản lý khóa tương xứng; giới hạn quyền truy cập và nhật ký thao tác.
- Định nghĩa vòng đời khóa: tạo, cấp token, lưu, đổi khóa, khôi phục, thu hồi và mất thiết bị. Đổi khóa có thể đòi hỏi **cấp lại token có binding mới**.
- Không ghi raw token, private JWK, dữ liệu ký nhạy cảm hoặc nguyên HTTP Authorization/DPoP header vào log. Nếu cần forensic, lưu fingerprint/hash và metadata theo chính sách.

### 10.2. Trạng thái chống replay và logging

Các dữ liệu vận hành nên thu thập: client_id, issuer, resource identifier, loại token, binding type, key thumbprint rút gọn hoặc hash, request ID, thời điểm, lý do từ chối, tỷ lệ nonce challenge và tình trạng replay store. Không lưu secret nguyên văn.

Cần giám sát:

- **dpop_proof_replayed**: jti/proof đã được dùng.
- **dpop_binding_mismatch**: khóa ký proof khác cnf.jkt.
- **dpop_ath_mismatch** hoặc **dpop_htu_htm_mismatch**: proof không khớp token hoặc request.
- **mtls_certificate_binding_mismatch**: chứng chỉ khác cnf của token.
- **dpop_nonce_required/invalid** và lỗi kho replay ở hệ thống nhiều instance.

Lỗi binding cần trả về lỗi xác thực/ủy quyền thích hợp theo OAuth/DPoP; không đưa thumbprint đầy đủ, nội dung token hoặc cấu trúc nội bộ cho bên gọi. Nếu cơ chế kiểm tra proof, replay hay mTLS gặp lỗi hạ tầng, API bảo vệ không nên âm thầm hạ cấp về xác thực Bearer.

### 10.3. Bộ kịch bản kiểm thử thiết yếu

1. **Hợp lệ:** token ràng buộc khóa K1, proof ký bởi K1, method/URI/ath chính xác → được phép nếu claims/scope phù hợp.
2. **Đổi khóa:** proof ký bởi K2 dù token ràng buộc K1 → bị từ chối.
3. **Thiếu proof:** gửi token mà không có DPoP header → bị từ chối.
4. **Dùng lại proof:** gửi lại cùng jti trong khoảng chấp nhận → bị từ chối.
5. **Đồng thời:** hai instance nhận cùng proof/jti → tối đa một lần được chấp nhận.
6. **Sai method/URI:** htm hoặc htu khác request → bị từ chối.
7. **Sai access token:** ath không tương ứng token đang trình → bị từ chối.
8. **Thời gian và nonce:** iat quá cũ/tương lai quá xa hoặc nonce sai khi server yêu cầu → bị từ chối.
9. **JWT/opaque:** cả hai đường xác thực token đều truy xuất và thực thi binding đúng.
10. **Refresh grant:** sender-constrained refresh token từ K1 không đổi được bằng K2; rotation nếu bật vẫn giữ binding qua token mới.
11. **mTLS:** cùng access token dùng đúng chứng chỉ được chấp nhận; chứng chỉ khác hoặc chứng cứ bị mất tại proxy bị từ chối.
12. **Token cơ bản:** token sai issuer, audience, exp, scope hoặc bị thu hồi không được qua chỉ vì proof/chứng chỉ hợp lệ.

Khi kiểm thử, hãy dùng cả trường hợp replay qua **nhiều node** và **khởi động lại dịch vụ**, để xác minh cache hoặc datastore thực sự duy trì khả năng chặn theo cửa sổ thời gian yêu cầu.

## 11. Những hiểu nhầm thường gặp

**“Ký DPoP proof rồi thì không cần xác thực access token.”** Sai. DPoP chứng minh quyền sở hữu khóa; token vẫn phải hợp lệ, đúng audience, scope và chính sách cấp quyền.

**“JWT access token có chữ ký đã đủ chống replay.”** Sai. Chữ ký JWT không buộc người gửi phải có khóa riêng của client và không xác nhận proof chưa được dùng.

**“Có cnf trong JWT nghĩa là đã an toàn.”** Sai. Resource server phải đối chiếu cnf với bằng chứng quyền sở hữu tại mỗi điểm sử dụng.

**“Có iat là không cần jti/replay cache.”** Sai. Trong thời gian iat còn được chấp nhận, proof có thể bị gửi nhiều lần nếu không kiểm tra reuse thích hợp.

**“Nonce thay thế mọi kiểm tra replay.”** Sai. Nonce chỉ là một thành phần tăng tính mới; server vẫn cần kiểm tra các điều kiện proof, ràng buộc token và chống reuse theo mô hình triển khai.

**“Khóa không xuất được đồng nghĩa ứng dụng không thể bị lạm dụng.”** Sai. Mã độc hoặc XSS có thể yêu cầu ứng dụng ký request khi nó đang hoạt động.

**“mTLS client authentication tự động làm mọi token thành certificate-bound.”** Sai. AS phải cấp binding và RS phải kiểm tra binding với chứng chỉ của kết nối thực tế.

## 12. Tự kiểm tra

1. Vì sao JWT access token có chữ ký hợp lệ vẫn có thể bị replay ở resource server?
2. Khác biệt giữa thông tin **cnf.jkt** của access token và **jwk** của một DPoP proof là gì?
3. Trường **ath** đóng vai trò nào khi access token được gửi đến resource server?
4. Tại sao phải có **jti** và kho chống replay nếu DPoP proof đã có **iat**?
5. Vì sao kết thúc mTLS tại reverse proxy làm phát sinh yêu cầu bảo vệ thông tin chứng chỉ khi chuyển xuống service?
6. Sender-constraining refresh token bổ sung gì cho refresh token rotation?
7. Nếu client mất khóa K1 nhưng vẫn giữ token ràng buộc với K1, tại sao không thể chỉ dùng khóa K2 để refresh?
8. Khi một access token bị đánh cắp cùng với khóa riêng tương ứng, còn những biện pháp giới hạn tác động nào?

**Ghi nhớ:** Chống replay bằng ràng buộc người gửi cần cả **token hợp lệ**, **binding đáng tin cậy**, **bằng chứng sở hữu khóa/chứng chỉ ở thời điểm sử dụng** và **kiểm tra tính mới của proof khi cơ chế yêu cầu**. DPoP, mTLS và refresh token rotation có các mục tiêu bổ sung, cần kết hợp theo mô hình tin cậy của hệ thống.

## Tài liệu tham khảo

- **RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP):** DPoP proof, các claims htm/htu/iat/jti/ath, nonce, DPoP token và kiểm tra replay.
- **RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens:** xác thực client bằng mTLS và cnf.x5t#S256.
- **RFC 9700 — Best Current Practice for OAuth 2.0 Security:** bảo vệ access token/refresh token, sender-constraining và rotation.
- **RFC 7800 — Proof-of-Possession Key Semantics for JSON Web Tokens (JWTs):** định nghĩa confirmation claim (cnf).
- **RFC 7662 — OAuth 2.0 Token Introspection:** lấy metadata tin cậy của token opaque.
- **RFC 7638 — JSON Web Key (JWK) Thumbprint:** cách tính thumbprint khóa công khai để đối chiếu binding.

