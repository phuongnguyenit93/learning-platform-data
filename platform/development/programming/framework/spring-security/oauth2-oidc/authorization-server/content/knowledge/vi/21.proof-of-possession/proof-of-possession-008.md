# Phối hợp với Resource Server để xác minh proof và token binding

Access token dạng **Bearer** hoạt động theo nguyên tắc: bất kỳ bên nào giữ được token đều có thể gửi token đó đến API. Điều này thuận tiện, nhưng tạo rủi ro lớn nếu access token bị lộ qua log, thiết bị, proxy, trình duyệt hoặc một hệ thống trung gian. **Demonstrating Proof of Possession (DPoP, RFC 9449)** bổ sung bằng chứng mật mã để ràng buộc access token với một cặp khóa của client. Khi gọi API, client phải vừa gửi access token vừa chứng minh đang sở hữu private key tương ứng.

Trong kiến trúc đó, **Authorization Server (AS)** chịu trách nhiệm xác minh DPoP proof khi cấp token và gắn public-key thumbprint vào token. **Resource Server (RS)** phải xác minh proof của từng request, kiểm tra access token được ràng buộc với đúng public key, đối chiếu proof với HTTP request hiện tại và ngăn proof bị replay. Hai bên phải dùng cùng một hợp đồng token binding; nếu AS phát token DPoP-bound nhưng RS chỉ xử lý Bearer token, cơ chế bảo vệ không hoàn chỉnh.

Bài học thuộc chương **DPoP** của module **SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER**. Nội dung hướng dẫn thiết kế, cấu hình, bảo mật, kiểm thử và vận hành OAuth 2.0/OpenID Connect Authorization Server với Spring Security, Spring Authorization Server và Spring Boot, tập trung vào **phối hợp với Resource Server để xác minh proof và token binding**.

> **Nguyên tắc quan trọng:** DPoP proof hợp lệ chỉ chứng minh request được ký bởi private key tương ứng. Resource Server còn phải xác minh access token, xác minh token đã bind với public key đó, đối chiếu ath, htm, htu, thời gian, nonce/replay và sau cùng mới áp dụng scope cùng quyền nghiệp vụ.

## 1. DPoP giải quyết vấn đề gì?

Giả sử orders-api nhận một Bearer access token. Nếu token bị sao chép từ log hoặc máy khách, kẻ tấn công có thể gửi token từ một máy khác cho đến khi token hết hạn hoặc bị thu hồi. RS không có bằng chứng cho biết caller đang giữ token có phải đúng client đã được cấp hay không.

DPoP thêm một cặp khóa do client quản lý:

- **Private key:** client giữ và dùng để ký từng DPoP proof; không gửi private key đến AS hoặc RS.
- **Public key:** client đưa vào JOSE header của proof dưới JWK public; AS dùng nó để ràng buộc token.
- **Token binding:** AS lưu dấu vân tay public key trong access token hoặc metadata introspection.
- **Proof theo request:** client ký proof mới cho mỗi HTTP request đến token endpoint hoặc protected resource.

Khi một access token bị đánh cắp nhưng private key không bị đánh cắp cùng, bên khác không thể tạo proof hợp lệ với public key đã bind. DPoP vì vậy giảm khả năng tái sử dụng token bị lộ theo kiểu bearer.

### 1.1. DPoP là sender-constraining ở tầng ứng dụng

DPoP là cơ chế **application-level sender constraint**. Nó không thay thế TLS, không mã hóa request body, không xác thực người dùng và không thay thế authorization tại API.

| Cơ chế | Điều được chứng minh/ràng buộc |
|---|---|
| Bearer access token | Người gọi đang sở hữu chuỗi token |
| DPoP | Người gọi có private key tương ứng với public key đã bind vào token và proof khớp request |
| mTLS-bound token (RFC 8705) | Token gắn với chứng chỉ client trong phiên TLS |
| PKCE | Authorization code gắn với code verifier của client |
| OIDC ID Token | Thông tin xác thực người dùng dành cho Relying Party |

DPoP có thể kết hợp với Authorization Code + PKCE, Client Credentials, Refresh Token hoặc grant khác nếu AS hỗ trợ. PKCE và DPoP bảo vệ các ranh giới khác nhau: PKCE bảo vệ authorization code; DPoP ràng buộc access token với key của client.

### 1.2. Những gì DPoP không tự giải quyết

- Không ngăn attacker sử dụng token nếu attacker đồng thời chiếm được private key hoặc có thể yêu cầu thiết bị bị chiếm ký proof.
- Không ngăn XSS độc hại điều khiển một ứng dụng browser có quyền sử dụng khóa, kể cả khi khóa không export được.
- Không tự xác định user, tenant, scope hoặc quyền trên một bản ghi.
- Không ký toàn bộ HTTP body hay mọi header tùy ý; proof ràng buộc method, target URI và access token theo các claim chuẩn.
- Không tự bảo vệ response từ RS.
- Không thay TLS hoặc kiểm soát proxy, DNS, issuer và trust configuration.

## 2. Các thành phần phải phối hợp

Ví dụ có ba thành phần:

- **portal-web:** OAuth2 Client, giữ private DPoP key.
- **identity.example.com:** Spring Authorization Server, xác minh proof khi client yêu cầu token.
- **orders-api:** Spring Security Resource Server, xác minh access token và DPoP proof trên từng request.

| Thành phần | Trách nhiệm DPoP |
|---|---|
| OAuth2 Client | Tạo/giữ key pair, ký proof cho token request và resource request |
| Authorization Server | Xác minh proof tại token endpoint, gắn public-key thumbprint vào access token, trả token_type=DPoP |
| Resource Server | Xác minh access token, proof, thumbprint binding, ath, request method/URI, thời gian và replay |
| Reverse proxy/API gateway | Bảo toàn đúng external URI/method, chỉ cung cấp forwarded headers từ proxy tin cậy |
| Replay store | Ghi nhận proof đã dùng trong cửa sổ hiệu lực, dùng chung giữa các node nếu triển khai cluster |

**AS và RS phải thống nhất token binding format.** Với JWT access token, RFC 9449 định nghĩa cnf.jkt. Với opaque token, AS phải trả thông tin confirmation tương ứng qua introspection hoặc một cơ chế tin cậy đã thỏa thuận.

## 3. Luồng từ cấp token đến gọi Resource Server

