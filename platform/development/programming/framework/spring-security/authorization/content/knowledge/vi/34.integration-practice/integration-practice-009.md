# Tích hợp dịch vụ chính sách với timeout và cache có kiểm soát

## 1. Bài toán tích hợp dịch vụ chính sách trong authorization

Trong một ứng dụng Spring Security, quyết định truy cập đôi khi được đưa ra bởi một **dịch vụ chính sách tập trung** (Policy Decision Point, **PDP**). Ứng dụng gọi dịch vụ ấy là **Policy Enforcement Point (PEP)**: phải kiểm tra quyết định và chặn hành động không được phép.

Ví dụ Alice có authority chức năng `DOCUMENT_READ` nhưng không phải tài liệu nào cũng được xem. Khi nhận `GET /documents/101`, API cần biết Alice thuộc tenant nào, tài liệu 101 thuộc tenant nào, Alice có grant/ACL nào, grant đã hết hạn chưa và chính sách có vừa đổi hay không.

```text
Client ──► Spring Security authentication
                 │
                 ▼
       HTTP / service-level authorization
                 │
                 ▼
       PEP ──► PDP: subject + action + resource + tenant
                 │         │
                 │         ├─ ALLOW hợp lệ
                 │         ├─ DENY
                 │         └─ timeout / lỗi / response sai
                 ▼
       Chỉ thực thi khi quyết định có thể tin cậy
       và dữ liệu vẫn đúng phạm vi tenant/owner
```

Nếu PEP chỉ gọi PDP để log, nhưng vẫn chạy nghiệp vụ sau `DENY` hoặc timeout thì authorization chưa được thực thi. Nếu API trả HTTP 403 nhưng database đã được cập nhật trước đó, bảo mật cũng đã thất bại.

Ba mục tiêu đi cùng nhau: **giới hạn thời gian chờ**, **thất bại an toàn (fail closed)** và **cache có hạn, không mở rộng quyền khi quá hạn**. Các cơ chế này bảo vệ cả tính đúng của quyền lẫn khả năng hoạt động của ứng dụng khi PDP có độ trễ hoặc ngừng đáp ứng.

## 2. Hợp đồng request/response PDP: dữ liệu nào cần có?

Một request server-to-server có thể được biểu diễn như sau:

```json
{
  "subjectId": "user-42",
  "tenantId": "tenant-a",
  "action": "DOCUMENT_READ",
  "resourceId": 101,
  "permissionRevision": 7
}
```

PDP trả quyết định theo hợp đồng API minh họa:

```json
{
  "allowed": true,
  "validUntil": "2026-11-06T08:00:02Z",
  "policyVersion": "p-183",
  "decisionId": "dec-8721"
}
```

Ý nghĩa bảo mật:

- `subjectId`, `tenantId`, `permissionRevision` phải được xác định bởi authentication provider và dữ liệu server đáng tin cậy. Không nhận chúng từ header/client body như sự thật.
- `action` phải phân biệt READ, EXPORT, ARCHIVE, ADMIN, v.v. `resourceId` cần đi cùng namespace/tenant để không nhầm hai tài nguyên trùng ID ở các phạm vi khác nhau.
- `allowed` **bắt buộc** có giá trị boolean hợp lệ. Response HTTP 200 không đồng nghĩa ALLOW; body null, lỗi JSON hoặc thiếu trường là **không có quyết định hợp lệ**.
- `validUntil` là thời điểm hết hiệu lực, kiểm tra theo bất biến `now < validUntil`. PDP phải tính hạn này dựa trên expiry grant và các ràng buộc chính sách.
- `policyVersion` và `decisionId` hỗ trợ audit, nhưng phiên bản trong response không tự thông báo cho các cache khác rằng đã có policy mới.
- Khi PDP trả thêm *obligations* (điều kiện che trường, step-up MFA, giới hạn giao dịch), PEP phải thi hành chúng; không được coi ALLOW đơn thuần là bỏ qua điều kiện.

Những trường nào ảnh hưởng tới quyết định đều phải được truyền tới PDP hoặc được PDP tự tra cứu đáng tin cậy. Nếu quyền dựa vào ACL, ownership hoặc trạng thái bản ghi, chỉ gửi role chung là thiếu ngữ cảnh. Contract cũng cần quy định rõ DENY đối tượng không tồn tại và không có quyền để tránh lộ sự tồn tại của ID qua thông báo lỗi.

