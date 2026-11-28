# Request identifier trong idempotency và xác thực HTTP request bằng HMAC

> **Chương:** Idempotency  
> **Đề bài:** Request identifier  
> **Module:** `SECURITY_AUTHENTICATION_HMAC_REQUEST_AUTHENTICATION` — Thiết kế xác thực HTTP request bằng HMAC với shared secret, canonical request bảo vệ method, URI, headers hoặc raw body theo hợp đồng; chống replay bằng timestamp/nonce, quản lý key rotation, kiểm thử proxy/gateway và phân biệt authentication với authorization.

## 1. Request identifier là gì, và cần phân biệt những định danh nào?

Trong HTTP, **request identifier** có thể chỉ một mã để tra log, một mã để phân biệt từng request HTTP, hoặc một mã được dùng để nhận biết **cùng một thao tác nghiệp vụ** khi client thử lại. Nếu không xác định rõ phạm vi của mã định danh, một cơ chế idempotency có thể chặn nhầm request hợp lệ hoặc cho phép ghi trùng tiền/đơn hàng.

Ví dụ: client gửi yêu cầu tạo khoản thanh toán nhưng mất kết nối trước khi nhận response.

~~~text
Lần gửi 1:
  POST /v1/payments
  X-Request-Id: request-A
  X-Idempotency-Key: payment-123
  X-Nonce: nonce-A
  X-Timestamp: t1
  X-Signature: HMAC(K, canonical-request-A)

Server đã tạo payment nhưng response bị mất.

Lần gửi 2 (retry hợp lệ):
  POST /v1/payments
  X-Request-Id: request-B
  X-Idempotency-Key: payment-123
  X-Nonce: nonce-B
  X-Timestamp: t2
  X-Signature: HMAC(K, canonical-request-B)
~~~

Lần 2 là **một HTTP attempt mới**, nhưng **cùng thao tác nghiệp vụ**. Client không nên phát lại nguyên request A vì nonce A đã được server sử dụng và bộ chống replay phải từ chối. Thay vào đó, nó tạo timestamp/nonce mới, **ký lại HMAC**, nhưng **giữ nguyên idempotency identifier** để server biết đây là retry của cùng ý định.

Trong hợp đồng minh họa của bài:

- **`X-Request-Id`:** mã nhận diện **từng HTTP attempt** cho correlation, tracing, logs; **đổi khi retry**.
- **`X-Idempotency-Key`:** mã nhận diện **một logical business operation**; **giữ nguyên khi retry đúng cùng thao tác**.
- **`X-Nonce`:** giá trị CSPRNG dùng một lần **cho từng request đã xác thực**, luôn thay trong lần ký mới.
- **`X-Timestamp`:** thời điểm Unix epoch seconds của **attempt đang gửi**, được ký và kiểm tra freshness.
- **`X-Signature`:** HMAC-SHA-256 được tính lại từ canonical request của **attempt hiện tại**.

Đây là **quy ước minh họa của bài**, không phải tên/semantics bắt buộc cho mọi HTTP API. Nhiều hệ thống dùng `X-Request-Id` chỉ để correlation; **đừng giả định chỉ cần gửi X-Request-Id thì server tự deduplicate nghiệp vụ**. Một API khác có thể chọn chính request ID làm idempotency key; khi đó phải đặc tả rằng nó ổn định **theo logical operation** chứ không phải per-attempt.

### 1.1. Một bảng phân biệt để tránh nhầm

| Định danh | Được tạo khi nào? | Retry cùng thao tác | Mục đích | Có nên ký HMAC? |
|---|---|---|---|---|
| **Attempt request ID** | Mỗi lần gửi HTTP | **Thay** | Correlation/tracing | **Có** nếu header được tin dùng để audit/trace hoặc chống sửa metadata |
| **Idempotency identifier** | Khi bắt đầu một thao tác logic | **Giữ** | Gộp retry về một kết quả nghiệp vụ | **Bắt buộc bảo vệ** nếu nó ảnh hưởng xử lý |
| **Nonce** | Mỗi request cần xác thực | **Thay** | Chặn phát lại một request đã ký | **Có**, là trường signed |
| **Timestamp** | Khi ký attempt | **Lấy lại thời gian** | Giới hạn tuổi request | **Có** |
| **Key ID** | Từ credential đang hiệu lực | Có thể đổi khi rotate | Chọn đúng shared secret | **Có**, và verify ownership |
| **Server-generated operation ID** | Khi server tạo resource | Giữ qua lifecycle | Định danh resource/business transaction | Có thể nằm trong response; không thay cho idempotency key |

**Nguyên tắc quan trọng:** *Một lần gọi lại HTTP không nhất thiết là một hành động mới, và cùng một action mới cũng không nhất thiết là cùng request ID.*

### 1.2. Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt request attempt ID, idempotency key, nonce, timestamp, signature và server resource ID.
2. Quy định rõ request identifier ổn định **trong logical operation** nhưng không ổn định giữa các HTTP attempts.
3. Đưa attempt ID và idempotency key vào canonical request để HMAC ràng buộc chính xác metadata ảnh hưởng hành vi.
4. Thiết kế idempotency lookup key dựa trên **audience, authenticated client ID và idempotency key**, không dựa trên IP hoặc key ID.
5. Phát hiện **reuse một idempotency key cho request payload/target khác** bằng operation fingerprint.
6. Tổ chức atomic reservation, trạng thái `IN_PROGRESS`, `COMPLETED`, `CONFLICT` và `IN_DOUBT`.
7. Thiết kế retry có timestamp/nonce/HMAC mới, giữ idempotency key, tránh race và duplicate side effects.
8. Viết ví dụ Java 17 có kiểm thử concurrency, key rotation, replay, authentication và authorization.
9. Giải thích vì sao in-memory idempotency cache **không bảo đảm exactly-once** và khi nào cần database transaction/outbox.
10. Kiểm thử gateway/proxy, timeout, multi-region, TTL và response caching an toàn.

## 2. Idempotency không đồng nghĩa nonce chống replay

HTTP request authentication và business idempotency bảo vệ **hai lớp khác nhau**:

~~~mermaid
flowchart TD
    A["Client tạo logical operation và idempotency key I"] --> B["Attempt 1: nonce N1, timestamp T1, requestId R1"]
    B --> C["Ký HMAC và gửi"]
    C --> D["Server: verify MAC và reserve N1"]
    D --> E["Tạo payment, lưu operation result cho I"]
    E --> F["Response bị mất trên mạng"]
    F --> G["Client retry I với nonce N2, timestamp T2, requestId R2"]
    G --> H["Ký HMAC mới"]
    H --> J["Server: verify MAC và reserve N2"]
    J --> K["Idempotency store tìm I đã hoàn tất"]
    K --> L["Trả kết quả đã ghi; KHÔNG tạo payment thứ hai"]
~~~

Nếu client **gửi lại nguyên request**, cùng nonce N1 và signature cũ, receiver phải từ chối tại **anti-replay**, không phải âm thầm coi nó là một HTTP attempt mới. Nếu client **ký lại với nonce N2**, anti-replay cho request mới vượt qua, nhưng **idempotency layer** phải ngăn side effect trùng.

| Trường hợp | HMAC | Nonce | Idempotency | Kết quả mong muốn |
|---|---|---|---|---|
| Request đầu tiên, hợp lệ | Đúng | Mới | Chưa có operation key | Thực hiện đúng một lần và ghi result |
| Sao chép nguyên request đầu | Vẫn đúng | **Đã dùng** | Có key cũ | Reject replay tại anti-replay |
| Retry với nonce mới, same key/body | Đúng với MAC mới | Mới | Operation đã `COMPLETED` | Trả result đã ghi, không thực hiện lại |
| Retry với nonce mới, same key nhưng body khác | Đúng với MAC mới | Mới | **Fingerprint khác** | Reject `CONFLICT`, không thực hiện |
| Tạo thao tác mới nhưng dùng lại key cũ | HMAC có thể đúng | Mới | Key đã có | Conflict, client phải cấp key mới cho ý định mới |
| Hai attempts cùng lúc với same key/body | Mỗi MAC đúng | Hai nonces mới | Chưa có result hoặc đang chạy | Chỉ một được phép thực hiện business; attempt khác nhận `IN_PROGRESS` hoặc result |

**Đừng chọn giữa nonce và idempotency.** Với các POST thay đổi dữ liệu, thông thường cần **cả hai**: nonce để chống phát lại request đã ký, idempotency key để gộp những **attempt mới nhưng cùng ý định**.

## 3. Một request identifier tốt phải có phạm vi và vòng đời rõ

### 3.1. Sinh ID bằng nguồn ngẫu nhiên phù hợp

Client có thể sinh **128 bit CSPRNG** rồi encode Base64URL không padding:

~~~java
SecureRandom secureRandom = new SecureRandom();
byte[] random = new byte[16];
secureRandom.nextBytes(random);
String id = Base64.getUrlEncoder()
        .withoutPadding().encodeToString(random);
// 16 bytes -> 22 ký tự Base64URL no-padding.
~~~

Dùng cùng kiểu sinh cho `X-Request-Id` và `X-Idempotency-Key`, **nhưng tạo và giữ chúng với vòng đời khác nhau**:

~~~text
Bắt đầu thao tác "tạo payment":
  I = newSecureRandomIdentifier()       // Chỉ tạo MỘT lần.

Attempt 1:
  R1 = newSecureRandomIdentifier()      // Mỗi lần gửi.
  N1 = newSecureRandomNonce()
  T1 = server-compatible Unix seconds

Attempt 2 (retry):
  R2 = newSecureRandomIdentifier()      // R2 != R1.
  N2 = newSecureRandomNonce()           // N2 != N1.
  T2 = thời gian tại lúc ký lại.
  Giữ nguyên I.
~~~

Không dùng timestamp hiện tại làm **idempotency key**: hai giao dịch trong cùng mili giây có thể vô tình trùng; cũng không dùng một bộ đếm chỉ nằm trong RAM nếu nhiều instances sinh ID độc lập mà không phối hợp. Có thể dùng UUID v4 hoặc UUID v7 khi API hỗ trợ cú pháp đó, nhưng **phải thống nhất format** và không giả định UUID v7 là 128 bit entropy thuần túy.

### 3.2. Request identifier có thể là gì?

| Loại ID | Phạm vi duy nhất | Độ ổn định | Có phù hợp cho idempotency? |
|---|---|---|---|
| Trace/span ID | Theo trace/span | Có thể thay khi retry/chia spans | Chỉ nếu contract quy định riêng; không mặc định |
| HTTP attempt ID | Mỗi lần gửi HTTP | **Không ổn định** qua retry | **Không** làm key gộp logical operation |
| Logical operation ID | Một ý định tạo/sửa tài nguyên | **Ổn định** qua retry | **Có** |
| Resource ID | Tài nguyên được server tạo | Sau khi tạo | Hữu ích cho PUT/lookup, không luôn sẵn trước POST |
| HMAC signature | Phụ thuộc timestamp/nonce/body/key | Đổi theo attempt | **Không** |
| Timestamp | Nhiều request có thể cùng giây | Không riêng biệt | **Không** |
| Nonce | Mỗi request đã ký | Đổi theo attempt | **Không** |

