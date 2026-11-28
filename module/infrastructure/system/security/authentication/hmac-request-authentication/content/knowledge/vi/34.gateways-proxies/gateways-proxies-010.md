# Kiểm thử qua proxy: xác minh HMAC xuyên gateway đến service

## 1. Tại sao phải kiểm thử qua proxy?

Trong module **SECURITY_AUTHENTICATION_HMAC_REQUEST_AUTHENTICATION**, client ký HTTP request bằng HMAC với **shared secret** và một **canonical request** theo hợp đồng: phương thức, URI, header được chọn và/hoặc body. Server phải kiểm tra chữ ký, timestamp/nonce chống replay, quản lý key rotation và phân biệt **xác thực** với **phân quyền**.

Ở chương **Gateway và proxy**, bài **Kiểm thử qua proxy** giải quyết một lỗi tích hợp thường chỉ xuất hiện sau khi triển khai: chữ ký HMAC chạy đúng khi client gửi thẳng vào service, nhưng bị từ chối hoặc bị diễn giải sai khi đi qua gateway, reverse proxy, ingress hay service mesh.

Nguyên nhân thường nằm ở cách proxy xử lý HTTP request: rewrite URL, thay `Host`/scheme, chuẩn hóa query hoặc path, bổ sung header, giải nén body, chuyển HTTP/2 sang HTTP/1.1, hoặc đưa request đến một replica khác. Test chỉ gọi controller hoặc mock verifier sẽ không quan sát được những thay đổi đó.

Mục tiêu sau bài học:

1. Thiết lập phép thử end-to-end **client → proxy/gateway → service → nghiệp vụ**, với cùng hợp đồng ký dùng trong production.
2. Đo được request mà client đã ký và request thực sự đến service, xác định thành phần nào được phép thay đổi.
3. Chứng minh **không thể qua xác thực** khi chữ ký sai, timestamp ngoài cửa sổ, nonce bị replay hoặc metadata từ proxy bị giả mạo.
4. Kiểm thử key rotation, kho nonce dùng chung giữa nhiều replica và quyền truy cập sau khi xác thực.
5. Xây bộ test có thể tái chạy trong CI/CD, có kết quả rõ ràng cả về HTTP response lẫn side effect nghiệp vụ.

> Hợp đồng ký dưới đây là **ví dụ để kiểm thử**, không phải định dạng HMAC HTTP chuẩn cho mọi API. Tập trường ký, encoding, canonicalization, skew, nonce TTL, chính sách key và mã lỗi phải khớp với hợp đồng thực tế.

## 2. Kiến trúc và ranh giới tin cậy cần quan sát

~~~mermaid
flowchart LR
    A[Test client ký HMAC] -->|HTTPS; public URL| G[Ingress / API gateway]
    G -->|route rewrite + forwarded metadata| P[Reverse proxy / mesh]
    P -->|kênh tin cậy| S[Service xác minh HMAC]
    S --> R[(Key store + nonce store)]
    S -->|principal đã xác thực| Z[Authorization]
    Z -->|đủ quyền| B[Handler + side effect]
    S -->|401 / 413 / 503| X[Response từ chối]
    Z -->|403| X
~~~

Một môi trường test phải có **ít nhất một request thật đi qua proxy**. Có thể bắt đầu bằng một reverse proxy trong Testcontainers/Docker và backend chạy trên cổng nội bộ; sau đó mở rộng lên ingress/gateway/service mesh thật trong staging.

Trong quá trình kiểm thử, phân biệt hai góc nhìn:

| Điểm quan sát | Những gì cần ghi nhận để so sánh |
|---|---|
| Client, **trước khi ký** | Method, public raw path/query, tập header được ký, byte body, key ID, timestamp, nonce, phiên bản HMAC |
| Gateway, **trước và sau rewrite** | Public request target nhận được, mapping sang route nội bộ, có transform body/header không, identity của hop tiếp theo |
| Service, **trước verify** | Actual internal route, metadata public target được xác thực, byte body thực tế, tập header hợp lệ |
| Service, **sau verify** | Authentication outcome, client/tenant/authority được xác minh, kết quả nonce claim, nguyên nhân lỗi đã phân nhóm |
| Backend nghiệp vụ | Handler có được gọi không, có phát sinh bản ghi/event/lệnh trả tiền không, có bị gọi nhiều lần không |

