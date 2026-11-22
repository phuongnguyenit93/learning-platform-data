# Phiên bản cũ, undo và nhu cầu giữ lịch sử dữ liệu

MVCC (Multi-Version Concurrency Control) cho phép nhiều giao dịch đọc và ghi cùng một dữ liệu mà không buộc mọi thao tác phải chờ nhau bằng khóa đọc/ghi. Để làm được điều đó, hệ quản trị cơ sở dữ liệu phải duy trì đủ thông tin về các phiên bản trước của một bản ghi. Một giao dịch đọc có thể cần nhìn thấy giá trị đã tồn tại tại thời điểm ảnh chụp của nó được tạo, ngay cả khi giao dịch khác đã cập nhật và commit giá trị mới.

Trong MySQL InnoDB, **undo log** lưu thông tin cần thiết để hoàn tác thay đổi và dựng lại phiên bản cũ của bản ghi. Các phiên bản cũ không được giữ vô thời hạn. InnoDB chỉ có thể loại bỏ chúng khi không còn giao dịch nào có ảnh chụp nhất quán cần đọc những phiên bản đó. Công việc dọn dẹp này do cơ chế **purge** thực hiện.

Vì vậy, thời gian sống của một phiên bản cũ phụ thuộc vào lịch sử giao dịch đang hoạt động. Một transaction đọc mở lâu có thể giữ một ảnh chụp cũ và ngăn InnoDB dọn nhiều undo record, dù ứng dụng đã chạy xong câu `SELECT` từ lâu.

Các ví dụ trong bài tập trung vào MySQL InnoDB. Những hệ quản trị khác cũng có thể dùng MVCC và undo/version store, nhưng cách lưu phiên bản, quy tắc giữ lịch sử và công cụ theo dõi khác nhau.

## 1. Vì sao cần lưu phiên bản cũ?

Giả sử hàng `accounts` có số dư ban đầu là 500. Giao dịch A bắt đầu đọc dữ liệu và lấy ảnh chụp nhất quán. Sau đó, giao dịch B cập nhật số dư thành 700 rồi commit.

Nếu InnoDB chỉ lưu giá trị mới nhất là 700, giao dịch A sẽ không thể trả lời nhất quán cho câu hỏi: “Số dư tại thời điểm ảnh chụp của A là bao nhiêu?”. Để A tiếp tục nhìn thấy 500, InnoDB phải có cách dựng lại phiên bản trước đó.

MVCC giải quyết vấn đề này bằng hai thành phần phối hợp:

- **Read view (ảnh chụp đọc):** mô tả ranh giới hiển thị của các giao dịch tại một thời điểm. Nó giúp quyết định phiên bản nào một consistent read được phép nhìn thấy.
- **Undo log:** giữ thông tin cần thiết để quay từ phiên bản hiện tại về phiên bản trước, nếu phiên bản hiện tại không nhìn thấy được trong read view.

Một giao dịch đọc thường không cần khóa độc quyền hàng chỉ để giữ một giá trị cũ. Thay vào đó, InnoDB dùng thông tin phiên bản và read view để chọn dữ liệu phù hợp. Giao dịch ghi vẫn phải phối hợp qua các cơ chế khóa của InnoDB; MVCC không loại bỏ mọi loại khóa.

## 2. Phiên bản hàng được lưu như thế nào trong InnoDB?

Với bảng InnoDB, bản ghi trong clustered index chứa các cột hệ thống phục vụ quản lý phiên bản. Hai cột quan trọng là:

- `DB_TRX_ID`: transaction ID của giao dịch gần nhất tạo hoặc sửa phiên bản hàng hiện tại.
- `DB_ROLL_PTR`: con trỏ đến undo record có thông tin để dựng lại phiên bản trước.

Nếu bảng không khai báo khóa chính hoặc khóa duy nhất phù hợp, InnoDB có thể tạo row ID nội bộ (`DB_ROW_ID`) để định danh hàng. Row ID không phải thành phần quyết định tính hiển thị MVCC.

Hình dung một hàng đã được cập nhật nhiều lần như sau:

```text
Clustered index: phiên bản hiện tại
┌────────────────────────────────────┐
│ id = 10, balance = 900             │
│ DB_TRX_ID = 305                    │
│ DB_ROLL_PTR ───────────────────────┼────┐
└────────────────────────────────────┘    │
                                          ▼
                                  Undo record của phiên bản trước
                                  ┌──────────────────────────────┐
                                  │ balance = 700                │
                                  │ thông tin phiên bản cũ       │
                                  │ roll pointer ────────────────┼──┐
                                  └──────────────────────────────┘  │
                                                                  ▼
                                                          Undo record cũ hơn
                                                          ┌──────────────────┐
                                                          │ balance = 500    │
                                                          └──────────────────┘
```

Sơ đồ thể hiện quan hệ logic. Undo record không nhất thiết chứa nguyên một bản sao đầy đủ của tất cả cột; nó chứa thông tin cần thiết để hoàn tác hoặc tái tạo phiên bản trước. Khi một consistent read cần giá trị cũ, InnoDB dùng `DB_ROLL_PTR` để lần theo chuỗi undo và dựng phiên bản phù hợp.

Nếu một hàng được cập nhật nhiều lần, có thể tồn tại nhiều undo record nối tiếp nhau. Một read view cũ có thể cần lùi qua nhiều phiên bản trước khi tìm được phiên bản hiển thị. Do đó, chi phí đọc phiên bản cũ có thể tăng khi chuỗi lịch sử dài.

## 3. Undo log phục vụ cả rollback và MVCC

Undo log không chỉ tồn tại để phục vụ consistent read. Nó còn giúp InnoDB hoàn tác thay đổi chưa commit.

Ví dụ, một transaction thực hiện:

```sql
START TRANSACTION;

UPDATE accounts
SET balance = balance - 100
WHERE id = 10;

-- Một bước nghiệp vụ tiếp theo thất bại.
ROLLBACK;
```

InnoDB cần thông tin undo để khôi phục giá trị trước khi transaction thay đổi hàng. Khi transaction bị rollback, undo được áp dụng để hoàn tác các thay đổi. Trong quá trình crash recovery, InnoDB cũng cần xử lý các transaction chưa hoàn tất và hoàn tác thay đổi của chúng khi cần.

Có thể phân biệt khái quát hai loại undo log:

| Loại undo | Vai trò | Vòng đời khái quát |
|---|---|---|
| Insert undo | Hoàn tác thao tác chèn hàng của transaction chưa commit | Sau khi transaction commit, thông tin insert undo thường không còn cần cho consistent read cũ và có thể được giải phóng. |
| Update undo | Hoàn tác cập nhật hoặc xóa, đồng thời hỗ trợ dựng phiên bản trước cho consistent read | Sau commit, có thể phải được giữ trong history cho đến khi không còn read view nào cần phiên bản cũ. |

Điểm quan trọng là **commit không đồng nghĩa với việc mọi undo record được xóa ngay**. Transaction đã commit không còn cần undo để rollback thông thường, nhưng update undo của nó vẫn có thể cần thiết cho một transaction đọc cũ hơn.

## 4. Read view quyết định phiên bản nào được nhìn thấy

Read view ghi nhận trạng thái các transaction tại thời điểm ảnh chụp được tạo. Nó giúp consistent read xác định transaction nào đã hoàn tất trước ảnh chụp, transaction nào còn hoạt động và transaction nào bắt đầu sau đó.

Ở mức khái niệm, khi xét phiên bản được tạo bởi transaction X, InnoDB phải xác định:

1. X có phải chính transaction đang đọc không? Transaction thường nhìn thấy thay đổi của chính nó.
2. X đã hoàn tất trước khi read view được tạo chưa? Nếu có, phiên bản có thể hiển thị.
3. X còn hoạt động tại thời điểm read view được tạo không? Nếu có, phiên bản của X chưa hiển thị với ảnh chụp đó, kể cả khi X commit sau này.
4. X có bắt đầu sau thời điểm ảnh chụp không? Nếu có, phiên bản của X không thuộc ảnh chụp.

Nếu phiên bản hiện tại không nhìn thấy được, InnoDB lần theo undo để dựng phiên bản cũ hơn rồi kiểm tra lại. Quá trình tiếp tục cho đến khi tìm được phiên bản phù hợp hoặc xác định hàng chưa tồn tại trong ảnh chụp.

Read view của InnoDB có các thông tin nội bộ tương ứng với transaction ID của transaction tạo ảnh chụp, transaction ID nhỏ nhất và giới hạn transaction ID tiếp theo, cùng danh sách transaction đang hoạt động tại thời điểm tạo ảnh chụp. Có thể hiểu quy tắc hiển thị qua ví dụ:

