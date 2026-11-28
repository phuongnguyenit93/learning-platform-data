# Bước học tiếp theo sau khi hoàn thành HMAC request authentication

## 1. Từ “biết tạo HMAC” đến “vận hành được một giao thức xác thực”

Trong module **SECURITY_AUTHENTICATION_HMAC_REQUEST_AUTHENTICATION**, người học đã tiếp cận việc xác thực HTTP request bằng **HMAC với shared secret**, xây dựng **canonical request** theo hợp đồng ký (method, URI, header và/hoặc body), xác minh MAC, giới hạn replay bằng **timestamp/nonce**, quản lý **key rotation**, kiểm tra ảnh hưởng **proxy/gateway** và phân biệt rõ **authentication** với **authorization**.

Chương **Tổng kết HMAC authentication** không nên kết thúc ở việc ghi nhớ cách gọi `Mac.getInstance("HmacSHA256")`. Bài **Bước học tiếp theo** biến kiến thức thành lộ trình nâng năng lực: từ viết được signer đơn giản, sang kiểm thử giao thức ở byte-level, tích hợp vào Spring Security, chứng minh an toàn khi chạy nhiều replica, và cuối cùng đưa ra quyết định kiến trúc/vận hành có căn cứ.

**Câu hỏi trọng tâm:** nếu một API dùng HMAC đang chạy production, bạn có thể chứng minh được **một request hợp lệ được chấp nhận, request không hợp lệ bị từ chối trước side effect, và kết quả đó vẫn đúng sau gateway rewrite, key rotation, Redis failover hoặc deploy phiên bản mới** hay không?

**Đầu ra mong muốn sau lộ trình:**

1. Một **signature contract** ngắn, không nhập nhằng về byte và encoding.
2. Một bộ **golden vectors độc lập** cho client và server.
3. Một HTTP authentication component tích hợp Spring Security nhưng không nhầm authentication với quyền truy cập.
4. Một lớp replay protection có kiểm thử **atomicity** trên store dùng chung.
5. Một bộ contract/security tests qua gateway và nhiều replica.
6. Tài liệu threat model, observability, key lifecycle và runbook sự cố.
7. Một báo cáo nghiệm thu có **positive lẫn negative evidence**, không chỉ kết quả “test xanh”.

Đây là **gợi ý học tiếp**, không phải yêu cầu bắt buộc phải dùng một framework, phiên bản HMAC hay dịch vụ hạ tầng cụ thể. Khi ứng dụng thực tế khác bài lab, cần điều chỉnh theo threat model và chính sách tổ chức.

## 2. Tự đánh giá trước khi chọn nhánh học

Đánh giá bằng **bằng chứng thực hiện được**, không bằng mức tự tin chủ quan:

| Năng lực | Câu hỏi tự kiểm tra | Bằng chứng đạt |
|---|---|---|
| Cryptographic primitive | HMAC khác hashing và chữ ký số ở đâu? | Viết JUnit so sánh HMAC với vector đã biết |
| Secret/encoding | Secret Base64 có được dùng trực tiếp như text không? | Decode secret ra bytes và so khớp expected MAC |
| Canonical request | Hai bên ký đúng byte nào? | Xuất canonical bytes/hash từ fixture có dữ liệu giả |
| Raw URI và gateway | Verifier ký public path hay internal path? | Test qua proxy có rewrite |
| Body handling | Sau filter, controller còn đọc được body không? | Integration test Servlet hoặc WebFlux thực |
| Replay | Hai request trùng nonce cùng lúc sẽ thế nào? | Một claim thắng trên Redis dùng chung |
| Key lifecycle | Key bị revoke nhưng cache còn giá trị thì sao? | Negative test nhiều replica với key đã thu hồi |
| Authorization | MAC đúng nhưng caller thiếu quyền thì sao? | 403 và không thực hiện nghiệp vụ |
| Fault handling | Nonce/key store không sẵn sàng thì sao? | Fail closed, lỗi availability theo contract |
| Operations | Sau deploy làm sao phát hiện filter bị bypass? | Positive + unsigned/invalid-MAC probes và dashboard |

Nếu chưa có bằng chứng cho ba dòng đầu, hãy bắt đầu ở **nhánh nền tảng**. Nếu đã có signer/verifier và test đơn JVM, nên tập trung **tích hợp Spring Security và distributed replay**. Nếu đã triển khai production, ưu tiên **security testing, incident response, migration và quan sát vận hành**.

### 2.1. Bốn mức độ thành thạo

| Mức | Có thể làm gì? | Chưa nên khẳng định |
|---|---|---|
| **L1 — Byte-level** | Tính đúng HMAC, thống nhất canonical bytes | “Đã có xác thực HTTP an toàn” |
| **L2 — HTTP/Spring** | Tạo principal từ verified key, route được bảo vệ | “An toàn qua mọi proxy/instance” |
| **L3 — Distributed security** | Nonce atomic, key revoke và proxy E2E được test | “Không có rủi ro vận hành còn lại” |
| **L4 — Production-ready** | Có threat model, tests, monitoring, rollback và runbook | “Không cần đánh giá lại khi thay đổi hợp đồng” |

Đừng nhảy từ L1 tới L4 chỉ bằng cách thêm một Redis client hoặc một filter. Mỗi mức đòi hỏi **loại bằng chứng khác nhau**.

