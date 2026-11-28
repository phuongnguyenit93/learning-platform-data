# Changed query test: kiểm thử thay đổi query sau khi ký HMAC

## 1. Mục tiêu và rủi ro cần kiểm chứng

Trong module **SECURITY_AUTHENTICATION_HMAC_REQUEST_AUTHENTICATION**, một HTTP request được xác thực bằng **HMAC với shared secret** và **canonical request** do client/server thỏa thuận. Dữ liệu được ký có thể gồm phương thức, URI, header và/hoặc digest của body. Server phải xác minh chữ ký, chống replay bằng timestamp/nonce, quản lý key rotation, kiểm tra đường đi qua proxy/gateway và tách **authentication** khỏi **authorization**.

Chương **Testing HMAC** đưa các cam kết đó thành phép thử có khả năng phát hiện regression. Bài **Changed query test** tập trung vào câu hỏi:

> Nếu client đã ký URL query ban đầu, nhưng query bị thay đổi trước khi tới verifier và **chữ ký không được tính lại**, hệ thống có phát hiện và từ chối request hay không?

Ví dụ client dự kiến gọi:

~~~http
POST /public/v1/payments?account=A123&mode=preview HTTP/1.1
Host: api.example.test
X-Key-Id: partner-a-v3
X-Timestamp: 2026-11-28T03:30:00Z
X-Nonce: 4f159a74-69c8-41da-b33c-e545a83537f2
X-Signature: <signature-for-original-query>
Content-Type: application/json

{"amount":125000,"currency":"VND"}
~~~

Kẻ tấn công hoặc một proxy cấu hình sai thay query thành:

~~~http
POST /public/v1/payments?account=B999&mode=execute HTTP/1.1
X-Key-Id: partner-a-v3
X-Timestamp: 2026-11-28T03:30:00Z
X-Nonce: 4f159a74-69c8-41da-b33c-e545a83537f2
X-Signature: <signature-for-original-query>
~~~

Nếu hợp đồng HMAC **bảo vệ query**, verifier phải từ chối request bị thay đổi. Nếu vẫn xử lý thanh toán cho `account=B999`, có khả năng server đã bỏ query khỏi canonical string, lấy query khác với query controller xử lý, canonicalize nhập nhằng hoặc thực hiện nghiệp vụ trước khi xác minh.

**Điều kiện quan trọng:** HMAC chỉ phát hiện thay đổi ở những trường **thực sự được đưa vào hợp đồng ký**. Nếu API chủ động không ký query, test không thể kỳ vọng HMAC chặn thay đổi query; khi đó hệ thống phải đánh giá lại rủi ro và ràng buộc tính toàn vẹn của các tham số có ảnh hưởng đến tài nguyên/quyền.

Sau bài này, người học có thể:

1. Xây **test dương** cho request có query hợp lệ và **test âm** thay query nhưng giữ nguyên HMAC.
2. Phân biệt ký **raw query** với ký **canonical query** đã chuẩn hóa; xác định kết quả đúng cho reorder/encoding/duplicate parameters.
3. Viết Java/JUnit test vector và integration test gửi request thực sự qua gateway/proxy.
4. Assert 401 và **không có side effect**, không chỉ nhìn response code.
5. Bao phủ timestamp/nonce, key rotation, route mapping và authorization mà không làm nhiễu kết quả test query tampering.

## 2. Hợp đồng canonical request là oracle của phép thử

Không tồn tại một chuẩn HMAC HTTP tự động áp dụng cho mọi API. Trước khi viết assertion, test phải biết **chính xác bytes nào được ký**. Ví dụ, hợp đồng minh họa `HMAC-V1` yêu cầu:

~~~text
HMAC-V1
<UPPERCASE_HTTP_METHOD>
<PUBLIC_RAW_PATH>
<PUBLIC_RAW_QUERY_OR_EMPTY>
<KEY_ID>
<UTC_TIMESTAMP>
<NONCE>
<LOWERCASE_HEX_SHA256_OF_BODY_BYTES>
~~~

Canonical string cho request đầu tiên:

~~~text
HMAC-V1
POST
/public/v1/payments
account=A123&mode=preview
partner-a-v3
2026-11-28T03:30:00Z
4f159a74-69c8-41da-b33c-e545a83537f2
<64-ky-tu-hex-cua-sha256-body>
~~~

Quy trình tạo chữ ký:

~~~text
bodyDigest = lowercaseHex(SHA256(exactBodyBytes))
canonical  = UTF8(joinWithLF(signedFields, bodyDigest))
signature  = Base64(HMAC-SHA256(sharedSecret, canonical))
~~~

Server phải tái tạo **đúng hợp đồng** rồi so sánh MAC bằng phép so sánh byte phù hợp, chẳng hạn `MessageDigest.isEqual`. Key ID chỉ là **lookup hint** trước khi MAC được xác minh; nó chưa phải danh tính đã xác thực.

Khi đổi `account=A123` thành `account=B999`:

~~~text
canonicalOriginal != canonicalChanged
HMAC(secret, canonicalOriginal) != HMAC(secret, canonicalChanged)
~~~

Điều này đúng với xác suất áp đảo theo tính chất HMAC-SHA256. Test phải gửi `canonicalChanged` ở wire nhưng giữ lại chữ ký tính theo `canonicalOriginal` để phát hiện verifier không ràng buộc query.

### 2.1. Query nào là query được ký?

