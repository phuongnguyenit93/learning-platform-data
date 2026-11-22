# MVCC và mức cô lập

## Khác biệt giữa SELECT thường và UPDATE/DELETE trong cùng giao dịch

Trong InnoDB, một câu `SELECT` thông thường và một câu `UPDATE` hoặc `DELETE` có thể nhìn thấy những phiên bản dữ liệu khác nhau dù chạy trong cùng một transaction. `SELECT` không khóa thường là *consistent read*: nó đọc một ảnh chụp dữ liệu theo cơ chế MVCC. `UPDATE` và `DELETE` là các thao tác đọc có khóa (*current/locking read*): chúng cần xét phiên bản hiện hành của hàng để quyết định hàng nào được sửa hoặc xóa và để giữ khóa phù hợp.

Khác biệt này đặc biệt quan trọng ở mức cô lập mặc định `REPEATABLE READ`. Một transaction có thể đọc đi đọc lại cùng một kết quả bằng `SELECT`, rồi ngay sau đó cập nhật hoặc xóa thêm hàng mà ảnh chụp ban đầu chưa hiển thị. Hiểu đúng hai cách đọc giúp tránh giả định sai về số hàng bị tác động, tránh ghi đè dữ liệu ngoài dự kiến và thiết kế transaction an toàn khi nhiều phiên cùng làm việc.

### 1. Hai cách đọc dữ liệu trong InnoDB

InnoDB dùng MVCC (Multi-Version Concurrency Control) để duy trì các phiên bản hàng. Thông tin undo giúp dựng lại phiên bản cũ phù hợp với ảnh chụp mà transaction đang đọc. Nhờ vậy, một `SELECT` không khóa thường có thể đọc dữ liệu nhất quán mà không phải chờ transaction khác nhả khóa ghi trên cùng hàng.

| Đặc điểm | `SELECT` thường | `UPDATE` / `DELETE` |
| --- | --- | --- |
| Cách đọc | Consistent read, không khóa hàng chỉ để đọc | Current/locking read để tìm và tác động lên hàng |
| Phiên bản được xét | Phiên bản phù hợp với read view của transaction hoặc statement | Phiên bản hiện hành đã commit, cộng với thay đổi của chính transaction |
| Mục đích | Đọc ảnh chụp nhất quán | Kiểm tra điều kiện trên dữ liệu hiện hành, sau đó khóa và sửa/xóa |
| Khóa ghi | Không lấy khóa hàng chỉ vì đọc | Lấy khóa trên các bản ghi và phạm vi chỉ mục cần thiết |
| Có thể thấy commit mới từ transaction khác? | Phụ thuộc read view và mức cô lập | Có thể thấy phiên bản mới nhất khi thực hiện thao tác |

`UPDATE` và `DELETE` không đơn giản lấy danh sách hàng từ kết quả của một `SELECT` trước đó. Chúng tự tìm hàng theo điều kiện của câu lệnh và dùng cơ chế đọc có khóa. Vì thế, hai câu lệnh trong cùng transaction có thể có tập hàng nhìn thấy khác nhau.

### 2. SELECT thường tạo read view như thế nào?

Với `REPEATABLE READ`, mức cô lập mặc định của InnoDB, read view cho các consistent read trong transaction thường được tạo tại lần consistent read đầu tiên. Các `SELECT` thường tiếp theo trong transaction sử dụng cùng read view đó. Commit từ transaction khác sau thời điểm này không xuất hiện trong các consistent read tiếp theo của transaction đang mở.

Với `READ COMMITTED`, mỗi consistent read thông thường tạo read view mới tại đầu câu lệnh. Vì vậy, hai câu `SELECT` trong cùng transaction có thể thấy các commit đã hoàn tất giữa hai câu lệnh. Điều này làm giảm hiện tượng đọc lặp lại cùng một snapshot, nhưng cũng có nghĩa kết quả của các lần đọc có thể khác nhau.

