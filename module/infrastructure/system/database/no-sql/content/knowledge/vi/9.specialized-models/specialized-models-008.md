# Dữ liệu sự kiện dạng nối tiếp và nhu cầu phát lại

Trong các hệ thống NoSQL, nhiều mô hình dữ liệu tập trung trả lời câu hỏi **trạng thái hiện tại là gì**: đơn hàng đang ở trạng thái nào, giỏ hàng chứa những sản phẩm nào, hoặc thiết bị có giá trị đo mới nhất bao nhiêu. Nhưng một số hệ thống còn cần biết **những việc gì đã xảy ra để tạo ra trạng thái ấy**, và nếu bộ xử lý, chỉ mục hay bảng báo cáo bị lỗi thì có thể **phát lại lịch sử để tạo lại kết quả** hay không.

Đó là bài toán của **dữ liệu sự kiện dạng nối tiếp (append-only event data)** và **replay**. Thay vì chỉ ghi đè một giá trị, hệ thống ghi những sự kiện mới vào một dòng lịch sử. Nhiều bộ xử lý có thể đọc dòng đó để xây dựng trạng thái hiện tại, chỉ mục tìm kiếm, báo cáo, dữ liệu tổng hợp hay các hệ thống phụ trợ.

Khả năng này rất có ích, nhưng không xuất hiện tự động chỉ vì ta dùng một message broker hoặc đặt tên bảng là **Events**. Replay đúng cần giải quyết **thứ tự, độ bền, định danh, trùng lặp, retention, phiên bản schema, ranh giới giao dịch và tác dụng phụ**. Không có các điều kiện đó, đọc lại sự kiện có thể tạo dữ liệu sai hoặc lặp lại những hành động nguy hiểm như gửi email, thu tiền hay phát lệnh vận chuyển.

## 1. Từ lưu trạng thái đến lưu lịch sử sự kiện

Giả sử document đơn hàng hiện tại:

~~~json
{
  "orderId": "O-1042",
  "status": "CONFIRMED",
  "total": 530000,
  "version": 3
}
~~~

Document này cho biết đơn đã xác nhận, nhưng không cho biết các bước trước đó. Một dòng sự kiện có thể ghi:

~~~text
1. OrderCreated(orderId=O-1042, total=530000)
2. InventoryReserved(orderId=O-1042, reservationId=R-21)
3. OrderConfirmed(orderId=O-1042)
~~~

Nếu có một hàm áp dụng sự kiện có quy tắc rõ ràng, trạng thái có thể được tái tạo:

~~~text
state = emptyOrder
state = apply(state, OrderCreated)
state = apply(state, InventoryReserved)
state = apply(state, OrderConfirmed)

=> state.status = CONFIRMED
~~~

Điều khác biệt là **lịch sử không bị mất khi trạng thái đổi**. Khi đơn chuyển từ PENDING sang CONFIRMED, hệ thống ghi nhận một sự kiện mới thay vì sửa lịch sử PENDING để giả vờ đơn luôn là CONFIRMED.

### 1.1. Append-only là nguyên tắc logic

**Append-only** nghĩa là khi có diễn biến mới, hệ tạo record sự kiện mới và giữ ý nghĩa của những record đã commit. Ví dụ:

~~~text
OrderCreated
OrderConfirmed
OrderCancellationRequested
OrderCanceled
~~~

Không sửa sự kiện OrderConfirmed cũ thành OrderCanceled. Hai sự kiện đã xảy ra vào hai thời điểm khác nhau; lịch sử cần diễn đạt được điều đó.

Tuy nhiên, append-only **không mặc định là lưu mãi mãi**. Broker có thể hết retention, log có thể bị compaction theo key, archive có chính sách xóa và dữ liệu nhạy cảm có thể buộc phải được xử lý theo chính sách riêng. Khả năng replay bị giới hạn bởi phần lịch sử thực sự còn đủ.

### 1.2. Command, event và state khác nhau

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| **Command** | Yêu cầu thực hiện hành động, có thể bị từ chối | ConfirmOrder |
| **Event** | Một diễn biến đã được ghi nhận là xảy ra | OrderConfirmed |
| **State** | Kết quả hiện tại sau khi áp dụng sự kiện | status = CONFIRMED |
| **Notification** | Thông điệp gửi cho bên nhận, có thể thông báo hoặc yêu cầu làm việc | SendConfirmationEmail |

Không nên phát OrderConfirmed ngay khi nhận lệnh ConfirmOrder nếu các điều kiện nghiệp vụ chưa được xác nhận. Cũng không nên dùng replay sự kiện OrderConfirmed để gọi lại lệnh xác nhận đơn.

### 1.3. Lợi ích và chi phí

Lưu sự kiện hỗ trợ truy vết, đối soát, nhiều read model và xây lại kết quả sau lỗi. Đổi lại, nó tăng số lượng bản ghi, đòi hỏi quản lý schema lịch sử, replay, idempotency và retention. Với một ứng dụng CRUD nhỏ không cần lịch sử hay projection, mô hình trạng thái trực tiếp có thể đơn giản và phù hợp hơn.

## 2. Một sự kiện được thiết kế thế nào?

Một record sự kiện thường có phần metadata chung và phần payload nghiệp vụ:

~~~json
{
  "eventId": "evt-000103",
  "eventType": "OrderConfirmed",
  "schemaVersion": 2,
  "tenantId": "T-10",
  "aggregateType": "Order",
  "aggregateId": "O-1042",
  "aggregateVersion": 3,
  "occurredAt": "2026-11-14T08:03:00Z",
  "recordedAt": "2026-11-14T08:03:01Z",
  "correlationId": "req-7281",
  "causationId": "evt-000102",
  "payload": {
    "confirmedTotal": 530000,
    "currency": "VND"
  }
}
~~~

| Thành phần | Vai trò |
|---|---|
| **eventId** | Định danh một event ổn định qua retry và replay; hỗ trợ chống trùng |
| **eventType** | Quyết định cách diễn giải sự kiện |
| **schemaVersion** | Giúp đọc các bản ghi từ nhiều phiên bản payload |
| **tenantId** | Xác định phạm vi sở hữu, phân quyền và nơi lưu dữ liệu |
| **aggregateId** | Chỉ ra thực thể nghiệp vụ mà sự kiện tác động |
| **aggregateVersion** | Hỗ trợ kiểm soát thứ tự và ghi cạnh tranh theo aggregate |
| **occurredAt** | Thời điểm diễn biến nghiệp vụ xảy ra |
| **recordedAt** | Thời điểm sự kiện được ghi nhận vào hệ thống |
| **correlationId** | Liên kết các bước của một request hoặc quy trình |
| **causationId** | Chỉ ra lệnh hoặc sự kiện dẫn tới sự kiện hiện tại |
| **payload** | Dữ kiện cần để xử lý lại mà không đoán từ trạng thái hiện hành |