## 3. Timeout: connect, request và deadline tổng

Hai timeout khác nhau:

| Cơ chế | Giới hạn gì? | Điểm cần nhớ |
| --- | --- | --- |
| `HttpClient.Builder.connectTimeout` | Tạo một kết nối mới tới PDP | Kết nối được tái sử dụng thì giới hạn này có thể không có tác dụng |
| `HttpRequest.Builder.timeout` | Thời gian một request chờ nhận response | Không đặt giới hạn này thì chờ response có thể kéo dài |
| Deadline của request nghiệp vụ | Tổng thời gian cho xác thực, PDP, database và response | Retry phải nằm trong thời gian còn lại |

Ví dụ ngân sách minh họa: request nghiệp vụ có 1.000 ms; connect timeout 100 ms; PDP request timeout 300 ms; dành thời gian còn lại cho DB/serialization. Các số này **không phải mặc định của Spring Security**. Hãy xác định từ latency p95/p99, SLO, lưu lượng, số thread và rủi ro nghiệp vụ.

**Không cộng hai timeout thành 400 ms như một bảo đảm**: request timeout áp dụng cho lời gọi request, trong đó có thời gian thiết lập kết nối theo hành vi HTTP client. Kết nối mới và request trên connection pool cần test riêng. HTTP timeout có thể gồm cả thời gian chờ response; cần đặt deadline ở các lớp phía trước để không vượt ngân sách tổng.

Một chính sách retry sai có thể gọi PDP ba lần, mỗi lần 300 ms, khiến một request 1 giây gần như hết ngân sách trước khi đụng database, đồng thời tăng tải lên PDP đang lỗi. Mặc định phù hợp là một lần đánh giá có deadline rõ, retry rất hạn chế khi lỗi tạm thời và vẫn còn ngân sách. **Không retry một quyết định DENY hợp lệ.**

## 4. Fail closed và chính sách suy giảm

`DENY` do PDP trả về khác với `UNAVAILABLE` khi PDP không trả lời. Cả hai đều phải **chặn thực thi**, nhưng cần ghi lý do khác nhau trong audit và metrics.

| Trạng thái | Đọc nội bộ cho phép cache ngắn | Mutation/admin nhạy cảm |
| --- | --- | --- |
| ALLOW hợp lệ từ PDP | Cho phép nếu phạm vi dữ liệu đúng | Cho phép nếu mọi điều kiện bổ sung đúng |
| DENY hợp lệ | Chặn | Chặn |
| Timeout/lỗi, cache trống | Chặn | Chặn |
| Cache ALLOW đúng key, chưa hết hạn | Có thể dùng nếu contract chấp nhận stale window | Không dùng nếu cần kiểm tra quyền hiện hành |
| Cache quá hạn nhưng PDP lỗi | Chặn, không kéo dài stale ALLOW | Chặn |
| Circuit breaker OPEN | Chặn khi không có quyết định được policy chấp nhận | Chặn |

Đừng triển khai:

```java
// SAI: dịch vụ chính sách không khả dụng lại mở quyền.
try {
    return pdp.isAllowed(input);
} catch (Exception failure) {
    return true;
}
```

Trong ví dụ `@PreAuthorize`, guard trả `false` khi PDP unavailable nên caller nhận denial của Spring method security. Tùy hợp đồng HTTP, API có thể trả 403 hoặc dùng một exception được ánh xạ 503 cho sự cố hạ tầng; **cả hai phải bảo đảm method nghiệp vụ không chạy**. Việc dùng cached ALLOW khi PDP không truy cập được là một lựa chọn chấp nhận rủi ro trong thời hạn xác định, không phải bảo đảm quyền hiện hành vẫn ALLOW.

## 5. Cache key, TTL và cửa sổ quyền cũ

Một khóa quyết định theo đối tượng tối thiểu:

```text
(subjectId, tenantId, action, resourceId, permissionRevision)
```

Nếu quyết định phụ thuộc group, owner, resource state, MFA, IP tin cậy, loại resource hoặc thuộc tính môi trường, phải đưa những phụ thuộc ấy vào key/version đáng tin cậy hoặc **không cache**. Cache theo mỗi username hay URL là nguy hiểm: cùng một caller có thể đọc nhiều tài liệu hoặc cùng URL có thể chứa nhiều hành động.

