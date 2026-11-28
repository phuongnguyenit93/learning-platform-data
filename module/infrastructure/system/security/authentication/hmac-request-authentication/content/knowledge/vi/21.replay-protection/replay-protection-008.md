# Replay trong cluster

Khi HTTP API dùng HMAC, client tính chữ ký từ **shared secret** và **canonical request** bao gồm những thành phần được hợp đồng ký quy định, chẳng hạn method, URI, signed headers và body digest. Nếu một request đã ký được gửi lại nguyên vẹn, HMAC vẫn có thể đúng vì byte thông điệp và secret không đổi. Đây chính là **replay**: một request cũ được chấp nhận thêm lần nữa trong khi hệ thống kỳ vọng nó chỉ được sử dụng một lần.

Khi ứng dụng chạy trên **cluster nhiều JVM, pods, gateways hoặc regions**, một giải pháp lưu nonce trong bộ nhớ từng node dễ thất bại: request đầu tới node A, request lặp tới node B; cả hai đều thấy nonce “chưa dùng”. Bài **Replay trong cluster** tập trung vào cách xây dựng một **quyết định admission nguyên tử, được chia sẻ và đủ bền vững**, đồng thời giải thích những giới hạn khi Redis/SQL failover và replication không nhất quán.

Bài học thuộc chương **Replay protection**, trong mô-đun `SECURITY_AUTHENTICATION_HMAC_REQUEST_AUTHENTICATION`. Mô-đun thiết kế xác thực HTTP request bằng HMAC với shared secret và canonical request, đồng thời thực hành chống replay bằng timestamp/nonce, quản lý key rotation, kiểm thử proxy/gateway và phân biệt authentication với authorization.

> **Nguyên tắc:** Mọi verifier có thể nhận cùng một signed request phải dùng **cùng replay authority hoặc một cơ chế ownership nhất quán tương đương**. Thao tác kiểm tra nonce chưa tồn tại rồi ghi nhận nó phải **nguyên tử**. Cần kiểm tra riêng tính bền vững của nonce đã được ghi khi failover: một `SET NX EX` atomic trên Redis primary **không mặc nhiên bảo đảm** acknowledged write tồn tại sau mọi failover.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt HMAC verification, timestamp freshness, replay admission, authorization và idempotency.
2. Tái hiện replay lọt qua **per-node nonce caches** hoặc check-then-set không nguyên tử.
3. Thiết kế replay namespace theo protocol version, audience, credential và nonce.
4. Dùng một **atomic insert-if-absent có TTL** để chống cạnh tranh trên cluster.
5. Tính nonce retention theo max request age, future skew và clock margin.
6. Phân tích Redis Cluster slots, primary/replica replication, failover và multi-region eventual consistency.
7. Thiết kế replay gate Java 17 với kết quả CLAIMED/REPLAY/UNKNOWN.
8. Kiểm thử đồng thời giữa nhiều nodes, crash, outage, eviction, clock skew và gateway retry.
9. Kết hợp key rotation, signed audience, principal và authorization.
10. Không nhầm một nonce chỉ được nhận một lần với **business exactly-once effects**.

## 2. Tại sao HMAC vẫn đúng khi request bị replay?

Request mẫu:

~~~http
POST /v1/payments HTTP/1.1
Host: api.example.test
Content-Type: application/json
X-Key-Id: partner-a-k3
X-Timestamp: 1800000030
X-Nonce: 6bfb21974a08417199273b09ca49a3ec
X-Signature: <base64url-hmac-sha256-tag>

{"paymentId":"P42","amount":500000}
~~~

Hợp đồng ký minh họa:

~~~text
HMAC-REQUEST-V1
POST
/v1/payments

audience:payments-api
content-type:application/json
x-key-id:partner-a-k3
x-timestamp:1800000030
x-nonce:6bfb21974a08417199273b09ca49a3ec
body-sha256:<hex-sha256-of-exact-raw-body>
~~~

Verifier tự tính `expectedTag = HMAC-SHA256(secret, canonicalBytes)` rồi so với `presentedTag` sau strict Base64URL decoding. Nếu attacker capture và gửi lại **đúng tất cả các byte**:

~~~text
method + URI + signed headers -> unchanged
raw body bytes               -> unchanged
timestamp + nonce            -> unchanged
HMAC input                   -> unchanged
expectedTag                  -> unchanged
presentedTag                 -> unchanged
~~~

HMAC vẫn khớp. Timestamp có thể vẫn nằm trong cửa sổ chấp nhận. **Chỉ replay store mới biết nonce đã được sử dụng trước đó**.

### 2.1. Các lớp bảo vệ không thay thế nhau

| Lớp | Kiểm tra | Không tự đảm bảo |
| --- | --- | --- |
| HMAC | Caller sở hữu shared secret và request đã ký không bị sửa | Request chưa từng được gửi |
| Signed timestamp | Thời điểm ký còn trong cửa sổ freshness | Không gửi lại trong cửa sổ |
| Signed nonce + shared replay store | Nonce chưa được claim trong scope | Nghiệp vụ không trùng với nonce mới |
| Key status/audience | Credential được phép dùng cho service này | Quyền trên mọi resource |
| Authorization | Principal có quyền action/resource/tenant | Một operation ID không double-execute |
| Idempotency | Cùng operation/event không có tác động trùng ngoài policy | Không thay cryptographic authentication |

Ký nonce rất quan trọng. Nếu chỉ thêm nonce vào header **ngoài signed set**, attacker có thể đổi nonce mà giữ HMAC của phần khác. Timestamp cũng phải được ràng buộc vào chữ ký.

## 3. Vì sao cache nonce cục bộ thất bại trong cluster?

~~~mermaid
flowchart LR
    C[HTTP client] --> G[Gateway / Load balancer]
    G --> A[Verifier A]
    G --> B[Verifier B]
    A --> CA[Nonce Map A]
    B --> CB[Nonce Map B]
~~~

Giả sử mỗi JVM có:

~~~java
ConcurrentHashMap<String, Long> localSeen = new ConcurrentHashMap<>();
~~~

Timeline:

~~~text
T1: Request R với nonce N tới node A
T2: A tính HMAC -> PASS
T3: N chưa có trong map A
T4: A ghi N vào map A và nhận R

T5: Attacker hoặc gateway gửi lại R tới node B
T6: B tính HMAC -> PASS
T7: N chưa có trong map B
T8: B ghi N vào map B và cũng nhận R
~~~

Hai JVM hoàn toàn không chia sẻ trạng thái. Dùng `ConcurrentHashMap` đúng cách cũng **không tạo cluster-wide visibility**.

### 3.1. Check-then-insert cũng có race trên một JVM

~~~java
// Sai: hai threads có thể cùng thấy missing.
if (!localSeen.containsKey(key)) {
    localSeen.put(key, nowSeconds);
    executeBusinessAction();
}
~~~

Tại một JVM, `putIfAbsent` có thể giải quyết check-and-insert race cục bộ. Nhưng production có nhiều JVM cần một **replay authority được các node chia sẻ**.

### 3.2. Sticky sessions không phải biện pháp chống replay đủ mạnh

- Load balancer có thể chuyển node khi restart, scale hoặc failover.
- Attacker có thể mở kết nối mới hoặc đi qua gateway khác.
- Gateway retry thường không bảo đảm cùng backend.
- Nhiều vùng/ingress không nhất thiết chia sẻ sticky cookie.
- Client có thể mất cookie hoặc cookie không nằm trong signed request.

