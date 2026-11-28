# Kiểm thử tenant trong hệ thống xác thực HMAC đa tenant

## 1. Mục tiêu kiểm thử: HMAC hợp lệ chưa đủ để truy cập đúng tenant

Một hệ thống API đa tenant phục vụ nhiều tổ chức trên cùng một hạ tầng. Trong mô-đun **SECURITY_AUTHENTICATION_HMAC_REQUEST_AUTHENTICATION**, client tạo chữ ký HMAC từ shared secret và canonical request; server xác minh chữ ký, kiểm tra timestamp/nonce chống replay rồi áp dụng chính sách phân quyền. Khi có tenant, quy trình còn phải chứng minh **request được xử lý trong đúng phạm vi tenant đã được cấp quyền**.

Giả sử `client-a` thuộc `tenant-a` và sở hữu `key-a-v2`. Một request do chính client này tạo, có chữ ký HMAC đúng nhưng khai `X-Tenant-Id: tenant-b`, vẫn có thể là hành vi truy cập chéo tenant trái phép. Chữ ký chứng minh client biết shared secret; nó không tự cấp quyền truy cập dữ liệu của `tenant-b`. Ngược lại, nếu người trung gian đổi `X-Tenant-Id` trên đường truyền, chữ ký phải sai **nếu tenant đích nằm trong canonical request được ký đúng cách**.

Kiểm thử tenant phải chứng minh đồng thời bốn điều kiện:

1. **Xác thực đúng danh tính:** key ID chỉ ra credential cụ thể, thuộc đúng principal/client, còn hiệu lực và được xác minh bằng đúng secret.
2. **Ràng buộc tenant vào request:** tenant đích cùng các trường cần bảo vệ được parse theo một hợp đồng canonical duy nhất, nằm trong dữ liệu ký và không bị thay đổi ngầm ở proxy/gateway.
3. **Phân quyền và cô lập dữ liệu:** principal đã xác thực chỉ thao tác tenant, action và resource được phép; truy vấn và lệnh ghi dùng tenant hiệu lực từ context tin cậy.
4. **Tính nhất quán xuyên hệ thống:** không có gateway, worker, cache, region hoặc API phụ nào chấp nhận context tenant sai, key bị thu hồi hoặc replay.

Bài học này trình bày **chiến lược và ca kiểm thử cụ thể**. Mục tiêu là tạo bằng chứng rằng cơ chế xác thực HMAC đa tenant an toàn ở cả trường hợp thành công, thất bại và thay đổi trạng thái trong vận hành.

## 2. Mô hình dữ liệu kiểm thử và ranh giới tin cậy

Để kiểm thử có thể lặp lại, trước tiên cố định dữ liệu và quy tắc phân quyền. Ví dụ môi trường test có:

| Thành phần | Tenant A | Tenant B |
| --- | --- | --- |
| Tenant ID chính tắc | `tenant-a` | `tenant-b` |
| Client/principal | `client-a` | `client-b` |
| Credential hiện tại | `key-a-v2` | `key-b-v1` |
| Shared secret | `secret-A2` trong secret manager test | `secret-B1` trong secret manager test |
| Dữ liệu nghiệp vụ | `invoice-a-101` | `invoice-b-201` |
| Trạng thái ban đầu | ENABLED, key ACTIVE | ENABLED, key ACTIVE |
| Quyền mặc định | CRUD hóa đơn A | CRUD hóa đơn B |

Các secret trong bảng chỉ là **tên tượng trưng của fixture**. Không dùng secret production trong test, log hoặc artifact. Có thể thêm `key-a-v1` còn ACTIVE trong cửa sổ key rotation, `key-a-v0` đã REVOKED, và một principal `processor` có grant được quản trị cho một số hành động trên A/B.

Mô hình quan hệ tin cậy:

~~~mermaid
flowchart LR
    R["Request: tenant claim, key ID, HMAC"] --> V["Verifier: credential lookup + HMAC + replay"]
    K[("Credential registry")] --> V
    V --> P["Principal đã xác thực"]
    P --> A["Authorization: principal + target tenant + action + resource"]
    G[("Tenant grants / policy")] --> A
    A --> T["Effective TenantContext tin cậy"]
    T --> S["Service / Repository"]
    S --> D[("Dữ liệu có tenant_id")]
~~~

Phải phân biệt **tenant từ request** (chưa đáng tin), **tenant sở hữu credential** trong registry và **tenant hiệu lực** sau kiểm tra quyền. Nếu thiết kế không hỗ trợ ủy quyền liên tenant thì tenant hiệu lực phải trùng tenant sở hữu; nếu có delegation, quyền đối với tenant đích phải được kiểm tra riêng, không suy ra từ HMAC.

### Những bất biến mà bài test phải giữ

| Bất biến | Dấu hiệu lỗi cần phát hiện |
| --- | --- |
| `keyId → credential → ownerTenant` xác định rõ ràng | Key của A bị gán principal/tenant B |
| Tenant ảnh hưởng đến nghiệp vụ được ký hoặc được ràng buộc theo hợp đồng | Sửa tenant mà chữ ký vẫn được chấp nhận |
| Chỉ principal có grant phù hợp được truy cập tenant đích | Chữ ký A hợp lệ và truy vấn được hóa đơn B |
| Mọi resource được kiểm tra với effective tenant | URL của A nhưng `resourceId` thuộc B vẫn trả dữ liệu |
| Client/tenant DISABLED chặn mọi credential tương ứng | Đổi sang key version mới vượt qua trạng thái disabled |
| Key REVOKED/EXPIRED không còn xác thực được | Proxy có cache cũ vẫn chấp nhận secret đã thu hồi |
| Nonce đã dùng không được chấp nhận lại trong cửa sổ timestamp | Phát lại cùng request qua node khác vẫn thành công |
| Tenant context không rò giữa các request hay công việc bất đồng bộ | Request B bị xử lý bằng context A của thread trước |
| Mã phản hồi công khai không tiết lộ secret và trạng thái nội bộ | Dò được tenant hoặc key tồn tại qua thông báo chi tiết |

