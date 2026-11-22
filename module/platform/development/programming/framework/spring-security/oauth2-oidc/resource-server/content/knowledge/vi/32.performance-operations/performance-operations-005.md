# Tải tăng khi gặp `kid` mới, nhiều issuer hoặc token ngẫu nhiên

Một Spring Security OAuth 2.0 Resource Server có thể gặp tải tăng mạnh dù phần lớn request cuối cùng đều bị từ chối. Nguyên nhân thường nằm ở các bước xác minh token cần truy cập dịch vụ bên ngoài hoặc tạo cache entry:

- **JWT có `kid` chưa biết:** decoder không tìm thấy public key tương ứng trong JWK Set đang cache và có thể phải tải lại JWKS để tìm key mới.
- **Nhiều issuer:** mỗi issuer có metadata, decoder, JWK Set cache, connection và policy riêng. Nếu issuer được phát hiện động, token từ issuer lạ có thể kích hoạt lookup hoặc tạo manager mới.
- **Token ngẫu nhiên:** token JWT có cấu trúc nhưng chứa `kid` ngẫu nhiên có thể làm tăng số lần refresh JWKS; opaque token ngẫu nhiên có thể làm tăng số lần gọi introspection.

Các request này thường đến từ client cấu hình sai, key rotation chưa đồng bộ, bot quét API hoặc một cuộc tấn công từ chối dịch vụ. Chúng cũng có thể xuất hiện trong đợt triển khai bình thường nếu nhiều instances đồng thời nhận token được ký bằng key mới.

> **Nguyên tắc vận hành:** giới hạn số nguồn issuer được tin cậy, kiểm soát chi phí của key refresh và introspection, tránh cache stampede, đặt giới hạn concurrency/timeout và giữ fail-closed khi không xác minh được token. Không chặn nhầm key mới trong một đợt rotation hợp lệ.

Bài học thuộc phần **Hiệu năng và vận hành**. Nội dung tập trung vào Spring Security Resource Server chạy Servlet với JWT/JWKS, opaque token/introspection và multi-issuer. Một số khái niệm cache, rate limit và observability áp dụng cho cả WebFlux, nhưng API reactive tương ứng khác với API Servlet.

## 1. Vì sao token bị từ chối vẫn có thể tạo tải lớn?

Một request bearer đi qua nhiều bước trước khi server kết luận token hợp lệ hay không:

~~~text
HTTP request
    |
    v
BearerTokenResolver
    |
    v
Parse token / đọc header claims chưa xác minh
    |
    v
Chọn AuthenticationManager / issuer
    |
    +----------------------------+
    |                            |
    v                            v
JWT Resource Server          Opaque Resource Server
    |                            |
    v                            v
JwtDecoder                  Token Introspection
    |                            |
    v                            v
Chọn key theo kid           Gọi Authorization Server
    |                            |
    v                            v
JWKS cache / refresh        active + token attributes
    |                            |
    +-------------+--------------+
                  |
                  v
        Xác minh issuer/audience/time
                  |
                  v
        Authentication / Authorization
~~~

Một request có thể bị từ chối ở nhiều điểm:

- Header không có bearer token: không cần tải JWKS hay gọi introspection.
- Token không parse được: thường bị từ chối trước khi tìm key.
- JWT parse được nhưng `kid` không khớp key cache: có thể kích hoạt JWKS refresh.
- Issuer không nằm trong allowlist: phải bị từ chối trước khi thực hiện discovery/lookup không được phép.
- Opaque token: Resource Server thường phải gọi introspection nếu không có cache hợp lệ.
- Token xác thực thành công nhưng thiếu scope: bị từ chối ở authorization, sau khi chi phí authentication đã phát sinh.

Vì vậy, **tỷ lệ 401 cao không tự chứng minh hệ thống đang an toàn trước tải xấu**. Cần quan sát thêm JWKS fetch, introspection request, cache miss, unknown issuer, latency và concurrency.

## 2. Ba kiểu tải cần phân biệt

### 2.1. JWT có `kid` mới hoặc không biết

Một JWT header có thể chứa:

~~~json
{
  "alg": "RS256",
  "kid": "signing-key-2026-b",
  "typ": "at+jwt"
}
~~~

Resource Server dùng `kid` để chọn public key trong JWKS của issuer đã cấu hình. Khi key không có trong JWK Set cache, decoder/JWK source có thể làm mới JWKS để tìm key vừa được công bố.

Đây là hành vi cần thiết cho key rotation. Nhưng một client có thể gửi nhiều JWT khác nhau, mỗi token có một `kid` ngẫu nhiên:

~~~text
kid=random-001 -> không có key -> refresh có thể xảy ra
kid=random-002 -> không có key -> refresh có thể xảy ra
kid=random-003 -> không có key -> refresh có thể xảy ra
...
~~~

Hệ quả có thể là:

- Nhiều HTTP requests tới JWKS endpoint.
- Tăng TLS handshake, DNS lookup hoặc connection pool usage.
- Tăng tải CPU và memory ở Authorization Server/CDN/proxy.
- Cache stampede khi nhiều request đồng thời cần refresh.
- Tăng latency của request hợp lệ trong cùng thời điểm.
- Làm các hệ thống khác dùng chung JWKS endpoint bị ảnh hưởng.

Hành vi refresh cụ thể phụ thuộc phiên bản Spring Security, Nimbus JOSE + JWT, JWK Set cache và HTTP cache. Không giả định rằng mọi unknown `kid` chắc chắn tạo một fetch riêng, cũng không giả định cache hiện tại luôn chặn được mọi đợt refresh. Hãy đo trên đúng dependency version và cấu hình đang triển khai.

### 2.2. Nhiều issuer

Một Resource Server có thể nhận token từ nhiều Authorization Servers, ví dụ các tenant hoặc hệ thống liên kết:

~~~text
Issuer A -> metadata A -> JWKS A -> decoder A
Issuer B -> metadata B -> JWKS B -> decoder B
Issuer C -> metadata C -> JWKS C -> decoder C
~~~

Mỗi issuer có thể cần:

- Discovery metadata riêng.
- JWKS URI và cache riêng.
- Signing keys/algorithms riêng.
- Audience và token validators riêng.
- Connection pool, timeout và metrics riêng.
- Trust policy và lifecycle riêng.

Nếu hệ thống cho phép issuer tùy ý xuất hiện trong token rồi tự động discovery, attacker có thể gửi nhiều `iss` khác nhau. Một resolver thiết kế không an toàn có thể tạo outbound requests hoặc manager/cache entries không giới hạn.

### 2.3. Token ngẫu nhiên

“Token ngẫu nhiên” không phải một trường hợp duy nhất. Cần phân loại:

