# Server fixture: dựng máy chủ kiểm thử hợp đồng xác thực HMAC

## 1. Server fixture là gì và vì sao cần thiết?

Trong module **SECURITY_AUTHENTICATION_HMAC_REQUEST_AUTHENTICATION**, HTTP request được xác thực bằng HMAC dựa trên **shared secret** và **canonical request** theo hợp đồng ký. Tùy API, hợp đồng có thể ràng buộc method, URI, header được chọn và/hoặc digest của body. Server còn phải kiểm tra timestamp/nonce chống replay, vòng đời key khi rotation, cách gateway/proxy chuyển tiếp request và **phân quyền** sau khi xác thực.

Ở chương **Contract testing**, bài **Server fixture** tập trung vào một môi trường máy chủ có **dữ liệu, thời gian và phụ thuộc kiểm soát được** để chứng minh client và server cùng hiểu hợp đồng HMAC. Fixture này không chỉ là bộ mock trả sẵn 200/401: nó phải đi qua **verifier và security chain thật**, trong khi những thành phần biến động được thay bằng dữ liệu kiểm thử đáng tin cậy.

Ví dụ một ứng dụng thanh toán có endpoint `POST /public/v1/payments?mode=preview&account=A123`. Nếu test chỉ gọi trực tiếp `HmacSigner.sign(...)` và so sánh với `HmacSigner.sign(...)`, một bug bỏ query khỏi canonical vẫn có thể khiến test xanh. Server fixture tốt sẽ tạo request độc lập, gửi qua HTTP/security adapter, xác minh principal và đảm bảo không có tác động nghiệp vụ ở trường hợp bị từ chối.

**Mục tiêu học tập:**

1. Thiết kế server fixture tái lập được: key store, clock, nonce store, route mapping, HTTP stack và authorization.
2. Tạo **golden vector** có digest và signature cố định để phát hiện sai khác byte/canonicalization giữa SDK và server.
3. Kiểm thử trạng thái **401/403/413/503** theo hợp đồng, không làm lộ secret hoặc key metadata.
4. Bao phủ replay đồng thời, key rotation, proxy rewriting, raw query/body và fail-closed.
5. Biết khi nào fake in-memory là đủ và khi nào cần Redis, gateway, database thật trong integration test.

> **Phân biệt:** *fixture* là dữ liệu và hạ tầng kiểm soát được dùng để chạy test; *contract* là hành vi HTTP/crypto phải giữ ổn định. Một fixture dễ chạy nhưng bỏ qua HMAC filter không kiểm chứng được contract xác thực.

## 2. Ranh giới của một server fixture đáng tin

~~~mermaid
flowchart LR
    C[Test client + golden vectors] -->|HTTP request thực| G[Gateway test nếu cần]
    G --> S[Ứng dụng Spring thực]
    S --> F[HMAC authentication filter]
    F --> K[Fixture key repository]
    F --> T[Fixture Clock]
    F --> N[Fixture nonce store]
    F --> A[Authorization policy thật]
    A --> B[Business handler + spy side effects]
    S --> R[HTTP response + audit events]
~~~

Các thành phần **nên để thật** trong test hợp đồng server:

- HTTP method/path/query/header/body parser của ứng dụng, hoặc HTTP adapter tương đương trong phạm vi test.
- Canonicalizer, HMAC-SHA256 verifier, header validation và so sánh chữ ký.
- Spring Security filter chain, cách tạo `Authentication`, entry point 401 và access-denied handler 403.
- Chính sách quyền dùng cho test (scope, tenant, route ownership), với dữ liệu key do fixture cung cấp.
- Cơ chế trả lỗi và bảo đảm filter dừng trước business handler khi chưa xác thực.

Các thành phần **có thể thay bằng test fixture** khi cần tính quyết định:

| Phụ thuộc | Fixture phù hợp | Giới hạn cần nhớ |
|---|---|---|
| `Clock` | `Clock.fixed(...)` hoặc clock điều khiển được | Mọi code xác minh phải dùng cùng clock được inject |
| Key repository | Map in-memory gồm key ID, secret giả, validity/tenant/authority | Không chứng minh latency, invalidation hay nhất quán của secret store thật |
| Nonce store | Fake atomic, reset được giữa các test | Chưa chứng minh TTL/atomicity đa replica trên Redis thật |
| Gateway | Test proxy có cấu hình rewrite/forwarded metadata | Mock route không thay thế thử nghiệm proxy thực |
| Business service | Spy/fake có đếm side effect | Không chứng minh transaction thực khi có database/message broker |
| Audit/metrics | In-memory sink | Không chứng minh log exporter/tracing cấu hình production |

