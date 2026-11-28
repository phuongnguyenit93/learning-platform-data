# Response cache trong Idempotency của HTTP request authentication bằng HMAC

**Response cache** trong cơ chế **idempotency** là nơi lưu **kết quả đã được xác định** của một thao tác có side effect, rồi trả lại kết quả ấy khi client retry **cùng một ý định nghiệp vụ** bằng cùng `Idempotency-Key`. Đây không đơn thuần là cache để tăng tốc như HTTP GET cache: response cache phải gắn với **khóa nghiệp vụ, fingerprint request, trạng thái xử lý và kết quả đã commit**, đồng thời ngăn cùng một tác vụ được thực hiện hai lần khi các retry đến đồng thời.

Bài thuộc chương **Idempotency**, module **SECURITY_AUTHENTICATION_HMAC_REQUEST_AUTHENTICATION**. Phạm vi module là xác thực HTTP request bằng **HMAC với shared secret** và canonical request có method, URI, signed headers/body; thực hành xác minh chữ ký, timestamp/nonce chống replay, key rotation, kiểm thử proxy/gateway và phân biệt authentication với authorization. Bài **Response cache** kết hợp các cơ chế ấy với một mục tiêu khác: **retry có an toàn khi mất response, hết thời gian chờ hoặc mạng đứt mà vẫn không tạo side effect lặp?**

**Nguyên lý:** Với mỗi lần retry, client vẫn tạo **timestamp mới, nonce mới và HMAC signature mới**, nhưng giữ nguyên **Idempotency-Key** và **ý định nghiệp vụ**. Server phải **xác minh HMAC, freshness, nonce và quyền ở mỗi request**, rồi mới truy xuất response cache theo một key đã scope đúng. Không bỏ qua HMAC chỉ vì tìm thấy idempotency key trong cache.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích **response cache idempotency** khác HTTP cache, nonce store và business idempotency record thế nào.
2. Thiết kế cache key theo **audience + authenticated client + tenant + operation + Idempotency-Key**, không scope tùy tiện theo nonce hoặc key ID.
3. Tính **request fingerprint ổn định** từ method, raw target, content type, body digest và dữ liệu nghiệp vụ có ý nghĩa; **không** đưa nonce/timestamp/chữ ký thay đổi giữa các retry vào fingerprint.
4. Thiết kế state machine `IN_PROGRESS`, `COMPLETED` và `UNKNOWN/RECONCILIATION`; phân biệt cache hit cùng fingerprint và key collision khác payload.
5. Bảo đảm **atomic reservation** và **persistence kết quả** với transaction/unique constraint; hiểu giới hạn khi gọi dịch vụ ngoài DB.
6. Quy định trạng thái HTTP, status/body/headers nào có thể replay, TTL retention và xử lý timeout hoặc lỗi 5xx.
7. Thực hành Java 17 với HMAC-SHA256, timestamp/nonce, `ConcurrentHashMap.computeIfAbsent`, concurrency test, retry dùng key cũ/nonce mới, key rotation và kiểm tra quyền.
8. Kiểm thử gateway, dữ liệu nhạy cảm, cache poisoning, double execution, ambiguous commit và expiry.

## 2. Vấn đề thực tế: server đã tạo giao dịch nhưng client không nhận được response

Giả sử client gửi:

~~~http
POST /v1/payments?currency=VND HTTP/1.1
Host: api.example.test
Content-Type: application/json
X-Client-Id: partner-42
X-Tenant-Id: shop-01
X-Key-Id: key-2026-11
X-Timestamp: <epoch-seconds>
X-Nonce: <32-lowercase-hex-characters>
Idempotency-Key: <32-lowercase-hex-characters>
X-Content-SHA256: <64-lowercase-hex-characters>
X-Signature: <base64-hmac-sha256-full-tag>

{"orderId":"order-123","amount":50000}
~~~

Các giá trị trong `<...>` là placeholder; request thật phải có giá trị cụ thể và HMAC được tính đúng từ canonical request.

Trình tự sự cố:

~~~mermaid
sequenceDiagram
    participant C as Client
    participant V as HMAC verifier
    participant D as Idempotency + business DB
    C->>V: Request A: idem=K, nonce=N1, ts=T1, HMAC=S1
    V->>V: HMAC/freshness/nonce/authz PASS
    V->>D: Atomic reserve K; tạo payment P; persist response
    D-->>V: HTTP 201, paymentId=P
    Note over V,C: Response bị mất trên mạng
    C->>V: Request B: idem=K, nonce=N2, ts=T2, HMAC=S2
    V->>V: Xác thực request B độc lập
    V->>D: Lookup K + stable fingerprint
    D-->>V: Completed: HTTP 201, paymentId=P
    V-->>C: Trả lại kết quả P, không tạo payment mới
~~~

**Bài toán không phải là “HMAC sai”**: cả A và B đều có thể ký đúng. Nonce `N2` khác `N1` nên replay detector có thể chấp nhận B. Nếu backend không có idempotency, A và B có thể tạo **hai giao dịch khác nhau**, mặc dù client chỉ có một ý định đặt lệnh thanh toán.

| Cơ chế | Khóa/đối tượng | Mục đích |
| --- | --- | --- |
| HMAC verification | Shared secret + canonical request bytes | Xác thực request và các trường đã ký. |
| Nonce replay guard | `(audience, clientId, nonce)` | Ngăn **cùng nonce** được dùng lại trong freshness window. |
| **Idempotency response cache** | `(audience, clientId, tenant, operation, idemKey)` | Nhận ra **cùng ý định nghiệp vụ** dù nonce/HMAC mới và trả lại kết quả đã xử lý. |
| Business uniqueness | Order ID, payment reference hoặc mã định danh giao dịch | Bảo vệ bất biến nghiệp vụ lâu dài, ngay cả sau khi cache hết TTL. |
| Authorization | Identity + tenant + operation + resource | Quyết định ai được xem/khởi tạo thao tác và **xem response đã lưu**. |

### 2.1. Điều gì xảy ra nếu retry cùng nonce?

Retry **nguyên request** với `nonce=N1` sẽ bị nonce store từ chối dù signature và idempotency key đều đúng. Đây là hành vi mong muốn để chống replay. Muốn retry một ý định hợp lệ sau timeout, client **ký một request mới với nonce/timestamp mới**, giữ `Idempotency-Key=K` và cùng input nghiệp vụ.

### 2.2. Cache hit không cho phép bỏ qua authentication

Không được viết:

~~~text
if (cache.contains(idempotencyKey)) {
    return cache.get(idempotencyKey);  // SAI: chưa HMAC/authorization.
}
verifyHmac(request);
~~~

Một attacker không có shared secret có thể đoán/đọc được key hoặc cố lặp lại key và lấy response. Thứ tự đúng là **strict parse → verify HMAC → timestamp/nonce → authorization → idempotency lookup**. Tùy kiến trúc, có thể kiểm tra sơ bộ format/giới hạn tài nguyên trước HMAC, nhưng không được cấp response chứa dữ liệu nhạy cảm khi identity và quyền chưa được xác thực.

## 3. Idempotency-Key và cache namespace

### 3.1. Idempotency-Key phải có trong canonical request

Contract ví dụ dùng một `Idempotency-Key` duy nhất, 16 byte ngẫu nhiên mã hóa thành **32 ký tự hex chữ thường**.

~~~java
import java.security.SecureRandom;
import java.util.HexFormat;

byte[] random = new byte[16];
new SecureRandom().nextBytes(random);
String idempotencyKey = HexFormat.of().formatHex(random);
~~~

Client tạo key **một lần cho một ý định nghiệp vụ**, lưu nó đủ lâu để retry, và **không** tạo key mới chỉ vì lần gửi trước bị timeout. Với ý định nghiệp vụ mới, tạo key mới. Sử dụng CSPRNG và định dạng đúng contract giúp giảm va chạm ngoài ý muốn và nguy cơ đoán key.

**Idempotency-Key phải được HMAC ký.** Nếu header này nằm ngoài canonical, attacker/proxy có thể thay key của request hợp lệ mà không làm sai tag, khiến backend tạo thao tác mới hoặc truy xuất sai response.

### 3.2. Phạm vi khóa chống cross-client/cross-tenant

Cache key minh họa:

~~~text
cacheKey = encodeTuple(
    audience,
    authenticatedClientId,
    authorizedTenantId,
    operationId,
    idempotencyKey
)
~~~

Trong ví dụ:

~~~text
audience       = payments-api
clientId       = partner-42
tenantId       = shop-01
operationId    = POST:/v1/payments
idempotencyKey = 9af0cb1496474a91b351072e9d7c2eae
~~~

