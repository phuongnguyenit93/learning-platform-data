# So sánh JWT và opaque token theo độ trễ, phụ thuộc mạng và khả năng thu hồi trong Spring Security reactive

## 1. Bài toán cần giải

Một API xây dựng bằng **Spring WebFlux** nhận `Authorization: Bearer ...` từ mobile app, frontend hoặc service khác. Hệ thống danh tính hỗ trợ hai lựa chọn:

- **JWT access token được resource server tự xác minh:** API dùng public key/JWKS của issuer, xác minh chữ ký và các claim; không cần hỏi Authorization Server về **từng** request thông thường.
- **Opaque access token được xác minh bằng introspection:** API gửi token tới Authorization Server theo **RFC 7662**, nhận `active` và metadata rồi mới quyết định authentication/authorization.

Nếu chỉ nói “JWT nhanh, opaque dễ thu hồi” thì chưa đủ để thiết kế. Thực tế phải xem **P95/P99 của endpoint**, **introspection RTT**, **JWKS cache miss**, **rate limit IdP**, **độ trễ đồng bộ thông tin thu hồi**, **cache TTL** và những thao tác cần quyền có hiệu lực ngay.

Sau bài học, bạn có thể:

1. Vẽ critical path cho mỗi kiểu xác thực và tách **chi phí xác minh token** khỏi độ trễ mạng gọi business API.
2. Tính tải introspection, latency trung bình theo cache hit rate và số request đồng thời bằng các giả định có thể kiểm chứng.
3. Giải thích vì sao **JWT không tuyệt đối không cần mạng** và **opaque có cache không tuyệt đối thu hồi tức thì**.
4. Ước lượng **revocation exposure window** khi khóa tài khoản hoặc thu hồi token.
5. Cấu hình Spring Security **reactive resource server** đúng với `ReactiveJwtDecoder` hay `ReactiveOpaqueTokenIntrospector`, có rule scope.
6. Tổ chức thí nghiệm canary và chaos test để chọn loại token theo **SLO**, yêu cầu thu hồi và độ tin cậy IdP.
7. Chạy chương trình **Java 17+ độc lập** mô phỏng latency/QPS/revocation để hiểu trade-off, cùng ví dụ Spring Boot WebFlux có thể kết nối IdP thật.
8. Nhận diện các anti-pattern: decode JWT không verify, fail-open introspection, cache `active=true` đến hết vòng đời token, retry vô hạn khi IdP lỗi.

**Phạm vi:** bài này so sánh **chiến lược xác minh** cho access token tại Resource Server. Không phải bài tạo JWT, làm OAuth2 Login hay lưu `OAuth2AuthorizedClient` ở ứng dụng gọi API. Định dạng của một token có thể là JWT nhưng vẫn được kiểm tra qua introspection; cần nói chính xác “JWT local verification” và “online introspection”.

## 2. Trục định dạng khác trục phương thức xác minh

**Bearer** theo RFC 6750 là cách trình credential trong header, **không nói credential là JWT hay opaque**.

~~~http
GET /api/orders HTTP/1.1
Host: api.example.com
Authorization: Bearer a7R-opaque-token-sample
~~~

~~~http
GET /api/orders HTTP/1.1
Host: api.example.com
Authorization: Bearer eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiIxIn0.sample-signature
~~~

Đây đều là **chuỗi minh họa**, không phải token hợp lệ dùng production. Một JWT dạng JWS Compact thường có ba phần **Base64URL(header).Base64URL(payload).Base64URL(signature)**; payload **có thể đọc được**, không được mã hóa mặc nhiên. Opaque token thường là chuỗi mà Resource Server **không giải mã để xác định quyền**. Cả hai là Bearer credentials: bị lộ token là có nguy cơ bị dùng lại.

| Câu hỏi | Cần xác định |
| --- | --- |
| Token có dạng gì? | Random opaque string, JWT/JWS hoặc định dạng khác |
| Resource Server tin ai để xác minh? | Local crypto + trusted claims hay Authorization Server qua introspection |
| Tại thời điểm request cần kiểm trạng thái thu hồi online không? | Có, không hoặc chỉ ở một số hành động |
| Token được cấp cho API nào? | `aud`, resource indicators, issuer, client/tenant |
| User được phép gọi endpoint gì? | Scope/authority/role và business policy |

Spring Security WebFlux có hai adapter:

- `oauth2ResourceServer(o -> o.jwt(...))` dùng **`ReactiveJwtDecoder`**, thường là `NimbusReactiveJwtDecoder`.
- `oauth2ResourceServer(o -> o.opaqueToken(...))` dùng **`ReactiveOpaqueTokenIntrospector`**, mặc định HTTP introspection qua `SpringReactiveOpaqueTokenIntrospector`.

Nếu Authorization Server phát **JWT** nhưng resource server dùng `opaqueToken()` để hỏi trạng thái `active` trên mỗi request, kiến trúc đó thuộc **online introspection**, không được tính như “JWT local miễn phí network”. Spring Security tài liệu chính thức hỗ trợ kiểu xử lý này.

## 3. Critical path xác minh: trước và sau cache

### 3.1. JWT local verification

~~~text
Client                  WebFlux Resource Server               Authorization Server
  |                              |                                     |
  | GET /api/orders + Bearer JWT |                                     |
  |----------------------------->|                                     |
  |                         read JWS header/payload                    |
  |                         find trusted signing key                  |
  |                             |                                      |
  |                     cache hit: key đã có                           |
  |                             |                                      |
  |                     verify signature                              |
  |                     validate iss/exp/nbf/aud                      |
  |                     map scope -> SCOPE_*                           |
  |                     authorize + business                           |
  |<---------------------- 200 / 401 / 403                             |
  |                             |                                      |
  |         cache miss/unknown kid ---> metadata/JWKS fetch ---------->|
  |                             |<------ key material -----------------|
~~~

**Warm path** (đã có khóa xác minh đáng tin trong cache) không cần gửi token đến IdP. Tuy nhiên, **cold path**, `kid` chưa thấy, key rotation, metadata discovery hay cache expiry có thể phát sinh HTTP call tới issuer/JWKS endpoint. Vì vậy “JWT luôn offline” là quá tuyệt đối.

**Local validation vẫn bắt buộc mỗi request**: kiểm chữ ký/JWS algorithm được phép, `exp`, `nbf`, `iss`, `aud`, tenant/client và scope. Không được chỉ Base64URL-decode payload rồi tin `roles`. Khi một token bị thu hồi ở IdP nhưng vẫn đúng chữ ký và chưa hết `exp`, local validator **không tự biết** tin thu hồi nếu không có một lớp revocation check bổ sung.

### 3.2. Opaque introspection

~~~text
Client                  WebFlux Resource Server               Authorization Server
  |                              |                                     |
  | GET /api/orders             |                                     |
  | Authorization: Bearer random-string                                |
  |----------------------------->|                                     |
  |                       ReactiveOpaqueTokenIntrospector             |
  |                             | HTTPS POST /introspect               |
  |                             | token=...                            |
  |                             | client authentication               |
  |                             |------------------------------------>|
  |                             |<----- active, scope, exp, aud -------|
  |                        check active and local API policy          |
  |                        map scopes -> SCOPE_*                      |
  |                        authorize + business                       |
  |<---------------------- 200 / 401 / 403                             |
~~~

Theo RFC 7662, Authorization Server trả một JSON chứa **`active` boolean**. `active=false` thường do token không tồn tại, hết hạn, bị revoke hoặc không phù hợp chính sách hỏi token. `active=true` là kết quả xác minh online theo semantics của Authorization Server, **không tự thay thế** check scope, audience, tenant và business authorization của chính API.

Nếu không cache kết quả, thường **mỗi request Bearer** thêm một network round trip và chi phí xử lý ở Authorization Server. Nhiều requests từ một client có cùng token vẫn có thể gọi introspection lặp lại nếu bạn không triển khai cache/aggregation.

### 3.3. Không nhầm network hop

