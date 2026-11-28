# Chọn error semantics trong thiết kế hệ thống xác thực HMAC HTTP

## 1. Tại sao error semantics là quyết định kiến trúc bảo mật?

Trong module `SECURITY_AUTHENTICATION_HMAC_REQUEST_AUTHENTICATION`, client gửi HTTP request với chữ ký HMAC được tính bằng shared secret trên **canonical request**. Hợp đồng ký quy định method, URI/query, signed headers và/hoặc body digest, thường gắn thêm key ID, timestamp và nonce. Server phải xác minh đúng secret, chống replay, quản lý key rotation, xử lý proxy/gateway và phân biệt **authentication** với **authorization**.

Một implementation có thể tính HMAC rất đúng nhưng vẫn có lỗi hệ thống nếu mọi exception đều trả 401, hoặc trả quá nhiều chi tiết như `KEY_EXISTS_BUT_NONCE_USED` cho client chưa xác thực. Cùng một status 401 có thể xuất hiện vì MAC sai, credential đã revoke, timestamp quá cũ, nonce replay hay server không đọc được Redis; nhưng **những nguyên nhân này không mang cùng ý nghĩa** và không nên có cùng hành vi retry/alert/incident.

**Error semantics** là quyết định về:

- **Bản chất** của failure: cú pháp HTTP, authentication, authorization, anti-replay, rate limiting, dependency hay nghiệp vụ.
- **HTTP status** và security challenge phù hợp.
- **Public error body/code** được phép để lộ cho caller.
- **Internal reason** đủ chính xác để vận hành/test nhưng không trở thành oracle.
- **Retry policy**: caller nên sửa signature, làm mới nonce, chờ hạ tầng hay không retry?
- **Side-effect invariants**: khi từ chối, có tạo principal, consume nonce hoặc chạy business không?
- **Tính nhất quán** qua gateway, Spring MVC, WebFlux, các region và các phiên bản signing suite.

Ví dụ:

~~~http
POST /api/hmac/payments HTTP/1.1
Host: api.example.test
Content-Type: application/json
X-Client-Id: partner-a
X-Key-Id: partner-a-prod-k004
X-Signing-Suite: hmac-v1-sha256
X-Timestamp: 2026-11-28T04:00:00Z
X-Nonce: 84a9b6c3-764e-40e3-a9b2-154fdb154f79
X-Signature: <base64-mac>

{"paymentId":"pay-401","amount":250000}
~~~

Nếu request này được gửi lại **nguyên vẹn**, MAC vẫn hợp lệ về toán học, nhưng nonce đã được claim nên authentication phải bị chặn. Nếu Redis không khả dụng, server **không biết** request đã được dùng hay chưa; đây là lỗi hạ tầng, không phải một `replay` đã được chứng minh. Nếu HMAC/nonce hợp lệ nhưng `partner-a` không có grant tạo payment của tenant-b thì đó là **authorization failure**.

### Kết quả học tập

Sau bài **Chọn error semantics** thuộc chương **Thiết kế HMAC system**, người học có thể:

1. Phân loại từng failure thành đúng tầng xử lý.
2. Xây contract public ổn định mà không tiết lộ trạng thái key/nonce/secret.
3. Quyết định cách dùng 400, 401, 403/404, 409, 413, 415, 429, 503 và các status liên quan.
4. Phân biệt `INVALID_SIGNATURE`, `REPLAY_DETECTED` và `REPLAY_STORE_UNAVAILABLE` trong telemetry.
5. Định nghĩa retry/idempotency mà không mở bypass chống replay.
6. Viết mapping cho Spring Security Servlet và WebFlux.
7. Thiết kế bộ test kiểm tra status, body, challenge, nonce state, principal và business effects.

## 2. Error semantics phải thỏa đồng thời năm mục tiêu

| Mục tiêu | Ý nghĩa | Lỗi thường gặp |
| --- | --- | --- |
| **Security** | Không leak secret, key existence, nonce/replay state | Trả `UNKNOWN_KEY` khác biệt công khai với `BAD_MAC` |
| **HTTP correctness** | Status thể hiện đúng tầng failure | Dùng 403 cho mọi chữ ký sai, dùng 401 cho Redis outage |
| **Client usability** | Caller biết cách sửa request hoặc retry an toàn | 400 cho mọi thứ, thiếu documentation |
| **Operations** | Có đủ reason/trace nội bộ để khắc phục | Chỉ log “unauthorized” mà không biết lỗi là gì |
| **Consistency** | Gateway/backend/region cùng contract | Gateway đổi 401 thành 500 hoặc trả body chứa secret |

Một thiết kế tốt dùng **hai kênh thông tin**:

**Kênh công khai (public contract):** ít phân loại, ổn định, không xác nhận sự tồn tại của key/tenant/nonce. Ví dụ `AUTHENTICATION_FAILED`, `REQUEST_INVALID`, `AUTHENTICATION_UNAVAILABLE`.

**Kênh nội bộ có kiểm soát:** các `internal reason` như `SIGNATURE_MISMATCH`, `TIMESTAMP_OUT_OF_WINDOW`, `REPLAY_DETECTED`, `CREDENTIAL_REVOKED`, `REPLAY_STORE_UNKNOWN`. Kênh này phục vụ audit, counters và test fixture; không tự động đưa toàn bộ reason lên HTTP response.

Không có một ánh xạ status duy nhất phù hợp mọi API: nếu hợp đồng public có yêu cầu tương thích cũ hoặc các route dùng authentication schemes khác, cần chọn mapping nhất quán **từng API boundary**. Những lựa chọn sau là **profile minh họa có lý do**, không phải chuẩn duy nhất cho HMAC tự thiết kế.

## 3. Đặt lỗi vào đúng bước của authentication pipeline

~~~mermaid
flowchart TD
    A["Ingress HTTP request"] --> B{"Route bảo vệ? HTTP framing và size hợp lệ?"}
    B -->|Framing sai| C["400; không vào verifier"]
    B -->|Body quá lớn| D["413; giới hạn tài nguyên"]
    B -->|Đúng| E["Strict HMAC envelope parse"]
    E -->|Sai cú pháp| F["400 hoặc generic 401 theo policy"]
    E -->|Đúng| G["Exact key ID + credential state + suite policy"]
    G -->|Không hợp lệ| H["Generic 401; không leak key state"]
    G -->|Store unavailable| I["503; fail closed"]
    G -->|Cho phép| J["Canonical bytes + HMAC compare"]
    J -->|MAC sai| H
    J -->|MAC đúng| K["Timestamp window / nonce format"]
    K -->|Không hợp lệ| H
    K -->|Hợp lệ| L["Atomic nonce claim sau MAC"]
    L -->|ALREADY_USED| H
    L -->|UNKNOWN/timeout| I
    L -->|FIRST_USE| M["Create trusted principal"]
    M --> N{"Authorization tenant/action/resource"}
    N -->|Deny| O["403 hoặc 404 theo resource-hiding policy"]
    N -->|Allow| P["Business validation + idempotency"]
    P -->|Conflict| Q["409 theo contract"]
    P -->|Pass| R["Execute business; return domain result"]
~~~

Mỗi nhánh cần **internal reason**, nhưng không nhất thiết dùng public status khác nhau. Lưu ý pipeline có thể kiểm tra timestamp format/window **trước MAC** để từ chối sớm malformed/stale input; tuy nhiên **không claim nonce trước khi MAC đúng**, nhằm chống nonce poisoning. Thứ tự thực tế ảnh hưởng cả latency, resource cost và oracle risk; phải đặc tả rõ.

### Bất biến không được vi phạm

- Chưa có **MAC hợp lệ và nonce first-use** thì không được tạo principal đã xác thực.
- Replay store `UNKNOWN` không được biến thành `FIRST_USE`, dù muốn tăng availability.
- Authorization không tự động pass chỉ vì HMAC đúng.
- Lỗi ở protected route không được làm request rơi qua một route/controller **không có security filter**.
- Không tạo side effect nghiệp vụ khi authentication hoặc authorization chưa hoàn thành.
- Một failure không được tự động thử key ID hoặc signing suite khác để “cứu” request.

## 4. Taxonomy nội bộ: đừng gom mọi lỗi thành BAD_CREDENTIALS

Một enum phân loại nội bộ có thể theo các nhóm sau:

| Nhóm | Ví dụ internal reason | Tầng tạo ra |
| --- | --- | --- |
| `TRANSPORT_PARSE` | `INVALID_HTTP_FRAMING`, `DUPLICATE_SIGNED_HEADER` | Gateway/HTTP adapter |
| `REQUEST_LIMIT` | `BODY_TOO_LARGE`, `HEADER_LIMIT_EXCEEDED` | Ingress/body capture |
| `AUTH_ENVELOPE` | `MISSING_SIGNATURE`, `INVALID_BASE64`, `UNSUPPORTED_SUITE` | HMAC parser |
| `CREDENTIAL_POLICY` | `KEY_NOT_FOUND`, `KEY_DISABLED`, `KEY_REVOKED` | Registry/policy |
| `CRYPTO_VERIFY` | `SIGNATURE_MISMATCH`, `CANONICAL_CONTRACT_MISMATCH` | MAC verifier/conformance |
| `FRESHNESS` | `TIMESTAMP_MALFORMED`, `TIMESTAMP_OUT_OF_WINDOW` | Clock validator |
| `REPLAY` | `REPLAY_DETECTED` | Atomic nonce store: ALREADY_USED |
| `AUTH_DEPENDENCY` | `CREDENTIAL_STORE_UNAVAILABLE`, `REPLAY_STORE_UNKNOWN` | Registry/Redis/HSM |
| `AUTHORIZATION` | `INSUFFICIENT_SCOPE`, `TENANT_DENIED`, `RESOURCE_HIDDEN` | Authorization layer |
| `RATE_LIMIT` | `RATE_LIMIT_EXCEEDED` | Admission/rate limiter |
| `DOMAIN` | `IDEMPOTENCY_PAYLOAD_CONFLICT`, `VALIDATION_FAILED` | Business service |
| `SERVER_ERROR` | `UNEXPECTED_INTERNAL_ERROR` | Application/runtime |

**Không đồng nhất `CANONICAL_CONTRACT_MISMATCH` với thông tin chắc chắn server có được từ request.** Một server chỉ thấy MAC mismatch thường **không biết** client ký path, body hay signed headers sai ở đâu. Tên reason chi tiết chỉ nên xuất hiện khi test harness hoặc diagnostic đáng tin cung cấp bằng chứng byte-level.

### Bốn trạng thái tối thiểu cho replay claim

~~~text
FIRST_USE         -> Có thể đi tiếp authz.
ALREADY_USED      -> Authentication reject, internal REPLAY_DETECTED.
UNKNOWN           -> Dependency failure, fail closed.
NOT_EXECUTED      -> Bỏ qua claim vì MAC/credential/timestamp sai.
~~~

`NOT_EXECUTED` quan trọng để test phát hiện nonce poisoning: request có MAC sai không được chạm replay state. Nếu chỉ log `401`, không biết nonce đã bị claim sai trước đó hay chưa.

## 5. Bảng quyết định HTTP status — một policy tham khảo

