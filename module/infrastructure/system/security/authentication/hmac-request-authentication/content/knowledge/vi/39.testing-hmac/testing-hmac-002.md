# Wrong secret test: kiểm thử HMAC khi client dùng sai shared secret

## 1. Mục tiêu của bài kiểm thử

Trong mô-đun `SECURITY_AUTHENTICATION_HMAC_REQUEST_AUTHENTICATION`, client gửi HTTP request được ký bằng HMAC từ **shared secret** và **canonical request**. Canonical request có thể bao gồm HTTP method, URI/query, signed headers và SHA-256 digest của body theo hợp đồng. Phía server dùng key ID để tìm đúng secret và trạng thái credential, dựng lại canonical bytes, so sánh MAC, kiểm tra timestamp/nonce chống replay, rồi mới thiết lập danh tính được xác thực. Phân quyền với tenant, action và resource là bước riêng.

**Wrong secret test** là một kiểm thử âm tính (*negative test*) nhằm chứng minh:

> Khi client ký một request hoàn toàn đúng về cấu trúc bằng **secret khác với secret server lưu cho đúng key ID**, server phải từ chối xác thực, không gọi nghiệp vụ và không sử dụng nhầm secret của key/version khác.

Điều tưởng đơn giản này dễ kiểm thử sai. Nếu request đồng thời thiếu timestamp, nonce đã bị dùng, body bị thay đổi hoặc key ID không tồn tại, nhận được HTTP 401 **không chứng minh** hệ thống đã phát hiện *wrong secret*. Nó chỉ chứng minh một nhánh khác đã từ chối.

Bài thuộc chương **Testing HMAC** và tập trung vào cách tách biến kiểm thử, xây dữ liệu ký đáng tin cậy, kiểm tra hành vi của Spring Security 6 (Servlet/Reactive), đo các hiệu ứng phụ, kiểm thử proxy/gateway, key rotation và những lỗi triển khai nguy hiểm như fallback secret, cache xác thực hay ghi nonce trước khi kiểm tra MAC.

### Kết quả học tập

Sau bài này, người học có thể:

1. Thiết kế một ca `wrong secret` có đủ **positive control** và **negative control**.
2. Giữ nguyên key ID, client ID, timestamp, nonce, method, URI, header và body trong hai nhánh so sánh.
3. Chứng minh HMAC fail vì **secret sai**, chứ không vì request bị ký/parse sai.
4. Kiểm tra HTTP response, `SecurityContext`/Reactor Context, nonce store và không có side effect nghiệp vụ.
5. Kiểm thử nhiều key version, client/tenant, proxy rewrite, gateway và secret manager.
6. Không để lỗi dependency hoặc cấu hình bảo mật biến thành kết luận test sai.

## 2. Threat model: người gửi biết request nhưng không có đúng secret

Giả sử credential registry lưu:

| Trường | Giá trị test |
| --- | --- |
| `clientId` | `partner-a` |
| `keyId` | `partner-a-k4` |
| `serverSecret` | `test-secret-A-2026` (chỉ dùng trong test) |
| `status` | `ACTIVE` |
| `ownerTenant` | `tenant-a` |
| `allowedAction` | `CREATE_PAYMENT` |

Người gửi có thể biết đường API, cấu trúc canonical request, key ID, timestamp, nonce và body. Tất cả các giá trị đó **không phải shared secret**. Với secret `test-secret-B-2026`, người gửi tính ra một MAC đúng **với B**, nhưng server đang cấu hình **A** cho key ID đó. Bản MAC phải bị từ chối.

~~~mermaid
sequenceDiagram
    participant C as Test Client
    participant A as Gateway / App
    participant R as Credential Registry
    participant N as Nonce Store
    participant B as Business Handler
    C->>C: Canonical request bytes = C1
    C->>C: Signature = HMAC(secret B, C1)
    C->>A: keyId=partner-a-k4 + signature B
    A->>R: Lookup đúng partner-a-k4
    R-->>A: ACTIVE + secret A
    A->>A: expected = HMAC(secret A, C1)
    A->>A: So sánh expected != signature B
    A-->>C: 401 AUTHENTICATION_FAILED
    Note over N: Không claim nonce khi MAC sai
    Note over B: Không gọi nghiệp vụ
~~~

Đây không phải brute force test và không cần thử hàng triệu secret. Mục đích là **khẳng định hệ thống luôn dùng đúng secret được đăng ký cho key ID** và không bỏ qua bước so sánh MAC.

## 3. Điều gì phải được giữ cố định?

Nếu thay đổi nhiều biến cùng lúc, kết quả âm tính mất khả năng quy nguyên nhân.

| Thuộc tính | Ca dùng secret đúng | Ca dùng secret sai | Phải như nhau? |
| --- | --- | --- | --- |
| HTTP method | `POST` | `POST` | Có |
| Raw target | `/api/hmac/payments?currency=VND` | Y hệt | Có |
| `X-Client-Id` | `partner-a` | `partner-a` | Có |
| `X-Key-Id` | `partner-a-k4` | `partner-a-k4` | Có |
| `X-Tenant-Id` | `tenant-a` | `tenant-a` | Có |
| `X-Timestamp` | Hợp lệ theo fixed Clock | Cùng timestamp | Có |
| `X-Nonce` | Giá trị mới, chưa claim | Cùng giá trị trong **fixture độc lập** | Có |
| `Content-Type` | `application/json` | Y hệt | Có |
| Raw body | Cùng mảng bytes | Cùng mảng bytes | Có |
| Secret để ký | Secret A | **Secret B** | **Không** |
| Signature | HMAC(A, canonical) | HMAC(B, canonical) | Khác |
| Registry key/secret server | Key K4 → A | Key K4 → A | Có |
| Expected authentication | Thành công | **Thất bại** | Khác |

**Chú ý nonce ở positive control:** nếu chạy ca thành công trước và dùng **cùng replay store**, nonce đã bị claim; ca wrong-secret chạy sau có thể bị từ chối do replay dù implementation kiểm tra sai thứ tự. Để cô lập biến, cần **reset replay store giữa hai test**, tạo store mới cho mỗi test hoặc giữ wrong-secret làm lần đầu với nonce N rồi mới chạy positive test của **chính N** để chứng minh request sai MAC không chiếm nonce.

Không thay đổi `X-Key-Id` sang một key không có trong registry: đó là **unknown key test**, không phải wrong secret test.

## 4. Canonical request và bytes dùng để ký

Một hợp đồng ký minh họa có thể dùng các dòng UTF-8, ngăn cách bằng `LF`, không có newline cuối:

~~~text
HMAC-REQUEST-V1
POST
/api/hmac/payments?currency=VND
application/json
partner-a
partner-a-k4
tenant-a
2026-11-28T04:00:00Z
2e0fabf6-0e06-4bbc-a3bd-d3f31cb4ee5a
<sha256-hex-cua-raw-body>
~~~

Dòng hash cuối chỉ là placeholder; không phải một test vector đã tính. Hợp đồng thực tế cần chốt chính xác:

- Phương thức HTTP và cách chuẩn hóa.
- Raw path/query, thứ tự hoặc quy tắc chuẩn hóa query, percent-encoding.
- Signed headers, cách xử lý duplicate/case/whitespace.
- Key ID, client ID, tenant, timestamp, nonce có nằm trong chữ ký không.
- Body bytes hoặc body digest, định dạng hex/Base64 và charset.
- Dấu phân cách `LF`/`CRLF`, newline cuối, version.
- Encode chữ ký: raw bytes, hex hay Base64/Base64url.

Một thay đổi nhỏ trong canonical bytes sẽ làm MAC khác. Vì vậy một test trả 401 sau khi gửi URI đã bị rewrite hoặc JSON đã bị serialize lại **không quy được nguyên nhân cho secret sai**.

### Hai lớp test bổ sung nhau

**Lớp 1 — Unit test verifier:** inject canonical bytes cụ thể và kiểm tra đúng/sai HMAC theo secret. Giảm biến phụ thuộc HTTP/proxy.

**Lớp 2 — Integration/E2E:** dùng một signer **độc lập** hoặc test vector đã chốt để ký HTTP request thực; kiểm tra filter/manager, body buffering, proxy và nonce. Không để cả signer lẫn verifier dùng chung một bug canonicalization rồi tưởng rằng hệ thống đúng vì positive test vẫn pass.

## 5. Điều kiện để một wrong-secret test thực sự có giá trị

Một ca negative test đáng tin nên chứng minh các mệnh đề sau:

1. **Credential tồn tại:** registry trả secret A cho đúng key ID K4.
2. **Credential được phép:** K4 ACTIVE, client enabled, chưa hết hạn.
3. **Request còn mới:** timestamp nằm trong time window; Clock được cố định ở unit test.
4. **Nonce chưa dùng:** không có bản ghi replay cho N.
5. **Canonical input được kiểm soát:** phương thức, URI, signed headers và body trùng hoàn toàn giữa hai nhánh.
6. **Chữ ký wrong-secret thật sự hợp lệ dưới B:** signer tạo MAC từ secret B, không gửi chuỗi ký ngẫu nhiên hoặc Base64 lỗi.
7. **Chữ ký wrong-secret khác MAC dưới A:** test có assert độc lập nếu cần.
8. **Server từ chối vì authentication:** không tạo principal tin cậy, không gọi controller/service.
9. **Nonce không bị claim trước MAC:** request sai secret không gây nonce poisoning.
10. **Positive control dùng A đi qua chính đường verify:** xác nhận route không bị cấu hình “luôn trả 401” hoặc sai contract.
11. **Không có fallback:** server không thử secret K3/K5 hay default secret khi K4 mismatch.
12. **HTTP response không tiết lộ:** không công khai secret, expected MAC, key existence/state hoặc nội dung canonical request.

Với test có gateway, thêm điều kiện **gateway và backend thống nhất điểm xác minh**, không đếm nhầm việc backend từ chối internal assertion thành lỗi wrong-secret của client.

## 6. HMAC-SHA256 ở Java 17: signer cho test

Trong Java, `javax.crypto.Mac` tính HMAC. Mỗi lần gọi nên tạo một `Mac` instance riêng hoặc quản lý instance thread-safety đúng; không chia sẻ một instance mutable giữa nhiều request/thread mà chưa đồng bộ.

~~~java
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.util.Arrays;
import java.util.Base64;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

final class HmacTestCrypto {
    private HmacTestCrypto() {}

    static byte[] sign(byte[] secret, byte[] canonical) {
        try {
            Mac mac = Mac.getInstance("HmacSHA256");
            mac.init(new SecretKeySpec(secret, "HmacSHA256"));
            return mac.doFinal(canonical);
        } catch (GeneralSecurityException ex) {
            throw new IllegalStateException(
                "HmacSHA256 unavailable", ex);
        }
    }

    static String signBase64(
            byte[] secret, byte[] canonical) {
        return Base64.getEncoder().encodeToString(
            sign(secret, canonical));
    }

    static boolean matches(
            byte[] expected, byte[] received) {
        // Validate length/encoding trước khi gọi hàm này.
        return MessageDigest.isEqual(expected, received);
    }
}
~~~

Trong API thật, chữ ký nhận từ HTTP cần được decode bằng encoding đã quy định, giới hạn chiều dài và từ chối dạng không chuẩn. Không gọi `String.equals` trên chuỗi HMAC rồi cho rằng đã so sánh an toàn về timing.

**Lưu ý test fixture:** secret A/B trong bài là **secret giả, chỉ dùng trong test**. Không copy key production vào source code, snapshot test, CI output hoặc log lỗi. Kể cả trong test, avoid in secret in assertions/logs; chỉ so sánh kết quả boolean hoặc byte arrays trong memory.

## 7. Unit test trọng tâm: chỉ đổi secret, giữ canonical bytes

Đây là một ví dụ **JUnit Jupiter hoàn chỉnh ở mức kiểm tra mật mã và nonce**. Để giảm biến, nó sử dụng canonical bytes đã được cố định. Trong production, canonical builder và credential registry sẽ được triển khai trong các component riêng.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.Arrays;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;

class WrongSecretCoreTest {
    private static final byte[] A =
        "test-secret-A-2026".getBytes(StandardCharsets.UTF_8);
    private static final byte[] B =
        "test-secret-B-2026".getBytes(StandardCharsets.UTF_8);

    private static final byte[] CANONICAL = String.join("\n",
        "HMAC-REQUEST-V1",
        "POST",
        "/api/hmac/payments?currency=VND",
        "application/json",
        "partner-a",
        "partner-a-k4",
        "tenant-a",
        "2026-11-28T04:00:00Z",
        "2e0fabf6-0e06-4bbc-a3bd-d3f31cb4ee5a",
        "4c9b5e10f15d5b851780e64c4735225b87fef2ea5f4b60ab0d76f6bf9ef7b5ca"
    ).getBytes(StandardCharsets.UTF_8);

    // Đây là một fixture canonical cố định để kiểm tra
    // riêng cơ chế chọn secret/so sánh HMAC.
    private static final String KEY_ID = "partner-a-k4";

    static final class CountingNonceStore {
        final AtomicInteger calls = new AtomicInteger();
        boolean used;