## 3. Bản đồ các nhánh kiến thức tiếp nối

~~~mermaid
flowchart TD
    A[HMAC fundamentals + secret bytes] --> B[Canonical contract + golden vectors]
    B --> C[Spring Security / HTTP integration]
    C --> D[Authn vs authz / tenant isolation]
    C --> E[Timestamp + nonce atomic replay protection]
    C --> F[Proxy/gateway trust boundaries]
    D --> G[Security/contract testing]
    E --> G
    F --> G
    G --> H[Key rotation / signature migration]
    G --> I[Metrics, tracing, failure handling]
    H --> J[Canary + incident response]
    I --> J
    J --> K[Capstone: production-like signed API]
~~~

Lộ trình không bắt buộc tuyến tính tuyệt đối: người dùng WebFlux có thể học về `DataBuffer` sớm; nhóm platform có thể ưu tiên gateway trước; nhóm security có thể bắt đầu bằng threat model và mutation testing. Tuy nhiên **canonical contract và trust boundaries** phải được làm rõ trước mọi tối ưu.

### 3.1. Ba hướng học tùy vai trò

| Bạn muốn trở thành... | Ưu tiên | Sản phẩm thực hành |
|---|---|---|
| **Backend Java/Spring** | HTTP filter, body replay, security context, authorization | Signed read/write API với MockMvc hoặc WebTestClient |
| **Security engineer** | Threat modeling, protocol ambiguity, key lifecycle, downgrade/replay attacks | Security test matrix + proof-of-rejection |
| **Platform/SRE** | Gateway, multi-region, Redis/key store, metrics, canary/rollback | Staging topology + operational runbook |

Nếu chưa chắc chọn nhánh nào, hoàn thiện **capstone cơ bản** ở mục 14 trước; từ những failure bạn gặp sẽ thấy nhánh cần đào sâu.

## 4. Chặng 1 — Nắm chắc các byte được ký

### 4.1. Bài tập: đóng băng HMAC-V1 contract

Hãy tạo một trang đặc tả riêng trong dự án thực hành, định nghĩa **đúng một** profile. Ví dụ:

~~~text
Profile: HMAC-V1
MAC: HMAC-SHA256, output 32 bytes
Secret: opaque bytes từ secret manager
Canonical charset: UTF-8, no BOM
Separator: LF, no trailing LF
Field 1: literal "HMAC-V1"
Field 2: uppercase HTTP method
Field 3: trusted public raw path
Field 4: trusted public raw query or empty
Field 5: key ID
Field 6: signed UTC timestamp
Field 7: signed nonce
Field 8: lowercase hex SHA-256 of exact body bytes
Wire signature: standard Base64 padded
~~~

Đây là **hợp đồng ví dụ**, không phải chuẩn chung cho tất cả API HMAC. Nếu hệ thống chọn signed headers, `Host`, body digest ở định dạng khác hoặc canonical URI được normalize, phải viết đầy đủ quy tắc tương ứng và version hóa.

### 4.2. Bài tập: kiểm thử primitive độc lập

Trước khi ký HTTP request, kiểm tra Java JCA bằng một vector HMAC-SHA256 đã công bố. Chẳng hạn một test case tiêu chuẩn dùng key gồm 20 byte `0x0b` và thông điệp UTF-8 `Hi There`:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import java.util.HexFormat;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import org.junit.jupiter.api.Test;

class HmacPrimitiveTest {
    @Test
    void sha256MatchesKnownTestVector() throws Exception {
        byte[] key = new byte[20];
        Arrays.fill(key, (byte) 0x0b);

        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(key, "HmacSHA256"));
        byte[] result = mac.doFinal(
                "Hi There".getBytes(StandardCharsets.UTF_8));

        assertEquals(
                "b0344c61d8db38535ca8afceaf0bf12b"
              + "881dc200c9833da726e9376c2e32cff7",
                HexFormat.of().formatHex(result));
    }
}
~~~

Khi test này xanh, bạn mới biết primitive HMAC chạy đúng trên vector đó. Nó **chưa chứng minh** canonical request hoặc HTTP verifier đúng.

### 4.3. Nhiệm vụ độc lập cho client và server

1. Tự viết signer Java và một signer khác implementation (một SDK khác ngôn ngữ hoặc công cụ kiểm thử độc lập).
2. Dùng **cùng secret giả**, input có UTF-8/Unicode và body JSON chứa khoảng trắng.
3. So từng lớp: body SHA-256 → canonical UTF-8 bytes → MAC bytes → Base64.
4. Chủ động đổi `LF` sang `CRLF`, thêm newline cuối, reserialize JSON và đảo query order.
5. Xác nhận những thay đổi làm signature không khớp **nếu hợp đồng ký raw bytes/ordering**.

**Điều kiện hoàn thành:** có tối thiểu một golden vector chứa expected literal, được xác nhận **không phụ thuộc vào chính signer đang kiểm thử**.

## 5. Chặng 2 — Tích hợp request signing vào Spring Security

Sau khi byte-level contract ổn định, nối verifier với **đường đi HTTP thật**.

~~~text
Ingress → Parser → HMAC verifier → Freshness/nonce → Authentication
       → Authorization → Handler
