# Mô phỏng mất kết nối trước hoặc sau khi hệ thống đích đã nhận

## Mục tiêu và bối cảnh

Trong module **SPRING_BOOT_INTEGRATION**, Spring Boot tổ chức tích hợp qua HTTP client, cơ sở dữ liệu, cache, broker thông điệp và các adapter Spring Integration. Hệ thống phải quản lý cấu hình, hợp đồng dữ liệu, giao dịch, lỗi, xử lý trùng lặp, kiểm thử và quan sát các luồng tích hợp thực tế.

Giả sử **Order Service** gọi HTTP `POST /reservations` của **Inventory Service** để giữ hàng. Client gửi yêu cầu, chờ vài giây rồi nhận lỗi `Connection reset` hoặc `Read timed out`. Có hai khả năng rất khác nhau:

- Inventory chưa từng nhận hoặc chưa xử lý yêu cầu: retry có thể là thao tác cần thiết.
- Inventory **đã ghi reservation và COMMIT**, nhưng response bị mất trên đường về: retry ngây thơ có thể giữ hàng **lần thứ hai**.

Từ phía client, hai tình huống này có thể tạo ra **cùng một loại IOException hoặc timeout**. Vì thế, nội dung cốt lõi của bài không phải là chọn bao nhiêu retries, mà là **mô phỏng chính xác thời điểm đứt kết nối, thu thập bằng chứng về trạng thái phía đích và bảo đảm retry/reconciliation an toàn**.

Bài thuộc chương **Hợp đồng và lỗi biên**, đề mục **Mô phỏng mất kết nối trước hoặc sau khi hệ thống đích đã nhận**. Đây là tình huống xuyên suốt HTTP, SOAP, database, Redis, Kafka, RabbitMQ, RSocket và các adapter của Spring Integration, với điểm khác nhau ở cơ chế xác nhận của từng giao thức.

### Kết quả học tập

Sau bài này, bạn có thể:

1. Phân biệt **request đã được gửi, đã đến broker/endpoint, đã được validate, đã commit và đã được xác nhận**.
2. Giải thích vì sao một timeout không chứng minh request chưa được xử lý.
3. Thiết kế **failure window matrix** cho trước và sau các mốc receipt/commit/ACK.
4. Mô phỏng connection refused, TCP reset, response drop, delay, một phần request body và network partition.
5. Tạo kiểm thử HTTP xác định phía đích đã ghi side effect trước khi làm mất response.
6. Xây contract với **operationId/Idempotency-Key**, response replay và API tra cứu trạng thái.
7. Kiểm thử producer confirms, consumer ACK, offset commit, inbox/outbox trên RabbitMQ/Kafka.
8. Phân biệt lỗi mạng transient với kết quả nghiệp vụ **UNKNOWN**.
9. Đo lường, hạn chế retry storm và xử lý incident khi thông tin phía đích chưa chắc chắn.
10. Viết acceptance tests bao gồm lỗi mạng, concurrency, crash, restart và recovery.

> **Nguyên tắc:** “Client không nhận được xác nhận” **khác** “đích chưa nhận yêu cầu” và cũng **khác** “đích chưa commit”. Khi thiếu bằng chứng, kết quả nghiệp vụ phải được xem là **UNKNOWN**, không tự gán **FAILED** rồi phát lại một command không có idempotency.

## 1. Vẽ timeline trước khi mô phỏng

~~~mermaid
sequenceDiagram
    participant C as Order Service (Client)
    participant N as Network / Proxy
    participant T as Inventory API (Target)
    participant D as Target Database
    C->>N: 1. Write request bytes
    N->>T: 2. Target receives request
    T->>T: 3. Validate + authorize
    T->>D: 4. Write reservation
    D-->>T: 5. COMMIT OK
    T-->>N: 6. Produce HTTP response
    N-->>C: 7. Client receives response
    Note over C,D: Kết nối có thể đứt ở bất kỳ khoảng nào
~~~

Không có một thời điểm duy nhất tên là “đích đã nhận”. Cần định nghĩa mốc nhận nào được dùng:

| Mốc | Điều đã chắc chắn xảy ra | Điều **chưa** được chứng minh |
| --- | --- | --- |
| Client gọi `RestClient.post()` | Code bắt đầu thao tác | Request ra khỏi process |
| Client ghi bytes vào socket thành công | OS/client stack nhận bytes | Đích application đã đọc |
| Proxy nhận request | Request tới proxy | Backend thật đã nhận |
| Target handler bắt đầu chạy | Handler đã thấy request | Validate thành công, SQL commit |
| Target queue tiếp nhận command bền vững | Work đã được persist theo contract | Business side effect hoàn thành |
| DB COMMIT thành công | Business write đã commit tại database đó | Caller nhận response/broker consumer ACK |
| Target ghi response vào socket | Application/transport bắt đầu gửi response | Client đã đọc, hiểu và lưu kết quả |
| Client nhận HTTP 2xx | Đích đã trả thành công theo HTTP contract | Mọi downstream bất đồng bộ sau đó đã xử lý |
| Client persist receipt/result | Caller có bằng chứng bền vững | Hệ thống khác ngoài phạm vi receipt đã hoàn tất |

**Lưu ý:** Một HTTP 202 có thể chỉ nghĩa là server **đã nhận công việc để xử lý**, không phải business transaction cuối cùng hoàn tất. Một HTTP 200 cũng chỉ có ý nghĩa theo **contract API cụ thể**: một số API dùng 200 cho yêu cầu khởi tạo workflow và tiếp tục xử lý nền.

### 1.1. Ba trạng thái phải phân biệt

~~~mermaid
stateDiagram-v2
    [*] --> PENDING
    PENDING --> CONFIRMED: Bằng chứng đích đã hoàn thành
    PENDING --> REJECTED: Từ chối rõ theo contract
    PENDING --> UNKNOWN: Timeout / mất kết nối
    UNKNOWN --> CONFIRMED: Query status / idempotent replay
    UNKNOWN --> REJECTED: Query status xác minh rejected
    UNKNOWN --> PENDING: Retry cùng operationId (theo policy)
    CONFIRMED --> [*]
    REJECTED --> [*]
~~~

- **CONFIRMED:** có bằng chứng đủ theo định nghĩa nghiệp vụ, ví dụ receipt/transaction ID mà đích đảm bảo đã commit.
- **REJECTED/FAILED:** đích trả từ chối rõ và đã xác minh không có business side effect, hoặc một failure không thể tạo side effect theo contract.
- **UNKNOWN:** không đủ bằng chứng khẳng định có/không có side effect.
- **PENDING:** ý định đang được xử lý hoặc chờ retry/reconciliation, không đồng nghĩa chưa từng được gửi.

Trong production, trạng thái có thể phong phú hơn như `WAITING_AUTH`, `RETRY_SCHEDULED`, `CANCEL_REQUESTED`, `CONFLICT`, `MANUAL_REVIEW`. Quan trọng nhất là không làm mất sự phân biệt **UNKNOWN** và **REJECTED**.

## 2. Ma trận failure windows

Xem một lệnh thay đổi trạng thái (reserve/charge/ship), không phải GET thuần đọc.

| Kịch bản | Điểm đứt | Đích có thể đã nhận? | Đích có thể đã commit? | Client nên làm gì? |
| --- | --- | --- | --- | --- |
| A | Chưa connect TCP | Không cho **attempt này** nếu biết chắc không mở được socket | Không cho attempt đó; nhưng xét các attempts trước | Retry an toàn hơn, vẫn phải giữ operationId |
| B | Sau connect, trước khi gửi hết bytes | Có thể nhận một phần | Tùy protocol/streaming handler | Không kết luận chắc chắn; kiểm tra dấu vết |
| C | Sau target nhận, trước validation | Có | Thường chưa, nhưng middleware có thể ghi audit/side effect | Phân biệt accepted vs committed |
| D | Sau validation, trước DB COMMIT | Có | Có thể rollback hoặc transaction vẫn đang xử lý | Chờ/tra cứu theo key |
| E | **Sau COMMIT, trước khi gửi response** | Có | **Có** trong kịch bản được chèn lỗi | Query status hoặc replay cùng key |
| F | Đích đã gửi response, mạng làm mất | Có | Tùy contract, có thể đã commit | UNKNOWN từ phía caller |
| G | Client nhận 2xx rồi crash trước khi lưu receipt | Có | Có thể đã commit | Durable intent + idempotent recovery |
| H | Timeout, client retry với **key mới** | Có | Có thể lần 1 đã commit | **Nguy hiểm: duplicate** |
| I | Timeout, client retry với **cùng key** | Có | Có thể đã commit | An toàn **nếu đích thực thi idempotency đúng** |

Mô phỏng phải chứng minh đang đứng ở dòng nào trong bảng. Ví dụ tạo lỗi `connection reset` bằng một stub **chưa thực thi side effect** chỉ kiểm tra đường “mất kết nối trước xử lý”; không chứng minh được hệ thống an toàn trong cửa sổ E.

### 2.1. Hai lần timeout giống nhau, kết quả khác nhau

~~~mermaid
flowchart TD
    R["Client POST reserve"] --> D{"Mất kết nối ở đâu?"}
    D -->|"Trước khi request tới target"| N["Target: no reservation"]
    D -->|"Sau COMMIT, trước response"| C["Target: reservation exists"]
    N --> T["Client thấy timeout/reset"]
    C --> T
    T --> U["Outcome UNKNOWN từ góc nhìn client"]
    U --> Q["Tra cứu operationId hoặc idempotent retry"]
~~~