Một request từ browser tới Resource Server luôn có network latency dù dùng JWT. So sánh đúng là:

~~~text
JWT warm:
client -> API -> local JWT verification -> business -> response

Opaque no-cache:
client -> API -> HTTPS introspection to IdP -> business -> response
                  ^ extra critical-path hop

JWT cold/JWKS miss:
client -> API -> JWKS fetch to IdP -> local verify -> business -> response
                  ^ occasional critical-path hop

Opaque cached:
client -> API -> cached introspection lookup -> business -> response
                  ^ extra hop avoided on cache hit; state may be stale
~~~

Không cộng network browser→API vào **chỉ một** phương án; để so latency, đo cùng request path, cùng business workload, cùng client region và cùng độ tải.

## 4. Bảng so sánh ba trục chính

| Tiêu chí | JWT local signature verification | Opaque + introspection không cache | Opaque + cache introspection |
| --- | --- | --- | --- |
| Extra call tới IdP trên warm request | Thường **0** | Thường **1** | 0 khi hit, 1 khi miss |
| CPU tại API | Parse JWS, verify signature + claims | Parse introspection response + local policy | Cache lookup + local policy |
| Network RTT thêm | Không ở warm path | Có ở critical path | Chỉ khi miss |
| Tail latency | Thường ổn hơn nếu key cache hit | Phụ thuộc tail của IdP/network | Có phân phối hai đỉnh: hit/miss |
| QPS tới IdP | JWKS/metadata định kỳ, không tỷ lệ 1:1 requests | Xấp xỉ bearer QPS | Xấp xỉ miss QPS |
| Tác động IdP outage | Warm keys có thể tiếp tục verify đến giới hạn chính sách/key cache | Authentication thường không hoàn tất | Hit còn dùng cache đến TTL; miss fail closed |
| Revoke trước `exp` | Không tự biết nếu không online revocation | Có thể thấy ngay khi IdP cập nhật trạng thái | Có cửa sổ stale-positive đến TTL |
| Bảo mật token payload | JWT JWS claims có thể đọc bởi bearer holder | Opaque string không tự lộ claims | Tương tự opaque nhưng cache lưu metadata |
| Scale API ngang | Dễ scale verification cục bộ | Scale phụ thuộc IdP latency/capacity | Cần thiết kế cache shared/local |
| Scope/role sau cấp token | Thường là snapshot trong JWT | IdP có thể trả metadata cập nhật | Có thể stale theo cache TTL |
| Khả năng kiểm tra audience/issuer | JWT validators tại API | Dựa vào IdP contract + validator ở API | Giống introspection, kiểm thêm tính nhất quán cache |
| Tính xác định khi disconnect | Phụ thuộc JWKS cache/key rotation | Thường từ chối khi không thể introspect | Phụ thuộc chiến lược hit/miss và chính sách fail closed |

Các ô “thường” là hành vi điển hình, **không phải cam kết hiệu năng** của một thư viện. Độ trễ thực tế chịu ảnh hưởng thuật toán ký, size token, JWK/cache, IdP database, network, connection pool, GC và số lượng request đồng thời.

## 5. Cách định lượng độ trễ mà không bịa benchmark

### 5.1. Mô hình đơn giản để tính ngân sách

Đặt:

- `L_app`: latency business handler **không bao gồm xác minh token**.
- `L_jwt`: local JWT verification với key cache hit.
- `L_intro`: phần tăng thêm khi gọi introspection, gồm network RTT/TLS connection reuse, IdP xử lý và parse/validation response.
- `h`: tỉ lệ **cache hit** của introspection, từ 0 đến 1.
- `λ`: Bearer requests/giây của các API có check.
- `T`: TTL cache positive introspection.
- `L_cache`: chi phí đọc cache (không nhất thiết bằng 0).

Các công thức kỳ vọng cho **mô hình minh họa**:

~~~text
JWT_warm_average       ≈ L_app + L_jwt
Opaque_no_cache_avg    ≈ L_app + L_intro
Opaque_cached_avg      ≈ L_app + h * L_cache + (1-h) * L_intro

Introspection_QPS_no_cache ≈ λ
Introspection_QPS_cached   ≈ λ * (1-h)

InFlight_introspection ≈ λ_miss * L_intro_seconds
~~~

Công thức số requests đang chờ sử dụng ý tưởng **Little's Law**, và giả định tốc độ ổn định, không có queue overload và định nghĩa latency introspection nhất quán. Thực tế cần thêm baseline networking/application, timeouts, concurrency caps, GC và retry. Công thức average không cho phép suy ra **P95/P99**: khi 90% cache hit, vẫn có thể tới 10% request đi đường miss và nhóm này hoàn toàn chiếm P95/P99.

### 5.2. Ví dụ số học — tất cả là **giả định**, không phải kết quả đo

Giả sử:

| Biến | Giá trị mô phỏng |
| --- | --- |
| `λ` | 1.200 protected requests/giây |
| `L_app` | 5,0 ms |
| `L_jwt` | 0,7 ms |
| `L_intro` | 22,0 ms |
| `h` khi cache opaque | 90% |
| `L_cache` | 0 ms để công thức đơn giản; thực tế luôn lớn hơn 0 |
| `T` cache positive | 10 giây |
| Thời gian còn lại của JWT `exp` | 300 giây |

Từ đó:

~~~text
JWT warm expected             = 5.0 + 0.7 = 5.7 ms
Opaque no cache expected      = 5.0 + 22.0 = 27.0 ms
Opaque 90% hit expected       = 5.0 + 0.1*22.0 = 7.2 ms

IdP calls/sec no cache        = 1200
IdP calls/sec with 90% hit    = 1200 * (1 - 0.90) = 120

In-flight no-cache expected   = 1200 * 0.022 = 26.4
In-flight cached expected     = 120  * 0.022 = 2.64
~~~

Đây **không** chứng minh JWT thực luôn mất 0,7 ms, IdP luôn mất 22 ms hay cache hit luôn 90%. Phải benchmark bằng token, JWS algorithm, IdP và network **của hệ thống bạn**. Nếu P99 introspection là 300 ms, request đi đường cache miss có thể bị tail latency rất cao dù mean nhìn đẹp.

### 5.3. P50/P95/P99: nhìn phân phối, không chỉ mean

Với cache hit rate 90%, nếu một số request miss đều có latency cao hơn hẳn hit, P50 nằm gần đường hit, còn P95 có thể nằm ở nhóm miss. Một dashboard chỉ hiển thị average 7,2 ms của mô hình trên sẽ che trải nghiệm của **10% request chậm**.

Khi benchmark, báo riêng:

- `jwt_verify_duration` (với cached JWKS, cold JWKS và key rotation).
- `introspection_http_duration` (connect, TLS, server processing, read).
- `introspection_cache_hit_rate`, positive/negative hit.
- End-to-end response latency P50, P95, P99; request rate và error rate.
- Concurrency/in-flight, connection pool queue, timeout, retry attempts.
- Distinct token cardinality: 1000 QPS với 10 user dùng một token khác 1000 QPS với 1000 tokens unique.
- Token TTL, session/authorization propagation và revocation lag.

### 5.4. Throughput và saturation

Ở 1.200 QPS, nếu mỗi introspection giữ connection khoảng 22 ms, theo mô hình sẽ có trung bình **26,4 requests introspection đang chờ**. Nhưng khi IdP chậm thành 200 ms, lượng in-flight có thể tăng lên **240** ngay cả khi request rate không đổi. Nếu pool/IdP queue bị bão hòa, latency có thể tăng phi tuyến; client timeout, circuit breaker và backpressure trở thành bắt buộc.

Không so sánh hai kiến trúc ở một QPS thấp rồi tuyên bố sẽ scale tương tự khi peak gấp 10 lần.

## 6. Java 17 chạy độc lập: tính các trade-off

File `TokenTradeoffModel.java` dưới đây **chỉ sử dụng JDK 17**, không cần Spring/IdP/network. Nó tính kỳ vọng từ giả định ở phần 5 và in kết quả có thứ tự ổn định bằng `Locale.ROOT`.

