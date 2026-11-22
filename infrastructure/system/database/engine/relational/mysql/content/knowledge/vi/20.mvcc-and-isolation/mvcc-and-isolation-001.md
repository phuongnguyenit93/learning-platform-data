# MVCC giải quyết đọc đồng thời với ghi như thế nào

Trong một hệ quản trị cơ sở dữ liệu, nhiều phiên có thể đọc và thay đổi cùng một hàng dữ liệu. Nếu mọi thao tác đọc đều phải chờ thao tác ghi kết thúc, hệ thống dễ bị nghẽn khi có nhiều truy vấn đồng thời. Nếu đọc trực tiếp dữ liệu đang bị thay đổi mà không có quy tắc nhất quán, truy vấn có thể nhìn thấy trạng thái chưa hoàn tất hoặc kết quả thay đổi giữa các lần đọc.

InnoDB của MySQL dùng **Multi-Version Concurrency Control (MVCC)** để giải quyết phần lớn xung đột giữa đọc thông thường và ghi. Thay vì buộc một truy vấn đọc phải khóa hàng đang được cập nhật, InnoDB có thể cung cấp cho truy vấn một phiên bản đã commit phù hợp với snapshot của nó. Ghi vẫn dùng khóa để bảo vệ thay đổi; MVCC chủ yếu giúp các consistent read không phải chặn người ghi và không đọc dữ liệu chưa commit.

## Mục tiêu

Sau bài học, bạn có thể:

- Giải thích vì sao đọc đồng thời với ghi cần cơ chế nhất quán.
- Mô tả vai trò của undo log, các phiên bản hàng và read view trong MVCC của InnoDB.
- Phân biệt consistent read với locking read (current read).
- Dự đoán kết quả đọc trong các transaction ở mức `READ COMMITTED` và `REPEATABLE READ`.
- Nhận biết giới hạn của MVCC, tác động của transaction kéo dài và trường hợp vẫn cần khóa.

Các ví dụ giả định bảng dùng InnoDB và cú pháp MySQL 8.0 trở lên.

## 1. Bài toán đọc đồng thời với ghi

Giả sử bảng `inventory` có một hàng:

| product_id | available |
|---:|---:|
| 10 | 8 |

Một phiên đang giảm số lượng còn hàng từ 8 xuống 6. Trong lúc transaction đó chưa commit, một phiên khác chạy báo cáo tồn kho. Hệ thống cần quyết định báo cáo sẽ nhìn thấy giá trị nào.

Có hai yêu cầu quan trọng:

- **Không đọc dữ liệu chưa commit:** phiên báo cáo không được nhìn thấy thay đổi mà transaction ghi có thể còn rollback.
- **Đọc nhất quán:** trong phạm vi snapshot của mình, truy vấn cần nhìn thấy một trạng thái dữ liệu xác định, thay vì lúc thì thấy giá trị cũ, lúc thì thấy một phần thay đổi mới.

Khóa độc quyền (exclusive lock) có thể bảo vệ hàng đang được ghi, nhưng nếu mọi truy vấn đọc đều phải chờ khóa này thì hoạt động đọc và ghi sẽ cản trở nhau. MVCC bổ sung một cách đọc khác: truy vấn đọc lấy phiên bản cũ phù hợp với snapshot trong khi transaction ghi tiếp tục cập nhật phiên bản hiện tại.

## 2. MVCC lưu và tìm phiên bản hàng như thế nào

### Phiên bản hiện tại và undo log

Khi transaction InnoDB cập nhật một hàng, engine ghi nhận thay đổi trong dữ liệu và lưu thông tin cần thiết để có thể dựng lại phiên bản trước đó trong undo log. Bản ghi trong clustered index có các trường hệ thống nội bộ, trong đó có transaction ID của lần thay đổi và con trỏ đến undo record. Có thể hình dung chuỗi phiên bản như sau:

```text
Phiên bản cũ hơn                         Phiên bản hiện tại
available = 8  <--- undo chain <---      available = 6
                                      trx_id = T2
```

