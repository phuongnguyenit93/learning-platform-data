# Timeout, lỗi mạng, phản hồi không hợp lệ và chính sách từ chối trong Spring Security

## 1. Bối cảnh: chính sách động và tình huống PDP bị lỗi

Một ứng dụng Spring Security có thể dùng `hasAuthority("DOC_READ")` để kiểm tra quyền cơ bản. Nhưng với quy tắc động như “Alice được đọc Document 42 khi cùng tenant, có chia sẻ hiện hành, tài liệu chưa bị khóa và thuộc đúng mức bảo mật”, quyết định có thể cần một **Policy Decision Point (PDP)** từ xa. Thành phần chặn thao tác và gọi PDP gọi là **Policy Enforcement Point (PEP)**.

PDP bình thường có thể trả:

```json
{
  "requestId": "req-42",
  "subject": "alice",
  "tenant": "alpha",
  "resource": "document:42",
  "action": "READ",
  "effect": "PERMIT",
  "policyVersion": 81
}
```

Nếu PDP timeout, mất mạng, trả HTTP 200 với JSON sai, hoặc trả PERMIT **dành cho tenant beta**, hành vi đúng phải là gì?

**Nguyên tắc an toàn:** chỉ một **PERMIT hợp lệ, được xác thực, khớp subject–tenant–resource–action, còn hiệu lực và đúng policy version** mới được cho qua. Không nhận được một PERMIT như vậy thì hành động được bảo vệ **không được thực thi**. Đây là **fail closed**.

Nhưng cần phân biệt:

- **Policy DENY:** PDP đã đánh giá và trả DENY hợp lệ. Caller không có quyền; thường HTTP 403 với caller đã xác thực.
- **Không thể đánh giá policy:** timeout, DNS/TLS/network, circuit breaker OPEN. Không được truy cập, nhưng là vấn đề availability; có thể trả 503/502 theo API contract.
- **Invalid response:** response có cấu trúc, version hoặc binding sai; không được truy cập và cần báo lỗi adapter/PDP.
- **Authentication failure:** caller chưa chứng minh danh tính, thường 401, xảy ra trước khi hỏi PDP.

“Fail closed” **không đồng nghĩa mọi lỗi phải trả 403**. Điều bất biến là **không có side effect, không đọc hoặc trả dữ liệu được bảo vệ khi chưa có quyết định cho phép hợp lệ**.

## 2. Kiến trúc: PEP, PDP, PIP và điểm kiểm tra

```text
HTTP / Method invocation
    |
    v
Spring Security Authentication
    |   subject, issuer, authorities
    v
Local guards
    |   authenticated? tenant? action? resource?
    v
PEP (AuthorizationManager / method guard)
    |
    v
Policy request builder
    |   canonical principal + tenant + resource + action
    v
PDP client (strict timeouts, TLS, bounded retry)
    |
    v
PDP policy engine
    |   policy version, attributes from PIP
    v
Response validator
    |   authenticated source
    |   exact request binding
    |   valid effect, expiry, policy revision, obligations
    v
Typed outcome
    |-- PERMIT_VALID --------> continue with guarded business action
    |-- DENY_POLICY ---------> deny
    |-- UNAVAILABLE_* -------> block action, record operational fault
    |-- INVALID_RESPONSE ----> block action, alert
```

| Thành phần | Công việc |
| --- | --- |
| **Authentication** | Xác minh caller; không tin raw JWT/header |
| **PEP** | Chặn truy cập ngay trước hành động |
| **PDP** | Đánh giá chính sách và trả PERMIT/DENY |
| **PIP** | Cung cấp attributes như membership, owner, classification, resource state |
| **PAP** | Quản trị policy/revision/rollout |
| **Adapter/validator** | Bảo đảm response thực sự thuộc câu hỏi vừa gửi |
| **Failure policy** | Quy định timeout/retry/deny/mapping lỗi |
| **Audit** | Ghi lại decision ID, latency, version và reason code theo chính sách bảo vệ log |

Spring Security sử dụng `AuthorizationManager<T>` cho nhiều điểm kiểm tra, bao gồm request và method authorization. `authorize(Supplier<Authentication>, T)` trả `AuthorizationResult`; `AuthorizationDecision(true/false)` là biểu diễn đơn giản. Giá trị `null` ở một số API có nghĩa **abstain/không đưa ra quyết định**, không phải “từ chối chắc chắn”.

**Không dùng `null` khi PDP hỏng** nếu đây là guard phải đưa quyết định cuối cùng. Hãy trả DENY rõ ràng hoặc ném typed failure mà integration của bạn xử lý an toàn.

## 3. Phân loại decision trước khi chuyển sang boolean

Một `boolean allowed` không đủ để vận hành chính sách động vì mất nguyên nhân. Dùng domain result rõ:

| Outcome | Ý nghĩa | Được làm nghiệp vụ? |
| --- | --- | --- |
| `PERMIT_VALID` | Một PERMIT có nguồn tin, binding, expiry, version và obligations hợp lệ | Có, nếu guard khác cũng đạt |
| `DENY_POLICY` | PDP trả DENY hợp lệ | Không |
| `UNAVAILABLE_TIMEOUT` | Hết thời gian chờ | Không |
| `UNAVAILABLE_NETWORK` | DNS, connection reset/refused, TLS lỗi | Không |
| `UNAVAILABLE_CIRCUIT_OPEN` | Circuit breaker đang chặn PDP calls | Không |
| `INVALID_RESPONSE` | Empty/malformed JSON, sai kiểu, effect không nhận diện | Không |
| `INVALID_BINDING` | Subject, tenant, action, resource hoặc requestId sai | Không |
| `STALE_DECISION` | Quá hạn, policy/entitlement version cũ | Không |
| `UNTRUSTED_RESPONSE` | Không xác thực được source/TLS/signature | Không |
| `UNAUTHENTICATED` | Caller chưa xác thực | Không |

Ba điểm then chốt:

1. Lỗi mạng là **không có quyết định**, chứ không phải policy đã ra quyết định DENY.
2. Không có quyết định thì **không mặc định ALLOW**.
3. Giữ typed outcome cho telemetry và HTTP mapping; tại PEP chỉ `PERMIT_VALID` có thể cho phép action.