Không log shared secret, chữ ký đầy đủ, dữ liệu thanh toán hay canonical string có bí mật. Để so sánh byte body, test có thể dùng SHA-256 của fixture **không nhạy cảm** cùng request ID; production nên giảm tối đa dữ liệu chẩn đoán và quản lý quyền đọc log.

### 2.1. Các invariant phải đúng

1. **Bất biến nội dung ký:** byte/canonical fields dùng tại service để xác minh phải đại diện cho cùng request mà client đã ký, theo hợp đồng đã công bố.
2. **Bất biến route:** public route đã ký phải được ánh xạ đúng sang internal route thực sự chạy handler; không dùng chữ ký của thao tác A để gọi thao tác B.
3. **Bất biến nguồn metadata:** nếu service dùng original target do gateway chuyển tiếp, dữ liệu đó chỉ được tin sau khi xác định hop phát hành và kiểm soát khả năng giả mạo từ client.
4. **Bất biến replay:** trong toàn bộ cluster, cùng một nonce hợp lệ cho một phạm vi client/key chỉ được claim theo chính sách một lần trong cửa sổ.
5. **Bất biến side effect:** request bị từ chối ở bất kỳ bước bảo mật nào không được ghi dữ liệu nghiệp vụ, phát sự kiện hoặc gọi phụ thuộc có tác dụng.

Chỉ cần một invariant sai, test HTTP trả 200 ở “happy path” cũng chưa chứng minh integration an toàn.

## 3. Chuẩn bị hợp đồng ký và test vector dùng chung

Giả sử client gửi request:

~~~http
POST /public/v1/payments?source=partner&mode=fast HTTP/1.1
Host: api.example.test
Content-Type: application/json
X-Key-Id: merchant-a-key-v2
X-Timestamp: 2026-11-28T03:20:00Z
X-Nonce: b30f3ed5-45f2-4626-8370-d35e079472ae
X-Signature: <base64-HMAC-SHA256>

{"amount":125000,"currency":"VND"}
~~~

Giả định hợp đồng `HMAC-V1` ký **public raw path**, **raw query**, method, key ID, timestamp, nonce và SHA-256 của **nguyên byte body**. Canonical string mẫu:

~~~text
HMAC-V1
POST
/public/v1/payments
source=partner&mode=fast
merchant-a-key-v2
2026-11-28T03:20:00Z
b30f3ed5-45f2-4626-8370-d35e079472ae
<lowercase-hex-sha256-of-original-body-bytes>
~~~

Quy trình:

~~~text
bodyHash  = lowercaseHex(SHA256(bodyBytes))
canonical = joinWithLF(
    "HMAC-V1", method, publicRawPath, publicRawQuery,
    keyId, timestamp, nonce, bodyHash
)
signature = Base64(HMAC-SHA256(secretBytes, UTF8(canonical)))
~~~

Trong fixture test, hãy cố định thứ tự trường, encoding UTF-8, luật percent-encoding, cách xử lý query lặp, ký tự điều khiển và độ dài trường. Nếu hợp đồng có thêm `Content-Type`, `Host` hay header khác, **bổ sung vào cả client signer và verifier**; test phải kiểm tra việc proxy bảo toàn đúng biểu diễn đã ký. Với production, nên version hóa định dạng canonical để có thể tiến hóa mà không diễn giải lẫn nhau.

**Hai loại vector cần lưu trong bộ test:** vector dương gồm key/secret giả và expected signature đã tính độc lập; vector âm thay từng thành phần được ký mà **không thay signature**. Test độc lập tránh việc cùng một bug nằm trong cả client signer và server verifier khiến test vẫn xanh.

### 3.1. Giả định khi URI bị rewrite

Ví dụ gateway thực hiện:

~~~text
CLIENT:
  POST https://api.example.test/public/v1/payments?source=partner&mode=fast

GATEWAY:
  public target = /public/v1/payments?source=partner&mode=fast
  route id      = payments.create.v1
  rewrite path  = /payments

SERVICE:
  actual route  = POST /payments
  signed target = /public/v1/payments?source=partner&mode=fast