Một client không được dựa riêng vào `SocketTimeoutException`, `ResourceAccessException` hoặc HTTP 502/504 để suy ra server chưa nhận request. Các gateway/proxies có thể cắt response trong khi target phía sau đã xử lý xong.

## 3. Phân biệt các lớp xác nhận

**Cần xác định chính xác chủ thể xác nhận:**

| Thông điệp/xác nhận | Ai xác nhận? | Không chứng minh |
| --- | --- | --- |
| TCP ACK | TCP stack ở peer | Application đã xử lý/commit |
| HTTP request body write completed | Local HTTP client/OS | Remote đã đọc hết body |
| HTTP 200/201 | HTTP endpoint/gateway trả response | Worker async khác đã xử lý nếu contract không nói vậy |
| HTTP 202 | Endpoint nhận yêu cầu xử lý | Business operation đã hoàn thành |
| HTTP 409 | Server báo conflict theo contract | Tự động là retryable hoặc permanent |
| Kafka producer future success | Broker accepted theo `acks` config | Consumer đã commit SQL |
| Rabbit publisher confirm ACK | Broker confirm theo AMQP policy | Routing chắc đến consumer hoặc business completed |
| Rabbit consumer `basicAck` | Consumer xác nhận delivery trên channel | Client producer đã biết kết quả |
| Kafka offset commit | Tiến độ consumer group | Side effect đã commit nếu code commit sớm |
| PostgreSQL JDBC COMMIT success | Database đã xác nhận commit | HTTP caller nhận receipt |
| Redis command `OK` | Redis xử lý command theo protocol | SQL transaction khác đồng thời thành công |

**Điểm khó:** “Target nhận” đôi khi là “broker đã persist vào queue”, đôi khi là “handler đã chạy”, hoặc “database đã COMMIT”. Bài kiểm thử phải chọn một ý nghĩa và ghi bằng chứng tương ứng, không dùng một từ “delivered” cho tất cả.

## 4. Định nghĩa business contract trước khi cắt mạng

Giả sử API giữ hàng:

~~~http
POST /v1/reservations HTTP/1.1
Host: inventory.example.org
Content-Type: application/json
Idempotency-Key: 5b0c3ae8-2c49-48a0-a0a0-4024a29e11b2

{"orderId":"ORD-100","sku":"SKU-A","quantity":2}
~~~

Contract cần nêu rõ:

1. Một `Idempotency-Key` định danh **một ý định nghiệp vụ**, không phải một HTTP attempt.
2. Retry cùng ý định dùng **cùng key và cùng payload semantics**.
3. Server phải lưu key và kết quả đủ lâu, bền sau restart nếu SLA yêu cầu.
4. Nếu key cũ được dùng cho payload khác, trả conflict/mismatch rõ, không làm việc mới.
5. Khi xử lý thành công, server trả **reservationId**, `operationId` và state.
6. Có endpoint tra cứu trạng thái nếu operation có thể bất đồng bộ hoặc unknown outcome.
7. Quy định key retention và xử lý khi hết retention.
8. Định nghĩa mã lỗi 400/401/403/409/422/429/5xx theo contract, không suy luận mặc định.
9. Phân biệt **accepted** với **completed**.
10. Quy định ordering/version khi hai commands khác nhau tác động cùng order.

### 4.1. Response thành công

~~~http
HTTP/1.1 201 Created
Content-Type: application/json
Location: /v1/reservations/RES-500

{"operationId":"5b0c3ae8-2c49-48a0-a0a0-4024a29e11b2",
 "reservationId":"RES-500",
 "state":"CONFIRMED"}
~~~

Nếu replay cùng key, một API có thể trả nguyên status/body của request đầu hoặc trả `200 OK` cùng reservationId. **Đây là chính sách theo hợp đồng**, không có một quy tắc bắt buộc chung cho mọi API sử dụng header `Idempotency-Key`.

### 4.2. Status lookup

~~~http
GET /v1/operations/5b0c3ae8-2c49-48a0-a0a0-4024a29e11b2 HTTP/1.1
Host: inventory.example.org
Authorization: Bearer <redacted>
~~~

Response ví dụ:

~~~json
{
  "operationId": "5b0c3ae8-2c49-48a0-a0a0-4024a29e11b2",
  "state": "CONFIRMED",
  "reservationId": "RES-500"
}
~~~

Status API cần phân quyền theo service/tenant; không công khai thông tin giao dịch chỉ vì biết operationId. Nếu trả 404, có thể có độ trễ đồng bộ/read replica hoặc retention; **404 không tự chứng minh operation chưa từng được commit** nếu contract không bảo đảm tính nhất quán đó.

### 4.3. Không sinh key mới mỗi retry

~~~java
// Sai: mỗi attempt có một logical identity mới.
retry(() -> inventory.reserve(
        java.util.UUID.randomUUID().toString(),
        command));
~~~

~~~java
// Đúng: key được tạo một lần cho một business intent.
String operationId = command.operationId();
retry(() -> inventory.reserve(operationId, command));
~~~

Ví dụ `retry` là hàm orchestration minh họa; cần policy retry có giới hạn và deadline tổng. Đặc biệt với Payment/Inventory, một retry có token mới **không làm side effect cũ biến mất**.

## 5. Idempotency server-side phải atomic

Một client gửi cùng key không đủ. Nếu target chỉ lưu key **sau** khi làm side effect, hai concurrent attempts có thể cùng thực hiện nghiệp vụ.

### 5.1. SQL schema minh họa

~~~sql
CREATE TABLE api_idempotency (
    consumer_name VARCHAR(80) NOT NULL,
    operation_id UUID NOT NULL,
    request_hash CHAR(64) NOT NULL,
    state VARCHAR(24) NOT NULL,
    response_json JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMPTZ,
    PRIMARY KEY (consumer_name, operation_id)
);