Không phải mọi ứng dụng đều cần đủ các trường trên. Event cảm biến có thể quan tâm deviceId, eventTime và measurement; event sourcing nghiệp vụ cần version hoặc cơ chế thứ tự mạnh theo aggregate. Nhưng một event quá thiếu dữ kiện có thể khiến replay không thể dựng lại kết quả.

### 2.1. Sự kiện nên mô tả một sự thật có ý nghĩa

Ví dụ OrderConfirmed thường có ý nghĩa rõ hơn một record chung OrderChanged với trạng thái mới. Dù vậy một change event tổng quát vẫn có thể phù hợp cho CDC hoặc đồng bộ kỹ thuật. Cần chọn mức ngữ nghĩa từ mục đích consumer.

### 2.2. Không lấy dữ liệu hiện tại để điền lịch sử một cách tùy tiện

Nếu event OrderCreated chỉ chứa productId và quantity, còn lần replay lấy giá bán **hiện tại** từ Product, doanh thu lịch sử có thể thay đổi sau khi sản phẩm tăng giá. Nếu nghiệp vụ yêu cầu giá tại thời điểm mua, event hoặc dữ liệu lịch sử có thẩm quyền phải lưu **unitPrice, currency, tax policy/version** thích hợp.

Tương tự, nếu replay cần tỷ giá, mức chiết khấu hoặc danh sách quyền tại thời điểm cũ, phải biết lấy nguồn lịch sử bất biến nào. Một hàm xử lý gọi các API hiện tại không chắc cho ra kết quả quá khứ đúng.

## 3. Phân biệt event log, event sourcing, CDC, audit và queue

Đây là các mẫu thường được dùng cùng nhau nhưng không đồng nghĩa.

| Mẫu | Nguồn có thẩm quyền | Mục đích và khả năng replay |
|---|---|---|
| **Append-only event log** | Tùy thiết kế log | Đọc lại các record đã ghi còn trong retention |
| **Event sourcing** | Event stream là nguồn trạng thái của aggregate | Tái tạo aggregate/projection bằng cách áp dụng event |
| **CDC (Change Data Capture)** | Database trạng thái đang được theo dõi | Phát thay đổi để đồng bộ sink, search, analytics |
| **Audit trail** | Nhật ký truy vết nghiệp vụ hoặc hệ thống | Tra cứu ai làm gì, khi nào; chưa chắc đủ tái dựng state |
| **Event streaming** | Luồng phát/sao chép sự kiện | Nhiều consumer xử lý độc lập, đọc lại theo vị trí |
| **Message queue** | Hàng đợi công việc | Giao việc và retry; có thể xóa message sau ACK |

### 3.1. Event sourcing là một quyết định về nguồn dữ liệu

Trong **event sourcing**, một stream như sau là nguồn có thẩm quyền của đơn:

~~~text
Order/O-1042:
  sequence 1: OrderCreated
  sequence 2: InventoryReserved
  sequence 3: OrderConfirmed
~~~

Trạng thái Order hiện hành chỉ là kết quả dẫn xuất. Một hệ thống khác có thể dùng bảng Orders làm nguồn chính và outbox để gửi OrderConfirmed cho downstream; hệ đó dùng event-driven messaging, nhưng chưa hẳn event sourcing.

### 3.2. CDC là thay đổi lưu trữ, không luôn là sự kiện nghiệp vụ

CDC có thể nói rằng hàng Orders đổi status từ PENDING sang CONFIRMED. Nhưng nếu yêu cầu ConfirmOrder đã bị từ chối, database không đổi, CDC cũng không có event tương ứng. Vì vậy CDC hữu ích cho đồng bộ dữ liệu, nhưng không thay thế mọi nhu cầu audit nghiệp vụ.

### 3.3. Audit log chưa chắc đủ để replay

Audit record “U-17 đã bấm Lưu” có thể hữu ích khi điều tra, nhưng không chứa nội dung đầy đủ để xây lại trạng thái. Một event nguồn đủ cho replay cũng chưa chắc đáp ứng toàn bộ yêu cầu audit về quyền truy cập, chống sửa đổi hoặc định danh con người.

## 4. Log phân vùng, thứ tự và offset

Một hệ log phân tán thường chia dữ liệu thành **partition** hoặc **stream**. Mỗi phần có trình tự nối tiếp riêng, cho phép nhiều consumer đọc độc lập.

~~~mermaid
flowchart LR
    PROD["Producers"] --> LOG["Durable event log"]
    LOG --> P0["Partition 0"]
    LOG --> P1["Partition 1"]
    P0 --> C1["Read model consumer"]
    P1 --> C1
    P0 --> C2["Analytics consumer"]
    P1 --> C2
~~~

### 4.1. Offset không phải định danh nghiệp vụ

Một offset là vị trí trong một partition/stream; nó giúp consumer ghi nhớ đã đọc đến đâu. Offset 100 ở partition 0 không có nghĩa event đó xảy ra trước offset 90 ở partition 1. Cũng không nên dùng offset như eventId toàn hệ thống.

EventId phục vụ nhận diện sự kiện. AggregateVersion phục vụ trình tự theo thực thể nghiệp vụ. Offset phục vụ tiến độ đọc log. Ba khái niệm có thể cùng tồn tại.

### 4.2. Partition key quyết định nơi giữ thứ tự

Nếu các sự kiện OrderCreated, InventoryReserved và OrderConfirmed của cùng đơn cần giữ thứ tự, dùng **orderId** hoặc khóa kết hợp **tenantId + orderId** để định tuyến tới cùng stream/partition có thể hợp lý.

| Cách chọn khóa | Ưu điểm | Đánh đổi |
|---|---|---|
| aggregateId | Các event của cùng aggregate dễ được xử lý theo thứ tự | Aggregate cực nóng có thể là nút thắt |
| tenantId | Dễ nhóm theo tenant | Tenant lớn có thể dồn lưu lượng vào một partition |
| tenantId + aggregateId | Tách thực thể giữa tenant và thường phân phối tốt hơn | Phải thiết kế serialization và routing nhất quán |
| Key ngẫu nhiên mỗi event | Có thể phân phối tải khá đều | Event cùng aggregate có thể đến sai thứ tự |
| Time bucket | Thuận tiện lưu theo vòng đời | Xử lý event đến muộn và đọc xuyên bucket phức tạp |

