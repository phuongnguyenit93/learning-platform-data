# Path ambiguity test: kiểm thử đường dẫn nhập nhằng trong xác thực HMAC

## 1. Bài toán bảo mật cần kiểm chứng

Trong module **SECURITY_AUTHENTICATION_HMAC_REQUEST_AUTHENTICATION**, client ký HTTP request bằng **HMAC với shared secret** trên một **canonical request** được hai phía thỏa thuận. Dữ liệu ký có thể bao gồm method, URI, header được chọn và/hoặc digest của body. Server phải xác minh chữ ký, chống replay bằng timestamp/nonce, xử lý key rotation, hoạt động đúng qua gateway/proxy và thực hiện **phân quyền** độc lập sau xác thực.

Chương **Security testing** tập trung vào cách chủ động tìm những sai lệch có khả năng dẫn đến bypass. Bài **Path ambiguity test** đặt câu hỏi:

> Có trường hợp nào **HMAC verifier xác nhận đường dẫn A**, nhưng router, gateway hoặc controller lại **thực thi tài nguyên/route B** vì mỗi lớp giải mã hoặc chuẩn hóa path theo cách khác nhau không?

Ví dụ một đối tác được phép ký request:

~~~http
POST /public/v1/payments HTTP/1.1
Host: api.example.test
X-Key-Id: partner-a-v2
X-Timestamp: 2026-11-28T10:00:00Z
X-Nonce: 25c20a80-0fb3-44e8-a579-27b3dba8334a
X-Signature: <base64-mac-for-public-v1-payments>
Content-Type: application/json

{"amount":125000,"currency":"VND"}
~~~

Nếu attacker giữ nguyên chữ ký nhưng thay đường dẫn thành `/public/v1/refunds`, request phải bị từ chối nếu path là trường được ký. Tuy nhiên các biến thể như `/public/v1/payments/..`, `/public/v1/payments/%2e%2e/admin`, `/public//v1/payments` hoặc `/public/v1/payments;mode=admin` phức tạp hơn: proxy, HTTP server, security matcher và handler có thể **không cùng diễn giải** những byte này.

**Mục tiêu:** phát hiện *path interpretation mismatch* dẫn đến sai dữ liệu ký, sai route, bypass security filter, hoặc gán quyền cho endpoint khác; không chỉ chứng minh HMAC-SHA256 có tính chất thay đổi input thì thay đổi MAC.

Sau bài học, người học có thể:

1. Phân biệt raw request target, path mà gateway nhìn thấy, path sau decode/normalization và path mà router thực thi.
2. Xác định contract ký **raw public path** hay **canonical/logical path**, từ đó chọn expected result đúng cho từng biến thể.
3. Thiết kế test thay path sau khi ký, test đường dẫn nhập nhằng, test qua proxy và test route/security matcher.
4. Viết Java/JUnit fixture cho HMAC, mutation test và integration test có **assert không phát sinh side effect**.
5. Tách rõ lỗi authentication (401), từ chối cú pháp/routing (400/404), lỗi authorization (403), replay và lỗi store (503).

## 2. Một request có thể có nhiều biểu diễn path

Không nên dùng từ “URI” mà không nói rõ đang chỉ biểu diễn nào:

| Biểu diễn | Ví dụ | Ai thường nhìn thấy? |
|---|---|---|
| Public request target | `/public/v1/payments?mode=preview` | Client và gateway ngoài |
| Public raw path | `/public/v1/payments` | Dữ liệu để ký nếu contract dùng raw path |
| Public raw query | `mode=preview` | Thành phần khác, có thể cũng nằm trong canonical |
| Percent-encoded path | `/public/v1/payments/%2e%2e/admin` | Parser trước khi decode |
| Decoded/normalized path | Có thể rút gọn thành `/public/v1/admin` | Một số proxy/framework; phụ thuộc cấu hình |
| Internal rewritten path | `/payments` | Service sau gateway rewrite |
| Route pattern | `POST /payments` | Router và Spring Security matcher |
| Effective resource/operation | `payments.create` | Business handler và authorization |

**Không được giả định** mọi proxy/framework đều normalize giống nhau. Một số server từ chối encoded slash hoặc path traversal, một số chuyển tiếp byte gốc, một số giải mã trước khi route matching. Kết quả còn phụ thuộc HTTP version, container, cấu hình firewall, route matcher và thứ tự middleware.

Chẳng hạn `%2e` thường giải mã thành dấu `.`. Nếu có đường dẫn `/public/v1/payments/%2e%2e/admin`, sau decode và xử lý dot segment, một thành phần có thể hiểu thành `/public/v1/admin`. Một thành phần khác có thể giữ nguyên `%2e%2e` như segment literal hoặc trả 400. **Test không được tự giả định rằng mọi stack sẽ đi đến cùng handler**; phải đo và khẳng định behavior thực tế.

### 2.1. Raw path không phải luôn là “bytes trên wire”

Java `URI#getRawPath()` biểu diễn path được escape trong một đối tượng URI, nhưng đối tượng ấy có thể đã được thư viện client chuẩn hóa trước khi gửi. Ở Servlet, `HttpServletRequest#getRequestURI()` trả URI mà container cung cấp, **không nhất thiết là request target gốc ngoài gateway**. Trong WebFlux, `ServerHttpRequest#getURI().getRawPath()` cũng phản ánh dữ liệu đã đi qua proxy/container.

Vì vậy, khi contract yêu cầu ký **public raw path**, test cần quan sát nhiều hop và chứng minh server nhận đúng biểu diễn tin cậy của path được ký. Không thể lấy một method tên “raw” rồi mặc định nó tái tạo được mọi byte nguyên thủy trên đường mạng.

