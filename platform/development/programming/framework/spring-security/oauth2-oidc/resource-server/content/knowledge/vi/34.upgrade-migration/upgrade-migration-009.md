# Khả năng DPoP, RFC 9068 và các tính năng phụ thuộc phiên bản

Spring Security Resource Server thường xác thực access token theo mô hình Bearer: client gửi token, server xác minh token và chấp nhận request nếu claims cùng quyền phù hợp. Mô hình này có một giới hạn: bất kỳ bên nào lấy được bearer token đều có thể thử sử dụng token đó cho tới khi token hết hạn hoặc bị thu hồi.

Hai tiêu chuẩn mở rộng đáng chú ý giải quyết các vấn đề khác nhau:

- **DPoP — RFC 9449:** ràng buộc access token với một cặp khóa của client. Mỗi request cần kèm một proof JWT chứng minh client đang giữ private key tương ứng.
- **JWT Profile for OAuth 2.0 Access Tokens — RFC 9068:** chuẩn hóa cấu trúc JWT access token, gồm loại token, claims bắt buộc và quy tắc xác thực để các Authorization Server và Resource Server liên tác tốt hơn.

Spring Security đã bổ sung các API cho hai khả năng này theo từng release. Việc nâng từ một phiên bản Security cũ lên phiên bản mới có thể làm xuất hiện validator, authentication provider hoặc converter mới; tuy nhiên không nên giả định mọi phiên bản đều có cùng API hoặc cùng mức tích hợp Servlet/Reactive.

Bài này giải thích giao thức, cách Spring Security hỗ trợ, các mốc phiên bản đáng chú ý, cách cấu hình RFC 9068, cách tạo DPoP proof, các rủi ro khi triển khai và bộ kiểm thử cần có trước khi bật tính năng trên production.

> **Phân biệt quan trọng:** RFC 9068 mô tả access token JWT và cách Resource Server xác thực token đó. DPoP mô tả cách ràng buộc token với khóa của client và chứng minh quyền sở hữu khóa trên từng request. Một access token có thể đồng thời tuân theo RFC 9068 và được ràng buộc bằng DPoP.

## 1. Bản đồ các tiêu chuẩn và thành phần

| Thành phần | Chuẩn hoặc API | Trách nhiệm |
|---|---|---|
| JWT access token profile | RFC 9068 | Chuẩn hóa header, claims và validation của JWT access token |
| DPoP | RFC 9449 | Sender-constrain access token với public key của client |
| JWT/JWS/JWK | RFC 7519, RFC 7515, RFC 7517 | Token claims, chữ ký và biểu diễn khóa |
| Spring JWT decoder | JwtDecoder / NimbusJwtDecoder | Xác minh chữ ký và decode access token |
| RFC 9068 validator | JwtValidators.createAtJwtValidator() | Kiểm tra token theo profile RFC 9068 |
| DPoP authentication provider | DPoPAuthenticationProvider | Xác thực access token được ràng buộc DPoP |
| DPoP proof decoder factory | DPoPProofJwtDecoderFactory | Tạo decoder và validator cho proof JWT |
| DPoP request converter | DPoPAuthenticationConverter | Trích xuất DPoP token/proof từ Servlet request |
| DPoP replay validator | DPoPProofReplayValidator | Chặn proof JWT bị dùng lại |
| OAuth2 Client / Authorization Server | Token endpoint và HTTP client integration | Tạo, gửi proof và phát hành token DPoP-bound |

Một hệ thống hoàn chỉnh cần phối hợp ít nhất ba bên:

```mermaid
flowchart LR
    C["OAuth2 Client"] -->|"DPoP proof + token request"| AS["Authorization Server"]
    AS -->|"Access token bound to public key"| C
    C -->|"Authorization: DPoP + DPoP proof"| RS["Resource Server"]
    RS -->|"Verify token, proof and key binding"| RS
    RS -->|"Authorize scope and business access"| API["Protected API"]
```

Authorization Server ràng buộc token với public key. Client giữ private key và tạo proof cho mỗi request. Resource Server xác minh cả access token lẫn proof trước khi tạo Authentication.

## 2. DPoP giải quyết vấn đề gì?

Với Bearer token thông thường, request có thể là:

```http
GET /api/orders HTTP/1.1
Host: api.example.test
Authorization: Bearer eyJhbGciOiJSUzI1NiIs...
```

Bên nào lấy được chuỗi token có thể gửi lại token đó. Chữ ký JWT chứng minh token được Authorization Server phát hành, nhưng không chứng minh người đang trình token chính là client ban đầu.

DPoP bổ sung bằng chứng sở hữu khóa:
- Client tạo một cặp public/private key.
- Client gửi DPoP proof khi xin access token.
- Authorization Server ghi nhận thumbprint của public key và ràng buộc access token với khóa đó.
- Khi gọi Resource Server, client gửi access token cùng một proof JWT mới.
- Resource Server xác minh proof được ký bằng private key tương ứng với public key đã ràng buộc vào access token.

Một access token bị đánh cắp riêng lẻ vì vậy không đủ để sử dụng nếu kẻ tấn công không có private key tương ứng.

### 2.1. DPoP là sender-constraining ở tầng ứng dụng

DPoP dùng JWT proof trong HTTP header. Nó không thay TLS và không mã hóa request body. TLS vẫn cần thiết để bảo vệ token, proof và dữ liệu trên đường truyền.

DPoP cũng không có nghĩa access token không thể bị đánh cắp. Nó làm cho token bị đánh cắp khó sử dụng độc lập hơn, vì attacker còn cần private key và phải tạo proof khớp với request hiện tại.

### 2.2. DPoP khác mTLS

| Đặc điểm | DPoP | OAuth mTLS |
|---|---|---|
| Cơ chế chứng minh | JWT proof được ký bằng private key của client | Client certificate trong TLS handshake |
| Gắn với request | Proof chứa method, URI và token hash | Ràng buộc token với certificate thumbprint |
| Phụ thuộc TLS termination | Không yêu cầu TLS certificate của client ở từng hop, nhưng vẫn yêu cầu TLS | Certificate cần được xử lý đúng tại TLS endpoint |
| Tính di động | Có thể dùng ở nhiều HTTP stack nếu tạo proof đúng | Phụ thuộc quản lý certificate và TLS |
| Replay | Dùng thời gian, jti, nonce và replay cache | TLS channel binding có đặc tính khác |
| Spring integration | DPoP Resource Server APIs theo version | OAuth mTLS support và client certificate configuration theo version |

Chọn cơ chế theo topology, khả năng quản lý khóa/certificate và yêu cầu bảo mật. Không coi DPoP là cách thay thế TLS.

## 3. Quy trình DPoP từ token endpoint tới Resource Server

### 3.1. Client xin access token

Client gửi DPoP proof trong header DPoP tới token endpoint:

```http
POST /oauth2/token HTTP/1.1
Host: issuer.example.test
Content-Type: application/x-www-form-urlencoded
DPoP: <SIGNED_DPOP_PROOF>

grant_type=authorization_code&
code=...&
redirect_uri=...&
client_id=orders-web
```