| Mức cô lập InnoDB | Thời điểm consistent read lấy snapshot | Hai `SELECT` thường trong cùng transaction |
| --- | --- | --- |
| `READ UNCOMMITTED` | Không bảo đảm consistent read theo snapshot như các mức cao hơn; có thể đọc dữ liệu chưa commit | Có thể đọc dữ liệu chưa commit và kết quả không nhất quán |
| `READ COMMITTED` | Mỗi câu lệnh consistent read | Có thể thấy commit mới giữa hai câu lệnh |
| `REPEATABLE READ` | Thường tại consistent read đầu tiên của transaction | Tiếp tục đọc cùng snapshot trong transaction |
| `SERIALIZABLE` | Khi transaction tường minh đang chạy, `SELECT` thường được chuyển thành locking read dùng khóa chia sẻ | Các thao tác đọc tham gia khóa để thực thi mức cô lập nghiêm ngặt hơn |

`START TRANSACTION` ở mức `REPEATABLE READ` không nhất thiết tạo read view ngay tại thời điểm câu lệnh chạy. Snapshot thường được xác lập khi transaction thực hiện consistent read đầu tiên. Nếu cần tạo snapshot nhất quán ngay lúc bắt đầu transaction, MySQL hỗ trợ `START TRANSACTION WITH CONSISTENT SNAPSHOT` trong điều kiện phù hợp.

### 3. UPDATE và DELETE đọc phiên bản hiện hành

Các câu `UPDATE` và `DELETE` cần biết hàng hiện đang có giá trị gì trước khi ghi thay đổi. Vì vậy, chúng dùng current read và khóa hàng được tác động. Nếu một transaction khác đang giữ khóa ghi trên hàng cần sửa, câu lệnh có thể phải chờ. Khi khóa được giải phóng, thao tác tiếp tục trên trạng thái hiện hành theo quy tắc của InnoDB và điều kiện `WHERE` được áp dụng cho hàng mà câu lệnh xử lý.

Ví dụ, giả sử bảng tồn kho:

```sql
CREATE TABLE inventory (
    id BIGINT PRIMARY KEY,
    sku VARCHAR(40) NOT NULL UNIQUE,
    quantity INT NOT NULL
) ENGINE = InnoDB;

INSERT INTO inventory (id, sku, quantity)
VALUES (1, 'KB-100', 10);
```

Ở mức `REPEATABLE READ`, thực hiện theo hai phiên sau.

**Phiên A:**

```sql
SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ;
START TRANSACTION;

SELECT quantity
FROM inventory
WHERE id = 1;
-- Kết quả: 10. Consistent read tạo read view của phiên A.
```

**Phiên B:**

```sql
START TRANSACTION;

UPDATE inventory
SET quantity = 7
WHERE id = 1;

COMMIT;
```

**Quay lại phiên A:**

```sql
SELECT quantity
FROM inventory
WHERE id = 1;
-- Vẫn đọc 10 từ read view cũ.

UPDATE inventory
SET quantity = quantity - 1
WHERE id = 1;

SELECT quantity
FROM inventory
WHERE id = 1;
-- Đọc thay đổi của chính phiên A: 6.

COMMIT;
```

`SELECT` đầu tiên và thứ hai của phiên A dùng snapshot cũ nên vẫn thấy `10`. Nhưng `UPDATE` dùng phiên bản hiện hành mà phiên B đã commit là `7`, rồi giảm xuống `6`. `SELECT` sau lệnh `UPDATE` thấy thay đổi của chính transaction A. Kết quả này tránh việc ghi đè mù giá trị `7` bằng `9` dựa trên snapshot cũ.

Ví dụ cho thấy một transaction có thể quan sát `10` bằng consistent read nhưng thao tác cập nhật lại tính toán trên giá trị hiện hành `7`. Không nên coi mọi câu lệnh trong transaction là đang đọc cùng một phiên bản dữ liệu.

### 4. Một SELECT không thấy hàng mới nhưng UPDATE vẫn có thể tác động đến hàng đó

Khác biệt không chỉ xảy ra với giá trị của một hàng đã tồn tại. Nó còn có thể xảy ra với hàng mới được transaction khác chèn sau khi read view của transaction hiện tại đã được tạo.