| Thành phần | Vì sao nên có? |
| --- | --- |
| Audience | Không chia sẻ response giữa các dịch vụ không cùng trust domain. |
| Authenticated client ID | Khóa cùng text từ hai client không nên làm lộ/đụng kết quả. |
| Tenant ID được authorize | Client có nhiều tenant không được đọc response tenant khác do trùng key. |
| Operation ID | Tránh dùng kết quả tạo payment để trả cho thao tác hoàn tiền/job khác. |
| Idempotency-Key | Nhận dạng một ý định cụ thể của client trong namespace đó. |

**Không đưa timestamp, nonce hoặc HMAC tag vào cache key**: chúng **phải thay đổi** ở retry, khiến cache miss và vô hiệu hóa idempotency. **Không mặc định đưa key ID vào cache key**: khi rotate từ key cũ sang key mới, một ý định đang retry vẫn phải nhận **cùng kết quả**, nếu client và scope không đổi.

Giá trị `clientId`/`tenantId` do HTTP client khai **chưa đáng tin** trước khi HMAC và authorization được kiểm tra. Không dùng chúng để tiết lộ response trước bước ấy.

### 3.3. Encoding tuple và hash lưu trữ

Nếu store key là chuỗi `audience + ":" + client + ":" + tenant + ":" + key`, một thành phần có dấu `:` có thể gây nhập nhằng. Hãy validate alphabet hoặc dùng **length-prefix serialization**; có thể hash tuple byte chính tắc bằng SHA-256 để giữ key cố định.

~~~text
scopeBytes = encodeLengthPrefixed(audience, client, tenant, operation, idemKey)
storageKey = "idem:v1:" + lowerHex(SHA256(scopeBytes))
~~~

Hash cache key **không thay thế** authentication/authorization; nó giúp lưu trữ có key đồng nhất và tránh ký tự đặc biệt. Phải giữ version của encoding để các replica có cùng cách tạo key.

## 4. Request fingerprint: cùng key nhưng khác nội dung phải bị từ chối

Idempotency key được dùng lại **chưa đủ** để biết đây là cùng ý định. Ví dụ:

~~~http
Idempotency-Key: 9af0cb1496474a91b351072e9d7c2eae

{"orderId":"order-123","amount":50000}
~~~

Sau đó client (hoặc bug) gửi:

~~~http
Idempotency-Key: 9af0cb1496474a91b351072e9d7c2eae

{"orderId":"order-123","amount":90000}
~~~

Nếu cache chỉ nhìn key và trả về 201 của lần đầu, client có thể **hiểu nhầm** giao dịch amount 90000 đã được xử lý. Nếu backend nhìn thấy key và tiếp tục thực thi body mới, lại vi phạm idempotency.

**Quy tắc:** cùng idempotency key + **cùng fingerprint** → kết quả cũ hoặc IN_PROGRESS; cùng key + **fingerprint khác** → reject **key reuse conflict** (ví dụ HTTP 409). Không ghi đè fingerprint gốc và không thực thi body thứ hai.

### 4.1. Fingerprint bao gồm dữ liệu gì?

Fingerprint phiên bản `IDEMPOTENCY-FINGERPRINT-V1` được server tính từ **request sau khi đã xác thực**, ví dụ:

~~~text
IDEMPOTENCY-FINGERPRINT-V1
POST
/v1/payments?currency=VND
audience:payments-api
tenant:shop-01
content-type:application/json
body-sha256:<lowerhex-SHA256(bodyBytes)>
~~~

Sau đó:

~~~text
fingerprint = lowerHex(SHA256(UTF8(fingerprintInput)))
~~~

Vì trong ví dụ `bodyBytes` là JSON serialized chính xác và **không được server canonicalize JSON**, hai JSON byte khác nhau (kể cả thay thứ tự key/whitespace) có fingerprint khác nhau. Đây là lựa chọn **conservative**: có thể reject hai JSON tương đương về nghĩa; đổi lại tránh vô tình xem hai payload khác byte là một. Nếu cần so sánh theo ngữ nghĩa, phải có **schema canonicalization và business identity contract** rõ ràng, không tự trim/normalize tùy ý.

| Nên nằm trong fingerprint/namespace | Không nên đưa vào stable fingerprint |
| --- | --- |
| Method/effective action đã được ký | Signed timestamp mới của retry |
| Raw URI/query hoặc operation/route canonical ổn định | Nonce mới của retry |
| Tenant, audience, client scope | Giá trị HMAC signature của retry |
| Content-Type/Content-Encoding theo contract | Key ID của request retry nếu không đổi quyền |
| SHA-256 của body bytes thực nhận; business parameters | Header tracing/request ID không liên quan ngữ nghĩa |
| Version của schema/representation | Giá trị header proxy do bên không tin cậy chèn |

Idempotency key bản thân nằm trong **cache namespace**, nên không cần lặp trong fingerprint; nếu có, phải luôn dùng **chính giá trị đã được HMAC ký**. Với API có semantic header khác như currency, region, target account, chúng phải được ràng buộc trong canonical/fingerprint.

### 4.2. Fingerprint là digest, không phải HMAC authorization

SHA-256 fingerprint giúp phát hiện input khác nhau, **không phải secret** và không thay thế HMAC request. Collision resistance của SHA-256 khiến hash phù hợp cho fingerprint, nhưng an toàn thực tế còn đòi **đúng tập field**; một hash không bao gồm `amount` hoặc `destinationAccount` dù rất khó collision vẫn không bảo vệ hai trường đó.

## 5. State machine response cache

Không thể chỉ lưu map `idempotencyKey -> responseBody`. Trong thực tế, request B có thể đến **khi A vẫn đang xử lý**.

~~~mermaid
stateDiagram-v2
    [*] --> ABSENT
    ABSENT --> IN_PROGRESS: Atomic reserve(key,fingerprint)
    IN_PROGRESS --> COMPLETED: Business commit + response persisted
    IN_PROGRESS --> UNKNOWN: Crash/timeout sau khi có thể đã side effect
    IN_PROGRESS --> FAILED_RETRYABLE: Chứng minh chưa có side effect (theo policy)
    FAILED_RETRYABLE --> IN_PROGRESS: Retry có kiểm soát
    UNKNOWN --> COMPLETED: Reconcile business outcome
    UNKNOWN --> REQUIRES_REVIEW: Không xác định được kết quả
    COMPLETED --> EXPIRED: Hết retention được công bố
    EXPIRED --> [*]
~~~

Trạng thái minh họa:

| State | Ý nghĩa | Hành vi retry cùng key/fingerprint |
| --- | --- | --- |
| **ABSENT** | Chưa có idempotency record trong retention | Có thể atomic reserve và xử lý mới. |
| **IN_PROGRESS** | Một worker đang sở hữu xử lý | Không tạo side effect thứ hai; có thể trả `202 Processing`/`409 In progress` hoặc đợi có giới hạn. |
| **COMPLETED** | Kết quả đã commit và response replayable đã persist | Trả lại status/body/vetted headers đã lưu; không chạy business lần nữa. |
| **UNKNOWN** | Không biết side effect có hoàn thành không | **Không tự chạy lại**; reconcile qua business reference/idempotent downstream. |
| **FAILED_RETRYABLE** | Chắc chắn chưa có side effect và policy cho phép retry | Cho retry có kiểm soát/atomic takeover. |
| **EXPIRED** | Record hết hạn lưu theo contract | Có thể bị coi là ý định mới nếu không có business uniqueness lâu dài. |

**State phải được cập nhật atomically cùng các bất biến cần bảo vệ.** Một record `COMPLETED` chỉ được phát hành khi kết quả nghiệp vụ đã được ghi bền vững theo transaction policy. Nếu chỉ update cache response **trước** khi commit payment, retry có thể nhận “đã thanh toán” trong khi payment rollback.

### 5.1. Concurrent first requests: chỉ một owner

~~~mermaid
sequenceDiagram
    participant A as Request A (nonce N1)
    participant B as Request B (nonce N2)
    participant I as Idempotency store
    participant P as Payment processor
    par Cùng Idempotency-Key=K
        A->>I: Reserve-if-absent K, fingerprint F
    and
        B->>I: Reserve-if-absent K, fingerprint F
    end
    I-->>A: Ví dụ CREATED / owner
    I-->>B: EXISTING / IN_PROGRESS
    A->>P: Execute payment once
    B-->>B: Không thực thi payment
    P-->>A: Payment P đã commit
    A->>I: Save COMPLETED + status/body
    I-->>A: Persisted
    Note over A,B: Retry sau có thể nhận response đã lưu
~~~

