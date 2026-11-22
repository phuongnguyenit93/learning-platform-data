# Token ràng buộc với bên gửi và ý nghĩa của proof of possession

> **Module:** SECURITY_TOKEN_SECURITY_JWT — Security - JSON Web Token (JWT)  
> **Chương:** Chống phát lại  
> **Phạm vi:** Cơ chế sender-constrained token và proof of possession trong OAuth/JWT ở mức giao thức và kiến trúc; không phụ thuộc Java, Spring hay framework cụ thể.

Với **bearer token**, bên nào nắm giữ token đều có thể thử sử dụng nó. Nếu access token bị sao chép từ log, browser storage, thiết bị hoặc một dịch vụ trung gian, attacker có thể phát lại token trong thời gian nó còn hiệu lực. Chữ ký JWT hợp lệ chỉ chứng minh token được phát hành bởi issuer có khóa tương ứng; nó không chứng minh request hiện tại đến từ đúng client đã được cấp token.

**Sender-constrained token** giảm rủi ro này bằng cách ràng buộc token với một khóa hoặc chứng thư của client. Khi sử dụng token, client phải chứng minh mình đang sở hữu khóa tương ứng. Bên nhận kiểm tra cả token lẫn bằng chứng đó. Vì vậy, chỉ đánh cắp chuỗi access token thường chưa đủ để sử dụng token từ một thiết bị khác.

Hai cơ chế OAuth tiêu biểu:

- **DPoP (RFC 9449):** client ký một proof JWT cho từng HTTP request bằng private key của client. Resource server kiểm tra proof, request method/URI, access token và khóa đã ràng buộc với token.
- **mTLS certificate-bound access token (RFC 8705):** authorization server ràng buộc token với chứng thư client; resource server kiểm tra chứng thư được trình bày trong kết nối TLS có thumbprint khớp với token.

Proof of possession không thay thế TLS, xác minh chữ ký của access token, kiểm tra audience hoặc authorization. Nó bổ sung bằng chứng rằng bên gửi request nắm giữ khóa/chứng thư mà token đã được ràng buộc.

## 1. Bearer token và giới hạn của việc chỉ giữ token

### 1.1. Bearer token

Trong mô hình bearer, access token là credential dạng “ai có token thì có thể dùng token”, miễn là token còn hợp lệ và request đáp ứng các policy khác.

Ví dụ:

~~~http
GET /orders/42 HTTP/1.1
Host: api.example.com
Authorization: Bearer eyJhbGciOi...
~~~

Resource server kiểm tra chữ ký hoặc trạng thái token, issuer, audience, thời hạn, scope và quyền trên tài nguyên. Nếu attacker lấy được token, họ có thể gửi request tương tự từ một thiết bị hoặc mạng khác.

### 1.2. Token bị sao chép có thể bị phát lại

Token có thể bị lộ qua:

- XSS hoặc browser storage có thể đọc bằng JavaScript.
- Log, tracing, analytics, URL hoặc báo cáo lỗi.
- Thiết bị đầu cuối bị malware kiểm soát.
- Một service trung gian hoặc proxy bị xâm phạm.
- Backup, snapshot hoặc kho dữ liệu lưu token.
- Người dùng vô tình chia sẻ token.

Nếu token chỉ là bearer credential, resource server không có bằng chứng mật mã nào cho biết request đến từ đúng thiết bị/client ban đầu.

### 1.3. Sender-constrained token thay đổi điều gì?

Với sender-constrained token, issuer gắn token với public key hoặc chứng thư của client. Client phải chứng minh quyền sở hữu private key tương ứng khi gọi API.

~~~mermaid
flowchart LR
    A[Authorization Server] -->|Access token gắn với key identity| C[Client giữ private key]
    C -->|Token + proof of possession| R[Resource Server]
    X[Attacker chỉ có token bị sao chép] -->|Không có private key| R
    R --> D{Token và proof đều hợp lệ?}
    D -->|Có| E[Tiếp tục kiểm tra quyền]
    D -->|Không| F[Từ chối]
~~~

Attacker chỉ có bản sao token sẽ không thể tạo proof mới nếu không có private key. Tuy nhiên, nếu attacker lấy được cả token lẫn private key, kiểm soát được client hoặc có thể gọi signing operation như một oracle, cơ chế này không còn bảo vệ được theo giả định ban đầu.

## 2. Khái niệm proof of possession và claim cnf

### 2.1. Proof of possession là gì?

Proof of possession (PoP) là bằng chứng mật mã cho thấy bên gửi request sở hữu hoặc kiểm soát khóa được gắn với credential. Bằng chứng phải liên kết với đúng token hoặc request theo giao thức.

Một cơ chế PoP thường có:

1. **Key binding:** token được issuer ràng buộc với public key hoặc certificate identity.
2. **Proof creation:** client dùng private key tương ứng tạo proof.
3. **Request binding:** proof gắn với request hoặc ngữ cảnh sử dụng token.
4. **Proof validation:** resource server kiểm tra chữ ký/proof và đối chiếu với token.
5. **Replay protection:** proof cũ không được tái sử dụng ngoài policy.