**Nguyên tắc:** thay *nguồn dữ liệu và phụ thuộc*, không thay *quyết định bảo mật cần kiểm tra*. Nếu mục tiêu test là xác minh nonce Redis `SET NX PX` hoặc key invalidation nhiều replica, phải dùng backend thật hoặc thành phần tương đương hỗ trợ semantics đó.

## 3. Đóng băng hợp đồng HMAC trước khi viết code fixture

Không có một định dạng canonical HMAC HTTP mặc định cho mọi hệ thống. Ví dụ xuyên suốt bài giả định phiên bản `HMAC-V1` với các trường:

~~~text
HMAC-V1
<METHOD_UPPERCASE>
<PUBLIC_RAW_PATH>
<PUBLIC_RAW_QUERY_OR_EMPTY>
<KEY_ID>
<TIMESTAMP_UTC>
<NONCE>
<LOWERCASE_HEX_SHA256_OF_EXACT_BODY_BYTES>
~~~

Các dòng ghép bằng dấu xuống dòng **LF (0x0A)**, không thêm LF ở cuối. Canonical string mã hóa UTF-8 trước khi tính HMAC:

~~~text
digest    = lowercaseHex(SHA256(bodyBytes))
canonical = UTF8(joinWithLF(
    "HMAC-V1", method, publicRawPath, publicRawQuery,
    keyId, timestamp, nonce, digest
))
signature = Base64(HMAC-SHA256(secretBytes, canonical))
~~~

Trong contract này:

- `method` là phương thức thực mà request gọi; phải thống nhất casing.
- `publicRawPath`/`publicRawQuery` là biểu diễn public URL **trước rewrite**, lấy từ nguồn tin cậy khi request đi qua gateway.
- Query **không có dấu `?`** trong canonical; query vắng mặt được biểu diễn thành chuỗi rỗng theo ví dụ.
- `bodyBytes` là byte body được client ký, **không phải JSON đã parse và serialize lại**.
- `keyId`, `timestamp`, `nonce` là một giá trị duy nhất mỗi header, có format và độ dài giới hạn; không cho newline/control characters tạo nhập nhằng giữa các dòng.
- Key có trạng thái active/overlap/revoked và các mốc hiệu lực do **server** quyết định.

Nếu hệ thống của bạn ký thêm `Content-Type`, `Host`, body digest header hoặc dùng canonical query đã sort, phải **thay cả fixture lẫn expected vector** theo đúng hợp đồng thực tế. Không dùng bài này như một lời khẳng định rằng mọi hệ thống nên ký raw query.

## 4. Một bộ dữ liệu server fixture cụ thể

Giả định test đóng băng thời gian tại `2026-11-28T10:00:00Z`, cửa sổ timestamp ±300 giây, hai biên được chấp nhận. Một key test đang active và một key bị thu hồi:

| Key ID | Secret trong fixture | Trạng thái tại thời gian test | Principal/authority |
|---|---|---|---|
| `partner-a-v2` | `test-hmac-secret-for-contract-v1` | Active | `partner-a`, `payments:write` |
| `partner-a-v1` | Secret test khác | Revoked | Không cấp quyền vì không qua xác thực |
| `partner-b-readonly` | Secret test khác | Active | `partner-b`, `payments:read` |
| `missing-key` | Không có | Not found | Không có principal |

Các secret trên **chỉ dùng trong kiểm thử**, không phải secret nên dùng trong production. Nếu dùng source control chứa fixture, bắt buộc secret giả, không trộn bất cứ secret thật nào của đối tác. Không dùng key ID chưa được xác thực để tự quyết định tenant/authority trước MAC.

**Các giá trị golden vector:**

~~~yaml
contract_version: HMAC-V1
method: POST
public_raw_path: /public/v1/payments
public_raw_query: mode=preview&account=A123
key_id: partner-a-v2
timestamp: "2026-11-28T10:00:00Z"
nonce: nonce-001
body_utf8_no_trailing_newline: '{"amount":125000,"currency":"VND"}'
secret_utf8: test-hmac-secret-for-contract-v1
body_sha256_lowerhex: ed6cd11906e5c888e772cfd89895fcf7d069d3cd6f47711466b021ad263f76b1
canonical_utf8_length_bytes: 167
expected_signature_base64: "+Vpc0JjB64J/k+pWdRi7qZgI+P42SqYfMUF4Yn+amJM="
~~~

Các giá trị digest và MAC được tính từ fixture cố định; **không biến chúng thành một file ngoài phạm vi được giao** trong quy trình này. Dùng chúng làm expected value của test chứ không cho code server tự tính expected rồi tự so sánh với kết quả của chính nó.

### 4.1. Canonical string của golden vector

~~~text
HMAC-V1
POST
/public/v1/payments
mode=preview&account=A123
partner-a-v2
2026-11-28T10:00:00Z
nonce-001
ed6cd11906e5c888e772cfd89895fcf7d069d3cd6f47711466b021ad263f76b1
~~~