### 2.2. Phân biệt path, query, authority và fragment

- `/public/v1/payments` là **path**.
- `?mode=preview` là **query**; path và query có thể là hai dòng riêng trong canonical.
- `Host`, scheme và port thuộc authority/origin; nếu ký chúng phải có quy tắc riêng về proxy và forwarded headers.
- `#fragment` không được gửi trong HTTP request target, nên không thể là field ký phía server trừ khi ứng dụng tự đưa nó vào dữ liệu khác.
- Trong HTTP/2, pseudo-header `:path` mang path cùng query; ở HTTP/1.1 thường dùng origin-form request-target. Proxy có thể chuyển đổi giữa hai phiên bản nhưng không được làm sai nghĩa request đã ký.

Một test chỉ đổi query không thay thế path ambiguity test; một test chỉ đổi path cũng không thay thế kiểm tra canonical body/header.

## 3. Threat model: xác minh A, thực thi B

~~~mermaid
flowchart TD
    A[Client ký public path A] --> B[Gateway / reverse proxy]
    B --> C{Path xử lý tại từng hop}
    C -->|Không biến đổi / contract rõ| D[Verifier ký đúng A]
    C -->|Decode hoặc normalize khác nhau| E[Verifier thấy A hoặc alias A]
    D --> F[Route matching + authorization]
    E --> G{Handler thực thi route nào?}
    G -->|B khác A| H[Nguy cơ path confusion/bypass]
    G -->|A đã được ràng buộc| F
    F --> I[Chỉ chạy handler nếu authn và authz đạt]
~~~

Các điểm đứt gãy bảo mật phổ biến:

1. **Signature binding sai:** client ký path A, verifier không đưa path vào canonical, nên MAC vẫn khớp khi request chuyển sang path B.
2. **Normalize khác lớp:** HMAC kiểm tra một path, Spring Security matcher dùng path khác, controller dùng path thứ ba.
3. **Gateway rewrite mất bằng chứng:** service ký internal path trong khi client ký public path, hoặc tin `X-Original-URI` do client tự giả mạo.
4. **Route bypass:** path alias không khớp matcher yêu cầu HMAC nhưng lại khớp handler nghiệp vụ.
5. **Authorization mismatch:** principal có quyền với resource A, path decode làm controller truy cập resource B.
6. **Double decoding:** `%252F` hoặc `%252e` được decode ở nhiều hop, biến literal percent escape thành slash/dot segment sau khi verifier đã tính chữ ký.
7. **Fallback nguy hiểm:** request không được match vào protected chain lại rơi sang `permitAll` hoặc một route dự phòng có cùng nghiệp vụ.

Đích kiểm thử không phải chứng minh mọi biến thể path đều trả 401; đích là chứng minh **không tồn tại đường đi mà dữ liệu được ký, route thực thi và quyền truy cập mâu thuẫn nhau**.

## 4. Chốt hợp đồng ký path trước khi thiết kế assertion

### 4.1. Hợp đồng A: ký raw public path

Một `HMAC-V1` minh họa:

~~~text
HMAC-V1
<UPPERCASE_METHOD>
<PUBLIC_RAW_PATH>
<PUBLIC_RAW_QUERY_OR_EMPTY>
<KEY_ID>
<TIMESTAMP_UTC>
<NONCE>
<LOWERCASE_HEX_SHA256_EXACT_BODY_BYTES>
~~~

Các dòng được nối bằng LF, mã hóa UTF-8, không có LF cuối. Signature:

~~~text
signature = Base64(
    HMAC-SHA256(secret, UTF8(canonicalRequest))
)
~~~

Với raw mode:

~~~text
A = /public/v1/payments
B = /public/v1/refunds
C = /public//v1/payments

canonical(A) != canonical(B)
canonical(A) != canonical(C)
~~~

Nếu giữ signature của A để gửi B hoặc C và request đi tới verifier cùng hợp đồng, MAC không còn hợp lệ. Tuy nhiên nếu C bị server/parser từ chối **trước** verifier, HTTP 400/404 cũng có thể là expected behavior; cần kiểm tra không có side effect và không có bypass.

### 4.2. Hợp đồng B: ký canonical hoặc logical path

Một số kiến trúc chủ động ký logical route ID hoặc canonical path:

~~~text
raw public path
    → strict parse + policy-defined normalization
    → canonical path hoặc logical route ID
    → HMAC field
~~~

Trong mô hình này, `/public/v1/payments` và `/public/v1/payments/` **có thể** tạo cùng canonical path nếu hợp đồng quy định alias hợp lệ và router cũng xử lý chúng như cùng một operation. Khi đó 2xx có thể là đúng cho cả hai với MAC giống nhau, **nhưng chỉ nếu authorization, resource mapping và handler cũng tương đương**.

Ngược lại, nếu normalize biến `/public/v1/admin` thành cùng route ID với `/public/v1/payments` thì hệ thống đã đánh đồng hai tài nguyên; đó là lỗi logic/trust boundary, không thể coi là tối ưu canonicalization.

**Không tự động decode rồi encode lại path để “làm test xanh”.** Mọi quy tắc normalize phải được version hóa trong contract, bao gồm xử lý `%2F`, `%5C`, dot segments, case, Unicode, trailing slash, matrix params và thứ tự các hop.

### 4.3. Hợp đồng phải khớp giữa verifier và router

Một invariant có thể diễn đạt:

~~~text
Nếu request được chấp nhận:
  signed_operation(request) == effective_routed_operation(request)
  AND authenticated_principal mayAccess(effective_routed_resource)