Sticky routing có thể là phần của ownership scheme **nếu được chứng minh không bypass**, nhưng mặc định không thay shared replay gate.

## 4. Bài toán admission: chỉ một request được “thắng”

Một API conceptual:

~~~text
claimOnce(namespace, nonce, ttl):
    if key is absent:
        atomically insert key with expiration
        return CLAIMED
    if key exists:
        leave its TTL unchanged
        return REPLAY
    if outcome is unknown or store cannot be trusted:
        return UNKNOWN
~~~

Kỳ vọng:

~~~text
Verifier A: claim(N) -> CLAIMED
Verifier B: claim(N) -> REPLAY
Verifier C: claim(N) -> REPLAY
~~~

Hoặc B thắng và A/C thua. Điều không được phép xảy ra trong một **replay authority nhất quán** là A và B cùng trả CLAIMED cho cùng key trong cùng validity window.

### 4.1. Những tính chất cần ghi rõ

1. **Atomicity:** Quyết định “absent → present” là một bước không bị chen ngang.
2. **Shared visibility:** Mọi verifier liên quan quan sát cùng quyết định.
3. **Retention:** Key không bị mất khi signed request vẫn đủ fresh.
4. **Durability:** Nếu system yêu cầu anti-replay xuyên failover, successful claim cần survive failure theo chính sách.
5. **Partition behavior:** Khi không có authority tin cậy, request phải được xử lý theo fail-closed/availability policy được công bố.
6. **Namespace correctness:** Không có delimiter collisions hay cross-service confusion.
7. **Audit and monitoring:** Có metrics phân biệt MAC failure, REPLAY, UNKNOWN, storage problems.

**Atomic trên primary hiện hành** không tự đồng nghĩa **durable/linearizable qua mọi replica failover**.

### 4.2. Khi nào nonce được coi đã dùng?

Một policy đơn giản và dễ kiểm soát: khi HMAC hợp lệ, timestamp fresh và nonce được claim thành công, **nonce đó đã dùng**, dù authorization hoặc business handler về sau thất bại. Không tự xóa nonce vì exception; một side effect có thể đã commit trước timeout.

Nếu cần retry semantics phức tạp hơn, dùng operation status và transactional idempotency, không làm yếu replay admission.

## 5. Replay namespace đúng phạm vi

Một replay key:

~~~text
hmac-replay:v1:payments-api:partner-a-k3:6bfb21974a08417199273b09ca49a3ec
~~~

| Thành phần | Ý nghĩa |
| --- | --- |
| `hmac-replay` | Prefix tránh đụng cache khác |
| `v1` | Protocol/signing contract version |
| `payments-api` | Audience do server kiểm tra |
| `partner-a-k3` | Key ID chọn exact record/secret |
| Nonce | 16-byte random nonce biểu diễn lowercase hex |

### 5.1. Vì sao thường không thêm path vào key?

Nếu key chứa `method + path + nonce`, cùng nonce có thể được dùng nhiều lần ở các endpoints khác nhau. Nếu contract muốn **một nonce duy nhất trên mọi request thuộc credential**, hãy dùng `audience + keyId + nonce`. Chỉ dùng per-route nonce scope khi có lý do và tài liệu rõ ràng.

### 5.2. Key ID so với principal ID

- Scope theo **key ID**: k2 và k3 trong rotation có replay namespaces riêng.
- Scope theo **principal ID**: một nonce dùng trên k2 có thể bị cấm dùng trên k3.

Cả hai có thể là thiết kế hợp lệ. Bài này chọn **audience + key ID + nonce** để mỗi key record chọn một secret rõ ràng. Nếu muốn unique xuyên credentials thì phải sửa contract có version và test cụ thể.

### 5.3. Không tin namespace do client tự khai

Server phải lấy audience từ routing/key policy tin cậy, kiểm tra key ID đã HMAC ký và validate nonce (ví dụ `[0-9a-f]{32}`). Nếu key ID cho phép dấu `:` hoặc ký tự tự do, cần length-prefix/structured encoding để tránh nhiều bộ giá trị tạo cùng một key string.

## 6. Nonce TTL và timestamp window trong cluster

Đặt:

- `t_s` là Unix seconds đã ký.
- `t_now` là giờ của verifier.
- `A` là **max past age**, ví dụ 300 giây.
- `F` là **allowed future skew**, ví dụ 30 giây.
- `M` là margin cho lệch đồng hồ, chậm trễ và sai số expiration.

Freshness:

\[
t_{\mathrm{now}} - A \le t_s \le t_{\mathrm{now}} + F
\]

Với một timestamp đã ký, cửa sổ mà nó có thể được chấp nhận là:

\[
t_s-F \le t_{\mathrm{now}} \le t_s+A
\]

Do đó một TTL cố định bảo thủ tính từ lúc claim thường là:

\[
\text{nonceTtl} \ge A+F+M
\]

### 6.1. Replay gap khi TTL quá ngắn

~~~text
At first admission: server now = T0
Signed timestamp: ts = T0 + 30
Max age A = 300s
Future skew F = 30s

If nonce TTL=300:
  replay record expires at T0+300
  signed request is fresh through T0+330
~~~

Từ `T0+300` đến `T0+330` request vẫn có thể fresh nhưng nonce đã biến mất. Cluster dù có Redis chung và atomic claim vẫn có thể **admit lại nonce**.

Ví dụ chọn `M=30` → TTL=360 giây. Margin phải được quyết định bằng clock-skew assumptions và vận hành thật, không dùng hằng số này cho mọi API.

### 6.2. Inclusive boundaries

Nếu freshness check dùng dấu `≤`, timestamp tại đúng `t_s+A` vẫn fresh. Không để TTL hết ngay tại biên khi request còn có thể được chấp nhận. Cần buffer cho clock drift giữa nodes, storage clock và latency từ timestamp-check tới claim.

### 6.3. Đồng hồ và timezone

- Dùng UTC epoch seconds, không phụ thuộc timezone hiển thị.
- Giám sát NTP/clock synchronization giữa nodes.
- Không dùng `System.nanoTime()` để so với Unix timestamp; đó là monotonic/relative time trong process.
- Test skew giữa các nodes và biên `t_s-F`, `t_s+A`.
- Nếu queue có thể giữ request lâu giữa freshness check và nonce claim, cần kiểm lại tại admission boundary hoặc quy định timeout/bounded delay.

### 6.4. Nonce absent không chứng minh timestamp fresh

Sau TTL expiration, replay key có thể không còn. Verifier vẫn phải kiểm tra **signed timestamp trên mọi request**; không thể chỉ hỏi store rồi coi absent là request hợp lệ.

## 7. Redis atomic claim bằng SET NX EX

Một lệnh:

~~~redis
SET hmac-replay:v1:payments-api:partner-a-k3:6bfb21974a08417199273b09ca49a3ec seen NX EX 360
~~~

- `SET` tạo key.
- `NX` chỉ tạo khi key không tồn tại.
- `EX 360` đặt TTL **trong cùng thao tác**.
- Trả thành công khi nonce mới được claim; trả key already exists với nonce đã dùng.
- Duplicate **không gia hạn TTL**.

