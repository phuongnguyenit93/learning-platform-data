# Phối hợp giới hạn lưu lượng, timeout và bảo vệ dịch vụ danh tính

**Module:** Spring Security – reactive / Spring WebFlux  
**Phần:** Gateway và nhiều tenant  
**Mục tiêu:** Bảo vệ Identity Provider (IdP)/Authorization Server khi gateway chịu traffic lớn, nhưng vẫn tách biệt tenant, giới hạn đúng người, tôn trọng revocation và không bỏ qua authentication khi hệ thống danh tính tạm lỗi.

## 1. Kết luận và mô hình trách nhiệm

**Rate limiting, timeout, bulkhead và circuit breaker là bốn cơ chế bổ sung cho nhau, không thể thay thế nhau.** Một gateway nhiều tenant nên có:

1. **Pre-auth throttling:** giới hạn request thô trước khi token được giải mã hoặc gửi introspection tới IdP. Chỉ sử dụng tín hiệu không đòi hỏi xác thực tenant, như source connection/IP do ingress đáng tin ghi nhận. Không tin HTTP header tenant từ Internet.
2. **Authentication:** xác minh Bearer bằng `ReactiveJwtDecoder` và JWKS đã được trust hoặc bằng `ReactiveOpaqueTokenIntrospector` (ví dụ `SpringReactiveOpaqueTokenIntrospector`) qua HTTPS introspection. Nếu không xác minh được, **không cấp principal**.
3. **Post-auth quotas:** giới hạn tenant/user/route bằng claim **đã xác minh** từ `JwtAuthenticationToken` hoặc principal introspection. Khóa quota phải được namespace theo issuer/tenant và, nếu cần, subject/client.
4. **Outbound IdP protection:** giới hạn số calls đang bay, rate IdP chung, connect/response/total deadlines, retry có chọn lọc, circuit breaker fail-closed.
5. **Downstream protection:** timeout và circuit riêng cho business upstream; authorization tại backend vẫn phải kiểm owner/tenant của resource.

```text
Internet -> CDN/WAF -> Trusted Ingress
                           |
                           v
                 +-------------------------+
                 | Spring Cloud Gateway    |
                 | (1) coarse pre-auth cap |
                 | (2) JWT/introspection   |------> IdP/AS
                 | (3) trusted tenant      |        /introspect
                 | (4) tenant/user quotas  |        JWKS metadata
                 | (5) routing/bulkhead    |
                 +------------+------------+
                              |
                        business calls
                              v
                     Tenant-aware services
                     own resource ACL checks
```

**Điểm kiến trúc hay bị bỏ qua:** nếu đặt limiter **sau** introspection thì 10.000 request dùng các token rác có thể đã gọi IdP 10.000 lần trước khi limiter biết tenant là ai. Ngược lại, nếu chỉ limit IP thì 100 user công ty cùng NAT có thể bị gom sai thành một “user”, trong khi một tenant có nhiều nguồn IP vẫn ăn hết ngân sách IdP. Cần hai lớp trước và sau authentication.

## 2. Trust boundaries và lựa chọn khóa rate limit

| Tầng | Nguồn tín hiệu | Có thể tin ngay không? | Dùng để làm gì |
| --- | --- | --- | --- |
| Reverse proxy được quản lý | Remote socket address / verified client IP | Có điều kiện: phải cấu hình trusted ingress | Coarse abuse detection trước auth |
| `X-Forwarded-For` tự gửi từ Internet | Header bất kỳ | **Không** | Không làm IP identity nếu chưa được proxy strip/replace |
| `X-Tenant-Id` / path tenant | Do caller kiểm soát | **Không** | Chỉ so với tenant đã verify, không chọn token decoder/quota trực tiếp |
| JWT payload vừa Base64 decode | Chưa kiểm chữ ký, issuer và audience | **Không** | Không được dùng claim để cấp quyền hoặc chọn URL IdP |
| `JwtAuthenticationToken` từ decoder tin cậy | JWT đã xác minh | Có điều kiện: thêm tenant allowlist/domain policy | Post-auth tenant/user quota |
| `OAuth2AuthenticatedPrincipal` từ introspection | AS đã trả active và claims hợp lệ | Có điều kiện: kiểm AS/tenant contract | Post-auth opaque token quota |
| Header `X-Verified-Tenant` do Gateway ghi | Gateway assertion | Chỉ tin khi backend nhận qua mTLS/private ingress | Routing, metadata phục vụ backend, không thay ACL |
| Redis/bucket state | State giới hạn toàn cụm | Tin theo topology, TLS/auth, fail policy | Global tenant quota |

Cách chọn key sau auth:

```text
preAuthKey  = trustworthy-network-peer-or-ingress-class
tenantKey   = trustedIssuerId + ":" + verifiedTenant
subjectKey  = trustedIssuerId + ":" + verifiedTenant + ":" + verifiedSubject
idpKey      = trustedIssuerId
routeKey    = tenantKey + ":" + routeId
```

**Không** coi subject trần là duy nhất trên mọi issuer; nhiều tenant có thể có cùng `sub=alice`. Với client_credentials, token đại diện **client ứng dụng**, không phải end user: chọn `client_id` hoặc service identity theo hợp đồng token. Trong production key phải chuẩn hóa, length-prefix/escape separators và giới hạn cardinality; không lấy raw access token làm bucket key nếu không có mục đích và bảo vệ dữ liệu.

### 2.1. Forwarded headers và nhiều tenant

Spring Cloud Gateway 2025.0 thay tên starter/prefix cấu hình. Với Gateway Server WebFlux, `spring.cloud.gateway.server.webflux.trusted-proxies` giúp khai báo những proxy nào có headers được tin. **Không dùng regex `.*` cho Internet**. Nếu không xác định được real client IP, dùng peer address và coarse global limit thay vì tin `X-Forwarded-For`. Tenant identity **không** được lấy từ IP hoặc network header; nhiều tenants có thể dùng chung NAT.

### 2.2. Multi-issuer không được là arbitrary metadata discovery

Nếu mỗi tenant có IdP riêng, chọn `ReactiveJwtDecoder`/authentication manager từ một **registry issuer được operator phê duyệt**. Các pattern như `JwtIssuerReactiveAuthenticationManagerResolver` chỉ an toàn khi resolver/manager bị giới hạn ở issuer allowlist, kiểm issuer/audience sau signature verification. Không dùng `iss` của JWT chưa xác minh để tự động HTTP fetch tới một URL tùy ý: attacker có thể biến gateway thành SSRF client và tạo JWKS fetch storm.

## 3. Chọn đúng mô hình bearer authentication

| Cơ chế | Đường IdP được dùng khi nào? | Khả năng revoke sớm | Điểm bảo vệ |
| --- | --- | --- | --- |
| JWT Resource Server offline | Local verify phần lớn requests, JWKS/discovery on cache miss/key rotation | Không biết revoked trước `exp` nếu không có cơ chế khác | Cache public keys, timeout JWKS fetch, issuer/audience checks |
| Opaque introspection | Thường gọi AS trên mỗi request/positive-cache miss | Có thể nhìn thấy `active=false` theo AS | Pre-auth limiter, IdP bulkhead/timeout, cache TTL từ revocation SLA |
| OAuth2 Client outbound token | AS token endpoint khi grant/refresh/rotation | Tùy AS policy | Refresh dedupe, limited retries, secret management |
| OIDC browser login | Browser login/consent và server token exchange | Có OP SSO/local session lifecycle riêng | state/nonce/PKCE, CSRF, login-specific rate controls |

