# Kiểm thử migration trong xác thực HTTP request bằng HMAC

## 1. Vì sao migration HMAC phải được kiểm thử như một thay đổi bảo mật?

Module **SECURITY_AUTHENTICATION_HMAC_REQUEST_AUTHENTICATION** thiết kế xác thực HTTP request bằng **HMAC với shared secret** trên một **canonical request** theo hợp đồng ký. Dữ liệu được ký có thể bao gồm method, URI, header và/hoặc body digest. Ngoài việc xác minh chữ ký, hệ thống còn phải kiểm tra timestamp/nonce để chống replay, quản lý key rotation, hoạt động đúng qua proxy/gateway và **phân biệt authentication với authorization**.

Trong chương **Migration**, bài **Kiểm thử migration** hướng dẫn chứng minh rằng một hệ thống đang nâng cấp cơ chế xác thực **tiếp tục tương thích đúng mức, loại bỏ cơ chế cũ đúng thời điểm và không mở đường bypass**.

Hai trường hợp thường gặp:

1. **Migration cơ chế xác thực:** từ API key tĩnh hoặc một scheme legacy sang HMAC per-request. Trong giai đoạn chuyển tiếp, có thể có cả client cũ và client mới.
2. **Migration hợp đồng chữ ký:** từ HMAC profile V1 sang V2, có thể đổi thuật toán, canonicalization, key ID, shared secret hoặc cách đóng gói signature.

Cả hai đều có nguy cơ: nếu backend cứ chấp nhận phương án cũ như fallback vô hạn, client chưa migrate vẫn hoạt động nhưng **chính sách mới không thực sự có hiệu lực**. Nếu bỏ phương án cũ quá sớm, client hợp lệ bị 401. Nếu đổi canonical path/query qua gateway, signature sai dù secret đúng. Nếu chia nonce theo profile không phù hợp, cùng nghiệp vụ có thể bị xử lý hai lần.

**Mục tiêu học tập:**

- Xác định **invariant** bảo mật và phạm vi tương thích cho từng giai đoạn.
- Thiết kế **acceptance matrix** theo trạng thái client, scheme, signature profile, key lifecycle và route.
- Viết golden-vector test, contract test client–server, HTTP/security integration test, negative test chống downgrade và test đa replica.
- Cô lập false positive do timestamp, nonce, key, proxy và authorization khi test một thay đổi cụ thể.
- Thiết kế kiểm tra canary/rollback, fault injection, observability và tiêu chí **go/no-go** dựa trên chứng cứ.

> Một test migration “request hợp lệ trả 200” chưa đủ. Bằng chứng quan trọng nhất là **mỗi request chỉ được chấp nhận bởi đúng policy đang có hiệu lực**, còn những đường cũ đã bị loại bỏ không thể vô tình cấp quyền hoặc gây side effect.

## 2. Những gì thay đổi và những gì bắt buộc giữ nguyên

| Thành phần | Có thể thay đổi khi migration | Điều phải giữ bất biến |
|---|---|---|
| Authentication scheme | API key legacy → HMAC | Không có request unauthenticated nào vào protected handler |
| Signature profile | V1 → V2, thuật toán/encoding khác | Chỉ profile được server cho phép mới xác thực thành công |
| Canonical request | Bổ sung signed method/path/query/header/body | Verifier bảo vệ **đúng operation và bytes** mà handler thực thi |
| Key ID/secret | Phát key mới, rotate/revoke key cũ | Không chấp nhận key revoked/expired, không lấy nhầm tenant |
| Timestamp | Format/window theo contract mới | Không bỏ freshness hoặc tin timestamp client trước verify |
| Nonce store | Chuyển Redis namespace/backend/TTL | Atomic claim; không replay/double side effect |
| Gateway | Rewrite path, HTTP version, WAF | Public signed target và effective route nhất quán |
| Spring Security chain | Filter/manager/route matcher mới | Mọi protected route được bảo vệ, fail closed |
| Authorization | Mapping authority/tenant có thể cập nhật | Xác thực thành công **không tự cấp quyền** |
| Observability | Metric names/dashboards mới | Không lộ secret, nonce, full MAC hay dữ liệu nhạy cảm |

**Migration thành công** là khi thay đổi được chấp nhận về chức năng nhưng vẫn chứng minh được các invariant: **signature đúng request**, **replay bị chặn**, **revoke có hiệu lực**, **quyền được kiểm tra**, **lỗi phụ thuộc không biến thành bypass**.

### 2.1. Không đánh đồng key rotation và migration signature

**Key rotation** có thể thay secret S1 → S2 mà vẫn dùng `HmacSHA256`/canonical V1. **Signature migration** đổi profile V1 → V2, có thể dùng thuật toán khác hoặc quy tắc ký khác. Khi làm đồng thời hai thay đổi, test cần tách từng biến để biết lỗi nằm ở key lookup, profile policy hay canonical bytes.

Đề xuất kiểm thử theo lớp: **crypto vectors → policy matrix → HTTP integration → gateway → distributed state → rollout/rollback**.

## 3. Ví dụ xuyên suốt: từ API key legacy sang HMAC V2

Giả sử hệ thống cũ cho phép:

~~~http
POST /public/v1/payments HTTP/1.1
X-Api-Key: <legacy-api-key>
Content-Type: application/json

{"amount":125000,"currency":"VND"}
~~~

Hệ thống mới yêu cầu HMAC, ví dụ:

~~~http
POST /public/v2/payments?account=A123&mode=preview HTTP/1.1
X-Key-Id: partner-a-hmac-v2
X-Hmac-Version: v2
X-Timestamp: 2026-11-28T10:00:00Z
X-Nonce: migration-probe-001
X-Signature: <base64-mac>
Content-Type: application/json

{"amount":125000,"currency":"VND"}
~~~

Ở ví dụ, V1/V2 được tách cả public path và key ID cho dễ nhận diện. **Không suy ra** mọi API cần đổi đường dẫn khi nâng cấp HMAC; các hệ thống cũng có thể giữ nguyên path và chỉ phiên bản hóa header/canonical contract. Việc gắn path version với signature version là lựa chọn của hợp đồng minh họa.

Một vòng migration có thể đi qua các trạng thái server sở hữu:

~~~mermaid
flowchart LR
    A[LEGACY_ONLY] --> B[DUAL]
    B --> C[HMAC_V1_REQUIRED]
    C --> D[HMAC_V2_REQUIRED]
    D --> E[RETIRED / SUSPENDED]
    D -. Không tự động downgrade .-> C
    C -. Không tự động fallback .-> B
~~~

**State thuộc server policy**, không suy từ `X-Hmac-Version` hay `X-Migration-State` do client tự khai. Một deployment có thể hỗ trợ đồng thời nhiều profile, nhưng chính sách **trên từng client và key** mới quyết định request nào được phép.

### 3.1. Acceptance matrix đề xuất