Giả sử bảng công việc:

```sql
CREATE TABLE job_queue (
    id BIGINT PRIMARY KEY,
    state VARCHAR(20) NOT NULL,
    created_at DATETIME NOT NULL
) ENGINE = InnoDB;

INSERT INTO job_queue (id, state, created_at)
VALUES (1, 'pending', '2026-11-01 09:00:00');
```

**Phiên A ở `REPEATABLE READ`:**

```sql
START TRANSACTION;

SELECT id
FROM job_queue
WHERE state = 'pending'
ORDER BY id;
-- Chỉ thấy id = 1; read view được tạo.
```

**Phiên B chèn và commit một hàng mới:**

```sql
INSERT INTO job_queue (id, state, created_at)
VALUES (2, 'pending', '2026-11-01 09:01:00');
COMMIT;
```

**Phiên A tiếp tục:**

```sql
SELECT id
FROM job_queue
WHERE state = 'pending'
ORDER BY id;
-- Vẫn chỉ thấy id = 1 trong snapshot cũ.

UPDATE job_queue
SET state = 'processing'
WHERE state = 'pending';
-- Có thể cập nhật cả id = 1 và id = 2.

SELECT id, state
FROM job_queue
ORDER BY id;
-- Phiên A thấy các thay đổi do chính nó thực hiện.

COMMIT;
```

Lệnh `UPDATE` tìm hàng theo trạng thái hiện hành và có thể tác động đến hàng `id = 2` mà consistent read trước đó không hiển thị. Đây là hệ quả của việc `UPDATE` dùng current read. Không nên suy ra số hàng bị sửa từ kết quả một `SELECT` không khóa chạy trước đó, ngay cả khi hai câu lệnh nằm trong cùng transaction `REPEATABLE READ`.

Ví dụ này giả định không có transaction khác giữ khóa xung đột và hàng mới đã commit trước khi `UPDATE` bắt đầu. Trong hệ thống thực tế, kết quả và thời gian chờ còn phụ thuộc khóa, thứ tự thực thi và điều kiện truy vấn.

### 5. Thay đổi nhìn thấy của chính transaction

Một consistent read không chỉ đọc snapshot cũ một cách máy móc. InnoDB luôn cho transaction thấy các thay đổi do chính transaction đó thực hiện. Vì vậy, nếu transaction cập nhật một hàng rồi đọc lại bằng `SELECT` thường, nó thấy giá trị mới của hàng đã sửa, trong khi những hàng khác vẫn có thể được đọc từ snapshot cũ.

Ví dụ:

```sql
START TRANSACTION;

SELECT id, quantity
FROM inventory
ORDER BY id;

UPDATE inventory
SET quantity = quantity - 1
WHERE id = 1;

SELECT id, quantity
FROM inventory
ORDER BY id;
-- Thấy quantity mới của id = 1 do transaction hiện tại sửa.

COMMIT;
```

Trong trường hợp có nhiều transaction đồng thời, kết quả cuối có thể là một tổ hợp: hàng do transaction hiện tại sửa được đọc ở phiên bản mới của chính nó, còn các hàng khác được đọc theo read view cũ. Đây là lý do không nên dùng một `SELECT` snapshot để suy luận rằng toàn bộ dữ liệu transaction đang thao tác đều thuộc cùng một thời điểm hiện hành.

### 6. SELECT ... FOR UPDATE và FOR SHARE là locking read

Khi ứng dụng cần đọc một hàng rồi quyết định cập nhật hàng đó, có thể dùng locking read để đồng bộ thao tác đọc với thao tác ghi. Hai dạng phổ biến:

- `SELECT ... FOR UPDATE`: lấy khóa độc quyền trên các hàng/index record được đọc, phù hợp khi transaction dự định sửa hoặc xóa chúng.
- `SELECT ... FOR SHARE`: lấy khóa chia sẻ, cho phép các transaction khác cũng đọc có khóa chia sẻ nhưng ngăn thay đổi xung đột cho đến khi transaction kết thúc.

