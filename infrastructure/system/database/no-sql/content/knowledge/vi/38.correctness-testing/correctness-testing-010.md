# Kiểm thử idempotency khi cùng yêu cầu được gửi lại

Một ứng dụng Java gửi lệnh `POST /orders/O17/confirm` tới dịch vụ sử dụng NoSQL. Database đã ghi trạng thái `CONFIRMED`, trừ một suất hàng tồn và tạo sự kiện gửi thông báo. Ngay sau lúc commit, kết nối mạng bị cắt trước khi HTTP response đến client. Client không biết lệnh thành công hay thất bại nên gửi lại **chính yêu cầu đó**. Nếu backend thực thi lại toàn bộ logic, số lượng tồn kho có thể bị trừ hai lần, Order có hai lịch sử xác nhận, và người mua nhận hai thông báo.

Tình huống này không hiếm: timeout, retry của HTTP client/gateway, leader failover, worker restart, message redelivery và duplicate delivery từ queue đều có thể làm **một ý định nghiệp vụ xuất hiện nhiều lần**. Trong các hệ phân tán, “đã gọi một lần” không đồng nghĩa “server đã thực thi một lần”; “client không nhận được phản hồi” cũng không đồng nghĩa “database chưa commit”.

**Idempotency** cho phép cùng một thao tác logic được yêu cầu lặp lại mà trạng thái/hiệu ứng nghiệp vụ cuối cùng vẫn tương đương việc áp dụng thao tác một lần. Nhưng chỉ thêm `Idempotency-Key` vào header **không đủ**; phải thiết kế nơi lưu bản ghi chống trùng, thao tác nguyên tử với dữ liệu nghiệp vụ, thời hạn giữ khóa, cách xử lý xung đột nội dung và hành vi khi có lỗi ở từng ranh giới.

Trong chương **Kiểm thử tính đúng** của module **Database No SQL**, bài học đi từ định nghĩa đến phương pháp chứng minh: **lệnh nào được coi là cùng yêu cầu, oracle nào xác nhận đúng, những lịch biểu cạnh tranh nào phải tạo ra, và cách fault injection tại ranh giới commit/ACK**. Ví dụ minh họa Java, JUnit, MongoDB, DynamoDB, Cosmos DB, Cassandra/ScyllaDB, Redis, Firestore và các đường truyền sự kiện.

> **Quy tắc kiểm thử:** Không khẳng định idempotency chỉ vì hai lần gọi đều trả `200 OK`. Phải chứng minh **chỉ một tác động nghiệp vụ có thẩm quyền được commit**, các lần lặp trả kết quả theo hợp đồng và không tạo side effect bổ sung — kể cả khi commit xảy ra nhưng ACK bị mất.

## 1. Định nghĩa đúng phạm vi idempotency

Một hàm `f` idempotent về trạng thái thường thỏa:

\[
f(f(s))=f(s).
\]

Đây là mô hình lý tưởng; trong API thực tế phải nêu rõ **trạng thái nào**, **hiệu ứng nào** và **trong khoảng thời gian nào**. Một request có thể tạo log truy cập ở mỗi lần nhận mà vẫn idempotent về nghiệp vụ, nếu logging đó không phải side effect mà hợp đồng yêu cầu chỉ một lần.

### 1.1. Idempotent operation khác duplicate message delivery

Một message có thể được gửi/nhận mười lần nhưng business command chỉ được áp dụng một lần. Không cần bảo đảm mạng chỉ truyền một bản.

### 1.2. Idempotency khác “server không làm gì”

Lần đầu có thể thay đổi Order từ `NEW` sang `CONFIRMED`; các lần tiếp theo nhận cùng command có thể trả receipt đã lưu mà không làm thay đổi lần nữa.

### 1.3. Idempotency khác “cùng trạng thái nhìn thấy”

Nếu hai lần trừ tồn kho `-1` rồi một job khác bù `+1`, trạng thái cuối có thể tình cờ bằng đúng, nhưng side effect đã xảy ra hai lần. Test phải kiểm ledger, events hoặc authoritative receipts, không chỉ tổng hiện tại.

### 1.4. Không nhất thiết cùng byte HTTP response

Tùy hợp đồng, lần retry có thể nhận cùng `orderId/result` và `200`, hoặc `202` khi lệnh còn xử lý. **Bất biến nghiệp vụ** phải giữ; nếu API cam kết replay chính xác status/body thì test thêm điều đó.

### 1.5. “Exactly once” cần được giới hạn

Không nên tuyên bố exactly-once end-to-end chỉ vì database hỗ trợ transaction. Một hệ thường bảo đảm **at-least-once delivery + at-most-once committed business effect trong một phạm vi key/thời hạn/authority đã định nghĩa**. External payment/email cần giao thức riêng.

## 2. Các thao tác idempotent tự nhiên và không tự nhiên

| Thao tác | Gửi lại có an toàn tự nhiên? | Điều cần xem |
|---|---|---|
| `set status = CONFIRMED` | Có thể, nếu điều kiện/side effect đúng | Trạng thái chuyển, event, auth |
| `balance = 100` | Có về giá trị, nhưng có concurrency risk | Lost update, version |
| `balance += 100` | **Không** | Mỗi retry cộng thêm |
| `stock -= 1` | **Không** | Mỗi retry trừ thêm |
| `create order with new random ID` | **Không** | Mỗi retry tạo order khác |
| `create order using stable business ID` | Có thể | Conditional insert/unique key |
| `append event with random eventId` | **Không** | Event trùng |
| `upsert same document` | Phụ thuộc | Version, timestamps, triggers |
| `delete by ID` | Thường hội tụ về absent | Audit, deletion effects, version |
| `charge payment` | **Không** nếu provider không deduplicate | Provider idempotency/reconciliation |

### 2.1. `PUT` không được tự động coi là an toàn

HTTP method có semantics được thiết kế, nhưng code có thể gửi email hay cộng counter sau mỗi PUT. Test behavior thực, không suy từ tên method.

### 2.2. Conditional write có thể ngăn trạng thái lặp nhưng vẫn sinh side effects

Nếu cập nhật `status` chỉ khi `NEW`, request retry bị từ chối bởi condition; nhưng nếu email được gửi **trước** conditional write thì đã có duplicate mail.

### 2.3. Business uniqueness khác idempotency key

Một `orderNumber` unique có thể chặn hai Orders trùng số, nhưng không nói hai attempts mang nội dung khác nhau có cùng một ý định hay không. Cần contract riêng cho request identity.

### 2.4. Đừng giả định mọi retry đều là duplicate

Người dùng có thể cố ý mua hai món giống nhau hai lần. Hai commands cùng payload nhưng **khác request IDs** có thể là hai nghiệp vụ hợp lệ.

## 3. Trường hợp nền: mất ACK sau commit

~~~mermaid
sequenceDiagram
    participant C as Client
    participant A as Java API
    participant D as NoSQL DB
    C->>A: POST confirm, key=K
    A->>D: Atomic business commit + receipt K
    D-->>A: COMMITTED
    Note over A,C: Network response lost
    C->>A: Retry same key K
    A->>D: Lookup existing receipt K
    D-->>A: Already committed, result R
    A-->>C: R, no second business effect
~~~

### 3.1. Client quan sát timeout không kết luận được outcome

Có thể request chưa tới server, đã tới nhưng fail trước commit, commit thành công nhưng response mất, hoặc server đang xử lý. Test cần bao trùm các nhánh.

### 3.2. Nếu receipt không được ghi cùng business mutation

Database có thể cập nhật Order nhưng receipt chưa lưu; retry không thấy receipt và thực hiện lại. Đây là điểm lỗi rất phổ biến của thiết kế hai bước.

### 3.3. Test với lỗi đúng vị trí

Chặn **response sau khi commit được xác nhận ở nguồn**, không chỉ ném exception trước khi gọi database. Mục tiêu là mô phỏng ambiguous outcome thật.

### 3.4. Oracle không phải HTTP 200

Kiểm Order version, số decrements, số ledger entries, số outbox events và receipt. Một response hợp lệ nhưng stock bị trừ hai lần vẫn FAIL.

## 4. Xác định “cùng yêu cầu” một cách chặt chẽ

Một lệnh ví dụ:

~~~json
{
  "orderId": "O17",
  "operation": "CONFIRM",
  "expectedVersion": 4,
  "paymentMethodRef": "P1"
}
~~~

Request header:

~~~text
Idempotency-Key: 20ef1d16-7789-4c63-b2ad-3d49005dbdc9
~~~

### 4.1. Cùng key, cùng payload

Được coi là cùng command trong scope đã định; response theo receipt/status cũ, không áp dụng lại business effect.

### 4.2. Cùng key, khác payload

Đây là **key reuse conflict**, không phải lệnh lặp hợp lệ. Server nên từ chối với mã lỗi ổn định (ví dụ `409 Conflict`) theo API contract; không lấy payload mới ghi đè nghĩa cũ.

### 4.3. Khác key, cùng payload

Theo idempotency dựa trên key, đây có thể là hai commands khác nhau. Nếu domain không cho tạo hai Orders với một external order ID, cần thêm business uniqueness/authority.

### 4.4. Scope của key

Định danh không nên là `key` toàn hệ nếu user có thể đoán trùng. Một namespace phù hợp có thể là `(authenticatedTenantId, operationType, idempotencyKey)` và gắn thêm caller principal hoặc resource nếu hợp đồng yêu cầu.

### 4.5. Đừng tin tenantId trong body