Request identifier dùng cho **correlation** không tự có giá trị bảo mật. Không đưa ID có dạng thông tin cá nhân (số thẻ, email, số điện thoại), secret hoặc access token vào header chỉ để phân biệt request. ID có thể xuất hiện trong log và các kênh giám sát; **nó không phải credential**.

### 3.3. Tính duy nhất phụ thuộc namespace

Một idempotency key có thể trùng tình cờ giữa hai clients. Lựa chọn scope trong bài:

~~~text
IdempotencyScope = (
    audience,                 // orders-api-production
    authenticatedClientId,    // merchant-a
    idempotencyKey             // giá trị stable per operation
)
~~~

Cùng `idempotencyKey = I` của merchant A và merchant B có thể trỏ hai operations riêng **nếu cả hai client được xác thực bằng khóa của chính mình**. Không dùng `X-Client-Id` chưa verify để tạo scope. Để chặn cross-tenant poisoning, lấy `authenticatedClientId` từ **key record/principal đáng tin sau khi HMAC đúng**.

**Không cho `keyId` vào scope** nếu muốn retry vẫn nhận diện cùng operation khi client rotate từ key cũ `VERIFY_ONLY` sang key mới `ACTIVE`. Key ID là credential selector, không phải business principal.

### 3.4. Vì sao không scope idempotency theo URL hoặc timestamp?

Nếu đưa timestamp hoặc request attempt ID vào store key, **mỗi retry tạo scope mới**, dedup không xảy ra:

~~~text
SAI:
 (client, idempotencyKey, nonce)
 (client, idempotencyKey, timestamp)
 (client, idempotencyKey, requestId)
~~~

Nếu đưa endpoint/method vào **scope** mà không có contract cụ thể, cùng idempotency key có thể bị tái sử dụng để tạo hai operations ở hai endpoints. Trong hợp đồng bài, **scope theo client/audience**, còn method, raw target, Content-Type và body được đưa vào **fingerprint kiểm tra ý định**; một key tái sử dụng cho request khác sẽ gây `CONFLICT`.

Một API khác có thể chính thức giới hạn key theo endpoint, nhưng phải ghi rõ vì sao, và việc tách scope không được vô tình cho phép cùng logical operation bị thực hiện trùng.

## 4. Xây dựng operation fingerprint để phát hiện dùng lại key sai

Idempotency store không thể chỉ kiểm tra `key đã xuất hiện` rồi trả bất kỳ response cũ nào. Nếu một client vô tình dùng cùng key `I` để gửi:

~~~http
POST /v1/payments?mode=commit
X-Idempotency-Key: I

{"amount":150000,"currency":"VND"}
~~~

và sau đó:

~~~http
POST /v1/payments?mode=commit
X-Idempotency-Key: I

{"amount":900000,"currency":"VND"}
~~~

thì **trả kết quả giao dịch đầu tiên cho lần gọi thứ hai** sẽ gây hiểu nhầm nguy hiểm. Server phải kiểm tra rằng **cùng key thực sự tương ứng cùng thao tác**, bằng cách lưu **operation fingerprint**.

### 4.1. Fingerprint hợp đồng minh họa

Trong bài này:

~~~text
businessRequestFingerprint = SHA-256(
    "idempotency-fingerprint-v1" + LF
    + method + LF
    + rawTarget + LF
    + canonicalContentType + LF
    + SHA-256(rawRequestBodyBytes).lowercaseHex
)
~~~

Các trường được nối bằng LF, không có LF cuối, mã hóa UTF-8. Method/target/Content-Type/body bytes phải được verifier và business handler hiểu nhất quán. Target ví dụ chỉ nhận `/v1/payments?mode=commit`. Bất kỳ thay đổi về raw body bytes (kể cả JSON whitespace) **đều là fingerprint mới** theo hợp đồng bài. Một API muốn coi hai cách serialize JSON tương đương phải định nghĩa **canonical JSON** và parser semantics riêng; không tự parse/re-serialize body rồi cho rằng chúng giống nhau.

**Không đưa** các trường sau vào fingerprint:

- Timestamp (`X-Timestamp`): retry được tạo ở thời điểm mới.
- Nonce (`X-Nonce`): retry bắt buộc dùng nonce mới.
- Attempt request ID (`X-Request-Id`): mỗi attempt phải khác.
- Key ID (`X-Key-Id`): client có thể rotate key.
- HMAC signature (`X-Signature`): thay theo mọi trường vừa nêu.

Idempotency key **nằm trong scope**, không cần đưa chính nó vào fingerprint. Audience/client cũng đã nằm trong scope; có thể thêm domain separator và trường nghiệp vụ khác vào fingerprint nếu cần.

### 4.2. Kết quả lookup theo scope và fingerprint

| Điều kiện | Kết quả |
|---|---|
| Scope chưa có record | **Reserve** và thực hiện một operation |
| Scope có record, fingerprint **khác** | **CONFLICT**; không thực hiện operation |
| Scope có record, cùng fingerprint, đang xử lý | **IN_PROGRESS**; không chạy duplicate |
| Scope có record, cùng fingerprint, đã hoàn thành | **REPLAYED_RESULT**; trả lại kết quả đã lưu |
| Scope có record, outcome chưa rõ do crash/timeout | **IN_DOUBT**; không tự thực hiện lại nếu có thể tạo duplicate |
| Key hết retention | Có thể không còn dedup | Cần contract TTL và domain constraints để tránh tạo trùng muộn |

Fingerprint ở đây không phải MAC bảo mật thay thế cho HMAC. Nó là **nhận diện ý định** được tính từ message đã được HMAC xác minh, nhằm ngăn key reuse với payload khác.

### 4.3. Khi nào so raw payload và khi nào so semantics?

Có ba thiết kế thường thấy:

1. **Exact bytes fingerprint:** đơn giản, deterministic, phù hợp khi client retry có thể tái gửi **cùng raw body**.
2. **Canonical media fingerprint:** parse JSON và canonical serialize theo **đặc tả rõ ràng**, hữu ích khi hai SDK serialize khác nhau nhưng cùng semantic operation. Phải xử lý duplicate keys, numbers, Unicode, content encoding và parser mismatch.
3. **Domain fingerprint:** xác định ID giao dịch, resource, amount, currency và các tham số nghiệp vụ đã được validate theo schema, rồi serialize canonical. Cần tránh loại bỏ một field có thể làm đổi side effects.

Bài dùng phương án 1 để giảm mơ hồ. Với hệ thống thực sự xử lý JSON canonical hoặc domain semantics, hãy tạo version fingerprint mới và test cross-language độc lập.

## 5. Gắn request identifier vào canonical HMAC request

Nếu server dựa vào `X-Idempotency-Key` để quyết định tạo hay trả lại kết quả, attacker không được phép thay key mà chữ ký vẫn khớp. Tương tự, nếu `X-Request-Id` được dùng cho audit chính thức, nên ràng buộc nó vào dữ liệu ký.

Hợp đồng minh họa `hmac-idempotency-v1` có **12 dòng**:

| Dòng | Giá trị | Quy tắc |
|---|---|---|
| 1 | Version | `hmac-idempotency-v1` |
| 2 | Audience | Literal `payments-api-production` |
| 3 | Method | `POST` theo request thật |
| 4 | Raw target | `/v1/payments?mode=commit` tại trust boundary |
| 5 | Content-Type | `application/json`, lowercase/trim hợp đồng |
| 6 | Client ID | `X-Client-Id`, được ký và xác minh key ownership |
| 7 | Key ID | `X-Key-Id`, được ký và tra record |
| 8 | Timestamp | `X-Timestamp` Unix epoch seconds canonical |
| 9 | Nonce | `X-Nonce`, 16 bytes Base64URL no-padding |
| 10 | Request ID | `X-Request-Id`, định danh **attempt** |
| 11 | Idempotency key | `X-Idempotency-Key`, định danh **logical operation** |
| 12 | Body digest | Lowercase hex SHA-256 của đúng raw body bytes |

Các dòng nối bằng **LF** (`\n`), **không thêm LF cuối**, rồi mã hóa UTF-8. HMAC-SHA-256 dùng secret của đúng `(clientId, keyId, audience)`; tag đầy đủ 32 byte được mã hóa Base64URL không padding (43 ký tự) vào `X-Signature`. Bản thân signature không nằm trong canonical text để tránh tự tham chiếu.

### 5.1. Ví dụ hai attempts

**Attempt đầu:**

~~~http
POST /v1/payments?mode=commit HTTP/1.1
Host: api.example.test
Content-Type: application/json
X-Client-Id: merchant-17
X-Key-Id: key-old
X-Timestamp: 1795824000
X-Nonce: b75sZVQmhTBcfnX-bNbGqw
X-Request-Id: 4Zxnz10vMUWn4FxeNCPrcA
X-Idempotency-Key: kUaB3zx0jj3OjQKffqnoBQ
X-Signature: <43-ky-tu-base64url-tag>

{"orderId":"o-123","amount":150000}
~~~

Canonical text:

~~~text
hmac-idempotency-v1
payments-api-production
POST
/v1/payments?mode=commit
application/json
merchant-17
key-old
1795824000
b75sZVQmhTBcfnX-bNbGqw
4Zxnz10vMUWn4FxeNCPrcA
kUaB3zx0jj3OjQKffqnoBQ
<sha256-hex-of-raw-body>
~~~

Dòng digest cuối và chữ ký ở header là **placeholder**; phải tính từ raw bytes thật. Unix timestamp ở đây chỉ minh họa cú pháp, không mặc nhiên nằm trong cửa sổ thời gian tại mọi thời điểm chạy.

**Retry hợp lệ của cùng operation:**

~~~text
X-Client-Id:       merchant-17           (không đổi)
X-Key-Id:          key-new               (có thể đổi vì rotation)
X-Timestamp:       t2                    (mới, cùng đơn vị seconds)
X-Nonce:           N2                    (mới)
X-Request-Id:      R2                    (mới)
X-Idempotency-Key: kUaB3zx0jj3OjQKffqnoBQ (GIỮ nguyên)
Body:              cùng raw body bytes
Signature:         HMAC mới trên canonical request retry
~~~

Nonce và signature của attempt đầu **không được dùng lại**. Idempotency key giữ nguyên; scope và fingerprint không đổi. Vì vậy server có thể trả kết quả đã lưu mà không tạo payment thứ hai.

