# Algorithm allowlist trong xác thực HTTP request bằng HMAC

## 1. Bối cảnh và mục tiêu

Trong module `SECURITY_AUTHENTICATION_HMAC_REQUEST_AUTHENTICATION`, client ký HTTP request bằng **HMAC với shared secret**, còn server xác minh trên cùng một **canonical request**. Chuỗi ký được xây dựng từ các thành phần đã thỏa thuận, chẳng hạn HTTP method, URI, header được chọn, timestamp, nonce và body digest. Timestamp và nonce giúp giới hạn replay; bước phân quyền vẫn diễn ra riêng sau khi danh tính client được xác thực.

Khi hệ thống phải hỗ trợ nhiều phiên bản giao thức, nhiều nhóm client hoặc di chuyển từ thuật toán HMAC này sang thuật toán HMAC khác, câu hỏi xuất hiện: **server cho phép thuật toán nào, theo chính sách nào, và ai được quyền quyết định?**

**Algorithm allowlist** là danh sách hữu hạn các **định danh thuật toán được server cho phép rõ ràng** trong một ngữ cảnh xác thực. Chỉ thuật toán nằm trong danh sách mới được dùng để xác minh chữ ký. Đối với HMAC request authentication, allowlist cần đi cùng chính sách trên từng credential/key; việc một thuật toán được hỗ trợ toàn hệ thống không đồng nghĩa mọi client được tự chọn thuật toán đó cho bất kỳ key nào.

Sau bài học, người học có thể:

- Phân biệt tên thuật toán trên wire với tên thuật toán dùng trong Java Cryptography Architecture (JCA).
- Thiết kế allowlist rõ ràng, xử lý mặc định theo hướng **từ chối**.
- Ngăn algorithm confusion và downgrade bằng **ràng buộc thuật toán với keyId/credential** và phiên bản hợp đồng ký.
- Viết verifier Java 17 và test JUnit 5 cho thuật toán hợp lệ, thuật toán lạ, phiên bản sai, chữ ký sai và key rotation.
- Kiểm tra tác động của proxy/gateway, timestamp/nonce, log và authorization đối với chính sách thuật toán.

> Bài này tập trung vào **kiểm soát thuật toán ký HMAC ở tầng HTTP**. Không giả định rằng mọi giao thức HMAC đều sử dụng cùng tên header, cách canonical hóa hoặc cách encode signature. Các giá trị header dưới đây là **hợp đồng minh họa** cần được hai phía thống nhất trước khi triển khai.

## 2. Thuật toán nào nên được phép?

Một allowlist mẫu cho một hệ thống hiện đại có thể như sau:

| Định danh giao thức | Tên JCA trong Java | Độ dài tag HMAC toàn phần | Vai trò |
|---|---|---:|---|
| `HMAC-SHA256` | `HmacSHA256` | 32 byte | Thuật toán mặc định trong phiên bản này |
| `HMAC-SHA512` | `HmacSHA512` | 64 byte | Thuật toán được hỗ trợ cho credential đã đăng ký |
| `HMAC-SHA1` | `HmacSHA1` | 20 byte | Không cho phép trong chính sách ví dụ |
| `MD5`, `SHA-256`, `none` | Không phải lựa chọn HMAC hợp lệ theo hợp đồng này | — | Từ chối |
| Giá trị không biết, viết sai chữ hoa/thường, có khoảng trắng | Không ánh xạ | — | Từ chối |

Không nên hiểu rằng một HMAC dùng SHA-1 tự động có thể bị giả mạo chỉ vì SHA-1 có vấn đề collision trong chữ ký số/hash thông thường. **Lý do từ chối `HMAC-SHA1` ở đây là chính sách giảm phụ thuộc thuật toán cũ và đơn giản hóa giao thức**, thay vì tuyên bố một tấn công cụ thể đã phá được mọi cách dùng HMAC-SHA1.

Tương tự, HMAC-SHA512 không tự động làm hệ thống an toàn hơn nếu secret yếu, canonical request sai, so sánh tag không an toàn hoặc server bỏ qua replay protection. Trong nhiều hệ thống, **chỉ cho phép `HMAC-SHA256`** là chính sách vừa đủ và dễ vận hành nhất. Nên thêm thuật toán khác khi có yêu cầu tương thích hoặc lộ trình chuyển đổi cụ thể.

### Hai lớp policy khác nhau

1. **Global allowlist**: tập định danh thuật toán được implementation hiểu và chấp nhận về mặt chính sách, ví dụ `{HMAC-SHA256, HMAC-SHA512}`.
2. **Credential policy**: với một `keyId`/client cụ thể, server lưu **thuật toán duy nhất đang được cấp quyền** cho credential đó (ví dụ `key-2026-b` chỉ dùng `HMAC-SHA512`).

Điều kiện chấp nhận phải thỏa cả hai:

\[
\text{allowed}(request) =
\text{algorithm} \in \text{globalAllowlist}
\land
\text{algorithm} = \text{credential.allowedAlgorithm}
\]

