# Body không khớp: ngữ nghĩa lỗi khi xác thực HTTP request bằng HMAC

## 1. Bối cảnh và mục tiêu

Trong module **SECURITY_AUTHENTICATION_HMAC_REQUEST_AUTHENTICATION**, client ký HTTP request bằng HMAC với **shared secret** và một **canonical request** được hai bên thống nhất. Hợp đồng có thể đưa phương thức HTTP, URI, một số header và/hoặc nội dung body vào dữ liệu được ký. Server xác minh chữ ký, chặn replay bằng timestamp/nonce, xử lý key rotation và chỉ sau đó mới quyết định phân quyền.

Ở chương **Error semantics**, bài **Body không khớp** giải thích tình huống: *client đã ký một body nhưng server xác minh trên một chuỗi byte khác*. Hệ quả là chữ ký HMAC không khớp; request phải bị chặn trước khi thực hiện nghiệp vụ, kể cả khi JSON nhìn bằng mắt có vẻ giống nhau.

Một tình huống thường gặp:

~~~text
Client tạo body A → hash(A) → ký canonical request → gửi request
                                         |
                                         v
                                Gateway / proxy
                                  thay đổi body
                                         |
                                         v
Service nhận body B → hash(B) → tái tạo canonical → HMAC khác
                                         |
                                         v
                         Từ chối xác thực; không chạy nghiệp vụ
~~~

Sau bài này, người học sẽ biết cách:

1. Phân biệt **khác biệt byte body**, **sai canonical request** và **body hợp lệ về cú pháp nhưng sai nghiệp vụ**.
2. Xác định tại sao JSON, charset, line ending, nén/giải nén hoặc middleware đọc/ghi lại body gây HMAC mismatch.
3. Chọn HTTP status và response không tiết lộ thông tin nhạy cảm.
4. Thiết kế Java verifier dùng đúng body bytes, kiểm soát kích thước, so sánh chữ ký và giữ body cho handler phía sau.
5. Kiểm thử lỗi qua client, gateway/proxy và service mà không vô tình bỏ qua bước xác thực.

## 2. “Body không khớp” chính xác là gì?

Giả sử một hợp đồng HMAC-V1 quy định canonical request gồm:

~~~text
HMAC-V1
<METHOD>
<PUBLIC_RAW_PATH>
<RAW_QUERY_OR_EMPTY>
<KEY_ID>
<TIMESTAMP>
<NONCE>
<HEX_LOWERCASE_SHA256(BODY_BYTES)>
~~~

Sau đó client tính:

~~~text
bodyDigest = lowercaseHex(SHA256(originalBodyBytes))
canonical  = joinWithLF(definedFieldsAndBodyDigest)
signature  = Base64(HMAC-SHA256(sharedSecret, UTF8(canonical)))
~~~

Server cũng phải tái tạo các trường theo **đúng hợp đồng** rồi tính HMAC. Nếu byte body đã thay đổi, `SHA256(originalBodyBytes) != SHA256(serverBodyBytes)` với xác suất cực cao; canonical string sẽ khác và chữ ký không còn hợp lệ.

Điều cần phân biệt:

| Hiện tượng | Điều đã sai | Xử lý điển hình |
|---|---|---|
| Client ký body A, gửi body B | Tính toàn vẹn của phần body được ký | HMAC không hợp lệ → 401 theo chính sách API |
| Body nguyên vẹn nhưng gateway rewrite URI được ký | Canonical request không thống nhất | HMAC không hợp lệ → 401; sửa hợp đồng/route |
| Body/URI nguyên vẹn, secret hoặc key ID sai | Khóa dùng để xác minh không đúng | Không xác thực được → 401 |
| Chữ ký đúng, JSON không parse được | Lỗi cú pháp payload sau xác thực | 400 Bad Request (theo API) |
| Chữ ký đúng, JSON hợp lệ nhưng thiếu trường nghiệp vụ | Validation của payload | 400 hoặc 422 theo hợp đồng |
| Chữ ký đúng, principal không có quyền thao tác | Authorization | 403 Forbidden |
| Body quá lớn trước khi đọc/hash | Giới hạn tài nguyên | 413 Content Too Large |
| Không truy cập được key store/nonce store | Không thể xác minh an toàn | 503 hoặc lỗi server phù hợp; fail closed |

