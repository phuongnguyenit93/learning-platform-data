# Cho rằng rollback khôi phục mọi mã sinh và tác động ngoài cơ sở dữ liệu

Một transaction database có thể thực hiện nhiều thao tác rồi bị `ROLLBACK`. Các thay đổi dữ liệu thuộc transaction đó thường được hoàn tác, nhưng điều này **không có nghĩa mọi thứ đã xảy ra trong lúc transaction chạy đều quay về trạng thái ban đầu**.

Một số cơ chế sinh mã như sequence, identity hoặc auto-increment có thể đã tiêu thụ giá trị và không trả lại giá trị đó khi rollback. Một email đã gửi, một HTTP request đã tới dịch vụ khác, một message đã được consumer nhận hoặc một file đã ghi ra filesystem cũng không tự biến mất chỉ vì transaction database rollback.

Đây là một lỗi thiết kế phổ biến trong hệ thống đồng thời: ứng dụng xem transaction như một vùng có thể hoàn tác mọi hiệu ứng, trong khi transaction chỉ kiểm soát những tài nguyên thực sự tham gia vào cơ chế transaction đó. Muốn bảo đảm nhất quán giữa database và hệ thống bên ngoài, cần thiết kế ranh giới rõ ràng, dùng outbox/inbox, idempotency hoặc quy trình bù trừ phù hợp.

## 1. Rollback thực sự hoàn tác điều gì?

Một transaction database gom các thay đổi thuộc phạm vi quản lý của DBMS thành một đơn vị commit hoặc rollback. Với bảng và storage engine có hỗ trợ transaction, nếu transaction rollback trước commit, các thay đổi DML chưa commit của transaction đó không trở thành dữ liệu đã xác nhận.

Ví dụ:

```sql
BEGIN;

UPDATE accounts
SET balance = balance - 100
WHERE account_id = 'A';

UPDATE accounts
SET balance = balance + 100
WHERE account_id = 'B';

ROLLBACK;
```

Nếu cả hai bảng/hàng thuộc transaction có khả năng rollback, số dư của A và B được khôi phục về trạng thái trước các câu `UPDATE`. Những khóa do transaction giữ cũng được giải phóng theo quy trình kết thúc transaction.

Nhưng transaction không phải một máy quay ngược thời gian cho toàn bộ tiến trình ứng dụng. Rollback không tự động:

- Trả lại số sequence/identity/auto-increment đã cấp.
- Thu hồi email, SMS, HTTP request hoặc lệnh thanh toán đã gửi ra ngoài.
- Xóa message đã được broker hoặc consumer nhận.
- Khôi phục file đã ghi, object đã upload hoặc dữ liệu cache đã sửa.
- Hoàn tác thay đổi đã commit bởi một transaction độc lập.
- Hoàn tác thao tác thuộc một autonomous transaction hoặc một cơ chế transaction khác.
- Đảm bảo mọi lệnh DDL có thể rollback; điều này phụ thuộc DBMS và loại DDL.

### Phạm vi transaction

```text
Ứng dụng
  │
  ├── Database transaction
  │     ├── INSERT / UPDATE / DELETE có transactional support
  │     ├── constraint và thay đổi dữ liệu cùng transaction
  │     └── COMMIT hoặc ROLLBACK
  │
  ├── Sequence / identity allocator
  ├── Message broker
  ├── Email / SMS / payment provider
  ├── Filesystem / object storage
  └── Cache / service khác
```

Chỉ các tài nguyên tham gia cùng một transaction coordinator/protocol mới có thể được điều phối nguyên tử trong cùng giao dịch. Một câu lệnh chạy trong cùng method Java không tự động thuộc cùng transaction database.

## 2. Mã sinh tự động có thể bị khuyết sau rollback

Nhiều hệ quản trị dùng cơ chế cấp số độc lập với việc commit hàng dữ liệu. Mục tiêu chính của sequence hoặc identity allocator là cấp giá trị duy nhất hiệu quả dưới concurrency, không phải tạo dãy số liên tục không có khoảng trống.

Giả sử bảng đơn hàng dùng mã số tự tăng:

```sql
BEGIN;

INSERT INTO orders (customer_id, total_amount)
VALUES (101, 500000);

-- Database cấp order_id = 5001.
-- Một bước sau đó gặp lỗi.

ROLLBACK;
```

Sau rollback, hàng `order_id = 5001` không còn trong bảng. Nhưng giá trị 5001 có thể đã được allocator tiêu thụ. Lần insert tiếp theo có thể nhận 5002.

```text
Giá trị allocator cấp: 5000 → 5001 → 5002

Hàng được commit:
  order_id = 5000
  order_id = 5002

Hàng 5001 không tồn tại vì transaction đã rollback.
```

Khoảng trống này là bình thường. Nó không chứng minh rằng một hàng bị mất sau commit, cũng không phải bằng chứng database bị hỏng.