| Thành phần | Vai trò | Ví dụ |
|---|---|---|
| Public raw path | Đường dẫn client nhìn thấy | `/public/v1/payments` |
| Raw query | Các byte ký tự query trong request target, **không gồm dấu `?`** theo hợp đồng mẫu | `account=A123&mode=preview` |
| Query parse thành map | Cấu trúc nghiệp vụ sau khi phân tích | `account -> A123`, `mode -> preview` |
| Internal route | Đường dẫn service nhìn thấy sau rewrite | `/payments` |
| Fragment | Chỉ tồn tại phía client, không được gửi trong HTTP request target | `#section` |

Nếu gateway rewrite public path thành internal path, service phải xác định signed public target từ nguồn đáng tin cậy hoặc dùng một định danh route logic được thỏa thuận. **Không lấy `X-Original-URI` hay `X-Forwarded-*` do client tự gửi làm sự thật**, vì attacker có thể điều khiển giá trị đó. Ingress phải sanitize metadata nội bộ, mỗi hop được bảo vệ và service đối chiếu route mapping.

### 2.2. Phân biệt hai hợp đồng query phổ biến

**Hợp đồng A — ký raw query:** ký biểu diễn query gốc theo HTTP request target mà phía xác minh quan sát một cách đáng tin:

~~~text
q1 = account=A123&mode=preview
q2 = mode=preview&account=A123

q1 != q2
=> giữ nguyên MAC của q1 để gửi q2 phải bị từ chối.
~~~

**Hợp đồng B — ký canonical query:** parse theo quy tắc được xác định đầy đủ, chuẩn hóa encoding và thứ tự, rồi ký biểu diễn chuẩn:

~~~text
q1 = account=A123&mode=preview
q2 = mode=preview&account=A123

canonicalQuery(q1) == canonicalQuery(q2)
=> có thể nhận cả hai nếu cả client, verifier và handler
   cùng diễn giải tham số và hợp đồng cho phép.
~~~

Không thể tự suy từ tên “Changed query” rằng **đổi thứ tự** luôn phải làm HMAC sai. Phép thử phải tuân theo hợp đồng. Tuy nhiên **thay đổi giá trị đã được bảo vệ** như `account=A123` → `account=B999` vẫn phải làm MAC không khớp nếu canonicalization không chủ động coi hai giá trị này là tương đương.

## 3. Threat model: thay query có thể thay đổi hành động

Query không chỉ để lọc dữ liệu. Nhiều API dùng query để quyết định tenant, resource, quyền hoặc mode xử lý:

| Query | Ví dụ bị thay | Rủi ro nếu query không được ký hoặc diễn giải sai |
|---|---|---|
| `account`/`tenant` | `A123` → `B999` | Gọi tài nguyên của tenant khác |
| `mode` | `preview` → `execute` | Chuyển từ xem trước sang thao tác ghi |
| `amount` | `100` → `1000` | Thay đổi tiền/giới hạn nghiệp vụ |
| `redirect_uri` | Domain dự kiến → domain khác | Có thể điều hướng dữ liệu/token sai nơi tùy chức năng |
| `includeDeleted` | `false` → `true` | Mở rộng tập dữ liệu đọc |
| `page`/`limit` | `20` → `1000000` | Gây tải nặng; có thể vượt hạn mức |
| `resourceId` | Một resource → resource khác | Sai ràng buộc object-level authorization |

Nếu một giá trị query ảnh hưởng đến nghĩa nghiệp vụ, nó phải được bảo vệ theo hợp đồng hoặc có cơ chế xác thực/authorization đủ mạnh khác; không được tin chỉ vì method và body đã được ký.

Đặc biệt, **HMAC hợp lệ không phải giấy phép truy cập mọi tài nguyên**. Với query được ký mới hoàn toàn bằng secret hợp lệ, client vẫn phải bị từ chối **403 Forbidden** nếu không sở hữu resource hoặc không có authority cần thiết. Changed query test kiểm tra *tính toàn vẹn*; authorization test kiểm tra *quyền*.

## 4. Mô hình test dương và âm đúng cách

### 4.1. Test dương: giữ nguyên query

~~~text
Q_original = "account=A123&mode=preview"
S_original = HMAC(secret, canonical(method, path, Q_original, ...))

send HTTP request:
  actual_query = Q_original
  signature    = S_original

Expected:
  authentication succeeds if key/time/nonce are valid
  authorization decides the resource
  expected handler is called according to API contract
~~~

Một baseline xanh chứng minh fixture, secret, thời gian, route và chữ ký đang tương thích. Nhưng **baseline chỉ xanh chưa chứng minh query được bảo vệ**: verifier bỏ query cũng có thể tình cờ nhận request nếu signer và verifier cùng bỏ query.

### 4.2. Test âm: ký query A, gửi query B

~~~text
Q_original = "account=A123&mode=preview"
Q_changed  = "account=B999&mode=execute"
S_original = HMAC(secret, canonical(method, path, Q_original, ...))

send HTTP request:
  actual_query = Q_changed
  signature    = S_original   // KHÔNG ký lại query B

Expected:
  401 authentication failure theo policy API
  no authenticated principal, no controller side effect
  nonce is not claimed if policy claims only after valid signature
~~~

**Lỗi thường gặp trong test:** gọi helper `signRequest()` **sau khi mutate query**. Khi đó helper tạo MAC mới đúng với query B, biến ca negative thành một request hợp lệ. Test phải cố ý giữ nguyên signature của A và thay **chỉ field đang kiểm chứng**.

