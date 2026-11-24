# Idempotency: xử lý request lặp an toàn

> **Chương:** Chống replay  
> **Phạm vi:** Module **SECURITY_AUTHENTICATION_FUNDAMENTALS** tìm hiểu nguyên lý xác thực danh tính từ credential, mật khẩu, MFA, passkey và chứng chỉ đến token, phiên, liên kết danh tính và khôi phục tài khoản. Bài này giải thích idempotency trong API và hệ thống xác thực: làm sao retry một request sau timeout mà không tạo thêm giao dịch, credential hoặc side effect; cách ràng buộc key với principal và payload; và cách xử lý cạnh tranh, crash, retention cùng các giới hạn của cơ chế.

## 1. Mục tiêu học tập

Sau bài học, người học có thể:

1. Giải thích idempotency và phân biệt nó với replay protection, authentication và authorization.
2. Nhận diện các thao tác cần idempotency như tạo giao dịch, cấp credential, reset password, gửi webhook và tạo resource.
3. Thiết kế idempotency key có scope, entropy, thời hạn và quy tắc tái sử dụng rõ ràng.
4. Tạo request fingerprint từ dữ liệu nghiệp vụ đã canonicalize.
5. Xử lý request đồng thời bằng unique constraint, transaction và state machine.
6. Thiết kế hành vi retry khi timeout, mất response, lỗi trước/sau commit hoặc service restart.
7. Dùng transactional outbox/saga cho side effect bên ngoài database.
8. Ngăn key collision, cross-account reuse, payload mismatch, storage abuse và rò rỉ response.
9. Triển khai idempotency service trong Java/Spring và xây dựng ma trận kiểm thử.

## 2. Idempotency là gì?

Một thao tác được gọi là **idempotent** khi thực hiện lặp lại cùng một yêu cầu trong cùng ngữ cảnh tạo ra hiệu quả nghiệp vụ tương đương với thực hiện một lần.

Ví dụ:

- Client gửi yêu cầu tạo một khoản thanh toán, server đã commit nhưng response bị mất do mạng.
- Client không biết thao tác đã thành công hay chưa nên retry.
- Nếu server không có idempotency, retry có thể tạo khoản thanh toán thứ hai.
- Nếu server xử lý idempotently, request retry được nhận diện là cùng thao tác và không tạo side effect thứ hai.

Idempotency chủ yếu giải quyết sự không chắc chắn khi client retry. Nó không chứng minh ai gửi request, không xác minh token và không tự ngăn mọi dạng replay.

### Ví dụ đơn giản

Giả sử client gửi:

~~~http
POST /api/transfers
Idempotency-Key: 8d5f...random-value
Content-Type: application/json

{
  "sourceAccount": "A-104",
  "beneficiary": "B-205",
  "amount": 250000,
  "currency": "VND"
}
~~~

Server ghi nhận key và kết quả giao dịch. Khi client gửi lại cùng key, cùng principal và cùng nội dung, server trả kết quả đã lưu thay vì tạo giao dịch mới.

Nếu client dùng lại key đó với amount khác, server phải phát hiện payload mismatch và từ chối. Không được âm thầm coi đây là request mới.

## 3. Idempotency khác replay protection như thế nào?

Hai cơ chế có liên quan nhưng bảo vệ mục tiêu khác nhau:

| Cơ chế | Câu hỏi | Ví dụ |
|---|---|---|
| **Idempotency** | Request lặp có tạo thêm side effect nghiệp vụ không? | Retry tạo payment chỉ tạo một payment |
| **Replay protection** | Một proof/credential/message đã dùng có bị gửi lại để vượt xác minh không? | Nonce WebAuthn/OIDC/DPoP chỉ được chấp nhận một lần |
| **Authentication** | Requester có chứng minh được danh tính/credential không? | JWT signature hoặc passkey assertion hợp lệ |
| **Authorization** | Principal có quyền thực hiện action trên resource không? | User có quyền chuyển tiền từ account này |
| **Deduplication** | Hai message có cùng event identity đã được xử lý chưa? | Webhook delivery ID đã xuất hiện |

Một request có thể cần cả replay protection lẫn idempotency. Ví dụ, webhook có chữ ký và timestamp để xác minh nguồn, delivery ID để chống xử lý lặp, và business transaction ID để ngăn tạo side effect trùng.

Idempotency key không phải password, access token hoặc bằng chứng danh tính. Attacker không được phép thực hiện thao tác chỉ vì họ biết một key.

## 4. HTTP method và idempotency

HTTP định nghĩa một số method có semantics idempotent:

| Method | Semantics thường gặp | Lưu ý |
|---|---|---|
| GET | Safe và idempotent | Không dùng GET để tạo side effect nghiệp vụ |
| HEAD | Safe và idempotent | Tương tự GET nhưng không trả representation body |
| PUT | Idempotent | Thay thế trạng thái resource bằng representation đã chỉ định |
| DELETE | Idempotent | Gọi lại không làm resource bị xóa thêm lần nữa |
| POST | Không mặc định idempotent | Có thể tạo resource hoặc thực hiện command; thường cần idempotency key |
| PATCH | Không mặc định idempotent | Tùy semantics của patch document/operation |