### Vì sao không tái sử dụng số đã cấp?

Nếu DBMS phải lấy lại mọi giá trị sau rollback, việc cấp số cần phối hợp phức tạp hơn giữa nhiều transaction. Một transaction khác có thể đã quan sát, ghi log hoặc tham chiếu đến giá trị đó. Giữ allocator đơn giản và tránh tái sử dụng giúp cấp mã đồng thời hiệu quả hơn.

Sequence/identity thường phục vụ mục đích tạo khóa kỹ thuật duy nhất. Không nên dùng chúng như bộ đếm hóa đơn, số chứng từ hoặc số nghiệp vụ bắt buộc liên tục nếu quy định yêu cầu không có khoảng trống.

## 3. Khác biệt giữa các cơ chế sinh mã

Tên và hành vi chi tiết phụ thuộc DBMS, nhưng cần ghi nhớ rằng các cơ chế phổ biến không cam kết trả lại số đã cấp sau rollback.

| DBMS / cơ chế | Hành vi khi transaction rollback |
|---|---|
| PostgreSQL `SEQUENCE` / `nextval()` | Giá trị đã lấy không được trả lại; `nextval()` không rollback cùng transaction |
| Oracle `SEQUENCE.NEXTVAL` | Giá trị sequence đã cấp không được trả lại khi transaction rollback |
| MySQL InnoDB `AUTO_INCREMENT` | Giá trị đã cấp cho insert thất bại/rollback thường không được tái sử dụng; có thể có khoảng trống |
| SQL Server `IDENTITY` | Giá trị identity đã tiêu thụ không được hoàn lại khi insert/transaction rollback |
| SQL Server `SEQUENCE` | `NEXT VALUE FOR` cấp giá trị độc lập với transaction; rollback không trả lại số |

### PostgreSQL

Ví dụ:

```sql
CREATE SEQUENCE order_id_seq START WITH 100;

BEGIN;

SELECT nextval('order_id_seq'); -- 100

ROLLBACK;

SELECT nextval('order_id_seq'); -- 101
```

`nextval()` có hiệu ứng không rollback. Ngược lại, `setval()` cũng thay đổi trạng thái sequence theo semantics riêng; không nên dùng `setval()` để cố lấp khoảng trống trong khi hệ thống đang có transaction đồng thời vì có thể tạo trùng hoặc làm hỏng giả định của ứng dụng.

PostgreSQL identity column được triển khai dựa trên sequence; vì vậy, rollback một `INSERT` không có nghĩa identity value được trả lại.

### Oracle

Ví dụ:

```sql
CREATE SEQUENCE order_seq START WITH 100;

SELECT order_seq.NEXTVAL FROM dual; -- 100

ROLLBACK;

SELECT order_seq.NEXTVAL FROM dual; -- 101
```

Oracle sequence cấp giá trị độc lập với transaction. Cache sequence còn có thể tạo khoảng trống khi instance dừng bất thường hoặc sequence cache bị mất. Vì vậy, không được dựa vào sequence để tạo số liên tục.

### MySQL InnoDB

Ví dụ:

```sql
CREATE TABLE orders (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    customer_id BIGINT NOT NULL
) ENGINE = InnoDB;

START TRANSACTION;

INSERT INTO orders (customer_id) VALUES (101);

ROLLBACK;

INSERT INTO orders (customer_id) VALUES (102);
```

Giá trị `AUTO_INCREMENT` đã cấp cho lần insert đầu có thể để lại khoảng trống. Chi tiết phân bổ có thể phụ thuộc phiên bản, lock mode, bulk insert và cấu hình engine; ứng dụng không nên giả định số bị rollback sẽ được cấp lại.

Lưu ý rằng tính rollback của DML phụ thuộc storage engine. InnoDB hỗ trợ transaction; một bảng dùng engine không hỗ trợ transaction như MyISAM không có cùng bảo đảm rollback cho dữ liệu bảng. Vì vậy, cần xác nhận engine thực tế thay vì chỉ nhìn câu `START TRANSACTION`.

### SQL Server

Ví dụ:

```sql
CREATE TABLE dbo.orders (
    id BIGINT IDENTITY(1, 1) PRIMARY KEY,
    customer_id BIGINT NOT NULL
);

BEGIN TRANSACTION;

INSERT INTO dbo.orders (customer_id) VALUES (101);

ROLLBACK TRANSACTION;

INSERT INTO dbo.orders (customer_id) VALUES (102);
```

Identity value đã được cấp cho lần insert đầu không được hoàn lại khi rollback. SQL Server `SEQUENCE` cũng không rollback giá trị đã cấp bởi `NEXT VALUE FOR`.

## 4. Không dùng IDENTITY/SEQUENCE làm số chứng từ liên tục

Một khóa kỹ thuật thường cần duy nhất, không cần liên tục. Một số nghiệp vụ lại yêu cầu số hóa đơn hoặc số chứng từ có quy tắc đánh số riêng.

