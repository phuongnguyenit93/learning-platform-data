# So sánh các phương án theo mức nhất quán và trải nghiệm người dùng

> **Thông điệp chính:** Giao dịch phân tán không chỉ là bài toán làm cho nhiều database “cùng thành công hoặc cùng thất bại”. Đó là bài toán quyết định **bất biến nghiệp vụ nào phải đúng ngay**, hệ thống **có thể chấp nhận trạng thái trung gian nào**, và **người dùng sẽ được hứa điều gì** trong lúc nhiều dịch vụ cùng tham gia. Transaction cục bộ, điều phối đồng bộ, 2PC, TCC, Saga và event-driven eventual consistency có điểm mạnh và giới hạn khác nhau. Không có phương án tốt nhất cho mọi use case; lựa chọn phải đồng thời xét **mức nhất quán, trải nghiệm người dùng, khả năng phục hồi và chi phí vận hành**.

Bài thuộc nhóm **Giao dịch phân tán** trong chủ đề kiến trúc hệ thống và microservices. Trọng tâm là cách so sánh phương án khi một nghiệp vụ như đặt hàng, giữ chỗ, thanh toán hoặc chuyển tiền cần phối hợp nhiều bounded context với database và lịch triển khai riêng.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **atomicity, consistency, isolation, durability** ở phạm vi transaction cục bộ và các bảo đảm của workflow xuyên service.
2. Xác định bất biến cần giữ tức thời và các dữ liệu chỉ cần hội tụ sau.
3. So sánh một transaction cục bộ, gọi đồng bộ nhiều service, distributed transaction/2PC, TCC và Saga orchestration/choreography.
4. Hiểu vì sao HTTP 200, broker ACK hoặc timeout không tự chứng minh toàn bộ quy trình đã hoàn tất.
5. Thiết kế UX với **PENDING, CONFIRMED, FAILED, COMPENSATING, EXPIRED** và cách cập nhật trạng thái.
6. Đưa ra chiến lược idempotency, timeout, retry, outbox/inbox, reconciliation và thao tác bù.
7. Lựa chọn phương án cho thanh toán, giữ tồn kho, đặt vé, chuyển tiền, báo cáo và tích hợp đối tác.
8. Xây ma trận quyết định theo mức nhất quán, độ trễ cảm nhận, tính sẵn sàng, độ phức tạp và mức độ chấp nhận của người dùng.

## 2. Giao dịch phân tán xuất hiện ở đâu?

Giả sử một khách nhấn nút **Đặt hàng**. Hệ thống có các service độc lập:

~~~text
Browser
   |
   v
Ordering
   |---> Pricing      : Xác định giá hợp lệ
   |---> Inventory    : Giữ lượng hàng
   |---> Payment      : Thu/ủy quyền thanh toán
   +---> Fulfillment  : Chuẩn bị giao hàng
~~~

Mỗi service có thể lưu dữ liệu trong một database khác nhau. Trong một transaction SQL của Ordering, bạn không thể tự động rollback database Inventory hoặc Payment khi lời gọi HTTP khác thất bại.

Ví dụ tình huống lỗi:

~~~text
1. Ordering tạo Order(PENDING)            -> thành công
2. Inventory giữ 2 sản phẩm               -> thành công
3. Payment thu tiền                       -> thành công
4. Ordering nhận response Payment         -> timeout
5. Ordering không biết Payment đã thu tiền hay chưa
~~~

Nếu Ordering giả định “timeout nghĩa là không thu tiền” và gọi lại bằng payment ID mới, khách có thể bị trừ tiền hai lần. Nếu Ordering trả “đơn thất bại” nhưng Inventory vẫn đang giữ hàng, dữ liệu nghiệp vụ đã lệch. Nếu cứ giữ HTTP connection đợi tất cả bước hoàn thành, trải nghiệm người dùng có thể chậm và dễ thất bại theo một dependency nhỏ.

**Giao dịch phân tán cần thiết kế một mô hình trạng thái và cam kết nghiệp vụ, không chỉ chọn thư viện transaction.**

## 3. Ba câu hỏi trước khi chọn phương án

### Câu hỏi A — Điều gì tuyệt đối không được sai?

Ví dụ:
- Inventory không được chấp nhận hai reservation làm vượt lượng tồn có thể bán.
- Payment không được thực hiện hai lần cho cùng một ý định thanh toán.
- Sổ cái không được làm mất bút toán đối ứng cần thiết theo quy tắc hạch toán.
- Một booking không được xác nhận hai khách cùng sở hữu chỗ ngồi duy nhất.

Các bất biến này phải được bảo vệ tại **nơi sở hữu dữ liệu và quyền quyết định**, thường bằng transaction cục bộ, unique constraint, optimistic locking hoặc cơ chế atomic khác.

### Câu hỏi B — Người dùng có thể đợi và chấp nhận trạng thái nào?

Ví dụ:
- Mở trang danh mục: có thể chờ vài trăm mili giây, không cần giao dịch xuyên service.
- Đặt hàng: một số sản phẩm cần trả kết quả xác nhận ngay, sản phẩm khác cho phép PENDING vài giây.
- Đặt vé máy bay: có thể hiện “Đang giữ chỗ” rồi xác nhận sau.
- Chuyển tiền: người dùng cần biết lệnh đã được tiếp nhận, nhưng kết quả thực tế có thể cần thời gian xác minh.
- Cập nhật báo cáo: chấp nhận trễ một phút nếu hiển thị timestamp.

### Câu hỏi C — Khi một phần đã thành công nhưng phần còn lại lỗi, ta làm gì?

- Có thể **rollback nguyên tử** trong một nguồn dữ liệu duy nhất không?
- Có thao tác **bù (compensation)** thực sự không?
- Có thể **giữ tài nguyên tạm thời** với thời hạn không?
- Có thể tiếp tục xử lý, retry an toàn và đối soát hay không?
- Trạng thái nào sẽ được hiển thị khi kết quả vẫn chưa xác định?

Đừng dùng “eventual consistency” làm câu trả lời cho mọi tình huống. Cần mô tả **eventually converges bằng cơ chế nào, trong khoảng thời gian nào, và người dùng thấy gì khi chưa hội tụ**.

## 4. Phân biệt ba lớp nhất quán

### 4.1. Nhất quán của bất biến cục bộ

Inventory sở hữu tồn kho và reservation. Hai yêu cầu đặt hàng đồng thời không được làm lượng cam kết vượt điều kiện cho phép. Cần kiểm tra/ghi atomically trong database Inventory, ví dụ conditional update dưới transaction đúng.

Đây là chuyện **tính đúng của nơi sở hữu bất biến**, không phụ thuộc Ordering gọi Inventory bằng REST, gRPC hay queue.

### 4.2. Nhất quán của workflow xuyên nhiều context

Một Order có thể ở PENDING trong lúc đợi Inventory và Payment. Mỗi service có transaction cục bộ của mình, còn toàn quy trình phải theo **state machine + coordination**.

Không nên diễn đạt “mọi database cùng ACID” nếu không có một cơ chế distributed transaction tương ứng và các tài nguyên thật sự tham gia. Một Saga không cung cấp atomic rollback trong cùng một khoảnh khắc; nó cung cấp cách đưa hệ thống về một trạng thái nghiệp vụ chấp nhận được sau các bước bù hoặc phục hồi.

### 4.3. Nhất quán của dữ liệu đọc phái sinh

Dashboard, search index hoặc OrderHistoryView có thể cập nhật chậm từ event. Đây là eventual consistency ở read model. Nó không tự cho phép nghiệp vụ dùng bảng đọc trễ để quyết định có thu tiền hay giữ hàng hay không.

**Quy tắc:** Hãy ghi rõ thứ gì là invariant, thứ gì là workflow state, và thứ gì chỉ là projection phục vụ đọc. Ba lớp có thể có mức nhất quán khác nhau trong cùng hệ thống.

## 5. Vì sao ACID cục bộ chưa đủ cho toàn hệ phân tán?

Trong một database transaction, ta thường nhắc đến:

- **Atomicity:** một tập thay đổi commit/rollback theo phạm vi transaction.
- **Consistency:** transaction giữ các ràng buộc dữ liệu/luật được thực thi.
- **Isolation:** các transaction đồng thời quan sát/ảnh hưởng nhau theo isolation level.
- **Durability:** kết quả đã commit được lưu bền theo bảo đảm của hệ thống.

Ví dụ:

~~~sql
BEGIN;
UPDATE inventory
SET available = available - 2
WHERE sku = 'SKU-1' AND available >= 2;

INSERT INTO reservations(reservation_id, sku, quantity, status)
VALUES ('R-101', 'SKU-1', 2, 'HELD');
COMMIT;
~~~

Mã SQL chỉ minh họa; production phải kiểm tra affected rows, xử lý transaction rollback khi điều kiện không đạt, đảm bảo uniqueness/idempotency và tính đúng của schema. Transaction này có thể bảo vệ dữ liệu Inventory, nhưng **không bao phủ** transaction ở Payment hay Ordering nếu chúng dùng database/transaction manager khác.

Một Spring @Transactional trên Ordering không tự tạo ACID xuyên một HTTP request tới Payment. Dù Payment báo 200, transaction của Ordering có thể rollback sau đó; vẫn phải có cơ chế phối hợp.

