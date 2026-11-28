# Replay attack test: kiểm thử chống phát lại HTTP request đã ký HMAC

## 1. Replay attack là gì trong xác thực HMAC?

Trong mô-đun `SECURITY_AUTHENTICATION_HMAC_REQUEST_AUTHENTICATION`, client ký HTTP request bằng **HMAC với shared secret** trên một **canonical request** gồm method, URI, signed headers và/hoặc body digest theo hợp đồng. Verifier lựa chọn đúng secret theo key ID, kiểm tra credential state, MAC, timestamp và nonce, rồi tạo principal đã xác thực. Authorization sau đó kiểm tra quyền với tenant, action và resource.

**Replay attack** xảy ra khi một bên gửi lại **bản sao request đã được ký hợp lệ**. HMAC không bị phá: attacker không cần biết shared secret nếu đã có một HTTP request cùng signature. Chữ ký trên request cũ vẫn đúng về mặt mật mã, nhưng request không được phép trở thành một lần thực thi mới.

Ví dụ request tạo payment:

~~~http
POST /api/hmac/payments HTTP/1.1
Host: api.example.test
Content-Type: application/json
X-Client-Id: partner-a
X-Key-Id: partner-a-k4
X-Timestamp: 2026-11-28T04:00:00Z
X-Nonce: 2a5c6e84-5f32-4a1f-a591-3ab96f0da55b
X-Signature: <base64-hmac-sha256>

{"paymentId":"pay-101","amount":250000}
~~~

Nếu request này được client gửi một lần, rồi bị copy và gửi tiếp trong **cửa sổ timestamp còn hợp lệ**, server vẫn có thể tính ra **đúng HMAC**. Cơ chế chống replay cần **nonce dùng một lần**, được lưu dưới dạng claim nguyên tử trong replay store, để lần gửi lại bị từ chối.

### Kết quả học tập

Sau bài **Replay attack test** thuộc chương **Security testing**, người học sẽ biết:

1. Phân biệt replay, request HMAC sai, timestamp hết hạn và business retry hợp lệ.
2. Thiết kế test positive control + replay negative với **cùng method, target, headers, raw body, timestamp, nonce và signature**.
3. Chứng minh HMAC đúng nhưng replay bị chặn tại nonce guard, không phải tại lỗi khác.
4. Kiểm tra thứ tự `verify MAC → atomic claim nonce → authorization → business`.
5. Kiểm tra race giữa nhiều request, node, gateway và region.
6. Kiểm tra TTL, clock skew, key rotation, proxy canonicalization, idempotency và fail closed.
7. Kiểm tra không có **business side effect** thứ hai và không lộ chi tiết bảo mật qua response/log.

**Nguyên tắc:** 401 ở lần thứ hai **chưa đủ** để chứng minh chống replay. Phải biết lần đầu có thực sự hợp lệ không, timestamp còn hợp lệ không, nonce đã được claim chưa và lần sau đã bị chặn ở đâu.

## 2. Đe dọa và ranh giới kiểm thử

Giả sử một client có quyền tạo payment. Attacker được mô phỏng trong test harness có một **bản sao** HTTP request đã ký, nhưng **không biết shared secret**. Mô hình cần bao gồm:

| Kẻ tấn công có thể | Kẻ tấn công không cần |
| --- | --- |
| Phát lại nguyên request, header và body | Phá HMAC-SHA256 |
| Gửi request qua connection mới | Biết secret |
| Gửi lại qua gateway/region khác | Thay đổi canonical bytes |
| Phát lại đồng thời nhiều bản sao | Tạo signature mới |
| Gửi lại trong cửa sổ timestamp | Khiến timestamp hợp lệ vĩnh viễn |
| Thử bypass qua backend route nội bộ nếu cấu hình sai | Có quyền nghiệp vụ hợp lệ |

Các biên giới cần được bảo vệ:

~~~mermaid
flowchart LR
    C["HMAC Client"] --> G1["Gateway 1"]
    C -. "Copy signed request" .-> A["Replay Test Client"]
    A --> G1
    A --> G2["Gateway 2"]
    G1 --> V1["HMAC Verifier A"]
    G2 --> V2["HMAC Verifier B"]
    V1 --> N[("Shared atomic nonce store")]
    V2 --> N
    V1 --> B["Business Service"]
    V2 --> B
    B --> D[("Database / Events")]
~~~

Nếu gateway xác minh HMAC, backend phải tin identity thông qua **mTLS và/hoặc assertion nội bộ đã kiểm tra**. Nếu backend xác minh HMAC, gateway phải bảo toàn canonical target và signed bytes. Hai kiến trúc đều cần replay test, nhưng **điểm claim nonce** và bằng chứng cần kiểm tra khác nhau.

Không dùng dữ liệu sản xuất hoặc request của người dùng thật để replay. Các thử nghiệm chỉ thực hiện trên **môi trường/test credential và endpoint được cấp phép**, ưu tiên sandbox không tạo thanh toán thật.

## 3. Cần có những cơ chế nào để replay test có ý nghĩa?

Một thiết kế HMAC an toàn thường có:

- **Key ID/version:** tìm secret đã đăng ký, kiểm tra ACTIVE/REVOKED và chủ sở hữu client.
- **Canonical contract:** cùng byte sequence ở signer và verifier cho method, URI/query, signed headers và body.
- **HMAC check:** xác nhận chữ ký bằng đúng secret của key ID đã khai.
- **Timestamp:** nằm trong một **acceptance window** xác định theo clock của server.
- **Nonce:** được ký cùng timestamp và request; đủ entropy, mới cho mỗi lần gửi.
- **Replay store:** key theo scope đã được xác thực, ví dụ `(credentialId, nonce)`; **atomic insert-if-absent + TTL**.
- **Authentication outcome:** chỉ tạo principal khi MAC, state, timestamp và nonce đều hợp lệ.
- **Authorization:** quyền tenant/action/resource **độc lập** với HMAC thành công.
- **Idempotency:** bảo vệ cùng business intent khi phải retry với nonce mới sau timeout.

Cần phân biệt hai nghĩa của “không lặp”:

| Bảo vệ | Bằng chứng | Phạm vi |
| --- | --- | --- |
| Chống replay HMAC | Nonce đã được claim | Một lần sử dụng bằng chứng authentication |
| Business idempotency | Idempotency key + payload/principal binding | Một ý định giao dịch, dù nhiều lần HTTP attempt |
| Exactly-once business effect | Transaction/idempotency/outbox hoặc cơ chế tương đương | Một side effect nghiệp vụ theo thiết kế |

Nonce store **không tự cung cấp exactly-once business semantics**. Test replay và test idempotency có mục tiêu khác nhau, dù phải phối hợp ở những API có side effect.

## 4. Canonical request phải bảo vệ cả timestamp và nonce

Một hợp đồng ký minh họa `HMAC-REQUEST-V1` có thể tạo UTF-8 text dưới đây, với `LF` phân cách và không có newline cuối:

~~~text
HMAC-REQUEST-V1
POST
/api/hmac/payments
application/json
partner-a
partner-a-k4
2026-11-28T04:00:00Z
2a5c6e84-5f32-4a1f-a591-3ab96f0da55b
<sha256-hex-cua-raw-body-bytes>
~~~

Đây là **mô tả cấu trúc**, không phải golden vector với digest/signature đã tính. Hợp đồng thực tế phải định nghĩa rõ ký tự, thứ tự trường, phương thức HTTP, raw URI/query, signed headers, duplicate, body encoding và format digest.

Test replay phải biết:

1. `X-Timestamp` và `X-Nonce` **thực sự nằm trong dữ liệu được HMAC bảo vệ**.
2. `X-Key-Id` cũng được ràng buộc vào signature hoặc vào một cơ chế lựa chọn secret không nhập nhằng.
3. Gateway không được tự đổi các trường đã ký sau khi client ký mà chưa có contract tương đương.
4. Request body bị đổi một byte phải làm MAC fail nếu body digest thuộc hợp đồng.
5. Khi gửi **lại nguyên request**, HMAC vẫn toán học hợp lệ, nhưng nonce guard phải từ chối.

Nếu attacker có thể thay nonce mà giữ signature đúng thì đây là lỗi **canonicalization/signature coverage**. Không thể vá bằng TTL hoặc Redis.

### Bộ test tối thiểu để không nhầm nguyên nhân