~~~mermaid
sequenceDiagram
    autonumber
    participant C as OAuth2 Client
    participant AS as Authorization Server
    participant RS as Resource Server

    Note over C: Tạo key pair K (private giữ tại client)
    C->>AS: POST /oauth2/token + DPoP proof(K public)
    AS->>AS: Verify proof: signature, typ, alg, htm, htu, iat, jti, nonce
    AS->>AS: Tính JWK thumbprint (jkt)
    AS-->>C: access_token + token_type=DPoP
    Note over AS: Token chứa cnf.jkt hoặc binding qua introspection
    C->>RS: Authorization: DPoP AT + DPoP proof(K, ath, htm, htu)
    RS->>RS: Verify access token và đọc cnf.jkt
    RS->>RS: Verify proof JWT bằng public JWK trong proof
    RS->>RS: So sánh proof key thumbprint với cnf.jkt
    RS->>RS: Kiểm tra ath, htm, htu, iat, nonce, jti/replay
    alt Token và proof hợp lệ
        RS-->>C: Xử lý authorization nghiệp vụ và trả response
    else Binding/proof/token không hợp lệ
        RS-->>C: 401 / DPoP challenge hoặc lỗi token
    end
~~~

Điểm quyết định là RS **không chỉ xác minh chữ ký proof**. Nó phải xác minh proof được ký bằng đúng public key đã bind vào access token. Nếu thiếu bước này, một người có token nhưng dùng key pair riêng vẫn có thể tự tạo proof hợp lệ cho key của mình.

## 4. DPoP proof là một JWT riêng

DPoP proof là một JWS/JWT ngắn hạn do client tạo cho từng HTTP request. Header có dạng:

~~~json
{
  "typ": "dpop+jwt",
  "alg": "ES256",
  "jwk": {
    "kty": "EC",
    "crv": "P-256",
    "x": "PUBLIC_X_COORDINATE",
    "y": "PUBLIC_Y_COORDINATE"
  }
}
~~~

Payload minh họa cho request tới Resource Server:

~~~json
{
  "jti": "9f6b6e80-5c0c-4c82-9f17-4e1a3f0a9d01",
  "htm": "GET",
  "htu": "https://orders.example.com/api/orders/123",
  "iat": 1794850000,
  "ath": "BASE64URL_SHA256_OF_ACCESS_TOKEN"
}
~~~

Các giá trị khóa và claim trong ví dụ là placeholder, không phải proof đã ký. Header jwk chứa **public key**; tuyệt đối không chứa private members như RSA d, EC d hoặc symmetric secret. DPoP proof phải dùng chữ ký bất đối xứng được hỗ trợ và được policy cho phép; không chấp nhận alg=none hoặc MAC algorithm.

### 4.1. Ý nghĩa các claim

| Claim | Bắt buộc ở proof? | Vai trò |
|---|---|---|
| jti | Có | ID duy nhất của proof; hỗ trợ replay detection |
| htm | Có | HTTP method mà proof được tạo cho |
| htu | Có | HTTP target URI, bỏ query và fragment |
| iat | Có | Thời điểm tạo proof |
| ath | Khi gửi access token đến protected resource | Hash của access token đang được gửi |
| nonce | Khi server yêu cầu nonce | Giá trị nonce mới nhất do chính server đó cấp |

ath không phải hash của toàn bộ request. Nó là hash của **giá trị access token**. Khi proof chỉ dùng ở token endpoint để xin access token, chưa có access token được gửi cùng request nên ath không được yêu cầu theo quy tắc protected-resource request.

### 4.2. Proof header jwk phải là public JWK

Resource Server cần public key trong proof để xác minh chữ ký, nhưng không được chấp nhận private key material trong JWK:

- RSA public: kty, n, e;
- EC public: kty, crv, x, y;
- OKP public: kty, crv, x.

Từ chối proof chứa private parameters. Không tải khóa từ URL tùy ý trong JWT header và không dùng kid như một trust anchor. Proof tự mang public JWK; RS vẫn phải xác minh chữ ký, thuật toán và binding với token.

### 4.3. typ và alg

- typ phải có giá trị dpop+jwt.
- alg phải là asymmetric signature algorithm đã đăng ký, được implementation hỗ trợ và được policy cho phép.
- Không chấp nhận none.
- Không chấp nhận HMAC/MAC algorithm cho DPoP proof.
- Không cho token header tự ép verifier dùng thuật toán ngoài allowlist.

## 5. Token binding: cnf.jkt

Khi AS xác minh DPoP proof lúc cấp token, nó lấy public JWK trong proof và tính **JWK SHA-256 Thumbprint** theo RFC 7638. Giá trị thumbprint được gắn vào access token dưới claim cnf.jkt.

Ví dụ JWT access token payload:

~~~json
{
  "iss": "https://identity.example.com",
  "sub": "user-42",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "iat": 1794850000,
  "exp": 1794850600,
  "cnf": {
    "jkt": "BASE64URL_SHA256_JWK_THUMBPRINT"
  }
}
~~~

cnf là confirmation claim; jkt xác định public key được dùng để sender-constrain token. Giá trị này là thumbprint của **JWK public**, không phải thumbprint của JWT proof, access token hoặc certificate.

### 5.1. Tính JWK thumbprint

RFC 7638 định nghĩa thumbprint dựa trên một JSON object chuẩn hóa chỉ gồm những member bắt buộc cho loại khóa. Sau khi tạo canonical representation, tính SHA-256 rồi Base64URL encode không padding.

Không lấy JSON JWK tùy ý rồi hash toàn bộ chuỗi nguyên bản: thứ tự member, khoảng trắng hoặc metadata bổ sung có thể làm kết quả khác. Dùng implementation RFC 7638 từ thư viện JOSE đã được kiểm chứng.

### 5.2. RS lấy binding ở đâu?

| Token format | Nguồn binding |
|---|---|
| JWT access token | Claim cnf.jkt sau khi RS xác minh chữ ký, issuer và các claim khác |
| Opaque/reference token | Kết quả introspection đáng tin cậy có cnf.jkt hoặc dữ liệu confirmation theo hợp đồng |

Không lấy cnf.jkt từ token chưa xác minh. Với opaque token, không decode chuỗi token để đoán claims; gọi introspection bằng credential của RS, xác minh active và lấy confirmation metadata từ response.

### 5.3. So sánh binding

~~~text
proofJkt = RFC7638_SHA256_Thumbprint(proof.header.jwk)
tokenJkt = verifiedAccessToken.cnf.jkt

if proofJkt != tokenJkt:
    reject request
~~~

Phải so sánh giá trị đã được parse và canonicalize đúng chuẩn, không so sánh chuỗi JWK JSON thô. Nếu access token không có confirmation binding nhưng request dùng DPoP scheme, không được tự suy ra token đã bind.

## 6. HTTP request tới Resource Server

Một request dùng DPoP-bound access token phải có **hai header**:

~~~http
GET /api/orders/123 HTTP/1.1
Host: orders.example.com
Authorization: DPoP ACCESS_TOKEN_VALUE
DPoP: SIGNED_DPOP_PROOF_JWT
Accept: application/json
~~~

Điểm cần nhớ:

- Authentication scheme trong Authorization là **DPoP**, không phải Bearer.
- Header DPoP chứa proof JWT mới cho request hiện tại.
- Proof phải có ath hash của chính access token đang gửi.
- Proof phải khớp HTTP method và target URI.
- Access token và proof phải bind cùng public key.

### 6.1. Không tráo DPoP và Bearer

Nếu access token được AS trả với token_type=DPoP, client phải gửi bằng scheme DPoP. Không được gửi token đó như Authorization: Bearer rồi mong RS suy ra DPoP proof ở header khác. Tương tự, không thể nâng một Bearer token thông thường thành DPoP-bound chỉ bằng cách thêm một proof header; token phải có confirmation binding do AS cấp.

Một RS có thể hỗ trợ cả Bearer và DPoP, nhưng cần xử lý từng scheme theo đúng loại token. Không để cùng một token DPoP-bound đi qua đường Bearer authentication khi thiếu proof.

## 7. Xác minh ath: proof phải gắn với đúng access token

Với protected resource request, claim ath là:

\[
ath = BASE64URL\_NO\_PADDING(SHA256(ASCII(access\_token)))
\]

Các bước:

1. Lấy đúng chuỗi access token từ Authorization header sau khi parse scheme DPoP.
2. Mã hóa giá trị token bằng ASCII theo RFC 9449.
3. Tính SHA-256 trên bytes đó.
4. Base64URL encode kết quả và bỏ padding.
5. So sánh với claim ath trong proof đã xác minh chữ ký.

### 7.1. Vì sao cần ath?

Giả sử client có hai access token AT-A và AT-B, cùng được bind vào một key pair nhưng đại diện cho quyền hoặc subject khác nhau. Một proof không gắn token có thể bị lấy từ request AT-A rồi thử dùng cùng proof với AT-B. ath ràng buộc proof với **giá trị cụ thể** của access token, giảm nguy cơ token substitution.

ath không thay thế cnf.jkt: hai kiểm tra trả lời hai câu hỏi khác nhau:

| Kiểm tra | Câu hỏi |
|---|---|
| ath | Proof này được tạo cho đúng access token đang gửi không? |
| cnf.jkt ↔ proof JWK thumbprint | Access token có được bind với đúng public key đã ký proof không? |

## 8. Xác minh htm và htu

DPoP proof gắn với HTTP request hiện tại bằng hai claim:

- htm: method, ví dụ GET, POST, PATCH;
- htu: target URI không có query và fragment.

Ví dụ proof được tạo cho:

~~~text
GET https://orders.example.com/api/orders/123
~~~

Proof đó không được dùng cho:

~~~text
POST https://orders.example.com/api/orders/123
GET  https://billing.example.com/api/orders/123
GET  https://orders.example.com/api/orders/456
~~~

RS phải so sánh htm với method của request thực tế và htu với target URI thực tế theo quy tắc URI normalization của RFC 9449/RFC 3986.

### 8.1. Query và fragment không nằm trong htu

htu bỏ query và fragment. Ví dụ:

~~~text
Request URI:
https://orders.example.com/api/orders/123?expand=items#section

DPoP htu:
https://orders.example.com/api/orders/123
~~~

Vì query không được bind bằng htu, không dùng query parameter làm bằng chứng mật mã duy nhất cho một quyết định nhạy cảm. Nếu query chứa resource identifier hoặc điều kiện nghiệp vụ, API vẫn phải thực hiện authorization trên dữ liệu thực tế và kiểm tra quyền tương ứng.

### 8.2. Reverse proxy và external URI

Trong production, RS có thể chạy sau load balancer/API gateway:

~~~text
Client
  -> https://api.example.com/orders/123
  -> ingress terminates TLS
  -> http://orders-service:8080/orders/123
~~~

Client ký htu=https://api.example.com/orders/123, trong khi ứng dụng nội bộ có thể nhìn thấy http://orders-service:8080/orders/123. Nếu hai bên không thống nhất external URI, proof hợp lệ sẽ bị từ chối; nếu RS tin Forwarded/X-Forwarded-* từ bất kỳ caller nào, attacker có thể giả mạo host/scheme.

Thiết kế cần:

- Chỉ chấp nhận forwarded headers từ proxy được tin cậy và có network boundary rõ ràng;
- Chuẩn hóa scheme, host, port và path theo public URI thực tế;
- Không cho client tự đặt host header để điều khiển URI mà RS dùng xác minh;
- Test các trường hợp proxy prefix, context path, port mặc định và URL normalization;
- Không bỏ kiểm tra htu chỉ để sửa lỗi do cấu hình proxy.

### 8.3. URI normalization

RFC 9449 khuyến nghị syntax-based và scheme-based normalization trước khi so sánh htu để giảm false negative. Cần áp dụng quy tắc nhất quán, không tự viết một phép canonicalization tùy tiện có thể làm hai resource khác nhau trở thành cùng URI.

## 9. Kiểm tra thời gian iat

iat cho biết thời điểm tạo proof. RS phải từ chối proof nằm ngoài cửa sổ thời gian chấp nhận. Cửa sổ thường ngắn, tính theo giây hoặc vài phút tùy policy, clock skew và nonce model.

Ví dụ:

~~~text
server time = 12:00:10
proof iat   = 12:00:08  -> có thể hợp lệ trong window
proof iat   = 11:40:00  -> quá cũ, từ chối
proof iat   = 12:30:00  -> tương lai bất hợp lý, từ chối
~~~

Không dùng TTL hàng giờ cho proof. Proof chỉ dành cho một request cụ thể, vì vậy thời hạn ngắn giúp giảm cửa sổ replay.

### 9.1. Đồng bộ thời gian

Các node RS và AS cần đồng bộ đồng hồ. Nếu lệch giờ quá lớn, proof hợp lệ có thể bị từ chối hoặc proof cũ có thể được chấp nhận lâu hơn dự kiến. Dùng NTP/clock monitoring và đặt clock-skew policy có chủ đích.

### 9.2. Nonce server-managed

Nếu cần kiểm soát thời điểm chặt hơn, AS hoặc RS có thể cấp nonce qua response header DPoP-Nonce. Client đưa nonce đó vào claim nonce của proof tiếp theo. Nonce là giá trị opaque do **chính server phát**; nonce của AS không được mang sang RS khác và ngược lại.

## 10. Replay protection: jti, cache và nonce