Idempotent về HTTP semantics không có nghĩa mọi implementation đều an toàn. Ví dụ DELETE có thể phát nhiều email hoặc tạo nhiều audit side effect nếu code xử lý lặp không cẩn thận.

Ngược lại, POST có thể được thiết kế idempotently bằng key và state server-side. Hãy xác định hiệu quả nghiệp vụ, không chỉ nhìn tên method.

## 5. Khi nào cần idempotency?

Nên cân nhắc idempotency cho thao tác:

- Tạo thanh toán, chuyển tiền, hoàn tiền hoặc lệnh giao dịch.
- Tạo tài khoản, đơn hàng, hóa đơn, booking hoặc ticket.
- Cấp API key, client secret, recovery code hoặc credential.
- Thực hiện password reset hoặc authenticator replacement.
- Gửi email/SMS/push có chi phí hoặc tác động nghiệp vụ.
- Xử lý webhook và event delivery có retry.
- Provision/deprovision user hoặc workload ở nhiều hệ thống.
- Chạy command bất đồng bộ từ queue.

Không nhất thiết áp dụng một idempotency table chung cho mọi GET hoặc thao tác đọc. Chọn nơi có side effect, retry không tránh khỏi và hậu quả của duplicate đủ lớn.

## 6. Idempotency key là gì?

Idempotency key là một identifier do client hoặc gateway tạo để đại diện cho một lần thao tác logic. Server dùng key này để nhận ra retry của cùng thao tác.

Key tốt cần:

- Khó đoán hoặc có entropy cao nếu client tạo ngẫu nhiên.
- Không chứa PII, password, access token hoặc dữ liệu nghiệp vụ.
- Có phạm vi sử dụng rõ ràng.
- Không dùng chung giữa các principal không liên quan.
- Không tái sử dụng cho một thao tác khác trong thời hạn retention.
- Được giới hạn kích thước và định dạng.

Client có thể tạo UUID ngẫu nhiên hoặc giá trị random đủ entropy. Key không phải secret để xác thực, nhưng không nên đưa vào log công khai hoặc dùng làm authorization credential.

### Key phải có scope

Không nên tìm record chỉ bằng key trên toàn hệ thống. Một định danh đầy đủ có thể gồm:

~~~text
scope:
  tenant_id
  principal_id
  client_id
  operation_name
  idempotency_key
~~~

Scope giúp ngăn một user vô tình hoặc cố ý dùng key của user khác, và ngăn cùng key ở endpoint khác bị coi là cùng thao tác.

Với webhook, scope có thể là provider + endpoint + event type + delivery ID. Với workload, scope có thể là service identity + operation.

## 7. Request fingerprint

Idempotency key chỉ cho biết client tuyên bố đây là cùng một thao tác. Server cần kiểm tra payload có thực sự giống request ban đầu không.

**Request fingerprint** là digest được tạo từ biểu diễn canonical của các trường có ý nghĩa nghiệp vụ.

Ví dụ transfer fingerprint nên bao gồm:

- Source account đã được xác minh từ server-side context.
- Beneficiary ID.
- Amount và currency.
- Action/operation.
- Tenant/resource.
- Transaction version hoặc các thuộc tính ảnh hưởng kết quả.

Không đưa vào fingerprint các dữ liệu thay đổi giữa retry nhưng không ảnh hưởng nghiệp vụ, ví dụ:

- Trace ID mới.
- Request timestamp mới nếu timestamp chỉ phục vụ telemetry.
- Header User-Agent.
- Authorization token đã rotate nhưng principal vẫn như cũ.
- Network IP.

Tùy API, client-supplied account ID cần được thay bằng account đã được xác định sau authorization. Không hash payload thô rồi bỏ qua canonicalization; thứ tự JSON key, số dạng 1 và 1.0, Unicode normalization hoặc giá trị mặc định có thể làm hai request tương đương tạo digest khác nhau.

### Canonicalization

Một cách làm:

1. Parse request theo schema đã định.
2. Xác thực kiểu dữ liệu, range và required fields.
3. Lấy principal, tenant, account và permission từ trusted server context.
4. Chuẩn hóa amount/currency/identifier theo quy tắc nghiệp vụ.
5. Tạo representation có thứ tự trường xác định.
6. Tính HMAC hoặc hash digest theo threat model.

Ví dụ:

~~~text
canonical_transfer_v1:
  tenant = tenant-9
  principal = user-104
  source = account-A104
  beneficiary = beneficiary-B205
  amount_minor_units = 250000
  currency = VND
  operation = TRANSFER
  version = 1
~~~

Version trong canonical format giúp thay đổi schema có kiểm soát. Nếu đổi thuật toán canonicalization, server cần biết record cũ được tạo bằng version nào.

