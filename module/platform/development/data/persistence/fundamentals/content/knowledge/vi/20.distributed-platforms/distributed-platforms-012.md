# Ranh giới giữa giao dịch phân tán, bù trừ và quy trình nghiệp vụ

Trong chương **Nền tảng phân tán** của mô-đun **DATA_PERSISTENCE_FUNDAMENTALS**, một hệ thống Java thường không chỉ ghi vào một cơ sở dữ liệu. Đặt hàng có thể cần giữ tồn kho, thu tiền, tạo vận đơn và phát sự kiện; mỗi bước do một dịch vụ và một kho dữ liệu riêng quản lý. Khi các bước trải qua nhiều ranh giới mạng, lời hứa “hoặc tất cả thành công, hoặc không có gì xảy ra” của một transaction cục bộ **không tự động mở rộng** ra toàn bộ quy trình.

Ba khái niệm phải được phân biệt:

- **Giao dịch phân tán:** cơ chế phối hợp nhiều tài nguyên để đạt một cam kết nguyên tử theo giao thức cụ thể, chẳng hạn two-phase commit (2PC/XA).
- **Bù trừ (compensation):** một **hành động nghiệp vụ mới** được thực hiện để khắc phục tác dụng của một bước đã commit; không phải nút “undo” của database.
- **Quy trình nghiệp vụ phân tán:** chuỗi trạng thái, quyết định, timeout, retry, thông điệp và quy tắc xử lý lỗi để đạt kết quả cuối; thường triển khai bằng saga, workflow/orchestrator hoặc choreography.

Mục tiêu là nhận ra **ranh giới bảo đảm của từng lựa chọn**, thiết kế các bước có thể khôi phục sau sự cố và dùng SQL/Java để bảo vệ tính đúng đắn mà không giả định mạng, broker hay đối tác luôn phản hồi.

## 1. Một đơn hàng không nằm trong một transaction duy nhất

Giả sử khách đặt một sản phẩm và chọn giao hàng:

```text
Client
  |
  v
Order Service ----(1)----> Order DB
  |
  +----(2)-------------> Inventory Service ---> Inventory DB
  |
  +----(3)-------------> Payment Service -----> Payment DB/Provider
  |
  +----(4)-------------> Shipping Service ----> Shipping DB/Partner
  |
  +----(5)-------------> Notification Service
```

Nếu Order Service thực hiện `COMMIT` ở Order DB, giao dịch đó chỉ bao trùm các thay đổi do **Order DB transaction manager** kiểm soát. Nó không tự commit hoặc rollback một khoản đã thu ở cổng thanh toán, một tồn kho ở dịch vụ khác hay một lô hàng đã được bàn giao.

Ví dụ:

1. Order DB lưu đơn hàng ở trạng thái `PENDING` và commit.
2. Inventory Service giữ hàng thành công rồi commit Inventory DB.
3. Payment Service thu tiền thành công.
4. Shipping Service từ chối vận chuyển vì địa chỉ không được hỗ trợ.

Lúc này **đã có các thay đổi thật và đã commit**. Không thể gọi `rollback()` trên JDBC connection của Order Service để hoàn tác chúng. Hệ thống phải chọn hành động nghiệp vụ: điều chỉnh địa chỉ, tìm hãng vận chuyển khác, hủy đơn, hoàn tiền, giải phóng tồn kho hoặc chuyển sang xử lý thủ công.

**Một thao tác HTTP thành công không phải một global commit**, và một timeout HTTP cũng không phải bằng chứng rằng hệ thống nhận yêu cầu đã rollback. Cần phân biệt *thực tế đã xảy ra* với *phản hồi mà caller nhìn thấy*.

## 2. Ranh giới của ACID cục bộ và nhất quán liên dịch vụ

Một giao dịch ACID trên cùng database có thể bảo vệ nhiều bảng bằng một commit:

```sql
BEGIN;

UPDATE inventory
SET available = available - 1
WHERE sku = 'BOOK-1'
  AND available >= 1;
-- Ứng dụng bắt buộc kiểm tra đúng 1 hàng được cập nhật.

INSERT INTO reservations(request_id, sku, quantity)
VALUES ('3d5da63b-9a45-4ee9-b640-873d489ba128', 'BOOK-1', 1);

COMMIT;
```

Nếu transaction rollback, cả cập nhật tồn kho và reservation đều không được commit. Database chịu trách nhiệm khóa, kiểm tra điều kiện, WAL/recovery và chính sách độ bền trong phạm vi của nó.

Nhưng khi bước tiếp theo gọi một Payment Service có cơ sở dữ liệu khác, phần transaction này đã **kết thúc**. Giữ một connection và transaction mở ở Order DB trong lúc chờ Payment Service **không làm Payment DB trở thành cùng transaction**, mà còn gây giữ khóa, cạn connection pool và tăng rủi ro timeout.

| Ranh giới | Có thể hứa điều gì khi triển khai đúng? | Không mặc nhiên hứa điều gì? |
| --- | --- | --- |
| Một SQL statement có điều kiện | Cập nhật hàng phù hợp một cách nguyên tử theo DBMS. | Các API bên ngoài cũng được cập nhật. |
| Một DB transaction | Các bảng/thay đổi trong cùng transaction commit hoặc rollback theo cấu hình. | Commit ở những DB khác thành một thao tác nguyên tử. |
| Message broker ACK | Broker xác nhận theo hợp đồng gửi/nhận đã cấu hình. | Consumer đã hoàn tất nghiệp vụ và DB của nó đã commit. |
| HTTP 2xx từ service ngoài | Đối tác xác nhận theo hợp đồng API. | Database của caller cũng commit, hoặc không thể có duplicate. |
| Saga hoàn tất | Các bước nghiệp vụ đã đạt một trạng thái cuối theo workflow. | Các bước từng diễn ra như một transaction ACID duy nhất. |

Khi yêu cầu nói “đặt hàng phải nhất quán”, hãy làm rõ **bất biến nào cần luôn đúng**, bất biến nào có thể tạm chưa đúng trong thời gian xử lý, và những trạng thái trung gian nào được phép hiển thị.

## 3. Giao dịch phân tán nguyên tử: 2PC/XA làm gì?

**Two-phase commit (2PC)** là giao thức để một coordinator phối hợp những tài nguyên có khả năng tham gia giao dịch phân tán. Một hình dung:

```text
                  Transaction Coordinator
                       /           \
                      /             \
               Database A        Database B

Phase 1 - PREPARE:
  Coordinator hỏi từng participant có thể commit không.
  Participant ghi trạng thái chuẩn bị và trả YES/NO.

Phase 2 - DECIDE:
  Tất cả YES  -> coordinator ghi quyết định COMMIT,
                 yêu cầu mọi participant commit.
  Có NO/lỗi   -> quyết định ROLLBACK theo giao thức.
```

