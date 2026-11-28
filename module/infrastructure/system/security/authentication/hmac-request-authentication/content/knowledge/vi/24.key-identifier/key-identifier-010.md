# Kiểm thử key lookup

**Key lookup** là bước server dùng **key identifier (key ID)** từ HTTP request để tìm credential record và shared secret tương ứng, rồi tính lại **expected HMAC**. Kiểm thử bước này không đơn giản là chứng minh “ID có trong map”; phải chứng minh verifier chọn **đúng ID, đúng secret, đúng algorithm, đúng audience, đúng principal và đúng key lifecycle**. Một lỗi fallback key, stale cache hoặc nhận header nhập nhằng có thể làm hỏng cả thiết kế request signing.

Bài thuộc chương **Key identifier** của mô-đun `SECURITY_AUTHENTICATION_HMAC_REQUEST_AUTHENTICATION`: xác thực HTTP request bằng HMAC trên shared secret và canonical request gồm method, URI, signed headers và/hoặc body. Bài còn đặt key lookup trong ngữ cảnh timestamp/nonce chống replay, key rotation, proxy/gateway và phân biệt authentication với authorization.

> **Nguyên tắc:** Key ID là **selector do client khai**, không phải bằng chứng xác thực. Lookup phải là **exact ID → một credential record đáng tin**; không trim/case-fold ID, không chọn khóa mặc định, không thử nhiều secret đến khi tag khớp. Chỉ tạo authenticated principal sau khi kiểm record policy, HMAC và replay/freshness thành công.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Nêu mục đích key ID và ranh giới tin cậy của key registry.
2. Thiết kế contract lookup exact-match, xử lý key ID sai grammar và HTTP header duplicates.
3. Kiểm thử unknown, expired, not-yet-active, disabled, revoked và retiring keys.
4. Kiểm thử rotation overlap, secret pairing, audience và algorithm policy.
5. Phân biệt registry `MISSING` với `UNAVAILABLE`, và thực hiện fail-closed.
6. Kiểm thử stale/negative cache, invalidation, concurrent lookups và multi-node propagation.
7. Viết Java 17 credential registry, HMAC verifier và các test cases JUnit.
8. Chứng minh key ID được đưa vào canonical request đã ký.
9. Kiểm thử thông tin lỗi, key enumeration/timing và logging an toàn.
10. Phân biệt xác thực principal từ key record với phân quyền trên resource.

## 2. Key ID không phải secret và không phải quyền

Một request minh họa:

~~~http
POST /v1/orders/42 HTTP/1.1
Host: api.example.test
Content-Type: application/json
X-Key-Id: partner-a-k3
X-Timestamp: 1800000030
X-Nonce: 6bfb21974a08417199273b09ca49a3ec
X-Signature: <base64url-hmac-sha256-tag>

{"status":"confirmed"}
~~~

Trusted registry có thể chứa:

~~~text
keyId:       partner-a-k3
principal:   partner-a-service
tenant:      tenant-A
audience:    orders-api
algorithm:   HmacSHA256
status:      ACTIVE
notBefore:   2026-01-01T00:00:00Z
notAfter:    2027-01-01T00:00:00Z
secretRef:   secret-manager/partner-a-k3
~~~

Đây là ví dụ, không phải credential thật. Production secrets phải được bảo vệ và không xuất hiện trong code/log/response.

| Thuộc tính | Nguồn | Ý nghĩa |
| --- | --- | --- |
| Key ID từ request | Caller khai, chưa xác minh | Selector cho lookup |
| Shared secret | Registry/secret manager đáng tin | Tính expected HMAC |
| Algorithm | Server-side protocol/key policy | Không phụ thuộc đề nghị tùy ý của client |
| Principal ID | Credential record | Identity sau authentication thành công |
| Tenant/audience/scope | Registry + policy | Giới hạn vùng áp dụng |
| Key status/time validity | Registry lifecycle | ACTIVE/REVOKED/RETIRING, thời hạn |
| Signed timestamp/nonce | Request + HMAC binding | Freshness và replay |
| Authorization | Server resource policy | Quyền thực hiện action |

**Biết key ID không chứng minh sở hữu secret.** Key ID thường là định danh công khai hoặc opaque, nhưng vẫn có thể tiết lộ tenant/đối tác nếu đặt theo tên thật; vì vậy logging/enumeration cần policy.

### 2.1. Không tạo principal ngay khi lookup tìm thấy record

Sai:

~~~java
KeyRecord record = registry.lookup(keyId);
securityContext.setPrincipal(record.principalId()); // Chưa verify HMAC!
~~~

Đúng về thứ tự:

~~~text
validate HTTP and key ID grammar
  -> exact registry lookup
  -> validate key record/status/algorithm/audience
  -> rebuild canonical request from received HTTP bytes
  -> HMAC(expected) and compare full tag
  -> check timestamp freshness and atomic nonce admission
  -> trusted principal from key record
  -> authorize(action, resource, tenant)
~~~

Không ghi nonce hay cấp principal từ **request chưa qua MAC**, vì attacker có thể giả key ID, chiếm replay namespace hoặc tạo identity giả.

## 3. Contract exact-match lookup

Một interface có ý nghĩa:

~~~text
lookupExact(keyId) -> FOUND(exactly one record)
                   | MISSING
                   | UNAVAILABLE
~~~

**Không** làm:

~~~text
find first key by prefix
query records with LIKE
lowercase/trim/percent-decode ID before lookup
pick newest ACTIVE key for tenant when ID missing
try k1, k2, k3 secrets until one signature verifies
~~~

Một key ID phải chọn **đúng một credential record và một secret/algorithm xác định**. Registry cần unique constraint theo ID hoặc guarantee tương đương. Không biến key rotation thành một vòng lặp thử mọi secret.

### 3.1. Key ID grammar V1

~~~text
[A-Za-z0-9_-]{1,64}
~~~

- 1–64 ký tự ASCII.
- **Case-sensitive**: `Partner-A-k3` khác `partner-a-k3`.
- Reject spaces/tabs, CR/LF, NUL, Unicode, slash, colon, dot, percent.
- Không auto `trim()`/`toLowerCase()` hoặc Unicode normalization.
- Không alias, prefix matching hay fallback.
- Production scheme khác có thể dùng grammar khác, nhưng phải công bố version và test chính xác.

### 3.2. Test table input key ID

| Input | Kỳ vọng |
| --- | --- |
| `partner-a-k3` | Format hợp lệ |
| `PARTNER-A-K3` | Format hợp lệ nhưng là **ID khác** |
| ` partner-a-k3` | Reject |
| `partner-a-k3 ` | Reject |
| `partner.a.k3` | Reject |
| `partner/a/k3` | Reject |
| `partner%2Da-k3` | Reject, không percent-decode |
| Ký tự Cyrillic trông giống Latin | Reject non-ASCII |
| CR/LF, NUL, TAB, DEL | Reject tại HTTP boundary |
| Null hoặc chuỗi rỗng | Reject |
| 65 ký tự | Reject |

HTTP **field names** case-insensitive nhưng **key ID values** theo protocol này case-sensitive. Hai quy tắc không được đánh đồng.

### 3.3. Duplicate ID headers

~~~http
X-Key-Id: partner-a-k2
x-key-id: partner-a-k3
~~~

Đây là hai occurrences cùng field name. Edge HTTP parser phải **reject**, không first-wins hoặc last-wins; ngay cả khi cả hai values giống nhau vẫn reject để không tạo nhiều representations của cùng credential.

Nếu key ID nằm trong `Authorization`, cần đúng **một Authorization field** và grammar cố định. Nếu ứng dụng hỗ trợ đồng thời cả `Authorization` và `X-Key-Id`, phải có policy đối chiếu rõ, tốt nhất là chọn một nguồn chính và reject nguồn xung đột.

### 3.4. Proxy có thể làm mất dấu duplicates

`HttpServletRequest.getHeader("X-Key-Id")` thường chỉ trả một value. `getHeaders` đọc danh sách mà container còn giữ lại, **không phục hồi raw headers đã bị gateway merge/drop**. Vì vậy test duplicate cần gửi raw requests vào ingress/gateway thật, không chỉ mock Java controller.

## 4. Danh mục invariant cần chứng minh

Key lookup được coi đúng chỉ khi các tính chất sau cùng được bảo vệ:

| Invariant | Phép kiểm thử |
| --- | --- |
| Exactly one ID trên request | Duplicates, case-variant names bị reject |
| Exact match | Case changes/prefix/suffix không chọn record gốc |
| One ID → one record | Duplicate rows vi phạm unique constraint |
| No fallback | MISSING không thử default/tenant's newest key |
| Secret pairing | Tag tính bằng k2 không được chấp nhận khi request khai k3 |
| Server-selected algorithm | Caller khai algorithm khác không đổi HMAC algorithm |
| Correct audience | Orders key không gọi payments API |
| Lifecycle enforcement | REVOKED/DISABLED/PROVISIONED reject |
| Temporal validity | notBefore inclusive, notAfter exclusive |
| RETIRING overlap | Chỉ verify trong khoảng policy cho phép |
| Key ID bound to MAC | Thay key ID mà giữ tag cũ bị reject |
| Principal trust | Principal lấy từ registry chỉ sau MAC, không từ caller role |
| Lookup outage | Không cho request đi tiếp |
| No secret leakage | Logs/errors không chứa shared secret hoặc expected tag |
| Rotation consistency | Nodes không tiếp tục chấp nhận key cũ ngoài policy |
| Replay integrity | MAC sai không claim nonce |
| Same HTTP semantics | Gateway/backend không parse key ID khác nhau |

