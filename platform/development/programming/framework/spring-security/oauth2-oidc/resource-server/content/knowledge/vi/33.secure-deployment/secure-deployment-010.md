# Chính sách khi discovery, JWKS hoặc introspection không hoạt động

Spring Security Resource Server phụ thuộc vào hạ tầng identity để biết cách xác minh access token. Tùy cấu hình, ứng dụng có thể cần đọc metadata discovery, tải public key từ JWKS hoặc gọi token introspection endpoint. Khi một trong các dịch vụ này không hoạt động, Resource Server phải quyết định request nào vẫn có thể xử lý an toàn, request nào cần bị từ chối và cách phản ánh sự cố cho client.

Ba dependency này có vai trò khác nhau:

- **Discovery** cung cấp metadata về issuer và các endpoint liên quan, chẳng hạn `jwks_uri` hoặc `introspection_endpoint`.
- **JWKS** cung cấp public keys để xác minh chữ ký JWT.
- **Introspection** trả lời trạng thái của một access token, thường gồm `active` và các thuộc tính được phép chia sẻ.

Chính sách vận hành cần phân biệt lỗi cấu hình, token không hợp lệ và identity dependency đang unavailable. Khi không thể xác minh token bằng nguồn tin cậy, protected endpoint phải giữ nguyên nguyên tắc **fail closed**. Cache có thể giúp ứng dụng tiếp tục xác thực trong một khoảng thời gian được kiểm soát, nhưng không được biến thành cơ chế chấp nhận token vô thời hạn.

Bài học thuộc chương **Triển khai an toàn**, tập trung vào discovery/metadata failure, JWKS outage, introspection outage, cache và stale data, hành vi startup/readiness/runtime, timeout/retry/circuit breaker, cấu hình Spring Security, observability, runbook và fault-injection testing.

> **Ngữ cảnh minh họa:** Orders API chạy Spring Boot 3.x / Spring Security 6.x. API có thể xác thực JWT bằng public key từ `https://id.example.com/oauth2/jwks`, hoặc xác thực opaque token qua `https://id.example.com/oauth2/introspect`. Authorization Server công bố metadata tại endpoint discovery. URL trong bài là ví dụ; cấu hình thực tế phải dùng issuer và endpoint đã được xác minh.

## 1. Phân biệt discovery, JWKS và introspection

### 1.1. Discovery cung cấp thông tin cấu hình của issuer

OIDC Discovery và OAuth 2.0 Authorization Server Metadata cho phép client hoặc Resource Server tìm các endpoint và capabilities của issuer. Metadata document có thể công bố:

- `issuer`: định danh issuer.
- `jwks_uri`: nơi lấy JSON Web Key Set.
- `introspection_endpoint`: nơi introspect token nếu issuer hỗ trợ.
- `authorization_endpoint` và `token_endpoint` cho OAuth client flows.
- Các thuật toán ký được hỗ trợ và metadata khác.

Một Resource Server chỉ xác minh JWT có thể cần `issuer` và `jwks_uri`. Một Resource Server dùng opaque token cần introspection endpoint và credentials để gọi endpoint đó. OAuth client có thể cần thêm authorization/token endpoints.

Discovery là bước lấy metadata. Nó không xác minh chữ ký access token và không trả lời token cụ thể còn active hay không.

### 1.2. JWKS cung cấp public key

JWKS là một JSON document chứa các JWK. Với JWT ký bất đối xứng, Resource Server chọn public key phù hợp với protected header và xác minh chữ ký. Sau đó ứng dụng còn phải validate issuer, audience, thời hạn, thuật toán và các điều kiện của access token.

JWKS không chứa trạng thái revoke của từng token. Việc tải được key không có nghĩa token có chữ ký hợp lệ, đúng audience hoặc còn hạn.

### 1.3. Introspection trả trạng thái của token

Với RFC 7662, Resource Server gửi token tới introspection endpoint. Authorization Server có thể trả:

~~~json
{
  "active": true,
  "sub": "alice",
  "scope": "orders.read",
  "aud": ["orders-api"],
  "exp": 2000000600
}
~~~

Trường `active` là tín hiệu cốt lõi. Khi `active` là false, token không được chấp nhận. Khi endpoint timeout hoặc trả lỗi, Resource Server không biết token có active hay không; lỗi dependency không tương đương với `active=false`.

### 1.4. Ba loại cache có mục đích khác nhau

| Cache | Dữ liệu | Giảm chi phí | Rủi ro khi dữ liệu cũ |
|---|---|---|---|
| Discovery metadata cache | Issuer và endpoint metadata | Giảm metadata fetch | Dùng endpoint/key source cũ sau thay đổi cấu hình |
| JWKS cache | Public JWK set hoặc key đã resolve | Giảm fetch và parse key | Key bị gỡ/compromise vẫn có thể được tin đến khi refresh |
| Introspection result cache | Kết quả active và principal attributes của token | Giảm remote calls | Token đã revoke có thể tiếp tục được chấp nhận trong TTL |

Không dùng một TTL chung cho cả ba loại. Metadata, key material và trạng thái token có vòng đời cũng như tác động bảo mật khác nhau.

