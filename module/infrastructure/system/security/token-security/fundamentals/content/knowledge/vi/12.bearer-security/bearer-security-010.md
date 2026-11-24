# Token ràng buộc người gửi

## Mục tiêu học tập

Trong chương **Bearer security** của học phần bảo mật token, câu hỏi trọng tâm là: **làm thế nào để một access token bị sao chép không dễ dàng được sử dụng bởi người khác?** Câu trả lời không chỉ nằm ở chữ ký JWT, mã hóa hay thời hạn token. Một nhóm biện pháp quan trọng là **sender-constrained token** — token được **ràng buộc với khả năng chứng minh quyền sở hữu khóa hoặc chứng chỉ** của bên gửi.

Sau khi học, bạn có thể:

1. Phân biệt **bearer token** với **sender-constrained access token** và giải thích vì sao JWT ký/mã hóa không tự ngăn phát lại.
2. Mô tả **DPoP (Demonstrating Proof of Possession, RFC 9449)**: khóa bất đối xứng, bằng chứng ký gắn với HTTP request và ràng buộc access token bằng `cnf.jkt`.
3. Mô tả **mTLS certificate-bound access token (RFC 8705)**: ràng buộc token với chứng chỉ TLS client bằng `cnf["x5t#S256"]`.
4. Hiểu trách nhiệm riêng của **Authorization Server** khi cấp token và **Resource Server** khi xác minh token, bằng chứng người gửi, scope, audience và quyền trên tài nguyên.
5. Thiết kế kiểm tra `htm`, `htu`, `iat`, `jti`, `ath`, `nonce`, chống phát lại và vận hành khóa/chứng chỉ.
6. Đánh giá giới hạn khi attacker có thể dùng khóa ký, khi trình duyệt bị XSS hoặc khi TLS bị kết thúc ở proxy; lựa chọn DPoP/mTLS theo mô hình đe dọa.

## 1. Bearer token bị sao chép thì điều gì xảy ra?

Với **bearer access token**, bên nhận thường chấp nhận request dựa trên việc caller **trình được token hợp lệ**, không đòi bằng chứng độc lập rằng caller là bên được phát token lúc đầu.

~~~http
GET /orders/42 HTTP/1.1
Host: api.example.test
Authorization: Bearer <ACCESS_TOKEN_PLACEHOLDER>
~~~

Resource Server (RS) có thể xác minh chữ ký JWT hoặc tra cứu opaque token, sau đó kiểm tra `iss`, `aud`, `exp`, `scope` và quyền tài nguyên. Những bước ấy quan trọng, nhưng nếu attacker đánh cắp **nguyên access token còn hiệu lực**, họ có thể trình **cùng chuỗi token** để yêu cầu API cho đến khi token hết hạn/bị thu hồi.

~~~mermaid
sequenceDiagram
    participant C as Client hợp lệ
    participant A as Attacker
    participant API as Resource Server
    C->>API: Bearer token T còn hiệu lực
    API-->>C: Cho phép nếu token và quyền đều hợp lệ
    Note over C,A: T bị sao chép từ log, XSS hoặc thiết bị
    A->>API: Gửi lại đúng bearer token T
    API-->>A: Có thể cho phép trong phạm vi quyền T
~~~

**JWT đã ký** giúp phát hiện payload bị sửa, **JWE** giúp bảo mật nội dung mã hóa, **TTL ngắn** giảm thời gian token có thể bị lạm dụng, **scope/audience hẹp** giảm phạm vi ảnh hưởng. Tuy nhiên, **không biện pháp nào trong số đó tự chứng minh người đang gửi request có quyền sở hữu một khóa riêng**.

### Mục tiêu của sender-constraining

Thay vì chỉ hỏi “Bạn có token T không?”, RS còn hỏi:

> “Bạn có thể chứng minh khả năng sử dụng khóa/chứng chỉ **đã được AS ràng buộc với token T** không, và bằng chứng đó có phù hợp với request hiện tại không?”

Kẻ tấn công chỉ sao chép chuỗi access token nhưng **không** có quyền sử dụng khóa/chứng chỉ tương ứng sẽ khó dùng token để gọi API.

| Thuộc tính | Bearer access token | Sender-constrained access token |
|---|---|---|
| Điều kiện trình token | Chủ yếu sở hữu token hợp lệ. | Token hợp lệ **và** proof từ khóa/chứng chỉ đã ràng buộc. |
| Sao chép token đơn lẻ | Có thể đủ để gọi API. | Thông thường **không đủ**. |
| Cơ chế điển hình | `Authorization: Bearer ...` | DPoP hoặc access token ràng buộc chứng chỉ mTLS. |
| Giới hạn quyền | Vẫn cần issuer, audience, scope, thời hạn và policy. | **Vẫn cần tất cả** các bước kiểm tra đó. |
| Khi attacker kiểm soát cả khóa hoặc ứng dụng | Token có thể bị lạm dụng. | **Vẫn có thể bị lạm dụng** nếu attacker sử dụng được khóa hợp lệ. |

Sender-constrained token là **giảm khả năng replay khi chỉ token bị lộ**, không phải bảo đảm tuyệt đối rằng thiết bị và ứng dụng chưa bị xâm nhập.

## 2. Các thành phần của mô hình tin cậy

Một luồng OAuth 2.0 thường có:

- **Client:** ứng dụng muốn gọi API; với DPoP, client tạo hoặc được cung cấp một cặp khóa thích hợp và **giữ private key**.
- **Authorization Server (AS):** phát hành access token và ghi **ràng buộc token với khóa/chứng chỉ** theo cơ chế đã chọn.
- **Resource Server (RS):** kiểm tra access token cùng **bằng chứng người gửi hiện tại**, rồi phân quyền theo request/tài nguyên.
- **Principal/Resource Owner:** người dùng hoặc service principal có quyền làm việc trong phạm vi được cấp.

Một ràng buộc mật mã không thay quyết định ủy quyền:

~~~text
request ALLOW chỉ khi:
    token được xác minh và dành cho Resource Server này
    AND token còn hiệu lực/trạng thái hợp lệ
    AND proof người gửi hợp lệ và khớp ràng buộc token
    AND scope đủ cho action
    AND principal có quyền trên resource/tenant cụ thể
~~~

AS **không nên** chỉ phát access token với claim mô tả public key rồi bỏ qua xác minh proof khi cấp. RS **không nên** chỉ kiểm tra proof có chữ ký hợp lệ mà quên so sánh public key/chứng chỉ đó với **token đã được cấp**.