### 5.2. Chỉ chấp nhận một giá trị của mỗi header đã ký

HTTP field names không phân biệt hoa/thường. Với các headers:

~~~http
X-Idempotency-Key: value-A
x-idempotency-key: value-B
~~~

đây là **hai occurrences cùng tên**. Hợp đồng bài yêu cầu **reject**, không chọn first/last, không nối comma-list và không trim/chuyển ký tự tùy tiện trước khi ký. Tương tự, phải kiểm soát duplicate `X-Nonce`, `X-Timestamp`, `X-Key-Id`, `X-Client-Id`, `X-Request-Id` và `X-Signature`.

Request identifier minh họa dùng **Base64URL no-padding 22 ký tự của 16 bytes CSPRNG**, cho cả attempt ID và idempotency key. Hợp đồng không cho padding, dấu cộng, slash, whitespace, Unicode hay percent-encoding trong header value. Client từ API khác dùng UUID hoặc key tùy ý cần **contract riêng**, không được silently convert.

### 5.3. Audience và authenticated client phải được tin cậy

Server lookup key record từ kho tin cậy theo `(clientId, keyId, audience)` rồi xác nhận owner và key state. Sau khi HMAC đúng, dùng **authenticated client ID từ record đó** để tạo idempotency scope.

Không dựa vào IP, `Host` chưa kiểm chứng hay `X-Verified-Client` do internet client tự gửi. Với key rotation, key ID phải được ký nhưng **không đưa vào idempotency scope** trong hợp đồng này, để retry qua key mới vẫn gộp về cùng operation.

## 6. Trạng thái idempotency và cuộc đua giữa retries

Một idempotency service tốt phải xử lý **request đến đồng thời**, không chỉ retry sau khi request đầu hoàn tất.

~~~mermaid
stateDiagram-v2
    [*] --> ABSENT
    ABSENT --> IN_PROGRESS: Atomic reserve(key, fingerprint)
    IN_PROGRESS --> COMPLETED: Business committed + result recorded
    IN_PROGRESS --> IN_DOUBT: Crash/timeout; outcome chưa xác định
    COMPLETED --> COMPLETED: Retry cùng fingerprint -> return saved result
    IN_PROGRESS --> IN_PROGRESS: Retry cùng fingerprint -> no duplicate execution
    IN_DOUBT --> IN_DOUBT: Retry -> reconciliation trước rerun
    COMPLETED --> [*]: Retention hết hạn theo policy
~~~

### 6.1. Atomic reservation là bắt buộc

Một luồng sai:

~~~text
Request A: GET idempotencyKey -> absent
Request B: GET idempotencyKey -> absent
Request A: create payment #1
Request B: create payment #2
A, B: SET idempotencyKey -> result
~~~

Dù có idempotency key, **hai side effects vẫn xảy ra** vì check-then-act không nguyên tử.

Một luồng an toàn hơn:

~~~text
Request A:
    atomic INSERT scope+fingerprint, state=IN_PROGRESS -> thắng
    thực hiện business operation, ghi result

Request B:
    atomic INSERT scope+fingerprint -> key đã tồn tại
    so fingerprint
    same fingerprint + IN_PROGRESS -> không thực hiện lại
    same fingerprint + COMPLETED   -> trả saved result
    different fingerprint          -> CONFLICT
~~~

Cơ chế insert-if-absent phải hoạt động qua **mọi verifier/backend nodes** có thể xử lý cùng authenticated client. Một `ConcurrentHashMap.putIfAbsent` chỉ chứng minh atomicity **trong một JVM**; production cần database unique constraint, transaction, hoặc dịch vụ reservation có tính nhất quán thích hợp.

### 6.2. Trạng thái HTTP phản hồi minh họa

| Tình trạng operation | Response minh họa | Ghi chú |
|---|---|---|
| Lần đầu hoàn tất | `201 Created` và body kết quả | Lưu kết quả trước khi cho retry xem |
| Retry cùng fingerprint, đã hoàn tất | `201 Created` + kết quả đã lưu; có thể kèm `Idempotency-Replayed: true` | Không tạo operation mới |
| Cùng key, khác fingerprint | `409 Conflict` | Không trả kết quả cũ cho yêu cầu khác |
| Cùng key/body nhưng operation đang xử lý | `202 Accepted` với `Retry-After` hoặc `409` theo contract | Không chạy business lần nữa |
| Outcome không rõ do lỗi trước khi ghi result | `202`/`503` theo API với trạng thái cần reconciliation | Không tự phát sinh duplicate |
| HMAC/timestamp/nonce sai | `401 Unauthorized` hoặc lỗi auth thích hợp | Không tạo idempotency record |
| Authenticated nhưng thiếu quyền resource | `403 Forbidden` | Không đưa response riêng của tenant khác cho caller |

Các status/header trên là **chính sách minh họa**, không phải chuẩn bắt buộc của mọi idempotency API. Nếu server lưu response cho retry, phải quyết định cụ thể với **lỗi 4xx/5xx**, response headers, body và version của API; không được tự cache mọi `500` khi không biết side effect đã xảy ra.

### 6.3. Không hứa “exactly once” chỉ vì có idempotency key

Điểm khó nhất là **ranh giới giữa lưu kết quả và thực hiện side effect**:

~~~text
1. Store state=IN_PROGRESS
2. Ghi tiền vào database
3. Server crash trước khi store state=COMPLETED
4. Retry đến với cùng idempotency key
~~~

Nếu store chỉ thấy `IN_PROGRESS` và “tự thử lại” mà không kiểm tra domain transaction, có thể ghi tiền lần hai. Trong production:

- Với side effect trong **cùng database**, ghi business row + idempotency record/result trong **cùng transaction**, kết hợp unique constraint; tránh cửa sổ crash giữa hai ghi.
- Với message/event xuất ra ngoài, cân nhắc **transactional outbox** hoặc command log cùng commit, consumer có dedup/idempotent handler.
- Với PSP/ngân hàng/external API, chuyển một **downstream idempotency identifier ổn định** nếu đối tác hỗ trợ, và có reconciliation khi outcome không rõ.
- Khi không bảo đảm atomicity xuyên hệ thống, dùng `IN_DOUBT` + truy vấn/tracing/reconciliation; **không tuyên bố exactly-once** một cách tuyệt đối.

### 6.4. Một request mới có thể trùng về nội dung nhưng không trùng operation

Nếu user thực sự muốn thanh toán hai lần cùng số tiền, với cùng body, **phải cấp hai idempotency keys khác nhau**. Idempotency không phải cơ chế “mọi JSON giống nhau chỉ xử lý một lần”; nó là lời hứa **trong phạm vi client/key/thời gian retention đã công bố** rằng cùng ID cho cùng intent sẽ không tạo thêm side effect.

## 7. Thời gian sống của idempotency record khác nonce TTL

Nonce chống replay một request trong cửa sổ timestamp; ví dụ:

~~~text
X-Timestamp: Unix epoch seconds
freshness window: ±300 seconds
nonce retention: >= 600 seconds + operational margin
example nonce TTL: 660 seconds
~~~

Idempotency key có mục tiêu **bao phủ khoảng thời gian client có thể retry một logical operation**. Ví dụ một API chọn **24 giờ** retention, nhưng không có thời hạn chung đúng cho mọi nghiệp vụ.

| Dữ liệu | Lifetime cần thiết | Khi hết hạn |
|---|---|---|
| Nonce record | Phủ toàn bộ acceptance interval của timestamp | Không còn phát hiện replay qua nonce; timestamp phải hết hợp lệ |
| Idempotency record/result | Phủ retry policy/latency/reconciliation của operation | Retry muộn có thể tạo operation mới nếu không có business uniqueness |
| Resource/business transaction | Theo quy định domain và lưu trữ | Không được xóa chỉ vì idempotency TTL hết |
| HTTP attempt request ID | Theo chính sách log/tracing | Chỉ ảnh hưởng correlation |
| Key record | Theo policy rotation/revocation | Phải tuân thủ key state, không phụ thuộc idempotency retention |

**Không dùng nonce TTL 660 giây cho idempotency chỉ vì cả hai đều là “dedup keys”.** Một response mất mạng vài phút sau khi giao dịch được tạo có thể khiến client retry muộn. Retention, storage, privacy và chi phí phải được thống nhất công khai.

### 7.1. Không âm thầm reset retention khi duplicate

Giả sử idempotency record hết hạn sau 24 giờ kể từ attempt đầu. Nếu mỗi retry kéo dài TTL thêm 24 giờ, một client có thể vô tình giữ record mãi, tăng storage. Nếu không gia hạn, client phải hiểu thời gian bảo đảm dedup. **Chọn một chính sách và ghi rõ**, ví dụ retention tính từ lúc **first accepted attempt**, không tự suy từ Redis TTL.

### 7.2. Vấn đề dữ liệu nhạy cảm trong cached response

Kết quả operation có thể chứa account, email, số tiền, transaction ID và thông tin riêng tư. Idempotency store cần:

- Scope theo principal/audience và ràng buộc key ownership.
- Authorization **trên mỗi attempt** trước khi trả result đã lưu, để quyền vừa bị thu hồi không mặc nhiên vẫn đọc được response cũ.
- Mã hóa lưu trữ, access controls, retention/delete policy phù hợp.
- Hạn chế log raw response, request body và shared secret.
- Ghi các header cần thiết và tránh replay một header có tính ngữ cảnh (ví dụ trace ID cũ hoặc Set-Cookie không phù hợp) một cách mù quáng.

Có thể lưu **operation ID + status** rồi tái tạo representation theo quyền hiện tại, thay vì cache toàn bộ response; điều quan trọng là **không tái thực hiện side effect** và không trả dữ liệu trái quyền.


## 8. Java 17: request identifier, HMAC và idempotency per-client

Mã nguồn sau là một chương trình **Java 17 độc lập** dùng JCA, `Clock.fixed`, `SecureRandom`, `ConcurrentHashMap` và `CountDownLatch`. Nó minh họa đầy đủ:

1. Tạo `X-Request-Id`, `X-Idempotency-Key` và nonce dưới dạng 16 bytes CSPRNG/Base64URL không padding, 22 ký tự.
2. Tạo canonical request **12 dòng** và ký HMAC-SHA-256.
3. Kiểm tra client/key ownership và trạng thái key (`ACTIVE`, `VERIFY_ONLY`, `REVOKED`), timestamp ±300 giây, Base64URL tag 32 byte và `MessageDigest.isEqual`.
4. Reserve nonce theo `(audience, authenticated client, nonce)` nguyên tử **sau MAC đúng**.
5. Kiểm tra authorization từ thông tin resource owner được lấy từ server, **trước khi tạo idempotency record**.
6. Tạo scope `(audience, authenticated client, idempotency key)`, lấy fingerprint từ method/target/Content-Type/body; không chứa key ID, timestamp, nonce, request ID.
7. Dùng `putIfAbsent` để một attempt được làm business; các attempt khác nhận `IN_PROGRESS` hoặc `REPLAYED` khi fingerprint giống nhau.
8. Khi business báo lỗi không rõ side effect, giữ `IN_DOUBT` thay vì tự động xử lý lại.
9. Test cùng client retry qua key rotation, hai client có cùng idempotency key, conflict payload, MAC giả, nonce replay và **12 threads gửi đồng thời**.

