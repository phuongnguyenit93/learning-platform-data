# Canonicalization contract: kiểm thử hợp đồng chuẩn hóa request HMAC

## 1. Vì sao canonicalization là một hợp đồng cần kiểm thử?

Trong mô-đun `SECURITY_AUTHENTICATION_HMAC_REQUEST_AUTHENTICATION`, HTTP client ký request bằng **HMAC với shared secret**, còn verifier dùng cùng secret để tính lại MAC. HMAC chỉ xác nhận tính toàn vẹn của **chuỗi byte thực sự được đưa vào MAC**; nếu client và server xây chuỗi đó khác nhau dù chỉ một byte, chữ ký hợp lệ ở phía client sẽ bị từ chối.

Một request đi qua SDK, CDN, WAF, gateway, reverse proxy, Servlet container hoặc Reactor Netty có thể bị biến đổi trước khi đến bộ xác thực. Ví dụ: gateway rewrite path, sắp xếp query, chuyển HTTP/2 sang HTTP/1.1, gộp header hoặc giải nén body. Mỗi thay đổi có thể khiến client/server tạo hai canonical requests khác nhau.

**Canonicalization contract** là bộ quy tắc có version xác định **chính xác byte nào được ký và cách tạo những byte ấy**. **Contract testing** kiểm tra độc lập rằng mọi producer (SDK/client) và consumer (gateway/verifier/backend) cùng triển khai quy tắc đó, kể cả khi thay đổi ngôn ngữ, framework, hạ tầng mạng hoặc phiên bản.

Bài thuộc chương **Contract testing**; nội dung kết nối đầy đủ mục tiêu module: method, URI, signed headers/body; shared secret/key ID; timestamp/nonce chống replay; key rotation; proxy/gateway; và phân biệt **authentication** với **authorization**.

### Vấn đề cần phát hiện

- Client và server xử lý `%2F`, `%2f` hoặc `/` khác nhau.
- Query `a=1&b=2` bị proxy đổi thành `b=2&a=1` mà hợp đồng không cho phép.
- Thư viện JSON serialize lại body làm thay byte đã ký.
- Header có hai giá trị hoặc có khoảng trắng, các bên chọn giá trị khác nhau.
- HTTP/2 `:path` và Servlet `getRequestURI()` không cùng cách biểu diễn.
- Gateway verify trước rewrite nhưng backend lại verify trên internal target.
- Version V2 thay đổi thuật toán canonicalization mà không có hợp đồng chuyển đổi rõ.
- Positive test cùng dùng một helper sai ở cả signer/verifier nên vẫn PASS.

**Nguyên tắc:** không thể sửa lỗi tương thích bằng cách “thử vài cách chuẩn hóa” đến khi chữ ký khớp. Một verifier phải chọn **đúng một contract đã công bố cho request** và kiểm tra đúng quy tắc của contract đó.

## 2. Phân biệt HTTP semantic equivalence và byte equality

Hai HTTP requests có thể cùng ý nghĩa ở tầng ứng dụng, nhưng HMAC trên canonical bytes vẫn khác.

| Biến thể A | Biến thể B | Có thể cùng nghĩa nghiệp vụ? | Kết quả theo raw-byte contract |
| --- | --- | --- | --- |
| `/orders?a=1&b=2` | `/orders?b=2&a=1` | Có, tùy ứng dụng | Khác bytes |
| `%2F` | `%2f` | Có thể cùng ký tự sau decode | Khác bytes |
| `x=a+b` | `x=a%20b` | Có thể cùng diễn giải form | Khác bytes |
| `{"a":1,"b":2}` | `{"b":2,"a":1}` | Thường có | Body hash khác |
| Body rỗng | Body `{}` | Có thể cùng object mặc định | Digest khác |
| `LF` | `CRLF` | Có thể cùng text | Digest khác |
| Header name `Content-Type` | `content-type` | Tương đương theo HTTP | Có thể canonical giống nếu contract lower-case tên |
| Header value có OWS ở hai đầu | Value không có OWS | Có thể tương đương theo quy tắc HTTP | Tùy contract có trim OWS hay không |
| `application/json` | `application/json; charset=utf-8` | Có thể cùng media type | Khác theo contract V1 minh họa |

Không tự áp `URLDecoder` cho raw query: nó có thể đổi `+` thành khoảng trắng hoặc biến đổi percent-encoding. Tương tự, `URI.normalize()` hoặc parse-serialize URL có thể làm mất thông tin cần ký.

Có hai họ giao thức hợp lệ:

1. **Raw representation signing:** ký raw request-target và raw body tại một trust boundary cố định, với một số header được chuẩn hóa cụ thể.
2. **Semantic canonicalization:** định nghĩa thuật toán chuyển các biểu diễn có nghĩa tương đương thành một representation canonical (ví dụ sort query, chuẩn hóa Unicode/JSON).

Bài sử dụng **hợp đồng V1 thiên về raw bytes** để dễ chỉ ra ranh giới. Có thể thiết kế họ thứ hai nhưng phải đặc tả nghiêm ngặt duplicate query, JSON số, Unicode, percent-encoding và mọi edge case; không được dựa vào “hành vi mặc định của thư viện”.

## 3. Ranh giới tin cậy: ký request ở thời điểm nào?

~~~mermaid
flowchart TD
    C["Client SDK ký HTTP request"] --> G["Public Gateway / Proxy"]
    G --> R["Routing / URI rewrite / body transformation"]
    R --> S["Spring MVC hoặc WebFlux verifier"]
    G -. "Có thể verify HMAC tại edge" .-> E["Gateway authentication decision"]
    E --> A["mTLS + signed internal assertion"]
    A --> S
    S --> P["Principal + Authorization"]
    P --> B["Business handler"]
~~~

Cần chốt **một** trong hai mô hình:

**A. Verifier ở backend.** Hợp đồng nói rõ backend nhận raw target nào; gateway phải bảo toàn thông tin được ký hoặc cung cấp metadata gốc qua **kênh đã xác thực**, sau khi xóa header giả do client gửi. Backend không được đọc `X-Original-URI` do Internet client tự khai rồi coi đó là target tin cậy.

**B. Verifier ở gateway.** Gateway xác minh canonical request **trước hoặc tại điểm transform đã quy định**, sau đó phát hành bằng chứng nội bộ cho backend. Backend cần xác minh gateway identity (ví dụ mTLS), issuer, audience, thời hạn, method/route/body binding và authorization; không chỉ tin `X-Authenticated-Client` thuần văn bản.

Bộ test phải ghi rõ **measurement/verification authority**. Không gọi request được backend trả 403 do thiếu quyền là “canonicalization mismatch”; authentication và authorization có outcome riêng.

## 4. Đặc tả hợp đồng HMAC-REQUEST-V1 minh họa

Để có dữ liệu kiểm thử nhất quán, ta đặt một **contract minh họa, không phải tiêu chuẩn HMAC chung**:

| Thuộc tính | Quy tắc V1 |
| --- | --- |
| Contract ID | `HMAC-REQUEST-V1` |
| HMAC algorithm | `HmacSHA256` trên canonical UTF-8 bytes |
| Signature wire encoding | Base64 chuẩn RFC 4648 có padding `=` (thí dụ) |
| Contract selection | Header `X-Signature-Version: HMAC-REQUEST-V1`, đúng một giá trị |
| Domain separation | Dòng đầu canonical là chính contract ID |
| HTTP method | Uppercase ASCII; trong ví dụ POST |
| Target | Origin-form `rawPath[?rawQuery]` tại **điểm verify đã thống nhất**, giữ nguyên thứ tự và percent bytes |
| Query | Không sort, không decode/encode lại, giữ duplicate và thứ tự nguyên văn |
| Signed headers | `Content-Type`, `X-Client-Id`, `X-Key-Id`, `X-Tenant-Id`, `X-Timestamp`, `X-Nonce` |
| Header names trong canonical | Lowercase ASCII, theo thứ tự cố định trong bảng |
| Header values | Đúng một giá trị mỗi tên, trim ASCII SP/HTAB ở hai đầu; không thay whitespace bên trong |
| Media type test fixture | Yêu cầu chính xác `application/json` sau trim; giá trị khác bị từ chối theo profile V1 này |
| Timestamp | UTC dạng `yyyy-MM-dd'T'HH:mm:ss'Z'`, không fractional seconds |
| Nonce | UUIDv4 dạng lowercase chuẩn, ký như text |
| Body | SHA-256 của **raw body bytes sau HTTP transfer decoding, trước mọi chuyển đổi ứng dụng đã không được hợp đồng cho phép** |
| Body digest | Hex lowercase 64 ký tự |
| Charset canonical | UTF-8; method/target/ID/header value trong profile ví dụ dùng ASCII |
| Line separator | Byte `0x0A` (LF) |
| Trailing separator | **Không có LF cuối** |
| Missing signed field | Từ chối, không âm thầm thay bằng chuỗi rỗng |
| Duplicate signed headers | Từ chối, kể cả khác nhau chỉ ở case |
| Signature header | `X-Signature` không nằm trong chuỗi ký vì sẽ tạo phụ thuộc vòng |
| Empty body | SHA-256 của mảng byte rỗng; vẫn có dòng digest |

