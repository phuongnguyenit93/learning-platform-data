# Giao dịch cục bộ và giới hạn giao dịch phân tán

## 1. Vì sao ranh giới giao dịch là quyết định kiến trúc?

Một thao tác nghiệp vụ thường chạm tới nhiều dữ liệu: tạo đơn thuê, giữ thiết bị, trừ hạn mức, ghi lịch sử và gửi thông báo. Nếu tất cả dữ liệu nằm trong một database, ta có thể dùng một transaction để bảo đảm các thay đổi cùng thành công hoặc cùng rollback. Nhưng trong kiến trúc cloud, dữ liệu thường thuộc nhiều service hoặc datastore độc lập. Khi đó, không thể mặc định có một lệnh COMMIT bao trùm mọi thành phần.

Trong module **CLOUD_ARCHITECTURE**, thiết kế dữ liệu và compute phải phù hợp yêu cầu nghiệp vụ, độ tin cậy, bảo mật, khả năng mở rộng, chi phí và vận hành. **Giao dịch cục bộ** giúp bảo vệ tính đúng đắn bên trong một ranh giới transaction. **Giao dịch phân tán** cố gắng phối hợp nhiều tài nguyên qua mạng, nơi có timeout, mất kết nối, node lỗi, retry và kết quả không rõ ràng.

**API contract**, **transaction protocol** và **business workflow** là ba khái niệm khác nhau. Một request gọi nhiều API không tự trở thành transaction phân tán; hệ thống cần protocol có hỗ trợ thật hoặc một mô hình workflow với trạng thái, retry và compensation rõ ràng.

Sau bài này, bạn có thể giải thích ACID và isolation; phân biệt atomicity cục bộ với tính nhất quán xuyên service; so sánh 2PC, Saga, transactional outbox/inbox và eventual consistency; thiết kế idempotency, retry, timeout, compensation và đối soát; đồng thời chọn nơi cần tính nguyên tử mạnh và nơi chấp nhận trạng thái trung gian.

## 2. Transaction cục bộ và ACID

Một transaction là đơn vị thao tác dữ liệu được database quản lý. Với hệ quản trị quan hệ hỗ trợ ACID, các thuộc tính thường được mô tả:

| Thuộc tính | Ý nghĩa | Ví dụ trong BookingCloud |
|---|---|---|
| **Atomicity** | Các thay đổi trong transaction cùng commit hoặc rollback | Tạo booking và chiếm slot cùng thành công; nếu một thao tác thất bại thì cả hai không được commit |
| **Consistency** | Transaction đưa dữ liệu từ trạng thái hợp lệ sang trạng thái hợp lệ theo constraint/rule được database và ứng dụng thực thi | Không có hai booking cùng chiếm một slot duy nhất |
| **Isolation** | Transaction đồng thời được cô lập theo mức isolation đã chọn | Hai khách tranh cùng slot không cùng commit thành công |
| **Durability** | Sau commit thành công, dữ liệu được lưu bền vững theo bảo đảm của database | API trả thành công chỉ sau khi booking đã được commit theo durability policy |

**Consistency trong ACID** là việc bảo toàn invariant/constraint của database; nó không tự động bảo đảm mọi quy tắc nghiệp vụ nằm trong nhiều hệ thống bên ngoài. Ví dụ transaction có thể bảo đảm một booking và một slot được ghi đúng trong database, nhưng không thể tự bảo đảm email provider đã gửi email hoặc dịch vụ thanh toán đã thu tiền.

### 2.1. Ví dụ transaction cục bộ

Giả sử mỗi slot định danh bằng cặp device_id + slot_id và chỉ được một booking chiếm. Cấu trúc dữ liệu có thể có unique constraint trên cặp này hoặc một bảng reservation có khóa duy nhất tương ứng.

~~~sql
BEGIN;

INSERT INTO bookings (
    booking_id, customer_id, device_id, slot_id, status
) VALUES (
    :booking_id, :customer_id, :device_id, :slot_id, 'confirmed'
);

UPDATE device_slots
SET status = 'reserved',
    booking_id = :booking_id
WHERE device_id = :device_id
  AND slot_id = :slot_id
  AND status = 'available';

-- Ứng dụng phải kiểm tra đúng một hàng được cập nhật.
-- Nếu không, ROLLBACK và trả conflict.

COMMIT;
~~~

Đoạn SQL trên là **mẫu logic**, cần điều chỉnh thứ tự và constraint theo schema thực tế. Một cách triển khai có thể dùng conditional update/unique constraint rồi kiểm tra số hàng bị ảnh hưởng; cách khác khóa hàng phù hợp. Mục tiêu là để database phân xử tranh chấp đồng thời, không dựa vào một lần SELECT trước đó rồi INSERT sau đó như hai thao tác không được bảo vệ.

Nếu transaction phát hiện slot đã được chiếm, ứng dụng rollback và trả lỗi nghiệp vụ phù hợp, ví dụ HTTP 409. Không trả 201 chỉ vì API đã nhận request.

### 2.2. Isolation và race condition