PoP chứng minh quyền kiểm soát khóa, không tự chứng minh người dùng đang hiện diện, đã đồng ý giao dịch hay có quyền truy cập tài nguyên.

### 2.2. Claim cnf

Claim **cnf** (confirmation) được định nghĩa trong RFC 7800 để biểu diễn thông tin khóa/bằng chứng mà token được ràng buộc. Trong các profile OAuth phổ biến:

- DPoP dùng **cnf.jkt** để chứa JWK thumbprint của public key client.
- mTLS certificate-bound token dùng **cnf.x5t#S256** để chứa SHA-256 thumbprint của client certificate.

Ví dụ payload JWT access token ràng buộc DPoP:

~~~json
{
  "iss": "https://id.example.com",
  "sub": "user-42",
  "aud": "https://api.example.com",
  "exp": 1794800600,
  "cnf": {
    "jkt": "base64url-jwk-thumbprint"
  }
}
~~~

Ví dụ payload JWT access token ràng buộc mTLS:

~~~json
{
  "iss": "https://id.example.com",
  "sub": "service-17",
  "aud": "https://api.example.com",
  "exp": 1794800600,
  "cnf": {
    "x5t#S256": "base64url-certificate-thumbprint"
  }
}
~~~

Đây là payload minh họa, không phải token đã ký. **cnf** phải nằm trong nội dung được issuer bảo vệ hoặc được trả về qua introspection đáng tin cậy. Resource server không được tin một **cnf** do caller tự gửi bên ngoài token.

### 2.3. Token signature và PoP proof làm hai nhiệm vụ khác nhau

| Kiểm tra | Câu hỏi được trả lời |
|---|---|
| Chữ ký JWT access token | Issuer có phát hành nội dung token này và token có bị sửa không? |
| Claims **iss**, **aud**, **exp**, type | Token có được tin cậy, dành cho API này và còn hiệu lực không? |
| **cnf** | Token bị ràng buộc với key/certificate identity nào? |
| DPoP proof hoặc mTLS certificate | Client hiện tại có chứng minh được quyền kiểm soát key/certificate đó không? |
| Scope và resource authorization | Client/subject có được phép thực hiện thao tác này không? |

Nếu access token là JWT, resource server thường xác minh chữ ký JWT và PoP riêng. Nếu access token opaque, resource server có thể lấy thông tin **cnf** từ introspection response đã xác thực. Cách kết hợp phải được định nghĩa trong contract.

## 3. DPoP: cơ chế proof ở tầng ứng dụng

### 3.1. DPoP hoạt động như thế nào?

DPoP cho phép OAuth client tạo một cặp khóa và ký proof JWT cho từng request. Public key được đưa vào protected header của proof; private key ở lại client.

Luồng tổng quát:

1. Client tạo hoặc chọn cặp khóa DPoP.
2. Client gửi proof tới authorization server khi yêu cầu token.
3. Authorization server xác minh proof và gắn token với thumbprint của public key.
4. Client gửi access token cùng proof mới tới resource server.
5. Resource server xác minh token, proof, request binding và key binding.

~~~mermaid
sequenceDiagram
    participant C as OAuth Client
    participant AS as Authorization Server
    participant RS as Resource Server
    C->>C: Tạo/giữ DPoP key pair
    C->>AS: Token request + DPoP proof
    AS->>AS: Verify proof và tính JWK thumbprint
    AS-->>C: Access token + token_type DPoP + cnf.jkt
    C->>C: Tạo proof mới cho HTTP request
    C->>RS: Authorization: DPoP token + DPoP header
    RS->>RS: Verify JWT/token, proof, htm, htu, ath, nonce
    RS->>RS: So khớp proof key với cnf.jkt
    RS-->>C: Response
~~~

DPoP là cơ chế ở tầng ứng dụng; request vẫn phải đi qua HTTPS. DPoP không mã hóa nội dung request và không thay thế TLS.

### 3.2. DPoP proof JWT

Một DPoP proof là JWT riêng, không phải access token. Header thường có:

~~~json
{
  "typ": "dpop+jwt",
  "alg": "ES256",
  "jwk": {
    "kty": "EC",
    "crv": "P-256",
    "x": "public-coordinate-x",
    "y": "public-coordinate-y"
  }
}
~~~

Header chứa public JWK để resource server xác minh chữ ký. Không đưa private key parameter vào proof. Thuật toán phải là thuật toán chữ ký bất đối xứng được DPoP cho phép; không dùng **none** hoặc HMAC.

Một proof cho request tới resource server có payload minh họa:

~~~json
{
  "jti": "proof-unique-id-001",
  "htm": "GET",
  "htu": "https://api.example.com/orders/42",
  "iat": 1794800100,
  "ath": "base64url-sha256-of-access-token",
  "nonce": "server-issued-nonce"
}
~~~

Các trường quan trọng:

| Claim | Ý nghĩa |
|---|---|
| **jti** | Định danh duy nhất của proof; dùng phát hiện proof bị phát lại |
| **htm** | HTTP method mà proof được tạo cho |
| **htu** | HTTP target URI mà proof được tạo cho; theo RFC 9449 không bao gồm query và fragment |
| **iat** | Thời điểm tạo proof |
| **ath** | Hash của access token được gửi cùng request tại resource server |
| **nonce** | Giá trị challenge do server cung cấp khi áp dụng nonce policy |

**nonce** không bắt buộc trong mọi deployment. Khi server yêu cầu nonce, client phải tạo proof mới chứa nonce được yêu cầu. Các ví dụ chỉ minh họa cấu trúc; giá trị tọa độ, thumbprint và hash không phải dữ liệu sử dụng thực tế.

### 3.3. Gửi DPoP request

Client gửi access token với scheme **DPoP** và proof trong header **DPoP**:

~~~http
GET /orders/42 HTTP/1.1
Host: api.example.com
Authorization: DPoP eyJhbGciOi...
DPoP: eyJ0eXAiOiJkcG9wK2p3dCIs...
~~~

Resource server cần xác minh cả hai thành phần. Chỉ nhận **Authorization: DPoP** mà không kiểm tra proof, hoặc chỉ xác minh proof nhưng không đối chiếu **cnf.jkt**, sẽ làm mất ý nghĩa ràng buộc.

### 3.4. Quy trình xác minh DPoP tại resource server

Một quy trình khái niệm:

1. Chọn contract và kiểm tra access token: chữ ký hoặc introspection, issuer, audience, token type, thời hạn và quyền.
2. Đọc **cnf.jkt** từ token đã được xác minh.
3. Parse DPoP proof như dữ liệu chưa tin cậy; kiểm tra **typ**, thuật toán và public JWK.
4. Xác minh chữ ký proof bằng public JWK trong header.
5. Tính JWK thumbprint của public key theo RFC 7638 và so khớp với **cnf.jkt**.
6. Kiểm tra **htm** đúng HTTP method thực tế.
7. Kiểm tra **htu** đúng URI đích theo quy tắc RFC 9449.
8. Tại resource server, kiểm tra **ath** khớp hash của access token gửi cùng request.
9. Kiểm tra **iat** trong cửa sổ thời gian cho phép.
10. Kiểm tra **jti** chưa được sử dụng; kiểm tra **nonce** nếu contract yêu cầu.
11. Chỉ sau khi mọi kiểm tra đạt mới tiếp tục authorization trên resource.

### 3.5. Ràng buộc htu và htm

**htm** ngăn proof được tạo cho một method rồi dùng cho method khác. Ví dụ proof cho GET không được tái sử dụng để gọi DELETE.

**htu** ràng buộc proof với URI đích. Khi triển khai sau reverse proxy hoặc API gateway, cần thống nhất URI mà resource server dùng để so khớp:

- Scheme, host, port và path phải được xác định theo quy tắc chuẩn.
- Query và fragment không thuộc giá trị **htu** theo RFC 9449.
- Không tin **Host**, **Forwarded** hoặc **X-Forwarded-*** từ client bất kỳ nếu proxy chưa xác thực và chuẩn hóa chúng.
- Proxy phải truyền thông tin URI gốc qua kênh tin cậy; resource server và proxy phải dùng cùng quy tắc canonicalization.

Nếu hai phía chuẩn hóa URI khác nhau, request hợp lệ có thể bị từ chối. Nếu chuẩn hóa quá lỏng, proof có thể bị dùng sai ngữ cảnh.

### 3.6. Ràng buộc ath

Khi DPoP proof được gửi cùng access token tới resource server, claim **ath** ràng buộc proof với đúng token. Resource server tính SHA-256 trên biểu diễn ASCII của access token, mã hóa kết quả theo Base64url không padding, rồi so khớp với **ath** theo RFC 9449.

Nếu attacker thay access token nhưng giữ proof cũ, **ath** không khớp. **ath** không thay thế việc xác minh chữ ký/active status của access token.

Ở token endpoint, proof được dùng để chứng minh client sở hữu khóa trong token request; khi không có access token được gửi cùng request, không có **ath** của access token để kiểm tra. Phải tuân thủ đúng ngữ cảnh của RFC 9449.

### 3.7. Nonce trong DPoP

Authorization server hoặc resource server có thể yêu cầu client dùng nonce do server cấp:

- Server trả nonce trong response header **DPoP-Nonce** theo flow áp dụng.
- Client tạo proof mới và đưa nonce vào claim **nonce**.
- Server kiểm tra nonce đúng, còn trong thời hạn và chưa bị dùng sai policy.
- Nonce có thể thay đổi theo server, client hoặc phiên làm việc; client không được tự giả định một nonce dùng được ở mọi nơi.

Nonce giúp server kiểm soát freshness và giảm khả năng attacker chuẩn bị proof từ trước. Nó không loại bỏ nhu cầu kiểm tra **jti**, **iat** và request binding.

