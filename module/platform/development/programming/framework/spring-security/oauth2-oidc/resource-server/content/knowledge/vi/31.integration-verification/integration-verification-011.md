# DPoP hoặc ràng buộc khóa khi phiên bản và cấu hình có hỗ trợ

OAuth 2.0 Bearer access token có một đặc tính quan trọng: bất kỳ bên nào sở hữu token đều có thể trình token đó để gọi API, miễn token còn hợp lệ và có đủ quyền. Nếu token bị lộ qua log, browser storage, memory dump hoặc một dependency bị compromise, kẻ khác có thể dùng token cho đến khi token hết hạn hoặc bị thu hồi.

**Sender-constrained access token** giảm rủi ro này bằng cách ràng buộc token với một khóa mà client phải chứng minh đang sở hữu khi sử dụng token. Hai cơ chế thường gặp là:

- **DPoP (Demonstrating Proof of Possession):** client ký một proof JWT cho từng request bằng private key. Resource Server kiểm tra proof và đối chiếu public-key thumbprint với token.
- **mTLS certificate-bound access token:** client dùng certificate trong TLS mutual authentication; Resource Server so certificate thumbprint của kết nối với confirmation claim trong token.

Các cơ chế này chỉ có tác dụng khi Authorization Server phát hành token theo đúng profile và Resource Server thực sự kiểm tra proof/binding. Việc một ứng dụng bật JWT Resource Server, HTTPS hoặc mTLS ở một connector **không tự động chứng minh token đã được ràng buộc khóa**.

Bài này tập trung vào cách hiểu DPoP theo RFC 9449, cách đối chiếu với mTLS và cách kiểm chứng khả năng hỗ trợ của phiên bản/cấu hình Spring Security. Tên API, DSL và property có thể khác theo release; hãy xác nhận tính năng ở đúng version mà dự án đang dùng.

## 1. Vì sao cần ràng buộc access token với khóa?

Với Bearer token thông thường, request chỉ cần mang token:

~~~http
GET /api/orders/123 HTTP/1.1
Host: orders.example.com
Authorization: Bearer <access-token>
~~~

Resource Server xác minh token, sau đó kiểm tra scope và các policy khác. Nếu attacker đánh cắp chuỗi token, họ có thể gửi request tương tự từ một máy khác.

Với sender-constrained token, client cần chứng minh quyền sở hữu private key đã được liên kết với token. Một token bị lấy riêng lẻ không đủ để gọi API nếu attacker không có khóa tương ứng.

| Cơ chế | Bằng chứng client gửi khi gọi API | Binding trong access token |
| --- | --- | --- |
| Bearer token | Chỉ access token | Không bắt buộc có confirmation key |
| DPoP | Access token + DPoP proof JWT được ký cho request | cnf.jkt: thumbprint của public JWK |
| mTLS certificate-bound | Access token + client certificate trong TLS handshake | cnf.x5t#S256: thumbprint của X.509 certificate |

DPoP và mTLS đều hướng đến proof of possession nhưng dùng loại khóa và cách chứng minh khác nhau. Không so sánh trực tiếp JWK thumbprint với certificate thumbprint.

### DPoP không thay thế TLS

DPoP bảo vệ việc sử dụng token khỏi tình huống token bị đánh cắp riêng lẻ. TLS vẫn cần thiết để bảo vệ tính bí mật và toàn vẹn của HTTP request, xác thực server và ngăn quan sát/chỉnh sửa dữ liệu trên đường truyền.

DPoP proof không mã hóa access token, không thay thế TLS server certificate validation và không tự bảo vệ dữ liệu nghiệp vụ trong response.

## 2. DPoP hoạt động ở mức giao thức

DPoP được mô tả trong RFC 9449. Client tạo một cặp khóa bất đối xứng và giữ private key ở phía client. Public key được đưa vào header của DPoP proof JWT. Client ký một proof mới cho request cần thực hiện.

Một DPoP proof có hai phần:

**Protected header** thường chứa:

- typ có giá trị dpop+jwt.
- alg là thuật toán chữ ký bất đối xứng được chấp nhận.
- jwk là public JWK dùng để xác minh proof; không chứa private key.

**Payload** thường chứa:

- jti: định danh duy nhất của proof.
- htm: HTTP method của request.
- htu: URI đích theo quy tắc DPoP, không gồm query và fragment.
- iat: thời điểm tạo proof.
- ath: hash của access token khi proof được dùng tại Resource Server.
- nonce: nonce do server cấp nếu server yêu cầu.

Một payload minh họa ở Resource Server:

~~~json
{
  "jti": "proof-unique-id-7f8c",
  "htm": "GET",
  "htu": "https://orders.example.com/api/orders/123",
  "iat": 1794746400,
  "ath": "base64url-sha256-of-access-token",
  "nonce": "server-issued-nonce-if-required"
}
~~~

Protected header minh họa:

~~~json
{
  "typ": "dpop+jwt",
  "alg": "ES256",
  "jwk": {
    "kty": "EC",
    "crv": "P-256",
    "x": "public-x-coordinate",
    "y": "public-y-coordinate"
  }
}
~~~