## 8. Luồng idempotency cơ bản

Một flow điển hình:

1. Xác thực request và lấy principal/client/tenant từ context đáng tin.
2. Kiểm tra authorization cho action/resource.
3. Validate request và tạo fingerprint canonical.
4. Tìm hoặc tạo record theo idempotency scope.
5. Nếu chưa có record, claim key nguyên tử và xử lý nghiệp vụ.
6. Lưu kết quả cùng trạng thái hoàn tất.
7. Trả response.
8. Nếu request lặp cùng key và fingerprint, trả kết quả đã lưu.
9. Nếu cùng key nhưng fingerprint khác, trả conflict.

~~~mermaid
flowchart TD
    A["Receive request"] --> B["Authenticate and authorize"]
    B --> C["Validate and canonicalize payload"]
    C --> D["Compute request fingerprint"]
    D --> E["Lookup scoped idempotency key"]
    E --> F{"Record exists?"}
    F -->|"No"| G["Atomically claim key"]
    G --> H["Execute business operation"]
    H --> I["Persist result and COMPLETED state"]
    F -->|"Yes"| J{"Fingerprint matches?"}
    J -->|"No"| K["409 Conflict"]
    J -->|"Yes, completed"| L["Return stored result"]
    J -->|"Yes, in progress"| M["Return pending/retry guidance"]
    I --> N["Respond"]
    L --> N
~~~

Authentication và authorization vẫn cần được kiểm tra ở mỗi request retry. Không nên trả dữ liệu kết quả cũ cho principal khác chỉ vì họ đoán hoặc biết key.

## 9. State machine của idempotency record

Một record có thể có các trạng thái:

| Trạng thái | Ý nghĩa | Hành vi với retry |
|---|---|---|
| IN_PROGRESS | Key đã được claim, thao tác đang chạy | Trả pending, chờ hoặc cung cấp retry-after |
| COMPLETED | Kết quả nghiệp vụ đã được commit | Trả kết quả đã lưu |
| FAILED_FINAL | Thao tác thất bại và kết quả lỗi được lưu theo policy | Trả lại lỗi tương ứng |
| RETRYABLE | Hệ thống xác định chưa có side effect và có thể thử lại | Cho phép worker/client tiếp tục theo quy tắc |
| EXPIRED | Hết retention window | Không còn bảo đảm dedup theo record đó |

Không phải mọi exception đều có thể đánh dấu RETRYABLE. Nếu service gọi payment provider, provider đã xử lý nhưng response bị mất, hệ thống không biết side effect đã xảy ra hay chưa. Khi đó cần reconciliation bằng provider transaction ID hoặc idempotency key phía provider.

### Trạng thái terminal và lỗi

Phải phân biệt:

- Lỗi validate trước khi claim key: có thể sửa request và gửi key mới theo contract.
- Lỗi authorization: không lưu kết quả thành công; mỗi retry vẫn phải kiểm tra quyền.
- Lỗi nghiệp vụ xác định trước side effect: có thể lưu FAILED_FINAL để retry cùng key nhận cùng kết quả.
- Timeout không rõ side effect: giữ trạng thái pending/unknown và reconcile; không tự chạy lại mù quáng.
- Lỗi hạ tầng trước khi bắt đầu xử lý: có thể cho retry sau khi xác minh chưa có side effect.

## 10. Atomicity và xử lý request đồng thời

Hai request giống nhau có thể đến gần như cùng lúc. Nếu code làm:

1. SELECT kiểm tra key chưa tồn tại.
2. Cả hai request đều thấy không có record.
3. Cả hai cùng tạo payment.

thì idempotency bị phá vỡ.

Giải pháp:

- Unique constraint trên scope đầy đủ của key.
- Insert/claim key bằng thao tác atomic.
- Transaction DB bao trùm việc tạo business record và hoàn tất idempotency record khi có thể.
- Row lock hoặc conditional update để chỉ một worker sở hữu thao tác.
- Request còn lại đọc trạng thái IN_PROGRESS/COMPLETED thay vì thực hiện side effect.

~~~sql
CREATE TABLE idempotency_record (
    tenant_id          VARCHAR(100) NOT NULL,
    principal_id       VARCHAR(200) NOT NULL,
    operation_name     VARCHAR(100) NOT NULL,
    key_hash           VARCHAR(128) NOT NULL,
    request_fingerprint VARCHAR(128) NOT NULL,
    state              VARCHAR(24) NOT NULL,
    response_status    INTEGER,
    response_body      TEXT,
    created_at         TIMESTAMP NOT NULL,
    expires_at         TIMESTAMP NOT NULL,
    completed_at       TIMESTAMP,
    PRIMARY KEY (
        tenant_id,
        principal_id,
        operation_name,
        key_hash
    )
);
~~~

DDL minh họa; kiểu dữ liệu, collation, index và transaction isolation cần phù hợp DB thực tế. Không đặt key_hash làm unique toàn cục nếu key scope có tenant/principal/operation.

### Claim key atomically

