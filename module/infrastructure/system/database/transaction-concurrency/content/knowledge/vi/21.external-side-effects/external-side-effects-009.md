# Phân biệt lỗi điều khiển đồng thời trong một cơ sở dữ liệu với lỗi phối hợp liên hệ thống

Một ứng dụng có thể gặp lỗi khi nhiều giao dịch cùng cập nhật dữ liệu, hoặc khi nhiều dịch vụ độc lập cùng tham gia một quy trình nghiệp vụ. Hai nhóm vấn đề này thường xuất hiện cùng lúc, nhưng nguyên nhân và cách khắc phục khác nhau.

**Lỗi điều khiển đồng thời trong một cơ sở dữ liệu** xảy ra khi các transaction cạnh tranh trên dữ liệu thuộc cùng một ranh giới transaction của DBMS. Ví dụ: lost update, write skew, deadlock, lock timeout, unique violation hoặc serialization failure. DBMS có thể dùng khóa, MVCC, constraint và isolation level để điều phối các transaction và quyết định commit hay rollback.

**Lỗi phối hợp liên hệ thống** xảy ra khi một quy trình đi qua nhiều ranh giới commit độc lập, chẳng hạn ứng dụng cập nhật đơn hàng trong database rồi gọi cổng thanh toán, gửi message hoặc yêu cầu dịch vụ kho. Một hệ thống có thể commit thành công trong khi hệ thống khác thất bại, timeout hoặc chưa nhận được thông điệp. Transaction cục bộ không thể tự rollback hiệu ứng đã xảy ra trong dịch vụ bên ngoài.

Phân biệt đúng ranh giới lỗi giúp chọn đúng công cụ: khóa và isolation để bảo vệ dữ liệu trong một database; outbox, inbox, idempotency, saga, retry và reconciliation để phối hợp các hệ thống độc lập.

## 1. Bắt đầu từ ranh giới commit

Một transaction database thường gom nhiều câu lệnh vào một đơn vị nguyên tử. Nếu transaction rollback, các thay đổi thuộc transaction đó không được commit. Ví dụ, trừ tiền tài khoản A và cộng tiền tài khoản B trong cùng một database có thể nằm trong một transaction:

```sql
BEGIN;

UPDATE account
SET balance = balance - 200
WHERE account_id = 1
  AND balance >= 200;

-- Ứng dụng phải xác nhận đúng một hàng được cập nhật.

UPDATE account
SET balance = balance + 200
WHERE account_id = 2;

-- Ứng dụng cũng phải xác nhận tài khoản đích tồn tại.

COMMIT;
```

Nếu một bước không thỏa điều kiện, ứng dụng rollback transaction để không chỉ trừ tiền mà không cộng tiền. Các câu lệnh này vẫn có thể gặp deadlock hoặc serialization failure khi những transaction khác cùng thao tác; DBMS sẽ áp dụng cơ chế đồng thời tương ứng.

Nhưng nếu quy trình gồm cập nhật tài khoản trong database A và gọi API của ngân hàng B, `ROLLBACK` ở database A không thể tự hoàn tác một giao dịch mà ngân hàng B đã chấp nhận. Hai hệ thống có hai trạng thái commit và hai cơ chế phục hồi riêng.

```text
Một database:
  BEGIN
    UPDATE A
    UPDATE B
  COMMIT / ROLLBACK
  -> một ranh giới transaction do cùng DBMS quản lý

Hai hệ thống:
  COMMIT database A
  gọi API hệ thống B
  -> hai kết quả commit độc lập, có thể chỉ một bên thành công
```

Đây là tiêu chí đầu tiên khi phân loại sự cố: các thao tác đang lỗi có cùng nằm trong một transaction do cùng một DBMS quản lý hay không?

## 2. Nhóm lỗi điều khiển đồng thời bên trong một database

Các lỗi trong một database thường liên quan đến transaction, dữ liệu, khóa, phiên bản hoặc quy tắc isolation.