Đây là ví dụ cấu trúc, không phải proof có chữ ký hợp lệ. Public JWK chỉ chứa tham số public cần để xác minh; không được đưa private scalar/key vào header.

## 3. Quy trình lấy DPoP-bound access token

Khi client yêu cầu token, nó gửi một DPoP proof đến token endpoint. Ở giai đoạn này chưa có access token để đưa vào ath, vì vậy proof cho token endpoint không có ath theo cách sử dụng ở Resource Server.

~~~mermaid
sequenceDiagram
    autonumber
    participant C as OAuth Client
    participant AS as Authorization Server
    C->>C: Tạo proof JWT bằng private key
    C->>AS: POST /token + DPoP proof
    AS->>AS: Verify proof signature, htm, htu, iat, jti, nonce
    AS->>AS: Tính JWK thumbprint (jkt)
    AS-->>C: Access token + token_type=DPoP
    Note over AS,C: Token được ràng buộc với public key của proof
~~~

Authorization Server có thể phát hành access token có confirmation claim:

~~~json
{
  "iss": "https://auth.example.com",
  "sub": "service-orders",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "cnf": {
    "jkt": "base64url-jwk-thumbprint"
  }
}
~~~

Giá trị jkt là JWK thumbprint theo quy tắc RFC 7638. Nó đại diện cho public key trong proof, không phải hash của toàn bộ JWT proof và cũng không phải thumbprint của X.509 certificate.

Token response có thể chứa token_type là DPoP. Client phải giữ access token cùng private key tương ứng. Nếu Authorization Server không phát token có confirmation binding hoặc không trả token type theo DPoP profile, không nên tự coi token đó là DPoP-bound chỉ vì request token có kèm một proof.

## 4. Quy trình gọi Resource Server

Khi gọi API, client gửi access token bằng scheme DPoP và gửi proof trong header DPoP:

~~~http
GET /api/orders/123 HTTP/1.1
Host: orders.example.com
Authorization: DPoP <access-token>
DPoP: <signed-dpop-proof-jwt>
~~~

Resource Server phải xác minh cả access token và proof. Trình tự khái niệm:

1. Xác định request dùng DPoP authorization scheme.
2. Xác minh access token theo profile của issuer: signature hoặc introspection, issuer, audience, expiry, token type và các claims bắt buộc.
3. Đọc cnf.jkt từ token đã xác minh.
4. Parse DPoP proof và kiểm tra protected header, public JWK, typ và alg.
5. Xác minh chữ ký proof bằng public JWK trong proof.
6. Tính JWK thumbprint và so sánh với cnf.jkt trong access token.
7. Kiểm tra htm, htu, iat, jti và ath.
8. Kiểm tra nonce nếu server yêu cầu.
9. Chống replay bằng cách phát hiện jti đã được sử dụng trong khoảng thời gian hợp lệ.
10. Chỉ sau đó mới thực hiện scope/role, tenant và object-level authorization.

~~~mermaid
flowchart TD
    A["Request: Authorization DPoP + DPoP proof"] --> B["Xác minh access token"]
    B --> C{"Token hợp lệ và có cnf.jkt?"}
    C -- "Không" --> X["Từ chối"]
    C -- "Có" --> D["Xác minh chữ ký DPoP proof"]
    D --> E["Tính JWK thumbprint"]
    E --> F{"Thumbprint khớp cnf.jkt?"}
    F -- "Không" --> X
    F -- "Có" --> G["Kiểm tra htm, htu, iat, ath, nonce"]
    G --> H["Chống replay jti"]
    H --> I{"Proof hợp lệ?"}
    I -- "Không" --> X
    I -- "Có" --> J["Scope, role, tenant, object policy"]
    J --> K["Xử lý API"]
~~~

**Không được bỏ qua một bước chỉ vì bước khác đã thành công.** Token signature hợp lệ không chứng minh người gửi có private key của client. Proof signature hợp lệ cũng không chứng minh access token được issuer chấp nhận.

## 5. Các claim của DPoP proof

| Claim/header | Nơi xuất hiện | Mục đích |
| --- | --- | --- |
| typ=dpop+jwt | Protected header | Nhận diện loại proof JWT |
| alg | Protected header | Thuật toán chữ ký được phép |
| jwk | Protected header | Public key xác minh proof |
| jti | Payload | ID duy nhất để chống replay |
| htm | Payload | HTTP method của request |
| htu | Payload | URI đích đã chuẩn hóa theo DPoP |
| iat | Payload | Thời điểm tạo proof |
| ath | Payload tại Resource Server | Ràng buộc proof với access token đang dùng |
| nonce | Payload khi server yêu cầu | Ràng buộc proof với challenge gần đây từ server |

### htm phải khớp HTTP method

Nếu request là GET, proof phải khai báo htm tương ứng. Một proof được tạo cho GET không thể được tái sử dụng để gửi POST.

### htu phải khớp URI đích

htu ràng buộc proof với URI đích theo quy tắc chuẩn hóa của DPoP. Query string và fragment không thuộc giá trị htu. Cần tính đúng scheme, host, port và path theo quy tắc của RFC.

