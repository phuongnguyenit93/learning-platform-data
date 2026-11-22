# 11.12. Cache khóa, key rotation và xử lý lỗi tải JWKS

## 1. Bối cảnh: ID Token phải được xác minh bằng khóa đáng tin cậy

Khi một ứng dụng **Spring Security OAuth 2.0/OIDC Client** dùng `oauth2Login()` để đăng nhập qua OpenID Connect Provider (OP), ứng dụng có thể nhận **ID Token** từ Token Endpoint sau khi đổi authorization code. ID Token thường là một JWT có chữ ký số; client cần xác minh token trước khi coi đó là thông tin xác thực đáng tin cậy.

Đối với ID Token được ký bằng thuật toán **bất đối xứng** như `RS256` hoặc `ES256`:

- **Provider giữ private key** để ký ID Token.
- **OAuth2/OIDC Client tải public key** tương ứng do provider công bố qua **JSON Web Key Set (JWKS)**.
- Client chọn khóa xác minh phù hợp với chữ ký token, kiểm tra chữ ký, sau đó kiểm tra các claim OIDC như `iss`, `aud`, `exp`, `iat`, `nonce` (khi đã sử dụng), cùng những ràng buộc khác khi áp dụng.
- Vì provider thay đổi khóa theo thời gian (*key rotation*), client cần một chiến lược **cache, làm mới và xử lý lỗi tải JWKS** để vừa bảo mật vừa duy trì khả năng đăng nhập.

**Không phải mọi ID Token đều phải dùng JWKS.** Với trường hợp provider và client thỏa thuận thuật toán đối xứng như `HS256`, việc xác minh liên quan khóa bí mật phù hợp chứ không dựa trên public JWKS kiểu RSA/EC. Bài này tập trung vào kịch bản OIDC thông dụng: **ID Token có chữ ký bất đối xứng và client truy xuất JWKS**.

**Mục tiêu học tập:** hiểu cách client xác định JWKS URI, chọn khóa bằng `kid`, vận hành cache khi provider đổi khóa, phân biệt lỗi mạng với lỗi chữ ký, triển khai xoay khóa có khoảng chồng lấn và xử lý sự cố mà không chấp nhận token chưa được xác minh.

## 2. Phân biệt JWKS, JWK, JWS, JWT và `kid`

Một hệ thống OIDC có thể sử dụng các khái niệm sau:

| Thuật ngữ | Vai trò | Ví dụ |
| --- | --- | --- |
| **JWT** (*JSON Web Token*) | Cấu trúc token chứa header/claims và phần ký hoặc mã hóa tùy profile | ID Token của OIDC |
| **JWS** (*JSON Web Signature*) | Cơ chế biểu diễn thông điệp có chữ ký | JWT ký bằng `RS256` hoặc `ES256` |
| **JWK** (*JSON Web Key*) | Cách biểu diễn một khóa bằng JSON | Public RSA key gồm `kty`, `n`, `e` |
| **JWKS** (*JSON Web Key Set*) | Tập nhiều JWK, thường công bố tại một HTTP endpoint | `{"keys":[...]}` |
| **`kid`** (*Key ID*) | Nhãn nhận diện khóa trong JWS header/JWK để tìm ứng viên xác minh | `"login-signing-2026-11"` |
| **`alg`** | Thuật toán mà JWS yêu cầu để xác minh chữ ký | `RS256` |
| **`use`** / **`key_ops`** | Mục đích sử dụng khóa nếu được khai báo | `sig` / `verify` |
| **`jwks_uri`** | Địa chỉ HTTPS của JWKS được công bố trong provider metadata | `https://login.example.com/keys` |

Ví dụ header của một ID Token đã ký:

~~~json
{
  "alg": "RS256",
  "kid": "login-signing-2026-11",
  "typ": "JWT"
}
~~~

Header chỉ là dữ liệu được gửi **cùng token**. Nó **không phải bằng chứng** rằng provider đã ký token bằng một khóa đáng tin. Client cần sử dụng thuật toán được cho phép và khóa đã được lấy từ **nguồn tin cậy gắn với đúng provider**, rồi thực hiện xác minh chữ ký.

Ví dụ JWKS với hai public RSA keys, rút gọn phần giá trị khóa cho dễ đọc:

~~~json
{
  "keys": [
    {
      "kty": "RSA",
      "use": "sig",
      "kid": "login-signing-2026-10",
      "alg": "RS256",
      "n": "<base64url-modulus-old>",
      "e": "AQAB"
    },
    {
      "kty": "RSA",
      "use": "sig",
      "kid": "login-signing-2026-11",
      "alg": "RS256",
      "n": "<base64url-modulus-new>",
      "e": "AQAB"
    }
  ]
}
~~~

`n`/`e` là thành phần **public** của RSA key; giá trị rút gọn ở đây không phải key hợp lệ để chạy xác minh. Với EC keys có thể thấy `crv`, `x` và `y`. JWKS public dành cho xác minh **không được công bố private key material**, ví dụ RSA `d`/`p`/`q` hoặc private EC `d`.

### 2.1. `kid` giúp chọn khóa, không xác nhận token hợp lệ

Quy trình logic thường là:

1. Đọc JWS header theo cách an toàn để lấy `kid` và `alg`.
2. Tra danh sách public keys được tin cậy của **issuer tương ứng**.
3. Chọn khóa ứng viên phù hợp `kid`, key type, algorithm và mục đích sử dụng.
4. Xác minh chữ ký trên **đúng byte dữ liệu JWS**.
5. Nếu chữ ký hợp lệ, tiếp tục kiểm tra **claims OIDC**.

**Chỉ trùng `kid` không có nghĩa token hợp lệ.** Tương tự, JWT có thể được decode thành JSON mà không có bất kỳ chữ ký hợp lệ nào; việc đọc payload không thay thế xác minh.

`kid` không phải tên duy nhất trên toàn Internet. Hai issuer khác nhau có thể dùng cùng `kid`. Cache key và trust boundary nên bao gồm **issuer/nguồn JWKS đáng tin** và thuộc tính cần thiết, không gom tất cả nhà cung cấp vào một bản đồ toàn cục chỉ theo `kid`.

### 2.2. Không tin URL hoặc thuật toán do token tự đề xuất

Khi token có header `jku`, `x5u` hoặc một URL khóa khác, **không tự động tải từ URL do token cung cấp** nếu URL đó chưa được chính sách client cho phép và ràng buộc với provider đáng tin. Nếu làm vậy, kẻ tấn công có thể gửi một JWKS endpoint của chính họ và ký token bằng khóa riêng.

Cũng không chấp nhận `alg=none` hoặc tự đổi từ thuật toán bất đối xứng sang thuật toán đối xứng theo token. Chính sách algorithm cần đến từ cấu hình đáng tin và khả năng hỗ trợ của IdP, không từ quyết định của dữ liệu chưa được xác minh.

## 3. Làm sao Spring Security biết tải JWKS ở đâu?

Trong OIDC, **issuer** là định danh chuẩn của provider, ví dụ:

~~~text
https://login.example.com
~~~

Provider có thể công bố metadata tại địa chỉ discovery tương ứng, ví dụ issuer dạng root:

~~~text
https://login.example.com/.well-known/openid-configuration
~~~

Một phần metadata minh họa:

~~~json
{
  "issuer": "https://login.example.com",
  "authorization_endpoint": "https://login.example.com/oauth2/authorize",
  "token_endpoint": "https://login.example.com/oauth2/token",
  "jwks_uri": "https://login.example.com/oauth2/keys",
  "id_token_signing_alg_values_supported": ["RS256", "ES256"]
}
~~~

