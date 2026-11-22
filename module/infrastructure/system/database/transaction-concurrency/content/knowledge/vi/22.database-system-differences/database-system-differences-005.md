# MySQL InnoDB: consistent read và locking read

## Hai cách đọc dữ liệu trong InnoDB

InnoDB hỗ trợ nhiều transaction cùng truy cập một bảng bằng cách kết hợp MVCC (multi-version concurrency control) với khóa. Khi đọc dữ liệu, ứng dụng cần phân biệt hai cơ chế:

- **Consistent read** là lần đọc không khóa, thường được thực hiện bằng câu `SELECT` thông thường. InnoDB dùng read view để xác định phiên bản dữ liệu mà transaction được phép nhìn thấy. Các lần đọc này thường không phải chờ transaction khác đang giữ khóa ghi trên bản ghi.
- **Locking read** là lần đọc có khóa, được yêu cầu bằng `SELECT ... FOR UPDATE` hoặc `SELECT ... FOR SHARE`. InnoDB đọc phiên bản hiện hành phù hợp và đặt khóa trên các bản ghi hoặc khoảng chỉ mục mà câu truy vấn truy cập.

Hai câu lệnh `SELECT` có thể cùng truy vấn một dòng nhưng nhìn thấy phiên bản khác nhau, vì chúng phục vụ mục đích khác nhau. Consistent read giúp transaction đọc một snapshot ổn định; locking read giúp transaction phối hợp với các transaction đang sửa dữ liệu và bảo vệ một quyết định đọc rồi ghi.

Sự khác biệt này đặc biệt quan trọng khi dùng MySQL InnoDB với mức cô lập mặc định `REPEATABLE READ`. Nếu trộn consistent read và locking read trong cùng transaction, ứng dụng có thể nhìn thấy hai phiên bản khác nhau của cùng một dòng. Điều đó là hành vi có chủ đích của InnoDB, không phải lỗi đọc dữ liệu.

## Consistent read và MVCC

### Read view và phiên bản hàng

Khi một transaction cập nhật một dòng, InnoDB lưu thông tin cần thiết trong undo log để có thể khôi phục phiên bản cũ. Nhờ đó, một transaction đọc có thể dựng lại phiên bản phù hợp với snapshot của nó mà không cần chặn transaction đang ghi.

Ví dụ, bảng `accounts` có một dòng:

| id | balance |
| --- | ---: |
| 10 | 1000000 |

Transaction A bắt đầu đọc ở thời điểm số dư là `1000000`. Transaction B sau đó cập nhật số dư thành `900000` và commit. Nếu A vẫn đang dùng snapshot cũ, câu `SELECT` thông thường của A có thể tiếp tục trả về `1000000`. InnoDB lấy phiên bản cũ từ chuỗi undo version để đáp ứng snapshot đó.

Một consistent read không đặt shared row lock lên dòng được đọc. Vì vậy, transaction B có thể cập nhật và commit trong khi A đang đọc snapshot. Đây là cách MVCC cho phép reader và writer tiến triển đồng thời.

### Khi nào snapshot được tạo?

Thời điểm tạo read view phụ thuộc mức cô lập:

- Với `REPEATABLE READ`, read view của transaction thường được tạo ở lần consistent read đầu tiên. Các consistent read tiếp theo trong transaction sử dụng cùng read view.
- Với `READ COMMITTED`, mỗi consistent read tạo một read view mới tại đầu câu lệnh. Hai câu `SELECT` trong cùng transaction có thể thấy hai trạng thái đã commit khác nhau.

Chỉ gọi `START TRANSACTION` chưa nhất thiết tạo snapshot ngay trong trường hợp thông thường. Nếu cần tạo snapshot ngay khi bắt đầu transaction ở mức `REPEATABLE READ`, MySQL hỗ trợ `START TRANSACTION WITH CONSISTENT SNAPSHOT`.

Ví dụ:

```sql
SET TRANSACTION ISOLATION LEVEL REPEATABLE READ;
START TRANSACTION;

-- Lần consistent read đầu tiên tạo read view.
SELECT balance
FROM accounts
WHERE id = 10;

-- Các consistent read sau vẫn dùng read view của transaction.
SELECT balance
FROM accounts
WHERE id = 10;

COMMIT;
```

Trong ví dụ này, nếu transaction khác cập nhật và commit số dư sau lần `SELECT` đầu tiên, câu `SELECT` thứ hai của transaction hiện tại vẫn đọc phiên bản theo snapshot cũ.

### Hành vi theo mức cô lập

| Isolation level | Consistent read thông thường trong InnoDB |
| --- | --- |
| `READ UNCOMMITTED` | Có thể đọc phiên bản chưa commit; không cung cấp snapshot nhất quán như các mức cao hơn. |
| `READ COMMITTED` | Mỗi câu `SELECT` tạo snapshot mới, chỉ thấy dữ liệu đã commit trước thời điểm bắt đầu câu lệnh. |
| `REPEATABLE READ` | Các consistent read trong một transaction dùng chung snapshot được tạo ở lần đọc nhất quán đầu tiên. Đây là mức mặc định của InnoDB. |
| `SERIALIZABLE` | Áp dụng ngữ nghĩa cô lập nghiêm ngặt hơn và có thể chuyển plain `SELECT` thành shared locking read trong transaction tường minh khi autocommit tắt. Cần xem xét cả chế độ transaction và câu lệnh thực tế. |

`START TRANSACTION WITH CONSISTENT SNAPSHOT` có ý nghĩa tạo snapshot ngay ở mức `REPEATABLE READ`; ở mức cô lập khác, tùy chọn này không tạo ra cùng bảo đảm snapshot lặp lại. Hãy đặt isolation level trước khi bắt đầu transaction nếu muốn kiểm soát hành vi của transaction đó.

## Locking read: đọc dữ liệu hiện hành và đặt khóa

Consistent read trả lời câu hỏi “snapshot của transaction cho thấy gì?”. Locking read trả lời câu hỏi “phiên bản hiện hành nào đang tồn tại và tôi cần khóa gì để phối hợp với các transaction khác?”.

InnoDB cung cấp hai dạng locking read phổ biến:

```sql
-- Đọc và đặt khóa độc quyền trên các bản ghi được truy cập.
SELECT balance
FROM accounts
WHERE id = 10
FOR UPDATE;

-- Đọc và đặt khóa chia sẻ trên các bản ghi được truy cập.
SELECT balance
FROM accounts
WHERE id = 10
FOR SHARE;
```

`FOR UPDATE` thường dùng trước khi transaction sửa các dòng vừa đọc. Khóa độc quyền ngăn transaction khác lấy khóa xung đột để sửa hoặc khóa dòng đó cho tới khi transaction hiện tại kết thúc.

`FOR SHARE` cho phép nhiều transaction cùng giữ khóa chia sẻ trên một dòng, nhưng ngăn transaction khác lấy khóa độc quyền để sửa dòng đó cho tới khi các khóa chia sẻ được giải phóng. Cú pháp `FOR SHARE` có trong MySQL 8.0; các phiên bản cũ hơn thường dùng `LOCK IN SHARE MODE`.

Locking read là current read: nó đọc dữ liệu hiện hành phù hợp thay vì buộc phải dùng read view cũ của consistent read. Nếu dòng đã được transaction khác cập nhật và commit sau khi snapshot của transaction hiện tại được tạo, `SELECT ... FOR UPDATE` có thể trả về giá trị mới nhất đã commit.

Nếu dòng đang bị transaction khác giữ khóa xung đột, locking read thường phải chờ. Sau khi transaction kia commit, InnoDB tiếp tục đọc phiên bản hiện hành và đặt khóa theo yêu cầu; nếu transaction kia rollback, nó xử lý theo trạng thái còn lại. Có thể thay hành vi chờ bằng `NOWAIT` hoặc `SKIP LOCKED` trong các trường hợp phù hợp.

