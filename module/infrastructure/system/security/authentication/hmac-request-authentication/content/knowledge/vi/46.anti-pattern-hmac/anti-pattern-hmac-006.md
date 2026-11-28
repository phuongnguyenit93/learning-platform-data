# Không chống replay: anti-pattern HMAC xác thực đúng chữ ký nhưng vẫn cho phát lại request

## 1. Bối cảnh và tình huống gây thiệt hại

Trong mô-đun `SECURITY_AUTHENTICATION_HMAC_REQUEST_AUTHENTICATION`, client ký HTTP request bằng **HMAC với shared secret** trên canonical request. Hợp đồng có thể bao gồm method, URI/query, signed headers và body digest. Verifier tìm đúng key ID, tính HMAC bằng secret tương ứng và so sánh với signature của client. Đó mới là điều kiện về **tính xác thực và tính toàn vẹn của bằng chứng**.

**Anti-pattern “Không chống replay”** xuất hiện khi server kết luận: *chữ ký HMAC đúng thì request này được phép chạy tiếp*, nhưng không kiểm tra bằng chứng vừa được dùng trước đó hay chưa. Một bản sao của request đã ký có thể tạo ra **cùng HMAC hợp lệ** ở lần thứ hai, thứ ba, thứ một nghìn; kẻ phát lại không cần biết secret.

Ví dụ API tạo lệnh chuyển tiền của đối tác:

~~~http
POST /api/hmac/payments HTTP/1.1
Host: api.example.test
Content-Type: application/json
X-Client-Id: partner-a
X-Key-Id: partner-a-prod-k004
X-Timestamp: 2026-11-28T04:00:00Z
X-Nonce: 77ae7eba-9be7-4b38-b5a7-a53a9f98a492
X-Signature: <base64-hmac-signature>

{"paymentId":"p-101","amount":250000,"currency":"VND"}
~~~

Giả sử request này được ký đúng bằng secret K4, được proxy hoặc client log lại cùng headers/body, rồi bị gửi lại. Nếu server chỉ kiểm tra HMAC mà không chống replay, nhiều request có thể cùng được xác thực thành `partner-a` và tạo **nhiều giao dịch**. Một hệ thống có business idempotency tốt có thể ngăn trùng giao dịch, nhưng **không làm biến mất lỗi authentication replay** ở các API khác.

### Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt **HMAC authenticity/integrity** với **freshness, one-time use** và **authorization**.
2. Chỉ ra vì sao timestamp-only, nonce-only hoặc `X-Request-Id` không được ký không đủ chống replay.
3. Thiết kế invariant: chữ ký đúng, timestamp hợp lệ, **atomic first-use nonce** mới được tạo principal.
4. Hiểu thứ tự xác minh MAC trước khi claim nonce để ngăn **nonce poisoning**.
5. Thiết kế TTL, namespace, key rotation, multi-node/gateway và fail-closed khi replay store lỗi.
6. Kiểm thử Spring Security 6 Servlet, WebFlux, retry/idempotency, concurrency và no side effects.
7. Có quy trình phát hiện, giảm thiểu và di trú từ hệ thống đã mắc anti-pattern.

## 2. HMAC không bảo đảm request chỉ được dùng một lần

HMAC-SHA256 có dạng:

\[
\mathrm{tag} = \operatorname{HMAC}_{K}(\mathrm{canonicalRequestBytes})
\]

Khi verifier nhận được đúng `canonicalRequestBytes` và tag tương ứng dưới cùng secret `K`, kết quả so sánh vẫn đúng bất kể đây là lần nhận thứ mấy.

| Thuộc tính | HMAC đơn thuần bảo vệ? | Kiểm soát bổ sung |
| --- | --- | --- |
| Client có bằng chứng biết shared secret | Có điều kiện, khi key được giữ bí mật và registry chọn đúng key | Key lifecycle, exact key lookup |
| Method/URI/body/header không bị sửa | Có, **chỉ với những trường thực sự được ký** | Canonical contract đầy đủ |
| Bằng chứng còn mới | **Không** | Timestamp + server Clock/window |
| Bằng chứng chưa từng dùng | **Không** | Nonce + stateful atomic claim |
| Request không bị copy từ log/proxy | **Không** | TLS, log redaction, access control |
| Client được quyền tenant/resource | **Không** | Authorization sau authentication |
| Giao dịch không tạo side effect trùng | **Không** | Business idempotency/transaction semantics |
| Key chưa hết hạn hoặc bị revoke | **Không** | Credential status/expiry/revocation |

**Bẫy suy luận:** chữ ký vẫn đúng khi request bị phát lại vì dữ liệu không bị thay đổi; đó là điều HMAC được thiết kế để chứng minh. Không thể “tăng độ mạnh HMAC từ SHA-256 lên SHA-512” để tự tạo tính một-lần.

Cần phân biệt **replay của một request hợp lệ** với **forge request mới**. Replay tận dụng một bằng chứng đã tồn tại; không cần tìm secret, không cần tạo MAC mới. Cơ chế chống replay vì thế phải gắn với **ngữ cảnh thời gian và trạng thái sử dụng**.

## 3. Threat model: bản sao chữ ký có thể đến từ đâu?

HTTPS/TLS giảm nguy cơ người ngoài nghe lén trên đường truyền, nhưng không loại bỏ mọi nơi một request đã được ký có thể bị lộ hoặc được tái gửi:

- Access log/WAF/APM/tracing ghi signature, signed headers và raw body.
- Browser/devtools, máy chủ đối tác, CI artifacts hoặc debug proxy được cấp quyền quá rộng.
- Một gateway hoặc internal service bị xâm nhập đọc được request sau TLS termination.
- Client SDK retry nguyên request sau timeout thay vì tạo nonce/signature mới.
- Message queue, job runner hoặc reverse proxy tự retry HTTP POST.
- Attacker có quyền gửi lại request ở một connection/instance/region khác.
- Lỗi double dispatch/double filter hoặc redelivery ở hạ tầng tự phát ra một lần xử lý nữa.

Không cần mô phỏng tấn công vào hệ thống không được cấp phép. Thực hành bằng **test credentials**, sandbox endpoints, request fixtures và controlled load/fault injection.

### Điều kiện kẻ phát lại cần có

Một attacker thường chỉ cần bản sao đủ những trường tham gia ký: method, raw target, signed headers, timestamp/nonce, signature và body. Nếu thiếu body trong hệ thống ký body, họ có thể không tái hiện request. Nhưng thiết kế **không được dựa vào hy vọng body không bao giờ bị sao chép**.

Nếu HMAC credential bị lộ, kẻ tấn công có thể ký request *mới* — tình huống nghiêm trọng hơn replay và cần revoke/rotate key. Replay test không thay thế incident response khi secret bị lộ.

## 4. Anti-pattern điển hình: chỉ tính lại MAC rồi cho request qua

Đoạn mã sau **cố tình sai** về mặt chống replay:

~~~java
// SAI: minh họa một AuthenticationProvider thiếu freshness.
Authentication authenticate(HmacAttempt attempt) {
    Credential credential =
        registry.findExact(attempt.keyId());

    if (credential == null || !credential.active()) {
        throw new BadCredentialsException("authentication_failed");
    }

    byte[] canonical = canonicalizer.build(attempt);
    byte[] expected = hmacSha256(
        credential.secretBytes(), canonical);

    if (!MessageDigest.isEqual(
            expected, attempt.signatureBytes())) {
        throw new BadCredentialsException("authentication_failed");
    }

    // BUG: không có timestamp window + nonce claim.
    return authenticatedPrincipal(credential);
}
~~~

Mặc dù đã kiểm tra secret đúng K4, MAC và credential ACTIVE, code này không có bằng chứng rằng request chưa được sử dụng. Nếu controller tạo payment sau authentication, bản sao HTTP thứ hai vẫn chạy qua filter.

**Dấu hiệu anti-pattern:**

- Không thấy bất kỳ `nonceStore`/replay-guard nào trong đường xác thực.
- Có header timestamp nhưng verifier chỉ đưa nó vào MAC rồi không kiểm tra giờ.
- Có nonce nhưng chỉ validate UUID format, không kiểm tra **chưa từng claim**.
- Có replay cache nhưng chỉ nằm trong một JVM, không chia sẻ giữa instances.
- Có `GET nonce` rồi `SET nonce`, không nguyên tử.
- Có branch `catch (RedisException) { return authenticated; }`.
- Dùng `signature.equals(previousSignature)` trong một cache TTL nhỏ không có scope/consistency.
- Dựa vào payment idempotency để nói “đã chống replay”, bỏ quên endpoint khác.

## 5. Diễn tiến tấn công: hai request, cùng chữ ký

~~~mermaid
sequenceDiagram
    participant C as HMAC Client
    participant G as Gateway
    participant V as Verifier thiếu replay guard
    participant B as Business Service
    C->>G: R1 = request + signature hợp lệ
    G->>V: R1
    V->>V: HMAC(K, canonical(R1)) = supplied
    V->>B: Authenticated, thực hiện nghiệp vụ
    B-->>C: Thành công
    Note over G: Một bản sao R1 bị giữ lại
    G->>V: R2 = exact copy của R1
    V->>V: HMAC(K, canonical(R2)) = supplied
    V->>B: Authenticated lần thứ hai
    Note over B: Side effect có thể xảy ra lần hai
~~~

Trong ví dụ, signature không bị giả mạo; cả R1 và R2 đều có **HMAC đúng**. Mã xử lý controller nhận authenticated principal giống nhau. Đây là lý do cần test **response + replay store + business side effects**, không chỉ test helper HMAC.

Một HTTP response 409 do payment duplicate ở business layer **không chứng minh** HMAC replay đã bị chặn ở authentication. Cũng vậy, 401 ở R2 vì timestamp hết hạn không chứng minh nonce guard có tác dụng.

## 6. Anti-pattern: “đã có timestamp, không cần nonce”

Một thiết kế có thể thêm `X-Timestamp` vào canonical bytes và chỉ kiểm tra:

\[
|t_{\mathrm{server}}-t_{\mathrm{signed}}|\le W
\]