**Lưu ý:** code fence trình bày có newline sau dòng cuối trên trang Markdown; byte canonical thực dùng để tính expected MAC **không chứa newline kết thúc**. Khi ký trong test, đừng copy toàn bộ fence rồi vô tình đưa CRLF hoặc LF cuối vào message.

## 5. Fixture cho Clock, key và nonce

### 5.1. Clock: cố định thời gian ở nguồn server

Java 17:

~~~java
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;

Clock contractClock = Clock.fixed(
        Instant.parse("2026-11-28T10:00:00Z"),
        ZoneOffset.UTC);
~~~

**Phải inject `contractClock` vào chính timestamp verifier**, không chỉ vào đối tượng tạo request ở test. Nếu HMAC filter tiếp tục gọi `Instant.now()` hoặc `System.currentTimeMillis()` trực tiếp, test cố định thời gian sẽ trở nên flaky hoặc luôn trả 401 sau khi golden timestamp hết cửa sổ.

Mỗi phép thử tại biên cần một clock có thể điều khiển, không dựa vào `Thread.sleep`:

~~~text
now = 10:00:00Z; W = 300 seconds
09:55:00Z -> accepted at boundary
09:54:59Z -> expired
10:05:00Z -> accepted at boundary
10:05:01Z -> future
~~~

Không tự đổi timezone, đoán format hoặc cắt phần giây lẻ để làm test xanh. Format timestamp nằm trong canonical request nên parser và signer phải thống nhất.

### 5.2. Key repository: dữ liệu cố định nhưng trạng thái thay được

Một fake key repository có thể chứa các record bất biến:

~~~java
import java.time.Instant;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;

public record ContractKey(
        String keyId,
        byte[] secret,
        String principalId,
        Set<String> authorities,
        Instant notBefore,
        Instant notAfter,
        boolean revoked) {
    // Fixture test: ở code thực cần tránh làm lộ mutable secret byte[].
}

public final class FakeContractKeyStore {
    private final Map<String, ContractKey> keys = new ConcurrentHashMap<>();
    private volatile boolean unavailable;

    public void put(ContractKey key) {
        keys.put(key.keyId(), key);
    }

    public void setUnavailable(boolean value) {
        unavailable = value;
    }

    public ContractKey findById(String keyId) {
        if (unavailable) {
            throw new IllegalStateException("KEY_STORE_UNAVAILABLE");
        }
        return keys.get(keyId); // null = lookup thành công nhưng không tồn tại
    }

    public void clear() {
        keys.clear();
        unavailable = false;
    }
}
~~~

Trong adapter thực, `null`/not-found dẫn đến credential rejection (thường 401), còn `KEY_STORE_UNAVAILABLE` dẫn đến nhánh 503 **fail closed**; không chuyển exception thành “unknown key” rồi cache âm. Key bị revoked hoặc hết hạn phải bị từ chối **dù secret có thể tính ra MAC đúng**.

Nếu dùng một key repository reactive, fixture nên giữ đúng ba trạng thái: `Mono.just(key)` = found, `Mono.empty()` = not found, `Mono.error(...)` = unavailable. Không viết stub trả `null` trong publisher. Để test rotation, thay record theo phiên bản, nhưng phải reset state giữa các test.

### 5.3. Nonce store: fake atomic chỉ cho test một process

Test bình thường có thể dùng `ConcurrentHashMap.newKeySet()` để chặn replay trong một JVM:

~~~java
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;

public final class FakeNonceStore {
    private final Set<String> used = ConcurrentHashMap.newKeySet();
    private volatile boolean unavailable;

    public boolean claimOnce(String verifiedScope, String nonce) {
        if (unavailable) {
            throw new IllegalStateException("NONCE_STORE_UNAVAILABLE");
        }
        // put-if-absent semantics nhờ Set.add thread-safe.
        return used.add(verifiedScope + ":" + nonce);
    }

    public void setUnavailable(boolean value) {
        unavailable = value;
    }

    public void reset() {
        used.clear();
        unavailable = false;
    }
}
~~~

Fake này có thể chứng minh **một process** không chấp nhận nonce trùng khi request chạy đồng thời; nó **không có TTL** và **không chứng minh tính nguyên tử giữa các replica**. Test với Redis thật cần thao tác tương đương `SET key value NX PX ttlMs` và kiểm tra TTL theo timestamp window. Ví dụ với window `now ± W`, nonce đã claim có thể cần lưu gần `2W` tính từ lúc request sớm nhất được nhận; TTL chỉ bằng `W` có thể chưa đủ.

**Điểm bắt buộc:** nonce chỉ được claim **sau khi chữ ký HMAC đã hợp lệ**. Request giả có `X-Nonce` của client khác không được phép chiếm nonce trước khi authentication thành công. Nếu nonce store bị lỗi, server trả lỗi hạ tầng theo hợp đồng, không bỏ qua anti-replay.