        boolean claim() {
            calls.incrementAndGet();
            if (used) return false;
            used = true;
            return true;
        }
    }

    static final class FocusedVerifier {
        private final CountingNonceStore nonceStore;

        FocusedVerifier(CountingNonceStore store) {
            this.nonceStore = store;
        }

        boolean verify(
                String keyId,
                byte[] canonicalBytes,
                byte[] clientSignature) {

            // Server registry được fake ở đây:
            // chỉ K4 tồn tại và luôn lưu SECRET A.
            if (!KEY_ID.equals(keyId)) return false;
            byte[] expected =
                HmacTestCrypto.sign(A, canonicalBytes);

            // Nonce KHÔNG được claim trước signature check.
            if (!MessageDigest.isEqual(
                    expected, clientSignature)) {
                return false;
            }
            return nonceStore.claim();
        }
    }

    @Test
    void wrongSecretIsRejectedWithoutConsumingNonce() {
        CountingNonceStore nonce = new CountingNonceStore();
        FocusedVerifier verifier = new FocusedVerifier(nonce);

        byte[] wrongMac = HmacTestCrypto.sign(B, CANONICAL);
        byte[] correctMac = HmacTestCrypto.sign(A, CANONICAL);

        // Cùng key ID, cùng canonical bytes, chỉ đổi secret.
        assertFalse(Arrays.equals(wrongMac, correctMac));
        assertFalse(verifier.verify(
            KEY_ID, CANONICAL, wrongMac));

        // HMAC sai không được chạm replay store.
        assertEquals(0, nonce.calls.get());

        // Positive control: N chưa bị chiếm bởi wrong-secret.
        assertTrue(verifier.verify(
            KEY_ID, CANONICAL, correctMac));
        assertEquals(1, nonce.calls.get());

        // Replay của cùng evidence đúng vẫn bị chặn.
        assertFalse(verifier.verify(
            KEY_ID, CANONICAL, correctMac));
        assertEquals(2, nonce.calls.get());
    }

    @Test
    void correctSecretWithFreshStoreIsAccepted() {
        CountingNonceStore nonce = new CountingNonceStore();
        assertTrue(new FocusedVerifier(nonce).verify(
            KEY_ID, CANONICAL,
            HmacTestCrypto.sign(A, CANONICAL)));
        assertEquals(1, nonce.calls.get());
    }
}
~~~

**Phạm vi chính xác:** fixture này kiểm tra secret selection, MAC comparison và thứ tự claim nonce bằng một fake store. Nó **chưa** tự kiểm tra body SHA-256, timestamp window, credential ACTIVE/REVOKED, Redis atomicity giữa node, Spring Security hay HTTP. String SHA-256 ở fixture là một giá trị canonical cố định cho unit test, không nên coi là digest đã được chứng minh khớp body thực. Dùng integration test và vector chuẩn để kiểm tra các lớp còn thiếu.

Không cần dùng `Clock` trong test MAC-only ở trên vì timestamp đã nằm trong canonical fixture; nếu code verifier thực kiểm tra timestamp, hãy inject `Clock.fixed(...)` và giữ request trong cửa sổ. Không hardcode timestamp 2026 vào một test integration chạy về sau với đồng hồ hệ thống thực.

## 8. Negative control: wrong secret khác malformed signature

Có nhiều cách tạo một request không hợp lệ, nhưng chúng kiểm thử **những nhánh khác nhau**:

| Dữ liệu đưa vào | Điều cần kết luận | Thuộc wrong secret test chính? |
| --- | --- | --- |
| HMAC hợp lệ dưới secret B, key ID K4 → A | Server dùng đúng A và từ chối MAC của B | **Có** |
| Chữ ký ngẫu nhiên dài 32 bytes | MAC mismatch nói chung | Bổ sung, không thay thế |
| Chữ ký Base64 sai | Parser từ chối input | Không |
| Chữ ký thiếu | Missing credentials | Không |
| Key ID không tồn tại | Unknown credential | Không |
| Timestamp quá cũ | Freshness failure | Không |
| Nonce đã dùng | Replay failure | Không |
| Body khác so với body được ký | Integrity mismatch | Test khác |
| Proxy rewrite URI ngoài hợp đồng | Canonicalization mismatch | Test khác |
| K4 bị REVOKED | Credential state failure | Test khác |
| Secret manager timeout | Dependency unavailable | Test khác |

Kết quả HTTP `401` giống nhau **không** có nghĩa các nhánh trên tương đương. Dùng test fixtures có tên rõ, ví dụ `wrongSecretButCorrectKeyId`, `malformedBase64`, `wrongKeyId`, `signatureForDifferentBody`.

Khi server trả public response giống nhau để tránh enumeration oracle, dùng **test spy/counter hoặc internal outcome enum** trong môi trường test để phân biệt lý do, không làm lộ mã nội bộ trong response production.

## 9. Kiểm thử secret lookup: không fallback sang key khác

Trong key rotation, hệ thống có thể có:

| Credential | Secret trong registry | Status |
| --- | --- | --- |
| `partner-a-k3` | Secret K3 | ACTIVE tạm trong overlap |
| `partner-a-k4` | Secret K4 | ACTIVE |
| `partner-a-k2` | Secret K2 | REVOKED |

Khi request khai `X-Key-Id: partner-a-k4`, verifier phải chọn **chính xác K4**. Nếu client ký bằng secret K3 hoặc K2 mà vẫn khai K4, request phải bị từ chối. Verifier không nên “thử mọi secret của partner-a đến khi cái nào khớp”, vì điều đó có thể vô tình cho secret cũ hoặc revoked tiếp tục có hiệu lực.

Mã nguy hiểm:

~~~java
// SAI: cho phép request khai K4 nhưng ký bằng K3.
for (Credential candidate : registry.getAllForClient(clientId)) {
    if (verifyHmac(candidate.secret(), canonical, signature)) {
        return authenticated(clientId);
    }
}
~~~

Mã đúng về nguyên tắc:

~~~java
Credential credential = registry.findExact(keyId);
if (credential == null || !credential.isActive()) {
    throw new BadCredentialsException("authentication_failed");
}

byte[] expected = hmacSha256(
    credential.secret(), canonicalBytes);
if (!MessageDigest.isEqual(expected, signatureBytes)) {
    throw new BadCredentialsException("authentication_failed");
}

// Chỉ sau đó mới kiểm tra timestamp/nonce và tạo principal.
~~~

Trong code production, xử lý secret phải tránh log và không chia sẻ `Mac` mutable giữa threads; credential state phải đủ mới theo yêu cầu revocation.

### Test ma trận key selection