| Loại lỗi | Dấu hiệu | Nguyên nhân thường gặp | Cách xử lý ban đầu |
|---|---|---|---|
| Lost update | Thay đổi của transaction này bị ghi đè bởi transaction khác | Đọc cùng phiên bản rồi ghi mà không kiểm tra version hoặc khóa phù hợp | Conditional UPDATE, version token hoặc khóa phù hợp |
| Dirty read | Đọc thấy dữ liệu chưa commit của transaction khác | Isolation cho phép đọc dữ liệu chưa commit | Chọn isolation bảo vệ yêu cầu nghiệp vụ |
| Non-repeatable read | Đọc cùng hàng hai lần nhưng nhận giá trị khác | Transaction khác cập nhật/commit giữa hai lần đọc | Chọn mức cô lập hoặc snapshot phù hợp |
| Phantom read | Truy vấn cùng điều kiện nhưng tập hàng thay đổi | Transaction khác chèn/xóa hàng thỏa predicate | Predicate/range protection hoặc serializable semantics |
| Write skew | Các transaction cập nhật hàng khác nhau nhưng cùng phá một invariant nhiều hàng | Chỉ kiểm tra snapshot và khóa riêng hàng được ghi | Constraint, guard row, advisory lock hoặc SERIALIZABLE |
| Deadlock | Các transaction tạo thành chu trình chờ khóa | Lấy nhiều tài nguyên theo thứ tự khác nhau | Đọc deadlock graph, chuẩn hóa thứ tự truy cập, retry toàn transaction |
| Lock timeout | Transaction chờ quá thời hạn | Khóa đang bị giữ lâu, transaction treo hoặc tải cao | Xác định blocker, rút ngắn transaction, điều chỉnh timeout có chủ đích |
| Serialization failure | DBMS từ chối transaction để giữ lịch tuần tự hợp lệ | Phụ thuộc đọc/ghi không thể tuần tự hóa theo isolation đã chọn | Rollback và retry toàn bộ transaction nếu an toàn |
| Constraint violation | Unique, check hoặc foreign key bị vi phạm | Hai thao tác cạnh tranh hoặc dữ liệu không thỏa quy tắc | Xem constraint là hàng rào; chuyển lỗi thành phản hồi nghiệp vụ |
| Optimistic version mismatch | UPDATE theo version không tác động hàng nào | Entity đã cũ hoặc bị xóa | Reload, hợp nhất hoặc báo conflict |

Các lỗi này thường có bằng chứng ở DBMS: transaction ID, session ID, lock resource, wait type, constraint name, SQLSTATE, execution plan hoặc optimistic token. Câu hỏi điều tra tập trung vào transaction nào đọc/ghi tài nguyên nào và tại sao DBMS chặn hoặc từ chối commit.

### 2.1. Ví dụ deadlock trong một database

Transaction A khóa hàng tài khoản 1 rồi yêu cầu tài khoản 2. Transaction B khóa hàng tài khoản 2 rồi yêu cầu tài khoản 1. Hai transaction chờ nhau tạo thành chu trình.

```text
Transaction A                  Transaction B
  giữ Account 1                  giữ Account 2
  chờ Account 2                  chờ Account 1
       \                          /
        +------- deadlock --------+
```

DBMS có thể hủy một transaction làm victim. Ứng dụng nhận lỗi deadlock và có thể retry toàn bộ transaction với giới hạn. Cách sửa lâu dài thường là chuẩn hóa thứ tự cập nhật tài khoản, giảm thời gian giữ khóa hoặc điều chỉnh truy vấn/index dựa trên deadlock graph.

### 2.2. Ví dụ write skew

Một khoa có hai bác sĩ đang trực. Mỗi transaction đọc thấy còn hai người trực, sau đó tắt trạng thái trực của một bác sĩ khác nhau. Nếu cả hai chỉ khóa hàng mà mình sửa, cả hai có thể commit và khiến không còn ai trực.

Đây là lỗi bảo vệ invariant nhiều hàng. Thêm một khóa hàng riêng lẻ không nhất thiết giải quyết được. Cần bảo vệ phạm vi đọc bằng SERIALIZABLE, guard row hoặc cơ chế tương đương; constraint phù hợp cũng có thể được dùng nếu mô hình dữ liệu cho phép.

## 3. Nhóm lỗi phối hợp giữa nhiều hệ thống

Khi quy trình đi qua nhiều hệ thống, mỗi hệ thống có thể commit độc lập. Những lỗi phổ biến gồm:

| Loại lỗi | Ví dụ | Vì sao transaction cục bộ không đủ? |
|---|---|---|
| Dual-write failure | DB đã lưu đơn hàng nhưng publish message thất bại | Commit DB và publish broker là hai thao tác độc lập |
| Partial success | Thanh toán thành công nhưng cập nhật đơn hàng thất bại | Không có rollback tự động xuyên qua hai dịch vụ |
| Timeout không rõ kết quả | Client timeout khi gọi API thanh toán | Request có thể đã được xử lý dù response bị mất |
| Message delivery lặp | Consumer nhận cùng event nhiều lần | Broker có thể giao lại sau timeout hoặc mất ACK |
| Message đến sai thứ tự | `OrderPaid` đến trước `OrderCreated` | Mạng và broker có thể trì hoãn, retry hoặc phân vùng message |
| Dịch vụ phụ thuộc không khả dụng | Kho không phản hồi khi đơn hàng đã được tạo | Mỗi dịch vụ có uptime và khả năng phục hồi riêng |
| Saga compensation thất bại | Đã giữ hàng nhưng thao tác hoàn tiền lỗi | Compensation là một hành động nghiệp vụ mới, cũng có thể lỗi |
| Dữ liệu đọc chưa đồng bộ | Màn hình đơn hàng chưa hiện trạng thái thanh toán mới | Read model hoặc replica có thể cập nhật trễ |
| Lease hết hạn trong khi worker cũ vẫn chạy | Worker mới nhận job nhưng worker cũ thức dậy | Lease không thể buộc tiến trình cũ dừng hoặc chặn hệ thống đích nếu không có fencing |

Ở nhóm này, cần theo dõi correlation ID, event ID, idempotency key, trạng thái workflow, outbox/inbox record, retry count và kết quả từ từng dịch vụ. Một lỗi HTTP timeout không cho biết chắc chắn thao tác bên ngoài đã thất bại; có thể response bị mất sau khi thao tác đã thành công.

## 4. Dual write: ví dụ kinh điển của ranh giới liên hệ thống

Giả sử dịch vụ Order cần lưu đơn hàng vào database rồi gửi `OrderCreated` đến broker để dịch vụ Inventory giữ hàng.

### Trình tự không an toàn A: commit DB trước, publish sau

```text
1. INSERT order
2. COMMIT database
3. publish OrderCreated
```

Nếu tiến trình chết sau bước 2 nhưng trước bước 3, đơn hàng tồn tại nhưng không có event. Inventory không biết cần giữ hàng. Retry toàn bộ request có thể tạo đơn hàng trùng nếu không có idempotency.

### Trình tự không an toàn B: publish trước, commit DB sau

```text
1. publish OrderCreated
2. INSERT order
3. COMMIT database
```

Nếu publish thành công nhưng database rollback, Inventory có thể giữ hàng cho một đơn hàng không tồn tại.

Không có cách sắp thứ tự hai thao tác độc lập nào loại bỏ hoàn toàn cửa sổ lỗi. Transaction DB chỉ bảo vệ các thay đổi bên trong DB đó.

## 5. Transactional outbox: nối commit database với việc phát sự kiện

Transactional outbox giải quyết dual-write giữa database và broker bằng cách ghi thay đổi nghiệp vụ cùng một bản ghi outbox trong cùng transaction database.

Ví dụ:

```sql
BEGIN;

INSERT INTO orders (order_id, customer_id, status)
VALUES (:order_id, :customer_id, 'PENDING');

INSERT INTO outbox_event (event_id, aggregate_id, event_type, payload, created_at)
VALUES (
    :event_id,
    :order_id,
    'OrderCreated',
    :payload,
    CURRENT_TIMESTAMP
);

COMMIT;
```

Nếu transaction commit, cả đơn hàng và event outbox cùng tồn tại. Nếu rollback, cả hai đều không tồn tại. Publisher riêng đọc outbox, gửi event đến broker rồi đánh dấu đã gửi.

```text
Order service transaction:
  INSERT order
  INSERT outbox event
  COMMIT

Publisher:
  đọc event chưa gửi
  publish event_id + payload
  đánh dấu published
```

Outbox loại bỏ cửa sổ “DB commit nhưng event chưa được lưu để phát”. Nhưng publisher vẫn có thể gửi lặp nếu broker đã nhận event rồi publisher chết trước khi đánh dấu `published`. Vì vậy, outbox thường tạo semantics at-least-once cho việc phát; consumer cần idempotency.

### 5.1. Claim outbox an toàn

Khi có nhiều publisher, cần claim từng nhóm event nguyên tử để tránh hai publisher cùng xử lý một hàng cùng lúc. Có thể dùng row lock với `SKIP LOCKED`, trạng thái lease, hoặc cơ chế claim tương ứng DBMS. Không giữ transaction DB mở trong lúc gọi broker; claim nhanh, commit, gửi, rồi ghi nhận kết quả bằng token/lease hoặc trạng thái có điều kiện.

Nếu publisher chết sau khi gửi nhưng trước khi đánh dấu thành công, lease hết hạn và event được gửi lại. Đây là lý do consumer phải nhận diện event bằng ID ổn định.