Mỗi ca kiểm thử nên nêu rõ **client đã ký request bằng secret nào**, **tenant được khai**, **tenant hiệu lực mong đợi**, **trạng thái credential** và **tác động dữ liệu kỳ vọng**. Chỉ kiểm tra mã HTTP mà không kiểm tra dữ liệu và audit có thể bỏ sót lỗi cross-tenant write.

## 3. Chuẩn bị môi trường kiểm thử có thể tái hiện

Bộ kiểm thử nên có các fixture độc lập:

1. **Tenant và client:** tạo tenant A, B; client/key sở hữu rõ ràng; trường hợp client ENABLED/DISABLED, tenant ENABLED/DISABLED.
2. **Credential:** tạo key hiện tại, key cũ trong rotation, key REVOKED, EXPIRED, NOT_YET_VALID; secret khác nhau và key ID không tái sử dụng.
3. **Dữ liệu:** tạo resource có ID khác nhau theo tenant và thêm một trường hợp ID giống nhau giữa hai tenant nếu hệ thống cho phép; snapshot dữ liệu trước khi gửi request.
4. **Đồng hồ:** dùng Clock cố định/được tiêm, ví dụ `2026-11-28T04:00:00Z`; kiểm tra biên timestamp và thời hạn mà không phụ thuộc thời gian máy chạy test.
5. **Replay store:** làm mới namespace test giữa các ca nhưng dùng **cùng kho nonce** cho nhiều verifier khi kiểm tra đồng thời/xuyên node.
6. **Gateway:** có môi trường đi qua đúng proxy/ingress/route rewrite như production; đo canonical target trước và sau proxy bằng phương pháp không làm lộ body/secret.
7. **Audit và dữ liệu:** có cách đọc kết quả từ DB, event bus và log bảo mật test để chứng minh không truy cập nhầm tenant.

Dùng một HMAC signer **độc lập với server verifier** để tạo test vector chuẩn. Nếu unit test gọi chung chính hàm canonicalize của server cho cả phía client lẫn server, hai bên có thể cùng mắc một lỗi mà test vẫn xanh. Với contract test, nên cố định input bytes, canonical bytes và chữ ký kỳ vọng từ một triển khai thứ hai hoặc vector đã được kiểm duyệt.

Giữ fixture rõ **môi trường/thời điểm/phiên bản hợp đồng ký**. Các giả định như “tenant ID luôn lowercase”, “query parameter sắp xếp theo byte UTF-8” hoặc “body hash tính trên bytes gốc” phải được định nghĩa trong hợp đồng, không để framework quyết định ngầm.

## 4. Nhóm kiểm thử xác thực và ràng buộc tenant

### 4.1. Ma trận positive/negative tối thiểu

| Test ID | Key/secret để ký | Tenant đích đã ký | Trạng thái/điều kiện | Kỳ vọng |
| --- | --- | --- | --- | --- |
| T-AUTH-01 | A2 | A | Client/key ENABLED/ACTIVE | Xác thực thành công, thực thi trong A nếu có quyền |
| T-AUTH-02 | B1 | B | Client/key ENABLED/ACTIVE | Xác thực thành công, thực thi trong B nếu có quyền |
| T-AUTH-03 | A2 | B | Không có grant liên tenant | HMAC có thể đúng nhưng từ chối authorization |
| T-AUTH-04 | A2 | A rồi sửa header sang B | Tenant đã bị đổi sau khi ký | Từ chối chữ ký, không dùng B |
| T-AUTH-05 | A2 | A | Header key ID đổi thành `key-b-v1` sau khi ký | Từ chối; không thử fallback secret |
| T-AUTH-06 | A2 | A | Key A2 bị REVOKED | Từ chối dù HMAC đúng |
| T-AUTH-07 | A2 | A | Tenant A DISABLED | Từ chối, không dùng key khác để vượt chặn |
| T-AUTH-08 | A2 | A | Client A DISABLED | Từ chối tất cả key của client A |
| T-AUTH-09 | A2 | A | Key A2 vượt `expires_at` | Từ chối theo giờ server |
| T-AUTH-10 | A2 | A | Key A2 chưa tới `valid_from` | Từ chối |
| T-AUTH-11 | A2 | A | Sai body sau khi ký | Từ chối HMAC |
| T-AUTH-12 | A2 | A | Nonce/timestamp sai hoặc nonce đã dùng | Từ chối replay hoặc request không còn mới |
| T-AUTH-13 | A2 | B | Có grant riêng đúng action/resource và B ENABLED | Có thể được phép theo chính sách delegation |
| T-AUTH-14 | A2 | B | Có grant ở B nhưng sai action hoặc đã hết hạn | Từ chối authorization |

Phải kiểm tra cả **request được ký hợp lệ cho tenant B bằng chính secret A** (T-AUTH-03). Đây là bài test đặc biệt quan trọng: hệ thống vẫn phải từ chối vì thiếu quyền, cho dù không có lỗi mật mã.

Với một API không công bố chi tiết trạng thái tenant, các trường hợp xác thực lỗi có thể trả 401 theo hợp đồng; trường hợp đã xác thực nhưng không đủ quyền có thể trả 403 hoặc phản hồi che giấu quyền tồn tại của resource (ví dụ 404) theo chính sách. **Điều quan trọng là từ chối nhất quán, không rò dữ liệu và ghi đúng mã lý do nội bộ.**

### 4.2. Phân biệt các lỗi trong log nội bộ

| Trường hợp | Mã kiểm tra nội bộ dự kiến |
| --- | --- |
| Key ID không có / không khớp owner | `CREDENTIAL_NOT_FOUND` hoặc `CREDENTIAL_OWNER_MISMATCH` |
| Tenant bị sửa so với dữ liệu đã ký | `SIGNATURE_MISMATCH` |
| Client ký B bằng secret A, không có grant | `TENANT_ACCESS_DENIED` |
| Credential hết hạn hoặc bị thu hồi | `CREDENTIAL_NOT_ACTIVE` |
| Tenant hoặc client bị vô hiệu hóa | `CLIENT_OR_TENANT_DISABLED` |
| Nonce đã sử dụng | `REPLAY_DETECTED` |
| Service không nhận context đáng tin | `TENANT_CONTEXT_MISSING` |