### Khóa được giữ trong bao lâu?

Trong transaction tường minh, khóa do locking read tạo ra thường được giữ tới `COMMIT` hoặc `ROLLBACK`. Vì vậy, hãy giữ transaction ngắn và chỉ làm phần công việc cần bảo vệ bên trong nó.

Nếu bật `autocommit=1` và chạy một câu `SELECT ... FOR UPDATE` độc lập, transaction của câu lệnh kết thúc ngay sau câu lệnh; khóa được giải phóng khi transaction kết thúc. Muốn khóa dòng để đọc rồi cập nhật ở câu lệnh tiếp theo, cần đặt cả hai trong cùng transaction:

```sql
START TRANSACTION;

SELECT balance
FROM accounts
WHERE id = 10
FOR UPDATE;

UPDATE accounts
SET balance = balance - 100000
WHERE id = 10;

COMMIT;
```

Nếu ứng dụng dùng connection pool, cần bảo đảm transaction thực sự còn mở trên cùng connection giữa câu locking read và câu ghi. Không được trả connection về pool hoặc kết thúc transaction ở giữa quy trình.

## Consistent read và locking read có thể nhìn thấy hai phiên bản khác nhau

Đây là điểm dễ gây nhầm nhất khi dùng `REPEATABLE READ`. Xét hai session cùng truy cập `accounts`:

**Session A**

```sql
SET TRANSACTION ISOLATION LEVEL REPEATABLE READ;
START TRANSACTION;

-- Tạo snapshot và đọc balance = 100.
SELECT balance FROM accounts WHERE id = 10;
```

**Session B**

```sql
START TRANSACTION;

UPDATE accounts
SET balance = 150
WHERE id = 10;

COMMIT;
```

**Session A tiếp tục**

```sql
-- Consistent read: vẫn đọc snapshot cũ, balance = 100.
SELECT balance FROM accounts WHERE id = 10;

-- Locking read: đọc phiên bản hiện hành đã commit, balance = 150.
SELECT balance FROM accounts WHERE id = 10 FOR UPDATE;

COMMIT;
```

Trong cùng transaction A, hai câu `SELECT` có thể lần lượt trả về `100` và `150`. Plain `SELECT` tiếp tục dùng read view cũ; `SELECT ... FOR UPDATE` đọc phiên bản hiện hành và đặt khóa. Đây là lý do không nên trộn hai kiểu đọc một cách tùy tiện khi xây dựng logic nghiệp vụ.

Sau khi locking read đã thấy `150`, một plain `SELECT` tiếp theo trong transaction A vẫn có thể trả về `100` ở mức `REPEATABLE READ`, vì nó vẫn dùng read view cũ. Việc đã thực hiện current read không làm mới snapshot consistent read.

Ở mức `READ COMMITTED`, plain `SELECT` thứ hai sau khi B commit sẽ tạo snapshot mới và thấy `150`. Dù vậy, locking read vẫn cần thiết nếu ứng dụng phải bảo vệ dòng trước các cập nhật cạnh tranh tiếp theo.

## Dùng locking read cho quy trình đọc rồi ghi

### Ví dụ kiểm tra tồn kho

Giả sử ứng dụng cần kiểm tra còn đủ hàng trước khi trừ tồn kho. Nếu hai request cùng đọc số lượng `5` bằng plain `SELECT`, cả hai có thể cùng kết luận đủ hàng cho đơn cần `4` sản phẩm. Nếu sau đó chúng ghi dựa trên giá trị đã đọc ở tầng ứng dụng, kết quả có thể sai.

Một cách dùng locking read:

```sql
START TRANSACTION;

SELECT quantity
FROM inventory
WHERE product_id = 42
FOR UPDATE;

-- Ứng dụng kiểm tra quantity >= số lượng cần mua.

UPDATE inventory
SET quantity = quantity - 4
WHERE product_id = 42;

COMMIT;
```

