# JWK, kid, bộ nhớ đệm khóa và luân chuyển khóa ký

## 1. Tại sao JWKS và key rotation quan trọng với Resource Server JWT?

Một ứng dụng Spring WebFlux được bảo vệ bởi Spring Security OAuth2 Resource Server có thể nhận yêu cầu:

~~~http
GET /api/key-info HTTP/1.1
Host: api.example.test
Authorization: Bearer <signed-access-token>
~~~

Authorization Server phát access token JWT ký bằng một **private signing key**. Resource Server phải xác minh chữ ký bằng **public verification key** phù hợp trước khi tin issuer, audience, subject, scopes và các claims khác.

Khi nhà cung cấp danh tính thay cặp khóa ký:
- JWT mới có thể mang `kid` mới trong JOSE header.
- Bộ khóa công khai được công bố qua **JWKS** có thêm public key mới.
- Nhiều instances WebFlux vẫn có thể giữ **JWKS cũ trong cache**.
- Nếu signer dùng khóa mới trước khi các verifiers nhận public key mới, một JWT mới và hợp lệ có thể bị **401**.
- Nếu gỡ public key cũ trước khi tất cả access tokens ký bằng private key cũ hết hạn, những token còn hạn có thể bị từ chối sau lần làm mới cache.
- Nếu private key cũ bị lộ, giữ key đó quá lâu để “không lỗi 401” lại có thể tiếp tục cho phép JWT giả mạo được xác minh.

Bài này hướng dẫn **JWK, kid, bộ nhớ đệm khóa và luân chuyển khóa ký** trong ngữ cảnh **Resource Server JWT** của Spring Security Reactive. Nó không phải bài về tạo access token hoặc OAuth2 Login: Resource Server **xác minh token**, không có trách nhiệm phát JWT cho client.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích JWK, JWKS và `kid`, phân biệt khóa công khai và khóa bí mật.
2. Theo dõi luồng từ Bearer JWT qua `NimbusReactiveJwtDecoder` đến lựa chọn khóa, xác minh chữ ký và kiểm claims.
3. Phân tích `kty`, `kid`, `alg`, `use`, `n`, `e` và những private key parameters cần cấm công bố.
4. Nhận diện cache của JWK source, HTTP client, CDN và từng process khác nhau.
5. Lên kế hoạch rollout A → A+B → B an toàn, tính thời điểm gỡ khóa A từ token lifetime/clock skew.
6. Phân biệt planned key rotation với emergency revocation khi private key bị lộ.
7. Cấu hình đúng `issuer-uri`, `jwk-set-uri`, `audiences`, allowed algorithms trong Spring Boot WebFlux.
8. Tự chạy project Java 17+ với **RSA-signed JWT thật và JWKS server cục bộ**, không cần IdP thật.
9. Biết kiểm thử `mockJwt()` hoặc mock decoder **không chứng minh** signature/JWKS cache hoạt động.
10. Debug 401/403, key propagation, key ID collision, endpoint outage và nhiều vùng deployment.

## 2. JWK là gì?

**JWK — JSON Web Key**, chuẩn hóa trong RFC 7517, là biểu diễn JSON của một khóa mật mã và metadata liên quan. Đối với RSA public verification key:

~~~json
{
  "kty": "RSA",
  "kid": "signing-rsa-2027-b",
  "use": "sig",
  "alg": "RS256",
  "n": "base64url-rsa-modulus-example-only",
  "e": "AQAB"
}
~~~

Đây là **JSON minh họa**, không phải public key thật có thể xác minh JWT. `n` là modulus RSA được encode Base64URL, `e` là public exponent. Với RSA thật, các giá trị này phải đến từ cặp khóa được sinh an toàn.

| Field | Ý nghĩa | Quy tắc triển khai |
| --- | --- | --- |
| `kty` | Key type, ví dụ RSA, EC, OKP, oct | Phải tương thích thuật toán ký và key selector |
| `kid` | Key ID — identifier để tìm khóa ứng viên | Không phải bằng chứng chữ ký hợp lệ |
| `use` | Intended use, thường `sig` | Không dùng encryption-only key để xác minh chữ ký |
| `key_ops` | Các thao tác như `verify` hoặc `sign` | Phải phù hợp policy nếu provider khai báo |
| `alg` | Thuật toán dự kiến, như `RS256` | Không mở toàn bộ thuật toán theo token không tin cậy |
| `n` và `e` | RSA public modulus và exponent | Có thể công bố trong public JWKS |
| `crv`, `x`, `y` | Các thành phần thường gặp của EC key | Không lẫn với RSA modulus |
| `x5c`, `x5t` | Certificate chain/thumbprint khi có | Cần trust policy, không mặc nhiên nâng quyền |
| `d`, `p`, `q`, `dp`, `dq`, `qi` | Các RSA private parameters | **Tuyệt đối không công bố trong public JWKS** |
| `k` đối với `oct` | Khóa đối xứng bí mật | Không đưa lên một public JWKS endpoint |

**Public key có thể công bố, private signing key phải giữ kín** tại Authorization Server/HSM/KMS. Resource Server không cần private signing key để xác minh RSA/ECDSA signed JWT. Nếu ai đó tải được private JWK từ một public endpoint, đây là sự cố bảo mật nghiêm trọng, cần đóng nguồn rò và luân chuyển khóa khẩn cấp.

### 2.1. JWK khác JWT, JWS và access token

- **JWK:** thông tin về một khóa.
- **JWK Set/JWKS:** danh sách các JWK trong object `{"keys":[...]}`.
- **JWS:** cơ chế ký payload bằng JOSE; JWS Compact thường có ba đoạn.
- **JWT:** token mang claims như `iss`, `sub`, `aud`, `exp`.
- **OAuth access token:** credential gửi resource server; có thể là JWT hoặc opaque.
- **OIDC ID token:** kết quả xác thực cho OAuth/OIDC client; không dùng thay access token tới business API.

JWT payload có thể Base64URL decode mà không cần secret. Chữ ký **không mã hóa claims**, nên không nhét mật khẩu, private keys, access secrets hoặc dữ liệu cá nhân không cần thiết vào claims.

### 2.2. Tại sao dùng public key thay shared secret ở nhiều API?

Nếu nhiều resource servers cùng giữ HMAC symmetric secret, một API bị chiếm có thể có key material đủ để tạo chữ ký mới. Với ký bất đối xứng, Resource Servers thường chỉ có **public verification keys**; private signing key ở một trust boundary riêng.

Tất nhiên public key không làm authorization tự đúng: API vẫn phải kiểm issuer, audience, expiry, scopes, tenant và object ownership.

## 3. JWKS: một bộ khóa, nhiều kid

Một JWKS thường có dạng:

~~~json
{
  "keys": [
    {
      "kty": "RSA",
      "kid": "rsa-A",
      "use": "sig",
      "alg": "RS256",
      "n": "public-modulus-A-example",
      "e": "AQAB"
    },
    {
      "kty": "RSA",
      "kid": "rsa-B",
      "use": "sig",
      "alg": "RS256",
      "n": "public-modulus-B-example",
      "e": "AQAB"
    }
  ]
}
~~~

Các modulus ở đây chỉ là sơ đồ, không phải material RSA thật. Điểm quan trọng là **A và B cùng tồn tại** trong giai đoạn rollover. Spring Security Reactive có thể tải JWKS và chọn khóa ứng viên phù hợp; không chọn `keys[0]` hoặc key cuối cùng theo thứ tự array.

JWKS URL không cố định với mọi provider. Một số nhà cung cấp dùng OIDC Discovery/Authorization Server Metadata với field `jwks_uri`; một số cung cấp URI trực tiếp. Phải dùng **địa chỉ do issuer tin cậy công bố**, không tự ghép một path rồi coi đó là đúng.

### 3.1. Phân biệt endpoint và nội dung

- `issuer-uri` xác định nhà phát hành mà JWT `iss` phải khớp.
- `jwk-set-uri` xác định nguồn public keys được Resource Server dùng.
- `audiences` xác định resource mà token phải được cấp cho.