| HTTP | Khi nào phù hợp trong HMAC API | Không được nhầm với |
| --- | --- | --- |
| **400 Bad Request** | Framing, duplicated headers, envelope grammar/malformed request theo contract | Không mặc định mọi MAC sai đều 400 |
| **401 Unauthorized** | Thiếu/không hợp lệ authentication evidence: MAC sai, key không eligible, timestamp sai, nonce replay | Không dùng cho server mất Redis/vault |
| **403 Forbidden** | Principal đã authenticated nhưng không có quyền action/tenant/resource | Không dùng cho key revoked/MAC sai |
| **404 Not Found** | Resource không tồn tại hoặc được cố ý che existence theo access policy | Không biến mọi authn failure thành 404 |
| **409 Conflict** | Business idempotency key được dùng lại cho payload/principal binding khác | Không coi replay nonce là business conflict |
| **413 Content Too Large** | Body vượt giới hạn cho phép trước khi verify | Không hash body bị cắt rồi authenticate |
| **415 Unsupported Media Type** | Route yêu cầu content type không được hỗ trợ | Không coi MAC mismatch là 415 |
| **422 Unprocessable Content** | Domain validation thất bại sau khi request đã được hiểu | Không gán cho chữ ký sai |
| **429 Too Many Requests** | Rate/quota limit từ admission policy | Không dùng thay replay-store outage |
| **500 Internal Server Error** | Bug không dự kiến; không leak stack/secret | Không gửi chi tiết expected MAC |
| **502/504** | Gateway nhận lỗi upstream hoặc timeout ở boundary thích hợp | Không dùng để báo sai secret |
| **503 Service Unavailable** | Auth dependency unavailable/unknown; phải fail closed | Không dùng để cho phép unsigned fallback |

Một status không thay thế **hợp đồng định dạng response**. Nếu client cần biết vì sao 503 có thể retry an toàn còn 401 nên sửa credentials/signing, hãy định nghĩa public code và retry guidance không lộ dữ liệu nhạy cảm.

**Lưu ý 401:** theo HTTP semantics, 401 gắn với authentication challenge và server nên gửi header `WWW-Authenticate` phù hợp. HMAC tự thiết kế không có một challenge mặc định chung cho mọi hệ thống; muốn dùng `HMAC realm="api"` phải **định nghĩa chính xác scheme** và cách client phản ứng. Không sao chép challenge giả làm chuẩn được Spring Security tự hỗ trợ.

## 6. Public response tối giản, internal reason giàu ngữ nghĩa

Một response `401` an toàn có thể như sau **nếu API đã công bố scheme HMAC tương ứng**:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: HMAC realm="api"
Content-Type: application/problem+json
Cache-Control: no-store

{
  "type": "about:blank",
  "title": "Unauthorized",
  "status": 401,
  "detail": "Authentication is required or invalid.",
  "code": "AUTHENTICATION_FAILED",
  "requestId": "req-57a2"
}
~~~

Nếu API có nhiều schemes hoặc cần challenge khác, điều chỉnh `WWW-Authenticate` theo tài liệu authentication của **chính API đó**. Ví dụ này là **custom HMAC contract**, không phải endpoint/challenge chuẩn có sẵn.

Server có thể ghi **audit nội bộ**, dùng correlation ID đã sanitize:

~~~json
{
  "event": "HMAC_AUTHENTICATION_FAILED",
  "reason": "REPLAY_DETECTED",
  "route": "payments_create",
  "credentialRevision": "rev-17",
  "requestId": "req-57a2",
  "outcome": "REJECTED"
}
~~~

Đây là metadata minh họa; không log secret, raw signature/body/canonical bytes. Ngay cả `credentialRevision` phải được kiểm soát quyền truy cập, retention và mức độ cần thiết. Không đưa raw key ID/tenant/client làm Prometheus labels.

### Ví dụ các thông tin công khai nên tránh

~~~json
{
  "error": "NONCE_USED_FOR_EXISTING_KEY",
  "keyId": "partner-a-prod-k004",
  "expectedSignature": "SECRET-DERIVED-MAC",
  "serverCanonicalBytes": "POST\n...",
  "serverClock": "2026-11-28T04:00:00.123456Z"
}
~~~

Một response như vậy có thể hỗ trợ reconnaissance: xác nhận key tồn tại, nonce từng dùng, thuật toán/contract đang áp dụng, rồi giúp attacker chỉnh request. **Không trả expected MAC, secret, full canonical bytes, replay namespace, credential state hoặc untrusted full path**.

Báo `serverClock` chi tiết trên lỗi authn cũng nên tránh nếu không có threat model và cơ chế clock sync thích hợp. Client đã có tài liệu timestamp window/signer SDK; không cần dùng public 401 làm kênh debug nhạy cảm.

## 7. Chống credential oracle và nonce oracle

Một `oracle` tồn tại khi attacker có thể suy ra thông tin không được phép từ response, status, body, headers hoặc timing.

Ví dụ phân loại sai:

| Input | Response thiếu an toàn | Rủi ro |
| --- | --- | --- |
| Key ID chưa tồn tại | `404 UNKNOWN_KEY` | Liệt kê key IDs |
| Key ID tồn tại nhưng MAC sai | `401 BAD_SIGNATURE` | So sánh xác nhận key tồn tại |
| Key ID đã revoke | `403 REVOKED_KEY` | Lộ key lifecycle |
| MAC hợp lệ nhưng nonce đã dùng | `409 NONCE_EXISTS` | Lộ replay state ở public API |
| Key lookup lỗi | `401 BAD_KEY` | Che incident hạ tầng và gây retry vô ích |

Một profile có thể trả **public 401 AUTHENTICATION_FAILED** cho missing/unknown/revoked key, MAC mismatch, timestamp invalid/out-of-window và replay. Internal reason vẫn phân biệt để điều tra.

**Nuance:** nếu API đã cho **authenticated client** biết một số thông tin key lifecycle qua management API có authorization, có thể cung cấp chi tiết ở **kênh quản trị riêng**; không đồng nghĩa public HMAC-protected endpoint được phép tiết lộ chi tiết đó.

### Timing side channel

Trả chung 401 chưa chắc làm mọi trường hợp không thể phân biệt. Một unknown key có thể return sớm trong khi known key chạy HMAC, body hash và Redis; attacker đo latency thống kê có thể suy ra state.

Các biện pháp tùy threat model:

- Giữ response shape/status nhất quán giữa các lỗi credential có tính nhạy cảm.
- Giới hạn rate, body size và request budget.
- So sánh MAC byte bằng API timing-resistant phù hợp như `MessageDigest.isEqual`; không tuyên bố **toàn pipeline** constant-time.
- Không thiết kế fallback thử nhiều keys/algorithms để “cân bằng timing”.
- Đánh giá thời gian xử lý/khả năng enumeration ở môi trường kiểm thử.
- Đối với unknown key, cân nhắc công việc giả lập có kiểm soát **nếu threat model cần**, nhưng phải đảm bảo không tạo DoS hoặc dùng secret mặc định làm credential thật.

Không có guarantee constant-time cho toàn HTTP stack; mục tiêu là giảm leakage trong giới hạn khả thi và giám sát probing.

## 8. 401: nhận diện failure authentication mà không đưa hướng dẫn vượt rào

Trong mô hình HMAC có state, các trường hợp sau thường đều trả 401 chung:

- Thiếu credential/signature trên route bắt buộc HMAC.
- Signature encoding invalid, signature length sai theo suite.
- Key ID không có trong registry, không ACTIVE, expired hoặc revoked.
- Suite ID/key version không được phép cho credential/route.
- MAC không khớp canonical bytes hoặc secret exact key ID.
- Timestamp ngoài cửa sổ hoặc format sai thuộc authentication proof.
- Nonce không đúng grammar hoặc đã được claim.
- Client/credential bị disabled trước khi tạo principal.

**Không** diễn giải mọi 401 là cùng nguyên nhân trong SDK. Client nên biết rằng 401 nghĩa là **không có authenticated identity**; cách xử lý an toàn là kiểm tra cấu hình signer/key, đồng hồ, nonce generation và contract theo đường debug được cấp quyền.

Một SDK **không được tự đổi HMAC-SHA512→HMAC-SHA256**, thử key cũ, tắt body hashing hay bỏ nonce chỉ vì nhận 401. Đó là algorithm/key downgrade.

### 401 không nên phát sinh sau khi đã tạo principal

Nếu request HMAC valid, nonce first-use đã claim và principal đã được xác thực, sau đó thiếu `SCOPE_PAYMENT_CREATE`, trả 403 (hoặc 404 theo resource-hiding policy), không đổi thành 401 để khiến caller retry chữ ký mới vô ích.

## 9. Timestamp/freshness lỗi là authentication failure, không phải replay đã chứng minh

Với một profile chấp nhận timestamp trong cửa sổ đối xứng:

\[
t_{\mathrm{server}}-W \le t_{\mathrm{signed}}
\le t_{\mathrm{server}}+W
\]

Ví dụ `W=5 phút`:

| Signed timestamp, Clock=04:00:00Z | Reason nội bộ | Public |
| --- | --- | --- |
| 03:54:59Z | `TIMESTAMP_OUT_OF_WINDOW` | 401 chung |
| 03:55:00Z | Còn hợp lệ (biên inclusive) | Tiếp tục verify |
| 04:00:00Z | Còn hợp lệ | Tiếp tục verify |
| 04:05:00Z | Còn hợp lệ (biên inclusive) | Tiếp tục verify |
| 04:05:01Z | `TIMESTAMP_OUT_OF_WINDOW` | 401 chung |
| Sai format/time zone theo contract | `TIMESTAMP_MALFORMED` | 401 chung |

Đây là **một chính sách minh họa**; hợp đồng có thể chỉ cho timestamp quá khứ hoặc định nghĩa biên khác. Test phải dùng `Clock.fixed`, không dựa vào giờ thật cho golden fixtures.

Nếu request cũ bị 401 **vì timestamp expired**, không thể kết luận nonce guard chống replay đang hoạt động. Cần test phát lại **trong khi timestamp còn hợp lệ**, quan sát `REPLAY_DETECTED` nội bộ.

### Retry của client khi clock skew

Không nên cho client dựa vào response 401 để suy đoán chính xác server clock, rồi tự liên tục ký lại với offset tăng dần. Hướng dẫn đồng bộ NTP/UTC và cung cấp signer SDK có validation; troubleshooting chi tiết có thể qua support/admin có xác thực.

Nếu client retry một request vì chỉnh clock, phải tạo **nonce mới** và signature mới, kiểm soát business idempotency. Không tái sử dụng nonce/signature cũ hoặc sửa timestamp mà giữ chữ ký.

## 10. Replay: khi nào 401, khi nào 409, khi nào 503?

Ba tình huống trông giống nhau ở client nhưng khác tầng:

| Tình huống | Bằng chứng server có | Kết luận | Public gợi ý |
| --- | --- | --- | --- |
| Same signed request, nonce đã claim | MAC đúng, Redis trả `ALREADY_USED` | **Authentication replay** | 401 chung |
| Redis trả timeout sau claim request | Không rõ nonce đã được ghi chưa | **Authentication unavailable** | 503 |
| Client retry bằng nonce mới nhưng dùng lại idempotency key với payload khác | Authentication mới đã pass, business key conflict | **Business conflict** | 409 |

