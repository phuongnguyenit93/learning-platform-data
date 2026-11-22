# Phân biệt thời hạn chờ khóa, thời hạn câu lệnh và thời hạn giao dịch

Trong cơ sở dữ liệu có nhiều loại thời hạn (*timeout/deadline*) khác nhau. Một câu lệnh có thể phải chờ khóa do giao dịch khác đang giữ tài nguyên; bản thân câu lệnh có thể chạy quá lâu; hoặc toàn bộ transaction có thể tồn tại lâu hơn thời gian mà ứng dụng cho phép. Ba tình huống này liên quan với nhau nhưng không giống nhau.

- **Thời hạn chờ khóa** (*lock wait timeout*) giới hạn thời gian một thao tác được phép chờ để lấy khóa đang bị giao dịch khác giữ.
- **Thời hạn câu lệnh** (*statement/query timeout*) giới hạn tổng thời gian thực thi một câu SQL hoặc một lệnh truy vấn.
- **Thời hạn giao dịch** (*transaction timeout/deadline*) giới hạn khoảng thời gian một transaction được phép tồn tại, tính từ khi bắt đầu cho đến khi commit hoặc rollback, theo cơ chế của hệ thống.

Phân biệt đúng ba loại thời hạn giúp xác định nguyên nhân một thao tác bị hủy, chọn cấu hình phù hợp và xử lý transaction đúng cách. Nếu chỉ tăng một timeout mà không hiểu phạm vi của nó, ứng dụng có thể vẫn bị hủy bởi một giới hạn khác hoặc tiếp tục giữ khóa sau khi câu lệnh đã lỗi.

## 1. Thời hạn chờ khóa: giới hạn một lần chờ tài nguyên

Khi một transaction yêu cầu khóa xung đột với khóa đang được transaction khác giữ, hệ quản trị đưa yêu cầu vào trạng thái chờ. Thời hạn chờ khóa giới hạn khoảng thời gian cho việc chờ đó.

Ví dụ, T1 đang giữ khóa độc quyền trên hàng `account(10)`. T2 muốn cập nhật cùng hàng:

```text
T1                                      T2
----------------------------------------------------------------
BEGIN
UPDATE account(10), giữ khóa X
                                        BEGIN
                                        UPDATE account(10), yêu cầu X
                                        Bắt đầu chờ khóa
                                        |
                                        +-- T1 nhả khóa trước timeout
                                        |      -> T2 lấy được khóa
                                        |
                                        +-- Hết lock timeout trước
                                               -> T2 nhận lỗi timeout
COMMIT
```

Lock timeout chỉ nói rằng T2 không lấy được khóa trong khoảng chờ được cho phép. Nó không chứng minh câu SQL vốn dĩ chậm, cũng không nhất thiết có nghĩa toàn bộ transaction đã vượt giới hạn thời gian.

Một câu lệnh có thể phải chờ nhiều khóa khác nhau. Tùy hệ quản trị, giới hạn lock wait có thể được áp dụng cho từng lần chờ lấy khóa. Vì vậy, tổng thời gian chờ khóa của câu lệnh có thể lớn hơn một giá trị timeout đơn lẻ nếu câu lệnh lần lượt gặp nhiều lần chờ khác nhau.

### Ví dụ PostgreSQL

PostgreSQL có tham số `lock_timeout`, cấu hình thời gian tối đa cho một lần chờ khóa. Có thể đặt trong transaction bằng `SET LOCAL`:

```sql
BEGIN;

SET LOCAL lock_timeout = '1s';

UPDATE account
SET balance = balance - 100
WHERE id = 10;

COMMIT;
```

Nếu thao tác cần chờ khóa quá giới hạn, PostgreSQL hủy statement với lỗi lock timeout. Transaction hiện tại chuyển sang trạng thái lỗi; ứng dụng cần rollback transaction hoặc rollback về savepoint hợp lệ trước khi tiếp tục. `SET LOCAL` chỉ có hiệu lực trong transaction hiện tại.