Version trong header chọn canonicalizer trong **allowlist**, còn dòng đầu canonical **ràng buộc version vào MAC**. Một request đổi version nhưng giữ signature cũ phải bị từ chối, không được fallback tự động sang phiên bản khác.

**Phạm vi demo:** ví dụ chỉ minh họa `POST application/json`. Sản phẩm thực tế cần profile riêng cho GET/body rỗng, form/multipart, các HTTP methods khác hoặc signed Host nếu cần. Không được hiểu các giới hạn của demo là quy tắc HTTP toàn cầu.

### Thứ tự dòng canonical bắt buộc

~~~text
HMAC-REQUEST-V1
<UPPERCASE_METHOD>
<RAW_TARGET>
content-type:<normalized-content-type>
x-client-id:<normalized-client-id>
x-key-id:<normalized-key-id>
x-tenant-id:<normalized-tenant-id>
x-timestamp:<normalized-timestamp>
x-nonce:<normalized-nonce>
<lowercase-sha256-hex-of-raw-body>
~~~

Ký tự `<...>` trong khối trên là placeholder; khi xây thực tế phải thay bằng bytes/giá trị tương ứng. **Không thêm một LF cuối** dòng digest. Các header có thứ tự cố định; không duyệt `HashMap` và sử dụng thứ tự iteration ngẫu nhiên.

## 5. Golden vector số 1: POST body rỗng

Dùng request minh họa:

~~~http
POST /api/orders?tag=a&tag=b HTTP/1.1
Host: api.example.test
Content-Type: application/json
X-Signature-Version: HMAC-REQUEST-V1
X-Client-Id: client-a
X-Key-Id: client-a-k4
X-Tenant-Id: tenant-a
X-Timestamp: 2026-11-28T03:00:00Z
X-Nonce: 34cfb0e7-2d64-4f43-b45c-7f630f7a1e31
X-Signature: <base64-signature>

~~~

Body là **0 byte**, không phải `{}`, `null` hay một dấu xuống dòng.

SHA-256 của mảng byte rỗng là hằng số đã biết:

~~~text
e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
~~~

Canonical text cuối cùng phải chính xác là:

~~~text
HMAC-REQUEST-V1
POST
/api/orders?tag=a&tag=b
content-type:application/json
x-client-id:client-a
x-key-id:client-a-k4
x-tenant-id:tenant-a
x-timestamp:2026-11-28T03:00:00Z
x-nonce:34cfb0e7-2d64-4f43-b45c-7f630f7a1e31
e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
~~~

Trong bộ test, `expectedCanonicalUtf8` phải là literal ở fixture **độc lập**, không được gọi lại chính canonicalizer đang test để tạo expected output. So sánh **`byte[]`**, không chỉ so sánh một `String` đã normalize.

Signature ở HTTP sample là placeholder vì chưa đưa secret test và giá trị MAC đã được tính/đối chiếu độc lập. Đừng biến placeholder thành “golden HMAC vector” giả. Có thể dùng literal canonical text ở trên như **golden canonical-byte vector**, rồi bổ sung `expectedSignatureBase64` tính bởi một implementation tham chiếu độc lập.

## 6. Golden vectors phải kiểm tra những lớp nào?

Một suite conformance gồm ít nhất ba lớp:

| Lớp | Input | Expected artifact | Phát hiện |
| --- | --- | --- | --- |
| Canonicalization | Method, raw target, signed headers, body bytes | Exact canonical UTF-8 bytes | Lỗi chuẩn hóa/encoding/order |
| Cryptographic signing | Secret bytes + golden canonical bytes | Exact 32-byte HMAC-SHA256 + Base64 | Lỗi thuật toán, secret/encoding |
| HTTP verification | HTTP request + registry + Clock/nonce fixture | Accepted/rejected, reason nội bộ, side effect | Lỗi filter, parser, lookup, gateway, replay |

Các kiểm thử có thể pass hoặc fail độc lập. Ví dụ MAC primitive có thể đúng nhưng canonical query bị sort sai; ngược lại canonical bytes đúng mà signer dùng `SHA256(secret || message)` thay HMAC thì signature sai.

### MAC primitive test với vector công khai

Có thể dùng vector HMAC-SHA256 đã được công bố rộng rãi: key gồm 20 bytes `0x0b`, message ASCII `Hi There` và expected digest:

~~~text
b0344c61d8db38535ca8afceaf0bf12b881dc200c9833da726e9376c2e32cff7
~~~

Đây là vector của **primitive HMAC-SHA256**, không phải signature cho request `HMAC-REQUEST-V1`. Không nhập nhằng hai thứ: vector primitive chứng minh phần Mac, còn golden canonical vector chứng minh phần hợp đồng request.

### Format fixture đề xuất

Một fixture có thể lưu dưới dạng JSON/YAML do team quản lý, gồm:

~~~json
{
  "id": "v1-empty-post-001",
  "contract": "HMAC-REQUEST-V1",
  "request": {
    "method": "POST",
    "rawTarget": "/api/orders?tag=a&tag=b",
    "headers": [
      ["Content-Type", "application/json"],
      ["X-Client-Id", "client-a"],
      ["X-Key-Id", "client-a-k4"],
      ["X-Tenant-Id", "tenant-a"],
      ["X-Timestamp", "2026-11-28T03:00:00Z"],
      ["X-Nonce", "34cfb0e7-2d64-4f43-b45c-7f630f7a1e31"]
    ],
    "bodyBase64": ""
  },
  "expectedCanonicalSha256": "<digest-of-canonical-bytes>",
  "expectedCanonicalText": "<exact-text-in-golden-vector>",
  "expectedHmacBase64": "<independently-computed-value>"
}
~~~

Các trường expected là placeholder **cho đến khi được tính, soát chéo và cố định**. Đừng lưu file fixture giả với expected placeholder rồi coi là test PASS. Nếu body là binary, luôn dùng `bodyBase64` để fixture không làm thay bytes do editor/newline/charset.

## 7. Xây canonicalizer Java 17 thuần hàm và có giới hạn input

Bên dưới là một implementation minh họa **phần dựng canonical bytes**, tách khỏi HTTP adapters. `headers` là cấu trúc lấy từ request, giữ được nhiều giá trị cùng tên. Phần adapter phải bảo đảm đã lấy đúng **raw target từ trust boundary**, không từ một header do client tùy ý chọn.

~~~java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.ArrayList;
import java.util.HexFormat;
import java.util.List;
import java.util.Map;
import java.util.Objects;

final class HmacCanonicalV1 {
    static final String VERSION = "HMAC-REQUEST-V1";

    private static final List<String> SIGNED_HEADERS = List.of(
        "content-type",
        "x-client-id",
        "x-key-id",
        "x-tenant-id",
        "x-timestamp",
        "x-nonce"
    );

    private HmacCanonicalV1() {}

    static byte[] build(
            String method,
            String rawTarget,
            Map<String, List<String>> headers,
            byte[] rawBody) {

        Objects.requireNonNull(headers);
        Objects.requireNonNull(rawBody);

        // Chỉ là profile POST/JSON minh họa;
        // mở rộng method qua version/profile mới.
        if (!"POST".equals(method)) {
            throw new IllegalArgumentException("method_invalid");
        }
        if (rawTarget == null
                || !rawTarget.startsWith("/")
                || rawTarget.indexOf('#') >= 0
                || hasControl(rawTarget)) {
            throw new IllegalArgumentException("target_invalid");
        }

        String version = singleHeader(
            headers, "x-signature-version");
        if (!VERSION.equals(version)) {
            throw new IllegalArgumentException("version_invalid");
        }

        List<String> lines = new ArrayList<>();
        lines.add(VERSION);
        lines.add(method);
        lines.add(rawTarget);

        for (String name : SIGNED_HEADERS) {
            String value = singleHeader(headers, name);
            if ("content-type".equals(name)
                    && !"application/json".equals(value)) {
                throw new IllegalArgumentException(
                    "content_type_invalid");
            }
            lines.add(name + ":" + value);
        }
        lines.add(sha256Hex(rawBody));

        return String.join("\n", lines)
            .getBytes(StandardCharsets.UTF_8);
    }