**Không** dùng 409 chỉ vì nonce đã được sử dụng. Nonce là chống replay của bằng chứng authentication, không phải resource conflict theo idempotency semantics. Ngược lại, request có nonce mới và HMAC đúng mà trùng business key có thể nhận business result cache hoặc 409 **sau** khi đã vượt authentication và authorization.

### TTL và status khi nonce hết hạn

Với timestamp window ±W, record nonce phải tồn tại ít nhất tới khi bằng chứng không còn được chấp nhận. Nếu TTL tính từ thời điểm claim, cấu hình bảo thủ là:

\[
TTL_{\mathrm{nonce}} \ge 2W+\varepsilon
\]

với margin `ε` cho clock skew và timing precision đã tính toán. Với W=5 phút, một cấu hình ví dụ là 11 phút; **không phải chuẩn áp dụng mọi API**.

Nếu record bị evict sớm, server có thể xem replay như first-use. Đây là **security violation**, không phải một lỗi client có thể giải bằng 409. Cần fault injection/retention tests.

## 11. Dependency failure: trả 503 và không giả vờ biết lỗi chữ ký

Nếu server cần đọc credential registry, secret manager/KMS/HSM hoặc shared replay store để xác thực, các dependency này trở thành **thành phần của security boundary**. Khi chúng lỗi:

- Không được coi “không tìm thấy key” nếu registry thật ra **không trả lời**.
- Không được biến Redis `UNKNOWN` thành `FIRST_USE`.
- Không được dùng secret fallback/global key để cho request qua.
- Không được thử thuật toán khác chỉ vì HSM/provider unavailable.
- Không được tạo authenticated principal khi chưa có bằng chứng quyết định đầy đủ.

Ví dụ public response:

~~~http
HTTP/1.1 503 Service Unavailable
Content-Type: application/problem+json
Cache-Control: no-store

{
  "type": "about:blank",
  "title": "Service Unavailable",
  "status": 503,
  "detail": "Authentication is temporarily unavailable.",
  "code": "AUTHENTICATION_UNAVAILABLE",
  "requestId": "req-57a3"
}
~~~

`Retry-After` có thể hữu ích nếu server có **thời điểm khôi phục hợp lý để công bố**; không cần bịa một thời gian cố định khi chưa biết outage sẽ kéo dài bao lâu. Với POST nhạy cảm, client phải cân nhắc **outcome unknown** của request đã gửi trước đó; không blindly retry business mà thiếu idempotency.

### Lỗi “lost ACK” của nonce claim

~~~mermaid
sequenceDiagram
    participant V as HMAC Verifier
    participant R as Redis Primary
    participant B as Business
    V->>R: SET replayKey 1 NX PX TTL
    R->>R: Có thể đã ghi nonce
    R--xV: Response bị mất/timeout
    V-->>V: Claim result UNKNOWN
    Note over B: Không được gọi business
    V-->>V: 503 fail closed
~~~

Nếu gateway nhận một upstream 503, nó không nên đổi thành 401 `INVALID_SIGNATURE` để ẩn sự cố. Những **lỗi dependency** phải hiển thị thành availability issue cho monitoring/SLO, trong khi vẫn không lộ tên vault/Redis host cho client.

### Cẩn thận với status 500/502/504

Ở một reverse proxy, 502 hoặc 504 có thể phản ánh lỗi upstream connection/timeout. Trong ứng dụng, một `AuthenticationServiceException` do nonce store/secret store unavailable thường có thể map 503. Không bắt buộc mọi boundary đều trả chính xác cùng một status, nhưng phải có **end-to-end contract** và audit reason rõ để support phân biệt lỗi hạ tầng với credential invalid.

## 12. 403 hoặc 404: HMAC hợp lệ nhưng không có quyền

Phần lớn API HMAC server-to-server có trình tự:

~~~text
HMAC + credential ACTIVE + timestamp + nonce first-use
    -> authenticatedPrincipal(clientId, ownerTenant, grants)
    -> authorization(route, requestedTenant, resourceId)
    -> business
~~~

Chữ ký hợp lệ bảo vệ `X-Tenant-Id` khỏi bị thay đổi **sau khi ký**, nhưng không chứng minh tenant được yêu cầu nằm trong quyền của client. Một principal `partner-a` của tenant-a có thể ký request hỏi thông tin tenant-b; đây là **authentication pass nhưng authorization deny**.

| Kịch bản | Quyết định | Public |
| --- | --- | --- |
| Chưa có authentication hợp lệ | Không tạo principal | 401 |
| Principal xác thực nhưng không có `PAYMENT_CREATE` | Deny action | 403 |
| Principal không có grant tenant-b | Deny tenant | 403 hoặc 404 theo policy |
| Resource ID không tồn tại | Resource lookup | 404 |
| Resource tồn tại ở tenant khác, policy che existence | Không xác nhận resource tồn tại | 404 |
| Resource tồn tại, principal đủ quyền | Chạy business | Domain response |

### Khi nào nên che resource existence bằng 404?

Nếu tài nguyên ở tenant khác có ID dễ đoán, trả 403 cho ID có thật và 404 cho ID không có thật có thể tạo **resource enumeration oracle**. Một policy có thể trả 404 cho cả trường hợp resource không tồn tại và không được phép nhìn thấy. Cần:

- Cùng response shape/status theo policy đối với caller tương đương.
- Không leak existence qua body, timing, ETag, cache hay headers.
- Ghi internal reason `TENANT_DENIED` hoặc `RESOURCE_HIDDEN` với quyền truy cập hạn chế.
- Tránh lookup trực tiếp resource của tenant khác trước khi enforce tenant-scoped query.

**Không mặc định mọi authorization failure phải 404.** Với action-level permission trên resource được phép nhìn thấy, 403 có thể là tín hiệu chuẩn xác và hữu ích hơn.

### Nonce đã được dùng khi authorization deny?

Nếu nonce được claim trước authorization, request nhận 403/404 vẫn tiêu thụ nonce. Đây là quyết định nhất quán: authentication evidence đã được dùng. Khi client sửa permission hoặc retry, cần tạo timestamp/nonce mới và signature mới, không tự xóa nonce cũ.

## 13. 400: malformed HTTP/headers và ranh giới giữa parse với authn

Một HMAC server cần nhận dạng hai nhóm sai:

**Sai framing/cú pháp HTTP độc lập với secret:** request line không hợp lệ, Content-Length mâu thuẫn, transfer-encoding ambiguity, header count/length vượt ngưỡng, duplicate security headers hoặc chuỗi mã hóa không thể parse. Đây thường là `400 Bad Request` hoặc status giới hạn tương ứng.

**Có request HTTP hợp lệ nhưng authentication proof sai:** key ID không đúng, MAC mismatch, timestamp ngoài window, nonce used. Đây thường là `401` chung.

Một số lỗi như `X-Signature` không phải Base64 hoặc thiếu `X-Key-Id` nằm ở ranh giới: API có thể chọn 400 hoặc 401 theo **public contract**, miễn nhất quán và không tạo credential oracle.

### Duplicate signed headers

~~~http
POST /api/hmac/payments HTTP/1.1
X-Key-Id: partner-a-prod-k004
X-Key-Id: partner-b-prod-k007
X-Timestamp: 2026-11-28T04:00:00Z
X-Nonce: nonce-example
X-Signature: ...
~~~

Nếu gateway lấy `first` nhưng Spring backend lấy `last`, verifier có thể tính HMAC với key khác hoặc ràng buộc sai identity. Với security-critical fields, chọn policy **reject duplicate/ambiguous input**, không tự chọn một giá trị tùy implementation. Không “khắc phục” signature mismatch bằng cách thử cả hai bản canonicalization.

### 400 không được dẫn tới bypass route

Một số application routers chuyển malformed signed request sang error controller hoặc fallback route **không bảo vệ**, vô tình chạy business. Phải bảo đảm:

- Các protected routes không bị bỏ authn khi handler mapping thay đổi.
- Parser/security filter xử lý lỗi trước business.
- Gateway và backend thống nhất về framing, target normalization và duplicate headers.
- Không có request-smuggling ambiguity tạo hai request khác nhau ở hai trust boundaries.

Test bắt buộc có positive control cùng route: nếu client ký đúng nhưng proxy rewrite sai, R1 có thể đã 401; R2 cũng 401 không chứng minh replay guard.

## 14. 413 và 415: lỗi tài nguyên/dạng nội dung trước khi tính HMAC

Một server có giới hạn raw body, header count và signed metadata để tránh attacker làm cạn memory/CPU trước bước authentication.

### Body quá lớn

Nếu route chỉ nhận body tối đa 1 MiB, request có raw payload 2 MiB phải được từ chối theo limit, thường `413 Content Too Large`. Không được:

- Buffer toàn bộ payload vô hạn mới nhận ra quá limit.
- Cắt body ở 1 MiB rồi băm phần bị cắt và so MAC.
- Tiếp tục business với body truncated.
- Claim nonce trước khi có đủ signed body bytes/MAC đúng.

Trong WebFlux, dùng bounded aggregation/streaming strategy có backpressure và giải phóng `DataBuffer` khi error/cancel; Servlet có thể dùng bounded wrapper/filter. Hạn mức phải đo **bytes thực** và có policy khi Content-Length thiếu/sai.

### Content-Type không hỗ trợ

`415 Unsupported Media Type` thích hợp nếu endpoint chỉ nhận `application/json` nhưng client gửi `text/plain`. Tuy nhiên nếu Content-Type là signed header, server phải thống nhất **giá trị chính xác để ký**. Không tự sửa `Content-Type` rồi tiếp tục verify dưới một canonical representation khác.

### Lỗi `422` sau khi authentication

Một request có MAC/nonce hợp lệ, media type được hỗ trợ, JSON parse được nhưng dữ liệu vi phạm domain validation có thể trả 422 (theo hợp đồng). Đây là **business/content failure**; nonce thường đã dùng và không được rollback để caller gửi lại same signature. Client sửa payload thì phải ký lại với nonce mới.

## 15. 429: rate limiting, admission control và anti-replay

`429 Too Many Requests` báo caller đã vượt policy quota/rate limit. Nó có thể xuất hiện trước khi server biết principal HMAC (theo IP/gateway identity) hoặc sau khi có authenticated client identity.

| Vị trí limiter | Identity đáng tin | Lưu ý |
| --- | --- | --- |
| Pre-auth | IP/connection/gateway workload | IP có thể NAT/shared/spoofed nếu tin forwarded header sai |
| Post-auth | Principal/client từ registry | Cần MAC/timestamp/nonce pass trước khi tin identity |
| Business quota | Tenant/action/resource grant | Gắn với authorization/business rules |

**429 không phải replay rejection.** Một request lặp có thể bị 429 vì limiter sớm và nonce chưa được kiểm tra, nên test anti-replay phải chạy trong môi trường không bị limiter che kết quả hoặc assert **internal claim outcome**.

Nếu giới hạn được áp dụng sau authentication, nonce có thể đã được claim và request nhận 429. Nếu limiter chạy trước MAC, nonce thường chưa claim. Đây là **behavior phải công bố cho SDK retry logic**. Không cho SDK tái dùng same signed nonce “vì server chỉ trả 429” mà bỏ qua trường hợp nonce đã từng claim.

### Retry-After