Giá trị `lock_timeout = 0` tắt giới hạn chờ khóa theo tham số này; nó không có nghĩa là NOWAIT. Muốn từ chối chờ cho locking read cụ thể, có thể dùng `FOR UPDATE NOWAIT` nếu câu lệnh và hệ quản trị hỗ trợ.

### Ví dụ MySQL InnoDB

InnoDB cung cấp `innodb_lock_wait_timeout` cho thời gian chờ khóa hàng:

```sql
SET SESSION innodb_lock_wait_timeout = 2;

START TRANSACTION;

UPDATE account
SET balance = balance - 100
WHERE id = 10;

COMMIT;
```

Giá trị được tính bằng giây. Đây là cấu hình cho chờ khóa InnoDB; metadata lock có tham số riêng là `lock_wait_timeout`. Khi lock wait timeout xảy ra, hành vi rollback mặc định thường chỉ rollback statement hiện tại; cấu hình `innodb_rollback_on_timeout` có thể thay đổi cách rollback transaction. Ứng dụng nên chủ động rollback transaction nếu không thể tiếp tục toàn bộ nghiệp vụ một cách an toàn.

## 2. Thời hạn câu lệnh: giới hạn tổng thời gian chạy SQL

Thời hạn câu lệnh (*statement timeout*) giới hạn thời gian từ khi câu lệnh bắt đầu thực thi cho đến khi hoàn tất hoặc bị hủy. Khoảng thời gian này có thể bao gồm:

- Thời gian lập kế hoạch và thực thi truy vấn.
- Thời gian đọc/ghi dữ liệu và chờ I/O.
- Thời gian chờ khóa.
- Thời gian xử lý join, sort, aggregate hoặc các phép tính khác.
- Các lần chờ tài nguyên khác trong quá trình thực thi.

Ví dụ, câu truy vấn báo cáo có thể không bị khóa nhưng vẫn chạy lâu do quét bảng lớn hoặc thiếu chỉ mục. Lock timeout không giúp xử lý nguyên nhân này; statement timeout mới là giới hạn phù hợp.

```text
Bắt đầu statement
       |
       +-- lập kế hoạch
       +-- chờ khóa (nếu có)
       +-- đọc/ghi và tính toán
       +-- trả kết quả
       |
       +-- nếu tổng thời gian vượt statement timeout -> hủy statement
```

### Ví dụ PostgreSQL

PostgreSQL có `statement_timeout` để giới hạn thời gian thực thi statement. Có thể đặt riêng trong transaction:

```sql
BEGIN;

SET LOCAL statement_timeout = '5s';

SELECT account_id, SUM(amount)
FROM account_transaction
GROUP BY account_id;

COMMIT;
```

Nếu statement mất quá năm giây, PostgreSQL hủy statement. Thời gian chờ khóa cũng nằm trong thời gian thực thi statement, do đó statement timeout có thể xảy ra trước lock timeout nếu phần ngân sách còn lại của câu lệnh nhỏ hơn thời gian chờ khóa còn lại.

Ví dụ, `statement_timeout = 3s` và `lock_timeout = 5s`: nếu câu lệnh bắt đầu chờ khóa ngay từ đầu, statement timeout thường kết thúc câu lệnh sau ba giây trước khi lock timeout năm giây hết hạn.

### Ví dụ MySQL

MySQL có `max_execution_time` cho một số câu `SELECT` đọc, với đơn vị mili giây:

```sql
SET SESSION max_execution_time = 5000;

SELECT account_id, SUM(amount)
FROM account_transaction
GROUP BY account_id;
```

Thiết lập này áp dụng cho các câu `SELECT` đủ điều kiện theo quy tắc MySQL; nó không phải timeout tổng quát cho mọi câu `INSERT`, `UPDATE` hoặc `DELETE`. Ứng dụng và driver cũng có thể đặt query timeout ở phía client. Cần phân biệt timeout được database thực thi với timeout do client ngừng chờ hoặc gửi yêu cầu hủy.