Nguồn JWKS có public key của đúng issuer **không thay được** audience validation. ID token OIDC của web client có thể cũng dùng khóa của cùng issuer; API vẫn phải từ chối ID token nếu `aud` không dành cho API.

### 3.2. Điều gì xảy ra nếu JWKS chứa nhiều loại khóa?

Một JWKS có thể chứa RSA, EC, signing key và encryption key. Key selection phải xét `kid`, `kty`, `use/key_ops`, `alg` và policy của verifier. Không cho client tự chọn một key tùy ý bằng cách sửa header rồi bỏ qua xác minh chữ ký.

## 4. kid là selector, không phải một chữ ký

JWT dạng JWS thường là:

~~~text
BASE64URL(protectedHeader).BASE64URL(payload).BASE64URL(signature)
~~~

Header minh họa:

~~~json
{
  "alg": "RS256",
  "kid": "rsa-B",
  "typ": "at+jwt"
}
~~~

`kid` trong JWT header giúp tìm key với ID phù hợp trong trusted JWKS. Sau khi tìm, verifier **vẫn phải kiểm JWS signature bằng public key đó**, và sau đó kiểm claims. Attacker có thể tự ghi `kid=rsa-B` vào một token, nhưng nếu chữ ký không được tạo bằng private key B hợp lệ, token vẫn phải bị từ chối.

### 4.1. Trình tự từ Bearer JWT đến controller

~~~text
HTTP Authorization: Bearer <JWT>
      |
      v
ServerBearerTokenAuthenticationConverter
      |
      v
JwtReactiveAuthenticationManager
      |
      v
ReactiveJwtDecoder / NimbusReactiveJwtDecoder
      |
      +--> Parse header CHƯA đáng tin (kid, alg)
      +--> Tìm public keys từ trusted JWKS/cache
      +--> Chọn candidates theo kid/kty/use/alg
      +--> Verify JWS signature
      +--> Validate iss, aud, exp, nbf, typ/profile policy
      |
      +--> Sai khóa/chữ ký/claim: 401
      |
      v
JwtAuthenticationToken (principal=Jwt)
      |
      v
scope/scp -> SCOPE_* authorities
      |
      +--> Thiếu quyền: 403
      |
      v
WebFlux controller -> service -> data
~~~

Đây là pipeline khái niệm; các filter CORS/CSRF, matcher và custom SecurityWebFilterChain có thể ảnh hưởng thứ tự xử lý thực tế.

### 4.2. Khi không có kid hoặc kid không tồn tại

JOSE không bắt buộc tất cả tokens phải có `kid`; một số verifier có thể thử các ứng viên khóa theo policy. Không hứa token thiếu kid “luôn 401” hoặc “luôn được chấp nhận”: hành vi phụ thuộc JWK source, algorithm và library. Với nhiều signing keys, issuer nên cung cấp **kid rõ ràng và ổn định**.

Nếu JWT có kid mới mà cache đang giữ bộ cũ, decoder có thể thử làm mới keys theo implementation/refresh policy. Không hứa **mỗi kid lạ đều gây ngay một JWKS fetch**, vì cách đó cũng có thể bị lợi dụng làm DoS.

### 4.3. Kid collision và tái sử dụng kid

RFC 7517 khuyến nghị các keys khác nhau trong cùng JWK Set dùng **kid khác nhau**. Không luân chuyển private RSA key từ vật liệu A sang B nhưng giữ `kid="default"` nếu không có lý do/đặc tả và kiểm thử rất rõ; thư viện/caches có thể chọn nhầm hoặc giữ public key cũ cùng ID.

Thiết kế tốt: một **versioned kid** cho một signing key version. Không coi kid là secret hoặc identifier toàn cục giữa mọi issuers.

### 4.4. Không bao giờ mở URL hoặc file từ kid chưa tin cậy

Sai:

~~~java
// PSEUDOCODE NGUY HIỂM: kid là input từ token chưa được verify.
Path keyPath = Path.of("/trusted-keys/" + rawKid + ".pem");
PublicKey key = readPublicKey(keyPath);
~~~

Nếu custom code không kiểm path/characters, attacker có thể đưa path traversal/injection. Tương tự, RFC 8725 cảnh báo dùng kid để xây SQL/LDAP lookup không được sanitize.

`jku`/`x5u` trong JWT header có thể là URL do attacker gửi; không theo một URL arbitrary để tải keys — đó là rủi ro SSRF và key substitution. Với production, dùng trusted issuer/JWKS URL allowlist trong cấu hình server.

## 5. Spring Security Reactive dùng những class nào?

| Class | Vai trò |
| --- | --- |
| `ServerHttpSecurity` | Reactive security DSL |
| `SecurityWebFilterChain` | Chuỗi WebFilter bảo vệ request |
| `ServerBearerTokenAuthenticationConverter` | Lấy Bearer token từ ServerWebExchange |
| `JwtReactiveAuthenticationManager` | Điều phối token authentication |
| `ReactiveJwtDecoder` | Hợp đồng async decode/verify JWT |
| `NimbusReactiveJwtDecoder` | Implementation phổ biến dùng Nimbus JOSE/JWKS |
| `JwtAuthenticationToken` | Authentication cho JWT đã được xác minh |
| `JwtValidators` / `JwtClaimValidator` | Kiểm issuer, timestamps, audience và policy thêm |
| `ReactiveSecurityContextHolder` | Truy cập SecurityContext trong Reactor Context |

**Đừng dùng các class Servlet** như `HttpSecurity`, `SecurityFilterChain`, `BearerTokenAuthenticationFilter` và `NimbusJwtDecoder` để cấu hình WebFlux resource server. `Jwt` model có thể dùng chung, nhưng filter chain và decoder là Reactive.

### 5.1. Tính năng nhận khóa mới tự động không có nghĩa “ngay lập tức”

Theo Spring Security Resource Server Reactive, resource server có thể tự nhận khóa public mới khi Authorization Server công bố chúng. Nhưng:
- Mỗi process/instance có thể nhìn một phiên bản JWKS khác nhau.
- Các HTTP caches/proxies/CDNs có thể giữ JSON cũ.
- Một decoder đã warm cache không nhất thiết thấy key mới ngay tại một mốc đoán trước.
- Không có bảo đảm mọi token mới được chấp nhận ngay sau khi issuer đổi signing key.
- Việc mất kết nối JWKS không được biến thành “bỏ kiểm chữ ký”.

**Do đó rollover an toàn vẫn cần pre-publish, overlap và vận hành.**

### 5.2. Default trusted algorithms

Trong tài liệu Spring Security 6.5 Reactive, `NimbusReactiveJwtDecoder` trong cấu hình phổ biến mặc định chỉ tin `RS256`. Nếu provider thật dùng RS512/ES256, phải review và cấu hình algorithm allowlist tương ứng. Không chấp nhận `alg=none` hoặc mọi thuật toán do JWT header tự đề xuất.

Ví dụ nếu thực sự muốn RS512:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.test/issuer
          jwk-set-uri: https://idp.example.test/issuer/jwks
          audiences:
            - orders-api
          jws-algorithms:
            - RS512
~~~

**Đây là cấu hình thay thế** cho token RS512, không dùng đồng thời với project RS256 bên dưới. Nếu token ký RS256 mà decoder chỉ cho RS512, authentication failure là đúng.

## 6. JWKS cache chứa gì và nằm ở đâu?

Nếu mọi request đều gọi IdP để lấy public keys, API bị phụ thuộc mạng ở mức request path, tăng latency và dễ làm IdP nghẽn khi load cao. JWKS caching giúp decoder verify nhiều JWT bằng những public keys đã tải trước.