Nếu có thể xác định, `Retry-After` cho 429 có thể giúp client giảm áp lực. Tuy vậy, retry HMAC nên ký **request mới với timestamp/nonce mới** theo policy; với POST có side effects cần giữ business idempotency key và đánh giá outcome của attempt trước. Không dùng Retry-After làm cớ tự động downgrade algorithm hoặc key.

## 16. 409: business idempotency conflict không phải HMAC replay

Một request thanh toán có thể đã được chấp nhận ở authentication nhưng response bị mất. Client retry hợp lệ cần:

~~~text
Business intent: CREATE_PAYMENT(pay-401)
Idempotency-Key: intent-pay-401

Attempt 1:
  Timestamp T1, nonce N1, signature HMAC1
  HTTP response bị mất; business outcome có thể đã commit

Attempt 2:
  Timestamp T2 mới, nonce N2 mới, signature HMAC2 mới
  Idempotency-Key vẫn là intent-pay-401
  Server có thể trả cached result nếu payload/principal khớp
~~~

**Exact replay của Attempt 1** với cùng N1 phải bị chặn tại authentication (401 chung), không đi tới idempotency handler.

Các kết quả khác nhau:

| Scenario | HMAC + nonce | Business check | Public |
| --- | --- | --- | --- |
| R1 đầu tiên | MAC valid, N1 new | Intent mới | Business 2xx/201/202 |
| R1 exact replay | MAC valid, N1 used | **Không chạy** | 401 |
| R2 cùng intent, N2 mới, cùng payload/principal | Authentication pass | Có thể trả stored result | 2xx theo contract |
| R3 cùng intent, N3 mới, payload khác | Authentication pass | Binding conflict | 409 |
| R4 cùng intent key nhưng tenant/action khác | Authentication pass | Deny hoặc conflict theo identity binding | 403/404/409 theo policy |

`Idempotency-Key` cần được bảo vệ bằng HMAC hoặc binding khác với principal, tenant, action và body digest để không bị thay trái phép. Idempotency store phải atomic/transactional với business side effects theo contract; nonce store **không thể** một mình bảo đảm exactly-once business execution.

### Kết quả unknown khi client mất response

Nếu connection bị cắt **sau khi** business commit, caller không biết transaction đã thành công. Chỉ nhìn thấy một 5xx/timeout không đủ để kết luận “server chưa làm gì”. Cần idempotency key, status lookup qua kênh có quyền hoặc reconciliation. Không hướng dẫn retry signed request cũ bằng cách xóa nonce server-side.

## 17. Error precedence: cùng request sai nhiều thứ thì trả gì?

Một request có thể đồng thời:

- Body quá lớn.
- Timestamp expired.
- Signature sai.
- Key ID đã revoke.
- Requested tenant không có quyền.
- Redis không khả dụng.

Không nên xây một “thứ tự lỗi” đơn giản bằng cách kiểm tra tất cả và trả reason đầu tiên kèm chi tiết. Điều đó vừa tốn tài nguyên vừa mở oracle. Cần **error precedence policy** dựa trên tầng/hạn mức:

1. **Ingress security:** từ chối transport framing bất hợp lệ, request smuggling, header/body quá limit ngay khi phát hiện.
2. **Auth envelope grammar:** từ chối input ambiguous/malformed theo API contract.
3. **Credential/key/suite eligibility:** exact lookup, không tiết lộ sự tồn tại key.
4. **MAC proof:** tính trên canonical bytes do server dựng; lỗi → 401 chung.
5. **Freshness và atomic replay:** timestamp validation và nonce claim sau MAC; error theo bảng.
6. **Authorization:** chỉ thực hiện sau authenticated principal.
7. **Business:** media/content/idempotency/domain validation theo route policy, không truy cập business trước authn.

Có thể kiểm tra timestamp grammar/window trước MAC để giảm load; nhưng **không claim nonce khi MAC sai**. Việc media-type/body-size kiểm tra ở bước 1 hay sau authentication tùy ingress/resource policy; cần giữ **fail-closed và no business effects** trong mọi lựa chọn.

### Một nguyên tắc quan sát lỗi

**Internal reason phải mô tả điều server thật sự biết.** Nếu Redis không kết nối được, không được tự ghi `REPLAY_DETECTED`. Nếu chỉ biết MAC mismatch, không ghi `CLIENT_SIGNED_WRONG_URI` trừ khi đã có bằng chứng golden bytes/test vector.

## 18. Key rotation và algorithm agility: giữ đúng error semantics khi overlap

Trong overlap K3/K4, server có thể cho phép cả hai keys ACTIVE:

| Request | Credential policy | Authentication outcome |
| --- | --- | --- |
| Header K4, MAC bằng secret K4 | K4 ACTIVE | Có thể pass nếu nonce new |
| Header K4, MAC bằng secret K3 | K4 ACTIVE | **401** generic, MAC mismatch |
| Header K3, MAC bằng secret K3 | K3 ACTIVE trong grace | Có thể pass theo policy |
| Header K3, MAC đúng K3 | K3 REVOKED | **401** generic, không hồi sinh key |
| Header K4, suite V1 bị deny | K4 chỉ cho V2 | **401** generic, không fallback |
| HSM provider unavailable | Không thể tính MAC | **503** dependency, không “bad signature” |

Không thử tất cả secrets/suites để tìm một MAC khớp, vì dễ tạo key confusion và downgrade. `X-Key-Id` và suite selector phải được binding trong ký hoặc cơ chế versioned contract có security review.

### Downgrade và error messages

Một client không được nhận `401 SIGNATURE_FAILED` rồi tự thử secret cũ V1. Một public error quá chi tiết kiểu “key K4 only accepts V1” có thể cung cấp attacker thông tin migration. Hướng dẫn nâng cấp nên đi qua **provisioning/management channel đã xác thực**, capability metadata an toàn và deprecation notices, không phải phản hồi từ protected API request có chữ ký sai.

### Key revoke và availability

Nếu credential registry báo `REVOKED` đáng tin → 401 chung. Nếu registry **timeout, trả dữ liệu không thể xác minh freshness** → 503/fail closed theo security requirement; không coi đó là `KEY_NOT_FOUND`. Đây là khác biệt rất quan trọng với incident response.

## 19. Gateway/proxy: một HTTP status có thể bị đổi ở nhiều tầng

Có hai mô hình:

**Gateway verify HMAC:** gateway làm MAC/timestamp/nonce claim, backend nhận trusted identity assertion qua mTLS/signed internal assertion. Backend **không tin** `X-Authenticated-Client` do client tự gửi. Gateway phải trả hoặc forward chính xác public error khi authentication không đạt; không mint assertion cho request bị replay.

**Backend verify HMAC:** gateway chuyển signed headers/body/URI theo contract. Nếu gateway rewrite `/public/payments` → `/internal/payments`, canonical target phải được định nghĩa rõ. Backend không tự tin `X-Original-URI` do client tùy ý khai.

~~~mermaid
flowchart LR
    C["HMAC client"] --> G["Gateway/WAF"]
    G --> V["HMAC verifier"]
    V --> N[("Atomic nonce authority")]
    V --> A["Authorization"]
    A --> B["Business"]
    V -. "Internal reason enum" .-> T["Security audit/metrics"]
    G -. "Public status contract" .-> C
~~~

### Proxy có thể làm gì sai?

| Tình huống | Hậu quả |
| --- | --- |
| Gateway biến backend 401 thành 200 + “error” trong JSON | Client hiểu sai và có thể retry/lấy dữ liệu |
| Gateway biến Redis 503 thành 401 | Che dependency incident, client rotate key vô ích |
| Gateway trả 502 HTML chứa upstream internals | Lộ topology/log dữ liệu |
| CDN cache response authn/authorization | Lộ dữ liệu hoặc tái sử dụng lỗi không đúng context |
| Proxy chuẩn hóa signed path/body mà không có contract | MAC mismatch nhưng log đổ lỗi “bad secret” |
| Gateway và backend dùng khác challenge scheme | SDK không thể diễn giải response nhất quán |
| Gateway cùng backend claim client nonce hai lần | First request hợp lệ bị báo replay |
| Client tự gửi identity/forwarded headers | Bypass authentication/tenant policy |

Áp dụng `Cache-Control: no-store` cho authentication error bodies nhạy cảm; cấu hình cache/cookie/auth headers và protected responses phù hợp với hệ thống thực. Lỗi upstream phải có public response **sanitized**, không leak stack/hostnames; trace/correlation có thể gửi qua kênh nội bộ có ACL.

### Lưu ý với 502/504

Một gateway thực sự có upstream connect failure hoặc timeout có thể trả 502/504 theo semantics của chính gateway. Đừng ép nó thành 401 “cho đồng nhất”; đó không phải bằng chứng client invalid. SDK phải phân biệt 5xx/timeout với 401 và thực hiện retry có idempotency phù hợp.

## 20. Chuẩn hóa public error schema bằng Problem Details

Có thể dùng cấu trúc **Problem Details for HTTP APIs** (RFC 9457) làm nền tảng, kết hợp một `code` riêng được document và version hóa:

~~~json
{
  "type": "about:blank",
  "title": "Unauthorized",
  "status": 401,
  "detail": "Authentication is required or invalid.",
  "code": "AUTHENTICATION_FAILED",
  "requestId": "req-57a2"
}
~~~

Những field `type`, `title`, `status`, `detail` thuộc mô hình Problem Details; `code` và `requestId` là **extensions riêng** của API. Nếu dùng `type="about:blank"`, `title` thường phản ánh HTTP status phrase; nếu muốn type riêng, dùng một URI type tài liệu ổn định do tổ chức quản lý.

### Profile response đề xuất

| HTTP status | Public code | Detail an toàn |
| --- | --- | --- |
| 400 | `REQUEST_INVALID` | “Request syntax is invalid.” |
| 401 | `AUTHENTICATION_FAILED` | “Authentication is required or invalid.” |
| 403 | `ACCESS_DENIED` | “You are not permitted to perform this operation.” |
| 404 | `RESOURCE_NOT_FOUND` | “Resource was not found.” |
| 409 | `IDEMPOTENCY_CONFLICT` | “The request conflicts with a previously recorded operation.” |
| 413 | `REQUEST_TOO_LARGE` | “Request exceeds the supported size.” |
| 415 | `MEDIA_TYPE_UNSUPPORTED` | “Content type is not supported.” |
| 422 | `VALIDATION_FAILED` | “Request content failed validation.” |
| 429 | `RATE_LIMITED` | “Request rate limit exceeded.” |
| 500 | `INTERNAL_ERROR` | “The service could not process this request.” |
| 503 | `AUTHENTICATION_UNAVAILABLE` | “Authentication is temporarily unavailable.” |

Không cần trả cùng một `code` cho 503 của auth dependency và 503 của business dependency nếu API có hai semantics khác; nhưng danh sách mã phải **có chừng mực** và không làm hở internal topology. Với `404` che resource existence, **không** phân biệt `RESOURCE_IN_OTHER_TENANT` trong public code.

### Header chính sách

- `Content-Type: application/problem+json` cho Problem Details payload.
- `Cache-Control: no-store` cho failures nhạy cảm/authenticated workflows.
- `WWW-Authenticate` phù hợp nếu response 401 và API sử dụng challenge scheme.
- `Retry-After` cho 429/503 nếu có hướng dẫn retry đáng tin cậy.
- Correlation `requestId` do server tạo hoặc validate, không phản chiếu raw user-supplied header không giới hạn.