Proof cho token request thường chứa:
- Header typ là dpop+jwt.
- Header alg là thuật toán chữ ký bất đối xứng được chấp nhận.
- Header jwk chứa public JWK của client.
- Claim htm là POST.
- Claim htu là URI token endpoint.
- Claim iat là thời điểm tạo proof.
- Claim jti là identifier duy nhất của proof.

Proof ở token request chưa gắn với access token đã phát hành nên không có claim ath.

Nếu Authorization Server chấp nhận proof, nó gắn public key của client vào access token. Response dùng token_type DPoP:

```http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store

{
  "access_token": "<ACCESS_TOKEN>",
  "token_type": "DPoP",
  "expires_in": 300
}
```

Client cần lưu access token cùng private key tương ứng. Nếu token được ràng buộc với key A, proof được ký bằng key B sẽ không sử dụng được.

### 3.2. Client gọi protected resource

Khi gọi API, client tạo proof mới cho request cụ thể:

```http
GET /api/orders?state=open HTTP/1.1
Host: api.example.test
Authorization: DPoP <ACCESS_TOKEN>
DPoP: <NEW_SIGNED_DPOP_PROOF>
```

Proof phải gắn với:
- HTTP method hiện tại.
- HTTP target URI hiện tại, bỏ query và fragment khi tạo htu.
- Thời điểm tạo proof.
- jti mới.
- Hash của access token trong claim ath.
- Nonce nếu server đã yêu cầu nonce.

Mỗi request cần proof riêng. Không cache rồi tái sử dụng một proof JWT cho nhiều request.

### 3.3. Resource Server xác minh những gì?

Resource Server phải:
1. Xác thực access token theo issuer, audience, signature, expiry và policy.
2. Xác minh proof JWT có chữ ký hợp lệ bằng public JWK trong header.
3. Kiểm tra proof type là dpop+jwt và thuật toán được cho phép.
4. So sánh htm với HTTP method thực tế.
5. So sánh htu với URI request sau normalization đúng quy tắc.
6. Kiểm tra iat nằm trong cửa sổ thời gian cho phép.
7. Kiểm tra jti chưa được sử dụng trước đó theo replay policy.
8. Nếu server đã cấp nonce, xác minh nonce trong proof.
9. Tính lại hash của access token và so sánh với ath.
10. So sánh thumbprint của public key trong proof với key được ràng buộc trong access token.

Sau khi DPoP authentication thành công, Spring Security vẫn áp dụng authorization thông thường: scope, role, method security, tenant và object-level policy.

## 4. Cấu trúc DPoP proof JWT

### 4.1. JOSE header

Ví dụ header đã decode:

```json
{
  "typ": "dpop+jwt",
  "alg": "RS256",
  "jwk": {
    "kty": "RSA",
    "e": "AQAB",
    "n": "<PUBLIC_MODULUS>"
  }
}
```

Các điểm cần nhớ:
- typ phải là dpop+jwt.
- alg phải là chữ ký bất đối xứng được hỗ trợ và cho phép.
- alg=none không được chấp nhận.
- jwk chỉ chứa public key material.
- Không đưa private exponent hoặc private EC scalar vào proof header.
- Không tin một JWK chỉ vì nó xuất hiện trong proof; cần kiểm tra chữ ký và binding với access token.

Public JWK trong proof là khóa client dùng để chứng minh possession. Nó khác public signing key của Authorization Server dùng để xác minh chữ ký access token.

### 4.2. Claims cơ bản

```json
{
  "jti": "f5b52b5e-4db3-4cb5-9f6d-4a6a7f2b2f7e",
  "htm": "GET",
  "htu": "https://api.example.test/api/orders",
  "iat": 1794744000
}
```

| Claim | Ý nghĩa | Kiểm tra |
|---|---|---|
| jti | Identifier duy nhất của proof | Không trùng trong replay window |
| htm | HTTP method của request | Phải khớp method thực tế |
| htu | HTTP target URI, bỏ query và fragment | Phải khớp URI request sau normalization |
| iat | Thời điểm tạo proof | Nằm trong time window cho phép |
| ath | Hash access token | Bắt buộc khi proof đi cùng access token tới protected resource |
| nonce | Nonce do AS/RS cấp | Bắt buộc khi server đã yêu cầu nonce |

jti cần có entropy đủ lớn. UUID v4 hoặc ít nhất 96 bit dữ liệu ngẫu nhiên là lựa chọn phù hợp. Không dùng timestamp đơn lẻ làm jti vì nhiều request có thể xảy ra trong cùng một đơn vị thời gian.

### 4.3. Claim ath

Khi proof được gửi cùng access token tới Resource Server, ath là Base64URL encoding không padding của SHA-256 trên ASCII bytes của access token.

```java
String accessTokenHash(String accessToken)
        throws NoSuchAlgorithmException {

    byte[] tokenBytes =
        accessToken.getBytes(StandardCharsets.US_ASCII);

    byte[] digest =
        MessageDigest.getInstance("SHA-256").digest(tokenBytes);

    return Base64.getUrlEncoder()
        .withoutPadding()
        .encodeToString(digest);
}
```

Không hash JWT payload hoặc decoded claims. ath được tính trên toàn bộ chuỗi access token mà client gửi trong Authorization header.

### 4.4. Binding claim cnf.jkt

JWT access token có thể mang claim:

```json
{
  "cnf": {
    "jkt": "<JWK_SHA256_THUMBPRINT>"
  }
}
```

jkt là SHA-256 JWK thumbprint của public key DPoP. Resource Server so sánh thumbprint này với public key trong DPoP proof.

Nếu access token là opaque token, Resource Server có thể nhận binding metadata từ introspection response. Dù dùng JWT hay opaque token, server vẫn phải có cách đáng tin cậy để xác định public key mà token bị ràng buộc.

### 4.5. Proof token và access token là hai JWT khác nhau

| Thuộc tính | Access token JWT | DPoP proof JWT |
|---|---|---|
| Mục đích | Đại diện authorization grant | Chứng minh possession của client key cho một request |
| typ | Có thể at+jwt nếu tuân RFC 9068 | dpop+jwt |
| Issuer | Authorization Server | Client tạo proof |
| Chữ ký | AS signing key | Client DPoP private key |
| Claims | iss, aud, sub, exp, iat, jti, client_id, scope... | htm, htu, iat, jti, ath, nonce |
| Thời gian sống | Thường vài phút hoặc theo policy | Rất ngắn, gắn với request |
| Reuse | Có thể dùng nhiều request trong thời hạn nếu Bearer; DPoP-bound cần proof mới | Không tái sử dụng |

## 5. Nonce và chống replay

### 5.1. Vì sao cần replay protection?

htm và htu ngăn proof bị dùng ở endpoint/method khác. ath gắn proof với đúng access token. Tuy nhiên, nếu attacker lấy được cả proof JWT và access token, họ có thể thử replay proof tại cùng endpoint trong thời gian proof còn hợp lệ.