**Body mismatch là lỗi về tính toàn vẹn của dữ liệu xác thực**, không tự động là lỗi “JSON không hợp lệ”. Server có thể parse body B thành một đối tượng hợp lệ, nhưng điều đó không chứng minh body B là thứ client đã ký.

### 2.1. Body dạng byte khác body dạng đối tượng

Hai payload sau có thể có ý nghĩa JSON tương đương:

~~~json
{"amount":125000,"currency":"VND"}
~~~

~~~json
{ "currency": "VND", "amount": 125000 }
~~~

Nhưng các byte chứa dấu cách và thứ tự field khác nhau; SHA-256 trên byte gốc cũng khác. Nếu contract ký **raw body**, không được lấy body đã parse thành `Map` rồi serialize lại để tính HMAC: thứ tự trường, whitespace, escape Unicode, cách ghi số và ký tự xuống dòng đều có thể thay đổi.

Muốn hai JSON tương đương tạo cùng chữ ký, hệ thống phải **quy định một chuẩn canonical JSON cụ thể** và dùng thống nhất ở mọi phía. Không được tự phát thêm “chuẩn hóa JSON” chỉ tại verifier; điều đó thay đổi chính đối tượng được xác thực và có thể tạo nhập nhằng khi parser của nghiệp vụ diễn giải khác canonicalizer.

### 2.2. Body rỗng, không có body và body có whitespace

Nếu hợp đồng ký byte body, một request không gửi body thường được xử lý theo quy ước **mảng byte rỗng**. Hash SHA-256 của 0 byte là:

~~~text
e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
~~~

Đó **không phải** hash của chuỗi literal `null`, `"{}"`, `"[]"`, chuỗi `" "` hay dấu xuống dòng. Nếu API phân biệt “không có body” với “body độ dài bằng 0”, phải đưa dấu phân biệt đó vào hợp đồng ký một cách tường minh; đừng để một phía dùng `null` còn phía kia dùng `byte[0]` một cách ngầm định.

## 3. Những nguyên nhân thường làm body không khớp

| Nguồn thay đổi | Ví dụ | Cách phát hiện |
|---|---|---|
| Serializer của client | Ký JSON compact, HTTP client gửi JSON pretty-print | So sánh digest ngay trước ký và tại lớp gửi thực tế |
| Charset/encoding | Ký UTF-8, gửi byte UTF-16 hoặc thêm BOM | Kiểm tra byte array và `Content-Type`/charset |
| Line endings | `\n` thành `\r\n` hoặc thêm newline cuối file | So sánh độ dài, SHA-256 và hex trong fixture không nhạy cảm |
| JSON escaping | `"\u00e9"` thay bằng ký tự `é` ở UTF-8 | Cả hai có thể parse giống nhau nhưng byte khác |
| Gateway/WAF | Parse rồi serialize lại JSON, chuẩn hóa whitespace, thêm trường | So sánh digest client, sau proxy và trước verifier |
| Compression | Client ký gzip bytes nhưng proxy giải nén trước verify | Chốt rõ ký bytes trước hay sau content decoding |
| Middleware ở service | Filter đọc/transform body trước HMAC filter | Kiểm tra filter order và wrapper/decorator |
| Multipart/form | Proxy chuyển boundary, đổi encoding/field order | Test đúng byte representation theo hợp đồng, không ký một form đã parse tùy ý |
| SDK retry | Body bị dựng lại nhưng tái sử dụng timestamp/nonce/signature cũ | Tính lại chữ ký trên chính payload của mỗi lần gửi |
| Streaming / upload | Một phần body bị bỏ, buffer bị đọc trước, body bị cắt theo giới hạn | Test EOF, kích thước, backpressure, giới hạn và đọc lại |

Không phải mọi thay đổi ở tầng mạng đều đổi **representation body**. Ví dụ, HTTP/1.1 chunked transfer có thể được proxy tập hợp thành một luồng bytes có cùng nội dung; nếu hợp đồng ký **entity content bytes**, cách chia chunk trên wire không cần là phần chữ ký. Ngược lại, `Content-Encoding: gzip` là một lớp biểu diễn nội dung: nếu proxy giải nén, các byte mà tầng ứng dụng nhận có thể khác. Contract phải nói chính xác byte nào được ký, tại điểm nào so với content decoding.