**JWT/JWKS cache ≠ introspection active cache.** JWKS cache giữ **public key** để verify chữ ký, không cho biết trạng thái bị thu hồi. Cache kết quả `active=true` của opaque introspection mới lưu một **security decision**, tạo stale window sau revoke. Nếu SLA revoke rất chặt, positive cache phải rất ngắn hoặc bằng 0 và vẫn cần đo AS propagation/inflight requests.

Trong WebFlux, `SpringReactiveOpaqueTokenIntrospector` là một implementation của `ReactiveOpaqueTokenIntrospector` dùng HTTP introspection. Ví dụ Boot properties:

```properties
spring.security.oauth2.resourceserver.opaquetoken.introspection-uri=https://trusted-idp.example.org/oauth2/introspect
spring.security.oauth2.resourceserver.opaquetoken.client-id=resource-server
spring.security.oauth2.resourceserver.opaquetoken.client-secret=secret-from-manager
```

Không gắn giá trị demo vào production. `active=false` từ introspection có thể là **HTTP 200 với body JSON**, nhưng Resource Server phải từ chối token khi xử lý request API.

### 3.1. Giới hạn pre-auth thực sự bảo vệ IdP thế nào?

Nếu không pre-auth admission, attacker có thể gửi 5.000 Bearer tokens ngẫu nhiên/giây. Với opaque tokens, mọi token có thể dẫn tới network introspection trừ khi tầng auth ngăn trước. Pre-auth cap 200 requests/s trên mỗi trusted source **giảm cơ hội** làm nghẽn IdP, nhưng không đủ với botnet nhiều IP; phải có global edge protection, WAF và per-AS concurrent/QPS limit. Không hứa “chặn toàn bộ DDoS” bằng một Map IP local.

### 3.2. Tenant-wide khác per-user quota

Một key `issuer|tenant|sub` giới hạn **mỗi user trong tenant**; nó **không** áp tổng quota của tenant nếu tenant có 100.000 users. Production cần **đồng thời**:

- Global edge/IdP safety limit.
- Tenant-wide bucket `issuer|tenant`.
- Per-user/client bucket `issuer|tenant|sub`.
- Per-route cost/priority (đọc metadata khác refresh/password reset).

Các policies là nhiều điều kiện AND độc lập; không thay tenant-wide bằng việc ghép tenant vào key subject.

## 4. Rate limiter, bulkhead và timeout: từng cơ chế cắt một loại rủi ro

| Công cụ | Giới hạn | Khi kích hoạt | Không giải quyết |
| --- | --- | --- | --- |
| Token bucket/RedisRateLimiter | Requests hoặc tokens mỗi giây và burst | 429 khi cạn token | Số calls đang bay nếu latency tăng |
| Fixed-window counter | Số requests trong cửa sổ cố định | 429 trên key | Burst ở cửa sổ, multi-pod global quota |
| Semaphore/bulkhead | Concurrent outbound requests | Fail-fast khi không còn slot | Số requests/s khi AS trả rất nhanh |
| Connect timeout | TCP connect/TLS liên quan | Fail khi không kết nối kịp | Total request deadline |
| Response timeout | Thời gian chờ server response | Fail khi response chậm | Pool acquire/DNS/queue |
| Reactor `Mono.timeout` | Toàn publisher từ subscription | Error/cancel sau deadline | Chính sách retry/error mapping |
| Circuit breaker | Fail-fast khi dependency nhiều lần lỗi | Open/half-open | JWT validation, quota fairness |
| Retry có điều kiện | Lỗi transient được xác định | Gọi lại trong ngân sách | 401 invalid token, idempotency, storm |

### 4.1. Little’s Law cho IdP

Số calls đồng thời trung bình xấp xỉ `λ × W`. Giả sử 80 introspection calls/s và latency trung bình 250ms, inflight trung bình khoảng 20. Nếu AS chậm thành 2.000ms, inflight có thể thành **160** mà QPS không đổi. Vì vậy limiter QPS không thể thay bulkhead; timeout giúp giải phóng slots, nhưng phải có upper bound toàn request, cancellation và monitoring.

### 4.2. Total deadline trước khi chọn retries

Ví dụ API có p99 budget 1.500ms:

```text
Ingress + preauth / routing         50ms
Authentication / introspection     350ms
Business upstream                  800ms
Response serialization             100ms
Reserve                            200ms
TOTAL                             1500ms
```

Nếu IdP tốn 350ms đã hết ngân sách xác thực. Không thử 3 lần mỗi lần 350ms rồi vẫn mong request đạt SLO. Cần connect/response/total timeout riêng cho IdP và cho backend. `spring.cloud.gateway.server.webflux.httpclient.response-timeout` điều khiển proxy outbound của Gateway; **không tự áp** cho `WebClient` được custom để gọi introspection/JWKS.

### 4.3. Rate limit phải fail như thế nào?

**429** có nghĩa request bị quota/policy từ chối, có thể thêm `Retry-After` khi có giá trị hợp lệ. **401** là thiếu/invalid Bearer token. **403** là authenticated nhưng không có quyền/tenant được cấp. **503** thường được dùng khi dependency hoặc breaker không khả dụng. **504** thường chỉ timeout ở gateway/upstream; status thực phụ thuộc Spring exception handler và Gateway configuration. **Không tự tuyên bố mỗi lỗi IdP luôn trả 503**, nhưng tất cả protected requests chưa được xác minh **không được trả 2xx thành công**.

Nếu Redis quota service down, không tự động `allow=true` cho mọi tenant. Chọn fallback đã được review: coarse local limit + shed-load có cap, hoặc fail-closed theo tier. Không coi Redis timeout là chứng cứ token invalid.

## 5. IdP protection khi cache/refresh/retry

### 5.1. JWT key rotation, key cache và timeout

Với `issuer-uri`, Spring Security có cơ chế discovery/JWKS để validate JWT, có thể cache JWK set. Nếu key `kid` mới xuất hiện trong lúc AS outage, gateway không có cơ sở verify JWT lạ. Không chấp nhận token bằng cách tắt signature. Nếu `issuer-uri` và `jwk-set-uri` được cung cấp phù hợp, Resource Server có thể giảm phụ thuộc IdP lúc startup, nhưng vẫn phải validate `iss`/`aud`/`exp` và quản lý rotation.

### 5.2. Opaque token positive cache và SLA revoke

Khi introspection trả active:

```text
cacheValidUntil = min(
    introspectionCompletedAt + approvedPositiveTtl,
    tokenExp
)
```

Một cache TTL 60s tạo cửa sổ token vừa revoke vẫn có thể được chấp nhận tới gần 60s sau lần kiểm trước, cộng AS propagation/inflight. Nếu SLA revoke là 5s, không được tùy ý cache 60s chỉ để cải thiện hit ratio. Khi AS down không dùng expired cache result làm authenticated principal. Không cache network errors, `active=false` dưới dạng principal hay `Mono.cache()` vô hạn. Quản lý tenant namespace, max entries, time bounds và invalidation ở mọi pod.

### 5.3. Retry và circuit breaker không được fail-open

Không retry signature invalid, token expired, `active=false`, invalid client secret; đó không phải lỗi transient. Với 429/502/503/network reset có thể có **tối đa 1 retry** theo policy/backoff jitter và within deadline; phải tính tác động lên QPS AS. Circuit open => fail-fast/dependency error, **không phải** `return Mono.just(anonymousOrAdminPrincipal)`. Với POST thanh toán/business write, không retry nếu thiếu idempotency key và transaction policy.

### 5.4. IdP chính là shared resource giữa tenants