| Ca | Điều thay đổi | Kỳ vọng |
| --- | --- | --- |
| First use | Chữ ký đúng, nonce N mới | Accepted |
| Exact replay | **Không đổi byte nào trong signed fields** | Rejected bởi nonce đã dùng |
| Nonce tampering | Chỉ đổi nonce, giữ signature | Rejected do MAC mismatch |
| Timestamp tampering | Chỉ đổi timestamp, giữ signature | Rejected do MAC mismatch |
| Body tampering | Chỉ đổi raw body, giữ signature | Rejected do body integrity |
| Expired timestamp | Giữ signature cũ, chờ hết window hoặc dùng fixed Clock | Rejected bởi timestamp, không phải bằng chứng nonce guard |

## 5. Test case cốt lõi: lần đầu hợp lệ, lần hai bị chặn

Một **replay security test** nên có fixture rõ:

~~~text
Credential:
  clientId: partner-a
  keyId: partner-a-k4
  keyStatus: ACTIVE
  secret: test-only-secret-A
  ownerTenant: tenant-a

Clock: 2026-11-28T04:00:00Z (fixed trong unit/integration test)
Request:
  method: POST
  rawTarget: /api/hmac/payments
  contentType: application/json
  timestamp: 2026-11-28T04:00:00Z
  nonce: 2a5c6e84-5f32-4a1f-a591-3ab96f0da55b
  body: {"paymentId":"pay-101","amount":250000}
Signature: HMAC-SHA256(test-only-secret-A, exact canonical bytes)
~~~

**Trình tự kiểm thử:**

1. Đảm bảo credential ACTIVE, timestamp hợp lệ, nonce **chưa tồn tại** và principal có grant tạo payment thử nghiệm.
2. Dùng **signer độc lập** tạo chữ ký của request; assert signature encoding hợp lệ.
3. Gửi request **R1**; xác nhận authentication pass và nonce được claim đúng một lần.
4. Ghi trạng thái DB/event/counter nghiệp vụ sau R1.
5. Gửi lại **R1 nguyên vẹn** trong cùng cửa sổ timestamp, không ký lại.
6. Kỳ vọng response authentication failure chung (thường 401), internal reason `REPLAY_DETECTED`, **không gọi handler lần hai**.
7. So sánh DB/event/counter: **không tăng thêm** sau replay.
8. Kiểm tra không tiết lộ secret, expected MAC, raw canonical bytes hoặc trạng thái nonce chi tiết cho người gọi.

**Positive control là bắt buộc**: nếu R1 cũng trả 401 do timestamp hết hạn, canonical mismatch hoặc key chưa có trong registry, R2 trả 401 không chứng minh replay guard hoạt động.

### Khái niệm “cùng request”

Không phải cùng `Idempotency-Key`; ở replay test cốt lõi, request R2 phải giữ nguyên **giá trị và thứ tự signed headers, URI/query, timestamp, nonce, raw body và signature**. Transport có thể là HTTP connection khác, nhưng nội dung thuộc canonical contract không được thay.

Nếu hệ thống ghi một `X-Request-Id` do gateway tạo mà **không nằm trong signature**, sự thay đổi ID đó không nên làm test thất bại; cần tập trung vào **signed bytes** và kiểm tra gateway không vô tình biến đổi các trường được ký.

## 6. Thứ tự an toàn: không claim nonce trước khi MAC hợp lệ

Một pipeline gợi ý:

~~~mermaid
flowchart TD
    A["HTTP request"] --> B["Giới hạn bytes + parse headers"]
    B --> C{"Timestamp, nonce hợp format và trong window?"}
    C -->|Không| X["Authentication failure"]
    C -->|Có| D["Lookup exact credential/key state"]
    D --> E{"HMAC trên canonical bytes hợp lệ?"}
    E -->|Không| X
    E -->|Có| F["Atomic claim (credentialId, nonce)"]
    F -->|ALREADY_USED| R["Replay rejected"]
    F -->|UNKNOWN| U["Fail closed: dependency unavailable"]
    F -->|FIRST_USE| G["Tạo authenticated principal"]
    G --> H{"Tenant/action/resource authorization?"}
    H -->|Không| Y["403/404 theo policy"]
    H -->|Có| J["Business handler + transaction"]
~~~

**Chỉ ghi nonce sau khi signature HMAC đúng**. Nếu claim trước, một người không biết secret có thể gửi nonce dự đoán/quan sát được kèm MAC sai để **chiếm nonce** và làm request hợp lệ của client bị từ chối (*nonce poisoning*).

Một negative test quan trọng:

~~~text
Store sạch, nonce N chưa dùng.

1) Gửi request với key ID K4, N, chữ ký sai:
   → 401; nonce store KHÔNG có N.

2) Gửi request đúng secret K4, vẫn dùng N:
   → authentication pass; nonce được claim lần đầu.

3) Gửi lại request ở bước 2:
   → replay rejected.
~~~

Nếu test chỉ kiểm tra bước 1 trả 401, nó không biết server có lỡ ghi nonce trước khi reject không.

### Claim trước hay sau authorization?

Trong pipeline minh họa, nonce claim sau MAC và trước authorization. Request có HMAC đúng nhưng thiếu quyền tenant sẽ **tiêu thụ nonce**, rồi bị 403/404. Đây là lựa chọn chính sách hợp lý: mọi bằng chứng HMAC đã được sử dụng sẽ không được phát lại. Nếu sản phẩm chọn thứ tự khác, phải đánh giá race và đảm bảo không thực thi side effect trước claim.

**MAC valid ≠ authorized**: replay test không thay thế test kiểm soát quyền tenant.

## 7. Replay store phải có thao tác nguyên tử và TTL

Một primitive phù hợp cho Redis:

~~~redis
SET hmac:nonce:v1:<digest-key> 1 NX PX 660000
~~~

Ở đây:

- `NX`: chỉ tạo key nếu chưa tồn tại.
- `PX 660000`: đặt TTL 660.000 ms (= 11 phút) trong **cùng thao tác**.
- Giá trị trả về “đã tạo” → `FIRST_USE`.
- Key đã có → `ALREADY_USED`.
- Lỗi mạng hoặc kết quả không xác định → `UNKNOWN`, **fail closed**.

Không triển khai bằng:

~~~text
if (!redis.exists(key)) {
    redis.set(key, "used");
}
~~~

Hai request đồng thời có thể cùng quan sát `exists=false` rồi đều đi vào nghiệp vụ.

### Scope của replay key

Với một secret/key ID có thể được rotate, namespace thường dùng:

~~~text
replayKey = (credentialIdFromRegistry, nonce)
~~~

`credentialId` phải được xác nhận bởi registry phía server, không lấy namespace tự do từ header do client khai. Nếu scope theo `(clientId, nonce)` để chống reuse xuyên key version, phải có quy tắc client identity và key rotation rõ. Không tự thêm `tenantId` vào scope để khiến một nonce dùng lại được ở tenant khác nếu cùng credential.

### Khóa storage và privacy

Có thể dùng digest của tuple đã canonical hóa thay vì raw nonce/key ID trong Redis key:

~~~text
hmac:nonce:v1:SHA256(
    lengthPrefix(credentialId) || credentialId || nonce
)
~~~

Giới hạn chiều dài và charset của nonce trước bước hash/storage. Không đưa nonce, key ID và secret vào metric labels. Dù nonce không phải shared secret, nó vẫn là một thành phần của request authentication, cần xử lý log/retention hợp lý.

## 8. Timestamp window, TTL và các test ranh giới

Giả sử verifier chấp nhận timestamp trong cửa sổ đối xứng:

\[
t_{\mathrm{server}}-W \le t_{\mathrm{signed}} \le t_{\mathrm{server}}+W
\]

Ví dụ `W = 5 phút`. Một request có timestamp **5 phút trong tương lai** khi được nhận lần đầu có thể vẫn còn được chấp nhận **thêm gần 10 phút** trong tương lai theo cùng hợp đồng. Nếu nonce record chỉ giữ 5 phút, replay key có thể hết hạn trong khi signature vẫn còn hợp lệ.

Với TTL cố định tính từ lúc claim, một lựa chọn bảo thủ:

\[
TTL_{\mathrm{nonce}} \ge 2W + \varepsilon
\]

Trong đó `ε` là margin cho clock skew/độ chính xác và trễ thực tế. Ví dụ `W=5 phút` thì `TTL=11 phút` là một **cấu hình minh họa**, không phải giá trị chuẩn cho mọi hệ thống.