| Client state | API key legacy | HMAC V1 | HMAC V2 | Ghi chú |
|---|---:|---:|---:|---|
| `LEGACY_ONLY` | Cho phép tạm thời | Từ chối hoặc chưa enable | Từ chối hoặc chưa enable | Chưa kích hoạt HMAC cho client |
| `DUAL` | Cho phép có thời hạn | Cho phép | Cho phép nếu đã cấp key V2 | Quan sát migration; không dùng legacy vô hạn |
| `HMAC_V1_REQUIRED` | **Từ chối** | Cho phép | Cho phép khi policy bật | Không fallback legacy |
| `HMAC_V2_REQUIRED` | **Từ chối** | **Từ chối** | Cho phép | Ratchet: V2 là yêu cầu tối thiểu |
| `SUSPENDED` | Từ chối | Từ chối | Từ chối | Không cấp Authentication |

Các ô “cho phép” đều còn phụ thuộc **route, key trạng thái active, timestamp/nonce, MAC và authorization**. Đừng lấy một hàng trong bảng làm quyết định chấp nhận request trước khi kiểm tra từng điều kiện.

Một bảng như vậy phải được lưu trong test fixture từ **chính đặc tả policy**; không tạo expected acceptance bằng cách gọi lại cùng hàm policy đang test rồi so với chính nó.

## 4. Threat model: những đường bypass trong migration

### 4.1. Downgrade và fallback im lặng

Một ví dụ sai:

~~~java
// KHÔNG dùng làm migration strategy:
if (!verifyHmacV2(request)) {
    if (verifyHmacV1(request) || legacyApiKeyValid(request)) {
        return authenticated;
    }
}
~~~

Nếu client đã là `HMAC_V2_REQUIRED`, chữ ký V2 sai phải dẫn tới **từ chối**, không mở đường quay về V1/legacy. Nếu client vẫn `DUAL`, phải chọn **một scheme xác định rõ theo contract** và áp dụng policy tương ứng; không liên tục thử các credential khác để “cứu” request.

### 4.2. Ambiguous credentials

Request vừa mang `X-Api-Key`, vừa mang `X-Signature` có thể dẫn đến hai parser/filter cho ra hai principal khác nhau. Có thể chọn policy **từ chối request trộn scheme** (đơn giản, dễ kiểm chứng), hoặc định nghĩa rule ưu tiên rõ ràng nếu thật sự cần dual-signature. Test phải bảo đảm:

- Một credential **sai** không làm hệ thống rẽ sang scheme cũ một cách vô tình.
- Không tạo hai `Authentication` hoặc gọi handler hai lần.
- Không cho client tự chọn principal/tenant dựa trên header chưa được xác minh.
- Nếu nhiều header cùng tên hoặc version khác nhau xuất hiện, request bị từ chối theo hợp đồng.

### 4.3. Sai trust boundary qua gateway

Client ký `/public/v2/payments` nhưng gateway chuyển thành `/payments`; verifier và handler có thể khác nhau về public target/route. Không sửa 401 bằng cách **bỏ URI/query khỏi canonical**. Chỉ tin original-target metadata do ingress đáng tin phát hành, đã strip header giả từ client, và đối chiếu mapping với effective handler.

### 4.4. Replay hoặc xử lý nghiệp vụ trùng

HMAC V1 và V2 có thể dùng cùng principal nhưng khác key/profile. Nếu nonce store tách `v1:nonce` và `v2:nonce`, **cùng nonce** có thể được claim hai lần nếu policy vốn cần chặn reuse xuyên profile. Tuy nhiên ngay cả một nonce namespace dùng chung cũng không chặn retry **bằng nonce khác**; API ghi dữ liệu còn cần **idempotency key** riêng.

Với legacy API key không có nonce, việc gửi cùng operation một lần qua legacy, một lần qua HMAC có thể đi qua hai cơ chế chống replay khác nhau. Test migration phải kiểm tra **idempotency ở tầng nghiệp vụ**, không kỳ vọng nonce HMAC tự bảo vệ mọi scheme.

### 4.5. Fail-open khi phụ thuộc gặp lỗi

Khi key store, nonce store, policy store hoặc secret manager lỗi, không được chuyển sang “legacy vì HMAC đang lỗi” nếu client/route không còn cho phép legacy. Xử lý đúng là **fail closed** và lỗi availability phù hợp, thường 503.

## 5. Phân tầng test để biết chính xác điều gì được chứng minh

| Tầng kiểm thử | Mục đích | Giới hạn |
|---|---|---|
| **Golden vectors** | Đồng nhất bytes canonical, digest và MAC | Không chứng minh HTTP adapter/filter |
| **Unit policy tests** | Đúng bảng trạng thái client/scheme/key/profile | Có thể bỏ sót bean/filter wiring |
| **Contract tests SDK ↔ server** | SDK cũ/mới cùng hiểu format, status, wire encoding | Mock proxy có thể che rewrite thật |
| **Spring Security integration** | HMAC filter, SecurityContext, entry point, 401/403 | Chưa chắc giống actual network server |
| **Real HTTP integration** | Header duplicate, request target, body stream | Một node không chứng minh distributed replay |
| **Gateway/proxy E2E** | Public URI, query, forwarded metadata, HTTP/2 | Cần cấu hình gần production |
| **Multi-replica + backing stores** | Nonce atomic, key/policy propagation, cache | Tốn hạ tầng; tránh chạy phá hoại ở production |
| **Canary / production synthetic** | Build/config thực và quan sát adoption | Chỉ dùng credential/route test, không chaos tùy tiện |

Phải ghi rõ một test đã chạy **qua tầng nào**. Ví dụ test JUnit tự gọi `Mac.doFinal` không xác nhận rằng route mới yêu cầu HMAC; một test trả 401 không bảo đảm request bị từ chối vì đúng lý do.

## 6. Thiết kế fixture quyết định được kết quả

Một server fixture tái lập nên có:

- **`Clock.fixed`** tại thời điểm test, kiểm soát freshness để test không hết hạn theo thời gian thực.
- **Key records synthetic**: V1 active, V2 active, revoked/expired, unknown; mỗi profile có secret riêng.
- **Policy repository**: trạng thái migration của client, phiên bản policy và khả năng thay đổi có kiểm soát.
- **Nonce store**: fake atomic trong unit tests, Redis thật hoặc backend tương đương ở integration đa replica.
- **Client signer độc lập**: không dùng chung buggy canonicalizer với server nếu mục tiêu là contract test.
- **Hai route được bảo vệ** và một route cần quyền khác, phục vụ các phép thử signed path và 403.
- **Business spy/idempotency repository**: chứng minh handler không tạo side effect với request bị từ chối.
- **Gateway fixture**: public path → internal path mapping và strip/overwrite internal headers.
- **Audit/metric sink**: xác nhận reason/stage, không ghi secret và không lấy raw header làm tag.

