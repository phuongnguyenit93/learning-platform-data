# Xác minh song song khi chuyển đổi cơ chế HMAC HTTP request

## 1. Vì sao cần xác minh song song?

Trong module `SECURITY_AUTHENTICATION_HMAC_REQUEST_AUTHENTICATION`, một HTTP request được ký bằng **HMAC và shared secret** trên canonical request chứa method, URI/query, signed headers và/hoặc body digest theo hợp đồng. Server xác minh chữ ký, credential/key ID, timestamp và nonce chống replay trước khi tạo principal; authorization đối với tenant, action và resource vẫn là bước khác.

Khi thay đổi cơ chế xác thực, một hệ thống đang có đối tác sản xuất không thể tùy tiện chuyển toàn bộ traffic từ verifier cũ sang verifier mới. Khác biệt có thể nằm trong **canonicalization**, key lookup, thuật toán MAC, format signature, xử lý gateway/proxy hoặc clock/replay. Nếu chỉ triển khai và chờ 401 từ client thật, quá trình migration dễ gây outage hoặc phát sinh cửa sổ bypass.

**Xác minh song song (*parallel/shadow verification*)** là kỹ thuật đưa **cùng một request đã quan sát** qua hai bộ đánh giá để đo mức tương đương trước khi thay đổi bên có quyền quyết định. Cần phân biệt:

- **Primary verifier**: bộ xác minh **duy nhất** có quyền quyết định authentication và dẫn tới nonce claim/establish principal trong luồng production.
- **Shadow verifier**: bộ xác minh thứ hai chạy theo chế độ quan sát, trả **kết quả nội bộ** để so sánh, **không** quyết định HTTP response, không claim nonce production và không tạo side effect.
- **Dual-signature protocol**: client thật sự gửi **hai bằng chứng chữ ký độc lập** theo hợp đồng đã định nghĩa; đây là một giao thức khác với việc chạy hai implementation trên cùng signature.
- **Dual acceptance**: một chính sách cho phép hai giao thức trong overlap có chủ đích, được giới hạn theo client/key/route/version, **không phải** fallback tùy tiện “chỉ cần một verifier pass”.

Bài thuộc chương **Migration**, tập trung vào di trú an toàn từ bộ verifier cũ sang mới, sử dụng shadow evaluation, canary, feature flags và test evidence, đồng thời giữ nguyên tính toàn vẹn request, chống replay, key rotation, gateway trust và phân quyền.

### Kết quả học tập

Sau bài này, người học có thể:

1. Chọn kiến trúc primary/shadow với một nguồn quyết định authentication.
2. Hiểu trường hợp có thể so sánh cùng một chữ ký và trường hợp bắt buộc có **chữ ký V2 riêng**.
3. Thiết kế kết quả phân loại `MATCH`, `DIVERGENCE`, `NOT_EVALUABLE`, `SHADOW_ERROR` mà không làm hở quyết định.
4. Không claim nonce hai lần hoặc cho shadow gây replay giả.
5. Triển khai Java 17/Spring Security 6 theo hướng side-effect-free shadow.
6. Kiểm thử canonical method/URI/headers/body qua gateway, key rotation, timestamp và tenancy.
7. Xây migration gates, canary/rollback và metric/alert có khả năng phát hiện bypass.

## 2. Bài toán minh họa: V1 → V2

Giả sử hệ thống có hai bộ verifier:

| Thuộc tính | V1 (đang chặn request) | V2 (dự kiến thay thế) |
| --- | --- | --- |
| Định danh protocol | `hmac-v1-sha256` | `hmac-v2-sha256` |
| HMAC | HmacSHA256 | HmacSHA256 |
| Canonicalization | Legacy xử lý path/query | Quy tắc raw-target rõ ràng |
| Signed headers | Method + path + timestamp + body hash | Method + raw target + key ID + signed headers + timestamp + nonce + body hash |
| Key lookup | Client ID hoặc key ID cũ | Exact key ID/version đã provision |
| Replay | Timestamp-only hoặc nonce policy cũ | Timestamp + atomic nonce claim |
| Gateway | Có thể rewrite request | Có contract external/internal target |
| State | Production primary | Chạy quan sát, chưa cấp quyền |

**Vấn đề:** một chữ ký V1 không thể tự trở thành chữ ký V2 nếu canonical bytes và signed-field coverage khác nhau. Nếu client chỉ gửi `X-Signature-V1`, shadow verifier V2 không có đầy đủ **V2 proof** để kết luận request “V2 valid”. Nó có thể kiểm tra dữ liệu, đánh giá canonical compatibility hoặc tính expected MAC phục vụ công cụ kiểm thử, nhưng không được ghi `V2_VERIFIED` chỉ vì có V1 proof.

Một kế hoạch khác có thể chuyển từ `HmacSHA256` sang `HmacSHA512` hoặc từ K3 sang K4. Khi **algorithm, secret hoặc canonical contract** khác, cần signer V2 tạo **MAC riêng** để kiểm tra V2 đầy đủ.

### Ma trận các trường hợp có thể so sánh

| Thay đổi | Dùng lại một signature để so hai verifier? | Kết luận hợp lệ |
| --- | --- | --- |
| Refactor code nhưng giữ cùng contract, key, MAC | **Có** | So sánh verifier output trên cùng evidence |
| Đổi nơi chạy (gateway → backend), giữ đúng proof/bytes | Có điều kiện | So sánh tại trust boundary đã chốt |
| Đổi cách lấy raw URI nhưng contract không đổi | Có điều kiện | Negative/positive kiểm tra byte-parity |
| Đổi canonical contract V1→V2 | **Không** để xác minh V2 hợp lệ | Cần signature V2 riêng hoặc golden fixture |
| Đổi key K3→K4 | **Không** | Cần HMAC ký bằng K4; key ID mới |
| Đổi HmacSHA256→HmacSHA512 | **Không** | Cần MAC V2 riêng, đúng length/encoding |
| Thêm nonce cho V2 khi V1 chưa ký nonce | **Không** | Client phải ký nonce trong V2 |
| Thay đổi authorization sau xác thực | Không phải chỉ HMAC | Test authz policy độc lập |

## 3. Threat model khi chạy hai verifier cùng lúc

Rủi ro lớn nhất là **thêm đường chấp nhận** mà không nhận ra.

~~~mermaid
flowchart LR
    C["Client HTTP request"] --> G["Gateway / HMAC adapter"]
    G --> S["Immutable request evidence"]
    S --> P["Primary verifier"]
    S -. "Bản sao giới hạn" .-> H["Shadow evaluator"]
    P --> R["Atomic nonce claim duy nhất"]
    R --> A["Authenticated principal"]
    A --> Z["Authorization + business"]
    H --> M["Outcome comparison, metrics, audit"]
    H -. "KHÔNG được quyết định" .-> X["No business / no shared nonce write"]
~~~

Các lỗi cần phòng vệ:

- Code dùng `primaryPass || shadowPass`; request bị V1 từ chối nhưng V2 có bug lại được chấp nhận.
- Verifier mới thử mọi secret/key version để “giúp client chuyển đổi” và tạo key fallback.
- Shadow gọi replay store `SET NX` trước primary làm **request hợp lệ** bị replay giả.
- Primary thành công xong shadow gọi verifier đầy đủ và bị đánh dấu replay; dashboard báo mismatch giả.
- Shadow ném exception làm traffic production trả 500/503 dù primary không có vấn đề.
- Shadow deserialize body hoặc copy toàn bộ body không giới hạn gây DoS/latency.
- Shadow tạo `Authentication` trong shared `SecurityContextHolder`/Reactor Context.
- Client chỉnh `X-Signing-Version` nhưng protocol selector không được HMAC ràng buộc.
- Gateway đổi URI hoặc gzip body giữa hai path khiến sự sai khác chỉ là lỗi quan sát.
- Dữ liệu test/debug chứa secret, raw body và signature có thể bị phát lại.
- Dual acceptance vô thời hạn tạo **downgrade**; key V1 bị revoke vẫn “hồi sinh” khi fallback.

**Ranh giới:** shadow là một công cụ kiểm chứng migration, **không phải nguồn authentication trust**.

## 4. Ba chế độ vận hành phải đặt tên rõ ràng

| Mode | Decision owner | Shadow behavior | Mục đích |
| --- | --- | --- | --- |
| `V1_ENFORCE_ONLY` | V1 | Không có | Baseline trước migration |
| `V1_ENFORCE_V2_SHADOW` | V1 | V2 đánh giá read-only | So sánh trước canary |
| `V2_ENFORCE_V1_SHADOW` | V2 | V1 read-only, không fallback | Theo dõi regression sau cutover |
| `V2_ENFORCE_ONLY` | V2 | Không có | Hoàn tất migration |
| `CONTROLLED_DUAL_ACCEPT` | Policy versioned, chọn một suite cụ thể | Không fallback tùy tiện | Chấp nhận hai suite có deadline |