Có thể ghi nội bộ một `DecisionReason` riêng; tránh log toàn bộ personal data hoặc policy attributes.

## 4. Fail open là lỗ hổng, fail closed là baseline

Phản ví dụ:

```java
boolean canRead(User user, long documentId) {
    try {
        return policyClient.canRead(user, documentId);
    } catch (Exception ex) {
        return true; // SAI: outage PDP = cấp quyền toàn bộ.
    }
}
```

Nếu attacker gây timeout bằng tải lớn, đường lỗi sẽ trở thành bypass authorization. Một lỗi TLS cũng có thể khiến hệ thống mở quyền.

Hướng fail closed:

```java
boolean canRead(User user, long documentId) {
    try {
        return policyClient.canRead(user, documentId);
    } catch (PdpUnavailableException ex) {
        return false; // Không thực hiện tác vụ được bảo vệ.
    }
}
```

Đây là **snippet tích hợp** (các type `User`/`policyClient`/`PdpUnavailableException` do ứng dụng định nghĩa). Trả false là an toàn về enforcement, nhưng dễ sinh HTTP 403 kể cả khi PDP outage. Với hệ thống cần 503, nên dùng typed exception/outcome và mapping ở **đúng ranh giới security filter/service**, tuyệt đối vẫn chặn business action.

### Không biến availability thành ngoại lệ “permitAll”

Một health endpoint công khai có thể được cấu hình `permitAll()` vì **policy định nghĩa nó public**. Nó không liên quan đến việc PDP hỏng. Với tài nguyên private, không tạm mở `permitAll()` toàn tuyến để giảm 403.

Nếu kiến trúc có local policy bundle được ký hoặc short-lived capability được verify độc lập, đó có thể là nguồn PERMIT hợp lệ khi remote PDP unavailable **chỉ khi** TTL, scope, issuer, audience, revocation SLA và policy version đều được thiết kế từ đầu. “Last-known PERMIT vô hạn” không phải fallback an toàn.

## 5. Timeout: xác định deadline từ đầu đến cuối

Một policy check từ xa có nhiều thời gian chờ:

- Lấy slot từ HTTP connection pool.
- DNS lookup và TCP connect.
- TLS handshake.
- Gửi request body.
- Chờ response headers/first byte.
- Đọc toàn body.
- Parse JSON, validate binding, expiry/version.
- Thực thi obligations bắt buộc.

Chỉ đặt connect timeout là không đủ nếu server nhận TCP nhưng không phản hồi. Chỉ đặt per-attempt timeout cũng không đủ nếu một request được retry liên tục.

Ví dụ **budget minh họa**, không phải cấu hình khuyến nghị cho mọi hệ thống:

```text
API request deadline:       1000 ms
Other application work:      350 ms
Reserve:                     150 ms
PDP overall budget:          500 ms
  connect timeout:           120 ms
  response timeout:          280 ms
  retry/backoff reserve:     phần còn lại
```

Bất biến:

```text
attempt time + backoff + retry + validation
    <= remaining PDP deadline
PDP deadline <= remaining caller/request deadline
```

Nếu hết deadline, **không chờ vô hạn và không làm tiếp protected operation**. Sau khi call bị cancel, một response PERMIT đến muộn không được dùng để tiếp tục thao tác đã bị hủy.

### Quy tắc khi bị interrupt

Java blocking client có thể ném `InterruptedException`. Đừng nuốt interrupt rồi retry vô hạn:

```java
try {
    return client.send(request, HttpResponse.BodyHandlers.ofString());
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    throw new PolicyCheckInterruptedException(ex);
}
```

Đây là snippet tích hợp, `PolicyCheckInterruptedException` do app định nghĩa. Phần code cần import `HttpResponse` và có `client`, `request` được tạo đúng.

## 6. Lỗi HTTP/network/TLS không phải policy DENY hợp lệ

Các lỗi phổ biến: DNS failure, connection refused, connection reset, read timeout, TLS untrusted certificate, hostname mismatch, reverse proxy trả HTML 502, PDP 503, service credential sai nên PDP nhận 401.

| Trạng thái | Phân loại phù hợp | Xử lý |
| --- | --- | --- |
| HTTPS 200 + body hợp lệ | Có thể xét decision | Validate toàn bộ rồi mới PERMIT/DENY |
| 200 nhưng body rỗng | INVALID_RESPONSE | Không cho phép |
| 200 nhưng JSON sai schema | INVALID_RESPONSE | Không cho phép |
| 204 | Không có decision | Không cho phép |
| 3xx redirect lạ | Transport/protocol error | Không tự follow sang host không tin cậy |
| 401/403 từ gateway PDP | Service credential/config error | Không tự coi là policy DENY nếu protocol không định nghĩa |
| 408, 429, 502, 503, 504 | Unavailable/transient tùy contract | Không cho phép; retry có điều kiện |
| 5xx khác | Unavailable/internal PDP error | Không cho phép |
| DNS/TCP/TLS/timeout | Transport failure | Không cho phép, đo metrics |

**Không đồng nhất HTTP 403 từ endpoint PDP với JSON `effect=DENY`.** 403 có thể do chính tài khoản service gọi PDP bị chặn; một decision protocol cần xác định response hợp lệ của PDP là gì.

**Không tắt TLS certificate validation** để “chữa lỗi PDP” vì khi đó một actor trung gian có thể phát response `PERMIT` giả.

## 7. Kiểm tra nguồn phản hồi và tính gắn kết request

Response minh họa:

```json
{
  "requestId": "r-123",
  "decisionId": "d-77",
  "effect": "PERMIT",
  "subject": "issuerA:alice",
  "tenant": "alpha",
  "resource": "document:42",
  "action": "READ",
  "policyVersion": 81,
  "issuedAt": "2026-11-05T03:00:00Z",
  "expiresAt": "2026-11-05T03:00:02Z"
}
```

Đây là **contract ví dụ**, không phải schema bắt buộc của mọi policy engine. Adapter của từng PDP phải map đúng.