Các mã trên chỉ mang tính ví dụ; không bắt buộc hệ thống phải dùng tên giống hệt. Test cần xác nhận **các nguyên nhân khác nhau không bị gộp thành “sai chữ ký” trong dữ liệu vận hành**, trong khi phản hồi công khai vẫn không biến thành công cụ dò tài khoản.

## 5. Kiểm thử hợp đồng canonical request có chứa tenant

HMAC ký **bytes**, không ký khái niệm “cùng ý nghĩa”. Một byte khác có thể làm chữ ký thay đổi. Giả sử hợp đồng `HMAC-REQUEST-V1` xây dựng các dòng UTF-8 theo thứ tự:

~~~text
HMAC-REQUEST-V1
POST
/v1/invoices?currency=VND
tenant-a
key-a-v2
2026-11-28T04:00:00Z
nonce-0001
<sha256-hex-cua-body-bytes>
~~~

Dòng cuối là placeholder; vector thực tế phải dùng digest thật, xác định dấu xuống dòng, normalization URI và body bytes gốc. Hợp đồng của một sản phẩm khác có thể dùng cấu trúc khác, nhưng **client, gateway và verifier phải cho cùng canonical bytes với cùng request được phép**.

### Ma trận canonicalization

| Biến thể đầu vào | Điều kiện kiểm thử |
| --- | --- |
| `X-Tenant-Id: tenant-a` so với `Tenant-A` | Từ chối biểu diễn không chuẩn hoặc chuẩn hóa đúng theo hợp đồng |
| Giá trị tenant có khoảng trắng đầu/cuối | Không được có cách hiểu khác giữa signer và verifier |
| Hai header `X-Tenant-Id` | Từ chối request mơ hồ, không chọn header tùy ý |
| Tenant trong path A, header B | Từ chối theo quy tắc đối chiếu nguồn tenant |
| Query `a=1&b=2` so với `b=2&a=1` | Canonical bytes đúng như hợp đồng; không dựa thứ tự ngẫu nhiên |
| Query có tham số trùng `a=1&a=2` | Quy tắc giữ thứ tự/sắp xếp/từ chối được kiểm tra tường minh |
| Ký tự `%2F` và `/` trong path | Không giải mã thành đường dẫn tenant khác ngoài hợp đồng |
| `%2f` so với `%2F` | Kết quả normalization có thể kiểm chứng, không double-decode |
| Unicode hoặc dấu tiếng Việt trong URI/body | Encode UTF-8 ổn định; body hash phản ánh bytes thật |
| JSON có thứ tự field hoặc whitespace khác | Nếu ký digest body bytes gốc, chữ ký thay đổi đúng kỳ vọng |
| Body rỗng, body `{}`, body `null` | Digest khác nhau và được xử lý chính xác |
| Method `GET` so với `POST` | Thay method khiến chữ ký không còn hợp lệ |
| Nhiều `Content-Type` hoặc signed header khác nhau | Parser xử lý/từ chối theo hợp đồng, không có ambiguity |
| Client gửi `X-Original-URI` / `X-Forwarded-Host` | Giá trị giả mạo không được dùng làm nguồn canonical đáng tin |
| Proxy rewrite route `/tenants/A/...` thành `/...` | Signer và verifier dùng đúng canonical target đã quy định |

Hai bài test cần chạy độc lập: (1) **bytes ký từ client** bằng đúng bytes verifier dùng; (2) **tenant hiệu lực** sau HMAC và phân quyền là tenant được phép. Chữ ký đúng không chứng minh test tenant đã đạt.

Một cách làm tốt là snapshot **canonical bytes an toàn trên fixture test** rồi so sánh với vector tham chiếu đã xác nhận. Không log canonical request từ production khi nó chứa dữ liệu nhạy cảm.

## 6. Ví dụ Java 17 + JUnit 5: ký đúng vẫn không được vượt tenant

Đoạn code dưới đây là **test harness tối giản có thể đặt trong test source set** của dự án Java 17 với JUnit Jupiter. Mục đích là kiểm tra logic ranh giới: ký HMAC thật bằng hai secret test riêng, kiểm tra signature, nonce, trạng thái credential và tenant của resource. Ví dụ dùng một tenant cho mỗi credential, không triển khai delegation.

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.time.Duration;
import java.time.Instant;
import java.util.Base64;
import java.util.HashMap;
import java.util.HashSet;
import java.util.HexFormat;
import java.util.Map;
import java.util.Set;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

class TenantHmacBoundaryTest {
    private static final Instant SERVER_NOW =
        Instant.parse("2026-11-28T04:00:00Z");

    enum Outcome {
        ALLOWED, AUTHENTICATION_FAILED, TENANT_FORBIDDEN
    }

    record Credential(
        String keyId,
        String ownerTenant,
        byte[] secret,
        boolean active
    ) {}

    record Request(
        String keyId,
        String tenant,
        String method,
        String canonicalTarget,
        String timestamp,
        String nonce,
        byte[] body,
        String signature
    ) {}

    private Map<String, Credential> registry;
    private Set<String> seenNonce;
    private Set<String> disabledTenants;

    @BeforeEach
    void setup() {
        registry = new HashMap<>();
        registry.put("key-a-v2", new Credential(
            "key-a-v2", "tenant-a",
            "test-secret-a-with-independent-entropy".getBytes(
                StandardCharsets.UTF_8), true));
        registry.put("key-b-v1", new Credential(
            "key-b-v1", "tenant-b",
            "test-secret-b-with-independent-entropy".getBytes(
                StandardCharsets.UTF_8), true));
        seenNonce = new HashSet<>();
        disabledTenants = new HashSet<>();
    }

