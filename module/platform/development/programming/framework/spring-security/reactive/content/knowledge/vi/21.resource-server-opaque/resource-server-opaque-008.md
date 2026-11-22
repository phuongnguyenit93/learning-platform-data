# Thiết kế timeout và bộ nhớ đệm theo yêu cầu thu hồi token

**Module:** Spring Security – reactive (Spring WebFlux)  
**Phần:** Resource Server Opaque  
**Mục tiêu:** Xây dựng chính sách gọi token introspection có giới hạn thời gian, dùng cache có kiểm soát và chứng minh bằng test rằng **thu hồi token có hiệu lực trong một cửa sổ thời gian đã thỏa thuận**, không âm thầm cho phép request khi không xác minh được Bearer token.

**Nguyên tắc quan trọng nhất:** Token introspection là một kiểm tra **trạng thái hiện tại** tại Authorization Server (AS), nhưng mỗi lần gọi AS sẽ tốn network latency và capacity. Lưu cache kết quả `active=true` giúp giảm tải nhưng giữ lại quyết định cấp quyền có thể **đã lỗi thời sau khi revoke**. Chọn cache TTL từ **revocation SLA** và `exp` của token, không lấy TTL bằng toàn bộ thời hạn sống của access token. Nếu không chấp nhận stale decision, để **positive cache TTL = 0** và kiểm tra introspection mỗi request; vẫn cần đánh giá độ trễ cập nhật ở AS và request đã đang xử lý. Trong mọi trường hợp, khi introspection không xác minh được token do timeout/network/AS outage, mặc định **fail-closed**: không biến kết quả chưa rõ thành authenticated principal.

Bài học gồm cơ chế RFC 7662, công thức thiết kế, timeout/circuit/retry, bounded cache, cấu hình Spring Security WebFlux Java 17+, ví dụ chạy độc lập với stdout chính xác, unit tests bằng đồng hồ giả và HTTP tests trong WebFlux. Các credential/token ví dụ là test fixture, không phải secret production.

## 1. Opaque Resource Server đang xác minh điều gì?

Một client gửi request đến Resource Server:

```http
GET /api/document HTTP/1.1
Host: docs.example.test
Authorization: Bearer opaque-token-value
```

Ở chế độ opaque token, `ReactiveOpaqueTokenIntrospector` nhận chuỗi token rồi thực hiện introspection qua HTTPS tới AS. Ví dụ request backend gửi:

```http
POST /oauth2/introspect HTTP/1.1
Host: idp.example.test
Authorization: Basic <encoded-resource-server-client-credentials>
Content-Type: application/x-www-form-urlencoded

token=opaque-token-value
```

AS trả kết quả trạng thái:

```json
{
  "active": true,
  "sub": "alice",
  "scope": "docs.read docs.write",
  "client_id": "approved-client",
  "exp": 1790000000
}
```

Spring Security đọc response hợp lệ, tạo `OAuth2AuthenticatedPrincipal`, ánh xạ scope thành `SCOPE_docs.read` và `SCOPE_docs.write`. Sau đó WebFlux authorization rule quyết định có cho vào handler hay không.

```text
Client
  |
  | Authorization: Bearer <token>
  v
WebFlux SecurityWebFilterChain
  |
  v
ReactiveOpaqueTokenIntrospector.introspect(token)
  |
  | HTTP POST, introspection credentials, TLS
  v
Authorization Server
  |
  | {"active": true, "scope": "docs.read", "exp": ...}
  v
OAuth2AuthenticatedPrincipal, GrantedAuthority SCOPE_docs.read
  |
  v
authorizeExchange.hasAuthority("SCOPE_docs.read")
  |
  +--> 200: active và đủ quyền
  +--> 401: thiếu/invalid token
  +--> 403: active nhưng không đủ scope
```

Nếu token đã revoke, AS có thể trả:

```json
{"active": false}
```

Theo RFC 7662, response `active=false` có thể là **HTTP 200 từ chính endpoint introspection**. Điều này **không có nghĩa** API phải trả 200: Resource Server phải coi Bearer token không hợp lệ, thông thường trả **401** cho client gọi API. Không log nguyên Bearer token hay introspection client secret.

### 1.1. Opaque nói đến cách xác minh, không chỉ định dạng chuỗi

Dù access token là chuỗi không đọc được hay JWT có cấu trúc, nếu Resource Server gửi token tới AS để hỏi `active` thì đang dùng **introspection**. JWT được kiểm chữ ký offline vẫn có thể đã bị thu hồi trước `exp`; vì vậy nếu hệ thống yêu cầu thu hồi sớm, chỉ kiểm JWS signature/exp thường không đủ. Có thể introspect JWT như opaque, hoặc thiết kế denylist/event/permission-version đáng tin riêng.

**Không nhầm với OIDC ID Token:** ID Token phục vụ Relying Party xác thực sự kiện login. Resource Server phải yêu cầu **access token** đúng audience, issuer, scope và policy; không chấp nhận ID Token chỉ vì nó cũng trông giống JWT.

### 1.2. Mặc định và điểm tùy chỉnh của Spring

Cấu hình Boot tối thiểu:

```properties
spring.security.oauth2.resourceserver.opaquetoken.introspection-uri=https://idp.example.test/oauth2/introspect
spring.security.oauth2.resourceserver.opaquetoken.client-id=resource-server-client
spring.security.oauth2.resourceserver.opaquetoken.client-secret=issued-secret
```

Trong WebFlux, `SpringReactiveOpaqueTokenIntrospector` thực hiện request HTTP bằng cơ chế reactive. Contract của nó:

```java
public interface ReactiveOpaqueTokenIntrospector {
    Mono<OAuth2AuthenticatedPrincipal> introspect(String token);
}
```

Bản cấu hình tối thiểu không đương nhiên cung cấp **bounded cache có TTL theo SLA thu hồi**. Nếu cần timeout/retry/cache/invalidation tùy biến, khai báo `@Bean ReactiveOpaqueTokenIntrospector` hoặc truyền introspector tường minh vào `oauth2ResourceServer(o -> o.opaqueToken(...))`.

**Đừng copy Servlet APIs:** `HttpSecurity`, `OpaqueTokenIntrospector` và `RestTemplate` là họ synchronous/Servlet. Với bài này dùng `ServerHttpSecurity`, `SecurityWebFilterChain`, `ReactiveOpaqueTokenIntrospector`, `WebClient` và Reactor.

## 2. Thu hồi token là một yêu cầu sản phẩm, không chỉ cấu hình cache

Trước khi chọn TTL, trả lời các câu hỏi:

1. Thu hồi một access token riêng lẻ, tất cả tokens của một user, client ID, device session hay mọi quyền của một tenant?
2. Token revoked phải ngừng được **chấp nhận tại API** sau tối đa bao nhiêu giây?
3. AS mất bao lâu để `active=false` được nhìn thấy ở **mọi replica / region introspection**?
4. Request đã xác thực **trước khi revocation** nhưng đang xử lý có được hoàn tất không?
5. Endpoint có độ nhạy khác nhau không (đọc dữ liệu tổng quan so với giao dịch tài chính hoặc quản lý admin)?
6. Có sự kiện revocation/invalidation được xác thực, delivered tới mọi Resource Server instances và có cơ chế reconciliation không?
7. Khi IdP outage, có thể chấp nhận từ chối phục vụ các API cần auth hay không?
8. Token introspection trả `exp`, `aud`, `sub`, `scope` với kiểu dữ liệu và SLA nhất quán không?
9. Cache bao nhiêu entries, nhiều tokens ngắn hạn hay cùng token gọi nhiều lần? QPS và tail latency thực?
10. Hệ thống nhiều issuer/tenant có thể vô tình dùng lại cache entry sai security domain không?

**Một token có `exp` sau 60 phút không cho phép cache `active=true` trong 60 phút.** `exp` là hard expiration boundary; revoke trước exp là điều cache có thể che khuất.

### 2.1. Công thức ngân sách revocation

Ký hiệu:

- `T_c`: TTL tối đa của một cached positive decision.
- `T_as`: độ trễ AS áp dụng/lan truyền revocation đến các introspection nodes.
- `T_event`: độ trễ sự kiện invalidation (nếu dựa vào event).
- `T_inflight`: thời gian hoàn tất những request đã được xác thực trước khi revoked.
- `T_margin`: clock skew, scheduling và biên an toàn.
- `SLA_revocation`: thời hạn quan sát được revocation tối đa theo chính sách.

Mô hình ngân sách thận trọng:

```text
window_max ~= T_c + T_as + T_event + T_inflight + T_margin

T_c <= SLA_revocation
       - T_as - T_event - T_inflight - T_margin
```

Đây là **phép tính định hướng**, không phải công thức bảo đảm của Spring Security. Nếu không có giới hạn trên đáng tin cho `T_as` hoặc độ trễ event, không thể cam kết SLA cứng chỉ nhờ TTL.

Ví dụ giả định:

| Bề mặt | SLA thu hồi | AS + inflight + margin | TTL tối đa còn lại | Cách làm |
| --- | ---: | ---: | ---: | --- |
| Tác vụ quản trị đặc biệt | 1 giây | 1 giây | 0 giây | Không positive cache; kiểm policy tại điểm commit |
| API văn bản nội bộ | 12 giây | 4 giây | 8 giây | TTL tối đa 8 giây; nên dự phòng thêm |
| Read-only ít nhạy cảm | 90 giây | 20 giây | 70 giây | TTL ngắn hơn 70 giây nếu được phê duyệt |
| Không đo được AS propagation | Không bảo đảm | Không rõ | Không suy được | Không tuyên bố SLA thu hồi |

**Phép tính mẫu:** SLA 10 giây, AS propagation 3 giây, inflight + margin 2 giây ⇒ budget cache 5 giây.

### 2.2. TTL từng entry cần chặn bởi exp

Giả sử một request introspect thành công lúc `now`, token có `exp`:

```text
entry.validUntil = min(now + positiveCacheTtl, exp)
```

Nếu cache policy 5 giây mà token còn 2 giây tới exp, **TTL thực chỉ còn 2 giây**. Nếu token `exp` đã qua, không sử dụng principal. Nếu introspection response không có exp hoặc kiểu exp không được hiểu đúng, một chính sách an toàn là **không positive-cache**; luôn hỏi lại AS vào request sau.

TTL nên tính từ **lần introspection thành công**, không từ `iat`. Không cache error/`active=false` rồi tái sử dụng như authenticated principal.

### 2.3. Vì sao TTL=0 vẫn không có “thu hồi tức thời tuyệt đối”?

Cache TTL=0 làm **request mới** gọi AS, nhưng vẫn có:

- AS eventual consistency/cập nhật nhiều region.
- Request đang xử lý sau một quyết định quyền trước revoke.
- Reverse proxy/gateway hoặc tầng auth phía trước có thể có cache khác.
- Background jobs/các kết nối dài/WebSocket có thể giữ authorization từ thời điểm bắt đầu.
- Revocation có thể chỉ là event bất đồng bộ; response revoke thành công không có nghĩa mọi AS replica đã sẵn sàng.

Với quyền đặc biệt nhạy cảm, có thể phải thêm user/permission version, denylist/recheck tại commit, cắt session và thực thi transaction-level policy, không chỉ kiểm token một lần lúc bắt đầu HTTP request.

## 3. Latency budget và timeout: đặt theo đường gọi IdP thật

Không để một external introspection call kéo dài hàng chục giây rồi làm cạn thread/connection pool. Trong Reactor/WebFlux, phân biệt các giới hạn:

| Giới hạn | Chặn điều gì | Ví dụ |
| --- | --- | --- |
| DNS resolution | Tra cứu tên IdP | Resolver timeout/cache đúng môi trường |
| TCP connect | Thiết lập kết nối | `CONNECT_TIMEOUT_MILLIS` |
| TLS handshake | Thiết lập kênh an toàn | TLS timeout + truststore |
| Connection acquire | Chờ lấy connection từ pool | Pool `pendingAcquireTimeout` |
| Response time | Chờ HTTP response | Reactor Netty `HttpClient.responseTimeout` |
| **Overall introspection deadline** | Tổng publisher gồm network/các bước delegate | Reactor `Mono.timeout(Duration)` |
| API request deadline | Authentication + business + response | Ingress/client timeout |
| Retry/timeouts | Nhiều attempts và backoff | Tổng retries phải nằm trong deadline |
| Bulkhead/circuit | Hạn chế ảnh hưởng khi IdP chậm/down | Bounded concurrency, fail-closed |

**Ngân sách minh họa**, không mặc định phù hợp mọi hệ thống:

```text
API p99 goal                  900 ms
Business/response budget      250 ms
IdP introspection total       550 ms
Reserve                       100 ms

TCP connect ceiling           150 ms
Response wait ceiling         350 ms
Whole introspection deadline  550 ms
Automatic retry               OFF
```

`Mono.timeout` là deadline từ lúc subscription tới phản hồi Mono; nó không thay các timeout của network pool/TLS, nhưng cho một trần tổng thể dễ quan sát. `HttpClient.responseTimeout` giúp giới hạn đợi response cụ thể. Một kết nối có thể mất thời gian chờ pool/DNS/TLS trước khi vào giai đoạn response; vì thế phải có **overall deadline**.

### 3.1. Timeout khác invalid token

- Introspection có kết quả `active=false`: **token invalid**, thường API 401.
- AS không reachable, DNS/TLS lỗi, hết deadline, AS 429/5xx: **không biết tình trạng token**, do đó fail-closed, không xử lý như authenticated.
- AS từ chối introspection client credentials: lỗi cấu hình/vận hành, **không phải** bằng chứng user token inactive.
- Token active nhưng thiếu `SCOPE_docs.write`: API **403** theo authorization policy.

**Không cam kết mọi timeout tự trả 503.** Trạng thái HTTP cho dependency error tùy Spring Security exception translation/custom handler. Nếu cần HTTP 503 (service unavailable) thay vì 401/500, hãy triển khai mapping có kiểm soát và test thực tại ingress. Điều không được thay đổi là request có Bearer **chưa xác minh** không được phép vào handler được bảo vệ.

### 3.2. Retry có thể làm sự cố tệ hơn

Không retry `active=false`, invalid token/invalid client, mọi lỗi 4xx một cách mù quáng. Với 429/502/503/network timeout có thể cân nhắc một retry ngắn theo backoff/jitter, nhưng phải:

- Giữ tổng attempts + delay **trong** deadline.
- Tôn trọng chính sách provider và `Retry-After`.
- Không retry storm khi IdP quá tải.
- Không tạo cơ chế fail-open/stale-after-expiry khi circuit breaker mở.
- Bật metrics theo reason và disable retry mặc định khi chưa có số liệu.

Nếu AS mất kết nối vài phút, cách an toàn là protected API tạm từ chối/không phục vụ, không tự tăng cache TTL vô hạn để duy trì tỷ lệ 200.

## 4. Thiết kế cache: chỉ positive, có giới hạn và có quyền thu hồi

| Kết quả introspection | Có nên cache? | Ghi chú |
| --- | --- | --- |
| `active=true`, principal/scope đã được AS chấp nhận | **Có thể** | Max TTL theo SLA, cap bởi exp |
| `active=false` | Không trong sample | Negative caching có rủi ro riêng, phải được thiết kế |
| Timeout, DNS/TLS/network error | Không | Không biết token active hay revoked |
| AS 401/403 vì sai introspection credentials | Không | Lỗi server-to-server |
| AS 429/5xx | Không | Dependency unavailable không phải authenticated |
| Mono rỗng/malformed response | Không | Không có principal hợp lệ |
| Cached principal đã quá `validUntil` | Không | Phải introspect lại |
| Token exp đã qua | Không | Không vượt hard expiry |
| Event revoke đáng tin | Invalidate entry khi có thể | Event delivery/race phải được kiểm |
| Token thuộc issuer/tenant khác | Không dùng chung | Phân vùng namespace và policy |

### 4.1. Cấm mẫu last-known-good không giới hạn

```java
// ANTI-PATTERN: RẤT NGUY HIỂM đối với dữ liệu bảo vệ.
return idp.introspect(token)
    .onErrorResume(ex -> Mono.just(lastKnownGoodPrincipal));
```

