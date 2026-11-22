# Claims cnf và quan hệ với khóa của bên giữ token

JWT thông thường thường được sử dụng như bearer token: bên nào nắm token đều có thể gửi token đến resource server trong thời hạn và phạm vi được cấp. Nếu token bị sao chép từ log, browser storage, thiết bị hoặc một kết nối bị xâm nhập, attacker có thể replay token mà không cần biết mật khẩu của người dùng. **Confirmation claim `cnf`** cho phép issuer ràng buộc token với một khóa hoặc credential của bên giữ token. Khi đó, bên trình token phải chứng minh đang sở hữu khóa tương ứng, thay vì chỉ gửi chuỗi JWT.

Bài này thuộc chương **Chống phát lại** của module **Security - JSON Web Token (JWT)**. Nội dung tập trung vào quan hệ giữa claim `cnf`, public key của token holder và proof-of-possession, áp dụng cho hệ thống bảo mật nói chung, độc lập ngôn ngữ lập trình và framework.

## 1. Mục tiêu và nguyên tắc

Sau bài học, người đọc có thể:

1. Phân biệt khóa ký JWT của issuer với khóa proof-of-possession của token holder.
2. Giải thích vai trò của claim `cnf` và các dạng ràng buộc khóa thường gặp.
3. Hiểu `cnf.jwk`, `cnf.jkt` và `cnf.x5t#S256` trong các profile liên quan.
4. Mô tả cách DPoP và mTLS chứng minh bên gọi đang sở hữu khóa được gắn với token.
5. Thiết kế quy trình cấp token, trình token và xác minh proof.
6. Phát hiện replay, key substitution, bearer fallback và lỗi cấu hình certificate/proxy.
7. Quản lý vòng đời khóa holder, rotation, thu hồi và chuyển đổi token.

**Nguyên tắc:** chữ ký JWT xác minh token do issuer phát hành; `cnf` xác định khóa mà bên trình token phải chứng minh đang sở hữu. Đây là hai vai trò khác nhau và cả hai phải được kiểm tra trước khi cho phép truy cập.

## 2. Bearer token và proof-of-possession

Với bearer token, quyền sử dụng gắn với việc nắm giữ token. Server không yêu cầu bên gọi chứng minh một bí mật hoặc khóa riêng khác.

Với proof-of-possession (PoP), token được ràng buộc với một khóa của holder. Khi gọi API, holder phải tạo proof bằng private key tương ứng hoặc thiết lập kết nối TLS bằng certificate đã được gắn với token.

| Đặc điểm | Bearer token | Token ràng buộc khóa (PoP) |
| --- | --- | --- |
| Điều kiện sử dụng | Có token hợp lệ | Có token hợp lệ và chứng minh sở hữu khóa được ràng buộc |
| Khi chỉ token bị đánh cắp | Attacker có thể replay trong thời hạn/phạm vi còn hiệu lực | Attacker thiếu private key/certificate thường không thể tạo proof hợp lệ |
| Thành phần bổ sung | Không bắt buộc proof theo request | DPoP proof, mTLS client certificate hoặc cơ chế PoP tương ứng |
| Vận hành | Đơn giản hơn | Phải quản lý khóa holder, proof validation và replay defense |
| Giới hạn | Token là credential có thể chuyển giao | Không bảo vệ nếu private key cũng bị đánh cắp hoặc attacker điều khiển được thao tác ký |

PoP làm giảm giá trị của một bản sao token bị đánh cắp riêng lẻ. Nó không tự ngăn malware, XSS hoặc attacker kiểm soát thiết bị sử dụng chính khóa hợp lệ để tạo proof.

## 3. Hai loại khóa có vai trò khác nhau

Một JWT có thể liên quan đến ít nhất hai cặp khóa:

1. **Issuer signing key:** private key của authorization server/issuer dùng để ký JWT; resource server dùng public key của issuer để xác minh chữ ký.
2. **Holder key:** private key của client, thiết bị hoặc workload; public key hoặc thumbprint của nó được gắn vào token qua `cnf`.

Ví dụ:

~~~text
Authorization Server:
  issuer_private_key -> ký JWT

JWT:
  iss = https://id.example.test/
  sub = user-123
  aud = orders-api
  cnf = thông tin khóa của token holder

Client / token holder:
  holder_private_key -> tạo proof cho request

Resource Server:
  issuer_public_key -> xác minh chữ ký JWT
  cnf + holder proof -> xác minh người trình token sở hữu khóa đã đăng ký