### 5.4. Business spy: kiểm tra không có side effect

Một bộ đếm chỉ là ví dụ tối thiểu:

~~~java
import java.util.concurrent.atomic.AtomicInteger;

public final class PaymentSpy {
    private final AtomicInteger createCalls = new AtomicInteger();

    public void recordCreatePayment() {
        createCalls.incrementAndGet();
    }

    public int createCallCount() {
        return createCalls.get();
    }

    public void reset() {
        createCalls.set(0);
    }
}
~~~

Trong integration test, spy phải được gọi **đúng chỗ handler sẽ thực hiện nghiệp vụ**, không chỉ là object có tồn tại trong context. Với nghiệp vụ có database, message broker hoặc downstream API, assert luôn rằng không ghi record, không publish event và không gửi lệnh thanh toán khi authn/authz thất bại.

## 6. Java golden-vector test độc lập với HTTP server

Golden vector cần được kiểm thử ở **cả producer và server-side verifier**. Ví dụ Java sau tạo canonical/HMAC theo hợp đồng minh họa, so với expected literal đã cố định trong fixture. Nó giúp phát hiện một số regression về LF, raw query, body encoding và Base64:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.Base64;
import java.util.HexFormat;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import org.junit.jupiter.api.Test;

class HmacV1GoldenVectorTest {
    @Test
    void signsFixedCanonicalBytes() throws Exception {
        byte[] body = "{\"amount\":125000,\"currency\":\"VND\"}"
                .getBytes(StandardCharsets.UTF_8);
        byte[] secret = "test-hmac-secret-for-contract-v1"
                .getBytes(StandardCharsets.UTF_8);

        String digest = HexFormat.of().formatHex(
                MessageDigest.getInstance("SHA-256").digest(body));
        assertEquals(
                "ed6cd11906e5c888e772cfd89895fcf7d069d3cd6f47711466b021ad263f76b1",
                digest);

        String canonical = String.join("\n",
                "HMAC-V1", "POST", "/public/v1/payments",
                "mode=preview&account=A123",
                "partner-a-v2", "2026-11-28T10:00:00Z",
                "nonce-001", digest);

        assertEquals(167,
                canonical.getBytes(StandardCharsets.UTF_8).length);

        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(secret, "HmacSHA256"));
        String actualBase64 = Base64.getEncoder().encodeToString(
                mac.doFinal(canonical.getBytes(StandardCharsets.UTF_8)));

        assertEquals(
                "+Vpc0JjB64J/k+pWdRi7qZgI+P42SqYfMUF4Yn+amJM=",
                actualBase64);
    }
}
~~~

Đây là một **test vector tính toán**; chưa kiểm tra request có đi qua HMAC filter của ứng dụng hay không. Để tránh một lỗi giống nhau nằm trong cả test signer và verifier, nên lưu vector đã tính từ một implementation độc lập và chạy cả kiểm thử conformance ở phía server. Hợp đồng giữa Java client, SDK ngôn ngữ khác và server phải thống nhất từ **byte canonical** đến kết quả MAC.

### 6.1. Vector âm cần tạo thế nào?

Mỗi test âm phải giữ các yếu tố khác hợp lệ:

~~~text
Golden request R được ký bằng secret/key active và nonce mới.

T1: đổi query, giữ signature R            -> 401
T2: đổi method, giữ signature R           -> 401
T3: đổi path, giữ signature R             -> 401
T4: đổi một byte body, giữ signature R    -> 401
T5: đổi signed header, giữ signature R    -> 401
T6: signature Base64 lỗi                  -> 401 theo API
T7: signature đúng nhưng nonce đã claim  -> 401 replay
~~~

Với **T1–T5**, tạo signature cho request gốc với **nonce chưa từng dùng**, rồi mutate **duy nhất một trường** khi gửi. Không chạy request gốc thành công với cùng nonce ngay trước test âm: khi đó test âm có thể thất bại vì replay thay vì phát hiện signed-field mismatch.

## 7. Tiêm fixture vào Spring Security mà không bypass verifier

Một cấu hình Spring test có thể inject `Clock` và các adapter test (mã sau là **khung tích hợp**, cần dùng interface/bean thực của dự án):

~~~java
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Primary;

@TestConfiguration
public class HmacServerFixtureConfiguration {
    @Bean
    @Primary
    Clock hmacTestClock() {
        return Clock.fixed(
                Instant.parse("2026-11-28T10:00:00Z"),
                ZoneOffset.UTC);
    }

    @Bean
    FakeContractKeyStore fakeContractKeyStore() {
        return new FakeContractKeyStore();
    }

    @Bean
    FakeNonceStore fakeNonceStore() {
        return new FakeNonceStore();
    }