### 3.1. Body bị sửa dù cùng một đối tượng JSON

Một dòng code tưởng như vô hại:

~~~java
// Cách làm dễ gây mismatch nếu hợp đồng ký raw body:
Map<String, Object> parsed = objectMapper.readValue(
        requestBytes, new TypeReference<>() {});
byte[] rebuilt = objectMapper.writeValueAsBytes(parsed);
String bodyHash = sha256Hex(rebuilt);
~~~

Nó hash `rebuilt` thay vì `requestBytes`. Hãy hash **đúng byte đã được client ký theo hợp đồng** và dùng byte đó cho bước verify. Việc deserialize để validate nghiệp vụ nên diễn ra **sau khi đã xác thực**.

### 3.2. Proxy thay đổi body giữa các hop

Ví dụ:

~~~mermaid
flowchart TD
    A[Client: JSON A] --> B[HMAC ký SHA-256 của A]
    B --> C[API gateway]
    C --> D{Proxy có transform body?}
    D -- Không --> E[Service nhận A]
    D -- Có: reserialize / decompress --> F[Service nhận B]
    E --> G[Hash A; chữ ký khớp]
    F --> H[Hash B; chữ ký sai]
    G --> I[Xử lý authn và authz tiếp]
    H --> J[401; không chạy nghiệp vụ]
~~~

Giải pháp ưu tiên là xác định **một biểu diễn canonical có thể bảo toàn qua tất cả hop**. Có thể tắt transform trên những route ký raw bytes, hoặc thống nhất một quy tắc canonicalization có phiên bản giữa client và server. Nếu gateway cố ý sửa body thì cần xem xét thay đổi thiết kế ranh giới xác thực (ví dụ gateway xác minh chữ ký gốc rồi phát hành một assertion được bảo vệ); không “bỏ body khỏi chữ ký” một cách âm thầm.

### 3.3. Lỗi khi đọc body tại service

Trong **Spring MVC**, servlet request body thường được đọc từ input stream. Nếu một custom filter đọc stream để tính hash rồi gọi `chain.doFilter` mà không cung cấp lại body cho controller, controller có thể nhận body rỗng. `ContentCachingRequestWrapper` hỗ trợ cache dữ liệu đã đọc nhưng **không mặc nhiên giúp phát lại input stream đã bị tiêu thụ**. Khi cần cả filter và handler đọc cùng payload, phải có wrapper replay thực sự, có giới hạn dung lượng.

Trong **Spring WebFlux**, `request.getBody()` là `Flux<DataBuffer>`. Sau khi một filter tiêu thụ publisher, request chuyển tiếp phải có `ServerHttpRequestDecorator` cung cấp lại dữ liệu phù hợp. Khi dùng `DataBufferUtils.join(...)` cần đặt giới hạn kích thước, release buffer đúng hợp đồng và tránh `block()` trên event-loop.

Nếu body bị đọc mất trước khi tính hash, server có thể vô tình kiểm tra hash của **byte[0]** thay vì request thật; đó là lỗi pipeline, không phải bằng chứng client gửi payload rỗng.

## 4. Chọn HTTP status và nội dung lỗi

Một request thuộc endpoint **bắt buộc HMAC** nhưng chữ ký không khớp vì body bị đổi phải được xử lý như **không xác thực được request**. Với API của bài học, lựa chọn nhất quán là **401 Unauthorized**, kèm `WWW-Authenticate` theo hợp đồng. Không trả về chi tiết giúp kẻ tấn công phân biệt “client ID tồn tại”, “hash body thực tế”, “expected signature” hay “secret nào đang được dùng”.

Ví dụ response:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: HMAC realm="signed-api"
Content-Type: application/problem+json
Cache-Control: no-store

{"type":"about:blank","title":"Unauthorized","status":401}
~~~

`HMAC` trong header challenge là **scheme tự thỏa thuận của API ví dụ**, không phải quy ước chung được mọi HTTP client hiểu. Server trả 401 nên gửi challenge đúng hợp đồng HTTP, còn client cần tài liệu cụ thể về cách tạo và truyền chữ ký.

Đừng trả:

~~~json
{
  "expectedBodySha256": "hash-tinh-duoc-tren-server",
  "expectedSignature": "chu-ky-server-tinh-duoc",
  "secretId": "chi-tiet-noi-bo"
}
~~~

Một response như vậy làm lộ thông tin chẩn đoán nhạy cảm và có thể trở thành oracle giúp đối thủ khám phá cơ chế ký. Dùng thông báo lỗi ngắn, ổn định; ghi mã lỗi riêng trong log an toàn phía server, ví dụ `AUTH_SIGNATURE_MISMATCH`, nhưng không gắn nhãn `BODY_MISMATCH` nếu **chưa có bằng chứng** rằng chính body khác (signature sai cũng có thể do method, URI, key, timestamp hay nonce).

### 4.1. Không nhầm với lỗi parse hoặc business validation

Đường xử lý nên là:

~~~text
HTTP request
  → giới hạn kích thước và kiểm tra cấu trúc HTTP cơ bản
  → xác định representation body theo hợp đồng
  → xác minh HMAC, timestamp, nonce và key
  → authentication thành công
  → authorization (quyền / tenant / resource)
  → parse và validate payload nghiệp vụ
  → controller thực thi
~~~

Thứ tự parse có thể thay đổi vì nhu cầu framework hoặc validation, nhưng **không được phát sinh side effect hay coi payload là đáng tin trước khi xác thực**. Nếu body sai cú pháp HTTP, lỗi có thể được phát hiện trước bước HMAC. Nếu body là JSON không hợp lệ nhưng bytes vẫn được ký đúng, đó là vấn đề parse/validation; status thường là 400 chứ không phải 401.

| Điều kiện | Status minh họa | Ý nghĩa |
|---|---|---|
| Signature HMAC sai dù body parse được | **401** | Chưa xác thực hợp lệ |
| Thiếu key ID/signature bắt buộc | **401** | Chưa có chứng thực hợp lệ |
| Timestamp ngoài window hoặc nonce đã được dùng | **401** | Yêu cầu không vượt qua xác thực |
| Header HTTP malformed theo hợp đồng | **400** (hoặc 401 theo policy authn đã thống nhất) | Lỗi cú pháp đầu vào |
| Content type không được API hỗ trợ | **415** | Unsupported Media Type |
| Body vượt giới hạn ứng dụng | **413** | Content Too Large |
| Signature đúng nhưng thiếu authority | **403** | Forbidden sau xác thực |
| Signature đúng, nội dung JSON sai schema | **400/422** theo hợp đồng | Validation nội dung |
| Kho key/nonce lỗi | **503** (ví dụ) | Không thể xác minh, fail closed |

Với một request đã được xác thực nhưng thiếu quyền, trả **403** từ authorization layer. HMAC không tự thay thế quyền truy cập. Không trả 403 chỉ vì body được ký không khớp.

## 5. Ví dụ Java 17+: xác minh chữ ký ràng buộc body bytes

Ví dụ tách riêng phần **tính HMAC trên byte body** để thấy rõ nơi dễ phát sinh mismatch. Adapter HTTP chịu trách nhiệm thu body trong giới hạn, kiểm tra cú pháp header, lấy đúng **public request target** nếu có proxy và tra secret đã được cấp cho key ID. Ví dụ **không** tự thay thế đầy đủ nonce store, key rotation, authorization hoặc security filter.

