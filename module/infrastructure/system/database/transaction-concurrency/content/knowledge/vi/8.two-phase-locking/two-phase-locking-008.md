# Giới hạn của 2PL khi giao dịch chứa thao tác ngoài cơ sở dữ liệu

Two-Phase Locking (2PL, khóa hai pha) giúp database điều phối các transaction đồng thời bằng cách quy định thời điểm lấy và nhả lock. Cơ chế này có thể bảo đảm lịch thực thi tuần tự hóa được (conflict-serializable) khi các thao tác liên quan đều nằm trong phạm vi mà database quản lý.

Một transaction trong ứng dụng thực tế đôi khi còn gọi HTTP API, gửi email, phát thông điệp, ghi file hoặc yêu cầu một dịch vụ thanh toán thực hiện giao dịch. Những thao tác đó nằm ngoài phạm vi quản lý lock và rollback của database. Vì vậy, 2PL không thể tự bảo đảm toàn bộ quy trình nghiệp vụ là nguyên tử.

Vấn đề xuất hiện rõ nhất khi ứng dụng thực hiện I/O bên ngoài trong lúc transaction database vẫn mở: lock có thể bị giữ lâu trong khi ứng dụng chờ mạng; dịch vụ bên ngoài có thể đã thực hiện hành động dù transaction database sau đó rollback; hoặc database đã commit nhưng lệnh gọi dịch vụ bên ngoài thất bại. Muốn thiết kế đúng, cần xác định ranh giới của transaction và phối hợp thêm các mẫu xử lý như Transactional Outbox, idempotency và Saga.

## 1. 2PL bảo đảm điều gì?

Theo quy tắc 2PL, vòng đời lock của một transaction có hai pha:

1. **Growing phase (pha tăng trưởng):** transaction có thể lấy thêm lock, nhưng chưa nhả lock nào.
2. **Shrinking phase (pha thu hẹp):** transaction bắt đầu nhả lock và không được lấy thêm lock mới.

Khi đã nhả lock đầu tiên, transaction không thể quay lại lấy một lock khác. Quy tắc này giới hạn thứ tự lấy và nhả lock để lịch thực thi các thao tác xung đột có thể được tuần tự hóa.

~~~text
Thời gian ----------------------------------------------------->

Growing phase                 Shrinking phase
lấy lock                      nhả lock
   |                              |
   v                              v
   L1 ---- L2 ---- L3 ----------- U1 ---- U2 ---- COMMIT
   |<-- có thể lấy thêm -->|      |<-- chỉ nhả lock -->|

   Sau U1, transaction không được lấy thêm lock.
~~~

Trong thực tế cần phân biệt 2PL tổng quát với **Strict 2PL**:

- 2PL quy định ranh giới giữa pha lấy lock và pha nhả lock.
- Strict 2PL giữ các exclusive lock đến khi transaction commit hoặc rollback. Cách này tránh việc transaction khác đọc hoặc ghi dữ liệu chưa commit trong những trường hợp tương ứng.
- Một số hệ quản trị còn giữ cả shared lock đến cuối transaction hoặc dùng biến thể nghiêm ngặt hơn. Chi tiết phụ thuộc engine và isolation level.

2PL điều phối các thao tác trên tài nguyên mà lock manager của database quản lý. Nó không tự quản lý trạng thái của máy chủ email, cổng thanh toán, dịch vụ giao hàng, broker hoặc filesystem. Database cũng không thể rollback một hành động đã được hệ thống bên ngoài thực hiện chỉ bằng câu lệnh ROLLBACK.

Đây là ranh giới quan trọng: **2PL có thể kiểm soát lịch truy cập dữ liệu trong database, nhưng không tự mở rộng thành transaction phân tán bao trùm mọi hệ thống mà ứng dụng gọi đến.**

## 2. Giới hạn thứ nhất: lock bị giữ trong lúc chờ I/O bên ngoài

Giả sử ứng dụng tạo đơn hàng, cập nhật tồn kho rồi gọi dịch vụ thanh toán ngay trong một transaction:

~~~text
BEGIN DATABASE TRANSACTION
    |
    +-- Đọc đơn hàng và tồn kho
    |
    +-- Lấy lock trên các dòng cần cập nhật
    |
    +-- Gọi Payment API
    |       |
    |       +-- Chờ mạng, xử lý, retry hoặc timeout
    |
    +-- Ghi kết quả thanh toán vào database
    |