### 4.1. Phân biệt FIND, MISSING, UNAVAILABLE

~~~text
FOUND(record):      exact ID tồn tại
MISSING:            nguồn lookup đáng tin xác nhận không tồn tại
UNAVAILABLE:        không thể có kết quả đáng tin (timeout/partition/error)
INVALID_KEY_ID:     bị reject ở parser trước lookup
~~~

Một network timeout **không phải** bằng chứng key ID không tồn tại. Trả kết quả nội bộ đúng loại giúp vận hành, rate-limiting và incident analysis. Mặt ngoài API có thể dùng generic authentication errors để hạn chế key enumeration, nhưng không nên bỏ qua `UNAVAILABLE` để tăng tỷ lệ thành công.

### 4.2. Fail closed khi registry và secret manager lỗi

Nếu exact record tồn tại nhưng secret manager trả lỗi, không dùng:

- Secret mặc định của service.
- Một secret cũ được cache ngoài tuổi hiệu lực nếu policy không cho.
- Secret mới nhất của cùng principal.
- Empty key hoặc key sinh từ chuỗi key ID.
- Một thuật toán khác để “thử cho tương thích”.

Những lựa chọn đó có thể làm mất tính ràng buộc key ID và trạng thái revocation. Với API nhạy cảm, không có trusted key record/secret nghĩa là **không thể xác minh request**, nên phải từ chối.

### 4.3. Error messages và key-existence oracle

Response nên hạn chế rò rỉ chi tiết:

~~~text
Không trả cho caller:
"Key partner-a-k3 exists but signature mismatched"
"Key partner-a-k3 expired at 08:13:02"
"Expected MAC bytes 0..7: ..."
"Trying fallback key k2"
~~~

Một hệ thống có thể trả HTTP authentication failure chung, và theo contract trả temporary failure phù hợp khi phụ thuộc nội bộ không hoạt động. Internal metrics vẫn cần `AUTH_KEY_LOOKUP_MISSING`, `AUTH_KEY_REVOKED`, `AUTH_KEY_LOOKUP_UNAVAILABLE`, nhưng **redact** dữ liệu nhạy cảm.

**Timing:** MISSING có thể reject nhanh, FOUND có thể tốn thời gian HMAC và secret lookup; đó có thể là **key-existence timing oracle**. `MessageDigest.isEqual` chỉ giảm leak trong so tag, không làm toàn bộ key lookup constant-time. Đánh giá theo threat model, số lượt probing, rate limits, key ID entropy, response policy và đo có kiểm soát; không khẳng định một benchmark ít mẫu đã chứng minh không có leak.

## 5. Vòng đời khóa và thời gian hiệu lực

Một credential record có thể có:

~~~text
keyId        = partner-a-k3
status       = ACTIVE / RETIRING / DISABLED / REVOKED
notBefore    = 2026-01-01T00:00:00Z
notAfter     = 2027-01-01T00:00:00Z
verifyUntil  = optional overlap cutoff for RETIRING
audience     = orders-api
algorithm    = HmacSHA256
secretRef    = secrets/partner-a-k3
principal    = partner-a-service
tenant       = tenant-A
~~~

### 5.1. Policy status minh họa

| Status | Được verify? | Lưu ý |
| --- | --- | --- |
| PROVISIONED | Không | Key chưa active |
| ACTIVE | Có nếu audience/algorithm/time hợp lệ | Chữ ký và anti-replay vẫn bắt buộc |
| RETIRING | Có chỉ trong overlap được policy cho phép | Không khuyến khích client ký request mới |
| REVOKED | Không | Emergency hoặc kết thúc lifecycle |
| DISABLED | Không | Tạm khóa credential |

Không chỉ dựa vào status text. Một key ACTIVE nhưng đã hết notAfter vẫn reject; key RETIRING có verifyUntil đã qua cũng reject.

### 5.2. Contract thời gian rõ ràng

\[
\text{validAt}(t) \iff \text{notBefore} \le t < \text{notAfter}
\]

- notBefore **inclusive**.
- notAfter **exclusive**.
- `Instant` và UTC; không dùng local timezone.
- Reject khoảng rỗng/đảo ngược: `notAfter <= notBefore`.
- Check thêm `verifyUntil` cho RETIRING.
- Không mặc định dùng signed client timestamp để “quay thời gian” key status về quá khứ. Key policy thường được kiểm tại **thời điểm server admission**, kể cả client ký từ trước khi revoke.

### 5.3. Key rotation k2 → k3

~~~text
k2 -> secret-v2, RETIRING until time T
k3 -> secret-v3, ACTIVE from time T0
~~~

Các kiểm thử quan trọng:

| Key ID trên request | Secret tạo tag | Kỳ vọng |
| --- | --- | --- |
| k2 | secret-v2 | Có thể pass trong overlap |
| k3 | secret-v3 | Pass khi ACTIVE |
| k2 | secret-v3 | Reject |
| k3 | secret-v2 | Reject |
| k9 không tồn tại | secret-v2 | Reject |
| k2 đã REVOKED | secret-v2 | Reject dù tag cryptographically correct |
| k3 trước notBefore | secret-v3 | Reject |
| k2 sau verifyUntil | secret-v2 | Reject |

**Không** thử secret-v2 sau khi request khai k3. Nếu key ID chỉ là label gắn với principal chung còn secret được chọn bằng vòng lặp, sẽ khó đảm bảo revocation/rotation đúng và audit không thể giải thích “request thực sự dùng key nào”.

### 5.4. Không tái sử dụng ID cho secret mới

Một policy an toàn là **mỗi key rotation tạo key ID mới**. Nếu thay secret dưới cùng một ID trong khi caches còn secret cũ, các verifier nodes có thể cho kết quả khác nhau. Trong trường hợp bắt buộc re-key cùng ID, cần protocol/version policy và atomic lifecycle transition được kiểm thử riêng; mặc định tránh alias ID này.

## 6. Test key ID được ký trong canonical request

Đây là một canonical request minh họa:

~~~text
HMAC-REQUEST-V1
POST
/v1/orders/42
dryRun=false
audience:orders-api
content-type:application/json
key-id:partner-a-k3
timestamp:1800000030
nonce:6bfb21974a08417199273b09ca49a3ec
body-sha256:<actual-hex-digest-of-raw-body>
~~~

Client tính:

~~~text
canonicalBytes = UTF8(canonicalRequest)
signature = Base64URL_NoPadding(HMAC-SHA256(secretForK3, canonicalBytes))
~~~

Verifier **không tin** canonical string do caller khai; nó tái tạo từ method, path/query, validated signed headers, raw body digest và metadata ở HTTP boundary đáng tin.

### 6.1. Metamorphic test tráo ID

1. Tạo request đúng với key ID k3 và secret-v3.
2. Đảm bảo key ID xuất hiện trong canonical bytes.
3. Đổi request key ID thành k2 nhưng **giữ nguyên tag**.
4. Verifier lookup exact k2 và tính expected HMAC theo k2/canonical ID k2.
5. Kết quả **phải reject**.

Test phải thất bại nếu ai đó “tối ưu” verifier bằng cách bỏ key ID khỏi canonical request hoặc thử các keys của principal đến khi tag khớp.

### 6.2. Trường hợp key ID trong Authorization

Nếu protocol dùng:

~~~http
Authorization: HMAC-V1 k3.1800000030.6bfb21974a08417199273b09ca49a3ec.<signature>
~~~

thì parser phải trích **đúng một key ID**, validate grammar, và ràng buộc key ID này trong canonical bytes. **Không** ký nguyên field Authorization chứa tag đầu ra vào chính input tạo tag (phụ thuộc vòng). Tương tự, timestamp và nonce cần được ký.

### 6.3. Algorithm/audience cũng phải được ràng buộc đáng tin

- Algorithm chọn theo key record/protocol version phía server, không tin `X-Algorithm: none`.
- Audience nằm trong canonical marker/signed metadata và được đối chiếu route/key record.
- Không cho cùng secret tùy tiện dùng xuyên service mà thiếu signed audience.
- Nếu client có quyền chọn danh sách signed headers, phải enforce **mandatory signed fields** từ server và từ chối downgrade.

### 6.4. Raw HTTP identity nhất quán qua gateway

Một proxy có thể strip path prefix, đổi HTTP/1.1↔HTTP/2, normalize URI hoặc gộp headers. Nếu signer/verifier/handler dùng những representations khác nhau, một HMAC đúng có thể bảo vệ request semantics khác với thao tác handler thực hiện. Test e2e phải xác nhận đúng **signing boundary** và cùng method/path/query/header/body tại verifier và router.

## 7. Test negative caching và key metadata cache

