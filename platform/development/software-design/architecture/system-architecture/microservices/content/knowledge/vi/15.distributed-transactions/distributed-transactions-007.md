# Đặt chỗ tài nguyên, hết hạn và xác nhận cuối cùng

> **Chủ đề:** Software Design Architecture → System Architecture → Microservices  
> **Nhóm kiến thức:** Giao dịch phân tán  
> **Bối cảnh:** Inventory, ghế vé, slot đặt lịch, quota khuyến mại và các nguồn tài nguyên hữu hạn được giữ tạm thời qua nhiều service.

## 1. Mục tiêu học tập

Sau bài học, người đọc có thể:

- Phân biệt reservation/hold với khóa database, lease, commit, release, cancel và compensation.
- Giải thích vì sao phân bổ tài nguyên hữu hạn cần bước đặt chỗ tạm khi checkout/thanh toán kéo dài nhiều request và nhiều service.
- Thiết kế trạng thái ACTIVE, CONFIRMED, RELEASED, EXPIRED; xác định điều kiện chuyển trạng thái và trạng thái terminal.
- Bảo vệ invariant không bán vượt năng lực bằng transaction, conditional UPDATE, uniqueness, version/row lock và idempotency.
- Xử lý cuộc đua giữa confirm và expiry, callback thanh toán đến muộn, retry cùng operation, message trùng và service restart.
- Xác định nguồn thời gian chính thức, expiresAt, TTL, gia hạn, chính sách dọn reservation và độ trễ cleanup.
- Đặt reserve/confirm/cancel vào workflow Saga hoặc TCC có quyền sở hữu nghiệp vụ, không đánh đồng với 2PC ACID.
- Dùng transactional outbox, stateful coordinator, retry có giới hạn và reconciliation để tiến về kết quả cuối dù transport timeout.
- Đề xuất API/Java/Spring Boot, các phép thử race/fault injection, metrics và runbook vận hành phù hợp.

## 2. Tình huống: chỉ còn một ghế cuối cùng

Nền tảng bán vé chỉ còn ghế S-12. Khách A và khách B đồng thời bắt đầu thanh toán:

~~~text
Khách A                    Khách B
  |                          |
  +----- yêu cầu S-12 -------+
             |
             v
        Checkout / Order
             |
             v
        Seat Service
        capacity(S-12)=1
~~~

Nếu ứng dụng chỉ kiểm tra available=true rồi đưa cả hai khách qua cổng thanh toán, hai khách có thể đều trả tiền trước khi hệ thống phát hiện chỉ còn một ghế. Nếu giữ khóa database suốt quá trình người dùng nhập thẻ, giao dịch sẽ kéo dài và gây nghẽn. Nếu lưu “giữ chỗ” vào Map trong RAM của một replica, replica khác không thấy; restart có thể làm mất quyền giữ.

Giải pháp phổ biến là tạo một **business reservation có thời hạn**:

~~~text
1. Seat Service kiểm tra và giữ ghế atomically.
2. Trả reservationId, expiresAt, state=ACTIVE.
3. Khách tiến hành bước thanh toán/xác minh.
4. Khi đủ điều kiện, coordinator gửi Confirm.
5. Seat Service xác nhận nếu reservation còn ACTIVE và chưa hết hạn.
6. Nếu khách bỏ dở hoặc thời hạn qua, service chuyển EXPIRED và release ghế.
7. Nếu kết quả thanh toán mơ hồ, service đối soát thay vì tự suy đoán.
~~~

**Điểm then chốt:** reservation là một thực thể nghiệp vụ bền vững, có trạng thái và thời hạn; nó không phải một transaction database bị mở suốt thời gian khách checkout.

### 2.1. Những bài toán tương tự

- Giữ ba đơn vị SKU trong 10 phút.
- Đặt phòng, slot tư vấn hoặc lịch khám.
- Giữ quota voucher trong một cửa sổ khuyến mãi.
- Giữ đơn vị GPU/CPU cho workload sẽ khởi chạy.
- Authorization hold từ cổng thanh toán trước capture; tuy nhiên semantics của tiền khác giữ kho và phải tuân thủ contract nhà cung cấp.

Các loại reservation có thể khác TTL, giới hạn gia hạn, rủi ro tài chính và điều kiện confirm. Không nên dùng một policy chung cho mọi resource nếu nghiệp vụ khác nhau.

## 3. Bộ khái niệm cần tách bạch

| Khái niệm | Ý nghĩa | Thời gian sống/đặc tính |
| --- | --- | --- |
| **Reservation/hold** | Quyền tạm phân bổ tài nguyên cho một logical operation | Seconds/minutes/hours, có reservation record và expiresAt |
| **Database row lock** | Ngăn transaction khác sửa cùng bản ghi trong thời gian giao dịch | Thường ngắn; giải phóng khi commit/rollback |
| **Lease** | Quyền sử dụng trong một khoảng thời gian, có thể gia hạn | Cần owner, deadline, đôi khi fencing token |
| **Confirm/commit nghiệp vụ** | Chuyển quyền tạm thành phân bổ cuối | Theo invariant của domain owner |
| **Release** | Trả tài nguyên chưa được confirm về available pool | Có thể là hiệu ứng của cancel/expire |
| **Expire** | Mất quyền sử dụng/confirm khi quá deadline | Không phụ thuộc việc worker quét đã chạy chưa |
| **Compensate** | Tạo hành động bù trừ cho side effect đã hoàn tất ở service khác | Có thể phát sinh refund, void, cancel allocation |
| **Reconcile** | Tra/đối chiếu dữ liệu thực tế khi các service bất đồng hoặc outcome chưa rõ | Có thể tự động hoặc cần can thiệp |

### 3.1. Không nhầm giao dịch database với reservation dài phút

Một local database transaction đủ ngắn để giữ capacity và INSERT reservation. Sau commit, mọi request tiếp theo dựa vào reservationId và state đã lưu. Không giữ row lock, connection hoặc transaction mở chờ người dùng thanh toán.

### 3.2. Một số loại giữ chỗ phải có luật riêng

Giữ ghế độc quyền có invariant: một seat chỉ có tối đa một owner đã xác nhận. Giữ 3 SKU trong kho có invariant số lượng: held + allocated không vượt capacity. Giữ một slot GPU có thể đi kèm generation/fencing và preemption. Authorization hold của Payment có kỳ hạn/khả năng void do bên xử lý tiền quyết định.

**Reservation chỉ là khung tư duy; điều kiện nghiệp vụ phải viết rõ cho từng owner.**

## 4. Ai sở hữu reservation?

Một service sở hữu resource phải là nơi quyết định **có thể giữ bao nhiêu và ai được xác nhận**.

| Resource | Data owner | Invariant |
| --- | --- | --- |
| SKU/stock | Inventory Service | Không allocate vượt lượng tồn cho phép |
| Seat | Ticket/Seat Service | Không bán cùng một ghế cho hai order |
| Delivery slot | Delivery Capacity Service | Không book vượt số lượt giao |
| Voucher quota | Promotion Service | Không cấp voucher vượt campaign budget |
| Hotel room/time | Booking Service | Không bán trùng phòng/đêm nếu độc quyền |
| Payment authorization | Payment Service/provider | Không authorize/capture trùng logical payment |

Order Service có thể điều phối checkout, nhưng không trực tiếp chỉnh bảng stock của Inventory khi Inventory là owner. Từng resource owner phải có transaction/constraints của riêng mình.

~~~text
Client
  |
  v
Order Service / Saga Coordinator
  |---- Reserve(resource, quantity) ----> Inventory Owner
  |---- Authorize(payment) -------------> Payment Owner
  |---- Confirm(reservationId) ---------> Inventory Owner
  |---- Mark Order Final locally -------> Order Database
  +---- Publish domain events ----------> Fulfillment