Không serialize stack trace, exception class, raw URI/query chứa token, key ID, signature hoặc expected digest vào public JSON.

## 21. Java 17: ánh xạ nguyên nhân nội bộ thành public contract

Có thể đặt mapping vào một lớp **thuần, không có side effects**, để các adapter Servlet/WebFlux cùng tái sử dụng và unit-test.

~~~java
enum HmacFailure {
    MALFORMED_HTTP,
    INVALID_SECURITY_ENVELOPE,
    BODY_TOO_LARGE,
    MEDIA_TYPE_UNSUPPORTED,
    RATE_LIMIT_EXCEEDED,

    KEY_UNKNOWN,
    KEY_DISABLED,
    KEY_REVOKED,
    SUITE_DISALLOWED,
    SIGNATURE_MISMATCH,
    TIMESTAMP_INVALID,
    NONCE_REPLAYED,

    CREDENTIAL_STORE_UNAVAILABLE,
    NONCE_STORE_UNKNOWN,
    CRYPTO_RUNTIME_UNAVAILABLE,

    ACCESS_DENIED,
    RESOURCE_HIDDEN,
    IDEMPOTENCY_CONFLICT,
    DOMAIN_VALIDATION_FAILED,
    INTERNAL_ERROR
}

record PublicProblem(
    int status,
    String code,
    String title,
    String detail,
    boolean authenticationChallenge
) {}

final class HmacErrorPolicy {
    private HmacErrorPolicy() {}

    static PublicProblem map(HmacFailure failure) {
        return switch (failure) {
            case MALFORMED_HTTP ->
                problem(400, "REQUEST_INVALID",
                    "Bad Request",
                    "Request syntax is invalid.", false);

            case BODY_TOO_LARGE ->
                problem(413, "REQUEST_TOO_LARGE",
                    "Content Too Large",
                    "Request exceeds the supported size.", false);

            case MEDIA_TYPE_UNSUPPORTED ->
                problem(415, "MEDIA_TYPE_UNSUPPORTED",
                    "Unsupported Media Type",
                    "Content type is not supported.", false);

            case RATE_LIMIT_EXCEEDED ->
                problem(429, "RATE_LIMITED",
                    "Too Many Requests",
                    "Request rate limit exceeded.", false);

            case KEY_UNKNOWN, KEY_DISABLED, KEY_REVOKED,
                 INVALID_SECURITY_ENVELOPE, SUITE_DISALLOWED,
                 SIGNATURE_MISMATCH, TIMESTAMP_INVALID,
                 NONCE_REPLAYED ->
                problem(401, "AUTHENTICATION_FAILED",
                    "Unauthorized",
                    "Authentication is required or invalid.", true);

            case CREDENTIAL_STORE_UNAVAILABLE,
                 NONCE_STORE_UNKNOWN,
                 CRYPTO_RUNTIME_UNAVAILABLE ->
                problem(503, "AUTHENTICATION_UNAVAILABLE",
                    "Service Unavailable",
                    "Authentication is temporarily unavailable.",
                    false);

            case ACCESS_DENIED ->
                problem(403, "ACCESS_DENIED",
                    "Forbidden",
                    "You are not permitted to perform this operation.",
                    false);

            case RESOURCE_HIDDEN ->
                problem(404, "RESOURCE_NOT_FOUND",
                    "Not Found",
                    "Resource was not found.", false);

            case IDEMPOTENCY_CONFLICT ->
                problem(409, "IDEMPOTENCY_CONFLICT",
                    "Conflict",
                    "The request conflicts with an existing operation.",
                    false);

            case DOMAIN_VALIDATION_FAILED ->
                problem(422, "VALIDATION_FAILED",
                    "Unprocessable Content",
                    "Request content failed validation.", false);

            case INTERNAL_ERROR ->
                problem(500, "INTERNAL_ERROR",
                    "Internal Server Error",
                    "The service could not process this request.", false);
        };
    }

    private static PublicProblem problem(
            int status, String code, String title,
            String detail, boolean challenge) {
        return new PublicProblem(
            status, code, title, detail, challenge);
    }
}
~~~

**Thiết kế có chủ đích:** nhiều internal failures ánh xạ vào cùng `AUTHENTICATION_FAILED`. `MALFORMED_HTTP` dùng 400 trong profile này, nhưng một API có thể coi `INVALID_SECURITY_ENVELOPE` là 400 thay vì 401 nếu contract và threat model yêu cầu. Khi đó phải chỉnh mapping **có review** và cập nhật tests, không phân biệt công khai key-existence.

### Không dùng enum này như nguồn dữ liệu không đáng tin

`HmacFailure` chỉ do **security adapter/provider nội bộ** phát ra, không chấp nhận `X-Failure-Reason` từ client rồi map trực tiếp. PublicProblem cũng không chứa internal reason, raw exception message hoặc secret-derived values.

### Failure của Redis không được nuốt

~~~java
// SAI: biến lỗi dependency thành lời buộc tội client.
try {
    return nonceStore.claim(key);
} catch (RuntimeException ex) {
    throw new BadCredentialsException("bad_signature");
}

// ĐÚNG VỀ PHÂN LOẠI: authentication không sẵn sàng.
try {
    return nonceStore.claim(key);
} catch (RuntimeException ex) {
    throw new HmacServiceUnavailableException(
        HmacFailure.NONCE_STORE_UNKNOWN);
}
~~~

`HmacServiceUnavailableException` là class dự án cần định nghĩa (hoặc dùng exception type tương ứng), không phải API có sẵn. Bản production cần audit event, circuit breaker policy và adapter error handling nhất quán, không cho exception raw đi ra public.

## 22. Spring Security Servlet: AuthenticationEntryPoint và AccessDeniedHandler

Trong Spring MVC/Spring Security 6, HMAC filter có thể ném `AuthenticationException` **trước khi request đi vào DispatcherServlet**. `@RestControllerAdvice` không đương nhiên xử lý tất cả lỗi ở filter chain. Vì vậy, authentication error cần được xử lý tại **security entry point/failure handler** phù hợp.

### Ví dụ AuthenticationEntryPoint

~~~java
import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.util.LinkedHashMap;
import java.util.Map;
import org.springframework.http.MediaType;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.web.AuthenticationEntryPoint;

final class HmacProblemEntryPoint implements AuthenticationEntryPoint {
    private final ObjectMapper objectMapper;

    HmacProblemEntryPoint(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
    }

    @Override
    public void commence(
            HttpServletRequest request,
            HttpServletResponse response,
            AuthenticationException cause)
            throws IOException {
        // Entry point chỉ dành cho authentication failures,
        // không nhận infrastructure error rồi coi là 401.
        PublicProblem p =
            HmacErrorPolicy.map(HmacFailure.SIGNATURE_MISMATCH);

        response.setStatus(p.status());
        response.setContentType(
            "application/problem+json");
        response.setCharacterEncoding("UTF-8");
        response.setHeader("Cache-Control", "no-store");

        // Chỉ dùng khi API đã định nghĩa scheme HMAC này.
        response.setHeader(
            "WWW-Authenticate", "HMAC realm=\"api\"");

        String requestId =
            String.valueOf(request.getAttribute("trustedRequestId"));
        // Production: requestId được tạo/sanitize phía server;
        // không phản chiếu raw header từ client.

        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("type", "about:blank");
        payload.put("title", p.title());
        payload.put("status", p.status());
        payload.put("detail", p.detail());
        payload.put("code", p.code());
        payload.put("requestId", requestId);

        objectMapper.writeValue(
            response.getOutputStream(), payload);
    }
}
~~~

**Giới hạn và lưu ý:**

- Đây là **adapter 401**, không phải một global handler cho mọi `HmacFailure`. Lỗi Redis/vault/provider phải được chuyển qua một đường xử lý **503 fail closed**, không ép vào `AuthenticationEntryPoint` trên mọi trường hợp.
- `trustedRequestId` phải được cấp và giới hạn bởi middleware đáng tin. Nếu absent, nên generate ID server-side; ví dụ dùng `String.valueOf(null)` chỉ là minh họa thiếu fallback.
- Header `WWW-Authenticate: HMAC realm="api"` chỉ được dùng khi ứng dụng đã tự định nghĩa scheme phù hợp.
- Không đưa `cause.getMessage()` hoặc raw exception vào payload.
- Nếu response đã committed, handler không thể sửa an toàn status/body; cần đảm bảo authentication xảy ra trước khi ghi response.

### AccessDeniedHandler

Với principal đã authenticated nhưng thiếu scope/tenant grant, dùng `AccessDeniedHandler` trả 403 hoặc resource-hiding 404 theo policy. Không tái dùng entry point 401 để che một principal đã xác thực:

~~~java
// Pseudocode: authorization policy phải phân biệt
// action denied và resource existence hiding.
if (principalAuthenticated && !authorized) {
    var p = HmacErrorPolicy.map(
        hideResourceExistence
            ? HmacFailure.RESOURCE_HIDDEN
            : HmacFailure.ACCESS_DENIED);
    writeProblemResponse(response, p);
}
~~~

`writeProblemResponse` là helper dự án; phải serialize body chuẩn, no-store và không leak resource existence qua logs/public response.

### Chỗ đặt trong SecurityFilterChain

~~~java
// Trích đoạn cấu hình Spring Security 6 Servlet.
// Cần tích hợp thêm route matcher, actual HMAC filter
// và các exception handlers khác của ứng dụng.
http.exceptionHandling(ex -> ex
    .authenticationEntryPoint(hmacProblemEntryPoint)
    .accessDeniedHandler(hmacAccessDeniedHandler));
~~~

Nếu HMAC filter được đặt trước `ExceptionTranslationFilter`, exception có thể cần được filter tự bắt/chuyển tới entry point tương ứng; không giả định một handler tự đón exception ở mọi filter position. Test bằng `@SpringBootTest` + `@AutoConfigureMockMvc` với **filter chain thật**, không chỉ gọi standalone controller.

## 23. Spring WebFlux: ServerAuthenticationEntryPoint và lỗi reactive

Với Spring WebFlux, authentication chạy trong `SecurityWebFilterChain` và có thể dùng `ReactiveAuthenticationManager`. Lỗi không đi qua `DispatcherServlet`; cần quản lý trong reactive security chain, nhất là khi claim nonce dùng `ReactiveStringRedisTemplate`.

### Ví dụ entry point trả 401

~~~java
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.nio.charset.StandardCharsets;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.UUID;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.web.server.ServerAuthenticationEntryPoint;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

final class HmacReactiveEntryPoint
        implements ServerAuthenticationEntryPoint {

    private final ObjectMapper mapper;

    HmacReactiveEntryPoint(ObjectMapper mapper) {
        this.mapper = mapper;
    }

    @Override
    public Mono<Void> commence(
            ServerWebExchange exchange,
            AuthenticationException ignored) {

        var response = exchange.getResponse();
        if (response.isCommitted()) {
            return Mono.empty();
        }

        PublicProblem problem =
            HmacErrorPolicy.map(HmacFailure.SIGNATURE_MISMATCH);

        response.setStatusCode(HttpStatus.UNAUTHORIZED);
        response.getHeaders().setContentType(
            MediaType.parseMediaType("application/problem+json"));
        response.getHeaders().setCacheControl("no-store");

        // Chỉ dùng khi API đã định nghĩa HMAC challenge.
        response.getHeaders().set(
            HttpHeaders.WWW_AUTHENTICATE, "HMAC realm=\"api\"");

        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("type", "about:blank");
        payload.put("title", problem.title());
        payload.put("status", problem.status());
        payload.put("detail", problem.detail());
        payload.put("code", problem.code());

        // Dùng ID được tạo từ phía server, không phản chiếu
        // chuỗi user-supplied thiếu giới hạn.
        payload.put("requestId",
            UUID.randomUUID().toString());

        final byte[] bytes;
        try {
            bytes = mapper.writeValueAsBytes(payload);
        } catch (JsonProcessingException ex) {
            return Mono.error(ex);
        }

        var buffer = response.bufferFactory().wrap(bytes);
        return response.writeWith(Mono.just(buffer));
    }
}
~~~