| Dạng input | Chi phí có thể phát sinh |
|---|---|
| Không có token | Bearer authentication challenge; thường không cần JWKS/introspection |
| Header không phải Bearer | Không được bearer resolver xử lý |
| Bearer string sai grammar | Resolver từ chối sớm |
| JWT compact format malformed | Parser từ chối trước bước xác minh chữ ký |
| JWT parse được, `kid` ngẫu nhiên | Có thể kích hoạt key lookup/refresh |
| JWT parse được, issuer lạ | Có thể kích hoạt issuer resolution nếu cấu hình động |
| JWT có key đúng nhưng chữ ký sai | Tải public key nếu chưa cache, sau đó verify thất bại |
| Opaque token ngẫu nhiên | Có thể tạo introspection call nếu không bị giới hạn/cache |
| Token hợp lệ nhưng thiếu scope | Authentication thành công; authorization từ chối |

Một cuộc kiểm thử tải phải tạo đúng loại input cần đo. Gửi chuỗi `not-a-jwt` không kiểm tra được chi phí của unknown `kid`, vì parser có thể từ chối trước khi truy cập JWKS.

## 3. Phân biệt malformed JWT với unknown `kid`

Đây là một khác biệt quan trọng khi điều tra tăng tải.

### 3.1. Malformed JWT thường bị từ chối trước khi tải JWKS

Ví dụ:

~~~http
Authorization: Bearer not-a-jwt
~~~

Chuỗi này không phải compact JWT có cấu trúc hợp lệ. Decoder có thể từ chối ngay ở bước parse, trước khi cần tìm signing key.

### 3.2. JWT có cấu trúc hợp lệ nhưng `kid` lạ đi xa hơn

Một JWT compact có ba phần header, payload và signature hợp lệ về cú pháp có thể có header:

~~~json
{
  "alg": "RS256",
  "kid": "attacker-generated-random-kid",
  "typ": "JWT"
}
~~~

Payload có thể chứa claims giả, và chữ ký có thể sai. Decoder vẫn có thể phải chọn key theo `kid` trước khi có thể kết luận chữ ký không hợp lệ. Nếu key không tìm thấy trong cache, JWK source có thể refresh JWKS.

**Không cần attacker có private key hợp lệ để tạo input kích hoạt key-selection path.** Điều attacker cần là một token có cấu trúc đủ để decoder đi tới bước chọn key.

### 3.3. `kid` là dữ liệu chưa xác minh

Không tin `kid` chỉ vì nó nằm trong JWT header. Trước khi chữ ký được xác minh:

- `kid` có thể do bất kỳ ai tạo.
- `alg` có thể do attacker chọn.
- `iss` trong payload chưa phải issuer đã xác minh.
- Các header `jku`/`x5u` không được phép tự quyết định nguồn khóa.

Resource Server chỉ được lấy keys từ JWKS URI gắn với issuer đã được cấu hình tin cậy. Không tải URL tùy ý do token cung cấp.

### 3.4. Không tắt signature verification để giảm tải

Một cách xử lý sai là bỏ qua chữ ký, chỉ đọc `iss`, `sub`, `scope` hoặc `kid` rồi tạo principal. Điều đó biến token giả thành credential có thể được chấp nhận.

Cần tối ưu đường xác minh, cache và network access; không bỏ qua cryptographic validation.

## 4. Unknown `kid` có thể tạo JWKS refresh amplification

### 4.1. Luồng key selection

~~~text
JWT header.kid
      |
      v
JwtDecoder / Nimbus JWK source
      |
      v
JWK Set cache
      |
      +-- Có key phù hợp
      |       |
      |       v
      |   Verify signature
      |
      +-- Không có key phù hợp
              |
              v
        Có thể tải lại JWKS
              |
              v
        Tìm key lần nữa
              |
              +-- Có -> verify signature
              |
              +-- Không -> reject token
~~~

Refresh là cần thiết khi Authorization Server vừa công bố key mới. Nhưng nếu mỗi request có một `kid` khác nhau, server có thể liên tục đi vào nhánh refresh tùy behavior của JWK source.

### 4.2. Cache hit không có nghĩa mọi unknown `kid` đều rẻ

Cache JWKS giúp tránh tải key set thường xuyên, nhưng có hai loại lookup khác nhau:

- **Cache hit có key phù hợp:** decoder lấy public key đã có và xác minh chữ ký.
- **Cache hit nhưng không có key phù hợp:** decoder biết key chưa có trong JWK Set; implementation có thể thử refresh để phát hiện key mới.

Đây là lý do chỉ đo cache hit rate chung có thể không đủ. Cần phân biệt:

- Key found in cached JWKS.
- Unknown `kid`.
- JWKS refresh attempted.
- Refresh succeeded/failed.
- Key found after refresh.
- Unknown `kid` vẫn không có sau refresh.

Nếu library không phát sẵn các metric chi tiết này, có thể instrument HTTP client/JWK retrieval layer hoặc test stub để đếm requests.

### 4.3. Ví dụ amplification

Giả sử một API nhận 1.000 requests/giây. Nếu 10% là JWT có `kid` chưa biết và mỗi request trong nhóm đó gây một JWKS fetch, JWKS endpoint có thể nhận tới 100 requests/giây từ một Resource Server.

Đây là **ví dụ giả định để minh họa**, không phải benchmark hoặc cam kết behavior của Nimbus. Con số thực tế phụ thuộc cache, concurrency, refresh policy và phiên bản thư viện.

Với nhiều replicas:

~~~text
API replica A ----+
API replica B ----+---- JWKS endpoint
API replica C ----+
API replica D ----+
~~~

Mỗi replica có thể giữ cache riêng. Một đợt token `kid` mới hoặc random `kid` có thể tạo tải cộng dồn trên JWKS endpoint.

## 5. Cache stampede khi nhiều request cùng gặp key lạ

Cache stampede xảy ra khi nhiều requests đồng thời phát hiện cache miss và cùng thực hiện một thao tác tải lại.

~~~text
Request 1 ----+
Request 2 ----+
Request 3 ----+---- cache miss ---- JWKS fetch
Request 4 ----+
Request 5 ----+
~~~

Nếu không có cơ chế coalesce/single-flight phù hợp, nhiều request có thể cùng tải một JWKS document giống nhau.

Tác động:

- Một sự kiện key rotation tạo spike traffic.
- Network connection pool bị chiếm.
- AS/CDN bị tăng tải.
- Request latency tăng.
- Retry từ client có thể khuếch đại spike.
- Nhiều replicas cùng refresh làm tải tăng theo số instances.

### 5.1. Single-flight refresh

Một chiến lược hữu ích là chỉ cho một thao tác refresh cùng issuer/JWKS URI diễn ra tại một thời điểm trong một process:

~~~text
N requests thấy unknown kid
          |
          v
     Refresh coordinator
          |
          +-- Request đầu tiên bắt đầu fetch JWKS
          |
          +-- Requests còn lại chờ kết quả fetch đó
          |
          v
     Cùng dùng kết quả mới