~~~

Không có transaction ACID xuyên toàn bộ sơ đồ theo mặc định. Đó là lý do coordinator cần trạng thái, idempotency và bù trừ.

### 4.1. Correlation IDs

~~~text
orderId       = ord-101
sagaId        = saga-101
reservationId = res-772
paymentOpId   = pay-op-901
reserveKey    = ord-101-reserve-v1
confirmKey    = ord-101-confirm-v1
~~~

Các ID có ý nghĩa khác nhau. Reservation owner tạo reservationId; Order giữ sagaId; Payment có operation ID riêng. Không dùng một chuỗi vô nghĩa cho tất cả scope. Không dùng correlation ID làm bằng chứng authorization.

## 5. Mô hình dữ liệu một reservation

Một bản ghi tối thiểu:

~~~text
reservationId
resourceId
resourceType
tenantId
ownerOrderId
quantity
state
createdAt
expiresAt
updatedAt
confirmedAt?
releasedAt?
version
reserveIdempotencyKey
confirmOperationId?
reason?
~~~

Tùy nghiệp vụ, cần giá đã được chốt, sales channel, warehouse, resource variant và correlation metadata. Không lưu dữ liệu nhạy cảm không cần thiết. Cần retention/audit cho terminal records đủ lâu để xử lý retry muộn và reconciliation.

### 5.1. Một record không thể đại diện toàn bộ workflow

Reservation thuộc Inventory không phải bản sao đầy đủ Payment hoặc Order. Nếu Payment thành công nhưng Inventory EXPIRED, mỗi service vẫn giữ lịch sử riêng; Order/Saga tổng hợp và quyết định compensation.

### 5.2. Resource ID không phải mã hiển thị

Một SKU biến thể, seatId và productId có thể khác nhau. Không tự đoán “productId = inventorySku”. API Reserve cần nhận ID do owner công bố hoặc có bước mapping hợp lệ, cùng kiểm tra tenant/warehouse khi cần.

## 6. State machine và trạng thái cuối

~~~text
                   request
                      |
                      v
                +-----------+
                |  RESERVE  |
                +-----+-----+
                 /         \
         no capacity      granted
              |             |
              v             v
           REJECTED        ACTIVE
                           / | \
                    confirm |  \ cancel
                      |     |   \
                      v     v    v
                 CONFIRMED EXPIRED RELEASED
~~~

ACTIVE là trạng thái giữ chỗ đã được lưu. CONFIRMED, EXPIRED, RELEASED thường là **terminal states của reservation**. Sau khi CONFIRMED, nghiệp vụ muốn trả hàng/hủy vé là workflow cancel/refund khác; không âm thầm đổi CONFIRMED trở lại ACTIVE.

### 6.1. Bảng chuyển trạng thái

| State cũ | Lệnh | Điều kiện | State mới | Hiệu ứng |
| --- | --- | --- | --- | --- |
| Không có | Reserve | Còn capacity, key hợp lệ | ACTIVE | Tăng held |
| Không có | Reserve | Hết capacity | REJECTED/error | Không giữ |
| ACTIVE | Confirm | Còn hạn, đúng operation/owner | CONFIRMED | Held → Allocated |
| ACTIVE | Release | Có quyền, chưa terminal | RELEASED | Giảm held |
| ACTIVE | Expire | Deadline đã đến | EXPIRED | Giảm held |
| ACTIVE | Extend | Còn hạn, có quyền, chưa vượt policy | ACTIVE | Tăng expiresAt/version |
| CONFIRMED | Confirm lặp | Cùng logical operation | CONFIRMED | Trả kết quả đã lưu, không ghi lặp |
| EXPIRED | Confirm | Bất kể callback muộn | EXPIRED | Không được cấp lại resource cũ |
| RELEASED | Confirm | Đã giải phóng | RELEASED | Không được xác nhận |
| CONFIRMED | Release | Tùy contract | Thường cần cancel workflow | Không đơn giản giảm held |

### 6.2. Một transition terminal phải thắng

Nếu Confirm và Expire đều thấy ACTIVE, chỉ một được chuyển sang terminal và cập nhật capacity. Phải bảo vệ tại local transaction/data owner, không ở application memory. Nếu event được giao trùng, terminal transition không xảy ra lần hai.

### 6.3. Trạng thái trung gian

Một số workflow cần CONFIRMING hoặc PROCESSING khi việc confirm liên quan một tác vụ không hoàn tất ngay. Khi đó contract phải nêu:

- Ai là owner của trạng thái trung gian?
- Deadline của trạng thái trung gian có giống expiresAt không?
- Nếu process crash, ai nhận lại operation?
- Caller nhận 202 hay một kết quả terminal?
- Điều kiện gì cho phép hủy/khôi phục?

Tránh trạng thái trung gian không có tiến trình recovery, khiến giữ chỗ tồn tại vô hạn.

## 7. Invariant không cấp phát vượt capacity

Lấy resource dạng số lượng:

~~~text
totalCapacity
heldCount
allocatedCount

available = totalCapacity - heldCount - allocatedCount

heldCount >= 0
allocatedCount >= 0
heldCount + allocatedCount <= totalCapacity
~~~

Khi Reserve quantity=q: heldCount += q. Khi Confirm: heldCount -= q; allocatedCount += q. Khi Expire/Release: heldCount -= q. Chỉ một transition được áp dụng cho mỗi reservation; confirm lặp không tăng allocatedCount lần hai.

### 7.1. Ví dụ capacity=2

~~~text
T0: total=2, held=0, allocated=0, available=2

A Reserve 1:
    held=1, allocated=0, available=1

B Reserve 1:
    held=2, allocated=0, available=0

C Reserve 1:
    rejected

A Confirm:
    held=1, allocated=1, available=0

B Expire:
    held=0, allocated=1, available=1
~~~

Một request C có thể thử lại sau khi B được release. Không thể coi resource đã sẵn ngay khi đồng hồ client hiển thị 0 nếu state transition chưa được thực hiện một cách nhất quán.

### 7.2. Race đọc–ghi không điều kiện

~~~text
A đọc available=1
B đọc available=1
A INSERT reservation ACTIVE q=1
B INSERT reservation ACTIVE q=1
=> oversell
~~~

Cả hai request có thể xảy ra trên các replicas khác nhau. Cần atomic conditional write, row lock/version hoặc constraint tại owner datastore.

### 7.3. SQL minh họa

~~~sql
CREATE TABLE resource_capacity (
  resource_id VARCHAR(80) PRIMARY KEY,
  total_capacity BIGINT NOT NULL,
  held_count BIGINT NOT NULL DEFAULT 0,
  allocated_count BIGINT NOT NULL DEFAULT 0,
  CHECK (total_capacity >= 0),
  CHECK (held_count >= 0),
  CHECK (allocated_count >= 0),
  CHECK (held_count + allocated_count <= total_capacity)
);
~~~

Conditional UPDATE:

~~~sql
UPDATE resource_capacity
SET held_count = held_count + :qty
WHERE resource_id = :resource_id
  AND :qty > 0
  AND total_capacity - held_count - allocated_count >= :qty;
~~~

Nếu affectedRows=1, nguồn dữ liệu cho phép hold. Nếu affectedRows=0, service kiểm tra thiếu resource, không đủ capacity hoặc input không hợp lệ theo contract. **UPDATE capacity và INSERT reservation phải trong cùng transaction**.

### 7.4. Bảng reservation