Lookup thường được cache để giảm độ trễ DB/secret manager. Cache là tối ưu hiệu năng nhưng có thể làm thay đổi **quyết định bảo mật** nếu không có TTL và invalidation policy rõ.

### 7.1. Cache hit và miss

Kiểm tra:

1. Lần đầu k3 chưa cache → registry trả record k3.
2. Lần thứ hai k3 trong cache → trả **cùng identity/status/algorithm/secret version** theo policy.
3. Cache miss → fetch đúng **một** record, không fetch theo tenant wildcard.
4. Không dùng stale record khi policy yêu cầu xác nhận trạng thái mới.
5. Không để cache key bị collisions do normalize/shorten key ID.

### 7.2. Negative caching

Cache `MISSING` có thể giảm enumeration load, nhưng khi key k4 **vừa được provision**, entry negative stale có thể làm request hợp lệ bị từ chối:

~~~text
T1: lookup(k4) -> MISSING, cache negative
T2: create and activate k4 in registry
T3: verifier sees cached MISSING -> rejects until expiry/invalidation
~~~

Đây thường là **availability/consistency bug**, không trực tiếp là accept unauthorized. Dù vậy cần test bootstrap/rotation propagation và xử lý cache invalidation.

### 7.3. Stale ACTIVE sau revoke là lỗi bảo mật

~~~text
T1: node A caches k2 ACTIVE + secret-v2
T2: central registry REVOKES k2
T3: node A still sees cached ACTIVE
T4: attacker with stolen secret-v2 signs request
T5: node A accepts despite revocation
~~~

Đây là tình huống nghiêm trọng hơn negative cache: cho phép credential không còn được chấp nhận. Thiết kế phải công bố **maximum revocation propagation delay** và liệu emergency revoke có cần immediate invalidation hoặc fail-closed check. Không có cache TTL nào tự bảo đảm “thu hồi tức thì” nếu không có một cơ chế consistency/invalidation đáp ứng yêu cầu.

### 7.4. Key cache và clock drift

Key có notAfter theo UTC, nhưng các nodes có clock lệch. Node chậm có thể coi key còn hiệu lực sau node nhanh. Cần đồng bộ clock, giám sát offset, kiểm tra time boundaries và policy rõ khi clock vượt ngưỡng cho phép.

### 7.5. Single-flight và concurrent reload

Nhiều threads cùng lookup k3 khi cache hết hạn có thể tạo request storm tới registry. Single-flight/coalescing là tối ưu hợp lý, nhưng phải kiểm tra:

- Caller nào cũng nhận **cùng** result/policy.
- Exceptions/timeouts không bị biến thành fake FOUND.
- Cache entry không chứa một secret reference bị đổi sang credential khác.
- Concurrent refresh và revoke không cho phép stale value ghi đè metadata mới.
- Không giữ secret trong logs/metrics hoặc exception traces.

## 8. Điểm phân biệt authentication và authorization

Key lookup trả record với `principalId=partner-a-service`, `tenant=tenant-A`. Sau HMAC và replay pass, server có thể tạo authenticated principal đó.

Nhưng nếu request target là:

~~~http
DELETE /v1/tenants/tenant-B/orders/42 HTTP/1.1
X-Key-Id: partner-a-k3
X-Timestamp: 1800000030
X-Nonce: 6bfb21974a08417199273b09ca49a3ec
X-Signature: <valid-tag-with-k3-secret>
~~~

thì key lookup có thể **FOUND**, MAC đúng, timestamp fresh và nonce mới, nhưng **authorization phải từ chối** vì principal A không có quyền trên tenant B.

Không dùng `X-Tenant-Id` hoặc `X-Role` caller tự khai làm nguồn quyền; HMAC ký một lời yêu cầu không có nghĩa server cấp quyền theo nội dung lời yêu cầu.

## 9. Java 17: mô hình credential và registry có thể kiểm thử

Ví dụ sau tập trung vào **key lookup contract**. Trong hệ thống thật, credential metadata và secret thường nằm ở các services/storage riêng, secret có thể ở KMS/HSM. Để học và unit test, ta dùng một immutable-ish credential record chứa bản sao secret bytes, chỉ sử dụng test secrets.

### 9.1. KeyStatus và KeyRecord

~~~java
public enum KeyStatus {
    PROVISIONED, ACTIVE, RETIRING, DISABLED, REVOKED
}
~~~

~~~java
import java.time.Instant;
import java.util.Objects;

public record KeyRecord(
        String keyId,
        String principalId,
        String tenantId,
        String audience,
        String algorithm,
        KeyStatus status,
        Instant notBefore,
        Instant notAfter,
        Instant verifyUntil,
        byte[] secret) {

    public KeyRecord {
        Objects.requireNonNull(keyId);
        Objects.requireNonNull(principalId);
        Objects.requireNonNull(tenantId);
        Objects.requireNonNull(audience);
        Objects.requireNonNull(algorithm);
        Objects.requireNonNull(status);
        Objects.requireNonNull(notBefore);
        Objects.requireNonNull(notAfter);
        Objects.requireNonNull(secret);

        if (!notBefore.isBefore(notAfter) || secret.length == 0) {
            throw new IllegalArgumentException("Invalid record");
        }

        // Tránh caller sửa secret input array sau khi tạo record.
        secret = secret.clone();
    }

    @Override
    public byte[] secret() {
        // Tránh để caller sửa secret của record.
        return secret.clone();
    }
}
~~~

**Giới hạn:** `record` chứa secret trong heap phù hợp cho unit test; production cần hạn chế vòng đời secret, truy cập có phân quyền và zeroization khi có thể. Không dùng `toString()` tự sinh của record chứa `secret` trong logs; dù `byte[]` thường in dạng identity, không dựa vào đó như một ranh giới bảo mật. Redact metadata/sensitive data một cách chủ động.

### 9.2. Interface registry với MISSING và UNAVAILABLE tách biệt

~~~java
import java.util.Optional;

public interface CredentialRegistry {
    /**
     * Exact lookup by one validated key ID.
     * Empty = a trustworthy lookup established that ID is absent.
     * Exception = registry cannot give a trustworthy result.
     */
    Optional<KeyRecord> findExact(String keyId)
            throws KeyLookupUnavailableException;
}
~~~

~~~java
public final class KeyLookupUnavailableException
        extends RuntimeException {

    public KeyLookupUnavailableException(String message) {
        super(message);
    }
}
~~~

Không dùng `Optional.empty()` để báo timeout/partition. Một controller có thể map hai lỗi sang response bên ngoài theo policy, nhưng chúng có nguyên nhân và retry behavior khác.

### 9.3. Strict key ID validation

~~~java
import java.util.regex.Pattern;

public final class KeyIdV1 {
    private static final Pattern ID =
            Pattern.compile("[A-Za-z0-9_-]{1,64}");

    private KeyIdV1() {}

    public static String validateExact(String raw) {
        if (raw == null || !ID.matcher(raw).matches()) {
            throw new IllegalArgumentException("Invalid key ID");
        }

        // Không normalize, trim, lowercase hoặc percent-decode.
        return raw;
    }
}
~~~

Pattern trong Java cần `matches()`, không dùng `find()`, để từ chối một chuỗi hợp lệ có thêm suffix độc hại.

### 9.4. Chính sách key validity và audience

~~~java
import java.time.Instant;
import java.util.Objects;

public final class KeyPolicyV1 {
    private KeyPolicyV1() {}

    public static boolean canVerify(
            KeyRecord key, String expectedAudience, Instant now) {

        Objects.requireNonNull(key);
        Objects.requireNonNull(expectedAudience);
        Objects.requireNonNull(now);

        if (!key.audience().equals(expectedAudience)
                || !"HmacSHA256".equals(key.algorithm())
                || now.isBefore(key.notBefore())
                || !now.isBefore(key.notAfter())) {
            return false;
        }

        return switch (key.status()) {
            case ACTIVE -> true;
            case RETIRING -> key.verifyUntil() != null
                    && now.isBefore(key.verifyUntil());
            case PROVISIONED, DISABLED, REVOKED -> false;
        };
    }
}
~~~

**Bài test cần phát hiện:** Một implementation chỉ kiểm `status == ACTIVE` mà quên `notAfter` sẽ nhận key hết hạn. Một implementation cho RETIRING dù `verifyUntil == null` sẽ làm overlap không có giới hạn.

### 9.5. In-memory fake registry, chỉ dành cho test

~~~java
import java.util.Map;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;

public final class FakeRegistry implements CredentialRegistry {
    private final Map<String, KeyRecord> records =
            new ConcurrentHashMap<>();
    private final AtomicInteger calls = new AtomicInteger();
    private volatile boolean unavailable;

    public void put(KeyRecord record) {
        records.put(record.keyId(), record);
    }

    public void remove(String id) {
        records.remove(id);
    }

    public void setUnavailable(boolean value) {
        unavailable = value;
    }

    public int calls() {
        return calls.get();
    }

    @Override
    public Optional<KeyRecord> findExact(String id) {
        calls.incrementAndGet();

        if (unavailable) {
            throw new KeyLookupUnavailableException(
                    "Registry unavailable");
        }
        return Optional.ofNullable(records.get(id));
    }
}
~~~