Khi `W=5 phút`, một request có timestamp còn trong cửa sổ vẫn có thể bị gửi lại **nhiều lần trong khoảng đó**. Timestamp làm giảm thời gian sử dụng một bằng chứng, **không** làm bằng chứng chỉ được dùng một lần.

~~~text
04:00:00 R1 timestamp=04:00:00, MAC đúng -> accepted
04:00:03 R2 y hệt, timestamp=04:00:00 -> accepted
04:00:04 R3 y hệt, timestamp=04:00:00 -> accepted
04:06:00 R4 y hệt -> rejected vì expired
~~~

**Biện pháp sửa:** timestamp cần được ký, kiểm tra window/clock skew; **nonce độc nhất được ký** phải được lưu trong một replay store và claim **nguyên tử**. Timestamp có tác dụng giới hạn **thời gian giữ state**, còn nonce tạo bằng chứng first-use trong thời gian đó.

### Test timestamp-only

1. Dùng fixed Clock tại `04:00:00Z`, tạo request MAC hợp lệ với timestamp cùng giờ.
2. Gửi R1 và xác nhận positive path thành công.
3. Gửi lại chính R1 ngay, không đổi chữ ký.
4. Nếu R2 vẫn đi vào nghiệp vụ, server đang thiếu replay protection.
5. Kiểm tra riêng timestamp ở `04:05:01Z`/`03:54:59Z` theo acceptance window; không trộn test hết hạn với test nonce.

Không kết luận một hệ thống đã an toàn chỉ vì request cũ 24 giờ bị 401.

## 7. Anti-pattern: nonce được sinh nhưng không được kiểm tra trạng thái

Một client gửi:

~~~http
X-Timestamp: 2026-11-28T04:00:00Z
X-Nonce: 77ae7eba-9be7-4b38-b5a7-a53a9f98a492
~~~

Nếu verifier chỉ kiểm tra `X-Nonce` là UUIDv4, header đó **không ngăn replay**. R2 giữ nguyên nonce và vẫn hợp lệ về format.

Những cách triển khai sai khác:

~~~java
// SAI: chỉ kiểm tra tồn tại/định dạng.
if (nonce != null && nonce.matches("[0-9a-f-]{36}")) {
    return authenticated;
}

// SAI: chỉ kiểm tra nonce là ngẫu nhiên, không lưu state.
// Server không có thông tin rằng nonce này đã xuất hiện.
~~~

**Nonce phải được ràng buộc vào signature và được theo dõi** theo scope của credential/client đã xác thực. Một nonce random 128-bit làm xác suất **va chạm tình cờ** nhỏ, nhưng **không thay thế server-side used-once state**. Attack replay sử dụng **cùng nonce**, không cần đoán nonce mới.

### Nếu client tái sử dụng nonce

Một số SDK sinh nonce một lần khi khởi tạo process rồi dùng cho mọi request, hoặc dùng timestamp theo giây làm nonce. Khi server có replay guard, request hợp lệ thứ hai bị từ chối dù nội dung khác. Client cần tạo nonce mới mỗi attempt theo contract. Cần đo **collision/reuse** bằng test và tài liệu SDK, không tự động bỏ nonce guard để tăng tỷ lệ thành công.

## 8. Anti-pattern: timestamp/nonce không được ký

Một hệ thống có thể lưu nonce nhưng lại **không đưa nó vào canonical request**. Khi đó attacker có thể copy request, thay nonce ở header mà **giữ nguyên HMAC**. Nếu server chấp nhận MAC không ràng buộc nonce, replay guard coi đây là nonce mới.

~~~text
R1:
  nonce=N1
  HMAC(K, method || path || bodyHash) = tag1

R2:
  nonce=N2   # attacker thay N1 bằng N2
  HMAC(K, method || path || bodyHash) = tag1   # vẫn khớp
~~~

Tương tự, nếu timestamp không được ký, attacker có thể đặt một timestamp mới khi bằng chứng cũ sắp hết hạn. Nếu key ID hoặc suite version không được ràng buộc đúng, có thể xảy ra key/algorithm confusion.

**Hợp đồng sửa:** canonical request bắt buộc chứa những giá trị chính xác của timestamp, nonce, key ID/version, method, target và mọi signed fields theo protocol đã được review. Signature input phải được tạo **từ request thực**, không tin chuỗi canonical do client tự gửi.

### Test tampering độc lập

| Ca | Thao tác | Kỳ vọng |
| --- | --- | --- |
| R1 valid, N1 | MAC đúng, nonce mới | First use accepted |
| Giữ MAC, đổi N1→N2 | Nonce bị thay sau khi ký | Signature mismatch |
| Giữ MAC, đổi timestamp | Timestamp bị thay sau khi ký | Signature mismatch |
| Giữ MAC, đổi body một byte | Body integrity | Signature mismatch |
| Giữ MAC, đổi raw URI/query | Target integrity | Signature mismatch |
| Giữ MAC, đổi key ID/suite | Identity/protocol binding | Reject |
| Gửi lại nguyên R1 | MAC vẫn đúng | **Replay rejected** |

Khi thử tamper một trường, phải bảo đảm **trường đó thuộc signed scope** của hợp đồng. Nếu nó được cố ý bỏ khỏi signature, test phải ghi rõ threat model và biện pháp binding khác.

## 9. Anti-pattern: kiểm tra nonce bằng “đọc rồi ghi”

Mã giả sau không nguyên tử:

~~~java
// SAI: race window giữa hai thao tác.
if (!nonceStore.exists(scope, nonce)) {
    nonceStore.put(scope, nonce, expiresAt);
    return authenticated;
}
return replayRejected;
~~~

Hai request đồng thời trên hai gateway:

~~~mermaid
sequenceDiagram
    participant A as Request A
    participant B as Request B
    participant S as Shared Store
    A->>S: EXISTS(K4,N)?
    B->>S: EXISTS(K4,N)?
    S-->>A: false
    S-->>B: false
    A->>S: PUT(K4,N)
    B->>S: PUT(K4,N)
    A-->>A: authenticated
    B-->>B: authenticated
~~~

Đây là lỗi **time-of-check/time-of-use (TOCTOU)**. Dùng `ConcurrentHashMap.putIfAbsent` trong **một JVM** có thể giải quyết race local, nhưng không có tác dụng khi nhiều instance độc lập.

### Primitive nguyên tử

Ví dụ Redis:

~~~redis
SET hmac:nonce:<digest-of-scope-and-nonce> 1 NX PX 660000
~~~

Lệnh `SET` có `NX` và `PX` trong một thao tác: chỉ một caller tạo key thành công. Kết quả cần phân biệt:

- `FIRST_USE`: SET thực sự thành công.
- `ALREADY_USED`: key đã tồn tại.
- `UNKNOWN`: timeout, network loss, failover hoặc không đủ thông tin.

Đây là **một phương án**, không phải bằng chứng tự động có global at-most-once với mọi topology Redis. Replication/failover/eviction/region độc lập vẫn cần threat model và test.

## 10. Anti-pattern: chỉ lưu nonce ở bộ nhớ một instance

Một `HashSet` static không phải replay guard phân tán. Nếu request đầu được load balancer tới node A, request thứ hai tới node B, hai node có thể đều thấy nonce “mới”.

~~~text
Client/attacker
   ├── R1 -> Gateway A -> localSetA.add(N) = true
   └── R2 -> Gateway B -> localSetB.add(N) = true
                                 |
                        Hai lần authentication pass
~~~

Cần có **shared authority** nhất quán trong phạm vi chống replay được tuyên bố: ví dụ một datastore cho mọi verifier của credential hoặc một hệ thống phân vùng credential có routing/consistency đã được chứng minh.

| Phạm vi deployment | Kiểm tra bắt buộc |
| --- | --- |
| Một JVM | Local atomicity là chưa đủ cho future scale |
| Nhiều pods trong một region | Shared nonce scope, atomic claim |
| Nhiều regions | Rõ guarantee global hay region-bound |
| Redis primary + replica | Tránh quyết định first-use dựa trên replica stale |
| Failover | Write ACK có thể mất theo consistency model |
| Gateway + backend | Không claim cùng nonce hai lần trên cùng key |
| Disaster recovery | Khôi phục replay state đủ retention |

**Không tự fallback sang local memory** khi shared replay store gặp lỗi. Điều đó biến lỗi hạ tầng thành một cửa sổ tấn công.

## 11. Anti-pattern: TTL ngắn hơn thời gian chữ ký còn hợp lệ

Nếu verifier chấp nhận timestamp trong cửa sổ đối xứng:

\[
t_{\mathrm{server}} - W \le t_{\mathrm{signed}}
\le t_{\mathrm{server}} + W
\]

thì một request có timestamp ở mép tương lai khi nhận lần đầu có thể còn hợp lệ gần **2W** tính từ lúc claim đầu. Nếu Redis TTL chỉ bằng W, nonce record biến mất **trước khi bằng chứng hết giá trị**.

Ví dụ:

~~~text
W = 5 phút, clock server lúc claim = 04:00
Timestamp được ký = 04:05 (vẫn hợp lệ)
Nonce N được claim lúc 04:00, TTL chỉ 5 phút

04:05:01  Nonce đã hết hạn trong Redis.
04:05:01  Timestamp=04:05 vẫn hợp lệ.
          Exact replay R1 có thể thành first-use lần hai.
~~~

Một cách bảo thủ với TTL tính từ lúc claim:

\[
TTL_{\mathrm{nonce}} \ge 2W + \varepsilon
\]

với `ε` bù clock skew/precision và đặc thù hệ thống. Với `W=5 phút`, `TTL=11 phút` có thể là **ví dụ triển khai**, không phải chuẩn chung. Nếu expiry tính theo timestamp ký:

~~~text
nonceExpiresAt >= signedTimestamp + W + safetyMargin
~~~

phải đảm bảo record vẫn tồn tại tới thời điểm cuối cùng request còn có thể được chấp nhận.

### Một nuance quan trọng