Trong ví dụ phía dưới, cache Caffeine có `maximumSize(10_000)` và `expireAfterWrite(2 giây)`. Bên cạnh TTL cứng, guard còn kiểm tra `validUntil` từ PDP tại mỗi lần hit. `expireAfterWrite` không gia hạn khi đọc; `expireAfterAccess` có thể khiến ALLOW được dùng lâu hơn nếu traffic liên tục.

### Vấn đề revoke

Nếu PDP revoke Alice vào thời điểm `t=0` nhưng node ứng dụng còn cached ALLOW tới `t+2s`, Alice có thể tiếp tục đọc trong cửa sổ đó. Với hành động yêu cầu **thu hồi tức thì**, TTL 2 giây không đủ: cần bỏ cache ALLOW hoặc sử dụng phiên bản/quyết định mới với bảo đảm nhất quán phù hợp.

Có các tình huống cần mô hình hóa:

1. Event revoke chỉ đến instance A, instance B vẫn còn cache.
2. Event xóa cache đến trước, response PDP cũ đến sau lại nạp ALLOW vào cache.
3. JWT cũ còn `permissionRevision` cũ; giá trị trong token không tự cập nhật khi revoke.
4. Owner của resource đổi, nhưng chỉ cache theo subject được invalidation.
5. Grant hết hạn trước thời điểm cache TTL; PDP phải giới hạn `validUntil` không vượt expiry đó.
6. Cache DENY còn hạn làm grant mới chưa được dùng ngay; thường ít nguy hiểm hơn stale ALLOW, nhưng vẫn ảnh hưởng UX/SLA.

`invalidateSubject` ở một JVM chỉ xóa local cache. Với multi-instance, cần sự kiện đáng tin, version fence hoặc chọn kiểm tra PDP trực tiếp cho những thao tác không chịu được stale ALLOW.

## 6. Java 17 độc lập: mô phỏng timeout/cache/revoke

Đoạn Java này **chạy độc lập**, không cần Spring hay Caffeine, để kiểm tra các bất biến: cache hit không hỏi PDP thêm, invalidate khiến quyết định mới được lấy, timeout không tự mở quyền, hành động nhạy cảm không dùng cache.

Tệp `PolicyCacheDemo.java`:

```java
import java.time.Instant;
import java.util.HashMap;
import java.util.Map;

public class PolicyCacheDemo {
    record Key(String subject, String tenant,
               String action, long resource, long revision) {}
    record Reply(boolean allowed, Instant validUntil) {}

    static class FakePdp {
        final Map<Key, Boolean> grants = new HashMap<>();
        boolean online = true;
        int calls;

        Reply decide(Key key, Instant now) {
            calls++;
            if (!online) throw new IllegalStateException("timeout");
            return new Reply(grants.getOrDefault(key, false),
                    now.plusSeconds(10));
        }
    }

    static class Guard {
        final FakePdp pdp;
        final Map<Key, Reply> cache = new HashMap<>();

        Guard(FakePdp pdp) { this.pdp = pdp; }

        boolean check(Key key, Instant now, boolean critical) {
            if (!critical) {
                Reply old = cache.get(key);
                if (old != null && now.isBefore(old.validUntil())) {
                    return old.allowed();
                }
            }
            try {
                Reply decision = pdp.decide(key, now);
                if (!critical) {
                    Instant hardLimit = now.plusSeconds(2);
                    Instant until = decision.validUntil()
                            .isBefore(hardLimit)
                            ? decision.validUntil() : hardLimit;
                    cache.put(key, new Reply(decision.allowed(), until));
                }
                return decision.allowed();
            } catch (IllegalStateException down) {
                return false;
            }
        }

        void invalidate(Key key) { cache.remove(key); }
    }

    public static void main(String[] args) {
        Instant now = Instant.parse("2026-11-06T08:00:00Z");
        Key read = new Key("alice", "tenant-a",
                "DOCUMENT_READ", 101, 7);
        Key admin = new Key("alice", "tenant-a",
                "POLICY_EDIT", 101, 7);

        FakePdp pdp = new FakePdp();
        pdp.grants.put(read, true);
        Guard guard = new Guard(pdp);

        System.out.println("first=" + guard.check(read, now, false));
        System.out.println("cached=" +
                guard.check(read, now.plusMillis(500), false));
        System.out.println("calls=" + pdp.calls);

        pdp.grants.put(read, false);
        guard.invalidate(read);
        System.out.println("revoked=" +
                guard.check(read, now.plusMillis(600), false));

        pdp.online = false;
        Key other = new Key("alice", "tenant-a",
                "DOCUMENT_READ", 102, 7);
        System.out.println("timeoutRead=" +
                guard.check(other, now.plusSeconds(1), false));
        System.out.println("timeoutAdmin=" +
                guard.check(admin, now.plusSeconds(1), true));
        System.out.println("totalCalls=" + pdp.calls);
    }
}
```