## 6. Những phương án cần so sánh

Bảng sau là điểm bắt đầu, không phải ranking tuyệt đối:

| Phương án | Bảo đảm nổi bật | Trải nghiệm người dùng thường gặp | Giá phải trả |
| --- | --- | --- | --- |
| **Một transaction cục bộ** | ACID trong một ownership/DB | Kết quả ngay khi commit, dễ hiểu | Phạm vi chỉ một transaction owner; không xử lý đa service tự động |
| **RPC đồng bộ tuần tự** | Caller biết response từng bước nếu nhận được | Có thể chờ kết quả cuối trong một request | Không có atomicity xuyên DB; tail latency/timeout và unknown outcome |
| **2PC/XA** | Atomic commit qua các resource thật sự hỗ trợ coordinator | Có thể trả kết quả sau global commit | Blocking, coordinator/lock/timeout, availability và vận hành phức tạp |
| **TCC (Try–Confirm–Cancel)** | Giữ trước rồi xác nhận/hủy có kiểm soát ở business level | Có thể PENDING trong thời gian giữ tài nguyên | Mỗi participant phải hỗ trợ reservation, expiry, idempotency |
| **Saga orchestration** | Điều phối chuỗi local transactions và compensation | PENDING → CONFIRMED/FAILED rõ ràng | Coordinator, durable state, bù trừ không tuyệt đối |
| **Saga choreography** | Các context phản ứng với domain events theo hợp đồng | Bất đồng bộ, có thể cập nhật tiến độ | Khó nhìn toàn flow, semantic coupling, loop/event ordering |
| **Outbox + event projection** | Dữ liệu phái sinh đồng bộ tin cậy hơn sau commit | UI read có thể thấy stale và cần freshness UX | Lag, dedup, replay, đối soát; không thay invariant transaction |
| **Một nguồn sự thật + read model** | Invariant nằm trong một owner, read có thể trễ | Command phản hồi rõ, danh sách cập nhật sau | Cần thiết kế read-after-write cho UX |

Lưu ý: 2PC, TCC và Saga là những cơ chế quản lý **giao dịch/workflow**, trong khi outbox là mẫu bảo vệ **việc phát thông điệp** và read projection là kỹ thuật phục vụ **truy vấn**. Các phương án không loại trừ nhau hoàn toàn; một Saga có thể dùng outbox và read projection.

## 7. Phương án 1 — Giữ transaction trong một bounded context

Đây là lựa chọn nên xem xét trước: **có thể đặt bất biến và dữ liệu phải commit cùng nhau trong một ownership hợp lý không?**

Ví dụ một Inventory Service duy nhất thực hiện ReserveStock và ghi Reservation trong cùng transaction:

~~~text
Ordering -- ReserveStock(commandId) --> Inventory
                                         |
                                         v
                                   Local DB transaction
                                     - check available
                                     - reserve stock
                                     - record commandId
                                         |
                                         v
                                    Reserved/Rejected
~~~

Điểm mạnh:
- Dễ bảo vệ invariant bằng transaction database và constraint.
- Dễ hiểu kết quả commit/rollback ở một nơi.
- Ít thành phần điều phối hơn.
- Debug, test, backup và phục hồi đơn giản hơn so với giao dịch phân tán.

Giới hạn:
- Nếu business workflow gồm thu tiền từ đối tác và giữ hàng từ kho, không thể đơn giản đặt tất cả vào một DB transaction mà vẫn giữ ownership độc lập.
- Nếu gộp quá nhiều bounded context khác nhau chỉ để có một transaction, hệ thống có thể tạo một monolith khó thay đổi.
- Single database không đồng nghĩa mọi transaction đều serializable hoặc không bao giờ tranh chấp; cần chọn isolation/concurrency control đúng.

**Chọn một transaction cục bộ khi một bất biến thực sự thuộc một owner.** Đừng tạo một network hop cho những thao tác bắt buộc commit nguyên tử trong cùng context chỉ để tăng số service.

## 8. Phương án 2 — RPC đồng bộ, đợi kết quả cuối

Một ứng dụng có thể gọi tuần tự các service:

~~~text
HTTP POST /orders
      |
      v
Ordering
  |--> Pricing.getQuote       [success]
  |--> Inventory.reserve      [success]
  |--> Payment.capture        [success]
  |--> Save Order.CONFIRMED
      |
      v
HTTP 201 Created
~~~

Nếu tất cả thao tác nhanh, idempotent hoặc được xử lý lỗi tốt, người dùng có thể có kết quả rõ ngay trong request. Nhưng đây **không phải transaction phân tán nguyên tử**.

### 8.1. Failure window

Ví dụ Inventory giữ hàng thành công, Payment lỗi. Ordering cần giải phóng reservation hoặc đặt order vào trạng thái cần xử lý. Nếu lời gọi release cũng lỗi, phải retry/reconciliation.

Nếu Payment đã thu nhưng response mất, Ordering không thể kết luận thất bại. Cần tra status theo paymentId và không retry với ID mới.

### 8.2. Latency và availability coupling

Nếu mỗi lời gọi có thời gian chờ tệ nhất lớn, tổng latency tăng. Một request thành công đòi nhiều dependency cùng sẵn sàng. Retry ở nhiều tầng có thể gây tải khuếch đại.

Ví dụ minh họa:

~~~text
Pricing RPC                  60 ms
Inventory RPC               100 ms
Payment RPC                 240 ms
Ordering local + DB          90 ms
Network/gateway overhead     50 ms
---------------------------------
Sequential estimate         540 ms
~~~

Đây là mô hình giả định; không thể suy ra p95 tổng bằng tổng p95 các service. Cần đo trace end-to-end trong điều kiện tải thật. Nếu Payment đôi lúc mất vài giây, endpoint có thể vượt SLO dù các bước khác khỏe.

### 8.3. Khi nào hợp lý?

- Chỉ có ít dependency, latency ổn định và kết quả bắt buộc trước phản hồi.
- Mỗi participant có idempotency và khả năng truy vấn trạng thái sau timeout.
- Có deadline chung và rollback/compensation khi một bước thất bại.
- Bước thất bại không tạo side effect ngoài kiểm soát.
- Khối lượng tải và availability đáp ứng cam kết sản phẩm.

**RPC đồng bộ không phải anti-pattern mặc định.** Nó nguy hiểm khi người viết tưởng một chuỗi HTTP gọi thành công tương đương một global ACID transaction.

## 9. Phương án 3 — Two-Phase Commit (2PC) và XA

2PC là giao thức phối hợp commit giữa các resource tham gia, theo hai pha khái niệm:

**Pha 1 — Prepare:** Coordinator yêu cầu participant chuẩn bị commit. Participant phải giữ những ràng buộc cần thiết để có thể commit theo quyết định cuối.

**Pha 2 — Commit/Rollback:** Khi các participant sẵn sàng, coordinator phát quyết định commit hoặc abort, theo giao thức tương ứng.

~~~text
                  Coordinator
                 /           \
          Prepare             Prepare
             v                 v
         Database A         Database B
          "ready"            "ready"
             \                 /
                   decision
                 /          \
              Commit       Commit
~~~

### 9.1. Lợi ích

Khi các tài nguyên thật sự hỗ trợ 2PC và coordinator được cấu hình đúng, hệ thống có thể có **atomic commit** xuyên các resource trong phạm vi distributed transaction. Điều này phù hợp với một số hệ thống có hạ tầng transaction quản lý tập trung và yêu cầu nguyên tử rõ ràng.

### 9.2. Chi phí và giới hạn

- Nhiều participant có thể phải giữ lock hoặc tài nguyên khi đã prepare.
- Coordinator failure và recovery log cần xử lý chính xác.
- Một participant không sẵn sàng có thể kéo dài blocking hoặc làm global transaction thất bại.
- Qua vùng mạng/cluster có latency cao, thời gian giữ tài nguyên và xác suất lỗi tăng.
- Payment gateway, email API, webhook và phần lớn hệ thống bên ngoài **không phải XA resource** có thể tham gia prepare/commit.
- 2PC không tự tạo một UX phản hồi nhanh nếu phải chờ mạng và các resource.

### 9.3. 2PC có phù hợp microservices?

Có thể có ngữ cảnh phù hợp, nhưng với bounded context có database và lifecycle riêng, hoặc với các side effect ngoài database, 2PC thường không phải giải pháp tổng quát. Nó tăng liên kết hạ tầng và đồng thời giữa các participant, ảnh hưởng tính sẵn sàng.

Đừng đưa 2PC vào chỉ vì “cần consistency cao”. Trước hết xác định invariant nào cần atomicity, tài nguyên nào thực sự hỗ trợ 2PC, thời gian giữ khóa, phạm vi mạng và hệ thống sẽ hồi phục thế nào.

### 9.4. “Strong consistency” không đồng nghĩa 2PC ở mọi nơi

Một hệ thống có thể giữ invariant mạnh **trong mỗi owner** rồi dùng Saga để phối hợp xuyên context; read projection eventual. Mức nhất quán của toàn sản phẩm phải được phát biểu theo từng invariant và cam kết chứ không theo một nhãn duy nhất.