Nếu signed timestamp chỉ được phép lệch **về quá khứ** (không cho timestamp tương lai), phương trình TTL khác. Không sao chép máy móc 2W vào mọi policy; phải chứng minh từ **chính cửa sổ acceptance và replication/clock model** đang dùng.

### Test TTL

1. Gửi R1 ở biên timestamp tương lai hợp lệ, nonce N mới.
2. Tiến test Clock tới sau điểm store hết TTL nhưng trước lúc timestamp hết hiệu lực.
3. Gửi lại y nguyên R1.
4. Nếu R2 được authenticated, TTL/retention đang không đủ.
5. Kiểm thử cả lúc đổi region, failover, eviction và policy window được cập nhật.

## 12. Anti-pattern: namespace nonce không ràng buộc principal đáng tin

Một thiết kế có thể tạo replay key từ các header do client tự khai:

~~~text
key = tenantHeader + ":" + nonceHeader
~~~

Nếu tenant không được xác thực/bind vào MAC hoặc client có thể đổi nó để tạo namespace mới, một nonce đã sử dụng có thể được chấp nhận dưới key khác.

Một scope thường gặp:

~~~text
replayScope = credentialIdFromServerRegistry
replayKey = HMAC-or-SHA256(encodeLengthPrefixed(
    replayScope, signedNonce))
~~~

`HMAC-or-SHA256` ở đây mô tả lựa chọn encoding/digest để tránh lưu raw identifiers trong key; **không phải yêu cầu bắt buộc sử dụng HMAC** cho Redis key. Quan trọng hơn là tuple/namespace **không có ambiguity**: dùng length-prefix hoặc format canonical, không nối chuỗi dễ trùng.

Các lựa chọn có trade-off:

| Scope | Hệ quả |
| --- | --- |
| `(credentialId, nonce)` | Ngăn reuse trong một credential/key version |
| `(clientId, nonce)` từ trusted registry | Có thể ngăn reuse xuyên key rotation cùng client |
| `(credentialId, suiteId, nonce)` | Tạo namespace riêng cho mỗi suite, cần threat model cross-version replay |
| `(tenant-header, nonce)` tùy ý | Có thể bị bypass nếu tenant claim thiếu binding |
| `(raw signature)` | Signature có thể đổi khi request được ký lại dù nonce cũ |
| `(IP address, nonce)` | Dễ bypass qua IP/proxy; không phải principal identity |

**Không mở namespace chỉ để tăng khả năng “retry thành công”**. Nếu một client cần dùng cùng business intent nhiều lần, thiết kế idempotency riêng thay vì làm yếu replay scope.

## 13. Anti-pattern: claim nonce trước khi xác minh MAC

Một “bản vá” phổ biến sau khi phát hiện replay là ghi nonce ngay khi parse request:

~~~java
// SAI: attacker chiếm nonce dù không biết secret.
if (nonceStore.claim(keyId, signedNonce)) {
    verifyHmacOrThrow(request);
    return authenticatedPrincipal;
}
throw new BadCredentialsException("replay");
~~~

Nếu attacker biết/dự đoán nonce N của request hợp lệ (ví dụ client dùng timestamp hoặc counter), họ có thể gửi N kèm chữ ký sai trước client. Server ghi N, rồi request thật có MAC đúng bị từ chối. Đây là **nonce poisoning**, một dạng denial-of-service.

### Thứ tự an toàn

~~~mermaid
flowchart TD
    A["HTTP request"] --> B["Parse strict headers + body-size limit"]
    B --> C{"Timestamp/nonce đúng format và window?"}
    C -->|Không| X["Authentication failure"]
    C -->|Có| D["Lookup exact key ID + ACTIVE state"]
    D --> E["Canonical bytes theo signing contract"]
    E --> F{"HMAC đúng secret của key ID?"}
    F -->|Không| X
    F -->|Có| G["Atomic claim signed nonce"]
    G -->|FIRST_USE| H["Trusted authenticated principal"]
    G -->|ALREADY_USED| R["Replay rejection"]
    G -->|UNKNOWN| U["Fail closed"]
    H --> I["Authorization tenant/action/resource"]
    I -->|Deny| K["403/404 theo policy"]
    I -->|Allow| J["Business handler"]
~~~

Có thể kiểm tra **timestamp grammar và window trước MAC** để loại malformed input; đây là thao tác read-only. Nhưng **không ghi nonce trước MAC đúng**. Replay namespace được tạo từ credential/principal đã tra cứu server-side, không phải chuỗi tenant tùy ý do client cung cấp.

### Test nonce poisoning

~~~text
Store sạch, key K4 ACTIVE, nonce N chưa từng dùng:
1. Gửi request có N, timestamp hợp lệ nhưng signature sai.
   -> 401, nonce store chưa có N, claim call count = 0.
2. Gửi request đúng MAC với cùng N và canonical contract.
   -> FIRST_USE, authentication pass.
3. Gửi lại request thứ hai y nguyên.
   -> ALREADY_USED, authentication rejected.
~~~

Một test chỉ assert 401 ở bước 1 **không phát hiện lỗi claim nonce sớm**.

### Nonce khi authorization bị từ chối

Trong pipeline ví dụ, nonce được claim **trước** authorization. Request có HMAC đúng nhưng thiếu quyền tenant có thể nhận 403 và nonce vẫn USED. Đây là quyết định có thể chấp nhận: bằng chứng authentication đã được dùng. Không tự xóa nonce khi controller 500/DB rollback, vì side effect có thể đã xảy ra trước lỗi.

## 14. Anti-pattern: fail-open khi replay store không khả dụng

Một thay đổi nhằm “bảo đảm availability” đôi khi phá hỏng xác thực:

~~~java
// SAI NGHIÊM TRỌNG: Redis lỗi thì cho qua.
try {
    return replayStore.claim(credentialId, nonce)
        ? authenticated() : replayRejected();
} catch (RedisConnectionFailureException ex) {
    return authenticated(); // fail-open
}
~~~

Phân biệt chính xác:

| Claim result | Ý nghĩa | Hành động |
| --- | --- | --- |
| `FIRST_USE` | Lệnh claim thành công | Có thể đi tiếp authorization |
| `ALREADY_USED` | Nonce đã tồn tại | Từ chối authentication |
| `UNKNOWN` | Không chắc claim đã commit hay chưa | **Fail closed**, thường 503 |
| Store unavailable | Không chứng minh được first-use | **Fail closed** |
| Key bị evict trước TTL | Mất state chống replay | Sự cố nghiêm trọng cần xử lý |

Nếu Redis đã ghi nonce rồi response mạng bị mất, lần retry `SET NX` có thể trả `ALREADY_USED` vì chính attempt cũ đã ghi. Không suy diễn từ đó rằng caller hiện “được phép” hoặc “attacker replay”. Với request nhạy cảm, xử lý claim UNKNOWN bằng cách **không thực thi nghiệp vụ** và cho client retry với **nonce mới**, phối hợp business idempotency.

### Không fallback sang cache local

~~~text
Redis unavailable -> fallback in-memory HashSet
Node A: N được claim thành công
Node B: N cũng được claim thành công
-> replay bypass trên cùng credential
~~~

Nếu security requirement là replay protection toàn hệ thống, việc âm thầm chuyển local store trong outage là **hạ cấp bảo mật**. Cần HA topology có cam kết consistency hoặc chặn request/fail closed.

### Failure injection cần có

- Redis lỗi trước khi nhận claim: không business.
- Redis thực thi SET NX rồi mất ACK: UNKNOWN, không business.
- Redis failover mất write vừa ACK: kiểm chứng guarantee đang cam kết.
- Eviction/TTL bất thường: không nhận lại chữ ký vẫn còn hạn.
- Multi-region network split: không double first-use nếu advertised global protection.

Mock luôn trả `true` không thể chứng minh các tình huống trên.

## 15. Anti-pattern xuyên key rotation và signing suite

Một hệ thống có nhiều keys/versions có thể mắc thêm lỗi:

- Request khai `K4` nhưng verifier thử secret K3 khi K4 mismatch.
- K3 đã `REVOKED` vẫn được chấp nhận nhờ fallback.
- Client sửa `X-Signing-Suite` hoặc key ID không nằm trong MAC để né replay namespace.
- Nonce scope bị tách theo suite V1/V2 không có threat model cross-version replay.
- Gateway/back-end claim nonce hai lần trên cùng namespace hoặc không dùng cùng store.
- Key ID K4 bị **tái sử dụng** cho secret khác, khiến audit/nonce/key state mập mờ.

| Key ID khai trong request | Secret xác minh | Outcome |
| --- | --- | --- |
| K4, MAC đúng secret K4 | **Chỉ K4** | Pass nếu ACTIVE và nonce mới |
| K4, MAC ký bởi K3 | **Chỉ K4** | Reject |
| K3 ACTIVE trong overlap | **Chỉ K3** | Có thể pass, theo policy |
| K3 REVOKED, MAC đúng K3 | Không được cấp principal | Reject |
| K4 nhưng suite disabled | Không fallback sang suite khác | Reject |

Với replay scope `(credentialId, nonce)`, các key versions có namespace riêng. Nếu sản phẩm cần **chống reuse xuyên keys của cùng client**, nên dùng scope `(trustedClientId, nonce)` hoặc phương án tương đương có kiểm chứng và migration retention phù hợp. Không thêm client-supplied tenant/suite tùy ý vào namespace để làm phép claim “dễ pass”.

**Một request phải chọn đúng một signing suite theo allowlist**, được MAC ràng buộc; không “thử tất cả algorithms/keys đến khi khớp”.

## 16. Tách rõ các trách nhiệm trong verifier an toàn

~~~text
HTTP adapter:
  reject malformed/duplicate signed headers
  enforce header/body-size limits
  capture exact method, URI/query, signed headers, raw body

Credential resolver:
  exact key ID, ACTIVE/REVOKED/expiry, client binding

Pure crypto verifier:
  canonical bytes theo contract đã version hóa
  HMAC đúng secret/key ID, constant-time MAC comparison

Freshness validator:
  strict timestamp grammar, Clock acceptance window
  signed nonce grammar/uniqueness requirements