~~~

Không nhầm `cnf` với `kid` của issuer signing key. `kid` trong JOSE header thường giúp chọn khóa xác minh chữ ký của JWT; `cnf` ràng buộc token với khóa hoặc credential của holder.

Thông thường không tái sử dụng issuer signing key làm holder key. Hai khóa phục vụ principal, mục đích và vòng đời khác nhau; cần tách quyền và quản lý độc lập.

## 4. Confirmation claim `cnf` là gì?

`cnf` là một registered claim được định nghĩa trong RFC 7800. Claim này mang thông tin xác nhận khóa hoặc phương thức xác nhận mà bên trình JWT phải chứng minh đang sở hữu. `cnf` thường là một JSON object; các member cụ thể phụ thuộc phương thức ràng buộc và profile giao thức.

Ví dụ minh họa với public JWK:

~~~json
{
  "iss": "https://id.example.test/",
  "sub": "user-123",
  "aud": "orders-api",
  "exp": 1794859200,
  "cnf": {
    "jwk": {
      "kty": "EC",
      "crv": "P-256",
      "x": "base64url-public-x",
      "y": "base64url-public-y"
    }
  }
}
~~~

JWT issuer ký toàn bộ payload, vì vậy `cnf` được bảo vệ bởi chữ ký của issuer. Resource server chỉ tin giá trị `cnf` sau khi xác minh JWT và kiểm tra issuer, audience, thời hạn cùng các policy liên quan.

`cnf` **không phải proof**. Nó chỉ cho biết khóa nào phải được dùng để tạo proof. Proof được gửi hoặc thể hiện trong request theo cơ chế PoP đã chọn.

## 5. Các cách biểu diễn khóa trong `cnf`

Các profile và phần mở rộng khác nhau định nghĩa member phù hợp với phương thức xác nhận. Những dạng thường gặp:

| Member | Ý nghĩa | Profile/ứng dụng tiêu biểu |
| --- | --- | --- |
| `jwk` | Chứa public JSON Web Key của holder | Confirmation method tổng quát theo RFC 7800 |
| `jkt` | JWK thumbprint của public key holder | DPoP theo RFC 9449 |
| `x5t#S256` | SHA-256 thumbprint của client X.509 certificate | OAuth mutual-TLS certificate-bound access token theo RFC 8705 |

Không tự chọn một member rồi giả định mọi client/verifier đều hiểu nó. Issuer, client và resource server phải thống nhất cùng profile và cách tạo proof.

### 5.1. `cnf.jwk`: đưa public key vào token

`jwk` chứa public key của holder. Verifier có thể dùng key này để xác minh proof được ký bởi private key tương ứng.

Ví dụ:

~~~json
{
  "cnf": {
    "jwk": {
      "kty": "EC",
      "crv": "P-256",
      "x": "public-coordinate-x",
      "y": "public-coordinate-y"
    }
  }
}
~~~

Chỉ public parameters được đưa vào token. Với EC, không đưa private scalar `d`; với RSA, không đưa private parameters; với OKP, không đưa private key `d`. Public JWK không phải bí mật, nhưng phải được kiểm tra loại khóa, curve, thuật toán và kích thước phù hợp.

### 5.2. `cnf.jkt`: tham chiếu bằng JWK thumbprint

Thay vì nhúng toàn bộ public JWK, token có thể chứa thumbprint của khóa. DPoP sử dụng `cnf.jkt` để ràng buộc access token với public key đã được dùng trong DPoP flow.

Thumbprint được tính theo quy tắc chuẩn hóa JWK của RFC 7638, thường dùng SHA-256 và Base64url encoding. Nó đại diện cho public key; không phải hash tùy ý của JSON JWK sau khi serialize.

Ví dụ:

~~~json
{
  "cnf": {
    "jkt": "base64url-sha256-jwk-thumbprint"
  }
}
~~~

Khi client gửi DPoP proof, resource server lấy public JWK từ protected header của proof, tính thumbprint theo RFC 7638 và so sánh với `cnf.jkt` trong access token.

### 5.3. `cnf.x5t#S256`: ràng buộc với certificate

Trong OAuth mutual-TLS certificate-bound access token, `cnf.x5t#S256` chứa SHA-256 thumbprint của client certificate. Resource server lấy certificate client đã được xác thực trong TLS handshake và so sánh thumbprint với claim trong token.

Ví dụ:

~~~json
{
  "cnf": {
    "x5t#S256": "base64url-sha256-client-certificate-thumbprint"
  }
}
~~~