## 2. Xây dựng chính sách lỗi trước khi triển khai

Chính sách cần trả lời ba câu hỏi cho từng dependency:

1. Có thể tiếp tục xử lý request bằng dữ liệu tin cậy đã cache không?
2. Nếu cần fetch dữ liệu mới nhưng dependency unavailable, request sẽ bị từ chối như thế nào?
3. Khi dependency phục hồi, ứng dụng làm mới cache và trở lại trạng thái bình thường ra sao?

Một ma trận quyết định cơ bản:

| Sự cố | Dữ liệu cache có thể dùng? | Hành vi cho protected endpoint |
|---|---|---|
| Discovery unavailable, metadata tin cậy còn trong cache | Có, trong giới hạn policy | Tiếp tục nếu endpoint/key source đã xác định và các bước xác thực khác thành công |
| Discovery unavailable, không có metadata cần thiết | Không | Không thể khởi tạo trust configuration; báo dependency/configuration failure |
| JWKS unavailable, public key phù hợp còn cache | Có, theo cache policy | Có thể xác minh JWT bằng key đã cache |
| JWKS unavailable, token mang `kid` chưa biết | Không có key để verify | Từ chối; không bỏ qua signature validation |
| Introspection unavailable, active result còn cache | Có, trong TTL được duyệt | Có thể dùng kết quả cache nếu revocation policy cho phép |
| Introspection unavailable, cache miss | Không | Không xác định được trạng thái token; fail closed |
| Introspection trả `active=false` | Không áp dụng | Từ chối token |
| Introspection client credentials sai | Không áp dụng | Fail closed và xử lý như lỗi cấu hình/identity integration |

Bảng này mô tả policy ở mức kiến trúc. HTTP status cuối cùng còn phụ thuộc loại exception, filter chain, entry point và API error contract.

### 2.1. Fail closed không có nghĩa mọi lỗi đều là 401

Fail closed có nghĩa không cấp quyền khi chưa có bằng chứng xác thực đáng tin. Nó không bắt buộc mọi dependency failure phải được báo cho client bằng cùng một status.

Có thể phân biệt:

- Token thiếu, sai chữ ký, hết hạn hoặc inactive: authentication failure, thường là `401 Unauthorized`.
- Authentication hợp lệ nhưng thiếu scope/authority: authorization failure, thường là `403 Forbidden`.
- Identity dependency unavailable khiến server không thể xác định trạng thái token: có thể biểu diễn là `503 Service Unavailable` theo API contract, hoặc qua authentication failure mapping mặc định của framework.
- Server cấu hình sai, chẳng hạn client secret introspection sai: operational/configuration failure cần alert và xử lý nội bộ.

Dù dùng status nào, request không được đi tiếp như một authenticated request khi chưa xác minh thành công.

### 2.2. Không fallback tự động sang cơ chế yếu hơn

Khi JWT decoder không tải được JWKS, không được tự động bỏ qua signature hoặc coi payload JWT là trusted. Khi introspection timeout, không được coi token là active. Không chuyển request protected sang anonymous handler rồi cho phép thao tác.

Nếu kiến trúc hỗ trợ nhiều issuer hoặc nhiều verification methods, việc chọn phương thức phải dựa trên cấu hình tin cậy của ứng dụng, không dựa trên việc phương thức đầu tiên vừa gặp lỗi.

## 3. Discovery không hoạt động

### 3.1. Discovery failure có thể xảy ra ở startup hoặc runtime

Các nguyên nhân phổ biến:

- DNS không phân giải được hostname issuer.
- TLS certificate hết hạn hoặc chain không đáng tin.
- Metadata endpoint timeout hoặc trả HTTP 5xx.
- Metadata JSON malformed hoặc thiếu trường bắt buộc.
- Giá trị `issuer` trong metadata không khớp issuer đã cấu hình.
- Proxy, firewall hoặc network policy chặn kết nối.
- Issuer vừa thay đổi endpoint nhưng metadata cache chưa được refresh.

Discovery có thể được thực hiện lúc khởi tạo decoder/client hoặc khi cần sử dụng, tùy framework version và cách cấu hình. Không giả định mọi ứng dụng Spring Security đều gọi discovery ở cùng một thời điểm.

### 3.2. Cấu hình endpoint tĩnh khi phù hợp

Nếu deployment đã biết issuer và JWKS URI, có thể cấu hình rõ các giá trị này để giảm phụ thuộc vào metadata discovery trong startup path.

Ví dụ JWT Resource Server:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://id.example.com
          jwk-set-uri: https://id.example.com/oauth2/jwks
~~~

Khi dùng trực tiếp `jwk-set-uri`, ứng dụng vẫn cần validate claim `iss`. Không bỏ issuer validation chỉ vì JWKS URI được cấu hình tĩnh. Behavior cụ thể của `issuer-uri` kết hợp `jwk-set-uri` phụ thuộc Spring Boot/Spring Security version; xác nhận với version được khóa trong dự án.

Với opaque token, có thể cấu hình trực tiếp introspection URI thay vì phụ thuộc metadata discovery:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://id.example.com/oauth2/introspect
          client-id: orders-resource-server
          client-secret: ${INTROSPECTION_CLIENT_SECRET}