Nếu dùng sequence làm số hóa đơn và transaction tạo hóa đơn rollback, số đã cấp có thể bị bỏ trống. Nếu ứng dụng cố sửa bằng cách tìm số trống nhỏ nhất rồi cấp lại, hai transaction đồng thời có thể cùng chọn một số.

### Tách khóa kỹ thuật và số nghiệp vụ

```sql
CREATE TABLE invoices (
    invoice_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    invoice_number VARCHAR(40) NOT NULL UNIQUE,
    customer_id BIGINT NOT NULL,
    total_amount DECIMAL(18, 2) NOT NULL
);
```

- `invoice_id` là khóa kỹ thuật để tham chiếu nội bộ; có thể có khoảng trống.
- `invoice_number` là số nghiệp vụ theo quy tắc đánh số của tổ chức.

Nếu quy định thực sự yêu cầu số liên tục trong một phạm vi, cần thiết kế bộ cấp số nghiệp vụ có điều phối và kiểm tra pháp lý/kế toán phù hợp. Một cách là khóa hàng bộ đếm theo phạm vi (ví dụ năm tài chính/chi nhánh), cấp số và ghi hóa đơn trong cùng transaction. Nhưng việc rollback có thể trả bộ đếm về trạng thái trước đó nếu chính bộ đếm là hàng transactional; mọi giao dịch cấp số phải khóa cùng hàng theo một giao thức thống nhất.

Ví dụ khái niệm:

```sql
BEGIN;

SELECT last_number
FROM invoice_counters
WHERE fiscal_year = 2026
FOR UPDATE;

UPDATE invoice_counters
SET last_number = last_number + 1
WHERE fiscal_year = 2026;

INSERT INTO invoices (invoice_number, customer_id, total_amount)
VALUES ('2026-000125', 101, 500000);

COMMIT;
```

Ví dụ này minh họa cách điều phối số bằng hàng counter; cần thêm bước lấy số mới đúng theo DBMS, kiểm tra kết quả và xử lý khi transaction lỗi. Khóa hàng counter tạo điểm tuần tự hóa nên có thể giảm throughput nếu mọi hóa đơn tranh chấp cùng một phạm vi. Nếu yêu cầu pháp lý cho phép số không liên tục, sequence thường đơn giản và mở rộng tốt hơn.

Không nên tự động xóa hoặc tái sử dụng số đã phát hành chỉ để lấp khoảng trống. Quy tắc xử lý số hủy, số void và audit phải theo nghiệp vụ và quy định áp dụng.

## 5. Rollback không thu hồi email, SMS hoặc HTTP request

Một lỗi khác là gọi dịch vụ bên ngoài trong lúc transaction database đang mở:

```text
BEGIN DATABASE TRANSACTION
  INSERT order
  gửi email xác nhận đơn hàng
  gọi API vận chuyển tạo shipment
  UPDATE order
  gặp lỗi
ROLLBACK
```

Database có thể xóa thay đổi `INSERT` và `UPDATE` chưa commit. Nhưng email đã vào hệ thống gửi thư và shipment có thể đã được tạo ở dịch vụ vận chuyển. Rollback không thể gọi ngược thời gian để thu hồi những hành động đó.

Hậu quả có thể là:

- Khách nhận email xác nhận một đơn hàng không tồn tại trong database.
- Nhà vận chuyển đã tạo shipment nhưng order bị rollback.
- Dịch vụ ngoài đã trừ tiền hoặc giữ chỗ trong khi database không ghi nhận kết quả.
- Một request retry có thể gửi email hoặc tạo shipment lần thứ hai.

### Gọi dịch vụ ngoài trước hay sau commit?

Không có thứ tự đơn giản nào làm hai hệ thống độc lập tự động nguyên tử:

**Gọi ngoài trước commit:** dịch vụ ngoài thành công, sau đó database rollback. Hệ thống ngoài đã có hiệu ứng nhưng database không có trạng thái tương ứng.

**Commit database trước, gọi ngoài sau:** database đã xác nhận, nhưng process có thể chết trước khi gọi dịch vụ ngoài. Database có đơn hàng nhưng dịch vụ ngoài chưa nhận yêu cầu.

**Dùng callback sau commit:** giảm việc gửi side effect trước khi dữ liệu được xác nhận, nhưng vẫn có khoảng trống nếu process chết sau commit và trước khi callback chạy.

Để giải quyết khoảng trống này, cần một cơ chế ghi nhận công việc phải thực hiện một cách bền vững cùng transaction database.

## 6. Transactional outbox: ghi ý định phát sự kiện cùng transaction

Transactional outbox là mẫu thiết kế phổ biến để phối hợp thay đổi database với việc phát message.

Thay vì gửi message trực tiếp khi transaction đang mở, ứng dụng ghi một outbox event trong cùng transaction với thay đổi nghiệp vụ:

```sql
BEGIN;

INSERT INTO orders (order_id, status, total_amount)
VALUES ('ORD-125', 'CONFIRMED', 500000);

INSERT INTO outbox_events (event_id, event_type, aggregate_id, payload)
VALUES (
    'EVT-9001',
    'OrderConfirmed',
    'ORD-125',
    '{"orderId":"ORD-125","total":500000}'
);

COMMIT;
```

Hai thay đổi được commit hoặc rollback cùng nhau:

- Nếu transaction rollback, không có order đã xác nhận và không có outbox event đã commit.
- Nếu transaction commit, cả order và ý định phát event đều tồn tại bền vững.

Worker riêng đọc outbox và gửi event tới broker hoặc dịch vụ ngoài. Nếu worker chết trước khi gửi, event vẫn còn trong outbox để gửi lại. Nếu gửi thành công nhưng worker chết trước khi đánh dấu đã gửi, event có thể được gửi lại; consumer phải có cơ chế chống xử lý lặp.

### Sơ đồ luồng outbox

```text
Request
   │
   ▼
BEGIN DATABASE TRANSACTION
   ├── ghi Order
   ├── ghi Outbox Event
   └── COMMIT
          │
          ▼
     Outbox Publisher
          │
          ├── gửi message tới broker
          └── đánh dấu/ghi nhận đã publish
                    │
                    ▼
               Consumer
                    ├── kiểm tra event_id
                    ├── áp dụng thay đổi một cách idempotent
                    └── commit inbox + nghiệp vụ
```

Outbox không làm broker và database trở thành một transaction ACID duy nhất. Nó bảo đảm ý định phát sự kiện được lưu cùng thay đổi database, rồi cho phép publisher retry. Việc gửi có thể là at-least-once, vì vậy consumer cần deduplicate.

## 7. Inbox và idempotent consumer

Consumer có thể nhận cùng message nhiều lần. Một mẫu thường dùng là lưu event ID đã xử lý trong bảng inbox có unique constraint:

```sql
CREATE TABLE processed_events (
    consumer_name VARCHAR(100) NOT NULL,
    event_id VARCHAR(120) NOT NULL,
    processed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_processed_event
        UNIQUE (consumer_name, event_id)
);
```

Consumer xử lý message trong cùng transaction với thay đổi nghiệp vụ:

```text
BEGIN
  INSERT processed_events(consumer_name, event_id)

  nếu insert thành công:
      cập nhật dữ liệu nghiệp vụ

  nếu event_id đã tồn tại:
      bỏ qua hiệu ứng đã xử lý
COMMIT
ACK message
```

Nếu transaction rollback, dấu inbox và thay đổi nghiệp vụ cùng rollback; broker có thể giao lại và consumer thử lại. Nếu transaction commit nhưng ACK bị mất, message có thể được giao lại; unique event ID giúp consumer nhận ra đã xử lý.

Không nên ghi inbox ở một transaction rồi cập nhật nghiệp vụ ở transaction khác. Nếu inbox commit trước rồi process chết, lần giao lại sẽ bị bỏ qua dù hiệu ứng nghiệp vụ chưa xảy ra. Ngược lại, nếu cập nhật nghiệp vụ commit trước rồi mới ghi inbox, lần giao lại có thể tạo hiệu ứng hai lần.

## 8. Idempotency key cho lời gọi dịch vụ ngoài

Một dịch vụ thanh toán hoặc API đối tác có thể hỗ trợ idempotency key. Khi gọi cùng một ý định nghiệp vụ nhiều lần, gửi cùng key để nhà cung cấp nhận diện các lần retry là cùng một thao tác.

Ví dụ:

```http
POST /charges
Idempotency-Key: payment-intent-ORD-125
Content-Type: application/json

{
  "orderId": "ORD-125",
  "amount": 500000,
  "currency": "VND"
}
```

Nếu timeout, worker gửi lại cùng key và cùng payload. Provider có thể trả lại kết quả charge đã tạo thay vì tạo charge mới.

Trước khi dựa vào cơ chế này, cần kiểm tra:

- Provider có hỗ trợ idempotency hay không.
- Phạm vi duy nhất của key là theo merchant, endpoint, account hay resource nào.
- Thời gian provider giữ key và khi nào key hết hạn.
- Cùng key nhưng payload khác bị xử lý như thế nào.
- Có API tra cứu trạng thái để đối soát khi kết quả không rõ ràng hay không.
- Response lần retry có trả lại cùng resource ID hoặc kết quả không.

Idempotency key nội bộ không tự bảo vệ side effect ở provider. Phải truyền hoặc ánh xạ key ổn định sang hệ thống ngoài nếu muốn bảo vệ cả ranh giới đó.

## 9. Saga và compensation không phải rollback

Khi một quy trình trải qua nhiều service hoặc nhiều database độc lập, không thể luôn giữ một transaction ACID xuyên suốt. Saga chia quy trình thành nhiều bước cục bộ đã commit. Nếu bước sau thất bại, hệ thống chạy **compensating action (hành động bù trừ)** để đưa nghiệp vụ về trạng thái chấp nhận được.