`FOR UPDATE` khóa dòng tồn kho trong khi ứng dụng kiểm tra và cập nhật. Request cạnh tranh muốn lấy khóa xung đột phải chờ. Sau khi transaction đầu tiên commit, request tiếp theo đọc giá trị hiện hành đã giảm và có thể từ chối nếu không còn đủ hàng.

Phải xử lý nhánh không đủ hàng bằng cách kết thúc transaction mà không cập nhật. Trong ứng dụng, cần rollback hoặc commit transaction chỉ đọc tùy cách triển khai; điều quan trọng là không giữ khóa lâu sau khi đã biết không thể đặt hàng.

### Cập nhật có điều kiện có thể đơn giản hơn

Không phải mọi thao tác đọc rồi ghi đều cần một câu `SELECT ... FOR UPDATE`. Nếu quy tắc nghiệp vụ có thể biểu diễn thành một câu `UPDATE` nguyên tử, hãy cân nhắc để database thực hiện phép kiểm tra và cập nhật cùng lúc:

```sql
UPDATE inventory
SET quantity = quantity - 4
WHERE product_id = 42
  AND quantity >= 4;
```

Sau đó kiểm tra số dòng bị ảnh hưởng:

- Một dòng được cập nhật: thao tác giữ chỗ hàng thành công.
- Không có dòng được cập nhật: sản phẩm không tồn tại hoặc không đủ hàng; ứng dụng xác định nhánh phù hợp bằng truy vấn bổ sung nếu cần.

Câu lệnh này dùng điều kiện trên giá trị trong database và thay đổi nó trong một thao tác có khóa. Nó tránh khoảng thời gian giữa việc đọc số lượng ở ứng dụng và ghi lại giá trị đã tính từ dữ liệu cũ.

Với chuyển tiền, có thể dùng cập nhật có điều kiện để bảo đảm tài khoản nguồn đủ số dư, đồng thời cập nhật hai tài khoản trong cùng transaction:

```sql
START TRANSACTION;

UPDATE accounts
SET balance = balance - 500000
WHERE id = 10
  AND balance >= 500000;

-- Ứng dụng phải kiểm tra ROW_COUNT() = 1 trước khi cộng tài khoản đích.
UPDATE accounts
SET balance = balance + 500000
WHERE id = 20;

COMMIT;
```

Nếu câu cập nhật tài khoản nguồn không tác động đúng một dòng, ứng dụng phải rollback thay vì tiếp tục cộng tiền. Trong hệ thống thực tế cũng cần kiểm tra tài khoản đích tồn tại, số tiền hợp lệ và các ràng buộc nghiệp vụ khác.

### Khi nào chọn locking read, atomic UPDATE hay optimistic locking?

| Cách tiếp cận | Phù hợp khi | Điểm cần cân nhắc |
| --- | --- | --- |
| `SELECT ... FOR UPDATE` | Cần đọc nhiều thuộc tính hoặc kiểm tra nhiều điều kiện rồi mới quyết định cập nhật. | Giữ khóa trong thời gian xử lý; transaction phải ngắn. |
| `UPDATE ... WHERE điều_kiện` | Quy tắc có thể biểu diễn trong một câu cập nhật có điều kiện. | Kiểm tra số dòng ảnh hưởng và xử lý trường hợp không thỏa điều kiện. |
| Optimistic locking với cột `version` | Xung đột hiếm và ứng dụng có thể thử lại khi phát hiện dữ liệu đã đổi. | Phải kiểm tra số dòng cập nhật; cần xử lý conflict ở tầng nghiệp vụ. |

Ví dụ optimistic locking:

```sql
UPDATE inventory
SET quantity = quantity - 4,
    version = version + 1
WHERE product_id = 42
  AND version = :version_read
  AND quantity >= 4;
```

Nếu số dòng bị ảnh hưởng bằng `0`, phiên bản đã thay đổi hoặc số lượng không đủ. Ứng dụng có thể đọc lại và thử lại theo quy tắc nghiệp vụ. Cách này không giữ khóa trong suốt thời gian ứng dụng xử lý dữ liệu đã đọc, nhưng vẫn dùng cơ chế cập nhật có điều kiện để phát hiện cạnh tranh.