Fake này cố ý không tự normalize key IDs. Nó **không** chứng minh cache consistency, KMS permissions, DB isolation hoặc multi-node behavior; những điều đó cần integration/failure tests riêng.

## 10. Java 17: xác minh HMAC theo đúng record đã lookup

Ta muốn phân biệt:

- `INVALID_ID`: ID sai format, không query registry.
- `UNKNOWN_KEY`: exact ID không có record.
- `KEY_NOT_ALLOWED`: record không cho verify theo policy/time/audience.
- `LOOKUP_UNAVAILABLE`: registry/KMS không thể đưa kết quả đáng tin.
- `MAC_MISMATCH`: HMAC theo đúng record không khớp.
- `MAC_VALID`: tag đúng cho expected canonical bytes **nhưng chưa hoàn thành chống replay hoặc authorization**.

### 10.1. Result type không tự cấp quyền

~~~java
public enum VerifyOutcome {
    INVALID_ID,
    UNKNOWN_KEY,
    KEY_NOT_ALLOWED,
    LOOKUP_UNAVAILABLE,
    MAC_MISMATCH,
    MAC_VALID
}
~~~

**Không** trả `principalId` trong response khi `MAC_MISMATCH`, dù lookup đã tìm thấy record. Principal chỉ được thiết lập khi MAC hợp lệ và các bước freshness/replay đạt yêu cầu.

### 10.2. Verifier helper Java 17

~~~java
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.time.Clock;
import java.util.Optional;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public final class KeyLookupVerifierV1 {
    private final CredentialRegistry registry;
    private final Clock clock;

    public KeyLookupVerifierV1(
            CredentialRegistry registry, Clock clock) {
        this.registry = registry;
        this.clock = clock;
    }

    /**
     * PRECONDITION:
     * - trustedCanonicalBytes do HTTP adapter/verifier tự tái dựng.
     * - key ID là metadata được bao phủ trong canonical bytes.
     * - presentedTag đã strict Base64URL decode về full 32 bytes.
     * - không có duplicated/ambiguous signed headers.
     *
     * Helper này chỉ đánh giá LOOKUP + HMAC, chưa kiểm nonce/authz.
     */
    public VerifyOutcome verifyMac(
            String rawKeyId,
            byte[] trustedCanonicalBytes,
            byte[] presentedTag) {

        final String keyId;
        try {
            keyId = KeyIdV1.validateExact(rawKeyId);
        } catch (IllegalArgumentException badId) {
            return VerifyOutcome.INVALID_ID;
        }

        if (trustedCanonicalBytes == null
                || presentedTag == null
                || presentedTag.length != 32) {
            return VerifyOutcome.MAC_MISMATCH;
        }

        final Optional<KeyRecord> found;
        try {
            found = registry.findExact(keyId);
        } catch (KeyLookupUnavailableException unavailable) {
            return VerifyOutcome.LOOKUP_UNAVAILABLE;
        }

        if (found.isEmpty()) {
            return VerifyOutcome.UNKNOWN_KEY;
        }

        KeyRecord record = found.get();
        if (!record.keyId().equals(keyId)
                || !KeyPolicyV1.canVerify(
                        record, "orders-api", clock.instant())) {
            return VerifyOutcome.KEY_NOT_ALLOWED;
        }

        byte[] expected;
        try {
            Mac mac = Mac.getInstance(record.algorithm());
            mac.init(new SecretKeySpec(
                    record.secret(), record.algorithm()));
            expected = mac.doFinal(trustedCanonicalBytes);
        } catch (GeneralSecurityException cryptoFailure) {
            // Không chấp nhận request nếu crypto bị lỗi.
            return VerifyOutcome.LOOKUP_UNAVAILABLE;
        }

        return MessageDigest.isEqual(expected, presentedTag)
                ? VerifyOutcome.MAC_VALID
                : VerifyOutcome.MAC_MISMATCH;
    }
}
~~~

**Ranh giới của ví dụ:** Hàm nhận `trustedCanonicalBytes` theo **precondition**. Trong production, không bao giờ nhận một canonical string do client đưa vào như “đã tin”. HTTP adapter phải tự tạo canonical bytes có chứa **key ID thực nhận** và method/path/query/headers/body đúng contract. Có thể thay kiểu `byte[]` bằng một giá trị chỉ được tạo bởi trusted canonicalizer để dễ enforce trong kiến trúc.

### 10.3. Không so String signatures hoặc MAC prefix

~~~java
// Không dùng phép so này cho HMAC tag:
expectedHex.startsWith(presentedHex);
expectedHex.equals(presentedHex);
java.util.Arrays.equals(expectedTag, suppliedTag);
~~~

Decode signature vào 32 byte rồi dùng `MessageDigest.isEqual`. Việc key lookup chạy nhanh/chậm không tự trở thành constant-time, nhưng comparator không nên cố tình thoát sớm theo số byte khớp.

### 10.4. Nên phân loại crypto failure rõ hơn trong production

Trong helper, crypto exception được quy về outcome không chấp nhận để minh họa fail-closed. Production nên có phân loại riêng **CRYPTO_UNAVAILABLE/CONFIG_ERROR**, telemetry bảo mật và exception handling chủ động; không để algorithm bị caller thay, không silently fallback sang algorithm cũ.

### 10.5. Một lớp key record/secret manager thật có thể bất đồng thời điểm

Nếu registry trả metadata ACTIVE nhưng secret manager trả secret đã bị rotate/revoke, cần chọn một protocol version/secret reference nhất quán theo record. Không fetch “latest secret for principal” độc lập với key ID. Test phải ghép **ID, status, version, secretRef và secret bytes** chính xác.

## 11. Kết nối với freshness, replay và principal

Một request có `MAC_VALID` vẫn chưa được xử lý nghiệp vụ:

~~~mermaid
flowchart TD
    A[HTTP request] --> B[Strict header parsing and key ID grammar]
    B --> C[Exact key registry lookup]
    C --> D[Key status, audience, algorithm, validity]
    D --> E[Server canonical bytes + expected HMAC]
    E --> F{Full MAC matches?}
    F -- No --> X[Reject authentication]
    F -- Yes --> G{Signed timestamp fresh?}
    G -- No --> X
    G -- Yes --> H[Atomic claim signed nonce]
    H --> I{Nonce new and store reliable?}
    I -- No --> X
    I -- Yes --> J[Principal from trusted key record]
    J --> K{Authorized action/resource/tenant?}
    K -- No --> Y[Reject authorization]
    K -- Yes --> L[Business handler with idempotency]
~~~

### 11.1. TTL phải bao phủ toàn freshness window

Đặt `A` là max past age, `F` là future skew, `M` là operational/clock margin. Một TTL nonce bảo thủ:

\[
\text{nonceTtl} \ge A + F + M
\]

Ví dụ `A=300` giây, `F=30` giây, `M=30` giây → 360 giây. Nếu lưu nonce chỉ 300 giây từ lần nhận đầu mà signed timestamp hợp lệ ở mép tương lai, replay entry có thể hết trước khi request stale.

### 11.2. Nonce được claim sau MAC

Khi `verifyMac` trả `MAC_VALID`, verifier mới kiểm timestamp và claim nonce bằng shared store atomic insert-if-absent. Nếu key lookup thất bại hoặc HMAC mismatch, **không ghi nonce** vào replay store. Nếu registry/nonce store unavailable, chọn fail-closed theo security policy.

### 11.3. Không trộn authentication với authorization

Sau MAC/freshness/replay, principal từ record `partner-a-service` có thể được authenticated. Nhưng authorization vẫn phải kiểm tra principal đó được phép sửa order/tenant trong URI hay không. Một `X-Role: admin` do client tự khai không phải bằng chứng server đã cấp role, kể cả nếu nó được HMAC ký.

## 12. JUnit 5: test exact lookup và key-secret pairing

Các test sau dùng Java 17, JUnit Jupiter, `FakeRegistry`, `KeyRecord` và `KeyLookupVerifierV1` ở mục trước. Đặt mỗi `public class/record` vào file Java tương ứng nếu chạy như project thật. Đây là **bộ ví dụ học thuật**, không phải code đã được chạy/QA trong STEP 4.

### 12.1. Dữ liệu test và HMAC fixture

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

public class KeyLookupVerifierV1Test {
    private static final Instant NOW =
            Instant.parse("2026-06-15T12:00:00Z");

    private static final Clock CLOCK =
            Clock.fixed(NOW, ZoneOffset.UTC);

    private static final byte[] SECRET_K2 =
            "test-only-secret-for-key-two".getBytes(
                    StandardCharsets.US_ASCII);

    private static final byte[] SECRET_K3 =
            "test-only-secret-for-key-three".getBytes(
                    StandardCharsets.US_ASCII);

    private FakeRegistry registry;
    private KeyLookupVerifierV1 verifier;

    @BeforeEach
    void setup() {
        registry = new FakeRegistry();
        verifier = new KeyLookupVerifierV1(registry, CLOCK);

        registry.put(record("partner-a-k2",
                SECRET_K2, KeyStatus.RETIRING));
        registry.put(record("partner-a-k3",
                SECRET_K3, KeyStatus.ACTIVE));
    }