Ví dụ đặt hàng:

| Bước | Hành động | Hành động bù trừ nếu bước sau thất bại |
|---|---|---|
| 1 | Tạo order ở trạng thái `PENDING` | Hủy order hoặc chuyển `CANCELLED` |
| 2 | Giữ tồn kho | Trả lại tồn kho |
| 3 | Authorize payment | Void authorization |
| 4 | Tạo shipment | Hủy shipment nếu provider cho phép |
| 5 | Xác nhận order | Có thể chuyển sang trạng thái xử lý lỗi/bù trừ theo nghiệp vụ |

Compensation không xóa lịch sử như rollback database. Ví dụ, khoản thanh toán đã capture có thể cần một giao dịch refund mới; shipment đã rời kho có thể không thể thu hồi ngay. Hệ thống phải ghi nhận cả hành động ban đầu và hành động bù trừ để audit.

Saga cần:

- Trạng thái bền vững cho từng bước.
- Retry có giới hạn và idempotency cho từng command.
- Compensation idempotent hoặc có thể xác định đã thực hiện.
- Timeout và cơ chế phát hiện bước bị kẹt.
- Quy trình manual intervention/reconciliation cho trường hợp không thể tự bù trừ.

Không nên gọi compensation là rollback. Rollback khôi phục thay đổi chưa commit trong một transaction; compensation là một nghiệp vụ mới nhằm sửa hoặc cân bằng hiệu ứng đã commit ở một hệ thống khác.

## 10. Autonomous transaction và commit độc lập

Một số DBMS hỗ trợ transaction độc lập lồng trong luồng xử lý. Oracle có **autonomous transaction**: transaction này có thể commit hoặc rollback độc lập với transaction gọi nó.

Ví dụ khái niệm trong PL/SQL:

```sql
CREATE OR REPLACE PROCEDURE write_audit(p_message VARCHAR2) AS
    PRAGMA AUTONOMOUS_TRANSACTION;
BEGIN
    INSERT INTO audit_log(message, created_at)
    VALUES (p_message, SYSTIMESTAMP);

    COMMIT;
END;
/
```

Transaction chính có thể gọi `write_audit`, sau đó rollback. Hàng audit đã được autonomous transaction commit vẫn tồn tại.

Điều này có thể hữu ích cho audit hoặc ghi nhận lỗi cần tồn tại dù transaction chính thất bại, nhưng cũng dễ làm người đọc hiểu nhầm rằng rollback chính sẽ xóa mọi thay đổi phát sinh trong call stack. Autonomous transaction không phải một phần của transaction cha và không được rollback cùng transaction cha.

Phải cẩn thận với khóa và phụ thuộc dữ liệu: autonomous transaction có thể chờ tài nguyên do transaction chính giữ, trong khi transaction chính lại chờ kết quả của autonomous routine, tạo tình huống deadlock hoặc lỗi thiết kế. Không dùng autonomous transaction tùy tiện cho dữ liệu nghiệp vụ cần commit/rollback cùng nhau.

## 11. DDL và các thao tác có implicit commit

Không phải mọi câu SQL đều tuân theo cùng quy tắc rollback của DML. Một số DBMS thực hiện implicit commit quanh DDL hoặc một số lệnh quản trị.

| DBMS | Lưu ý về DDL/transaction |
|---|---|
| Oracle | Nhiều DDL thông thường thực hiện commit ngầm trước và sau DDL thành công; không thể giả định DDL nằm trong transaction DML có thể rollback |
| MySQL | Nhiều DDL và lệnh quản trị gây implicit commit; danh sách ngoại lệ phụ thuộc câu lệnh và phiên bản |
| PostgreSQL | Nhiều lệnh DDL có thể chạy trong transaction và rollback, nhưng có ngoại lệ như một số thao tác quản trị/index hoặc lệnh không cho chạy trong transaction block |
| SQL Server | Nhiều DDL hỗ trợ transaction, nhưng hành vi phụ thuộc loại lệnh và thao tác; không nên giả định mọi lệnh đều rollback được |

Ví dụ Oracle:

```sql
UPDATE accounts
SET balance = balance - 100
WHERE account_id = 'A';

CREATE TABLE audit_temp (id NUMBER);

ROLLBACK;
```

Do DDL Oracle thường gây implicit commit, thay đổi `UPDATE` trước DDL có thể đã được commit trước khi `CREATE TABLE` chạy. `ROLLBACK` sau đó không hoàn tác được thay đổi đã commit.

Không dùng migration DDL như một bước giữa transaction nghiệp vụ với giả định rằng mọi thao tác trước đó vẫn có thể rollback. Tách schema migration khỏi transaction request và kiểm tra tài liệu DBMS cho từng lệnh cụ thể.