~~~sql
CREATE TABLE reservations (
  reservation_id VARCHAR(80) PRIMARY KEY,
  tenant_id VARCHAR(80) NOT NULL,
  idempotency_key VARCHAR(160) NOT NULL,
  owner_operation_id VARCHAR(80) NOT NULL,
  resource_id VARCHAR(80) NOT NULL,
  quantity BIGINT NOT NULL,
  state VARCHAR(24) NOT NULL,
  expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
  created_at TIMESTAMP WITH TIME ZONE NOT NULL,
  updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
  version BIGINT NOT NULL DEFAULT 0,
  CHECK (quantity > 0),
  UNIQUE (tenant_id, idempotency_key)
);
~~~

Đây là schema minh họa; syntax/transaction isolation và index thực tế tùy database. Cần index (state, expires_at), policy audit/retention và cơ chế kiểm uniqueness của idempotency key cả khi request đồng thời.

## 8. Atomicity giữa reservation và counters

Phản mẫu:

~~~text
Transaction 1:
  UPDATE state ACTIVE → CONFIRMED
  COMMIT
Process crash
Transaction 2:
  UPDATE held--, allocated++
  chưa xảy ra
~~~

Kết quả state và counters lệch. Thiết kế đơn giản nhất là cùng local transaction:

~~~text
BEGIN
  lock reservation row
  verify current state, expiry, owner
  update reservation state
  update capacity counters
  insert outbox event
COMMIT
~~~

Khi nhiều resource rows cùng được khóa, tuân theo thứ tự ổn định (ví dụ resourceId tăng dần) để giảm deadlock. Nếu transaction deadlock hoặc rollback, retry với cùng logical operation ID và giới hạn phù hợp.

### 8.1. Có thể dùng optimistic concurrency

Ví dụ chuyển ACTIVE → CONFIRMED:

~~~sql
UPDATE reservations
SET state = 'CONFIRMED',
    version = version + 1
WHERE reservation_id = :id
  AND state = 'ACTIVE'
  AND version = :expected_version
  AND expires_at > CURRENT_TIMESTAMP;
~~~

Nếu affectedRows=0, không được suy ngay là expiry; reservation có thể đã CONFIRMED bởi retry khác, đã RELEASED, hoặc version khác. Cần đọc lại outcome. Việc chuyển counters cũng phải atomic với state transition.

### 8.2. Row lock và thời gian

Có thể dùng SELECT ... FOR UPDATE rồi đọc CURRENT_TIMESTAMP/database clock trong transaction. Cần chọn chính xác thời điểm so sánh thời gian; một số database định nghĩa CURRENT_TIMESTAMP tại đầu transaction, số khác có biến thể lấy giờ tại statement. Nếu yêu cầu chặt về deadline, kiểm semantics thực tế của database và triển khai.

### 8.3. Unique seat thay cho counter

Với ghế độc quyền, có thể dùng constraint ngăn hai booking CONFIRMED cùng seat, hoặc một bản ghi seat state/version được cập nhật có điều kiện. Không phải mọi resource cần held_count; chọn mô hình dễ chứng minh invariant nhất.

## 9. Thời gian hết hạn là quy tắc nghiệp vụ

~~~text
createdAt = 09:00:00 UTC
expiresAt = 09:10:00 UTC
TTL = 10 phút
~~~

Contract cần trả lời:

- Confirm được phép khi serverNow < expiresAt, hay <=?
- Nếu request tới lúc 09:09:59 nhưng transaction tới bước commit sau 09:10, ai thắng?
- Expiry worker chạy muộn có làm reservation còn hợp lệ không?
- Client có quyền yêu cầu TTL riêng không? Giới hạn bao nhiêu?
- Có thể gia hạn hay không và tối đa mấy lần?
- Nếu có nhiều resources với TTL khác nhau, toàn checkout phải theo deadline nào?

Một chính sách nhất quán có thể là **chỉ chuyển ACTIVE → CONFIRMED khi nguồn thời gian được owner xác nhận là trước expiresAt tại thời điểm kiểm tra transition**. Nếu hết hạn, không được hồi sinh quyền giữ cũ khi callback thanh toán tới muộn.

### 9.1. Server clock là authority

Không tin timestamp do browser/mobile cung cấp để quyết định quyền giữ. Tránh mỗi JVM tự quyết khác nhau do clock skew. Có thể dùng database time authority trong local transaction, đồng bộ NTP và ghi UTC timestamp cho audit.

Monotonic clock phù hợp đo duration trong một process; giá trị monotonic của hai process không tự so sánh xuyên máy. expiresAt lưu bền phải có format/timezone và precision rõ.

### 9.2. Cleanup lag

Expiry worker chỉ chạy mỗi 30 giây thì R có thể vượt expiresAt 20 giây trước khi bị đánh dấu EXPIRED. Quyền confirm **đã hết theo contract**, dù heldCount chưa giảm. Đây là tình trạng capacity bị giữ dư tạm thời, không phải lý do được phép xác nhận muộn.

Nếu cần trả lại resource nhanh, có thể quét thường hơn, làm cleanup opportunistic trên đường Reserve hoặc dùng deadline jobs; vẫn phải giữ invariant và atomic state transition.

### 9.3. Không đánh đồng Redis TTL với business expire

Một Redis key tự biến mất không bảo đảm transaction đồng thời giảm heldCount ở PostgreSQL. Eviction/failure cũng khác expiry nghiệp vụ. Để dùng Redis làm owner, cần atomic scripts/transactions, persistence, failure/replication semantics, audit và reconciliation phù hợp. Với mô hình cần chống oversell và chứng cứ terminal, lưu reservation trong database owner thường dễ lý giải hơn.

## 10. Race Confirm–Expire

Ví dụ:

~~~text
Reservation R ACTIVE, expiresAt=10:00:00

09:59:59.900  Confirm worker nhận lệnh
10:00:00.010  Expiry worker tìm thấy R quá hạn
10:00:00.030  Hai worker tranh cập nhật R
~~~

Hai worker không được mỗi người quyết định từ snapshot riêng rồi ghi đè. Nếu Confirm thắng trước deadline theo rule, R → CONFIRMED. Nếu Expire thắng hoặc deadline không còn hợp lệ, R → EXPIRED. **Chỉ một terminal transition được commit**, counters khớp terminal state.

### 10.1. Pseudocode transaction

~~~text
BEGIN
SELECT reservation FOR UPDATE

if state == CONFIRMED and same operation:
    return already confirmed

if state != ACTIVE:
    return state-specific conflict

dbNow = authoritative clock

if dbNow >= expiresAt:
    state = EXPIRED
    heldCount -= quantity
    write outbox ReservationExpired
    COMMIT
    return expired outcome

state = CONFIRMED
heldCount -= quantity
allocatedCount += quantity
write outbox ReservationConfirmed
COMMIT
return confirmed outcome
~~~

Trong implementation thật, các nhánh phải thực hiện transaction và mapping lỗi đúng. Không ném unchecked exception trước khi commit ở nhánh đã cập nhật EXPIRED nếu Spring transaction policy sẽ rollback.

### 10.2. Race Release–Expire

Khi người dùng cancel cùng lúc sweeper expire, cả hai muốn giảm heldCount. Chỉ một transition ACTIVE → RELEASED/EXPIRED thành công. Lệnh còn lại đọc terminal state, không giảm lần hai.

### 10.3. Race Confirm–Confirm

Hai retry từ cùng operation qua hai replicas phải cho một allocation effect. Một transaction chuyển state; request sau nhận kết quả cũ theo idempotency policy. Nếu confirm từ một order khác, phải từ chối.

### 10.4. Race Extend–Expire

Nếu renew đến sau deadline, không gia hạn. Khi cả hai cạnh tranh, check state/time/version tại owner. Không phụ thuộc countdown hiển thị trên client.

## 11. Gia hạn reservation có giới hạn