    private static String canonical(Request req) {
        byte[] digest;
        try {
            digest = MessageDigest.getInstance("SHA-256")
                .digest(req.body());
        } catch (GeneralSecurityException ex) {
            throw new IllegalStateException(ex);
        }

        return String.join("\n",
            "HMAC-REQUEST-V1",
            req.method(),
            req.canonicalTarget(),
            req.tenant(),
            req.keyId(),
            req.timestamp(),
            req.nonce(),
            HexFormat.of().formatHex(digest));
    }

    private static byte[] hmac(byte[] secret, Request req) {
        try {
            Mac mac = Mac.getInstance("HmacSHA256");
            mac.init(new SecretKeySpec(secret, "HmacSHA256"));
            return mac.doFinal(
                canonical(req).getBytes(StandardCharsets.UTF_8));
        } catch (GeneralSecurityException ex) {
            throw new IllegalStateException(ex);
        }
    }

    private Request signed(String keyId, String tenant, String nonce) {
        Request unsigned = new Request(
            keyId, tenant, "POST", "/v1/invoices",
            SERVER_NOW.toString(), nonce,
            "{\"amount\":100}".getBytes(StandardCharsets.UTF_8),
            null);

        byte[] bytes = hmac(registry.get(keyId).secret(), unsigned);
        return new Request(
            keyId, tenant, unsigned.method(),
            unsigned.canonicalTarget(), unsigned.timestamp(),
            unsigned.nonce(), unsigned.body(),
            Base64.getEncoder().encodeToString(bytes));
    }

    private Outcome process(Request req, String resourceOwnerTenant) {
        Credential key = registry.get(req.keyId());
        if (key == null || !key.active()
                || disabledTenants.contains(key.ownerTenant())) {
            return Outcome.AUTHENTICATION_FAILED;
        }

        Instant timestamp;
        try {
            timestamp = Instant.parse(req.timestamp());
        } catch (RuntimeException invalidTimestamp) {
            return Outcome.AUTHENTICATION_FAILED;
        }
        if (Duration.between(timestamp, SERVER_NOW).abs()
                .compareTo(Duration.ofMinutes(5)) > 0) {
            return Outcome.AUTHENTICATION_FAILED;
        }

        byte[] supplied;
        try {
            supplied = Base64.getDecoder().decode(req.signature());
        } catch (RuntimeException invalidSignature) {
            return Outcome.AUTHENTICATION_FAILED;
        }
        byte[] expected = hmac(key.secret(), req);
        if (supplied.length != expected.length
                || !MessageDigest.isEqual(supplied, expected)) {
            return Outcome.AUTHENTICATION_FAILED;
        }

        // Test in-memory; production phải dùng thao tác nguyên tử,
        // TTL và kho nonce chung cho mọi gateway/verifier.
        if (!seenNonce.add(req.keyId() + ":" + req.nonce())) {
            return Outcome.AUTHENTICATION_FAILED;
        }

        // Đã xác thực HMAC, nhưng vẫn phải xét tenant đích
        // và tenant thực sự sở hữu resource.
        if (!key.ownerTenant().equals(req.tenant())
                || !req.tenant().equals(resourceOwnerTenant)) {
            return Outcome.TENANT_FORBIDDEN;
        }

        return Outcome.ALLOWED;
    }

    @Test
    void ownTenantWithValidHmacIsAllowed() {
        Request req = signed("key-a-v2", "tenant-a", "n-001");
        assertEquals(Outcome.ALLOWED, process(req, "tenant-a"));
    }

    @Test
    void correctlySignedRequestToOtherTenantIsDenied() {
        // Client A cố tình ký tenant B bằng secret của chính A.
        Request req = signed("key-a-v2", "tenant-b", "n-002");
        assertEquals(
            Outcome.TENANT_FORBIDDEN, process(req, "tenant-b"));
    }

    @Test
    void changingTenantAfterSigningInvalidatesSignature() {
        Request original = signed("key-a-v2", "tenant-a", "n-003");
        Request tampered = new Request(
            original.keyId(), "tenant-b", original.method(),
            original.canonicalTarget(), original.timestamp(),
            original.nonce(), original.body(), original.signature());

        assertEquals(
            Outcome.AUTHENTICATION_FAILED,
            process(tampered, "tenant-b"));
    }

    @Test
    void resourceOfOtherTenantIsDeniedEvenWithOwnTenantClaim() {
        Request req = signed("key-a-v2", "tenant-a", "n-004");
        assertEquals(
            Outcome.TENANT_FORBIDDEN, process(req, "tenant-b"));
    }

    @Test
    void disabledTenantCannotUseActiveCredential() {
        disabledTenants.add("tenant-a");
        Request req = signed("key-a-v2", "tenant-a", "n-005");
        assertEquals(
            Outcome.AUTHENTICATION_FAILED,
            process(req, "tenant-a"));
    }

    @Test
    void sameNonceCannotBeUsedTwice() {
        Request req = signed("key-a-v2", "tenant-a", "n-006");
        assertEquals(Outcome.ALLOWED, process(req, "tenant-a"));
        assertEquals(
            Outcome.AUTHENTICATION_FAILED,
            process(req, "tenant-a"));
    }

    @Test
    void swappingKeyIdAfterSigningDoesNotFindMatchingSecret() {
        Request original = signed("key-a-v2", "tenant-a", "n-007");
        Request wrongKey = new Request(
            "key-b-v1", original.tenant(), original.method(),
            original.canonicalTarget(), original.timestamp(),
            original.nonce(), original.body(), original.signature());

        assertEquals(
            Outcome.AUTHENTICATION_FAILED,
            process(wrongKey, "tenant-a"));
    }
}
~~~

**Giới hạn của mã minh họa:** `process` chỉ mô phỏng pipeline test với hai tenant, một endpoint, một policy `ownerTenant == requestedTenant == resourceOwnerTenant`. Nó chưa kiểm tra trạng thái client, vòng đời key đầy đủ, delegated grant, header trùng, độ dài input, canonical URI qua proxy, dữ liệu database thực tế hay nonce dùng chung trong hệ thống phân tán. Trong production, secret phải đến từ kho bí mật, body bytes và canonical target phải do tầng giao thức đáng tin tạo, trạng thái tenant/credential cần độ mới được kiểm soát. Không sao chép logic test harness này làm verifier production.