~~~

Trong raw mode, ánh xạ từ public signed path đến handler nội bộ có thể nằm trong gateway + route policy. Trong logical mode, route ID chỉ đáng tin nếu nguồn xác định route được bảo vệ và mapping tới handler không thay đổi ngầm.

Không dùng `X-Internal-Route-Id` hay `X-Original-URI` do client tự khai làm route ID đã được xác thực. Nếu sử dụng metadata gateway, ingress phải strip/overwrite header từ client, kênh tới service được xác thực và service kiểm tra sự phù hợp giữa original target với internal handler.

## 5. Ma trận path ambiguity quan trọng

Bảng dưới là **input kiểm thử**, không phải lời khẳng định một loại URI được mọi HTTP stack chấp nhận. Expected outcome phải được ghi theo contract, cấu hình proxy và router:

| Nhóm | Biến thể so với `/public/v1/payments` | Câu hỏi bảo mật |
|---|---|---|
| Đổi path hợp lệ | `/public/v1/refunds` | Signature của payments có dùng lại để vào refunds không? |
| Trailing slash | `/public/v1/payments/` | Router coi là alias hay route khác? |
| Double slash | `/public//v1/payments` | Proxy có collapse `//` trước verifier nhưng handler không? |
| Dot segment | `/public/v1/./payments` | Lớp nào loại bỏ `./`? |
| Parent segment | `/public/v1/payments/../admin` | Sau normalize có vượt qua ranh giới route không? |
| Encoded dot | `/public/v1/%2e/payments` | Decode `%2e` thành `.` ở đâu? |
| Encoded dot-dot | `/public/v1/payments/%2e%2e/admin` | Có tạo alias tới `/public/v1/admin`? |
| Encoded slash | `/public/v1/payments%2Fadmin` | `%2F` là ký tự của segment hay slash phân cách? |
| Encoded backslash | `/public/v1/payments%5Cadmin` | Có lớp nào xem backslash như separator? |
| Literal backslash | `/public/v1/payments\admin` | HTTP stack, WAF và router xử lý đồng nhất không? |
| Double encoded slash | `/public/v1/payments%252Fadmin` | Có xảy ra decode hai lần trước handler không? |
| Case percent encoding | `%2f` so với `%2F` | Raw mode có giữ nguyên byte, canonical mode chuẩn hóa thế nào? |
| Path parameters | `/public/v1/payments;role=admin` | Có lớp nào bỏ phần sau dấu `;`? |
| Query khác biệt | `/public/v1/payments?mode=admin` | Query có ký riêng? Đừng đánh đồng với path |
| Case-sensitive path | `/Public/v1/payments` | Matcher và router có cùng quy tắc case? |
| Unicode path | Unicode NFC/NFD hoặc percent-encoded UTF-8 | Các lớp có cùng normalization/charset? |
| Empty/repeated segments | `/public/v1//payments/` | Có route bypass do alias hay không? |
| Percent escape sai | `/public/v1/%ZZ/payments` | Được từ chối nhất quán ở lớp nào? |
| Encoded percent | `/public/v1/%252e%252e/admin` | Có decode nhiều lần tạo traversal? |
| Path prefix overlap | `/public/v1/payments-admin` | Matcher prefix có vô tình match nhầm không? |
| HTTP/2 ↔ HTTP/1.1 | `:path` qua gateway thành request-target | Có normalize khác biệt khi chuyển giao thức không? |

**Phép thử phải chia hai loại**:

- **Loại 1 — thay sang path hợp lệ khác và vẫn vào HMAC verifier:** dùng để chứng minh **MAC ràng buộc path**. Ví dụ payments → refunds, hai route đều tồn tại, đều cần HMAC, timestamp/key/nonce hợp lệ. Nếu giữ chữ ký cũ, kỳ vọng 401.
- **Loại 2 — path nhập nhằng/không hợp lệ:** có thể bị chặn trước verifier (400/404), hoặc normalize theo contract. Kỳ vọng trọng tâm là **không bypass, không thực thi sai handler, không vi phạm authorization**, chứ không buộc mọi biến thể trả 401.

### 5.1. Vì sao encoded slash nguy hiểm?

`/public/v1/payments%2Fadmin` có thể được một tầng xem là một segment `payments%2Fadmin` và tầng khác decode thành hai segment `payments/admin`. Nếu security matcher kiểm tra prefix khác router, request có thể đi vào policy không dự kiến. Cách giảm thiểu thường là **từ chối encoded slash trên route không hỗ trợ** hoặc thiết kế canonicalization/matching thống nhất xuyên suốt các hop.

### 5.2. Vì sao path parameter và matrix variable cần test?

Một số HTTP stack xử lý phần sau dấu chấm phẩy trong path theo các quy tắc riêng; một lớp có thể giữ `;role=admin` còn lớp khác bỏ trước khi route. Nếu verifier ký path đầy đủ nhưng authorization dùng path đã bỏ semicolon, hoặc ngược lại, hợp đồng có thể bị phá. Trên những API không sử dụng matrix variables, **từ chối dấu `;` trên signed route** có thể là lựa chọn đơn giản và an toàn.

### 5.3. Không lẫn `+` trong path với form/query encoding

`+` thường được diễn giải thành space trong biểu diễn `application/x-www-form-urlencoded`, nhưng không có quy tắc chung “mọi dấu cộng trong URL path đều là space”. Đừng dùng `URLDecoder` dành cho form để chuẩn hóa path một cách tùy tiện. Nếu contract cho phép percent-encoded path, cần xác định rõ parser và bộ mã hóa dành riêng cho path.