1. K4 + signature do K4 tạo → thành công khi nonce mới.
2. K4 + signature do K3 tạo → **401**, dù K3 vẫn ACTIVE.
3. K4 + signature do K2 REVOKED tạo → **401**, không fallback.
4. K2 + signature do K2 tạo → **401** vì key REVOKED.
5. K4 + signature do một client khác tạo → **401**.
6. K4 + signature do K4 tạo nhưng client trong signed header bị sửa → **401**.
7. K4 + secret bị rotate sau khi client ký → kết quả theo chính sách overlap/expiry được định nghĩa, không đoán.
8. K4 + revoked state trong registry vừa commit → xác minh từ mọi node phải tuân thủ cam kết freshness.

**Quan trọng:** test `wrong secret` và `revoked key` phải độc lập. Nếu K4 bị REVOKED, dù signature do K3 tạo cũng bị từ chối ngay ở bước state; test đó không chứng minh secret mismatch check.

## 10. JUnit test cho key rotation và client isolation

Một ca unit có thể inject registry fake trả đúng secret theo key ID và spy việc lookup:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

import java.nio.charset.StandardCharsets;
import java.util.Map;
import org.junit.jupiter.api.Test;

class WrongSecretLookupTest {

    interface CredentialRegistry {
        byte[] findSecretByExactKeyId(String keyId);
    }

    interface SignatureVerifier {
        boolean verify(
            String keyId, byte[] canonical, byte[] signature);
    }

    @Test
    void wrongSecretCannotSucceedViaAnotherKeyVersion() {
        byte[] secretK3 =
            "test-secret-K3".getBytes(StandardCharsets.UTF_8);
        byte[] secretK4 =
            "test-secret-K4".getBytes(StandardCharsets.UTF_8);
        byte[] canonical = "unit-canonical"
            .getBytes(StandardCharsets.UTF_8);
        byte[] signatureUsingK3 =
            HmacTestCrypto.sign(secretK3, canonical);

        CredentialRegistry registry =
            mock(CredentialRegistry.class);
        when(registry.findSecretByExactKeyId("partner-a-k4"))
            .thenReturn(secretK4);

        SignatureVerifier verifier = (keyId, bytes, sig) -> {
            byte[] selected =
                registry.findSecretByExactKeyId(keyId);
            if (selected == null) return false;
            return java.security.MessageDigest.isEqual(
                HmacTestCrypto.sign(selected, bytes), sig);
        };

        assertFalse(verifier.verify(
            "partner-a-k4", canonical, signatureUsingK3));
        verify(registry, times(1))
            .findSecretByExactKeyId("partner-a-k4");
        verifyNoMoreInteractions(registry);
    }
}
~~~

Đây là test minh họa **lookup theo đúng key ID**, không thay thế test repository thực, trạng thái ACTIVE/REVOKED hay logic Spring Security. Test secret K3/K4 chỉ được sử dụng cho fixture; không hiển thị secret thực tế khi assertion fail.

Một phép thử khác cần đặt cùng signature B dưới `clientId` khác và giữ `keyId` không đổi; nếu MAC sai nhưng server vẫn tạo principal của client B, có nguy cơ **identity confusion**. Key ID phải gắn với client/tenant đã biết trong registry, không lấy owner identity từ header tự khai.

## 11. Wrong secret test qua Spring Security 6 Servlet

Trong Spring MVC, một integration test nên chạy qua **SecurityFilterChain thật**:

~~~mermaid
flowchart TD
    A["MockMvc HTTP request với keyId=K4"] --> B["HmacAuthenticationFilter"]
    B --> C["Parser + canonical request"]
    C --> D["AuthenticationManager"]
    D --> E["HmacAuthenticationProvider"]
    E --> F["Registry K4 trả secret A"]
    F --> G{"Signature do secret B tạo?"}
    G -->|Mismatch| H["AuthenticationException"]
    H --> I["AuthenticationEntryPoint"]
    I --> J["401 generic problem response"]
    J --> K["Không controller, không claim nonce"]
~~~

Dùng `@SpringBootTest` + `@AutoConfigureMockMvc` hoặc một integration fixture có Spring Security filter registration thực. Không chỉ gọi controller trực tiếp hoặc dùng `MockMvcBuilders.standaloneSetup` không gắn security chain rồi kết luận HMAC filter hoạt động.

### Một test khung MockMvc

~~~java
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.*;

import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet
    .AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class HmacWrongSecretMvcIT {

    @Autowired MockMvc mvc;
    @Autowired IndependentTestSigner signer;

    @Test
    void wrongSecretReturns401() throws Exception {
        String body = "{\"paymentId\":\"pay-101\",\"amount\":250000}";
        String timestamp = "2026-11-28T04:00:00Z";
        String nonce = "nonce-mvc-wrong-secret-001";

        // signer tạo chữ ký theo contract trên chính bytes
        // của request, nhưng cố ý dùng secret B.
        String signature = signer.signWithWrongSecret(
            "POST", "/api/hmac/payments?currency=VND",
            "application/json",
            "partner-a", "partner-a-k4", "tenant-a",
            timestamp, nonce,
            body.getBytes(StandardCharsets.UTF_8));

        mvc.perform(post("/api/hmac/payments")
                .queryParam("currency", "VND")
                .contentType(MediaType.APPLICATION_JSON)
                .header("X-Client-Id", "partner-a")
                .header("X-Key-Id", "partner-a-k4")
                .header("X-Tenant-Id", "tenant-a")
                .header("X-Timestamp", timestamp)
                .header("X-Nonce", nonce)
                .header("X-Signature", signature)
                .content(body))
            .andExpect(status().isUnauthorized())
            .andExpect(header().string(
                "Cache-Control", "no-store"))
            .andExpect(jsonPath("$.code").value(
                "AUTHENTICATION_FAILED"));
    }
}
~~~

`IndependentTestSigner` là fixture dự án phải hiện thực; không phải class có sẵn của Spring. Test dùng timestamp cố định **chỉ chạy đúng khi inject `Clock.fixed` tại verifier** hoặc chuyển timestamp sang thời điểm hợp lệ khi chạy. Dự án cần cài registry K4 → secret A, client/tenant ACTIVE và nonce store sạch. Nếu app trả response format khác, assertion phải theo **hợp đồng API đã chốt**, không ép cứng JSON example.

Một test thành công tương ứng phải dùng **cùng test signer** với secret A và dữ liệu cùng cấu trúc. Sau test wrong secret, cần assert nonce store **chưa có N**, mock/spied `PaymentService` **không được gọi**, không có DB write và không có authenticated principal.