    @Bean
    PaymentSpy paymentSpy() {
        return new PaymentSpy();
    }
}
~~~

**Quan trọng:** chỉ định nghĩa `FakeContractKeyStore` và `FakeNonceStore` chưa làm HMAC filter tự động sử dụng chúng. Trong ứng dụng thực phải có adapter/`@Primary` bean triển khai **chính interface repository và nonce store mà production verifier đang gọi**, hoặc cấu hình profile test ánh xạ tới các fake. Khi test khởi tạo, nên assert verifier nhận bean fixture, không nhận store production.

Fixture không được tạo `Authentication` sẵn trong test cho request HMAC; các annotation kiểu `@WithMockUser` sẽ bypass mục tiêu nếu đang kiểm thử chứng thực bằng secret. Chúng có thể hữu ích cho test authorization **riêng**, nhưng không phải test server contract HMAC.

### 7.1. Chu trình chuẩn bị/teardown một test

~~~text
Before each test:
  set clock = fixed T0
  clear fake key store and nonce store
  seed synthetic keys K1/K2 with policy status
  reset payment spy, audit sink and metrics
  choose fresh test nonce

Execute:
  build request bytes + headers independently
  sign canonical fields per published contract
  send HTTP request through real security chain
  assert status + response headers + security outcome
  assert side effects and nonce claim behavior

After each test:
  clear fake stores and counters
  do not carry secret/nonce state into next test
~~~

Nếu suite chạy song song trong **một Spring context chia sẻ fake store**, reset giữa các test có thể tạo race condition. Dùng context riêng, namespace riêng hoặc disable parallelism cho nhóm test phụ thuộc state. Khi cần kiểm thử replay nhiều request cùng lúc, **chỉ chia sẻ state trong chính phép thử đó**.

## 8. HTTP contract test: quan sát server như client thật

Một test chỉ gọi `HmacVerifier.verify(...)` kiểm tra crypto logic, nhưng chưa quan sát được HTTP semantics. Đối với server fixture, nên dùng một trong các cấp độ:

| Cấp độ | Cách thử | Điều chứng minh |
|---|---|---|
| Pure crypto/vector | JUnit + canonical bytes/secret giả | Thuật toán, encoding, expected MAC |
| Security-slice integration | `MockMvc`/`WebTestClient` với filter chain được bật | Header parser, authentication, response 401/403, handler boundary |
| Real HTTP server | `@SpringBootTest(RANDOM_PORT)` + HTTP client | Container/server adapter, body stream, headers và wiring |
| Proxy end-to-end | HTTP client → Nginx/Envoy/gateway → service | Route rewrite, forwarded metadata, normalization và multi-hop |
| Distributed backing stores | ≥2 service replicas + Redis/key store | Atomic nonce claim, revoke propagation, failover |

Không nhất thiết chạy tất cả ở mỗi commit, nhưng **phải có ít nhất một test sử dụng filter thực**. Hãy ghi rõ mức độ bao phủ; một test MockMvc không thể khẳng định đã kiểm tra behavior HTTP/2 hoặc proxy production.

### 8.1. Mẫu HTTP test với Java 17

Đây là **khung test tích hợp**. Giả định server đã khởi động trên `localhost:port` với fixture key, clock, nonce ở mục trước; `sign(...)` là hàm client signer độc lập tuân thủ `HMAC-V1`. Các helper `startServerWithFixture`, `sign` và `businessSpy` đại diện cho adapter do dự án cung cấp:

~~~java
// Pseudocode JUnit 5 ở mức HTTP: dùng server thật được inject fixture.
byte[] body = "{\"amount\":125000,\"currency\":\"VND\"}"
        .getBytes(StandardCharsets.UTF_8);

String path = "/public/v1/payments";
String query = "mode=preview&account=A123";
String nonce = "nonce-success-1";
String timestamp = "2026-11-28T10:00:00Z";

String signature = clientSigner.signBase64(
        "POST", path, query, "partner-a-v2",
        timestamp, nonce, body);

HttpRequest request = HttpRequest.newBuilder(
        URI.create("http://127.0.0.1:" + port + path + "?" + query))
    .header("Content-Type", "application/json")
    .header("X-Key-Id", "partner-a-v2")
    .header("X-Timestamp", timestamp)
    .header("X-Nonce", nonce)
    .header("X-Signature", signature)
    .POST(HttpRequest.BodyPublishers.ofByteArray(body))
    .build();

HttpResponse<String> response =
        HttpClient.newHttpClient()
            .send(request, HttpResponse.BodyHandlers.ofString());
assertEquals(201, response.statusCode()); // Theo API fixture ví dụ.
assertEquals(1, businessSpy.createCallCount());
~~~

Đây là trích đoạn có biến/helper được fixture cung cấp, **không phải file JUnit standalone**. Nếu endpoint trả 200 thay vì 201 theo hợp đồng thực, test phải assert đúng mã đã công bố, không hardcode 201 cho mọi API.