COMMIT
~~~

Trong lúc ứng dụng chờ Payment API, transaction database vẫn chưa kết thúc. Theo cách quản lý lock của engine, các lock cần giữ đến commit hoặc rollback vẫn đang được giữ. Một transaction khác muốn cập nhật cùng dòng tồn kho hoặc đơn hàng có thể phải chờ.

Thời gian giữ lock khi đó không còn chỉ phụ thuộc vào tốc độ truy vấn database. Nó bao gồm cả độ trễ mạng, thời gian xử lý của nhà cung cấp, retry và thời gian chờ timeout.

Ví dụ, một câu lệnh cập nhật chỉ mất vài mili giây, nhưng dịch vụ bên ngoài mất ba giây mới phản hồi. Nếu ứng dụng giữ transaction mở suốt ba giây, lock có thể tồn tại lâu hơn nhiều so với thời gian thực sự cần để cập nhật dữ liệu.

### Hệ quả đối với hệ thống

| Hệ quả | Vì sao xảy ra |
|---|---|
| Tăng lock wait | Transaction khác cần tài nguyên đang bị giữ trong lúc chờ dịch vụ bên ngoài |
| Giảm throughput | Ít transaction có thể đồng thời đi qua vùng dữ liệu đang tranh chấp |
| Tăng nguy cơ deadlock | Transaction giữ lock lâu hơn, làm các chuỗi chờ có thêm thời gian hình thành |
| Tăng số transaction timeout | Thời gian gọi dịch vụ cộng thêm vào thời gian transaction và có thể vượt giới hạn |
| Giữ connection lâu | Connection database và tài nguyên transaction bị chiếm trong lúc ứng dụng không thực hiện truy vấn |
| Khó dự đoán tải | Độ trễ của hệ thống bên ngoài biến động truyền sang thời gian giữ tài nguyên database |

Một dịch vụ bên ngoài chậm hoặc mất kết nối có thể khiến database chịu áp lực dù bản thân truy vấn SQL vẫn nhanh. Khi nhiều request đồng thời chờ cùng một nhà cung cấp, số transaction mở và số connection bị giữ có thể tăng mạnh.

Không phải mọi transaction đều cần giữ mọi lock trong suốt thời gian đó; phạm vi và thời điểm giải phóng phụ thuộc loại lock, engine và isolation level. Tuy nhiên, với Strict 2PL, exclusive lock được giữ đến khi transaction kết thúc. Nếu transaction còn chờ I/O bên ngoài, các exclusive lock đó tiếp tục tồn tại.

## 3. Giới hạn thứ hai: rollback database không hoàn tác được hành động bên ngoài

Giả sử một ứng dụng đặt hàng và thanh toán. Nó gọi cổng thanh toán thành công, sau đó ghi kết quả vào database nhưng gặp lỗi trước khi commit.

~~~text
Ứng dụng                 Database                Payment Provider
   |                         |                           |
   |--- BEGIN -------------->|                           |
   |--- UPDATE order ------->|                           |
   |                         |                           |
   |--- Charge payment -------------------------------->|
   |                         |<------ Payment success ---|
   |                         |                           |
   |--- UPDATE payment ----->|                           |
   |                         X lỗi trước COMMIT          |
   |--- ROLLBACK ----------->|                           |
   |                         |                           |
   |  Database đã rollback; nhà cung cấp vẫn đã thu tiền |
~~~

Sau rollback:

- Database có thể không ghi nhận khoản thanh toán thành công.
- Nhà cung cấp thanh toán vẫn có giao dịch đã được chấp nhận.
- Người dùng có thể bị trừ tiền dù đơn hàng trong database trở về trạng thái chưa thanh toán.

Điều này không vi phạm quy tắc 2PL. Lock manager đã thực hiện công việc của nó trong phạm vi database. Vấn đề nằm ở chỗ hành động thanh toán đã diễn ra tại một hệ thống không tham gia transaction database.

Cùng một giới hạn xuất hiện với các hành động khác:

- Email đã gửi không thể được thu hồi bằng rollback.
- Tin nhắn đã được broker hoặc consumer xử lý không tự biến mất khi database rollback.
- File đã ghi ra filesystem không bị xóa bởi ROLLBACK của database.
- Lệnh tạo shipment đã được dịch vụ vận chuyển chấp nhận không tự hủy khi transaction cục bộ thất bại.
- Một HTTP request đã kích hoạt quy trình tại dịch vụ khác không thể được đảo ngược chỉ bằng cách rollback dữ liệu cục bộ.

Có thể viết một thao tác bù để sửa hậu quả, nhưng đó là một hành động nghiệp vụ mới, không phải rollback nguyên tử của database. Thao tác bù cũng có thể thất bại hoặc chỉ khôi phục được một phần.

## 4. Giới hạn thứ ba: timeout tạo ra kết quả không chắc chắn

Một tình huống khó xử lý là ứng dụng gửi request đến dịch vụ bên ngoài rồi hết thời gian chờ:

~~~text
Ứng dụng                         Dịch vụ bên ngoài
   |                                    |
   |-------- POST /payments ---------->|
   |                                    |
   |                         Đã nhận và xử lý request
   |                                    |
   |<--- Response bị mất hoặc trễ -------X
   |
   +-- Ứng dụng nhận timeout
~~~

Timeout chỉ cho biết ứng dụng không nhận được phản hồi trong khoảng thời gian cho phép. Nó không chứng minh dịch vụ bên ngoài chưa thực hiện hành động.

Nếu ứng dụng retry ngay bằng một request mới, có thể xảy ra:

- Request đầu đã được xử lý nhưng response bị mất.
- Request retry được xử lý lần nữa.
- Người dùng bị thu tiền hai lần hoặc hệ thống tạo hai shipment, hai ticket hay hai thông báo.

Đây là lý do cần phân biệt ba trạng thái:

- **Thành công đã xác nhận:** nhận được phản hồi đủ để xác định thao tác đã thành công.
- **Thất bại đã xác nhận:** dịch vụ trả kết quả cho biết thao tác không được thực hiện.
- **Kết quả chưa xác định:** timeout, mất kết nối hoặc lỗi xảy ra trước khi ứng dụng biết kết quả cuối cùng.

Không nên coi trạng thái thứ ba là thất bại chắc chắn. Ứng dụng cần tra cứu trạng thái hoặc retry bằng cùng một khóa idempotency theo hợp đồng của dịch vụ.

## 5. Giới hạn thứ tư: không thể vừa giữ 2PL vừa chờ vô hạn để bảo đảm mọi hệ thống cùng thành công

Một transaction có thể cố gắng giữ lock trong khi chờ tất cả dịch vụ bên ngoài phản hồi. Cách này tạo cảm giác rằng dữ liệu database chỉ commit khi mọi việc đã hoàn tất. Nhưng nếu dịch vụ chậm, hệ thống phải trả giá bằng lock wait và connection bị giữ lâu.

Nếu ứng dụng nhả lock sớm để tránh chờ, nó phải giải quyết một bài toán khác: dữ liệu có thể thay đổi trong lúc dịch vụ bên ngoài đang xử lý. Khi ứng dụng quay lại, giả định ban đầu có thể đã không còn đúng.

Ví dụ, ứng dụng kiểm tra còn một chỗ trong lớp học, sau đó gọi dịch vụ thu phí. Nếu transaction nhả lock và một request khác đặt chỗ cuối cùng trước khi request đầu hoàn tất, ứng dụng phải xử lý tình huống cả hai bên đều có thể đã tiến hành thanh toán.

Vì vậy, chỉ chuyển lời gọi HTTP ra ngoài transaction chưa đủ. Ứng dụng cần xác định một quy trình nghiệp vụ có trạng thái trung gian, có quy tắc giữ chỗ, xác nhận, hủy hoặc bù trừ.

Một cách nhìn hữu ích:

| Cách làm | Vấn đề cần giải quyết |
|---|---|
| Giữ transaction trong lúc gọi dịch vụ | Lock và connection bị giữ lâu; hành động bên ngoài vẫn không rollback cùng database |
| Commit trước rồi gọi dịch vụ | Có thể crash sau commit nhưng trước khi gọi dịch vụ |
| Nhả lock rồi tiếp tục xử lý | Dữ liệu có thể bị transaction khác thay đổi trong khoảng trống |
| Dùng transaction phân tán | Chỉ phù hợp khi tất cả participant hỗ trợ giao thức và cùng tham gia transaction |