### 7.1. Hai cách làm sai

**Sai:**

~~~text
GET nonceKey -> missing
SET nonceKey seen EX 360
~~~

Hai node có thể cùng thấy missing trước khi ghi.

**Sai:**

~~~text
SETNX nonceKey seen
EXPIRE nonceKey 360
~~~

Nếu process crash giữa hai lệnh, key có thể tồn tại vô thời hạn, phá capacity plan. Một lệnh `SET NX EX` đơn giản hơn.

### 7.2. Redis Cluster one-key atomicity

Redis Cluster phân phối keys vào hash slots. Một `SET NX EX` trên một key được thực hiện atomically ở primary phụ trách slot đó. Client cluster-aware phải theo redirect `MOVED`/`ASK` và định tuyến mọi request cùng key tới đúng authority.

Điều đó **không** biến nhiều Redis clusters độc lập thành một shared replay store, và cũng không tự bảo đảm durability qua failover.

### 7.3. Replication/failover: ACK có thể mất

Timeline:

~~~text
1. Verifier A SET NX EX N on primary P -> OK.
2. A admits signed request R.
3. P fails before replica Q has received the nonce write.
4. Q becomes primary.
5. Verifier B retries same R.
6. Q has no nonce N -> SET NX EX -> OK.
7. R may be admitted twice across failover.
~~~

**Kết luận:** Atomicity trên một primary không phải lời hứa nonce bền vững qua mọi failover khi replication bất đồng bộ.

Các công cụ replication acknowledgment/persistence có thể **giảm nguy cơ** tùy failure mode, nhưng không tự tạo strong linearizability cho mọi partition. Nếu nghiệp vụ yêu cầu guarantee cao, phải chọn mô hình storage/commit có consistency/durability tương xứng và kiểm thử các trường hợp primary crash sau ACK.

### 7.4. Eviction trước TTL

Nếu Redis evict nonce key do memory pressure, signed request còn hạn có thể qua lại. Cần capacity, metrics evicted_keys và policy không âm thầm bỏ nonce đang hiệu lực. Khi store không đủ năng lực claim an toàn, **fail closed** cho API nhạy cảm.

## 8. Multi-region và eventual consistency

~~~mermaid
flowchart TB
    C[Client / replay actor] --> L[Global load balancer]
    L --> A[Verifier Region A]
    L --> B[Verifier Region B]
    A --> SA[Replay store A]
    B --> SB[Replay store B]
    SA <-->|Eventual replication| SB
~~~

Nếu R tới A và B trước replication:

~~~text
T1: A sees N absent -> inserts N -> ACCEPT
T2: B has not yet received N
T3: B sees N absent -> inserts N -> ACCEPT
T4: A/B eventually converge, but two admissions already happened
~~~

**Eventual convergence không rút lại được business effects đã xảy ra.**

### 8.1. Các lựa chọn kiến trúc

| Thiết kế | Ưu điểm | Giới hạn/tradeoff |
| --- | --- | --- |
| Một replay authority toàn cục | Một quyết định nhất quán | Network latency và availability |
| Home region theo credential | Một owner xử lý scope đó | Routing, failover và fencing phức tạp |
| Unique key trong durable DB | Admission gắn DB commit | Storage/throughput/cleanup cost |
| Consensus/quorum authority | Có thể đạt consistency mạnh qua partition theo assumptions | Complexity/availability tradeoff |
| Independent regional stores | Latency thấp | Có nguy cơ double admission trước replication |

Nếu home-region ownership chuyển từ A sang B, phải có **fencing** bảo đảm owner cũ không tiếp tục nhận nonce. Không có rào chắn đó, split-brain có thể khiến cả hai coi mình là authority.

## 9. SQL unique constraint như một authority khác

Một replay table minh họa:

~~~sql
CREATE TABLE hmac_replay_nonce (
    namespace VARCHAR(200) NOT NULL,
    nonce_hex CHAR(32) NOT NULL,
    claimed_at TIMESTAMP NOT NULL,
    expires_at TIMESTAMP NOT NULL,
    PRIMARY KEY (namespace, nonce_hex)
);
~~~

Dùng **INSERT** có unique constraint làm cơ chế phân xử. Hai transactions tranh cùng key chỉ một được commit thành công theo guarantees của DB được chọn. Không dùng `SELECT` rồi `INSERT` như một thay thế cho uniqueness vì có race.

Đây là mô hình khái niệm; SQL dialect, isolation, primary/replica failover và durability phụ thuộc DB/configuration. Background cleanup phải xóa rows **sau** retention deadline an toàn; xóa sớm làm mất replay protection.

### 9.1. Database cũng cần phân tích failover

Unique constraint trên primary không tự trả lời replica failover có mất acknowledged commit hay không. Phải kiểm tra replication mode và consistency guarantee của hệ thống DB thực tế. Storage choice và business criticality quyết định tradeoff.

### 9.2. Một admission record khác business operation record

Nonce key chỉ nói “signed request với nonce N đã được nhận”. Một payment ID có thể được gửi lại **bằng nonce mới**. Một unique business operation ID và transactional idempotency store vẫn cần để ngăn double-charge.

## 10. Java 17: replay admission contract

Không nên buộc business logic trực tiếp vào API của một Redis client cụ thể. Tách một interface replay store với kết quả rõ ràng:

~~~java
import java.time.Duration;

public interface ReplayStore {
    enum ClaimResult {
        CLAIMED,  // Nonce mới, được ghi kèm TTL.
        REPLAY,   // Nonce đã được claim; TTL không đổi.
        UNKNOWN   // Store outage, timeout hoặc write outcome không chắc.
    }

    ClaimResult claimOnce(String replayKey, Duration ttl);
}
~~~

**Điều kiện tiên quyết:** `CLAIMED` chỉ mô tả kết quả adapter ở **mức bảo đảm mà storage deployment thực sự cung cấp**. Đừng để một adapter Redis chỉ nhận ACK từ primary tự khẳng định đã có durability toàn cluster qua mọi failover.

### 10.1. Namespace và TTL policy

~~~java
import java.time.Duration;
import java.util.regex.Pattern;

public final class ReplayPolicyV1 {
    public static final long MAX_PAST_AGE = 300;
    public static final long FUTURE_SKEW = 30;
    public static final long SAFETY_MARGIN = 30;

    public static final Duration NONCE_TTL = Duration.ofSeconds(
            MAX_PAST_AGE + FUTURE_SKEW + SAFETY_MARGIN);

    private static final Pattern KEY_ID =
            Pattern.compile("[A-Za-z0-9._-]{1,80}");
    private static final Pattern NONCE =
            Pattern.compile("[0-9a-f]{32}");

    private ReplayPolicyV1() {}

    public static String storageKey(String keyId, String nonce) {
        if (keyId == null || !KEY_ID.matcher(keyId).matches()
                || nonce == null || !NONCE.matcher(nonce).matches()) {
            throw new IllegalArgumentException("Invalid replay identity");
        }
        // Audience đáng tin được xác định từ service/key registry.
        return "hmac-replay:v1:payments-api:" + keyId + ":" + nonce;
    }
}
~~~

Mã minh họa cho service `payments-api`. Trong hệ thống thật, replay namespace phải được thiết kế nhất quán với cách verifier xác thực signed audience và credential scope.

### 10.2. Timestamp freshness với Clock testable