    private static KeyRecord record(
            String id, byte[] secret, KeyStatus status) {
        return new KeyRecord(
                id,
                "partner-a-service",
                "tenant-A",
                "orders-api",
                "HmacSHA256",
                status,
                NOW.minusSeconds(86_400),
                NOW.plusSeconds(86_400),
                NOW.plusSeconds(3_600),
                secret);
    }

    private static byte[] canonical(String id) {
        // Test fixture do server-side builder giả lập tạo.
        // Key ID PHẢI nằm trong những bytes được ký.
        String message = String.join("\n",
                "HMAC-REQUEST-V1",
                "POST",
                "/v1/orders/42",
                "",
                "audience:orders-api",
                "content-type:application/json",
                "key-id:" + id,
                "timestamp:1800000030",
                "nonce:6bfb21974a08417199273b09ca49a3ec",
                "body-sha256:"
                    + "3a6eb0790f39ac87c94f3856b2dd2c5d"
                    + "110e6811602261a9a923d3bb23adc8b7");
        return message.getBytes(StandardCharsets.UTF_8);
    }

    private static byte[] sign(byte[] secret, byte[] canonical)
            throws GeneralSecurityException {

        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(secret, "HmacSHA256"));
        return mac.doFinal(canonical);
    }

    @Test
    void exactIdAndMatchingSecretPass() throws Exception {
        byte[] message = canonical("partner-a-k3");
        byte[] tag = sign(SECRET_K3, message);

        assertEquals(VerifyOutcome.MAC_VALID,
                verifier.verifyMac("partner-a-k3", message, tag));
    }

    @Test
    void samePrincipalDoesNotAllowWrongSecret() throws Exception {
        byte[] message = canonical("partner-a-k3");
        byte[] tagSignedWithK2 = sign(SECRET_K2, message);

        assertEquals(VerifyOutcome.MAC_MISMATCH,
                verifier.verifyMac(
                        "partner-a-k3", message, tagSignedWithK2));
    }

    @Test
    void unknownIdDoesNotFallBackToK2() throws Exception {
        byte[] message = canonical("partner-a-k9");
        byte[] tagSignedWithK2 = sign(SECRET_K2, message);

        assertEquals(VerifyOutcome.UNKNOWN_KEY,
                verifier.verifyMac(
                        "partner-a-k9", message, tagSignedWithK2));
    }

    @Test
    void changingKeyIdWithoutResigningFails() throws Exception {
        byte[] canonicalK3 = canonical("partner-a-k3");
        byte[] oldTag = sign(SECRET_K3, canonicalK3);

        // Simulates server constructing bytes for the altered key ID.
        byte[] canonicalK2 = canonical("partner-a-k2");

        assertEquals(VerifyOutcome.MAC_MISMATCH,
                verifier.verifyMac(
                        "partner-a-k2", canonicalK2, oldTag));
    }

    @Test
    void caseVariantIsDifferentCredential() throws Exception {
        byte[] bytes = canonical("PARTNER-A-K3");
        byte[] tag = sign(SECRET_K3, bytes);

        assertEquals(VerifyOutcome.UNKNOWN_KEY,
                verifier.verifyMac("PARTNER-A-K3", bytes, tag));
    }

    @Test
    void invalidIdIsRejectedBeforeLookup() {
        byte[] any = canonical("partner-a-k3");
        byte[] tag = new byte[32];
        int before = registry.calls();

        assertEquals(VerifyOutcome.INVALID_ID,
                verifier.verifyMac(" partner-a-k3", any, tag));
        assertEquals(before, registry.calls());
    }

    @Test
    void registryOutageIsNotMissingKey() throws Exception {
        registry.setUnavailable(true);
        byte[] bytes = canonical("partner-a-k3");
        byte[] tag = sign(SECRET_K3, bytes);

        assertEquals(VerifyOutcome.LOOKUP_UNAVAILABLE,
                verifier.verifyMac("partner-a-k3", bytes, tag));
    }
}
~~~

**Ý nghĩa:** Test `wrongSecret` không chỉ chứng minh HMAC khác secret cho tag khác; nó bảo vệ invariant “lookup k3 → chỉ dùng secret k3”, kể cả k2 và k3 cùng principal. Test `invalidIdIsRejectedBeforeLookup` chứng minh input sai grammar không gây registry query.

### 12.2. Ghi chú về canonical fixture

`canonical(id)` trong test tạo một chuỗi cố định và bao gồm key ID. Nó **không phải thư viện canonical request đầy đủ**. Production phải build canonical bytes từ HTTP request được parser/gateway xác nhận, gồm method/path/query, signed headers, raw body digest và metadata đúng contract. Test riêng phải chứng minh không có khoảng trống giữa bytes được ký và request handler thực thi.

### 12.3. Tại sao unknown-key test ký với secret k2?

Ta muốn phát hiện implementation kiểu:

~~~text
lookup k9 -> missing
fallback to tenant's active key k2
HMAC(secret-k2, message-of-k9) -> match
accept
~~~

Bằng cách tạo tag **cố tình đúng với fallback secret**, test đảm bảo hệ thống vẫn trả `UNKNOWN_KEY`. Nếu test chỉ dùng random invalid tag, một implementation có fallback nhưng tag vẫn không khớp có thể vượt qua test mà không bộc lộ bug.

## 13. JUnit 5: kiểm tra key lifecycle và time boundaries

Các test sau dùng `KeyPolicyV1.canVerify`, dễ tách khỏi HMAC để nhìn rõ policy:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.nio.charset.StandardCharsets;
import java.time.Instant;
import org.junit.jupiter.api.Test;

public class KeyPolicyV1Test {
    private static final Instant START =
            Instant.parse("2026-06-01T00:00:00Z");

    private static final Instant END =
            Instant.parse("2026-07-01T00:00:00Z");

    private static final byte[] TEST_SECRET =
            "test-secret".getBytes(StandardCharsets.US_ASCII);

    private static KeyRecord record(
            KeyStatus status, Instant retirementCutoff) {
        return new KeyRecord(
                "k3",
                "principal-A",
                "tenant-A",
                "orders-api",
                "HmacSHA256",
                status,
                START,
                END,
                retirementCutoff,
                TEST_SECRET);
    }

    @Test
    void startIsInclusiveAndEndIsExclusive() {
        KeyRecord active = record(KeyStatus.ACTIVE, null);

        assertFalse(KeyPolicyV1.canVerify(active,
                "orders-api", START.minusNanos(1)));
        assertTrue(KeyPolicyV1.canVerify(active,
                "orders-api", START));
        assertTrue(KeyPolicyV1.canVerify(active,
                "orders-api", END.minusNanos(1)));
        assertFalse(KeyPolicyV1.canVerify(active,
                "orders-api", END));
    }

    @Test
    void revokedDisabledProvisionedCannotVerify() {
        Instant now = START.plusSeconds(60);

        for (KeyStatus status : new KeyStatus[] {
                KeyStatus.REVOKED,
                KeyStatus.DISABLED,
                KeyStatus.PROVISIONED }) {
            assertFalse(KeyPolicyV1.canVerify(
                    record(status, null), "orders-api", now));
        }
    }

    @Test
    void retiringNeedsExplicitCutoff() {
        Instant cutoff = START.plusSeconds(900);
        KeyRecord retiring = record(KeyStatus.RETIRING, cutoff);

        assertTrue(KeyPolicyV1.canVerify(
                retiring, "orders-api", cutoff.minusNanos(1)));
        assertFalse(KeyPolicyV1.canVerify(
                retiring, "orders-api", cutoff));

        assertFalse(KeyPolicyV1.canVerify(
                record(KeyStatus.RETIRING, null),
                "orders-api", START.plusSeconds(1)));
    }

    @Test
    void wrongAudienceIsNotAuthorizedToVerify() {
        assertFalse(KeyPolicyV1.canVerify(
                record(KeyStatus.ACTIVE, null),
                "payments-api",
                START.plusSeconds(1)));
    }

    @Test
    void wrongAlgorithmRejectsEvenWithActiveStatus() {
        KeyRecord weak = new KeyRecord(
                "k3", "principal-A", "tenant-A",
                "orders-api", "HmacSHA1",
                KeyStatus.ACTIVE, START, END, null, TEST_SECRET);

        assertFalse(KeyPolicyV1.canVerify(
                weak, "orders-api", START.plusSeconds(1)));
    }

    @Test
    void invalidTimeIntervalIsRejectedWhenLoadingRecord() {
        assertThrows(IllegalArgumentException.class,
                () -> new KeyRecord(
                        "k3", "principal-A", "tenant-A",
                        "orders-api", "HmacSHA256",
                        KeyStatus.ACTIVE, END, START,
                        null, TEST_SECRET));
    }
}
~~~

### 13.1. Những trường hợp bổ sung

Ngoài các test trên, nên kiểm:

- `verifyUntil` nằm **sau** notAfter: key vẫn phải hết hạn ở notAfter.
- Chuyển ACTIVE → REVOKED khi request đang chờ secret lookup.
- Lookup status thay đổi giữa lần test và lần admission.
- Key record bị sửa metadata trong cache nhưng secret cũ vẫn còn.
- SecretRef k3 trỏ nhầm secret-v2.
- Algorithm metadata sai version dù `keyId` đúng.
- Clock lệch giữa hai nodes và timestamp ở biên.
- K2 RETIRING được phép verify đến cutoff; sau cutoff mọi node đều reject.