## 3. DPoP là gì?

**DPoP** theo **RFC 9449** cho phép client chứng minh mình có thể sử dụng **private key bất đối xứng** thông qua một **DPoP proof**: JWT dạng JWS được ký, được tạo cho một HTTP request cụ thể. Public key được thể hiện trong header proof và được dùng để kiểm tra chữ ký.

Một access token DPoP-bound được AS ràng buộc với **JWK Thumbprint** của public key (thường được biểu diễn bằng `cnf.jkt` trong JWT access token hoặc metadata phù hợp ở introspection).

### Phân biệt ba thứ

| Thành phần | Là gì? | Nơi sử dụng |
|---|---|---|
| **Access token DPoP-bound** | Token chứa/được tra cứu cùng thông tin khóa đã ràng buộc, audience và quyền được cấp. | RS kiểm tra token và ràng buộc khóa. |
| **DPoP proof** | JWS được **private key của client** ký, gắn với phương thức/URI/thời điểm/yêu cầu và khi gọi RS còn gắn với access token. | Client gửi trong HTTP header `DPoP`; RS/AS xác minh proof. |
| **Public JWK thumbprint** | Dấu vân tay theo quy tắc chuẩn của public JWK, dùng để so khớp ràng buộc. | AS lưu/gắn với token; RS so với khóa trong proof. |

DPoP proof **không phải access token**, cũng không tự cấp scope hay xác nhận user có quyền trên dữ liệu. Ngược lại, access token không thể tự thay DPoP proof của từng request.

### Luồng cấp token và gọi API

~~~mermaid
sequenceDiagram
    participant C as Client giữ private key K
    participant AS as Authorization Server
    participant API as Orders API
    C->>C: Tạo cặp khóa K (public/private)
    C->>AS: Token request + DPoP proof ký bằng K
    AS->>AS: Kiểm tra proof, client, grant, chính sách
    AS->>AS: Phát token T ràng buộc public key K
    AS-->>C: access_token T, token_type DPoP
    C->>C: Tạo proof mới cho GET /orders/42
    C->>API: Authorization: DPoP T + header DPoP: proof
    API->>API: Xác minh T và proof, so thumbprint
    API->>API: Kiểm tra scope và quyền trên order
    API-->>C: Kết quả được phép
~~~

Đây là minh họa luồng; cách xin token (Authorization Code + PKCE, Client Credentials...) phải tuân thủ OAuth và yêu cầu riêng của AS. DPoP **bổ sung** proof sở hữu khóa, không thay xác thực client confidential, PKCE, policy cấp token hay consent khi các bước ấy áp dụng.

## 4. DPoP proof chứa những gì?

Một DPoP proof dùng cấu trúc **JWS**, với protected header minh họa:

~~~json
{
  "typ": "dpop+jwt",
  "alg": "ES256",
  "jwk": {
    "kty": "EC",
    "crv": "P-256",
    "x": "<PUBLIC_X_BASE64URL>",
    "y": "<PUBLIC_Y_BASE64URL>"
  }
}
~~~

JWK ở đây **chỉ chứa thành phần khóa công khai**, không được đưa private key (`d`) vào proof. Thuật toán ký phải là loại **bất đối xứng được cho phép** theo RFC/profile; không chấp nhận `none` hoặc tự tin thuật toán từ header mà chưa áp dụng allowlist.

Payload khi gọi **Resource Server** có dạng minh họa:

~~~json
{
  "jti": "proof-unique-id-001",
  "htm": "GET",
  "htu": "https://api.example.test/orders/42",
  "iat": 1893456000,
  "ath": "<BASE64URL_SHA256_OF_ACCESS_TOKEN>",
  "nonce": "<OPTIONAL_SERVER_NONCE>"
}
~~~

Các placeholder chỉ để giải thích cấu trúc, **không phải một proof hợp lệ có thể dùng thực tế**.

| Trường | Vai trò | Điều RS/AS cần chú ý |
|---|---|---|
| `jti` | ID duy nhất của proof để chống **phát lại cùng proof** trong cửa sổ chấp nhận. | Theo dõi sử dụng lại trên toàn phạm vi RS thích hợp; giới hạn thời gian lưu. |
| `htm` | HTTP method được proof bảo vệ. | Phải khớp phương thức request thực tế, ví dụ `GET` hay `POST`. |
| `htu` | URI đích được proof bảo vệ. | So khớp URI hiệu lực theo quy tắc DPoP; **query và fragment không nằm trong `htu`**. |
| `iat` | Thời điểm tạo proof theo NumericDate. | Chỉ nhận proof đủ mới trong cửa sổ thời gian quy định, có clock skew hợp lý. |
| `ath` | Base64URL của SHA-256 trên giá trị **access token**. | Khi trình token cho RS, khớp hash của token thực tế trong request. |
| `nonce` | Giá trị thử thách do server cung cấp nếu cơ chế nonce được áp dụng. | Kiểm tra đúng nonce còn hiệu lực do AS hoặc RS phát hành. |

**Quan trọng:** khi client tạo proof tại **token endpoint của AS**, proof chưa trình access token để dùng với RS, nên **không có yêu cầu `ath` của access token** trong trường hợp đó. Khi dùng DPoP-bound access token **tại RS**, proof phải chứa `ath` phù hợp với chính token được gửi.

DPoP proof **không bảo vệ toàn bộ query, request body hoặc mọi HTTP header**. Việc đổi body của cùng request nếu attacker có thể ký proof hợp lệ vẫn phải được chặn bằng authentication/authorization, TLS, kiểm tra tính toàn vẹn ứng dụng và chính sách nghiệp vụ.

### HTTP request sử dụng DPoP

~~~http
GET /orders/42 HTTP/1.1
Host: api.example.test
Authorization: DPoP <DPOP_BOUND_ACCESS_TOKEN>
DPoP: <SIGNED_DPOP_PROOF_JWT>
~~~

Với DPoP, **`Authorization: DPoP`** và header **`DPoP`** có vai trò khác nhau. Một token DPoP-bound không được đối xử như bearer token có thể dùng mà không kèm proof.

Trong OAuth token response, AS cấp DPoP-bound token với `token_type` tương ứng; ví dụ:

~~~json
{
  "access_token": "<DPOP_BOUND_ACCESS_TOKEN>",
  "token_type": "DPoP",
  "expires_in": 600,
  "scope": "orders:read"
}
~~~

Đừng suy rằng cứ thấy JWT chứa `cnf` là có thể bỏ qua yêu cầu header proof. Resource Server phải triển khai đúng cơ chế được token/profile chỉ định.