Nếu đặt expiry theo timestamp đã ký, cần bảo đảm:

~~~text
recordExpiresAt >= signedTimestamp + W + safetyMargin
~~~

Không được cho nonce hết hạn trước lần cuối cùng một verifier được phép còn chấp nhận request theo timestamp policy.

### Bảng fixed Clock

Giả sử `Clock.fixed(2026-11-28T04:00:00Z)`, `W=5 phút` và biên inclusive:

| Timestamp ký | Request được xét tiếp? | Giải thích |
| --- | --- | --- |
| 03:54:59Z | Không | Quá cũ |
| 03:55:00Z | Có | Đúng biên dưới |
| 04:00:00Z | Có | Trong cửa sổ |
| 04:05:00Z | Có | Đúng biên trên |
| 04:05:01Z | Không | Quá xa tương lai |

**Test đúng nonce guard** phải thực hiện replay **khi timestamp vẫn còn hợp lệ**, thay vì chờ quá cửa sổ để server trả 401 vì expired timestamp. Test expired timestamp là một test **bổ sung độc lập**.

### Test TTL bị cấu hình quá ngắn

1. Claim nonce lúc signed timestamp còn ở mép tương lai.
2. Dịch test Clock đến thời điểm record vừa bị xóa.
3. Xác nhận signed timestamp **vẫn còn trong cửa sổ**.
4. Gửi lại R1; một implementation an toàn phải **vẫn từ chối** hoặc test phải FAIL để phát hiện cấu hình TTL thiếu.
5. Chạy qua các verifier có clock skew khác nhau đã được phép.

Một fake store không mô phỏng TTL **không thể chứng minh** tính an toàn của expiry. Cần integration test với store thật hoặc clock-controlled store có expiration semantics.

## 9. Java 17: verifier có thể test bằng fake atomic nonce store

Ta có thể cô lập **HMAC + replay logic** khỏi HTTP framework bằng một ví dụ Java 17. Những class dưới dùng cho unit test/kiến trúc minh họa, **không phải full production verifier**: không có credential registry, signed-header parser, body capture, tenant policy hay timestamp validation.

~~~java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;

import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

record SignedEvidence(
    String credentialId,
    String nonce,
    byte[] canonicalBytes,
    byte[] signatureBytes
) {}

interface NonceStore {
    boolean claim(String credentialId, String nonce);
}

final class AtomicFakeNonceStore implements NonceStore {
    private final Set<String> seen = ConcurrentHashMap.newKeySet();
    final AtomicInteger claimCalls = new AtomicInteger();

    @Override
    public boolean claim(String credentialId, String nonce) {
        claimCalls.incrementAndGet();
        return seen.add(credentialId + ":" + nonce);
    }

    boolean contains(String credentialId, String nonce) {
        return seen.contains(credentialId + ":" + nonce);
    }
}

final class MiniHmacReplayVerifier {
    private final byte[] serverSecret;
    private final NonceStore nonceStore;

    MiniHmacReplayVerifier(
            byte[] serverSecret, NonceStore nonceStore) {
        this.serverSecret = serverSecret.clone();
        this.nonceStore = nonceStore;
    }

    boolean authenticate(SignedEvidence evidence) {
        // Preconditions của ví dụ:
        // credentialId/nonce/canonicalBytes đã được parse
        // và timestamp còn trong window bằng Clock test.
        byte[] expected = hmacSha256(
            serverSecret, evidence.canonicalBytes());

        if (!MessageDigest.isEqual(
                expected, evidence.signatureBytes())) {
            return false; // Không claim nonce khi MAC sai.
        }

        return nonceStore.claim(
            evidence.credentialId(), evidence.nonce());
    }

    static byte[] hmacSha256(byte[] key, byte[] content) {
        try {
            Mac mac = Mac.getInstance("HmacSHA256");
            mac.init(new SecretKeySpec(key, "HmacSHA256"));
            return mac.doFinal(content);
        } catch (GeneralSecurityException ex) {
            throw new IllegalStateException(
                "HmacSHA256 unavailable", ex);
        }
    }
}
~~~

**Giới hạn bảo mật quan trọng:** `SignedEvidence` có thể do caller dựng tùy ý. Trong ứng dụng thực tế, verifier phải **tự dựng canonical bytes từ HTTP request và dùng secret đúng key ID lấy từ registry**; không cho client gửi sẵn `canonicalBytes` rồi được tin. `AtomicFakeNonceStore` chỉ giữ dữ liệu **trong một JVM, không có TTL**, nên tuyệt đối không dùng thay replay store phân tán của production.

Các test sau dùng helper này để chứng minh logic kiểm tra signature trước nonce, chứ không tuyên bố đã kiểm tra hết HTTP contract.

## 10. JUnit 5: replay đúng request và không có claim thứ hai

Một test khép kín ở mức core có thể dùng fixture canonical bytes không nhạy cảm và secret test:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.Test;

class ReplayCoreTest {
    private static final byte[] SECRET =
        "unit-secret-replay-2026"
            .getBytes(StandardCharsets.UTF_8);

    private static final byte[] CANONICAL = String.join("\n",
        "HMAC-REQUEST-V1",
        "POST",
        "/api/hmac/payments",
        "application/json",
        "partner-a",
        "partner-a-k4",
        "2026-11-28T04:00:00Z",
        "2a5c6e84-5f32-4a1f-a591-3ab96f0da55b",
        "<fixture-body-digest>"
    ).getBytes(StandardCharsets.UTF_8);

    private SignedEvidence proof() {
        return new SignedEvidence(
            "partner-a-k4",
            "2a5c6e84-5f32-4a1f-a591-3ab96f0da55b",
            CANONICAL,
            MiniHmacReplayVerifier.hmacSha256(SECRET, CANONICAL)
        );
    }

    @Test
    void acceptsFirstUseAndRejectsExactReplay() {
        AtomicFakeNonceStore store = new AtomicFakeNonceStore();
        MiniHmacReplayVerifier verifier =
            new MiniHmacReplayVerifier(SECRET, store);
        SignedEvidence request = proof();

        assertTrue(verifier.authenticate(request));
        assertTrue(store.contains(
            request.credentialId(), request.nonce()));

        // Dùng y nguyên object evidence/signature lần đầu.
        assertFalse(verifier.authenticate(request));
        assertEquals(2, store.claimCalls.get());
    }

    @Test
    void wrongMacCannotPoisonNonce() {
        AtomicFakeNonceStore store = new AtomicFakeNonceStore();
        MiniHmacReplayVerifier verifier =
            new MiniHmacReplayVerifier(SECRET, store);
        SignedEvidence valid = proof();

        byte[] wrong = valid.signatureBytes().clone();
        wrong[0] ^= 1; // MAC có định dạng đúng nhưng giá trị sai.
        SignedEvidence invalid = new SignedEvidence(
            valid.credentialId(), valid.nonce(),
            valid.canonicalBytes(), wrong
        );

        assertFalse(verifier.authenticate(invalid));
        assertEquals(0, store.claimCalls.get());

        // Nonce vẫn chưa bị tiêu thụ.
        assertTrue(verifier.authenticate(valid));
        assertEquals(1, store.claimCalls.get());
    }
}
~~~

Ở đây `<fixture-body-digest>` là **placeholder trong bytes thử nghiệm**, không phải body SHA-256 thật. Test chỉ chứng minh thứ tự MAC/claim và tính một-lần của fake store. Trong **contract/integration test**, thay bằng canonical bytes thực được tính/soát chéo độc lập từ method/URI/headers/raw body và dùng signer độc lập.

Một test tích hợp phải kiểm tra thêm **chữ ký đúng là của request HTTP được gửi**, để không bỏ sót lỗi canonicalization.

### Vì sao không assert 401 ngay trong unit này?

Verifier mẫu trả `boolean` để cô lập quyết định. HTTP 401 là trách nhiệm của Spring Security adapter/`AuthenticationEntryPoint` và được kiểm tra ở integration tests. Tách lớp giúp test có thể chỉ ra bug replay **ngay cả khi HTTP error handling thay đổi**.

## 11. Concurrency test: đúng một request claim thành công

Một kẻ tấn công có thể gửi nhiều bản sao cùng lúc thay vì chờ response request đầu. Nếu hệ thống dùng `GET` rồi `SET`, nhiều request có thể cùng vượt qua.