Hai request có thể cùng đọc trạng thái slot là available rồi cùng cố tạo booking. Một lần đọc đơn thuần không giữ quyền sở hữu slot cho tới khi ghi.

| Cách bảo vệ | Ý tưởng | Lưu ý |
|---|---|---|
| Unique constraint | Database từ chối bản ghi trùng | Phải xác định đúng khóa nghiệp vụ, xử lý duplicate key |
| Conditional update | Chỉ cập nhật nếu trạng thái vẫn available | Kiểm tra row count và transaction outcome |
| Row lock | Khóa bản ghi slot trong transaction | Cần thứ tự khóa nhất quán, timeout và xử lý deadlock |
| Serializable isolation | Database đảm bảo kết quả tương đương thứ tự tuần tự phù hợp | Có thể retry serialization failure; overhead và contention cao hơn |

Không phải mọi API cần SERIALIZABLE. Chọn isolation phù hợp invariant và workload, sau đó thử concurrency. Nếu dùng READ COMMITTED, unique constraint hoặc conditional write vẫn có thể bảo vệ một số invariant đơn giản; nếu rule phức tạp hơn, phải chứng minh bằng mô hình transaction cụ thể.

### 2.3. Transaction càng dài, chi phí càng lớn

Giữ transaction mở trong lúc gọi email, payment gateway hoặc service khác là một anti-pattern phổ biến:

- Connection và lock bị giữ trong thời gian chờ mạng.
- Một dependency chậm làm tăng latency và làm cạn connection pool.
- Timeout làm caller không biết remote operation đã hoàn tất hay chưa.
- Retry có thể lặp side effect hoặc tạo nhiều transaction cùng tranh chấp.
- Database khó scale hơn khi transaction dài và nhiều lock.

Transaction cục bộ nên bao quanh **những thay đổi dữ liệu cần nguyên tử trong cùng ranh giới lưu trữ**, không kéo dài qua các bước I/O mạng không cần thiết.

## 3. Transaction boundary là gì?

**Transaction boundary** là phạm vi dữ liệu và thao tác được một transaction manager kiểm soát nguyên tử. Ranh giới có thể là một transaction của một relational database; một số datastore có transaction phạm vi record/document/partition riêng. Không giả định mọi database có cùng phạm vi hoặc cùng semantics.

Trong kiến trúc service, mỗi service thường sở hữu dữ liệu của mình. Service khác truy cập thông qua API hoặc event thay vì cùng sửa trực tiếp database nội bộ. Điều này tạo ra ranh giới ownership rõ nhưng cũng có nghĩa một nghiệp vụ xuyên service không còn nằm trong một transaction cục bộ.

~~~mermaid
flowchart TB
    subgraph S1["Booking service / transaction boundary A"]
      BA["Booking API"]
      BDB[("Booking DB")]
      BA --> BDB
    end
    subgraph S2["Inventory service / transaction boundary B"]
      IA["Inventory API"]
      IDB[("Inventory DB")]
      IA --> IDB
    end
    subgraph S3["Payment service / transaction boundary C"]
      PA["Payment API"]
      PDB[("Payment DB")]
      PA --> PDB
    end
    BA -->|"HTTP/event qua mạng"| IA
    BA -->|"HTTP/event qua mạng"| PA
~~~

Mỗi DB tự quản lý transaction bên trong nó. Mũi tên HTTP/event không tự mở rộng transaction của Booking DB sang Inventory DB hoặc Payment DB.

### 3.1. Không phải mọi “nhiều bước” đều là distributed transaction

Một request gọi ba API tuần tự chỉ là một workflow điều phối nhiều thao tác. Để trở thành distributed transaction theo nghĩa chặt, các participant phải tham gia một protocol phối hợp commit/abort với cơ chế chuẩn bị và quyết định thống nhất. Nhiều hệ thống microservice không sử dụng protocol đó; chúng dùng Saga, event-driven workflow hoặc eventual consistency.

Phân biệt này quan trọng khi phát biểu “toàn bộ thao tác atomic”. Nếu hệ thống chỉ thực hiện HTTP calls tuần tự, thao tác đầu có thể đã commit trong khi thao tác thứ hai timeout. Caller không có rollback tự động đối với thay đổi đã commit ở service đầu.

## 4. Vì sao giao dịch phân tán khó hơn?

Khi các participant nằm ở các process/network/datastore khác nhau, hệ thống phải xử lý:

- **Partial failure:** một service đã commit nhưng response bị mất; caller không biết kết quả.
- **Network partition/timeout:** không phân biệt chắc chắn request chưa tới, đang xử lý hay đã thành công nhưng phản hồi không về.
- **Coordinator failure:** bộ điều phối có thể chết sau khi participant đã chuẩn bị hoặc commit một phần.
- **Concurrent transactions:** nhiều workflow có thể tranh cùng tài nguyên ở các service.
- **Different storage semantics:** participant có thể dùng database, queue hoặc external API không hỗ trợ cùng protocol.
- **Long duration:** một quy trình nghiệp vụ có thể kéo dài nhiều phút/giờ/ngày; giữ lock xuyên suốt không thực tế.
- **Operational complexity:** cần log, correlation ID, trạng thái workflow, timeout, retry, recovery và đối soát.