Trong Java, XA có thể được sử dụng thông qua transaction manager hỗ trợ JTA/XA và các `XAResource` tương thích. Tuy nhiên, **không phải mọi database, message broker, driver hoặc API HTTP đều là participant XA**. Một cổng thanh toán bên ngoài không thể tự biến thành tài nguyên XA chỉ vì ứng dụng gắn `@Transactional`.

### 2PC có giá trị khi nào?

Với tập tài nguyên **đều hỗ trợ giao thức** và yêu cầu atomic commit mạnh, 2PC là một lựa chọn đáng xem xét. Nhưng cần tính tới:

- **Thời gian khóa và trạng thái prepared:** participant có thể phải giữ tài nguyên trong khi coordinator quyết định.
- **Khả năng blocking:** với 2PC cổ điển, khi coordinator không sẵn sàng sau prepare, các participant có thể ở trạng thái *in-doubt* và phải chờ phục hồi/quyết định hợp lệ.
- **Chi phí round-trip và log bền vững:** độ trễ và throughput chịu tác động từ nhiều nút tham gia.
- **Vận hành recovery:** phải theo dõi, xử lý những giao dịch prepared lâu, hiểu cơ chế coordinator khôi phục.
- **Phạm vi:** atomic commit không giải quyết việc gửi email, giao hàng vật lý, khôi phục lỗi logic hoặc chọn chính sách nghiệp vụ khi đối tác từ chối.

**2PC không đồng nghĩa với “mọi service cùng thấy dữ liệu tại cùng một thời điểm”.** Atomic commit và các bảo đảm đọc/serializability là những thuộc tính cần xem xét riêng theo giao thức và cấu hình.

### 2PC có thay thế saga không?

Không nên xem 2PC và saga là hai nút bấm tùy chọn trên cùng một bài toán. 2PC tìm cách phối hợp **commit của những tài nguyên có hỗ trợ**. Saga chia quy trình dài thành **các local transaction đã commit** và các bước bù trừ có ý nghĩa nghiệp vụ. Nhiều thao tác như phát hành vận đơn, thu tiền qua một nhà cung cấp bên ngoài hoặc gửi thông báo không có khả năng tham gia vào 2PC.

## 4. Saga: chuỗi giao dịch cục bộ có thể bù trừ

**Saga** chia một quy trình thành các bước `T1, T2, T3...`. Mỗi bước có local transaction và có thể có hành động bù trừ `C1, C2, C3...` khi quy trình không thể tiếp tục.

```text
Luồng thuận:
  T1: Tạo đơn PENDING
      |
  T2: Giữ tồn kho
      |
  T3: Thu tiền
      |
  T4: Tạo vận đơn
      |
      v
  COMPLETED

Nếu T4 không thực hiện được:
  C3: Hoàn tiền theo quy tắc thanh toán
      |
  C2: Giải phóng phần tồn kho còn giữ
      |
  C1: Đánh dấu đơn CANCELLED/COMPENSATED
```

Sơ đồ thể hiện một **chính sách bù trừ ví dụ**, không có nghĩa mọi nghiệp vụ luôn bù theo thứ tự đảo ngược. Thứ tự thực tế phải được thiết kế theo tác dụng phụ, tính không thể đảo ngược và khả năng lặp lại của từng bước.

Trong saga, giữa T2 và T3 có thể tồn tại trạng thái **tồn kho đã giữ nhưng thanh toán chưa thành công**. Đây là **trạng thái trung gian hợp lệ có chủ đích**, không phải database đang vi phạm một transaction ACID. Người thiết kế phải trả lời: giữ hàng được bao lâu, có thể hủy giữ không, chuyện gì xảy ra nếu thanh toán phản hồi sau khi giữ hàng hết hạn?

### Saga bảo đảm gì và không bảo đảm gì?

Một saga được thiết kế đúng có thể:

1. Tiến hành qua nhiều hệ thống mà không cần một global database lock kéo dài.
2. Lưu tiến độ bền vững để phục hồi sau crash.
3. Nhận diện retry/duplicate bằng định danh bước và idempotency key.
4. Áp dụng chính sách bù trừ có giới hạn hoặc chuyển sang xử lý thủ công.

Saga **không tự bảo đảm** atomic visibility, isolation tương đương một DB transaction, hoặc luôn khôi phục được đúng trạng thái ban đầu. Đường bù trừ cũng có thể thất bại hoặc mất ACK. Hệ thống cần thiết kế cả **lỗi của chính hành động bù trừ**.

## 5. Bù trừ không phải rollback kỹ thuật

Một transaction chưa commit có thể được rollback trong database. Ngược lại, một local transaction **đã commit** không thể bị kéo ngược lại chỉ bằng cách gọi `rollback()` từ service khác.

Ví dụ: Payment Service đã ghi nhận khoản thu 500.000 đồng. “Bù trừ” bằng **refund** thường tạo một giao dịch tài chính mới, có mã riêng, có thể mất phí, chậm, hoặc cần phê duyệt. Nó **không xóa** sự kiện thu tiền ban đầu khỏi lịch sử kế toán.

| Bước đã thành công | Bù trừ có thể dùng | Vì sao không phải phép đảo hoàn hảo? |
| --- | --- | --- |
| Giữ tồn kho có thời hạn | Hủy giữ hàng/release reservation. | Hàng có thể đã được phân bổ hoặc reservation đã hết hạn. |
| Trừ số dư/thu tiền | Refund/reversal theo hợp đồng bên thanh toán. | Có phí, chênh lệch tỷ giá, thời gian xử lý, giới hạn pháp lý. |
| Tạo vận đơn chưa bàn giao | Hủy vận đơn. | Đối tác có thể đã tiếp nhận và phát sinh phí. |
| Hàng đã giao cho đơn vị vận chuyển | Yêu cầu hoàn trả/thu hồi. | Không thể đảm bảo xóa dấu vết vận chuyển vật lý. |
| Gửi email/SMS | Gửi thông báo điều chỉnh. | Không thể “thu hồi” việc người nhận đã đọc thông điệp. |
| Cấp quyền truy cập | Thu hồi quyền. | Dữ liệu đã được tải xuống không nhất thiết thu hồi được. |

Vì vậy:

- **Bù trừ là hành động nghiệp vụ** có thể cần xác thực, chính sách phí, lịch sử và kiểm toán.
- **Bù trừ có thể chỉ đạt kết quả tương đương về nghiệp vụ**, không khôi phục chính xác trạng thái bit-by-bit.
- **Không phải bước nào cũng bù được**. Với hành động không thể đảo, có thể cần trì hoãn bước đó, cho phép trạng thái cần can thiệp hoặc thay đổi thứ tự workflow.
- **Không được âm thầm xóa lịch sử** của bước đã xảy ra để mô phỏng rằng nó chưa từng diễn ra.

Điều này làm rõ ranh giới trách nhiệm: domain/application quyết định **hành động nào được xem là bù trừ hợp lệ**, còn persistence adapter chỉ lưu thao tác theo transaction local tương ứng.

## 6. Thiết kế trạng thái workflow để người dùng và hệ thống hiểu cùng một kết quả