DPoP vì vậy cần:
- Cửa sổ iat ngắn.
- jti duy nhất.
- Replay cache để từ chối jti đã thấy.
- Nonce server khi deployment cần kiểm soát thời điểm tạo proof chặt hơn.

### 5.2. Replay cache

Server lưu jti đã sử dụng trong thời gian proof còn được chấp nhận. Nếu cùng jti xuất hiện lần nữa trong replay window, request bị từ chối.

Một cache in-memory chỉ chia sẻ giữa threads trong cùng process. Khi chạy nhiều instance:
- Hai instance có thể nhận cùng proof ở hai request gần nhau.
- Nếu cache không được chia sẻ, mỗi instance có thể không biết proof đã dùng ở instance kia.
- Replay protection vì vậy cần cache dùng chung hoặc cơ chế đồng bộ tương đương.
- Thao tác kiểm tra-và-ghi phải atomic để hai request đồng thời không cùng được chấp nhận.

Spring Security có DPoPProofReplayValidator từ 6.5.12. API có DPoPProofReplayValidator.InMemoryCache, nhưng tài liệu nêu rõ giới hạn single-node. Cluster production nên dùng distributed Cache như Redis hoặc Hazelcast theo topology thực tế.

### 5.3. DPoP-Nonce

Authorization Server hoặc Resource Server có thể trả header DPoP-Nonce. Client đưa nonce mới nhất vào claim nonce của proof tiếp theo.

Ví dụ server yêu cầu nonce:

```http
HTTP/1.1 400 Bad Request
DPoP-Nonce: <SERVER_NONCE>
Content-Type: application/json

{
  "error": "use_dpop_nonce",
  "error_description": "A fresh DPoP nonce is required"
}
```

Client tạo proof mới với nonce nhận được và retry request theo protocol. Nonce là opaque value; client không tự diễn giải hoặc tạo thay server.

Không retry vô hạn:
- Giới hạn số lần xử lý nonce challenge.
- Cập nhật nonce theo response mới nhất.
- Không dùng nonce của Authorization Server cho Resource Server khác.
- Không chia sẻ nonce giữa issuer/resource context nếu protocol không cho phép.
- Giữ jti mới cho mỗi proof retry.

## 6. URI và reverse proxy là điểm dễ sai

DPoP proof gắn với htu. Nếu client ký URI public nhưng Resource Server nhìn thấy URI nội bộ sau reverse proxy, hai giá trị có thể khác nhau.

Ví dụ:
- Client gọi https://api.example.test/api/orders.
- Load balancer chuyển tới http://orders-service:8080/api/orders.
- Servlet request có thể nhìn thấy scheme/host nội bộ nếu forwarded headers chưa được xử lý đúng.

Khi đó proof hợp lệ về chữ ký nhưng htu comparison thất bại.

Cần:
1. Xác định canonical external URI mà client sử dụng.
2. Cấu hình forwarded-header handling có kiểm soát.
3. Chỉ tin Forwarded/X-Forwarded-* từ proxy được xác thực.
4. Không cho caller trực tiếp gửi header giả để thay host/scheme.
5. Áp dụng URI normalization theo RFC 3986 trước khi so sánh.
6. Kiểm thử path prefix, port, scheme và trailing slash.
7. Không đưa query/fragment vào htu.

Nếu deployment có nhiều proxy hops, ghi rõ hop nào rewrite host, scheme và path. Không bật trust forwarded headers trên mọi nguồn request.

## 7. Spring Security hỗ trợ DPoP theo phiên bản

DPoP là tính năng có mốc API cụ thể. Khi đọc ví dụ, phải đối chiếu đúng Spring Security version đang được Spring Boot quản lý.

| API hoặc capability | Mốc Spring Security | Ý nghĩa |
|---|---:|---|
| DPoP Resource Server building blocks | 6.5 | Có DPoPAuthenticationProvider, DPoPAuthenticationToken và DPoPProofJwtDecoderFactory |
| DPoP proof decoder factory | 6.5 | Tạo JwtDecoder theo DPoPProofContext |
| RFC 9068 validator builder | 6.5 | JwtValidators.createAtJwtValidator() |
| DPoPProofReplayValidator | 6.5.12 | Validator chống replay với jti cache |
| DPoPAuthenticationConverter | 7.1 | Converter Servlet request thành DPoPAuthenticationToken |
| DPoP default proof validation | Có thay đổi theo patch | Xác minh htm/htu/iat/jti/jkt/ath theo API patch đang dùng |
| DPoP Resource Server reference | 6.5, 7.0, 7.1 | Tài liệu có các trang theo từng release line |
| RFC 9068 Servlet/Reactive examples | 6.5 trở lên trong docs hiện hành | NimbusJwtDecoder và NimbusReactiveJwtDecoder |

Mốc trên là mốc API được ghi trong tài liệu Spring Security hiện hành tại thời điểm soạn bài. Patch releases có thể bổ sung validator, thay đổi default hoặc thêm helper. Luôn kiểm tra API docs của đúng patch version trước khi copy code.

### 7.1. Các building blocks cho DPoP Resource Server

Các class quan trọng:

- DPoPAuthenticationProvider: AuthenticationProvider xác thực DPoP-bound access token.
- DPoPAuthenticationToken: Authentication request/representation cho DPoP-protected resource request.
- DPoPProofContext: Context truyền thông tin liên quan tới proof và access token.
- DPoPProofJwtDecoderFactory: Tạo decoder cho DPoP proof.
- DPoPAuthenticationConverter: Trích xuất DPoP credential từ HttpServletRequest; API này có từ Security 7.1.
- DPoPAuthenticationEntryPoint: Xử lý authentication challenge cho DPoP request.
- DPoPProofReplayValidator: Kiểm tra proof jti chưa được dùng lại.

DPoPAuthenticationProvider nhận AuthenticationManager dùng để xác thực access token, sau đó xử lý proof context. Default proof decoder factory cung cấp validation cho proof JWT; ứng dụng có thể thay validator factory khi cần policy bổ sung.

### 7.2. DPoPAuthenticationConverter chỉ có từ 7.1

Nếu code dùng DPoPAuthenticationConverter, cần Spring Security 7.1 trở lên. Converter nhận Servlet request và cố gắng trích xuất DPoP-bound token/proof thành DPoPAuthenticationToken.

Với 6.5 hoặc 7.0, không giả định class này tồn tại. Cần dùng integration mechanism của version đó hoặc tự viết converter theo contract. Không copy import từ tài liệu 7.1 vào dự án 6.5 rồi xử lý bằng cách thêm jar riêng lẻ.

### 7.3. Replay validator có mốc patch riêng

DPoPProofReplayValidator được ghi nhận từ 6.5.12. Nếu dự án đang dùng 6.5.0–6.5.11:
- Kiểm tra validator mặc định của DPoPProofJwtDecoderFactory ở patch đó.
- Xác nhận jti được kiểm tra theo replay policy.
- Nếu cần single-use replay cache, nâng lên patch có API hỗ trợ hoặc triển khai validator tương thích.
- Không giả định class có mặt chỉ vì ứng dụng đang dùng Security 6.5.