Replay gate:
  atomic claim (trusted scope, signed nonce) với TTL đủ
  FIRST_USE / ALREADY_USED / UNKNOWN

Authentication:
  ONLY FIRST_USE mới tạo principal tin cậy

Authorization:
  tenant/action/resource/grants riêng

Business handler:
  side effects chỉ sau cả authn + authz
~~~

**Không tin canonical bytes do client tự gửi**; server dựng lại từ HTTP request thực ở trust boundary đã thống nhất. Việc gateway rewrite external→internal URI hoặc body compression phải được giải quyết trong signing contract, không tự sửa nhiều kiểu canonical hóa đến khi chữ ký khớp.

**Bất biến triển khai:** với một replay scope và nonce, trong khoảng một chữ ký còn được phép dùng, có tối đa một authoritative first-use; request MAC sai không được ghi nonce; nếu kết quả claim chưa chắc chắn, không được tạo authenticated principal.

## 17. Java 17: core verifier kiểm tra MAC, timestamp và nonce

Ví dụ sau cô lập phần security core để giải thích cách **sửa anti-pattern**, không phải một HTTP verifier production hoàn chỉnh. `SignedEvidence` chỉ được tạo bởi adapter **phía server** từ signed HTTP fields đã parse/validate; không nhận canonical bytes do client tự khai.

~~~java
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.Objects;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

record SignedEvidence(
    String credentialId,
    Instant signedAt,
    String nonce,
    byte[] canonicalBytes,
    byte[] signatureBytes
) {
    SignedEvidence {
        Objects.requireNonNull(credentialId);
        Objects.requireNonNull(signedAt);
        Objects.requireNonNull(nonce);
        canonicalBytes = canonicalBytes.clone();
        signatureBytes = signatureBytes.clone();
    }

    @Override
    public byte[] canonicalBytes() {
        return canonicalBytes.clone();
    }

    @Override
    public byte[] signatureBytes() {
        return signatureBytes.clone();
    }
}

enum ReplayClaim {
    FIRST_USE, ALREADY_USED, UNKNOWN
}

interface AtomicNonceStore {
    ReplayClaim claim(
        String trustedCredentialId,
        String validatedNonce,
        Duration ttl);
}

enum ReplayAuthResult {
    ACCEPTED, INVALID_SIGNATURE, INVALID_TIMESTAMP,
    REPLAY, AUTHENTICATION_UNAVAILABLE
}

final class HmacReplayGuard {
    private final byte[] secret;
    private final AtomicNonceStore store;
    private final Clock clock;
    private final Duration allowedSkew;
    private final Duration nonceTtl;

    HmacReplayGuard(
            byte[] secret,
            AtomicNonceStore store,
            Clock clock,
            Duration allowedSkew,
            Duration nonceTtl) {
        this.secret = secret.clone();
        this.store = Objects.requireNonNull(store);
        this.clock = Objects.requireNonNull(clock);
        this.allowedSkew = allowedSkew;
        this.nonceTtl = nonceTtl;
    }

    ReplayAuthResult verify(SignedEvidence input) {
        Instant now = clock.instant();

        // Window đối xứng inclusive minh họa.
        if (input.signedAt().isBefore(now.minus(allowedSkew))
                || input.signedAt().isAfter(
                    now.plus(allowedSkew))) {
            return ReplayAuthResult.INVALID_TIMESTAMP;
        }

        byte[] expected = sign(secret, input.canonicalBytes());
        byte[] supplied = input.signatureBytes();

        // Nonce KHÔNG được claim khi MAC sai.
        if (supplied.length != expected.length
                || !MessageDigest.isEqual(expected, supplied)) {
            return ReplayAuthResult.INVALID_SIGNATURE;
        }

        ReplayClaim result;
        try {
            result = store.claim(
                input.credentialId(), input.nonce(), nonceTtl);
        } catch (RuntimeException ex) {
            return ReplayAuthResult.AUTHENTICATION_UNAVAILABLE;
        }

        if (result == ReplayClaim.FIRST_USE) {
            return ReplayAuthResult.ACCEPTED;
        }
        if (result == ReplayClaim.ALREADY_USED) {
            return ReplayAuthResult.REPLAY;
        }
        return ReplayAuthResult.AUTHENTICATION_UNAVAILABLE;
    }

    static byte[] sign(byte[] key, byte[] data) {
        try {
            Mac mac = Mac.getInstance("HmacSHA256");
            mac.init(new SecretKeySpec(key, "HmacSHA256"));
            return mac.doFinal(data);
        } catch (GeneralSecurityException ex) {
            throw new IllegalStateException(
                "hmac_runtime_unavailable", ex);
        }
    }
}
~~~

### Phạm vi và điều kiện tiên quyết

- **Đây là core skeleton:** chưa có credential registry, key revocation, tenant grants, body capture, strict nonce grammar hay parsing duplicate headers. `secret` phải đến từ **exact key ID** và trạng thái ACTIVE kiểm tra đủ mới.
- `SignedEvidence.canonicalBytes` và `credentialId` chỉ đến từ adapter/trusted registry, không phải request body của client. Nếu client tự cung cấp canonical bytes, thiết kế không an toàn.
- `allowedSkew`/`nonceTtl` do server config đáng tin quyết định; cần validation/retention proof.
- `Mac` là mutable; tạo instance mới mỗi verify hoặc quản lý thread-safe.
- Nếu provider crypto lỗi, fail closed và map lỗi vận hành riêng, không mặc định cho qua.
- `ReplayAuthResult.ACCEPTED` chưa phải permission; cần tạo principal từ registry và authorization độc lập.

## 18. Spring Data Redis: adapter nguyên tử cho Servlet và Reactive

Một adapter blocking phía Spring MVC/Servlet có thể dùng `StringRedisTemplate`:

~~~java
import java.time.Duration;
import org.springframework.data.redis.core.StringRedisTemplate;

final class RedisNonceStore implements AtomicNonceStore {
    private final StringRedisTemplate redis;

    RedisNonceStore(StringRedisTemplate redis) {
        this.redis = redis;
    }

    @Override
    public ReplayClaim claim(
            String credentialId,
            String nonce,
            Duration ttl) {
        // Encode digest trên tuple length-prefixed để
        // tránh key collision/dynamic raw identifiers.
        String key = "hmac:nonce:v1:" +
            ReplayKeyCodec.digest(credentialId, nonce);

        Boolean ok = redis.opsForValue()
            .setIfAbsent(key, "1", ttl);
        if (ok == null) return ReplayClaim.UNKNOWN;

        return ok ? ReplayClaim.FIRST_USE
                  : ReplayClaim.ALREADY_USED;
    }
}
~~~

`ReplayKeyCodec` là helper **dự án phải triển khai**, không phải class có sẵn của Spring. Trước khi gọi Redis, phải giới hạn/validate nonce, TTL dương, scope và encoding. Exception từ Redis được HMAC guard bắt thành `AUTHENTICATION_UNAVAILABLE`; không fallback `FIRST_USE`.

Trong WebFlux, không gọi Redis blocking trên event loop:

~~~java
import java.time.Duration;
import org.springframework.data.redis.core.ReactiveStringRedisTemplate;
import reactor.core.publisher.Mono;

final class ReactiveRedisNonceStore {
    private final ReactiveStringRedisTemplate redis;

    ReactiveRedisNonceStore(
            ReactiveStringRedisTemplate redis) {
        this.redis = redis;
    }

    Mono<ReplayClaim> claim(String key, Duration ttl) {
        return redis.opsForValue()
            .setIfAbsent(key, "1", ttl)
            .map(ok -> ok ? ReplayClaim.FIRST_USE
                          : ReplayClaim.ALREADY_USED)
            .switchIfEmpty(Mono.just(ReplayClaim.UNKNOWN))
            .onErrorReturn(ReplayClaim.UNKNOWN);
    }
}
~~~

**Bắt buộc:** caller của reactive adapter phải map `UNKNOWN` thành **fail closed**, không sử dụng `onErrorReturn(FIRST_USE)`. Các mẫu trên chỉ minh họa API conditional-set; consistency và failover semantics của deployment Redis phải được kiểm thử độc lập.

## 19. JUnit 5: test exact replay và nonce poisoning

Bộ test tập trung vào logic `HmacReplayGuard` và fake store nguyên tử trong một JVM:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.nio.charset.StandardCharsets;
import java.time.*;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;

class HmacReplayGuardTest {
    private static final byte[] SECRET =
        "test-only-hmac-secret"
            .getBytes(StandardCharsets.UTF_8);
    private static final Instant NOW =
        Instant.parse("2026-11-28T04:00:00Z");

    static final class FakeStore implements AtomicNonceStore {
        final Set<String> seen = ConcurrentHashMap.newKeySet();
        final AtomicInteger calls = new AtomicInteger();

        @Override
        public ReplayClaim claim(
                String id, String nonce, Duration ttl) {
            calls.incrementAndGet();
            return seen.add(id + ":" + nonce)
                ? ReplayClaim.FIRST_USE
                : ReplayClaim.ALREADY_USED;
        }
    }

    private HmacReplayGuard guard(AtomicNonceStore store) {
        return new HmacReplayGuard(
            SECRET, store, Clock.fixed(NOW, ZoneOffset.UTC),
            Duration.ofMinutes(5), Duration.ofMinutes(11));
    }

    private SignedEvidence evidence(String nonce) {
        // Unit fixture: kiểm tra core MAC/claim.
        // Test HTTP riêng phải dựng canonical raw request.
        byte[] canonical = (
            "POST\n/api/orders\n2026-11-28T04:00:00Z\n" + nonce)
            .getBytes(StandardCharsets.UTF_8);
        return new SignedEvidence(
            "cred-k4", NOW, nonce, canonical,
            HmacReplayGuard.sign(SECRET, canonical));
    }

    @Test
    void firstUseAcceptedButExactReplayRejected() {
        FakeStore store = new FakeStore();
        var signed = evidence("nonce-test-001");

        assertEquals(ReplayAuthResult.ACCEPTED,
            guard(store).verify(signed));
        assertEquals(ReplayAuthResult.REPLAY,
            guard(store).verify(signed));
        assertEquals(2, store.calls.get());
    }