## Record lock, gap lock và next-key lock

Locking read trong InnoDB không đơn giản là khóa một “dòng” trừu tượng. InnoDB đặt khóa trên các bản ghi chỉ mục mà execution plan truy cập. Với truy vấn dùng secondary index, việc khóa còn có thể liên quan tới bản ghi tương ứng trong clustered index.

Ba khái niệm thường gặp:

- **Record lock:** khóa một bản ghi chỉ mục cụ thể.
- **Gap lock:** khóa khoảng trống giữa các bản ghi chỉ mục, ngăn transaction khác chèn khóa chỉ mục mới vào khoảng đó.
- **Next-key lock:** kết hợp record lock với gap lock đứng trước bản ghi chỉ mục; đây là cơ chế thường dùng để bảo vệ các khoảng trong range scan.

### Khóa theo điều kiện tìm kiếm

Giả sử có chỉ mục duy nhất trên `id`:

```sql
SELECT *
FROM orders
WHERE id = 100
FOR UPDATE;
```

Khi truy vấn tìm thấy đúng một bản ghi bằng phép so sánh đầy đủ trên unique index, InnoDB thường chỉ cần record lock cho bản ghi đó, không cần khóa khoảng trước nó. Điều này giúp giảm phạm vi khóa.

Truy vấn theo khoảng:

```sql
SELECT *
FROM orders
WHERE created_at >= '2026-01-01'
  AND created_at < '2026-02-01'
FOR UPDATE;
```

Nếu chạy ở `REPEATABLE READ`, InnoDB có thể dùng next-key lock trên các khoảng chỉ mục được quét để ngăn transaction khác chèn các giá trị mới vào khoảng đang được bảo vệ. Điều này giúp locking read và thao tác ghi tránh một số phantom trong phạm vi truy vấn.

Phạm vi khóa thực tế phụ thuộc chỉ mục được chọn, điều kiện truy vấn, số dòng khớp và isolation level. Một truy vấn không có chỉ mục phù hợp có thể quét và khóa nhiều bản ghi hơn dự kiến. Vì vậy, cần xem execution plan và thiết kế index cho các truy vấn khóa.

### Ảnh hưởng của READ COMMITTED

Ở `READ COMMITTED`, InnoDB thường tắt gap locking cho các tìm kiếm và range scan, ngoại trừ các trường hợp cần thiết như kiểm tra foreign key và duplicate key. Vì vậy, các câu lệnh có thể gặp phantom rows mà `REPEATABLE READ` ngăn bằng next-key lock trong những trường hợp tương ứng.

Điều này không có nghĩa `READ COMMITTED` bỏ mọi khóa. Record lock vẫn được dùng để bảo vệ bản ghi đang được cập nhật hoặc khóa bằng `FOR UPDATE`/`FOR SHARE`. Các quy tắc cụ thể còn phụ thuộc loại câu lệnh và index.

## Locking read trong các truy vấn hàng đợi

Một ứng dụng worker có thể cần lấy một nhóm job đang chờ mà không để các worker khác cùng lấy những job đó. MySQL 8.0 hỗ trợ `SKIP LOCKED`:

```sql
START TRANSACTION;

SELECT id
FROM jobs
WHERE status = 'READY'
ORDER BY id
LIMIT 10
FOR UPDATE SKIP LOCKED;

-- Ứng dụng cập nhật các ID vừa nhận thành RUNNING.
UPDATE jobs
SET status = 'RUNNING'
WHERE id IN (101, 102, 103);

COMMIT;
```

Trong ví dụ, các ID trong `UPDATE` là danh sách thực tế trả về từ câu `SELECT`; danh sách minh họa không được hard-code trong ứng dụng. `FOR UPDATE` khóa các job được chọn. `SKIP LOCKED` khiến worker bỏ qua các dòng đang bị transaction khác khóa và chọn dòng khác nếu có.