Các tài liệu API ban đầu của 6.5 mô tả default proof validator kiểm tra htm, htu, jti và iat. Tài liệu API mới hơn mô tả thêm jkt và ath trong default validator factory. Đây là ví dụ rõ ràng cho việc cần kiểm tra patch-level behavior.

### 7.4. Servlet và Reactive không nên được suy luận giống nhau

Tài liệu DPoP Resource Server hiện hành nằm trong phần Servlet và DPoPAuthenticationConverter nhận jakarta.servlet.http.HttpServletRequest. Trong khi đó, RFC 9068 có ví dụ riêng cho NimbusReactiveJwtDecoder.

Điều này có nghĩa:
- Có thể cấu hình RFC 9068 validator trong cả Servlet và Reactive JWT decoder.
- Không suy ra DPoP Reactive integration tồn tại chỉ vì JWT Reactive Resource Server tồn tại.
- Nếu ứng dụng WebFlux cần DPoP, xác minh đúng API trong version target; nếu không có integration được hỗ trợ, phải thiết kế và kiểm thử custom reactive authentication path.
- Không gọi blocking DPoP decoder/cache từ Netty event loop.

## 8. Tích hợp DPoP proof trong Spring

Spring Security cung cấp building blocks để tạo và xác minh DPoP proof. Client vẫn phải có key management và tạo proof đúng cho từng request.

Ví dụ tạo proof cho token endpoint bằng NimbusJwtEncoder:

```java
RSAKey dpopKey = ...; // private key stays on the client

JWKSource<SecurityContext> jwkSource =
    (selector, context) ->
        selector.select(new JWKSet(dpopKey));

NimbusJwtEncoder proofEncoder =
    new NimbusJwtEncoder(jwkSource);

JwsHeader header = JwsHeader
    .with(SignatureAlgorithm.RS256)
    .type("dpop+jwt")
    .jwk(dpopKey.toPublicJWK().toJSONObject())
    .build();

JwtClaimsSet claims = JwtClaimsSet.builder()
    .issuedAt(Instant.now())
    .claim("htm", "POST")
    .claim("htu", "https://issuer.example.test/oauth2/token")
    .id(UUID.randomUUID().toString())
    .build();

Jwt proof = proofEncoder.encode(
    JwtEncoderParameters.from(header, claims)
);
```

Đây là minh họa phía client. Không đưa private JWK vào request; chỉ public projection được đưa vào JOSE header. Proof token endpoint không có ath vì access token chưa được phát hành.

### 8.1. Tạo proof cho protected resource

Khi đã có access token, proof cần thêm ath:

```java
String ath = accessTokenHash(accessToken);

JwtClaimsSet claims = JwtClaimsSet.builder()
    .issuedAt(Instant.now())
    .claim("htm", "GET")
    .claim("htu", "https://api.example.test/api/orders")
    .claim("ath", ath)
    .id(UUID.randomUUID().toString())
    .build();

Jwt proof = proofEncoder.encode(
    JwtEncoderParameters.from(header, claims)
);
```

Nếu Resource Server đã cấp DPoP-Nonce, thêm claim nonce vào proof. Dùng đúng HTTP method và external URI mà server sẽ so sánh.

### 8.2. Đừng giả định OAuth2 Client tự tạo proof

Một ứng dụng có OAuth2AuthorizedClientManager và WebClient chưa chắc tự động tạo DPoP proof. Hãy kiểm tra đúng phiên bản và đúng token client implementation:
- Token request có DPoP header không?
- Client có lưu key binding cùng authorized client không?
- Mỗi resource request có tạo proof mới không?
- ath có được tính trên token chính xác không?
- Authorization scheme có là DPoP không?
- Nonce challenge có được xử lý đúng không?

Nếu phải tự tích hợp, đặt proof generation trong component có thể truy cập method, canonical URI, token và key. Không tạo proof trước khi biết request cuối cùng sẽ đi tới URI/method nào.

### 8.3. Authorization Server phải phát hành token có binding

Resource Server không thể tự biến một Bearer token bất kỳ thành DPoP-bound. Authorization Server phải:
- Nhận và xác minh DPoP proof ở token endpoint.
- Xác định public key của client.
- Phát access token với token_type DPoP.
- Gắn public key thumbprint qua cnf.jkt hoặc cơ chế introspection tương đương.
- Duy trì policy nhất quán khi refresh hoặc đổi token.

Nếu chỉ thêm DPoPAuthenticationProvider ở Resource Server nhưng AS vẫn phát Bearer token không có binding, hai phía không cùng một protocol contract.

## 9. RFC 9068 chuẩn hóa JWT access token như thế nào?

OAuth 2.0 không bắt buộc access token phải là JWT. Token có thể opaque và được introspect, hoặc là JWT được Resource Server xác minh cục bộ.

RFC 9068 định nghĩa profile JWT dành riêng cho OAuth 2.0 access token. Mục tiêu là làm rõ:
- Header type để phân biệt access token với JWT khác.
- Claims bắt buộc.
- Audience/resource semantics.
- Cách Resource Server xác thực token.
- Tránh nhầm OIDC ID token với access token.

### 9.1. Header typ

JWT access token theo RFC 9068 phải có typ là một trong:
- at+jwt
- application/at+jwt

Giá trị at+jwt được khuyến nghị vì bỏ prefix application/.

Ví dụ:

```json
{
  "typ": "at+jwt",
  "alg": "RS256",
  "kid": "as-signing-key-2026"
}
```

Không nhầm:
- at+jwt: access token JWT theo RFC 9068.
- dpop+jwt: proof JWT theo RFC 9449.
- JWT: type chung, không tự xác định token purpose.
- ID token: token OIDC mô tả authentication event cho client.

### 9.2. Claims bắt buộc

RFC 9068 yêu cầu các claims sau:

| Claim | Bắt buộc | Ý nghĩa |
|---|---|---|
| iss | Có | Authorization Server phát hành token |
| exp | Có | Thời điểm token hết hạn |
| aud | Có | Resource Server hoặc resource indicator được phép nhận token |
| sub | Có | Subject; có thể là user hoặc client tùy grant |
| client_id | Có | OAuth client mà token được phát hành cho |
| iat | Có | Thời điểm phát hành |
| jti | Có | Token identifier |

Claim scope được khuyến nghị khi authorization request có scope. Profile có thể chứa các identity/authorization claims bổ sung theo policy.

### 9.3. Thuật toán chữ ký

JWT access token theo RFC 9068 phải được ký và không được dùng alg=none. Profile yêu cầu conforming Authorization Server và Resource Server hỗ trợ RS256; hệ thống có thể hỗ trợ thêm thuật toán khác theo policy và registry.

Asymmetric signing được khuyến nghị vì Resource Server chỉ cần public key để xác minh, còn private key ở Authorization Server.

### 9.4. Audience là resource identifier

aud không phải client_id. Nó chỉ ra resource mà access token dành cho.

Ví dụ:

```json
{
  "iss": "https://issuer.example.test",
  "sub": "user-123",
  "aud": ["https://orders.example.test"],
  "client_id": "orders-web",
  "scope": "orders.read orders.write",
  "iat": 1794744000,
  "exp": 1794744300,
  "jti": "token-identifier-123"
}
```

Orders API phải xác minh audience của chính nó. Không chấp nhận token chỉ vì issuer hợp lệ hoặc client_id nằm trong allowlist.

### 9.5. Subject thay đổi theo grant type

Với authorization code hoặc grant có resource owner, sub thường định danh user. Với client credentials, sub có thể định danh client application.

Không viết policy giả định mọi sub đều là user ID. Nếu service token có sub là client identity, object ownership logic phải xử lý đúng principal type.

## 10. Vì sao RFC 9068 giúp tránh ID token confusion?

OIDC ID token và OAuth access token đều có thể là JWT, có chữ ký và chứa iss/sub/aud/exp. Nhưng chúng có mục đích khác nhau:

| Thuộc tính | OIDC ID token | RFC 9068 access token |
|---|---|---|
| Người nhận | OIDC client | Resource Server/API |
| Audience | Client ID | Resource identifier |
| typ | Theo OIDC/JWT profile | at+jwt hoặc application/at+jwt |
| Mục đích | Bằng chứng authentication cho client | Credential truy cập API |
| Claims | Có thể có nonce, auth_time, acr, amr | Có client_id, scope và claims authorization |
| Nơi tiêu thụ | OIDC client | OAuth Resource Server |

Một API không nên chấp nhận ID token chỉ vì chữ ký và issuer đúng. RFC 9068 yêu cầu kiểm tra typ, audience và profile claims, giúp giảm cross-JWT confusion.

## 11. Cấu hình RFC 9068 validator trong Spring Security

Spring Security cung cấp JwtValidators.createAtJwtValidator() từ version 6.5. Builder yêu cầu ít nhất audience và issuer; có thể thêm clientId và custom validators.

Ví dụ Servlet Resource Server:

```java
@Bean
JwtDecoder jwtDecoder(
        @Value("${security.issuer-uri}") String issuerUri) {

    NimbusJwtDecoder decoder =
        NimbusJwtDecoder.withIssuerLocation(issuerUri)
            .validateTypes(false)
            .build();

    decoder.setJwtValidator(
        JwtValidators.createAtJwtValidator()
            .issuer(issuerUri)
            .audience("https://orders.example.test")
            .clientId("orders-web")
            .build()
    );

    return decoder;
}
```

Trong cấu hình này:
- withIssuerLocation xác định issuer và cách lấy metadata/JWKS.
- validateTypes(false) tắt type validation mặc định của Nimbus để validator RFC 9068 chịu trách nhiệm kiểm tra type at+jwt.
- audience() ràng buộc token với Orders API.
- issuer() ràng buộc issuer chính xác.
- clientId() giới hạn client_id nếu API chỉ chấp nhận client cụ thể.

Không gọi validateTypes(false) rồi quên gắn RFC 9068 validator. Nếu tắt kiểm tra type mà không thay thế bằng validator đúng, ứng dụng có thể mất một phần bảo vệ chống token confusion.

### 11.1. Có nên luôn ràng buộc client_id?

Không nhất thiết. RFC 9068 yêu cầu claim client_id tồn tại, nhưng API có thể phục vụ nhiều OAuth clients. Nếu cần chấp nhận nhiều client:
- Không cấu hình một clientId duy nhất.
- Thêm validator kiểm tra allowlist theo policy.
- Giữ audience và issuer là các điều kiện bắt buộc.
- Đừng dùng client_id thay cho authorization scope hoặc user identity.

### 11.2. Thêm custom claim validators

Builder có validators consumer để thêm hoặc thay validator theo claim name. Ví dụ ứng dụng yêu cầu tenant_id:

```java
JwtValidators.AtJwtBuilder builder =
    JwtValidators.createAtJwtValidator()
        .issuer(issuerUri)
        .audience("https://orders.example.test");

builder.validators(validators ->
    validators.put("tenant_id", jwt -> {
        String tenantId = jwt.getClaimAsString("tenant_id");

        if (tenantId != null && !tenantId.isBlank()) {
            return OAuth2TokenValidatorResult.success();
        }

        OAuth2Error error = new OAuth2Error(
            "invalid_token",
            "Required tenant_id claim is missing",
            null
        );

        return OAuth2TokenValidatorResult.failure(error);
    })
);

decoder.setJwtValidator(builder.build());
```

Đây là ví dụ validator bắt buộc claim có giá trị. Nếu tenant_id chỉ là điều kiện của một số operation, có thể kiểm tra ở authorization/service layer thay vì từ chối mọi token không có claim này.

### 11.3. Kết hợp validator theo cách có chủ đích

Khi tự tạo JwtDecoder, hãy bảo đảm các kiểm tra sau vẫn tồn tại:
- Chữ ký theo thuật toán cho phép.
- Issuer.
- Audience.
- exp và nbf.
- RFC 9068 typ và required claims.
- Custom profile claims theo contract.
- Clock skew theo policy.

Không thay toàn bộ validator mặc định bằng một lambda chỉ kiểm tra audience. Việc thay validator có thể vô tình bỏ kiểm tra thời gian hoặc issuer.

## 12. RFC 9068 trong WebFlux

Spring Security có ví dụ tương đương với NimbusReactiveJwtDecoder:

```java
@Bean
ReactiveJwtDecoder jwtDecoder(
        @Value("${security.issuer-uri}") String issuerUri) {

    NimbusReactiveJwtDecoder decoder =
        NimbusReactiveJwtDecoder.withIssuerLocation(issuerUri)
            .validateTypes(false)
            .build();

    decoder.setJwtValidator(
        JwtValidators.createAtJwtValidator()
            .issuer(issuerUri)
            .audience("https://orders.example.test")
            .build()
    );

    return decoder;
}
```

RFC 9068 validator là phần dùng chung ở cấp Jwt. Decoder Servlet và Reactive khác nhau về execution model và network retrieval, nhưng profile claims cần được kiểm tra như nhau.

Không chuyển ReactiveJwtDecoder vào Servlet SecurityFilterChain hoặc JwtDecoder vào SecurityWebFilterChain. Dùng đúng abstraction theo application type.

## 13. DPoP và RFC 9068 kết hợp trong cùng một access token

Một JWT access token có thể vừa tuân RFC 9068 vừa là DPoP-bound:

```json
{
  "iss": "https://issuer.example.test",
  "sub": "user-123",
  "aud": ["https://orders.example.test"],
  "client_id": "orders-web",
  "iat": 1794744000,
  "exp": 1794744300,
  "jti": "access-token-id",
  "scope": "orders.read",
  "cnf": {
    "jkt": "thumbprint-of-client-public-key"
  }
}
```

Header access token:

```json
{
  "typ": "at+jwt",
  "alg": "RS256",
  "kid": "authorization-server-key"
}
```

DPoP proof riêng:

```json
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
```