Trong ứng dụng Spring Boot, đăng ký OIDC Client thường dùng `issuer-uri`:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          corporate:
            provider: company-oidc
            client-id: ${CORPORATE_CLIENT_ID}
            client-secret: ${CORPORATE_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - email
        provider:
          company-oidc:
            issuer-uri: https://login.example.com
~~~

Khi provider hỗ trợ discovery, Spring Security/Spring Boot có thể lấy metadata để dựng `ClientRegistration`, từ đó xác định `jwks_uri`. Các endpoint và issuer phải phù hợp với metadata/đăng ký chính thức của provider. Với issuer có path hoặc realm, vị trí discovery cụ thể phụ thuộc quy tắc metadata chuẩn và provider; đừng tự đoán bằng cách nối chuỗi rồi lấy đó làm sự thật.

**Ba tầng cần phân biệt rõ:**

1. **Metadata discovery:** lấy tài liệu mô tả provider, thường diễn ra khi xây dựng client registration/khởi động ứng dụng và có thể gây lỗi khởi động nếu IdP không truy cập được.
2. **JWKS retrieval:** lấy danh sách public keys để xác minh chữ ký; có thể diễn ra khi tạo decoder hoặc khi gặp token cần xác minh, tùy implementation.
3. **ID Token validation:** chọn khóa phù hợp, xác minh chữ ký và các claim của ID Token **trong mỗi lần ID Token được kiểm tra**, dù public key có thể đang ở cache.

Khi sử dụng `oauth2Login()` trong Spring Security, framework có thành phần chuyên trách **OIDC ID Token decoder** (ví dụ cơ chế xây dựng decoder theo `ClientRegistration` như `OidcIdTokenDecoderFactory` trong các phiên bản có API này). **Đừng đồng nhất nó với bean `JwtDecoder` chỉ dùng cho Resource Server**. Tùy biến cache của Resource Server không đương nhiên thay đổi cách OAuth2 Login xác minh ID Token.

## 4. Luồng tải, chọn và cache public key

~~~mermaid
sequenceDiagram
    autonumber
    participant B as Browser
    participant C as Spring Security OIDC Client
    participant Cache as JWKS / Key cache
    participant P as OIDC Provider

    B->>C: Callback authorization code + state
    C->>P: POST Token Endpoint (code + PKCE nếu dùng)
    P-->>C: Token Response gồm ID Token (JWS, kid=K2)
    C->>Cache: Tìm public key của issuer và kid=K2
    alt Cache có key phù hợp, còn dùng được
        Cache-->>C: Public key K2
    else Chưa có key phù hợp / cần làm mới
        C->>P: GET jwks_uri qua HTTPS
        P-->>C: JWKS chứa public keys K1, K2
        C->>Cache: Cập nhật tập khóa theo chính sách
        Cache-->>C: Public key K2
    end
    C->>C: Xác minh chữ ký và claims OIDC
    C-->>B: Hoàn tất login hoặc từ chối
~~~

**Cache ở đây cache các khóa xác minh công khai**, không phải cache kết quả “token đã hợp lệ” dùng cho mọi người dùng. Mỗi ID Token vẫn phải được kiểm tra chữ ký và các claim thích hợp.

### 4.1. Tại sao cần cache?

Nếu backend tải JWKS cho **mọi lần đăng nhập**, nó tạo nhiều request tới IdP, tăng độ trễ và khiến chức năng login phụ thuộc tuyệt đối vào tính sẵn sàng của JWKS endpoint ở mọi request. Cache phù hợp đem lại:

- Ít request mạng hơn khi các token cùng sử dụng một bộ khóa.
- Đăng nhập nhanh hơn khi public key đã có trong cache.
- Giảm nguy cơ quá tải JWKS endpoint khi nhiều instance/traffic tăng đột biến.
- Khả năng tiếp tục xác minh token bằng khóa đã tin cậy trong một **khoảng thời gian chính sách cho phép**, khi JWKS endpoint tạm thời mất kết nối.

Lợi ích về khả dụng phải luôn được cân bằng với tính mới của khóa: **cache quá lâu có thể bỏ lỡ khóa mới hoặc việc rút bỏ khóa cũ**.

### 4.2. Cache JWKS khác cache một key

Một implementation có thể lưu nguyên **JWKS document**, hoặc lưu các key đã phân tích. Đây là hai cách biểu diễn của cùng nguồn dữ liệu; logic chọn key vẫn phải dựa vào issuer và các điều kiện phù hợp.

| Loại cache | Lợi ích | Lưu ý |
| --- | --- | --- |
| Cache JWKS theo issuer/JWKS URI tin cậy | Có toàn bộ key set để giải quyết các `kid` | Phải refresh khi key set thay đổi |
| Cache key đã chọn theo issuer + `kid` + thuật toán/chính sách | Tra nhanh khi có nhiều token | Cần cập nhật/loại bỏ key khi JWKS thay đổi |
| Cache HTTP (ETag, Cache-Control) | Giảm băng thông, hỗ trợ revalidation | Có thể bị giới hạn bởi HTTP client/phiên bản thư viện |
| Cache kết quả discovery | Không phải tải metadata liên tục | **Không** chứng minh JWKS key vẫn mới |
| Cache DNS | Giảm tra cứu DNS | Không thay thế JWKS cache hoặc kiểm tra TLS |

Trong dự án sử dụng Spring Security, một phần việc cache có thể do **Nimbus JOSE + JWT** và các thành phần HTTP client bên dưới đảm nhiệm. **Không khẳng định một TTL cố định hoặc quy tắc “unknown kid luôn tự reload” cho mọi phiên bản Spring Security/Nimbus**; behavior cần được xác định theo dependency và cấu hình được triển khai.

## 5. Chiến lược cache hợp lý: freshness, TTL và refresh

Có ba thời điểm cần phân biệt:

| Mốc | Ý nghĩa |
| --- | --- |
| **Fetched at** | Thời điểm cache lấy JWKS thành công |
| **Fresh-until** | Khoảng thời gian có thể ưu tiên dùng cache trước khi revalidate, theo chính sách |
| **Hard expiry / maximum staleness** | Giới hạn không được dùng bản cache cũ nữa, nếu tổ chức cho phép sử dụng stale cache có kiểm soát |

Không phải API cache của mọi thư viện đều triển khai đủ ba mốc. Đây là mô hình thiết kế để hiểu cách cân bằng **availability** và **rotation/revocation**.

### 5.1. Cache hit

ID Token dùng `kid=K1`, public key K1 đang trong tập khóa được tin cậy và cache còn đáp ứng chính sách. Decoder sử dụng key đó để **xác minh chữ ký** và kiểm tra claims. Không cần tải JWKS mới chỉ vì có một token mới mang cùng `kid`.

### 5.2. Cache miss vì `kid` mới

Provider bắt đầu ký bằng K2 nhưng cache hiện chỉ có K1. Client có thể thực hiện **làm mới JWKS có giới hạn** để tìm K2.

Mẫu logic:

~~~text
ID Token nhận được: issuer=company, alg=RS256, kid=K2

1. Chọn đúng nguồn JWKS đã cấu hình cho company issuer.
2. Tìm khóa K2 phù hợp thuật toán/mục đích trong cache.
3. Nếu không tìm thấy:
   - Chỉ trigger refresh theo rate-limit / single-flight policy.
   - Lấy JWKS qua TLS từ URL đã được tin cậy.
   - Phân tích và thay thế/cập nhật key set theo chính sách.
   - Tìm lại K2.
4. Nếu vẫn không có K2 -> từ chối ID Token.
5. Nếu tìm được K2 -> xác minh chữ ký + validate OIDC claims.
6. Nếu chữ ký hoặc claim sai -> từ chối.
~~~

Đây là **thuật toán minh họa**, không phải mô tả chính xác thứ tự refresh bắt buộc của mọi phiên bản thư viện. Một cache cụ thể có thể quyết định refresh dựa trên TTL, key miss, HTTP cache validator hoặc callback riêng.

### 5.3. Cache expired theo TTL

Nếu cache đã quá tuổi thọ được phép, decoder cần làm mới trước khi dựa vào khóa theo chính sách đang sử dụng. Khi JWKS endpoint lỗi, lựa chọn **từ chối** hoặc **sử dụng last-known-good key trong giới hạn** phải được quyết định dựa trên mô hình rủi ro. Không nên tự động dùng khóa đã hết hạn vô thời hạn.

Ví dụ giả định:

~~~text
T0   tải JWKS (K1)
T0+5m   cache đến điểm revalidate
T0+6m   JWKS endpoint lỗi tạm thời
T0+7m   một ID Token kid=K1 xuất hiện

Nếu policy không cho phép stale:
    từ chối do không thể lấy khóa xác minh hợp lệ theo policy

Nếu policy cho phép stale có giới hạn:
    chỉ xem xét public key K1 đã từng tin cậy,
    vẫn bắt buộc xác minh chữ ký/issuer/audience/time/nonce,
    áp dụng hard-expiry và giám sát sự cố
~~~

Dùng stale key là quyết định **có đánh đổi bảo mật**: nếu provider vừa thu hồi K1 vì lộ private key, một client giữ K1 trong cache có thể tiếp tục tin vào chữ ký từ khóa bị xâm phạm. Với sự cố compromise hoặc chính sách không cho phép stale, cần **fail closed**.

### 5.4. Điều gì xảy ra với ETag và HTTP Cache-Control?

JWKS endpoint có thể trả:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: public, max-age=300
ETag: "jwks-v42"
~~~

Trong lần revalidate sau, HTTP client có thể gửi `If-None-Match`; nếu response `304 Not Modified` hợp lệ, client dùng lại dữ liệu cache theo semantics HTTP tương ứng.

Tuy nhiên, **không giả định mọi lớp JWKS decoder tự sử dụng ETag, Cache-Control hay 304 theo cùng cách**. Một số cache đặt TTL nội bộ; một số HTTP client được cấu hình riêng; một số triển khai không giữ HTTP response headers. Khi cần điều khiển chi tiết, xác định chính xác API cache và HTTP transport đang dùng trong phiên bản Spring Security/Nimbus.

### 5.5. Chống “thundering herd” và negative-cache không an toàn

Nếu nhiều request cùng gặp `kid` lạ trong lúc key rotation, hàng trăm pod có thể đồng loạt tải JWKS.

Những biện pháp có thể dùng:

- **Single-flight** trong một process: tại một thời điểm chỉ một lượt refresh JWKS cho cùng nguồn, các request khác chờ kết quả với timeout.
- **Rate limit/cooldown** cho refresh do unknown `kid` gây ra.
- **Timeout, bounded retry và backoff có jitter** khi JWKS endpoint lỗi.
- **Không cache negative miss quá lâu**: nếu cache “K2 không tồn tại” quá dài, rollout khóa mới có thể gây lỗi đăng nhập kéo dài dù provider đã cập nhật JWKS.
- **Không để `kid` do attacker đặt tùy ý** kích hoạt unlimited network fetch.

Giới hạn refresh nhằm chống DoS, nhưng **không được biến cache miss thành chấp nhận token chưa xác minh**.

## 6. Key rotation có kế hoạch: khoảng chồng lấn giữa khóa cũ và khóa mới

Provider thường cần xoay khóa định kỳ để giảm rủi ro và tuân thủ chính sách. Nếu provider ngừng công bố K1 ngay khi bắt đầu ký bằng K2, client đang cache K1 hoặc cần xác minh ID Token cũ có thể bị lỗi.

Mô hình rotation có kế hoạch với hai khóa:

~~~mermaid
flowchart LR
    A["Giai đoạn 1\nJWKS: K1\nKý ID Token: K1"] --> B["Giai đoạn 2\nJWKS: K1 + K2\nKý ID Token: K1"]
    B --> C["Giai đoạn 3\nJWKS: K1 + K2\nKý ID Token: K2"]
    C --> D["Giai đoạn 4\nJWKS: K2\nKý ID Token: K2"]
~~~

### 6.1. Trình tự khuyến nghị

1. **Chuẩn bị key pair mới K2** trong hệ thống quản lý khóa của provider. Private key không được công khai qua JWKS.
2. **Publish public key K2 vào JWKS** trong khi provider vẫn ký ID Token bằng K1. Điều này giúp client làm quen với K2 trước khi sử dụng.
3. **Chờ thời gian lan truyền phù hợp** theo JWKS cache TTL, CDN/proxy cache, khả năng refresh của các client và độ trễ mạng. Không giả định tất cả client cùng refresh ngay.
4. **Chuyển signing key sang K2.** ID Token mới có header `kid=K2` và chữ ký tạo bằng private K2.
5. **Tiếp tục công bố K1** đủ lâu để các ID Token đã ký bằng K1 còn hợp lệ được xác minh, có xét thời hạn token và clock skew được cho phép, cũng như đặc điểm hệ thống.
6. **Loại K1 khỏi JWKS** khi đã qua cửa sổ chuyển tiếp và không còn lý do tin cậy khóa cũ. Nếu đã được đánh dấu compromise, không chờ cửa sổ thông thường.
7. **Giám sát** lỗi unknown kid, signature verification, số lần refresh JWKS, HTTP error và tỷ lệ login thất bại trước/trong/sau rotation.

Ví dụ minh họa:

| Thời điểm | JWKS provider công bố | Khóa dùng ký token mới | Điều client phải làm |
| --- | --- | --- | --- |
| 09:00 | K1 | K1 | Dùng/cache K1 |
| 09:10 | K1, K2 | K1 | Khi refresh, có thể nhận cả hai khóa |
| 09:30 | K1, K2 | K2 | Nhận token K2; cache miss có thể refresh để tìm K2 |
| 10:30 | K1, K2 | K2 | Vẫn xác minh được token cũ K1 còn trong thời hạn |
| Sau cửa sổ chuyển tiếp | K2 | K2 | Khi JWKS refresh, ngừng tin cậy K1 theo chính sách |

Các thời điểm trên chỉ là **tình huống minh họa**, không hàm ý TTL bắt buộc hoặc thời gian chờ chung của OIDC.

### 6.2. Bao lâu mới gỡ K1?

Không có một con số áp dụng cho mọi hệ thống. Provider cần xét:

- Thời gian còn hiệu lực tối đa của **ID Token đã ký bằng K1**.
- Clock skew mà các client cho phép.
- Cache TTL/hard expiry của client, proxy, CDN hoặc JWKS retrieval library.
- Thời gian rollout nhiều region/instance.
- Những dịch vụ khác cũng xác minh chữ ký bằng cùng tập khóa.
- Khả năng rollback từ K2 về K1 nếu phát sinh sự cố.

Điều quan trọng là gỡ K1 **chỉ khi hợp lệ về mặt chính sách và không còn token cũ cần được chấp nhận**, trừ trường hợp khóa bị compromise và phải ngừng tin ngay.

### 6.3. Dùng `kid` mới khi tạo khóa mới

Nên cấp **Key ID mới và ổn định cho từng signing key**; tránh dùng lại cùng một `kid` cho khóa có public material khác. Nếu provider công bố K2 nhưng vẫn gắn nhãn `kid=K1`, client có thể chọn nhầm cache key cũ và thất bại xác minh hoặc gặp hành vi khó đoán.

Với trường hợp cùng một JWKS có nhiều keys dùng chung `kid` hoặc không có `kid`, cách lựa chọn ứng viên tùy vào library và thuật toán. Một provider chủ động quản trị key rotation nên đưa ra cấu hình rõ ràng, giúp client chọn khóa một cách xác định.

## 7. Rotation khẩn cấp vì khóa bị lộ khác rotation định kỳ

**Key compromise** là tình huống provider nghi ngờ private signing key đã bị lộ, bị sử dụng trái phép hoặc mất khả năng đảm bảo bí mật. Khi đó cách vận hành khác rotation có kế hoạch.

Với compromised K1:

1. Provider **ngừng ký bằng K1 ngay** theo kế hoạch ứng cứu.
2. Sinh/kích hoạt K2 từ nguồn khóa an toàn và công bố public K2.
3. **Gỡ K1 khỏi nguồn tin cậy** theo quy trình thu hồi khẩn cấp, thay vì giữ K1 chỉ để bảo đảm ID Token cũ vẫn đăng nhập được.
4. Phối hợp với client để **làm mới/evict JWKS cache có chứa K1**; nếu không, các client dùng stale cache có thể tiếp tục chấp nhận chữ ký của K1.
5. Đánh giá việc **thu hồi/đóng phiên đăng nhập** đã hình thành trước đó và các credential/token liên quan theo phạm vi ảnh hưởng.
6. Giám sát đăng nhập bất thường, lỗi chữ ký và thời gian propagation của việc thu hồi.

Một điểm cần hiểu: Trong ứng dụng Spring Security web dùng session, **ID Token thường được xác minh khi login**, sau đó ứng dụng có thể dựa vào **session cookie** trong những request tiếp theo. Việc xóa K1 khỏi JWKS **không tự động làm mọi session đã đăng nhập trước đó bị xóa**. Nếu private key bị lộ, tổ chức có thể cần chính sách thu hồi phiên/reauthentication, xử lý token và sự kiện sự cố riêng.

**Không dùng stale JWKS vô hạn để duy trì login trong sự cố lộ khóa.** Khả dụng không được đánh đổi bằng việc tiếp tục tin khóa đã biết là không an toàn.

## 8. Spring Security OAuth2 Login: cấu hình cơ bản và trách nhiệm của decoder

### 8.1. Dependency ứng dụng Servlet

Ví dụ Spring Boot Servlet:

~~~gradle
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
}
~~~