~~~java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.util.Base64;
import java.util.HexFormat;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public final class HmacBodyVerifier {
    private HmacBodyVerifier() {}

    public static String sha256Hex(byte[] originalBody) {
        try {
            byte[] digest = MessageDigest.getInstance("SHA-256")
                    .digest(originalBody);
            return HexFormat.of().formatHex(digest);
        } catch (GeneralSecurityException e) {
            throw new IllegalStateException("SHA-256 unavailable", e);
        }
    }

    // Tất cả thành phần đã qua kiểm tra format, uniqueness và source trust.
    // rawQuery = "" khi URI không có query.
    public static String canonical(
            String method, String publicRawPath, String rawQuery,
            String keyId, String timestamp, String nonce, byte[] originalBody) {
        return String.join("\n",
                "HMAC-V1",
                method,
                publicRawPath,
                rawQuery,
                keyId,
                timestamp,
                nonce,
                sha256Hex(originalBody));
    }

    public static boolean signatureMatches(
            byte[] sharedSecret, String canonical, String signatureBase64) {
        // HTTP adapter phải giới hạn chiều dài signature/header trước khi gọi.
        if (signatureBase64 == null || signatureBase64.length() > 256) {
            return false;
        }
        final byte[] received;
        try {
            received = Base64.getDecoder().decode(signatureBase64);
        } catch (IllegalArgumentException malformed) {
            return false;
        }
        if (received.length != 32) {
            return false; // HMAC-SHA256 tạo 32 byte.
        }
        try {
            Mac mac = Mac.getInstance("HmacSHA256");
            mac.init(new SecretKeySpec(sharedSecret, "HmacSHA256"));
            byte[] expected = mac.doFinal(
                    canonical.getBytes(StandardCharsets.UTF_8));
            return MessageDigest.isEqual(expected, received);
        } catch (GeneralSecurityException e) {
            // Lỗi crypto provider là lỗi vận hành, không phải bad credentials.
            throw new IllegalStateException("Cannot verify HMAC", e);
        }
    }
}
~~~

Trong mã này:

- Hash tính trực tiếp trên `originalBody`; không chuyển byte array thành `String`, không trim hoặc serialize JSON lại.
- `canonical` có dấu xuống dòng LF cố định và đúng thứ tự các trường trong hợp đồng. **Input chứa newline hoặc control character phải bị từ chối trước**, tránh nhập nhằng ranh giới giữa các trường.
- Chữ ký Base64 được decode nghiêm ngặt, giới hạn chiều dài và so sánh dạng byte với `MessageDigest.isEqual`; không dùng `String.equals` để so sánh MAC.
- Mỗi lần xác minh tạo một `Mac` riêng vì `Mac` có trạng thái mutable và không dùng chung giữa request đồng thời.
- Không log `sharedSecret`, `canonical` chứa dữ liệu nhạy cảm, expected HMAC hay signature của client.

### 5.1. Luồng adapter HTTP cần triển khai

~~~text
HMAC filter trên route bắt buộc ký:
    giới hạn kích thước body trước khi buffer/hash
    bảo toàn raw bytes theo hợp đồng cho cả verifier và handler
    đọc đúng một giá trị cho mỗi header HMAC bắt buộc
    kiểm tra version, thuật toán, encoding và cú pháp
    xác định public method/URI đáng tin qua proxy
    lấy key active theo key ID từ server-side key store
    kiểm tra timestamp theo clock/cửa sổ đã cấu hình

    canonical = HmacBodyVerifier.canonical(..., bodyBytes)
    if !HmacBodyVerifier.signatureMatches(secret, canonical, signature):
        trả 401 và dừng filter chain

    claim nonce atomically trong shared nonce store
    nếu nonce đã dùng: trả 401 và dừng
    nếu kho nonce/key lỗi: trả 503 và dừng

    tạo Authentication từ client/tenant/authority phía server
    chuyển sang authorization
    nếu thiếu quyền: trả 403, không chạy nghiệp vụ
    nếu đủ quyền: chuyển body nguyên vẹn cho handler
~~~

Không chuyển sang “body hash chỉ mang tính tham khảo” sau khi thấy chữ ký sai. Nếu contract tuyên bố body được ký, việc bỏ `bodyDigest` khỏi canonical sẽ vô hiệu hóa bảo đảm tính toàn vẹn.

### 5.2. Đừng lấy header body digest làm nguồn sự thật

Một số giao thức đưa `X-Content-SHA256` hoặc `Digest`/`Content-Digest` vào request. Nếu có, server vẫn phải **tự tính digest từ body nhận được**, so sánh với giá trị khai báo và bảo đảm digest được ràng buộc bởi HMAC theo hợp đồng. Chỉ tin một header do client gửi rồi ký/so sánh header mà không kiểm tra body có thể cho phép gửi nội dung khác với digest đã khai báo.

Ví dụ, nếu canonical chỉ chứa `X-Content-SHA256`, service phải kiểm tra:

~~~text
digestHeader == SHA256(actualBodyBytes)
AND
signature == HMAC(secret, canonicalIncludingDigestHeader)
~~~

Nếu một trong hai điều kiện sai, request không được thực hiện nghiệp vụ. Khi lỗi, chỉ cần phản hồi xác thực chung theo policy, tránh tạo nhiều oracle cho attacker.