## 5. DPoP: access token ràng buộc public key ra sao?

### Bước phát hành tại Authorization Server

Khi client gọi token endpoint với DPoP proof:

1. AS nhận HTTP request có **header `DPoP`**.
2. AS xác minh proof JWS bằng public JWK trong header proof, kiểm tra `typ`, `alg`, `htm`, `htu`, `iat`, `jti` và nonce nếu yêu cầu.
3. AS kiểm tra **grant, client authentication/PKCE, subject, scope, resource, policy** như một giao dịch OAuth bình thường.
4. Nếu cấp DPoP-bound access token, AS xác định **JWK thumbprint** của public key dùng xác minh proof.
5. AS gắn thumbprint đó với **token được cấp**, hoặc trả metadata có thể kiểm tra qua introspection khi RS dùng opaque token.

Ví dụ **payload JWT access token minh họa**, không phải proof:

~~~json
{
  "iss": "https://auth.example.test",
  "sub": "user-123",
  "aud": "orders-api",
  "scope": "orders:read",
  "iat": 1893456000,
  "exp": 1893456600,
  "cnf": {
    "jkt": "<BASE64URL_JWK_SHA256_THUMBPRINT>"
  }
}
~~~

`cnf` (*confirmation*) chứa thông tin về khóa mà người gửi cần chứng minh quyền sở hữu; `jkt` là JWK thumbprint theo quy tắc RFC 7638. Với **opaque token**, RS có thể lấy thông tin `cnf.jkt` từ introspection/nguồn metadata tin cậy thay vì nhìn vào payload JWT.

Một `jkt` **không phải private key**, và bản thân giá trị thumbprint **không phải proof**. Cần chứng minh ký được bằng private key của public JWK tương ứng.

### Bước sử dụng tại Resource Server

RS kiểm tra **hai đối tượng độc lập nhưng liên kết**:

~~~text
Access token T:
    đã xác minh issuer, audience, exp, scope, trạng thái
    token confirmation thumbprint = jkt_expected

DPoP proof P:
    chữ ký hợp lệ với public JWK trong P
    JWK thumbprint = jkt_proof
    htm/htu trùng request
    iat đủ mới, jti chưa từng dùng trong cửa sổ
    ath = base64url(SHA-256(T))
    nonce hợp lệ nếu RS yêu cầu

Accept sender proof iff jkt_proof == jkt_expected
AND mọi điều kiện proof khác đều đạt.
Sau đó mới xét scope và quyền trên tài nguyên.
~~~

Nếu RS chỉ kiểm tra chữ ký proof nhưng **không** so sánh `jkt_proof` với `cnf.jkt` của access token, attacker có thể tự tạo một cặp khóa riêng rồi ký một proof cho token đã đánh cắp — làm mất ý nghĩa sender-constraining.

Nếu RS chỉ so sánh `jkt` mà không kiểm tra `htm`/`htu`, `ath`, thời điểm hoặc `jti`, một proof bị lộ có thể bị dùng sai request hoặc bị phát lại.

## 6. Chống phát lại DPoP proof: `jti`, thời gian và nonce

DPoP hạn chế dùng token bị sao chép nhưng **DPoP proof cũng có thể bị đánh cắp/phát lại**. Vì vậy proof được thiết kế để ngắn hạn và gắn với HTTP request.

### `jti` không chỉ là trường để ghi log

RS/AS cần phát hiện việc **dùng lại cùng một proof ID** trong phạm vi chấp nhận phù hợp. Một hệ thống có nhiều instance cần xem xét:

- Kho nhận diện `jti` đã dùng phải được chia sẻ/đồng bộ đủ cho mô hình triển khai; chỉ lưu trong memory của một instance có thể cho phép replay sang instance khác.
- Định danh chống replay cần được gắn với **khóa/proof và ngữ cảnh cần thiết** để tránh nhận nhầm hoặc tạo xung đột không cần thiết.
- Giới hạn cửa sổ thời gian và dung lượng lưu; từ chối proof cũ hoặc trùng.
- Nếu kho chống replay bắt buộc không hoạt động, **không tự chấp nhận proof trùng hoặc bỏ kiểm tra**.

Không chỉ thêm `jti` vào JWT rồi cho rằng hệ thống đã chống replay. **Giá trị duy nhất chỉ có tác dụng khi server kiểm tra việc tái sử dụng**.

### `iat` và cửa sổ hiệu lực

RS định nghĩa khoảng thời gian chấp nhận proof đủ mới, có cân nhắc độ lệch đồng hồ. Proof quá cũ hoặc thời gian bất hợp lý phải bị từ chối. Đừng cho thời hạn proof kéo dài giống access token; **proof nên được tạo mới cho mỗi HTTP request**.

### Nonce do AS/RS đưa ra

DPoP hỗ trợ nonce khi server cần ràng buộc proof với một thử thách mới, ví dụ giảm khả năng chuẩn bị trước các proof hợp lệ trong thời gian dài.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant API as Resource Server
    C->>API: Token T + DPoP proof không có nonce phù hợp
    API-->>C: Phản hồi use_dpop_nonce + DPoP-Nonce: N
    C->>C: Tạo proof mới với nonce N và jti mới
    C->>API: Token T + DPoP proof mới
    API->>API: Verify nonce, jti, iat, htm, htu, ath, key binding
    API-->>C: Xử lý request nếu mọi điều kiện đều hợp lệ
~~~

AS và RS có thể có **nonce khác nhau**, phạm vi/chính sách riêng. Client không nên nhầm nonce nhận từ một server với nonce dùng cho server khác. Với mỗi lần thử lại, tạo proof mới và `jti` mới; không phát lại nguyên proof vừa bị từ chối.

**Giới hạn:** việc DPoP `htu` bỏ qua query/fragment theo RFC có nghĩa một proof không tự ràng buộc từng tham số query. Do đó **không dựa vào DPoP một mình** để bảo vệ ngữ nghĩa payload/biến đổi request; Authorization tại API vẫn phải kiểm tra toàn bộ dữ liệu yêu cầu.

## 7. mTLS certificate-bound access token

**Mutual TLS (mTLS)** cho phép phía server kiểm tra **client certificate** trong kết nối TLS. Theo **RFC 8705**, access token có thể được ràng buộc với chứng chỉ của client, để RS kiểm tra **caller hiện tại có trình chứng chỉ khớp token hay không**.

### Hai khái niệm liên quan nhưng không giống nhau