### Checklist validate trước PERMIT

1. Kênh response được xác thực (TLS/mTLS với server trust và hostname check, hoặc chữ ký phù hợp).
2. HTTP status, content-type, body size đúng contract.
3. JSON parse thành đúng một object, không bị truncate.
4. Các trường bắt buộc có mặt, đúng kiểu, không được silent coercion.
5. `effect` chỉ nhận chính xác `PERMIT`/`DENY` theo protocol.
6. `requestId`/nonce đúng câu hỏi này, chống lẫn response/replay.
7. `subject` đúng identity đã xác minh, gồm issuer nếu `sub` không duy nhất toàn hệ thống.
8. `tenant` đúng tenant đã authorize, không phải raw header/path client.
9. `resource` đúng canonical type/id của đối tượng trong server.
10. `action` đúng thao tác sẽ thực hiện (READ không bao hàm DELETE).
11. `policyVersion` đúng hoặc lớn hơn floor mà caller yêu cầu.
12. `issuedAt`/`expiresAt` hợp lý theo policy clock skew/TTL.
13. Attributes/entitlement version phù hợp nếu được đưa vào policy request.
14. Mọi **obligation bắt buộc** được hiểu và có thể thực thi.

Một response `PERMIT` cho tenant beta khi caller ở alpha là **INVALID_BINDING**, không phải allow. Tương tự một response cho resource khác hoặc action khác phải bị từ chối.

### Không dùng chuỗi “truthy” hoặc default allow

```java
// SAI: bất cứ effect nào khác DENY đều được cấp quyền.
boolean allow = !"DENY".equals(effect);

// SAI: body không null không phải bằng chứng authorization.
boolean allow = httpResponse.body() != null;

// ĐÚNG HƯỚNG: chỉ PERMIT của một validated decision.
boolean allow = validated.effect() == Effect.PERMIT;
```

Các đoạn trên là snippets, `Effect`/`validated` phải là typed decision sau khi validator hoàn tất.

### JSON ambiguity

Response sau không được coi là một quyết định rõ:

```json
{"effect":"DENY","effect":"PERMIT"}
```

Nếu parser chấp nhận duplicate keys và lấy phần tử cuối, attacker hoặc lỗi server có thể thay đổi semantics. Với policy-critical JSON, reject duplicate keys hoặc xử lý đúng schema contract nghiêm ngặt. Tương tự không chuyển `"true"`, `1` hoặc `"yes"` thành PERMIT nếu protocol quy định enum string.

## 8. Policy DENY và lỗi xác thực endpoint phải tách biệt

Ví dụ Alice thực sự không được phép:

```text
PDP authenticated
  -> parse response
  -> match subject/tenant/resource/action
  -> effect DENY
  -> DENY_POLICY
```

Đây là một quyết định bình thường: không cần retry để “kiếm PERMIT”, không đánh dấu PDP unhealthy.

Ngược lại:

```text
PDP timeout          -> UNAVAILABLE_TIMEOUT
PDP connection reset -> UNAVAILABLE_NETWORK
JSON missing effect  -> INVALID_RESPONSE
Version 79 < min 81  -> STALE_DECISION
TLS hostname invalid -> UNTRUSTED_RESPONSE
```

Các outcome lỗi đều **chặn action**, nhưng nên có status/metrics riêng để vận hành.

### HTTP mapping gợi ý

| Tình huống | HTTP API gợi ý |
| --- | --- |
| Không có authentication | 401 |
| DENY_POLICY hợp lệ | 403 hoặc 404 theo API privacy contract |
| Timeout/circuit open | 503, đôi khi 502/504 theo gateway design |
| Invalid PDP response | 502/503 hoặc lỗi nội bộ trung tính |
| Request input không hợp lệ | 400 |
| Policy local DENY chắc chắn | 403 |

Trong Spring Security, nếu manager trả `new AuthorizationDecision(false)`, `AuthorizationFilter` và exception translation thường dẫn tới 403 cho caller đã xác thực. Nếu muốn 503 cho PDP unavailable, **không chỉ thêm `@RestControllerAdvice` rồi tưởng mọi exception từ security filter đều được bắt**. Phải xử lý tại ranh giới filter/authorization hoặc trong service boundary mà controller handler thực sự quản lý; kiểm thử với `MockMvc`.

## 9. Retry có giới hạn, không retry mọi thứ

Retry có thể có ích cho transient network failures, nhưng một hệ thống 1000 request/s với 3 extra retries có thể đẩy PDP từ 1000 lên 4000 calls/s và làm outage trầm trọng hơn.

Quy tắc:

- Chỉ retry những tình huống transient đã được phân loại: connection reset, 503/429 theo contract, một số timeout.
- Không retry `DENY_POLICY`.
- Không retry response mismatch/TLS untrusted/malformed schema để hy vọng lần sau cấp quyền.
- Chỉ retry policy **evaluation idempotent**; không tự retry mutation nghiệp vụ (chuyển tiền, phê duyệt) vì policy call timeout.
- Giới hạn attempts (ví dụ tối đa 2 tổng lần gọi) và overall deadline.
- Backoff có jitter để tránh đồng bộ burst.
- Tôn trọng `Retry-After` nếu provider hỗ trợ, nhưng không vượt deadline.
- Đừng thay đổi subject/action/resource giữa retries.
- Khi request đã cancel, đừng tiếp tục retry hoặc xử lý business action.

Một retry có thể nhận policy mới so với lần đầu do membership thay đổi; đây là lý do phải validate policy revision và xử lý state changes theo consistency contract, không chỉ đọc effect.

## 10. Circuit breaker và bulkhead

Circuit breaker giúp bảo vệ resources khi PDP lỗi liên tiếp:

```text
CLOSED -> gọi PDP, đo lỗi/độ trễ
   |
   v
OPEN -> không gọi PDP, trả UNAVAILABLE_CIRCUIT_OPEN
   |
   v
HALF_OPEN -> cho một số probes có giới hạn
   | healthy              | still failing
   v                      v
CLOSED                   OPEN
```

**Circuit OPEN không phải PERMIT.** Nếu code có fallback “circuit open thì bỏ PDP”, đó là bypass.