Đồng thời phải xác minh chữ ký, thời gian, nonce và quyền truy cập theo các bước riêng. Với các API cần nhiều thuật toán trên cùng client, cấp **nhiều credential/keyId khác nhau**, mỗi credential có policy cố định, thay vì cho phép caller chuyển thuật toán tùy ý trên cùng shared secret.

## 3. Những kiểu lỗi mà allowlist cần chặn

### 3.1. Chấp nhận tên thuật toán từ header một cách trực tiếp

Mẫu không an toàn:

~~~java
// KHÔNG DÙNG: header không đáng tin cậy quyết định thuật toán JCA.
String requestedAlgorithm = request.getHeader("X-HMAC-Algorithm");
Mac mac = Mac.getInstance(requestedAlgorithm);
mac.init(new SecretKeySpec(secret, requestedAlgorithm));
~~~

Ở đây caller điều khiển chuỗi truyền trực tiếp vào crypto provider. Behavior có thể phụ thuộc tên alias/thuật toán mà provider hỗ trợ; còn chính sách của ứng dụng không được xác minh. Không nên có fallback kiểu `Mac.getInstance("HmacSHA256")` khi header không biết: fallback khiến hai phía có thể hiểu khác nhau và làm khó nhận diện migration sai.

Thay vào đó, **ánh xạ chính xác** định danh public sang tên JCA từ bản ghi do server kiểm soát:

~~~java
Map<String, String> allowed = Map.of(
        "HMAC-SHA256", "HmacSHA256",
        "HMAC-SHA512", "HmacSHA512"
);

String jcaName = allowed.get(untrustedHeader);
if (jcaName == null) {
    throw new InvalidSignaturePolicyException();
}
// Chỉ sau khi kiểm tra credential policy mới tạo Mac với jcaName.
~~~

Không cần chấp nhận `hmac-sha256`, `HMAC-SHA256 `, `sha256` hay alias của provider chỉ vì chúng có vẻ tương đương. Nếu giao thức muốn cho phép alias, chúng phải được chỉ định **có chủ đích**, canonical hóa thống nhất, và được ký như một giá trị cụ thể.

### 3.2. Thuật toán có trong allowlist nhưng sai credential

Một hệ thống cho phép cả HMAC-SHA256 và HMAC-SHA512 vẫn có thể sai nếu làm theo yêu cầu của client:

~~~text
X-HMAC-Key-Id: key-256
X-HMAC-Algorithm: HMAC-SHA512
~~~

Nếu `key-256` chỉ được cấp cho `HMAC-SHA256`, server phải từ chối **ngay ở credential policy**. Không được thử hết thuật toán cho đến khi một chữ ký khớp. Nếu cố dùng cùng key với mọi thuật toán, có thể khiến chính sách chuyển đổi không được thực thi và tăng diện tích kiểm thử.

### 3.3. Downgrade trong giai đoạn chuyển đổi

Giả sử hệ thống muốn một client chuyển từ HMAC-SHA256 sang HMAC-SHA512. Nếu verifier vẫn chấp nhận cả hai thuật toán cho cùng `keyId`, client hoặc attacker có quyền gửi request được ký có thể tiếp tục dùng thuật toán cũ vô thời hạn. Một allowlist toàn cục **không giải quyết riêng vấn đề downgrade**; cần chính sách per-key, thời hạn chuyển đổi và quy trình thu hồi credential cũ.

### 3.4. Thuật toán bị tách khỏi dữ liệu có chữ ký

Header `X-HMAC-Algorithm` và `X-HMAC-Key-Id` phải được xác thực bằng policy; đồng thời nên xuất hiện trong **canonical request đã ký** để buộc chữ ký vào lựa chọn giao thức. Nếu một hệ thống có nhiều phiên bản canonical request, đưa cả **version** và định danh thuật toán vào chuỗi ký hoặc một cơ chế binding tương đương đã được đặc tả. Điều này tránh các đường xử lý cùng một byte request theo nhiều quy tắc khác nhau.

### 3.5. Header mơ hồ qua gateway

HTTP header names là case-insensitive, nhưng **giá trị algorithm ID trong ví dụ là case-sensitive**. Các tình huống cần từ chối hoặc xử lý theo hợp đồng chặt chẽ gồm:

~~~http
X-HMAC-Algorithm: HMAC-SHA256
X-HMAC-Algorithm: HMAC-SHA512
~~~

~~~http
X-HMAC-Algorithm: HMAC-SHA256, HMAC-SHA512
~~~

~~~http
X-HMAC-Algorithm: HMAC-SHA256 
~~~

Gateway có thể gộp duplicate header thành một dòng hoặc sửa whitespace. Ứng dụng cần kiểm tra số lần xuất hiện và cú pháp chính xác tại tầng có thể quan sát raw headers, hoặc cấu hình gateway **từ chối trường hợp mơ hồ trước khi forward**. Đừng tự động lấy header cuối, cắt chuỗi theo dấu phẩy hoặc âm thầm `trim()` rồi chấp nhận nếu hợp đồng không cho phép.

## 4. Giao thức minh họa với algorithm allowlist

Ví dụ sử dụng:

~~~http
POST /v1/payments?currency=VND HTTP/1.1
Content-Type: application/json
X-HMAC-Version: hmac-v1
X-HMAC-Key-Id: client-a-k2
X-HMAC-Algorithm: HMAC-SHA256
X-HMAC-Timestamp: 1795834800
X-HMAC-Nonce: nce-20261128-0001
X-HMAC-Signature: <lowercase-hex-of-full-HMAC-tag>

{"amount":150000}
~~~

**Định danh do server quản lý:**

- `hmac-v1`: phiên bản cố định của hợp đồng canonical request.
- `client-a-k2`: credential identifier; server tra metadata gồm client/principal, secret, trạng thái và thuật toán được cấp.
- `HMAC-SHA256`: thuật toán mà credential `client-a-k2` đã đăng ký. Giá trị lấy từ request dùng để **đối chiếu**, không quyết định policy.
- `X-HMAC-Signature`: lowercase hex của **full-length HMAC tag**; 64 ký tự với HMAC-SHA256, 128 ký tự với HMAC-SHA512.

Trong ví dụ, canonical request là UTF-8 của các dòng dưới đây, nối bằng byte LF (`\n`); không thêm dòng rỗng cuối chuỗi:

~~~text
REQUEST-HMAC
hmac-v1
HMAC-SHA256
client-a-k2
POST
/v1/payments?currency=VND
1795834800
nce-20261128-0001
<lowercase-hex-SHA256-of-exact-body-bytes>
~~~

Đây là hợp đồng riêng của bài học. Ở production, đường dẫn/query phải có quy tắc canonical hóa rõ ràng, không nhầm URL form decoding với URI percent decoding; method, version, keyId, algorithm, timestamp và nonce phải được validate cú pháp trước khi ghép dòng để tránh ký tự điều khiển và ambiguity. Signature header **không nằm trong dữ liệu đã ký** vì nó chính là kết quả tính HMAC.

Quy trình xác minh:

~~~mermaid
flowchart TD
    A["Nhận HTTP request"] --> B{"Header/format hợp lệ,<br/>không duplicate?"}
    B -->|Không| R["Từ chối xác thực"]
    B -->|Có| C{"Version được hỗ trợ?"}
    C -->|Không| R
    C -->|Có| D{"Algorithm ID nằm trong allowlist?"}
    D -->|Không| R
    D -->|Có| E["Tra credential theo keyId"]
    E --> F{"Credential active và<br/>algorithm khớp policy?"}
    F -->|Không| R
    F -->|Có| G{"Timestamp còn hạn?"}
    G -->|Không| R
    G -->|Có| H["Tính canonical bytes theo version<br/>và HMAC bằng thuật toán từ policy"]
    H --> I{"Full tag khớp?"}
    I -->|Không| R
    I -->|Có| J{"Nonce chưa dùng<br/>và đăng ký atomic?"}
    J -->|Không| R
    J -->|Có| K["Authenticated principal"]
    K --> L["Kiểm tra authorization<br/>trên endpoint/resource"]
~~~

Thứ tự có thể thay đổi để giảm rò rỉ thông tin hoặc tối ưu hiệu năng, nhưng phải bảo đảm **không đăng ký nonce trước khi xác minh hợp lệ** và không bỏ qua bất kỳ chính sách nào. Phản hồi public nên là một lỗi authentication thống nhất, dù test nội bộ ghi nhận lý do cụ thể.

## 5. Ví dụ Java 17: allowlist và ràng buộc per-key

Code dưới đây là một verifier minh họa. Nó giả định tầng HTTP đã chuyển request-target thành `pathAndCanonicalQuery` một cách nhất quán, đã loại bỏ duplicate headers và kiểm tra không có CR/LF trong các trường canonical. `NonceStore` cần hiện thực atomic/TTL trong môi trường nhiều instance; bản test có thể dùng `HashSet`.

**`HmacAlgorithmAllowlist.java`**