## 10. Phương án 4 — TCC: Try–Confirm–Cancel

TCC là mẫu giao dịch nghiệp vụ gồm:

1. **Try:** đặt giữ/đăng ký tài nguyên có thời hạn mà chưa chốt cuối.
2. **Confirm:** xác nhận sử dụng tài nguyên đã giữ.
3. **Cancel:** giải phóng/hoàn tác reservation nếu quy trình không hoàn tất.

Ví dụ đặt vé:

~~~text
Booking
   |-- Try SeatService.reserve(seat, bookingId, ttl)
   |<-- HOLD_CREATED
   |
   |-- Try PaymentService.authorize(amount, paymentId)
   |<-- AUTHORIZED
   |
   |-- Confirm SeatService.confirm(holdId)
   |-- Confirm PaymentService.capture(paymentId)
   |
   +--> Booking.CONFIRMED
~~~

Nếu không thể tiếp tục, Coordinator có thể gọi Cancel cho các reservation còn hợp lệ.

### 10.1. Khi TCC phù hợp

- Tài nguyên có trạng thái **đặt giữ tạm thời** riêng biệt.
- Có thể xác định TTL/expiry và thao tác hủy an toàn.
- Business owner chấp nhận có reservation làm giảm capacity trong một thời gian.
- Các participant đều có API Try/Confirm/Cancel rõ và idempotent.
- Có quy tắc xử lý việc Confirm một phần đã thành công, phần còn lại lỗi.

### 10.2. Đánh đổi UX

Người dùng có thể thấy:
- “Đã giữ chỗ trong 05:00 phút.”
- “Đang xác nhận thanh toán.”
- “Giữ chỗ đã hết hạn, vui lòng chọn lại.”
- “Đã xác nhận vé.”

Điều này phù hợp với booking hoặc checkout có giới hạn tồn kho, nhưng không được hứa “đã mua vé” chỉ khi còn HOLD_CREATED.

### 10.3. Những góc khó của TCC

- TTL hết hạn trong lúc Payment đang xử lý.
- Cancel đến trước Try do thông điệp bị trễ.
- Confirm được retry sau khi đã thành công.
- Một participant đã confirm nhưng participant khác thất bại.
- Reservation bị giữ quá lâu do coordinator chết.
- Có trường hợp cần hoàn tiền thực, không thể chỉ Cancel authorization.

**TCC không bảo đảm tự động toàn quy trình là ACID.** Nó tạo protocol nghiệp vụ rõ hơn, nhưng vẫn cần durable state, idempotency, timeout/recovery và reconciliation.

## 11. Phương án 5 — Saga: nhiều local transaction có thao tác bù

Saga là một chuỗi bước nghiệp vụ, mỗi bước commit tại service sở hữu, kèm hành vi bù/khắc phục khi một bước sau không thành công.

~~~text
T1: Create Order(PENDING)
         |
         v
T2: ReserveStock
         |
         v
T3: CapturePayment
         |
         v
T4: Confirm Order
~~~

Nếu T3 thất bại sau T2 thành công:

~~~text
Payment failed
    |
    v
Compensation: ReleaseStock
    |
    v
Order FAILED / CANCELLED
~~~

### 11.1. Saga không phải rollback ACID

Thao tác bù là **nghiệp vụ mới**. Hoàn tiền sau khi đã thu tiền có thể phát sinh giao dịch refund riêng, mất thời gian và phụ thuộc nhà cung cấp. Gửi email “đơn bị hủy” không thể xóa khỏi hộp thư khách email đã gửi trước đó.

Do đó, trạng thái sau compensation có thể là **tương đương nghiệp vụ** chứ không phải toàn bộ thế giới quay về đúng trạng thái trước giao dịch.

### 11.2. Saga orchestration

Một coordinator/process manager nắm quy trình:

~~~text
                  [Order Process Manager]
                     |      |       |
                     v      v       v
                 Inventory Payment Shipping
                  command   command  command
                     ^      ^       ^
                     +------ events-+
~~~

Ưu điểm:
- Dễ nhìn trạng thái toàn flow và người chịu trách nhiệm tiến độ.
- Dễ triển khai timeout, deadline, compensation và escalation.
- Theo dõi tiến trình từ một bản ghi workflow.

Đánh đổi:
- Cần durable state cho coordinator.
- Cần tránh coordinator trở thành nơi chứa business rule của các context.
- Vận hành thêm workflow engine hoặc process manager.
- Phải xử lý coordinator restart, duplicate events và migration của workflow đang chạy.

### 11.3. Saga choreography

Các service phản ứng với domain events:

~~~text
Ordering -- OrderPlaced -------> Inventory
Inventory -- StockReserved ----> Payment
Payment -- PaymentCaptured ----> Ordering
Ordering -- OrderConfirmed ----> Notification
~~~

Ưu điểm:
- Các context có thể phản ứng độc lập qua hợp đồng event.
- Producer không cần gọi từng consumer đồng bộ.
- Phù hợp các luồng không có một trung tâm điều phối duy nhất, nếu semantics rõ.

Đánh đổi:
- Business flow dễ phân tán qua nhiều consumer.
- Khó nhìn “ai đang giữ trạng thái tổng”.
- Có thể xuất hiện vòng lặp sự kiện, duplicate, missing event.
- Thay đổi workflow có thể buộc nhiều team phối hợp.

**Choreography không đồng nghĩa không có coupling.** Event schema, meaning, ordering và cách consumer phản ứng là coupling ở mức contract.

## 12. Mức nhất quán của Saga: hiểu chính xác

Trong Saga, mỗi service có thể giữ **ACID cục bộ**, nhưng toàn quy trình có **trạng thái trung gian quan sát được**.

~~~text
T0  Order created, status=PENDING
T1  Inventory reserved
T2  Payment pending
T3  Payment captured
T4  Order confirmed
T5  Analytics updated
~~~

Trong khoảng T1–T4, các service có trạng thái khác nhau và mọi phép đọc tổng hợp có thể thấy “một phần”. Cần quy định:

- Trạng thái chính thức của quy trình là gì?
- Màn hình nào được hiển thị trạng thái PENDING?
- Khi nào khách được tiếp tục hành động?
- Có được hủy một order đang thanh toán không?
- Nếu user đóng browser, workflow còn tiếp tục không?
- Làm sao xử lý timeout không xác định?
- Khi nào hệ thống hết thời gian chờ và cần bù/đối soát?

**Eventual consistency có ý nghĩa khi có quy tắc hội tụ, deadline và owner theo dõi các trường hợp không hội tụ.** Không được coi “cuối cùng sẽ đúng” là bảo đảm tự nhiên của broker.

## 13. Phương án 6 — Bất đồng bộ và projection cho UX phản hồi nhanh

Một số bước như gửi email, cập nhật analytics và tạo search index không nên nằm trên đường phản hồi checkout nếu chúng không ảnh hưởng quyết định mua thành công.

~~~text
POST /orders
     |
     v
Ordering commits Order + outbox
     |
     v
Response to browser

Outbox -> Event broker
            |-> Notification
            |-> Analytics
            +-> Search projection
~~~

Lợi ích: giảm latency cảm nhận của thao tác chính, giảm availability coupling với công việc phụ.

Đánh đổi: consumer có thể chậm, event trùng, projection không thấy dữ liệu ngay. Hãy phân biệt **latency đến ACK** với **latency hoàn thành nghiệp vụ**.

Nếu một bước bắt buộc như giữ hàng hoặc thanh toán được đưa sang async, Order phải có trạng thái PENDING rõ, không thể trả CONFIRMED chỉ vì message đã vào broker.

### 13.1. Read-after-write gap

~~~text
10:00:00 POST /orders -> 201 Created, orderId=O-101
10:00:00 GET /my-orders -> read projection chưa có O-101
10:00:01 Projection nhận OrderPlaced
10:00:01 GET /my-orders -> thấy O-101
~~~

Đây không phải bằng chứng tạo đơn thất bại. UI có thể:
- Hiển thị Order ID và trạng thái từ command response.
- Đọc authoritative status từ Ordering cho đơn vừa tạo.
- Dùng operationId/version token để poll khi projection còn chậm.
- Hiển thị “đang cập nhật” thay vì khuyến khích khách nhấn lại tạo đơn.

### 13.2. Async không phải luôn cho UX tốt hơn

Người dùng có thể thích chờ thêm 300 ms để biết chắc booking thành công hơn là nhận “đang xử lý” rồi phải theo dõi. Ngược lại, yêu cầu tạo báo cáo mất 30 giây nên nhận job ID và cập nhật sau. Cần thiết kế theo tâm lý và rủi ro của từng thao tác.

## 14. Mức nhất quán và kỳ vọng UX: ma trận quyết định

