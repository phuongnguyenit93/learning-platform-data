# Viết contract test cho HTTP HMAC Request Authentication

## 1. Mục tiêu dự án thực hành

Bài **Viết contract test** thuộc chương **Dự án thực hành** của module `SECURITY_AUTHENTICATION_HMAC_REQUEST_AUTHENTICATION`. Người học xây dựng một bộ **kiểm thử hợp đồng** giữa client ký request, gateway/proxy, server xác minh HMAC và handler nghiệp vụ. Mục đích không chỉ là chứng minh một lời gọi HTTP trả mã 2xx, mà còn xác nhận **cùng một request được các thành phần hiểu theo cùng một hợp đồng byte-level**, và mọi biến thể không hợp lệ bị từ chối.

HMAC sử dụng **shared secret** để xác thực các trường đã ký của HTTP request. Trong dự án, canonical request bao gồm HTTP method, canonical URI path/query, content type, timestamp, nonce và SHA-256 digest của body. Phần xác minh sử dụng keyId để tra secret, policy thuật toán, trạng thái credential; thêm freshness window và nonce store để chống replay. **Phân quyền** theo principal/resource diễn ra riêng sau khi xác thực.

Sau bài học, người học cần hoàn thành:

- Một **hợp đồng ký hmac-v1** mô tả chính xác các byte được ký và cách xử lý đầu vào mơ hồ.
- Một **bộ golden vectors** độc lập giữa client và server, có positive/negative vectors.
- Mã **test signer Java 17** không phụ thuộc implementation canonicalizer của server.
- Bộ **JUnit 5 offline tests** để kiểm tra byte-level serialization và biến thể tương đương/không tương đương.
- Bộ **HTTP black-box contract tests** chạy qua staging gateway và verifier, gồm sửa body/query, expired timestamp, replay và thuật toán không được phép.
- Kịch bản kiểm thử key rotation, revocation, proxy rewrite, nonce atomic, authorization và cách báo cáo kết quả.
- Một **checklist Definition of Done** để chấp nhận bản triển khai mà không phải dựa vào một số request 200/204 đơn lẻ.

> **Phạm vi:** Bài viết là một **đề bài kèm lời giải tham khảo về cách thiết kế test**. API, endpoint, header, chính sách status và các giá trị thời gian bên dưới là hợp đồng mẫu để người học dựng trên môi trường test/staging được ủy quyền. Không sử dụng key thật, không thực hiện giao dịch tài chính thật, không đưa secret hoặc signature đầy đủ vào log/ticket. STEP 4 soạn nội dung, không chạy build/test hay Content QA.

## 2. Contract test khác unit test ở đâu?

Một unit test gọi `HmacSigner.sign()` rồi dùng chính `HmacSigner.verify()` có thể cho kết quả xanh dù client và server thật triển khai **cùng một sai lầm**, hoặc gateway rewrite query khiến kết quả ngoài thực tế không khớp. Contract test phải kiểm chứng **đường biên giữa các thành phần**, tốt nhất có fixtures độc lập và so sánh với kết quả đã chốt từ hợp đồng.

| Loại kiểm thử | Phần được kiểm tra | Giới hạn |
|---|---|---|
| Unit test canonicalizer | Một hàm parse/sắp xếp/encode query | Không chứng minh phía client khác ngôn ngữ tương thích |
| Unit test HMAC | Kết quả cryptographic MAC trên message cụ thể | Không chứng minh message chứa đủ method/path/query/body |
| **Offline contract test** | Byte serialization và golden vector mà các phía phải tuân thủ | Không thấy lỗi gateway, nonce store hay authorization |
| **HTTP black-box contract test** | Request ký thật đi qua gateway, verifier, handler | Cần sandbox credential, endpoint fixture và observability |
| Integration test đa instance | Nonce atomic, policy propagation, clock/region | Không thay thế load/security testing |
| Security regression | Body/query/header tampering, downgrade, replay và vượt quyền | Phải phân biệt nguyên nhân reject, tránh false positive |

Một contract test tốt có hai loại oracle:

1. **Byte oracle:** canonical request và HMAC tag phải khớp một golden vector được xây dựng **độc lập**, không chỉ từ cùng hàm production.
2. **Behavior oracle:** với request đã ký, server phải **chấp nhận/từ chối đúng tầng và đúng nguyên nhân**, kể cả khi đi qua gateway hoặc nhiều verifier.

### 2.1. Ai sở hữu hợp đồng?

Chủ sở hữu client, API security và gateway cần cùng duyệt một tài liệu versioned. Mỗi thay đổi ở path/query normalization, signed headers, body digest, algorithm, timestamp unit hoặc nonce scope có thể là **thay đổi giao thức**. Không tự sửa behavior của v1 để "cho qua" một client đang lỗi mà không có regression tests và kế hoạch versioning.

## 3. Kiến trúc thử nghiệm và điều kiện chuẩn bị

~~~mermaid
flowchart LR
    C["Client test signer<br/>Java 17"] --> G["Staging Gateway<br/>HTTP edge"]
    G --> V["HMAC Verifier<br/>policy + canonical bytes"]
    V --> N["Nonce Store<br/>atomic shared TTL"]
    V --> K["Credential Store<br/>keyId + secret + status"]
    V --> A["Authorization<br/>principal/resource"]
    A --> H["Fixture Handler<br/>no side effects"]
    T["Test Runner JUnit 5"] --> C
    T --> O["Contract report<br/>requestId + reason"]
    G --> O
    V --> O
    H --> O
~~~

### 3.1. Sandbox cần có

| Thành phần | Yêu cầu | Lý do |
|---|---|---|
| Client fixture | `sandbox-client` có `keyId` và secret **chỉ dành cho test** | Không ảnh hưởng credential thật |
| HMAC verifier | Chấp nhận `hmac-v1`/`HMAC-SHA256` cho test key | Ràng buộc policy được quan sát qua HTTP |
| Clock | Server dùng UTC và NTP; unit tests hỗ trợ `Clock.fixed(...)` | Test ranh giới không phụ thuộc `sleep` |
| Nonce store | Shared giữa các instance, claim atomically | Test replay xuyên node |
| Route hợp lệ | `POST /contract-test/orders`, HMAC đúng + có quyền trả **204** | Positive oracle và tránh side effect |
| Route không được cấp quyền | `POST /contract-test/forbidden`, HMAC đúng trả **403** | Test tách authN/authZ |
| Authentication error | Với contract mẫu, authN fail trả **401** | Có oracle nhất quán cho negative tests |
| Auditing | Request ID, reason nội bộ, policy/gateway version | Tìm nguyên nhân mà không tiết lộ bí mật |
| Gateway | Giống production về rewrite path/query/header/body | Phát hiện integration mismatch |

Hai route trên là **fixture giả định** phải được cung cấp trong môi trường test; chúng không phải endpoint mặc định của Spring Security. Nếu dự án có cách mã hóa lỗi khác, cập nhật hợp đồng thử nghiệm và assertion tương ứng, **không tự gán 401/403 cho mọi framework**.

### 3.2. Cách tổ chức bài nộp

Một cấu trúc bài thực hành có thể gồm:

~~~text
hmac-contract-tests/
  src/test/java/example/contract/
    ContractV1.java              # signer/canonicalizer độc lập
    ContractV1OfflineTest.java   # golden + property/negative tests
    HmacWireContractIT.java      # black-box HTTP tests
  fixtures/
    golden-v1.json               # raw bytes, canonical hex, expected HMAC
    invalid-v1.json              # malformed/ambiguous cases
  README-test-contract.md        # environment, setup, run, expected status
  reports/
    # Kết quả CI không chứa secrets/signatures đầy đủ