| Trạng thái transaction ghi | Kết quả đối với read view đã tạo trước đó |
|---|---|
| Đã commit trước khi ảnh chụp được tạo | Phiên bản có thể hiển thị. |
| Đang hoạt động lúc ảnh chụp được tạo | Phiên bản không hiển thị trong ảnh chụp đó. |
| Bắt đầu sau khi ảnh chụp được tạo | Phiên bản không hiển thị trong ảnh chụp đó. |
| Là transaction đang đọc | Thay đổi của chính transaction được xử lý theo quy tắc read-your-own-writes. |

Một transaction đang hoạt động khi read view được tạo vẫn bị xem là chưa hoàn tất trong ảnh chụp đó, ngay cả khi nó commit trước lần `SELECT` tiếp theo. Đây là lý do hai câu đọc trong cùng một transaction `REPEATABLE READ` có thể tiếp tục thấy cùng một giá trị cũ.

## 5. Ảnh chụp theo câu lệnh và theo giao dịch

Thời điểm tạo read view phụ thuộc isolation level. Trong InnoDB, sự khác nhau thường được quan tâm nhất là `READ COMMITTED` và `REPEATABLE READ`.

### READ COMMITTED: ảnh chụp mới cho mỗi consistent read

Với `READ COMMITTED`, mỗi consistent read thông thường tạo read view mới khi câu đọc bắt đầu. Vì vậy, hai câu `SELECT` trong cùng transaction có thể nhìn thấy dữ liệu khác nhau nếu transaction khác commit ở giữa hai câu.

Giả sử số dư ban đầu là 500:

```text
Thời gian       Transaction A (READ COMMITTED)    Transaction B
---------       ------------------------------    -------------
t1              BEGIN
t2              SELECT balance -> 500
t3                                                  UPDATE balance = 700
t4                                                  COMMIT
t5              SELECT balance -> 700
t6              COMMIT
```

Ở câu đọc tại `t2`, read view được tạo trước khi B commit nên A thấy 500. Đến câu đọc tại `t5`, A có read view mới nên có thể thấy phiên bản 700 đã commit.

### REPEATABLE READ: các consistent read dùng cùng ảnh chụp

Với `REPEATABLE READ` mặc định của InnoDB, read view cho consistent read thường được tạo ở lần consistent read đầu tiên của transaction và được tái sử dụng cho các consistent read tiếp theo trong transaction đó.

```text
Thời gian       Transaction A (REPEATABLE READ)  Transaction B
---------       ------------------------------    -------------
t1              BEGIN
t2              SELECT balance -> 500
                (read view được tạo)
t3                                                  UPDATE balance = 700
t4                                                  COMMIT
t5              SELECT balance -> 500
                (dùng lại read view cũ)
t6              COMMIT
```

Mặc dù B đã commit trước câu đọc thứ hai, A vẫn thấy 500 vì ảnh chụp của A được tạo trước khi B commit. Sau khi A commit, transaction tiếp theo có thể tạo ảnh chụp mới và thấy 700.

Nếu ứng dụng cần tạo ảnh chụp nhất quán ngay khi bắt đầu transaction thay vì đợi consistent read đầu tiên, MySQL hỗ trợ:

```sql
SET TRANSACTION ISOLATION LEVEL REPEATABLE READ;
START TRANSACTION WITH CONSISTENT SNAPSHOT;

SELECT balance
FROM accounts
WHERE id = 10;

COMMIT;
```

`WITH CONSISTENT SNAPSHOT` có ý nghĩa với `REPEATABLE READ`; ở isolation level khác, yêu cầu này không tạo ra cùng hành vi snapshot như vậy. Hãy kiểm tra tài liệu của phiên bản MySQL đang triển khai.

### Bảng so sánh

| Đặc điểm | READ COMMITTED | REPEATABLE READ (InnoDB) |
|---|---|---|
| Read view của consistent read | Tạo mới cho từng câu đọc | Dùng lại read view của transaction sau khi được tạo |
| Hai câu SELECT trong cùng transaction | Có thể thấy hai trạng thái đã commit khác nhau | Thường thấy cùng ảnh chụp đối với các consistent read |
| Thời điểm read view thông thường được tạo | Khi mỗi consistent read bắt đầu | Ở consistent read đầu tiên của transaction |
| Ảnh hưởng đến purge | Read view thường tồn tại ngắn hơn nếu câu đọc kết thúc | Một transaction giữ snapshot lâu có thể giữ lại lịch sử lâu hơn |

