# Event sourcing: phát lại, snapshot và điều kiện áp dụng

Trong nhiều hệ thống, cơ sở dữ liệu chỉ lưu trạng thái hiện tại của một đối tượng: đơn hàng đang ở trạng thái nào, tài khoản còn bao nhiêu tiền hoặc thiết bị đang được giữ đến khi nào. Cách lưu này hiệu quả cho truy vấn hiện tại, nhưng không tự giải thích đầy đủ trạng thái đã thay đổi như thế nào và quyết định nào đã tạo ra kết quả nếu lịch sử không được ghi riêng.

**Event sourcing** là cách tổ chức dữ liệu trong đó các thay đổi nghiệp vụ được lưu thành một chuỗi sự kiện bất biến theo thứ tự. Trạng thái hiện tại được suy ra bằng cách áp dụng các sự kiện đó. Nhờ vậy, hệ thống có thể tái dựng trạng thái ở một thời điểm, kiểm tra lịch sử, xây dựng projection mới hoặc sửa cách tính dữ liệu đọc bằng cách phát lại sự kiện. Đổi lại, thiết kế phải xử lý thứ tự, version, tính tương thích, snapshot, dung lượng lưu trữ, quyền riêng tư và các tác động phụ khi replay.

Bài học thuộc chương **Tính nhất quán** của lộ trình **Cloud Architecture**. Nội dung tập trung vào event store, aggregate, phát lại, snapshot và điều kiện áp dụng trong hệ thống cloud. Các quyết định cần cân nhắc giữa tính đúng đắn nghiệp vụ, độ tin cậy, bảo mật, hiệu năng, chi phí và khả năng vận hành.

Sau bài học, bạn có thể:

- Phân biệt event sourcing, event-driven architecture, audit log và CRUD state storage.
- Mô hình hóa aggregate bằng event stream có thứ tự và version.
- Thiết kế append, concurrency control, idempotency và event schema.
- Tái dựng trạng thái bằng replay và xây snapshot để giảm thời gian phục hồi.
- Xây dựng hoặc rebuild read projection mà không lặp lại side effect.
- Xử lý event schema evolution, dữ liệu nhạy cảm, retention và migration.
- Đánh giá chi phí và rủi ro vận hành để xác định khi nào event sourcing phù hợp.

## 1. Event sourcing là gì?

Trong mô hình CRUD truyền thống, một thao tác thay đổi thường cập nhật trực tiếp bản ghi hiện tại. Ví dụ số dư trước giao dịch là 1.000.000 VND, khách thanh toán 250.000 VND và hệ thống cập nhật số dư thành 750.000 VND. Nếu chỉ lưu trạng thái cuối, dữ liệu hiện tại không tự giải thích được giao dịch nào đã diễn ra.

Trong event sourcing, hệ thống ghi sự kiện mô tả thay đổi:

- AccountOpened
- MoneyDeposited
- PaymentDebited

Trạng thái hiện tại được dựng bằng cách áp dụng lần lượt các event từ đầu stream. Event không phải câu lệnh SQL hay bản sao toàn bộ row; nó mô tả **một sự kiện nghiệp vụ đã xảy ra**.

### 1.1. Ví dụ event stream

~~~text
Aggregate: Account-42

Version 1: AccountOpened(initialBalance = 1,000,000 VND)
Version 2: MoneyDeposited(amount = 100,000 VND)
Version 3: PaymentDebited(amount = 250,000 VND)

State after version 3:
  balance = 850,000 VND
~~~

Từ stream này có thể dựng trạng thái ở version 1, 2 hoặc 3. Event stream không tự bảo đảm phép tính đúng; logic xử lý event và invariant phải được thiết kế, kiểm thử và quản lý version.

~~~mermaid
flowchart LR
    C["Command"] --> D["Domain logic"]
    D --> E["Append event"]
    E --> S[("Event store")]
    S --> R["Replay / projection processor"]
    R --> ST["Current state / read model"]
    ST --> Q["Query API"]
~~~

Command yêu cầu hệ thống thực hiện hành động. Domain logic xác thực điều kiện nghiệp vụ, sau đó append event nếu hợp lệ. Event store lưu lịch sử; projection processor có thể áp dụng event để xây read model. **Event sourcing không có nghĩa mọi lần đọc đều phải replay toàn bộ stream**; hệ thống thường dùng projection hoặc snapshot để truy vấn và phục hồi hiệu quả.

## 2. Phân biệt event sourcing với các khái niệm gần nhau

| Khái niệm | Điều được lưu hoặc tổ chức | Mục đích |
| --- | --- | --- |
| CRUD state storage | Trạng thái hiện tại của entity/row | Đọc và cập nhật trạng thái hiện hành |
| Audit log | Dấu vết ai đã làm gì, khi nào, với metadata | Kiểm toán và điều tra |
| Event sourcing | Chuỗi event nghiệp vụ làm nguồn dữ liệu chính | Dựng lại trạng thái và lịch sử thay đổi |
| Event-driven architecture | Các thành phần giao tiếp hoặc phản ứng qua event/message | Giảm coupling và xử lý bất đồng bộ |
| Transaction log/WAL | Ghi nhận thay đổi ở mức database engine | Recovery, replication và durability của DB |
| Change Data Capture (CDC) | Trích xuất thay đổi từ database log/table | Đồng bộ dữ liệu sang hệ thống khác |

Một hệ thống có thể dùng event-driven architecture nhưng vẫn lưu trạng thái bằng CRUD. Ví dụ ứng dụng cập nhật bảng Booking, sau đó phát BookingUpdated qua outbox. Đây là event-driven integration, nhưng chưa phải event sourcing nếu bảng Booking là nguồn sự thật và event chỉ là thông điệp tích hợp.

Ngược lại, event-sourced aggregate lưu stream event làm nguồn trạng thái và có thể phát domain/integration event cho consumer khác.

### 2.1. Audit log không thay thế event store