~~~

Cấu trúc này mô tả **deliverable** của người học; bài Knowledge không yêu cầu tạo các file ngoài bài Markdown đang được giao.

## 4. Đặc tả hợp đồng ký `hmac-v1`

### 4.1. Mười một dòng canonical request

Đặt `C(req)` là chuỗi 11 dòng sau, nối bằng **byte LF (0x0A)**, UTF-8, **không** có LF cuối:

~~~text
HMAC-HTTP-REQUEST
hmac-v1
HMAC-SHA256
<KEY_ID>
<METHOD>
<CANONICAL_PATH>
<CANONICAL_QUERY>
<CONTENT_TYPE>
<TIMESTAMP_SECONDS>
<NONCE>
<BODY_SHA256_LOWER_HEX>
~~~

Nếu query không tồn tại, dòng `CANONICAL_QUERY` **rỗng nhưng vẫn chiếm một dòng**; chuỗi có hai byte LF liền nhau ở vùng đó. Không được dùng `trim()` cho toàn chuỗi ký vì sẽ làm mất empty values hợp lệ. Domain separator `HMAC-HTTP-REQUEST` tách chữ ký HTTP khỏi các thông điệp dùng cùng loại key theo mục đích khác.

\[
\operatorname{bodyHash}=\operatorname{lowerHex}(\operatorname{SHA256}(\text{exactBodyBytes}))
\]

\[
\operatorname{signature}=\operatorname{lowerHex}(\operatorname{HMAC\text{-}SHA256}
(K,\operatorname{UTF8}(C(req))))
\]

Signature có **64 lowercase hex characters**, tương đương full 32-byte HMAC-SHA256 tag. Server phải tự tính body hash trên byte body thực nhận và dùng nó trong chuỗi ký, **không** chỉ so sánh với hash do client khai.

### 4.2. Quy tắc cho từng trường

| Trường | Contract mẫu | Nếu sai |
|---|---|---|
| Version | `hmac-v1` chính xác; luôn được ký | Reject unsupported version |
| Algorithm | `HMAC-SHA256` chính xác; được server và credential policy cấp | Reject unknown/downgrade |
| KeyId | `[A-Za-z0-9_-]{1,64}`, tra secret và principal từ store | Reject unknown, inactive hoặc malformed |
| Method | Trong `GET, POST, PUT, PATCH, DELETE`; uppercase | Reject không hợp đồng |
| Path | `/` hoặc segment ASCII unreserved, không percent-escape, empty/dot segments | Reject ambiguity |
| Query | Parse nghiêm, unique keys sau decode, sorted, percent-encode lại | Reject duplicate/invalid UTF-8/escape |
| Content-Type | Literal `application/json` cho fixture này | Reject media type ngoài hợp đồng |
| Timestamp | Unix epoch **giây UTC** không có leading zero | Reject malformed hoặc out-of-window |
| Nonce | `[A-Za-z0-9_-]{16,128}`, random và unique per credential | Reject malformed/replay |
| Body hash | SHA-256 exact body bytes, kể cả body rỗng | Invalid MAC nếu body bị thay |
| Signature | Full tag, lowercase hex, so sánh byte theo cách hạn chế timing leakage | Reject invalid MAC |

Trong ví dụ, `MAX_AGE=300s`, `FUTURE_SKEW=60s`, hai biên được **chấp nhận**:

~~~text
now - 300s <= timestamp <= now + 60s
~~~

Timestamp chỉ chống request quá cũ/quá xa trong tương lai. Nonce store phải dùng chung giữa các verifier và thực hiện claim atomic với TTL được tính để không có hai lần chấp nhận cùng nonce trong cửa sổ liên quan. Key rotation, revocation và authorization vẫn cần test riêng.

### 4.3. Canonical query nghiêm ngặt

Query thô chỉ cho phép ký tự ASCII unreserved, dấu `+` (được xem là **literal plus**, không phải space), escape `%HH`, `&` giữa các cặp và một `=` phân key/value. Percent-decode **đúng một lần**, decode UTF-8 strict, từ chối control bytes; key sau decode chỉ chứa ASCII unreserved và **không được trùng**, kể cả `a` và `%61`. Value có thể là UTF-8 hợp lệ. Sau đó encode các byte ngoài unreserved thành `%HH` uppercase; sort theo encoded key, nối `&`.

| Input | Canonical hoặc expected |
|---|---|
| `b=2&a=1` | `a=1&b=2` |
| `q=hello+world` | `q=hello%2Bworld` |
| `q=hello%20world` | `q=hello%20world` |
| `x=%2f` | `x=%2F` |
| `x=%252F` | `x=%252F`, **khác** `%2F` |
| `text=%C3%A9` | `text=%C3%A9` |
| `x=` | `x=` hợp lệ |
| `a=1&%61=2` | Reject duplicate sau decode |
| `a=1&a=2` | Reject duplicate |
| `x=%G0`, `x=%C0%AF` | Reject malformed encoding |
| `x`, `=1`, `x=1&`, `a=1;b=2` | Reject cú pháp |
| `q=a b`, raw Unicode trong query | Reject raw character ngoài hợp đồng |

Giới hạn ví dụ: raw/canonical query tối đa 4096 ký tự, tối đa 64 cặp, key đã decode tối đa 128 byte, value tối đa 1024 byte; path tối đa 1024 ký tự; body tối đa **1 MiB**. Các giới hạn đó là phần của contract; không nên thay đổi âm thầm trên một server node.

### 4.4. Body, header và gateway

Body được ký qua SHA-256 của **đúng bytes mà verifier xác minh và handler sẽ dùng**. Không băm JSON DTO serialize lại vì whitespace, thứ tự property, escaping và số thập phân có thể khác; không bỏ body digest chỉ vì body rỗng. Hash SHA-256 của body rỗng có thể dùng làm golden vector:

~~~text
e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
~~~

Content type được ràng buộc vào chuỗi ký. Nếu API thật dựa vào `Host`, authority, tenant header hoặc media type parameters để định tuyến/diễn giải nội dung, phải **bổ sung chúng vào hợp đồng ký hoặc ranh giới tin cậy tương đương**. Mẫu này không tự bảo vệ mọi header.

Trước khi dựng canonical bytes, adapter HTTP phải từ chối duplicate signed headers, giá trị chứa CR/LF, phương thức không được cho phép, path/query đã biến đổi ngoài contract. Với HTTP/2, `:path` và `:authority` có hình thức khác start-line HTTP/1.1; hai bên phải thống nhất trường canonical **theo ngữ nghĩa protocol**, không giả định luôn có cùng raw HTTP start-line.

## 5. Kế hoạch kiểm thử và oracle

### 5.1. Ma trận hợp đồng