Một proof đã bị bắt có thể bị phát lại trong cùng endpoint/method và cửa sổ iat. DPoP vì vậy cần cả thời gian ngắn và cơ chế phát hiện reuse.

### 10.1. jti phải đủ ngẫu nhiên và duy nhất

RFC 9449 yêu cầu jti có xác suất trùng không đáng kể trong context và thời gian hiệu lực. Có thể dùng ít nhất 96 bit dữ liệu giả ngẫu nhiên hoặc UUID version 4. Client phải tạo jti mới cho mỗi proof.

### 10.2. RS lưu proof đã dùng

Một triển khai có thể lưu replay key như:

~~~text
replayKey = hash(jkt || jti || request-context)
value     = expiresAt
~~~

Khi nhận proof:

1. Xác minh proof trước khi tin các claims;
2. Tạo replay key từ key identity và jti;
3. Atomic insert nếu key chưa tồn tại;
4. Nếu đã tồn tại trong cửa sổ còn hiệu lực, từ chối replay;
5. Xóa record sau khi proof chắc chắn không còn được chấp nhận.

Việc ghi phải có tính **atomic**. Mẫu if-not-exists-then-put không an toàn khi nhiều request đồng thời cùng kiểm tra.

### 10.3. Multi-node cần replay store dùng chung

Nếu một proof được gửi đến node A rồi replay đến node B, cache in-memory riêng của từng node không biết proof đã dùng. Với cluster, dùng cache/store phân tán có thao tác put-if-absent/atomic và TTL phù hợp.

Spring Security có DPoPProofReplayValidator và DPoPProofReplayValidator.InMemoryCache; tài liệu API nêu rõ cache in-memory chỉ phù hợp một node. Cluster production cần triển khai cache phân tán phù hợp, không chỉ nhân bản application instances.

### 10.4. Nonce và jti không thay thế nhau

Nonce do server cấp giúp server kiểm soát proof phải gắn với một challenge mới. jti nhận diện từng proof để chống dùng lại. Theo RFC, server có thể chấp nhận cùng một nonce trong nhiều proof; uniqueness/replay control vẫn dựa vào jti và thời gian.

## 11. Nonce challenge và retry của client

Khi RS yêu cầu nonce, request không có nonce phù hợp sẽ bị từ chối và trả:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: DPoP error="use_dpop_nonce", error_description="Resource server requires a nonce"
DPoP-Nonce: SERVER_ISSUED_NONCE
Cache-Control: no-store
~~~

Client phải:

1. Đọc nonce từ DPoP-Nonce;
2. Tạo **proof JWT mới**, với jti mới và claim nonce chứa giá trị server vừa cấp;
3. Tính lại ath cho access token đang dùng;
4. Ký proof bằng private key đã bind vào token;
5. Gửi lại request theo giới hạn retry hợp lý.

Không gửi lại nguyên proof cũ rồi chỉ thay header. Nonce không phải OIDC nonce trong ID Token và không phải OAuth state.

### 11.1. Nonce của AS và nonce của RS độc lập

AS cấp nonce cho request đến token endpoint; RS cấp nonce cho protected-resource request. Hai server có thể có state, vòng đời và policy riêng. Client nên lưu nonce theo đúng server/endpoint context và không chia sẻ nonce giữa issuer/resource server khác nhau.

### 11.2. Retry không được nhân đôi thao tác nghiệp vụ

Nếu RS yêu cầu nonce sau khi nhận một request POST có side effect, client phải xử lý retry theo thiết kế idempotency của API. DPoP nonce challenge thường được trả ở giai đoạn xác thực trước authorization/business handler; tuy nhiên client không được giả định mọi lỗi mạng/challenge đều chứng minh nghiệp vụ chưa chạy. Dùng idempotency key phù hợp cho thao tác ghi.

## 12. Quy trình xác minh tại Resource Server

Một pipeline dễ kiểm tra nên chia thành các bước:

1. **Parse authentication scheme:** xác định request đang dùng Authorization: DPoP.
2. **Lấy access token:** không lấy token từ query hoặc body.
3. **Xác minh access token:** chữ ký hoặc introspection, issuer, thời hạn, audience, token active và policy cần thiết.
4. **Lấy confirmation binding:** đọc cnf.jkt từ JWT đã xác minh hoặc introspection result tin cậy.
5. **Parse DPoP proof:** chỉ một header DPoP, một JWT well-formed.
6. **Xác minh proof header:** typ=dpop+jwt, asymmetric alg được cho phép, JWK public-only, signature hợp lệ.
7. **Xác minh request claims:** htm, htu, iat, jti và nonce khi được yêu cầu.
8. **Xác minh token binding:** thumbprint proof JWK bằng cnf.jkt.
9. **Xác minh ath:** hash access token trong request khớp claim ath.
10. **Chống replay:** atomic insert jti vào replay store.
11. **Authorization nghiệp vụ:** scope, role, tenant, resource ownership và policy hiện hành.
12. **Trả response:** không log access token/proof thô; gửi nonce mới nếu policy yêu cầu.

### 12.1. Vì sao xác minh access token và proof là hai việc khác nhau?

| Access token validation | DPoP proof validation |
|---|---|
| Token do issuer tin cậy phát? | Proof do private key tương ứng ký? |
| Token còn hạn/active? | Proof đủ mới và chưa replay? |
| Token dành cho RS này? | Proof dành cho HTTP method/URI này? |
| Token có scope/claims cần thiết? | Proof bind đúng access token và đúng public key? |

Không bỏ qua access-token validation sau khi proof hợp lệ. Một proof được ký đúng nhưng đi cùng access token hết hạn vẫn phải bị từ chối.

### 12.2. DPoP proof không phải identity của user

Public key chứng minh client đang sở hữu key pair, không tự cho biết người dùng cuối là ai. Danh tính user, tenant và quyền vẫn lấy từ access token đã xác minh cùng dữ liệu/policy của ứng dụng. Không dùng thumbprint làm user ID hoặc thay thế sub.

## 13. Spring Security Resource Server

Spring Security đã bổ sung các thành phần DPoP theo từng phiên bản. Cần phân biệt **có class xử lý DPoP** và **có DSL tích hợp đầy đủ vào filter chain**:

| Phiên bản Spring Security | Thành phần DPoP | Cách tích hợp |
|---|---|---|
| **6.5.x** | Có DPoPAuthenticationProvider, DPoPAuthenticationToken, DPoPProofContext, DPoPProofJwtDecoderFactory, DPoPProofReplayValidator | Cần wiring phù hợp phiên bản; không mặc định có DSL Resource Server dPoP(...) |
| **7.1+** | Có thêm DPoPAuthenticationConverter và OAuth2ResourceServerConfigurer.DPoPConfigurer | Có DSL oauth2ResourceServer(...).dPoP(...) để bật DPoP-bound access token support |