## 3. Thời hạn giao dịch: giới hạn toàn bộ transaction

Transaction có thể bao gồm nhiều câu SQL và khoảng thời gian xử lý giữa các câu lệnh. Thời hạn giao dịch giới hạn tổng thời gian transaction được phép tồn tại, từ khi bắt đầu đến khi kết thúc bằng `COMMIT` hoặc `ROLLBACK`.

Ví dụ:

```text
BEGIN
  SELECT ...                  1 giây
  xử lý logic trong ứng dụng  4 giây
  UPDATE ...                  1 giây
  chờ khóa                    2 giây
  COMMIT                      1 giây
END

Tổng thời gian transaction = 9 giây
```

Ngay cả khi từng câu SQL đều nằm trong statement timeout riêng, transaction vẫn có thể tồn tại quá lâu vì nó chứa nhiều statement hoặc ứng dụng xử lý giữa các statement. Nếu hệ thống có transaction deadline tám giây, ví dụ trên đã vượt giới hạn dù không statement nào riêng lẻ chạy quá tám giây.

Thời hạn giao dịch có thể được thực thi ở các tầng khác nhau:

- **Database engine:** một số hệ quản trị có tham số giới hạn tuổi transaction hoặc cơ chế tương đương.
- **Transaction manager/framework:** framework có thể đặt deadline cho transaction được quản lý.
- **Application deadline:** ứng dụng tự theo dõi thời gian còn lại và yêu cầu hủy công việc khi vượt ngân sách.

Không có một câu lệnh SQL chuẩn dùng chung để cấu hình transaction timeout trên mọi hệ quản trị. Cần kiểm tra cách database, transaction manager và driver phối hợp. Một deadline ở framework không nhất thiết tự hủy câu SQL đang chạy nếu timeout không được truyền xuống driver/database.

### Ví dụ PostgreSQL và giới hạn phiên bản

PostgreSQL cung cấp `transaction_timeout` từ PostgreSQL 17 để chấm dứt session khi transaction tồn tại quá thời gian cấu hình. Tham số này khác `statement_timeout` và `idle_in_transaction_session_timeout`; cần xác nhận phiên bản đang chạy và chính sách quyền cấu hình trước khi sử dụng.

PostgreSQL cũng có `idle_in_transaction_session_timeout`, nhưng tham số này chỉ giới hạn thời gian session ở trạng thái idle trong khi vẫn mở transaction. Nó không phải giới hạn tổng thời gian transaction đang thực thi các câu SQL.

### Transaction timeout ở tầng ứng dụng

Một transaction manager có thể nhận timeout khi bắt đầu transaction. Ví dụ khái quát:

```text
transaction deadline = thời điểm bắt đầu + 10 giây

BEGIN
  chạy statement 1
  chạy statement 2
  nếu thời gian còn lại <= 0:
      hủy công việc nếu có thể
      ROLLBACK
  nếu hoàn tất trong hạn:
      COMMIT
```

Đây là mô hình xử lý, không phải cú pháp SQL dùng chung. Việc timeout có hủy truy vấn đang chạy, đánh dấu transaction rollback-only hay chỉ được kiểm tra ở lần gọi tiếp theo phụ thuộc transaction manager, driver và database. Ứng dụng phải bảo đảm transaction không bị để mở sau khi deadline đã hết.

## 4. Phân biệt transaction timeout và idle-in-transaction timeout

Hai giới hạn này thường bị nhầm vì đều liên quan đến transaction kéo dài.

- **Transaction timeout:** đo tổng tuổi transaction, bao gồm thời gian chạy statement và thời gian giữa các statement.
- **Idle-in-transaction timeout:** chỉ đo khoảng thời gian transaction đang mở nhưng session không chạy statement, ví dụ ứng dụng đã đọc dữ liệu rồi chờ người dùng hoặc chờ một dịch vụ khác.