| Mã | Tình huống | Oracle |
|---|---|---|
| CT-01 | Request hợp lệ với HMAC đúng và key active | 204 ở fixture allowed |
| CT-02 | Đảo thứ tự query unique keys, giữ chữ ký theo canonical tương đương | 204 |
| CT-03 | Sửa `amount` trong body sau ký, trước lần gửi đầu | 401 do invalid MAC |
| CT-04 | Sửa `currency` trong raw query nhưng giữ chữ ký cũ | 401 do invalid MAC |
| CT-05 | `+` so với `%20` trong query | Canonical khác, không chia sẻ HMAC |
| CT-06 | `%2f` so với `%2F` | Canonical giống |
| CT-07 | Query duplicate keys sau decode | Reject trước business handler |
| CT-08 | Malformed percent/UTF-8 và path bất thường | Reject có kiểm soát, không gây unhandled 500 |
| CT-09 | Timestamp vừa quá `MAX_AGE`, **ký lại đúng** | 401, freshness reject |
| CT-10 | Timestamp ngoài `FUTURE_SKEW`, ký lại đúng | 401 |
| CT-11 | Cùng nonce/HMAC gửi hai lần | Lần đầu 204, lần sau 401 |
| CT-12 | Hai request cùng nonce đến hai verifier đồng thời | Tối đa một lần 204 |
| CT-13 | Algorithm không được phép hoặc sai policy key | 401 |
| CT-14 | Key revoked, HMAC đúng với timestamp/nonce mới | 401 |
| CT-15 | HMAC đúng nhưng client thiếu quyền vào resource | 403 |
| CT-16 | Gateway rewrite ký tự query/body/header đã ký | Reject hoặc giữ byte canonical đúng contract |
| CT-17 | Nonce store không thể claim | Fail closed; không có side effect |
| CT-18 | Body/query/header vượt giới hạn | Reject bounded, không exhaustion |

Phân biệt **status code ở wire** với **reason nội bộ**. Trong hợp đồng ví dụ 401 dành cho authentication failure, 403 cho authorization failure, 204 cho allowed fixture. Một implementation có thể chọn 400 cho malformed request hoặc 503 khi nonce store outage; nếu thế phải xác định rõ trong contract test thay vì tùy ý gộp mọi lỗi thành 401.

### 5.2. Tránh ba loại false positive quan trọng

1. **Replay che giấu thiếu body binding:** Nếu gửi request gốc đã được server chấp nhận rồi sửa body và gửi lại, nonce đã dùng có thể khiến request bị từ chối dù HMAC **không bao phủ body**. CT-03 phải tạo chữ ký gốc, sửa body **trước lần gửi đầu** với nonce mới.
2. **Signature mismatch che giấu freshness:** Nếu sửa header timestamp của request đã ký nhưng giữ chữ ký cũ, kết quả 401 có thể do invalid MAC chứ không phải timestamp expired. CT-09/10 phải **ký lại cho timestamp kiểm thử**.
3. **Timestamp/signature che giấu key revoke:** Để chứng minh key bị thu hồi, request phải được ký đúng bằng secret cũ, dùng timestamp hợp lệ và nonce mới. Request cũ expired không chứng minh revocation đã áp dụng trên mọi verifier.

### 5.3. Tách golden vector khỏi test HTTP

Offline tests nên chạy trên mọi commit và không phụ thuộc network/clock thực. HTTP contract tests chạy trên sandbox đã provisioned và gateway có policy ổn định. Trong CI, nếu thiếu staging URL/credential, **fail job integration với thông báo rõ**; không mặc nhiên skip toàn bộ test rồi kết luận tương thích.

## 6. Java 17: test signer độc lập theo hợp đồng

Mã tham khảo sau nằm **trong project test**, không import thư viện canonicalization của server. Nó tạo chính xác 11 dòng ký, parse query strict, dùng SHA-256 cho exact body bytes và HMAC-SHA256 cho chuỗi canonical. Việc client và server độc lập implement contract giúp phát hiện lỗi tương thích; một test tốt vẫn cần golden vector được tính và đối chiếu từ nguồn độc lập thứ hai.

**`ContractV1.java`**

~~~java
package example.contract;