## 12. Filesystem, object storage và cache cũng ở ngoài transaction database

### Ghi file

Ví dụ ứng dụng tạo hóa đơn PDF:

```text
BEGIN DATABASE TRANSACTION
  INSERT invoice row
  ghi file invoice-125.pdf
  lỗi khi cập nhật ledger
ROLLBACK
```

Hàng invoice có thể bị rollback nhưng file PDF vẫn còn. Ngược lại, nếu file được ghi sau commit mà upload thất bại, database có invoice nhưng file chưa tồn tại.

Một cách thiết kế là:

- Ghi bản ghi công việc hoặc outbox trong transaction.
- Worker tạo/upload file sau commit.
- Lưu trạng thái `PENDING`, `READY` hoặc `FAILED`.
- Dùng tên file/object key ổn định theo business ID để retry không tạo nhiều bản sao ngoài ý muốn.
- Có job reconciliation tìm bản ghi thiếu file hoặc object mồ côi.
- Dọn file tạm bằng quy trình có kiểm soát, không xóa theo phỏng đoán khi transaction còn có thể commit.

### Cache

Nếu ứng dụng cập nhật cache trước khi database commit rồi transaction rollback, cache có thể chứa trạng thái không tồn tại trong database. Nếu commit database xong nhưng process chết trước khi invalidate cache, cache có thể giữ dữ liệu cũ.

Các cách thường dùng:

- Chỉ cập nhật/invalidate cache sau commit.
- Ghi sự kiện invalidation vào outbox cùng transaction.
- Dùng version hoặc timestamp để tránh ghi đè dữ liệu cache mới bằng dữ liệu cũ.
- Chấp nhận eventual consistency có thời hạn rõ ràng và có cơ chế refresh/reconcile.

Callback sau commit giúp tránh cập nhật cache trước khi dữ liệu được xác nhận, nhưng không bảo đảm callback luôn chạy nếu process chết ngay sau commit. Outbox bền vững phù hợp hơn khi việc phát sự kiện là bắt buộc.

## 13. Distributed transaction và two-phase commit

Về lý thuyết, một số hệ thống có thể phối hợp nhiều resource manager bằng distributed transaction/two-phase commit (2PC). Coordinator yêu cầu các participant prepare, sau đó quyết định commit hoặc rollback.

2PC có thể cung cấp atomic commit giữa các resource manager hỗ trợ protocol tương ứng, nhưng có chi phí và vận hành phức tạp:

- Participant phải hỗ trợ XA hoặc giao thức tương thích.
- Transaction có thể giữ tài nguyên trong thời gian prepare.
- Coordinator hoặc mạng gặp sự cố có thể khiến participant ở trạng thái in-doubt.
- Cần recovery log và quy trình xử lý giao dịch chưa rõ kết quả.
- Không phải API HTTP, email provider, filesystem hoặc broker nào cũng tham gia XA.

Không nên mặc định rằng Spring `@Transactional` tự tạo distributed transaction giữa database và HTTP API. Annotation này thường quản lý transaction theo transaction manager đã cấu hình. Nếu chỉ có một JDBC datasource, lời gọi HTTP bên trong method không tự tham gia transaction database.

Với đa số tích hợp microservice, outbox/inbox và saga thường thực tế hơn việc cố giữ một transaction xuyên suốt nhiều hệ thống. 2PC phù hợp khi toàn bộ participant hỗ trợ và yêu cầu atomic commit thực sự đáng với chi phí vận hành.

## 14. Những mẫu code dễ tạo hiểu nhầm

### Gửi email trước commit

```java
@Transactional
public void createOrder(OrderRequest request) {
    Order order = orderRepository.save(toOrder(request));
    emailClient.sendConfirmation(order.getId());
    ledgerRepository.post(order);
}
```

Nếu `post()` ném exception và transaction rollback, email vẫn có thể đã được gửi. `@Transactional` không thể thu hồi email.

### Gọi provider rồi rollback database

```java
@Transactional
public void charge(Order order) {
    paymentProvider.charge(order.amount());
    paymentRepository.save(new Payment(order.id(), order.amount()));
}
```

Nếu lưu `Payment` thất bại sau khi provider đã charge, database rollback nhưng charge ở provider vẫn tồn tại. Cần provider idempotency key, lưu trạng thái intent, outbox/saga và reconciliation.

### Dùng sequence như số liên tục

```sql
BEGIN;
SELECT nextval('invoice_seq');
ROLLBACK;
```

Lần lấy sequence đã tiêu thụ số. Không được giả định lần tiếp theo sẽ nhận lại số đó.

### Chỉ thêm callback sau commit rồi nghĩ đã bảo đảm phát message

```java
@Transactional
public void createOrder(Order order) {
    orderRepository.save(order);
    registerAfterCommit(() -> broker.publish(orderCreated(order)));
}
```