Dù tenant A và tenant B có quotas riêng, nếu cùng một IdP, cả hai dùng chung outbound connection pool và token/introspection API. Cần global cap và per-tenant quotas. Nếu tenants có IdP độc lập, không dùng một circuit chung khiến sự cố IdP A đóng mọi requests tenant B; chọn per-issuer breaker/bulkhead cùng một global safety ceiling. Quota theo tenant không được làm xói mòn giới hạn AS mà operator đã cam kết.

## 6. Java 17 độc lập: tính concurrent slots và budget

Lưu `IdentityCapacityDemo.java`:

```java
public class IdentityCapacityDemo {
    static int estimatedInflight(int qps, int latencyMs) {
        return (int) Math.ceil(qps * latencyMs / 1000.0);
    }

    static int remainingBudget(
            int deadlineMs, int authMs,
            int upstreamMs, int reserveMs) {
        return Math.max(0,
            deadlineMs - authMs - upstreamMs - reserveMs);
    }

    public static void main(String[] args) {
        System.out.println("idpInflight=" +
            estimatedInflight(80, 250));
        System.out.println("idpSlowInflight=" +
            estimatedInflight(80, 2000));
        System.out.println("remainingMs=" +
            remainingBudget(1500, 350, 800, 200));
    }
}
```

Chạy bằng JDK 17+:

```bash
javac IdentityCapacityDemo.java
java IdentityCapacityDemo
```

**Stdout chính xác:**

```text
idpInflight=20
idpSlowInflight=160
remainingMs=150
```

Đây là phép tính sizing, **không phải benchmark** và không đảm bảo p99/concurrency peak. Phải đo distributions, burstiness, retry amplification và error budget trước khi chốt limits.

## 7. Project Spring Boot 3.5.7 + Spring Cloud Gateway 4.3: kiến trúc demo

Ta xây project local với 3 cơ chế cụ thể:

1. `WebFilter` có thứ tự cao thực hiện **pre-auth coarse IP limiter**, không parse JWT tenant.
2. Spring Security WebFlux Resource Server verify JWT HS256 **test-only**, kiểm chữ ký, issuer, audience, expiry rồi tạo `JwtAuthenticationToken`. Không có IdP network ở demo này.
3. `GatewayFilter` dùng tenant claim **sau xác thực**, giới hạn per issuer+tenant+subject, scrub untrusted headers và chuyển đến một internal `forward:` controller. Tất cả test happy path chạy mà không cần backend HTTP ngoài.

Thêm `IdentityCallGuard` với bulkhead `Semaphore.tryAcquire()` + `Mono.timeout` và unit tests. Class này **được trình bày để tích hợp khi thực tế có outbound IdP/introspection client**, không được giả vờ nó đang chặn network JWKS của JWT demo.

### 7.1. Cấu trúc

```text
tenant-gateway-defense/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/gateway/
    │   │   ├── GatewayApplication.java
    │   │   ├── FixedWindowBudget.java
    │   │   ├── IdentityCallGuard.java
    │   │   ├── SecurityConfig.java
    │   │   ├── GatewayRoutes.java
    │   │   └── EchoController.java
    │   └── resources/application.properties
    └── test/java/demo/gateway/
        ├── FixedWindowBudgetTests.java
        ├── IdentityCallGuardTests.java
        └── GatewayHttpTests.java
```

Không thêm Servlet `spring-boot-starter-web`. Release train **Spring Cloud 2025.0** dùng starter mới `spring-cloud-starter-gateway-server-webflux` và prefix `spring.cloud.gateway.server.webflux`. Phiên bản đã chọn là mốc học tập; sản phẩm thật dùng bản còn hỗ trợ và bản vá bảo mật.

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
    <artifactId>tenant-gateway-defense</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
        <spring-cloud.version>2025.0.0</spring-cloud.version>
    </properties>
    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>org.springframework.cloud</groupId>
                <artifactId>spring-cloud-dependencies</artifactId>
                <version>${spring-cloud.version}</version>
                <type>pom</type>
                <scope>import</scope>
            </dependency>
        </dependencies>
    </dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-starter-gateway-server-webflux</artifactId>
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
spring.application.name=tenant-gateway-defense
server.port=8080

# JWT decoder/key được tạo trong Java CHỈ cho demo.
# Không cấu hình issuer-uri hay JWKS endpoint giả trong project này.
```

`src/main/java/demo/gateway/GatewayApplication.java`:

```java
package demo.gateway;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class GatewayApplication {
    public static void main(String[] args) {
        SpringApplication.run(GatewayApplication.class, args);
    }
}
```

### 7.2. FixedWindowBudget.java: limiter atomic per key trong một process

`src/main/java/demo/gateway/FixedWindowBudget.java`:

```java
package demo.gateway;

import java.time.Clock;
import java.time.Duration;
import java.util.Objects;
import java.util.concurrent.atomic.AtomicBoolean;
import com.github.benmanes.caffeine.cache.Cache;
import com.github.benmanes.caffeine.cache.Caffeine;

public final class FixedWindowBudget {
    private record Window(long resetMs, int count) {}

    private final Clock clock;
    private final Cache<String, Window> entries;

    public FixedWindowBudget(Clock clock, long maxKeys) {
        this.clock = Objects.requireNonNull(clock);
        if (maxKeys < 1) {
            throw new IllegalArgumentException("maxKeys");
        }
        entries = Caffeine.newBuilder()
            .maximumSize(maxKeys)
            .expireAfterWrite(Duration.ofMinutes(2))
            .build();
    }

    public boolean allow(String key, int limit, Duration window) {
        Objects.requireNonNull(key);
        Objects.requireNonNull(window);
        if (limit < 1 || window.toMillis() < 1) {
            throw new IllegalArgumentException("Invalid quota");
        }

        long now = clock.millis();
        long duration = window.toMillis();
        AtomicBoolean granted = new AtomicBoolean(false);

        entries.asMap().compute(key, (k, previous) -> {
            if (previous == null || now >= previous.resetMs()) {
                granted.set(true);
                return new Window(now + duration, 1);
            }
            if (previous.count() < limit) {
                granted.set(true);
                return new Window(
                    previous.resetMs(), previous.count() + 1);
            }
            return previous;
        });
        return granted.get();
    }
}
```

**Hạn chế rõ ràng:** Fixed window có burst ở ranh giới; Caffeine eviction trước thời điểm reset có thể cấp lại quota; state bị reset khi pod restart và **không phân tán**. Đây là mẫu giáo trình đơn giản, không phải giới hạn global/quota billing trong production. Chọn RedisRateLimiter/edge rate limiting khi nhiều replicas.

### 7.3. IdentityCallGuard.java: semaphore + deadline để bảo vệ AS

`src/main/java/demo/gateway/IdentityCallGuard.java`:

```java
package demo.gateway;

import java.time.Duration;
import java.util.Objects;
import java.util.concurrent.Semaphore;
import reactor.core.publisher.Mono;

public final class IdentityCallGuard {
    public static final class Busy extends RuntimeException {
        public Busy() {
            super("Identity calls are saturated");
        }
    }

    private final Semaphore permits;
    private final Duration deadline;

    public IdentityCallGuard(int concurrent, Duration deadline) {
        if (concurrent < 1) {
            throw new IllegalArgumentException("concurrent");
        }
        this.deadline = Objects.requireNonNull(deadline);
        if (deadline.isZero() || deadline.isNegative()) {
            throw new IllegalArgumentException("deadline");
        }
        permits = new Semaphore(concurrent);
    }