### 4.3. Tránh nhiễu do timestamp và nonce

Nếu test dương gửi request trước rồi test âm **tái sử dụng cùng nonce**, request thứ hai có thể bị từ chối vì replay, kể cả khi verifier bỏ query khỏi canonical. Test như vậy **không chứng minh** query tampering đã được phát hiện.

Giải pháp:

1. Test âm dùng **nonce mới chưa từng claim**, nhưng chữ ký vẫn được tạo trên **Q_original** với chính nonce mới đó; sau khi ký, chỉ thay `actual_query`.
2. Test dùng `Clock.fixed` phía server hoặc tạo timestamp hiện hành nằm trong window.
3. Key được seed active, secret đúng, body/method/path/header không đổi, store nonce hoạt động.
4. Với unit verifier, quan sát explicit `SIGNATURE_INVALID` hoặc spy xác nhận **không gọi nonce claim** ở ca MAC sai, nếu đó là thứ tự thiết kế.
5. Test HTTP ngoài hệ thống có thể chỉ thấy 401 chung; kết luận query mismatch phải dựa trên fixture và quan sát có quyền, không dựa trên body lỗi công khai.

**Không reset nonce store production để “chữa” test.** Trong môi trường test cô lập, mỗi case nên có namespace/fixture riêng và dọn dữ liệu sau khi hoàn thành.

## 5. Bộ biến thể query cần kiểm tra

Một bộ test chỉ thay `mode=preview` thành `mode=execute` là khởi đầu tốt, nhưng chưa bao phủ những lỗi canonicalization hay gặp.

| Trường hợp | Query đã ký | Query gửi thực tế | Kỳ vọng nếu ký **raw query** |
|---|---|---|---|
| Đổi giá trị | `mode=preview` | `mode=execute` | MAC sai |
| Thêm tham số | `account=A123` | `account=A123&debug=true` | MAC sai |
| Bỏ tham số | `account=A123&mode=preview` | `account=A123` | MAC sai |
| Đổi tên key | `account=A123` | `accountId=A123` | MAC sai |
| Đảo thứ tự | `a=1&b=2` | `b=2&a=1` | MAC sai trong raw mode |
| Key lặp | `role=user` | `role=user&role=admin` | MAC sai; handler không lấy giá trị trái hợp đồng |
| Thay encoding | `q=hello%20world` | `q=hello+world` | MAC sai nếu bytes raw khác |
| Chữ hoa percent encoding | `path=%2Fhome` | `path=%2fhome` | MAC sai nếu raw mode giữ nguyên encoding |
| Đổi empty value | `flag=` | `flag` | MAC sai nếu contract phân biệt |
| Bỏ query | `x=1` | Không có query | MAC sai |
| Dấu phân tách | `x=1%26y%3D2` | `x=1&y=2` | MAC sai; khác cấu trúc tham số |
| Unicode encoding | `name=%C3%A9` | Biểu diễn khác cùng ký tự sau parse | MAC sai nếu wire representation khác |
| Fragment | `x=1` | URL client thêm `#part` | Không được kỳ vọng MAC sai chỉ vì fragment, vì fragment không gửi trong request target |

**Với canonical query mode**, bảng thay đổi: một số trường hợp như đảo thứ tự có thể hợp lệ nếu quy tắc sắp xếp và xử lý duplicate parameters được định nghĩa rõ. Cần xây **bảng kỳ vọng riêng** cho canonical mode; không thay đổi verifier cho qua mọi biến thể chỉ để các test raw mode xanh.

### 5.1. Các điểm dễ nhập nhằng

**Thứ tự tham số.** `a=1&b=2` và `b=2&a=1` thường tương đương khi handler đọc map, nhưng **khác chuỗi raw**. Nếu contract chuẩn hóa và sort theo key, hãy quy định thứ tự khi key trùng.

**Tham số trùng.** `role=user&role=admin` có thể được framework trả giá trị đầu tiên, giá trị cuối, danh sách hoặc lỗi; một verifier dùng `getParameter("role")` còn handler dùng danh sách có thể dẫn đến **HTTP parameter pollution**. Ưu tiên từ chối duplicate ở tham số đơn trị hoặc canonicalize **toàn bộ tập giá trị** theo quy tắc nhất quán.

**Percent encoding.** `%2F` và `/` hoặc `%20` và `+` có thể được một parser diễn giải tương đương trong một số ngữ cảnh nhưng không giống byte. Nếu chuẩn hóa, cần nêu rõ decode bao nhiêu lần, uppercase/lowercase hex, ký tự được phép và xử lý chuỗi percent-escape sai.

**Unicode.** Hai dạng Unicode NFC/NFD có thể hiển thị giống nhau nhưng khác byte. Nếu muốn canonical Unicode normalization, hãy áp dụng theo cùng một chuẩn đã thỏa thuận; nếu ký raw query, đừng tự động normalize ở một phía.

**Phân biệt query vắng mặt với query rỗng.** `/path` và `/path?` có thể có `rawQuery=null` hoặc `rawQuery=""` tùy thư viện. Hợp đồng mẫu quy `null` thành chuỗi rỗng; nếu cần phân biệt hai trường hợp, phải thêm dấu phân biệt vào canonical string và test riêng.

**Ký tự `#`** trong URL client đánh dấu fragment, không thuộc HTTP request target. Nếu cần literal `#` trong query, phải encode phù hợp (ví dụ `%23`) và test request thực tế trên wire.