| Khái niệm | Mục đích |
|---|---|
| **mTLS client authentication** | Client sử dụng certificate để xác thực danh tính client với AS theo cơ chế được cấu hình. |
| **mTLS certificate-bound access token** | Token được AS ràng buộc với certificate, và RS yêu cầu kết nối TLS trình certificate khớp để được sử dụng token. |

Một hệ thống có thể áp dụng các cơ chế theo policy/profile của mình; **xác thực client tại AS** không tự bảo đảm RS cũng kiểm tra ràng buộc access token. Mặt khác, mô hình self-signed certificate phù hợp theo RFC có thể dùng cho sender-constraining trong điều kiện được hỗ trợ, nhưng điều đó **không đồng nghĩa** certificate tự được CA tin cậy cho mọi mục đích.

### Ràng buộc chứng chỉ bằng `cnf["x5t#S256"]`

Khi AS cấp JWT access token certificate-bound, một claim có thể có dạng:

~~~json
{
  "iss": "https://auth.example.test",
  "sub": "service-orders",
  "aud": "billing-api",
  "scope": "billing:read",
  "exp": 1893456600,
  "cnf": {
    "x5t#S256": "<BASE64URL_SHA256_OF_CERT_DER>"
  }
}
~~~

Giá trị `x5t#S256` biểu diễn **SHA-256 thumbprint của client certificate dạng DER**, được mã hóa Base64URL. Với opaque token, thông tin tương ứng có thể được RS lấy qua introspection.

### Bước kiểm tra ở Resource Server

1. RS nhận request qua TLS theo chính sách mTLS và thu được **client certificate đã được TLS stack xác minh phù hợp**.
2. RS xác minh access token là token được AS đáng tin cấp, đúng audience, loại token, thời hạn và trạng thái.
3. RS tính thumbprint từ **certificate thực sự gắn với kết nối được tin**, rồi so với `cnf["x5t#S256"]` của token.
4. Chỉ sau khi khớp ràng buộc, RS xét `scope`, principal và quyền trên đối tượng.

~~~mermaid
sequenceDiagram
    participant C as Client giữ private key certificate
    participant AS as Authorization Server
    participant API as Billing API
    C->>AS: Token request qua TLS có client certificate
    AS->>AS: Áp dụng policy và gắn cert thumbprint với token
    AS-->>C: Certificate-bound access token T
    C->>API: TLS với client certificate + access token T
    API->>API: Xác minh TLS client cert và token T
    API->>API: So cert thumbprint với cnf x5t#S256
    API->>API: Kiểm tra audience, scope và quyền dữ liệu
    API-->>C: Chỉ trả dữ liệu được phép
~~~

Với mTLS-bound token, cú pháp HTTP truyền access token có thể sử dụng cơ chế bearer-style theo profile, **nhưng thực tế RS phải yêu cầu chứng chỉ đúng**. Không được coi một token certificate-bound là bearer token thuần túy chỉ vì thấy chuỗi `Authorization` chứa một scheme quen thuộc.

### Nguy cơ khi TLS kết thúc ở reverse proxy hoặc API Gateway

Nếu proxy **kết thúc TLS**, backend không tự nhìn thấy client certificate ban đầu. Một lỗi đặc biệt nguy hiểm là backend tin ngay:

~~~http
X-Client-Cert: <CERTIFICATE_SUPPLIED_BY_UNTRUSTED_CALLER>
~~~

Nếu client bên ngoài được phép tự đặt header này, attacker có thể giả một chứng chỉ hoặc dữ liệu thumbprint. Kiến trúc cần:

- Proxy xác minh client certificate ở TLS connection **thật**.
- Kênh proxy → backend có bảo vệ và xác thực đáng tin, hoặc proxy đảm nhận kiểm tra ràng buộc token ở ranh giới được định nghĩa.
- Proxy **xóa/ghi đè** header certificate do caller cung cấp và chỉ chuyển metadata được xác thực qua kênh tin cậy.
- Backend chỉ tin forwarded certificate context từ proxy được xác thực theo quy tắc cụ thể, không tin mọi header tên “client-cert”.
- Có kiểm thử khi đi qua gateway, load balancer, service mesh và nhiều lớp reverse proxy.

Sender-constraining bằng mTLS thất bại nếu hệ thống **mất quan hệ tin cậy giữa kết nối TLS thực và certificate dùng để so token**.

## 8. DPoP và mTLS: nên chọn phương án nào?

| Tiêu chí | **DPoP (RFC 9449)** | **mTLS certificate-bound (RFC 8705)** |
|---|---|---|
| Cách chứng minh khóa | JWS proof riêng cho HTTP request, ký bằng private key. | TLS handshake với client certificate và khóa riêng tương ứng. |
| Token gắn với | JWK thumbprint `cnf.jkt`. | Thumbprint certificate `cnf["x5t#S256"]`. |
| Ràng buộc request | `htm`, `htu`, `iat`, `jti`, `ath` và nonce khi cần. | Quan hệ giữa token và chứng chỉ trình trên kết nối TLS. |
| Vận hành | Tạo proof mỗi request, kiểm tra replay cache/nonce và URI. | Quản lý PKI/cert, TLS gateway, certificate rotation. |
| Môi trường phù hợp | Public clients có khả năng tạo/giữ khóa, API hỗ trợ proof. | Backend-to-backend và hạ tầng hỗ trợ client certificate đáng tin. |
| Khi token bị sao chép | Bản sao đơn lẻ không đủ nếu attacker không dùng được private key. | Bản sao đơn lẻ không đủ nếu attacker không sử dụng được private key/certificate gắn với token. |
| Khi private key bị chiếm hoặc bị dùng trái phép | Vẫn có nguy cơ. | Vẫn có nguy cơ. |

Đây là so sánh để **lựa chọn kiến trúc**, không phải xếp hạng rằng DPoP luôn an toàn hơn mTLS hoặc ngược lại. Cần xem năng lực client, cách quản lý khóa, yêu cầu latency, topology TLS, proxy/gateway và mức độ rủi ro.

### Điểm chung quan trọng

- **AS phải phát hành ràng buộc** bằng một nguồn token/metadata đáng tin.
- **RS phải xác minh ràng buộc** ở request thật, không chỉ kiểm tra token còn hạn.
- **Scope, audience, authorization theo tài nguyên** vẫn bắt buộc.
- **Private key/certificate** phải được bảo vệ; nếu attacker dùng được khóa, cơ chế sender-constraining không còn bảo vệ đầy đủ.
- **Refresh token** và phiên phải có chiến lược bảo vệ/thu hồi riêng.