Khi Resource Server đứng sau reverse proxy, ứng dụng có thể chỉ nhìn thấy kết nối nội bộ, ví dụ http://service:8080, trong khi client gọi https://orders.example.com. Nếu hai phía tạo htu theo hai URI khác nhau, proof hợp lệ sẽ bị từ chối hoặc một cấu hình sai có thể mở đường cho việc xác minh URI không đúng.

Không tin các header X-Forwarded-Host, Forwarded hoặc X-Forwarded-Proto do client tự gửi. Chỉ sử dụng forwarded metadata từ proxy được tin cậy, sau khi proxy loại bỏ header giả mạo và ghi giá trị đã xác minh. Cấu hình external base URL rõ ràng thường dễ kiểm soát hơn việc suy luận tùy tiện từ request.

### iat và jti

iat giới hạn tuổi proof. Server cần clock skew hợp lý để chấp nhận sai lệch thời gian nhỏ nhưng không để proof cũ được sử dụng quá lâu.

jti phải đủ duy nhất để server phát hiện proof đã được dùng. Nếu không có replay detection, attacker có thể ghi lại một proof còn trong time window và gửi lại.

### ath ràng buộc proof với access token

Ở Resource Server, ath được tính theo công thức:

~~~text
BASE64URL-NOPAD(SHA-256(ASCII(access_token)))
~~~

Ví dụ Java helper:

~~~java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.Base64;

final class DpopTokenHash {

    private DpopTokenHash() {
    }

    static String ath(String accessToken) {
        try {
            byte[] digest = MessageDigest.getInstance("SHA-256")
                .digest(accessToken.getBytes(StandardCharsets.US_ASCII));

            return Base64.getUrlEncoder()
                .withoutPadding()
                .encodeToString(digest);
        } catch (NoSuchAlgorithmException exception) {
            throw new IllegalStateException(
                "SHA-256 is unavailable", exception);
        }
    }
}
~~~

So sánh ath với giá trị tính từ đúng access token trong Authorization header. Không hash chuỗi "Bearer " hoặc "DPoP " kèm theo token; input là giá trị token theo quy tắc protocol. Không ghi access token ra log khi debug.

## 6. JWK thumbprint và cnf.jkt

Resource Server cần chứng minh public key dùng để ký DPoP proof chính là key đã được Authorization Server ràng buộc vào access token.

Quy trình:

- Đọc public JWK từ proof header.
- Xác minh proof signature bằng key đó.
- Tạo JWK thumbprint theo RFC 7638.
- So sánh thumbprint với cnf.jkt của access token đã được xác minh.

Với RSA, EC và các loại key khác nhau, canonical member set dùng để tạo thumbprint khác nhau theo quy tắc JWK. Không tự serialize toàn bộ JSON JWK rồi hash chuỗi JSON nguyên văn; thứ tự thuộc tính, whitespace và trường metadata có thể làm kết quả khác. Dùng implementation tuân theo RFC 7638.

Không dùng public key do proof tự khai báo để xác minh access token signature trừ khi token profile/issuer có quy định riêng. Trong DPoP, public JWK xác minh proof; access token được xác minh theo issuer key hoặc introspection. Hai vai trò key khác nhau.

## 7. Nonce và chống replay

DPoP proof là JWT được ký, nhưng chữ ký hợp lệ không tự ngăn replay. Attacker có thể sao chép một proof đã được tạo và gửi lại trong thời gian proof còn được chấp nhận nếu server không phát hiện jti đã dùng.

### Replay cache

Resource Server có thể lưu cặp định danh như issuer/key thumbprint và jti trong một kho dùng chung, với TTL phù hợp proof acceptance window. Khi proof hợp lệ được sử dụng lần đầu, ghi nhận jti theo thao tác atomic; lần sau cùng jti phải bị từ chối.

Trong môi trường nhiều instance, replay cache chỉ tồn tại trong memory của từng pod là chưa đủ. Attacker có thể gửi request đầu đến pod A và replay đến pod B. Dùng một kho chia sẻ hoặc cơ chế phân vùng request có bảo đảm tương đương.

Cache cần giới hạn dung lượng và TTL để tránh bị lạm dụng tạo lượng jti vô hạn. Không giữ replay entries lâu hơn mức cần thiết, nhưng cũng không xóa trước khi proof hết cửa sổ chấp nhận.

### Server nonce

Server có thể yêu cầu client gửi nonce mới trong proof. Khi server trả DPoP-Nonce, client tạo một proof mới chứa nonce đó và gửi lại request. Nonce phải được kiểm tra theo policy của server; không dùng lại một proof cũ chỉ bằng cách thêm nonce vào header.

Nonce giúp server tăng khả năng chống replay và kiểm soát freshness. Nó không thay thế signature validation, htm/htu, ath hoặc jti replay detection nếu profile yêu cầu các kiểm tra đó.

### Clock skew

Các máy client, ingress, Resource Server và Authorization Server có thể lệch thời gian. Cần đồng bộ NTP và cấu hình cửa sổ chấp nhận hợp lý. Không tăng cửa sổ iat quá rộng để che lỗi clock; điều đó kéo dài cơ hội replay.

## 8. Phân biệt DPoP, mTLS certificate-bound và Bearer