~~~

Đây là cấu hình endpoint đã được xác định và quản lý bởi deployment. Nó không miễn trừ việc bảo vệ TLS, client credentials và trust relationship.

### 3.3. Không dùng discovery fallback tới issuer tùy ý

Issuer là trust boundary. Không lấy issuer từ request parameter, untrusted JWT claim trước khi xác minh, tenant input hoặc hostname do caller điều khiển rồi thực hiện discovery tới URL đó.

Nếu hỗ trợ multi-tenant/multi-issuer, phải có registry allowlist hoặc tenant-to-issuer mapping được quản trị. Kiểm tra hostname, scheme, issuer identity và JWKS URI theo policy trước khi tạo decoder. Tránh SSRF bằng cách không cho token hoặc client chọn metadata URL tùy ý.

### 3.4. Metadata cache và thời gian sử dụng stale

Nếu metadata cache còn hiệu lực, ứng dụng có thể tiếp tục dùng issuer/JWKS/introspection endpoint đã biết trong outage ngắn. Nhưng metadata cũ có thể trỏ tới endpoint đã bị thay thế hoặc key source không còn đúng.

Policy cần quy định:

- TTL tối đa cho metadata.
- Có được dùng stale metadata khi fetch thất bại hay không.
- Thời gian stale tối đa.
- Cách phát hiện issuer hoặc endpoint đã thay đổi.
- Quy trình invalidate metadata khẩn cấp.
- Hành vi khi metadata cache trống lúc startup.

Không dùng stale metadata vô hạn. Nếu issuer bị compromise hoặc endpoint trust bị thay đổi, cache cũ có thể kéo dài việc tin một cấu hình đã bị thu hồi.

### 3.5. Startup, readiness và liveness

Không nên để một lỗi tạm thời ở discovery làm liveness probe thất bại liên tục và gây restart loop. Liveness trả lời ứng dụng còn sống và có thể tiến triển không; readiness trả lời instance có đủ khả năng nhận traffic theo policy.

Một cách tổ chức:

- **Liveness:** kiểm tra process/application event loop còn hoạt động.
- **Readiness:** kiểm tra ứng dụng đã nạp cấu hình security cần thiết và có thể phục vụ loại traffic được nhận.
- **Dependency health:** báo riêng tình trạng issuer metadata, JWKS và introspection.

Nếu instance mới chưa có metadata/key cần thiết để xác minh token, readiness có thể cần giữ false cho traffic protected. Nếu instance đã có trust configuration và cached keys còn hợp lệ, một outage ngắn có thể không cần loại instance khỏi load balancer. Thiết kế probe theo khả năng thực tế và policy của ứng dụng.

## 4. JWKS không hoạt động

### 4.1. Khi public key còn trong cache

Nếu JWT mang `kid` đã có trong JWK cache và key vẫn được policy cho phép, Resource Server có thể xác minh chữ ký mà không gọi JWKS endpoint. Khi đó outage JWKS không nhất thiết làm mọi request JWT thất bại.

Điều này phụ thuộc JWK source/cache implementation và trạng thái cache. Cache hit chỉ giúp có key; signature, issuer, audience, expiry, `nbf`, algorithm và các validators khác vẫn phải chạy.

### 4.2. Khi token mang kid mới

Nếu token mang `kid` chưa có trong cache, JWK source thường cần refresh hoặc tải JWKS để tìm key. Khi endpoint unavailable và không có key phù hợp trong cache, Resource Server không thể xác minh chữ ký.

Chính sách an toàn:

1. Thực hiện refresh theo behavior đã cấu hình, có giới hạn.
2. Nếu fetch thành công, tìm key và verify signature.
3. Nếu fetch thất bại hoặc key vẫn không tồn tại, từ chối token.
4. Ghi nhận unknown-kid và JWKS dependency failure.
5. Không fallback sang một key khác chỉ vì key ID không tìm thấy.

### 4.3. Khi JWKS trả dữ liệu sai hoặc không đáng tin

Các tình huống cần từ chối key set mới:

- TLS validation thất bại.
- JSON không hợp lệ.
- JWK thiếu public parameters bắt buộc.
- Key type không phù hợp thuật toán.
- Key usage/algorithm không phù hợp policy.
- Response không có key phù hợp.
- Issuer/JWKS URI không thuộc trust configuration.

Không cập nhật cache bằng một response lỗi hoặc malformed. Giữ nguyên key set hợp lệ đang cache chỉ khi cache policy cho phép; không biến dữ liệu lỗi thành trust material.

### 4.4. Stale key có thể giúp availability nhưng làm chậm key revocation

Dùng cached public key trong outage giúp hệ thống tiếp tục phục vụ token đã được ký bằng key đó. Nhưng nếu private signing key bị compromise và public key đã bị gỡ khỏi JWKS, instance vẫn giữ key cũ có thể tiếp tục chấp nhận token cho tới khi cache refresh hoặc hết hạn.

Do đó cần hai policy khác nhau:

- **Outage thông thường:** cho phép dùng cached key trong giới hạn TTL/stale window đã duyệt.
- **Key compromise:** kích hoạt emergency deny/invalidation để ngừng tin key bị lộ, kể cả khi cache còn key đó.