Chọn partition key chỉ là một phần: nếu consumer xử lý song song các event của cùng partition nhưng commit kết quả không theo thứ tự, ý nghĩa ordering vẫn có thể bị phá vỡ.

### 4.3. Không mặc định có thứ tự toàn cục

Hệ có nhiều partition thường chỉ có thứ tự trong từng partition. Muốn mọi giao dịch của mọi khách hàng có thứ tự toàn hệ thống phải thêm cơ chế coordination hoặc chấp nhận một điểm tuần tự hóa, thường đi kèm giới hạn throughput và availability.

Đa số workload chỉ cần thứ tự **theo một aggregate**. Đừng đánh đổi khả năng mở rộng để lấy global ordering khi nghiệp vụ không cần.

### 4.4. Event time khác recorded time và processing time

Một thiết bị có thể đo lúc 08:00, gửi lúc 09:00 và được consumer xử lý lúc 09:03:

~~~text
eventTime      = 08:00
recordedTime   = 09:00
processingTime = 09:03
~~~

Truy vấn lịch sử cảm biến thường dùng eventTime, trong khi replay theo offset dùng vị trí đã ghi. Sắp log theo eventTime có thể làm sai lịch sử nhận, đặc biệt khi có late events và clock skew. Các phép tổng hợp theo thời gian sự kiện có thể cần watermark, late-arrival policy và window, khác với thứ tự nghiệp vụ theo aggregateVersion.

## 5. Ghi sự kiện bền vững: tại sao dual-write có vấn đề?

Giả sử hệ thống xác nhận một đơn:

~~~text
1. UPDATE Orders SET status = CONFIRMED
2. PUBLISH OrderConfirmed to EventLog
~~~

Nếu bước 1 thành công nhưng tiến trình chết trước bước 2, trạng thái nguồn đã đổi nhưng consumer không nhận được sự kiện. Nếu publish trước rồi transaction database rollback, consumer có thể thấy sự kiện về một việc chưa được commit.

### 5.1. Transactional outbox

Mẫu **transactional outbox** ghi thay đổi dữ liệu và một event chờ phát trong **cùng ranh giới giao dịch nguyên tử**:

~~~text
BEGIN TRANSACTION
  update Order to CONFIRMED
  insert Outbox(eventId, OrderConfirmed)
COMMIT

Publisher:
  read unsent outbox
  publish to broker
  mark delivery progress
~~~

~~~mermaid
flowchart TD
    CMD["ConfirmOrder"] --> TX["Atomic transaction"]
    TX --> ORD[("Orders")]
    TX --> OUT[("Outbox")]
    OUT --> PUB["Publisher"]
    PUB --> LOG["Durable log"]
    LOG --> PROJ["Consumers"]
~~~

Nếu Orders và Outbox nằm ở các khóa hoặc hệ quản trị không hỗ trợ transaction thích hợp, chỉ tạo hai record riêng không tự bảo đảm atomicity. Cần dùng cơ chế transaction đúng phạm vi, CDC từ nguồn đã commit hoặc thiết kế khác phù hợp.

Outbox giảm nguy cơ **commit nguồn xong nhưng mất ý định phát event**; nó không tự bảo đảm message chỉ được publish một lần. Publisher có thể chết sau publish, trước khi đánh dấu đã gửi. Consumer phải chống trùng.

### 5.2. Append event theo expected version

Trong event sourcing, một thao tác có thể trực tiếp append sự kiện vào stream:

~~~text
append(
  stream = Order/O-1042,
  expectedVersion = 2,
  event = OrderConfirmed(version=3)
)
~~~

Nếu hai writer cùng dựa trên version 2, event store cần có thao tác kiểm tra version và append nguyên tử để tránh cả hai đều ghi version 3. Writer thất bại phải đọc trạng thái mới rồi đánh giá lại command.

### 5.3. Độ bền phải được xác định theo ACK và replication

Một broker phản hồi thành công có thể có nhiều ngữ nghĩa khác nhau: leader nhận, log được ghi bền, hoặc nhiều replica đã ACK. Các tham số đó ảnh hưởng dữ liệu có thể mất khi node/region lỗi và ảnh hưởng khả năng replay.

Hãy xác định:

- Khi nào producer được coi là commit thành công?
- Retry của producer có sinh trùng hoặc đổi thứ tự không?
- Replication factor, acknowledgment và RPO là gì?
- Khi leader đổi, record đã ACK có thể mất không?
- Event được lưu và sao chép tới những region nào?

Không nên suy ra mọi hệ có chữ **durable** đều có cùng bảo đảm.

## 6. Nhu cầu replay xuất hiện khi nào?

**Replay** là đọc lại sự kiện đã được ghi và áp dụng bằng một bộ xử lý để tái tạo hoặc thay đổi kết quả dẫn xuất.

Các trường hợp thường gặp:

1. **Rebuild projection:** bảng OrdersByCustomer bị mất hoặc sai.
2. **Sửa lỗi tính toán:** projector doanh thu cũ xử lý refund sai.
3. **Thêm chỉ mục:** xây search index mới từ lịch sử sự kiện.
4. **Khôi phục aggregate:** tính state từ stream/snapshot trong event sourcing.
5. **Đối soát:** so sánh projection với kết quả đọc lại nguồn sự kiện.
6. **Backtesting:** chạy thuật toán mới trên lịch sử mà không thay đổi dữ liệu live.
7. **Migration:** chuyển dữ liệu sang model hoặc hệ lưu trữ khác.

### 6.1. Replay một aggregate và replay toàn luồng

| Hình thức | Phạm vi | Điểm cần chú ý |
|---|---|---|
| Replay aggregate | Từng stream Order hoặc Account | Bắt đầu đúng version, không thiếu event |
| Replay projection | Nhiều stream/partition | Ordering, idempotency, checkpoint, catch-up |
| Replay một time range | Một khoảng event hoặc offset | Cần trạng thái ban đầu và quy tắc late events |
| Replay toàn bộ lịch sử | Tất cả event còn khả dụng | Chi phí, schema cũ, retention, side effects |

Replay từ đầu một log chỉ có 30 ngày retention sẽ không thể tái tạo chính xác một báo cáo cần dữ kiện của 2 năm nếu thiếu archive hoặc nguồn thay thế.

### 6.2. Những điều kiện để replay đáng tin

