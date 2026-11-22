# Commit, rollback và các kết quả chưa xác định khi mất kết nối

Một ứng dụng Java gửi yêu cầu **đặt phòng** vào NoSQL. Database nhận thao tác, ghi dữ liệu và có thể đã commit. Ngay sau đó, kết nối mạng đứt trước khi phản hồi tới ứng dụng. Java chỉ thấy **timeout**.

Câu hỏi khó không phải “có lỗi mạng không?”, mà là: **giao dịch đã commit hay chưa?** Nếu ứng dụng coi timeout là thất bại rồi tạo yêu cầu mới, có thể đặt phòng hai lần hoặc trừ tiền hai lần. Nếu coi timeout là thành công, có thể báo khách đã đặt được phòng dù database thực ra chưa ghi gì.

Đây là bài toán **kết quả chưa xác định (unknown/ambiguous outcome)**: từ góc nhìn client, sau khi mất kết nối, có thể có nhiều lịch sử thực thi khác nhau dẫn tới **cùng một lỗi timeout**. Không thể suy ra kết quả commit chỉ từ ngoại lệ mạng.

Trong chương **Giao dịch và nguyên tử** của **Database No SQL**, bài học này giải thích ranh giới commit, rollback, atomicity, durability và replication; cách xử lý timeout, retry và idempotency; những khác biệt cần lưu ý trong MongoDB, DynamoDB, Cassandra, Redis; cùng một kiến trúc Java để truy hồi kết quả thay vì tạo tác dụng phụ trùng.

> **Nguyên tắc xuyên suốt:** “Tôi không nhận được ACK” **không đồng nghĩa** “database không commit”. “Tôi nhận timeout” cũng **không chứng minh** “database đã commit”. Hãy giữ trạng thái **UNKNOWN**, dùng định danh thao tác bền vững để tra cứu/thử lại an toàn, và chỉ báo thành công hoặc thất bại nghiệp vụ khi có bằng chứng phù hợp.

## 1. Phân biệt transaction, commit, rollback và phản hồi mạng

Các khái niệm dễ bị nhầm:

| Khái niệm | Ý nghĩa | Điều không nên suy diễn |
| --- | --- | --- |
| **Transaction (giao dịch)** | Đơn vị thay đổi được engine quản lý với hợp đồng atomicity/isolation/durability cụ thể | Mọi database NoSQL đều hỗ trợ transaction đa tài liệu giống nhau |
| **Atomicity (tính nguyên tử)** | Trong phạm vi được bảo đảm, thay đổi của transaction được áp dụng như một đơn vị hoặc không áp dụng | Atomicity của một item bao gồm cả email, HTTP và dịch vụ thanh toán |
| **Commit** | Chuyển transaction sang trạng thái được chấp nhận/bền vững theo hợp đồng engine | Client chắc chắn đã nhận được thông báo commit |
| **Abort/rollback** | Hủy thay đổi chưa commit, theo cơ chế hỗ trợ | Có thể đảo ngược tự động mọi tác dụng phụ đã xảy ra sau commit |
| **Write acknowledgment (ACK)** | Thông điệp cho client biết database đã đạt một mức xác nhận | ACK luôn đồng nghĩa dữ liệu đã tồn tại trên mọi replica và mọi vùng |
| **Timeout/mất kết nối** | Client không nhận kết quả trong hạn hoặc mất đường truyền | Transaction chắc chắn thất bại |
| **Durability** | Dữ liệu đã commit sống sót qua những dạng sự cố được bảo đảm | Mọi cấu hình mặc định đều bền qua mất điện và mọi thảm họa |
| **Isolation** | Quy định transaction đồng thời nhìn và ảnh hưởng nhau thế nào | Atomicity tự bảo đảm không có lost update, write skew hoặc oversell |

Ví dụ một giao dịch chuyển tiền nội bộ giữa hai ví trong cùng một kho hỗ trợ transaction:

~~~~text
Tài khoản A: 1.000
Tài khoản B:   200

Transaction:
  A -= 100
  B += 100

Sau commit thành công:
  A = 900
  B = 300

Nếu abort trước commit:
  A = 1.000
  B =   200
~~~~

Đây là **bất biến trong một ranh giới transaction**. Nếu hai tài khoản thuộc hai dịch vụ độc lập, một transaction ở database A không mặc nhiên làm thay đổi tại database B theo kiểu tất cả-hoặc-không.

### 1.1. Điểm commit là sự kiện ở server, không phải tại nút “Gửi” của client

Một luồng đơn giản:

~~~~mermaid
sequenceDiagram
    participant Client as Java client
    participant DB as NoSQL database
    Client->>DB: Write / commit request
    DB->>DB: Check constraints and apply transaction
    DB->>DB: Reach commit decision
    DB-->>Client: Success acknowledgment
~~~~

**Commit** xảy ra theo giao thức của database. **ACK** là một thông điệp truyền qua mạng sau hoặc quanh các bước được quy định trong giao thức đó.

Nếu phản hồi bị mất, transaction có thể vẫn còn nguyên trạng thái **committed**. Việc client đóng socket không phải lệnh rollback.

### 1.2. Nơi dữ liệu “đã ghi” không luôn là nơi “đã bền vững”

Một engine có thể trải qua các mốc:

~~~~text
request received
  -> validated
  -> in-memory / WAL / replica steps
  -> commit decision
  -> durability threshold satisfied
  -> response sent
  -> response received by client
~~~~

Thứ tự và bảo đảm chính xác phụ thuộc sản phẩm cùng cấu hình write concern, fsync, replication và transaction.

Ví dụ một ACK chỉ phản ánh việc leader nhận ghi có thể yếu hơn ACK yêu cầu **quorum/majority** hoặc trạng thái bền vững theo chính sách. Không thể dùng một câu “database trả success” mà bỏ qua **success theo mức bảo đảm nào**.

## 2. Tình huống kinh điển: commit xong nhưng ACK bị mất

Giả sử API tạo booking bằng lệnh:

~~~~text
createBooking(
    roomId = "R-08",
    checkIn = "2026-12-01",
    checkOut = "2026-12-03"
)
~~~~

Dòng thời gian:

~~~~mermaid
sequenceDiagram
    participant User
    participant API as Booking API
    participant DB as Booking Store
    User->>API: POST /bookings
    API->>DB: Insert booking + commit
    DB->>DB: Commit thành công
    DB--xAPI: Response bị mất do lỗi mạng
    API-->>User: Timeout / outcome unknown
    Note over User,DB: Booking có thể đã tồn tại dù client chỉ thấy lỗi
~~~~

Từ phía API, không có phản hồi nên **không có bằng chứng trực tiếp** rằng thao tác đã commit. Nhưng dữ liệu thực có thể đã tồn tại.

Nếu retry tạo một booking mới với ID mới:

~~~~text
Lần 1:
  DB committed booking B-901
  Response bị mất

Lần 2:
  API tạo booking B-902
  DB committed booking B-902

Kết quả:
  Hai booking cho cùng một ý định của khách.
~~~~

**Retry không có idempotency** là nguyên nhân phổ biến của duplicate order, double charge, hai thông báo email hoặc hai lần cộng điểm.

### 2.1. Những thời điểm lỗi khác nhau có thể tạo cùng một timeout

| Vị trí lỗi | Điều thực sự có thể xảy ra | Client thường thấy |
| --- | --- | --- |
| Trước khi request được gửi | DB chưa từng nhận | Timeout, connection error |
| Request đến nhưng bị reject trước khi thực thi | Không có thay đổi commit | Error nếu phản hồi đến; timeout nếu không |
| Server đang thực thi/chưa ra quyết định | Có thể tiếp tục rồi commit hoặc abort | Timeout |
| Server đã abort | Không commit | Error hoặc timeout |
| Server đã commit, ACK bị mất | **Đã commit** | Timeout |
| Server trả ACK, proxy/API cắt kết nối | Có thể đã commit | 502/504/connection error ở tầng trên |
| Client nhận success, sau đó tiến trình crash trước khi ghi trạng thái local | Đã commit nhưng client mất ký ức | Lần khởi động sau có thể coi là chưa làm |

**Một biểu hiện quan sát giống nhau có thể tương ứng nhiều trạng thái thật.** Vì thế cần thiết kế khả năng xác định trạng thái **theo định danh thao tác**, không dựa trên cảm giác về thời điểm timeout.

## 3. Mô hình ba trạng thái từ góc nhìn client

Từ góc nhìn ứng dụng, có thể mô hình hóa kết quả:

- **COMMITTED:** Có bằng chứng đáng tin rằng transaction đã commit theo hợp đồng được yêu cầu.
- **NOT_COMMITTED/REJECTED:** Có bằng chứng kết luận thao tác không commit và không còn có thể commit dưới chính định danh đó.
- **UNKNOWN:** Không đủ bằng chứng để kết luận một trong hai trạng thái trên.