**Một canonicalization sai ở cả signer và verifier.** Nếu test chỉ dùng lại helper server để ký request, cả hai cùng bỏ query và test dương vẫn xanh. Dùng test vector độc lập hoặc hardcoded expected MAC từ implementation khác để phát hiện sai contract.

## 6. Ví dụ Java 17+: ký query và cố ý mutate sau khi ký

Đoạn Java sau hiện thực **hợp đồng HMAC-V1 minh họa**: SHA-256 body, raw query, key ID, timestamp và nonce. Các giá trị đã phải qua validation cú pháp/độ dài theo hợp đồng trước khi đưa vào canonical string; đặc biệt không cho ký tự xuống dòng, ký tự điều khiển ở field phân tách bằng LF.

~~~java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.util.Base64;
import java.util.HexFormat;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public final class QueryHmacTestSigner {
    private QueryHmacTestSigner() {}

    public static String canonical(
            String method, String publicRawPath, String publicRawQuery,
            String keyId, String timestamp, String nonce, byte[] body)
            throws GeneralSecurityException {

        String digest = HexFormat.of().formatHex(
                MessageDigest.getInstance("SHA-256").digest(body));
        return String.join("\n",
                "HMAC-V1",
                method,
                publicRawPath,
                publicRawQuery == null ? "" : publicRawQuery,
                keyId,
                timestamp,
                nonce,
                digest);
    }

    public static byte[] sign(
            byte[] secret, String canonical)
            throws GeneralSecurityException {

        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(secret, "HmacSHA256"));
        return mac.doFinal(canonical.getBytes(StandardCharsets.UTF_8));
    }

    public static String signBase64(byte[] secret, String canonical)
            throws GeneralSecurityException {
        return Base64.getEncoder().encodeToString(sign(secret, canonical));
    }
}
~~~

Để kiểm tra biến đổi query tại mức thuật toán, test dưới đây tính signature trên canonical A, sau đó thay query trong canonical B:

~~~java
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import org.junit.jupiter.api.Test;

class ChangedQueryHmacUnitTest {

    @Test
    void changingSignedQueryInvalidatesOriginalMac() throws Exception {
        byte[] secret = "secret-for-testing-only"
                .getBytes(StandardCharsets.UTF_8);
        byte[] body = "{\"amount\":125000}".getBytes(StandardCharsets.UTF_8);
        String nonce = "fresh-nonce-0001";
        String timestamp = "2026-11-28T03:30:00Z";

        String canonicalA = QueryHmacTestSigner.canonical(
                "POST", "/public/v1/payments",
                "account=A123&mode=preview",
                "partner-a-v3", timestamp, nonce, body);

        byte[] macFromA = QueryHmacTestSigner.sign(secret, canonicalA);

        String canonicalB = QueryHmacTestSigner.canonical(
                "POST", "/public/v1/payments",
                "account=B999&mode=execute",
                "partner-a-v3", timestamp, nonce, body);

        assertTrue(MessageDigest.isEqual(
                macFromA, QueryHmacTestSigner.sign(secret, canonicalA)));
        assertFalse(MessageDigest.isEqual(
                macFromA, QueryHmacTestSigner.sign(secret, canonicalB)));
    }
}
~~~

Test thuật toán trên xác nhận **MAC thay đổi khi đầu vào ký thay đổi**. Nó **chưa chứng minh HTTP verifier lấy query đúng**. Hai lời gọi cùng helper signer cũng chưa thay thế test vector độc lập. Một suite đáng tin cần thêm test integration bên dưới và ít nhất một vector có expected signature được tính bằng implementation độc lập.

### 6.1. Vì sao test chỉ so sánh HMAC chưa đủ?

Một verifier có thể có bug:

~~~java
// SAI: bỏ query thực tế trong canonical string.
String canonical = method + "\n" + path + "\n" + "" + "\n" + bodyDigest;
~~~

Test `HMAC(secret, canonicalA) != HMAC(secret, canonicalB)` vẫn pass, vì test không gọi verifier. **Changed query integration test** phải gửi HTTP request vào security chain thực sự và xác minh request bị từ chối trước controller.

## 7. Integration test qua HTTP/gateway với chữ ký giữ nguyên

Môi trường test nên có:

- Client thực có khả năng kiểm soát **raw request target**, header và body bytes.
- Gateway/reverse proxy thực hoặc cấu hình tương đương staging, có thể rewrite public path sang internal route.
- Service chứa HMAC filter/verifier, key store/nonce store và Spring Security authorization như production.
- Key test active và secret giả, clock cố định/đồng bộ, nonce namespace riêng cho các test.
- Spy hoặc test database để xác nhận **không có side effect** ở request bị từ chối.

Ví dụ endpoint ngoài là `/public/v1/payments`; gateway route đến `/payments`. Hợp đồng ký **public raw path/query**. Trong code JUnit 5 sau, `proxyBase` phải do test harness cung cấp (ví dụ cổng mapped của test proxy); không gọi thẳng service:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.UUID;
import org.junit.jupiter.api.Test;

class ChangedQueryThroughProxyIT {
    private final HttpClient client = HttpClient.newHttpClient();
    private final URI proxyBase = URI.create("http://127.0.0.1:18080");
    private final byte[] testSecret =
            "secret-for-testing-only".getBytes(StandardCharsets.UTF_8);