~~~

### 5.1. Các câu hỏi buộc phải trả lời

- Spring MVC/Servlet hay Spring WebFlux? Body được đọc ở đâu, có thể đọc lại ở handler không?
- HMAC chạy ở gateway, tại service hay cả hai theo hai trust boundaries khác nhau?
- Header nào bắt buộc và được lấy đúng một giá trị? Duplicate được xử lý ra sao?
- Request-target gốc trước gateway rewrite được lấy từ nguồn nào **đáng tin**?
- Route nào bắt buộc authentication; route nào cố ý public?
- Authentication principal/authorities được dựng từ **verified key record** hay từ header người gọi tự khai?
- Lỗi MAC sai, timestamp cũ, nonce replay, store down và thiếu quyền đi qua error handler nào?

### 5.2. Mẫu contract interface, không khóa kiến trúc

~~~java
public interface SignedRequestVerifier {
    VerifiedClient verify(
            SignedRequestView request,
            byte[] exactBodyBytes);
}

public record VerifiedClient(
        String clientId,
        String tenantId,
        java.util.Set<String> grantedAuthorities) {}

// SignedRequestView và lớp exception là phần adapter của ứng dụng.
// Không tạo VerifiedClient trước khi kiểm tra MAC + key policy.
~~~

Tách **HTTP adapter**, **cryptographic verifier**, **key repository**, **replay guard** và **principal factory** giúp kiểm thử từng trust boundary. Interface trên chỉ là định hướng phân rã; cần kiểm tra thêm giới hạn body và cấu hình security chain.

**Bẫy Servlet:** `ContentCachingRequestWrapper` cache bytes được đọc, nhưng không mặc nhiên giúp downstream đọc lại stream sau khi filter đã tiêu thụ. **Bẫy WebFlux:** `Flux<DataBuffer>` có thể chỉ được consume một lần; phải tránh `block()` trên event loop, giới hạn body và quản lý pooled buffers.

### 5.3. Bài kiểm tra tốt nghiệp chặng 2

Tạo hai endpoint fixture:

~~~text
GET  /public/signed-probe    -> requires probe:read
POST /public/signed-admin    -> requires probe:admin
~~~

Một client chỉ có `probe:read`:

| Request | Expected |
|---|---|
| MAC hợp lệ tới `signed-probe` | 2xx theo contract |
| Thiếu hoặc sai MAC tới `signed-probe` | 401 |
| MAC hợp lệ tới `signed-admin` | 403 |
| Query hoặc path được ký bị sửa sau khi ký | 401 nếu vẫn tới protected verifier |
| Route malformed bị proxy từ chối sớm | 400/404 theo policy, không side effect |

Nếu thiếu MAC nhưng handler vẫn chạy, **dừng tại chặng này** và kiểm tra matcher/filter chain, không học tối ưu tiếp.

## 6. Chặng 3 — Replay protection phân tán

HMAC đúng không ngăn một request bị phát lại trong khi chữ ký còn hợp lệ. Bước tiếp theo là làm rõ **freshness + nonce + shared storage**.

### 6.1. Timestamp window và TTL

Giả sử chấp nhận timestamp `T` khi:

\[
now-W \le T \le now+W
\]

với `W = 300 giây` là **giả định của lab**, không phải khuyến nghị mặc định cho mọi hệ thống.

Nếu một request được nhận tại `T-W`, nó còn có thể được chấp nhận cho đến `T+W`. Thời gian replay tiềm năng tối đa là **2W**. Vì vậy:

- TTL cố định từ lúc claim phải **ít nhất 2W cộng biên an toàn** theo clock/store policy; hoặc
- TTL tính từ `T+W-now` cộng biên đủ để entry tồn tại đến khi MAC không còn hợp lệ.

**TTL chỉ bằng W có thể tạo lỗ hổng replay** nếu request đầu tiên đến ở biên tương lai của timestamp.

### 6.2. Atomic claim ở shared store

Với Redis, thao tác ý tưởng là:

~~~text
SET hmac:nonce:<trusted-client-scope>:<hashed-nonce> 1 NX PX <ttl-ms>
~~~

`NX` và TTL cần được áp dụng **nguyên tử**. Không dùng `GET` rồi `SET`, không chỉ lưu nonce trong map của một instance.

**Thứ tự bắt buộc:** verify MAC và key policy → freshness → atomic claim nonce → tạo Authentication → authorization → handler. Có thể reject timestamp/format sớm hơn để tiết kiệm tài nguyên, nhưng **không claim nonce của request có MAC sai**.

### 6.3. Ba test nên viết trước khi triển khai Redis

1. **Same-request replay:** lần đầu hợp lệ, lần hai cùng signature/timestamp/nonce bị từ chối; handler chỉ chạy một lần.
2. **Invalid-MAC does not poison nonce:** request MAC sai với nonce N **không** làm request hợp lệ có cùng N bị từ chối vì “đã claim”.
3. **Two-replica race:** hai request hợp lệ có cùng nonce gửi đồng thời vào hai service instances; chỉ một atomic claim thành công.

