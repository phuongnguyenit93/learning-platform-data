# Kiểm thử DPoP, mTLS và các trường hợp token binding không khớp

Trong một OAuth 2.0/OpenID Connect Authorization Server xây dựng bằng Spring Authorization Server, access token thường được xem là bearer token: bất kỳ bên nào giữ được token đều có thể thử sử dụng nó. Nếu token bị lộ qua log, trình duyệt, proxy hoặc một dịch vụ trung gian, kẻ lấy được token có thể gọi API cho đến khi token hết hạn hoặc bị thu hồi.

DPoP (Demonstrating Proof of Possession, RFC 9449) và mutual TLS (mTLS, RFC 8705) bổ sung bằng chứng về khóa mà client đang sở hữu. Authorization Server ràng buộc token với khóa công khai hoặc chứng chỉ của client; Resource Server kiểm tra bằng chứng trong mỗi lần gọi API. Bài học này tập trung vào cách kiểm thử cả hai đầu của ràng buộc, đặc biệt là khi token được phát hành cho khóa A nhưng request lại chứng minh quyền sở hữu khóa B.

## Mục tiêu kiểm thử

Sau bài học, bạn có thể:

- Phân biệt bearer token với access token được ràng buộc bằng DPoP hoặc mTLS.
- Kiểm tra cấu trúc và chữ ký của DPoP proof, các claim theo request, nonce và cơ chế chống phát lại.
- Kiểm tra claim xác nhận khóa trong access token: `cnf.jkt` cho DPoP và `cnf.x5t#S256` cho mTLS.
- Kiểm tra Resource Server từ chối token khi bằng chứng khóa không khớp.
- Thiết kế kiểm thử ở cấp unit, tích hợp Authorization Server, Resource Server và TLS thực tế.
- Nhận diện lỗi cấu hình tại reverse proxy, nơi TLS kết thúc trước ứng dụng Spring.

## 1. Hiểu đúng điều đang được ràng buộc

Bearer token chỉ cần được trình bày. Sender-constrained token yêu cầu bên gọi API chứng minh mình đang sở hữu khóa đã được dùng khi cấp token. Việc kiểm tra chữ ký JWT của access token vẫn cần thiết, nhưng chưa đủ: Resource Server còn phải kiểm tra bằng chứng của request có khớp với thông tin ràng buộc trong token hay không.

| Cơ chế | Bằng chứng ở request | Thông tin ràng buộc trong token | Nơi kiểm tra |
|---|---|---|---|
| DPoP | JWT proof ký bằng private key của client, gửi trong header `DPoP` | `cnf.jkt`: thumbprint của public JWK | Authorization Server ở token endpoint và Resource Server ở API |
| mTLS | Client certificate được trình bày trong TLS handshake | `cnf.x5t#S256`: thumbprint của chứng chỉ client | TLS endpoint và Resource Server |
| Bearer thông thường | Không có proof sở hữu khóa | Không có ràng buộc sender | Resource Server kiểm tra token |

DPoP và mTLS giải quyết cùng một nhóm rủi ro nhưng dùng hai loại bằng chứng khác nhau. DPoP dùng chữ ký ở tầng HTTP; mTLS dùng chứng chỉ ở tầng TLS. Một hệ thống có thể hỗ trợ cả hai loại client, nhưng phải biết chính xác loại ràng buộc của từng token.

Cũng cần phân biệt hai khái niệm thường bị nhầm:

- **mTLS client authentication** xác thực client khi client kết nối tới Authorization Server. Các phương thức như `tls_client_auth` hoặc `self_signed_tls_client_auth` thuộc bài toán xác thực client.
- **Certificate-bound access token** ràng buộc access token với chứng chỉ. Resource Server phải kiểm tra chứng chỉ của kết nối đang sử dụng token.

Một kết nối dùng mTLS để xác thực client không tự động chứng minh rằng access token được phát hành đã ràng buộc với chứng chỉ đó. Kiểm thử cần xác minh cả hai quyết định nếu hệ thống yêu cầu cả hai.

PKCE cũng không thay thế DPoP hoặc mTLS. PKCE bảo vệ việc đổi authorization code; DPoP và mTLS bảo vệ việc sử dụng token sau khi token được cấp. Các cơ chế này có thể được dùng cùng nhau.