~~~

Service cần sử dụng **signed public target đã được bảo vệ** khi kiểm tra HMAC, rồi ràng buộc nó với `POST /payments` theo mapping tin cậy. Nếu service tự ký lại `/payments`, request hợp lệ bị từ chối. Nếu service tin một `X-Original-URI` mà Internet client có thể tự đặt, request có thể bị diễn giải lệch route.

## 4. Môi trường kiểm thử sát đường đi thật

Một test harness có thể gồm:

- **Test client**: Java `HttpClient`, RestAssured hoặc thư viện khác có khả năng kiểm soát exact request target/header/body.
- **Reverse proxy/gateway**: Nginx, Envoy hoặc chính API gateway đang triển khai; cần chạy với cấu hình rewrite và header forwarding gần production.
- **Service thật**: ứng dụng Spring MVC hoặc Spring WebFlux có filter HMAC và authorization như sẽ triển khai; expose backend chỉ trên private test network.
- **Key store**: key giả theo client/tenant, trạng thái active/rotating/revoked và hiệu lực.
- **Nonce store dùng chung**: Redis hoặc backend atomic tương ứng; tối thiểu hai service replica để kiểm thử replay đồng thời.
- **Clock điều khiển được**: truyền `Clock` vào verifier, tạo timestamp theo test hoặc đóng băng thời gian test; không dùng `sleep` để chờ hết hạn nonce trong unit test.
- **Spy nghiệp vụ**: đếm số bản ghi/command/event và đối chiếu idempotency key, không chỉ assert HTTP status.

Ví dụ cấu hình Nginx sau **chỉ minh họa một route test**:

~~~nginx
# Đây là trích đoạn của server test, chưa bao gồm TLS/mTLS/network policy.
location = /public/v1/payments {
    # Original request-target, trước khi rewrite.
    proxy_set_header X-Internal-Public-Target $request_uri;
    proxy_set_header X-Internal-Route-Id "payments.create.v1";

    # Đổi route nhìn thấy ở service thành /payments.
    rewrite ^ /payments break;
    proxy_pass http://payment-service:8080;
}
~~~

`$request_uri` trong cấu hình minh họa dùng để mang public request target trước rewrite; kiểm thử phải xác nhận giá trị thực tế được forward đúng nguyên tắc của hợp đồng. Mỗi gateway có semantics rewrite, normalize và forward khác nhau.

**Quan trọng:** chỉ dùng `X-Internal-Public-Target` khi ingress đã xóa/ghi đè tất cả giá trị do client cung cấp, các hop sau đó được xác thực/bảo vệ và service không thể bị gọi tắt từ mạng thiếu tin cậy. `proxy_set_header` trên một route không thay thế việc đánh giá toàn bộ hop, duplicate headers, network policy và mTLS. Cần test cả khả năng gửi trực tiếp vào backend và giả mạo các header nội bộ. Metadata có thể cần một chữ ký/assertion của gateway riêng nếu đường nội bộ không hoàn toàn được tin cậy.

### 4.1. Ba mức kiểm thử

| Mức | Mục đích | Giới hạn |
|---|---|---|
| Unit test canonicalizer và HMAC verifier | Xác định từng byte ký, lỗi parser, so sánh signature, clock và nonce | Không phản ánh proxy thực tế |
| Integration test qua proxy chạy trong container | Bắt rewrite, forwarded headers, body transform, error handling, replica routing | Chỉ đại diện cho cấu hình proxy trong test |
| End-to-end staging gần production | Kiểm tra TLS termination, WAF/ingress, HTTP/2, service mesh, multi-hop và network policies | Cần kiểm soát dữ liệu, secret giả và side effect test |

CI nên chạy test mức 1 và 2 trên mỗi thay đổi quan trọng; mức 3 được thực hiện khi cấu hình gateway, mesh, hợp đồng ký hoặc đường đi traffic thay đổi, và trước khi phát hành.

## 5. Ma trận kiểm thử tối thiểu

Các mã HTTP dưới đây giả định API dùng **401** cho lỗi xác thực HMAC, **403** cho principal đã xác thực nhưng thiếu quyền, **413** cho payload vượt giới hạn và **503** khi không thể xác minh vì kho key/nonce lỗi. Mã **400** có thể dành cho cú pháp HTTP malformed theo hợp đồng; không cần cố biến mọi lỗi thành 401.