| Lớp | Ví dụ dữ liệu | Rủi ro khi stale |
| --- | --- | --- |
| Local decoder/JWK source | JWKS JSON hoặc candidate public keys | Chưa thấy B hoặc còn giữ A |
| HTTP client/gateway tới IdP | JWKS response cache | Có thể trả bộ keys cũ |
| CDN ở trước JWKS endpoint | Public JWKS JSON theo edge region | Một vùng cập nhật chậm |
| Mỗi pod WebFlux | Cache process-local riêng | Pod 1 nhận B, pod 2 chưa |
| Shared cache tự thiết kế | JWKS theo URL/issuer | Key collisions nếu không partition trust đúng |
| Hardcoded PEM/public key | Bản key từ deployment | Không tự theo JWKS rotation |
| Browser/private cache | API response/cookie | **Không phải** cache JWT public keys ở Resource Server |

Đừng nhầm với `CacheControl.noStore()` của một HTTP response chứa dữ liệu nhạy cảm. JWKS chỉ công bố **public keys**; HTTP caching policy của JWKS endpoint có thể là public, nhưng private signing key phải không xuất hiện ở đó.

### 6.1. Ba “đồng hồ” khác nhau

1. **JWT exp/nbf:** thời hạn token được cho phép sử dụng.
2. **JWKS cache freshness/TTL:** bao lâu decoder hoặc intermediary giữ một bản key set cũ.
3. **Rotation overlap:** bao lâu JWKS công bố đồng thời A+B để tokens A và B cùng có thể xác minh.

Ví dụ token A TTL 20 phút, JWKS được cache 5 phút: **không** có nghĩa có thể gỡ A chỉ sau 5 phút kể từ lúc chuyển ký. Một token A được phát sát thời điểm chuyển ký vẫn có thể còn hợp lệ gần 20 phút.

### 6.2. Không lấy default cache từ Servlet sang Reactive

Spring Security Servlet có tài liệu về `NimbusJwtDecoder` và builder `.cache(Cache)`. **Reactive** sử dụng `NimbusReactiveJwtDecoder`, API builder khác (ví dụ `webClient(...)`, `jwtProcessorCustomizer(...)`). Không sao chép:

~~~java
// KHÔNG DÙNG cho Reactive builder nếu API không có method cache.
NimbusReactiveJwtDecoder.withJwkSetUri(uri)
        .cache(cacheManager.getCache("jwks"))
        .build();
~~~

Đây là **phản ví dụ không compile theo Reactive builder 6.5**. Không tuyên bố mọi triển khai Reactive cache “chính xác 5 phút” vì một con số trong tài liệu Servlet. Nếu cần một SLA rotation, phải kiểm Spring Security/Nimbus version, loại JWK source, HTTP client/caching, CDN behavior và kết quả integration tests trên hệ thống của mình.

### 6.3. Một HTTP response JWKS có thể có caching headers

~~~http
HTTP/1.1 200 OK
Content-Type: application/jwk-set+json
Cache-Control: public, max-age=300
ETag: "keyset-version-42"
~~~

**Đây là policy minh họa**, không phải mặc định bắt buộc của Spring Security/IdP. HTTP Cache-Control ở issuer/CDN không tự chứng minh Nimbus Reactive decoder dùng đúng 300 giây làm TTL. Cần kiểm lớp cache thực sự đang quyết định sự mới/cũ của key material.

### 6.4. Unknown kid storms

Nếu attacker gửi nhiều JWT với header chứa `kid` ngẫu nhiên, một implementation naive có thể tải JWKS hàng nghìn lần, làm tăng tải IdP và latency. Đối sách:
- Để thư viện JOSE/JWK source có refresh bounds/caching phù hợp.
- Rate-limit/risk-control các request không hợp lệ trước khi quá tải.
- Không log raw kid như metric label không giới hạn cardinality.
- Giới hạn response sizes/timeouts của trusted JWKS endpoint.
- Không “on unknown kid, fetch unlimited in every request” bằng code tự chế.

**Không fallback sang accept JWT** khi JWKS fetch thất bại.

## 7. Kế hoạch rotation bình thường: A → A+B → B

Quy trình khuyến nghị cho **planned signing-key rollover**:

1. **Sinh signing key B** an toàn trong KMS/HSM/Authorization Server; giữ private B ở nơi ký, không sao chép sang Resource Server.
2. **Đặt kid B mới**, khác kid A. Giữ danh sách keys/versions theo quy trình audit.
3. **Công bố public B trước**: JWKS trả A+B nhưng issuer vẫn ký JWT mới bằng private A.
4. **Đợi propagation**: caches, CDNs, regions và resource-server pods có cơ hội nhận JWKS gồm B. Có thể dùng canary/token staging để xác nhận.
5. **Chuyển issuer sang ký bằng B**: JWT mới có `kid=B`; tokens A đã cấp trước đó vẫn có thể còn hợp lệ.
6. **Giữ public A+B**: cả JWT A cũ và JWT B mới được verify trong giai đoạn overlap.
7. **Đợi lifetime còn lại của tokens A**: tính từ *thời điểm cuối cùng thật sự ký A*, không chỉ lịch dự kiến.
8. **Gỡ public A** sau max token lifetime, allowed clock skew, các retry/offline clients và safety margin.
9. **Retire private A** theo key management policy, hoàn tất audit và monitoring.

~~~text
T0                 T1                  T2                   T3
|------------------|-------------------|--------------------|
JWKS: [A]          JWKS: [A,B]         JWKS: [A,B]          JWKS: [B]
Signer: A          Signer: A           Signer: B             Signer: B
                   ^                   ^                    ^
                   |                   |                    |
              Pre-publish      Switch signing        Remove A after
              public B         to private B          last A-token expiry
~~~

**Thứ tự không được đảo**: công bố B trước khi ký B; giữ A đến khi không còn token A phải được chấp nhận.

### 7.1. Tính thời điểm gỡ A

Một điều kiện lập kế hoạch:

~~~text
T_remove_A >= T_last_A_token_issued
              + max_validity_of_A_tokens
              + allowed_clock_skew
              + operational_safety_margin
~~~

Ngoài ra, B phải được phân phối đủ rộng **trước** khi switch signing. Nếu có token TTL biến thiên, token exchange, background jobs, offline clients hay multi-region signers, lấy max thực sự và tình huống vận hành phù hợp.

### 7.2. Ví dụ thời gian

Giả định minh họa:
- 10:00: JWKS công bố A+B.
- 10:15: đã kiểm tra các vùng; issuer dừng ký A và bắt đầu ký B.
- JWT A có lifetime tối đa 20 phút.
- Clock skew cho phép 1 phút và safety margin 4 phút.

Mốc gỡ A sớm nhất theo giả định:

~~~text
10:15 + 20 phút + 1 phút + 4 phút = 10:40
~~~

Không dùng mốc này cho hệ thống thật nếu còn signer phát JWT A sau 10:15 hoặc có access tokens dài hơn 20 phút.

### 7.3. Vì sao không giữ A vĩnh viễn?

Giữ public A sau khi đã retire vẫn làm trust surface rộng hơn cần thiết và khó chứng minh các signing keys cũ đã được loại bỏ. Có thể không ngay lập tức gây nguy cơ nếu private A an toàn, nhưng vận hành lâu dài phải quản lý key retirement rõ ràng.

### 7.4. Vì sao không gỡ A ngay khi ký B?

Vì token A có thể còn `exp` hợp lệ. Khi decoder mới tải JWKS B-only, nó sẽ không tìm được A; sau khi cache refresh, một user có token A chưa hết hạn có thể nhận 401. Planned rotation cần một **cửa sổ chồng lấp**, không phải cập nhật một công tắc tại một thời điểm.

## 8. Emergency rotation khi private key bị lộ

Planned rotation tối ưu cho tính liên tục. **Compromised private signing key** là tình huống khác: một attacker giữ private A có thể ký token giả với kid A nếu verifier còn chấp nhận public A.