## 2. Kiểm thử luồng DPoP

### 2.1. DPoP proof gồm những gì?

Client tạo một cặp khóa bất đối xứng và giữ private key ở phía client. Với mỗi request cần proof, client tạo một JWT ngắn hạn, ký bằng private key và gửi trong header `DPoP`.

Header JWT của proof có các thành phần chính:

- `typ` phải là `dpop+jwt`.
- `alg` phải là thuật toán chữ ký bất đối xứng được hệ thống cho phép. Không chấp nhận `none`.
- `jwk` chứa public JWK để server xác minh chữ ký. Không được chứa private key material.

Payload của proof thường có:

- `jti`: định danh duy nhất của proof, dùng để phát hiện phát lại.
- `htm`: HTTP method của request, viết hoa theo method thực tế.
- `htu`: URI đích của request. Giá trị này không chứa query string hoặc fragment; scheme, host, port và path vẫn phải khớp với URI đích mà server xác định.
- `iat`: thời điểm tạo proof.
- `nonce`: nonce do server cấp khi chính sách yêu cầu.
- `ath`: hash của access token, bắt buộc khi proof được gửi tới Resource Server cùng access token.

Khi client gọi token endpoint, proof gắn với method và URI của token endpoint. Khi client gọi Resource Server, proof phải gắn với request API và có thêm `ath`. Giá trị `ath` được tính bằng SHA-256 trên chuỗi access token, sau đó mã hóa Base64 URL-safe không padding.

### 2.2. Kiểm tra token được phát hành

Khi Authorization Server chấp nhận DPoP proof ở token endpoint, access token được phát hành phải mang ràng buộc tới public key đã ký proof. Với JWT access token, thông tin này thường nằm trong claim:

~~~json
{
  "cnf": {
    "jkt": "thumbprint-cua-public-jwk"
  }
}
~~~

Thumbprint phải được tính theo quy tắc JWK thumbprint (RFC 7638). Hãy dùng thư viện JOSE đã được kiểm chứng để tính thumbprint; không tự ghép JSON hoặc dựa vào trường `kid`, vì `kid` chỉ là định danh do bên phát hành JWK đặt.

Response token endpoint cho DPoP-bound token sử dụng `token_type: DPoP`. Client cần giữ private key tương ứng để tạo proof khi sử dụng access token. Nếu hệ thống hỗ trợ refresh token được ràng buộc DPoP, thao tác refresh cũng phải chứng minh quyền sở hữu đúng khóa đã ràng buộc.

Với opaque access token, Resource Server thường nhận thông tin xác nhận qua cơ chế introspection hoặc một cơ chế chia sẻ metadata tương đương. Đừng giả định mọi access token đều là JWT hoặc Resource Server luôn có thể đọc claim trực tiếp.

### 2.3. Kiểm tra request tại Resource Server

Một request API DPoP-bound thường có dạng:

~~~http
GET /api/orders/42 HTTP/1.1
Host: api.example.test
Authorization: DPoP eyJ...access-token...
DPoP: eyJ...proof-jwt...
~~~

Resource Server cần thực hiện đầy đủ các bước sau:

1. Xác minh access token: chữ ký hoặc introspection, issuer, audience, thời hạn và các điều kiện token khác.
2. Đọc `cnf.jkt` từ token đã được xác minh.
3. Kiểm tra header và chữ ký DPoP proof; chỉ chấp nhận public JWK hợp lệ và thuật toán nằm trong allowlist.
4. Tính thumbprint từ public JWK trong proof và so sánh với `cnf.jkt`.
5. So sánh `htm` và `htu` với request hiện tại.
6. Kiểm tra `iat` trong khoảng thời gian chấp nhận, kiểm tra nonce nếu chính sách yêu cầu.
7. Kiểm tra `jti` chưa được sử dụng trong cửa sổ chống phát lại.
8. Tính lại `ath` từ access token đang được gửi và so sánh với claim trong proof.

Chỉ cần một bước không đạt, request phải bị từ chối. Đặc biệt, một proof có chữ ký hợp lệ vẫn không được chấp nhận nếu public key của proof khác thumbprint trong access token.