**Không** chỉ assert `401`: request có thể bị trả 401 do timestamp hết hạn, filter thiếu cấu hình, nonce trùng, hoặc signer ký sai URI.

## 12. Khi nào và bằng cách nào kiểm tra side effect?

HMAC wrong secret là thất bại ở **authentication**. Nó phải bị chặn **trước** các hành động nghiệp vụ:

- Không gọi controller handler cần authentication.
- Không ghi vào DB, không phát event qua queue, không gửi email/thanh toán.
- Không mở truy vấn dữ liệu thuộc tenant được bảo vệ.
- Không tạo `SecurityContext` authenticated hoặc reactive principal cho request đó.
- Không claim nonce khi MAC không hợp lệ.
- Không ghi secret hoặc expected HMAC vào log/audit.

Test có thể dùng một spy service:

~~~java
// Ví dụ assertion với Mockito, trong test đã inject spy
// vào service thật hoặc test configuration:
verify(paymentService, never()).createPayment(any());
verifyNoInteractions(paymentEventPublisher);

// Với test DB: assert row count hoặc trạng thái giao dịch
// không thay đổi trước/sau request sai secret.
~~~

Một điểm cần cẩn trọng: authentication filter có thể **tra credential registry** để lấy secret, nên `verifyNoInteractions(registry)` là assertion sai. Thứ không được gọi là **business path và replay claim** trước khi MAC đúng. Nếu hệ thống cần đọc tenant policy ở authentication stage, phân biệt read-only lookup bắt buộc với side effect trái phép.

Không chỉ dựa trên HTTP status để chứng minh không có side effect; phải kiểm chứng bằng mock/spy, storage fixture hoặc audit/event capture.

## 13. Thứ tự nonce: test chống nonce poisoning

Nonce nên được claim **sau khi MAC hợp lệ**. Nếu server claim nonce trước phép so sánh chữ ký, attacker có thể đưa một nonce dự đoán/quan sát được với signature sai để chiếm slot, làm request hợp lệ sau đó bị từ chối replay.

Kiểm thử quan trọng:

~~~text
Bước 1: Replay store chưa có nonce N.
Bước 2: Gửi request R có key K4, timestamp hợp lệ,
        nonce N, canonical bytes C, signature = HMAC(B,C).
Kỳ vọng: authentication FAIL, replay store chưa ghi N.
Bước 3: Gửi request cũng có K4, N, C nhưng signature
        = HMAC(A,C) (server secret đúng).
Kỳ vọng: authentication PASS, atomic claim N thành công.
Bước 4: Gửi lại request đã PASS ở bước 3.
Kỳ vọng: authentication FAIL do replay.
~~~

**Đừng chạy bước 3 trước bước 2 trên cùng replay store** rồi suy luận server chặn wrong secret. Nếu nonce đã được dùng trước, một verifier kiểm tra replay sớm cũng có thể trả 401 trong cả hai trường hợp và che lỗi thứ tự.

### Ngữ nghĩa HTTP khi nonce đã dùng

Wrong secret và replay có thể đều trả public `401 AUTHENTICATION_FAILED`, nhưng nên có **mã nguyên nhân nội bộ** khác nhau: `SIGNATURE_MISMATCH` và `REPLAY_DETECTED`. Không công khai các mã này cho người chưa xác thực nếu tạo credential enumeration oracle.

Với backend phân tán, mock replay store chỉ kiểm tra thứ tự; cần E2E với kho nguyên tử dùng chung để chứng minh một nonce không được nhận hai lần qua nhiều gateway/instance.

## 14. Error semantics và tránh tiết lộ secret

Một hợp đồng API HMAC có thể trả response:

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
  "requestId": "req-741a3"
}
~~~

Đây là ví dụ Problem Details với trường `code`, `requestId` mở rộng. Header `WWW-Authenticate: HMAC realm="api"` chỉ được dùng khi hệ thống đã **định nghĩa và công bố scheme HMAC/challenge này**; không phải challenge do Spring Security tự cung cấp.

### Những gì không được lộ

Không trả trong HTTP response hoặc log có thể truy cập công khai:

- Secret A/B hay secret version đang ACTIVE.
- Expected MAC, calculated HMAC, full signature.
- Full canonical request nếu chứa query/body nhạy cảm.
- “Key K4 exists, but secret mismatched” hoặc “key revoked” nếu cần giảm enumeration.
- Stack trace, credential store path, Redis connection string.
- Target tenant hay resource identity nhạy cảm khi chưa có quyền.

Nên dùng cùng public code `AUTHENTICATION_FAILED` cho signature mismatch, key không tồn tại/revoked và replay, trong khi hệ thống giám sát/audit nội bộ ghi một `reason` enum giới hạn.

### 401 không giống 403 hay 503

| Trường hợp | Bản chất | HTTP gợi ý |
| --- | --- | --- |
| K4 tồn tại ACTIVE nhưng ký bằng B thay A | Authentication failed | 401 |
| K4 không tồn tại | Authentication failed | 401 công khai tương tự |
| HMAC đúng nhưng nonce đã dùng | Authentication failed (replay) | 401 |
| HMAC đúng nhưng thiếu quyền tenant B | Authorization denied | 403/404 theo policy |
| Secret manager timeout, không xác định secret | Dependency unavailable | 503 theo policy, fail closed |
| Body vượt giới hạn capture | Chưa hoàn tất authentication | 413 |
| Header/base64 malformed | Input/authentication failed | 400 hoặc 401 theo contract |

Không biến secret manager unavailable thành “wrong secret”: hai trường hợp có hành động vận hành khác nhau. Đặc biệt, khi registry/vault lỗi, hệ thống **không được fail open** bằng default secret hoặc bypass signature.

## 15. Spring WebFlux: wrong secret test qua reactive chain

Với Spring WebFlux, request body là `Flux<DataBuffer>`; authentication dùng `ReactiveAuthenticationManager`, `AuthenticationWebFilter` hoặc custom `WebFilter` trong `SecurityWebFilterChain`. Principal đi qua **Reactor Context** chứ không gắn bằng thread-local Servlet.

Khi test wrong secret:

1. Dùng `WebTestClient` chạy cùng reactive filter chain thật.
2. Signer tạo MAC bằng B cho key K4 trong registry đang giữ A.
3. Nếu body được ký, capture và verify trên đúng raw bytes, giới hạn byte.
4. Đảm bảo body có thể replay cho handler **chỉ sau** khi authentication thành công.
5. Kỳ vọng 401, không gọi controller và **không claim nonce**.
6. Chạy thêm positive control bằng A, nonce mới và cùng contract.