`autocommit=1` thường làm mỗi câu lệnh trở thành một transaction riêng. Do đó, một câu `SELECT` đơn lẻ thường không giữ read view qua câu lệnh kế tiếp. Tuy nhiên, ứng dụng có thể mở transaction tường minh hoặc tắt autocommit, khiến read view tồn tại lâu hơn.

## 6. Consistent read và current read không giống nhau

Không phải mọi câu lệnh đọc trong InnoDB đều dùng read view theo cùng cách. Cần phân biệt consistent read với locking/current read.

**Consistent read** là kiểu đọc thông thường, chẳng hạn:

```sql
SELECT balance
FROM accounts
WHERE id = 10;
```

Nó dùng read view và có thể dựng lại phiên bản cũ bằng undo để trả về dữ liệu phù hợp với ảnh chụp.

**Current read** đọc phiên bản hiện tại cần thiết cho thao tác khóa hoặc ghi. Những câu lệnh thường thuộc nhóm này gồm:

```sql
SELECT balance
FROM accounts
WHERE id = 10
FOR UPDATE;

SELECT balance
FROM accounts
WHERE id = 10
FOR SHARE;

UPDATE accounts
SET balance = balance - 100
WHERE id = 10;
```

Locking read và thao tác ghi phải xét dữ liệu hiện tại theo quy tắc khóa của InnoDB để tránh cập nhật dựa trên một phiên bản cũ không còn phù hợp. Chúng có thể chờ transaction khác và lấy khóa hàng hoặc khóa khoảng. Vì vậy, trong cùng một transaction `REPEATABLE READ`, một câu `SELECT` thông thường có thể thấy snapshot cũ trong khi `SELECT ... FOR UPDATE` thấy trạng thái hiện tại mới hơn.

Ví dụ:

```text
Transaction A (REPEATABLE READ)        Transaction B
--------------------------------        -------------
BEGIN
SELECT balance -> 500
(read view được tạo)
                                        UPDATE balance = 700
                                        COMMIT
SELECT balance -> 500
SELECT balance FOR UPDATE -> 700
```

Ví dụ minh họa sự khác nhau giữa consistent read và current read. Câu locking read còn có thể bị ảnh hưởng bởi xung đột khóa và các quy tắc cụ thể của câu lệnh. Không nên dùng kết quả của hai kiểu đọc như thể chúng luôn đại diện cho cùng một snapshot.

## 7. Purge: khi nào phiên bản cũ được phép biến mất?

Undo history phải được giữ đủ lâu để mọi read view đang tồn tại có thể dựng lại phiên bản mà nó cần. Nếu một transaction vẫn có thể nhìn thấy phiên bản cũ, InnoDB chưa được phép xóa undo record cần cho phiên bản đó.

Sau khi không còn read view nào cần một phiên bản cũ, InnoDB có thể dọn phần lịch sử tương ứng. Công việc này gọi là **purge**. Purge chạy nền, xử lý các undo log đã commit và những bản ghi đã được đánh dấu xóa khi chúng không còn cần thiết cho MVCC.

Với thao tác `DELETE`, InnoDB thường đánh dấu bản ghi là đã xóa trước. Bản ghi và các mục chỉ mục liên quan chỉ có thể được loại bỏ vật lý khi purge xác định rằng không còn read view nào cần nhìn thấy phiên bản trước khi xóa.

Chu trình khái quát:

```text
Transaction ghi cập nhật hoặc xóa hàng
                 |
                 v
       Tạo thông tin undo cần thiết
                 |
                 v
       Transaction ghi COMMIT
                 |
                 v
       Undo cần cho phiên bản cũ
       được giữ trong history
                 |
                 v
       Các read view liên quan kết thúc
                 |
                 v
       Purge xác định phiên bản đã hết nhu cầu
                 |
                 v
       Dọn undo history và bản ghi delete-marked
```

Commit chỉ kết thúc transaction ghi. Nó không đảm bảo mọi phiên bản cũ có thể bị dọn ngay, vì có thể vẫn còn transaction đọc đang giữ ảnh chụp cũ.

## 8. Ví dụ: một snapshot cũ giữ lại undo history

Giả sử bảng `products` có hàng `id = 1`, `price = 100`.

**Session A — mở transaction đọc:**