    @Test
    void wrongMacCannotConsumeNonce() {
        FakeStore store = new FakeStore();
        var signed = evidence("nonce-test-002");

        byte[] corrupted = signed.signatureBytes();
        corrupted[0] ^= 1;
        var invalid = new SignedEvidence(
            signed.credentialId(), signed.signedAt(),
            signed.nonce(), signed.canonicalBytes(), corrupted);

        assertEquals(ReplayAuthResult.INVALID_SIGNATURE,
            guard(store).verify(invalid));
        assertEquals(0, store.calls.get());
        assertEquals(ReplayAuthResult.ACCEPTED,
            guard(store).verify(signed));
        assertEquals(1, store.calls.get());
    }

    @Test
    void unknownStoreOutcomeFailsClosed() {
        AtomicNonceStore unavailable =
            (id, nonce, ttl) -> ReplayClaim.UNKNOWN;
        assertEquals(ReplayAuthResult.AUTHENTICATION_UNAVAILABLE,
            guard(unavailable).verify(evidence("nonce-test-003")));
    }

    @Test
    void expiredTimestampIsNotNonceTest() {
        Clock afterWindow = Clock.fixed(
            NOW.plus(Duration.ofMinutes(6)),
            ZoneOffset.UTC);
        FakeStore store = new FakeStore();
        HmacReplayGuard subject = new HmacReplayGuard(
            SECRET, store, afterWindow,
            Duration.ofMinutes(5), Duration.ofMinutes(11));

        assertEquals(ReplayAuthResult.INVALID_TIMESTAMP,
            subject.verify(evidence("nonce-test-004")));
        assertEquals(0, store.calls.get());
    }
}
~~~

**Giới hạn:** fake store không có TTL, replication, failover hay multi-node; test chỉ xác minh logic local và thứ tự MAC-before-claim. Cần golden vectors/canonical contract độc lập và HTTP integration tests để kiểm tra thực sự đang ký raw body/URI/timestamp/nonce.

### Mutation testing

Nếu cố ý đổi verifier thành:

~~~java
// Mutation lỗi: bỏ replay guard.
if (validSignature) return ReplayAuthResult.ACCEPTED;
~~~

test `firstUseAcceptedButExactReplayRejected` **phải FAIL** ở lần thứ hai. Nếu thay đổi thứ tự claim trước MAC, test `wrongMacCannotConsumeNonce` **phải FAIL**. Đây là cách xác nhận tests thực sự phát hiện anti-pattern, không chỉ nhìn 401.

## 20. Concurrency: 100 bản sao cùng chữ ký

Một attacker không cần chờ R1 trả về; có thể gửi 100 bản sao đồng thời. Test unit sau chứng minh local atomic fake, **không thay thế distributed test**:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.nio.charset.StandardCharsets;
import java.time.*;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.stream.IntStream;
import org.junit.jupiter.api.Test;

class HmacReplayConcurrencyTest {
    @Test
    void oneOfHundredParallelCopiesIsAccepted() {
        Set<String> used = ConcurrentHashMap.newKeySet();
        AtomicNonceStore store = (id, nonce, ttl) ->
            used.add(id + ":" + nonce)
                ? ReplayClaim.FIRST_USE
                : ReplayClaim.ALREADY_USED;

        byte[] secret = "test-only-parallel-key"
            .getBytes(StandardCharsets.UTF_8);
        Instant now = Instant.parse("2026-11-28T04:00:00Z");
        byte[] canonical = "unit-canonical"
            .getBytes(StandardCharsets.UTF_8);

        SignedEvidence proof = new SignedEvidence(
            "cred-k4", now, "nonce-parallel-001",
            canonical, HmacReplayGuard.sign(secret, canonical));
        HmacReplayGuard verifier = new HmacReplayGuard(
            secret, store,
            Clock.fixed(now, ZoneOffset.UTC),
            Duration.ofMinutes(5),
            Duration.ofMinutes(11));

        AtomicInteger pass = new AtomicInteger();
        IntStream.range(0, 100).parallel().forEach(i -> {
            if (verifier.verify(proof) == ReplayAuthResult.ACCEPTED) {
                pass.incrementAndGet();
            }
        });
        assertEquals(1, pass.get());
    }
}
~~~

E2E phải gửi 100 HTTP requests thực qua nhiều pods/gateways/regions, bảo đảm đúng một **authoritative FIRST_USE** trong phạm vi cam kết, các bản còn lại không tạo principal/side effect và mọi Redis UNKNOWN đều fail closed. Đừng coi “một payment row duy nhất” là đủ: business idempotency có thể che lỗi authentication replay.

## 21. Spring Security Servlet: test qua HMAC filter thật

Đối với Spring Boot/Spring Security 6 trên Servlet, lỗi thiếu chống replay thường nằm trong `OncePerRequestFilter` hoặc `AuthenticationProvider`. Một bài test chỉ gọi `Mac.doFinal` không đi qua filter/entry point/nonce store, nên không thấy lỗi ở luồng thực tế.

~~~mermaid
sequenceDiagram
    participant C as MockMvc Client
    participant F as HmacAuthenticationFilter
    participant P as AuthenticationProvider
    participant N as Shared Replay Store
    participant B as PaymentService
    C->>F: R1 hợp lệ: K4, T1, N1, MAC1
    F->>P: parse + canonical + verify MAC
    P->>N: atomic claim (K4,N1)
    N-->>P: FIRST_USE
    P-->>F: authenticated principal
    F->>B: authorize + create payment
    B-->>C: 2xx hoặc business result
    C->>F: R2 = exact copy of R1
    F->>P: MAC vẫn hợp lệ
    P->>N: atomic claim (K4,N1)
    N-->>P: ALREADY_USED
    P-->>F: authentication failure
    F-->>C: 401 generic response
    Note over B: Không có business call lần hai
~~~

### Test khung bằng MockMvc

~~~java
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;
import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet
    .AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class MissingReplayProtectionMvcIT {
    @Autowired MockMvc mvc;
    @Autowired HmacTestSigner signer;
    @Autowired ReplayTestFixture fixture;

    @Test
    void sameSignedHttpRequestNeverExecutesBusinessTwice()
            throws Exception {
        fixture.clearReplayState();
        fixture.useFixedClock("2026-11-28T04:00:00Z");
        fixture.activateCredential("partner-a-prod-k004");

        byte[] body =
            "{\"paymentId\":\"p-101\",\"amount\":250000}"
            .getBytes(java.nio.charset.StandardCharsets.UTF_8);
        String nonce =
            "77ae7eba-9be7-4b38-b5a7-a53a9f98a492";
        String signature = signer.sign(
            "POST", "/api/hmac/payments", body,
            "partner-a-prod-k004",
            "2026-11-28T04:00:00Z", nonce);

        // Hai request giống signed fields/bytes;
        // không ký lại lần hai.
        var r1 = fixture.signedPost(
            "/api/hmac/payments", body, nonce, signature);
        var r2 = fixture.signedPost(
            "/api/hmac/payments", body, nonce, signature);

        mvc.perform(r1).andExpect(status().is2xxSuccessful());
        long commitsAfterFirst =
            fixture.businessCommitCount("p-101");

        mvc.perform(r2).andExpect(status().isUnauthorized());
        assertEquals(commitsAfterFirst,
            fixture.businessCommitCount("p-101"));
    }
}
~~~

Đây là **integration test skeleton**: `HmacTestSigner` và `ReplayTestFixture` là lớp phải được dự án xây dựng. Chúng không có sẵn trong Spring. `Clock.fixed` và nonce store reset/fixture cách ly là điều kiện tiên quyết; nếu timestamp 2026 bị quá hạn do đồng hồ chạy thực, R1 cũng có thể bị 401 và **test không chứng minh replay**.

### Test cần bổ sung ở Servlet

- R1 pass cùng ký tự/bytes đã ký, R2 401, controller không được gọi lần hai.
- Nonce N chưa claim nếu MAC sai; sau đó MAC đúng cùng N vẫn first-use.
- Body capture không làm `@RequestBody` rỗng: đọc body một lần có bounded caching/replay.
- Duplicate signed headers, malformed Base64, raw URI encoding bị từ chối đúng contract.
- Filter không đăng ký **hai lần** vừa trong Servlet container vừa trong `SecurityFilterChain`.
- `REQUEST`/`ASYNC`/`ERROR` dispatch không gây claim nonce kép trong cùng request logic.
- `AuthenticationException` ở filter được map qua `AuthenticationEntryPoint`, không dựa thuần `@RestControllerAdvice`.
- Một key K4 REVOKED không được tạo principal dù signature toán học đúng.

Nếu có quota/rate limiter trả 429 trước HMAC, không coi 429 đó là “replay guard đã chặn”. Cần quan sát internal claim result và business spy.

## 22. Spring WebFlux: replay guard trong reactive security chain

WebFlux dùng `SecurityWebFilterChain`, `ReactiveAuthenticationManager` và `ReactiveSecurityContextHolder`. Request body là `Flux<DataBuffer>`, có thể one-shot và dùng pooled/direct memory. Nếu tính HMAC từ raw body, phải capture có giới hạn và replay cho downstream **chỉ sau khi auth pass**.

Một flow mô tả:

~~~text
WebFilter
  -> validate headers/size
  -> bounded DataBuffer capture + raw-body digest
  -> canonical request bytes
  -> exact credential/key HMAC check
  -> timestamp window
  -> reactive atomic nonce claim (Redis)
       FIRST_USE -> Reactor authenticated context
       ALREADY_USED -> AuthenticationException
       UNKNOWN -> AuthenticationServiceException / 503
  -> authorization -> handler
~~~

Không làm:

~~~java
// SAI: lỗi replay store biến thành first-use.
return replayStore.claim(key, ttl)
    .onErrorReturn(ReplayClaim.FIRST_USE);