Kết quả A/B có thể đảo chiều; bất biến là **tối đa một owner xử lý một key/fingerprint** trong cùng namespace khi store bình thường. Nếu request đến với **fingerprint khác**, phải trả conflict ngay cả khi record đầu đang IN_PROGRESS.

### 5.2. Response cache phải bền vững đến đâu?

Nếu payment đã commit nhưng cache response ghi trên một Redis không bền vững, failover có thể làm **mất record COMPLETED**; retry `Idempotency-Key=K` trông như request mới và có thể tạo payment trùng. Do đó **cache đóng vai trò bảo đảm nghiệp vụ**, không chỉ optimization.

Các phương án mạnh hơn gồm SQL transaction ghi payment và idempotency outcome chung DB, unique constraint business ID, durable downstream idempotency key, outbox hoặc quy trình reconciliation. Không có phép thuật “exactly once” tự xuất hiện từ một `ConcurrentHashMap` hoặc cache `SET NX`.

## 6. Thiết kế response được cache và replay

### 6.1. Lưu kết quả nào?

Với một response thành công:

~~~http
HTTP/1.1 201 Created
Content-Type: application/json
Location: /v1/payments/pay-000001

{"paymentId":"pay-000001","status":"CREATED"}
~~~

Record nên chứa **status HTTP, response body đã ổn định và các response metadata được whitelist**; có thể thay vì lưu toàn bộ JSON thì lưu **business outcome ID** và dựng response từ nguồn bền vững khi retry. Quyết định nào cũng phải giữ ổn định thông tin caller được hứa trong contract.

**Không** sao chép bừa toàn bộ HTTP response headers vào cache:

- `Date`, `Server`, `Connection`, `Transfer-Encoding`, `Content-Length` và các hop-specific/transport metadata nên được hệ thống HTTP tạo lại hoặc tính đúng từ body thực gửi.
- `Set-Cookie`, bearer token, response HMAC nonce, session headers hoặc các credential có thể gây **session leakage** nếu replay nguyên trạng.
- Các header biểu diễn `Content-Encoding`, `ETag`, `Vary` cần policy nhất quán với body representation được trả lại.
- `Location` hoặc resource ID có thể được lưu nếu nó là kết quả bất biến đã commit và caller vẫn có quyền nhìn thấy.

**Cache response nhạy cảm phải scope đúng tenant và xác minh authorization trên mọi lần đọc**, có mã hóa at rest/kiểm soát RBAC/log theo chính sách dữ liệu. Không để một client đoán idempotency key của client khác và lấy JSON chứa payment/account.

### 6.2. Response ở trạng thái IN_PROGRESS

Hai lựa chọn ví dụ:

~~~http
HTTP/1.1 202 Accepted
Content-Type: application/json
Retry-After: 2

{"status":"PROCESSING","message":"Retry với cùng Idempotency-Key"}
~~~

hoặc một lỗi conflict riêng (`409`) cho trạng thái in progress. Hợp đồng phải phân biệt **409 do key dùng với fingerprint khác** và trạng thái “request cũ đang xử lý”; không để client hiểu 202 là **payment đã commit**. `Retry-After` là một gợi ý, không phải deadline bảo đảm.

Khi retry, client cần **nonce/timestamp/signature mới**; không gửi lại cùng chữ ký/nonce và kỳ vọng response cache trả về.

### 6.3. Có nên cache HTTP 4xx và 5xx không?

Không có một chính sách mặc định đúng cho mọi API:

| Kết quả | Gợi ý policy |
| --- | --- |
| 201/200 sau commit | Có thể lưu response bền vững và replay giống kết quả lần đầu. |
| 202 đã chấp nhận một job lâu dài | Lưu **job ID/trạng thái bền vững**, cho retry biết cùng job; không tạo job thứ hai. |
| 400 validation trước side effect | Có thể không reserve hoặc lưu lỗi deterministic ngắn hạn; quy định rõ trong contract. |
| 401/403 của retry | **Không trả cached business response** khi request hiện tại chưa authenticated/authorized. |
| 409 cùng key khác fingerprint | Conflict; không ghi đè record gốc. |
| 429 rate limit | Không tự coi là business outcome đã commit; tách rate policy khỏi outcome cache. |
| 500 trước side effect chắc chắn | Có thể cho retry có kiểm soát sau xác minh không có side effect. |
| Timeout/500 sau side effect có thể xảy ra | **UNKNOWN**, reconcile; không tự chạy lại chỉ vì 500. |

Một số API cố tình cache cả response 500 như một phần contract. Nếu chọn cách ấy, phải đánh giá trường hợp thực tế **side effect đã/ chưa xảy ra**, TTL và cách client biết kết quả; đừng tự đoán rằng 5xx luôn nghĩa là chưa commit.

## 7. Retry đã ký HMAC và response cache: thứ tự bảo mật

~~~mermaid
flowchart TD
    A["Request mới hoặc retry tại trusted ingress"] --> B["Strict HTTP parse: method, URI, headers/body, duplicate"]
    B --> C["Decode HMAC signature; chọn key theo client/key ID"]
    C --> D["Recompute canonical: method/URI/headers/body + idem key"]
    D --> E{"Full HMAC tag hợp lệ? Key active?"}
    E -->|Không| X["401 / authentication reject"]
    E -->|Có| F{"Timestamp fresh và nonce atomic claim?"}
    F -->|Không| X
    F -->|Có| G{"Authorization hiện tại cho tenant/action/resource?"}
    G -->|Không| Y["403 / deny, không trả cached body"]
    G -->|Có| H["Tạo stable fingerprint và scoped cache key"]
    H --> I{"Atomic lookup/reserve state?"}
    I -->|Key có fingerprint khác| J["409 key reuse conflict"]
    I -->|COMPLETED cùng fingerprint| K["Replay cached outcome, không side effect"]
    I -->|IN_PROGRESS cùng fingerprint| L["202 Processing / bounded wait"]
    I -->|NEW reservation| M["Thực thi một lần + persist outcome"]
    M --> N["COMPLETED: trả original outcome"]
    I -->|UNKNOWN| O["Reconcile, không tự execute lần nữa"]
~~~

**Lưu ý:** Pipeline có thể đổi thứ tự kiểm tra không có side effect để giảm CPU (như validation format hoặc kiểm tra timestamp trước HMAC), nhưng **đọc/trả response cache nhạy cảm phải sau authn/authz**, và không được xử lý nghiệp vụ trước khi nonce và idempotency reservation đã được bảo vệ.

### 7.1. Tại sao nonce và idempotency key có TTL khác nhau?

Với timestamp policy minh họa `pastWindow = 300 giây`, `futureTolerance = 60 giây` và safety margin `10 giây`, nonce store phải lưu nonce đủ khoảng **370 giây** từ lần claim sớm nhất, hoặc tới `signedTimestamp + 300 + margin`. Đây là cửa sổ **xác thực/chống replay**.

Idempotency record có thể cần giữ **24 giờ** hoặc nhiều ngày tùy SLA retry và trách nhiệm pháp lý/nghiệp vụ. Đây là cửa sổ **ý định nghiệp vụ**, không phải cửa sổ của HMAC. Nếu cache record hết hạn nhưng business transaction vẫn tồn tại, **business unique ID** có thể tiếp tục bảo đảm không tạo kết quả trùng.

~~~text
nonceRetention ~= 300 + 60 + 10 = 370 seconds (ví dụ)
idempotencyRetention = 24 hours (ví dụ, phải công bố)
businessUniqueness   = theo miền nghiệp vụ (có thể dài hơn rất nhiều)
~~~

Không đặt TTL idempotency theo nonce TTL rồi chấp nhận retry sau 10 phút tạo payment mới, nếu contract hứa an toàn retry nhiều giờ.

### 7.2. HMAC key rotation khi retry

Giả sử request A ký bằng `key-2026-11`, còn B retry sau rotation bằng `key-2026-12`. Cả hai phải được xác minh **đúng key record** của từng request; nếu key cũ đã revoke, request cũ không tự được “miễn” vì từng tồn tại cache entry. Khi B hợp lệ và cùng idempotency key/fingerprint, backend nên **trả lại outcome cũ**.

Không đưa key ID vào response cache namespace nếu không có lý do nghiệp vụ rất cụ thể: thay key sẽ tạo cache miss và có nguy cơ thực thi hai lần.

## 8. SQL transaction và unique constraint để lưu response bền vững

Một schema minh họa dùng PostgreSQL:

~~~sql
CREATE TABLE idempotency_responses (
    audience           text NOT NULL,
    client_id          text NOT NULL,
    tenant_id          text NOT NULL,
    operation_id       text NOT NULL,
    idempotency_key    text NOT NULL,
    fingerprint_sha256 char(64) NOT NULL,
    state              text NOT NULL
                       CHECK (state IN ('IN_PROGRESS','COMPLETED','UNKNOWN')),
    response_status    integer,
    response_type      text,
    response_body      bytea,
    resource_id        text,
    created_at         timestamptz NOT NULL DEFAULT now(),
    expires_at         timestamptz NOT NULL,
    PRIMARY KEY (
        audience, client_id, tenant_id, operation_id, idempotency_key
    ),
    CHECK (
        (state <> 'COMPLETED') OR
        (response_status IS NOT NULL AND response_body IS NOT NULL)
    )
);
~~~

Unique primary key bảo đảm các transaction cùng scope/key không thể tạo **hai reservation cùng tồn tại**. Một bước reserve ví dụ:

~~~sql
INSERT INTO idempotency_responses (
    audience, client_id, tenant_id, operation_id, idempotency_key,
    fingerprint_sha256, state, expires_at
) VALUES ($1, $2, $3, $4, $5, $6, 'IN_PROGRESS', $7)
ON CONFLICT DO NOTHING
RETURNING idempotency_key;
~~~

**Một row được trả:** mình sở hữu reservation mới, có thể xử lý theo state machine. **Không row:** record đã tồn tại; đọc nó, xác minh fingerprint tương ứng, rồi quyết định `COMPLETED`/`IN_PROGRESS`/`UNKNOWN`. **Không** làm `SELECT` rồi `INSERT` thiếu unique constraint. Với transaction chưa commit, DB có thể đợi conflict resolution; phải thiết kế timeout và rollback cẩn thận.

### 8.1. Khi business effect ở cùng một database

Cách dễ suy luận nhất là giữ **business write và completed outcome** trong **một DB transaction**, với khóa uniqueness đủ mạnh:

~~~text
BEGIN TRANSACTION
  1) INSERT idempotency reservation có unique constraint
  2) Nếu không phải owner: không chạy business; trả existing sau transaction
  3) Insert/update payment và ledger với business invariant/unique ID
  4) Update idempotency record:
       state=COMPLETED,
       response_status=201,
       response_body=outcome đã chốt,
       resource_id=payment ID
COMMIT
Trả response CHỈ sau commit thành công.
~~~

Nếu transaction rollback trước commit, cả payment và response record rollback cùng nhau. Nếu commit thành công nhưng HTTP response mất, retry tra record COMPLETED và trả lại **cùng payment**.

Không giữ DB transaction mở xuyên một HTTP call đến payment gateway không nằm trong DB rồi kỳ vọng ACID bao phủ gateway. Khi có **external side effect**, cần state machine durable, **outbox**, downstream idempotency key và reconciliation.

### 8.2. Khi external payment provider gặp timeout

Ví dụ:

~~~text
1) Persist reservation IN_PROGRESS cho K
2) Gửi payment API với downstreamIdempotencyKey = K_scoped
3) Provider có thể đã tạo payment P
4) Network timeout: caller không nhận provider response
5) Đánh dấu UNKNOWN, không phát lệnh payment thứ hai tùy tiện
6) Query provider bằng stable business reference/K_scoped
7) Reconcile P rồi persist COMPLETED + response
8) Retry của client chỉ xem trạng thái, không execute duplicate
~~~

Nếu provider không hỗ trợ idempotency/tra cứu kết quả, **không thể hứa exactly-once side effect** chỉ bằng response cache ở application layer. Phải nêu rõ giới hạn và quy trình xử lý UNKNOWN/manual reconciliation.

## 9. Java 17: mô phỏng signed retry và response cache

Chương trình Java 17 dưới đây có thể đặt trong **một file `IdempotencyResponseCacheExample.java`**. Nó trình bày signer, HMAC verifier và một **in-memory response cache mô phỏng**:

- Client gửi request tạo payment bằng `Idempotency-Key=K`, nonce ngẫu nhiên và signed timestamp.
- Verifier kiểm tra signature Base64 chuẩn padded, HMAC-SHA256 full 32 byte, body digest và key policy; claim nonce.
- Authorization được đánh giá cho **mỗi request** trước khi đọc response cache.
- Cache sử dụng `ConcurrentHashMap.computeIfAbsent` để tạo **một owner**; request khác cùng fingerprint đang xử lý nhận 202, đã hoàn thành nhận 201 cached; payload khác cùng key nhận 409.
- Test retry nonce/timestamp mới, retry qua key rotation, tampering, concurrent requests và chặn response tenant không đủ quyền.

**Lưu ý:** đây là **unit-test illustration**, không phải triển khai payment production. Map trong JVM không bền vững/TTL/distributed transaction; state `IN_PROGRESS` có thể tồn tại vô hạn khi JVM crash hay worker lỗi; muốn an toàn thật cần database, durability, reconciliation và middleware HTTP đáng tin.

### 9.1. Signing contract của ví dụ

Canonical request được tạo bằng cách nối **LF 0x0A**, UTF-8, không có LF cuối:

~~~text
HMAC-IDEMPOTENCY-RESPONSE-V1
POST
/v1/payments?currency=VND
audience:payments-api
x-client-id:partner-42
x-tenant-id:shop-01
x-key-id:<active-key-id>
x-timestamp:<epoch-seconds>
x-nonce:<32-lowercase-hex>
idempotency-key:<32-lowercase-hex>
content-type:application/json
x-content-sha256:<64-lowercase-hex>
~~~

`X-Signature` không nằm trong canonical vì nó là kết quả HMAC của canonical. Dấu thời gian và nonce **phải thay đổi khi retry**, còn `idempotency-key` và business input **giữ nguyên**. Server tra key theo client ID + key ID nhưng chỉ công nhận identity **sau** HMAC đúng và key policy đạt.

### 9.2. Mã nguồn minh họa hoàn chỉnh