Chạy trên JDK 17 trở lên:

```bash
javac PolicyCacheDemo.java
java PolicyCacheDemo
```

Stdout chính xác:

```text
first=true
cached=true
calls=1
revoked=false
timeoutRead=false
timeoutAdmin=false
totalCalls=4
```

Nếu bỏ `guard.invalidate(read)`, kết quả `revoked` có thể tiếp tục là `true` do cache ALLOW còn hạn tại `t+600ms`. Mã này mô phỏng thứ tự logic và giả định một thread; production cần cache thread-safe, invalidation đa node và timeout HTTP thật.

## 7. Spring Boot: dependency và cấu hình thời gian chờ

Ví dụ tích hợp dùng Java 17+, Spring Boot 3.x, Spring Security 6, Jackson, Caffeine và JDBC. Các đoạn sau thuộc một ứng dụng đã có authentication và database, **không phải** các tệp standalone `javac`. Gradle dependencies minh họa:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    implementation 'com.github.ben-manes.caffeine:caffeine'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

Trong package `demo.policy`, tệp `PolicyConfig.java`:

```java
package demo.policy;

import java.net.http.HttpClient;
import java.time.Clock;
import java.time.Duration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class PolicyConfig {
    @Bean
    Clock policyClock() {
        return Clock.systemUTC();
    }

    @Bean
    HttpClient policyHttpClient() {
        return HttpClient.newBuilder()
                .connectTimeout(Duration.ofMillis(100))
                .followRedirects(HttpClient.Redirect.NEVER)
                .build();
    }
}
```

Spring Security starter **không tự bật** method authorization. Phải có `@EnableMethodSecurity`, và method được gọi qua Spring-managed AOP proxy. `HttpClient` được tái sử dụng như bean, không tạo mới mỗi request. Trong production, cấu hình TLS trust, mTLS/workload identity hoặc service credential và allowlist host; không tắt TLS verification khi có lỗi kết nối.

## 8. Contracts và HTTP adapter: luôn kiểm tra response

Tệp `PolicyContracts.java` gồm các kiểu package-private:

```java
package demo.policy;

import java.time.Instant;

record AccessPrincipal(
        String subject, String tenant, long permissionRevision) {}

record PolicyKey(
        String subject, String tenant, String action,
        long resourceId, long permissionRevision) {}

record PolicyReply(
        Boolean allowed, Instant validUntil,
        String policyVersion, String decisionId) {}

record CachedDecision(boolean allowed, Instant validUntil) {}

interface PolicyClient {
    PolicyReply decide(PolicyKey key);
}

final class PolicyUnavailableException extends RuntimeException {
    PolicyUnavailableException(String text) { super(text); }
    PolicyUnavailableException(String text, Throwable cause) {
        super(text, cause);
    }
}
```

`AccessPrincipal` phải do authentication provider/converter đáng tin tạo, không nhận trực tiếp từ JSON bên ngoài. Tệp `HttpPolicyClient.java`:

```java
package demo.policy;

import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
final class HttpPolicyClient implements PolicyClient {
    private final HttpClient client;
    private final ObjectMapper mapper;
    private final URI endpoint;

    HttpPolicyClient(HttpClient client, ObjectMapper mapper,
                     @Value("${security.policy.decision-url}")
                     String url) {
        this.client = client;
        this.mapper = mapper;
        this.endpoint = URI.create(url);
        if (!"https".equalsIgnoreCase(endpoint.getScheme())) {
            throw new IllegalArgumentException("PDP must use HTTPS");
        }
    }

    @Override
    public PolicyReply decide(PolicyKey key) {
        try {
            HttpRequest request = HttpRequest.newBuilder(endpoint)
                    .timeout(Duration.ofMillis(300))
                    .header("Content-Type", "application/json")
                    .POST(HttpRequest.BodyPublishers.ofString(
                            mapper.writeValueAsString(key),
                            StandardCharsets.UTF_8))
                    .build();

            HttpResponse<String> response = client.send(
                    request, HttpResponse.BodyHandlers.ofString(
                            StandardCharsets.UTF_8));
            if (response.statusCode() != 200) {
                throw new PolicyUnavailableException(
                        "PDP HTTP " + response.statusCode());
            }
            PolicyReply reply = mapper.readValue(
                    response.body(), PolicyReply.class);
            if (reply == null || reply.allowed() == null
                    || reply.validUntil() == null
                    || reply.policyVersion() == null
                    || reply.decisionId() == null) {
                throw new PolicyUnavailableException("Invalid PDP response");
            }
            return reply;
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new PolicyUnavailableException("Interrupted", ex);
        } catch (IOException ex) {
            throw new PolicyUnavailableException("PDP I/O or JSON error", ex);
        }
    }
}
```