Resilience4j hỗ trợ `CircuitBreaker`, `Retry`, `TimeLimiter`, `Bulkhead`. Theo tài liệu, CircuitBreaker không tự giới hạn số calls đồng thời; phải thêm Bulkhead khi cần concurrency isolation.

Các điểm cấu hình:

- Per-cluster/endpoint breakers đủ để cô lập hỏng hóc, không tạo một breaker cho mỗi arbitrary key client.
- Threshold theo failure rate và slow calls; đừng coi `DENY_POLICY` là transport failure.
- OPEN trả failure type, không dùng `cached PERMIT` quá hạn.
- HALF_OPEN probes cũng phải đi qua validator; PERMIT từ probe sai schema vẫn là lỗi.
- Rejection do bulkhead/pool full là unavailable, không biến thành allow.
- Có metrics alert về breaker state và số requests bị chặn.

## 11. Cache quyết định: key, TTL và thu hồi quyền

Một cached authorization decision phải gắn với:

```text
issuer + canonical subject
tenant
resource type + canonical resource ID
action
attributes / resource version có ảnh hưởng
policy version + entitlement version
authentication assurance nếu policy dùng
decision issuedAt / expiresAt
```

**Cache theo resourceId đơn lẻ là sai:** Alice có quyền trên document 42 không có nghĩa Bob có quyền. Cache theo tenant cũng chưa đủ nếu mỗi user có owner/share khác nhau.

### Có được dùng cached PERMIT khi PDP không sẵn sàng?

Chỉ khi đó là **một PERMIT còn hạn và hợp lệ theo hợp đồng** với TTL, policy version, revocation SLA, key đúng scope và nguồn tin cậy. Nếu expiry đã qua hoặc membership đã bị revoke, không được kéo dài hiệu lực chỉ để giữ availability.

Phân biệt:

- Cache `DENY_POLICY` hợp lệ có thể chấp nhận trong thời gian ngắn theo policy.
- Cache `UNAVAILABLE_TIMEOUT` như một DENY vĩnh viễn là sai semantics/monitoring.
- Cache `INVALID_RESPONSE` thành allow là nghiêm trọng.
- Quyền đổi cần invalidation hoặc version bump; với revocation tức thời, có thể phải bỏ cache positive quyết định.

### Local policy bundle

Một policy engine local có bundle được ký/versioned có thể giúp phục vụ offline. Tuy vậy, nếu bundle cũ hơn minimum required revision hoặc không biết membership mới bị revoke, local PERMIT có thể không đạt policy. Cần kiểm tra version floor và cơ chế cập nhật, không chỉ “bundle đang có file là dùng được”.

## 12. Java 17 runnable: mô phỏng toàn bộ nhánh lỗi quan trọng

Ví dụ này **không cần Spring, Maven hay Internet**. Nó mô phỏng một PDP transport adapter có các trường hợp timeout, IOException, reply rỗng, sai effect, sai tenant/resource/requestId, stale version, expiry và nguồn không tin cậy. Một boolean `sourceVerified` trong ví dụ mô phỏng **kết quả của TLS/signature verifier phía client**, không phải field client/PDP JSON tự khai để được tin.

Tệp `PdpFailureLab.java`:

```java
import java.io.IOException;
import java.util.Objects;
import java.util.concurrent.TimeoutException;

public final class PdpFailureLab {

    record Query(
            String requestId,
            String subject,
            String tenant,
            String resource,
            String action,
            long minPolicyVersion) {}

    record Reply(
            String requestId,
            String subject,
            String tenant,
            String resource,
            String action,
            String effect,
            long policyVersion,
            long expiresAtMillis,
            boolean sourceVerified) {}

    enum Scenario {
        ALLOW,
        POLICY_DENY,
        TIMEOUT,
        NETWORK_ERROR,
        EMPTY_REPLY,
        UNKNOWN_EFFECT,
        WRONG_TENANT,
        WRONG_RESOURCE,
        WRONG_REQUEST_ID,
        STALE_POLICY,
        EXPIRED,
        UNTRUSTED_SOURCE
    }

    enum Outcome {
        PERMIT,
        DENY_POLICY,
        DENY_TIMEOUT,
        DENY_NETWORK,
        DENY_INVALID
    }

    private PdpFailureLab() {}

    private static Reply valid(Query q, String effect) {
        return new Reply(
                q.requestId(), q.subject(), q.tenant(),
                q.resource(), q.action(), effect,
                7L, 2_000L, true);
    }

    private static Reply remote(Query q, Scenario scenario)
            throws IOException, TimeoutException {
        return switch (scenario) {
            case ALLOW -> valid(q, "PERMIT");
            case POLICY_DENY -> valid(q, "DENY");
            case TIMEOUT -> throw new TimeoutException("Simulated timeout");
            case NETWORK_ERROR -> throw new IOException("Simulated network error");
            case EMPTY_REPLY -> null;
            case UNKNOWN_EFFECT -> valid(q, "MAYBE");
            case WRONG_TENANT -> new Reply(
                    q.requestId(), q.subject(), "beta",
                    q.resource(), q.action(), "PERMIT",
                    7L, 2_000L, true);
            case WRONG_RESOURCE -> new Reply(
                    q.requestId(), q.subject(), q.tenant(),
                    "document:999", q.action(), "PERMIT",
                    7L, 2_000L, true);
            case WRONG_REQUEST_ID -> new Reply(
                    "other-request", q.subject(), q.tenant(),
                    q.resource(), q.action(), "PERMIT",
                    7L, 2_000L, true);
            case STALE_POLICY -> new Reply(
                    q.requestId(), q.subject(), q.tenant(),
                    q.resource(), q.action(), "PERMIT",
                    6L, 2_000L, true);
            case EXPIRED -> new Reply(
                    q.requestId(), q.subject(), q.tenant(),
                    q.resource(), q.action(), "PERMIT",
                    7L, 900L, true);
            case UNTRUSTED_SOURCE -> new Reply(
                    q.requestId(), q.subject(), q.tenant(),
                    q.resource(), q.action(), "PERMIT",
                    7L, 2_000L, false);
        };
    }

    private static Outcome decide(
            Query q, Scenario scenario, long nowMillis) {
        try {
            Reply r = remote(q, scenario);

            if (r == null || !r.sourceVerified()
                    || !Objects.equals(r.requestId(), q.requestId())
                    || !Objects.equals(r.subject(), q.subject())
                    || !Objects.equals(r.tenant(), q.tenant())
                    || !Objects.equals(r.resource(), q.resource())
                    || !Objects.equals(r.action(), q.action())
                    || r.policyVersion() < q.minPolicyVersion()
                    || r.expiresAtMillis() <= nowMillis) {
                return Outcome.DENY_INVALID;
            }

            return switch (r.effect()) {
                case "PERMIT" -> Outcome.PERMIT;
                case "DENY" -> Outcome.DENY_POLICY;
                default -> Outcome.DENY_INVALID;
            };
        } catch (TimeoutException ex) {
            return Outcome.DENY_TIMEOUT;
        } catch (IOException ex) {
            return Outcome.DENY_NETWORK;
        }
    }

    public static void main(String[] args) {
        Query query = new Query(
                "req-001", "alice", "alpha",
                "document:42", "READ", 7L);

        for (Scenario scenario : Scenario.values()) {
            System.out.println(
                    scenario + "=" + decide(query, scenario, 1_000L));
        }
    }
}
```