Proof claims:

```json
{
  "jti": "unique-proof-id",
  "htm": "GET",
  "htu": "https://orders.example.test/api/orders",
  "iat": 1794744010,
  "ath": "<BASE64URL_SHA256_OF_ACCESS_TOKEN>"
}
```

Access token được ký bởi Authorization Server. DPoP proof được ký bởi client. Hai chữ ký chứng minh hai điều khác nhau:
- Token signature: Authorization Server phát hành token.
- DPoP proof signature: client hiện tại giữ private key tương ứng public key đã bind vào token.

Resource Server phải xác minh cả hai và binding giữa chúng.

## 14. Những tính năng phụ thuộc phiên bản cần đối chiếu

Khi nâng cấp, không chỉ xem major version. Một số capability được thêm ở minor hoặc patch release:

| Capability | Phiên bản được ghi nhận | Việc cần xác minh |
|---|---:|---|
| DPoPAuthenticationProvider | 6.5 | Có class và provider API |
| DPoPProofJwtDecoderFactory | 6.5 | Có proof decoder factory |
| JwtValidators.createAtJwtValidator | 6.5 | Có RFC 9068 profile validator |
| DPoPProofReplayValidator | 6.5.12 | Có single-use jti replay validator |
| DPoPAuthenticationConverter | 7.1 | Có Servlet request converter |
| DPoP default proof validation | Có thay đổi theo patch | Xác minh các claim htm/htu/iat/jti/jkt/ath được validate |
| DPoP Resource Server reference | 6.5, 7.0, 7.1 | Tài liệu có các trang theo từng release line |
| RFC 9068 Servlet/Reactive examples | 6.5 trở lên trong docs hiện hành | NimbusJwtDecoder và NimbusReactiveJwtDecoder |

Mốc trên là mốc API được ghi trong tài liệu Spring Security hiện hành tại thời điểm soạn bài. Patch releases có thể bổ sung validator, thay đổi default hoặc thêm helper. Luôn kiểm tra API docs của đúng patch version trước khi copy code.

### 14.1. Spring Boot quản lý Spring Security

Trong ứng dụng Boot:
- Chọn Boot release trước.
- Xem Spring Security version mà Boot BOM quản lý.
- Kiểm tra DPoP/RFC 9068 API có trong version đó.
- Nếu cần tính năng ở patch mới hơn, ưu tiên nâng Boot patch/minor phù hợp.
- Tránh override riêng spring-security-oauth2-resource-server hoặc spring-security-oauth2-jose sang version khác.

Không trộn spring-security-core, web, config, oauth2-resource-server, oauth2-jose và spring-security-test ở các version khác nhau.

### 14.2. Kiểm tra dependency thực tế

Gradle:

```powershell
.\gradlew dependencyInsight --dependency spring-security-oauth2-resource-server --configuration runtimeClasspath
.\gradlew dependencyInsight --dependency spring-security-oauth2-jose --configuration runtimeClasspath
.\gradlew dependencyInsight --dependency spring-security-core --configuration runtimeClasspath
```

Maven:

```powershell
mvn dependency:tree -Dincludes=org.springframework.security
```

Sau đó kiểm tra API bằng đúng dependency đã resolve, không chỉ dựa vào docs của latest.

### 14.3. Compile probe cho API version-dependent

Khi không chắc một method đã xuất hiện ở patch nào, tạo một compile test nhỏ trong branch nâng cấp:
- Import DPoPAuthenticationProvider.
- Import DPoPAuthenticationConverter nếu định dùng.
- Import DPoPProofReplayValidator.
- Gọi JwtValidators.createAtJwtValidator().
- Xây NimbusJwtDecoder với validateTypes(false).
- Xây NimbusReactiveJwtDecoder nếu app dùng WebFlux.

Compile probe xác nhận class/method có trong classpath thực tế. Sau đó mới viết integration tests.

## 15. Kiểm thử RFC 9068

Một bộ test nên có positive và negative token riêng:

| Case | Header/claims | Kết quả |
|---|---|---|
| Token profile hợp lệ | typ at+jwt, đủ required claims, signature đúng | Authentication thành công |
| typ là JWT chung | Không đúng RFC 9068 profile | Từ chối |
| typ là dpop+jwt | Đây là proof token, không phải access token | Từ chối như access token |
| Thiếu iss | Required claim thiếu | Từ chối |
| Thiếu exp | Required claim thiếu | Từ chối |
| Thiếu aud | Required claim thiếu | Từ chối |
| Thiếu sub | Required claim thiếu | Từ chối |
| Thiếu client_id | Required claim thiếu | Từ chối |
| Thiếu iat hoặc jti | Required claim thiếu | Từ chối |
| Issuer sai | Signature hợp lệ nhưng iss không khớp | Từ chối |
| Audience sai | Token dành cho API khác | Từ chối |
| Token hết hạn | exp ở quá khứ | Từ chối |
| Signature sai | Token không xác minh được | Từ chối |
| ID token gửi tới API | Sai token purpose/audience/type | Từ chối |

Với MockMvc/WebTestClient, dùng JWT compact ký thật và decoder thật cho profile integration tests. jwt() hoặc mockJwt() hữu ích cho authorization tests nhưng không chứng minh typ/header/required claims đã được decoder kiểm tra.

### 15.1. Kiểm tra authority mapping riêng

Nếu token có scope, kiểm tra authority được tạo đúng:
- orders.read thành SCOPE_orders.read.
- Token thiếu scope không có authority đó.
- Converter custom không làm mất profile validation.
- client_id không bị hiểu nhầm thành scope.
- sub service principal không bị coi là user nếu policy cần phân biệt.

### 15.2. Kiểm tra ID token không thể dùng làm access token

Tạo OIDC ID token fixture có:
- iss đúng.
- Signature đúng.
- aud là OIDC client ID.
- Claims OIDC hợp lệ.

Sau đó gửi ID token tới Resource Server. Token phải bị từ chối do type/audience/profile mismatch. Đây là test chống cross-JWT confusion có giá trị cao.

## 16. Kiểm thử DPoP end-to-end

Dùng test key pair riêng cho DPoP client và key pair khác cho Authorization Server. Không dùng chung một key để test cả hai chữ ký.

### 16.1. Positive case

- Authorization Server test phát access token token_type DPoP.
- Token chứa cnf.jkt đúng public key client.
- Client tạo proof có typ dpop+jwt.
- Proof có htm, htu, iat, jti và ath đúng.
- Client gửi Authorization: DPoP và DPoP header.
- Resource Server xác minh cả token và proof.
- Authorization rule theo scope cho request qua.

### 16.2. Negative cases