Sau đó làm bài test khó hơn: **Redis failover mất entry vừa claim, memory eviction trước TTL và clock lệch giữa replica**. `SET NX PX` chứng minh atomicity của một lệnh trên node đang xử lý, nhưng không tự bảo đảm durability/exactly-once sau mọi dạng failover.

**Phân biệt:** anti-replay ngăn tái sử dụng nonce, không ngăn client gửi **hai request có nonce mới** cùng lệnh tạo thanh toán. API ghi dữ liệu còn cần idempotency key và đối soát kết quả nghiệp vụ.

## 7. Chặng 4 — Key rotation, revoke và algorithm agility

Sau khi kiểm soát nonce, học cách thay key mà không vô hiệu hóa các invariant.

| Trạng thái | Hành vi cần test |
|---|---|
| Key K1 active | MAC dùng K1 được xác minh nếu còn đủ điều kiện |
| K1/K2 cùng active trong overlap | Cả hai hoạt động theo policy nhưng cùng principal/tenant đúng |
| K1 revoked | MAC K1 đúng toán học vẫn bị từ chối trên mọi replica theo giới hạn revoke |
| K2 active | Request ký K2 với nonce mới được chấp nhận |
| Key store unavailable | Không fallback secret hay bypass verifier; fail closed |

### 7.1. Đặt key ID vào đúng vai trò

`X-Key-Id` **chưa phải danh tính đã xác thực**. Nó chỉ giúp server tìm key record. Chỉ sau khi MAC hợp lệ, key còn active và policy được thỏa mãn mới được dựng principal/tenant/authorities từ dữ liệu server sở hữu.

Không thử mọi key đến khi tìm được MAC khớp. Không tin `X-Tenant-Id`, `X-Role` hoặc key metadata từ caller để cấp quyền.

### 7.2. Chuyển signature profile khác với rotate secret

Key rotation có thể giữ nguyên `HmacSHA256`. Signature migration có thể thay:

- MAC primitive, chẳng hạn profile có HMAC-SHA512.
- Canonical version hoặc signed fields.
- Output encoding Base64/Base64URL.
- Key ID format và quy tắc profile negotiation.

Mọi thay đổi có thể phá compatibility đều cần **versioned contract và golden vector**. Trong một migration profile:

~~~text
legacy / v1-allowed → dual-capable → v2-required → v1-retired
~~~

Đây là state do **server policy** quyết định. Khi đã `v2-required`, request V2 MAC sai **không được rơi về V1** dù V1 MAC đúng, và key V1 đã revoke không được “hồi sinh” khi rollback code.

### 7.3. Nhiệm vụ chặng 4

Thiết kế test “MAC đúng nhưng policy cấm” để chứng minh security boundary thực sự tồn tại. Nếu test V1 bị từ chối vì key không tồn tại hoặc timestamp đã hết hạn, test **chưa chứng minh** anti-downgrade.

## 8. Chặng 5 — Gateway, URI và HTTP parser như một phần giao thức

Một request bên ngoài có thể đi qua TLS termination, WAF, reverse proxy và routing layer. Những lớp đó có thể thay path, query, header hoặc body representation.

~~~text
Client signs: POST /public/v1/orders?mode=preview
Gateway sends: POST /orders?mode=preview
Handler: orders.create
~~~

Nếu contract ký **public raw path**, verifier phải có cơ chế đáng tin để xác minh đúng public target. Không dùng `X-Original-URI` do client tự khai để “phục hồi” đường dẫn đã ký. Gateway cần strip/overwrite metadata từ bên ngoài và bảo vệ giao tiếp tới service, hoặc xác minh signature tại gateway rồi chuyển tiếp một assertion được bảo vệ.

### 8.1. Bộ biến thể nên thử

| Input | Cần phát hiện |
|---|---|
| `/orders` và `/orders/` | Trailing-slash alias có cùng policy? |
| `/public//v1/orders` | Double slash bị collapse tại lớp nào? |
| `/orders/%2e%2e/admin` | Dot-segment decode/path traversal |
| `/orders%2Fadmin` | Encoded slash được xem là segment hay separator? |
| `/orders%252Fadmin` | Double decoding qua nhiều hop |
| `a=1&b=2` và `b=2&a=1` | Query order trong raw/canonical mode |
| `role=user&role=admin` | Duplicate parameter semantics |
| `q=hello+world` và `q=hello%20world` | Form encoding khác raw query |
| Header `X-Original-URI` tự khai | Spoofing signed target |
| HTTP/2 `:path` qua HTTP/1.1 | Ngữ nghĩa request target khi chuyển giao thức |

Đừng kỳ vọng mọi path bất thường trả 401. Container/gateway có thể trả **400/404 trước verifier**; điều quan trọng là **không vào protected handler bằng đường dẫn không được bảo vệ**, không xử lý resource khác dữ liệu đã ký.

**Điều kiện hoàn thành:** có test chạy qua **proxy thật hoặc cấu hình tương đương production**, không chỉ gọi verifier với chuỗi path dựng thủ công.

## 9. Chặng 6 — Nâng chất lượng security testing

Các test phải được tổ chức sao cho **mỗi thất bại chỉ chứng minh một điều**.