Việc `seenNonce` dùng `HashSet` chỉ hợp lệ khi chạy unit test tuần tự. Test tích hợp chống replay phải dùng Redis/DB hoặc store thật có thao tác insert-if-absent nguyên tử trên tất cả verifier và TTL bao phủ cửa sổ timestamp. Test này chứng minh **hành vi kỳ vọng ở một điểm kiểm tra**, chưa chứng minh tích hợp đầy đủ.

## 7. Kiểm thử resource và dữ liệu thực tế: chống IDOR chéo tenant

Nếu hệ thống có `GET /v1/invoices/{invoiceId}`, lỗi thường gặp là code tìm invoice bằng `invoiceId` rồi trả về ngay vì HMAC đã hợp lệ. Khi đó client A có thể đoán ID của B và đọc hóa đơn B.

Bộ test cần dựng hai tầng điều kiện:

- `authenticatedTenantContext.effectiveTenantId == tenant-a`.
- Resource trong database thực sự thuộc `tenant-a`, hoặc có quyền chia sẻ/ủy quyền cụ thể đã được xác nhận.

Ví dụ query an toàn:

~~~sql
SELECT invoice_id, tenant_id, amount, status
FROM invoices
WHERE tenant_id = :effective_tenant_id
  AND invoice_id = :invoice_id;
~~~

Với thao tác cập nhật:

~~~sql
UPDATE invoices
SET status = :new_status
WHERE tenant_id = :effective_tenant_id
  AND invoice_id = :invoice_id
RETURNING invoice_id, tenant_id, status;
~~~

Kiểm thử phải xác nhận **không hàng nào thuộc tenant B bị đọc, đổi hoặc xóa** khi request đã xác thực là tenant A. Kiểm tra trạng thái database **trước và sau** request. Đừng coi HTTP 403 là đủ nếu service đã thay đổi dữ liệu rồi mới trả lỗi do một filter chạy muộn.

### Ca kiểm thử dữ liệu cần có

| Bề mặt | Tình huống | Bằng chứng mong đợi |
| --- | --- | --- |
| GET theo ID | A dùng ID hóa đơn B | Không trả body/metadata B; DB không đổi |
| LIST + pagination | A gửi cursor/page token sinh từ B | Không xuất hiện bản ghi B, cursor bị ràng buộc tenant |
| CREATE | A gửi body `tenantId=B` dù path/header A | Từ chối hoặc lấy tenant từ context tin cậy; không tạo row ở B |
| UPDATE/DELETE | A sửa ID chỉ tồn tại ở B | Không có hàng B bị ảnh hưởng |
| Bulk API | Danh sách ID trộn A/B | Policy được áp dụng từng item hoặc từ chối toàn bộ theo hợp đồng |
| Search/export | A lọc/query tìm thông tin B | Chỉ nhận dữ liệu A, kể cả aggregate count và file export |
| File/object storage | A dùng object key của B | Storage lookup gắn tenant và quyền, không có presigned URL của B |
| Cache response | A và B gọi cùng URL/resource key | Cache phải namespace theo tenant và policy phù hợp |
| Async job/event | A tạo job xử lý resource B | Worker từ chối dữ liệu B và không dùng header tenant của caller |
| Error/reporting | A cố tình truyền ID B | Không rò owner, schema, storage path hay dữ liệu B qua lỗi |

Một lỗi khó phát hiện: API từ chối GET của B nhưng endpoint **export** hoặc **batch** dùng query không có `tenant_id`, vẫn trả dữ liệu B. Cần chạy cùng tập negative test cho **mọi đường truy cập dữ liệu**: REST, GraphQL, batch, worker và tool nội bộ có khả năng xử lý request từ client.

Nếu sử dụng PostgreSQL Row Level Security, kiểm thử bằng tài khoản database thực thi thật để xác nhận policy tenant được bật và session tenant được đặt lại đúng sau khi trả connection vào pool. Chỉ thấy `tenant_id` trong câu SQL không chứng minh RLS hoặc connection pool an toàn.

## 8. Kiểm thử tenant context xuyên gateway, proxy và microservice

Trong thực tế, HMAC có thể được xác minh ở gateway rồi truyền danh tính và tenant đã xác thực cho service phía sau. Những biến thể cần kiểm thử:

~~~mermaid
sequenceDiagram
    participant C as Client A
    participant G as API Gateway
    participant S as Invoice Service
    participant DB as Database
    C->>G: Key A + signed tenant-a
    G->>G: Verify HMAC, replay, tenant policy
    G->>S: Authenticated tenant-a context
    S->>DB: Query WHERE tenant_id=tenant-a
    DB-->>S: Chỉ dữ liệu A
    S-->>C: Kết quả A
    Note over C,G: Client gửi thêm X-Authenticated-Tenant: tenant-b
    C->>G: Header nội bộ giả mạo
    G->>G: Loại bỏ header giả; tạo context mới
~~~

### Danh sách ca tích hợp trọng tâm