**UNKNOWN là trạng thái tri thức của client**, không nhất thiết là một trạng thái được lưu trong transaction engine. Server có thể đã biết rõ committed hoặc aborted, còn client thì chưa.

~~~~mermaid
stateDiagram-v2
    [*] --> SUBMITTED
    SUBMITTED --> COMMITTED: Verified commit
    SUBMITTED --> REJECTED: Verified non-commit / final rejection
    SUBMITTED --> UNKNOWN: Timeout / connection loss
    UNKNOWN --> COMMITTED: Reconcile / same-operation retry
    UNKNOWN --> REJECTED: Authoritative final result
    UNKNOWN --> UNKNOWN: Still unresolved
    COMMITTED --> [*]
    REJECTED --> [*]
~~~~

**Không nên tự chuyển UNKNOWN → REJECTED chỉ vì đã qua 30 giây.** Hết thời gian chờ của client không tự thu hồi một giao dịch đã commit hoặc một request vẫn đang được server xử lý.

### 3.1. “Failed” là từ quá mơ hồ

Hãy phân biệt:

~~~~text
NETWORK_FAILED    -> Không biết kết quả nghiệp vụ.
VALIDATION_FAILED -> Server từ chối yêu cầu theo rule.
CONFLICT          -> Điều kiện ghi không thỏa; biết kết quả của lần ghi đó.
ABORTED           -> Transaction bị hủy và không commit.
COMMITTED         -> Transaction đạt commit theo hợp đồng.
~~~~

Một endpoint nên đưa ra lỗi có **mã và ngữ nghĩa rõ**, thay vì chỉ trả **500 Internal Server Error** rồi bắt người gọi tự đoán có thể retry được không.

### 3.2. Những bằng chứng mạnh và yếu

**Bằng chứng mạnh hơn:**

- Commit ACK hợp lệ theo mức durability yêu cầu.
- Bản ghi kết quả thao tác **operationId** trong nguồn có thẩm quyền, được ghi nguyên tử cùng thay đổi nghiệp vụ.
- Một bản ghi trạng thái cuối đã được đối soát bằng đường đọc và consistency phù hợp.
- Phản hồi lặp lại từ một idempotency ledger còn bền vững và cùng payload fingerprint.

**Bằng chứng yếu hoặc không đủ:**

- HTTP timeout.
- Log client ghi “send succeeded”.
- Tìm không thấy bản ghi trong cache/GSI/search index cập nhật bất đồng bộ.
- Một event đã xuất hiện trên message broker nhưng source commit chưa được chứng minh.
- Consumer nhận message một lần.
- Một log không có commit record vì log đã bị xoay vòng hoặc ghi không đầy đủ.

**“Không tìm thấy” có thể không chứng minh “không commit”** khi read path eventual, commit còn đang xử lý, lookup sai khóa, hoặc ledger chưa đủ độ tin cậy.

## 4. Commit, rollback và chuyện đã commit không thể “rollback lại”

### 4.1. Rollback/abort trước commit

Trong transaction hỗ trợ rollback, nếu một bước không hợp lệ trước điểm commit, engine có thể hủy toàn bộ các thay đổi trong ranh giới transaction:

~~~~text
BEGIN
  Reserve room R-08 for slot S
  Insert booking B-901
  Insert operation result OP-101
COMMIT
~~~~

Nếu transaction bị abort do xung đột hoặc validation trước commit, các cập nhật thuộc **cùng transaction atomic** không được công bố thành một phần thành công.

Tuy nhiên, kết quả còn phụ thuộc ranh giới: nếu code đã **gửi email** hoặc **gọi provider thanh toán** giữa các bước, những tác dụng phụ bên ngoài **không được database rollback tự động**.

### 4.2. Khi đã commit, cần giao dịch bù chứ không phải rollback quá khứ

Giả sử Booking Store đã commit B-901. Khách thay đổi ý định; API muốn hủy booking:

~~~~text
BookingConfirmed(B-901)  -> đã commit
BookingCancelled(B-901)  -> một thay đổi nghiệp vụ mới
~~~~

Thao tác hủy có thể:
- Chuyển trạng thái booking từ CONFIRMED sang CANCELLED.
- Trả lại inventory/slot theo chính sách.
- Phát event hủy.
- Nếu đã thu tiền, yêu cầu **refund** qua payment provider.

Đây là **compensation**, không phải phục hồi một transaction chưa từng xảy ra. Audit trail có thể phải giữ cả **đã xác nhận** và **đã hủy**.

### 4.3. Rollback command cũng có thể bị timeout

Nếu client gửi **abortTransaction()** rồi mất kết nối, không nên mặc định abort thành công. Trong một số giao thức, server có thể đã commit trước khi abort đến, hoặc một transaction đã kết thúc. Cần kiểm tra trạng thái bằng cơ chế engine/operation ID thay vì dựa trên thành công của socket close.

### 4.4. Atomicity không thay thế isolation

Hai transaction độc lập đều có thể atomic nhưng vẫn gặp lỗi nghiệp vụ khi cùng dựa trên một lần đọc không được bảo vệ:

~~~~text
Stock = 1
T1 đọc stock = 1
T2 đọc stock = 1
T1 tạo order
T2 tạo order
~~~~

Nếu không có **conditional update, optimistic concurrency, serializable transaction** hoặc cơ chế giữ hàng phù hợp, hệ có thể oversell dù từng thao tác ghi riêng lẻ đều atomic.

Vì vậy, khi thiết kế booking/payment, cần đặt hai câu hỏi khác nhau:

1. **Sau một lỗi mạng, ta xác định transaction đã commit chưa?**
2. **Ngay cả khi transaction commit đúng, nó có giữ bất biến khi có transaction đồng thời không?**

## 5. Các loại lỗi: loại nào được retry?

Không phải mọi ngoại lệ đều có cùng chiến lược.

| Loại kết quả | Ví dụ | Hành động |
| --- | --- | --- |
| **Known validation rejection** | Ngày check-out trước check-in | Không retry nguyên request; sửa dữ liệu |
| **Known conditional conflict** | Room slot đã được người khác giữ | Xử lý xung đột nghiệp vụ; không tạo đơn trùng |
| **Known transaction abort** | Giao dịch bị abort rõ ràng trước commit | Có thể retry toàn transaction sau khi kiểm tra điều kiện |
| **Unknown commit result** | Timeout sau khi gửi COMMIT | Retry **commit của cùng transaction** nếu driver/giao thức cho phép; hoặc reconcile operationId |
| **Unknown request result** | Mất kết nối khi Put/TransactWrite đã gửi | Retry với **cùng idempotency key**; đọc trạng thái từ nguồn |
| **Transient resource failure** | Throttling, leader failover, mạng ngắt | Retry có giới hạn, backoff, jitter, giữ operationId |
| **Permanent incompatibility** | Sai schema, kiểu dữ liệu, permission | Không retry vô hạn; cần sửa |
| **External provider timeout** | Payment capture timeout | Tra provider bằng merchant request ID/idempotency key; không charge mới bằng ID khác |

### 5.1. Retry commit khác retry toàn transaction

Sau khi **đã gửi COMMIT mà chưa biết kết quả**, một điều quan trọng là không được tự động **khởi tạo transaction mới** cho cùng một hành động mà không có idempotency.

Phân biệt:

~~~~text
Retry commit:
  Gửi lại quyết định COMMIT cho transaction identity cũ,
  nếu engine/driver hỗ trợ nhận diện cùng transaction.

Retry entire transaction:
  Chạy lại logic nghiệp vụ trong transaction mới,
  có thể thực hiện lại insert, decrement, phát sự kiện...
~~~~

**Retry commit** được một số giao thức thiết kế để an toàn dưới nhãn lỗi unknown commit; **retry toàn transaction** có thể gây tác dụng phụ trùng nếu lần đầu thực ra đã commit.

Ở mức ứng dụng, dù phải retry toàn request, hãy bảo đảm **operationId không đổi** và được xử lý nguyên tử/idempotent ở server.

### 5.2. Backoff và deadline không thay thế idempotency

Retry có thể theo exponential backoff có jitter:

~~~~text
Attempt 1: request timeout
Attempt 2: sau 100-200 ms
Attempt 3: sau 200-400 ms
Attempt 4: sau 400-800 ms
...
Stop sau tổng retry budget / deadline
~~~~

Khoảng chờ phải được lựa chọn theo SLO, throttling và tải thực tế. Backoff giúp giảm retry storm nhưng **không ngăn duplicate commit**. Việc dừng retry sau deadline chỉ có nghĩa client **ngừng cố gắng**, không phải transaction chắc chắn rollback.

## 6. Idempotency: cùng một ý định chỉ có một kết quả nghiệp vụ

**Idempotency** trong ngữ cảnh API tạo đơn nghĩa là các lần gửi lại **cùng một ý định nghiệp vụ** với cùng một khóa phải tạo **cùng một kết quả cuối** hoặc trả về trạng thái của kết quả đó, chứ không thực hiện tác dụng phụ mới mỗi lần.