~~~java
import java.time.Clock;

public final class FreshnessV1 {
    private FreshnessV1() {}

    public static boolean isFresh(long signedTimestamp, Clock clock) {
        long now = clock.instant().getEpochSecond();
        if (signedTimestamp < 0 || now < 0) {
            return false;
        }

        try {
            long oldest = Math.subtractExact(
                    now, ReplayPolicyV1.MAX_PAST_AGE);
            long newest = Math.addExact(
                    now, ReplayPolicyV1.FUTURE_SKEW);
            return signedTimestamp >= oldest
                    && signedTimestamp <= newest;
        } catch (ArithmeticException overflow) {
            return false;
        }
    }
}
~~~

`Clock.fixed(...)` rất hữu ích cho boundary tests. Không dùng `LocalDateTime` và timezone mặc định để diễn giải Unix epoch seconds.

HTTP adapter phải parse `X-Timestamp` theo **cú pháp được ký** (ví dụ không chấp nhận leading zeros, dấu `+`, ký tự lạ, số vượt `long` hoặc milliseconds nhầm seconds). Nếu client ký chuỗi thời gian `00123` còn server parse thành `123` và serialize lại, canonical bytes có thể không thống nhất.

### 10.3. Replay gate chỉ được gọi sau MAC

~~~java
import java.time.Clock;

public final class ReplayGateV1 {
    public enum Decision {
        ALLOW, REPLAY, STALE, STORE_UNAVAILABLE
    }

    private final ReplayStore store;
    private final Clock clock;

    public ReplayGateV1(ReplayStore store, Clock clock) {
        this.store = store;
        this.clock = clock;
    }

    /**
     * PRECONDITION:
     * - HTTP request đã validate và canonicalize.
     * - Key record, status, audience đã được xác thực.
     * - HMAC tag expected đã so khớp với presented signature.
     * - keyId, timestamp, nonce là những field đã ký.
     */
    public Decision admitVerified(
            String keyId, String nonce, long signedTimestamp) {

        if (!FreshnessV1.isFresh(signedTimestamp, clock)) {
            return Decision.STALE;
        }

        String key = ReplayPolicyV1.storageKey(keyId, nonce);
        final ReplayStore.ClaimResult result;

        try {
            result = store.claimOnce(key, ReplayPolicyV1.NONCE_TTL);
        } catch (RuntimeException unknownFailure) {
            return Decision.STORE_UNAVAILABLE;
        }

        if (result == ReplayStore.ClaimResult.CLAIMED) {
            return Decision.ALLOW;
        }
        if (result == ReplayStore.ClaimResult.REPLAY) {
            return Decision.REPLAY;
        }
        return Decision.STORE_UNAVAILABLE;
    }
}
~~~

Đây không phải bộ HMAC verifier đầy đủ. Hàm **chỉ nhận request đã vượt MAC** và dùng replay store để quyết định có được đi tiếp. Nếu code gọi `admitVerified` ngay sau khi parse `X-Key-Id` và `X-Nonce` mà chưa so MAC, attacker có thể gửi các giá trị tự khai để **poison replay store**, ngăn request hợp lệ.

### 10.4. Thứ tự HTTP middleware an toàn

~~~mermaid
flowchart TD
    A[HTTP Request] --> B[Validate framing, signed headers, limits]
    B --> C[Parse key ID, timestamp, nonce, signature]
    C --> D[Lookup exact trusted key record]
    D --> E[Canonicalize method, path, query, signed headers, raw body digest]
    E --> F[Compute expected HMAC and compare full tag]
    F --> G{HMAC valid?}
    G -- No --> X[Reject]
    G -- Yes --> H{Signed timestamp fresh?}
    H -- No --> X
    H -- Yes --> I[Atomic claim nonce in shared authority]
    I --> J{Result}
    J -- REPLAY or UNKNOWN --> X
    J -- CLAIMED --> K[Trusted principal from credential]
    K --> L{Authorize action, resource, tenant?}
    L -- No --> Y[Reject authorization]
    L -- Yes --> M[Business operation + idempotency]
~~~

Có thể kiểm tra một số điều kiện rẻ (độ dài, timestamp quá xa) trước HMAC để giảm chi phí; nhưng **không ghi trạng thái nonce của request chưa xác thực**.

## 11. Java 17: Redis adapter minh họa

Trong một Redis client thật, câu lệnh phải có semantics tương đương:

~~~redis
SET <replay-key> seen NX EX <ttl-seconds>
~~~

Interface ứng dụng để tránh gắn bài học với phiên bản thư viện:

~~~java
public interface RedisCommandAdapter {
    enum Status {
        INSERTED, ALREADY_EXISTS, UNCERTAIN
    }

    Status setNxEx(String key, String value, long seconds);
}
~~~

Adapter:

~~~java
import java.time.Duration;

public final class RedisReplayStore implements ReplayStore {
    private final RedisCommandAdapter redis;

    public RedisReplayStore(RedisCommandAdapter redis) {
        this.redis = redis;
    }

    @Override
    public ClaimResult claimOnce(String key, Duration ttl) {
        if (ttl == null || ttl.isZero() || ttl.isNegative()
                || ttl.getSeconds() < 1) {
            throw new IllegalArgumentException("Invalid TTL");
        }

        // PHẢI là MỘT thao tác Redis SET ... NX EX ...
        var status = redis.setNxEx(key, "seen", ttl.getSeconds());

        return switch (status) {
            case INSERTED -> ClaimResult.CLAIMED;
            case ALREADY_EXISTS -> ClaimResult.REPLAY;
            case UNCERTAIN -> ClaimResult.UNKNOWN;
        };
    }
}
~~~

Các Redis libraries (Lettuce/Jedis/Spring Data Redis) có API khác nhau; mã ở đây là **khung tích hợp**, không được hiểu là lời gọi production copy-paste đầy đủ.

Cần kiểm tra adapter xử lý:

- Redis Cluster redirect `MOVED`/`ASK`.
- Thời gian timeout, reconnect và retry.
- Primary promotion/failover.
- Kết quả ghi không xác định nếu response bị mất.
- Consistency/durability guarantee thực, không chỉ return code.

### 11.1. UNKNOWN không có nghĩa “chưa ghi”

Ví dụ:

~~~text
T1 client sends SET NX EX N
T2 Redis writes N
T3 Redis response is lost
T4 client reports timeout
~~~

Ứng dụng không biết chắc request có được ghi hay chưa. Nếu mù quáng retry/cấp quyền, có thể làm lệch semantics admission. Trong API nhạy cảm, coi outcome là `UNKNOWN` và **không chạy business action**.

Nếu client muốn retry nghiệp vụ, cung cấp cơ chế operation-status lookup, signed request mới với nonce mới và idempotency business để tránh side effects trùng.

### 11.2. Không fail open trong catch

~~~java
// Sai nếu API yêu cầu chống replay mạnh.
try {
    return replayStore.claimOnce(key, ttl);
} catch (RuntimeException ignored) {
    return ReplayStore.ClaimResult.CLAIMED;
}
~~~

Đoạn này mở bypass đúng khi hệ thống chịu lỗi. Cần error classification, metrics/alerts và **fail closed** theo security requirement, kể cả khi phải từ chối một số requests hợp lệ.

## 12. Java 17: test concurrency với fake store