## 4. mTLS certificate-bound access token

### 4.1. mTLS là gì trong ngữ cảnh này?

mTLS là TLS trong đó client cũng trình bày chứng thư để server xác thực client ở tầng kết nối. Trong OAuth certificate-bound access token, authorization server gắn access token với thumbprint của client certificate. Resource server kiểm tra chứng thư client trong kết nối hiện tại và so sánh với thông tin ràng buộc trong token.

Không nhầm client certificate với server certificate:

- Server certificate giúp client xác minh máy chủ.
- Client certificate được trình bày để server xác minh client.
- Certificate-bound access token gắn token với client certificate cụ thể.

### 4.2. Luồng cấp và sử dụng token

~~~mermaid
sequenceDiagram
    participant C as OAuth Client
    participant AS as Authorization Server
    participant RS as Resource Server
    C->>AS: TLS handshake + client certificate
    AS->>AS: Xác thực client certificate
    C->>AS: Token request qua mTLS
    AS-->>C: Access token có cnf.x5t#S256
    C->>RS: TLS handshake + cùng client certificate
    RS->>RS: Xác thực client certificate
    C->>RS: Request + access token
    RS->>RS: So thumbprint cert với cnf.x5t#S256
    RS-->>C: Response nếu token và certificate hợp lệ
~~~

Authorization server và resource server phải cùng hiểu profile mTLS và cách xác minh certificate. Việc client dùng HTTPS thông thường mà không trình bày client certificate không đáp ứng certificate binding.

### 4.3. Claim cnf.x5t#S256

Claim **cnf.x5t#S256** chứa Base64url-encoded SHA-256 thumbprint của client certificate theo RFC 8705.

Resource server:

1. Xác minh access token hoặc lấy metadata qua introspection đáng tin cậy.
2. Đọc **cnf.x5t#S256**.
3. Lấy client certificate đã được xác thực cho kết nối hiện tại.
4. Tính thumbprint theo quy tắc RFC 8705.
5. So sánh với giá trị trong token.
6. Từ chối nếu không có certificate, certificate không hợp lệ hoặc thumbprint không khớp.

Không so sánh subject name hoặc chuỗi issuer của certificate thay cho thumbprint nếu contract yêu cầu certificate binding. Hai certificate có thể có subject tương tự nhưng là hai key pair khác nhau.

### 4.4. TLS termination tại proxy hoặc load balancer

Trong kiến trúc thực tế, TLS có thể kết thúc tại load balancer/API gateway thay vì resource server. Khi đó cần bảo đảm:

- Proxy thực sự yêu cầu và xác minh client certificate.
- Proxy truyền thông tin certificate/thumbprint qua kênh nội bộ được xác thực và bảo vệ.
- Proxy loại bỏ header do client tự gửi có thể giả mạo certificate identity.
- Resource server chỉ tin metadata certificate từ proxy được cấu hình tin cậy.
- Không cho phép request đi đường vòng trực tiếp tới backend để bỏ qua mTLS.
- Có quy tắc rõ khi proxy chuyển tiếp qua nhiều hop.

Không được tin một header như **X-Client-Cert** chỉ vì nó xuất hiện trong request. Nếu client bên ngoài có thể tự đặt header đó, attacker có thể giả mạo identity. Cần strip header đầu vào, tạo lại tại proxy tin cậy và bảo vệ kết nối proxy-to-backend.

## 5. So sánh DPoP và mTLS

| Tiêu chí | DPoP | mTLS certificate-bound token |
|---|---|---|
| Bằng chứng | JWT proof ký bằng private key client | Client certificate trong TLS handshake |
| Key identity trong token | **cnf.jkt** | **cnf.x5t#S256** |
| Ràng buộc request | Method, URI, access-token hash và các claim proof | Certificate được dùng trên kết nối TLS |
| Mức triển khai | Tầng ứng dụng, qua header DPoP | Tầng TLS và OAuth |
| Hạ tầng cần hỗ trợ | Client tạo proof, AS/RS xác minh DPoP | TLS client authentication ở AS/RS hoặc proxy tin cậy |
| Replay control | **jti**, **iat**, nonce và request binding | TLS channel/certificate binding; cần bảo vệ token và kết nối theo profile |
| Tương thích môi trường browser | Có thể triển khai nhưng phải bảo vệ DPoP key | Phụ thuộc khả năng quản lý client certificate trong browser |
| Vận hành proxy | Cần URI canonicalization và header proof được bảo toàn | Cần chuyển tiếp certificate identity an toàn |
| Khả năng thay certificate/key | Tạo/bind token với key mới | Certificate mới có thumbprint khác; token cần binding phù hợp |

Hai cơ chế đều yêu cầu bảo vệ private key. DPoP không thay thế mTLS cho bảo vệ kênh; mTLS cũng không thay thế xác minh JWT, audience hoặc scope. Lựa chọn dựa trên client type, hạ tầng TLS, khả năng quản lý khóa và yêu cầu tương thích.

## 6. Chọn và quản lý khóa của client