Ví dụ:

~~~~http
POST /bookings
Idempotency-Key: 4f8b2d3a-6ec2-4b3f-a6d1-25e72b9c1048
Content-Type: application/json

{
  "roomId": "R-08",
  "checkIn": "2026-12-01",
  "checkOut": "2026-12-03"
}
~~~~

Nếu response lần đầu mất, client gửi lại **cùng key** và **cùng payload**:

~~~~http
POST /bookings
Idempotency-Key: 4f8b2d3a-6ec2-4b3f-a6d1-25e72b9c1048
Content-Type: application/json

{
  "roomId": "R-08",
  "checkIn": "2026-12-01",
  "checkOut": "2026-12-03"
}
~~~~

Server cần trả kết quả booking đã có, không tạo B-902.

### 6.1. Khóa idempotency phải gắn đúng phạm vi

Một hợp đồng tốt xác định:

- **Ai tạo key?** Client hoặc server theo flow; key được giữ qua restart/retry.
- **Phạm vi key:** theo tenant/customer và loại thao tác, ví dụ (tenantId, operationType, key).
- **Ràng buộc payload:** cùng key nhưng payload khác phải **bị từ chối** thay vì âm thầm trả kết quả cũ.
- **Độ dài thời gian giữ:** vượt qua retry window và khả năng request cũ đến muộn, theo rủi ro nghiệp vụ.
- **Mức bền vững:** ledger còn tồn tại sau failover/restore theo hợp đồng.
- **Thao tác thực thi nguyên tử:** key và tác dụng nghiệp vụ phải có hàng rào đúng đắn chống race.
- **Trạng thái chưa hoàn tất:** cần kế hoạch khôi phục thay vì giữ PENDING vô hạn.

Không dùng một idempotency key chung cho toàn bộ “đặt phòng” vì hai lần đặt phòng hợp lệ khác nhau phải có hai key khác nhau.

### 6.2. Cùng key nhưng payload khác là conflict

Ví dụ:

~~~~text
Key: OP-101
Payload lần 1: room R-08, 2026-12-01 -> 2026-12-03

Payload lần 2: room R-09, 2026-12-01 -> 2026-12-03
~~~~

Nếu server chỉ kiểm tra key tồn tại rồi trả booking cũ, user có thể hiểu nhầm lần đổi phòng đã thành công. Cần so khớp một **request fingerprint** có ngữ nghĩa.

Fingerprint có thể dựa trên các trường đã canonicalize của payload. Không hash raw JSON một cách ngẫu nhiên nếu thứ tự field hoặc định dạng timestamp/số có thể khác nhau nhưng cùng ý nghĩa.

### 6.3. Idempotency key không thay thế business unique constraint

Hai request **khác key** nhưng cùng giữ một phòng/slot vẫn phải được xử lý cạnh tranh đúng.

~~~~text
OP-101 -> reserve room R-08 at 2026-12-01
OP-102 -> reserve room R-08 at 2026-12-01
~~~~

Nếu chỉ chống lặp cùng key, cả hai có thể trở thành hai booking. Cần **unique key/conditional write** theo room+time slot hoặc cơ chế bất biến tương đương.

**Idempotency giải quyết “lặp cùng ý định”; concurrency control giải quyết “hai ý định tranh cùng tài nguyên”.**

## 7. Thiết kế operation ledger bền vững

Một mẫu phổ biến là lưu **bản ghi kết quả thao tác** trong nguồn có thẩm quyền.

Ví dụ:

~~~~json
{
  "tenantId": "hotel-42",
  "operationId": "OP-101",
  "operationType": "CREATE_BOOKING",
  "requestFingerprint": "sha256:...",
  "status": "COMMITTED",
  "bookingId": "B-901",
  "bookingVersion": 1,
  "resultCode": "BOOKING_CREATED",
  "createdAt": "2026-11-14T09:30:00Z"
}
~~~~

Mục tiêu là khi client quay lại, server có thể trả:

~~~~json
{
  "operationId": "OP-101",
  "status": "COMMITTED",
  "bookingId": "B-901"
}
~~~~

**Bản ghi ledger phải liên kết đáng tin với quyết định nghiệp vụ.** Nếu viết booking rồi mới viết ledger ở một thao tác độc lập, crash giữa hai bước có thể tạo **booking đã commit nhưng ledger không có**.

### 7.1. Nếu database hỗ trợ multi-item transaction

Trong cùng transaction:

~~~~text
BEGIN TRANSACTION

  1. Kiểm tra (tenantId, operationId) chưa được dùng
  2. Chặn xung đột giữ phòng / kiểm tra slot
  3. Ghi Booking B-901
  4. Ghi OperationResult OP-101 -> B-901, COMMITTED
  5. Ghi Outbox BookingCreated (nếu cần phát sự kiện)

COMMIT
~~~~

Sau commit, **booking, ledger và outbox** trở thành một đơn vị theo bảo đảm của transaction.

Nếu ACK commit mất, retry cùng key có thể tìm thấy ledger và trả booking B-901. Nếu hai request OP-101 đến đồng thời, **unique constraint/conditional transaction** chỉ được cho một thao tác thắng.

### 7.2. Trạng thái PENDING cần một ý nghĩa rõ

Trong một số flow kéo dài, ứng dụng có thể lưu:

~~~~text
OP-101: PENDING
  -> PREPARED
  -> COMMITTED
hoặc
  -> REJECTED
~~~~

Nếu PENDING được lưu **trước** khi thực hiện tác dụng nghiệp vụ, cần một workflow phục hồi:

- Bản PENDING có lease/owner và deadline hợp lý không?
- Khi owner chết, worker khác có thể claim bằng compare-and-set không?
- Làm sao biết tác dụng phụ đã xảy ra trước khi owner chết?
- Một worker chạy muộn có bị ngăn ghi sau khi worker mới đã tiếp quản không?
- Khi ledger kẹt, hệ trả UNKNOWN cho client hay tự tạo một booking khác?

Một **lease hết hạn** không chứng minh tác vụ chưa commit. Khi có worker cạnh tranh hoặc tác dụng phụ kéo dài, có thể cần **fencing token/generation** và kiểm tra version tại điểm ghi.

### 7.3. TTL của idempotency record là quyết định nghiệp vụ

Nếu idempotency key chỉ được giữ 1 giờ nhưng client có thể retry sau 24 giờ, cùng key có thể bị coi là mới và tạo booking khác.

Chọn retention bằng cách xem:
- Thời gian retry tối đa của client và job.
- Khả năng message/webhook bị phát lại sau nhiều ngày.
- Chính sách thanh toán/đặt chỗ và yêu cầu audit.
- Rủi ro dữ liệu cũ bị restore.
- Chi phí lưu ledger lâu dài.

Có những nghiệp vụ cần giữ **mã giao dịch bất biến lâu dài**, dù cache idempotency ngắn hạn đã hết. **Không tự dùng TTL 5 phút cho mọi giao dịch tài chính** vì cache của API thường chỉ tồn tại 5 phút.

## 8. Khi chỉ có atomic write một item

Nhiều NoSQL tối ưu atomicity trong phạm vi một item/document/partition, còn transaction rộng hơn có thể có giới hạn hoặc không được hỗ trợ.

Nếu có thể **đóng gói bất biến và operationId vào cùng thực thể**, một atomic conditional write có thể đủ:

~~~~json
{
  "slotKey": "ROOM#R-08#2026-12-01",
  "reservedByBookingId": "B-901",
  "lastOperationId": "OP-101",
  "version": 18
}
~~~~

Ý tưởng logic:

~~~~text
UPDATE slot S
IF slot S is available
THEN set reservedByBookingId = B-901,
         lastOperationId = OP-101,
         version = oldVersion + 1
~~~~

Nếu timeout, đọc slot theo **mức nhất quán phù hợp** và kiểm tra **lastOperationId**. Nếu cùng OP-101 đã là người giữ chỗ, có bằng chứng thao tác đã áp dụng. Nếu slot thuộc OP khác, ứng dụng cần xử lý xung đột.

Tuy nhiên, điều này có giới hạn:

- Nếu sau OP-101 đã có OP-102 hợp lệ cập nhật cùng item, một trường **lastOperationId** có thể đã bị ghi đè; không thể chứng minh mọi lịch sử chỉ từ trạng thái mới nhất.
- Nếu booking còn cần ghi vào collection khác, một atomic item update **không tự bao trùm** collection đó.
- Nếu nghiệp vụ cần lịch sử kiểm toán, có thể phải giữ **operation log riêng với ràng buộc nguyên tử tương ứng** hoặc chọn mô hình dữ liệu khác.

**Thiết kế schema theo ranh giới nguyên tử** là quyết định cốt lõi trong NoSQL, không chỉ là việc chọn khóa truy vấn nhanh.

## 9. Đọc lại sau timeout: có thể kết luận những gì?

Một chiến lược tự nhiên:

~~~~text
1. Gửi COMMIT hoặc conditional write.
2. Timeout.
3. GET trạng thái theo operationId.
4. Nếu thấy COMMITTED -> trả thành công.
5. Nếu thấy REJECTED -> trả từ chối.
6. Nếu không thấy -> ???
~~~~

**Bước 6 là chỗ dễ mắc lỗi.**

### 9.1. Nếu read path eventual consistent

Không thấy operation record **không chứng minh** chưa commit. Có thể source đã commit nhưng replica/GSI/search chưa được đồng bộ.

Ví dụ:

~~~~text
10:00:00.000  Primary commit OP-101
10:00:00.050  ACK bị mất
10:00:00.100  Client đọc GSI -> không thấy
10:00:01.000  GSI bắt kịp -> thấy COMMITTED
~~~~

Nếu tại 10:00:00.100 client tạo OP-102, hệ có thể sinh duplicate.

### 9.2. Nếu read path strongly consistent

Đọc nhất quán mạnh từ nguồn có thẩm quyền có thể xác nhận **một record đã commit** khi tìm thấy. Nhưng **không tìm thấy tại một thời điểm** vẫn cần xét:

- Commit của request cũ đã kết thúc hay còn in-flight?
- Có cùng unique key/conditional guard ngăn nó commit **sau** lần đọc?
- Transaction ledger có được ghi atomic với side effect không?
- Có coordinator/replica failover hoặc read routing nào phá kỳ vọng không?

Nếu hệ thống cho phép request cũ **đang chờ** và commit sau một read “không thấy”, lần đọc đó không bảo đảm ý định đã thất bại. Cách an toàn thường là **retry có cùng operationId dưới hàng rào unique/conditional**, thay vì tự sáng tạo operationId mới.

### 9.3. Định nghĩa endpoint trạng thái rõ ràng

Một API có thể cung cấp:

~~~~http
GET /operations/OP-101
~~~~

Phản hồi ví dụ:

~~~~json
{
  "operationId": "OP-101",
  "status": "COMMITTED",
  "resourceId": "B-901"
}
~~~~

Hoặc:

~~~~json
{
  "operationId": "OP-101",
  "status": "PENDING",
  "retryAfterSeconds": 2
}
~~~~

Nếu không có bản ghi và không thể loại trừ một request cũ đang thực thi, hệ cần thể hiện **UNKNOWN/NOT_YET_OBSERVED** theo hợp đồng thay vì suy diễn NOT_COMMITTED. Mã HTTP **404** đơn thuần có thể gây hiểu nhầm nếu không nói rõ ngữ nghĩa.

## 10. MongoDB: unknown commit result và retry transaction

MongoDB hỗ trợ transaction theo các điều kiện/giới hạn của sản phẩm và phiên bản. Khi dùng transaction qua driver, có hai nhãn lỗi nổi bật:

- **TransientTransactionError:** lỗi transient trong transaction có thể cho phép retry **toàn transaction** theo hướng dẫn driver, nếu phù hợp.
- **UnknownTransactionCommitResult:** sau khi gửi commit, client không thể xác định commit đã thành công hay chưa; cách xử lý điển hình là **retry commit của cùng transaction** theo cơ chế driver.

Các nhãn này có ngữ nghĩa riêng; không thể lấy một exception “timeout” chung rồi tùy tiện chọn retry toàn bộ logic.

### 10.1. Mẫu luồng với MongoDB Java driver (mã giả)

~~~~java
ClientSession session = mongoClient.startSession();

try {
    session.startTransaction(transactionOptions);

    // Các ghi phải dùng cùng session/transaction.
    insertBooking(session, booking);
    insertOperationResult(session, operationId, bookingId);
    insertOutbox(session, event);

    // Khi commit trả UNKNOWN, driver/app phải dùng
    // chiến lược retry commit cùng transaction.
    commitWithUnknownResultHandling(session);

} finally {
    session.close();
}
~~~~

Đoạn code trên là **mã khung**, các hàm chưa định nghĩa và không thể copy chạy trực tiếp. Nó minh họa ranh giới transaction và nguyên tắc rằng các operation phải tham gia **cùng session**.

Không nên viết:

~~~~java
try {
    commitTransaction();
} catch (SocketTimeoutException ex) {
    createNewBookingWithNewId(); // SAI: có thể duplicate
}
~~~~

Nếu driver hỗ trợ callback transaction có retry tự động, cần hiểu **những lỗi nào driver retry, retry commit hay retry body, timeout cuối cùng trả ra nhãn gì**, và tránh chạy tác dụng phụ ngoài database trong transaction callback.

### 10.2. Dùng transaction API đúng không có nghĩa “exactly once” cho external side effects

Không nên làm:

~~~~text
startTransaction
  insert booking
  charge payment provider qua HTTP
  insert outbox
commitTransaction
~~~~

Nếu transaction body bị retry, **charge provider có thể chạy lại**. Nếu transaction bị abort, provider cũng không tự rollback charge.

Thay vào đó, giao dịch database có thể ghi **booking intent/outbox**; worker thực hiện payment với provider idempotency key rồi cập nhật kết quả theo một workflow riêng.

### 10.3. Write concern/read concern phải được định nghĩa

Một transaction hoặc ghi được xác nhận phụ thuộc **write concern**, còn việc đọc kiểm chứng phụ thuộc **read concern và đường đọc**. Muốn phục hồi trạng thái sau failover, không nên mặc định cấu hình yếu nhất có cùng độ bền với majority/snapshot/linearizable mà sản phẩm hỗ trợ.

Đặc biệt, **timeout ở commit và rollback ở transaction là hai tình huống khác nhau**. Nếu đã gửi commit và có nhãn unknown, không nói “chắc chắn rollback” chỉ vì client không có kết quả.

## 11. DynamoDB: conditional write, transaction và ClientRequestToken

DynamoDB hỗ trợ những thao tác nguyên tử ở cấp item, conditional writes và **TransactWriteItems** cho nhóm item trong phạm vi giới hạn của dịch vụ.

Một mẫu cho tạo booking:

~~~~text
TransactWriteItems:
  Put Booking B-901
      condition: chưa tồn tại
  Put Operation OP-101
      condition: chưa tồn tại
  Update Slot R-08#2026-12-01
      condition: available = true
~~~~

Nếu toàn bộ điều kiện thỏa và transaction commit, các cập nhật thuộc giao dịch được áp dụng nguyên tử theo hợp đồng của DynamoDB. Nếu điều kiện không thỏa, transaction bị từ chối theo cơ chế transaction và ứng dụng phải phân biệt đó với timeout.

### 11.1. ClientRequestToken

API **TransactWriteItems** có thể nhận **ClientRequestToken** để hỗ trợ idempotency cho cùng yêu cầu trong **một khoảng thời gian giới hạn do dịch vụ định nghĩa**. Retry với token không đổi và tham số phù hợp tránh thực hiện lại như yêu cầu mới trong khoảng được hỗ trợ.

Nhưng:

- **Khoảng idempotency không kéo dài vĩnh viễn**.
- Tham số khác nhau với token cũ có thể tạo lỗi mismatch.
- Không nên xem token SDK là mã nghiệp vụ duy nhất cho toàn bộ đời sống booking/payment.
- Sau khi hết cửa sổ của dịch vụ, cần **operation ledger và unique/conditional guard** ở dữ liệu ứng dụng nếu cần chống lặp lâu dài.

### 11.2. GSI không phải nơi kết luận commit

Một item đã commit trên bảng chính có thể **chưa xuất hiện ở GSI** vì GSI được cập nhật bất đồng bộ. Để tra OP-101, ưu tiên dùng **key trực tiếp trên bảng có thẩm quyền** và mức đọc phù hợp, không chỉ query GSI rồi kết luận “chưa có”.

### 11.3. Transaction không tự bao trùm mọi dịch vụ khác

Một **TransactWriteItems** thành công không đồng nghĩa:
- Event đã được consumer xử lý.
- Search index đã mới.
- Payment provider đã thu tiền.
- Email đã gửi.
- Mọi bản sao xuyên vùng đều cung cấp cùng một instant read guarantee.

Các thành phần ngoài ranh giới transaction cần outbox, reconciliation và idempotency riêng.

## 12. Cassandra: CAS/LWT và ý nghĩa kết quả không xác định

Cassandra thường tối ưu mô hình phân tán theo partition và consistency level. Với những thao tác cần compare-and-set, có **lightweight transaction (LWT)** dựa trên cơ chế consensus theo phạm vi hỗ trợ, ví dụ CQL:

~~~~sql
INSERT INTO booking_slots (
    slot_key, booking_id, operation_id
) VALUES (
    'ROOM#R-08#2026-12-01', 'B-901', 'OP-101'
) IF NOT EXISTS;
~~~~

Nếu nhận kết quả **[applied] = true**, client có bằng chứng từ cơ chế LWT rằng thao tác conditional được chấp nhận theo hợp đồng và consistency đã chọn.