### 2.4. Các điểm dễ sai khi xác minh DPoP

**URI phía sau reverse proxy:** Ứng dụng có thể nhìn thấy kết nối nội bộ qua HTTP trong khi client gọi URL HTTPS bên ngoài. Nếu ứng dụng tự dựng `htu` từ request nội bộ, proof hợp lệ từ client sẽ bị từ chối hoặc việc xác minh có thể bị yếu đi. Chỉ tin `Forwarded` hoặc `X-Forwarded-*` từ proxy đã được cấu hình tin cậy; kiểm thử cả scheme, host, port và path bên ngoài.

**Chống phát lại phân tán:** Một node đã chấp nhận `jti` không được để node khác trong cluster chấp nhận lại cùng proof. Kho lưu replay phải có thao tác ghi nguyên tử, thời gian lưu phù hợp với cửa sổ `iat`, và phạm vi khóa đủ để phân biệt proof. Kiểm thử hai request đồng thời tới hai node.

**Độ lệch đồng hồ:** Dùng `Clock` có thể thay thế trong kiểm thử để xác minh proof quá cũ và proof có `iat` ở tương lai. Cửa sổ cho phép phải nhỏ và được cấu hình rõ ràng.

**Nonce:** Nếu server yêu cầu nonce, kiểm thử cả trường hợp thiếu nonce, nonce sai, nonce hết hạn và nonce hợp lệ. Khi yêu cầu nonce mới, response cần cung cấp nonce theo hợp đồng DPoP của hệ thống, thường qua header `DPoP-Nonce`.

**JWK không an toàn:** Không nhận JWK có private key material, thuật toán không được cho phép hoặc loại khóa không phù hợp. Không coi một `kid` tùy ý là bằng chứng sở hữu khóa.

## 3. Kiểm thử luồng mTLS

### 3.1. Chứng chỉ được dùng để ràng buộc token

Trong mTLS, client trình bày chứng chỉ X.509 trong TLS handshake. Authorization Server có thể dùng chứng chỉ đó để xác thực client, để ràng buộc access token, hoặc cho cả hai mục đích.

Với certificate-bound access token theo RFC 8705, claim xác nhận thường có dạng:

~~~json
{
  "cnf": {
    "x5t#S256": "thumbprint-cua-client-certificate"
  }
}
~~~

Thumbprint `x5t#S256` là SHA-256 của DER encoding của chứng chỉ client, được mã hóa Base64 URL-safe không padding. Khi Resource Server nhận token, nó lấy chứng chỉ client từ TLS connection đã được xác minh, tính thumbprint và so sánh với giá trị trong token.

Certificate-bound access token theo mTLS vẫn thường được gửi bằng scheme `Bearer` của OAuth 2.0. Ràng buộc được thực thi bằng chứng chỉ trong TLS connection. Vì vậy, chỉ nhìn thấy `Authorization: Bearer` không đủ để kết luận token là bearer token không ràng buộc; Resource Server vẫn phải kiểm tra `cnf.x5t#S256`.

Không dùng subject DN hoặc serial number làm phép so khớp thay thế. Hai chứng chỉ có thể có cùng subject nhưng khác khóa và khác DER encoding. Kiểm thử cần tạo hai chứng chỉ như vậy để chắc chắn ứng dụng so sánh đúng thumbprint.

### 3.2. Kiểm tra hai điểm kết nối

Ở token endpoint, xác minh rằng:

- TLS handshake yêu cầu client certificate theo chính sách.
- Certificate chain được xác minh bằng truststore phù hợp.
- Client identity được ánh xạ theo chính sách đăng ký client.
- Khi phát hành certificate-bound token, claim `cnf.x5t#S256` khớp chứng chỉ thực tế đã được chấp nhận.
- Việc xác thực client bằng mTLS và việc ràng buộc token được kiểm tra độc lập.

Ở Resource Server, xác minh rằng:

- Request trình bày đúng chứng chỉ đã được ràng buộc với token.
- Chứng chỉ được lấy từ TLS connection đã xác minh, không phải từ một header do client tùy ý gửi.
- Thumbprint được tính từ chứng chỉ leaf mà hệ thống quy định dùng để ràng buộc.
- Token bị từ chối nếu chứng chỉ vắng mặt hoặc thumbprint không khớp.