Một fake có thể dùng `ConcurrentHashMap.putIfAbsent` cho **unit tests trong một process**:

~~~java
import java.time.Duration;
import java.util.concurrent.ConcurrentHashMap;

public final class InMemoryFakeReplayStore implements ReplayStore {
    private final ConcurrentHashMap<String, Boolean> used =
            new ConcurrentHashMap<>();

    @Override
    public ClaimResult claimOnce(String key, Duration ttl) {
        // Test-only: không có TTL, không có cluster visibility.
        return used.putIfAbsent(key, Boolean.TRUE) == null
                ? ClaimResult.CLAIMED
                : ClaimResult.REPLAY;
    }
}
~~~

Không đưa fake này vào production khi có nhiều nodes. Nó không mô phỏng Redis failover, eviction, replicas hoặc clocks.

### 12.1. Hai mươi threads tranh cùng nonce

~~~java
import java.time.Duration;
import java.util.ArrayList;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public final class ReplayClaimRaceDemo {
    public static void main(String[] args) throws Exception {
        ReplayStore store = new InMemoryFakeReplayStore();
        String key = "one-namespace:one-nonce";
        int workers = 20;

        var ready = new CountDownLatch(workers);
        var start = new CountDownLatch(1);
        var pool = Executors.newFixedThreadPool(workers);

        try {
            var futures =
                    new ArrayList<Future<ReplayStore.ClaimResult>>();

            for (int i = 0; i < workers; i++) {
                futures.add(pool.submit(() -> {
                    ready.countDown();
                    start.await();
                    return store.claimOnce(
                            key, Duration.ofSeconds(360));
                }));
            }

            ready.await();
            start.countDown();

            int winners = 0;
            for (var f : futures) {
                if (f.get() == ReplayStore.ClaimResult.CLAIMED) {
                    winners++;
                }
            }
            if (winners != 1) {
                throw new AssertionError(
                        "Expected exactly one winner: " + winners);
            }
        } finally {
            pool.shutdownNow();
        }
    }
}
~~~

Đây là minh họa atomicity trong một JVM. Để test **cluster**, cần nhiều app processes/containers cùng gửi claim tới **cùng Redis/SQL authority**. Một test chỉ dùng hai threads chung một map không chứng minh khả năng chống replay giữa hai pods.

### 12.2. Fake trả UNKNOWN cho negative tests

Tạo một adapter giả trả `UNKNOWN` hoặc ném exception, rồi khẳng định `ReplayGateV1` trả `STORE_UNAVAILABLE` và **business handler không chạy**. Cần test cả trường hợp nonce stale: không gọi store khi freshness đã thất bại.

## 13. Crash, retry và business idempotency

Xét luồng:

~~~text
T1  signed request R (nonce N1) -> HMAC valid
T2  replay store claim N1 -> success
T3  payment P42 committed
T4  server crashes before HTTP response
T5  client retries original R (nonce N1)
T6  replay store sees N1 -> reject replay
~~~

Đây là behavior hợp lệ theo one-time nonce contract. Client cần biết trạng thái operation thông qua idempotency key/operation lookup.

Nếu client thay nonce thành N2 và ký request mới cho cùng paymentId, replay gate có thể cho qua, nên business layer phải có **durable idempotency**.

### 13.1. So sánh hai loại khóa

| Khóa | Nơi sử dụng | Ý nghĩa |
| --- | --- | --- |
| `audience:keyId:nonce` | Replay store | Signed request freshness/one-time admission |
| `principalId:paymentId` | Business store | Business operation được thực hiện không quá một lần theo policy |
| `eventId:consumerId` | Event consumer | Event deduplication |
| `keyId` | Credential registry | Secret, algorithm, principal, audience, lifecycle |

Idempotency key có ảnh hưởng semantics nên **phải được ký** hoặc nằm trong signed body, và server cần enforce unique business key/transactional result.

### 13.2. Không xóa nonce khi business lỗi

Một timeout không cho biết payment đã commit chưa. Xóa nonce chỉ vì API trả 500 có thể cho request cũ chạy lại. Thay vì vậy dùng operation status/idempotent retry, hoặc state machine nghiệp vụ được thiết kế riêng.

### 13.3. Transactional outbox và side effects bên ngoài

Trong workflow gửi message/ghi DB và gọi downstream, idempotency cần xét các biên transaction. Có thể dùng transactional outbox và unique operation IDs để tránh trùng sự kiện hoặc xử lý lại an toàn. Nonce store không thay các cơ chế này.

## 14. Gateway, reverse proxy và replay ownership

~~~mermaid
sequenceDiagram
    participant C as Client
    participant G as Gateway
    participant V as HMAC verifier cluster
    participant S as Replay store
    participant B as Business service

    C->>G: HTTPS signed request
    G->>V: Forward signed components
    V->>V: Canonicalize, HMAC verify, freshness
    V->>S: Atomic claim nonce
    S-->>V: CLAIMED / REPLAY / UNKNOWN
    V->>B: Authenticated principal if admitted
    B->>B: Authorization and idempotent operation
~~~

### 14.1. Verifier ở gateway

Gateway kiểm HMAC và claim nonce **trước** các phép rewrite ảnh hưởng signed method/path/body. Backend chỉ được tin principal từ gateway qua authenticated internal channel; phải chặn bypass và xóa client-supplied identity headers.

Gateway cũng là cluster: mọi gateway nodes cần shared replay authority.

### 14.2. Verifier ở backend

Gateway phải giữ nguyên signed fields hoặc có một mapping canonical được định nghĩa rõ, versioned và đáng tin. Không tin `X-Original-URI`/`X-Forwarded-*` do Internet tự gửi. Các backend nodes dùng chung replay authority.

### 14.3. Double verification không phải double admission

Nếu gateway đã claim nonce và backend lại claim cùng nonce vào cùng namespace, backend sẽ coi request hợp lệ là replay. Cần phân công **owner của replay admission**. Có thể verify lại chữ ký ở tầng sau cho defense in depth, nhưng không tự claim hai lần mà thiếu contract cho internal trust boundary.

### 14.4. Gateway retry nguyên signed request

Một gateway gửi R tới backend, bị timeout và retry R qua node khác. Nếu lần đầu đã claim nonce, lần retry phải bị đánh dấu replay. Đây không phải lỗi HMAC. Business idempotency/operation-status phải hỗ trợ client biết outcome.

### 14.5. HTTP framing và canonical path/query

Proxy có thể thay `Content-Length`, chuyển HTTP/1.1 ↔ HTTP/2 hoặc strip path prefix. HMAC verifier và router phải hiểu **cùng signed semantics**, hash đúng raw body content bytes theo contract. Nếu proxy reserialize JSON, canonical body digest có thể khác. Sửa những lỗi này riêng; không nới lỏng replay gate chỉ vì signature mismatch.

## 15. Key rotation và cross-service replay

Trong rotation:

~~~text
partner-a-k2 -> RETIRING, secret v2
partner-a-k3 -> ACTIVE, secret v3
~~~

Mỗi key ID ánh xạ tới **đúng secret/algorithm/audience/principal** của key record. Nonce namespace theo key ID giữ trạng thái riêng cho k2 và k3.