### 8.2. Query tampering: giữ signature cũ

~~~java
// Trong một test độc lập, nonce chưa được dùng trước đó.
String nonce = "nonce-query-tamper-1";
String originalQuery = "mode=preview&account=A123";
String changedQuery  = "mode=execute&account=B999";

String signature = clientSigner.signBase64(
        "POST", "/public/v1/payments", originalQuery,
        "partner-a-v2", "2026-11-28T10:00:00Z", nonce, body);

// HTTP request thực dùng changedQuery, nhưng GIỮ NGUYÊN chữ ký originalQuery.
HttpResponse<String> response = sendSignedHttp(
        changedQuery, signature, nonce, body);

assertEquals(401, response.statusCode());
assertEquals(0, businessSpy.createCallCount());
// Nếu policy claim nonce sau MAC: nonce store không có entry này.
~~~

Test âm chỉ có giá trị khi timestamp, key, secret, body và path đều đúng, nonce mới và endpoint đúng filter. Một 401 do timestamp hết hạn hoặc key bị revoke sẽ che khuất regression bỏ query khỏi canonical.

### 8.3. Từ chối 401 khác 403

Hai phép thử phải tồn tại riêng:

**Authentication failure:** ký sai body/query, key không tồn tại, nonce replay hoặc timestamp ngoài cửa sổ → 401 theo API fixture, không có `Authentication` hợp lệ, không side effect.

**Authorization failure:** một key `partner-b-readonly` có MAC hoàn toàn hợp lệ nhưng không có `payments:write`. Server xác thực được `partner-b` nhưng từ chối thao tác POST → **403 Forbidden**, không side effect. Không cho key sở hữu secret tự động truy cập mọi tenant/resource.

HTTP 401 nên kèm `WWW-Authenticate` theo contract. Nếu API dùng scheme riêng `HMAC`, ví dụ `WWW-Authenticate: HMAC realm="signed-api"` là quy ước dự án, không phải một header chuẩn tự có của mọi Spring Security setup. Không trả expected HMAC, secret hoặc key existence trong body lỗi.

## 9. Bảng contract tests bắt buộc

| Fixture / biến thể | Response/behavior mong đợi | Thành phần được kiểm tra |
|---|---|---|
| Golden request, key active, nonce mới | 2xx/201 theo endpoint, đúng một handler call | Full authentication + authorization |
| Thiếu signature hoặc key ID | 401, handler không chạy | Header bắt buộc |
| Signature sai Base64, quá dài hoặc trùng nhiều header | 401/400 theo contract, không side effect | Parsing, uniqueness và bounds |
| Sai secret, giữ method/path/query/body | 401, không lộ key existence | MAC verify |
| Body đổi một byte nhưng giữ MAC cũ | 401, không side effect | Raw body digest |
| Query đổi giá trị nhưng giữ MAC cũ | 401, không side effect | Query binding |
| Query reorder, percent-encoding, key lặp | Theo raw/canonical query contract | Canonicalization và HTTP parameter pollution |
| Path/method bị thay sau ký | 401 hoặc route-level rejection theo contract | Route binding |
| Timestamp ngoài ±W | 401, không side effect | Freshness |
| Timestamp đúng ngay biên | Không bị từ chối chỉ vì clock | Inclusive/exclusive boundary |
| Nonce gửi lại sau request đã được chấp nhận | 401 replay | Anti-replay |
| Key đã revoked/hết hạn | 401 dù MAC toán học đúng | Key lifecycle |
| Key mới active và key cũ overlap | Theo hiệu lực key tại thời điểm test | Rotation |
| Key store timeout/unavailable | 503, không side effect | Fail-closed, lỗi hạ tầng |
| Nonce store unavailable | 503, không side effect | Fail-closed anti-replay |
| MAC hợp lệ nhưng chỉ có `payments:read` | 403, không side effect | Authorization |
| Body vượt hạn mức | 413, không buffer vô hạn | Bounded body capture |
| Body là JSON sai schema nhưng MAC hợp lệ | 400/422 theo API, không vào business action | Validation sau authn |
| Header original-target nội bộ do client tự khai | Không điều khiển verifier | Proxy trust boundary |
| Gateway rewrite path, giữ signed public target | Baseline hợp lệ; tamper phải bị từ chối | Contract qua proxy |

Mỗi row nên có ít nhất một assertion trên response và một assertion về trạng thái **business side effect**. Đối với các ca 401/503, có thể quan sát audit reason nội bộ nhưng không biến lý do chi tiết thành response oracle cho client.

## 10. Replay và concurrency: từ fake đến Redis thật

### 10.1. Test replay tuần tự

~~~text
Given:
    HMAC hợp lệ với nonce N, timestamp T, key K