### 5.2. Consumer inbox và idempotency

Consumer có thể lưu event đã xử lý trong bảng inbox với unique key:

```sql
CREATE TABLE inbox_event (
    consumer_name VARCHAR(100) NOT NULL,
    event_id VARCHAR(100) NOT NULL,
    processed_at TIMESTAMP NOT NULL,
    PRIMARY KEY (consumer_name, event_id)
);
```

Trong cùng transaction với thay đổi nghiệp vụ của consumer:

```text
BEGIN
  INSERT inbox_event(consumer_name, event_id)
  nếu unique conflict: event đã xử lý, không áp dụng lại
  nếu insert thành công:
      áp dụng thay đổi nghiệp vụ
COMMIT
ACK message
```

Việc lưu inbox và thay đổi nghiệp vụ phải cùng transaction database. Nếu consumer commit thay đổi nghiệp vụ nhưng chết trước khi ACK, broker có thể giao lại event; unique key trong inbox giúp nhận ra event đã được xử lý. Nếu chỉ lưu inbox trước rồi thay đổi nghiệp vụ ở transaction khác, lỗi giữa hai bước có thể làm mất tác động.

## 6. Idempotency khi kết quả của request không rõ

Trong hệ thống phân tán, timeout không chứng minh thao tác thất bại. Ví dụ:

1. Order service gửi yêu cầu thanh toán.
2. Payment service xử lý và ghi nhận thanh toán thành công.
3. Response bị mất trên mạng.
4. Order service nhận timeout và không biết payment đã thành công hay chưa.

Nếu gửi yêu cầu mới với một ID khác, khách hàng có thể bị trừ tiền hai lần. Cần dùng **idempotency key** ổn định cho cùng một ý định nghiệp vụ, ví dụ `payment:order-123`.

Payment service lưu key cùng kết quả. Khi nhận lại cùng key, nó trả về kết quả đã lưu thay vì tạo khoản thanh toán mới. Cùng một key nhưng payload khác nhau nên được từ chối hoặc xử lý theo hợp đồng rõ ràng; không nên âm thầm tái sử dụng key cho một ý định khác.

Idempotency cần được áp dụng ở nơi hiệu ứng xảy ra. Nếu chỉ lưu key ở Order service nhưng Payment service không kiểm tra, yêu cầu lặp vẫn có thể tạo giao dịch thanh toán mới.

### Phân biệt retry với lặp tác động

Retry là hành vi gửi lại yêu cầu sau một lỗi tạm thời. Idempotency bảo đảm việc gửi lại cùng ý định không nhân đôi hiệu ứng. Hai khái niệm bổ sung cho nhau:

- Retry không có idempotency có thể gây duplicate.
- Idempotency không có retry có thể khiến công việc bị bỏ dở mãi mãi.
- Retry có giới hạn cùng idempotency key ổn định giúp phục hồi sau timeout mà không nhân đôi hiệu ứng.

## 7. Saga: phối hợp quy trình qua nhiều transaction

Khi một quy trình gồm nhiều dịch vụ, mỗi bước thường commit trong database của dịch vụ đó. **Saga** mô hình hóa quy trình thành một chuỗi local transaction. Nếu bước sau thất bại, hệ thống chạy các hành động bù trừ (compensation) cho những bước đã hoàn tất.

Ví dụ đặt hàng:

```text
Create order (Order service)
        |
        v
Reserve inventory (Inventory service)
        |
        v
Authorize payment (Payment service)
        |
        v
Confirm order (Order service)
```

Nếu Payment thất bại sau khi Inventory đã giữ hàng, saga có thể chạy `Release inventory` rồi chuyển order sang `CANCELLED` hoặc `PAYMENT_FAILED`.

```text
Create order
     |
     v
Reserve inventory
     |
     v
Authorize payment -- thất bại
     |
     v
Release inventory (compensation)
     |
     v
Mark order as failed
```

### 7.1. Compensation không phải rollback database

Rollback xóa bỏ các thay đổi chưa commit trong một transaction cục bộ. Compensation là một hành động nghiệp vụ mới được thực hiện sau khi một bước trước đã commit.

Ví dụ:

- `Reserve inventory` đã commit; compensation là `Release inventory`.
- `Charge payment` đã hoàn tất; compensation có thể là `Refund payment`.
- `Send notification` đã gửi; thường không thể thu hồi email đã đến người nhận; có thể gửi thông báo đính chính.