### 13.2. Test boundary khác với test HMAC

Ở `KeyPolicyV1Test`, không cần tính HMAC; ta đang kiểm tra **đường policy**. Ở integration tests, vẫn cần chứng minh dù tag đúng với secret của key đã revoked, request **bị reject**. Nếu chỉ test policy helper, code controller có thể quên gọi helper.

## 14. Property-based và mutation tests

Ví dụ các thuộc tính hữu ích:

1. Với key ID V1 hợp lệ, `validateExact(id)` trả đúng **cùng chuỗi**, không normalize.
2. Với key ID có ít nhất một ký tự ngoài grammar, validator phải reject.
3. Thêm suffix/prefix vào một ID hợp lệ không được match ID gốc.
4. Đổi case một ký tự alphabetic tạo một ID khác; không được vô tình lookup bản ghi cũ.
5. Với bất kỳ 2 secrets khác nhau k2/k3 đã chọn từ test fixtures, tag tạo dưới một secret không được verifier chấp nhận dưới ID còn lại (ngoại trừ collision lý thuyết không nên dùng làm điều kiện test cho random inputs).
6. Sửa method/path/query/header/body trong signed canonical input phải đổi tag hoặc bị contract reject.
7. Tráo key ID giữ tag cũ phải fail.
8. Một key ID MISSING phải fail **ngay cả khi** tag được tạo từ một secret khác tồn tại trong registry.
9. Một key REVOKED/EXPIRED không được verify pass dù tag đúng.
10. Registry exceptions không được chuyển thành default key FOUND.

### 14.1. Mutation tests phát hiện thay đổi code nguy hiểm

Tưởng tượng một refactor xóa check:

~~~java
if (!record.keyId().equals(keyId)) {
    return KEY_NOT_ALLOWED;
}
~~~

Một fake registry bị lỗi trả **record k2 cho lookup k3**; test phải reject. Nếu các test chỉ dùng map lookup luôn đúng, nhánh bảo vệ mapping integrity sẽ không được kiểm.

Tương tự, nếu ai đó đổi:

~~~text
registry.findExact(k3)
~~~

thành:

~~~text
registry.findLatestActiveForTenant(A)
~~~

test `wrongSecret`, `unknownIdNoFallback` và rotation cross-tests phải thất bại.

### 14.2. Đừng kiểm HMAC bằng cùng logic production đang test

Unit test tính tag bằng `Mac.getInstance("HmacSHA256")` giúp tạo input cho verifier, nhưng có thể bỏ sót lỗi nếu cùng một hàm canonicalizer bị dùng sai ở cả signer và verifier tests. Cần **known-answer test vectors** cho HMAC primitive (ví dụ RFC 4231) và **independent canonical examples** được xác nhận bằng test fixtures/versioned protocol.

Không cần hardcode secrets thật hay key IDs production trong tests.

## 15. Kiểm thử integration: registry, secret manager và gateway

Unit tests với `FakeRegistry` chứng minh semantics của một implementation nhỏ, nhưng không chứng minh toàn bộ request pipeline đúng. Cần integration tests ở những ranh giới mà dữ liệu HTTP hoặc trạng thái key có thể biến đổi.

### 15.1. Luồng từ HTTP edge đến principal

~~~mermaid
sequenceDiagram
    participant C as Client
    participant G as Gateway / HTTP parser
    participant V as HMAC verifier
    participant R as Key registry
    participant S as Secret manager
    participant N as Replay store
    participant A as Application

    C->>G: Signed request + key ID
    G->>V: Validated HTTP under signing contract
    V->>R: findExact(key ID)
    R-->>V: Record / Missing / Unavailable
    V->>S: resolve exact secret reference
    S-->>V: Trusted secret or failure
    V->>V: Canonical bytes + expected HMAC + compare
    V->>N: Atomic nonce admission after valid MAC
    N-->>V: New / Replay / Unavailable
    V->>A: Trusted principal and policy context
    A->>A: Authorize action/resource/tenant
~~~

Production có thể lookup một record chứa secret bytes hoặc dùng KMS/HSM tính HMAC trực tiếp. Nhưng invariants không đổi: **key ID chọn đúng một version/secret**, status/audience/algorithm được thực thi và mọi lỗi không chắc chắn không tạo authenticated principal.

### 15.2. Topology cần test

| Topology | Kiểm thử quan trọng |
| --- | --- |
| Gateway verify + lookup | Gateway strip identity headers tự khai, chọn đúng key ID |
| Backend verify + lookup | Proxy giữ đúng signed semantics và key ID |
| Cả gateway/backend verify | Hai tầng chọn cùng ID/version; không double-claim nonce vô tình |
| Multi-node registry cache | Rotation/revocation propagation có hạn rõ |
| Multi-region registry | Các vùng không chọn secret/policy khác nhau cho cùng ID ngoài guarantee |
| Endpoint hỗ trợ Basic/Bearer/HMAC | Không fallback schemes vào HMAC endpoint ngoài policy |
| HTTP/1.1 và HTTP/2 | Duplicates và case-insensitive header names nhất quán |
| Reverse proxy path rewrite | Signing boundary và canonical request được xác định |

### 15.3. Duplicate header tại ingress

~~~http
X-Key-Id: partner-a-k2
x-key-id: partner-a-k3
~~~

Edge parser phải từ chối trước khi chọn secret. Nếu proxy đã bỏ/mix hai occurrences, Java backend không khôi phục được raw request gốc. Vì vậy test phải gửi malformed HTTP vào **ingress thật**, không chỉ `MockHttpServletRequest`.

### 15.4. Spoofed gateway identity

Nếu gateway truyền `X-Authenticated-Client` tới backend nhưng không xóa header cùng tên do Internet tự khai, backend có thể cấp identity sai.

Test bảo đảm:

1. Client-supplied identity/proxy headers được strip/reject.
2. Gateway gắn trusted principal chỉ sau key policy, HMAC và replay.
3. Kênh nội bộ được bảo vệ (ví dụ mTLS hoặc integrity-protected assertion).
4. Backend chặn direct access trái trust boundary.
5. Backend authorization không tự dùng caller `X-Role` hay `X-Tenant-Id` làm quyền.

## 16. Cache invalidation, propagation và concurrency

### 16.1. Revocation propagation across nodes

~~~text
Node A caches k2 ACTIVE and secret-v2
Node B caches k2 ACTIVE and secret-v2
Central registry revokes k2 at T
Node A receives invalidation
Node B misses invalidation and keeps ACTIVE
Attacker with stolen secret-v2 signs request through B
~~~

Kiểm thử:

- Revoke k2 ở registry.
- Gửi signed request k2/secret-v2 tới từng node.
- Đánh giá theo **revocation consistency guarantee** của hệ thống.
- Nếu yêu cầu revoke tức thời, node không chắc về state mới cần fail closed hoặc query một authority nhất quán.
- Nếu có propagation deadline, test đúng deadline và metrics cảnh báo.
- Không dừng ở “DB record REVOKED”; phải đo hành vi của **actual verifier nodes**.

### 16.2. Cache race: stale refresh đè bản ghi mới

~~~text
T1: Thread A starts loading old k2 ACTIVE record
T2: Registry changes k2 to REVOKED
T3: Thread B installs REVOKED record in cache
T4: Thread A completes late and overwrites cache with ACTIVE
~~~

Một cache không version-aware có thể **hồi sinh credential đã revoke**. Cách giảm rủi ro gồm monotonic record revision, fencing stale cache loads và invalidation protocol. Test cần dùng barriers/latches để chủ động điều phối interleaving, không chỉ đợi timing may mắn.

### 16.3. Burst cùng một key ID

Khi 100 threads cùng lookup k3 lúc cache miss:

- Nếu dùng single-flight, giới hạn số fetch đến registry.
- Mọi callers nhận đúng record version/status.
- Registry timeout không chuyển thành fake FOUND/default secret.
- Exceptions không bị cache vĩnh viễn.
- Concurrent revoke và refresh không cho stale ACTIVE override state mới.

Single-flight là tối ưu hiệu năng; **correctness và policy consistency mới là yêu cầu bảo mật**.

### 16.4. Negative cache và key mới provision

~~~text
T1: lookup k4 -> MISSING; cache negative
T2: registry creates and activates k4
T3: client signs valid request with k4
T4: stale negative cache still rejects until invalidation/TTL
~~~

Thường đây là availability/rollout bug; cần test provisioning SLA, negative TTL và invalidation. Không tái sử dụng cùng key ID cho một secret khác chỉ để “cứu” negative cache.

### 16.5. Secret manager outage

Record k3 FOUND nhưng không thể lấy secret theo `secretRef`:

- Không coi bất kỳ tag nào là authenticated.
- Không dùng secret cũ ngoài policy hoặc secret của k2.
- Không xuất secretRef/internal path trong public response.
- Ghi metric `AUTH_SECRET_UNAVAILABLE` đã redacted.
- Retry bounded/circuit-breaker theo policy; không tạo unbounded lookup storm.
- Với endpoint nhạy cảm, fail closed và không claim nonce.