| Nhóm | Tình huống gửi qua proxy | Kết quả cần quan sát |
|---|---|---|
| Happy path | Ký public path/query đúng, gateway rewrite path sang internal service | Thành công theo API, principal và mapping đúng; nghiệp vụ đúng một lần |
| Path tampering | Sửa path ký nhưng giữ chữ ký | 401, không có side effect |
| Path normalization | Thử `//`, `.`, `..`, `%2F`, trailing slash, khác chữ hoa | Chỉ chấp nhận khi contract và router thống nhất; không route smuggling |
| Query tampering | Đổi một giá trị query, đảo thứ tự key khi ký raw query | 401 nếu khác signed raw query |
| Duplicate query | `role=user&role=admin`, query rỗng/không rỗng và nhiều khóa trùng | Parser, canonicalizer và handler dùng cùng một ngữ nghĩa; không parameter pollution |
| Host/scheme | Proxy đổi public HTTPS/Host sang HTTP/internal Host | Chữ ký vẫn đúng nếu contract không ký các trường đó; nếu ký thì dùng nguồn public authority đáng tin cậy |
| HTTP version | HTTP/2 bên ngoài, HTTP/1.1 bên trong | Signature hợp lệ theo canonical semantics đã công bố |
| Header added/removed | Gateway thêm `Via`, `X-Forwarded-*`, request ID, bỏ hop-by-hop headers | Các header ngoài tập signed headers không ảnh hưởng signature; header được ký không bị thay |
| Duplicate signed headers | Gửi hai `X-Key-Id`/`X-Signature`, khác capitalization | Từ chối theo contract, không lấy giá trị tùy hop |
| Header spoofing | Client gửi `X-Internal-Public-Target`/route ID giả | Ingress xóa/ghi đè; service không tin giá trị client |
| Direct bypass | Gọi cổng backend với forged forwarded metadata | Bị network/mTLS chặn hoặc từ chối trước nghiệp vụ |
| Body byte tampering | Đổi whitespace, thứ tự field JSON, ký tự newline hoặc 1 byte body sau khi ký | 401 nếu ký raw body hash |
| Compression | Gzip/decompress tại gateway, chuyển `Content-Encoding` | Đúng theo contract ký compressed hoặc decompressed bytes; sai biểu diễn phải từ chối |
| Streaming/chunked | Chunked upload và thay HTTP framing qua proxy | Không lệ thuộc kích thước chunk nếu contract ký entity body bytes |
| Request quá lớn | Body vượt giới hạn service, dù gateway cho qua | 413; memory không tăng vô hạn, handler không chạy |
| Credential sai | Key ID lạ, chữ ký Base64 sai, secret sai, key bị revoke | 401; response không lộ nội bộ |
| Timestamp | Timestamp cũ, quá tương lai, sai format, lệch clock | 401 ngoài cửa sổ; đúng tại biên được định nghĩa |
| Replay | Cùng chữ ký/nonce gửi lại đến cùng hoặc khác replica | Tối đa một request qua nonce claim; replay 401 |
| Store failure | Key store/nonce store timeout, mất kết nối | Fail closed, 503 (theo API), không chạy nghiệp vụ |
| Rotation | Key mới active, key cũ còn overlap, key đã revoke | Chỉ key đang được phép mới hợp lệ |
| Authorization | Signature đúng nhưng principal thiếu `payments:write`/sai tenant | 403; không có side effect |
| Retry | Gửi lại thao tác ghi sau lỗi mạng với nonce mới và idempotency key cũ | HMAC hợp lệ nhưng không nhân đôi hiệu ứng nghiệp vụ |

Với từng hàng, lưu lại các bằng chứng: HTTP status/header/body, trace ID, trạng thái nonce và **assertion rằng handler không được gọi** ở mọi nhánh từ chối. Không “sửa” hệ thống bằng cách bỏ kiểm tra path/body/nonce để test xanh.

## 6. Ví dụ Java: tạo signed request để gửi qua proxy