Không có biến thể 2PL nào tự giải quyết được mọi vấn đề trên, vì các hệ thống bên ngoài nằm ngoài phạm vi lock manager.

## 6. Thiết kế phổ biến: tách transaction database khỏi lời gọi bên ngoài

Một hướng thiết kế thường dùng là để transaction database hoàn thành nhanh, ghi nhận ý định cần thực hiện, sau đó xử lý I/O bên ngoài bằng một worker.

Ví dụ với đơn hàng:

1. Transaction database kiểm tra điều kiện nghiệp vụ, tạo đơn hàng ở trạng thái **PENDING_PAYMENT** và ghi một bản ghi sự kiện cần gửi.
2. Transaction commit, giải phóng lock.
3. Worker đọc sự kiện và gọi Payment API.
4. Worker ghi kết quả thanh toán vào database trong một transaction ngắn khác.
5. Đơn hàng chuyển sang **PAID** hoặc **PAYMENT_FAILED** theo kết quả đã xác nhận.

~~~text
Request API
    |
    v
Database transaction A
    |
    +-- Tạo Order: PENDING_PAYMENT
    |
    +-- Tạo Outbox event: PaymentRequested
    |
    +-- COMMIT
             |
             v
       Outbox Worker
             |
             +-- Gọi Payment API
             |
             +-- Nhận kết quả
             |
             v
Database transaction B
    |
    +-- Cập nhật Payment/Order
    |
    +-- COMMIT
~~~

Cách này rút ngắn thời gian giữ lock trong database. Tuy nhiên, nó cần một cơ chế chuyển sự kiện đáng tin cậy và xử lý trường hợp gửi lặp.

### 6.1. Transactional Outbox

Transactional Outbox lưu sự kiện cần phát trong cùng transaction database với thay đổi nghiệp vụ.

Ví dụ:

~~~sql
BEGIN;

INSERT INTO orders (order_id, status, total_amount)
VALUES (1001, 'PENDING_PAYMENT', 500000);

INSERT INTO outbox_events (event_id, event_type, aggregate_id, payload, status)
VALUES (
    'evt-1001',
    'PaymentRequested',
    '1001',
    '{"orderId":1001,"amount":500000}',
    'PENDING'
);

COMMIT;
~~~

Hai thay đổi được commit cùng nhau:

- Nếu transaction rollback, đơn hàng và outbox event đều không được lưu.
- Nếu transaction commit, cả đơn hàng lẫn yêu cầu cần xử lý đều tồn tại.

Một worker đọc các bản ghi outbox chưa xử lý và gửi chúng đến dịch vụ đích. Nhờ vậy, ứng dụng tránh được khoảng trống nguy hiểm giữa việc commit dữ liệu nghiệp vụ và việc cố gắng phát thông điệp.

Tuy nhiên, Outbox không làm cho HTTP request hoặc việc gửi message trở thành exactly-once. Worker có thể gửi thành công nhưng crash trước khi đánh dấu event đã xử lý. Khi chạy lại, nó có thể gửi event lần nữa. Vì vậy, phía nhận vẫn cần xử lý lặp an toàn.

### 6.2. Idempotency ở phía dịch vụ nhận

Một thao tác idempotent có thể được thực hiện lặp lại mà kết quả nghiệp vụ tương đương với thực hiện một lần, theo hợp đồng của thao tác đó.

Ứng dụng có thể tạo một khóa duy nhất cho mỗi ý định nghiệp vụ, ví dụ **payment-order-1001**, và gửi khóa đó trong mọi lần retry. Dịch vụ nhận lưu khóa cùng kết quả đã xử lý. Khi nhận lại cùng khóa, dịch vụ trả kết quả cũ hoặc xác định request đã được xử lý thay vì tạo một khoản thanh toán mới.

~~~text
Lần gửi 1:
    Idempotency-Key: payment-order-1001
    -> Nhà cung cấp tạo giao dịch P-778
    -> Response bị mất

Lần retry:
    Idempotency-Key: payment-order-1001
    -> Nhà cung cấp nhận ra khóa đã xử lý
    -> Trả lại kết quả giao dịch P-778
    -> Không tạo khoản thu thứ hai