### 16.6. Clock skew và key validity

Mỗi verifier dùng UTC clock cho `notBefore/notAfter` và timestamp freshness. Node nhanh và node chậm có thể có quyết định khác nhau gần cutoff. Giám sát clock offset, đặt acceptance policy rõ và test ngay trước/đúng/sau key validity boundaries; không dùng `LocalDateTime` hoặc timezone mặc định để diễn giải Instant.

## 17. Ma trận kiểm thử key lookup

| Nhóm | Tình huống | Kết quả mong đợi |
| --- | --- | --- |
| Parser | Key ID đúng grammar | Exact lookup |
| Parser | Null/empty/65 chars | Reject trước lookup |
| Parser | CR/LF/Unicode/whitespace | Reject ở HTTP edge/validator |
| Parser | Case variant của ID | ID khác, không lowercase |
| HTTP | Duplicate `X-Key-Id` khác case | Reject trước lookup |
| HTTP | Hai Authorization credentials | Reject ambiguity |
| HTTP | Proxy merge/drop key field | Edge xử lý theo signing contract, không tự chọn |
| Registry | Exact ID FOUND | Đúng một record |
| Registry | Unknown key | Reject, không fallback |
| Registry | ID có prefix trùng | Không match record khác |
| Registry | Registry trả record khác ID | Reject mapping integrity |
| Registry | Duplicate IDs trong store | Unique constraint/storage invariant |
| Registry | Timeout/partition | UNAVAILABLE, fail closed |
| Secret | Secret manager unavailable | Không accept |
| Secret | k3 secretRef trỏ nhầm secret-v2 | Test phát hiện wrong pairing |
| Secret | ID k3, HMAC tạo bởi secret-v2 | Reject MAC mismatch |
| Secret | ID k2, HMAC tạo bởi secret-v3 | Reject MAC mismatch |
| Secret | Unknown k9, tag từ secret-v2 | Reject unknown, không fallback |
| Algorithm | Key HmacSHA1 trong V1 chỉ nhận SHA256 | Reject |
| Algorithm | Client khai `algorithm=none` | Không override server policy |
| Audience | Key orders tới payments API | Reject |
| Status | PROVISIONED | Reject |
| Status | DISABLED | Reject |
| Status | REVOKED | Reject dù tag đúng |
| Status | ACTIVE trong window | Có thể verify |
| Status | RETIRING trong overlap | Verify nếu policy cho |
| Status | RETIRING sau cutoff | Reject |
| Time | Before notBefore một tick | Reject |
| Time | Exactly notBefore | Chấp nhận biên policy |
| Time | Just before notAfter | Chấp nhận biên policy |
| Time | Exactly notAfter | Reject |
| Time | Clock skew giữa nodes | Đáp ứng policy và offset limit |
| Rotation | k2/k3 overlap | Không dùng secret chéo |
| Rotation | k2 vừa revoke | Không accept ngoài propagation guarantee |
| Cache | Negative k4 rồi provision | Invalidation/TTL theo SLA |
| Cache | Stale ACTIVE sau revoke | Không accept trái policy |
| Cache | Slow refresh đè record mới | Phát hiện/fence stale version |
| Cache | 100 requests cùng key khi miss | Correctness và bounded load |
| Canonical | Tráo key ID giữ tag | Reject |
| Canonical | Signed path/body/header đổi | MAC mismatch hoặc contract reject |
| Replay | MAC sai, nonce mới | Không ghi nonce |
| Replay | MAC đúng, nonce trùng | Replay reject |
| Replay | Shared replay store unavailable | Fail closed |
| Authorization | Tenant A key gọi resource tenant B | Authorization reject |
| Logging | Secret manager/registry error | Không log secret/expected tag |
| Errors | Unknown vs revoked key | Không tiết lộ details ngoài policy |
| Timing | MISSING vs FOUND latency | Đánh giá key-existence oracle có kiểm soát |
| Gateway | HTTP/1.1↔HTTP/2 | Same key ID/signed semantics |
| Gateway | Forged identity header | Không tạo principal từ spoof |
| Distributed | Failover/replication | Đúng consistency/failure semantics đã công bố |

### 17.1. Cross-secret tests quan trọng hơn “2 happy paths”

Hai bài test “k2 ký đúng → pass” và “k3 ký đúng → pass” **không bắt lỗi fallback secret**. Cần explicit cross tests:

~~~text
id=k2, signature created with secret-v3 -> REJECT
id=k3, signature created with secret-v2 -> REJECT
id=k9, signature created with secret-v2 -> REJECT
~~~

Một implementation sai thử mọi ACTIVE secret có thể vượt happy paths, nhưng phải thất bại với negative tests này.

### 17.2. Integration tests phải đi qua actual policy

`KeyPolicyV1.canVerify` có thể đúng nhưng HTTP middleware quên gọi hàm. Vì vậy ký request bằng secret của một key REVOKED, gửi qua endpoint thật và assert business handler **không chạy**; tương tự key expired hoặc wrong audience.

### 17.3. Test từ gateway thay vì chỉ mock container

Nếu ingress đã loại một `X-Key-Id` trong hai occurrences, mock ở Java không biết request từng duplicate. Raw HTTP integration test cần kiểm tra edge reject ambiguity trước khi thành phần tiếp theo mất evidence.

## 18. Tình huống thực tế: request được nhận bằng khóa đã thu hồi

Một hệ thống có 3 pods A/B/C, mỗi pod cache key record 10 phút:

~~~text
T0: k2 ACTIVE, secret-v2
T1: credential k2 bị lộ, Security team revoke k2 tại registry
T2: pod A nhận invalidation; pod B và C vẫn cache ACTIVE
T3: attacker gửi HMAC đúng dưới k2 tới pod B
T4: pod B chấp nhận vì dùng stale ACTIVE record
~~~

HMAC primitive ở pod B có thể hoàn toàn đúng. Lỗi là **key lookup policy consistency**.

### 18.1. Điều tra

1. Kiểm tra current registry record, version, status và revoke timestamp.
2. Kiểm tra cache TTL/invalidation và revision tại mỗi verifier node.
3. Kiểm tra key ID trên signed request có đúng k2 hay đã fallback sang ID khác.
4. Kiểm tra secret reference có bị alias/reused không.
5. Kiểm tra những requests nào được nhận trong propagation window.
6. Kiểm tra principal, audience, scope và authorization outcome.
7. Đánh giá sự cố theo **revocation guarantee đã công bố**, không chỉ theo trạng thái hiện tại của DB.

### 18.2. Cách khắc phục

- Tách unique key IDs theo mỗi lần rotation; không thay secret dưới cùng một ID.
- Dùng monotonic record version và cache invalidation có thể quan sát.
- Với emergency revoke, ưu tiên consistency mạnh hơn hoặc fail closed nếu không xác nhận được policy mới.
- Giới hạn thời gian chấp nhận record stale theo threat model; đo/alert khi vượt.
- Test cùng signed request k2 trên **mọi verifier node** khi revoke.
- Áp dụng timestamp/nonce replay protection và business authorization, nhưng **không coi chúng thay revocation**.

## 19. Sai lầm triển khai thường gặp

### 19.1. Case-fold key ID

`Partner-A-k3` và `partner-a-k3` là hai identifiers khác nhau theo V1. Auto lowercase tạo alias không được signer/registry contract đồng ý.

### 19.2. Trim hoặc decode trước lookup

`" partner-a-k3 "`, `partner%2Da-k3` hoặc Unicode confusable phải reject, không normalize thành ID hợp lệ ở một tầng còn tầng khác giữ nguyên.

### 19.3. Dùng prefix query

`LIKE "partner-a%"` có thể chọn nhầm record, đặc biệt khi k1/k2/k3 đồng tồn tại.

### 19.4. Fallback default secret

Unknown ID phải reject. Một shared fallback secret có thể làm request mạo ID được chấp nhận.

### 19.5. Thử tất cả secret của principal

“MAC khớp với một secret bất kỳ” không chứng minh **key ID được yêu cầu** hợp lệ và chưa revoked. Key rotation phải chọn secret theo exact ID.

### 19.6. Xem RETIRING là ACTIVE vô thời hạn

RETIRING chỉ được verify trong overlap rõ. Sau verifyUntil, tag đúng vẫn phải reject.

### 19.7. Tin client khai algorithm

`X-Algorithm: none` không được tắt HMAC. Key version và algorithm phải do server contract/key record quyết định.

### 19.8. Gộp MISSING và UNAVAILABLE vào default FOUND

Timeout hoặc partition là lỗi độ tin cậy, không phải lý do cấp principal tạm.

### 19.9. Cache ACTIVE quá lâu sau revoke

Một node với stale ACTIVE có thể nhận stolen secret. Cần clock consistency, invalidation/TTL và test propagation.

### 19.10. Cấp principal trước HMAC

Biết key ID hoặc tìm thấy key record không đồng nghĩa đã chứng minh caller sở hữu secret.

### 19.11. Ghi nonce trước MAC