## 6. Quyết định expected result ở từng tầng

| Request / kết quả kiểm tra | HTTP status minh họa | Điều kiện tối thiểu |
|---|---|---|
| Request đúng path, MAC/key/time/nonce hợp lệ, đủ quyền | 2xx theo API | Handler đúng operation, side effect đúng một lần |
| Đổi sang **một protected path hợp lệ khác**, giữ MAC cũ | **401** | Không có handler/side effect; xác nhận lỗi MAC |
| Path malformed, encoded slash bị policy cấm | **400** hoặc **404** theo route/container | Không rơi vào handler ngoài policy |
| Path alias hợp lệ trong canonical mode | Có thể 2xx | Chỉ khi alias thực sự cùng operation/quyền |
| Path alias khác resource nhưng MAC vẫn hợp lệ | **Không được chấp nhận** | Đó là lỗi route binding nếu 2xx |
| MAC đúng cho path B nhưng principal thiếu quyền trên B | **403** | Authentication thành công nhưng authorization từ chối |
| Timestamp ngoài cửa sổ | **401** | Không nhầm thành path mismatch |
| Nonce đã claim trước đó | **401** | Replay bị chặn qua nhiều replica |
| Key bị revoke/không tồn tại | **401** | Không cho thử các key khác để cứu MAC |
| Key/nonce store không hoạt động | **503** theo contract | Fail closed, không chạy handler |
| Body quá lớn | **413** | Không buffer vô hạn trước xác thực |

Một test trả 401 **chưa chứng minh** verifier kiểm tra path: có thể là timestamp hết hạn hoặc nonce replay. Một test trả 404 **chưa chứng minh** URL nhập nhằng an toàn: proxy có thể chuyển nó thành route khác trong cấu hình thực tế. Khi kiểm tra, phải biết **route nào được match, filter nào được gọi, nguyên nhân nội bộ và side effect nào đã xảy ra**.

HTTP 401 nên có `WWW-Authenticate` theo hợp đồng. Scheme `HMAC` dùng trong ví dụ là lựa chọn riêng của API, không phải cơ chế được Spring Security tự cung cấp. Response công khai không chứa expected MAC, secret, canonical bytes nhạy cảm hoặc kết quả key enumeration.

## 7. Thiết kế fixture: cố định các yếu tố không thuộc path

Một server fixture hữu ích cho bài này cần:

| Thành phần | Thiết lập | Vì sao |
|---|---|---|
| Secret test | Chỉ synthetic shared secret, không credential thật | Để signer/verify dùng khóa ổn định |
| Key ID | Một key active và có hiệu lực | Không để lỗi key che lỗi path |
| Server clock | `Clock.fixed(...)` | Timestamp không tự hết hạn |
| Timestamp | Nằm trong window của clock fixture | Không lẫn freshness rejection |
| Nonce | Mới cho mỗi test âm | Không lẫn replay rejection |
| Nonce store | Fake atomic cho unit, Redis thật cho multi-replica | Mỗi phép thử rõ trạng thái và ranh giới |
| Protected routes | Ít nhất payments và refunds đều yêu cầu HMAC | Path mutation vẫn vào verifier |
| Authorization | Test principal có quyền cho baseline | Tách MAC mismatch với 403 |
| Gateway | Route rewrite/tin cậy tương tự production | Bắt lỗi decode ở nhiều hop |
| Business spy | Đếm invocation và side effect | Chứng minh request bị từ chối trước handler |

**Hai loại test phải có fixture tách biệt**. Test “MAC ràng buộc path” đổi `/public/v1/payments` sang một endpoint *hợp lệ và được bảo vệ*. Test “path ambiguity không bypass” gửi encoding/dot segments có thể bị chặn ở gateway hoặc security layer; cần assertion về route/handler chứ không chỉ một mã lỗi cố định.

~~~text
Precondition test A:
  signPath   = "/public/v1/payments"
  actualPath = "/public/v1/refunds"
  nonce      = fresh for THIS test
  signature  = HMAC(secret, canonical(signPath, ...))
  request sent with actualPath + original signature

Expected:
  401 from the protected security chain
  refundHandler not called
  paymentHandler not called
  nonce not claimed if claim happens after valid MAC
~~~

### 7.1. Tránh false positive từ replay

Nếu test dương gửi path A với nonce N trước, sau đó test âm gửi path B **cũng dùng nonce N**, 401 có thể là do replay. Do đó:

1. Mỗi negative case sử dụng **nonce chưa từng được claim**.
2. Tạo chữ ký cho path A bằng chính nonce mới đó.
3. Chỉ thay **actual request path** thành B, không ký lại.
4. Test key/clock/body/method/header khác giữ nguyên và hợp lệ.
5. Nếu có audit nội bộ, xác nhận MAC mismatch xảy ra trước nonce claim; không công khai chi tiết này trong HTTP response.

Không reset nonce store của môi trường dùng chung với production. Test fixture phải có namespace cô lập và teardown độc lập; nhiều test song song không được dùng chung mutable fixture rồi race.

## 8. Java 17: dựng signer theo raw-path contract minh họa

Class sau phục vụ test, không tự động là hợp đồng của mọi API. Nó hash byte body đúng như nhận được, đưa raw path vào một dòng canonical và tính HMAC-SHA256. Test HTTP adapter phải kiểm tra format/độ dài/số lượng header, không cho newline trong các trường canonical:

~~~java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.util.Base64;
import java.util.HexFormat;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public final class PathHmacTestSigner {
    private PathHmacTestSigner() {}

    public static String canonical(
            String method, String publicRawPath, String publicRawQuery,
            String keyId, String timestamp, String nonce, byte[] rawBody)
            throws GeneralSecurityException {

        String bodyHash = HexFormat.of().formatHex(
                MessageDigest.getInstance("SHA-256").digest(rawBody));
        return String.join("\n",
                "HMAC-V1",
                method,
                publicRawPath,
                publicRawQuery == null ? "" : publicRawQuery,
                keyId,
                timestamp,
                nonce,
                bodyHash);
    }

    public static byte[] sign(byte[] secret, String canonical)
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

Ví dụ dùng `HMAC-V1` nêu ở mục 4; canonical join **không có LF kết thúc**. Không được chuyển `rawBody` thành String rồi serialize JSON trước khi hash. Nếu hợp đồng ký header khác (ví dụ `Content-Type`) phải bổ sung và dùng đúng biểu diễn đã thỏa thuận.

### 8.1. Unit test: đổi path hợp lệ làm MAC không khớp

~~~java
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import org.junit.jupiter.api.Test;

class PathHmacTestSignerTest {
    @Test
    void changingSignedPathChangesHmac() throws Exception {
        byte[] secret = "synthetic-contract-key-1"
                .getBytes(StandardCharsets.UTF_8);
        byte[] body = "{\"amount\":125000}"
                .getBytes(StandardCharsets.UTF_8);

        String timestamp = "2026-11-28T10:00:00Z";
        String nonce = "nonce-path-mutation-001";

        String original = PathHmacTestSigner.canonical(
                "POST", "/public/v1/payments", "",
                "partner-a-v2", timestamp, nonce, body);
        String changed = PathHmacTestSigner.canonical(
                "POST", "/public/v1/refunds", "",
                "partner-a-v2", timestamp, nonce, body);

        byte[] signedMac = PathHmacTestSigner.sign(secret, original);
        assertTrue(MessageDigest.isEqual(
                signedMac, PathHmacTestSigner.sign(secret, original)));
        assertFalse(MessageDigest.isEqual(
                signedMac, PathHmacTestSigner.sign(secret, changed)));
    }
}
~~~

Test trên cho thấy đầu vào HMAC khác tạo MAC khác; **chưa chứng minh server verifier lấy đúng path**. Nếu signer và verifier cùng có bug bỏ path khỏi canonical, positive test vẫn có thể pass. Cần một **golden vector độc lập** cho canonical bytes và test HTTP qua security chain.

### 8.2. Unit test cho policy path nghiêm ngặt

Một số API chỉ cho phép vài route public cụ thể. **Nếu hợp đồng cố ý chỉ hỗ trợ path ASCII đơn giản, không encoding**, allowlist trước xác thực là một biện pháp dễ xác minh:

~~~java
import java.util.Set;

public final class StrictSignedPathPolicy {
    private static final Set<String> ALLOWED = Set.of(
            "/public/v1/payments",
            "/public/v1/refunds");

    private StrictSignedPathPolicy() {}

    public static boolean accepts(String publicRawPath) {
        return publicRawPath != null && ALLOWED.contains(publicRawPath);
    }
}
~~~

~~~java
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;
import org.junit.jupiter.api.Test;

class StrictSignedPathPolicyTest {
    @Test
    void rejectsAliasesNotPresentInTheContract() {
        assertTrue(StrictSignedPathPolicy.accepts(
                "/public/v1/payments"));
        assertFalse(StrictSignedPathPolicy.accepts(
                "/public/v1/payments/"));
        assertFalse(StrictSignedPathPolicy.accepts(
                "/public//v1/payments"));
        assertFalse(StrictSignedPathPolicy.accepts(
                "/public/v1/./payments"));
        assertFalse(StrictSignedPathPolicy.accepts(
                "/public/v1/payments%2Fadmin"));
        assertFalse(StrictSignedPathPolicy.accepts(
                "/public/v1/payments;role=admin"));
    }
}
~~~

Đây chỉ là **policy mẫu cho hai đường dẫn cố định**, không phải trình parse URI đầy đủ. Với route có path parameter hoặc ứng dụng cần percent-encoding hợp lệ, phải thiết kế parser/canonicalization riêng và test tính tương đương. Quan trọng hơn, policy phải nhận public raw path **từ nguồn đáng tin trước khi bị normalize mất thông tin**. Nếu container đã biến `/public//v1/payments` thành `/public/v1/payments` trước khi gọi policy, hàm này không thể phát hiện biến thể gốc; cần cấu hình/kiểm tra ở ingress hoặc container.

## 9. Integration test: thay path **sau khi ký** qua HTTP

Để test ranh giới HTTP, fixture phải có hai endpoint `POST /public/v1/payments` và `POST /public/v1/refunds`, **đều yêu cầu HMAC**, dù gateway có rewrite tới internal routes khác nhau. Đầu tiên ký payments, sau đó gửi request tới refunds mà giữ nguyên chữ ký đó.

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

class PathBindingThroughGatewayIT {
    private final HttpClient client = HttpClient.newHttpClient();
    private final URI gatewayBase = URI.create("http://127.0.0.1:18080");
    private final byte[] secret = "synthetic-contract-key-1"
            .getBytes(StandardCharsets.UTF_8);

    private HttpResponse<String> send(
            String pathToSign, String actualPath, String nonce)
            throws Exception {

        byte[] body = "{\"amount\":125000}"
                .getBytes(StandardCharsets.UTF_8);
        // Test thật phải đồng bộ với Clock của server fixture.
        String timestamp = Instant.now().toString();
        String canonical = PathHmacTestSigner.canonical(
                "POST", pathToSign, "", "partner-a-v2",
                timestamp, nonce, body);
        String signature = PathHmacTestSigner.signBase64(
                secret, canonical);

        HttpRequest request = HttpRequest.newBuilder(
                URI.create(gatewayBase.toString() + actualPath))
                .header("Content-Type", "application/json")
                .header("X-Key-Id", "partner-a-v2")
                .header("X-Timestamp", timestamp)
                .header("X-Nonce", nonce)
                .header("X-Signature", signature)
                .POST(HttpRequest.BodyPublishers.ofByteArray(body))
                .build();
        return client.send(request, HttpResponse.BodyHandlers.ofString());
    }

    @Test
    void changedProtectedPathFailsAuthentication() throws Exception {
        String nonce = UUID.randomUUID().toString();
        HttpResponse<String> response = send(
                "/public/v1/payments",
                "/public/v1/refunds",
                nonce);

        assertEquals(401, response.statusCode());
        // Test harness cần assert paymentSpy=0, refundSpy=0,
        // và security filter đã xử lý request.
    }
}
~~~

`gatewayBase` là ví dụ cổng gateway của **test harness**, không phải một server tự khởi động từ code này. Trong suite thật, nó phải trỏ đúng proxy/test server đã inject key/clock/nonce, và nên có **baseline** ký refunds gửi refunds thành công theo API. Nếu refunds trả 404 do không có route, một test kỳ vọng 401 sẽ không chứng minh path binding; hãy bảo đảm hai route đều tồn tại và protected.

**Lưu ý về timestamp:** nếu server dùng `Clock.fixed`, đừng để test gửi `Instant.now()` khác cửa sổ; thay bằng timestamp do fixture cấp. Nếu server dùng clock thực, fixture phải đồng bộ với client. Với negative case, nonce mới chưa dùng là bắt buộc.

### 9.1. Test body/headers không đổi khi mutate path

Một ca changed-path chuẩn chỉ thay **actualPath**, giữ method, raw query, body bytes, signed headers, key ID, timestamp và nonce đúng với chữ ký đã tạo. Nếu helper HTTP client tự động ký lại request sau khi sửa URI, test đã biến thành ca hợp lệ khác. Không gọi signer sau bước mutate.

### 9.2. Assert cả handler và side effect

~~~java
// Pseudocode bên trong integration test có fixture spy và DB giả.
int beforePayments = paymentSpy.createCalls();
int beforeRefunds = refundSpy.createCalls();

HttpResponse<String> rejected = send(
        "/public/v1/payments",
        "/public/v1/refunds",
        "nonce-not-previously-claimed");

assertEquals(401, rejected.statusCode());
assertEquals(beforePayments, paymentSpy.createCalls());
assertEquals(beforeRefunds, refundSpy.createCalls());
verifyNoInteractions(paymentEventPublisher, refundEventPublisher);
~~~

Khi test chạy trên dịch vụ có database/broker thực, kiểm tra cả số record ghi, message publish và downstream calls. Nếu HTTP trả 401 nhưng refund handler đã thực hiện lệnh hoàn tiền, test phải thất bại: bảo mật cần ngăn side effect **trước khi request bị từ chối**.

## 10. Kiểm thử path nhập nhằng xuyên proxy và HTTP stack

Một test tốt phải quan sát đường đi:

~~~text
Test client raw request target
    → edge gateway / WAF (input validation)
    → reverse proxy (rewrite / normalize / forwarded metadata)
    → HTTP container (URI parsing)
    → HMAC filter (signed public target)
    → Spring route matcher / handler mapping
    → authorization (resource/operation)
    → business handler
~~~

Test có thể dùng gateway thực hoặc container tương đương staging. Với những URI bất thường, Java `HttpClient` hoặc `URI.create` có thể chuẩn hóa, escape hoặc từ chối **trước khi gửi**. Do đó, cần **xác minh request target thực tại hop đầu tiên**; trong môi trường test cô lập có thể dùng HTTP client mức thấp hỗ trợ gửi exact request target. Không tự suy rằng một string Java giống bytes gateway nhận được.

### 10.1. Thiết kế test case theo từng hop

| Test | Input/đường đi | Assertion chính |
|---|---|---|
| Raw happy path | `/public/v1/payments` | HMAC hợp lệ, đúng route/quyền |
| Valid cross-route tamper | Sign payments, gửi refunds | 401, không handler nào chạy |
| Double slash | `/public//v1/payments` | Reject/normalize theo policy, không bypass |
| Dot segments | `/public/v1/./payments`, `/../` | Tầng normalize có hành vi ổn định và được kiểm chứng |
| Encoded slash | `%2F` và `%2f` | Không khác kết quả bảo mật giữa WAF, verifier, router |
| Double decode | `%252F`/`%252e` | Không biến path literal được ký thành route khác |
| Semicolon | `;role=admin` | Không bỏ field ở một lớp rồi cho handler dùng nghĩa khác |
| Backslash | Literal `\` hoặc `%5C` | Không vượt security matcher nhờ separator khác |
| Percent escape malformed | `%ZZ` hoặc `%` cuối path | Reject rõ ràng, không bypass filter |
| Trailing slash | `/payments/` | Theo contract, không rơi vào route permitAll |
| Unicode NFC/NFD | Biểu diễn khác nhau | Normalize/reject theo hợp đồng, không truy cập sai resource |
| HTTP/2 translation | `:path` qua gateway | Không thay signed operation |
| Client-supplied original URI | Header giả `X-Original-URI` | Ingress strip/overwrite, không tin dữ liệu client |
| Direct backend access | Bỏ qua gateway | Network/mTLS hoặc service policy chặn an toàn |

Với mỗi case nên ghi thêm **matched route ID**, **handler ID** và **reason enum** trong test sink nội bộ, nhưng không log raw URI chứa dữ liệu nhạy cảm ở production. Nếu request bị từ chối ngay gateway, kiểm tra gateway response và việc service **không nhận request**. Nếu request đến service, kiểm tra HMAC/security chain, route mapping và side effect.

### 10.2. Test header spoofing qua gateway

Client cố gửi:

~~~http
POST /public/v1/refunds HTTP/1.1
X-Original-URI: /public/v1/payments
X-Internal-Public-Target: /public/v1/payments
X-Internal-Route-Id: payments.create
X-Signature: <signature-valid-for-payments>
~~~

**Không chấp nhận** chữ ký của payments chỉ vì attacker viết một header nói rằng request gốc là payments. Gateway phải xóa/ghi đè metadata từ client, chỉ service kết nối qua hop được xác thực mới được tin metadata gateway và vẫn phải kiểm tra mapping giữa request target, route nội bộ và operation.

Nếu gateway có chủ đích xác thực HMAC ở edge thay vì service, nó cần phát hành một assertion **được bảo vệ** tới backend và gắn assertion vào target/operation thực tế; backend không được tin một chuỗi header chưa xác thực như thể đó là kết quả verify.

### 10.3. Filter coverage test: mọi alias đều được bảo vệ

Một lỗi rất nguy hiểm là security chain chỉ match path “đẹp”:

~~~text
Security matcher: /public/v1/payments
Handler mapping:  /public/v1/payments hoặc alias sau normalize

Request nhập nhằng đi vào handler
nhưng không đi qua HMAC verifier.
~~~

Kiểm thử nên có route-scanner/fixture để khẳng định **mọi path có thể chạm business handler đều thuộc một policy rõ ràng**. Default-deny hoặc route matcher bảo vệ theo operation có thể giảm rủi ro. Tránh cấu hình fallback `permitAll` cho request “không match”, rồi để router thực thi nghiệp vụ sau một bước normalize khác.

## 11. Authentication, authorization, replay và key rotation

**Authentication:** MAC sai vì đổi một path được ký → 401 chung theo contract (kèm challenge phù hợp). Không suy ra đây là body mismatch hay key sai nếu chưa kiểm chứng fixture.

**Authorization:** giả sử client tạo chữ ký mới **đúng** cho `/public/v1/refunds` bằng secret còn active, nhưng principal chỉ có `payments:write`. Request đã authenticated, nhưng phải nhận **403 Forbidden** vì thiếu `refunds:write`. HMAC hợp lệ không tự cấp quyền trên route/resource khác.

**Replay:** request cũ có cùng nonce và MAC hợp lệ vẫn có thể bị gửi lại. Nonce phải claim **nguyên tử** trong shared store sau signature valid. Test changed-path không được dùng nonce đã claim để tránh một 401 “đúng mã” nhưng sai nguyên nhân.

**Key rotation:** nếu một key bị revoke, mọi path dù signature toán học đúng vẫn phải từ chối. Trong thời gian overlap, key ID K1/K2 chỉ được chấp nhận theo policy; không thử mọi secret đến khi tìm chữ ký khớp. Test path binding dùng một key active ổn định, còn test key lifecycle được chạy riêng.

**Proxy/tenant:** route alias có thể vô tình chuyển từ `tenant A` sang `tenant B`. Thông tin tenant để tạo principal phải xuất phát từ bản ghi key đã xác minh, còn resource/tenant được yêu cầu phải qua authorization. Không tự tin `X-Tenant-Id`, forwarded path hay role được client khai báo.

**Failure mode:** khi key store hoặc nonce store không khả dụng, server fail closed (ví dụ 503), không cho request đi qua nhằm “giữ SLA”; các metric nội bộ phải phân biệt lỗi hệ thống với credential rejection.

## 12. Property-based test và mutation testing

Để tránh phụ thuộc một vài URI viết tay, tạo bộ generator có kiểm soát cho từng nhóm:

- Sinh path ASCII hợp lệ trong tập route được bảo vệ; đổi sang **operation khác** nhưng giữ MAC cũ.
- Chèn/xóa dấu slash, trailing slash, dot segment, encoded dot và encoded slash.
- Sinh percent escape hợp lệ/không hợp lệ, encoding chữ hoa/chữ thường, double encoding.
- Sinh path segment có Unicode NFC/NFD, ký tự đặc biệt và độ dài sát giới hạn.
- Thêm semicolon matrix variable hoặc backslash tại các vị trí khác nhau.
- Tạo các biến thể có cùng logical operation **chỉ khi contract định nghĩa chúng tương đương**.

Những property cần kiểm tra:

~~~text
P1: Nếu raw path thay đổi và raw-path contract không xem là alias:
    giữ original MAC => không authenticated.

P2: Nếu input bị policy từ chối trước HMAC:
    handler không chạy, dù MAC có hoặc không.

P3: Nếu contract coi hai path tương đương:
    verifier, router và authorization phải đi tới cùng operation/resource.

P4: Nếu effective operation khác signed operation:
    request không thể tạo side effect.

P5: Không có public path nào tới protected business handler
    mà tránh được security filter.
~~~

**Mutation testing** đặc biệt hữu ích: thử cố ý thay verifier dùng path rỗng, bỏ path khỏi canonical, tin `X-Original-URI` do client gửi hoặc tắt strict path policy. Bộ test đúng phải đỏ. Nếu suite vẫn xanh, nó mới chứng minh vài HTTP status chứ chưa bảo vệ được invariant path binding.

## 13. Chẩn đoán khi test thất bại

### 13.1. Baseline hợp lệ nhận 401

Trước khi nghi do path ambiguity, kiểm tra:

1. Timestamp có nằm trong cửa sổ theo server clock, nonce có mới và key có còn active?
2. Client và verifier có cùng HMAC version, separator LF, encoding UTF-8 và secret?
3. Client thật sự gửi raw path/query nào? Có thư viện URI tự normalize trước khi phát?
4. Gateway có rewrite public path sang internal path, và verifier có lấy đúng **public target đáng tin**?
5. HMAC filter có hash body gốc hay parse/serialize lại, có ký cùng headers không?
6. Duplicate headers, content encoding hoặc proxy thêm/xóa trường ký có làm canonical khác?

Chỉ sau khi fixture đủ điều kiện mới dùng negative path case để kết luận.

### 13.2. Changed-path nhận 2xx

Đây có thể là lỗi nặng nếu actual path là operation khác:

1. Test đã ký **sau khi mutate** actualPath chưa? Nếu có, case không còn negative.
2. Có path nào không được đưa vào canonical string không?
3. Verifier đang lấy path từ internal header không đáng tin hoặc hằng số route?
4. Security matcher có bỏ qua path alias, trong khi handler vẫn nhận?
5. Gateway có normalize actualPath về signedPath không? Nếu đó là **alias được contract cho phép**, cần kiểm tra same operation; nếu không, policy phải từ chối.
6. Handler và authorization có cùng cách giải mã path và cùng effective resource không?
7. Có side effect nào đã chạy trước khi exception authentication được phát không?

### 13.3. Ambiguous path nhận 400 hoặc 404

Đây **có thể là kết quả tốt**, nhưng cần xác nhận:

- Request thật sự đã đến hop nào và bị từ chối ở đâu.
- Không có retry/fallback nội bộ chuyển sang route khác.
- Không có handler hoặc downstream call nào được kích hoạt.
- Không có khác biệt behavior nguy hiểm khi chuyển HTTP/1.1 ↔ HTTP/2, thay percent encoding hoặc bật proxy config khác.

Để chẩn đoán, log/trace nên dùng correlation ID do gateway/service tin cậy, route template và reason enum hữu hạn. **Không log secret, signature đầy đủ, body chứa PII hoặc raw query nhạy cảm**. Khi cần kiểm tra byte request target, dùng fixture giả trong môi trường test cô lập và chỉ lưu bằng chứng theo chính sách truy cập/retention.

## 14. Checklist triển khai cho CI và staging

- [ ] Contract nêu rõ raw public path, canonical path hay logical route ID; version, encoding và policy alias/normalization.
- [ ] Có golden vector HMAC độc lập bao gồm path; test signer và verifier không cùng bỏ path.
- [ ] Có hai route **đều được bảo vệ** để test ký A, gửi B mà không ký lại.
- [ ] Timestamp hợp lệ, key active, nonce mới cho mỗi negative case; không nhầm 401 replay với MAC mismatch.
- [ ] Test nhập nhằng gồm trailing slash, `//`, dot/parent segments, `%2F`, `%2e`, `%252F`, backslash, semicolon, Unicode, percent malformed.
- [ ] Mỗi biến thể có expected behavior theo contract (reject hoặc alias hợp lệ), không ép tất cả thành 401.
- [ ] Quan sát actual request target tại hop thích hợp; Java URI/HTTP client có thể normalize trước khi gửi.
- [ ] Gateway strip/overwrite original-target metadata giả, giao tiếp tới service được xác thực, route mapping đáng tin.
- [ ] Security matcher, verifier, router và authorization dùng cùng operation/resource semantics, không có `permitAll` fallback.
- [ ] HMAC không bị bỏ qua khi alias path không khớp matcher; handler không chạy trước authentication.
- [ ] Assert HTTP status, matched route/handler ID và **không side effect** trong mọi trường hợp bị từ chối.
- [ ] Signed request hợp lệ nhưng thiếu quyền vào route B nhận 403, không phải 401.
- [ ] Replay, key rotation/revoke và unavailable store được kiểm thử riêng, không gây false positive cho path test.
- [ ] Có property-based/mutation tests để phát hiện khi path binding bị vô hiệu hóa.
- [ ] CI chạy unit/vector + Spring Security integration; staging chạy thêm proxy thật, HTTP version transition và nhiều replica khi cần.
- [ ] Log/metric không chứa secret, raw MAC hoặc định danh chưa xác thực làm nhãn cardinality cao.

## 15. Kết luận

**Path ambiguity test** kiểm chứng nhiều hơn “đổi URI thì MAC sai”. Nó buộc toàn bộ đường đi từ **client → gateway → HTTP parser → HMAC verifier → security matcher → router → authorization** phải nhất quán về **path được ký và operation thực thi**. Một signed path hợp lệ không được phép bị thay thành resource khác; một path nhập nhằng không được phép trở thành lối tắt vượt security filter.

Cách kiểm thử hiệu quả là kết hợp **một negative case thay sang protected path hợp lệ khác** để chứng minh HMAC bảo vệ path, với **bộ biến thể nhập nhằng** để phát hiện decode/normalize/rewrite không nhất quán. Mỗi case phải kiểm tra status và side effect, đồng thời cô lập timestamp, nonce, key rotation và phân quyền. Khi các invariant đó được giữ qua proxy và nhiều framework/HTTP version, hệ thống mới thực sự bảo vệ đúng tài nguyên mà client đã ký.