## 6. Test đơn vị cho body mismatch

Một bài test dễ đọc: tạo chữ ký cho body A, sau đó dùng **cùng chữ ký** để xác minh body B có khác biệt nhỏ. Mẫu JUnit 5 dưới đây giả sử các import liên quan đã có trong test source:

~~~java
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.util.Base64;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import org.junit.jupiter.api.Test;

class HmacBodyVerifierTest {
    @Test
    void changedBodyFailsAuthentication() throws GeneralSecurityException {
        byte[] secret = "test-secret-only".getBytes(StandardCharsets.UTF_8);
        byte[] bodyA = "{\"amount\":125000,\"currency\":\"VND\"}"
                .getBytes(StandardCharsets.UTF_8);
        byte[] bodyB = "{ \"currency\": \"VND\", \"amount\": 125000 }"
                .getBytes(StandardCharsets.UTF_8);

        String canonicalA = HmacBodyVerifier.canonical(
                "POST", "/api/payments", "", "client-a",
                "2026-11-28T03:20:00Z", "nonce-123", bodyA);

        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(secret, "HmacSHA256"));
        String signatureA = Base64.getEncoder().encodeToString(
                mac.doFinal(canonicalA.getBytes(StandardCharsets.UTF_8)));

        assertTrue(HmacBodyVerifier.signatureMatches(
                secret, canonicalA, signatureA));

        String canonicalB = HmacBodyVerifier.canonical(
                "POST", "/api/payments", "", "client-a",
                "2026-11-28T03:20:00Z", "nonce-123", bodyB);
        assertFalse(HmacBodyVerifier.signatureMatches(
                secret, canonicalB, signatureA));
    }
}
~~~

Test này kiểm tra trực tiếp việc HMAC bảo vệ byte body, **chưa chứng minh cả giao thức HTTP được bảo vệ**. Với production, cần vector chữ ký được tính độc lập với verifier (và một số test vector cố định) để tránh cùng một lỗi canonicalization trong cả signer và verifier làm test vẫn xanh.

### 6.1. Test matrix không thể thiếu

| Ca kiểm thử | Điều kỳ vọng |
|---|---|
| Body A đã ký, gửi nguyên byte A | HMAC hợp lệ nếu method/URI/key/timestamp/nonce cũng hợp lệ |
| Body A đã ký, gửi body B chỉ khác một dấu cách | 401; handler không được gọi |
| JSON đổi thứ tự field nhưng cùng semantic | 401 nếu ký raw body |
| Thêm hoặc xóa newline cuối body | 401 |
| Thay đổi UTF-8 BOM, ký tự Unicode/escape hoặc charset | 401 nếu byte được ký khác |
| Không có body vs body rỗng | Theo quy ước contract; hash đúng `byte[0]` nếu hai trường hợp được xem tương đương |
| Header khai báo digest khác digest tự tính | Từ chối xác thực, không tin header |
| Header signature sai Base64/quá dài hoặc trùng nhiều giá trị | Từ chối; không dò giá trị khác để tìm chữ ký khớp |
| Request đúng chữ ký, JSON không hợp lệ | 400/422 theo validation contract sau xác thực |
| Body vượt giới hạn gateway/service | 413, không buffer không giới hạn |
| Gateway giải nén/rewrite body không theo contract | Từ chối, không tự bỏ kiểm tra body |
| HMAC đúng nhưng thiếu authority | 403, không có side effect |
| Key ID bị revoke hoặc ngoài hiệu lực rotation | 401 |
| Nonce dùng lại đến hai replica | Tối đa một request được claim nonce |
| Key/nonce store không sẵn sàng | Fail closed, 503 hoặc lỗi hệ thống phù hợp |

Với mỗi test từ chối, cần assert cả **status** lẫn **không có side effect** (không ghi thanh toán, không phát event, không gọi dịch vụ khác). Nếu chỉ kiểm tra status nhưng filter vẫn chuyển tiếp chain, test sẽ bỏ sót lỗi nghiêm trọng.

## 7. Kiểm thử xuyên gateway và proxy

Giả sử client ký:

~~~text
POST https://api.example.test/public/v1/payments?source=partner
body = {"amount":125000,"currency":"VND"}
~~~