`CONTROLLED_DUAL_ACCEPT` là trường hợp đặc biệt: request khai **một version được ký**, server chọn **đúng một verifier** bằng allowlist theo route/credential; các request dùng V1 chỉ pass khi policy còn cho V1. Đây không phải `V1.verify || V2.verify`.

### Trạng thái không an toàn

~~~java
// SAI: shadow trở thành đường bypass authentication.
boolean accepted =
    oldVerifier.verify(request) || newVerifier.verify(request);
if (accepted) {
    chain.doFilter(request, response);
}
~~~

Cũng không nên:

~~~java
// SAI: khi V2 fail thì thử V1 không có policy/version binding.
try {
    return verifyV2(request);
} catch (BadCredentialsException e) {
    return verifyV1(request);
}
~~~

Thay vào đó, **decision policy** quyết định suite và verifier có thẩm quyền trước khi kiểm tra MAC; shadow chỉ đo.

## 5. Thiết kế bất biến: một quyết định, một nonce claim, một principal

Một migration an toàn cần giữ các invariants:

1. Mỗi inbound request có **tối đa một authoritative authentication decision**.
2. Mỗi accepted signed request có **một path claim nonce production**; shadow không tạo claim bổ sung.
3. Chỉ primary được phát hành authenticated principal vào `SecurityContext` hoặc Reactor Context.
4. Authorization dựa vào principal đã xác thực, không dựa shadow result.
5. Request không hợp lệ theo primary **không được** shadow “cứu”.
6. Key state, secret, suite policy được kiểm tra theo **exact key ID** và approval hiện hành.
7. Timestamp/nonce, key ID/suite version phải được signed theo hợp đồng hiệu lực.
8. Gateway/proxy phải đưa đến verifier đúng canonical target/body bytes của contract.
9. Shadow failure không làm production fail open; lỗi vận hành của shadow cần được **cô lập và ghi nhận**.
10. Bất kỳ thay đổi **chủ ý** về acceptance policy nào phải được review, version và đánh giá riêng.

Điểm 9 có nuance: **shadow failure được phép bỏ qua như quan sát** khi primary đã quyết định độc lập; đây không phải việc bỏ qua lỗi nonce store/secret manager của **primary**. Nếu primary thiếu nonce store, phải fail closed dù shadow báo pass.

## 6. Luồng xác thực và thứ tự thực thi

~~~mermaid
sequenceDiagram
    participant C as Client
    participant F as HMAC Adapter
    participant P as Primary Verifier
    participant N as Production Nonce Store
    participant H as Shadow Evaluator
    participant M as Metrics
    participant B as Business
    C->>F: Signed HTTP request
    F->>F: Bounded raw body capture + parsed evidence
    F->>P: Authenticate primary proof/policy
    P->>N: Claim nonce only after MAC valid
    N-->>P: FIRST_USE / ALREADY_USED / UNKNOWN
    P-->>F: Authoritative accepted or rejected
    F-->>H: Sanitized snapshot / bounded shadow task
    H-->>M: Pure evaluation outcome; no replay writes
    alt primary accepted and authz allowed
        F->>B: Continue once
    else primary denied or dependency unavailable
        F-->>C: 401 / 503 theo contract
    end
~~~

Sơ đồ biểu diễn một **luồng logic**; phần shadow có thể chạy đồng thời hoặc sau primary tùy mô hình. Để tránh ảnh hưởng độ trễ production, có thể chạy shadow bất đồng bộ có giới hạn hoặc sample traffic, nhưng **không gửi các raw secrets/body sang queue/log không tin cậy**.

Cần có thời gian và context cùng nguồn cho hai đánh giá: cùng raw method/URI/headers/body, cùng observed timestamp và policy/key revision đã được chốt (hoặc ghi revision riêng để giải thích divergence). Không giả định hai lần đọc secret registry ở hai thời điểm khác nhau sẽ luôn trả cùng key state.

### Không để shadow đụng authenticated context

Trong Servlet, `SecurityContextHolder` mặc định gắn với execution context/thread; shadow tuyệt đối không set/clear principal của primary. Trong WebFlux, `ReactiveSecurityContextHolder` dùng Reactor Context; shadow observer chỉ nhận immutable evidence cần thiết, không mutate authenticated context hay thực thi handler.

## 7. Xác minh song song khác dual-signature như thế nào?

**Shadow verifier khi không đổi giao thức:** cả hai implementations hiểu `HMAC-REQUEST-V1` và cùng key K4. Client chỉ gửi một signature. Hai bên có thể tính expected MAC từ cùng canonical bytes và so sánh; đây là parity test thực sự.

**Shadow verifier khi thay giao thức:** V2 yêu cầu thêm signed nonce hoặc thay body digest. Chữ ký V1 chỉ xác thực message V1. Muốn biết V2 hợp lệ, client phải gửi **V2 signature** hoặc một conformance fixture đã được signer V2 ký độc lập. Ví dụ:

~~~http
POST /api/hmac/orders HTTP/1.1
X-Key-Id-V1: partner-a-k3
X-Signature-V1: <signature-under-K3-and-V1>
X-Key-Id-V2: partner-a-k4
X-Signing-Version-V2: HMAC-REQUEST-V2
X-Timestamp: 2026-11-28T04:00:00Z
X-Nonce: 45859ac6-a453-43a5-8d42-33d7566b7f73
X-Signature-V2: <signature-under-K4-and-V2>
Content-Type: application/json

{"orderId":"o-401"}
~~~

Đây là **dual-signature protocol minh họa**, chưa đầy đủ RFC/HTTP contract. Cần chốt chính xác:

- Hai signatures có ký cùng method/target/body bytes không?
- K3/V1 và K4/V2 liên kết đến **cùng principal/client và authorized audience** bằng registry không?
- Version, key ID, timestamp và nonce được HMAC ràng buộc trong **từng signature** ra sao?
- Trường signature nào bị loại khỏi canonical bytes để tránh vòng lặp?
- Nếu xóa một trong hai signature, request bị parser từ chối hay được xử lý bằng policy nào?
- Nếu gateway rewrite URI, hai verifier nhìn target nào?
- Có giới hạn header length/count và chống duplicate header/HTTP header confusion không?
- **Primary** claim nonce production một lần; shadow không ghi nonce production.
- Khi client V2 chuyển sang primary, request phải có V2 proof hợp lệ, không dùng V1 proof làm fallback.

Không nên ký toàn bộ tập headers bao gồm hai trường signature theo kiểu vòng lặp. Có thể dùng canonical core fields chung và versioned domain separators, hoặc signed manifest/binding rõ, nhưng phải có golden vectors độc lập.

## 8. Chỉ có signature V1: kết quả V2 phải là NOT_EVALUABLE

Khi client cũ chỉ gửi `X-Signature-V1`:

| Câu hỏi | Shadow V2 có thể kết luận? |
| --- | --- |
| Raw target parsing V2 có chạy được? | Có |
| Body digest V2 có đúng golden bytes? | Có, nếu có fixture/known expected |
| Key ID V2 đã provision chưa? | Có thể biết từ registry, nếu được phép đọc |
| Timestamp/nonce có đúng format V2? | Có thể kiểm tra read-only |
| V2 signature có hợp lệ không? | **Không**, nếu không có V2 signature |
| Nonce mới có thể atomic claim không? | **Không** qua shadow read-only |
| V2 authentication thành công production? | **Không được khẳng định** |

Không đếm `V2_VALID` chỉ vì server tự tính được `HMAC(K4, C_V2)` mà **không có chữ ký V2 client gửi để đối chiếu**. Ai biết server secret cũng có thể tự tạo expected MAC; nó không chứng minh client đang ký đúng V2.

Một cách nâng chất lượng migration là triển khai SDK có thể gửi cả V1/V2 signatures trong canary đã được duyệt, sau đó shadow kiểm tra **V2 proof**. Những client chưa triển khai V2 được phân loại riêng là `NOT_EVALUABLE`, không tính là divergence.

## 9. Kết quả so sánh cần ngữ nghĩa rõ

Một evaluator có thể trả:

~~~java
enum CryptoOutcome {
    VALID,
    INVALID_SIGNATURE,
    INVALID_INPUT,
    UNKNOWN_CREDENTIAL,
    DISABLED_CREDENTIAL,
    UNSUPPORTED_SUITE,
    NOT_EVALUABLE,
    EVALUATION_ERROR
}

enum ParallelComparison {
    MATCH_VALID,
    MATCH_REJECTED,
    DIVERGENCE_PRIMARY_ONLY,
    DIVERGENCE_SHADOW_ONLY,
    NOT_COMPARABLE,
    SHADOW_ERROR
}
~~~

Các tên này là model nội bộ, không phải HTTP public codes. Khi **cùng một proof** và cùng eligibility policy, `VALID/VALID` hoặc `INVALID/INVALID` có ý nghĩa parity.

Với **hai proof V1/V2** có chủ đích khác nhau, `primary VALID, shadow INVALID` có thể là **migration readiness issue**, nhưng không tự chứng minh có bug trong verifier: có thể key V2 chưa provision, SDK ký canonical V2 sai, signed header thiếu hoặc policy không cho phép V2.