| Thuộc tính | Bearer | DPoP | mTLS certificate-bound |
| --- | --- | --- | --- |
| Proof of possession | Không | Chữ ký proof JWT | TLS handshake bằng client certificate |
| Khóa client | Không bắt buộc | Private key tương ứng public JWK | Private key tương ứng X.509 certificate |
| Confirmation claim | Không bắt buộc | cnf.jkt | cnf.x5t#S256 |
| Header khi gọi API | Authorization: Bearer | Authorization: DPoP và DPoP proof | Authorization token và mTLS client cert |
| Proof gắn HTTP method/URI | Không | Có, qua htm/htu | Không theo cách DPoP |
| TLS client certificate bắt buộc | Không | Không | Có |
| Replay defense | Chủ yếu phụ thuộc token/transport | jti, time window, nonce và ath | Dựa trên mTLS proof và profile vận hành |
| Phù hợp | Tích hợp OAuth thông thường | Client có thể giữ key và tạo proof per request | Hệ thống có PKI/mTLS và quản lý certificate |

DPoP thường thuận tiện hơn khi client không thể hoặc không muốn dùng client certificate trong TLS handshake. mTLS phù hợp với hệ thống backend, gateway và môi trường đã có PKI. Việc chọn cơ chế phải theo khả năng client, issuer, Resource Server, proxy và vận hành.

## 9. Khi nào Spring Security hỗ trợ DPoP?

Khả năng DPoP phụ thuộc vào **version Spring Security**, module liên quan, Authorization Server và cấu hình runtime. Không nên suy ra support chỉ từ việc dự án có dependency oauth2-resource-server hoặc dùng một bản Spring Boot mới.

Trước khi viết cấu hình, xác minh cả hai phía:

| Thành phần | Câu hỏi cần xác nhận |
| --- | --- |
| OAuth Client | Có tạo DPoP proof và giữ private key an toàn không? |
| Authorization Server | Có nhận proof ở token endpoint và phát token_type DPoP không? |
| Token format | JWT/opaque token có mang cnf.jkt theo profile không? |
| Resource Server | Có hỗ trợ DPoP authorization scheme và DPoP proof header không? |
| Proof validator | Có kiểm tra typ, alg, JWK, signature, htm, htu, iat, jti, ath và nonce không? |
| Replay defense | Có replay cache phù hợp khi chạy nhiều instance không? |
| Reverse proxy | Có xác định đúng external URI cho htu không? |
| Tests | Có test tích hợp xác nhận token và proof được kiểm tra cùng nhau không? |

### Kiểm tra version đang được quản lý

Xem version thực tế được resolve từ Spring Boot BOM hoặc dependency management, không chỉ nhìn version khai báo trong build file. Spring Security Test, Resource Server, JOSE và các module OAuth liên quan nên tương thích cùng release train.

Kiểm tra tài liệu reference, release notes và API của đúng version để xác nhận:
- Có DPoP support ở Resource Server hay không.
- Có DPoP support ở Authorization Server/client hay không.
- Cấu hình bật support ở đâu.
- Có yêu cầu thêm dependency hoặc validator không.
- DPoP proof có được kiểm tra tự động trong security chain hay phải tích hợp component riêng.
- Các loại token và thuật toán nào được hỗ trợ.

Không copy một DSL/property từ một release khác rồi giả định nó tồn tại. Không tạo cấu hình giả như một property tự đặt tên dpop-enabled nếu framework không công bố property đó.

### Authorization Server và Resource Server là hai phần độc lập

Một Authorization Server có thể phát DPoP-bound token nhưng Resource Server chưa hỗ trợ xác minh proof. Ngược lại, Resource Server có thể hiểu proof nhưng issuer vẫn phát Bearer token không có cnf.jkt.

Chỉ bật chế độ DPoP khi cả client, issuer và Resource Server thống nhất profile. Nếu thiếu một mắt xích, hãy dùng cơ chế sender-constraining khác mà cả hệ thống hỗ trợ, hoặc giữ policy Bearer hiện tại với đánh giá rủi ro phù hợp; không giả vờ đã có binding.

## 10. Cấu hình Spring Security theo khả năng thực tế

Không có một đoạn YAML hoặc DSL duy nhất đúng cho mọi phiên bản Spring Security và mọi Authorization Server. Cấu hình cụ thể phụ thuộc release và implementation. Quy trình nên là:

1. Xác nhận dependency versions đang resolve.
2. Đọc tài liệu chính thức đúng version về DPoP Resource Server và Authorization Server.
3. Xác nhận token endpoint có thể phát DPoP-bound token.
4. Xác nhận Resource Server nhận scheme DPoP và header proof.
5. Cấu hình trust/issuer/audience/algorithm như các token khác.
6. Cấu hình proof validation và replay defense.
7. Cấu hình external URI/proxy nếu có.
8. Viết integration tests trước khi bật policy trong production.

### Nếu framework có support built-in

Dùng chính API được release đó công bố. Kiểm tra rõ:
- Cơ chế bật DPoP.
- Có tự xác minh cnf.jkt không.
- Có tự kiểm tra ath, htm, htu và nonce không.
- Replay cache có được cung cấp không hay cần application component.
- DPoP scheme có được xử lý khác Bearer scheme không.
- Error response và DPoP-Nonce header được phát ra thế nào.