~~~

Cách triển khai cụ thể phụ thuộc JWK source/cache library và version. Không giả định `NimbusJwtDecoder` tự cung cấp một distributed single-flight coordinator cho mọi deployment.

Nếu nhiều replicas cùng chạy, single-flight in-memory chỉ coalesce trong từng process. Có thể cần cache/shared coordination ở tầng HTTP client, gateway, proxy hoặc key-distribution service.

### 5.2. Shared cache và cache namespace

Một shared cache có thể giảm số lần mỗi replica tải JWKS, nhưng phải tách namespace chính xác:

~~~text
jwks:{issuer-A}:{jwks-uri-A}
jwks:{issuer-B}:{jwks-uri-B}
~~~

Không dùng riêng `kid` làm cache key. Hai issuers có thể dùng cùng `kid` nhưng public key khác nhau.

Cache entry nên gắn với issuer/JWKS URI đã được tin cậy. Khi đổi issuer hoặc endpoint, không tái sử dụng cache cũ chỉ vì key ID trùng.

### 5.3. Jitter và refresh coordination

Nếu mọi replica khởi động cùng lúc hoặc cùng TTL, chúng có thể refresh đồng thời. TTL jitter hoặc pre-warm có thể phân tán tải theo thời gian.

Ví dụ chiến lược vận hành:

- Khởi động replicas theo rolling deployment.
- Pre-warm JWKS cache sau khi cấu hình issuer.
- Tránh TTL giống nhau cho mọi cache khi có thể kiểm soát.
- Dùng connection pooling và giới hạn concurrent outbound fetches.
- Coalesce refresh cùng issuer.
- Không retry đồng loạt khi JWKS endpoint vừa phục hồi.

Không tự sửa TTL theo cảm tính: phải cân bằng freshness, key rotation SLA và khả năng chịu outage.

## 6. Unknown `kid` và negative caching

Một chiến lược có thể cân nhắc là **negative caching**: ghi nhớ ngắn hạn rằng một `kid` cụ thể không tồn tại trong JWKS vừa tải.

Ví dụ:

~~~text
issuer-A + kid=random-123
    |
    v
JWKS refresh
    |
    v
Không có key
    |
    v
Negative cache entry ngắn hạn
    |
    v
Request lặp lại cùng kid -> reject nhanh
~~~

### 6.1. Lợi ích

- Giảm việc lặp lại cùng một lookup/refresh.
- Có ích khi bot gửi lại cùng token hoặc cùng `kid`.
- Giảm tải JWKS endpoint trong một số kiểu retry.

### 6.2. Rủi ro

Nếu attacker tạo mỗi request một `kid` mới, negative cache có thể bị lấp đầy bởi các entry không hữu ích.

Nếu cache không giới hạn kích thước, chính negative cache trở thành vector DoS qua memory exhaustion.

Nếu TTL quá dài, key hợp lệ vừa được AS công bố có thể bị xem là unknown tới khi negative entry hết hạn.

### 6.3. Quy tắc nếu tự triển khai

- Giới hạn kích thước cache.
- Dùng TTL ngắn.
- Namespace theo issuer/JWKS URI.
- Không lưu raw access token.
- Có eviction policy.
- Có giới hạn số lượng unknown `kid` mới mỗi khoảng thời gian.
- Xóa/invalidate negative entry khi JWKS refresh thành công và key mới xuất hiện.
- Đo tỷ lệ negative cache hit và eviction.

Negative caching là một optimization cần thiết kế và kiểm thử theo version/stack; không nên giả định nó đã được bật mặc định trong mọi cấu hình Spring Security/Nimbus.

## 7. Cache JWKS trong Spring Security

Spring Security Servlet Resource Server dùng `NimbusJwtDecoder` cho JWT. Decoder lấy JWK Set từ URI cấu hình và có cache để tránh fetch public keys ở mọi request.

Ở các version hiện hành có tài liệu hóa builder cache, có thể truyền Spring `Cache` vào decoder:

~~~java
@Bean
JwtDecoder jwtDecoder(
        CacheManager cacheManager,
        @Value("${app.security.issuer}") String issuer,
        @Value("${app.security.jwk-set-uri}") String jwkSetUri) {

    NimbusJwtDecoder decoder = NimbusJwtDecoder
        .withJwkSetUri(jwkSetUri)
        .cache(cacheManager.getCache("orders-jwks"))
        .build();

    decoder.setJwtValidator(
        JwtValidators.createDefaultWithIssuer(issuer)
    );

    return decoder;
}
~~~

Đây là ví dụ Servlet. Cần giữ các validators cần thiết như issuer, timestamp, audience và token profile của API. Nếu dùng custom `JwtDecoder`, đừng vô tình bỏ validation mà Boot auto-configuration trước đó đã thiết lập.

### 7.1. Cache mặc định và cache tùy chỉnh

Các phiên bản Spring Security hiện hành mô tả `NimbusJwtDecoder` sử dụng cache in-memory mặc định có TTL ngắn (tài liệu Servlet hiện hành nêu khoảng 5 phút). TTL và API có thể thay đổi theo version.

Cache tùy chỉnh hữu ích khi:

- Có nhiều replicas và muốn chia sẻ JWK Set.
- Muốn quản lý TTL tập trung.
- Cần metrics hit/miss/eviction.
- Muốn điều chỉnh cache backend theo hạ tầng.
- Cần quan sát refresh và outage.

Nhưng cache shared không tự giải quyết unknown `kid` flood nếu mỗi request khác nhau vẫn kích hoạt refresh. Cần kiểm tra behavior thực tế của JWK source và có giới hạn refresh phù hợp.

### 7.2. Không cache Authentication theo `kid`

`kid` chỉ định key, không phải token identity. Một key có thể ký hàng triệu tokens khác nhau với scopes/subjects/audiences khác nhau.

Không dùng:

~~~text
cache["orders-signing-key-1"] = authenticated=true
~~~

để quyết định token hợp lệ. Mỗi JWT vẫn cần xác minh chữ ký và claims riêng.

### 7.3. Cache key phải chứa issuer context

Trong multi-issuer system:

~~~text
issuer A / kid=key-1 -> public key A
issuer B / kid=key-1 -> public key B
~~~

Nếu cache chỉ dùng `kid=key-1`, key của issuer A có thể bị dùng nhầm cho issuer B. Luôn gắn cache với issuer/JWKS URI đã cấu hình và trust context tương ứng.

## 8. Key rotation đúng cách để tránh spike tải

Unknown `kid` không phải lúc nào cũng là tấn công. Nó thường xuất hiện khi AS đổi signing key.

### 8.1. Rotation có overlap

Một quy trình rotation bình thường:

~~~text
T0: JWKS chỉ công bố key-A
    AS ký token bằng key-A

T1: JWKS công bố key-A và key-B
    Resource Server có thời gian nhận key-B

T2: AS bắt đầu ký token mới bằng key-B
    Token mới có kid=key-B

T3: Token cũ ký bằng key-A vẫn còn hiệu lực
    JWKS giữ key-A trong overlap window

T4: Token-A đã hết hạn + clock skew
    AS gỡ key-A theo chính sách
~~~

Nếu AS bắt đầu ký bằng key-B trước khi công bố key-B, Resource Server có thể nhận một đợt unknown `kid` hợp lệ và refresh liên tục.

### 8.2. Pre-publish và warm-up

Để giảm spike:

1. Công bố key mới trong JWKS trước.
2. Chờ thời gian đủ để cache/replicas nhận key.
3. Kiểm tra JWKS từ network path của Resource Server.
4. Sau đó mới bắt đầu ký token bằng key mới.
5. Giữ key cũ cho tới khi token cũ hết hạn cộng clock skew và overlap cần thiết.
6. Theo dõi unknown `kid` và refresh rate trong rollout.

Có thể pre-warm decoder/cache trong deployment hoặc readiness phase, nhưng phải kiểm soát startup dependency. Không làm toàn bộ replicas cùng lúc gây spike tới AS.

### 8.3. Xử lý key compromise khẩn cấp

Nếu private signing key bị compromise, giữ key cũ trong JWKS để tránh 401 có thể không còn phù hợp. Cần quy trình khẩn cấp:

- Ngừng ký bằng key bị compromise.
- Gỡ/deny key theo policy của AS.
- Làm mới hoặc invalidate JWKS cache trên Resource Servers.
- Xem xét token lifetime, revocation và deny-list theo khả năng AS.
- Xác định các instances vẫn giữ public key cũ trong cache.
- Theo dõi token ký bằng key cũ.
- Phối hợp giữa AS và tất cả APIs dùng chung issuer.

Một cache TTL dài có thể khiến public key cũ tiếp tục được dùng sau khi AS đã gỡ key. Đây là trade-off giữa availability và tốc độ phản ứng khi compromise.

## 9. Multi-issuer: giới hạn trust trước khi tạo decoder

### 9.1. Không discovery từ issuer tùy ý

Một thiết kế nguy hiểm:

~~~text
1. Parse JWT payload.
2. Đọc iss bất kỳ.
3. Nối iss với well-known path.
4. Gọi URL do token quyết định.
5. Tạo decoder/manager mới.
~~~

`iss` trong token chưa được xác minh. Attacker có thể gửi:

- Issuer giả trên domain do họ kiểm soát.
- URL nội bộ hoặc địa chỉ loopback.
- Hostname cloud metadata service.
- Hàng nghìn issuer khác nhau.
- URL gây redirect hoặc DNS rebinding.

Nếu server thực hiện outbound discovery dựa trên input này, nguy cơ gồm SSRF, DNS/network scanning, cache exhaustion và connection pool exhaustion.

### 9.2. Dùng trusted issuer allowlist

Nếu API chỉ chấp nhận một tập issuer đã biết, khai báo rõ:

~~~java
@Bean
AuthenticationManagerResolver<HttpServletRequest>
trustedIssuerResolver() {

    return JwtIssuerAuthenticationManagerResolver.fromTrustedIssuers(
        "https://login-a.example.com/issuer",
        "https://login-b.example.com/issuer",
        "https://login-c.example.com/issuer"
    );
}
~~~

Gắn resolver vào Servlet Resource Server:

~~~java
@Bean
SecurityFilterChain apiSecurity(
        HttpSecurity http,
        AuthenticationManagerResolver<HttpServletRequest> trustedIssuerResolver)
        throws Exception {

    return http
        .authorizeHttpRequests(auth -> auth
            .anyRequest().authenticated()
        )
        .oauth2ResourceServer(oauth2 -> oauth2
            .authenticationManagerResolver(trustedIssuerResolver)
        )
        .build();
}
~~~

Các imports chính gồm:

~~~java
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.security.authentication.AuthenticationManagerResolver;
import org.springframework.security.oauth2.server.resource.authentication.JwtIssuerAuthenticationManagerResolver;
~~~

Allowlist giúp giới hạn issuer mà resolver có thể tin. Mỗi issuer vẫn cần validation audience, signature, time, algorithm và token profile phù hợp.

### 9.3. Không dùng `iss` chưa xác minh làm tenant authorization

Resolver có thể cần đọc issuer claim chưa xác minh để chọn manager. Điều đó chỉ là bước định tuyến tới một manager đã được cấu hình tin cậy; **không phải xác thực issuer thành công**.

Sau khi chọn manager, JWT decoder vẫn phải verify signature và claim `iss` theo issuer cụ thể.

Không dùng `iss` chưa xác minh để:

- Cấp quyền tenant.
- Chọn database tenant không giới hạn.
- Tạo account hoặc user record.
- Chấp nhận audience.
- Gọi arbitrary endpoint.

### 9.4. Dynamic issuer registry phải có giới hạn

Một số hệ thống multi-tenant cần onboarding issuer động. Khi đó:

- Issuer phải được đăng ký và phê duyệt trước.
- Registry lưu canonical issuer và metadata/JWKS URL đã xác minh.
- Có giới hạn số issuer active.
- Cache manager/decoder phải có eviction hoặc lifecycle rõ.
- Không tạo manager mới cho mỗi token lạ.
- Không tự động tin issuer chỉ vì tenant gửi URL.
- Có quy trình disable issuer và invalidate cache.
- Tách credentials/network policy theo issuer khi cần.

Nếu issuer registry cho phép không giới hạn tenant đăng ký, chi phí manager, decoder, cache và connection có thể tăng theo số tenant.

## 10. Multi-issuer cache và connection management

Với mỗi issuer, Resource Server có thể cần:

- Metadata cache.
- JWK Set cache.
- `JwtDecoder`/`AuthenticationManager`.
- HTTP client connection pool.
- Metrics và failure state.
- Audience/token validators.

Ví dụ 100 issuers có thể tạo 100 trust contexts độc lập. Không nhất thiết tất cả đều hoạt động đồng thời, nhưng cache/connection footprint cần được đo.

### 10.1. Không chia sẻ JWK cache giữa issuers

Cache namespace nên bao gồm issuer hoặc JWKS URI:

~~~text
jwks:{canonical-issuer}:{jwks-uri}
~~~

Không dùng cache key chỉ là `kid` hoặc algorithm.

### 10.2. Giới hạn issuer manager cache

Nếu resolver tạo manager theo issuer động, hãy xem xét:

- Maximum number of managers.
- Idle eviction.
- TTL theo tenant lifecycle.
- Single-flight manager creation.
- Duplicate discovery suppression.
- Cleanup connection/cache khi issuer bị disable.
- Metrics manager count và cache size.