Không cộng `NOT_EVALUABLE` vào mẫu số “V2 signature mismatch rate” theo cách khiến rollout readiness trông tốt giả. Cần theo dõi **coverage** riêng:

\[
coverage_{\mathrm{shadow}}
=\frac{\text{requests có đủ V2 proof và đánh giá thành công}}
{\text{requests thuộc cohort cần đánh giá V2}}
\]

Chỉ so divergence trên tập có đủ evidence, cùng semantics và policy revision phù hợp.

## 10. Java 17: tách pure cryptographic evaluation khỏi nonce claim

Để shadow không tự ghi replay store, tách API:

~~~java
import java.time.Instant;
import java.util.Arrays;

record SignedRequestEvidence(
    String clientId,
    String keyId,
    String suiteId,
    String method,
    String rawTarget,
    String timestamp,
    String nonce,
    byte[] canonicalBytes,
    byte[] signatureBytes
) {
    SignedRequestEvidence {
        // Clone tránh mutable bytes bị đổi sau capture.
        canonicalBytes = canonicalBytes.clone();
        signatureBytes = signatureBytes.clone();
    }

    @Override
    public byte[] canonicalBytes() {
        return canonicalBytes.clone();
    }

    @Override
    public byte[] signatureBytes() {
        return signatureBytes.clone();
    }
}

record CryptoEvaluation(
    CryptoOutcome outcome,
    String credentialRevision,
    String canonicalContract
) {}

interface PureHmacEvaluator {
    // KHÔNG có claim nonce, auth context hay side effect.
    CryptoEvaluation evaluate(
        SignedRequestEvidence evidence,
        Instant referenceTime
    );
}

interface AtomicNonceClaimer {
    // Chỉ authoritative path được gọi.
    boolean firstUse(String credentialId, String nonce);
}
~~~

**Lưu ý:** Đây là type minh họa. Trong production, `canonicalBytes` phải được **server tự dựng từ raw HTTP request** theo contract, không tin một trường canonical bytes do client gửi. `SignedRequestEvidence` lưu secret? **Không**. Nó chứa signature/canonical bytes nhưng có thể là dữ liệu nhạy cảm; chỉ chuyển tới shadow evaluator trong trust boundary được bảo vệ, không lưu ra analytics pipeline.

`record` clone bytes giúp tránh mutate sau capture nhưng tạo thêm allocation. Với body lớn, nên dùng request-scoped immutable evidence hoặc digest/reference được quản lý có limit, không nhân đôi raw body không giới hạn. Không dùng shadow queue tùy tiện để chứa raw payload payment.

## 11. Java 17: primary quyết định, shadow chỉ đo

Ví dụ tối giản bên dưới cho thấy chỗ cần đặt side effects. Trong một hệ thống đầy đủ, `PureHmacEvaluator` còn phải kiểm tra credential ACTIVE, exact key ID, signing suite, freshness của key và canonical bytes; phần timestamp/nonce ở primary phải có validator riêng.

~~~java
import java.time.Clock;

record PrimaryDecision(
    boolean authenticated,
    String reason
) {}

final class ParallelHmacAuthentication {
    private final PureHmacEvaluator primary;
    private final PureHmacEvaluator shadow;
    private final AtomicNonceClaimer nonceStore;
    private final ShadowOutcomeSink sink;
    private final Clock clock;

    ParallelHmacAuthentication(
            PureHmacEvaluator primary,
            PureHmacEvaluator shadow,
            AtomicNonceClaimer nonceStore,
            ShadowOutcomeSink sink,
            Clock clock) {
        this.primary = primary;
        this.shadow = shadow;
        this.nonceStore = nonceStore;
        this.sink = sink;
        this.clock = clock;
    }

    PrimaryDecision authenticate(
            SignedRequestEvidence evidence,
            String trustedCredentialId) {
        var observedAt = clock.instant();

        // Primary xử lý đúng signing proof được policy chọn.
        CryptoEvaluation p = primary.evaluate(
            evidence, observedAt);

        // Shadow là side-effect-free; không tác động
        // response, principal hoặc nonce production.
        try {
            CryptoEvaluation s = shadow.evaluate(
                evidence, observedAt);
            sink.record(p, s); // bounded, sanitized metrics
        } catch (RuntimeException ignored) {
            sink.recordShadowFailure(); // no sensitive data
        }

        if (p.outcome() != CryptoOutcome.VALID) {
            return new PrimaryDecision(
                false, "authentication_failed");
        }

        // Ví dụ giả định freshness và credential ACTIVE
        // đã được primary.evaluate xác thực chính xác.
        boolean firstUse = nonceStore.firstUse(
            trustedCredentialId, evidence.nonce());

        if (!firstUse) {
            return new PrimaryDecision(false, "replay");
        }

        return new PrimaryDecision(true, "authenticated");
    }
}

interface ShadowOutcomeSink {
    void record(CryptoEvaluation primary,
                CryptoEvaluation shadow);
    void recordShadowFailure();
}
~~~

**Đoạn này là skeleton**, không phải implementation production an toàn hoàn chỉnh: chưa xử lý `UNKNOWN` từ nonce store (boolean không đủ cho timeout), chưa tạo principal, chưa kiểm tra request binding của `trustedCredentialId`, chưa authorization và có thể bị shadow làm tăng latency vì chạy trước nonce claim. Bản production cần:

- Replay claim trả **FIRST_USE / ALREADY_USED / UNKNOWN** để fail closed.
- `trustedCredentialId` phải đến từ registry sau MAC đúng, không từ client header.
- Shadow sink không được block/throw trên request path; có timeout/bulkhead và sampling.
- Chọn **đúng một primary** theo request/route policy đã version hóa.
- Nếu shadow chạy async, snapshot bytes và revision phải có ownership/lifecycle rõ.
- Shadow và primary cùng nhận **proof phù hợp**; không giả định một V1 proof đủ cho V2.
- Nếu shadow cần kiểm tra credential state thì chỉ read-only, không mutate audit/replay store.

Ví dụ cố ý cô lập ý tưởng: **primary quyết định, shadow chỉ quan sát**.

## 12. Nên chạy shadow trước, sau hay đồng thời?

Có ba lựa chọn:

| Chiến lược | Lợi điểm | Rủi ro/điều kiện |
| --- | --- | --- |
| Sync shadow trước response | Có kết quả ngay, dễ so với primary | Tăng p95/p99; exception phải được cô lập |
| Sync shadow sau primary evaluation | So chính xác kết quả primary | Có thể chặn đường response; cần budget |
| Bounded async shadow | Giảm độ trễ người dùng | Queue overflow, cancellation, snapshot/lifecycle |
| Offline conformance/replay traffic | Không chạm production hot path | Privacy, freshness và khả năng tái hiện nonce |

**Async** không có nghĩa tạo thread cho mọi request hoặc đẩy body lên queue vô hạn. Một observer tốt có:

- Bounded queue/concurrency, sample rate và per-route budget.
- Timeout/shadow drop count, không ảnh hưởng authentication decision.
- Read-only credential access có IAM tối thiểu.
- Không log secret/expected MAC/full signature/raw body.
- Không gọi business handler, webhook hoặc event producer.
- Có circuit breaker **chỉ dành cho shadow**; lỗi primary vẫn fail closed.
- Có correlation ID/bucket labels giới hạn, không raw client/tenant làm metrics labels.

Nếu migrate logic nonce store (Redis driver/namespace), không thể xác minh atomicity chỉ bằng pure shadow. Phải có **integration/fault-injection** riêng với isolated store và mô hình replay thật.

## 13. Double-claim nonce: bẫy nghiêm trọng của xác minh song song

Một request hợp lệ với nonce N có MAC đúng theo cả hai verifiers. Nếu cả hai tự chạy full `authenticate()` rồi gọi cùng Redis key:

~~~text
Primary: SET hmac:nonce:(K4,N) NX → FIRST_USE
Shadow:  SET hmac:nonce:(K4,N) NX → ALREADY_USED
~~~

Shadow sẽ báo “replay detected” dù đây là **cùng một inbound request**. Đảo lịch chạy còn nghiêm trọng hơn:

~~~text
Shadow:  FIRST_USE
Primary: ALREADY_USED → request hợp lệ bị 401
~~~

Nếu code lại dùng `primaryPass || shadowPass`, shadow có thể chấp nhận request đáng lẽ primary reject, tạo bypass. Cả hai trường hợp đều không chấp nhận được.

### Quy tắc triển khai

1. Xác minh MAC/canonical/suite/credential read-only có thể chạy song song.
2. Timestamp validation read-only có thể chạy trên cùng `observedAt`.
3. Nonce claim production thực hiện **duy nhất một lần** bởi authoritative path.
4. Shadow không được viết vào production nonce namespace.
5. Nếu shadow dùng store mô phỏng, kết luận chỉ mang nghĩa test/dry-run, **không** chứng minh atomic replay guarantee.
6. Với migration nonce store (Redis A→B), cần kế hoạch riêng xác định **store nào quyết định**, cách mirror/dual-write nếu áp dụng và consistency model; không âm thầm xem hai `SET NX` độc lập là một quyết định chung.
7. Nếu primary nonce store trả UNKNOWN/timeout, fail closed; shadow FIRST_USE không được cứu request.