import java.io.ByteArrayOutputStream;
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.util.HexFormat;
import java.util.HashSet;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.StringJoiner;
import java.util.TreeMap;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public final class ContractV1 {
    private ContractV1() {}

    public static final int MAX_BODY_BYTES = 1_048_576;
    public static final int MAX_QUERY_CHARS = 4_096;
    public static final int MAX_QUERY_PAIRS = 64;
    private static final String HEX = "0123456789ABCDEF";
    private static final Set<String> METHODS =
            Set.of("GET", "POST", "PUT", "PATCH", "DELETE");

    public record Input(
            String keyId, String method, String path, String rawQuery,
            String contentType, String timestamp, String nonce, byte[] body) {

        public Input {
            body = Objects.requireNonNull(body, "body").clone();
        }

        @Override
        public byte[] body() {
            return body.clone();
        }
    }

    public static byte[] canonicalBytes(Input input) {
        Objects.requireNonNull(input, "input");
        token(input.keyId(), "[A-Za-z0-9_-]{1,64}", "keyId");
        token(input.nonce(), "[A-Za-z0-9_-]{16,128}", "nonce");

        if (input.method() == null || !METHODS.contains(input.method())) {
            throw new IllegalArgumentException("invalid_method");
        }
        validPath(input.path());

        if (!"application/json".equals(input.contentType())) {
            throw new IllegalArgumentException("invalid_content_type");
        }
        String timestamp = input.timestamp();
        if (timestamp == null
                || !timestamp.matches("0|[1-9][0-9]{0,18}")) {
            throw new IllegalArgumentException("invalid_timestamp");
        }
        try {
            Long.parseLong(timestamp);
        } catch (NumberFormatException ex) {
            throw new IllegalArgumentException("invalid_timestamp", ex);
        }

        byte[] body = input.body();
        if (body.length > MAX_BODY_BYTES) {
            throw new IllegalArgumentException("body_too_large");
        }

        String canonicalQuery = canonicalQuery(input.rawQuery());
        String bodyHash = sha256Hex(body);

        String canonical = String.join("\n",
                "HMAC-HTTP-REQUEST",
                "hmac-v1",
                "HMAC-SHA256",
                input.keyId(),
                input.method(),
                input.path(),
                canonicalQuery,
                input.contentType(),
                timestamp,
                input.nonce(),
                bodyHash);
        return canonical.getBytes(StandardCharsets.UTF_8);
    }

    public static String sign(byte[] secret, Input input) {
        Objects.requireNonNull(secret, "secret");
        try {
            Mac mac = Mac.getInstance("HmacSHA256");
            mac.init(new SecretKeySpec(secret, "HmacSHA256"));
            return HexFormat.of().formatHex(mac.doFinal(canonicalBytes(input)));
        } catch (GeneralSecurityException ex) {
            throw new IllegalStateException("HMAC-SHA256 unavailable", ex);
        }
    }

    public static String sha256Hex(byte[] body) {
        try {
            return HexFormat.of().formatHex(
                    MessageDigest.getInstance("SHA-256").digest(body));
        } catch (GeneralSecurityException ex) {
            throw new IllegalStateException("SHA-256 unavailable", ex);
        }
    }

    private static void validPath(String path) {
        if (path == null || path.length() > 1_024
                || !path.matches(
                    "/(?:[A-Za-z0-9._~-]+(?:/[A-Za-z0-9._~-]+)*)?")) {
            throw new IllegalArgumentException("invalid_path");
        }
        for (String segment : path.split("/", -1)) {
            if (segment.equals(".") || segment.equals("..")) {
                throw new IllegalArgumentException("dot_segment");
            }
        }
    }

    private static void token(String value, String regex, String name) {
        if (value == null || !value.matches(regex)) {
            throw new IllegalArgumentException("invalid_" + name);
        }
    }

    public static String canonicalQuery(String rawQuery) {
        if (rawQuery == null || rawQuery.isEmpty()) {
            return "";
        }
        if (rawQuery.length() > MAX_QUERY_CHARS) {
            throw new IllegalArgumentException("query_too_long");
        }

        String[] pairs = rawQuery.split("&", -1);
        if (pairs.length > MAX_QUERY_PAIRS) {
            throw new IllegalArgumentException("too_many_pairs");
        }

        Set<String> seenKeys = new HashSet<>();
        Map<String, String> encoded = new TreeMap<>();

        for (String pair : pairs) {
            int separator = pair.indexOf('=');
            if (separator <= 0) {
                throw new IllegalArgumentException("invalid_pair");
            }

            String key = decode(pair.substring(0, separator), 128);
            String value = decode(pair.substring(separator + 1), 1_024);
            if (!key.matches("[A-Za-z0-9_.~-]+")) {
                throw new IllegalArgumentException("invalid_key");
            }
            if (!seenKeys.add(key)) {
                throw new IllegalArgumentException("duplicate_key");
            }

            encoded.put(encode(key), encode(value));
        }

        StringJoiner joiner = new StringJoiner("&");
        for (var entry : encoded.entrySet()) {
            joiner.add(entry.getKey() + "=" + entry.getValue());
        }
        String canonical = joiner.toString();
        if (canonical.length() > MAX_QUERY_CHARS) {
            throw new IllegalArgumentException("canonical_query_too_long");
        }
        return canonical;
    }

    private static String decode(String raw, int maxBytes) {
        ByteArrayOutputStream out = new ByteArrayOutputStream();

        for (int i = 0; i < raw.length();) {
            char ch = raw.charAt(i);
            if (ch == '%') {
                if (i + 2 >= raw.length()) {
                    throw new IllegalArgumentException("bad_percent");
                }
                int hi = fromHex(raw.charAt(i + 1));
                int lo = fromHex(raw.charAt(i + 2));
                if (hi < 0 || lo < 0) {
                    throw new IllegalArgumentException("bad_percent");
                }
                out.write((hi << 4) | lo);
                i += 3;
            } else if (ch < 128 && (unreserved(ch) || ch == '+')) {
                // URI query: literal '+' KHÔNG phải dấu cách.
                out.write(ch);
                i++;
            } else {
                throw new IllegalArgumentException("invalid_raw_character");
            }
            if (out.size() > maxBytes) {
                throw new IllegalArgumentException("component_too_long");
            }
        }

        byte[] bytes = out.toByteArray();
        for (byte b : bytes) {
            int u = b & 0xFF;
            if (u < 0x20 || u == 0x7F) {
                throw new IllegalArgumentException("control_byte");
            }
        }

        try {
            return StandardCharsets.UTF_8.newDecoder()
                    .onMalformedInput(CodingErrorAction.REPORT)
                    .onUnmappableCharacter(CodingErrorAction.REPORT)
                    .decode(ByteBuffer.wrap(bytes)).toString();
        } catch (CharacterCodingException ex) {
            throw new IllegalArgumentException("invalid_utf8", ex);
        }
    }

    private static String encode(String decoded) {
        StringBuilder out = new StringBuilder();
        for (byte b : decoded.getBytes(StandardCharsets.UTF_8)) {
            int u = b & 0xFF;
            if (unreserved(u)) {
                out.append((char) u);
            } else {
                out.append('%')
                        .append(HEX.charAt(u >>> 4))
                        .append(HEX.charAt(u & 0x0F));
            }
        }
        return out.toString();
    }

    private static boolean unreserved(int c) {
        return (c >= 'A' && c <= 'Z')
                || (c >= 'a' && c <= 'z')
                || (c >= '0' && c <= '9')
                || c == '-' || c == '.' || c == '_' || c == '~';
    }

    private static int fromHex(char ch) {
        if (ch >= '0' && ch <= '9') return ch - '0';
        if (ch >= 'a' && ch <= 'f') return ch - 'a' + 10;
        if (ch >= 'A' && ch <= 'F') return ch - 'A' + 10;
        return -1;
    }
}
~~~

### 6.1. Giới hạn của signer tham khảo

- `ContractV1` là **test fixture**, không phải HTTP adapter. Nó **không** đọc raw HTTP start-line, kiểm tra duplicate signed headers, hoặc xác nhận raw request-target đã được gateway giữ nguyên.
- Chữ ký `sign(...)` dùng secret test; phía server vẫn phải tra credential active, kiểm tra allowlist, freshness, nonce atomic và xác định principal.
- Body được clone trong `Input` để tránh mảng byte bị sửa sau khi tạo fixture. Adapter/handler thật vẫn phải bảo đảm sử dụng **chính bytes đã được xác minh**.
- Query parser cố ý từ chối một số URL hợp lệ theo HTTP, như repeated keys hoặc Unicode path, vì contract mẫu không định nghĩa chúng. Không tự nới parser của test cho một client mà không version hóa hợp đồng.
- Việc cùng Java tạo ra cả signature và expected signature không chứng minh tương thích; phải bổ sung golden vectors được tạo **độc lập với mã production/test signer này**.

## 7. JUnit 5 offline contract tests

Các test dưới đây không cần server, Redis hoặc internet. Chúng đóng băng **cấu trúc và ngữ nghĩa canonical bytes**, tạo các biến thể dương/âm và thử property sắp xếp query. Bộ test có thể chạy trên mỗi pull request sau khi người học đặt code vào project Java 17 và thêm JUnit Jupiter.

**`ContractV1OfflineTest.java`**

~~~java
package example.contract;

import static org.junit.jupiter.api.Assertions.*;

import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Random;
import org.junit.jupiter.api.Test;

class ContractV1OfflineTest {
    // CHỈ dùng làm fixture, không dùng làm production secret.
    private static final byte[] TEST_SECRET =
            "contract-test-fixture-secret-not-production"
                    .getBytes(StandardCharsets.UTF_8);

    private static ContractV1.Input fixture(String query, String body) {
        return new ContractV1.Input(
                "sandbox-key-1",
                "POST",
                "/contract-test/orders",
                query,
                "application/json",
                "1795834800",
                "nonce-contract-000001",
                body.getBytes(StandardCharsets.UTF_8));
    }

    @Test
    void exactElevenLinesIncludingEmptyBodyDigest() {
        String canonical = new String(
                ContractV1.canonicalBytes(fixture("b=2&a=1", "")),
                StandardCharsets.UTF_8);
        String[] lines = canonical.split("\n", -1);

        assertEquals(11, lines.length);
        assertEquals("HMAC-HTTP-REQUEST", lines[0]);
        assertEquals("hmac-v1", lines[1]);
        assertEquals("HMAC-SHA256", lines[2]);
        assertEquals("sandbox-key-1", lines[3]);
        assertEquals("POST", lines[4]);
        assertEquals("/contract-test/orders", lines[5]);
        assertEquals("a=1&b=2", lines[6]);
        assertEquals("application/json", lines[7]);
        assertEquals("1795834800", lines[8]);
        assertEquals("nonce-contract-000001", lines[9]);
        assertEquals(
                "e3b0c44298fc1c149afbf4c8996fb924"
                + "27ae41e4649b934ca495991b7852b855",
                lines[10]);
        assertFalse(canonical.endsWith("\n"));
    }

    @Test
    void noQueryRetainsItsEmptyLine() {
        String canonical = new String(
                ContractV1.canonicalBytes(fixture(null, "")),
                StandardCharsets.UTF_8);
        String[] lines = canonical.split("\n", -1);

        assertEquals(11, lines.length);
        assertEquals("", lines[6]);
        assertEquals("application/json", lines[7]);
    }