- Event chứa đủ thông tin để tính kết quả.
- Nguồn còn giữ đầy đủ sự kiện cần thiết.
- Consumer có thể đọc được các phiên bản schema cũ.
- Event có eventId/sequence phù hợp để phát hiện trùng và gap.
- Hàm dựng trạng thái hạn chế phụ thuộc vào dữ liệu hiện tại từ hệ ngoài.
- Checkpoint chỉ tiến khi kết quả xử lý tương ứng đã bền vững.
- Tác dụng phụ của nghiệp vụ được tách khỏi việc dựng projection.
- Có cơ chế bắt kịp sự kiện mới trong khi replay.
- Có đối soát, rollback và quyền truy cập theo tenant/region.

## 7. Replay không được thực thi lại tác dụng phụ

Giả sử consumer OrderConfirmed đang làm bốn việc:

~~~text
1. Cập nhật OrdersByCustomer
2. Cộng số đơn đã xác nhận vào báo cáo
3. Gửi email cho khách
4. Gọi hệ thống bên ngoài để tạo chứng từ
~~~

Nếu replay một triệu event vì read model bị lỗi mà vẫn chạy toàn bộ logic, hệ thống có thể gửi lại email cũ hoặc tạo chứng từ trùng.

Giải pháp là tách **projection handler** khỏi **effect handler**:

~~~mermaid
flowchart TD
    EVT["OrderConfirmed"] --> PROJ["Projection handler"]
    EVT --> LIVE["Live effect handler"]
    PROJ --> DB[("Read model")]
    LIVE --> EXT["Email / external services"]
    REPLAY["Replay job"] --> PROJ
~~~

Khi rebuild, chỉ bật các thao tác tạo hoặc sửa **projection mục tiêu**, không gọi lại thanh toán, gửi hàng hay email. Các effect bên ngoài còn cần idempotency riêng ở luồng live vì message có thể được giao lặp.

### 7.1. Hàm applyEvent nên xác định với cùng dữ liệu

Pseudocode:

~~~text
applyEvent(state, event):
    switch event.type:
        case OrderCreated:
            return state with total=event.total, status=PENDING
        case InventoryReserved:
            return state with status=RESERVED
        case OrderConfirmed:
            return state with status=CONFIRMED
        case OrderCanceled:
            return state with status=CANCELED
~~~

Hàm này không cần gọi đồng hồ hiện tại, lấy giá bán mới nhất, tạo ID ngẫu nhiên, hoặc gọi API thanh toán. Nếu thuật toán mới cố ý tính lại theo logic khác, cần gắn **projector version** và dữ liệu phụ trợ lịch sử cố định để kết quả có thể kiểm chứng và lặp lại.

### 7.2. Replay không phải phát lại command

Event OrderConfirmed có nghĩa một đơn **đã được xác nhận**, chứ không phải một yêu cầu mới cần chạy lại bước giữ kho hoặc thu tiền. Replay nhằm xây lại biểu diễn của sự thật đã ghi nhận; muốn thực thi lại command là một nghiệp vụ khác cần đánh giá riêng và kiểm soát tác dụng phụ.

## 8. At-least-once, duplicate, checkpoint và tính idempotent

Consumer có thể crash sau khi ghi kết quả nhưng trước khi commit offset:

~~~text
1. Consumer đọc PaymentCaptured tại offset 150.
2. Consumer cộng 530000 vào RevenueByDay.
3. Process chết trước khi lưu checkpoint mới.
4. Sau restart, consumer đọc offset 150 lần nữa.
5. Nếu tăng tiếp, doanh thu bị cộng hai lần.
~~~

### 8.1. Các mức giao nhận

| Cơ chế | Ý nghĩa | Hệ quả cho ứng dụng |
|---|---|---|
| At-most-once | Có thể bỏ mất event nhưng hạn chế giao lại | Không phù hợp dữ liệu không được mất |
| At-least-once | Một event có thể xuất hiện nhiều lần | Cần idempotency, dedup, checkpoint |
| Exactly-once trong phạm vi được hỗ trợ | Một số engine đảm bảo kết quả một lần trong ranh giới transaction | Phải biết có bao gồm sink và hiệu ứng bên ngoài không |

Exactly-once của một stream processor **không tự động bao gồm email, cổng thanh toán hoặc database nằm ngoài transaction của nó**. Phải xác định phạm vi bảo đảm thật.

### 8.2. Idempotency bằng eventId

Một projector có thể dùng:

~~~text
RevenueByDay(tenantId, date, total)
ProcessedEvent(eventId)

transaction:
    if eventId chưa được ghi:
        cộng doanh thu
        ghi ProcessedEvent(eventId)
commit
~~~

Điều kiện **đã xử lý hay chưa** và cập nhật projection cần có ranh giới nguyên tử phù hợp. Nếu đọc ProcessedEvent rồi ghi RevenueByDay thành hai hành động độc lập, nhiều worker có thể cùng xử lý một event.

### 8.3. Idempotency theo version của aggregate

Với một projection trạng thái từng đơn:

~~~text
storedVersion = 10
incoming event.version = 11  => có thể áp dụng
incoming event.version = 10  => trùng/cũ, bỏ qua
incoming event.version = 12  => thiếu version 11, cần xử lý gap
~~~

Thao tác kiểm tra version và cập nhật state phải được đồng bộ nguyên tử hoặc bằng cơ chế CAS tương ứng. Với projection tổng hợp nhiều aggregate, một version chung cho toàn bảng không đủ; cần thiết kế dedupe và đóng góp dữ liệu cho từng event/aggregate.

### 8.4. Checkpoint phải theo đúng tiến độ bền vững

Checkpoint trước khi ghi sink có thể dẫn tới **bỏ sót event** khi crash. Checkpoint sau ghi sink có thể dẫn tới **xử lý lặp**, vì vậy projector phải idempotent.

Với log phân vùng:

- Lưu tiến độ theo từng partition/stream.
- Nếu xử lý song song, không commit offset vượt qua event thấp hơn chưa xử lý.
- Phân biệt offset đã nhận, đã xử lý và đã commit.
- Khi sink và checkpoint không nằm trong cùng transaction, dùng một cơ chế khôi phục an toàn.

## 9. Sự kiện đến sai thứ tự, trùng hoặc bị thiếu

Trong hệ phân tán, thứ tự nhận có thể khác thứ tự nghiệp vụ:

~~~text
Consumer nhận:
  OrderConfirmed(version=3)
  OrderCreated(version=1)
  InventoryReserved(version=2)
~~~

Nếu áp dụng theo thứ tự nhận, projector có thể tạo trạng thái sai.

### 9.1. Cách xử lý theo yêu cầu nghiệp vụ