`SKIP LOCKED` phù hợp với hàng đợi vì worker không cần chờ một job đang được worker khác xử lý. Tuy nhiên, kết quả là một view không nhất quán của tập dữ liệu: các dòng bị khóa bị bỏ qua, nên không dùng cú pháp này cho truy vấn báo cáo hoặc nghiệp vụ cần đọc đầy đủ tập kết quả.

`NOWAIT` là lựa chọn khác:

```sql
SELECT id, status
FROM jobs
WHERE id = 101
FOR UPDATE NOWAIT;
```

Nếu dòng bị khóa, câu lệnh trả lỗi ngay thay vì chờ. Ứng dụng có thể trả thông báo bận hoặc thử lại sau. Cả `NOWAIT` và `SKIP LOCKED` đều là tùy chọn của locking read trong các phiên bản MySQL hỗ trợ chúng; hãy xác nhận phiên bản MySQL đang chạy trước khi sử dụng.

## Deadlock và lock wait khi dùng locking read

Khóa giúp phối hợp ghi đồng thời nhưng cũng có thể tạo deadlock. Ví dụ:

```text
Transaction A                     Transaction B
--------------                     --------------
Khóa dòng account 10               
                                   Khóa dòng account 20
Chờ khóa dòng account 20           
                                   Chờ khóa dòng account 10
```

Mỗi transaction giữ một khóa mà transaction kia cần, tạo thành chu trình chờ. InnoDB phát hiện deadlock và chọn một transaction làm nạn nhân để rollback. Ứng dụng cần bắt lỗi deadlock và có thể thử lại toàn bộ transaction với backoff phù hợp.

Một số cách giảm nguy cơ:

1. Truy cập nhiều dòng theo cùng một thứ tự ở mọi luồng xử lý, ví dụ luôn khóa account có ID nhỏ trước.
2. Giữ transaction ngắn; không gọi HTTP, gửi email hoặc chờ người dùng trong lúc đang giữ khóa.
3. Tạo index phù hợp để câu locking read quét ít bản ghi.
4. Chỉ khóa những dòng cần thiết và chọn đúng mức cô lập cho nghiệp vụ.
5. Xử lý deadlock và lock wait như tình huống bình thường trong hệ thống đồng thời, thay vì giả định chúng không xảy ra.

Deadlock và lock wait timeout là hai loại lỗi khác nhau. Deadlock khiến InnoDB rollback transaction được chọn làm nạn nhân. Lock wait timeout xảy ra khi chờ khóa vượt quá giới hạn; mặc định, InnoDB thường rollback câu lệnh bị timeout chứ không nhất thiết rollback toàn transaction, trừ khi cấu hình `innodb_rollback_on_timeout` thay đổi hành vi. Ứng dụng cần xác định transaction còn ở trạng thái nào và chủ động rollback hoặc retry theo chính sách.

## Những nhầm lẫn thường gặp

| Nhầm lẫn | Hành vi thực tế |
| --- | --- |
| `START TRANSACTION` luôn tạo snapshot ngay lập tức. | Với consistent read thông thường ở `REPEATABLE READ`, read view thường được tạo ở lần consistent read đầu tiên; có thể yêu cầu tạo sớm bằng `WITH CONSISTENT SNAPSHOT`. |
| Plain `SELECT` luôn đọc dữ liệu mới nhất đã commit. | Ở `REPEATABLE READ`, nó đọc phiên bản theo snapshot của transaction. |
| `SELECT ... FOR UPDATE` cũng dùng snapshot cũ. | Đây là current read và đọc dữ liệu hiện hành phù hợp, đồng thời đặt khóa. |
| `SELECT ... FOR UPDATE` khóa mọi reader khác. | Nó chặn các thao tác lấy khóa xung đột; plain consistent read thường vẫn đọc phiên bản snapshot bằng MVCC. |
| `FOR SHARE` cho phép transaction khác cập nhật ngay. | Shared lock xung đột với exclusive lock cần cho thao tác cập nhật. |
| Một câu locking read độc lập giữ khóa sau khi kết thúc. | Với autocommit, transaction kết thúc sau câu lệnh và khóa được giải phóng. |
| `SKIP LOCKED` trả về đầy đủ các dòng phù hợp. | Nó bỏ qua các dòng đang bị khóa, nên kết quả không phải một view đầy đủ nhất quán. |
| Chỉ cần có `FOR UPDATE` là khóa đúng phạm vi. | Index và execution plan quyết định các bản ghi chỉ mục được quét và khóa; truy vấn rộng có thể khóa nhiều hơn dự kiến. |
| Transaction rollback có thể hoàn tác mọi thay đổi do transaction đã gọi. | Rollback chỉ hoàn tác tài nguyên thuộc transaction; nó không thu hồi HTTP request, email hay thao tác filesystem bên ngoài. |