~~~mermaid
sequenceDiagram
    participant A as Request A
    participant B as Request B
    participant R as Atomic Replay Store
    participant S as Business Service
    A->>R: Claim key N with SET NX + TTL
    B->>R: Claim cùng key N
    R-->>A: FIRST_USE
    R-->>B: ALREADY_USED
    A->>S: Tiếp tục sau authorization
    B-->>B: Không gọi business
~~~

### Unit concurrency test

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.nio.charset.StandardCharsets;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.stream.IntStream;
import org.junit.jupiter.api.Test;

class ReplayConcurrencyTest {
    @Test
    void exactlyOneParallelClaimPasses() {
        byte[] secret =
            "test-replay-concurrency"
                .getBytes(StandardCharsets.UTF_8);
        byte[] canonical =
            "canonical-fixture".getBytes(StandardCharsets.UTF_8);

        SignedEvidence request = new SignedEvidence(
            "partner-a-k4", "nonce-parallel-0001",
            canonical,
            MiniHmacReplayVerifier.hmacSha256(
                secret, canonical)
        );

        AtomicFakeNonceStore store = new AtomicFakeNonceStore();
        MiniHmacReplayVerifier verifier =
            new MiniHmacReplayVerifier(secret, store);
        AtomicInteger accepted = new AtomicInteger();

        IntStream.range(0, 100).parallel().forEach(i -> {
            if (verifier.authenticate(request)) {
                accepted.incrementAndGet();
            }
        });

        assertEquals(1, accepted.get());
        assertEquals(100, store.claimCalls.get());
    }
}
~~~

Kết quả test này **chỉ chứng minh atomicity của ConcurrentHashMap trong một JVM**. Nó **không** chứng minh multi-node, Redis TTL, replication hoặc failover. Để chứng minh production guarantee, cần **integration concurrency test với replay store thực** và các verifier/gateway độc lập.

### Những assertion E2E đồng thời

- Có **100 HTTP requests thực** cùng timestamp/nonce/signature đã ký.
- Exactly **one authentication first-use** trong các request đã có MAC và state hợp lệ, theo mô hình atomic store.
- Các request còn lại bị reject replay hoặc bị lỗi hạ tầng và không được đi vào nghiệp vụ.
- Tối đa **một business transaction** được commit từ cùng signed request, nếu request đầu có quyền và nghiệp vụ hợp lệ.
- Không có hai gateway cùng trả kết luận “first-use” cho cùng replay scope khi sản phẩm cam kết global anti-replay.
- Nếu test gặp lỗi store `UNKNOWN`, **không** coi nó là first-use thành công.

Nếu đo “một response 2xx” nhưng payment handler idempotent đã trả cùng business result nhiều lần, vẫn cần quan sát replay decision nội bộ; idempotency không thay thế nonce guard.

## 12. Multi-node và Redis: atomic trên một primary chưa đủ global guarantee

Một thiết kế thường gặp là nhiều gateway/instances cùng dùng Redis:

~~~text
Gateway A ----\
               -> Redis primary (SET NX + TTL)
Gateway B ----/
~~~

Trong trạng thái bình thường và với **cùng replay namespace**, `SET NX` trên **một primary có thẩm quyền** cho phép tối đa một claim thành công.

Nhưng các cấu hình sau có thể phá lời hứa chống replay toàn cục:

| Thiết kế/lỗi | Hệ quả |
| --- | --- |
| Mỗi JVM lưu nonce vào `HashSet` riêng | Replay qua node khác có thể pass |
| Gateway A dùng Redis region A, gateway B dùng Redis region B | Hai nơi có thể cùng first-use |
| Replication bất đồng bộ, đọc từ replica stale | Kết luận “chưa có nonce” có thể sai |
| Primary crash/failover mất một write vừa ACK | Nonce đã claim có thể biến mất |
| Eviction trước TTL | Request cũ có thể được chấp nhận lại |
| Hai verifier dùng namespace khác nhau | Cùng nonce được claim ở hai domain |
| Redis timeout sau khi đã thực hiện lệnh | Caller không biết kết quả, phải fail closed |
| Credential phân tuyến sang nhiều region không có giao thức thống nhất | Không thể chứng minh global at-most-once |

Một câu trả lời “chúng tôi dùng Redis nên không có replay” là **chưa đủ**. Test phải bao gồm topology, các điểm ghi, failover, consistency, credential routing và policy khi store không khả dụng.

### Chiến lược để có ranh giới rõ

- Một miền claim có thẩm quyền đáp ứng tính nhất quán yêu cầu của từng credential.
- Nếu sử dụng region affinity, không cho cùng credential vượt qua nhiều miền độc lập mà vẫn quảng bá global anti-replay.
- Có cơ chế fail closed khi không thể chứng minh claim.
- Kiểm thử tập trung vào **đúng phạm vi cam kết**, không chỉ hai processes trong cùng máy.
- Có test retention, eviction và recovery sau failover.

Không tự động fallback sang cache in-memory khi Redis gặp lỗi. Nó giúp availability trước mắt nhưng làm mất chính guarantee mà replay test cần chứng minh.

## 13. Spring Data Redis: claim đồng bộ và reactive

### Spring MVC / Servlet adapter

Với `StringRedisTemplate`, việc `setIfAbsent(key, value, ttl)` thể hiện một thao tác conditional set cùng expiry:

~~~java
import java.time.Duration;
import org.springframework.data.redis.core.StringRedisTemplate;

enum ClaimOutcome {
    FIRST_USE, ALREADY_USED
}

final class ReplayStoreUnavailableException
        extends RuntimeException {
    ReplayStoreUnavailableException(String message) {
        super(message);
    }
}

final class RedisNonceStore {
    private final StringRedisTemplate redis;

    RedisNonceStore(StringRedisTemplate redis) {
        this.redis = redis;
    }

    ClaimOutcome claim(String key, Duration ttl) {
        Boolean inserted =
            redis.opsForValue().setIfAbsent(key, "1", ttl);

        if (inserted == null) {
            throw new ReplayStoreUnavailableException(
                "nonce_claim_unknown");
        }
        return inserted
            ? ClaimOutcome.FIRST_USE
            : ClaimOutcome.ALREADY_USED;
    }
}
~~~

Các exception từ driver/connection/timeout cũng phải được phân loại là **dependency unavailable** và chặn request, không đổi sang `FIRST_USE`. Code chỉ minh họa method claim, chưa có giới hạn key format, cấu hình Redis, TTL calculation, retry policy hoặc credential lookup.

### Spring WebFlux / reactive adapter

Trong WebFlux, không dùng client Redis blocking trên event loop:

~~~java
import java.time.Duration;
import org.springframework.data.redis.core.ReactiveStringRedisTemplate;
import reactor.core.publisher.Mono;

final class ReactiveRedisNonceStore {
    private final ReactiveStringRedisTemplate redis;

    ReactiveRedisNonceStore(
            ReactiveStringRedisTemplate redis) {
        this.redis = redis;
    }

    Mono<ClaimOutcome> claim(String key, Duration ttl) {
        return redis.opsForValue()
            .setIfAbsent(key, "1", ttl)
            .switchIfEmpty(Mono.error(
                new ReplayStoreUnavailableException(
                    "nonce_claim_unknown")))
            .map(inserted -> inserted
                ? ClaimOutcome.FIRST_USE
                : ClaimOutcome.ALREADY_USED);
    }
}
~~~

Đặc biệt **không** dùng `onErrorReturn(true)`, `defaultIfEmpty(true)` hoặc `onErrorResume(e -> Mono.just(FIRST_USE))` khi store lỗi. Chúng biến mất khả năng chống replay thành một “success path”. Những lỗi Redis trong pipeline cần được dịch thành response fail closed, thường 503 theo hợp đồng public.

### Vì sao không retry một SET NX tùy tiện?

Khi request tới Redis và response mạng mất, lần retry lệnh claim có thể thấy key `EXISTS` dù **chính attempt hiện tại đã ghi key trước đó**. Không suy đoán đây là một attacker replay hoặc kết luận first-use từ một thao tác lặp. Với security semantics, kết quả **mơ hồ** phải fail closed; retry HTTP nghiệp vụ được giải quyết bằng request mới và idempotency riêng.

## 14. HTTP và Spring Security: response phải đúng tầng

Một API HMAC thường có thể dùng response công khai chung cho authentication failure:

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
  "code": "AUTHENTICATION_FAILED",
  "requestId": "req-7af20"
}
~~~