Đây là **mô hình học tập trong một JVM**. `ConcurrentHashMap` không durable, không được chia sẻ giữa replicas; code không thể đảm bảo exactly-once khi process crash. Production cần transaction/outbox hoặc tương đương như mục 6.

### 8.1. Mã nguồn `RequestIdentifierHmacDemo.java`

~~~java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.Base64;
import java.util.HexFormat;
import java.util.List;
import java.util.Locale;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Supplier;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public final class RequestIdentifierHmacDemo {
    private static final String VERSION = "hmac-idempotency-v1";
    private static final String AUDIENCE = "payments-api-production";
    private static final String ALGORITHM = "HmacSHA256";
    private static final long WINDOW_SECONDS = 300L;
    private static final long NONCE_TTL_SECONDS = 660L;

    private RequestIdentifierHmacDemo() {}

    public record Request(
            String method, String rawTarget, String contentType,
            String clientId, String keyId, String timestamp,
            String nonce, String requestId,
            String idempotencyKey, byte[] body) {
        public Request {
            if (body == null) {
                throw new IllegalArgumentException("Missing body");
            }
            body = body.clone();
        }
        @Override
        public byte[] body() {
            return body.clone();
        }
    }

    public enum KeyState { ACTIVE, VERIFY_ONLY, REVOKED }

    // Key record do server lookup từ kho đáng tin, không lấy từ body.
    public record KeyRecord(
            String clientId, String keyId, String audience,
            KeyState state, long verifyOnlyUntilSeconds,
            byte[] secret) {
        public KeyRecord {
            if (secret == null || secret.length != 32) {
                throw new IllegalArgumentException(
                        "Demo requires 32-byte secret");
            }
            secret = secret.clone();
        }
        @Override
        public byte[] secret() {
            return secret.clone();
        }
    }

    public record NonceScope(
            String audience, String authenticatedClient,
            String nonce) {}

    public record OperationScope(
            String audience, String authenticatedClient,
            String idempotencyKey) {}

    public record Result(int status, String paymentId) {}

    public enum Decision {
        CREATED, REPLAYED, IN_PROGRESS, CONFLICT, IN_DOUBT,
        AUTHN_REJECTED, REPLAY_REJECTED, AUTHZ_DENIED
    }

    public record Outcome(Decision decision, Result result) {}

    private static final class OperationEntry {
        final String fingerprint;
        volatile Result completed;
        volatile boolean inDoubt;

        OperationEntry(String fingerprint) {
            this.fingerprint = fingerprint;
        }
    }

    // DEMO ONLY: local, in-memory, không có persistence/TTL.
    public static final class IdempotencyStore {
        private final ConcurrentHashMap<OperationScope, OperationEntry>
                records = new ConcurrentHashMap<>();

        public Outcome runOnce(
                OperationScope scope, String fingerprint,
                Supplier<Result> businessAction) {
            OperationEntry proposal = new OperationEntry(fingerprint);
            OperationEntry existing =
                    records.putIfAbsent(scope, proposal);
            if (existing != null) {
                if (!existing.fingerprint.equals(fingerprint)) {
                    return new Outcome(Decision.CONFLICT, null);
                }
                if (existing.inDoubt) {
                    return new Outcome(Decision.IN_DOUBT, null);
                }
                if (existing.completed != null) {
                    return new Outcome(
                            Decision.REPLAYED, existing.completed);
                }
                return new Outcome(Decision.IN_PROGRESS, null);
            }
            try {
                // Chỉ request thắng putIfAbsent được chạy side effect.
                Result result = businessAction.get();
                proposal.completed = result; // volatile publish.
                return new Outcome(Decision.CREATED, result);
            } catch (RuntimeException uncertainOutcome) {
                // KHÔNG remove entry và tự retry: side effect có thể đã xảy ra.
                proposal.inDoubt = true;
                return new Outcome(Decision.IN_DOUBT, null);
            }
        }
    }

    // Chỉ an toàn trong cùng một JVM; production cần kho atomic chung.
    public static final class NonceStore {
        private final ConcurrentHashMap<NonceScope, Long> used =
                new ConcurrentHashMap<>();

        public boolean reserve(NonceScope scope, long now, long ttl) {
            final boolean[] first = {false};
            used.compute(scope, (key, expiration) -> {
                if (expiration != null && expiration > now) {
                    return expiration;
                }
                first[0] = true;
                return Math.addExact(now, ttl);
            });
            return first[0];
        }
    }

    public static String randomIdentifier(SecureRandom random) {
        byte[] bytes = new byte[16];
        random.nextBytes(bytes);
        return Base64.getUrlEncoder().withoutPadding()
                .encodeToString(bytes);
    }

    // Cho nonce, request ID và idempotency ID cùng dạng 16-byte random.
    private static String canonicalIdentifier(String value) {
        if (value == null
                || !value.matches("[A-Za-z0-9_-]{22}")) {
            throw new IllegalArgumentException("Invalid identifier");
        }
        final byte[] bytes;
        try {
            bytes = Base64.getUrlDecoder().decode(value);
        } catch (IllegalArgumentException ex) {
            throw new IllegalArgumentException("Invalid ID encoding", ex);
        }
        if (bytes.length != 16
                || !Base64.getUrlEncoder().withoutPadding()
                        .encodeToString(bytes).equals(value)) {
            throw new IllegalArgumentException(
                    "Non-canonical identifier");
        }
        return value;
    }

    private static String ascii(String value, int max) {
        if (value == null || value.isEmpty()
                || value.length() > max
                || value.chars().anyMatch(c -> c < 0x21 || c > 0x7E)) {
            throw new IllegalArgumentException("Bad signed field");
        }
        return value;
    }

    private static String canonicalType(String contentType) {
        if (contentType == null || contentType.length() > 128
                || contentType.chars().anyMatch(
                        c -> (c < 0x20 && c != '\t') || c > 0x7E)) {
            throw new IllegalArgumentException("Bad Content-Type");
        }
        String type = contentType.trim().toLowerCase(Locale.ROOT);
        if (!"application/json".equals(type)) {
            throw new IllegalArgumentException("Only JSON supported");
        }
        return type;
    }

    private static long parseSeconds(String value) {
        if (value == null
                || !value.matches("[1-9][0-9]{0,18}")) {
            throw new IllegalArgumentException("Not epoch seconds");
        }
        try {
            return Long.parseLong(value);
        } catch (NumberFormatException ex) {
            throw new IllegalArgumentException("Time overflow", ex);
        }
    }

    private static boolean inTimeWindow(String value, long now) {
        try {
            long delta = Math.subtractExact(parseSeconds(value), now);
            return delta >= -WINDOW_SECONDS
                    && delta <= WINDOW_SECONDS;
        } catch (IllegalArgumentException | ArithmeticException ex) {
            return false;
        }
    }

    private static String sha256Hex(byte[] body)
            throws GeneralSecurityException {
        return HexFormat.of().formatHex(
                MessageDigest.getInstance("SHA-256").digest(body));
    }

    public static byte[] canonicalBytes(Request r)
            throws GeneralSecurityException {
        if (r == null || !"POST".equals(r.method())) {
            throw new IllegalArgumentException("Only POST supported");
        }
        String target = ascii(r.rawTarget(), 2048);
        if (!"/v1/payments?mode=commit".equals(target)) {
            throw new IllegalArgumentException("Bad target");
        }
        String client = ascii(r.clientId(), 64);
        String keyId = ascii(r.keyId(), 64);
        if (!client.matches("[A-Za-z0-9_-]+")
                || !keyId.matches("[A-Za-z0-9_-]+")) {
            throw new IllegalArgumentException("Bad client/key ID");
        }
        String timestamp = ascii(r.timestamp(), 19);
        parseSeconds(timestamp);
        String nonce = canonicalIdentifier(r.nonce());
        String requestId = canonicalIdentifier(r.requestId());
        String idempotencyKey =
                canonicalIdentifier(r.idempotencyKey());

        byte[] rawBody = r.body();
        if (rawBody.length > 64 * 1024) {
            throw new IllegalArgumentException("Body too large");
        }
        String bodyHash = sha256Hex(rawBody);
        String canonical = String.join("\n",
                VERSION, AUDIENCE, r.method(), target,
                canonicalType(r.contentType()),
                client, keyId, timestamp, nonce,
                requestId, idempotencyKey, bodyHash);
        return canonical.getBytes(StandardCharsets.UTF_8);
    }

    private static byte[] hmac(byte[] secret, byte[] input)
            throws GeneralSecurityException {
        if (secret == null || secret.length != 32) {
            throw new IllegalArgumentException("Bad HMAC secret");
        }
        Mac engine = Mac.getInstance(ALGORITHM);
        engine.init(new SecretKeySpec(secret, ALGORITHM));
        return engine.doFinal(input);
    }

    public static String sign(Request request, byte[] secret)
            throws GeneralSecurityException {
        return Base64.getUrlEncoder().withoutPadding()
                .encodeToString(hmac(secret, canonicalBytes(request)));
    }

    public static byte[] decodeTagStrict(String signature) {
        if (signature == null
                || !signature.matches("[A-Za-z0-9_-]{43}")) {
            throw new IllegalArgumentException("Bad signature format");
        }
        final byte[] bytes;
        try {
            bytes = Base64.getUrlDecoder().decode(signature);
        } catch (IllegalArgumentException ex) {
            throw new IllegalArgumentException("Bad Base64URL", ex);
        }
        if (bytes.length != 32
                || !Base64.getUrlEncoder().withoutPadding()
                        .encodeToString(bytes).equals(signature)) {
            throw new IllegalArgumentException(
                    "Non-canonical/truncated HMAC tag");
        }
        return bytes;
    }

    private static boolean keyCanVerify(
            Request request, KeyRecord key, long now) {
        if (request.clientId() == null || request.keyId() == null
                || !request.clientId().equals(key.clientId())
                || !request.keyId().equals(key.keyId())
                || !AUDIENCE.equals(key.audience())) {
            return false;
        }
        if (key.state() == KeyState.REVOKED) return false;
        return key.state() == KeyState.ACTIVE
                || (key.state() == KeyState.VERIFY_ONLY
                    && now <= key.verifyOnlyUntilSeconds());
    }

    private static boolean verifyMac(
            Request request, String signature, byte[] secret)
            throws GeneralSecurityException {
        final byte[] received;
        final byte[] expected;
        try {
            received = decodeTagStrict(signature);
            expected = hmac(secret, canonicalBytes(request));
        } catch (IllegalArgumentException invalid) {
            return false;
        }
        return MessageDigest.isEqual(expected, received);
    }

    // Chỉ business intent; attempt-specific fields bị loại khỏi hash.
    public static String operationFingerprint(Request r)
            throws GeneralSecurityException {
        String bodyHash = sha256Hex(r.body());
        String text = String.join("\n",
                "idempotency-fingerprint-v1",
                r.method(), r.rawTarget(),
                canonicalType(r.contentType()), bodyHash);
        return sha256Hex(text.getBytes(StandardCharsets.UTF_8));
    }

    // HTTP adapter đã reject duplicate headers và lấy raw target/body.
    // resourceOwnerFromServer là owner tin cậy từ DB/domain layer,
    // KHÔNG phải một header do HTTP client tự đặt.
    public static Outcome handle(
            Request r, String signature, KeyRecord key,
            Clock clock, NonceStore nonceStore,
            IdempotencyStore idempotencyStore,
            String resourceOwnerFromServer,
            Supplier<Result> businessAction)
            throws GeneralSecurityException {
        if (r == null || key == null || clock == null
                || nonceStore == null || idempotencyStore == null) {
            return new Outcome(Decision.AUTHN_REJECTED, null);
        }
        long now = clock.instant().getEpochSecond();
        if (!inTimeWindow(r.timestamp(), now)
                || !keyCanVerify(r, key, now)
                || !verifyMac(r, signature, key.secret())) {
            return new Outcome(Decision.AUTHN_REJECTED, null);
        }

        // Một attempt có nonce cũ không thể vượt qua anti-replay.
        NonceScope nonceScope = new NonceScope(
                key.audience(), key.clientId(), r.nonce());
        if (!nonceStore.reserve(
                nonceScope, now, NONCE_TTL_SECONDS)) {
            return new Outcome(Decision.REPLAY_REJECTED, null);
        }

        // Authorization mỗi attempt TRƯỚC idempotency lookup/result.
        if (!key.clientId().equals(resourceOwnerFromServer)) {
            return new Outcome(Decision.AUTHZ_DENIED, null);
        }

        OperationScope operationScope = new OperationScope(
                key.audience(), key.clientId(), r.idempotencyKey());
        return idempotencyStore.runOnce(
                operationScope, operationFingerprint(r), businessAction);
    }

    private static Request request(
            String client, String keyId, String time, String nonce,
            String requestId, String idempotencyKey, byte[] body) {
        return new Request(
                "POST", "/v1/payments?mode=commit",
                "application/json", client, keyId, time, nonce,
                requestId, idempotencyKey, body);
    }

    private static void require(boolean condition, String label) {
        if (!condition) throw new AssertionError(label);
    }

    private static void concurrencyTest(
            KeyRecord key, Clock clock, SecureRandom random)
            throws Exception {
        final int attempts = 12;
        byte[] body = "{\"amount\":150000}"
                .getBytes(StandardCharsets.UTF_8);
        String idempotencyKey = randomIdentifier(random);
        NonceStore nonceStore = new NonceStore();
        IdempotencyStore operationStore = new IdempotencyStore();
        AtomicInteger sideEffects = new AtomicInteger();
        ExecutorService executor =
                Executors.newFixedThreadPool(attempts);
        CountDownLatch ready = new CountDownLatch(attempts);
        CountDownLatch start = new CountDownLatch(1);
        List<Future<Outcome>> results = new ArrayList<>();

        try {
            for (int i = 0; i < attempts; i++) {
                Request r = request(
                        key.clientId(), key.keyId(),
                        Long.toString(clock.instant().getEpochSecond()),
                        randomIdentifier(random), randomIdentifier(random),
                        idempotencyKey, body);
                String signature = sign(r, key.secret());
                results.add(executor.submit(() -> {
                    ready.countDown();
                    start.await();
                    return handle(r, signature, key, clock,
                            nonceStore, operationStore, key.clientId(),
                            () -> new Result(
                                    201, "payment-"
                                    + sideEffects.incrementAndGet()));
                }));
            }
            require(ready.await(10, TimeUnit.SECONDS),
                    "Threads must be ready");
            start.countDown();
            int created = 0;
            int reused = 0;
            for (Future<Outcome> future : results) {
                Decision kind = future.get().decision();
                if (kind == Decision.CREATED) created++;
                if (kind == Decision.REPLAYED
                        || kind == Decision.IN_PROGRESS) reused++;
            }
            require(created == 1, "Exactly one business execution");
            require(reused == attempts - 1,
                    "Every other attempt deduplicated");
            require(sideEffects.get() == 1,
                    "Business side effect must occur once");
        } finally {
            start.countDown();
            executor.shutdownNow();
        }
    }

    public static void main(String[] args) throws Exception {
        SecureRandom random = new SecureRandom();
        Clock clock = Clock.fixed(
                Instant.parse("2026-11-28T00:00:00Z"),
                ZoneOffset.UTC);
        String time = Long.toString(
                clock.instant().getEpochSecond());

        byte[] oldSecret = new byte[32];
        byte[] newSecret = new byte[32];
        byte[] otherSecret = new byte[32];
        random.nextBytes(oldSecret);
        random.nextBytes(newSecret);
        random.nextBytes(otherSecret);

        KeyRecord oldKey = new KeyRecord(
                "merchant-a", "key-old", AUDIENCE,
                KeyState.VERIFY_ONLY,
                clock.instant().getEpochSecond() + 120L,
                oldSecret);
        KeyRecord newKey = new KeyRecord(
                "merchant-a", "key-new", AUDIENCE,
                KeyState.ACTIVE, 0L, newSecret);
        KeyRecord otherClientKey = new KeyRecord(
                "merchant-b", "key-b", AUDIENCE,
                KeyState.ACTIVE, 0L, otherSecret);

        byte[] body = "{\"amount\":150000}"
                .getBytes(StandardCharsets.UTF_8);
        byte[] changedBody = "{\"amount\":900000}"
                .getBytes(StandardCharsets.UTF_8);
        String operationId = randomIdentifier(random);
        AtomicInteger sideEffects = new AtomicInteger();
        NonceStore nonces = new NonceStore();
        IdempotencyStore operations = new IdempotencyStore();
        Supplier<Result> business = () ->
                new Result(201, "payment-"
                        + sideEffects.incrementAndGet());

        // First attempt: logical operation is created.
        Request first = request("merchant-a", "key-old", time,
                randomIdentifier(random), randomIdentifier(random),
                operationId, body);
        String firstSignature = sign(first, oldSecret);
        Outcome initial = handle(
                first, firstSignature, oldKey, clock, nonces,
                operations, "merchant-a", business);
        require(initial.decision() == Decision.CREATED,
                "First attempt creates payment");

        // Exact HTTP replay: same nonce is rejected by anti-replay.
        require(handle(first, firstSignature, oldKey,
                clock, nonces, operations, "merchant-a", business)
                .decision() == Decision.REPLAY_REJECTED,
                "Exact replay blocked by nonce");

        // Same logical operation but fresh attempt, new key during rotation.
        Request retry = request("merchant-a", "key-new", time,
                randomIdentifier(random), randomIdentifier(random),
                operationId, body);
        String retrySignature = sign(retry, newSecret);
        Outcome retried = handle(retry, retrySignature,
                newKey, clock, nonces, operations,
                "merchant-a", business);
        require(retried.decision() == Decision.REPLAYED,
                "New signed attempt returns old operation result");
        require(retried.result().equals(initial.result()),
                "Identical response for the logical operation");
        require(sideEffects.get() == 1,
                "Retry must not repeat the side effect");

        // Same idempotency ID but different intent: conflict.
        Request differentIntent = request(
                "merchant-a", "key-new", time,
                randomIdentifier(random), randomIdentifier(random),
                operationId, changedBody);
        require(handle(differentIntent, sign(differentIntent, newSecret),
                newKey, clock, nonces, operations,
                "merchant-a", business)
                .decision() == Decision.CONFLICT,
                "Same key with changed payload rejected");
        require(sideEffects.get() == 1, "Conflict did not write");

        // Same idempotency key from ANOTHER authenticated client:
        // independent namespace; no cross-tenant poisoning.
        Request clientB = request("merchant-b", "key-b", time,
                randomIdentifier(random), randomIdentifier(random),
                operationId, body);
        require(handle(clientB, sign(clientB, otherSecret),
                otherClientKey, clock, nonces, operations,
                "merchant-b", business)
                .decision() == Decision.CREATED,
                "Other client gets separate namespace");
        require(sideEffects.get() == 2, "Client B created own operation");

        // HMAC false must not reserve nonce OR idempotency key.
        String freshOperation = randomIdentifier(random);
        Request protectedRequest = request(
                "merchant-a", "key-new", time,
                randomIdentifier(random), randomIdentifier(random),
                freshOperation, body);
        String goodSignature = sign(protectedRequest, newSecret);
        byte[] changedTag = decodeTagStrict(goodSignature);
        changedTag[0] ^= 1;
        String forged = Base64.getUrlEncoder().withoutPadding()
                .encodeToString(changedTag);
        require(handle(protectedRequest, forged, newKey, clock,
                nonces, operations, "merchant-a", business)
                .decision() == Decision.AUTHN_REJECTED,
                "Forged MAC rejected before either store");
        require(handle(protectedRequest, goodSignature, newKey,
                clock, nonces, operations, "merchant-a", business)
                .decision() == Decision.CREATED,
                "Real request not poisoned by forged signature");
        require(sideEffects.get() == 3, "Protected operation executed once");

        // Valid MAC but forbidden resource: no idempotency result stored.
        Request unauthorized = request(
                "merchant-a", "key-new", time,
                randomIdentifier(random), randomIdentifier(random),
                randomIdentifier(random), body);
        require(handle(unauthorized, sign(unauthorized, newSecret),
                newKey, clock, nonces, operations,
                "merchant-b", business)
                .decision() == Decision.AUTHZ_DENIED,
                "Authenticated does not imply authorized");

        // A new request ID is signed, not included in fingerprint.
        Request attemptIdTampered = request(
                retry.clientId(), retry.keyId(), retry.timestamp(),
                retry.nonce(), randomIdentifier(random),
                retry.idempotencyKey(), retry.body());
        require(!verifyMac(
                attemptIdTampered, retrySignature, newSecret),
                "Attempt ID must be cryptographically bound");
        require(operationFingerprint(first).equals(
                operationFingerprint(retry)),
                "Different nonce/requestId/keyId cannot change intent");

        // A fully signed request with a new timestamp but same
        // idempotency key also maps to the same operation.
        Request timeChanged = request(
                retry.clientId(), retry.keyId(),
                Long.toString(clock.instant().getEpochSecond() + 1),
                randomIdentifier(random), randomIdentifier(random),
                retry.idempotencyKey(), retry.body());
        require(handle(timeChanged, sign(timeChanged, newSecret),
                newKey, clock, nonces, operations,
                "merchant-a", business)
                .decision() == Decision.REPLAYED,
                "Timestamp is per-attempt, not operation identity");

        // Key is revoked even if its secret can compute the same MAC.
        KeyRecord revoked = new KeyRecord(
                "merchant-a", "key-new", AUDIENCE,
                KeyState.REVOKED, 0L, newSecret);
        Request withRevokedKey = request(
                "merchant-a", "key-new", time,
                randomIdentifier(random), randomIdentifier(random),
                randomIdentifier(random), body);
        require(handle(withRevokedKey, sign(withRevokedKey, newSecret),
                revoked, clock, nonces, operations,
                "merchant-a", business)
                .decision() == Decision.AUTHN_REJECTED,
                "Revoked key cannot authenticate");

        concurrencyTest(newKey, clock, random);
        System.out.println("PASS request identifier/idempotency HMAC tests");
    }
}
~~~