## 9. Sender-constrained token không giải quyết toàn bộ sự cố

### 9.1. Bị đánh cắp token nhưng không bị đánh cắp khóa

Đây là tình huống sender-constraining nhắm tới. Attacker có chuỗi access token nhưng không thể tạo DPoP proof hợp lệ hoặc không thể hoàn tất kết nối mTLS với certificate/khóa tương ứng. RS từ chối nếu đã kiểm tra đúng ràng buộc.

### 9.2. Attacker dùng được private key

Nếu private key bị lộ cùng token hoặc attacker kiểm soát môi trường mà khóa có thể ký/hoàn tất TLS, attacker **có thể tiếp tục tạo proof hợp lệ**. DPoP không mặc nhiên chứng minh ứng dụng gốc không bị malware. HSM, TPM, secure enclave hoặc key store không cho xuất khóa có thể giảm nguy cơ xuất khóa, nhưng **không nhất thiết ngăn malware đang chạy trong cùng ngữ cảnh gọi API ký**.

### 9.3. XSS trong trình duyệt

DPoP có thể giảm rủi ro attacker **mang token ra khỏi trình duyệt và dùng từ thiết bị khác** nếu private key không xuất được. Tuy nhiên, JavaScript độc hại chạy trong origin bị xâm nhập có thể **đọc hoặc sử dụng token** và có thể yêu cầu môi trường ký proof/điều khiển ứng dụng khi phiên còn hoạt động. Do đó cần chống XSS, CSP phù hợp, giảm token tồn tại ở JavaScript, cân nhắc BFF và không dùng DPoP như biện pháp thay thế an toàn frontend.

### 9.4. Replay proof còn hiệu lực

DPoP proof bị sao chép vẫn có thể bị thử phát lại nếu `jti` không được theo dõi hoặc cửa sổ thời gian quá rộng. `nonce` và kiểm tra `iat`, `jti`, `htm`, `htu`, `ath` hạn chế những khả năng này. Cần bảo đảm nhiều instance RS thống nhất chính sách replay.

### 9.5. Client được cấp quyền quá rộng

Token DPoP/mTLS hợp lệ **không bảo vệ** khỏi việc client được AS cấp `payments:refund` ngoài nhu cầu. Cơ chế này xác nhận khả năng sử dụng khóa, **không đánh giá đúng sai của consent, scope hay policy**. Authorization Server phải áp dụng quyền tối thiểu và Resource Server phải kiểm tra hành động nghiệp vụ.

### 9.6. Dữ liệu tenant khác nhưng token và proof đều hợp lệ

Một user có `orders:read`, `aud=orders-api` và proof hợp lệ vẫn **không** được đọc đơn của user/tenant khác nếu không được ủy quyền. Sender constraint chỉ là **một lớp bảo vệ sử dụng token**, không thay object-level authorization.

## 10. Luồng kiểm tra tại Resource Server

### Trình tự xử lý khuyến nghị

~~~mermaid
flowchart TD
    A["Client gọi API kèm access token"] --> B{"Đúng loại token, dạng và kênh?"}
    B -- Không --> R1["Từ chối: token không được chấp nhận"]
    B -- Có --> C{"Token được xác minh? iss/aud/exp/trạng thái đúng?"}
    C -- Không --> R1
    C -- Có --> D{"Loại ràng buộc theo policy?"}
    D -- DPoP --> E["Xác minh JWS proof, htm/htu/iat/jti/ath/nonce"]
    D -- mTLS --> F["Xác minh TLS client cert và thumbprint"]
    D -- Không có ràng buộc --> G{"API chấp nhận bearer theo policy?"}
    E --> H{"Khóa proof khớp cnf.jkt?"}
    F --> I{"Cert khớp cnf.x5t#S256?"}
    G -- Không --> R1
    G -- Có --> J["Tiếp tục theo chính sách bearer"]
    H -- Không --> R1
    I -- Không --> R1
    H -- Có --> K{"Scope đủ?"}
    I -- Có --> K
    J --> K
    K -- Không --> R2["403: thiếu quyền"]
    K -- Có --> L{"Principal được phép trên object/tenant?"}
    L -- Không --> R2
    L -- Có --> OK["Cho phép action trong phạm vi"]
~~~

Với endpoint **bắt buộc sender-constrained access token**, nhánh bearer không proof phải bị từ chối; không có cơ chế “fallback sang bearer” chỉ vì việc xác minh DPoP/mTLS gặp lỗi.

### Mã giả kiểm tra DPoP-bound access token

~~~text
handleRequest(request):
    token = parseAccessTokenWithExpectedAuthorizationScheme(request)
    if token missing:
        rejectUnauthenticated()

    validatedToken = validateTokenFromTrustedIssuer(token)
      # JWT: verify signature/key/algorithm, iss/aud/exp/nbf/type
      # opaque: authenticated introspection + active/aud/scope/exp
    if invalid(validatedToken) or not intendedForThisAPI(validatedToken):
        rejectUnauthenticated()

    if validatedToken.isDpopBound:
        proof = parseDpopHeader(request)
        if missing(proof):
            rejectUnauthenticated()
        verifiedProof = verifyDpopJws(proof, allowedAlgs, publicJwk)
        if invalid(verifiedProof):
            rejectUnauthenticated()
        if verifiedProof.htm != actualMethod(request)
            or verifiedProof.htu != effectiveUriWithoutQueryOrFragment(request):
            rejectUnauthenticated()
        if not recent(verifiedProof.iat):
            rejectUnauthenticated()
        if not constantTimeEquals(verifiedProof.ath, hashAccessToken(token)):
            rejectUnauthenticated()
        if serverRequiresNonce and not validNonce(verifiedProof.nonce):
            rejectUnauthenticated()
        if thumbprint(verifiedProof.publicJwk) != validatedToken.cnf.jkt:
            rejectUnauthenticated()
        if not atomicallyRegisterUniqueProofId(
                verifiedProof.publicJwk, verifiedProof.jti, replayWindow):
            rejectUnauthenticated()

    else if validatedToken.isMtlsBound:
        certificate = verifiedClientCertificateFromTrustedTlsContext(request)
        if certificate missing or sha256Thumbprint(certificate) != validatedToken.cnf.certThumbprint:
            rejectUnauthenticated()

    else if thisAPI.requiresSenderConstrainedTokens:
        rejectUnauthenticated()

    if not validatedToken.grantedScopes.containsExact(requiredScope(request)):
        rejectInsufficientScope()

    resource = loadTrustedResource(request.resourceId)
    if not authorized(validatedToken.principal, request.action, resource):
        rejectForbidden()

    return performAuthorizedAction(resource)