~~~java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.time.Clock;
import java.time.DateTimeException;
import java.time.Instant;
import java.util.HexFormat;
import java.util.Locale;
import java.util.Map;
import java.util.Objects;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public final class HmacAlgorithmAllowlist {
    private HmacAlgorithmAllowlist() {}

    private static final String VERSION = "hmac-v1";
    private static final int MIN_SECRET_BYTES = 32; // Policy cho secret random.
    private static final int MAX_AGE_SECONDS = 300;
    private static final int FUTURE_SKEW_SECONDS = 60;

    private record AlgorithmSpec(String jcaName, int tagBytes) {}

    private static final Map<String, AlgorithmSpec> ALLOWLIST = Map.of(
            "HMAC-SHA256", new AlgorithmSpec("HmacSHA256", 32),
            "HMAC-SHA512", new AlgorithmSpec("HmacSHA512", 64));

    // Credential metadata được cấp ngoài luồng (onboarding/rotation).
    public record Credential(String algorithm, byte[] secret, boolean active) {
        public Credential {
            Objects.requireNonNull(algorithm);
            secret = Objects.requireNonNull(secret).clone();
        }

        @Override
        public byte[] secret() {
            return secret.clone();
        }
    }

    // body được sao chép để dữ liệu không bị đổi sau khi tạo Request.
    public record Request(
            String method,
            String pathAndCanonicalQuery,
            String version,
            String algorithm,
            String keyId,
            String timestampSeconds,
            String nonce,
            byte[] body,
            String signatureHex) {
        public Request {
            body = body == null ? null : body.clone();
        }

        @Override
        public byte[] body() {
            return body == null ? null : body.clone();
        }
    }

    public enum Decision {
        ACCEPTED, MALFORMED, VERSION_NOT_ALLOWED, ALGORITHM_NOT_ALLOWED,
        CREDENTIAL_NOT_ALLOWED, TIMESTAMP_INVALID, SIGNATURE_INVALID,
        NONCE_REPLAY
    }

    @FunctionalInterface
    public interface NonceStore {
        // Production: thao tác atomic, có TTL, dùng chung giữa các instance.
        boolean claimOnce(String keyId, String nonce, Instant expiresAt);
    }

    public static final class Verifier {
        private final Clock clock;
        private final Map<String, Credential> credentials;
        private final NonceStore nonceStore;

        public Verifier(
                Clock clock,
                Map<String, Credential> credentials,
                NonceStore nonceStore) {
            this.clock = Objects.requireNonNull(clock);
            this.credentials = Map.copyOf(credentials);
            this.nonceStore = Objects.requireNonNull(nonceStore);

            // Từ chối cả cấu hình sai, thay vì đợi request đầu tiên.
            for (Credential credential : this.credentials.values()) {
                if (!ALLOWLIST.containsKey(credential.algorithm())
                        || credential.secret().length < MIN_SECRET_BYTES) {
                    throw new IllegalArgumentException(
                            "Invalid credential algorithm/secret policy");
                }
            }
        }

        public Decision verify(Request request) {
            if (request == null
                    || request.method() == null
                    || request.pathAndCanonicalQuery() == null
                    || request.version() == null
                    || request.algorithm() == null
                    || request.keyId() == null
                    || request.timestampSeconds() == null
                    || request.nonce() == null
                    || request.body() == null
                    || request.signatureHex() == null
                    || request.nonce().isBlank()) {
                return Decision.MALFORMED;
            }

            // Cú pháp mẫu: keyId/nonce chỉ gồm token ASCII không nhập nhằng.
            if (!request.keyId().matches("[A-Za-z0-9_-]{1,64}")
                    || !request.nonce().matches("[A-Za-z0-9_-]{8,128}")) {
                return Decision.MALFORMED;
            }
            if (!VERSION.equals(request.version())) {
                return Decision.VERSION_NOT_ALLOWED;
            }

            // Tuyệt đối không gọi Mac.getInstance(request.algorithm()).
            AlgorithmSpec spec = ALLOWLIST.get(request.algorithm());
            if (spec == null) {
                return Decision.ALGORITHM_NOT_ALLOWED;
            }

            Credential credential = credentials.get(request.keyId());
            if (credential == null
                    || !credential.active()
                    || !credential.algorithm().equals(request.algorithm())) {
                return Decision.CREDENTIAL_NOT_ALLOWED;
            }

            final Instant timestamp;
            try {
                String raw = request.timestampSeconds();
                if (!raw.matches("0|[1-9][0-9]*")) {
                    return Decision.TIMESTAMP_INVALID;
                }
                timestamp = Instant.ofEpochSecond(Long.parseLong(raw));
            } catch (NumberFormatException | DateTimeException ex) {
                return Decision.TIMESTAMP_INVALID;
            }

            Instant now = clock.instant();
            if (timestamp.isBefore(now.minusSeconds(MAX_AGE_SECONDS))
                    || timestamp.isAfter(now.plusSeconds(FUTURE_SKEW_SECONDS))) {
                return Decision.TIMESTAMP_INVALID;
            }

            byte[] supplied;
            try {
                String hex = request.signatureHex();
                // Chính sách ví dụ: lowercase hex, full-length tag.
                if (hex.length() != spec.tagBytes() * 2
                        || !hex.matches("[0-9a-f]+")) {
                    return Decision.SIGNATURE_INVALID;
                }
                supplied = HexFormat.of().parseHex(hex);
            } catch (IllegalArgumentException ex) {
                return Decision.SIGNATURE_INVALID;
            }

            byte[] expected = hmac(
                    spec.jcaName(), credential.secret(), canonicalBytes(request));
            if (!MessageDigest.isEqual(expected, supplied)) {
                return Decision.SIGNATURE_INVALID;
            }

            // Đăng ký nonce sau khi HMAC và timestamp hợp lệ.
            // +1 s bao phủ thời điểm biên với timestamp theo giây.
            Instant expiresAt = timestamp.plusSeconds(MAX_AGE_SECONDS + 1);
            return nonceStore.claimOnce(request.keyId(), request.nonce(), expiresAt)
                    ? Decision.ACCEPTED
                    : Decision.NONCE_REPLAY;
        }
    }

    // Chỉ phục vụ test fixture; client production có signer riêng.
    public static String signForTest(Request request, byte[] secret) {
        AlgorithmSpec spec = ALLOWLIST.get(request.algorithm());
        if (spec == null) {
            throw new IllegalArgumentException("Unknown test algorithm");
        }
        return HexFormat.of().formatHex(
                hmac(spec.jcaName(), secret, canonicalBytes(request)));
    }

    private static byte[] canonicalBytes(Request r) {
        final byte[] digest;
        try {
            digest = MessageDigest.getInstance("SHA-256").digest(r.body());
        } catch (GeneralSecurityException ex) {
            throw new IllegalStateException("SHA-256 unavailable", ex);
        }

        String canonical = String.join("\n",
                "REQUEST-HMAC",
                r.version(),
                r.algorithm(),
                r.keyId(),
                r.method().toUpperCase(Locale.ROOT),
                r.pathAndCanonicalQuery(),
                r.timestampSeconds(),
                r.nonce(),
                HexFormat.of().formatHex(digest));
        return canonical.getBytes(StandardCharsets.UTF_8);
    }

    private static byte[] hmac(String jcaName, byte[] secret, byte[] data) {
        try {
            Mac mac = Mac.getInstance(jcaName);
            mac.init(new SecretKeySpec(secret, jcaName));
            return mac.doFinal(data);
        } catch (GeneralSecurityException ex) {
            throw new IllegalStateException("Required HMAC unavailable", ex);
        }
    }
}
~~~