Nếu TLS kết thúc tại ingress hoặc reverse proxy, ứng dụng phía sau không trực tiếp nhìn thấy TLS client certificate ban đầu. Khi đó proxy phải xác minh chứng chỉ và truyền thông tin theo một kênh nội bộ được bảo vệ. Proxy phải xóa header chứng chỉ do client gửi từ bên ngoài trước khi tự thêm header đáng tin cậy. Kiểm thử đường đi qua proxy và đường truy cập trực tiếp vào ứng dụng để phát hiện việc giả mạo header hoặc bỏ qua lớp xác minh.

### 3.3. Xử lý vòng đời chứng chỉ

Một token được ràng buộc với chứng chỉ A không tự động trở nên hợp lệ với chứng chỉ B sau khi client xoay vòng chứng chỉ. Hãy kiểm thử chính sách chuyển đổi rõ ràng:

- Token cũ tiếp tục được dùng với chứng chỉ A trong thời hạn cho phép.
- Token cũ bị từ chối khi request dùng chứng chỉ B.
- Client lấy token mới được ràng buộc với chứng chỉ B.
- Chứng chỉ hết hạn, bị thu hồi hoặc không còn nằm trong trust chain bị từ chối theo chính sách TLS.
- Một chứng chỉ mới có cùng subject với chứng chỉ cũ vẫn được xem là chứng chỉ khác nếu thumbprint khác.

Một lỗi chứng chỉ ở TLS handshake có thể khiến kết nối bị đóng trước khi HTTP request tới ứng dụng. Với các trường hợp này, kiểm thử phải xác minh handshake thất bại hoặc kết nối bị từ chối; không nhất thiết phải mong đợi một HTTP status như 401.

## 4. Tích hợp kiểm thử với Spring Authorization Server

Spring Authorization Server cung cấp các điểm mở rộng cho xác thực client, token endpoint và phát hành token. Cách triển khai DPoP hoặc certificate-bound token phụ thuộc phiên bản Spring Authorization Server, Spring Security, servlet container và kiến trúc TLS termination đang dùng. Vì vậy, bài kiểm thử phải xác nhận hành vi của toàn bộ stack thay vì chỉ xác nhận một bean đã được cấu hình.

Với JWT access token, ứng dụng có thể dùng `OAuth2TokenCustomizer<JwtEncodingContext>` để đưa thông tin xác nhận vào token. Ví dụ dưới đây minh họa vị trí gắn claim; `SenderConstraintContextResolver` là thành phần do ứng dụng định nghĩa:

~~~java
@Bean
OAuth2TokenCustomizer<JwtEncodingContext> accessTokenCustomizer(
        SenderConstraintContextResolver bindingResolver) {

    return context -> {
        if (OAuth2TokenType.ACCESS_TOKEN.equals(context.getTokenType())) {
            Map<String, Object> confirmation =
                    bindingResolver.resolve(context);

            if (!confirmation.isEmpty()) {
                context.getClaims().claim("cnf", confirmation);
            }
        }
    };
}
~~~

Đoạn code này chỉ minh họa bước đưa claim vào JWT. Nó không tự xác minh DPoP proof, không chống phát lại, không xác minh TLS client certificate và không khiến Resource Server tự động kiểm tra token binding. Những trách nhiệm đó phải được triển khai ở đúng điểm xử lý request hoặc được cung cấp bởi phiên bản/thành phần có hỗ trợ tương ứng.

Nếu dùng opaque token, hãy xác minh rằng introspection response cung cấp thông tin xác nhận cần thiết và Resource Server thực sự dùng thông tin đó. Nếu dùng JWT, hãy kiểm tra claim trong token đã ký sau khi phát hành, thay vì chỉ kiểm tra object trong bộ nhớ trước khi mã hóa.

Nên chia kiểm thử theo trách nhiệm:

| Lớp kiểm thử | Thành phần cần xác minh | Bằng chứng đạt |
|---|---|---|
| Unit | DPoP proof verifier, JWK thumbprint, certificate thumbprint, replay store, nonce và clock | Đầu vào hợp lệ được chấp nhận; từng điều kiện sai bị từ chối |
| Authorization Server integration | Token endpoint và bước phát hành token | Token được phát hành đúng loại, có `cnf` đúng khóa/chứng chỉ |
| Resource Server integration | Bộ lọc hoặc thành phần xác minh sender constraint | Token chỉ được chấp nhận khi proof/chứng chỉ khớp |
| HTTPS end-to-end | TLS connector, truststore và client certificate | Handshake và request thực tế tuân theo chính sách mTLS |
| Proxy/deployment | Ingress, forwarded headers và đường truyền chứng chỉ | Không thể giả mạo URI hoặc chứng chỉ qua header không tin cậy |

## 5. Ma trận kiểm thử token binding

Nên dùng hai bộ khóa DPoP độc lập (A và B), hai chứng chỉ độc lập (A và B), đồng hồ có thể điều khiển và kho replay có thể reset giữa các test. Token được phát hành cho A là fixture quan trọng nhất: mọi test mismatch phải dùng token này rồi gửi bằng chứng của B.

### 5.1. DPoP

| Trường hợp | Dữ liệu kiểm thử | Kết quả mong đợi |
|---|---|---|
| Proof hợp lệ | Chữ ký đúng, `htm`, `htu`, `iat`, `jti` hợp lệ; key khớp `cnf.jkt` | Request được chấp nhận |
| Thiếu proof | Không có header `DPoP` trong luồng bắt buộc DPoP | Token endpoint hoặc Resource Server từ chối theo hợp đồng lỗi |
| Sai định dạng | JWT hỏng, thiếu claim bắt buộc hoặc `typ` không phải `dpop+jwt` | Proof bị từ chối |
| Sai chữ ký | Payload được ký bằng key khác với public JWK trong header | Proof bị từ chối |
| Thuật toán không hợp lệ | `alg=none`, thuật toán đối xứng hoặc thuật toán ngoài allowlist | Proof bị từ chối |
| Có private key material | JWK trong proof chứa trường private key | Proof bị từ chối |
| Token binding mismatch | Token có `cnf.jkt` của A nhưng proof dùng public key B | Token không được chấp nhận |
| Sai HTTP method | `htm` là GET nhưng request thực tế là POST | Proof bị từ chối |
| Sai URI đích | `htu` sai scheme, host, port hoặc path | Proof bị từ chối |
| Proof quá cũ hoặc ở tương lai | `iat` nằm ngoài cửa sổ cho phép | Proof bị từ chối |
| Phát lại | Gửi lại cùng proof với cùng `jti` trong cửa sổ chống phát lại | Lần gửi lại bị từ chối |
| Sai access-token hash | `ath` không phải hash của access token đang gửi | Request bị từ chối |
| Thiếu nonce | Server đang yêu cầu nonce nhưng proof không có nonce | Server yêu cầu nonce theo hợp đồng |
| Nonce sai hoặc hết hạn | Proof dùng nonce cũ hoặc nonce của phiên khác | Proof bị từ chối hoặc yêu cầu nonce mới |
| Sai token scheme | Dùng `Authorization: Bearer` cho token yêu cầu DPoP | Request bị từ chối |
| Refresh bằng khóa khác | Refresh token ràng buộc với A nhưng proof refresh dùng B | Yêu cầu refresh bị từ chối |

### 5.2. mTLS