Trong tệp thực, `${security.policy.decision-url}` tương ứng biểu thức cấu hình Spring `@Value` cho property `security.policy.decision-url`, chẳng hạn dạng chuẩn `@Value("${security.policy.decision-url}")`. Cần cung cấp URL HTTPS trusted trong cấu hình và thiết lập authentication giữa các service. Adapter minh họa không tự cấu hình mTLS/token, không giới hạn kích thước response; bổ sung những phần đó theo cơ chế vận hành trước khi production.

`HttpRequest.timeout` giới hạn request 300 ms; `HttpClient.connectTimeout` giới hạn tạo kết nối mới 100 ms. Lỗi `HttpTimeoutException` là `IOException` và đi thành `PolicyUnavailableException`. `ObjectMapper` phải được cấu hình hỗ trợ `Instant` (Spring Boot thường tự cấu hình Jackson Java Time khi có module); cần test response parsing thật. Không chấp nhận HTTP 200 trống, `allowed=null` hoặc response không có expiry.

## 9. Caffeine guard: giới hạn TTL và bỏ cache ở mutation

Tệp `PolicyGuard.java`:

```java
package demo.policy;

import com.github.benmanes.caffeine.cache.Cache;
import com.github.benmanes.caffeine.cache.Caffeine;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;

import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Component;

@Component("policyGuard")
public final class PolicyGuard {
    private static final Duration MAX_AGE = Duration.ofSeconds(2);
    private final PolicyClient client;
    private final Clock clock;
    private final Cache<PolicyKey, CachedDecision> cache;

    public PolicyGuard(PolicyClient client, Clock clock) {
        this.client = client;
        this.clock = clock;
        this.cache = Caffeine.newBuilder()
                .maximumSize(10_000)
                .expireAfterWrite(MAX_AGE)
                .build();
    }

    public boolean canRead(Authentication auth, long id) {
        return decide(auth, "DOCUMENT_READ", id, true);
    }

    public boolean canArchive(Authentication auth, long id) {
        return decide(auth, "DOCUMENT_ARCHIVE", id, false);
    }

    private boolean decide(
            Authentication auth, String action,
            long resourceId, boolean cacheAllowed) {
        if (auth == null || !auth.isAuthenticated()
                || !(auth.getPrincipal() instanceof AccessPrincipal p)
                || p.subject() == null || p.subject().isBlank()
                || p.tenant() == null || p.tenant().isBlank()
                || p.permissionRevision() < 0 || resourceId <= 0) {
            return false;
        }

        PolicyKey key = new PolicyKey(
                p.subject(), p.tenant(), action,
                resourceId, p.permissionRevision());

        Instant now = clock.instant();
        if (cacheAllowed) {
            CachedDecision previous = cache.getIfPresent(key);
            if (previous != null) {
                if (now.isBefore(previous.validUntil())) {
                    return previous.allowed();
                }
                cache.invalidate(key);
            }
        }

        try {
            PolicyReply answer = client.decide(key);
            Instant afterCall = clock.instant();
            if (!answer.validUntil().isAfter(afterCall)) {
                return false;
            }
            if (cacheAllowed) {
                Instant hardLimit = afterCall.plus(MAX_AGE);
                Instant until = answer.validUntil().isBefore(hardLimit)
                        ? answer.validUntil() : hardLimit;
                cache.put(key, new CachedDecision(
                        answer.allowed(), until));
            }
            return answer.allowed();
        } catch (PolicyUnavailableException ex) {
            return false;
        }
    }

    public void invalidateSubject(String subject) {
        cache.asMap().keySet().removeIf(
                k -> k.subject().equals(subject));
    }
}
```