JWKS removal tại origin không đảm bảo thu hồi tức thời ở mọi Resource Server instance.

### 4.5. Không kéo dài stale key vô thời hạn

Nếu JWKS unavailable lâu hơn thời gian stale tối đa, ứng dụng cần từ chối token yêu cầu key chưa được xác nhận theo policy hiện hành. Không tự động kéo dài cache TTL mỗi lần fetch thất bại. Việc giữ cache cũ phải là lựa chọn có giới hạn và có quan sát.

## 5. Introspection không hoạt động

### 5.1. Introspection cache hit

Nếu Resource Server có kết quả introspection `active=true` còn trong TTL, có thể dùng kết quả đó theo policy. TTL cần bị chặn bởi:

- Thời gian còn lại tới token expiry.
- Revocation staleness window được chấp nhận.
- TTL tối đa của security policy.
- Thời gian hiệu lực của metadata/issuer policy liên quan.

Ví dụ nếu API yêu cầu token revoke được phản ánh trong tối đa 10 giây, cache active 60 giây không đáp ứng yêu cầu. Khi cache entry hết hạn, Resource Server phải introspect lại trước khi tiếp tục chấp nhận token.

### 5.2. Introspection cache miss

Nếu cache miss và AS không truy cập được, Resource Server không có bằng chứng token active. Không suy luận active từ việc token đã được chấp nhận trước đó, không chấp nhận chỉ dựa vào token string và không trả authorities mặc định.

Request protected phải fail closed. API có thể trả `503` theo dependency error contract nếu server xác định introspection service unavailable; nếu framework map lỗi thành authentication failure, response có thể là `401`. Cần integration test cho status thực tế.

### 5.3. Introspection trả active=false

Đây là kết quả xác thực hợp lệ từ AS nhưng token không active. Từ chối token và không cache nó như active. Negative cache có thể được dùng ngắn hạn để giảm lặp lại, nhưng phải phân biệt rõ inactive response với timeout/5xx.

### 5.4. Introspection credentials hoặc client bị lỗi

Các lỗi như client ID sai, client secret hết hạn, client bị disable hoặc AS trả 401/403 thường là lỗi integration/configuration. Không retry vô hạn và không coi đó là token inactive của end user.

Hành động phù hợp:

- Fail closed.
- Alert ngay cho đội vận hành.
- Kiểm tra secret rotation và client registration.
- Kiểm tra quyền của resource server client trên introspection endpoint.
- Tránh log secret hoặc request body chứa token.

### 5.5. Introspection response malformed

Nếu response không phải JSON hợp lệ, thiếu `active`, sai kiểu dữ liệu hoặc không đáp ứng protocol contract, không tạo authenticated principal. Không diễn giải response thiếu trường thành `active=true`.

Nếu AS trả metadata không đủ để tạo principal/authorities theo contract của ứng dụng, từ chối hoặc báo integration error theo chính sách đã định nghĩa.

## 6. Timeout, retry và circuit breaker

### 6.1. Mọi remote call cần deadline hữu hạn

Discovery, JWKS fetch và introspection đều là network dependencies. Cần xác định connection timeout, TLS handshake timeout nếu HTTP client hỗ trợ cấu hình riêng, response/read timeout, connection pool acquisition timeout, tổng deadline phù hợp request budget và giới hạn kích thước response.

Không để thread request chờ vô hạn vì một identity endpoint bị treo.

### 6.2. Retry chỉ cho lỗi transient phù hợp

Có thể cân nhắc retry với network reset, timeout ngắn hoặc một số HTTP 5xx. Không retry vô hạn và không retry mọi response.

| Lỗi | Hướng xử lý |
|---|---|
| DNS timeout hoặc connection reset | Retry giới hạn nếu còn request deadline |
| HTTP 502/503/504 | Retry có budget/backoff nếu policy cho phép |
| HTTP 400 từ metadata/introspection | Kiểm tra request/configuration; không retry mù |
| HTTP 401/403 từ introspection client | Sửa credentials/registration; không retry liên tục |
| JWT signature invalid | Từ chối token; không retry JWKS chỉ để biến token invalid thành valid |
| Unknown kid | Refresh theo JWK source policy có giới hạn |
| HTTP 429 | Tôn trọng `Retry-After` nếu phù hợp deadline và client behavior |

Retry có thể nhân đôi traffic trong outage. Dùng exponential backoff với jitter, giới hạn tổng số lần và không vượt request deadline.

### 6.3. Circuit breaker bảo vệ dependency

Circuit breaker có thể ngừng gọi một endpoint đang lỗi liên tục, giảm queue và bảo vệ connection pool. Khi circuit open:

- Discovery không thể cung cấp metadata mới.
- JWKS không thể cung cấp key mới.
- Introspection không thể cung cấp trạng thái mới cho cache miss.

Circuit breaker không tạo ra bằng chứng xác thực. Cache entry còn hiệu lực có thể tiếp tục dùng theo policy; cache miss phải fail closed. Không cấu hình fallback trả `active=true`, authorities mặc định hoặc bỏ signature validation.

### 6.4. Bulkhead và connection pool