    @Test
    void reversedUniqueParametersHaveSameCanonicalBytes() {
        assertArrayEquals(
                ContractV1.canonicalBytes(fixture("b=2&a=1", "x")),
                ContractV1.canonicalBytes(fixture("a=1&b=2", "x")));
    }

    @Test
    void plusAndSpaceDifferWhileHexCaseDoesNot() {
        assertEquals("q=a%2Bb",
                ContractV1.canonicalQuery("q=a+b"));
        assertEquals("q=a%20b",
                ContractV1.canonicalQuery("q=a%20b"));
        assertNotEquals(
                ContractV1.canonicalQuery("q=a+b"),
                ContractV1.canonicalQuery("q=a%20b"));
        assertEquals(
                ContractV1.canonicalQuery("x=%2f"),
                ContractV1.canonicalQuery("x=%2F"));
    }

    @Test
    void decodingMustHappenExactlyOnce() {
        assertEquals("x=%252F",
                ContractV1.canonicalQuery("x=%252F"));
        assertEquals("x=%2F",
                ContractV1.canonicalQuery("x=%2F"));
    }

    @Test
    void duplicateKeysAfterDecodeAreRejected() {
        for (String raw : List.of(
                "role=user&role=admin",
                "a=1&%61=2")) {
            assertThrows(IllegalArgumentException.class,
                    () -> ContractV1.canonicalQuery(raw), raw);
        }
    }

    @Test
    void malformedInputsAreRejected() {
        for (String raw : List.of(
                "a", "=1", "a=1&", "a=1&&b=2",
                "x=%", "x=%G0", "x=%C0%AF", "x=%FF",
                "x=%00", "x=%0D%0A", "x=a b",
                "x=1;admin=true", "x=a=b", "q=é")) {
            assertThrows(IllegalArgumentException.class,
                    () -> ContractV1.canonicalQuery(raw), raw);
        }
    }

    @Test
    void tamperedBodyCannotReuseSignedTag() {
        String original = ContractV1.sign(TEST_SECRET,
                fixture("currency=VND", "{\"amount\":100000}"));
        String tampered = ContractV1.sign(TEST_SECRET,
                fixture("currency=VND", "{\"amount\":900000}"));

        assertNotEquals(original, tampered);
        assertEquals(64, original.length());
    }

    @Test
    void tamperedQueryCannotReuseSignedTag() {
        assertNotEquals(
                ContractV1.sign(TEST_SECRET,
                        fixture("currency=VND", "{\"amount\":100000}")),
                ContractV1.sign(TEST_SECRET,
                        fixture("currency=USD", "{\"amount\":100000}")));
    }

    @Test
    void rejectsInvalidPathAndOversizeBody() {
        for (String path : List.of(
                "/a/../admin", "//admin", "/orders/",
                "/orders/%2F", "/a?b=1")) {
            var bad = new ContractV1.Input(
                    "sandbox-key-1", "POST", path, "",
                    "application/json", "1795834800",
                    "nonce-contract-000001", new byte[0]);
            assertThrows(IllegalArgumentException.class,
                    () -> ContractV1.canonicalBytes(bad), path);
        }

        var tooLarge = new ContractV1.Input(
                "sandbox-key-1", "POST", "/contract-test/orders", "",
                "application/json", "1795834800",
                "nonce-contract-000001",
                new byte[ContractV1.MAX_BODY_BYTES + 1]);
        assertThrows(IllegalArgumentException.class,
                () -> ContractV1.canonicalBytes(tooLarge));
    }

    @Test
    void queryPermutationsRemainEquivalentWithFixedSeed() {
        Random random = new Random(0x5EEDL);
        String[] values = {"", "1", "%7e", "%2F", "+", "%C3%A9"};

        for (int iteration = 0; iteration < 1_000; iteration++) {
            List<String> pairs = new ArrayList<>();
            int count = 1 + random.nextInt(12);
            for (int i = 0; i < count; i++) {
                pairs.add("k" + i + "="
                        + values[random.nextInt(values.length)]);
            }

            String canonical = ContractV1.canonicalQuery(
                    String.join("&", pairs));
            Collections.shuffle(pairs, random);
            String permuted = String.join("&", pairs);
            assertEquals(canonical,
                    ContractV1.canonicalQuery(permuted),
                    "iteration=" + iteration);
            assertEquals(canonical,
                    ContractV1.canonicalQuery(canonical),
                    "idempotence failed");
        }
    }
}
~~~

### 7.1. Thêm một golden vector thật sự độc lập

Test `exactElevenLinesIncludingEmptyBodyDigest` cố định cấu trúc nhưng test signer vẫn có thể cùng sai về HMAC nếu phía server copy cùng logic. Vì vậy, tạo **một tập vector do nhóm client và nhóm server xác nhận riêng**. Mỗi vector nên lưu:

~~~json
{
  "contract": "hmac-v1",
  "description": "POST with two sorted unique query parameters",
  "method": "POST",
  "path": "/contract-test/orders",
  "rawQuery": "orderId=o-123&currency=VND",
  "canonicalQuery": "currency=VND&orderId=o-123",
  "contentType": "application/json",
  "timestamp": "1795834800",
  "nonce": "nonce-contract-000001",
  "bodyUtf8": "{\"amount\":100000}",
  "canonicalUtf8Lines": 11,
  "canonicalHex": "<populate-from-independent-reference>",
  "expectedHmacHex": "<populate-from-independent-reference>"
}
~~~

Đây là **schema minh họa**; các placeholder không được coi là expected values có thể chạy test ngay. Trong bản nộp thật, thay chúng bằng canonical byte hex và expected HMAC tính từ **secret giả chỉ dành cho test**, lưu phương pháp tạo độc lập và dùng `assertArrayEquals` trên canonical bytes, `assertEquals` trên HMAC. Nếu chưa có vector độc lập đã được phê duyệt, đánh dấu **BLOCKED: MISSING_GOLDEN_VECTOR**, không tự tuyên bố hợp đồng đã được kiểm chứng.

## 8. JUnit 5 HTTP black-box contract test qua gateway

Ở tầng này test **không import verifier hoặc security filter của server**. Nó tự ký request bằng `ContractV1` trong test project và gửi HTTP thực sự qua gateway staging. Server phải triển khai contract độc lập và cung cấp fixture endpoint không gây side effect.

### 8.1. Biến môi trường và route fixture

~~~text
HMAC_CONTRACT_BASE_URL=https://staging-api.example.test
HMAC_CONTRACT_KEY_ID=sandbox-key-1
HMAC_CONTRACT_KEY_HEX=<hex-of-test-only-secret>
~~~

Các giá trị trên là placeholder. Trong CI dùng secret store bảo mật; **không đưa secret thật vào Markdown, source, log, pipeline report hoặc terminal history**. Cần provision client `sandbox-key-1` với `hmac-v1/HMAC-SHA256`, cho phép gọi `POST /contract-test/orders` (trả **204**) nhưng không cấp quyền gọi `POST /contract-test/forbidden` (trả **403** khi authN hợp lệ). AuthN fail trả **401** theo hợp đồng mẫu. Nếu API thực có cách map status khác, chuẩn hóa lại **contract trước**, không sửa assertion chỉ để xanh.

### 8.2. Java 17 HTTP test harness

**`HmacWireContractIT.java`**

~~~java
package example.contract;