CREATE TABLE inventory_reservations (
    reservation_id UUID PRIMARY KEY,
    operation_id UUID NOT NULL UNIQUE,
    order_id VARCHAR(120) NOT NULL,
    sku VARCHAR(100) NOT NULL,
    quantity INT NOT NULL CHECK (quantity > 0),
    state VARCHAR(24) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
~~~

**Hai ràng buộc bảo vệ khác nhau:**

- `PRIMARY KEY (consumer_name, operation_id)` phân biệt intent đã thấy.
- `UNIQUE (operation_id)` ở bảng nghiệp vụ chặn reservation trùng do retry hoặc caller khác đi vòng idempotency store.

`request_hash` là fingerprint của **canonicalized business payload**, không phải một chuỗi JSON serialize ngẫu nhiên có thứ tự fields khác nhau. Không log raw payload nhạy cảm; hash cần có chính sách phù hợp khi input chứa dữ liệu có entropy thấp hoặc cần chống suy đoán.

### 5.2. Transaction cần bao gồm idempotency result và business state

~~~mermaid
sequenceDiagram
    participant C as Client
    participant T as Inventory Service
    participant D as PostgreSQL
    C->>T: Reserve(operationId, requestHash)
    T->>D: BEGIN
    T->>D: INSERT idempotency row ON CONFLICT DO NOTHING
    alt Key mới
        T->>D: INSERT reservation
        T->>D: UPDATE idempotency state=COMPLETED + receipt
        T->>D: COMMIT
        D-->>T: Commit OK
    else Key tồn tại
        T->>D: Read stored hash/state/receipt
        D-->>T: Existing result
    end
    T-->>C: Return stored receipt
~~~

Nếu insert idempotency row và insert reservation **không cùng transaction**, dễ có trạng thái “key đã xử lý” nhưng reservation chưa được ghi hoặc ngược lại.

### 5.3. PostgreSQL claim operation bằng unique key

~~~sql
INSERT INTO api_idempotency (
    consumer_name, operation_id, request_hash, state)
VALUES (
    'inventory-reserve', :operationId, :requestHash, 'PROCESSING')
ON CONFLICT (consumer_name, operation_id) DO NOTHING;
~~~

Trong **cùng SQL transaction** khi claim thành công:

~~~sql
INSERT INTO inventory_reservations (
    reservation_id, operation_id,
    order_id, sku, quantity, state)
VALUES (
    :reservationId, :operationId,
    :orderId, :sku, :quantity, 'CONFIRMED');
~~~

~~~sql
UPDATE api_idempotency
   SET state = 'COMPLETED',
       response_json = CAST(:receiptJson AS jsonb),
       completed_at = CURRENT_TIMESTAMP
 WHERE consumer_name = 'inventory-reserve'
   AND operation_id = :operationId;
~~~

Sau đó COMMIT. Nếu transaction rollback, các writes cùng rollback. Nếu hai requests trùng key đến đồng thời, PostgreSQL unique index/transaction isolation giúp đồng bộ xung đột insert; request thua cần **đọc lại trạng thái sau khi winner COMMIT** hoặc trả `IN_PROGRESS` theo policy, không cứ giả định data đã sẵn.

### 5.4. Pseudocode application service

~~~java
@Transactional
public ReservationReceipt reserve(
        UUID operationId,
        String fingerprint,
        ReserveCommand command) {

    boolean claimed = idempotencyStore.tryClaim(
            "inventory-reserve", operationId, fingerprint);

    if (!claimed) {
        StoredOperation previous =
                idempotencyStore.find("inventory-reserve", operationId);

        if (!previous.requestHash().equals(fingerprint)) {
            throw new IdempotencyPayloadMismatchException();
        }

        if (previous.completed()) {
            return previous.receipt();
        }
        throw new OperationInProgressException();
    }

    ReservationReceipt receipt =
            reservationRepository.insertReservation(
                    operationId, command);

    idempotencyStore.complete(
            "inventory-reserve", operationId, receipt);

    return receipt;
}
~~~

`idempotencyStore`, `ReserveCommand`, `ReservationReceipt` và exceptions ở đây là **interfaces/classes của ứng dụng**, không phải API sẵn có của Spring. Pseudocode giả định `tryClaim` dùng SQL atomic, các thao tác dùng **cùng DataSource/transaction manager**, và `@Transactional` được gọi qua Spring proxy.

**Không đưa HTTP calls bên ngoài vào transaction này** rồi tưởng có thể rollback side effect ở hệ thống khác. Nếu reservation phải gọi một ERP, target có thể dùng outbox nội bộ để durable handoff.

### 5.5. Vấn đề crash giữa claim và completion

Nếu `PROCESSING` chỉ tồn tại trong **transaction chưa COMMIT**, khi process crash trước COMMIT cả claim và reservation rollback, retry có thể claim lại. Nếu bạn COMMIT claim sớm rồi làm business write ở transaction sau, phải thiết kế **lease, trạng thái IN_PROGRESS và recovery**; không để key mắc kẹt vĩnh viễn.

### 5.6. Idempotency retention và payload mismatch

Một contract đầy đủ cần trả lời:

- Key còn được nhận diện bao lâu?
- Nếu retry sau khi key đã bị xóa, có nguy cơ duplicate không?
- Nếu cùng key nhưng body khác, hệ thống từ chối hay dùng kết quả cũ?
- Nếu response chứa trường thay đổi theo thời gian, replay nguyên receipt hay dựng state mới?
- Nếu đầu tiên trả lỗi 5xx sau khi transaction rollback, có lưu “failure” làm kết quả cố định không?
- Nếu operation đã được accepted nhưng work đang chạy, trả status nào?
- Nếu số lượng order rows quá lớn, cần archival/tombstone để key cũ không hồi sinh command không?

Đối với side effect rủi ro cao, retention phải tương thích **cửa sổ retry/replay thực tế**, kể cả broker DLQ, worker outage và manual replay.

## 6. Mô phỏng HTTP mất kết nối trước khi đích nhận

Muốn thực sự test tình huống **đích chưa nhận**, điều khiển fault ở proxy/network **trước khi gửi request đến target**.

### 6.1. Kịch bản A: connection refused

Một client gọi host:port mà không có process lắng nghe:

~~~text
Order Service
    |
    +-- TCP connect → ECONNREFUSED
    |
    x  Target HTTP handler không chạy trên connection này
~~~

Nếu chứng minh endpoint cụ thể **không chấp nhận connection**, chưa có request trên connection đó. Nhưng không được suy luận rằng **toàn bộ business intent chưa từng đến** nếu trước đó client/SDK đã gửi attempt khác hoặc proxy có cơ chế retry ngầm.

Unit/integration test nên kiểm tra:

- Client phát connection exception theo error taxonomy.
- Không ghi `CONFIRMED` vào local business state chỉ vì `post()` đã được gọi.
- Outbox intent vẫn bền và có retry schedule.
- Retry không tạo operationId mới.
- HTTP client pool/timeout không làm request treo vô hạn.

### 6.2. Kịch bản B: TCP reset ngay sau connect, trước request body

Dùng một fault proxy trước target, cấu hình RST/drop từ client tới target **trước khi backend được forward bytes**. Kiểm tra:

1. Proxy ghi nhận connection được mở.
2. Target không ghi request-received record cho attempt đó.
3. Target DB không có row cho operationId.
4. Client thấy network failure.
5. Retry cùng operationId khi đường truyền khôi phục chỉ tạo một reservation.

Một WireMock/MockWebServer “disconnect at start” có thể minh họa lỗi transport, nhưng **không chứng minh behavior của target thật**. Muốn kết luận “target không nhận”, phải có **evidence từ phía target** hoặc proxy biết chính xác chưa forward.

### 6.3. Kịch bản C: gửi nửa body rồi cắt

HTTP request có body lớn (ví dụ import JSON/XML). Kết nối có thể đứt sau vài KB:

~~~text
POST /import Content-Length: 100000
  -> target receives first 4096 bytes
  -> client/proxy disconnects
  -> target cannot parse complete payload
~~~

Nhiều frameworks buffer/validate body trước khi gọi controller. Nhưng API streaming có thể thực hiện side effects **trước khi nhận đủ body**, nên không được mặc định partial request luôn an toàn.

Kiểm thử cần dùng parser/handler contract thực:

- Có atomic commit chỉ sau khi nhận đủ payload?
- Có cleanup phần tạm chưa commit?
- Target có lưu `multipart upload session` hoặc import checkpoint?
- Nếu client retry toàn file, có duplicate rows?
- Request size/timeout/streaming semantics có nhất quán không?

## 7. Mô phỏng HTTP đích đã nhận nhưng chưa commit

Đây là một cửa sổ quan trọng vì “request received” **không đồng nghĩa business completed**.

### 7.1. Dùng synchronization gates thay cho sleep

Một target test-only có thể đặt ba điểm đồng bộ:

~~~text
onRequestReceived:
    record RECEIVED(operationId)
    signal requestReceivedLatch
    await allowBusinessWriteLatch

businessWrite:
    BEGIN; insert business row; COMMIT
    signal committedLatch
    await allowResponseLatch

writeResponse:
    return receipt
~~~

Test điều khiển theo thứ tự:

1. Client gửi POST trong một async task.
2. Đợi `requestReceivedLatch` để biết target handler đã bắt đầu.
3. Cắt proxy connection **trước** khi cho write transaction.
4. Mở `allowBusinessWriteLatch` hoặc chủ động hủy operation theo contract.
5. Đọc target DB để biết side effect cuối cùng có xảy ra hay không.
6. Không dựa trên việc client thấy lỗi để kết luận.

**Không dùng `Thread.sleep(200)` làm bằng chứng request đã đến hoặc DB đã commit.** Scheduler/network latency thay đổi làm test flaky. Dùng `CountDownLatch`, barrier, database row/state hoặc event hooks với timeout hữu hạn.

### 7.2. Phải phân biệt “đã nhận” và “đã chấp nhận bền vững”

Một server có thể trả 202 sau khi ghi command vào bảng `pending_jobs`, rồi worker xử lý sau. Khi đó:

~~~text
HTTP handler received
   -> INSERT pending_jobs; COMMIT
   -> 202 Accepted
   -> background worker later modifies inventory
~~~

Nếu response 202 bị mất, client không biết **job record đã lưu** hay chưa; query theo operationId phải trả trạng thái `ACCEPTED/PENDING`. Nếu retry POST cùng key, target không tạo job thứ hai. Không trả “COMPLETED” ngay sau khi chỉ ghi pending job.

## 8. Mô phỏng đích đã COMMIT nhưng response bị mất

Đây là kịch bản trung tâm của bài: **sự kiện thành công ở server và lỗi nhìn thấy từ client cùng tồn tại**.

~~~mermaid
sequenceDiagram
    participant C as Order Service
    participant P as Fault Proxy
    participant T as Inventory Service
    participant D as PostgreSQL
    C->>P: POST Idempotency-Key=K-100
    P->>T: Forward request
    T->>D: INSERT reservation + idempotency receipt
    D-->>T: COMMIT OK
    T-->>P: HTTP 201 receipt
    P--xC: DROP response / TCP RESET
    C->>C: Timeout → mark UNKNOWN
    C->>P: GET /operations/K-100 or retry same key
    P->>T: Reconciliation
    T->>D: Find stored receipt K-100
    D-->>T: CONFIRMED, reservation R-500
    T-->>C: Same receipt (no new reservation)
~~~

### 8.1. Khác biệt quan trọng

- **Mất request:** target có thể không biết lệnh.
- **Mất response:** target có thể đã commit, chỉ có caller không biết.
- **Mất acknowledgement của broker:** broker có thể đã lưu event, producer không biết.
- **Mất consumer ACK:** consumer có thể đã commit SQL, broker có thể phát lại.

**Mọi trường hợp đều dẫn đến khả năng replay**, nhưng thời điểm và nơi cần idempotency khác nhau.

### 8.2. Một thiết kế sai dễ lặp side effect

~~~java
try {
    inventoryClient.reserve(orderId);
} catch (ResourceAccessException e) {
    // Sai: timeout không chứng minh server chưa reserve.
    inventoryClient.reserve(orderId);
}
~~~

Nếu `reserve(orderId)` sinh operationId ngẫu nhiên bên trong mỗi lần gọi, request thứ hai là một **business command mới** từ góc nhìn target.

### 8.3. Thiết kế tốt hơn

~~~java
String operationId = outboxIntent.operationId();
try {
    ReservationReceipt receipt =
            inventoryClient.reserve(operationId, command);

    outboxIntent.markConfirmed(receipt);
} catch (ResourceAccessException e) {
    // Không tạo operationId mới.
    outboxIntent.markUnknown(e.getClass().getSimpleName());
    reconciliationScheduler.schedule(operationId);
}
~~~

`outboxIntent`, `reconciliationScheduler` và `inventoryClient` là ứng dụng minh họa. Trạng thái phải được persist bền trong DB, không chỉ là biến Java. Không log raw Authorization header/token trong error logs.

## 9. Thực hành HTTP: test stub cắt response sau “commit”

Một cách kiểm thử mô phỏng bằng **OkHttp MockWebServer**: stub đếm số side effect dựa trên Idempotency-Key, thực hiện “commit” trong memory **trước khi** trả network fault. Sau đó client retry cùng key và nhận receipt cũ.

Đây là **test hợp đồng/transport có kiểm soát**, không thay thế PostgreSQL transaction test.

### 9.1. Test dependencies minh họa

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'

    // Chọn artifact/group tương thích OkHttp version của project.
    testImplementation 'com.squareup.okhttp3:mockwebserver:4.12.0'
}
~~~