Đây là adapter **riêng cho 401 authentication failure**. Không nên đưa `AuthenticationServiceException` do Redis timeout vào flow 401 chung. Đường lỗi dependency cần map **503 fail closed** từ một tầng được định nghĩa (failure handler hoặc exception mapping trước khi response committed) mà không đánh rơi context.

### Những rủi ro riêng của reactive chain

- Không dùng `block()` hoặc Redis client blocking trên Netty event loop.
- Khi body HMAC được capture từ `Flux<DataBuffer>`, phải đặt giới hạn bytes, xử lý complete/error/cancel và release pooled buffers.
- Không tự `subscribe()` replay claim ngoài security chain; nó có thể chạy trễ hoặc không gắn với quyết định authentication.
- `Mono.empty()` khi nonce store mất response **không** được hiểu là authentication success.
- Khi response đã committed, không thể thay status/body tùy ý; authentication cần hoàn thành trước business streaming response.
- `ReactiveSecurityContextHolder` chỉ được thiết lập sau khi MAC/timestamp/nonce pass.
- Shadow verification hoặc audit observer không được mutate context hay claim nonce thêm lần nữa.

### Reactive claim phải phân biệt ba kết quả

~~~java
// Reactor pseudocode: classes/variables thuộc dự án.
return verifyMacAndTimestamp(proof)
    .flatMap(verified ->
        nonceStore.claim(
            verified.trustedCredentialId(),
            verified.nonce(),
            verified.ttl())
        .flatMap(result -> switch (result) {
            case FIRST_USE -> Mono.just(
                verified.toAuthentication());
            case ALREADY_USED -> Mono.error(
                new BadCredentialsException(
                    "authentication_failed"));
            case UNKNOWN -> Mono.error(
                new AuthenticationServiceException(
                    "authentication_unavailable"));
        })
    );
~~~

Nếu `nonceStore.claim(...)` thực sự ném lỗi reactive, phải map vào `AuthenticationServiceException` hoặc loại internal dependency exception tương ứng; **không** dùng `onErrorReturn(FIRST_USE)`. Luồng ở trên là pseudocode để nhấn mạnh semantics, không phải implementation copy-build nếu thiếu adapters.

## 24. Phân biệt exception type và public error: không dùng một catch-all

Một error policy tốt không chỉ là switch theo enum; tầng tạo exception cũng phải chính xác:

| Nguồn | Exception/result | Đường xử lý |
| --- | --- | --- |
| MAC mismatch | Authentication failure | 401 entry point |
| Unknown/revoked credential | Authentication failure | 401 entry point, internal reason riêng |
| Timestamp/nonce replay | Authentication failure | 401 entry point |
| Redis claim timeout | Dependency unavailable | 503 error adapter, fail closed |
| Secret store timeout | Dependency unavailable | 503 error adapter, fail closed |
| Tenant/action denied | Access denied | 403/404 handler theo policy |
| Validation/business idempotency | Domain exception | Controller/domain error mapping |
| Unexpected bug | Internal server error | 500 sanitized, alert |
| Gateway upstream timeout | Proxy-level error | 504/502 theo boundary |

Hai cách làm nguy hiểm:

~~~java
// SAI: mọi exception trở thành BAD_CREDENTIALS.
// Redis lỗi cũng bị “đổ tội” cho client.
catch (Exception ex) {
    throw new BadCredentialsException("signature_invalid");
}

// SAI: status 401 bị nuốt và tiếp tục controller.
catch (AuthenticationException ex) {
    logger.warn("bad auth");
    filterChain.doFilter(request, response);
}
~~~

Nguyên tắc đúng: mỗi security failure **kết thúc luồng yêu cầu** tại một boundary rõ. Chỉ business branch có authenticated/authorized context mới gọi controller hoặc downstream handler. Exception phải được dịch thành public response **một lần**, không ghi partial response rồi ném tiếp khiến gateway trả status khác.

### Internal reason cần typed data, không parse exception string

Không viết logic kiểu `if (exception.getMessage().contains("nonce")) ...`. Thay vào đó dùng exception/result typed (enum) từ verifier, có metadata route/stage và category rõ, rồi map qua policy layer. Public output không phản chiếu `getMessage()` chứa key ID, signing bytes hoặc secret store hostname.

## 25. Tài liệu cho SDK: hành vi đúng theo response

Một HMAC SDK cần nhận được một **contract retry** rõ. Không thể chỉ nói “retry khi status ≥ 500”.

| Response | Ý nghĩa cho client | Hành vi khuyến nghị |
| --- | --- | --- |
| 400 | Malformed request/contract input | Sửa serializer/headers; không retry nguyên request vô hạn |
| 401 | Authentication proof không được chấp nhận | Kiểm tra key/suite/clock/nonce/canonical contract; không downgrade |
| 403 | Authenticated nhưng thiếu quyền | Xin grant/kiểm tra tenant, không rotate secret theo phản xạ |
| 404 | Resource không thấy được/không tồn tại | Không suy luận tenant/resource existence |
| 409 | Idempotency/body binding conflict | Không tự tạo intent key khác để bỏ qua conflict |
| 413 | Payload vượt limit | Giảm size hoặc dùng upload protocol được hỗ trợ |
| 415 | Media type không phù hợp | Đổi Content-Type và ký lại request |
| 422 | Domain validation failed | Sửa payload, dùng nonce/signature mới |
| 429 | Bị rate limit | Thực hiện backoff/Retry-After hợp lý; ký attempt mới |
| 500 | Lỗi ứng dụng | Xác minh outcome, dùng idempotency/status lookup |
| 502/503/504 | Dependency/gateway failure | Retry an toàn có kiểm soát, nonce mới; kiểm tra business outcome |

### Quy tắc vàng khi retry

Nếu client quyết định tạo **HTTP attempt mới**, phải tạo **timestamp, nonce và HMAC signature mới** khi contract yêu cầu nonce dùng một lần. Nếu retry là của cùng business intent, giữ `Idempotency-Key` và binding với principal/tenant/action/payload. Điều này khác với cách HTTP libraries tự gửi lại **nguyên request bytes** sau timeout; middleware retry phải được tích hợp với HMAC signer.

Không nên tự kết luận “503 nghĩa là server chưa làm gì”: nếu response bị mất sau business commit thì outcome vẫn có thể unknown. Client nên sử dụng idempotency và reconciliation thay vì phát lại chữ ký cũ.

### Không đưa key lifecycle vào public 401

Chi tiết provisioning/rotation như K4 đã revoke, K5 sẵn sàng, giờ cutover... nên có management API **đã xác thực và phân quyền**, không cần trả trong protected HMAC endpoint cho một caller có signature sai. Như vậy SDK vẫn có con đường sửa lỗi hợp pháp mà không tạo credential oracle.

## 26. Monitoring, audit và operational SLO từ error semantics

Không đủ để đếm số 401. Mỗi failure stage cần một **reason enum low-cardinality** để triage:

| Metric logic | Labels hữu hạn | Công dụng |
| --- | --- | --- |
| `hmac_auth_attempts_total` | route, outcome, reason | Chữ ký/timestamp/replay errors |
| `hmac_nonce_claims_total` | result | FIRST_USE/ALREADY_USED/UNKNOWN |
| `hmac_auth_dependency_failures_total` | dependency_kind, outcome | Redis/vault/provider unavailable |
| `hmac_authorization_denied_total` | route, reason | Tenant/scope/resource policy |
| `hmac_problem_responses_total` | route, status, code | Tương thích public error contract |
| `hmac_signing_suite_attempts_total` | suite, outcome | Migration/rotation |
| `hmac_gateway_error_mappings_total` | upstream_class, public_status | Proxy parity |
| `hmac_auth_duration_seconds` | route, stage | p50/p95/p99, dependency latency |

Tất cả labels phải lấy từ **allowlist enum/route template**, không dùng raw path/query, client ID/key ID/tenant ID, nonce, signature, body, requestId. Những trường high-cardinality có thể nằm trong controlled trace/audit theo security policy nếu thực sự cần và được bảo vệ.

### Alert có hành động

- Nonce store `UNKNOWN` tăng nhưng HTTP response vẫn 2xx → dấu hiệu **fail-open**.
- Revoked key được ghi nhận `AUTHENTICATED` → incident lifecycle/policy cache.
- Replay result `ALREADY_USED` tăng sau SDK update → kiểm tra retry reuse nonce hoặc tấn công.
- 401 tăng theo gateway mới, positive signing vector fail → canonicalization/proxy drift.
- 503 auth dependency tăng → lỗi vault/Redis/provider, không yêu cầu khách rotate key.
- 403 tăng theo tenant → grant/authorization change, không tự sửa HMAC signer.
- R2 exact replay có business effect thứ hai → security regression.
- Unknown key và signature mismatch có response/timing khác biệt lớn → đánh giá oracle.

### SLO phải đo đúng failure class

Nếu toàn bộ 401 đều tính vào service unavailability, SLO có thể đỏ do client cấu hình sai; nếu bỏ qua mọi 503, sự cố **nonce store** sẽ bị che. Một policy có thể tách:

- **Client-authn failure:** key/MAC/timestamp/replay invalid.
- **Authn infrastructure failure:** nonce store/vault/crypto runtime unavailable.
- **Authorization deny:** policy quyết định, không phải hạ tầng hỏng.
- **Server/application failure:** 500/502/503/504 theo boundary.
- **Successful authorized business:** 2xx/3xx và domain outcomes theo sản phẩm.

Cần thêm latency p95/p99 của body digest, key lookup, replay claim và error serialization; đừng tạo logging quá nhiều trên hot path vì nó có thể gây DoS.

## 27. Đặc tả kiểm thử: status đúng vẫn chưa đủ

Một test chất lượng cho error semantics phải có **positive control** cùng route/credential/Clock, sau đó thay **một điều kiện** để xác định failure.

Ví dụ kiểm thử replay:

~~~text
Fixture:
  K4 ACTIVE, secret S4 test-only
  Clock.fixed(2026-11-28T04:00:00Z)
  HMAC-REQUEST-V1 contract đã có golden canonical bytes
  Nonce N chưa claim
  Business sandbox không tạo tiền thật

R1:
  signed method, raw URI/query, headers, body digest, T, N
  MAC đúng S4
  → authentication pass, nonce FIRST_USE, business effect ≤ 1

R2:
  bản sao signed request R1 y hệt
  T vẫn trong window
  → public 401 AUTHENTICATION_FAILED
  → internal REPLAY_DETECTED, nonce ALREADY_USED
  → không có business effect lần thứ hai
