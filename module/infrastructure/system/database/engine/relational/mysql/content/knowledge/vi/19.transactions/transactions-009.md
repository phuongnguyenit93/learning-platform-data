# READ ONLY/READ WRITE và lựa chọn đặc tính giao dịch

Trong MySQL, một transaction có thể được khai báo là `READ ONLY` hoặc `READ WRITE`. Đây là **chế độ truy cập dữ liệu** của transaction: transaction chỉ đọc dữ liệu từ các bảng thông thường, hay được phép đọc và thay đổi dữ liệu. MySQL còn cho phép chọn **mức cô lập** (isolation level) để kiểm soát cách các transaction đồng thời nhìn thấy thay đổi của nhau.

Khi vận hành cơ sở dữ liệu quan hệ, việc chọn đúng các đặc tính này giúp câu truy vấn báo cáo có phạm vi đọc nhất quán, đồng thời giúp transaction nghiệp vụ có quyền ghi rõ ràng. Cần hiểu rằng chế độ đọc/ghi và mức cô lập là hai lựa chọn riêng biệt: `READ ONLY` không tự động có nghĩa là `SERIALIZABLE`, và `READ WRITE` cũng không tự động có nghĩa là `READ COMMITTED`.

## 1. Hai chế độ truy cập của transaction

### `READ ONLY`

Transaction `READ ONLY` được khai báo để đọc dữ liệu từ các bảng thông thường. MySQL không cho phép transaction này thay đổi bảng không phải bảng tạm. Bảng tạm (temporary table) là ngoại lệ: transaction vẫn có thể thêm, sửa hoặc xóa dữ liệu trong bảng tạm.

Ví dụ một transaction chỉ đọc để tổng hợp báo cáo:

```sql
START TRANSACTION READ ONLY;

SELECT COUNT(*) AS order_count
FROM orders
WHERE created_at >= '2026-01-01';

SELECT SUM(total_amount) AS revenue
FROM orders
WHERE created_at >= '2026-01-01';

COMMIT;
```

Transaction có thể thực hiện nhiều câu `SELECT` trước khi kết thúc. Với InnoDB, việc khai báo trước rằng transaction chỉ đọc còn giúp engine áp dụng một số tối ưu dành cho read-only transaction.

Nếu cố gắng cập nhật một bảng thông thường trong transaction này, MySQL sẽ từ chối câu lệnh:

```sql
START TRANSACTION READ ONLY;

UPDATE orders
SET total_amount = total_amount + 10000
WHERE order_id = 1001;

ROLLBACK;
```

`UPDATE` không được thực hiện vì transaction đã khai báo `READ ONLY`. `ROLLBACK` kết thúc transaction.

### `READ WRITE`

Transaction `READ WRITE` được phép đọc và thay đổi dữ liệu, miễn là tài khoản có quyền phù hợp và các ràng buộc dữ liệu được đáp ứng. Đây là chế độ mặc định khi MySQL bắt đầu transaction nếu không có cấu hình khác.

```sql
START TRANSACTION READ WRITE;

UPDATE inventory
SET quantity = quantity - 2
WHERE product_id = 9001;

INSERT INTO stock_movements (product_id, quantity_change, reason)
VALUES (9001, -2, 'Bán hàng');

COMMIT;
```

Hai thay đổi được nhóm trong cùng transaction. Nếu quy trình phát hiện lỗi trước khi commit, ứng dụng có thể `ROLLBACK` để hủy các thay đổi transactional đã thực hiện.

`READ WRITE` chỉ khai báo rằng transaction được phép ghi. Nó không bỏ qua quyền truy cập, khóa, ràng buộc khóa ngoại, ràng buộc duy nhất hay các lỗi khác của câu lệnh.

## 2. Khai báo chế độ ngay khi bắt đầu transaction

MySQL cho phép truyền đặc tính transaction trực tiếp vào `START TRANSACTION`:

```sql
START TRANSACTION READ ONLY;
-- Các câu lệnh chỉ đọc
COMMIT;

START TRANSACTION READ WRITE;
-- Các câu lệnh có thể đọc và ghi
COMMIT;
```