Scope tenant phải lấy từ principal đã xác thực/ủy quyền, không để client chỉ định namespace của tenant khác.

## 5. Fingerprint payload: khi nào hai request giống nhau?

Nhiều hệ lưu fingerprint/hash của semantic payload cạnh key. Cần quy ước ổn định: fields nào nằm trong fingerprint, kiểu giá trị, null/missing, normalization và thứ tự.

### 5.1. JSON serialization không luôn canonical

Hai JSON objects:

~~~json
{"orderId":"O17","operation":"CONFIRM"}
~~~

~~~json
{"operation":"CONFIRM","orderId":"O17"}
~~~

có cùng nghĩa trong một API nhưng byte text khác nhau. Hash raw JSON string có thể báo conflict sai.

### 5.2. Chọn canonical representation

Parse vào DTO typed; tạo fingerprint từ các fields business quan trọng theo thứ tự cố định, có type/length framing hoặc canonical JSON có version. Không nối chuỗi mơ hồ như `tenantId + orderId` nếu không có separators/framing chặt.

### 5.3. Loại fields không quyết định lệnh

`traceId`, timestamp gateway, user-agent có thể khác khi retry. Nếu chúng không thay nghĩa, không nên khiến fingerprint khác. Ngược lại, amount/currency/orderId phải được bao gồm.

### 5.4. Amount và Unicode

Dùng minor units/integer hoặc Decimal chuẩn; xác định `100.0` và `100.00` có cùng nghĩa hay không. Unicode normalization cho product/user data cũng cần policy rõ.

### 5.5. Hash không thay authorization

Một fingerprint khớp không chứng minh caller được phép xem receipt của người khác. Lookup receipt cần quyền và namespace như business operation.

## 6. Contract nên nói rõ kết quả retry

| Request | Trạng thái nguồn | Kỳ vọng |
|---|---|---|
| Key K mới + payload P | Chưa có receipt | Áp dụng một lần |
| K + P lặp sau success | Đã COMMITTED | Trả recorded result, không ghi thêm |
| K + P lặp lúc đang xử lý | IN_PROGRESS | Bounded wait hoặc 202/409 theo policy |
| K + Q khác P | Đã có K | Conflict, không ghi Q |
| Key K2 + P | Không trùng K | Lệnh mới hoặc domain uniqueness check |
| K sau process restart | Receipt durable | Vẫn deduplicate |
| K sau receipt expiry | Phụ thuộc policy | Có thể bị coi mới; phải quản rủi ro |
| Tenant B dùng K của A | Namespace tách | Không nhìn/thay receipt của A |
| K với business validation fail | Không commit nghiệp vụ | Cách lưu failure được định nghĩa |

### 6.1. Lưu response hay chỉ result identifier?

Có thể lưu status/body đã canonicalize, hoặc resourceId/resultCode rồi reconstruct response. Nếu reconstruct từ state hiện tại, retry có thể trả version khác; test theo contract đã chọn.

### 6.2. Business failure có cache không?

Nếu confirm Order bị từ chối do thiếu stock, hệ có thể lưu một terminal failure để key K không đổi nghĩa, hoặc cho retry khi trạng thái thay đổi. Quyết định là **domain/API contract**, không có một đáp án chung.

### 6.3. Lỗi 5xx/throttling khác terminal result

Không cache mọi exception thành “FAILED vĩnh viễn” nếu thao tác chưa commit. Nhưng cũng không replay mutation mù nếu outcome unknown. Cần resolve receipt/authority.

### 6.4. HTTP status không là source of truth

Một `500` sau database commit không có nghĩa được phép gửi một lệnh nghiệp vụ mới. Client retry giữ nguyên key, server resolve existing command.

## 7. Mô hình receipt và trạng thái xử lý

Một record nhận diện command:

~~~json
{
  "tenantId": "T1",
  "operation": "CONFIRM_ORDER",
  "idempotencyKey": "K",
  "payloadFingerprint": "sha256:...",
  "status": "COMMITTED",
  "result": {"orderId":"O17","newVersion":5},
  "businessEntityId": "O17",
  "createdAt": "2026-11-14T10:00:00Z",
  "expiresAt": "2026-11-21T10:00:00Z"
}
~~~

### 7.1. `PENDING` và `COMMITTED`

Một design có state machine:

~~~mermaid
flowchart LR
    NEW["ABSENT"] --> P["PENDING"]
    P --> C["COMMITTED"]
    P --> R["RECOVERABLE / RESOLVE"]
    R --> C
    P --> F["TERMINAL_REJECTED (policy)"]
~~~

Các transitions phải được hỗ trợ bởi nguyên tử hóa hoặc recovery protocol. Không đơn giản viết `PENDING`, sửa business record, rồi hy vọng update receipt luôn thành công.

### 7.2. PENDING không phải bằng chứng command chưa commit

Nếu record PENDING được tạo trước business mutation và process crash sau commit nhưng trước update receipt, retry phải reconcile, không tự commit lại.

### 7.3. Lease/fencing cho in-progress ownership

Nếu nhiều workers tranh cùng key, có thể dùng lease/epoch để chỉ một worker điều phối. Lease expiration không chứng minh worker cũ không commit; cần conditional/fencing tại source.

### 7.4. TTL và trạng thái terminal

Receipt expiry phải tuân theo business retry horizon, external provider semantics, queue redelivery horizon và legal/privacy policy. Đừng đặt TTL quá ngắn chỉ để tiết kiệm storage.

## 8. Điều kiện nguyên tử quan trọng nhất

Mục tiêu:

~~~text
Commit transaction:
    IF receipt K absent (or compatible resolved state)
    AND business preconditions hold
    THEN apply business mutation
         AND record receipt/result for K
    COMMIT ATOMICALLY
~~~

### 8.1. Vì sao check-then-write thông thường sai?

~~~text
T1: GET receipt K -> absent
T2: GET receipt K -> absent
T1: decrement stock
T2: decrement stock
T1: PUT receipt K
T2: PUT receipt K
~~~

Một receipt ở cuối **không ngăn** hai decrements. Test concurrency cần ép chính lịch biểu này xuất hiện.

### 8.2. Unique index/conditional put là primitive

Một uniqueness constraint theo `(scope,key)` hoặc conditional insert tạo điểm tranh chấp nguyên tử, nhưng business mutation cũng cần được bảo vệ cùng commit boundary hoặc giao thức có thể recover.

### 8.3. Atomic receipt riêng không tự đủ

Nếu `receipt INSERT` thành công rồi service crash trước `stock -= 1`, retry thấy receipt và trả success giả. Hãy lưu outcome đúng thời điểm hoặc mô hình PENDING có recovery/compensation rõ.

### 8.4. Transaction phạm vi phù hợp

Một số NoSQL hỗ trợ transaction nhiều documents cùng partition; một số hỗ trợ distributed transactions có giới hạn; số khác chỉ CAS trên một item. Design/test phải dựa scope và failure model thực.

### 8.5. External effect ngoài transaction

Database transaction không thể thường xuyên gói trực tiếp SMTP/payment provider trong atomic commit. Dùng outbox và idempotent consumer/provider key.

## 9. Ma trận lỗi quanh commit

| Điểm lỗi được đưa vào | Database business mutation | Receipt | Hành vi cần chứng minh |
|---|---|---|---|
| Trước khi request tới server | Không | Không | Retry có thể làm lần đầu |
| Trước transaction begin | Không | Không | Retry an toàn |
| Trong transaction trước commit | Rolled back hoặc unknown theo engine | Đồng bộ với transaction | Resolve đúng |
| Commit thành công, response DB mất | Đã commit | Đã commit nếu atomic | Retry đọc receipt, không mutate |
| DB phản hồi success, HTTP response mất | Đã commit | Đã commit | Retry trả recorded result |
| Process crash ngay sau commit | Đã commit | Đã commit | Sau restart vẫn deduplicate |
| Concurrent same-key requests | Có thể đua | Một winner | Đúng một business commit |
| Receipt expired | Phụ thuộc policy | Không còn | Ngăn duplicate theo domain nếu cần |
| CDC consumer redelivery | Source đã commit | Event/dedupe state | Projection/effect không tăng lần hai |

### 9.1. Fault injection phải nhắm đúng ranh giới

Một test chỉ ném exception trước khi lưu DB không chứng minh “mất ACK sau commit”. Cần test driver proxy/failpoint hoặc abstraction có thể ép outcome **COMMITTED nhưng caller thấy timeout**.

### 9.2. Recovery của giao dịch unknown

Một số SDK cung cấp nhãn lỗi cho transaction retry hoặc commit outcome unknown. Test phải tránh lặp lại toàn bộ business logic khi chỉ nên retry commit/resolve; hành vi tùy engine và API.

### 9.3. Không dùng wall-clock làm bằng chứng

Event xảy ra “sau 100 ms” không chứng minh commit đã trước hay sau. Dùng recorded commit/version/receipt và synchronization barriers.

## 10. Xác định oracle để test “một lần”

Đối với `reserveOneItem`:

~~~text
Initial authoritative stock: 10
N repeated attempts with same command key K

Expected:
    committed reservation count for K = 1
    stock after = 9
    associated outbox event IDs for K = 1
    receipt for K = 1
    all completed retries return same reservation ID
~~~

### 10.1. Đo ở nguồn có thẩm quyền

Đừng chỉ kiểm cache/search index; chúng có thể lag. Đọc authoritative stock/ledger/receipt với consistency phù hợp sau khi test đạt quiescence.