Audit log thường ghi người thực hiện, IP, thời điểm và hành động; không nhất thiết đủ thông tin để tái dựng state. Event sourcing cần sự kiện có ý nghĩa nghiệp vụ và dữ liệu đủ để xác định phép chuyển trạng thái.

Không nên lấy log text hoặc access log rồi gọi đó là event store. Log phục vụ quan sát thường không có contract ổn định, thứ tự aggregate hoặc durability cần thiết.

## 3. Aggregate và event stream

Trong Domain-Driven Design, **aggregate** là ranh giới nhất quán nghiệp vụ. Aggregate root kiểm soát các thay đổi cần bảo vệ cùng invariant. Trong event sourcing, mỗi aggregate thường có một stream riêng, được định danh ổn định và có version tăng dần.

Ví dụ:

- Booking-1005 có stream riêng về tạo đơn, giữ chỗ, xác nhận và hủy.
- Account-42 có stream riêng về nạp tiền và ghi nợ.
- Asset-21 có stream riêng về trạng thái thiết bị và bảo trì.

Một event stream thường có metadata:

| Thành phần | Ý nghĩa |
| --- | --- |
| Aggregate ID | Định danh đối tượng hoặc aggregate |
| Stream version | Vị trí/version của event trong stream |
| Event type | Loại sự kiện nghiệp vụ |
| Payload | Dữ liệu cần để áp dụng sự kiện |
| Event ID | ID duy nhất của event |
| Occurred time | Thời điểm nghiệp vụ xảy ra |
| Recorded time | Thời điểm event store ghi event |
| Correlation/causation ID | Liên hệ với yêu cầu hoặc sự kiện dẫn đến event |
| Schema version | Phiên bản cấu trúc event |

Event store thường cần hỗ trợ append theo expected version hoặc cơ chế concurrency tương đương để tránh ghi đè logic của nhau.

### 3.1. Event là sự kiện đã xảy ra

Tên event nên dùng thì quá khứ hoặc thể hiện sự kiện đã hoàn tất: BookingCreated, ReservationConfirmed, PaymentAuthorized, BookingCancelled. Tên như CreateBooking hoặc AuthorizePayment thường là command, tức yêu cầu thực hiện hành động.

Payload nên mô tả thay đổi có nghĩa, ví dụ PaymentAuthorized với amount, currency và providerReference, thay vì event tổng quát BookingChanged kèm JSON khó diễn giải.

## 4. Command, quyết định nghiệp vụ và append event

Event sourcing không bỏ qua command handling. Khi command tới, aggregate phải dựng state hiện tại, kiểm tra invariant rồi quyết định event nào được phép ghi.

Ví dụ command CancelBooking:

1. Load stream Booking-1005.
2. Dựng state hiện tại từ snapshot và các event mới hơn nếu có.
3. Kiểm tra đơn đang ở trạng thái có thể hủy.
4. Kiểm tra thời hạn và quyền của caller.
5. Nếu hợp lệ, append BookingCancelled.
6. Nếu không hợp lệ, trả business rejection; không append event thay đổi trạng thái.

~~~text
handle(CancelBooking(command)):
    state = loadAggregate(command.bookingId)

    if state.status is not CONFIRMED:
        reject("Booking cannot be cancelled")

    if now > state.cancellationDeadline:
        reject("Cancellation window expired")

    append(
        expectedVersion = state.version,
        event = BookingCancelled(
            bookingId = state.id,
            reason = command.reason
        )
    )
~~~

Đây là pseudocode minh họa. Triển khai thực tế cần xác thực quyền, xử lý command trùng, đồng thời ghi event và tạo integration notification theo thiết kế giao dịch cụ thể.

### 4.1. Invariant ở đúng ranh giới

Nếu invariant thuộc một aggregate, mọi command thay đổi aggregate phải được kiểm tra tại cùng ranh giới đó. Ví dụ không được xác nhận booking đã hủy. Việc kiểm tra chỉ ở API gateway hoặc UI là không đủ vì nhiều client, job và consumer có thể gọi cùng domain.

Nếu invariant trải qua nhiều aggregate hoặc bounded context, một transaction event store đơn lẻ có thể không giải quyết được. Cần workflow/process manager, reservation, saga hoặc cơ chế đồng bộ khác.

## 5. Event store: yêu cầu lưu trữ

Event store là nơi lưu stream và hỗ trợ đọc/append theo semantics cần thiết. Có thể dùng sản phẩm event store chuyên dụng hoặc xây trên database/log với thiết kế cẩn thận. Không phải cứ có bảng events là tự động có event store đúng.

Các đặc tính cần đánh giá:

- **Append durability:** event đã xác nhận ghi có sống sót trước lỗi theo cam kết hay không.
- **Per-stream ordering:** event trong cùng stream có thứ tự xác định.
- **Optimistic concurrency:** append chỉ thành công nếu expected version vẫn đúng.
- **Read by stream:** tải event theo aggregate ID và vị trí/version.
- **Global subscription/catch-up:** đọc event mới để xây projection nếu kiến trúc cần.
- **Idempotent append hoặc dedup:** xử lý client retry sau timeout.
- **Retention/archival:** giữ event theo chính sách nghiệp vụ/pháp lý.
- **Backup/restore:** phục hồi store và checkpoint đồng bộ.
- **Security:** encryption, access control, audit và phân tách tenant.

### 5.1. Ví dụ cấu trúc bảng event

~~~sql
CREATE TABLE event_stream (
    stream_id       VARCHAR(200) NOT NULL,
    version         BIGINT NOT NULL,
    event_id        VARCHAR(100) NOT NULL,
    event_type      VARCHAR(200) NOT NULL,
    schema_version  INTEGER NOT NULL,
    occurred_at     TIMESTAMP NOT NULL,
    recorded_at     TIMESTAMP NOT NULL,
    correlation_id  VARCHAR(100),
    payload         JSON NOT NULL,
    PRIMARY KEY (stream_id, version),
    UNIQUE (event_id)
);
~~~