Ví dụ:

```text
BEGIN
  SELECT ...                 chạy 1 giây
  ứng dụng chờ người dùng    idle 30 giây
  UPDATE ...                 chạy 1 giây
COMMIT

Tuổi transaction: khoảng 32 giây
Thời gian idle trong transaction: 30 giây
```

Nếu transaction timeout là 20 giây, transaction vượt giới hạn tổng tuổi. Nếu idle-in-transaction timeout là 10 giây, session có thể bị chấm dứt trong lúc ứng dụng đang chờ người dùng, dù chưa tới transaction timeout.

Idle transaction đặc biệt nguy hiểm trong hệ thống MVCC và quản lý khóa. Nó có thể giữ khóa, giữ snapshot cũ, ngăn dọn dẹp phiên bản dữ liệu hoặc chiếm connection trong pool dù không thực hiện công việc hữu ích. Vì vậy, cần tránh mở transaction trước khi người dùng nhập liệu hoặc trong lúc gọi dịch vụ bên ngoài.

## 5. So sánh ba loại thời hạn

| Tiêu chí | Lock wait timeout | Statement timeout | Transaction timeout |
|---|---|---|---|
| Phạm vi | Một lần chờ lấy khóa | Một câu lệnh SQL | Toàn bộ transaction |
| Bắt đầu tính | Khi yêu cầu khóa phải chờ | Khi statement bắt đầu | Khi transaction bắt đầu |
| Bao gồm thời gian chạy SQL? | Không, chỉ thời gian chờ khóa | Có | Có |
| Bao gồm thời gian giữa hai statement? | Không | Không | Có |
| Bắt được truy vấn chậm không do khóa? | Không | Có | Có, nếu transaction vượt tổng deadline |
| Bắt được transaction mở lâu khi ứng dụng chờ? | Không | Không | Có, nếu là giới hạn tổng transaction |
| Phạm vi cấu hình | Thường ở database/session/statement | Database, driver hoặc client | Database, transaction manager hoặc ứng dụng |

## 6. Ba timeout cùng tác động lên một thao tác

Ba giới hạn có thể cùng áp dụng trong một transaction. Giới hạn nào hết trước sẽ quyết định thao tác bị dừng trước, nhưng cách hủy và trạng thái transaction phụ thuộc hệ quản trị.

Giả sử:

- Lock wait timeout: 2 giây.
- Statement timeout: 5 giây.
- Transaction deadline: 8 giây tính từ lúc `BEGIN`.

Nếu transaction mới bắt đầu và ngay lập tức chờ khóa, lock wait timeout có thể xảy ra sau 2 giây. Nếu khóa được cấp sau 1 giây nhưng truy vấn tiếp tục tính toán lâu, statement timeout có thể kết thúc statement ở mốc 5 giây kể từ khi statement bắt đầu. Nếu mỗi statement đều ngắn nhưng tổng transaction kéo dài quá 8 giây, transaction deadline có thể là giới hạn cuối cùng.

```text
Thời gian từ BEGIN
0s          2s             5s                 8s
|-----------|--------------|------------------|
BEGIN       lock wait      statement budget   transaction deadline
            có thể hết     có thể hết         có thể hết

Giới hạn sớm nhất có thể kết thúc công việc trước.
```

Sơ đồ chỉ minh họa ba ngân sách cùng tồn tại. Thực tế, statement có thể bắt đầu muộn hơn transaction; lock wait có thể bắt đầu ở giữa statement; transaction manager có thể tính deadline từ lúc bắt đầu xử lý nghiệp vụ thay vì đúng thời điểm database nhận `BEGIN`.

## 7. Cách phối hợp các deadline

Một thiết kế thường đặt giới hạn theo thứ tự:

\[
T_{lock} < T_{statement} < T_{transaction} < T_{request}
\]