Compensation không nhất thiết đảo ngược vật lý mọi hiệu ứng. Hoàn tiền có thể mất thời gian, bị từ chối hoặc phát sinh phí. Do đó, saga cần trạng thái trung gian, retry compensation, timeout và quy trình vận hành cho trường hợp bù trừ không thành công.

### 7.2. Orchestration và choreography

| Kiểu | Cách hoạt động | Ưu điểm | Đánh đổi |
|---|---|---|---|
| Orchestration | Một coordinator điều khiển bước tiếp theo và compensation | Nhìn rõ trạng thái tổng thể, dễ theo dõi tiến trình | Coordinator cần bền vững, không trở thành điểm lỗi đơn |
| Choreography | Dịch vụ phát/nhận event và tự kích hoạt bước tiếp theo | Giảm phụ thuộc vào coordinator trung tâm | Luồng nghiệp vụ phân tán, khó quan sát chuỗi sự kiện và vòng lặp |

Dù chọn kiểu nào, trạng thái saga cần được lưu bền vững. Không nên chỉ giữ tiến trình trong bộ nhớ của một request đang chạy; process restart không được làm mất thông tin các bước đã commit và các compensation còn phải chạy.

## 8. Distributed transaction và Two-Phase Commit

Một số công nghệ hỗ trợ distributed transaction như XA/Two-Phase Commit (2PC). Coordinator yêu cầu các participant chuẩn bị commit, sau đó quyết định commit hoặc rollback toàn cục.

```text
Phase 1: PREPARE
  Coordinator -> DB A: prepare
  Coordinator -> DB B: prepare
  Participant giữ tài nguyên và ghi nhận trạng thái prepared

Phase 2: DECISION
  Nếu tất cả prepare thành công: quyết định COMMIT
  Nếu có participant thất bại: quyết định ROLLBACK
```

2PC có thể cung cấp atomic commit qua các participant hỗ trợ giao thức, nhưng có chi phí và giới hạn:

- Participant có thể giữ khóa/tài nguyên trong lúc chờ quyết định.
- Coordinator hoặc network gặp sự cố có thể khiến transaction ở trạng thái in-doubt.
- Tất cả participant phải hỗ trợ giao thức và được cấu hình đúng.
- Không thể biến một API HTTP bất kỳ, email server hoặc hệ thống bên ngoài thành XA participant chỉ bằng cách gọi nó trong transaction.
- Vận hành và khôi phục phức tạp hơn transaction cục bộ.

Vì vậy, 2PC phù hợp với một số hệ thống có hạ tầng transaction phân tán hỗ trợ rõ ràng. Với quy trình microservice dài, nhiều tác động ngoài hoặc yêu cầu tiếp tục hoạt động khi dịch vụ tạm mất kết nối, saga/outbox/idempotency thường phù hợp hơn.

## 9. Vì sao không nên giữ transaction database mở trong lúc gọi dịch vụ ngoài?

Một mẫu thường gây sự cố:

```java
@Transactional
public void placeOrder(OrderRequest request) {
    Order order = orderRepository.save(createOrder(request));

    paymentClient.charge(request.paymentDetails());

    order.markPaid();
}
```

Trong ví dụ này, transaction DB có thể giữ khóa và connection trong suốt thời gian chờ Payment API. Nếu API chậm hoặc timeout:

- Transaction giữ khóa lâu hơn, làm tăng lock wait và deadlock trong database.
- Connection pool bị chiếm dụng trong lúc chờ mạng.
- Payment có thể đã thành công dù ứng dụng nhận timeout.
- Database rollback không hoàn tác khoản charge ở Payment service.

Một thiết kế tốt hơn thường chia ranh giới:

1. Transaction ngắn tạo order ở trạng thái `PENDING` và ghi outbox event/command.
2. Publisher gửi yêu cầu thanh toán với idempotency key.
3. Payment service xử lý và phát kết quả.
4. Consumer cập nhật trạng thái order trong transaction cục bộ.
5. Nếu thất bại, saga thực hiện compensation hoặc chuyển sang trạng thái cần xử lý.

Điều này giảm thời gian giữ tài nguyên database và làm rõ trạng thái quy trình. Nó không loại bỏ độ trễ hoặc partial failure; thay vào đó, hệ thống lưu trạng thái để có thể tiếp tục và phục hồi.

## 10. Phân biệt lỗi bằng bằng chứng và nơi quan sát

Khi nhận một lỗi, hãy xác định nó xuất hiện ở đâu và ranh giới nào đã commit.