Với OkHttp 5 hoặc Spring Boot versions khác, package/artifact cho MockWebServer có thể thay đổi; pin compatible version qua dependency management. Không sửa version production BOM chỉ để copy test.

### 9.2. Test “đích xử lý rồi socket bị đóng”

~~~java
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

import okhttp3.mockwebserver.Dispatcher;
import okhttp3.mockwebserver.MockResponse;
import okhttp3.mockwebserver.MockWebServer;
import okhttp3.mockwebserver.RecordedRequest;
import okhttp3.mockwebserver.SocketPolicy;

import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;

import static org.junit.jupiter.api.Assertions.*;

class LostResponseContractTest {

    @Test
    void commitsOnceEvenIfFirstResponseIsLost() throws Exception {
        var reservations =
                new ConcurrentHashMap<String, String>();
        var businessInserts = new AtomicInteger();
        var dropFirstResponse = new AtomicBoolean(true);

        try (var server = new MockWebServer()) {
            server.setDispatcher(new Dispatcher() {
                @Override
                public MockResponse dispatch(RecordedRequest request) {
                    if (!"/v1/reservations".equals(request.getPath())) {
                        return new MockResponse().setResponseCode(404);
                    }

                    String key = request.getHeader("Idempotency-Key");
                    if (key == null || key.isBlank()) {
                        return new MockResponse().setResponseCode(400);
                    }

                    // Mô phỏng business commit / persisted receipt:
                    String receipt = reservations.computeIfAbsent(
                            key, ignored -> {
                                businessInserts.incrementAndGet();
                                return "RES-500";
                            });

                    if (dropFirstResponse.getAndSet(false)) {
                        // Target stub đã lưu kết quả trước khi
                        // đóng kết nối mà không gửi HTTP response.
                        return new MockResponse()
                                .setSocketPolicy(
                                        SocketPolicy.DISCONNECT_AFTER_REQUEST);
                    }

                    return new MockResponse()
                            .setResponseCode(201)
                            .addHeader("Content-Type", "text/plain")
                            .setBody(receipt);
                }
            });

            server.start();

            RestClient client = RestClient.builder()
                    .baseUrl(server.url("/").toString())
                    .build();

            String operationId =
                    "d9c7590a-2544-4af1-a76e-438a1f1b6154";

            // Test setup phải vô hiệu hóa transparent retry
            // trong underlying HTTP transport nếu nó tự retry.
            assertThrows(RestClientException.class,
                    () -> reserve(client, operationId));

            assertEquals(1, businessInserts.get());

            String replayReceipt = reserve(client, operationId);

            assertEquals("RES-500", replayReceipt);
            assertEquals(1, businessInserts.get());
            assertEquals(1, reservations.size());
        }
    }

    private String reserve(RestClient client, String operationId) {
        return client.post()
                .uri("/v1/reservations")
                .header("Idempotency-Key", operationId)
                .contentType(MediaType.APPLICATION_JSON)
                .body("""
                        {"orderId":"ORD-100",
                         "sku":"SKU-A",
                         "quantity":2}
                        """)
                .retrieve()
                .body(String.class);
    }
}
~~~

**Cách đọc test:**

- `computeIfAbsent` mô phỏng logic **chỉ tạo một reservation cho một operationId**.
- `DISCONNECT_AFTER_REQUEST` tạo lỗi network sau khi stub nhận request; code dispatcher đã ghi simulated receipt.
- Client đầu tiên không nhận response; retry cùng key nhận lại `RES-500`.
- `businessInserts==1` là bằng chứng từ **target stub** rằng side effect logical chỉ chạy một lần.

**Giới hạn quan trọng:**

1. `ConcurrentHashMap` không bền sau restart và không thay SQL transaction; đây chỉ là **mô phỏng**.
2. Exact behavior của socket policy và transport retries phải xác minh theo MockWebServer/HTTP client version.
3. Nếu underlying HTTP transport tự retry ngầm, assertion “first call throws” có thể không đúng dù target đã thấy một fault. Khi cần test chính xác từng attempt, cấu hình transport không tự retry và assert server request count.
4. Một implementation idempotency dùng in-memory map như ví dụ này **không đủ** cho multi-pod/production.
5. Test chưa chứng minh request payload được so sánh fingerprint; cần test reuse key với body khác riêng.
6. Test chưa chứng minh DB commit và process restart; dùng Testcontainers/target application thật cho bước tiếp theo.

### 9.3. Test reuse key với payload khác

Một target đúng contract phải phát hiện:

~~~text
Key K-100, body {"sku":"A","quantity":2} -> reserve R-500
Key K-100, body {"sku":"B","quantity":7} -> conflict/mismatch
~~~

Không được trả receipt R-500 cho request B như thể đã thực hiện B, và cũng không được tạo reservation thứ hai dưới cùng key. Test assert response theo **contract đã công bố**, ví dụ 409 Conflict hoặc 422 Unprocessable Content nếu API chọn semantics đó.

### 9.4. Test hai calls đồng thời cùng key

Chạy 2+ clients đồng thời với cùng operationId. Mục tiêu:

- Một transaction tạo reservation.
- Request còn lại đợi, nhận receipt cũ hoặc trạng thái IN_PROGRESS theo policy.
- Không phát sinh race `existsByKey → insert`.
- Nếu first transaction rollback, attempt hợp lệ tiếp theo vẫn có thể tạo reservation.
- Số business rows = 1 sau cả hai kết thúc.
- Không có deadlock hoặc chờ vô hạn.

Bài test này nên dùng **PostgreSQL Testcontainers** với UNIQUE constraint và transaction thật, không tin `ConcurrentHashMap` là bằng chứng đủ.

## 10. Mô phỏng response loss bằng proxy thay vì sửa service

Một lựa chọn mạnh hơn là đặt **Toxiproxy** giữa Order Service và Inventory Service:

~~~text
Order Service
   |
   v
Toxiproxy listen port
   |
   v
Inventory Service → PostgreSQL
~~~

Proxy cho phép tạo latency, timeout, bandwidth limits hoặc cắt đường truyền **mà không sửa business code**. Tuy nhiên, cắt lúc nào là điều quyết định test có ý nghĩa.

### 10.1. Test fixture và mốc đồng bộ

Đích test-only cung cấp tín hiệu:

~~~text
requestReceivedLatch
businessCommittedLatch
responseReleaseLatch
~~~

Test script ý tưởng:

~~~text
1. Start Inventory + PostgreSQL + Toxiproxy.
2. Client gửi POST operationId K-100 qua proxy.
3. Chờ Inventory báo businessCommittedLatch.
4. Cắt đường proxy target -> client trước khi response đi qua.
5. Cho Inventory tiếp tục tạo response.
6. Client thấy IOException/timeout; không mark FAILED.
7. Query PostgreSQL trực tiếp: có reservation K-100.
8. Khôi phục proxy.
9. Client GET /operations/K-100 hoặc POST lại cùng key.
10. Assert receipt trùng, DB chỉ có một reservation.
~~~

**Cửa sổ test phải deterministic.** Nếu chỉ đặt proxy latency 500 ms rồi `Thread.sleep(100)` để cắt, không biết server đã commit hay chưa. Chờ `businessCommittedLatch` hoặc chứng cứ transaction row + chặn response trước khi release.

### 10.2. Hướng cut cho từng thí nghiệm

| Vị trí fault | Tác dụng mong muốn | Bằng chứng cần có |
| --- | --- | --- |
| Client → proxy trước connect | Client chưa gửi được attempt | Không có accepted connection cho attempt |
| Proxy → target trước forward | Target chưa nhận attempt | Target handler counter = 0 |
| Proxy → target sau forward một phần | Target nhận body thiếu | Request body bytes, validation/result |
| Target → proxy trước response | Target có thể commit nhưng không phản hồi | DB committed row + response suppressed |
| Proxy → client sau target COMMIT | Target đã hoàn thành, client không biết | Commit marker + client network error |
| Sau client receipt, trước local persist | Target + client đã trao đổi, caller crash | Target receipt + local intent vẫn pending |
| Broker → consumer trước delivery | Message tồn trong queue, chưa xử lý | Queue ready/durable state |
| Consumer → broker sau DB COMMIT | Consumer ACK mất | DB inbox committed + broker redelivery |

### 10.3. Fault APIs không được hardcode nhầm phiên bản

Toxiproxy Java API, Docker image và toxics có các tham số/version khác nhau. Khi viết automated tests, kiểm tra lại thư viện mà dự án đang pin (ví dụ Testcontainers Toxiproxy module và client toxic builder). Không lấy một snippet proxy `timeout` rồi khẳng định nó luôn cắt đúng sau COMMIT; **thời điểm fault injection phải do test gate quyết định**.

### 10.4. Proxy không thay target evidence

Proxy biết điều gì đã đi qua network link; nó không biết một SQL transaction đã COMMIT hay chưa. Để xác nhận sau COMMIT, cần:

- Database row/transaction receipt.
- Application-level commit marker hoặc event bền.
- Deterministic test barrier sau khi commit thành công.
- Correlation operationId khớp giữa request, DB và logs.

Nếu chỉ có proxy TCP logs, kết luận “target đã xử lý” là suy diễn thiếu bằng chứng.

## 11. Bảng tình huống HTTP cần tự động hóa