| Case | Thay đổi | Kết quả |
|---|---|---|
| Không có DPoP proof | Chỉ gửi access token | Từ chối |
| Sai proof signature | Ký proof bằng private key khác | Từ chối |
| Sai key binding | cnf.jkt không khớp proof public key | Từ chối |
| Sai ath | Hash không khớp access token | Từ chối |
| Sai htm | Proof GET nhưng request POST | Từ chối |
| Sai htu | Proof ký cho URI khác | Từ chối |
| Proof hết cửa sổ | iat quá cũ | Từ chối |
| Reuse jti | Gửi cùng proof lần hai | Từ chối theo replay policy |
| Nonce thiếu | Server đã yêu cầu nonce | Từ chối hoặc trả nonce challenge |
| Nonce sai | Claim nonce không khớp | Từ chối |
| Duplicate DPoP header | Nhiều header proof | Từ chối |
| typ sai | typ không phải dpop+jwt | Từ chối |
| alg=none | Proof không có chữ ký an toàn | Từ chối |
| JWK có private material | Header chứa private key parameters | Từ chối |
| Dùng Bearer scheme | Gửi DPoP-bound token dưới Bearer | Từ chối theo policy |

### 16.3. Test replay trên nhiều instance

Nếu chạy nhiều Resource Server nodes:
- Gửi proof lần đầu tới node A.
- Gửi lại cùng proof tới node B.
- Xác nhận node B cũng từ chối.
- Xác nhận replay cache được chia sẻ và thao tác ghi là atomic.
- Test cache eviction/expiry để không giữ jti vô hạn.

InMemoryCache phù hợp cho test single-node hoặc local. Production cluster cần shared cache.

### 16.4. Test reverse proxy và htu

Chạy request qua cùng proxy topology production:
- TLS termination.
- Forwarded host/proto.
- Path prefix rewrite.
- Context path.
- Port normalization.

Proof được tạo theo public URI phải được server xác minh theo cùng canonical URI. Test chỉ chạy MockMvc trực tiếp có thể không phát hiện lỗi proxy.

## 17. Kiểm thử nonce và client retry

Mô phỏng:
1. Client gửi proof không nonce.
2. Server trả use_dpop_nonce và DPoP-Nonce.
3. Client tạo proof mới, jti mới, nonce mới.
4. Client retry.
5. Server chấp nhận nếu các validation khác đạt.

Negative tests:
- Nonce cũ.
- Nonce từ issuer khác.
- Nonce bị thiếu sau challenge.
- Retry cùng proof/jti.
- Server liên tục cấp nonce mới.
- Client retry quá số lần cho phép.

Nonce challenge không nên tạo retry storm. Client cần giới hạn số lần retry và ghi telemetry theo error code, không ghi raw proof/token.

## 18. DPoP và RFC 9068 test matrix kết hợp

| Access token | Proof | Kết quả |
|---|---|---|
| RFC 9068 hợp lệ, DPoP-bound | Proof đúng key, htm/htu/ath/jti đúng | Cho qua authentication |
| RFC 9068 hợp lệ, không có cnf binding | Proof có chữ ký đúng nhưng token không bound | Không coi là DPoP-bound |
| RFC 9068 sai audience | Proof đúng | Từ chối token |
| RFC 9068 sai typ | Proof đúng | Từ chối access token |
| Token đúng, proof sai ath | Sai access-token hash | Từ chối proof |
| Token đúng, proof sai jkt | Sai key thumbprint | Từ chối proof |
| Token đúng, proof replay | jti đã được dùng | Từ chối replay |
| Token hết hạn, proof mới | Proof hợp lệ | Từ chối token |
| Token hợp lệ, proof hợp lệ, thiếu scope | Authorization thiếu | 403 |
| Token/proof hợp lệ, object policy từ chối | Ownership/tenant denial | 403/404 theo policy |

Test từng failure layer riêng để xác định chính xác validator nào chịu trách nhiệm.

## 19. Troubleshooting theo triệu chứng

| Triệu chứng | Nguyên nhân có thể | Kiểm tra |
|---|---|---|
| JWT at+jwt bị từ chối type | Nimbus type validation chưa được điều chỉnh cho RFC 9068 | validateTypes và AtJwtValidator |
| Token profile hợp lệ nhưng 401 | issuer/audience/time/signature hoặc required claim sai | Decoder exception và claims |
| ID token được chấp nhận | Chỉ kiểm tra signature/issuer, thiếu type/audience profile | Thêm RFC 9068 validation |
| DPoP token bị từ chối vì scheme | Client gửi Bearer thay DPoP | Authorization header |
| DPoP proof signature sai | Key pair không khớp hoặc proof bị sửa | Public JWK và signer |
| jkt mismatch | Access token bound key khác proof key | cnf.jkt và JWK thumbprint |
| ath mismatch | Hash token sai hoặc token bị thay | Hash ASCII access token |
| htm mismatch | Proof tạo trước khi biết method cuối cùng | Tạo proof ngay trước send |
| htu mismatch | Reverse proxy/path/scheme khác | Canonical external URI |
| Proof replay bị chấp nhận trên node khác | Replay cache local | Shared atomic cache |
| Proof bị từ chối do iat | Clock skew giữa client/server | Clock synchronization và skew policy |
| Nonce challenge lặp vô hạn | Client không lưu nonce hoặc tạo proof không gắn nonce | DPoP-Nonce handling |
| Converter class không tồn tại | Dùng API 7.1 trong 6.5/7.0 | Resolved Security version |
| Replay validator class không tồn tại | Patch thấp hơn 6.5.12 | DependencyInsight và patch upgrade |
| Reactive DPoP integration thiếu | Giả định Servlet API có bản Reactive tương đương | Kiểm tra API Reactive cụ thể |

## 20. Các lỗi thiết kế thường gặp

1. **Coi DPoP proof là access token.** Hai JWT có purpose và signing key khác nhau.
2. **Dùng Bearer scheme cho DPoP-bound token.** Request phải dùng scheme DPoP theo protocol.
3. **Tái sử dụng proof JWT.** Mỗi request cần jti/proof mới.
4. **Không tính ath trên toàn bộ token string.** Hash payload hoặc decoded claims là sai.
5. **Không kiểm tra cnf.jkt.** Chữ ký proof hợp lệ nhưng không chứng minh key đã bind với token.
6. **Không kiểm tra htm/htu.** Proof có thể bị dùng cho request khác.
7. **Không có replay cache dùng chung.** Cluster có thể chấp nhận cùng proof hai lần.
8. **Bỏ qua DPoP-Nonce.** Không đáp ứng policy của AS/RS.
9. **Đưa private JWK vào proof header.** Làm lộ private key.
10. **Tin Forwarded header từ mọi client.** Attacker có thể tác động htu comparison.
11. **Cho phép ID token vào API.** Dẫn tới cross-JWT confusion.
12. **Tắt typ validation mà không thêm RFC 9068 validator.** Token purpose không còn được xác định.
13. **Chỉ kiểm tra issuer và signature.** Bỏ audience và required profile claims.
14. **Giả định client library tự tạo DPoP proof.** Cần xác minh HTTP/token client behavior.
15. **Giả định Reactive có cùng DPoP APIs với Servlet.** Tài liệu và API phải được kiểm tra riêng.
16. **Nâng một module Security riêng lẻ.** Có thể tạo split versions.
17. **Chỉ test unit decoder.** Không kiểm tra header extraction, proxy URI và replay.
18. **Không kiểm tra token_type từ AS.** Client có thể xử lý DPoP token như Bearer token.
19. **Không có key lifecycle cho client DPoP.** Key rotation làm token cũ mất khả năng sử dụng nếu binding không được xử lý.
20. **Log proof hoặc access token.** Làm lộ credential và request metadata.