Khung kiểm thử:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive
    .AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class WrongSecretWebFluxIT {
    @Autowired WebTestClient client;
    @Autowired IndependentTestSigner signer;

    @Test
    void rejectsSignatureFromWrongSecret() {
        String payload = "{\"paymentId\":\"pay-101\"}";
        String timestamp = "2026-11-28T04:00:00Z";
        String nonce = "nonce-webflux-wrong-001";

        String signature = signer.signWithWrongSecret(
            "POST", "/api/hmac/payments",
            "application/json",
            "partner-a", "partner-a-k4", "tenant-a",
            timestamp, nonce,
            payload.getBytes(java.nio.charset.StandardCharsets.UTF_8));

        client.post()
            .uri("/api/hmac/payments")
            .contentType(MediaType.APPLICATION_JSON)
            .header("X-Client-Id", "partner-a")
            .header("X-Key-Id", "partner-a-k4")
            .header("X-Tenant-Id", "tenant-a")
            .header("X-Timestamp", timestamp)
            .header("X-Nonce", nonce)
            .header("X-Signature", signature)
            .bodyValue(payload)
            .exchange()
            .expectStatus().isUnauthorized();
    }
}
~~~

Như ví dụ MVC, cần fixture signer do dự án xây, injected Clock/registry/nonce và assertions **no side effects**. Không gọi `block()` trên event loop của request. Nếu reactive filter bắt `AuthenticationException`, phải phân loại chính xác mà không bắt lỗi controller downstream rồi đổi thành 401.

Đặc biệt, `DataBuffer` có thể dùng pooled/direct memory; test error/cancel cần đảm bảo release đúng. Một wrong-secret request lớn vẫn phải chịu **body-size/concurrency limits**; không giữ body không giới hạn chỉ để xác minh thất bại.

## 16. Gateway và proxy: phân biệt wrong secret với canonical mismatch

Một request do client ký ở đường:

~~~text
External: POST /public/v1/payments?currency=VND
Internal: POST /internal/payments?currency=VND
~~~

Nếu backend ký/verify theo internal target nhưng signer dùng external target, MAC sai **dù client dùng secret đúng**. Khi thử wrong secret, kiểu sai lệch này gây **false confidence**: cả A và B đều fail nên không thể biết có thực sự bảo vệ secret không.

### Quy trình kiểm tra qua proxy

1. Xác định **điểm verify HMAC**: gateway hay backend.
2. Chốt canonical target: external path/query hay internal path/query theo contract.
3. Với secret A, request hợp lệ phải **thành công trước qua cùng tuyến proxy**.
4. Với cùng request nhưng ký B, phải **bị từ chối** tại đúng verifier.
5. Test cả duplicate signed headers, header normalization, `X-Original-URI` spoofing và gzip/body transformation.
6. Kiểm chứng backend không bị gọi nếu gateway đã từ chối và không có đường direct access bypass gateway.
7. Không tin `X-Authenticated-Client` thuần văn bản hoặc forwarded header tự khai như bằng chứng HMAC hợp lệ.

### Hai kiến trúc kiểm thử khác nhau

**Gateway verify HMAC:** wrong-secret response phải được quyết định ở gateway. Backend nhận identity qua mTLS/signed assertion đã kiểm tra issuer, audience, expiry, method/target/body binding. Test cần khẳng định gateway **không mint assertion** khi chữ ký dùng secret B.

**Backend verify HMAC:** gateway chỉ forward theo hợp đồng; wrong-secret phải bị backend từ chối. Test cần bảo toàn các signed bytes qua proxy và kiểm tra request không bị rewrite ngoài contract.

Nếu một proxy trước verifier có request body buffering, measurement latency sẽ thay đổi, nhưng kết luận bảo mật không được thay. Header `X-Original-URI` từ client không phải chứng cứ đáng tin nếu chưa được gateway làm sạch.

## 17. Multi-tenant: wrong secret không được tạo quyền

HMAC xác thực **credential/client**. Một client có thể ký request hợp lệ nhưng không được phép truy cập mọi tenant. Hai lớp kiểm thử cần độc lập:

**Authentication negative:** K4 thuộc `partner-a`, server secret A; signature tạo từ B. Request phải bị 401 **trước** authorization, không tạo principal hay truy vấn dữ liệu tenant.

**Authorization negative:** K4 với secret A và nonce mới, nhưng target tenant B không có delegated grant. HMAC có thể **hợp lệ**, song policy phải từ chối 403/404 và không rò dữ liệu B.

Không dùng wrong-secret test để chứng minh tenant isolation; nó chưa chạy tới policy. Một hệ thống có thể từ chối MAC sai đúng cách nhưng vẫn có lỗi IDOR cho client được xác thực.

### Bảo vệ client identity

Key ID/credential record phải được registry ánh xạ đến principal và owner tenant. Đừng lấy `X-Client-Id` hoặc `X-Tenant-Id` từ request làm danh tính đã xác thực trước khi HMAC đúng. Ngay cả khi header tenant đã được HMAC ký, điều đó chỉ bảo vệ **tính toàn vẹn claim**, không cấp quyền tenant.

Trong test, sai secret **không được** tạo `Authentication` có authorities như `ROLE_USER` hay `CREATE_PAYMENT` cho principal giả. Kiểm tra nguyên nhân bằng spy security context trong test harness, không cấp quyền mặc định trên thất bại.

## 18. Test secret manager và lỗi hạ tầng riêng

Nếu secret manager, credential registry hoặc replay store không khả dụng, verifier không thể kết luận chữ ký đã dùng secret sai. Đó là **lỗi hạ tầng xác thực** hoặc kết quả không xác định, không phải wrong-secret evidence.

| Tình huống | Phản hồi hợp lý | Kiểm tra |
| --- | --- | --- |
| Registry trả đúng K4→A; signature dưới B | 401 | Wrong secret confirmed |
| Registry trả K4 không tồn tại | 401 | Unknown key |
| Registry timeout không trả key | 503 theo hợp đồng | Fail closed, không fallback |
| Secret manager trả lỗi 5xx | 503 theo hợp đồng | Không dùng secret mặc định |
| Replay store lỗi **sau MAC đúng** | 503 theo hợp đồng | Không chấp nhận khi thiếu anti-replay |
| Replay store không được gọi vì MAC sai | 401 | No nonce poisoning |
| Cache ACTIVE nhưng key đã REVOKED | Phải từ chối theo freshness contract | Không suy từ cache cũ |
| Key K4 lookup nhầm secret K3 | 401 với MAC K4 đúng hoặc fail test positive | Phát hiện lookup bug |

Không cài một test fixture khiến `registry.getSecret()` luôn ném exception rồi xem `401` là pass. Điều đó kiểm tra failure mapping chứ không kiểm tra secret mismatch.