| ID | Fault | Đích có side effect? | Kỳ vọng caller | Kỳ vọng sau recover |
| --- | --- | --- | --- | --- |
| HTTP-01 | DNS/connect fail trước request | Không cho attempt đó | Transient / pending retry | Một operation |
| HTTP-02 | Reset trước target handler | Không | UNKNOWN hoặc transport failure | Một operation |
| HTTP-03 | Body gửi một phần | Tùy handler, test contract | UNKNOWN | Không duplicate |
| HTTP-04 | Handler received, validation reject | Không business commit | Explicit rejection nếu có receipt | Không retry không phù hợp |
| HTTP-05 | DB rollback, response lost | Không committed reservation | UNKNOWN, query/retry cùng key | Có thể thực hiện một lần |
| HTTP-06 | DB COMMIT, response lost | **Có** | UNKNOWN | Một reservation, replay receipt cũ |
| HTTP-07 | Target sends 201, proxy drops | **Có** | UNKNOWN | Một reservation |
| HTTP-08 | Client got 201, local DB write fails | **Có** | Pending/UNKNOWN after crash | Reconcile, không duplicate |
| HTTP-09 | Two concurrent same-key requests | Tối đa một business write | One success + replay/in-progress | Một row |
| HTTP-10 | Same key, different payload | Không side effect thứ hai | Conflict/mismatch | Không mutation |
| HTTP-11 | Retry sau server restart | Trước đó có commit | UNKNOWN -> confirmed | Persistence của idempotency survives |
| HTTP-12 | Target async 202 then worker fails | Accepted, chưa hoàn tất | PENDING | Status FAILED/RETRY hoặc completed tùy policy |
| HTTP-13 | Target 429/503 trước xử lý | Thường không, nhưng kiểm tra contract | Bounded retry/backoff | Không retry storm |
| HTTP-14 | Timeout sau remote side effect | **Có thể** | UNKNOWN | Status lookup/idempotent retry |
| HTTP-15 | Retry key retention expired | Có thể đã commit từ lâu | Không mặc định retry | Manual reconciliation/retention policy |

Không phải mọi hàng đều có cùng retry policy. Một response `400` do payload sai không sửa được bằng retry; `429` yêu cầu quota/backoff; timeout sau write là UNKNOWN dù exception có vẻ “network transient”.

## 12. Spring Boot RestClient: chính sách cho kết quả không chắc chắn

`RestClient` trong Spring Framework 6.1+ là client HTTP đồng bộ phổ biến, có thể dùng trong Spring Boot 3.2+.

### 12.1. Tách HTTP adapter theo downstream

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;

@Configuration(proxyBeanMethods = false)
class InventoryClientConfiguration {

    @Bean
    RestClient inventoryRestClient(RestClient.Builder builder) {
        return builder
                .baseUrl("https://inventory.example.org")
                .build();
    }
}
~~~

Trong production, `baseUrl` nên đến từ externalized config, có HTTPS/TLS trust, auth, pool, connect/read timeouts và observability riêng. **HTTP request factory không mặc định bảo đảm một timeout tổng phù hợp**; cấu hình theo transport cụ thể.

### 12.2. API adapter gắn operationId

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

@Component
class InventoryHttpGateway {

    private final RestClient client;

    InventoryHttpGateway(
            @Qualifier("inventoryRestClient") RestClient client) {
        this.client = client;
    }

    ReservationReceipt reserve(
            String operationId, ReserveCommand command) {

        return client.post()
                .uri("/v1/reservations")
                .header("Idempotency-Key", operationId)
                .contentType(MediaType.APPLICATION_JSON)
                .body(command)
                .retrieve()
                .body(ReservationReceipt.class);
    }
}
~~~

`ReserveCommand` và `ReservationReceipt` là domain DTO minh họa. Đừng lưu raw Authorization header/access token trong DB outbox hoặc request log; worker lấy credential khi thực thi.

### 12.3. Timeout phải phân loại đúng

| Lỗi | Điều có thể suy ra | Điều không nên suy ra |
| --- | --- | --- |
| Connect refused | Không mở được connection cho attempt hiện tại | Chưa có attempt khác được xử lý |
| TLS handshake failed | Connection TLS không hoàn tất theo client | Remote không có side effect từ request khác |
| Pool acquisition timeout | Chưa mượn connection từ pool cho attempt này | Business intent tổng thể chưa bao giờ gửi |
| Write failure | Write chưa hoàn tất theo client | Remote chưa nhận partial/full bytes |
| Read timeout | Không nhận response đúng hạn | Remote chưa commit |
| Connection reset | Connection bị cắt | Không biết server đã nhận/commit |
| HTTP 502/504 từ proxy | Proxy/gateway lỗi/timeout | Backend chắc chắn chưa xử lý |
| HTTP 409 | Có conflict theo contract | Tự động retryable hay không |
| HTTP 202 | Request accepted theo contract | Business completed |
| HTTP 201 với receipt bền | Có bằng chứng theo API contract | Worker ngoài contract cũng thành công |

Tránh một generic catch `Exception` rồi `markFailed`. Map network errors thành **unknown outcome** hoặc retry-scheduled state theo operation contract, đồng thời ghi error category để điều tra.

### 12.4. Retry policy nên nhìn theo business semantics

- GET thuần đọc có thể retry theo HTTP semantics nếu không có side effect ẩn.
- PUT theo resource ID có thể idempotent **nếu API thực sự làm đúng contract**.
- POST thay đổi nghiệp vụ cần server-side idempotency key/status lookup.
- Retry 429/503 cần exponential backoff với jitter, Retry-After khi phù hợp.
- Không retry 401/403/invalid credentials vô hạn.
- Mỗi operation có **tổng deadline** và maximum attempts.
- Khi remote outcome UNKNOWN, không publish một logical command mới với ID mới.
- Client SDK có thể có **transparent retry**; kiểm tra cấu hình tổng các tầng để tránh nhân attempts.

## 13. SOAP, XML và những endpoint không có Idempotency-Key

Một hệ thống legacy SOAP có thể chỉ có operation:

~~~xml
<ReserveOrder>
    <ExternalOrderId>ORD-100</ExternalOrderId>
    <Sku>SKU-A</Sku>
    <Quantity>2</Quantity>
</ReserveOrder>
~~~

Nếu SOAP response mất sau commit, retry vẫn có thể duplicate. HTTP Basic/TLS, WS-Security Signature hay XML schema validation **không cung cấp idempotency**.

### 13.1. Nếu partner hỗ trợ business key

Dùng `ExternalOrderId`/`OperationId` ổn định, yêu cầu partner dedupe bằng unique constraint hoặc trả receipt cũ. Với payment, thường cần `merchantTransactionId` hoặc request ID do provider hỗ trợ.

### 13.2. Nếu partner không hỗ trợ idempotency

Cần chọn một trong những chiến lược an toàn hơn:

1. **Query status** theo business reference trước khi retry.
2. **Reconciliation** qua report/batch/API của partner.
3. **Human approval** đối với side effect chi phí cao.
4. Workflow với trạng thái UNKNOWN và timeout SLA rõ.
5. Compensation nếu business contract hỗ trợ (cancellation/refund), nhưng compensation không tương đương rollback ACID.
6. Giới hạn khả năng retry; không tự động phát lại vô hạn.

**Không thể đạt exactly-once end-to-end** bằng một phía client đơn lẻ nếu target không hỗ trợ cách nhận diện logical operation, kiểm tra trạng thái hoặc một giao thức giao dịch phù hợp.

## 14. Producer: “broker đã nhận nhưng ACK bị mất”

Mô hình giống HTTP response loss nhưng chủ thể xác nhận là **broker**.

~~~mermaid
sequenceDiagram
    participant P as Order Producer
    participant B as RabbitMQ / Kafka
    participant R as Consumer
    P->>B: Publish eventId E-100
    B->>B: Accept/persist theo broker policy
    B--xP: Producer ACK / confirm lost
    P->>P: Publish outcome UNKNOWN
    P->>B: Retry eventId E-100
    B->>R: Deliver possibly duplicated E-100
    R->>R: Deduplicate by eventId
~~~

Nếu producer thấy timeout khi chờ confirms, broker **có thể đã ghi message**, chỉ producer không biết. Do đó:

- Outbox eventId ổn định qua retry.
- Consumer phải idempotent.
- Đo producer attempted vs broker confirmed vs consumer applied riêng.
- Không tạo “event mới” với eventId khác cho cùng outbox intent.

### 14.1. RabbitMQ publisher confirm

Rabbit publisher confirms báo broker đã xử lý publish theo cơ chế confirm. Khi dùng `mandatory=true` và publisher returns, có thể phân biệt unroutable message; **publisher ACK không đồng nghĩa message đã route được tới queue mong muốn nếu không xét return/route contract**.

Ví dụ cấu hình Boot minh họa:

~~~yaml
spring:
  rabbitmq:
    publisher-confirm-type: correlated
    publisher-returns: true
    template:
      mandatory: true
~~~

Cần cấu hình exchanges/queues/bindings, message persistence/quorum/durable topology phù hợp. Nếu broker connection bị cắt **sau khi broker accepted nhưng trước confirm về producer**, confirm future có thể fail/timeout trong khi message vẫn tồn tại.

### 14.2. Kafka producer ACK

Kafka `acks=all` yêu cầu broker acknowledgement theo replicated log/ISR policy, nhưng không chứng minh consumer đã xử lý. Idempotent producer giảm duplicate từ **retry của cùng producer session** theo protocol/broker semantics; nó không tự chống **business command được publish lại bởi một process khác với producer identity mới**.

~~~yaml
spring:
  kafka:
    producer:
      acks: all
      properties:
        enable.idempotence: true
~~~

