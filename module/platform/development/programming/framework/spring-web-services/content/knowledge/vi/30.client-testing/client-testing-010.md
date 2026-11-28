# Kiểm thử logic thử lại và bảo đảm không lặp tác dụng nghiệp vụ

## 1. Vì sao SOAP client cần retry có kiểm soát?

Trong tích hợp SOAP doanh nghiệp, một request có thể đã đến server và thực hiện xong nghiệp vụ nhưng client vẫn không nhận được response. Ví dụ `CreateShipment` đã ghi vận đơn vào database, server gửi SOAP response nhưng kết nối bị reset trước khi response tới client. Client nhìn thấy timeout và không biết lệnh đã commit hay chưa.

Nếu client gửi lại request như một lệnh mới, hệ thống có thể tạo **hai vận đơn**, gửi hai email, trừ tiền hai lần hoặc phát hành hai chứng từ. Retry chỉ giải quyết lỗi truyền thông; nó không tự bảo đảm tác dụng nghiệp vụ chỉ xảy ra một lần.

Module **SPRING_WEB_SERVICES** học phát triển dịch vụ SOAP theo hướng **contract-first**: thiết kế XSD/WSDL, JAXB/OXM, xây dựng endpoint và SOAP client, xử lý SOAP Fault, interceptor, XML security, WS-Security, chứng chỉ và kiểm thử tương thích hệ thống doanh nghiệp. Bài thuộc chương **Kiểm thử máy khách**, tập trung vào cách thiết kế và kiểm thử retry để SOAP client phục hồi được khi lỗi tạm thời mà không lặp side effects.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt retry ở tầng transport với retry một business operation.
2. Nhận diện trạng thái **unknown outcome** khi timeout xảy ra sau khi server có thể đã commit.
3. Phân loại lỗi có thể retry và lỗi không được retry từ HTTP, SOAP Fault và exception.
4. Thiết kế idempotency key ổn định cho một business intent.
5. Bảo vệ server bằng unique constraint, transaction và lưu kết quả của request đã xử lý.
6. Xử lý cùng key nhưng payload khác, retry đồng thời và duplicate đến từ nhiều client instances.
7. Dùng exponential backoff, jitter, retry budget và deadline.
8. Kiểm thử bằng SOAP endpoint/client thật hoặc test transport có thể mô phỏng timeout, reset và duplicate.
9. Phân biệt idempotency, deduplication, exactly-once delivery và at-least-once delivery.
10. Xây dựng observability để theo dõi retries, duplicate requests và kết quả không chắc chắn.

## 2. Một request SOAP có thể thành công dù client báo lỗi

Giả sử client gửi:

~~~text
CreateShipment(requestId=REQ-1042, account=ACCT-A, order=ORD-55)
~~~

Server thực hiện:

1. Nhận SOAP Envelope.
2. Xác thực HTTP/TLS/WS-Security.
3. Validate XSD và quyền của caller.
4. Tạo bản ghi shipment trong transaction.
5. Commit transaction.
6. Serialize SOAP response.
7. Gửi response qua HTTP.

Nếu network đứt ở bước 6 hoặc 7, client có thể nhận `SocketTimeoutException`, connection reset hoặc lỗi đọc response. Nhưng database đã commit ở bước 5.

~~~mermaid
sequenceDiagram
    participant C as SOAP Client
    participant S as SOAP Service
    participant DB as Database
    C->>S: CreateShipment(requestId=REQ-1042)
    S->>DB: INSERT shipment
    DB-->>S: COMMIT
    S--xC: Response lost / timeout
    Note over C: Client không biết request đã commit
    C->>S: Retry CreateShipment(requestId=REQ-1042)
    S->>DB: Lookup idempotency key
    DB-->>S: Existing result
    S-->>C: Return original outcome
~~~

Đây là lý do phải thiết kế **idempotency tại server** trước khi bật retry cho operation có side effects.

### 2.1. Unknown outcome khác failure

| Kết quả phía client | Điều có thể đã xảy ra phía server | Cách xử lý |
| --- | --- | --- |
| DNS lookup thất bại trước khi kết nối | Request thường chưa tới endpoint | Có thể retry nếu lỗi tạm thời |
| TCP connect timeout | Chưa rõ request đã được gửi hay chưa tùy transport/proxy | Phân loại theo phase; với command, giữ nguyên idempotency key |
| Timeout khi ghi request | Server có thể nhận một phần hoặc toàn bộ | Outcome chưa chắc chắn |
| Timeout khi đọc response | Server có thể đã commit | Outcome chưa chắc chắn, không tạo key mới |
| SOAP Sender/Client Fault | Request không hợp lệ hoặc caller không được phép | Thường không retry |
| SOAP Receiver/Server Fault | Server lỗi; có thể trước hoặc sau side effect | Chỉ retry theo fault contract và idempotency |
| HTTP 503 | Service tạm không sẵn sàng, nhưng intermediary có thể đã xử lý một phần | Retry có giới hạn và cùng key |
| HTTP 401/403 | Authentication/authorization thất bại | Không retry như lỗi mạng |
| HTTP 413 | Payload quá lớn | Không retry cùng payload |

**Timeout không chứng minh server chưa làm gì.** Một client an toàn phải coi timeout sau khi gửi command là unknown outcome cho đến khi truy vấn được trạng thái hoặc gửi lại cùng idempotency key tới server hỗ trợ deduplication.

## 3. Retry, idempotency và deduplication là ba khái niệm khác nhau

- **Retry**: gửi lại một lần thực hiện vì client chưa nhận được kết quả mong muốn.
- **Idempotency**: lặp lại cùng một intent không làm thay đổi kết quả nghiệp vụ sau lần đầu.
- **Deduplication**: nhận diện và xử lý một request đã được tiếp nhận/xử lý trước đó để tránh thực hiện side effect lần nữa.

HTTP `PUT` thường được thiết kế idempotent theo semantics HTTP, nhưng SOAP operation thường được mô tả bằng WSDL operation và business contract riêng. Tên `Get...`, `Create...` hay SOAPAction **không tự quyết định** semantics retry.

### 3.1. Idempotent không có nghĩa response phải giống từng byte

Một request tra cứu trạng thái có thể trả `PENDING` ở lần đầu và `SHIPPED` ở lần sau do trạng thái nghiệp vụ thay đổi. Operation vẫn không gây side effect chỉ vì được gọi nhiều lần.

Với một command tạo vận đơn, retry cùng idempotency key có thể trả lại cùng `shipmentId` và outcome đã lưu, dù timestamp HTTP hoặc correlation ID của lần trao đổi hiện tại khác nhau.

### 3.2. Exactly-once thường là tuyên bố quá mạnh

Mạng có thể mất message/response, client có thể crash, server có thể restart, broker có thể redeliver. Hệ thống thực tế thường kết hợp:

- **At-least-once attempts**: request có thể được gửi nhiều lần.
- **Idempotency/deduplication**: server đảm bảo một business intent chỉ tạo một hiệu ứng đã định nghĩa.
- **Atomic persistence**: kết quả nghiệp vụ và idempotency record được commit nhất quán.
- **Recovery/status query**: client có cách xác định outcome khi response bị mất.

Nói “exactly once” mà không nêu boundary, storage, transaction và side effects bên ngoài dễ gây hiểu lầm. Mục tiêu thực tế là **một hiệu ứng nghiệp vụ có kiểm soát trong phạm vi được bảo vệ**, không phải một lần truyền duy nhất trên mạng.

## 4. Phân loại SOAP operation theo retry semantics

Trước khi cấu hình retry, lập inventory operation:

| Operation | Side effect | Retry mặc định | Điều kiện an toàn |
| --- | --- | --- | --- |
| `GetShipmentStatus` | Không, nếu là read thuần | Có giới hạn | Query ổn định, không side effect ẩn |
| `ListShipmentHistory` | Không, nếu là read thuần | Có giới hạn | Pagination/cursor có semantics rõ |
| `CreateShipment` | Tạo bản ghi/đặt chỗ | Không retry mù | Idempotency key và dedupe phía server |
| `CancelShipment` | Chuyển trạng thái | Có điều kiện | Key ổn định, state transition có điều kiện |
| `ChargePayment` | Trừ tiền/ghi nhận thanh toán | Tuyệt đối không retry mù | Provider idempotency/reference và reconciliation |
| `SendNotification` | Gửi email/SMS | Có thể gửi trùng | Outbox/deduplication ở notification boundary |
| `UploadDocument` | Lưu file/metadata | Có điều kiện | Document key, checksum, storage idempotency |
| `ApproveAdjustment` | Quyết định/phê duyệt | Không retry mù | Unique decision ID, approver/state checks |

### 4.1. Read-only cũng có thể gây tác dụng phụ

Một `Get...` operation vẫn có thể:

- Ghi audit event.
- Cập nhật `lastAccessedAt`.
- Tạo billing record theo lượt đọc.
- Gửi notification hoặc trigger workflow.
- Consume một one-time token.

Vì vậy hãy phân loại theo **side effects thật**, không chỉ theo tên operation.

### 4.2. Không retry validation/authentication failures

Những lỗi sau thường là deterministic:

- SOAP Sender/Client Fault do XSD hoặc business input sai.
- HTTP 400/401/403/404/413.
- WS-Security signature, UsernameToken, timestamp hoặc certificate không hợp lệ.
- Permission bị từ chối.
- Idempotency key bị dùng lại với payload khác.
- Business state conflict như hủy một shipment đã giao.

Retry liên tục không làm một request sai trở thành đúng; nó chỉ tăng tải và có thể làm hệ thống khó vận hành hơn.

## 5. Idempotency key là gì?

**Idempotency key** là định danh ổn định cho một business intent. Client tạo key khi bắt đầu command và giữ nguyên key cho mọi lần retry của command đó.

Ví dụ:

~~~xml
<sh:CreateShipmentRequest
    xmlns:sh="urn:example:shipment:v1">
  <sh:requestId>01JCR9QW9P0M6M6K2YFQ5GJ7NX</sh:requestId>
  <sh:accountId>ACCT-A</sh:accountId>
  <sh:orderReference>ORD-55</sh:orderReference>
  <sh:destinationCode>HCM-01</sh:destinationCode>
</sh:CreateShipmentRequest>
~~~

`requestId` trong ví dụ được dùng làm idempotency key theo contract giả định. Không phải mọi field `requestId` đều tự có semantics ấy; WSDL/XSD và tài liệu API phải quy định rõ.

### 5.1. Key phải được tạo ở client theo business intent

Ví dụ client nhận lệnh từ một đơn hàng `ORD-55`:

- Khi bắt đầu tạo shipment lần đầu, client tạo key `K-123`.
- Lần gửi đầu timeout.
- Client retry vẫn dùng `K-123`.
- Người dùng bấm retry lại từ màn hình vẫn dùng `K-123` nếu đó là cùng intent.
- Người dùng thực sự yêu cầu tạo một shipment thứ hai độc lập thì tạo key mới.

Không tạo UUID mới bên trong mỗi lần gọi method retry; làm vậy khiến server coi mỗi lần retry là một command khác.

### 5.2. Correlation ID không thay idempotency key

| Identifier | Mục đích | Có giữ nguyên qua retry? |
| --- | --- | --- |
| Idempotency key | Deduplicate business command | **Có** |
| Correlation ID | Liên kết log/trace của một business flow | Thường có |
| Attempt ID | Nhận diện một lần truyền cụ thể | Không, mỗi lần thử mới |
| SOAP Message ID | Nhận diện một SOAP message theo WS-Addressing nếu dùng | Có thể khác mỗi attempt |
| Order reference | Tham chiếu nghiệp vụ từ đối tác | Theo contract |
| Trace/span ID | Observability | Span của mỗi attempt thường mới; trace có thể cùng flow |

Một số hệ thống đặt correlation ID và idempotency key bằng nhau, nhưng đó là lựa chọn contract/design, không phải mặc định. Nếu cần theo dõi từng attempt riêng, vẫn phải có attempt ID hoặc span ID.

## 6. Chọn phạm vi duy nhất của idempotency key

Server cần biết key là duy nhất trong phạm vi nào. Một khóa có thể được scope bằng:

~~~text
(tenant_id, authenticated_partner_id, operation_name, idempotency_key)
~~~

Ví dụ `K-123` của `partner-a/CreateShipment` khác `K-123` của `partner-b/CreateShipment` nếu policy cho phép.

Không chỉ dùng idempotency key toàn cục nếu nhiều tenants có thể chọn cùng giá trị. Cũng không dùng một `partnerId` do SOAP Body tự khai mà chưa map tới verified principal.

### 6.1. Key phải có độ khó đoán phù hợp

Dùng UUID ngẫu nhiên, UUIDv7/ULID hoặc token đủ entropy tùy chuẩn nội bộ. Không dùng số tăng dần toàn cục nếu key có thể bị dò để truy cập trạng thái request của người khác.

Key không phải bearer credential. Mọi lookup/replay phải tiếp tục kiểm authorization theo principal, tenant và operation.

### 6.2. Độ dài và validation trong XSD

Contract có thể giới hạn:

- `minLength`/`maxLength`.
- Allowed character pattern nếu thực sự cần.
- `requestId` bắt buộc cho các commands có side effect.
- Quy tắc không tái sử dụng key trong retention window.

Không để key khổng lồ làm tăng index/database costs. Kiểm thêm giới hạn ở service layer vì validation ở client có thể bị bỏ qua.

## 7. Payload fingerprint: cùng key nhưng khác lệnh phải bị từ chối

Server nên lưu fingerprint/hash của **các trường command có ý nghĩa nghiệp vụ**, cùng idempotency key.

Ví dụ:

\[
fingerprint = SHA256(canonicalBusinessPayload)
\]

`canonicalBusinessPayload` nên là biểu diễn canonical do server xây từ DTO đã validate, không băm raw SOAP XML tùy tiện vì namespace prefixes, whitespace, timestamps hoặc WS-Security headers có thể thay đổi mà ý nghĩa nghiệp vụ không đổi.

Với key `K-123`:

- Payload lần đầu: account A, order ORD-55, destination HCM-01.
- Retry: cùng các giá trị trên → trả outcome đã ghi.
- Request khác dùng lại K-123 nhưng destination HN-02 → **idempotency conflict**, không thực hiện command thứ hai.

### 7.1. Tại sao không chỉ so request XML string?

SOAP message có thể khác ở:

- Prefix namespace nhưng QName tương đương.
- Element formatting/whitespace.
- Timestamp/security headers.
- WS-Addressing MessageID.
- Correlation/attempt metadata.

Hãy canonicalize các business fields đã parse, normalize theo contract và serialize ổn định. Nếu dữ liệu nhạy cảm, lưu keyed HMAC thay vì hash thuần trong trường hợp payload có entropy thấp và có nguy cơ dò giá trị.

### 7.2. Không fingerprint bí mật một cách bừa bãi

Không đưa UsernameToken password, certificate private material, Authorization header hoặc secret fields vào business fingerprint. Fingerprint nên gồm những trường quyết định nội dung tác dụng nghiệp vụ.

## 8. Lưu idempotency record nguyên tử với business result

Một bảng minh họa:

~~~sql
CREATE TABLE idempotency_record (
    tenant_id          VARCHAR(64) NOT NULL,
    partner_id         VARCHAR(128) NOT NULL,
    operation_name     VARCHAR(128) NOT NULL,
    idempotency_key    VARCHAR(128) NOT NULL,
    payload_hash       CHAR(64) NOT NULL,
    state              VARCHAR(24) NOT NULL,
    resource_id        VARCHAR(128),
    response_payload   TEXT,
    created_at         TIMESTAMP NOT NULL,
    completed_at       TIMESTAMP,
    expires_at         TIMESTAMP,
    PRIMARY KEY (
      tenant_id, partner_id, operation_name, idempotency_key
    )
);
~~~

Đây là DDL minh họa; kiểu timestamp, index, collation và độ dài cần điều chỉnh theo database thực tế. `response_payload` có thể thay bằng business result reference hoặc response snapshot an toàn. Không lưu SOAP envelope raw có token/password.

### 8.1. Transaction flow đơn giản

~~~mermaid
flowchart TD
    A[Receive command] --> B[Authenticate + authorize]
    B --> C[Validate command + compute fingerprint]
    C --> D[Insert idempotency key]
    D --> E{Unique key acquired?}
    E -->|No, existing same hash| F[Return stored outcome]
    E -->|No, different hash| G[Idempotency conflict]
    E -->|Yes| H[Execute business operation]
    H --> I[Store resource/result]
    I --> J[Mark record COMPLETED]
    J --> K[Commit transaction]
    K --> L[Return SOAP response]
~~~

Nếu record và business update cùng một transactional database, có thể thực hiện insert, business update và complete record trong **một transaction**. Lần retry chỉ nhìn thấy trạng thái committed sau khi cả hai cùng commit.

### 8.2. Race giữa hai request cùng key

Unique constraint là lớp bảo vệ quan trọng. Nếu hai server instances đồng thời nhận cùng key:

- Chỉ một transaction thắng insert/unique key.
- Transaction còn lại phải xử lý unique conflict và đọc record đã commit, hoặc chờ/retry lookup theo semantics DB.
- Không để cả hai cùng chạy business operation trước khi deduplication quyết định winner.

Một câu `SELECT` trước rồi `INSERT` không đủ khi không có unique constraint/locking; hai threads có thể cùng thấy “chưa tồn tại”.

### 8.3. Đừng lưu COMPLETED trước business commit

Nếu server ghi idempotency state `COMPLETED`, rồi business transaction rollback, retry sẽ nhận một kết quả thành công không tồn tại. Business result và dedupe state phải có atomicity hoặc một state machine/recovery protocol chứng minh được tính nhất quán.

## 9. Xử lý trạng thái PROCESSING và request đồng thời

Một số hệ thống xử lý lâu không thể giữ một database transaction mở trong toàn bộ workflow. Có thể dùng state machine:

| State | Ý nghĩa | Hành vi retry |
| --- | --- | --- |
| `PROCESSING` | Request đã được nhận, công việc chưa hoàn tất | Trả trạng thái đang xử lý hoặc hướng client query |
| `COMPLETED` | Có kết quả đã lưu | Replay kết quả |
| `FAILED_FINAL` | Lỗi xác định, không retry với cùng payload | Trả cùng lỗi business |
| `RETRYABLE_FAILURE` | Có thể tiếp tục theo workflow | Tiếp tục cùng operation/key có kiểm soát |
| `UNKNOWN` | Không xác định được kết quả downstream | Reconciliation trước khi quyết định |
| `EXPIRED` | Retention window kết thúc | Theo contract; không mặc định cho phép thực hiện lại |

State machine cần được cập nhật bằng transaction/compare-and-set/lease để tránh nhiều workers cùng claim một request.

### 9.1. Không giữ lock vĩnh viễn

Nếu worker crash khi state là `PROCESSING`, cần lease/heartbeat hoặc timeout để recovery. Tuy nhiên không chỉ thấy lease hết hạn rồi thực hiện lại side effect; trước hết cần xác định operation trước có thể đã hoàn thành ở downstream hay không.

### 9.2. Trả một trạng thái có thể truy vấn

Contract có thể quy định `GetOperationStatus(requestId)` hoặc `GetCommandResult(idempotencyKey)` để client hỏi outcome. Endpoint này vẫn phải kiểm quyền và scope key theo authenticated principal; không để người có key đoán biết kết quả của tenant khác.

## 10. Side effects ngoài database: Outbox và downstream idempotency

Một transaction database không thể tự atomically commit một SMTP send, payment provider call hoặc message broker publish nếu không có protocol phân tán phù hợp.

Ví dụ `CreateShipment` tạo row và gửi event:

1. Insert shipment.
2. Insert outbox event trong cùng transaction.
3. Commit.
4. Outbox dispatcher gửi event.
5. Consumer deduplicate theo event ID/operation key.
6. Notification/payment provider nhận external idempotency key nếu hỗ trợ.

Nếu server gửi email trước commit rồi transaction rollback, có thể có email cho shipment không tồn tại. Nếu commit xong nhưng dispatcher crash sau khi gửi event và trước khi mark sent, event có thể được publish lại.

**Outbox thường tạo delivery at-least-once; consumer vẫn cần idempotency/deduplication.**

### 10.1. Idempotency phải xuyên suốt chuỗi

Nếu SOAP server ghi idempotency record nhưng downstream payment provider không có idempotent reference, duplicate có thể xảy ra ở payment boundary. Mỗi side effect phải có một strategy tương ứng:

- Database write: unique constraint/transaction.
- Outbox: stable event ID và consumer inbox/deduplication.
- Payment: provider idempotency key/reference và status reconciliation.
- Email: notification job ID và provider-specific dedupe khi có.
- File storage: deterministic object key/checksum hoặc conditional create.

Đừng khẳng định toàn bộ workflow “exactly once” chỉ vì table idempotency có unique index.

## 11. Client retry policy: phân loại trước khi gửi lại

Client nên quyết định retry dựa trên:

- **Operation semantics** (read hay command).
- **Có idempotency key không** và server có hỗ trợ không.
- Loại exception/HTTP status.
- SOAP Fault code/detail và policy đã thỏa thuận.
- Attempt count, total deadline và retry budget.
- Retry-After hoặc partner-specific throttling.
- Request body có thể gửi lại an toàn không.
- Credentials/certificate còn hợp lệ không.

### 11.1. Bảng phân loại

| Tình huống | Default | Ghi chú |
| --- | --- | --- |
| Connect timeout trước request | Có thể retry | Chỉ nếu lỗi transient và deadline còn |
| Connection reset trong write/read | Không rõ outcome | Với command cần key ổn định |
| Read timeout sau khi gửi | Không rõ outcome | Không tạo key mới |
| HTTP 429 | Có điều kiện | Tôn trọng `Retry-After`, budget |
| HTTP 502/503/504 | Có điều kiện | Gateway có thể không biết backend đã commit hay chưa |
| HTTP 400/401/403/404/413 | Không | Sửa request/credentials/authorization |
| SOAP Sender/Client Fault | Thường không | Lỗi request/contract/security |
| SOAP Receiver/Server Fault | Theo fault code | Chỉ retry nếu contract cho biết transient và idempotent |
| Invalid signature/certificate | Không | Không retry credential sai |
| Business state conflict | Không | Cần xử lý nghiệp vụ |
| Idempotency conflict | Không | Cùng key nhưng khác payload là client bug |

Không chỉ retry theo HTTP status: SOAP Fault có thể được gửi với HTTP 500; body Fault và detail thường quyết định semantics. Ngược lại, reverse proxy có thể trả HTML 502 không phải SOAP Fault.

### 11.2. Retry policy phải được công bố

Đối tác cần biết:

- Fault codes nào transient.
- Retry window tối đa bao lâu.
- Có hỗ trợ idempotency key không.
- Retention period của key.
- Khi nào phải query status.
- Thế nào là cùng business intent.
- Có cho đổi payload dưới cùng key hay không.
- Cách xử lý request đang `PROCESSING`.

Không để client suy đoán semantics từ message text tự do.

## 12. Exponential backoff và jitter

Retry liên tiếp không delay có thể khuếch đại outage. Exponential backoff tăng khoảng cách giữa các lần thử:

\[
d_n = \min(d_{max}, d_0 \times 2^n)
\]

Trong đó `d0` là initial delay, `dmax` là cap, `n` là chỉ số retry bắt đầu từ 0.

**Full jitter** chọn một delay ngẫu nhiên trong:

\[
wait_n \sim U(0, d_n)
\]

Điều này phân tán nhiều clients thay vì cùng retry đúng một thời điểm.

### 12.1. Ví dụ

Giả sử `d0 = 200 ms`, `dmax = 5 s`:

| Retry index | Backoff cap | Full jitter range |
| ---: | ---: | --- |
| 0 | 200 ms | 0–200 ms |
| 1 | 400 ms | 0–400 ms |
| 2 | 800 ms | 0–800 ms |
| 3 | 1.600 ms | 0–1.600 ms |
| 4 | 3.200 ms | 0–3.200 ms |
| 5 | 5.000 ms | 0–5.000 ms |

Đây là số minh họa, không phải mặc định Spring-WS. Tính tổng delay và timeout theo SLA/business deadline, không chỉ số attempts.

### 12.2. Retry-After

Nếu HTTP 429/503 trả `Retry-After`, client nên tuân theo trong phạm vi deadline/budget. Header có thể là số giây hoặc HTTP date theo HTTP semantics. Validate giá trị, cap thời gian chờ và không để response không đáng tin bắt client ngủ vô hạn.

## 13. Retry budget, deadline và timeout

Một retry policy an toàn cần:

- Per-attempt connection timeout.
- Per-attempt response/read timeout.
- **Total operation deadline** tính cả queueing, serialization và backoff.
- Maximum attempts.
- Retry budget theo dependency/client/partner.
- Circuit breaker hoặc load shedding khi downstream tiếp tục lỗi.
- Cancellation khi caller không còn chờ kết quả.

Ví dụ tổng deadline 8 giây, 3 attempts, mỗi attempt timeout 2 giây và backoff 200/400 ms: vẫn phải cộng cả thời gian lập request, DNS, connect, response parse và scheduling. Cấu hình các timeout độc lập cần khớp với deadline tổng.

### 13.1. Không xếp nhiều lớp retry chồng nhau

Nếu `WebServiceTemplate` wrapper retry 3 lần, HTTP client retry 3 lần, proxy retry 2 lần và caller retry 3 lần, số request thực tế có thể lên tới hàng chục lần.

Xác định một tầng sở hữu retry policy chính. Các tầng thấp hơn chỉ retry transport failures được biết chắc an toàn, với budget chung/được tính vào tổng attempts. Kiểm tra hành vi retry mặc định của HTTP client, gateway và broker, không giả định chỉ có một lần retry.

## 14. Dùng WebServiceTemplate trong retry boundary

`WebServiceTemplate` của Spring-WS gửi request/nhận response và thực hiện marshal/unmarshal. Retry thường được đặt ở một application wrapper quanh **một operation**, không phải bằng cách retry toàn bộ business workflow vô điều kiện.

Ví dụ facade:

~~~java
public final class ShipmentSoapClient {
    private final WebServiceTemplate template;
    private final RetryPolicy retryPolicy;

    public ShipmentSoapClient(
            WebServiceTemplate template,
            RetryPolicy retryPolicy) {
        this.template = template;
        this.retryPolicy = retryPolicy;
    }

    public CreateShipmentResponse create(
            CreateShipmentRequest request) {
        String key = request.getRequestId();

        return retryPolicy.execute(
            () -> template.marshalSendAndReceive(
                request,
                message -> addAttemptHeaders(message, key)
            ),
            failure -> isRetryableCreateFailure(failure)
        );
    }
}
~~~

Đây là **pseudo-integration**: `RetryPolicy`, `addAttemptHeaders` và `isRetryableCreateFailure` là code ứng dụng cần triển khai; exact `marshalSendAndReceive` overload và message callback phụ thuộc Spring-WS version. Mục đích quan trọng là `requestId` được tạo trước retry loop và giữ nguyên trong mọi lần gửi.

### 14.1. Không mutate JAXB request mỗi attempt

Không thay `requestId`, account, order reference hoặc destination khi retry. Các fields như attempt number, timestamp vận chuyển hoặc trace header có thể khác nếu contract cho phép, nhưng phải được loại khỏi business fingerprint.

### 14.2. Request phải replayable

- JAXB object có thể marshal lại nếu không bị mutate.
- Attachment từ file nên đọc lại được; stream one-shot cần buffer/spool có giới hạn hoặc mở stream mới.
- Không retry khi request body đã bị tiêu thụ và không thể tái tạo.
- SOAP message interceptor không nên sửa business payload khác nhau theo attempt.

## 15. Ví dụ retry wrapper có giới hạn

Một minh họa thuần Java (không phụ thuộc thư viện retry cụ thể):

~~~java
import java.time.Duration;
import java.util.concurrent.ThreadLocalRandom;
import java.util.function.Predicate;

public final class SimpleRetryExecutor {

    public <T> T execute(
            CheckedSupplier<T> action,
            Predicate<Exception> retryable,
            int maxAttempts,
            Duration initialDelay,
            Duration maxDelay) throws Exception {

        Exception last = null;

        for (int attempt = 0; attempt < maxAttempts; attempt++) {
            try {
                return action.get();
            } catch (Exception failure) {
                last = failure;

                boolean canRetry =
                    attempt + 1 < maxAttempts
                    && retryable.test(failure);

                if (!canRetry) {
                    throw failure;
                }

                long capMillis = Math.min(
                    maxDelay.toMillis(),
                    initialDelay.toMillis() * (1L << attempt));

                long delayMillis =
                    ThreadLocalRandom.current()
                        .nextLong(Math.max(1, capMillis + 1));

                Thread.sleep(delayMillis);
            }
        }

        throw last;
    }

    @FunctionalInterface
    public interface CheckedSupplier<T> {
        T get() throws Exception;
    }
}
~~~

Đây là ví dụ giáo dục, **chưa phải production-ready**:

- `1L << attempt` cần giới hạn attempts để tránh overflow.
- Chưa tính total deadline/cancellation.
- Chưa parse `Retry-After`.
- `Thread.sleep` chặn thread và interruption cần được xử lý/propagate.
- Chưa phân loại SOAP Fault/HTTP exception.
- Chưa có metrics, retry budget hoặc circuit breaker.
- `maxAttempts` phải được validate lớn hơn 0; `maxDelay`/`initialDelay` không âm.
- Với reactive/async app, dùng scheduler/non-blocking delay phù hợp.

Một thư viện như Spring Retry hoặc Resilience4j có thể hỗ trợ policy orchestration, nhưng **không tự giải quyết idempotency phía server**. Kiểm compatibility và semantics theo version trước khi chọn.

## 16. Không retry mọi WebServiceTransportException

Spring-WS có các exception ở tầng transport và SOAP. Tên class và wrapping có thể khác theo sender, nhưng tư duy phân loại phải rõ:

- Lỗi I/O/connection tạm thời có thể retry theo operation semantics.
- HTTP status exception cần kiểm status và headers.
- SOAP Fault phải parse fault code/detail theo contract.
- Security failures, invalid request và business errors không phải lỗi transient.
- Unexpected runtime exception có thể là bug; không retry vô hạn.