~~~java
import java.util.Locale;

public final class TokenTradeoffModel {

    record Inputs(int requestsPerSecond,
                  double businessMs,
                  double jwtVerifyMs,
                  double introspectionMs,
                  double cacheHitRate,
                  int cacheTtlSeconds,
                  int jwtRemainingSeconds) {
    }

    private TokenTradeoffModel() {
    }

    public static void main(String[] args) {
        Inputs input = new Inputs(
                1200, 5.0, 0.7, 22.0, 0.90, 10, 300);

        double jwt = input.businessMs() + input.jwtVerifyMs();
        double opaque = input.businessMs()
                + input.introspectionMs();
        double missRate = 1.0 - input.cacheHitRate();
        double opaqueCached = input.businessMs()
                + missRate * input.introspectionMs();

        long rawIdpQps = input.requestsPerSecond();
        long cachedIdpQps = Math.round(
                input.requestsPerSecond() * missRate);

        double inFlight = rawIdpQps
                * input.introspectionMs() / 1000.0;
        double inFlightCached = cachedIdpQps
                * input.introspectionMs() / 1000.0;

        System.out.printf(Locale.ROOT,
                "jwt_warm_avg_ms=%.1f%n", jwt);
        System.out.printf(Locale.ROOT,
                "opaque_no_cache_avg_ms=%.1f%n", opaque);
        System.out.printf(Locale.ROOT,
                "opaque_cached_avg_ms=%.1f%n", opaqueCached);
        System.out.printf(Locale.ROOT,
                "idp_qps_no_cache=%d%n", rawIdpQps);
        System.out.printf(Locale.ROOT,
                "idp_qps_cached=%d%n", cachedIdpQps);
        System.out.printf(Locale.ROOT,
                "intro_in_flight_no_cache=%.1f%n", inFlight);
        System.out.printf(Locale.ROOT,
                "intro_in_flight_cached=%.2f%n", inFlightCached);
        System.out.println("cache_stale_bound_s="
                + input.cacheTtlSeconds());
        System.out.println("jwt_local_revocation_bound_s="
                + input.jwtRemainingSeconds());
    }
}
~~~

Chạy từ thư mục lưu file:

~~~bash
javac TokenTradeoffModel.java
java TokenTradeoffModel
~~~

**Stdout được tính trực tiếp từ code:**

~~~text
jwt_warm_avg_ms=5.7
opaque_no_cache_avg_ms=27.0
opaque_cached_avg_ms=7.2
idp_qps_no_cache=1200
idp_qps_cached=120
intro_in_flight_no_cache=26.4
intro_in_flight_cached=2.64
cache_stale_bound_s=10
jwt_local_revocation_bound_s=300
~~~

Phần `cache_stale_bound_s` chỉ là **cửa sổ stale tối đa do một tầng positive cache TTL** trong mô hình lý tưởng: chưa tính IdP propagation, clock skew, network outage, nhiều cache layers hay trường hợp policy cố dùng stale-on-error. `jwt_local_revocation_bound_s` chỉ là **thời gian còn lại của JWT** giả định không có denylist, token version, introspection hay online policy. Không dùng hai giá trị này làm SLA production khi chưa đo.

Thay `cacheHitRate`, `introspectionMs` và `requestsPerSecond` để khảo sát độ nhạy. Một cache hit 99% không đảm bảo an toàn nếu tổ chức yêu cầu thu hồi quyền trong **dưới 2 giây**.

## 7. Phụ thuộc mạng và tính sẵn sàng: “JWT offline” cũng có giới hạn

### 7.1. Opaque no-cache: IdP nằm trên critical path

Khi dùng introspection, resource server cần:

1. Resolve DNS/TCP/TLS tới IdP qua mạng tin cậy.
2. Authenticate bằng client credentials (hoặc phương thức IdP quy định).
3. Gửi token qua HTTPS, nhận response hợp lệ.
4. Kiểm `active`, mapping scope và các ràng buộc resource server.
5. Tiếp tục business nếu authentication/authorization pass.

Nếu IdP mất mạng, resource server **không xác minh được token mới/uncached**. Theo nguyên tắc an toàn, **fail closed**, không chuyển network timeout thành “token active”. Cần định nghĩa response 503/502 cho hạ tầng khi phù hợp; mặc định framework có thể map lỗi khác nhau theo exception handling. Không ép tất cả introspection timeout thành 401 invalid_token vì lỗi đó không nói token bị revoke.

### 7.2. JWT warm: không cần IdP trên mỗi request

Khi cached JWK còn phù hợp, JWT local verification có thể tiếp tục xác minh cả khi IdP tạm down. Nhưng:

- Một token được ký bằng **key mới** mà API chưa có thể bị từ chối khi JWKS refresh thất bại.
- Lần request đầu có thể cần metadata/JWK discovery tùy cấu hình.
- Public key rotation/key removal không lan tới API đúng lúc có thể gây fail/mất an toàn.
- Nếu JWT cần online revocation/policy service ở mỗi request, kiến trúc **lại phụ thuộc mạng**.
- Nếu issuer sử dụng encryption/JWE mà decoder không hỗ trợ, local JWT path không chạy chỉ vì token có format giống JWT.
- Nếu `aud` hoặc `iss` sai, verify signature không đủ để accept.

Vì vậy câu đúng là: **JWT local verification với trusted key cache giảm phụ thuộc IdP trên warm path**, không phải “JWT vĩnh viễn độc lập với IdP”.

### 7.3. Ví dụ availability budget có giả định độc lập

Giả sử resource server đạt availability 99,9% và introspection service đạt 99,9%, giả sử **hai sự cố độc lập** và mọi request opaque no-cache phải thành công ở cả hai.

~~~text
A_joint = A_api * A_introspection
        = 0.999 * 0.999
        = 0.998001
        = 99.8001 %
~~~

Đây là **mô hình đơn giản**, không phải một SLA được đo. Trong thực tế các failure có thể **tương quan** (cùng region, DNS, network hoặc certificate infrastructure), và API còn phụ thuộc database/cache/business service. Không nhân xác suất tùy tiện rồi coi như dự báo chính xác. Mục tiêu là thấy mỗi online dependency trên critical path đều có **availability budget**.

Ở đường JWT warm, nếu IdP down mà JWKS vẫn cache hợp lệ, IdP không còn là dependency per-request trong khoảng đó; nhưng phải đo riêng cold start, key rotation và revocation policy.

### 7.4. Retry, circuit breaker, timeout

Với introspection, các quyết định cần rõ ràng:

| Tình huống | Hành động gợi ý |
| --- | --- |
| `active=false` hợp lệ | Từ chối token, **không retry** để “xin active=true” |
| IdP trả HTTP 401 cho introspection client | Kiểm secret/auth method, không retry vô hạn bằng cùng secret |
| Timeout | Có deadline ngắn, circuit breaker/rate limiting; fail closed |
| 429 | Tôn trọng rate limit và retry budget, tránh bão token |
| 503 tạm thời | Có thể retry **cực kỳ có giới hạn** khi token check là operation an toàn với IdP, không giữ request đến vô hạn |
| JSON introspection không đúng schema | Không coi token active |
| JWKS key rotation | Quản lý cache/refresh và giám sát, không tắt JWT signature validator |
| JWT không hợp lệ chữ ký | 401, không fallback “decode payload” |

**Không dùng `retryWhen(Retry.indefinitely())` để làm introspection.** Nếu IdP chậm, retry lồng nhau ở WebClient, gateway, service mesh và IdP proxy sẽ làm tải nhân lên, khiến chính outage kéo dài. Fail closed là yêu cầu security; xử lý trải nghiệm 5xx và retry của client theo contract riêng.

## 8. Thu hồi token: so sánh độ trễ có hiệu lực

### 8.1. Ba khái niệm hay bị lẫn