Lệnh chạy với JDK 17+:

```bash
javac PdpFailureLab.java
java PdpFailureLab
```

Stdout chính xác theo logic chương trình:

```text
ALLOW=PERMIT
POLICY_DENY=DENY_POLICY
TIMEOUT=DENY_TIMEOUT
NETWORK_ERROR=DENY_NETWORK
EMPTY_REPLY=DENY_INVALID
UNKNOWN_EFFECT=DENY_INVALID
WRONG_TENANT=DENY_INVALID
WRONG_RESOURCE=DENY_INVALID
WRONG_REQUEST_ID=DENY_INVALID
STALE_POLICY=DENY_INVALID
EXPIRED=DENY_INVALID
UNTRUSTED_SOURCE=DENY_INVALID
```

**Giải thích:**

- `ALLOW` có PERMIT, binding đúng, version 7 và expiry=2000 > now=1000.
- `POLICY_DENY` là quyết định từ chối hợp lệ, không phải mạng lỗi.
- `TIMEOUT`/`NETWORK_ERROR` bị chặn nhưng được phân loại riêng.
- `EMPTY_REPLY` mô phỏng adapter không thu được decision object.
- `UNKNOWN_EFFECT` bị reject vì “MAYBE” không phải giá trị hợp lệ.
- `WRONG_TENANT/RESOURCE/REQUEST_ID` ngăn cấp quyền từ response thuộc request khác.
- `STALE_POLICY` trả version 6, nhỏ hơn required version 7.
- `EXPIRED` trả expiry=900, không còn hiệu lực ở now=1000.
- `UNTRUSTED_SOURCE` giả lập việc TLS/signature/source verification thất bại.

**Giới hạn:** demo không parse JSON thật, không mở socket, không kiểm tra chữ ký TLS, không chứa Spring Security. Nó cố ý tách state machine/validation rule ra để nhìn rõ invariant; production cần adapter JSON/TLS/clock/attributes/obligations thật. Không dùng thời gian hay version hardcoded như trong demo khi triển khai.

## 13. Spring Security AuthorizationManager: nối strict policy gate vào HTTP

Trong Spring Security 6.4+ có `AuthorizationManager<T>.authorize` trả `AuthorizationResult`, và có thể dùng `AuthorizationDecision`. Đoạn dưới minh họa manager bắt buộc ra quyết định ở một endpoint:

```java
import java.util.function.Supplier;

import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.authorization.AuthorizationResult;
import org.springframework.security.core.Authentication;
import org.springframework.security.web.access.intercept.RequestAuthorizationContext;

final class RemoteDocumentAuthorizationManager
        implements AuthorizationManager<RequestAuthorizationContext> {

    private final DocumentPolicyGate policyGate;

    RemoteDocumentAuthorizationManager(DocumentPolicyGate policyGate) {
        this.policyGate = policyGate;
    }

    @Override
    public AuthorizationResult authorize(
            Supplier<Authentication> authentication,
            RequestAuthorizationContext context) {

        Authentication current = authentication.get();
        if (current == null || !current.isAuthenticated()
                || current instanceof AnonymousAuthenticationToken) {
            return new AuthorizationDecision(false);
        }

        String requestedTenant = context.getVariables().get("tenant");
        String id = context.getVariables().get("id");

        if (requestedTenant == null || id == null) {
            return new AuthorizationDecision(false);
        }

        // Policy gate xác minh membership, canonical resource tenant,
        // local authority, response PERMIT, binding và expiry.
        PolicyOutcome result =
                policyGate.checkRead(current, requestedTenant, id);

        // Mọi lỗi và mọi DENY đều tạo negative decision.
        return new AuthorizationDecision(
                result == PolicyOutcome.PERMIT_VALID);
    }
}
```

`DocumentPolicyGate` và `PolicyOutcome` là abstractions nghiệp vụ của dự án, **không phải class Spring dựng sẵn**. Gate phải trả PERMIT_VALID **chỉ** sau khi đã kiểm tra tất cả điều kiện, và phải biến timeout/invalid reply thành non-permit (hoặc typed operational error được xử lý ở security boundary).

Nối vào filter chain:

```java
@Bean
SecurityFilterChain apiFilter(
        HttpSecurity http,
        RemoteDocumentAuthorizationManager remoteManager)
        throws Exception {

    http.authorizeHttpRequests(auth -> auth
            .requestMatchers(
                HttpMethod.GET,
                "/api/tenants/{tenant}/documents/{id}"
            ).access(remoteManager)
            .anyRequest().denyAll());

    return http.build();
}
```