Đây là một hướng thiết kế phổ biến, không phải điều kiện bắt buộc. Ý tưởng là phát hiện tranh chấp khóa sớm, cho statement đủ thời gian thực thi, giữ tổng transaction trong giới hạn và để request còn một khoảng thời gian xử lý lỗi hoặc trả phản hồi.

Ví dụ ngân sách:

| Giới hạn | Giá trị minh họa | Mục tiêu |
|---|---:|---|
| Lock wait | 1 giây | Không chờ một khóa quá lâu |
| Statement | 4 giây | Giới hạn một truy vấn hoặc cập nhật |
| Transaction | 7 giây | Giới hạn tổng thời gian transaction |
| HTTP request | 9 giây | Còn thời gian rollback, ghi log và trả phản hồi |

Các giá trị trên chỉ để minh họa cách phân tầng. Cần chọn theo SLA, thời gian truy vấn bình thường, độ trễ mạng, tải cao điểm và hành vi timeout thực tế của hệ thống.

Một số lưu ý:

- Nếu lock timeout lớn hơn statement timeout, statement timeout có thể kết thúc câu lệnh trước khi lock timeout hết hạn.
- Nếu statement timeout lớn hơn thời gian còn lại của transaction, transaction deadline có thể hết trước.
- Nếu request deadline hết nhưng database vẫn đang chạy, ứng dụng cần cơ chế hủy câu lệnh hoặc đóng/rollback transaction; chỉ ngừng chờ ở HTTP layer có thể để database tiếp tục làm việc.
- Timeout theo session cần được đặt lại hoặc khôi phục khi dùng connection pool để request tiếp theo không kế thừa cấu hình ngoài ý muốn.
- Cần dành một phần ngân sách cho rollback và xử lý lỗi; không đặt mọi timeout đúng bằng request deadline.

## 8. Timeout không đồng nghĩa với deadlock

Timeout là một giới hạn thời gian. Deadlock là một chu trình chờ mà các transaction giữ tài nguyên cần thiết cho nhau.

```text
T1 giữ khóa A và chờ khóa B
T2 giữ khóa B và chờ khóa A

T1 cần T2 nhả B.
T2 cần T1 nhả A.
       -> deadlock
```

Hệ quản trị có cơ chế phát hiện deadlock có thể hủy một transaction nạn nhân ngay khi phát hiện chu trình, không cần đợi lock timeout hoặc statement timeout hết hạn. Ngược lại, một transaction có thể chờ một khóa rất lâu mà không tạo chu trình; trường hợp đó có thể kết thúc bởi lock timeout hoặc statement timeout.

Khi điều tra lỗi, cần phân biệt:

- Lock timeout: một yêu cầu khóa đã chờ quá giới hạn.
- Statement timeout: toàn bộ câu lệnh chạy quá thời hạn.
- Transaction timeout: transaction tồn tại quá thời hạn tổng.
- Deadlock victim: hệ quản trị phát hiện chu trình và chọn transaction bị hủy.
- Client/request timeout: ứng dụng hoặc gateway ngừng chờ; database có thể vẫn đang xử lý nếu chưa nhận được tín hiệu hủy.

## 9. Sau timeout, transaction có trạng thái gì?

Không phải timeout nào cũng có cùng hành vi rollback. Đây là lý do ứng dụng không nên bắt mọi lỗi timeout rồi tiếp tục chạy câu SQL tiếp theo trong cùng transaction.