- **Token hết hạn:** `exp` tới hạn, kiểm thời gian không còn cho phép dùng token.
- **Token bị thu hồi:** IdP hoặc policy đánh dấu token không active **trước `exp`**; cần kênh xác minh nào đó để API biết.
- **Đổi quyền/account status:** user bị khóa hay mất role; có thể ảnh hưởng token hiện tại **nếu IdP/introspection và policy được thiết kế** để cập nhật metadata hoặc trả inactive. Không có bảo đảm chung rằng mọi claim `scope` tự thay đổi tức thì sau khi admin sửa role.

### 8.2. Timeline thu hồi

~~~text
T0: Authorization Server phát token, exp = T0 + 15 phút
T1: Security team revoke token ngay khi phát hiện bị lộ

Opaque introspection NO CACHE:
    request sau T1 -> IdP trả active=false (sau propagation)
    -> API từ chối, không cần chờ exp

Opaque introspection CACHE positive 30 giây:
    request trước T1 cache active=true
    request sau T1 có thể vẫn hit cache
    -> API có thể chấp nhận trong cửa sổ TTL còn lại
    -> khi cache hết hạn, phải introspect lại, thấy inactive

JWT local-only (không denylist, online check):
    signature/iss/nbf/aud/exp vẫn hợp lệ
    -> API có thể chấp nhận đến exp,
       dù IdP đã đánh dấu revoked tại T1
~~~

**Giới hạn:** IdP không nhất thiết đồng bộ revocation tức thời giữa mọi region; DB/event propagation, issuer policy và các tầng cache khác cũng tạo độ trễ. Khi nói “opaque gần real-time” phải đo `T_revocation_to_first_401` trong hệ thống thật, không chỉ đọc thông số TTL.

### 8.3. Công thức cửa sổ revocation

Dùng ký hiệu:

- `D_as`: delay để IdP/introspection phản ánh revoke.
- `D_cache`: thời gian positive cache còn hiệu lực sau T1.
- `D_jwt`: thời gian còn lại tới token `exp`, sau tính clock skew.
- `D_events`: delay của denylist/token version/push revocation event, nếu tồn tại.

Trong **mô hình không fail-open**, các khoảng gần đúng:

~~~text
Opaque no cache:
  revoke_exposure ≈ D_as + propagation/network nhỏ

Opaque cached:
  revoke_exposure ≲ D_as + D_cache
  (nếu không có stale-on-error và TTL hữu hạn)

JWT local-only:
  revoke_exposure ≲ D_jwt
  (có thể được cắt ngắn bởi denylist/online check)

JWT with revocation event:
  revoke_exposure phụ thuộc D_events + local policy/cache
  (không chỉ phụ thuộc exp)
~~~

Các dấu bất đẳng thức chỉ là **mô hình đơn giản**. Cache refresh xảy ra ngay trước khi IdP hoàn tất propagation có thể kéo dài stale window thêm một TTL; token time skew, replication và stale-while-error có thể làm trễ hơn. SLA thực tế phải tính **hợp đồng của Authorization Server và tất cả cache layers**.

### 8.4. Token TTL ngắn có phải revocation hoàn hảo?

Không. JWT access token 5 phút giới hạn exposure tối đa theo `exp` và clock skew trong mô hình local-only, nhưng 5 phút có thể vẫn không đáp ứng yêu cầu “khóa tài khoản có hiệu lực dưới 10 giây”. Ngược lại, opaque token có thể có TTL dài nhưng bị revoke và introspect ngay — nếu endpoint và đồng bộ trạng thái đủ nhanh.

JWT ngắn hạn cần cơ chế **refresh token** để UX không liên tục bắt login. Refresh token thường được giữ ở OAuth2 Client/Authorization Server, có quy tắc revoke và rotation riêng. **Không** dùng ID Token làm access token để đổi TTL một cách tùy tiện.

## 9. Caching introspection: tối ưu latency nhưng tăng stale window

### 9.1. RFC 7662 cho phép caching, không yêu cầu cache

RFC 7662 `4` nêu rõ resource server **có thể cache** response introspection nhưng phải cân nhắc performance/security tradeoff; **nếu response có `exp` thì không được cache vượt quá `exp`**. Do đó:

~~~text
ttl_effective = min(
    configured_positive_cache_ttl,
    max(0, token_exp - now - allowed_clock_skew)
)
~~~

Đây là biểu thức policy gợi ý. Với token không có `exp`, phải đặt upper bound thời gian bảo mật riêng; không cache vô hạn. Không lấy giá trị `expires_at` hay `exp` không được validate làm TTL dài.

### 9.2. Cache hit rate không chỉ do TTL

Hit rate phụ thuộc:

- Số request mỗi token trong TTL.
- Số lượng tokens unique/giây.
- Cache local mỗi pod hay shared Redis.
- Load balancing sticky hay round-robin.
- Eviction policy/size memory.
- Thời gian thực `exp` còn lại.
- Cache key normalization và partition theo issuer/audience.
- Quá trình refresh token làm xuất hiện token mới.
- Negative caching, token brute-force và cache penetration.

Ví dụ hai hệ thống đều 1.200 requests/s:

- Hệ thống A có 12 service clients dùng token ổn định, mỗi token gọi API rất nhiều trong 10 giây → cache hit có thể cao.
- Hệ thống B có 1.200 người dùng mỗi người dùng một token khác nhau một lần → cache hit thấp dù QPS tương tự.

Không dùng một hit rate đo từ test một-user để dự báo production có hàng triệu unique tokens.

### 9.3. Tầng cache và vị trí lưu

| Cách lưu | Latency | Consistency | Điểm cần lưu ý |
| --- | --- | --- | --- |
| Không cache | Tăng RTT IdP mỗi request | Trạng thái mới nhất theo IdP | Tải cao, fail closed khi network mất |
| JVM-local cache | Hit rất nhanh | Mỗi pod giữ TTL riêng | Rollout/scale tạo cold misses, revoked có thể stale nhiều pod |
| Redis/shared cache | Hit có thêm network | TTL chia sẻ, có thể invalidate theo event | Redis là dependency mới, cần TLS/auth/availability |
| CDN/edge cache introspection | Ít phù hợp nếu không kiểm key/quyền chặt | Nguy cơ token metadata/PII bị chia sẻ | Chỉ dùng nếu có thiết kế security đặc biệt |
| Cache token verdict đến hết exp | QPS IdP thấp | Revocation có thể chậm như JWT local | Mất phần lớn lợi ích thu hồi gần real-time |

**Cache key không được lộ raw token** trong key observability. Nếu cần lưu, sử dụng HMAC/SHA-256 có secret key riêng theo threat model, tránh va chạm và cache poisoning; hạn chế quyền đọc cache. Cache value có thể chứa claims/PII, cần bảo vệ dữ liệu nhạy cảm và TTL tuyệt đối.

### 9.4. Không dùng Mono.cache() như cache toàn hệ thống

~~~java
// Anti-pattern nếu mong cache dùng chung nhiều request:
@Override
public Mono<OAuth2AuthenticatedPrincipal> introspect(String token) {
    return delegate.introspect(token).cache();
}
~~~

Mỗi lần gọi method có thể tạo **Mono mới**, `cache()` chỉ memoize trên publisher instance đó, không tự tạo global keyed cache theo token. Muốn cache across requests cần một component có key, eviction, TTL, concurrency, negative/positive policy và invalidation.

### 9.5. Cache negative responses và lỗi mạng

`active=false` có thể được cache rất ngắn để giảm brute-force/garbage-token load **chỉ nếu policy cho phép**. Không cache network timeout/HTTP 503 như `active=false` lâu dài — đó là sự cố IdP, không phải quyết định token invalid. Cũng không cache error rồi tự **allow token** khi upstream down trừ khi đã được security review cực kỳ đặc biệt; mặc định nên fail closed.

### 9.6. Tính toán trade-off cache TTL

Giả sử requirement “token bị revoke phải bị chặn trong **không quá 15 giây**”:

- Nếu introspection replication lag worst-case 5 giây và positive cache TTL 30 giây, **không thể cam kết** 15 giây.
- Nếu cache TTL 3 giây và replication lag 5 giây, vẫn cần kiểm scheduler/propagation/tail để kết luận, nhưng ngân sách tổng 8 giây lý thuyết có thể để chỗ cho jitter.
- Nếu JWT local có access token TTL 10 phút, không có revocation check, thì không thể cam kết 15 giây bằng cách giảm JWKS cache TTL. JWKS cache là **cache public keys**, không phải cache quyết định token active.

Cần đo worst-case và P99, không chỉ nhìn các giá trị lý thuyết.

## 10. Ví dụ Spring Boot 4.1.x: cùng API, hai chiến lược

Bài demo tạo **một** ứng dụng WebFlux với **hai profile loại trừ nhau**: `jwt` và `opaque`. Cùng endpoint `GET /api/data` đòi `SCOPE_data.read`; chỉ cách resource server xác minh Bearer token thay đổi.

**Điều kiện chạy end-to-end:** phải có Authorization Server thật phát JWT cho profile `jwt` hoặc cấp opaque token/introspection credentials cho profile `opaque`. Demo không tự phát token, không đưa hard-coded token “admin” vào production, không giả vờ kiểm chứng IdP offline.

### 10.1. Maven pom.xml

Dùng Java **17+**, Maven, Spring Boot **4.1.2**, Spring Reactive Web, Spring Security và resource server. Ở Spring Boot 4, tên starter chuẩn cho OAuth2 Resource Server là `spring-boot-starter-security-oauth2-resource-server`.

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.1.2</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>token-strategy-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security-oauth2-resource-server</artifactId>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**Không** trộn với `spring-boot-starter-web` của Servlet khi dạy WebFlux. Không cần thêm OAuth2 Client registration chỉ để API nhận Bearer token; OAuth2 Client là bên đi xin và sử dụng token để gọi API, khác Resource Server.

### 10.2. Cấu hình theo profile

File `src/main/resources/application.properties`:

~~~properties
server.port=8080
~~~

File `src/main/resources/application-jwt.properties`:

~~~properties
spring.security.oauth2.resourceserver.jwt.issuer-uri=${JWT_ISSUER_URI}
spring.security.oauth2.resourceserver.jwt.audiences=${JWT_API_AUDIENCE}
~~~

File `src/main/resources/application-opaque.properties`:

~~~properties
spring.security.oauth2.resourceserver.opaquetoken.introspection-uri=${INTROSPECTION_URI}
spring.security.oauth2.resourceserver.opaquetoken.client-id=${INTROSPECTION_CLIENT_ID}
spring.security.oauth2.resourceserver.opaquetoken.client-secret=${INTROSPECTION_CLIENT_SECRET}
~~~

Những ký hiệu `${...}` trong phần soạn được chuyển thành property placeholders chuẩn Spring `$...` khi lưu Knowledge. **Đây là biến môi trường cần cung cấp ở runtime**, không phải secrets thật. `JWT_ISSUER_URI` là issuer của access token; `JWT_API_AUDIENCE` là audience dành cho API. Introspection URI phải dùng HTTPS và credentials được Authorization Server cấp riêng cho resource server.

Chỉ kích hoạt **một** profile `jwt` hoặc `opaque` mỗi lần chạy để không tạo hai `SecurityWebFilterChain` cùng match all. Với production, dùng secrets manager thay vì lưu client secret trong file source.

### 10.3. File Java đầy đủ

Tạo `src/main/java/com/example/tokenstrategy/TokenStrategyApplication.java`:

~~~java
package com.example.tokenstrategy;

import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Profile;
import org.springframework.http.MediaType;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@SpringBootApplication
@EnableWebFluxSecurity
public class TokenStrategyApplication {

    public static void main(String[] args) {
        SpringApplication.run(TokenStrategyApplication.class, args);
    }

    private static ServerHttpSecurity common(ServerHttpSecurity http) {
        return http
                .authorizeExchange(ex -> ex
                        .pathMatchers("/healthz").permitAll()
                        .pathMatchers("/api/data")
                                .hasAuthority("SCOPE_data.read")
                        .anyExchange().denyAll())
                .httpBasic(basic -> basic.disable())
                .formLogin(form -> form.disable());
    }

    @Bean
    @Profile("jwt")
    SecurityWebFilterChain jwtChain(ServerHttpSecurity http) {
        return common(http)
                .oauth2ResourceServer(oauth2 ->
                        oauth2.jwt(Customizer.withDefaults()))
                .build();
    }

    @Bean
    @Profile("opaque")
    SecurityWebFilterChain opaqueChain(ServerHttpSecurity http) {
        return common(http)
                .oauth2ResourceServer(oauth2 ->
                        oauth2.opaqueToken(Customizer.withDefaults()))
                .build();
    }

    @RestController
    static class Api {

        @GetMapping(value = "/healthz",
                produces = MediaType.APPLICATION_JSON_VALUE)
        Mono<Map<String, String>> healthz() {
            return Mono.just(Map.of("status", "UP"));
        }

        @GetMapping(value = "/api/data",
                produces = MediaType.APPLICATION_JSON_VALUE)
        Mono<Map<String, String>> data() {
            return Mono.just(Map.of("result", "DATA_OK"));
        }
    }
}
~~~

**Tại sao code tách theo profile?**

- `@Profile("jwt")` tạo chain dùng `ReactiveJwtDecoder` và trusted JWKS. Đây là nhánh local verification.
- `@Profile("opaque")` tạo chain dùng `ReactiveOpaqueTokenIntrospector` và introspection URI. Đây là nhánh online validation.
- Cả hai dùng chính sách `hasAuthority("SCOPE_data.read")` giống nhau, nên so sánh latency không bị lẫn logic authorization.
- `/healthz` được public để kiểm process khi chưa có token; một Bearer token lỗi cố ý gửi vào public route vẫn có thể bị auth filter từ chối, nên test health **không gắn Authorization**.
- `formLogin`/`httpBasic` bị disable, chỉ dùng Bearer auth. Không khai báo cookie/session login. Demo có **GET**; không tự suy rằng CSRF luôn được tắt/không cần trên API khác.
- Không hard-code issuer, secret hoặc role; Spring Boot lấy config theo profile.
- Không gọi `.block()`, dùng reactive `Mono` trong controller.
- `Map.of` không bảo đảm thứ tự key JSON, test nên so field `result`.

**Giới hạn:** chương trình sẽ biên dịch khi resolved Spring Boot/Security dependencies tương thích, nhưng **để chạy xác minh Bearer thật**, cần issuer/JWKS hoặc introspection endpoint của IdP. Không suy diễn rằng chỉ chạy `mvn spring-boot:run` khi chưa có IdP sẽ chứng minh JWT/opaque hiệu năng.

### 10.4. Chạy profile JWT

Giả sử token JWT hợp lệ đã được IdP cấp cho audience và scope đúng:

~~~bash
export SPRING_PROFILES_ACTIVE=jwt
export JWT_ISSUER_URI='https://issuer.example.com/realms/company'
export JWT_API_AUDIENCE='api.example.com'
./mvnw spring-boot:run
~~~

Địa chỉ trên là **issuer minh họa**, phải thay bằng issuer thực tế. Kiểm kết quả:

~~~bash
curl -i http://localhost:8080/healthz
curl -i http://localhost:8080/api/data
curl -i -H "Authorization: Bearer $JWT_ACCESS_TOKEN" \
  http://localhost:8080/api/data
~~~

Khi `JWT_ACCESS_TOKEN` có chữ ký, issuer, audience, thời gian và `scope=data.read` hợp lệ, endpoint cuối trả HTTP **200** với `{"result":"DATA_OK"}`. Không có token → thường **401**; token valid nhưng không có `SCOPE_data.read` → thường **403**. Nếu JWT bị sửa signature hoặc sai audience → **401**.