Điều này quan trọng khi chọn Spring Boot BOM: không sao chép cấu hình của 7.1 vào dự án đang dùng 6.5 rồi kỳ vọng biên dịch được.

### 13.1. Cấu hình Resource Server trên Spring Security 7.1+

Ví dụ servlet Resource Server dùng JWT:

~~~java
@Bean
SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
    http
        .authorizeHttpRequests(authorize -> authorize
            .requestMatchers("/api/orders/**")
                .hasAuthority("SCOPE_orders.read")
            .anyRequest().authenticated()
        )
        .oauth2ResourceServer(oauth2 -> oauth2
            .jwt(Customizer.withDefaults())
            .dPoP(Customizer.withDefaults())
        );

    return http.build();
}
~~~

Ví dụ cần dependency Resource Server và JOSE, issuer/JWKS configuration và các bean liên quan. jwt(...) cung cấp xác minh access token JWT; dPoP(...) bật xử lý DPoP-bound access token. Kiểm tra cấu hình thực tế của version đang dùng và integration test scheme DPoP, cnf.jkt, ath, htu và replay.

Nếu dùng opaque access token, cấu hình token introspection thay cho JWT decoder và bảo đảm introspection result cung cấp confirmation binding. Không dùng một decoder giả lập cnf.jkt để thay introspection tin cậy.

### 13.2. Cấu hình issuer cho JWT

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://identity.example.com
~~~

Resource Server vẫn phải xác minh iss, signature, exp, nbf, audience và các policy claims theo hệ thống. DPoP không thay những validator đó.

### 13.3. Spring Security 6.5: wiring mức thấp

Ở 6.5, có thể dùng DPoPAuthenticationProvider để xác minh một DPoPAuthenticationToken cùng token authentication manager, nhưng cần tự tích hợp request extraction/filter/entry point phù hợp vì DSL dPoP(...) và DPoPAuthenticationConverter được bổ sung ở các version sau.

Sơ đồ wiring:

~~~text
HttpServletRequest
  -> custom AuthenticationConverter
  -> DPoPAuthenticationToken(accessToken, proof, method, resourceUri)
  -> AuthenticationManager
      -> DPoPAuthenticationProvider
          -> token AuthenticationManager (JWT or opaque)
          -> DPoPProofJwtDecoderFactory
          -> binding + proof validation
  -> SecurityContext
~~~

Đây là kiến trúc wiring, không phải code copy-paste. Khi tự triển khai, cần giữ đúng thứ tự xác minh, xử lý lỗi/nonce, replay cache, response header và không tạo đường Bearer fallback cho DPoP-bound token. Nếu không có kinh nghiệm viết filter authentication, nên nâng lên version có DSL chính thức hoặc dùng implementation đã được đánh giá.

### 13.4. Replay validator của Spring

DPoPProofReplayValidator giúp kiểm soát proof reuse thông qua cache. InMemoryCache phù hợp test hoặc một node; với cluster cần cache phân tán có atomic put-if-absent và TTL phù hợp. Không tạo cache key từ raw access token; chỉ lưu thông tin cần thiết như hash/identifier của proof và thời hạn.

### 13.5. Đừng tự bỏ validator mặc định

Nếu tùy biến DPoPProofJwtDecoderFactory, JwtDecoder hoặc provider:

- Giữ xác minh chữ ký và public JWK;
- Giữ typ, alg, htm, htu, iat, jkt, ath và jti validation;
- Giữ nonce validation khi server yêu cầu;
- Bổ sung custom validation mà không bỏ validator chuẩn;
- Kiểm thử negative cases độc lập để chứng minh từng điều kiện thực sự được thực thi.

## 14. Spring Authorization Server: cấp DPoP-bound access token

Ở phía AS, client gửi DPoP proof trong header khi gọi token endpoint. AS xác minh proof theo RFC 9449; nếu hợp lệ, AS ràng buộc access token được cấp với public key trong proof và trả token_type=DPoP.

Ví dụ:

~~~http
POST /oauth2/token HTTP/1.1
Host: identity.example.com
Content-Type: application/x-www-form-urlencoded
DPoP: SIGNED_DPOP_PROOF_FOR_TOKEN_ENDPOINT

grant_type=authorization_code&code=AUTHORIZATION_CODE&redirect_uri=https%3A%2F%2Fportal.example.com%2Fcallback&code_verifier=PKCE_VERIFIER
~~~

Proof cho token endpoint phải có htm=POST, htu trỏ tới token endpoint thực tế, iat, jti và nonce nếu AS yêu cầu. Không có access token được trình bày trong request này nên ath không phải claim bắt buộc ở bước đó.

Response thành công:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store
Pragma: no-cache

{
  "access_token": "REDACTED_DPOP_BOUND_ACCESS_TOKEN",
  "token_type": "DPoP",
  "expires_in": 300,
  "scope": "orders.read"
}
~~~

AS phải đưa binding vào token hoặc metadata introspection. Với JWT, binding thường là:

~~~json
{
  "cnf": {
    "jkt": "BASE64URL_SHA256_JWK_THUMBPRINT"
  }
}
~~~

### 14.1. Binding phải áp dụng cho các grant được hỗ trợ

DPoP proof có thể được gửi ở token endpoint cho nhiều grant như Authorization Code, Refresh Token và Client Credentials. AS phải áp dụng cùng nguyên tắc xác minh proof và binding theo policy cho grant tương ứng. Không chỉ bảo vệ Authorization Code rồi để Client Credentials hoặc Refresh Token phát Bearer token ngoài ý muốn.

### 14.2. Refresh token và DPoP key

Khi AS cấp refresh token được sender-constrain bằng DPoP, việc sử dụng refresh token sau đó cũng cần proof theo đúng key binding. Nếu client mất private key hoặc đổi key, refresh token đã bind vào key cũ không thể tự chuyển sang key mới. Client cần flow phục hồi/ủy quyền lại theo policy; không cho phép chỉ thêm một public key mới để chiếm refresh token cũ.

### 14.3. Metadata discovery

Authorization Server có thể công bố các thuật toán DPoP proof hỗ trợ qua metadata, ví dụ dpop_signing_alg_values_supported. Client nên discovery từ issuer tin cậy và chọn thuật toán trong danh sách. Không suy ra thuật toán chỉ từ một token hoặc cấu hình do caller gửi.

### 14.4. Custom token generation