Đây là **hợp đồng API minh họa**. `WWW-Authenticate: HMAC realm="api"` chỉ hợp lệ khi API đã **định nghĩa scheme HMAC/challenge** tương ứng; Spring Security không tự cung cấp một HMAC challenge chuẩn cho mọi ứng dụng.

Không trả `NONCE_ALREADY_USED` như public code nếu việc đó tạo oracle để dò credential hoặc nhận biết request từng được chấp nhận. Có thể ghi **internal reason `REPLAY_DETECTED`** trong security audit/metric với quyền truy cập được kiểm soát.

| Trường hợp | Ngữ nghĩa | Public status gợi ý |
| --- | --- | --- |
| HMAC đúng, nonce mới, đủ quyền | Authentication + authorization pass | Theo business response |
| HMAC đúng, nonce đã claim | Authentication replay failure | 401 chung |
| HMAC sai | Authentication failure | 401 chung |
| Timestamp quá cũ/tương lai | Authentication failure | 401 chung |
| Key REVOKED/expired | Credential ineligible | 401 chung |
| HMAC đúng, nonce mới, thiếu quyền tenant | Authorization denied | 403/404 theo policy |
| Replay store timeout/unknown | Authentication dependency unavailable | 503, fail closed |
| Body quá lớn | Không đánh giá đầy đủ | 413 |
| Business idempotency key dùng cho payload khác | Business conflict | 409 theo hợp đồng |

**Không nhầm 401 với 403:** replay guard chặn ở authentication; còn 403 là principal đã được xác thực nhưng không có quyền. **Không nhầm 401 với 503:** store lỗi không đủ bằng chứng kết luận request là replay.

## 15. Kiểm thử Spring MVC bằng MockMvc và SecurityFilterChain thật

Với Spring Boot/Spring Security 6 trên Servlet, replay test phải chạy qua **HMAC filter và AuthenticationManager/Provider thực**. Tránh `MockMvcBuilders.standaloneSetup` không gắn Spring Security, vì nó có thể bỏ qua hoàn toàn HMAC chain.

Một cấu trúc integration:

~~~mermaid
sequenceDiagram
    participant T as MockMvc Test
    participant F as Hmac OncePerRequestFilter
    participant M as AuthenticationManager
    participant N as Replay Store
    participant P as PaymentService
    T->>F: R1 valid signed request
    F->>M: authenticate(proof)
    M->>N: claim N
    N-->>M: FIRST_USE
    M-->>F: authenticated
    F->>P: request đi qua authz
    P-->>T: 2xx / test success
    T->>F: R2 exact signed replay
    F->>M: authenticate(proof)
    M->>N: claim N
    N-->>M: ALREADY_USED
    M-->>F: AuthenticationException
    F-->>T: 401
    Note over P: Không gọi nghiệp vụ ở R2
~~~

### MockMvc integration test skeleton

~~~java
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet
    .AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class HmacReplayMvcIT {

    @Autowired MockMvc mvc;
    @Autowired IndependentHmacSigner signer;
    @Autowired ReplayTestFixtures fixtures;

    @Test
    void exactSignedReplayCannotRunBusinessTwice()
            throws Exception {

        fixtures.resetNonceStore();
        fixtures.useFixedClock("2026-11-28T04:00:00Z");
        fixtures.activateCredential("partner-a-k4");

        byte[] body =
            "{\"paymentId\":\"pay-101\",\"amount\":250000}"
            .getBytes(java.nio.charset.StandardCharsets.UTF_8);

        String nonce = "2a5c6e84-5f32-4a1f-a591-3ab96f0da55b";
        String signature = signer.sign(
            "POST", "/api/hmac/payments", body,
            "partner-a-k4", "2026-11-28T04:00:00Z", nonce);

        // Không tính lại signature cho lần gửi thứ hai.
        var first = fixtures.signedPost(
            "/api/hmac/payments", body, nonce, signature);
        var exactReplay = fixtures.signedPost(
            "/api/hmac/payments", body, nonce, signature);

        mvc.perform(first)
            .andExpect(status().is2xxSuccessful());

        long effectsAfterFirst =
            fixtures.businessCommitCount("pay-101");

        mvc.perform(exactReplay)
            .andExpect(status().isUnauthorized());

        org.junit.jupiter.api.Assertions.assertEquals(
            effectsAfterFirst,
            fixtures.businessCommitCount("pay-101"));
    }
}
~~~

**Đây là test skeleton**: `IndependentHmacSigner`, `ReplayTestFixtures` và các method của fixture là thành phần dự án phải tạo, không phải API Spring sẵn có. Positive request phải pass đúng authz và business fixture. Fixed timestamp 2026 chỉ dùng khi verifier nhận `Clock.fixed`; nếu chạy test với đồng hồ thật ngoài cửa sổ, kết quả 401 của replay sẽ là **PASS giả**.

Cần thêm assert replay store đã claim nonce một lần, reason internal đúng và payment/event publisher không được gọi lần hai. Đếm DB rows có thể che side effect gửi message, nên với flow phức tạp phải kiểm tra **DB + outbox/events**.

### Filter dispatch

Một `OncePerRequestFilter` chạy hai lần do đăng ký đồng thời ở Servlet container và `SecurityFilterChain` có thể claim nonce lần hai **trong chính R1**, khiến request hợp lệ bị 401. Test registration/order và dispatch `REQUEST`/`ASYNC`/`ERROR` để phát hiện false replay do cấu hình.

## 16. Kiểm thử Spring WebFlux bằng WebTestClient

Trong WebFlux, body là `Flux<DataBuffer>`. Một `WebFilter` HMAC có thể buffer có giới hạn, hash raw bytes, verify credential/MAC/timestamp/nonce và replay body qua `ServerHttpRequestDecorator`. Security principal sống trong **Reactor Context**.

Một test skeleton:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive
    .AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class HmacReplayWebFluxIT {

    @Autowired WebTestClient client;
    @Autowired IndependentHmacSigner signer;
    @Autowired ReplayTestFixtures fixtures;

    @Test
    void rejectsSameSignedNonceOnSecondRequest() {
        fixtures.resetNonceStore();
        fixtures.useFixedClock("2026-11-28T04:00:00Z");

        String body = "{\"paymentId\":\"pay-201\"}";
        String nonce = "4a6123df-79bd-48a1-a4d1-2b535e5838b5";
        String signature = signer.sign(
            "POST", "/api/hmac/payments",
            body.getBytes(java.nio.charset.StandardCharsets.UTF_8),
            "partner-a-k4",
            "2026-11-28T04:00:00Z", nonce);

        send(body, nonce, signature)
            .expectStatus().is2xxSuccessful();

        send(body, nonce, signature)
            .expectStatus().isUnauthorized();

        fixtures.assertOneBusinessCommit("pay-201");
    }

    private WebTestClient.ResponseSpec send(
            String body, String nonce, String signature) {
        return client.post()
            .uri("/api/hmac/payments")
            .header("Content-Type", "application/json")
            .header("X-Client-Id", "partner-a")
            .header("X-Key-Id", "partner-a-k4")
            .header("X-Tenant-Id", "tenant-a")
            .header("X-Timestamp", "2026-11-28T04:00:00Z")
            .header("X-Nonce", nonce)
            .header("X-Signature", signature)
            .bodyValue(body)
            .exchange();
    }
}
~~~

Trong WebFlux integration, ngoài status và business effects, cần kiểm tra:

- Body được xác minh và replay **đúng bytes**; controller không nhận body rỗng.
- Không tạo authenticated principal cho R2; không rò `ReactiveSecurityContextHolder` giữa requests.
- `DataBufferUtils.join(..., maxBytes)` có giới hạn, release pooled buffers đúng khi success/error/cancel.
- Không `block()` trong event loop để gọi Redis/vault.
- Request cancel/timeout giữa chừng không vô tình báo first-use thành công nếu chữ ký chưa được xác minh đầy đủ.

Một `StepVerifier` test riêng cho capture body không thay thế `WebTestClient` chạy cả `SecurityWebFilterChain`; cần cả hai loại.

## 17. Client retry hợp lệ khác replay attack như thế nào?

Sau một network timeout, client có thể không biết payment đã commit hay chưa. Gửi lại **y nguyên** request với cùng timestamp/nonce/signature phải bị replay guard từ chối. Nhưng điều đó **không có nghĩa** việc thử lại nghiệp vụ đã được giải quyết.

### Ba lần gửi minh họa

~~~text
Business intent: CREATE_PAYMENT(pay-101)
Idempotency-Key: intent-pay-101