Test có thể sử dụng fault injection để khiến vault/Redis chậm hoặc lỗi; khi đó phải assert fail closed và alert, **không** cho request đi tiếp vì thiếu thông tin.

## 19. Property-based và mutation testing cho wrong secret

Ngoài hai secret A/B cố định, có thể tạo nhiều cặp secret khác nhau **trong môi trường test**:

- Với một canonical bytes cố định, `HMAC(secretA, canonical)` phải verify khi registry giữ A.
- Với secret B khác A, HMAC của B gần như chắc chắn khác HMAC của A (khả năng collision cực nhỏ), nên phải bị từ chối.
- Thay từng bit của secret A để tạo secret B, giữ mọi dữ liệu khác cố định.
- Thay chiều dài secret 16/32/64 bytes trong test; server không được giả định một độ dài cứng không đúng contract.
- Với các bytes chứa `0x00` hoặc giá trị ngoài UTF-8, đảm bảo secret được xử lý như bytes, không qua `String.trim()`.
- Thử Base64url vs Base64 standard theo đúng phiên bản contract; sai encoding phải bị parser từ chối, không fallback thuật toán tùy tiện.

Những test sau **không** nên tạo secret từ môi trường production hoặc in raw key vào console. Có thể dùng `SecureRandom` cho dữ liệu test nhưng để tái hiện lỗi, nên lưu seed test trong CI artifact hoặc dùng vector cố định **không nhạy cảm**.

### Mutation testing đáng giá

Nếu cố ý sửa verifier thành:

~~~java
// Mutation lỗi: bỏ qua signature verification.
boolean matches = true;
~~~

thì wrong-secret test phải **FAIL**, vì request dùng B bị chấp nhận. Nếu sửa thứ tự thành:

~~~java
// Mutation lỗi: claim nonce trước MAC compare.
replayStore.claim(keyId, nonce);
boolean matches =
    MessageDigest.isEqual(expectedMac, providedMac);
~~~

thì test `wrong secret must not consume nonce` phải **FAIL**. Đây là cách kiểm tra test thực sự bắt được lỗi nguy hiểm chứ không chỉ assert status.

Các mutation khác cần bị test phát hiện: luôn chọn “default secret”, thử toàn bộ old key, bỏ qua credential status, bỏ qua nonce/timestamp hoặc tạo authenticated principal dù signature mismatch.

## 20. Ma trận kiểm thử Wrong secret mở rộng

| Test ID | Thiết lập | Kết quả và assertion quan trọng |
| --- | --- | --- |
| WS-01 | K4 ACTIVE, ký bằng A | Positive: authentication pass |
| WS-02 | K4 ACTIVE, ký bằng B | **401; MAC mismatch; không nghiệp vụ** |
| WS-03 | K4 ACTIVE, ký B, N chưa dùng | Không claim nonce |
| WS-04 | Sau WS-03, ký A dùng chính N | Pass; chứng minh không nonce poisoning |
| WS-05 | Gửi lại request ký A cùng N | Replay rejected |
| WS-06 | K4 nhưng ký bằng secret K3 ACTIVE | Fail; không fallback old key |
| WS-07 | K4 nhưng ký bằng secret K2 REVOKED | Fail; không fallback revoked |
| WS-08 | K2 REVOKED và ký đúng K2 | Fail vì credential state |
| WS-09 | Sai secret nhưng key ID không tồn tại | Test riêng unknown key; public response chung |
| WS-10 | Sai secret, timestamp ngoài window | Test bị nhiễu; phải sửa fixture trước |
| WS-11 | Sai secret, signed body đúng raw bytes | MAC mismatch được cô lập |
| WS-12 | Secret đúng nhưng body thay một byte | Integrity mismatch riêng |
| WS-13 | Secret đúng nhưng JSON whitespace khác | Raw-body contract test |
| WS-14 | Secret đúng nhưng URI path rewrite | Canonicalization contract test |
| WS-15 | Secret sai với duplicate key/signature headers | Header parser từ chối ambiguity |
| WS-16 | Secret sai và signature malformed Base64 | Parser failure, không gán nhầm MAC mismatch |
| WS-17 | Sai secret trong MVC SecurityFilterChain | 401 via entry point; controller không chạy |
| WS-18 | Sai secret trong WebFlux SecurityWebFilterChain | 401; no principal, no side effect |
| WS-19 | Sai secret qua public API gateway | Gateway/backend reject tại đúng điểm verify |
| WS-20 | Ký A qua chính tuyến gateway | Positive control đi qua proxy |
| WS-21 | Gateway strip client-supplied auth assertion | Không được bypass HMAC |
| WS-22 | Call trực tiếp backend có header giả | Từ chối theo trust policy |
| WS-23 | Wrong secret khi registry timeout | Phân biệt dependency unavailable, không pass nhầm |
| WS-24 | Wrong secret sau cache key rotation | Chọn secret K4 đúng version |
| WS-25 | Wrong secret trên 2 instance | Từ chối nhất quán |
| WS-26 | Nhiều concurrent requests sai secret | Không ghi nonce; không tạo principal |
| WS-27 | Sai secret + target tenant B | Không được đi đến authorization/data B |
| WS-28 | Đúng secret + target tenant B thiếu grant | 403/404 riêng; authentication pass |
| WS-29 | Response sai secret chứa expected HMAC | Test **FAIL**, rò thông tin |
| WS-30 | Security logs chứa raw secret/signature | Test **FAIL**, rò thông tin |
| WS-31 | Filter được đăng ký hai lần | Phát hiện double authentication/nonce claim |
| WS-32 | Request body vượt giới hạn | 413/not evaluated, không quy sai secret |
| WS-33 | Bị disable HMAC filter | Positive/negative probes phải phát hiện bypass |
| WS-34 | Secret B trùng A do fixture cấu hình lỗi | Precondition assert phải FAIL |
| WS-35 | Mọi request đều trả 401 do routing lỗi | Positive control phải FAIL |
| WS-36 | Auth service trả 503 khi secret store unavailable | Fail closed, không lộ secret |

Ma trận giúp tách **core wrong secret** (WS-01 đến WS-04) khỏi các nguyên nhân dễ nhầm (timestamp, replay, parser), triển khai framework (MVC/WebFlux), gateway và vận hành. Không cần chạy toàn bộ ma trận ở mọi unit test; phân bổ theo tầng unit, integration, contract và E2E.

## 21. Đo đạc, audit và tránh test tạo oracle

Metric nội bộ có thể phân loại:

~~~text
hmac.authentication.attempts{result="valid",reason="none"}
hmac.authentication.attempts{result="invalid",reason="signature"}
hmac.authentication.attempts{result="invalid",reason="credential"}
hmac.authentication.attempts{result="invalid",reason="replay"}
hmac.authentication.attempts{result="unavailable",reason="dependency"}
~~~

Không đưa `key_id`, `client_id`, `tenant_id`, `nonce`, raw URI, full signature hoặc exception message thành **metric labels**: cardinality cao và có nguy cơ lộ dữ liệu. Trong audit nội bộ có quyền truy cập, có thể ghi correlation ID, verifier instance, contract version, key revision và internal reason được kiểm soát, nhưng không ghi shared secret, expected MAC hoặc raw body nhạy cảm.

### Timing là một phần của bề mặt thông tin

Dù trả cùng body 401, thời gian xử lý cho `KEY_NOT_FOUND` và `SIGNATURE_MISMATCH` có thể khác do registry lookup/crypto. Hãy kiểm tra theo threat model, đặt rate limiting, thống nhất các nhánh xử lý thích hợp và tránh đưa lý do chi tiết ra client. Không thể khẳng định toàn bộ đường HTTP/network/database “constant-time” chỉ vì dùng `MessageDigest.isEqual`.

### Không load test bằng secret thật

Dùng credential test với quyền tối thiểu, route sandbox và isolated test stores. Một bộ test HMAC sai không cần gửi request vào cổng payment production rồi kiểm chứng qua giao dịch thật. E2E security probes phải có phạm vi được cấp phép, rate limit phù hợp và không phá dữ liệu.

## 22. Bài tập thực hành: test PASS nhưng vẫn có lỗ hổng

Nhóm phát triển viết:

~~~java
@Test
void wrongSecretIsRejected() throws Exception {
    mockMvc.perform(post("/api/hmac/payments")
            .header("X-Key-Id", "unknown-key")
            .header("X-Signature", "not-base64")
            .content("{\"amount\":123}"))
        .andExpect(status().isUnauthorized());
}
~~~

Test PASS, và nhóm kết luận “HMAC verifier đã từ chối wrong secret”. Nhưng thực tế có thể hệ thống chỉ phát hiện unknown key/malformed signature trước khi tính HMAC. Một bug bỏ qua MAC comparison vẫn có thể lọt qua.

Hãy trả lời:

1. Vì sao test trên không kiểm tra wrong secret?
2. Cần thay key ID và credential registry thành fixture nào?
3. Cần tạo signature B như thế nào để nó hợp lệ về format nhưng sai secret?
4. Timestamp, nonce, URI/body và signed headers phải kiểm soát ra sao?
5. Positive control cần làm gì để tránh “always-401 false positive”?
6. Làm sao assert wrong-secret không consume nonce?
7. Nếu server thử K3 khi K4 sai, test nào phải phát hiện?
8. 401, 403 và 503 trong những trường hợp nào?
9. Cần test qua Spring Security filter chain và gateway thế nào?
10. Những log/response nào không được tiết lộ cho client?

**Gợi ý:** đăng ký K4 → A ở registry, dùng B để ký **cùng canonical bytes** có timestamp hợp lệ/nonce mới, và kiểm tra 401 + no business + no nonce claim. Sau đó ký đúng A bằng chính nonce N trên state sạch để chứng minh secret mismatch thật sự là nguyên nhân. Bổ sung test key version, canonical proxy rewrite, masked errors và 503 fail-closed.

## 23. Checklist trước khi chấp nhận Wrong secret test

- [ ] Đúng phạm vi `HMAC request authentication`; test gọi verifier thực chứ không chỉ controller standalone.
- [ ] Có key ID tồn tại, ACTIVE và ánh xạ đến **secret A** từ registry test.
- [ ] Wrong-secret signer dùng secret B **khác A**, test assert hai MAC khác nhau.
- [ ] Key ID, client, tenant, method, URI/query, signed headers, raw body, timestamp và nonce được kiểm soát.
- [ ] Timestamp nằm trong cửa sổ; unit test dùng `Clock.fixed`, integration test có clock/test fixture hợp lệ.
- [ ] Nonce chưa được claim trước negative test; replay store độc lập hoặc reset đúng cách.
- [ ] Chữ ký B có format/độ dài hợp lệ; không dùng random bytes hoặc malformed Base64 thay thế.
- [ ] Negative request bị từ chối tại **bước MAC verification** và public status/code đúng hợp đồng.
- [ ] Không có authenticated principal, business side effect hoặc cross-tenant access.
- [ ] Nonce **không** bị ghi khi signature sai; positive request bằng A với cùng N đi tiếp được.
- [ ] Positive control dùng đúng secret A chạy qua cùng verifier/route để tránh always-reject test.
- [ ] Không fallback secret của K3/K2 hoặc secret mặc định khi K4 mismatch.
- [ ] Key rotation, revoked key và client disabled có test riêng, không làm nhiễu wrong-secret core test.
- [ ] Unknown key, malformed header, expired timestamp, replay và body tampering có test riêng.
- [ ] Với MVC, `MockMvc` đi qua `SecurityFilterChain` và entry point; kiểm tra 401, no controller.
- [ ] Với WebFlux, `WebTestClient` đi qua reactive security chain; kiểm tra context, pooled-body cleanup.
- [ ] Với gateway, biết điểm verify và canonical external/internal URI; test positive A và negative B cùng tuyến.
- [ ] Gateway không cấp internal assertion cho request dùng B; backend không tin header giả mạo.
- [ ] Lỗi vault/registry/replay store là dependency failure, không tự coi là wrong secret hoặc fail open.
- [ ] Public response/log không có shared secret, expected MAC, stack trace hay canonical bytes nhạy cảm.
- [ ] Meter labels có danh sách hữu hạn; reason nội bộ không bị phơi qua HTTP.
- [ ] Test vectors độc lập chứng minh canonicalization/encoding; không chỉ dùng một helper chung cho signer và verifier.
- [ ] Có coverage concurrency, multi-instance, key rotation/revocation, nonce poisoning và tenant authorization riêng.
- [ ] CI dùng credential thử nghiệm, không đọc secret production; mọi test có thể chạy lặp lại không làm bẩn nonce store.

**Wrong secret test tốt không chỉ cần một phản hồi 401.** Nó phải chứng minh server dùng **đúng secret gắn với đúng key ID**, từ chối chữ ký do secret khác tạo trên **chính xác cùng canonical bytes**, không claim nonce trước khi MAC hợp lệ, không tạo principal hay side effect và không âm thầm fallback qua key rotation/gateway. Khi thêm positive control, test vector độc lập và kiểm tra đầy đủ trust boundary, kết quả mới có giá trị bảo vệ hệ thống HMAC trong thực tế.