Callback không chạy nếu process chết sau commit nhưng trước khi callback thực hiện. Nếu event là bắt buộc, ghi outbox trong transaction và publisher xử lý sau commit.

## 15. Thiết kế transaction boundary đúng

Một quy trình nghiệp vụ nên chia rõ:

1. **Dữ liệu cần atomic trong database:** ghi trong cùng transaction.
2. **Ý định cần phát ra ngoài:** ghi outbox cùng transaction.
3. **Side effect ngoài:** thực hiện sau commit bằng worker hoặc workflow.
4. **Retry:** dùng idempotency key ổn định cho cùng ý định.
5. **Consumer:** deduplicate bằng event ID và inbox trong cùng transaction với hiệu ứng database.
6. **Thất bại sau commit:** dùng trạng thái bền vững, retry, compensation hoặc reconciliation.

Ví dụ một đơn hàng:

```text
HTTP request
   │
   ▼
BEGIN
  ├── INSERT order(PENDING)
  ├── INSERT payment_intent(PENDING)
  ├── INSERT outbox(OrderCreated)
  └── COMMIT
          │
          ▼
   Outbox publisher
          │
          ▼
   Payment worker
          ├── gọi provider với idempotency key
          ├── ghi kết quả payment bằng transaction riêng
          └── phát PaymentAuthorized event qua outbox
```

Nếu payment provider timeout, worker có thể retry cùng key hoặc truy vấn trạng thái. Nếu provider đã xử lý, lần retry không tạo charge mới theo hợp đồng idempotency của provider. Nếu provider không hỗ trợ, cần quy trình đối soát/manual handling phù hợp.

## 16. Kiểm thử rollback và side effect

Test cần chứng minh chính xác phần nào rollback và phần nào tồn tại sau rollback.

### Test sequence gap

- Bắt đầu transaction.
- Lấy sequence/identity value.
- Rollback.
- Lấy giá trị tiếp theo.
- Xác nhận giá trị mới có thể lớn hơn; không assert rằng dãy phải liên tục.

### Test email/provider không được gọi trước commit

- Giả lập lỗi sau khi ghi dữ liệu database nhưng trước commit.
- Xác nhận transaction rollback.
- Xác nhận outbox event không tồn tại đã commit.
- Xác nhận worker/provider không nhận yêu cầu.

### Test outbox sau commit

- Commit order và outbox event cùng transaction.
- Giả lập process/worker dừng trước khi publish.
- Khởi động publisher lại.
- Xác nhận event được phát từ outbox.
- Giả lập publish thành công nhưng đánh dấu chưa gửi bị lỗi.
- Xác nhận event có thể được gửi lại nhưng consumer chỉ áp dụng hiệu ứng một lần.

### Test saga compensation

- Hoàn tất bước giữ tồn kho.
- Làm bước payment thất bại.
- Chạy compensation trả tồn kho.
- Xác nhận trạng thái order phản ánh thất bại/hủy và audit giữ lại lịch sử bước đã thực hiện.
- Gửi lại compensation để xác nhận nó idempotent hoặc không tạo hoàn tồn kho hai lần.

Không nên test chỉ bằng mock `@Transactional` rồi kết luận database rollback đúng. Hãy dùng integration test với DBMS thực để kiểm tra transaction, sequence và engine. Với side effect ngoài, dùng fake server hoặc sandbox và đặt fault injection tại các ranh giới trước/sau commit.

## 17. Những hiểu nhầm thường gặp

| Hiểu nhầm | Cách hiểu đúng |
|---|---|
| Rollback đưa toàn hệ thống về trạng thái trước transaction | Rollback chỉ tác động đến thay đổi thuộc transaction/resource được quản lý; side effect ngoài không tự đảo ngược |
| Sequence/identity phải quay lại số cũ sau rollback | Giá trị đã cấp thường bị tiêu thụ; khoảng trống là bình thường |
| ID tăng liên tục chứng minh không mất dữ liệu | ID chỉ là khóa kỹ thuật, không phải bộ đếm số hàng đã commit |
| Gửi email trong method `@Transactional` khiến email rollback cùng database | Email provider không tham gia JDBC transaction chỉ vì được gọi trong method đó |
| Callback after-commit bảo đảm event luôn được gửi | Process có thể chết sau commit trước callback; outbox lưu ý định phát một cách bền vững |
| Ghi outbox đồng nghĩa broker chỉ nhận đúng một message | Publisher có thể gửi lặp; consumer cần inbox/idempotency |
| Compensation tương đương rollback | Compensation là hành động nghiệp vụ mới, không xóa lịch sử hiệu ứng đã xảy ra |
| DDL luôn rollback như UPDATE | DDL có implicit commit hoặc ngoại lệ tùy DBMS và câu lệnh |
| `@Transactional` bao trùm HTTP API và filesystem | Annotation chỉ quản lý tài nguyên tham gia transaction manager; HTTP/file không tự tham gia |
| Có thể lấp mọi khoảng trống sequence bằng cách cấp lại số nhỏ nhất | Có thể tạo trùng dưới concurrency và phá audit; số nghiệp vụ cần cơ chế cấp riêng |