    private HttpResponse<String> send(
            String signedQuery, String actualQuery, String nonce)
            throws Exception {

        String path = "/public/v1/payments";
        String keyId = "partner-a-v3";
        // Trong suite thật, lấy từ Clock được đồng bộ với verifier.
        String timestamp = Instant.now().toString();
        byte[] body = "{\"amount\":125000,\"currency\":\"VND\"}"
                .getBytes(StandardCharsets.UTF_8);

        String canonical = QueryHmacTestSigner.canonical(
                "POST", path, signedQuery,
                keyId, timestamp, nonce, body);
        String signature = QueryHmacTestSigner.signBase64(
                testSecret, canonical);

        // Chỉ URL gửi đi dùng actualQuery; signature vẫn ký signedQuery.
        URI target = URI.create(
                proxyBase.toString() + path + "?" + actualQuery);
        HttpRequest request = HttpRequest.newBuilder(target)
                .header("Content-Type", "application/json")
                .header("X-Key-Id", keyId)
                .header("X-Timestamp", timestamp)
                .header("X-Nonce", nonce)
                .header("X-Signature", signature)
                .POST(HttpRequest.BodyPublishers.ofByteArray(body))
                .build();

        return client.send(request, HttpResponse.BodyHandlers.ofString());
    }

    @Test
    void originalQueryIsAcceptedButChangedQueryIsRejected() throws Exception {
        String original = "account=A123&mode=preview";
        String changed = "account=B999&mode=execute";

        // Nonce độc lập cho baseline, không gây replay ở ca negative.
        HttpResponse<String> baseline = send(
                original, original, UUID.randomUUID().toString());
        assertEquals(200, baseline.statusCode());

        HttpResponse<String> tampered = send(
                original, changed, UUID.randomUUID().toString());
        assertEquals(401, tampered.statusCode());

        // Cần thêm assertion: không có payment mới cho account B999.
        // Và verifier reason/signature check phải phù hợp policy.
    }
}
~~~

`200` chỉ đúng nếu API test quy định thành công trả 200; API tạo resource có thể trả 201 hoặc mã khác. Khi chạy thực tế, fixture `account=A123` phải có quyền và body/nonce/key/timestamp đều hợp lệ. Dùng `Clock` inject/fixed hoặc time source đồng bộ để tránh test flaky vì thời gian. Trong HTTP client, `URI.create` và proxy có thể diễn giải/chuẩn hóa URI: **đối với các ca percent-encoding, duplicate query, URL bất thường, cần kiểm tra raw request target trên wire**, dùng driver có khả năng kiểm soát byte gửi nếu cần.

### 7.1. Negative case không bị nhiễu bởi replay

Ở ví dụ trên, chữ ký cho request bị thay được tạo **trước** khi mutate URL, dùng nonce mới. Không gửi một request hợp lệ có **cùng nonce** trước đó. Trong policy lưu nonce sau khi HMAC khớp, invalid signature sẽ không làm phát sinh nonce claim. Nếu hệ thống cố tình kiểm tra thứ tự khác, cần làm rõ kỳ vọng và reason nội bộ tương ứng; mục tiêu vẫn là chứng minh **MAC không khớp vì query** chứ không phải chỉ vì replay.

### 7.2. Assert side effect, không chỉ HTTP status

Ví dụ test dùng repository spy hoặc database test:

~~~java
// Pseudocode: nằm trong integration test có paymentRepository và publisher.
long before = paymentRepository.count();

HttpResponse<String> response = send(
        "account=A123&mode=preview",
        "account=B999&mode=execute",
        UUID.randomUUID().toString());

assertEquals(401, response.statusCode());
assertEquals(before, paymentRepository.count());
verifyNoInteractions(paymentEventPublisher);
~~~

Nếu handler vẫn ghi thanh toán rồi mới trả 401, hệ thống đã thất bại ở ranh giới xác thực. Với request có side effect ngoài database, kiểm tra cả external calls, message publishing và audit nghiệp vụ. Đừng để test dương tạo dữ liệu mà test âm đếm nhầm; hãy dùng fixture/namespace riêng hoặc ghi nhận trạng thái sau baseline.

## 8. Kiểm thử query canonicalization đúng hợp đồng

### 8.1. Raw query mode: mọi thay đổi byte đều đáng nghi

Trong mode này, các biến thể:

~~~text
mode=preview
mode=Preview
mode=preview&
mode=preview%20
mode=preview%2520
mode=preview&debug=true
~~~

đều khác raw query đã ký. Nếu hợp đồng thực sự ký raw query nguyên vẹn, test negative phải cho thấy **giữ signature cũ + gửi raw query khác → authentication failure**.

Lưu ý ký chuỗi query ở tầng **byte/canonical** được thỏa thuận; một API có thể coi một số URL normalization là không hợp lệ ngay từ đầu với **400**, thay vì để đến bước MAC. Test phải xác nhận request không vào nghiệp vụ và kiểm tra đúng phase/status của hợp đồng.

### 8.2. Canonical query mode: phân biệt đổi biểu diễn và đổi nghĩa

Nếu hợp đồng quy định sort key, normalize percent-encoding và giữ mọi giá trị:

~~~text
Raw A:      mode=preview&account=A123
Raw B:      account=A123&mode=preview
Canonical:  account=A123&mode=preview
~~~

Phép thử hợp lệ có thể kỳ vọng **cùng chữ ký**, nhưng chỉ khi parser và handler cũng hiểu hai request như nhau. Ngược lại:

~~~text
Raw C:      account=B999&mode=preview
Canonical:  account=B999&mode=preview
~~~

phải không khớp chữ ký A.

Định nghĩa canonical query phải trả lời đầy đủ:

1. Tên và giá trị được percent-decode **mấy lần**, rồi encode lại theo charset nào?
2. Có normalize Unicode, lowercase key hoặc biến `+` thành dấu cách không?
3. Dấu `;` có được coi là separator hay ký tự trong value?
4. Thứ tự so sánh dựa trên Unicode code point hay byte UTF-8?
5. Tham số **trùng key** được giữ toàn bộ, sort theo value, giữ thứ tự hay từ chối?
6. Query rỗng và vắng mặt là cùng canonical string hay không?
7. Tham số không biết trước có bị từ chối, được ký toàn bộ hay được loại theo allowlist?

Không được canonicalize bằng một `Map<String, String>` làm mất key trùng, trong khi controller lại dùng `MultiValueMap` hoặc đọc query đầu/cuối khác nhau. Điều này có thể cho phép một chữ ký xác thực **một nghĩa** nhưng handler thực thi **nghĩa khác**.

### 8.3. Property-based và mutation testing

Với tập tham số hợp lệ được tạo ngẫu nhiên, có thể xây các thuộc tính:

~~~text
Nếu query có thay đổi ngữ nghĩa thuộc tập field được ký:
    verify(originalSignature, mutatedRequest) == false

Nếu canonicalQuery(A) == canonicalQuery(B) theo hợp đồng:
    chữ ký của A có thể hợp lệ cho B
    VÀ server handler phải diễn giải A, B tương đương.

Nếu một query bị từ chối do ambiguous encoding/duplicates:
    không có side effect.
~~~

Property-based test nên sinh trường hợp percent encoding, Unicode NFC/NFD, tham số rỗng, duplicate keys và các separator đặc biệt. Mutation testing có thể thử **xóa trường query khỏi canonicalizer** hoặc dùng query rỗng cố định: bộ test tốt phải thất bại khi verifier không còn ràng buộc query.

## 9. Gateway/proxy có thể phá Changed query test như thế nào?

Một đường đi phổ biến:

~~~mermaid
flowchart LR
    A[Client: ký public raw query A] --> G[Gateway / ingress]
    G -->|Path rewrite, query preserved or transformed| S[Service]
    S --> V{Xác minh canonical public target}
    V -- Query không khớp --> R[401; dừng]
    V -- Hợp lệ --> N[Nonce claim + authz]
    N --> H[Handler]
~~~

Những thay đổi cần test qua **proxy chạy thật**:

| Hành vi proxy | Điều cần xác minh |
|---|---|
| Rewrite path nhưng giữ raw query | Service dùng public target đúng contract; chữ ký baseline hợp lệ |
| Reorder query tự động | Raw mode phải từ chối signature cũ; canonical mode xử lý theo hợp đồng |
| Thêm tham số như `tracking=true` | Nếu ký toàn bộ query, signature cũ không thể còn hợp lệ |
| Bỏ query hoặc cắt ở ký tự đặc biệt | Request bị từ chối; không thực hiện nghiệp vụ khác |
| Decode `%2F`/`%26` trước khi forward | Không tạo khác biệt diễn giải giữa verifier và handler |
| Dùng `X-Original-URI`/`Forwarded` không đáng tin | Client giả header không thể điều khiển canonical request |
| HTTP/2 bên ngoài, HTTP/1.1 bên trong | Query semantics được bảo toàn theo hợp đồng |
| WAF/proxy normalize URL | Có policy rõ; test vector qua WAF/gateway đạt kết quả mong đợi |

**Không sửa lỗi 401 bằng cách bỏ query khỏi chữ ký.** Nếu proxy bắt buộc phải thay đổi query, có thể thiết kế lại hợp đồng ký một **logical target**, quy định canonical query thống nhất, hoặc xác minh HMAC tại gateway rồi gửi assertion được bảo vệ tới service. Mọi phương án đều yêu cầu ràng buộc đúng request gốc với thao tác thực thi; không tin bất kỳ header nội bộ nào nếu client có thể giả mạo.

### 9.1. Kiểm thử header spoofing liên quan đến query

Client cố tình gửi:

~~~http
POST /public/v1/payments?account=B999 HTTP/1.1
X-Internal-Original-Target: /public/v1/payments?account=A123
X-Internal-Route-Id: payments.create.v1
X-Signature: <signature-for-account-A123>
~~~

Kỳ vọng: ingress strip/overwrite metadata nội bộ do client tự khai, service chỉ chấp nhận metadata phát hành qua kênh/hop đã được xác thực, và **không** dùng chữ ký cho account A123 để cho request business B999 qua. Ngoài HMAC, kiểm tra mapping public target ↔ route handler để tránh chữ ký của một endpoint được dùng trên endpoint khác.

## 10. HTTP status, authentication và authorization

| Tình huống | Kỳ vọng theo API ví dụ |
|---|---|
| Query được ký bị thay nhưng giữ signature cũ | **401 Unauthorized**, không chạy handler |
| Query/HTTP request target malformed trước khi tạo canonical | **400 Bad Request** có thể phù hợp theo parser/policy |
| Signature đúng cho query mới nhưng client không có quyền resource | **403 Forbidden** |
| Thiếu header chữ ký bắt buộc | **401** |
| Key ID unknown/revoked hoặc MAC sai | **401** chung, tránh tiết lộ trạng thái key |
| Timestamp hết hạn hoặc nonce replay | **401**; không phải kết luận query mismatch |
| Key/nonce store lỗi, không thể xác minh | **503 Service Unavailable** theo policy; fail closed |
| Query quá dài/truy vấn vượt giới hạn được cấu hình | **400/414/431** tùy tầng/protocol/policy; phải chặn trước nghiệp vụ |