Nếu không ghi `READ ONLY` hoặc `READ WRITE`, transaction sử dụng chế độ truy cập mặc định đang có hiệu lực. Có thể khai báo thêm `WITH CONSISTENT SNAPSHOT` khi cần tạo consistent snapshot cho InnoDB ở mức cô lập phù hợp:

```sql
START TRANSACTION WITH CONSISTENT SNAPSHOT, READ ONLY;

SELECT COUNT(*) FROM orders;
SELECT COUNT(*) FROM order_items;

COMMIT;
```

`WITH CONSISTENT SNAPSHOT` chỉ có tác dụng với InnoDB khi mức cô lập là `REPEATABLE READ`. Nếu dùng mức cô lập khác, MySQL bỏ qua tùy chọn này. Với `REPEATABLE READ`, tùy chọn giúp tạo snapshot nhất quán ngay khi bắt đầu transaction thay vì đợi đến lần đọc nhất quán đầu tiên.

## 3. Đặt đặc tính cho transaction tiếp theo hoặc cho session

Ngoài cách khai báo trên `START TRANSACTION`, MySQL cung cấp `SET TRANSACTION` để đặt đặc tính cho transaction. Phạm vi ảnh hưởng phụ thuộc vào từ khóa đi kèm:

| Câu lệnh | Phạm vi áp dụng |
|---|---|
| `SET TRANSACTION ...` | Chỉ transaction kế tiếp của session hiện tại |
| `SET SESSION TRANSACTION ...` | Mặc định cho các transaction tiếp theo trong session hiện tại |
| `SET GLOBAL TRANSACTION ...` | Mặc định cho các session mới được tạo sau đó; không đổi cấu hình của session đang tồn tại |

Ví dụ đặt transaction kế tiếp ở chế độ chỉ đọc:

```sql
SET TRANSACTION READ ONLY;

START TRANSACTION;
SELECT * FROM orders WHERE order_id = 1001;
COMMIT;
```

Ví dụ đặt mặc định cho các transaction tiếp theo của kết nối hiện tại:

```sql
SET SESSION TRANSACTION READ ONLY;

START TRANSACTION;
SELECT COUNT(*) FROM orders;
COMMIT;
```

Khi cần ghi, có thể đặt lại session hoặc ghi đè cho một transaction cụ thể:

```sql
START TRANSACTION READ WRITE;
UPDATE orders
SET total_amount = 150000.00
WHERE order_id = 1001;
COMMIT;
```

Thiết lập `SESSION` tồn tại trên kết nối cho đến khi được thay đổi hoặc kết nối kết thúc. Thiết lập `GLOBAL` cần quyền quản trị phù hợp và chỉ ảnh hưởng các kết nối mới. Không nên nhầm việc đổi đặc tính cho transaction kế tiếp với việc thay đổi một transaction đã bắt đầu.

## 4. Chọn mức cô lập giao dịch

Chế độ `READ ONLY`/`READ WRITE` trả lời câu hỏi transaction có được ghi hay không. Mức cô lập trả lời câu hỏi transaction nhìn thấy dữ liệu của các transaction khác như thế nào. MySQL hỗ trợ bốn mức cô lập chuẩn:

| Mức cô lập | Hành vi chính | Khi cân nhắc sử dụng |
|---|---|---|
| `READ UNCOMMITTED` | Có thể đọc thay đổi chưa commit của transaction khác (dirty read) | Chỉ cân nhắc khi chấp nhận dữ liệu tạm thời và hiểu rõ rủi ro |
| `READ COMMITTED` | Không đọc dữ liệu chưa commit; mỗi lần consistent read trong transaction có thể thấy snapshot mới | Khi cần thấy các thay đổi đã commit gần đây giữa các lần đọc |
| `REPEATABLE READ` | Các consistent read trong cùng transaction dùng cùng snapshot được thiết lập ở lần đọc nhất quán đầu tiên | Khi cần kết quả đọc lặp lại ổn định; đây là mặc định phổ biến của InnoDB |
| `SERIALIZABLE` | Cư xử nghiêm ngặt hơn để các transaction có kết quả tương đương một thứ tự thực thi tuần tự | Khi tính đúng đắn yêu cầu mức cô lập cao và có thể chấp nhận nhiều chờ khóa hơn |

Các hiện tượng thường dùng để hiểu mức cô lập:

- **Dirty read:** đọc dữ liệu mà transaction ghi chưa commit; transaction ghi có thể rollback sau đó.
- **Non-repeatable read:** cùng một truy vấn đọc một hàng hai lần nhưng nhận giá trị khác vì transaction khác đã commit cập nhật ở giữa.
- **Phantom read:** chạy lại một điều kiện truy vấn và thấy thêm hoặc mất các hàng phù hợp vì transaction khác đã thay đổi tập hàng đó.

Với InnoDB, `REPEATABLE READ` sử dụng consistent read dựa trên MVCC để các lần đọc thông thường trong transaction giữ cùng snapshot. Các câu lệnh đọc có khóa như `SELECT ... FOR UPDATE` hoặc `SELECT ... FOR SHARE` có quy tắc đọc và khóa riêng; không nên đánh đồng chúng với consistent read thông thường.

Mức cô lập mặc định của InnoDB trong MySQL thường là `REPEATABLE READ`, nhưng cấu hình server hoặc session có thể thay đổi giá trị này. Hãy kiểm tra môi trường thực tế trước khi dựa vào mặc định.

## 5. Đặt mức cô lập bằng `SET TRANSACTION`

Có thể đặt mức cô lập cho transaction tiếp theo:

```sql
SET TRANSACTION ISOLATION LEVEL READ COMMITTED;

START TRANSACTION READ ONLY;
SELECT COUNT(*) FROM orders;
COMMIT;
```

Hoặc đặt mặc định cho các transaction tiếp theo của session hiện tại:

```sql
SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ;
```

Nếu cần áp dụng mặc định cho các session mới, quản trị viên có thể dùng phạm vi `GLOBAL`:

```sql
SET GLOBAL TRANSACTION ISOLATION LEVEL READ COMMITTED;
```

Lệnh `GLOBAL` yêu cầu quyền phù hợp. Nó không thay đổi mức cô lập của các kết nối đang mở; các session hiện tại cần tự đặt lại bằng phạm vi `SESSION` nếu muốn dùng giá trị mới.

Có thể đặt cả mức cô lập và chế độ truy cập trong một câu lệnh:

```sql
SET TRANSACTION ISOLATION LEVEL READ COMMITTED, READ ONLY;
START TRANSACTION;

SELECT order_id, total_amount
FROM orders
WHERE created_at >= CURRENT_DATE - INTERVAL 7 DAY;

COMMIT;
```

Ở ví dụ này, transaction kế tiếp dùng `READ COMMITTED` và `READ ONLY`. Hai đặc tính được chọn độc lập nhưng có thể khai báo cùng nhau.

## 6. Kết hợp chế độ truy cập với transaction nghiệp vụ

### Báo cáo cần một góc nhìn nhất quán

Giả sử một báo cáo đọc tổng đơn hàng và tổng dòng hàng. Nếu cần các lần đọc nhất quán trong một snapshot, có thể dùng InnoDB với `REPEATABLE READ` và `WITH CONSISTENT SNAPSHOT`:

```sql
SET TRANSACTION ISOLATION LEVEL REPEATABLE READ;

START TRANSACTION WITH CONSISTENT SNAPSHOT, READ ONLY;

SELECT COUNT(*) AS order_count
FROM orders;

SELECT COUNT(*) AS item_count
FROM order_items;

COMMIT;
```

Các consistent read trong transaction nhìn dữ liệu theo snapshot được tạo lúc bắt đầu. Transaction kết thúc bằng `COMMIT` vì không có thay đổi cần hoàn tác; dùng `ROLLBACK` cũng có thể kết thúc một transaction chỉ đọc.

### Cập nhật dữ liệu cần kiểm soát lỗi

Một transaction nghiệp vụ thường cần `READ WRITE` và mức cô lập phù hợp với quy tắc dữ liệu:

```sql
SET TRANSACTION ISOLATION LEVEL READ COMMITTED;

START TRANSACTION READ WRITE;

UPDATE accounts
SET balance = balance - 50000
WHERE account_id = 10;

UPDATE accounts
SET balance = balance + 50000
WHERE account_id = 20;

COMMIT;
```