Vì thế incident response có thể cần:
- Ngừng ký bằng A ngay.
- Phát public B trước nếu đủ khả năng, và chuyển signer sang B.
- Loại A khỏi trust policy/JWKS **sớm hơn** expiry của token A, chấp nhận việc một số token thật bị 401.
- Purge hoặc invalidate caches ở những nơi có hỗ trợ; xác minh per instance/region.
- Có thể restart/redeploy verifiers đã giữ A khi cần chặn stale trust nhanh hơn.
- Vô hiệu hóa credentials/refresh tokens và phối hợp với người dùng/client có liên quan.
- Điều tra phạm vi lộ key, kiểm KMS, backups, pipelines, logs và IAM.
- Theo dõi token-substitution/forged claims và hành vi bất thường.

**Chỉnh JWKS tại origin không đồng nghĩa tất cả caches ngừng giữ A ngay.** Tác động của bất đồng bộ cần có trong playbook. Không bỏ xác minh chữ ký hoặc tự tăng allowed algorithms để “đỡ lỗi 401”.

## 9. Cấu hình Spring Boot WebFlux Resource Server JWT

Một cấu hình rõ ràng:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.test/issuer
          jwk-set-uri: https://idp.example.test/issuer/jwks
          audiences:
            - orders-api
~~~

- `issuer-uri` dùng để xác minh `iss`.
- `jwk-set-uri` chỉ nơi lấy public keys, tránh phải khám phá JWKS URL lúc khởi tạo.
- `audiences` đòi JWT được cấp đúng resource server.
- Key selection dựa trên headers/JWK phù hợp nhưng vẫn phải verify signature.

**URL này là dữ liệu ví dụ, không có IdP thật.** Production phải dùng HTTPS issuer/JWKS đáng tin cậy. Khi chỉ khai báo issuer, Spring Security 6.5 Reactive có thể defer discovery đến Bearer request đầu tiên nhờ `SupplierReactiveJwtDecoder`. Khi tự tạo decoder, việc lazy initialization có thể khác; không mặc nhiên cho rằng mọi custom bean không bao giờ gọi IdP ở startup.

### 9.1. Nếu cần custom ReactiveJwtDecoder

Ví dụ snippet:

~~~java
NimbusReactiveJwtDecoder decoder =
        NimbusReactiveJwtDecoder.withJwkSetUri(jwkSetUri).build();

decoder.setJwtValidator(
        new DelegatingOAuth2TokenValidator<>(
                JwtValidators.createDefaultWithIssuer(issuerUri),
                new JwtClaimValidator<List<String>>(
                        "aud",
                        aud -> aud != null && aud.contains("orders-api"))));
~~~

Đây là **snippet trong method**, cần imports và các biến `jwkSetUri`/`issuerUri`. Lý do đặt validator tường minh: một `ReactiveJwtDecoder` custom có thể **thay** Boot's auto-configuration. Chỉ xác minh chữ ký bằng trusted JWKS **không tự bảo đảm** issuer/audience đúng nếu ta quên gắn validators.

### 9.2. Timeout/Proxy WebClient cho JWKS

Reactive builder hỗ trợ `webClient(...)`:

~~~java
// Snippet tùy biến, cần WebClient, Reactor Netty và các imports.
WebClient jwksClient = WebClient.builder()
        .clientConnector(new ReactorClientHttpConnector(
                HttpClient.create()
                        .responseTimeout(Duration.ofSeconds(5))))
        .build();

NimbusReactiveJwtDecoder decoder =
        NimbusReactiveJwtDecoder.withJwkSetUri(jwkSetUri)
                .webClient(jwksClient)
                .build();
~~~

Nếu dùng bean decoder custom như trên, phải thêm issuer, audience validators tương ứng và cấu hình algorithms cho đúng issuer. Không block Reactor event loop để tự tải JWKS bằng `block()` hoặc `RestTemplate` trong AuthenticationWebFilter.

## 10. Mã Java 17+ chạy được: JWKS cục bộ và test rotation

Dự án có:
- Ứng dụng Spring Boot WebFlux JWT Resource Server với routes public/protected.
- Integration tests thật tạo **hai cặp RSA** và JWS có chữ ký thật, cung cấp **public JWKS** từ `HttpServer` của JDK ở `127.0.0.1`.
- `NimbusReactiveJwtDecoder` thật verify signature, `iss`, `aud`, expiry.
- Bài test HTTP gửi Bearer header vào SecurityWebFilterChain và mock decoder để kiểm status/authorities; **không nhầm mock với crypto validation**.

### 10.1. Cấu trúc project

~~~text
webflux-jwks-rotation/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── java/demo/
    │   │   ├── DemoApplication.java
    │   │   ├── SecurityConfig.java
    │   │   └── ApiController.java
    │   └── resources/
    │       └── application.yml
    └── test/java/demo/
        ├── JwksRotationTest.java
        └── ResourceServerHttpTest.java
~~~

### 10.2. settings.gradle

~~~groovy
rootProject.name = 'webflux-jwks-rotation'
~~~

### 10.3. build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.7'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('compileTestJava') {
    options.compilerArgs.addAll(['--add-modules', 'jdk.httpserver'])
}

tasks.named('test') {
    useJUnitPlatform()
    jvmArgs '--add-modules', 'jdk.httpserver'
}
~~~

Gradle cần JDK 17+ và các dependencies tương thích. Các mã kiểm thử dùng `com.sun.net.httpserver.HttpServer` thuộc module `jdk.httpserver` để dựng server local. Không chạy IdP thật và không cần thêm một mock-server dependency riêng.

### 10.4. application.yml

`src/main/resources/application.yml`:

~~~yaml
server:
  port: 8080

spring:
  application:
    name: webflux-jwks-rotation
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.test/issuer
          jwk-set-uri: https://idp.example.test/issuer/jwks
          audiences:
            - orders-api
~~~

Khi chạy app không có IdP, public endpoint vẫn có thể hoạt động; protected JWT request sẽ không xác minh thành công với URL ví dụ. Tests dùng JWKS local hoặc mocked decoder nên không yêu cầu kết nối tới hostname giả.

### 10.5. DemoApplication.java

`src/main/java/demo/DemoApplication.java`:

~~~java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

### 10.6. SecurityConfig.java

`src/main/java/demo/SecurityConfig.java`:

~~~java
package demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.context.NoOpServerSecurityContextRepository;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfig {

    @Bean
    SecurityWebFilterChain filterChain(ServerHttpSecurity http) {
        return http
                .securityContextRepository(
                        NoOpServerSecurityContextRepository.getInstance())
                // Chỉ Bearer-only: không có browser cookie login/Basic.
                .csrf(ServerHttpSecurity.CsrfSpec::disable)
                .httpBasic(ServerHttpSecurity.HttpBasicSpec::disable)
                .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
                .authorizeExchange(ex -> ex
                        .pathMatchers(HttpMethod.GET, "/public/ping")
                                .permitAll()
                        .pathMatchers(HttpMethod.GET, "/api/key-info")
                                .hasAuthority("SCOPE_keys.read")
                        .pathMatchers(HttpMethod.GET, "/api/subject")
                                .authenticated()
                        .anyExchange().denyAll())
                .oauth2ResourceServer(oauth2 -> oauth2
                        .jwt(Customizer.withDefaults()))
                .build();
    }
}
~~~

`NoOpServerSecurityContextRepository` không lưu authentication qua session, nhưng nó không cấm mọi WebSession dùng ở những code khác. `csrf(...disable)` ở đây **chỉ áp cho demo API Bearer-only**; nếu hệ thống dùng cookie/Basic/form/OIDC login với browser ambient credentials, phải thiết kế CSRF theo các security chains/routes tương ứng.

### 10.7. ApiController.java

`src/main/java/demo/ApiController.java`:

~~~java
package demo;

import java.util.Map;

import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
public class ApiController {

    @GetMapping("/public/ping")
    public Mono<String> ping() {
        return Mono.just("pong");
    }

    @GetMapping("/api/key-info")
    public Mono<Map<String, String>> keyInfo(
            @AuthenticationPrincipal Jwt jwt) {

        Object kid = jwt.getHeaders().get("kid");
        return Mono.just(Map.of(
                "subject", jwt.getSubject(),
                "kid", kid == null ? "absent" : kid.toString()));
    }