| Loại test | Điều kiện đã cố định | Điều thay đổi | Kỳ vọng |
|---|---|---|---|
| MAC path binding | Key active, timestamp valid, nonce mới | Signed path A → actual B | MAC mismatch/reject |
| Body integrity | Exact original body, nonce mới | Thay bytes body sau ký | Reject |
| Timestamp freshness | MAC đúng với timestamp test | T nằm ngoài window | 401 freshness |
| Replay | First request đã claim | Gửi lại same nonce/MAC | 401 replay |
| Revocation | MAC đúng với revoked key | Key state active → revoked | 401 theo policy |
| Authorization | MAC đúng, principal xác thực | Thiếu required authority | 403 |
| Store outage | MAC đúng, key/policy hợp lệ | Redis/key store down | 503/fail closed |
| Downgrade | Legacy/V1 MAC hợp lệ | Client state v2-required | 401 |

Một HTTP 401 do nonce đã dùng lại **không chứng minh** URI được ký; một 401 do key revoked **không chứng minh** HMAC primitive đúng; một 403 **không chứng minh** authentication đã chạy nếu security chain cấu hình sai. Hãy dùng **fixed clock, fresh nonce, controlled key states, handler spy** và audit reason trong test harness.

### 9.1. Các mutation test có giá trị cao

Cố tình tạo các bug **chỉ trong môi trường test**:

1. Bỏ path khỏi canonical request.
2. Không kiểm tra MAC nhưng vẫn cấp principal.
3. Claim nonce trước khi verify signature.
4. Dùng Redis `GET` rồi `SET` thay vì atomic claim.
5. Cho phép `legacy` khi client đã `v2-required`.
6. Tin header `X-Original-URI` do client gửi.
7. Catch exception nonce store rồi return success.
8. Bỏ authorization ở một protected route.

Bộ kiểm thử đúng phải **đỏ** ở mỗi mutation. Nếu vẫn xanh, những test đang có chưa bảo vệ được invariant tương ứng.

## 10. Chặng 7 — Observability, hiệu năng và sự cố

HMAC verifier có thể là một phần của **critical path** request:

~~~text
HTTP parsing → body digest → key lookup → MAC verify
             → timestamp/nonce claim → Authentication
             → Authorization → Handler
~~~

Các bước đáng đo gồm key lookup p95/p99, nonce claim latency, input/body sizes, invalid signature rate, replay rejection, 401/403/503 và số protected routes có filter coverage. Không đo “HMAC nhanh” chỉ bằng phép benchmark `Mac.doFinal` trong một JVM rồi suy ra endpoint production sẽ nhanh.

### 10.1. Metric cardinality và privacy

Dùng nhãn hữu hạn:

~~~text
hmac_auth_requests_total{
  route="orders.create",
  profile="v1",
  outcome="rejected",
  reason="signature_invalid"
}
~~~

Không dùng raw nonce, full signature, body, raw query, key ID chưa xác thực, tenant header tự khai hoặc trace ID làm metric labels. Chúng có thể chứa thông tin nhạy cảm và gây cardinality explosion. Log nguyên nhân nội bộ chỉ nên dùng enum đã kiểm soát, correlation ID và cơ chế giới hạn quyền truy cập/retention.

### 10.2. Runbook nhỏ cho từng failure mode

| Dấu hiệu | Hành động điều tra | Điều không được làm |
|---|---|---|
| 401 tăng sau deploy gateway | Kiểm tra canonical public path/query, golden vector | Bỏ signed URI để giảm 401 |
| Timestamp invalid tăng | Kiểm tra UTC/NTP, client clock, queue delay | Nới window không đánh giá replay |
| Replay rejection tăng | Kiểm tra retry/nonce generator và audit | Tắt nonce check |
| Key revoked còn được nhận | Kiểm tra cache invalidation trên mọi replica | Kéo dài key revoked không có phê duyệt |
| Redis không sẵn sàng | Fail closed, khôi phục store, theo dõi 503 | Catch lỗi rồi cho request đi tiếp |
| Authn success nhưng tenant lạ truy cập | Kiểm tra authorization/resource ownership | Coi key ID/client header là đủ quyền |

Khi sự cố ảnh hưởng khách hàng, cần thông báo **dữ kiện đã xác nhận**, tách giả thuyết khỏi kết luận, không gửi secret/full MAC trong email/ticket và không hướng dẫn đối tác tắt xác thực. Với key nghi lộ, dùng kênh **out-of-band** để xác minh người nhận và điều phối revoke/rotate.

## 11. Ba dự án kế tiếp nên làm theo độ khó tăng dần

### Dự án A — Signed Read API (nền tảng)

**Mục tiêu:** một API chỉ đọc, mỗi request phải có MAC đúng với HMAC-V1.

**Sản phẩm:**

- Java client signer dùng secret giả trong test và secret manager khi vận hành.
- Spring MVC hoặc WebFlux verifier thực hiện canonical request rõ ràng.
- Protected route `GET /signed-probe`, không side effect.
- Bộ golden vectors và negative HTTP tests.

**Nghiệm thu:** GET ký đúng được nhận; thiếu/sai MAC, signed path/query sai đều bị từ chối; không có route alias nào bypass filter. Không cần Redis trong giai đoạn này, nhưng phải ghi rõ **chưa có replay protection**.

### Dự án B — Signed Write API có replay protection

**Mục tiêu:** bảo vệ một endpoint tạo resource **giả lập**, chạy ít nhất hai replica.