| Trường hợp | Dữ liệu kiểm thử | Kết quả mong đợi |
|---|---|---|
| Chứng chỉ hợp lệ | Chứng chỉ A được tin cậy và khớp `cnf.x5t#S256` | Request được chấp nhận |
| Không có client certificate | Kết nối không trình bày chứng chỉ trong luồng bắt buộc mTLS | TLS handshake hoặc request bị từ chối |
| Sai chứng chỉ | Token ràng buộc với A nhưng kết nối dùng B | Token không được chấp nhận |
| Cùng subject, khác khóa | A và B có subject DN giống nhau nhưng DER khác nhau | B bị từ chối |
| Chứng chỉ hết hạn | Client dùng chứng chỉ đã hết hạn | TLS handshake bị từ chối theo chính sách |
| Chain không tin cậy | Chứng chỉ không được truststore chấp nhận | TLS handshake bị từ chối |
| Chứng chỉ bị thu hồi | Chứng chỉ nằm trong trạng thái thu hồi và hệ thống có kiểm tra trạng thái đó | Kết nối bị từ chối theo chính sách thu hồi |
| Giả mạo header | Client tự gửi header chứa thông tin chứng chỉ | Header bị proxy loại bỏ; không thể thay chứng chỉ TLS |
| Xoay vòng chứng chỉ | Token cũ của A được gửi cùng chứng chỉ mới B | Token cũ bị từ chối; token mới phải được cấp cho B |
| Chỉ xác thực client bằng mTLS | Client certificate được dùng để đăng nhập nhưng token không có claim ràng buộc dù policy yêu cầu | Test phát hiện lỗi phát hành token |
| Truy cập qua proxy | Proxy xác minh A và truyền dữ liệu chứng chỉ qua kênh tin cậy | Request hợp lệ được chấp nhận; header từ client không thể ghi đè |

### 5.3. Kiểm thử chéo hai cơ chế

Ngoài từng bộ test riêng, cần xác nhận Resource Server không nhầm loại bằng chứng:

- DPoP-bound token không được chấp nhận chỉ vì request có một client certificate hợp lệ.
- Certificate-bound token không được chấp nhận chỉ vì request có một DPoP proof hợp lệ.
- Token không có claim `cnf` phải tuân theo chính sách bearer đã cấu hình; không được vô tình bỏ qua yêu cầu sender constraint của client.
- Nếu hệ thống chủ ý hỗ trợ token ràng buộc đồng thời nhiều yếu tố, kiểm thử riêng quy tắc kết hợp. Nếu chưa định nghĩa quy tắc này, từ chối cấu hình `cnf` không rõ nghĩa thay vì tự suy diễn.

## 6. Tạo DPoP proof trong test

Có thể dùng Nimbus JOSE + JWT để tạo proof với khóa kiểm thử. Đoạn dưới đây là ví dụ tạo proof cho token endpoint; các giá trị method và URI phải khớp request mà test gửi:

~~~java
ECKey keyA = new ECKeyGenerator(Curve.P_256)
        .keyID("dpop-test-a")
        .generate();

JWSHeader header = new JWSHeader.Builder(JWSAlgorithm.ES256)
        .type(new JOSEObjectType("dpop+jwt"))
        .jwk(keyA.toPublicJWK())
        .build();

JWTClaimsSet claims = new JWTClaimsSet.Builder()
        .jwtID(UUID.randomUUID().toString())
        .issueTime(Date.from(clock.instant()))
        .claim("htm", "POST")
        .claim("htu", "https://as.example.test/oauth2/token")
        .build();

SignedJWT proof = new SignedJWT(header, claims);
proof.sign(new ECDSASigner(keyA));

String dpopHeader = proof.serialize();
~~~

Đối với request tới Resource Server, tạo proof mới cho request đó và bổ sung claim `ath`:

~~~java
String ath = Base64URL.encode(
        MessageDigest.getInstance("SHA-256")
                .digest(accessToken.getBytes(StandardCharsets.US_ASCII))
).toString();
~~~

Sau đó đưa `ath` vào payload trước khi ký proof. Không tái sử dụng proof của token endpoint cho API request: method, URI, access-token hash và `jti` đều gắn với một request cụ thể.

Để chứng minh mismatch, phát hành token bằng key A rồi tạo proof bằng key B. Không chỉ thay `kid`: hãy dùng một cặp khóa độc lập để thumbprint thực sự khác nhau. Test phải quan sát kết quả ở Resource Server, nơi token và proof được đối chiếu.

## 7. Ví dụ kiểm thử tích hợp ở Resource Server

Giả sử endpoint `/api/orders/42` yêu cầu DPoP. Test có thể gửi access token đã được phát hành cho key A nhưng proof được ký bởi key B:

~~~java
mockMvc.perform(get("/api/orders/42")
        .header(HttpHeaders.AUTHORIZATION, "DPoP " + accessTokenBoundToA)
        .header("DPoP", createProof(keyB, "GET",
                "https://api.example.test/api/orders/42",
                accessTokenBoundToA)))
    .andExpect(status().isUnauthorized());