    private static String singleHeader(
            Map<String, List<String>> headers,
            String wanted) {
        List<String> found = new ArrayList<>();

        // HTTP header name case-insensitive; không được để
        // hai key khác case tạo hai cách hiểu khác nhau.
        headers.forEach((name, values) -> {
            if (name.equalsIgnoreCase(wanted)
                    && values != null) {
                found.addAll(values);
            }
        });

        if (found.size() != 1 || found.get(0) == null) {
            throw new IllegalArgumentException(
                "signed_header_missing_or_duplicate");
        }

        String value = trimOws(found.get(0));
        if (value.isEmpty() || hasControl(value)) {
            throw new IllegalArgumentException(
                "signed_header_invalid");
        }
        return value;
    }

    // Chỉ trim ASCII OWS: SP và HTAB, không dùng
    // strip()/trim() tùy tiện để normalize Unicode.
    private static String trimOws(String s) {
        int start = 0;
        int end = s.length();
        while (start < end
                && (s.charAt(start) == ' '
                || s.charAt(start) == '\t')) {
            start++;
        }
        while (end > start
                && (s.charAt(end - 1) == ' '
                || s.charAt(end - 1) == '\t')) {
            end--;
        }
        return s.substring(start, end);
    }

    private static boolean hasControl(String s) {
        for (int i = 0; i < s.length(); i++) {
            char c = s.charAt(i);
            if (c < 0x20 || c == 0x7F) return true;
        }
        return false;
    }

    private static String sha256Hex(byte[] bytes) {
        try {
            return HexFormat.of().formatHex(
                MessageDigest.getInstance("SHA-256")
                    .digest(bytes));
        } catch (NoSuchAlgorithmException ex) {
            throw new IllegalStateException(
                "SHA-256 unavailable", ex);
        }
    }
}
~~~

**Giới hạn quan trọng của mẫu:** đây là canonicalizer minh họa, **không phải HTTP security parser đầy đủ**. Adapter production còn phải validate raw-target grammar/percent escapes và URI authority, kiểm tra format ký tự ASCII/UTF-8/ID/timestamp/nonce, header length/count, signed header duplication ở lớp proxy, route allowlist, body size limit và cách framework xử lý header comma-join. Trong các HTTP APIs, một số thư viện có thể gộp duplicate values **trước khi code Java nhận được**: cần từ chối ambiguity ở tầng còn quan sát được raw headers.

`hasControl` ở đây cố ý cấm HTAB **bên trong** signed header value (sau khi trim OWS), để tránh hai cách diễn giải. Hợp đồng cần nói rõ điều này; nếu HTTP client thật có tab trong giá trị, nó bị reject theo profile này. Các header identity/timestamp phải được validate bằng grammar chặt ở adapter, không chỉ dựa vào `hasControl`.

## 8. JUnit 5 golden-byte test không phụ thuộc signer

Test sau giữ `expectedCanonical` thành một literal **được viết độc lập** với implementation, dùng body rỗng để tận dụng SHA-256 vector đã biết:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.nio.charset.StandardCharsets;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;

class HmacCanonicalV1Test {

    private Map<String, List<String>> headers() {
        Map<String, List<String>> h = new LinkedHashMap<>();
        h.put("Content-Type", List.of(" application/json "));
        h.put("X-Signature-Version",
            List.of("HMAC-REQUEST-V1"));
        h.put("X-Client-Id", List.of("client-a"));
        h.put("X-Key-Id", List.of("client-a-k4"));
        h.put("X-Tenant-Id", List.of("tenant-a"));
        h.put("X-Timestamp",
            List.of("2026-11-28T03:00:00Z"));
        h.put("X-Nonce", List.of(
            "34cfb0e7-2d64-4f43-b45c-7f630f7a1e31"));
        return h;
    }

    @Test
    void producesExactGoldenUtf8Bytes() {
        String expected = String.join("\n",
            "HMAC-REQUEST-V1",
            "POST",
            "/api/orders?tag=a&tag=b",
            "content-type:application/json",
            "x-client-id:client-a",
            "x-key-id:client-a-k4",
            "x-tenant-id:tenant-a",
            "x-timestamp:2026-11-28T03:00:00Z",
            "x-nonce:34cfb0e7-2d64-4f43-b45c-7f630f7a1e31",
            "e3b0c44298fc1c149afbf4c8996fb92427"
                + "ae41e4649b934ca495991b7852b855"
        );

        byte[] actual = HmacCanonicalV1.build(
            "POST", "/api/orders?tag=a&tag=b",
            headers(), new byte[0]);

        assertArrayEquals(
            expected.getBytes(StandardCharsets.UTF_8),
            actual);
    }

    @Test
    void rawQueryOrderingIsPartOfSignatureContract() {
        byte[] a = HmacCanonicalV1.build(
            "POST", "/api/orders?a=1&b=2",
            headers(), new byte[0]);
        byte[] b = HmacCanonicalV1.build(
            "POST", "/api/orders?b=2&a=1",
            headers(), new byte[0]);

        assertFalse(java.util.Arrays.equals(a, b));
    }

    @Test
    void rejectsDuplicateSignedHeaderEvenWithDifferentCase() {
        Map<String, List<String>> h = headers();
        h.put("x-key-id", List.of("client-a-k4"));

        assertThrows(IllegalArgumentException.class,
            () -> HmacCanonicalV1.build(
                "POST", "/api/orders", h, new byte[0]));
    }

    @Test
    void rejectsDifferentVersionWithoutFallback() {
        Map<String, List<String>> h = headers();
        h.put("X-Signature-Version",
            List.of("HMAC-REQUEST-V2"));

        assertThrows(IllegalArgumentException.class,
            () -> HmacCanonicalV1.build(
                "POST", "/api/orders", h, new byte[0]));
    }
}
~~~

Trong một test suite hoàn chỉnh, còn phải kiểm tra **thiếu signed header**, header có hai values, body nonempty, body binary, timestamp grammar, nonce grammar, JSON whitespace, percent-encoded target và việc HTTP adapter chọn đúng raw target.

Đừng đánh đồng “canonicalizer từ chối input không hợp lệ” với “MAC không khớp”. Test nên phân loại typed reason ở nội bộ, còn public response có thể cùng `AUTHENTICATION_FAILED` để tránh enumeration.

## 9. Unit test primitive HMAC-SHA256 độc lập với HTTP

Để cô lập nguyên nhân, dùng test vector có expected MAC **không được tính từ cùng helper** trong assertion:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import java.util.HexFormat;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import org.junit.jupiter.api.Test;

class HmacSha256PrimitiveTest {

    @Test
    void matchesPublishedHmacSha256Vector() throws Exception {
        byte[] key = new byte[20];
        Arrays.fill(key, (byte) 0x0b);
        byte[] message = "Hi There"
            .getBytes(StandardCharsets.US_ASCII);

        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(key, "HmacSHA256"));
        byte[] actual = mac.doFinal(message);

        assertEquals(
            "b0344c61d8db38535ca8afceaf0bf12"
                + "b881dc200c9833da726e9376c2e32cff7",
            HexFormat.of().formatHex(actual)
        );
    }
}
~~~

Ở tầng request, mã ký mẫu:

~~~java
byte[] canonical = HmacCanonicalV1.build(
    "POST", rawTarget, signedHeaders, rawBody);

Mac mac = Mac.getInstance("HmacSHA256");
mac.init(new SecretKeySpec(testSecret, "HmacSHA256"));
byte[] signature = mac.doFinal(canonical);
String wireValue =
    java.util.Base64.getEncoder().encodeToString(signature);
~~~

`testSecret` phải là dữ liệu test rõ ràng, không dùng credential production. Server cần decode signature theo **đúng Base64 profile đã công bố**, yêu cầu MAC dài 32 bytes và so sánh bằng `MessageDigest.isEqual(expected, received)` hoặc API phù hợp. Không thử đồng thời nhiều encoding/algorithm hoặc version để “sửa” một request sai.

## 10. Header contract: tên, giá trị, whitespace và duplicate

HTTP header name không phân biệt hoa/thường, nhưng signed header **value** có thể nhạy cảm với ký tự và cách normalize. Vì vậy, test header phải rõ:

| Input | Kết quả theo V1 minh họa | Lý do |
| --- | --- | --- |
| `Content-Type: application/json` | Hợp lệ | Đúng profile |
| `content-type: application/json` | Hợp lệ | Tên được lowercase |
| `Content-Type:  application/json ` | Hợp lệ | Trim ASCII OWS ở hai đầu |
| `Content-Type: application/json; charset=utf-8` | Từ chối | Khác profile đã công bố |
| Hai `X-Key-Id` headers | Từ chối | Không chọn first/last tùy tầng |
| `X-Key-Id` và `x-key-id` cùng xuất hiện | Từ chối | Duplicate dù khác case |
| `X-Key-Id: K4, K3` | Không được hiểu là một ID hợp lệ | Header list ambiguity |
| `X-Nonce` có tab giữa chuỗi | Từ chối | Grammar nonce không chấp nhận |
| Header chứa CR/LF | Từ chối tại ingress/adapter | Ngăn injection, parser disagreement |
| Thiếu `X-Timestamp` | Từ chối | Không tự thay bằng empty string |
| `X-Signature` có hai values | Từ chối ở signature parser | Không thử nhiều chữ ký |