### 10.2. Kiểm số lần “effect” thay vì số lần gọi hàm

Handler có thể chạy lại code để tra receipt. Unit-test mock đếm `handle()` phải được gọi đúng một lần là một giả định quá mạnh và có thể sai mục tiêu. Đếm **committed mutations**.

### 10.3. Invariant về tiền

Nếu lệnh chuyển 100.000 đồng: một debit, một credit, một transfer ID, số dư bảo toàn tổng và không có posting thứ hai sau retry.

### 10.4. Invariant về Order

Order chỉ chuyển một lần từ CREATED sang CONFIRMED; một event business `ORDER_CONFIRMED` có stable eventId; không tạo 2 orders/reservations.

### 10.5. Negative oracle

Nếu payload khác dùng cùng key, **không có mutation bổ sung**; conflict được trả rõ. Đây là test quan trọng không kém duplicate-success.

## 11. Bộ kiểm thử tối thiểu ở API boundary

| ID | Chuỗi requests | Kỳ vọng |
|---|---|---|
| T01 | K,P một lần | Một commit + receipt |
| T02 | K,P hai lần tuần tự | Không tăng effect lần hai |
| T03 | K,P 100 lần tuần tự | Cùng semantic result |
| T04 | K,P đồng thời 100 clients | Một winner/commit |
| T05 | K,P rồi K,Q | Conflict, không ghi Q |
| T06 | K,P rồi K2,P | Theo business contract cho lệnh mới |
| T07 | Client timeout sau commit, retry K | Đúng một commit |
| T08 | Crash/restart giữa hai attempts | Receipt durable |
| T09 | Gateway + SDK đều retry | Không nhân effects |
| T10 | K của tenant A, tenant B dùng K | Không lộ receipt và namespace đúng |
| T11 | K với case/JSON field-order variation | Fingerprint theo policy |
| T12 | K sau TTL expiry | Hành vi được định nghĩa, không tạo effect ngoài ý định |
| T13 | Validation failure cùng K | Policy ổn định |
| T14 | Business conflict và retry | Không bỏ qua expectedVersion |
| T15 | Duplicate delivery CDC/outbox | Downstream idempotent |

### 11.1. Cùng response không đủ

Một backend có thể trả response cache nhưng worker đã thực hiện hai DB writes; cần kiểm nguồn có thẩm quyền sau requests.

### 11.2. Same-key/different-payload race

Hai requests K với payload P và Q đến đồng thời. Hệ phải cho tối đa một payload thắng và payload kia conflict, không áp dụng cả hai.

### 11.3. Timeout không phải failure chắc chắn

Test client cần retry cùng K, không tạo UUID mới mỗi lần HTTP retry. Nếu HTTP library tự thêm key theo attempt, contract bị phá.

### 11.4. Cleanup sau test

Các cases dùng sandbox dataset/tenants giả, bảo đảm không charge thật, không gửi email thật, không phá production.

## 12. Test thời gian: key sống bao lâu?

Idempotency receipts không thể giữ mãi trong mọi hệ. Nhưng TTL phải tương thích với thời gian mà một retry có thể xuất hiện.

### 12.1. TTL ngắn hơn retry horizon

Nếu receipt tồn tại 5 phút nhưng client queue offline phát lại sau 1 giờ, hệ có thể coi lệnh cũ là mới và trừ stock lần hai.

### 12.2. TTL hết không xóa business uniqueness

Với một `paymentId` hoặc `orderId` ổn định, domain uniqueness có thể ngăn duplicate lâu hơn receipt TTL. Test cả “dedupe window” và “domain invariant lifetime”.

### 12.3. TTL cleanup bất đồng bộ

Ở nhiều NoSQL, TTL expiry không có nghĩa physical deletion ngay tại giây `expiresAt`; kiểm hành vi logic theo storage contract, không phụ thuộc cron chạy đúng mili giây.

### 12.4. Clock skew

`expiresAt` nên dựa authoritative time policy, không dựa timestamp do client tự gửi. Test nhiều instances với clocks lệch và request nằm sát boundary.

### 12.5. Legal/privacy retention

Receipt có thể chứa PII hoặc serialized response. Chọn fields tối thiểu và retention policy để cân bằng dedupe với nghĩa vụ bảo vệ/xóa dữ liệu.

## 13. Test concurrency: 100 clients cùng key

Đơn giản gọi API 100 lần trong loop không mô phỏng race. Phải đồng bộ threads để nhiều requests tranh cùng receipt key.

~~~mermaid
sequenceDiagram
    participant A as Client A
    participant B as Client B
    participant R as Receipt Store
    participant D as Business Data
    A->>R: Claim key K
    B->>R: Claim key K
    R-->>A: Won claim
    R-->>B: Already claimed
    A->>D: Commit effect + receipt atomically
    B->>R: Resolve final receipt
    R-->>B: Same result
~~~

### 13.1. `CountDownLatch` để cùng xuất phát

Test dùng start gate để tất cả threads gửi đồng thời; không dùng `Thread.sleep` rồi hy vọng scheduler tạo race.

### 13.2. Ngẫu nhiên lịch biểu

Repeat test nhiều seeds/schedules, xen network delays/CPU pauses và process restarts để tìm bug hiếm.

### 13.3. Không chỉ kiểm “không exception”

Đếm receipts/commits/ledger entries; check all responses semantics, không có unhandled hangs và retry budget.

### 13.4. Parallelism phải đúng phạm vi

Nếu mỗi thread dùng một different key, test throughput chứ không test dedupe cùng key. Cần có cả positive load distinct keys để đảm bảo không khóa toàn hệ vô lý.

### 13.5. Multiple server instances

In-memory map ở một pod có thể pass unit tests nhưng fail khi requests đến hai pods. Integration test cần thực hiện qua nhiều processes với common durable authority.

## 14. Java: interface điều khiển atomic business command

Một abstraction làm rõ hợp đồng của repository:

~~~java
import java.util.Objects;

public record ConfirmOrderCommand(
    String tenantId,
    String orderId,
    String idempotencyKey,
    String payloadFingerprint,
    long expectedVersion
) {
    public ConfirmOrderCommand {
        Objects.requireNonNull(tenantId);
        Objects.requireNonNull(orderId);
        Objects.requireNonNull(idempotencyKey);
        Objects.requireNonNull(payloadFingerprint);
        if (tenantId.isBlank() || orderId.isBlank()
                || idempotencyKey.isBlank() || expectedVersion < 0) {
            throw new IllegalArgumentException("invalid command");
        }
    }
}

public record ConfirmOrderResult(
    String orderId,
    long committedVersion,
    String confirmationId
) {}

public sealed interface ConfirmOutcome
    permits Confirmed, KeyConflict, VersionConflict, InProgress {
}

public record Confirmed(ConfirmOrderResult result)
    implements ConfirmOutcome {}
public record KeyConflict() implements ConfirmOutcome {}
public record VersionConflict() implements ConfirmOutcome {}
public record InProgress() implements ConfirmOutcome {}

public interface AtomicOrderCommandStore {
    // Must enforce receipt+business effect atomicity or
    // an explicitly recoverable protocol at its authority.
    ConfirmOutcome executeOrReplay(ConfirmOrderCommand command);
}
~~~

### 14.1. Interface không tạo nguyên tử

Implementation bắt buộc dùng transaction/conditional-write primitive hoặc recoverable state machine theo NoSQL backend. Không viết `find receipt; if absent then update; save receipt` dưới vỏ cùng method rồi gọi đó là atomic.

### 14.2. Fingerprint cần được server tạo

Client gửi key, server tính canonical fingerprint từ command fields đã validate. Client-provided fingerprint không được tin như bằng chứng payload giống.

### 14.3. Scope phải trusted

`tenantId` đi vào constructor chỉ sau khi lấy từ authenticated principal/authorization; một body tùy ý không được chọn namespace.

### 14.4. `InProgress` không ngụ ý thất bại

Client có thể chờ bounded interval hoặc retry sau `Retry-After`; không gửi command với key mới.

## 15. Java: fake store cho kiểm thử hợp đồng

Một fake in-memory với `synchronized` chỉ mô phỏng **một atomic authority trong một JVM**; nó **không** là implementation production, không có durability, distributed locking hoặc network failures. Nó hữu ích để định nghĩa test oracle trước khi chạy cùng tests trên DB adapter thật.

~~~java
import java.util.HashMap;
import java.util.Map;
import java.util.concurrent.atomic.AtomicInteger;

public final class InMemoryAtomicFake
    implements AtomicOrderCommandStore {

    private record Saved(
        String fingerprint, ConfirmOrderResult result) {}

    private final Map<String, Saved> receipts = new HashMap<>();
    private final Map<String, Long> orderVersions = new HashMap<>();
    private final AtomicInteger businessCommits = new AtomicInteger();

    public synchronized void seedOrder(
            String tenantId, String orderId, long version) {
        orderVersions.put(tenantId + "/" + orderId, version);
    }

    public int committedMutations() {
        return businessCommits.get();
    }

    @Override
    public synchronized ConfirmOutcome executeOrReplay(
            ConfirmOrderCommand c) {
        String receiptKey =
            c.tenantId() + "/CONFIRM/" + c.idempotencyKey();
        Saved saved = receipts.get(receiptKey);
        if (saved != null) {
            if (!saved.fingerprint().equals(c.payloadFingerprint())) {
                return new KeyConflict();
            }
            return new Confirmed(saved.result());
        }

        String entityKey = c.tenantId() + "/" + c.orderId();
        Long current = orderVersions.get(entityKey);
        if (current == null || current != c.expectedVersion()) {
            return new VersionConflict();
        }

        long next = current + 1;
        ConfirmOrderResult result = new ConfirmOrderResult(
            c.orderId(), next, "CONFIRM-" + c.idempotencyKey());
        orderVersions.put(entityKey, next);
        receipts.put(receiptKey, new Saved(
            c.payloadFingerprint(), result));
        businessCommits.incrementAndGet();
        return new Confirmed(result);
    }
}
~~~