Nhưng nếu client **timeout trong khi coordinator đang xử lý**, có thể không biết cuối cùng điều kiện đã được áp dụng hay chưa. Gửi lại một lệnh tạo booking với ID mới mà không kiểm tra operationId sẽ nguy hiểm.

### 12.1. Lưu dấu idempotency ngay trong hàng được bảo vệ

Ví dụ item booking_slots chứa **operation_id** và **booking_id**. Sau timeout, đọc hàng này theo đường nhất quán phù hợp để nhận diện kết quả. Nếu thấy slot đã bị giữ bởi OP-101, không tạo booking mới chỉ vì lần trước mất ACK.

Cần thiết kế thêm khi một booking bao gồm **nhiều ngày/slot**, nhiều partition hoặc tác dụng ngoài Cassandra; một LWT một hàng không tự trở thành transaction đa partition, đa dịch vụ.

### 12.2. Logged batch không có nghĩa isolation ACID toàn cục

Các cơ chế **batch** trong Cassandra có ngữ nghĩa riêng về ghi, atomicity/logging và visibility. Không suy ra rằng một logged batch tự cung cấp **isolation serializable đa partition và rollback đa bước** như một relational transaction. Phải đọc đúng hợp đồng version/consistency, nhất là khi có conditional statement.

Nếu hệ thống cần giữ nhiều invariant xuyên nhiều partition, có thể phải đổi cách gom dữ liệu, dùng một điểm quyết định riêng hoặc một workflow nghiệp vụ phù hợp.

## 13. Redis: MULTI/EXEC là một trường hợp cần hiểu chính xác

Redis cung cấp **MULTI/EXEC** để xếp hàng và thực thi một chuỗi lệnh theo ngữ nghĩa transaction của Redis, và **WATCH** để kiểm tra thay đổi trước EXEC.

Ví dụ:

~~~~redis
WATCH booking:slot:R-08:2026-12-01
MULTI
SET booking:slot:R-08:2026-12-01 B-901
SET booking:op:OP-101 B-901
EXEC
~~~~

Đây chỉ là minh họa cú pháp, **chưa đủ bảo vệ** slot nếu không có logic đọc/kiểm tra điều kiện đúng và chính sách khóa, TTL, persistence phù hợp.

Các điểm quan trọng:

- **MULTI/EXEC không cung cấp rollback kiểu relational transaction cho các lệnh đã thực thi khi một lệnh trong EXEC gặp runtime error.**
- **WATCH** có thể làm transaction không thực thi nếu key được theo dõi đã thay đổi trước EXEC; ứng dụng cần xử lý trạng thái retry.
- **Timeout trong hoặc sau EXEC** vẫn có thể khiến client không biết lệnh đã chạy hay chưa.
- Độ bền sau crash/failover phụ thuộc cấu hình persistence/replication của Redis; atomic command execution không đồng nghĩa mọi ACK đều có durability như ledger tài chính.
- Một key lưu idempotency với TTL ngắn có thể biến mất trước khi client retry.

Ví dụ nên làm ở cấp một script/atomic operation phù hợp là **kiểm tra slot chưa được giữ và đặt slot cùng operation marker một cách nguyên tử**, thay vì tách GET và SET không điều kiện rồi hy vọng network không lỗi.

**Không dùng Redis làm nguồn duy nhất cho khoản thanh toán đã chốt nếu không chứng minh được độ bền, khôi phục và retention đúng yêu cầu nghiệp vụ.** Redis rất hữu ích cho cache, lock/coordination hay trạng thái tạm thời khi phù hợp.

## 14. Transaction của database không bao trùm payment, email và search

Một flow đặt phòng thường bao gồm:

~~~~mermaid
flowchart LR
    API["Booking API"] --> DB[("Booking DB")]
    DB --> OUT[("Outbox")]
    OUT --> WORK["Background worker"]
    WORK --> PAY["Payment provider"]
    WORK --> MAIL["Email provider"]
    WORK --> IDX[("Search / read model")]
~~~~

Chỉ transaction trong Booking DB không thể làm **HTTP charge**, **email send** và **update search index** cùng rollback như một đơn vị ACID.

### 14.1. Transactional outbox

Một mẫu an toàn:
1. Trong cùng transaction nguồn, ghi booking/operation ledger và một **outbox event**.
2. Commit source.
3. Relay phát sự kiện từ outbox sang broker hoặc consumer.
4. Consumer xử lý idempotent, ACK khi trạng thái cần thiết đã lưu đáng tin.
5. Retry/reconciliation xử lý những lần publish hoặc consume lỗi.

Ví dụ:

~~~~json
{
  "eventId": "evt-7b21",
  "operationId": "OP-101",
  "eventType": "BookingConfirmed",
  "bookingId": "B-901",
  "aggregateVersion": 1
}
~~~~

Nếu relay publish xong nhưng crash trước khi đánh dấu đã gửi, event có thể được phát **hai lần**. Consumer phải chống lặp bằng eventId/operationId và trạng thái đã áp dụng.

Outbox giảm lỗi **dual write** nhưng không tự bảo đảm sự kiện chỉ được giao đúng một lần.

### 14.2. Sự kiện trùng không được tạo side effect trùng

Một worker xử lý event BookingConfirmed có thể gửi email và cập nhật search:

~~~~text
Receive evt-7b21
  -> Check whether evt already applied
  -> Apply desired change idempotently
  -> Record completion durable
  -> ACK message
~~~~

Nhưng vẫn có khoảng trống khi gửi email bên ngoài và ghi completion ở database. Nếu worker crash sau email nhưng trước completion, lần retry có thể gửi lại.

Cách xử lý phụ thuộc provider:
- Dùng **idempotency key hỗ trợ bởi provider** khi có.
- Dùng outbox/delivery ledger với semantics rõ.
- Chấp nhận duplicate ở những side effect ít nguy hại và thiết kế phát hiện.
- Không tuyên bố **exactly once end-to-end** nếu không có hợp đồng từ provider.

### 14.3. Thanh toán là ví dụ nghiêm trọng

Flow sai:

~~~~text
POST /charge 100.000 VND
  -> Provider đã capture
  -> Network timeout
API retry bằng paymentId mới
  -> Provider capture thêm 100.000 VND
~~~~

Flow thích hợp hơn:
- Tạo **merchantPaymentOperationId** trước request.
- Gửi cùng key cho provider nếu API của họ hỗ trợ idempotency.
- Lưu trạng thái nguồn: PENDING, SUCCEEDED, FAILED hoặc UNKNOWN theo hợp đồng.
- Khi timeout, **query/reconcile** theo merchantPaymentOperationId hoặc provider reference.
- Không bắt đầu charge mới cho cùng ý định chỉ vì không thấy response.
- Nếu cần hoàn tiền, làm **refund transaction** riêng với ID và audit trail.

**Không lấy trạng thái một webhook đến muộn làm bằng chứng duy nhất** nếu có thể có event duplicate/out-of-order; đối soát với nguồn có thẩm quyền của provider và version/status.

## 15. Saga, compensation và trạng thái tạm thời

Nếu một hành động trải qua nhiều dịch vụ, dùng **saga/workflow** thay vì coi tất cả như transaction một database.

Ví dụ:

~~~~text
1. Reserve slot       (Booking)
2. Authorize payment  (Payment)
3. Confirm booking    (Booking)
4. Send notification  (Messaging)
~~~~

Nếu bước 2 thất bại sau khi bước 1 thành công, workflow có thể phát lệnh **ReleaseSlot**. Nếu bước 3 commit nhưng thông báo không gửi được, không nên hủy booking chỉ vì email thất bại; có thể retry thông báo.

### 15.1. Compensation không đảo ngược lịch sử

~~~~text
RESERVED -> CONFIRMED -> CANCELLED
~~~~

Mỗi chuyển trạng thái là sự kiện nghiệp vụ có thể có tác động riêng. Nếu đã charge, hoàn tiền là một giao dịch khác; đôi khi phải mất thời gian để provider xác nhận refund.

Do đó trạng thái flow có thể là:

~~~~text
BOOKING_PENDING_PAYMENT
PAYMENT_UNKNOWN
PAYMENT_SUCCEEDED
BOOKING_CONFIRMED
CANCELLATION_PENDING
REFUND_PENDING
BOOKING_CANCELLED
~~~~

Không được ánh xạ mọi trạng thái tạm thành **FAILED** vì app không chờ được lâu.

### 15.2. Saga cũng cần idempotency cho từng bước

Một orchestrator có thể crash giữa việc gửi command và lưu checkpoint. Khi khởi động lại, nó có thể gửi lại ReserveSlot hoặc AuthorizePayment. Mỗi participant cần:
- OperationId duy nhất theo bước.
- Chống lặp theo key.
- Guard state transition.
- Khả năng truy vấn trạng thái đã thực thi.
- Timeout/retry và escalation khi kết quả còn UNKNOWN.