### 8.2. Biên dịch và chạy

Lưu khối Java vào `RequestIdentifierHmacDemo.java`. Dùng JDK 17 hoặc mới hơn:

~~~bash
javac RequestIdentifierHmacDemo.java
java RequestIdentifierHmacDemo
~~~

Kết quả mong đợi:

~~~text
PASS request identifier/idempotency HMAC tests
~~~

### 8.3. Bài test chứng minh điều gì?

| Test | Quan sát |
|---|---|
| Lần đầu merchant A dùng key cũ | Tạo đúng một payment và ghi operation result |
| Replay nguyên attempt | Nonce store từ chối, **không** coi là retry mới |
| Merchant A retry qua key mới | HMAC mới hợp lệ; idempotency store trả result cũ |
| Giữ idempotency key, đổi body | **CONFLICT**, không tạo payment thứ hai |
| Merchant B dùng cùng idempotency key | Tạo operation riêng vì authenticated client khác |
| Attacker gửi MAC giả cùng nonce/idempotency key | Không reserve, không gây poisoning |
| Request thật đến sau MAC giả | Vẫn có thể tạo operation |
| Authenticated client không có quyền resource | **AUTHZ_DENIED**, không tạo idempotency result |
| Thay request ID sau khi ký | HMAC không còn khớp |
| Retry timestamp mới, nonce mới, request ID mới | Vẫn nhận ra cùng logical operation |
| Key bị `REVOKED` | Reject dù MAC tính bằng secret đó đúng |
| 12 attempts cùng operation, mỗi attempt nonce khác | **Chính xác một** side effect; các request còn lại in-progress/replayed |