Ví dụ người dùng phải qua 3-D Secure, xác minh danh tính hoặc quá trình checkout đặc biệt.

Một API Extend/Renew nên có:

- Owner/principal có quyền.
- State vẫn ACTIVE và chưa hết hạn.
- Số lần gia hạn và maximum lifetime.
- Rule tính expiresAt mới, không vượt maxDeadline.
- Version/idempotency để xử lý hai renew đồng thời.
- Audit reason (3DS, manual approval, support intervention).
- Thông báo expiresAt mới cho client.

TTL quá dài khóa tài nguyên dù khách đã bỏ dở; TTL quá ngắn làm payment thành công nhưng confirmation fail. Chính sách nên dựa trên thời gian checkout thực tế, tỷ lệ abandoned và mức khan hiếm tài nguyên.

### 11.1. Không gia hạn vô hạn từ client

Không cho client tự gửi expiresAt rất xa hoặc mỗi request GET vô tình kéo dài phiên giữ. Nếu tự động gia hạn, phải có hạn mức và dấu hiệu người dùng thực sự còn tham gia quy trình.

### 11.2. Gia hạn một group

Một checkout giữ Inventory, Delivery Slot và Promotion quota có TTL khác nhau. Gia hạn Inventory không tự gia hạn voucher. Coordinator cần theo dõi **deadline sớm nhất của các holds bắt buộc** hoặc dùng một chính sách orchestration rõ.

## 12. Idempotency cho Reserve, Confirm và Release

Trong hệ thống phân tán, request có thể gửi lại vì:

- Client mất kết nối.
- Gateway/SDK retry có kiểm soát.
- Broker giao message ít nhất một lần.
- Worker restart trước khi ack.
- Caller nhận timeout dù state đã commit.

Idempotency key/operation ID phải giúp provider nhận ra **cùng một logical action**.

### 12.1. Reserve API

~~~http
POST /v1/reservations
Idempotency-Key: ord-101-reserve-v1
Content-Type: application/json

{
  "operationId": "ord-101",
  "resourceId": "sku-88",
  "quantity": 2
}
~~~

~~~http
HTTP/1.1 201 Created
Location: /v1/reservations/res-772
Content-Type: application/json

{
  "reservationId": "res-772",
  "state": "ACTIVE",
  "quantity": 2,
  "expiresAt": "2026-11-11T09:10:00Z"
}
~~~

Nếu hai request cùng key đến đồng thời, unique constraint/transaction phải chặn việc tạo hai holds. Khi key tồn tại:

- Same logical payload: trả record/kết quả hợp lệ theo contract.
- Different payload: 409 conflict.
- Key đã hết thời gian retention: rule xử lý retry muộn phải rõ để không tạo một hold trùng bất ngờ.

### 12.2. Confirm API

~~~http
POST /v1/reservations/res-772/confirm
Idempotency-Key: ord-101-confirm-v1
Content-Type: application/json

{
  "orderId": "ord-101"
}
~~~

Nếu confirm đã thành công từ cùng operation, request lặp trả terminal outcome chứ không tăng allocatedCount. Nếu reservation đã EXPIRED, trả conflict/expired; không coi lệnh retry là lý do phục hồi R.

### 12.3. Release API

~~~http
POST /v1/reservations/res-772/release
Idempotency-Key: ord-101-release-v1
~~~

Release lặp không giảm heldCount hai lần. Nếu đã CONFIRMED, endpoint có thể từ chối và hướng dẫn cancel allocation workflow khác. Nếu đã EXPIRED, có thể trả kết quả “đã không còn giữ” theo contract nhưng giữ nguyên trạng thái terminal/audit.

### 12.4. Idempotency scope

Cần xác định tenant + operation type + key, payload fingerprint, trạng thái IN_PROGRESS/COMPLETED, transaction uniqueness và retention. Không dựa vào header đơn thuần; phải thực thi tại owner.

## 13. Sơ đồ Saga/TCC: Reserve → Payment → Confirm

~~~text
Order Coordinator        Inventory Owner          Payment Owner
        |                       |                        |
        |---- Reserve --------->|                        |
        |<--- R ACTIVE ---------|                        |
        |                                                |
        |---------------- Authorize --------------------->|
        |<-------------- AUTHORIZED/UNKNOWN --------------|
        |                       |                        |
        |---- Confirm --------->|                        |
        |<--- CONFIRMED --------|                        |
        |                                                |
        |---- Update Order COMPLETED locally             |
        +---- Publish domain events                      |
~~~

Đây là thứ tự minh họa, không phải workflow đúng cho mọi payment provider. Trong thực tế có thể authorize trước, reserve trước, capture sau hoặc kết hợp các bước. Mỗi thứ tự có failure window và compensation riêng.

### 13.1. TCC và Saga khác 2PC database

Try/Reserve đặt quyền tạm; Confirm chuyển sang cuối; Cancel giải phóng. Nó giống phong cách **Try–Confirm–Cancel (TCC)**. Đây là business protocol với local transactions, không mặc nhiên là hai-phase commit ACID trên toàn bộ các database.

Saga có thể bao gồm những service không hỗ trợ chuẩn TCC: Payment authorize/void/capture/refund, Inventory reserve/confirm/release, Order state transitions. Coordinator cần mô hình hóa từng capability.

### 13.2. Trường hợp Payment FAILED

~~~text
Inventory R ACTIVE
Payment Authorize FAILED
Coordinator:
  Order -> PAYMENT_FAILED
  Release R with same logical release operation
  On Release timeout: query state/retry idempotently
~~~

Không tuyên bố reservation đã được release chỉ vì đã gửi command. Nếu release không thể thực hiện, expiry worker và reconciliation sẽ cần xử lý.

### 13.3. Trường hợp Payment thành công nhưng Confirm không được

Có thể Payment đã AUTHORIZED hoặc CAPTURED, nhưng Inventory R đã EXPIRED và capacity được cấp cho R2.

**Không được confirm R cũ bằng cách bỏ qua expiry.** Các tùy chọn tùy nghiệp vụ:

- Void authorization nếu chưa capture.
- Refund nếu đã capture và chính sách yêu cầu.
- Tạo reservation mới nếu còn capacity, chỉ sau khi đã có quyết định nghiệp vụ/chấp thuận phù hợp.
- Đưa Order sang COMPENSATION_PENDING/RECONCILIATION nếu outcome chưa rõ.
- Thông báo đúng trạng thái cho người dùng; không hứa đã có hàng/ghế khi không có confirm.

### 13.4. Không có thứ tự thần kỳ tránh hết lỗi

Capture trước Confirm gây nguy cơ “đã thu tiền nhưng hết hàng”. Confirm trước Capture gây nguy cơ “đã phân bổ nhưng không thu tiền”. Saga cần bước bù trừ, state machine và recovery cho cả hai đường.

## 14. Timeout chưa chắc là thất bại

~~~text
Order ---- Confirm(R) ----> Inventory
                            |
                            +-- COMMIT state=CONFIRMED
                            |
                            X response mất
Order thấy timeout
~~~

Order không biết chắc Confirm đã fail. Nếu gửi lệnh Reserve mới hoặc tự gắn EXPIRED, có thể sai. Cần:

1. Lưu operation ID trước khi gửi.
2. Query reservation status sau timeout.
3. Retry với **cùng** confirm operation key nếu trạng thái chưa xác định và còn hợp lệ.
4. Kiểm terminal outcome theo Inventory source of truth.
5. Đối soát Payment/Order để hoàn tất workflow.

### 14.1. Payment timeout tương tự nhưng nguy hiểm hơn

Gateway thanh toán có thể đã charge/authorize tiền trước khi response mất. Không được tạo payment mới bằng key mới chỉ để “thử lại”. Tra cứu operation/webhook/provider statement hoặc quy trình đối soát.