### 6.1. Khóa, authority và tenant của fixture

| Key ID | Profile | Client | Quyền ví dụ | Trạng thái |
|---|---|---|---|---|
| `partner-a-hmac-v1` | V1 | partner-a | `payments:write` | Active trong overlap |
| `partner-a-hmac-v2` | V2 | partner-a | `payments:write` | Active |
| `partner-b-readonly` | V2 | partner-b | `payments:read` | Active |
| `partner-a-revoked` | V1 | partner-a | Không cấp quyền | Revoked |
| `missing-key` | Không có | Không có | Không có | Not found |

Principal, tenant và authorities phải đến từ **bản ghi key đã được xác thực phía server**. `X-Key-Id` là một lookup hint chưa đáng tin; header `X-Tenant-Id` hoặc `X-Role` tự khai không cấp được quyền.

Nếu test chạy song song, không reset một store dùng chung giữa các case khi có request in-flight; dùng namespace, instance hoặc context độc lập. Không dùng credential thật của đối tác trong test.

## 7. Golden vector cố định cho HMAC V1 và V2

Để kiểm tra migration profile, ví dụ định nghĩa hai canonical domains khác nhau nhưng đều dùng HMAC-SHA256:

~~~text
<HMAC-V1-HS256 hoặc HMAC-V2-HS256>
<METHOD_UPPERCASE>
<PUBLIC_RAW_PATH>
<PUBLIC_RAW_QUERY_OR_EMPTY>
<KEY_ID>
<UTC_TIMESTAMP>
<NONCE>
<LOWERCASE_HEX_SHA256_OF_EXACT_BODY_BYTES>
~~~

Các dòng nối bằng **LF (0x0A)**, không thêm LF cuối, rồi mã hóa UTF-8 trước khi tính MAC. Trong hệ thống thật V2 có thể dùng HMAC-SHA512, signed headers hoặc quy tắc canonical khác; phải version hóa profile và thay vector tương ứng. **Không có chuẩn canonical HMAC HTTP tự động đúng cho mọi API.**

Đây là các vector **synthetic** có expected MAC cố định được tính từ dữ liệu đã nêu, để không so sánh signer với chính nó:

~~~yaml
common:
  method: POST
  raw_query: account=A123&mode=preview
  timestamp: "2026-11-28T10:00:00Z"
  nonce: migration-probe-001
  body_utf8_no_trailing_newline: '{"amount":125000,"currency":"VND"}'
  body_sha256_lowerhex: ed6cd11906e5c888e772cfd89895fcf7d069d3cd6f47711466b021ad263f76b1

v1:
  domain: HMAC-V1-HS256
  path: /public/v1/payments
  key_id: partner-a-hmac-v1
  secret_utf8: synthetic-secret-only-for-v1-migration
  algorithm_jca: HmacSHA256
  canonical_utf8_bytes: 188
  signature_base64: "BjEfsghmXyzYdx1Cc2ykN1WctIjn8TpahIEIlDQy5CQ="

v2:
  domain: HMAC-V2-HS256
  path: /public/v2/payments
  key_id: partner-a-hmac-v2
  secret_utf8: synthetic-secret-only-for-v2-migration
  algorithm_jca: HmacSHA256
  canonical_utf8_bytes: 188
  signature_base64: "KFi5joO98s+5USurjU39x/sfx3/oToNR+8LJw7ZJl9s="
~~~

**Vì sao cả hai cùng HMAC-SHA256?** Bài tập này cô lập **signature profile/canonical/key migration** khỏi thay đổi thuật toán. Nếu migration thật còn đổi `HmacSHA512`, cần thêm vector V2-SHA512 có độ dài MAC 64 byte và kiểm tra policy chọn đúng JCA algorithm. Không suy rằng V2 chỉ là “SHA-256 nhưng đổi tên”.

### 7.1. Golden vectors phải kiểm tra những sai sót nào?

| Sai sót | Bằng chứng từ vector |
|---|---|
| Dùng CRLF thay LF | Canonical bytes/MAC không khớp |
| Thêm newline ở cuối | Độ dài và MAC sai |
| Hash body JSON đã parse/serialize | Body SHA-256 sai |
| Bỏ raw query hoặc sort query ngoài contract | MAC sai |
| Ký internal path thay public path | MAC sai |
| Dùng nhầm secret V1 cho V2 | Expected signature không khớp |
| Bỏ domain prefix/version | MAC sai; có nguy cơ cross-profile confusion |
| Decode Base64 sai hoặc truncate MAC | Signature không được chấp nhận |

Giữ vector trong bộ test của SDK và server; nên xác nhận bằng **ít nhất một implementation độc lập**. Golden vector tự nó **không chứng minh** filter mới được đăng ký đúng hoặc route không bị bypass.

## 8. Java 17: test signer độc lập và JUnit 5 vector tests

Đoạn dưới mô tả **chính xác profile minh họa** ở mục 7, không phải SDK dùng chung cho mọi giao thức HMAC:

~~~java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.util.Base64;
import java.util.HexFormat;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public final class MigrationHmacVectorSigner {
    private MigrationHmacVectorSigner() {}

    public static String canonical(
            String domain, String method, String publicRawPath,
            String publicRawQuery, String keyId, String timestamp,
            String nonce, byte[] body) throws GeneralSecurityException {

        // Test fixture phải kiểm soát format/ký tự điều khiển;
        // không nhận field tùy ý có CR/LF từ người dùng.
        String digest = HexFormat.of().formatHex(
                MessageDigest.getInstance("SHA-256").digest(body));

        return String.join("\n",
                domain, method, publicRawPath,
                publicRawQuery == null ? "" : publicRawQuery,
                keyId, timestamp, nonce, digest);
    }

    public static byte[] mac(byte[] secret, String canonical)
            throws GeneralSecurityException {
        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(secret, "HmacSHA256"));
        return mac.doFinal(canonical.getBytes(StandardCharsets.UTF_8));
    }

    public static String base64(byte[] secret, String canonical)
            throws GeneralSecurityException {
        return Base64.getEncoder().encodeToString(mac(secret, canonical));
    }
}
~~~

JUnit test so với literal signature, sử dụng `Clock.fixed` tại phần tích hợp để mọi timestamp cùng trong cửa sổ:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.Test;

class MigrationGoldenVectorsTest {
    private static final byte[] BODY =
            "{\"amount\":125000,\"currency\":\"VND\"}"
                    .getBytes(StandardCharsets.UTF_8);

    private String canonical(String version, String path, String keyId)
            throws Exception {
        return MigrationHmacVectorSigner.canonical(
                "HMAC-" + version + "-HS256", "POST", path,
                "account=A123&mode=preview", keyId,
                "2026-11-28T10:00:00Z", "migration-probe-001", BODY);
    }