Nó biến AS outage thành một con đường **bỏ qua revocation**. Tương tự, `Mono.cache()` hoặc map lưu toàn bộ Mono theo token mà không quy định size/TTL/error policy có thể:

- Cache lỗi hoặc cached success vô hạn.
- Giữ token plaintext làm key trong heap/log.
- Tăng cardinality tới memory exhaustion.
- Trộn kết quả AS/tenant khác nhau.
- Không invalidate được sau revoke.
- Không phân biệt lỗi network và invalid token.

### 4.2. Positive cache an toàn hơn cần những thuộc tính gì?

- **Bounded size:** `maximumSize`/eviction, chống attacker tạo vô số tokens khác nhau.
- **Positive-only:** chỉ cache `onNext` của `delegate.introspect(token)` đã xác thực; lỗi không được cache.
- **TTL:** `min(now + maxAge, token.exp)` và kiểm deadline trước mỗi hit.
- **TTL = 0 option:** tắt cache thành công cho nhóm endpoint yêu cầu fresh.
- **No raw bearer key:** key dùng HMAC digest bằng secret riêng, hạn chế rò token nếu heap/cache debug; principal vẫn là dữ liệu nhạy cảm.
- **Isolation:** issuer/AS/tenant và client registration phải được phân vùng; sample chỉ một AS.
- **Trusted invalidation:** có thể xóa entry khi AS gửi sự kiện revoke đáng tin, nhưng event phải tới mọi pod.
- **Failure behavior:** không stale-on-error; sau entry hết hạn mà AS down thì request không được xác thực.
- **Concurrency:** nhiều cache misses cùng token có thể gây stampede; production cần bounded single-flight/backpressure/circuit khi số đo cho thấy cần.

### 4.3. Caffeine và token expiry

`Caffeine.expireAfterWrite(maxAge)` đặt một trần physical-time cho entry. Tuy nhiên **mỗi token có exp khác nhau**. Cần lưu riêng `validUntil` và kiểm ở hit:

```text
Caffeine physical expiration: tối đa policy maxAge
Entry validUntil: min(now + policy maxAge, exp)
Allowed cache hit: clock.now < validUntil
```

Nếu `maxAge=0`, không gọi cache put. Hệ đa pod có local Caffeine cache sẽ có các cửa sổ stale riêng; local `invalidate(token)` không tự broadcast. Nếu Revocation API chỉ cung cấp `jti`/session ID, cần reverse index hoặc denylist theo trusted ID (không gửi raw Bearer qua event bus).

## 5. Java 17 độc lập: tính ngân sách TTL và stdout chính xác

Chạy chương trình không dùng Spring để hiểu công thức. Đây là mô hình số học, **không** thay introspection thật.

Lưu `RevocationBudgetDemo.java`:

```java
import java.time.Duration;
import java.time.Instant;

public class RevocationBudgetDemo {
    static Duration cacheBudget(
            Duration sla, Duration asPropagation,
            Duration inflightAndMargin) {

        Duration remain = sla.minus(asPropagation)
            .minus(inflightAndMargin);

        return remain.isNegative()
            ? Duration.ZERO : remain;
    }

    static Duration actualEntryTtl(
            Instant now, Instant exp, Duration maxTtl) {

        Duration remaining = Duration.between(now, exp);
        if (remaining.isNegative() || remaining.isZero()) {
            return Duration.ZERO;
        }
        return remaining.compareTo(maxTtl) < 0
            ? remaining : maxTtl;
    }

    public static void main(String[] args) {
        Duration budget = cacheBudget(
            Duration.ofSeconds(10),
            Duration.ofSeconds(3),
            Duration.ofSeconds(2));

        Instant now = Instant.parse("2026-01-01T00:00:00Z");
        Duration entry = actualEntryTtl(
            now, now.plusSeconds(2), budget);

        System.out.println("cacheBudget=" + budget);
        System.out.println("entryTtl=" + entry);
        System.out.println("strict=" +
            cacheBudget(Duration.ofSeconds(1),
                Duration.ofSeconds(2), Duration.ZERO));
    }
}
```

Chạy JDK 17+:

```bash
javac RevocationBudgetDemo.java
java RevocationBudgetDemo
```

**Stdout chính xác:**

```text
cacheBudget=PT5S
entryTtl=PT2S
strict=PT0S
```

**Giải thích:** Revocation SLA 10s trừ AS 3s và inflight/margin 2s còn 5s cache budget. Nhưng một token chỉ còn sống 2s thì entry được cache tối đa 2s. SLA 1s trong khi AS propagation 2s không đủ budget: TTL phải 0, và vẫn không thể bảo đảm SLA cứng nếu AS chậm 2s.

## 6. Project Spring Boot WebFlux Java 17+ minh họa đầy đủ

Project có WebFlux Resource Server Bearer-only, một `ReactiveOpaqueTokenIntrospector` dùng WebClient timeout và wrapper Caffeine positive cache. Test có fake-clock logic và WebTestClient HTTP; không cần Authorization Server thật để chạy test mẫu.

```text
opaque-cache-timeout/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/opaque/
    │   │   ├── OpaqueApplication.java
    │   │   ├── RevocationBoundIntrospector.java
    │   │   ├── SecurityConfig.java
    │   │   └── DocumentController.java
    │   └── resources/application.properties
    └── test/java/demo/opaque/
        ├── RevocationBoundIntrospectorTests.java
        └── OpaqueHttpTests.java
```

**Mốc dependency:** Spring Boot 3.5.7, Java 17+ và Maven 3.9+. Khi triển khai sản phẩm thật phải chọn bản còn hỗ trợ và cập nhật bản vá, không cố định bản giáo trình vô thời hạn. Không thêm `spring-boot-starter-web` vì bài dùng WebFlux/reactive, không phải Servlet.

`pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>opaque-cache-timeout</artifactId>
    <version>1.0.0</version>
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
            <artifactId>spring-boot-starter-oauth2-resource-server</artifactId>
        </dependency>
        <dependency>
            <groupId>com.github.ben-manes.caffeine</groupId>
            <artifactId>caffeine</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
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
```

`src/main/resources/application.properties`:

```properties
spring.application.name=opaque-cache-timeout
server.port=8080

# IdP/credentials placeholder: thay bằng endpoint, ID, secret thật được phê duyệt.
demo.introspection.uri=https://idp.example.invalid/oauth2/introspect
demo.introspection.client-id=resource-server-training
demo.introspection.client-secret=${INTROSPECTION_CLIENT_SECRET:training-not-valid}

# Số liệu demo, không phải lựa chọn mặc định cho mọi sản phẩm.
demo.introspection.connect-ms=150
demo.introspection.response-ms=350
demo.introspection.deadline-ms=550
demo.introspection.cache-ms=2000
demo.introspection.max-entries=10000
```

`demo.introspection.cache-ms=0` là lựa chọn tắt positive cache. Không coi việc tắt cache là đã giải quyết AS eventual consistency/inflight requests. Client secret ở đây **chỉ dành cho xác thực Resource Server với AS introspection endpoint**, không phải token/user password. Trong production dùng secret manager và HTTPS trust configuration.

`src/main/java/demo/opaque/OpaqueApplication.java`:

```java
package demo.opaque;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OpaqueApplication {
    public static void main(String[] args) {
        SpringApplication.run(OpaqueApplication.class, args);
    }
}
```

### 6.1. RevocationBoundIntrospector.java

Wrapper dùng Caffeine và token HMAC fingerprint. Nó không làm introspection protocol; `delegate` là một introspector thật hoặc fake test đã xác minh `active`.

`src/main/java/demo/opaque/RevocationBoundIntrospector.java`:

```java
package demo.opaque;

import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.SecureRandom;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.HexFormat;
import java.util.Objects;

import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

import com.github.benmanes.caffeine.cache.Cache;
import com.github.benmanes.caffeine.cache.Caffeine;

import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.core.OAuth2TokenIntrospectionClaimNames;
import org.springframework.security.oauth2.server.resource.introspection.BadOpaqueTokenException;
import org.springframework.security.oauth2.server.resource.introspection.ReactiveOpaqueTokenIntrospector;

import reactor.core.publisher.Mono;

public final class RevocationBoundIntrospector
        implements ReactiveOpaqueTokenIntrospector {

    private static final String HMAC = "HmacSHA256";

    private record Entry(
        OAuth2AuthenticatedPrincipal principal,
        Instant validUntil
    ) {}

    private final ReactiveOpaqueTokenIntrospector delegate;
    private final Duration deadline;
    private final Duration maxAge;
    private final Clock clock;
    private final byte[] hmacKey = new byte[32];
    private final Cache<String, Entry> cache;

    public RevocationBoundIntrospector(
            ReactiveOpaqueTokenIntrospector delegate,
            Duration deadline,
            Duration maxAge,
            long maxEntries,
            Clock clock) {

        this.delegate = Objects.requireNonNull(delegate);
        this.clock = Objects.requireNonNull(clock);
        this.deadline = Objects.requireNonNull(deadline);
        this.maxAge = Objects.requireNonNull(maxAge);

        if (deadline.isZero() || deadline.isNegative()
                || maxAge.isNegative() || maxEntries < 0) {
            throw new IllegalArgumentException(
                "Timeout, TTL or capacity is invalid");
        }

        new SecureRandom().nextBytes(hmacKey);

        Duration physicalTtl = maxAge.isZero()
            ? Duration.ofMillis(1) : maxAge;

        this.cache = Caffeine.newBuilder()
            .maximumSize(maxEntries)
            .expireAfterWrite(physicalTtl)
            .build();
    }

    @Override
    public Mono<OAuth2AuthenticatedPrincipal> introspect(String token) {
        return Mono.defer(() -> {
            String key = cacheKey(token);
            Instant now = clock.instant();

            Entry cached = cache.getIfPresent(key);
            if (cached != null
                    && now.isBefore(cached.validUntil())) {
                return Mono.just(cached.principal());
            }

            if (cached != null) {
                cache.invalidate(key);
            }

            // Không dùng stale entry trên lỗi hoặc AS outage.
            return delegate.introspect(token)
                .timeout(deadline)
                .switchIfEmpty(Mono.error(
                    new BadOpaqueTokenException(
                        "Empty introspection response")))
                .flatMap(principal -> {
                    Instant checkedAt = clock.instant();
                    Object raw = principal.getAttribute(
                        OAuth2TokenIntrospectionClaimNames.EXP);
                    Instant exp = expiry(raw);

                    if (exp != null
                            && !checkedAt.isBefore(exp)) {
                        return Mono.error(
                            new BadOpaqueTokenException(
                                "Introspection token expired"));
                    }

                    // Không có exp hoặc TTL=0 => không positive-cache.
                    if (!maxAge.isZero() && exp != null) {
                        Instant until = checkedAt.plus(maxAge);
                        if (exp.isBefore(until)) {
                            until = exp;
                        }
                        if (checkedAt.isBefore(until)) {
                            cache.put(key, new Entry(principal, until));
                        }
                    }

                    return Mono.just(principal);
                });
        });
    }

    // Chỉ code tin cậy đã có token mới có thể gọi hàm này.
    // Không gửi raw token trên revocation event bus.
    public void invalidate(String token) {
        cache.invalidate(cacheKey(token));
    }

    private static Instant expiry(Object value) {
        if (value instanceof Instant t) {
            return t;
        }
        if (value instanceof Number t) {
            return Instant.ofEpochSecond(t.longValue());
        }
        return null;
    }

    private String cacheKey(String token) {
        Objects.requireNonNull(token, "token");
        try {
            Mac mac = Mac.getInstance(HMAC);
            mac.init(new SecretKeySpec(hmacKey, HMAC));
            return HexFormat.of().formatHex(
                mac.doFinal(token.getBytes(
                    StandardCharsets.UTF_8)));
        }
        catch (GeneralSecurityException ex) {
            throw new IllegalStateException(
                "Cannot compute HMAC key", ex);
        }
    }
}
```

**QA của thiết kế wrapper:**

1. `Mono.defer` kiểm cache ở subscription time, không giữ dữ liệu một lần từ khi assemble Mono.
2. `cache.getIfPresent` chỉ chấp nhận entry khi `now < validUntil`; nếu cũ thì xóa, hỏi lại AS.
3. `delegate.introspect(token)` là nơi xác minh active. Wrapper chỉ lưu **principal thành công**, không lưu inactive/error/empty.
4. `Mono.timeout(deadline)` áp deadline trên cache miss. Timeout phát error, **không** trả principal tạm.
5. `maxAge=Duration.ZERO` bỏ positive cache; vẫn có timeout.
6. Token có `exp` dạng `Instant` hoặc epoch seconds số được hỗ trợ. Nếu exp không có, không cache; tùy chính sách có thể chọn reject toàn bộ response không exp.
7. Cache Caffeine có `maximumSize`, `expireAfterWrite` và validUntil theo exp. Không cache raw token string trong key, chỉ HMAC digest với khóa ngẫu nhiên per-process. Principal/claims trong cache vẫn là dữ liệu nhạy cảm.
8. Hàm `invalidate(token)` chỉ xóa **local instance** khi trusted code thực sự có token. Không dùng nó để hứa invalidation đa pod; event theo jti/subject cần reverse index/version và consistency design riêng.
9. Sample không gộp đồng thời các cache misses (*single-flight*). Cold-start có thể tạo nhiều introspection calls cho cùng token; production xem metrics/bulkhead/dedup có giới hạn.
10. Cache positive là một quyết định **cố ý chấp nhận stale window**. Khi token revoke ngay sau cache miss, entry còn được dùng tới tối đa TTL. Nếu threat model không chấp nhận, đặt TTL 0.

### 6.2. SecurityConfig.java với network timeouts

`src/main/java/demo/opaque/SecurityConfig.java`:

```java
package demo.opaque;

import java.time.Clock;
import java.time.Duration;

import io.netty.channel.ChannelOption;
import reactor.netty.http.client.HttpClient;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.oauth2.server.resource.introspection.ReactiveOpaqueTokenIntrospector;
import org.springframework.security.oauth2.server.resource.introspection.SpringReactiveOpaqueTokenIntrospector;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.context.NoOpServerSecurityContextRepository;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfig {

    @Bean
    ReactiveOpaqueTokenIntrospector introspector(
            @Value("${demo.introspection.uri}") String uri,
            @Value("${demo.introspection.client-id}") String id,
            @Value("${demo.introspection.client-secret}") String secret,
            @Value("${demo.introspection.connect-ms}") int connectMs,
            @Value("${demo.introspection.response-ms}") long responseMs,
            @Value("${demo.introspection.deadline-ms}") long deadlineMs,
            @Value("${demo.introspection.cache-ms}") long cacheMs,
            @Value("${demo.introspection.max-entries}") long maxEntries) {

        HttpClient transport = HttpClient.create()
            .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, connectMs)
            .responseTimeout(Duration.ofMillis(responseMs));

        // Chỉ dùng WebClient này gọi introspection URI do admin cấu hình.
        WebClient asClient = WebClient.builder()
            .clientConnector(new ReactorClientHttpConnector(transport))
            .defaultHeaders(headers -> headers.setBasicAuth(id, secret))
            .build();

        // Spring Security 6.5: constructor nhận WebClient.
        ReactiveOpaqueTokenIntrospector actualAs =
            new SpringReactiveOpaqueTokenIntrospector(
                uri, asClient);

        return new RevocationBoundIntrospector(
            actualAs,
            Duration.ofMillis(deadlineMs),
            Duration.ofMillis(cacheMs),
            maxEntries,
            Clock.systemUTC());
    }

    @Bean
    SecurityWebFilterChain security(
            ServerHttpSecurity http,
            ReactiveOpaqueTokenIntrospector introspector) {

        return http
            .securityContextRepository(
                NoOpServerSecurityContextRepository.getInstance())
            .authorizeExchange(ex -> ex
                .pathMatchers(HttpMethod.GET, "/public")
                    .permitAll()
                .pathMatchers(HttpMethod.GET, "/api/document")
                    .hasAuthority("SCOPE_docs.read")
                .pathMatchers(HttpMethod.POST, "/api/document")
                    .hasAuthority("SCOPE_docs.write")
                .pathMatchers(HttpMethod.GET, "/api/whoami")
                    .authenticated()
                .anyExchange().denyAll())
            .oauth2ResourceServer(oauth2 ->
                oauth2.opaqueToken(opaque ->
                    opaque.introspector(introspector)))
            .formLogin(form -> form.disable())
            .httpBasic(basic -> basic.disable())
            // Chỉ cho API Bearer header-only. Nếu dùng cookie auth,
            // phải đánh giá lại và giữ CSRF ở route tương ứng.
            .csrf(csrf -> csrf.disable())
            .build();
    }
}
```