Ở đây `canRead` có thể dùng cache đúng key trong hai giây; `canArchive` luôn hỏi PDP. Nếu PDP timeout và không có cache ALLOW còn hạn, guard trả `false`. Cache **không** tự xử lý revoke đa instance: `invalidateSubject` chỉ là điểm móc để nhận sự kiện đáng tin cậy. Một request đang gọi PDP trước khi revoke có thể nạp lại ALLOW sau invalidate. Với quyền nhạy cảm yêu cầu revoke ngay, hãy bỏ ALLOW cache hoặc xây dựng cơ chế version fence/thống nhất quyết định chặt hơn.

`validUntil` phải do PDP quyết định theo grant expiry/policy và phải được PEP kiểm tra ở mỗi lần hit. Cache DENY ngắn cũng có thể làm quyền vừa được cấp chưa hiệu lực ngay, vì vậy cần nêu trong SLA và bài test. Trong production, lỗi adapter phải được chuẩn hóa thành `PolicyUnavailableException`; không âm thầm chuyển exception thành ALLOW.

## 10. Method security và điều kiện data layer

Tệp `DocumentService.java` minh họa với bảng `documents(id, tenant_id, title, archived)`. Nó được gọi từ Spring-managed bean proxy, có `@EnableMethodSecurity` như phần 7:

```java
package demo.policy;

import java.util.List;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.access.method.P;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class DocumentService {
    private final JdbcTemplate jdbc;

    public DocumentService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @PreAuthorize("""
            hasAuthority('DOCUMENT_READ') and
            @policyGuard.canRead(authentication, #id)
            """)
    public String readTitle(@P("id") long id) {
        AccessPrincipal p = principal();
        List<String> titles = jdbc.query("""
                SELECT title FROM documents
                 WHERE id = ? AND tenant_id = ?
                """, (rs, i) -> rs.getString("title"),
                id, p.tenant());
        return titles.isEmpty() ? null : titles.get(0);
    }

    @Transactional
    @PreAuthorize("""
            hasAuthority('DOCUMENT_ARCHIVE') and
            @policyGuard.canArchive(authentication, #id)
            """)
    public boolean archive(@P("id") long id) {
        AccessPrincipal p = principal();
        int count = jdbc.update("""
                UPDATE documents
                   SET archived = TRUE
                 WHERE id = ? AND tenant_id = ?
                   AND archived = FALSE
                """, id, p.tenant());
        return count == 1;
    }

    private AccessPrincipal principal() {
        Authentication authentication = SecurityContextHolder
                .getContext().getAuthentication();
        return (AccessPrincipal) authentication.getPrincipal();
    }
}
```

`@P("id")` giúp Spring SpEL nhận biết tham số `#id` khi build không có `-parameters`. Quyền chức năng `DOCUMENT_READ`/`DOCUMENT_ARCHIVE` và quyết định PDP là **hai điều kiện đồng thời**. Query/update còn giới hạn tenant; nếu domain dùng ACL/owner thì bổ sung predicate tương ứng. Không để caller truyền tenant của người khác vào repository.

Một quyết định ALLOW tại `t1` và lần ghi database ở `t2` có thể gặp race khi quyền đổi. `@Transactional` hỗ trợ transaction DB, nhưng không tạo transaction phân tán với PDP. Với hành động rủi ro cao cần kiểm tra version/quyền tại thời điểm ghi hoặc ràng buộc cập nhật dữ liệu an toàn. Gọi method qua `this.method()` trong cùng bean có thể bỏ qua AOP interception; cần test đường vào thực.

## 11. Unit test và kiểm thử tích hợp

Dùng fake `PolicyClient` để kiểm tra cache và fail closed độc lập với mạng. Trong cùng package `demo.policy`, đoạn JUnit 5 sau có thể đưa vào `PolicyGuardTest.java`:

```java
package demo.policy;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.List;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;
import org.springframework.security.authentication
        .UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

import static org.junit.jupiter.api.Assertions.*;

class PolicyGuardTest {
    static final Instant NOW =
            Instant.parse("2026-11-06T08:00:00Z");

    Authentication actor(String user, String tenant) {
        return UsernamePasswordAuthenticationToken.authenticated(
                new AccessPrincipal(user, tenant, 7L), "N/A",
                List.of(new SimpleGrantedAuthority("DOCUMENT_READ")));
    }

    @Test
    void cacheHitThenInvalidate() {
        AtomicBoolean allow = new AtomicBoolean(true);
        AtomicInteger calls = new AtomicInteger();
        PolicyClient fake = key -> {
            calls.incrementAndGet();
            return new PolicyReply(
                    allow.get(), NOW.plusSeconds(5), "p1", "d1");
        };
        PolicyGuard guard = new PolicyGuard(
                fake, Clock.fixed(NOW, ZoneOffset.UTC));

        assertTrue(guard.canRead(actor("alice", "t1"), 101));
        assertTrue(guard.canRead(actor("alice", "t1"), 101));
        assertEquals(1, calls.get());
        allow.set(false);
        guard.invalidateSubject("alice");
        assertFalse(guard.canRead(actor("alice", "t1"), 101));
        assertEquals(2, calls.get());
    }

    @Test
    void timeoutAndExpiredReplyDeny() {
        PolicyClient down = key -> {
            throw new PolicyUnavailableException("timeout");
        };
        PolicyGuard guard = new PolicyGuard(
                down, Clock.fixed(NOW, ZoneOffset.UTC));
        assertFalse(guard.canRead(actor("alice", "t1"), 101));
        assertFalse(guard.canArchive(actor("alice", "t1"), 101));

        PolicyClient expired = key -> new PolicyReply(
                true, NOW, "p1", "d2");
        assertFalse(new PolicyGuard(
                expired, Clock.fixed(NOW, ZoneOffset.UTC))
                .canRead(actor("alice", "t1"), 101));
    }

    @Test
    void keySeparatesTenantsAndResources() {
        AtomicInteger calls = new AtomicInteger();
        PolicyClient fake = key -> {
            calls.incrementAndGet();
            return new PolicyReply(
                    true, NOW.plusSeconds(5), "p1", "d1");
        };
        PolicyGuard guard = new PolicyGuard(
                fake, Clock.fixed(NOW, ZoneOffset.UTC));
        assertTrue(guard.canRead(actor("alice", "t1"), 101));
        assertTrue(guard.canRead(actor("alice", "t2"), 101));
        assertTrue(guard.canRead(actor("alice", "t1"), 102));
        assertTrue(guard.canRead(actor("bob", "t1"), 101));
        assertEquals(4, calls.get());
    }
}
```

Chạy bằng Gradle trong module tương ứng:

```bash
./gradlew test --tests demo.policy.PolicyGuardTest
```

Đoạn test này xác nhận logic guard với fake PDP, **chưa đo timeout HTTP thực hoặc test Spring AOP/DB**. Dùng mock HTTP server cố tình trả response sau 300 ms để kiểm tra `HttpTimeoutException`; thử HTTP 500/429, JSON lỗi, `allowed=null`, `validUntil==now`. Với `@SpringBootTest`/`MockMvc`, lấy service qua Spring context và dùng authentication có `AccessPrincipal` thay vì principal chuỗi của `@WithMockUser`. Sau request bị deny/timeout, assert database và event không đổi.

## 12. Concurrency, circuit breaker và vận hành

`HttpClient.send` là lời gọi blocking; nếu PDP chậm, servlet thread có thể bị giữ gần mức timeout. Hệ thống nhiều request cần **bulkhead/concurrency limit**, hàng đợi hữu hạn, rate limit và circuit breaker. Khi breaker OPEN hoặc bulkhead đầy, đường xử lý phải chặn thay vì bypass authorization.

Với WebFlux, không gọi blocking HTTP client trên event-loop; sử dụng client reactive với timeout và truyền SecurityContext đúng Reactor context, hoặc bounded scheduler nếu bắt buộc gọi blocking. Retry phải nằm trong ngân sách request, không tăng tải vô hạn khi PDP lỗi.

Log phân biệt `ALLOW`, `DENY` và `UNAVAILABLE`, nguồn `PDP` hay `CACHE`, action, policy version, decision ID, correlation ID và latency. Bảo vệ thông tin cá nhân, không log token/secret. Metric labels không nên chứa subjectId/resourceId (cardinality cao). Theo dõi p95/p99 PDP latency, timeout ratio, cache hit/miss, stale ALLOW window, revocation lag, circuit breaker OPEN và số lần update xảy ra sau denial (phải bằng 0).