Ví dụ kiểm tra và trừ tồn kho theo một transaction:

```sql
START TRANSACTION;

SELECT quantity
FROM inventory
WHERE id = 1
FOR UPDATE;

UPDATE inventory
SET quantity = quantity - 1
WHERE id = 1
  AND quantity >= 1;

COMMIT;
```

`FOR UPDATE` khóa hàng được tìm thấy để transaction khác không thể đồng thời thay đổi nó theo cách xung đột trước khi transaction hiện tại kết thúc. Ứng dụng vẫn phải kiểm tra số hàng bị tác động của `UPDATE`; nếu không có hàng nào được cập nhật, có thể hết tồn kho hoặc điều kiện không còn đúng.

Một cách khác là gộp điều kiện vào câu cập nhật có tính nguyên tử:

```sql
UPDATE inventory
SET quantity = quantity - 1
WHERE id = 1
  AND quantity >= 1;
```

Sau đó kiểm tra số hàng bị tác động để biết có trừ được tồn kho hay không. Cách này thường đơn giản hơn khi không cần đọc thêm thông tin giữa bước kiểm tra và cập nhật.

Nếu `autocommit=1`, khóa của locking read được giải phóng khi statement kết thúc. Muốn giữ khóa qua nhiều câu lệnh, phải đặt chúng trong một transaction tường minh và kết thúc bằng `COMMIT` hoặc `ROLLBACK`.

### 7. Mức cô lập ảnh hưởng thế nào đến UPDATE và DELETE?

Các câu `UPDATE` và `DELETE` vẫn phải đọc và khóa dữ liệu hiện hành ở các mức cô lập thông dụng. Khác biệt lớn giữa `READ COMMITTED` và `REPEATABLE READ` nằm ở consistent read và phạm vi khóa khoảng (gap/next-key lock).

| Đặc điểm | `READ COMMITTED` | `REPEATABLE READ` |
| --- | --- | --- |
| `SELECT` thường | Snapshot mới cho mỗi câu lệnh | Dùng cùng read view trong transaction sau lần đọc nhất quán đầu tiên |
| `UPDATE` / `DELETE` | Dùng current read để tìm và tác động lên hàng | Dùng current read để tìm và tác động lên hàng |
| Khóa khoảng | Thông thường không khóa gap cho tìm kiếm thông thường; vẫn có ngoại lệ như kiểm tra khóa ngoại và khóa trùng | Có thể dùng next-key lock để bảo vệ phạm vi index được quét |
| Hệ quả khi transaction khác chèn hàng mới | Câu `SELECT` tiếp theo có thể thấy hàng mới; DML vẫn xét dữ liệu hiện hành | `SELECT` thường có thể không thấy hàng mới trong snapshot, trong khi DML có thể xét hàng đó |

Ở `READ COMMITTED`, InnoDB có thể dùng *semi-consistent read* trong một số thao tác `UPDATE`: nếu hàng đang bị transaction khác khóa, MySQL có thể dùng phiên bản đã commit gần nhất để đánh giá điều kiện `WHERE`; nếu hàng phù hợp, nó đọc lại và lấy khóa cần thiết sau khi có thể tiếp tục. Đây là chi tiết tối ưu hóa nội bộ, không nên xem là cơ chế thay thế cho transaction hoặc khóa rõ ràng.

Ở `REPEATABLE READ`, next-key lock kết hợp khóa record và gap có thể ngăn transaction khác chèn vào một phạm vi chỉ mục mà câu lệnh đang quét. Phạm vi khóa phụ thuộc chỉ mục và kế hoạch truy cập, không chỉ phụ thuộc cách viết điều kiện `WHERE`. Một truy vấn quét phạm vi rộng có thể khóa nhiều record hoặc gap hơn dự kiến.

### 8. Khóa phụ thuộc vào chỉ mục và điều kiện tìm kiếm