**Vì sao 3 timeout?** `CONNECT_TIMEOUT_MILLIS` giới hạn TCP connect. `HttpClient.responseTimeout` giới hạn đợi response. Wrapper `Mono.timeout` là deadline cho **toàn introspection attempt**, không bị một bước chờ connection pool/TLS kéo dài quá mức. Trong production bổ sung pool acquire timeout, TLS handshake timeout, DNS configuration và connection limits theo hạ tầng thật.

**Cẩn thận Basic:** `defaultHeaders.setBasicAuth(id,secret)` chỉ dùng **server-to-server** khi Resource Server gọi endpoint introspection. API inbound từ Internet vẫn **không** chấp nhận HTTP Basic; vì vậy `httpBasic.disable()` không mâu thuẫn.

Nếu IdP dùng `private_key_jwt`/mTLS thay Basic, mẫu này cần thay cơ chế client authentication. Không dùng WebClient Basic chứa secret này cho những URI do user tự nhập; rủi ro SSRF và credential leak.

### 6.3. Controller chỉ mô phỏng business request

`src/main/java/demo/opaque/DocumentController.java`:

```java
package demo.opaque;

import org.springframework.http.MediaType;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class DocumentController {

    @GetMapping(value = "/public",
                produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> publicPage() {
        return Mono.just("public");
    }

    @GetMapping(value = "/api/document",
                produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> readDocument() {
        return Mono.just("document-visible");
    }

    @PostMapping(value = "/api/document",
                 produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> updateDocument() {
        // Chỉ demo, không thay đổi dữ liệu thật.
        return Mono.just("document-updated");
    }

    @GetMapping(value = "/api/whoami",
                produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> whoami() {
        return ReactiveSecurityContextHolder.getContext()
            .map(ctx -> ctx.getAuthentication().getName());
    }
}
```

Resource Server thực còn phải kiểm tenant/owner và business permissions ở service/repository. `SCOPE_docs.read` cho biết token có loại quyền “đọc tài liệu”, **không** chứng minh user có quyền đọc bất kỳ document nào. Không log raw tokens/full introspection JSON; `whoami` chỉ trả name được bảo vệ.

## 7. Unit tests: timeout, cache TTL, token expiry và revocation stale window

Test dùng `MutableClock` để tiến thời gian bằng tay. Độ dài TTL được xác minh **không cần sleep hàng giây**, tránh flakiness. Trường hợp AS timeout dùng `Mono.never()` và deadline 70ms.

`src/test/java/demo/opaque/RevocationBoundIntrospectorTests.java`:

```java
package demo.opaque;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.util.List;
import java.util.Map;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

import org.junit.jupiter.api.Test;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.core.DefaultOAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.introspection.BadOpaqueTokenException;
import org.springframework.security.oauth2.server.resource.introspection.ReactiveOpaqueTokenIntrospector;

import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;

class RevocationBoundIntrospectorTests {

    static class MutableClock extends Clock {
        private final AtomicReference<Instant> now =
            new AtomicReference<>(
                Instant.parse("2026-01-01T00:00:00Z"));

        @Override
        public ZoneId getZone() {
            return ZoneOffset.UTC;
        }

        @Override
        public Clock withZone(ZoneId zone) {
            return this;
        }

        @Override
        public Instant instant() {
            return now.get();
        }

        void advance(long seconds) {
            now.updateAndGet(t -> t.plusSeconds(seconds));
        }
    }

    private static OAuth2AuthenticatedPrincipal active(
            Instant expiry) {
        return new DefaultOAuth2AuthenticatedPrincipal(
            "alice",
            Map.of("sub", "alice", "scope", "docs.read",
                "exp", expiry),
            List.of(new SimpleGrantedAuthority("SCOPE_docs.read")));
    }

    private static OAuth2AuthenticatedPrincipal withoutExp() {
        return new DefaultOAuth2AuthenticatedPrincipal(
            "alice", Map.of("sub", "alice"),
            List.of(new SimpleGrantedAuthority("SCOPE_docs.read")));
    }

    private static RevocationBoundIntrospector wrapper(
            ReactiveOpaqueTokenIntrospector delegate,
            Clock clock, Duration ttl) {
        return new RevocationBoundIntrospector(
            delegate, Duration.ofMillis(70), ttl,
            100, clock);
    }

    @Test
    void repeatedPositiveHitCallsAsOnlyOnce() {
        MutableClock c = new MutableClock();
        AtomicInteger calls = new AtomicInteger();

        ReactiveOpaqueTokenIntrospector as = token -> {
            calls.incrementAndGet();
            return Mono.just(active(
                c.instant().plusSeconds(60)));
        };

        var cache = wrapper(as, c, Duration.ofSeconds(5));
        assertEquals("alice", cache.introspect("A")
            .block().getName());
        assertEquals("alice", cache.introspect("A")
            .block().getName());
        assertEquals(1, calls.get());
    }

    @Test
    void afterPolicyTtlExpiresIntrospectsAgain() {
        MutableClock c = new MutableClock();
        AtomicInteger calls = new AtomicInteger();

        ReactiveOpaqueTokenIntrospector as = token -> {
            calls.incrementAndGet();
            return Mono.just(active(
                c.instant().plusSeconds(60)));
        };

        var cache = wrapper(as, c, Duration.ofSeconds(2));
        cache.introspect("A").block();
        c.advance(3);
        cache.introspect("A").block();
        assertEquals(2, calls.get());
    }

    @Test
    void tokenExpCapsCacheEntryBeforePolicyTtl() {
        MutableClock c = new MutableClock();
        AtomicInteger calls = new AtomicInteger();

        ReactiveOpaqueTokenIntrospector as = token -> {
            calls.incrementAndGet();
            return Mono.just(active(
                c.instant().plusSeconds(1)));
        };

        var cache = wrapper(as, c, Duration.ofSeconds(10));
        cache.introspect("A").block();
        c.advance(2);
        cache.introspect("A").block();
        assertEquals(2, calls.get());
    }

    @Test
    void revocationCanRemainCachedUntilTtlExpires() {
        MutableClock c = new MutableClock();
        AtomicInteger calls = new AtomicInteger();
        AtomicBoolean revoked = new AtomicBoolean(false);

        ReactiveOpaqueTokenIntrospector as = token -> {
            calls.incrementAndGet();
            return revoked.get()
                ? Mono.error(new BadOpaqueTokenException("inactive"))
                : Mono.just(active(
                    c.instant().plusSeconds(60)));
        };

        var cache = wrapper(as, c, Duration.ofSeconds(2));
        cache.introspect("A").block();
        revoked.set(true);

        // Một cache hit ngay sau revoke: stale window được chấp nhận.
        assertEquals("alice", cache.introspect("A")
            .block().getName());
        assertEquals(1, calls.get());

        c.advance(3);
        StepVerifier.create(cache.introspect("A"))
            .expectError(BadOpaqueTokenException.class)
            .verify();
        assertEquals(2, calls.get());
    }

    @Test
    void zeroTtlChecksRevokedStateOnNextRequest() {
        MutableClock c = new MutableClock();
        AtomicInteger calls = new AtomicInteger();
        AtomicBoolean revoked = new AtomicBoolean(false);

        ReactiveOpaqueTokenIntrospector as = token -> {
            calls.incrementAndGet();
            return revoked.get()
                ? Mono.error(new BadOpaqueTokenException("inactive"))
                : Mono.just(active(
                    c.instant().plusSeconds(60)));
        };

        var cache = wrapper(as, c, Duration.ZERO);
        cache.introspect("A").block();
        revoked.set(true);
        StepVerifier.create(cache.introspect("A"))
            .expectError(BadOpaqueTokenException.class)
            .verify();
        assertEquals(2, calls.get());
    }

    @Test
    void missingExpNeverPositiveCaches() {
        MutableClock c = new MutableClock();
        AtomicInteger calls = new AtomicInteger();
        ReactiveOpaqueTokenIntrospector as = token -> {
            calls.incrementAndGet();
            return Mono.just(withoutExp());
        };

        var cache = wrapper(as, c, Duration.ofSeconds(5));
        cache.introspect("A").block();
        cache.introspect("A").block();
        assertEquals(2, calls.get());
    }

    @Test
    void inactiveErrorNeverBecomesCachedSuccess() {
        MutableClock c = new MutableClock();
        AtomicInteger calls = new AtomicInteger();

        ReactiveOpaqueTokenIntrospector as = token -> {
            calls.incrementAndGet();
            return Mono.error(
                new BadOpaqueTokenException("inactive"));
        };

        var cache = wrapper(as, c, Duration.ofSeconds(5));

        StepVerifier.create(cache.introspect("bad"))
            .expectError(BadOpaqueTokenException.class)
            .verify();
        StepVerifier.create(cache.introspect("bad"))
            .expectError(BadOpaqueTokenException.class)
            .verify();
        assertEquals(2, calls.get());
    }

    @Test
    void emptyIntrospectionFailsClosed() {
        MutableClock c = new MutableClock();
        ReactiveOpaqueTokenIntrospector as = token -> Mono.empty();

        var cache = wrapper(as, c, Duration.ofSeconds(5));
        StepVerifier.create(cache.introspect("empty"))
            .expectError(BadOpaqueTokenException.class)
            .verify();
    }

    @Test
    void timeoutFailsClosedInsteadOfReturningPrincipal() {
        MutableClock c = new MutableClock();
        ReactiveOpaqueTokenIntrospector as = token -> Mono.never();

        var cache = wrapper(as, c, Duration.ofSeconds(5));
        StepVerifier.create(cache.introspect("slow"))
            .expectError(TimeoutException.class)
            .verify(Duration.ofSeconds(2));
    }

    @Test
    void trustedLocalInvalidateForcesNewIntrospection() {
        MutableClock c = new MutableClock();
        AtomicInteger calls = new AtomicInteger();

        ReactiveOpaqueTokenIntrospector as = token -> {
            calls.incrementAndGet();
            return Mono.just(active(
                c.instant().plusSeconds(60)));
        };

        var cache = wrapper(as, c, Duration.ofSeconds(5));
        cache.introspect("A").block();
        cache.invalidate("A");
        cache.introspect("A").block();
        assertEquals(2, calls.get());
    }

    @Test
    void distinctBearerStringsCannotReuseOneEntry() {
        MutableClock c = new MutableClock();
        AtomicInteger calls = new AtomicInteger();

        ReactiveOpaqueTokenIntrospector as = token -> {
            calls.incrementAndGet();
            return Mono.just(active(
                c.instant().plusSeconds(60)));
        };

        var cache = wrapper(as, c, Duration.ofSeconds(5));
        cache.introspect("A").block();
        cache.introspect("B").block();
        cache.introspect("A").block();
        assertEquals(2, calls.get());
    }

    @Test
    void expiredIntrospectionResponseIsRejected() {
        MutableClock c = new MutableClock();
        ReactiveOpaqueTokenIntrospector as = token ->
            Mono.just(active(c.instant().minusSeconds(1)));

        var cache = wrapper(as, c, Duration.ofSeconds(5));
        StepVerifier.create(cache.introspect("expired"))
            .expectError(BadOpaqueTokenException.class)
            .verify();
    }
}
```