### 15.1. Các keys trong fake chỉ là minh họa

`tenantId + "/" + key` chưa phải binary-safe framing cho dữ liệu tùy ý; production nên dùng typed compound keys hoặc canonical encoding được định nghĩa.

### 15.2. Tại sao fake pass chưa chứng minh production đúng?

Nó sử dụng monitor lock toàn JVM, không có hai nodes, disk crash, TTL, leader failover hoặc transaction ambiguity. Integration tests phải nhắm implementation NoSQL thật.

### 15.3. Vấn đề equality và canonical fingerprint

Fake chỉ so string fingerprint do caller đưa. Trong service production phải tính fingerprint ở server từ semantic DTO, không để client tự đưa hai hashes bằng nhau cho payload khác.

## 16. JUnit: gửi cùng yêu cầu 100 lần đồng thời

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.*;
import org.junit.jupiter.api.Test;

final class DuplicateConcurrentRequestTest {
    @Test
    void commitsOnlyOnceForConcurrentDuplicates() throws Exception {
        InMemoryAtomicFake store = new InMemoryAtomicFake();
        store.seedOrder("T1", "O17", 4);

        ConfirmOrderCommand command = new ConfirmOrderCommand(
            "T1", "O17", "K-123", "hash:confirm-o17-v4", 4);

        int clients = 100;
        ExecutorService pool = Executors.newFixedThreadPool(clients);
        CountDownLatch ready = new CountDownLatch(clients);
        CountDownLatch start = new CountDownLatch(1);

        try {
            List<Future<ConfirmOutcome>> futures = new ArrayList<>();
            for (int i = 0; i < clients; i++) {
                futures.add(pool.submit(() -> {
                    ready.countDown();
                    if (!start.await(5, TimeUnit.SECONDS)) {
                        throw new IllegalStateException("gate timed out");
                    }
                    return store.executeOrReplay(command);
                }));
            }
            assertTrue(ready.await(5, TimeUnit.SECONDS));
            start.countDown();

            for (Future<ConfirmOutcome> future : futures) {
                ConfirmOutcome outcome = future.get(
                    10, TimeUnit.SECONDS);
                assertInstanceOf(Confirmed.class, outcome);
                assertEquals(5,
                    ((Confirmed) outcome).result().committedVersion());
            }
            assertEquals(1, store.committedMutations());
        } finally {
            start.countDown();
            pool.shutdownNow();
        }
    }
}
~~~

### 16.1. Ý nghĩa của test

Một trăm threads cạnh tranh cùng key; fake chỉ commit một mutation và replay cùng result. Đây là test contract/fake, **chưa phải phép thử database thật**.

### 16.2. Test integration phải chạy nhiều server instances

Thay fake bằng adapter MongoDB/DynamoDB/Cosmos/Cassandra/Redis thật trong môi trường cô lập, gửi qua API/gateway để bao gồm JSON parse, auth, retry và network path.

### 16.3. Thread count không đảm bảo đúng 100 concurrent database commits

Barrier đồng bộ điểm khởi đầu nhưng scheduler/network vẫn có biến động. Có thể dùng fault barriers ở chỗ claim receipt/commit để buộc race cụ thể.

### 16.4. Deadlock/timeouts là test outcome

Nếu test treo vì 100 requests chờ một lock vô hạn, nó không đạt. Bound waiting/deadlines và kiểm pool exhaustion.

## 17. JUnit: same-key different-payload phải xung đột

~~~java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

final class KeyReuseConflictTest {
    @Test
    void rejectsNewMeaningForOldKey() {
        InMemoryAtomicFake store = new InMemoryAtomicFake();
        store.seedOrder("T1", "O17", 4);

        ConfirmOrderCommand first = new ConfirmOrderCommand(
            "T1", "O17", "K", "hash:payload-A", 4);
        ConfirmOrderCommand changed = new ConfirmOrderCommand(
            "T1", "O17", "K", "hash:payload-B", 4);

        assertInstanceOf(Confirmed.class,
            store.executeOrReplay(first));
        assertInstanceOf(KeyConflict.class,
            store.executeOrReplay(changed));
        assertEquals(1, store.committedMutations());
    }
}
~~~

### 17.1. Thử thay field quan trọng

Đổi amount, currency, orderId, operation type hoặc expected version cùng key; server phải reject theo fingerprint policy.

### 17.2. Thử JSON field order khác nhau

Nếu contract nói nghĩa không đổi, `{"a":1,"b":2}` và `{"b":2,"a":1}` không nên bị conflict chỉ do serializer thứ tự khác.

### 17.3. Thử key collision giữa tenants

Tenant A dùng K trước, tenant B dùng K cùng payload; namespace/authorization phải độc lập, không leak result của A.

### 17.4. Test mixed requests tranh cùng key

Cho P và Q đến đúng cùng lúc, đảm bảo chỉ tối đa một payload được commit, payload còn lại nhận conflict; không cả hai được success.

## 18. Test mất response sau commit bằng fault injection

Giả định có test-only adapter/proxy có thể buộc trạng thái:

~~~text
request K
    -> database commits receipt + stock mutation
    -> fault injector drops HTTP response
client observes timeout
client retries K
    -> API replays receipt, no mutation
~~~

### 18.1. Hai pha quan sát

Sau lần đầu timeout, đọc database bằng đường kiểm thử có consistency phù hợp để chứng minh mutation thực đã commit. Sau retry, đọc lại để chứng minh commit count vẫn là 1.

### 18.2. Không mô phỏng bằng “throw trước commit”

Một test như vậy chỉ chứng minh retry sau thất bại chắc chắn; nó bỏ qua trường hợp nguy hiểm nhất: **unknown commit outcome**.

### 18.3. Fault tại response gateway

Có thể drop response ở HTTP reverse proxy sau khi service hoàn thành, không cần giả mạo database state. Đảm bảo test setup biết chắc thời điểm commit xảy ra.

### 18.4. Fault tại DB driver

Có thể tiêm connection reset sau khi server đã commit nhưng trước khi driver nhận ACK, nếu framework/test harness hỗ trợ. Đọc authoritative receipt để resolve.

### 18.5. Test nhiều lần cùng điểm lỗi

Khi client retry 3–10 lần, commit vẫn một. Test không tự tin vào thời gian ngủ hoặc việc network sẽ thất bại đúng lúc ngẫu nhiên.

## 19. Test crash/restart ở mọi điểm cắt

Một chuỗi công việc có thể:

~~~text
1. Validate command.
2. Begin transaction.
3. Record command claim/receipt.
4. Apply stock/order mutation.
5. Record outbox event.
6. Commit.
7. Build response.
8. Send HTTP response.
~~~

### 19.1. Crash trước commit

Transaction phải rollback hoặc protocol recovery xác định được state. Retry có thể thực hiện lần đầu và tạo đúng một receipt.

### 19.2. Crash sau commit trước response

Retry sau process restart phải thấy durable receipt và không tạo mutation khác. In-memory dedupe chắc chắn không đủ.

### 19.3. Crash sau ghi PENDING

Nếu thiết kế có PENDING riêng ngoài atomic transaction, cần xác định có commit hay chưa bằng authority/command log; không để PENDING kẹt mãi hoặc áp dụng hai lần.

### 19.4. Crash khi outbox chưa publish

Outbox record durable phải được publisher xử lý sau restart; không mất event. Nếu publish lặp, consumer deduplicate bằng eventId.

### 19.5. Thử process-kill thật ở integration environment

Không chỉ simulate exception; reboot/kill process có thể làm mất memory/caches nhưng database vẫn còn state, giúp phát hiện dependence vào JVM instance.

## 20. Test expired receipt và delayed replay

### 20.1. Define retention horizon

Một retry sau 10 phút, một message sau 3 ngày và một offline mobile request sau 14 ngày có thể cùng key. Contract phải quy định liệu chúng được replay hay coi là lệnh mới.

### 20.2. Test TTL boundary

Gửi K,P trước expiry, đúng lúc expiry và sau expiry (với fake clock nếu có). Tránh test timing brittle bằng `Thread.sleep(24h)`.

### 20.3. Receipt hết nhưng Order vẫn tồn tại

Domain business key/unique constraint có thể ngăn duplicate resource. Nếu một lệnh `stock -= 1` không có business uniqueness riêng, TTL hết có thể khiến trừ thêm; đó là lựa chọn rủi ro cần hiểu và test.

### 20.4. Avoid replay from archived queues

Nếu DLQ messages sau 30 ngày được replay, receipt TTL 7 ngày không đủ để bảo đảm idempotency. Có thể cần durable business event IDs hoặc ledger retention dài hơn.

## 21. Test hai lớp retry chồng nhau

~~~text
Mobile client: up to 3 attempts
API gateway: up to 2 attempts
Java HTTP client: up to 3 attempts
DB SDK: internal transient retry
~~~

### 21.1. Retry amplification

Một lệnh có thể được gửi nhiều lần hơn dự tính nếu layers retry không phối hợp. Test bằng tracing/receipt counts thay vì giả định chỉ một retry loop.