    @GetMapping("/api/subject")
    public Mono<Map<String, String>> subject(
            @AuthenticationPrincipal Jwt jwt) {
        return Mono.just(Map.of("subject", jwt.getSubject()));
    }
}
~~~

Endpoint `/api/key-info` trả kid/subject **chỉ để minh họa sau authentication**; production có thể hạn chế hoặc không trả key identifier, không bao giờ trả raw JWT, private key, access token hoặc tất cả claims. `kid` đơn lẻ không bảo đảm token an toàn, chỉ chữ ký và validators đã vượt qua mới cho controller chạy.

## 11. JwksRotationTest.java — ký RSA thật, public JWKS cục bộ

Tạo file `src/test/java/demo/JwksRotationTest.java`:

~~~java
package demo;

import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.interfaces.RSAPrivateKey;
import java.security.interfaces.RSAPublicKey;
import java.time.Instant;
import java.util.Arrays;
import java.util.Date;
import java.util.List;
import java.util.concurrent.atomic.AtomicReference;

import com.nimbusds.jose.JOSEException;
import com.nimbusds.jose.JWSAlgorithm;
import com.nimbusds.jose.JWSHeader;
import com.nimbusds.jose.crypto.RSASSASigner;
import com.nimbusds.jose.jwk.JWK;
import com.nimbusds.jose.jwk.JWKSet;
import com.nimbusds.jose.jwk.KeyUse;
import com.nimbusds.jose.jwk.RSAKey;
import com.nimbusds.jwt.JWTClaimsSet;
import com.nimbusds.jwt.SignedJWT;
import com.sun.net.httpserver.HttpServer;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtClaimValidator;
import org.springframework.security.oauth2.jwt.JwtException;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusReactiveJwtDecoder;

import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;

class JwksRotationTest {

    private static final String ISSUER =
            "https://idp.example.test/issuer";
    private static final String AUDIENCE = "orders-api";

    private HttpServer server;
    private final AtomicReference<String> jwks =
            new AtomicReference<>();
    private KeyMaterial keyA;
    private KeyMaterial keyB;

    private record KeyMaterial(
            String kid, RSAPrivateKey privateKey, RSAKey publicJwk) {
    }

    @BeforeEach
    void setup() throws Exception {
        keyA = generateKey("rsa-A");
        keyB = generateKey("rsa-B");
        publish(keyA);

        server = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/jwks", exchange -> {
            byte[] body = jwks.get()
                    .getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders().set(
                    "Content-Type", "application/jwk-set+json");
            exchange.getResponseHeaders().set(
                    "Cache-Control", "no-cache");
            exchange.sendResponseHeaders(200, body.length);
            try (OutputStream out = exchange.getResponseBody()) {
                out.write(body);
            }
        });
        server.start();
    }

    @AfterEach
    void cleanup() {
        if (server != null) {
            server.stop(0);
        }
    }

    private static KeyMaterial generateKey(String kid)
            throws Exception {
        KeyPairGenerator generator =
                KeyPairGenerator.getInstance("RSA");
        generator.initialize(2048);
        KeyPair pair = generator.generateKeyPair();

        RSAKey publicJwk = new RSAKey.Builder(
                (RSAPublicKey) pair.getPublic())
                .keyID(kid)
                .keyUse(KeyUse.SIGNATURE)
                .algorithm(JWSAlgorithm.RS256)
                .build();
        return new KeyMaterial(
                kid,
                (RSAPrivateKey) pair.getPrivate(),
                publicJwk);
    }

    private void publish(KeyMaterial... keys) {
        // Chỉ public JWK được serialize ra HTTP endpoint.
        List<JWK> publicKeys = Arrays.stream(keys)
                .map(k -> (JWK) k.publicJwk())
                .toList();
        jwks.set(new JWKSet(publicKeys).toString());
    }

    private NimbusReactiveJwtDecoder decoder() {
        String uri = "http://127.0.0.1:"
                + server.getAddress().getPort() + "/jwks";
        NimbusReactiveJwtDecoder decoder =
                NimbusReactiveJwtDecoder.withJwkSetUri(uri).build();

        decoder.setJwtValidator(
                new DelegatingOAuth2TokenValidator<>(
                        JwtValidators.createDefaultWithIssuer(
                                ISSUER),
                        new JwtClaimValidator<List<String>>(
                                "aud",
                                aud -> aud != null
                                        && aud.contains(AUDIENCE))));
        return decoder;
    }

    private static String sign(
            KeyMaterial signingKey,
            String issuer,
            String audience,
            Instant expiresAt) throws JOSEException {

        Instant now = Instant.now();
        JWTClaimsSet claims = new JWTClaimsSet.Builder()
                .issuer(issuer)
                .subject("reader-42")
                .audience(audience)
                .issueTime(Date.from(now.minusSeconds(20)))
                .notBeforeTime(Date.from(now.minusSeconds(20)))
                .expirationTime(Date.from(expiresAt))
                .claim("scope", "keys.read")
                .build();

        SignedJWT signedJwt = new SignedJWT(
                new JWSHeader.Builder(JWSAlgorithm.RS256)
                        .keyID(signingKey.kid())
                        .build(),
                claims);
        signedJwt.sign(
                new RSASSASigner(signingKey.privateKey()));
        return signedJwt.serialize();
    }

    private String validToken(KeyMaterial key)
            throws JOSEException {
        return sign(key, ISSUER, AUDIENCE,
                Instant.now().plusSeconds(600));
    }

    @Test
    void firstVersionValidWithAOnly() throws Exception {
        StepVerifier.create(
                decoder().decode(validToken(keyA)))
                .assertNext(jwt -> {
                    assertEquals("reader-42", jwt.getSubject());
                    assertEquals("rsa-A",
                            jwt.getHeaders().get("kid"));
                })
                .verifyComplete();
    }

    @Test
    void overlapAllowsBothOldAndNewTokens()
            throws Exception {
        publish(keyA, keyB);
        String a = validToken(keyA);
        String b = validToken(keyB);

        NimbusReactiveJwtDecoder d = decoder();

        StepVerifier.create(d.decode(a))
                .assertNext(jwt -> assertEquals("rsa-A",
                        jwt.getHeaders().get("kid")))
                .verifyComplete();
        StepVerifier.create(d.decode(b))
                .assertNext(jwt -> assertEquals("rsa-B",
                        jwt.getHeaders().get("kid")))
                .verifyComplete();
    }

    @Test
    void freshDecoderAfterRetirementRejectsA()
            throws Exception {
        String tokenA = validToken(keyA);
        publish(keyB);

        StepVerifier.create(decoder().decode(tokenA))
                .expectError(JwtException.class).verify();

        StepVerifier.create(
                decoder().decode(validToken(keyB)))
                .assertNext(jwt -> assertEquals("rsa-B",
                        jwt.getHeaders().get("kid")))
                .verifyComplete();
    }

    @Test
    void signedTokensWithWrongClaimsAreRejected()
            throws Exception {
        NimbusReactiveJwtDecoder d = decoder();

        String wrongIssuer = sign(keyA,
                "https://other.example.test", AUDIENCE,
                Instant.now().plusSeconds(600));
        String wrongAudience = sign(keyA,
                ISSUER, "other-api",
                Instant.now().plusSeconds(600));
        String expired = sign(keyA,
                ISSUER, AUDIENCE,
                Instant.now().minusSeconds(3600));

        StepVerifier.create(d.decode(wrongIssuer))
                .expectError(JwtException.class).verify();
        StepVerifier.create(d.decode(wrongAudience))
                .expectError(JwtException.class).verify();
        StepVerifier.create(d.decode(expired))
                .expectError(JwtException.class).verify();
    }

    @Test
    void kidAWithPrivateKeyBFailsSignature()
            throws Exception {
        // Header kid A, nhưng chữ ký được tạo bởi private B.
        JWTClaimsSet claims = new JWTClaimsSet.Builder()
                .issuer(ISSUER)
                .subject("reader-42")
                .audience(AUDIENCE)
                .issueTime(Date.from(
                        Instant.now().minusSeconds(20)))
                .expirationTime(Date.from(
                        Instant.now().plusSeconds(600)))
                .build();

        SignedJWT forgery = new SignedJWT(
                new JWSHeader.Builder(JWSAlgorithm.RS256)
                        .keyID("rsa-A").build(),
                claims);
        forgery.sign(new RSASSASigner(
                keyB.privateKey()));

        StepVerifier.create(
                decoder().decode(forgery.serialize()))
                .expectError(JwtException.class).verify();
    }
}
~~~