Đây là mô hình khái niệm. Undo log không đơn giản là một bản sao đầy đủ của toàn bộ bảng; nó lưu thông tin cần thiết để hoàn tác thay đổi hoặc dựng lại phiên bản cũ khi consistent read cần đến.

Khi một truy vấn cần phiên bản cũ, InnoDB lần theo chuỗi undo để dựng lại giá trị phù hợp. Một truy vấn đọc thông thường vì vậy không cần yêu cầu transaction đang ghi nhả khóa hàng chỉ để xem giá trị trước khi cập nhật.

### Read view (snapshot đọc)

Read view mô tả tập phiên bản mà một consistent read được phép nhìn thấy. Khi tạo read view, InnoDB ghi nhận trạng thái transaction đang hoạt động cùng các mốc transaction ID. Khi xét một phiên bản, engine xác định transaction tạo ra phiên bản đó đã nằm ngoài snapshot, còn hoạt động tại thời điểm snapshot, hay bắt đầu sau snapshot.

Ở mức khái niệm:

- Phiên bản đã commit trước thời điểm snapshot và không thuộc một transaction còn hoạt động tại thời điểm đó có thể được nhìn thấy.
- Phiên bản do transaction còn hoạt động khi snapshot được tạo ra sẽ không được nhìn thấy, kể cả transaction đó commit sau này.
- Phiên bản do transaction bắt đầu sau snapshot tạo ra không thuộc snapshot và cũng không được nhìn thấy.
- Transaction luôn nhìn thấy các thay đổi mà chính nó đã thực hiện trước đó, theo quy tắc đọc của InnoDB.

Read view không phải bản sao vật lý của toàn bộ database. Nó là quy tắc xác định phiên bản nào hợp lệ; dữ liệu phiên bản cũ được dựng từ undo khi cần.

### Khi nào phiên bản cũ được dọn dẹp

Undo record còn cần thiết khi một read view đang mở có thể phải dùng đến nó. Tiến trình purge của InnoDB chỉ dọn những undo version không còn cần cho transaction nào. Vì vậy, một transaction đọc kéo dài có thể giữ snapshot cũ và làm chậm purge, khiến lượng undo history tích lũy tăng lên.

## 3. Consistent read: đọc snapshot mà không khóa hàng

Với InnoDB, một câu `SELECT` thông thường (không có `FOR UPDATE` hoặc `FOR SHARE`) là consistent nonlocking read ở các mức cô lập hỗ trợ snapshot. Nó đọc phiên bản phù hợp với read view và không đặt khóa hàng để ngăn transaction khác cập nhật hàng đó.

Ví dụ, trong khi phiên A đọc `available = 8`, phiên B có thể cập nhật hàng thành 6 và commit. Câu `SELECT` của A vẫn đọc phiên bản 8 nếu snapshot của A được tạo trước thay đổi của B. Phiên B không cần chờ câu đọc thông thường của A kết thúc.

Điều này tạo ra hai lợi ích:

- **Đọc không chặn ghi:** báo cáo hoặc truy vấn tra cứu thông thường có thể đọc phiên bản cũ trong lúc transaction khác cập nhật phiên bản hiện tại.
- **Ghi không làm thay đổi snapshot đang đọc:** một transaction không bất ngờ thấy giá trị của transaction khác xuất hiện giữa các consistent read thuộc cùng snapshot.

Consistent read vẫn lấy metadata lock cần thiết cho câu lệnh và vẫn chịu ảnh hưởng của các loại khóa hoặc thao tác khác. MVCC không có nghĩa là toàn bộ database không còn khóa.

## 4. Thời điểm tạo snapshot phụ thuộc mức cô lập

MVCC cung cấp các phiên bản để đọc; mức cô lập quyết định khi nào read view được tạo và tái sử dụng. Trong MySQL/InnoDB, hai mức thường gặp là `READ COMMITTED` và `REPEATABLE READ`.