Attempt 1:
  Timestamp = T1
  Nonce = N1
  Signature = HMAC(request with T1, N1)
  Outcome = HTTP timeout; business outcome unknown

Attempt 2 (client retry theo hợp đồng):
  Timestamp = T2 mới
  Nonce = N2 mới
  Signature = HMAC(request with T2, N2)
  Idempotency-Key = intent-pay-101  (GIỮ NGUYÊN)
  Outcome = cùng business result nếu server có idempotency đúng

Attack replay:
  Timestamp = T1
  Nonce = N1
  Signature = signature cũ
  Outcome = authentication rejected
~~~

**Idempotency-Key phải được HMAC ký/bound với principal, tenant, action và payload digest** nếu giao thức sử dụng nó cho nghiệp vụ nhạy cảm. Server cần lưu kết quả intent một cách nguyên tử, có policy TTL và kiểm tra cùng key + payload khác.

### Các test riêng

| Test | Mục tiêu |
| --- | --- |
| Retry exact signed R1 | Replay rejected |
| Retry bằng nonce mới N2, giữ idempotency key và payload | Authentication pass; business result không nhân đôi |
| Cùng idempotency key nhưng payload khác, ký nonce mới | Business conflict, thường 409 |
| Cùng nonce N1 nhưng đổi timestamp và ký lại bằng secret hợp lệ | Replay rejected theo nonce scope khi record còn |
| Controller 500 sau khi nonce N1 được claim | N1 vẫn USED; không “rollback nonce” tự động |
| Redis claim UNKNOWN | Không chạy business; retry cần chính sách cho outcome chưa rõ |

Nonce là **bằng chứng lần gửi**, còn idempotency key là **ý định nghiệp vụ**. Hai store có semantics và retention khác nhau.

## 18. Không rollback nonce khi nghiệp vụ thất bại

Một sai lầm là xóa nonce khi handler trả 500 để client “có thể gửi lại cùng chữ ký”. Điều đó có thể tạo replay nếu nghiệp vụ đã có side effect trước lỗi:

~~~text
T0: R1 HMAC valid, nonce N1 mới
T1: Replay store ghi N1
T2: Service phát event tới queue
T3: Database rollback / response 500
T4: Code xóa N1 để cho retry
T5: R1 bị phát lại, event được gửi lần thứ hai
~~~

Trong một thiết kế thông dụng, **nonce đã claim không bị xóa vì authorization denied, JSON validation failed, DB rollback hoặc network disconnect**. Một lần claim thành công không đồng nghĩa transaction thành công, nhưng bằng chứng đó cũng không được tự động “được dùng lại”.

Các bài test cần assert:

- Request R1 dùng N1, sau khi auth pass nhưng controller lỗi → N1 vẫn tồn tại.
- R1 gửi lại N1 → bị từ chối ở authentication.
- Client muốn retry phải dùng N2 và **business idempotency**.
- Không suy ra payment success từ việc nonce store có record.

## 19. Key rotation, revoked key và scope nonce xuyên version

Khi rotate secret, registry có thể có:

| Key | State | Secret |
| --- | --- | --- |
| K3 | ACTIVE trong overlap | secret-K3 |
| K4 | ACTIVE | secret-K4 |
| K2 | REVOKED | secret-K2 |

Nếu request khai `X-Key-Id: K4` thì verifier chỉ được dùng **secret K4**, không thử K3 khi MAC sai. Một request dùng K3 khi đã REVOKED phải bị từ chối dù HMAC toán học đúng.

### Replay matrix qua rotation

| Kịch bản | Kỳ vọng |
| --- | --- |
| R1 ký bằng K4, nonce N mới | Có thể first-use |
| Phát lại R1 ký K4, N | Replay rejected |
| Request khai K4 nhưng ký bằng K3 | Signature mismatch |
| K3 còn ACTIVE, ký riêng request mới, nonce mới | Có thể authenticated |
| K3 đã REVOKED, ký đúng K3, nonce mới | Từ chối credential |
| Dùng cùng nonce N trên K3 và K4 | Phụ thuộc scope `(credentialId,nonce)` hay `(clientId,nonce)` đã công bố |
| Đổi `X-Key-Id` sau khi ký, giữ signature | Signature mismatch hoặc binding rejected |
| Cache trạng thái K3 stale sau REVOKED | Test phải phát hiện vi phạm revocation freshness |

Nếu replay namespace theo `(credentialId, nonce)`, một nonce có thể tồn tại ở hai version khác nhau; tuy nhiên **client vẫn phải tạo nonce mới cho từng request**. Nếu yêu cầu là “một nonce duy nhất theo client qua mọi key version”, chọn scope `(clientId, nonce)` và kiểm tra client identity từ registry, đồng thời bảo vệ cross-version replay theo contract.

Không để user-supplied tenant ID tự mở replay namespace mới cho cùng credential.

## 20. Multi-tenant: đừng nhầm chống replay với phân quyền

Một request ký HMAC hợp lệ cho principal `partner-a` có thể yêu cầu dữ liệu `tenant-b`. Chữ ký và nonce mới chỉ chứng minh **authentication evidence hợp lệ**; chúng không chứng minh A được quyền truy cập B.

Hai bài test độc lập:

**Replay negative:** R1 của partner-a tới tenant-a thành công; phát lại nguyên R1 bị chặn và không có side effect thứ hai.

**Authorization negative:** R2 khác, nonce mới, chữ ký HMAC đúng nhưng target tenant-b không có delegated grant; request bị 403/404 theo policy, không đọc/ghi tài nguyên tenant-b.

Nếu hệ thống claim nonce **trước** authorization, nonce của R2 có thể đã dùng dù R2 bị 403. Đây là hành vi theo contract, không phải false replay.

### Bảo vệ identity binding

- `X-Client-Id` và `X-Tenant-Id` được ký để bảo vệ tính toàn vẹn claim.
- Credential registry xác định **owner principal/tenant** đáng tin.
- Requested tenant phải được kiểm tra grant và resource ownership.
- Effective tenant được chọn **sau authorization**, không chỉ từ header.
- Replay store key scope không được tin tenant tự khai để tránh bypass.

Cần assert resource tenant khác **không bị trả về, sửa, gửi event hoặc tạo side effect**, chứ không chỉ status.

## 21. Gateway và proxy: replay qua nhiều trust boundaries

### Kiến trúc A — HMAC verification tại gateway

Gateway xác minh MAC, key state, timestamp và claim nonce. Sau đó gateway cấp trusted identity assertion tới backend qua mTLS hoặc cơ chế tương đương. Backend **không được tin header do client tự khai** như `X-Authenticated-Client`.

Test:

1. R1 có MAC hợp lệ qua gateway A → accepted, nonce claim.
2. R2 y hệt qua gateway B → reject, không mint assertion cho R2.
3. Client gửi `X-Gateway-Assertion` hoặc `X-Authenticated-Client` giả → gateway strip/reject.
4. Backend direct route từ workload không phải gateway → bị từ chối.
5. Internal assertion có issuer/audience/time/body binding sai → bị từ chối.
6. Internal assertion replay trong TTL → theo threat model phải được chặn bằng `jti`/channel binding hoặc cơ chế tương đương.

**Không claim cùng client nonce hai lần** nếu gateway đã claim ở edge và backend cũng dùng lại cùng replay key, vì R1 hợp lệ sẽ bị coi là replay ngay tại backend. Nếu bảo vệ thêm hop gateway→backend, cần **nonce/jti namespace nội bộ riêng**.

### Kiến trúc B — HMAC verification tại backend

Gateway chỉ forward HTTP request theo canonical contract. Backend tự tính HMAC và claim nonce, dùng replay store chung.

Test:

- Gateway rewrite `/public/v1/payments` thành `/internal/payments`: verifier biết rõ ký external/internal target nào.
- Proxy thay body/header ký ngoài hợp đồng → HMAC fail, không được coi là replay success.
- Client giả `X-Original-URI` → không thể khiến backend dùng target giả.
- Replay cùng signed request qua gateway khác → backend từ chối nếu nonce đã dùng.
- HTTP/1.1 ↔ HTTP/2 và duplicate signed headers không tạo parser disagreement.

**Positive control qua đúng proxy là bắt buộc**. Nếu R1 đã bị signature mismatch do rewrite, test R2 cũng trả 401 không chứng minh replay.

## 22. Replay detection và error semantics trong monitoring