**Bổ sung:**

- Timestamp + 128-bit nonce (CSPRNG, Base64URL theo profile).
- Redis atomic claim với TTL và scope từ verified identity.
- Business idempotency key độc lập với nonce.
- Key rotation K1/K2 và revoke test.
- Negative tests cho fail-closed, 401/403/503 và no side effect.

**Nghiệm thu:** hai request cùng nonce chạy đồng thời chỉ cho phép một claim; retry với nonce khác nhưng cùng idempotency key không tạo resource trùng; Redis unavailable không làm API bỏ xác thực.

### Dự án C — Production-like HMAC Gateway Lab

**Mục tiêu:** chứng minh hợp đồng đúng qua proxy, nhiều profile/key và một đợt deploy giả lập.

**Bổ sung:**

- Gateway rewrite public path thành internal path.
- Test percent encoding, duplicate headers và forwarded spoofing.
- Client policy `dual-capable → v2-required`; key V1 được revoke.
- Dashboard/alert dựa trên route/profile/reason enums.
- Canary với positive **và negative** probes.
- Tabletop incident: Redis outage hoặc nghi lộ shared secret.

**Nghiệm thu:** không có fallback legacy/V1 trái policy; bypass route bị bắt; fail-closed hoạt động; có bằng chứng rollback không hồi sinh key revoked hoặc xóa nonce history.

> **Quy tắc chọn dự án:** chỉ chuyển sang dự án tiếp theo khi bộ test của dự án trước thực sự **phát hiện được** ít nhất một lỗi được cố ý đưa vào test fixture (ví dụ bỏ HMAC verification hoặc claim nonce trước MAC).

## 12. Lịch học mẫu bốn chặng

Đây là **nhịp triển khai minh họa**, không phải thời lượng cố định hay cam kết thời gian; học chậm hơn để có bằng chứng đúng vẫn tốt hơn tăng tốc bằng cách bỏ kiểm thử.

| Chặng | Trọng tâm | Đầu ra có thể review | Điều kiện chuyển chặng |
|---|---|---|---|
| **1. Contract** | HMAC primitive, encoding, raw URI/body | Đặc tả HMAC-V1 + golden vector độc lập | Bytes/MAC khớp giữa hai implementation |
| **2. Integration** | Spring Security, route coverage, authn/authz | Signed read API + HTTP tests | Không có protected-route bypass |
| **3. Distributed** | Timestamp, nonce Redis, rotation | Signed write API + race/TTL/revoke tests | Replay, revoke, store failures đều fail closed |
| **4. Operations** | Gateway, canary, telemetry, incident | E2E gateway lab + runbook/ADR | Security gates đạt trên các replica/vùng đã test |

Trong mỗi chặng nên có vòng:

~~~text
Write contract → Implement minimal slice → Create negative test
→ Inject one deliberate bug → Verify test detects bug
→ Fix → Record evidence → Review before expanding scope
~~~

Đừng dùng tốc độ hoàn thành tính năng làm tiêu chí duy nhất. Với phần mềm xác thực, **khả năng chứng minh đúng khi request không hợp lệ** quan trọng không kém happy path.

## 13. Mẫu Definition of Done cho bài thực hành cuối

Một hệ thống lab có thể được xem là đạt khi:

### 13.1. Cryptographic contract

- [ ] Secret là bytes độc lập, được quản lý bằng nguồn tin cậy, không hardcode production credential.
- [ ] Profile/version, canonical charset/separator, signed fields, body digest và wire MAC encoding được mô tả.
- [ ] Có golden vectors **literal** độc lập, bao gồm UTF-8, query và body bytes.
- [ ] Signed method/path/query/header/body theo hợp đồng bị thay đổi → MAC mismatch.
- [ ] Signature parsing có giới hạn, reject malformed/duplicate/overlong headers.

### 13.2. Authentication và authorization

- [ ] Key lookup không cấp danh tính trước MAC; revoked/expired/profile-disallowed key bị từ chối.
- [ ] HTTP security chain bảo vệ mọi protected route, bao gồm alias/method tương ứng.
- [ ] Principal/authorities lấy từ verified key record, không từ header tự khai.
- [ ] HMAC đúng nhưng thiếu quyền → 403; không side effect.
- [ ] Key/nonce/policy store unavailable → fail closed; không fallback sang scheme cũ.

### 13.3. Replay và distributed state

- [ ] Timestamp có window/format rõ, nonce được ký và sinh bằng CSPRNG.
- [ ] Nonce chỉ được claim sau khi MAC hợp lệ; claim atomic trên shared store.
- [ ] TTL bao phủ toàn bộ thời gian signed timestamp còn có thể được chấp nhận.
- [ ] Hai replica không cùng claim một nonce; có kiểm tra failover/eviction assumptions.
- [ ] Nonce scope đúng client/tenant sau xác thực, hoạt động xuyên key rotation theo policy.
- [ ] Idempotency nghiệp vụ được kiểm thử riêng.

### 13.4. Vận hành

- [ ] Golden vector và signed request đi qua gateway thật, kể cả khi có rewrite.
- [ ] Forwarded header giả không thay được trusted public target.
- [ ] Canary đo positive/negative outcomes trên đúng release/region.
- [ ] Metrics/log không lộ secret/full MAC/nonce/PII và không dùng unbounded labels.
- [ ] Có runbook revoke/rotate, replay incident, store outage và security-safe rollback.