Đây là schema giản lược cho mục đích giảng dạy. CSDL thực tế có thể dùng partitioning, binary payload, metadata column, index bổ sung và chiến lược lưu trữ khác. Relational table cũng cần bảo đảm append concurrency, indexing, transaction và hiệu năng đọc phù hợp.

## 6. Optimistic concurrency và ghi đồng thời

Giả sử hai request cùng load Booking-1005 tại version 12. Request A xác nhận đơn, request B hủy đơn. Nếu cả hai append mà không kiểm tra version, stream có thể chứa hai event mâu thuẫn dựa trên cùng state cũ.

**Expected version** cho phép một request append chỉ khi stream vẫn ở version mong đợi.

~~~mermaid
sequenceDiagram
    participant A as Command A
    participant B as Command B
    participant S as Event Store

    A->>S: Load stream version 12
    B->>S: Load stream version 12
    A->>S: Append event, expectedVersion=12
    S-->>A: Success, new version 13
    B->>S: Append event, expectedVersion=12
    S-->>B: Conflict: actual version 13
    B->>B: Reload state và quyết định lại
~~~

Khi conflict, không nên tự động append lại event cũ. Command handler cần load state mới và đánh giá lại điều kiện; thao tác có thể trở thành không hợp lệ.

### 6.1. Phạm vi của concurrency control

Version stream bảo vệ các ghi lên cùng stream. Nó không tự bảo vệ invariant liên aggregate, ví dụ hai booking cạnh tranh giữ cùng một asset nếu mỗi booking có stream khác nhau. Cần có aggregate/stream sở hữu reservation, unique constraint hoặc cơ chế điều phối phù hợp.

### 6.2. Idempotent command và append retry

Client có thể timeout sau khi event store đã commit nhưng trước khi nhận response. Khi retry command, hệ thống cần biết request đã xử lý chưa. Có thể dùng command ID/idempotency key và lưu kết quả xử lý gắn với command. Event ID cũng cần duy nhất.

Dedup event không đồng nghĩa dedup command: cùng một command có thể tạo nhiều event hợp lệ, còn retry cùng command không nên tạo lại các side effect.

## 7. Dựng trạng thái bằng replay

Replay là quá trình đọc event theo thứ tự và áp dụng chúng lên state ban đầu.

~~~text
v1 AccountOpened(openingBalance=1,000,000)
v2 MoneyDeposited(amount=200,000)
v3 PaymentDebited(amount=350,000)
v4 MoneyDeposited(amount=50,000)
~~~

Reducer có thể áp dụng:

~~~text
apply(state, AccountOpened):
    state.balance = openingBalance

apply(state, MoneyDeposited):
    state.balance += amount

apply(state, PaymentDebited):
    state.balance -= amount
~~~

Sau version 4:

\[
1.000.000 + 200.000 - 350.000 + 50.000 = 900.000\ \text{VND}
\]

Một reducer tốt nên có tính xác định: cùng state ban đầu và cùng chuỗi event đã version hóa phải cho cùng kết quả. Hạn chế gọi API bên ngoài, đọc thời gian hiện tại hoặc dùng cấu hình thay đổi theo môi trường trong hàm apply state.

### 7.1. Replay khác chạy lại command

- **Command** là yêu cầu có thể bị từ chối, phụ thuộc quyền, state hiện tại và điều kiện nghiệp vụ.
- **Replay** áp dụng các quyết định đã được ghi trong event để tái dựng state hoặc projection.

Không replay bằng cách gửi lại mọi command ban đầu như thể người dùng vừa yêu cầu. Làm vậy có thể tính giá lại, gửi thanh toán lại hoặc áp dụng quy tắc hiện tại khác với quyết định lịch sử.

### 7.2. Determinism và dữ liệu ngoài

Reducer không nên tính lại những dữ kiện đã được quyết định bên ngoài nếu event có thể lưu kết quả quyết định. Ví dụ RentalPriceQuoted nên chứa giá và currency đã chốt nếu lịch sử cần tái dựng đúng giá tại thời điểm đó, thay vì replay gọi bảng giá hiện tại.

Nếu event handler phụ thuộc exchange rate, tax rule hoặc lịch ngày lễ, phải lưu kết quả áp dụng hoặc version policy có thể tái lập.

## 8. Replay để làm gì?

| Mục đích | Đầu vào | Kết quả | Lưu ý |
| --- | --- | --- | --- |
| Dựng lại aggregate | Stream của aggregate | Current state | Giữ thứ tự và event semantics |
| Xây read projection | Event từ checkpoint hoặc đầu stream | Bảng đọc mới | Consumer idempotent, theo dõi checkpoint |
| Sửa projection bug | Replay vào projection version mới | Read model đã sửa | Không ghi đè projection đang phục vụ trước khi kiểm tra |
| Tái dựng báo cáo | Event nghiệp vụ | Dataset/analytics | Chính sách dữ liệu và metric phải version |
| Điều tra/audit | Event stream và metadata | Lịch sử quyết định | Kiểm soát quyền truy cập |
| Migration consumer | Event cũ sang schema/read model mới | Projection mới | Kiểm tra compatibility và replay progress |

### 8.1. Không replay side effect

Nếu projection consumer gửi email, gọi payment provider hoặc SMS, replay có thể lặp các tác động bên ngoài. Cần phân biệt:

- **State projector:** chỉ cập nhật read model có thể xóa và dựng lại.
- **Integration side-effect handler:** thực hiện tác động bên ngoài, cần idempotency và không tự chạy khi rebuild projection.
- **Operational replay:** quy trình được phê duyệt, có mode, target, checkpoint và giới hạn rõ.

Nên tách projection builder khỏi integration handler. Không dùng một consumer làm cả cập nhật read model và gửi email nếu cần khả năng replay độc lập.

## 9. Snapshot là gì?

Khi stream có hàng triệu event, dựng aggregate bằng cách replay từ event đầu tiên mỗi lần có command có thể quá chậm. **Snapshot** lưu một biểu diễn state tại version cụ thể để giảm số event phải đọc.