- K2 còn trong overlap: phải giữ nonce k2 đủ timestamp freshness window.
- K2 bị revoke toàn hệ thống: request k2 bị từ chối bất kể nonce entry tồn tại.
- K3 mới: dùng key record mới, secret mới và nonce namespace k3.
- Không thử nhiều secrets dưới cùng key ID tới khi MAC khớp; làm mơ hồ credential và revocation.

### 15.1. Signed audience quan trọng

Nếu cùng secret dùng cho orders và payments nhưng canonical request không ràng buộc audience, request có thể bị đem sang service khác. Replay key có audience **không tự sửa** lỗ hổng thiếu audience binding. Cần ký audience/authority theo contract, kiểm tra key record có quyền cho đích và route thật khớp.

## 16. Authorization không đến từ replay claim

Một client tenant A có thể ký request:

~~~http
POST /v1/tenants/B/payments HTTP/1.1
X-Key-Id: tenant-a-k3
X-Timestamp: 1800000030
X-Nonce: 6bfb21974a08417199273b09ca49a3ec
X-Signature: <valid-tag-under-tenant-A-secret>
~~~

HMAC đúng, timestamp fresh, nonce mới **không cho tenant A quyền thực hiện thanh toán của tenant B**. Server phải lấy principal từ trusted key registry sau authentication, xác định resource từ router/request đã validate và authorize action/resource/tenant.

Không tin `X-Role`, `X-Tenant-Id` hoặc `X-Authenticated-User` do caller tự khai làm cấp quyền, dù các header đó có thể được ký. HMAC bảo vệ lời yêu cầu, **không cấp quyền cho nội dung của lời yêu cầu**.

## 17. Capacity planning và observability

Số nonce entries đang active xấp xỉ:

\[
\mathrm{entries} \approx \mathrm{acceptedRequestsPerSecond}\times \mathrm{nonceTtlSeconds}
\]

Ví dụ 5.000 accepted requests/giây và TTL 360 giây → khoảng **1.800.000 entries**, chưa tính key bytes, value, TTL metadata, fragmentation, replicas, persistence và peak traffic.

### 17.1. Khi thiếu memory

Không tự hạ TTL xuống dưới window an toàn. Tăng capacity, thiết kế sharding đúng và đặt policy eviction/fail-closed có kiểm soát. Cần load test với **peak** request rate và burst traffic, không chỉ trung bình.

### 17.2. Metrics cần có

| Metric | Mục tiêu |
| --- | --- |
| HMAC verify success/failure | Tách crypto authentication với replay |
| Claim `CLAIMED`, `REPLAY`, `UNKNOWN` | Admission/replay/store health |
| Redis memory/evicted_keys/latency | Bảo đảm retention |
| Failover/replication lag | Theo dõi nguy cơ mất acknowledged nonce |
| Clock skew across nodes | Freshness và TTL đúng |
| Key rotation/revocation lag | Tránh một node nhận credential đã revoke |
| Gateway retry counts | Chẩn đoán duplicate forwarding |
| Business idempotency conflicts | Phát hiện request nonce mới cùng operation |

Không log shared secret hoặc toàn bộ signed request còn hạn có thể replay được; dùng redacted IDs/metrics.

## 18. Ma trận kiểm thử Replay trong cluster

Kiểm thử phải tách **cryptographic verification**, **atomic replay admission**, **failure semantics** và **business idempotency**. Một test chạy hai threads trong một JVM chỉ chứng minh một phần rất nhỏ so với deployment đa node.

### 18.1. HMAC, timestamp và namespace

| Test | Tình huống | Kết quả mong đợi |
| --- | --- | --- |
| HMAC hợp lệ | Đúng key, method, URI, body, signed headers | Qua bước MAC |
| HMAC sai | Thay một byte body giữ nguyên signature | Từ chối trước claim |
| Nonce tampering | Sửa `X-Nonce` giữ nguyên tag | HMAC sai |
| Timestamp tampering | Sửa `X-Timestamp` giữ nguyên tag | HMAC sai |
| Wrong audience | Mang signed request payments sang orders | Từ chối policy/MAC |
| Unknown key ID | Registry không có record | Từ chối |
| Revoked key | Tag đúng với secret đã thu hồi | Từ chối |
| Timestamp `now-A` | Đúng biên quá khứ, inclusive policy | Fresh |
| Timestamp `now-A-1` | Quá cũ | Reject |
| Timestamp `now+F` | Đúng biên tương lai, inclusive policy | Fresh |
| Timestamp `now+F+1` | Quá xa trong tương lai | Reject |
| Nonce malformed | Không đủ 32 lowercase hex | Reject |
| Duplicate `X-Nonce` | Hai header cùng tên khác case | Reject ở HTTP adapter |
| Key ID và nonce signed | Tự sửa key ID/nonce | HMAC không khớp |
| Namespace khác | Cùng nonce dưới key IDs khác | Theo credential-scope policy rõ |

### 18.2. Atomicity và thời hạn lưu

| Test | Tình huống | Kết quả mong đợi |
| --- | --- | --- |
| First claim | Nonce key absent | `CLAIMED` |
| Repeat claim | Same nonce còn TTL | `REPLAY` |
| Concurrent pair | Hai node tranh cùng key | Tối đa một `CLAIMED` |
| Concurrent burst | 100 workers với shared store | Tối đa một `CLAIMED` |
| Separate namespaces | Nonces giống nhau dưới credential khác | Theo scope đã định nghĩa |
| GET + SET race | Hai node đều đọc absent | Negative test phát hiện double admission |
| SETNX rồi EXPIRE | Crash giữa hai lệnh | Negative test cho entry thiếu TTL |
| Duplicate TTL | Claim lặp | TTL cũ không reset |
| `A=300,F=30,TTL=300` | Future-edge timestamp | Negative test: replay gap |
| `A=300,F=30,M=30,TTL=360` | Future-edge timestamp | Record sống đủ window theo assumptions |
| Inclusive boundary | Replay tại `ts+A` | Không được cho qua lần hai |
| After freshness | `now>ts+A` | Reject stale dù replay key absent |
| Clock skew | Node A nhanh, B chậm | Acceptance/TTL an toàn trong margin |
| Clock drift vượt margin | Offset bất thường | Alert/fail policy; không khẳng định an toàn |
| Redis eviction | Key bị xóa trước TTL | Phát hiện nguy cơ, không silent bypass |

### 18.3. Cluster failure và multi-region

| Test | Failure mode | Điều cần kiểm chứng |
| --- | --- | --- |
| Redis Cluster redirect | `MOVED`/`ASK` khi rebalance | Client đến đúng key slot owner |
| Network timeout trước write | Không có ACK tin cậy | `UNKNOWN`, fail closed |
| Network timeout sau write | Có thể đã ghi nhưng mất response | Không tự xem là CLAIMED |
| Primary crash sau ACK | Nonce chưa replicate | Đánh giá lost acknowledged write |
| Replica promotion | Failover trong nonce window | Guarantee đã công bố có còn đúng? |
| Replica lag | ACK trước khi replica thấy nonce | Kiểm tra khả năng replay sau failover |
| Store unavailable | Không còn replay authority | Không cho qua API nhạy cảm |
| Memory full | Không thể claim nonce | Fail closed |
| Split-brain | Hai primaries cùng accept | Phát hiện double admission / fencing cần thiết |
| Region A và B | Independent eventual stores | Negative test phát hiện dual accept |
| Home region failover | Owner chuyển từ A sang B | Owner cũ được fence trước khi B hoạt động |
| Gateway retry | Cùng signed request tới node khác | Replay rejected nếu nonce đã claim |
| Gateway reserialize body | Body bytes khác sau proxy | MAC lỗi hoặc verify tại đúng boundary |
| Gateway strips path prefix | URI signed khác URI nhận | Contract rõ; không thử normalize tùy tiện |