### 21.2. Mỗi attempt giữ cùng identity

Header idempotency key không được bị regenerate ở gateway/service boundary; traceId có thể thay cho từng attempt, nhưng business commandId giữ nguyên.

### 21.3. Timeout budgets

Retries phải có deadline/backoff/jitter/rate limit để tránh làm quá tải database. Idempotency giữ correctness nhưng không giải quyết retry storm về capacity.

### 21.4. Lỗi có thể retry và lỗi phải sửa đầu vào

Invalid payload, permission denied và key reuse conflict không nên retry vô hạn. Unknown outcome cần resolve; 429/503 có thể retry có budget theo contract.

### 21.5. Test sự phân loại

Mock/tiêm các response codes và network exceptions, xác nhận retry giữ key và dừng khi terminal rejection.

## 22. MongoDB: unique receipt và transactional mutation

Một mô hình gồm collection `idempotency_receipts` và `orders`:

~~~javascript
db.idempotency_receipts.createIndex(
  {tenantId: 1, operation: 1, idempotencyKey: 1},
  {unique: true}
);
~~~

Điều kiện cần: receipt insert, Order mutation và outbox intent được commit trong **cùng transaction được backend hỗ trợ**, với read/write concerns/durability phù hợp. Truy vấn receipt sau duplicate phải gắn scope tenant.

### 22.1. Điều gì xảy ra nếu hai requests cùng K?

Unique index giúp một winner tạo receipt; loser nhận duplicate/conflict rồi đọc receipt. Có thể cần wait/resolution nếu winner còn in-progress. Không kết luận “duplicate key” luôn là cùng payload: phải so fingerprint.

### 22.2. Không gửi email trong transaction callback

MongoDB transaction helpers có thể retry toàn callback trong những tình huống nhất định. External mail/payment side effect trong callback có thể chạy nhiều lần dù DB transaction commit một lần.

### 22.3. Unknown commit result

Một nhãn lỗi commit outcome unknown yêu cầu cách resolve/retry phù hợp driver và transaction API. Không bắt đầu lại mutation với commandId mới.

### 22.4. Read concern và replica failover

Test receipt durability sau leader election/restart theo acknowledged write concern và deployment topology. Một acknowledged write với cấu hình durability yếu có thể bị rollback trong failure model; idempotency không sửa điều đó.

### 22.5. Không chỉ dựa vào unique index

Unique receipt riêng nhưng Order update ngoài transaction vẫn có crash gap. Test failpoint giữa hai writes để phát hiện.

## 23. DynamoDB: conditional put và transactional writes

Một cách xây idempotency receipt là một item với key duy nhất theo tenant/operation/request key. `PutItem` có điều kiện `attribute_not_exists(PK)` ngăn hai claim trùng. Nếu business item và receipt khác nhau, có thể cần `TransactWriteItems` khi nằm trong giới hạn API.

~~~text
TransactWriteItems:
    Put receipt item
        Condition: receipt PK must not exist
    Update Order item
        Condition: expected order version
    Put outbox event item
        Condition: event ID must not exist
~~~

### 23.1. Transaction một lần

Với atomic transaction, receipt và Order update cùng commit hoặc không commit theo bảo đảm DynamoDB. Sau timeout unknown, client kiểm receipt và state trước khi quyết định retry.

### 23.2. `ClientRequestToken` có phạm vi giới hạn

API transaction hỗ trợ client request token với cửa sổ idempotency nhất định, **không nên coi token SDK là receipt nghiệp vụ vĩnh viễn**. Khi cần retry qua giờ/ngày, persist receipt/domain ID theo policy riêng.

### 23.3. Same token, changed parameters

API có thể từ chối parameter mismatch theo semantics token. Test cả token reuse với cùng request và tham số khác, kiểm version/SDK contract cụ thể.

### 23.4. Read after failure

Kiểm receipt với consistency phù hợp và biết transaction result; không assume eventual read lập tức thấy mọi state trong mọi đường/index.

### 23.5. TTL cleanup

DynamoDB TTL cleanup không tức thời; không lấy timing của physical delete làm oracle. Business dedupe window cần độc lập với cơ chế housekeeping.

## 24. Cosmos DB for NoSQL: transaction theo logical partition

Cosmos DB transactional batch có các bảo đảm nguyên tử trong **cùng logical partition key** theo API được hỗ trợ.

### 24.1. Cùng partition

Nếu Order, receipt và outbox đều có cùng partition key phù hợp, có thể đặt writes vào transactional batch với condition/ETag khi cần. Test duplicate same key và concurrent claims.

### 24.2. Khác partition

Không giả định batch có atomicity xuyên nhiều logical partitions. Có thể cần partitioning lại, một authority record, saga/outbox và reconciliation.

### 24.3. ETag và optimistic concurrency

`If-Match`/ETag giúp ngăn lost updates, nhưng một request retry sau commit có thể gặp precondition failed. Service phải resolve receipt để nhận diện duplicate-success, không tự báo lỗi nghiệp vụ mới.

### 24.4. RU throttling

429/retry-after và timeout làm attempts lặp; test cùng key dưới throttling mà không tạo duplicate effect. Rate limits không thay idempotency.

### 24.5. Session/eventual reads

Nếu đọc receipt qua consistency yếu hoặc replica lag, một retry có thể tạm không thấy commit. Không dùng read “not found” từ projection lagging làm bằng chứng được phép thực thi lại.

## 25. Cassandra/ScyllaDB: LWT và giới hạn nguyên tử

Lightweight transactions/conditional writes có thể giúp xác lập duy nhất một receipt hoặc entity state theo key/partition và consistency setup, nhưng **không tự tạo transaction nhiều arbitrary partitions**.

### 25.1. `IF NOT EXISTS`

Một command receipt row có thể được claim bằng conditional insert. Tuy nhiên, sau claim, business write ở partition khác không tự atomic; phải có state machine/recovery protocol nếu không thể đưa vào cùng boundary.

### 25.2. Consistency levels

Chọn serial consistency/read-write consistency phù hợp với LWT semantics và replica topology. Test leader/replica outages và retry sau timeout.

### 25.3. Ambiguous LWT result

Timeout có thể xảy ra khi operation đã áp dụng hoặc chưa; đọc source authoritative/receipt để resolve, không tự gửi lệnh có request ID mới.

### 25.4. TTL và tombstones

Receipts có TTL tạo tombstones; deletion/compaction timing và delayed replays phải được tính. TTL receipt khác commitlog retention.

### 25.5. Không dùng logged batch như transaction đa partition chung

Batch semantics không thay distributed multi-record transactional isolation. Thiết kế idempotency theo source authority.

## 26. Redis: atomic script và persistence boundary

Redis có thể dùng Lua script hoặc transactions để thực hiện check receipt + update cùng một atomic execution **trong phạm vi server/slot phù hợp**. Nếu Redis chỉ là cache còn nguồn nghiệp vụ ở NoSQL khác, nó không thể tự bảo đảm atomicity với nguồn đó.

~~~text
Redis-only conceptual atomic script:
    IF receipt(K) exists:
        verify fingerprint
        return existing result
    ELSE:
        update one owned Redis state
        set receipt(K) with bounded TTL
        return committed result
~~~

### 26.1. Script atomic ở Redis không đồng nghĩa durable ACK sau failover

Redis persistence/replication semantics, disk snapshots/AOF và failover có thể tác động durability. Test crash/restart và acknowledged outcomes theo configuration, không suy chỉ từ atomic script.

### 26.2. Redis Cluster slot

Các keys dùng trong một script/multi-key operation phải phù hợp cluster slot constraints; hash tags có thể giúp locality nhưng có hot slot tradeoff.

### 26.3. Key eviction

Nếu Redis receipt bị evict trước TTL do memory pressure, retry muộn có thể mất dedupe. Đừng đặt **duy nhất** receipt bảo vệ money/stock trong cache có thể mất khi domain requires stronger guarantees.

### 26.4. External DB

Redis `SETNX` claim trước MongoDB write không làm hai operations atomic. Test crash giữa chúng để phát hiện pending forever/duplicate.

## 27. Firestore: transaction callback có thể chạy lại

Firestore SDK có transactional reads/writes và có thể retry transaction callback khi dữ liệu cạnh tranh. Do đó:

- Không gửi email, gọi payment API hoặc sinh irreversible side effects trong callback.
- Ghi receipt/idempotency document và domain mutation trong transaction khi khả năng/limits API phù hợp.
- Test concurrent transaction conflicts và callback retries.
- Gắn namespace tenant/user và lưu fingerprint + result.

### 27.1. Callback re-execution khác duplicate API request

Ngay cả một HTTP request có thể khiến transaction callback chạy nhiều lần. Số lần chạy Java lambda không phải số business commits.

### 27.2. IDs của documents

Nếu mỗi callback gọi `new random document ID`, retry có thể tạo references khác nhau. Dùng deterministic ID khi design cần cùng command result.

### 27.3. Listener/index lag

Response/projection từ listeners có thể đến sau commit; receipt đọc authoritative theo consistency API được hỗ trợ.

## 28. Outbox: idempotency của request chưa đủ cho side effects

Giả sử Order transition commit một lần, nhưng message broker có at-least-once delivery:

~~~mermaid
flowchart LR
    API["Command K"] --> TX["Atomic Order + Receipt + Outbox E"]
    TX --> PUB["Outbox publisher"]
    PUB --> MQ["Message broker"]
    MQ --> CON["Consumer receives E possibly more than once"]
    CON --> DED["Consumer dedupe + effect"]