~~~text
Event stream:
v1 ... v5000

Snapshot:
  aggregateId = Booking-1005
  atVersion   = 4800
  state       = { status: CONFIRMED, ... }

Load current state:
  load snapshot at version 4800
  apply events v4801 ... v5000
~~~

Snapshot là **dữ liệu dẫn xuất từ event stream**, không phải nguồn sự thật thay thế event. Nếu snapshot mất hoặc sai, hệ thống phải có khả năng rebuild từ event stream hoặc backup hợp lệ.

~~~mermaid
flowchart LR
    ES[("Event stream v1...vN")] --> RP["Replay events"]
    RP --> SNAP["Snapshot at version K"]
    SNAP --> LOAD["Load snapshot K"]
    ES --> TAIL["Read events K+1...N"]
    LOAD --> REDUCE["Apply tail events"]
    TAIL --> REDUCE
    REDUCE --> STATE["Current aggregate state"]
~~~

### 9.1. Snapshot cadence

Không nhất thiết snapshot sau mọi event. Có thể tạo snapshot theo số event mới, thời gian, kích thước stream, chi phí replay đo được hoặc checkpoint nghiệp vụ phù hợp.

Snapshot quá thường xuyên tăng write và storage; quá thưa tăng thời gian load. Hãy đo p95 load time, event count, snapshot build cost, kích thước state và tần suất command.

### 9.2. Snapshot phải có metadata

Tối thiểu nên có aggregate ID, stream version, snapshot schema/version, timestamp, state payload và có thể checksum/format version. Khi load, xác minh snapshot thuộc stream đúng và version không vượt stream version. Nếu snapshot không đọc được hoặc schema không hỗ trợ, cần fallback sang snapshot cũ hoặc replay đầy đủ theo policy.

Snapshot version K phải đại diện state **sau khi áp dụng đến event K**; sau đó chỉ apply event K+1 trở đi.

## 10. Snapshot và checkpoint của projection khác nhau

Snapshot phục vụ dựng **aggregate state**. Projection checkpoint lưu vị trí consumer đã xử lý trong event stream hoặc log. Hai thứ có thể cùng mang version/offset nhưng mục đích khác nhau.

| Nội dung | Aggregate snapshot | Projection checkpoint |
| --- | --- | --- |
| Mục đích | Giảm số event cần replay để load aggregate | Tiếp tục consumer từ vị trí đã xử lý |
| Lưu gì? | Aggregate state tại một stream version | Offset/version/position đã xử lý |
| Sử dụng bởi | Command handler/aggregate loader | Projection consumer |
| Xóa được không? | Có thể rebuild từ stream | Có thể rebuild projection hoặc checkpoint an toàn |
| Điều cần bảo vệ | Snapshot/schema/state integrity | Checkpoint không vượt quá dữ liệu đã commit |

Nếu consumer cập nhật bảng projection nhưng ghi checkpoint trước khi transaction commit, khi crash hệ thống có thể bỏ qua dữ liệu chưa ghi. Thứ tự cập nhật projection và checkpoint cần atomic hoặc có cơ chế phát hiện và phục hồi.

## 11. CQRS và read projection

Event stream tối ưu cho việc ghi lịch sử và tái dựng aggregate, nhưng không nhất thiết tối ưu cho mọi truy vấn như tìm tất cả đơn của khách hoặc đếm đơn theo trạng thái. Hệ thống thường xây **read projection** từ event.

- Write model kiểm tra command và append event.
- Projection consumer đọc event và cập nhật read database.
- Query API đọc từ read model phù hợp với màn hình.
- Projection có thể eventual consistent và cần theo dõi lag.

~~~mermaid
flowchart TB
    CMD["Commands"] --> AGG["Aggregate / domain logic"]
    AGG --> ES[("Event store")]
    ES --> SUB["Event subscriptions"]
    SUB --> P1["Booking list projection"]
    SUB --> P2["Customer history projection"]
    SUB --> P3["Analytics projection"]
    P1 --> R1[("Query DB A")]
    P2 --> R2[("Query DB B")]
    P3 --> R3[("Warehouse")]
    API["Query API"] --> R1
    API --> R2
~~~

Read projection có thể xóa và dựng lại từ stream nếu logic projector còn tương thích và toàn bộ event cần thiết vẫn được giữ. Không nên để người dùng sửa read model trực tiếp; thay đổi nghiệp vụ phải đi qua command và write model.

### 11.1. Projection có thể lag

Khi event store append xong nhưng consumer chưa xử lý, query có thể vẫn trả trạng thái cũ. API có thể trả projection version/lastUpdated hoặc cung cấp read-your-writes bằng cách chờ checkpoint đạt version yêu cầu trong giới hạn thời gian.

Không giả định transaction giữa event store và mọi read DB là atomic. Nếu cần command đồng thời làm read model cập nhật ngay, phải thiết kế consistency contract rõ.

## 12. Event sourcing và transactional outbox

Event store là nguồn trạng thái trong event sourcing. Nếu hệ thống cần publish event sang broker/consumer bên ngoài, phải bảo đảm ghi event và thông báo phát event không bị lệch nhau.

Trong kiến trúc CRUD dùng relational DB, transactional outbox ghi thay đổi nghiệp vụ và outbox record cùng transaction. Trong event sourcing, event store có thể cung cấp subscription/change feed đáng tin cậy; hoặc adapter theo dõi stream và checkpoint. Mục tiêu là không có trường hợp event đã commit nhưng integration event bị mất không có cách phát hiện.

### 12.1. Domain event và integration event

- **Domain event:** phục vụ mô hình nghiệp vụ nội bộ và có thể chứa chi tiết theo domain.
- **Integration event:** hợp đồng công bố ra ngoài bounded context, cần ổn định, version hóa và giảm dữ liệu nhạy cảm.

Không nên phát nguyên payload nội bộ ra mọi consumer. Integration adapter có thể ánh xạ và lọc domain event thành contract công khai.