Một bài test chất lượng cần assert **số lần claim thực tế = 1** cho một request được chấp nhận, ngay cả khi shadow enabled và retry/error dispatch xảy ra.

## 14. Timestamp và key-state parity: đừng so kết quả ở hai thời điểm khác nhau

Hai bộ verifier có thể khác kết quả **mà không có lỗi canonicalization** nếu dùng các điều kiện đánh giá khác nhau:

| Khác biệt | Ví dụ | Tác động |
| --- | --- | --- |
| Clock | Primary kiểm tra 04:00:00; shadow xử lý lúc 04:06:00 | Timestamp vừa hết window |
| Key revision | Primary thấy K4 ACTIVE; shadow đọc sau khi REVOKED | Policy divergence hợp lý theo thời điểm |
| Allowlist | Primary cho V1; shadow chỉ nhận V2 | Expected migration difference |
| Credential cache | Primary cache revision 11, shadow revision 12 | Stale state cần đánh giá riêng |
| Canonical target | Primary ký external URI, shadow dùng internal URI | Proxy/canonical mismatch |
| Body bytes | Shadow copy body sau khi stream đã consumed | Hash rỗng hoặc byte corruption |
| Nonce store | Primary đã claim N; shadow truy vấn N sau đó | “Already used” là trạng thái tự nhiên |
| Signed proof | V1 có MAC cũ; V2 chưa có signature | `NOT_EVALUABLE`, không phải invalid |

Để so sánh công bằng, thu thập **immutable request snapshot** tại một điểm ingress rõ, cùng `observedAt` và ghi metadata về policy/key revision. Nếu không thể pin cùng revision vì registry dynamic, kết quả cần mang nhãn `POLICY_REVISION_DIFFERENT` hoặc `NOT_COMPARABLE`, không tự tính là V2 cryptographic failure.

### Kiểm tra timestamp

Giả sử server chấp nhận:

\[
|t_{\mathrm{server}}-t_{\mathrm{signed}}|\le W
\]

Hai implementations phải dùng **cùng W, precision, inclusive/exclusive boundary và nguồn Clock** cho test parity. Với `W=5 phút` và `Clock.fixed(2026-11-28T04:00:00Z)`, test thời điểm 03:55:00, 04:05:00 và các mốc ±1 giây để tìm drift. Production có thể dùng NTP/monotonic duration khác, nhưng không dùng wall-clock timer để đo latency rồi nhầm với timestamp policy.

### Credential revocation

Shadow có thể phát hiện provider mới lấy được trạng thái K3 REVOKED trong khi primary đang cache ACTIVE. Đây là **security signal cần xử lý**, không phải lý do bật shadow lên làm decision owner bất ngờ. Khi primary không thỏa freshness policy, phải **sửa hoặc fail closed primary** qua một thay đổi kiểm soát, không chờ đủ một “parity threshold” mới bảo vệ key đã revoke.

## 15. Key rotation và migration verifier là hai trục riêng

Key rotation (`K3→K4`) và refactor verifier (`Implementation A→B`) không phải một thay đổi. Nên tách để dễ quy nguyên nhân:

| Hoạt động | Key ID | Secret | Canonical contract | Verifier |
| --- | --- | --- | --- | --- |
| Baseline | K3 | S3 | V1 | A primary |
| Refactor parity | K3 | S3 | V1 | A primary + B shadow |
| Verifier cutover | K3 | S3 | V1 | B primary |
| Key rotate | K4 | S4 | V1 | B primary, overlap K3 có hạn |
| Contract migrate | K4/V2 key được provision | S4 hoặc key V2 riêng theo policy | V2 | B V2 primary |

Thứ tự này không bắt buộc cho mọi hệ thống, nhưng giúp cô lập lỗi. Khi cần thay cả canonical contract và key, hãy dùng test matrix đa trục và **hai signatures độc lập**, không coi signature cũ tương đương signature mới.

### Exact key lookup là bất biến

Nếu HTTP request khai `X-Key-Id: partner-a-k4`, verifier chỉ được dùng secret gắn với K4:

~~~java
// SAI: fallback sang K3 nếu K4 không khớp.
for (Credential c : registry.allForClient(clientId)) {
    if (verifyMac(c.secret(), request)) {
        return authenticated(clientId);
    }
}
~~~

Tư duy đúng:

~~~text
parse exact keyId K4
  -> registry.getExact(K4)
  -> check key ACTIVE + suite allowed + owner identity
  -> MAC verify using ONLY key for K4
  -> timestamp/nonce check
  -> authenticated principal
~~~

Với credential state `REVOKED`, MAC toán học đúng cũng phải bị từ chối. Shadow không có quyền thử key revoked để rồi báo “pass” như một lựa chọn recovery production.

### Replay namespace khi đổi key/version

Nếu nonce scope theo `(credentialId, nonce)`, K3 và K4 có thể có namespaces độc lập. Nếu cùng một logical client có thể tạo bằng chứng giống nhau xuyên version, cần xác định có muốn scope theo `(clientId, nonce)` hoặc signed request digest không; phải có threat model, không đổi ngầm trong migration. Ngay cả với namespace tách, SDK vẫn phải tạo **nonce mới cho từng request attempt**.

## 16. Spring MVC/SecurityFilterChain: điểm chèn shadow

Một flow Servlet thường là:

~~~text
Spring Security 6 / Servlet
  OncePerRequestFilter
    -> bounded raw-body capture/replayable wrapper
    -> parse canonical signed evidence + version/key ID
    -> AuthenticationManager / HmacAuthenticationProvider
         -> PRIMARY cryptographic evaluation
         -> exact key state + timestamp
         -> ONE atomic nonce claim
         -> principal
    -> AuthorizationManager / tenant-resource policy
    -> MVC controller

  Shadow observer (read-only)
    -> copy immutable/sanitized evidence from same request
    -> evaluate second implementation/second proof if present
    -> bounded metrics; no SecurityContext writes or nonce claim
~~~

Một triển khai tốt sẽ đặt **migration orchestration** trong một service tập trung, thay vì thêm hai HMAC filters có thể cùng đọc body/cùng gọi `AuthenticationManager`. Nếu đăng ký hai `OncePerRequestFilter` hoặc vừa đăng ký global Servlet filter vừa đưa filter đó vào `SecurityFilterChain`, R1 có thể bị claim nonce hai lần và thất bại ngay khi dùng khóa đúng.

**Hãy test route matching**, tránh để security filter hoạt động trên một route rồi controller khác lại được bỏ qua. Nếu request có body, filter phải replay bytes đúng cho `@RequestBody`, không giả định `ContentCachingRequestWrapper` tự tạo stream rewind.

### Exception semantics

`AuthenticationException` xảy ra trước `DispatcherServlet` không chắc được bắt bởi `@RestControllerAdvice`. Đường production dùng `AuthenticationEntryPoint` hoặc authentication failure handler. Shadow exceptions nên được bắt tại observer boundary và đưa vào internal metrics, **không** đổi primary response thành 401 hay 500.

Tương tự, lỗi của **primary** secret manager/nonce store cần fail closed, thường 503 theo hợp đồng, không thể bị biến thành “shadow timeout, bỏ qua”.

## 17. Java 17/JUnit 5: test shadow không được nới quyền

Ví dụ kiểm thử trực tiếp `ParallelHmacAuthentication` đã trình bày trong mục 11. Bản test sử dụng fake clock và in-memory counter; nó **chỉ kiểm chứng orchestration**, chưa kiểm thử HMAC-SHA256 hoặc Redis production.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;

class ParallelHmacAuthenticationTest {
    private final Clock fixedClock = Clock.fixed(
        Instant.parse("2026-11-28T04:00:00Z"),
        ZoneOffset.UTC);

    private SignedRequestEvidence fixture() {
        return new SignedRequestEvidence(
            "partner-a", "partner-a-k4",
            "hmac-v1-sha256", "POST",
            "/api/orders", "2026-11-28T04:00:00Z",
            "58fa55f1-bd5a-4735-8ad2-1d2a207f7d33",
            "canonical-test-bytes".getBytes(
                java.nio.charset.StandardCharsets.UTF_8),
            new byte[32]
        );
    }

    private static class TestSink implements ShadowOutcomeSink {
        int comparisons;
        int failures;

        @Override
        public void record(CryptoEvaluation p, CryptoEvaluation s) {
            comparisons++;
        }

        @Override
        public void recordShadowFailure() {
            failures++;
        }
    }