| Mức cô lập | Snapshot của consistent read | Hệ quả chính |
|---|---|---|
| `READ UNCOMMITTED` | Không dùng snapshot consistent read theo cách của RC/RR; có thể đọc dữ liệu chưa commit | Có nguy cơ dirty read |
| `READ COMMITTED` | Mỗi consistent read tạo snapshot mới tại đầu câu lệnh | Có thể thấy commit mới giữa hai câu `SELECT` trong cùng transaction |
| `REPEATABLE READ` | Các consistent read trong transaction dùng cùng read view; thường được tạo ở consistent read đầu tiên | Đọc lặp lại cùng snapshot cho kết quả nhất quán |
| `SERIALIZABLE` | Khi tắt autocommit, các câu `SELECT` thông thường được chuyển thành locking read dùng shared lock | Tăng mức bảo vệ bằng khóa và có thể làm đọc/ghi chờ nhau |

`REPEATABLE READ` là mức mặc định của InnoDB trong MySQL. Nếu cần tạo snapshot ngay lúc bắt đầu transaction ở mức này, có thể dùng `START TRANSACTION WITH CONSISTENT SNAPSHOT`. Nếu chỉ dùng `START TRANSACTION`, read view của consistent read thường được tạo khi câu consistent read đầu tiên chạy. Tùy chọn `WITH CONSISTENT SNAPSHOT` chỉ có tác dụng tạo snapshot nhất quán ở `REPEATABLE READ`.

Có thể xem và thiết lập mức cô lập cho session trước khi mở transaction:

```sql
SELECT @@transaction_isolation;

SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ;
START TRANSACTION;
```

Không thay đổi mức cô lập giữa lúc transaction đang chạy để mong thay đổi snapshot hiện tại. Hãy thiết lập trước khi bắt đầu transaction tiếp theo.

## 5. Ví dụ hai phiên ở REPEATABLE READ

Giả sử `inventory(product_id, available)` dùng InnoDB và hiện có `product_id = 10`, `available = 8`.

**Phiên A**

```sql
SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ;
START TRANSACTION;

SELECT available
FROM inventory
WHERE product_id = 10;
-- Kết quả: 8. Consistent read đầu tiên tạo snapshot của A.
```

Trong lúc A vẫn mở transaction, phiên B thực hiện:

```sql
START TRANSACTION;

UPDATE inventory
SET available = available - 2
WHERE product_id = 10;

COMMIT;
-- Giá trị hiện tại đã commit là 6.
```

Quay lại phiên A:

```sql
SELECT available
FROM inventory
WHERE product_id = 10;
-- Vẫn là 8: consistent read dùng snapshot cũ của A.
```

Khi A cần đọc phiên bản hiện tại để quyết định cập nhật, A có thể yêu cầu locking read:

```sql
SELECT available
FROM inventory
WHERE product_id = 10
FOR UPDATE;
-- Đọc phiên bản hiện tại đã commit (6) và khóa hàng phù hợp.

COMMIT;
```

Ví dụ cho thấy cùng một transaction ở `REPEATABLE READ` có thể nhận hai kết quả khác nhau tùy loại đọc: `SELECT` thông thường đọc snapshot, còn `SELECT ... FOR UPDATE` đọc phiên bản hiện tại và đặt khóa. Hãy chọn loại đọc theo mục đích nghiệp vụ.

## 6. Consistent read và current read khác nhau

MVCC không khiến mọi câu lệnh đều đọc snapshot. Các thao tác cần quyết định hoặc thay đổi trạng thái hiện tại thường dùng current read và khóa.

| Thao tác InnoDB | Cách đọc điển hình | Khóa hàng |
|---|---|---|
| `SELECT` thông thường | Consistent read theo read view | Không khóa hàng chỉ để đọc |
| `SELECT ... FOR SHARE` | Current/locking read | Đặt shared lock trên các bản ghi hoặc phạm vi được đọc |
| `SELECT ... FOR UPDATE` | Current/locking read | Đặt exclusive lock phù hợp với bản ghi hoặc phạm vi được đọc |
| `UPDATE` | Đọc phiên bản hiện tại để xác định và thay đổi hàng | Đặt khóa ghi |
| `DELETE` | Đọc phiên bản hiện tại để xác định và xóa hàng | Đặt khóa ghi |