Không tạo `JwtDecoder` mới cho mỗi request. Decoder và manager nên được tái sử dụng theo issuer đã đăng ký.

### 10.3. Tách timeout và concurrency theo dependency

Một issuer chậm không nên chiếm hết outbound resources dùng cho issuer khác. Có thể tách connection pools hoặc concurrency budgets theo dependency/issuer group khi tải đủ lớn.

Giữ tổng số outbound requests bounded. Retry cần có giới hạn, backoff và jitter; không retry vô hạn các lỗi 401/403 hoặc unknown key.

## 11. Opaque token ngẫu nhiên có thể gây introspection flood

Với opaque token, Resource Server thường không thể tự xác minh token offline. Nó gọi introspection endpoint:

~~~text
Authorization: Bearer opaque-random-token
              |
              v
OpaqueTokenAuthenticationProvider
              |
              v
Reactive/Servlet OpaqueTokenIntrospector
              |
              v
POST /introspect
              |
              v
Authorization Server
              |
              v
active=false
~~~

Nếu API nhận 5.000 opaque token ngẫu nhiên mỗi giây và không có cache/rate limit, AS có thể nhận gần 5.000 introspection calls/giây từ API đó. Đây là phép tính minh họa: tải thực tế phụ thuộc cache, concurrency, retries và cách introspector hoạt động.

### 11.1. Bảo vệ introspection endpoint

- Resource Server phải xác thực client bằng method được AS cho phép.
- Chỉ cấp quyền introspect cần thiết cho API.
- Dùng TLS và kiểm tra server certificate.
- Đặt connect/read timeout ngắn theo SLO.
- Giới hạn concurrent requests.
- Dùng connection pool có giới hạn.
- Áp dụng rate limit theo client/resource server ở gateway hoặc AS.
- Theo dõi latency, 401/403 client auth, 5xx và timeout.
- Không fail open khi introspection endpoint lỗi.

### 11.2. Cache active và inactive response

Introspection response có thể được cache, nhưng TTL ảnh hưởng trực tiếp tới revocation freshness.

- Cache `active=true`: giảm tải AS nhưng token bị revoke có thể tiếp tục được chấp nhận tới khi cache hết hạn.
- Cache `active=false`: giảm tải khi cùng token invalid bị gửi lặp lại, nhưng TTL dài có thể làm chậm việc chấp nhận token vừa được cấp hoặc token state vừa thay đổi.
- Không cache response lỗi mạng như thể token inactive hoặc active; đó là dependency failure khác với token state.
- Cache key phải được tạo an toàn từ token và gắn với introspection endpoint/resource context.
- Giới hạn kích thước và TTL để tránh memory exhaustion.

Negative caching hữu ích nhất khi cùng token bị gửi lặp lại. Với mỗi request một token ngẫu nhiên mới, rate limit và concurrency limit quan trọng hơn.

### 11.3. Opaque token không có `kid`

Opaque token không dùng `kid` để chọn JWK, nhưng vẫn có thể tạo tải tương tự ở tầng introspection. Đừng áp dụng giải pháp unknown `kid` cho opaque token; hãy instrument introspection path riêng.

## 12. Rate limiting: chặn tải trước khi nó tới AS/JWKS

Rate limiting nên được áp dụng ở một hoặc nhiều tầng:

1. CDN/WAF/API gateway.
2. Ingress/load balancer.
3. Application filter trước bước authentication tốn network.
4. JWK/introspection outbound client.
5. Authorization Server endpoint.

### 12.1. Rate limit trước authentication

Request chưa xác thực không có user ID đáng tin để rate limit theo principal. Có thể dùng:

- Source IP hoặc network identity đã được proxy tin cậy cung cấp.
- Connection/client certificate nếu TLS layer xác minh.
- Route/API key hoặc gateway client metadata có integrity.
- Global budget cho anonymous traffic.
- Per-tenant/client budget sau khi xác định được identity đáng tin.

Cẩn thận với IP NAT: nhiều users hợp lệ có thể dùng chung một IP. Rate limit quá chặt theo IP có thể chặn traffic thật.

### 12.2. Tách budget theo loại chi phí

Không chỉ đặt một request rate chung. Có thể cần budget riêng:

| Budget | Mục tiêu |
|---|---|
| Inbound request rate | Giới hạn tổng request tới API |
| Invalid bearer rate | Giảm token flood |
| Unknown issuer rate | Giảm discovery/manager lookup |
| Unknown `kid` refresh rate | Bảo vệ JWKS endpoint |
| JWKS outbound concurrency | Giới hạn key fetch đồng thời |
| Introspection concurrency | Bảo vệ AS token endpoint |
| Per-issuer connection budget | Tránh một issuer chiếm toàn bộ pool |

Nếu một request có thể kích hoạt nhiều outbound calls, rate limit ở tầng ngoài cùng có hiệu quả nhất.

### 12.3. Rate limit không thay thế token validation

Một request được rate limiter cho phép vẫn phải đi qua:

- Signature verification.
- Issuer/audience/time validators.
- Token profile validation.
- Scope/authority authorization.
- Tenant và object-level authorization.

Không cho request qua chỉ vì nó nằm dưới rate limit.

### 12.4. Response khi bị rate limit

Gateway có thể trả:

~~~http
HTTP/1.1 429 Too Many Requests
Retry-After: 10
~~~

Đây là response của rate limiting policy, khác với `401 invalid_token`. Client cần hiểu `429` là vượt request budget, không nhất thiết token sai.

Không trả `WWW-Authenticate: Bearer error="invalid_token"` cho request chỉ bị rate limit nếu token chưa được xác minh.

## 13. Timeout, retry và circuit breaker cho JWKS/introspection

### 13.1. Timeout

Đặt timeout cho:

- DNS/connect.
- TLS handshake.
- Response/read.
- Tổng thời gian dependency call.
- Pool acquisition.
- Retry budget.

Timeout phải nằm trong latency budget của API. Một timeout 30 giây có thể không phù hợp nếu API có SLO 200 ms.

### 13.2. Retry có giới hạn

Chỉ retry lỗi transient phù hợp:

- Connection reset.
- Temporary network failure.
- HTTP 502/503/504 nếu policy cho phép.

Không retry vô hạn:

- Unknown `kid` sau khi đã refresh JWKS mà key vẫn không tồn tại.
- Signature invalid.
- Issuer/audience mismatch.
- Introspection client 401/403.
- Token inactive.

Dùng backoff, jitter và tổng deadline. Retry cùng lúc trên mọi replicas có thể tạo retry storm.

### 13.3. Circuit breaker

Circuit breaker có thể ngăn ứng dụng tiếp tục tạo tải tới JWKS/introspection endpoint đang lỗi.