Trong Spring Authorization Server version có hỗ trợ DPoP, token context có thể mang thông tin proof key (ví dụ OAuth2TokenContext.DPOP_PROOF_KEY trong API version tương ứng). Nếu customizer hoặc token generator tùy biến:

- Không ghi đè cnf.jkt do cơ chế DPoP tạo ra;
- Không copy jwk từ request mà chưa qua proof verification;
- Không phát token type Bearer khi token đã bind DPoP;
- Đảm bảo cả JWT và opaque/introspection path giữ được binding;
- Kiểm thử response token type cùng nội dung cnf.

Các API token context thay đổi theo version Spring Security/Authorization Server; kiểm tra dependency BOM và Javadoc của version đang dùng trước khi viết customizer.

## 15. JWT và opaque access token

RS có thể nhận thông tin binding theo hai cách:

| Cách phát hành | RS xác minh binding như thế nào? | Điểm cần bảo vệ |
|---|---|---|
| JWT access token | Verify JWT signature, issuer, time, audience; đọc cnf.jkt đã xác minh | JWKS, key rotation, claim validation |
| Opaque access token | Gọi introspection; kiểm tra active và confirmation metadata | Introspection credential, TLS, cache và availability |

Opaque token không có nghĩa RS bỏ qua proof. RS vẫn cần lấy cnf.jkt (hoặc binding tương đương) từ introspection rồi so sánh với public key trong DPoP proof. Nếu introspection không trả binding, RS không có cơ sở để chứng minh token đã bind với proof key.

### 15.1. Không trộn Bearer và DPoP semantics

Một access token thông thường không có cnf.jkt là Bearer token. Một token có cnf.jkt là sender-constrained. Không tự động coi mọi access token từ issuer đều DPoP-bound; RS cần biết token type/binding thực tế. Ngược lại, không chấp nhận DPoP-bound token trên Bearer path chỉ vì chữ ký JWT hợp lệ.

## 16. Lỗi xác minh và phản hồi HTTP

Các lỗi có thể xuất hiện ở AS token endpoint hoặc RS protected resource:

| Lỗi | Ví dụ | Xử lý |
|---|---|---|
| Proof thiếu/sai định dạng | Không có header DPoP, nhiều DPoP headers, JWT malformed | Từ chối authentication |
| typ sai | Không phải dpop+jwt | Từ chối proof |
| alg không hợp lệ | none, HMAC, algorithm không được cho phép | Từ chối proof |
| JWK private hoặc signature sai | Proof không xác minh được bằng public JWK | Từ chối proof |
| htm/htu mismatch | Proof ký cho POST nhưng request là GET | Từ chối proof |
| Proof cũ | iat ngoài cửa sổ | Từ chối proof |
| Nonce thiếu/sai | RS yêu cầu nonce mới | Challenge use_dpop_nonce và DPoP-Nonce |
| Replay | jti đã dùng | Từ chối proof |
| Token không bind đúng key | cnf.jkt khác proof JWK thumbprint | Từ chối access |
| ath mismatch | Proof được tạo cho token khác | Từ chối request |
| Token không hợp lệ | Sai issuer/signature/audience/expired/inactive | Từ chối token |
| Scope/authorization thiếu | Proof và token hợp lệ nhưng thiếu quyền | Từ chối authorization (thường 403) |

Không gộp mọi lỗi thành invalid token. Việc phân loại giúp client biết khi nào cần xin nonce mới, khi nào cần lấy token khác, và khi nào cần sửa policy. Tuy nhiên, không tiết lộ trong error body các thông tin nhạy cảm về key, token, account hoặc nội bộ policy.

### 16.1. Nonce challenge ở Resource Server

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: DPoP error="use_dpop_nonce", error_description="A fresh DPoP nonce is required"
DPoP-Nonce: NEW_OPAQUE_NONCE
~~~

Client tạo proof mới chứa nonce=NEW_OPAQUE_NONCE, jti mới và ath được tính lại cho access token đang gửi. Không dùng nonce này tại AS hoặc một RS khác.

### 16.2. Phân biệt 401 và 403

- **401 Unauthorized:** authentication chưa được chứng minh — access token/proof/binding không hợp lệ hoặc nonce challenge cần được đáp ứng.
- **403 Forbidden:** authentication thành công nhưng principal/scope/tenant/business policy không cho phép hành động.

Một request có proof hợp lệ nhưng thiếu orders.write vẫn phải bị từ chối authorization; không nên yêu cầu client tạo proof mới để sửa một lỗi thiếu scope.

## 17. Các giới hạn bảo mật và cách triển khai an toàn

### 17.1. TLS vẫn bắt buộc

DPoP không thay HTTPS. TLS bảo vệ bí mật token/proof khi truyền và xác thực server endpoint. Nếu client gửi proof tới server giả mạo, attacker có thể thu thập token hoặc khai thác luồng. Xác minh certificate, issuer và endpoint discovery.

### 17.2. Bảo vệ private key phía client

- Tạo key bằng CSPRNG và lưu trong secure storage/keystore phù hợp nền tảng;
- Ưu tiên hardware-backed/non-exportable key khi nền tảng hỗ trợ;
- Không ghi private key vào log, file cấu hình, local storage không an toàn hoặc analytics;
- Có quy trình key loss/rotation và cấp token mới;
- Tách key theo client instance/device hoặc phạm vi phù hợp, tránh dùng một private key toàn tổ chức nếu không cần;
- Xóa key khi logout/device decommission theo policy, nhưng hiểu rằng token đã cấp vẫn cần hết hạn/thu hồi.

### 17.3. Replay cache phải được giới hạn

Kẻ tấn công có thể gửi proof với jti cực dài hoặc tạo số lượng proof lớn để làm đầy cache. Giới hạn độ dài claim, kích thước proof, số request theo key, TTL, memory/cache capacity và rate limit. Lưu hash của jti/identifier nếu phù hợp để giảm lưu dữ liệu thô.

### 17.4. Reverse proxy là một phần của trust boundary

Nếu RS dùng forwarded headers để dựng htu, chỉ tin proxy đã xác thực/được allowlist. Proxy cần loại bỏ header forwarded do client gửi từ Internet và tạo lại giá trị của nó. Nếu không, attacker có thể điều khiển external URI mà RS dùng để xác minh.

### 17.5. Không log credential

Không ghi raw access token, DPoP proof JWT, Authorization header, private key, nonce hoặc full request chứa dữ liệu nhạy cảm. Có thể log kid/thumbprint đã pseudonymize, result code, endpoint, request correlation ID và latency theo policy.

### 17.6. DPoP không ký body