Đây là thumbprint của **client certificate** được dùng để chứng minh danh tính/khóa của bên gọi, không phải certificate TLS của server. Resource server phải biết certificate nào thực sự được xác thực ở kết nối đang xử lý.

## 6. Quy trình ràng buộc token với khóa holder

Một flow PoP thường có các giai đoạn:

1. **Holder tạo hoặc sở hữu khóa:** client/thiết bị/workload tạo key pair hoặc có client certificate; private key được giữ trong môi trường holder.
2. **Holder đăng ký public key hoặc certificate:** public key, thumbprint hoặc bằng chứng tương ứng được gửi trong authorization/token flow.
3. **Issuer xác thực yêu cầu:** issuer xác minh client/user/grant và kiểm tra việc holder sở hữu khóa theo profile.
4. **Issuer phát hành token:** JWT chứa `cnf` tương ứng và được issuer ký.
5. **Holder gửi request:** client gửi access token cùng proof hoặc kết nối mTLS bằng certificate đã ràng buộc.
6. **Resource server xác minh:** kiểm tra chữ ký/claims JWT, kiểm tra `cnf` và xác minh proof/certificate.
7. **Resource server chống replay:** kiểm tra freshness, nonce, request binding hoặc trạng thái proof theo profile.

Không nên chỉ nhận một public key do client tự khai báo rồi đưa vào `cnf` mà không xác minh yêu cầu được gắn với client/grant đúng. Nếu attacker có thể thay public key trong bước cấp token, ràng buộc PoP mất ý nghĩa.

## 7. DPoP: dùng proof JWT để chứng minh sở hữu khóa

Demonstrating Proof of Possession (DPoP) là cơ chế OAuth ràng buộc access token với một public key của client. Client ký một DPoP proof JWT bằng private key tương ứng cho request. Access token được cấp có thể chứa `cnf.jkt` là thumbprint của public key đó.

### 7.1. Cấu trúc DPoP proof

DPoP proof là một JWT riêng, có header và claims theo RFC 9449. Header thường có:

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

Proof được ký bằng private key tương ứng với public JWK trong header. Các claim quan trọng gồm:

| Claim | Vai trò |
| --- | --- |
| `jti` | Định danh duy nhất của proof, hỗ trợ phát hiện replay. |
| `htm` | HTTP method của request, ví dụ POST. |
| `htu` | HTTP URI đích theo quy tắc DPoP, không bao gồm query và fragment. |
| `iat` | Thời điểm tạo proof. |
| `nonce` | Giá trị challenge do server cấp khi profile/flow yêu cầu. |
| `ath` | Hash của access token trong DPoP proof gửi đến protected resource. |

Không dùng DPoP proof làm access token. Proof có mục đích gắn một request với khóa holder và request context; access token vẫn mang quyền truy cập được issuer cấp.

### 7.2. Quan hệ giữa `cnf.jkt` và proof

Giả sử access token có:

~~~json
{
  "cnf": {
    "jkt": "thumbprint-of-client-public-key"
  }
}
~~~

Client tạo DPoP proof với public JWK trong header. Resource server:

1. Xác minh access token bằng issuer public key.
2. Đọc `cnf.jkt` sau khi token đã được xác minh.
3. Tính JWK thumbprint của public key trong DPoP proof.
4. So sánh thumbprint đó với `cnf.jkt`.
5. Xác minh chữ ký proof bằng public key tương ứng.
6. Kiểm tra request method, target URI, thời điểm, nonce nếu có và `ath`.
7. Kiểm tra proof chưa từng được chấp nhận theo replay policy.

Nếu thumbprint không khớp, proof không thuộc khóa đã ràng buộc với access token và request phải bị từ chối.

### 7.3. `ath` gắn proof với access token

Khi DPoP proof được gửi đến protected resource, claim `ath` ràng buộc proof với access token cụ thể. Giá trị được tính bằng SHA-256 trên ASCII bytes của access token, sau đó Base64url encode theo RFC 9449.

Điều này ngăn việc lấy một proof hợp lệ của một token rồi ghép tùy ý với một access token khác. Resource server phải tự tính lại và so sánh theo quy tắc chuẩn; không tin giá trị `ath` do client gửi mà chưa xác minh.

### 7.4. Ví dụ request DPoP

~~~http
GET /orders/123 HTTP/1.1
Host: api.example.test
Authorization: DPoP <access-token>
DPoP: <signed-dpop-proof-jwt>
~~~