```sql
SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ;
START TRANSACTION;

SELECT price
FROM products
WHERE id = 1;
-- Kết quả: 100. Read view của A được tạo.
```

**Session B — cập nhật và commit:**

```sql
UPDATE products
SET price = 120
WHERE id = 1;

COMMIT;
```

InnoDB lưu thông tin undo để có thể dựng lại `price = 100`. Phiên bản hiện tại là 120, nhưng A vẫn cần phiên bản 100.

**Session A — đọc lại:**

```sql
SELECT price
FROM products
WHERE id = 1;
-- Vẫn thấy 100 trong read view cũ.
```

Trong lúc A còn giữ transaction và read view, purge không thể loại bỏ undo cần thiết để dựng giá trị 100. Sau khi A kết thúc transaction:

```sql
COMMIT;
```

Nếu không còn read view nào khác cần phiên bản cũ, purge có thể dọn undo history tương ứng. Việc dọn là công việc nền, nên không nhất thiết diễn ra đúng vào thời điểm câu `COMMIT` của A trả về.

## 9. Transaction dài làm tăng history như thế nào?

Một transaction đọc dài có thể không cập nhật hàng nào nhưng vẫn giữ read view cũ. Trong khi đó, các transaction khác tiếp tục cập nhật và xóa dữ liệu. Những transaction ghi này tạo undo history mới, nhưng purge phải giữ lại phần lịch sử cần cho snapshot cũ.

Kết quả có thể là:

- History list tăng vì undo log đã commit chưa thể được purge.
- Các phiên bản cũ của cùng một hàng tồn tại lâu hơn.
- Một consistent read có thể phải lần qua chuỗi phiên bản dài hơn để tìm phiên bản hiển thị.
- Undo tablespace có thể cần nhiều dung lượng hơn; dung lượng tệp không nhất thiết giảm ngay khi lịch sử được purge.
- Purge phải xử lý backlog lớn sau khi transaction giữ snapshot kết thúc, tạo thêm tải I/O và CPU.

Một transaction ghi dài cũng có tác động riêng: undo của thay đổi chưa commit phải được giữ để rollback nếu cần; transaction đó chưa đưa phần update undo tương ứng vào history như một transaction đã commit. Khi có cả transaction đọc giữ snapshot cũ và transaction ghi dài, nhiều loại nhu cầu giữ undo có thể cùng tồn tại.

Không phải mọi transaction mở lâu đều chắc chắn ghim một read view cũ. Với `REPEATABLE READ`, read view consistent read thông thường chỉ được tạo khi có consistent read đầu tiên, trừ trường hợp yêu cầu `WITH CONSISTENT SNAPSHOT`. Với `READ COMMITTED`, read view của một câu đọc thường kết thúc cùng câu đọc. Khi điều tra, cần xem transaction đã tạo snapshot chưa, isolation level là gì và câu lệnh nào đang chạy.

## 10. History list length nói lên điều gì?

InnoDB theo dõi lượng undo history đang chờ purge. Trong `SHOW ENGINE INNODB STATUS`, phần TRANSACTIONS thường hiển thị thông tin như:

```text
History list length 12345
```

`History list length` là chỉ số về số trang undo log trong history list, không phải số hàng đã cập nhật, không phải số transaction đang mở và cũng không phải số phiên bản hàng chính xác. Nó hữu ích nhất khi theo dõi xu hướng theo thời gian và đối chiếu với transaction lâu nhất, tốc độ ghi và năng lực purge.

History list tăng trong một khoảng tải ghi cao chưa chắc là sự cố. Nếu purge không theo kịp hoặc một snapshot cũ giữ lịch sử quá lâu, giá trị có thể tăng liên tục và duy trì ở mức cao. Sau khi transaction giữ snapshot kết thúc, history list có thể giảm dần khi purge bắt kịp.

Undo tablespace và history list cũng là hai khái niệm khác nhau. Purge giải phóng các undo record không còn cần thiết để InnoDB tái sử dụng không gian; điều đó không đồng nghĩa kích thước tệp undo trên filesystem lập tức giảm. Việc thu nhỏ hoặc truncate tablespace có cơ chế và điều kiện riêng.

## 11. Theo dõi transaction và purge trong MySQL

### Tìm transaction mở lâu