### 8.4. Giới hạn và trách nhiệm của triển khai production

- `IdempotencyStore` và `NonceStore` ở đây chỉ sống trong RAM của **một process**; restart mất trạng thái, multi-replica không chia sẻ atomicity. Production phải dùng durable store/transaction có unique constraints và TTL đúng policy.
- `OperationEntry.completed` là một `volatile Result` trong RAM; **không** thể commit atomically cùng transaction ghi tiền vào DB. Khi business action ném exception, demo giữ `IN_DOUBT`; việc làm rõ kết quả cần hệ thống reconciliation, không được tự retry mù.
- Mã có các key records mẫu được tạo sẵn. Ứng dụng thật phải lookup `(clientId,keyId,audience)`, kiểm tra trạng thái và deadline từ server-controlled key store, bảo vệ secret/rotation.
- `resourceOwnerFromServer` minh họa authorization; trong hệ thống thật phải lấy owner từ resource DB/domain, không nhận từ client HTTP. Kiểm tra policy action/tenant có thể phức tạp hơn so sánh chuỗi owner.
- HTTP adapter cần bảo toàn raw method/target/header/body theo signing contract và reject duplicate signed headers. Code nhận các fields đã được adapter kiểm tra, không tự giải quyết HTTP request smuggling, proxy rewrite hoặc decoded body biến đổi.
- Fingerprint so **raw body bytes**, không tự JSON canonicalize. Hai JSON texts tương đương về semantics nhưng khác whitespace sẽ `CONFLICT` theo contract bài.
- Demo không cache/serialize response headers, không có cleanup, expiry, rate limiting, tracing, error status và encryption at rest. Các lớp đó cần bổ sung theo production threat model.
- `MessageDigest.isEqual` chỉ dùng so HMAC tag; toàn bộ pipeline không được mặc nhận constant-time.
- Tests không thay cho **golden HMAC fixtures độc lập** và vector RFC 4231; ký và verify bằng cùng helper có thể cùng mắc lỗi canonicalization.


## 9. Các trường hợp bắt buộc kiểm thử request identifier

Một bộ test đầy đủ phải kiểm tra **hai tầng riêng**: HTTP attempt authentication/anti-replay và business idempotency. Chỉ test `requestId.equals(...)` không đủ.

### 9.1. Ma trận ID, nonce, timestamp và business result

| Tình huống | Request ID | Idempotency key | Nonce | HMAC | Kết quả |
|---|---|---|---|---|---|
| Lần đầu tạo payment | R1 | I1 | N1 | Hợp lệ | `CREATED`, một side effect |
| Gửi lại nguyên request | R1 | I1 | N1 | Vẫn hợp lệ | **Replay rejected** |
| Retry cùng intent | R2 | I1 | N2 | Ký lại hợp lệ | `REPLAYED`, giữ một side effect |
| Retry dùng key ID mới | R3 | I1 | N3 | Hợp lệ với secret mới | `REPLAYED` nếu cùng principal |
| Retry cùng key, payload khác | R4 | I1 | N4 | Hợp lệ | **CONFLICT** |
| Giao dịch mới, cùng body | R5 | I2 | N5 | Hợp lệ | `CREATED` lần mới |
| Client B dùng cùng I1 | RB1 | I1 | NB1 | Hợp lệ với secret B | `CREATED` riêng cho B |
| Attempt mới nhưng quên đổi nonce | R6 | I1 | N1 | HMAC ký lại | **Replay rejected** theo scope nonce |
| Idempotency key thay sau ký | R1 | I2 | N1 | Giữ tag cũ | **MAC fail** |
| Request ID thay sau ký | R2 | I1 | N2 | Giữ tag cũ | **MAC fail** theo contract |
| Timestamp mới, body cùng | R7 | I1 | N7 | HMAC mới hợp lệ | `REPLAYED` nếu còn retention |
| Client A thiếu quyền resource | R8 | I3 | N8 | Hợp lệ | **Authorization deny**, không tạo result |
| Key bị revoke | R9 | I4 | N9 | Tính được MAC cũ | **Authentication reject** |
| Operation đang xử lý | R10 | I5 | N10 | Hợp lệ | `IN_PROGRESS`, không ghi trùng |
| Side effect outcome chưa rõ | R11 | I5 | N11 | Hợp lệ | `IN_DOUBT`, không rerun mù |

Bảng dùng ký hiệu R1, I1, N1 để dễ đọc; trong request thật, chúng phải có biểu diễn canonical đúng hợp đồng và sử dụng nguồn sinh phù hợp. Tất cả attempts sau lần đầu phải được xem xét **freshness và authorization riêng**, ngay cả khi operation đã hoàn thành.

### 9.2. Negative tests về định dạng header

| Header/input | Kỳ vọng |
|---|---|
| `X-Idempotency-Key` thiếu khi endpoint yêu cầu | Reject |
| Hai `X-Idempotency-Key` | Reject, không lấy first/last |
| `X-Idempotency-Key: A,B` | Reject; comma-list không hợp lệ |
| Idempotency key trùng với một nonce hợp lệ | Không tự gây lỗi do giá trị tình cờ trùng; **vai trò khác nhau** |
| Idempotency key chứa `/`, `+`, `=` | Reject vì ví dụ dùng Base64URL no-padding |
| Key có percent escapes `%2F` trong header | Reject, không tự URL-decode |
| Key chứa khoảng trắng, newline, NUL | Reject |
| 22 ký tự đúng alphabet nhưng pad bits không canonical | Reject qua decode/encode round-trip |
| ID quá ngắn/quá dài | Reject |
| Signature Base64URL sai length hoặc truncated MAC | Reject |
| `X-Timestamp` milliseconds khi contract yêu cầu seconds | Fail freshness, dù tag được tính đúng trên chuỗi đó |
| Duplicate `X-Request-Id` | Reject theo signed-header policy |
| Không có nonce hoặc nonce đã dùng | Authentication reject |
| JSON/body khác raw bytes | Operation fingerprint đổi và HMAC phải được ký lại |

**Không suy từ format mà một ID chắc chắn ngẫu nhiên.** Server kiểm được byte length/canonical encoding và uniqueness đã ghi nhận, còn entropy phải được bảo đảm ở phía client library/generator.

### 9.3. Unit tests cho fingerprint

Cho các requests có cùng `(audience, authenticatedClient, idempotencyKey)`:

~~~text
Request A:
  POST /v1/payments?mode=commit
  Content-Type: application/json
  body: {"amount":150000}
  timestamp=t1, nonce=n1, requestId=r1, keyId=k1

Request B:
  POST /v1/payments?mode=commit
  Content-Type: application/json
  body: {"amount":150000}
  timestamp=t2, nonce=n2, requestId=r2, keyId=k2

Request C:
  POST /v1/payments?mode=commit
  Content-Type: application/json
  body: {"amount":900000}
  timestamp=t3, nonce=n3, requestId=r3, keyId=k2
~~~

Theo contract:

~~~text
fingerprint(A) == fingerprint(B)
fingerprint(A) != fingerprint(C)   (với xác suất áp đảo)
~~~

Cả A, B và C đều có thể có **HMAC hợp lệ của riêng chúng**, vì sender thật có secret. Vì thế **HMAC đúng không loại bỏ nhu cầu so fingerprint**. HMAC trả lời “request này có được ký đúng không?”, fingerprint trả lời “request này có cùng ý định với operation key trước đó không?”.

Nếu server cần kiểm tra **method khác**, **raw target khác** hoặc Content-Type khác, dùng một route grammar/dispatcher thật thay vì chỉ hai request như ví dụ Java. Những thành phần ảnh hưởng side effect đều phải được ký và đưa vào fingerprint theo contract.

### 9.4. Unit tests cho state machine