    public <T> Mono<T> protect(Mono<T> remoteCall) {
        Objects.requireNonNull(remoteCall);
        return Mono.defer(() -> {
            if (!permits.tryAcquire()) {
                return Mono.error(new Busy());
            }
            return remoteCall.timeout(deadline)
                .doFinally(signal -> permits.release());
        });
    }
}
```

Phần `tryAcquire()` **không block** Netty thread. `doFinally` giải phóng slot khi response/error/timeout/cancel. Nếu muốn dùng cho introspection:

```java
// Fragment, cần một introspector thực và accessToken có sẵn.
IdentityCallGuard guard =
    new IdentityCallGuard(32, Duration.ofMillis(350));

Mono<OAuth2AuthenticatedPrincipal> principal = guard.protect(
    Mono.defer(() -> actualIntrospector.introspect(accessToken)));
```

Cần gắn guard **thực sự vào outbound path tới IdP**. Wrapper `Mono.defer` giúp đưa hoạt động remote vào lúc subscription. Nếu `Busy`/timeout, fail-closed; không tạo principal dự phòng. Với môi trường thực, bổ sung WebClient connect/response timeout, pool limit, metrics, circuit và có thể phân vùng guard theo issuer.

### 7.4. SecurityConfig.java: Bearer-only JWT demo, pre-auth limiter

`src/main/java/demo/gateway/SecurityConfig.java`:

```java
package demo.gateway;

import java.nio.charset.StandardCharsets;
import java.time.Clock;
import java.time.Duration;
import javax.crypto.SecretKey;
import javax.crypto.spec.SecretKeySpec;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jose.jws.MacAlgorithm;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusReactiveJwtDecoder;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.context.NoOpServerSecurityContextRepository;
import org.springframework.web.server.WebFilter;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfig {
    static final String ISSUER = "https://issuer.demo.invalid";
    static final String AUDIENCE = "gateway-api";

    // CHỈ demo/test: production dùng JWK/trust từ IdP.
    static final SecretKey DEMO_KEY = new SecretKeySpec(
        "gateway-demo-32-byte-minimum-not-production-secret"
            .getBytes(StandardCharsets.UTF_8), "HmacSHA256");

    @Bean
    ReactiveJwtDecoder jwtDecoder() {
        NimbusReactiveJwtDecoder decoder =
            NimbusReactiveJwtDecoder.withSecretKey(DEMO_KEY)
                .macAlgorithm(MacAlgorithm.HS256).build();

        OAuth2TokenValidator<Jwt> aud = jwt ->
            jwt.getAudience().contains(AUDIENCE)
                ? OAuth2TokenValidatorResult.success()
                : OAuth2TokenValidatorResult.failure(
                    new OAuth2Error("invalid_token",
                        "Wrong audience", null));

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                JwtValidators.createDefaultWithIssuer(ISSUER), aud));
        return decoder;
    }

    @Bean
    SecurityWebFilterChain security(ServerHttpSecurity http) {
        return http
            .securityContextRepository(
                NoOpServerSecurityContextRepository.getInstance())
            .authorizeExchange(ex -> ex
                .pathMatchers(HttpMethod.GET, "/public").permitAll()
                .pathMatchers("/api/**").authenticated()
                .anyExchange().denyAll())
            .oauth2ResourceServer(oauth -> oauth
                .jwt(Customizer.withDefaults()))
            .formLogin(form -> form.disable())
            .httpBasic(basic -> basic.disable())
            .csrf(csrf -> csrf.disable())
            .build();
    }

    @Bean("ingressBudget")
    FixedWindowBudget ingressBudget() {
        return new FixedWindowBudget(Clock.systemUTC(), 10000);
    }

    @Bean("tenantBudget")
    FixedWindowBudget tenantBudget() {
        return new FixedWindowBudget(Clock.systemUTC(), 10000);
    }

    @Bean
    @Order(Ordered.HIGHEST_PRECEDENCE)
    WebFilter coarsePreAuth(
            @Qualifier("ingressBudget") FixedWindowBudget budget) {
        return (exchange, chain) -> {
            String path = exchange.getRequest().getPath().value();
            if (!path.startsWith("/api/")) {
                return chain.filter(exchange);
            }

            var peer = exchange.getRequest().getRemoteAddress();
            String address = peer == null ? "unknown" :
                peer.getAddress() == null
                    ? peer.getHostString()
                    : peer.getAddress().getHostAddress();

            // 100/minute là mức demo, chưa sizing theo IdP thực.
            if (!budget.allow("ip:" + address, 100,
                    Duration.ofMinutes(1))) {
                exchange.getResponse().setStatusCode(
                    HttpStatus.TOO_MANY_REQUESTS);
                return exchange.getResponse().setComplete();
            }
            return chain.filter(exchange);
        };
    }
}
```

**Thứ tự:** `@Order(Ordered.HIGHEST_PRECEDENCE)` trên `WebFilter` giúp đặt admission sớm trong WebFlux chain. Gateway `GlobalFilter` hay route-specific `GatewayFilter` không đồng nghĩa `WebFilter`; hãy kiểm order bằng integration test có spy vào introspection/JWKS client trước production.

Tắt CSRF **chỉ** vì demo nhận authentication từ Bearer **header-only** và không bật WebSession cookie/form/HTTP Basic fallback. Nếu sản phẩm thêm browser BFF/session cookie, cần tách `SecurityWebFilterChain` và giữ CSRF cho mutations, không copy `csrf.disable()` lên toàn website.

### 7.5. GatewayRoutes.java: quota lấy từ JwtAuthenticationToken

`src/main/java/demo/gateway/GatewayRoutes.java`:

```java
package demo.gateway;

import java.time.Duration;
import java.util.Set;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.cloud.gateway.filter.GatewayFilter;
import org.springframework.cloud.gateway.route.RouteLocator;
import org.springframework.cloud.gateway.route.builder.RouteLocatorBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

@Configuration
public class GatewayRoutes {
    private static final Set<String> ALLOWED =
        Set.of("acme", "globex");

    private static Mono<Void> deny(
            ServerWebExchange exchange, HttpStatus status) {
        exchange.getResponse().setStatusCode(status);
        return exchange.getResponse().setComplete();
    }

    @Bean
    GatewayFilter verifiedTenantQuota(
            @Qualifier("tenantBudget") FixedWindowBudget budget) {
        return (exchange, chain) -> exchange.getPrincipal()
            .ofType(JwtAuthenticationToken.class)
            .switchIfEmpty(Mono.error(
                new ResponseStatusException(
                    HttpStatus.UNAUTHORIZED, "Bearer JWT required")))
            .flatMap(auth -> {
                String tenant = auth.getToken()
                    .getClaimAsString("tenant_id");

                if (tenant == null || !ALLOWED.contains(tenant)) {
                    return deny(exchange, HttpStatus.FORBIDDEN);
                }

                String key = auth.getToken().getIssuer()
                    + "|" + tenant + "|" + auth.getName();

                if (!budget.allow(key, 2,
                        Duration.ofSeconds(30))) {
                    return deny(
                        exchange, HttpStatus.TOO_MANY_REQUESTS);
                }

                var safeRequest = exchange.getRequest().mutate()
                    .headers(h -> {
                        h.remove("X-Tenant-Id");
                        h.remove("X-Verified-Tenant");
                        h.remove(HttpHeaders.AUTHORIZATION);
                        h.set("X-Verified-Tenant", tenant);
                    }).build();

                return chain.filter(
                    exchange.mutate().request(safeRequest).build());
            });
    }