| Bằng chứng | Nghiêng về lỗi trong database | Nghiêng về lỗi phối hợp liên hệ thống |
|---|---|---|
| SQLSTATE, unique/check/FK violation | Có | Có thể là lỗi cục bộ của một participant |
| Deadlock graph, lock wait, blocker session | Có | Có thể xảy ra bên trong một dịch vụ, nhưng không mô tả toàn saga |
| Serialization failure/optimistic lock exception | Có | Một bước local transaction của workflow bị từ chối |
| HTTP timeout hoặc connection reset khi gọi dịch vụ | Không trực tiếp | Có; kết quả remote có thể chưa rõ |
| Message redelivery, duplicate event ID | Không trực tiếp | Có |
| Outbox event chưa publish | DB local có thể đã commit | Có; cần kiểm tra publisher/broker |
| Saga ở trạng thái chờ compensation | Không phải deadlock DB | Có; một bước nghiệp vụ hoặc bù trừ chưa hoàn tất |
| Replica/read model lag | Không nhất thiết là lỗi transaction | Có thể là độ trễ đồng bộ/nhất quán cuối cùng |

Không nên kết luận dựa vào một log đơn lẻ. Ví dụ, một lỗi unique violation trong consumer có thể là biểu hiện của event bị giao lặp; nguyên nhân gốc nằm ở semantics giao message hoặc idempotency chứ không phải index bị hỏng.

### 10.1. Định danh để nối các log

Một quy trình liên hệ thống cần các ID khác nhau cho mục đích khác nhau:

- `request_id`: một lần gọi API từ client.
- `correlation_id`: định danh xuyên suốt một quy trình nghiệp vụ.
- `causation_id`: event hoặc command trực tiếp gây ra event hiện tại.
- `event_id`: định danh duy nhất của một message.
- `idempotency_key`: định danh ổn định của một ý định có thể được gửi lại.
- `transaction_id`: định danh transaction cục bộ trong database.
- `saga_id`/`workflow_id`: định danh tiến trình nhiều bước.

Không dùng một ID thay thế tất cả. Một request có thể tạo nhiều transaction, một transaction có thể ghi nhiều event, và một event có thể được xử lý bởi nhiều consumer. Log có cấu trúc nên mang correlation ID cùng event/transaction ID phù hợp để nối các bước.

## 11. Bảng quyết định: nên dùng công cụ nào?

| Vấn đề cần giải quyết | Công cụ phù hợp để xem xét | Công cụ không đủ nếu dùng một mình |
|---|---|---|
| Hai transaction cập nhật cùng một hàng | Version check, atomic UPDATE, row lock | Chỉ kiểm tra ở UI |
| Nhiều transaction tạo cùng khóa nghiệp vụ | UNIQUE constraint, UPSERT | SELECT rồi INSERT không có bảo vệ |
| Deadlock trong một DB | Deadlock graph, thứ tự khóa nhất quán, retry | Idempotency key ở broker |
| Invariant nhiều hàng | SERIALIZABLE, guard row, predicate/range protection, constraint phù hợp | Version token trên một hàng riêng lẻ |
| DB commit và publish event phải cùng được ghi nhận | Transactional outbox | Hai lệnh DB commit và broker publish độc lập |
| Consumer có thể nhận message nhiều lần | Inbox/unique event ID, idempotent handler | Chỉ ACK sau khi xử lý mà không lưu trạng thái dedup |
| API remote timeout không rõ kết quả | Idempotency key và truy vấn trạng thái | Retry với key mới |
| Quy trình qua nhiều service cần bù trừ | Saga với trạng thái bền vững và compensation | DB rollback cục bộ |
| Cần atomic commit qua các DB hỗ trợ XA | 2PC/XA nếu hạ tầng phù hợp | Gọi API HTTP bên trong `@Transactional` |
| Worker có thể chết khi đang xử lý job | Lease, heartbeat, fencing và idempotency | Chỉ có cột `PROCESSING` không expiry |

## 12. Ví dụ tổng hợp: đặt hàng, giữ kho và thanh toán

Giả sử khách hàng đặt một sản phẩm. Quy trình gồm Order service, Inventory service và Payment service. Mỗi service sở hữu database riêng.

### Các trạng thái nghiệp vụ

| Thành phần | Trạng thái ví dụ |
|---|---|
| Order | `PENDING`, `CONFIRMED`, `CANCELLED`, `PAYMENT_FAILED` |
| Inventory reservation | `NOT_RESERVED`, `RESERVED`, `RELEASED`, `COMMITTED` |
| Payment | `NOT_REQUESTED`, `AUTHORIZED`, `CAPTURED`, `REFUNDED`, `FAILED` |