1. **Header nội bộ giả mạo:** client gửi `X-Authenticated-Tenant: tenant-b`. Gateway phải xóa mọi giá trị do client tự gửi, rồi tạo context nội bộ từ kết quả xác thực và policy. Service không đọc header ngoài để thay thế context tin cậy.
2. **Bypass gateway:** gọi trực tiếp endpoint service vốn chỉ tin header tenant mà không xác minh nguồn. Kỳ vọng: từ chối khi thiếu mTLS/token nội bộ được xác minh hoặc cơ chế xác thực tương đương.
3. **Proxy rewrite:** client ký path/query nguyên gốc; gateway đổi route. Verifier phải dùng dạng canonical URI theo hợp đồng. Kiểm thử request thực qua ingress, proxy, gateway và service, không chỉ gọi verifier trực tiếp.
4. **Header duplicate/casing:** nhiều `X-Tenant-Id`, khoảng trắng, tenant viết hoa, nhiều header key ID, chuyển HTTP/1.1 sang HTTP/2. Parser ở gateway và backend phải có kết quả thống nhất, từ chối ambiguity.
5. **Propagation:** gateway kết luận effective tenant A nhưng service nhận tenant B do header hoặc interceptor ghi đè. Kỳ vọng: service từ chối và không thao tác dữ liệu.
6. **Thread/context leak:** gửi xen kẽ request A và B trên cùng thread pool, cùng connection hoặc reactive chain. Kỳ vọng: dữ liệu A/B không lẫn; thread-local/MDC được dọn; async context chỉ mang thông tin tin cậy.
7. **Service-to-service:** service A gọi billing/worker với tenant đã xác thực qua kênh nội bộ. Consumer kiểm tra token/audience, quyền và tenant của event; không tin trường `tenantId` trong payload bên ngoài.
8. **Streaming/cancel:** request nhận tenant A nhưng chuyển sang tenant B giữa các chunk hoặc retry. Kỳ vọng: context không bị thay đổi theo header bên ngoài và mỗi công việc gắn tenant ổn định.

Ở ca kiểm thử proxy, cần xác nhận **cả chữ ký** lẫn **tenant hiệu lực**. Một bản vá canonicalization có thể làm HMAC đúng nhưng vô tình chọn tenant từ URI đã rewrite thay vì tenant đã được kiểm tra trước đó.

## 9. Kiểm thử timestamp, nonce và replay theo tenant

HMAC không tự ngăn replay. Một chữ ký đúng có thể được phát lại nếu timestamp/nonce không được kiểm tra. Trong môi trường nhiều tenant, cách chọn namespace của nonce store cũng có thể tạo lỗ hổng.

Các kịch bản:

| Ca | Cách thực hiện | Kỳ vọng |
| --- | --- | --- |
| R-01 | Gửi cùng request A hai lần tới cùng node | Lần hai bị từ chối |
| R-02 | Gửi request A tới node 1 rồi replay tới node 2 | Lần sau bị từ chối trên toàn cụm |
| R-03 | Hai request giống nhau đến đồng thời | Chỉ một request được đăng ký nonce thành công |
| R-04 | Timestamp cũ hơn cửa sổ cho phép | Từ chối trước khi thực hiện nghiệp vụ |
| R-05 | Timestamp ở sát biên cửa sổ | Kết quả đúng quy tắc inclusive/exclusive của hợp đồng |
| R-06 | Timestamp tương lai vượt mức clock skew | Từ chối |
| R-07 | Nonce rỗng, cực dài hoặc chứa ký tự không cho phép | Từ chối input |
| R-08 | Gửi cùng nonce với hai key khác nhau | Xử lý đúng scope nonce đã công bố, không ghi đè nhầm credential |
| R-09 | Thay tenant claim mà giữ chữ ký và nonce | Từ chối do HMAC hoặc tenant policy, không được tạo ngữ cảnh khác |
| R-10 | Kho nonce ngừng hoạt động | Fail closed, không tạm bỏ kiểm tra để giữ throughput |

Một khóa replay thường là `(credentialId, nonce)` với TTL bao phủ toàn bộ thời gian request đã ký có thể được chấp nhận. Nếu dùng `(credentialId, tenantId, nonce)`, phải có lý do hợp đồng rõ ràng vì cùng credential có thể gửi tới nhiều tenant khi có delegated grant. Đừng để việc thay tenant mở lại cửa sổ replay của cùng chữ ký.

**Quan trọng về thứ tự:** chỉ đăng ký nonce sau khi chữ ký HMAC hợp lệ để tránh người ngoài chiếm nonce của client bằng request giả mạo. Nhưng dù nonce mới, request vào tenant không có quyền vẫn phải bị từ chối. Test nên đo cả side effect và idempotency nghiệp vụ vì chống replay không thay thế idempotency key trong các luồng như thanh toán.

## 10. Kiểm thử key rotation, client/tenant disabled và trạng thái cache

Một tenant có thể có nhiều client, mỗi client nhiều key version. Khi rotation, key cũ và mới có thể cùng ACTIVE trong thời gian chuyển đổi, nhưng chúng **không làm thay đổi quyền tenant**.

| Kịch bản | Kỳ vọng |
| --- | --- |
| Key A v1 và v2 cùng ACTIVE, yêu cầu tenant A | Cả hai được xét HMAC độc lập nếu nằm trong cửa sổ hợp lệ |
| Key A v1 REVOKED, v2 ACTIVE | v1 bị từ chối; v2 tiếp tục hoạt động theo quyền A |
| Tenant A DISABLED nhưng key v2 ACTIVE | Tất cả client/key của A bị chặn theo policy |
| Client A1 DISABLED, client A2 vẫn ENABLED trong tenant A | A1 bị chặn; A2 được xét độc lập, trừ khi tenant cũng DISABLED |
| Kích hoạt lại tenant A sau sự cố | Key đã REVOKED vẫn REVOKED, không tự hồi sinh |
| Thay version ở header từ A v1 thành A v2 sau khi ký | HMAC không khớp |
| Client A dùng key B | Từ chối owner mismatch và không cấp tenant B |
| Tạo key mới cho A nhưng giữ client disabled | Vẫn từ chối; rotation không bypass trạng thái client |

### Kiểm thử cache trạng thái và phân quyền

Thiết lập hai gateway dùng cache. Lúc `T0`, gateway B có snapshot `tenant-a=ENABLED` hoặc grant A→B đang cho phép. Lúc `T1`, registry commit `tenant-a=DISABLED` hoặc thu hồi grant. Ngay sau đó gửi request qua cả hai gateway.

Một test chỉ chứng minh database có trạng thái mới là **chưa đủ**. Cần đo:

- Mỗi gateway đã nhận revision mới chưa, hoặc có kiểm tra lại ở nguồn có thẩm quyền không?
- Node bị mất event hoặc offline có thể tiếp tục tin snapshot cũ quá giới hạn freshness không?
- Event cũ `ENABLED` đến sau event mới `DISABLED` có làm cache quay về trạng thái cũ không?
- Việc thu hồi key/grant có được áp dụng trước khi nghiệp vụ nhạy cảm chạy không?
- Khi registry, vault hoặc event bus lỗi, verifier có từ chối theo chính sách **fail closed** không?