~~~

Khóa idempotency cần ổn định qua các lần retry của cùng một ý định nghiệp vụ. Không tạo khóa mới cho mỗi lần gửi lại, vì như vậy dịch vụ nhận có thể coi mỗi request là một thao tác khác nhau.

Idempotency cũng cần được hỗ trợ và thực thi đúng ở phía dịch vụ nhận. Nếu API không có cơ chế này, ứng dụng phải dùng khả năng tra cứu giao dịch, đối soát hoặc một quy trình bảo vệ khác theo hợp đồng của nhà cung cấp.

## 7. Khi quy trình có nhiều bước: dùng Saga và thao tác bù

Với một quy trình đi qua nhiều dịch vụ, chẳng hạn đặt hàng, thanh toán và tạo vận đơn, không thể giả định tất cả dịch vụ cùng tham gia một transaction database.

Saga mô hình hóa quy trình thành nhiều bước cục bộ. Mỗi bước commit trong hệ thống của nó. Nếu bước sau thất bại, quy trình có thể chạy các **compensating action** để đưa nghiệp vụ về một trạng thái chấp nhận được.

Ví dụ:

| Bước | Hành động chính | Hành động bù có thể có |
|---|---|---|
| 1 | Tạo đơn hàng ở trạng thái chờ | Hủy đơn hàng |
| 2 | Giữ hoặc trừ tồn kho | Hoàn tồn kho hoặc giải phóng giữ chỗ |
| 3 | Thu tiền | Hoàn tiền |
| 4 | Tạo vận đơn | Hủy vận đơn nếu nhà vận chuyển cho phép |

Luồng khái quát:

~~~text
Tạo đơn hàng
    |
    v
Giữ tồn kho
    |
    v
Thanh toán
    |
    v
Tạo vận đơn
    |
    +---- Thành công toàn bộ ----> Order COMPLETED
    |
    +---- Một bước thất bại
                |
                v
         Chạy các bước bù
                |
                v
         Order COMPENSATING
                |
                +---- Bù thành công ---> Order CANCELLED
                |
                +---- Bù thất bại -----> Order NEEDS_REVIEW
~~~

Saga không cung cấp rollback nguyên tử giống transaction database. Một khoản tiền đã thu rồi hoàn lại vẫn có thể tạo ra phí, thời gian chờ hoặc dấu vết nghiệp vụ. Nhà vận chuyển có thể đã nhận lệnh và không cho hủy. Vì vậy, hành động bù phải được định nghĩa theo quy tắc nghiệp vụ, có thể retry, có idempotency và có trạng thái để theo dõi.

Saga phù hợp khi quy trình cần tiến triển qua nhiều dịch vụ độc lập và chấp nhận trạng thái trung gian. Nó đòi hỏi thiết kế trạng thái, timeout, retry, đối soát và xử lý bù rõ ràng.

## 8. Giữ tính đúng đắn khi không giữ lock suốt lời gọi bên ngoài

Khi transaction kết thúc trước khi gọi dịch vụ, dữ liệu có thể thay đổi trước lúc worker xử lý. Ứng dụng cần chọn cơ chế bảo vệ phù hợp với nghiệp vụ.

### 8.1. Trạng thái trung gian và reservation có thời hạn

Với hàng tồn kho hoặc chỗ đặt trước, có thể tạo reservation có thời hạn thay vì giữ database transaction mở trong lúc chờ thanh toán.

Ví dụ:

~~~sql
BEGIN;

UPDATE inventory
SET available_quantity = available_quantity - 1
WHERE product_id = 42
  AND available_quantity > 0;

-- Ứng dụng kiểm tra số dòng được cập nhật.
-- Nếu bằng 1, tạo reservation có thời hạn.
INSERT INTO reservations (reservation_id, product_id, status, expires_at)
VALUES ('res-1001', 42, 'HELD', CURRENT_TIMESTAMP + INTERVAL '10' MINUTE);

COMMIT;
~~~

Đoạn SQL trên mang tính minh họa; cú pháp interval và cách bảo đảm tính nguyên tử giữa cập nhật tồn kho với reservation phụ thuộc hệ quản trị. Trong triển khai thực tế, hai thao tác cần nằm trong cùng transaction và ứng dụng phải kiểm tra điều kiện cập nhật thành công.