## 13. Ma trận kiểm thử và lỗi thường gặp

| Tình huống | Kỳ vọng |
| --- | --- |
| ALLOW đúng identity/action/tenant | Chỉ tài nguyên trong scope được đọc/sửa |
| PDP DENY | Không chạy method, không ghi/event thành công |
| Thiếu authority chức năng | `@PreAuthorize` chặn dù PDP có thể ALLOW |
| PDP timeout hoặc connection refused | Không có side effect |
| HTTP 500/429, JSON lỗi, body rỗng | Fail closed, không cache ALLOW |
| ALLOW hết `validUntil` | Không dùng cache quá thời điểm này |
| Cùng user nhưng đổi tenant/action/resource | Cache key khác |
| Cache hit trong TTL | Không gọi PDP thêm nếu loại action cho phép cache |
| Revoke với event invalidate | Request sau invalidate hỏi PDP và deny |
| Event thất lạc/in-flight response cũ | Không vượt SLA; action nhạy cảm cần nhất quán mạnh |
| Admin/archiving | Bypass cache, PDP không khả dụng thì deny |
| Cache trống khi breaker OPEN | Deny, không tự động fallback ALLOW |
| Concurrent request lớn | Giới hạn thread, queue và connection |
| Session/JWT còn quyền cũ | Hành vi tuân theo SLA revoke, không mặc định quyền còn sống |
| Không có `@EnableMethodSecurity` | Test phải phát hiện method protection không chạy |
| DB đổi tenant/owner giữa request | Predicate/transaction bảo vệ phạm vi dữ liệu |

Các lỗi điển hình: chỉ đặt connect timeout; cache theo mỗi username; dùng `expireAfterAccess` kéo dài quyền; trả `true` khi PDP lỗi; dùng kết quả HTTP 200 mà không kiểm tra body; bỏ kiểm tra tenant ở SQL; invalidation một node nhưng tưởng đã thu hồi toàn cluster; tin claim revision trong JWT cũ là version mới nhất; tự động ALLOW khi circuit breaker OPEN; test chỉ assert status mà không kiểm tra database.

## 14. Bài tập áp dụng và tiêu chí nghiệm thu

**Bài A — Deadline:** tạo PDP giả trả lời sau 600 ms; request timeout 300 ms. Chứng minh `archive` không được chạy, database không đổi và log phân biệt nguyên nhân unavailable.

**Bài B — Cache isolation:** Alice tenant A đọc 101, Bob tenant A đọc 101, Alice tenant B đọc 101 và Alice tenant A đọc 102. Những key khác nhau phải có quyết định riêng; tăng revision để kiểm tra cache miss.

**Bài C — Thu hồi:** cho Alice đọc 101, revoke ở PDP, phát invalidate, đọc lại và xác nhận deny. Lặp lại không invalidate để đo stale window. Kiểm tra response PDP cũ tới sau invalidate để thấy nhu cầu version fence.

**Bài D — Phân loại rủi ro:** với đọc nội bộ có thể chấp nhận cache ALLOW 2 giây, nhưng archive/admin phải hỏi PDP. Làm PDP down, kiểm tra cache hết hạn không bao giờ được dùng tiếp và mutation không thực hiện.

**Bài E — Vận hành:** đo latency p99, timeout, cache hit và revocation lag trong nhiều instance; điều chỉnh timeout, TTL và concurrency phù hợp SLO. Không tăng TTL cho quyền nhạy cảm chỉ để cải thiện hiệu năng.

**Tiêu chí hoàn thành:** PEP nhận identity từ nguồn xác thực, PDP đánh giá đúng subject/action/resource/scope, timeout hữu hạn, không có fail-open, cache key và expiry đúng, invalidate/race phù hợp SLA, method security thực sự có hiệu lực, DB kiểm tra tenant/owner, test ALLOW/DENY/timeout/revoke và quan sát được trạng thái dữ liệu sau denial.

## Tài liệu tham khảo

- Spring Security — Method Security: https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html
- Spring Security — Authorization Architecture: https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html
- Java SE 17 — HttpClient.Builder: https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.Builder.html
- Java SE 17 — HttpRequest.Builder: https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpRequest.Builder.html
- Caffeine — Eviction: https://github.com/ben-manes/caffeine/wiki/Eviction
- Caffeine — Cleanup: https://github.com/ben-manes/caffeine/wiki/Cleanup