| Nhu cầu nghiệp vụ | Trạng thái nhất quán cần thiết | Trải nghiệm phù hợp | Phương án thường cân nhắc |
| --- | --- | --- | --- |
| Giữ một chỗ ngồi duy nhất | Atomic reservation tại seat owner | HOLD/EXPIRED/CONFIRMED rõ | Local transaction + TCC/Saga |
| Đặt một đơn hàng nhiều bước | Invariant cục bộ, workflow hội tụ | PENDING rồi xác nhận/thất bại | Saga orchestration hoặc choreography |
| Thu tiền một lần cho ý định thanh toán | Idempotency/ledger tại Payment owner | PROCESSING/PAID/UNKNOWN có tra cứu | Local payment transaction + workflow/reconciliation |
| Chuyển tiền nội bộ cùng một ledger | Bất biến số dư và bút toán đúng atomically | Kết quả chỉ sau commit chuẩn | Transaction cục bộ của ledger nếu cùng owner |
| Chuyển tiền liên hệ thống | Nhiều bên xử lý, thời gian liên thông | Đã tiếp nhận/đang xử lý/hoàn tất | Workflow state + reconciliation theo mạng thanh toán |
| Gửi email xác nhận | Không làm thay đổi thành công của đơn | Không chặn checkout | Outbox + async consumer |
| Dashboard doanh thu | Projection có thể stale nếu công bố | Hiển thị thời điểm cập nhật | Event-driven read model/batch |
| Tìm kiếm sản phẩm | Dữ liệu index có thể trễ | Kết quả gần realtime với lưu ý | Event-driven projection |
| Đổi mật khẩu/thu hồi quyền | Phạm vi bảo đảm bảo mật cụ thể, có thể cần cập nhật rất nhanh | Xác nhận theo owner và chiến lược vô hiệu hóa phiên | Transaction owner + policy propagation có giới hạn |
| Tạo PDF báo cáo | Không cần đồng bộ với transaction mua hàng | Job queued/progress/download | Queue/worker, query status |

Ma trận là hướng thảo luận, **không phải bảng quyết định cứng**. Ví dụ “đơn hàng” của một cửa hàng nhỏ có thể hoàn tất đồng bộ trong vài trăm mili giây; một sàn nhiều đối tác có thể phải duy trì PENDING lâu hơn.

## 15. Phân biệt độ nhất quán của dữ liệu với sự rõ ràng của UI

Một hệ thống có thể có internal eventual consistency nhưng UX vẫn minh bạch và đáng tin cậy nếu:
- Thông báo trạng thái chính xác.
- Có operationId để không mất dấu yêu cầu.
- Không buộc người dùng đoán có nên thử lại hay không.
- Có timeout UX và escalation khi quá thời gian bình thường.
- Có thông báo hoàn thành hoặc thất bại thật.
- Đảm bảo không nhân đôi side effect khi client retry.

Ngược lại, một hệ thống dùng nhiều RPC đồng bộ vẫn tạo UX kém nếu:
- Màn hình treo vô hạn.
- Timeout nhưng tiền đã bị trừ.
- Trả “thất bại” trong khi đơn đã được tạo.
- Không có ID để tra cứu.
- Không đưa ra bước tiếp theo khi một bên thứ ba xử lý chậm.

**Tính nhất quán kỹ thuật và sự chắc chắn mà người dùng cảm nhận có liên quan nhưng không phải cùng một thứ.**

## 16. Trạng thái nghiệp vụ cho workflow dài

Một state machine minh họa cho Order:

~~~text
                   +---------+
PlaceOrder ------> | PENDING |
                   +----+----+
                        |
           +------------+-------------+
           |                          |
        success                     failure
           |                          |
           v                          v
     +-----------+             +--------------+
     | CONFIRMED |             | COMPENSATING |
     +-----------+             +-------+------+
                                       |
                          +------------+-----------+
                          |                        |
                      complete               needs review
                          |                        |
                          v                        v
                      +--------+            +---------------+
                      | FAILED |            | MANUAL_REVIEW |
                      +--------+            +---------------+
~~~

Một hệ thống thực có thể cần thêm PAYMENT_PENDING, RESERVATION_HELD, CANCEL_REQUESTED, EXPIRED hoặc REFUND_PENDING. Không tạo quá nhiều trạng thái nếu UI và domain không cần, nhưng cũng không gom mọi trường hợp vào “FAILED” gây mất ý nghĩa.

### 16.1. Trạng thái UNKNOWN khác FAILED

Nếu Payment timeout, kết quả **unknown** cho đến khi có thông tin từ Payment. Không thể tự suy luận FAILED. Có thể giữ PAYMENT_PENDING, thực hiện truy vấn trạng thái theo paymentId hoặc chờ webhook/event có chữ ký đáng tin cậy.

### 16.2. Trạng thái COMPENSATING khác CANCELLED hoàn tất

Một saga đang giải phóng hàng hoặc hoàn tiền chưa thể hứa “mọi thứ đã trở lại như trước”. UI nên hiển thị “Đang xử lý hủy/hoàn tiền” và chỉ chuyển sang trạng thái cuối khi nhận được bằng chứng hoàn thành.

### 16.3. Người dùng có thể đóng trình duyệt

Workflow phân tán phải tiếp tục dựa vào **durable process state** chứ không dựa vào HTTP connection sống. Sau khi đăng nhập lại, người dùng tra được kết quả từ orderId/operationId.

## 17. Hợp đồng API phản hồi đúng mức cam kết

### 17.1. Chấp nhận để xử lý sau

~~~http
POST /api/orders
Idempotency-Key: place-order-123
Content-Type: application/json

{"customerId":"C-7","items":[{"sku":"SKU-1","quantity":2}]}
~~~

Response:

~~~http
HTTP/1.1 202 Accepted
Content-Type: application/json
Location: /api/order-operations/OP-123

{
  "operationId": "OP-123",
  "orderId": "O-123",
  "status": "PENDING",
  "statusUrl": "/api/order-operations/OP-123"
}
~~~

Đây là trường hợp hệ thống đã nhận một công việc bền vững để hoàn tất sau. Không dùng HTTP 202 nếu request thực ra bị bỏ hoặc chưa được lưu với trách nhiệm xử lý.

### 17.2. Resource đã được tạo

~~~http
HTTP/1.1 201 Created
Location: /api/orders/O-123
Content-Type: application/json

{
  "orderId": "O-123",
  "status": "CONFIRMED"
}
~~~

201 có nghĩa resource đã được tạo theo hợp đồng HTTP; thuộc tính CONFIRMED ở payload phải có **nghĩa nghiệp vụ được bảo đảm**. Một Order resource có thể được tạo PENDING và trả 201 nếu contract diễn đạt đúng rằng đã tạo tài nguyên Order, nhưng không được đánh đồng tạo tài nguyên với hoàn tất thanh toán.

### 17.3. Truy vấn tiến độ

~~~http
GET /api/order-operations/OP-123
~~~

Response:

~~~json
{
  "operationId": "OP-123",
  "orderId": "O-123",
  "status": "PAYMENT_PENDING",
  "updatedAt": "2026-11-12T08:05:10Z",
  "canCancel": true
}
~~~

Không đưa mọi chi tiết internal state hoặc thông tin nhạy cảm vào public API. Trạng thái gửi tới UI phải ổn định, có contract rõ, không rò rỉ thông tin thanh toán.

### 17.4. Không bảo đảm “retry lại là an toàn” chỉ từ HTTP method

POST có thể được thiết kế idempotent bằng idempotency key ở owner, nhưng không tự idempotent chỉ vì client dùng cùng payload. Một request timeout có thể đã tạo resource hoặc side effect.

## 18. Bảng UX theo tình huống lỗi

| Tình huống | Trạng thái nội bộ | Thông điệp UI phù hợp | Hành động hệ thống |
| --- | --- | --- | --- |
| Đã nhận lệnh bền vững | PENDING | “Đã nhận yêu cầu, đang xử lý” | Trả operationId; tiếp tục workflow |
| Inventory từ chối thật | OUT_OF_STOCK | “Sản phẩm đã hết hàng” | Kết thúc/điều chỉnh đơn, không thu tiền |
| Payment provider timeout | PAYMENT_UNKNOWN/PENDING | “Đang xác minh thanh toán, chưa thực hiện lại” | Tra status theo idempotency key/reconciliation |
| Đã thu tiền nhưng chưa giữ được chỗ | COMPENSATING | “Đang xử lý hoàn tiền hoặc hỗ trợ” | Trigger refund/compensation; theo dõi |
| Mọi điều kiện hoàn tất | CONFIRMED | “Đơn đã được xác nhận” | Công bố event và gửi thông báo |
| Workflow thất bại và bù đã xong | FAILED/CANCELLED | “Không hoàn tất, khoản giữ đã được giải phóng” | Lưu audit state, cho phép tạo lệnh mới khi phù hợp |
| Read projection chậm | Source confirmed, projection lag | “Thông tin đang cập nhật” | Read authoritative hoặc chờ projection |
| Manual review | MANUAL_REVIEW | “Cần thêm thời gian xác minh” | Hàng đợi xử lý và escalation SLA |

Một UX có trách nhiệm luôn phân biệt **chưa biết kết quả**, **chưa hoàn tất**, **đã thất bại** và **đã hoàn tất**.

## 19. Case study A — Checkout thương mại điện tử

### 19.1. Mục tiêu

Khách đặt 2 sản phẩm, số lượng hạn chế. Hệ thống phải tránh overselling, tránh charge trùng và không tạo đơn đã CONFIRMED khi chưa đủ điều kiện.