Với các field identity, key ID, nonce hoặc signature, nên validate **duy nhất một field/value**, giới hạn độ dài, charset và grammar rõ. Không dùng `headers.getFirst()` trong khi duplicate không được kiểm tra; hai bên có thể chọn first/last khác nhau.

**Nuance của HTTP API:** một số framework/proxy tự nối nhiều header thành một chuỗi comma-separated. Nếu hợp đồng không cho phép list-valued input, phải có cơ chế kiểm tra ở nơi còn thấy nhiều dòng gốc hoặc từ chối dạng dấu phẩy/ambiguous. Không thể lấy lại phân biệt hai header gốc sau khi proxy đã gộp nếu không có metadata đáng tin.

## 11. URI và query: nơi xảy ra nhiều lỗi tương thích nhất

**Raw target** trong V1 là chuỗi origin-form `/path?query` được xác định ở điểm verify. Test cần xem nó như bytes có thứ tự, không biến thành map parameters.

| Target A | Target B | Test kỳ vọng trong V1 |
| --- | --- | --- |
| `/orders?a=1&b=2` | `/orders?b=2&a=1` | Canonical bytes khác |
| `/orders?a=1&a=2` | `/orders?a=2&a=1` | Khác |
| `/orders?x=%2F` | `/orders?x=%2f` | Khác |
| `/orders?x=a+b` | `/orders?x=a%20b` | Khác |
| `/orders?x=` | `/orders?x` | Khác |
| `/orders` | `/orders?` | Theo contract raw target, phải đặc tả khác/đồng nhất; V1 ví dụ giữ đúng raw string |
| `/a/%2E%2E/b` | `/b` | Không tự normalize |
| `/orders?tag=a&tag=b` | `/orders?tag=a` | Khác, không bỏ duplicate |

Cần kiểm thử riêng việc **route tới handler** có cùng ngữ nghĩa với **route được ký**. Nếu gateway/router decode `%2F` thành slash sau khi HMAC verify nhưng authorization dựa trên URL khác, attacker có thể lợi dụng **canonicalization gap** dù MAC đúng.

Trong Servlet, `getRequestURI()` và `getQueryString()` có thể hữu ích nhưng không phải cam kết rằng tất cả raw octets trước proxy đã được giữ nguyên. Trong WebFlux, `ServerHttpRequest.getURI().getRawPath()/getRawQuery()` có thể giúp xây raw target **sau các transformation** mà adapter đã nhận. Contract phải xác định điểm quan sát và kiểm thử bằng HTTP proxy thực.

### Không chuẩn hóa “để test pass”

Một số bản vá nguy hiểm:

~~~java
// Nguy hiểm nếu hợp đồng ký raw target:
String normalized = URLDecoder.decode(
    request.getQueryString(), StandardCharsets.UTF_8);

// Nguy hiểm nếu vô tình đổi thứ tự/lặp:
Map<String, String> query = parseQuery(rawQuery);
String rebuilt = serializeSorted(query);
~~~

Nếu thực sự muốn sort query, cần **version mới**, quy tắc xử lý duplicate và test vectors riêng. Không tự chuyển thuật toán khi gặp mismatch.

## 12. Body contract: exact bytes, content encoding và payload rỗng

HMAC dùng digest raw body bytes trong profile V1. Những ca nên có trong bộ golden fixture:

1. Body rỗng `byte[0]`.
2. Body UTF-8 JSON compact.
3. Cùng JSON thêm whitespace hoặc đổi thứ tự field.
4. Body kết thúc bằng `LF` so với không có newline.
5. JSON có non-ASCII bytes, ký tự Unicode tổ hợp.
6. Body chứa `0x00` hoặc byte không phải UTF-8 (để kiểm tra parse policy).
7. Body binary cố định, nếu profile route cho phép.
8. Body có size đúng limit, vượt limit đúng một byte.
9. Multipart với boundary/metadata đã cố định, nếu có route multipart.
10. Gzip payload và payload đã decompress để chứng minh **không nhầm hai representation**.

Body rỗng có SHA-256 riêng; `{}` và `null` có digest khác. Cách làm sai:

~~~java
String json = objectMapper.readTree(body)
    .toString();
byte[] reconstructed =
    json.getBytes(StandardCharsets.UTF_8);
// Hash reconstructed thay vì bytes do client ký.
~~~

Cách làm đúng theo profile raw body:

~~~java
byte[] exactBytes = boundedRequestBodyCapture(request);
byte[] bodyDigest =
    MessageDigest.getInstance("SHA-256")
        .digest(exactBytes);
~~~

**Không chỉ tin `X-Body-SHA256` do client gửi.** Nếu client ký header digest, verifier vẫn phải hash raw body thực nhận để kiểm tra nó khớp, rồi mới đưa digest vào canonical request. Ngược lại body có thể bị thay mà chữ ký header vẫn đúng.

### Compression và proxy

HTTP `Content-Encoding: gzip` là một transformation có ý nghĩa với bytes. Đặt rõ contract ký **compressed payload** hay **decompressed representation** ở bước nào, đồng thời giới hạn cả kích thước nén và giải nén. Trong profile `application/json` minh họa, có thể **từ chối Content-Encoding khác identity** thay vì cho phép proxy giải nén ngầm để giảm ambiguity.

HTTP transfer-encoding/chunk framing không nhất thiết là bytes của application body. Test HTTP/1.1 chunked và HTTP/2 cần chứng minh cùng **payload bytes sau transfer decoding** tạo cùng digest; không giả định raw TCP bytes là body.

## 13. Clock, timestamp và nonce có nằm trong canonical contract không?

**Có, nếu cơ chế chống replay của module dựa trên timestamp/nonce.** Một attacker không được phép thay nonce hoặc timestamp mà giữ MAC hợp lệ.

Ví dụ timestamp V1 được yêu cầu đúng format `2026-11-28T03:00:00Z`. Không tự chấp nhận `2026-11-28T10:00:00+07:00` như cùng canonical text trừ khi hợp đồng định nghĩa rõ cách parse/normalize trước khi ký. Một client có thể biểu diễn cùng instant bằng hai chuỗi khác nhau; raw signed header values là **hai chứng cứ HMAC khác nhau**.

Bài test cần có:

| Trường hợp | Kỳ vọng |
| --- | --- |
| Timestamp hợp lệ, Clock cố định | Chữ ký đúng và freshness passed |
| Timestamp quá cũ | Authentication rejected |
| Timestamp tương lai vượt skew | Authentication rejected |
| ISO instant cùng thời điểm nhưng format khác | Theo grammar V1, thường reject |
| Thay timestamp sau ký | Signature mismatch |
| Thay nonce sau ký | Signature mismatch |
| Nonce mới và MAC đúng | Atomic first claim success |
| Gửi lại cùng nonce/signature | Replay rejected |
| Gửi cùng nonce tới hai instance | Chỉ một first claim nếu store bảo đảm phạm vi |
| Nonce store timeout/unknown | Fail closed, không xem là first use |

Lưu ý: **canonicalization contract** kiểm tra text/bytes nhất quán; **timestamp acceptance window** và **nonce retention** là chính sách xác thực chạy sau hoặc kết hợp theo thứ tự có kiểm soát. Contract test không thay thế stateful security test.

Với cửa sổ đối xứng `±W`, TTL fixed của nonce cần bao phủ toàn bộ thời gian signature có thể còn hợp lệ, thường ít nhất `2W + margin` trong kịch bản claim ở biên timestamp tương lai. Test tại các điểm biên bằng `Clock.fixed`.

## 14. Key ID, secret version và key rotation

Key rotation có thể có K3 và K4 cùng ACTIVE trong cửa sổ. Contract ký phải xác định rõ **key ID** được gửi và đưa vào canonical bytes. Verifier lookup **đúng key ID**; không được thử mọi secret khi signature mismatch.

| Ca | Credential registry | Signature tạo bằng | Kỳ vọng |
| --- | --- | --- | --- |
| K4 ACTIVE, key ID K4 | K4 → secret4 | secret4 | Pass nếu timestamp/nonce hợp lệ |
| Key ID K4 nhưng ký bằng K3 | K4 → secret4 | secret3 | Fail |
| K3 ACTIVE, key ID K3 | K3 → secret3 | secret3 | Pass trong overlap |
| K3 REVOKED, key ID K3 | K3 → revoked | secret3 | Fail dù MAC về toán học đúng |
| Key ID K4 nhưng ký bằng default secret | K4 → secret4 | default | Fail |
| Key ID K4, server cache K3 | Registry/caching lỗi | secret4 | Positive control phải phát hiện |
| Key ID thiếu/trùng | Bất kỳ | Bất kỳ | Reject parse |
| Client ID thay nhưng MAC giữ nguyên | Bất kỳ | Signature cũ | Fail hoặc bị registry binding từ chối |