Saga giải quyết luồng bù/điều phối, **không tự xóa bài toán ambiguous outcome**.

## 16. HTTP API contract khi không biết commit

Một API có thể phân biệt:

| Trường hợp | Phản hồi hợp lý có thể chọn | Ý nghĩa |
| --- | --- | --- |
| Booking commit và xác minh được | 201 Created hoặc 200 cho retry | Đã thành công |
| Request có cùng key và cùng payload đã thành công | 200/201 kèm cùng bookingId | Replay kết quả idempotent |
| Cùng key nhưng payload khác | 409 Conflict hoặc lỗi tương đương | Không chấp nhận đổi ý nghĩa key |
| Điều kiện giữ phòng không thỏa | 409 Conflict | Từ chối nghiệp vụ đã xác định |
| Đang xử lý dài hơn HTTP deadline, có tracking bền vững | 202 Accepted + operation status URL | Đã nhận xử lý; **không có nghĩa đã commit booking** |
| Không biết request đã commit hay chưa và không có status chắc chắn | 503/504 hoặc trạng thái UNKNOWN được mô tả rõ | Client không được suy ra rollback |

**HTTP status code không thay thế hợp đồng transaction.** Cách chọn 202/503/504 phụ thuộc việc server có thực sự nhận và theo dõi operation bền vững hay chưa. Không trả 202 Accepted rồi làm mất mọi dấu vết của operation khi restart.

Một response tốt khi chờ xử lý:

~~~~json
{
  "operationId": "OP-101",
  "status": "PENDING",
  "statusUrl": "/operations/OP-101"
}
~~~~

Sau khi đã biết kết quả:

~~~~json
{
  "operationId": "OP-101",
  "status": "COMMITTED",
  "bookingId": "B-901"
}
~~~~

Client nên lưu **operationId** bền vững trước khi gửi thao tác quan trọng. Nếu app mobile mất điện sau khi gửi nhưng trước khi nhận response, nó vẫn có ID để tra cứu khi khởi động lại.

## 17. Mã Java mẫu: biểu diễn kết quả rõ ràng

Đừng thiết kế service chỉ trả **boolean success** cho một hành động có thể ambiguous.

Một kiểu dữ liệu kết quả:

~~~~java
public enum OperationState {
    COMMITTED,
    REJECTED,
    PENDING,
    UNKNOWN
}

public record BookingResult(
        String operationId,
        OperationState state,
        String bookingId,
        String reason
) {}
~~~~

Một lớp phía client phải chuyển **timeout** thành UNKNOWN, không thành REJECTED:

~~~~java
public BookingResult submitBooking(
        String operationId,
        BookingCommand command
) {
    try {
        return bookingGateway.submit(operationId, command);
    } catch (TransportTimeoutException ex) {
        return new BookingResult(
                operationId,
                OperationState.UNKNOWN,
                null,
                "Commit outcome not observed"
        );
    }
}
~~~~

Các kiểu **BookingCommand**, **bookingGateway** và **TransportTimeoutException** là thành phần minh họa do ứng dụng định nghĩa. Đoạn code không biên dịch độc lập nếu chưa có các lớp và interface đó.

### 17.1. Vòng lặp xử lý UNKNOWN

Mã giả phía application:

~~~~text
processBookingIntent(intent):
    opId = persistedClientOperationId(intent)
    fingerprint = canonicalHash(intent)

    response = submit(opId, fingerprint, intent)

    if response == COMMITTED:
        return bookingId

    if response == REJECTED:
        return businessError

    if response in {PENDING, UNKNOWN}:
        for attempt in boundedRetryBudget:
            state = queryAuthoritativeOperation(opId)

            if state == COMMITTED:
                return bookingId

            if state == REJECTED:
                return businessError

            maybeRetrySameOperationIdWithBackoff()

        return "processing status unknown; use operationId to check later"
~~~~

**Không tạo opId mới ở mỗi lần retry.**

### 17.2. Retry ở tầng HTTP client có thể vô tình trùng

Ngoài code chính, các lớp proxy/load balancer, gateway, SDK và queue có thể có retry tự động. Cần biết:

- SDK có retry write nào khi timeout?
- HTTP reverse proxy có replay request khi upstream disconnect?
- Queue có at-least-once delivery?
- Mobile app có gửi lại khi người dùng nhấn nút lần nữa?
- Job scheduler có chạy lại task sau khi worker crash?

Idempotency nên được thực thi **tại nguồn nghiệp vụ**, không chỉ ở UI bằng cách disable nút “Đặt phòng”.

### 17.3. Tránh ghi log sai sự thật

Không ghi:

~~~~text
ERROR: Booking creation failed
~~~~

khi chỉ biết timeout. Nên ghi:

~~~~text
WARN: Booking commit outcome unknown
  operationId=OP-101
  requestFingerprint=...
  attempt=2
  timeoutMs=3000
  resolutionStatus=PENDING
~~~~

Không log raw payment token, mật khẩu, thông tin cá nhân hoặc toàn bộ card payload chỉ để debug.

## 18. Tính đúng khi có nhiều thao tác tranh nhau

### 18.1. Slot booking và conditional guard

Giả sử hai khách gửi:

~~~~text
OP-101 -> room R-08, 01/12
OP-102 -> room R-08, 01/12
~~~~

Hai operationId khác nhau là **hai ý định khác nhau**, không phải retry. Để không đặt trùng:

~~~~text
ReserveSlot(slotId, bookingId)
  condition: slot is available / version matches
~~~~

Một hệ giao dịch cần đảm bảo chỉ một trong hai thao tác có thể giữ slot theo hợp đồng atomicity/isolation đã chọn. Sau một timeout ở OP-101, server phải tra trạng thái OP-101, không chọn OP-102 hoặc chờ search index cập nhật rồi quyết định.

### 18.2. Sử dụng deterministic ID có giúp không?

Nếu bookingId được suy ra bền vững từ operationId hoặc client cung cấp một ID cố định, retry có thể cố ghi cùng ID và gặp unique constraint thay vì tạo hai ID khác nhau. Điều đó **giúp** chống lặp.

Nhưng cần thận trọng:

- ID không thể chỉ là hash công khai dễ đoán nếu có ràng buộc bảo mật.
- Không được để người dùng đổi payload dưới cùng ID mà ghi đè booking cũ.
- ID cố định không giải quyết cạnh tranh **hai operation khác nhau cùng slot**.
- Tác dụng phụ ngoài DB vẫn cần idempotency riêng.

### 18.3. “Exactly once” phải có phạm vi

Thông điệp có thể được giao nhiều lần, transaction có thể commit một lần, handler có thể chạy lại. Ta có thể xây **effectively-once business effect** bằng operationId, unique constraint và atomic ledger, nhưng không nên tuyên bố “toàn hệ exactly once” nếu payment, email, search và broker có các giao thức khác nhau.

Một câu tuyên bố tốt hơn:

> Với mỗi cặp (tenantId, operationId), Booking Store chỉ có tối đa một kết quả booking đã commit; các lần retry cùng request fingerprint trả lại kết quả đó trong thời hạn retention đã công bố.

Đây là **bất biến cụ thể, kiểm thử được**, không phải khẩu hiệu.

## 19. Durability và replication: ACK có thể bảo vệ tới đâu?

Một transaction đã ACK theo cấu hình yếu có thể có rủi ro mất khi leader crash trước khi dữ liệu được nhân bản/bền vững theo những kịch bản sự cố mà cấu hình đó **không bảo đảm**.

Một số câu hỏi phải trả lời trước khi khẳng định “commit bền”:

1. ACK của write có yêu cầu log flush hoặc fsync không?
2. Có bao nhiêu replica xác nhận trước khi ACK?
3. Ghi đã đạt commit theo quorum/majority nào?
4. Khi failover, leader mới có thể thiếu write nào?
5. Có phân biệt **durability trên một vùng** và **sao chép đa vùng**?
6. Có bảo đảm linearizable read sau write trong cấu hình đã chọn không?
7. Transaction có được ghi atomically cùng idempotency ledger và outbox không?

Không có một câu trả lời chung cho toàn bộ NoSQL.

### 19.1. Client ACK và “business confirmed” là hai tầng

Một hệ có thể chia:
- **Database committed:** booking record đã commit theo durability contract.
- **Business confirmed:** slot đã được giữ hợp lệ, payment state đáp ứng điều kiện, mọi bước workflow bắt buộc đã hoàn tất.

Nếu nghiệp vụ yêu cầu payment trước khi xác nhận, một database commit trạng thái **PENDING_PAYMENT** không có nghĩa nên hiển thị **CONFIRMED**. Đừng dùng một cờ “committed” để thay thế toàn bộ workflow.

### 19.2. Khi khôi phục từ backup

Restore từ snapshot cũ có thể làm thiếu ledger hoặc booking vừa commit sau mốc backup. Nếu bên ngoài đã charge hoặc gửi email, cần đối soát qua operationId và provider reference.