Ví dụ phân loại theo mã lỗi ứng dụng:

~~~java
boolean isRetryable(Result result) {
    return switch (result.category()) {
        case CONNECT_TIMEOUT,
             CONNECTION_RESET,
             HTTP_429,
             HTTP_502,
             HTTP_503,
             HTTP_504,
             SOAP_TRANSIENT_RECEIVER_FAULT -> true;
        case SOAP_SENDER_FAULT,
             AUTHENTICATION_FAILED,
             AUTHORIZATION_DENIED,
             VALIDATION_FAILED,
             IDEMPOTENCY_CONFLICT,
             BUSINESS_STATE_CONFLICT,
             CERTIFICATE_INVALID -> false;
        default -> false;
    };
}
~~~

`Result` và enum ở đây là abstraction ứng dụng. Với exception thật, cần unwrap `cause` có kiểm soát, không dựa vào substring của message như `"timeout"` hoặc `"temporary"` để quyết định.

### 16.1. Server Fault không phải lúc nào cũng retryable

SOAP 1.1 dùng `Client`/`Server`, SOAP 1.2 dùng `Sender`/`Receiver`. `Server`/`Receiver` là nhóm lỗi phía server nhưng có thể là lỗi vĩnh viễn của configuration, schema, code hoặc dependency. Tốt hơn là contract công bố fault detail/code ổn định như `DEPENDENCY_TEMPORARILY_UNAVAILABLE`; client phân loại theo code đó.

## 17. Status query và recovery sau unknown outcome

Với một command có idempotency key, contract có thể cung cấp:

~~~xml
<sh:GetCommandStatusRequest>
  <sh:requestId>REQ-1042</sh:requestId>
</sh:GetCommandStatusRequest>
~~~

Response ví dụ:

~~~xml
<sh:GetCommandStatusResponse>
  <sh:requestId>REQ-1042</sh:requestId>
  <sh:state>COMPLETED</sh:state>
  <sh:resourceId>SHP-5001</sh:resourceId>
</sh:GetCommandStatusResponse>
~~~

Contract cần xác định các trạng thái như `NOT_FOUND`, `PROCESSING`, `COMPLETED`, `FAILED_FINAL`, `UNKNOWN`. `NOT_FOUND` không nhất thiết chứng minh request chưa tới server: record có thể chưa commit, đang chờ replica, đã hết retention hoặc status query đọc từ eventual-consistent store.

### 17.1. Không lập tức tạo key mới khi NOT_FOUND

Nếu status query chưa thấy key, có thể:

1. Đợi propagation window theo contract.
2. Gửi lại cùng key tới endpoint hỗ trợ idempotency.
3. Tra cứu ở authoritative store/status endpoint.
4. Chuyển manual reconciliation nếu downstream outcome chưa rõ.

Không tạo business intent mới cho tới khi xác minh intent trước đã kết thúc hoặc được hủy theo protocol.

## 18. Idempotency với payment và side effect không thể đảo ngược

Thanh toán, chuyển tiền, phát hành vé hoặc gửi lệnh tới thiết bị vật lý có rủi ro cao. Với những operation này:

- Dùng idempotency key/reference do business flow tạo một lần.
- Gửi cùng key tới payment provider nếu provider hỗ trợ.
- Lưu provider transaction ID và status.
- Khi timeout unknown outcome, query provider trước khi retry charge.
- Không tự bù trừ bằng cách charge lần nữa rồi hy vọng hệ thống reconciliation sửa.
- Thiết kế compensation/saga nếu workflow nhiều hệ thống.
- Có manual review cho state `UNKNOWN` quá lâu.

**Một idempotency table ở SOAP facade không thể ngăn payment duplicate nếu facade gọi provider không có idempotency hoặc reconciliation.**

## 19. Authentication, signature và timestamp khi retry

SOAP message có thể dùng WS-Security UsernameToken, XML Signature, Timestamp hoặc encryption. Retry cùng business intent không có nghĩa **SOAP bytes phải giống hệt**:

- Timestamp có thể phải tạo mới để không hết hạn.
- Nonce cần mới cho mỗi UsernameToken PasswordDigest theo policy.
- WS-Addressing MessageID có thể mới cho mỗi SOAP message.
- Signature phải được tính lại nếu header/body thay đổi.
- Business idempotency key phải giữ nguyên.
- HTTP authorization/certificate phải còn hợp lệ.

Không replay nguyên một SOAP envelope đã ký và timestamp cũ qua thời gian dài nếu security policy yêu cầu freshness. Cũng không đổi `requestId` để tạo message mới; đây là hai lớp identifier khác nhau.

### 19.1. Security replay cache khác business idempotency store

WSS4J replay protection có thể chặn một nonce/timestamp/message bị tái sử dụng theo security profile. Nó không thay deduplication business key:

- Security replay cache chống replay message/token ở tầng security.
- Idempotency store cho phép client retry cùng business command trong policy window và trả lại outcome.
- Cùng requestId nhưng tạo UsernameToken nonce mới có thể là message mới hợp lệ nhưng cùng business intent.
- Tái sử dụng raw signed message có thể bị WSS4J chặn dù business idempotency key vẫn đúng.

Phải thiết kế cả hai lớp mà không coi một lớp thay thế lớp kia.

## 20. Retention: giữ idempotency record bao lâu?

Retention window phải lớn hơn khoảng retry/recovery có thể xảy ra:

- Client timeout/retry window.
- Queue redelivery/recovery window.
- Partner outage duration.
- Batch/job restart window.
- Settlement/reconciliation process nếu cần.
- Clock skew và replication lag.

Nếu xóa record quá sớm, client retry sau vài giờ có thể tạo lại business side effect. Nếu giữ mãi, bảng sẽ phình và có dữ liệu nhạy cảm tồn tại lâu hơn cần thiết.

### 20.1. TTL không tự giải quyết key reuse

Sau khi record hết hạn, server cần policy rõ:

- Key cũ bị từ chối vĩnh viễn theo compact tombstone.
- Key được phép tái sử dụng sau một window rõ ràng.
- Business uniqueness constraint riêng (ví dụ order ID) ngăn tạo trùng lâu dài.
- Kết quả cũ được lưu trong audit/event store.

Với một số lệnh tài chính, **business uniqueness constraint** có thể cần tồn tại lâu hơn idempotency cache. Đừng dùng TTL làm lớp bảo vệ duy nhất chống duplicate.

## 21. Kiểm thử retry: test cả khi response mất sau commit

Một test chỉ mô phỏng HTTP 503 trước khi server xử lý sẽ không kiểm được nguy cơ quan trọng nhất. Cần mô phỏng server đã commit nhưng client không nhận response.

### 21.1. Test scenario

~~~text
Given:
  requestId = REQ-1042
  business order = ORD-55
  server idempotency store is empty

When:
  first SOAP request reaches service
  service commits shipment SHP-5001
  test transport drops the response
  client retries with the same requestId

Then:
  server returns SHP-5001 again
  shipment row count for REQ-1042 is 1
  outbox event count for the command is 1
  no second notification/payment is created
~~~

Test phải quan sát **database/downstream side effects**, không chỉ assert client nhận được một response.

### 21.2. Dùng fault injection ở đúng thời điểm

Có thể dùng test server/interceptor/fake transport để:

- Delay response vượt read timeout sau khi handler commit.
- Drop response body sau transaction commit.
- Reset connection khi response đang ghi.
- Trả HTTP 503 trước khi request tới application.
- Trả HTTP 503 sau khi upstream đã xử lý (gateway behavior mô phỏng).
- Crash worker sau khi gửi outbox event nhưng trước khi mark sent.