### 6.1. Phân biệt khóa issuer và khóa client

Trong một hệ thống DPoP:

- **Issuer signing key** ký access token JWT để resource server xác minh issuer.
- **Client DPoP key** ký proof để chứng minh request đến từ bên giữ private key.

Hai khóa có chủ sở hữu, vòng đời và mục đích khác nhau. Không dùng private signing key của authorization server làm DPoP key cho client.

Trong mTLS:

- **Issuer signing key** bảo vệ access token nếu token là JWT.
- **Client certificate private key** chứng minh client sở hữu certificate đã được ràng buộc với token.

Không nhầm key ID của issuer với thumbprint của client key/certificate.

### 6.2. Sinh và lưu DPoP private key

Client cần:

- Sinh key pair bằng nguồn ngẫu nhiên mật mã.
- Dùng thuật toán/curve được DPoP và các bên hỗ trợ.
- Giữ private key ở nơi hạn chế truy cập; không gửi private key trong proof.
- Không ghi private key hoặc serialized secret vào log, storage không bảo vệ hay telemetry.
- Xác định key scope: theo client registration, browser profile, device, user session hoặc installation.
- Có quy trình backup/recovery phù hợp; không sao chép key tùy tiện giữa thiết bị.

Nếu khóa được lưu bằng Web Crypto non-extractable key trong browser, việc export private key có thể bị hạn chế. Tuy nhiên, script độc hại chạy trong cùng origin vẫn có thể gọi các thao tác ký mà ứng dụng cho phép nếu nó truy cập được key handle/runtime. Non-extractable không đồng nghĩa XSS không thể sử dụng key.

### 6.3. Vòng đời và luân chuyển khóa

Khi client key bị lộ, mất hoặc thay đổi:

1. Dừng sử dụng key cũ.
2. Tạo key pair hoặc certificate mới.
3. Xin access token mới được ràng buộc với key identity mới.
4. Thu hồi token/grant gắn với key cũ theo policy.
5. Resource server từ chối token cũ hoặc proof dùng key cũ khi trạng thái revoke có hiệu lực.
6. Xóa key cũ khỏi nơi lưu trữ và thiết bị có thể truy cập.

Không thể đổi **cnf.jkt** hoặc **cnf.x5t#S256** của token đã ký mà không có issuer phát hành token mới. Nếu private key client bị mất, client thường phải thực hiện lại flow cấp token để tạo binding mới.

### 6.4. Chia sẻ key giữa nhiều thiết bị

Nếu nhiều thiết bị dùng chung một DPoP private key hoặc client certificate, việc thu hồi và audit trở nên khó hơn:

- Một thiết bị bị xâm phạm có thể ảnh hưởng các thiết bị còn lại.
- Không thể phân biệt proof đến từ thiết bị nào chỉ dựa trên key chung.
- Thu hồi một thiết bị có thể buộc thay key cho tất cả.

Nếu cần thu hồi riêng từng thiết bị, nên có key identity riêng theo thiết bị hoặc installation và trạng thái quản lý tương ứng.

## 7. Replay protection cho proof

### 7.1. Vì sao proof cũng cần chống phát lại?

DPoP proof là JWT đã ký. Nếu attacker sao chép được cả HTTP request và proof, họ có thể thử gửi lại proof trong khoảng thời gian proof còn được chấp nhận. Vì vậy, chữ ký proof không tự làm proof dùng một lần.

Resource server nên kiểm tra:

- **jti** chưa từng được chấp nhận trong cửa sổ replay.
- **iat** nằm trong cửa sổ thời gian cho phép.
- Nonce đúng nếu server yêu cầu.
- **htm**, **htu** và **ath** khớp request/token hiện tại.
- Key thumbprint khớp **cnf.jkt**.

### 7.2. Replay cache

Một replay cache có thể dùng key kết hợp:

~~~text
replay_key = issuer_or_resource_context + jkt + jti
~~~

Lưu dấu proof đã chấp nhận trong thời gian ít nhất bao phủ cửa sổ proof còn được phép. TTL cần tính đến clock skew và thời gian tối đa server chấp nhận proof cũ.

Không dùng riêng **jti** nếu có nhiều client/key namespace và khả năng trùng ID. Không lưu raw access token hoặc private key trong replay cache.

### 7.3. Nhiều resource server và tính nhất quán

Nếu cùng proof có thể được gửi tới nhiều node hoặc nhiều region:

- Replay cache phải được chia sẻ hoặc có cơ chế phân vùng bảo đảm proof không được chấp nhận lặp ngoài ý muốn.
- Cập nhật **jti** cần atomic để hai request đồng thời không cùng vượt qua.
- Cần xác định proof replay scope là theo resource server, issuer, key hay toàn bộ trust domain.
- Cache TTL phải đủ dài theo cửa sổ **iat** và policy.
- Theo dõi cache outage, eviction và replication lag.