    @Test
    void shadowValidCannotOverridePrimaryReject() {
        AtomicInteger nonceCalls = new AtomicInteger();
        PureHmacEvaluator primary = (e, at) ->
            new CryptoEvaluation(
                CryptoOutcome.INVALID_SIGNATURE, "r7", "V1");
        PureHmacEvaluator shadow = (e, at) ->
            new CryptoEvaluation(
                CryptoOutcome.VALID, "r7", "V1");
        AtomicNonceClaimer nonceStore = (id, nonce) -> {
            nonceCalls.incrementAndGet();
            return true;
        };
        TestSink sink = new TestSink();

        var subject = new ParallelHmacAuthentication(
            primary, shadow, nonceStore, sink, fixedClock);

        PrimaryDecision decision =
            subject.authenticate(fixture(), "cred-7f31");

        assertFalse(decision.authenticated());
        assertEquals(0, nonceCalls.get());
        assertEquals(1, sink.comparisons);
    }

    @Test
    void primaryValidClaimsOnceEvenIfShadowRejects() {
        AtomicInteger nonceCalls = new AtomicInteger();
        PureHmacEvaluator primary = (e, at) ->
            new CryptoEvaluation(
                CryptoOutcome.VALID, "r7", "V1");
        PureHmacEvaluator shadow = (e, at) ->
            new CryptoEvaluation(
                CryptoOutcome.INVALID_SIGNATURE, "r7", "V1");
        AtomicNonceClaimer nonceStore = (id, nonce) -> {
            nonceCalls.incrementAndGet();
            return true;
        };

        var subject = new ParallelHmacAuthentication(
            primary, shadow, nonceStore,
            new TestSink(), fixedClock);

        assertTrue(subject.authenticate(
            fixture(), "cred-7f31").authenticated());
        assertEquals(1, nonceCalls.get());
    }

    @Test
    void shadowExceptionNeverAuthenticatesRequest() {
        AtomicInteger nonceCalls = new AtomicInteger();
        PureHmacEvaluator primary = (e, at) ->
            new CryptoEvaluation(
                CryptoOutcome.INVALID_SIGNATURE, "r7", "V1");
        PureHmacEvaluator shadow = (e, at) -> {
            throw new IllegalStateException("shadow_unavailable");
        };
        AtomicNonceClaimer nonceStore = (id, nonce) -> {
            nonceCalls.incrementAndGet();
            return true;
        };
        TestSink sink = new TestSink();

        var subject = new ParallelHmacAuthentication(
            primary, shadow, nonceStore, sink, fixedClock);

        assertFalse(subject.authenticate(
            fixture(), "cred-7f31").authenticated());
        assertEquals(0, nonceCalls.get());
        assertEquals(1, sink.failures);
    }
}
~~~

**Giới hạn:** fixture dùng byte arrays tổng hợp, không phải HMAC signature thật; unit test này chỉ bảo vệ **quyền quyết định**, không đánh giá crypto correctness. Một test khác phải dùng signer độc lập, golden canonical bytes, wrong-secret, timestamp/nonce và key lifecycle.

### Test side-effect-free phải cụ thể

Dùng Mockito spy ở integration tests để assert:

~~~java
// Khung assertion khi đã inject spy vào production adapters.
verify(productionNonceStore, times(1)).claim(any(), any());
verify(shadowNonceStore, never()).claim(any(), any());
verify(paymentService, times(1)).createPayment(any());
~~~

Các assertions trên cần điều chỉnh theo kiến trúc: nếu shadow không có nonce store reference thì test `verifyNoInteractions(...)` có thể là cách mạnh hơn. Đừng đánh giá cùng request hai lần qua full `AuthenticationManager` rồi kỳ vọng shadow tự read-only.

## 18. Spring WebFlux: reactive shadow và lifecycle của body

Trong WebFlux, `ServerHttpRequest.getBody()` là `Flux<DataBuffer>`. Không thể tùy tiện subscribe hai lần vào body gốc và hy vọng hai bộ verifier đều nhận cùng bytes. Nếu một filter consume raw body để hash, downstream controller cũng cần cách replay đúng; pooled `DataBuffer` có lifecycle release/cancel riêng.

Một flow phù hợp:

1. Lấy raw body bytes bằng **bounded capture** hoặc một streaming strategy đã được review.
2. Xác minh size limit **trên bytes thực**, không tin `Content-Length` đơn lẻ.
3. Tạo request-scoped immutable `BodyEvidence` gồm length/body digest và một replayable body source nếu controller cần.
4. Hai pure evaluators chỉ đọc cùng evidence, không tự subscribe HTTP request body.
5. Primary thực hiện nonce claim qua reactive Redis driver sau MAC đúng.
6. Shadow kết thúc bằng metrics, không mutate Reactor Context/secret/key state.
7. Release pooled buffers trên complete/error/cancel; không cache vô hạn `Flux<DataBuffer>`.
8. Nếu shadow được bật theo sampling, không nhân đôi full-body copy không cần thiết.

### Reactor pseudo-flow

~~~java
// Sơ đồ dạng Reactor pseudocode; types thuộc dự án.
return captureBodyBounded(exchange, MAX_BODY_BYTES)
    .flatMap(evidence ->
        primaryEvaluate(evidence)
            .flatMap(primary -> {
                // Shadow side-effect-free có bounded execution.
                submitShadowObservation(evidence, primary);

                if (!primary.cryptoValid()) {
                    return Mono.error(
                        new BadCredentialsException(
                            "authentication_failed"));
                }

                // Claim nonce duy nhất trên authoritative path.
                return atomicNonceStore.claim(
                        primary.credentialId(),
                        evidence.nonce())
                    .flatMap(result -> switch (result) {
                        case FIRST_USE -> Mono.just(
                            primary.authentication());
                        case ALREADY_USED -> Mono.error(
                            new BadCredentialsException(
                                "authentication_failed"));
                        case UNKNOWN -> Mono.error(
                            new AuthenticationServiceException(
                                "replay_store_unavailable"));
                    });
            })
    );
~~~

Đoạn trên là **pseudocode**, không phải code Spring có thể copy-build: `submitShadowObservation` cần snapshot ownership, error isolation và không gây blocking. Authentication/authorization context phải được set qua reactive security primitives đúng thiết kế; `Mono.error` primary dependency phải fail closed. Đừng viết `onErrorResume(error -> verifyV1())` sau khi V2 thất bại.

Nếu primary và shadow cùng lấy một pooled buffer rồi một bên release sớm, bên kia có thể đọc dữ liệu hỏng. Trong migration, bảo toàn bytes và memory safety quan trọng hơn tối ưu vài bản sao nhỏ.

## 19. Gateway và reverse proxy: so sánh đúng trust boundary

Có hai kiến trúc cần phân biệt:

**A. Gateway là HMAC verifier.** Gateway xác minh signature, key state, timestamp/nonce và claim replay. Backend nhận principal qua **mTLS hoặc signed internal assertion** đã kiểm tra issuer/audience/expiry/method/target/body binding. Shadow có thể chạy trong gateway hoặc canary gateway, nhưng không mint assertion nếu primary reject.

**B. Backend là HMAC verifier.** Gateway forward request đến backend. Cần hợp đồng định nghĩa external/internal raw request-target khi gateway rewrite URI, header normalization, content encoding và body.

~~~mermaid
flowchart TD
    C["Client ký raw external request"] --> G["Gateway"]
    G --> P["Primary verifier ở edge hoặc backend"]
    G -. "Snapshot cùng trust boundary" .-> S["Shadow verifier"]
    P --> N["Single authoritative nonce claim"]
    N --> B["Backend authorization"]
    S --> M["Comparison + route/version metrics"]
~~~

### Tình huống cần test

| Gateway transform | Rủi ro với parity |
| --- | --- |
| `/public/v1/orders` → `/internal/orders` | Primary và shadow ký URI khác |
| Query reorder | Raw target thay đổi |
| `%2F` ↔ `%2f` | Percent-encoded octets khác |
| HTTP/1.1 → HTTP/2 | Pseudo-headers, target/host handling khác |
| Header value OWS/comma joining | Duplicate signed header không được xử lý giống |
| gzip decompress/recompress | Raw body digest thay |
| Chunked transfer framing | Không được nhầm transport chunks với payload |
| `X-Forwarded-Host`, `X-Original-URI` | Header từ Internet client có thể spoof |
| Direct backend route | Có thể bypass gateway verifier |
| Gateway credential cache | Revocation policy lệch phiên bản |

**Positive control qua chính gateway là bắt buộc:** V1 primary phải chấp nhận request hợp lệ với cùng target/body; shadow V2 có V2 proof nếu muốn đánh giá full V2. Nếu cả hai fail vì proxy rewrite, đó không phải bằng chứng migration đã tương đương.

### Không nhân đôi request nghiệp vụ

Một kiểu “mirror traffic” nguy hiểm là để shadow request đi qua **cả handler/payment service**. Một POST tạo payment được mirror tới backend B có thể tạo side effect hai lần, ngay cả khi cả hai verifier đúng.

Shadow chỉ chạy **authentication-evaluation code path**, không gọi controller, DB writes, message publisher hoặc outbound API. Nếu cần mô phỏng full request tới môi trường shadow, dùng isolated fake dependencies và dataset test, không route production payment thật.