Gateway có thể rewrite `/public/v1/payments` thành `/payments`. Nếu canonical gồm **public path**, service cần lấy public target từ nguồn đã được xác thực và bảo vệ, đồng thời ràng buộc nó với endpoint nội bộ thực sự. Nếu canonical body có ký byte gốc, proxy phải bảo toàn byte body đến service hoặc thực hiện chuyển giao có hợp đồng rõ ràng.

Các phép thử end-to-end nên đi qua proxy thực sự:

1. **Happy path:** gửi body ký hợp lệ qua proxy, gateway chỉ rewrite route đã cho phép; service trả thành công theo API và handler chạy đúng một lần.
2. **Body bị transform:** cấu hình test proxy thay JSON A thành JSON B; giữ signature A. Service phải trả 401 và không tạo giao dịch.
3. **Path/query bị transform:** body không đổi nhưng sửa public target đã ký; service từ chối, trừ các phép chuẩn hóa được hợp đồng quy định rõ.
4. **Compression:** gửi `Content-Encoding: gzip`, kiểm tra client ký compressed bytes hay decompressed bytes theo đúng policy; thay kiểu transform ngoài hợp đồng phải bị từ chối.
5. **Giả mạo metadata:** client gửi `X-Original-URI`/`X-Forwarded-*`/`X-Internal-Public-Target` giả. Ingress phải strip/overwrite header nội bộ, service chỉ tin hop đã xác thực và route mapping hợp lệ.
6. **Hai replica:** gửi lại cùng signed request tới các replica khác nhau để xác minh nonce store **atomic và dùng chung**.
7. **Key rotation:** ký bằng key mới/cũ trong thời gian overlap; sau revoke phải từ chối key cũ ở mọi replica.

Thu thập **digest, độ dài và correlation ID** tại các điểm kiểm thử được phép ghi, nhưng không log payload nhạy cảm hoặc secret. Nếu hash tại client và service khác nhau, kiểm tra xem hai phía có thực sự hash **cùng tầng representation** hay không trước khi kết luận proxy đã làm hỏng dữ liệu.

### 7.1. Chẩn đoán khi “body không khớp”

Để tìm nguyên nhân không cần log toàn bộ nội dung request:

1. Cố định body fixture, biết rõ byte array gửi lên, tính digest trước bước tạo chữ ký.
2. Dùng client HTTP có khả năng gửi **chính xác những bytes đã ký** (không gửi đối tượng rồi để thư viện tự serialize lần hai).
3. Trên môi trường test có kiểm soát, đo độ dài/digest byte body ở gateway trước và sau transform, rồi tại service **trước verifier**.
4. Nếu digest khác, kiểm tra middleware serialize JSON, charset, newline, gzip, multipart và body buffering.
5. Nếu digest bằng nhưng HMAC sai, kiểm tra method, public URI/query, các header được ký, encoding signature, key ID và canonical separator.
6. Nếu chữ ký khớp nhưng request vẫn bị từ chối, kiểm tra timestamp, nonce, key status, authorization hoặc payload validation theo đúng status thực tế.

**Không suy ra “body khác” chỉ từ HTTP 401.** Một 401 trả chung là chủ ý để giảm lộ thông tin xác thực; kết luận chi tiết thuộc về test fixture và log nội bộ đã giới hạn truy cập.

## 8. Chống replay và key rotation liên quan thế nào đến body?

Nếu attacker giữ nguyên body và chữ ký rồi phát lại request, HMAC vẫn khớp. Đó không phải lỗi body mismatch mà là **replay**, cần kiểm tra timestamp/nonce. Nonce phải được claim nguyên tử trong shared store (ví dụ thao tác tương đương Redis `SET NX PX`) sau khi signature hợp lệ và trước side effect. TTL phải bao phủ cửa sổ mà request đã chấp nhận vẫn có thể bị gửi lại; không dùng hai thao tác “kiểm tra rồi insert” tách rời.

Ngược lại, client muốn retry cùng giao dịch nhưng **sửa body** thì phải tạo lại body digest, canonical string, HMAC và thông thường dùng timestamp/nonce mới. Để tránh tạo nhiều thanh toán khi mạng mất response, hãy dùng **idempotency key** riêng; nonce HMAC và idempotency phục vụ hai mục đích khác nhau.