Các ca này đại diện những failure windows khác nhau; một mock client chỉ ném exception trước khi gọi server sẽ không mô phỏng unknown outcome.

## 22. Unit test cho retry classifier và backoff

Các thứ nên test riêng:

- Lỗi nào retryable/non-retryable.
- Max attempts chính xác.
- Không retry sau total deadline.
- Jitter nằm trong range.
- `Retry-After` được parse, validate và cap.
- SOAP Sender/Client Fault không retry.
- Idempotency conflict không retry.
- Interrupted thread dừng retry.
- Một retry attempt có attempt ID mới nhưng key ổn định.
- Request object/body được tái tạo giống business payload.

Dùng injectable `Clock`, `Sleeper`, `RandomSource` hoặc scheduler để kiểm deterministic; tránh test dựa vào `Thread.sleep` thật và thời gian chờ dài.

Ví dụ interface cho testability:

~~~java
interface Sleeper {
    void sleep(Duration duration) throws InterruptedException;
}

interface DelayPolicy {
    Duration nextDelay(int retryIndex);
}
~~~

Đây là ports do ứng dụng định nghĩa. Unit tests có thể dùng fake sleeper ghi lại delays mà không phải đợi.

## 23. Test server idempotency và concurrent duplicates

| Kịch bản | Assertion quan trọng |
| --- | --- |
| Cùng key, cùng payload, tuần tự | Một resource; retry trả cùng resource |
| Cùng key, payload khác | Conflict; không chạy operation lần hai |
| Cùng key, đồng thời trên hai pods | Một business execution |
| Server crash trước commit | Retry có thể execute một lần |
| Server crash sau commit trước response | Retry trả outcome đã lưu |
| Outbox publish rồi crash trước ack | Consumer không tạo duplicate side effect |
| Key hết retention | Behavior đúng contract/tombstone policy |
| Partner khác dùng cùng key | Scope không va chạm ngoài ý muốn |
| Principal không có quyền query key | Không lộ result của partner khác |
| Idempotency store unavailable | Fail closed cho commands có side effect |

### 23.1. Test concurrency thật

Dùng nhiều threads/clients và barrier để gửi cùng key gần như đồng thời. Assert:

- Có đúng một row/resource.
- Có đúng số outbox records.
- Không có trạng thái `PROCESSING` mồ côi vĩnh viễn.
- Các requests thua nhận outcome/fault theo contract.
- Payload mismatch không đổi dữ liệu winner.
- Unique constraint thực sự ở database, không chỉ kiểm bằng mock repository.

## 24. SOAP client integration test với Spring-WS

Có thể dùng các công cụ theo tầng:

- `MockWebServiceServer`: kiểm SOAP client request, response matching và lỗi ở mức Spring-WS client testing.
- Test HTTP server (ví dụ WireMock hoặc server fixture): mô phỏng status, delay, disconnect và headers.
- SOAP endpoint integration test với application context thật: kiểm WSS4J, endpoint, method authorization, transaction và idempotency.
- Database integration test với engine thật: kiểm unique constraint, isolation và race.
- Consumer/provider contract tests: xác minh WSDL/XSD, fault details, namespaces, SOAP 1.1/1.2 và idempotency semantics.

### 24.1. MockWebServiceServer có giới hạn

Mock transport có thể kiểm client tạo payload đúng và xử lý SOAP response/Fault. Nhưng nó thường không tái tạo đầy đủ:

- TCP connection reset ở giữa response.
- Commit database phía server rồi mất response.
- Proxy/gateway retry behavior.
- TLS/mTLS handshake và certificate expiry.
- Hai server instances tranh cùng unique key.

Kết hợp mock tests với HTTP/TLS/database integration tests; không tuyên bố “end-to-end idempotency passed” chỉ từ một mock response.

## 25. Ví dụ test response mất sau commit (ý tưởng kiểm thử)

Pseudo-code integration test:

~~~java
@Test
void retryAfterCommittedResponseWasLostReturnsSameShipment() {
    String key = "REQ-1042";

    transport.failAfterServerCommitOnce();

    assertThrows(
        ResourceAccessException.class,
        () -> client.create(createRequest(key, "ORD-55")));

    CreateShipmentResponse retry =
        client.create(createRequest(key, "ORD-55"));

    assertEquals("SHP-5001", retry.getShipmentId());
    assertEquals(1, shipmentRepository.countByRequestId(key));
    assertEquals(1, outboxRepository.countByRequestId(key));
}
~~~

`transport.failAfterServerCommitOnce()` là **test hook giả định** mà nhóm test phải tự triển khai, không phải method có sẵn của Spring-WS. Exception class thực tế phụ thuộc sender/test server. Điều quan trọng là first request **đã commit thật** trước khi transport giả lập mất response.

## 26. Test SOAP Fault mapping và retry decisions

Fault detail nên có mã ổn định trong XSD/WSDL hoặc tài liệu contract:

| Fault code | Ý nghĩa | Retry? |
| --- | --- | --- |
| `INVALID_REQUEST` | Request không đúng contract | Không |
| `AUTHENTICATION_FAILED` | Credential/token không hợp lệ | Không |
| `ACCESS_DENIED` | Không có quyền | Không |
| `IDEMPOTENCY_CONFLICT` | Cùng key, payload khác | Không |
| `BUSINESS_STATE_CONFLICT` | Trạng thái không cho operation | Không |
| `DEPENDENCY_TEMPORARY_UNAVAILABLE` | Downstream tạm lỗi | Có điều kiện |
| `PROCESSING_IN_PROGRESS` | Key đang được xử lý | Query/poll theo policy |
| `OUTCOME_UNKNOWN` | Server chưa xác định được kết quả downstream | Reconcile/query; không tạo key mới |
| `INTERNAL_ERROR` | Lỗi server chưa phân loại | Không retry vô hạn |

Đừng phân loại bằng `faultstring` tự do. Dùng QName/code/detail có contract, và giữ SOAP 1.1/1.2 mapping nhất quán.

### 26.1. Fault có thể đi kèm HTTP 500

Nhiều SOAP stacks trả SOAP Fault với HTTP 500. Client không nên bỏ qua body chỉ vì status là 500; cần parse fault khi transport cho phép. Ngược lại, HTML 500 từ proxy không phải SOAP Fault và phải được xử lý riêng như transport/gateway response.

## 27. Retry trong batch và message-driven clients

Một batch có 1.000 commands không nên retry cả batch nếu 998 đã thành công và 2 commands lỗi. Cần một idempotency key cho từng business intent, trạng thái/receipt per item và giới hạn concurrency.

Với message listener:

- Ack message sau khi outcome được lưu bền vững.
- Redelivery dùng cùng business key/event ID.
- Consumer inbox/deduplication bảo vệ side effect.
- Poison messages/validation errors chuyển dead-letter hoặc trạng thái terminal theo policy.
- Retry delay và DLQ không làm mất business correlation.

**Transport attempt ID khác event ID/idempotency key**; redelivery không được làm thành business command mới.

## 28. Observability: nhìn được mỗi attempt và một business intent

Một log cấu trúc có thể ghi:

~~~json
{
  "operation": "CreateShipment",
  "partner": "partner-a",
  "idempotencyKeyHash": "sha256:example",
  "correlationId": "CORR-1042",
  "attempt": 2,
  "result": "REPLAYED_COMPLETED",
  "resourceId": "SHP-5001",
  "durationMs": 183
}
~~~

Ví dụ chỉ minh họa metadata; không log raw credentials, SOAP UsernameToken, Authorization header, private data hoặc toàn bộ SOAP Body. Hash key cũng phải đánh giá cardinality/privacy; không đưa raw idempotency key làm metrics label.