### 19.2. Thiết kế một workflow minh họa

~~~text
Browser POST /orders (idempotencyKey)
        |
        v
Ordering: save Order(PENDING) + outbox command
        |
        v
Process Manager
  |-- ReserveStock(commandId, sku, quantity) -> Inventory
  |<-- StockReserved / StockRejected
  |
  |-- CapturePayment(paymentId, amount) ----> Payment
  |<-- PaymentCaptured / PaymentFailed
  |
  +-- Confirm Order / Compensate -> Ordering
                                   |
                                   v
                            OrderConfirmed/Failed
                                   |
                              Projection/Email
~~~

Inventory bảo vệ bất biến stock trong transaction của Inventory; Payment bảo vệ transaction và idempotency tại Payment; Ordering giữ state machine và điều phối nghiệp vụ.

### 19.3. Khi Inventory từ chối

Nếu không đủ hàng, process manager đặt Order FAILED/REJECTED theo contract, không bắt đầu thu tiền. UI hiển thị chính xác hết hàng và có thể cho khách cập nhật số lượng.

### 19.4. Khi Payment timeout

Không tự tạo payment request mới với paymentId khác. Truy vấn trạng thái với operation ID đã có, chờ event/webhook đáng tin và đối soát nếu cần.

### 19.5. Khi Payment thành công nhưng Order update lỗi

PaymentCaptured là business fact cần được ghi nhận bền vững. Process manager retry idempotent update Order và sau khi thành công mới công bố OrderConfirmed. Nếu retry kéo dài, hệ thống cần alert và manual escalation; UI có thể ở trạng thái PROCESSING/VERIFYING.

### 19.6. Khi Payment thất bại sau reservation

Có thể ReleaseStock với reservationId ổn định. Nếu ReleaseStock timeout, phải tra status/retry an toàn. Không tuyên bố “đã giải phóng hàng” trước khi có bằng chứng phù hợp.

### 19.7. Có nên giữ HTTP request chờ tất cả bước?

Nếu mọi bước rất nhanh, người dùng có thể đợi và nhận CONFIRMED trong một request. Nhưng yêu cầu này cần SLO và failure semantics rõ. Với Payment chậm/không chắc chắn, trả operationId và trạng thái PENDING thường trung thực hơn, miễn UX hỗ trợ theo dõi.

## 20. Case study B — Đặt vé và giữ chỗ (TCC)

Với một chỗ ngồi duy nhất, cần ngăn hai khách cùng có booking CONFIRMED.

~~~text
1. SeatService.TryHold(seatId, bookingId, expiresAt)
2. PaymentService.Authorize(paymentId)
3. SeatService.ConfirmHold(holdId)
4. PaymentService.Capture(paymentId)
5. Booking.CONFIRMED
~~~

Đây là **một luồng minh họa**, không bảo đảm mọi nhà cung cấp payment đều hỗ trợ authorize/capture hoặc các bước này luôn phải ở thứ tự đó. Thiết kế thực tế phải xác định một thời điểm commit nghiệp vụ và xử lý failure giữa từng bước.

### 20.1. UX giữ chỗ

Có thể hiển thị:
- “Ghế được giữ trong 04:59 phút”.
- “Đang xác minh thanh toán”.
- “Đã xác nhận booking”.
- “Thời gian giữ chỗ đã hết; khoản tiền chưa được thu hoặc đang được hoàn theo trạng thái thực tế”.

Không hứa booking confirmed chỉ khi TryHold trả thành công.

### 20.2. Điều gì xảy ra khi khách rời trang?

TTL phải do seat owner xử lý bền vững. Khi hết hạn, reservation có thể chuyển EXPIRED và slot được giải phóng theo policy, dù browser đã đóng. UI reconnect phải đọc trạng thái thật, không dựa vào bộ đếm thời gian phía client làm nguồn sự thật.

### 20.3. Trường hợp khó: Payment đã capture nhưng hold hết hạn

Cần workflow điều tra/hoàn tiền hoặc tái cấp chỗ theo chính sách, với SLA và thông báo. Đây là lý do TCC vẫn cần compensation, idempotency, deadline và recovery.

## 21. Case study C — Chuyển tiền và sổ cái

Tình huống tài chính cần phân biệt hai phạm vi:

### 21.1. Chuyển giữa hai tài khoản trong cùng một ledger owner

Nếu hệ thống sổ cái sở hữu cả debit và credit, và ràng buộc kế toán cần commit nguyên tử trong một database có khả năng, **một local transaction** thường được ưu tiên hơn tách debit/credit thành hai microservice rồi dùng Saga.

~~~text
Ledger transfer command
       |
       v
One local transaction:
  validate transfer
  record debit entry
  record credit entry
  enforce balancing constraints
  commit
       |
       v
Transfer accepted/committed
~~~

Ví dụ này giả định các nghiệp vụ và account đều do cùng ledger owner quản lý. Cần kiểm soát concurrency, overdraft, uniqueness, audit và reconciliation đúng yêu cầu; không thể suy luận điều đó chỉ từ cú pháp BEGIN/COMMIT.

### 21.2. Chuyển qua hệ thống liên ngân hàng hoặc đối tác

Khi tiền phải đi qua hệ thống không nằm trong cùng transaction boundary, không thể dùng @Transactional hoặc 2PC với một API ngoài nếu nó không là participant. Cần trạng thái như SUBMITTED/PROCESSING/SETTLED/FAILED/RETURNED và cơ chế reconciliation, thông báo/truy vấn trạng thái chuẩn của mạng thanh toán.

Không nên dùng eventual consistency như lý do để hiển thị số dư khả dụng sai hoặc vượt kiểm soát số dư. Bất biến trong ledger vẫn phải được giữ cục bộ.

### 21.3. UX của tiền tệ cần nghiêm ngặt

- Người dùng phải có mã giao dịch ổn định.
- Không khuyến khích tạo giao dịch mới khi timeout.
- Cần tách trạng thái gửi lệnh và trạng thái quyết toán.
- Khi unknown outcome, thông báo “đang xác minh” thay vì “thất bại” hoặc “thành công” không có căn cứ.
- Refund/reversal là giao dịch nghiệp vụ riêng, cần audit trail.

## 22. Case study D — Báo cáo và read projection

Một dashboard doanh thu cập nhật từ PaymentCaptured và RefundCompleted events. UI chấp nhận trễ 10 giây, có nhãn “Cập nhật lần cuối”.

~~~text
Payment Write DB
   |
   +-- outbox -> broker -> Analytics projection
                                   |
                                   v
                              Read DB/cache
                                   |
                                   v
                               Dashboard
~~~

Ở đây mục tiêu không phải global transaction, mà là **dữ liệu đọc hội tụ có kiểm soát**. Cần dedup event, xử lý out-of-order và đối soát với nguồn chính thức. Nếu consumer lag 2 phút, UI không nên vẫn ghi “doanh thu thời gian thực”.

Khi người quản trị quyết định hoàn tiền, command phải đi tới Payment owner, không được sửa số liệu trong dashboard để coi là đã hoàn tất.

## 23. Điều kiện khiến mỗi phương án nên hoặc không nên được chọn

### 23.1. Một local transaction phù hợp khi

- Các bất biến liên quan thuộc cùng bounded context/owner.
- Có thể commit atomically trong một DB hoặc tài nguyên giao dịch thống nhất.
- User cần kết quả ngay theo phạm vi đó.
- Không có side effect external bất khả đảo nằm trong transaction.

Không phù hợp để “ôm” mọi tính năng của doanh nghiệp vào một database chỉ để tránh workflow.

### 23.2. RPC đồng bộ phù hợp khi

- Cần câu trả lời trực tiếp, ít downstream dependency, latency trong SLO.
- Có idempotency và handling unknown outcome.
- Các failure/compensation được thiết kế rõ.
- Không giả định RPC chain là một transaction nguyên tử.

Cần tránh chuỗi dài gây tail latency và availability coupling cao.

### 23.3. 2PC phù hợp khi

- Tất cả participant thực sự hỗ trợ global transaction và recovery.
- Atomic commit xuyên các resource là yêu cầu có căn cứ.
- Hệ thống chịu được lock/blocking/latency và vận hành coordinator.
- Các tác dụng bên ngoài không thuộc XA được xử lý riêng.

Không phù hợp nếu một participant là HTTP payment provider không hỗ trợ prepare/commit.

### 23.4. TCC phù hợp khi

- Resource có thể giữ trước, xác nhận hoặc hủy.
- Có TTL và khả năng recover holds.
- Mỗi participant có Try/Confirm/Cancel hợp đồng rõ.
- Đội ngũ quản trị được reservation leak, timeout và partial confirmation.

Không phù hợp nếu thao tác không thể giữ/hoàn tác, hoặc việc tạo holds gây chi phí quá lớn.

### 23.5. Saga phù hợp khi

- Workflow gồm nhiều local transactions ở các owner khác nhau.
- Có trạng thái trung gian rõ và hành vi bù/khắc phục.
- Có durable coordinator hoặc event contracts đủ tin cậy.
- Business chấp nhận hoàn tất sau và thời gian hội tụ cụ thể.