| Stored state | Incoming fingerprint | Kỳ vọng |
|---|---|---|
| Absent | F1 | Atomic reserve; chỉ một winner |
| `IN_PROGRESS` | F1 | Không thực hiện lại; trả in-progress |
| `IN_PROGRESS` | F2 | `CONFLICT` |
| `COMPLETED` | F1 | Trả kết quả cũ, không gọi business |
| `COMPLETED` | F2 | `CONFLICT` |
| `IN_DOUBT` | F1 | Không tự rerun; reconciliation |
| `IN_DOUBT` | F2 | `CONFLICT` |
| Expired | F1 | Chính sách retention/business uniqueness quyết định; có nguy cơ duplicate |
| Denied authorization | F1 | Không trả cache result trái quyền và không tạo operation mới |

Kiểm tra thứ tự **authorization trước khi dùng saved response**: một response chứa thông tin tài chính không được trả cho principal không còn quyền chỉ vì họ đoán được idempotency key.

### 9.5. Concurrency và crash fault injection

Chạy ít nhất những kịch bản sau:

1. **12–100 HTTP attempts đồng thời**, mỗi attempt có request ID/nonce/HMAC riêng nhưng cùng client/idempotency key/body; kết quả tối đa **một** side effect.
2. Hai backend khác nhau cùng xử lý một idempotency scope; database unique constraint/atomic reservation phải chọn một winner.
3. Retry đến đúng lúc winner vừa commit nhưng chưa gửi response; retry phải lấy được result đã commit.
4. Process crash **trước** business transaction: policy có thể cho operation tiếp tục sau recovery.
5. Process crash **sau khi side effect commit nhưng trước khi idempotency result commit**: hệ thống không được tự tạo giao dịch thứ hai. Đây là ca quan trọng nhất để quyết định dùng chung transaction/outbox.
6. Network timeout tới PSP nhưng PSP có thể đã ghi tiền: đánh dấu `IN_DOUBT` và query/reconcile bằng downstream operation ID.
7. Idempotency store failover mất một record vừa tạo; kiểm tra durability và recovery.
8. Idempotency record hết TTL nhưng retry đến sau đó; cần làm rõ bảo đảm của API và business uniqueness.
9. Client A gửi idempotency key I, client B gửi I đồng thời; các namespace không được đè lên nhau.
10. Đang rotate credential: request key cũ `VERIFY_ONLY` và key mới `ACTIVE` với cùng idempotency key phải gộp theo client, không tạo hai operations.
11. Nonce store không khả dụng: nếu anti-replay là bắt buộc, **fail closed**, không bỏ qua để phục vụ retry.
12. Concurrent duplicate **khác body**: một operation được tạo, các bản khác `CONFLICT`, không phải ghi tiền theo request đến sau.

### 9.6. Golden fixtures và cross-language

Bộ golden fixtures cần chứa dữ liệu có expected **tính độc lập**:

~~~text
contractVersion=hmac-idempotency-v1
audience=payments-api-production
method=POST
rawTarget=/v1/payments?mode=commit
contentType=application/json
clientId=merchant-test
keyId=test-k1
timestamp=<canonical-Unix-epoch-seconds>
nonce=<canonical-22-char-Base64URL>
requestId=<canonical-22-char-Base64URL>
idempotencyKey=<canonical-22-char-Base64URL>
rawBodyBase64=<exact-raw-bytes>
secretHex=<test-only-32-byte-key>
expectedCanonicalRequest=<12-lines-LF-no-final-newline>
expectedHmacHex=<64-lowercase-hex>
expectedSignatureBase64Url=<43-chars-no-padding>
expectedBusinessFingerprint=<SHA256-of-versioned-method-target-type-body-hash>
~~~

Java, Go, Node.js và Python SDK phải tạo **cùng canonical bytes, HMAC, Base64URL và fingerprint** khi dùng cùng fixture. Dùng test vector **RFC 4231** để kiểm chứng HMAC-SHA-256 độc lập; chỉ tự sign/verify bằng cùng helper có thể làm hai lỗi giống nhau tự che nhau.

## 10. Gateway/proxy và HTTP request identifier

Một gateway có thể thêm `X-Request-Id` để trace, nhưng không nên tự thay `X-Idempotency-Key` hoặc metadata đã ký.

~~~mermaid
sequenceDiagram
    participant C as Client SDK
    participant G as API Gateway
    participant V as HMAC Verifier
    participant N as Nonce Store
    participant I as Idempotency Store
    participant B as Business/DB
    C->>C: Logical key I, attempt ID R1, nonce N1
    C->>G: POST + signed R1/I/N1
    G->>V: Preserved signed fields và raw content
    V->>V: Validate key state/time/HMAC
    V->>N: Reserve nonce N1 theo authenticated client
    N-->>V: OK
    V->>V: Authorization
    V->>I: Atomic reserve I + fingerprint
    I-->>V: CREATED / REPLAYED / CONFLICT / IN_PROGRESS
    V->>B: Chỉ winner được chạy side effect
    B-->>V: Committed result
    V-->>C: Response (có thể bị mất trên mạng)
    C->>C: Retry cùng I, tạo R2/N2/timestamp/MAC mới
    C->>G: POST + signed R2/I/N2
    G->>V: Preserved signed fields
    V->>I: Lookup same client/I/fingerprint
    I-->>V: REPLAYED result
    V-->>C: Trả result cũ, không ghi trùng
~~~

### 10.1. Những biến đổi cần kiểm thử

| Hành vi ở gateway/framework | Rủi ro | Cách xử lý |
|---|---|---|
| Gateway sinh `X-Request-Id` mới cho một signed request | MAC fail nếu field nằm trong canonical request | Client tạo và ký, hoặc dùng **proxy-only trace ID riêng** không thay signed field |
| Gateway xóa hoặc sinh `X-Idempotency-Key` | Mất business identity, có thể tạo duplicate | Reject thiếu key; không tự sinh key thay client |
| Retry tự động một POST nhưng giữ nonce/signature cũ | Anti-replay phải reject | Không retry âm thầm; SDK tạo attempt mới, ký lại |
| Proxy thay JSON whitespace/body | Raw-body fingerprint và MAC đổi | Verify trước rewrite; giữ raw bytes theo contract |
| Proxy reorder hoặc decode query | Method/target semantics lệch | Cố định canonical target; integration test |
| Hai `X-Idempotency-Key` bị gộp | Parser first/last khác nhau | Reject duplicate tại edge |
| Proxy thay `X-Key-Id` trong rotation | Lookup sai hoặc HMAC mismatch | Chỉ client chọn credential, signed key ID |
| Gateway dùng IP thay authenticated client ID | Cross-client collision hoặc scope đổi theo NAT | Scope theo principal sau verify |
| Gateway có cache trước auth | Có thể bỏ qua freshness/authorization | Không dùng cache để bypass verifier và policy |
| Gateway gắn `X-Verified-Client` do client cung cấp | Giả principal và nhầm namespace | Strip untrusted headers, xác thực kênh nội bộ |
| Hai regions có idempotency DB eventual consistency | Cả hai có thể reserve cùng key | Dùng authoritative/strongly consistent reservation |
| Timeout giữa gateway/backend | Backend có thể đã commit | Retry theo cùng idempotency key; reconciliation nếu không rõ |

### 10.2. Client retry phải có trách nhiệm rõ

Một retry policy phù hợp có thể:

~~~text
1. Tạo idempotency key I trước attempt đầu.
2. Lưu I trong context của logical operation.
3. Gửi attempt R1/N1/T1/HMAC1.
4. Nếu nhận result cuối cùng: kết thúc.
5. Nếu timeout hoặc lỗi retryable theo policy:
   a. Chờ backoff + jitter với giới hạn tổng thời gian.
   b. Giữ I và raw body/intent.
   c. Tạo attempt ID R2, nonce N2, timestamp T2.
   d. Ký lại HMAC2 theo đúng key đang hiệu lực.
   e. Gửi retry.
6. Nếu server báo IN_PROGRESS:
   tuân Retry-After hoặc poll theo API, không tạo side effect riêng.
7. Nếu CONFLICT:
   Dừng; lỗi reuse key/intent phải được điều tra.
8. Nếu IN_DOUBT:
   Query reconciliation/status theo operation ID,
   không tự gửi payment mới với key khác để "vượt qua".
~~~

Không được retry **mọi HTTP 500/timeout vô hạn**: request đầu có thể đã thực thi thành công. Backoff, retry budget, deadlines và idempotency retention phải phù hợp với nghiệp vụ/đối tác.

## 11. Authentication, authorization và trách nhiệm quản trị ID

### 11.1. Authentication không cấp quyền trên payment

Merchant A ký request đúng:

~~~http
POST /v1/payments?mode=commit HTTP/1.1
X-Client-Id: merchant-a
X-Key-Id: key-a
X-Timestamp: <valid-seconds>
X-Nonce: <fresh-nonce>
X-Request-Id: <new-attempt-id>
X-Idempotency-Key: <stable-operation-id>
X-Signature: <valid-hmac>
~~~

Body lại yêu cầu thanh toán bằng một tài khoản thuộc merchant B:

~~~text
Authentication:
  client = merchant-a
  timestamp = valid
  nonce = fresh
  HMAC = valid
  request/operation identifiers = canonical

Authorization:
  action = payments:create
  funding account owner = merchant-b
  principal = merchant-a
  decision = DENY
~~~

Không gọi business create, không trả cache result nhạy cảm từ operation cũ của client B. `X-Idempotency-Key` chỉ là **ID do client cấp**, không phải bằng chứng sở hữu resource. Idempotency store phải tách namespace bằng **principal đã xác thực**.

### 11.2. Có thể dùng ID làm access token không?

Không. Request ID, idempotency key và nonce **không phải bearer tokens**. Đúng là idempotency key khó đoán giúp giảm accidental collision và enumeration, nhưng **không được dựa vào việc khó đoán để bỏ HMAC hoặc authorization**. Client có thể copy một idempotency key từ log; điều đó không cho họ quyền lấy payment response của tenant khác.

Đồng thời, nếu một idempotency key xuất hiện trong log, trace, support ticket hoặc database, phải áp retention/access control theo chính sách vì nó giúp liên kết hành vi và có thể chứa metadata nhạy cảm nếu generator không tốt.

### 11.3. Nếu client bị lộ secret thì idempotency vẫn hữu ích không?

Attacker có secret thật có thể ký một request mới với nonce và idempotency key mới. Idempotency **không chặn** kẻ đang sở hữu credential hợp lệ tạo một thao tác mới; cần revoke/rotate key, quota, authorization, velocity limits và giám sát hành vi. Nó chỉ bảo đảm những attempts **được gắn cùng logical key** không nhân side effects theo chính sách.

### 11.4. Kết quả idempotency và kiểm soát quyền thay đổi theo thời gian

Giả sử A tạo payment trong lúc có quyền, nhưng quyền bị thu hồi trước khi A retry. Server không được “vì cùng idempotency key nên trả lại toàn bộ dữ liệu” mà bỏ authz. Có thể chọn trả một status tối thiểu, hoặc yêu cầu authorization lại rồi trả result phù hợp; quyết định này thuộc API/security policy. **Không dùng idempotency cache làm đường tắt bỏ authentication/authorization.**