// SAI: tạo một subscribe riêng để ghi nonce,
// authentication có thể tiếp tục trước khi claim xong.
replayStore.claim(key, ttl).subscribe();
return Mono.just(authenticatedPrincipal);
~~~

Trong Reactor, hãy **compose** claim vào chain bằng `flatMap` để security decision chỉ hoàn tất khi result được biết. Không dùng `block()` trên Netty event loop. Pooled `DataBuffer` cần release khi success/error/cancel; hạn mức bytes/concurrency phải được đặt rõ để tránh DoS ngay trước nonce guard.

### WebTestClient integration skeleton

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
class MissingReplayProtectionWebFluxIT {
    @Autowired WebTestClient client;
    @Autowired HmacTestSigner signer;
    @Autowired ReplayTestFixture fixture;

    @Test
    void sameNonceAndSignatureIsRejectedOnSecondCall() {
        fixture.clearReplayState();
        fixture.useFixedClock("2026-11-28T04:00:00Z");

        String body = "{\"paymentId\":\"p-201\"}";
        String timestamp = "2026-11-28T04:00:00Z";
        String nonce =
            "34dc41b1-2911-4bc5-900a-37af5ef75598";
        String signature = signer.sign(
            "POST", "/api/hmac/payments",
            body.getBytes(java.nio.charset.StandardCharsets.UTF_8),
            "partner-a-prod-k004", timestamp, nonce);

        send(body, timestamp, nonce, signature)
            .expectStatus().is2xxSuccessful();
        send(body, timestamp, nonce, signature)
            .expectStatus().isUnauthorized();
        fixture.assertOneBusinessCommit("p-201");
    }

    private WebTestClient.ResponseSpec send(
            String body, String timestamp, String nonce,
            String signature) {
        return client.post()
            .uri("/api/hmac/payments")
            .header("Content-Type", "application/json")
            .header("X-Client-Id", "partner-a")
            .header("X-Key-Id", "partner-a-prod-k004")
            .header("X-Timestamp", timestamp)
            .header("X-Nonce", nonce)
            .header("X-Signature", signature)
            .bodyValue(body)
            .exchange();
    }
}
~~~

Test khung trên cần signer/fixture đúng dự án và clock injection; không biên dịch độc lập nếu thiếu chúng. Không chỉ assert HTTP 401: xác minh **không có principal/context cho replay**, không có side effect lần hai, Redis claim result `ALREADY_USED` và không rò pooled buffers.

### WebFlux cancel/error

Nếu client disconnect khi đang gửi body, verifier không được claim nonce trước khi nhận và xác minh đầy đủ **signed bytes**. Nếu body đã được xác minh và nonce claim thành công nhưng response bị hủy sau đó, record nonce vẫn phải giữ; client retry bằng nonce mới và idempotency phù hợp. Không rollback nonce để cứu một response bị cancel.

## 23. Gateway/proxy: chỗ anti-pattern được nhân lên

### Kiến trúc A — Gateway xác minh HMAC

Gateway nhận external request, verify HMAC và claim nonce. Backend chỉ tin principal thông qua **mTLS/trusted workload identity hoặc signed assertion nội bộ** có issuer/audience/expiry/method/target/body binding. Nếu backend cũng claim **chính nonce client** trong cùng namespace, R1 sẽ bị báo replay giả.

~~~text
Internet Client -> Gateway HMAC + nonce FIRST_USE
                -> signed internal assertion / mTLS
                -> Backend checks assertion + authorization
                -> business
~~~

Test cần chứng minh:

- Exact replay R2 qua Gateway B bị reject dù R1 qua Gateway A.
- Gateway không mint internal assertion khi MAC hoặc nonce fail.
- Headers `X-Authenticated-Client`/`X-Original-URI` do Internet client tự khai bị strip/reject.
- Direct backend route không qua trusted gateway bị chặn.
- Internal assertion có thể cần `jti`/nonce chống replay **riêng**, không dùng lại namespace nonce client.

### Kiến trúc B — Backend xác minh HMAC

Gateway forward request, backend dùng exact credential secret và shared nonce store. Cần biết canonical bytes được ký là raw **external URI** hay internal URI sau rewrite.

| Proxy behavior | Ảnh hưởng |
| --- | --- |
| `/public/v1/payments` → `/internal/payments` | URI signature mismatch nếu contract không thống nhất |
| Query reorder/duplicate query | Thay canonical target nếu ký raw query |
| Percent-encoding normalize | `%2F`/`%2f`, `+`/`%20` có thể khác bytes |
| HTTP/2 → HTTP/1.1 | Header names/pseudo-header/raw target handling khác |
| gzip decompress | Body digest có thể khác |
| JSON transform | Raw body bytes bị đổi |
| Duplicate signed headers | Có thể chọn first/last khác giữa proxy và app |
| Backend ingress bypass | Có thể không chạy HMAC/replay middleware |

**False-positive nguy hiểm:** R1 đúng secret qua gateway bị 401 vì path rewrite, R2 cũng 401. Nếu chỉ nhìn R2, nhóm tưởng replay đã được chặn. Phải có **positive R1 qua cùng tuyến** trước khi kết luận anti-replay hoạt động.

### Multi-region guarantee

Nếu mỗi region có replay store riêng và một credential có thể truy cập cả hai, cùng signed request có thể được nhận hai lần. Phải định nghĩa rõ global consistency hoặc credential region-binding. DNS/load balancer failover cũng là một dạng thay đổi region cần test.

## 24. Retry, idempotency và giới hạn của replay protection

Một client có thể gửi R1 hợp lệ, server đã xử lý nhưng HTTP response bị mất. Nếu client gửi lại **nguyên R1** cùng nonce/signature, replay guard phải reject. Đây là hành vi an ninh đúng, nhưng client vẫn cần cách retry business hợp lý.

~~~text
Business intent: CREATE_PAYMENT(paymentId=p-101)
Idempotency-Key: intent-p-101

Attempt 1:
  timestamp=T1, nonce=N1, signature=MAC(K,canonical1)
  server có thể đã commit, client timeout

Attempt 2 đúng protocol:
  timestamp=T2, nonce=N2 (mới), signature=MAC(K,canonical2)
  Idempotency-Key vẫn là intent-p-101
  service trả cùng business result hoặc xử lý conflict theo policy

Attack replay:
  timestamp=T1, nonce=N1, signature và body nguyên vẹn
  authentication rejected vì nonce USED
~~~

### Phải tách hai store

| Store | Khóa logic | Mục đích |
| --- | --- | --- |
| Replay store | Trusted credential/client scope + signed nonce | One-time authentication evidence |
| Idempotency store | Principal + tenant + action + idempotency key + request binding | Một business intent không nhân đôi |
| Business transaction/outbox | Transaction ID / event ID | Nhất quán DB và side effects |

`Idempotency-Key` nên được HMAC ký hoặc bind với principal, tenant, action và body digest theo hợp đồng. Cùng idempotency key mà payload khác phải bị từ chối (ví dụ 409) theo contract, không tái sử dụng kết quả của payload cũ.

**Không xóa nonce khi controller 500, authorization 403 hoặc client timeout**. Side effect có thể đã xảy ra trước khi thấy lỗi; xóa nonce mở lại cửa phát lại request cũ. Sau khi authentication accepted, client retry cần **nonce mới** và business idempotency.

### GET cũng cần threat model

Một GET được thiết kế an toàn không có side effect có thể ít rủi ro nhân đôi giao dịch hơn POST, nhưng **signed GET request vẫn có thể bị phát lại để truy xuất dữ liệu** trong thời hạn signature còn hợp lệ. Đừng chỉ bật anti-replay cho POST nếu chính sách yêu cầu one-time evidence trên các routes đọc dữ liệu nhạy cảm. Nếu chọn mô hình **reusable signed URLs** có expiry thay vì one-time HMAC, đó là **giao thức khác** với threat model, audience, scope và TTL được công bố rõ; không gọi nó là đã chống replay một lần.

## 25. Authentication khác authorization, ngay cả khi chặn được replay

Một credential K4 có thể xác thực principal `partner-a` thuộc `tenant-a`. HMAC đúng, nonce mới chỉ chứng minh bằng chứng xác thực mới và hợp lệ; không chứng minh quyền tới mọi tenant/resource.

~~~mermaid
flowchart TD
    A["Request K4 và requested tenant-b"] --> B["Exact registry lookup K4"]
    B --> C["HMAC + timestamp + nonce first-use?"]
    C -->|Không| X["401/503 authentication"]
    C -->|Có| D["Trusted principal partner-a"]
    D --> E{"Partner-a có grant tenant-b?"}
    E -->|Không| Y["403/404 authorization"]
    E -->|Có| F["Business handler"]
~~~

**Anti-pattern liên quan:** sau khi thêm nonce store, developer coi mọi authenticated request đều có quyền trên requested tenant `X-Tenant-Id`. Header tenant được ký chỉ bảo vệ **tính toàn vẹn claim**, không tạo grant. Effective tenant phải được quyết định từ principal/credential registry, delegation và resource ownership.

Bộ test phải tách:

- R1 valid MAC/nonce mới, tenant-a có grant → business allowed.
- R2 exact replay tenant-a → authentication rejected.
- R3 MAC/nonce mới, tenant-b không có grant → authorization rejected, no tenant-b data.
- R4 thay tenant-a→tenant-b nhưng giữ MAC → signature mismatch nếu tenant thuộc signed fields.
- R5 key revoked có signature đúng → authentication rejected.

Nếu authorization check thực hiện sau nonce claim, R3 có thể tiêu thụ nonce mặc dù trả 403. Cần mô tả rõ trong client contract để retry đúng cách.

## 26. Error semantics, logs và privacy khi chặn replay

Một API có thể công khai lỗi authentication chung:

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
  "requestId": "req-a912"
}
~~~

Đây là response **minh họa**. `WWW-Authenticate: HMAC realm="api"` chỉ dùng nếu ứng dụng đã **định nghĩa challenge scheme HMAC riêng**; Spring Security không tự cung cấp một challenge HMAC chuẩn cho mọi API.