Một workflow cần có **mô hình trạng thái rõ** chứ không chỉ chuỗi lời gọi API. Ví dụ:

```text
          [RESERVE_PENDING]
                |
          inventory reserved
                v
          [PAYMENT_PENDING]
                |
           payment charged
                v
          [SHIPMENT_PENDING]
                |
          shipping accepted
                v
           [COMPLETED]

Nhánh không thể tiếp tục:
  RESERVE_PENDING --rejected--> [REJECTED]
  PAYMENT_PENDING --rejected--> [RELEASE_PENDING]
  SHIPMENT_PENDING --failed--> [REFUND_PENDING]
  REFUND_PENDING --refunded--> [RELEASE_PENDING]
  RELEASE_PENDING --released--> [COMPENSATED]

Nếu bù trừ không thể xác nhận:
  [..._PENDING] --> [NEEDS_REVIEW] hoặc tiếp tục chờ/đối soát
```

Trạng thái `COMPLETED` hay `COMPENSATED` là **trạng thái kết thúc của quy trình**, khác với `COMMIT` của từng database. Một đơn hàng có thể đi qua nhiều lần commit cục bộ trước khi đạt một trong các trạng thái này.

Lập một **bảng chuyển trạng thái hợp lệ**:

| Trạng thái hiện tại | Sự kiện/kết quả có thẩm quyền | Trạng thái tiếp theo | Hành động tiếp theo |
| --- | --- | --- | --- |
| `RESERVE_PENDING` | Inventory xác nhận reserved | `PAYMENT_PENDING` | Phát lệnh charge với ID ổn định. |
| `RESERVE_PENDING` | Inventory từ chối | `REJECTED` | Đóng workflow, thông báo người dùng. |
| `PAYMENT_PENDING` | Payment xác nhận charged | `SHIPMENT_PENDING` | Phát lệnh tạo vận đơn. |
| `PAYMENT_PENDING` | Payment từ chối xác định | `RELEASE_PENDING` | Phát lệnh release inventory. |
| `SHIPMENT_PENDING` | Shipping xác nhận accepted | `COMPLETED` | Hoàn tất đơn và phát kết quả. |
| `SHIPMENT_PENDING` | Shipping từ chối xác định | `REFUND_PENDING` | Bắt đầu hoàn tiền. |
| `REFUND_PENDING` | Refund đã hoàn tất | `RELEASE_PENDING` | Giải phóng tồn kho. |
| `RELEASE_PENDING` | Inventory đã release | `COMPENSATED` | Đóng workflow có ghi nhận lịch sử. |
| Bất kỳ bước pending phù hợp | Kết quả chưa xác định | Giữ pending hoặc `NEEDS_REVIEW` | Đối soát; không đoán thất bại. |

Đối với trạng thái trung gian, có thể trả HTTP `202 Accepted` kèm `operationId` và endpoint truy vấn; không nên báo “thành công cuối” chỉ vì Order DB đã ghi được trạng thái `PAYMENT_PENDING`.

### Đừng nhầm trạng thái workflow với trạng thái giao dịch local

Một trạng thái được commit trong Order DB phản ánh **điều mà Order Service đã biết và lưu**, không phải luôn là sự thật mới nhất ở tất cả các hệ thống. Ví dụ `PAYMENT_PENDING` có thể vẫn tồn tại sau khi provider đã thu tiền nhưng phản hồi bị mất. Vì vậy, một trạng thái pending cần có **quy trình đối soát**, không chỉ bộ đếm thời gian rồi mặc định thất bại.

## 7. Orchestration và choreography là hai cách điều phối saga

### 7.1. Orchestration: một coordinator điều khiển tiến trình

Với orchestration, một thành phần giữ trạng thái và phát lệnh:

```text
               Order Saga Orchestrator
                    |       ^ event
          command   |       |
                    v       |
             Inventory Service
                    |       ^ event
          command   |       |
                    v       |
               Payment Service
                    |       ^ event
          command   |       |
                    v       |
              Shipping Service
```

Ưu điểm:

- Có một nơi nhìn thấy **trạng thái tổng thể**, timeout, thứ tự và chính sách bù trừ.
- Dễ giải thích “đơn hiện đang ở bước nào” và xây endpoint theo dõi.
- Có thể dễ thay đổi workflow theo phiên bản và chạy kiểm thử theo state machine.

Rủi ro:

- Coordinator có thể trở thành nút nghẽn nếu thiết kế thiếu phân vùng/khả năng mở rộng.
- Cần **lưu trạng thái bền vững**, phát lệnh không mất sau commit và tránh nhiều worker cùng điều khiển một saga.
- Coordinator không được nghĩ rằng nó có thể rollback các participant bằng JDBC của chính mình.

Orchestrator có thể là code Java và bảng trạng thái trong database, hoặc một workflow engine phù hợp. Chọn công cụ dựa trên yêu cầu retry, timer, observability, tải, khả năng vận hành và mức trừu tượng nhóm hiểu được.

### 7.2. Choreography: các dịch vụ phản ứng với sự kiện

Với choreography, không nhất thiết có một coordinator duy nhất:

```text
OrderCreated
    |
    v
Inventory Service --> InventoryReserved
                             |
                             v
                       Payment Service --> PaymentCharged
                                              |
                                              v
                                        Shipping Service
```

Ưu điểm là các dịch vụ có thể phản ứng với sự kiện theo ranh giới riêng và giảm điều phối trực tiếp. Nhưng khi chuỗi gồm nhiều nhánh lỗi và bù trừ, logic workflow có thể **bị rải khắp consumer**, khó trả lời ai chịu trách nhiệm cho một đơn hàng bị kẹt.

Hãy so sánh:

| Tiêu chí | Orchestration | Choreography |
| --- | --- | --- |
| Nơi định nghĩa quy trình tổng thể | Thường tập trung ở coordinator/workflow. | Phân tán qua các handler sự kiện. |
| Thêm nhánh bù trừ phức tạp | Thường dễ quan sát và điều phối. | Dễ tạo phụ thuộc sự kiện ngầm và vòng lặp. |
| Quyền tự chủ của service | Service thực thi lệnh và phát kết quả. | Service chủ động phản ứng theo hợp đồng event. |
| Giám sát một workflow | Có thể theo trạng thái điều phối. | Cần correlation ID, trace và projection tổng hợp. |
| Độ tin cậy khi crash | Vẫn cần outbox/inbox và durable state. | Cũng cần outbox/inbox và chống trùng. |

Không có kiểu nào loại bỏ transaction local, idempotency, retry và đối soát. Một tổ chức có thể phối hợp cả hai: workflow quan trọng được orchestration, các thông báo ít quan trọng được truyền bằng sự kiện.

## 8. TCC: Try–Confirm–Cancel khi nghiệp vụ hỗ trợ giữ tài nguyên

**Try–Confirm–Cancel (TCC)** là một phương pháp phối hợp khác, thường phù hợp khi nghiệp vụ có thao tác **giữ tài nguyên tạm thời**:

1. **Try:** xác nhận khả năng và giữ phần tài nguyên cần thiết, ví dụ giữ 2 ghế trong 10 phút.
2. **Confirm:** xác nhận sử dụng phần đã giữ khi các bước khác đáp ứng.
3. **Cancel:** giải phóng phần đã giữ khi workflow không tiếp tục.

```text
Seat Service: Try(orderId, seatIds) ---> HELD, expiresAt
Payment:      Authorize(orderId)    ---> AUTHORIZED
Seat Service: Confirm(orderId)      ---> CONFIRMED
Payment:      Capture(orderId)      ---> CAPTURED

Nếu không thể confirm:
  Cancel hold / void authorization theo trạng thái thực tế
```

Các bước trên **vẫn là những thao tác riêng**; thiết kế phải xử lý trường hợp giữ ghế hết hạn trước khi confirm, capture thành công nhưng ACK bị mất, hoặc cancel đến trước try do retry/out-of-order. Không được xem TCC là cơ chế tạo global ACID miễn phí.

TCC phù hợp khi participant **có API Try/Confirm/Cancel đáng tin cậy**, sử dụng operation ID ổn định và đủ khả năng xử lý nhiều lần gọi. Nếu một bên chỉ có API “giao hàng ngay” và không thể giữ/hủy, mô hình TCC không tự tạo khả năng bù trừ.

## 9. Gửi lệnh/sự kiện cùng transaction local: transactional outbox

Một lỗ hổng phổ biến:

```text
BEGIN
UPDATE orders SET state = 'PAYMENT_PENDING'
COMMIT

Ứng dụng sập trước broker.publish(ChargePayment)
→ Đã lưu trạng thái nhưng không có lệnh thanh toán.
```

Đảo thứ tự cũng không an toàn: nếu phát lệnh thanh toán **trước** khi Order DB commit, database có thể rollback sau khi Payment Service đã thu tiền.

**Transactional outbox** đặt **bản ghi tiến trình và thông điệp cần gửi** trong **cùng một transaction của một database**:

```text
Local transaction:
  UPDATE order_workflows.state
  INSERT outbox_events(event_id, command_id, payload)
  COMMIT

Outbox relay sau commit:
  đọc pending event
  gửi broker
  đánh dấu published / thử lại nếu cần
```

Nếu ứng dụng sập trước commit, **cả tiến trình và outbox cùng rollback**. Nếu commit thành công nhưng relay sập, event vẫn còn để gửi lại.

### Outbox không bảo đảm broker nhận đúng một lần

Nếu relay gửi tới broker thành công nhưng sập trước khi đánh dấu `published_at`, nó có thể gửi lại cùng event. Do đó:

- Event có **event ID ổn định**, không tạo ID mới mỗi lần gửi lại.
- Consumer cần xử lý **idempotent** và có thể dùng **inbox/deduplication table**.
- Consumer phải cập nhật business state và đánh dấu đã nhận event **trong cùng transaction** nếu dùng một DB local.
- Phải có quan sát backlog, số lần gửi, DLQ và chính sách xử lý event lỗi kéo dài.

Một transaction của Order DB + outbox **không phải một distributed transaction giữa Order DB và broker**. Nó là một giao thức phân phối có thể phục hồi, thường cho kết quả **at-least-once**, nên mọi participant phải chịu được sự kiện lặp.

## 10. Inbox và idempotency: retry an toàn tại từng bước

Giả sử event `InventoryReserved` được giao hai lần. Nếu handler chỉ gọi Payment Service hai lần mà không kiểm tra, khách hàng có thể bị thu tiền hai lần. Cần nhận diện:

- **Correlation ID:** `orderId` hoặc `sagaId` để ghép các bước thuộc cùng workflow.
- **Event ID:** xác định một message cụ thể để consumer phát hiện giao lặp.
- **Command/operation ID:** xác định **một ý định nghiệp vụ** như `charge-payment-for-order-123`; các lần retry gửi **cùng ID**.
- **Attempt ID:** có thể thay đổi mỗi lần thử và phục vụ log/metrics, không thay thế operation ID.

Một inbox lưu event ID đã xử lý thành công:

```sql
CREATE TABLE inbox_events (
    consumer_name TEXT NOT NULL,
    event_id      UUID NOT NULL,
    received_at   TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (consumer_name, event_id)
);
```

Quy trình xử lý sự kiện có thể là:

```text
BEGIN transaction ở DB của consumer
  INSERT inbox(consumer, event_id) ON CONFLICT DO NOTHING
  nếu đã có: không xử lý lại
  nếu là event mới:
      kiểm tra trạng thái/phiên bản hiện tại
      chuyển trạng thái có điều kiện
      INSERT outbox cho bước kế tiếp nếu cần
COMMIT
ACK broker chỉ sau khi local commit
```

Nếu xử lý thất bại trước commit, inbox phải rollback cùng trạng thái; event được giao lại vẫn còn cơ hội chạy. Nếu inbox được commit **trước** khi thay đổi nghiệp vụ, retry có thể bỏ qua một công việc chưa hoàn thành. Cũng phải tránh việc đánh dấu event là “đã xử lý” khi thực chất nó chỉ là **event đến sai thứ tự cần xử lý sau**.

**Inbox theo event ID không đủ nếu upstream tạo hai event ID khác nhau cho cùng một thao tác.** Bảo đảm chống tác dụng phụ lặp cần khóa nghiệp vụ ổn định như `UNIQUE(payment_operation_id)` ở Payment DB hoặc idempotency key ở nhà cung cấp thanh toán.

## 11. Thiết kế bảng workflow và outbox trên PostgreSQL

Một ví dụ tối giản, phục vụ minh họa cho orchestrator:

```sql
CREATE TABLE order_workflows (
    order_id    UUID PRIMARY KEY,
    request_id  UUID NOT NULL UNIQUE,
    state       TEXT NOT NULL CHECK (state IN (
        'RESERVE_PENDING',
        'PAYMENT_PENDING',
        'SHIPMENT_PENDING',
        'COMPLETED',
        'REJECTED',
        'REFUND_PENDING',
        'RELEASE_PENDING',
        'COMPENSATED',
        'NEEDS_REVIEW'
    )),
    version     BIGINT NOT NULL DEFAULT 0 CHECK (version >= 0),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE outbox_events (
    event_id      UUID PRIMARY KEY,
    order_id      UUID NOT NULL REFERENCES order_workflows(order_id),
    command_id    UUID NOT NULL UNIQUE,
    event_type    TEXT NOT NULL,
    payload       JSONB NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    published_at  TIMESTAMPTZ
);

CREATE INDEX outbox_unpublished_idx
    ON outbox_events (created_at)
    WHERE published_at IS NULL;
```

Các bảng này lưu **trạng thái điều phối và lệnh chưa gửi**, không thay thế bảng nghiệp vụ order, payment ledger hay reservation thực tế của từng service. Hệ thống production cần chính sách retention/partition, audit, tenant và quyền truy cập, cùng thông tin lỗi/retry phù hợp.