Không phù hợp nếu mọi thứ bắt buộc phải atomically đổi trạng thái ngay và không thể có intermediate state hoặc compensation có ý nghĩa.

### 23.6. Event-driven projection phù hợp khi

- Query/read có thể stale trong thời gian được công bố.
- Nhiều consumer cần phản ứng độc lập sau commit.
- Muốn giảm synchronous fan-out cho dashboard/search.
- Có event delivery, replay, dedup và reconciliation đáng tin.

Không dùng projection stale để quyết định một invariant như số dư khả dụng hoặc stock reservation.

## 24. Reliability primitives thường cần bất kể phương án

### 24.1. Idempotency

Một thao tác ghi lặp lại với cùng ý định phải không tạo hiệu ứng nghiệp vụ trùng. Ví dụ Payment giữ idempotencyKey và kết quả xử lý trong store có transaction/unique constraint phù hợp.

Giữ nguyên khóa qua retry, kể cả retry sau timeout, rollback deployment hay webhook gửi lại. Không tạo khóa mới cho cùng một payment chỉ để “chắc chắn được xử lý”.

### 24.2. Transactional outbox

Ghi trạng thái và outbox event trong cùng local transaction; một publisher phát event ra broker và có thể phát trùng. Consumer cần idempotency.

Không giải quyết tự động transaction xuyên những database consumer hoặc một external payment API.

### 24.3. Inbox/deduplication

Consumer lưu eventId/commandId đã xử lý và dùng unique constraint hoặc transaction cục bộ để ngăn lặp hiệu ứng. Nếu ACK mất sau commit, event có thể được giao lại; consumer an toàn khi xử lý lại.

### 24.4. Retry có giới hạn

Retry lỗi tạm thời với backoff/jitter và deadline; không retry business rejection vĩnh viễn. Nếu app, mesh và gateway cùng retry, tải có thể nhân bội, nhất là khi downstream đang quá tải.

### 24.5. Timeout và unknown outcome

Timeout nói **caller không nhận được kết quả đúng hạn**. Nó không khẳng định transaction phía nhận chưa commit. Cần query result, event/webhook có chứng thực hoặc reconciliation.

### 24.6. Dead-letter handling và manual review

Nếu message mãi không xử lý được, DLQ cần alert và quy trình khôi phục. Đưa vào DLQ không có nghĩa đã hoàn tất Saga hoặc hoàn tiền. Có những trường hợp phải chuyển MANUAL_REVIEW với owner và thời hạn xử lý rõ.

### 24.7. Reconciliation

Đối soát các record/transaction giữa các owner theo contract: số tiền đã captured, reservation đang held, Order state, refund status. Đối soát phát hiện sai lệch mà metrics transport không thấy.

### 24.8. Observability

Cần trace/correlationId, operationId, commandId, eventId và step state. Metrics nên bao gồm workflow duration p95/p99, stuck-PENDING count, retry count, compensation failure rate, backlog, reconciliation mismatches và business outcomes.

## 25. Spring Boot: biểu diễn state machine đơn giản

Một mô hình Order state có thể viết như sau:

~~~java
package example.ordering.domain;

public enum OrderStatus {
    PENDING,
    RESERVATION_HELD,
    PAYMENT_PENDING,
    CONFIRMED,
    COMPENSATING,
    FAILED,
    MANUAL_REVIEW
}
~~~

Command DTO có định danh ổn định:

~~~java
package example.ordering.application;

import java.util.UUID;

public record PlaceOrderCommand(
        UUID customerId,
        String idempotencyKey,
        String sku,
        int quantity) {}

public record PlaceOrderResult(
        UUID orderId,
        OrderStatus status,
        UUID operationId) {}
~~~

Một handler minh họa:

~~~java
package example.ordering.application;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class PlaceOrderHandler {
    private final OrderRepository orders;
    private final OutboxRepository outbox;
    private final IdempotencyStore idempotency;

    public PlaceOrderHandler(
            OrderRepository orders,
            OutboxRepository outbox,
            IdempotencyStore idempotency) {
        this.orders = orders;
        this.outbox = outbox;
        this.idempotency = idempotency;
    }

    @Transactional
    public PlaceOrderResult handle(PlaceOrderCommand command) {
        // Phải dùng UNIQUE key/transaction để chống race condition;
        // đoạn code mô tả kiến trúc, chưa đủ cho production.
        var previous = idempotency.findResult(command.idempotencyKey());
        if (previous.isPresent()) {
            return previous.get();
        }

        var order = Order.createPending(
                command.customerId(), command.sku(), command.quantity());

        orders.save(order);
        outbox.save(OrderPlacedEvent.from(order));

        var result = new PlaceOrderResult(
                order.id(), OrderStatus.PENDING, order.operationId());
        idempotency.store(command.idempotencyKey(), result);
        return result;
    }
}
~~~

Đây là **mã khái niệm** với một số interface/domain type cần được định nghĩa trong ứng dụng thật. Chỉ kiểm tra findResult rồi storeResult mà không có ràng buộc nguyên tử **không đủ chống hai request đồng thời**; production cần unique constraint, lock hoặc insert-if-absent atomic và xử lý conflict.

### 25.1. @Transactional bao phủ điều gì?

Annotation @Transactional thường quản lý transaction trong một tài nguyên cục bộ do Spring transaction manager cấu hình. Không viết:

~~~java
@Transactional
public void placeAndCharge() {
    orderRepository.save(order);
    paymentHttpClient.capture(paymentId); // external side effect
}
~~~

rồi tưởng rollback Order cũng rollback Payment. Payment có thể đã commit ở hệ thống riêng. Cần workflow + idempotency + compensation/reconciliation.

## 26. Process Manager/Saga orchestration: mô tả bằng pseudocode

~~~text
on OrderPlaced(event):
    load durable orderProcess(event.orderId)
    if step not completed:
        send ReserveStock with stable commandId
        persist step RESERVATION_REQUESTED

on StockReserved(event):
    deduplicate eventId
    persist reservationId and step RESERVED
    send CapturePayment with stable paymentId
    persist step PAYMENT_REQUESTED

on PaymentCaptured(event):
    deduplicate eventId
    persist paymentId and step PAID
    command Ordering.ConfirmOrder
    persist workflow completion when confirmed

on PaymentFailed(event):
    deduplicate eventId
    send ReleaseStock(reservationId) idempotently
    persist COMPENSATING until release confirmed

on timeout:
    do NOT guess success/failure
    query owner by stable operationId
    retry safely or escalate to reconciliation
~~~

**Không gửi command rồi chỉ giữ trạng thái step trong RAM.** Process manager cần một cơ chế bền vững để tránh mất tiến độ khi restart. Nếu bước persist và bước gửi message cần liên kết, có thể dùng outbox. Cần giải quyết duplicate transition, concurrency và ordering theo aggregate/operationId.

### 26.1. Coordinator không nên sở hữu mọi business rule

Process Manager quyết định trình tự và xử lý trạng thái workflow. Inventory vẫn quyết định có giữ hàng được không; Payment vẫn quyết định trạng thái thanh toán. Không chuyển ownership sang coordinator để tiện gọi.

### 26.2. Choreography cần correlation rõ

Nếu chọn choreography, các event phải có correlationId/causationId, eventId, aggregateId, schema version và nghĩa nghiệp vụ ổn định. Thiếu các trường này, rất khó nối một StockReserved với đúng OrderPlaced, đặc biệt khi retry.

## 27. Spring Boot: ví dụ API trạng thái không đánh lừa người dùng

Một endpoint có thể trả 202 cho workflow đang xử lý:

~~~java
package example.ordering.api;

import java.net.URI;
import java.util.UUID;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/orders")
public class OrderCommandController {
    private final PlaceOrderHandler handler;

    public OrderCommandController(PlaceOrderHandler handler) {
        this.handler = handler;
    }

    @PostMapping
    public ResponseEntity<PlaceOrderResult> place(
            @RequestHeader("Idempotency-Key") String key,
            @RequestBody PlaceOrderRequest body) {
        var result = handler.handle(
                new PlaceOrderCommand(
                        body.customerId(), key, body.sku(), body.quantity()));

        URI statusUri = URI.create(
                "/api/order-operations/" + result.operationId());

        return ResponseEntity.accepted()
                .location(statusUri)
                .body(result);
    }
}

record PlaceOrderRequest(UUID customerId, String sku, int quantity) {}
~~~

Điểm cần lưu ý:
- Idempotency-Key phải được lưu và enforcement thật, không chỉ đọc header.
- customerId không nên là nguồn xác thực duy nhất nếu nghiệp vụ “đặt cho tôi”; dùng authenticated principal/tenant context.
- 202 chỉ hợp lệ khi request đã được tiếp nhận và có tiến độ bền vững.
- Khi operation hoàn tất, GET status endpoint phải trả kết quả đáng tin cậy.
- Khi một số bước thất bại, không tự động đổi toàn bộ Order sang FAILED nếu cần compensation/manual review.

## 28. Xử lý retry và timeout từ góc nhìn người dùng

### 28.1. Client timeout sau khi server đã tạo Order

Người dùng thấy spinner lâu, kết nối mất. Nếu client POST lại với idempotencyKey mới, có thể tạo đơn trùng.