Một dashboard nên phân biệt rõ:

| Internal outcome | Public classification | Ý nghĩa |
| --- | --- | --- |
| `SIGNATURE_MISMATCH` | `AUTHENTICATION_FAILED` | Signed bytes/secret không khớp |
| `TIMESTAMP_OUT_OF_WINDOW` | `AUTHENTICATION_FAILED` | Timestamp sai |
| `REPLAY_DETECTED` | `AUTHENTICATION_FAILED` | MAC hợp lệ nhưng nonce đã dùng |
| `CREDENTIAL_REVOKED` | `AUTHENTICATION_FAILED` | Key không còn được phép |
| `REPLAY_STORE_UNAVAILABLE` | `AUTHENTICATION_UNAVAILABLE` | Không thể xác định kết quả claim |
| `ACCESS_DENIED` | Authorization failure | HMAC valid, thiếu quyền |
| `IDEMPOTENCY_CONFLICT` | Business conflict | Cùng intent key nhưng payload khác |

Metric có thể là:

~~~text
hmac_authentication_attempts_total{
  route="payments", result="invalid", reason="replay"
}

hmac_replay_store_operations_total{
  operation="claim", outcome="already_used"
}
~~~

Tên metric là **minh họa** và phụ thuộc exporter; tag phải là **low cardinality**. Không dùng raw nonce, shared secret, full signature, client ID/tenant ID, raw URI hoặc body làm Prometheus labels. Security audit có thể lưu correlation ID và reason được kiểm soát, nhưng **không log secret/expected MAC/body nhạy cảm**.

Replay spike không tự chứng minh tấn công: client SDK có thể retry cùng nonce, gateway filter có thể chạy hai lần, hoặc Redis stale/inconsistent. Cần correlation với deployment, retry/error rates, clock drift và nonce store health.

### Không tạo oracle từ response

Đừng trả khác biệt quá chi tiết giữa `KEY_NOT_FOUND` và `NONCE_USED` nếu kẻ chưa xác thực có thể dò hoạt động của credential. Dùng public status/body chung theo contract, giới hạn rate và ghi reason nội bộ.

Đánh giá timing side channel theo threat model; `MessageDigest.isEqual` cho MAC bytes không có nghĩa toàn bộ HTTP path là constant-time.

## 23. Security test không phải chỉ có status 401

Một test replay chất lượng nên assert ít nhất **bốn lớp**:

| Lớp | Điều cần chứng minh |
| --- | --- |
| Cryptographic | R1 và R2 cùng exact signed bytes; MAC đúng dưới secret đã đăng ký |
| Replay state | Claim R1 = FIRST_USE; R2 = ALREADY_USED; store atomic và TTL đủ |
| HTTP/security | R1 authenticated, R2 rejected; không có principal cho R2 |
| Business | Không có business effect thứ hai: DB row, event, queue, email, payment |

Nếu chỉ kiểm tra R2 nhận 401, một implementation “luôn từ chối mọi request” cũng PASS. Nếu chỉ kiểm tra DB có một payment, idempotency có thể đã che lỗi bỏ qua replay. Nếu chỉ kiểm tra `SET NX` trong unit fake, multi-region có thể vẫn double-accept.

**Một chuỗi test nên có cả success path, negative replay path, state assertions và side-effect assertions.**

### Test replay trong request có body lớn

Body-size limit và bounded capture vẫn phải hoạt động trên cả R1/R2. Một client phát lại payload lớn có thể gây DoS nếu server buffer body không giới hạn trước khi phát hiện nonce trùng. Có thể từ chối sớm input sai format/oversized, nhưng không được ghi nonce trước MAC hợp lệ; với request body được ký, MAC thường chỉ hoàn tất sau khi đã nhận body theo contract.

## 24. Ma trận kiểm thử replay bảo mật mở rộng

| Test ID | Kịch bản | Kỳ vọng |
| --- | --- | --- |
| REPLAY-01 | R1 valid MAC, nonce N mới | First-use accepted |
| REPLAY-02 | R2 là exact copy của R1 trong timestamp window | Replay rejected |
| REPLAY-03 | R2 qua connection khác, signed bytes giữ nguyên | Replay rejected |
| REPLAY-04 | R2 gửi đồng thời với R1 | Chỉ một claim thành công |
| REPLAY-05 | 100 request cùng nonce/signature trên một JVM | Một first-use |
| REPLAY-06 | Cùng signed request qua hai service instances | Replay rejected ở instance còn lại |
| REPLAY-07 | Cùng signed request qua hai gateway | Replay rejected toàn miền |
| REPLAY-08 | Cùng request tới hai region | Theo global anti-replay guarantee, không double-accept |
| REPLAY-09 | Nonce mới nhưng signature sai | HMAC reject; không claim nonce |
| REPLAY-10 | MAC sai trước rồi MAC đúng, dùng cùng nonce | MAC đúng first-use được phép |
| REPLAY-11 | Thay nonce sau khi ký, giữ signature | Signature mismatch |
| REPLAY-12 | Thay timestamp sau khi ký, giữ signature | Signature mismatch |
| REPLAY-13 | Thay body raw bytes, giữ signature | Signature mismatch |
| REPLAY-14 | Thay URI/query/method đã ký, giữ signature | Signature mismatch |
| REPLAY-15 | Nonce quá ngắn/sai format/trùng header | Parse reject; không ghi state |
| REPLAY-16 | Timestamp ở biên dưới/trên của W | Đúng inclusive/exclusive contract |
| REPLAY-17 | Timestamp quá cũ | Reject timestamp, không kết luận nonce guard |
| REPLAY-18 | Timestamp tương lai quá W | Reject |
| REPLAY-19 | Nonce TTL hết trước khi signature hết hạn | Test FAIL/cảnh báo cấu hình không an toàn |
| REPLAY-20 | Body empty vs nonempty | Hash raw bytes đúng, R2 exact replay bị chặn |
| REPLAY-21 | Cùng nonce, đổi body và **ký lại đúng key** | Reuse nonce rejected theo scope |
| REPLAY-22 | Cùng nonce, timestamp mới, ký lại đúng key | Reuse nonce rejected khi record còn |
| REPLAY-23 | Request khai K4 nhưng ký bằng K3 | Signature mismatch; không fallback |
| REPLAY-24 | K3 REVOKED, nonce mới | Reject key state |
| REPLAY-25 | K3/K4 overlap khi rotation | Scope nonce theo contract, không bỏ revoke |
| REPLAY-26 | Client/tenant DISABLED | Reject credential/client policy |
| REPLAY-27 | Valid HMAC nhưng tenant target không có grant | Authorization denied, không data leak |
| REPLAY-28 | Nonce claim trước khi business 500 | Nonce vẫn dùng; retry có nonce mới |
| REPLAY-29 | Retry intent với nonce mới, cùng idempotency key | Không nhân đôi business effect |
| REPLAY-30 | Cùng idempotency key, payload khác | Business conflict |
| REPLAY-31 | Redis `SET NX` gặp timeout | Fail closed; không coi first-use |
| REPLAY-32 | Redis ghi thành công nhưng mất ACK | Outcome unknown; không xử lý business |
| REPLAY-33 | Redis failover mất write | Phát hiện violation của global guarantee |
| REPLAY-34 | Redis eviction trước TTL | Không cho request cũ replay |
| REPLAY-35 | Replica lag giữa hai region | Không double-accept nếu cam kết global |
| REPLAY-36 | HMAC filter đăng ký hai lần | Không gây false replay cho chính R1 |
| REPLAY-37 | Servlet ERROR/ASYNC dispatch | Không claim lại trái contract |
| REPLAY-38 | WebFlux `DataBuffer` cancel/error | Không leak memory, không tạo principal |
| REPLAY-39 | Gateway rewrite path | Positive control pass, exact replay fail |
| REPLAY-40 | Client giả gateway identity header | Không bypass HMAC/replay |
| REPLAY-41 | Direct backend access bỏ gateway | Bị network/mTLS/assertion policy chặn |
| REPLAY-42 | Internal assertion `jti` replay | Bị chặn theo internal assertion policy |
| REPLAY-43 | Body quá size limit | 413, không buffer vô hạn hoặc side effect |
| REPLAY-44 | Rate limit gây 429 trước verifier | Không nhầm thành replay failure |
| REPLAY-45 | Replay public response chứa `REPLAY_DETECTED`/key state | Test bảo mật từ chối rò thông tin theo policy |
| REPLAY-46 | Log chứa raw secret/signature/body | Test bảo mật thất bại |
| REPLAY-47 | HMAC disabled trên route mới | Synthetic probe phải phát hiện bypass |
| REPLAY-48 | R1 success nhưng event publisher phát hai lần từ R2 | Test FAIL: business side effect kép |