**JWT_ACCESS_TOKEN** chỉ là tên biến môi trường cần được set bằng credential thực; không in token ra màn hình hoặc commit vào Git.

### 10.5. Chạy profile opaque

Dừng process JWT trước, đổi profile:

~~~bash
export SPRING_PROFILES_ACTIVE=opaque
export INTROSPECTION_URI='https://issuer.example.com/oauth2/introspect'
export INTROSPECTION_CLIENT_ID='resource-server-id'
export INTROSPECTION_CLIENT_SECRET='secret-issued-by-idp'
./mvnw spring-boot:run
~~~

Các giá trị này là ví dụ; phải thay bằng introspection URI và credential thật. Kiểm:

~~~bash
curl -i http://localhost:8080/healthz
curl -i http://localhost:8080/api/data
curl -i -H "Authorization: Bearer $OPAQUE_ACCESS_TOKEN" \
  http://localhost:8080/api/data
~~~

Nếu token introspect active và có `data.read` scope, response 200 `DATA_OK`; token inactive/expired/revoked → thường **401**; active nhưng thiếu scope → thường **403**.

**Quan trọng:** profile `opaque` không cố gắng decode token thành JWT, còn profile `jwt` không gửi token tới introspection endpoint trên warm path. Việc dùng cùng ứng dụng/controller giúp benchmark tập trung vào **verification strategy** thay vì business endpoint khác nhau.

### 10.6. Windows PowerShell

PowerShell đặt biến bằng `$env:SPRING_PROFILES_ACTIVE="jwt"`, `$env:JWT_ISSUER_URI="..."` và `$env:JWT_API_AUDIENCE="..."`. Chạy `.\mvnw.cmd spring-boot:run`. Với curl, dùng `curl.exe` nếu `curl` bị alias thành `Invoke-WebRequest`. Không truyền token vào URL; khi chạy benchmark có thể cần secret injection thay vì lệnh command-line xuất hiện trong process list.

## 11. Thiết kế benchmark có ý nghĩa

### 11.1. Giữ cố định mọi yếu tố không cần so sánh

- Cùng Spring Boot/Spring Security version, Java version, container CPU/memory.
- Cùng application handler, JSON serialization, downstream dependencies.
- Cùng region/zone network, HTTP connection pool, TLS/proxy topology.
- Cùng payload request/response, JWT signing algorithm phù hợp và token size.
- Cùng scope/authority mapping; kiểm audience/issuer như production.
- Cùng concurrency/QPS pattern và tỷ lệ token unique.
- Cùng GC warmup, JWKS warmup, IdP introspection warmup.
- Đo riêng cold-start/JWKS rotation; không gộp chúng vào warm P99 rồi gọi chung.
- Thực hiện nhiều vòng lặp, có confidence interval và ghi rõ sample count.

**Không benchmark** bằng introspection mock `Mono.just(principal)` rồi so với JWT signature thật; như vậy bỏ toàn bộ network/IdP lookup và không đo được câu hỏi đề bài. Ngược lại, cũng không dùng database business nặng khác nhau để so hai lựa chọn.

### 11.2. Thiết kế ba workload

| Workload | Token distribution | Mục tiêu |
| --- | --- | --- |
| A: một token nóng | 1 token dùng lại ở nhiều requests | Cache introspection có lợi nhất, đo reuse |
| B: nhiều token | Mỗi user/token ít request | Đo miss rate gần production |
| C: token rotation/revocation | Tokens được đổi/revoke trong lúc chạy | Đo stale window, failed requests, key refresh |

Chạy mức tải ví dụ 50, 200, 800, 1500 QPS **theo khả năng hạ tầng được cho phép**, không bắn load test vào IdP bên thứ ba không có phê duyệt. Nếu IdP có quota, phối hợp với chủ sở hữu để tránh bị rate limit gây outage.

### 11.3. Các mốc đo

| Metric | JWT local | Opaque no-cache | Opaque cached |
| --- | --- | --- | --- |
| End-to-end P50/P95/P99 | Đo | Đo | Đo |
| Token verification duration | Crypto + validators | Network + parse | Cache lookup hoặc network |
| IdP requests/s | JWK/discovery | ~bearer QPS | ~cache misses |
| Cache hit/miss | JWKS cache | 0/không áp dụng | Positive/negative hit |
| Error 401/403 | Signature/claim/authority | inactive/authority | stale/authority |
| IdP 429/5xx/timeout | Cần theo dõi JWKS | Trực tiếp ảnh hưởng | Miss trực tiếp ảnh hưởng |
| Revocation-to-first-deny | Theo exp hoặc online check | Theo IdP propagation | Theo cache TTL + propagation |
| Key rotation failure | Quan trọng | Không có JWKS local check nếu chỉ introspect | Không có JWT-JWKS local check |
| Connection pool saturation | Ít trên warm JWT path | Có | Theo miss rate |

**Measurement hygiene:** không log raw access token, bearer header, introspection client secret hoặc JWT claims chứa PII để gắn vào metric. Dùng hashed/opaque test IDs để ghép traces khi cần.

### 11.4. Chaos test IdP network partition

Với môi trường thử nghiệm có phép:

1. Chạy request warm JWT và opaque thành công; ghi baseline.
2. Chặn **chỉ đường tới introspection endpoint**.
3. Xác minh opaque no-cache **fail closed**; không silently accept.
4. Xác minh JWT warm có key cache hợp lệ **có thể** tiếp tục verify, song vẫn bị giới hạn bởi downstream dependencies.
5. Chặn JWKS endpoint rồi phát JWT ký bằng key mới: JWT có thể fail khi decoder không thể lấy key mới; kiểm alert.
6. Bật cache opaque TTL 5 giây; xem hit còn thành công tạm thời nếu token đã được cache, miss phải fail closed.
7. Thu hồi một token rồi đo thời gian request bắt đầu nhận 401/deny theo cơ chế IdP.
8. Khôi phục IdP, xác minh circuit breaker half-open và QPS không tạo retry storm.

Đừng bật fail-open để “đạt mục tiêu availability” khi bài toán bảo mật đòi hỏi token được kiểm tra online. Nếu hệ thống chấp nhận stale-on-error, đó là **quyết định rủi ro được phê duyệt**, có TTL cứng, scope giới hạn và audit; không phải mặc định của Spring Security.

## 12. Revocation test: cần test theo đồng hồ thực

### 12.1. Kịch bản token bị revoke

Trong một môi trường test có IdP hỗ trợ token revocation:

~~~text
T0 cấp token và gọi /api/data => 200
T1 gọi IdP revoke token / disable account
T2 cứ mỗi giây thử /api/data bằng token cũ
T3 lần đầu API từ chối token => 401 hoặc policy-specific deny

Observed revocation lag = T3 - T1
~~~

Với JWT local-only, nếu token vẫn signature/issuer/audience/exp hợp lệ, thường API **tiếp tục 200** cho đến `exp` trừ khi có denylist/online policy. Với opaque no-cache, API có thể từ chối ở request ngay sau khi IdP thể hiện `active=false`; với opaque cache, chờ cache TTL/invalidation.

**Không dùng một POST có side effect** để đo revoke mỗi giây. Dùng GET chỉ đọc để không tạo giao dịch trùng hoặc thay đổi dữ liệu thật.

### 12.2. Biến cố thu hồi không phải lúc nào là token revoked

Khi quản trị viên thay role, IdP có thể giữ access token đã cấp với scope snapshot đến khi token hết hạn. Một introspection endpoint có thể vẫn báo `active=true` và scope cũ theo policy. Do đó đo **hai việc riêng**:

- Token revoked → `active=false` sau bao lâu?
- User role/account disabled → introspection/JWT authority được cập nhật **theo quy ước nào**?

Không cam kết opaque sẽ tự cập nhật scope ngay chỉ vì introspection online; nó phụ thuộc **semantics IdP và nguồn dữ liệu introspection**.

### 12.3. JWT revocation options