Tách giới hạn tài nguyên cho identity HTTP calls khỏi các outbound calls khác khi cần. Giới hạn concurrency giúp một introspection outage không chiếm hết request threads hoặc connection pool của API. Cấu hình pool đủ lớn cho traffic hợp lệ nhưng có hard limit; theo dõi pool saturation và pending acquisitions.

### 6.5. Không đặt retry ở nhiều tầng mà không tính tổng

Nếu HTTP client retry 3 lần, service wrapper retry 3 lần và gateway retry thêm, một request có thể tạo nhiều lần gọi hơn dự kiến. Chọn một tầng sở hữu retry policy hoặc tính tổng retry budget xuyên suốt hệ thống.

## 7. Cấu hình Spring Security Resource Server

### 7.1. JWT với issuer và JWKS URI

Cấu hình Spring Boot:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://id.example.com
          jwk-set-uri: https://id.example.com/oauth2/jwks
~~~

Security filter chain:

~~~java
@Bean
SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/health/**").permitAll()
            .anyRequest().authenticated()
        )
        .oauth2ResourceServer(oauth2 ->
            oauth2.jwt(Customizer.withDefaults())
        )
        .build();
}
~~~

`issuer-uri` giữ issuer làm một phần của trust policy. `jwk-set-uri` chỉ định trực tiếp key endpoint. Kiểm tra version Spring Boot/Spring Security để hiểu chính xác startup discovery và decoder initialization behavior.

### 7.2. Tạo decoder với issuer validator

Khi cần kiểm soát decoder trực tiếp:

~~~java
@Bean
JwtDecoder jwtDecoder() {
    String issuer = "https://id.example.com";
    String jwkSetUri = "https://id.example.com/oauth2/jwks";

    NimbusJwtDecoder decoder =
        NimbusJwtDecoder.withJwkSetUri(jwkSetUri).build();

    decoder.setJwtValidator(
        JwtValidators.createDefaultWithIssuer(issuer)
    );

    return decoder;
}
~~~

Ví dụ này giữ default timestamp validators cùng issuer validation. Nếu API cần audience validator, compose thêm validator thay vì ghi đè toàn bộ policy một cách vô ý.

Không tự viết decoder bỏ qua signature hoặc tự parse payload rồi tạo `JwtAuthenticationToken`.

### 7.3. Opaque token introspection

Cấu hình Spring Boot:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://id.example.com/oauth2/introspect
          client-id: orders-resource-server
          client-secret: ${INTROSPECTION_CLIENT_SECRET}
~~~

Security filter chain:

~~~java
@Bean
SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .anyRequest().authenticated()
        )
        .oauth2ResourceServer(oauth2 ->
            oauth2.opaqueToken(Customizer.withDefaults())
        )
        .build();
~~~

Client credentials được dùng để Resource Server gọi introspection endpoint. Chúng không phải Bearer token của end user. Secret phải được cấp qua secret manager hoặc environment injection.

### 7.4. Dùng endpoint tĩnh và discovery có chủ đích

Khi muốn giảm dependency vào discovery trong startup path, có thể cấu hình JWKS URI hoặc introspection URI trực tiếp. Đổi lại, endpoint và issuer metadata trở thành cấu hình deployment cần được cập nhật, kiểm soát và audit.

Không hardcode endpoint production rải rác trong nhiều class. Dùng configuration properties, kiểm tra giá trị ở startup và quản lý thay đổi qua deployment process.

### 7.5. Timeout và HTTP client

Nimbus decoder/JWK source và introspection client có các điểm cấu hình HTTP transport khác nhau theo Spring Security/Nimbus version. Hãy cấu hình connect/read timeout, TLS trust và connection pooling qua API được hỗ trợ bởi version dự án. Không giả định một property timeout áp dụng cho mọi HTTP client mà framework sử dụng.

Nếu cung cấp custom HTTP client, kiểm tra nó thực sự được dùng bởi decoder/introspector trong filter chain. Một bean HTTP client không được wiring vào identity component sẽ không thay đổi timeout runtime.

## 8. Startup và deployment strategy

### 8.1. Phân biệt cấu hình hợp lệ với dependency tạm thời unavailable

Startup nên kiểm tra cấu hình local:

- Issuer URI hợp lệ và dùng HTTPS theo policy.
- JWKS/introspection endpoint đúng hostname.
- Client ID có giá trị.
- Secret được cấp.
- Algorithm allowlist và audience policy được khai báo.
- Timeout/retry/cache policy có giới hạn.

Một dependency tạm thời unavailable không nhất thiết phải gây restart loop nếu ứng dụng đã có trust configuration hợp lệ và có thể dùng cached data. Ngược lại, cấu hình sai hoặc không có nguồn key/metadata đáng tin không được coi là degraded state an toàn.

### 8.2. Warm-up cache có kiểm soát

Với JWT, có thể chủ động kiểm tra JWKS endpoint hoặc tải key set trong deployment warm-up để phát hiện lỗi trước khi nhận traffic. Không dùng token giả để kết luận decoder đã sẵn sàng nếu test không đi qua signature verification thực.

Với introspection, không thể warm một token arbitrary để thay thế cache thực tế. Có thể health-check endpoint bằng cơ chế được AS hỗ trợ, nhưng health check phải dùng client authentication đúng và không tạo token state giả.

### 8.3. Readiness phải phản ánh khả năng phục vụ

Một instance mới chưa có public key và không truy cập được JWKS có thể chưa sẵn sàng nhận protected JWT traffic. Một instance đã có cached key hợp lệ có thể tiếp tục phục vụ theo stale policy. Readiness cần dựa trên trạng thái thực tế và policy, không chỉ ping endpoint.

Tránh gắn identity dependency check vào liveness nếu việc fail làm pod restart liên tục và khiến outage lan rộng.

### 8.4. Rollout và rollback

Trước deployment:

- Kiểm tra discovery metadata/JWKS/introspection endpoint từ network zone production.
- Kiểm tra TLS chain và credentials.
- Kiểm tra key rotation overlap.
- Đặt timeout/retry/circuit breaker.
- Xác nhận cache policy và revocation SLA.
- Chuẩn bị rollback cấu hình issuer/endpoint nếu thay đổi sai.

Rollback endpoint không có nghĩa rollback về một issuer hoặc key không còn đáng tin. Chỉ quay lại trust configuration đã được xác nhận và còn hiệu lực.

## 9. Phân biệt lỗi identity với lỗi authorization

Resource Server cần giữ rõ các tầng:

1. **Authentication:** token có được xác minh và principal có được tạo không?
2. **Authorization:** principal có authority/scope cần thiết không?
3. **Dependency availability:** có thể truy cập metadata/key/introspection source không?

| Tình huống | Kết quả |
|---|---|
| JWT signature invalid | Authentication failure |
| JWT expired | Authentication failure |
| Introspection `active=false` | Authentication failure |
| Token hợp lệ nhưng thiếu `SCOPE_orders.write` | Authorization failure |
| JWKS timeout và không có key trong cache | Dependency/authentication failure |
| Introspection timeout và cache miss | Dependency/authentication failure |
| Discovery metadata malformed | Identity configuration/dependency failure |

Không trả `403 insufficient_scope` khi token chưa được xác minh. Không báo `invalid_token` như thể token chắc chắn sai khi nguyên nhân thực là introspection service unavailable, nếu API có khả năng phân biệt hai loại lỗi.

### 9.1. Status và Bearer challenge

Theo Bearer token semantics:

- `401` thường dùng cho thiếu token hoặc token invalid.
- `403` với `insufficient_scope` dùng khi authentication thành công nhưng scope không đủ.
- `503` có thể dùng cho identity dependency outage nếu API gateway/error contract hỗ trợ phân biệt.

Spring Security có default entry point và access-denied handling. Nếu cần status khác cho một dependency exception, hãy tùy biến error mapping có kiểm soát và kiểm thử qua filter chain. Không trả stack trace, endpoint nội bộ, response body từ AS hoặc token trong error response.

## 10. Observability cho identity dependencies

### 10.1. Metrics discovery

Theo dõi metadata fetch success/failure, metadata fetch latency, metadata cache hit/miss/age, issuer mismatch, metadata parse/validation errors và thời điểm refresh thành công gần nhất.

### 10.2. Metrics JWKS

Theo dõi JWKS fetch success/failure và latency, JWKS cache hit/miss/age, unknown `kid` count, signature verification failure, key set size, last successful JWKS refresh và TLS/DNS/HTTP error category.

### 10.3. Metrics introspection

Theo dõi introspection QPS và latency p50/p95/p99, active/inactive outcomes, HTTP/network failures, cache hit/miss/eviction/expiry, in-flight requests, connection pool saturation, timeout/retry/circuit breaker state và last successful introspection response.

### 10.4. Không log credential hoặc tạo high-cardinality labels

Không log Authorization header, raw JWT, opaque token, introspection request body, client secret hoặc toàn bộ claims. Không dùng token hash, `sub`, `jti`, session ID hay `kid` tùy ý do caller gửi làm metric labels.

Có thể log request correlation ID, dependency name (`discovery`, `jwks`, `introspection`), error category, HTTP status đã chuẩn hóa, cache hit/miss, issuer alias được cấu hình và circuit breaker state.

Nếu cần điều tra token cụ thể, dùng audit mechanism được bảo vệ và identifier đã được kiểm soát; không đưa credential vào log thông thường.

### 10.5. Alert theo tác động

Alert hữu ích gồm discovery/JWKS/introspection failure kéo dài, unknown-kid tăng đột biến, signature failure tăng sau rotation, introspection latency p99 vượt budget, cache stale age vượt ngưỡng, connection pool bão hòa, client credentials bị từ chối và circuit breaker mở quá lâu.

Không alert chỉ dựa vào một lỗi đơn lẻ trong rollout có kế hoạch; kết hợp error rate, duration, affected instances và request impact.

## 11. Runbook xử lý sự cố

### 11.1. Discovery endpoint không truy cập được

1. Xác nhận hostname/issuer URI đã cấu hình.
2. Kiểm tra DNS, route, proxy và firewall.
3. Kiểm tra TLS certificate chain, hostname và expiry.
4. Kiểm tra HTTP status và response body metadata.
5. Kiểm tra issuer trong document có khớp cấu hình không.
6. Xác định metadata cache còn hợp lệ hay đã hết stale window.
7. Nếu dùng endpoint tĩnh, xác nhận JWKS/introspection URI vẫn đúng và được trust.
8. Khôi phục endpoint hoặc deploy metadata/configuration đã được xác nhận.

Không lấy issuer khác làm fallback chỉ vì issuer hiện tại unavailable.

### 11.2. JWKS fetch lỗi

1. Xác định token có `kid` nào và algorithm nào; chỉ dùng header để chẩn đoán.
2. Xác nhận key ID có trong JWKS origin.
3. Kiểm tra JWK source cache age và last refresh.
4. Kiểm tra DNS/TLS/HTTP status từ Resource Server.
5. Kiểm tra key type, `use`, `alg` và public parameters.
6. Nếu key còn trong cache, áp dụng stale policy.
7. Nếu key không có và không fetch được, từ chối token.
8. Kiểm tra có rotation chưa publish-before-sign hay không.

Không tắt signature validation để khôi phục traffic.

### 11.3. Introspection endpoint lỗi

1. Xác nhận introspection URI.
2. Kiểm tra client ID/secret và thời hạn secret.
3. Kiểm tra quyền của Resource Server client trên endpoint.
4. Kiểm tra TLS, DNS, proxy, connection pool và timeout.
5. Xem cache hit/miss và tuổi của active result.
6. Nếu active result còn TTL, chỉ dùng theo policy.
7. Nếu cache miss, fail closed và trả dependency error theo contract.
8. Theo dõi QPS/latency sau khi AS phục hồi.

Không diễn giải timeout thành `active=true`.

### 11.4. Sau khi dependency phục hồi

- Xác nhận metadata/JWKS response hợp lệ.
- Cho JWK source/cache refresh theo policy.
- Xác nhận key mới hoặc endpoint mới đã được nhận.
- Kiểm tra introspection response với test token hợp lệ được quản lý.
- Theo dõi cache hit/miss và failure rate.
- Xác nhận circuit breaker đóng lại theo recovery policy.
- Kiểm tra không có retry storm sau phục hồi.

## 12. Kiểm thử failure behavior

### 12.1. Discovery tests

Dùng mock HTTP server hoặc WireMock để mô phỏng metadata fetch thành công, timeout, HTTP 404/500/503, TLS/DNS failure nếu test harness hỗ trợ, metadata JSON malformed, thiếu `jwks_uri` hoặc introspection endpoint cần thiết, issuer mismatch và metadata thay đổi endpoint sau refresh.

Xác nhận startup/readiness behavior phù hợp policy và ứng dụng không tin issuer tùy ý.

### 12.2. JWKS tests

Tạo test key pair và JWKS endpoint có thể điều khiển:

- Key có trong cache, endpoint ngừng hoạt động.
- Cache miss, endpoint unavailable.
- Unknown `kid`, refresh thành công.
- Unknown `kid`, refresh thất bại.
- Key mới được publish trước khi token mới được ký.
- Key cũ còn trong overlap.
- Key cũ bị gỡ sau thời gian token lifetime.
- Chữ ký sai dù `kid` tồn tại.
- JWKS malformed hoặc key type không phù hợp.

Dùng decoder thật để kiểm tra signature verification. Mock `JwtDecoder` không chứng minh JWK fetch, parsing hay chữ ký hoạt động.

### 12.3. Introspection tests

Dùng mock introspection endpoint:

- `active=true` với metadata hợp lệ.
- `active=false`.
- HTTP 401/403 do client authentication.
- HTTP 429/5xx.
- Timeout và connection reset.
- Response malformed hoặc thiếu `active`.
- Cache hit khi AS outage.
- Cache miss khi AS outage.
- Cache expiry sau revocation.
- Concurrent misses và giới hạn concurrency.

Xác nhận dependency failure không biến thành authenticated principal và không bị cache nhầm như inactive response.

### 12.4. Kiểm thử status mapping qua filter chain

Dùng MockMvc và security filter chain thật để xác nhận token invalid trả status theo contract, thiếu scope trả 403, JWKS/introspection dependency outage trả status đã thiết kế, không có controller/service side effect khi authentication chưa thành công và error response không chứa token/secret/nội dung nội bộ.

### 12.5. Không dùng sleep dài hoặc test phụ thuộc internet

Dùng mock server, controllable clock và cache test provider để điều khiển TTL/failure. Test không nên gọi Authorization Server production hoặc phụ thuộc internet công cộng. Điều này giúp tái lập outage và kiểm tra chính xác thời điểm cache hết hạn.

## 13. Ví dụ ma trận policy theo dependency

Một cấu hình vận hành có thể định nghĩa các giới hạn sau (giá trị chỉ minh họa; cần chọn theo SLA/security policy của hệ thống):

| Thành phần | Bình thường | Outage ngắn | Outage kéo dài |
|---|---|---|---|
| Discovery metadata | Fetch/refresh theo cache | Dùng metadata tin cậy trong TTL | Không dùng stale metadata vô hạn; giữ instance degraded/not ready nếu không xác định được endpoint |
| JWKS | Cache key set và refresh khi cần | Dùng key đã cache theo stale policy | Từ chối token cần key chưa có hoặc key đã vượt stale limit |
| Introspection | Gọi endpoint và cache active result ngắn | Dùng active result còn TTL nếu policy cho phép | Cache miss bị từ chối; alert và báo dependency outage |
| Client credentials | Secret được quản lý và rotate | Tiếp tục khi credential còn hợp lệ | Fail closed, khôi phục secret/registration |
| HTTP client | Pool/timeout hữu hạn | Retry transient có budget | Circuit breaker/bulkhead, không queue vô hạn |

Giá trị TTL và stale window phải được ghi thành policy rõ ràng, không để mỗi instance hoặc mỗi module tự quyết định.

## 14. Những sai lầm thường gặp

1. **Gộp discovery, JWKS và introspection thành một dependency:** chúng cung cấp dữ liệu khác nhau và có cache policy khác nhau.
2. **Cho rằng discovery outage luôn làm mọi JWT request thất bại:** endpoint tĩnh và metadata cache có thể cho phép tiếp tục trong giới hạn policy.
3. **Cho rằng JWKS outage làm mọi JWT request thất bại ngay:** key phù hợp có thể còn trong cache.
4. **Chấp nhận token có kid mới khi không tải được public key:** không thể xác minh chữ ký.
5. **Dùng stale key vô thời hạn:** key bị compromise có thể tiếp tục được tin.
6. **Coi JWKS removal là revoke tức thời:** instance còn cache có thể vẫn dùng key cũ.
7. **Coi introspection timeout là `active=false`:** timeout không cho biết token state.
8. **Coi introspection timeout là `active=true`:** đây là fail open.
9. **Cache dependency exception:** lỗi mạng có thể tồn tại lâu hơn outage.
10. **Retry không giới hạn:** khuếch đại sự cố và gây retry storm.
11. **Circuit breaker có fallback allow:** breaker không thể tạo bằng chứng authentication.
12. **Gắn dependency outage vào liveness:** restart loop có thể làm outage lan rộng.
13. **Dùng issuer hoặc JWKS URL từ input không tin cậy:** tạo SSRF/trust confusion.
14. **Không kiểm thử status mapping:** client có thể nhận 401/403/500 không đúng contract.
15. **Log raw token hoặc introspection body:** làm lộ credential.
16. **Chỉ kiểm tra health endpoint của AS:** endpoint sống không chứng minh Resource Server có thể lấy metadata/key hoặc introspect với credentials thực.

## 15. Checklist triển khai an toàn

- [ ] Phân biệt discovery metadata, JWKS key material và introspection state.
- [ ] Chỉ dùng issuer và endpoint từ cấu hình/trust registry đã xác nhận.
- [ ] Không cho caller điều khiển discovery URL, `jku` hoặc `x5u`.
- [ ] Đặt TTL riêng cho metadata, JWKS và introspection result.
- [ ] Định nghĩa stale window và emergency invalidation.
- [ ] Giữ signature, issuer, audience, expiry và algorithm validation.
- [ ] Unknown `kid` phải refresh có giới hạn rồi fail closed nếu vẫn không tìm thấy.
- [ ] Introspection cache miss khi AS outage phải fail closed.
- [ ] Không cache timeout/5xx như token inactive hoặc active.
- [ ] Đặt connection/read timeout và request deadline.
- [ ] Giới hạn retry, concurrency và connection pool.
- [ ] Dùng circuit breaker để bảo vệ dependency, không để fallback allow.
- [ ] Phân biệt liveness, readiness và dependency health.
- [ ] Tách authentication failure, authorization failure và dependency outage.
- [ ] Có metrics cho cache, latency, failure, unknown `kid` và circuit state.
- [ ] Không log token, secret hoặc introspection request body.
- [ ] Có fault-injection tests cho discovery, JWKS và introspection.
- [ ] Có runbook cho recovery và key/credential compromise.

## 16. Tài liệu tham khảo

- [OpenID Connect Discovery 1.0](https://openid.net/specs/openid-connect-discovery-1_0.html): metadata discovery và issuer configuration.
- [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414): metadata cho Authorization Server.
- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517): JWK và JWKS format.
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519): JWT structure và claims.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): introspection request/response và `active`.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): Bearer token error semantics.
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): issuer/key validation và JWT security practices.
- [Spring Security — JWT Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): JWT decoder, issuer, JWKS và validators.
- [Spring Security — Opaque Token Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html): opaque token introspection.
- [Spring Security — OAuth2 Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/index.html): Servlet Resource Server configuration.

**Kết luận:** Khi discovery, JWKS hoặc introspection gặp sự cố, Resource Server chỉ được tiếp tục xác thực bằng dữ liệu tin cậy còn hiệu lực theo cache policy đã duyệt. JWT có thể tiếp tục được verify bằng public key đã cache; token mang `kid` chưa biết phải bị từ chối nếu không lấy được key. Introspection chỉ có thể dùng active result còn trong TTL; cache miss khi endpoint unavailable phải fail closed. Timeout, retry, circuit breaker, readiness, status mapping và observability cần được thiết kế cùng nhau để bảo vệ cả security boundary lẫn availability của API.