Ví dụ dùng Java 17+, ký đúng hợp đồng `HMAC-V1` ở mục 3 bằng HMAC-SHA256. Để test này chạy được, fixture phải dùng cùng public raw path/query; signature chỉ được thay bằng chữ ký mới khi test muốn mô phỏng client **cố ý ký lại**.

~~~java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.util.Base64;
import java.util.HexFormat;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public final class HmacV1TestSigner {
    private HmacV1TestSigner() {}

    public static String sign(
            byte[] secret,
            String method, String publicRawPath, String publicRawQuery,
            String keyId, String timestamp, String nonce, byte[] body)
            throws GeneralSecurityException {

        String bodyHash = HexFormat.of().formatHex(
                MessageDigest.getInstance("SHA-256").digest(body));
        String canonical = String.join("\n",
                "HMAC-V1", method, publicRawPath, publicRawQuery,
                keyId, timestamp, nonce, bodyHash);

        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(secret, "HmacSHA256"));
        byte[] signature = mac.doFinal(
                canonical.getBytes(StandardCharsets.UTF_8));
        return Base64.getEncoder().encodeToString(signature);
    }
}
~~~

Một đoạn JUnit 5 minh họa **gửi request vào cổng public của proxy**, không gọi trực tiếp cổng backend:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Clock;
import java.time.Instant;
import java.util.UUID;
import org.junit.jupiter.api.Test;

class HmacThroughProxyIT {
    // Trong suite thực, các giá trị được cấp từ test harness/containers.
    private final URI proxyBaseUrl = URI.create("http://127.0.0.1:18080");
    private final HttpClient client = HttpClient.newHttpClient();
    private final Clock clock = Clock.systemUTC();
    private final String keyId = "merchant-a-key-v2";
    private final byte[] testSecret =
            "test-secret-is-not-for-production".getBytes(StandardCharsets.UTF_8);

    @Test
    void validSignatureSurvivesProxyRewrite() throws Exception {
        String path = "/public/v1/payments";
        String query = "source=partner&mode=fast";
        String timestamp = Instant.now(clock).toString();
        String nonce = UUID.randomUUID().toString();
        byte[] body = "{\"amount\":125000,\"currency\":\"VND\"}"
                .getBytes(StandardCharsets.UTF_8);
        String signature = HmacV1TestSigner.sign(
                testSecret, "POST", path, query, keyId, timestamp, nonce, body);

        HttpRequest request = HttpRequest.newBuilder(
                        proxyBaseUrl.resolve(path + "?" + query))
                .header("Content-Type", "application/json")
                .header("X-Key-Id", keyId)
                .header("X-Timestamp", timestamp)
                .header("X-Nonce", nonce)
                .header("X-Signature", signature)
                .POST(HttpRequest.BodyPublishers.ofByteArray(body))
                .build();

        HttpResponse<String> response =
                client.send(request, HttpResponse.BodyHandlers.ofString());
        assertEquals(201, response.statusCode());
        // Suite thật còn assert 1 bản ghi payment và route/tenant đúng.
    }
}
~~~

Giá trị `201` chỉ đúng nếu endpoint test quy định trả `201 Created`. Trong test suite thật, URL cổng proxy phải lấy từ runtime test (ví dụ Testcontainers mapped port), clock phải được cố định/đồng bộ với verifier, key test phải được seed vào kho key và nonce store sạch giữa các test độc lập.

**Lưu ý về byte trên wire:** `URI.resolve(...)` và các thư viện HTTP có thể tự chuẩn hóa một số ký tự; với các ca `%2F`, duplicate query, `..` hay URL bất thường, hãy dùng client/test driver có thể kiểm soát chính xác request target và quan sát proxy nhận gì. Không kết luận về canonical path chỉ từ chuỗi URL trước khi thư viện HTTP gửi.

### 6.1. Tamper body nhưng giữ chữ ký

Sau khi tạo signature cho body A, gửi body B qua cùng endpoint:

~~~java
byte[] bodyA = "{\"amount\":125000}".getBytes(StandardCharsets.UTF_8);
byte[] bodyB = "{\"amount\":125001}".getBytes(StandardCharsets.UTF_8);

String signature = HmacV1TestSigner.sign(
        testSecret, "POST", "/public/v1/payments", "",
        keyId, timestamp, nonce, bodyA);