~~~

Đây là **mã giả mô hình**, không phải một thuật toán tự triển khai DPoP/mTLS đầy đủ. Thư viện/gateway tin cậy phải xử lý chuẩn hóa URI, xác thực JWS, kiểm tra `jwk`, chống replay nguyên tử, nonce, TLS client identity, lỗi giao thức và những điều kiện RFC chi tiết. Không tự viết primitives mật mã hoặc so sánh tùy tiện khi hệ thống đã có middleware hỗ trợ.

### Ví dụ Java: authorization trên kết quả đã xác minh

Các lớp `ValidatedAccessToken` và `SenderProofResult` trong ví dụ chỉ được tạo bởi **lớp xác minh bảo mật đáng tin**, không phải dữ liệu do client tự gửi:

~~~java
import java.util.Objects;
import java.util.Set;

record ValidatedAccessToken(
    String subject,
    String tenantId,
    Set<String> audience,
    Set<String> scopes,
    boolean active
) {}

record SenderProofResult(boolean verified, String bindingMethod) {}
record Order(String id, String ownerId, String tenantId) {}

final class OrderAccessPolicy {
    static boolean canRead(
            ValidatedAccessToken token,
            SenderProofResult proof,
            Order order) {
        if (token == null || proof == null || order == null) {
            return false;
        }
        if (!token.active() || !proof.verified()) {
            return false;
        }
        if (token.audience() == null
                || !token.audience().contains("orders-api")
                || token.scopes() == null
                || !token.scopes().contains("orders:read")) {
            return false;
        }
        return token.tenantId() != null
                && token.subject() != null
                && Objects.equals(token.tenantId(), order.tenantId())
                && Objects.equals(token.subject(), order.ownerId());
    }
}
~~~

Code trên **không** xác minh DPoP JWT, certificate, issuer hay chữ ký; nó chỉ minh họa lớp **quyền nghiệp vụ** trên kết quả đã được middleware xác nhận. Không cho caller tự đặt `SenderProofResult(verified=true)`. DPoP và mTLS phải được enforce trên mọi đường đi tới nghiệp vụ, kể cả endpoint nội bộ nếu nằm trong ranh giới cần bảo vệ.

## 11. Lưu trữ, cấp mới, refresh và luân chuyển khóa

### Lưu khóa và access token

- **Không lưu private key trong log, URL, repository, analytics, crash report** hoặc dữ liệu frontend công khai.
- Khi có thể, dùng **secure key store/keystore** hoặc cơ chế khóa không cho xuất tùy nền tảng; xác định rõ ai có quyền **sử dụng** khóa.
- Token nên có **audience, scope và TTL tối thiểu** theo nhu cầu. Sender-constrained token vẫn cần bảo vệ token vì attacker có thể tấn công vào app hoặc đánh cắp cả khóa.
- Với trình duyệt, chống **XSS**; với mobile/backend, bảo vệ backup, bí mật triển khai và quyền truy cập khóa.
- Với mTLS, quản lý certificate lifecycle, hết hạn, gia hạn, CA/trust policy và kênh TLS có xác thực.

### Khóa được xoay thì token cũ có dùng tiếp được không?

Token DPoP được ràng buộc với thumbprint của **khóa cũ**. Một proof được ký bởi khóa **mới** không được tự chấp nhận cho token cũ chỉ vì cùng client ID. Client phải xin **access token được ràng buộc với khóa mới** theo luồng và chính sách AS.

Với mTLS, khi đổi certificate, thumbprint `x5t#S256` cũng có thể đổi; token ràng buộc certificate cũ không tự dùng được với certificate mới. AS/RS cần phối hợp thời hạn, quy trình cấp token và chuyển đổi certificate.

Không đổi chính sách thành “chấp nhận bất kỳ khóa nào của cùng user” để tránh gián đoạn, vì như vậy vô hiệu hóa mục tiêu ràng buộc **token cụ thể với khóa cụ thể**.

### Refresh token có cần ràng buộc người gửi không?

Refresh token có khả năng duy trì quyền truy cập lâu hơn access token, nên cần bảo vệ đặc biệt. Theo thiết kế và loại client, AS có thể dùng **refresh token rotation**, sender-constraining hoặc cả các biện pháp phù hợp để phát hiện/ngăn token bị đánh cắp.

Khi refresh token được ràng buộc với DPoP key, AS phải kiểm tra **proof hợp lệ của key tương ứng** khi client dùng refresh token, theo profile và policy. DPoP proof trình tại token endpoint **không phải access token `ath` tại RS**.

Không suy rằng **access token DPoP-bound luôn đồng nghĩa mọi refresh token liên quan cũng đã được bảo vệ đúng**. Kiểm tra riêng chính sách và triển khai cho refresh token.

### Thu hồi và trạng thái quyền

Sender-constraining làm khó kẻ chỉ đánh cắp token, nhưng **không thay thu hồi**. Khi user bị khóa, client bị vô hiệu hóa, consent bị rút, khóa bị lộ hoặc quyền tenant thay đổi, RS/AS cần chính sách TTL, introspection, denylist hoặc kiểm tra trạng thái/permission hiện hành.

Chữ ký và `cnf` vẫn có thể hợp lệ sau khi permission bị rút. Mức độ cập nhật ngay của quyền là yêu cầu **authorization**, không phải điều DPoP/mTLS tự giải quyết.

## 12. Lời gọi giữa microservices và nhiều Resource Server

Một client có token `aud=orders-api` và DPoP proof hợp lệ cho `GET https://api.example.test/orders/42`. Orders API muốn gọi Billing API. **Không thể chỉ chuyển tiếp token/proof cũ**:

- Token có `aud=orders-api` không dành cho Billing API.
- DPoP proof gắn với `htm`/`htu` của request tới Orders, không hợp lệ cho request khác tới Billing.
- Orders API không có private key của client gốc và **không nên giả vờ** là client sở hữu khóa ấy.

~~~mermaid
sequenceDiagram
    participant Client
    participant Orders as Orders API
    participant AS as Authorization Server
    participant Billing as Billing API
    Client->>Orders: Token O + proof cho Orders
    Orders->>Orders: Verify token O, proof, quyền đọc đơn
    Orders->>AS: Xin token B cho Billing theo grant/policy hỗ trợ
    Note over Orders,AS: Ví dụ service token hoặc token exchange
    AS-->>Orders: Token B aud=billing-api, sender binding phù hợp
    Orders->>Billing: Token B + sender proof/certificate của Orders
    Billing->>Billing: Verify B, binding, scope và quyền
    Billing-->>Orders: Kết quả theo policy