Scheme Authorization là `DPoP` trong flow DPoP, không phải `Bearer`. Resource server phải yêu cầu proof phù hợp và không âm thầm chấp nhận cùng access token như bearer token khi proof thiếu hoặc sai.

## 8. mTLS-bound access token

Mutual TLS (mTLS) xác thực cả server và client trong TLS handshake. Với certificate-bound access token, authorization server ràng buộc access token với client certificate được dùng trong quá trình cấp token.

### 8.1. Quy trình tổng quát

1. Client sở hữu private key và X.509 certificate.
2. Client thiết lập TLS connection và chứng minh sở hữu private key bằng handshake.
3. Authorization server xác minh client certificate theo trust policy.
4. Authorization server phát hành token chứa `cnf.x5t#S256` của certificate.
5. Client gửi access token trên kết nối mTLS phù hợp.
6. Resource server xác minh certificate client trên kết nối và so sánh thumbprint với claim.

### 8.2. Kiểm tra certificate

Resource server cần kiểm tra:

- TLS handshake đã xác thực client certificate thành công.
- Certificate chain, validity, usage và trust policy phù hợp.
- Thumbprint SHA-256 của certificate đúng với `cnf.x5t#S256`.
- Certificate thuộc đúng client/credential profile và chưa bị thu hồi theo policy.
- Token còn hạn, issuer/audience/scope hợp lệ.

Chỉ có header HTTP chứa certificate fingerprint do client tự gửi không phải bằng chứng mTLS. Bằng chứng phải đến từ TLS connection đã được xác thực.

### 8.3. TLS termination tại proxy

Nếu load balancer hoặc reverse proxy kết thúc TLS trước resource server, backend có thể không trực tiếp nhìn thấy TLS client certificate. Khi đó:

- Proxy phải xác minh client certificate.
- Thông tin certificate được chuyển đến backend qua kênh tin cậy và có tính toàn vẹn.
- Proxy phải xóa/ghi đè mọi header certificate do client bên ngoài tự gửi.
- Backend chỉ tin metadata từ proxy đã xác thực, không tin header cùng tên từ nguồn bất kỳ.
- Cân nhắc mTLS giữa proxy và backend hoặc cơ chế attestation tương đương.

Nếu không chứng minh được certificate ở kết nối gốc, không được coi request là mTLS-bound chỉ vì có một header chứa thumbprint.

## 9. So sánh DPoP và mTLS

| Tiêu chí | DPoP | mTLS-bound token |
| --- | --- | --- |
| Bằng chứng | JWT proof được ký cho request | Client certificate được xác thực trong TLS handshake |
| Khóa holder | Asymmetric key của client | Private key tương ứng client certificate |
| Token binding | `cnf.jkt` | `cnf.x5t#S256` |
| Ràng buộc request | Method, URI, thời điểm, token hash và nonce theo profile | TLS connection/certificate; không tự gắn proof với từng HTTP method/URI như DPoP |
| Hạ tầng | Cần client tạo proof và server xác minh | Cần TLS client authentication xuyên suốt proxy/gateway |
| Phù hợp | Public client, native app và một số SPA/API flow | Workload/service-to-service và môi trường quản lý certificate |
| Replay control | `jti`, `iat`, nonce, `ath` và replay cache | Ràng buộc với possession của private key/certificate; vẫn cần TLS/session policy |
| Vận hành | Quản lý khóa client và proof validation | Quản lý PKI, certificate issuance, renewal và TLS termination |

Hai cơ chế đều nhằm giảm khả năng sử dụng token bị đánh cắp riêng lẻ. Lựa chọn phụ thuộc client, hạ tầng TLS, khả năng giữ private key và yêu cầu vận hành.

## 10. Trình tự xác minh tại resource server

Resource server nên có một quy trình rõ ràng và fail closed:

1. Xác định token profile và phương thức sender-constraining được endpoint yêu cầu.
2. Parse JWT theo giới hạn kích thước/cấu trúc; không dùng claims trước khi xác minh.
3. Xác minh chữ ký issuer, allowlist thuật toán, `iss`, `aud`, `exp`, `nbf` và policy claims.
4. Yêu cầu `cnf` đúng cấu trúc và đúng member theo profile.
5. Lấy bằng chứng holder từ DPoP proof hoặc TLS client certificate.
6. So sánh key thumbprint/certificate thumbprint với `cnf`.
7. Xác minh proof signature hoặc TLS client authentication.
8. Kiểm tra request binding, freshness, nonce và replay state.
9. Kiểm tra scope/permission và các policy nghiệp vụ.
10. Chỉ sau đó mới thực hiện side effect hoặc trả dữ liệu bảo vệ.