~~~text
CLOSED
  |
  | failures vượt ngưỡng
  v
OPEN
  |
  | tạm ngừng outbound calls
  v
HALF-OPEN
  |
  +-- dependency phục hồi -> CLOSED
  |
  +-- tiếp tục lỗi ------> OPEN
~~~

Khi circuit mở:

- Token có key hợp lệ trong cache vẫn có thể được xác minh theo policy.
- Token cần key mới mà không lấy được key thì phải bị từ chối.
- Opaque token không có kết quả introspection cache hợp lệ thì không thể được xác nhận.
- Không tạo principal mặc định hoặc coi dependency timeout là `active=true`.

Cần phân biệt authentication failure với dependency outage trong monitoring và error handling. Tùy kiến trúc, lỗi dependency có thể cần trả 503 thay vì giả định token invalid; không làm thay đổi fail-closed decision.

## 14. Không để unknown issuer trở thành SSRF

Issuer trong JWT payload chưa xác minh. Nếu ứng dụng tạo metadata URL từ giá trị `iss` do request gửi, attacker có thể điều khiển outbound request.

Ví dụ input nguy hiểm:

~~~json
{
  "iss": "http://127.0.0.1:8080/admin"
}
~~~

Hoặc issuer trỏ tới hostname nội bộ/metadata service.

Biện pháp:

- Dùng allowlist issuer canonical.
- Không fetch arbitrary metadata/JWKS URI từ untrusted token.
- Không tin `jku` hoặc `x5u` trong JWT header để lấy signing key.
- Chặn loopback, link-local, private network và redirect ngoài policy ở tầng egress.
- Không cho tenant tự đăng ký URL issuer mà không có quy trình phê duyệt.
- Dùng DNS/network egress policy để bổ sung lớp bảo vệ.
- Kiểm tra exact issuer equality sau khi decoder xác minh chữ ký.
- Giới hạn cache/manager count nếu issuer registry có tính động.

Allowlist ở application và egress control ở network là hai lớp bổ sung cho nhau.

## 15. Quan sát tải: metric nào giúp tìm đúng nguyên nhân?

Không chỉ nhìn CPU hoặc số lượng 401. Hãy theo dõi:

### 15.1. JWT/JWKS

| Metric/event | Ý nghĩa |
|---|---|
| `jwt_requests_total` | Tổng JWT authentication attempts |
| `jwt_parse_failures_total` | Token malformed trước verify |
| `jwt_unknown_kid_total` | Token có key ID không tìm thấy |
| `jwks_fetch_total` | Số lần tải JWKS |
| `jwks_fetch_duration` | Latency tải key set |
| `jwks_fetch_failures_total` | Lỗi HTTP/DNS/TLS/timeout |
| `jwks_cache_hits_total` | Cache phục vụ được key |
| `jwks_cache_misses_total` | Cần tìm key/refresh |
| `jwks_refresh_after_unknown_kid_total` | Refresh do không tìm thấy key |
| `jwt_signature_failures_total` | Key được tìm nhưng signature invalid |
| `jwt_issuer_rejected_total` | Issuer không được chấp nhận |
| `jwt_audience_rejected_total` | Audience không đúng |

Tên metric là gợi ý instrumentation; không khẳng định Spring Security tự phát mọi metric này.

### 15.2. Multi-issuer

- Unknown issuer count.
- Issuer manager creation count.
- Active decoder/manager count.
- Metadata fetch rate.
- Per-issuer JWKS fetch rate.
- Cache size/eviction.
- Per-issuer authentication latency.
- Issuer disabled/rejected events.

### 15.3. Opaque/introspection

- Introspection requests per second.
- Active/inactive response counts.
- Introspection p50/p95/p99 latency.
- Timeout/5xx rate.
- Client authentication 401/403.
- Cache hit/miss.
- Concurrent introspection calls.
- Response parsing failures.

### 15.4. Tránh metric cardinality cao

Không đưa các giá trị sau làm metric labels không giới hạn:

- Raw token.
- `kid` tùy ý từ attacker.
- `iss` tùy ý.
- Username/email/subject.
- URL tùy ý do request cung cấp.

Thay vào đó:

- Dùng issuer ID từ registry đã phê duyệt.
- Nhóm lỗi theo loại.
- Log `kid` đã truncate/hash khi cần điều tra.
- Giới hạn sample cho unknown values.
- Dùng counters/histograms không có label attacker-controlled.

Nếu mỗi `kid` ngẫu nhiên trở thành một label, metrics backend có thể bị cardinality DoS.

## 16. Kiểm thử unknown `kid` và cache behavior

Test phải tạo JWT có cấu trúc hợp lệ với `kid` chưa có trong JWKS. Một chuỗi malformed không đủ để kiểm tra refresh behavior.

### 16.1. JWKS stub có request counter

Dùng mock HTTP server để trả JWK Set và đếm số lần GET:

~~~text
Test JWKS server
  GET /jwks
    -> counter++
    -> return current JWK Set
~~~

Test cases:

1. Token ký bằng key đang có trong JWKS.
2. Gửi nhiều token khác nhau cùng `kid` hợp lệ.
3. Gửi token có `kid` không tồn tại.
4. Gửi nhiều token với các `kid` ngẫu nhiên khác nhau.
5. Gửi nhiều request đồng thời với cùng unknown `kid`.
6. Thêm key mới vào JWKS.
7. Gửi token ký bằng key mới.
8. Gỡ key cũ sau overlap và kiểm tra token cũ.
9. Làm JWKS endpoint timeout/503.
10. Xác nhận không có request nào tới URL từ `jku`/`x5u` do token cung cấp.

Đếm JWKS fetch và latency theo từng trường hợp. Kết quả phụ thuộc Nimbus/Spring Security version; test này giúp biết đúng behavior của dependency đang dùng.

### 16.2. Test cache stampede

~~~text
1. Clear JWKS cache.
2. Chuẩn bị một token với unknown kid.
3. Phát N requests đồng thời.
4. Đếm số JWKS fetch.
5. Đo p95/p99 request latency.
6. Lặp lại trên nhiều application instances.
~~~

So sánh:

- Một instance, cache in-memory.
- Một instance, refresh coordination.
- Nhiều instances với cache riêng.
- Nhiều instances với shared cache/coalescing nếu kiến trúc hỗ trợ.

Không chỉ kiểm tra HTTP response 401; mục tiêu của test là đo outbound amplification.

### 16.3. Test key rotation hợp lệ

- JWKS ban đầu có key A.
- Công bố thêm key B.
- Chờ cache propagation theo policy.
- Phát token ký bằng B.
- Xác nhận request hợp lệ không tạo spike refresh kéo dài.
- Giữ token A trong overlap và xác minh vẫn hoạt động.
- Gỡ A sau khi token A hết hạn theo policy.