    @Test
    void publishedV1VectorMatchesExactBytes() throws Exception {
        String canonical = canonical(
                "V1", "/public/v1/payments", "partner-a-hmac-v1");
        byte[] secret = "synthetic-secret-only-for-v1-migration"
                .getBytes(StandardCharsets.UTF_8);
        assertEquals(188,
                canonical.getBytes(StandardCharsets.UTF_8).length);
        assertEquals(
                "BjEfsghmXyzYdx1Cc2ykN1WctIjn8TpahIEIlDQy5CQ=",
                MigrationHmacVectorSigner.base64(secret, canonical));
    }

    @Test
    void publishedV2VectorMatchesExactBytes() throws Exception {
        String canonical = canonical(
                "V2", "/public/v2/payments", "partner-a-hmac-v2");
        byte[] secret = "synthetic-secret-only-for-v2-migration"
                .getBytes(StandardCharsets.UTF_8);
        assertEquals(188,
                canonical.getBytes(StandardCharsets.UTF_8).length);
        assertEquals(
                "KFi5joO98s+5USurjU39x/sfx3/oToNR+8LJw7ZJl9s=",
                MigrationHmacVectorSigner.base64(secret, canonical));
    }

    @Test
    void profileDomainIsCryptographicallyBound() throws Exception {
        byte[] secret = "synthetic-secret-only-for-v2-migration"
                .getBytes(StandardCharsets.UTF_8);
        String original = canonical(
                "V2", "/public/v2/payments", "partner-a-hmac-v2");
        String wrongDomain = MigrationHmacVectorSigner.canonical(
                "HMAC-V1-HS256", "POST", "/public/v2/payments",
                "account=A123&mode=preview", "partner-a-hmac-v2",
                "2026-11-28T10:00:00Z", "migration-probe-001", BODY);
        assertNotEquals(
                MigrationHmacVectorSigner.base64(secret, original),
                MigrationHmacVectorSigner.base64(secret, wrongDomain));
    }
}
~~~

Đây là **crypto/vector tests**. Việc domain khác tạo MAC khác chưa chứng minh server **không fallback sang profile cũ**. Policy và filter chain phải được test qua integration tiếp theo.

### 8.1. Không cho phép thuật toán do client tùy ý chỉ định

Trên server, thay vì `Mac.getInstance(rawAlgorithmHeader)`, nên map profile đã parse từ allowlist (V1/V2) tới thuật toán và yêu cầu key record cho phép **đúng profile đó**. Một request có header `X-Hmac-Version: none`, hai header version hoặc key V2 dùng profile V1 phải bị từ chối. Không thử tuần tự mọi secret/profile cho tới khi MAC khớp.

Với MAC thực tế, sau khi strict Base64 decode, kiểm tra đúng độ dài expected (32 byte đối với HmacSHA256 không truncate), rồi so sánh bytes bằng `MessageDigest.isEqual` hoặc primitive tương đương; không so sánh string Base64 tùy tiện. Header malformed, oversized và duplicate phải được chặn trước lookup/crypto.

## 9. Unit tests cho migration policy (không chỉ crypto)

Một decision model test có thể mô tả:

~~~java
enum MigrationState {
    LEGACY_ONLY,
    DUAL,
    HMAC_V1_REQUIRED,
    HMAC_V2_REQUIRED,
    SUSPENDED
}

enum CredentialScheme {
    LEGACY_API_KEY, HMAC_V1, HMAC_V2
}

final class MigrationPolicy {
    static boolean permits(
            MigrationState state, CredentialScheme scheme) {
        return switch (state) {
            case LEGACY_ONLY ->
                    scheme == CredentialScheme.LEGACY_API_KEY;
            case DUAL -> true; // Chỉ trong overlap được phê duyệt.
            case HMAC_V1_REQUIRED ->
                    scheme == CredentialScheme.HMAC_V1
                            || scheme == CredentialScheme.HMAC_V2;
            case HMAC_V2_REQUIRED ->
                    scheme == CredentialScheme.HMAC_V2;
            case SUSPENDED -> false;
        };
    }
}
~~~

Đây là **mô hình chính sách tối giản để dạy kiểm thử**. Trong production, quyết định còn cần route, client identity, key active/revoked, timestamp, signature, scope và trạng thái policy được lưu đáng tin; không truyền `MigrationState` từ HTTP header vào hàm này.

Một tập assertions hữu ích:

~~~java
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;
import org.junit.jupiter.api.Test;

class MigrationPolicyTest {
    @Test
    void cannotDowngradeAfterV2Required() {
        assertFalse(MigrationPolicy.permits(
                MigrationState.HMAC_V2_REQUIRED,
                CredentialScheme.LEGACY_API_KEY));
        assertFalse(MigrationPolicy.permits(
                MigrationState.HMAC_V2_REQUIRED,
                CredentialScheme.HMAC_V1));
        assertTrue(MigrationPolicy.permits(
                MigrationState.HMAC_V2_REQUIRED,
                CredentialScheme.HMAC_V2));
    }

    @Test
    void suspendedClientHasNoAcceptedScheme() {
        for (CredentialScheme scheme : CredentialScheme.values()) {
            assertFalse(MigrationPolicy.permits(
                    MigrationState.SUSPENDED, scheme));
        }
    }
}
~~~

**Đừng chỉ test hàm `permits` bằng cách gọi chính hàm đó để tạo expected.** Acceptance table ở mục 3 là oracle độc lập. Integration test phải chứng minh policy của client **được tải từ store thật** và có hiệu lực trên mọi pod, kể cả khi cache đã warm.

## 10. HTTP integration tests qua Spring Security

Một integration test phải đi qua authentication filter/manager thực và assert:

1. **Authentication**: server xác định principal từ key record hoặc cơ chế legacy đã được policy cho phép.
2. **Authorization**: principal có/không có quyền truy cập route/resource như được quy định.
3. **Side effects**: request bị từ chối không gọi business handler và không ghi dữ liệu.
4. **HTTP semantics**: credential sai → 401, đã xác thực nhưng thiếu quyền → 403, không thể xác minh do store lỗi → 503 theo policy.

Ví dụ khung test sử dụng test harness của dự án:

~~~java
// Pseudocode integration test; helpers do fixture cung cấp,
// chạy qua Spring Security filter thật, không dùng @WithMockUser.
fixture.clockAt("2026-11-28T10:00:00Z");
fixture.setState("partner-a", "HMAC_V2_REQUIRED");
fixture.seedActiveHmacKey("partner-a-hmac-v2", "v2");
fixture.seedActiveHmacKey("partner-a-hmac-v1", "v1");

// Chữ ký V1 phải ĐÚNG về mặt crypto, nonce mới.
var legacyProfileRequest = fixture.signAsV1(
        "/public/v1/payments", "nonce-v1-denied-001");
var denied = fixture.sendHttp(legacyProfileRequest);
assertEquals(401, denied.statusCode());
assertEquals(0, fixture.paymentWriteCount());