Không được bỏ qua bước PoP rồi tiếp tục như bearer token nếu proof thiếu, sai chữ ký, sai thumbprint hoặc không đúng request. Một endpoint yêu cầu sender-constrained token phải thực thi yêu cầu đó trên mọi request thuộc profile.

## 11. Replay protection cho DPoP proof

Proof JWT cũng có thể bị đánh cắp và replay. Vì vậy, chỉ xác minh chữ ký proof là chưa đủ.

Các kiểm soát:

- `iat`: chỉ chấp nhận proof trong cửa sổ thời gian ngắn theo policy.
- `jti`: yêu cầu định danh proof duy nhất.
- Replay cache: lưu khóa kết hợp như thumbprint holder và `jti` đã được chấp nhận trong khoảng thời gian liên quan.
- Nonce: server có thể yêu cầu proof chứa nonce mới để giảm khả năng tạo proof trước hoặc replay ngoài luồng.
- `htm` và `htu`: proof phải gắn với method và URI của request thực tế.
- `ath`: proof tại resource server phải gắn với đúng access token.

Replay cache trong hệ thống nhiều instance cần thao tác ghi kiểm tra nguyên tử. Nếu mỗi instance có cache riêng, cùng một proof có thể được gửi đến instance khác và được chấp nhận lần nữa. Có thể dùng store phân tán hoặc cơ chế phân vùng request có bảo đảm tương đương.

Thời gian lưu replay entry phải bao phủ cửa sổ mà proof còn có thể được chấp nhận, có tính đến clock skew và nonce policy. Không giữ vô hạn nếu không cần; cũng không xóa quá sớm.

## 12. Chọn và bảo vệ khóa holder

Khóa holder quyết định độ mạnh của ràng buộc PoP. Một public key được đưa vào `cnf` không giúp ích nếu private key dễ bị sao chép hoặc mọi client cùng dùng một khóa.

### 12.1. Yêu cầu với key pair

- Dùng thuật toán và kích thước/curve được profile cho phép.
- Sinh private key bằng CSPRNG hoặc cơ chế bảo mật của hệ điều hành/KMS/HSM.
- Giữ private key trong secure storage hoặc phần cứng khi khả thi.
- Không gửi private key đến authorization server hoặc resource server.
- Không ghi private key vào log, telemetry, crash dump hoặc backup không bảo vệ.
- Dùng khóa riêng theo client/thiết bị/workload hoặc trust boundary phù hợp.
- Không tái sử dụng issuer signing key làm holder key.

### 12.2. Khóa phần cứng và non-exportable

Thiết bị có thể giữ private key trong Secure Enclave, TPM, keystore phần cứng hoặc HSM. Non-exportable key làm giảm khả năng trích xuất private material, nhưng không tự ngăn ứng dụng bị xâm nhập gọi API ký. Cần kiểm soát quyền gọi, attestation nếu profile hỗ trợ và phát hiện sử dụng bất thường.

### 12.3. Một khóa cho nhiều token

Một holder key có thể được dùng để ràng buộc nhiều access token trong cùng client/session nếu policy cho phép. Tuy nhiên, cần cân nhắc:

- Phạm vi ảnh hưởng khi key bị lộ.
- Khả năng revoke token theo từng grant.
- Liên kết giữa các ứng dụng hoặc tenant.
- Cách rotate key mà không làm gián đoạn mọi phiên.

Không dùng chung một private key cho nhiều người dùng hoặc nhiều tổ chức chỉ để giảm số lượng khóa.

## 13. Cấp token và xác minh quyền sở hữu khóa

Issuer phải biết public key trong `cnf` thực sự gắn với client/grant được xác thực. Cách xác minh phụ thuộc profile:

- Với DPoP, client gửi proof tại token endpoint; authorization server xác minh proof và lấy public key/thumbprint.
- Với mTLS, authorization server xác minh client certificate trong TLS handshake và gắn token với certificate.
- Với cơ chế JWK khác, issuer cần một bước đăng ký/attestation hoặc proof-of-possession phù hợp trước khi tin public key.

Không cho phép client gửi một `cnf` tùy ý trong request rồi để issuer chép thẳng vào access token mà không xác minh quan hệ giữa key và client. Nếu attacker có thể yêu cầu token gắn với public key do attacker kiểm soát cho một grant không thuộc họ, binding không bảo vệ được chủ thể thực sự.