~~~java
import java.net.URI;
import java.net.http.HttpRequest;
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.Arrays;
import java.util.Base64;
import java.util.HexFormat;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public final class IdempotencyResponseCacheExample {
    private static final SecureRandom RNG = new SecureRandom();
    private static final String METHOD = "POST";
    private static final String TARGET = "/v1/payments?currency=VND";
    private static final String OPERATION = "POST:/v1/payments";
    private static final String AUDIENCE = "payments-api";
    private static final String CLIENT = "partner-42";
    private static final String TENANT = "shop-01";
    private static final String OLD_KEY = "key-2026-11";
    private static final String NEW_KEY = "key-2026-12";
    private static final String CONTENT_TYPE = "application/json";
    private static final long PAST_SECONDS = 300;
    private static final long FUTURE_SECONDS = 60;

    record Request(
        String method, String target, String clientId, String tenantId,
        String keyId, String timestamp, String nonce, String idemKey,
        String contentType, String bodyHash, String signature, byte[] body
    ) {}

    record KeyRecord(
        String clientId, String keyId, byte[] secret,
        Instant activeFrom, Instant expiresAt, boolean revoked
    ) {}

    // Response là dữ liệu nghiệp vụ ổn định; không giữ raw auth headers.
    record Result(int status, String contentType, String body,
                  boolean fromCache) {}

    record CacheKey(String audience, String clientId, String tenantId,
                    String operation, String idemKey) {}

    static final class Entry {
        final String fingerprint;
        volatile Result completed;  // Null = đang xử lý hoặc không rõ outcome.

        Entry(String fingerprint) {
            this.fingerprint = fingerprint;
        }
    }

    // Demo một JVM: không TTL, không durable, không dùng cho cluster.
    static final class ResponseCache {
        final ConcurrentHashMap<CacheKey, Entry> entries =
            new ConcurrentHashMap<>();
    }

    // Demo một JVM: production phải dùng atomic shared nonce store + TTL.
    static final class NonceStore {
        private final Set<String> used =
            ConcurrentHashMap.newKeySet();

        boolean claim(String audience, String client, String nonce) {
            return used.add(audience + ":" + client + ":" + nonce);
        }
    }

    static byte[] random32() {
        byte[] bytes = new byte[32];
        RNG.nextBytes(bytes);
        return bytes;
    }

    static String randomHex16() {
        byte[] bytes = new byte[16];
        RNG.nextBytes(bytes);
        return HexFormat.of().formatHex(bytes);
    }

    static String sha256Hex(byte[] data)
            throws GeneralSecurityException {
        return HexFormat.of().formatHex(
            MessageDigest.getInstance("SHA-256").digest(data));
    }

    static byte[] hmac(byte[] secret, String canonical)
            throws GeneralSecurityException {
        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(secret, "HmacSHA256"));
        return mac.doFinal(
            canonical.getBytes(StandardCharsets.UTF_8));
    }

    static String canonical(Request r, String actualBodyHash) {
        if (!METHOD.equals(r.method()) || !TARGET.equals(r.target()) ||
            !CLIENT.equals(r.clientId()) ||
            r.tenantId() == null ||
            !r.tenantId().matches("[a-z0-9-]{1,40}") ||
            !(OLD_KEY.equals(r.keyId()) || NEW_KEY.equals(r.keyId())) ||
            !CONTENT_TYPE.equals(r.contentType()) ||
            r.timestamp() == null ||
            !r.timestamp().matches("[1-9][0-9]{0,18}") ||
            r.nonce() == null ||
            !r.nonce().matches("[0-9a-f]{32}") ||
            r.idemKey() == null ||
            !r.idemKey().matches("[0-9a-f]{32}") ||
            actualBodyHash == null ||
            !actualBodyHash.matches("[0-9a-f]{64}")) {
            throw new IllegalArgumentException("Invalid signing contract");
        }
        return String.join("\n",
            "HMAC-IDEMPOTENCY-RESPONSE-V1",
            r.method(), r.target(),
            "audience:" + AUDIENCE,
            "x-client-id:" + r.clientId(),
            "x-tenant-id:" + r.tenantId(),
            "x-key-id:" + r.keyId(),
            "x-timestamp:" + r.timestamp(),
            "x-nonce:" + r.nonce(),
            "idempotency-key:" + r.idemKey(),
            "content-type:" + r.contentType(),
            "x-content-sha256:" + actualBodyHash);
    }

    static byte[] decodeFullHmacTag(String signature) {
        if (signature == null ||
            !signature.matches("[A-Za-z0-9+/]{43}=")) {
            return null;
        }
        try {
            byte[] result = Base64.getDecoder().decode(signature);
            if (result.length != 32 ||
                !Base64.getEncoder().encodeToString(result)
                    .equals(signature)) {
                return null;
            }
            return result;
        } catch (IllegalArgumentException malformed) {
            return null;
        }
    }

    static Long parseTimestamp(String timestamp) {
        if (timestamp == null ||
            !timestamp.matches("[1-9][0-9]{0,18}")) {
            return null;
        }
        try {
            return Long.parseLong(timestamp);
        } catch (NumberFormatException overflow) {
            return null;
        }
    }

    static boolean fresh(long signed, long now) {
        try {
            return signed >= Math.subtractExact(now, PAST_SECONDS) &&
                   signed <= Math.addExact(now, FUTURE_SECONDS);
        } catch (ArithmeticException overflow) {
            return false;
        }
    }

    static Request sign(String tenant, String keyId,
            byte[] secret, String idemKey, byte[] body, Clock clock)
            throws GeneralSecurityException {
        String nonce = randomHex16(); // MỖI retry tạo nonce mới.
        String timestamp =
            Long.toString(clock.instant().getEpochSecond());
        String hash = sha256Hex(body);
        Request unsigned = new Request(
            METHOD, TARGET, CLIENT, tenant, keyId, timestamp,
            nonce, idemKey, CONTENT_TYPE, hash, "", body.clone());
        String text = canonical(unsigned, hash);
        String signature = Base64.getEncoder().encodeToString(
            hmac(secret, text));
        return new Request(
            METHOD, TARGET, CLIENT, tenant, keyId, timestamp,
            nonce, idemKey, CONTENT_TYPE, hash, signature, body.clone());
    }

    static boolean verifyAndClaim(Request r, Map<String, KeyRecord> keys,
            Clock clock, NonceStore nonceStore)
            throws GeneralSecurityException {
        if (r == null || r.body() == null ||
            r.body().length > 65536) {
            return false;
        }
        byte[] supplied = decodeFullHmacTag(r.signature());
        Long ts = parseTimestamp(r.timestamp());
        if (supplied == null || ts == null) {
            return false;
        }
        Instant at = clock.instant();
        if (!fresh(ts, at.getEpochSecond())) {
            return false;
        }

        final String signedText;
        try {
            String actualBodyHash = sha256Hex(r.body());
            if (!actualBodyHash.equals(r.bodyHash())) {
                return false;
            }
            signedText = canonical(r, actualBodyHash);
        } catch (IllegalArgumentException invalid) {
            return false;
        }

        KeyRecord key = keys.get(r.clientId() + ":" + r.keyId());
        if (key == null || key.revoked() ||
            !r.clientId().equals(key.clientId()) ||
            !r.keyId().equals(key.keyId()) ||
            key.secret() == null || key.secret().length < 32 ||
            at.isBefore(key.activeFrom()) ||
            !at.isBefore(key.expiresAt())) {
            return false;
        }
        byte[] expected = hmac(key.secret(), signedText);
        if (expected.length != 32 ||
            !MessageDigest.isEqual(expected, supplied)) {
            return false;
        }
        // Chỉ claim nonce sau HMAC. Idem cache KHÔNG nằm trước bước này.
        return nonceStore.claim(AUDIENCE, r.clientId(), r.nonce());
    }

    // Stable fingerprint: KHÔNG bao gồm nonce, timestamp, signature/key ID.
    static String fingerprint(Request r)
            throws GeneralSecurityException {
        String input = String.join("\n",
            "IDEMPOTENCY-FINGERPRINT-V1",
            r.method(), r.target(),
            "audience:" + AUDIENCE,
            "tenant:" + r.tenantId(),
            "content-type:" + r.contentType(),
            "body-sha256:" + sha256Hex(r.body()));
        return sha256Hex(input.getBytes(StandardCharsets.UTF_8));
    }

    static Result handle(Request r, Map<String, KeyRecord> keys,
            Clock clock, NonceStore nonceStore, ResponseCache cache,
            AtomicInteger businessExecutions)
            throws GeneralSecurityException {
        if (!verifyAndClaim(r, keys, clock, nonceStore)) {
            return new Result(401, "application/json",
                "{\"error\":\"UNAUTHENTICATED\"}", false);
        }

        // Mô phỏng authorization hiện tại. Trong thực tế tra ACL/tenant.
        if (!TENANT.equals(r.tenantId())) {
            return new Result(403, "application/json",
                "{\"error\":\"FORBIDDEN\"}", false);
        }

        CacheKey key = new CacheKey(
            AUDIENCE, r.clientId(), r.tenantId(),
            OPERATION, r.idemKey());
        String currentFingerprint = fingerprint(r);
        AtomicBoolean owner = new AtomicBoolean(false);
        Entry entry = cache.entries.computeIfAbsent(key, k -> {
            owner.set(true);
            return new Entry(currentFingerprint);
        });

        if (!entry.fingerprint.equals(currentFingerprint)) {
            return new Result(409, "application/json",
                "{\"error\":\"IDEMPOTENCY_KEY_REUSED_WITH_NEW_INPUT\"}",
                false);
        }
        if (!owner.get()) {
            Result previous = entry.completed;
            if (previous != null) {
                return new Result(previous.status(),
                    previous.contentType(), previous.body(), true);
            }
            return new Result(202, "application/json",
                "{\"status\":\"PROCESSING\"}", false);
        }

        // Mô phỏng side effect CHỈ cho owner của idempotency key.
        // Trong production cần DB transaction/outbox/durable outcome.
        int paymentNumber = businessExecutions.incrementAndGet();
        String response = "{\"paymentId\":\"pay-" +
            paymentNumber + "\",\"status\":\"CREATED\"}";
        Result completed =
            new Result(201, "application/json", response, false);
        entry.completed = completed;
        return completed;
    }

    static Request withBody(Request r, byte[] changed) {
        return new Request(
            r.method(), r.target(), r.clientId(), r.tenantId(),
            r.keyId(), r.timestamp(), r.nonce(), r.idemKey(),
            r.contentType(), r.bodyHash(), r.signature(), changed);
    }

    static void require(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    static void rfc4231KnownAnswer() throws Exception {
        byte[] secret = new byte[20];
        Arrays.fill(secret, (byte) 0x0b);
        String actual = HexFormat.of().formatHex(
            hmac(secret, "Hi There"));
        String expected =
            "b0344c61d8db38535ca8afceaf0bf12" +
            "b881dc200c9833da726e9376c2e32cff7";
        require(actual.equals(expected), "RFC 4231 known-answer test");
    }

    public static void main(String[] args) throws Exception {
        rfc4231KnownAnswer();
        byte[] oldSecret = random32();
        byte[] newSecret = random32();
        Instant from = Instant.parse("2026-01-01T00:00:00Z");
        Instant until = Instant.parse("2027-01-01T00:00:00Z");
        Map<String, KeyRecord> keyring = Map.of(
            CLIENT + ":" + OLD_KEY,
            new KeyRecord(CLIENT, OLD_KEY, oldSecret,
                from, until, false),
            CLIENT + ":" + NEW_KEY,
            new KeyRecord(CLIENT, NEW_KEY, newSecret,
                from, until, false));
        Clock clock = Clock.fixed(
            Instant.parse("2026-11-28T02:00:00Z"), ZoneOffset.UTC);
        byte[] body = "{\"orderId\":\"order-123\",\"amount\":50000}"
            .getBytes(StandardCharsets.UTF_8);
        String idemKey = randomHex16();
        NonceStore nonceStore = new NonceStore();
        ResponseCache cache = new ResponseCache();
        AtomicInteger executions = new AtomicInteger();

        Request first = sign(
            TENANT, OLD_KEY, oldSecret, idemKey, body, clock);
        HttpRequest sample = HttpRequest.newBuilder(
                URI.create("https://api.example.test" + TARGET))
            .header("Content-Type", first.contentType())
            .header("X-Client-Id", first.clientId())
            .header("X-Tenant-Id", first.tenantId())
            .header("X-Key-Id", first.keyId())
            .header("X-Timestamp", first.timestamp())
            .header("X-Nonce", first.nonce())
            .header("Idempotency-Key", first.idemKey())
            .header("X-Content-SHA256", first.bodyHash())
            .header("X-Signature", first.signature())
            .POST(HttpRequest.BodyPublishers.ofByteArray(first.body()))
            .build(); // Không gửi request ra mạng.
        require(METHOD.equals(sample.method()),
            "HTTP method mismatch");

        Result created = handle(first, keyring, clock,
            nonceStore, cache, executions);
        require(created.status() == 201 && executions.get() == 1,
            "First request must create exactly one payment");

        // Gửi lại nguyên request: nonce vẫn cũ, reject dù cache đã có.
        Result replay = handle(first, keyring, clock,
            nonceStore, cache, executions);
        require(replay.status() == 401 && executions.get() == 1,
            "Exact nonce replay must be rejected before cache lookup");

        // Retry hợp lệ: idem key/body không đổi, timestamp/nonce/HMAC mới.
        Clock later = Clock.offset(clock, Duration.ofSeconds(1));
        Request retry = sign(
            TENANT, OLD_KEY, oldSecret, idemKey, body, later);
        Result cached = handle(retry, keyring, later,
            nonceStore, cache, executions);
        require(cached.status() == 201 && cached.fromCache() &&
                cached.body().equals(created.body()) &&
                executions.get() == 1,
            "Retry must replay original response without side effect");

        // Rotation: key mới, nonce mới nhưng idem key vẫn trỏ kết quả cũ.
        Request rotated = sign(
            TENANT, NEW_KEY, newSecret, idemKey, body, later);
        Result rotatedResult = handle(rotated, keyring, later,
            nonceStore, cache, executions);
        require(rotatedResult.status() == 201 &&
                rotatedResult.fromCache() && executions.get() == 1,
            "Rotation must not produce duplicate business action");

        // Cùng key nhưng body khác, HMAC mới hợp lệ -> 409.
        byte[] changedBody =
            "{\"orderId\":\"order-123\",\"amount\":90000}"
                .getBytes(StandardCharsets.UTF_8);
        Request changed = sign(
            TENANT, NEW_KEY, newSecret, idemKey, changedBody, later);
        Result conflict = handle(changed, keyring, later,
            nonceStore, cache, executions);
        require(conflict.status() == 409 && executions.get() == 1,
            "Same key with different fingerprint must conflict");

        // Không cho phép request tenant khác lấy cached response.
        Request otherTenant = sign("shop-02", NEW_KEY, newSecret,
            idemKey, body, later);
        Result forbidden = handle(otherTenant, keyring, later,
            nonceStore, cache, executions);
        require(forbidden.status() == 403 &&
                !forbidden.body().contains("pay-") &&
                executions.get() == 1,
            "Current authorization must precede response lookup");

        // Body giả mạo nhưng giữ HMAC cũ: reject trước khi đốt nonce.
        Request unclaimed = sign(
            TENANT, OLD_KEY, oldSecret, randomHex16(), body, clock);
        byte[] tampered = unclaimed.body().clone();
        tampered[0] ^= 1;
        Result bad = handle(withBody(unclaimed, tampered),
            keyring, clock, nonceStore, cache, executions);
        require(bad.status() == 401, "Tampered body must fail HMAC");
        Result validAfterBad = handle(unclaimed, keyring,
            clock, nonceStore, cache, executions);
        require(validAfterBad.status() == 201 &&
                executions.get() == 2,
            "Invalid MAC must not burn nonce");

        // Cùng idem key, body; 12 request HMAC/nonce khác nhau đồng thời.
        String contestedKey = randomHex16();
        ResponseCache contestedCache = new ResponseCache();
        NonceStore contestedNonces = new NonceStore();
        AtomicInteger contestedEffects = new AtomicInteger();
        ExecutorService pool = Executors.newFixedThreadPool(12);
        CountDownLatch ready = new CountDownLatch(12);
        CountDownLatch go = new CountDownLatch(1);
        try {
            java.util.List<Future<Result>> results =
                new java.util.ArrayList<>();
            for (int i = 0; i < 12; i++) {
                Request signed = sign(
                    TENANT, OLD_KEY, oldSecret, contestedKey, body, clock);
                results.add(pool.submit(() -> {
                    ready.countDown();
                    go.await();
                    return handle(signed, keyring, clock,
                        contestedNonces, contestedCache, contestedEffects);
                }));
            }
            ready.await();
            go.countDown();
            for (Future<Result> future : results) {
                int status = future.get().status();
                require(status == 201 || status == 202,
                    "Concurrent requests must be created/cached/in-progress");
            }
            require(contestedEffects.get() == 1,
                "Atomic reservation must execute side effect exactly once");
        } finally {
            go.countDown();
            pool.shutdownNow();
        }

        // Sau race, một retry mới sẽ trả lại đúng result của owner.
        Request afterRace = sign(
            TENANT, NEW_KEY, newSecret, contestedKey, body, later);
        Result stable = handle(afterRace, keyring, later,
            contestedNonces, contestedCache, contestedEffects);
        require(stable.status() == 201 && stable.fromCache() &&
                contestedEffects.get() == 1,
            "Post-concurrency retry must replay completed response");

        System.out.println(
            "PASS: HMAC, new-nonce retry, response cache, 12-way race");
    }
}
~~~