### 4.1. Ví dụ: đặt lịch cần giữ thiết bị và thu tiền

Workflow gồm: Booking service tạo PENDING; Inventory service giữ slot; Payment service authorize/charge; Booking service chuyển sang CONFIRMED; Notification worker gửi xác nhận.

Nếu bước giữ slot thành công và payment thất bại, hệ thống cần giải phóng slot. Nếu payment thành công nhưng bước confirm timeout, không thể tạo payment mới một cách mù quáng; cần truy vấn trạng thái hoặc tiếp tục workflow bằng cùng operation identity.

~~~mermaid
sequenceDiagram
    autonumber
    actor C as Customer
    participant B as Booking service
    participant I as Inventory service
    participant P as Payment service
    participant N as Notification

    C->>B: Create booking
    B->>B: Local transaction: PENDING
    B->>I: Hold slot
    I-->>B: Hold accepted
    B->>P: Authorize payment
    alt Payment accepted
        P-->>B: Payment authorized
        B->>B: Local transaction: CONFIRMED
        B->>N: Publish confirmation event
        B-->>C: Booking confirmed
    else Payment declined
        P-->>B: Declined
        B->>I: Release held slot
        I-->>B: Slot released
        B->>B: Local transaction: FAILED
        B-->>C: Booking failed
    end
~~~

Sơ đồ chỉ mô tả luồng thành công và một nhánh từ chối. Nó chưa giải quyết mọi timeout, crash hay response bị mất; đó là lý do phải có workflow state, idempotency và recovery.

## 5. Two-phase commit (2PC)

**Two-phase commit** là protocol phối hợp commit giữa coordinator và các participant có hỗ trợ. Nó chia quá trình thành hai pha:

1. **Prepare:** coordinator yêu cầu participant chuẩn bị transaction. Participant kiểm tra có thể commit hay không, ghi thông tin cần thiết vào log và trả YES/NO. YES có nghĩa participant sẵn sàng commit nếu quyết định cuối là COMMIT; nó chưa tự commit.
2. **Commit/Abort:** nếu tất cả participant trả YES, coordinator ra quyết định COMMIT; nếu có participant trả NO hoặc điều kiện thất bại, coordinator ra quyết định ABORT. Participant thực hiện quyết định đã nhận.

~~~mermaid
sequenceDiagram
    autonumber
    participant C as Coordinator
    participant A as Participant A
    participant B as Participant B

    C->>A: PREPARE transaction
    C->>B: PREPARE transaction
    A->>A: Validate + persist prepare state
    B->>B: Validate + persist prepare state
    A-->>C: YES
    B-->>C: YES
    C->>C: Persist COMMIT decision
    C->>A: COMMIT
    C->>B: COMMIT
    A-->>C: ACK
    B-->>C: ACK
~~~

Nếu một participant trả NO, coordinator cần quyết định ABORT và thông báo participant. Nếu coordinator gặp lỗi sau prepare, các participant có thể phải giữ lock/resource và chờ quyết định; 2PC có thể **blocking** trong một số failure scenario. Recovery phụ thuộc log bền vững và khả năng participant/coordinator phục hồi để hoàn tất quyết định.

### 5.1. Điều kiện để dùng 2PC

2PC chỉ có thể dùng khi mọi participant hỗ trợ cùng protocol hoặc một distributed transaction manager có adapter đúng semantics. Một HTTP API tùy ý, payment gateway bên thứ ba hay email service không tự trở thành participant 2PC.

### 5.2. Đánh đổi của 2PC

| Lợi ích | Chi phí/rủi ro |
|---|---|
| Có quyết định commit/abort phối hợp giữa các participant hỗ trợ | Coordinator và participant cần protocol/log/recovery |
| Có thể giữ atomicity xuyên nhiều resource trong mô hình được hỗ trợ | Participant giữ lock/resource trong lúc chờ quyết định |
| Ứng dụng có mô hình transaction thống nhất hơn | Blocking khi coordinator/communication lỗi ở thời điểm không thuận lợi |
| Phù hợp một số hệ thống có yêu cầu chặt và participant đồng nhất | Latency, coupling, operational complexity và giới hạn dịch vụ |

2PC không làm hệ thống miễn nhiễm lỗi mạng. Nó biến một phần vấn đề thành protocol recovery; nhóm vận hành vẫn cần hiểu prepared transaction, timeout, coordinator log và cách xử lý transaction bị treo.

### 5.3. Khi nào 2PC đáng cân nhắc?

2PC có thể phù hợp khi atomicity xuyên các resource là bắt buộc; tất cả participant và hạ tầng hỗ trợ transaction protocol một cách rõ ràng; transaction ngắn, participant ổn định và latency/availability trade-off được chấp nhận; tổ chức có khả năng vận hành coordinator, recovery log và xử lý prepared transaction.

Nó thường không phù hợp để ghép các SaaS/HTTP API độc lập, payment provider hoặc workflow kéo dài. Với các trường hợp này, Saga và compensation thường thực tế hơn.