### Giải thích các điểm bảo vệ

- **Allowlist nằm trong code/policy server.** Header chỉ được tra cứu bằng `ALLOWLIST.get(...)`; không được truyền thẳng vào JCA provider.
- **Mỗi credential có một thuật toán.** Dù global allowlist chứa hai lựa chọn, request bị từ chối nếu algorithm khác metadata của `keyId`. Đồng thời constructor kiểm tra policy lúc khởi tạo.
- **Cấm fallback ngầm.** Thiếu algorithm, sai version, không có mapping hay thiếu credential đều dẫn đến từ chối rõ ràng.
- **Bind metadata vào HMAC.** `version`, `algorithm` và `keyId` đều nằm trong canonical bytes, cùng method, path/query, timestamp, nonce và body digest.
- **Full tag và so sánh byte.** Signature hex có độ dài chính xác theo thuật toán; `MessageDigest.isEqual` được dùng để so sánh các tag đã decode.
- **Replay guard đứng sau signature.** Timestamp/nonce không thay thế HMAC. `claimOnce` phải atomic và dùng key được giới hạn theo client/tenant trên kho thực tế; demo chỉ thể hiện interface.
- **Shared secret cần đủ entropy.** Kiểm tra độ dài 32 byte không chứng minh secret đã được sinh ngẫu nhiên. Secret phải đến từ CSPRNG/secret manager, không lấy từ mật khẩu dễ đoán và không xuất hiện trong log.

> **Giới hạn cố ý:** `pathAndCanonicalQuery` phải đã được parser/canonicalizer đáng tin cậy chuẩn hóa theo hợp đồng. Mẫu chưa thay thế HTTP request parsing, duplicate header detection, credential storage/secret wiping, TLS, rate limiting, principal mapping hay authorization. Đối với server có thể nhận method/path/query chứa ký tự điều khiển hoặc CR/LF, cần từ chối ngay tại adapter trước khi xây chuỗi ký nhiều dòng.

## 6. JUnit 5: test allowlist và chống downgrade

Test phải chứng minh rằng **chữ ký đúng với một thuật toán đã đăng ký được chấp nhận**, và những trường hợp không tuân thủ policy bị từ chối. Các key dưới đây chỉ dùng trong unit test; không dùng chuỗi cố định để sinh secret production.

**`HmacAlgorithmAllowlistTest.java`**

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.nio.charset.StandardCharsets;
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;

import org.junit.jupiter.api.Test;

class HmacAlgorithmAllowlistTest {
    private static final Clock CLOCK = Clock.fixed(
            Instant.parse("2026-11-28T03:00:00Z"), ZoneOffset.UTC);

    private static final byte[] KEY_256 =
            "0123456789abcdef0123456789abcdef"
                    .getBytes(StandardCharsets.UTF_8);
    private static final byte[] KEY_512 =
            "abcdef0123456789abcdef0123456789"
                    .getBytes(StandardCharsets.UTF_8);

    private final Set<String> nonces = new HashSet<>();
    private final HmacAlgorithmAllowlist.Verifier verifier =
            new HmacAlgorithmAllowlist.Verifier(
                    CLOCK,
                    Map.of(
                            "key256", new HmacAlgorithmAllowlist.Credential(
                                    "HMAC-SHA256", KEY_256, true),
                            "key512", new HmacAlgorithmAllowlist.Credential(
                                    "HMAC-SHA512", KEY_512, true),
                            "revoked", new HmacAlgorithmAllowlist.Credential(
                                    "HMAC-SHA256", KEY_256, false)),
                    (keyId, nonce, expiresAt) ->
                            nonces.add(keyId + "|" + nonce));