```sql
SELECT
    trx_id,
    trx_mysql_thread_id AS connection_id,
    trx_started,
    TIMESTAMPDIFF(SECOND, trx_started, NOW()) AS age_seconds,
    trx_state,
    trx_rows_locked,
    trx_rows_modified,
    trx_query
FROM information_schema.innodb_trx
ORDER BY trx_started;
```

Đặc biệt chú ý transaction có `age_seconds` lớn. `trx_query` có thể rỗng nếu kết nối đang nhàn rỗi giữa các câu lệnh; transaction vẫn có thể đang mở. Đối chiếu `connection_id` với process list để xác định ứng dụng hoặc phiên kết nối sở hữu transaction.

### Xem trạng thái InnoDB

```sql
SHOW ENGINE INNODB STATUS\G
```

Trong phần `TRANSACTIONS`, xem transaction đang hoạt động, thời điểm bắt đầu và `History list length`. Phần này cung cấp ảnh chụp trạng thái tại thời điểm chạy lệnh; hãy lấy mẫu nhiều lần để nhận biết xu hướng thay vì kết luận từ một con số đơn lẻ.

### Xem metric history list

Trên phiên bản MySQL có metric tương ứng trong `INFORMATION_SCHEMA.INNODB_METRICS`, có thể truy vấn:

```sql
SELECT NAME, COUNT
FROM information_schema.innodb_metrics
WHERE NAME = 'trx_rseg_history_len';
```

Metric có thể cần được bật tùy cấu hình và phiên bản. Nếu không có kết quả, hãy dùng `SHOW ENGINE INNODB STATUS` và kiểm tra trạng thái metric thay vì suy ra rằng hệ thống không có undo history.

Khi chẩn đoán, kết hợp ít nhất ba dữ kiện:

1. Transaction nào có thời gian mở lâu nhất và thuộc ứng dụng nào?
2. Transaction đó đang dùng isolation level nào, đã thực hiện consistent read chưa và còn giữ read view không?
3. History list length đang tăng, ổn định hay giảm? Tốc độ ghi và purge có thay đổi cùng thời điểm không?

## 12. Giảm nguy cơ giữ lịch sử quá lâu

### Kết thúc transaction đúng thời điểm

- Mở transaction ngay trước nhóm thao tác cần tính nguyên tử.
- Commit hoặc rollback sau khi hoàn tất nhóm thao tác.
- Không gọi HTTP/RPC, gửi email, chờ người dùng hoặc chờ tác vụ ngoài cơ sở dữ liệu trong khi vẫn giữ transaction nếu không cần thiết.
- Đảm bảo mọi nhánh exception đều rollback hoặc đóng transaction trước khi trả connection về pool.
- Không để kết nối ở trạng thái nhàn rỗi với transaction mở.

### Chia nhỏ công việc ghi lớn

Batch cập nhật hoặc xóa hàng triệu bản ghi trong một transaction có thể giữ undo của transaction đó trong thời gian dài và tạo backlog lớn. Có thể chia công việc thành các lô nhỏ, commit theo từng lô và theo dõi tính nhất quán nghiệp vụ. Mỗi lần commit giúp InnoDB có cơ hội đưa update undo đã hoàn tất vào history để purge xử lý khi không còn snapshot cần nó.

Việc chia lô cần có khóa định danh hoặc điều kiện phân trang ổn định để tránh bỏ sót hay xử lý trùng hàng. Nếu nghiệp vụ yêu cầu toàn bộ batch phải nguyên tử, cần cân nhắc rõ trade-off trước khi thay đổi ranh giới commit.

### Chọn isolation level theo yêu cầu nghiệp vụ

`READ COMMITTED` thường tạo read view ngắn hơn `REPEATABLE READ`, do đó có thể giảm thời gian giữ một snapshot xuyên suốt transaction. Tuy nhiên, hai câu đọc trong cùng transaction có thể thấy hai trạng thái đã commit khác nhau. Chỉ đổi isolation level khi nghiệp vụ chấp nhận sự khác biệt này; đây không phải biện pháp thay thế cho việc đóng transaction đúng cách.

### Theo dõi purge sau khi xử lý nguyên nhân

Nếu history list đã tăng cao, trước tiên hãy tìm transaction giữ snapshot hoặc transaction ghi kéo dài. Tăng số purge thread hay thay đổi tham số liên quan purge không giải phóng được phiên bản mà một read view còn cần. Sau khi nguyên nhân giữ lịch sử được xử lý, mới đánh giá liệu năng lực purge có theo kịp tốc độ ghi hay không.