Khi trả 401, HTTP yêu cầu challenge `WWW-Authenticate` phù hợp; nếu API dùng scheme `HMAC` tự định nghĩa, response có thể dùng `WWW-Authenticate: HMAC realm="signed-api"` theo hợp đồng riêng. Không trả expected canonical string, MAC kỳ vọng, shared secret, trạng thái nonce hoặc key tồn tại hay không.

**Đừng gán 403 cho MAC sai chỉ vì query liên quan đến tenant.** Nếu HMAC không đúng, request chưa được xác thực. Nếu HMAC đúng nhưng client không có quyền với tenant/resource được ký, đó mới là tình huống authorization.

Test nên quan sát error reason nội bộ được phân nhóm an toàn, như `CREDENTIAL_INVALID`, nhưng không mặc định tuyên bố “query changed” từ mọi 401: method, body, header, timestamp hoặc key cũng có thể gây mismatch.

## 11. Replay, key rotation và độ cô lập của test

**Replay:** cùng method/path/query/body/timestamp/nonce/signature gửi lại thường vẫn có MAC hợp lệ; chống replay yêu cầu nonce được claim nguyên tử trên shared store. Changed query test không thay thế replay test. Nếu tampered request có cùng nonce với request đã thành công, từ chối có thể do replay; tách fixture để kiểm chứng đúng nguyên nhân.

**Timestamp:** dùng `Clock.fixed` ở verifier hoặc thời gian đồng bộ giữa test client và service; thử timestamp quá cũ hay tương lai ở **bài kiểm thử freshness riêng**. Không để một timestamp hardcoded từ trước làm tất cả các ca query test vô tình trả 401.

**Key rotation:** seed đúng key active cho happy path; kiểm tra key cũ/new theo overlap và revoke ở test chuyên trách. Key ID là lookup hint, không phải credential tự xác thực. Không đổi key/secret giữa baseline và tampering case nếu mục tiêu chỉ là query.

**Multi-tenant:** một client ký query trỏ tới tenant khác bằng secret **hợp lệ** vẫn phải qua authorization. Changed query test với chữ ký cũ kiểm tra tính toàn vẹn; test HMAC ký lại hợp lệ cho query mới rồi nhận 403 sẽ kiểm tra tenant/resource policy riêng.

**Retries:** nếu client tự sửa query khi retry, phải ký lại toàn bộ request theo hợp đồng, thường dùng timestamp/nonce mới. Với API ghi dữ liệu, dùng **idempotency key** tách biệt; nonce HMAC không bảo đảm idempotency của nghiệp vụ.

## 12. Test matrix khuyến nghị cho CI

| Case | Cách tạo | Điều kiện chấp nhận |
|---|---|---|
| Baseline đúng | Sign Q, gửi Q, nonce mới | Thành công theo API và authz |
| Thay value | Sign Q, gửi Q' khác value | 401, không side effect |
| Thêm tham số | Sign Q, gửi Q + tham số | 401 trong raw mode |
| Xóa tham số | Sign Q, gửi Q bỏ key | 401 trong raw mode |
| Đảo thứ tự | Sign `a=1&b=2`, gửi `b=2&a=1` | Raw: 401; canonical: theo contract |
| Query key trùng | Sign một value, gửi hai value | Không bị lấy sai giá trị do parameter pollution |
| Query rỗng/vắng mặt | Sign theo biểu diễn được quy định | Kết quả nhất quán trên mọi HTTP stack |
| Percent encoding | Sign `%20`, gửi `+` hoặc thay `%2F` | Raw: khác phải từ chối; canonical: theo contract |
| Unicode normalization | Sign NFC, gửi NFD | Hành vi có tài liệu và test vector |
| Delimiter encoding | `%26`/`%3D` ↔ `&`/`=` | Không xác minh nghĩa khác |
| Query dài bất thường | Gửi query vượt giới hạn | Không tiêu tốn vô hạn bộ nhớ/CPU, không side effect |
| Fragment URL | Thêm `#fragment` phía client | Không tính fragment như field gửi qua HTTP |
| Proxy path rewrite | Gửi qua gateway, path nội bộ khác | Signed public target khớp route |
| Proxy query rewrite | Gateway tự thêm/bớt tham số | Không silent bypass; xử lý theo hợp đồng |
| Forged forwarded header | Client tự gửi original-target giả | Ingress/service từ chối tin metadata giả |
| Sign đúng query mới, thiếu quyền | Re-sign Q', principal thiếu quyền | 403, không side effect |
| Tái gửi cùng nonce | Gửi lại signed request nguyên trạng | Replay bị chặn trên mọi replica |
| Timestamp sai | Tạo ts ngoài cửa sổ | 401, không gán nhầm query mismatch |
| Key revoke | Ký bằng key đã revoke | 401, không gán nhầm query mismatch |
| Key/nonce store lỗi | Inject timeout/down | Fail closed, thường 503 |