Có thể dùng INSERT với unique constraint và xử lý duplicate-key conflict. Chỉ transaction insert thành công mới được quyền thực hiện nghiệp vụ. Request thua race đọc record đã tồn tại và áp dụng quy tắc fingerprint/state.

Không dựa vào distributed lock tự chế nếu DB unique constraint và transaction có thể giải quyết. Nếu dùng lock phân tán, cần xử lý lease expiry, owner token, fencing token và crash để tránh worker cũ tiếp tục commit sau khi lock hết hạn.

## 11. Database transaction và business side effect

Nếu idempotency record và business mutation nằm trong cùng database, nên thực hiện trong một transaction:

1. Claim key.
2. Tạo business record.
3. Lưu response/result reference.
4. Đánh dấu COMPLETED.
5. Commit.

Nếu transaction rollback, cả business record và idempotency completion cũng rollback. Nếu commit thành công nhưng response bị mất, retry sẽ thấy COMPLETED và trả kết quả cũ.

Không lưu COMPLETED trước khi business mutation commit. Nếu record báo thành công nhưng payment không được tạo, retry sẽ không sửa được trạng thái.

Với side effect bên ngoài database, transaction đơn lẻ không đủ.

## 12. External side effects: transactional outbox và saga

Ví dụ tạo payment trong database rồi gọi payment provider:

- DB transaction tạo payment intent và outbox event.
- Worker đọc outbox và gọi provider bằng idempotency key ổn định.
- Provider trả provider transaction ID.
- Worker lưu kết quả và đánh dấu event đã xử lý.
- Nếu worker crash sau khi provider xử lý nhưng trước khi ghi DB, worker retry cùng provider key để provider deduplicate.

~~~mermaid
sequenceDiagram
    autonumber
    participant API as Application API
    participant DB as Database
    participant W as Outbox worker
    participant PSP as Payment provider

    API->>DB: Claim idempotency key + create payment intent + outbox
    DB-->>API: Commit
    API-->>API: Return accepted/pending
    W->>DB: Read pending outbox event
    W->>PSP: Create payment with stable provider idempotency key
    PSP-->>W: Provider payment ID/result
    W->>DB: Store result and mark outbox complete
    Note over W,PSP: Retry uses same provider key after timeout
~~~

Outbox bảo đảm event được ghi cùng business transaction, nhưng worker có thể giao event nhiều lần. Consumer và provider vẫn cần idempotency/deduplication.

Với workflow nhiều hệ thống, saga có thể dùng bước bù trừ (compensation) khi không thể rollback side effect đã xảy ra. Compensation không xóa lịch sử; nó tạo một thao tác nghiệp vụ ngược lại.

Không tuyên bố exactly-once delivery trên mạng phân tán chỉ bằng một idempotency table. Thực tế thường là at-least-once delivery kết hợp idempotent processing và reconciliation.

## 13. Retry, timeout và crash recovery

Client cần biết khi nào retry:

| Tình huống | Hành vi gợi ý |
|---|---|
| Không kết nối được trước khi request tới server | Retry cùng key |
| Server trả validation error trước khi xử lý | Sửa request theo contract; dùng key mới nếu payload đã đổi |
| Server trả COMPLETED nhưng response bị mất | Retry cùng key để nhận lại kết quả |
| Server báo IN_PROGRESS | Chờ hoặc poll trạng thái; không tạo key mới |
| Server timeout, trạng thái không rõ | Retry cùng key hoặc query operation status |
| Provider timeout sau khi có thể đã xử lý | Retry cùng provider key hoặc reconcile |
| Server crash trước commit | Transaction rollback; key có thể được claim lại theo policy |
| Server crash sau commit trước response | Retry trả kết quả đã lưu |

Client không nên tự sinh key mới mỗi lần retry. Làm vậy biến một thao tác logic thành nhiều thao tác riêng biệt.

### Retry budget

Thiết kế retry cần:

- Exponential backoff và jitter.
- Giới hạn số lần và tổng thời gian retry.
- Respect Retry-After khi server cung cấp.
- Không retry lỗi xác định như 400/401/403/409 một cách vô hạn.
- Giữ key ổn định cho cùng một thao tác logic.
- Dùng operation ID để tra cứu trạng thái khi request bất đồng bộ.

## 14. Response replay và dữ liệu nhạy cảm

Khi request lặp, server có thể trả lại response đã lưu. Nhưng không phải mọi response đều nên lưu nguyên văn.

Lưu ý:

- Không lưu access token, refresh token, password, OTP hoặc recovery code trong response snapshot.
- Không lưu thông tin cá nhân vượt quá nhu cầu.
- Với response có dữ liệu nhạy cảm, xác thực và authorization lại trước khi trả.
- Có thể lưu resource ID/status thay vì body đầy đủ rồi dựng response hiện tại theo quyền.
- Định nghĩa rõ response status/header nào được replay.
- Không replay header có giá trị thay đổi như Date, trace ID hoặc Set-Cookie nếu không phù hợp.
- Không trả response của principal khác dù cùng idempotency key.