| Cơ chế bổ sung | Hiệu ứng | Đánh đổi |
| --- | --- | --- |
| JWT TTL ngắn | Giới hạn thời gian token cũ còn được dùng | Tăng tần suất refresh, UX/IdP load |
| Denylist theo `jti` | Chặn token cụ thể trước exp | State store/network/cache mới; cần bảo mật ID |
| Token version per user | Khóa toàn bộ token cũ khi version thay | Cần online/cache lookup |
| Event push revocation | Cập nhật denylist/policy cache | Event reliability, propagation lag |
| Online introspection cho JWT | AS quyết định active tại request | Mang trade-off latency/availability của opaque |
| High-risk endpoint online check | Chỉ ràng buộc action nhạy cảm | Policy phức tạp, cần bảo đảm không bypass |

**Không rotate toàn bộ signing key** chỉ để revoke một access token của một user: key có thể đang ký rất nhiều JWT hợp lệ và rotation không đồng nghĩa mọi resource server sẽ cập nhật ngay.

## 13. Bảo mật khi xây hệ thống introspection

### 13.1. Token introspection endpoint phải an toàn

Theo RFC 7662, protected resource gửi token trong HTTP POST form, authentication của resource server tới introspection endpoint theo cơ chế AS yêu cầu. Cần:

- HTTPS/TLS với certificate đáng tin; không dùng trust-all SSL context.
- Chỉ allowlist IdP hostname, không lấy introspection URL từ token hoặc user query (tránh SSRF).
- Secret manager/mTLS/private_key_jwt nếu IdP hỗ trợ, rotation, audit.
- Timeout, connection pool và circuit breaker để không giữ vô hạn request Netty.
- Chỉ nhận response `active` boolean đúng schema và metadata thuộc issuer/client/audience.
- Không trả raw introspection response hoặc client secret ra API public.
- Không đưa token vào URL/query parameter, URL logs hay analytics.
- Nếu cache, bảo vệ keys và values (PII), TTL, eviction và revocation event.
- Không để API B dùng introspection permission của API A để nhận token thuộc namespace không liên quan.

### 13.2. JWT local verification cũng có trust boundary

- Chỉ tin issuer/JWK Set URI được cấu hình, không tin `jku`/`x5u` tùy ý trong token header.
- Chỉ chấp nhận các signature algorithms do policy cho phép, không chấp nhận unsigned token.
- Verify `iss`, `aud`, `exp`, `nbf` và constraints của profile JWT access token.
- Bảo vệ JWKS cache, xử lý key rotation, key revoke và stale keys có policy.
- Không đưa PII nhạy cảm/secret trong JWS payload vì client có thể đọc.
- Không coi ID Token là access token nếu contract resource server không cho phép.
- Không map `ROLE_ADMIN` từ một claim do end user tự sửa được.
- Không bỏ qua authorization chỉ vì authentication thành công.

### 13.3. Authentication 401 khác Authorization 403

| Tình huống | HTTP thông thường | Ý nghĩa |
| --- | --- | --- |
| Không gửi Bearer tới protected route | 401 | Chưa authentication |
| Opaque `active=false` | 401 | Token không được chấp nhận |
| JWT signature invalid/expired/wrong audience | 401 | Token invalid |
| Token hợp lệ nhưng thiếu `SCOPE_data.read` | 403 | Authentication pass, authorization deny |
| Introspection endpoint timeout | Lỗi hạ tầng/response theo handler | Không coi là token valid |
| Business validation sau auth | 4xx/5xx theo nghiệp vụ | Không tự kết luận là lỗi JWT/opaque |

Đối với request 401/403, xem `WWW-Authenticate` để phân biệt `invalid_token` và `insufficient_scope` khi server cung cấp. Không chỉ dựa vào response body mặc định của một version Spring Security.

## 14. Anti-pattern và cách khắc phục

### 14.1. “JWT nhanh hơn opaque 10 lần” mà không đo

Đây là một phát biểu không có giá trị phổ quát. RTT, locality, cache, crypto algorithm, payload, workload đều thay đổi. Phải đo cùng SLO, warm/cold cache và P95/P99.

### 14.2. “JWT không bao giờ cần IdP”

JWKS discovery/refresh và rotation có thể cần mạng. Nếu thêm online policy/revocation, JWT path có thể mất lợi thế network; phải đo theo kiến trúc thực.

### 14.3. “Opaque luôn được revoke tức thì”

Kết quả có thể chậm do IdP replication, positive cache, polling interval và app retries. Không hứa latency revoke nếu chưa đo `revocation-to-first-deny`.

### 14.4. “Cache introspection tới exp là tối ưu”

Nếu TTL tới expiry dài, revoked token có thể tiếp tục được chấp nhận. RFC 7662 cho phép cache nhưng cảnh báo stale; TTL phải theo risk budget.

### 14.5. “Khi IdP timeout thì bỏ qua xác minh”

Không tạo `OAuth2AuthenticatedPrincipal` khi chưa biết token active. Đây là **fail-open** và có thể tạo truy cập trái phép.

### 14.6. “Có access token JWT nên chỉ cần decode”

Base64URL decode không verify JWS signature, `iss`, `aud`, `exp`. Sử dụng `ReactiveJwtDecoder` với trusted validators.

### 14.7. “HTTP 403 chứng minh token bị revoke”

Không. 403 thường do valid token thiếu scope/authority; token invalid thường bị chặn ở authentication (401). Phải test riêng.

### 14.8. “Không có caching nên IdP sẽ chịu nổi peak”

Introspection có thể biến 1000 API RPS thành 1000 extra IdP RPS; cần load/capacity test và rate limit. Đừng thử quá tải IdP chung của công ty.

### 14.9. “Thay OpaqueTokenIntrospector Servlet trong WebFlux”

WebFlux cần `ReactiveOpaqueTokenIntrospector` và reactive `ServerHttpSecurity`. Không `block()` trong request thread/event loop.

### 14.10. “JWKS TTL giảm là JWT revoke nhanh hơn”

JWKS cache lưu **public signing keys**, không lưu trạng thái revoke từng access token. Giảm TTL JWKS tăng dependency IdP mà không giải quyết per-token revocation.

### 14.11. “Cache hit rate cao thì P99 chắc nhanh”

10% miss có thể chi phối P95/P99 dù average thấp. Phải báo riêng hit/miss latency và tail metrics.

### 14.12. “Revocation lúc T1 thì ngay sau đó introspection trả active=false toàn cầu”

Replication/region lag có thể làm nhận `active=true` một thời gian. Test multi-region và hợp đồng IdP.

### 14.13. “Dùng token trong URL để dễ benchmark”

Bearer token trong URL dễ lộ qua access logs, browser history và Referer. Dùng header HTTPS; khi benchmark tránh in full Authorization.

### 14.14. “Đo throughput bằng @MockBean introspector nhưng gọi là đo network”

Fake introspector trả `Mono.just(principal)` không thực hiện HTTP, không đo network, rate limit hay IdP state; chỉ phù hợp test authentication/authorization logic.

### 14.15. “Bật nhiều SecurityWebFilterChain match-all để hỗ trợ cả hai”

Hai chain match-all thiếu `@Order`/matcher có thể làm một chain nuốt request của chain kia. Trong bài demo dùng **profile loại trừ**, hoặc ở production cần cấu hình explicit paths/securityMatcher và thiết kế migration rõ.

## 15. Ma trận quyết định kiến trúc