htm và htu gắn proof với method và URI (không có query/fragment); ath gắn với access token. Body JSON, query parameters và các header khác không tự động được ký bởi DPoP. API cần chống sửa payload phải dùng TLS và authorization/business validation phù hợp; không tuyên bố DPoP cung cấp toàn vẹn toàn bộ HTTP message.

## 18. Kiểm thử phối hợp giữa Authorization Server và Resource Server

Kiểm thử phải chứng minh **token được cấp có binding**, client tạo proof hợp lệ và RS từ chối mọi sai khác quan trọng. Unit test cho hàm hash ath chưa đủ để chứng minh filter chain thực thi DPoP.

### 18.1. Ma trận kiểm thử

| Trường hợp | Kết quả cần xác minh |
|---|---|
| Token endpoint nhận proof hợp lệ | Trả access token với token_type=DPoP |
| Access token JWT được cấp | Có cnf.jkt khớp public key của proof |
| Opaque token được cấp | Introspection trả binding metadata mà RS có thể xác minh |
| RS nhận DPoP token + proof đúng | Xác minh thành công, tiếp tục scope/business authorization |
| Proof ký bằng key khác token binding | Từ chối |
| Proof thiếu ath khi gọi resource | Từ chối |
| ath hash token khác | Từ chối |
| htm không khớp request | Từ chối |
| htu sai host/path/scheme | Từ chối |
| htu chỉ khác query | Áp dụng quy tắc bỏ query/fragment; API vẫn kiểm tra quyền dữ liệu |
| Proof iat quá cũ/tương lai | Từ chối |
| jti đã dùng | Replay bị từ chối |
| Hai node cùng nhận một proof | Shared replay store chỉ cho một request thắng |
| Nonce bắt buộc nhưng thiếu | Trả use_dpop_nonce và DPoP-Nonce |
| Client retry với nonce mới, jti mới | Thành công nếu mọi điều kiện khác đúng |
| Public JWK chứa private field | Từ chối proof |
| typ sai hoặc alg=none | Từ chối proof |
| DPoP-bound token gửi bằng Bearer | Không chấp nhận qua Bearer path |
| Bearer token thêm proof nhưng không có cnf.jkt | Không tự nâng token thành DPoP-bound |
| Token hết hạn/sai issuer/sai audience | Từ chối dù proof hợp lệ |
| Token/proof hợp lệ nhưng thiếu scope | 403 theo policy |
| Private key bị mất | Token cũ không dùng được bằng key khác; cần reauthorization/reissue |
| DPoP proof/token bị log | Test/scan phải phát hiện và loại bỏ dữ liệu nhạy cảm |

### 18.2. MockMvc test hình dạng request

Ví dụ khung test với Spring Security 7.1+:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class DPoPResourceServerTests {

    @Autowired
    MockMvc mvc;

    @Test
    void acceptsDpopBoundTokenWithMatchingProof() throws Exception {
        String accessToken = fixtureDpopBoundAccessToken();
        String proof = fixtureProofFor(
            accessToken,
            "GET",
            "https://orders.example.com/api/orders/123");

        mvc.perform(get("/api/orders/123")
                .header(HttpHeaders.AUTHORIZATION, "DPoP " + accessToken)
                .header("DPoP", proof))
            .andExpect(status().isOk());
    }
}
~~~

Đây là **khung test** cần fixture tạo access token được ký và bind đúng, proof ký bởi private key tương ứng, ath chính xác, htu khớp external request và replay store sạch. Nếu chạy sau proxy hoặc MockMvc dùng host/path khác, cấu hình URI fixture phải trùng URI mà application thực sự xác minh.

### 18.3. Negative test binding

1. Cấp access token AT1 bind với key K1;
2. Tạo proof P2 ký bằng key K2;
3. Gửi AT1 cùng P2;
4. Xác minh RS từ chối dù chữ ký P2 hoàn toàn hợp lệ.

Test này chứng minh RS so sánh cnf.jkt và proof JWK thumbprint, thay vì chỉ kiểm tra proof có chữ ký đúng.

### 18.4. Negative test ath

1. Cấp AT1 và AT2;
2. Tạo proof với ath=hash(AT1);
3. Gửi proof đó cùng AT2;
4. RS phải từ chối.

Giữ nguyên key, method, URI và thời gian để test chỉ thất bại vì ath, tránh tạo một request có nhiều lỗi đồng thời rồi không biết validator nào đã chạy.

### 18.5. Kiểm thử replay và nonce

Gửi cùng một proof hai lần trong cửa sổ iat. Lần đầu có thể thành công; lần thứ hai phải bị từ chối nếu replay detection được bật theo policy. Với nonce challenge, kiểm tra nonce của RS không được chấp nhận tại AS và ngược lại. Trong cluster, gửi lần một đến node A, lần hai đến node B để chứng minh cache dùng chung.

## 19. Vận hành và giám sát

| Metric/event | Mục đích | Không ghi |
|---|---|---|
| dpop_proof_valid / invalid | Theo dõi tỷ lệ proof hợp lệ | Raw proof JWT |
| dpop_binding_mismatch | Phát hiện token/proof key mismatch | Access token |
| dpop_ath_mismatch | Phát hiện proof gắn token sai | Token value |
| dpop_htu_mismatch | Phát hiện proxy/canonical URI lỗi hoặc request bị đổi | Full URL có query PII |
| dpop_iat_out_of_window | Phát hiện clock skew/proof cũ | Private key |
| dpop_replay_detected | Theo dõi replay | Raw jti nếu không cần thiết |
| dpop_nonce_challenge | Đo tần suất nonce challenge | Nonce thô trong log rộng |
| Replay cache latency/capacity | Phát hiện cache chậm/đầy | Cache dump |
| Token type/binding distribution | Theo dõi Bearer và DPoP adoption | Raw token |
| Key thumbprint rotation | Theo dõi client key lifecycle | Private key material |

### 19.1. Cluster và consistency

Mọi node RS cần dùng replay store có semantics nhất quán. Nếu node A đã chấp nhận jti=J1, node B phải biết J1 đã được dùng trong cửa sổ hiệu lực. Nếu cache phân tán không khả dụng, policy cần quyết định fail-closed cho endpoint nhạy cảm hoặc có fallback được đánh giá rõ; không âm thầm bỏ replay protection.

### 19.2. Sự cố đổi key

Khi client mất hoặc rotate DPoP key:

- Token cũ vẫn bind với thumbprint cũ;
- Proof ký bằng key mới không khớp cnf.jkt;
- Client thường phải lấy token mới qua flow được AS cho phép;
- Không sửa cnf.jkt của token đã cấp để trỏ sang key mới.

### 19.3. Quan sát phía AS và RS

