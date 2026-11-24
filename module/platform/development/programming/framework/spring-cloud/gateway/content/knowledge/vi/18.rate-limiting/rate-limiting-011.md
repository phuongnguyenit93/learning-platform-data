# RateLimiter tùy biến và chính sách khi kho giới hạn lưu lượng lỗi

## 1. Bài toán: giới hạn lưu lượng phải hoạt động khi có nhiều Gateway

Trong hệ thống microservices, client gọi API qua **Spring Cloud Gateway Server WebFlux**. Gateway chọn route bằng predicate, áp dụng filter chain, có thể biến đổi đường dẫn/header, dùng `lb://service-id` khám phá backend rồi gửi request. Để bảo vệ hệ thống khỏi một người dùng, đối tác hoặc ứng dụng gửi quá nhiều request, ta thường đặt **rate limiting** ngay ở cổng vào:

~~~text
Client → Gateway → RequestRateLimiter → orders-service
                            │
                            └── Redis / quota store
~~~

Ở quy mô nhỏ, một bộ đếm trong RAM có vẻ đủ. Nhưng khi có ba Gateway replica, nếu mỗi replica cho 100 request/phút và không dùng kho chung, cùng một client có thể được chấp nhận khoảng **300 request/phút** khi traffic trải qua cả ba replica. Vì thế, chính sách giới hạn lưu lượng dùng để bảo vệ **quota toàn cụm** thường cần bộ lưu trữ/phối hợp phân tán.

Một câu hỏi khó hơn là: **Redis hoặc kho tính quota bị mất kết nối thì sao?** Các lựa chọn đều có giá:

- **Fail-open:** tiếp tục cho request đi qua, duy trì khả năng phục vụ nhưng có thể mất giới hạn.
- **Fail-closed:** không forward request khi không chứng minh được còn quota, giảm rủi ro bị lạm dụng nhưng làm API phụ thuộc độ sẵn sàng của kho quota.
- **Degraded/bounded fallback:** dùng một ngân sách dự phòng hạn chế trong một thời gian ngắn, phức tạp hơn vì nhiều replica có thể cùng phát ngân sách.

Bài thuộc chương **Giới hạn lưu lượng** của **SPRING_CLOUD_GATEWAY**. Bạn sẽ học cách viết `RateLimiter` tùy biến, chọn `KeyResolver` an toàn, trả mã trạng thái đúng và kiểm thử Redis outage. Kiến thức liên quan chặt chẽ tới xác thực, route/filter, service discovery, circuit breaker, retry, TLS và quan sát request.

> **Phạm vi:** Các ví dụ dùng **Spring Cloud Gateway Server WebFlux**. Không lấy API của Gateway Server MVC rồi áp dụng vào WebFlux: hai biến thể có bộ filter, cấu hình và kiểu key resolver khác nhau. Mẫu Java ở mục 7 dành cho học tập, cần build/test với đúng Spring Boot và Spring Cloud BOM trước khi đưa vào production.

## 2. Phân biệt ba quyết định độc lập

Khi một request đến Gateway, ít nhất ba câu hỏi có thể xảy ra:

| Quyết định | Thành phần | Nếu thất bại thì sao? |
| --- | --- | --- |
| **Ai được gọi API?** | Spring Security, xác thực JWT/session và authorization | Thường **401** hoặc **403** |
| **Caller đã vượt quota chưa?** | `RequestRateLimiter` + `RateLimiter` | Mặc định **429 Too Many Requests** khi quota thực sự hết |
| **Có xác định được quota không?** | Redis, service tính quota hoặc cache phân tán | **Không đồng nghĩa với vượt quota**; cần policy outage riêng |

Đừng gộp ba trường hợp thành một lỗi 429. Nếu Redis bị mất kết nối, server **không biết** client đã dùng bao nhiêu token. Trả 429 có thể đánh lừa client rằng họ đã vượt hạn mức, trong khi lỗi thật là hạ tầng quota không sẵn sàng. Với fail-closed, **503 Service Unavailable** thường truyền đạt tình huống này rõ hơn.

Một request chỉ nên được forward khi **đã xác thực đủ quyền** và đáp ứng chính sách quota hiện hành (hoặc một fallback được cho phép rõ ràng). Rate limiting không thay thế authorization; authorization cũng không tự tạo quota.

### 2.1. Sơ đồ luồng xử lý

~~~mermaid
flowchart TD
    C["Client request"] --> S{"Authenticated / authorized?"}
    S -->|"Không"| A["401 / 403"]
    S -->|"Có"| K["KeyResolver tạo quota key"]
    K --> E{"Có key đáng tin?"}
    E -->|"Không"| D["Từ chối theo empty-key policy"]
    E -->|"Có"| R["RateLimiter kiểm tra quota store"]
    R --> Q{"Kết quả?"}
    Q -->|"Còn quota"| F["Forward tới backend"]
    Q -->|"Hết quota"| T["429 Too Many Requests"]
    Q -->|"Kho lỗi / timeout"| P{"Outage policy?"}
    P -->|"Fail-closed"| U["503 Service Unavailable"]
    P -->|"Fail-open"| F
    P -->|"Bounded degrade"| B["Local emergency budget"]
    B -->|"Còn ngân sách"| F
    B -->|"Hết"| U
~~~

**Lưu ý:** Thứ tự thực thi thực tế phụ thuộc Spring Security WebFilter và thứ tự GatewayFilter của route. Sơ đồ trình bày **thứ tự quyết định logic cần đạt**, không phải một lời hứa rằng mọi bộ lọc luôn chạy đúng thứ tự minh họa nếu bạn cấu hình sai.

## 3. RequestRateLimiter, KeyResolver và RateLimiter làm gì?

Trong Gateway Server WebFlux, `RequestRateLimiter` là **GatewayFilter Factory**. Nó lấy một key, nhờ `RateLimiter` quyết định có được tiếp tục, rồi:

1. Nếu `RateLimiter.Response.isAllowed()` là `true`, request đi tiếp trong chain.
2. Nếu `isAllowed()` là `false`, filter thường hoàn tất response với **429** (có thể cấu hình status code).
3. Các response headers do limiter trả về có thể được đưa vào HTTP response.
4. Nếu lời gọi limiter báo **lỗi**, cần xác định error handler và policy phù hợp; không coi mọi lỗi là `isAllowed=false`.

### 3.1. KeyResolver

`KeyResolver` cung cấp:

~~~java
public interface KeyResolver {
    Mono<String> resolve(ServerWebExchange exchange);
}
~~~

Ví dụ key có thể là **user ID đã xác thực**, **client/application ID**, **tenant ID** hoặc một khóa tổng hợp được chuẩn hóa:

~~~text
quota-key = tenant-42 | principal-123 | route-orders-read
~~~

`PrincipalNameKeyResolver` là cơ chế mặc định được tài liệu Gateway WebFlux mô tả; nó lấy tên Principal từ exchange. Khi không tìm được key, Gateway **mặc định từ chối**. Thuộc tính điều khiển trường hợp empty key có thể khác namespace theo release; xem configuration properties của version đang chạy, không tự chuyển toàn bộ request thiếu danh tính thành một key chung.

### 3.2. RateLimiter

Một bean `RateLimiter` cung cấp quyết định reactive:

~~~java
Mono<RateLimiter.Response> isAllowed(String routeId, String id);
~~~

Trong đó:

- `routeId` nhận biết route mà Gateway đang xử lý.
- `id` là khóa caller sau `KeyResolver`.
- Response chứa **boolean allowed** và một map **response headers**.

Một `RateLimiter` tùy biến có thể hỗ trợ tenant-specific quota, cost theo route, sliding window, fixed window hoặc nguồn quota bên ngoài. Dù thuật toán nào, **key, trạng thái lưu trữ, timeout và failure policy** đều quan trọng như phép tính quota.

### 3.3. Không dùng RequestRateLimiter shortcut YAML

Theo tài liệu Gateway, `RequestRateLimiter` dùng cấu hình **dạng đầy đủ**; ví dụ dưới **không hợp lệ**:

~~~yaml
# SAI: không dùng shortcut notation cho RequestRateLimiter.
filters:
  - RequestRateLimiter=10, 20
~~~

Hãy dùng `name: RequestRateLimiter` với `args` và tham chiếu bean Spring bằng SpEL như `"#{@myLimiter}"`.

## 4. Token bucket và các thông số RedisRateLimiter tích hợp

Gateway WebFlux có sẵn `RedisRateLimiter` sử dụng thuật toán **token bucket**; đây là điểm khởi đầu hữu ích trước khi tự viết limiter.

~~~text
Bucket capacity:  6 token
Refill:           2 token / giây
Mỗi request:      1 token

Đủ token   → cho qua, trừ token
Thiếu token → HTTP 429 (bình thường, kho quota khỏe)
~~~

| Tham số | Ví dụ | Ý nghĩa |
| --- | ---: | --- |
| `replenishRate` | 2 | Số token nạp lại mỗi giây |
| `burstCapacity` | 6 | Số token tối đa trong bucket |
| `requestedTokens` | 1 | Chi phí token của một request |

Với số trên, một bucket đã đầy có thể cho phép tối đa sáu request đến gần như cùng lúc, sau đó cần thời gian để được nạp lại. Đó **không** phải giới hạn cứng “chỉ hai request cho mỗi giây lịch” và cũng không có nghĩa sau đúng một giây sẽ chắc chắn được thêm hai request nếu trạng thái bucket khác.

Theo hướng dẫn Spring, trường hợp giới hạn chậm hơn 1 request/giây có thể biểu diễn bằng các tham số token phù hợp, ví dụ `replenishRate=1`, `requestedTokens=60` và `burstCapacity=60` cho mức khoảng một request/phút.

### 4.1. RedisRateLimiter trên Gateway Server WebFlux 5.x

~~~yaml
server:
  port: 8080