Nếu mỗi node dùng cache cục bộ độc lập, attacker có thể phát lại cùng proof tới node khác trước khi trạng thái đồng bộ. Kiến trúc phải đánh giá rủi ro này và chọn cơ chế phù hợp.

### 7.4. Nonce và replay cache bổ trợ nhau

Nonce làm proof phụ thuộc vào challenge mới do server phát hành. Replay cache phát hiện proof có **jti** đã được dùng. Hai biện pháp giải quyết các khía cạnh khác nhau:

| Cơ chế | Tác dụng |
|---|---|
| **iat** | Giới hạn tuổi proof |
| **jti** + replay cache | Phát hiện cùng proof được gửi lại |
| **nonce** | Buộc proof gắn với challenge server cấp |
| **htm**/**htu** | Gắn proof với method và URI |
| **ath** | Gắn proof với access token |
| **cnf.jkt** | Gắn proof key với token |

Không xem nonce như thay thế hoàn toàn replay cache nếu contract yêu cầu phát hiện proof reuse.

## 8. Những giới hạn của sender-constrained token

### 8.1. Không chống được attacker lấy cả token lẫn khóa

Nếu attacker lấy được access token và private key, họ có thể tạo proof mới. Với mTLS, nếu attacker có private key của client certificate hoặc kiểm soát được client TLS stack, certificate binding không còn bảo vệ được.

Vì vậy, PoP chuyển rủi ro từ “chỉ cần lấy token” sang “phải kiểm soát cả token và key/proof capability”; nó không loại bỏ nhu cầu bảo vệ endpoint và key store.

### 8.2. XSS vẫn có thể hành động trong phiên

Trong ứng dụng browser, XSS có thể:

- Gọi API ngay trong origin bằng quyền của người dùng.
- Đọc access token nếu token được JavaScript lưu trong storage.
- Gọi hàm ký DPoP nếu script có thể truy cập key handle hoặc API ký của ứng dụng.
- Thay đổi dữ liệu trước khi gửi request hoặc lừa người dùng xác nhận hành động.

DPoP có thể làm token bị exfiltrate khó dùng từ một thiết bị khác nếu private key không bị lộ và signing capability không bị lạm dụng. Nhưng DPoP không thay thế XSS prevention, CSP, authorization hoặc xác nhận giao dịch.

### 8.3. Không tự bảo vệ request body hoặc ý định người dùng

DPoP ràng buộc method, URI và access token theo chuẩn; nó không mặc định ký toàn bộ HTTP body. Nếu endpoint thực hiện chuyển tiền, đổi email hoặc hành động nhạy cảm, cần integrity/authentication cho dữ liệu nghiệp vụ và xác nhận ý định theo threat model riêng.

Không suy ra rằng proof hợp lệ có nghĩa người dùng đã nhìn thấy hoặc đồng ý với nội dung giao dịch.

### 8.4. Không thay thế các kiểm tra token thông thường

Ngay cả khi PoP hợp lệ, resource server vẫn phải kiểm tra:

- Chữ ký/active status của access token.
- Issuer và audience.
- Token type/profile.
- Thời hạn và trạng thái thu hồi.
- Scope, subject, actor và quyền trên tài nguyên.
- Các ràng buộc nghiệp vụ và chính sách rủi ro.

Một proof hợp lệ gắn với token hết hạn hoặc sai audience vẫn phải bị từ chối.

## 9. Triển khai qua gateway, proxy và nhiều hop

### 9.1. DPoP qua reverse proxy

Proxy phải bảo toàn DPoP header và chuyển tiếp request theo cách không làm thay đổi method/URI semantics mà resource server xác minh. Nếu proxy rewrite path hoặc scheme:

- Xác định URI bên client ký và URI resource server dùng để xác minh.
- Dùng cấu hình canonicalization nhất quán.
- Chỉ tin forwarded metadata từ proxy được xác thực.
- Không cho client tự ghi đè forwarded host/proto.
- Kiểm thử cả request trực tiếp và request đi qua gateway.

### 9.2. mTLS qua TLS termination

Nếu TLS kết thúc tại gateway, backend không trực tiếp thấy TLS client certificate ban đầu. Cần một mô hình tin cậy để gateway chuyển certificate identity:

- Gateway xác thực certificate và tính thumbprint.
- Gateway xóa mọi header certificate do client gửi.
- Gateway tạo metadata nội bộ đã xác thực.
- Kết nối gateway-backend được bảo vệ và backend chỉ nhận traffic từ gateway.
- Backend đối chiếu thumbprint với **cnf.x5t#S256**.

Nếu backend chấp nhận header certificate từ Internet hoặc từ nguồn không xác thực, attacker có thể giả mạo PoP identity.

### 9.3. Service mesh và nhiều hop

Khi request đi qua nhiều service, cần quyết định service nào là sender được ràng buộc:

- Client ban đầu có giữ token và key không?
- Gateway có xác minh PoP rồi chuyển tiếp identity đã xác minh không?
- Service trung gian có token exchange và trở thành actor mới không?
- Token mới có audience của service đích và **cnf** phù hợp không?

Không chuyển tiếp token DPoP/mTLS như bearer token sau khi bỏ proof/certificate binding. Nếu service trung gian cần gọi downstream thay mặt user, dùng delegation/token exchange và cấp token phù hợp cho service đó.

## 10. Lỗi xác minh và phản hồi

### 10.1. Các nhóm lỗi thường gặp

| Lỗi | Nguyên nhân | Hành vi |
|---|---|---|
| Token không có **cnf** nhưng endpoint yêu cầu sender constraint | Token sai profile | Từ chối |
| DPoP proof thiếu hoặc sai **typ** | Proof không đúng định dạng | Từ chối |
| DPoP algorithm không được phép | Thuật toán không phù hợp | Từ chối |
| Chữ ký proof sai | Không chứng minh được quyền sở hữu key | Từ chối |
| JWK thumbprint không khớp **cnf.jkt** | Proof dùng key khác token binding | Từ chối |
| **htm** hoặc **htu** không khớp | Proof thuộc request khác | Từ chối |
| **ath** không khớp access token | Proof gắn với token khác | Từ chối |
| **iat** quá cũ/tương lai bất hợp lý | Proof ngoài time window | Từ chối |
| **jti** đã dùng | Replay | Từ chối |
| Nonce thiếu/sai khi server yêu cầu | Challenge chưa được đáp ứng | Từ chối và yêu cầu proof mới theo flow |
| mTLS certificate không có hoặc không hợp lệ | Không có client certificate được xác thực | Từ chối |
| Certificate thumbprint không khớp **cnf.x5t#S256** | Token được bind với certificate khác | Từ chối |

### 10.2. Phản hồi lỗi DPoP

DPoP định nghĩa các error response như **invalid_dpop_proof** và cơ chế nonce challenge theo RFC 9449. Khi yêu cầu nonce, server có thể trả nonce mới để client tạo proof khác. Client không nên lặp lại cùng proof cũ; phải tạo proof mới với **jti** mới và nonce phù hợp.

Không đưa chi tiết private key, certificate nội bộ, thumbprint đầy đủ hoặc token vào thông báo lỗi công khai. Log nội bộ có thể dùng mã lỗi, contract ID, key identifier đã được chuẩn hóa và request ID.

### 10.3. Phân biệt lỗi xác thực và lỗi quyền

- Token/proof/certificate không hợp lệ: request không vượt qua authentication.
- Token và proof hợp lệ nhưng thiếu scope hoặc quyền tài nguyên: từ chối authorization.
- Status service hoặc replay cache bắt buộc không khả dụng: xử lý theo availability policy đã định; không tự động coi proof là hợp lệ.

## 11. Ví dụ cấu hình hợp đồng

### 11.1. Profile DPoP

~~~yaml
sender_constraint:
  type: dpop
  token_type: DPoP
  confirmation_claim:
    name: cnf.jkt
    algorithm: jwk-thumbprint-rfc7638
  proof:
    typ: dpop+jwt
    allowed_algorithms:
      - ES256
    required_claims:
      - jti
      - htm
      - htu
      - iat
      - ath
    nonce_policy: server_challenge_when_required
    max_proof_age_seconds: 60
    replay_detection:
      enabled: true
      key: jkt_and_jti
  transport:
    tls_required: true
~~~

Đây là ví dụ cấu hình khái niệm, không phải schema chuẩn. Các thuật toán, thời gian và nonce policy cần phù hợp với RFC 9449 và profile cụ thể. **ath** áp dụng cho proof gắn với access token tại resource server.

### 11.2. Profile mTLS

~~~yaml
sender_constraint:
  type: mtls
  confirmation_claim:
    name: cnf.x5t#S256
    algorithm: sha256_certificate_thumbprint
  client_certificate:
    require_valid_chain: true
    check_validity: true
    check_revocation: according_to_pki_policy
  resource_server:
    compare_presented_certificate_thumbprint: true
    trusted_tls_terminators:
      - api-gateway-prod
  transport:
    tls_required: true
~~~

Đây là ví dụ khái niệm. Trust chain, certificate policy, TLS termination và revocation phải được đặc tả theo PKI/hạ tầng thật.

## 12. Ma trận kiểm thử sender-constrained token

| ID | Tình huống | Kết quả mong đợi |
|---|---|---|
| P01 | DPoP access token và proof đúng key, request, ath | Có thể chấp nhận sau các kiểm tra token/quyền |
| P02 | Chỉ có access token, thiếu DPoP proof | Từ chối |
| P03 | Proof ký bằng key khác **cnf.jkt** | Từ chối |
| P04 | Proof **typ** sai hoặc thiếu | Từ chối |
| P05 | Proof dùng **alg: none** hoặc HMAC | Từ chối |
| P06 | **htm** khác HTTP method thực tế | Từ chối |
| P07 | **htu** khác URI đích theo canonicalization contract | Từ chối |
| P08 | **ath** không khớp access token | Từ chối |
| P09 | **iat** ngoài cửa sổ cho phép | Từ chối |
| P10 | Gửi lại cùng **jti**/proof trong replay window | Từ chối |
| P11 | Nonce bị yêu cầu nhưng thiếu hoặc sai | Trả challenge/lỗi theo RFC 9449 |
| P12 | Hai request đồng thời dùng cùng proof | Chỉ request đầu tiên được chấp nhận |
| P13 | Token DPoP bị gửi với scheme Bearer | Từ chối theo profile |
| P14 | mTLS token không có client certificate | Từ chối |
| P15 | Certificate hợp lệ nhưng thumbprint khác **cnf.x5t#S256** | Từ chối |
| P16 | Header certificate do client tự gửi qua proxy | Không tin; proxy phải strip và tạo metadata tin cậy |
| P17 | DPoP request qua proxy rewrite URI | Xác minh theo URI canonicalization đã thống nhất |
| P18 | Client key bị rotate nhưng token vẫn bind key cũ | Token cũ bị từ chối hoặc xử lý theo transition policy |
| P19 | Access token hết hạn nhưng proof hợp lệ | Từ chối |
| P20 | Token/proof hợp lệ nhưng thiếu scope | Từ chối quyền |
| P21 | Replay cache không khả dụng | Áp dụng fail policy; không bỏ qua replay check ngoài contract |
| P22 | Attacker có token nhưng không có private key | Không tạo được proof/certificate binding hợp lệ |