### 9.3. Vì sao `computeIfAbsent` quan trọng trong ví dụ?

Trong `ResponseCache`:

~~~java
Entry entry = cache.entries.computeIfAbsent(key, k -> {
    owner.set(true);
    return new Entry(currentFingerprint);
});
~~~

`computeIfAbsent` bảo đảm **tạo một record cho cùng CacheKey một cách nguyên tử trong một ConcurrentHashMap**. Lời gọi thắng có `owner=true` và thực thi business once; các lời gọi còn lại không được execute, chỉ kiểm tra fingerprint và xem trạng thái. Nếu record đã `COMPLETED` trả response cũ; nếu chưa thì trả `202 Processing`. Với fingerprint khác, phải trả `409` ngay cả khi request mới được ký HMAC đúng.

**Không kết luận ví dụ này là exactly-once production**: khi process chết sau `businessExecutions.incrementAndGet()` nhưng trước `entry.completed=...`, response cache mất kết quả và side effect thực tế không chắc chắn. Trong production cần DB transaction/outbox/unique constraint và xử lý UNKNOWN; `ConcurrentHashMap` chỉ phù hợp minh họa atomic reservation **trong một JVM**.

### 9.4. Vì sao không dùng HMAC signature làm fingerprint?

Trong retry, `nonce` và `timestamp` mới làm **canonical request bytes và HMAC tag thay đổi**, dù body nghiệp vụ giống hệt. Nếu cache fingerprint là SHA-256 của toàn bộ signed canonical (bao gồm nonce/timestamp), mọi retry đều gây mismatch. Hàm `fingerprint` cố tình chỉ dùng **method, raw target, audience, tenant, content type và body SHA-256**; cache key đã chứa client/operation/idempotency key. Đây là một fingerprint **của ý định nghiệp vụ**, không phải của wire request.

### 9.5. Giới hạn phải bổ sung trong production