Cần các imports `@Bean`, `HttpSecurity`, `HttpMethod` và `SecurityFilterChain`; đây là **snippet tích hợp**, cần authentication mechanism, Spring context, policy gate và controller. `RequestAuthorizationContext.getVariables()` có path variables khi matcher tương ứng trích xuất; path variables vẫn là **input chưa được ủy quyền**. Phải kiểm tra tenant membership và resource thuộc tenant thực tế, không chỉ copy `{tenant}` vào PDP request.

### Nếu cần phân biệt 403 với 503

Adapter ví dụ ở trên trả `AuthorizationDecision(false)` cho mọi non-permit nên Spring Security sẽ xử lý qua đường AccessDenied, thông thường HTTP 403 cho caller đã xác thực. Nếu PDP unavailable cần HTTP 503, thiết kế exception mapping tại filter/authorization boundary phù hợp hoặc một application policy gate chạy trước mutation dưới handler có kiểm soát, và kiểm thử response thật. Không để việc map 503 vô tình bỏ qua authorization guard.

**Không dùng `return null` khi timeout.** Với manager bắt buộc, đó không phải DENY tường minh, và composition semantics dễ gây bất ngờ.

## 14. Local guard và dynamic PDP phải kết hợp đúng

Giả sử được đọc nếu caller authenticated **và** thuộc tenant **và** có role cơ bản **và** PDP PERMIT:

```text
allowed =
  authenticated
  AND tenantMembershipValid
  AND resourceTenantMatches
  AND hasLocalAuthority
  AND validRemotePermit
  AND mandatoryObligationsSatisfied
```

Phản ví dụ:

```java
boolean allowed = hasAuthority || pdpAllowed; // SAI nếu policy yêu cầu đủ hai.
```

Điều kiện đúng:

```java
boolean allowed = authenticated
        && tenantMembershipValid
        && resourceTenantMatches
        && hasAuthority
        && remotePermitValid
        && obligationsSatisfied;
```

Các biến là kết quả policy đã xác minh, không lấy từ request body client. Có thể short-circuit các local deny chắc chắn trước khi gọi remote PDP để giảm độ trễ và hạn chế attributes nhạy cảm gửi ra ngoài. Nhưng local pass không có nghĩa cho phép nếu dynamic PDP bắt buộc.

### Tránh time-of-check/time-of-use

Remote PDP PERMIT tại T1 không tự chứng minh tài liệu vẫn thuộc tenant đó tại T2. Khi có mutation nhạy cảm, dùng conditional SQL/transaction/version checks:

```sql
UPDATE documents
SET status = 'APPROVED'
WHERE id = :document_id
  AND tenant_id = :authorized_tenant
  AND owner_id = :authenticated_subject
  AND status = 'PENDING'
  AND version = :expected_version;
```

Kiểm tra affected rows bằng 1. Nếu resource đổi trạng thái giữa authorization và update, không dùng PERMIT cũ để bypass race. Tùy nghiệp vụ phải re-evaluate trên snapshot mới.

## 15. Response obligations: có PERMIT nhưng vẫn chưa thể thực hiện

PDP có thể trả PERMIT kèm yêu cầu:

```json
{
  "effect": "PERMIT",
  "obligations": [
    {"type": "MASK_FIELD", "field": "salary"},
    {"type": "AUDIT", "level": "SENSITIVE"}
  ]
}
```

Nếu ứng dụng không hỗ trợ `MASK_FIELD` mà vẫn gửi salary nguyên bản, thì PERMIT đã bị diễn giải sai. Policy gate phải kiểm tra một obligation bắt buộc có thể được thực thi; nếu không, **deny/invalid**. Obligations có thể bao gồm bắt buộc MFA, audit, watermark, redact, rate-limit hoặc resource conditions.

Không lấy một trường `obligations` rỗng khi parser bỏ qua unknown fields rồi giả định tất cả điều kiện đã đạt. Schema/version của obligations cần test như effect.

### Data minimization

Không gửi nguyên access token, password, private document body hoặc PII không cần thiết cho PDP. Gửi canonical subject/tenant/resource attributes tối thiểu, qua transport bảo vệ. Audit/logs dùng decision ID và reason code, không log toàn bộ payload nhạy cảm.

## 16. Java 17 HttpClient: transport là một tầng, policy validator là tầng khác

Mẫu transport JDK 17 (snippet **tích hợp**, cần `jsonBody` đã serialize từ trusted request):

```java
HttpClient client = HttpClient.newBuilder()
        .connectTimeout(Duration.ofMillis(150))
        .followRedirects(HttpClient.Redirect.NEVER)
        .build();

HttpRequest request = HttpRequest.newBuilder()
        .uri(URI.create("https://pdp.internal.example/check"))
        .timeout(Duration.ofMillis(300))
        .header("Content-Type", "application/json")
        .POST(HttpRequest.BodyPublishers.ofString(jsonBody))
        .build();

HttpResponse<String> response = client.send(
        request, HttpResponse.BodyHandlers.ofString());
```

Imports tương ứng: `java.net.URI`, `java.net.http.HttpClient`, `HttpRequest`, `HttpResponse`, `java.time.Duration`.

Các cảnh báo:

- PDP URI từ config allowlist, **không từ header/URL client** để tránh SSRF.
- Không auto-follow redirect đến endpoint lạ.
- Không disable TLS/hostname verification.
- `response.statusCode() == 200` mới là điều kiện transport đầu tiên; còn cần strict JSON parse và binding.
- `send` có thể ném `IOException`/`InterruptedException`; phân loại, bảo toàn interrupt và fail closed.
- Đừng lấy connect timeout=150ms và request timeout=300ms như thông số phổ quát; đo theo SLO.

Với Spring `RestClient`/`WebClient`, cần cấu hình connect/response timeout ở HTTP client cụ thể và test thực tế. Trong reactive, nhớ tổng budget/deadline và tránh blocking calls trên event loop.

## 17. Batch policy decisions và phản hồi thiếu item

PDP có thể trả nhiều quyết định:

```json
{
  "requestId": "batch-01",
  "results": [
    {"resource":"document:41","effect":"PERMIT"},
    {"resource":"document:42","effect":"DENY"}
  ]
}
```

Nếu request hỏi 3 resources mà response chỉ có 2, **item thiếu không được mặc định PERMIT**. Kiểm tra:

- Mỗi resource/action trong response thuộc request; không có extras.
- Không duplicate resource ID có outcomes mâu thuẫn.
- Không gán nhầm dựa trên thứ tự array khi provider không bảo đảm thứ tự.
- Các item đều có binding đúng subject, tenant, expiry, policy version.
- All-or-nothing operations cần tất cả requested items PERMIT trước khi mutate; còn partial success phải là contract rõ ràng, báo per-item results.
- Các item cross-tenant phải được authorize riêng, không chỉ dùng một tenant ID chung.

Ví dụ policy all-of ở tầng adapter **sau khi đã validate map**:

```java
boolean allPermitted = !requestedIds.isEmpty()
        && requestedIds.stream().allMatch(id ->
                validatedById.containsKey(id)
                && validatedById.get(id) == Effect.PERMIT);
```

`validatedById` phải là map đã được kiểm tra schema, duplicates và binding, không phải raw JSON. Điều kiện `!requestedIds.isEmpty()` tránh `Stream.allMatch` trả true trên stream rỗng nếu business không cho batch empty.

## 18. Observability: đừng gộp mọi lỗi thành 403

Audit event ví dụ:

```json
{
  "event": "policy_decision",
  "requestId": "req-001",
  "decisionId": null,
  "actorRef": "opaque-actor-id",
  "tenantAlias": "tenant-a",
  "action": "READ",
  "resourceType": "document",
  "outcome": "UNAVAILABLE_TIMEOUT",
  "durationMillis": 302,
  "policyVersion": null,
  "pdpCluster": "zone-a"
}
```

Tùy hệ thống, actorRef/tenantAlias vẫn có thể là dữ liệu cá nhân và cần kiểm soát truy cập log.

Metrics hữu ích:

| Metric | Lý do |
| --- | --- |
| `pdp_checks_total{outcome}` | Tách PERMIT, DENY_POLICY, TIMEOUT, INVALID, CIRCUIT_OPEN |
| `pdp_duration_seconds` | Theo dõi latency percentiles |
| `pdp_retry_total` | Phát hiện retry storms |
| `pdp_circuit_state` | Biết OPEN/HALF_OPEN/CLOSED |
| `pdp_invalid_response_total{reason}` | Phát hiện lỗi schema/binding/version |
| `pdp_tls_error_total` | Chẩn đoán trust store và certificate |
| `policy_revision_lag` | Phát hiện PDP/cache policy bundle stale |
| `authorization_unavailable_total` | Số requests bị chặn vì PDP outage |

Tránh gắn requestId, subjectId, documentId vào **metric labels** vì cardinality lớn và rủi ro lộ dữ liệu. Dùng traces/logs có quyền truy cập phù hợp. Client nhận thông báo trung tính, không tiết lộ tài liệu có tồn tại hay policy nội bộ.

## 19. Bộ kiểm thử lỗi: nên có trường hợp thành công và toàn bộ đường lỗi

| Trường hợp | Expected enforcement |
| --- | --- |
| PERMIT đúng caller/tenant/resource/action/version/expiry | Được tiếp tục nếu local guard khác đạt |
| DENY hợp lệ | Không vào business method |
| Connect timeout | Không vào business method |
| Response timeout | Không vào business method |
| Connection refused/reset | Không vào business method |
| DNS failure | Không vào business method |
| Untrusted TLS certificate/hostname | Không vào business method |
| 200 nhưng body rỗng | Không vào business method |
| 200 nhưng JSON malformed | Không vào business method |
| JSON có duplicate effect keys | Reject/deny |
| Effect null/unknown/bool/string "true" | Reject/deny |
| Wrong subject | Reject/deny |
| Wrong tenant | Reject/deny |
| Wrong resource ID/type | Reject/deny |
| Wrong action | Reject/deny |
| Wrong requestId/nonce | Reject/deny |
| Reply expired | Reject/deny |
| Policy version quá cũ | Reject/deny |
| PERMIT có obligation chưa hỗ trợ | Reject/deny |
| PDP trả 401/403 do service credential | Không coi là user PERMIT/DENY hợp lệ |
| Circuit OPEN | Không gọi PDP, vẫn block nghiệp vụ |
| Retry hết attempts/deadline | Không chạy business operation |
| Cache có PERMIT của user khác | Cache key test phát hiện, không cho dùng |
| Membership/ACL vừa bị revoke | Không dùng cached positive stale |
| Batch thiếu item | Không tự grant item thiếu |
| Request cancelled | Không tiếp tục mutation |
| Resource thay đổi version trước UPDATE | Conditional update 0 rows; không coi success |

**Test cần assert side effect bằng 0** cho các đường fail, không chỉ nhìn HTTP code. Một controller có thể đã update DB rồi mới ném exception.

### Fault injection tầng HTTP

Dùng WireMock/MockWebServer hoặc một stub HTTP server thích hợp để mô phỏng slow response, reset socket, body truncated, 200 HTML, mismatched IDs, 503, TLS cert sai, circuit open. Unit test chỉ mock `policyGate.check()` trả false không chứng minh transport/parsing/deadline thực.

### Integration qua Spring Security

`@SpringBootTest`, `@AutoConfigureMockMvc` và `@WithMockUser` có thể kiểm tra endpoint matcher và manager. Với manager ở mục 13, timeout được ánh xạ thành `AuthorizationDecision(false)` nên caller đã xác thực thường nhận 403. Nếu dự án chọn typed operational error/503, test status phải tương ứng.

`@WithMockUser` không kiểm chứng JWT signature/issuer/audience. Nếu app là Resource Server, thêm test decoder/security filter với token thật được ký bằng test key, ngoài các mock auth tests.

## 20. Runbook khi PDP outage hoặc deploy sai schema

### Khi timeout/network tăng