Worker có thể gọi dịch vụ thanh toán sau khi transaction đã commit. Nếu thanh toán thành công, reservation được xác nhận. Nếu thất bại hoặc hết hạn, quy trình giải phóng số lượng đã giữ bằng một transaction khác.

Reservation là trạng thái nghiệp vụ có thời hạn. Nó không phải lock database được giữ trong nhiều phút. Hệ thống cần xử lý chính xác việc hết hạn đồng thời với việc thanh toán thành công để không giải phóng một reservation đã được xác nhận.

### 8.2. Optimistic locking và version

Nếu ứng dụng đọc dữ liệu, gọi dịch vụ bên ngoài rồi quay lại cập nhật, dữ liệu có thể đã bị thay đổi. Một cột version giúp phát hiện trường hợp này.

~~~sql
UPDATE orders
SET status = 'PAID',
    version = version + 1
WHERE order_id = 1001
  AND status = 'PENDING_PAYMENT'
  AND version = 7;
~~~

Nếu số dòng được cập nhật bằng 0, trạng thái hoặc version đã thay đổi so với giả định ban đầu. Ứng dụng phải đọc lại và quyết định xử lý tiếp, thay vì ghi đè một thay đổi mới hơn.

Optimistic locking giúp phát hiện xung đột khi cập nhật. Nó không tự hoàn tác khoản tiền mà dịch vụ bên ngoài đã thu. Nếu thanh toán đã thành công nhưng cập nhật trạng thái thất bại, quy trình vẫn cần tra cứu giao dịch, retry cập nhật hoặc chạy bước bù theo quy tắc nghiệp vụ.

### 8.3. Ghi nhận kết quả và đối soát

Đối với những thao tác có kết quả không xác định, hệ thống nên lưu mã tham chiếu của nhà cung cấp, idempotency key và trạng thái xử lý. Một tác vụ đối soát có thể tra cứu các giao dịch đang ở trạng thái **UNKNOWN** hoặc **PENDING_CONFIRMATION** để xác định kết quả cuối cùng.

Không nên chuyển một giao dịch timeout thành **FAILED** ngay nếu nhà cung cấp chưa xác nhận thất bại. Trạng thái trung gian giúp ứng dụng tránh thực hiện lại một hành động có thể đã thành công.

## 9. Khi nào transaction phân tán là lựa chọn phù hợp?

Two-Phase Commit (2PC) là một giao thức phối hợp commit giữa nhiều participant có hỗ trợ transaction phân tán. Coordinator yêu cầu các participant chuẩn bị commit, sau đó quyết định commit hoặc abort dựa trên kết quả chuẩn bị.

2PC có thể giúp nhiều resource manager tham gia một transaction chung nếu chúng hỗ trợ giao thức và được cấu hình đúng. Nhưng một REST API thông thường, một thao tác gửi email hoặc một filesystem không tự trở thành participant của 2PC chỉ vì ứng dụng gọi chúng trong lúc transaction database đang mở.

Ngay cả khi có 2PC, hệ thống vẫn phải cân nhắc:

- Các participant có thật sự hỗ trợ cùng giao thức và transaction manager tương thích hay không.
- Chi phí phối hợp, cấu hình, vận hành và phục hồi khi coordinator gặp sự cố.
- Khả năng transaction bị giữ ở trạng thái prepared trong lúc chờ quyết định.
- Tài nguyên bị khóa hoặc giữ chỗ lâu hơn trong quá trình phối hợp.
- Việc hệ thống bên ngoài có đáp ứng yêu cầu transaction và tính nhất quán của nghiệp vụ hay không.

2PC phù hợp khi cần commit nguyên tử giữa các resource manager có hỗ trợ transaction phân tán và chấp nhận chi phí vận hành của mô hình đó. Với các dịch vụ HTTP độc lập, Outbox, idempotency và Saga thường thực tế hơn.

## 10. Chọn cách thiết kế theo loại thao tác bên ngoài