// V2 ký đúng, scope write hợp lệ.
var v2Request = fixture.signAsV2(
        "/public/v2/payments", "nonce-v2-accepted-001");
var accepted = fixture.sendHttp(v2Request);
assertEquals(201, accepted.statusCode()); // Ví dụ API tạo resource.
assertEquals(1, fixture.paymentWriteCount());
~~~

**Quan trọng:** nếu V1 request tình cờ có MAC sai do test signer lỗi, 401 không chứng minh anti-downgrade. Hãy xác nhận V1 golden vector trước và dùng một nonce/key/time/route hợp lệ để duy nhất **policy V2_REQUIRED** quyết định từ chối.

### 10.1. Test cấu hình filter chain sau rollout

Những lỗi wire-level thường bị unit tests bỏ sót:

- V1 và V2 security filters đều chạy, tạo hai authentication contexts.
- Filter V2 bị đăng ký ngoài `SecurityFilterChain` / `SecurityWebFilterChain` và vô tình chạy hai lần.
- Route legacy thuộc `permitAll` trong khi handler payment vẫn tồn tại phía sau.
- Parser nhận header trùng và lấy giá trị đầu/cuối khác nhau giữa filter và controller.
- Gateway rewrite path/query nhưng Spring matcher và HMAC verifier lấy representation khác.
- Exception handler trả 401 nhưng controller đã ghi side effect trước đó.

Test với `MockMvc`/`WebTestClient` có filter chain được bật; bổ sung real HTTP/proxy tests khi cần quan sát behavior container, pooled body buffers và chuyển đổi HTTP version.

## 11. Bộ negative tests chống downgrade và confusion

| Case | Input/fixture | Kỳ vọng |
|---|---|---|
| Legacy sau khi bắt buộc HMAC | `HMAC_V2_REQUIRED` + API key legacy hợp lệ | 401, không fallback |
| V1 sau khi yêu cầu V2 | MAC V1 đúng nhưng policy cấm | 401, không side effect |
| V2 MAC sai, thêm API key cũ | Trộn hai credential | Bị từ chối theo policy; không cứu bằng legacy |
| V2 MAC sai, thêm V1 MAC đúng | Hai chữ ký trên cùng request | Không được OR/fallback với client V2-required |
| Header profile V2→V1 | Giữ key ID/MAC V2 | 401 |
| Key ID V1 + profile V2 | Đổi metadata, giữ MAC cũ | 401 |
| Version malformed/unknown | `none`, `v9`, trùng header | 400/401 theo contract, không chạy handler |
| Algorithm từ input | `X-Hmac-Algorithm: arbitrary` | Không được chọn tên JCA tùy ý |
| Legacy và HMAC cùng request | Ambiguous principal/tenant | Reject hoặc strict precedence như contract, không bypass |
| Thiếu signature ở V2 route | Header thiếu, key ID có | 401, không fallback |
| Query/path bị mutate | Sign A, gửi B giữ signature cũ | 401 nếu field ký bị đổi |
| Body bytes bị mutate | Sign body A, gửi body B | 401 nếu body digest được ký |
| HMAC hợp lệ nhưng thiếu quyền | Key readonly, route write | 403, không side effect |
| Policy/key store timeout | Request đúng cryptographically | 503/fail closed |
| Nonce store timeout | MAC đúng nhưng không claim được nonce | 503/fail closed |
| Key revoked nhưng cache còn entry | MAC đúng với secret cũ | 401 theo revoke policy |
| Route alias/encoded path | `%2F`, `%2e`, `//`, `;` | Không route bypass; reject/normalize theo contract |

**Không ép mọi path ambiguity trả 401.** URI malformed có thể bị gateway/container từ chối 400/404 trước verifier, miễn không có handler/side effect và không rơi vào route mở. Quan trọng là signer, verifier, router và authorization **đồng ý về operation thực thi**.

### 11.1. False positive do nonce và timestamp

Một test negative ký request A, gửi A thành công, rồi sửa path thành B **nhưng giữ cùng nonce** có thể nhận 401 chỉ vì replay. Để chứng minh MAC bảo vệ path/query:

1. Tạo **nonce mới chưa từng claim** cho case negative.
2. Tính signature trên request A với nonce mới.
3. Gửi request B **giữ nguyên signature của A**.
4. Giữ key/secret/timestamp/body/header khác đúng và hợp lệ.
5. Assert result 401 và, nếu có audit nội bộ, signature mismatch; không claim nonce theo policy.

Với test timestamp boundary, dùng `Clock.fixed`; với production synthetic, dùng clock đồng bộ và timestamp hiện hành. Đừng hardcode một timestamp cũ trong HTTP canary rồi kết luận v2 signer sai.

## 12. Nonce replay và idempotency xuyên migration

### 12.1. Atomic claim ở nhiều replica

Với shared Redis, một chính sách thường dùng:

~~~text
SET hmac:nonce:<trusted-client-scope>:<hash(nonce)> 1 NX PX <ttl-ms>
~~~

`NX` và expiry được thiết lập **atomically**; không kiểm tra `GET` rồi `SET` tách rời. Phạm vi nonce phải dựa vào identity **đã xác thực**, không tin header key ID chưa verified để cấp quyền. TTL phải bao phủ toàn bộ thời gian một signed request còn hợp lệ theo timestamp window; nếu window đối xứng `±W`, TTL bằng `W` từ lần nhận đầu có thể không đủ.

Test migration với hai replica:

~~~text
Request A: client partner-a, V1, nonce N, MAC V1 đúng
Request B: client partner-a, V2, nonce N, MAC V2 đúng
                  |
                  v
       Đồng thời qua replica A và B
                  |
                  v
    Shared nonce namespace nếu policy yêu cầu
                  |
                  v
       Tối đa một atomic claim thành công
~~~

Nếu chính sách migration đòi **không chấp nhận reuse nonce xuyên profile**, shared nonce key không nên chứa profile hoặc key ID như một partition độc lập làm tách cùng client. Nhưng scope cụ thể phụ thuộc kiến trúc multi-tenant/key; hãy tài liệu hóa và test threat model.

Với V1 và V2 ở **các request có signed method/path khác nhau**, việc nonce trùng có cần reject hay không là quyết định contract. Nếu cả hai đều có thể cùng thực hiện **một nghiệp vụ**, anti-replay phải được kết hợp với kiểm soát idempotency và mapping operation.

### 12.2. Migration từ API key không có nonce

Legacy API key không tự đưa request timestamp/nonce vào MAC. Trong giai đoạn `DUAL`, một payment có thể được submit:

~~~text
legacy API key → create payment #A
HMAC V2 + nonce mới → create payment #A một lần nữa
~~~

Nonce chỉ bảo vệ replay của **signed HMAC request**, không đủ ngăn hai request khác scheme. Bài test migration phải xác nhận business **idempotency key** hoặc transaction identity được ràng buộc đúng và có cơ chế chống double-commit, kể cả khi client retry với credential mới.