### Luồng thành công

1. Order service tạo order `PENDING` và outbox event `OrderCreated` trong cùng transaction.
2. Inventory nhận event với inbox/idempotency, giữ hàng và phát `InventoryReserved`.
3. Order workflow nhận `InventoryReserved`, gửi lệnh authorize payment với key ổn định `payment:order-123`.
4. Payment service xử lý idempotent và phát `PaymentAuthorized`.
5. Order service nhận event, cập nhật order `CONFIRMED` trong transaction cục bộ.
6. Inventory nhận lệnh commit reservation nếu nghiệp vụ cần bước xác nhận cuối.

### Luồng thất bại

Nếu Payment thất bại sau khi Inventory đã giữ hàng:

1. Saga ghi nhận `PaymentFailed`.
2. Order chuyển sang `PAYMENT_FAILED` hoặc `CANCELLED` theo quy tắc.
3. Saga phát lệnh `ReleaseInventory`.
4. Inventory giải phóng reservation idempotently và phát kết quả.
5. Nếu release thất bại tạm thời, saga retry; nếu lỗi kéo dài, đưa vào hàng đợi xử lý và cảnh báo vận hành.

Mỗi bước là một local transaction. Không có một transaction database duy nhất bao trùm cả ba service. Hệ thống đạt trạng thái nghiệp vụ cuối cùng thông qua event, idempotency, retry và compensation.

### Nếu response thanh toán bị timeout?

Order service không nên tạo một yêu cầu thanh toán mới với key khác. Nó nên truy vấn trạng thái theo idempotency key hoặc gửi lại cùng key. Payment service phải trả cùng kết quả đã lưu nếu yêu cầu trước đã thành công.

### Nếu consumer xử lý event hai lần?

Consumer dùng `(consumer_name, event_id)` làm unique key trong inbox. Việc áp dụng thay đổi nghiệp vụ và ghi inbox cùng transaction đảm bảo event đã được xử lý sẽ không áp dụng lại khi broker redeliver.

## 13. Reconciliation: phát hiện và sửa sai lệch còn sót lại

Outbox, inbox, idempotency và saga giảm rủi ro nhưng không làm mọi sự cố biến mất. Có thể vẫn có message bị cấu hình sai, compensation lỗi kéo dài, dữ liệu cũ từ hệ thống ngoài hoặc lỗi code.

**Reconciliation** là quy trình đối chiếu định kỳ giữa các nguồn dữ liệu để tìm trạng thái không nhất quán và tạo tác vụ sửa chữa có kiểm soát.

Ví dụ:

- Order `PENDING` quá lâu nhưng Payment đã `AUTHORIZED`.
- Payment `CAPTURED` nhưng Order vẫn `PAYMENT_FAILED`.
- Inventory reservation tồn tại nhưng order đã `CANCELLED`.
- Outbox event chưa publish quá ngưỡng thời gian.
- Saga đã bắt đầu compensation nhưng không có kết quả sau nhiều lần thử.

Reconciliation nên:

1. Xác định invariant xuyên hệ thống và nguồn dữ liệu có thẩm quyền cho từng trạng thái.
2. Tìm các bản ghi không khớp theo correlation ID/order ID/event ID.
3. Phân loại sai lệch có thể tự sửa và sai lệch cần con người xem xét.
4. Tạo lệnh sửa chữa idempotent, có audit và giới hạn retry.
5. Ghi lại kết quả đối chiếu để không lặp sửa chữa gây tác động mới.

Không nên sửa trực tiếp trạng thái một bên chỉ để làm hai màn hình trông giống nhau. Cần hiểu sự kiện nào đã xảy ra và hành động bù trừ nào hợp lệ về nghiệp vụ.