Khi rotate secret, một key ID phải ánh xạ đến đúng key còn hiệu lực cho client/tenant. Signature mismatch với key mới có thể do client tiếp tục ký bằng secret cũ nhưng gửi key ID mới; đó là lỗi credential/canonical, không phải bằng chứng body đã đổi. Server không được thử hết mọi secret hoặc nới bỏ xác minh body để làm request thành công.

## 9. Sai lầm dễ gặp và cách phòng tránh

**“JSON nhìn giống nhau nên hash phải giống.”** Sai nếu ký byte raw. Phải đối chiếu byte, không đối chiếu đối tượng đã parse.

**“Cứ serialize JSON lại trước khi verify để chuẩn hóa.”** Chỉ đúng nếu hợp đồng có canonical JSON được định nghĩa chính xác và client cũng áp dụng; nếu không sẽ tạo sai lệch hoặc lỗ hổng diễn giải khác nhau giữa các parser.

**“Body hash lấy từ header là đủ.”** Sai nếu không tự hash actual body và không ràng buộc header digest với HMAC.

**“Proxy đã đổi body, tạm thời bỏ body khỏi canonical.”** Điều này làm mất bảo vệ nội dung request. Cần sửa data path hoặc thay đổi hợp đồng ký có phiên bản và kiểm thử an toàn.

**“Signature sai thì trả 403.”** Sai ngữ nghĩa: chữ ký sai thuộc authentication → 401 theo chính sách của ví dụ; 403 dành cho principal đã xác thực nhưng thiếu quyền.

**“Test ký và gửi hai lần serialize cùng object là đủ.”** Chưa đủ: trong test cần kiểm soát chính xác byte array trên wire, kể cả trường hợp proxy thay đổi nội dung.

**“Khi nonce store lỗi thì cho qua để tránh downtime.”** Sai: request phải fail closed; nếu không, attacker có thể replay chữ ký hợp lệ.

**“Body lớn thì cứ buffer hết rồi hash.”** Dễ gây cạn bộ nhớ. Cần giới hạn kích thước; với streaming/upload lớn, thiết kế hợp đồng ký stream/spooling phù hợp thay vì lưu vô hạn.

## 10. Checklist thực hành

- [ ] Hợp đồng HMAC mô tả chính xác byte representation body được ký, charset, content encoding, trường header/path/query, version và thuật toán.
- [ ] HTTP client ký **cùng byte array** thực sự được gửi; không để bước serialize thứ hai thay đổi payload.
- [ ] Service hash đúng byte theo hợp đồng, không parse/serialize lại body trước khi tính chữ ký.
- [ ] Có giới hạn body và giải pháp replay/caching an toàn cho Servlet/WebFlux; không làm mất body của handler.
- [ ] Gateway/proxy bảo toàn nội dung đã ký hoặc có thiết kế chuyển giao được bảo vệ; public route được ánh xạ đúng với internal route.
- [ ] Digest do client khai báo được kiểm tra lại từ body thật và được ràng buộc bởi chữ ký.
- [ ] Signature so sánh theo byte với hàm phù hợp; header HMAC sai/thiếu/trùng được từ chối.
- [ ] 401 cho signature không hợp lệ, 403 cho thiếu quyền, 413 cho quá lớn; lỗi hạ tầng không được biến thành cho qua xác thực.
- [ ] Timestamp/nonce chống replay và key rotation/revoke được kiểm tra độc lập với body digest.
- [ ] Test JSON thay whitespace/order, newline, Unicode, gzip, body rỗng, proxy transform và nhiều replica.
- [ ] Mọi request bị từ chối không có side effect; log chẩn đoán không chứa secret, raw signature hoặc body nhạy cảm.

**Điểm cốt lõi:** khi chữ ký HMAC bảo vệ body, *body không khớp* nghĩa là dữ liệu được xác minh không còn đúng với nội dung đã được ký theo hợp đồng. Cách sửa là tìm và xử lý chỗ bytes/canonical request bị thay đổi, đồng thời giữ nguyên ranh giới xác thực, chống replay và phân quyền. Một response 401 nhất quán cho client và bằng chứng kiểm thử có kiểm soát ở nội bộ giúp vừa bảo vệ hệ thống vừa chẩn đoán được sự cố.