### 14.2. Những trạng thái Order có thể cần

~~~text
WAITING_RESERVATION
WAITING_PAYMENT
PAYMENT_OUTCOME_UNKNOWN
WAITING_CONFIRMATION
CONFIRM_OUTCOME_UNKNOWN
COMPLETED
EXPIRED_NEEDS_RECONCILIATION
COMPENSATION_PENDING
CANCELLED_FINAL
FAILED_FINAL
~~~

Tên trạng thái chỉ minh họa. Quan trọng là có chỗ lưu **UNKNOWN** và một next action để worker recovery, không ép mọi timeout thành FAILED.

## 15. Eventual consistency và transactional outbox

Một tình huống:

~~~text
Inventory transaction:
  R ACTIVE → CONFIRMED
  COMMIT

Process crash before sending ReservationConfirmed event.
~~~

Nếu Order chỉ chờ broker event, nó có thể treo dù Inventory đã confirm. Dùng **transactional outbox**:

~~~text
Local Inventory DB transaction
  +-- update reservation state
  +-- update capacity counters
  +-- insert outbox event
              |
             COMMIT
              |
Outbox relay → Message Broker → Order consumer
                                     |
                                dedupe/check version
~~~

State change và ý định phát event nằm cùng local transaction. Relay có thể gửi event nhiều lần nếu crash sau publish nhưng trước mark-sent, vì vậy consumer vẫn phải idempotent.

### 15.1. Event envelope

~~~json
{
  "eventId": "evt-555",
  "eventType": "ReservationConfirmed",
  "reservationId": "res-772",
  "orderId": "ord-101",
  "resourceId": "sku-88",
  "quantity": 2,
  "aggregateVersion": 3,
  "occurredAt": "2026-11-11T09:04:20Z"
}
~~~

Event không phải nguồn sự thật duy nhất; owner DB giữ record terminal. Khi nhận event bất đồng thứ tự, consumer có thể dùng aggregateVersion và trạng thái của mình, hoặc query owner để làm rõ.

### 15.2. Out-of-order message

ReservationCreated v1, ReservationExtended v2, ReservationConfirmed v3 có thể đến consumer không đúng thứ tự tùy broker/retry/replay. Không cho sự kiện Created v1 đến muộn ghi đè state Confirmed v3. Không dựa hoàn toàn vào “last message wins”.

### 15.3. Exactly once ở mức hiệu ứng

Broker delivery nhiều khi chỉ bảo đảm at-least-once trong một phạm vi; hiệu ứng nghiệp vụ “chỉ phân bổ một lần” phải được bảo vệ bằng state transition, unique constraints/idempotency. Không suy ra một hệ thống toàn cục exactly-once chỉ từ việc dùng outbox.

## 16. Expiry worker và cleanup

Worker quét reservation ACTIVE có expiresAt <= now:

~~~text
Every interval:
  scan bounded batch ACTIVE + overdue
  claim/lock records
  transition ACTIVE → EXPIRED atomically
  decrease heldCount
  insert outbox ReservationExpired
  commit
~~~

### 16.1. Hai workers không được release hai lần

Nếu A và B cùng chọn R, chỉ một worker được thực hiện transition. Có thể dùng row lock, SELECT FOR UPDATE SKIP LOCKED (nếu DB hỗ trợ), conditional UPDATE hoặc queue lease/fencing phù hợp. Local synchronized không bảo vệ xuyên replicas.

### 16.2. Cleanup theo batch

Cần index trên state/expiresAt, batch size giới hạn, transaction ngắn, tránh long-running table locks. Theo dõi backlog và thời gian trễ. Với hotspot lớn, cần partition/sharding/worker coordination phù hợp.

### 16.3. Opportunistic expire

Khi Reserve mới tìm thấy resource bị giữ bởi overdue reservations, owner có thể dọn expired records trước admission check trong cùng quy tắc transaction. Cách này cải thiện khả dụng nhưng phải tránh full scan/lock quá nhiều và vẫn bảo toàn invariant.

### 16.4. Retention

Không nên xóa toàn bộ bản ghi ngay khi hết hạn nếu cần đối soát payment hoặc trả lời retry muộn. Có thể lưu terminal record theo retention rồi archive/delete có kiểm soát.

## 17. Fencing token và tác vụ cũ tới muộn

Với tài nguyên như GPU lease hoặc độc quyền xử lý job, có tình huống:

~~~text
Worker A giữ lease epoch=41.
A bị pause lâu.
Lease hết hạn.
Worker B được cấp lease epoch=42 và bắt đầu xử lý.
A tỉnh dậy, gửi write với epoch=41.
~~~

Nếu storage/resource chỉ tin rằng A *từng* có lease, lệnh cũ có thể ghi đè B. **Fencing token tăng đơn điệu** cho mỗi lần cấp quyền và receiver kiểm token là một cách chặn.

~~~text
receiver has accepted epoch=42
write(epoch=41) → rejected
~~~

Một TTL key hết hạn không tự ngăn worker cũ làm side effect ở downstream. Fencing phải được kiểm tại nơi tiếp nhận write. Với giữ ghế, điều tương đương là reservationId/version/state terminal; confirm cũ không được phép thắng reservation mới.

## 18. Nhiều resource trong cùng checkout

Một order có thể cần:

~~~text
Order O
  ├─ Inventory reservation R1 (TTL 10m)
  ├─ Delivery slot reservation R2 (TTL 6m)
  └─ Promotion reservation R3 (TTL 8m)
~~~

Coordinator phải biết deadline của từng hold và điều kiện toàn cục. Nếu cần confirm cả ba, deadline sớm nhất có thể là 6 phút, trừ khi có cơ chế renew được công bố.

### 18.1. Partial reserve failure

Inventory thành công, Delivery slot thất bại. Coordinator phải release R1 (và R3 nếu đã giữ). Nếu release timeout, query state/retry idempotently. Không trả “checkout failed and all resources returned” khi chưa có bằng chứng.

### 18.2. Deadlock ở mức business hold

~~~text
Order A giữ X, chờ Y
Order B giữ Y, chờ X
~~~

Có thể đặt thứ tự cố định để reserve, dùng TTL giới hạn, fail fast, hoặc atomic multi-resource hold nếu cùng owner. Không cố giữ DB locks xuyên Saga.

### 18.3. Reservation group

Nếu một owner Inventory giữ nhiều SKUs, có thể tạo group reservation và line items trong một DB transaction, nếu datastore hỗ trợ. Nếu các line nằm ở nhiều warehouses/owners độc lập, cần workflow và compensation; không gọi đó là atomic global reserve khi không có cơ sở.

## 19. Bảo mật và chống lạm dụng giữ chỗ

Reservation có thể bị khai thác để làm cạn inventory mà không mua:

- Script tạo hàng nghìn holds để người khác không mua được.
- Caller tự gửi ownerId/tenantId để giữ hoặc confirm của người khác.
- Client tăng TTL thành vài giờ.
- Bot liên tục Extend để giữ tài nguyên vô hạn.
- Đoán reservationId và truy vấn trạng thái người dùng khác.
- Retry không kiểm payload dẫn tới giữ chỗ mới khi key cũ đã hết retention.

Cơ chế phòng vệ tùy sản phẩm:

- AuthN/AuthZ và kiểm owner resource.
- Rate limit/quota theo tenant/principal; chống bot khi cần.
- Max active holds/account, max quantity, max TTL và renew count.
- Idempotency scope và unique constraint.
- Input validation, TLS, service identity/mTLS khi phù hợp.
- Không tin thời gian/giá/owner do client tự khai.
- Logs/traces không chứa token/cookie hoặc PII không cần thiết.
- Theo dõi abuse signals, nhưng không tạo false positives loại bỏ khách hợp lệ.