### 18.4. Business/authorization

| Test | Tình huống | Kỳ vọng |
| --- | --- | --- |
| HMAC đúng, tenant sai | Principal A gọi resource tenant B | Authorization từ chối |
| Same paymentId, nonce N1/N2 | Hai signed requests khác nonce | Business idempotency ngăn double charge |
| Crash sau claim | Handler chưa chắc đã commit | Không tự release nonce; dùng operation status |
| Response lost | Client retry nguyên signed R | Replay reject, trạng thái nghiệp vụ truy vấn được |
| Rotation k2/k3 | Cả hai key hợp lệ trong overlap | Mỗi key ID dùng đúng secret/namespace |
| Key k2 bị revoke | Nonce entry đã mất | Key status vẫn từ chối |

### 18.5. Phương pháp chạy test đúng

Một kịch bản integration:

1. Dựng hai verifier processes/containers với **cùng replay store**.
2. Tạo một test credential và signed request R có timestamp fresh, nonce N.
3. Dùng barrier hoặc công cụ test router gửi **cùng R gần đồng thời** tới cả hai.
4. Xác nhận cả hai có thể tính HMAC đúng.
5. Đếm admission outcomes: đúng một `CLAIMED` trong mô hình có một shared atomic authority, còn lại `REPLAY` hoặc lỗi an toàn.
6. Đảm bảo business handler không chạy hơn một lần cho R.
7. Thử request cùng nonce nhưng timestamp mới được ký lại: vẫn phải reject trong cùng namespace.
8. Thử nonce mới và cùng paymentId: replay gate có thể cho qua, idempotency bảo vệ business.
9. Lặp qua gateway retry, rolling deployment và HTTP versions được hỗ trợ.
10. Kiểm thử failover, network partitions, eviction và multi-region bằng scenarios tách biệt.

Không dựa vào `Thread.sleep` để chắc chắn tạo race. Dùng concurrency barriers, shared storage và quan sát admission results. Một test chỉ dùng `ConcurrentHashMap` trong JVM **không chứng minh** cluster-wide correctness.

## 19. Tình huống thực tế: một thanh toán bị nhận hai lần

Giả sử payment API chạy trên hai pods và mỗi pod có local nonce map:

~~~text
R: POST /v1/payments, paymentId=P42, nonce=N, HMAC valid

T1: R -> Pod A; N missing in A; execute payment P42
T2: replay R -> Pod B; N missing in B; execute payment P42 again
~~~

**Root cause:** Trạng thái replay cục bộ, không chia sẻ. HMAC và timestamp có thể hoạt động hoàn toàn đúng.

### 19.1. Sửa theo từng lớp

- Đưa nonce admission vào shared atomic replay authority.
- Chọn retention TTL bao phủ max-age, future skew và clock margin.
- Bảo đảm store outcome không chắc chắn dẫn đến **fail closed**.
- Test cross-node replay, gateway retry, failover và eviction.
- Dùng business idempotency theo principal + paymentId/operation ID.
- Authorization principal đối với tài khoản nguồn và hành động thanh toán.

### 19.2. Rủi ro sau khi chuyển sang Redis

Trong vận hành bình thường, `SET NX EX` giải quyết race giữa các pods. Nhưng nếu acknowledged nonce write mất trong primary failover, replay có thể được nhận lại. Vì vậy, khi yêu cầu an toàn là “không double-charge kể cả khi store failover”, cần **business transaction/idempotency bền vững** và/hoặc nâng consistency/durability của replay authority.

Không dùng câu “exactly once guaranteed” khi chưa chứng minh failure assumptions.

### 19.3. Ví dụ replay gap do TTL sai

Giả sử:

~~~text
maxPastAge       = 300s
futureSkew       = 30s
nonce TTL        = 300s
first server now = T0
signed timestamp = T0 + 30s
~~~

Nonce hết hạn `T0+300` nhưng request có thể fresh tới `T0+330`. Attacker replay tại `T0+310`: HMAC đúng, timestamp vẫn fresh, nonce đã absent. **Một shared atomic store cũng không sửa được chính sách TTL sai.**

## 20. Những sai lầm thường gặp

### 20.1. “Dùng Redis chung là đủ”

Không nếu TTL quá ngắn, bị eviction, failover làm mất acknowledged writes hoặc multi-region không có strong authority.

### 20.2. “Mọi JVM đều có ConcurrentHashMap nên an toàn”

Không. Local map không chia sẻ giữa nodes. Sticky sessions cũng không tự bảo đảm routing nhất quán qua failover.

### 20.3. “GET rồi SET gần nhau nên không có race”

Sai. Hai request đồng thời có thể cùng thấy absent. Dùng atomic `SET NX EX` hoặc primitive tương đương.

### 20.4. “SETNX sau đó EXPIRE không khác gì SET NX EX”

Nếu crash giữa hai lệnh có thể để lại key không expiration. Không tách riêng nếu không có transaction/script đảm bảo đúng semantics.

### 20.5. “Redis Cluster tức là không thể mất nonce”

Không. Redis Cluster slot routing/single-primary atomicity khác durability khi replicas bất đồng bộ hoặc failover.

### 20.6. “Đồng bộ eventual giữa hai regions rồi sẽ ổn”

Hai admissions có thể đã xảy ra trước replication. Eventual convergence không hoàn tác business effects.

### 20.7. “Nonce TTL chỉ cần bằng max-age”

Nếu timestamp tương lai được cho phép, acceptance window có thể dài thêm `F`. Cần `A+F+M` hoặc deadline tương đương đã kiểm chứng.

### 20.8. “Nonce đã có thì kéo dài TTL thêm”

Việc kéo dài mỗi replay tạo memory pressure và không thuộc retention policy ban đầu. Duplicate phải reject và giữ expiry.

### 20.9. “Store timeout thì cho request qua để tăng availability”

Với API nhạy cảm, đây là fail-open replay bypass. Phải quyết định theo security policy và ưu tiên từ chối khi không có authority đáng tin.

### 20.10. “Gateway retry nguyên request luôn phải thành công”

Khi nonce đã claim, retry nguyên signed request là replay theo contract. Cần operation-status/idempotent retry.

### 20.11. “Nonce giúp đảm bảo exactly-once payment”

Client có thể ký request mới với nonce mới nhưng cùng paymentId. Idempotency/transactional business layer là yêu cầu riêng.

### 20.12. “HMAC và nonce đều đúng là đủ quyền”

Không. Credential hợp lệ vẫn có thể ký một request đòi quyền không có. Authorization theo principal, resource và tenant là độc lập.

## 21. Bài tập thực hành

### Bài tập 1 — Replay qua hai pods

Vẽ timeline 2 requests giống nhau tới pod A/B có local cache. Tìm điểm thiếu shared state. Thay bằng atomic claim và mô tả linearization point.

### Bài tập 2 — Tính TTL