    private static HmacAlgorithmAllowlist.Request signed(
            String keyId, String algorithm, byte[] secret, String nonce) {
        var unsigned = new HmacAlgorithmAllowlist.Request(
                "POST", "/v1/payments?currency=VND",
                "hmac-v1", algorithm, keyId,
                Long.toString(CLOCK.instant().getEpochSecond()),
                nonce, "{\"amount\":150000}"
                        .getBytes(StandardCharsets.UTF_8), "");
        return withSignature(unsigned,
                HmacAlgorithmAllowlist.signForTest(unsigned, secret));
    }

    private static HmacAlgorithmAllowlist.Request withSignature(
            HmacAlgorithmAllowlist.Request request, String signature) {
        return new HmacAlgorithmAllowlist.Request(
                request.method(), request.pathAndCanonicalQuery(),
                request.version(), request.algorithm(), request.keyId(),
                request.timestampSeconds(), request.nonce(), request.body(),
                signature);
    }

    private static HmacAlgorithmAllowlist.Request withAlgorithm(
            HmacAlgorithmAllowlist.Request request, String algorithm) {
        return new HmacAlgorithmAllowlist.Request(
                request.method(), request.pathAndCanonicalQuery(),
                request.version(), algorithm, request.keyId(),
                request.timestampSeconds(), request.nonce(), request.body(),
                request.signatureHex());
    }

    @Test
    void acceptsAlgorithmAssignedToEachCredential() {
        var req256 = signed("key256", "HMAC-SHA256", KEY_256, "nonce-000001");
        var req512 = signed("key512", "HMAC-SHA512", KEY_512, "nonce-000002");

        assertEquals(HmacAlgorithmAllowlist.Decision.ACCEPTED,
                verifier.verify(req256));
        assertEquals(HmacAlgorithmAllowlist.Decision.ACCEPTED,
                verifier.verify(req512));
    }

    @Test
    void unlistedAlgorithmIsRejectedWithoutTryingProviderAliases() {
        var original = signed("key256", "HMAC-SHA256", KEY_256, "nonce-000003");

        for (String attack : new String[]{
                "none", "HMAC-SHA1", "SHA-256", "HmacSHA256",
                "hmac-sha256", "HMAC-SHA256 ", "HMAC-SHA384"}) {
            assertEquals(HmacAlgorithmAllowlist.Decision.ALGORITHM_NOT_ALLOWED,
                    verifier.verify(withAlgorithm(original, attack)), attack);
        }
    }

    @Test
    void algorithmOnAllowlistButNotForKeyIsRejected() {
        var original = signed("key256", "HMAC-SHA256", KEY_256, "nonce-000004");
        var switched = withAlgorithm(original, "HMAC-SHA512");

        assertEquals(HmacAlgorithmAllowlist.Decision.CREDENTIAL_NOT_ALLOWED,
                verifier.verify(switched));
    }

    @Test
    void wrongSignatureLengthOrEncodingIsRejected() {
        var original = signed("key256", "HMAC-SHA256", KEY_256, "nonce-000005");

        assertEquals(HmacAlgorithmAllowlist.Decision.SIGNATURE_INVALID,
                verifier.verify(withSignature(original, "00")));
        assertEquals(HmacAlgorithmAllowlist.Decision.SIGNATURE_INVALID,
                verifier.verify(withSignature(original,
                        original.signatureHex().toUpperCase())));
    }

    @Test
    void versionChangeCannotReuseSignature() {
        var original = signed("key256", "HMAC-SHA256", KEY_256, "nonce-000006");
        var changed = new HmacAlgorithmAllowlist.Request(
                original.method(), original.pathAndCanonicalQuery(),
                "hmac-v0", original.algorithm(), original.keyId(),
                original.timestampSeconds(), original.nonce(), original.body(),
                original.signatureHex());

        assertEquals(HmacAlgorithmAllowlist.Decision.VERSION_NOT_ALLOWED,
                verifier.verify(changed));
    }

    @Test
    void rejectedCredentialsDoNotBecomeActiveBecauseAlgorithmIsAllowed() {
        var revoked = signed("revoked", "HMAC-SHA256", KEY_256, "nonce-000007");
        assertEquals(HmacAlgorithmAllowlist.Decision.CREDENTIAL_NOT_ALLOWED,
                verifier.verify(revoked));
    }

    @Test
    void expiredRequestIsRejectedEvenWhenAlgorithmAndMacAreValid() {
        var recent = signed("key256", "HMAC-SHA256", KEY_256, "nonce-000008");
        var oldUnsigned = new HmacAlgorithmAllowlist.Request(
                recent.method(), recent.pathAndCanonicalQuery(),
                recent.version(), recent.algorithm(), recent.keyId(),
                Long.toString(CLOCK.instant().minusSeconds(301).getEpochSecond()),
                recent.nonce(), recent.body(), "");
        var expired = withSignature(oldUnsigned,
                HmacAlgorithmAllowlist.signForTest(oldUnsigned, KEY_256));

        assertEquals(HmacAlgorithmAllowlist.Decision.TIMESTAMP_INVALID,
                verifier.verify(expired));
    }