| Hệ quản trị/cơ chế | Hành vi cần lưu ý |
|---|---|
| PostgreSQL statement error | Transaction thường chuyển sang trạng thái lỗi; cần `ROLLBACK` hoặc rollback về savepoint trước khi tiếp tục. |
| MySQL InnoDB lock wait timeout | Mặc định thường rollback statement; tùy cấu hình có thể rollback toàn transaction. Ứng dụng cần quyết định rollback nếu nghiệp vụ không thể tiếp tục. |
| SQL Server lock timeout | Statement bị hủy; transaction có thể vẫn tồn tại tùy trạng thái và cấu hình xử lý lỗi. Cần kiểm tra `XACT_STATE()`/trạng thái transaction trước khi tiếp tục. |
| Client-side query timeout | Client/driver có thể gửi yêu cầu hủy; việc statement dừng và transaction được rollback hay không phụ thuộc driver/database. |
| Transaction manager deadline | Có thể đánh dấu transaction rollback-only hoặc yêu cầu hủy statement; cần tuân theo transaction manager và driver. |

Một luồng xử lý an toàn thường là:

1. Phân loại lỗi theo mã lỗi và nguồn phát sinh, không chỉ dựa vào thông điệp chứa chữ “timeout”.
2. Dừng các thao tác tiếp theo phụ thuộc kết quả của statement thất bại.
3. Kiểm tra transaction còn hoạt động, đã bị hủy hay ở trạng thái rollback-only theo API của driver/framework.
4. Rollback transaction nếu không thể bảo đảm tính nhất quán.
5. Chỉ retry toàn bộ đơn vị nghiệp vụ khi lỗi có thể thử lại và thao tác an toàn khi lặp.
6. Không trả thành công cho request khi commit chưa được xác nhận.

Đặc biệt, nếu client mất kết nối đúng lúc gửi `COMMIT`, kết quả commit có thể không rõ ràng với ứng dụng: database có thể đã commit nhưng phản hồi không tới được client. Không nên mặc định chạy lại thao tác tạo đơn hàng hoặc thanh toán ngay lập tức. Hãy dùng idempotency key hoặc cơ chế truy vấn trạng thái để xác định kết quả.

## 10. Ví dụ cấu hình kết hợp trong PostgreSQL

PostgreSQL minh họa khá rõ ba phạm vi timeout. Ví dụ sau giả định phiên bản hỗ trợ `transaction_timeout` (PostgreSQL 17 trở lên):

```sql
-- Cấu hình ở phạm vi session; giá trị thực tế phải phù hợp workload.
SET lock_timeout = '1s';
SET statement_timeout = '4s';
SET transaction_timeout = '7s';

BEGIN;

UPDATE account
SET balance = balance - 100
WHERE id = 10;

COMMIT;
```

`lock_timeout` giới hạn thời gian chờ khóa; `statement_timeout` giới hạn từng statement; `transaction_timeout` giới hạn tuổi transaction. Cần kiểm tra phiên bản PostgreSQL, quyền cấu hình và chính sách triển khai trước khi dùng `transaction_timeout`. Nếu hệ thống chạy PostgreSQL cũ hơn, có thể cần transaction deadline ở tầng ứng dụng hoặc transaction manager.

Để tránh cấu hình session rò rỉ qua connection pool, có thể dùng `SET LOCAL` cho các tham số phù hợp bên trong transaction:

```sql
BEGIN;

SET LOCAL lock_timeout = '1s';
SET LOCAL statement_timeout = '4s';

-- Các câu lệnh nghiệp vụ

COMMIT;
```

`SET LOCAL` chỉ có hiệu lực trong transaction hiện tại. Không phải mọi tham số đều có thể đặt theo cùng cách ở mọi phiên bản; cần xem tài liệu PostgreSQL đang dùng.

## 11. Ví dụ cấu hình ở tầng ứng dụng

Trong nhiều ứng dụng Java, timeout có thể được đặt ở nhiều lớp:

- Transaction manager/framework giới hạn thời gian transaction.
- JDBC `Statement.setQueryTimeout(...)` hoặc API tương đương giới hạn thời gian chờ thực thi statement ở phía client.
- Database session đặt lock timeout và statement timeout.
- HTTP server hoặc gateway đặt deadline cho request.