**Không làm test wrong secret bằng cách đổi sang key ID không tồn tại**: đó là missing-key test. Giữ key ID, canonical bytes giống nhau, chỉ thay secret để kiểm tra cryptographic mismatch.

Canonical contract tương thích chưa bảo đảm key revocation hoạt động. Nếu registry cache trạng thái ACTIVE quá cũ, request K3 có thể được chấp nhận trái chính sách; cần test revocation freshness độc lập với canonical-byte tests.

## 15. Java 17: đối chiếu bytes với signature và credential

Một HMAC verifier đúng logic cần phân biệt rõ các bước:

~~~java
// Khung pseudocode cho verifier; các type là của dự án.
Credential credential =
    registry.findExact(requestKeyId);

if (credential == null || !credential.isActive()) {
    throw new BadCredentialsException("authentication_failed");
}

byte[] canonical = HmacCanonicalV1.build(
    requestMethod, trustedRawTarget,
    signedHeaders, rawBody);

Mac mac = Mac.getInstance("HmacSHA256");
mac.init(new SecretKeySpec(
    credential.secretBytes(), "HmacSHA256"));
byte[] expected = mac.doFinal(canonical);

byte[] actual = strictBase64Decode(
    signatureHeader, 32 /* expected MAC length */);

if (!MessageDigest.isEqual(expected, actual)) {
    throw new BadCredentialsException("authentication_failed");
}

// Chỉ sau MAC hợp lệ mới claim nonce nguyên tử.
// Không cho business chạy khi store unavailable.
replayStore.checkAndClaim(
    credential.id(), nonce, signedTimestamp);

// Bây giờ mới tạo principal và chạy authorization riêng.
return authenticatedPrincipalFromRegistry(credential);
~~~

Đây là **khung kiến trúc**, chưa có đầy đủ kiểm tra timestamp, giới hạn kích thước, exception handling và integration. Các bước phải tuân thủ hợp đồng thứ tự xác thực đã thiết kế: malformed input/time out có thể bị từ chối sớm, nhưng **không claim nonce trước khi MAC đúng**.

Trong sản phẩm hỗ trợ nhiều version, chọn canonicalizer theo **allowlist rõ ràng**, ký version vào canonical bytes và không fallback sang V1/V2 khi MAC không khớp. Kết quả phiên bản không được “auto repair” bằng cách thử lại với thuật toán khác.

## 16. Consumer-driven contract testing giữa client SDK và verifier

Một hệ thống có thể có:

- Java client SDK.
- Python/Go/Node.js client tích hợp đối tác.
- Gateway/Envoy/NGINX có plugin HMAC.
- Spring MVC service.
- Spring WebFlux service.

Nếu mỗi bên tự triển khai canonicalization, cần **một bộ fixture độc lập, có version** để mọi bên chạy.

~~~mermaid
flowchart TD
    F["Versioned golden fixtures"] --> J["Java client signer conformance"]
    F --> P["Python/Go/Node signer conformance"]
    F --> G["Gateway HMAC verifier conformance"]
    F --> M["Spring MVC verifier conformance"]
    F --> W["Spring WebFlux verifier conformance"]
    J --> C["Cross-implementation parity gate"]
    P --> C
    G --> C
    M --> C
    W --> C
    C --> D{"Tất cả exact byte vectors PASS?"}
    D -->|Không| X["Block release / investigate drift"]
    D -->|Có| E["Integration + E2E proxy tests"]
~~~

### Hợp đồng do ai sở hữu?

Một đội/hệ thống sở hữu **specification và versioned fixtures**; không lấy output mới nhất của SDK A làm “sự thật” rồi bắt tất cả verifier khác khớp. Có thể sử dụng một reference implementation đã được review để tạo fixtures ban đầu, nhưng:

1. Expected bytes/signatures phải được **đối chiếu bằng implementation độc lập**.
2. Fixtures đã phát hành không đổi theo refactor code.
3. Mọi thay đổi breaking cần version mới và migration plan.
4. Client/server triển khai phải công bố rõ supported contract versions.

Trong consumer-driven testing, đối tác có thể gửi những trường hợp khó từ thư viện của họ (URI encoding, Unicode, duplicate query). Producer/server không nhất thiết chấp nhận mọi biểu diễn; nó phải **chấp nhận hoặc từ chối nhất quán với spec**.

### Shared implementation không thay được independent test

Nếu cả Java client và Spring server dùng cùng thư viện canonicalizer, hai bên có thể cùng sai. Positive round-trip test vẫn PASS, nhưng SDK ở ngôn ngữ khác fail. Do đó, ngoài test round-trip, luôn cần **golden byte literals** và ít nhất một implementation độc lập ở test contract.

## 17. Contract tests ở Spring MVC (Servlet)

Một HMAC authentication filter thường chạy **trước `DispatcherServlet`**, tiêu thụ request body để hash, rồi phải replay body cho controller. Contract suite cần kiểm tra:

- `getInputStream()` một lần đọc: filter không khiến `@RequestBody` ở controller rỗng.
- Raw request-target từ Servlet/container có đúng contract không.
- Header có nhiều values/case/OWS được xử lý rõ.
- `Content-Type` và body bytes được giữ nguyên sau proxy.
- Giới hạn body có ở filter và ingress; không dùng `readAllBytes()` vô hạn.
- HMAC fail thì controller không chạy, nonce không được claim.
- HMAC pass thì controller nhận chính bytes đã xác minh.

Ví dụ khung `MockMvc` chạy security chain thật:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class HmacCanonicalContractMvcIT {

    @Autowired MockMvc mvc;
    @Autowired IndependentHmacSigner testSigner;

    @Test
    void rejectsChangedRawQueryWithOriginalSignature()
            throws Exception {
        byte[] body = "{\"orderId\":\"o-1\"}"
            .getBytes(StandardCharsets.UTF_8);

        // Fixture dựng timestamp/nonce hợp lệ từ Clock test;
        // signer tạo canonical bytes theo reference contract.
        String timestamp = "2026-11-28T03:00:00Z";
        String nonce = "34cfb0e7-2d64-4f43-b45c-7f630f7a1e31";
        String sig = testSigner.sign(
            "POST", "/api/orders?a=1&b=2",
            timestamp, nonce, body);

        mvc.perform(post("/api/orders?b=2&a=1")
                .contentType("application/json")
                .header("X-Signature-Version", "HMAC-REQUEST-V1")
                .header("X-Client-Id", "client-a")
                .header("X-Key-Id", "client-a-k4")
                .header("X-Tenant-Id", "tenant-a")
                .header("X-Timestamp", timestamp)
                .header("X-Nonce", nonce)
                .header("X-Signature", sig)
                .content(body))
            .andExpect(status().isUnauthorized());
    }
}
~~~

Đây là **test skeleton**: import JUnit/Spring và `IndependentHmacSigner` thuộc fixture của dự án, không phải class có sẵn. Timestamp cố định ở tháng 11/2026 chỉ hợp lệ khi verifier dùng **Clock cố định tương ứng**. Nếu chạy với đồng hồ thật sau cửa sổ, test có thể trả 401 vì timestamp cũ và **không chứng minh query mismatch**. Cần thêm positive control qua **cùng route, secret, headers và nonce store sạch**.

`MockMvc` không mô phỏng đầy đủ Netty/proxy/HTTP/2/encoding transformations. Các trường hợp URI percent-encoding thực tế phải được test qua server container và gateway thật, không chỉ với `MockMvcRequestBuilders`.

## 18. Contract tests ở Spring WebFlux

Với WebFlux, `ServerHttpRequest.getBody()` phát `Flux<DataBuffer>`. Một `WebFilter` xác thực body có thể thu buffer có giới hạn, hash và replay qua `ServerHttpRequestDecorator`. Không được subscribe lại source body tùy tiện.

Kiểm thử bằng `WebTestClient`/`StepVerifier` cần bao phủ:

1. Một body được chia thành một hoặc nhiều `DataBuffer` khác nhau → **cùng SHA-256**, vì chunk boundary không phải bytes được ký.
2. Body rỗng → digest `e3b0...b855`.
3. Body vượt limit → 413/không thực thi controller, không băm body bị cắt.
4. Source error/cancel → release pooled buffers, không tạo authenticated principal.
5. `DataBufferUtils.join(body, maxBytes)` phát lỗi khi vượt giới hạn; đường thành công release joined buffer đúng một lần.
6. Downstream đọc lại body sau khi MAC đúng → nhận nguyên raw bytes, không trùng/thiếu.
7. `ReactiveSecurityContextHolder` có principal đúng ở nhánh hợp lệ, không rò context sang request khác.
8. Authentication dependency timeout → fail closed, không gọi `block()` trên event loop.

Một test focused cho chunk invariance:

~~~java
import static org.junit.jupiter.api.Assertions.assertArrayEquals;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import org.junit.jupiter.api.Test;
import org.springframework.core.io.buffer.DataBuffer;
import org.springframework.core.io.buffer.DefaultDataBufferFactory;
import org.springframework.core.io.buffer.DataBufferUtils;
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

class HmacBodyChunkContractTest {
    private final DefaultDataBufferFactory buffers =
        new DefaultDataBufferFactory();

    @Test
    void bodyDigestDoesNotDependOnDataBufferBoundaries() {
        byte[] expected = "abc123"
            .getBytes(StandardCharsets.UTF_8);

        Flux<DataBuffer> chunks = Flux.just(
            buffers.wrap("ab".getBytes(StandardCharsets.UTF_8)),
            buffers.wrap("c123".getBytes(StandardCharsets.UTF_8)));

        StepVerifier.create(
            DataBufferUtils.join(chunks, 1024)
                .map(joined -> {
                    try {
                        byte[] bytes =
                            new byte[joined.readableByteCount()];
                        joined.read(bytes);
                        return bytes;
                    } finally {
                        DataBufferUtils.release(joined);
                    }
                })
        ).assertNext(actual ->
            assertArrayEquals(expected, actual)
        ).verifyComplete();
    }
}
~~~

Mẫu trên chứng minh **capture giữ nguyên bytes** khi chunk khác nhau, chưa tính SHA-256 hoặc HMAC. Bộ integration test cần nối `MessageDigest` vào bytes đã capture và so với digest của fixture độc lập, rồi kiểm tra `WebTestClient` qua security chain. Không kết luận “đã kiểm thử WebFlux HMAC” chỉ nhờ StepVerifier của một buffer helper.

## 19. End-to-end qua gateway/proxy: nơi unit test dễ bỏ sót

Một conformance suite cần có ít nhất hai đường:

~~~text
Client SDK → gateway → backend verifier
Client SDK → gateway verifier → mTLS/assertion → backend
~~~

### Với backend verifier

Test vector được ký theo **target tại điểm verify đã quy định**. Gateway phải giữ nguyên hoặc chuyển metadata gốc đáng tin nếu có rewrite. Không sử dụng `X-Original-URI` từ client để tự “sửa” signature.

### Với gateway verifier

Gateway verify canonical contract ở edge. Sau khi rewrite, backend không cần ký lại request bằng secret client, nhưng phải xác minh signed internal assertion hoặc trust channel phù hợp. Assertion cần ràng buộc identity, method, internal target, body digest, audience và thời hạn, rồi backend phân quyền riêng.

### Ma trận proxy

| Biến đổi | Câu hỏi test |
| --- | --- |
| `/public/orders` → `/internal/orders` | MAC được verify tại target nào? |
| HTTP/1.1 → HTTP/2 | `:path` và header names được hiểu như thế nào? |
| TLS termination | Scheme/Host nào có/không nằm trong hợp đồng? |
| Query reorder | Raw target có được bảo toàn không? |
| Percent-encoding case | `%2F` so với `%2f` được giữ ra sao? |
| Header normalization | OWS và case header có đúng profile không? |
| Duplicate signed headers | Gateway có từ chối trước khi gộp? |
| Gzip decompress | Body được ký là compressed hay decompressed bytes? |
| JSON transformation | Raw body hash có thay đổi? |
| Chunked framing | Payload bytes sau transfer decoding có như nhau không? |
| Header spoofing | `X-Authenticated-Client`/`X-Original-URI` do client có bị strip? |
| Direct backend route | Có bypass được gateway verifier không? |

Contract test cần assert **không có side effect** khi chữ ký không còn hợp lệ, không chỉ assert HTTP 401/403. Với endpoint payment/order, dùng sandbox fixture; không chạy probe destructive trên production.

## 20. Versioning, migration và backward compatibility

Canonicalization là một **wire protocol**. Nếu V1 ký raw query theo thứ tự nhận, còn V2 sort query, đó là thay đổi có thể làm chữ ký cũ không được chấp nhận. Không sửa behavior V1 tại chỗ rồi tin rằng mọi SDK sẽ tự cập nhật.

Chiến lược an toàn:

1. Công bố `HMAC-REQUEST-V2` với document/fixtures độc lập.
2. Dùng domain separation trong canonical bytes: dòng đầu V2 khác V1.
3. Đưa version vào header được kiểm tra; chỉ chọn từ **allowlist**.
4. Bổ sung signer/verifier V2 trong thời gian overlap có kiểm soát.
5. Kiểm thử **V1 vẫn đúng golden fixtures cũ** sau khi thêm V2.
6. Client chọn một version theo capability đã thống nhất; không được tự hạ version khi MAC thất bại.
7. Theo dõi tỷ lệ V1/V2 qua metric label version hữu hạn, không dùng raw untrusted version text.
8. Khi ngừng V1, từ chối version cũ theo chính sách và cập nhật thông báo/deprecation.
9. Key rotation và canonical contract migration là **hai trục độc lập**, tránh thay key và thuật toán cùng lúc nếu không cần.
10. Vẫn kiểm tra credential state/nonce/authorization trên cả hai version.

### Không nên “try all versions”

~~~java
// SAI nếu đây không phải contract được thiết kế:
for (Canonicalizer v : allSupportedVersions) {
    if (verifyHmac(v.canonicalize(request), secret, signature)) {
        return authenticatedPrincipal;
    }
}
~~~

Việc thử nhiều thuật toán có thể tạo ambiguity và downgrade, khiến telemetry/troubleshooting không biết client thực sự ký version nào. Nếu hỗ trợ nhiều version, chọn **một canonicalizer** theo version đã parse, rồi xác minh version đó như một phần của canonical bytes.

### Cross-version replay

Nếu cùng key ID/nonce được chấp nhận ở V1 và V2, replay namespace phải được thiết kế rõ. Không tách nonce store theo version một cách tùy tiện, vì cùng client có thể tạo thêm một miền phát lại. Với scope `(credentialId, nonce)`, một nonce chỉ được claim một lần xuyên version cho cùng credential; nếu chọn scope khác, phải có threat model và test cụ thể.

## 21. Security semantics không được nhầm với canonical equivalence

Một request HMAC đúng không tự được quyền truy cập mọi tài nguyên. Cần test riêng:

| Authentication | Authorization | HTTP/side effect kỳ vọng |
| --- | --- | --- |
| MAC đúng, key ACTIVE, nonce mới | Có quyền tenant/resource | Đi tiếp và thực thi theo nghiệp vụ |
| MAC đúng, key ACTIVE, nonce mới | Không có quyền tenant B | 403/404 theo policy, không đọc/ghi B |
| MAC sai vì target/body bị sửa | Chưa tới bước authz | 401 chung, không nghiệp vụ |
| MAC đúng nhưng key REVOKED | Chưa được xác thực | 401 chung |
| MAC đúng nhưng nonce đã dùng | Replay rejected | 401 chung |
| Credential store unavailable | Không đủ bằng chứng | 503/fail closed theo policy |
| Request body quá lớn | Chưa evaluate đầy đủ | 413 |
| Gateway assertion sai audience/body binding | Không được tin principal | Từ chối tại backend |

`X-Tenant-Id` được ký giúp bảo vệ **tính toàn vẹn của claim tenant**, nhưng không cấp quyền. Effective tenant phải đến từ quyết định authorization dựa trên principal/credential owner/grant và resource owner.

Hợp đồng canonical có thể cho HTTP `Host` không nằm trong signed bytes, nhưng dịch vụ phải đảm bảo principal/key chỉ dùng trong authority/service audience được phép. Nếu cùng secret chấp nhận trên nhiều hostname/route nhạy cảm, cần **signed audience/host hoặc key scoping ở backend** để tránh cross-service replay. Đây là phần threat model vượt ra ngoài raw-target equality.

## 22. Negative tests: thứ thay đổi nhỏ nhất phải gây kết luận đúng

Contract test không chỉ gồm happy path. Nó phải phân biệt:

- **Signature mismatch:** thay đúng một byte thuộc phạm vi đã ký, giữ key/timestamp/nonce hợp lệ.
- **Malformed input:** duplicate header, Base64 hỏng, raw target sai grammar.
- **State/replay failure:** key revoked, timestamp out of window, nonce reused.
- **Authorization failure:** MAC đúng nhưng không có quyền với tenant/resource.
- **Infrastructure failure:** registry/secret/replay store unavailable.

Khi test thay target, phải dùng **positive control** cùng route và same signer/secret đi qua thành công; nếu cả positive và negative đều trả 401 do timestamp hết hạn, test không có giá trị chứng minh canonicalization.

### Một ví dụ metamorphic test

Đối với V1, thay thứ tự query là thay canonical bytes:

~~~java
byte[] a = HmacCanonicalV1.build(
    "POST", "/api/orders?a=1&b=2", headers, body);