When:
    request thứ nhất dùng (K, N, T) -> được chấp nhận
    request thứ hai gửi lại chính request đó -> bị từ chối
Then:
    số side effect cuối cùng đúng bằng một
~~~

Một fake atomic `Set.add(...)` đủ để kiểm tra luồng verifier gọi nonce store **đúng thứ tự** trong cùng process.

### 10.2. Test hai replica

Ở môi trường tích hợp với Redis/Testcontainers hoặc store production-equivalent:

~~~text
Service A ─┐
           ├─ đồng thời claim same verified-scope + nonce
Service B ─┘
                    |
                    v
              Redis SET NX PX
                    |
                    v
          chính xác một claim thành công
~~~

Test dùng barrier để phát đồng thời các request **có cùng signed fields**. Yêu cầu **tối đa một** request được xử lý nghiệp vụ, request còn lại bị chặn bởi replay; không dùng `GET` rồi `SET` tách rời. Nếu phát cả hai request mà không có request nào thành công vì lỗi khác, test cần báo lỗi fixture, không coi đó là “replay protection PASS”.

TTL phải bao phủ toàn bộ thời gian chữ ký vẫn được chấp nhận theo timestamp policy. Thử TTL expiry cùng fake clock/real Redis bằng công cụ test kiểm soát thời gian phù hợp; đừng viết unit test chờ nhiều phút bằng `Thread.sleep`. Fake không có TTL chỉ chứng minh logic một-process, **không chứng minh expiry/cluster**.

## 11. Key rotation, revoke và lỗi hạ tầng

Server fixture cần điều khiển được **key state** để kiểm tra những thời điểm khác nhau:

~~~text
T0: K1 = active; K2 = not yet active
T1: K1 và K2 cùng active trong overlap
T2: K1 = revoked; K2 = active
T3: key store unavailable
~~~

Test:

1. Ký bằng `K1` tại T0 và nhận hợp lệ nếu endpoint cho phép.
2. Tại T1, cả hai key ID còn hiệu lực theo chính sách đều có thể xác thực (mỗi request có nonce riêng).
3. Tại T2, chữ ký MAC với secret `K1` vẫn **đúng về mặt toán học**, nhưng phải bị từ chối theo policy revoke trên mọi replica.
4. Khi store không truy cập được, trả 503/fail-closed. Không lấy bản stale ngoài policy hoặc coi timeout là key không tồn tại.

Nếu test dùng **cache key**, thay dữ liệu trong fake repository chưa chắc làm cache refresh: đó chính là điều cần kiểm thử. Kết hợp thử revoke qua cache warm/cold, invalidation message bị mất và giới hạn độ trễ revoke. TTL cache không tự bảo đảm revoke tức thì.

Khi test unknown key, revoked key và bad MAC, response nên tương đồng theo chính sách để giảm khả năng enumeration; debug/audit nội bộ không được in secret, expected MAC hay canonical string chứa dữ liệu nhạy cảm.

## 12. Gateway/proxy server fixture

Một service có thể chạy đúng khi gọi trực tiếp, nhưng fail sau khi ingress rewrite:

~~~text
Client signed target: POST /public/v1/payments?mode=preview&account=A123
Gateway internal:     POST /payments?mode=preview&account=A123
Server handler:       POST /payments
~~~

Nếu hợp đồng ký **public target**, fixture gateway cần:

- Mô phỏng đúng hoặc sử dụng cấu hình thật của route rewrite, forwarded headers và TLS termination.
- Xóa/ghi đè **header nội bộ do client gửi** và bảo vệ hop gateway→service (network policy, mTLS/workload identity hoặc cơ chế tương đương).
- Chuyển thông tin public signed target theo một nguồn có xác thực; server kiểm tra mapping public route ↔ actual handler.
- Kiểm tra body không bị WAF/proxy parse rồi serialize lại nếu hợp đồng ký raw body bytes.

Các test quan trọng:

| Test | Điều quan sát |
|---|---|
| Public path được rewrite đúng | Golden signature vẫn được chấp nhận |
| Gateway tự thay đổi query đã ký | Chữ ký cũ bị từ chối, không side effect |
| Client gửi `X-Internal-Public-Target` giả | Metadata giả không thể qua verifier |
| Percent-encoding, duplicate query | Server và handler cùng một quy tắc canonicalization |
| Gọi tắt backend từ mạng thiếu tin cậy | Bị chặn bởi mạng/mTLS hoặc bị từ chối an toàn |
| Nhiều service replica sau load balancer | Nonce claim và key revoke nhất quán |

**Không dùng header original URI bất kỳ để “sửa” 401**. Nếu gateway cần biến đổi trường được ký, thiết kế hợp đồng canonical/ủy quyền phải xử lý biến đổi đó rõ ràng. Fixture phải phát hiện chữ ký cho thao tác A không được sử dụng trên thao tác B.