Idempotency record là dữ liệu bảo mật: cần access control, encryption at rest khi phù hợp, retention và audit.

## 15. Retention và hết hạn key

Idempotency record không nhất thiết lưu mãi. Retention phải dài hơn khoảng retry tối đa và phù hợp vòng đời nghiệp vụ.

Ví dụ:

- API đơn giản: vài giờ hoặc một ngày tùy contract.
- Thanh toán/đơn hàng: có thể cần thời gian dài hơn theo quy tắc đối soát.
- Webhook: retention theo provider retry window và event history.
- Credential issuance: có thể giữ operation ID/audit record lâu hơn key dedup record.

Khi record hết hạn:

- Không còn bảo đảm request cũ sẽ được deduplicate.
- Client không nên dùng lại key cũ cho một thao tác mới.
- Hệ thống cần định nghĩa cách xử lý key reuse sau expiry.
- Với giao dịch tài chính, business unique reference có thể cần giữ lâu hơn idempotency cache.

Không xóa record IN_PROGRESS chỉ vì TTL ngắn nếu worker vẫn đang xử lý. Dùng lease/heartbeat và reconciliation để xác định worker chết hay operation còn pending.

## 16. Idempotency trong credential issuance và authentication

Idempotency hữu ích cho thao tác xác thực có side effect:

- Tạo recovery grant.
- Cấp API key hoặc certificate.
- Đăng ký authenticator.
- Xoay refresh token.
- Tạo OAuth authorization artifact hoặc client registration.
- Gửi notification có chi phí.

Ví dụ, client retry yêu cầu cấp API key vì response đầu tiên bị mất. Nếu không idempotent, server có thể tạo nhiều key active mà client không biết secret của các key cũ.

Thiết kế:

- Key scope gắn với principal/client và operation.
- Fingerprint gồm credential type, purpose, audience, scopes và policy version.
- Record lưu key ID/resource ID và trạng thái, không lưu plaintext secret.
- Secret chỉ hiển thị một lần; nếu response bị mất sau issuance, không thể phát lại secret plaintext từ verifier hash.
- Có thể trả trạng thái đã cấp và yêu cầu revoke key không nhận được, hoặc dùng flow activation/rotation mới có kiểm soát.

Đây là khác biệt quan trọng: idempotency của nghiệp vụ không có nghĩa server luôn có thể replay một secret chỉ hiển thị một lần. Contract phải định nghĩa cách xử lý khi response chứa secret bị mất.

## 17. Webhook idempotency và event deduplication

Webhook provider thường retry khi consumer timeout hoặc trả non-2xx. Consumer cần xác minh chữ ký/timestamp trước, sau đó deduplicate theo event ID hoặc delivery ID.

Quy trình:

1. Xác minh chữ ký theo provider secret/key.
2. Kiểm tra timestamp/replay window nếu protocol hỗ trợ.
3. Lấy event ID từ payload/header đã xác minh.
4. Claim event ID atomically trong phạm vi provider/account.
5. Kiểm tra event type và schema.
6. Áp dụng business update idempotently.
7. Ghi kết quả và trả acknowledgment.

Không deduplicate chỉ theo raw payload hash; hai event hợp lệ khác nhau có thể có payload giống nhau. Ưu tiên event ID ổn định do provider cấp.

Webhook signature validation và event dedup là hai lớp khác nhau. Một event ID đã xử lý không cho phép bỏ qua xác minh chữ ký cho request mới.

## 18. Idempotency và replay attack

Attacker có thể cố ý phát lại request hợp lệ. Idempotency giúp hạn chế side effect lặp, nhưng không phải replay defense đầy đủ:

- Nếu endpoint không xác thực principal, attacker vẫn có thể gửi request đầu tiên.
- Nếu idempotency scope quá rộng, attacker có thể gây key collision hoặc làm request hợp lệ nhận kết quả sai.
- Nếu record hết hạn, request cũ có thể tạo side effect lần nữa.
- Nếu endpoint trả lại response nhạy cảm cho người không có quyền, key có thể bị dùng để lấy dữ liệu.
- Nếu request thay đổi payload mà server không fingerprint, cùng key có thể được dùng cho nội dung khác.

Với authentication proof, vẫn cần nonce, challenge, timestamp, audience, signature, one-time consumption và replay cache theo giao thức.

Với nghiệp vụ tài chính, ngoài idempotency key còn nên có business invariant như transaction reference duy nhất, số dư/limit check, transaction state machine và reconciliation.

## 19. Abuse controls và bảo vệ kho idempotency

Idempotency store có thể bị lạm dụng để tăng tải hoặc chiếm dung lượng:

- Gửi vô số key ngẫu nhiên để tạo record.
- Gửi cùng key với payload khác nhau để gây conflict.
- Giữ nhiều operation ở IN_PROGRESS.
- Dùng key lớn hoặc request body lớn để tăng chi phí hashing/storage.
- Cố đoán key hoặc khai thác response replay.
- Tấn công race để tạo nhiều side effect.