Với `A=180` giây, `F=20` giây và `M=25` giây, tính TTL bảo thủ. Chứng minh TTL chỉ 180 giây tạo cửa sổ replay nếu timestamp nằm ở future bound.

### Bài tập 3 — Java replay gate

Viết JUnit tests cho `ReplayGateV1`: CLAIMED, REPLAY, UNKNOWN, exception, timestamp stale/future, malformed nonce. Xác nhận chỉ CLAIMED mới dẫn tới ALLOW.

### Bài tập 4 — Redis integration

Dùng client Redis thực gọi `SET key value NX EX ttl` từ hai application instances. Gửi cùng nonce đồng thời. Xác minh chỉ một thành công và duplicate không reset TTL.

### Bài tập 5 — Failover durability

Tạo kịch bản primary trả ACK rồi chết trước khi replica chắc chắn nhận write; phát lại nonce qua node khác. Ghi rõ điều hệ thống của bạn bảo đảm và không bảo đảm.

### Bài tập 6 — Multi-region

Dựng hai stores có eventual replication với delay. Gửi R đồng thời vào A/B. Xác định vì sao cả hai có thể claim N và đề xuất home-region ownership/fencing hoặc strong authority.

### Bài tập 7 — Gateway retry

Giả lập mất response sau nonce claim, gateway retry R sang pod khác. Giải thích replay rejection đúng theo contract và thiết kế operation-status giúp client biết outcome.

### Bài tập 8 — Business idempotency

Ký hai requests có nonce N1/N2 khác nhau cùng paymentId P42. Dùng unique business operation key đảm bảo không double-charge.

### Bài tập 9 — Authorization

Client tenant A có HMAC đúng và nonce mới gọi account tenant B. Kiểm thử credential identity và resource authorization tách nhau.

## 22. Checklist triển khai Replay trong cluster

- [ ] HMAC contract ký method, canonical URI, signed headers, body digest và metadata xác thực có ý nghĩa.
- [ ] `X-Key-Id`, `X-Timestamp`, `X-Nonce` được ràng buộc vào canonical request ký.
- [ ] Verifier tự tính expected HMAC từ trusted key record và request thực nhận.
- [ ] Signature full-length được decode/compare an toàn; header trùng hoặc ambiguity bị reject.
- [ ] Timestamp freshness có max-age/future skew và clocks được kiểm soát.
- [ ] Nonce TTL bao phủ `A+F+M` hoặc deadline đã chứng minh an toàn.
- [ ] Replay namespace chứa protocol version/audience/credential/nonce không nhập nhằng.
- [ ] Mọi verifier liên quan dùng shared authority hoặc ownership/consistency scheme tương đương.
- [ ] Atomic insert-if-absent có TTL trong cùng thao tác, không dùng GET + SET.
- [ ] Nonce duplicate không reset TTL.
- [ ] Nonce chỉ được claim sau HMAC hợp lệ; không làm bẩn store từ request giả.
- [ ] Store timeout/UNKNOWN/outage không silently bypass replay gate.
- [ ] Redis Cluster routing, replication lag, failover và eviction được đánh giá.
- [ ] Kiến trúc phân biệt single-primary atomicity với failover durability/linearizability.
- [ ] Multi-region không dùng independent eventual stores khi yêu cầu strong one-time admission.
- [ ] Key rotation/revocation có cache invalidation và policy overlap đúng.
- [ ] Gateway routing/rewrite không thay signed semantics ngoài contract; admission owner rõ.
- [ ] Backend chỉ tin principal/gateway metadata qua protected trust boundary.
- [ ] Authorization kiểm tra principal/action/resource/tenant riêng.
- [ ] Business idempotency/transactional unique operation key ngăn duplicate effects.
- [ ] Có metrics claim CLAIMED/REPLAY/UNKNOWN, store errors, evictions, clock drift và failover.
- [ ] Có concurrency tests, TTL boundary, multi-node, multi-region, failover và gateway retry tests.
- [ ] Tài liệu kiến trúc công bố những failure modes mà hệ thống **thật sự** chống được.

## 23. Câu hỏi tự kiểm tra

1. **Vì sao HMAC đúng không ngăn replay?** Cùng secret và canonical bytes luôn tạo cùng tag.
2. **Vì sao local map của mỗi pod không đủ?** Node khác không biết nonce đã được claim.
3. **Atomic nonce claim nghĩa là gì?** Chỉ một caller có thể chuyển key absent sang present trong shared authority.
4. **`SET NX EX` giải quyết vấn đề gì?** Một lệnh insert-if-absent kèm TTL, loại race check-then-set.
5. **`GET` rồi `SET` có an toàn không?** Không, hai nodes có thể cùng quan sát absent.
6. **Redis Cluster tự bảo đảm không mất nonce qua failover không?** Không mặc nhiên; async replication có thể mất acknowledged write.
7. **Vì sao TTL thường cần `A+F+M`?** Để bao phủ toàn bộ freshness window, future skew và clock margin.
8. **Khi nonce entry expired, server có phải kiểm timestamp nữa không?** Có, trên mỗi request.
9. **Có thể claim nonce trước khi verify HMAC không?** Không, vì attacker có thể poison replay namespace.
10. **Store timeout có thể xem là nonce mới không?** Không, outcome có thể không chắc; fail closed theo policy.
11. **Eventual multi-region có thể nhận same nonce hai lần không?** Có, trước replication.
12. **Gateway retry nguyên request bị replay reject có phải bug?** Không nhất thiết; cần idempotency/operation status.
13. **Nonce có thay business idempotency không?** Không, caller có thể tạo nonce mới cho cùng operation.
14. **Key đã revoked nhưng nonce entry expired có được phép gửi không?** Không; key status vẫn từ chối.
15. **HMAC/nonce đúng có cấp quyền cho tenant khác không?** Không, authorization là lớp độc lập.
16. **Muốn chống double-admit qua failover phải kiểm gì?** Durability/consistency của acknowledged write, promotion và partition behavior.

## 24. Tài liệu tham khảo

- **RFC 2104 — HMAC: Keyed-Hashing for Message Authentication.** Cơ sở HMAC với shared secret.
- **RFC 4231 — Identifiers and Test Vectors for HMAC-SHA-224/256/384/512.** Known-answer tests.
- **RFC 9110 / RFC 9112 — HTTP Semantics / HTTP/1.1.** Signed request semantics và parsing.
- **RFC 3986 — URI Generic Syntax.** Những khác biệt của canonical path/query.
- **Redis SET command documentation.** Atomic `NX` và expiration `EX`/`PX`.
- **Redis Cluster / Redis replication documentation.** Hash slots, redirects, replication và failover.
- **Java SE 17 — `Clock`, `SecureRandom`, `javax.crypto.Mac`, `MessageDigest.isEqual`.** API time/crypto phục vụ HMAC anti-replay.

**Kết luận:** **Replay trong cluster là bài toán one-time admission trên một replay authority đủ nhất quán**, không chỉ là phép tính HMAC. Server cần xác minh đúng canonical request, key record và timestamp, rồi claim nonce atomically với TTL an toàn, không cho qua nếu kết quả store không chắc. Redis `SET NX EX` chống race trên primary nhưng không tự đảm bảo durability qua mọi failover hoặc eventual multi-region. Hệ thống cần thiết kế thêm key rotation, gateway trust boundary, authorization và transactional idempotency để bảo vệ cả request lẫn business effect.