~~~

**Client Credentials** hoặc **Token Exchange (RFC 8693)** có thể phù hợp nếu AS và hệ thống hỗ trợ. Việc cấp token B phải dựa trên **quan hệ tin cậy và quyền thực sự của Orders**, hoặc ủy quyền thay mặt người dùng được kiểm soát. Không tự tạo token mới bằng cách sửa `aud`/`cnf`/`scope` của token ban đầu.

Nếu nhiều Resource Server được cấp cùng một access token, **mỗi RS vẫn phải kiểm tra audience, scope và sender binding đúng**; DPoP proof được tạo **mới cho từng HTTP request**.

## 13. Lỗi thường gặp và cách xử lý

| Sai lầm | Tại sao nguy hiểm? | Nguyên tắc đúng |
|---|---|---|
| “JWT ký rồi nên không cần DPoP/mTLS.” | Chữ ký JWT không chứng minh caller hiện tại giữ khóa riêng. | Dùng sender proof nếu threat model yêu cầu hạn chế lạm dụng token bị sao chép. |
| “DPoP proof ký hợp lệ là đủ.” | Attacker có thể tự ký proof bằng khóa của mình cho token bị đánh cắp. | **So thumbprint proof với `cnf.jkt` của token**. |
| “Không cần `ath` khi gọi RS.” | Proof không được ràng buộc với access token đang trình. | Xác minh `ath` đúng token của request theo RFC. |
| “Chỉ kiểm tra `htm`, không kiểm tra `htu`.” | Proof có thể được dùng ở URI ngoài ý định. | Kiểm tra method **và** URI đích hiệu lực. |
| “Có `jti` là tự chống replay.” | Nếu không lưu trạng thái, proof có thể được chấp nhận lại. | Kiểm tra uniqueness trong cửa sổ phù hợp. |
| “DPoP proof gắn cả query và body.” | RFC DPoP không bảo vệ toàn bộ request đó. | Kiểm tra nội dung request và authorization riêng. |
| “Token có `cnf` là tự an toàn.” | Thiếu kiểm tra proof/cert tại RS sẽ thành bearer. | Enforce ràng buộc ở nơi nhận. |
| “Header `X-Client-Cert` từ internet là bằng chứng mTLS.” | Caller có thể giả header. | Chỉ tin TLS certificate context từ proxy/stack đáng tin. |
| “Client auth mTLS ở AS là đủ cho mọi API.” | RS có thể không kiểm tra cert-bound token. | Tách client auth và token binding, enforce cả nơi cần. |
| “DPoP khóa không xuất được là khỏi lo XSS.” | Script độc hại có thể dùng khóa ngay tại origin/ứng dụng. | Chống XSS, bảo vệ phiên và giới hạn quyền. |
| “Đổi key rồi dùng tiếp token cũ.” | Token được cấp cho thumbprint khóa trước. | Xin token mới được AS ràng buộc với khóa mới. |
| “Đã có sender proof thì bỏ scope/audience.” | Proof không chứng minh quyền nghiệp vụ. | Tiếp tục kiểm tra issuer, audience, scope, tenant và object. |

## 14. Ma trận kiểm thử

Giả sử Orders API chỉ chấp nhận **DPoP-bound access token** có `aud=orders-api` và `scope=orders:read`. Order 42 thuộc `tenant-a` do `user-123` sở hữu.

| Token và proof | Kỳ vọng | Lý do |
|---|---|---|
| Token hợp lệ, proof đúng khóa/method/URI/`ath`, `jti` mới; user-123 đọc order 42 | **PERMIT** khi policy khác thỏa mãn. | Đúng ràng buộc, scope và quyền tài nguyên. |
| Token đúng nhưng **không có** header `DPoP` | **DENY**. | Thiếu bằng chứng bắt buộc. |
| Token `cnf.jkt=K1`, proof ký bằng K2 | **DENY**. | Proof key không khớp token. |
| Proof đúng khóa nhưng chữ ký JWS sai | **DENY**. | Bằng chứng mật mã không hợp lệ. |
| Proof đúng khóa nhưng `htm=POST` cho request GET | **DENY**. | Sai HTTP method. |
| Proof đúng khóa nhưng `htu` dành cho API khác | **DENY**. | Sai target URI. |
| Proof đúng khóa nhưng `ath` là hash của token khác | **DENY**. | Proof không gắn access token đang dùng. |
| Proof có `iat` quá cũ hoặc vượt giới hạn tương lai | **DENY**. | Ngoài cửa sổ hiệu lực. |
| Proof có `jti` đã dùng trong cửa sổ chống replay | **DENY**. | Phát lại bằng chứng. |
| RS yêu cầu nonce nhưng proof thiếu/sai nonce | **DENY** hoặc trả thử thách nonce phù hợp. | Không đáp ứng yêu cầu thử thách. |
| Access token đúng proof nhưng `aud=billing-api` | **DENY**. | Token không dành cho Orders. |
| Token và proof đúng, thiếu `orders:read` | **DENY (thường 403)**. | Thiếu scope. |
| Token/proof đủ nhưng user thuộc tenant B, order thuộc tenant A | **DENY**. | Không có object-level authorization. |
| mTLS token có `cnf["x5t#S256"]=C1`, caller trình cert C2 | **DENY**. | Certificate không khớp binding. |
| mTLS token đúng cert nhưng backend chỉ thấy header client-cert giả | **DENY**. | Header không phải TLS certificate context tin cậy. |
| Attacker đánh cắp token, **không có private key** | **DENY** khi sender binding được enforce đúng. | Chỉ sao chép token không đủ. |
| Attacker có token **và quyền dùng private key** | **Có nguy cơ bị lạm dụng**. | Sender constraining không chứng minh môi trường caller sạch. |

Nên có **integration tests qua gateway thực** với HTTPS, lỗi proxy header, key rotation, thử lại nonce, cụm nhiều RS instance và trường hợp cache chống replay gặp lỗi; chỉ unit test một hàm so sánh `cnf` chưa chứng minh toàn bộ hệ thống an toàn.

## 15. Tình huống suy luận

**Tình huống A — Ký token đã đủ?** Một JWT access token được ký bằng RSA và còn hạn. Attacker có bản sao token nhưng không có private key của AS. Họ vẫn có thể gọi API bearer token không?