| Tình huống | Nghiêng về | Điều kiện cần |
| --- | --- | --- |
| API throughput rất cao, yêu cầu latency thấp | JWT local verification | JWKS/alg/iss/aud đúng; token TTL và revocation SLA chấp nhận |
| Cần revoke token gần thời gian thực | Opaque no-cache introspection | AS propagation nhanh, endpoint HA và latency budget |
| API nhạy cảm, có online policy service | Introspection hoặc hybrid | Mọi path high-risk phải check online/fail closed |
| Nhiều microservices ở nhiều region | JWT cho phần lớn requests, online check selective | Quản lý keys, TTL, audience isolation, incident rollback |
| IdP ở xa, RTT lớn, endpoint SLA thấp | JWT warm hoặc introspection cache được cân nhắc | Không bỏ yêu cầu revocation, phải đo tail |
| IdP có thể cấp introspection nhưng không JWT phù hợp | Opaque | Đủ capacity/HA, client auth/TLS, resource restrictions |
| JWT đã phát nhưng cần kiểm revoke trên mỗi request | Introspect JWT qua opaque support | Cấu hình theo verification method, không tin format |
| Chỉ cho phép stale quyền tối đa 5 giây | Opaque TTL cực ngắn hoặc online policy | Đo IdP replication & TTL và P99 |
| Sợ token payload lộ claims nhạy cảm | Opaque hoặc JWT tối thiểu claims/encrypted profile | Không nhầm “opaque” với chống lộ Bearer token |
| IdP outage phải không làm mọi endpoint dừng | JWT warm với local policy khi phù hợp | Chấp nhận revocation delay; đo JWKS cold/rotation |

**Không có đáp án cố định**. Với một hệ thống có dữ liệu đọc ít nhạy cảm và giao dịch đổi thông tin tài khoản, có thể dùng JWT local cho read operations, còn write operations high-risk kiểm policy online. Nhưng phải chứng minh đường online check không bị bypass và mọi loại token đều được cấp cho đúng audience.

## 16. Checklist production

1. Xác định định dạng token và **phương thức xác minh** riêng, không suy từ dấu chấm của chuỗi.
2. Với WebFlux, dùng `ServerHttpSecurity`, `ReactiveJwtDecoder` hoặc `ReactiveOpaqueTokenIntrospector`, không dùng Servlet API.
3. Validate JWT chữ ký/trusted algorithm, `iss`, `aud`, `exp`, `nbf`, scope và tenant.
4. Với introspection, dùng TLS/HTTPS, client auth hợp lệ, kiểm `active` và policy audience/resource.
5. Biết token revocation SLA thực tế là bao nhiêu giây và ai chịu trách nhiệm cung cấp.
6. Đo P50/P95/P99 verification và API latency; không dùng số minh họa làm benchmark.
7. Có số IdP calls/s, cache hit/miss, distinct tokens/s và retry/timeout metrics.
8. Có mô hình capacity/concurrency theo peak RPS và RTT; tính thêm pool queue/saturation.
9. Với JWT, kiểm cold JWKS/rotation/outage, không chỉ warm path.
10. Với opaque, có timeout, circuit breaker, rate-limit handling, no infinite retry.
11. Fail closed khi introspection unavailable, không tự cấp authenticated principal.
12. Nếu cache introspection, TTL không vượt `exp` theo RFC 7662 và không vượt risk budget.
13. Không log raw Bearer token, client secret, JWT claims nhạy cảm hoặc raw cache key.
14. Kiểm đủ 200/401/403, revoked, expired, insufficient_scope, wrong audience, IdP 503, JWT key rotation.
15. Kiểm hiệu lực revoke theo đồng hồ thực và theo region/cache layers.
16. Thống nhất trust boundary, không dùng ID Token thay access token.
17. Không để test credentials/issuer giả hoặc profile demo trong production.
18. Tài liệu hóa trường hợp hybrid để không bypass online check ở route nhạy cảm.
19. Có migration plan khi đổi opaque sang JWT hoặc ngược lại, đặc biệt về token cũ còn hạn.
20. Review quyết định lại sau khi IdP SLA, token TTL, traffic mix hoặc policy rủi ro thay đổi.

## 17. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao JWT warm verification thường nhanh hơn opaque no-cache?

**Đáp án:** JWT có thể verify chữ ký và claims tại API bằng trusted public key đã cache; opaque no-cache thường phải gửi token qua HTTPS tới introspection endpoint và chờ response.

**Câu 2.** Vì sao JWT không tuyệt đối “offline”?

**Đáp án:** JWKS discovery, cache miss, key rotation hoặc online revocation policy có thể cần mạng; lợi thế là không phải gọi IdP trên từng warm request.

**Câu 3.** 1.200 QPS và introspection 22ms cho số request đang chờ trung bình bao nhiêu trong mô hình đơn giản không cache?

**Đáp án:** `1200*0.022=26.4` theo Little's Law, trước khi xét queuing/saturation.

**Câu 4.** Cache introspection 90% khi 1.200 QPS làm IdP QPS ước tính còn bao nhiêu?

**Đáp án:** `1200*(1-0.90)=120` calls/s trong mô hình tỉ lệ hit ổn định.

**Câu 5.** Vì sao `active=true` chưa có nghĩa user xem được mọi API?

**Đáp án:** Cần kiểm resource audience/issuer/tenant và `SCOPE_*`/authority cho route; authenticated khác authorized.

**Câu 6.** Nếu opaque introspection cache TTL=30 giây, có thể cam kết revoke dưới 10 giây không?

**Đáp án:** Không nếu chỉ dựa vào TTL 30 giây và không có event invalidation; còn IdP replication lag.

**Câu 7.** Vì sao local JWT validation có thể vẫn chấp nhận token vừa revoke?

**Đáp án:** Chữ ký/claims vẫn hợp lệ đến `exp`; local verifier không tự có thông tin revocation từng token.

**Câu 8.** `Mono.cache()` trong introspect method có làm cache toàn API không?

**Đáp án:** Không mặc định; nếu mỗi invocation tạo Mono mới thì cache thuộc từng publisher instance, không keyed cache giữa requests.

**Câu 9.** Muốn giảm P99 opaque, chỉ tăng cache TTL có đủ?

**Đáp án:** Chưa chắc. Cần đo miss/IdP tail, token cardinality, connection pools và chấp nhận được stale window; tăng TTL làm revocation chậm.

**Câu 10.** IdP outage có được tự xem token opaque là active không?

**Đáp án:** Không theo chính sách an toàn mặc định. Fail closed, phân loại network outage, giám sát và khắc phục, tránh retry vô hạn.

**Câu 11.** JWT dùng `opaqueToken()` để hỏi introspection còn được tính là “JWT local” không?

**Đáp án:** Không. Token có format JWT nhưng chiến lược validation là online introspection, vẫn phụ thuộc RTT và state của IdP.

**Câu 12.** Có nên đổi signing key toàn hệ thống để revoke token của một người không?

**Đáp án:** Không phải giải pháp thông thường. Nó có thể ảnh hưởng hàng loạt token; cân nhắc short TTL, denylist, token version hoặc online introspection/policy.

## 18. Tài liệu chính thức

- [Spring Security — Reactive OAuth2 Resource Server: JWT](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html)
- [Spring Security — Reactive OAuth2 Resource Server: Opaque Token](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/opaque-token.html)
- [Spring Security — OAuth2 WebFlux Overview](https://docs.spring.io/spring-security/reference/reactive/oauth2/)
- [Javadoc — ReactiveJwtDecoder](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/jwt/ReactiveJwtDecoder.html)
- [Javadoc — ReactiveOpaqueTokenIntrospector](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/introspection/ReactiveOpaqueTokenIntrospector.html)
- [Javadoc — SpringReactiveOpaqueTokenIntrospector](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/introspection/SpringReactiveOpaqueTokenIntrospector.html)
- [Javadoc — ServerHttpSecurity](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.html)
- [Spring Boot 4 — OAuth2 Resource Server auto-configuration](https://docs.spring.io/spring-boot/reference/security/oauth2.html)
- [RFC 7662 `4 — Token Introspection and Caching](https://www.rfc-editor.org/rfc/rfc7662#section-4)
- [RFC 6750 — OAuth2 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
- [RFC 7519 — JSON Web Token](https://www.rfc-editor.org/rfc/rfc7519)
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725)
- [RFC 9068 — JWT Profile for OAuth2 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068)
- [Project Reactor — Retry and Backpressure](https://projectreactor.io/docs/core/release/reference/)