**Trong CI:** tối thiểu cần unit canonicalizer, test vector HMAC độc lập, integration test qua Spring Security và một phép thử **qua gateway/proxy thật** có route rewrite. Khi thay đổi SDK, router, WAF, version canonical hoặc bộ parse query, phải chạy lại nhóm test encoding/duplicate parameters.

## 13. Chẩn đoán khi Changed query test không như mong đợi

### 13.1. Test âm bất ngờ trả 2xx

Kiểm tra theo thứ tự:

1. Signer đã tính signature **trước khi** query bị đổi chưa? Có helper nào tự ký lại URL thực tế không?
2. Verifier có thật sự đưa query vào canonical string hay đang dùng chuỗi rỗng/hằng số?
3. Một trong các lớp có vô tình bỏ qua HMAC filter hoặc match nhầm route `permitAll` không?
4. Verifier và handler có lấy query từ **cùng representation đáng tin** không? Có duplicate parameter hoặc decoding không nhất quán?
5. Gateway có đưa `X-Original-URI` do client giả mạo trở lại verifier không?
6. MAC check có kết thúc chain trước khi controller chạy hay response 2xx đã được ghi từ handler trước đó?

Nếu test đổi sang một query **tương đương** theo canonical contract (ví dụ chỉ đảo thứ tự khi hợp đồng sort), 2xx có thể **đúng**. Hãy xác nhận kỳ vọng trước khi sửa code.

### 13.2. Test dương bất ngờ trả 401

Nguyên nhân có thể là:

- Timestamp đã hết window, nonce bị dùng lại, key ID sai trạng thái hoặc secret khác giữa test và service.
- Client HTTP library re-encode query sau khi signer đã ký raw bytes.
- Gateway rewrite/normalize path/query; service tạo canonical trên internal path hay query đã đổi.
- Header ký bị proxy thêm/bớt, body bytes thay vì hash raw body bị serialize lại.
- Verifier dùng encoding, separator, version HMAC hoặc cách xử lý query rỗng khác signer.

Trong môi trường test cô lập, so sánh độ dài/digest của **canonical bytes** theo các thành phần đã được kiểm soát, không log shared secret, expected MAC, raw body tài chính hay query nhạy cảm trong production. Trace ID an toàn, route template và reason tổng quát giúp liên kết sự kiện xuyên gateway.

### 13.3. Test âm trả 401 nhưng vẫn không chứng minh bảo vệ query

Một response 401 có thể vì secret sai, key revoked hoặc nonce replay. Hãy tạo **fixture đủ điều kiện để qua tất cả phép kiểm tra khác** và dùng spy tại verifier hoặc unit-level contract test. Khi có quyền truy cập event nội bộ, xác nhận MAC verification thất bại trên query mới; phía HTTP vẫn chỉ trả lỗi chung, không công khai thông tin giúp dò chữ ký.

## 14. Checklist thực hành

- [ ] Xác định raw query hay canonical query, cách xử lý query rỗng, encoding, key lặp, Unicode và phiên bản hợp đồng.
- [ ] Tạo một golden vector được tính độc lập; xác nhận signer và verifier không cùng bỏ query.
- [ ] Test dương ký Q gửi Q, test âm **ký Q nhưng gửi Q'** mà không ký lại.
- [ ] Từng negative case có nonce mới, key active và timestamp hợp lệ để tránh nhiễu do replay/freshness.
- [ ] Test HTTP đi qua đúng HMAC filter và, nếu có, gateway thật với public path/query.
- [ ] Query đã ký ràng buộc với query được handler/authorization diễn giải; không có parameter pollution.
- [ ] Client không thể giả `X-Original-URI` hay original query từ gateway để vượt verification.
- [ ] 401 cho request chưa xác thực do MAC sai; 403 chỉ khi đã xác thực nhưng thiếu quyền.
- [ ] Mọi request tampered đều không ghi database, phát event hoặc gọi downstream có side effect.
- [ ] Nonce được claim nguyên tử **sau khi chữ ký hợp lệ**; replay test được tách khỏi changed-query test.
- [ ] Key rotation/revoke, timestamp/window và lỗi store có test riêng; không làm nhiễu phép thử query.
- [ ] Bộ test gồm thay value, add/remove, reorder, duplicates, percent encoding, Unicode và empty query.
- [ ] Log/test artifact không chứa shared secret, full signature, raw query nhạy cảm hoặc body chứa PII.
- [ ] Regression chạy lại khi nâng version gateway/proxy, HTTP client, router hoặc canonicalization library.

## 15. Kết luận

**Changed query test** không chỉ là bài kiểm tra “đổi một tham số thì trả 401”. Nó chứng minh rằng **query ảnh hưởng đến request thực thi được ràng buộc đúng với chữ ký HMAC**, trên cùng biểu diễn mà client và server đã ký theo hợp đồng. Test phải giữ signature cũ khi mutate query, đồng thời loại bỏ yếu tố gây nhiễu như nonce replay, timestamp hết hạn hoặc key sai.

Một triển khai đạt yêu cầu vừa từ chối request có query thay đổi ngoài hợp đồng, vừa chấp nhận những biểu diễn **thực sự tương đương nếu canonicalization cho phép**, không bị đánh lừa bởi duplicate parameters hay forwarded header giả qua proxy. Sau khi HMAC hợp lệ, authorization vẫn phải kiểm tra quyền với tài nguyên được yêu cầu; toàn bộ nhánh lỗi phải dừng trước side effect. Đó là ranh giới quan trọng nhất mà bộ kiểm thử cần bảo vệ.