### 11.1. Năm điều được kiểm chứng

1. **Chữ ký RSA thật:** chỉ public A trong JWKS vẫn verify được token ký private A, đúng issuer/audience.
2. **Overlap:** khi JWKS có public A+B, decoder có thể chấp nhận JWT A và B.
3. **Gỡ A:** một **decoder mới** nhìn JWKS B-only từ chối JWT A, chấp nhận JWT B.
4. **Sai claims:** token được ký đúng nhưng issuer, audience hoặc expiration sai bị từ chối.
5. **Giả kid:** header nói kid A nhưng ký private B không vượt được signature verification.

**Test này không chứng minh cache đã tự refresh tức thời.** Mỗi giai đoạn dùng decoder mới hoặc đã thấy JWKS A+B ngay từ đầu. Để kiểm tra stale-key cache, phải reuse một decoder được warm với A, đổi JWKS của test server, rồi đo refresh behavior theo thời gian/điều kiện của version cụ thể.

`HttpServer` chạy trên localhost qua HTTP **chỉ phục vụ kiểm thử**; production JWKS dùng HTTPS/trusted issuer, không có private material trong response. RSA private keys chỉ nằm trong memory của test, không được serialize bởi phương thức `publish`.

## 12. ResourceServerHttpTest.java — HTTP 401/403 với mock decoder

Bài test thứ hai gửi Bearer header qua WebFlux SecurityWebFilterChain. Nó dùng `@MockitoBean ReactiveJwtDecoder` để giả lập decoded JWT, vì vậy **không kiểm chữ ký hoặc JWKS caching**.

`src/test/java/demo/ResourceServerHttpTest.java`:

~~~java
package demo;

import java.time.Instant;
import java.util.List;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.security.oauth2.jwt.BadJwtException;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.reactive.server.WebTestClient;

import reactor.core.publisher.Mono;

import static org.mockito.Mockito.when;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

@SpringBootTest
class ResourceServerHttpTest {

    @Autowired
    ApplicationContext context;

    @MockitoBean
    ReactiveJwtDecoder jwtDecoder;

    private WebTestClient client;

    @BeforeEach
    void setup() {
        client = WebTestClient.bindToApplicationContext(context)
                .apply(springSecurity())
                .configureClient()
                .build();

        when(jwtDecoder.decode("read-token"))
                .thenReturn(Mono.just(jwt(
                        "read-token", "keys.read")));
        when(jwtDecoder.decode("other-scope-token"))
                .thenReturn(Mono.just(jwt(
                        "other-scope-token", "profile")));
        when(jwtDecoder.decode("bad-token"))
                .thenReturn(Mono.error(
                        new BadJwtException("invalid test JWT")));
    }

    private Jwt jwt(String value, String scope) {
        Instant now = Instant.now();
        return Jwt.withTokenValue(value)
                .header("alg", "RS256")
                .header("kid", "rsa-A")
                .claim("iss", "https://idp.example.test/issuer")
                .claim("sub", "reader-42")
                .claim("aud", List.of("orders-api"))
                .claim("scope", scope)
                .issuedAt(now.minusSeconds(30))
                .expiresAt(now.plusSeconds(600))
                .build();
    }

    @Test
    void publicPingIs200() {
        client.get().uri("/public/ping")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("pong");
    }

    @Test
    void noBearerIs401() {
        client.get().uri("/api/key-info")
                .exchange()
                .expectStatus().isUnauthorized()
                .expectHeader().valueMatches(
                        "WWW-Authenticate", "Bearer.*");
    }