- `Request` là record test đã parse; server thật phải lấy **raw method/path/query, header value, body bytes** từ trusted ingress và reject duplicate/security header ambiguity, CR/LF injection, content framing sai.
- `NonceStore` là một Set cục bộ **không TTL**, không chia sẻ giữa replica; cần shared atomic nonce store có retention bao phủ timestamp window, và xử lý fail-closed khi store lỗi.
- `ResponseCache` là map cục bộ **không TTL và không durable**. Nhiều pod sẽ tạo nhiều payment nếu không có authoritative reservation chung. Dùng DB/conditional write có uniqueness và transaction.
- `Result` chỉ lưu `status`, `contentType` và `body`; production phải lưu hoặc dựng đúng các response header đã whitelist; không replay `Set-Cookie`, auth token, transport metadata và credential.
- Hàm authorization cố định `TENANT` chỉ mang tính minh họa, không thay RBAC/ACL, tenant lookup, amount limit, resource permission và chính sách key/route.
- Chương trình không gọi payment provider, không thể hiện `UNKNOWN`/reconciliation; đó là phần khó bắt buộc cho external side effects.
- Với một retry đã hết TTL idempotency, server có thể coi key là mới; cần công bố window và dùng business uniqueness lâu hơn nếu nghiệp vụ yêu cầu.

## 10. Tình huống failure và cách chọn response

### 10.1. Client timeout trước khi nhận kết quả

**Kịch bản:** server xử lý xong, response mất trên mạng. Client không được coi timeout là “thao tác chưa thực hiện”. Nó retry với **cùng Idempotency-Key**, **nonce/timestamp mới**, **signed body giống cũ**. Server authn/authz lại, rồi cache hit `COMPLETED` trả kết quả gốc.

### 10.2. Hai request cùng key đến đồng thời

**Kịch bản:** client gửi lại khi request đầu còn trong hàng đợi. Atomic reservation định một owner duy nhất; bên còn lại nhận `202` (hoặc trạng thái in-progress được contract quy định) thay vì chạy payment. Sau khi owner commit, retry mới nhận original outcome.

### 10.3. Response cache đã ghi nhưng business rollback

**Lỗ hổng:** response `COMPLETED` được persist trước khi DB commit. Client retry nhận `201 Created` dù không có resource thật. **Giải pháp:** persist business state và response trong cùng transaction, hoặc chỉ publish `COMPLETED` sau khi downstream outcome được xác nhận và lưu bền vững; xử lý `UNKNOWN` khi không thể biết.

### 10.4. Business commit nhưng cache bị xóa/mất

**Lỗ hổng:** Redis evict một idempotency record trước TTL, failover mất write, hoặc cleanup sai thời hạn. Retry `K` trông như first request, có nguy cơ side effect lần hai. **Giải pháp:** durability phù hợp, business unique reference, downstream idempotency key, reconciliation; không coi một cache tạm với LRU là nguồn chân lý.

### 10.5. Client reuse key với payload mới

**Hành vi:** ký request hợp lệ với `amount=90000` và key từng dùng cho `amount=50000`. Server trả **409 key fingerprint mismatch**, không trả cached response cũ làm như số tiền mới đã xử lý, cũng không tạo giao dịch mới.

### 10.6. Key rotation hoặc quyền bị thu hồi

Nếu request retry dùng key mới vẫn active, cùng identity/tenant/operation/key/fingerprint thì có thể nhận cached response sau authentication/authorization. Nếu secret key đã revoke, hoặc client mất quyền với tenant/resource, **không tiết lộ response cũ** chỉ vì cache hit trước đó. Việc cache có sẵn **không** tạo quyền truy cập mới.

## 11. Proxy/gateway, HTTP semantics và cache poisoning

~~~mermaid
sequenceDiagram
    participant C as Client
    participant P as Proxy không tin cậy
    participant G as Trusted gateway
    participant N as Shared nonce guard
    participant I as Durable idempotency store
    participant B as Business DB
    C->>P: POST + signed Idempotency-Key, nonce, timestamp, body
    P->>G: Có thể retry/forward/rewrite
    G->>G: Strict parse + HMAC + freshness + authz
    G->>N: Atomic nonce claim
    alt Nonce duplicate
        N-->>G: Replay
        G-->>C: Reject
    else Nonce mới
        G->>I: Scope + fingerprint + atomic reserve/lookup
        alt Completed and same fingerprint
            I-->>G: Stored response
            G-->>C: Original result, no new business write
        else In progress
            I-->>G: Processing
            G-->>C: 202 or contract-defined status
        else New owner
            G->>B: Commit business + durable result
            B-->>I: Persist Completed outcome
            G-->>C: Created response
        else Fingerprint mismatch
            I-->>G: Conflict
            G-->>C: 409
        end
    end
~~~

| Tình huống | Nguy cơ | Thiết kế an toàn |
| --- | --- | --- |
| CDN cache POST response theo URL | Lộ cached response giữa client/tenant | Không dùng generic shared CDN cache làm idempotency authority; `Cache-Control: no-store` theo policy. |
| Gateway bỏ qua HMAC vì Idempotency-Key đã có | Attacker đoán key đọc response | HMAC và authz lại mỗi retry. |
| Proxy thay Idempotency-Key | Cùng signed body có thể bị xem là ý định mới | Bắt buộc ký idempotency key trong canonical. |
| Proxy biến đổi body/query | Fingerprint/cache mismatch hoặc business sai | Verify raw request tại trusted boundary, thống nhất canonical với router. |
| Gateway và backend đều chạy idempotency ở hai store khác nhau | Hai owner độc lập, duplicate execution | Xác định **một authoritative reservation** hoặc giao thức phối hợp rõ. |
| HTTP/2 chuyển sang HTTP/1.1 | Header name/order/URI representation thay đổi | Parse signed method, raw target, headers và body nhất quán. |
| Duplicate `Idempotency-Key` hoặc `X-Signature` | Các hop chọn value khác nhau | Reject duplicate trước khi gộp. |
| Cache lưu `Set-Cookie` hoặc session token | Retry có thể nhận credential không hợp lệ/sai user | Whitelist response metadata; không replay credentials tùy tiện. |
| Response được gzip ở gateway | Cached body/headers và Content-Length không nhất quán | Lưu representation rõ ràng, để HTTP layer sinh transport headers phù hợp. |
| Backend xử lý operation khác method đã ký | Response cache ràng buộc sai action | Xác định effective method/path và kiểm tra trước routing. |

**Response cache này không phải cache công khai của trình duyệt hay CDN.** Nó là **bản ghi kết quả idempotency ở phía server**, được scope theo identity và phải được bảo vệ bằng authorization như chính business resource.

## 12. TTL, retention, bảo mật dữ liệu và vận hành

### 12.1. TTL và điều kiện xóa

Ví dụ policy `Idempotency-Key` có hiệu lực **24 giờ kể từ lần reserve đầu**, nhưng đây chỉ là ví dụ, cần công bố rõ cho client. Khi hết hạn:

- Nếu business key/resource vẫn có unique constraint, request mới cùng ý định có thể tiếp tục bị ngăn duplicate theo logic nghiệp vụ.
- Nếu chỉ dựa response cache, **không thể hứa** rằng request retry sau TTL sẽ không gây tác dụng phụ lặp.
- Không xóa record `IN_PROGRESS` hoặc `UNKNOWN` chỉ vì vượt một TTL cố định mà **không reconcile**, nếu side effect trước đó vẫn có thể xảy ra.
- Cleanup cần bảo đảm không tạo race: vừa xóa entry cũ vừa nhận một retry không được tạo hai owner cho cùng một outcome cần còn unique.

### 12.2. Dung lượng và lưu trữ an toàn

Ước lượng thô nếu hệ thống có \(R\) ý định mới/giây và giữ \(T\) giây:

\[
N \approx R \times T
\]

Với 100 ý định mới/giây và 24 giờ (86.400 giây), trung bình có thể cần lưu **8.640.000 idempotency records** trong steady state, chưa kể kích thước response, index, replication, mã hóa, backup và burst.

**Không lưu full request body hoặc credentials nếu chỉ cần fingerprint/outcome ID.** Nếu phải lưu response JSON nhạy cảm, phân quyền truy cập store, mã hóa dữ liệu ở trạng thái nghỉ, giới hạn retention, kiểm tra audit và không log raw HMAC signature, shared secret, bearer token hay thông tin thanh toán nhạy cảm.

### 12.3. Monitoring và SLO

Theo dõi:

- Cache **NEW/IN_PROGRESS/COMPLETED/CONFLICT/UNKNOWN** theo operation và tenant.
- Tỉ lệ retry/new nonce, cache hit, fingerprint mismatch, retention expiry, số record stuck IN_PROGRESS.
- DB unique conflict, lock wait, transaction rollback, failover/replication lag, failed/ambiguous commit.
- Business duplicate reference, downstream idempotency hit, reconcile backlog, side-effect discrepancy.
- Nonce claim conflict/TTL, HMAC failure, authorization denial và hành vi retry sau clock skew.
- Latency p95/p99, error budget, kích thước response và quyền truy cập dữ liệu nhạy cảm.

Các metric phục vụ vận hành, **không thay** unit/integration tests về atomic reservation và durable business outcome.

## 13. Ma trận kiểm thử Response cache