**Hard stop:** chỉ cần **một** request thiếu MAC đi tới protected handler, key revoked được chấp nhận ngoài policy, nonce replay gây side effect hoặc thiếu quyền vẫn được xử lý thì bài thực hành **chưa đạt**, dù những test khác xanh.

## 14. Bài tập tổng hợp: viết acceptance matrix trước code

Giả sử:

- Client A có key K1 và K2 cùng liên kết với verified principal A.
- K1 dùng profile V1, K2 dùng V2; policy A hiện là `v2-required`.
- Request `POST /orders` đã ký với nonce N1, còn trong timestamp window.
- Redis nonce store dùng chung giữa hai replica.
- Client A có quyền `orders:read`, **không** có `orders:create`.

Hãy dự đoán:

| Tình huống | Dự đoán đúng |
|---|---|
| HMAC V1 với K1 đúng, nonce mới | **401** theo policy v2-required |
| HMAC V2 với K2 đúng, nonce mới, gọi `POST /orders` | **403** thiếu quyền |
| HMAC V2 với K2 đúng, nonce N1 đã claim trước | **401** replay nếu kiểm tra nonce trước authorization |
| HMAC V2 hợp lệ nhưng Redis không thể claim | **503** fail closed theo HTTP contract ví dụ |
| Dùng lại MAC V2, đổi path sang `/admin` | **MAC mismatch** nếu path được ký; có thể bị reject routing sớm |
| HMAC V2 hợp lệ, có quyền write, nhưng K2 vừa revoked | **401** theo key lifecycle |
| Caller gửi `X-Role: admin` nhưng key record chỉ có read | **Không nâng quyền**; authorization vẫn 403 |

**Lưu ý về thứ tự:** nếu một implementation đặt authorization trước replay claim, response cho request thiếu quyền có thể khác trong một số kết hợp. Bảng trên mô tả pipeline **verify MAC → freshness/nonce → Authentication → authorization**; cần đặt expected tests theo contract cụ thể, nhưng **không bao giờ cho handler chạy trước các kiểm soát bắt buộc**.

### 14.1. Câu hỏi thiết kế mở

Nếu chuyển replay scope từ `keyId + nonce` sang `verifiedClientId + nonce` khi đang rotate K1/K2, bạn sẽ:

1. Giữ khả năng nhận diện nonces đã claim trong namespace cũ đến khi signature hết hạn như thế nào?
2. Tránh chấp nhận replay xuyên hai namespace trong giai đoạn chuyển đổi thế nào?
3. Kiểm tra đồng thời tại hai replica/region bằng fixture nào?
4. Đánh giá tác động lên Redis memory, TTL, failover và client retry ra sao?

Không có một đáp án cấu hình đúng cho mọi hệ thống. Đáp án tốt phải nêu **threat model, invariant, migration strategy và bằng chứng test**, không chỉ chỉ ra một lệnh Redis.

## 15. Khi nào nên học công nghệ khác ngoài HMAC riêng của ứng dụng?

HMAC request signing là một thiết kế hữu ích trong các mô hình **server-to-server** hoặc client đã có shared secret. Nó **không tự thay thế** TLS, authorization, quản lý credential hoặc các cơ chế danh tính khác.

| Hướng tiếp theo | Khi nên học | Câu hỏi cần trả lời |
|---|---|---|
| **HTTP Message Signatures** | Muốn nghiên cứu cơ chế ký HTTP có cấu trúc/khả năng tương tác | Signature base, covered components, key discovery và profile khác HMAC tự chế thế nào? |
| **OAuth 2.0 / OpenID Connect** | Cần delegated access, user identity hoặc scopes | Token, issuer/audience, delegation khác shared-secret request signing thế nào? |
| **mTLS và workload identity** | Service-to-service, nhận dạng hai chiều và máy khách được quản lý | Identity của kết nối có thay thế bảo vệ nội dung request qua nhiều proxy không? |
| **API gateway security** | Có nhiều reverse proxies, edge auth và zero-trust boundaries | Ai xác minh, ai có quyền cấp assertion cho backend? |
| **KMS/HSM, secret management** | Nhiều keys/tenants, audit, revoke, rotation | Secret lifetime, access scope, outage và key hierarchy ra sao? |
| **Distributed consistency** | Replay state qua nhiều replica/region | Atomicity, replication lag, failover và durability ảnh hưởng replay thế nào? |
| **Threat modeling / application security** | API xử lý dữ liệu nhạy cảm hoặc tài chính | Credential compromise, SSRF, request smuggling, parser ambiguity và authz failures được kiểm thử ra sao? |

Một số tài liệu nền tảng hữu ích để đọc tiếp là **RFC 2104** (HMAC), **RFC 4231** (test vectors), **RFC 9110** (HTTP semantics), **RFC 3986** (URI), **RFC 9421** (HTTP Message Signatures) và **RFC 9530** (HTTP Digest Fields). Các tài liệu này **không tự định nghĩa** cùng một canonical request cho giao thức HMAC-V1 tự xây của bài lab; cần phân biệt chuẩn mô tả cơ chế chung với hợp đồng ứng dụng.