**Không** “tối ưu” bằng cách chấp nhận lại một nonce đã dùng để làm legacy retry dễ hơn. Đó là bypass replay protection.

### 12.3. Khi nonce store bị lỗi

Nếu Redis/nonce service unavailable, dù V1/V2 MAC khớp thì không được tiếp tục bằng scheme cũ khi client đã yêu cầu HMAC. Server phải fail closed; lỗi hạ tầng được phân loại riêng với credential invalid. Trong staging cần fault injection, trong production chỉ thực hiện chaos có giới hạn và được phê duyệt.

## 13. Key rotation/revoke, cache và tính nhất quán policy

Hệ thống có thể cache key metadata, shared secret, trạng thái key hoặc allowed signature profiles. Migration trở nên nguy hiểm nếu cache làm chậm quyết định `HMAC_V2_REQUIRED` hoặc việc revoke key V1.

### 13.1. Test theo timeline

~~~text
T0: V1 key K1 active, V2 key K2 chưa active
T1: K1 + K2 active theo overlap, client DUAL
T2: Client HMAC_V2_REQUIRED
T3: K1 revoked, K2 active
T4: Key/policy store unreachable
~~~

Test cho từng mốc:

| Mốc | Expected |
|---|---|
| T0 | Request V1 đúng policy được chấp nhận; V2 chỉ được nhận nếu đã bật |
| T1 | V1/V2 được nhận theo profile/key có hiệu lực, replay vẫn được chặn |
| T2 | MAC V1 dù đúng cũng bị 401; V2 đúng tiếp tục |
| T3 | K1 không được chấp nhận trên mọi replica, kể cả cache warm |
| T4 | Không cấp quyền bằng policy stale ngoài giới hạn; fail closed nếu không thể xác minh |

**TTL cache không phải revoke tức thì.** Nếu có yêu cầu thu hồi ngay, cần online check/invalidation đáng tin và chính sách cho trường hợp không thể đồng bộ. Một late cache refresh không được “hồi sinh” record active của K1 sau thông điệp revoke.

### 13.2. Đừng xoay lại secret trong test mà không kiểm soát

Nếu đang test **signature migration**, giữ key/secret phù hợp và chỉ đổi profile; nếu đang test **key rotation**, giữ canonical profile để xác định riêng logic key lifecycle. Khi test cả hai một lúc, phải có các case tách biệt cùng một case E2E tổng hợp.

Không dùng key production đang được đối tác sử dụng để thử revoke. Dùng synthetic key có scope nhỏ trong staging hoặc production probe có quy trình phê duyệt.

## 14. Tương thích SDK, gateway và canonical request

Migration không chỉ là backend. Những client SDK khác ngôn ngữ có thể encode URI, header và body khác nhau:

| Trường hợp | Client cũ/mới có thể khác nhau thế nào? | Cần test |
|---|---|---|
| HTTP method | Lowercase/uppercase | Canonical case đúng contract |
| Public path | Gateway rewrite thành internal path | Server kiểm tra signed public target tin cậy |
| Query | Reorder, duplicate, percent encoding | Raw/canonical query interpretation nhất quán |
| Header | Duplicate, whitespace, casing, newline | Header selection/normalization đúng contract |
| Body | JSON key order, whitespace, Unicode, gzip | SHA-256 trên đúng byte đã ký |
| Timestamp | Unix seconds vs ISO-8601, timezone | Format/window đúng, boundary tests |
| Nonce | Charset, uniqueness, TTL | Không replay; không collision giữa clients |
| Base64 | Standard vs URL-safe, padding | Strict decoding theo profile |
| HMAC algorithm | SHA-256 vs SHA-512; output length | Profile whitelist, không arbitrary JCA |
| Key ID | Old/new format hoặc tenant-scoped | Không lấy nhầm secret/tenant |
| Retry | Client ký lại timestamp/nonce | Business idempotency vẫn hoạt động |

**Không dùng một SDK mới để tạo cả expected vector lẫn actual request rồi tự tuyên bố backward compatibility.** Chạy **old SDK** thật theo phiên bản được hỗ trợ, **new SDK** thật, và golden vectors được xuất từ implementation khác. Nếu client cũ không thể nhận một số header mới, phải có contract compatibility rõ trong giai đoạn overlap.

### 14.1. Gateway path mapping và header spoofing

Ví dụ:

~~~text
Client signs: POST /public/v2/payments?account=A123&mode=preview
Gateway maps: POST /payments?account=A123&mode=preview
Handler runs: payments.create
~~~

Trong test qua proxy, cần:

1. Positive signature V2 được chấp nhận trên public route.
2. Giữ MAC cũ, đổi signed path/query → từ chối trước handler.
3. Client gửi `X-Original-URI`/`X-Internal-Route-Id` giả → không được dùng để lựa chọn canonical path.
4. Các biến thể `%2F`, `%2e`, `//`, semicolon và double decoding không vượt security matcher.
5. HTTP/2 `:path` → HTTP/1.1 request target không làm đổi effective operation.
6. Body bytes và các signed headers được bảo toàn hoặc có quy tắc ký rõ khi proxy biến đổi.

Không bật `permitAll` cho alias cũ chỉ vì gateway rewrite. Nếu nhiều public routes dẫn tới cùng handler, từng route phải có authentication và authorization policy tương ứng.

## 15. Shadow verification, dual-run và giới hạn của kết quả quan sát

Một số team chạy **shadow mode** trước khi bắt buộc HMAC:

~~~text
Request trong giai đoạn migration:
  ├── Legacy authentication quyết định request có được chấp nhận
  └── V2 shadow verifier chỉ quan sát/chấm compatibility
            (không tự cấp quyền và không gọi handler lần hai)
~~~

Điều kiện bắt buộc:

- Nếu request legacy **không mang đủ header/signature V2**, shadow không thể khẳng định HMAC V2 sẽ thành công; chỉ có thể ghi “không có dữ liệu thử”.
- Shadow verifier không được cấp `Authentication` riêng, thay route, tạo side effect hoặc claim nonce production một cách làm ảnh hưởng đến request enforce sau đó.
- Nếu cần kiểm tra replay trong shadow, dùng dữ liệu mô phỏng/namespace thử và ghi rõ **không chứng minh** anti-replay production đã hoạt động.
- Shadow kiểm tra HMAC bằng key/secret đã cấp đúng quyền, giới hạn CPU/I/O và tuyệt đối không log full canonical hoặc secret.
- Tỷ lệ shadow success chỉ là **tín hiệu compatibility**, không phải security gate cho `HMAC_V2_REQUIRED`.

Sau khi chuyển sang enforce, server mới bắt buộc HMAC V2; không dùng kết quả shadow như một “thẻ xác thực” cho request khác.

### 15.1. Dual accept khác dual signature