~~~

Nếu R1 cũng 401 do key chưa ACTIVE hoặc proxy rewrite path, R2 401 không chứng minh gì. Nếu R2 trả 409 từ payment idempotency, HMAC guard có thể đã để replay đi qua authentication. Test cần kiểm tra **vị trí từ chối**.

### Năm lớp assertion

1. **HTTP contract:** status, content type, challenge, cache headers, code/detail.
2. **Internal classification:** reason đúng, không bị map nhầm 401/503.
3. **Replay/credential state:** nonce claim count và key revision.
4. **Security principal/context:** không có authenticated identity khi authn fail.
5. **Business effects:** DB rows, outbox, queue, payment, email không tăng.

Với authorization 403/404, nonce có thể đã dùng nếu claim trước authz; test phải phù hợp với policy. Với malformed request bị 400 trước MAC, thường nonce **không được claim**.

## 28. JUnit 5: khóa public mapping bằng unit tests

Có thể kiểm tra `HmacErrorPolicy` thuần Java mà không cần khởi động server:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

class HmacErrorPolicyTest {
    @Test
    void unknownKeyAndInvalidMacExposeSamePublicContract() {
        PublicProblem unknown =
            HmacErrorPolicy.map(HmacFailure.KEY_UNKNOWN);
        PublicProblem badMac =
            HmacErrorPolicy.map(HmacFailure.SIGNATURE_MISMATCH);

        assertEquals(401, unknown.status());
        assertEquals(unknown.status(), badMac.status());
        assertEquals(unknown.code(), badMac.code());
        assertEquals(unknown.detail(), badMac.detail());
        assertTrue(unknown.authenticationChallenge());
    }

    @Test
    void revokedKeyAndReplayUseGenericAuthenticationError() {
        PublicProblem revoked =
            HmacErrorPolicy.map(HmacFailure.KEY_REVOKED);
        PublicProblem replay =
            HmacErrorPolicy.map(HmacFailure.NONCE_REPLAYED);

        assertEquals("AUTHENTICATION_FAILED", revoked.code());
        assertEquals(revoked.code(), replay.code());
        assertEquals(401, replay.status());
    }

    @Test
    void nonceStoreUnknownNeverBecomesBadCredentials() {
        PublicProblem unavailable =
            HmacErrorPolicy.map(HmacFailure.NONCE_STORE_UNKNOWN);

        assertEquals(503, unavailable.status());
        assertEquals(
            "AUTHENTICATION_UNAVAILABLE",
            unavailable.code());
        assertFalse(unavailable.authenticationChallenge());
    }

    @Test
    void authorizationIsSeparateFromAuthentication() {
        assertEquals(403,
            HmacErrorPolicy.map(
                HmacFailure.ACCESS_DENIED).status());
        assertEquals(404,
            HmacErrorPolicy.map(
                HmacFailure.RESOURCE_HIDDEN).status());
    }

    @Test
    void domainConflictIsNotHmacReplay() {
        assertEquals(409,
            HmacErrorPolicy.map(
                HmacFailure.IDEMPOTENCY_CONFLICT).status());
        assertEquals(401,
            HmacErrorPolicy.map(
                HmacFailure.NONCE_REPLAYED).status());
    }

    @Test
    void oversizedAndMalformedAreDistinguished() {
        assertEquals(413,
            HmacErrorPolicy.map(
                HmacFailure.BODY_TOO_LARGE).status());
        assertEquals(400,
            HmacErrorPolicy.map(
                HmacFailure.MALFORMED_HTTP).status());
    }
}
~~~

Bộ unit tests này **chỉ khóa policy mapping**, không chứng minh verifier đã phát đúng `HmacFailure` hoặc Spring response đã serialize đúng. Vì thế cần integration tests qua filter chain và dependency fault-injection.

## 29. Spring integration: kiểm tra đúng handler, challenge và trạng thái

### Servlet/MockMvc test skeleton

~~~java
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.*;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet
    .AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class HmacErrorSemanticsMvcIT {

    @Autowired MockMvc mvc;
    @Autowired HmacTestFixture fixture;

    @Test
    void unknownKeyAndBadMacReturnSamePublic401()
            throws Exception {
        fixture.useFixedClock("2026-11-28T04:00:00Z");
        var unknownKey = fixture.signedRequestWithUnknownKey();
        var badMac = fixture.signedRequestWithWrongMac();

        mvc.perform(unknownKey)
            .andExpect(status().isUnauthorized())
            .andExpect(header().string(
                "Cache-Control", "no-store"))
            .andExpect(jsonPath("$.code")
                .value("AUTHENTICATION_FAILED"));

        mvc.perform(badMac)
            .andExpect(status().isUnauthorized())
            .andExpect(jsonPath("$.code")
                .value("AUTHENTICATION_FAILED"));
    }

    @Test
    void nonceStoreOutageIs503Not401()
            throws Exception {
        fixture.activateCredential("partner-a-prod-k004");
        fixture.useFixedClock("2026-11-28T04:00:00Z");
        fixture.forceNonceStoreUnknown();

        mvc.perform(fixture.validSignedRequestWithNewNonce())
            .andExpect(status().isServiceUnavailable())
            .andExpect(jsonPath("$.code")
                .value("AUTHENTICATION_UNAVAILABLE"));

        fixture.assertNoBusinessEffects();
    }
}
~~~

Đây là **test skeleton**: `HmacTestFixture` và các request helpers phải do dự án xây, không phải API Spring có sẵn. Dùng signer độc lập và credential test, đừng tính expected MAC bằng chính verifier đang kiểm tra. Test challenge, content type, no-store và response không chứa internal reason/raw secret/signature.

### WebFlux/WebTestClient test skeleton

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive
    .AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class HmacErrorSemanticsWebFluxIT {

    @Autowired WebTestClient client;
    @Autowired HmacTestFixture fixture;

    @Test
    void exactReplayProducesGeneric401Not409() {
        fixture.clearReplayState();
        fixture.useFixedClock("2026-11-28T04:00:00Z");

        var signed = fixture.signedPaymentWithFreshNonce();
        fixture.send(client, signed)
            .expectStatus().is2xxSuccessful();

        fixture.send(client, signed)
            .expectStatus().isUnauthorized()
            .expectBody()
            .jsonPath("$.code")
            .isEqualTo("AUTHENTICATION_FAILED");

        fixture.assertOneBusinessCommit();
    }
}
~~~

Đây cũng là skeleton. Với WebFlux, cần assert Redis errors không bị `onErrorResume(...firstUse)`, pooled `DataBuffer` giải phóng đúng và Reactor Security Context không rò sang request kế tiếp.

## 30. Ma trận kiểm thử chọn error semantics

| ID | Tình huống | Public semantics và bằng chứng cần có |
| --- | --- | --- |
| ERR-01 | Thiếu HMAC signature trên protected route | 401 chung; không controller |
| ERR-02 | Unknown key ID | 401 chung, không reveal key existence |
| ERR-03 | Known key nhưng MAC sai | 401 body/code tương đương ERR-02 |
| ERR-04 | Key REVOKED, MAC đúng | 401 chung; no principal |
| ERR-05 | Key DISABLED/EXPIRED | 401 chung; no business |
| ERR-06 | Client owner disabled | 401 chung theo policy |
| ERR-07 | Suite không allowed cho credential | 401 chung; không fallback |
| ERR-08 | MAC length/Base64 sai | Generic authn reject theo contract |
| ERR-09 | Timestamp quá cũ | 401; internal freshness reason |
| ERR-10 | Timestamp quá xa tương lai | 401; internal freshness reason |
| ERR-11 | Timestamp malformed | 401/400 theo profile đã document |
| ERR-12 | Timestamp/nonce bị sửa sau ký | MAC mismatch; không claim nonce |
| ERR-13 | R1 đúng MAC, nonce mới | Positive authentication pass |
| ERR-14 | R2 exact copy của R1 trong window | 401; internal REPLAY_DETECTED |
| ERR-15 | MAC sai trước rồi MAC đúng cùng nonce | MAC sai không poison nonce |
| ERR-16 | Redis trả ALREADY_USED | 401 chung, no business |
| ERR-17 | Redis command timeout trước commit | 503, fail closed |
| ERR-18 | Redis commit nhưng lost ACK | 503/UNKNOWN, no business |
| ERR-19 | Credential registry unavailable | 503, không tự kết luận key unknown |
| ERR-20 | Secret store unavailable | 503, không dùng default secret |
| ERR-21 | HSM/crypto provider unavailable | 503/fail closed, không “bad MAC” |
| ERR-22 | Redis 503 được gateway biến thành 401 | Test FAIL: sai nguyên nhân |
| ERR-23 | V1 key revoked nhưng verifier thử fallback | Test FAIL: key confusion |
| ERR-24 | V2 MAC sai, tự fallback V1 | Test FAIL: downgrade |
| ERR-25 | Duplicate key ID headers | 400 hoặc generic 401 theo contract; không ambiguous |
| ERR-26 | Content-Length framing conflict | 400; không vào business |
| ERR-27 | Signed header count quá lớn | Reject theo bounds; không DoS |
| ERR-28 | Body vượt limit | 413; không hash truncated body |
| ERR-29 | Content-Type không được hỗ trợ | 415 theo route policy |
| ERR-30 | JSON hợp lệ nhưng domain value sai | 422/400 domain validation theo contract |
| ERR-31 | Authenticated principal thiếu scope | 403 |
| ERR-32 | Principal thiếu grant tenant khác | 403/404 theo policy |
| ERR-33 | Resource tenant khác bị 404 che existence | Body/timing không leak rõ |
| ERR-34 | Resource ID không tồn tại | 404 tương thích resource hiding |
| ERR-35 | Body đổi nhưng giữ MAC | 401; authentication failure |
| ERR-36 | Header signed tenant đổi nhưng giữ MAC | 401; integrity failure |
| ERR-37 | Authenticated intent key trùng payload khác | 409 business conflict |
| ERR-38 | Exact replay nonce nhưng cùng idempotency key | 401, không đẩy tới business 409 |
| ERR-39 | Retry với nonce mới, same intent/payload | Authn pass, business result theo idempotency |
| ERR-40 | Retry POST sau timeout, unknown outcome | Không double side effect |
| ERR-41 | Rate limit trước HMAC | 429 có thể xảy ra; không tính replay proof |
| ERR-42 | Rate limit sau authentication | 429, nonce semantics được document |
| ERR-43 | Có Retry-After đáng tin | Header parse được, không chứa key/secret |
| ERR-44 | Retry-After không xác định | Không bịa ETA |
| ERR-45 | Unknown key vs bad MAC khác public body | Test FAIL: credential oracle |
| ERR-46 | Public error chứa expected MAC | Test FAIL: secret-derived leak |
| ERR-47 | Public error chứa nonce state/key version | Test FAIL theo privacy policy |
| ERR-48 | Public JSON chứa stack trace/vault URL | Test FAIL |
| ERR-49 | Public error phản chiếu raw requestId/header | Reject/sanitize injection |
| ERR-50 | 401 thiếu WWW-Authenticate theo auth contract | Test FAIL về challenge semantics |
| ERR-51 | 401 challenge không được định nghĩa | Test FAIL về interoperability |
| ERR-52 | Servlet exception ném trước DispatcherServlet | EntryPoint xử lý đúng |
| ERR-53 | AccessDeniedHandler trả nhầm 401 | Test FAIL: phải authz semantics |
| ERR-54 | WebFlux Mono.empty từ Redis bị coi authenticated | Test FAIL |
| ERR-55 | WebFlux DataBuffer bị giữ sau cancel | Test FAIL: resource leak |
| ERR-56 | Gateway rewrite signed external/internal URI | Positive signer vector pass; negative rõ |
| ERR-57 | HTTP/1.1 ↔ HTTP/2 duplicate header disagreement | Reject ambiguity |
| ERR-58 | Direct backend bypass gateway trust | Reject theo mTLS/assertion policy |
| ERR-59 | Revoked credential cache stale trên region | Security test FAIL |
| ERR-60 | Nonce TTL ngắn hơn signature lifetime | Replay retention test FAIL |
| ERR-61 | Redis multi-region cho hai FIRST_USE | Vi phạm global guarantee đã công bố |
| ERR-62 | 401 spike do SDK reuse nonce | Internal replay reason, không đổ lỗi MAC |
| ERR-63 | 503 auth dependency nhưng SLO bỏ qua | Monitoring test FAIL |
| ERR-64 | Public error schema thay đổi ở gateway | Contract/parity test FAIL |