**RPO/RTO, dữ liệu được ACK và khả năng tái dựng ledger** phải được thiết kế cùng nhau. Idempotency key chỉ hữu ích khi hệ có thể khôi phục hoặc đối chiếu lịch sử của key qua sự cố được giả định.

## 20. Khi nào “không thấy dữ liệu” mới có ý nghĩa?

Xem hai trường hợp.

**Trường hợp A — Không có hàng rào:**

~~~~text
Request R1 sent -> timeout
Strong read at t1 sees no booking
R1 still processing and commits at t2 > t1
~~~~

Đọc không thấy ở t1 không kết luận R1 sẽ không bao giờ commit. Nếu tạo R2 với key khác, có nguy cơ duplicate.

**Trường hợp B — Có unique/conditional guard:**

~~~~text
Request R1 with operationId OP-101 -> timeout
Client retries same OP-101
DB guarantees only one successful insert for OP-101
~~~~

Dù R1/R2 thực thi chồng lấp, unique constraint/conditional write cho cùng khóa khiến chúng không thể tạo hai booking **nếu thao tác lưu ledger và booking được thiết kế nguyên tử đúng**.

Vì vậy, câu trả lời cho unknown outcome thường không phải “hãy đọc một lần” mà là:

> **Dùng định danh ổn định + hàng rào chống lặp + khả năng truy hồi kết quả + đọc theo mức nhất quán phù hợp.**

## 21. Fault injection: kiểm thử mất kết nối tại mọi ranh giới

Không thể kiểm chứng xử lý UNKNOWN chỉ bằng unit test luồng success. Cần chủ động tạo lỗi tại những thời điểm khác nhau.

### 21.1. Ma trận sự cố

| Vị trí sự cố | Cách tạo trong môi trường thử | Bất biến phải giữ |
| --- | --- | --- |
| Trước khi DB nhận request | Chặn mạng trước khi gửi | Không phát sinh booking |
| Sau khi DB nhận, trước commit | Kill/abort transaction có kiểm soát | Không thấy partial state |
| Sau commit, trước ACK | Làm mất phản hồi commit | Retry cùng operationId không duplicate |
| Sau ACK, trước client ghi state | Crash client process | Restart tra lại được operationId |
| Trong lúc commit, trạng thái chưa rõ | Leader failover hoặc timeout | Không tự báo reject; có reconciliation |
| Client retry đồng thời | Hai thread gọi cùng key | Tối đa một kết quả nghiệp vụ |
| Cùng key, payload khác | Gửi fingerprint khác | Từ chối xung đột, không sửa kết quả cũ |
| Hai key tranh cùng slot | Gửi hai request song song | Tối đa một holder cho slot |
| Ledger write và booking write | Crash giữa các lệnh nếu không có transaction | Lộ điểm không nguyên tử; sửa thiết kế |
| Broker giao event trùng | Publish cùng event nhiều lần | Không charge/increment hai lần |
| Provider capture xong, HTTP timeout | Giả lập provider unknown | Không capture lại với key mới |
| Replica đọc chậm | Đọc qua replica/GSI lag | Không coi absence là rollback |
| Idempotency key hết TTL | Retry sau cửa sổ retention | Chính sách xử lý rõ, không duplicate ngoài ý muốn |
| Restore backup cũ | Phục hồi từ snapshot và reconcile | Tìm lại những effect đã commit/charge |
| Worker lease hết | Worker cũ trở lại khi worker mới chạy | Fencing/conditional transitions bảo vệ state |

### 21.2. Test phải kiểm tra trạng thái cuối, không chỉ HTTP

Một test đúng nên kiểm tra:
- Số bản ghi booking theo operationId và theo room/slot.
- Số lần inventory thực sự bị trừ.
- Số bản ghi ledger, event/outbox và phiên bản.
- Số lần provider capture/refund theo merchant reference.
- Trạng thái sau failover/restore.
- Response của lần retry **có cùng bookingId**.
- Không còn operation UNKNOWN/PENDING vĩnh viễn nếu có cơ chế recovery.
- Có cảnh báo nếu sau deadline vẫn không thể kết luận.

Nếu chỉ assert “API trả 504” thì chưa kiểm tra được gì về transaction outcome.

### 21.3. Java unit test giả lập outcome unknown

Một bộ test có thể dựng fake store:

~~~~java
// Pseudocode:
fakeStore.commitOperation("OP-101", "B-901");
fakeNetwork.dropCommitAck();

BookingResult first = service.create("OP-101", request);
assert first.state() == UNKNOWN;

// Sau đó client gửi lại cùng ý định:
BookingResult second = service.create("OP-101", request);
assert second.bookingId().equals("B-901");

assert fakeStore.countBookingsForOperation("OP-101") == 1;
~~~~

Đây là **mã giả test**, không phải JUnit chạy độc lập. Cần test tích hợp với **database/driver thật** vì semantics của transaction, replica và timeout không thể giả lập chính xác chỉ bằng fake object.

## 22. Observability cho kết quả chưa xác định

Một hệ tốt không chỉ retry mà còn **biết bao nhiêu thao tác đang UNKNOWN và bao lâu thì giải quyết được**.

| Metric | Ý nghĩa | Hành động |
| --- | --- | --- |
| **unknown_outcome_total** | Số thao tác mất kết quả cuối | Điều tra mạng, commit latency, failover |
| **unknown_age_p95/p99** | Thời gian để biết kết quả | Kiểm tra reconciliation/ledger |
| **unresolved_operations** | Số operation đang chờ | Cảnh báo và chạy repair |
| **oldest_unresolved_age** | Tuổi operation lâu nhất chưa kết luận | Escalate nếu vượt deadline |
| **idempotency_replay_total** | Số lần retry cùng key được nhận diện | Đánh giá retry layer |
| **fingerprint_conflict_total** | Cùng key với payload khác | Phát hiện lỗi client/tấn công |
| **duplicate_effect_prevented_total** | Số duplicate bị hàng rào chặn | Quan sát hiệu quả idempotency |
| **conditional_conflict_total** | Business conflict thực | Phân biệt với lỗi mạng |
| **transaction_commit_latency** | Độ trễ commit | Tìm saturation/storage issue |
| **payment_reconciliation_lag** | Chậm xác định charge/refund | Báo rủi ro tài chính |
| **outbox_pending_age** | Thay đổi commit nhưng event chưa phát | Điều tra relay/consumer |
| **ledger_source_mismatch** | Booking có nhưng operation ledger không khớp | Lỗi nghiêm trọng về tính nguyên tử |

Metrics cần gắn **operationId và traceId** nhưng tránh lưu thông tin cá nhân hoặc payment credentials trong log/metric labels có cardinality quá cao.

### 22.1. Tracing qua nhiều tầng

Một trace có thể gồm:

~~~~text
clientRequestId  = REQ-77
operationId      = OP-101
bookingId        = B-901
dbTransactionId  = txn-...
paymentReference = PAY-554
outboxEventId    = evt-7b21
~~~~

Các ID có vai trò khác nhau:
- **requestId** phân biệt mỗi HTTP attempt.
- **operationId** gắn nhiều request với **cùng ý định**.
- **transactionId** thuộc một lần thực thi DB transaction cụ thể.
- **paymentReference** dùng để đối soát provider.
- **eventId** phục vụ dedup consumer.

**Không dùng requestId mỗi attempt như idempotency key** nếu requestId luôn được tạo mới cho mỗi retry.

## 23. Runbook: API timeout sau khi gửi commit

Khi vận hành nhận một ticket “khách thấy lỗi nhưng có thể bị trừ tiền/đặt phòng”, không tự chạy lại toàn bộ nghiệp vụ.

### Bước 1 — Xác định operation

Thu thập:
- OperationId/idempotency key và tenant.
- Fingerprint của yêu cầu đã gửi.
- Khoảng thời gian request/timeout.
- Mức write concern và transaction settings.
- Provider reference nếu có thanh toán.
- TraceId cho request đầu và các lần retry.

### Bước 2 — Tra nguồn có thẩm quyền

Kiểm tra:
- Ledger có **COMMITTED/REJECTED/PENDING** không?
- Booking có ghi operationId tương ứng không?
- Conditional guard room/slot đang thuộc booking nào?
- Outbox có event cùng transaction không?
- Ghi có được ACK/commit theo mức durability cấu hình không?

Đừng chỉ tìm trong search index, cache hoặc GSI eventual rồi coi không có.

### Bước 3 — Nếu UNKNOWN, không tự tạo operation mới

- Retry/tra cứu **cùng operationId** trong giới hạn an toàn.
- Nếu driver hỗ trợ retry **commit cùng transaction**, dùng đúng cơ chế.
- Nếu transaction identity không còn để retry, dùng **idempotency ledger + conditional write**.
- Với provider ngoài hệ, query bằng merchant reference và dùng chính sách retry idempotent của họ.
- Nếu chưa thể kết luận, giữ trạng thái UNKNOWN và thông báo rõ cho UI/support.