### 15.1. So sánh kiến trúc trước khi chọn công nghệ

Không chọn HMAC chỉ vì “đơn giản hơn OAuth” hoặc chọn OAuth chỉ vì “phổ biến hơn”. Hãy viết một bảng quyết định:

- Caller là con người, mobile app, browser, workload hay server được kiểm soát?
- Ai giữ secret và có thể bảo vệ nó? Có cần secret riêng cho từng client/tenant?
- Cần **delegated authorization** hay chỉ authentication của một đối tác?
- Có proxy trung gian biến đổi request không? Cần integrity end-to-end của method/path/body đến mức nào?
- Cần replay protection, business idempotency, key rotation và incident response ở mức nào?
- Có chuẩn/SDK đáng tin nào đáp ứng yêu cầu mà không phải tự thiết kế canonicalization không?

HMAC request signing có thể phối hợp với OAuth/mTLS theo threat model, nhưng **nhiều cơ chế không mặc nhiên an toàn hơn** nếu trust boundaries và key ownership không được mô tả.

## 16. Mẫu nhật ký học tập kỹ thuật cho mỗi chặng

Để biến bài tập thành năng lực có thể review, mỗi lần hoàn thành một thay đổi hãy ghi:

~~~yaml
learning_stage: distributed-replay
artifact: signed-orders-lab
environment: staging
signature_profile: HMAC-V1
assumptions:
  timestamp_window_seconds: 300
  nonce_scope: verified-client
  nonce_store: shared-redis
checks:
  valid_signed_request: PASS
  invalid_mac_rejected: PASS
  nonce_not_claimed_on_invalid_mac: PASS
  two_replica_atomic_claim: PASS
  revoked_key_rejected: PASS
  insufficient_authority_403: PASS
  store_unavailable_fail_closed: PASS
  no_side_effect_on_rejection: PASS
evidence:
  - golden-vector-test-report
  - integration-test-report
  - gateway-probe-result
decision: READY_FOR_REVIEW
~~~

**Đây là ví dụ định dạng báo cáo, không phải kết quả test đã chạy.** Khi thực hành thật, mỗi dòng `PASS` phải có bằng chứng từ test run, phiên bản code/config, thời điểm và môi trường; không dùng một bảng tự điền để thay kiểm thử. Không nhúng secret, full signature, raw body chứa dữ liệu thật hoặc nonce production vào nhật ký.

## 17. Checklist tự định hướng: hôm nay nên bắt đầu ở đâu?

Nếu mới xong phần lý thuyết, hãy làm **chặng 1**: viết một contract chỉ một trang và kiểm tra một HMAC vector độc lập. Nếu đã có REST API và filter hoạt động, hãy thêm **negative integration tests** cho thiếu/sai MAC và quyền bị từ chối. Nếu test đã xanh trong một JVM nhưng deployment có nhiều pod, tiếp theo là **Redis atomic nonce test hai replica** và key revoke cache invalidation.

Nếu API đã dùng thật qua gateway, ưu tiên test **trusted public path**, các biến thể percent-encoding và route coverage. Nếu đã vượt các gate kỹ thuật, bước học tiếp theo đáng giá nhất thường là **vận hành có kiểm chứng**: dashboard đúng cardinality, canary có negative probes, incident communications và rollback không làm giảm bảo mật.

### 17.1. Câu hỏi chốt trước khi tự nhận “đã làm chủ HMAC”

- Khi secret bị lộ, bạn có thể revoke đúng key mà không làm mất quyền kiểm soát cả tenant không?
- Khi Redis lỗi, có đường code nào cho request bỏ qua nonce không?
- Khi proxy rewrite path, bạn biết **byte nào được ký** và **handler nào sẽ chạy** không?
- Khi client nâng V1 → V2, có test chứng minh downgrade bị chặn không?
- Khi HMAC hợp lệ nhưng caller thiếu quyền, có assertion 403 và không side effect không?
- Khi hai request đồng thời tới hai replica, có bằng chứng một nonce chỉ được claim một lần không?
- Khi deployment mới làm 401 giảm bất thường, bạn có kiểm tra liệu authentication filter bị bỏ qua không?

**Nếu chưa trả lời được bằng test, trace và policy rõ ràng, đó chính là chủ đề học tiếp theo.**

## 18. Kết luận

Sau HMAC request authentication, bước học hiệu quả nhất là chuyển từ **thuộc API mật mã** sang **chứng minh những invariant bảo mật qua toàn bộ vòng đời HTTP request**. Hãy tiến dần từ **bytes và golden vectors → Spring Security → replay/key lifecycle → proxy/gateway → security testing → operations/incident response**; mỗi chặng để lại một artifact có thể review.

Một hệ thống tốt không chỉ ký đúng request, mà còn **không chấp nhận request bị sửa, bị phát lại, dùng key đã thu hồi, sai profile hoặc thiếu quyền**, ngay cả khi backend trải qua rollout, failover hay migration. Khi bạn có thể **giải thích, triển khai, chủ động phá thử bằng test và khôi phục an toàn** những bảo đảm đó, kiến thức HMAC đã trở thành năng lực thiết kế và vận hành một cơ chế xác thực thực tế.