~~~

### 28.1. Event ID phải ổn định

Outbox event có một `eventId` durable. Publisher retry cùng eventId, không tạo event ID mới mỗi lần gửi.

### 28.2. Consumer dedupe

Consumer dùng `(consumerName,eventId)` hoặc business key làm receipt. Nếu effect và consumer receipt đều nằm trong cùng transactional boundary có thể atomic commit; nếu không, cần protocol riêng.

### 28.3. Broker ACK mất

Publisher gửi event thành công, broker ACK mất, publisher resend; broker/consumer có thể thấy duplicate. Test đúng tình huống này.

### 28.4. Side effects bên ngoài

Email có thể gửi hai lần khi consumer crash sau SMTP success trước receipt. Payment provider có thể hỗ trợ idempotency key riêng; nếu không, phải reconciliation và policy chấp nhận/compensate.

### 28.5. Đừng gọi “exactly-once Kafka” là end-to-end

Các guarantee của transaction broker chỉ có phạm vi nhất định. Chúng không tự gộp database NoSQL và payment/SMTP thành một transaction.

## 29. Test hiệu ứng bên ngoài

### 29.1. Payment

Gửi cùng business payment command nhiều lần, giữ stable provider idempotency key. Oracle gồm provider charge count, receipt, ledger posting, amount/currency, refunds/unknown outcomes.

### 29.2. Email/notification

Giả lập provider chấp nhận gửi nhưng response mất. Nếu provider không deduplicate, test phải chỉ ra giới hạn bảo đảm; có thể dùng notification ID/provider tracking để tránh duplicate trong khả năng API.

### 29.3. Inventory

Một reservation ID duy nhất và stock decrement một lần. Releasing reservation lặp lại không được cộng stock hai lần.

### 29.4. External webhook

Webhook provider gửi cùng event nhiều lần và không đảm bảo order. Consumer phải dùng eventId/version và idempotent apply.

### 29.5. Không chạy destructive tests trên production

Tất cả tests external effects dùng sandbox/fake/test account và được cô lập; không charge khách hàng thật hoặc gửi email thật.

## 30. Property-based và model-based testing

Ngoài các test examples cố định, sinh chuỗi ngẫu nhiên của operations và faults:

~~~text
Operations:
    submit(K,P), retry(K,P), submit(K,Q),
    restartServer(), delayResponse(), dropAck(),
    expireReceipt(), redeliverEvent(E),
    failoverLeader(), readAuthority()

Model:
    at most one committed business effect per scoped K
    key reuse with different semantic payload is rejected
    no decreasing aggregate version
    no duplicate ledger/outbox effect IDs
~~~

### 30.1. Mô hình trừu tượng đơn giản

Giữ `Map<(tenant,operation,key), fingerprint/result>` và business state trong reference model tuần tự. So outputs/invariants của SUT dưới các lịch biểu concurrency.

### 30.2. Random schedule và seed

Ghi seed, sequence và fault schedule để có thể tái lập failure. Test ngẫu nhiên không có replay information rất khó sửa.

### 30.3. Linearizability

Nếu contract yêu cầu mỗi command atomic tại một linearization point, kiểm lịch sử invocation/response và tìm một thứ tự tuần tự hợp lệ. Không phải mọi projection eventual phải linearizable; chỉ áp constraint cho source of truth.

### 30.4. State machine testing

Test transition `ABSENT -> PENDING -> COMMITTED`, không cho `COMMITTED -> PENDING`, không cho cùng key khác fingerprint trở thành COMMITTED lần hai.

### 30.5. Shrinking

Khi test thấy sequence 500 events gây duplicate, rút gọn còn chuỗi nhỏ như “A commit; response lost; B retry” để dễ chỉ nguyên nhân.

## 31. Integration test với NoSQL thật cần quan sát gì?

### 31.1. Chạy qua hai API instances

Gửi cùng key tới hai pods/instances với shared DB. In-memory dedupe cache trên từng JVM có thể pass đơn tiến trình nhưng fail distributed.

### 31.2. Chuyển leader/primary

Trong lúc transaction/conditional write, gây failover được kiểm soát trong môi trường test; sau hồi phục kiểm durability + dedupe.

### 31.3. Network partition

Chặn response giữa API và DB hoặc giữa API và client đúng thời điểm; không tự phá source dataset không thể restore.

### 31.4. Throttling và retries

Tiêm 429/503/timeouts có giới hạn. Oracle đo business commits, receipt state và retry amplification.

### 31.5. Restart toàn bộ API layer

Sau lần đầu commit, kill/restart all service instances rồi retry key; durable receipt phải còn và không double effect.

### 31.6. Validate consistency mode

Đọc qua eventual index có thể tạm chưa thấy receipt. Test phải phân biệt lag tạm thời với duplicate mutation; dùng reads phù hợp semantics của authority.

## 32. Test cùng key nhưng hai requests khác nhau đồng thời

Một race đặc biệt:

~~~text
Client A: key K, payload P = amount 100
Client B: key K, payload Q = amount 200

Both arrive simultaneously.
~~~

### 32.1. Điều kiện đúng

Tối đa một payload được commit cho key K. Request còn lại phải nhận key-reuse conflict hoặc trạng thái in-progress rồi conflict sau khi fingerprint biết rõ.

### 32.2. Không được thay thế receipt

Nếu A lưu fingerprint P, B không được overwrite receipt bằng Q để khiến retry A bị coi thành command khác.

### 32.3. Không dùng last-write-wins

LWW có thể làm một lệnh được coi đã committed rồi bị ghi đè metadata bởi lệnh khác, dù business effect đầu vẫn tồn tại.

### 32.4. Test replay sau race

Gửi lại P rồi Q. Một phải replay result của winner, một phải conflict. Không có mutation mới.

## 33. Test key không bị tái sử dụng ngoài ý muốn

### 33.1. Client tạo key một lần cho business intent

Key sinh khi người dùng bấm “Thanh toán” cho một giao dịch; HTTP retries dùng lại key. Người dùng thực hiện một thanh toán khác phải có key khác.

### 33.2. Queue message identity

Producer gửi lại same event cần giữ eventId. Nếu mỗi delivery được bọc bằng ID mới, consumer dedupe theo delivery ID không giúp.

### 33.3. Batch commands

Nếu batch có N items, cần rõ idempotency ở cấp batch hay từng item. Một batch fail giữa chừng không được silently double-apply 90 items đã commit khi retry toàn batch.

### 33.4. Key length và entropy

Validate format/length, tránh keys user-controlled quá dài gây storage/DoS; cryptographic randomness giúp tránh collision nhưng không thay namespace/authorization.

### 33.5. Business retries sau thay đổi input

Nếu user sửa amount từ 100 thành 200 sau failure, đó là **lệnh mới** với key mới, không dùng lại K và hy vọng server áp payload mới.

## 34. Test negative business outcomes

### 34.1. Thiếu stock

Nếu request K bị reject vì không đủ tồn kho, API có thể lưu terminal failure trong receipt. Retry sau nhập thêm stock vẫn trả failure cũ hoặc cho lại theo policy; test contract đã chọn.

### 34.2. ExpectedVersion conflict

Client dùng version 4 nhưng Order đã version 5. Retry cùng key không được bỏ expectedVersion rồi force update. Nếu retry là duplicate của command đã commit, receipt resolution xảy ra trước hoặc cùng precondition check tùy design.

### 34.3. Permission denied

Không dùng idempotency receipt để bỏ qua authorization sau khi role bị thu hồi. Việc replay sensitive result phải kiểm quyền ở thời điểm đọc.

### 34.4. Validation mismatch

JSON object sai schema, thiếu currency hoặc orderId không hợp lệ phải bị reject trước business mutation. Đừng lưu bản ghi terminal “success” cho input chưa hợp lệ.

### 34.5. Same key, new authenticated principal

Nếu key scope theo tenant nhưng principal đổi, API phải quy định quyền replay result; không cho người mới tự thấy dữ liệu riêng tư chỉ vì đoán key.

## 35. Observability: nhìn thấy retry và deduplication

| Metric | Ý nghĩa |
|---|---|
| `command_attempts_total` | Requests/attempts nhận được |
| `command_new_commits_total` | Business commands commit mới |
| `idempotency_replays_total` | Requests được phục vụ từ receipt |
| `idempotency_key_conflicts_total` | Same key/different fingerprint |
| `idempotency_in_progress_total` | Trùng request đang thực hiện |
| `command_unknown_outcome_total` | Ambiguous commit cần resolve |
| `receipt_resolution_latency` | Thời gian đọc/khôi phục outcome |
| `duplicate_event_deliveries_total` | Outbox/consumer redelivery |
| `ledger_duplicate_prevented_total` | Conditional conflict có mục đích |
| `receipt_expired_retries_total` | Retry tới sau retention |
| `invariant_violations_total` | Mất cân bằng/duplicate authoritative effects |

### 35.1. Đừng đưa key đầy đủ vào metric label

Idempotency keys có cardinality cao và có thể nhạy cảm. Dùng operation/result/tenant tier có giới hạn; IDs chỉ nên có trong structured logs/traces được redacted/kiểm quyền.

### 35.2. Correlation ID và command ID khác nhau

Mỗi HTTP attempt có traceId khác, nhưng commandId giữ ổn định. Tracing nên nối attempts về cùng business command mà không lộ payload nhạy cảm.

### 35.3. Tỷ lệ replay cao không luôn là bug