## 17. Kiểm thử multi-issuer và issuer lạ

Test matrix:

| Token | Kỳ vọng |
|---|---|
| Issuer A đã allowlist, chữ ký/audience đúng | Được xác thực |
| Issuer B đã allowlist, chữ ký/audience đúng | Được xác thực theo decoder B |
| Issuer chưa allowlist | Từ chối, không discovery arbitrary URL |
| Issuer giả là loopback/private IP | Từ chối, không outbound request |
| Issuer A nhưng key từ issuer B | Signature/issuer validation thất bại |
| Issuer A và B cùng `kid` | Chọn đúng key theo issuer namespace |
| Issuer A bị disable | Không tạo authentication manager mới |
| Hàng nghìn issuer ngẫu nhiên | Không tăng manager/cache không giới hạn |
| Metadata endpoint A timeout | Chỉ ảnh hưởng trust path A theo policy |
| JWKS A lỗi | Không làm cache/manager B bị ghi đè |

Một test quan trọng là dùng HTTP stub để đếm outbound requests. Với issuer lạ, kỳ vọng số lần discovery/JWKS call là **0** khi issuer allowlist không chấp nhận nó.

## 18. Kiểm thử opaque token flood

Với opaque token, dùng introspection stub:

~~~text
POST /introspect
  count++
  token=random-token
  -> {"active": false}
~~~

Test:

- Cùng một inactive token lặp lại.
- Nhiều token random khác nhau.
- Introspection latency tăng.
- Introspection endpoint timeout/503.
- Client authentication sai.
- Concurrency đạt giới hạn.
- Cache active/inactive theo TTL.
- Token vừa revoke nhưng cache active còn hạn.
- Response malformed.
- Một resource server không dùng cache của resource server khác.

Đo số introspection requests trên mỗi inbound request và số concurrent calls tối đa. Xác nhận hệ thống không fail open khi dependency lỗi.

## 19. Runbook khi thấy JWKS hoặc AS tăng tải

Khi alert báo JWKS/introspection request tăng đột biến:

**Bước 1 — Phân loại traffic.** Xem inbound RPS, tỷ lệ 401, token parse failure, unknown `kid`, unknown issuer và opaque token rate.

**Bước 2 — Kiểm tra key rotation.** Xác nhận AS có vừa publish key mới, đổi `kid` hoặc bắt đầu ký bằng key mới không.

**Bước 3 — So sánh JWKS.** Kiểm tra `kid` trong token hợp lệ có xuất hiện trong JWKS hay không; so sánh từ network path của từng replica.

**Bước 4 — Kiểm tra cache.** Xem hit/miss, refresh count, TTL, eviction và sự khác biệt giữa replicas.

**Bước 5 — Kiểm tra issuer.** Xem có token từ issuer chưa allowlist hoặc issuer values ngẫu nhiên không.

**Bước 6 — Kiểm tra introspection.** Xác định opaque token flood, latency AS, client auth errors và cache behavior.

**Bước 7 — Giới hạn outbound.** Áp concurrency, timeout, rate limit và circuit breaker phù hợp. Không tăng retry để chữa outage.

**Bước 8 — Bảo toàn validation.** Không tắt signature, issuer, audience hoặc active checks để giảm tải.

**Bước 9 — Phối hợp AS.** Xác nhận rotation, key compromise, endpoint health và rate limiting phía AS.

**Bước 10 — Theo dõi phục hồi.** Kiểm tra JWKS fetch rate, introspection RPS, p95/p99 và tỷ lệ token hợp lệ sau khi thay đổi.

## 20. Cấu hình vận hành minh họa

Một cấu hình JWT cơ bản:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.com/realms/orders
          jwk-set-uri: https://login.example.com/realms/orders/protocol/openid-connect/certs
          audiences:
            - orders-api
~~~

Các giá trị là ví dụ. Trong môi trường thực:

- Dùng issuer/JWKS URI đúng environment.
- Giữ issuer và audience validation.
- Đặt HTTP connect/read timeout phù hợp cho JWKS retrieval theo API của version đang dùng.
- Chọn cache TTL theo key rotation SLA.
- Instrument fetch và cache.
- Giới hạn outbound network tới host đã phê duyệt.

Đối với nhiều issuer, dùng resolver allowlist thay vì suy ra trust từ mọi `iss` xuất hiện trong token.

Đối với opaque token, cấu hình introspection URI và client credentials riêng cho Resource Server; bổ sung timeout, connection pool, rate limit và cache theo revocation policy.

## 21. Cân bằng hiệu năng, availability và security

| Quyết định | Tăng hiệu năng | Rủi ro cần kiểm soát |
|---|---|---|
| Cache JWKS lâu hơn | Ít fetch hơn | Key rotation/compromise propagation chậm hơn |
| Cache introspection lâu hơn | Ít gọi AS | Token revoked vẫn có thể được chấp nhận trong TTL |
| Negative cache unknown `kid` | Giảm refresh lặp | Key mới có thể bị từ chối tạm thời; cache có thể bị lấp |
| Shared JWKS cache | Giảm fetch giữa replicas | Cache isolation/availability và issuer namespace |
| Single-flight refresh | Giảm cache stampede | Các request chờ chung một refresh chậm |
| Rate limit inbound | Giảm tải backend | Có thể chặn client hợp lệ nếu key phân loại sai |
| Circuit breaker | Bảo vệ dependency khi outage | Token cần key mới/opaque không cache sẽ không xác minh được |
| Dynamic issuer registry | Hỗ trợ onboarding linh hoạt | Cache/manager growth và SSRF nếu không kiểm soát |
| Pre-warm JWKS | Giảm cold-start latency | Startup có thể phụ thuộc AS nếu làm đồng bộ |

Không có một TTL hoặc rate limit phù hợp mọi hệ thống. Hãy chọn dựa trên:

- Access token maximum lifetime.
- Key rotation interval và overlap.
- Revocation SLA.
- Số issuers.
- Số application replicas.
- Inbound RPS và invalid-token ratio.
- AS/JWKS capacity.
- API latency SLO.
- Network failure model.

## 22. Những anti-pattern cần tránh

**Refresh JWKS vô hạn cho mọi unknown `kid`.** Có thể tạo amplification; cần đo refresh behavior và giới hạn outbound.

**Tạo decoder cho mọi issuer token gửi lên.** Có thể tạo SSRF, unbounded manager cache và metadata flood.

**Dùng `kid` làm cache key global.** Cùng `kid` ở hai issuer không có nghĩa cùng public key.

**Dùng `iss` chưa xác minh làm tenant identity.** Issuer chỉ được tin sau khi token được verify theo manager đã được allowlist.

**Tắt signature validation khi JWKS chậm.** Điều đó biến token giả thành credential.

**Cache `authenticated=true` theo `kid`.** Một key ký nhiều token có claims khác nhau; từng token phải được xác minh.