## 6. Saga: chuỗi local transaction và compensating action

**Saga** mô hình hóa một nghiệp vụ phân tán thành chuỗi local transaction. Mỗi participant commit trong database riêng; nếu một bước sau thất bại, workflow chạy các **compensating action** để đưa trạng thái nghiệp vụ về một kết quả chấp nhận được.

Saga không phải rollback nguyên tử theo nghĩa database. Compensation là một thao tác nghiệp vụ mới, có thể thất bại, có thể cần retry, và không nhất thiết xóa được tác động đã xảy ra bên ngoài.

### 6.1. Ví dụ Saga đặt lịch

| Bước | Local transaction | Nếu bước sau thất bại, compensation có thể là |
|---|---|---|
| 1. Tạo booking pending | Booking DB ghi PENDING | Hủy booking pending |
| 2. Giữ slot | Inventory DB ghi HELD | Release slot |
| 3. Authorize payment | Payment DB/provider ghi AUTHORIZED | Void authorization |
| 4. Confirm booking | Booking DB chuyển CONFIRMED | Nếu nghiệp vụ cho phép, chuyển sang CANCELLATION_PENDING và xử lý hủy |
| 5. Capture payment | Payment ghi CAPTURED | Refund; đây là giao dịch mới, không phải xóa charge |
| 6. Gửi thông báo | Notification system ghi SENT/ACCEPTED | Có thể gửi thông báo đính chính; email đã gửi không thể “thu hồi” chắc chắn |

Saga thường nên sắp xếp các bước để bước có thể thất bại nhiều/ít đảo ngược xảy ra trước side effect khó bù. Với payment, authorize trước và capture sau khi booking được xác nhận có thể giảm nhu cầu refund, nếu provider và quy trình nghiệp vụ hỗ trợ.

~~~mermaid
flowchart TD
    START["Start booking saga"] --> S1["T1: Create PENDING booking"]
    S1 --> S2["T2: Hold inventory slot"]
    S2 --> S3["T3: Authorize payment"]
    S3 --> S4["T4: Confirm booking"]
    S4 --> S5["T5: Capture payment / notify"]
    S5 --> DONE["Completed"]
    S2 -->|"Failure"| C1["C1: Cancel pending booking"]
    S3 -->|"Failure"| C2["C2: Release slot"]
    C2 --> C1
    S4 -->|"Failure"| C3["C3: Void authorization"]
    C3 --> C2
    C1 --> FAIL["Compensated / Failed"]
    C2 --> FAIL
    C3 --> FAIL
~~~

Sơ đồ rút gọn chỉ minh họa các bước đảo ngược. Hệ thống thật cần biểu diễn timeout, kết quả chưa rõ, compensation retry, manual intervention và trạng thái PARTIALLY_COMPENSATED.

### 6.2. Orchestration và choreography

| Kiểu | Cách hoạt động | Ưu điểm | Đánh đổi |
|---|---|---|---|
| **Orchestration** | Một saga orchestrator lưu state và gọi participant theo workflow | Trình tự, timeout, retry, compensation rõ; dễ quan sát luồng nghiệp vụ | Orchestrator cần HA, persistence và quản trị; business flow tập trung hơn |
| **Choreography** | Participant phát event và service khác phản ứng theo event | Ít central coordinator, các service tương đối độc lập | Khó nhìn toàn workflow, dễ tạo vòng event phức tạp, tracing và compensation khó hơn |

Với workflow có nhiều nhánh, timeout, điều kiện và bước compensation, orchestration thường dễ kiểm soát hơn. Choreography phù hợp các event phản ứng đơn giản, ít bước và có ownership rõ. Không có cách nào tự động loại bỏ distributed failure.

### 6.3. Saga state machine

Mỗi Saga cần một định danh ổn định và trạng thái có thể phục hồi:

~~~text
CREATED
  -> BOOKING_PENDING
  -> INVENTORY_HELD
  -> PAYMENT_AUTHORIZED
  -> BOOKING_CONFIRMED
  -> COMPLETED

Failure paths:
  -> COMPENSATING
  -> COMPENSATED
  -> MANUAL_REVIEW
  -> FAILED
~~~

State machine phải ghi được bước hiện tại, kết quả participant, số lần thử, deadline, compensation cần thực hiện và correlation ID. Orchestrator restart phải đọc state bền vững rồi tiếp tục; không dựa vào bộ nhớ process.

### 6.4. Compensation không phải rollback lịch sử

Nếu payment đã capture 500.000 đồng, compensation refund 500.000 đồng tạo ra một giao dịch tài chính mới. Có thể có độ trễ, phí, refund pending hoặc provider từ chối. Không thể xóa sự kiện charge như thể nó chưa từng tồn tại.

Tương tự, slot đã được hold có thể đã hết hạn hoặc được cấp cho người khác sau khi release; email đã gửi không thể bảo đảm thu hồi; event đã được consumer bên ngoài xử lý có thể tạo side effect khó đảo ngược. Vì vậy compensation cần **ngữ nghĩa nghiệp vụ**, không chỉ là một hàm inverse kỹ thuật.