## 13. Event schema evolution

Event store giữ lịch sử lâu dài nên event schema phải sống lâu hơn một lần deploy ứng dụng. Field đổi tên, đổi kiểu hoặc thay ý nghĩa có thể làm replay event cũ thất bại.

Các chiến lược:

1. **Additive change:** thêm field optional với default phù hợp.
2. **Upcasting:** chuyển event version cũ thành biểu diễn mới khi đọc, không nhất thiết rewrite dữ liệu lịch sử.
3. **Versioned event type:** tạo type/version mới khi semantic thay đổi đáng kể.
4. **Transformation/rewrite:** chỉ thực hiện khi có lý do, kiểm tra integrity, backup và audit đầy đủ.

~~~text
v1 BookingCreated:
    bookingId, customerId

v2 BookingCreated:
    bookingId, customerId, currency

Upcaster:
    if event schema is v1:
        currency = default determined by historical policy
        return v2 representation
~~~

Default cho event lịch sử phải có căn cứ. Nếu currency không thể suy ra an toàn, không nên gán giá trị tùy tiện; cần dữ liệu tham chiếu đã version hóa hoặc giữ semantics v1 trong reducer.

### 13.1. Tránh dùng cấu hình hiện tại cho lịch sử

Nếu replay event năm ngoái bằng tax rate hoặc pricing policy hôm nay, kết quả có thể khác quyết định ban đầu. Event cần giữ dữ liệu đã chốt hoặc tham chiếu version policy có thể tái dựng. Với dữ liệu nhạy cảm, cân nhắc không lưu quá nhiều thông tin cá nhân trong payload vĩnh viễn.

## 14. Dữ liệu nhạy cảm, quyền riêng tư và retention

Event sourcing tạo ra lịch sử có giá trị cao nhưng cũng làm việc sửa/xóa dữ liệu khó hơn. Nếu event append-only được giữ dài hạn, yêu cầu xóa dữ liệu cá nhân có thể xung đột với payload chứa thông tin định danh.

Cần thiết kế ngay từ đầu:

- **Data minimization:** event chỉ chứa dữ liệu cần để bảo toàn ý nghĩa nghiệp vụ.
- **Reference thay payload:** lưu ID tham chiếu tới profile có thể xóa/cập nhật khi phù hợp; đánh đổi là replay cần dữ liệu tham chiếu đã version hóa hoặc snapshot.
- **Encryption/tokenization:** mã hóa hoặc token hóa trường nhạy cảm với key lifecycle rõ.
- **Separate PII store:** tách thông tin định danh khỏi event stream để xử lý quyền xóa phù hợp.
- **Retention policy:** phân loại event theo nghĩa vụ lưu trữ và mục đích; không giữ vô thời hạn theo mặc định.
- **Access control/audit:** quyền đọc event thường nhạy cảm hơn quyền xem read model; truy vấn replay/export cần kiểm soát.
- **Backup and archive:** bản sao lưu, archive và replica cũng phải nằm trong chính sách dữ liệu.

Không phải lúc nào cũng có thể xóa sạch một event khỏi log append-only mà không ảnh hưởng integrity hoặc nghĩa vụ lưu trữ. Có thể cần crypto-erasure, tách PII, tombstone hoặc quy trình pháp lý/kiểm soát đặc biệt tùy chính sách và quy định áp dụng. Đây là quyết định cần chuyên gia có thẩm quyền xác nhận.

## 15. Event sourcing trong hệ thống phân tán và consistency

Event sourcing không tự tạo distributed transaction giữa nhiều aggregate hoặc service. Một event append vào stream A không khiến stream B và database của service C commit nguyên tử.

Nếu use case trải qua nhiều aggregate, có thể dùng process manager/saga, reservation, compensation, eventual consistency, idempotent consumer và reconciliation.

Ví dụ Booking được tạo nhưng Inventory chưa xác nhận giữ chỗ. State có thể là PENDING_RESERVATION; khi có ReservationAccepted, workflow chuyển sang PENDING_PAYMENT. Không nên ghi CONFIRMED chỉ vì command đầu tiên đã được nhận.

### 15.1. Trạng thái tạm là một phần của mô hình

Event sourcing thường khiến vòng đời nhiều trạng thái rõ hơn. Tuy nhiên, không nên tạo quá nhiều status không phản ánh quy tắc nghiệp vụ. Mỗi transition cần điều kiện, owner và cách xử lý lỗi/timeout.

## 16. Hiệu năng, partitioning và hot stream

Mỗi aggregate thường có một stream có thứ tự. Nếu một aggregate nhận quá nhiều ghi, stream đó có thể thành hot stream vì mọi append cần phối hợp version.

Các câu hỏi hiệu năng:

- Có quá nhiều event trên một aggregate không?
- Có thể tách aggregate theo ranh giới invariant mà vẫn đúng nghiệp vụ không?
- Partitioning theo stream/tenant/aggregate ID có phân bố tải đều không?
- Query projection có cần index riêng?
- Payload có lớn hoặc lặp dữ liệu quá nhiều không?
- Replay có thể giới hạn theo time/version hoặc dùng snapshot không?
- Subscription có consumer lag hoặc checkpoint contention không?

Không tách aggregate chỉ để tăng throughput nếu điều đó phá invariant. Nếu một tài khoản có hàng nghìn giao dịch mỗi giây, có thể cần thiết kế ledger/partition chuyên biệt; không nhất thiết một stream duy nhất phù hợp.

## 17. Snapshot, archive và retention

Một hệ thống event-sourced lâu dài cần chính sách cho event cũ, snapshot và bản sao lưu.