HttpRequest tampered = HttpRequest.newBuilder(
                proxyBaseUrl.resolve("/public/v1/payments"))
        .header("Content-Type", "application/json")
        .header("X-Key-Id", keyId)
        .header("X-Timestamp", timestamp)
        .header("X-Nonce", nonce)
        .header("X-Signature", signature)
        .POST(HttpRequest.BodyPublishers.ofByteArray(bodyB))
        .build();

HttpResponse<String> response =
        client.send(tampered, HttpResponse.BodyHandlers.ofString());
assertEquals(401, response.statusCode());
// Đồng thời assert paymentRepository.count() không tăng.
~~~

Đây là đoạn trích dùng lại biến/test fixture ở ví dụ trên. Việc ký body A rồi gửi body B phải trả lỗi khi body hash nằm trong canonical request. Cần làm cùng test khi proxy parse/serialize JSON hoặc áp dụng gzip; nếu body bị biến đổi nhưng signature vẫn được chấp nhận ngoài phạm vi cho phép, đó là lỗi nghiêm trọng.

### 6.2. Replay qua hai replica

Một test tuần tự dễ bỏ sót race condition; dùng **hai request đồng thời** với cùng `keyId`, `nonce`, `timestamp`, `signature` và byte body tới cùng một gateway đang cân bằng tải giữa ít nhất hai service replica:

~~~text
Prepare signed request R with new nonce N.
Send R concurrently via proxy, synchronized by barrier.
Require: exactly one nonce claim succeeds across replicas.
Require: at most one business execution occurs.
Require: all other copies are rejected as replay (401 per contract).
Require: retrying R later inside the validity window is rejected.
~~~

Kho nonce dùng chung cần cung cấp **atomic insert-if-absent + expiry**, chẳng hạn Redis `SET key value NX PX ttl`. Kiểm tra rồi mới ghi bằng hai lệnh tách rời không đáp ứng kiểm thử đồng thời. Tương tự, hai cache RAM riêng trên hai replica không đủ ngăn replay xuyên instance.

TTL phải bao phủ toàn bộ thời gian một request đã nhận có thể còn hợp lệ. Nếu timestamp được chấp nhận trong `now ± W`, một request ký ở tương lai gần `now + W` có thể còn hợp lệ đến `now + 2W`. Đừng đặt TTL `W` một cách máy móc. Khi store lỗi, **không cho request qua**; test mô phỏng timeout/unavailable và yêu cầu service trả lỗi server phù hợp.

## 7. Kiểm thử metadata proxy và đường đi vòng

### 7.1. Header giả mạo từ bên ngoài

Client thử gửi:

~~~http
POST /public/v1/payments HTTP/1.1
X-Internal-Public-Target: /admin/refunds
X-Internal-Route-Id: refunds.create.v1
X-Forwarded-Host: attacker.example
X-Forwarded-Proto: https
~~~

Header này **không được** quyết định canonical target hay route nếu client không thuộc trust domain được phép cấp metadata. Ingress cần strip/overwrite metadata dành riêng cho nội bộ; service cần xác thực hop và kiểm tra mapping giữa public route, internal route và handler thực tế.

Test bao gồm các biến thể:

- Trùng header với khác capitalization (`X-Internal-Public-Target` và `x-internal-public-target`).
- Header nhiều giá trị hoặc các hop nối/chồng `Forwarded` và `X-Forwarded-*`.
- Gọi thẳng backend bằng IP/port nội bộ có thể truy cập được từ workload không được tin.
- Mỗi proxy hop định tuyến, thêm/bỏ header theo cấu hình riêng và chuyển tiếp HTTP/2 ↔ HTTP/1.1.
- Gateway hợp lệ nhưng gửi route ID không khớp method/path đang gọi.

Nếu truy cập backend trực tiếp có thể vượt kiểm tra identity gateway hoặc đưa client-supplied public target qua verification, test phải thất bại. **IP nội bộ không tự nó xác nhận nguồn gốc đáng tin cậy**; ưu tiên network policy, mTLS với workload identity và kiểm soát metadata.

### 7.2. Path normalization và request smuggling theo ngữ nghĩa