## 13. Checklist thiết kế và vận hành

**Hợp đồng token**

- [ ] Xác định endpoint/profile nào yêu cầu bearer hay sender-constrained token.
- [ ] Chọn DPoP hoặc mTLS theo client, hạ tầng và threat model.
- [ ] Định nghĩa **cnf.jkt** hoặc **cnf.x5t#S256** và cách đối chiếu.
- [ ] Phân biệt issuer signing key với client PoP key/certificate.
- [ ] Giữ HTTPS/TLS bắt buộc; PoP không thay thế bảo vệ kênh.

**DPoP**

- [ ] Proof có **typ=dpop+jwt** và thuật toán chữ ký bất đối xứng được phép.
- [ ] Public JWK không chứa private parameters.
- [ ] Chữ ký proof và JWK thumbprint khớp **cnf.jkt**.
- [ ] Kiểm tra **htm**, **htu**, **iat**, **jti** và **ath** đúng ngữ cảnh.
- [ ] Nonce policy được định nghĩa và client tạo proof mới khi có challenge.
- [ ] Replay cache có namespace, TTL, atomicity và xử lý multi-region phù hợp.
- [ ] URI canonicalization qua proxy được thống nhất.

**mTLS**

- [ ] Client certificate được xác thực ở TLS layer.
- [ ] Thumbprint certificate khớp **cnf.x5t#S256**.
- [ ] TLS termination/proxy chuyển certificate identity qua kênh tin cậy.
- [ ] Header certificate do client gửi bị loại bỏ.
- [ ] Có quy trình certificate issuance, rotation, expiry và revocation.