Không chỉ bật một option rồi bỏ qua các kiểm tra mà documentation yêu cầu ứng dụng tự cấu hình.

### Nếu framework chưa có support built-in

Có ba hướng triển khai:

- Nâng cấp lên version đã hỗ trợ đầy đủ và tương thích với ứng dụng.
- Đưa DPoP enforcement vào API gateway hoặc một security component chuyên trách đã được kiểm chứng.
- Tích hợp thư viện DPoP/JWT được duy trì, xây dựng adapter rõ ràng và kiểm thử theo RFC.

Tự viết một filter kiểm tra riêng lẻ htm hoặc chữ ký proof không đủ để triển khai DPoP. Cần cả binding với token, ath, nonce, jti replay detection, URI normalization, algorithm allowlist và failure handling.

Không tự động fallback từ DPoP-bound token sang Bearer nếu proof thiếu hoặc sai. Điều đó làm mất mục đích sender-constraining.

## 11. Phác thảo thứ tự kiểm tra trong Resource Server

Dù dùng implementation built-in hay adapter, thứ tự logic cần bảo đảm các dữ liệu được tin cậy trước khi dùng:

**Bước A — Xác thực access token**

- Parse đúng authorization scheme.
- Xác minh chữ ký hoặc introspection response.
- Xác minh issuer, audience, expiry và token profile.
- Xác nhận token được phát theo DPoP profile.
- Đọc cnf.jkt từ token đã xác minh.

**Bước B — Xác thực DPoP proof**

- Chỉ chấp nhận typ dpop+jwt.
- Chỉ chấp nhận thuật toán bất đối xứng trong allowlist.
- Từ chối header chứa private key material hoặc JWK không phù hợp.
- Xác minh proof signature.
- Tính JWK thumbprint và so với cnf.jkt.
- Kiểm tra htm, htu, iat và ath.
- Kiểm tra nonce nếu policy yêu cầu.
- Ghi nhận jti theo cơ chế replay detection.

**Bước C — Authorization**

- Map scope/permissions thành GrantedAuthority.
- Kiểm tra role và quyền chức năng.
- Kiểm tra tenant, owner, membership và trạng thái đối tượng.
- Thực thi controller/service.

Không dùng claim trong proof chưa xác minh để cấp quyền. Không sử dụng JWK do proof gửi để xác minh access token issuer signature.

## 12. Token JWT và opaque token trong DPoP

DPoP binding không phụ thuộc việc access token là JWT hay opaque. Điều quan trọng là Resource Server có thể lấy được confirmation claim đáng tin.

### JWT access token

Resource Server xác minh chữ ký JWT, issuer, audience, time và profile. Sau đó đọc cnf.jkt từ claims đã xác minh.

### Opaque access token

Resource Server gọi introspection endpoint. Response cần cung cấp trạng thái active và confirmation data theo contract, ví dụ:

~~~json
{
  "active": true,
  "sub": "service-orders",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "cnf": {
    "jkt": "base64url-jwk-thumbprint"
  }
}
~~~

Nếu introspection chỉ trả active=true nhưng không có cnf.jkt cần thiết, Resource Server chưa có đủ dữ liệu để xác minh DPoP binding. Không suy luận key binding từ client_id hoặc từ việc token được phát hành qua TLS.

## 13. Reverse proxy và cách xác định htu

DPoP proof ràng buộc với URI đích. Reverse proxy có thể thay đổi scheme, host, port hoặc path khi forward request:

~~~text
Client
  |
  | https://api.example.com/v1/orders/123
  v
Ingress
  |
  | http://orders-service:8080/internal/orders/123
  v
Resource Server
~~~

Client có thể tạo htu theo external URI, trong khi backend nhìn thấy URI nội bộ. Nếu backend tự dùng request URI nội bộ để so sánh, proof sẽ mismatch.

Cần thống nhất cách xác định URI:
- Dùng cấu hình external origin/path mapping rõ ràng nếu kiến trúc cho phép.
- Hoặc chỉ sử dụng forwarded metadata từ proxy nằm trong trusted proxy list.
- Proxy phải xóa forwarded headers do client gửi vào và ghi lại giá trị chính xác.
- Kiểm tra behavior khi có nhiều proxy hop, path rewrite, port mapping và TLS termination.
- Không chấp nhận host tùy ý từ request để tạo htu; có thể gây host confusion hoặc bypass validation.

Integration test phải chạy qua cùng topology/proxy rule như môi trường triển khai. Test bind trực tiếp controller có thể không phát hiện lỗi URI normalization.

## 14. Replay cache và khả năng mở rộng nhiều instance

Giả sử proof hợp lệ có jti = P-100. Nếu request đầu tiên được xử lý ở pod A, pod A cần ghi nhận P-100 đã sử dụng. Request replay đến pod B phải nhìn thấy cùng trạng thái.