Metrics có thể gồm:

- `soap_client_attempts_total{operation,outcome}`
- `soap_client_retries_total{partner,reason}`
- `soap_idempotency_replays_total{operation}`
- `soap_idempotency_conflicts_total{operation}`
- `soap_unknown_outcomes_total{operation}`
- `soap_retry_exhausted_total{operation}`
- `soap_processing_in_progress_total{operation}`

Đây là metric names gợi ý, không tự được Spring-WS cung cấp. Dùng labels bounded; partner IDs/operation names chỉ khi số lượng được kiểm soát.

### 28.1. Đừng log body trong retry loop

Một request có thể được gửi nhiều lần; logging raw XML ở mỗi attempt vừa tăng chi phí vừa nhân rộng dữ liệu nhạy cảm. Log operation, key hash/reference phù hợp, attempt, result category, latency và correlation. Nếu phải lưu payload để điều tra, cần redaction, encryption, access control và retention riêng.

## 29. Retry và circuit breaker

Retry phù hợp với lỗi ngắn hạn. Khi downstream liên tục hỏng, retry tăng tải và có thể giữ thread/resource quá lâu. Circuit breaker tạm ngừng call khi failure rate vượt threshold:

- `CLOSED`: cho request đi qua.
- `OPEN`: từ chối nhanh trong thời gian cool-down.
- `HALF_OPEN`: cho một số probes để kiểm tra phục hồi.

Circuit breaker không bảo đảm idempotency; nó chỉ điều tiết traffic. Khi mở breaker, client command có thể chưa được gửi hoặc outcome trước đó vẫn unknown. Giữ key và trạng thái command để recovery sau.

### 29.1. Bulkhead và per-partner isolation

Một partner SOAP endpoint chậm không nên chiếm hết threads/connections cho các partner khác. Dùng bounded thread pool, connection pool, per-partner concurrency limits và retry budgets. Không mở một thread không giới hạn cho mỗi timeout.

## 30. Security và authorization trong status/retry endpoint

Một idempotency key không phải secret đủ để đọc kết quả. Mỗi `GetCommandStatus` hoặc replay:

- Xác thực caller bằng HTTP/TLS/WS-Security theo policy.
- Map principal/partner đáng tin.
- Kiểm key thuộc đúng principal/tenant/operation.
- Không trả resource ID hoặc response payload của tenant khác.
- Không để lookup endpoint trở thành oracle dò request IDs.
- Audit access/denied decisions.

Nếu client được quyền tạo command nhưng sau đó bị revoke, policy phải quy định họ còn được query kết quả cũ hay không. Tách quyền **submit**, **replay response** và **read resource** khi cần.

## 31. Những anti-pattern thường gặp

### 31.1. Sinh UUID mới mỗi attempt

Server thấy mỗi retry là command mới. Tạo key một lần khi bắt đầu business intent rồi giữ nguyên.

### 31.2. Retry mọi exception ba lần

Validation, auth, certificate, permission và business conflict không tự hồi phục. Classify faults/exceptions theo contract.

### 31.3. Timeout nghĩa là request thất bại

Server có thể đã commit. Coi outcome là unknown, query/retry cùng key.

### 31.4. Chỉ dedupe trong memory

Restart/pod scaling làm mất map. Dùng persistence shared/unique constraint với retention rõ.

### 31.5. SELECT trước rồi INSERT không unique constraint

Concurrent requests vẫn có thể duplicate. Enforce uniqueness ở database và handle conflict.

### 31.6. Lưu idempotency result sau side effect ở transaction khác

Crash giữa hai bước làm side effect có rồi nhưng record chưa có. Dùng transaction/Outbox/downstream idempotency hoặc recovery protocol.

### 31.7. Cùng key nhưng payload khác thì trả result cũ

Có thể che lỗi client hoặc kết hợp sai business intents. So fingerprint và trả conflict.

### 31.8. Dùng SOAP MessageID làm business key

MessageID có thể khác mỗi lần gửi; security/replay semantics khác business idempotency. Định nghĩa field/contract riêng hoặc quy định semantics rõ.

### 31.9. Retry cùng signed SOAP bytes mãi mãi

Timestamp/nonce có thể hết hạn hoặc bị replay protection chặn. Tạo message security mới cho mỗi attempt nhưng giữ business idempotency key.

### 31.10. Retry đồng thời không giới hạn

Gây retry storm và overload. Exponential backoff, jitter, budget, deadline, circuit breaker.

### 31.11. Dùng post-filter/response cache như idempotency

Caching một response không bảo vệ side effects server. Idempotency phải đặt tại command processing boundary và persistence.

### 31.12. Tin HTTP 503 chắc chắn server chưa xử lý

Gateway có thể trả 503 sau khi upstream commit hoặc response bị mất. Dùng idempotency khi outcome không rõ.

## 32. Quy trình triển khai đề xuất

1. Liệt kê mọi SOAP operation và side effects thực.
2. Phân loại read-only, idempotent command, non-idempotent command và external side effect.
3. Thiết kế XSD/WSDL fields cho idempotency key, status query và Fault codes.
4. Chọn scope key theo verified partner/tenant/operation.
5. Định nghĩa canonical business payload fingerprint.
6. Thiết kế idempotency state machine, unique constraint và retention.
7. Gộp business write + completed record vào transaction khi có thể.
8. Dùng outbox/inbox hoặc downstream idempotency cho side effects ngoài DB.
9. Thiết kế SOAP client retry classifier, total deadline, backoff+jitter, retry budget.
10. Giữ key ổn định và tái tạo request message an toàn từng attempt.
11. Đảm bảo WS-Security freshness/replay protection vẫn hợp lệ mỗi attempt.
12. Cung cấp status query/reconciliation cho unknown outcomes.
13. Ánh xạ SOAP Fault bằng stable codes, không retry deterministic errors.
14. Kiểm status/replay authorization theo principal/tenant.
15. Viết unit tests classifier/backoff và integration tests server dedupe/concurrency.
16. Fault-inject response loss **sau commit**, gateway errors và crash windows.
17. Đo duplicate, unknown outcomes, retry exhaustion và downstream availability.
18. Chạy interoperability tests với client Java/.NET/ESB theo WSDL/security policy thật.
19. Diễn tập restart/rollout/secret rotation và recovery khi idempotency store unavailable.

## 33. Bài tập thực hành

### Bài tập 1 — Phân loại operation

Với `GetShipmentStatus`, `CreateShipment`, `CancelShipment`, `ChargePayment`, `SendNotification`, liệt kê side effects và retry semantics. Giải thích operation nào cần idempotency key và tại sao.

### Bài tập 2 — Mô phỏng lost response

Tạo SOAP service test lưu shipment thành công rồi làm transport mất response đầu tiên. Client retry cùng `requestId`. Assert chỉ có một shipment và response retry trả cùng `shipmentId`.

### Bài tập 3 — Cùng key, payload khác

Gửi `CreateShipment(K-1, destination=HCM)` rồi `CreateShipment(K-1, destination=HAN)`. Server phải trả `IDEMPOTENCY_CONFLICT`, không đổi destination hoặc tạo shipment thứ hai.

### Bài tập 4 — Concurrent duplicate

Dùng 20–50 threads gửi cùng key cùng payload đến hai service instances. Enforce database unique constraint. Assert chỉ một business execution, một outbox event và các callers nhận cùng logical outcome theo contract.

### Bài tập 5 — Fault classifier

Tạo các SOAP 1.1/1.2 Fault và HTTP 400/401/429/502/503/504 fixtures. Kiểm retry classifier, `Retry-After`, maximum attempts và total deadline. Không dùng substring trong faultstring làm policy.