### Phân tầng kiểm thử

- **Unit/policy:** ERR-01–12, 15–16, 23–25, 29–38, 45–51; mapping, signed fields, secret-safe output.
- **Spring integration:** ERR-13–22, 27–28, 31–44, 52–55; filter, entry points, Reactor and business state.
- **Gateway/E2E:** ERR-22, 56–59, 64; forwarded identity, raw target, HTTP protocol and response rewriting.
- **Distributed/fault injection:** ERR-17–21, 40, 60–61, 63; Redis failover/secret manager, retries, SLO.
- **Operations:** ERR-62–63; alert triage, runbooks và client SDK support.

Một test có thể thuộc nhiều tầng; không cần viết mỗi ID thành một class. Điều quan trọng là bảo đảm **failure được phân loại đúng và không mở đường authentication/business ngoài ý muốn**.

## 31. Di trú từ error contract cũ sang contract mới

Một hệ thống cũ có thể đang:

- Trả `400` cho mọi HMAC invalid, kể cả revoked key và replay.
- Trả `401` cho Redis outage.
- Trả `200 {"success":false}` cho forbidden tenant.
- Trả `409 NONCE_REUSED` công khai.
- Trả HTML 502 khác nhau qua mỗi gateway.

Khi thay contract, cần cân nhắc **SDK backward compatibility** và khả năng retry tự động. Một lộ trình:

1. **Inventory:** thống kê status/body/challenge hiện có ở từng route/client SDK/gateway.
2. **Define:** phê duyệt taxonomy nội bộ, public code/status map và privacy constraints.
3. **Golden contract tests:** tạo fixture cho valid MAC, invalid MAC, replay, store outage, tenant denied và business conflict.
4. **Instrument:** thu reason nội bộ trước thay đổi public behavior; tránh log secrets.
5. **Client coordination:** cập nhật SDK retry/idempotency logic, không hạ signing suite khi 401.
6. **Canary:** bật error adapter mới cho cohort server-side; đo 4xx/5xx và behavior client.
7. **Gateway parity:** bảo đảm 401/403/503 không bị rewrite hoặc cache sai.
8. **Rollout:** áp dụng theo version/route/policy có quản lý, không dựa header client tự bật “new auth”.
9. **Retire:** loại bỏ fallback trả lỗi cũ và test trên mọi verifier/region.
10. **Observe:** alert bị che 503, unknown nonce store, revoked-key acceptance và client retry storms.

### Một điểm cần đặc biệt tránh

**Không đổi Redis outage từ 401 sang 503 nhưng vẫn để verifier fail open.** Status mới phải xuất phát từ một **quyết định fail closed thật**. Tương tự, một bộ handler trả 401 đẹp mắt nhưng HMAC filter không chạy trên một route thì vẫn là bypass.

### Rollback có giữ security không?

Nếu code mới lỗi serialization, có thể rollback response adapter nhưng **không rollback key revoke/anti-replay/tenant authorization policy**. Nếu version cũ có lỗ hổng public oracle nghiêm trọng, rollback cần assessment và phương án an toàn, không tự mở lại vì số liệu 4xx tăng.

## 32. Tình huống thực hành: phân loại 10 lỗi xảy ra trong cùng hệ thống

Một dịch vụ Spring Boot 3 có HMAC gateway + Redis shared nonce store. Trong cùng ngày, on-call ghi nhận:

~~~text
A. Client partner-a gửi signature sai -> 401 BAD_SIGNATURE
B. Client thay keyId sang một ID chưa tồn tại -> 404 UNKNOWN_KEY
C. Redis timeout khi SET NX, request được 401 INVALID_NONCE
D. R1 tạo payment thành công; R2 exact replay trả 409 DUPLICATE_PAYMENT
E. Tenant-a ký đúng request đọc resource của tenant-b -> 401
F. Gateway B chuyển response backend 503 thành 502 HTML + hostname
G. Payment body 2 MiB vượt limit nhưng được buffer toàn bộ trước reject
H. Key K3 bị revoke nhưng cache một pod còn ACTIVE; request trả 200
I. Client retry payment timeout bằng cùng nonce/signature
J. WebFlux filter onErrorResume Redis lỗi -> Mono.just(FIRST_USE)
~~~

Hãy giải thích:

1. Vì sao A/B không nên có public message giúp dò key existence?
2. C phải được phân loại thế nào nếu Redis outcome UNKNOWN?
3. D có thể che lỗi replay guard ra sao?
4. E là lỗi authentication hay authorization, và khi nào chọn 404?
5. F cần error translation và gateway observability như thế nào?
6. G cần limit ở bước nào so với HMAC body digest?
7. H là security incident loại nào và sao không được coi là “cache issue bình thường”?
8. I nên retry bằng nonce mới và idempotency key như thế nào?
9. J có nguy cơ tạo authentication success không có nonce claim ra sao?
10. Public response code/schema cho A–J nên chuẩn hóa thế nào?
11. Internal reason nào cần ghi nhưng không public?
12. Test nào chứng minh **không có side effect thứ hai** và **không có authenticated principal khi dependency unavailable**?

**Định hướng:** gom lỗi key/MAC/replay vào 401 chung; Redis UNKNOWN → 503 fail closed; tenant grants → 403/404 sau authn; same business intent → idempotency layer riêng; gateway sanitize upstream failures; 413 với bounded body capture; revoked key phải reject ở mọi pod. Sửa SDK retry để nonce/signature mới, giữ business idempotency key khi intent không đổi.

## 33. Checklist thiết kế error semantics trước production

- [ ] Đã có bảng taxonomy nội bộ cho framing, HMAC envelope, key state, MAC, timestamp, replay, dependency, authorization và business.
- [ ] Public HTTP status/code/body được version hóa và review, không map trực tiếp raw exception messages.
- [ ] Unknown/revoked key, MAC sai, timestamp invalid, nonce used có public authentication error thống nhất theo threat model.
- [ ] 401 kèm `WWW-Authenticate` phù hợp scheme thực tế; không quảng bá challenge HMAC tự bịa là chuẩn chung.
- [ ] Response chứa `application/problem+json`, status/code ổn định và `Cache-Control: no-store` khi cần.
- [ ] Public body không chứa secret, expected MAC, full signature, canonical raw bytes, nonce state, key existence hoặc stack trace.
- [ ] 400 cho malformed framing/duplicate security headers theo contract, không để request-smuggling ambiguity.
- [ ] 413 cho body quá limit trước unbounded buffering, không hash/trust truncated body.
- [ ] 415/422 dùng cho media/domain semantics khi phù hợp, không nhầm với signature failure.
- [ ] Credential registry/KMS/Redis/HSM timeout/UNKNOWN phải **fail closed**, không báo 401 giả hoặc dùng default secret.
- [ ] Replay key đã dùng → authentication reject, không business 409; business idempotency conflict mới thuộc 409.
- [ ] Timestamp/nonce được ký, validate freshness và atomic nonce claim **sau MAC đúng**.
- [ ] Nonce claim có FIRST_USE/ALREADY_USED/UNKNOWN/NOT_EXECUTED semantics để test/audit.
- [ ] TTL retention bao phủ toàn bộ signature acceptance window, including clock skew và multi-node guarantee.
- [ ] Authenticated principal đến từ exact credential registry, không tin client-provided identity/tenant header.
- [ ] HMAC pass chưa đủ: authorization tenant/action/resource chạy độc lập, 403/404 theo privacy policy.
- [ ] 429 limiter trước/sau authn có nonce semantics và SDK retry docs rõ ràng.
- [ ] Mọi retry tạo timestamp/nonce/signature mới, business idempotency key được giữ khi cùng intent.
- [ ] Gateway/proxy giữ đúng signed URI/header/body contract và không rewrite 401/403/503 mơ hồ.
- [ ] Gateway/backend không claim cùng client nonce hai lần hoặc tin identity headers giả.
- [ ] Key rotation/revocation và signing suite không dùng fallback nhiều secret/algorithms.
- [ ] Servlet `AuthenticationEntryPoint` xử lý auth failures trước controller; `AccessDeniedHandler` xử lý authz.
- [ ] WebFlux `ServerAuthenticationEntryPoint`, reactive nonce claim và `DataBuffer` lifecycle được test.
- [ ] Lỗi security không làm request đi qua fallback/unprotected route.
- [ ] Internal reason/audit có quyền truy cập, low-cardinality metric labels, không lộ key ID/nonce/signature.
- [ ] Có SLO/alerts riêng cho invalid client proofs vs auth dependency failures.
- [ ] Test 401 chống credential oracle và 503 dependency, không chỉ kiểm tra status.
- [ ] Test positive R1 + exact replay R2 trong timestamp window, assert nonce state và no second side effect.
- [ ] Wrong MAC không poison nonce, Redis timeout không tạo principal, key revoked không được accepted.
- [ ] Có contract tests cho MVC/WebFlux, gateway HTTP/1.1↔HTTP/2, tenant masking và business idempotency.
- [ ] Canary/migration có versioned public error policy và SDK compatibility plan, không rollback security fixes.
- [ ] Runbook sự cố chỉ dẫn khắc phục theo **internal reason**, không yêu cầu client tiết lộ raw shared secret.

**Chọn error semantics là một phần của thiết kế bảo mật HMAC, không chỉ là việc chọn status code.** Một hệ thống đúng phải phân biệt authentication thất bại (401), authorization bị từ chối (403/404), business conflict (409) và dependency không đủ khả năng xác thực (503); đồng thời duy trì public response tối giản, internal telemetry đủ dùng, nonce chống replay nguyên tử, key lifecycle, gateway trust và hợp đồng retry an toàn. Giá trị của thiết kế được chứng minh khi **mỗi failure bị chặn ở đúng tầng, không rò thông tin và không tạo principal hoặc side effect ngoài ý muốn**.

### Nonce poisoning

Verifier **không claim nonce khi MAC sai**. Nếu attacker gửi N với MAC sai rồi client thật dùng N hợp lệ, request thật phải được phép first-use. Test phải kiểm tra store untouched sau bad MAC, không chỉ 401.