byte[] b = HmacCanonicalV1.build(
    "POST", "/api/orders?b=2&a=1", headers, body);

assertFalse(Arrays.equals(a, b));
~~~

Ngược lại, thay **case của header name** nhưng giữ cùng value là một biến đổi *được chuẩn hóa*:

~~~java
Map<String, List<String>> h1 = headersWith("Content-Type");
Map<String, List<String>> h2 = headersWith("content-type");

assertArrayEquals(
    HmacCanonicalV1.build("POST", target, h1, body),
    HmacCanonicalV1.build("POST", target, h2, body));
~~~

Hai helper `headersWith`, `target`, `body` ở ví dụ là fixture test; không phải API sẵn có. Với `Content-Type`, thay OWS hai đầu là biến đổi được profile cho phép, còn thay whitespace bên trong, media-type parameter hoặc body bytes có thể bị reject/đổi MAC.

### Mutation testing

Thử cố ý làm sai canonicalizer trong test sandbox:

- Bỏ dòng timestamp/nonce.
- Sort query dù contract không cho phép.
- Lowercase toàn header **values**.
- Thêm newline cuối canonical.
- Hash `String` sau decode thay vì raw bytes.
- Bỏ qua duplicate signed headers.
- Dùng secret mặc định khi không tìm thấy key ID.
- Claim nonce trước khi HMAC đúng.
- Accept request khi replay store lỗi.

Conformance suite tốt phải **FAIL** khi gặp các mutation này. Nếu test vẫn PASS, có thể expected output được tạo bởi cùng code sai hoặc assertions chỉ kiểm tra status quá rộng.

## 23. Ma trận conformance có thể giao cho từng SDK

| ID | Kịch bản | Kết quả kỳ vọng |
| --- | --- | --- |
| CAN-01 | POST body rỗng | Canonical bytes khớp golden vector |
| CAN-02 | Body UTF-8 JSON compact | SHA-256 đúng raw bytes |
| CAN-03 | Body JSON thêm whitespace | Digest/MAC khác |
| CAN-04 | Body đổi thứ tự field | Digest/MAC khác |
| CAN-05 | Body có LF cuối | Khác body không LF |
| CAN-06 | Binary body nếu route cho phép | Digest khớp bytes, không qua String |
| CAN-07 | Non-ASCII Unicode trong body | Hash bytes thực, không normalize |
| CAN-08 | Body vượt max + 1 byte | 413, không hash body bị cắt |
| CAN-09 | Query đổi thứ tự | Canonical bytes khác |
| CAN-10 | Query có duplicate keys | Giữ thứ tự, không map-overwrite |
| CAN-11 | `%2F` đổi thành `%2f` | Canonical raw target khác |
| CAN-12 | `+` đổi `%20` | Không tự decode/normalize |
| CAN-13 | Path dot segments và encoded slash | Không tự đổi route/authorization |
| CAN-14 | Header name đổi case | Canonical tương đương theo V1 |
| CAN-15 | Header value có ASCII OWS hai đầu | Trim đúng contract |
| CAN-16 | Header value đổi whitespace nội bộ | Reject hoặc khác theo grammar |
| CAN-17 | Hai `X-Key-Id` headers | Từ chối ambiguous |
| CAN-18 | Header duplicate khác case | Từ chối |
| CAN-19 | Thiếu `X-Timestamp` | Từ chối |
| CAN-20 | `X-Signature-Version` lạ | Từ chối, không fallback |
| CAN-21 | Version đổi nhưng giữ signature | Không được accept |
| CAN-22 | HMAC primitive public vector | Exact expected 32 bytes |
| CAN-23 | K4 ký bằng secret K4 | Positive HMAC, nonce mới |
| CAN-24 | Key ID K4 ký bằng secret K3 | MAC mismatch, không fallback |
| CAN-25 | Key K3 REVOKED ký đúng K3 | Authentication rejected |
| CAN-26 | Timestamp quá cũ/tương lai | Từ chối theo window |
| CAN-27 | Thay nonce sau khi ký | MAC mismatch |
| CAN-28 | Replay cùng nonce | Claim đầu được chấp nhận, lần sau fail |
| CAN-29 | Nonce đồng thời hai instance | Chỉ một atomic claim thành công |
| CAN-30 | Secret/replay store timeout | Fail closed, không 2xx |
| CAN-31 | HTTP/1.1 ↔ HTTP/2 | Payload/target contract nhất quán |
| CAN-32 | Gateway rewrite external/internal path | Verify đúng trust boundary |
| CAN-33 | Gateway normalize/query reorder trái contract | Không tạo false-positive accept |
| CAN-34 | Gzip decompress/recompress | Body digest/contract được bảo toàn hoặc reject |
| CAN-35 | Client giả forwarded/original URI | Không sửa canonical target đáng tin |
| CAN-36 | Backend nhận gateway assertion sai audience | Từ chối |
| CAN-37 | MAC valid nhưng target tenant khác | Authorization deny, không lộ data |
| CAN-38 | MVC body replay | Controller nhận bytes đã ký |
| CAN-39 | WebFlux body chia chunk khác nhau | Digest bất biến |
| CAN-40 | WebFlux cancel/error | Cleanup buffers, không auth success |
| CAN-41 | V1 signer với V1 verifier | Cross-language parity PASS |
| CAN-42 | V1 signer với V2-only verifier | Reject theo version policy |
| CAN-43 | Golden fixtures qua Java/Python/Go | Exact canonical byte parity |
| CAN-44 | Auth filter bị bypass | Synthetic negative probe phát hiện |
| CAN-45 | Double filter registration | Không claim nonce hai lần |
| CAN-46 | Key rotation K3/K4 overlap | Đúng secret từng ID, không cross-version fallback |
| CAN-47 | Body đã signed nhưng proxy transform | Reject nếu không có contract transformation |
| CAN-48 | Nonce mới, HMAC valid, business 500 | Auth metric valid nhưng HTTP 500, nonce đã claim |

Không cần chạy mọi test ở từng tầng. Có thể chia CAN-01–22 vào **unit/contract**, CAN-23–30 và CAN-37–40 vào **integration**, CAN-31–36 và CAN-41–47 vào **gateway/E2E**, đồng thời chạy một tập smoke tối thiểu trên mỗi release.

## 24. CI/CD và phát hành golden fixtures

Golden fixtures là phần **API hợp đồng** cần review và version control. Một pipeline có thể gồm:

~~~mermaid
flowchart TD
    A["Thay đổi canonical spec/SDK/verifier/gateway"] --> B["Lint schema + validate fixture grammar"]
    B --> C["Golden canonical byte tests"]
    C --> D["Primitive HMAC + exact signature tests"]
    D --> E["Cross-language producer/consumer tests"]
    E --> F["Spring MVC/WebFlux integration"]
    F --> G["Gateway real-proxy contract tests"]
    G --> H["Timestamp/nonce/rotation/authorization regressions"]
    H --> I{"Tất cả assertions PASS?"}
    I -->|Không| X["Block release, phân tích byte diff"]
    I -->|Có| J["Publish versioned contract artifacts"]
~~~

**Nguyên tắc release:**

- Một thay đổi chuẩn hóa bytes phải được đánh dấu **breaking** trừ khi có bằng chứng tương thích.
- Review expected canonical bytes/signatures như dữ liệu giao thức, không dùng tùy tiện snapshot update.
- Test producers/consumers từ **những phiên bản đang chạy** và cả phiên bản sắp deploy.
- Mỗi golden fixture có ID, contract version, nguồn gốc, expected byte length/digest và tình huống.
- Giữ nguyên fixture V1 cũ khi bổ sung V2.
- Khi nâng cấp Spring, Netty, gateway hoặc SDK HTTP, chạy lại bộ **raw URI/header/body conformance**.
- Gateway config/ingress rewrite thay đổi cũng phải trigger contract tests, không chỉ ứng dụng Java.
- Test nội bộ không dùng production shared secret; fixture secret phải tách biệt và không log nguyên key.
- Bên thứ ba chỉ nhận fixture công khai hoặc secret dành riêng cho test, không truy cập registry production.

### Đọc byte diff thay vì chỉ thấy “signature mismatch”

Khi client và server khác MAC, so sánh theo thứ tự:

1. Contract version và domain string.
2. Canonical byte length và dấu newline cuối.
3. Method/raw target byte sequence.
4. Signed header names, order, normalization, số giá trị.
5. Timestamp/nonce text.
6. Body raw length và digest.
7. Encoding (UTF-8) và newline `0x0A`.
8. MAC bytes và Base64 encoding.
9. Key ID đúng secret version/status.
10. Gateway transformation tại đúng trust boundary.

Trong test environment có fixture không nhạy cảm, có thể lưu **hex dumps của canonical bytes** để diff. Trong production, không dump full canonical request chứa token, query nhạy cảm hoặc body; chỉ log contract version, route group, payload length, correlation ID và các reason enums an toàn.