**Tại sao test revocation có một cache hit “stale” là đúng?** Vì policy TTL > 0 đồng nghĩa hệ chấp nhận một khoảng thời gian không hỏi AS. Test không nên che giấu điều đó. Cần chuyển kết quả thành SLO và chứng minh window thực tế ≤ mức được duyệt.

`StepVerifier` kiểm timeout trực tiếp ở lớp wrapper, **không** tự chứng minh controller trả đúng HTTP 503 hay 401. Muốn kiểm mã dependency failure, phải bổ sung global exception mapping/entry point và integration tests với AS mock/staging, không suy đoán status.

## 8. WebTestClient integration: Bearer resource policy không cần AS ngoài

Ta dùng một `@TestConfiguration` cung cấp `@Primary ReactiveOpaqueTokenIntrospector` giả cho các Bearer tokens học tập: `reader-demo` có `SCOPE_docs.read`; `writer-demo` có `SCOPE_docs.write`; token khác bị `BadOpaqueTokenException`. SecurityWebFilterChain được chạy thật, nhưng test **không gọi một network introspection endpoint**, nên không thể coi là e2e của AS.

`src/test/java/demo/opaque/OpaqueHttpTests.java`:

```java
package demo.opaque;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.List;
import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.context.annotation.Primary;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.core.DefaultOAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.introspection.BadOpaqueTokenException;
import org.springframework.security.oauth2.server.resource.introspection.ReactiveOpaqueTokenIntrospector;
import org.springframework.test.web.reactive.server.WebTestClient;

import reactor.core.publisher.Mono;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@Import(OpaqueHttpTests.FakeAs.class)
class OpaqueHttpTests {

    @Autowired
    WebTestClient client;

    @TestConfiguration
    static class FakeAs {

        @Bean
        @Primary
        ReactiveOpaqueTokenIntrospector testingIntrospector() {
            ReactiveOpaqueTokenIntrospector fake = token -> {
                if (!token.equals("reader-demo")
                        && !token.equals("writer-demo")) {
                    return Mono.error(
                        new BadOpaqueTokenException("inactive"));
                }

                String scope = token.equals("reader-demo")
                    ? "docs.read" : "docs.write";

                OAuth2AuthenticatedPrincipal principal =
                    new DefaultOAuth2AuthenticatedPrincipal(
                        "alice",
                        Map.of("sub", "alice",
                            "scope", scope,
                            "exp", Instant.now().plusSeconds(60)),
                        List.of(new SimpleGrantedAuthority(
                            "SCOPE_" + scope)));
                return Mono.just(principal);
            };

            return new RevocationBoundIntrospector(
                fake, Duration.ofMillis(550),
                Duration.ofSeconds(2), 100,
                Clock.systemUTC());
        }
    }

    @Test
    void publicRouteCanBeCalledAnonymously() {
        client.get().uri("/public")
            .exchange().expectStatus().isOk()
            .expectBody(String.class).isEqualTo("public");
    }

    @Test
    void missingBearerIs401() {
        client.get().uri("/api/document")
            .exchange().expectStatus().isUnauthorized();
    }

    @Test
    void activeReaderCanRead() {
        client.get().uri("/api/document")
            .headers(h -> h.setBearerAuth("reader-demo"))
            .exchange().expectStatus().isOk()
            .expectBody(String.class).isEqualTo(
                "document-visible");
    }

    @Test
    void readScopeCannotWrite() {
        client.post().uri("/api/document")
            .headers(h -> h.setBearerAuth("reader-demo"))
            .exchange().expectStatus().isForbidden();
    }

    @Test
    void writerCanPostWithoutCsrfBecauseOnlyBearerHeaderIsAccepted() {
        client.post().uri("/api/document")
            .headers(h -> h.setBearerAuth("writer-demo"))
            .exchange().expectStatus().isOk()
            .expectBody(String.class).isEqualTo(
                "document-updated");
    }

    @Test
    void writeScopeCannotRead() {
        client.get().uri("/api/document")
            .headers(h -> h.setBearerAuth("writer-demo"))
            .exchange().expectStatus().isForbidden();
    }

    @Test
    void inactiveTokenReturns401() {
        client.get().uri("/api/document")
            .headers(h -> h.setBearerAuth("inactive-demo"))
            .exchange().expectStatus().isUnauthorized();
    }

    @Test
    void cookieAloneCannotAuthenticateBearerApi() {
        client.get().uri("/api/document")
            .cookie("access_token", "reader-demo")
            .exchange().expectStatus().isUnauthorized();
    }

    @Test
    void basicAuthCannotReplaceBearer() {
        client.get().uri("/api/document")
            .headers(h -> h.setBasicAuth("alice", "password"))
            .exchange().expectStatus().isUnauthorized();
    }

    @Test
    void whoamiUsesIntrospectedPrincipal() {
        client.get().uri("/api/whoami")
            .headers(h -> h.setBearerAuth("reader-demo"))
            .exchange().expectStatus().isOk()
            .expectBody(String.class).isEqualTo("alice");
    }
}
```