## Quy trình chọn kiểu đọc

Trước khi viết truy vấn, hãy xác định mục tiêu:

1. Nếu chỉ cần đọc dữ liệu để hiển thị hoặc tính toán theo snapshot, dùng plain `SELECT` và hiểu rõ snapshot của isolation level.
2. Nếu cần đọc rồi quyết định sửa đúng các dòng đó, cân nhắc `SELECT ... FOR UPDATE` trong transaction ngắn.
3. Nếu chỉ cần thay đổi theo một điều kiện có thể diễn đạt bằng SQL, ưu tiên `UPDATE ... WHERE ...` có điều kiện và kiểm tra số dòng ảnh hưởng.
4. Nếu xung đột hiếm và có thể phát hiện thay đổi, cân nhắc optimistic locking với cột version.
5. Nếu xử lý hàng đợi nhiều worker, cân nhắc `FOR UPDATE SKIP LOCKED` và một cơ chế lease/khôi phục job bị kẹt.
6. Nếu truy vấn khóa theo khoảng, xem xét index và next-key lock để hiểu tác động tới transaction khác.

Hãy giữ các thao tác cần cùng nhất quán trong cùng transaction, kiểm tra isolation level thực tế của connection và không để transaction giữ khóa lâu hơn cần thiết.

## Bài tập vận dụng

Giả sử bảng `inventory` có `product_id` là khóa chính, `quantity` là số lượng còn lại và `version` là số phiên bản. Hai request đồng thời muốn mua 4 sản phẩm, trong khi tồn kho hiện tại là 5.

1. Nếu cả hai request dùng plain `SELECT quantity` ở mức `REPEATABLE READ`, vì sao cả hai có thể cùng đọc số lượng 5?
2. Nếu mỗi request dùng `SELECT quantity ... FOR UPDATE`, transaction thứ hai sẽ quan sát dữ liệu ở thời điểm nào sau khi transaction thứ nhất commit?
3. Viết một câu `UPDATE` có điều kiện để chỉ trừ tồn kho khi `quantity >= 4`, và giải thích cách dùng số dòng ảnh hưởng.
4. Viết một câu `UPDATE` dùng `version` để phát hiện request khác đã cập nhật trước.
5. Nếu worker lấy job bằng `FOR UPDATE SKIP LOCKED`, vì sao kết quả không thích hợp cho màn hình báo cáo cần đếm toàn bộ job `READY`?

Một cách giải quyết có thể dùng `UPDATE inventory SET quantity = quantity - 4 WHERE product_id = ? AND quantity >= 4` rồi kiểm tra chỉ một dòng được cập nhật. Nếu cần đọc thêm nhiều dữ liệu và giữ dòng trong lúc quyết định, dùng `SELECT ... FOR UPDATE` trong cùng transaction. Nếu dùng optimistic locking, thêm điều kiện `version = :expectedVersion` và tăng version trong câu cập nhật. Mỗi cách đều phải xử lý trường hợp cạnh tranh theo kết quả thực tế từ database.