Kiểm soát:

- Giới hạn kích thước và charset của key.
- Rate limit theo principal/client/tenant và operation.
- Giới hạn số record pending và thời gian lease.
- Giới hạn payload size và canonicalization cost.
- TTL/retention và cleanup có kiểm soát.
- Unique constraint và atomic claim.
- Monitor tỷ lệ conflict, duplicate, pending lâu và storage growth.
- Không trả response snapshot nếu authorization hiện tại không cho phép.
- Bảo vệ endpoint status lookup khỏi enumeration.

Không dùng IP làm scope duy nhất; NAT và proxy khiến nhiều người chia sẻ IP. Principal/client/tenant đã xác minh là các thành phần quan trọng của scope.

## 20. Java/Spring: mô hình dữ liệu idempotency

Ví dụ record:

~~~java
enum IdempotencyState {
    IN_PROGRESS,
    COMPLETED,
    FAILED_FINAL,
    RETRYABLE
}

record IdempotencyScope(
    String tenantId,
    String principalId,
    String operation,
    String keyHash
) {}

record IdempotencyRecord(
    IdempotencyScope scope,
    String requestFingerprint,
    IdempotencyState state,
    String resourceId,
    Integer responseStatus,
    Instant createdAt,
    Instant expiresAt
) {}

sealed interface ClaimResult {
    record Acquired(IdempotencyRecord record) implements ClaimResult {}
    record Existing(IdempotencyRecord record) implements ClaimResult {}
    record PayloadConflict() implements ClaimResult {}
}
~~~

### Claim và xử lý transfer

~~~java
@Service
class TransferCommandService {
    private final IdempotencyRepository idempotency;
    private final TransferRepository transfers;
    private final TransferAuthorizer authorizer;
    private final FingerprintService fingerprints;

    TransferCommandService(
            IdempotencyRepository idempotency,
            TransferRepository transfers,
            TransferAuthorizer authorizer,
            FingerprintService fingerprints) {
        this.idempotency = idempotency;
        this.transfers = transfers;
        this.authorizer = authorizer;
        this.fingerprints = fingerprints;
    }

    @Transactional
    TransferResult create(
            AuthenticatedPrincipal principal,
            String idempotencyKey,
            CreateTransferRequest request) {

        TransferIntent intent = authorizer.authorizeAndResolve(
            principal, request
        );
        String fingerprint = fingerprints.forTransfer(
            principal, intent
        );
        String keyHash = fingerprints.hashKey(idempotencyKey);

        ClaimResult claim = idempotency.claim(
            principal.tenantId(),
            principal.id(),
            "CREATE_TRANSFER",
            keyHash,
            fingerprint
        );

        if (claim instanceof ClaimResult.PayloadConflict) {
            throw new IdempotencyPayloadConflictException();
        }

        if (claim instanceof ClaimResult.Existing existing) {
            IdempotencyRecord record = existing.record();
            return switch (record.state()) {
                case COMPLETED -> transfers.findResult(record.resourceId());
                case IN_PROGRESS -> throw new OperationInProgressException();
                case FAILED_FINAL -> throw new StoredOperationFailureException();
                case RETRYABLE -> throw new RetryPolicyRequiredException();
            };
        }

        Transfer transfer = transfers.create(intent);
        idempotency.complete(
            principal.tenantId(),
            principal.id(),
            "CREATE_TRANSFER",
            keyHash,
            transfer.id()
        );
        return TransferResult.from(transfer);
    }
}
~~~

Đây là ví dụ khung. Repository claim phải dùng unique constraint/atomic insert và so khớp fingerprint trong transaction. Khi record mới được tạo, business mutation và complete record phải commit cùng transaction nếu cùng database. Không dùng SELECT-then-INSERT không khóa vì có race. Existing result chỉ được trả sau khi xác minh principal, authorization và quyền đọc resource hiện tại.

### Fingerprint canonicalization

~~~java
record TransferIntent(
    String sourceAccountId,
    String beneficiaryId,
    long amountMinorUnits,
    String currency,
    String tenantId
) {}

String canonical(TransferIntent intent) {
    return String.join("|",
        intent.tenantId(),
        intent.sourceAccountId(),
        intent.beneficiaryId(),
        Long.toString(intent.amountMinorUnits()),
        intent.currency(),
        "TRANSFER_V1"
    );
}
~~~

Đây là minh họa đơn giản; production nên dùng encoding có phân tách không nhập nhằng hoặc canonical serialization chuẩn. Không ghép chuỗi tùy tiện nếu giá trị có thể chứa ký tự phân cách.

## 21. Java/Spring: webhook consumer idempotent

~~~java
@Transactional
void handleWebhook(VerifiedWebhook event) {
    boolean firstDelivery = inboxRepository.insertIfAbsent(
        event.providerId(),
        event.eventId()
    );

    if (!firstDelivery) {
        return;
    }

    webhookBusinessHandler.apply(event);
    inboxRepository.markProcessed(
        event.providerId(),
        event.eventId()
    );
}
~~~