import static org.junit.jupiter.api.Assertions.assertEquals;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.time.Instant;
import java.util.HexFormat;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.CompletableFuture;
import org.junit.jupiter.api.Test;

class HmacWireContractIT {
    private static final HttpClient HTTP = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(5)).build();

    private static String env(String name) {
        String value = System.getenv(name);
        if (value == null || value.isBlank()) {
            throw new IllegalStateException("Missing test config: " + name);
        }
        return value;
    }

    private static String baseUrl() {
        String base = env("HMAC_CONTRACT_BASE_URL");
        return base.endsWith("/")
                ? base.substring(0, base.length() - 1) : base;
    }

    private static byte[] secret() {
        return HexFormat.of().parseHex(env("HMAC_CONTRACT_KEY_HEX"));
    }

    private static String keyId() {
        return env("HMAC_CONTRACT_KEY_ID");
    }

    private static String nonce() {
        return UUID.randomUUID().toString().replace("-", "");
    }

    private static byte[] utf8(String text) {
        return text.getBytes(StandardCharsets.UTF_8);
    }

    private static HttpRequest signedRequest(
            String path, String wireQuery, String signedQuery,
            byte[] signedBody, byte[] sentBody, long timestamp,
            String nonce, String wireAlgorithm) {
        var fixture = new ContractV1.Input(
                keyId(), "POST", path, signedQuery,
                "application/json", Long.toString(timestamp),
                nonce, signedBody);
        String signature = ContractV1.sign(secret(), fixture);
        String uri = baseUrl() + path
                + (wireQuery == null ? "" : "?" + wireQuery);

        return HttpRequest.newBuilder(URI.create(uri))
                .timeout(Duration.ofSeconds(10))
                .header("Content-Type", "application/json")
                .header("X-HMAC-Version", "hmac-v1")
                .header("X-HMAC-Key-Id", keyId())
                .header("X-HMAC-Algorithm", wireAlgorithm)
                .header("X-HMAC-Timestamp", Long.toString(timestamp))
                .header("X-HMAC-Nonce", nonce)
                .header("X-HMAC-Signature", signature)
                .POST(HttpRequest.BodyPublishers.ofByteArray(sentBody))
                .build();
    }

    private static HttpRequest orders(
            String wireQuery, String signedQuery,
            byte[] signedBody, byte[] sentBody,
            long timestamp, String nonce, String wireAlgorithm) {
        return signedRequest("/contract-test/orders",
                wireQuery, signedQuery, signedBody, sentBody,
                timestamp, nonce, wireAlgorithm);
    }

    private static int status(HttpRequest request) throws Exception {
        return HTTP.send(
                request, HttpResponse.BodyHandlers.discarding())
                .statusCode();
    }

    @Test
    void validHmacThroughGateway() throws Exception {
        byte[] body = utf8("{\"amount\":100000}");
        long now = Instant.now().getEpochSecond();
        assertEquals(204, status(orders(
                "currency=VND&orderId=o-123",
                "currency=VND&orderId=o-123",
                body, body, now, nonce(), "HMAC-SHA256")));
    }

    @Test
    void reorderedQueryCanBeEquivalent() throws Exception {
        byte[] body = utf8("{\"amount\":100000}");
        long now = Instant.now().getEpochSecond();
        assertEquals(204, status(orders(
                "orderId=o-123&currency=VND",
                "currency=VND&orderId=o-123",
                body, body, now, nonce(), "HMAC-SHA256")));
    }

    @Test
    void changedBodyBeforeFirstSendIsRejected() throws Exception {
        byte[] original = utf8("{\"amount\":100000}");
        byte[] tampered = utf8("{\"amount\":900000}");
        long now = Instant.now().getEpochSecond();

        assertEquals(401, status(orders(
                "currency=VND&orderId=o-123",
                "currency=VND&orderId=o-123",
                original, tampered, now, nonce(), "HMAC-SHA256")));
    }

    @Test
    void changedQueryWithOldSignatureIsRejected() throws Exception {
        byte[] body = utf8("{\"amount\":100000}");
        long now = Instant.now().getEpochSecond();

        assertEquals(401, status(orders(
                "currency=USD&orderId=o-123",
                "currency=VND&orderId=o-123",
                body, body, now, nonce(), "HMAC-SHA256")));
    }

    @Test
    void expiredTimestampWithValidHmacIsRejected() throws Exception {
        byte[] body = utf8("{\"amount\":100000}");
        long expired = Instant.now().minusSeconds(360).getEpochSecond();

        // Chữ ký được tạo CHO timestamp đã hết hạn.
        assertEquals(401, status(orders(
                "currency=VND&orderId=o-123",
                "currency=VND&orderId=o-123",
                body, body, expired, nonce(), "HMAC-SHA256")));
    }

    @Test
    void sameRequestIsRejectedOnSecondAttempt() throws Exception {
        byte[] body = utf8("{\"amount\":100000}");
        HttpRequest request = orders(
                "currency=VND&orderId=o-123",
                "currency=VND&orderId=o-123",
                body, body, Instant.now().getEpochSecond(),
                nonce(), "HMAC-SHA256");

        assertEquals(204, status(request));
        assertEquals(401, status(request));
    }

    @Test
    void unknownAlgorithmIsNotAllowed() throws Exception {
        byte[] body = utf8("{\"amount\":100000}");
        assertEquals(401, status(orders(
                "currency=VND&orderId=o-123",
                "currency=VND&orderId=o-123",
                body, body, Instant.now().getEpochSecond(),
                nonce(), "none")));
    }

    @Test
    void validHmacWithoutPermissionIsForbidden() throws Exception {
        byte[] body = utf8("{\"probe\":true}");
        assertEquals(403, status(signedRequest(
                "/contract-test/forbidden", null, null,
                body, body, Instant.now().getEpochSecond(),
                nonce(), "HMAC-SHA256")));
    }

    @Test
    void concurrentDuplicateNonceIsAcceptedOnlyOnce()
            throws Exception {
        byte[] body = utf8("{\"amount\":100000}");
        HttpRequest request = orders(
                "currency=VND&orderId=o-123",
                "currency=VND&orderId=o-123",
                body, body, Instant.now().getEpochSecond(),
                nonce(), "HMAC-SHA256");

        CompletableFuture<Integer> first = HTTP.sendAsync(
                request, HttpResponse.BodyHandlers.discarding())
                .thenApply(HttpResponse::statusCode);
        CompletableFuture<Integer> second = HTTP.sendAsync(
                request, HttpResponse.BodyHandlers.discarding())
                .thenApply(HttpResponse::statusCode);
        CompletableFuture.allOf(first, second).join();

        List<Integer> results = List.of(first.join(), second.join());
        assertEquals(1L, results.stream()
                .filter(code -> code == 204).count());
        assertEquals(1L, results.stream()
                .filter(code -> code == 401).count());
    }
}
~~~

### 8.3. Những điều mã HTTP test **chưa** chứng minh

**Mã này dùng clock thực** để tạo request còn hạn. Trước khi chạy, CI runner và verifier phải đồng bộ UTC/NTP; unit tests cho điểm biên nên inject `Clock.fixed(...)` vào server, không dùng `Thread.sleep` rồi hy vọng đạt đúng `now - 300`.

**Concurrency test** chỉ gửi hai request đồng thời. Nó có thể cùng đi vào một instance và **chưa chứng minh** nonce store atomic giữa hai vùng. Cần staging infrastructure có routing/trace đến hai verifier độc lập, nhiều vòng chạy và quan sát kho nonce.