Với truy vấn phạm vi, InnoDB có thể khóa các index record và gap liên quan (next-key lock), tùy mức cô lập, chỉ mục và điều kiện truy vấn. Vì thế, không nên suy ra rằng locking read chỉ khóa đúng các hàng cuối cùng được trả về.

Ví dụ đọc số dư để kiểm tra trước khi trừ tiền:

```sql
START TRANSACTION;

SELECT balance
FROM accounts
WHERE account_id = 42
FOR UPDATE;

-- Ứng dụng kiểm tra số dư và thực hiện cập nhật phù hợp.
UPDATE accounts
SET balance = balance - 100
WHERE account_id = 42
  AND balance >= 100;

COMMIT;
```

`FOR UPDATE` giúp phiên đọc giữ khóa ghi trên hàng cho đến khi transaction kết thúc, nhờ đó transaction khác không thể đồng thời thay đổi hàng theo cách phá vỡ quyết định dựa trên số dư vừa đọc. Điều kiện kiểm tra ngay trong `UPDATE` vẫn hữu ích như một lớp bảo vệ bổ sung. Ứng dụng cần kiểm tra số hàng bị ảnh hưởng để biết thao tác có thực sự trừ tiền hay không.

Nếu chỉ cần phép biến đổi nguyên tử đơn giản, một câu lệnh có điều kiện thường gọn hơn việc đọc rồi tính ở ứng dụng:

```sql
UPDATE accounts
SET balance = balance - 100
WHERE account_id = 42
  AND balance >= 100;
```

Sau đó kiểm tra số hàng thay đổi. Nếu không có hàng nào được cập nhật, tài khoản không tồn tại hoặc điều kiện số dư không thỏa mãn; ứng dụng có thể phân biệt hai trường hợp bằng truy vấn phù hợp trong transaction.

## 7. MVCC không thay thế mọi loại khóa

MVCC tối ưu cho consistent read. Những thao tác cần đảm bảo quyền ghi hoặc phối hợp nhiều transaction vẫn cần locking:

- Hai transaction cùng cập nhật một hàng phải được tuần tự hóa bằng khóa ghi.
- `SELECT ... FOR UPDATE` phù hợp khi ứng dụng đọc một hàng rồi đưa ra quyết định ghi dựa trên giá trị hiện tại.
- `SELECT ... FOR SHARE` phù hợp khi cần đọc và giữ shared lock để bảo vệ dữ liệu khỏi bị thay đổi trong phần còn lại của transaction.
- Kiểm tra khóa duy nhất và khóa ngoại có thể sử dụng khóa nội bộ để bảo vệ ràng buộc.
- DDL và metadata lock có thể khiến truy vấn phải chờ, dù consistent read không khóa hàng dữ liệu.

Ở `REPEATABLE READ`, consistent read thông thường có thể không nhìn thấy hàng được transaction khác chèn sau thời điểm snapshot. Nhưng locking read và các câu lệnh DML cần bảo vệ phạm vi hiện tại bằng cơ chế khóa phù hợp. Với truy vấn phạm vi, next-key lock giúp ngăn một số kiểu chèn phantom trong phạm vi bị khóa. Không nên đồng nhất hành vi snapshot của plain `SELECT` với hành vi khóa của `SELECT ... FOR UPDATE`.

## 8. Chi phí vận hành và transaction kéo dài

MVCC giảm chờ giữa đọc và ghi, nhưng phải giữ đủ thông tin lịch sử để phục vụ snapshot còn hiệu lực. Một transaction mở lâu, kể cả chỉ chạy `SELECT` rồi để kết nối ở trạng thái idle, có thể giữ read view cũ. Khi đó purge chưa thể xóa một số undo version.

Hệ quả có thể gồm:

- Undo history và history list length tăng.
- Purge không theo kịp lượng thay đổi, làm tăng công việc nền.
- Tablespace chứa undo cần thêm dung lượng.
- Các truy vấn phải đi qua chuỗi phiên bản dài hơn để dựng lại giá trị cũ.

Một số cách giảm tác động:

1. Giữ transaction ngắn và commit hoặc rollback ngay sau khi hoàn tất công việc.
2. Không mở transaction trước khi chờ người dùng thao tác hoặc chờ dịch vụ bên ngoài.
3. Với báo cáo lớn, cân nhắc chia thành các phạm vi hoặc thời điểm chạy phù hợp với yêu cầu nhất quán.
4. Theo dõi transaction đang mở và trạng thái InnoDB khi history list length tăng bất thường.

Có thể xem các transaction InnoDB đang hoạt động bằng:

```sql
SELECT trx_id,
       trx_state,
       trx_started,
       trx_mysql_thread_id,
       trx_query
FROM information_schema.innodb_trx
ORDER BY trx_started;
```

Để xem thêm trạng thái engine và thông tin undo/purge, dùng:

```sql
SHOW ENGINE INNODB STATUS;
```

Không nên kết luận chỉ từ một chỉ số đơn lẻ. Hãy đối chiếu thời gian transaction mở, tải ghi, tốc độ purge và xu hướng dung lượng undo.

## 9. Những hiểu nhầm thường gặp

| Hiểu nhầm | Thực tế |
|---|---|
| MVCC nghĩa là InnoDB không dùng khóa | Ghi, locking read, kiểm tra ràng buộc và nhiều thao tác khác vẫn cần khóa |
| Mọi `SELECT` đều thấy dữ liệu mới nhất | Consistent read có thể đọc snapshot cũ; locking read đọc phiên bản hiện tại |
| `REPEATABLE READ` luôn tạo snapshot ngay khi `START TRANSACTION` | Thông thường read view được tạo ở consistent read đầu tiên; có thể dùng `WITH CONSISTENT SNAPSHOT` để tạo ngay |
| Transaction khác commit thì snapshot cũ tự đổi | Read view của `REPEATABLE READ` vẫn giữ nguyên trong transaction |
| Undo log chỉ phục vụ rollback | Undo còn giúp dựng lại phiên bản cũ cho consistent read |
| Transaction chỉ đọc không ảnh hưởng purge | Read view cũ của transaction đọc kéo dài có thể giữ undo history cần thiết |
| `SELECT ... FOR UPDATE` giống `SELECT` thường nhưng nhanh hơn | Đây là locking/current read, có thể chờ và giữ khóa đến cuối transaction |

## 10. Bài thực hành

Giả sử bảng `inventory(product_id, available)` và `accounts(account_id, balance)` đều dùng InnoDB.

1. Mô phỏng hai phiên: A bắt đầu transaction ở `REPEATABLE READ` và đọc tồn kho; B giảm tồn kho rồi commit. Dự đoán kết quả của lần `SELECT` thông thường tiếp theo ở A.
2. Trong transaction A ở câu 1, chạy thêm `SELECT ... FOR UPDATE`. Giải thích vì sao kết quả có thể khác với consistent read trước đó.
3. Lặp lại tình huống ở `READ COMMITTED`. So sánh kết quả hai câu `SELECT` thông thường trong cùng transaction.
4. Giải thích vì sao transaction chỉ đọc nhưng mở lâu vẫn có thể làm undo history tăng.
5. Viết một câu `UPDATE` có điều kiện để trừ 100 khỏi tài khoản khi số dư đủ, sau đó nêu cách xác nhận cập nhật thành công.
6. Mở hai transaction cùng cập nhật một hàng và quan sát transaction nào phải chờ khóa. So sánh hành vi đó với một `SELECT` thông thường.

## Ghi nhớ

- MVCC của InnoDB dùng read view và undo version để cung cấp dữ liệu nhất quán cho consistent read.
- Consistent read thông thường đọc snapshot và không khóa hàng; thao tác ghi vẫn dùng khóa để bảo vệ thay đổi.
- `READ COMMITTED` tạo snapshot mới cho mỗi consistent read; `REPEATABLE READ` tái sử dụng read view trong transaction.
- `SELECT ... FOR UPDATE`, `SELECT ... FOR SHARE`, `UPDATE` và `DELETE` cần đọc trạng thái hiện tại và có thể đặt khóa.
- MVCC giảm xung đột đọc/ghi nhưng không loại bỏ khóa; transaction kéo dài có thể cản purge và làm undo history tích lũy.