spring:
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: orders-quota
              uri: http://localhost:9091
              predicates:
                - Path=/api/orders/**
              filters:
                - name: RequestRateLimiter
                  args:
                    key-resolver: "#{@authenticatedUserKeyResolver}"
                    redis-rate-limiter.replenishRate: 2
                    redis-rate-limiter.burstCapacity: 6
                    redis-rate-limiter.requestedTokens: 1
                - StripPrefix=1
~~~

### 4.2. RedisRateLimiter trên Gateway Server WebFlux 4.2/4.3

Cùng danh sách `routes` nhưng đặt dưới namespace:

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        - id: orders-quota
          uri: http://localhost:9091
          predicates:
            - Path=/api/orders/**
          filters:
            - name: RequestRateLimiter
              args:
                key-resolver: "#{@authenticatedUserKeyResolver}"
                redis-rate-limiter.replenishRate: 2
                redis-rate-limiter.burstCapacity: 6
                redis-rate-limiter.requestedTokens: 1
            - StripPrefix=1
~~~

Các ví dụ này giả định **đã có KeyResolver bean**, Redis reactive client và ứng dụng bảo vệ route sao cho Principal đáng tin. Dùng một namespace route theo version; không đặt trùng route ở cả tiền tố cũ và mới.

Dependency Redis reactive theo hướng dẫn Gateway/Spring Boot từng dòng (ví dụ Boot 3.x):

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-redis-reactive</artifactId>
</dependency>
~~~

Chọn starter Gateway tương ứng với Boot/Cloud BOM: các bản mới dùng `spring-cloud-starter-gateway-server-webflux`, nhiều bản 4.x dùng `spring-cloud-starter-gateway`. Không thêm Servlet MVC starter vào dự án định chạy Server WebFlux.

### 4.3. KeyResolver từ principal đã được xác thực

~~~java
package demo.gateway.quota;

import java.security.Principal;

import org.springframework.cloud.gateway.filter.ratelimit.KeyResolver;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class QuotaKeyConfig {

    @Bean
    KeyResolver authenticatedUserKeyResolver() {
        return exchange -> exchange.getPrincipal()
                .map(Principal::getName)
                .filter(name -> !name.isBlank());
    }
}
~~~

Trong production cần **Spring Security** xác thực caller trước khi dùng principal, quy định rõ cách ghép tenant ID và route ID, cũng như xử lý anonymous callers. Không lấy `user` từ query parameter, `X-User-Id` hoặc `X-Api-Key` do client tự khai rồi coi đó là danh tính đã được chứng minh.

### 4.4. Vì sao không nên coi lỗi Redis của limiter tích hợp là fail-closed mặc định?

Một số phiên bản/triển khai `RedisRateLimiter` của Spring Cloud Gateway đã có nhánh xử lý lỗi thực thi Lua/Redis bằng cách trả quyết định **cho qua** (fail-open) với số token còn lại không xác định. Điều này giúp tránh Redis trở thành hard dependency cho traffic, nhưng **có thể gây vượt quota khi Redis lỗi**.

**Hành vi chính xác phụ thuộc bản Spring Cloud Gateway đang triển khai.** Phải đọc implementation tương ứng, quan sát logs/metrics và **chạy fault injection thực tế**. Đừng chỉ bọc:

~~~java
// KHÔNG ĐỦ ĐỂ BẢO ĐẢM fail-closed:
redisRateLimiter.isAllowed(routeId, key)
    .onErrorResume(error -> Mono.just(
        new RateLimiter.Response(false, java.util.Map.of())));
~~~

Nếu implementation bên trong **đã bắt lỗi và trả allowed=true**, tầng `onErrorResume` phía ngoài **không nhìn thấy lỗi nữa**. Muốn kiểm soát chắc chắn fail-closed, phải có một đường truy cập kho quota mà bạn sở hữu **ngữ nghĩa lỗi**, hoặc một cơ chế kiểm tra health/degraded mode độc lập được kiểm thử.

## 5. Chọn quota key: quyết định an toàn hơn chọn thuật toán

| Key strategy | Ưu điểm | Rủi ro |
| --- | --- | --- |
| Principal ID sau khi JWT/session đã xác thực | Gắn quota với người dùng thật | Tên principal có thể trùng giữa tenants nếu không bổ sung tenant |
| OAuth2 client ID đã kiểm chứng | Phù hợp API machine-to-machine | Một client nhiều người dùng có thể dùng chung quota |
| Tenant ID + route group | Giới hạn tổng quota theo hợp đồng | Một tenant đông người dùng có thể gây ảnh hưởng nội bộ |
| IP client **đã được proxy tin cậy xác minh** | Dùng được cho request chưa đăng nhập | NAT/CDN làm nhiều người chung IP; XFF dễ bị giả nếu edge không làm sạch |
| Header/tên user lấy trực tiếp từ query | Tiện cho lab | Client đổi giá trị để lách rate limiting |

Thiết kế production thường cần **nhiều tầng quota**:

~~~text
Toàn hệ thống:    bảo vệ tổng công suất Gateway / backend
Theo tenant:      hợp đồng 1.000 req/phút
Theo principal:   50 req/phút
Theo route:       POST /payments hạn chế hơn GET /products
Theo IP tin cậy:  phòng abuse trước khi đăng nhập
~~~

Tránh ghép key bằng thông tin nhạy cảm nguyên văn vào Redis/log. Dùng namespace rõ ràng và **HMAC hoặc định danh nội bộ ít nhạy cảm** khi có yêu cầu bảo vệ PII. Nếu tự hash các ID ngắn/dễ đoán bằng SHA-256 thuần, hash không hẳn đủ để bảo vệ danh tính khỏi brute-force.

**Lưu ý route ID:** Bộ đếm riêng cho từng route khác với bộ đếm chung cho một tenant. Nếu bạn đổi route ID trong một bản triển khai, các key quota dựa trên route ID có thể thay đổi, vô tình reset hạn mức. Hãy có kế hoạch migration và xác định liệu quota là per-route hay cross-route.

## 6. Thiết kế fail-open, fail-closed và bounded degradation

### 6.1. Bảng quyết định theo loại API

| API / rủi ro | Chính sách khi quota store lỗi | Lý do / điều kiện |
| --- | --- | --- |
| GET catalog công khai, có cache và bảo vệ upstream riêng | **Fail-open có kiểm soát** | Ưu tiên availability, nhưng phải có giới hạn tổng ở ingress/LB |
| Đọc dashboard nội bộ đã xác thực | **Bounded fallback** hoặc fail-closed | Tránh chặn toàn bộ nhưng vẫn hạn chế hiệu ứng nhiều replica |
| POST thanh toán, đổi mật khẩu, phát OTP | **Fail-closed** hoặc giới hạn dự phòng rất chặt | Abuse có thể gây thiệt hại trực tiếp |
| API đối tác tính phí/quota hợp đồng | Thường **fail-closed** hoặc ngân sách dự phòng được ghi nhận | Không được mất kiểm soát chi phí; cần policy hợp đồng |
| Health endpoint của hệ thống | Chính sách riêng, tránh dùng quota user thông thường | Health phải phản ánh trạng thái vận hành, không tạo load vô hạn |

Đây là **gợi ý kiến trúc**, không phải mặc định của Spring Cloud Gateway. Mỗi sản phẩm cần cân nhắc SLA, khả năng phục hồi, chi phí abuse, mạng nội bộ và trách nhiệm vận hành.

### 6.2. Fail-open phải có giới hạn

Fail-open đơn giản “Redis lỗi thì `allowed=true`” có nguy cơ trở thành **tắt rate limiting toàn hệ thống** đúng lúc bị tấn công. Nếu chọn fail-open:

1. Giới hạn thời gian degraded mode; alert tức thời.
2. Giữ tầng edge/WAF hoặc global connection/request cap độc lập.
3. Hạn chế endpoint nhạy cảm hoặc hạ quota tùy class.
4. Không coi quota bị mất là `remaining=unlimited`.
5. Thu thập số request đã qua trong degraded mode để đánh giá vượt quota sau sự cố.

### 6.3. Fail-closed cần phân biệt lỗi kho và quota

Khi kho Redis **hoạt động** và số request đã vượt quota: phản hồi **429 Too Many Requests**. Khi Redis **không thể quyết định** trong deadline và policy buộc từ chối: phản hồi **503 Service Unavailable** hoặc mã lỗi hạ tầng nhất quán, không tự giả định 429.

Không chuyển mọi exception thành `RateLimiter.Response(false)` mà quên filter thường trả **429** cho `false`. Với code tùy biến, nên **phát lỗi có phân loại** để tầng WebFlux error handling trả 503.

### 6.4. Bounded local fallback và vấn đề nhiều replica

Giả sử Redis outage nhưng mỗi Gateway replica có ngân sách dự phòng **5 request/giây**:

~~~text
2 Gateway replica → có thể cho 10 request/giây
10 Gateway replica → có thể cho 50 request/giây
~~~

Đó là giới hạn **mỗi replica**, không còn là quota **toàn cụm**. Hệ thống autoscale trong outage có thể vô tình tăng lưu lượng. Bounded fallback cần:

- Ngân sách toàn cụm được chia nhỏ theo số replica tối đa hoặc cấp lease trước khi outage.
- TTL ngắn, ngưỡng tổng và cơ chế rejoin/reconciliation rõ ràng.
- Cơ chế tránh một client đổi replica liên tục để lấy thêm ngân sách.
- Test đồng thời và scale-out, không chỉ test một Gateway local.

## 7. RateLimiter tùy biến: Redis fixed-window atomic và fail-closed

Để minh họa một implementation **sở hữu trực tiếp đường lỗi Redis**, ta tạo `RateLimiter` dùng Lua Redis: mỗi key được cho **3 request trong một cửa sổ 10 giây tính từ request đầu**. Đây là thuật toán **fixed window theo TTL bắt đầu ở lượt đầu**, **khác token bucket** của `RedisRateLimiter` tích hợp.

Ưu điểm cho bài học là script Redis có thể kiểm tra tăng bộ đếm và đặt TTL trong một thao tác **atomic**; mọi Gateway replica kết nối cùng Redis sẽ dùng chung counter. Bất lợi là ngay sát ranh giới hai cửa sổ có thể xuất hiện burst lớn hơn hạn mức trong 10 giây trượt. Nếu bài toán đòi hỏi sliding-window chính xác, token bucket có chi phí khác hoặc quota theo cost, cần chọn thuật toán phù hợp.

### 7.1. Java implementation cho Gateway WebFlux

Ví dụ tạo file `AtomicRedisWindowLimiter.java` trong project Gateway của bài lab. Code hướng đến Spring Cloud Gateway WebFlux và Spring Data Redis reactive với Java 17+:

~~~java
package demo.gateway.quota;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.time.Duration;
import java.util.HexFormat;
import java.util.List;
import java.util.Map;

import org.springframework.cloud.gateway.filter.ratelimit.RateLimiter;
import org.springframework.data.redis.core.ReactiveStringRedisTemplate;
import org.springframework.data.redis.core.script.DefaultRedisScript;
import org.springframework.http.HttpStatus;
import org.springframework.web.server.ResponseStatusException;
import reactor.core.publisher.Mono;

public final class AtomicRedisWindowLimiter
        implements RateLimiter<AtomicRedisWindowLimiter.Config> {

    // Cấu hình cố định cho lab; không đọc quota từ request.
    public static final class Config {
    }

    private static final long LIMIT = 3;
    private static final Duration WINDOW = Duration.ofSeconds(10);
    private static final Duration STORE_DEADLINE =
            Duration.ofMillis(300);

    private final ReactiveStringRedisTemplate redis;
    private final DefaultRedisScript<Long> script;

    public AtomicRedisWindowLimiter(ReactiveStringRedisTemplate redis) {
        this.redis = redis;
        this.script = new DefaultRedisScript<>();
        this.script.setResultType(Long.class);
        this.script.setScriptText(
                "local n = redis.call('INCR', KEYS[1]); "
                + "if n == 1 then "
                + "  redis.call('PEXPIRE', KEYS[1], ARGV[1]); "
                + "end; "
                + "return n;");
    }

    @Override
    public Class<Config> getConfigClass() {
        return Config.class;
    }

    @Override
    public Config newConfig() {
        return new Config();
    }

    @Override
    public Map<String, Config> getConfig() {
        // Demo không định nghĩa config riêng theo route.
        return Map.of();
    }

    @Override
    public Mono<RateLimiter.Response> isAllowed(
            String routeId, String id) {

        // routeId do Gateway cung cấp; id do KeyResolver xác định.
        String key = "gw:quota:demo:" + sha256(routeId + "|" + id);

        return redis.execute(
                    script,
                    List.of(key),
                    List.of(Long.toString(WINDOW.toMillis())))
                .next()
                .switchIfEmpty(Mono.error(
                        new IllegalStateException("Redis script empty")))
                .map(count -> {
                    long remaining = Math.max(0, LIMIT - count);
                    return new RateLimiter.Response(
                            count <= LIMIT,
                            Map.of("X-RateLimit-Remaining",
                                    Long.toString(remaining)));
                })
                .timeout(STORE_DEADLINE)
                // Quan trọng: lỗi store KHÔNG chuyển thành 429.
                .onErrorMap(error -> new ResponseStatusException(
                        HttpStatus.SERVICE_UNAVAILABLE,
                        "Quota store temporarily unavailable",
                        error));
    }

    private static String sha256(String value) {
        try {
            byte[] digest = MessageDigest.getInstance("SHA-256")
                    .digest(value.getBytes(StandardCharsets.UTF_8));
            return HexFormat.of().formatHex(digest);
        } catch (NoSuchAlgorithmException error) {
            throw new IllegalStateException(error);
        }
    }
}
~~~

Điểm chính của lớp này:

- `RateLimiter.Response(true, ...)` cho request **còn quota**, `false` khi **đã hết quota**.
- Lua script dùng `INCR` và `PEXPIRE` trong cùng một script để mọi replica dùng một quota counter ở Redis; `PEXPIRE` chỉ đặt khi key vừa được tạo.
- Nếu lệnh Redis lỗi, kết quả rỗng hoặc vượt deadline, `onErrorMap` ném `ResponseStatusException(503)` thay vì trả `allowed=false`. Điều này thể hiện **fail-closed không mập mờ 429** khi đi qua WebFlux error handling thông thường.
- `getConfigClass`, `newConfig`, `getConfig` thực hiện contract `RateLimiter`; code demo dùng một policy cố định, chưa hỗ trợ cấu hình quota riêng cho từng route/tenant từ YAML.
- Hash SHA-256 trong key tránh hiện nguyên tên caller trong Redis key nhưng **không bảo đảm ẩn danh** đối với ID dễ đoán. Production nên cân nhắc HMAC và quy tắc quản lý key/namespace.

**Giới hạn học thuật:** Đây là ví dụ khung vận hành, chưa được build/test trong repo; API phụ thuộc dòng Gateway/Spring Data Redis. Khi ứng dụng yêu cầu scale lớn, cần benchmark, test Redis Cluster, hash-slot/TTL, kiểm soát key cardinality, đúng semantics của script trong version và chính sách timeout của HTTP client. Không lấy ví dụ này làm thư viện production nguyên trạng.

### 7.2. Khai báo bean và KeyResolver cho môi trường lab

Để có thể chạy lệnh `curl` mà không cần dựng IdP/JWT, ví dụ sau dùng **header do client tự gửi** `X-Lab-Key`. Đây là cách **cố tình thiếu bảo mật** chỉ áp dụng cho localhost lab; production phải thay bằng resolver dựa trên principal hoặc API key **đã được xác thực**.

~~~java
package demo.gateway.quota;

import org.springframework.cloud.gateway.filter.ratelimit.KeyResolver;
import org.springframework.cloud.gateway.filter.ratelimit.RateLimiter;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.core.ReactiveStringRedisTemplate;
import reactor.core.publisher.Mono;

@Configuration
public class LabQuotaConfiguration {

    @Bean("atomicQuotaLimiter")
    RateLimiter<AtomicRedisWindowLimiter.Config> atomicQuotaLimiter(
            ReactiveStringRedisTemplate redis) {
        return new AtomicRedisWindowLimiter(redis);
    }

    @Bean("labKeyResolver")
    KeyResolver labKeyResolver() {
        return exchange -> Mono.justOrEmpty(
                        exchange.getRequest()
                                .getHeaders().getFirst("X-Lab-Key"))
                .filter(key -> !key.isBlank())
                .filter(key -> key.matches("[A-Za-z0-9_-]{1,64}"));
    }
}
~~~

Nếu không có `X-Lab-Key` hoặc giá trị sai định dạng, resolver không sinh key; cấu hình mặc định của `RequestRateLimiter` sẽ **từ chối empty key**. Không tự chuyển mọi request không danh tính thành một key như `"anonymous"` rồi tưởng đã bảo vệ chính xác mỗi người dùng.

### 7.3. Gắn custom RateLimiter vào route WebFlux 5.x

~~~yaml
server:
  port: 8080

spring:
  data:
    redis:
      host: localhost
      port: 6379
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: orders-quota-lab
              uri: http://localhost:9091
              predicates:
                - Path=/api/orders/**
                - Method=GET,POST
              filters:
                - name: RequestRateLimiter
                  args:
                    rate-limiter: "#{@atomicQuotaLimiter}"
                    key-resolver: "#{@labKeyResolver}"
                - StripPrefix=1
~~~

Với WebFlux **4.2/4.3**, giữ nguyên `routes` rồi chuyển nó dưới `spring.cloud.gateway.routes`; không cần đổi Java bean reference:

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        - id: orders-quota-lab
          uri: http://localhost:9091
          predicates:
            - Path=/api/orders/**
            - Method=GET,POST
          filters:
            - name: RequestRateLimiter
              args:
                rate-limiter: "#{@atomicQuotaLimiter}"
                key-resolver: "#{@labKeyResolver}"
            - StripPrefix=1
~~~

`RequestRateLimiter` **không** dùng `redis-rate-limiter.replenishRate` hay `burstCapacity` khi tham chiếu custom bean này: thuật toán của `AtomicRedisWindowLimiter` là fixed-window với constants của lớp Java. Đừng cấu hình cả hai rồi giả định chúng phối hợp.

### 7.4. Nếu chọn fail-open có chủ đích thì đổi gì?

Trong custom limiter ở mục 7.1, có thể thay nhánh lỗi bằng cách:

~~~java
// Chỉ minh họa policy fail-open; KHÔNG dùng mặc định cho API nhạy cảm.
.onErrorResume(error -> {
    // Tăng metric limiter_store_error, tạo alert theo hệ thống vận hành.
    return Mono.just(new RateLimiter.Response(
            true, Map.of("X-RateLimit-Mode", "degraded")));
});
~~~

Khi fail-open, phải có giới hạn edge và giám sát degraded mode. **Không gửi raw exception hoặc hostname Redis trong response.** Nếu cần bounded fallback, phải thiết kế bộ đếm local có TTL/size tối đa và ngân sách trên mỗi replica, rồi tính ảnh hưởng khi autoscale; không chỉ thêm `.onErrorResume(... allowed=true)`.

## 8. Response headers và status cần minh bạch

| Tình trạng | Status gợi ý | Điều cần truyền đạt |
| --- | --- | --- |
| Còn quota, backend trả thành công | Thường **2xx** của backend | Request đã được chuyển tiếp |
| Hết quota thực sự | **429 Too Many Requests** | Client nên giảm tốc độ hoặc chờ theo policy |
| Thiếu key khi chính sách yêu cầu key | Theo empty-key config (thường **403**) | Không đủ danh tính để xác định quota |
| Redis không cho kết quả trước deadline và fail-closed | **503 Service Unavailable** | Hạ tầng quota tạm thời không sẵn sàng |
| Redis lỗi nhưng fail-open | Status do backend trả | Request được cho qua trong degraded mode |
| Backend không khả dụng sau khi đã qua quota | **5xx** khác/503 tùy lỗi | Không phải quota exceeded |

Các header có thể hữu ích:

- `X-RateLimit-Remaining`: số lượng đơn vị quota còn lại **theo thuật toán áp dụng**, không phải quyền truy cập tuyệt đối. Với custom code, chỉ xuất hiện sau quyết định Redis thành công.
- `Retry-After`: thời gian khuyến nghị chờ, thường theo **giây** hoặc HTTP-date; nên tính từ **thời gian cửa sổ/TTL thực tế**, không hardcode sai.
- `RateLimit-Limit`, `RateLimit-Remaining`, `RateLimit-Reset`: chỉ dùng đúng semantics của chuẩn phiên bản đang hỗ trợ, tránh phát header gây hiểu sai.
- `X-RateLimit-Mode: degraded`: có thể dùng cho test nội bộ; cân nhắc **không công khai chi tiết trạng thái phòng vệ** với mọi client trong production.

**Không trả `Retry-After: 10` cho mọi lỗi** của limiter theo quán tính. Với fixed-window do Redis điều khiển, phải biết TTL còn lại nếu muốn báo chính xác; với Redis outage, không biết khi nào kho phục hồi. Client có thể áp dụng exponential backoff có jitter theo retry policy riêng, không retry ồ ạt làm tình hình tệ hơn.

### 8.1. Phân biệt 429 do Gateway và 429 do backend

Một service downstream cũng có thể trả 429. Cần trace route ID, filter decision source và response headers nội bộ để phân biệt:

~~~text
429 Gateway quota → backend KHÔNG nhận request
429 Backend quota → Gateway đã forward request, backend tự từ chối
~~~

Nếu dùng retry, tránh tự retry 429 vượt quota theo chuỗi vô hạn. Retry 503 do Redis lỗi cũng cần hạn chế vì chính Redis đang quá tải hoặc unavailable.

## 9. Thực hành: kiểm chứng custom limiter bằng hai tiến trình

### 9.1. Chuẩn bị backend nhỏ

Tạo một backend Spring Boot WebFlux độc lập, cổng `9091`, dependency `spring-boot-starter-webflux`:

~~~yaml
# application.yml của backend echo
server:
  port: 9091
~~~

~~~java
package demo.orders;

import java.util.Map;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class OrdersApplication {
    public static void main(String[] args) {
        SpringApplication.run(OrdersApplication.class, args);
    }
}

@RestController
class OrdersController {
    @GetMapping("/orders/{id}")
    Map<String, String> read(@PathVariable String id) {
        return Map.of("id", id, "servedBy", "orders-backend");
    }
}
~~~

Backend không cần tự biết quota. Khi `RequestRateLimiter` ở Gateway từ chối, request **không đến** endpoint trên; đây là tín hiệu quan trọng khi phân tích logs.

### 9.2. Khởi động Redis cho lab

Nếu có Docker và Redis image:

~~~bash
docker run --rm --name quota-redis-lab \
  -p 127.0.0.1:6379:6379 redis:7
~~~

Nếu không dùng Docker, chạy Redis local hoặc một Redis test đã quản lý. **Không mở Redis ra Internet** hoặc dùng Redis production công khai mà không có ACL/TLS. Khi Gateway nằm trong Docker container riêng, `localhost` của container không phải host Redis; dùng DNS/host thích hợp.

Chạy backend và Gateway trong hai terminal từ đúng thư mục dự án Maven tương ứng:

~~~bash
./mvnw spring-boot:run
~~~

Ví dụ trong bài giả định dependencies, Java source và cấu hình đã được tạo phù hợp với release; bài viết **không tuyên bố đã chạy build hoặc thử nghiệm thực tế**.

### 9.3. Gửi bốn request liên tiếp với cùng lab key

Trong vòng 10 giây tính từ request đầu, gửi:

~~~bash
for i in 1 2 3 4; do
  echo "Call $i"
  curl -sS -o /dev/null -D - \
    "http://localhost:8080/api/orders/42" \
    -H "X-Lab-Key: demo-tenant" |
    grep -i -E '^(HTTP/|X-RateLimit-Remaining:)'
done
~~~

**Kỳ vọng nếu cả bốn request chạy trong cùng một cửa sổ TTL, Redis khỏe và không có traffic khác dùng key đó:**

| Request | Bộ đếm Redis sau request | Kết quả |
| ---: | ---: | --- |
| 1 | 1 | Cho qua; backend thường trả 200 |
| 2 | 2 | Cho qua |
| 3 | 3 | Cho qua |
| 4 | 4 | **429 Too Many Requests** |

Sau khi TTL của cửa sổ kết thúc, lệnh kế tiếp có thể lại được cho qua. Với một key khác như `X-Lab-Key: demo-other`, quota được tính độc lập trong bài lab. **Đổi key tùy ý để lấy quota mới là một lỗ hổng trong sản phẩm thật**: đó là lý do ví dụ dùng header tự khai chỉ dành cho local test.

Thử gọi không kèm key:

~~~bash
curl -i "http://localhost:8080/api/orders/42"
~~~

Nếu dùng default deny-empty-key, Gateway từ chối trước backend. Mã phản hồi thường là **403**, không giống 429 do vượt quota. Kiểm tra thuộc tính `deny-empty-key` / `empty-key-status-code` của version khi cần đổi policy.

### 9.4. Kiểm tra kho Redis lỗi: fault injection

Chỉ trong môi trường lab, dừng container Redis:

~~~bash
docker stop quota-redis-lab
~~~

Sau đó gọi lại cùng endpoint:

~~~bash
curl -i "http://localhost:8080/api/orders/42" \
  -H "X-Lab-Key: demo-tenant"
~~~

Với custom limiter ở mục 7.1, khi lệnh Redis lỗi hoặc timeout, nhánh `onErrorMap` sẽ tạo lỗi **503 Service Unavailable** trong đường xử lý WebFlux thông thường. Request **không** được forward đến backend. Nếu mã khác, kiểm tra custom exception handler, filter order và cấu hình Gateway thực tế.

Khi dùng **RedisRateLimiter tích hợp** thay cho custom limiter, **không suy đoán** hành vi tương tự: một số bản có thể fail-open như đã cảnh báo ở mục 4.4. Hãy ghi lại behavior thực tế và đối chiếu source đúng version.

### 9.5. Mở rộng thử hai Gateway replica

Chạy Gateway A/B trên cổng khác nhau, nhưng **cùng Redis và cùng cấu hình limiter**. Gửi luân phiên qua A và B bằng **cùng quota key** trong một cửa sổ. Nếu custom Redis script giữ được state toàn cụm, tổng số request được chấp nhận **không vượt LIMIT=3** cho key/route trong cửa sổ đó (không tính các request từ cửa sổ khác).

Lưu ý mỗi request HTTP nhận routeId tương ứng. Nếu A và B được cấu hình **route ID khác nhau**, code đang hash `routeId + "|" + id` nên chúng tạo **hai quota key riêng**, khiến test sai. Phải bảo đảm route ID/namespace/policy nhất quán trước khi tuyên bố quota toàn cụm.

## 10. Kiểm tra failure mode ngoài Redis down

Không chỉ có trường hợp tắt Redis hoàn toàn. Một chính sách tốt cần kiểm thử:

| Tình huống lỗi | Điều cần xác nhận |
| --- | --- |
| Redis trả timeout chậm, không đóng kết nối | Có **deadline** để không giữ request vô hạn |
| DNS/TLS/ACL/authentication của Redis sai | Lỗi store được phân loại, không bị báo thành 429 |
| Redis script không tồn tại/không chạy | Custom limiter không cho qua ngoài policy |
| Redis Cluster đổi primary/slot | Các key có cách phân vùng và retry hợp lệ; không nhân đôi quyết định |
| Redis mất kết nối 15 giây rồi trở lại | Degraded mode được thu hồi, metrics/alert trở lại bình thường |
| Redis còn hoạt động nhưng p99 latency tăng cao | Quota check không trở thành nút thắt hiệu năng |
| Gateway autoscale trong outage | Local fallback không làm quota toàn cụm tăng theo số replica ngoài ý định |
| Một user gọi rất nhiều key ngẫu nhiên | Redis key cardinality được giới hạn; tránh tấn công bộ nhớ |
| Hai request đồng thời cùng key | Atomic Lua/transaction cho kết quả chính xác, không mất cập nhật |
| Policy chuyển từ v1 sang v2 | Thay đổi route ID, namespace, window, TTL không vô tình reset quota |

Để quan sát, nên có các chỉ số:

- `rate_limit_decision_total{route,decision="allow|deny"}`
- `rate_limit_store_error_total{route,reason="timeout|connection|script"}`
- `rate_limit_degraded_total{route,policy="open|closed|local"}`
- `rate_limit_store_latency_seconds` dạng histogram
- `rate_limit_denied_total{route}` và status code 429/503

Các nhãn chỉ nên có **cardinality thấp**. Không đưa principal ID, API key, raw token hoặc IP cá nhân vào metric labels; có thể dùng log có kiểm soát riêng nếu cần truy vết. Theo dõi cả tỷ lệ **backend requests / ingress requests** để nhận biết quota bị mất tác dụng.

## 11. Các bẫy vận hành và bảo mật

### 11.1. IP từ X-Forwarded-For chưa chắc là client thật

Một client có thể tự gửi `X-Forwarded-For`. Nếu Gateway dùng phần tử trái nhất làm quota key mà không có ingress/WAF **làm sạch header và khóa đường bypass**, attacker đổi IP giả để né limit. Hãy xác minh proxy trust boundary trước khi dùng IP; khi khả thi, ưu tiên principal/client ID đã xác thực.

### 11.2. Tính phí theo route nhưng không kiểm tra route fallback

Nếu route `/api/payments/**` có limiter chặt nhưng một route tổng quát `/api/**` không có limiter hoặc thắng thứ tự ưu tiên, request có thể tránh chính sách. Kiểm tra route order, route predicate và toàn bộ luồng với các path/method tương đương.

### 11.3. CORS preflight và health

Browser có thể gửi `OPTIONS` trước POST JSON. Nếu quota tính mọi preflight như request ghi dữ liệu, hoặc Security chặn OPTIONS, frontend gặp lỗi CORS khó phân biệt. Đặt chính sách cho preflight có chủ đích, không “mở mọi OPTIONS” bất kể nguồn; health probes cũng cần policy riêng.

### 11.4. Retry không có nghĩa là có thêm quota miễn phí

Một request client có thể bị Gateway hoặc backend retry. Nếu limiter chạy **một lần** trước retry filter nhưng backend nhận nhiều attempt, quota tính ở client-request level có thể không bảo vệ tổng backend calls. Ngược lại, nếu limiter được chạy lại mỗi attempt, một client request có thể bị trừ quota nhiều lần. Phải định nghĩa **quota tính theo HTTP client request hay theo backend attempt** và kiểm tra filter order/retry metrics.

### 11.5. Fail-closed quá rộng có thể gây outage dây chuyền

Nếu tất cả API, kể cả health/readiness, đều fail-closed khi Redis lỗi, một sự cố quota store có thể khiến Gateway bị đánh dấu unhealthy và cả cụm nhận traffic churn. Thiết kế readiness/liveness, fallback và policy riêng cho endpoint quản trị. **Không** vì vậy mà tự fail-open cho API thanh toán hoặc bảo mật nhạy cảm.

### 11.6. Bảo vệ kho quota

Redis cần mạng riêng, ACL, TLS nếu phù hợp, timeout hợp lý và dự phòng/failover. Quản lý key/TTL/namespace để tránh memory exhaustion, dùng script atomic cho bộ đếm phân tán. Không lưu raw Bearer token hay bí mật trong Redis quota keys; không chấp nhận key từ query tùy ý như danh tính production.

### 11.7. Bucket4j/local cache không tự thành quota toàn cụm

Gateway WebFlux các phiên bản mới cũng có tích hợp **Bucket4j** và các persistence adapter. Ví dụ Bucket4j dùng **Caffeine local** phù hợp lab hoặc giới hạn theo replica, không tự chia sẻ bucket xuyên nhiều Gateway process. Chỉ khi có **distributed persistence** và cấu hình chính xác, mới nên coi quota được áp dụng toàn cụm.

## 12. Checklist trước khi đưa vào production

- [ ] Xác định quota theo **tenant/user/client/route** và phạm vi **per-replica hay global**.
- [ ] KeyResolver dựa trên danh tính đã xác thực hoặc IP từ proxy tin cậy; xử lý rõ missing key.
- [ ] Đã chọn thuật toán token bucket, fixed/sliding window phù hợp với mức burst cho phép.
- [ ] Có giới hạn TTL, số key và bộ nhớ Redis; tránh high-cardinality do caller tùy ý tạo key.
- [ ] Nếu dùng limiter tích hợp, đã kiểm tra **hành vi lỗi Redis ở đúng phiên bản**, không đoán fail-closed.
- [ ] Có policy riêng **fail-open, fail-closed hoặc bounded degrade** theo mức độ nhạy cảm API.
- [ ] Fail-closed do store lỗi trả mã hạ tầng phù hợp (thường 503), không ngụy trang thành quota-exceeded 429.
- [ ] Có deadline cho quota store và giới hạn retry; không để request mắc kẹt.
- [ ] Nếu fallback local, đã tính ngân sách theo **số Gateway replica tối đa**.
- [ ] Redis key/namespace/route ID/policy nhất quán giữa tất cả replicas.
- [ ] Test request đồng thời trên nhiều Gateway replica và thay đổi route/order.
- [ ] Test Redis down, slow, failover, phục hồi và key cardinality cao.
- [ ] CORS preflight, health checks và authentication được xử lý với policy rõ ràng.
- [ ] Rate limit không thay thế xác thực/phân quyền, WAF hoặc capacity protection.
- [ ] Retry/circuit breaker theo route không vô tình nhân nhiều backend attempts ngoài quota dự kiến.
- [ ] Metrics/trace phân biệt allow, 429, empty key và store outage, không chứa secrets/PII.
- [ ] Có runbook vận hành: ai được bật fail-open, thời gian tối đa, rollback và cảnh báo.

## 13. Câu hỏi tự kiểm tra

**1. Vì sao ba Gateway replica, mỗi replica giữ bộ đếm trong RAM 10 req/s, không bảo đảm quota toàn cụm 10 req/s?**

Vì state độc lập; cùng key có thể được cấp đến ba ngân sách. Cần kho chung, cấp quota theo lease hoặc cơ chế phân phối ngân sách có kiểm soát.

**2. Redis báo timeout nhưng code trả `RateLimiter.Response(false)`. Vì sao có thể sai?**

`false` thường khiến `RequestRateLimiter` trả **429**, mặc dù không biết client có vượt quota hay không. Với fail-closed, lỗi store nên được phân loại thành **503** hoặc chính sách hạ tầng thích hợp.

**3. Bọc `redisRateLimiter.isAllowed(...).onErrorResume(...)` đã bảo đảm bắt được mọi lỗi Redis?**

Không, nếu implementation RedisRateLimiter **đã bắt lỗi bên trong và trả allowed=true**. Cần kiểm tra source/version, fault injection hoặc triển khai đường quota có error semantics do chính mình kiểm soát.

**4. Vì sao `X-Lab-Key` trong ví dụ chỉ phù hợp localhost?**

Vì client có thể đổi header để lấy quota mới. Production cần principal/API key đã xác thực hoặc địa chỉ IP được xác minh qua proxy tin cậy.

**5. Khi Redis lỗi, một fallback 5 req/s trên mỗi Gateway có được coi là global 5 req/s không?**

Không. Nếu có bốn replica, nó có thể cấp tổng cộng 20 req/s. Cần ngân sách toàn cụm được phân phối hoặc chấp nhận rõ mức vượt trong bounded fallback.

## 14. Tài liệu tham khảo

1. [Spring Cloud Gateway Server WebFlux 5.x — RequestRateLimiter](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/gatewayfilter-factories/requestratelimiter-factory.html): `KeyResolver`, Redis token bucket, custom `RateLimiter`, Bucket4j và YAML.
2. [Spring Cloud Gateway Server WebFlux 4.3 — RequestRateLimiter](https://docs.spring.io/spring-cloud-gateway/reference/4.3/spring-cloud-gateway-server-webflux/gatewayfilter-factories/requestratelimiter-factory.html): cú pháp route và filter trong dòng 4.3.
3. [Spring Cloud Gateway 4.2 — RequestRateLimiter](https://docs.spring.io/spring-cloud-gateway/reference/4.2/spring-cloud-gateway/gatewayfilter-factories/requestratelimiter-factory.html): đối chiếu phiên bản 4.2.
4. [Spring Cloud Gateway — Configuration Properties](https://docs.spring.io/spring-cloud-gateway/reference/5.1/configprops.html): các properties của Redis limiter, route và filter WebFlux.
5. [Spring Data Redis — Reactive Redis Support](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories.html): bắt đầu từ tài liệu Spring Data Redis để kiểm tra reactive access và cấu hình Redis.
6. [RFC 6585 — 429 Too Many Requests](https://www.rfc-editor.org/rfc/rfc6585#section-4): ý nghĩa 429 và khả năng cung cấp `Retry-After`.

**Ghi nhớ:** `RequestRateLimiter` của Spring Cloud Gateway cần **KeyResolver đáng tin**, **RateLimiter quyết định chính xác** và **quota store phù hợp với phạm vi nhiều replica**. **Hết quota thực sự** khác với **không truy vấn được quota**. Khi Redis lỗi, fail-open, fail-closed hoặc degraded budget đều là một **quyết định bảo mật/vận hành có chủ đích**, phải được mã hóa rõ ràng, quan sát và kiểm chứng bằng fault injection; không nên suy từ status mặc định hoặc một lệnh `onErrorResume` đặt sai tầng.