Chạy từ root của project:

```bash
mvn test
```

**Mục tiêu: 22 tests** (12 unit wrapper + 10 HTTP), khi tạo đúng files và dùng JDK/dependencies phù hợp. Các bài test là **mã mẫu để người học chạy**; bài này **không khẳng định đã chạy Maven tại repository của bạn**. Test HTTP dùng fake AS trả principal trong memory; test wrapper kiểm timeout/cache. Để bảo đảm contract RFC 7662, mạng/TLS, client credentials và AS thật, cần test staging/sandbox riêng.

### 8.1. Những giả định mà bộ test chưa chứng minh

- AS thật có trả `active=false` cho token revoked ở mọi node trong SLA không?
- WebClient có gửi form `token=...` và HTTP Basic client credentials tới URI đúng không?
- TCP connect/pool acquire/TLS/response timeout có hoạt động chính xác qua proxy không?
- IdP 429/500/malformed JSON hoặc revoked giữa các requests có bị fail-closed không?
- Cache behavior có đúng khi 10.000 callers cùng token gọi đồng thời không?
- Revocation event có tới tất cả pod và không có ordering race không?
- Sai issuer/audience/tenant có bị loại trong contract introspection không?
- Timeout exception được security handler map thành HTTP 503/5xx/401 ra sao?

Những điểm trên nên có các bài integration qua AS sandbox/mock HTTP server thực, browser/ingress environment và load tests. **Không** sửa fail-closed thành fail-open chỉ để endpoint trả 200 trong lúc AS lỗi.

## 9. Chạy bằng curl, so sánh cache và độ trễ

Bật app:

```bash
java -version
mvn -version
mvn spring-boot:run
```

Thử public và Bearer thiếu:

```bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/api/document
curl -i -H 'Authorization: Bearer invalid-token' \
  http://localhost:8080/api/document
```

Kỳ vọng public 200; protected không Bearer 401. Request có Bearer `invalid-token` với endpoint demo `idp.example.invalid` chưa cấu hình thật sẽ bị dependency error, **không** có quyền vào handler. Không tuyên bố response phải luôn là một status 401 hay 503 khi AS chưa thể kết nối, vì exception translation cần kiểm thực tế.

Khi có AS sandbox được tổ chức phê duyệt, thay `demo.introspection.uri`, `client-id` và `client-secret`; lấy **access token opaque thật** cho test. Gọi:

```bash
# Chỉ để mô tả: thay placeholder bằng token hợp lệ từ AS sandbox.
curl -i -H 'Authorization: Bearer <VALID_OPAQUE_ACCESS_TOKEN>' \
  http://localhost:8080/api/document
```

`<VALID_OPAQUE_ACCESS_TOKEN>` là placeholder; không có token issuance endpoint trong project này. Resource Server **không tự phát token**. Để thử happy path offline, dùng `mvn test` với fake AS principal. Trên PowerShell, có thể cần `curl.exe`.

Không ghi Bearer token/client secret vào URL query, access log, debugging screenshots hoặc shell history; với môi trường thật dùng HTTPS và giữ secrets trong secure env/manager.

### 9.1. Đo tải

Giả sử 1.000 requests mỗi giây tới protected API:

- Cache miss toàn bộ → khoảng 1.000 introspection attempts/s, chưa tính retries.
- 70% cache hit → khoảng 300 misses/s.
- Nhưng số thực phụ thuộc token uniqueness, TTL, evictions, đồng thời cold misses, cluster distribution và retry.

**Đây chỉ là ví dụ số học.** Tăng hit rate bằng cách kéo dài TTL từ 2 giây lên 30 phút là vi phạm revocation SLA nếu business không chấp thuận. Khi IdP outage, retry mọi request có thể tạo retry storm và làm AS hồi phục chậm hơn.

### 9.2. Metrics cần có

| Metric | Câu hỏi |
| --- | --- |
| `introspection.duration` p50/p95/p99 | IdP thêm bao nhiêu latency cho cache miss? |
| `introspection.timeout.count` | Deadline có thường xuyên bị vượt? |
| `introspection.outcome` by category | Active/inactive, invalid client, 429, 5xx, TLS? |
| `introspection.inflight` | Tắc nghẽn/bulkhead? |
| `cache.hit/miss/eviction` | Cache giúp giảm tải bao nhiêu? |
| `cache.ttl.configured` | Có bị tăng TTL ngoài review không? |
| `revocation.observed.latency` | Token revoked mất bao lâu đến lúc API từ chối? |
| `event.delivery.lag/dropped` | Cơ chế invalidation có đáng tin? |
| `auth.401` và `authz.403` | Thiếu credential hay thiếu quyền? |
| `api.latency.protected/public` p99 | Introspection kéo dài API bao nhiêu? |
| IdP QPS/429/5xx | AS capacity chịu được peak/miss storm? |

Không dùng raw tokens/user names/session IDs làm metric label (cardinality và privacy). Không log nguyên body introspection hoặc `Authorization` header. Nếu cần trace correlation, dùng ID riêng và redaction; một token HMAC fingerprint cũng cần quản trị retention/quyền truy cập.

## 10. Chính sách theo tình huống

### 10.1. Quản trị cấp quyền nhạy cảm

`POST /api/admin/change-policy`: chọn cache TTL 0, kiểm quyền admin ở authorization layer và có thể kiểm policy version hoặc trạng thái tại điểm commit. Khi AS unavailable, từ chối thao tác; không cho last-known-good. Nếu AS không thể trả revoked state dưới 1 giây, cần thay đổi kiến trúc/thỏa thuận SLA, không giải quyết bằng TTL âm.

### 10.2. API chỉ đọc dữ liệu ít nhạy cảm

Nếu sản phẩm chấp nhận revocation window 30 giây và AS + inflight margin ≤5 giây, positive cache TTL có thể tối đa 25 giây theo mô hình; chọn một giá trị thấp hơn để dự phòng. Nếu `exp` còn 3 giây thì entry chỉ dùng 3 giây. Theo dõi `revocation.observed.latency`, không chỉ cache hit ratio.

### 10.3. Cụm nhiều pod

Mỗi pod có local Caffeine cache; revocation event tới một pod không tác động các pod khác. Dùng event fan-out có authentication, sequence/version và reconciliation, hoặc shared cache/denylist đã review. Nếu không thể bảo đảm delivery, TTL vẫn là safety net. **Không phát raw Bearer token** qua bus chỉ để invalidate.

### 10.4. IdP outage

Khi AS mất kết nối 2 phút và positive cache TTL 2 giây, entry active cũ có thể tiếp tục được dùng tới khi hết TTL. Sau đó request cần xác minh phải **không thành công**; không tự kéo dài cache 2 phút. UI có thể nhận lỗi dependency theo exception handler; đội SRE nên cảnh báo và khôi phục IdP/đường mạng thay vì mở quyền.

### 10.5. Token exp còn ít hơn TTL

`maxAge=10s` nhưng token còn 1s đến exp: TTL thực ≤1s. Nếu token đã hết hạn tại lúc introspection response tới Resource Server, wrapper phải reject, không cache.

## 11. Lỗi thiết kế thường gặp