## 25. Monitoring và cách phát hiện canonicalization drift

Metric gợi ý, có labels **hữu hạn**:

~~~text
hmac_authentication_attempts_total{
  route="orders", contract="v1",
  result="invalid", reason="signature"
}

hmac_contract_mismatch_total{
  route="orders", contract="v1",
  gateway_group="edge-a", component="raw_target"
}
~~~

Tên ở trên là **minh họa**; phải xác nhận exporter Micrometer/Prometheus thực tế. Một verifier thông thường biết signature mismatch nhưng **không biết chắc** nguyên nhân ở raw target hay body. Không tự tăng `component="raw_target"` chỉ vì MAC sai. Nhãn component chỉ hợp lệ khi có **diagnostics từ golden probe có ground truth** hoặc so sánh dữ liệu tin cậy trong môi trường kiểm thử.

Monitor:

- Tỷ lệ HMAC signature mismatch sau deploy proxy/SDK mới.
- Mismatch theo version, route và gateway group hữu hạn.
- Timestamp rejection, nonce replay, credential rejected và dependency unavailable tách biệt.
- Tỷ lệ V1/V2 trong migration, nhãn từ allowlist.
- Key revoke acceptance probes.
- Synthetic bad-signature/duplicate-header/body-tamper probes trên môi trường được phép.
- Số lần test E2E thất bại sau gateway config change.

Không gắn `clientId`, `keyId`, `tenantId`, nonce, full path hay raw signature làm Prometheus labels: tăng cardinality và lộ thông tin. Security audit chi tiết hơn chỉ được lưu có kiểm soát, không trộn vào public HTTP response.

### Status semantics

| Outcome | Public status gợi ý | Reason nội bộ |
| --- | --- | --- |
| Chữ ký không khớp canonical request | 401 | `SIGNATURE_MISMATCH` |
| Contract version không hỗ trợ | 400/401 tùy hợp đồng | `UNSUPPORTED_VERSION` |
| Header duplicate/malformed | 400/401 tùy hợp đồng | `MALFORMED_SIGNED_INPUT` |
| Timestamp ngoài cửa sổ | 401 | `TIMESTAMP_OUT_OF_WINDOW` |
| Nonce đã dùng | 401 | `REPLAY_DETECTED` |
| Secret manager/nonce store unavailable | 503 | `AUTHENTICATION_UNAVAILABLE` |
| HMAC valid nhưng thiếu quyền tenant | 403/404 theo policy | `ACCESS_DENIED` |
| Body quá lớn | 413 | `BODY_LIMIT_EXCEEDED` |

Public response có thể gom nhiều authentication failures thành `AUTHENTICATION_FAILED` để tránh làm **oracle** dò key/nonce. Không hiển thị expected MAC, secret hoặc canonical bytes trong response.

## 26. Bài tập: hai SDK cùng ký một request nhưng khác signature

Một đối tác dùng Java SDK và Go SDK gọi:

~~~http
POST /api/orders?tag=b&tag=a HTTP/1.1
Content-Type: application/json
X-Client-Id: client-a
X-Key-Id: client-a-k4
X-Tenant-Id: tenant-a
X-Timestamp: 2026-11-28T03:00:00Z
X-Nonce: 34cfb0e7-2d64-4f43-b45c-7f630f7a1e31
X-Signature-Version: HMAC-REQUEST-V1
X-Signature: <signature>
Content-Length: 17

{"orderId":"o-1"}
~~~

Java SDK ký **raw target đúng thứ tự** `tag=b&tag=a` và body bytes gốc. Go SDK parse query vào map rồi sort thành `tag=a&tag=b`; phía gateway normalize path và backend kiểm tra `Content-Type` sau khi thêm `charset=utf-8`. Cả Java và Go đều dùng **cùng secret K4**, nhưng chữ ký khác nhau. Một developer đề nghị backend “thử cả hai kiểu sort query cho đến khi khớp”.

Hãy phân tích:

1. V1 ký `raw target` hay query đã sort?
2. Vì sao cùng secret vẫn tạo hai chữ ký khác?
3. Body đã được giữ đúng raw bytes ở cả SDK chưa?
4. `Content-Type` thêm parameter có vi phạm profile V1 minh họa không?
5. Gateway có được thay URI hoặc signed header sau khi client ký mà không có contract transformation không?
6. Vì sao không nên “try both versions/normalizations until MAC matches”?
7. Golden vector nào giúp phát hiện sai lệch của Go SDK trước integration?
8. Test nào chứng minh backend từ chối duplicate `X-Key-Id`?
9. Nếu tenant header đã được ký, có tự suy ra quyền tenant không?
10. Khi bổ sung V2 sort query, làm sao giữ V1 tương thích và chống downgrade?
11. Trong multi-node system, timestamp/nonce contract và replay store liên quan như thế nào?
12. Nên ghi telemetry gì mà không lộ request body/secret?

**Hướng giải:** cố định V1 raw query representation, body digest từ bytes thật và signed headers theo quy tắc versioned; sửa Go SDK để tạo cùng canonical bytes. Gateway phải bảo toàn hoặc verify ở edge rồi chuyển assertion nội bộ có request binding. V2 là version riêng; một request chỉ có một canonicalizer đã chọn. Nonce, key state và authorization tiếp tục là những bước độc lập sau kiểm tra signature.

## 27. Checklist canonicalization contract testing trước production

- [ ] Hợp đồng có **ID/version**, domain separation và byte-level specification được review.
- [ ] Xác định rõ method, raw URI/query, signed headers, body digest, timestamp, nonce và key ID nằm trong chuỗi ký.
- [ ] Quy tắc UTF-8, LF, newline cuối, hex/Base64, header name order và OWS được chốt chính xác.
- [ ] Query duplicate/order, percent-encoding, `+` và `%20` được định nghĩa; không parse-serialize ngầm.
- [ ] Header duplicate/case/whitespace có hành vi reject/normalize rõ; không chọn first/last tùy tầng.
- [ ] Body được ký theo raw bytes tại trust boundary thống nhất; không deserialize JSON rồi serialize lại.
- [ ] Body rỗng, JSON khác whitespace, Unicode, binary, gzip và multipart được cover theo route contract.
- [ ] Có **golden canonical bytes** độc lập; golden HMAC signature được tính và soát chéo độc lập.
- [ ] Primitive HmacSHA256 có test vector công khai; không dùng mỗi positive round-trip.
- [ ] Mỗi SDK/ngôn ngữ, gateway và Spring verifier phải PASS **cùng versioned fixtures**.
- [ ] Có negative tests cho target, signed header, body, timestamp, nonce và version tampering.
- [ ] Có positive controls cùng tuyến để tránh 401 do Clock/route lỗi che kết quả.
- [ ] HMAC verifier dùng **đúng secret theo key ID**; không fallback key khác khi MAC sai.
- [ ] Key rotation/revocation và trạng thái client/tenant có tests riêng, không bị cache stale bypass.
- [ ] Nonce claim nguyên tử sau khi MAC đúng, timestamp window/retention đủ và multi-node replay được test.
- [ ] Backend/gateway chốt **một điểm xác minh** và quy tắc external/internal raw target qua rewrite.
- [ ] Forwarded/original URI và gateway identity headers từ client được strip/reject; internal assertion được verify.
- [ ] MVC capture bounded và replay body chính xác; WebFlux quản lý DataBuffer release/cancel/backpressure.
- [ ] Không để HTTP transfer chunking hoặc compression tạo representation ambiguity.
- [ ] Effective tenant, action, resource luôn đi qua authorization sau khi HMAC pass.
- [ ] Khi bổ sung V2, giữ nguyên golden V1, có allowlist và không thử fallback version khi signature sai.
- [ ] CI chạy schema/golden byte/primitive HMAC/cross-language/integration/E2E theo thay đổi app, SDK và proxy.
- [ ] Logs và metrics không lộ shared secret, full signature, raw body hoặc canonical request nhạy cảm.
- [ ] Có dashboard theo contract version, route và reason hữu hạn; drift được kiểm tra bằng fixture có ground truth.
- [ ] Test âm tính chứng minh **không có side effect** trước khi xác thực và phân quyền đạt yêu cầu.

**Canonicalization contract là một giao thức byte-level, không phải chi tiết implementation riêng của Java, Go hay proxy.** Kiểm thử đúng phải dùng golden fixtures độc lập, so sánh exact canonical bytes và HMAC, kiểm tra HTTP transformation thực tế, giữ version tương thích và ngăn fallback mơ hồ. Chỉ sau khi chứng minh hai đầu ký **cùng một chuỗi byte** mới có thể kết luận về secret, timestamp/nonce chống replay, key rotation và phân quyền trên nền bằng chứng HMAC đáng tin cậy.