| Thành phần | Cách quản lý | Rủi ro cần kiểm soát |
| --- | --- | --- |
| Event nóng | Store có latency thấp, append/read thường xuyên | Storage cost, index và backup |
| Event lịch sử ít truy cập | Archive/object storage hoặc tier rẻ hơn | Tăng restore/replay latency |
| Snapshot | Tạo theo ngưỡng; lưu version và schema | Snapshot lỗi hoặc không tương thích |
| Projection hiện tại | Database tối ưu cho query | Có thể rebuild nhưng tốn thời gian |
| Checkpoint | Lưu vị trí consumer bền vững | Checkpoint sai làm thiếu/trùng dữ liệu |
| Backup event store | Backup/replication theo RPO/RTO | Restore cần kiểm tra thứ tự và integrity |

### 17.1. Snapshot không thay thế backup

Snapshot là state dẫn xuất ở version K. Nó không bảo vệ toàn bộ event stream trước lỗi xóa nhầm, corruption hoặc compromise. Event store cần backup/replication và thử phục hồi riêng; projection cũng cần được kiểm tra khả năng rebuild hoặc phục hồi.

### 17.2. Replay sau archive

Nếu event cũ được chuyển sang archive, aggregate loader có thể lấy snapshot và chỉ đọc phần event nóng mới. Nhưng rebuild projection từ đầu vẫn cần toàn bộ lịch sử hoặc baseline được tin cậy. Archive phải nêu cách truy xuất, kiểm tra integrity, restore và chi phí egress.

## 18. Kiểm thử event-sourced system

Kiểm thử cần bao phủ reducer, command decision, concurrency, replay, schema evolution và side effect.

- **Reducer tests:** chuỗi event đã biết cho ra state mong đợi.
- **Command tests:** state hiện tại và command tạo đúng event hoặc business rejection.
- **Invariant tests:** transition sai bị từ chối.
- **Concurrency tests:** append đồng thời cùng expected version chỉ một request thắng.
- **Replay tests:** rebuild state/projection cho kết quả tương ứng với bản chuẩn.
- **Snapshot tests:** load snapshot K rồi apply event K+1...N cho kết quả giống full replay.
- **Schema compatibility tests:** event version cũ đọc được bằng reducer/upcaster mới.
- **Duplicate/reordering tests:** consumer xử lý duplicate, event đến muộn hoặc sequence gap theo contract.
- **Failure/recovery tests:** crash sau append, trước publish, trong projection update và trước checkpoint.
- **Privacy/security tests:** quyền đọc stream, masking, retention và xóa/tách dữ liệu đúng chính sách.

### 18.1. Property-based và invariant tests

Ví dụ với tài khoản: số dư không được xuống dưới hạn mức cho phép; replay mọi stream hợp lệ phải duy trì invariant này. Có thể tạo chuỗi event/command ngẫu nhiên để tìm tổ hợp transition chưa được nghĩ tới. Test phải xác định rõ event nào hợp lệ, không kỳ vọng reducer âm thầm sửa event vi phạm.

## 19. Ví dụ thực tế: vòng đời đơn thuê

Giả sử nền tảng cho thuê thiết bị cần lưu lịch sử quyết định đặt thuê để giải thích vì sao đơn được xác nhận, hủy hoặc hoàn tiền.

### 19.1. Stream ví dụ

~~~text
Booking-1005
v1 BookingCreated(customerId, itemId, startAt, endAt)
v2 ReservationAccepted(reservationId, expiresAt)
v3 PaymentAuthorized(paymentReference, amount, currency)
v4 BookingConfirmed(confirmedAt)
v5 CancellationRequested(reason, requestedAt)
v6 BookingCancelled(cancelledAt)
v7 RefundRequested(refundId, amount)
v8 RefundCompleted(refundId, providerReference)
~~~

Chuỗi trên chỉ là ví dụ. Một số hệ thống có thể dùng aggregate riêng cho Payment/Refund; không nhất thiết nhét tất cả domain vào Booking stream.

### 19.2. State được dựng như thế nào?

- BookingCreated tạo trạng thái ban đầu.
- ReservationAccepted đánh dấu tài sản đã giữ.
- PaymentAuthorized lưu reference và số tiền được ủy quyền.
- BookingConfirmed chuyển đơn sang confirmed.
- CancellationRequested ghi nhận yêu cầu hủy nhưng chưa chắc đơn đã hủy.
- BookingCancelled xác nhận transition đã hoàn tất.
- Refund event mô tả tiến trình hoàn tiền.

Điểm phân biệt là request và outcome. RefundRequested không đồng nghĩa tiền đã được hoàn. Hệ thống cần event kết quả như RefundCompleted hoặc RefundFailed.

### 19.3. Snapshot và query projection

Sau version 100 của Booking stream, hệ thống có thể lưu snapshot chứa trạng thái đơn đã xác nhận, thông tin tham chiếu và version 100. Query projection có thể chứa một dòng cho màn hình danh sách đơn. Snapshot giúp command handler dựng aggregate nhanh; projection giúp truy vấn danh sách nhanh. Hai cấu trúc có mục đích khác nhau và có thể có schema riêng.

### 19.4. Replay để sửa projection

Giả sử projection cũ tính sai số ngày thuê do lỗi timezone. Quy trình:

1. Sửa projector và thêm test với biên ngày/giờ.
2. Tạo projection version mới hoặc bảng mới, không xóa ngay bảng đang phục vụ.
3. Replay event từ checkpoint/đầu stream phù hợp.
4. So sánh số bản ghi, trạng thái, số liệu và checksum với kiểm tra độc lập.
5. Xác minh lag và dữ liệu biên, sau đó chuyển query sang projection mới.
6. Giữ đường rollback trong thời gian quy định và retire projection cũ sau khi ổn định.

Replay projection không được gửi lại email xác nhận, yêu cầu payment hoặc hoàn tiền. Các consumer side effect phải chạy theo luồng live có idempotency riêng.

## 20. Khi nào event sourcing phù hợp?

Event sourcing có giá trị khi **lịch sử thay đổi là một phần quan trọng của dữ liệu**, cần khả năng tái dựng state hoặc xây nhiều góc nhìn đọc từ cùng các sự kiện nghiệp vụ.

Các điều kiện thường nghiêng về event sourcing:

1. **Audit sâu:** cần giải thích ai/điều gì đã tạo ra state và chuỗi quyết định.
2. **Business history quan trọng:** tài chính, ledger, hợp đồng, booking hoặc quy trình nhiều trạng thái.
3. **Temporal reconstruction:** cần dựng state tại một thời điểm hoặc theo version.
4. **Nhiều projection:** cùng lịch sử phục vụ read model, báo cáo và tích hợp.
5. **Replay có ích thực sự:** cần rebuild projection, sửa logic đọc hoặc migrate schema.
6. **Quy tắc nghiệp vụ rõ:** aggregate boundary và event semantics có thể mô hình hóa.
7. **Đội vận hành đủ năng lực:** có tooling cho event store, replay, backup, schema và observability.

Một tổ chức có thể dùng event sourcing cho một số domain như ledger/booking mà vẫn dùng CRUD cho profile, catalog hoặc cấu hình ít cần lịch sử. Không cần áp dụng cho toàn hệ thống.

## 21. Khi nào không nên dùng?

Event sourcing thường không đáng với dữ liệu đơn giản mà chỉ cần state hiện tại, hoặc khi tổ chức chưa có năng lực vận hành lịch sử event dài hạn.

Các tín hiệu:

- **CRUD đơn giản:** danh mục ít thay đổi, không cần dựng lại lịch sử.
- **Không có nhu cầu replay/audit mạnh:** current state và audit log phù hợp là đủ.
- **Đội chưa quản lý được schema evolution:** event format được giữ nhiều năm nhưng consumer thay đổi liên tục.
- **Quy trình nghiệp vụ chưa rõ:** event type và aggregate boundary thay đổi liên tục, gây chi phí migration.
- **Yêu cầu xóa dữ liệu mâu thuẫn retention:** chưa có thiết kế PII, crypto-erasure hoặc legal hold.
- **Khối lượng quá lớn trên một aggregate nóng:** cần kiến trúc chuyên biệt để giữ thứ tự và throughput.
- **Truy vấn linh hoạt là nhu cầu chủ đạo:** event stream không thay thế database query/read model.
- **Chi phí và complexity vượt lợi ích:** event store, projections, snapshots, replay tooling và on-call quá nặng.

Không nên triển khai event sourcing chỉ vì muốn có audit trail. Một audit log đáng tin cậy, có kiểm soát bất biến và lưu trữ đúng có thể đáp ứng yêu cầu với chi phí thấp hơn.

## 22. Đánh đổi kiến trúc

| Tiêu chí | Lợi ích | Chi phí/rủi ro |
| --- | --- | --- |
| Lịch sử nghiệp vụ | Tái dựng, audit và giải thích state | Dữ liệu tăng theo thời gian, cần retention |
| Replay | Rebuild projection, thử logic mới trên lịch sử | Tốn tài nguyên, phải tránh side effect |
| Snapshot | Giảm event cần load | Thêm logic version, storage và validation |
| CQRS | Read model tối ưu theo use case | Eventual consistency và đồng bộ projection |
| Schema evolution | Giữ lịch sử lâu dài | Cần upcaster, compatibility và test |
| Concurrency | Expected version bảo vệ cùng stream | Conflict và retry khi nhiều command |
| Security/privacy | Audit rõ và kiểm soát lịch sử | Event lưu PII lâu và quyền đọc rộng |
| Operations | Có thể phục hồi/read model từ stream | Tooling replay, backup và incident response phức tạp |
| Cost | Tách write/read và nhiều projection | Event storage, replication, index, compute và archive |

Có thể chọn mức phù hợp:

- CRUD với audit metadata khi chỉ cần trạng thái hiện tại và lịch sử ai sửa.
- CRUD + transactional outbox khi cần phát event tích hợp đáng tin cậy.
- Event log có giới hạn khi chỉ cần lưu một số loại thay đổi phục vụ audit.
- Event sourcing đầy đủ khi event là nguồn sự thật và replay/state reconstruction có giá trị nghiệp vụ rõ.

Các mức này không phải cấp độ trưởng thành bắt buộc. Chọn phương án tối giản đáp ứng yêu cầu có thể đo.

## 23. Lộ trình triển khai an toàn

1. **Chọn bounded context:** bắt đầu với domain có lịch sử quan trọng, ranh giới và owner rõ.
2. **Định nghĩa aggregate và invariant:** xác định stream ID, concurrency scope và transition hợp lệ.
3. **Định nghĩa event contract:** tên, schema, metadata, version và dữ liệu tối thiểu.
4. **Chọn event store:** kiểm tra durability, expected version, subscriptions, backup, retention và security.
5. **Viết reducer/command handler:** bảo đảm apply logic deterministic và business rejection.
6. **Thiết kế projection:** query model, checkpoint, idempotency và rebuild strategy.
7. **Thiết kế snapshot:** đo stream length/load time, schema và fallback.
8. **Thiết kế side effect:** tách integration handlers, outbox/subscription, dedup và compensation.
9. **Xác định privacy/retention:** PII, encryption, legal hold và archive.
10. **Thiết lập observability:** stream version, append conflict, projection lag, replay progress và storage growth.
11. **Diễn tập recovery:** restore event store, rebuild projection và load aggregate từ snapshot.
12. **Review quyết định:** tiếp tục, mở rộng hoặc thu hẹp phạm vi dựa trên TCO và lợi ích thực tế.