**Dual accept:** server cho phép một trong các scheme **theo client policy**, nhưng mỗi request có một scheme được xác định rõ. **Dual signature:** một request mang hai MAC và policy quyết định cần một hay cả hai. Với dual signature, nếu client đã `HMAC_V2_REQUIRED`, MAC V1 đúng **không cứu** MAC V2 sai. Đừng vô tình biến điều kiện AND bắt buộc thành OR.

## 16. Fault injection và test hiệu năng trong migration

### 16.1. Hệ thống có thể fail khác nhau theo profile

| Fault | Kỳ vọng |
|---|---|
| Key repository unavailable | Không coi error là unknown key; fail closed |
| Policy store unavailable | Không tự hạ client sang legacy/V1 |
| Nonce store unavailable | Không cho qua HMAC request chưa claim được nonce |
| One replica stale migration state | Không nhận scheme đã bị cấm quá propagation SLA |
| Gateway route config cũ trên một region | Không xác thực sai signed target; cảnh báo drift |
| Server clock skew | Timestamp window đúng policy; phát hiện bất thường |
| Secret manager trả key version sai | MAC không được chấp nhận với secret khác |
| Cache stampede khi key mới phát hành | Có limits/backpressure, không fallback credential |
| New SDK retry request sau timeout | Không duplicate side effect, có idempotency |
| Signature decoder nhận bytes sai | Reject, không chấp nhận truncated MAC |

**Staging** thích hợp để tắt Redis giả lập, gây network partition hay chạy concurrency race. **Production** chỉ nên dùng synthetic no-op và kiểm tra metrics/health; fault injection trực tiếp cần chủ sở hữu và blast radius được phê duyệt.

### 16.2. Đo latency và backend load

Migration có thể làm mỗi request tốn thêm key lookup, body hashing, HMAC verify và nonce claim. Cần so sánh:

- End-to-end request latency p50/p95/p99 theo route/profile.
- HMAC authentication duration, key lookup hit/miss, remote key-store QPS.
- Nonce claim latency/error, cache TTL/eviction và in-flight lookup.
- 401/403/503, replay rejects, invalid signature, unsupported profile.
- CPU/heap/GC, Servlet threads hoặc WebFlux event-loop saturation.
- Business success/duplicate idempotency outcome.

Không dùng client ID/key ID/nonce/timestamp/raw signature làm metric label; chọn profile enum, route template, outcome/reason enum và deployment version. Một p99 tốt hơn **không bù được** việc legacy fallback còn mở cho client V2-required.

## 17. Canary và bộ tiêu chí go/no-go

Một rollout nên tách **feature support** (server hiểu V2) khỏi **policy enforcement** (client bắt buộc V2):

~~~mermaid
flowchart TD
    A[Publish contract + golden vectors] --> B[Server hỗ trợ V2 ở staging]
    B --> C[Integration + gateway + distributed tests]
    C --> D[Server canary có telemetry]
    D --> E{Compat + security gates PASS?}
    E -- Không --> F[Freeze, triage, safe rollback/forward-fix]
    E -- Có --> G[Enable DUAL cho nhóm client]
    G --> H[Observe SDK V2 + key rotation]
    H --> I{Client đủ điều kiện V2 required?}
    I -- Chưa --> H
    I -- Có --> J[Enforce V2 per client]
    J --> K[Re-test no fallback + multi-replica]
    K --> L[Retire legacy/V1 trong giới hạn đã duyệt]
~~~

### 17.1. Security gates không được nới

| Gate | PASS | HARD STOP |
|---|---|---|
| Signed request | SDK V2 và server thống nhất canonical bytes | Signature đúng vẫn 401 sau proxy |
| Missing/invalid MAC | Protected route từ chối | Không có MAC mà handler vẫn chạy |
| Migration state | Client V2-required không vào legacy/V1 | Một pod chấp nhận scheme đã bị cấm |
| Revoke | Key cũ bị từ chối trong policy | Revoked key vẫn được nhận ngoài giới hạn |
| Replay | Atomic claim trên các replica | Hai replay có side effect |
| Authorization | MAC đúng nhưng thiếu quyền trả 403 | Cross-tenant/cross-resource access |
| Fail closed | Key/nonce/policy store lỗi không bypass | Fallback để giữ uptime |
| Gateway contract | Public target ↔ effective route đúng | Verify operation A, thực thi B |
| Observability | Đo accepted/rejected/unavailable theo profile | Secret hoặc high-cardinality input trong metric/log |

Một số ngưỡng availability/latency có thể tùy release; **bất kỳ security bypass nào là hard stop**, không được bù bởi tỷ lệ 2xx tăng.

### 17.2. Rollback nào an toàn?

Rollback software vẫn phải tôn trọng **trạng thái policy và key hiện tại**:

- **Có thể** rollback binary/gateway config nếu bản cũ vẫn thực thi policy V2-required, chống replay và reject key revoked.
- **Không được** tự bật lại API key legacy/V1 cho client đã chốt V2, hồi sinh secret revoked hoặc xóa nonce history.
- Nếu bản cũ không thể bảo đảm chính sách mới, cần forward-fix, cô lập route hoặc từ chối request an toàn.
- Sau rollback phải chạy lại **negative downgrade/replay/revoke/authz tests**, không chỉ positive smoke.

Rollback từ một bug V2 có thể yêu cầu phê duyệt ngoại lệ cho **một số client trong thời hạn xác định**; đó là quyết định bảo mật riêng với audit, không phải việc verifier tự fallback âm thầm.

## 18. Ma trận kiểm thử migration cho CI/staging/production

| Case | CI/unit | Staging E2E | Production safe |
|---|---|---|---|
| V1/V2 golden vectors | Bắt buộc | Bắt buộc | Synthetic check nếu được phép |
| Old SDK với legacy/V1 trong overlap | Có | Có qua gateway | Canary có client test |
| New SDK với V2 | Có | Có qua gateway | Synthetic read-only |
| Legacy/V1 khi V2-required | Có | Có trên mọi replica | Negative probe an toàn |
| Mixed/duplicate credential headers | Có | Có | Theo phạm vi đã duyệt |
| Changed signed method/path/query/body | Có | Có | Chọn synthetic cases |
| Timestamp boundary/clock skew | Fixed clock | Multi-node | Theo drift telemetry |
| Nonce replay đồng thời | Fake atomic | Redis, ≥2 replica | Chỉ khi được phê duyệt |
| Cross-version nonce reuse | Có | Có | Không làm thao tác ghi thật |
| Key rotate/revoke/cache invalidation | Có | Có | Synthetic key scope riêng |
| Key/policy/nonce store unavailable | Fake error | Fault injection | Health/availability monitoring |
| Authn 401 vs authz 403 | Có | Có | Synthetic restricted route |
| Tenant isolation | Có | Có | Chỉ synthetic tenants |
| Gateway rewrite/HTTP2/path ambiguity | Adapter unit | Proxy thật | Spot checks có giới hạn |
| Business idempotency xuyên scheme | Có | DB/event transaction test | Không tạo giao dịch giả trên live |
| Rollback rồi re-test chính sách | Test orchestration | Staging rollback | Verify sau rollback thật |