Không nên cố xóa undo file thủ công hoặc kết thúc transaction chỉ dựa trên một giá trị history list. InnoDB quản lý vòng đời undo; can thiệp sai có thể gây mất dữ liệu chưa commit hoặc ảnh hưởng hoạt động ứng dụng.

## 13. Các nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| Transaction ghi commit thì undo của nó bị xóa ngay. | Update undo có thể phải được giữ cho các read view cũ. Purge dọn khi lịch sử không còn cần thiết. |
| Chỉ transaction ghi mới ảnh hưởng đến undo history. | Transaction đọc giữ snapshot cũ có thể ngăn purge dọn undo do transaction khác tạo ra. |
| Một connection `Sleep` không ảnh hưởng MVCC. | Connection nhàn rỗi nhưng transaction còn mở có thể giữ read view và ghim lịch sử. |
| History list length là số transaction hoặc số hàng cũ. | Đây là độ dài history list tính theo trang undo log, không phải số hàng hay số transaction. |
| Purge xong thì undo tablespace lập tức nhỏ lại trên filesystem. | Không gian được giải phóng để tái sử dụng không đồng nghĩa tệp undo lập tức được thu nhỏ. |
| `SELECT ... FOR UPDATE` luôn đọc cùng snapshot với `SELECT` thường. | Locking read là current read, có thể thấy phiên bản hiện tại khác với consistent read. |
| Tăng purge thread sẽ xử lý được mọi history backlog. | Nếu read view còn cần phiên bản cũ, purge không được phép xóa chúng. Cần xử lý transaction giữ snapshot trước. |

## 14. Checklist điều tra history list tăng

1. Lấy `SHOW ENGINE INNODB STATUS` và ghi lại `History list length`.
2. Truy vấn `information_schema.innodb_trx` để tìm transaction mở lâu.
3. Xác định transaction nào đã thực hiện consistent read và có thể còn giữ read view.
4. Kiểm tra isolation level, thời điểm bắt đầu snapshot và trạng thái kết nối.
5. Đối chiếu với workload ghi/xóa để biết undo history được tạo nhanh đến mức nào.
6. Phối hợp với chủ sở hữu ứng dụng để kết thúc transaction bị bỏ quên hoặc điều chỉnh batch dài.
7. Theo dõi history list qua nhiều mẫu sau khi xử lý; xác nhận purge đang bắt kịp.
8. Chỉ điều chỉnh năng lực purge hoặc quản lý undo tablespace sau khi đã hiểu nguyên nhân và đo được giới hạn thực tế.

## 15. Tự kiểm tra

**Vì sao transaction A vẫn thấy giá trị 100 sau khi transaction B đã cập nhật thành 120 và commit?**

Vì consistent read của A dùng read view được tạo trước khi B commit. InnoDB dùng undo record để dựng phiên bản 100 phù hợp với ảnh chụp của A.

**Undo log có tác dụng gì sau khi transaction đã commit?**

Update undo có thể tiếp tục cần thiết để các read view cũ đọc phiên bản trước. Khi không còn read view nào cần lịch sử đó, purge mới có thể dọn.

**Vì sao một transaction chỉ đọc vẫn có thể làm history list tăng?**

Nếu transaction giữ read view cũ, purge phải bảo toàn các phiên bản mà ảnh chụp đó có thể cần. Các transaction khác vẫn tiếp tục tạo undo history khi cập nhật hoặc xóa dữ liệu.

**READ COMMITTED và REPEATABLE READ khác nhau thế nào về read view?**

READ COMMITTED thường tạo read view mới cho từng consistent read. REPEATABLE READ thường tái sử dụng read view của transaction sau lần consistent read đầu tiên.

**History list length bằng số hàng đã xóa chưa được purge phải không?**

Không. Đây là độ dài history list theo trang undo log; nó không phải số hàng, số phiên bản hay số transaction chính xác.

Khi phân tích MVCC, hãy nối ba phần thành một chuỗi: **read view quyết định phiên bản cần thấy, undo giúp dựng phiên bản đó, và purge chỉ loại bỏ lịch sử khi không còn read view nào cần đến nó**. Chuỗi này giải thích vì sao một transaction đọc mở lâu có thể làm dữ liệu lịch sử tồn tại lâu hơn nhiều so với thời gian chạy của câu SQL cuối cùng.