Mobile networks/retries có thể tạo duplicate attempts hợp lệ. Điều đáng lo là số committed effects lớn hơn distinct business command IDs, key conflicts hoặc unknown outcome tồn đọng.

### 35.4. Audit receipts

Lưu createdAt, committedAt, result ID, fingerprint digest, scope, expiration policy và source version; tránh raw password/payment details trong logs.

## 36. Case study: trừ tồn kho hai lần sau timeout

Ứng dụng giữ `stock=20`; hai requests cùng K đến từ một gateway retry. Service cũ:

~~~text
check stock > 0
update stock = stock - 1
respond 200
~~~

### 36.1. Lỗi

Request đầu commit nhưng ACK mất; request sau lại kiểm stock >0 và trừ thêm, kết quả 18 thay vì 19.

### 36.2. Thiết kế sửa

Stable `reservationId`/key, conditional stock decrement và receipt/reservation record trong một atomic boundary được hỗ trợ hoặc một source-authority protocol.

### 36.3. Bộ test

Sequential 2×, concurrent 100×, lost ACK, restart, key conflict, release reservation twice, two different keys cạnh tranh 1 stock remaining.

### 36.4. Oracle

Stock=19, một reservation, một receipt, một event, no negative stock. Với hai distinct keys cạnh tranh stock cuối, chỉ một reservation thành công.

## 37. Case study: tạo đơn hàng trùng khi mạng chập chờn

Một endpoint `POST /orders` tạo random UUID khi được gọi. Nếu mobile app retry, hai Order IDs xuất hiện dù user bấm một lần.

### 37.1. Thiết kế

Gắn idempotency key theo intent và persist `key -> orderId/result` cùng create operation. Không tạo orderId mới trên retry.

### 37.2. Key reuse khác payload

Retry cùng key nhưng thay cart items/amount phải conflict. Nếu user đã đổi giỏ hàng, cần một intent mới với key mới.

### 37.3. Test

Timeout sau Order committed; retry từ client mới/process khác; assert một Order và same logical orderId returned.

### 37.4. Backup/recovery

Sau restore từ backup cũ, receipt có thể mất trong khi downstream payment đã charge. Cần recovery policy/ledger/provider reconciliation chứ không giả mọi dữ liệu về cùng mốc.

## 38. Case study: Kafka redelivery và projection

Outbox đã commit một `ORDER_CONFIRMED` event, consumer ghi search projection rồi crash trước broker ACK. Broker phát lại event.

### 38.1. Projection có thể upsert theo version

Nếu consumer apply `set status=CONFIRMED, version=5` có conditional monotonic version, replay v5 có thể là no-op.

### 38.2. Event side effects không tự idempotent

Consumer gửi email mỗi lần nhận event sẽ gửi hai lần. Cần một notification outbox/receipt hoặc provider-supported dedupe.

### 38.3. Test sequence

Deliver E, apply projection, drop ACK, restart consumer, redeliver E; kiểm projection version và notification count theo contract.

### 38.4. Duplicate event có thể đến muộn

Sau khi projection lên version 7, event v5 được redeliver. Consumer không được ghi lùi về v5.

## 39. Case study: receipt TTL quá ngắn

Một command key K có TTL 15 phút. Mobile offline queue có thể phát lại sau 24 giờ; event processor có thể replay sau 72 giờ.

### 39.1. Kịch bản

Lúc 09:00 command K commit. Lúc 09:15 receipt hết hạn logic. Ngày hôm sau mobile app gửi lại K vì chưa thấy ACK. Hệ tưởng K mới.

### 39.2. Nếu domain operation là decrement

Stock bị trừ hai lần nếu không còn business reservation ID/ledger unique. TTL không phải giải pháp bảo vệ cho retry horizon dài.

### 39.3. Fix

Chọn retention phù hợp, giữ durable domain identity hoặc provider event ID, và cấm tái sử dụng business command ID cho cùng entity theo policy.

### 39.4. Test

Fake clock/controlled expiration; retry tại 14 phút, 16 phút, 24 giờ, 3 ngày; kiểm invariant và documented behavior.

## 40. Runbook thiết kế test fault injection

### Bước 1 — Định nghĩa operation

Chọn `ConfirmOrder`, `ReserveStock`, `ChargePayment` hoặc `AppendEvent`; ghi semantic payload, scope, key, expectedVersion.

### Bước 2 — Xác định nguồn có thẩm quyền

Receipt ở đâu? Business mutation ở đâu? Có transaction scope nào? Outbox ở cùng commit không? External provider có idempotency API không?

### Bước 3 — Viết oracle

Một committed mutation per command, no duplicate ledger entry, stock không âm, same semantic result, mismatch conflict.

### Bước 4 — Tạo test cases tuần tự

First attempt, immediate retry, repeated 100 times, same-key/different-body, new-key/same-body, tenant isolation.

### Bước 5 — Tạo concurrent schedules

N threads cùng key, mixed payload race, multiple processes, distinct keys tranh một tài nguyên hữu hạn.

### Bước 6 — Tiêm lỗi tại boundaries

Before commit, during commit, after commit before ACK, HTTP response dropped, process restart, leader failover, event redelivery, receipt TTL expiry.

### Bước 7 — Đọc authoritative state

Kiểm receipts, entity versions, balance/stock, outbox, provider receipts và absence of duplicates.

### Bước 8 — Lặp và lưu seeds

Chạy nhiều schedules với bounded deadlines; ghi fault timing/seed/repro steps, không dựa vào sleep ngẫu nhiên.

### Bước 9 — Kết luận theo phạm vi

Chỉ tuyên bố guarantee trong model đã test: one region, one database/partition, receipt TTL, consistency level, external effects được mock/provider sandbox.

## 41. Bộ dữ liệu kiểm thử đề xuất

~~~text
Tenant A:
  Order O17: status=NEW, version=4
  Inventory SKU-X: stock=10
  No command receipt K

Tenant B:
  Order O17: status=NEW, version=9
  Inventory SKU-X: stock=20
  No command receipt K

Commands:
  K/P: Confirm A/O17 with expectedVersion=4
  K/Q: Confirm A/O17 but changed payload
  K2/P: Separate business intent with same fields
  B/K: Tenant B request with same textual key K
~~~

### 41.1. Vì sao hai tenants có cùng orderId/key?

Để chứng minh scope/authorization đúng, không bị global-key collision hay leak receipt. Cần đặt data trong test environment cô lập.

### 41.2. Cần baseline trước mỗi run

Reset theo supported API hoặc dùng fresh test namespace; đừng lẫn kết quả test cũ thành replay đang cần kiểm.

### 41.3. Ghi receipt với result reference

Sử dụng stable confirmationId/reservationId cho oracle; không lấy random timestamp làm bằng chứng có một commit.

## 42. Test cho batch và bulk command

Một request chứa 100 Order updates:

~~~text
BatchId=B1
Items=O1..O100
~~~

### 42.1. Atomic batch nếu engine hỗ trợ

Nếu business contract toàn batch atomic, cần receipt và 100 effects cùng transaction phù hợp. Nhưng đa phần NoSQL có giới hạn transaction size/scope; test phải xét.

### 42.2. Partial batch

Nếu chỉ 90/100 items commit trước crash, retry B1 phải nhận biết từng item completed và không làm 90 items lần hai. Một receipt batch ở trạng thái DONE/FAILED đơn giản không đủ.

### 42.3. Stable item IDs

Mỗi item có sub-commandId/unique effect ID hoặc per-item processing record để retry idempotent.

### 42.4. Mismatch batch payload

Cùng batchId nhưng danh sách items khác phải conflict theo policy; không nhập nhằng hai batches cùng ID.

### 42.5. Reporting

API trả per-item results/terminal outcomes có thể replay được; không tự mark full success khi còn 10 items pending.

## 43. Những hiểu lầm cần tránh

### “Gửi 200 OK hai lần tức là idempotent”

Không: có thể DB đã bị cập nhật hai lần nhưng response giống.

### “Có Idempotency-Key header là đủ”

Không: cần durable receipt, fingerprint, atomic effect/claim và TTL policy.

### “Đọc receipt trước khi ghi là ngăn race”

Không: hai requests đồng thời đều có thể đọc absent.

### “Unique receipt index là mọi thứ đều atomic”

Không nếu business update và receipt save ở hai independent commits.

### “Timeout nghĩa chưa commit”

Không: ACK có thể mất sau commit.

### “Transaction retry callback chạy nhiều lần thì business side effect được bảo vệ”

Chỉ DB writes trong transaction có thể được bảo vệ; external mail/payment trong callback vẫn có thể lặp.

### “Redis SETNX bảo vệ payment trong MongoDB”

Không có atomicity xuyên hai engines chỉ bằng SETNX.

### “Receipt TTL 1 giờ đủ vì HTTP timeout 30 giây”

Không nếu mobile queue, DLQ hoặc event replay xuất hiện sau nhiều giờ/ngày.

### “Cùng payload luôn là cùng nghiệp vụ”

Không: user có thể cố ý thực hiện hai commands giống nhau với keys khác.

### “Cùng key nhưng payload khác thì chọn request mới hơn”

Không: key reuse conflict phải được xử lý rõ, không silently overwrite.

### “At-least-once delivery bằng exactly-once effect”

Không tự động: cần idempotent effect/receipt ở consumer authority.

### “Unit test trên một JVM chứng minh production”

Không: cần multi-instance, durable DB và failure injection.

### “Một receipt ở cache đủ cho business-critical writes”