## 20. API contract minh họa

| Method / route | Ý nghĩa |
| --- | --- |
| POST /v1/reservations | Tạo reservation với idempotency key |
| GET /v1/reservations/{id} | Đọc state/expiresAt theo authorization |
| POST /v1/reservations/{id}/confirm | Xác nhận hold còn hiệu lực |
| POST /v1/reservations/{id}/release | Trả tài nguyên chưa xác nhận |
| POST /v1/reservations/{id}/extend | Gia hạn có giới hạn |
| GET /v1/operations/{id} | Tra kết quả thao tác chưa rõ |

### 20.1. Những mã HTTP thường được cân nhắc

| Tình huống | Trả về có thể dùng | Chú ý |
| --- | --- | --- |
| Reserve tạo thành công | 201 Created | Trả reservationId, expiresAt |
| Confirm thành công | 200 OK | Trả terminal CONFIRMED |
| Confirm xử lý async | 202 Accepted | Chưa có kết quả cuối, phải poll |
| Không đủ capacity | 409 Conflict | Không tạo hold |
| Reservation expired | 409 hoặc 410 theo contract | Không confirm lại R cũ |
| Key trùng payload khác | 409 Conflict | Bảo vệ idempotency |
| Không có quyền | 403/404 theo security policy | Tránh leak resource |
| Too many reservations | 429 Too Many Requests | Quota/rate limit |
| Dependency unavailable | 503 hoặc domain code | Không suy outcome chắc chắn |
| Gateway timeout | 504 tại gateway | Mutation có thể đã commit |

Không có một HTTP mapping bắt buộc cho mọi sản phẩm; phải ghi rõ semantics, business error code và retry policy.

### 20.2. 202 không phải thành công cuối

~~~http
HTTP/1.1 202 Accepted
Location: /v1/operations/op-909
Content-Type: application/json

{"operationId":"op-909","state":"PROCESSING"}
~~~

Client không nên phát vé/hiển thị “mua thành công” chỉ vì nhận 202. Phải chờ terminal outcome theo contract.

## 21. Java/Spring Boot: ví dụ local transaction

Ví dụ dưới đây là pseudo-Java chú trọng kiến trúc; tên repository/exception được lược giản, cần bổ sung imports/validation/security/error handling khi triển khai.

~~~java
public record ReserveRequest(
    String resourceId,
    long quantity,
    String orderId
) {}

public record ReservationView(
    String id,
    String state,
    Instant expiresAt
) {}
~~~

### 21.1. Reserve trong transaction

~~~java
@Transactional
public ReservationView reserve(
        String tenantId,
        String key,
        ReserveRequest input) {

    // Kiểm tra idempotency key đã dùng hay chưa.
    // Nếu cùng key + payload, trả logical result cũ.
    // Nếu cùng key + payload khác, conflict.
    // Kiểm authorization và quantity > 0.

    int changed = jdbc.update(
        """
        UPDATE resource_capacity
           SET held_count = held_count + ?
         WHERE resource_id = ?
           AND total_capacity - held_count - allocated_count >= ?
        """,
        input.quantity(),
        input.resourceId(),
        input.quantity());

    if (changed != 1) {
        throw new InsufficientCapacityException();
    }

    Instant expiresAt = databaseTime.now()
        .plus(ttlPolicy.forResource(input.resourceId()));

    // INSERT reservation ACTIVE và outbox event
    // cùng transaction với UPDATE capacity.
    return reservationRepository.createAndReturn(
        tenantId, key, input, expiresAt);
}
~~~

Nếu hai callers trùng key cùng lúc, unique constraint có thể khiến một transaction rollback. Không cố tiếp tục sử dụng transaction đã lỗi; query kết quả key đã commit qua luồng retry/idempotency phù hợp.

### 21.2. Confirm trong transaction có row lock

~~~java
@Transactional
public ConfirmOutcome transitionConfirm(
        String reservationId,
        String operationId) {

    Reservation r = reservationRepository.lockById(reservationId);

    if (r.state() == CONFIRMED && r.matches(operationId)) {
        return ConfirmOutcome.confirmed(r);
    }

    if (r.state() != ACTIVE) {
        return ConfirmOutcome.conflict(r.state());
    }

    Instant now = databaseTime.now();

    if (!now.isBefore(r.expiresAt())) {
        reservationRepository.markExpired(r);
        capacityRepository.releaseHeld(r.resourceId(), r.quantity());
        outboxRepository.appendExpired(r);
        return ConfirmOutcome.expired(r);
    }

    reservationRepository.markConfirmed(r, operationId);
    capacityRepository.moveHeldToAllocated(
        r.resourceId(), r.quantity());
    outboxRepository.appendConfirmed(r);
    return ConfirmOutcome.confirmed(r);
}
~~~

Hàm này trả outcome để transaction **commit** trước khi controller map EXPIRED thành HTTP 409. Nếu ném unchecked exception ngay sau khi cập nhật EXPIRED trong Spring @Transactional mặc định, transaction có thể rollback, khiến cleanup không được lưu.

### 21.3. Controller map state thành HTTP

~~~java
@PostMapping("/v1/reservations/{id}/confirm")
public ResponseEntity<?> confirm(
        @PathVariable String id,
        @RequestHeader("Idempotency-Key") String operationKey) {

    ConfirmOutcome outcome =
        reservationService.transitionConfirm(id, operationKey);

    return switch (outcome.state()) {
        case CONFIRMED -> ResponseEntity.ok(outcome.view());
        case EXPIRED -> ResponseEntity.status(409)
            .body(Map.of("code", "RESERVATION_EXPIRED"));
        default -> ResponseEntity.status(409)
            .body(Map.of("code", "INVALID_RESERVATION_STATE"));
    };
}
~~~

Đây là minh họa cấu trúc. Production cần xác minh caller, tenant, request payload, expiry semantics, version và deadlock/retry policy. Không gọi service xuyên mạng trong local DB transaction để chờ vài giây nếu có thể tránh.

### 21.4. Optimistic locking và JPA

Có thể dùng @Version trên reservation để phát hiện ghi đè đồng thời, nhưng @Version **không tự bảo đảm capacity invariant** nếu mỗi request vẫn đọc available rồi insert không kiểm điều kiện. Capacity row/constraint phải được bảo vệ độc lập.

### 21.5. Không dùng RAM replica làm nguồn sự thật

ConcurrentHashMap trong Inventory replica A không đồng bộ với B; static lock cũng không bảo vệ xuyên pods. Reservation phải sống qua restart và được query bởi worker/reconciler khác.

## 22. Coordinator và cơ chế khôi phục

Order cần lưu state workflow:

~~~text
SagaRecord:
  sagaId
  orderId
  reservationIds[]
  paymentOperationId
  currentStep
  lastKnownPaymentState
  lastKnownInventoryState
  retryCount
  nextAction
  updatedAt
~~~

Một transaction Order có thể cập nhật trạng thái và outbox command/event. Worker đọc state, gọi service tiếp theo và ghi kết quả. Khi worker chết, workflow có thể được tiếp tục bằng một worker khác.

### 22.1. Retry có kiểm soát

- Giữ nguyên operation ID qua retry.
- Backoff và jitter cho lỗi tạm.
- Giới hạn retry theo deadline/capacity.
- Không retry confirm đã expired vô hạn.
- Không phát payment request mới bằng key mới khi outcome cũ chưa rõ.
- Dùng DLQ/manual remediation cho trường hợp không thể tự phục hồi.
- Không đánh đồng “đã gửi Release” với “đã release thành công”.

### 22.2. Reconciliation

Tìm các bất thường:

- ACTIVE nhưng expiresAt đã qua và chưa dọn.
- CONFIRMED trong Inventory nhưng Order vẫn WAITING.
- CAPTURED Payment nhưng Inventory EXPIRED.
- Order COMPLETED nhưng reservation không được confirm.
- Outbox events chưa publish lâu.
- Counters không khớp tổng records ACTIVE/CONFIRMED.

Không phải mọi sai lệch đều có thể tự động sửa; một số cần refund, hủy vé hoặc liên hệ khách.

## 23. Payment callback đến muộn

~~~text
T0 Inventory Reserve R, expiresAt=T+10m
T1 Payment auth/capture mất nhiều thời gian
T2 R EXPIRED và capacity được trả
T3 Khách khác giữ capacity vừa trả
T4 Payment callback SUCCESS cho order cũ
~~~

Không được chuyển R từ EXPIRED sang CONFIRMED. Nếu tiền đã authorize, có thể void theo provider; nếu capture, có thể refund; nếu Payment vẫn UNKNOWN, phải tra kết quả. Một reservation mới chỉ được tạo sau admission check mới, không sử dụng quyền cũ.

### 23.1. Webhook không bảo đảm đơn nhất hoặc thứ tự

Callback có thể được gửi trùng, đến chậm hoặc đảo thứ tự. Consumer dùng eventId/operationId và state machine. Đừng để callback FAILED đến sau SUCCESS làm Order chuyển lùi nếu provider status không cho phép.

### 23.2. Compensation không phải rollback transaction toàn cục

Refund có thời gian hoàn tiền, phí và khả năng lỗi. Email đã gửi không thu hồi được. Một hành động compensation là operation nghiệp vụ mới, có idempotency, audit và status. Không hứa với khách rằng mọi side effect đã bị “rollback” nếu chưa có bằng chứng.

## 24. Giám sát và SLO

| Chỉ số | Điều cần hiểu |
| --- | --- |
| Active holds | Có bao nhiêu reservation ACTIVE |
| Held/allocated/available capacity | Mức sử dụng và invariant |
| Reserve accept/reject rate | Mức khan hiếm và contention |
| Time-to-confirm P50/P95/P99 | Cơ sở chọn TTL |
| Expiry/abandon rate | Khách bỏ giỏ, TTL quá ngắn/dài |
| Expiry cleanup lag | Tài nguyên bị giữ sau deadline bao lâu |
| Confirm after expiry | Callback/checkout quá chậm |
| Terminal state conflicts | Race confirm/release/expire |
| Idempotency dedupe hits | Retry và duplicate operations |
| Reconciliation backlog age | Workflow đang UNKNOWN quá lâu |
| Payment captured but expired | Tác động tài chính cần ưu tiên |
| Compensation pending | Số void/refund/release chưa hoàn tất |
| Outbox lag / DLQ | Event propagation/recovery |
| Invariant violations | Cảnh báo khẩn về oversell |

HTTP 200 không đủ chứng minh checkout đúng; timeout cũng không đủ chứng minh thất bại. Cần đo **logical operation outcome**, terminal states và các trường hợp business inconsistency.

### 24.1. Trace và log

~~~text
trace/order:
  Order.createSaga
  Inventory.reserve
  Payment.authorize
  Inventory.confirm
  Order.commitFinalState
  Outbox.publish
~~~

Một saga kéo dài có thể dùng trace links/correlation thay vì span mở suốt nhiều phút. Tránh log raw access token, cookie, số thẻ hoặc PII không cần thiết. Metrics không nên dùng reservationId riêng làm label với cardinality vô hạn.

## 25. Kiểm thử bắt buộc

### 25.1. Reserve–Reserve tranh đơn vị cuối

~~~text
Given: capacity=1, held=0, allocated=0
When: A và B đồng thời Reserve(quantity=1)
Then:
  chỉ một ACTIVE reservation được tạo
  held+allocated <= capacity
  request còn lại nhận insufficient capacity
~~~

### 25.2. Confirm–Confirm trùng request

~~~text
Given: R ACTIVE, quantity=1
When: hai replicas đồng thời Confirm(R, cùng operation)
Then:
  R chuyển CONFIRMED một lần
  held giảm đúng 1, allocated tăng đúng 1
  request lặp nhận terminal result, không tạo effect mới
~~~

### 25.3. Confirm–Expire sát deadline

~~~text
Given: R ACTIVE, expiresAt=T
When: confirm và expiry transaction tranh row ở T
Then:
  chỉ một terminal transition
  counters phản ánh chính xác state
  confirm sau deadline không được hồi sinh R
~~~

Dùng clock điều khiển được/integration DB test với isolation thật. Tránh chỉ sleep() theo thời gian thực khiến test flake.

### 25.4. Extend–Expire

Gia hạn trước hạn thì được theo policy; sau hạn bị từ chối. Hai renew đồng thời không vượt max lifetime. Client sửa expiresAt phải bị bỏ qua/từ chối.

### 25.5. Release–Expire

Hai workers cùng muốn release R. Chỉ một lần giảm held; event có thể gửi lặp nhưng consumer dedupe.

### 25.6. Crash sau commit trước response

~~~text
Given: Confirm(R) đã commit
When: Inventory replica crash trước khi trả 200
Then:
  Retry/query với cùng operationId thấy CONFIRMED
  Không tạo allocation thứ hai
~~~

### 25.7. Crash sau DB commit trước event publish

Outbox relay sau restart phải publish được event. Nếu publish lặp, Order consumer chỉ chuyển state một lần.

### 25.8. Payment success khi R expired

Khi Payment callback thành công nhưng Inventory R đã EXPIRED và tài nguyên cấp cho khách khác, R vẫn EXPIRED; Order phải vào reconciliation/compensation theo policy.

### 25.9. Các fault khác

- Clock skew giữa replicas.
- Network partition Order ↔ Inventory.
- Retry storm, broker duplicate, event out of order.
- Database deadlock/timeout/rollback.
- Worker expiry chết giữa batch.
- Client bấm Confirm và Cancel đồng thời.
- Resource group giữ một số dòng thành công, số khác thất bại.
- Idempotency key dùng lại với payload khác.
- Release và callback Payment đến trễ sau rolling deploy.

Assertion quan trọng:

~~~text
held >= 0
allocated >= 0
held + allocated <= totalCapacity

mỗi reservation có tối đa một terminal state
mỗi logical Confirm có một allocation effect
mọi ACTIVE record có expiresAt hợp lệ
mọi workflow UNKNOWN có cơ chế reconciliation
~~~

## 26. Các phản mẫu

**“Chỉ cần SELECT available rồi INSERT.”**  
Sai khi concurrent requests. Cần atomic admission/transaction.

**“Dùng synchronized trong Java đủ chống oversell.”**  
Không qua nhiều replicas; local mutex không là distributed invariant.

**“Giữ DB transaction mở chờ khách thanh toán.”**  
Gây lock contention và connection exhaustion. Dùng business reservation persistent.

**“TTL Redis xóa key là mọi thứ đã an toàn.”**  
Không nếu capacity ở store khác hoặc cần audit/reconciliation.

**“Expiry worker chạy trễ thì hold vẫn có quyền confirm.”**  
Không nếu contract dựa vào expiresAt. Cleanup lag khác expiry semantics.

**“Confirm lặp chỉ cần trả 200.”**  
Phải kiểm đúng owner/operation và không chuyển state hai lần.

**“Payment timeout = chưa thu tiền.”**  
Sai. Cần query provider và đối soát.

**“Callback success có thể hồi sinh reservation đã hết hạn.”**  
Có thể phá invariant vì resource đã cấp cho người khác.