**Java HttpClient** kiểm tra cú pháp URI/header, nên không phát được mọi raw malformed request-target hoặc duplicate header cần thử. Các ca percent escape sai, newline injection hay header coalescing phải dùng harness có khả năng tạo request bytes ở tầng gateway/test proxy được ủy quyền, đồng thời ghi nhận request thực sự trên wire. Đừng coi một test không thể phát input là test "pass".

**Authorization phải có chữ ký đúng cho path bị cấm.** Nếu ký path allowed rồi sửa sang path forbidden, kết quả 401 là lỗi HMAC, không phải bằng chứng authorization đã hoạt động. Vì thế test `validHmacWithoutPermissionIsForbidden` ký chính path forbidden.

**Không log HMAC secret hoặc full signature.** Nếu cần debug, ghi request ID, hợp đồng, build/gateway version, reason nội bộ và hash canonical trên fixture không nhạy cảm.

## 9. Các kịch bản contract nâng cao cần dựng ở staging

Black-box HTTP tests trong mục 8 kiểm tra những đường quan trọng nhất. Để triển khai HMAC thật, dự án phải có thêm các bài kiểm thử về policy, khôi phục và dữ liệu được xử lý sau gateway. Những tình huống sau nên dùng **admin test fixtures/fault injection đã được phê duyệt**, không sửa credential, traffic hay service production trực tiếp.

### 9.1. Key rotation và revocation

Trình tự bài test:

1. Tạo hai credential sandbox cho cùng client: `key-old` và `key-new`, mỗi key có **secret riêng** và algorithm đã đăng ký.
2. Trong planned overlap được duyệt, ký hai request với timestamp/nonce **riêng biệt**. Xác minh cả hai được nhận trên route allowed.
3. Chuyển policy `key-old` sang `REVOKED` bằng test admin API (không dùng chung key fixture với production).
4. **Ký một request hoàn toàn mới bằng secret old**, timestamp hiện tại, nonce chưa dùng. Kỳ vọng từ chối **credential**, không chỉ thất bại do timestamp/replay.
5. Ký request mới bằng `key-new`, xác minh vẫn được nhận và quyền resource/tenant không bị thay đổi.
6. Lặp lại qua nhiều gateway/verifier/region; đo delay giữa control-plane revoke và khi mọi data plane từ chối.
7. Nếu gặp cache stale, đánh dấu lỗi **revocation propagation**, không "sửa" bằng cách rollback key đã thu hồi.

Nếu key bị lộ, không duy trì overlap như planned rotation: phải cô lập client, revoke secret nguy cơ và phát credential mới qua môi trường tin cậy.

### 9.2. Thuật toán và version downgrade

Gửi các request có chữ ký đúng hoặc metadata cố tình mâu thuẫn:

| Tình huống | Kỳ vọng |
|---|---|
| `key-old` chỉ được cấp `HMAC-SHA256` nhưng wire ghi `HMAC-SHA512` | Reject per-key policy |
| Wire algorithm `none`, `HMAC-SHA1`, alias hoặc giá trị có whitespace | Reject global allowlist/cú pháp |
| `X-HMAC-Version: hmac-v0` nhưng credential chỉ cấp `hmac-v1` | Reject |
| Client gửi `hmac-v2` nhưng HMAC được tạo bằng format v1 | Reject; không fallback ngầm |
| Cùng secret nhưng thử mọi algorithm/canonical format đến khi tag khớp | **Không được tồn tại** trong verifier |
| Key đã revoke nhưng HMAC tính đúng theo format cũ | Reject credential |

Phiên bản và algorithm phải được **ràng buộc trong canonical bytes**, đồng thời so với metadata credential. Việc có hai algorithm trong global allowlist không có nghĩa client được tự chọn algorithm bất kỳ cho cùng key.

### 9.3. Gateway normalization và parser differential

Tạo cùng bộ fixture đi theo hai tuyến: **direct-to-verifier ở staging** và **via gateway staging**. Ghi canonical digest ở client, gateway (nếu có), verifier cùng giá trị mà business handler thực nhận.

| Biến thể | Điều phải đo |
|---|---|
| Đảo thứ tự unique query keys | HMAC vẫn đúng nếu canonical equivalence được contract cho phép |
| Query `a=1&%61=2` | Bị từ chối dù framework chọn first/last |
| `q=hello+world` so với `q=hello%20world` | Khác nghĩa và khác MAC theo contract |
| `%2F` so với `%252F` | Decode đúng một lần |
| Header `Content-Type` bị normalize hoặc đổi giá trị | Bind với dữ liệu thực handler sử dụng |
| HTTP/1.1 ↔ HTTP/2, forwarded headers | Routing, authority và signed metadata thống nhất |
| Body bị gzip decompress hoặc JSON reserialize | Không xử lý representation khác dữ liệu đã ký |
| URL path normalization `/a/../admin`, encoded slash | Reject theo path policy, không route nhầm |

Nếu một request có HMAC đúng nhưng handler thấy một body/query khác về ngữ nghĩa so với verifier, đó là **lỗi security correctness** ngay cả khi mọi test MAC cơ bản xanh. Với API thực có tenant routing từ `Host`, cần ký authority hoặc áp dụng ranh giới tin cậy đã chứng minh; hợp đồng mẫu không tự bảo vệ trường đó.

### 9.4. Nonce store lỗi, retry và idempotency

- **Atomic concurrency:** hai request cùng keyId+nonce, HMAC và timestamp đúng phải có tối đa một lần được nhận ngay cả trên hai node khác nhau.
- **Dependency outage:** dùng fault injection làm nonce store timeout. Verifier phải **fail closed**; không chuyển sang mỗi pod một cache in-memory, không thực hiện side effect.
- **TTL:** nonce phải tồn tại đủ lâu qua toàn bộ freshness window có margin cho clock drift; sau TTL mà timestamp vẫn hợp lệ không được tạo replay hole.
- **Retry:** gửi lại nguyên request với cùng nonce có thể bị từ chối. Nếu nghiệp vụ cần retry an toàn, cần `Idempotency-Key` và cơ chế lưu kết quả giao dịch có ràng buộc principal/request riêng; **không** biến nonce thành token dùng nhiều lần.
- **Replay qua rotation:** phạm vi nonce được xác định theo verified credential/client policy; không để việc thay tên keyId nhưng tái sử dụng secret và phạm vi không rõ tạo đường bypass.

Một lệnh Redis minh họa atomic claim là:

~~~text
SET hmac:nonce:<verified-credential-scope>:<nonce-digest> 1 NX EX 600
~~~

TTL 600 giây chỉ là ví dụ. Giá trị thực phụ thuộc cửa sổ tuổi request, future skew, clock skew và cách đồng bộ nhiều vùng. Lệnh phải chạy trên miền state chung; tách `GET` rồi `SET` thành hai thao tác là anti-pattern race condition.

## 10. Thiết kế test có thể tái lập trong CI

### 10.1. Tách hai tầng chạy

**Tầng A — offline, chạy mỗi PR:** Compile Java 17, JUnit Jupiter; chạy `ContractV1OfflineTest`, golden byte vectors, malformed/duplicate query và property tests có seed cố định. Không cần network hoặc secret ngoài fixture test đã công bố an toàn.

**Tầng B — integration, chạy trên sandbox được provision:** Chạy `HmacWireContractIT` qua gateway, dùng CI secrets, một fixture client có scope hạn chế và các route không có side effect. Trong Maven, tên class `*IT` thường được chạy qua **Failsafe** khi project đã cấu hình plugin ở pha `integration-test`/`verify`; nếu project dùng Gradle, cấu hình source set/task `integrationTest` riêng. Không mặc định rằng lệnh chạy unit test sẽ tự phát hiện `*IT`.