Không nếu cache eviction/restart/failover làm mất receipt trước retry horizon.

### “Idempotency không cần kiểm authorization”

Không: replay result của tenant khác có thể rò dữ liệu.

### “Có test concurrency thì không cần test lost ACK”

Hai failure modes độc lập; phải kiểm cả hai.

### “Khôi phục DB từ backup sẽ giữ mọi idempotency record”

Không nếu receipts và downstream effects được phục hồi tới những mốc khác nhau.

## 44. Checklist trước khi công bố idempotent API

1. Đã định nghĩa **business operation** cụ thể và điều gì được coi là “effect” chưa?
2. Có stable idempotency key cho một user intent không?
3. Retry của client/gateway có giữ nguyên key không?
4. Scope key theo authenticated tenant/operation phù hợp không?
5. Same-key/different-payload có reject rõ không?
6. Fingerprint canonical và versioned chưa?
7. Receipt có durable storage thay vì JVM-local map không?
8. Claim/receipt và business mutation atomic hoặc recoverable không?
9. Unique key/conditional writes được enforce tại source không?
10. Có version/CAS guards để tránh lost updates không?
11. Có state PENDING/COMMITTED và protocol resolve UNKNOWN không?
12. Receipt có lưu result ID/status cần replay không?
13. Retention của receipt dài hơn retry/delayed replay window chưa?
14. TTL expiry semantics đã được test chưa?
15. Domain uniqueness có bảo vệ sau receipt expiry khi cần không?
16. Tất cả side effects qua outbox/provider có dedupe riêng không?
17. Event IDs và command IDs có ổn định qua retries không?
18. Transaction retry callback không gọi external effect trực tiếp chứ?
19. Có xử lý request cùng K đến đồng thời không?
20. Có test same K/different payload đồng thời không?
21. Có test lost ACK **sau commit** không?
22. Có test process restart sau commit không?
23. Có test leader failover/connection reset theo backend không?
24. Có test retries chồng nhiều tầng không?
25. Có test 429/throttling và retry budget không?
26. Có test tenant isolation và quyền replay receipt không?
27. Có assert **authoritative business effects**, không chỉ response không?
28. Có kiểm outbox/CDC redelivery không?
29. Có kiểm batch partial success/resume nếu API hỗ trợ không?
30. Có metrics replay/conflicts/unknown/invariant violations không?
31. Có test backup restore/receipt loss nếu nằm trong recovery model không?
32. Đã giới hạn scope các guarantee được công bố chưa?

## 45. Bài tập thực hành

### Bài 1 — Idempotency là gì?

Phân biệt “HTTP request đã đến một lần”, “handler đã chạy một lần” và “business effect commit một lần”. Tại sao chỉ điều cuối là oracle quan trọng?

### Bài 2 — Nhận diện operation

Phân loại `set status=PAID`, `counter+=1`, `put item`, `append event`, `delete by id` theo khả năng idempotent tự nhiên và hidden side effects.

### Bài 3 — Lost ACK

Viết timeline: server commit, ACK mất, client timeout, retry. Nêu trạng thái/receipt mong đợi và cách fault injector buộc đúng thời điểm.

### Bài 4 — Same key, same payload

Gửi K,P 100 lần tuần tự; xác định status/result contract và business mutation count.

### Bài 5 — Concurrency

Sử dụng `CountDownLatch` để 100 threads cùng gửi K,P; kiểm một commit và cùng semantic result.

### Bài 6 — Payload mismatch

Gửi K,P rồi K,Q với amount khác; vì sao phải conflict, không chọn request cuối?

### Bài 7 — Concurrent mismatch

Hai requests K,P và K,Q đến đồng thời. Thiết kế oracle “at most one payload committed” và response cho loser.

### Bài 8 — Different key, same body

Người dùng mua hai món giống nhau hai lần với K1 và K2. Vì sao không nên dedupe chỉ dựa trên raw payload hash?

### Bài 9 — JSON canonicalization

Thiết kế fingerprint ổn định khi JSON field order thay đổi, đồng thời vẫn phát hiện amount/currency/orderId thay đổi.

### Bài 10 — Tenant isolation

Tenant A và B đều dùng textual key K. Thiết kế receipt namespace và test không lộ kết quả chéo tenant.

### Bài 11 — Check-then-write

Hai threads đều đọc receipt absent rồi trừ stock. Vẽ interleaving và chọn atomic primitive phù hợp.

### Bài 12 — Receipt first, effect later

Service lưu `COMMITTED` receipt trước khi update Order, rồi crash. Tại sao retry có thể báo thành công giả?

### Bài 13 — Effect first, receipt later

Service update Order xong rồi crash trước receipt. Tại sao retry có thể duplicate? Đề xuất transaction hoặc recoverable protocol.

### Bài 14 — PENDING

Thiết kế state machine PENDING/COMMITTED/UNKNOWN có lease/fencing, nêu recovery khi worker cũ vẫn đang chạy.

### Bài 15 — Transaction callback

Một MongoDB transaction callback gửi email. Nếu callback bị retry, điều gì xảy ra? Thiết kế outbox thay thế.

### Bài 16 — DynamoDB

Thiết kế `TransactWriteItems` gồm conditional receipt item + Order update + outbox event, nêu giới hạn của `ClientRequestToken`.

### Bài 17 — Cosmos DB

Vì sao receipt và Order ở cùng logical partition có thể dùng transactional batch nhưng ở partitions khác cần protocol khác?

### Bài 18 — Cassandra

Một LWT claim receipt thành công nhưng Order update ở partition khác thất bại. Phân tích atomicity gap và recovery.

### Bài 19 — Redis

Redis SETNX receipt, rồi MongoDB decrement. Service crash giữa hai bước. Vì sao Redis claim không đủ? Test này ra sao?

### Bài 20 — Firestore

Transaction callback chạy lại do conflict. Thiết kế test để chứng minh callback count khác business commit count.

### Bài 21 — TTL

Receipt TTL 15 phút, mobile retry sau 24 giờ. Đề xuất policy tránh lặp với stock/payment operations.

### Bài 22 — Different errors

Phân loại validation error, key conflict, 429, transient DB timeout và unknown commit; client được retry như thế nào?

### Bài 23 — Retry amplification

Mobile retry 3, gateway retry 2, backend SDK retry 3. Thiết kế metrics/deadline để kiểm đúng một business effect dưới nhiều attempts.

### Bài 24 — Outbox

Order commit và event E xuất hiện một lần trong outbox; broker giao E ba lần. Viết consumer dedupe oracle.

### Bài 25 — Payment provider

Provider chấp nhận charge nhưng response mất. Thiết kế stable provider key, receipt lookup và reconciliation trước khi charge lại.

### Bài 26 — Notification

Consumer gửi email rồi crash trước ACK. Những bảo đảm nào có thể và không thể hứa nếu SMTP provider không hỗ trợ dedupe?

### Bài 27 — Batch

Batch 100 items commit 90 rồi crash. Thiết kế per-item identities/checkpoints để retry không duplicate.

### Bài 28 — Model-based

Tạo reference model cho `(tenant,operation,key) -> result` và sinh random events submit/retry/restart/dropAck/expire.

### Bài 29 — Linearizability

Thu thập history invocation/response cho hai same-key requests đồng thời. Tìm một thứ tự tuần tự hợp lệ hoặc nêu vi phạm.

### Bài 30 — Failover

Đưa leader failover sau commit nhưng trước response. Kiểm receipt durability và business correctness theo write concern/consistency.

### Bài 31 — Fake vs real DB

Fake `synchronized` pass 100-thread test nhưng production hai pods duplicate. Liệt kê integration tests cần bổ sung.

### Bài 32 — Read replicas

Receipt vừa commit nhưng replica đọc eventual vẫn báo absent. Vì sao không được lấy đó làm bằng chứng để apply lại?

### Bài 33 — Authorization

Một user đoán được idempotency key của tenant khác; làm sao ngăn replay API trả sensitive result?

### Bài 34 — Restore

Backup khôi phục Order và receipt từ hôm trước, nhưng payment provider đã xử lý charge hôm nay. Thiết kế reconciliation và idempotency tránh charge lại.

### Bài 35 — Tổng hợp Java/NoSQL

Thiết kế endpoint `POST /orders/{id}/confirm` dùng Java + một NoSQL tùy chọn: DTO typed, fingerprint, receipt/transaction authority, expectedVersion, outbox, retry/unknown outcome, TTL, tenant scope và 15 test scenarios với oracle.

---

**Kết luận:** **Kiểm thử idempotency khi cùng yêu cầu được gửi lại** phải chứng minh một điều sâu hơn “API không báo lỗi”: **một ý định nghiệp vụ chỉ tạo tối đa một tác động có thẩm quyền trong phạm vi và thời hạn đã công bố**, dù client, gateway, SDK hoặc message broker phát lại. Bài test quan trọng nhất là **database commit thành công nhưng ACK không tới client**, tiếp theo là **nhiều requests cùng key đến đồng thời** và **cùng key với payload khác nhau**. Muốn vượt qua các phép thử, hệ cần key/fingerprint có scope, receipt bền, atomic transaction/conditional-write hoặc recovery protocol đúng, version/tombstone guards, TTL phù hợp và outbox/consumer idempotency cho side effects. Đừng chỉ kiểm HTTP status: hãy đọc **authoritative receipts, versions, ledgers, stocks và event IDs** để thấy rõ rằng không có effect thứ hai, không bỏ sót effect thứ nhất và không nhầm lệnh mới với retry cũ.