    @Bean
    RouteLocator routes(
            RouteLocatorBuilder builder,
            GatewayFilter verifiedTenantQuota) {
        return builder.routes()
            .route("orders", r -> r.path("/api/orders")
                .filters(f -> f.filter(verifiedTenantQuota))
                .uri("forward:///__demo_upstream"))
            .build();
    }
}
```

Ở đây key là **per-user-within-tenant**, không phải tenant-global. Filter chỉ chạy **sau** Bearer authentication của Spring Security và chỉ nhận `JwtAuthenticationToken`. Từ chối tenant unknown/missing, không dùng header user-supplied làm fallback. Gateway xóa `X-Tenant-Id`, `X-Verified-Tenant`, raw `Authorization` rồi thêm tenant verified cho internal fixture. Trong hệ thật nếu backend cần Bearer phải có chính sách token relay/exchange đúng `aud`; không xóa một cách máy móc, cũng không gửi token ra mọi upstream.

`forward:///__demo_upstream` là tuyến **nội bộ cùng process**, không phải HTTPS/mTLS proxy thật. Backend ngoài process phải không thể bị gọi trực tiếp với `X-Verified-Tenant=admin`; dùng mTLS/service identity và network isolation.

### 7.6. EchoController.java: quan sát spoofed header

`src/main/java/demo/gateway/EchoController.java`:

```java
package demo.gateway;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class EchoController {

    @GetMapping(value = "/public",
                produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> publicPage() {
        return Mono.just("public");
    }

    @GetMapping(value = "/__demo_upstream",
                produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> echo(
        @RequestHeader(value = "X-Verified-Tenant",
            required = false) String tenant,
        @RequestHeader(value = "X-Tenant-Id",
            required = false) String untrusted,
        @RequestHeader(value = "Authorization",
            required = false) String bearer) {
        return Mono.just("tenant=" + tenant
            + ";untrustedForwarded=" + (untrusted != null)
            + ";bearerForwarded=" + (bearer != null));
    }
}
```

Expected khi caller gửi valid JWT `tenant_id=acme` nhưng header `X-Tenant-Id=globex`:

```text
tenant=acme;untrustedForwarded=false;bearerForwarded=false
```

Direct `GET /__demo_upstream` bị `anyExchange().denyAll()` ngăn, nhưng trong production không được coi điều đó thay network policy.

## 8. Test Java 17 cho limiter và IdP concurrency

### 8.1. FixedWindowBudgetTests.java

`src/test/java/demo/gateway/FixedWindowBudgetTests.java`:

```java
package demo.gateway;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.util.concurrent.atomic.AtomicReference;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class FixedWindowBudgetTests {
    static class MutableClock extends Clock {
        AtomicReference<Instant> now = new AtomicReference<>(
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
            now.updateAndGet(v -> v.plusSeconds(seconds));
        }
    }

    @Test
    void twoAllowedThirdDenied() {
        var clock = new MutableClock();
        var limiter = new FixedWindowBudget(clock, 100);
        assertTrue(limiter.allow(
            "acme|alice", 2, Duration.ofSeconds(30)));
        assertTrue(limiter.allow(
            "acme|alice", 2, Duration.ofSeconds(30)));
        assertFalse(limiter.allow(
            "acme|alice", 2, Duration.ofSeconds(30)));
    }

    @Test
    void nextWindowResetsCounter() {
        var clock = new MutableClock();
        var limiter = new FixedWindowBudget(clock, 100);
        assertTrue(limiter.allow("alice", 1,
            Duration.ofSeconds(10)));
        assertFalse(limiter.allow("alice", 1,
            Duration.ofSeconds(10)));
        clock.advance(10);
        assertTrue(limiter.allow("alice", 1,
            Duration.ofSeconds(10)));
    }

    @Test
    void differentTenantKeysAreIndependent() {
        var limiter = new FixedWindowBudget(
            Clock.systemUTC(), 100);
        assertTrue(limiter.allow("acme|alice", 1,
            Duration.ofSeconds(30)));
        assertTrue(limiter.allow("globex|alice", 1,
            Duration.ofSeconds(30)));
        assertFalse(limiter.allow("acme|alice", 1,
            Duration.ofSeconds(30)));
    }

    @Test
    void invalidQuotaAndCapacityRejectConfiguration() {
        assertThrows(IllegalArgumentException.class,
            () -> new FixedWindowBudget(
                Clock.systemUTC(), 0));
        var limiter = new FixedWindowBudget(
            Clock.systemUTC(), 100);
        assertThrows(IllegalArgumentException.class,
            () -> limiter.allow("key", 0,
                Duration.ofSeconds(1)));
        assertThrows(IllegalArgumentException.class,
            () -> limiter.allow("key", 1,
                Duration.ZERO));
    }
}
```

### 8.2. IdentityCallGuardTests.java

`src/test/java/demo/gateway/IdentityCallGuardTests.java`:

```java
package demo.gateway;

import java.time.Duration;
import java.util.concurrent.TimeoutException;

import org.junit.jupiter.api.Test;
import reactor.core.Disposable;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.*;

class IdentityCallGuardTests {

    @Test
    void normalResponsePasses() {
        var guard = new IdentityCallGuard(
            1, Duration.ofSeconds(1));
        StepVerifier.create(guard.protect(Mono.just("ok")))
            .expectNext("ok")
            .verifyComplete();
    }

    @Test
    void secondInFlightCallFailsFast() {
        var guard = new IdentityCallGuard(
            1, Duration.ofSeconds(5));
        Disposable hold =
            guard.protect(Mono.<String>never()).subscribe();
        try {
            StepVerifier.create(
                    guard.protect(Mono.just("second")))
                .expectError(IdentityCallGuard.Busy.class)
                .verify();
        }
        finally {
            hold.dispose();
        }
        StepVerifier.create(guard.protect(Mono.just("free")))
            .expectNext("free")
            .verifyComplete();
    }

    @Test
    void timeoutDoesNotTurnIntoSuccessfulPrincipal() {
        var guard = new IdentityCallGuard(
            1, Duration.ofMillis(40));
        StepVerifier.create(
                guard.protect(Mono.<String>never()))
            .expectError(TimeoutException.class)
            .verify(Duration.ofSeconds(2));
    }

    @Test
    void invalidGuardConfigurationFails() {
        assertThrows(IllegalArgumentException.class,
            () -> new IdentityCallGuard(
                0, Duration.ofSeconds(1)));
        assertThrows(IllegalArgumentException.class,
            () -> new IdentityCallGuard(
                1, Duration.ZERO));
    }
}
```

Các test này chứng minh admission, TTL theo clock demo, concurrency và timeout behavior tại lớp local. Không chứng minh IdP network/TLS/Redis distributed limiter. `Semaphore.tryAcquire` không block; cancellation release slot qua `doFinally`.

## 9. HTTP integration tests: Gateway + JWT thật trong môi trường local

`GatewayHttpTests.java` dùng `NimbusJwtEncoder` tạo signed HS256 JWT fixture, gửi qua network tới Spring Boot `RANDOM_PORT`. `ReactiveJwtDecoder` kiểm chữ ký, issuer, audience, expiry; GatewayFilter sau đó áp tenant. Không dùng `mockJwt()` để tạo Authentication trực tiếp, vì như vậy sẽ bỏ qua decoder thật. **Khóa HS256 chỉ dành localhost/test**, không được deploy production.

`src/test/java/demo/gateway/GatewayHttpTests.java`:

```java
package demo.gateway;

import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.List;
import javax.crypto.SecretKey;
import javax.crypto.spec.SecretKeySpec;

import com.nimbusds.jose.jwk.source.ImmutableSecret;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.oauth2.jose.jws.MacAlgorithm;
import org.springframework.security.oauth2.jwt.JwtClaimsSet;
import org.springframework.security.oauth2.jwt.JwtEncoderParameters;
import org.springframework.security.oauth2.jwt.JwsHeader;
import org.springframework.security.oauth2.jwt.NimbusJwtEncoder;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class GatewayHttpTests {

    @Autowired
    WebTestClient client;

    private static String signed(
            String sub, String tenant, String issuer,
            String audience, SecretKey key) {

        Instant now = Instant.now();
        JwtClaimsSet.Builder builder = JwtClaimsSet.builder()
            .issuer(issuer)
            .subject(sub)
            .audience(List.of(audience))
            .issuedAt(now)
            .notBefore(now.minusSeconds(5))
            .expiresAt(now.plusSeconds(900))
            .claim("scope", "orders.read");

        if (tenant != null) {
            builder.claim("tenant_id", tenant);
        }

        return new NimbusJwtEncoder(new ImmutableSecret<>(key))
            .encode(JwtEncoderParameters.from(
                JwsHeader.with(MacAlgorithm.HS256).build(),
                builder.build()))
            .getTokenValue();
    }

    private static String valid(String sub, String tenant) {
        return signed(sub, tenant,
            SecurityConfig.ISSUER,
            SecurityConfig.AUDIENCE, SecurityConfig.DEMO_KEY);
    }

    @Test
    void publicRouteCanBeCalledAnonymously() {
        client.get().uri("/public")
            .exchange().expectStatus().isOk()
            .expectBody(String.class).isEqualTo("public");
    }

    @Test
    void missingBearerIs401() {
        client.get().uri("/api/orders")
            .exchange().expectStatus().isUnauthorized();
    }

    @Test
    void malformedBearerIs401() {
        client.get().uri("/api/orders")
            .headers(h -> h.setBearerAuth("not-a-jwt"))
            .exchange().expectStatus().isUnauthorized();
    }

    @Test
    void wrongIssuerIs401() {
        String jwt = signed("wrong-issuer", "acme",
            "https://untrusted.invalid",
            SecurityConfig.AUDIENCE, SecurityConfig.DEMO_KEY);
        client.get().uri("/api/orders")
            .headers(h -> h.setBearerAuth(jwt))
            .exchange().expectStatus().isUnauthorized();
    }

    @Test
    void wrongAudienceIs401() {
        String jwt = signed("wrong-aud", "acme",
            SecurityConfig.ISSUER,
            "different-api", SecurityConfig.DEMO_KEY);
        client.get().uri("/api/orders")
            .headers(h -> h.setBearerAuth(jwt))
            .exchange().expectStatus().isUnauthorized();
    }

    @Test
    void badSignatureIs401() {
        SecretKey wrong = new SecretKeySpec(
            "bad-signing-key-32-chars-minimum-test-only"
                .getBytes(StandardCharsets.UTF_8),
            "HmacSHA256");
        String jwt = signed("wrong-signature", "acme",
            SecurityConfig.ISSUER,
            SecurityConfig.AUDIENCE, wrong);
        client.get().uri("/api/orders")
            .headers(h -> h.setBearerAuth(jwt))
            .exchange().expectStatus().isUnauthorized();
    }

    @Test
    void missingTenantClaimIs403() {
        client.get().uri("/api/orders")
            .headers(h -> h.setBearerAuth(
                valid("no-tenant", null)))
            .exchange().expectStatus().isForbidden();
    }

    @Test
    void tenantOutsideAllowlistIs403() {
        client.get().uri("/api/orders")
            .headers(h -> h.setBearerAuth(
                valid("bad-tenant", "unlisted")))
            .exchange().expectStatus().isForbidden();
    }

    @Test
    void forgedTenantHeaderCannotOverrideSignedTenant() {
        client.get().uri("/api/orders")
            .headers(h -> {
                h.setBearerAuth(valid("spoofed", "acme"));
                h.set("X-Tenant-Id", "globex");
                h.set("X-Verified-Tenant", "admin");
            })
            .exchange().expectStatus().isOk()
            .expectBody(String.class).isEqualTo(
                "tenant=acme;untrustedForwarded=false;" +
                "bearerForwarded=false");
    }

    @Test
    void legitimateTenantGetsVerifiedForwardedHeader() {
        client.get().uri("/api/orders")
            .headers(h -> h.setBearerAuth(
                valid("forwarded", "globex")))
            .exchange().expectStatus().isOk()
            .expectBody(String.class).isEqualTo(
                "tenant=globex;untrustedForwarded=false;" +
                "bearerForwarded=false");
    }

    @Test
    void quotaAllowsTwoRequestsThen429() {
        String token = valid("quota-test", "acme");
        client.get().uri("/api/orders")
            .headers(h -> h.setBearerAuth(token))
            .exchange().expectStatus().isOk();
        client.get().uri("/api/orders")
            .headers(h -> h.setBearerAuth(token))
            .exchange().expectStatus().isOk();
        client.get().uri("/api/orders")
            .headers(h -> h.setBearerAuth(token))
            .exchange().expectStatus().isEqualTo(429);
    }

    @Test
    void sameSubjectDifferentTenantHasOwnQuota() {
        String acme = valid("same-subject", "acme");
        String globex = valid("same-subject", "globex");

        client.get().uri("/api/orders")
            .headers(h -> h.setBearerAuth(acme))
            .exchange().expectStatus().isOk();
        client.get().uri("/api/orders")
            .headers(h -> h.setBearerAuth(acme))
            .exchange().expectStatus().isOk();
        client.get().uri("/api/orders")
            .headers(h -> h.setBearerAuth(globex))
            .exchange().expectStatus().isOk();
    }

    @Test
    void directInternalEndpointIsDenied() {
        client.get().uri("/__demo_upstream")
            .headers(h -> h.setBearerAuth(
                valid("internal", "acme")))
            .exchange().expectStatus().isForbidden();
    }

    @Test
    void cookieAloneIsNotBearerAuth() {
        client.get().uri("/api/orders")
            .cookie("access_token", "irrelevant")
            .exchange().expectStatus().isUnauthorized();
    }

    @Test
    void basicAuthIsNotBearerJwt() {
        client.get().uri("/api/orders")
            .headers(h -> h.setBasicAuth("alice", "password"))
            .exchange().expectStatus().isUnauthorized();
    }
}
```

Tổng cộng **23 test mẫu**: 4 cho limiter, 4 cho guard và 15 HTTP tests. Đây là mã để người học tự chạy, **không khẳng định đã chạy Maven trong môi trường của bạn**. Unit tests kiểm local logic; HTTP tests kiểm real JWT decoder và Gateway filters local, **không** chứng minh actual IdP introspection, JWKS fetch/key rotation, Redis hoặc multi-pod quota.

### 9.1. Chạy trên localhost

```bash
java -version
mvn -version
mvn test
mvn spring-boot:run
```

Quan sát những request không cần issued JWT:

```bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/api/orders
curl -i -H 'Authorization: Bearer invalid' \
  http://localhost:8080/api/orders
```

Kỳ vọng public 200, missing/malformed Bearer 401, trừ khi đã vượt coarse pre-auth quota 100 requests/phút từ cùng remote peer và nhận **429 trước authentication**. Không có Authorization Server cấp token trong app; signed demo tokens được tạo bởi test helper. Không đưa `DEMO_KEY` hoặc test tokens ra production.

## 10. Production: RedisRateLimiter và Gateway timeout

### 10.1. Redis-based tenant-wide quota