InnoDB thường khóa các index record mà câu lệnh tìm thấy hoặc quét qua để thực hiện thao tác. Nếu điều kiện dùng khóa chính hoặc unique index với giá trị duy nhất, phạm vi khóa thường hẹp. Nếu điều kiện không có chỉ mục phù hợp, InnoDB có thể phải quét và khóa nhiều record hơn, làm tăng cạnh tranh và nguy cơ deadlock.

Ví dụ, nếu thường xuyên xử lý hàng đợi theo trạng thái và thời gian tạo:

```sql
CREATE INDEX idx_job_queue_state_created
    ON job_queue (state, created_at, id);

UPDATE job_queue
SET state = 'processing'
WHERE state = 'pending'
  AND created_at < CURRENT_TIMESTAMP;
```

Chỉ mục `(state, created_at, id)` có thể giúp tìm phạm vi cần xử lý hiệu quả hơn. Tuy nhiên, câu lệnh vẫn có thể khóa nhiều hàng pending phù hợp; chỉ mục không tự động giới hạn số hàng hoặc bảo đảm chỉ một worker xử lý một công việc. Muốn chia lô và phối hợp nhiều worker, cần thêm chiến lược claim, điều kiện cập nhật nguyên tử hoặc locking read phù hợp.

Có thể dùng `EXPLAIN` để kiểm tra đường truy cập dự kiến:

```sql
EXPLAIN
UPDATE job_queue
SET state = 'processing'
WHERE state = 'pending'
  AND created_at < CURRENT_TIMESTAMP;
```

Quan sát `key`, `type`, ước lượng số hàng và phạm vi quét. Nếu câu lệnh đọc quá nhiều hàng, hãy xem lại chỉ mục, điều kiện và cách chia lô. `EXPLAIN` cho biết kế hoạch dự kiến; khi điều tra tải hoặc khóa thực tế, cần kết hợp số liệu runtime và thông tin lock wait.

### 9. Quy tắc thực hành để tránh lỗi đọc và ghi

1. Nếu chỉ cần đọc báo cáo nhất quán, dùng `SELECT` thường và hiểu snapshot của mức cô lập đang áp dụng.
2. Nếu cần đọc một hàng rồi cập nhật dựa trên chính giá trị đó, cân nhắc `SELECT ... FOR UPDATE` trong transaction tường minh.
3. Nếu chỉ cần thực hiện phép thay đổi có điều kiện, ưu tiên đưa điều kiện vào một câu `UPDATE` nguyên tử và kiểm tra số hàng bị tác động.
4. Không dùng kết quả `SELECT` thường để dự đoán chắc chắn tập hàng mà `UPDATE` hoặc `DELETE` sẽ tác động.
5. Tạo chỉ mục phù hợp với điều kiện lọc và thứ tự truy cập để giảm số record bị quét/khóa.
6. Giữ transaction ngắn; commit hoặc rollback sớm để giải phóng khóa và giảm undo history.
7. Chuẩn bị xử lý deadlock và lock wait timeout bằng cách rollback transaction phù hợp và thử lại toàn bộ đơn vị công việc một cách có kiểm soát.
8. Khi cần xử lý hàng đợi nhiều worker, thiết kế cơ chế nhận việc (claim) có tính nguyên tử; không dựa vào một lần `SELECT` snapshot để phân chia công việc.

### 10. Tóm tắt

`SELECT` thường trong InnoDB đọc một snapshot theo MVCC. Ở `REPEATABLE READ`, snapshot thường được giữ xuyên suốt các consistent read trong transaction; ở `READ COMMITTED`, mỗi câu lệnh có snapshot mới. `UPDATE` và `DELETE` dùng current read cùng khóa để thao tác trên dữ liệu hiện hành. Vì vậy, chúng có thể tác động đến hàng mà `SELECT` trước đó không nhìn thấy, đồng thời vẫn cho transaction thấy các thay đổi do chính nó thực hiện. Khi cần đồng bộ một chuỗi đọc rồi ghi, hãy dùng locking read hoặc một câu DML có điều kiện nguyên tử, chọn chỉ mục phù hợp và quản lý transaction ngắn gọn.