Các trường hợp dưới đây dành cho hợp đồng HMAC-IDEMPOTENCY-RESPONSE-V1. Với test ở cụm thật, dùng store authoritative/DB transaction; ví dụ Java chỉ kiểm tra cơ chế trong một JVM.

| Ca kiểm thử | Thao tác | Kết quả mong đợi |
| --- | --- | --- |
| First request | HMAC đúng, nonce mới, idempotency key chưa có | Reserve một owner, thực thi một lần, lưu `COMPLETED`, trả 201. |
| Retry hợp lệ | Cùng key/fingerprint, nonce/timestamp mới, HMAC mới | Authn/authz/nonce PASS, trả cached 201 và body gốc, không chạy lần hai. |
| Replay nguyên request | Giữ nonce/timestamp/signature cũ | Nonce store reject; **không** bypass nhờ cache hit. |
| Retry sau key rotation | Cùng idempotency key và body, key ID/secret mới active | HMAC mới PASS, cùng cached outcome. |
| Key cũ revoked | Retry được ký bằng key đã thu hồi | 401/deny authn, không trả cached response. |
| Tenant không còn quyền | Retry cùng key dưới client mất quyền | 403, **không trả** cached body. |
| Cross-tenant same text key | Client/tenant khác dùng cùng key string | Cache namespace tách biệt; authz vẫn bắt buộc. |
| Cross-operation same key | `POST /payments` và `POST /refunds` | Không trộn cached response giữa operations. |
| Key reuse với body khác | Giữ key, đổi `amount` rồi ký HMAC mới | 409 fingerprint conflict, không side effect mới. |
| Key reuse với target khác | Giữ key, đổi route/query được ký | Scope/fingerprint khác theo contract; không trả kết quả sai action. |
| Body representation khác nhưng JSON tương đương | Thay whitespace/key order, giữ key | Với fingerprint raw body hash, **409** theo contract ví dụ. |
| Hai request cùng key đồng thời | Nonce khác, same fingerprint, cùng authoritative store | Một owner; request khác Processing/cached, **một** side effect. |
| Hai request cùng key/body khác đồng thời | Fingerprint A khác B | Một reservation; request còn lại nhận conflict, không xử lý payload thứ hai. |
| Owner chưa xong | Retry khi record `IN_PROGRESS` | 202/409 processing theo contract, không chạy duplicate. |
| Owner hoàn tất | Retry sau khi `COMPLETED` commit | Trả exact stable response theo policy. |
| Owner crash trước side effect | Có chứng cứ chắc chắn không commit | Cho controlled retry/takeover sau xác minh; không tự chạy do lock timeout. |
| Owner crash sau side effect | DB/external provider có thể đã commit | `UNKNOWN`, reconcile; không tự execute lại. |
| Cache completed trước business commit | Forced rollback business | Test phải phát hiện “phantom success”; sửa transaction boundary. |
| Business commit nhưng HTTP response mất | Client retry sau timeout | Replay kết quả từ durable outcome, cùng payment ID. |
| Response store failover mất record | Durable outcome không còn ở cache | Test nhận diện khả năng duplicate; business unique/downstream idempotency bảo vệ. |
| Idempotency TTL hết | Retry sau published retention | Kết quả do contract/business uniqueness quyết định; không hứa cache hit vĩnh viễn. |
| Nonce TTL hết nhưng idempotency còn | Client retry HMAC mới | Cache vẫn còn `COMPLETED` nếu trong retention; hai TTL độc lập. |
| HMAC header tampered | Sửa body/signature/key | Reject trước cache lookup; không làm lộ outcome. |
| Duplicate `Idempotency-Key` | Hai field line, case-insensitive | Reject tại trusted ingress. |
| Cached response chứa token/cookie | Retry với user/session khác | Không replay credentials; kiểm tra whitelist và authz. |
| Concurrent multi-replica | Hai pod nhận cùng key | Unique reservation trên shared store, tối đa một owner. |
| Multi-region active-active | Hai region có idempotency store độc lập | Test phát hiện double execution; cần strong coordination/routing. |
| Downstream timeout/unknown | Provider có thể đã tạo payment | Không mù quáng gọi lại; reconcile bằng stable business reference. |

### Câu hỏi tự đánh giá

1. Vì sao **nonce store** không tự ngăn hai request có nonce khác nhau nhưng cùng `Idempotency-Key` tạo hai payment?
2. Retry hợp lệ nên tạo **nonce/HMAC mới** hay gửi lại nguyên request? Server phải xử lý khác nhau thế nào?
3. Những trường nào nên và không nên xuất hiện trong **stable request fingerprint**?
4. Cùng idempotency key nhưng body khác thì nên trả cached 201, tạo payment thứ hai hay 409?
5. Cache entry `IN_PROGRESS` và `UNKNOWN` khác nhau thế nào; vì sao không tự xóa và execute lại sau timeout?
6. Vì sao một Redis atomic reserve vẫn chưa bảo đảm exactly-once khi failover mất record hoặc payment provider là dịch vụ ngoài?
7. Có nên trả response đã cache trước khi xác minh HMAC và quyền tenant của retry không? Vì sao?
8. Nếu TTL idempotency chỉ 370 giây giống nonce TTL, hệ thống có thể mắc lỗi nghiệp vụ gì khi retry sau 15 phút?
9. Những response headers nào nguy hiểm khi sao chép nguyên vào cache?
10. Vì sao key rotation không nên khiến một ý định retry tạo cache key mới?

## 14. Checklist thiết kế và triển khai

- [ ] Chốt `Idempotency-Key` format, entropy, phạm vi và **thời hạn retry** trong API contract; client tạo một key cho một ý định, reuse khi retry.
- [ ] **Ký Idempotency-Key trong canonical request**, cùng method, raw URI/query, signed headers/body digest và timestamp/nonce.
- [ ] Mỗi retry dùng **timestamp mới, nonce mới, HMAC mới**; nonces vẫn được atomic claim theo replay policy.
- [ ] Strict parse HTTP và từ chối duplicate `Idempotency-Key`/`X-Signature`/`X-Nonce`/security headers; bảo vệ trust boundary gateway/backend.
- [ ] Không đọc/trả cached response trước **HMAC verification, timestamp freshness, nonce claim và authorization hiện tại**.
- [ ] Cache key scope theo **audience, authenticated client, authorized tenant, operation và Idempotency-Key**; không scope theo nonce/timestamp/key ID tùy tiện.
- [ ] Tính fingerprint từ các **input nghiệp vụ đã xác thực**; không dùng raw HMAC signature hoặc nonce/timestamp làm fingerprint.
- [ ] Cùng key khác fingerprint → **409 conflict**; không overwrite outcome cũ và không tạo side effect thứ hai.
- [ ] Atomic reserve có unique constraint/conditional write ở authoritative store; một owner duy nhất khi các retry đến đồng thời.
- [ ] Lưu và diễn giải rõ `IN_PROGRESS`, `COMPLETED`, `UNKNOWN`; retry IN_PROGRESS không execute; UNKNOWN phải reconcile.
- [ ] Kết quả business và `COMPLETED` cần **durable atomic persistence** nếu cùng DB; external side effects cần outbox, downstream idempotency/reconciliation.
- [ ] Chỉ replay **status/body và metadata được whitelist**, không sao chép token, `Set-Cookie`, hop-by-hop headers hay credential.
- [ ] Kiểm tra lại quyền tenant/resource khi retry, kể cả khi cache đã có kết quả hợp lệ.
- [ ] Nonce TTL tính từ freshness window; idempotency TTL tính từ **SLA retry nghiệp vụ** (ví dụ 24 giờ), business uniqueness có thể dài hơn.
- [ ] Không dùng generic browser/CDN cache thay nguồn idempotency authoritative, không để proxy rewrite signed key/payload sau verify.
- [ ] Kiểm thử concurrent retry nhiều replica, different payload, key rotation, TTL/eviction, rollback, crash after side effect, ambiguous timeout, response leakage và authorization denied.

**Kết luận:** **Response cache cho idempotency** là một **bản ghi kết quả có phạm vi, fingerprint, trạng thái và độ bền phù hợp**, dùng để trả lại kết quả của **cùng một ý định nghiệp vụ** mà không thực thi side effect thêm lần nữa. Nó chỉ an toàn khi mọi retry vẫn được HMAC xác thực, timestamp/nonce kiểm tra độc lập, quyền hiện tại được xác minh và thao tác reserve/commit kết quả có tính nguyên tử. **Nonce chống phát lại cùng request; response cache/idempotency chống lặp cùng ý định nghiệp vụ.** Hai lớp bảo vệ này bổ sung nhau, không thay thế nhau.