Cấu hình bảo mật:

~~~java
@Configuration
class OidcLoginSecurity {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/assets/**").permitAll()
                .anyRequest().authenticated()
            )
            .oauth2Login(Customizer.withDefaults());

        return http.build();
    }
}
~~~

Các class/annotation sử dụng `import` từ Spring Security và Spring Framework tương ứng; đoạn ví dụ lược bớt phần `import`.

Cùng với `spring.security.oauth2.client.registration.corporate` và provider `issuer-uri` đã khai báo ở phần 3, Spring Security đảm nhiệm luồng OAuth2 Login và OIDC ID Token validation theo khả năng của phiên bản được sử dụng.

**Điều không nên làm:** tự parse ID Token từ HTTP response rồi dùng `Base64` decode để lấy `sub` và coi đó là danh tính đã được xác thực. Việc xác minh chữ ký, issuer, audience, thời hạn và nonce (khi áp dụng) phải nằm trong cơ chế decoder/validator tin cậy.

### 8.2. Cấu hình khóa trong `ClientRegistration`

Trong Spring Boot, thông tin provider có thể có các thuộc tính như:

~~~yaml
spring:
  security:
    oauth2:
      client:
        provider:
          company-oidc:
            issuer-uri: https://login.example.com
~~~

`issuer-uri` là điểm xuất phát để lấy metadata chuẩn và xây dựng thông tin provider. Việc cấu hình `jwk-set-uri` tường minh có thể hữu ích ở một số tình huống, nhưng phải sử dụng URL JWKS **chính thức, đáng tin** của issuer. **Không đổi tùy tiện sang JWKS của một provider khác** để khắc phục lỗi tải khóa.

Nếu các endpoints được cấu hình riêng thay vì thông qua metadata discovery, ứng dụng vẫn phải bảo toàn đầy đủ validation OIDC, gồm issuer và ID Token. Thay đổi cách xác định JWKS URI **không được làm yếu** trust boundary.

### 8.3. WebFlux

Trong WebFlux, cấu hình bảo mật có hình thức tương ứng:

~~~java
@Configuration
@EnableWebFluxSecurity
class ReactiveOidcLoginSecurity {

    @Bean
    SecurityWebFilterChain webSecurity(ServerHttpSecurity http) {
        return http
            .authorizeExchange(auth -> auth
                .pathMatchers("/", "/assets/**").permitAll()
                .anyExchange().authenticated())
            .oauth2Login(Customizer.withDefaults())
            .build();
    }
}
~~~

`ReactiveClientRegistrationRepository` quản lý client registration bên WebFlux, còn các thành phần OAuth2/OIDC reactive thực hiện authorization-code exchange và ID Token validation. Tùy biến HTTP client/JWKS retrieval cần dùng **các extension points phù hợp với reactive stack**; không đưa trực tiếp code Servlet vào luồng WebFlux.

### 8.4. Tùy biến cache ở đúng điểm tích hợp

Có hai luồng xác minh dễ bị nhầm:

| Luồng | Token cần xác minh | Thành phần cần điều chỉnh khi tùy biến JWKS |
| --- | --- | --- |
| **OAuth2/OIDC Login** | **ID Token** trả về cho OAuth2 Client | OIDC ID Token decoder/factory và HTTP retrieval liên quan của **OAuth2 Login** |
| **Resource Server** | **Access token** dạng JWT được gửi vào API | `JwtDecoder`/resource-server JWT configuration tương ứng |

Ví dụ cấu hình:

~~~java
http.oauth2ResourceServer(oauth2 ->
    oauth2.jwt(Customizer.withDefaults()));
~~~

là cách **bảo vệ API như Resource Server**, không phải cách duy nhất hoặc mặc định để điều khiển ID Token decoder trong `oauth2Login()`.

Tương tự, một `WebClient` bean có proxy, timeout và retry do ứng dụng tạo **không bảo đảm** JWKS retrieval của OIDC Login tự dùng bean đó. JWKS decoder có thể dùng HTTP client hoặc cache riêng. Nếu ứng dụng thực sự cần tùy biến TTL, networking, cache store hay JWKS refresh, cần kiểm tra **phiên bản Spring Security và Nimbus JOSE + JWT** trong dependency graph và sử dụng đúng API decoder/factory/JWK source được hỗ trợ.

Không nên thay thế OIDC authentication provider bằng một đoạn code tự xác minh JWT chỉ để điều chỉnh TTL: làm vậy dễ bỏ sót nonce, issuer, audience, `azp`, expiry và các ràng buộc của OIDC.

## 9. Giải quyết lỗi tải JWKS: không đồng nhất mọi lỗi

Các lỗi có thể xảy ra ở nhiều lớp. Mỗi lớp cần cách xử lý khác nhau:

| Tình huống | Biểu hiện có thể thấy | Giải thích | Xử lý ưu tiên |
| --- | --- | --- | --- |
| DNS của backend không phân giải JWKS host | `UnknownHostException` hoặc tên tương đương | Resolver/private DNS không có record/tuyến | Kiểm tra DNS từ VM/pod chạy app |
| Không kết nối TCP tới JWKS | Connect timeout/reset | Firewall, NAT, route, proxy hoặc NetworkPolicy | Kiểm tra egress path và timeout |
| TLS trust thất bại | `PKIX path building failed`, certificate error | JVM chưa tin CA, chain thiếu, certificate sai | Sửa truststore/CA và hostname |
| JWKS trả `401`/`403` | HTTP unauthorized/forbidden | Endpoint bị bảo vệ sai hoặc gateway chặn | JWKS public phải được truy xuất theo hợp đồng provider; kiểm tra ACL/gateway |
| JWKS trả `404` | Not found | `jwks_uri` sai, issuer/realm/path đổi | Xác minh metadata chính thức |
| JWKS trả `429` | Rate limit | Quá nhiều lần refresh/unknown `kid` | Backoff, cooldown, cache/single-flight |
| JWKS trả `502`/`503`/`504` | Upstream unavailable | Gateway/IdP mất khả dụng hoặc quá tải | Timeout, bounded retry, alerting |
| JWKS trả HTML/JSON không hợp lệ | Parse failure | WAF/login portal trả trang HTML hoặc payload lỗi | Kiểm tra content-type/body đã che dữ liệu và proxy route |
| Cache có K1, token chứa `kid=K2` | Unknown key ID | Provider mới xoay khóa hoặc token không đáng tin | Refresh JWKS có giới hạn; nếu không tìm thấy K2 thì từ chối |
| Khóa K2 có trong JWKS nhưng chữ ký sai | Signature verification failure | Token bị sửa, sai khóa, sai algorithm hoặc issuer | Từ chối; không thử khóa tùy tiện |
| JWKS đúng nhưng token `iss`/`aud` sai | Claims validation failure | Token không được phát cho issuer/client dự kiến | Từ chối; kiểm tra cấu hình provider và client |
| `nonce` không khớp | OIDC correlation failure | ID Token không thuộc authorization request đã khởi tạo | Từ chối; kiểm tra flow, state/session và nonce |
| Lỗi chỉ xảy ra ở vài pod | Cache/network inconsistency | Pod khác version/cache hoặc egress | So cache age, dependency, proxy, DNS và rollout |
| Lỗi xuất hiện ngay sau rotation | Cache vẫn giữ key cũ hoặc thiếu key mới | Provider công bố khóa chưa đủ sớm hoặc decoder không refresh | Kiểm tra timeline publish, TTL và refresh behavior |

**Không kết luận “JWKS đang lỗi” chỉ vì OIDC Login thất bại.** Authorization code, PKCE verifier, state/session, client authentication, claim validation và Resource Server là các bước riêng. Cần xác định lỗi xảy ra lúc **lấy khóa**, **chọn khóa**, **xác minh chữ ký** hay **kiểm tra claims**.

### 9.1. Unknown `kid` và signature invalid là hai lỗi khác nhau

Ví dụ:

- JWKS hiện tại có public key K1. Token header khai báo `kid=K2`. Decoder **không tìm được khóa ứng viên**. Một lượt refresh hợp lệ có thể đưa về K2.
- JWKS có K2 và token cũng khai báo K2, nhưng chữ ký không xác minh được. Đây là **signature invalid**; không được cố sửa bằng cách vô hiệu xác minh, chấp nhận token nếu payload “trông hợp lệ”, hoặc thử khóa tùy ý không được tin cậy.

Một attacker có thể tạo rất nhiều JWT với `kid` ngẫu nhiên để kích hoạt cache miss. Vì thế chỉ refresh từ **JWKS URI đã được cấu hình**, theo cooldown/rate limit thích hợp; **không tải một key server mới từ dữ liệu header của token**.

### 9.2. Phân biệt lỗi mạng tạm thời và lỗi trust

Mất mạng tới JWKS có thể là sự cố khả dụng; certificate sai host hoặc chain không tin cậy là **lỗi danh tính máy chủ**. Giải pháp cho cả hai không giống nhau:

- Network timeout: kiểm tra proxy/route/firewall, điều chỉnh timeout/retry có giới hạn nếu cần.
- TLS validation error: xác nhận CA và hostname; sửa certificate/trust material, không tắt verification.
- Unknown `kid` sau rotation: kiểm tra provider có publish K2 và decoder có refresh theo chính sách.
- Invalid signature: từ chối token và điều tra tính toàn vẹn/token provenance.

Không sử dụng cấu hình “trust all certificates”, “disable hostname verification” hoặc bỏ `iss`/`aud` để vượt lỗi đăng nhập.

## 10. Chính sách khi JWKS endpoint tạm thời không khả dụng

Đây là quyết định giữa **độ sẵn sàng** và **mức tin cậy** của khóa.

### 10.1. Không có khóa phù hợp đã được tin cậy

Nếu JWKS endpoint không kết nối được và cache **không có khóa phù hợp** để xác minh chữ ký, client không thể chứng minh ID Token hợp lệ.

**Hành vi an toàn: từ chối đăng nhập** hoặc hiển thị lỗi tạm thời và khởi tạo lại flow sau khi hệ thống phục hồi. Không cho login chỉ dựa trên claims được decode.

### 10.2. Có last-known-good key phù hợp

Nếu cache còn K1 được tải từ provider chính thức trước đó, ứng dụng **có thể** tiếp tục xác minh một ID Token được ký bằng K1 trong thời gian ngắn nếu **chính sách bảo mật cho phép sử dụng cache cũ có giới hạn**. Điều kiện tối thiểu:

1. K1 đến từ JWKS của issuer đã được cấu hình và từng được xác thực qua kênh đáng tin.
2. Token thực sự có chữ ký hợp lệ bằng K1, không chỉ trùng `kid`.
3. Các kiểm tra OIDC còn lại vẫn chạy: issuer, audience, expiry, nonce khi có, v.v.
4. Độ tuổi bản cache nằm trong giới hạn hard-expiry của policy.
5. Không có tín hiệu K1 đã bị thu hồi/compromise.
6. Việc sử dụng stale cache được theo dõi và có thời hạn, không kéo dài vô hạn.

Đây là mô hình **graceful degradation có kiểm soát**, không phải behavior mặc định được bảo đảm của Spring Security/Nimbus. Một số tổ chức yêu cầu fail closed ngay khi cache không còn fresh; chính sách đó cũng hợp lệ, đặc biệt với ứng dụng nhạy cảm.

### 10.3. Khi không biết key có bị rút khỏi JWKS hay không

Nếu mạng hỏng, client không biết provider vừa rút K1 vì rotation bình thường hay vì compromise. Do đó mỗi phút dùng stale cache là một khoảng chấp nhận rủi ro nhất định. Với ứng dụng có yêu cầu bảo mật cao, nên chọn **ngưỡng staleness ngắn** hoặc fail closed.

Một tính năng “giữ mọi public key cũ mãi mãi cho đến khi token hết hạn” **không thay thế** kiểm tra thu hồi khóa. Trong sự cố compromise, token giả có thể được ký với private key đã lộ trước khi tới hạn `exp`. Cần cơ chế xử lý khẩn cấp ngoài cache TTL thông thường.

### 10.4. Không retry vô hạn trong authentication filter

Nếu JWKS retrieval timeout, giữ request login treo lâu hoặc retry vô hạn có thể làm cạn worker/thread/event-loop resources. Thay vào đó:

- Đặt connect/read/overall timeout phù hợp hạ tầng.
- Giới hạn số lượt retry, áp dụng backoff và jitter khi thích hợp.
- Không retry lỗi xác minh chữ ký/claims như lỗi mạng.
- Nếu dùng cache, áp dụng single-flight/cooldown cho refresh.
- Có thông điệp lỗi phù hợp cho người dùng và log đủ thông tin vận hành đã ẩn bí mật.

Không phải mọi HTTP error đều đáng retry. Ví dụ `404` do cấu hình JWKS URI sai hoặc TLS hostname mismatch phải được **sửa cấu hình**, không giải quyết bằng retry dày đặc.

## 11. Kiểm tra JWKS và TLS từ đúng môi trường chạy ứng dụng

Khi IdP nằm trong mạng nội bộ hoặc hệ thống có egress proxy, hãy kiểm tra **từ pod/VM/container chạy Spring Boot hoặc môi trường có cùng DNS, routing và truststore**. Kiểm tra từ laptop chỉ chứng minh đường mạng của laptop.

Ví dụ issuer ở root path:

~~~bash
# Đọc metadata của provider đã được xác minh.
curl --connect-timeout 5 --max-time 15 -fsS \
  https://login.example.com/.well-known/openid-configuration \
  | jq -r '.issuer, .jwks_uri, (.id_token_signing_alg_values_supported // [])'
~~~

Trong kết quả, xác nhận `issuer` khớp cấu hình client và `jwks_uri` trỏ tới endpoint được provider công bố. Đường dẫn discovery ở ví dụ áp dụng issuer dạng root; với issuer có path/realm, dùng URL discovery đúng theo provider.

Lấy tập khóa bằng URL thực tế từ metadata, ví dụ nếu provider công bố `https://login.example.com/oauth2/keys`:

~~~bash
curl --connect-timeout 5 --max-time 15 -fsS \
  https://login.example.com/oauth2/keys \
  | jq -r '.keys[] | [.kid, .kty, (.alg // "-"), (.use // "-")] | @tsv'
~~~

Lệnh trên chỉ xem **metadata của public keys**; không in token hoặc credential. `jq` là công cụ tùy chọn để đọc JSON; trên môi trường không có `jq`, có thể dùng trình đọc JSON khác.

Nếu provider dùng CA nội bộ đã được tổ chức xác minh:

~~~bash
curl --cacert /opt/app/certs/corp-root-ca.pem \
  --connect-timeout 5 --max-time 15 -fsS \
  https://login.example.com/oauth2/keys
~~~

Để quan sát TLS certificate của đường kết nối trực tiếp khi có OpenSSL:

~~~bash
openssl s_client \
  -connect login.example.com:443 \
  -servername login.example.com \
  -showcerts
~~~

Nếu tuyến thực đi qua HTTP CONNECT proxy hoặc TLS inspection, kết quả của kết nối trực tiếp có thể khác. Cần kiểm tra proxy/DNS/truststore của **HTTP client mà Spring Security dùng để tải JWKS**, không chỉ dựa trên `curl`.

**Đặc biệt:** `curl` thành công không chứng minh JVM cũng thành công, vì CA store, proxy environment, HTTP client, DNS resolver và timeout có thể khác nhau. `curl -k` chỉ bỏ qua TLS validation nên không chứng minh cấu hình an toàn; không dùng nó làm giải pháp production.

### 11.1. Truststore JVM và private CA

Nếu thấy lỗi dạng:

~~~text
PKIX path building failed
unable to find valid certification path to requested target
~~~

hãy kiểm tra chain certificate của provider và trust material Java. Có thể tạo truststore riêng đã được kiểm chứng:

~~~bash
keytool -importcert \
  -alias corporate-root \
  -file corp-root-ca.pem \
  -keystore corporate-truststore.p12 \
  -storetype PKCS12
~~~

Sau đó cấu hình JVM hoặc HTTP client liên quan sử dụng truststore đó. Việc thay global JVM truststore có thể làm mất tập CA công cộng mặc định nếu file mới không chứa chúng; cần bảo đảm các endpoint khác vẫn được tin cậy hợp lệ.

**Lưu ý:** truststore chứa CA dùng để xác minh **server TLS certificate**, không phải JWKS public key cache. Trust TLS thành công chưa chứng minh nội dung JWKS an toàn nếu issuer/JWKS URI bị cấu hình sai; ngược lại, JWKS hợp lệ cũng không cho phép bỏ qua TLS hostname verification.

### 11.2. Cảnh báo trên proxy/CDN cache

Proxy HTTP hoặc CDN đứng trước JWKS endpoint có thể tiếp tục trả **bộ khóa cũ** dù provider đã publish K2. Cần xác định:

- Provider backend đã công bố K2 chưa?
- Proxy/CDN có cache JWKS và TTL riêng không?
- HTTP response headers có phù hợp với chính sách rotation không?
- Các client ở những region có nhận cùng phiên bản JWKS không?
- Có proxy authentication/allowlist ảnh hưởng đến JWKS URI không?

Không ép cache “luôn fresh” bằng cách vô hiệu hóa toàn bộ cache nếu traffic lớn; ưu tiên một chiến lược TTL/refresh phù hợp thời điểm rotation và ngân sách request.

## 12. Theo dõi phiên bản thư viện và hành vi thực tế của cache

Spring Security có thể sử dụng nhiều lớp thư viện cho OIDC/JWT, trong đó phần JWT/JWK thường liên quan **Nimbus JOSE + JWT**. Hành vi cụ thể thay đổi theo phiên bản:

- Cache nằm ở mức decoder, JWK source, JWKS document hay HTTP client?
- TTL mặc định là bao nhiêu?
- Có refresh ngay khi gặp unknown `kid` không, hay phải đợi TTL?
- Có giới hạn tần suất refresh khi unknown `kid` liên tục không?
- Có hỗ trợ ETag/HTTP cache header không?
- Có chấp nhận stale key khi lỗi mạng không, và trong giới hạn nào?
- Decoder được tạo theo **mỗi ClientRegistration**, mỗi issuer hay được chia sẻ tùy cách ứng dụng cấu hình?
- Có hook để cung cấp custom HTTP client, proxy, cache hoặc validator không?
- Behavior của login OIDC có giống Resource Server decoder không?

**Không nên ghi một TTL mặc định như “5 phút” thành quy tắc chắc chắn** nếu chưa kiểm tra phiên bản thực tế và config. Tương tự, không nên hứa rằng “unknown kid chắc chắn được refresh ngay” khi chưa xác định implementation.

Khi cần thay đổi behavior, ưu tiên cách được Spring Security/Nimbus hỗ trợ chính thức: custom OIDC decoder/factory/JWK source hoặc HTTP retrieval theo API đúng phiên bản. Không tự cắt bỏ phần OIDC claim validation để cài cache riêng.

### 12.1. Hướng cấu trúc cho custom cache (pseudocode)

Ý tưởng thuật toán của một bộ giải quyết key an toàn:

~~~text
resolveSigningKey(issuer, allowedAlgorithms, tokenHeader):
    assert issuer is configured and trusted
    assert tokenHeader.alg belongs to allowedAlgorithms

    cache = keySetCache.forIssuer(issuer)
    key = cache.findCandidate(
        kid=tokenHeader.kid,
        alg=tokenHeader.alg,
        use="sig"
    )

    if key absent:
        if refreshPolicy.allowsAttempt(issuer):
            refreshOnceWithTimeout(
                jwksUri=configuredMetadata[issuer].jwksUri
            )
            key = cache.findCandidate(...)

    if key absent:
        fail("No trusted signing key available")

    if cache too stale under active security policy:
        fail("Trusted key freshness requirement not met")

    return key
~~~

Đây là **pseudocode kiến trúc**, không phải API có sẵn để copy vào Spring Security. Nó chỉ giải quyết **lựa chọn khóa**; tầng phía trên vẫn phải xác minh signature và **toàn bộ OIDC ID Token claims**. Nếu bạn tự xây logic này, cần đánh giá rất kỹ trust boundary, concurrency, TTL và các edge cases của JOSE; thường an toàn hơn khi cấu hình thư viện đã được duy trì và kiểm chứng.

## 13. Khóa cũ, phiên đăng nhập và thời hạn token: ba vòng đời khác nhau

Đôi khi nhóm vận hành nhận thấy “đã xóa K1 khỏi JWKS nhưng người dùng login trước đó vẫn ở trong ứng dụng”. Điều này không nhất thiết là bug của JWKS cache.

Trong một web app dựa trên HTTP session:

1. User hoàn thành OIDC Login. Client xác minh ID Token bằng public K1.
2. Spring Security tạo `Authentication` và lưu trong session ứng dụng.
3. Các request browser tiếp theo có thể dùng **session cookie**, không cần tải JWKS và kiểm tra lại ID Token ở mỗi request.
4. Provider gỡ K1 khỏi JWKS. **Session đã xác thực trong app vẫn có thể tồn tại** cho đến khi session bị hết hạn/thu hồi theo chính sách.

Ngoài ra:

- **ID Token expiration** quy định khi nào ID Token còn được chấp nhận như assertion theo policy.
- **Access token expiration** quy định vòng đời credential dùng để gọi API.
- **JWKS cache lifetime** quy định độ mới của tập public keys.
- **Application session lifetime** quy định thời gian phiên người dùng tại ứng dụng tồn tại.

Bốn mốc có thể khác nhau. Khi ký khóa bị compromise, cần đánh giá ảnh hưởng đến **các phiên đã đăng nhập** chứ không chỉ thay JWKS.

## 14. Kịch bản triển khai và phân tích

### Tình huống A — Provider chuẩn bị xoay K1 sang K2

Provider công bố JWKS chứa K1, K2 trước khi chuyển ký bằng K2. Các Spring Boot instances ở nhiều region có cache JWKS khác nhau.

**Cách tiếp cận:** công bố K2 đủ sớm để các client có cơ hội refresh; tính toán thời gian chờ dựa trên cache policy/rollout thực; sau đó chuyển ký và giám sát unknown `kid`. Giữ K1 trong giai đoạn chồng lấn để ID Token cũ còn hợp lệ có thể được xác minh. Không thay private/public key nhưng tiếp tục dùng cùng `kid` theo thói quen.

### Tình huống B — Sau rotation, một nhóm pod lỗi unknown `kid=K2`

Một số pod đã có K2; nhóm còn lại tiếp tục dùng cache K1 hoặc bị egress proxy chặn JWKS.

**Cách tiếp cận:** so sánh phiên bản thư viện, cache age, khả năng refresh, proxy và DNS theo từng pod. Kiểm tra endpoint JWKS thực sự đã có K2 và request từ pod lỗi có đi tới đúng URL tin cậy. Không sửa bằng cách cho client chấp nhận ID Token chưa xác minh.

### Tình huống C — JWKS endpoint trả 503 trong lúc login tăng cao

IdP authentication/Token Endpoint còn đáp ứng, nhưng JWKS mất khả dụng.

**Cách tiếp cận:** nếu client có key hợp lệ theo policy, có thể tiếp tục xác minh những ID Token dùng key đã cache **trong khoảng cho phép**. Với unknown kid hoặc không có key phù hợp, phải từ chối. Giới hạn retry và theo dõi outage. Nếu chính sách yêu cầu JWKS luôn fresh, fail closed khi không làm mới được.

### Tình huống D — JWT có `kid` trùng nhưng signature invalid

JWKS công bố K1, token cũng khai báo `kid=K1`, song chữ ký không khớp.

**Cách tiếp cận:** từ chối ID Token. Không kết luận đây đơn thuần là “cache chưa cập nhật”, vì có thể là token bị sửa, ký bằng private key khác, chọn sai issuer hoặc provider quản lý khóa sai. Xác minh cấu hình issuer/algorithm/key và điều tra sau khi đã chặn token.

### Tình huống E — JWKS URL có certificate từ CA doanh nghiệp

`curl` trên laptop thành công, container Spring Boot lỗi PKIX.

**Cách tiếp cận:** xác định CA chain và hostname, nhập CA tin cậy vào truststore/SSL context mà **HTTP client thực sự dùng để tải JWKS**, kiểm tra proxy interception và hướng DNS của pod. Không dùng “trust all” để bỏ qua lỗi TLS.

### Tình huống F — Khóa K1 bị lộ, ứng dụng đang cho phép stale cache dài

IdP gỡ K1 nhưng client vẫn chấp nhận token ký bằng K1 do cache chưa hết hard TTL.

**Cách tiếp cận:** kích hoạt quy trình khẩn cấp để invalidate/refresh cache, dừng tin K1 và đánh giá session/token đã phát. Tính năng stale cache để vượt outage thông thường không được phép ngăn việc thu hồi khóa compromise.

### Tình huống G — Một token từ issuer khác có cùng `kid`

Multi-tenant app dùng hai OIDC Providers A và B, cả hai có key ID là `current`.

**Cách tiếp cận:** cache và chọn key phải theo **issuer/JWKS URI tin cậy**, không chỉ theo `kid`. ID Token từ provider B không được xác minh bằng khóa của provider A hoặc được gán vào `ClientRegistration` khác chỉ vì trùng nhãn key.

### Tình huống H — Session tồn tại sau khi provider gỡ signing key

Người dùng đăng nhập trước rotation vẫn truy cập website nhờ session.

**Cách tiếp cận:** đây là sự khác biệt giữa **ID Token validation lúc login** và **session validation mỗi request**. Nếu cần buộc xác thực lại, phải có chính sách session/reauthentication hoặc thu hồi phiên, không dựa vào JWKS rotation đơn thuần.

## 15. Giám sát và cảnh báo vận hành

Một hệ thống OIDC Client đáng tin cậy nên phân biệt **lỗi tải JWKS**, **lỗi chọn key**, **lỗi chữ ký**, và **lỗi claim** thay vì gom thành một chỉ số “login failed”.

| Chỉ số/event gợi ý | Ý nghĩa |
| --- | --- |
| `jwks_fetch_success` / `jwks_fetch_failure` | Tần suất thành công/thất bại khi liên hệ JWKS endpoint |
| `jwks_fetch_duration` | Độ trễ truy xuất key set |
| `jwks_cache_hit` / `jwks_cache_miss` | Khả năng dùng khóa từ cache |
| `jwks_refresh_trigger{reason=ttl_or_unknown_kid}` | Nguyên nhân reload; cần giới hạn cardinality |
| `jwks_unknown_kid` | Token không tìm được key tương ứng trong nguồn tin cậy |
| `id_token_signature_failure` | Chữ ký không hợp lệ dù đã có key phù hợp |
| `id_token_claim_failure` | Issuer/audience/time/nonce hoặc điều kiện OIDC khác không hợp lệ |
| `oidc_login_success` / `oidc_login_failure` | Kết quả xác thực tổng thể |

Tên metric chỉ là gợi ý, không phải metric mặc định của Spring Security. Không đưa raw `kid`, `state`, `nonce` hoặc token vào metric label/cardinality vô hạn; nhiều `kid` giả do attacker gửi có thể làm tăng chi phí giám sát.

Trong log sự cố, thông tin có ích thường là:

- Registration ID/issuer **đã được chuẩn hóa** và hostname JWKS.
- Giai đoạn lỗi: discovery, TCP, TLS, HTTP, JSON parse, key selection, signature, OIDC claim validation.
- HTTP status, loại exception và thời gian request.
- Cache age/cache hit/miss và thời điểm refresh thành công gần nhất.
- Correlation ID nội bộ của login flow, không mang credential.

**Không ghi log** raw ID Token, access token, authorization code, client secret, private key, session cookie, PKCE verifier hoặc nonce; ngay cả payload có thông tin định danh cũng có thể là dữ liệu nhạy cảm.

### 15.1. Cảnh báo cần nhìn theo thời gian

Tăng `unknown_kid` ngay khi provider thay signing key có thể là dấu hiệu cache chưa làm mới đủ nhanh. Tăng `jwks_fetch_failure` cùng lỗi mạng cho thấy vấn đề ở JWKS endpoint/egress. Tăng `signature_failure` mà JWKS vẫn tải bình thường có thể là sự cố khóa, sai issuer, sai thuật toán hoặc token giả mạo; không nên tự động đổi security policy để “làm xanh dashboard”.

## 16. Những hiểu nhầm thường gặp

**“Trong JWKS có `kid` của token, vậy ID Token hợp lệ.”** Không. `kid` chỉ giúp chọn ứng viên; vẫn phải xác minh chữ ký và claims.

**“Cache key nghĩa là không cần kiểm tra chữ ký mỗi lần login.”** Không. Cache giảm số lần tải khóa qua mạng; nó không bỏ xác minh token mới.

**“Bật `oauth2ResourceServer().jwt()` là đã cấu hình cache cho OIDC Login.”** Không. Resource Server xác minh access token đi vào API; OAuth2 Login xác minh ID Token bằng luồng/decoder tương ứng.

**“Thấy `kid` lạ thì tải JWKS từ URL `jku` trong token.”** Không. Nguồn JWKS phải được ràng buộc với issuer/provider đã tin cậy, không lấy từ token chưa xác minh.

**“Cache miss nghĩa là chắc chắn provider vừa rotate key.”** Không. Có thể là token giả với `kid` tùy ý, lỗi issuer hoặc JWKS endpoint không đồng bộ.

**“JWKS endpoint trả 503 nên có thể bỏ qua kiểm tra chữ ký.”** Không. Không có public key phù hợp được tin cậy thì phải từ chối. Nếu dùng cache cũ, phải theo policy có giới hạn và vẫn kiểm tra chữ ký/claims.

**“Đổi signing key là tự logout toàn bộ người dùng.”** Không. Phiên đăng nhập hiện hữu có thể độc lập với việc xác minh ID Token mới; cần quản lý session riêng.

**“Nhận được JWKS qua HTTPS là đủ, không cần validate issuer/audience.”** Không. JWKS chỉ là một phần của validation; token phải được phát hành bởi đúng issuer và dành cho đúng client.

**“Bất cứ lỗi `invalid_grant` nào cũng do JWKS.”** Không. `invalid_grant` thường liên quan token exchange, authorization code, redirect URI, PKCE hoặc trạng thái grant; JWKS thường được dùng ở bước xác minh chữ ký sau khi đã nhận ID Token.

**“Dùng chung cache theo `kid` cho mọi tenant để tiết kiệm bộ nhớ.”** Không an toàn. Cần phân biệt issuer/JWKS source để tránh chọn nhầm khóa giữa các provider.

## 17. Câu hỏi tự kiểm tra

**Câu 1.** ID Token khai báo `alg=RS256` và `kid=K2` nhưng cache chỉ có K1. Ứng dụng có nên tự động chấp nhận token vì provider đang rotation?

**Trả lời:** Không. Ứng dụng có thể làm mới JWKS từ nguồn tin cậy theo policy. Nếu không tìm được K2 phù hợp hoặc không xác minh được chữ ký, phải từ chối.

**Câu 2.** Provider chuẩn bị xoay K1 sang K2. Thứ tự nào giúp hạn chế lỗi đăng nhập nhất?

**Trả lời:** Công bố public K2 trong JWKS **trước khi** dùng private K2 để ký token mới, cho phép cache có thời gian cập nhật; chuyển sang ký K2; giữ public K1 trong thời gian chuyển tiếp phù hợp; sau đó mới gỡ K1 khi không còn token cũ cần xác minh, trừ trường hợp compromise.

**Câu 3.** Nếu JWKS endpoint đang down nhưng cache có K1, có thể bỏ qua kiểm tra `iss` và `aud` để login tiếp không?

**Trả lời:** Không. Dù dùng cached key theo policy, client vẫn phải xác minh chữ ký và mọi claim OIDC bắt buộc, gồm issuer, audience, thời hạn và nonce khi áp dụng.

**Câu 4.** Tại sao TTL của JWKS cache không đồng nghĩa với thời hạn ID Token?

**Trả lời:** TTL cache quyết định độ mới của **public keys**; `exp` trong ID Token quyết định token còn hiệu lực. Token đã hết hạn không trở nên hợp lệ vì key vẫn cache, và key quá stale có thể bị policy từ chối dù token chưa hết hạn.

**Câu 5.** Có thể dùng `JwtDecoder` bean của Resource Server để chắc chắn thay đổi cache ID Token trong `oauth2Login()` không?

**Trả lời:** Không thể kết luận như vậy. Cần xác định đúng decoder/factory và HTTP/JWK cache của **OIDC Login**, theo Spring Security version và stack được dùng.

**Câu 6.** Vì sao HTTP `503` do JWKS endpoint và `signature verification failed` cần hai hướng xử lý khác nhau?

**Trả lời:** `503` là lỗi khả dụng của đường lấy khóa; có thể cần retry có giới hạn, kiểm tra egress/cache policy. Signature failure là lỗi xác minh token; phải từ chối, không retry mù quáng hoặc bỏ kiểm tra.

**Câu 7.** Trong multi-tenant OIDC Client, hai issuer có thể dùng cùng `kid` không?

**Trả lời:** Có. `kid` là định danh khóa trong ngữ cảnh key set, không phải định danh toàn cục. Cache phải ràng buộc khóa với issuer/JWKS source được tin cậy.

**Câu 8.** Khi private signing key bị lộ và IdP gỡ public key khỏi JWKS, ứng dụng có nên tiếp tục chấp nhận khóa từ cache stale không?

**Trả lời:** Không. Cần thực hiện policy thu hồi khẩn cấp, làm mới/evict cache và đánh giá các session/token liên quan. Stale cache có kiểm soát dành cho sự cố mạng thông thường không được áp dụng để bỏ qua thông tin compromise.

**Câu 9.** `curl` tải JWKS thành công trên laptop nhưng ứng dụng trong Kubernetes lỗi TLS. Điều gì cần kiểm tra?

**Trả lời:** DNS/route của pod, proxy egress, server certificate SAN/chain, CA truststore hoặc SSL context của HTTP client thực sự tải JWKS; laptop và container có thể dùng trust material khác nhau.

**Câu 10.** Người dùng đã đăng nhập bằng ID Token ký với K1 vẫn ở lại website sau khi K1 bị gỡ khỏi JWKS. Đây có phải bằng chứng cache không cập nhật?

**Trả lời:** Không nhất thiết. Web app có thể đang dùng session cookie để xác thực request tiếp theo, không còn xác minh lại ID Token mỗi lần. Quản lý và thu hồi phiên là một cơ chế riêng.

## 18. Tài liệu tham khảo

- [Spring Security Reference — OAuth 2.0 Login (Servlet)](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/index.html)
- [Spring Security Reference — Advanced OAuth 2.0 Login Configuration](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/advanced.html)
- [Spring Security Reference — OAuth 2.0 Login (Reactive)](https://docs.spring.io/spring-security/reference/reactive/oauth2/login/index.html)
- [Spring Security API — OidcIdTokenDecoderFactory](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/client/oidc/authentication/OidcIdTokenDecoderFactory.html)
- [OpenID Connect Core 1.0 — ID Token Validation](https://openid.net/specs/openid-connect-core-1_0.html)
- [OpenID Connect Discovery 1.0 — jwks_uri](https://openid.net/specs/openid-connect-discovery-1_0.html)
- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517)
- [RFC 7518 — JSON Web Algorithms (JWA)](https://www.rfc-editor.org/rfc/rfc7518)
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519)
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725)

**Ghi nhớ:** JWKS là **nguồn public keys đáng tin gắn với đúng issuer** để xác minh ID Token được ký bất đối xứng. Cache làm giảm tải và độ trễ, nhưng phải có giới hạn về độ mới và cơ chế refresh phù hợp khi xuất hiện khóa mới. Provider cần rotation có **khoảng chồng lấn public keys**; khi có khóa bị lộ, phải thu hồi theo quy trình khẩn cấp. Nếu không có khóa phù hợp đáng tin hoặc chữ ký/claims không hợp lệ, ứng dụng **từ chối xác thực** thay vì bỏ qua validation để duy trì login.