1. Xác nhận `UNAVAILABLE_TIMEOUT`/`UNAVAILABLE_NETWORK` tăng, tách khỏi DENY_POLICY.
2. Xác định PDP cluster, endpoint/certificate, DNS, gateway, service credential và policy backend.
3. Kiểm tra deadlines, connection pool, thread pool saturation, retry rate, circuit state.
4. Không bật `permitAll()` trên protected routes.
5. Kích hoạt redundancy/local verified bundle nếu kiến trúc đã thiết kế.
6. Đo canary PERMIT và DENY hợp lệ sau khi dịch vụ hồi phục.
7. Xác nhận không có side effect xảy ra trong outage.
8. Đánh giá incident security nếu thấy đường fail-open.

### Khi INVALID_RESPONSE tăng

- Có thể client/server không tương thích schema, content-type bị thay, proxy trả HTML 200 hoặc policy version không khớp.
- Kiểm tra parser strict/duplicate keys, response signature, binding và obligations.
- Dùng canary với ALLOW, DENY, invalid response; không “chữa” bằng cách bỏ validation.
- Rollback/forward-fix protocol theo kế hoạch tương thích, giữ audit.
- Không coi tăng INVALID_RESPONSE là user tự nhiên thiếu quyền.

### Khi thu hồi quyền

- Invalidate cached PERMIT liên quan hoặc tăng entitlement/policy revision.
- Cập nhật bundle và xác nhận mọi instances biết version floor.
- Với background jobs, reauthorize lúc execute nếu policy yêu cầu.
- Kiểm tra TOCTOU và conditional writes.
- Theo dõi các quyết định PERMIT stale, nếu có thì điều tra.

## 21. Những anti-pattern nguy hiểm

**1. `catch (Exception) return true`:** PDP chết trở thành đường mở quyền.

**2. `HTTP 200 = PERMIT`:** chưa kiểm tra decision content.

**3. `if (effect != "DENY") allow`:** response null/unknown thành allow.

**4. `AuthorizationManager` trả null khi timeout:** abstain không phải deny tường minh.

**5. Không đặt request/read deadline:** pool bị chiếm, dễ DoS.

**6. Retry cả DENY_POLICY:** không có ý nghĩa, tăng tải và tạo kết quả không ổn định.

**7. Fallback `permitAll` hoặc stale PERMIT không giới hạn:** vi phạm revocation.

**8. Cache theo resourceId:** rò quyền giữa users/tenants.

**9. Chỉ kiểm tra effect, không kiểm tra subject/tenant/action/resource:** reply khác request có thể cấp nhầm quyền.

**10. Không verify TLS/source:** attacker có thể trả JSON PERMIT giả.

**11. Bỏ qua obligations:** PERMIT có điều kiện trở thành PERMIT vô điều kiện.

**12. Log raw JWT, policy request/response nhạy cảm:** lộ secrets/PII.

**13. Đưa PDP URL/policy revision từ input client:** dễ SSRF, bypass/downgrade.

**14. Gộp transport 403 với policy DENY:** metrics và incident triage sai.

**15. Kiểm tra PDP sau mutation:** policy DENY không hoàn tác side effects đã thực hiện.

**16. Một PERMIT cho document cũ dùng sau khi resource đổi owner/tenant/version:** TOCTOU.

**17. Không giới hạn batch response IDs:** lẫn kết quả hoặc bỏ qua item.

**18. Metrics chỉ đo tổng 403:** outage/schema faults bị che.

**19. Một service credential platform ADMIN cho mọi tenant mà không authorize requested scope:** confused deputy.

**20. Thử tăng retry/timeouts vô hạn để “đỡ báo lỗi”:** làm suy giảm availability hơn nữa.

## 22. Checklist production

- [ ] Chỉ cho phép khi có **PERMIT hợp lệ, đúng binding và còn hiệu lực**.
- [ ] Authentication/tenant/resource local guards độc lập và fail closed.
- [ ] DENY_POLICY được tách khỏi TIMEOUT, NETWORK, INVALID, CIRCUIT_OPEN.
- [ ] `AuthorizationManager` không dùng null/abstain cho sự cố PDP khi guard bắt buộc.
- [ ] Connect/read/overall timeouts hữu hạn và nằm trong request deadline.
- [ ] Retry chỉ transient/idempotent evaluation, bounded attempts và backoff.
- [ ] Circuit breaker OPEN không bao giờ được coi là PERMIT; có bulkhead khi cần.
- [ ] PDP URL allowlisted, TLS/hostname/mTLS/source được xác minh.
- [ ] JSON strict schema/duplicate keys/effect; reject response rỗng hoặc bất thường.
- [ ] RequestId/subject/tenant/resource/action/version/expiry được xác minh.
- [ ] Obligations bắt buộc được hỗ trợ và thực thi.
- [ ] Cache positive quyết định có scope key đầy đủ, TTL và revocation policy.
- [ ] Side effect chỉ sau authorization; write còn có tenant/version conditional predicates.
- [ ] Batch policy check xử lý thiếu item và atomicity đúng.
- [ ] HTTP 401/403/503 được map ở đúng security/application boundary.
- [ ] Audit decisionId, reason, latency, policy revision nhưng không log secrets.
- [ ] Có tests HTTP fault injection, invalid response, wrong binding, revocation, retry, cache, circuit open và no side effects.
- [ ] Có runbook cho outage/schema mismatch/revocation.

**Ghi nhớ:** timeout, network error và malformed response **không chứng minh caller bị policy DENY**, nhưng cũng **không bao giờ tạo PERMIT**. Tầng thực thi chỉ được tiến hành khi có **validated PERMIT** cho chính caller, tenant, resource và action hiện hành. Hãy tách lỗi vận hành để chẩn đoán và phục hồi, đồng thời giữ nguyên invariant **không cho phép dữ liệu hoặc side effects vượt quyền**.

## Tài liệu chính thức

- [Spring Security — Authorization Architecture](https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html)
- [Spring Security — AuthorizationManager JavaDoc](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authorization/AuthorizationManager.html)
- [Spring Security — Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)
- [Resilience4j — CircuitBreaker](https://resilience4j.readme.io/docs/circuitbreaker)
- [Resilience4j — Retry](https://resilience4j.readme.io/docs/retry)
- [Resilience4j — TimeLimiter](https://resilience4j.readme.io/docs/timeout)
- [Java 17 — HttpClient](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html)