Không chỉ thử URL “đúng”. Các biểu diễn sau có thể được proxy và backend diễn giải khác nhau:

~~~text
/public/v1/payments
/public/v1//payments
/public/v1/./payments
/public/v1/a/../payments
/public/v1/%70ayments
/public/v1%2Fpayments
~~~

Test phải xác định **trên wire** request target nào đến proxy, representation nào được ký, route nào được chọn và service xác minh field nào. Nếu proxy coi hai path tương đương nhưng service không, cần hợp đồng normalization chung hoặc từ chối biểu diễn nhập nhằng. Đặc biệt tránh tình huống một chuỗi HMAC hợp lệ cho route A lại được proxy hoặc controller thực thi như route B.

Với query, kiểm tra key lặp, query rỗng, dấu `+`/`%20`, ký tự Unicode và encoded delimiters. Không parse query thành map rồi bỏ giá trị trùng trước khi ký nếu handler vẫn dùng giá trị còn lại.

## 8. Kiểm thử timestamp, nonce, key rotation và quyền

**Timestamp:** dùng một `Clock` injected vào verifier để test chính xác các thời điểm `now - W - ε`, `now - W`, `now`, `now + W`, `now + W + ε` theo cách định nghĩa biên trong hợp đồng. Một số bộ kiểm tra dùng `abs(now - ts) <= W`, số khác loại biên; phải công bố trước và có test. Không trông chờ thời gian thực của CI khi assert các ca sát biên.

**Nonce:** kiểm tra nonce thiếu, sai định dạng, rất dài, replay cùng request, replay qua nhiều replica và lưu nonce chỉ sau khi signature hợp lệ. Một request giả chữ ký không được chiếm nonce hợp lệ của client khác. Test scope của nonce theo client/key đã được cấu hình, không để nonce của tenant A chặn tenant B nếu hợp đồng tách riêng.

**Key rotation:** tạo key cũ `K1` và key mới `K2` trong fixture. Khi overlap, cả hai key ID còn hiệu lực được chấp nhận theo policy; khi revoke `K1`, mọi request ký bằng `K1` phải bị từ chối ở **tất cả replica**, kể cả replica có cache. Không thử một danh sách secret không giới hạn cho tới khi khớp.

**Authorization:** tạo một principal có HMAC hợp lệ nhưng thiếu `payments:write` hoặc không sở hữu resource. Kết quả phải là **403** ở lớp authorization và không có side effect. Một principal ký được HMAC không được cấp quyền tự động chỉ vì header tự khai báo `role=admin`/`tenant-id`.

**Retry/idempotency:** nếu một request tạo thanh toán thành công nhưng response mất trên đường mạng, client phải sinh timestamp/nonce/chữ ký mới để retry; dùng idempotency key tách biệt nhằm tránh tạo hai giao dịch. Nonce HMAC là bảo vệ replay ở lớp xác thực, **không thay thế** logic idempotency của nghiệp vụ.

## 9. Chẩn đoán khi test thất bại

Khi request hợp lệ đi qua proxy nhưng server trả 401, hãy so sánh theo thứ tự:

1. **Method và public target:** client đã ký `POST /public/v1/payments?…` hay `POST /payments`? Service lấy public target ở nguồn có xác thực chưa? Gateway map đúng route không?
2. **Raw query:** thứ tự tham số, encoding, key trùng, dấu `?`/query rỗng có giữ nguyên theo contract không?
3. **Headers:** có header ký bị gateway đổi, gộp, đổi whitespace hoặc bỏ không? Có header trùng hoặc một hop thêm `Forwarded` bất ngờ không?
4. **Body:** hash của fixture client có bằng hash byte mà verifier nhận không? Proxy có decompress/re-encode payload không?
5. **Khóa/thuật toán:** key ID có hiệu lực và đúng tenant không? Secret, HMAC algorithm, encoding signature và version có trùng contract không?
6. **Thời gian/replay:** clock skew, timestamp format, nonce store và TTL có đúng policy không? Client có vô tình tái sử dụng nonce từ test trước không?
7. **Phân quyền:** nếu signature hợp lệ mà trả 403, kiểm tra authority/resource ownership thay vì sửa HMAC.