## 14. Các lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Cách phòng tránh |
|---|---|---|
| Cho rằng `@Transactional` bao trùm API ngoài | DB rollback nhưng dịch vụ ngoài vẫn đã commit | Dùng saga/outbox/idempotency hoặc XA nếu mọi participant thật sự hỗ trợ |
| Giữ transaction mở khi gọi API chậm | Giữ khóa và connection, tăng lock wait | Chia transaction thành các bước cục bộ ngắn |
| Commit DB rồi publish message riêng | Event có thể bị mất khi process chết | Ghi outbox trong cùng transaction DB |
| Publish rồi mới commit DB | Consumer có thể xử lý event cho dữ liệu chưa commit | Outbox hoặc transaction phân tán được hỗ trợ |
| Consumer giả định message chỉ đến một lần | Tác động bị nhân đôi khi redelivery | Inbox, unique event ID và idempotent handler |
| Retry API với idempotency key mới | Có thể tạo hiệu ứng mới dù request cũ đã thành công | Dùng key ổn định cho cùng ý định nghiệp vụ |
| Gọi compensation một lần rồi bỏ qua lỗi | Trạng thái saga bị kẹt | Lưu trạng thái, retry compensation và cảnh báo |
| Xem timeout là thất bại chắc chắn | Có thể thực hiện lặp một tác động đã thành công | Tra cứu kết quả hoặc gửi lại cùng idempotency key |
| Dùng distributed lock thay cho transaction | Có quyền xử lý nhưng các hệ thống vẫn commit độc lập | Kết hợp lease/fencing với workflow và idempotency |
| Không có reconciliation | Sai lệch tồn tại lâu mà không được phát hiện | Đối chiếu định kỳ và có quy trình sửa chữa |

## 15. Quy trình phân loại một sự cố

Khi một quy trình nghiệp vụ thất bại, hãy trả lời theo thứ tự:

1. **Ranh giới nào đang gặp lỗi?** Một transaction trong một DB, hay nhiều dịch vụ/database/broker?
2. **Đã commit ở đâu?** Xác định từng participant đã commit, rollback, timeout hay chưa rõ kết quả.
3. **Có lỗi transaction cụ thể không?** Đọc SQLSTATE, constraint, deadlock graph, lock wait, serialization failure hoặc optimistic version mismatch.
4. **Có lỗi giao tiếp không?** Kiểm tra timeout, retry, broker redelivery, event order và response bị mất.
5. **Có thể xảy ra duplicate không?** Kiểm tra idempotency key, event ID, inbox và unique constraint.
6. **Trạng thái workflow hiện tại là gì?** Xem saga state, outbox pending, reservation và payment status.
7. **Có compensation đang chờ không?** Kiểm tra retry count, lỗi cuối cùng và bước tiếp theo.
8. **Cần sửa dữ liệu hay chỉ retry?** Chỉ retry lỗi tạm thời; dùng reconciliation/compensation cho trạng thái đã commit một phần.
9. **Làm sao chứng minh đã sửa?** Kiểm tra invariant cục bộ, invariant xuyên hệ thống, duplicate rate, event lag và tuổi workflow.

Một sự cố có thể chứa cả hai nhóm. Ví dụ, Inventory consumer gặp deadlock trong database khi xử lý `OrderCreated`; sau đó broker redeliver event. Deadlock là lỗi cục bộ của Inventory DB, còn redelivery là hành vi phối hợp message. Cần retry transaction cục bộ đồng thời bảo đảm consumer idempotent để event lặp không giữ hàng hai lần.

## 16. Nguyên tắc thiết kế

- Dùng transaction database để bảo vệ các thay đổi thuộc cùng một ranh giới DB.
- Viết invariant trước khi chọn isolation, khóa hoặc cơ chế retry.
- Dùng constraint và atomic DML khi có thể bảo vệ quy tắc trực tiếp.
- Giữ transaction ngắn; tránh chờ network hoặc người dùng trong khi đang giữ khóa.
- Với DB commit cộng publish event, dùng transactional outbox.
- Với consumer có thể nhận lại message, dùng inbox hoặc idempotent handler.
- Với request remote có kết quả không rõ, dùng idempotency key ổn định và khả năng truy vấn trạng thái.
- Với quy trình nhiều service, dùng saga và compensation có trạng thái bền vững.
- Dùng lease/fencing để kiểm soát worker cũ; lease đơn thuần không dừng được tiến trình cũ.
- Có retry giới hạn, backoff, dead-letter và reconciliation.
- Dùng correlation ID và event/transaction ID để nối bằng chứng xuyên suốt quy trình.

Điều khiển đồng thời trong một database bảo vệ các transaction cạnh tranh trên cùng tập dữ liệu và ranh giới commit. Phối hợp liên hệ thống xử lý các bước nghiệp vụ có thể thành công hoặc thất bại độc lập. Một ứng dụng đáng tin cậy cần cả hai lớp: transaction, constraint và isolation ở từng database; outbox, inbox, idempotency, saga và reconciliation giữa các hệ thống. Xác định đúng nơi commit và nơi phát sinh lỗi là bước quyết định để chọn cơ chế phục hồi phù hợp.