- Định tuyến event cùng aggregate vào cùng stream/partition có thứ tự được bảo đảm.
- Dùng aggregateVersion để phát hiện gap và duplicate.
- Nếu thiếu version, tạm dừng aggregate, nạp event còn thiếu hoặc đối soát nguồn.
- Với thống kê theo event time, dùng window/watermark và chính sách late events.
- Nếu phép tổng hợp thật sự giao hoán và idempotent, có thể không cần thứ tự nghiêm ngặt.

**Watermark** trong stream processing không tự bảo vệ thứ tự trạng thái của một aggregate; đây là hai bài toán khác nhau.

### 9.2. Poison event và schema lỗi

Một event không thể giải mã hoặc vi phạm bất biến có thể khiến consumer retry vô hạn. Cần phân biệt:

- Lỗi tạm thời của sink: retry với backoff.
- Payload sai schema: cách ly/quarantine hoặc DLQ để điều tra.
- Thiếu sequence quan trọng: tạm dừng luồng của aggregate và khôi phục.
- Lỗi dữ liệu không thể sửa: ghi nhận phạm vi ảnh hưởng, quyết định cách xử lý theo yêu cầu sản phẩm.

Bỏ qua event lỗi có thể làm projection không chính xác; phải có quy tắc rõ chứ không tự “skip để pipeline chạy tiếp”.

## 10. Quy trình replay an toàn để dựng lại read model

Giả sử bảng **OrdersByCustomer** bị lỗi do consumer cũ xử lý sai một số trạng thái. Dữ liệu nguồn và log vẫn còn đầy đủ. Mục tiêu là xây bảng **OrdersByCustomer_v2** và chuyển API sang đọc bảng mới.

### Bước 1: Chốt phạm vi

Xác định tenant, stream/partition, khoảng lịch sử, schema, nguồn dữ liệu có thẩm quyền và các giới hạn retention. Nếu lịch sử đã bị cắt, cần có archive/snapshot hoặc chấp nhận giới hạn tái dựng được mô tả rõ.

### Bước 2: Chuẩn bị projector mới

Projector v2 cần xử lý schema cũ, có idempotency và chỉ ghi projection. Vô hiệu hóa các hành động gửi email, gọi thanh toán và tác động live.

~~~text
source = OrderEvents
consumer = OrderProjectionV2
target = OrdersByCustomer_v2
mode = REBUILD
external effects = DISABLED
~~~

### Bước 3: Ghi ranh giới theo partition

Đặt nguồn bắt đầu, kiểm kê các partition/stream và ghi lại offset hoặc sequence cho từng phần. Không dùng một timestamp toàn cục thay thế offset trong hệ không có global order.

### Bước 4: Replay vào đích riêng có checkpoint

~~~text
for each partition:
    read events starting at saved offset
    validate schema and tenant scope
    apply event to new projection idempotently
    save checkpoint after committed result
~~~

Đây là pseudocode; trong thực tế cần xử lý batch, concurrency và lỗi ở từng event.

### Bước 5: Bắt kịp lưu lượng live

Trong lúc đọc lịch sử, producer vẫn ghi sự kiện mới. Projector v2 phải tiếp tục đọc tail của log, hoặc có cơ chế ghép snapshot/backfill với các event phát sinh sau mốc đã lưu.

Không cắt API sang v2 ngay khi job đọc xong một snapshot cũ; phải bảo đảm dữ liệu mới đã được xử lý đến ngưỡng thống nhất.

### Bước 6: Đối soát và cutover

So sánh số bản ghi, trạng thái/version, tổng tiền, thứ tự phân trang, duplicate, gap và độ trễ. Đổi đường đọc khi kết quả đạt tiêu chí và consumer v2 đã bắt kịp. Giữ phương án rollback trong thời gian kiểm chứng.

### Bước 7: Ghi lịch sử công việc replay

Lưu version projector, phạm vi tenant, offset bắt đầu/kết thúc, số event xử lý, lỗi, checksum/số liệu đối soát, thời điểm cutover và người chịu trách nhiệm. Những dữ kiện này giúp giải thích vì sao read model mới có kết quả như hiện tại.

~~~mermaid
flowchart TD
    SOURCE["Event log"] --> OLD["Old projector"]
    SOURCE --> NEW["Replay projector v2"]
    NEW --> TARGET[("Read model v2")]
    NEW --> CHECK["Checkpoint per partition"]
    TARGET --> VALIDATE["Đối soát và catch-up"]
    VALIDATE --> CUT["Switch API reads"]
~~~

## 11. Snapshot và khôi phục aggregate nhanh hơn

Khi một aggregate có rất nhiều event, replay từ event đầu tiên mỗi lần tải state có thể tốn tài nguyên. **Snapshot** lưu trạng thái tại một version đã biết:

~~~json
{
  "aggregateId": "O-1042",
  "snapshotVersion": 1000,
  "schemaVersion": 3,
  "state": {
    "status": "PROCESSING",
    "total": 530000
  }
}
~~~

Khôi phục:

~~~text
state = loadSnapshot(aggregateId)
for event in loadEventsAfter(snapshotVersion):
    state = apply(state, event)
~~~

Snapshot phải phản ánh **đúng state tại đúng sequence**. Nếu snapshot lấy state của version 1003 nhưng được ghi nhãn 1000, replay phần tiếp theo có thể áp dụng trùng hoặc sai.

### 11.1. Snapshot không thay toàn bộ lịch sử

Một snapshot aggregate tại version 1000 có thể đủ để khôi phục trạng thái sau đó, nhưng không đủ để tính doanh thu từng ngày của 3 năm trước nếu các event tài chính lịch sử đã biến mất.

Vì vậy phải phân biệt:

- **Khôi phục state mới nhất:** snapshot và event tail có thể đủ.
- **Xây mọi projection lịch sử trong tương lai:** cần giữ event hoặc dữ liệu lịch sử có thông tin tương đương.

### 11.2. Snapshot cũng có schema và quyền truy cập

Snapshot chứa dữ liệu nghiệp vụ, có thể là dữ liệu nhạy cảm. Nó cần versioning, retention, backup, quyền theo tenant và khả năng xác minh tương tự các dữ liệu gốc khác.

## 12. Schema evolution và replay sự kiện cũ

Event nối tiếp có thể tồn tại lâu hơn rất nhiều phiên bản ứng dụng. Một event OrderCreated cũ có dạng:

~~~json
{
  "eventType": "OrderCreated",
  "schemaVersion": 1,
  "payload": {"total": 530000}
}
~~~

Phiên bản mới:

~~~json
{
  "eventType": "OrderCreated",
  "schemaVersion": 2,
  "payload": {
    "total": 530000,
    "currency": "VND",
    "taxIncluded": true
  }
}
~~~