Hướng thiết kế:
- Idempotency key được sinh cho **một ý định đặt hàng**, giữ qua retry.
- Backend lưu mapping key → operation/order result có thời hạn phù hợp.
- Client có thể GET operation status với operationId hoặc dùng lại key.
- Khi không có kết quả cuối, UI nói “đang kiểm tra” thay vì “thất bại”.
- Chỉ cho phép “đặt đơn mới” khi user thực sự xác nhận ý định mới.

### 28.2. Payment timeout

Không hiển thị “chưa trừ tiền” khi chưa kiểm chứng. Có thể ghi:
- “Chúng tôi đang xác minh tình trạng thanh toán của giao dịch này.”
- “Không cần thanh toán lại ngay lúc này.”
- “Bạn có thể theo dõi kết quả bằng mã giao dịch.”

Không đưa ra lời hứa thời gian cố định nếu hệ thống không có SLA đo được.

### 28.3. Compensation mất thời gian

Nếu tiền đã capture và refund đang xử lý, UI cần hai trạng thái riêng:
- Giao dịch thanh toán đã thu.
- Yêu cầu hoàn tiền đang xử lý.

Không có transaction đảo ngược thời gian; một refund thành công có thể hiện lên sao kê sau một thời gian do hệ thống bên ngoài.

## 29. Những hiểu nhầm thường gặp

**“Dùng 2PC thì UX chắc chắn tốt nhất.”**  
Atomic commit không đồng nghĩa độ trễ thấp hay availability cao. 2PC có thể giữ lock, block khi participant/coordinator lỗi và không áp dụng với API ngoài XA.

**“Dùng Saga thì cuối cùng mọi thứ tự rollback.”**  
Compensation là nghiệp vụ riêng có thể thất bại hoặc không thể đảo hoàn toàn. Cần state, retry, reconciliation và xử lý thủ công khi cần.

**“HTTP 200 nghĩa mọi service đã commit.”**  
Response của một API chỉ có ý nghĩa theo contract của nó. Không tự bao phủ transaction của tất cả downstream.

**“Timeout nghĩa là chưa thu tiền.”**  
Timeout chỉ nói caller không nhận được phản hồi. Phải xác minh theo ID ổn định.

**“Eventual consistency nghĩa dữ liệu có thể sai vô thời hạn.”**  
Nếu không có monitoring/recovery, đó là hệ thống không kiểm soát tính đúng, không phải thiết kế eventual consistency tốt. Phải có giới hạn kỳ vọng và cơ chế hội tụ.

**“Message queue đem lại exactly-once toàn workflow.”**  
Delivery semantics của broker không tự bao phủ database hoặc payment provider ngoài broker. Idempotency business effect vẫn cần.

**“TCC luôn tốt hơn Saga.”**  
TCC đòi mọi participant có thể Try/Confirm/Cancel và quản lý holds; nhiều quy trình không hỗ trợ. Saga linh hoạt hơn ở một số workflow nhưng compensation có giới hạn.

**“Mọi bước phải chờ người dùng.”**  
Email và analytics thường có thể bất đồng bộ nếu không quyết định kết quả checkout. Chỉ giữ bước bắt buộc trên critical path.

**“Trả 202 là đã giải quyết latency.”**  
Giảm thời gian ACK không làm giảm thời gian hoàn tất hoặc rủi ro xử lý nền. UX phải có tracking/status và escalation.

**“Read projection có thể quyết định thanh toán/tồn kho.”**  
Projection có thể stale. Quyết định ghi phải đến owner của invariant.

**“Chia nhỏ service càng nhiều càng nhất quán.”**  
Cắt một invariant qua nhiều service có thể tạo distributed transaction khó hơn. Boundary phải theo năng lực nghiệp vụ và data ownership.

## 30. Cách đưa quyết định vào ADR

Một Architecture Decision Record cho workflow phân tán nên ghi:

~~~text
Title: Checkout cross-service consistency approach

Business promise:
  - Khách nhận Order ID ngay sau tiếp nhận bền vững.
  - Chỉ hiển thị CONFIRMED khi stock reserved và payment captured.
  - Khi chưa biết payment result, không khuyến khích thanh toán lại.

Invariants and owners:
  - Inventory: no overselling, reservation atomic.
  - Payment: idempotent capture per payment intent.
  - Ordering: valid Order state transitions.

Options evaluated:
  - Synchronous RPC chain
  - 2PC (not applicable to external payment)
  - TCC (where reserve/authorize operations exist)
  - Saga orchestration
  - Saga choreography

Choice:
  - Durable saga orchestration + local transactions + outbox/inbox.

Consistency:
  - Strong invariants within owners.
  - Workflow PENDING between steps.
  - Order read projection eventual; authoritative status endpoint available.

UX:
  - HTTP 202 + operationId.
  - Polling/SSE for progress, reconnect to GET status.
  - Distinguish payment unknown, compensating, failed, confirmed.

Recovery:
  - Stable operation/command IDs, idempotency, retry, reconciliation.
  - Timeouts, compensation policy and manual-review escalation.

Metrics:
  - Workflow p95 completion time, stuck PENDING age,
    compensation failures, duplicate attempts and mismatches.

Rollback / deployment:
  - Version-compatible contracts and durable state migration.
~~~

ADR cần giải thích vì sao các phương án khác không phù hợp với use case, không chỉ ghi tên công nghệ đã chọn.

## 31. Quy trình ra quyết định theo mức nhất quán và UX

### Bước 1 — Viết rõ business invariants

Liệt kê những điều không được sai, owner và transaction boundary. Nếu một invariant nằm tại một owner, giữ nó trong local transaction càng nhiều càng tốt.

### Bước 2 — Xác định trạng thái mà người dùng chấp nhận

Có thể hiển thị PENDING 5 giây không? Có cho phép giữ chỗ 5 phút không? Có cần phản hồi ngay trong 300 ms không? Không phải mọi nghiệp vụ đều cần UX “thành công tức thì”.

### Bước 3 — Liệt kê resource/participant thực

Database nào, service nào, bên thứ ba nào? Có participant hỗ trợ 2PC/XA không? Có API authorize/capture hoặc reservation TTL không? Nếu không có, đừng chọn cơ chế dựa vào khả năng không tồn tại.

### Bước 4 — Thiết kế đường thành công và đường lỗi

Vẽ từng bước, các failure window, compensation và unknown outcome. Ai lưu durable progress và ai biết trạng thái cuối cùng?

### Bước 5 — Chọn cơ chế tối thiểu phù hợp

Local transaction nếu đủ. RPC đồng bộ nếu ngắn và kết quả ngay là bắt buộc. TCC nếu tài nguyên có reservation tự nhiên. Saga nếu phối hợp nhiều local transactions. 2PC chỉ khi tài nguyên thực sự hỗ trợ và atomic commit toàn phạm vi đáng giá. Read projection async khi chủ yếu là nhu cầu đọc.

### Bước 6 — Tạo UX contract

Trạng thái, status endpoint, operationId, retry button, cancellation policy, thông báo khi lỗi và khi hoàn tất. Phân biệt “đã nhận”, “đang xử lý”, “không xác định”, “đã xác nhận” và “đã bù xong”.

### Bước 7 — Thử lỗi và đối soát

Mô phỏng timeout sau khi commit, event trùng, mất ACK, process restart, participant unavailable, retry storm, compensation failure và replay. Đo kết quả thực, không chỉ happy path.

### Bước 8 — Vận hành theo business SLO

Theo dõi thời gian hoàn tất workflow, số giao dịch treo, tỷ lệ bù trừ, pending quá hạn, reconciliation mismatch và phản ánh khiếu nại người dùng.

## 32. Bài tập tình huống

### Bài 1 — Có nên dùng 2PC cho checkout?

Ordering dùng PostgreSQL, Inventory dùng PostgreSQL, Payment là nhà cung cấp API bên ngoài không hỗ trợ prepare/commit. Một nhóm đề xuất 2PC cho cả ba.

**Gợi ý:** Không thể bao phủ Payment bằng XA nếu provider không tham gia. Cần local transaction ở mỗi owner, workflow state, idempotency, compensation/reconciliation; có thể dùng Saga/TCC nếu hợp đồng payment hỗ trợ authorize/capture.

### Bài 2 — Khi nào một transaction local tốt hơn Saga?

Một ledger service sở hữu cả hai tài khoản nội bộ và phải ghi debit/credit cân bằng. Có cần tách thành hai microservice và Saga để “đúng microservices”?

**Gợi ý:** Không. Một local transaction trong owner phù hợp giúp bảo vệ invariant. Tách một bất biến qua service boundary chỉ để tăng phân tán có thể làm tính đúng phức tạp hơn.

### Bài 3 — Payment timeout

Payment đã capture thành công nhưng response mất. Ordering đánh dấu FAILED và khách thử lại bằng id mới. Rủi ro gì?

**Gợi ý:** Charge hai lần và trạng thái Order lệch. Giữ paymentId/idempotencyKey, query status, đợi event/webhook có xác minh, xử lý reconciliation; UI hiển thị verifying/unknown thay vì failed chắc chắn.

### Bài 4 — Reservation hết hạn khi đang thanh toán

