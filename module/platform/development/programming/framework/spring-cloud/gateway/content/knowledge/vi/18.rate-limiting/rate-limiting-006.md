# KeyResolver theo người dùng, khách hàng, API key hoặc địa chỉ IP trong Spring Cloud Gateway

Khi một Gateway phục vụ hàng nghìn client, **giới hạn lưu lượng (rate limiting)** giúp ngăn một nguồn request chiếm hết năng lực của backend. Tuy nhiên, chỉ đặt ngưỡng “10 request/giây” là chưa đủ: **10 request/giây cho ai?** Cho mỗi người dùng, mỗi tổ chức khách hàng, mỗi API key, mỗi địa chỉ IP hay cho toàn bộ hệ thống?

Trong **SPRING_CLOUD_GATEWAY**, `RequestRateLimiter` GatewayFilter Factory phối hợp với một **`KeyResolver`** để xác định **định danh dùng làm khóa giới hạn** cho mỗi request. Bài học thuộc chương **Giới hạn lưu lượng** và đi sâu vào cách lựa chọn khóa theo người dùng, tenant/khách hàng, API key đã xác minh hoặc địa chỉ IP, cũng như tác động của lựa chọn này đến công bằng, bảo mật, khả năng chống lạm dụng và vận hành nhiều Gateway instance.

Bài kết nối với route predicate, filter chain, biến đổi path/header, khám phá dịch vụ, Spring Security, circuit breaker, retry, TLS và quan sát request; **rate limiting không thay thế bất kỳ lớp bảo vệ nào trong số đó**.

> **Phạm vi:** Ví dụ áp dụng cho **Spring Cloud Gateway Server WebFlux** theo cú pháp cấu hình thường gặp ở Gateway 4.x. Một số bản mới có namespace khác, chẳng hạn nhóm `spring.cloud.gateway.server.webflux.*`; Server MVC cũng có cấu trúc và lớp filter khác. Kiểm tra version Spring Boot, Spring Cloud release train và Gateway thực tế trước khi sao chép. Các ID, địa chỉ, hạn mức, domain và token minh họa không phải cấu hình production.

## 1. KeyResolver là gì?

`KeyResolver` là một interface của Spring Cloud Gateway, về ý nghĩa có phương thức:

~~~java
Mono<String> resolve(ServerWebExchange exchange);
~~~

Nó nhận `ServerWebExchange`, đọc thông tin có sẵn trong request/context đáng tin cậy rồi trả về một **`Mono<String>` chứa khóa**. Ví dụ:

~~~text
Request A: người dùng u-100      -> key = user:u-100
Request B: người dùng u-200      -> key = user:u-200
Request C: người dùng u-100      -> key = user:u-100
~~~

Request A và C cùng định danh nên được tính vào **cùng phạm vi hạn mức** nếu chúng cùng chính sách/route limiter. Request B có thể được tính độc lập.

**KeyResolver không tự đếm request và không quyết định giá trị replenish/burst.** Nó chỉ chọn “bucket của ai”; bộ `RateLimiter` mới xử lý việc cấp/không cấp lượt request theo ngân sách.

### Quan hệ giữa các thành phần

| Thành phần | Trách nhiệm | Ví dụ |
|---|---|---|
| **Route Predicate** | Chọn route ứng với URL/method/host | `Path=/api/orders/**` |
| **`RequestRateLimiter`** | Gọi KeyResolver, áp dụng limiter, có thể chặn request | Filter gắn trên route orders |
| **`KeyResolver`** | Tạo khóa ổn định từ danh tính/ngữ cảnh request | `user:8f2…` |
| **`RateLimiter`** | Kiểm tra/ghi nhận token hoặc ngân sách | Redis token bucket |
| **Spring Security/API-key authenticator** | Xác minh người gọi và cung cấp danh tính đã tin cậy | JWT `sub`; client ID đã validate |
| **Downstream** | Xử lý nghiệp vụ khi request được cho qua | `lb://orders-service` |

~~~mermaid
flowchart TD
    C["Client HTTP request"] --> S["Authentication / trusted proxy context"]
    S --> M{"Gateway route matches?"}
    M -->|Không| N["Không chạy limiter của route đó"]
    M -->|Có| F["RequestRateLimiter GatewayFilter"]
    F --> K["KeyResolver: Mono<String>"]
    K --> KEY{"Khóa có hợp lệ?"}
    KEY -->|Không| EMPTY["Chính sách empty key"]
    KEY -->|Có| L["RateLimiter: bucket theo phạm vi cấu hình"]
    L --> Q{"Còn token / quota?"}
    Q -->|Không| R["Từ chối, thường HTTP 429"]
    Q -->|Có| G["Chạy filter chain và forward"]
    G --> D["Downstream microservice"]
~~~

**Kết luận thiết kế:** một KeyResolver tốt trả về ID **ổn định, không rò bí mật, đủ phân biệt đúng chủ thể và khó bị client giả mạo**.

## 2. Cấu hình RequestRateLimiter với KeyResolver