## 12. Những sai lầm thường gặp

1. **Dùng `X-Request-Id` per-attempt làm idempotency key:** mỗi retry là một key mới nên tạo duplicate.
2. **Dùng nonce làm idempotency key:** retry bắt buộc nonce mới, dedup không xảy ra.
3. **Retry bằng nguyên timestamp/nonce/signature:** anti-replay phải reject, dù HMAC đúng.
4. **Không đưa idempotency key vào canonical HMAC:** client/proxy/attacker có thể thay routing của dedup ngoài message đã ký.
5. **Dùng raw `X-Client-Id` làm namespace trước khi verify:** nonce/idempotency poisoning qua tenant.
6. **Đưa key ID vào idempotency scope:** rotate credentials vô tình reset dedup.
7. **Không so fingerprint:** reuse key với amount khác có thể trả sai result hoặc thực hiện sai intent.
8. **Tạo fingerprint gồm timestamp/nonce/requestId:** retry đúng intent cũng conflict.
9. **GET rồi INSERT tách biệt:** hai requests đồng thời cùng thực hiện side effect.
10. **Nhầm cache RAM với durable transaction:** crash mất record vẫn tạo duplicate.
11. **Auto-retry khi outcome chưa rõ:** PSP có thể đã thu tiền nhưng server ghi duplicate.
12. **Dùng idempotency TTL giống nonce TTL:** không bảo vệ retries muộn hơn freshness window.
13. **Không re-authorize khi trả cached result:** lộ thông tin sau khi quyền bị thu hồi.
14. **Tin `X-Verified-Client` ngoài trust boundary:** giả danh principal và lấy result sai namespace.
15. **Đặt dữ liệu cá nhân vào ID:** request identifiers xuất hiện trong logs và traces.
16. **Cho rằng idempotency nghĩa là exactly-once toàn hệ thống:** thiếu transaction/outbox/reconciliation.
17. **Không giới hạn rate/ID cardinality:** attacker có credential thật có thể làm đầy store.
18. **Không phân biệt operation mới và retry:** cùng body nhưng khác ý định phải có key mới.

## 13. Bài tập thực hành

**Bài 1 — Phân biệt định danh:** Hãy phân loại `X-Request-Id`, `X-Idempotency-Key`, `X-Nonce`, `X-Timestamp`, `X-Signature` và payment ID. Trường nào được giữ, trường nào thay khi retry cùng operation?

**Bài 2 — HTTP timeout:** Client POST tạo payment, server đã commit nhưng response thất lạc. Viết hai requests (attempt đầu và retry) có timestamp/nonce/signature mới nhưng cùng idempotency key. Những lớp nào kiểm tra trước khi trả cached result?

**Bài 3 — Scope theo client:** Merchant A và merchant B dùng cùng idempotency key. Nếu key store map theo `(client, key)` thì kết quả thế nào? Điều gì xảy ra nếu map chỉ theo key?

**Bài 4 — Rotation:** Merchant A retry qua `key-old` và `key-new`. Vì sao đưa key ID vào idempotency scope có thể tạo duplicate, trong khi key ID vẫn phải là signed field?

**Bài 5 — Fingerprint:** Hai attempts cùng idempotency key/body nhưng khác nonce, timestamp và request ID. Vì sao fingerprint phải bằng nhau? Nếu amount trong body đổi thì server phải làm gì?

**Bài 6 — JSON bytes:** Hai JSON có cùng ý nghĩa nghiệp vụ nhưng khác whitespace. Trong contract raw-byte fingerprint, chúng được coi là giống nhau không? Hãy đề xuất một hợp đồng canonical JSON khác nếu muốn chúng tương đương, đồng thời phân tích duplicate JSON keys.

**Bài 7 — Race:** Hai backend cùng thấy idempotency key chưa có, rồi cùng tạo payment. Chỉ ra bước thiếu atomicity và đề xuất database unique constraint/transaction.

**Bài 8 — Crash after commit:** Database đã ghi payment, idempotency result chưa lưu thì process crash. Vì sao retry tự động có thể tạo payment lần hai? Nêu phương án transaction/outbox/reconciliation.

**Bài 9 — Nonce vs idempotency:** Vì sao retry với nonce cũ phải bị chặn, còn retry với nonce mới và idempotency key cũ có thể được trả lại result?

**Bài 10 — Gateway:** Gateway tự thay `X-Request-Id` để trace nhưng header này nằm trong canonical HMAC. Chữ ký có còn hợp lệ không? Nên dùng trace ID riêng tại proxy thế nào?

**Bài 11 — Authorization:** Merchant A có HMAC hợp lệ và idempotency key trùng với một payment của B. Vì sao server không được trả dữ liệu payment B? Cần scope và kiểm quyền gì?

**Bài 12 — TTL:** Nonce TTL là 660 giây nhưng idempotency retry policy là 24 giờ. Nếu đặt TTL operation cũng 660 giây, tình huống nào dẫn đến duplicate?

**Bài 13 — Concurrency:** Thực thi 100 attempts cùng logical operation với 100 nonces khác nhau qua nhiều nodes. Chỉ số nào chứng minh dedup đúng, và vì sao một unit test `ConcurrentHashMap` là chưa đủ?

**Bài 14 — In doubt:** Một PSP timeout sau khi request đã gửi. Làm sao xác định khoản tiền đã thu hay chưa mà không tạo payment ID mới để thử lại mù?

## 14. Checklist triển khai

1. **Xác định semantics:** per-attempt request ID khác stable logical operation idempotency key.
2. **Sinh ID:** 128-bit CSPRNG/UUID hợp đồng cho key; không dùng timestamp, email hoặc HMAC tag làm operation identifier.
3. **Khả năng retry:** giữ một idempotency key cho cùng ý định, tạo request ID, timestamp, nonce và HMAC mới mỗi attempt.
4. **Ký đúng fields:** method, raw URI/query, Content-Type, client/key IDs, timestamp, nonce, attempt request ID, idempotency key và raw body digest theo canonical contract.
5. **Validate strict:** ASCII/Base64URL format, tag 32 byte, duplicate signed headers, payload size và HTTP framing.
6. **Key lookup:** authenticated client và audience từ key record đáng tin; kiểm ACTIVE/VERIFY_ONLY/REVOKED.
7. **Nonce:** reserve nguyên tử sau MAC đúng, namespace per authenticated client/audience, TTL phủ timestamp window, fail closed.
8. **Operation scope:** `(audience, authenticatedClientId, idempotencyKey)`, không chứa nonce/timestamp/requestId/keyId theo contract bài.
9. **Fingerprint:** method/target/type/raw body hash; mismatch ⇒ conflict, không tạo side effect.
10. **Authorization:** kiểm tra principal/action/resource ở mỗi attempt trước khi trả cached result hoặc làm business.
11. **Atomicity:** insert-if-absent trong durable store, transaction cùng side effect khi có thể; xử lý `IN_PROGRESS/COMPLETED/IN_DOUBT` rõ ràng.
12. **Retention:** idempotency TTL theo retry/domain window, khác nonce TTL; có policy cho retries sau khi record hết hạn.
13. **External side effects:** outbox/downstream idempotency/reconciliation cho PSP, queue hoặc hệ thống không cùng database.
14. **Gateway:** không rewrite signed IDs/body/target trước HMAC; chỉ tin principal metadata qua trusted proxy/connection.
15. **Response:** kết quả lưu phải nhất quán và bảo mật; không cache response nhạy cảm mà bỏ authorization.
16. **Quan sát:** log attempt ID, operation ID/hashed key và trạng thái có kiểm soát, không log secret/HMAC expected/raw body nhạy cảm.
17. **Kiểm thử:** tamper, replay, retry, conflict, rotation, crash injection, concurrency multi-node, multi-region, TTL và authz.

## 15. Kết luận

**Request identifier** chỉ có ý nghĩa đúng khi xác định rõ **nó nhận diện một HTTP attempt hay một logical business operation**. Trong hợp đồng bài học:

- `X-Request-Id` thay đổi cho từng attempt và giúp correlation.
- `X-Idempotency-Key` ổn định cho toàn bộ retries của một thao tác logic.
- `X-Nonce`, `X-Timestamp` và `X-Signature` phải được tạo/kiểm tra lại cho mỗi attempt để đáp ứng HMAC authentication và chống replay.
- Idempotency store lookup theo **(audience, authenticated client, idempotency key)**; fingerprint ràng buộc intent và phát hiện thay payload.
- **Atomic reservation, durable result, transaction/outbox và reconciliation** bảo vệ side effects, trong khi authorization quyết định client có quyền trên resource thật hay không.

HMAC và nonce ngăn request bị sửa/được phát lại, nhưng không tự giải quyết timeout/retry hoặc exactly-once business. Ngược lại, idempotency không thay thế HMAC, kiểm soát secret/key rotation, timestamp/nonce, gateway integrity hay phân quyền. Thiết kế đúng là **ghép các lớp với phạm vi ID và ranh giới giao dịch rõ ràng**.

**Tài liệu tham khảo:**

- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110): method semantics và khái niệm idempotent HTTP methods; không đồng nghĩa tự dedup POST.
- [RFC 9112 — HTTP/1.1](https://www.rfc-editor.org/rfc/rfc9112): message framing, header parsing và intermediaries.
- [RFC 9113 — HTTP/2](https://www.rfc-editor.org/rfc/rfc9113): HTTP/2 pseudo-headers, `:method` và `:path`.
- [RFC 2104 — HMAC](https://www.rfc-editor.org/rfc/rfc2104): keyed-hash authentication.
- [RFC 4231 — HMAC-SHA-256 Test Vectors](https://www.rfc-editor.org/rfc/rfc4231): kiểm chứng HMAC độc lập.
- [RFC 4648 — Base-N Encodings](https://www.rfc-editor.org/rfc/rfc4648): Base64URL, padding và canonical encoding.
- [RFC 9421 — HTTP Message Signatures](https://www.rfc-editor.org/rfc/rfc9421): tham khảo cơ chế ký các thành phần HTTP; `hmac-idempotency-v1` là **hợp đồng học tập riêng**, không mặc nhiên tương thích RFC 9421.
- [Java SE 17 — SecureRandom](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/SecureRandom.html): sinh identifiers/nonce bằng CSPRNG.
- [Java SE 17 — Mac](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/Mac.html): HMAC-SHA-256 trong JCA.
- [Java SE 17 — MessageDigest](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/MessageDigest.html): SHA-256 và `isEqual`.
- [Java SE 17 — ConcurrentHashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html): `putIfAbsent`/`compute` chỉ tạo atomicity trong JVM, không thay database transaction.
- [Java SE 17 — Clock](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Clock.html): fixed time tests và epoch seconds.