SeatService TryHold 5 phút, Payment processing 6 phút, booking confirm sau timeout.

**Gợi ý:** Không được CONFIRM một hold đã EXPIRED. Cần deadline/TTL phù hợp, quy tắc gia hạn nếu được phép, điều phối và compensation/refund nếu đã thu tiền nhưng không còn chỗ.

### Bài 5 — Đơn PENDING quá lâu

Một Saga tạo đơn PENDING rồi message StockReserved bị kẹt DLQ. Hệ thống chờ vô hạn.

**Gợi ý:** DLQ không phải kết thúc workflow. Cần alert, timeout SLA, replay an toàn, query source owner, compensation hoặc manual review. UI phải cho người dùng biết tiến độ/thất bại.

### Bài 6 — Email lỗi sau Order CONFIRMED

Email provider trả 500 sau khi Order đã xác nhận. Có nên rollback Order và báo checkout thất bại?

**Gợi ý:** Nếu email không phải điều kiện tạo đơn, không. Dùng outbox/event + notification consumer retry, giữ Order confirmed và theo dõi trạng thái gửi mail riêng.

### Bài 7 — Saga compensation không hoàn toàn đảo ngược

Booking đã gửi email xác nhận và charge thành công, nhưng cuối cùng không có chỗ. Hoàn tiền xong có nghĩa mọi thứ y như chưa từng diễn ra?

**Gợi ý:** Không. Email đã gửi, customer trust, phí giao dịch và thời gian refund là hệ quả không đảo ngược. Cần communication và quy trình chăm sóc khách, không coi compensation tương đương rollback ACID.

### Bài 8 — Dashboard stale

Analytics projection trễ 30 giây trong khi doanh số thay đổi. Có nên cho dashboard dùng projection không?

**Gợi ý:** Tùy yêu cầu. Nếu chấp nhận stale 30 giây, hiển thị update timestamp và giám sát lag. Nếu cần số chốt quyết toán, phải có nguồn chính thức/reconciliation và contract báo cáo rõ.

### Bài 9 — Saga choreography quá phức tạp

Sáu service phản ứng qua events và không ai biết một order đã hoàn tất hay chưa. Hướng xử lý?

**Gợi ý:** Đưa correlationId/causationId, event contracts và observability; cân nhắc process manager/orchestration cho workflow có trách nhiệm rõ. Không chỉ thêm một event mới để che coupling.

### Bài 10 — UX phản hồi nhanh nhưng sai

Frontend trả “Thanh toán thành công!” ngay sau broker ACK, Payment chưa xử lý. Người dùng thoát và Payment thất bại.

**Gợi ý:** Broker ACK khác captured. Trả PENDING/processing và đường theo dõi; chỉ nói thành công khi có business fact từ Payment owner.

### Bài 11 — Đặt hàng hai lần do retry

Client POST /orders, server lưu đơn rồi timeout. Client tự POST lại. Làm sao bảo vệ?

**Gợi ý:** Idempotency key ổn định qua retry, uniqueness tại Ordering, trả lại result của cùng operationId/orderId. Nếu người dùng thật sự muốn đơn thứ hai, đó là ý định mới với key mới.

### Bài 12 — Chọn sync hay async cho một bước

Pricing trả quote trong 50 ms, Inventory trong 80 ms, Payment có đuôi p99 10 giây. Product cho phép trang “Đang xác minh”.

**Gợi ý:** Có thể giữ quote/validation cần tức thời, tạo Order PENDING và xử lý Payment với durable workflow, timeout và status update. Không nhất thiết giữ HTTP connection 10 giây. Nhưng cần chính sách khi user hủy hoặc trả tiền thành công sau khi màn hình hết chờ.

### Bài 13 — Có thể dùng read model để reserve stock?

Inventory read projection báo còn 5, hai khách đồng thời đặt mỗi người 4 sản phẩm. Có thể CONFIRMED cả hai không?

**Gợi ý:** Không. Inventory owner phải kiểm tra và ghi reservation atomically. Read projection chỉ là dữ liệu hiển thị/ước lượng theo freshness contract.

### Bài 14 — 2PC làm request treo

Một participant đã prepare, coordinator mất kết nối. Lock giữ lâu, API timeout. Điều này thể hiện đánh đổi gì?

**Gợi ý:** Atomic commit protocol có blocking/recovery complexity; không mặc định là giải pháp availability hoặc latency tốt. Cần coordinator recovery và đánh giá thời gian giữ tài nguyên.

### Bài 15 — Compensation thất bại

PaymentCaptured đã xảy ra, Inventory reservation được giải phóng, nhưng RefundPayment từ chối vì API đối tác lỗi.

**Gợi ý:** Không tự đánh dấu “đã hoàn tiền”. Giữ REFUND_PENDING/MANUAL_REVIEW, retry theo idempotency, đối soát và hỗ trợ khách theo SLA. Refund là một giao dịch mới có trạng thái riêng.

## 33. Checklist thiết kế giao dịch phân tán

### Bất biến và mô hình trạng thái
- [ ] Đã nêu rõ mỗi business invariant và service owner.
- [ ] Có thể gom bất biến thành local transaction hợp lý không?
- [ ] Đã phân biệt local ACID với workflow consistency và read projection?
- [ ] Có state machine với PENDING, CONFIRMED, FAILED, UNKNOWN/COMPENSATING khi cần?
- [ ] Có định nghĩa đúng điều kiện chuyển mỗi trạng thái?

### Lựa chọn cơ chế
- [ ] Đã so sánh RPC sync, 2PC, TCC, Saga, async projection theo yêu cầu?
- [ ] Nếu chọn 2PC, mọi resource có hỗ trợ global transaction và recovery?
- [ ] Nếu chọn TCC, có Try/Confirm/Cancel, TTL và idempotency?
- [ ] Nếu chọn Saga, có compensation thực, durable progress và owner điều phối?
- [ ] Nếu chọn choreography, có sự kiện rõ nghĩa, correlation và observability?

### Reliability và consistency
- [ ] IdempotencyKey/operationId ổn định qua retry và rollout.
- [ ] Timeout được xử lý như unknown outcome khi phù hợp.
- [ ] Có outbox/inbox và event dedup nếu sử dụng messaging.
- [ ] Có xử lý out-of-order, message trùng, mất ACK và consumer restart.
- [ ] Có deadline, retry/backoff, DLQ, reconciliation và manual escalation.
- [ ] Không dùng dữ liệu projection stale để quyết định invariant ghi.
- [ ] Có thể giải thích chính xác “eventually consistent” hội tụ bằng cơ chế nào.

### UX và hợp đồng
- [ ] API phân biệt accepted, resource created và business confirmed.
- [ ] Có status endpoint/operationId và hỗ trợ reconnect.
- [ ] UI phân biệt pending, unknown, failed, compensating và completed.
- [ ] Có chính sách cancellation/expiry và bù trừ được truyền đạt rõ.
- [ ] Không khuyến khích retry thao tác tiền/chỗ khi chưa biết kết quả cũ.
- [ ] Có độ trễ kỳ vọng và phương án thông báo khi quá SLA.

### Vận hành
- [ ] Có tracing end-to-end theo operationId/traceId.
- [ ] Có metrics workflow duration, stuck state, compensation failure.
- [ ] Có reconciliation giữa các owners và xử lý mismatch.
- [ ] Có chaos/failure tests cho các cửa sổ lỗi quan trọng.
- [ ] Có người chịu trách nhiệm manual review và incident runbook.
- [ ] Đã đánh giá latency, throughput, availability và chi phí hạ tầng.

## 34. Ghi nhớ

1. **Bảo vệ invariant tại đúng owner** bằng transaction/concurrency control phù hợp; đừng đẩy mọi bất biến thành consistency của message broker.
2. **Một transaction cục bộ là lựa chọn đơn giản nhất** khi dữ liệu cần thay đổi atomically cùng một bounded context.
3. **RPC đồng bộ cho phản hồi trực tiếp nhưng không tự là global ACID transaction.** Deadline và unknown outcome vẫn phải giải quyết.
4. **2PC có thể đem lại atomic commit trong phạm vi resource hỗ trợ** nhưng tăng blocking, lock và chi phí vận hành; không phù hợp mọi external API.
5. **TCC thích hợp khi tài nguyên có thể đặt giữ tạm**, còn Saga thích hợp khi workflow phải đi qua nhiều local transactions có bù/khắc phục.
6. **Saga không phải rollback thời gian:** compensation có thể mất thời gian, thất bại hoặc không đảo được mọi tác dụng.
7. **Eventual consistency phải có state machine, convergence và reconciliation**, không chỉ có queue.
8. **Trải nghiệm tốt không nhất thiết đồng nghĩa “thành công tức thì”.** Trạng thái PENDING/UNKNOWN trung thực và operationId đáng tin thường tốt hơn lời hứa sai.
9. **Idempotency, outbox, retry an toàn, tracing và đối soát** là các nền tảng quan trọng bất kể mẫu giao dịch.
10. **Quyết định cuối cùng dựa trên nghiệp vụ và UX:** nhất quán ở đâu, ai được quyền quyết định, người dùng chờ được bao lâu, và điều gì xảy ra khi một phần đã thành công còn phần khác chưa hoàn tất.