## 24. Các lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Cách phòng tránh |
| --- | --- | --- |
| Coi event sourcing giống phát message | Broker không có lịch sử/semantics đủ để dựng state | Xác định event store là source of truth |
| Event là snapshot row sau mỗi update | Payload lớn và khó hiểu ý nghĩa nghiệp vụ | Ghi event mô tả thay đổi có nghĩa |
| Không kiểm tra expected version | Command đồng thời tạo transition mâu thuẫn | Optimistic concurrency theo stream |
| Reducer gọi API hoặc đọc thời gian hiện tại | Replay cho kết quả khác nhau | Giữ apply logic deterministic, lưu dữ kiện cần thiết |
| Replay toàn bộ handler có side effect | Gửi email/thu tiền lặp lại | Tách projector và integration side-effect consumer |
| Snapshot không ghi version | Áp event sai đoạn hoặc bỏ sót | Lưu atVersion và chỉ apply phần tiếp theo |
| Snapshot bị coi là backup | Mất event lịch sử khi store lỗi | Backup/replicate event store riêng |
| Schema event thay đổi phá vỡ replay | Consumer cũ không đọc được lịch sử | Version, upcasting và compatibility test |
| Replay trong giờ cao điểm không giới hạn | Tăng tải DB, ảnh hưởng production | Rate limit replay và dùng projection target riêng |
| Một stream quá nóng | Conflict/latency cao | Review aggregate boundary và invariant |
| Event chứa PII không có retention | Khó xử lý yêu cầu xóa, tăng phạm vi rò rỉ | Data minimization, tokenization, retention |
| Projection checkpoint ghi trước dữ liệu | Bỏ qua event khi restart | Atomic update hoặc recovery protocol |
| Dùng event log làm query database | Query khó và chậm | CQRS/read projection phù hợp |
| Chọn event sourcing chỉ vì audit | Chi phí vận hành vượt lợi ích | So sánh với audit log/CRUD + outbox |

## 25. Kiểm tra và nghiệm thu kiến trúc

Một hệ thống event-sourced cần chứng minh được khả năng ghi, đọc, replay và phục hồi.

- [ ] Event là source of truth cho aggregate được chọn; ranh giới CRUD/event sourcing rõ.
- [ ] Aggregate ID và event stream version có quy tắc nhất quán.
- [ ] Append hỗ trợ expected version/concurrency và command retry idempotent.
- [ ] Event chứa schema version, event ID, correlation và dữ liệu cần tái dựng.
- [ ] Reducer deterministic và có test invariant.
- [ ] Replay state và projection không lặp side effect.
- [ ] Snapshot có atVersion, schema version, validation và fallback.
- [ ] Projection checkpoint không vượt quá dữ liệu đã commit.
- [ ] Schema evolution/upcasting xử lý được event lịch sử.
- [ ] PII, retention, archive, encryption và quyền đọc stream được thiết kế.
- [ ] Event store có backup/restore và đã diễn tập.
- [ ] Có metric append conflict, stream length, projection lag, replay progress và storage growth.
- [ ] Có giới hạn tải replay và runbook xử lý lỗi projection/DLQ.
- [ ] Đã so sánh lợi ích với CRUD, audit log và outbox.

## 26. Đánh giá theo Well-Architected

| Góc nhìn | Câu hỏi thiết kế |
| --- | --- |
| **Độ tin cậy** | Append đã xác nhận có durable? Event store có backup? Snapshot có thể rebuild? Replay và projection có checkpoint phục hồi? |
| **Bảo mật** | Ai được đọc stream? Payload có PII/secret? Retention, key lifecycle, legal hold và audit được quản lý? |
| **Hiệu quả hiệu năng** | Stream length, append latency, replay duration và projection lag có nằm trong SLO? Snapshot cadence có phù hợp? |
| **Tối ưu chi phí** | Event storage, replication, indexing, archive, snapshot và replay compute có được dự báo? |
| **Khả năng vận hành** | Có tooling xem stream, theo dõi version/conflict, rebuild projection, rollback consumer và diễn tập recovery? |

## 27. Bài tập áp dụng

Một nền tảng tài chính nội bộ cần quản lý tài khoản chi tiêu. Yêu cầu gồm: mọi thay đổi số dư phải giải thích được; cần tái dựng số dư tại cuối tháng bất kỳ; báo cáo theo phòng ban được cập nhật trong vài phút; một số thông tin người dùng phải có thể được xóa hoặc tách theo chính sách lưu trữ. Lưu lượng có thể có một số tài khoản tổng hợp nhận rất nhiều giao dịch.

Hãy đề xuất:

1. Có nên dùng event sourcing cho toàn hệ thống hay chỉ cho ledger/account domain? Giải thích.
2. Thiết kế aggregate, event type và metadata để giữ lịch sử thay đổi số dư.
3. Làm sao xử lý hai giao dịch đồng thời trên cùng tài khoản?
4. Snapshot nên tạo theo điều kiện nào và cần lưu version gì?
5. Làm thế nào xây projection báo cáo theo phòng ban và rebuild khi sửa logic?
6. Event nào có thể chứa PII, dữ liệu nào nên token hóa hoặc tham chiếu ngoài?
7. Quy trình replay phải ngăn gửi lại thông báo, gọi thanh toán hoặc áp dụng side effect thế nào?
8. Đặt SLO, retention, backup và kiểm thử recovery ra sao?
9. Những dấu hiệu nào chứng minh event store hoặc một stream aggregate đang trở thành nút thắt?

Một phương án có cơ sở có thể dùng event sourcing cho ledger, tách profile cá nhân thành kho dữ liệu có lifecycle khác, dùng projection cho báo cáo, snapshot để tăng tốc load aggregate và kiểm soát concurrency theo account. Phải có chính sách rõ cho PII, backup, replay và các tài khoản nóng; không nên chỉ tăng số consumer nếu mọi ghi vẫn tranh chấp cùng một stream.

**Điểm cốt lõi:** event sourcing biến lịch sử thay đổi nghiệp vụ thành nguồn dữ liệu chính; replay dựng lại state hoặc projection; snapshot giảm lượng event phải đọc nhưng vẫn là dữ liệu dẫn xuất. Mô hình có giá trị khi lịch sử, khả năng giải thích và tái dựng thật sự quan trọng, đồng thời tổ chức đủ năng lực quản lý schema, privacy, storage, concurrency và recovery. Nếu chỉ cần trạng thái hiện tại hoặc audit đơn giản, CRUD kết hợp audit log/outbox thường là phương án dễ vận hành hơn.