Kafka transactions/exactly-once semantics có phạm vi nhất định trong Kafka read-process-write workflows; **không tự bao trùm PostgreSQL hoặc HTTP remote transaction**. Với outbox relay publish lại cùng logical event sau crash, consumer inbox/unique business key vẫn cần thiết.

## 15. Consumer: “DB đã COMMIT nhưng ACK/offset commit bị mất”

Đây là chiều ngược lại của mất publisher confirm.

~~~mermaid
sequenceDiagram
    participant B as Broker
    participant C as Consumer
    participant D as PostgreSQL
    B->>C: Deliver E-100
    C->>D: BEGIN + inbox unique insert + business update
    D-->>C: COMMIT OK
    C--xB: Consumer ACK lost / connection closed
    B->>C: Redelivery E-100
    C->>D: Inbox indicates already applied
    C-->>B: ACK duplicate safely
~~~

Không có một cách giải quyết bằng connection timeout. **ACK sau COMMIT + inbox idempotency** là một pattern thực tế cho at-least-once delivery.

### 15.1. RabbitMQ manual ACK

~~~java
@RabbitListener(
        queues = "inventory.order-events",
        containerFactory = "manualAckListenerFactory")
public void onMessage(
        OrderEvent event,
        com.rabbitmq.client.Channel channel,
        @Header(AmqpHeaders.DELIVERY_TAG) long tag)
        throws java.io.IOException {

    inventoryService.applyIdempotently(event); // SQL COMMIT

    channel.basicAck(tag, false);              // ACK sau COMMIT
}
~~~

Ví dụ giả định `manualAckListenerFactory` cấu hình `AcknowledgeMode.MANUAL`, `inventoryService` có transaction và SQL inbox atomic, `OrderEvent` là DTO ứng dụng. Cần thêm imports cho `@RabbitListener`/`@Header`/`AmqpHeaders` và error path. Manual ACK phải được gửi **trên đúng channel nhận delivery**; không lưu tag để ACK từ channel khác.

**Test bắt buộc:** ép broker/channel disconnect sau SQL COMMIT trước `basicAck`, rồi assert redelivery E-100 không tăng business count.

### 15.2. RabbitMQ AUTO ACK khác NONE

Spring AMQP `AcknowledgeMode.AUTO` thường có nghĩa **container gửi consumer ACK sau khi listener method hoàn tất thành công**, không phải RabbitMQ auto-ack-on-delivery. `AcknowledgeMode.NONE` mới ứng với broker auto-ack-on-delivery. Với transactional service đồng bộ, AUTO có thể phù hợp nếu method chỉ return sau SQL COMMIT.

Nếu method chỉ `executor.submit(...)` rồi return, AUTO có thể ACK quá sớm trước khi task RAM chạy; virtual threads không giải quyết được điều này.

### 15.3. Kafka offset commit

~~~java
@KafkaListener(topics = "orders.events")
public void consume(
        ConsumerRecord<String, OrderEvent> record,
        Acknowledgment acknowledgment) {

    inventoryService.applyIdempotently(record.value());
    acknowledgment.acknowledge(); // Theo ack-mode đã cấu hình.
}
~~~

Ví dụ giả định `Acknowledgment` được Spring Kafka inject và listener dùng manual acknowledgement mode phù hợp. Khi SQL COMMIT thành công nhưng offset commit fail, Kafka redeliver. Nếu offset commit **trước** SQL COMMIT, consumer có thể mất khả năng tự replay khi DB rollback.

Kafka partition ordering và concurrency vẫn quan trọng: eventId dedupe không tự bảo đảm events E-2/E-1 của cùng order được áp dụng đúng version. Cần version guard/state transition checks.

## 16. Inbox SQL cho consumer idempotent

Một inbox được commit cùng business update:

~~~sql
CREATE TABLE processed_integration_events (
    consumer_name VARCHAR(100) NOT NULL,
    event_id UUID NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (consumer_name, event_id)
);
~~~

Với PostgreSQL:

~~~java
import java.util.UUID;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class InventoryEventService {

    private final JdbcTemplate jdbc;

    public InventoryEventService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void applyIdempotently(OrderEvent event) {
        int inserted = jdbc.update(
                """
                INSERT INTO processed_integration_events(
                    consumer_name, event_id)
                VALUES ('inventory', ?)
                ON CONFLICT (consumer_name, event_id) DO NOTHING
                """,
                UUID.fromString(event.eventId()));

        if (inserted == 0) {
            return; // Đã xử lý cùng logical event.
        }

        jdbc.update(
                """
                INSERT INTO inventory_projection(
                    order_id, version, state)
                VALUES (?, ?, 'RESERVED')
                ON CONFLICT (order_id)
                DO UPDATE SET
                    version = EXCLUDED.version,
                    state = EXCLUDED.state
                WHERE inventory_projection.version < EXCLUDED.version
                """,
                event.orderId(),
                event.aggregateVersion());
    }
}
~~~

Đoạn code đòi migration tạo `inventory_projection` với UNIQUE/PRIMARY KEY `order_id` và cột `version`. Nếu update projection fail, transaction rollback cả inbox insert. Nếu event có version cũ hơn, conditional update tránh ghi đè state mới.

**Phân biệt:** inbox chặn **cùng eventId** xử lý hai lần; version guard chặn **event khác ID nhưng đến sai thứ tự**.

## 17. Outbox: bảo vệ “local commit rồi mất kết nối trước publish”

Một producer thường vừa ghi business state vừa muốn publish event sang RabbitMQ/Kafka.

Nếu code làm:

~~~java
@Transactional
public void confirmOrder(Order order) {
    repository.save(order);
    rabbitTemplate.convertAndSend(
            "orders.events", "order.confirmed", order);
}
~~~

thì `@Transactional` với JDBC transaction manager **không tự biến RabbitMQ publish thành cùng ACID transaction**. Broker nhận nhưng DB rollback, hoặc DB COMMIT mà publish fail là hai failure windows khác nhau.

### 17.1. Mẫu outbox

~~~mermaid
flowchart LR
    A["Business command"] --> T["SQL transaction"]
    T --> O["Update order"]
    T --> E["Insert outbox eventId"]
    O --> C["COMMIT"]
    E --> C
    C --> W["Outbox relay"]
    W --> B["Broker or HTTP partner"]
    W --> R["Receipt/confirm or UNKNOWN"]
    R --> U["Retry/reconciliation"]
~~~

SQL schema giản lược:

~~~sql
CREATE TABLE integration_outbox (
    event_id UUID PRIMARY KEY,
    aggregate_id VARCHAR(120) NOT NULL,
    event_type VARCHAR(100) NOT NULL,
    payload JSONB NOT NULL,
    status VARCHAR(30) NOT NULL,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
~~~

Outbox relay cần cơ chế **claim/lease** nếu có nhiều pods. Với PostgreSQL có thể dùng `SELECT ... FOR UPDATE SKIP LOCKED` trong transaction ngắn và ghi lease/status. Không giữ SQL transaction mở nhiều giây chỉ để chờ HTTP response hoặc broker confirm.

### 17.2. Crash sau broker accepted trước outbox status update

~~~text
Outbox row PENDING(E-100)
    |
    +-- relay publish E-100
    +-- broker accepted E-100
    +-- producer confirm LOST / relay crashes
    |
    +-- outbox still PENDING
    +-- relay restarts, publishes E-100 again
    |
    +-- consumer inbox deduplicates E-100
~~~

Đây là *at-least-once delivery with idempotent processing*, không phải "exactly-once publish". Đổi outbox eventId mỗi attempt phá vỡ khả năng dedupe.

### 17.3. Retry budget và DLQ

Nếu outbox relay retries 5 lần, RabbitMQ consumer retries 3 lần và HTTP adapter retries 3 lần, tổng số side-effect attempts có thể nhiều hơn dự kiến. Cần quản lý **retry budget xuyên tầng**, DLQ/parking, reconciliation và alert. Một lỗi hợp đồng dữ liệu permanent không nên retry nóng.

## 18. Mất kết nối ở JDBC: COMMIT outcome unknown

Một client JDBC gửi `COMMIT` tới database nhưng connection đứt trước khi nó nhận ACK. Khi đó:

~~~text
Client: COMMIT request sent
DB:    COMMIT may have succeeded
Link:  connection reset before response
Client: transaction outcome UNKNOWN
~~~

Không được luôn coi exception ở `connection.commit()` là chứng minh transaction rollback. Driver/JTA/runtime có semantics riêng, nhưng về nguyên lý distributed communication, **ACK của COMMIT có thể mất sau khi DB đã commit**.

### 18.1. Retry có thể tạo hai business rows

Nếu code:

~~~java
try {
    insertOrderWithGeneratedId(command);
} catch (CannotGetJdbcConnectionException ex) {
    insertOrderWithGeneratedId(command); // Risky!
}
~~~

và client đã mất connection sau một COMMIT thành công, request thứ hai có thể tạo một order mới với ID khác.

Đối sách:

- Business identity/commandId có UNIQUE constraint.
- Insert/upsert theo stable key.
- Khi exception có outcome unknown, tra cứu DB bằng stable key.
- Không tạo ID/key mới cho cùng command.
- Nếu DB failover/read replica có độ trễ, đợi consistent read theo contract.
- Phân biệt deadlock/serialization rollback đã biết với COMMIT acknowledgement loss.

### 18.2. Không lạm dụng @Transactional

Spring `@Transactional` không làm biến mất commit ambiguity do network partition. Nó cung cấp local transaction management, nhưng ứng dụng vẫn cần business idempotency, reconciliation, constraint và retry policy.

## 19. Redis: write acknowledged vs durable state

Redis `SET` có thể trả `OK`, nhưng kết nối đứt sau khi Redis thực thi command và trước khi client nhận response. Một retry `INCR` sẽ nhân đôi tác động:

~~~text
INCR stock_counter
  → Redis đã tăng từ 10 lên 11
  → reply lost
  → client retries INCR
  → tăng lên 12
~~~

Các lệnh như `SET key value` có thể idempotent theo semantics của cùng value, nhưng `INCR`, `LPUSH`, `XADD` và script có side effects cần kiểm tra kỹ. Redis persistence/replication durability còn phụ thuộc AOF/RDB, replication, failover và cấu hình.

### 19.1. Thử nghiệm Redis

1. Khởi động Redis Testcontainers.
2. Dùng proxy cắt response sau khi server nhận/execute `INCR`.
3. Đọc counter trực tiếp từ server độc lập.
4. Retry với cùng business operationId theo dedupe Lua/SQL contract.
5. Assert counter chỉ tăng một lần.
6. Test restart/failover nếu durability là yêu cầu.

Không thể biến `INCR` thành exactly once chỉ bằng việc tăng timeout. Nếu Redis là cache, có thể chấp nhận retry/sai lệch nhất thời; nếu đó là ledger tồn kho/thanh toán, nên lưu authoritative state trong database có uniqueness/transactions phù hợp.

## 20. Mô phỏng các fault với Testcontainers

Sử dụng môi trường test tách biệt, không chạy chaos trên hệ thống production thật. Một topology điển hình:

~~~mermaid
flowchart TD
    T["JUnit / SpringBootTest"] --> O["Order Service test"]
    O --> PX["ToxiproxyContainer"]
    PX --> I["Inventory target test service"]
    I --> DB["PostgreSQLContainer"]
    O --> R["RabbitMQContainer / KafkaContainer"]
    R --> C["Consumer test app"]
    C --> DB
~~~

### 20.1. Những thành phần cần bảo đảm

- **PostgreSQL Testcontainers**: xác minh commit/rollback và UNIQUE constraints thực tế.
- **MockWebServer/WireMock**: tạo lỗi HTTP, kiểm tra headers/body và response drop.
- **Toxiproxy**: tác động transport theo hướng cụ thể, tạo partition, latency hoặc reset.
- **RabbitMQ/Kafka Testcontainers**: publisher confirm, consumer ACK/offset commit và redelivery.
- **CountDownLatch/barrier**: đồng bộ chính xác trước/sau mốc commit.
- **Outbox/inbox schema migrations**: chạy đúng production DDL.
- **Logs/counters**: gắn operationId vào target evidence, không chỉ client exception.
- **Cleanup**: đóng proxies/containers, release latches trong `finally` để không treo tests.

### 20.2. Không dùng thời gian ngủ cố định làm mốc fault

~~~java
// Flaky: không biết phía đích đang ở giai đoạn nào.
Thread.sleep(100);
proxy.disconnect();
~~~

~~~java
// Ý tưởng tốt hơn với test barrier:
assertTrue(targetCommitted.await(5, TimeUnit.SECONDS));
proxy.disconnectResponsePath();
allowTargetResponse.countDown();
~~~

`proxy.disconnectResponsePath()` là pseudocode cho control API tương ứng của test proxy, không phải phương thức có sẵn từ một Toxiproxy Java client cụ thể. Khi triển khai thật, phải chọn toxic/cut action theo đúng library version.

### 20.3. Timeouts bắt buộc cho mọi latch

Một testcase có fault injection có thể làm target không bao giờ đến một mốc. Mọi `await` phải có timeout và assertion; `finally` release các gates để threads/sockets không bị treo vô hạn. Điều này đặc biệt quan trọng khi chạy CI song song.

## 21. Kiểm thử định kỳ kịch bản “đã nhận nhưng mất ACK”

Một hệ thống integration tốt nên có một tập regression tests với ma trận nhỏ nhưng chắc:

### 21.1. Acceptance criterion với HTTP

~~~text
Given một operationId K-100 và payload P
And Inventory target có transactional idempotency
When Inventory COMMIT reservation K-100
And response bị cắt trước khi Order Service nhận
Then Order Service ghi trạng thái UNKNOWN/PENDING_RECONCILIATION
And Inventory chỉ có 1 reservation cho K-100
When Order Service tra cứu hoặc retry với cùng K-100
Then nhận lại receipt ban đầu
And Inventory vẫn chỉ có 1 reservation
~~~

### 21.2. Acceptance criterion với publisher

~~~text
Given outbox event E-100 PENDING
When broker accepted message E-100
And producer confirm bị mất
Then outbox không tự coi là thất bại vĩnh viễn
When relay retry E-100
Then consumer side effect được áp một lần
And outbox cuối cùng có trạng thái confirmed/reconciled
~~~

### 21.3. Acceptance criterion với consumer

~~~text
Given consumer nhận E-100
When DB COMMIT inbox + projection
And consumer ACK/offset commit bị mất
Then broker có thể redeliver E-100
When consumer nhận lại E-100
Then inbox chặn duplicate business write
And consumer ACK/commit progress thành công
~~~

### 21.4. Acceptance criterion với local caller crash

~~~text
Given target trả HTTP 201 cho K-100
And Order Service crash trước khi cập nhật outbox row
When Order Service restart
Then outbox vẫn có durable intent K-100
And retry/reconciliation dùng cùng key
And target chỉ có một reservation
~~~

### 21.5. Negative cases quan trọng

- Replay cùng key nhưng payload khác → conflict, không tạo side effect.
- Retry sau retention expiry → policy rõ, không âm thầm duplicate.
- Two concurrent requests cùng key → một durable business write.
- Target COMMIT fail → không lưu receipt COMPLETED.
- Target trả 202 nhưng worker fail → caller không được đánh dấu CONFIRMED.
- Read replica lag → GET status tạm 404 không gây retry tạo command mới.
- OperationId thiếu/không hợp lệ → reject sớm.
- Timeout sau write → UNKNOWN, không coi là rollback.
- Consumer nhận event cũ version thấp → version guard tránh ghi đè.
- Broker unrouteable → publisher return/retry/DLQ policy phù hợp.

## 22. Quan sát đúng “đã nhận”, “đã commit”, “đã biết kết quả”

Các tín hiệu cần tách:

| Metric hoặc sự kiện | Ý nghĩa |
| --- | --- |
| `integration.outbound.attempted` | Client bắt đầu một attempt |
| `integration.outbound.bytes_written` | HTTP transport đã ghi bytes (nếu có instrumentation) |
| `integration.target.request_received` | Target handler nhận request |
| `integration.target.business_committed` | Target business transaction COMMIT |
| `integration.outbound.response_received` | Client nhận response |
| `integration.outbound.outcome_unknown` | Caller không có đủ bằng chứng |
| `integration.outbox.pending_age` | Durable intents chưa resolved |
| `integration.reconciliation.success` | UNKNOWN được xác minh |
| `integration.idempotency.replayed` | Target trả receipt cũ |
| `integration.idempotency.conflict` | Same key, different payload |
| `integration.consumer.duplicate` | Consumer phát hiện event trùng |
| `integration.publisher.confirmed` | Broker confirmed theo policy |
| `integration.consumer.business_applied` | SQL/domain side effect commit |
| `integration.consumer.ack_failed` | ACK/offset commit không thành công |

Các tên metric trên là **đề xuất instrumentation của ứng dụng**, không khẳng định Micrometer/Actuator tự cung cấp toàn bộ. Cần định nghĩa và đo rõ, tránh lẫn `business_committed` với chỉ `request_received`.

### 22.1. Correlation và cardinality

Trong structured logs có thể dùng `operationId`/`eventId` với quyền truy cập, retention và redaction phù hợp để điều tra một trường hợp. Nhưng Prometheus metric labels cần cardinality thấp như `downstream=inventory`, `stage=response_lost`, `outcome=unknown`; **không đặt operationId/orderId/token vào metric labels**.

### 22.2. Đừng log secrets

Không log Authorization header, Basic credential, API key, OAuth2 access token, client secret, database password hoặc raw PII payload trong trace. Khi cần fingerprint payload, hash/canonicalization phải theo contract và không tạo khả năng suy ra secret nhạy cảm.

### 22.3. Một trace với missing response

~~~text
trace / operationId K-100
  10:00:00.000 client POST started
  10:00:00.010 target request received
  10:00:00.030 target transaction committed R-500
  10:00:00.031 proxy reset response
  10:00:02.000 client read timeout (UNKNOWN)
  10:00:05.000 reconciliation GET K-100
  10:00:05.010 target returns CONFIRMED R-500
  10:00:05.020 client state updated CONFIRMED
~~~

Đây là timeline minh họa. Thực tế clocks có skew, logs có thể out of order; dùng operationId và causal markers, không chỉ sắp xếp timestamp để “chứng minh” mốc.

## 23. Runbook khi timeout mà chưa biết đích đã nhận chưa

| Triệu chứng | Nguy cơ | Hành động |
| --- | --- | --- |
| Client read timeout sau POST | Target có thể đã commit | Đặt UNKNOWN, query status/key |
| Connection reset sau request bytes | Target có thể đã xử lý | Kiểm target receipt/DB |
| Gateway 504 nhưng target logs có COMMIT | Duplicate nếu retry key mới | Retry cùng key hoặc reconcile |
| HTTP 202 mất response | Job có thể đã persisted | Query operationId |
| Publisher confirm timeout | Broker có thể đã nhận event | Retry cùng eventId, consumer inbox |
| Rabbit consumer ACK fail | DB có thể đã commit | Dedupe khi redelivery |
| Kafka offset commit fail | Record có thể được xử lý | Inbox + replay safety |
| JDBC COMMIT ack lost | DB outcome unknown | Query theo stable business key |
| Redis INCR timeout | Counter có thể đã tăng | Không retry INCR mù |
| Idempotency table miss trên read replica | Replica lag | Consistent read/primary lookup |
| DLQ tăng | Poison messages hoặc retry exhausted | Điều tra contract, replay có kiểm soát |
| Retries tăng đột biến | Retry storm gây overload | Rate-limit, backoff/jitter, circuit breaker |
| 409 khi key reuse | Mismatch payload hoặc operation đang xử lý | So fingerprint/status contract |
| 2 reservations cùng operationId | Server idempotency lỗi | Incident, reconciliation, unique constraint |

### 23.1. Quy trình điều tra một UNKNOWN

1. Lấy stable `operationId` từ source intent/outbox.
2. Xác định request/publish attempts và response/confirm evidence.
3. Phân biệt network failure xảy ra **trước request, sau receipt hay sau commit** bằng target evidence.
4. Query operation status/target database theo contract và consistent read.
5. Nếu CONFIRMED, cập nhật local state bằng receipt, **không phát command mới**.
6. Nếu REJECTED rõ, ghi lý do/compensation theo policy.
7. Nếu PENDING, lên lịch kiểm tra lại với deadline.
8. Nếu UNKNOWN kéo dài, dùng idempotent replay hoặc manual reconciliation theo risk.
9. Lưu audit quyết định, không sửa/XÓA evidence.
10. Đánh giá incident/backoff và cập nhật automated test.

### 23.2. Khi nào không nên retry tự động?

- Side effect tài chính/đặt hàng không có idempotency hay status lookup.
- Hệ thống đích không xác nhận được trạng thái và một lần trùng có hậu quả nghiêm trọng.
- Retry window/credential đã hết hạn hoặc request body không còn chắc chắn.
- Mismatch payload cùng operationId.
- Permanent validation/authorization failure.
- Broker backlog/partner overload cần giảm tải thay vì phát lại liên tục.

Trong những trường hợp này, giữ operation UNKNOWN và escalation/reconciliation **an toàn hơn tạo duplicate**.

## 24. Những anti-pattern phổ biến

| Anti-pattern | Vì sao sai? | Cách đúng |
| --- | --- | --- |
| `catch IOException => NOT_PROCESSED` | Không biết target đã commit chưa | UNKNOWN + reconciliation |
| Sinh UUID mới mỗi retry | Biến một intent thành nhiều commands | Giữ operationId ổn định |
| Chỉ test `connection refused` | Không phủ lost response sau COMMIT | Inject fault ở commit barrier |
| Dùng `Thread.sleep(100)` để cắt proxy | Race, flaky | CountDownLatch/commit marker |
| Đếm client HTTP attempts làm business success | Attempts không chứng minh commit | Target DB receipt + business metric |
| Dùng in-memory set cho idempotency production | Mất sau crash, không share pods | SQL unique + transaction |
| `SELECT exists` rồi INSERT không có constraint | Race giữa concurrent retries | Atomic INSERT/UNIQUE |
| COMMIT business và idempotency receipt ở hai transactions | Key/result không nhất quán | Cùng DB transaction |
| Lưu key chỉ sau side effect | Retry cạnh tranh tạo duplicate | Claim + business write atomic |
| Dedupe chỉ ở producer | Consumer redelivery vẫn có | Inbox/unique business key |
| Coi Kafka acks=all là consumer applied | Sai phạm vi broker ACK | Consumer commit + idempotency |
| Rabbit consumer ACK trước SQL COMMIT | Có thể mất message | ACK sau COMMIT |
| Kafka offset commit trước DB | Mất khả năng replay | Commit progress sau durable handoff |
| HTTP 202 được xem là COMPLETED | Chỉ accepted workflow | Status polling/completion event |
| Thêm retry ở 3 tầng không kiểm soát | Attempts nhân lên, quá tải | Retry budget xuyên tầng |
| Retry Redis INCR khi timeout | Counter tăng hai lần | Business idempotency/script/DB |
| Test HTTP stub rồi kết luận ACID | In-memory state không bền | PostgreSQL Testcontainers |
| Proxy log thay bằng DB commit evidence | Proxy không thấy transaction | Database receipt/commit marker |
| Xóa outbox row sau publish attempt | Confirm có thể chưa đến | Durable state + reconciliation |
| Không định nghĩa key retention | Replay cũ tạo tác động mới | Retention phù hợp SLA |
| Log Authorization/raw payload để debug | Rò secrets/PII | Redaction và correlation ID |

## 25. Checklist kiểm thử trước production

- [ ] Đã định nghĩa “target received”, “accepted”, “committed”, “confirmed” cho từng API/protocol.
- [ ] Client có operationId/idempotency key ổn định cho một business intent.
- [ ] Target lưu idempotency/receipt đủ bền, có unique constraint và atomic transaction.
- [ ] Same key + same payload replay trả receipt/status nhất quán.
- [ ] Same key + different payload bị từ chối rõ.
- [ ] Có status lookup hoặc reconciliation policy cho UNKNOWN.
- [ ] Test cut **trước backend receipt** và xác minh target thật chưa nhận.
- [ ] Test cut **sau backend receipt, trước COMMIT**, có barrier deterministic.
- [ ] Test cut **sau COMMIT, trước response** và xác minh target side effect.
- [ ] Test proxy mất response dù target đã gửi/commit.
- [ ] Test crash client sau nhận receipt trước persist local result.
- [ ] Test concurrent same-key requests và restart target.
- [ ] Đã kiểm tra transparent HTTP retries, response timeouts và Retry-After.
- [ ] Transaction và schema/migrations được test trên DB thật (Testcontainers).
- [ ] Producer confirm loss được test với broker thật và stable eventId.
- [ ] Consumer SQL COMMIT + ACK lost được test, inbox chặn duplicate.
- [ ] Out-of-order events có aggregate version guard.
- [ ] Outbox relay có lease, retry budget, unknown state, DLQ/reconciliation.
- [ ] Redis non-idempotent commands có policy tránh duplicate.
- [ ] Tất cả test gates/latches có timeout và cleanup.
- [ ] Metrics phân biệt attempted, received, committed, response received và unknown.
- [ ] Không log secret/token/PII, metric tags không có high-cardinality IDs.
- [ ] Có runbook cho UNKNOWN, manual review, replay và compensation.
- [ ] Không xem HTTP 202, publisher ACK, consumer ACK và SQL COMMIT là một loại “thành công”.

**Ghi nhớ:** **Mất kết nối trước khi hệ thống đích nhận** có thể nghĩa là thao tác chưa hề xảy ra; **mất kết nối sau khi đích đã COMMIT** có thể tạo cùng IOException ở client nhưng nghiệp vụ đã hoàn thành. Cách duy nhất để xử lý đáng tin cậy là thiết kế **hợp đồng business identity, trạng thái UNKNOWN, server-side idempotency, status lookup/reconciliation, outbox/inbox**, rồi kiểm thử có điều khiển chính xác các failure windows. Timeout và retry là công cụ vận hành; chúng **không thay được bằng chứng về business state**.

## Tài liệu tham khảo

- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110): idempotent methods, status codes và semantics HTTP.
- [RFC 9112 — HTTP/1.1](https://www.rfc-editor.org/rfc/rfc9112): HTTP message framing, incomplete messages và connections.
- [Spring Framework — REST Clients](https://docs.spring.io/spring-framework/reference/integration/rest-clients.html): RestClient, response handling và HTTP interfaces.
- [Spring Framework — Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction.html): local transaction boundaries.
- [Spring Boot — SQL Databases](https://docs.spring.io/spring-boot/reference/data/sql.html): JDBC, DataSource, transaction và pooling.
- [Spring Retry — Reference](https://docs.spring.io/spring-retry/docs/current/reference/html/): retry policy, backoff và recoverer.
- [Resilience4j — Retry](https://resilience4j.readme.io/docs/retry): bounded retry và exception classification.
- [OkHttp — MockWebServer](https://square.github.io/okhttp/features/mocking/): deterministic HTTP stubs, faults và recorded requests.
- [Testcontainers — Toxiproxy](https://java.testcontainers.org/modules/toxiproxy/): network fault injection trong integration tests.
- [Testcontainers — PostgreSQL](https://java.testcontainers.org/modules/databases/postgres/): real transaction/unique constraint tests.
- [Spring AMQP — Publisher Confirms and Returns](https://docs.spring.io/spring-amqp/reference/amqp/publisher-confirms-returns.html): broker confirms và unroutable messages.
- [RabbitMQ — Consumer Acknowledgements and Publisher Confirms](https://www.rabbitmq.com/docs/confirms): consumer vs publisher acknowledgement semantics.
- [Spring for Apache Kafka — Sending Messages](https://docs.spring.io/spring-kafka/reference/kafka/sending-messages.html): KafkaTemplate producer futures.
- [Spring for Apache Kafka — Listener Containers](https://docs.spring.io/spring-kafka/reference/kafka/receiving-messages/message-listener-container.html): consumer ACK/offset lifecycle.
- [Apache Kafka — Producer Configs](https://kafka.apache.org/documentation/#producerconfigs): acks, idempotence, retry/timeout behavior.
- [Enterprise Integration Patterns — Idempotent Receiver](https://www.enterpriseintegrationpatterns.com/patterns/messaging/IdempotentReceiver.html): dedupe và at-least-once delivery.
- [Transactional Outbox Pattern](https://microservices.io/patterns/data/transactional-outbox.html): business transaction và durable publish intent.