| Anti-pattern | Vì sao nguy hiểm | Thay bằng |
| --- | --- | --- |
| Cache `active=true` đến `exp` cả giờ | Revoke không có hiệu lực sớm | TTL theo SLA, cap exp |
| Không hỏi security về revoke SLA | TTL chọn tùy tiện | SLO/SLI rõ, đo AS propagation |
| `Mono.cache()` giữ error vô hạn | Caching failure, lộ/memory | Positive-only bounded cache |
| Timeout thì lấy lastKnownGood sau TTL | **Fail-open** | Fail-closed, no stale-on-error |
| Circuit breaker mở thì tạo principal giả | Bỏ qua authentication | Dependency failure, deny |
| Cache raw bearer string làm key | Heap/log secret exposure | HMAC digest, retention hạn chế |
| Chỉ dùng response timeout | Pool/DNS/TLS kéo dài | Total Mono deadline và stage limits |
| Retry 3 lần mọi lỗi | p99 phình, IdP quá tải | Retry hạn chế, chọn lỗi có thể hồi phục |
| Không kiểm `exp` khi cache hit | Token hết hạn vẫn active | Entry validUntil |
| Một cache dùng chung issuer/tenant | Sai ranh giới trust | Namespace/partition policy |
| Event revoke chỉ đến một pod | Pod còn lại stale | Fan-out, reconciliation, TTL |
| Dùng `block()`/RestTemplate trên event loop | Reactor starvation | WebClient và reactive APIs |
| Nhầm `active=false` HTTP 200 là success API | Invalid token được cho vào | Spring introspector xác minh active |
| Test bằng mock principal rồi gọi là network test | Không kiểm TLS/latency/AS | Unit + HTTP + sandbox integration |
| Thấy 403 rồi bỏ scope check | Bypass authorization | Điều tra `SCOPE_` và resource ownership |
| Dùng opaque auth nhưng chấp nhận cookie fallback | CSRF threat không còn bearer-only | Tách chain, giữ CSRF cho browser |
| Client secret ở WebClient dùng chung | SSRF/token leakage | WebClient riêng tới trusted AS |
| Tắt cache rồi cam kết instant revoke | Bỏ qua AS propagation/inflight | Recheck commit + version/denylist theo policy |

## 12. Checklist trước production

1. Xác định revocation SLA cho từng loại endpoint và token.
2. Đo AS propagation trên các node/region; không cam kết SLA nếu không có bound.
3. Chọn `T_cache` theo SLA trừ AS/inflight/margin, không lấy bằng token lifespan.
4. Cap TTL bằng `exp`; không cache positive nếu exp thiếu hoặc không hiểu rõ.
5. Cache chỉ kết quả `active=true` đã được introspector chứng thực; không cache timeout, 5xx, inactive thành principal.
6. Fail-closed khi AS inaccessible; không trả stale-after-TTL hoặc authenticated mặc định.
7. Tạo WebClient riêng cho introspection, HTTPS, trusted URI, client auth/secret store.
8. Có TCP connect, response, pool, TLS và total timeout; chọn từ API latency budget.
9. Retry có hạn, chỉ với lỗi phù hợp và trong deadline, tránh thundering herd.
10. Bounded cache có max entries, positive-only, HMAC key/retention bảo mật và invalidation.
11. Với nhiều pods/issuer/tenant, thiết kế cache namespace và event fan-out/reconciliation.
12. Không tự ý cache kết quả `active` trên API admin/transaction không chấp nhận stale.
13. Luôn giữ authentication/authorization: 401 cho invalid token, 403 cho thiếu scope, owner/tenant check ở service.
14. Chỉ miễn CSRF cho API thực sự Bearer-header-only; session/cookie routes vẫn cần CSRF.
15. Unit test fake clock cho TTL/expiry/revoke, StepVerifier cho timeout/errors, WebTestClient cho 401/403/200.
16. Staging test RFC 7662 với IdP sandbox, invalid client, 429/5xx, timeout, mTLS/TLS, multi-region and load.
17. Có dashboard latency, cache hit/miss, invalidation lag và revoked observation latency, không log secrets.
18. Ghi rõ người có quyền điều chỉnh TTL và quy trình emergency disable cache khi sự cố quyền truy cập.

## 13. Câu hỏi tự đánh giá

**Câu 1.** Opaque token Resource Server có bắt buộc nhận một token “không phải JWT” không?  
**Không.** Cơ chế opaque ở Spring mô tả **introspection**; có thể introspect JWT để kiểm revoked state nếu policy yêu cầu.

**Câu 2.** Vì sao `exp` sau 30 phút không cho phép positive-cache 30 phút?  
Vì token có thể bị thu hồi **trước exp**. Cache dài sẽ cho phép token revoked hoạt động tới khi hết cache.

**Câu 3.** SLA revoked 10s, AS 3s, inflight/safety 2s; TTL tối đa?  
Theo ngân sách minh họa, **5 giây**, cần margin thực tế và đo AS.

**Câu 4.** Cache TTL 10s nhưng token còn 2s tới exp, entry TTL?  
**Không quá 2 giây**; cap bởi exp.

**Câu 5.** Positive-cache TTL=0 bảo đảm mọi request sau revoke ngay lập tức trả 401 không?  
**Không tuyệt đối.** Vẫn có AS eventual consistency và request đang xử lý.

**Câu 6.** `{"active":false}` từ AS có bắt buộc trả HTTP 401 không?  
Không. RFC 7662 có thể trả HTTP 200 với `active=false`; API Resource Server coi Bearer invalid.

**Câu 7.** Khi introspection timeout, có được gửi cached principal đã quá TTL để tránh 5xx không?  
Không trong **fail-closed** policy; không có bằng chứng token còn active.

**Câu 8.** `Mono.cache()` không bounded có hợp lý cho token validation không?  
Không. Nó có thể giữ success/error/raw token lâu hoặc tốn bộ nhớ; dùng positive-only bounded cache với expiry/invalidation.

**Câu 9.** Vì sao cần deadline tổng khi đã có `HttpClient.responseTimeout`?  
Vì pool/DNS/connect/TLS và các bước trước response có thể chiếm thời gian. Deadline tổng chặn publisher kéo dài.

**Câu 10.** Cached token revoke ngay sau AS check còn được phép gọi API không?  
Có thể, trong **stale window đã chấp nhận** khi TTL>0. Nếu không được, tắt cache và thiết kế recheck/quyền tức thời hơn.

**Câu 11.** Local `invalidate(token)` có xóa entry ở mọi pod không?  
Không. Cache mỗi process riêng; cần event propagation/shared strategy và reconciliation.

**Câu 12.** Hai test classes mẫu kiểm điều gì?  
Unit test kiểm wrapper timeout/TTL/revocation; HTTP test kiểm Spring Security Bearer routing/authorization với fake IdP, **không** thay AS sandbox.

**Câu 13.** Một token active nhưng thiếu `SCOPE_docs.write` khi POST nhận gì?  
**403 Forbidden**, vì authentication thành công nhưng authorization không đủ.

**Câu 14.** AS trả 5xx có phải token inactive không?  
Không biết token active hay không. Đó là dependency failure, không được biến thành authenticated principal.

### Tài liệu chính thức

- Spring Security 6.5 – Reactive Resource Server Opaque Tokens: https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/resource-server/opaque-token.html
- Spring Security 6.5 – OAuth2 WebFlux Overview: https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/index.html
- Spring Security 6.5 API – `ReactiveOpaqueTokenIntrospector`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/server/resource/introspection/ReactiveOpaqueTokenIntrospector.html
- Spring Security 6.5 API – `SpringReactiveOpaqueTokenIntrospector`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/server/resource/introspection/SpringReactiveOpaqueTokenIntrospector.html
- RFC 7662 – Token Introspection: https://www.rfc-editor.org/rfc/rfc7662
- RFC 7009 – Token Revocation: https://www.rfc-editor.org/rfc/rfc7009
- RFC 6750 – Bearer Token Usage: https://www.rfc-editor.org/rfc/rfc6750
- Reactor Netty – HttpClient timeouts: https://projectreactor.io/docs/netty/release/reference/http-client.html
- Project Reactor – Mono.timeout: https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html
- Caffeine – Expiration/Eviction: https://github.com/ben-manes/caffeine/wiki/Eviction

**Tóm tắt:** Resource Server Opaque phụ thuộc introspection để biết `active`. Timeout phải nằm trong latency budget, outage phải **fail-closed**, còn cache success phải **positive-only, bounded và giới hạn bởi cả `exp` lẫn revocation SLA**. Nếu không chấp nhận token revoked còn được dùng trong một cửa sổ stale thì không bật positive cache; vẫn phải giải quyết consistency AS và request in-flight. Dùng WebFlux `ReactiveOpaqueTokenIntrospector` với WebClient timeout, kiểm bằng fake-clock tests và AS sandbox trước production.