`cnf` phải được tạo từ kết quả xác thực ở authorization server và được ký trong token. Resource server không nên nhận một header `cnf` do client gửi để ghi đè claim đã ký.

## 14. Key rotation và thay đổi holder key

Token đã phát hành được ràng buộc với key material hoặc certificate cụ thể. Khi holder thay khóa, token cũ không tự động chuyển sang khóa mới.

Quy trình tham khảo:

1. Holder tạo key pair/certificate mới.
2. Client thực hiện lại quy trình xác thực/đăng ký khóa theo profile.
3. Authorization server cấp token mới với `cnf` tương ứng khóa mới.
4. Client chuyển request sang token và proof mới.
5. Token cũ tiếp tục chỉ hợp lệ với khóa cũ cho đến khi hết hạn hoặc bị revoke.
6. Khi hết thời gian chuyển tiếp, revoke credential cũ và xử lý key/certificate theo policy.

Nếu private key cũ bị lộ, không chờ hết TTL thông thường. Thu hồi token/grant liên quan, ngừng tin key binding và cấp token mới sau khi xác thực lại.

### 14.1. Certificate renewal trong mTLS

Certificate renewal thường tạo certificate mới và có thumbprint khác, kể cả khi một số thông tin subject giống nhau. Token gắn với thumbprint cũ không tự động được chấp nhận trên kết nối dùng certificate mới. Client cần token được ràng buộc với certificate mới hoặc cơ chế chuyển đổi được profile cho phép.

## 15. Thu hồi và xử lý khi holder key bị xâm phạm

Các tình huống:

- Access token bị lộ nhưng private key holder còn an toàn.
- Private key holder bị export hoặc sao chép.
- Ứng dụng bị xâm nhập và attacker có thể gọi thao tác ký.
- Client certificate bị đánh cắp hoặc bị cấp sai.
- Proxy/TLS termination làm sai lệch danh tính certificate.

Phản ứng nên bao gồm:

1. Xác định issuer, client, token/grant, key thumbprint hoặc certificate serial/thumbprint liên quan.
2. Thu hồi token, refresh-token family, client credential hoặc certificate theo phạm vi ảnh hưởng.
3. Ngăn cấp token mới với holder key bị xâm phạm.
4. Cập nhật trust/revocation state và cache ở resource server.
5. Tạo khóa/certificate mới và cấp token mới sau khi xác thực.
6. Điều tra request/proof đã sử dụng trong khoảng bị xâm nhập.
7. Kiểm tra các ứng dụng hoặc tenant khác có dùng chung key hay không.

Nếu chỉ access token bị lộ mà attacker không có holder key, PoP có thể ngăn replay. Tuy nhiên, vẫn nên đánh giá nguồn rò rỉ và revoke token nếu có nguy cơ attacker lấy được private key hoặc gọi được signer.

## 16. Giới hạn bảo vệ và các tình huống PoP không đủ

PoP làm tăng yêu cầu của attacker, nhưng không biến client thành môi trường an toàn tuyệt đối.

- **Private key bị đánh cắp:** attacker có cả token và key có thể tạo proof hợp lệ.
- **XSS hoặc malware điều khiển client:** attacker có thể gọi API ký của key dù key không export được.
- **Request relay:** attacker có thể chuyển tiếp request đến một client/thiết bị hợp lệ đang giữ khóa nếu ứng dụng cho phép bị điều khiển.
- **Sai request binding:** nếu server không kiểm tra method, URI, token hash hoặc nonce đúng, proof có thể bị dùng sai ngữ cảnh.
- **Replay cache không chia sẻ:** proof có thể được replay qua instance khác.
- **TLS proxy sai cấu hình:** backend tin certificate header giả do client gửi.
- **Bearer fallback:** endpoint chấp nhận token khi proof thiếu sẽ vô hiệu hóa binding.
- **Khóa dùng chung:** compromise một client có thể ảnh hưởng nhiều token/client cùng dùng khóa.

Với browser client, PoP không thay thế XSS defense và CSRF defense. JavaScript độc hại chạy cùng origin có thể thao tác ứng dụng và yêu cầu key ký proof; cookie tự động gửi vẫn cần CSRF policy phù hợp.

## 17. Các lỗi xác minh và cách xử lý