## 7. Transactional outbox và inbox

Một lỗi phổ biến trong event-driven architecture là ghi DB rồi publish event theo hai thao tác riêng. Nếu DB commit thành công nhưng process chết trước khi publish, dữ liệu đã thay đổi nhưng consumer không nhận được event. Trường hợp ngược lại, publish trước rồi DB rollback có thể khiến consumer nhận sự kiện cho giao dịch chưa tồn tại.

### 7.1. Transactional outbox

**Outbox pattern** ghi thay đổi nghiệp vụ và event cần phát trong **cùng local DB transaction**. Một relay sau đó đọc các outbox record đã commit và publish vào broker.

~~~mermaid
sequenceDiagram
    autonumber
    participant API as Booking API
    participant DB as Booking DB
    participant Relay as Outbox relay
    participant Q as Message broker
    participant W as Consumer

    API->>DB: BEGIN
    API->>DB: INSERT booking
    API->>DB: INSERT outbox event
    API->>DB: COMMIT
    Relay->>DB: Read committed outbox rows
    DB-->>Relay: event_id + payload
    Relay->>Q: Publish event
    Q-->>Relay: Publish acknowledged
    Relay->>DB: Mark published / record offset
    Q-->>W: Deliver event
~~~

Outbox bảo đảm **booking và ý định phát event** được commit cùng nhau trong DB. Nó không bảo đảm message chỉ publish một lần. Nếu relay publish thành công nhưng chết trước khi đánh dấu published, nó có thể publish lại sau khi restart.

Vì thế consumer phải hỗ trợ duplicate delivery bằng idempotency/deduplication. Outbox cần polling hoặc change-data-capture phù hợp, index theo trạng thái/thời gian, retry, retention, cleanup và cảnh báo backlog.

### 7.2. Inbox/deduplication ở consumer

Consumer có thể ghi event_id vào inbox/dedup table cùng với thay đổi nghiệp vụ trong một local transaction:

~~~sql
BEGIN;

INSERT INTO processed_events (event_id, processed_at)
VALUES (:event_id, CURRENT_TIMESTAMP)
ON CONFLICT (event_id) DO NOTHING;

-- Chỉ xử lý event nếu insert mới thành công.
-- Update trạng thái nghiệp vụ cùng transaction.

COMMIT;
~~~

Đây là pseudo-SQL theo cú pháp gần PostgreSQL. Cần kiểm tra kết quả insert để biết event đã xử lý trước đó hay chưa. Nếu update nghiệp vụ và ghi processed marker không nằm cùng transaction, crash giữa hai thao tác vẫn có thể gây mất hoặc xử lý lặp.

Đối với side effect bên ngoài DB, như gọi payment provider, dedup marker trong database không đủ để bảo đảm exactly-once. Cần idempotency key được provider hỗ trợ hoặc một workflow state/đối soát để xử lý kết quả không rõ.

### 7.3. Outbox không thay thế Saga

Outbox giải quyết việc **ghi dữ liệu và phát event đáng tin cậy** từ một local transaction. Saga giải quyết việc **điều phối nhiều local transaction và compensation** xuyên service. Chúng thường được dùng cùng nhau:

- Orchestrator ghi saga state và command/event vào outbox.
- Participant nhận command, xử lý idempotent và ghi kết quả.
- Participant ghi event trả lời vào outbox cùng local update.
- Orchestrator nhận event, chuyển state và quyết định bước kế tiếp.

## 8. Idempotency, retry và timeout

Distributed workflow không thể tránh hoàn toàn duplicate hoặc kết quả không rõ ràng. Thiết kế phải giả định request/message có thể được gửi lại.

### 8.1. Idempotency key

Một operation có thể mang key duy nhất theo phạm vi nghiệp vụ:

~~~http
POST /payments/authorize
Idempotency-Key: saga-7812-payment-authorize
Content-Type: application/json

{
  "bookingId": "bkg-8124",
  "amount": 500000,
  "currency": "VND"
}
~~~

Provider/payment service lưu kết quả gắn với key. Khi nhận lại cùng key và cùng request semantics, nó trả kết quả trước đó hoặc response phù hợp; cùng key nhưng payload khác phải được từ chối theo contract. Thời gian lưu key phải đủ dài so với cửa sổ retry/đối soát.

Không dùng cùng key cho hai operation độc lập. Cần namespace key theo tenant/customer/operation nếu phạm vi uniqueness không toàn cục.

### 8.2. Timeout không có nghĩa operation thất bại

Giả sử orchestrator gửi authorize payment. Payment service commit thành công nhưng response bị mất. Orchestrator timeout:

- Không thể kết luận payment chưa xảy ra.
- Gửi lại với key mới có thể tạo authorize/charge lặp.
- Bỏ qua kết quả có thể khiến booking không được xác nhận dù đã giữ tiền.

Recovery an toàn:

1. Retry cùng idempotency key nếu provider contract cho phép.
2. Query operation status theo payment ID/key khi API hỗ trợ.
3. Nếu kết quả vẫn chưa rõ, đánh dấu Saga ở trạng thái chờ xác minh thay vì tự làm compensation mù.
4. Đưa vào đối soát/manual review khi đã vượt deadline.

### 8.3. Retry có giới hạn

Retry nên có timeout phù hợp; exponential backoff và jitter; maximum attempts/deadline; phân loại retryable vs non-retryable; circuit breaker/bulkhead hoặc rate limit khi phù hợp; idempotency/deduplication cho side effect; DLQ hoặc trạng thái failed cần người xử lý.

Không retry vô hạn lỗi validation, insufficient funds hoặc permission denied. Không retry tất cả 5xx một cách vô điều kiện khi operation có side effect không idempotent.

## 9. Eventual consistency và trạng thái trung gian

Trong Saga, các service commit ở thời điểm khác nhau. Trong một khoảng thời gian, hệ thống có thể quan sát Booking=PENDING, Inventory=HELD và Payment=AUTHORIZING. Đây không nhất thiết là lỗi nếu trạng thái trung gian được mô hình hóa và consumer xử lý đúng. Sau khi workflow hoàn thành, read model được cập nhật và trạng thái hội tụ về kết quả cuối.

**Eventual consistency** nghĩa là nếu không có cập nhật mới và các thao tác truyền/áp dụng được hoàn tất, các bản sao/read model liên quan cuối cùng sẽ hội tụ theo quy tắc hệ thống. Nó không có nghĩa “dữ liệu tự động đúng”, cũng không chỉ định thời gian hội tụ cố định.

### 9.1. Thiết kế trạng thái nghiệp vụ tường minh

| Trạng thái | Ý nghĩa | Consumer/UI nên làm gì |
|---|---|---|
| PENDING | Workflow đã bắt đầu, chưa hoàn tất | Hiển thị đang xử lý, không khẳng định booking confirmed |
| INVENTORY_HELD | Slot đã được giữ tạm | Theo dõi payment/confirmation deadline |
| PAYMENT_PENDING | Chờ xác định payment outcome | Không tạo payment mới; kiểm tra cùng operation ID |
| CONFIRMED | Các điều kiện nghiệp vụ đã đạt | Hiển thị booking đã xác nhận |
| COMPENSATING | Đang giải phóng/hoàn tác tác động trước | Hiển thị đang xử lý hủy/hoàn tiền nếu phù hợp |
| COMPENSATED | Các compensation bắt buộc đã hoàn tất | Hiển thị thất bại/hủy và thông tin cần thiết |
| MANUAL_REVIEW | Kết quả không thể tự xác minh | Chuyển support/ops xử lý |
| FAILED | Workflow kết thúc thất bại theo định nghĩa | Không còn retry tự động nếu không có policy |

UI không nên hiển thị CONFIRMED chỉ vì booking record đã được tạo nếu policy nghiệp vụ yêu cầu inventory và payment phải thành công trước.

### 9.2. Read-your-writes và read model

Nếu client vừa tạo booking rồi đọc từ read replica/event-projected view, dữ liệu có thể chưa xuất hiện. Có thể đọc từ nguồn ghi trong thời gian ngắn sau command; trả operation ID và trạng thái PENDING cho client poll; dùng event/cursor hoặc version để consumer biết projection đã xử lý tới đâu; và nêu rõ consistency guarantee của read endpoint.

Không dùng một read replica eventual-consistent làm nguồn quyết định duy nhất cho invariant đặt chỗ.

## 10. Chọn chiến lược theo yêu cầu

| Tình huống | Cơ chế thường cân nhắc | Lý do |
|---|---|---|
| Nhiều bảng trong cùng relational DB cần cùng commit | Local ACID transaction + constraints | Đơn giản, atomicity rõ |
| Hai datastore hỗ trợ chung distributed transaction protocol, yêu cầu atomicity nghiêm | 2PC/XA nếu nền tảng hỗ trợ và chấp nhận trade-off | Có protocol commit phối hợp |
| Workflow dài, nhiều service, có compensation nghiệp vụ | Saga orchestration/choreography | Không giữ distributed lock xuyên suốt |
| Ghi DB và phát event | Transactional outbox | Tránh mất event giữa DB commit và publish |
| Consumer có thể nhận message trùng | Inbox/deduplication + idempotent handler | Bảo vệ xử lý lặp |
| Báo cáo/read model có thể cập nhật trễ | Event-driven projection/eventual consistency | Tăng tách biệt và khả năng scale |
| Side effect không thể đảo ngược dễ dàng | Pending state, authorize-before-capture, reconcile/manual review | Không hứa rollback giả tạo |

### 10.1. Câu hỏi quyết định