    @Test
    void replayIsRejectedEvenWhenMacIsValid() {
        var request = signed("key256", "HMAC-SHA256", KEY_256, "nonce-000009");

        assertEquals(HmacAlgorithmAllowlist.Decision.ACCEPTED,
                verifier.verify(request));
        assertEquals(HmacAlgorithmAllowlist.Decision.NONCE_REPLAY,
                verifier.verify(request));
    }

    @Test
    void invalidCredentialPolicyFailsAtStartup() {
        assertThrows(IllegalArgumentException.class,
                () -> new HmacAlgorithmAllowlist.Verifier(
                        CLOCK,
                        Map.of("bad", new HmacAlgorithmAllowlist.Credential(
                                "HMAC-SHA1", KEY_256, true)),
                        (keyId, nonce, expiresAt) -> true));
    }
}
~~~

Điểm phân biệt quan trọng giữa hai test âm tính:

- `unlistedAlgorithmIsRejectedWithoutTryingProviderAliases` xác minh **global allowlist**: bất kỳ định danh không được cấp đều bị từ chối ngay.
- `algorithmOnAllowlistButNotForKeyIsRejected` xác minh **credential policy**: HMAC-SHA512 nằm trong global allowlist nhưng vẫn không hợp lệ với `key256`.

Test expired tạo **chữ ký hợp lệ cho timestamp cũ**; nếu chỉ sửa timestamp của request đã ký mà giữ signature cũ, kết quả sẽ kiểm tra signature mismatch thay vì chính sách timestamp. Test replay chứng minh algorithm policy không loại bỏ nhu cầu nonce store.

Trong hệ thống thực, thêm test vector cố định được tạo độc lập bởi client và server; helper `signForTest` và verifier dùng chung code canonicalization có thể che giấu một lỗi chung nếu không có test liên thông khác implementation.

## 7. Rotation và migration không tạo cửa hạ cấp

Algorithm agility là khả năng **thay thuật toán một cách có kiểm soát** khi yêu cầu bảo mật, chính sách hoặc tính tương thích thay đổi. Điều này bao gồm khả năng thêm, không còn phát hành mới, tạm chấp nhận và cuối cùng loại bỏ thuật toán cũ.

Ví dụ lộ trình chuyển từ HMAC-SHA256 sang HMAC-SHA512 cho một client:

| Giai đoạn | Credential hoạt động | Policy của verifier | Điều cần kiểm thử |
|---|---|---|---|
| A. Hiện tại | `key-a` → HMAC-SHA256 | Chỉ nhận `key-a` theo SHA256 | Request SHA512 với `key-a` bị từ chối |
| B. Cấp key mới | `key-a` → SHA256, `key-b` → SHA512 | Mỗi key có đúng một thuật toán; cả hai còn thời hạn | Hai phiên bản client đều ký/xác minh đúng với key tương ứng |
| C. Chuyển client | Client chuyển sang `key-b` | HMAC-SHA256 chỉ còn hoạt động với `key-a` trong thời gian chuyển đổi | Không fallback nếu `key-b` gửi SHA256 |
| D. Thu hồi key cũ | `key-b` → SHA512 | `key-a` inactive/removed | Request ký đúng SHA256 bằng `key-a` vẫn bị từ chối |
| E. Dọn policy (nếu áp dụng toàn hệ thống) | Không còn credential SHA256 | Có thể bỏ HMAC-SHA256 khỏi allowlist | Regression test xác nhận không còn endpoint chấp nhận SHA256 |

Ở các giai đoạn B/C, **cả hai thuật toán có thể cùng xuất hiện trong allowlist**. Đây không phải lỗi nếu mỗi key được gắn metadata rõ ràng và credential cũ có thời hạn hữu hạn. Hệ thống nên đo số request theo algorithm/key version, cảnh báo client chưa chuyển và chỉ thu hồi key cũ khi quy trình migration được xác nhận.

Không cần tạo cơ chế "tự thử SHA256 rồi SHA512" nếu client gửi sai thông tin. Thay đổi phiên bản canonical request (ví dụ thêm header được ký, thay quy tắc URI) cũng cần điều phối như một **protocol version migration**, vì algorithm migration và canonicalization migration là hai vấn đề khác nhau.

**Quản lý secret:** Không dùng lại một secret cho nhiều credential mới nếu có thể cấp key riêng; tạo secret ngẫu nhiên bằng CSPRNG, lưu trong secret manager/KMS phù hợp, kiểm soát quyền đọc và đảm bảo key rotation không làm hỏng nonce scope. Khi secret hoặc thuật toán bị thu hồi, server không được chấp nhận lại chỉ vì tag tính ra trùng với secret từng hợp lệ.

## 8. Những test tích hợp bắt buộc quanh allowlist

### 8.1. Gateway và cách đọc header

Gateway/API proxy có thể normalize hoặc gộp header. Cần chạy request thật đi qua toàn tuyến, không chỉ unit test với `Map<String, String>` đã mất thông tin duplicate. Các test quan trọng:

1. Header thuật toán thiếu, rỗng, trùng hai dòng, list `A,B`, giá trị có khoảng trắng hoặc control character → bị từ chối theo hợp đồng.
2. Header name đổi case (`x-hmac-algorithm`) → vẫn được nhận diện như cùng header nếu không trùng; **giá trị** `HMAC-SHA256` vẫn phải khớp đúng.
3. Gateway rewrite path, query, header ký hoặc body → verifier và client phải tính cùng canonical bytes; khác biệt phải gây signature invalid thay vì fallback.
4. Header version/keyId/algorithm đã ký bị sửa trong đường truyền → không vượt qua credential policy và/hoặc kiểm tra MAC.
5. Retry của gateway với cùng nonce → được điều phối với chính sách replay/idempotency; không vì retry mà bỏ `NonceStore`.
6. API gateway/edge và service triển khai khác phiên bản allowlist → test deployment compatibility, không dùng chính sách yếu hơn ở một mắt xích mà không phát hiện.

### 8.2. Authentication, replay và authorization

Một request có **algorithm đúng** vẫn có thể bị từ chối vì key đã thu hồi, chữ ký sai, timestamp hết hạn, nonce lặp hoặc không đủ quyền thực hiện thao tác. Phân loại đúng sẽ giúp test không tạo ra false positive:

| Tình huống | Tầng chịu trách nhiệm | Kết quả mong đợi |
|---|---|---|
| `HMAC-SHA1` trong header | Algorithm policy | Reject trước verify MAC |
| `HMAC-SHA512` + key chỉ được cấp SHA256 | Credential policy | Reject |
| SHA256 + key đúng + body bị sửa | HMAC verification | Reject |
| SHA256 + signature đúng + timestamp cũ | Freshness policy | Reject |
| SHA256 + signature đúng + nonce đã dùng | Replay protection | Reject |
| SHA256 + mọi kiểm tra xác thực đúng nhưng truy cập tenant khác | Authorization | Deny theo policy tài nguyên |

Không được nhầm **xác thực** (chứng minh request liên quan đến credential hợp lệ) với **phân quyền** (client/principal này có được phép truy cập tài nguyên hay không). Algorithm allowlist chỉ phục vụ chính sách xác thực.

### 8.3. Log, metric và phản hồi lỗi

Trong test, có thể dùng reason nội bộ như `unsupported_algorithm`, `algorithm_key_mismatch`, `unsupported_protocol_version`, `invalid_mac`, `expired_timestamp`, `replayed_nonce` để xác định lỗi đúng lớp.

Ở API công khai, nên trả mã lỗi xác thực chung (ví dụ HTTP 401 theo hợp đồng) để tránh làm lộ trạng thái tồn tại của keyId, secret hay policy đặc thù của một client. Metric hữu ích gồm tỷ lệ request theo algorithm, số lần từ chối theo nhóm policy, client còn dùng credential cũ và sai khác giữa các gateway/instance. Log không được ghi shared secret, toàn bộ canonical request chứa dữ liệu nhạy cảm hay chữ ký đầy đủ.

## 9. Checklist review và bài thực hành

Khi review một cơ chế HMAC có algorithm agility, xác nhận:

- [ ] Có danh sách thuật toán **tường minh**, được kiểm soát bởi server và version hóa.
- [ ] Tên algorithm ở header được ánh xạ qua allowlist; không truyền giá trị thô vào `Mac.getInstance`.
- [ ] Mỗi credential/keyId có algorithm được cấp; caller không thể chọn một thuật toán khác dù vẫn nằm trong global allowlist.
- [ ] Unknown, empty, duplicate, malformed, khác case hoặc có whitespace bị xử lý đúng hợp đồng; không fallback âm thầm.
- [ ] Version, algorithm, keyId được bind vào canonical request hoặc cơ chế ràng buộc tương đương.
- [ ] Tag HMAC được kiểm tra đúng độ dài và so sánh bằng byte theo cách hạn chế timing leak.
- [ ] Secret đủ entropy, key rotation có lộ trình, key cũ được thu hồi và policy không còn chấp nhận legacy ngoài hạn.
- [ ] Timestamp, nonce, proxy/gateway, canonical URI/header/body được test end-to-end.
- [ ] Sau khi xác thực, authorization vẫn độc lập và kiểm tra principal/resource.
- [ ] Test bao gồm positive, negative, downgrade, algorithm/key mismatch, migration và replay.

**Bài tập thực hành:** Giả sử một API hiện hỗ trợ riêng HMAC-SHA256 cho `key-1`. Hãy cấp `key-2` được phép HMAC-SHA512 và thiết kế các test cho bốn request: (a) `key-1` + SHA256 + tag đúng; (b) `key-1` + SHA512 + tag tính đúng bằng secret cũ; (c) `key-2` + SHA512 + tag đúng; (d) `key-2` + `HMAC-SHA1` hoặc `none`. Kỳ vọng chỉ (a) và (c) được đi tiếp qua bước algorithm/credential policy; (b) và (d) bị từ chối bất kể chữ ký có được tạo ra bằng thuật toán caller yêu cầu hay không. Sau đó thu hồi `key-1` và xác nhận (a) cũng bị từ chối. Cuối cùng, chạy lại các tình huống qua gateway và đảm bảo kết quả không thay đổi.