AS cần theo dõi token issuance DPoP, lỗi proof/nonce và thuật toán proof; RS theo dõi binding mismatch, replay, ath/htu mismatch và authorization failures. Correlation ID có thể nối hai phía nhưng không nên truyền raw access token hoặc proof vào telemetry.

## 20. Checklist triển khai production

1. **Key lifecycle:** client tạo và bảo vệ private key bằng secure storage phù hợp?
2. **Token binding:** AS xác minh DPoP proof ở token endpoint và gắn cnf.jkt hoặc introspection binding?
3. **Token type:** AS trả token_type=DPoP; client dùng scheme DPoP khi gọi RS?
4. **Proof header:** RS kiểm tra một DPoP header duy nhất, typ=dpop+jwt, asymmetric alg và public-only JWK?
5. **Signature:** proof được verify bằng đúng public JWK trong header?
6. **Key binding:** thumbprint proof JWK khớp cnf.jkt của access token đã xác minh?
7. **Token validation:** issuer, signature/introspection, exp, nbf, audience, scope và active state vẫn được kiểm tra?
8. **Request binding:** htm, htu, URI normalization và external URI sau proxy chính xác?
9. **Access-token hash:** ath bằng Base64URL-no-padding của SHA-256 trên ASCII token value?
10. **Freshness:** iat trong cửa sổ ngắn, clock đồng bộ?
11. **Replay:** jti đủ ngẫu nhiên, cache atomic và shared giữa các node?
12. **Nonce:** AS/RS nonce được tách riêng, client retry bằng proof mới?
13. **Opaque token:** introspection trả confirmation binding và RS tin đúng nguồn?
14. **Spring version:** dùng DSL DPoP phù hợp version; không copy API 7.1 vào 6.5?
15. **Proxy:** forwarded headers chỉ được tin từ proxy đã cấu hình?
16. **Testing:** có negative test key mismatch, ath, htm, htu, expiry, nonce và replay?
17. **Observability:** không log token, proof, private key hoặc nonce nhạy cảm?
18. **Incident response:** có quy trình khi key bị lộ, client mất key, replay cache outage hoặc token bị compromise?

## 21. Bài tập vận dụng

**Tình huống A — Token bị đánh cắp:** Kẻ tấn công lấy được access token DPoP-bound từ log nhưng không có private key. Giải thích vì sao Bearer replay không còn đủ để truy cập và RS cần kiểm tra những gì.

**Tình huống B — Binding mismatch:** Token có cnf.jkt=JKT-A, proof chứa public JWK có thumbprint JKT-B, nhưng chữ ký proof hợp lệ. RS nên trả kết quả nào và tại sao?

**Tình huống C — Hai request đồng thời:** Cùng một proof có jti=J1 được gửi đến hai RS node. Vì sao cache in-memory riêng không đủ? Thiết kế atomic replay store ra sao?

**Tình huống D — Reverse proxy:** Client ký htu=https://api.example.com/v1/orders/1; ứng dụng nội bộ nhìn thấy http://orders-service:8080/v1/orders/1. Hãy thiết kế cách xác minh external URI và ranh giới tin cậy của forwarded headers.

**Tình huống E — Nonce challenge:** RS trả DPoP-Nonce. Vì sao client phải tạo proof mới với jti mới? Nonce của RS có thể dùng tại AS không?

**Gợi ý:** A cần cả proof key, token binding, ath, htm, htu, iat và replay checks. B phải bị từ chối do binding mismatch. C cần store dùng chung với atomic insert-if-absent và TTL. D cần trusted proxy cung cấp external URI đã chuẩn hóa; không tin forwarded header do client tự gửi. E proof mới có nonce mới và jti mới; nonce chỉ có giá trị tại server đã phát.

## 22. Tổng kết

**DPoP (RFC 9449)** ràng buộc OAuth access token với public key của client. AS xác minh proof ở token endpoint, tính JWK thumbprint và gắn vào token qua cnf.jkt hoặc introspection metadata. Client sau đó gửi access token với authentication scheme DPoP trong Authorization header, cùng header DPoP chứa proof mới cho từng request.

**Resource Server** phải xác minh access token, proof JWT, public-key thumbprint binding, ath, htm, htu, iat, nonce khi được yêu cầu và replay state qua jti. Sau khi authentication thành công, RS vẫn phải kiểm tra scope, audience và quyền nghiệp vụ.

Trong Spring Security, DPoP support xuất hiện theo từng mốc phiên bản: 6.5 có các provider/validator nền tảng; DSL Resource Server dPoP(...) và converter tích hợp được bổ sung ở 7.1. Khi triển khai, phải chọn đúng API theo BOM và kiểm thử xuyên suốt từ AS tới RS, đặc biệt trong môi trường reverse proxy và multi-node.

DPoP giúp giảm nguy cơ token bị đánh cắp và dùng lại như Bearer, nhưng chỉ có hiệu quả khi private key được bảo vệ, proof được kiểm tra đầy đủ, replay store nhất quán và toàn bộ hệ thống vẫn sử dụng TLS cùng authorization policy đúng.

## 23. Tài liệu tham khảo

- [RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449): DPoP proof, token binding, cnf.jkt, ath, nonce, protected-resource validation và replay.
- [RFC 7638 — JSON Web Key (JWK) Thumbprint](https://www.rfc-editor.org/rfc/rfc7638): cách tính thumbprint của public JWK.
- [RFC 7515 — JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515): chữ ký JWT, Base64URL và JOSE header.
- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517): public JWK và key members.
- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): token endpoint, access token và error response.
- [Spring Security — OAuth 2.0 DPoP-bound Access Tokens](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/dpop-tokens.html): DPoP request, cnf.jkt, ath và Resource Server.
- [Spring Security 6.5 — What's New](https://docs.spring.io/spring-security/reference/6.5/whats-new.html): mốc giới thiệu DPoP support trong Spring Security 6.5.
- [Spring Security — Protocol Endpoints](https://docs.spring.io/spring-security/reference/servlet/oauth2/authorization-server/protocol-endpoints.html): DPoP-bound token support ở Authorization Server và token endpoint.
- [Spring Security API — DPoPAuthenticationProvider](https://docs.spring.io/spring-security/reference/6.5-SNAPSHOT/api/java/org/springframework/security/oauth2/server/resource/authentication/DPoPAuthenticationProvider.html): provider xác minh DPoP-bound protected-resource request.
- [Spring Security API — DPoPConfigurer](https://docs.spring.io/spring-security/reference/7.1-SNAPSHOT/api/java/org/springframework/security/config/annotation/web/configurers/oauth2/server/resource/OAuth2ResourceServerConfigurer.DPoPConfigurer.html): DSL DPoP Resource Server từ Spring Security 7.1.