1. Invariant nào phải luôn đúng ở mọi thời điểm và invariant nào có thể đúng sau khi workflow kết thúc?
2. Có thể gom dữ liệu vào một transaction boundary mà không phá ownership/scaling của service không?
3. Participant có hỗ trợ distributed transaction protocol không? Nếu không, đừng giả vờ đang dùng 2PC.
4. Compensation có ý nghĩa nghiệp vụ thực sự hay chỉ là lời gọi API ngược?
5. Khi timeout, có thể tra cứu kết quả theo operation ID/idempotency key không?
6. Người dùng có chấp nhận trạng thái PENDING/PROCESSING hay cần quyết định tức thời?
7. Ai theo dõi Saga đang treo, DLQ và đối soát?
8. Chi phí vận hành distributed workflow có xứng với lợi ích tách service không?

## 11. Bảo mật ở ranh giới transaction phân tán

Distributed workflow làm tăng số service có thể nhìn thấy hoặc thay đổi một phần dữ liệu. Một số kiểm soát cần có:

- Service identity và quyền tối thiểu cho mỗi command/event.
- Xác thực publisher/consumer; không tin message chỉ vì nó đến từ broker.
- Validate schema, tenant ID, event ID, version và correlation fields.
- Bảo vệ idempotency store khỏi truy cập/chỉnh sửa trái phép.
- Không đưa access token, payment credential hoặc PII dư thừa vào event payload.
- Mã hóa đường truyền và dữ liệu lưu; kiểm soát quyền đọc DLQ, outbox và workflow history.
- Ghi audit cho compensation, manual override và thao tác replay.
- Chống replay ngoài ý muốn bằng event ID, timestamp/nonce hoặc quy tắc trạng thái thích hợp; không nhầm deduplication nghiệp vụ với xác minh danh tính.

Saga orchestrator có thể chứa dữ liệu trạng thái nhạy cảm và có quyền gọi nhiều service. Bảo vệ nó như component có blast radius lớn: RBAC chặt, secret rotation, audit, backup state và kiểm soát thay đổi workflow.

## 12. Quan sát, recovery và đối soát

Một distributed transaction/workflow cần được quan sát xuyên service. Các trường nên truyền có kiểm soát:

| Trường | Mục đích |
|---|---|
| saga_id | Định danh một workflow nghiệp vụ |
| operation_id | Định danh một bước/operation cụ thể |
| correlation_id | Liên kết log/trace giữa các service |
| event_id | Deduplicate event |
| causation_id | Biết event/command nào dẫn tới event hiện tại |
| attempt | Theo dõi retry |
| deadline | Biết thời hạn nghiệp vụ của workflow |
| state | Trạng thái hiện tại và bước chờ |

Tránh dùng saga_id làm metric label nếu cardinality quá lớn; có thể ghi trong log/trace, còn metric tổng hợp theo operation/state/service.

### 12.1. Metric hữu ích

- Số Saga đang ở trạng thái PENDING/COMPENSATING/MANUAL_REVIEW.
- Tuổi workflow lâu nhất và tỷ lệ vượt deadline.
- Tỷ lệ success, compensation success/failure và manual intervention.
- Số message outbox chưa publish, tuổi outbox lâu nhất.
- Consumer lag, duplicate event rate, retry count và DLQ depth.
- Payment/booking mismatch và số operation kết quả không rõ.
- p95/p99 latency mỗi participant và thời gian hoàn tất workflow.
- Chi phí queue, database, network và orchestration trên mỗi workflow thành công.

### 12.2. Đối soát

Một số hệ thống bên ngoài không thể cung cấp kết quả đồng bộ đáng tin cậy. Ví dụ payment gateway có thể đã charge dù callback bị mất. Job đối soát nên lấy danh sách operation pending/unknown quá deadline; query trạng thái từ provider bằng transaction/reference ID; so sánh với booking/payment ledger nội bộ; chọn action tiếp tục workflow, capture/void/refund hoặc manual review; rồi ghi audit và cập nhật state bằng transaction cục bộ.

Đối soát là một phần bình thường của kiến trúc giao dịch phân tán, không phải cách chữa cháy hiếm hoi.

## 13. Đánh giá theo Well-Architected

| Góc nhìn | Câu hỏi review | Bằng chứng |
|---|---|---|
| **Operational Excellence** | Có thể tìm Saga đang treo và phục hồi sau coordinator restart không? | Persistent state, runbook, replay/repair, dashboards và audit |
| **Security** | Ai được phát command, xem payload, đọc DLQ và chạy compensation? | Service identity, least privilege, encryption, audit |
| **Reliability** | Participant lỗi/timeout hoặc event giao trùng có làm sai trạng thái nghiệp vụ không? | Idempotency tests, outbox/inbox, fault injection, reconciliation |
| **Performance Efficiency** | Transaction có dài, lock contention cao hoặc workflow có quá nhiều network round trip? | DB lock metrics, p95 participant/workflow, throughput |
| **Cost Optimization** | Coordinator, broker, retry, storage và đối soát tốn bao nhiêu? | Cost/workflow, message volume, retry rate, retention |
| **Sustainability** | Có retry loop, event trùng, polling quá thường xuyên hoặc lưu state vô hạn? | Duplicate rate, polling efficiency, retention/lifecycle |

Một kiến trúc chỉ đạt khi các trade-off đã được nêu và phép thử chứng minh behavior phù hợp. Thêm Saga không tự động làm hệ thống đáng tin cậy; nó tăng số trạng thái và cơ chế phục hồi cần vận hành.