## 20. Migration của canonicalization và signing suite

Có ba dạng migration hay gặp:

### 20.1. Thay implementation, giữ wire contract

Hai evaluators cùng nhận `HMAC-REQUEST-V1`, K4 và signature V1. Đây là loại so sánh dễ nhất: `VALID` ở primary phải có cùng kết quả ở shadow, khi cùng credential/policy/time. Golden vectors byte-level dùng để tìm mismatch về query, headers, body.

### 20.2. Đổi canonical request V1→V2

Ví dụ V1 không ký `X-Nonce`, V2 yêu cầu ký nonce và key ID. **Không** so HMAC V1 với MAC được tính lại trên canonical V2 rồi gọi mismatch là lỗi. Kế hoạch:

1. Công bố V2 contract có version/domain separation.
2. Tạo golden canonical bytes/signature độc lập.
3. SDK có thể gửi **V1 proof + V2 proof** trong canary nếu hai bên thỏa thuận protocol dual-sign.
4. Primary kiểm tra V1; shadow đánh giá V2 proof read-only.
5. Lọc ra cohort đã cung cấp V2 proof và registry có key/route policy phù hợp.
6. Theo dõi V2 compatibility, giảm mismatch có lý do.
7. Chuyển V2 primary cho canary; V1 shadow read-only.
8. Enforce V2 và retire V1 theo deadline.

### 20.3. Đổi thuật toán HMAC hoặc secret/key version

Với V1 `HmacSHA256` và V2 `HmacSHA512`, MAC length, encoding và key material có thể khác. Provision **đúng secret của V2**, không bắt V2 verifier dùng lại output SHA256 của client. Key rotation cũng nên cấp key ID mới, tránh “K4 trỏ lúc S4, lúc S5”. Nếu dùng master-key derivation, cần KDF/domain separation được security review; không dùng hàm nối tự chế.

### Không có “verify một MAC với hai secret rồi OR”

Nếu request khai K4, verifier phải dùng **một exact key record**, không thử K3/K5 khi K4 mismatch. Việc nhiều key ACTIVE trong overlap không phải lý do cho phép một request chọn bất kỳ secret nào server có.

## 21. Rollout: từ baseline tới cutover và retirement

Một kế hoạch migration có checkpoint cụ thể:

| Pha | Primary | Shadow | Khả năng client | Điều kiện chuyển |
| --- | --- | --- | --- | --- |
| 0 — Baseline | V1 | Không | V1 | Security regression và golden V1 pass |
| 1 — Shadow start | V1 | V2 read-only | V1; V2 proof canary nếu thay contract | No shadow side effects, observability sẵn |
| 2 — Compatibility | V1 | V2 | Dual proof cohort tăng | Coverage đủ và mismatch được giải thích |
| 3 — V2 canary | V2 cho cohort đã provision | V1 read-only | V2 keys + signer active | Auth/replay/authz/concurrency E2E pass |
| 4 — Expand V2 | V2 theo policy | V1 sampled | Đối tác migrate theo lịch | p95/p99/error budget, no bypass |
| 5 — Enforce V2 | V2 | V1 chỉ audit nếu cần | V1 bị disable cho migrated clients | V1 valid MAC bị reject theo policy |
| 6 — Retire | V2 | Tắt | V2 | Không còn V1 accepted ngoài policy |

**Capability discovery chỉ là thông tin:** metadata `preferred=V2` không đồng nghĩa V1 đã bị deny, và không bảo đảm mọi gateway có V2. Cần deploy toàn tuyến và provision credentials V2 **trước** khi yêu cầu client gửi V2.

### Đặt migration owner và SLO

Giao trách nhiệm rõ: security owner (threat model), SDK owner (dual proof), API owner (HTTP contract), platform owner (gateway/Redis), operations owner (rollback). Định nghĩa các mục tiêu có số liệu, ví dụ:

- Tỷ lệ shadow-evaluable đủ lớn trên cohort được chọn.
- Không còn divergence *chưa giải thích* trong những test/security-critical routes bắt buộc.
- Không có replay double-claim hay business side effect của shadow.
- p95/p99 và CPU/heap budget không vượt giới hạn đo thực tế.
- Không có V1 accepted sau khi bị policy deny.
- Key revocation và multi-region consistency pass.

**Không sử dụng threshold kiểu “shadow match 99,9%” một cách mù quáng**: 0,1% còn lại có thể là bug cho phép cross-tenant hoặc MAC bypass. Những security-critical divergences phải được phân tích và chặn release.

## 22. Canary selection và feature flags không do client quyết định

Canary nên được quyết định **phía server** theo allowlist client/credential/route có kiểm soát, version policy và release cohort; không dựa vào header tự do như `X-Use-New-Auth: true` của client ngoài.

Một chính sách gợi ý:

~~~yaml
migrationPolicy:
  revision: r21
  routes:
    orders:
      primary: V1
      shadow: V2
      shadowSampleRate: 0.10
  canary:
    enabledCredentialIds:
      - cred-test-101
      - cred-test-102
    primary: V2
  fallbackToOtherVerifierOnMacFailure: false
  productionNonceClaimers: 1
~~~

Đây là YAML **minh họa**, không phải file cấu hình đã được nạp vào workspace. `enabledCredentialIds` phải đến từ registry/flag service tin cậy và được mapping sau lookup; đừng cho client tự gửi ID canary tùy ý.

### Hai tính chất khác nhau

- **Observability toggle:** bật/tắt shadow cho phép giảm overhead; không thay acceptance policy.
- **Security policy toggle:** đổi primary hoặc enable suite; là thay đổi có tác động bảo mật, cần approval, kiểm toán, rollback rules và khả năng phân phối nhất quán.

Không giao “kill switch” bypass HMAC cho một flag vận hành chung. Nếu V2 gây sự cố, có thể rollback primary theo policy đã được phê duyệt hoặc dừng route; không cho request unsigned qua production để tăng availability.

## 23. Rollback: quay lui an toàn, không hồi sinh khóa/suite bị revoke

Một rollback migration có thể gặp:

- V2 canonicalizer sai khiến client hợp lệ nhận 401.
- V2 body capture bị lỗi khi gateway dùng gzip.
- V2 credential cache stale.
- V2 replay store latency làm p99 tăng.
- Một region chưa deploy key/policy version cần thiết.

Quyết định rollback phải xét:

1. **Có chính sách cho phép dùng V1 nữa không?**
2. V1 verifier có bug bảo mật đang khiến phải retire không?
3. K3/V1 key đã REVOKED chưa?
4. Nonce state có còn bảo vệ request V1 nếu quay về không?
5. Những client đã chuyển V2 có thể quay lại V1 không, theo minimum suite đã ký thỏa thuận?
6. Backfill/gateway consistency và authz policy có còn đúng không?

Nếu V1 đã bị vô hiệu do security incident, **không rollback tự động bật V1** dù V2 lỗi; ưu tiên fail closed, khắc phục V2 hoặc phương án bảo mật được review. Việc cho client tự thử V1 sau 401 V2 là đường downgrade nguy hiểm.

### Rollback cả replay-store topology

Nếu V2 dùng một replay namespace mới, quay về V1 có thể tạo cơ hội phát lại request cũ nếu nonce state không được duy trì theo scope. Test rollback không chỉ xem HTTP 2xx của V1, mà phải chứng minh **nonce cũ vẫn không được chấp nhận lại**, key revoked bị reject và tenant authorization không đổi.

## 24. Response semantics và privacy khi hai verifier bất đồng

**Chỉ primary** được ảnh hưởng HTTP response:

| Primary outcome | Shadow outcome | Response/doanh nghiệp | Điều cần ghi nhận |
| --- | --- | --- | --- |
| Valid + nonce first-use | Valid | Theo authorization/business | Parity pass |
| Invalid MAC | Valid | 401, **không được cho đi tiếp** | Critical divergence |
| Valid + nonce first-use | Invalid | Theo primary, authz tiếp tục | Compatibility gap |
| Invalid MAC | Invalid | 401 | Reject parity, cần xác định reason |
| Valid MAC + replay used | Valid crypto | 401 replay | Không coi shadow là bypass |
| Credential store unavailable | Shadow valid | 503 fail closed primary | Dependency issue |
| Primary valid + authz deny | Shadow valid | 403/404 theo policy | Authorization independent |
| Primary valid | Shadow timeout | Theo primary | `SHADOW_ERROR` và alert |
| Unsupported V2 proof | V2 NOT_EVALUABLE | Theo primary | Coverage chưa đủ |

Ở bảng, `Valid` của shadow là **pure cryptographic/eligibility evaluation**, không chứng minh đã atomic nonce claim hoặc authorized. Để tránh ngộ nhận, metrics nên dùng tên `shadow_crypto_valid` chứ không phải `shadow_authenticated`.

Một public response minh họa cho primary authentication failure:

~~~http
HTTP/1.1 401 Unauthorized
Content-Type: application/problem+json
Cache-Control: no-store
WWW-Authenticate: HMAC realm="api"

{
  "type": "about:blank",
  "title": "Unauthorized",
  "status": 401,
  "detail": "Authentication is required or invalid.",
  "code": "AUTHENTICATION_FAILED"
}
~~~

Challenge `HMAC realm="api"` chỉ dùng nếu ứng dụng đã **định nghĩa scheme này**, không phải tính năng mặc định của Spring Security. Không trả expected MAC, raw secret, full canonical bytes hoặc “shadow V2 says valid” ra public API; thông tin đó có thể tạo credential/replay oracle.

## 25. Observability: dashboard cho sự tương đương và readiness

Một dashboard migration nên tách các chỉ số:

| Tín hiệu | Nhãn hữu hạn | Công dụng |
| --- | --- | --- |
| `hmac_primary_decisions_total` | route, suite, outcome, reason | Acceptance/security baseline |
| `hmac_shadow_evaluations_total` | route, suite, outcome | Shadow coverage và lỗi |
| `hmac_parallel_comparisons_total` | route, primaryVersion, shadowVersion, result | Phân bố divergence |
| `hmac_shadow_skipped_total` | route, reason | Sampling, overload, missing V2 proof |
| `hmac_shadow_duration` | route, suite | Overhead CPU/latency |
| `hmac_nonce_claim_total` | outcome | Đếm claim primary, phát hiện double-claim |
| `hmac_policy_revision` | region, revisionGroup | Cache/deployment convergence |
| `hmac_key_state_errors` | reason | Revocation/key lookup issues |

Dùng `route` theo route template/allowlist và version/suite từ enum. Không dùng raw client ID, key ID, tenant ID, nonce, signature, raw target, full body digest hoặc request ID làm **metric label**. Correlation ID có thể nằm trong audit/trace có ACL phù hợp, không phải high-cardinality Prometheus label.

### Đặt tên sai lệch một cách trung thực

Một verifier quan sát signature mismatch **không biết chắc** nguyên nhân là URI, key hay body. Chỉ gắn component cause nếu có grounded diagnostics trong test harness hoặc trace đáng tin. Sử dụng enum trung tính `SIGNATURE_MISMATCH` và dữ liệu conformance độc lập để điều tra.

Theo dõi `shadowCoverage = evaluated/elegible` đúng cohort, `NOT_EVALUABLE` và `SHADOW_ERROR` riêng. Một match rate cao nhưng chỉ 5% request có đủ V2 signature không đủ bằng chứng cutover.

### Chi phí performance của shadow

Hash body hai lần trên cùng raw bytes và secret lookup hai lần tăng CPU/allocation. Với body 1 MiB và 1.000 in-flight requests, mỗi bản copy raw body thêm khoảng 1 GiB dữ liệu. Vì vậy:

- Có body limit và bounded shadow sampling.
- Nếu cùng digest contract, có thể chia sẻ request-scoped digest đáng tin **read-only**.
- Nếu V1/V2 dùng digest khác, tính từng digest đúng nhưng không giữ nhiều body copies vô hạn.
- Tách p95/p99 read body, digest, credential lookup, replay store và downstream latency.
- Khi shadow quá tải, **drop/record metric**, không nới authentication hay tắt primary crypto.

## 26. Ma trận kiểm thử Parallel verification

| ID | Fixture / hành vi | Kỳ vọng |
| --- | --- | --- |
| MIG-01 | Primary V1 valid, shadow V1 clone valid | MATCH_VALID; claim nonce đúng một lần |
| MIG-02 | Primary invalid MAC, shadow reports valid | HTTP 401; không override |
| MIG-03 | Primary valid, shadow invalid | Primary vẫn quyết định; ghi divergence |
| MIG-04 | Primary invalid, shadow invalid | 401; no principal |
| MIG-05 | Shadow throws exception | Primary không đổi result; ghi SHADOW_ERROR |
| MIG-06 | Shadow timeout | Không block vô hạn; metrics/drop |
| MIG-07 | Shadow returns NOT_EVALUABLE | Không tính là signature mismatch |
| MIG-08 | Chỉ có V1 signature, V2 cần V2 proof | V2 NOT_EVALUABLE, không “V2 passed” |
| MIG-09 | Client dual-sign hợp lệ V1+V2 | Primary V1 pass; V2 crypto evaluation pass |
| MIG-10 | Dual-sign V1 valid, V2 wrong secret | Primary theo V1; V2 mismatch và no side effects |
| MIG-11 | Dual-sign V2 valid, V1 revoked key | V1 không thể được fallback chấp nhận |
| MIG-12 | Đổi signed version header, giữ MAC | Reject, không downgrade |
| MIG-13 | V2 key ID K4, ký bằng K3 | Reject, không try old secret |
| MIG-14 | K3 REVOKED, signature V1 đúng | Policy reject, dù MAC toán học đúng |
| MIG-15 | Request body bị thay sau client ký | Signature mismatch |
| MIG-16 | JSON whitespace/property order thay | Raw-body digest mismatch theo contract |
| MIG-17 | Query order thay | Đúng contract V1/V2, không tự repair |
| MIG-18 | Percent-encoding case thay | Test raw-target byte parity |
| MIG-19 | Duplicate signed headers | Reject ambiguity trước evaluation |
| MIG-20 | Gateway external/internal URI rewrite | Positive control mỗi verifier theo trust boundary |
| MIG-21 | HTTP/1.1↔HTTP/2 qua proxy | Canonical parity đã công bố |
| MIG-22 | gzip decompress/recompress | Body bytes/digest đúng contract hoặc reject |
| MIG-23 | Bounded body limit +1 byte | 413; không shadow buffer vô hạn |
| MIG-24 | WebFlux body chia chunks khác nhau | Digest không phụ thuộc chunk boundaries |
| MIG-25 | WebFlux request cancel/error | Release DataBuffer; không auth success |
| MIG-26 | Double filter registration | Không claim nonce 2 lần ngay trong R1 |
| MIG-27 | Shadow gọi production replay store | Test FAIL: no shadow claim invariant |
| MIG-28 | Primary nonce FIRST_USE, shadow crypto valid | Một claim production, request tiếp tục authz |
| MIG-29 | Primary nonce ALREADY_USED, shadow crypto valid | 401; không business |
| MIG-30 | Primary nonce UNKNOWN, shadow valid | 503/fail closed; shadow không cứu request |
| MIG-31 | Timestamp ở biên ±W, same observedAt | Không lệch vì hai Clock khác |
| MIG-32 | Policy revision primary/shadow khác | Phân loại NOT_COMPARABLE; điều tra cache |
| MIG-33 | Credential disabled giữa hai evaluations | Không báo cryptographic mismatch sai nguyên nhân |
| MIG-34 | V1→V2 suite cùng client, nonce reused | Theo shared replay scope đã công bố |
| MIG-35 | Concurrent 100 signed requests cùng nonce | Một claim thành công toàn phạm vi |
| MIG-36 | Redis replication/failover | Không double-accept vượt security guarantee |
| MIG-37 | Spring MVC @RequestBody sau capture | Nhận đúng raw bytes, không body rỗng |
| MIG-38 | Reactive SecurityContext cross-request | Không rò principal |
| MIG-39 | Primary HMAC pass nhưng tenant B không grant | 403/404; shadow không cấp quyền |
| MIG-40 | Mirror shadow request tới business handler | Test FAIL: business side effects phải bằng 0 |
| MIG-41 | Primary signature invalid, shadow valid | Không có DB/event/email side effect |
| MIG-42 | Toggle shadow on/off | Accepted/rejected population không đổi |
| MIG-43 | Canary V2 với suite enabled/provisioned | V2 primary pass, V1 shadow read-only |
| MIG-44 | Canary V2 và V2 proof missing | Reject theo V2 policy, không fallback |
| MIG-45 | Disable V1 sau deadline | V1 MAC đúng vẫn reject mọi gateway |
| MIG-46 | Rollback app khi V1 key revoked | Không hồi sinh V1/key |
| MIG-47 | Shadow sampling 10% | Coverage/sample count rõ; không suy toàn bộ traffic |
| MIG-48 | Shadow queue quá tải | Drop/metric; primary unaffected |
| MIG-49 | Shadow attempts to mutate SecurityContext | Test FAIL, principal phải từ primary |
| MIG-50 | Public 401 chứa expected MAC/secret | Test FAIL, lộ dữ liệu |
| MIG-51 | Logging raw body/signature/nonce ở shadow | Test FAIL, có nguy cơ replay/privacy |
| MIG-52 | Gateway header `X-Authenticated-Client` spoofed | Không bypass HMAC/mTLS trust |
| MIG-53 | Direct backend request bỏ gateway verifier | Bị chặn trust policy |
| MIG-54 | Primary accepted nhưng payment 500 | Nonce đã claim, không tự rollback |
| MIG-55 | Client retry intent với nonce mới | Idempotency tránh duplicate business effect |
| MIG-56 | V1/V2 policy cache stale | Test phát hiện vi phạm revocation/convergence |