## 18. Tự kiểm tra

**Tình huống 1:** Transaction lấy `nextval()` của PostgreSQL rồi rollback. Lần sau có chắc nhận lại đúng số vừa lấy không?

**Đáp án:** Không. `nextval()` không rollback; giá trị đã cấp được tiêu thụ. Khoảng trống sequence là bình thường.

**Tình huống 2:** Một method Java có `@Transactional` insert order, gửi email rồi gặp exception. Order rollback. Email có tự biến mất khỏi hộp thư người nhận không?

**Đáp án:** Không. Email service là hệ thống ngoài transaction database. Nếu email đã được gửi, rollback database không thu hồi được. Nên ghi outbox trong transaction và gửi sau commit.

**Tình huống 3:** Ứng dụng commit order rồi gọi broker trong callback after-commit. Process chết ngay sau commit trước khi callback chạy. Điều gì xảy ra?

**Đáp án:** Order tồn tại nhưng event có thể chưa được publish. Callback trong bộ nhớ không bền vững. Ghi outbox event cùng transaction với order để publisher có thể tiếp tục sau restart.

**Tình huống 4:** Publisher gửi event thành công nhưng chết trước khi đánh dấu outbox row đã gửi. Lần chạy lại có thể gửi gì?

**Đáp án:** Có thể gửi lại cùng event. Consumer cần lưu event ID đã xử lý và cập nhật dữ liệu nghiệp vụ trong cùng transaction để redelivery không tạo hiệu ứng lặp.

**Tình huống 5:** Oracle procedure gọi autonomous transaction để ghi audit và commit. Transaction chính rollback. Audit row có bị xóa không?

**Đáp án:** Không. Autonomous transaction commit độc lập nên không bị rollback cùng transaction chính.

**Tình huống 6:** Ứng dụng dùng sequence làm số hóa đơn và phát hiện khoảng trống sau khi một transaction rollback. Có nên tự cấp lại số trống nhỏ nhất không?

**Đáp án:** Không nên làm tùy tiện. Dưới concurrency, nhiều transaction có thể cùng chọn số trống; việc tái sử dụng còn có thể vi phạm audit/quy định. Tách khóa kỹ thuật khỏi số nghiệp vụ và thiết kế bộ cấp số nghiệp vụ có điều phối nếu thật sự cần liên tục.

**Tình huống 7:** Một transaction cập nhật bảng InnoDB và bảng MyISAM rồi rollback. Có thể giả định cả hai bảng được khôi phục không?

**Đáp án:** Không. InnoDB hỗ trợ transaction; MyISAM không cung cấp cùng bảo đảm rollback cho dữ liệu bảng. Cần dùng storage engine có transactional support cho dữ liệu phải commit/rollback nguyên tử.

**Tình huống 8:** Payment provider đã capture tiền nhưng database transaction ghi payment bị rollback. Nên dùng rollback database để xử lý khoản tiền đó như thế nào?

**Đáp án:** Rollback không hoàn tiền ở provider. Cần lưu trạng thái intent và thực hiện hành động bù trừ như refund/void theo API provider, có idempotency key và reconciliation để xác nhận kết quả.

Khi thiết kế transaction, hãy xác định chính xác tài nguyên nào được database quản lý, tài nguyên nào có commit độc lập và hiệu ứng nào không thể thu hồi. Chấp nhận khoảng trống của sequence như đặc tính của khóa kỹ thuật; dùng cơ chế riêng cho số nghiệp vụ. Với email, message, payment, file và cache, ghi ý định bền vững trong transaction rồi xử lý sau commit bằng outbox, idempotency và compensation khi cần. Rollback bảo vệ tính nguyên tử trong phạm vi transaction; tính nhất quán xuyên nhiều hệ thống cần một thiết kế phối hợp riêng.

## Tài liệu tham khảo

- [PostgreSQL — Sequence Manipulation Functions](https://www.postgresql.org/docs/current/functions-sequence.html)
- [Oracle Database — CREATE SEQUENCE](https://docs.oracle.com/en/database/oracle/oracle-database/26/sqlrf/CREATE-SEQUENCE.html)
- [MySQL 8.0 — InnoDB AUTO_INCREMENT Handling](https://dev.mysql.com/doc/refman/8.0/en/innodb-auto-increment-handling.html)
- [SQL Server — IDENTITY Property](https://learn.microsoft.com/en-us/sql/t-sql/statements/create-table-transact-sql-identity-property)
- [SQL Server — Sequence Numbers](https://learn.microsoft.com/en-us/sql/relational-databases/sequence-numbers/sequence-numbers)
- [Oracle Database — Autonomous Transactions](https://docs.oracle.com/en/database/oracle/oracle-database/26/lnpls/autonomous-transactions.html)