| Cách lưu jti | Hành vi | Đánh giá |
| --- | --- | --- |
| In-memory từng instance | Pod A và B có trạng thái riêng | Không đủ cho cluster nhiều instance |
| Shared cache/store có atomic insert | Mọi instance dùng chung replay state | Phù hợp nếu TTL và consistency đúng |
| Sticky session | Một client thường vào cùng instance | Không tự bảo đảm replay defense khi routing thay đổi |
| Không lưu jti | Proof còn hạn có thể bị phát lại | Không đáp ứng replay detection |

Replay cache cần:
- Atomic insert-if-absent hoặc thao tác tương đương.
- TTL theo proof acceptance window và clock skew.
- Key namespace phù hợp issuer/key thumbprint để tránh collision.
- Giới hạn dung lượng, rate limit và metrics.
- Xử lý outage theo fail-closed policy cho endpoint yêu cầu DPoP.

Nếu replay store không truy cập được, không nên âm thầm bỏ qua replay check rồi tiếp tục nhận proof. Định nghĩa rõ endpoint có từ chối request hay trả dependency error theo contract vận hành.

## 15. Quản lý khóa phía client

DPoP bảo vệ token bị đánh cắp riêng lẻ; private key của client trở thành tài sản cần bảo vệ.

Các yêu cầu thường gặp:
- Tạo khóa bằng cryptographic random generator phù hợp.
- Ưu tiên OS keystore, secure enclave, TPM hoặc HSM nếu client platform hỗ trợ.
- Không lưu private JWK trong log, source control, local storage không phù hợp hoặc telemetry.
- Phân tách khóa theo application/client/device theo threat model.
- Có quy trình xoay khóa và đăng ký public key mới.
- Không dùng một private key chung cho dev, staging và production.
- Khi mất/compromise khóa, có quy trình revoke/rotate token và đăng ký key mới.

### Key rotation

Access token đã ràng buộc với jkt cũ không tự chuyển sang key mới. Khi client đổi key, cần yêu cầu token mới được ràng buộc với public key mới và chuyển đổi theo rollout đã thiết kế.

~~~text
Key A -> public JWK thumbprint JKT-A
Token T1 -> cnf.jkt = JKT-A

Client tạo Key B -> thumbprint JKT-B
Client yêu cầu token mới với proof từ Key B
Token T2 -> cnf.jkt = JKT-B

T1 + proof từ B -> mismatch
T2 + proof từ B -> match
~~~

Không sửa cnf.jkt trong token cũ. Chỉ Authorization Server phát hành token mới theo quy trình tin cậy.

## 16. Failure behavior và HTTP response

DPoP tạo thêm những trường hợp lỗi ngoài token invalid thông thường:

| Tình huống | Lý do | Hành vi mong đợi |
| --- | --- | --- |
| Không có DPoP proof cho token bound | Thiếu proof of possession | Từ chối |
| Proof signature sai | Proof không đáng tin | Từ chối |
| typ hoặc alg không được chấp nhận | Sai proof profile | Từ chối |
| cnf.jkt không khớp | Dùng sai key | Từ chối |
| htm/htu mismatch | Proof dành cho request khác | Từ chối |
| ath mismatch | Proof gắn với token khác | Từ chối |
| iat quá cũ/quá xa tương lai | Proof không nằm trong time window | Từ chối |
| jti đã dùng | Replay | Từ chối |
| Nonce thiếu/sai khi được yêu cầu | Không đáp ứng challenge | Trả challenge/error theo DPoP profile |
| Replay store outage | Không thể bảo đảm chống replay | Fail closed hoặc dependency error theo policy |
| Access token hết hạn/issuer sai | Token invalid | 401 |
| Token hợp lệ nhưng thiếu scope | Authorization denied | 403 |

Error code và header cụ thể phải theo RFC 9449, OAuth error response và implementation/version đang dùng. Khi server yêu cầu nonce, client cần đọc DPoP-Nonce response header, tạo proof mới chứa nonce và retry theo quy tắc. Không retry vô hạn; áp dụng giới hạn retry và timeout.

Không đưa raw token, DPoP proof hoặc private key vào log. Có thể log correlation ID, failure category, issuer/client identifier đã được làm sạch và metrics tổng hợp.

## 17. Kiểm thử DPoP theo từng tầng

Không nên chỉ có một integration test trả 200. Chia test theo capability:

| Tầng | Mục tiêu | Cách kiểm thử |
| --- | --- | --- |
| Proof construction | Header/payload đúng | Unit test client proof builder |
| Proof signature | Private key ký, public key xác minh | Unit test cryptographic |
| JWK thumbprint | jkt tính đúng theo RFC 7638 | Test vector và implementation độc lập |
| ath | Hash đúng access token | Test vector SHA-256/Base64URL |
| Token binding | cnf.jkt khớp proof JWK | Resource Server validator test |
| Request binding | htm/htu khớp request | WebFlux/Servlet integration test |
| Freshness | iat và clock skew | Boundary tests |
| Replay | jti không thể dùng hai lần | Shared replay store integration test |
| Nonce | Server challenge và client retry | End-to-end test |
| AS issuance | Token type và cnf đúng | Token endpoint integration test |
| RS acceptance | Token + proof cùng hợp lệ | HTTP integration test qua filter chain |
| Proxy behavior | External URI đúng | Test qua ingress/proxy topology |

### Positive case