### Khởi tạo workflow và command đầu tiên nguyên tử

```sql
BEGIN;

INSERT INTO order_workflows(order_id, request_id, state)
VALUES (:order_id, :request_id, 'RESERVE_PENDING')
ON CONFLICT (request_id) DO NOTHING
RETURNING order_id;

-- Chỉ khi INSERT trả 1 hàng, mới INSERT outbox ReserveInventory.
INSERT INTO outbox_events(
    event_id, order_id, command_id, event_type, payload
)
VALUES (
    :event_id, :order_id, :reserve_command_id,
    'ReserveInventory', :payload::jsonb
);

COMMIT;
```

**Chú ý:** đoạn trên biểu diễn hai bước với nhánh điều kiện do ứng dụng thực thi; **không chạy vô điều kiện INSERT outbox nếu INSERT workflow trả 0 hàng**. Khi request ID đã tồn tại, cần đọc lại kết quả, so payload nghiệp vụ và trả/xử lý theo giao thức idempotency. Nếu mất ACK commit, đối soát tại primary trước khi quyết định thử lại.

Các placeholder `:name` là cú pháp minh họa cho công cụ bind tham số; JDBC thuần dùng `?`. Không ghép chuỗi trực tiếp từ dữ liệu người dùng vào SQL.

### Chuyển trạng thái có điều kiện

Khi nhận sự kiện inventory đã giữ hàng thành công:

```sql
BEGIN;

UPDATE order_workflows
SET state = 'PAYMENT_PENDING',
    version = version + 1,
    updated_at = CURRENT_TIMESTAMP
WHERE order_id = :order_id
  AND state = 'RESERVE_PENDING';
-- Bắt buộc kiểm tra đúng 1 hàng được cập nhật.

INSERT INTO outbox_events (
    event_id, order_id, command_id, event_type, payload
)
VALUES (
    :event_id, :order_id, :charge_command_id,
    'ChargePayment', :payload::jsonb
);

COMMIT;
```

Cũng như phần khởi tạo, `INSERT outbox` chỉ được chạy khi phép chuyển trạng thái thành công. Nếu `UPDATE` trả 0 hàng, **không tự động suy ra inventory thất bại**: có thể event trùng, đến trễ, workflow đã bù trừ hoặc đã được xử lý theo đường khác. Cần kiểm tra trạng thái hiện tại và quyết định bỏ qua, trì hoãn, xử lý xung đột hay chuyển tới DLQ.

Điều kiện trong câu `UPDATE` là **hàng rào trạng thái** (*state guard*). Cột `version` hỗ trợ thêm optimistic concurrency và audit. Không được cho một worker cũ chuyển `COMPENSATED` trở lại `PAYMENT_PENDING` chỉ vì nó nhận một event trễ.

## 12. Java/Spring: ghi inbox, state và outbox trong cùng transaction

Ví dụ sau minh họa một handler sự kiện trên **cùng PostgreSQL datasource và Spring transaction manager**, sử dụng `JdbcTemplate`. Mã đòi có các bảng như phần trên, thêm bảng `inbox_events`, và chạy qua Spring-managed proxy. Java 17+ hỗ trợ text block và `UUID.nameUUIDFromBytes(...)`.

```java
import java.math.BigDecimal;
import java.nio.charset.StandardCharsets;
import java.util.UUID;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public final class OrderSagaEventHandler {
    private final JdbcTemplate jdbc;

    public OrderSagaEventHandler(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void onInventoryReserved(
            UUID eventId, UUID orderId, BigDecimal amount) {

        int claimed = jdbc.update("""
            INSERT INTO inbox_events (consumer_name, event_id)
            VALUES ('order-saga', ?)
            ON CONFLICT DO NOTHING
            """, eventId);

        if (claimed == 0) {
            return; // Sự kiện đã được xử lý trong lần commit trước.
        }

        int changed = jdbc.update("""
            UPDATE order_workflows
               SET state = 'PAYMENT_PENDING',
                   version = version + 1,
                   updated_at = CURRENT_TIMESTAMP
             WHERE order_id = ?
               AND state = 'RESERVE_PENDING'
            """, orderId);

        if (changed != 1) {
            // Rollback cả inbox: event chưa được xác nhận đã xử lý.
            // Tầng consumer sẽ phân loại: đến sai thứ tự,
            // stale event hay workflow đã ở trạng thái cuối.
            throw new IllegalStateException(
                    "Unexpected saga state for order " + orderId);
        }

        // Ví dụ này giả định mỗi order chỉ có một ý định charge.
        UUID commandId = UUID.nameUUIDFromBytes(
                ("charge:" + orderId).getBytes(StandardCharsets.UTF_8));

        jdbc.update("""
            INSERT INTO outbox_events (
                event_id, order_id, command_id, event_type, payload
            ) VALUES (
                ?, ?, ?, 'ChargePayment',
                jsonb_build_object(
                    'orderId', CAST(? AS text),
                    'commandId', CAST(? AS text),
                    'amount', CAST(? AS numeric)
                )
            )
            """,
            UUID.randomUUID(), orderId, commandId,
            orderId.toString(), commandId.toString(), amount);
    }
}
```

Trong ví dụ, **inbox + chuyển state + outbox cùng commit hoặc cùng rollback**. Khi broker giao lặp lại **cùng event ID** sau commit, handler thấy inbox có rồi bỏ qua. Nếu process sập trước commit, inbox cũng rollback để giao lại không bị bỏ qua.

Các giới hạn cần giải quyết ở production:

1. **Sự kiện sai thứ tự/đã lỗi thời:** ví dụ handler ném lỗi và rollback inbox; consumer cần phân loại sau đó, có thể đánh dấu event là không còn phù hợp hoặc đưa vào nơi chờ xử lý. Không retry vô hạn một trạng thái terminal hợp lệ.
2. **Nguồn sự kiện có đáng tin không?** Phải xác thực nguồn, payload, `orderId`, số tiền, tenant và quyền trước khi chuyển trạng thái; không tin event gửi tới là đúng chỉ vì nó có UUID.
3. **Operation ID ổn định:** cách tạo `commandId` từ `orderId` chỉ phù hợp giả định mỗi order có **một lần charge**. Nếu nghiệp vụ có nhiều lần thu tiền hợp lệ, key phải bao gồm định danh của **mỗi ý định thu tiền**, không dùng chung để chặn nhầm.
4. **Không gọi Payment Service bên trong local transaction:** handler chỉ ghi outbox; relay phát command sau commit.
5. **Xử lý race giữa nhiều worker:** unique inbox, điều kiện state và transaction giúp chặn một số race, nhưng cần chuẩn hóa quy tắc xử lý event trễ và các nhánh bù trừ.
6. **Quy trình relay:** outbox phải được gửi tới broker theo cách có thể retry mà không tạo command ID mới; cần chính sách claim/lock và bảo vệ khi nhiều relay cùng chạy.