## 14. Bài thực hành: đặt lịch qua ba service

BookingCloud tách thành Booking, Inventory và Payment service, mỗi service có database riêng. Người dùng tạo đơn thuê theo quy trình: Booking tạo PENDING; Inventory giữ slot; Payment authorize số tiền; Booking confirm; Payment capture; Notification gửi email.

Các tình huống cần xử lý:

- Inventory giữ slot thành công nhưng response bị timeout.
- Payment authorize thành công nhưng callback bị mất.
- Booking confirm thành công nhưng orchestrator crash trước khi ghi state.
- Payment capture thành công nhưng notification service unavailable.
- Compensation release slot thất bại do Inventory service đang bảo trì.
- Queue giao cùng event hai lần.
- Một Saga pending quá 10 phút và slot hold sắp hết hạn.

Hãy thực hiện:

**Bài 1 — Transaction boundary:** xác định dữ liệu nào nằm trong từng local transaction và invariant nào phải được giữ trong mỗi service.

**Bài 2 — Chọn protocol:** giải thích vì sao HTTP calls tuần tự không phải 2PC; trong điều kiện nào 2PC có thể sử dụng; đề xuất Saga cho workflow này.

**Bài 3 — Thiết kế Saga state machine:** liệt kê state, command, event, timeout, retry và compensation cho sáu bước.

**Bài 4 — Kết quả không rõ:** thiết kế cách query payment theo cùng idempotency key/reference khi timeout. Không tạo charge thứ hai chỉ vì không nhận response.

**Bài 5 — Outbox/inbox:** xác định event nào ghi qua outbox, consumer nào deduplicate và trạng thái nào cập nhật trong cùng local transaction.

**Bài 6 — Compensation failure:** nếu release slot thất bại, workflow ở trạng thái nào, retry bao lâu, khi nào chuyển MANUAL_REVIEW và ai được quyền xử lý?

**Bài 7 — Đo lường:** đề xuất metric cho workflow age, compensation success, duplicate events, payment mismatch, p95 và chi phí mỗi booking.

### Khung phân tích mẫu

| Bước | Local commit | Sự cố giả định | Recovery/compensation |
|---|---|---|---|
| Tạo booking | Booking PENDING + outbox command | Response bị mất | Query theo booking/idempotency key |
| Hold slot | Inventory HELD + expiry | Timeout không rõ kết quả | Query hold ID hoặc retry cùng key |
| Authorize payment | Payment AUTHORIZED | Callback mất | Query provider theo reference |
| Confirm booking | Booking CONFIRMED | Orchestrator restart | Resume từ persisted saga state |
| Capture payment | Payment CAPTURED | Response mất | Query status; tránh charge lặp |
| Notification | Notification event accepted | Worker lỗi | Retry idempotent; DLQ/manual review |

Đây là gợi ý cấu trúc, không phải đáp án duy nhất. Cần làm rõ trạng thái của từng participant và semantics của provider ngoài.

## 15. Checklist trước khi chọn transaction strategy

- [ ] Đã liệt kê invariant nghiệp vụ và xác định nơi thực thi chúng.
- [ ] Transaction cục bộ càng ngắn càng tốt và nằm trong một ranh giới storage được hỗ trợ.
- [ ] Isolation, unique constraint, lock và concurrency behavior đã được kiểm thử.
- [ ] Không giả định nhiều HTTP calls là một atomic transaction.
- [ ] Nếu dùng 2PC, mọi participant hỗ trợ protocol và có kế hoạch coordinator recovery.
- [ ] Nếu dùng Saga, từng local transaction và compensating action có semantics rõ.
- [ ] Saga state được lưu bền vững, có timeout/deadline và manual review path.
- [ ] Outbox ghi cùng transaction với thay đổi nghiệp vụ; consumer xử lý duplicate qua inbox/idempotency.
- [ ] External side effect dùng idempotency key/query status/reconciliation khi có thể.
- [ ] Eventual consistency và trạng thái trung gian được phản ánh trong API/UI.
- [ ] DLQ, replay, compensation failure và đối soát có owner/runbook.
- [ ] Log/trace liên kết được workflow nhưng không làm lộ dữ liệu nhạy cảm.
- [ ] Có fault-injection test cho crash, timeout, duplicate, partial commit và participant outage.
- [ ] Đã đánh giá chi phí/latency/availability của chiến lược đã chọn theo Well-Architected.

Transaction cục bộ là công cụ mạnh để bảo vệ invariant bên trong một ranh giới dữ liệu. Khi nghiệp vụ vượt qua nhiều service, không thể tự giả định atomicity sẽ lan theo các lời gọi mạng. Hãy chọn protocol có hỗ trợ thật, hoặc mô hình hóa workflow bằng Saga, outbox/inbox, idempotency và đối soát; đồng thời công khai các trạng thái trung gian và giới hạn phục hồi. Đó là cách xây hệ thống phân tán đúng đắn và có thể vận hành.