VerifiedWebhook chỉ được tạo sau khi xác minh chữ ký, timestamp và provider identity. Inbox insert cần unique constraint trên provider/event ID. Nếu business update và inbox record cùng DB, commit trong một transaction; nếu có external side effect, dùng outbox và idempotency ở consumer/provider tiếp theo.

## 22. Các sai lầm thường gặp

| Sai lầm | Hậu quả | Cách sửa |
|---|---|---|
| Client tạo key mới cho mỗi retry | Mỗi retry thành thao tác mới | Giữ key ổn định cho cùng logical operation |
| Key không có principal/tenant scope | Cross-user collision hoặc response leak | Scope theo tenant, principal, client và operation |
| Không so request fingerprint | Cùng key có thể đổi payload | Canonical fingerprint và conflict khi mismatch |
| SELECT rồi INSERT không atomic | Race tạo duplicate side effect | Unique constraint và atomic claim |
| Lưu COMPLETED trước business commit | Record nói thành công nhưng resource chưa tồn tại | Commit mutation và completion cùng transaction |
| Gọi external provider trong DB transaction rồi retry mù | Provider có thể đã xử lý trước timeout | Outbox, provider idempotency key và reconciliation |
| Coi idempotency là replay protection | Proof/token bị phát lại vẫn có thể hợp lệ | Nonce/challenge/replay cache riêng |
| Trả stored response không kiểm tra quyền | Principal khác lấy dữ liệu | Authentication/authorization mỗi retry |
| Replay raw response chứa secret | Rò token/API key/recovery code | Không snapshot secret; dùng resource reference |
| Xóa IN_PROGRESS theo TTL đơn giản | Worker còn chạy và side effect trùng | Lease/heartbeat/reconciliation |
| Retention quá ngắn | Retry muộn tạo side effect lần nữa | Retention theo retry window và nghiệp vụ |
| Retention vô hạn | Storage growth và dữ liệu không cần thiết | TTL, cleanup và archive có kiểm soát |
| Hash payload JSON thô | Equivalent request có fingerprint khác | Schema validation và canonicalization |
| Retry mọi lỗi vô hạn | Overload và duplicate risk | Retry budget, backoff, jitter, error classification |
| Key là bearer authorization | Ai biết key có thể gọi endpoint | Vẫn xác thực và kiểm tra quyền độc lập |

## 23. Ma trận kiểm thử idempotency

| Kiểm thử | Kết quả mong đợi |
|---|---|
| Request đầu tiên với key mới | Một operation được tạo |
| Cùng key, cùng principal, cùng payload sau COMPLETED | Trả cùng operation/result, không tạo side effect mới |
| Cùng key nhưng amount/beneficiary khác | Conflict, không thay đổi operation cũ |
| Cùng key ở principal khác | Không trả kết quả của principal đầu; scope tách biệt |
| Cùng key ở operation khác | Không va chạm do operation scope |
| Hai request đồng thời cùng key/payload | Chỉ một worker tạo side effect |
| Hai request đồng thời cùng key/payload khác nhau | Một request claim; request kia conflict |
| Response mất sau commit | Retry trả kết quả đã lưu |
| Process crash trước DB commit | Transaction rollback; retry xử lý theo trạng thái |
| Process crash sau commit trước response | Retry nhận lại kết quả COMPLETED |
| External provider timeout sau khi xử lý | Retry cùng provider key hoặc reconcile; không tạo payment thứ hai |
| Record IN_PROGRESS còn worker lease hợp lệ | Retry nhận pending/Retry-After |
| Worker chết và lease hết hạn | Recovery worker reconcile trước khi chạy lại |
| Key hết retention | Hành vi reuse được định nghĩa rõ; business invariant vẫn bảo vệ |
| Authorization bị thu hồi trước retry | Không trả dữ liệu nhạy cảm hoặc cho phép side effect mới |
| Stored response có secret | Test phải phát hiện; secret không được snapshot |
| Key quá dài hoặc ký tự không hợp lệ | Từ chối theo validation |
| Gửi hàng nghìn key ngẫu nhiên | Rate limit/quota bảo vệ store |
| Webhook event ID lặp | Business handler chỉ áp dụng một lần |
| Webhook chữ ký sai nhưng event ID đã tồn tại | Vẫn từ chối vì signature verification diễn ra trước dedup |
| Credential issuance response bị mất | Không tạo credential active trùng; secret one-time xử lý theo contract |
| Retry có Authorization token mới nhưng cùng principal | Vẫn nhận diện operation theo scope/fingerprint đã định nghĩa |
| Canonical payload có JSON key order khác | Fingerprint giống nếu semantics giống |
| Currency/amount representation không hợp lệ | Validation từ chối trước khi claim |

Kiểm thử cần đo số business record, ledger entry, email/SMS, provider call và event được tạo; chỉ kiểm tra HTTP status là chưa đủ.