Đây chỉ là minh họa cách khai báo đặc tính. Ứng dụng thực tế cần kiểm tra tài khoản nguồn tồn tại, số dư đủ, số hàng bị ảnh hưởng và xử lý mọi lỗi trước khi commit. Nếu một điều kiện nghiệp vụ không đạt, rollback để tránh chỉ hoàn tất một nửa thao tác chuyển tiền.

## 7. Những lưu ý khi vận hành

**Không xem `READ ONLY` là một transaction không cần kết thúc.** Transaction chỉ đọc vẫn giữ snapshot và có thể giữ tài nguyên hoặc ảnh hưởng đến việc dọn phiên bản dữ liệu cũ trong InnoDB. Hãy hoàn tất bằng `COMMIT` hoặc `ROLLBACK` ngay khi đọc xong, đặc biệt với báo cáo dài.

**Không để transaction mở trong lúc chờ người dùng.** Tránh mở transaction rồi chờ nhập liệu, gọi dịch vụ bên ngoài hoặc xử lý tác vụ lâu. Thời gian mở transaction dài có thể giữ khóa (nếu có) và làm tăng chi phí duy trì read view.

**Cẩn thận với connection pool.** `SET SESSION TRANSACTION ...` thay đổi trạng thái của kết nối. Khi connection được trả về pool, session setting có thể vẫn còn và ảnh hưởng người dùng tiếp theo. Hãy cấu hình nhất quán khi tạo/cho mượn kết nối hoặc khôi phục trạng thái session theo chính sách của pool.

**Không kỳ vọng `ROLLBACK` hoàn tác mọi loại câu lệnh.** MySQL có các câu lệnh DDL gây implicit commit. Không nên đặt `CREATE TABLE`, `ALTER TABLE` hoặc `DROP TABLE` giữa các thao tác DML rồi kỳ vọng rollback sẽ khôi phục toàn bộ trạng thái trước đó.

**Không bắt đầu transaction lồng nhau bằng `START TRANSACTION`.** MySQL không hỗ trợ nested transaction theo cách một `START TRANSACTION` bên trong tự tạo lớp transaction mới. Bắt đầu transaction mới có thể kết thúc transaction đang mở bằng implicit commit. Nếu cần điểm quay lui trong một transaction, hãy tìm hiểu `SAVEPOINT`, `ROLLBACK TO SAVEPOINT` và `RELEASE SAVEPOINT`.

## 8. Bảng chọn nhanh

| Nhu cầu | Chế độ truy cập | Mức cô lập gợi ý | Ghi chú |
|---|---|---|---|
| Truy vấn báo cáo, không sửa bảng | `READ ONLY` | `REPEATABLE READ` nếu cần cùng snapshot qua nhiều lần đọc | Có thể thêm `WITH CONSISTENT SNAPSHOT` cho InnoDB |
| Đọc dữ liệu và cần thấy commit mới ở mỗi lần đọc | `READ ONLY` | `READ COMMITTED` | Mỗi consistent read có thể nhận snapshot mới |
| Cập nhật nhiều bảng trong một nghiệp vụ | `READ WRITE` | Chọn theo invariant và hành vi đồng thời cần bảo vệ | Kiểm tra kết quả và rollback khi nghiệp vụ thất bại |
| Quy trình cần mức cô lập nghiêm ngặt | `READ WRITE` hoặc `READ ONLY` | `SERIALIZABLE` | Đánh giá tác động chờ khóa và thông lượng |

Không có một mức cô lập phù hợp cho mọi truy vấn. Hãy bắt đầu từ yêu cầu nhất quán của nghiệp vụ, xác định transaction có cần ghi không, sau đó chọn mức cô lập và thời gian giữ transaction ngắn nhất có thể.

## 9. Tự kiểm tra

1. `READ ONLY` có cho phép thêm dữ liệu vào temporary table không? Vì sao?
2. Khác biệt giữa `SET TRANSACTION READ ONLY` và `SET SESSION TRANSACTION READ ONLY` là gì?
3. Vì sao `READ ONLY` và `REPEATABLE READ` không phải hai cách gọi của cùng một đặc tính?
4. `WITH CONSISTENT SNAPSHOT` có tác dụng trong trường hợp nào với InnoDB?
5. Vì sao cần chú ý session setting khi sử dụng connection pool?
6. Vì sao không nên để một transaction chỉ đọc mở trong thời gian dài?