| Tình huống | Xử lý |
| --- | --- |
| Token không có `cnf` nhưng endpoint yêu cầu PoP | Từ chối; không hạ xuống bearer. |
| `cnf` sai cấu trúc hoặc thiếu member bắt buộc | Từ chối và ghi reason code nội bộ. |
| DPoP proof không có public JWK hợp lệ | Từ chối proof. |
| JWK thumbprint không khớp `cnf.jkt` | Từ chối request. |
| Chữ ký DPoP proof sai | Từ chối request. |
| `htm` hoặc `htu` không khớp request | Từ chối request. |
| `ath` không khớp access token | Từ chối request. |
| Proof quá cũ hoặc `iat` vượt policy | Từ chối request. |
| `jti` đã được sử dụng | Từ chối replay. |
| Nonce bắt buộc nhưng thiếu/sai | Từ chối hoặc yêu cầu challenge lại theo profile. |
| mTLS certificate thumbprint không khớp `cnf.x5t#S256` | Từ chối request. |
| Backend không xác minh được metadata certificate từ proxy | Từ chối theo fail-closed policy. |
| Holder key đã bị revoke | Từ chối token/proof theo revocation policy. |

Response công khai nên dùng thông báo phù hợp với giao thức, không tiết lộ thumbprint, key ID nội bộ, chi tiết so sánh hoặc trạng thái cache. Log nội bộ có thể ghi reason code và key reference đã chuẩn hóa, không ghi token hay private key.

## 18. Ví dụ DPoP end-to-end

Giả sử mobile client tạo một EC key pair. Private key được giữ trong secure storage; public key được dùng trong DPoP proof.

**Bước 1 — Cấp token**

- Client gửi yêu cầu token kèm DPoP proof.
- Authorization server xác minh proof và lấy JWK thumbprint.
- Authorization server phát hành JWT access token có `cnf.jkt`.

**Bước 2 — Gọi API**

- Client gửi access token trong `Authorization: DPoP`.
- Client tạo proof JWT mới cho method và URI hiện tại.
- Proof được ký bằng private key holder và chứa `jti`, `htm`, `htu`, `iat`, `ath` cùng nonce nếu được yêu cầu.

**Bước 3 — Resource server xác minh**

- Xác minh chữ ký issuer và claims access token.
- Tính thumbprint public JWK trong DPoP proof.
- So sánh với `cnf.jkt`.
- Xác minh chữ ký proof và request binding.
- Kiểm tra `ath`, freshness, nonce và replay cache.
- Kiểm tra scope/permission rồi mới thực hiện hành động.

Nếu attacker chỉ sao chép access token mà không có private key, attacker không thể tự tạo proof hợp lệ cho request mới. Nếu attacker replay một proof đã thu được, `jti`, freshness, nonce và request binding giúp phát hiện hoặc giới hạn việc sử dụng lại.

## 19. Ví dụ mTLS end-to-end

Giả sử một workload gọi API nội bộ qua mTLS:

1. Workload có client certificate và private key.
2. Authorization server xác minh certificate ở TLS handshake khi cấp token.
3. Access token được ký có claim `cnf.x5t#S256` chứa thumbprint certificate.
4. Workload gọi resource server qua mTLS bằng certificate tương ứng.
5. Resource server xác minh token, lấy client certificate từ TLS session đã xác thực và tính thumbprint.
6. Nếu thumbprint trùng claim, tiếp tục kiểm tra audience, scope và policy.
7. Nếu certificate khác, request bị từ chối dù bearer token có chữ ký hợp lệ.

Khi có proxy kết thúc TLS, backend chỉ được dùng certificate metadata nếu proxy đã xác minh certificate và chuyển metadata qua một kênh tin cậy. Header do client tự gửi không phải bằng chứng.

## 20. Những anti-pattern cần tránh