**Quan trọng:** nếu test “v1 bị chặn” dùng nonce đã claim hoặc key V1 bị revoke từ trước, 401 không chứng minh V2-required policy. Fixtures phải tách những nguyên nhân này.

## 19. Kế hoạch thực hành: một buổi kiểm thử migration

Một quy trình thực hành cho nhóm phát triển/vận hành:

1. **Khóa đặc tả.** Ghi rõ scheme, profile, canonical bytes, key state, server policy và TTL nonce. Chọn bộ golden vectors độc lập.
2. **Chuẩn bị fixture.** Tạo synthetic clients A/B, key legacy/V1/V2, clock cố định, nonce namespace riêng và protected no-op endpoint.
3. **Xác nhận baseline.** Old SDK hoạt động trong trạng thái legacy/dual đã cho phép; new SDK hoạt động đúng trong dual.
4. **Chạy negative crypto.** Đổi path/query/body sau khi ký và giữ chữ ký cũ; kiểm tra key/profile mismatch và header duplicate.
5. **Chuyển policy.** Đặt client A thành `HMAC_V2_REQUIRED` trên server; thử credential legacy và V1 **hợp lệ về mặt crypto** nhưng phải bị từ chối.
6. **Kiểm tra phân quyền.** Client B có MAC V2 đúng nhưng thiếu `payments:write` phải nhận 403, không side effect.
7. **Kiểm tra replay.** Gửi đồng thời V1/V2 theo overlap với nonce giống nhau, rồi thử retry cùng nghiệp vụ với nonce khác để kiểm tra idempotency.
8. **Kiểm tra revoke.** Làm warm cache tại hai replica, thu hồi synthetic key V1, xác minh chính sách lan truyền trong giới hạn cho phép.
9. **Kiểm tra gateway.** Ký public URI rồi gửi qua actual ingress; thử forwarded metadata giả và ambiguous encoded path.
10. **Fault injection.** Trong staging, làm policy/key/nonce store unavailable; tất cả tình huống không thể xác minh phải fail closed.
11. **Canary.** Chạy probes an toàn trên phiên bản mới, so 401/403/503, p95/p99 và client adoption theo profile đã parse.
12. **Kiểm tra rollback.** Thử quay về bản cũ nhưng không khôi phục legacy/V1 ngoài chính sách; ghi rõ quyết định/exception nếu có.

### 19.1. Kết quả chạy test nên được ghi thế nào?

~~~yaml
test_run: migration-hmac-fixture-001
environment: staging
server_release: synthetic-release-id
policy_state: HMAC_V2_REQUIRED
client_id: synthetic-partner-a
contract_profile: v2
clock_utc: "2026-11-28T10:00:00Z"
checks:
  golden_v2: PASS
  new_sdk_positive: PASS
  legacy_downgrade_rejected: PASS
  v1_downgrade_rejected: PASS
  changed_query_rejected: PASS
  cross_version_replay_protection: PASS
  revoked_key_rejected_all_replicas: PASS
  authz_readonly_denied_write: PASS
  policy_store_failure_closed: PASS
  gateway_public_target_binding: PASS
  no_side_effect_on_rejections: PASS
decision: GO
~~~

Đây là **bản ghi ví dụ, không phải kết quả đã chạy**. Trong hệ thống thật phải kèm trace/CI report và reference tới evidence đã kiểm soát, thời gian, người duyệt, phiên bản policy/key và số replica được test. Một ô `PASS` tự khai không thay thế dữ liệu xác minh.

## 20. Checklist cuối trước khi retire scheme cũ

- [ ] Có inventory SDK/client theo mức sử dụng, gồm cả client batch ít traffic và integration theo vùng.
- [ ] Hợp đồng V1/V2 được version hóa: method, public path/query, signed headers/body, encoding, signature format, MAC algorithm.
- [ ] Golden vectors có expected bytes/MAC cố định và được xác nhận độc lập giữa SDK và server.
- [ ] Migration state do server quản lý, không lấy từ client headers; policy đã có audit/version.
- [ ] Test acceptance matrix cho từng trạng thái/client, gồm **legacy/V1 đúng nhưng không được chấp nhận sau cutover**.
- [ ] Không có fallback tự động từ V2 sai sang V1 hoặc API key legacy; mixed credential header được xử lý đúng contract.
- [ ] Secret/key V1 và V2 có lifecycle riêng; key revoke không thể được chấp nhận qua cache stale ngoài policy.
- [ ] Timestamp dùng clock đáng tin và nonce claim nguyên tử, scope cross-version có test; retry idempotency riêng.
- [ ] Authn và authz được kiểm tra độc lập; cross-tenant/resource không truy cập sai.
- [ ] Changed path/query/header/body sau ký bị từ chối theo hợp đồng, kể cả qua gateway/proxy.
- [ ] Policy/key/nonce store unavailable → fail closed; fault injection staging đã PASS.
- [ ] Mọi case bị từ chối đều không gọi handler, ghi DB, publish event hoặc downstream write.
- [ ] Canary có positive **và** negative probes trên đúng build, đúng ingress, các region/replica quan trọng.
- [ ] Metrics có profile/outcome/reason enum hữu hạn, không lộ secret, raw signature, nonce hoặc key ID chưa xác thực.
- [ ] Rollback không tự kích hoạt lại credential/algorithm đã retire hoặc xóa nonce; có owner và phê duyệt ngoại lệ.
- [ ] Đã xác nhận đối tác nhận thông báo, biết deadline/key rotation và kênh hỗ trợ bảo mật.
- [ ] Sau khi retire legacy/V1, chạy test với **credential cũ đúng về toán học** và xác nhận mọi pod/region đều từ chối.

## 21. Kết luận

**Kiểm thử migration HMAC** là bài kiểm tra ranh giới **tương thích có điều kiện** và **bảo mật không suy giảm**. Nó không kết thúc ở việc SDK mới tạo được MAC hay request hợp lệ nhận 200; hệ thống phải chứng minh **legacy đã bị chặn khi đến hạn, V1 không thể cứu V2 sai, key revoked không thể hồi sinh, nonce không bị replay và authorization vẫn hoạt động trên đúng resource**.

Một chiến lược đáng tin dùng **golden vector độc lập → policy matrix → Spring Security/HTTP integration → gateway contract → multi-replica/fault tests → canary/rollback**. Mỗi bước cần positive và negative assertions cùng bằng chứng **không side effect khi từ chối**. Chỉ khi cả tính tương thích trong cửa sổ được phép lẫn việc loại bỏ đường cũ đều được chứng minh, migration mới có thể được coi là hoàn tất.