**“Outbox bảo đảm exactly once toàn hệ thống.”**  
Không. Relay có thể gửi trùng, consumer phải idempotent.

**“Compensation là rollback ACID.”**  
Sai. Refund/void/cancel là business operations riêng và có thể thất bại.

**“Xóa mọi bản ghi expired ngay lập tức.”**  
Có thể mất bằng chứng để trả retry muộn và đối soát payment.

**“Mọi loại tài nguyên nên có cùng TTL.”**  
Không. Vé, kho, booking, coupon, payment authorization có thời hạn và rủi ro khác nhau.

## 27. Bài tập thực hành

### Bài 1 — Ghế cuối cùng
Một ghế chỉ có capacity=1. Hai khách từ hai replicas đồng thời Reserve. Hãy viết transaction/conditional UPDATE và logic idempotency để đúng một người thắng.

### Bài 2 — Confirm đúng thời điểm hết hạn
R ACTIVE, expiresAt=10:00. Confirm bắt đầu lúc 09:59:59.900; sweeper vào lúc 10:00:00.010. Hãy định nghĩa clock/time rule, transaction, state terminal và test.

### Bài 3 — Payment đã thành công nhưng mất hàng
Payment callback success sau 7 phút; hold TTL=5 phút, hàng đã cấp cho khách khác. Thiết kế Order states, void/refund hoặc reservation mới, reconciliation và thông điệp cho khách.

### Bài 4 — Hai expiry workers
A và B cùng chọn R ACTIVE expired, quantity=3. Hãy làm sao chỉ một worker giảm heldCount; cùng transaction publish outbox event; consumer idempotent.

### Bài 5 — Nhóm ba tài nguyên
Checkout cần Inventory TTL 10m, Delivery TTL 6m, Promotion TTL 8m. Hãy lập deadline plan, renew/release policy, partial reservation compensation và tránh deadlock.

### Bài 6 — Timeout sau commit
Inventory đã confirm nhưng response mất. Client retry qua replica khác. Thiết kế endpoint GET operation status, idempotency key và response terminal.

### Bài 7 — Clock drift
A nhanh 5 giây, B chậm 7 giây. Hãy chứng minh vì sao database time authority và atomic state transition tránh kết quả khác nhau.

### Bài 8 — Redis vs database
Một nhóm muốn lưu hold key TTL trong Redis nhưng cập nhật capacity ở PostgreSQL. Hãy xác định failure windows và đề xuất một cơ chế lưu/đối soát có thể bảo vệ invariant.

### Bài 9 — Reconciliation dashboard
Có 15 ACTIVE reservations quá hạn 2 phút, 3 CAPTURED Payment nhưng Inventory EXPIRED, 5 outbox events chưa publish. Hãy sắp ưu tiên xử lý, metric/alerts và runbook.

## 28. Checklist thiết kế

### Domain và contract
- [ ] Resource owner và invariant được chỉ định.
- [ ] Reservation state machine/terminal states được mô tả.
- [ ] CONFIRMED có nghĩa cụ thể, không lẫn với payment settlement.
- [ ] Reserve, Confirm, Release, Expire, Extend có preconditions/side effects.
- [ ] API có idempotency key scope, payload identity và retention.
- [ ] Time authority, UTC, expiresAt và quy tắc ranh giới < / <= rõ.
- [ ] TTL/renew/max lifetime dựa trên số liệu nghiệp vụ.

### Tính đúng và đồng thời
- [ ] Capacity invariant được database transaction/constraint bảo vệ.
- [ ] Reserve–Reserve không oversell.
- [ ] Confirm–Expire chỉ một terminal state thắng.
- [ ] Release–Expire không giảm held hai lần.
- [ ] Counters, reservation state và outbox ghi cùng local transaction.
- [ ] Lock order và deadlock/retry policy được xác định.
- [ ] Không giữ transaction mở suốt checkout.

### Distributed workflow
- [ ] Saga/Order/Payment/Inventory mỗi bên có state và correlation riêng.
- [ ] Timeout được xem là UNKNOWN khi không có bằng chứng cuối.
- [ ] Payment callback trễ/trùng/đảo thứ tự được xử lý.
- [ ] Compensation void/refund/cancel có idempotency.
- [ ] Outbox và consumer dedupe/replay được thiết kế.
- [ ] Expiry worker có claim/batch/recovery.
- [ ] Reconciliation có owner, SLA và manual remediation.

### Vận hành
- [ ] AuthN/AuthZ, tenant isolation, anti-abuse và max holds.
- [ ] Metrics gồm held/allocated, expire lag, conflicts, compensation backlog.
- [ ] Logs/traces có operation correlation, không chứa token/PII.
- [ ] Đã test concurrency, failure injection, restart và rolling deployment.
- [ ] Retention/audit terminal records phù hợp.
- [ ] Có runbook cho Payment CAPTURED nhưng Inventory EXPIRED.

## 29. Mẫu ADR

~~~markdown
# ADR: Reservation with Expiry and Final Confirmation

## Context
- Resource và owner:
- Invariant capacity:
- Expected throughput/contended resources:
- Checkout P95/P99 và TTL:
- Các service tham gia:

## Decision
- State machine:
- Time authority và expiry semantics:
- Storage + transaction boundary:
- Admission/conditional update:
- Confirm–Expire race:
- Extend policy:
- Idempotency key/operation ID:
- Outbox/inbox/event ordering:
- Payment outcome/compensation:
- Reconciliation:
- Security/abuse controls:

## Alternatives
- No reservation, validate at commit:
- Redis TTL only:
- Long database transaction:
- TCC/Saga:
- Escrow/other capacity model:

## Risks
- Contention/oversell:
- Held capacity lost sales:
- Cleanup lag:
- Payment mismatch:
- DB/broker outage:
- Rollback/upgrade:

## Evidence
- Concurrency tests:
- Fault injection:
- Saga recovery tests:
- Metrics/alerts:
- Reconciliation runbook:
~~~

## 30. Tổng kết

**Reservation là quyền tạm thời đối với một tài nguyên hữu hạn, có owner, trạng thái, định danh và thời hạn.** Nó cho phép workflow nhiều service tiến hành mà không khóa database dài phút, nhưng chỉ đáng tin cậy khi state transitions và invariant được bảo vệ tại resource owner.

Những nguyên tắc trọng tâm:

1. **Giữ và xác nhận phải atomic tại owner.** Không oversell, không hai terminal transitions.
2. **Hết hạn là quy tắc nghiệp vụ.** Deadline dựa trên server clock, không dựa vào countdown client hay lịch chạy worker.
3. **Confirm/release/expire phải idempotent.** Retry không được nhân đôi allocation hoặc giảm held hai lần.
4. **Timeout không chứng minh thất bại.** Tra trạng thái và đối soát khi operation outcome chưa rõ.
5. **Payment và Inventory không cùng local transaction.** Saga/TCC và compensation phải bao phủ các failure windows.
6. **Không hồi sinh reservation đã expired.** Nếu tiền thành công nhưng tài nguyên đã mất, dùng void/refund hoặc quy trình mới có admission check.
7. **Event cần outbox và consumer dedupe.** Không giả định broker giao đúng một lần hay đúng thứ tự trong mọi tình huống.
8. **Phục hồi và quan sát là một phần thiết kế.** Expiry worker, Saga state, reconciliation và audit phải sống qua restart.

Câu hỏi cuối để review: **“Khi Confirm đến đúng lúc Expire, payment đã commit nhưng response mất, hoặc callback tới sau khi tài nguyên được người khác giữ, hệ thống có còn bảo vệ capacity, tiền khách hàng và một kết quả cuối duy nhất không?”** Câu trả lời phải đến từ state machine, transaction, idempotency, reconciliation và các phép thử lỗi lặp lại được.