    @Test
    void invalidJwtIs401() {
        client.get().uri("/api/key-info")
                .headers(h -> h.setBearerAuth("bad-token"))
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void wrongScopeIs403() {
        client.get().uri("/api/key-info")
                .headers(h -> h.setBearerAuth(
                        "other-scope-token"))
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void correctScopeYieldsSafeKidMetadata() {
        client.get().uri("/api/key-info")
                .headers(h -> h.setBearerAuth("read-token"))
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.subject").isEqualTo("reader-42")
                .jsonPath("$.kid").isEqualTo("rsa-A")
                .jsonPath("$.tokenValue").doesNotExist();
    }

    @Test
    void authenticatedSubjectRouteNeedsNoReadScope() {
        client.get().uri("/api/subject")
                .headers(h -> h.setBearerAuth(
                        "other-scope-token"))
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.subject").isEqualTo("reader-42");
    }

    @Test
    void undefinedRouteIsDenied() {
        client.get().uri("/api/undefined")
                .headers(h -> h.setBearerAuth("read-token"))
                .exchange()
                .expectStatus().isForbidden();
    }
}
~~~

Nội dung test chứng minh:
- Public route trả 200.
- Protected route thiếu/invalid Bearer → 401, thường có Bearer challenge.
- Valid mock Jwt nhưng thiếu `SCOPE_keys.read` → 403.
- Scope đúng → 200 và controller chỉ trả metadata được phép.
- Một route chỉ đòi authenticated không bắt buộc có keys.read.
- Những routes chưa khai báo bị deny theo `anyExchange().denyAll()`.

**Không** gửi `read-token` hoặc `other-scope-token` vào production: chúng không phải JWT ba phần có chữ ký và chỉ được mock decoder chấp nhận trong test.

## 13. Chạy Gradle, curl và kết quả mong đợi

Trong thư mục project:

~~~bash
gradle test
~~~

Hoặc dùng `./gradlew test` nếu đã tạo Gradle Wrapper. Với test classes ở trên, dự kiến tổng **12 phương thức @Test** (5 ký JWT/JWKS thật + 7 HTTP mocked decoder). Những test này phải được chạy để xác nhận compile và behavior trong môi trường người học; **không có khẳng định đã thực thi Gradle tại đây**.

Chạy app:

~~~bash
gradle bootRun
~~~

Sau đó:

~~~bash
curl -i http://localhost:8080/public/ping
~~~

Kỳ vọng 200 và body `pong`.

~~~bash
curl -i http://localhost:8080/api/key-info
~~~

Kỳ vọng 401 cùng `WWW-Authenticate: Bearer` cho request không token.

~~~bash
curl -i http://localhost:8080/api/key-info \
  -H 'Authorization: Bearer not-a-real-signed-jwt'
~~~

Chuỗi này không phải JWS hợp lệ, do đó phải bị authentication từ chối; **401** thường gặp. Do JWKS config trong `application.yml` trỏ hostname giả, network failure/exception handling cụ thể có thể ảnh hưởng response; hãy xem test JWT ký thật ở phần 11 để kiểm chữ ký không phụ thuộc IdP.

### 13.1. Test với IdP thật trong staging

Khi thay issuer/JWKS bằng nhà cung cấp tin cậy, lấy một access token hợp lệ có `aud=orders-api` và `scope=keys.read` qua grant phù hợp, rồi gọi:

~~~bash
curl -i https://api-staging.example.test/api/key-info \
  -H 'Authorization: Bearer <staging-access-token>'
~~~

Đây là template; không có token thật. Tránh lưu token production trong shell history/log công cộng. JWT hợp lệ và scope đúng → 200; JWT signature/issuer/audience/expiry sai → 401; JWT hợp lệ nhưng thiếu scope → 403.

### 13.2. Test với JWT thật khác test với mockJwt()

| Loại test | Bearer header thực? | RSA/JWS verify thật? | Được kết luận |
| --- | --- | --- | --- |
| `mockJwt()` | Không bắt buộc | Không | Authorization/controller khi đã authenticated |
| `ResourceServerHttpTest` mock decoder | Có | Không | Bearer filter, scope mapping, 401/403/200 |
| `JwksRotationTest` JDK HTTP JWKS | Decode trực tiếp | **Có** | Chữ ký/kid/issuer/aud/expiry và key overlap với fresh decoders |
| Test reuse warm decoder + đổi JWKS | Có tùy test | Có | Cache refresh/stale-key behavior của version cụ thể |
| Staging IdP thật | Có | Có | Network/proxy/TLS/JWKS/CDN/rotation end-to-end |

Một bản test pass không tự chứng minh mọi tầng; đặc biệt **mockJwt() không hề ký JWT hay xác minh kid**.

## 14. Kiểm thử cache stale có phương pháp

Các test trong project sử dụng public keys thay đổi tại JWKS endpoint nhưng **khởi tạo decoder mới** khi cần quan sát một version cố định. Để đo cache:
1. Tạo decoder D, JWKS chỉ A.
2. Decode JWT A để D nạp/có cơ hội cache JWKS A.
3. Publish A+B; đo D có chấp nhận token B không và sau bao lâu.
4. Lặp trong điều kiện network và TTL thực tế, không giả định unknown kid luôn fetch tức thì.
5. Publish B-only; đo D có còn chấp nhận JWT A bao lâu.
6. So sánh với decoder D2 mới từ B-only; D2 sẽ không có A.
7. Thêm 2–3 decoder instances để mô phỏng pods.
8. Mô phỏng JWKS 503/timeout/invalid JSON và unknown-kid bursts có giới hạn.
9. Kiểm HTTP caching ở proxy/CDN nếu có, đo fetch count/latency.
10. Gắn kết quả với chính xác Spring Security/Nimbus version và cấu hình.

**Không dùng Thread.sleep(300) rồi coi đó là SLA của Spring.** Thời gian phụ thuộc schedulers, event loops, cache implementation, HTTP client và network. Test timeout/cache cần có bound đáng tin và policy sản phẩm, không suy luận từ một run local.

### 14.1. Vì sao cache hit sai có thể là vấn đề lớn?

Nếu cache còn public key A sau khi issuer đã xóa A, một JWT A có chữ ký hợp lệ và claims còn hạn **có thể** tiếp tục được xác minh ở một instance cho đến khi cache đổi. Đó là lý do emergency compromise không thể chỉ dựa trên một HTTP response JWKS mới.

Ngược lại, khi cache mới chưa chứa B, token B có thể bị 401 ngay cả khi issuer mới ký đúng. Prepublish B và chờ propagation làm giảm cửa sổ này.

## 15. Triệu chứng và nguyên nhân khi key rotation

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Token B bị 401 ngay sau switch | Public B chưa tới cached JWKS | Publish B sớm, đo propagation |
| Token A còn exp nhưng 401 khi B hoạt động | Gỡ A quá sớm | Overlap tới khi token A hết hạn |
| Chỉ một pod/region 401 | Local cache/edge bất đồng bộ | Kiểm key set từng instance |
| Có kid trong JWKS nhưng signature sai | Wrong private key hoặc token bị sửa | Kiểm signer và JOSE signature |
| Cùng kid nhưng key bytes khác | Kid reused/collision | Mỗi key version một kid riêng |
| Mọi token đều 401 sau deploy | issuer/audience/alg/JWKS URL sai | Kiểm trust configuration |
| Token verified nhưng API trả 403 | Scope/role/tenant không đủ | Kiểm authorization, không đổ lỗi JWKS |
| JWKS endpoint trả 5xx | IdP/network outage | Resilience, không bypass verification |
| JWKS endpoint trả khóa private | Key disclosure | Incident response/rotate ngay |
| Issuer A có kid=default, issuer B cũng vậy | Multi-tenant key collision nếu cache chung | Partition theo trusted issuer |
| Tăng 401 + fetch JWKS rất nhiều | Unknown kid flooding hoặc cache miss | Rate limits, refresh bounds |
| Chỉ sau restart mới nhận B | Decoder/cache không refresh như dự kiến | Kiểm TTL/library/cache config |
| Token dùng alg ES256, decoder chỉ RS256 | Algorithm policy mismatch | Review rồi cấu hình trusted alg |
| API nhận ID token vì cùng issuer/JWKS | Audience/token-type confusion | Validate aud/typ/scope |

Không chữa các lỗi này bằng `alg=none`, tắt issuer/audience validation hoặc chấp nhận mọi public key do request chỉ định.

## 16. Monitoring và runbook vận hành

Metrics hữu ích:
- Tỷ lệ 401 theo route, instance, region và thời điểm switch signer.
- JWT validation failures phân loại “unknown key”, “signature”, “issuer”, “audience”, “expiry” ở mức **không lộ secrets** và theo khả năng instrumentation của thư viện.
- JWKS fetch success/errors/timeouts/latency.
- Key-set version hoặc danh sách trusted kid đã được kiểm soát; không dùng kid của attacker làm nhãn metric không giới hạn.
- Cache refresh count/age khi JWK source có thể expose.
- Canary A/B token validation ở những môi trường được phép.
- IdP key rotation events và timeline publishing/signing/removal.

Các bước on-call khi JWT B 401:
1. Xác định B token được ký lúc nào và `kid` là gì.
2. Xác minh JWKS URL tin cậy ở origin đã có B hay chưa.
3. Kiểm CDN/edge/proxy có còn JWKS A-only không.
4. Kiểm cấu hình issuer, audience, allowed algorithm trên resource server.
5. Kiểm từng pod/region, không chỉ load-balancer tổng.
6. Dùng token test hợp lệ, không log raw JWT.
7. Nếu chỉ B chưa được phân phối, cân nhắc trì hoãn switch signing theo runbook.
8. Nếu A bị compromised, áp emergency procedure — không mở lại A đơn thuần để tránh 401.
9. Xem lại TTL, propagation, rollback và key publication pipeline.

### 16.1. Log an toàn

Chỉ log route template, status, correlation ID, loại validation failure, latency hoặc key-version đã chuẩn hóa. Không log `Authorization` header, JWT raw, signing keys, private JWK, entire claims chứa PII hoặc token trong URL. JWT header/kid đến từ dữ liệu chưa tin cậy, nên cần kiểm cardinality trước khi đưa vào labels/log indexes.

## 17. Multi-issuer và key trust boundary

Trong một hệ thống nhiều issuers:
- Issuer A và B có thể cùng dùng `kid="key-1"` nhưng public key khác.
- Global map theo **chỉ kid** là sai mô hình.
- Trust cần tách theo issuer/JWKS nguồn được phê duyệt và audience/resource policy.
- Claims `iss` từ payload chưa verify chỉ có thể là **gợi ý phân tuyến tới allowlist**, không phải URL arbitrary để tải JWKS.
- Nếu dùng `JwtIssuerReactiveAuthenticationManagerResolver`, chỉ cho trusted issuers, không chấp nhận issuer động từ Internet.
- Sau signature verification vẫn phải kiểm tenant/ownership và API scopes.

Mô hình:

~~~text
trusted issuer A -> decoder A -> JWKS A -> allowed API audiences -> tenant A policy
trusted issuer B -> decoder B -> JWKS B -> allowed API audiences -> tenant B policy
unrecognized issuer -> reject
~~~

Token substitution risk: cùng issuer có thể phát ID tokens cho client khác và access tokens cho APIs khác. **Cùng chữ ký/kid không có nghĩa cùng mục đích**. Xác minh `aud`, access-token profile (RFC 9068 khi áp dụng) và role/permission policy.

## 18. Checklist trước production

### JWK/JWKS
- [ ] Public JWKS **không** chứa private RSA parameters hoặc symmetric secret `k`.
- [ ] Signing private keys thuộc IdP/KMS/HSM, không phát tới API.
- [ ] Kid distinct per key material, tránh reuse/collision trong một issuer.
- [ ] JWK `kty`, `use/key_ops`, `alg` phù hợp signing verification.
- [ ] JWKS URL/issuer cố định hoặc allowlisted, HTTPS/TLS an toàn.
- [ ] Không dùng arbitrary `jku`/`x5u` hay kid file/SQL lookup không an toàn.
- [ ] Không chọn key bằng thứ tự array `keys[0]`.
- [ ] Không bỏ signature verification vì lỗi cache.

### Caching và rotation
- [ ] Đã biết version Spring Security/Nimbus và JWK cache thật.
- [ ] Cache TTL, unknown-kid behavior, timeouts và CDN được kiểm thử.
- [ ] Public B được prepublish trước khi issuer chuyển signing sang B.
- [ ] Giữ A+B khi token A chưa hết hạn.
- [ ] Có công thức max TTL + skew + margin để gỡ A.
- [ ] Monitoring canary A/B, JWKS fetch và 401 theo pod/region.
- [ ] Có kế hoạch rollback controlled cho planned rotation.
- [ ] Có **khẩn cấp** key-compromise runbook khác planned rotation.
- [ ] Có cách xử lý stale caches khi A bị compromise.
- [ ] Multi-issuer cache được partition theo trust source.

### Spring Reactive security
- [ ] Đúng `ServerHttpSecurity`/`SecurityWebFilterChain`/`ReactiveJwtDecoder`.
- [ ] JWT iss, aud, exp/nbf và allowed algorithms được validate.
- [ ] Không dùng ID token làm Bearer access token.
- [ ] SCOPE_/role mapping và object/tenant authorization được kiểm tra riêng.
- [ ] CSRF chỉ disable khi Bearer-only không có ambient browser credentials theo threat model.
- [ ] CORS preflight không bị authentication bắt sai trong SPA.
- [ ] Không log raw JWT, private keys hoặc credential metadata nhạy cảm.
- [ ] Không dùng block() trong reactive authentication path.

### Kiểm thử
- [ ] Signed JWT RSA A thành công với public JWK A.
- [ ] JWKS A+B chấp nhận JWT ký A và B.
- [ ] Decoder mới từ JWKS B-only từ chối JWT A.
- [ ] JWT sai iss/aud/exp thất bại dù signature hợp lệ.
- [ ] Kid A + private B không vượt signature check.
- [ ] HTTP Bearer thiếu token 401; thiếu scope 403; scope đủ 200.
- [ ] Warm-cache behavior được test riêng, không suy ra từ fresh decoder.
- [ ] Unknown kid flooding/JWKS outage có giới hạn.
- [ ] Multi-instance/region canary và emergency rotation đã thử diễn tập.

## 19. Câu hỏi tự kiểm tra

**1. JWK và JWKS khác nhau thế nào?**

> JWK mô tả một khóa, JWKS chứa một tập khóa theo định dạng JSON `keys`.

**2. Kid có phải secret không?**

> Không. Nó là identifier để tìm public key ứng viên; signature và claims vẫn phải verify.

**3. RSA public JWK có n/e để làm gì?**

> Tạo RSA public verification key; không cần private signing exponent để verify.

**4. Có được đưa RSA private `d` lên JWKS endpoint không?**

> Không. Đó là tiết lộ khóa ký và có thể cho phép phát JWT giả.

**5. Tại sao có giai đoạn JWKS A+B?**

> Để token A cũ và token B mới cùng xác minh được trong quá trình rollout.

**6. Tại sao phải publish B trước khi signer dùng B?**

> Các Resource Servers và caches cần biết public B; nếu chưa có, token B có thể bị 401.

**7. Khi nào gỡ A trong planned rotation?**

> Sau thời gian token A cuối cùng có thể còn hợp lệ cộng clock skew và safety margin theo thiết kế.

**8. Nếu private A bị lộ, có nên chờ hết token A?**

> Không mặc nhiên; thường cần emergency revocation nhanh, chấp nhận việc token thật bị từ chối.

**9. JWT exp có đồng nghĩa JWKS cache TTL không?**

> Không. Một cái là thời hạn token, một cái là freshness của public keys.

**10. Vì sao không dùng `NimbusJwtDecoder.cache(...)` của Servlet trong Reactive?**

> Hai builder khác nhau; phải tham khảo `NimbusReactiveJwtDecoder` API/version đang dùng.

**11. Nếu JWT có kid hợp lệ nhưng ký bởi private key khác?**

> Signature verification thất bại; kid không thay chữ ký.

**12. JWKS của hai issuers có thể trùng kid không?**

> Có; không được trộn key stores chỉ theo kid, phải giữ trust boundary theo issuer.

**13. HTTP JWKS endpoint có luôn phải trả max-age 300 không?**

> Không. Đây là ví dụ; TTL cần phù hợp SLA rotation/cache và thư viện.

**14. Tại sao mockJwt() không chứng minh key rotation an toàn?**

> Mock bypass RSA verification và JWKS lookup; phải dùng JWT ký thật và decoder thật.

**15. Nếu B token 401 chỉ ở một số pods, xem gì trước?**

> Local cache, JWKS CDN/edge propagation, trusted issuer/JWKS config, algorithms, network.

**16. Key rotation có tự cấp token mới cho client không?**

> Không. Resource Server chỉ xác minh; Authorization Server và OAuth Client quản lý token issuance/refresh.

## 20. Tổng kết và tài liệu chính thức

Với **Spring Security Reactive Resource Server JWT**, một JWT hợp lệ không chỉ có header `kid` đúng. Resource Server phải tải **public keys từ JWKS đáng tin**, chọn ứng viên theo key/algorithm policy, xác minh chữ ký và kiểm `iss`, `aud`, `exp`/`nbf`, sau đó mới thực thi scopes/roles/tenant/ownership.

Quy trình rollover bình thường:

~~~text
Generate private/public B
    -> Publish public A+B
    -> Allow time for JWKS caches and regions to observe B
    -> Switch signer A to B
    -> Keep A+B until last A token can no longer be accepted
    -> Remove public A, retire private A and monitor
~~~

Khi key bị compromise, cần kế hoạch khẩn cấp để loại trust với A sớm, kể cả phải làm một số JWT cũ bị 401. Không lấy TTL của Servlet cache làm cam kết cho Reactive, không coi một fresh-decoder test là bằng chứng warm cache đã refresh; luôn đo ở dependency version/hạ tầng thật.

### Tài liệu tham khảo chính thức

- Spring Security 6.5 — OAuth2 Resource Server JWT (Reactive): https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/resource-server/jwt.html
- Spring Security 6.5 — Reactive Bearer Tokens: https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/resource-server/bearer-tokens.html
- Spring Security 6.5 — WebFlux OAuth2 Testing: https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/oauth2.html
- Spring Security Javadoc — NimbusReactiveJwtDecoder: https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/oauth2/jwt/NimbusReactiveJwtDecoder.html
- Spring Security Javadoc — JwkSetUriReactiveJwtDecoderBuilder: https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/oauth2/jwt/NimbusReactiveJwtDecoder.JwkSetUriReactiveJwtDecoderBuilder.html
- Spring Boot 3.5 — Spring Security: https://docs.spring.io/spring-boot/3.5/reference/web/spring-security.html
- RFC 7517 — JSON Web Key: https://www.rfc-editor.org/rfc/rfc7517
- RFC 7515 — JSON Web Signature: https://www.rfc-editor.org/rfc/rfc7515
- RFC 7519 — JSON Web Token: https://www.rfc-editor.org/rfc/rfc7519
- RFC 8725 — JWT Best Current Practices: https://www.rfc-editor.org/rfc/rfc8725
- RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens: https://www.rfc-editor.org/rfc/rfc9068
- RFC 6750 — OAuth 2.0 Bearer Token Usage: https://www.rfc-editor.org/rfc/rfc6750