| Lỗi | Bản chất | Public status gợi ý |
| --- | --- | --- |
| HMAC sai/unknown key | Authentication failed | 401 chung |
| Timestamp ngoài acceptance window | Authentication failed | 401 chung |
| Nonce đã used | Replay rejection | 401 chung |
| Nonce store timeout/unknown | Không đủ bằng chứng xác thực | 503, fail closed |
| Body vượt limit | Request quá lớn để xác minh | 413 |
| Header invalid/duplicate | Malformed security input | 400 hoặc 401 theo API contract |
| MAC và nonce hợp lệ, thiếu quyền tenant | Authorization denied | 403/404 theo policy |
| Cùng idempotency key nhưng body khác | Business conflict | 409 theo contract |

**Không phân biệt quá chi tiết trên public error** khiến attacker dò credential existence, nonce state hoặc secret version. Internal reason `REPLAY_DETECTED` hữu ích cho kiểm thử/monitoring, nhưng không nhất thiết được phơi cho client chưa xác thực.

### Không ghi ra logs

- Raw secret, key material hoặc vault responses.
- Full HMAC signature, raw request body và full canonical request chứa sensitive data.
- Timestamp+nonce+signature+body dưới dạng có thể dựng lại một signed request.
- Key IDs, client IDs, tenant IDs vào **metric labels** có cardinality cao.
- Full query/token trong HTTP tracing.

Trong audit có ACL phù hợp, có thể ghi correlation ID, route group, contract version, credential revision đã pseudonymize và internal reason enum. Không quảng bá “request replayed” một cách chắc chắn nếu chỉ biết timestamp hết hạn; đó là **freshness reject**, không chứng minh request đã dùng trước đó.

## 27. Monitoring: phát hiện replay và lỗi triển khai

Các metric logic (tên minh họa) nên dùng labels hữu hạn:

~~~text
hmac_authentication_attempts_total{
  route="payments", result="invalid", reason="replay"
}

hmac_nonce_claims_total{
  operation="claim", outcome="already_used"
}

hmac_authentication_attempts_total{
  route="payments", result="unavailable", reason="nonce_store"
}
~~~

Không dùng raw nonce, key ID, client ID, tenant ID, full path, full signature hoặc request ID làm Prometheus labels. Route nên là **route template/allowlist**, không raw URI.

### Điều cần quan sát

| Tín hiệu | Giả thuyết | Kiểm tra thêm |
| --- | --- | --- |
| Replay rejection tăng sau SDK release | Client retry cùng nonce | Xem retry policy, SDK signing |
| Replay tăng sau cấu hình filter | Double filter registration | Quan sát một request bị claim 2 lần |
| Replay chỉ xuất hiện ở Gateway B | Namespace/clock khác nhau | Cross-gateway contract test |
| 401 tăng sau proxy rewrite | Canonical mismatch | Positive signed vector qua cùng tuyến |
| Chấp nhận request K3 sau revoke | Cache policy stale | Revocation propagation test |
| Nonce store UNKNOWN tăng | Redis issue | Fail-closed outcomes, latency/failover |
| Side effects trùng dù replay metrics thấp | No replay guard/incorrect scope | DB/outbox events và signed request IDs |
| p99 HMAC tăng mạnh | Body capture/Redis latency | Bounded buffers, stage timers |

**Replay spike không tự động chứng minh attacker tấn công.** Có thể do client retry cùng nonce, clock drift, load balancer hoặc double filter. Điều tra bằng correlation có kiểm soát, không tiết lộ raw signatures trong dashboard.

### Alert có hành động

- Một synthetic exact-replay probe được chấp nhận lần hai.
- Replayed request tạo business side effect thứ hai.
- Nonce store error nhưng route trả 2xx (fail-open indicator).
- Key revoked vẫn được authenticated.
- Replay TTL nhỏ hơn timestamp acceptance policy.
- Multi-node/region simultaneous replay có hơn một FIRST_USE.
- Gateway/backend claims khác namespace khi chính sách yêu cầu global.
- Body-size limit bị bypass trước HMAC verification.

## 28. Phát hiện và sửa anti-pattern trên hệ thống đang chạy

Không nên bật một Redis nonce guard mới cho toàn bộ traffic mà không xét client retry, canonicalization và rollout; nếu không, có thể gây 401 hàng loạt dù mục tiêu bảo mật đúng.

### Kế hoạch khắc phục theo pha

| Pha | Hành động | Bằng chứng đạt |
| --- | --- | --- |
| 0. Inventory | Liệt kê các HMAC-protected routes/gateway/client SDK | Không bỏ sót protected endpoint |
| 1. Threat model | Xác định signed fields, timestamp window, audience, key scope | Hợp đồng ký có version |
| 2. Golden vectors | Kiểm tra canonical method/URI/headers/body/timestamp/nonce | Byte-level signer/verifier parity |
| 3. SDK prep | Sinh nonce mới mỗi HTTP attempt, timestamp UTC, ký đúng fields | Client conformance tests |
| 4. Store deployment | Redis/shared atomic claim, TTL đủ, HA/failover controls | Multi-node test và fault injection |
| 5. Shadow metrics | Ghi nhận nonce reuse/dry-run **không chạm production claim** | Không làm side effect, privacy-safe |
| 6. Canary enforce | Bật replay guard theo route/credential cohort **server-side** | Positive + exact replay + wrong-MAC tests |
| 7. Expand | Mở rộng khi side-effect invariants/latency đạt | No unexplained critical failures |
| 8. Enforce | Bắt buộc nonce cho toàn bộ protected routes theo policy | Synthetic replay always rejected |
| 9. Retire old path | Loại bỏ timestamp-only/fail-open fallback | Không còn bypass route |
| 10. Operate | Rotation/revoke, dashboards, runbooks | Security alerts + regression CI |

**Quan trọng với legacy clients:** nếu HMAC V1 không ký nonce, chỉ thêm Redis store trên header nonce **không giải quyết** vì attacker có thể đổi nonce mà MAC vẫn hợp lệ. Cần **nâng version signing contract**, SDK tạo MAC mới ràng buộc nonce và kế hoạch thay key/suite nếu cần. Cho phép hai contracts trong overlap phải theo **exact version/key/route policy**, không thử mọi verifier/algorithm cho đến khi chấp nhận.

### Emergency mitigation

Khi thấy active replay hoặc side effects lặp:

1. Chặn/giới hạn route và credential bị ảnh hưởng trong phạm vi được phép.
2. Nếu secret có thể đã lộ, **revoke/rotate** theo incident response; chống replay không cứu được leaked-key signing.
3. Kiểm tra chính sách rate limiting, body-size limits và operational fail closed.
4. Đối soát DB/outbox/payment, ngăn duplicate effects và hỗ trợ reconciliation.
5. Giữ evidence an toàn (request IDs, audit), không lan truyền full secrets/signatures.
6. Khôi phục với versioned signed nonce contract + atomic store; chạy E2E trước khi mở lại.

### Không “migrate” bằng hai verifiers OR

Trong thời gian chuyển từ legacy timestamp-only sang nonce-based V2, nếu code dùng `legacyPass || v2Pass` thì request V2 bị reject replay vẫn có thể “được cứu” bằng legacy path. Chọn verifier theo **suite/version được policy cho phép** và được MAC ràng buộc; không fallback tự động khi V2 fail.

## 29. Ma trận kiểm thử anti-pattern Không chống replay

| ID | Tình huống | Kỳ vọng |
| --- | --- | --- |
| AR-01 | Request MAC đúng, nonce N mới | First use accepted |
| AR-02 | Exact copy của AR-01 ngay trong window | Replay rejected |
| AR-03 | Cùng copy qua connection mới | Replay rejected |
| AR-04 | Exact copy qua gateway khác | Replay rejected trong cùng scope |
| AR-05 | Exact copy qua instance khác | Replay rejected |
| AR-06 | 100 requests đồng thời cùng signature | At most one FIRST_USE |
| AR-07 | MAC sai, nonce N mới | Reject, không claim N |
| AR-08 | AR-07 sau đó MAC đúng cùng N | First-use accepted |
| AR-09 | Đổi nonce sau khi ký nhưng giữ MAC | Signature mismatch |
| AR-10 | Đổi timestamp sau khi ký | Signature mismatch |
| AR-11 | Đổi method/URI/query đã ký | Signature mismatch |
| AR-12 | Đổi raw body/header đã ký | Signature mismatch |
| AR-13 | Timestamp hợp lệ nhưng R2 bị replay | Reject **vì nonce**, không vì expiry |
| AR-14 | Timestamp quá cũ | Rejected by freshness, test riêng |
| AR-15 | Timestamp quá xa tương lai | Reject |
| AR-16 | Timestamp ở biên ±W | Policy inclusive/exclusive đúng |
| AR-17 | Nonce thiếu hoặc malformed | Reject trước state write |
| AR-18 | Nonce random nhưng không lưu state | Replay test phải FAIL |
| AR-19 | Header nonce không nằm trong signature | Tampered nonce test phải FAIL |
| AR-20 | Header timestamp không nằm trong signature | Tampered timestamp test phải FAIL |
| AR-21 | Nonce check GET rồi SET | Concurrency phải phát hiện double-accept |
| AR-22 | Local nonce HashSet mỗi node | Cross-node test phải FAIL |
| AR-23 | Redis SET NX + TTL, concurrency | Một claim thành công |
| AR-24 | Redis command timeout before write | Fail closed, no business |
| AR-25 | Redis commit nhưng lost ACK | UNKNOWN, no business |
| AR-26 | Redis failover mất write | Phát hiện vi phạm guarantee |
| AR-27 | Redis eviction trước TTL | Request không được nhận lại |
| AR-28 | TTL nhỏ hơn active signature lifetime | Test TTL phải FAIL |
| AR-29 | Signed timestamp ở biên tương lai | TTL đủ bao phủ |
| AR-30 | Reuse nonce cùng credential nhưng body mới, MAC mới | Reject trong retention scope |
| AR-31 | Nonce reuse xuyên K3/K4 | Theo scope/key rotation contract |
| AR-32 | Nonce reuse xuyên V1/V2 | Không bypass policy bằng suite |
| AR-33 | K4 khai nhưng ký bằng K3 secret | Reject, không fallback |
| AR-34 | K3 REVOKED, MAC đúng | Reject |
| AR-35 | Client disabled, MAC đúng | Reject |
| AR-36 | HMAC valid nhưng tenant-b thiếu grant | Authorization deny, no leak |
| AR-37 | Requested tenant header đổi mà giữ MAC | Signature/binding reject |
| AR-38 | Spring MVC R1 accepted, R2 401 | Business handler chỉ một lần |
| AR-39 | Double filter registration | Không claim nonce hai lần trên R1 |
| AR-40 | Servlet ASYNC/ERROR dispatch | Không false replay |
| AR-41 | Spring WebFlux R1 accepted, R2 401 | No principal/context leak |
| AR-42 | WebFlux DataBuffer error/cancel | Release đúng, không claim trước MAC |
| AR-43 | WebFlux Redis reactive timeout | Fail closed, không block event loop |
| AR-44 | Gateway external/internal URI rewrite | Positive R1 đúng contract, R2 replay reject |
| AR-45 | HTTP/1.1↔HTTP/2 và query order | Byte-level canonical parity |
| AR-46 | gzip/JSON transform sau ký | Reject hoặc transformation theo contract |
| AR-47 | Client spoof gateway identity header | Không bypass |
| AR-48 | Direct backend route bỏ gateway | Trust policy chặn |
| AR-49 | Business 500 sau nonce claim | Nonce vẫn USED |
| AR-50 | HTTP timeout rồi retry y nguyên R1 | Replay rejected |
| AR-51 | Retry với nonce mới + idempotency key cũ | Không nhân đôi business effect |
| AR-52 | Cùng idempotency key, payload khác | Business conflict |
| AR-53 | Payment idempotency ngăn trùng nhưng replay guard tắt | Authn regression test phải FAIL |
| AR-54 | GET signed sensitive data bị phát lại | Theo one-time vs reusable-token contract |
| AR-55 | Public response tiết lộ nonce/key existence | Privacy/security test FAIL |
| AR-56 | Logs chứa raw body + full signature | Security test FAIL |
| AR-57 | Nonce store unavailable nhưng HTTP 2xx | Test FAIL: fail-open |
| AR-58 | Route mới không gắn HMAC filter | Synthetic negative probe phát hiện bypass |
| AR-59 | Primary V2 replay reject nhưng legacy fallback pass | Test FAIL: downgrade |
| AR-60 | Multi-region active-active cùng credential | Global/region guarantee đúng policy |