Ví dụ lệnh minh họa cho project **đã có cấu hình tương ứng** (không thực thi trong bước viết bài):

~~~bash
# Maven: offline JUnit tests theo cấu hình Surefire
mvn -Dtest=ContractV1OfflineTest test

# Maven: tích hợp nếu dự án đã cấu hình Failsafe cho *IT
mvn verify

# Gradle tương đương nếu project có task integrationTest
./gradlew test integrationTest
~~~

Nếu thiếu `HMAC_CONTRACT_BASE_URL`, `HMAC_CONTRACT_KEY_ID` hoặc `HMAC_CONTRACT_KEY_HEX` thì staging test phải **fail fast** với thông báo cấu hình thiếu. Không biến toàn bộ integration test thành `@Disabled` hoặc silently skip rồi báo CI thành công.

### 10.2. Test data, reset state và tránh flaky

- Sinh **nonce mới cho mỗi ca**; khi test replay thì cố ý dùng lại chính request và nonce đó.
- Dùng dữ liệu test không nhạy cảm; không reuse secret production; không log HMAC signature hay nguyên canonical payload production.
- Phân biệt **fixed clock unit tests** với **live clock integration tests**. Ở HTTP tests, chọn timestamp cách biên một khoảng an toàn để tránh network delay làm test false fail.
- Không chạy trên endpoint tạo giao dịch thật; sandbox handler có thể trả 204 mà không lưu gì, hoặc fixture được reset theo test run ID.
- Dùng client sandbox cô lập theo pipeline nếu các test khác cùng lúc dùng nonce/credential store; tránh credential bị revoke giữa hai test.
- Kiểm tra môi trường trước khi chạy: policy version, gateway build, sandbox key status, clock sync và nonce store health.
- Lưu seed/failing input đã tối giản cho fuzz tests, request ID của failure và test correlation ID, nhưng không lưu secret hoặc full signature.
- Với concurrency/fault tests, chạy theo job riêng có resource control; một lần 204/401 ở cùng pod không đủ chứng minh tính atomic multi-region.

### 10.3. Mẫu báo cáo contract test

~~~text
Contract suite: HMAC Request Authentication v1
Environment: staging
Change/build: <build-id>
Client fixture: sandbox-client
Gateway build: <gateway-build-id>
Verifier build: <verifier-build-id>
Credential policy version: <policy-version>
Nonce cluster: <test-cluster-alias>
Clock basis: UTC / NTP verified
Offline vectors: <passed>/<total>
HTTP black-box cases: <passed>/<total>
Multi-instance replay probes: <passed>/<total>
Revocation propagation: <measured-and-verified>
Authorization negative tests: <passed>/<total>
Open differences: <issue-ids>
Final decision: PASS / FAIL / BLOCKED
Evidence location: <restricted-test-report-reference>
~~~

Mỗi testcase nên có **ID, input category, expected behavior, actual behavior, internal reason (nếu có), request ID, verifier instance, gateway version** và trạng thái được điều tra. Tránh ghi body nhạy cảm, shared secret và full signature vào test report.

## 11. Definition of Done và rubric đánh giá

Một dự án được coi là hoàn thành kỹ thuật khi những điều sau được kiểm chứng:

- [ ] Contract `hmac-v1` mô tả đầy đủ **11 dòng canonical**, UTF-8/LF, empty query, đúng HMAC tag encoding và version/key/algorithm binding.
- [ ] Có golden vectors **tính độc lập**, chứa cả canonical byte hex và expected HMAC tag từ key test.
- [ ] Offline JUnit chạy trên dữ liệu hợp lệ/không hợp lệ, duplicate after decode, percent-encoding, Unicode và giới hạn tài nguyên.
- [ ] HTTP black-box tests dùng **signer tách khỏi server**, chạy thực sự qua gateway đã biết build.
- [ ] Sửa body/query **trước lần gửi đầu với nonce mới** bị từ chối do invalid MAC; không nhầm với replay.
- [ ] Expired/future timestamp được **ký lại đúng** và reject do freshness; kiểm tra biên bằng fixed clock.
- [ ] Replay đồng thời được kiểm tra trên ít nhất hai verifier chia sẻ store atomic; outage fail closed.
- [ ] Unknown/revoked credential, algorithm mismatch, version downgrade và key rotation được kiểm chứng độc lập.
- [ ] HMAC hợp lệ nhưng principal không đủ quyền bị từ chối ở **authorization**, không phải vì chữ ký sai.
- [ ] Gateway và handler sử dụng cùng ngữ nghĩa path/query/headers/body đã được ký.
- [ ] Test suite tách offline/integration, có evidence và không chứa secret production.
- [ ] Mọi sự khác biệt được ghi thành issue/test regression, có owner và cách khắc phục.

Rubric tham khảo (tổng 100 điểm):

| Phần | Điểm |
|---|---:|
| Đặc tả canonical format, body/header/query policy rõ | 20 |
| Golden vectors độc lập và offline tests đủ các nhóm | 20 |
| HTTP black-box contract test thực sự qua gateway | 20 |
| Negative tests không bị replay/signature/timestamp che nguyên nhân | 15 |
| Key rotation, nonce atomic, algorithm policy và authZ | 15 |
| CI reproducibility, report/evidence và bảo vệ secret | 10 |

**Không chấp nhận** bộ test chỉ gọi một hàm signer và verifier dùng chung implementation, hoặc chỉ kiểm tra `2xx` trên một request bình thường.

## 12. Bài tập mở rộng và câu hỏi review

1. **Đổi parser:** Thêm client thứ hai viết bằng ngôn ngữ khác Java. Hai client phải tạo **cùng canonical bytes** từ một tập golden vectors, kể cả `%2f`, `%252F`, `+`, body rỗng và UTF-8.
2. **Thử lỗi có chủ ý:** Tạo một verifier test cố tình bỏ body digest khỏi canonical request. Chạy CT-03 để chứng minh test mới phát hiện việc sửa amount; nếu test vẫn xanh, phân tích việc nonce/timestamp hoặc cách gửi fixture đang che lấp lỗi.
3. **Proxy rewrite:** Cho staging gateway thay query order và một signed header. Chứng minh biến thể nào tương đương theo contract và biến thể nào phải reject.
4. **Key compromise:** Revoke key cũ, thử ký request mới bằng đúng secret cũ. Đo propagation trên mọi instance và đối chiếu log/trace mà không in secret.
5. **Policy evolution:** Thiết kế `hmac-v2` thay cách canonical headers hoặc cho phép repeated query keys; tạo test vectors độc lập, chiến lược version per-key và lộ trình dừng v1 không fallback.
6. **Authorization:** Với HMAC hợp lệ, thử truy cập resource khác tenant. Giải thích vì sao chữ ký đúng không thay thế `PermissionEvaluator`, ACL hoặc policy ở service layer.

**Kết luận:** Contract test cho HMAC không phải chỉ là "ký một chuỗi rồi xem server có trả 200 không". Bộ test đáng tin phải khóa chặt **byte-level canonical format**, có signer/verifier độc lập, thử cả data tampering và malformed request, xác minh freshness/nonce/credential lifecycle, đo sự nhất quán qua proxy/gateway và chứng minh **xác thực không được nhầm với phân quyền**.