Ví dụ Gateway có route orders dùng Redis Rate Limiter và Bean tên `userKeyResolver`:

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        - id: orders-api
          uri: lb://orders-service
          predicates:
            - Path=/api/orders/**
          filters:
            - name: RequestRateLimiter
              args:
                key-resolver: "#{@userKeyResolver}"
                redis-rate-limiter.replenishRate: 10
                redis-rate-limiter.burstCapacity: 20
                redis-rate-limiter.requestedTokens: 1
~~~

Ý nghĩa của những tham số theo mô hình Redis token bucket:

- `key-resolver: "#{@userKeyResolver}"` tham chiếu một **Spring Bean** bằng biểu thức SpEL. Đây **không phải tên header** để Gateway tự đọc.
- `replenishRate: 10`: bổ sung tối đa khoảng **10 token/giây** vào một bucket, theo thuật toán và điều kiện vận hành thực tế.
- `burstCapacity: 20`: sức chứa tối đa của bucket là **20 token**; có thể cho phép một burst ngắn nếu bucket đầy.
- `requestedTokens: 1`: mỗi request được cho phép cần tiêu thụ **1 token**.
- Khi không đủ ngân sách, bộ lọc thường trả **HTTP 429 Too Many Requests**, không forward request đó.

**Đây không phải “chắc chắn tối đa 10 request trong mọi cửa sổ 1 giây”.** Token bucket cho phép các burst khi còn token và nạp dần theo thời gian; nó không có semantics giống fixed-window counter.

Redis limiter cần **Redis đang hoạt động và dependencies phù hợp** (thường qua Spring Data Redis Reactive) cũng như lớp kết nối Redis của Gateway. Không chỉ khai báo YAML mà mặc định có thể sử dụng Redis. Redis cho phép chia sẻ trạng thái limiter giữa nhiều Gateway node; cách Redis keys được tạo và thuật toán là trách nhiệm implementation của `RedisRateLimiter`.

### Trạng thái khóa và mã lỗi

| Tình huống | Điều gì xảy ra? | Cách hiểu |
|---|---|---|
| Route match, có key, bucket còn token | Request tiếp tục filter chain | Backend có thể được gọi |
| Route match, có key, bucket không đủ token | Thường **429** | Đã đạt hạn mức |
| Không có key / `Mono.empty()` | Chính sách **empty key** quyết định, thường mặc định từ chối | Không nên nhầm với bucket hết token |
| Authentication chặn trước route | Có thể là **401/403** | Limiter của route có thể chưa chạy |
| Không match route | Không chạy limiter route đó | Có thể 404 hoặc route khác |
| Redis gặp lỗi | Phụ thuộc error handling/implementation | Không tự suy ra fail-open hoặc fail-closed |

Trong các dòng hỗ trợ, có các thuộc tính cấu hình chính sách khóa rỗng như `spring.cloud.gateway.filter.request-rate-limiter.deny-empty-key` và `spring.cloud.gateway.filter.request-rate-limiter.empty-key-status-code`. Tên đầy đủ và mặc định cần đối chiếu đúng phiên bản. **Không thay đổi deny-empty-key thành false chỉ để tránh lỗi khi chưa có principal**.

## 3. Lựa chọn khóa theo người dùng đã xác thực

Một trường hợp phổ biến là hạn mức **mỗi người dùng**, ví dụ một người chỉ được gửi một số request/giây đến API orders. Khi dùng Spring Security reactive, có thể lấy `Principal` từ `ServerWebExchange`:

~~~java
package example.gateway.ratelimit;

import org.springframework.cloud.gateway.filter.ratelimit.KeyResolver;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import reactor.core.publisher.Mono;

@Configuration
public class RateLimitKeysConfiguration {

    @Bean("userKeyResolver")
    KeyResolver userKeyResolver() {
        return exchange -> exchange.getPrincipal()
            .ofType(Authentication.class)
            .filter(Authentication::isAuthenticated)
            .filter(auth -> !(auth instanceof AnonymousAuthenticationToken))
            .map(Authentication::getName)
            .filter(name -> !name.isBlank())
            .map(name -> "user:" + name);
    }
}
~~~

Đoạn mã trên minh họa cách truy cập danh tính qua reactive `exchange.getPrincipal()`, không dùng `ThreadLocal`. Trên thực tế:

- `Authentication.getName()` phải là **ID ổn định đáng tin cậy**, được sinh từ cơ chế authentication đã cấu hình.
- Đừng mặc định `getName()` luôn là email hoặc luôn là JWT subject trong mọi OAuth2 provider; kiểm tra principal converter của ứng dụng.
- Trong một hệ thống đa tenant, chỉ có username như `alex` có thể bị trùng ở hai tổ chức. Cần thêm phạm vi tenant/issuer theo policy.
- Với API public chưa đăng nhập, `exchange.getPrincipal()` có thể rỗng. Giữ hành vi **deny on empty** hoặc đặt một lớp giới hạn riêng theo IP cho traffic anonymous, không gộp nhầm tất cả vào bucket của `anonymous`.
- Nếu auth xảy ra **sau** bộ lọc rate limit do cấu hình khác thường, KeyResolver sẽ chưa có danh tính. Phải kiểm chứng thứ tự security/route filters thật.

**Không dùng tên hiển thị thay ID:** một nickname có thể đổi, trùng hoặc do người dùng tự chọn. Nếu cần quota liên tục theo tài khoản, chọn subject/account ID bất biến theo chính sách nghiệp vụ.

### JWT: chọn `sub` thay vì thông tin do client tự nhập

Khi Gateway dùng Spring Security OAuth2 Resource Server, một Bean chuyên cho JWT có thể lấy `sub` từ `JwtAuthenticationToken` đã xác thực:

~~~java
import org.springframework.cloud.gateway.filter.ratelimit.KeyResolver;
import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;
import reactor.core.publisher.Mono;

@Bean("jwtSubjectKeyResolver")
KeyResolver jwtSubjectKeyResolver() {
    return exchange -> exchange.getPrincipal()
        .ofType(JwtAuthenticationToken.class)
        .flatMap(auth -> Mono.justOrEmpty(auth.getToken().getSubject()))
        .filter(sub -> !sub.isBlank())
        .map(sub -> "user:" + sub);
}
~~~

**Chỉ tin claim của JWT sau khi signature, issuer, thời hạn và audience cần thiết đã được kiểm tra**. `sub` có thể chỉ duy nhất **trong phạm vi issuer**, không nhất thiết duy nhất trên toàn bộ nền tảng. Nếu có nhiều identity providers, đưa **issuer/client namespace** đã được kiểm chứng vào khóa để tránh trùng ID. Không dùng chuỗi JWT thô làm key.

## 4. Lựa chọn khóa theo khách hàng, tổ chức hoặc tenant

Trong API B2B, một khách hàng có thể có **nhiều người dùng** cùng dùng ngân sách chung. Khi đó, limiter theo `tenantId` hoặc `clientId` có thể đúng hơn limiter theo `sub`.

Ví dụ:

~~~text
Tenant acme:
  user u1 ─┐
  user u2 ─┼──> key = tenant:acme (chung quota)
  user u3 ─┘

Tenant beta:
  user v1 ────> key = tenant:beta (quota độc lập)
~~~

### KeyResolver từ tenant claim đã xác minh

Giả định Identity Provider cấp JWT có claim `tenant_id` và Gateway đã xác thực token phù hợp:

~~~java
import org.springframework.cloud.gateway.filter.ratelimit.KeyResolver;
import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;
import reactor.core.publisher.Mono;

@Bean("tenantKeyResolver")
KeyResolver tenantKeyResolver() {
    return exchange -> exchange.getPrincipal()
        .ofType(JwtAuthenticationToken.class)
        .flatMap(auth -> {
            String tenant = auth.getToken().getClaimAsString("tenant_id");
            if (tenant == null || tenant.isBlank()) {
                return Mono.empty();
            }
            return Mono.just("tenant:" + tenant);
        });
}
~~~

Nếu `tenant_id` thiếu, `Mono.empty()` kích hoạt chính sách khóa rỗng của filter. Đừng tự chọn tenant từ header `X-Tenant-Id` do client gửi để lấp chỗ trống nếu chưa kiểm chứng nó thuộc người dùng.

**Rủi ro multi-tenancy:** việc JWT có một `tenant_id` không thay thế validation rằng người dùng thực sự được phép thao tác trên tenant đó. Backend vẫn cần kiểm tra resource ownership và tenant isolation. Nếu một người có thể chọn tenant hiện hành, KeyResolver phải lấy tenant đã **được hệ thống xác nhận**, không chỉ parameter tự khai.

### Hai tầng ngân sách: tenant + user

Một hệ thống có thể muốn:

1. Mỗi tổ chức tối đa **1.000 request/giây**.
2. Mỗi người dùng trong tổ chức tối đa **20 request/giây**.

**Một KeyResolver trả một khóa không tự tạo hai bộ đếm độc lập.** Ghép khóa `tenant:acme:user:u1` tạo một bucket cho **cặp tenant/user**, chứ không đồng thời áp hai hạn mức tenant và user.

Muốn **hai chính sách độc lập**, cần thiết kế thêm tầng rate limiter/filter phù hợp, hoặc một dịch vụ quota tập trung kiểm tra cả hai. Nếu dùng nhiều `RequestRateLimiter`, phải hiểu chúng được áp dụng cho route nào, cách chúng được cấu hình, thứ tự và chi phí Redis; không tự giả định cấu hình một dòng tạo ra hạn mức phân cấp.

| Cấu trúc key | Quota thực sự được chia sẻ bởi |
|---|---|
| `tenant:acme` | Mọi người dùng thuộc tenant acme |
| `user:u1` | Người dùng u1 qua các phạm vi cùng limiter |
| `tenant:acme:user:u1` | Riêng u1 trong tenant acme |
| `consumer:mobile-app` | Một ứng dụng/client đã được xác thực |
| `ip:198.51.100.10` | Các request cùng địa chỉ IP đã xác định |

## 5. Khóa theo API key: chỉ sử dụng sau khi xác minh

API key thường xuất hiện ở header như:

~~~http
GET /api/reports HTTP/1.1
Host: api.example.test
X-API-Key: <secret-api-key>
~~~

Cách dễ mắc lỗi nhưng **không an toàn** là:

~~~java
// KHÔNG DÙNG TRONG PRODUCTION:
return Mono.justOrEmpty(
    exchange.getRequest().getHeaders().getFirst("X-API-Key")
);
~~~

Vì sao? Một client có thể **tạo vô số chuỗi API key ngẫu nhiên**, mỗi chuỗi được coi là một bucket mới nếu limiter chưa xác minh key. Ngoài ra, key thô có thể bị ghi vào Redis keys, log hoặc traces và làm lộ credential.

### Mô hình an toàn hơn

1. Một **authentication component** xác minh API key (hoặc chữ ký, trạng thái, quyền, hết hạn) với nguồn tin cậy.
2. Thành phần này xác định **consumer ID ổn định**, ví dụ `partner-42` hoặc internal account ID.
3. KeyResolver chỉ dùng **consumer ID đã được xác minh**, không dùng raw API key.
4. Thứ tự xử lý bảo đảm consumer ID hiện diện **trước RequestRateLimiter**; nếu thiếu hoặc sai, request bị xử lý theo security/empty-key policy.

Ví dụ một `WebFilter` bảo mật đã kiểm tra API key và ghi thuộc tính đáng tin cậy `verifiedConsumerId` vào exchange. KeyResolver:

~~~java
import org.springframework.cloud.gateway.filter.ratelimit.KeyResolver;
import org.springframework.context.annotation.Bean;
import reactor.core.publisher.Mono;

@Bean("consumerKeyResolver")
KeyResolver consumerKeyResolver() {
    return exchange -> Mono
        .justOrEmpty(exchange.<String>getAttribute("verifiedConsumerId"))
        .filter(consumerId -> !consumerId.isBlank())
        .map(consumerId -> "consumer:" + consumerId);
}
~~~

**Đây chỉ là phần KeyResolver.** Bài không giả định Spring Security mặc định có attribute `verifiedConsumerId`. Bạn phải triển khai và kiểm thử authentication component tạo attribute từ kết quả kiểm tra API key, với quy ước rõ về thời gian sống và trust boundary.

Nếu nhiều API keys cùng thuộc một khách hàng, bạn có thể dùng một **consumer ID chung** để áp hạn mức theo khách hàng. Nếu muốn quota riêng cho từng key hợp lệ, dùng **key ID không bí mật** do hệ thống cấp, không dùng secret key thô.

### API key nằm ở đâu trong chính sách bảo mật?

| Giá trị | Có phù hợp làm quota key? | Lý do |
|---|---|---|
| Raw `X-API-Key` từ request | **Không** | Chưa được xác minh, chứa bí mật, có thể xoay giá trị |
| Internal key ID sau xác thực | Có thể | Ổn định và không chứa secret |
| Consumer/account ID sau xác thực | Có thể | Nhiều key của một consumer dùng chung quota |
| Tenant ID từ header tự khai | Không, nếu chưa kiểm chứng | Dễ giả mạo tenant |
| OAuth2 `client_id` đã xác thực | Có thể | Phù hợp quota theo ứng dụng nếu identity được kiểm chứng |

## 6. Khóa theo địa chỉ IP: dùng cho anonymous traffic có giới hạn

Khi endpoint công khai không có principal hay API key, **địa chỉ IP** là một lựa chọn để hạn chế lạm dụng cơ bản. Từ request WebFlux:

~~~java
import java.net.InetSocketAddress;
import org.springframework.cloud.gateway.filter.ratelimit.KeyResolver;
import org.springframework.context.annotation.Bean;
import reactor.core.publisher.Mono;

@Bean("peerIpKeyResolver")
KeyResolver peerIpKeyResolver() {
    return exchange -> {
        InetSocketAddress remote = exchange.getRequest().getRemoteAddress();
        if (remote == null || remote.getAddress() == null) {
            return Mono.empty();
        }
        return Mono.just("ip:" + remote.getAddress().getHostAddress());
    };
}
~~~

Đây là **IP của peer được runtime công nhận** theo cách request đến WebFlux. Nếu Gateway chạy sau ingress/load balancer/reverse proxy, `getRemoteAddress()` có thể là **IP của proxy**, khiến mọi client chia một bucket.

### Không tin `X-Forwarded-For` thô

Một request có thể tự gửi:

~~~http
X-Forwarded-For: 203.0.113.1
~~~

Nếu bạn dùng thẳng header này làm key, kẻ tấn công có thể thay IP tùy ý để tạo vô số bucket, vượt hạn mức.

**Cần thiết kế chuỗi proxy tin cậy**:

- Chỉ ingress/proxy được tin cậy mới được phép đặt/thay thông tin forwarded.
- Proxy phải loại bỏ hoặc chuẩn hóa header forwarded do client không tin cậy gửi.
- Gateway/framework phải được cấu hình xử lý forwarded headers theo chính sách **trusted proxies** và đúng phiên bản.
- Nếu dùng IP do proxy suy ra, KeyResolver chỉ đọc kết quả **đã được chuẩn hóa trong trust boundary**, không lấy trực tiếp chuỗi header do client nhập.
- Ở các môi trường cụ thể, dùng metadata kết nối/proxy protocol đã xác thực thay vì suy luận tùy tiện từ `X-Real-IP`, `Forwarded` hoặc `X-Forwarded-For`.

~~~mermaid
flowchart LR
    C["Client IP 198.51.100.10"] --> P["Trusted ingress"]
    P -->|Request đã chuẩn hóa| G["Gateway"]
    U["Untrusted X-Forwarded-For do client gửi"] -.-> P
    P -->|Không tin chuỗi giả mạo| X["Bỏ hoặc thay thông tin forged"]
    G --> R["KeyResolver lấy IP đã tin cậy"]
    R --> B["Bucket ip:198.51.100.10"]
~~~

Sơ đồ minh họa mục tiêu kiến trúc, **không có nghĩa mọi ingress tự động bỏ header giả mạo**. Phải cấu hình và test thật.

### Hạn chế không thể tránh của hạn mức theo IP

| Hạn chế | Hệ quả |
|---|---|
| NAT / mạng công ty / mạng di động | Nhiều người dùng hợp lệ chia một IP, có thể bị chặn oan |
| IPv6 privacy addresses | Client đổi địa chỉ, khó có định danh ổn định |
| Proxy/CDN không được nhận diện đúng | Tất cả request đi vào cùng IP ingress |
| Botnet nhiều IP | Dễ phân tán tải và tránh hạn mức mỗi IP |
| Địa chỉ IP thay đổi theo thời gian | Quota không còn bám theo tài khoản |
| Dữ liệu địa chỉ IP là dữ liệu có thể nhạy cảm | Cần chính sách lưu trữ/logging và quyền truy cập |

Vì vậy, IP-based limiting thích hợp như một **lớp phòng vệ sơ bộ**, không phải công cụ thay thế danh tính người dùng hoặc giải pháp chống DDoS ở edge/network.

## 7. Chọn chiến lược theo loại endpoint

Không có một KeyResolver tối ưu cho mọi route. Nên đặt câu hỏi: **ai tiêu thụ tài nguyên, ai trả phí và ai có khả năng làm quá tải downstream?**

| API / luồng | Khóa ưu tiên | Lý do |
|---|---|---|
| API cần đăng nhập của người dùng | User ID đã xác thực | Công bằng theo tài khoản |
| API SaaS B2B tính quota theo hợp đồng | Tenant/consumer ID đã xác minh | Cả tổ chức dùng chung ngân sách |
| API cho tích hợp đối tác | Validated API key ID hoặc consumer ID | Quản lý quota theo client được cấp phép |
| Trang login, health public, landing endpoint | IP được xác nhận qua proxy tin cậy, hoặc key chuyên dụng | Chưa có user identity ở thời điểm đầu |
| API upload tốn tài nguyên | User/tenant + trọng số chi phí phù hợp | Request lớn đắt hơn một GET nhỏ |
| API admin nhạy cảm | ID operator và quota chặt cùng authorization | Không cho ai vượt quyền chỉ vì còn token |
| API GraphQL / thao tác biến thiên chi phí | Cost-aware limiter nếu hỗ trợ, có thể cần custom logic | Một request có thể khác nhau rất lớn về chi phí |
| Endpoint nội bộ service-to-service | Service identity (mTLS/SPIFFE/OAuth2 client) đã xác minh | Tách traffic của từng workload |

**Không lấy IP làm key chính cho người dùng đã xác thực** nếu nhu cầu thực chất là quota theo tài khoản; nó tạo bất công với NAT và dễ bị né qua đổi mạng. Ngược lại, **không lấy user ID làm key cho trang login chưa xác thực**, vì chưa có danh tính đáng tin cậy.

### Endpoint nào không nên có cùng policy?

Một GET đọc dữ liệu cache và một POST tạo giao dịch có chi phí/rủi ro khác nhau. Dùng cùng key nhưng **khác route/filter policy** có thể tạo quota riêng; cũng có thể cố ý chia ngân sách chung qua custom limiter. Thiết kế phải ghi rõ mong muốn, không để hành vi phát sinh ngẫu nhiên từ cách đặt route ID.

## 8. Bucket scope: route ID và khóa do KeyResolver trả về

Một chi tiết nâng cao nhưng rất quan trọng: với cách tích hợp mặc định, `RequestRateLimiter` làm việc trong **ngữ cảnh route**. `RedisRateLimiter` thường được cung cấp cả **route ID** và **resolved key** khi xác định các khóa dữ liệu trong Redis. Vì vậy:

- Hai request cùng `user:u1` trên **cùng route** có thể dùng chung bucket.
- Cùng `user:u1` nhưng trên **hai route khác nhau** có thể được tính bởi **hai bucket riêng**, dù KeyResolver trả về cùng chuỗi.
- Chỉ thêm `routeId` vào KeyResolver **không tự tạo global quota**, và có thể thừa nếu Redis limiter đã phân vùng theo route.
- Muốn **một hạn mức thực sự dùng chung trên nhiều routes**, phải chọn mô hình limiter hỗ trợ pooling/costing xuyên route, hoặc viết custom rate limiter/chính sách tập trung; không giả định chỉ trả cùng user ID là đủ.

Ví dụ:

~~~text
Route orders-read:
  Redis limiter scope = orders-read + user:u1

Route reports-read:
  Redis limiter scope = reports-read + user:u1

=> Hai bucket độc lập trong cấu hình RedisRateLimiter thông thường.
~~~

Một hệ thống có thể chủ động đặt hai hạn mức: “10 GET orders/s” và “2 GET reports/s”. Khi thêm route thứ ba, quota mới cũng phải được thiết kế thay vì mặc định nó kế thừa một global user limit.

### Ghép khóa có cấu trúc

Với custom limiter hoặc chính sách cần phân biệt tenant/user, có thể xây key dạng:

~~~text
tenant:<trustedTenantId>:user:<trustedSubjectId>
~~~

Bảo đảm hai ID được **chuẩn hóa/encode không nhập nhằng**. Nếu ID có thể chứa dấu phân tách `:` hoặc ký tự bất thường, có thể dùng UUID/ID nội bộ chuẩn hóa hoặc phép mã hóa an toàn. Không để chuỗi do client cung cấp trực tiếp tạo Redis key tùy ý, gây key-space explosion.

## 9. Xử lý khóa rỗng và lỗi: phải định nghĩa rõ chính sách

`KeyResolver` trả về `Mono.empty()` khi không tìm thấy khóa đáng tin cậy. Đây không phải cùng tình huống “được cấp khóa nhưng hết token”.

Với những dòng Gateway hỗ trợ cấu hình:

~~~yaml
spring:
  cloud:
    gateway:
      filter:
        request-rate-limiter:
          deny-empty-key: true
          # Có thể cấu hình empty-key-status-code
          # theo tài liệu và namespace của phiên bản đang dùng.
~~~

`deny-empty-key: true` thể hiện ý định **không cho request thiếu key đi qua filter**. Mã HTTP cho empty key được điều khiển riêng theo implementation/version (thường khác `429` khi bucket hết token). Đừng hardcode kiểm thử rằng mọi trường hợp thiếu key đều trả `429`.

### Bốn cách xử lý khi thiếu key

| Chiến lược | Ưu điểm | Rủi ro |
|---|---|---|
| **Deny empty key** | Không cho bypass quota | Endpoint public có thể bị từ chối khi chưa xác thực |
| Fallback sang IP đã xác minh | Dùng được cho anonymous traffic | Phải xử lý proxy trust, NAT và privacy |
| Bucket `anonymous` chung | Dễ giới hạn tổng anonymous requests | Một client xấu có thể chiếm quota của mọi người |
| Cho qua khi không có key | Tránh chặn lỗi hợp lệ | Dễ tạo lỗ hổng rate-limit bypass nếu key resolver có lỗi |

Nếu cần fallback user → IP, hãy **thiết kế loại request** và thứ tự authentication rõ ràng, chứ không đơn giản lấy dữ liệu bất kỳ. Ví dụ về logic:

~~~text
Nếu principal đã xác thực và có user ID ổn định:
    key = user:<id>
Nếu endpoint công khai và có IP đã được proxy tin cậy xác định:
    key = ip:<client-ip>
Ngược lại:
    không trả key -> áp chính sách deny / error riêng
~~~

**Fail-open hay fail-closed khi Redis lỗi là quyết định khác với deny-empty-key.** `deny-empty-key` chỉ nói về **không xác định được khóa**; nó không thiết lập hành vi khi backend Redis gặp network error. Phải kiểm tra cách exception propagation/fallback của phiên bản, và thiết kế ranh giới an toàn với các API quan trọng.

## 10. Thứ tự với Spring Security, GatewayFilters và service discovery

Ở Gateway Server WebFlux, Spring Security thường xử lý request ở tầng **WebFilter** trước khi nó vào chuỗi `GatewayFilter` của route. Nhờ đó, `exchange.getPrincipal()` có thể chứa danh tính đã xác thực khi `RequestRateLimiter` chạy.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant S as Spring Security WebFilters
    participant G as Gateway Route Filter Chain
    participant K as KeyResolver
    participant R as RedisRateLimiter
    participant B as Backend
    C->>S: HTTP request + Bearer token
    S->>S: Validate token + authorize
    alt Token không hợp lệ / thiếu quyền
        S-->>C: 401 / 403
    else Được phép
        S->>G: Request đã qua security
        G->>K: resolve(exchange)
        K-->>G: user:sub-123
        G->>R: isAllowed(routeId, key)
        alt Không đủ token
            R-->>G: not allowed
            G-->>C: 429
        else Được phép
            R-->>G: allowed
            G->>B: Route/LoadBalancer/forward
            B-->>C: Response qua Gateway
        end
    end
~~~

Điều này có vài hệ quả:

1. **401/403 có thể xuất hiện trước 429**. Một kẻ không có JWT hợp lệ không nhất thiết tiêu tốn token của user bucket, vì GatewayFilter chưa chạy.
2. Muốn giới hạn cả tấn công login/invalid-token, cần **một lớp giới hạn trước authentication** (ví dụ ingress/WAF, rate limiting ở tầng WebFilter hoặc proxy) với định danh phù hợp.
3. `GlobalFilter` và `GatewayFilter` có thể có `Ordered` khác nhau; nếu một custom filter mới thiết lập trusted consumer ID sau `RequestRateLimiter`, KeyResolver không thấy ID đó.
4. `lb://service-id` chọn instance sau khi route đã được chọn; limiter theo user/tenant không tự biến thành limiter mỗi backend instance.
5. `Retry` có thể khiến một request đã được Gateway cho phép tạo **nhiều outbound attempts**. Rate limiter ở trước Retry thường tính theo client request, không mặc định tính mỗi backend attempt. Phải thiết kế retry budget và timeout riêng.

### Cảnh báo với việc dùng header nội bộ

Một `GlobalFilter` có thể gắn `X-Authenticated-User` sau xác thực, nhưng KeyResolver không nên coi **bất cứ header nào hiện diện trong exchange** cũng đáng tin. Nếu chính header đó có thể do client gửi và chưa được loại bỏ, sẽ có nguy cơ giả mạo. Ưu tiên principal, claims đã validate hoặc exchange attribute chỉ được security component ghi.

## 11. Redis token bucket: hiểu thông số và hành vi thực tế

Trong mô hình Redis token bucket:

~~~text
burstCapacity: 20 token tối đa
replenishRate: 10 token/giây
requestedTokens: 1 token/request

Khi bucket đầy:
  Có thể xử lý khoảng 20 request liên tiếp sát nhau,
  sau đó cần chờ token được bổ sung.
~~~

**Không coi 20/10 là con số bảo đảm mọi bài stress test sẽ quan sát chính xác.** Kết quả còn phụ thuộc thời gian gửi request, concurrency, độ trễ Redis, khởi tạo bucket, refill và sự chênh thời điểm của client/load balancer.

### Hạn mức trung bình thấp hơn một request mỗi giây

Khi muốn trung bình khoảng **1 request/20 giây**, một số hướng dẫn RedisRateLimiter sử dụng mô hình:

~~~yaml
filters:
  - name: RequestRateLimiter
    args:
      key-resolver: "#{@userKeyResolver}"
      redis-rate-limiter.replenishRate: 1
      redis-rate-limiter.burstCapacity: 20
      redis-rate-limiter.requestedTokens: 20
~~~

Theo mô hình, mỗi giây nạp 1 token, mỗi request tốn 20 token, bucket chứa tối đa 20: sau một request đủ token cần đợi khoảng 20 giây để đủ lại, nếu không có điều kiện khác. **Hạn mức này cần thử thực tế**, không sao chép sang production mà không hiểu nhu cầu.

### Những yếu tố vận hành Redis

| Vấn đề | Điều cần theo dõi |
|---|---|
| Nhiều Gateway instances | Có dùng cùng Redis/namespace và cùng cấu hình limiter? |
| Redis cluster/latency | Lỗi mạng, thời gian thực thi script và timeout |
| Route ID thay đổi | Bucket có thể chuyển phạm vi do khóa Redis phụ thuộc route |
| Rất nhiều key động | Bộ nhớ/key churn và nguy cơ DoS key-space |
| Clock/time windows | Hành vi thuật toán khi hệ thống lệch thời gian hoặc trải qua restart |
| Rate limit response headers | Header thông báo quota (nếu được bật) và tính nhất quán với policy |
| Observability | Số request allowed/denied, 429, latency Redis, lỗi resolver |

Không dùng limiter để thay công cụ chống DDoS volumetric ở ingress/CDN; request có thể tiêu tốn tài nguyên mạng trước khi Gateway kịp gọi Redis.

## 12. Bài thực hành: so sánh khóa theo user, consumer và IP

### Chuẩn bị

Giả định:

- Gateway Server WebFlux chạy cổng `8080`, backend orders phục vụ `/orders/42`.
- Có Redis phù hợp cho `RedisRateLimiter`.
- Spring Security JWT Resource Server đã xác thực JWT của các user test.
- KeyResolver Bean `userKeyResolver` hoặc `tenantKeyResolver` đã được đăng ký và chọn đúng trong cấu hình.
- URI `lb://orders-service` hoạt động nhờ DiscoveryClient/LoadBalancer, hoặc tạm thay bằng `http://localhost:9090` trong lab nếu không dùng discovery.

Ví dụ route cấu hình hạn mức tương đối nhỏ để dễ quan sát:

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        - id: orders-lab
          uri: http://localhost:9090
          predicates:
            - Path=/api/orders/**
          filters:
            - StripPrefix=1
            - name: RequestRateLimiter
              args:
                key-resolver: "#{@userKeyResolver}"
                redis-rate-limiter.replenishRate: 2
                redis-rate-limiter.burstCapacity: 3
                redis-rate-limiter.requestedTokens: 1
~~~

`StripPrefix=1` chỉ sửa path; key lấy từ Spring Security principal. Backend nhận `/orders/42` nếu không có filter path khác.

### Bước 1 — Gửi request với user A

Giả sử một token test hợp lệ của user A đã được cấp:

~~~bash
# Thay <JWT_USER_A> bằng access token TEST hợp lệ của user A.
curl -i -H "Authorization: Bearer <JWT_USER_A>" \
  http://localhost:8080/api/orders/42
~~~

Gửi nhiều request **trong một khoảng thời gian ngắn**; một số request có thể bị `429` khi bucket không còn token. Số lượng chính xác phụ thuộc timing và trạng thái bucket. Không log token thật hoặc đưa token vào repository.

### Bước 2 — So sánh với user B

~~~bash
curl -i -H "Authorization: Bearer <JWT_USER_B>" \
  http://localhost:8080/api/orders/42
~~~

Nếu cả hai token hợp lệ, principal ID khác nhau và policy dùng `userKeyResolver`, B được tính theo bucket riêng của B. Nếu B vẫn nhận 429 ngay trong khi bucket mới, kiểm tra liệu principal ID có thực sự khác, route ID, Redis state từ lượt test trước và những limiter ở tầng khác.

### Bước 3 — Đổi thành tenantKeyResolver

Đổi:

~~~yaml
key-resolver: "#{@tenantKeyResolver}"
~~~

Dùng hai token test thuộc **cùng tenant** nhưng khác `sub`. Cả hai sẽ dùng key `tenant:<id>` nên tiêu cùng ngân sách. Một token của tenant khác sẽ vào bucket khác. Để so sánh công bằng, reset môi trường test/bucket theo quy trình được phép hoặc dùng một route ID test mới; không xóa Redis production keys.

### Bước 4 — API key consumer

Chỉ khi đã có cơ chế validate API key và set `verifiedConsumerId` đáng tin, đổi route thành:

~~~yaml
key-resolver: "#{@consumerKeyResolver}"
~~~

Gửi hai API keys hợp lệ cùng thuộc một consumer, xác minh chúng chia quota theo consumer ID. Gửi một API key giả: request phải bị authentication component từ chối hoặc không có trusted consumer ID; **không được sinh bucket mới chỉ từ chuỗi API key giả**.

### Bước 5 — Anonymous IP policy

Trên một route public riêng, sử dụng `peerIpKeyResolver` với proxy trust đã xác minh. Gửi nhiều request từ cùng peer IP, rồi thử môi trường có reverse proxy và kiểm tra `getRemoteAddress()` tại Gateway:

- Nếu mọi client đều trở thành IP của ingress, quota theo IP đã mất tác dụng phân biệt client.
- Nếu lấy raw `X-Forwarded-For` do client sửa và quota thay đổi theo header giả, thiết kế đang có lỗ hổng.
- Nếu IP không xác định, cần thấy hành vi empty key theo chính sách.

### Ma trận kiểm thử

| Test | Resolver | Điều cần quan sát |
|---|---|---|
| Nhiều request cùng user | User ID | Bucket dùng chung, vượt ngưỡng trả 429 |
| Hai user độc lập | User ID | Không tranh bucket nếu khác ID |
| Hai user cùng tenant | Tenant ID | Chia hạn mức nếu tenant giống nhau |
| Hai API keys cùng consumer | Trusted consumer ID | Chia hạn mức theo consumer |
| API key sai | Consumer ID | Không tạo khóa từ secret giả |
| Client qua proxy | Peer/trusted client IP | Đúng IP theo trust boundary, không chỉ IP ingress |
| Request không auth | User ID | Security/empty-key policy rõ ràng |
| Request route khác | User ID | Xác minh quota có tách theo route ID như thiết kế |
| Redis lỗi | Mọi resolver | Xác minh fail policy và status thực tế |

## 13. Troubleshooting theo triệu chứng

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Tất cả request đều bị từ chối trước 429 | Authentication trả 401/403, không có principal | Kiểm tra security chain và token trước khi debug Redis |
| Empty-key trên user đã login | KeyResolver không lấy đúng `Authentication` hoặc converter tạo ID rỗng | Kiểm tra principal type và tên Bean |
| Mọi user chia cùng quota | Key luôn là `anonymous` hoặc lấy IP ingress | Dùng user/consumer ID đã xác thực |
| Một user có nhiều bucket bất thường | Key lấy từ token thô, email đổi, path/query tùy biến | Dùng stable internal ID, chuẩn hóa key |
| 429 chỉ trên một số node | Redis/cache/config khác nhau hoặc route ID không đồng nhất | Kiểm tra tất cả Gateway instances |
| 429 quá sớm | Burst quá nhỏ, requestedTokens quá lớn, test reuse bucket | Xem cấu hình và Redis state, timing |
| Không thấy 429 dù stress | Limiter chưa gắn route, key rỗng được bypass, Redis policy, request không match | Xem route runtime/filter chain và kết quả HTTP |
| API key random vẫn được cấp quota mới | Dùng raw header làm key | Bắt buộc validate API key trước rate limit |
| Khóa IP đổi theo `X-Forwarded-For` giả | Tin forwarded header do client gửi | Cấu hình trusted proxy chain |
| Hệ thống NAT bị chặn oan | Quota theo IP gộp nhiều người | Chuyển sang user/tenant khi có auth, điều chỉnh policy anonymous |
| Khi Redis down request trả 5xx | Error handling theo implementation không đáp ứng SLO | Kiểm tra circuit/timeout và chính sách fail-open/fail-closed được phê duyệt |
| Cùng user đi route khác không chung quota | Bucket tách theo route ID | Cần custom shared quota nếu thực sự muốn global limit |
| Backend bị quá tải dù 429 ít | Retry nhân số outbound attempts hoặc request chi phí cao | Thiết kế retry budget, cost-aware limit và capacity management |
| Lộ thông tin nhạy cảm qua logs | Ghi raw JWT/API key/session ID trong key | Chỉ dùng internal ID, mask/sanitize logging |

**Phương pháp kiểm tra nhanh:** (1) request đã qua authentication chưa; (2) route có match không; (3) Bean KeyResolver trả key gì, có trusted không; (4) key/route đi vào limiter nào; (5) Redis có hoạt động không; (6) request bị từ chối ở Gateway hay backend. Không đọc/ghi raw credentials vào log để điều tra.

## 14. Nguyên tắc thiết kế và vận hành production

1. **Xác thực trước khi tin danh tính:** ưu tiên principal, JWT claims đã validate, mTLS identity hoặc verified consumer ID; đừng tin header tự khai.
2. **Chọn quota owner rõ ràng:** user, tenant, consumer, service identity hoặc trusted client IP. Ghi trong thiết kế vì sao đối tượng đó phải chia ngân sách.
3. **Không nhầm composite key với hierarchical quotas:** key `tenant:user` là một bucket, không đồng thời là hai hạn mức tenant và user.
4. **Thiết kế route scope:** kiểm tra RedisRateLimiter phân hoạch theo route ID; custom policy nếu cần chia quota xuyên routes.
5. **Phân lớp phòng vệ:** giới hạn anonymous/invalid-auth ở edge, giới hạn authenticated calls tại Gateway, giới hạn cost/rủi ro ở backend.
6. **Ràng buộc empty/error behavior:** không cho phép bypass khi principal vắng; xác định hành vi khi Redis không khả dụng.
7. **Tính ngân sách theo chi phí thực:** requestedTokens có thể phù hợp request cost, nhưng nếu cần dynamic cost thì phải có cơ chế tùy biến và kiểm thử riêng.
8. **Kiểm soát route discovery:** route mới sinh từ registry có thể không nhận cùng policy mặc định; xác minh các route public được bảo vệ.
9. **Không xem rate limit là authorization:** client còn token không đồng nghĩa có quyền; JWT sai vẫn phải từ chối.
10. **Chú ý retry và circuit breaker:** một request được tính một lần ở edge có thể tạo nhiều lần gọi backend; giới hạn retry, timeout và idempotency.
11. **Bảo vệ Redis và dữ liệu:** dùng network isolation, quyền truy cập, TLS khi phù hợp và quota key không chứa secret/PII không cần thiết.
12. **Quan sát không rò thông tin:** theo dõi 429, tỷ lệ deny, latency Redis, route ID và key class (không log key nhạy cảm).
13. **Kiểm thử nhiều instance và proxy:** sử dụng same Redis backend, xác nhận IP thật và policy khi backend/downstream lỗi.
14. **Thận trọng khi thay đổi hạn mức:** đánh giá tác động lên khách hàng, triển khai theo giai đoạn, có rollback và cảnh báo.

## 15. Checklist tự đánh giá

- [ ] Tôi giải thích được `KeyResolver.resolve(exchange)` trả `Mono<String>` và chức năng của `RequestRateLimiter`.
- [ ] Tôi hiểu Redis token bucket với replenishRate, burstCapacity và requestedTokens.
- [ ] Tôi biết chọn user ID khi quota theo tài khoản, tenant khi quota theo khách hàng và consumer ID khi quota theo API key.
- [ ] Tôi **không** dùng raw API key hoặc raw JWT làm rate-limit key.
- [ ] Tôi kiểm tra `JwtAuthenticationToken`/`Authentication` đã được xác thực trước khi lấy `sub`/client ID.
- [ ] Tôi không lấy tenant từ header/client claim chưa kiểm chứng.
- [ ] Tôi phân biệt IP của peer với client IP sau proxy và không tin `X-Forwarded-For` thô.
- [ ] Tôi đã tính đến NAT, IPv6 privacy addresses và botnet khi dùng IP quota.
- [ ] Tôi biết `Mono.empty()` liên quan deny-empty-key và khác với bucket hết token.
- [ ] Tôi không cho phép empty-key bypass hoặc fail-open Redis một cách vô tình.
- [ ] Tôi hiểu RedisRateLimiter thường phân chia quota theo **route ID + key**, không tự có global quota xuyên routes.
- [ ] Tôi đã kiểm tra thứ tự security, GatewayFilter và custom authentication attributes.
- [ ] Tôi biết 401/403 khác 429 và request bị chặn trước route có thể không tiêu user bucket.
- [ ] Tôi hiểu retry/fallback và rate limiting có thể tính các đơn vị request khác nhau.
- [ ] Tôi đã kiểm thử user A/B, tenant, validated API key, proxy IP, multi-instance và Redis failure.
- [ ] Tôi có giám sát denied/allowed, latency Redis, 429 và backend capacity mà không lộ bí mật.
- [ ] Tôi vẫn duy trì authorization, TLS, discovery route governance, circuit breaker và observability như các cơ chế độc lập.

## Tài liệu tham khảo chính thức

- [Spring Cloud Gateway Reference](https://docs.spring.io/spring-cloud-gateway/reference/) — mục **RequestRateLimiter GatewayFilter Factory**, **Redis RateLimiter**, `KeyResolver` và cấu hình route theo bản **Server WebFlux** đang dùng.
- [Spring Cloud Gateway project](https://spring.io/projects/spring-cloud-gateway) — tài liệu dự án, bản phát hành và release train.
- [Spring Security Reactive Reference](https://docs.spring.io/spring-security/reference/reactive/index.html) — xác thực principal/JWT và `SecurityWebFilterChain`.
- [Spring Security Reactive JWT Resource Server](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html) — kiểm tra JWT và claims đáng tin.
- [Spring Framework — ServerWebExchange](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/server/ServerWebExchange.html) — `getPrincipal()`, request và exchange attributes.
- [Redis documentation](https://redis.io/docs/latest/) — hạ tầng lưu trạng thái Redis, theo dõi hiệu năng và bảo vệ truy cập.

**Ghi nhớ:** `KeyResolver` trả lời câu hỏi **“request này tiêu ngân sách của ai?”**. Chọn **user đã xác thực** cho quota theo tài khoản, **tenant/consumer đã xác minh** cho quota theo khách hàng hoặc API key, và **IP đã được xác nhận qua proxy tin cậy** cho traffic anonymous. Khi key thiếu, Redis lỗi hoặc có nhiều routes/instances, phải định nghĩa chính sách rõ ràng; nếu không, rate limiting rất dễ bị vượt qua hoặc chặn nhầm người dùng hợp lệ.