Attacker có thể poison replay store bằng key ID/nonce tự khai. Claim nonce sau MAC hợp lệ và freshness.

### 19.12. Coi HMAC đúng là đủ quyền

Principal A ký request tới tenant B vẫn phải bị authorization từ chối.

### 19.13. Log secret để chẩn đoán lookup

Không xuất raw HMAC secret, signed request còn hạn, expected tag hoặc full credentials vào log.

## 20. Bài tập thực hành

### Bài tập 1 — Strict ID parser

Viết tests cho `KeyIdV1.validateExact`: ID hợp lệ, null, empty, 64/65 chars, Unicode, CRLF, leading/trailing whitespace, dot, slash, percent-encoding và case variants.

### Bài tập 2 — Không có fallback

Tạo FakeRegistry chỉ có k2. Gửi request khai k9 nhưng ký bằng secret-v2. Kiểm tra outcome vẫn là UNKNOWN_KEY, không thử k2.

### Bài tập 3 — Cross-secret rotation

Thêm k2 RETIRING và k3 ACTIVE trong overlap. Tạo 4 tổ hợp ID/secret. Chỉ cho hai cặp đúng qua, sau cutoff k2 phải reject.

### Bài tập 4 — Lifecycle boundaries

Dùng `Clock.fixed` để kiểm notBefore inclusive, notAfter exclusive và RETIRING verifyUntil exclusive; thử key status REVOKED với signature cryptographically correct.

### Bài tập 5 — Cache invalidation

Mô phỏng stale ACTIVE ở node B sau revoke. Viết test chứng minh behavior đúng theo SLA (hoặc chọn strong-consistency/fail-closed guarantee).

### Bài tập 6 — Lookup errors

Fake registry ném `KeyLookupUnavailableException`. Kiểm tra helper trả LOOKUP_UNAVAILABLE và caller không tạo principal/claim nonce.

### Bài tập 7 — Gateway duplicate headers

Gửi hai `X-Key-Id` khác case qua ingress. Kiểm tra request bị từ chối trước khi verifier lựa chọn key; test cả HTTP/1.1 và HTTP/2 nếu deployment hỗ trợ.

### Bài tập 8 — Key ID signed binding

Ký một request với k3. Đổi key ID thành k2 nhưng giữ signature, kiểm tra HMAC mismatch. Xác nhận key ID hiện diện trong canonical bytes thực nhận.

### Bài tập 9 — Authn vs authz

Principal tenant A dùng secret đúng để ký request cập nhật order tenant B. Xác minh MAC/nonce đúng, nhưng authorization phải từ chối.

### Bài tập 10 — Observability và incident review

Thiết kế metric/structured log để phân biệt INVALID_ID, MISSING, REVOKED, UNAVAILABLE, MAC_MISMATCH và policy deny mà không log shared secret, expected tag hoặc nguyên signed request.

## 21. Checklist Kiểm thử key lookup

- [ ] Key ID được parse strict trước khi lookup; không normalize/trim/percent-decode ngoài contract.
- [ ] Một request có đúng một key ID/Authorization selector; duplicate HTTP fields bị reject tại ingress.
- [ ] Registry có exact unique key ID; không prefix/case-insensitive alias ngoài protocol.
- [ ] Không có default secret hoặc fallback thử nhiều secrets.
- [ ] Mỗi key ID ánh xạ đúng một version, secretRef, algorithm, principal và audience.
- [ ] Secret đến từ trusted store và không được ghi logs/source.
- [ ] Key status ACTIVE/RETIRING/REVOKED/DISABLED/PROVISIONED được kiểm.
- [ ] notBefore/notAfter/verifyUntil có inclusive/exclusive boundaries rõ, test bằng UTC Clock.
- [ ] RETIRING chỉ verify trong overlap, revoke có hiệu lực theo consistency guarantee.
- [ ] Error MISSING và UNAVAILABLE được phân biệt nội bộ, fail closed.
- [ ] Cache và negative-cache TTL/invalidation/record versions được test.
- [ ] Multi-node/region propagation, clock skew và failover có tests.
- [ ] Algorithm/audience được áp từ server-side policy, không từ unsigned client hint.
- [ ] Key ID, timestamp, nonce và các mandatory signed fields được HMAC bảo vệ.
- [ ] Verifier dùng canonical bytes từ request thực nhận, không từ caller-supplied string.
- [ ] Full HMAC tag được so bằng primitive phù hợp như `MessageDigest.isEqual`.
- [ ] MAC sai không tạo principal hoặc claim nonce.
- [ ] Freshness và shared atomic nonce replay store hoạt động độc lập với key lookup.
- [ ] Authentication principal đến từ record đáng tin, authorization kiểm action/resource/tenant riêng.
- [ ] Gateway/backend thống nhất signing boundary; không tin client-supplied identity headers.
- [ ] Negative tests bao gồm cross-key secret, unknown key signed with existing secret và revoked-key valid MAC.
- [ ] External errors hạn chế key enumeration/secret leakage; logs/metrics redacted.
- [ ] Test coverage có unit, fake/integration, concurrency, failure injection và end-to-end gateway.

## 22. Câu hỏi tự kiểm tra

1. **Key ID có phải mật khẩu không?** Không; nó là selector do caller khai.
2. **Lookup FOUND có đủ để tạo principal không?** Không; phải verify MAC và anti-replay.
3. **Vì sao exact match quan trọng?** Ngăn chọn nhầm credential, secret và status.
4. **Key ID case-insensitive vì HTTP header name case-insensitive?** Không; tên field và giá trị key ID có contract khác.
5. **Unknown key có được thử secret khác không?** Không; phải reject exact lookup.
6. **MISSING khác UNAVAILABLE thế nào?** MISSING là không có record đáng tin; UNAVAILABLE không thể xác minh trạng thái lookup.
7. **Tại sao tag đúng với k2 không được chấp nhận dưới ID k3?** K3 phải dùng secret/policy của k3, không fallback.
8. **Key REVOKED nhưng tag tính đúng có được accept không?** Không; lifecycle policy chặn.
9. **Biên notAfter được test thế nào?** notAfter là exclusive trong contract minh họa.
10. **RETIRING có thể verify mãi không?** Không; cần cutoff/overlap.
11. **Vì sao cache ACTIVE sau revoke nguy hiểm?** Node stale có thể nhận stolen secret ngoài policy.
12. **Negative cache có thể gây gì khi provision key mới?** Reject tạm thời key hợp lệ do cached MISSING.
13. **Tại sao phải ký key ID trong canonical bytes?** Để không tráo credential selector mà giữ tag cũ.
14. **Ai quyết định algorithm?** Server protocol/key record, không phải client tự khai.
15. **Lookup UNAVAILABLE có được fail open không?** Không với API cần xác thực nghiêm ngặt.
16. **Nonce ghi trước MAC có rủi ro gì?** Attacker có thể poison replay store.
17. **Key ID đã xác minh có nghĩa principal có quyền trên tenant khác không?** Không; authorization riêng.
18. **Một test với two valid keys có phát hiện fallback không?** Chưa; cần cross-secret và unknown-key negative tests.
19. **Tại sao test raw HTTP ingress quan trọng?** Proxy có thể merge/drop duplicate headers trước Java.
20. **Có thể suy toàn bộ verifier constant-time từ MessageDigest.isEqual không?** Không; lookup, cache, parser và response timing cũng quan trọng.

## 23. Tài liệu tham khảo và hướng đọc tiếp

- **RFC 2104 — HMAC: Keyed-Hashing for Message Authentication.** Cơ chế HMAC với shared secret.
- **RFC 4231 — HMAC-SHA-224/256/384/512 Test Vectors.** Kiểm tra HMAC primitive độc lập với registry.
- **RFC 9110 — HTTP Semantics.** Authentication fields, header semantics và request targets.
- **RFC 9112 / RFC 9113 — HTTP/1.1 / HTTP/2.** Framing, duplicate/case header handling, gateway boundary.
- **RFC 3986 — Uniform Resource Identifier Generic Syntax.** Canonical URI/path/query.
- **Java SE 17 — `javax.crypto.Mac`, `SecretKeySpec`, `MessageDigest.isEqual`, `Clock`, `Instant`.** Crypto/time APIs.
- **JUnit Jupiter (JUnit 5) — User Guide.** Parameterized tests, fixtures, assertions và concurrency-related integration tests.
- **OWASP — API authentication, credential lifecycle và security logging guidance.** Bối cảnh bảo vệ identity, secrets và error oracles.

**Kết luận:** **Kiểm thử key lookup phải chứng minh selector do client khai luôn dẫn tới đúng một key record đáng tin, đúng policy và đúng shared secret—không fallback, không tự normalize ID và không cấp quyền trước HMAC.** Bộ test tốt không dừng ở hai “happy path”; phải có wrong-secret pairing, unknown-ID signed by existing secret, revoked-key valid MAC, cache stale/rotation races, registry outage và parser/gateway ambiguity. Khi kết hợp với canonical request, timestamp/nonce, key rotation, trusted principal và authorization riêng, key lookup mới trở thành một mắt xích đáng tin trong xác thực HTTP request bằng HMAC.