## 13. Debug fixture mà không tạo false positive

Một kết quả test 401 **chưa đủ** để kết luận verifier đã phát hiện đúng mutation:

- **Timestamp hardcoded từ lâu:** verifier đang dùng clock thật, test luôn trả 401 trước MAC.
- **Nonce cũ:** test âm bị replay rejection, không kiểm tra changed query/body.
- **Sai secret:** mọi case âm đều 401, kể cả khi verifier bỏ path khỏi canonical.
- **Security filter không chạy:** test có thể thấy 2xx từ controller hoặc 403 từ một filter khác.
- **Test signer dùng chung buggy canonicalizer:** cả hai bên cùng bỏ signed query; golden vector độc lập mới phát hiện.
- **Proxy normalize raw query:** test client gửi byte khác fixture dự kiến; phải quan sát actual request target.
- **Thử quyền bằng mock principal:** bỏ qua HMAC nhưng vẫn gọi đó là “contract authentication test”.
- **Fake store được inject sai:** test dùng key/nonce production hoặc bean khác, fixture reset không có tác dụng.
- **Một request có nhiều side effect:** chỉ assert HTTP status mà bỏ qua DB/event count.

Checklist chẩn đoán:

1. In ra **test vector ID, route ID, loại outcome và trace ID an toàn**; không log secret/full signature/body nhạy cảm.
2. Xác minh bean `Clock`, key repository, nonce store mà verifier thực sự sử dụng.
3. Kiểm tra expected canonical bytes với fixed vector (độ dài/hash trong môi trường test).
4. Khẳng định request đi qua HMAC security chain và authn kết thúc **trước** handler.
5. Đảm bảo mutation âm thay **một signed field**, giữ các tiền đề còn lại hợp lệ.
6. Khi test qua proxy, so sánh public signed target và actual internal route được ánh xạ bởi hop đáng tin cậy.
7. Kiểm tra state sau request: nonce claimed hay chưa, side effect count, audit reason.

## 14. Tiêu chí hoàn thành server fixture

- [ ] Có hợp đồng canonical version rõ ràng: method, public URI/query, signed headers, body bytes, encoding, timestamp/nonce.
- [ ] Có golden vector cố định được tính độc lập, gồm body SHA-256, canonical byte length và expected HMAC.
- [ ] Fixture điều khiển server clock; cả server verifier và test client dùng thời gian phù hợp.
- [ ] Key store seed được key active, read-only, revoked, overlap và unknown; không dùng secret thật.
- [ ] Nonce fake có atomic semantics một process; test Redis/cluster riêng xác minh TTL và concurrent replay.
- [ ] Có test HTTP đi qua **filter và verifier thật**, không dựa vào `@WithMockUser` để giả HMAC.
- [ ] Có test dương và mutation âm cho method/path/query/header/body; không ký lại field đã mutate.
- [ ] Header sai/thiếu/trùng và body quá lớn bị từ chối theo contract, không side effect.
- [ ] 401 cho credential invalid, 403 cho quyền không đủ, 503 cho store unavailable; HTTP error không lộ bí mật.
- [ ] Có test key rotation/revoke qua nhiều replica và cache stale nếu hệ thống có cache.
- [ ] Có test proxy rewrite, metadata giả mạo, duplicate query, raw body và route mapping.
- [ ] Mỗi request bị từ chối có assertion không tạo DB record/event/downstream side effect.
- [ ] Fixture reset độc lập; parallel test không can thiệp nonce/key/clock của nhau.
- [ ] Test report có phân loại rõ **unit/slice/HTTP/proxy/distributed** và giới hạn của từng mức.
- [ ] Log, metric và trace của test không lưu secret, signature đầy đủ hay dữ liệu nhạy cảm.

## 15. Tổng kết

**Server fixture** là nền tảng để biến hợp đồng HMAC thành các phép thử tái lập được. Thay vì chỉ mock kết quả xác thực, hãy giữ **canonicalizer, verifier và Spring Security chain thật**, rồi kiểm soát clock, key/secret giả, nonce state và tác động nghiệp vụ. Golden vector buộc client và server đồng ý trên **chính xác byte được ký**, còn test HTTP buộc sự đồng ý đó tồn tại qua header parser, filter, gateway và authorization.

Một server fixture đạt yêu cầu không chỉ nhận request hợp lệ mà còn **từ chối đúng nguyên nhân** ở các trường hợp signed data bị thay, nonce replay, key bị revoke, thiếu quyền hay store không khả dụng. Quan trọng hơn, **không có request chưa xác thực hoặc chưa được phân quyền nào tạo ra side effect**. Đó là hợp đồng cần bảo vệ khi nâng cấp Java/Spring Security, sửa gateway, rotate key hoặc thay đổi cơ chế chống replay.