### Cách chia tầng

- **Unit:** REPLAY-01–05, 09–19, 21–22; fixed Clock, fake store hoặc pure verifier.
- **Integration:** REPLAY-06–07, 23–30, 36–38; Spring Security + Redis thật + DB/event fixture.
- **Distributed/fault injection:** REPLAY-08, 31–35; proxy, Redis topology/failover.
- **Security/E2E:** REPLAY-39–48; gateway trust, side effects, leakage, protected-route bypass.

Không cần ép toàn bộ bài test vào một class JUnit; điều quan trọng là mỗi yêu cầu bảo mật có **evidence độc lập** và false positive được kiểm soát.

## 25. Fault injection: phân biệt replay với dependency unavailable

Một vấn đề khó: Redis nhận lệnh `SET NX`, có thể đã ghi key, nhưng response trả về verifier bị timeout. Kết quả **không xác định**; không nên coi request là first-use để chạy nghiệp vụ.

~~~mermaid
sequenceDiagram
    participant V as HMAC Verifier
    participant R as Redis Primary
    participant B as Business
    V->>R: SET nonce NX PX
    R->>R: Có thể đã ghi
    R--xV: Network timeout / lost response
    V-->>V: UNKNOWN, fail closed
    Note over B: Không gọi business khi outcome unknown
~~~

Test:

1. Kịch bản Redis thật không khả dụng **trước khi nhận lệnh** → 503, no business.
2. Kịch bản lệnh đã commit nhưng response bị drop → 503/unknown, no business.
3. Kịch bản Redis trả `ALREADY_USED` rõ ràng → 401/replay, no business.
4. Redis restart/failover → xác minh nonce record không mất trước khi signature hết hiệu lực nếu cam kết vậy.
5. Replay store đầy bộ nhớ và eviction → test retention/fail closed.
6. Multiple instances cùng claim qua topology production → không double first-use.

**Không** tự động tái gửi chính thao tác claim rồi kết luận false nghĩa là replay của attacker. Kết quả security về phép claim trước đó đã mơ hồ; public response nên phản ánh dependency failure theo policy.

## 26. Những lỗi triển khai mà replay test phải bắt được

### 26.1. Không ký nonce

Attacker có thể thay nonce trong header mà giữ signature cho method/body. Negative test `tamper nonce, keep signature` phải reject.

### 26.2. Ghi nonce trước khi verify MAC

Attacker không biết secret vẫn có thể chiếm nonce của request hợp lệ. Test wrong-MAC first, right-MAC second phải pass ở bước thứ hai.

### 26.3. Dùng `GET` rồi `SET`

Hai requests đồng thời đều thấy key chưa tồn tại. Test concurrency/fault injection phải phát hiện double first-use.

### 26.4. Dùng local `HashSet` mỗi node

Request replay sang node khác có thể được chấp nhận. Test multi-instance cùng nonce phải fail trên implementation này.

### 26.5. TTL quá ngắn so với timestamp window

Nonce key mất khi request vẫn còn hợp lệ; replay sau TTL được chấp nhận. Test ở biên tương lai phát hiện lỗi.

### 26.6. Fail open khi replay store timeout

Cấu hình `catch(Exception) { return authenticated(); }` là lỗ hổng nghiêm trọng. Fault injection phải bảo đảm no business và 503/appropriate failure.

### 26.7. Cache kết luận “HMAC valid” theo signature

Nếu request lặp cùng signature được trả authenticated từ cache, replay guard có thể bị bỏ qua. Test R2 exact copy phải fail dù cache hit.

### 26.8. Xóa nonce khi controller lỗi

Đã có thể có event/DB side effect trước lỗi. Test business 500 rồi replay R1 phải vẫn bị reject.

### 26.9. Chỉ kiểm tra HTTP status

Một filter “always reject” cũng khiến R2 trả 401; **positive control** phải được chấp nhận trước.

### 26.10. Tin gateway header tự khai

Direct backend route hoặc spoofed `X-Authenticated-Client` có thể bỏ qua toàn bộ HMAC. Gateway trust và direct-access negative test phải có.

### 26.11. Bỏ authorization vì MAC/nonce pass

HMAC hợp lệ không có nghĩa principal được truy cập tenant khác. Test grant/resource riêng.

### 26.12. Double registration HMAC filter

R1 có thể bị claim hai lần trong cùng request; test registration và dispatch phải phát hiện false replay.

### 26.13. Dựa vào business idempotency thay vì nonce guard

Payment không bị trùng nhưng HTTP replay vẫn được authenticated, có thể khai thác ở endpoint khác không có idempotency. Test internal replay outcome độc lập.

### 26.14. Dùng lại nonce khi key rotation

Client nên tạo nonce mới cho từng attempt; scope replay phải được quy định rõ xuyên version, tránh tự vô hiệu hóa hoặc bypass bằng thay key ID.

## 27. Test checklist trước khi chấp nhận production

- [ ] Đã định nghĩa HMAC canonical contract, signed method/URI/header/body, timestamp và nonce.
- [ ] Test signer độc lập tạo chữ ký đúng secret, đúng key ID và đúng raw bytes.
- [ ] Positive control R1 với nonce mới được authenticated và có quyền cho sandbox action.
- [ ] Exact replay R2 dùng **cùng signed bytes và signature** khi timestamp vẫn còn hiệu lực.
- [ ] R2 bị từ chối ở nonce guard; không tạo authenticated principal hoặc business side effect.
- [ ] Internal reason phân biệt `REPLAY_DETECTED`, `SIGNATURE_MISMATCH` và `TIMESTAMP_OUT_OF_WINDOW`.
- [ ] Không claim nonce khi MAC sai; test wrong-MAC first → right-MAC same nonce.
- [ ] Nonce claim dùng atomic insert-if-absent + TTL; không `GET` rồi `SET`.
- [ ] TTL đủ bao phủ timestamp acceptance window kể cả timestamp ở tương lai và clock skew.
- [ ] Replay scope theo credential/client đã xác thực, không mở namespace tùy ý theo tenant.
- [ ] Multi-node/gateway/region tests phản ánh đúng global guarantee và failover topology thực.
- [ ] Redis failure/timeout/unknown outcome luôn fail closed, không fallback local store.
- [ ] Key rotation lookup đúng secret/version, key REVOKED không được chấp nhận.
- [ ] Nonce không bị xóa khi authorization/business lỗi; retry có idempotency riêng.
- [ ] Gateway rewrite/canonical target được kiểm thử bằng positive và negative cùng tuyến.
- [ ] Backend không tin forwarded/identity headers do client tự khai; internal assertion có request binding.
- [ ] Spring MVC filter không double register, controller nhận đúng body replay được.
- [ ] WebFlux DataBuffer có size limit và release/cancel; không dùng blocking Redis trên event loop.
- [ ] Không có 2xx hoặc business side effect khi MAC sai, replay, store lỗi hoặc key revoked.
- [ ] HMAC-valid không đồng nghĩa authorized: tenant/action/resource policy có test riêng.
- [ ] Public error không làm lộ key/nonce/replay state; log/metrics không chứa secret/signature/raw body.
- [ ] Security test có assert DB/events/outbox, không chỉ HTTP status.
- [ ] Synthetic probes phát hiện route mới bỏ qua HMAC filter.
- [ ] Concurrency và fault-injection tests chạy trong CI/môi trường test đã cấp phép, không dùng payment production.
- [ ] Regression tests chạy lại sau thay đổi gateway, signer SDK, key rotation, Redis topology hoặc framework.

**Replay attack test không phải bài test tính lại HMAC.** Nó phải chứng minh rằng **một request có chữ ký và dữ liệu ký đúng chỉ được dùng một lần trong phạm vi chống replay đã công bố**; mọi bản sao đến sau, kể cả đến đồng thời hoặc qua gateway khác, phải bị từ chối mà không tạo side effect. Thiết kế đúng kết hợp canonical request được ký, timestamp window, atomic nonce claim/retention, fail closed, key lifecycle và authorization độc lập; với retry nghiệp vụ, cần thêm idempotency thay vì tái sử dụng chính bằng chứng HMAC cũ.