Các lớp này không tự động đồng bộ. Ví dụ, HTTP request có deadline 5 giây nhưng JDBC query timeout là 30 giây. Người dùng có thể đã nhận lỗi gateway trong khi câu truy vấn vẫn chạy thêm 25 giây nếu việc hủy không được truyền xuống database.

Một mô hình quản lý deadline ở tầng ứng dụng:

```text
Request deadline: 8 giây
       |
       +-- bắt đầu transaction, còn 8 giây
       |
       +-- chạy statement 1, timeout tối đa 3 giây
       |
       +-- chạy statement 2, chỉ dùng phần thời gian còn lại
       |
       +-- nếu deadline gần hết:
              hủy statement nếu có thể
              rollback transaction
              trả lỗi timeout phù hợp
```

Nếu transaction manager không tự hủy câu SQL đang chạy, ứng dụng cần cấu hình query timeout hoặc cơ chế cancellation ở driver. Việc hủy statement cũng không thay thế rollback; transaction có thể còn giữ khóa nếu vẫn mở.

## 12. Quan sát và chẩn đoán timeout

Khi hệ thống có timeout, cần thu thập đủ thông tin để biết giới hạn nào đã kích hoạt:

- Mã lỗi SQLState/vendor code và tên exception ở tầng ứng dụng.
- Loại timeout: lock wait, statement, transaction, idle transaction, client query hay request deadline.
- Thời điểm bắt đầu transaction và statement, thời điểm timeout xảy ra.
- Câu lệnh hoặc loại thao tác đang chạy, thời gian thực thi và thời gian chờ khóa.
- Transaction giữ khóa hoặc snapshot lâu nhất, cùng tài nguyên bị tranh chấp.
- Trạng thái transaction sau lỗi và kết quả rollback/commit.
- Số lần retry, thời gian backoff và tỷ lệ retry thành công.

Không ghi thông tin nhạy cảm như dữ liệu cá nhân, token hoặc giá trị bí mật vào log. Có thể ghi tên thao tác, mã truy vết, loại tài nguyên, thời lượng và mã lỗi để điều tra.

## 13. Những điểm cần nhớ

- Lock wait timeout giới hạn thời gian chờ để lấy khóa, không giới hạn tổng thời gian chạy truy vấn.
- Statement timeout giới hạn tổng thời gian của một câu lệnh và thường bao gồm cả thời gian câu lệnh chờ khóa.
- Transaction timeout giới hạn tuổi của toàn transaction, bao gồm nhiều statement và thời gian giữa chúng nếu transaction vẫn mở.
- Idle-in-transaction timeout chỉ giới hạn thời gian session không chạy statement trong khi transaction vẫn mở; nó khác giới hạn tổng transaction.
- Không có một cú pháp transaction timeout SQL dùng chung cho mọi database; cần xác định timeout được thực thi ở database, transaction manager hay ứng dụng.
- Lock timeout, statement timeout và transaction timeout có thể cùng tồn tại; giới hạn nào hết trước có thể kết thúc công việc trước.
- Deadlock là chu trình chờ, không phải một loại timeout; hệ quản trị có thể phát hiện và hủy transaction trước khi timeout hết hạn.
- Hủy statement không bảo đảm transaction tự rollback trong mọi hệ quản trị. Ứng dụng phải kiểm tra trạng thái và rollback khi cần.
- Client ngừng chờ không đồng nghĩa database đã dừng truy vấn; cần cơ chế cancellation và cleanup rõ ràng.

Khi thiết kế thời hạn cho một thao tác cơ sở dữ liệu, hãy xác định rõ giới hạn nào đang bảo vệ tài nguyên, giới hạn nào bảo vệ một câu SQL và giới hạn nào bảo vệ toàn bộ đơn vị nghiệp vụ. Phối hợp chúng với deadline của request, dành thời gian cho rollback và xử lý lỗi, rồi kiểm tra hành vi thực tế của database và driver để tránh transaction bị bỏ mở sau timeout.