- Client có key pair test.
- Authorization Server test phát token có cnf.jkt tương ứng.
- Client tạo DPoP proof mới cho GET URI đúng.
- ath hash đúng access token.
- jti chưa được dùng.
- Nonce hợp lệ nếu yêu cầu.
- Resource Server chấp nhận token/proof rồi kiểm tra scope.

### Negative cases

- Proof được ký bằng key khác.
- Token bound với JKT-A nhưng proof dùng JKT-B.
- Thiếu cnf.jkt.
- Thiếu DPoP header.
- Authorization scheme Bearer cho token yêu cầu DPoP.
- ath được tính từ token khác.
- HTTP method sai.
- URI sai host, port, scheme hoặc path.
- Proof hết hạn hoặc iat ở tương lai.
- jti replay.
- Nonce sai hoặc thiếu.
- Access token signature sai/expired/audience sai.
- Introspection trả active=false hoặc không có cnf.jkt.
- Replay store không sẵn sàng.

Mỗi test phải xác định failure ở tầng token, proof hay authorization để tránh một lỗi sớm che mất lỗi cần kiểm chứng.

## 18. Mock danh tính không kiểm tra DPoP proof

Một test dùng mock JWT hoặc mock user có thể hữu ích để kiểm tra scope/role, nhưng không chứng minh DPoP đang hoạt động.

| Cách test | Có kiểm tra DPoP proof không? |
| --- | --- |
| mockJwt()/mockUser() | Không |
| Mock access token Authentication trong SecurityContext | Không |
| Bearer/DPoP header với decoder mock | Chỉ kiểm tra filter wiring theo behavior mock; không xác minh chữ ký thật |
| Proof validator unit test với key test | Có thể kiểm tra proof logic |
| Resource Server integration với token/proof đã ký | Có |
| End-to-end qua Authorization Server và Resource Server test | Có, nếu cả hai phía dùng implementation thật |

Để kiểm tra DPoP, request phải mang cả access token và DPoP proof qua đúng authentication mechanism. Một helper dựng Authentication đã bỏ qua phần quan trọng nhất của sender-constraining.

## 19. DPoP và mTLS certificate-bound trong Spring Security

Nếu version/cấu hình chưa hỗ trợ DPoP nhưng hệ thống đã hỗ trợ certificate-bound access token, có thể dùng mTLS theo RFC 8705 làm sender-constraining mechanism.

Với mTLS certificate-bound token:
- Client dùng certificate trong TLS handshake.
- Token mang cnf.x5t#S256.
- Resource Server lấy leaf client certificate đã được xác thực.
- Tính SHA-256 thumbprint trên DER certificate.
- So với claim trong token.

Với DPoP:
- Client ký proof JWT bằng private key.
- Token mang cnf.jkt.
- Resource Server xác minh proof và JWK thumbprint.
- Kiểm tra request binding, ath, freshness, nonce và replay.

Hai cơ chế có thể yêu cầu integration khác nhau trong Spring Security và proxy. Không dùng property mTLS để giả lập DPoP hoặc ngược lại. Xác nhận framework và Authorization Server hỗ trợ đúng profile trước khi chọn.

## 20. Capability matrix trước khi bật trong từng môi trường

Dev, staging và production có thể khác nhau về issuer, proxy, key store, token type và support của framework. Lập ma trận trước khi triển khai:

| Hạng mục | Dev | Staging | Production |
| --- | --- | --- | --- |
| Spring Boot/Security version | Version đã resolve | Version release candidate/target | Version đã phê duyệt |
| DPoP support phía client | Đã test/chưa | Đã test/chưa | Đã test/chưa |
| DPoP support phía AS | Đã test/chưa | Đã test/chưa | Đã test/chưa |
| DPoP support phía Resource Server | Đã test/chưa | Đã test/chưa | Đã test/chưa |
| Token type và cnf.jkt | Đã xác nhận/chưa | Đã xác nhận/chưa | Đã xác nhận/chưa |
| Algorithm allowlist | Test key | Giống production | Security policy |
| JWK thumbprint | Test vector | Cross-check | Contract |
| ath/htm/htu | Đã test/chưa | Đã test/chưa | Đã test/chưa |
| Nonce/replay cache | Local/shared test | Cluster test | Shared store/SLO |
| Proxy external URI | Local route | Ingress staging | Trusted proxy configuration |
| Clock synchronization | NTP | NTP | NTP/monitoring |
| Key storage/rotation | Dev key riêng | Staging key riêng | Secure keystore/HSM nếu cần |
| Failure response | 401/nonce | 401/nonce/503 | Contract và alert |
| Revocation/incident process | Test | Runbook rehearsal | Operational runbook |

Không đánh dấu support là “đã bật” chỉ dựa trên dependency có mặt. Bằng chứng cần là token response có binding, Resource Server xác minh proof và các negative test bị từ chối.

## 21. Checklist kiểm chứng theo phiên bản

Trước khi viết code hoặc thay đổi cấu hình, xác nhận:

1. Version Spring Boot và Spring Security thực tế được resolve.
2. Tài liệu release tương ứng có mô tả DPoP ở đúng vai trò client, AS hoặc Resource Server.
3. OAuth client tạo được proof đúng RFC 9449.
4. Authorization Server xác minh proof và phát token có cnf.jkt.
5. Token response sử dụng token_type đúng profile.
6. Resource Server chấp nhận DPoP authorization scheme.
7. Resource Server xác minh proof signature, typ, alg và JWK.
8. Resource Server đối chiếu JKT với cnf.jkt.
9. Resource Server kiểm tra htm, htu, iat, ath và nonce.
10. Replay protection hoạt động giữa các instance.
11. Proxy không làm sai URI và không cho client giả mạo forwarded headers.
12. Các test âm chứng minh token/proof sai bị từ chối.
13. TLS vẫn được bật và certificate server được xác minh.
14. Metrics/log không làm lộ token, proof hoặc private key.

Nếu bất kỳ khả năng bắt buộc nào chưa có, ghi rõ giới hạn và chọn một cơ chế sender-constraining được hỗ trợ đầy đủ. Không triển khai nửa vời rồi quảng bá rằng access token đã được ràng buộc khóa.

## 22. Các lỗi thường gặp

**“Bật HTTPS là token không thể bị đánh cắp.”** HTTPS bảo vệ kết nối; token vẫn có thể lộ ở endpoint, log, memory hoặc client storage.

**“Có DPoP header là request đã an toàn.”** Phải xác minh proof, key binding, htm, htu, iat, ath, nonce và replay.

**“Proof signature hợp lệ là đủ.”** Proof còn phải dùng đúng key đã ràng buộc trong cnf.jkt và khớp request/access token.

**“cnf.jkt là hash của JWT proof.”** Không. Đây là JWK thumbprint theo RFC 7638.

**“cnf.jkt và cnf.x5t#S256 giống nhau.”** Không. Một giá trị ràng buộc JWK, giá trị kia ràng buộc X.509 certificate.

**“DPoP proof có thể tái sử dụng cho nhiều request.”** Không nên. jti, htm, htu, iat và ath ràng buộc proof với request/token; tạo proof mới theo request.

**“Không cần ath vì token đã có cnf.”** ath ràng buộc proof với access token đang gửi ở Resource Server; cnf.jkt ràng buộc token với key. Hai kiểm tra khác nhau.

**“Replay cache local là đủ cho cluster.”** Không nếu request replay có thể đến instance khác. Cần shared/atomic replay detection hoặc cơ chế tương đương.

**“Proxy có thể tự suy ra htu từ bất kỳ X-Forwarded-Host.”** Chỉ tin metadata từ proxy được xác thực và cấu hình trust rõ ràng.

**“Resource Server có JWT support nghĩa là có DPoP support.”** Không. JWT decoder và DPoP proof validation là khả năng khác nhau.

**“Authorization Server phát DPoP token là backend tự được bảo vệ.”** Không nếu Resource Server không kiểm tra proof và cnf.jkt.

**“Có thể fallback sang Bearer khi DPoP proof lỗi.”** Điều đó làm mất sender-constraining và có thể cho phép token bị đánh cắp được sử dụng.

## 23. Quy trình triển khai

1. **Xác định threat model:** token bị lộ ở đâu, client giữ khóa bằng cách nào, endpoint nào cần sender-constraining.
2. **Kiểm tra phiên bản:** xác nhận Spring Security và Authorization Server hỗ trợ DPoP hoặc mTLS-bound token đúng profile.
3. **Chốt cơ chế:** DPoP hay mTLS; không trộn claim hoặc proof giữa hai cơ chế.
4. **Cấu hình client:** tạo và bảo vệ key pair, tạo proof theo request, xử lý nonce và token_type.
5. **Cấu hình issuer:** xác minh proof ở token endpoint và phát access token có cnf binding.
6. **Cấu hình Resource Server:** kiểm tra token, proof, thumbprint, request binding và replay.
7. **Cấu hình proxy:** bảo đảm external URI/forwarded metadata có nguồn tin cậy.
8. **Cấu hình vận hành:** replay cache dùng chung, NTP, rate limit, timeout, key rotation và metrics.
9. **Viết test dương:** token và proof hợp lệ được chấp nhận.
10. **Viết test âm:** key mismatch, token mismatch, ath, htm, htu, nonce, iat, jti replay và audience/scope sai đều bị xử lý đúng.
11. **Chạy test theo topology:** kiểm tra qua ingress và nhiều Resource Server instance.
12. **Triển khai theo môi trường:** dùng key, issuer, client registration và replay store riêng cho dev/staging/production.

**Điểm cần nhớ:** DPoP ràng buộc access token với public key của client thông qua cnf.jkt và yêu cầu client chứng minh possession bằng proof JWT cho request. Resource Server phải xác minh cả access token lẫn proof, đối chiếu key thumbprint, kiểm tra htm/htu/iat/ath/nonce và chống replay jti. mTLS certificate-bound là cơ chế ràng buộc khóa khác, dùng cnf.x5t#S256 và client certificate. Chỉ bật cơ chế khi client, Authorization Server, Resource Server, proxy và phiên bản Spring Security đều hỗ trợ đúng profile; JWT Resource Server hoặc HTTPS đơn thuần chưa đủ.