| Anti-pattern | Rủi ro | Cách xử lý |
| --- | --- | --- |
| Nhầm issuer signing key với holder key | Dùng sai khóa để xác minh proof hoặc làm lộ quyền ký token. | Tách key purpose, owner và lifecycle. |
| Xem `cnf` là proof | Chỉ có claim nhưng không yêu cầu holder chứng minh sở hữu khóa. | Xác minh DPoP proof hoặc mTLS certificate trên request. |
| Tin `cnf` trước khi xác minh chữ ký JWT | Attacker có thể sửa binding claim. | Chỉ đọc claim sau khi JWT được xác minh. |
| Tin public JWK tùy ý trong request | Attacker tự chọn khóa rồi ký proof bằng khóa của mình. | So thumbprint với `cnf` đã ký trong token. |
| Đưa private key vào `cnf.jwk` | Lộ khóa holder cho mọi bên đọc token. | Chỉ chứa public parameters. |
| Dùng `kid` thay cho thumbprint binding | `kid` là lookup hint, không bảo đảm nhận diện key material theo chuẩn thumbprint. | Dùng `jkt` hoặc `x5t#S256` đúng profile. |
| Chấp nhận bearer fallback khi proof sai | Attacker có thể bỏ qua PoP. | Fail closed cho token/profile yêu cầu sender-constraining. |
| Không kiểm tra DPoP `ath` | Proof có thể bị ghép với access token khác. | Tính và xác minh `ath` theo RFC 9449. |
| Không có replay cache cho `jti` | Proof bị đánh cắp có thể được phát lại trong cửa sổ freshness. | Replay cache dùng chung hoặc cơ chế nguyên tử tương đương. |
| Tin certificate header từ client | Attacker tự khai certificate thumbprint. | Chỉ tin certificate từ TLS handshake hoặc proxy được xác thực. |
| Dùng chung holder key cho nhiều client | Compromise một client ảnh hưởng nhiều token. | Tách key theo client/device/trust boundary. |
| Thay holder key nhưng vẫn dùng token cũ | `cnf` không còn khớp key hiện tại. | Cấp token mới và chuyển đổi có kiểm soát. |

## 21. Checklist triển khai

**Token và key binding**

- [ ] Xác định rõ issuer signing key và holder key.
- [ ] `cnf` được issuer tạo và bảo vệ bằng chữ ký JWT.
- [ ] Member `jwk`, `jkt` hoặc `x5t#S256` khớp profile đang dùng.
- [ ] Không có private key material trong JWT hoặc public JWK.
- [ ] Holder key được gắn với đúng client/grant sau khi xác minh sở hữu.

**DPoP**

- [ ] Proof dùng header `typ=dpop+jwt` và thuật toán bất đối xứng được cho phép.
- [ ] JWK thumbprint của proof khớp `cnf.jkt`.
- [ ] Chữ ký proof được xác minh.
- [ ] `htm`, `htu`, `iat`, `jti`, `ath` và nonce được kiểm tra theo profile.
- [ ] Replay cache hoạt động nhất quán trên nhiều instance.
- [ ] Không có bearer fallback khi proof thiếu hoặc sai.

**mTLS**

- [ ] Client certificate được xác minh trong TLS handshake.
- [ ] Thumbprint certificate khớp `cnf.x5t#S256`.
- [ ] TLS termination/proxy chuyển certificate metadata qua kênh tin cậy.
- [ ] Header certificate do client gửi bị loại bỏ hoặc ghi đè ở trust boundary.
- [ ] Certificate renewal và revocation có quy trình cấp token mới.

**Vòng đời và vận hành**

- [ ] Private holder key được bảo vệ và không ghi log.
- [ ] Có quy trình rotation, revoke và xử lý compromise.
- [ ] Có kiểm thử token bị đánh cắp nhưng thiếu holder key.
- [ ] Có kiểm thử proof replay, key mismatch và certificate mismatch.
- [ ] Log dùng reason code an toàn, không ghi JWT hoặc private material.

## 22. Tài liệu chuẩn tham khảo

- [RFC 7800 — Proof-of-Possession Key Semantics for JSON Web Tokens (JWTs)](https://www.rfc-editor.org/rfc/rfc7800): confirmation claim `cnf` và các cách biểu diễn khóa holder.
- [RFC 7638 — JSON Web Key (JWK) Thumbprint](https://www.rfc-editor.org/rfc/rfc7638): cách tính thumbprint chuẩn hóa của JWK.
- [RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449): DPoP proof JWT, `cnf.jkt`, `ath`, nonce và replay considerations.
- [RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens](https://www.rfc-editor.org/rfc/rfc8705): mTLS client authentication và `cnf.x5t#S256`.
- [RFC 7515 — JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515): chữ ký bảo vệ JWT/JWS.
- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517): biểu diễn public key và member JWK.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700): thực hành bảo mật OAuth 2.0 hiện đại.

**Ghi nhớ:** issuer ký JWT bằng khóa của issuer; `cnf` ràng buộc token với khóa của holder. DPoP xác minh proof JWT và thumbprint `cnf.jkt`; mTLS xác minh client certificate và `cnf.x5t#S256`. Chỉ chấp nhận token sau khi xác minh cả issuer token lẫn bằng chứng sở hữu khóa, đồng thời kiểm soát freshness, replay và vòng đời holder key.