**Cache introspection không có TTL.** Token revoke có thể tiếp tục được chấp nhận vô thời hạn.

**Cache unknown `kid` không giới hạn.** Attacker có thể làm đầy memory bằng các giá trị ngẫu nhiên.

**Retry mọi lỗi không giới hạn.** Có thể tạo retry storm và làm AS/JWKS outage nặng hơn.

**Dùng một connection pool không giới hạn cho mọi issuer.** Một issuer chậm có thể chiếm tài nguyên của tất cả issuer.

**Tin `jku`/`x5u` từ JWT header.** Có thể cho attacker điều khiển nguồn public key.

**Chỉ nhìn CPU và 401.** Không thấy JWKS refresh amplification hoặc introspection flood.

**Dùng raw `kid`, issuer hoặc token làm metrics labels.** Cardinality có thể tăng không giới hạn.

**Trả `active=true` khi introspection timeout.** Đây là fail-open và cho phép token chưa xác minh được đi tiếp.

**Cắt bỏ key cũ ngay khi có key mới.** Token còn hạn ký bằng key cũ có thể bị từ chối ngoài dự kiến.

## 23. Câu hỏi tự kiểm tra

**1.** Vì sao một JWT có `kid` ngẫu nhiên có thể làm tăng tải JWKS?

> Nếu token parse được nhưng key không có trong JWK Set cache, JWK source có thể refresh JWKS để tìm key mới trước khi từ chối token.

**2.** Token `not-a-jwt` có kiểm tra được unknown `kid` behavior không?

> Không. Parser có thể từ chối trước bước chọn key; cần JWT compact có cấu trúc hợp lệ và `kid` chưa tồn tại.

**3.** `kid` có phải dữ liệu đáng tin trước khi xác minh chữ ký?

> Không. Nó là dữ liệu từ JWT header chưa được xác minh, chỉ dùng để chọn key trong JWKS source đã được cấu hình tin cậy.

**4.** Vì sao không nên discovery từ issuer bất kỳ trong token?

> Có thể tạo SSRF, DNS/network scanning, manager cache không giới hạn và metadata request flood.

**5.** `JwtIssuerAuthenticationManagerResolver.fromTrustedIssuers(...)` giúp gì?

> Giới hạn các issuer mà Resource Server có thể chọn manager để xác thực.

**6.** Hai issuer dùng cùng `kid` có thể dùng cùng key không?

> Có thể, nhưng không được giả định. Cache và key selection phải namespace theo issuer/JWKS source.

**7.** Cache JWKS có nghĩa mọi unknown `kid` đều không tạo network request không?

> Không. Cache hit không có key phù hợp có thể kích hoạt refresh tùy implementation/version.

**8.** Cache stampede là gì?

> Nhiều requests cùng phát hiện cache miss và đồng thời thực hiện một thao tác refresh/tải dữ liệu giống nhau.

**9.** Single-flight refresh có tác dụng gì?

> Coalesce nhiều refresh đồng thời cho cùng issuer/JWKS source thành một thao tác chung trong phạm vi coordinator.

**10.** Negative caching unknown `kid` có rủi ro gì?

> Cache có thể bị lấp bởi nhiều `kid` ngẫu nhiên hoặc trì hoãn việc nhận key mới nếu TTL quá dài.

**11.** Opaque token ngẫu nhiên gây tải ở đâu?

> Tại introspection endpoint nếu Resource Server gọi AS cho mỗi token và không có cache/rate limit phù hợp.

**12.** Vì sao introspection cache TTL ảnh hưởng revocation?

> Response active cũ có thể được dùng sau khi AS revoke token cho tới khi cache hết hạn.

**13.** Có nên fail open khi JWKS/introspection endpoint timeout?

> Không. Nếu không thể xác minh token, không được tạo authenticated principal.

**14.** Vì sao cần pre-publish key mới?

> Để Resource Servers nhận public key trước khi AS bắt đầu ký token bằng key đó, giảm unknown-kid spike.

**15.** Vì sao cần giữ key cũ trong overlap?

> Token cũ có thể còn hiệu lực; gỡ key quá sớm làm token hợp lệ bị từ chối.

**16.** Rate limit unknown issuer nên đặt ở đâu?

> Ở ingress/gateway hoặc resolver boundary trước khi discovery/manager creation; chỉ dùng issuer đã allowlist làm identity label.

**17.** Vì sao không đưa `kid` ngẫu nhiên làm metrics label?

> Mỗi giá trị có thể tạo time series mới và gây metrics cardinality exhaustion.

**18.** Test nào chứng minh unknown `kid` refresh behavior?

> Gửi signed/compact JWT có `kid` không tồn tại qua decoder thật và dùng JWKS stub đếm số lần fetch, cả khi request đơn lẻ và burst đồng thời.

## 24. Tài liệu tham khảo

- [Spring Security — Servlet OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): `JwtDecoder`, JWKS, cache và key rotation.
- [Spring Security — Multi-tenancy](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/multitenancy.html): trusted issuer resolver và nhiều authentication managers.
- [Spring Security — AuthenticationManagerResolver API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/AuthenticationManagerResolver.html): chọn authentication manager theo request.
- [Nimbus JOSE + JWT — RemoteJWKSet API](https://javadoc.io/doc/com.nimbusds/nimbus-jose-jwt/latest/com/nimbusds/jose/jwk/source/RemoteJWKSet.html): tải JWK Set từ remote source và cache behavior theo version.
- [RFC 7517 — JSON Web Key](https://www.rfc-editor.org/rfc/rfc7517): JWK, JWK Set và `kid`.
- [RFC 7519 — JSON Web Token](https://www.rfc-editor.org/rfc/rfc7519): JWT structure và registered claims.
- [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414): issuer metadata và `jwks_uri`.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): introspection request/response và `active`.
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): issuer/audience validation, algorithm verification và tránh JWT confusion.
- [Spring Framework — HTTP Clients](https://docs.spring.io/spring-framework/reference/integration/rest-clients.html): cấu hình HTTP clients, timeout và connection behavior.
- [Project Reactor — Context](https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html): Reactor Context nếu triển khai reactive Resource Server.

**Kết luận:** Tải tăng khi gặp `kid` mới, nhiều issuer hoặc token ngẫu nhiên xuất phát từ các đường chi phí khác nhau: JWKS refresh, issuer discovery/manager creation và introspection. Hãy phân biệt malformed token với JWT có `kid` lạ, giới hạn issuer bằng allowlist, namespace cache theo issuer, coalesce refresh, đặt rate limit/concurrency/timeout, quản lý key rotation có overlap và theo dõi outbound calls. Khi không xác minh được chữ ký hoặc trạng thái token, Resource Server phải fail closed; tối ưu hiệu năng không được làm suy yếu trust validation.