**Giải thích:** Có thể. Attacker không cần ký token mới, chỉ gửi lại **nguyên token**. Sender-constraining thêm điều kiện sở hữu khóa/chứng chỉ của **client**, khác với chữ ký phát hành của **AS**.

**Tình huống B — DPoP proof của attacker.** Attacker có token với `cnf.jkt` của client hợp lệ. Họ tạo cặp khóa khác, ký DPoP proof mới. API có chấp nhận?

**Giải thích:** Không, nếu RS so sánh JWK thumbprint của proof với `cnf.jkt` của token. Chữ ký proof hợp lệ với khóa bất kỳ **không đủ**.

**Tình huống C — Proof bị copy cho endpoint khác.** Proof có `htm=GET` và `htu=https://api.example.test/orders/42`, nhưng attacker dùng nó cho `POST /orders/42/cancel`. Kết quả?

**Giải thích:** Từ chối do method không khớp; đồng thời endpoint hủy đơn cần scope/permission riêng. Nếu chỉ kiểm tra JWS signature mà bỏ `htm`/`htu` thì có lỗi nghiêm trọng.

**Tình huống D — Multi-instance replay.** RS có hai instance, mỗi instance lưu `jti` đã dùng trong RAM riêng. Request proof P đến instance 1 và ngay sau đó được gửi lại đến instance 2. Rủi ro gì?

**Giải thích:** Instance 2 có thể không biết P đã được dùng và chấp nhận replay. Thiết kế kho chống replay và phân tán state phải phù hợp cửa sổ hiệu lực và topology triển khai.

**Tình huống E — Mất private key do XSS?** Khóa DPoP không cho xuất khỏi WebCrypto, nhưng attacker đã thực thi JavaScript trong origin và có thể gọi API ký bằng khóa đó. DPoP có ngăn hoàn toàn không?

**Giải thích:** Không. Không cho xuất khóa giúp hạn chế đem khóa sang thiết bị khác, nhưng code độc hại vẫn có thể **sử dụng khóa** trong ngữ cảnh bị chiếm. Cần chống XSS, hạn chế quyền và bảo vệ phiên.

**Tình huống F — Gateway gửi certificate qua header.** Backend nhận `X-Client-Cert` nhưng header đó có thể do client bên ngoài đặt. Backend kiểm tra hash so với `cnf`. Có an toàn?

**Giải thích:** Không. Nếu header không đến từ một kênh tin cậy với proxy đã xác minh TLS client certificate, attacker có thể giả dữ liệu. Cần kiểm soát TLS termination, xóa header không đáng tin và ràng buộc proxy–backend.

**Tình huống G — Token đúng khóa nhưng sai tenant.** Client có DPoP-bound token với `orders:read`, proof hợp lệ, nhưng request đọc đơn thuộc tenant khác. Có trả dữ liệu không?

**Giải thích:** Không, trừ khi có ủy quyền liên tenant được thiết kế rõ. Sender binding chỉ kiểm tra **ai có khả năng sử dụng khóa**, không xác nhận quyền đọc bản ghi.

## Checklist triển khai

1. **Chọn mô hình đe dọa:** cần bảo vệ trường hợp token bị sao chép, kênh TLS, ứng dụng bị XSS, khóa bị lộ hay client không đáng tin? Sender-constraining giải quyết đúng một phần.
2. **Định nghĩa loại token được hỗ trợ:** bearer, DPoP-bound, mTLS certificate-bound, JWT/opaque; không tự fallback sang bearer khi proof bắt buộc thất bại.
3. **AS ràng buộc khi phát hành:** xác minh proof/cert, client/grant, resource và scope; phát token/metadata có confirmation đúng khóa.
4. **RS kiểm tra token trước cấp quyền:** trusted issuer, signature/introspection, audience, thời hạn, trạng thái và token type đúng API.
5. **DPoP proof đầy đủ:** JWS với public JWK tin cậy, allowed `alg`, `typ`, `htm`, `htu`, `iat`, `jti`, `ath` ở RS, nonce khi yêu cầu, cùng so khớp `cnf.jkt`.
6. **Chống replay phân tán:** proof ID mới mỗi request; kiểm tra trùng, thời gian, nonce, và xử lý lỗi kho chống replay đúng policy.
7. **mTLS certificate-bound:** chứng chỉ được xác minh ở TLS stack, thumbprint khớp `cnf["x5t#S256"]`; proxy–backend có kênh tin cậy, không chấp nhận header giả.
8. **Bảo vệ khóa/certificate:** nơi lưu phù hợp, tối thiểu quyền sử dụng, rotation, TTL, xử lý khi key compromise và cấp token mới sau đổi khóa.
9. **Refresh và thu hồi:** bảo vệ refresh token riêng, giới hạn cấp mới, revoke khi quyền/consent thay đổi và kiểm tra quyền hiện hành cho action nhạy cảm.
10. **Authorization không thay đổi:** scope đúng action, audience đúng RS, chủ thể đúng tenant/owner, quyền business/field và trạng thái resource.
11. **Kiểm thử phủ định:** thiếu proof, sai `ath`/`jkt`/cert, replay `jti`, sai method/URI/nonce/time, gateway spoof, token sai audience và sai tenant.

## Ghi nhớ

**Token ràng buộc người gửi** yêu cầu bên gọi API chứng minh **khả năng sử dụng khóa hoặc chứng chỉ đã được AS gắn với access token**. **DPoP** dùng bằng chứng JWS cho từng request và ràng buộc bằng `cnf.jkt`; **mTLS certificate-bound token** dùng chứng chỉ client TLS và thumbprint `cnf["x5t#S256"]`. Hai cơ chế giảm rủi ro khi attacker **chỉ sao chép token**, nhưng không bảo đảm an toàn nếu attacker dùng được khóa, điều khiển client hoặc có quyền đã cấp quá rộng. Resource Server luôn phải kiểm tra **issuer, audience, thời hạn, scope, trạng thái, principal và quyền trên từng tài nguyên**, đồng thời bảo vệ vòng đời token, refresh token và xử lý thu hồi.

### Tài liệu tham khảo

- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
- [RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens](https://www.rfc-editor.org/rfc/rfc8705)
- [RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449)
- [RFC 7638 — JSON Web Key (JWK) Thumbprint](https://www.rfc-editor.org/rfc/rfc7638)
- [RFC 7800 — Proof-of-Possession Key Semantics for JWTs](https://www.rfc-editor.org/rfc/rfc7800)
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662)
- [RFC 8693 — OAuth 2.0 Token Exchange](https://www.rfc-editor.org/rfc/rfc8693)
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725)
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068)
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700)