### Chia bộ test theo tầng

- **Unit:** AR-01–20, AR-30–35, AR-49; fake Clock/atomic store và mutation tests.
- **Integration:** AR-21–24, AR-36–43, AR-49–53; Spring Security, Redis, DB/outbox.
- **Distributed/fault injection:** AR-04–06, AR-25–29, AR-44–48, AR-60.
- **Security regression:** AR-47–48, AR-54–59; authz, logs/privacy và policy downgrade.

Điểm quan trọng không phải số test lớn, mà là **mỗi assertion xác nhận đúng failure mode**, có positive control và quan sát side effect/trust boundary thật.

## 30. Bài tập: vì sao bài test hiện tại PASS nhưng hệ thống vẫn dễ bị replay?

Một nhóm tích hợp viết:

~~~java
@Test
void rejectsOldHmacRequest() throws Exception {
    mockMvc.perform(post("/api/hmac/payments")
            .header("X-Key-Id", "partner-a-prod-k004")
            .header("X-Timestamp", "2025-01-01T00:00:00Z")
            .header("X-Nonce", "nonce-test")
            .header("X-Signature", "invalid-signature"))
        .andExpect(status().isUnauthorized());
}
~~~

Nhóm tuyên bố: “Có timestamp, nonce và test 401 nên đã chống replay.” Nhưng test có **timestamp quá cũ**, signature malformed, không có registry/secret/body canonical hợp lệ và cũng **không gửi request lần hai**. Verifier chỉ kiểm tra expired timestamp hoặc parser malformed cũng PASS.

Hãy trả lời:

1. Vì sao test trên không chứng minh replay guard hoạt động?
2. Cần positive control R1 như thế nào để loại trừ always-401 và signer lỗi?
3. R2 phải giữ những fields nào **giống hệt R1**?
4. MAC đúng trong R2 vì sao vẫn phải reject?
5. Làm sao assert R2 bị từ chối do nonce **ALREADY_USED**, không phải timestamp hết hạn?
6. Nếu chỉ gửi MAC sai và nonce N mới, replay store có được ghi N không?
7. Vì sao `SET NX PX` khác với `exists→set`?
8. Với W=5 phút đối xứng, tại sao TTL 5 phút có thể thiếu?
9. R2 qua Gateway B có thể bypass nếu A/B dùng local nonce store không?
10. Khi Redis mất ACK, caller có được cho request qua không?
11. Khi payment R1 commit nhưng client timeout, retry như thế nào để không làm yếu anti-replay?
12. HMAC đúng có tự cấp quyền `tenant-b` không?
13. Key K3 bị revoke nhưng MAC toán học đúng có được chấp nhận không?
14. Nếu legacy V1 không ký nonce, chỉ thêm Redis claim trên nonce header có đủ an toàn không?

**Định hướng thực hành:** tạo một K4 test credential ACTIVE, signer độc lập ký canonical bytes thật (method, raw URI/query, headers, raw body hash, timestamp, nonce) với Clock cố định. Gửi R1, assert pass + FIRST_USE + một business effect. Gửi exact copy R2 trong cùng cửa sổ, assert 401 + ALREADY_USED + không có business effect thứ hai. Gửi MAC sai N3 rồi MAC đúng N3 để phát hiện nonce poisoning. Lặp với multi-node, Redis timeout, key rotation, gateway và tenant grant tests.

## 31. Checklist loại bỏ anti-pattern “Không chống replay”

- [ ] HMAC request contract có version, ký chính xác method, URI/query, relevant signed headers/body digest, key ID, timestamp và nonce.
- [ ] Shared secret có entropy đủ, độc lập theo credential/environment, được giữ trong secret manager có IAM và rotation.
- [ ] Server exact lookup key ID; credential ACTIVE, chưa REVOKED và đúng principal/audience.
- [ ] Timestamp được ký, validate grammar và window bằng Clock có kiểm soát.
- [ ] Nonce được ký, có length/format/uniqueness policy và được tạo mới cho từng attempt.
- [ ] HMAC verifier không chỉ check nonce format mà phải **atomic first-use claim**.
- [ ] Replay scope được tính từ trusted credential/client identity, không từ tenant/header tự khai tùy ý.
- [ ] Claim nonce **chỉ sau khi MAC đúng**, tránh nonce poisoning.
- [ ] Replay store có conditional insert-if-absent + TTL trong một thao tác, không GET rồi SET.
- [ ] TTL bao phủ toàn bộ khoảng signature còn hợp lệ, kể cả timestamp ở mép tương lai và clock skew.
- [ ] Redis/shared store đáp ứng consistency và failover guarantee ở multi-node/region.
- [ ] Store timeout/UNKNOWN/eviction không dẫn tới fail-open hoặc local fallback không an toàn.
- [ ] Không claim cùng client nonce hai lần khi gateway và backend cùng tham gia; internal assertion có trust/replay policy riêng.
- [ ] Server không thử key/algorithm/canonical version khác khi MAC fail, không hồi sinh revoked key.
- [ ] Servlet filter không double register; body capture bounded và controller nhận đúng raw bytes đã xác minh.
- [ ] WebFlux DataBuffer được release khi complete/error/cancel; reactive nonce claim được compose, không block event loop.
- [ ] R1 valid MAC/nonce mới phải đi qua cùng route/verifier để chứng minh positive control.
- [ ] R2 exact signed copy phải bị reject **khi timestamp còn hợp lệ**.
- [ ] Internal reason/claim state chứng minh replay rejection, không chỉ 401.
- [ ] R2 không tạo principal, không gọi business handler hoặc gây DB/outbox/queue side effect lần hai.
- [ ] Wrong-MAC với nonce mới không consume nonce; right-MAC sau đó vẫn first-use.
- [ ] Concurrency 100 requests, nhiều pods/gateways và Redis failover được kiểm thử.
- [ ] Signed timestamp/nonce/key ID/suite/tenant tampering được phát hiện theo contract.
- [ ] Nonce không bị xóa vì authorization denied, handler 500 hay timeout sau authentication.
- [ ] Client retry sử dụng nonce/signature mới và business idempotency key riêng.
- [ ] HMAC pass không tự cấp quyền tenant/action/resource; authorization tách biệt.
- [ ] Public errors không lộ secret, key existence, nonce state hoặc full canonical bytes.
- [ ] Metrics/logs low cardinality, không chứa full signature/body hoặc raw secret.
- [ ] Có synthetic replay probe phát hiện route mới bỏ HMAC filter hoặc fallback legacy.
- [ ] Migration từ timestamp-only/unsigned-nonce phải nâng contract, SDK, store và rollout có canary.
- [ ] Runbook sự cố bao gồm khóa compromised credential, đối soát side effects và kiểm tra policy trên mọi region.
- [ ] Mọi test dùng credential sandbox, không replay HTTP request thật của đối tác production.

**“Không chống replay” là một anti-pattern bảo mật ngay cả khi HMAC được tính hoàn toàn chính xác.** Một request có MAC hợp lệ chứng minh dữ liệu đã ký chưa đổi và người tạo bằng chứng từng có secret; nó **không chứng minh request chưa từng được sử dụng**. Để loại bỏ lỗ hổng, cần timestamp/nonce được ký, replay store có claim nguyên tử và TTL đủ, fail closed khi không xác định state, đồng thời duy trì exact key lookup, canonical contract, gateway trust và authorization riêng. Khi triển khai xong, bằng chứng quan trọng nhất là **R1 hợp lệ được chấp nhận đúng một lần và R2 y hệt bị từ chối trước mọi side effect**.