Cam kết “mọi request mới sau commit DISABLED bị chặn” cần một điểm kiểm tra có trạng thái đủ mới hoặc cơ chế fail closed khi không chứng minh được. Pub/sub bất đồng bộ và TTL cache đơn thuần **không đảm bảo** điều đó. Test nên ghi rõ tiêu chuẩn mạnh hay yếu mà hệ thống thực sự áp dụng, tránh khẳng định thu hồi tức thì khi vẫn có cửa sổ dữ liệu cũ.

## 11. Kiểm thử delegation và quyền liên tenant

Nếu nghiệp vụ cho phép một principal phục vụ nhiều tenant, cần tạo fixture rõ ràng:

| Principal | Owner tenant | Target tenant | Action | Grant |
| --- | --- | --- | --- | --- |
| `processor` | `tenant-platform` | `tenant-a` | `CREATE_INVOICE` | ALLOW |
| `processor` | `tenant-platform` | `tenant-b` | `READ_INVOICE` | ALLOW |
| `processor` | `tenant-platform` | `tenant-b` | `DELETE_INVOICE` | DENY |
| `client-a` | `tenant-a` | `tenant-b` | Mọi action | DENY |

Các kiểm thử bắt buộc:

1. `processor` ký request tenant B cho `READ_INVOICE` với HMAC đúng: có thể được phép theo grant.
2. Cùng principal, cùng tenant B nhưng action `DELETE_INVOICE`: bị từ chối.
3. Grant đã hết hạn hoặc REVOKED: request bị từ chối dù cache từng trả ALLOW.
4. Tenant B bị DISABLED: grant chưa hết hạn không được ghi đè trạng thái tenant nếu chính sách yêu cầu chặn.
5. Principal chỉ có grant tenant A không được phép chọn B bằng cách sửa path/header/body.
6. Request tenant B đúng quyền nhưng `invoiceId` thuộc tenant A: vẫn không được truy cập nhầm resource.
7. Ở service sau gateway, context `effectiveTenant=B` phải giữ nguyên và được ký/xác thực trên đường nội bộ, không tin header do client tự gửi.

Đặc biệt phải thử **quyền theo action và resource**, không chỉ kiểm tra “principal có trong danh sách grant của tenant”. Một grant `READ` không tự động cấp `WRITE`, và grant đối với một nhóm resource không tự động bao phủ tất cả resource trong cùng tenant.

## 12. Test concurrency, failure và property-based

### Test tính chất bất biến

Với dữ liệu fixture có nhiều tenant/key/resource, có thể chạy property-based test:

> Với mọi credential `k` thuộc tenant `A` và mọi resource `r` thuộc tenant `B` khác `A`, nếu không có grant liên tenant phù hợp thì việc gửi request ký đúng bằng secret của `k` **không được làm lộ hoặc thay đổi** `r`.

Sinh có kiểm soát tenant ID, key ID, action, path, body và thứ tự request. Kiểm tra cả phản hồi lẫn trạng thái database cuối cùng. Những giá trị rìa nên bao gồm Unicode trong path, tenant ID có dấu cách, query trùng tham số, ID resource tương tự nhau và tenant có danh sách client rỗng.

### Test đồng thời và race condition

- Hai request giống nonce vào hai node tại cùng thời điểm: chỉ một request được chấp nhận.
- Hai admin thao tác disable/enable tenant cùng `row_version`: chỉ một cập nhật thành công; thao tác còn lại thấy xung đột.
- Một request đã qua xác thực rồi tenant bị DISABLED trước khi ghi dữ liệu: chính sách phải định nghĩa xử lý **in-flight**; nếu yêu cầu chặn trước commit nghiệp vụ, test kiểm tra lại trạng thái hoặc cơ chế hủy.
- Một job async chạy lâu vừa bắt đầu thì grant bị thu hồi: kiểm tra tại các điểm nhạy cảm theo cam kết, không chỉ ở thời điểm enqueue.
- Event REVOKED version 11 tới trước ENABLED version 10: cache không quay ngược.
- Nhiều request A/B xen kẽ trên thread pool hoặc coroutine: không có context tenant tồn dư.

### Fault injection

Dừng lần lượt registry, secret manager, replay store, authz store, gateway-to-service channel và event consumer. Kết quả mong đợi là **không có đường bỏ qua kiểm tra bảo mật khi phụ trợ lỗi**. Kiểm tra HTTP timeout, retry, circuit breaker và log/alert. Tránh coi lỗi hạ tầng là một yêu cầu HMAC hợp lệ mà vẫn cho thực thi nghiệp vụ.

## 13. Thiết kế bộ test end-to-end qua môi trường thực

Một lộ trình phù hợp:

~~~mermaid
flowchart TD
    U["Unit: policy + tenant resolver"] --> C["Contract: canonical bytes và HMAC vector"]
    C --> I["Integration: registry, DB, authz, replay store"]
    I --> G["Gateway E2E: proxy rewrite + forwarded headers"]
    G --> M["Multi-node: cache stale, rotation, revoke, concurrency"]
    M --> O["Observability: audit, metrics, không rò secret"]
~~~

**Unit test** chứng minh quy tắc như client/key owner khớp, tenant effective đúng và quyền không bị bỏ qua. **Contract test** kiểm tra byte-for-byte giữa signer và verifier với vector độc lập. **Integration test** xác nhận DB query, nonce atomic, trạng thái credential và delegated grant. **End-to-end test** chạy qua ingress/gateway/service thật để bắt lỗi rewrite, header trust và context propagation. **Fault/multi-node test** kiểm tra cache stale, event thất lạc, cạnh tranh và thời điểm thu hồi.

Một ca E2E tiêu chuẩn nên ghi:

~~~yaml
id: TENANT-E2E-004
purpose: Client A ký đúng HMAC nhưng không có quyền đọc dữ liệu B
given:
  credential: key-a-v2
  ownerTenant: tenant-a
  targetTenant: tenant-b
  resource: invoice-b-201
  method: GET
  clock: 2026-11-28T04:00:00Z
  nonce: e2e-tenant-004
when:
  signature: valid_hmac_with_key_a
  route: through_real_gateway
then:
  authorization: denied
  response: no_tenant_b_data
  database_b_unchanged: true
  audit: tenant_access_denied
~~~

YAML này là **mẫu mô tả test case**, chưa phải file cấu hình của một framework cụ thể. Có thể dùng mẫu tương tự để viết test data-driven cho từng route; quan trọng là test runner kiểm chứng đầy đủ phần `then`, đặc biệt side effect và tenant context sau gateway.

## 14. Quan sát kết quả kiểm thử và tiêu chí hoàn thành

Không nên chỉ đếm số test PASS; phải thu được bằng chứng cho những ranh giới trọng yếu.

| Bằng chứng | Mục đích |
| --- | --- |
| Trace request qua gateway và service | Biết effective tenant được giữ nhất quán |
| Audit principal/key/tenant/action/result | Phân biệt lỗi xác thực, phân quyền, tenant mismatch |
| Snapshot DB A/B trước và sau negative tests | Chứng minh không có dữ liệu tenant khác bị ảnh hưởng |
| Kết quả ký đối chiếu vector độc lập | Chứng minh canonical request đúng hợp đồng |
| Kết quả replay multi-node | Chứng minh nonce store dùng chung và có tính nguyên tử |
| Lag/revision của cache trạng thái | Đo cửa sổ thu hồi thực tế |
| Thống kê lỗi proxy, registry, authz, nonce store | Phát hiện đường fail open và tuyến bị bỏ sót |
| Kiểm tra log/header/body | Chứng minh không ghi shared secret hay dữ liệu nhạy cảm |

Giới hạn thông tin log: tuyệt đối không in shared secret hoặc chữ ký HMAC production; không dump toàn bộ canonical request có body nhạy cảm. Các định danh tenant/key có thể cần che hoặc bảo vệ theo chính sách. Dùng correlation ID và mã lý do hữu hạn; đừng tạo nhãn metric Prometheus với tenant/key có cardinality lớn.

Một phiên kiểm thử có thể coi là **đạt yêu cầu kỹ thuật cho phạm vi đã kiểm** khi:

- Mọi ca cross-tenant thiếu grant đều bị từ chối trước khi đọc/ghi dữ liệu ngoài phạm vi.
- Các request tenant hợp lệ tiếp tục hoạt động, kể cả khi tenant khác bị DISABLED hoặc key khác bị REVOKED.
- Không có trường hợp thay header/path/body/tenant/key ID sau ký mà vẫn vượt qua HMAC trái hợp đồng.
- Replay bị từ chối xuyên node; nonce, timestamp và trạng thái credential hoạt động đúng ở mốc biên.
- Gateway và downstream dùng duy nhất context tenant được xác thực và phân quyền; không tin header nội bộ giả mạo.
- Cache, rotation và thu hồi thực thi theo đúng cam kết freshness đã định, kể cả khi event mất hoặc phụ trợ lỗi.
- Test xác minh cả phản hồi, log/audit và side effect dữ liệu; không có secret hoặc dữ liệu tenant khác bị lộ.

## 15. Bài tập thực hành: phát hiện lỗi xuyên tenant qua proxy

Có hai tenant A và B. Client A có key `key-a-v3`, HMAC hợp lệ với request:

~~~http
GET /tenants/tenant-a/invoices/invoice-b-201 HTTP/1.1
Host: api.example.test
X-Key-Id: key-a-v3
X-Tenant-Id: tenant-a
X-Timestamp: 2026-11-28T04:05:00Z
X-Nonce: tenant-case-001
X-Signature: <base64-signature>
~~~

Gateway xác minh HMAC thành công, rồi rewrite path thành `/invoices/invoice-b-201` và forward `X-Tenant-Id: tenant-a`. Service gọi repository `findById("invoice-b-201")` mà **không kiểm tra tenant của resource**.

Hãy thiết kế bộ kiểm thử trả lời các câu hỏi:

1. Tại sao request có HMAC đúng và tenant header A vẫn có thể là truy cập chéo tenant?
2. Phản hồi và trạng thái database mong đợi là gì nếu `invoice-b-201` thuộc B?
3. Cần kiểm thử thêm endpoint LIST, UPDATE, DELETE và export thế nào để tránh bỏ sót đường đi?
4. Nếu người gửi sửa `X-Tenant-Id` thành B sau ký thì điều gì phải xảy ra?
5. Nếu client A **tự ký lại** request cho tenant B, test nào chứng minh nó không có grant hợp lệ?
6. Nếu service được gọi trực tiếp bằng header `X-Authenticated-Tenant: tenant-b`, nó phải kiểm tra gì?

**Định hướng:** Repository phải lấy `effectiveTenantId` đáng tin từ authorization và luôn scope query theo tenant. Chữ ký HMAC bảo đảm request không bị chỉnh trái phép, nhưng không cấp quyền với resource B; một resource ID từ B phải bị từ chối hoặc che giấu theo hợp đồng. Sửa tenant sau ký làm HMAC sai; tự ký tenant B bằng secret A có thể cho HMAC đúng nhưng phải bị từ chối authorization nếu thiếu grant. Downstream chỉ nhận tenant context qua kênh nội bộ đã xác thực và phải từ chối request không có context hợp lệ.

Trong hệ thống HMAC đa tenant, **kiểm thử tenant** chỉ đầy đủ khi kiểm chứng ba lớp đồng thời: **byte canonical request và chữ ký HMAC**, **tenant hiệu lực đã qua kiểm tra quyền**, và **dữ liệu thực tế được truy cập sau mọi gateway/service**. Một test chỉ xác nhận HMAC đúng hoặc HTTP status đúng sẽ không phát hiện hết nguy cơ truy cập chéo tenant.