**Key lifecycle và giới hạn**

- [ ] Client private key được bảo vệ, có scope và vòng đời rõ.
- [ ] Có quy trình thay key và cấp token binding mới.
- [ ] XSS, malware và khả năng gọi signing oracle được đánh giá.
- [ ] Không coi PoP là bằng chứng user intent hoặc quyền truy cập.
- [ ] Vẫn kiểm tra issuer, audience, thời hạn, trạng thái, scope và quyền tài nguyên.
- [ ] Có test replay, key mismatch, nonce, proxy và dependency outage.

**Điều cần nhớ:** Sender-constrained token làm cho việc đánh cắp riêng access token khó chuyển thành quyền truy cập từ một client khác. DPoP chứng minh quyền sở hữu private key bằng proof gắn với request; mTLS chứng minh client dùng certificate đã được ràng buộc với token. Hiệu quả phụ thuộc vào việc bảo vệ khóa, xác minh **cnf**, chống replay proof và duy trì đúng trust boundary qua proxy. PoP bổ sung một lớp bảo vệ cho bearer token, không thay thế TLS, XSS prevention hoặc authorization.

## Tài liệu tham khảo

- [RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449): DPoP proof, request binding, nonce và token binding.
- [RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens](https://www.rfc-editor.org/rfc/rfc8705): mTLS client authentication và certificate-bound access token.
- [RFC 7800 — Proof-of-Possession Key Semantics for JSON Web Tokens (JWTs)](https://www.rfc-editor.org/rfc/rfc7800): Claim **cnf** và semantics key confirmation.
- [RFC 7638 — JSON Web Key (JWK) Thumbprint](https://www.rfc-editor.org/rfc/rfc7638): Tính thumbprint cho public JWK.
- [RFC 7515 — JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515): Cấu trúc JWS và chữ ký.
- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517): JWK và các tham số khóa.
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519): JWT claims và cấu trúc token.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): Lấy trạng thái và metadata token từ authorization server.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700): Thực hành bảo vệ OAuth token và sender-constrained token.