~~~

Đây là mẫu kiểm thử cho endpoint và helper do ứng dụng định nghĩa. Cần bổ sung test tương ứng với key A để chứng minh cùng token được chấp nhận khi proof đúng. Với test mTLS ở MockMvc, có thể đặt request attribute chứa chứng chỉ để kiểm tra logic ứng dụng; tuy nhiên cách đó chỉ mô phỏng dữ liệu container cung cấp, không kiểm tra TLS handshake.

Một bài test mTLS đầu cuối cần chạy server HTTPS với cấu hình yêu cầu client certificate, truststore kiểm thử và hai client keystore A/B. Gọi cùng endpoint bằng chứng chỉ A và B để xác minh chứng chỉ được lấy từ TLS connection thật. Bài test qua ingress cần thêm trường hợp client gửi header chứng chỉ giả mạo để chứng minh proxy đã loại bỏ header đó.

## 8. Kiểm tra phản hồi lỗi và khả năng vận hành

Hãy kiểm tra hợp đồng lỗi ở ranh giới HTTP thay vì phụ thuộc vào tên exception nội bộ:

- DPoP proof không hợp lệ ở token endpoint thường được trả về bằng lỗi OAuth `invalid_dpop_proof`.
- Khi server yêu cầu nonce mới, response có thể dùng `use_dpop_nonce` và cung cấp `DPoP-Nonce`.
- Resource Server có thể trả 401 với challenge DPoP khi proof không hợp lệ; token không hợp lệ hoặc không khớp ràng buộc phải bị từ chối như một token không được phép sử dụng.
- mTLS handshake thất bại có thể đóng kết nối trước khi ứng dụng tạo HTTP response.
- Không trả access token, DPoP proof nguyên bản, private key hoặc nội dung bí mật của chứng chỉ vào response lỗi hay log.

Một bộ test ổn định nên xác minh status, error code hoặc challenge header theo hợp đồng công khai của ứng dụng. Không nên khóa test vào thông điệp exception hoặc stack trace, vì các chi tiết đó có thể thay đổi khi nâng cấp Spring Security hoặc thư viện JOSE.

Khi chạy trong cluster, kiểm tra replay store dùng chung giữa các node và thao tác ghi chống phát lại có tính nguyên tử. Khi chạy sau proxy, kiểm tra cách xác định URI bên ngoài và nguồn dữ liệu client certificate. Khi xoay vòng khóa hoặc chứng chỉ, kiểm tra thời gian tồn tại của token cũ, quy trình cấp token mới và khả năng thu hồi theo chính sách.

## 9. Checklist hoàn tất

Trước khi đưa cơ chế sender constraint vào môi trường tích hợp, hãy xác nhận:

- [ ] Token DPoP có `cnf.jkt` đúng public JWK đã ký proof.
- [ ] Token mTLS có `cnf.x5t#S256` đúng chứng chỉ client được chấp nhận.
- [ ] Resource Server xác minh chữ ký token trước khi tin claim `cnf`.
- [ ] Resource Server đối chiếu proof/chứng chỉ với claim `cnf` trong mọi request cần sender constraint.
- [ ] DPoP kiểm tra `typ`, thuật toán, chữ ký, `htm`, `htu`, `iat`, `jti`, `ath` và nonce theo chính sách.
- [ ] Replay detection hoạt động giữa nhiều node và trong các request đồng thời.
- [ ] mTLS kiểm tra certificate chain tại TLS endpoint và không tin header chứng chỉ do client tự đặt.
- [ ] Token cũ bị từ chối khi dùng khóa hoặc chứng chỉ khác.
- [ ] Kiểm thử qua reverse proxy xác minh đúng URI bên ngoài và chứng chỉ client.
- [ ] Phản hồi lỗi không làm lộ token, proof hoặc khóa bí mật.

Một bộ kiểm thử tốt phải chứng minh cả đường đi hợp lệ và đường đi sai ràng buộc. Chỉ kiểm tra token được phát hành có claim `cnf` là chưa đủ; bằng chứng sở hữu khóa phải được kiểm tra ở mỗi request sử dụng token.