| Thao tác | Rủi ro chính | Hướng xử lý thường phù hợp |
|---|---|---|
| Gửi email xác nhận | Email có thể đã gửi dù database rollback; retry có thể gửi trùng | Outbox, event id ổn định, xử lý gửi lặp |
| Phát message | Message có thể được broker nhận dù worker chưa ghi nhận đã gửi | Transactional Outbox và consumer idempotent |
| Thu tiền | Timeout không cho biết chắc đã thu hay chưa; retry có thể thu trùng | Idempotency key, tra cứu giao dịch, Outbox, Saga và đối soát |
| Tạo vận đơn | Dịch vụ vận chuyển có thể đã tạo vận đơn dù ứng dụng mất response | Idempotency, tra cứu theo mã yêu cầu, thao tác hủy nếu được hỗ trợ |
| Ghi file | File có thể tồn tại dù transaction database rollback | Ghi file tạm, xác nhận bằng trạng thái database, cơ chế dọn dẹp hoặc đối soát |
| Gọi dịch vụ đọc dữ liệu | Kết quả bên ngoài có thể thay đổi trong khi transaction đang mở | Gọi ngoài transaction nếu phù hợp; xác định rõ yêu cầu về snapshot và version |
| Cập nhật hệ thống khác | Hai hệ thống có thể lệch trạng thái khi một bên thất bại | Outbox, Saga, retry và quy trình đối soát |

Không có một mẫu duy nhất phù hợp cho mọi loại I/O. Hãy chọn theo khả năng retry, tính đảo ngược của hành động, yêu cầu nhất quán và hợp đồng API của hệ thống đích.

## 11. Nguyên tắc thiết kế thực tế

Khi một use case vừa cập nhật database vừa gọi dịch vụ bên ngoài, có thể lần lượt đặt ra các câu hỏi sau:

1. **Thao tác nào thực sự phải nguyên tử trong database?** Đưa những thay đổi dữ liệu liên quan vào cùng một transaction ngắn.
2. **Có thể ghi nhận ý định trước khi gọi dịch vụ không?** Nếu có, lưu outbox event hoặc trạng thái chờ trong cùng transaction với dữ liệu nghiệp vụ.
3. **Nếu ứng dụng crash sau commit thì sao?** Cần worker có thể tiếp tục xử lý từ dữ liệu đã lưu.
4. **Nếu dịch vụ đã xử lý nhưng response bị mất thì sao?** Cần idempotency key hoặc khả năng tra cứu theo mã tham chiếu.
5. **Nếu bước sau thất bại thì nghiệp vụ cần làm gì?** Định nghĩa hành động bù, trạng thái trung gian và quy trình xử lý khi bù thất bại.
6. **Dữ liệu có thể thay đổi trong thời gian chờ không?** Dùng reservation, version hoặc điều kiện cập nhật để xác nhận giả định vẫn còn đúng.
7. **Có cần đối soát không?** Với thanh toán, vận chuyển và các thao tác có hậu quả tài chính hoặc vận hành, cần cơ chế phát hiện trạng thái lệch giữa các hệ thống.

Một transaction database nên giữ lock trong khoảng thời gian cần thiết để bảo vệ thay đổi dữ liệu thuộc transaction đó. Việc gọi mạng hoặc chờ người dùng thường nên được biểu diễn thành bước nghiệp vụ riêng, có trạng thái và khả năng phục hồi.

## Kết luận

2PL giúp database kiểm soát xung đột giữa các transaction trên tài nguyên mà database quản lý. Khi một transaction chứa thao tác ngoài cơ sở dữ liệu, giới hạn của cơ chế này xuất hiện ở hai điểm: thời gian chờ bên ngoài có thể kéo dài thời gian giữ lock, và rollback database không thể đảo ngược hành động mà hệ thống khác đã thực hiện.

Thiết kế phù hợp thường chia quy trình thành các transaction database ngắn, ghi nhận sự kiện hoặc trạng thái cần xử lý, rồi thực hiện I/O bên ngoài bằng worker. Transactional Outbox giúp không bỏ sót ý định cần phát; idempotency giúp retry an toàn; Saga và thao tác bù xử lý quy trình nhiều bước; reservation và version giúp bảo vệ điều kiện nghiệp vụ khi không giữ lock suốt thời gian chờ.

Cần xem các cơ chế này là những phần bổ sung cho nhau. 2PL bảo vệ tính đúng đắn của truy cập dữ liệu trong database; ứng dụng cần thêm giao thức và trạng thái nghiệp vụ để điều phối những hệ thống nằm ngoài ranh giới đó.