Ví dụ làm rõ **ranh giới transaction cục bộ và thông điệp bền vững**. Nó không triển khai toàn bộ saga end-to-end và không chứng minh hệ thống đã đạt exactly-once ở mọi service.

## 13. Không biết đã commit/chuyển tiền hay chưa: đừng đoán trạng thái

Một lớp lỗi khó nhất là **kết quả không rõ ràng** (*indeterminate outcome*). Ví dụ:

```text
Order Saga gửi ChargePayment(command_id = P)
             |
             v
Payment Service nhận P
  - ghi payment
  - COMMIT local database
             |
       Mất mạng trước ACK
             X
Order Saga timeout, chưa biết payment đã commit hay chưa
```

**Sai:** coi mọi timeout như “chưa thu tiền” rồi gửi một `command_id` mới. Payment Service có thể thu tiền lần nữa.

**Đúng:** giữ nguyên `command_id = P`; Payment Service lưu kết quả bằng một ràng buộc duy nhất, ví dụ `UNIQUE(payment_operation_id)`, rồi cho phép truy vấn kết quả theo P. Khi timeout, orchestrator **đối soát trạng thái ở nguồn có thẩm quyền** hoặc gửi lại **cùng P** qua giao thức idempotent.

Nếu provider thanh toán bên ngoài có idempotency key, cần xem **thời hạn và phạm vi bảo đảm của provider**; không tự giả định key có hiệu lực vô hạn. Nếu provider không hỗ trợ tra cứu đáng tin, workflow có thể phải chuyển `NEEDS_REVIEW` để con người đối chiếu trước khi gọi thêm một tác vụ có thể thu tiền.

Một lần `rollback()` trên JDBC connection của Order Service **không thể xác định và cũng không thể hoàn tác** Payment Service đã commit hay chưa.

### Retry và compensation phải cùng an toàn với duplicate

Không chỉ bước thuận cần chống trùng. Nếu refund bị timeout sau khi tiền đã hoàn:

- Giữ cùng `refund_operation_id` khi tra cứu hoặc thử lại.
- Không phát khoản refund thứ hai có mã mới vì chưa nhận ACK.
- Ghi nhận kết quả cuối từ provider/Payment DB.
- Phân biệt đã *khởi tạo refund* với đã *hoàn tất refund*: provider có thể xử lý bất đồng bộ.

Với release inventory, có thể cập nhật theo điều kiện `reservation_id` và trạng thái, sao cho gọi release nhiều lần **không cộng tồn kho thêm nhiều lần**. Đừng xây compensation bằng một câu lệnh `UPDATE available = available + quantity` vô điều kiện cho mỗi retry.

## 14. Timeout, lease và các bước chạy lâu

Một saga có thể tồn tại nhiều phút hoặc nhiều ngày. Vì thế cần hiểu các loại thời hạn:

| Thời hạn | Ý nghĩa | Sai lầm cần tránh |
| --- | --- | --- |
| HTTP timeout | Client ngừng chờ phản hồi. | Coi đối tác chắc chắn không thực hiện hành động. |
| Broker redelivery timeout | Consumer chưa ACK theo thời hạn; có thể giao lại. | Nghĩ rằng tác vụ trước đã bị hủy hoặc rollback. |
| DB lock/statement timeout | Giới hạn thời gian chờ khóa/truy vấn ở DB. | Gộp với thời hạn nghiệp vụ không liên quan. |
| Reservation expiry | Giữ tài nguyên có hiệu lực đến một mốc. | Confirm sau khi đã hết hạn mà không kiểm tra lại. |
| Worker lease | Quyền xử lý tạm thời để tránh nhiều worker cùng chủ động. | Coi lease hết hạn là bằng chứng worker cũ không còn thao tác ngoài. |
| Business deadline | Thời điểm phải chuyển hướng workflow hoặc báo cho người dùng. | Tự động bù trừ khi chưa biết tác dụng phụ có xảy ra. |

Một worker chậm có thể mất lease rồi **tiếp tục chạy** sau khi worker khác đã tiếp quản. Muốn ngăn stale worker làm hỏng state, cần dùng **version check/compare-and-set hoặc fencing token** tại điểm nhận ghi. Nếu đã gửi lệnh cho hệ thống ngoài không kiểm fencing, phải dùng operation ID và giao thức đối soát để xử lý trùng.

Lưu ý chuyện thời gian: các service có thể lệch clock. Với hạn giữ tài nguyên, nên có một hệ thống **chịu trách nhiệm quyết định hiệu lực của hold**; không để client tự suy đoán chỉ từ đồng hồ của mình.

## 15. Consistency: bất biến nào được bảo vệ tức thì, bất biến nào chỉ đạt sau workflow?

Một saga có nhiều trạng thái đã commit nhưng chưa hoàn tất. Vì vậy, thiết kế phải chỉ rõ hai loại bất biến:

### Bất biến phải đúng tức thì trong mỗi local database

Ví dụ Inventory DB phải ngăn:

- Tồn kho âm.
- Một reservation ID được giữ hai lần.
- Release cùng reservation hai lần khiến tồn kho tăng sai.
- Confirm một reservation đã hết hạn/hủy, nếu quy tắc không cho phép.

Có thể dùng transaction, `CHECK`, `UNIQUE`, `UPDATE ... WHERE ...`, version và locking phù hợp ở Inventory DB. Các biện pháp này không phụ thuộc vào việc Order Service chọn choreography hay orchestration.

### Bất biến cần đạt sau khi workflow kết thúc

Ví dụ: “Đơn hàng `COMPLETED` phải có thanh toán cuối cùng đã được xác nhận và đã tạo vận đơn theo chính sách”. Trong lúc `PAYMENT_PENDING`, việc chưa có vận đơn có thể là trạng thái hợp lệ.

**Điều kiện để chuyển sang COMPLETED** phải được bảo vệ: chỉ chuyển khi nhận các sự kiện có thẩm quyền, khớp order/operation ID và state/version. Không cho notification handler tự ý đổi `COMPLETED` chỉ vì có thông điệp “PaymentCharged” mà chưa biết Shipping đã hoàn thành.

### Đọc dữ liệu trong trạng thái trung gian

Một dashboard hoặc API có thể đọc projection từ event, replica hoặc cache và **chậm hơn** dữ liệu local đã commit. Khi ra quyết định quan trọng, cần chọn nguồn đọc có bảo đảm độ mới/nhất quán phù hợp; không dùng việc “replica chưa thấy bản ghi” để kết luận bước trước không xảy ra.

**Eventual consistency** phải có giới hạn thực tế: những trạng thái trung gian nào được phép, ai chịu trách nhiệm tiến độ, deadline, retry, backlog và trường hợp nào buộc escalation. Nó không có nghĩa hệ thống có quyền kẹt vĩnh viễn mà không bị phát hiện.

## 16. Khi nào nên chọn 2PC, saga, TCC hoặc chỉ một database?