Trong môi trường test cô lập, có thể log **digest và độ dài** các phần canonical cùng ID fixture để đối chiếu. Không bật log canonical string có credential/body/secret trong production. Giữ cùng correlation ID xuyên proxy và service, ghi route ID, nhóm mã lỗi, latency xác minh và tình trạng kho nonce; đừng gửi secret, expected MAC hoặc chi tiết tồn tại key cho client.

### Bảng triệu chứng và nguyên nhân thường gặp

| Triệu chứng | Nghi vấn ưu tiên | Cách xác minh |
|---|---|---|
| Direct service 2xx, qua gateway 401 | Rewrite path/query hoặc body | So sánh signed public target và bytes service thực sự kiểm |
| Chỉ request có dấu `%`/`+` lỗi | Percent-decoding/normalization | Test raw URI với driver kiểm soát wire |
| HTTP/1.1 thành công, HTTP/2 thất bại | Host/pseudo-header, header folding hoặc canonicalizer phụ thuộc wire format | So sánh canonical fields giữa protocol versions |
| Request JSON hợp lệ nhưng HMAC sai | Proxy serialize lại body | So sánh byte digest trước/sau proxy |
| Replay qua replica A bị chặn nhưng replica B được qua | Nonce store cục bộ hoặc claim không atomic | Chạy concurrent test trên 2 replica, đo claim result |
| Khi Redis lỗi vẫn trả 2xx | Có nhánh fallback bỏ kiểm tra nonce | Fault injection, assert side effect bằng 0 |
| 401/403 thay đổi bất thường | Filter order, entry point và access-denied handler | Test principal chưa xác thực vs đã xác thực thiếu quyền |
| Chỉ key vừa revoke vẫn hoạt động | Cache key không được invalidation/TTL quá dài | Test revoke ngay với mọi replica |

## 10. Điều kiện nghiệm thu trong CI và staging

Một bộ test “Kiểm thử qua proxy” được coi là đủ cơ sở nghiệm thu kỹ thuật khi:

- [ ] Có test vector HMAC độc lập, có cả signature đúng và signature sai sau khi sửa từng signed field.
- [ ] Có ít nhất một bài test thực đi qua **proxy chạy thật**, dùng public route rồi rewrite sang route nội bộ.
- [ ] Có bằng chứng bảo toàn hoặc xác thực đáng tin cậy của public target và mapping tới handler thực tế.
- [ ] Header nội bộ do client tự gửi không thể điều khiển verification; backend không bị gọi tắt từ nguồn thiếu tin cậy.
- [ ] Có ca raw path/query khó, duplicate header và khác biệt HTTP/1.1 ↔ HTTP/2 nếu hệ thống hỗ trợ.
- [ ] Body ký không bị đổi âm thầm khi qua gateway; có test compression, chunked và giới hạn dung lượng theo contract.
- [ ] Timestamp, nonce, concurrent replay giữa các replica và lỗi nonce/key store đều được kiểm tra; lỗi store fail closed.
- [ ] Có test rotation/revoke trên toàn cluster, không chấp nhận key đã thu hồi.
- [ ] Có test HMAC hợp lệ nhưng thiếu authority dẫn đến 403; request không có HMAC hợp lệ dẫn đến 401.
- [ ] Mỗi nhánh từ chối đều khẳng định **không có side effect** và response không lộ bí mật.
- [ ] Cấu hình gateway/mesh mang vào test từ cùng nguồn phiên bản hoặc có cơ chế kiểm tra chênh lệch với production.
- [ ] Test logs/metrics đủ truy vết lỗi nhưng không làm lộ secret/signature/body nhạy cảm.

**Điểm cần nhớ:** kiểm thử HMAC qua proxy kiểm tra cả **tính nhất quán của request được ký** lẫn **ranh giới tin cậy giữa các hop**. Một request thành công khi gọi thẳng service chưa chứng minh hệ thống an toàn khi production rewrite URI, thêm header hoặc phân phối sang nhiều replica. Bộ kiểm thử tốt phải xác minh đúng từng byte canonical theo hợp đồng, chặn replay và request giả mạo, đồng thời chứng minh không có nghiệp vụ nào chạy khi xác thực hoặc phân quyền thất bại.