### Bài tập 6 — Replay security

Tạo UsernameToken/WS-Security mới cho mỗi retry với nonce/timestamp hợp lệ, giữ idempotency key. Gửi lại raw SOAP envelope cũ và so behavior replay cache với business deduplication store.

### Bài tập 7 — Outbox crash window

Publish outbox event rồi mô phỏng worker crash trước khi mark delivered. Redelivery phải không tạo hai notifications hoặc charges. Dùng consumer inbox/deduplication.

### Bài tập 8 — Unknown payment outcome

Mô phỏng payment provider charge thành công nhưng response timeout. Client phải query provider bằng stable reference hoặc retry cùng provider idempotency key; không charge bằng key mới.

### Bài tập 9 — Retention/recovery

Giảm retention trong test, gửi retry sau expiry và chứng minh behavior đúng contract. Thử partner khác dùng cùng key, principal không đủ quyền query key, và status replica bị lag.

### Bài tập 10 — Retry storm

Cho downstream trả 503 trong thời gian ngắn, chạy nhiều clients. Đo attempts, total latency và recovery. Thử jitter, budget, circuit breaker, bulkhead và xác nhận các giới hạn được tuân thủ.

## 34. Checklist trước khi phát hành

- [ ] Mỗi WSDL operation đã được phân loại theo side effect/retry semantics.
- [ ] Client tạo idempotency key **một lần cho mỗi business intent**.
- [ ] Key được giữ nguyên qua retry, timeout, process restart và user retry trong cùng intent.
- [ ] Contract mô tả key scope, length, retention, conflict behavior và status query.
- [ ] Server scope key theo trusted partner/tenant/operation.
- [ ] Request payload canonicalization/fingerprint bỏ fields vận chuyển/security biến đổi theo attempt.
- [ ] Cùng key nhưng payload khác bị từ chối rõ ràng.
- [ ] Database có unique constraint; không dựa vào SELECT-then-INSERT đơn thuần.
- [ ] Idempotency record và business result có atomicity/recovery protocol.
- [ ] `PROCESSING` có lease/heartbeat và xử lý worker crash.
- [ ] Outbox/inbox/downstream idempotency bảo vệ external side effects.
- [ ] Payment/email/storage provider có reference/dedupe phù hợp.
- [ ] Retry classifier hiểu HTTP status, SOAP Fault code/detail và exception phase.
- [ ] Validation/authentication/authorization/certificate/business conflict không bị retry tự động.
- [ ] Unknown outcome không làm client sinh key mới hoặc tạo side effect khác.
- [ ] Backoff có cap và jitter; có maximum attempts, total deadline và retry budget.
- [ ] Tôn trọng/cap `Retry-After`; không retry storm.
- [ ] HTTP client/gateway/proxy retry được kiểm kê để tránh retry amplification.
- [ ] Request body/attachment có thể replayable hoặc được tái tạo an toàn.
- [ ] WS-Security Timestamp/Nonce/Signature được tạo hợp lệ cho từng message attempt.
- [ ] Security replay cache không bị nhầm với business idempotency store.
- [ ] Status/replay endpoint kiểm authentication, tenant và authorization.
- [ ] SOAP Fault details có stable QName/code và không dựa faultstring tự do.
- [ ] Response mất **sau commit** được fault-inject trong test.
- [ ] Có concurrent duplicate tests trên database/instances thực.
- [ ] Có tests payload mismatch, retention expiry, crash windows, outbox redelivery và provider unknown outcome.
- [ ] Metrics phân biệt attempts/retries/replays/conflicts/unknown outcomes.
- [ ] Logs không chứa raw credentials, SOAP body nhạy cảm hoặc private data không cần thiết.
- [ ] Java/.NET/ESB interoperability kiểm idempotency và Fault semantics theo contract.

## 35. Tài liệu tham khảo

- [Spring Web Services — Reference](https://docs.spring.io/spring-ws/reference/): `WebServiceTemplate`, client interceptors, SOAP fault handling và client testing.
- [Spring Web Services — Client-side Testing](https://docs.spring.io/spring-ws/reference/testing.html): `MockWebServiceServer` và kiểm thử SOAP clients.
- [Spring Framework — WebServiceTemplate Javadoc](https://docs.spring.io/spring-ws/docs/current/api/org/springframework/ws/client/core/WebServiceTemplate.html): marshal/send/receive APIs và fault handling.
- [Spring Retry — Reference](https://github.com/spring-projects/spring-retry): retry policy, backoff và retry context (đối chiếu trạng thái/version được dự án dùng).
- [Resilience4j — Retry](https://resilience4j.readme.io/docs/retry): bounded retry, interval functions và integration patterns.
- [AWS Builders' Library — Timeouts, retries, and backoff with jitter](https://aws.amazon.com/builders-library/timeouts-retries-and-backoff-with-jitter/): timeout, retry amplification, backoff và jitter.
- [AWS — Making retries safe with idempotent APIs](https://aws.amazon.com/builders-library/making-retries-safe-with-idempotent-APIs/): idempotency tokens và xử lý request trùng.
- [IETF RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110): semantics của safe/idempotent methods và retry implications.
- [IETF RFC 9333 — RateLimit Fields for HTTP](https://www.rfc-editor.org/rfc/rfc9333): rate limit response metadata; kết hợp với policy đối tác thực tế.
- [Microsoft — Idempotency patterns](https://learn.microsoft.com/en-us/azure/architecture/patterns/idempotency): thiết kế chống duplicate và xử lý message delivery lặp.
- [Microservices.io — Idempotent Consumer](https://microservices.io/patterns/communication-style/idempotent-consumer.html): deduplication ở message consumer.
- [Microservices.io — Transactional Outbox](https://microservices.io/patterns/data/transactional-outbox.html): atomic persistence và delivery at-least-once.
- [OASIS — WS-Security 1.1.1](https://docs.oasis-open.org/wss-m/wss/v1.1.1/os/wss-SOAPMessageSecurity-v1.1.1-os.html): message security, token/signature và freshness/replay considerations.

Các ví dụ dùng Spring-WS API và Java theo hướng minh họa. Đối chiếu đúng phiên bản Spring-WS, HTTP sender, WSS4J, database engine, retry library và SOAP contract của đối tác trước khi áp dụng production. Các types như `RetryPolicy`, `IdempotencyRecord`, `ShipmentRepository` và test fault injection là abstractions cần triển khai trong ứng dụng.

## 36. Tổng kết

**Retry không làm một lệnh an toàn hơn nếu server không có cơ chế chống lặp side effect.** Khi client timeout sau khi server commit, outcome là unknown; client phải giữ nguyên idempotency key, query trạng thái hoặc gửi lại cùng intent đến server có deduplication. Sinh key mới trong mỗi attempt biến retry thành một business command khác.

Một thiết kế bền vững kết hợp operation semantics, key scope theo principal/tenant/operation, payload fingerprint, unique constraint, transaction, outbox/inbox và idempotency ở downstream. Client phân loại lỗi bằng HTTP/SOAP Fault contract, giới hạn attempts/deadline, exponential backoff+jitter, retry budget và circuit breaker. WS-Security replay protection vẫn phải hoạt động độc lập với business idempotency.

Trong **SPRING_WEB_SERVICES**, hãy kiểm thử đường đi thực từ `WebServiceTemplate` qua transport, WSS4J và endpoint đến database/downstream. Ca quan trọng nhất là **server đã commit nhưng response bị mất**; một test chỉ mock HTTP 503 trước khi xử lý chưa đủ. Khi duplicate, concurrency, crash windows, status recovery và interoperability đều được kiểm chứng, SOAP client mới có thể retry có trách nhiệm mà không nhân đôi tác dụng nghiệp vụ.