## 24. Tình huống phân tích

### Tình huống A: payment đã commit nhưng response bị mất

Client gửi POST tạo payment. Server commit payment nhưng kết nối bị ngắt trước khi trả response. Client retry với cùng idempotency key.

**Phân tích:** server tìm record COMPLETED có cùng scope và fingerprint, xác minh authorization hiện tại rồi trả resource/result đã lưu. Không tạo payment mới.

### Tình huống B: cùng key nhưng payload thay đổi

Client gửi key K cho chuyển 100.000 VND, sau đó gửi lại key K cho 900.000 VND.

**Phân tích:** fingerprint khác nhau. Server trả conflict, giữ nguyên operation ban đầu và không thay đổi số tiền.

### Tình huống C: hai request đến đồng thời

Hai thread cùng kiểm tra key chưa tồn tại và cùng tạo lệnh chuyển tiền.

**Phân tích:** SELECT-then-INSERT không đủ. Unique constraint và atomic claim quyết định duy nhất một request sở hữu key; request còn lại đọc trạng thái.

### Tình huống D: provider đã xử lý nhưng worker timeout

Outbox worker gọi payment provider. Provider tạo giao dịch nhưng response bị mất; worker không biết kết quả.

**Phân tích:** dùng cùng provider idempotency key khi retry hoặc tra cứu bằng merchant reference. Không tạo key mới và gửi lại như payment mới. Reconcile trạng thái trước khi đánh dấu hoàn tất.

### Tình huống E: cấp API key nhưng response chứa secret bị mất

Issuance service đã tạo key, chỉ lưu verifier, nhưng client không nhận được plaintext secret do mạng lỗi.

**Phân tích:** server không thể khôi phục plaintext từ verifier. Contract cần cho biết key ở trạng thái pending/active, hỗ trợ revoke key không nhận được và cấp key mới có kiểm soát; không lưu plaintext lâu dài chỉ để replay response.

## 25. Quy trình thiết kế và vận hành

Trước khi triển khai idempotency, hãy xác định:

1. Logical operation nào cần deduplicate và side effect nào có thể bị tạo trùng?
2. Ai tạo idempotency key và key có entropy/format/size phù hợp không?
3. Scope gồm tenant, principal, client và operation nào?
4. Request fingerprint gồm các field nghiệp vụ nào và được canonicalize ra sao?
5. Cùng key khác fingerprint trả conflict như thế nào?
6. State machine có IN_PROGRESS, COMPLETED, FAILED_FINAL, RETRYABLE và EXPIRED không?
7. Claim key có atomic và được bảo vệ bằng unique constraint không?
8. Business mutation và idempotency completion có cùng transaction không?
9. External side effect có outbox, downstream idempotency key và reconciliation không?
10. Retry/timeout/crash được phân loại ra sao; client giữ key ổn định thế nào?
11. Response snapshot có chứa secret hoặc dữ liệu không được phép replay không?
12. Retention, TTL, cleanup và key reuse policy là gì?
13. Authorization có được kiểm tra lại trước khi replay response không?
14. Có rate limit, quota và giám sát pending/conflict/storage growth không?
15. Có diễn tập duplicate delivery, race, process crash và provider timeout không?

## 26. Ghi nhớ trọng tâm

- **Idempotency làm retry an toàn về mặt side effect.** Cùng một logical operation không tạo kết quả nghiệp vụ trùng.
- **Idempotency khác replay protection.** Vẫn cần authentication, authorization, nonce/challenge và replay defense theo giao thức.
- **Key phải có scope và fingerprint.** Cùng key khác payload phải conflict; không được âm thầm thay đổi thao tác cũ.
- **Atomic claim là bắt buộc khi có concurrency.** Dùng unique constraint/transaction thay cho SELECT-then-INSERT không khóa.
- **Business mutation và idempotency completion nên commit cùng transaction** khi cùng database.
- **External side effect cần outbox, downstream key và reconciliation.** Mạng phân tán thường là at-least-once kết hợp idempotent processing.
- **Timeout không đồng nghĩa thất bại.** Nếu side effect chưa rõ, giữ trạng thái pending/unknown và reconcile trước khi chạy lại.
- **Response replay vẫn cần authorization.** Không để key trở thành credential hoặc đường rò dữ liệu.
- **Retention và retry contract phải rõ ràng.** Hết record có thể mất bảo đảm dedup; business invariant có thể cần tồn tại lâu hơn.
- **Credential issuance cần xử lý secret one-time riêng.** Không thể replay plaintext secret nếu hệ thống chỉ lưu verifier.

Idempotency là một hợp đồng giữa client, API, database và các hệ thống downstream. Khi key được ràng buộc với đúng principal và payload, claim được thực hiện nguyên tử, kết quả được lưu đúng thời điểm và side effect bên ngoài có cơ chế đối soát, retry có thể an toàn mà không biến một thao tác thành nhiều giao dịch.