### Chọn cấp kiểm thử

- **Unit:** MIG-01–08, 12–19, 27–34, 42, 49; verify orchestration và contract.
- **Spring integration:** MIG-09–11, 23–26, 35, 37–41, 43–44, 54–55; filter/provider/nonce/DB.
- **Gateway E2E:** MIG-20–22, 45–46, 52–53; proxy/region/identity.
- **Fault injection:** MIG-06, 30, 32–33, 36, 47–48, 56; dependency and scaling.
- **Privacy/audit:** MIG-50–51; logs/traces/public response.

Không dùng chỉ một response 401 làm bằng chứng chống downgrade: mọi negative case phải có **positive control cùng route/clock/registry** để loại trừ lỗi môi trường.

## 27. Failure injection và nguyên tắc dừng migration

Một migration gate tốt phải có **điều kiện dừng cụ thể**. Ví dụ:

| Sự kiện | Hành động |
| --- | --- |
| Có request primary reject nhưng shadow pass do bug bypass | Chặn cutover, phân tích, không mở fallback |
| Shadow sai canonical bytes ở một gateway | Giữ primary V1, sửa proxy contract |
| Shadow timeout/queue overflow nhiều | Giảm sampling, giữ primary nguyên vẹn |
| V2 có tỷ lệ valid thấp do SDK chưa dual-sign | Phân loại NOT_EVALUABLE, hoàn thiện rollout SDK |
| V2 secret/key chưa provision | Không quảng bá capability cho credential đó |
| V2 nonce store timeout | Canary fail closed; không dùng primary V1 cứu khi V2 đã enforce |
| Key revoked vẫn được accepted ở node nào đó | Incident, tắt route/credential, không chờ match rate |
| Cross-tenant authorization gap | Dừng rollout, đánh giá data exposure |
| V1 MAC đúng vẫn accepted sau retirement | Security violation, khắc phục policy convergence |
| Business side effect từ shadow | Dừng shadow ngay, điều tra duplicate operations |

**Không rollback một security fix chỉ để đạt SLO** khi rollback tái mở lỗ hổng có bằng chứng. Ưu tiên tắt shadow, rollback code không làm yếu policy hoặc fail closed route có vấn đề.

### Mức độ “song song” có giới hạn

Hai evaluators chạy đồng thời không bảo đảm kết quả so sánh công bằng nếu mỗi bên dùng credential revision/time khác. Với test parity, pin immutable evidence và common evaluation time. Với rollout thực, instrument revision và classifies mismatch; đừng cố đồng bộ bằng cách gửi secrets/canonical body ra một hệ thống quan sát kém bảo vệ.

## 28. Bài tập phân tích: shadow 100% pass nhưng production vẫn nguy hiểm

Một nhóm đang chuyển từ V1 sang V2 trên Spring Boot 3 + gateway:

~~~text
Primary V1:
  key K3, HmacSHA256
  ký method + normalized URI + body digest
  Redis namespace hmac:nonce:v1

Shadow V2:
  key K4, HmacSHA512
  ký raw URI + signed headers + timestamp/nonce + body digest
  chạy AuthenticationManager thứ hai trên cùng HTTP request
  Redis namespace hmac:nonce:v2

SDK đối tác:
  vẫn chỉ gửi X-Signature-V1, chưa gửi V2 proof

Gateway:
  rewrite /public/orders → /internal/orders

Metrics:
  shadow_pass = true khi tính được expected HMAC V2 trên server
  “100% shadow compatible”
~~~

Một pull request đề xuất:

~~~java
Authentication a = verifyV1(request);
Authentication b = verifyV2(request);
return (a != null) ? a : b;
~~~

Hãy trả lời:

1. Vì sao không có V2 signature mà lại đếm `shadow_pass` là sai?
2. Vì sao V2 dùng K4/HmacSHA512 cần proof độc lập với V1?
3. Shadow gọi full `AuthenticationManager` có thể tác động nonce như thế nào?
4. Hai nonce namespaces V1/V2 có tạo khả năng cross-version replay không?
5. Vì sao `a != null ? a : b` là fallback/downgrade?
6. Gateway rewrite URI có thể tạo divergence giả ra sao?
7. Thế nào là primary authentication decision owner?
8. Làm sao đặt effective suite policy và key-grant cho canary?
9. Có nên chạy mirror request qua payment service thật không?
10. Metrics cần phân biệt `NOT_EVALUABLE`, `INVALID` và `SHADOW_ERROR` như thế nào?
11. Khi V2 primary lỗi Redis, có được dùng V1 shadow result để cho request chạy không?
12. Khi MAC V2 đúng nhưng tenant B không có grant, HTTP response thuộc authentication hay authorization?
13. Vì sao update metadata `preferred=V2` chưa đủ để deprecate V1?
14. Những test nào chứng minh cutover không làm tăng side effects hoặc hồi sinh revoked K3?

**Định hướng:** yêu cầu SDK gửi **V2 proof được ký thực**, xây canonical vectors V1/V2 độc lập; primary là nguồn quyết định duy nhất, shadow chỉ đánh giá crypto read-only; nonce claim duy nhất ở authoritative store. Sửa gateway contract, dùng key ID exact lookup, canary theo server policy và giữ authorization riêng. Chỉ cutover khi coverage và security-critical divergences đã được giải thích.

## 29. Checklist triển khai xác minh song song

- [ ] Có mục tiêu migration rõ: refactor verifier, đổi canonicalization, đổi key hoặc đổi MAC algorithm.
- [ ] Hai verifiers chỉ so sánh kết quả có ý nghĩa khi proof/contract/key/policy tương đương; nếu khác phải có V2 signature độc lập.
- [ ] Primary là **nguồn authoritative authentication decision duy nhất**, shadow không tự mở acceptance path.
- [ ] Không dùng `old.verify || new.verify` hoặc “try alternate key/suite” khi MAC fail.
- [ ] Header signing version/key ID được ký vào canonical request hoặc binding an toàn tương đương.
- [ ] Key lookup theo exact key ID, không hồi sinh key đã REVOKED/disabled.
- [ ] Immutable request evidence có method/raw target/signed headers/raw body digest theo đúng trust boundary.
- [ ] Bounded body capture; Servlet body replay đúng; WebFlux DataBuffer release/cancel đúng.
- [ ] Shadow không ghi nonce production, không tạo principal, không mutate SecurityContext/Reactor Context.
- [ ] Production nonce claim **chỉ một lần** sau MAC đúng, atomic và fail closed nếu UNKNOWN.
- [ ] Timestamp check dùng cùng observedAt/fixed Clock cho parity; revision khác được đánh dấu không so sánh được.
- [ ] Shadow exception/timeout/overload được cô lập, không biến primary reject thành accept.
- [ ] Không mirror request tới business handler, DB writes, queue, payment hoặc email của production.
- [ ] V1/V2 dual proof protocol được version hóa, chống header ambiguity và canonicalization gap.
- [ ] HMAC đúng vẫn phải qua tenant/action/resource authorization độc lập.
- [ ] Gateway/external-internal URI rewrite, gzip, HTTP/2 và forwarded headers có conformance tests thực tế.
- [ ] Không tin client-supplied identity/forwarded headers; backend xác minh gateway mTLS/signed assertion.
- [ ] Có positive controls, golden canonical vectors và signer độc lập, không dùng mỗi HTTP 401.
- [ ] Phân loại `NOT_EVALUABLE`, `SHADOW_ERROR` và policy mismatch riêng khỏi cryptographic divergence.
- [ ] Metric labels hữu hạn; không log raw secret, full signature, nonce, canonical request hoặc body nhạy cảm.
- [ ] Shadow sampling/circuit breaker có memory/concurrency budget và không làm giảm security boundary.
- [ ] Canary do server policy/credential cohort kiểm soát, không do client header tự bật.
- [ ] Deploy và provision V2 trước khi advertise; chỉ bật V2 primary cho credential/route sẵn sàng.
- [ ] Có test nonce concurrency, multi-node, Redis failover và rollback replay state theo guarantee.
- [ ] Key rotation/revocation và suite migration có deadline, audit và không fallback secret cũ.
- [ ] Cutover gate yêu cầu các divergence security-critical được điều tra, không chỉ match-rate cao.
- [ ] Rollback không vô hiệu emergency security policy hoặc tái mở V1/key đã revoke.
- [ ] Runbooks, on-call, alert và test regressions được kiểm chứng trước rollout production.

**Xác minh song song an toàn không phải việc có hai bộ verifier rồi cho phép bộ nào pass cũng được.** Nó là một cơ chế **đo lường có kiểm soát**: primary sở hữu quyết định và nonce claim; shadow chỉ đánh giá cùng bằng chứng hoặc V2 proof độc lập, không gây side effect. Khi đã chứng minh canonical parity, key/suite eligibility, replay safety, gateway consistency và authorization boundary, mới chuyển quyền quyết định sang V2 theo từng cohort và loại bỏ V1 có thời hạn.