Projector v2 không thể mặc định mọi event cũ đều có currency và taxIncluded.

### 12.1. Các chiến lược hỗ trợ schema lịch sử

| Cách tiếp cận | Ý tưởng | Điều cần cẩn trọng |
|---|---|---|
| Reader tương thích ngược | Hỗ trợ các trường cũ và mới | Default phải đúng về nghiệp vụ |
| Upcaster | Biến event v1 thành dạng logic mới trước khi apply | Không được bịa dữ liệu lịch sử |
| Versioned event type | Diễn đạt sự thay đổi ngữ nghĩa bằng loại/phiên bản rõ ràng | Consumer cần xử lý nhiều loại |
| Migration/rebuild có kiểm soát | Chuyển sang read model hoặc log mới | Cần đối soát và ranh giới cutover |

Nếu event v1 không có currency và lịch sử từng tồn tại nhiều loại tiền, gán mọi event cũ mặc định VND có thể làm báo cáo sai. Cần nguồn bổ sung đáng tin cậy hoặc công khai phạm vi không thể khôi phục chính xác.

### 12.2. Contract ở cả producer và consumer

Producer mới có thể phát schema mới khi consumer cũ vẫn chạy; consumer mới lại phải đọc schema cũ lúc replay. Vì vậy nên có quy tắc compatibility, schema registry hoặc contract test phù hợp, version logic và kế hoạch rollout.

Không nên tái sử dụng một eventType với ý nghĩa hoàn toàn khác mà không có chiến lược tương thích.

## 13. Retention, archive, compaction và giới hạn replay

**Append-only không có nghĩa event vẫn còn mãi trong broker.** Nhiều hệ hỗ trợ:

- Retention theo thời gian hoặc dung lượng.
- Log compaction theo key để giữ một bản trạng thái gần nhất.
- Archive event sang object storage/kho lạnh.
- Snapshot trạng thái kết hợp event tail.
- Xóa theo quyền riêng tư, retention hợp đồng hoặc data residency.

**Log compaction theo key** ở broker khác với **SSTable compaction của LSM-tree**. Log compaction có thể làm lịch sử các lần cập nhật theo cùng key không còn đọc đầy đủ. SSTable compaction là cách lưu trữ bên dưới hợp nhất/tái tổ chức tệp. Hai cơ chế có mục đích và semantics khác nhau.

### 13.1. Replay horizon

| Mục tiêu | Lịch sử tối thiểu cần có |
|---|---|
| Consumer có thể khởi động lại sau lỗi 24 giờ | Event còn giữ đủ từ checkpoint |
| Dựng báo cáo 90 ngày | Event hoặc archive đủ dữ liệu cho 90 ngày |
| Khôi phục state mới nhất | Snapshot hợp lệ + event tail, hoặc toàn stream |
| Audit 5 năm | Lịch sử có đúng trường audit và retention yêu cầu |
| Xây projection mới từ ngày đầu | Toàn bộ dữ kiện cần thiết hoặc nguồn lịch sử thay thế |

Nếu broker giữ 7 ngày, không thể tuyên bố replay được 2 năm nếu không có archive, snapshot hoặc nguồn dữ liệu phù hợp khác.

### 13.2. Dung lượng tăng theo tốc độ sự kiện

Giả sử 10.000 event/giây, mỗi event trung bình 500 byte:

~~~text
10.000 × 500 = 5.000.000 byte/giây

5.000.000 × 86.400 = 432.000.000.000 byte/ngày
                      ≈ 432 GB/ngày (đơn vị thập phân)

30 ngày ≈ 12,96 TB dữ liệu logic
~~~

Chưa tính replication, index, overhead phân đoạn, compression, backup, archive và băng thông. Với tải không đồng đều phải tính cả peak và headroom. Thêm khả năng replay lâu dài có thể tăng đáng kể chi phí lưu trữ và vận hành.

### 13.3. Dữ liệu nhạy cảm trong event log

Một event chứa số điện thoại hoặc địa chỉ có thể được sao chép tới nhiều consumer, index và archive. Cần:

- Chỉ đưa vào payload dữ kiện thực sự cần.
- Dùng ID/tham chiếu khi không cần lặp dữ liệu cá nhân.
- Kiểm soát tenant scope, quyền truy cập và region.
- Thiết kế retention và xóa/ẩn danh phù hợp chính sách.
- Kiểm kê backup, archive và projection.
- Không coi append-only là lý do bỏ qua nghĩa vụ xóa dữ liệu.

Việc một event đã được mã hóa không tự động giải quyết mọi yêu cầu vị trí lưu dữ liệu.

## 14. Chọn mô hình lưu sự kiện theo nhu cầu

| Mô hình/công cụ | Khi nào thường phù hợp | Cần xác minh |
|---|---|---|
| Durable partitioned log / broker | Nhiều consumer đọc tuần tự, replay theo offset | Retention, ACK, ordering, replication |
| Event store theo aggregate stream | Event sourcing với expected-version append | Concurrency, version, snapshot, truy vấn xuyên stream |
| Wide-column theo time range | Nhiều event, cần truy vấn theo partition và thời gian | Partition key, TTL, compaction, hot key |
| Document collection lưu event | Payload linh hoạt, truy vấn metadata | Index, write throughput, kích thước, transaction |
| CDC từ database nguồn | Đồng bộ index, analytics, cache | Snapshot ban đầu, retention, before/after |
| Time-series engine | Telemetry/metric, downsampling theo thời gian | Độ đầy đủ của event gốc và replay |
| Object storage archive | Lưu lâu dài và batch replay | Manifest, schema, thứ tự, chi phí truy xuất |

Một hệ có thể kết hợp database giao dịch, outbox/CDC, broker, read model và archive:

~~~mermaid
flowchart TD
    API["Transactional API"] --> DB[("Authoritative DB")]
    DB --> OUT["Outbox / CDC"]
    OUT --> LOG["Durable event log"]
    LOG --> P1["Projection worker"]
    LOG --> P2["Analytics worker"]
    LOG --> ARCH[("Long-term archive")]
    P1 --> RM[("NoSQL read model")]
    ARCH --> REBUILD["Batch replay"]
    REBUILD --> RM2[("New read model")]
~~~

Trong event sourcing, event store có thể là nguồn trạng thái chính thay cho DB trạng thái. Hình trên chỉ minh họa một dạng kiến trúc, không bắt buộc dùng nhiều sản phẩm. Mỗi hệ thêm vào đều tạo công việc quản lý schema, quyền, backup, đồng bộ và on-call.

## 15. Case study: đơn hàng, thanh toán và báo cáo doanh thu

Một nền tảng thương mại điện tử cần:

- Xác nhận đơn hàng có bảo vệ bất biến trạng thái.
- Hiển thị lịch sử đơn theo khách hàng.
- Ghi nhận thanh toán và hoàn tiền.
- Tổng hợp doanh thu theo ngày và tenant.
- Có thể tính lại doanh thu khi quy tắc kế toán hoặc projector thay đổi.

### 15.1. Sự kiện nghiệp vụ

~~~text
OrderCreated(orderId, total, currency)
InventoryReserved(orderId, reservationId)
OrderConfirmed(orderId)
PaymentCaptured(orderId, paymentId, amount, currency)
RefundIssued(orderId, refundId, amount, currency)
OrderCanceled(orderId, reason)
~~~

**OrderConfirmed** không nhất thiết đồng nghĩa tiền đã được thu. Báo cáo tiền có thể phải dựa trên PaymentCaptured và RefundIssued hoặc các sự kiện đã được nghiệp vụ/kế toán xác nhận.

### 15.2. Cùng lịch sử, nhiều kết quả dẫn xuất

~~~text
Authoritative source / event stream
          |
          +--> OrdersById
          +--> OrdersByCustomer
          +--> RevenueByDay
          +--> SearchIndex
~~~

Nếu RevenueProjector v1 cộng PaymentCaptured nhưng bỏ sót RefundIssued, báo cáo sẽ cao hơn thực tế. Có thể xây RevenueByDay_v2 từ sự kiện lịch sử:

1. Định nghĩa quy tắc tính tiền, hoàn tiền, thời điểm ghi nhận.
2. Viết projector v2 với schema cũ và mới.
3. Replay vào bảng v2 riêng, có dedupe và checkpoint.
4. Bắt kịp các sự kiện live.
5. Đối soát theo ngày, currency, tenant và ID giao dịch.
6. Chuyển báo cáo sang v2 khi đạt ngưỡng kiểm chứng.

Điểm cốt lõi: **Replay PaymentCaptured không được gọi lại cổng thanh toán để thu tiền lần hai**. Projector chỉ diễn giải thông tin đã được xác nhận.

### 15.3. Refund đến sau ảnh hưởng báo cáo ngày nào?

Một thanh toán được capture ngày 1, hoàn tiền ngày 10. Có báo cáo trừ refund vào ngày 10; có báo cáo cần điều chỉnh doanh thu của ngày bán gốc. Không có đáp án chung trước khi chốt định nghĩa nghiệp vụ. Event cần chứa paymentId/refundId, amount, currency, mối liên hệ giao dịch và các mốc thời gian thích hợp để hỗ trợ quy tắc được chọn.

### 15.4. Replay có thể gây tải lớn

Nếu live xử lý 10.000 event/giây, replay 100 triệu event cần thời gian và tài nguyên đáng kể. Chạy cùng sink với API checkout có thể tăng p99 latency hoặc gây throttling.

Nên cô lập read model rebuild, giới hạn tốc độ, theo dõi lag/catch-up và chỉ cutover sau đối soát. Replay đúng logic nhưng làm hệ production mất ổn định vẫn là thiết kế vận hành chưa đạt.

## 16. Observability và vận hành replay

| Nhóm chỉ số | Điều cần theo dõi |
|---|---|
| Producer | Event/giây, payload bytes, ACK latency, lỗi gửi, retry |
| Broker/log | Partition skew, replica lag, retention horizon, dung lượng |
| Consumer | Lag theo partition, offset commit, throughput, rebalance |
| Correctness | Duplicate, aggregate version gap, mismatch projection |
| Schema | Decode error, event không tương thích, quarantine/DLQ |
| Replay | Job version, phạm vi, tốc độ, checkpoint, lag so với live |
| Sink | p95/p99 write, conflict, lỗi index, kết quả đối soát |
| Security | Lỗi cross-tenant, truy cập trái vùng, dữ liệu nhạy cảm trong log |

Một metric consumer lag trung bình có thể che partition cực nóng hoặc một poison event làm kẹt một aggregate. Cần giữ khả năng truy vết theo eventId, aggregateId và correlationId; tuy nhiên không nên biến mọi ID riêng lẻ thành label metric gây bùng nổ cardinality. Các ID đó thường hợp lý hơn trong log hoặc trace.

### 16.1. Thông tin cần lưu cho mỗi replay job

~~~json
{
  "replayJobId": "replay-20261114-01",
  "source": "OrderEvents",
  "projectorVersion": "revenue-v2.1",
  "target": "RevenueByDay_v2",
  "scope": {"tenantId": "T-10"},
  "processedEvents": 1250000,
  "rejectedEvents": 0,
  "status": "COMPLETED"
}
~~~

Trong triển khai thực tế còn cần offset/range cho từng partition, thời gian chạy, checksum/đối soát, các event bị cách ly và thông tin cutover để một lần dựng lại có thể kiểm tra được.

## 17. Những sai lầm thường gặp

### “Có broker thì replay được toàn bộ lịch sử mãi mãi”

Retention theo thời gian/dung lượng, log compaction hoặc mất archive có thể làm lịch sử không đầy đủ. Cần biết replay horizon thực tế.

### “Phát event là đã dùng event sourcing”

Nếu database trạng thái vẫn là nguồn chính còn event chỉ để thông báo, đó chưa nhất thiết là event sourcing. Phân biệt rõ nguồn có thẩm quyền giúp quyết định cách phục hồi.

### “Có timestamp là có thứ tự chính xác”

Clock skew, event đến muộn, nhiều partition và timestamp trùng làm thứ tự không chắc chắn. Dùng version/sequence theo phạm vi cần bảo vệ.

### “Offset là ID duy nhất cho event”

Offset có phạm vi partition; dùng eventId ổn định để dedupe và aggregateVersion cho trình tự nghiệp vụ khi cần.

### “Commit offset trước cho nhanh”

Nếu kết quả sink chưa bền vững, restart có thể bỏ qua event. Checkpoint phải được phối hợp với ghi và idempotency.

### “Exactly-once nghĩa là mọi API bên ngoài chỉ chạy một lần”

Bảo đảm chỉ đúng trong phạm vi được sản phẩm hỗ trợ. Email, thanh toán, giao hàng và các hệ khác vẫn cần idempotency.

### “Replay là chạy lại toàn bộ handler”

Điều này dễ làm gửi email, thu tiền hoặc tạo chứng từ trùng. Tách rebuild projection khỏi live effects.

### “Event là bất biến nên không cần migration schema”

Event cũ vẫn cần được reader mới giải mã và diễn giải đúng. Cần versioning, compatibility và upcaster khi thích hợp.