| Bối cảnh | Hướng thường đáng cân nhắc | Câu hỏi quyết định |
| --- | --- | --- |
| Các bảng cùng database, transaction ngắn | **Một ACID transaction**. | Có thật cần tách tài nguyên ra nhiều service? |
| Nhiều tài nguyên hỗ trợ XA, cần atomic commit, chấp nhận chi phí vận hành | **2PC/XA** có transaction coordinator. | Mọi participant đều hỗ trợ? Recovery prepared transaction vận hành được? |
| Nhiều service có local DB riêng, bước có bù trừ nghiệp vụ | **Saga** orchestration hoặc choreography. | Có thể chịu trạng thái trung gian và bù trừ không? |
| Tài nguyên hỗ trợ hold/confirm/cancel có thời hạn | **TCC** hoặc quy trình reservation tương đương. | Hết hạn, duplicate và confirm/cancel cạnh tranh được giải quyết thế nào? |
| Chỉ cần phát sự kiện đáng tin sau một local commit | **Transactional outbox + idempotent consumer**. | Có broker relay, retry và quan sát backlog không? |
| Tác dụng phụ không thể đảo (gửi hàng, thông báo đã đọc) | **Workflow với điểm không thể bù trừ và can thiệp thủ công**. | Có thể trì hoãn hành động đó hoặc thiết kế recovery khác không? |

**Đừng vội tách microservice nếu các bất biến cần một transaction mạnh trên nhiều bảng.** Đôi khi một database và một application boundary rõ ràng là thiết kế đúng hơn một saga phức tạp. Ngược lại, nếu các đơn vị nghiệp vụ sở hữu dữ liệu riêng và giao thức bù trừ khả thi, cố ép mọi thứ vào XA có thể tăng phụ thuộc và độ khó vận hành.

### Chọn orchestration hay choreography?

Một saga nhiều bước, có timeout dài và bù trừ phức tạp thường thuận lợi khi có **orchestrator giữ durable state**. Với vài sự kiện ít phụ thuộc và không có nhánh bù trừ phức tạp, **choreography** có thể đủ. Dù chọn cách nào, cần có **hợp đồng sự kiện, correlation ID, idempotency và quy trình recovery**.

## 17. Quan sát vận hành: biết saga đang kẹt ở đâu

Một hệ thống phân tán không chỉ cần dashboard HTTP 500; nó cần quan sát **tiến độ nghiệp vụ**:

| Chỉ số / dữ kiện | Giúp trả lời |
| --- | --- |
| Số saga theo trạng thái và tuổi | Có bao nhiêu đơn đang `PAYMENT_PENDING` quá lâu? |
| Số workflow `NEEDS_REVIEW` | Có bao nhiêu tác vụ không thể tự kết luận an toàn? |
| Số compensation đang chạy/thất bại | Có bù trừ nào kẹt và cần xử lý thủ công? |
| Outbox backlog và tuổi event cũ nhất | Có command đã commit nhưng chưa gửi? |
| Inbox duplicate/unique conflict | Broker có giao lại nhiều? Command ID có bị tái sử dụng sai? |
| Độ trễ từ event đến trạng thái local | Workflow mất bao lâu để đạt từng bước? |
| Tỷ lệ timeout, retry, DLQ | Có vấn đề ở dependency nào và backoff có gây thác lũ? |
| Replication lag/failover events | Nguồn đọc có đủ mới để đối soát không? |
| Trạng thái payment/refund theo operation ID | Có kết quả đã thực hiện nhưng caller chưa được cập nhật? |

Log/trace nên mang `orderId`, `sagaId`, `commandId`, `eventId`, tên bước và trạng thái chuyển tiếp. Không ghi dữ liệu thẻ hoặc bí mật thanh toán vào log. Với mỗi command, lưu đủ bằng chứng để phân biệt **đã phát lệnh**, **đã nhận ACK**, **đã xác nhận kết quả nghiệp vụ** và **đã cập nhật workflow**.

Hệ thống cần chính sách:

1. Tự retry trong khoảng thời gian có giới hạn với backoff + jitter và cùng operation ID.
2. Đối soát từ nguồn có thẩm quyền khi kết quả không rõ.
3. Giới hạn số worker/connection để không làm nghẽn participant đang lỗi.
4. Đưa event/tác vụ có dữ liệu sai hoặc lỗi kéo dài sang DLQ/parking queue.
5. Có runbook để đội vận hành can thiệp trên trạng thái thực tế, không thực hiện “refund thêm lần nữa cho chắc”.

## 18. Kiểm thử lỗi ở mọi điểm chuyển ranh giới

Một saga không được đánh giá chỉ bằng happy path. Test cần giả lập cả **crash sau commit**, **ACK bị mất**, **giao lặp** và **cạnh tranh giữa các worker**.

| Kịch bản | Kết quả cần chứng minh |
| --- | --- |
| Order DB commit cùng outbox, worker sập trước publish | Event vẫn trong outbox và sẽ được gửi lại. |
| Broker nhận event, relay sập trước đánh dấu sent | Có thể publish lặp nhưng consumer không áp dụng nghiệp vụ hai lần. |
| Consumer ghi inbox rồi lỗi trước cập nhật state | Cả transaction rollback; event có thể retry. |
| Hai consumer cùng nhận một event ID | Chỉ một xử lý nghiệp vụ được commit; handler kia nhận ra duplicate. |
| Hai event khác ID nhưng cùng operation ID | Participant vẫn chống trùng tác dụng phụ bằng operation ID. |
| Payment commit nhưng ACK bị mất | Orchestrator đối soát đúng mã, không tạo charge mới. |
| Refund commit nhưng ACK bị mất | Không hoàn tiền hai lần; tiếp tục đối soát trạng thái refund. |
| Inventory reservation hết hạn khi Payment đang chạy | Workflow xác định lại trạng thái hold trước khi confirm, có bước bù hợp lệ. |
| Sự kiện `PaymentCharged` đến sau `COMPENSATED` | Event trễ không đẩy workflow trở lại trạng thái thanh toán; điều tra kết quả ngoài DB. |
| Worker cũ tiếp tục sau khi lease hết hạn | Version/fencing ngăn stale worker ghi đè state mới. |
| Failover sang replica chậm | Không kết luận không có payment chỉ từ việc đọc replica; phát hiện gap bảo đảm. |
| Một bước không thể bù trừ | Có trạng thái `NEEDS_REVIEW` và quy trình can thiệp thực tế. |

### Bài tập kiểm thử cụ thể

Giả sử có một đơn hàng `orderId=O`, Payment Service lưu duy nhất `payment_operation_id=P`. Gửi `ChargePayment(P)` **hai lần đồng thời**, rồi cho một client mất ACK. Kết quả mong muốn:

1. Payment DB ghi nhận **tối đa một tác dụng thu tiền** cho P trong phạm vi bảo đảm đã thiết kế.
2. Các lần retry vẫn dùng P và đọc lại cùng kết quả đã commit.
3. Order Saga chuyển khỏi `PAYMENT_PENDING` **chỉ khi có bằng chứng hợp lệ**.
4. Nếu Shipping từ chối, refund sử dụng **refund operation ID riêng ổn định**, không tái dùng P cho một ý định khác.
5. Nếu refund chưa rõ kết quả, workflow không tuyên bố `COMPENSATED` khi chưa có bằng chứng hoàn tất.
6. Mọi trạng thái cuối có audit trail và không được worker cũ ghi đè.

Kiểm thử nên thực hiện với **database và broker phù hợp trong môi trường kiểm thử có thể kiểm soát**, có cơ chế chủ động ngắt kết nối, dừng worker và sắp lịch sự kiện. Mock unit test giúp kiểm tra nhánh điều phối, nhưng không chứng minh unique constraint, transaction isolation, outbox recovery hay lịch giao event ngoài thực tế.

## 19. Những ngộ nhận cần tránh

| Ngộ nhận | Cách hiểu đúng |
| --- | --- |
| “Gắn `@Transactional` ở Order Service là rollback được Payment Service.” | Chỉ những resource cùng transaction manager/giao thức mới nằm trong ranh giới commit đó. |
| “Saga giống một global transaction có bước undo.” | Các bước saga đã commit riêng; compensation là tác vụ nghiệp vụ mới và có thể thất bại. |
| “2PC luôn là giải pháp tốt nhất để dữ liệu nhất quán.” | Cần participant hỗ trợ, xử lý blocking/recovery và chi phí điều phối; không bao gồm mọi tác dụng vật lý. |
| “HTTP timeout nghĩa là đối tác chưa xử lý.” | Đối tác có thể đã commit trước khi ACK bị mất. |
| “Có outbox tức broker giao event đúng một lần.” | Relay có thể gửi lặp; cần inbox/idempotency và stable ID. |
| “Một event ID duy nhất đã đủ chống thu tiền trùng.” | Hai event khác ID có thể cùng đại diện một payment operation; cần khóa nghiệp vụ. |
| “Hết timeout của lease nghĩa là worker cũ đã dừng.” | Worker cũ có thể tiếp tục; cần fencing/version hoặc idempotency. |
| “Có saga thì không cần ACID bên trong service.” | Mỗi bước vẫn phải bảo vệ bất biến local bằng transaction/constraint. |
| “Compensation thất bại thì cứ báo workflow đã rollback.” | Phải giữ trạng thái trung gian/NEEDS_REVIEW và tiếp tục phục hồi. |
| “Eventual consistency là cuối cùng tự đúng, không cần theo dõi.” | Cần deadline, retry, đối soát, metrics, DLQ và trách nhiệm vận hành. |
| “PaymentCharged event là đủ để đánh dấu đơn COMPLETED.” | Phải xác nhận toàn bộ điều kiện workflow, ví dụ shipping đã đạt trạng thái cần thiết. |

## 20. Câu hỏi tự kiểm tra

**Câu 1.** Order DB commit xong rồi Payment Service timeout. Gọi `rollback()` trên connection của Order Service có hoàn tác khoản thu không?

**Không.** Payment là tài nguyên khác và có thể đã commit. Cần đối soát bằng payment operation ID, rồi tiếp tục hoặc bù trừ theo trạng thái thật.

**Câu 2.** Vì sao không nên gửi message ra broker rồi mới commit Order DB?

Vì consumer có thể xử lý command trong lúc transaction ở Order DB rollback, dẫn tới tác dụng phụ bên ngoài không có trạng thái/order đã commit tương ứng. Outbox trong cùng local transaction giúp thu hẹp khoảng trống này.

**Câu 3.** Outbox relay có thể gửi một message hai lần không?

**Có.** Nếu broker đã nhận nhưng relay sập trước khi đánh dấu published, nó sẽ gửi lại. Consumer phải có dedup/idempotency và chỉ ACK sau khi local transaction hoàn tất phù hợp.

**Câu 4.** Hoàn tiền sau khi thu tiền có phải rollback ACID không?

**Không.** Refund là một giao dịch nghiệp vụ mới, có thể phát sinh phí hoặc chờ xử lý. Lịch sử thu tiền vẫn phải được giữ cho mục đích audit.

**Câu 5.** Chỉ cần `UNIQUE(event_id)` trong inbox đã chắc không thu tiền trùng chưa?

**Chưa.** Một thao tác thu tiền có thể được gửi bằng hai message khác ID. Payment Service còn cần `UNIQUE(payment_operation_id)` hoặc idempotency key theo ý định nghiệp vụ.

**Câu 6.** Vì sao một saga vẫn cần transaction isolation và conditional update trong Inventory DB?

Vì hai saga có thể đồng thời giữ cùng hàng. Phải cưỡng chế điều kiện tồn kho tại thời điểm ghi bằng transaction, khóa hoặc `UPDATE ... WHERE ...`; workflow không làm cuộc đua đó tự biến mất.

**Câu 7.** Với quy trình có thể mất nhiều ngày và gồm bước không thể đảo, lựa chọn 2PC hay saga chỉ dựa trên độ ngắn của mã điều phối có đúng không?

**Không.** Cần xét hợp đồng participant, thời hạn, khả năng bù trừ, trạng thái trung gian, độ sẵn sàng và phục hồi. Một quy trình dài có bước vật lý thường cần workflow và chính sách can thiệp, không thể ép thành một database transaction kéo dài.

**Câu 8.** Khi PaymentCharged đến muộn sau khi order đã bị `COMPENSATED`, orchestrator nên tự đổi về `PAYMENT_PENDING`?

**Không.** Cần kiểm tra nguyên nhân, operation ID và dữ liệu thật ở Payment Service; có thể phải refund/đối soát thêm. State guard ngăn worker hoặc event cũ đảo ngược trạng thái cuối một cách vô điều kiện.

## Kết luận

**Giao dịch phân tán, bù trừ và quy trình nghiệp vụ giải quyết những vấn đề khác nhau.** 2PC/XA phối hợp commit giữa những tài nguyên hỗ trợ giao thức; saga điều phối các local transaction có thể cần bù trừ; TCC sử dụng ý tưởng giữ–xác nhận–hủy khi nghiệp vụ cho phép. Không mô hình nào xóa được sự tồn tại của timeout, kết quả chưa rõ, sự kiện lặp hay tác dụng phụ không thể đảo.

Khi xây dựng nền tảng persistence cho Java, hãy bắt đầu từ **bất biến nghiệp vụ và ranh giới dữ liệu có thẩm quyền**, chọn transaction local mạnh ở mỗi service, lưu workflow state bền vững, phát lệnh qua outbox, nhận lệnh qua inbox/idempotency và thiết kế đường đối soát cả cho bước thuận lẫn bước bù trừ. Một workflow được xem là đáng tin khi có thể **giải thích, khôi phục và kiểm thử kết quả sau sự cố**, chứ không chỉ chạy trơn tru trên happy path.