Trong triển khai nhiều replicas, dùng Spring Cloud Gateway 4.3 `RequestRateLimiter` + Redis reactive. Thêm dependency:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-redis-reactive</artifactId>
</dependency>
```

Production YAML **minh họa**, thay cho demo route (không khai cả hai tuyến cùng predicate mà thiếu thứ tự rõ):

```yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: tenant-orders
              uri: https://orders.internal.example
              predicates:
                - Path=/api/orders/**
              filters:
                - name: RequestRateLimiter
                  args:
                    key-resolver: "#{@verifiedTenantKeyResolver}"
                    redis-rate-limiter.replenishRate: 10
                    redis-rate-limiter.burstCapacity: 20
                    redis-rate-limiter.requestedTokens: 1
```

`redis-rate-limiter.replenishRate` là token mỗi giây, `burstCapacity` là burst budget, `requestedTokens` là cost mỗi request. Mặc định exceeded limit → **429**. `KeyResolver` phải lấy **verified principal**:

```java
@Bean
KeyResolver verifiedTenantKeyResolver() {
    return exchange -> exchange.getPrincipal()
        .ofType(JwtAuthenticationToken.class)
        .flatMap(auth -> Mono.justOrEmpty(
            auth.getToken().getClaimAsString("tenant_id")))
        .filter(tenant -> ALLOWED_TENANTS.contains(tenant))
        .map(tenant -> "trusted-issuer:" + tenant);
}
```

Fragment cần imports `KeyResolver`, `JwtAuthenticationToken`, `Mono` và registry `ALLOWED_TENANTS`. Với multi-issuer, key phải có **verified issuer ID**, không hard-code `trusted-issuer`. Không dùng user query param hoặc `X-Tenant-Id` làm key. Theo chính sách, không có key phải bị từ chối; đừng cấu hình `deny-empty-key=false` cho route cần quota.

Một limiter theo tenant **không tự áp per-user quota**. Muốn cả hai, dùng các lớp độc lập và định nghĩa cost của từng route; Redis cũng cần TLS/auth, timeout, availability/fail policy. Khi Redis outage, không cho tenant vượt vô hạn do fallback thiếu kiểm soát.

### 10.2. Timeout downstream ở Gateway

Trong Spring Cloud 2025.0, dùng prefix `spring.cloud.gateway.server.webflux`:

```yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          httpclient:
            connect-timeout: 200
            response-timeout: 750ms
          routes:
            - id: api
              uri: https://backend.internal.example
              predicates:
                - Path=/api/**
              metadata:
                connect-timeout: 200
                response-timeout: 750
```

Global connect timeout là milliseconds, global response timeout là Java `Duration`; per-route metadata response/connect timeouts được biểu diễn bằng milliseconds. Đừng nhầm settings này với WebClient gọi introspection. Cả hai vẫn cần overall API deadline.

### 10.3. IdP WebClient timeout là cấu hình khác

Fragment:

```java
HttpClient netty = HttpClient.create()
    .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 100)
    .responseTimeout(Duration.ofMillis(250));

WebClient idpClient = WebClient.builder()
    .clientConnector(new ReactorClientHttpConnector(netty))
    .build();

Mono<IdpReply> result = idpClient.post()
    .uri("https://trusted-idp.example.org/introspect")
    .retrieve()
    .bodyToMono(IdpReply.class)
    .timeout(Duration.ofMillis(350));
```

Cần lớp `IdpReply`, imports và client auth đúng chuẩn. Đây chỉ là fragment để nhấn mạnh **HTTP connect, response và overall timeout khác nhau**. Trong production, introspection thường yêu cầu Basic/mTLS/private_key_jwt client authentication; không dùng WebClient mang IdP secret để gọi URI do user kiểm soát, tránh SSRF. Không gửi access token/client secret trong URL query hoặc HTTP logs.

### 10.4. Circuit breaker và retry cho đúng nơi

Gateway `CircuitBreaker` route filter (Spring Cloud CircuitBreaker/Reactor Resilience4j) bảo vệ business upstream; muốn circuit cho **IdP introspection** phải bọc outbound IdP client/`ReactiveOpaqueTokenIntrospector` riêng. Cấu hình breaker theo issuer để tenant A lỗi không kéo tenant B. Khi circuit open, **không return success principal**. Với 429/503/backend timeout có thể retry chọn lọc và giới hạn attempts trong tổng deadline; không retry POST business không có idempotency key.

## 11. Kiểm thử staging bắt buộc ngoài mã local

- **Pre-auth order:** gửi một lượng lớn invalid Bearer tokens, spy/mock số calls `SpringReactiveOpaqueTokenIntrospector` để xác nhận 429 xảy ra **trước** network introspection.
- **IdP outage/latency:** token đã được cấp nhưng introspection 429/5xx/timeout; protected endpoint phải không xử lý thành công. Xác nhận overall deadline và bulkhead không giữ slot khi canceled.
- **JWT keys:** key rotation, unknown `kid`, wrong issuer/audience, JWK fetch timeout không cho bypass signature.
- **Tenant spoof:** wrong `X-Tenant-Id`, forged `Forwarded`, path tenant mismatch, same subject khác issuer/tenant, unauthorized tenant.
- **Hierarchical quotas:** tổng tenant ≤ plan và mỗi subject ≤ user quota qua **N pods**, không chỉ trong một process.
- **Redis outage:** thử fail behavior đã approved, metrics/alerts; không silently turn off limits.
- **Long requests:** backend p99 chậm, breaker open, retry attempts có idempotency, status 503/504.
- **Bearer privacy:** không token relay ngoài scope, log redaction, strip untrusted verified headers, backend mTLS.
- **Revocation:** với opaque positive caching, đo stale window so với SLA; JWT offline không tuyên bố revoke instant.
- **Browser/BFF:** CSRF session mutation, SameSite/Origin/CSP nếu thêm cookie auth; demo Bearer-only không có các paths này.
- **Fairness:** một tenant flood không chiếm toàn bộ IdP pool, một issuer outage không làm issuer khác hỏng theo, global safety budget vẫn áp.

Không suy các kết quả staging từ test `mockJwt` hoặc signed fixture local. Test route forward nội bộ không kiểm TLS/mTLS của kết nối gateway → backend thật.

## 12. Quan sát và vận hành

| Metric/SLI | Công dụng |
| --- | --- |
| `gateway.requests` by route/status | RPS, 200/401/403/429/503/504 |
| `preauth.rejected` by trusted ingress class | Phát hiện invalid-token flood trước IdP |
| `tenant.quota.rejected` by tier | Fairness/abuse, tránh raw user labels |
| `jwt.verify.duration`, `jwks.fetch.miss` | CPU/JWKS refresh issue |
| `introspection.duration` p50/p95/p99 | Latency IdP cache miss |
| `idp.inflight`, `idp.bulkhead.rejected` | Capacity/saturation |
| `idp.circuit.state`, `idp.retry.attempts` | Tránh retry storm và breaker chéo issuer |
| `redis.ratelimiter.duration`/errors | Dependency quota phân tán |
| `gateway.backend.duration`/errors | Phân biệt downstream chậm và IdP chậm |
| `revocation.observed.latency` | SLA freshness của opaque token cache |
| Reactor Netty pool wait, event loop lag | Tắc nghẽn/p99 xấu |

Không dùng raw access token, client secret, user email, IP và tenant ID nhạy cảm làm high-cardinality labels nếu chưa được duyệt. Dùng route template, issuer allowlist ID, tenant tier và correlation ID đã được hạn chế để điều tra. Cần runbook rõ cho “IdP outage”, “Redis outage”, “unknown kid”, “tenant flood”, “expired tokens flood” và emergency reduce TTL/retry rate.

## 13. Những lỗi phổ biến

| Anti-pattern | Hậu quả | Cách thay thế |
| --- | --- | --- |
| Chỉ rate-limit sau Authentication | Token giả đã làm IdP quá tải | Pre-auth coarse admission |
| Pre-auth dựa `X-Tenant-Id` | Attacker chọn bucket tenant tùy ý | Trusted IP/ingress metadata |
| Post-auth dùng query tenant/user | Spoof/bypass quota | Verified `JwtAuthenticationToken` |
| Chỉ per-user key | Tenant nhiều users vượt tổng plan | Tenant-wide + user quotas |
| Local limiter coi như global | N pods nhân limit | Redis/distributed limiter |
| Cho thiếu tenant vào default tenant | Lộ dữ liệu cross-tenant | Deny unknown/mismatch |
| Lấy `iss` token chưa verify để fetch JWKS tùy ý | SSRF, JWKS fetch storm | Issuer allowlist |
| Cache JWKS bị nhầm là revocation check | Revoked token vẫn dùng tới `exp` | Introspection/denylist/event nếu cần |
| IdP timeout trả last-known-good vô hạn | Fail-open | No stale-on-error |
| Retry token invalid/active=false | Retry storm và khó vận hành | No retry auth failures |
| Không giới hạn IdP concurrent calls | Pool starvation khi AS chậm | Semaphore/bulkhead + deadline |
| Dùng Gateway httpclient timeout cho IdP WebClient | IdP calls vẫn treo | Separate IdP transport limits |
| Circuit open thì `permitAll` | Authentication bypass | Fail-closed |
| Backend tin `X-Verified-Tenant` Internet | Header spoofing | Strip, rewrite và mTLS/private ingress |
| Relay raw JWT tới mọi upstream | Token leakage, wrong audience | Explicit token exchange/relay policy |
| Tắt CSRF trên web cookie login | CSRF mutation | Chain riêng và CSRF |
| Test local signed JWT được coi là network IdP test | Thiếu coverage TLS, JWKS, revocation | Staging mock-AS và real IdP |
| Log full token/introspection response | Credential leak | Redaction + safe metadata |

## 14. Checklist production

1. Xác định trust boundaries: WAF/ingress → Gateway → IdP/AS → tenant services.
2. Có pre-auth coarse throttle đủ sớm để giảm JWT/introspection amplification.
3. JWT/opaque Authentication xác minh token và issuer/audience trước khi đọc tenant claim.
4. Có quota post-auth theo issuer/tenant/user và thêm global per-IdP capacity.
5. Tránh header/path/query spoofing; không chọn IdP URL từ issuer chưa trust.
6. Có token/JWKS caching khác biệt rõ với opaque introspection positive cache/revoke SLA.
7. Có total deadline cho IdP, timeout connection/pool/TLS/response, bulkhead, circuit fail-closed.
8. Có backend route timeout/circuit riêng, retry có giới hạn và idempotency policy.
9. Quota multi-pod dùng Redis/trusted distributed limiter, không chỉ local Caffeine.
10. Strip/rewrite identity headers, chặn direct backend ingress, mTLS/service identity.
11. Giữ CSRF khi xuất hiện browser cookie auth; không copy API Bearer-only setting.
12. Test negative cases 401/403/429, IdP outage/Redis outage, revocation, wrong issuer/audience.
13. Giám sát p99, inflight, quota rejects, unknown keys, retry amplification và fairness.
14. Có runbook giảm TTL, phân quyền điều chỉnh quota, kiểm version Spring Boot/Cloud trước upgrade.

## 15. Câu hỏi ôn tập

**1.** Tại sao post-auth tenant limiter chưa đủ bảo vệ introspection?  
Vì token chưa xác minh vẫn có thể kích hoạt AS call trước khi principal xuất hiện.

**2.** Có nên dùng `X-Tenant-Id` trước xác thực làm key?  
Không. Client có thể giả/đổi header.

**3.** JWT có thể không cần IdP mỗi request không?  
Có, signature được verify local bằng JWK đã cache; không tự có revocation freshness.

**4.** Quota per-user có giới hạn tổng tenant không?  
Không; cần tenant-wide bucket độc lập.

**5.** Bulkhead khác rate limiter thế nào?  
Bulkhead giới hạn calls đang bay, rate limiter giới hạn tốc độ; cả hai cần timeout.

**6.** Khi IdP lỗi, có thể tự xác thực principal giả không?  
Không. Fail-closed; status dependency theo exception mapping nhưng protected action không được 2xx.

**7.** Gateway backend timeout có tự giới hạn introspection WebClient không?  
Không. IdP client cần deadline riêng.

**8.** Vì sao cần RedisRateLimiter cho multi-pod?  
Local limiter áp mỗi pod riêng, không đảm bảo quota toàn cụm.

**9.** Làm gì với unknown issuer/tenant?  
Deny; không dùng arbitrary discovery hoặc default tenant.

**10.** CSRF có bị loại bỏ chỉ vì website dùng OAuth2 không?  
Không. Cookie-auth/browser mutation vẫn cần CSRF; demo chỉ Bearer-header-only.

**11.** Vì sao không retry POST business vô điều kiện?  
Timeout có thể xảy ra sau khi upstream đã thực hiện side effect; cần idempotency.

**12.** Điều gì chứng minh test local?  
JWT signature/audience/issuer được kiểm, tenant header không override, 429 sau quota. Không chứng minh Redis, JWKS network, opaque revocation hay nhiều replicas.

### Tài liệu chính thức

- Spring Cloud 2025.0 release (Boot 3.5 compatibility): https://spring.io/blog/2025/05/29/spring-cloud-2025-0-0-is-abvailable/
- Spring Cloud 2025.0 release notes, new starter/prefixes: https://github.com/spring-cloud/spring-cloud-release/wiki/Spring-Cloud-2025.0-Release-Notes
- Spring Cloud Gateway 4.3 starter: https://docs.spring.io/spring-cloud-gateway/reference/4.3/spring-cloud-gateway-server-webflux/starter.html
- Spring Cloud Gateway 4.3 RequestRateLimiter: https://docs.spring.io/spring-cloud-gateway/reference/4.3/spring-cloud-gateway-server-webflux/gatewayfilter-factories/requestratelimiter-factory.html
- Spring Cloud Gateway 4.3 HTTP timeouts: https://docs.spring.io/spring-cloud-gateway/reference/4.3/spring-cloud-gateway-server-webflux/http-timeouts-configuration.html
- Spring Cloud Gateway 4.3 CircuitBreaker: https://docs.spring.io/spring-cloud-gateway/reference/4.3/spring-cloud-gateway-server-webflux/gatewayfilter-factories/circuitbreaker-filter-factory.html
- Spring Security 6.5 Reactive JWT: https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/resource-server/jwt.html
- Spring Security 6.5 Reactive Opaque: https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/resource-server/opaque-token.html
- RFC 7662 – Token Introspection: https://www.rfc-editor.org/rfc/rfc7662
- RFC 6750 – Bearer Token Usage: https://www.rfc-editor.org/rfc/rfc6750
- Reactor Netty HTTP Client: https://projectreactor.io/docs/netty/release/reference/http-client.html

**Tóm lại:** Gateway nhiều tenant bảo vệ IdP hiệu quả bằng **pre-auth coarse throttle trước chi phí xác thực**, **post-auth tenant/user quota trên danh tính đã verify**, **identity-specific rate/concurrency limits**, timeout tổng và circuit fail-closed. Không lấy tenant từ header tự khai, không đồng nhất JWK cache với revocation, và không chỉ dựa local limiter để tuyên bố quota toàn cluster. Chạy local signed JWT tests rồi bổ sung staging Redis/IdP/network-failure tests trước khi triển khai.