## 21. Lộ trình nâng cấp để bật RFC 9068 và DPoP

**Bước 1 — Chốt token contract.** Xác định issuer, audience, client_id, scope, typ, signing algorithm, DPoP binding và nonce behavior.

**Bước 2 — Chọn Spring Boot release train.** Xác định Spring Security patch được Boot BOM quản lý.

**Bước 3 — Kiểm tra feature API.** Xác nhận createAtJwtValidator, DPoPAuthenticationProvider, DPoPProofJwtDecoderFactory, replay validator và converter có trong dependency graph.

**Bước 4 — Bật RFC 9068 validation.** Cấu hình type, issuer, audience và required claims; thêm custom validators nếu token profile cần.

**Bước 5 — Kiểm tra Authorization Server.** Xác nhận token endpoint nhận proof và phát token_type DPoP cùng cnf.jkt hoặc introspection binding.

**Bước 6 — Tích hợp client proof generation.** Quản lý key, tạo proof theo request, ath và nonce.

**Bước 7 — Tích hợp Resource Server DPoP.** Dùng provider/converter/decoder factory tương thích với version; cấu hình replay cache.

**Bước 8 — Chạy test matrix.** Positive/negative signature, claims, jkt, ath, htm, htu, nonce và replay.

**Bước 9 — Kiểm tra proxy topology.** Đảm bảo htu comparison dùng đúng URI công khai.

**Bước 10 — Rollout có kiểm soát.** Theo dõi DPoP success/failure, nonce challenge, replay rejection, 401/403 và client compatibility.

**Bước 11 — Có phương án rollback.** Giữ tương thích client/server và policy rõ nếu phải quay lại Bearer cho một nhóm client. Không âm thầm downgrade DPoP-bound token thành Bearer.

## 22. Observability và vận hành

Theo dõi các tín hiệu:
- Số request DPoP proof hợp lệ/không hợp lệ.
- Lý do proof validation failure: typ, signature, htm, htu, iat, jti, ath, jkt, nonce.
- Số replay proof bị từ chối.
- Tỷ lệ nonce challenge.
- Tỷ lệ RFC 9068 validation failure theo typ/issuer/audience/time/required claim.
- Token type DPoP vs Bearer theo client registration.
- Latency của proof validation và replay cache.
- Cache availability và eviction.

Không ghi:
- Raw access token.
- Raw DPoP proof.
- Private key.
- Full JWT payload nếu chứa PII.
- Authorization header.

Dùng reason code và correlation ID. Nếu cần ghi kid hoặc JWK thumbprint, kiểm tra logging policy và không tạo metric cardinality cao.

## 23. Checklist trước khi phát hành

- [ ] Authorization Server và Resource Server cùng hỗ trợ DPoP.
- [ ] Token response có token_type DPoP cho DPoP-bound token.
- [ ] Access token có binding cnf.jkt hoặc introspection metadata tương đương.
- [ ] Client giữ private key an toàn và không gửi private material.
- [ ] Proof có typ dpop+jwt và asymmetric alg được allowlist.
- [ ] Proof có jti, htm, htu, iat.
- [ ] Protected resource proof có ath đúng.
- [ ] Nonce được xử lý khi server yêu cầu.
- [ ] jti replay detection được bật và dùng cache phù hợp cluster.
- [ ] htu comparison xử lý reverse proxy và forwarded headers an toàn.
- [ ] DPoP token dùng Authorization scheme DPoP.
- [ ] RFC 9068 typ at+jwt/application/at+jwt được kiểm tra.
- [ ] RFC 9068 required claims được xác minh.
- [ ] Issuer, audience, signature, exp/nbf và algorithm policy được giữ.
- [ ] ID token bị từ chối tại Resource Server.
- [ ] JwtValidators.createAtJwtValidator có trong version thực tế.
- [ ] DPoP APIs khớp Spring Security patch version.
- [ ] Servlet/Reactive support được xác minh riêng.
- [ ] Test negative cho ath, jkt, htm, htu, nonce, replay và typ.
- [ ] Test multi-node replay cache.
- [ ] Test client token acquisition và downstream request thật.
- [ ] Logs không chứa token/proof/private key.
- [ ] Có rollout và rollback plan cho client chưa hỗ trợ DPoP.

## 24. Tài liệu tham khảo

- [RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449.html): DPoP proof, htm, htu, ath, nonce, key binding và replay.
- [RFC 9068 — JSON Web Token (JWT) Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068.html): typ at+jwt, required claims và Resource Server validation.
- [RFC 7515 — JSON Web Signature](https://www.rfc-editor.org/rfc/rfc7515): JWS signing và compact serialization.
- [RFC 7517 — JSON Web Key](https://www.rfc-editor.org/rfc/rfc7517): JWK/JWKS và public key representation.
- [Spring Security — DPoP-bound Access Tokens](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/dpop-tokens.html): DPoP Resource Server flow và Java proof generation.
- [Spring Security 6.5 — DPoP-bound Access Tokens](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/dpop-tokens.html): API theo Security 6.5.
- [Spring Security — JWT Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): JWT decoder, algorithm và RFC 9068 validation.
- [Spring Security — Reactive JWT Resource Server](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html): RFC 9068 validator với NimbusReactiveJwtDecoder.
- [Spring Security API — JwtValidators](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/jwt/JwtValidators.html): createAtJwtValidator và mốc version.
- [Spring Security API — DPoPAuthenticationProvider](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/authentication/DPoPAuthenticationProvider.html): DPoP authentication provider.
- [Spring Security API — DPoPProofJwtDecoderFactory](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/jwt/DPoPProofJwtDecoderFactory.html): proof decoder và validator factory.
- [Spring Security API — DPoPProofReplayValidator](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/jwt/DPoPProofReplayValidator.html): jti replay protection và cache.
- [Spring Security — What’s New in 6.5](https://docs.spring.io/spring-security/reference/6.5/whats-new.html): DPoP được giới thiệu trong Spring Security 6.5.

**Kết luận:** RFC 9068 chuẩn hóa loại JWT access token và các claims mà Resource Server phải xác minh; DPoP ràng buộc token với public key của client và yêu cầu proof mới cho mỗi request. Spring Security có RFC 9068 validator từ 6.5 và các DPoP Resource Server building blocks từ 6.5, với replay validator và request converter xuất hiện ở các mốc patch/minor sau đó. Hãy chọn đúng API theo Spring Security version, kiểm tra cả Authorization Server lẫn client và Resource Server, rồi test chữ ký, typ, claims, jkt, ath, htm, htu, nonce và replay trước khi rollout. **Không bật DPoP chỉ bằng cách thêm một header; toàn bộ token issuance, key binding và request verification phải cùng tuân thủ RFC 9449.**