### “Snapshot đã đủ cho mọi báo cáo lịch sử”

Snapshot có thể đủ cho state mới nhất nhưng không lưu chi tiết mọi thay đổi cũ. Muốn báo cáo lịch sử cần dữ kiện tương ứng.

### “Chỉ cần chạy lại job là read model sẽ đúng”

Nếu logic vẫn sai, event lỗi bị bỏ qua, checkpoint thiếu hoặc replay nhân đôi số liệu, kết quả có thể tệ hơn. Cần đối soát và cutover có kiểm soát.

### “Append-only cho phép bỏ qua xóa dữ liệu”

Quyền riêng tư, retention và nghĩa vụ về dữ liệu có thể yêu cầu xóa/ẩn danh hoặc kiểm soát bản sao. Mô hình sự kiện phải đáp ứng những chính sách đó.

## 18. Quy trình lựa chọn mô hình sự kiện nối tiếp

Khi thiết kế NoSQL có nhu cầu replay, nên làm theo trình tự:

1. **Xác định mục tiêu:** cần replay để phục hồi consumer, aggregate, báo cáo hay audit?
2. **Chọn nguồn có thẩm quyền:** event store, database trạng thái với outbox/CDC hay hệ event độc lập?
3. **Thiết kế event contract:** eventId, aggregateId, sequence, tenant, schemaVersion và payload đủ dữ kiện.
4. **Xác định thứ tự:** theo aggregate, partition hay event time; cách phát hiện gap/duplicate.
5. **Bảo vệ commit:** expected-version append, transaction outbox hoặc cơ chế phù hợp.
6. **Thiết kế consumer:** idempotent, checkpoint an toàn, xử lý poison event và cách ly effect.
7. **Định nghĩa replay horizon:** retention, archive, snapshot và nguồn lịch sử bổ sung.
8. **Quản lý schema evolution:** reader tương thích, upcaster, contract và version logic.
9. **Thiết kế replay vận hành:** giới hạn tải, catch-up, đối soát, cutover và rollback.
10. **Xét dữ liệu nhạy cảm:** tenant isolation, vị trí lưu, quyền truy cập và retention toàn hệ thống.

Một quyết định kỹ thuật có thể được ghi lại:

~~~text
Workload: Rebuild OrdersByCustomer, tối đa 6 tháng lịch sử
Source: Orders DB + transactional outbox
Key: (tenantId, orderId)
Ordering: theo aggregateVersion của từng Order
Delivery: at-least-once
Idempotency: eventId + atomic projection update
Replay target: versioned read model riêng
External effects during replay: disabled
Retention: broker 30 ngày + archive đủ 6 tháng
Schema: versioned event, upcaster cho định dạng cũ
Cutover: catch-up + đối soát đạt tiêu chí
Observability: offset lag, duplicate, gap, mismatch
~~~

## 19. Bài tập thực hành

### Bài 1 — Chuyển từ trạng thái sang sự kiện

Một hệ đặt vé chỉ lưu Booking hiện tại với status CANCELED. Hãy đề xuất các domain event để tái dựng trạng thái, chỉ ra eventId, bookingId, sequence, occurredAt và phân biệt command CancelBooking với event BookingCanceled. Nếu cần phát lại, làm sao tránh gửi email hủy vé lần nữa?

### Bài 2 — Thứ tự trên nhiều partition

Producer gửi OrderCreated, OrderConfirmed và OrderCanceled của cùng đơn vào ba partition khác nhau bằng key ngẫu nhiên. Consumer nhận theo thứ tự Canceled, Created, Confirmed. Hãy phân tích vì sao offset không đảm bảo thứ tự và đề xuất partition key cùng aggregateVersion.

### Bài 3 — Duplicate doanh thu

Consumer đọc PaymentCaptured ở offset 900, cộng doanh thu, sau đó crash trước khi checkpoint. Hãy thiết kế projector idempotent, nêu yêu cầu atomicity khi kiểm tra eventId và cập nhật tổng tiền, và quyết định checkpoint an toàn.

### Bài 4 — Log mất lịch sử

Broker giữ event 14 ngày nhưng nhóm phân tích muốn dựng lại báo cáo của hai năm trước. Chỉ có snapshot trạng thái đơn mới nhất. Hãy xác định những gì có thể phục hồi, những gì không có đủ dữ kiện và thiết kế retention/archive cho nhu cầu tương lai.

### Bài 5 — Event schema qua nhiều năm

OrderCreated v1 chỉ có total; v2 thêm currency. Hệ từng hỗ trợ nhiều loại tiền. Vì sao gán mọi event v1 mặc định VND có thể sai? Hãy thiết kế upcaster và cách nhận diện những record không thể khôi phục chính xác.

### Bài 6 — Rebuild dưới lưu lượng live

Log có 100 triệu event cũ, producer phát 10.000 event/giây, projector mới đọc tối đa 30.000 event/giây. Hãy mô tả cách replay vào bảng v2, lưu checkpoint từng partition, bắt kịp live, đối soát và chuyển API. Nêu rủi ro nếu chuyển đọc quá sớm.

### Bài 7 — Side effect khi replay

Một consumer vừa xây projection, vừa gọi cổng thanh toán và gửi email. Nhóm muốn replay một tháng event để sửa số liệu. Hãy tách projector và effect handler, thiết kế idempotency cho từng loại tác động và chỉ ra điều kiện an toàn trước khi chạy.

### Bài 8 — Ước lượng lưu trữ

Một hệ phát 2.500 event/giây, trung bình 1.200 byte/event, giữ 90 ngày, replication factor giả định bằng 3. Hãy tính dung lượng logic mỗi ngày, 90 ngày, và dung lượng sau nhân bản trước compression, index, backup. Vì sao chưa thể dùng ngay con số này để cấp quota đĩa production?

---

**Kết luận:** Dữ liệu sự kiện dạng nối tiếp giúp giữ lại những gì đã xảy ra và xây lại trạng thái hay kết quả dẫn xuất khi cần. Nhưng replay đáng tin cậy đòi hỏi **event đủ dữ kiện, thứ tự có phạm vi rõ ràng, lưu trữ bền vững, idempotency, checkpoint, schema evolution, retention phù hợp và cách ly tác dụng phụ**. Trong NoSQL, thiết kế event log phải gắn với partition key, nguồn dữ liệu có thẩm quyền, các read model và quy trình vận hành. Chỉ khi biết **replay nhằm mục đích gì, lịch sử có thể đọc lại đến đâu, và kết quả được xác minh thế nào**, hệ thống mới thực sự hưởng lợi từ mô hình này.