### Bước 4 — Xử lý stuck PENDING

- Xác định owner/lease/generation và nguồn trạng thái thật.
- Dùng compare-and-set để claim recovery job nếu cần.
- Trước khi chạy lại side effect, kiểm tra **có thể đã xảy ra** không.
- Đối soát tất cả bước bắt buộc của saga.
- Đưa trường hợp không thể tự kết luận tới quy trình xử lý thủ công có audit.

### Bước 5 — Chốt và ngăn tái diễn

- Lưu kết quả cuối cùng cùng operationId.
- Bảo đảm UI/support đọc được trạng thái đúng.
- Kiểm tra duplicate booking/charge/notification đã xảy ra trước đó.
- Điều tra nguyên nhân timeout: network, failover, long commit, throttling, storage I/O hoặc client deadline.
- Bổ sung fault injection/metric và sửa retry policy nếu cần.

## 24. Những nhầm lẫn phổ biến

1. **“Timeout nghĩa là transaction rollback.”** Không; commit có thể đã xảy ra và ACK bị mất.
2. **“Không thấy trong search nghĩa là chưa commit.”** Search/GSI có thể trễ.
3. **“Gửi lại request với ID mới là retry.”** Đó có thể là một **ý định mới** đối với server.
4. **“Có idempotency key trong header là đủ.”** Key cần được lưu/kiểm tra bằng hàng rào có tính nguyên tử với kết quả nghiệp vụ.
5. **“Đã rollback database thì payment cũng rollback.”** Không; provider ngoài DB cần workflow/compensation.
6. **“Mọi exception đều retry toàn transaction.”** Phải phân biệt abort chắc chắn với unknown commit.
7. **“Retry commit và retry transaction body là một.”** Không; side effect có thể chạy lại.
8. **“Một atomic write bảo vệ được 10 tài liệu ở service khác.”** Chỉ trong phạm vi atomicity đã công bố.
9. **“ACK luôn có độ bền như nhau.”** Write concern, fsync và replication thay đổi bảo đảm.
10. **“Một strong read không thấy là chứng minh request cũ không còn có thể commit.”** Không nếu request vẫn in-flight và thiếu guard.
11. **“Redis MULTI/EXEC rollback mọi runtime error.”** Không có rollback kiểu relational cho lệnh đã thực thi.
12. **“DynamoDB ClientRequestToken chống trùng vĩnh viễn.”** Có cửa sổ idempotency giới hạn.
13. **“Cassandra logged batch là transaction serializable toàn cục.”** Không được suy diễn vậy.
14. **“Retry có exponential backoff sẽ không duplicate.”** Backoff giảm tải, không thay idempotency.
15. **“Client biết commit rồi thì đã hoàn tất nghiệp vụ.”** Có thể còn payment/search/email hoặc bước saga.
16. **“PENDING quá lâu cứ xóa rồi tạo lại.”** Có thể khiến side effect trùng; cần reconciliation.
17. **“Exactly once là thuộc tính mặc định của broker + DB.”** Phải định nghĩa phạm vi effect và chứng minh hợp đồng.
18. **“Một khóa idempotency có thể dùng cho mọi giao dịch.”** Hai ý định hợp lệ phải có key khác nhau.
19. **“Ghi booking rồi ghi ledger sau cũng ổn.”** Crash giữa hai bước phá khả năng tra cứu.
20. **“404 từ endpoint trạng thái luôn là NOT_COMMITTED.”** Chỉ đúng khi API có thể loại trừ request in-flight và bảo đảm nguồn tra cứu.

## 25. Bài tập thực hành: booking mất kết nối và thanh toán

Một ứng dụng đặt phòng dùng Java 21 và NoSQL có:

- 5.000 yêu cầu đặt phòng/giây vào giờ cao điểm.
- Mỗi phòng/slot chỉ được có **một booking CONFIRMED**.
- Client tạo và giữ **operationId** qua các lần retry.
- Booking Store có conditional write; môi trường cũng hỗ trợ một cơ chế multi-item transaction trong phạm vi được khai báo.
- Search index hiển thị phòng còn trống bất đồng bộ.
- Payment provider hỗ trợ một merchant idempotency key, nhưng có thể timeout sau khi capture.
- API deadline 3 giây; một số commit có thể kéo dài hơn do failover.
- Consumer outbox có thể được giao event trùng.
- UI phải tránh báo thành công hoặc thất bại sai khi kết quả còn UNKNOWN.

### Phần A — Phân biệt kết quả

Với ba timeline:

~~~~text
A. Request không tới server, client timeout.
B. Source commit booking, commit ACK bị mất.
C. Transaction bị reject do slot đã được giữ, rejection response bị mất.
~~~~

Nêu client **quan sát được gì**, trạng thái **thật có thể là gì**, và vì sao không thể phân biệt A/B/C chỉ bằng một timeout. Ở bước nào có thể kết luận COMMITTED hoặc REJECTED?

### Phần B — Thiết kế operation ledger

Đề xuất schema cho:
- **Booking**: bookingId, roomId, dateRange/slot, status, version, operationId.
- **OperationResult**: tenantId, operationId, requestFingerprint, state, bookingId, timestamps.
- **RoomSlot**: slotKey, holderBookingId, version.
- **OutboxEvent**: eventId, operationId, aggregateId, aggregateVersion, eventType.

Chọn một transaction/conditional design để bảo vệ **cùng key chỉ có một booking** và **mỗi slot chỉ có một holder**, ngay cả khi hai request đồng thời đến. Nêu rõ phần nào thật sự nằm trong cùng ranh giới atomicity.

### Phần C — Client retry

Client gửi OP-101 rồi timeout. Hãy mô tả thuật toán:
1. Giữ nguyên OP-101 và fingerprint.
2. Tra kết quả theo nguồn có thẩm quyền.
3. Nếu chưa có bằng chứng, retry cùng OP-101 với backoff và bounded deadline.
4. Khi chưa thể kết luận, hiển thị trạng thái nào?
5. Làm gì khi app được mở lại một ngày sau?

Giải thích vì sao sinh OP-102 khi OP-101 timeout là nguy hiểm.

### Phần D — Commit và rollback

Giả sử Booking Store đã commit, Payment provider trả timeout, và search chưa thấy booking. Phân biệt:
- Transaction nào đã commit?
- Payment có thể đã capture chưa?
- Có thể rollback booking vừa commit như một transaction chưa từng xảy ra không?
- Khi nào phải tạo compensation/cancellation/refund?
- Search stale có được phép quyết định slot còn trống để ghi không?

### Phần E — Tạo sự cố và kiểm chứng

Đề xuất test:
1. Drop ACK sau database commit.
2. Failover giữa transaction và ACK.
3. Gửi OP-101 hai lần đồng thời.
4. Gửi cùng key với payload khác.
5. Gửi hai key khác nhau cho cùng slot.
6. Timeout payment sau capture.
7. Duplicate outbox event.
8. Operation ledger PENDING bị bỏ lại sau worker crash.
9. Đọc qua replica/search cập nhật chậm.
10. Retry sau khi bản ghi idempotency hết TTL.

Với mỗi test, nêu **bất biến**, phương pháp xác minh, metric cần theo dõi và hành động khi outcome chưa rõ.

### Phần F — Trả lời tình huống vận hành

Khách báo: “Ứng dụng hiện lỗi mạng, nhưng ngân hàng đã ghi nhận khoản tiền.” Bạn có **operationId và merchantPaymentReference**. Hãy lập runbook để biết booking đã commit, provider đã capture thật hay chỉ authorization, có cần refund hay không, và tránh charge lần nữa.

### Hướng giải

Điểm quyết định giữ phòng phải dùng **conditional/transactional write ở nguồn**, không dựa vào search index. OperationId cùng request fingerprint phải được lưu hoặc bảo vệ bằng **unique/conditional guard**, tốt nhất nguyên tử cùng booking và outbox trong phạm vi hỗ trợ. Timeout giữ **UNKNOWN**, sau đó dùng đọc đáng tin và retry **cùng operationId**. Payment cần idempotency/reconciliation riêng; email/search dùng outbox và consumer idempotent. Khi muốn hủy một booking đã commit, cần **thao tác bù được audit**, không giả định rollback được lịch sử.

**Kết luận:** Trong NoSQL, commit và rollback chỉ có ý nghĩa trong **ranh giới transaction, durability và isolation cụ thể**. Mất kết nối có thể làm client không biết kết quả dù database đã quyết định xong; vì thế **timeout không được chuyển thành rollback hoặc success bằng suy đoán**. Một hệ đúng đắn phải kết hợp **operationId bền vững, idempotency/conditional guard, tra cứu kết quả tại nguồn, retry theo loại lỗi, outbox, compensation và quan sát UNKNOWN**. Thiết kế phải cho phép hệ thống phục hồi sau mất ACK mà **không tạo hai tác dụng nghiệp vụ từ một ý định duy nhất**.
