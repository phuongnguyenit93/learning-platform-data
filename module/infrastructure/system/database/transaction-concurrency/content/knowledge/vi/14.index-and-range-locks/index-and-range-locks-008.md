# ORDER BY, LIMIT và phạm vi khóa cần kiểm chứng thực tế

Một câu truy vấn có `ORDER BY` và `LIMIT` thường trả về một tập kết quả nhỏ. Tuy nhiên, số hàng được trả về không cho biết chính xác database đã phải đọc và khóa bao nhiêu bản ghi trong quá trình thực thi. Phạm vi khóa phụ thuộc vào chỉ mục được chọn, thứ tự quét, điều kiện lọc, isolation level và cách storage engine thực hiện locking read.

Với MySQL InnoDB, câu `SELECT ... FOR UPDATE` có thể khóa các bản ghi chỉ mục được quét và những bản ghi clustered index tương ứng. Khi quét một khoảng chỉ mục ở `REPEATABLE READ`, InnoDB còn có thể dùng next-key lock để bảo vệ khoảng giữa các bản ghi. Vì thế, `LIMIT 10` không phải cam kết rằng chỉ có đúng 10 bản ghi hoặc 10 khoảng khóa bị ảnh hưởng.

Muốn biết phạm vi khóa thực tế, cần đọc execution plan, xem các lock đang tồn tại trong `performance_schema.data_locks`, rồi thử cạnh tranh bằng một transaction khác. Bài này tập trung vào MySQL InnoDB; các hệ quản trị khác có mô hình khóa và công cụ quan sát khác nhau.

## 1. ORDER BY và LIMIT mô tả kết quả, không mô tả phạm vi khóa

Giả sử hệ thống có bảng `jobs` chứa các công việc cần worker nhận xử lý:

```sql
CREATE TABLE jobs (
    id BIGINT PRIMARY KEY,
    status VARCHAR(20) NOT NULL,
    priority INT NOT NULL,
    created_at DATETIME(6) NOT NULL,
    KEY ix_jobs_claim (status, priority, id)
) ENGINE = InnoDB;
```

Một worker muốn nhận 10 công việc có trạng thái `READY`, ưu tiên cao trước:

```sql
START TRANSACTION;

SELECT id, priority, created_at
FROM jobs
WHERE status = 'READY'
ORDER BY priority, id
LIMIT 10
FOR UPDATE;

-- Cập nhật trạng thái các id đã nhận.
-- COMMIT sau khi thao tác nhận việc hoàn tất.
```

`ORDER BY priority, id` xác định thứ tự kết quả. `LIMIT 10` giới hạn số hàng được trả về. `FOR UPDATE` yêu cầu khóa các bản ghi cần thiết cho locking read đến khi transaction kết thúc.

Trong InnoDB, locking read chỉ có hiệu lực khi đang ở trong transaction; nếu `autocommit` bật và câu lệnh chạy độc lập ngoài transaction tường minh, `FOR UPDATE` không giữ khóa cho một bước xử lý tiếp theo. Hãy dùng `START TRANSACTION`/`BEGIN` hoặc tắt autocommit cho phạm vi công việc cần khóa, rồi kết thúc bằng `COMMIT` hoặc `ROLLBACK`.

Ba khái niệm này có vai trò khác nhau:

- `ORDER BY` xác định thứ tự logic của các hàng kết quả.
- `LIMIT` giới hạn số hàng kết quả.
- `FOR UPDATE` yêu cầu database khóa dữ liệu được truy cập theo execution plan và quy tắc của storage engine.

Nếu database có thể đọc trực tiếp theo đúng thứ tự từ chỉ mục, nó có thể dừng quét sau khi tìm đủ số hàng cần thiết. Nếu phải dùng một access path khác rồi sắp xếp, nó có thể phải xem xét nhiều ứng viên hơn trước khi xác định 10 hàng đầu tiên. Cần xem execution plan và lock thực tế để biết điều gì xảy ra trong trường hợp cụ thể.

## 2. Chỉ mục quyết định đường quét

Chỉ mục `ix_jobs_claim (status, priority, id)` phù hợp với truy vấn vì:

1. `status` được lọc bằng điều kiện bằng (`status = 'READY'`).
2. Sau khi cố định giá trị `status`, các entry tiếp theo được sắp theo `priority` rồi `id`.
3. Database có thể duyệt các entry theo thứ tự yêu cầu và dừng khi tìm đủ số hàng phù hợp, nếu execution plan chọn đường quét này.

Thứ tự cột trong composite index quan trọng. Với truy vấn lọc một giá trị `status` và sắp theo `priority, id`, chỉ mục `(status, priority, id)` thường hữu ích hơn chỉ mục `(priority, id)` vì nó có thể giới hạn vùng quét ngay từ `status`.

So sánh hai định nghĩa:

```sql
-- Hỗ trợ lọc status trước, sau đó đọc theo thứ tự ưu tiên.
CREATE INDEX ix_jobs_claim
ON jobs (status, priority, id);

-- Có thể phải quét nhiều priority rồi mới lọc status.
CREATE INDEX ix_jobs_priority
ON jobs (priority, id);
```

Chỉ mục thứ hai vẫn có thể giúp `ORDER BY`, nhưng nếu các hàng `READY` thưa giữa nhiều trạng thái khác, engine có thể phải duyệt qua nhiều entry trước khi thu được đủ 10 hàng phù hợp. Các cột và thứ tự thực tế phải dựa trên workload, phân bố dữ liệu và execution plan.

### Thêm cột tie-breaker để thứ tự ổn định

Nếu chỉ viết:

```sql
ORDER BY priority
LIMIT 10
```

thì nhiều hàng cùng priority không có thứ tự xác định giữa chúng. Lần chạy sau có thể trả về nhóm hàng khác khi execution plan hoặc dữ liệu thay đổi. Thêm một khóa duy nhất làm tie-breaker:

```sql
ORDER BY priority, id
LIMIT 10
```

Thứ tự ổn định giúp worker phân chia công việc và kiểm thử phạm vi quét dễ hiểu hơn. Nó cũng giúp chỉ mục `(status, priority, id)` hỗ trợ thứ tự cần thiết.

## 3. Vì sao LIMIT không bảo đảm chỉ khóa đúng N hàng?

Kết quả trả về và các index record được quét là hai khái niệm khác nhau. Một locking read có thể truy cập nhiều index record để tìm hàng thỏa điều kiện. InnoDB áp dụng khóa theo các record được truy cập trong đường thực thi, và với secondary index có thể khóa cả record tương ứng trong clustered index.

Một số yếu tố làm phạm vi khóa rộng hơn số hàng trả về:

- Không có chỉ mục phù hợp cho điều kiện lọc hoặc thứ tự sắp xếp.
- Chỉ mục hỗ trợ `ORDER BY` nhưng không hỗ trợ lọc hiệu quả, khiến engine phải quét qua nhiều hàng không thỏa điều kiện.
- Điều kiện lọc còn lại được đánh giá sau khi đọc index entry hoặc sau khi lấy dữ liệu từ clustered index.
- Phạm vi khóa ở `REPEATABLE READ` bao gồm next-key lock hoặc gap lock để ngăn thao tác chèn vào khoảng đang được bảo vệ.
- Execution plan thay đổi khi thống kê, dữ liệu hoặc tham số truy vấn thay đổi.

Ví dụ, truy vấn sau trả về tối đa 10 hàng:

```sql
SELECT id, priority
FROM jobs
WHERE status = 'READY'
  AND priority <= 3
ORDER BY priority, id
LIMIT 10
FOR UPDATE;
```

Nếu chỉ mục phù hợp là `(status, priority, id)`, vùng tìm kiếm có thể được giới hạn tốt. Nếu chỉ có chỉ mục khác hoặc không có chỉ mục phù hợp, engine có thể phải quét rộng hơn. Số hàng trả về vẫn tối đa 10 trong cả hai trường hợp, nhưng lock footprint có thể khác đáng kể.

Không nên diễn giải câu “InnoDB khóa các record được quét” thành một công thức đơn giản rằng mọi hàng mà optimizer từng đọc đều chắc chắn còn bị khóa đến commit. Việc lọc điều kiện, loại truy cập, isolation level, loại lock và giai đoạn thực thi đều có thể ảnh hưởng. Hãy quan sát `data_locks` trong transaction đang mở và thử thao tác cạnh tranh để xác nhận hành vi của phiên bản MySQL cụ thể.

## 4. ORDER BY có thể cần filesort

Nếu không có chỉ mục cung cấp thứ tự cần thiết, MySQL có thể sử dụng `filesort`. Tên này không có nghĩa lúc nào cũng ghi file xuống đĩa; đây là tên thuật toán sắp xếp bổ sung của MySQL.

Ví dụ, truy vấn:

```sql
SELECT id, priority
FROM jobs
WHERE status = 'READY'
ORDER BY priority, id
LIMIT 10
FOR UPDATE;
```

có thể dùng `ix_jobs_claim` để duyệt theo thứ tự. Nếu chỉ mục đó không tồn tại hoặc optimizer chọn đường khác, execution plan có thể hiển thị `Using filesort`.

Khi cần sắp xếp, database phải xem xét các ứng viên để xác định thứ tự kết quả. `LIMIT` có thể giúp thuật toán giảm lượng dữ liệu cần giữ hoặc sắp xếp, nhưng không tự động biến access path thành một range scan chỉ gồm 10 record. Đặc biệt với locking read, đừng suy luận phạm vi khóa từ việc kết quả cuối cùng chỉ có 10 dòng.

Nếu truy vấn thường xuyên dùng `ORDER BY ... LIMIT`, hãy cân nhắc thiết kế composite index khớp với equality predicate và thứ tự sắp xếp. Sau đó xác nhận optimizer thực sự chọn chỉ mục đó trong môi trường có dữ liệu và thống kê tương tự production.

## 5. Next-key lock và gap lock làm phạm vi khóa lớn hơn record

InnoDB dùng record lock để khóa một index record. Ở `REPEATABLE READ`, range scan có thể dùng **next-key lock**, kết hợp record lock trên một index record với gap lock trên khoảng ngay trước record đó. Gap lock bảo vệ khoảng giữa các key, ngăn transaction khác chèn key mới vào vùng được khóa.

Ví dụ, index có các key `10`, `20`, `30`, `40`. Một range locking read có thể khóa các record và các khoảng liên quan, tùy điều kiện và access path:

```text
... ( -∞, 10 ] ( 10, 20 ] ( 20, 30 ] ( 30, 40 ] ( 40, +∞ )
          ^          ^          ^          ^
       next-key   next-key   next-key   next-key
```

Đây là hình minh họa khái niệm, không phải cam kết rằng một truy vấn cụ thể khóa tất cả các khoảng trên. Phạm vi thật phụ thuộc range được quét, index được dùng, điều kiện biên và isolation level.

Một truy vấn dùng equality predicate trên toàn bộ cột của unique index để tìm đúng một hàng tồn tại thường chỉ cần record lock trên hàng đó, không cần gap lock bao quanh. Nhưng nếu tìm kiếm theo range, theo prefix không duy nhất hoặc không tìm thấy key, gap/next-key lock có thể xuất hiện ở `REPEATABLE READ`.

Ở `READ COMMITTED`, InnoDB thường tắt gap locking cho các search và index scan thông thường; gap lock vẫn có thể được dùng cho kiểm tra khóa ngoại và duplicate-key. Vì vậy, cùng một truy vấn có thể tạo lock footprint khác giữa `READ COMMITTED` và `REPEATABLE READ`.

## 6. Ví dụ worker nhận việc bằng ORDER BY, LIMIT và SKIP LOCKED

Một queue nhiều worker thường muốn mỗi worker nhận một nhóm việc mà không phải chờ các worker khác đang giữ hàng. MySQL hỗ trợ `SKIP LOCKED` cho locking read:

```sql
START TRANSACTION;

SELECT id
FROM jobs
WHERE status = 'READY'
ORDER BY priority, id
LIMIT 10
FOR UPDATE SKIP LOCKED;

-- Dùng các id vừa nhận để cập nhật trạng thái.
UPDATE jobs
SET status = 'RUNNING'
WHERE id IN (101, 102, 103);

COMMIT;
```

Danh sách id trong câu `UPDATE` chỉ là ví dụ; ứng dụng phải dùng chính các id mà câu `SELECT` trả về.

`SKIP LOCKED` bỏ qua hàng đang bị transaction khác khóa thay vì chờ chúng. Điều này hữu ích cho queue, nhưng kết quả không còn là một góc nhìn nhất quán thông thường của bảng: các hàng bị khóa bị bỏ qua. Không dùng nó cho báo cáo cần đầy đủ mọi hàng.

`SKIP LOCKED` cũng không có nghĩa worker chắc chắn khóa đúng 10 index record. Để tìm đủ 10 hàng chưa bị khóa, engine có thể phải đi qua nhiều entry hơn. Nếu các hàng đầu danh sách thường xuyên bị khóa, worker có thể quét sâu hơn trong index. Với gap lock hoặc access path rộng, các thao tác chèn và cập nhật khác vẫn có thể chịu ảnh hưởng.

Một transaction cần kết thúc nhanh sau khi nhận việc. Không giữ transaction mở trong lúc worker thực hiện tác vụ dài bên ngoài database; hãy commit trạng thái nhận việc trước, sau đó xử lý công việc bằng một transaction riêng khi cần ghi kết quả.

## 7. NOWAIT và SKIP LOCKED không thay thế thiết kế chỉ mục

MySQL cung cấp `NOWAIT` và `SKIP LOCKED` cho locking read:

```sql
-- Trả lỗi ngay nếu cần chờ một row lock.
SELECT id
FROM jobs
WHERE status = 'READY'
ORDER BY priority, id
LIMIT 10
FOR UPDATE NOWAIT;
```

```sql
-- Bỏ qua các hàng đang bị khóa.
SELECT id
FROM jobs
WHERE status = 'READY'
ORDER BY priority, id
LIMIT 10
FOR UPDATE SKIP LOCKED;
```

`NOWAIT` giúp ứng dụng phản hồi nhanh khi hàng cần khóa đang bận. `SKIP LOCKED` giúp worker lấy hàng khác. Cả hai điều khiển hành vi khi gặp row lock; chúng không bảo đảm phạm vi quét nhỏ, không loại bỏ gap lock và không xử lý mọi loại chờ khác như metadata lock.

Nếu truy vấn cần quét hàng trăm nghìn index entry để tìm 10 hàng, `SKIP LOCKED` không sửa được vấn đề access path. Cần thiết kế index và predicate phù hợp, sau đó đo lại.

## 8. Kiểm tra execution plan trước khi suy luận lock footprint

Dùng `EXPLAIN` để xem optimizer dự kiến truy cập dữ liệu như thế nào:

```sql
EXPLAIN FORMAT=JSON
SELECT id, priority, created_at
FROM jobs
WHERE status = 'READY'
ORDER BY priority, id
LIMIT 10
FOR UPDATE;
```

Các trường cần chú ý tùy định dạng output:

- `key`: chỉ mục mà optimizer dự kiến sử dụng.
- `type` hoặc `access_type`: kiểu truy cập như `range`, `ref`, `eq_ref`, `index` hoặc `ALL`.
- `rows` và `rows_examined_per_scan`: số hàng ước lượng mà optimizer dự kiến phải xem.
- `filtered`: tỷ lệ hàng ước tính còn lại sau điều kiện lọc.
- `using_filesort` hoặc `Using filesort`: có bước sắp xếp bổ sung.
- `attached_condition` và thông tin index condition: điều kiện nào được áp dụng trong từng giai đoạn.

`EXPLAIN` cho biết kế hoạch và ước lượng, không chứng minh chính xác những khóa được cấp trong lần chạy thật. `EXPLAIN ANALYZE` thực thi câu lệnh để đo số hàng thực tế và thời gian; với locking read, điều này có thể lấy khóa và tạo tác động lên dữ liệu. Chỉ dùng trong môi trường thử nghiệm hoặc transaction được kiểm soát, không chạy tùy tiện trên production.

Sau khi thêm hoặc thay đổi index, hãy chạy lại `EXPLAIN` với dữ liệu và tham số đại diện. Thống kê cũ, phân bố dữ liệu lệch hoặc parameter khác nhau có thể khiến optimizer chọn access path khác.

## 9. Quan sát khóa thực tế bằng Performance Schema

Trong MySQL 8.0, `performance_schema.data_locks` hiển thị các khóa dữ liệu InnoDB đang được giữ hoặc chờ. Truy vấn ví dụ:

```sql
SELECT
    ENGINE_TRANSACTION_ID,
    THREAD_ID,
    OBJECT_SCHEMA,
    OBJECT_NAME,
    INDEX_NAME,
    LOCK_TYPE,
    LOCK_MODE,
    LOCK_STATUS,
    LOCK_DATA
FROM performance_schema.data_locks
WHERE OBJECT_SCHEMA = DATABASE()
  AND OBJECT_NAME = 'jobs'
ORDER BY THREAD_ID, INDEX_NAME, LOCK_DATA;
```

Các cột quan trọng:

- `OBJECT_NAME`: bảng đang có khóa.
- `INDEX_NAME`: chỉ mục mà record lock liên quan đến; có thể là secondary index hoặc `PRIMARY`.
- `LOCK_TYPE`: thường là `RECORD` hoặc `TABLE`.
- `LOCK_MODE`: mode khóa. Có thể thấy `X`, `S`, `X,GAP`, `X,REC_NOT_GAP` hoặc các biến thể tùy loại khóa và phiên bản.
- `LOCK_STATUS`: `GRANTED` nếu đã được cấp, `WAITING` hoặc trạng thái chờ tương ứng nếu chưa được cấp tùy phiên bản hiển thị.
- `LOCK_DATA`: giá trị key hoặc thông tin record liên quan; có thể không có đầy đủ trong mọi trường hợp.

Với secondary index, có thể thấy khóa trên index được dùng để tìm hàng và khóa trên clustered index tương ứng. Không đếm số dòng trong `data_locks` rồi coi đó là số hàng kết quả: một hàng có thể tạo nhiều lock entry và một entry có thể đại diện cho phạm vi record/gap.

### Tìm quan hệ giữa phiên chờ và phiên chặn

```sql
SELECT
    REQUESTING_ENGINE_TRANSACTION_ID AS waiting_trx,
    REQUESTING_THREAD_ID AS waiting_thread,
    BLOCKING_ENGINE_TRANSACTION_ID AS blocking_trx,
    BLOCKING_THREAD_ID AS blocking_thread,
    REQUESTING_ENGINE_LOCK_ID,
    BLOCKING_ENGINE_LOCK_ID
FROM performance_schema.data_lock_waits;
```

View này giúp xác định transaction nào đang chờ transaction nào. Có thể join `data_locks` theo engine lock id để xem đối tượng, index và mode liên quan.

### Kiểm tra trạng thái InnoDB

```sql
SHOW ENGINE INNODB STATUS\G
```

Phần `TRANSACTIONS` và `LATEST DETECTED DEADLOCK` có thể cung cấp thêm thông tin về transaction, lock wait và deadlock. Đây là ảnh chụp trạng thái tại thời điểm chạy lệnh; kết hợp với `data_locks` và `data_lock_waits` để hiểu tình huống đang diễn ra.

Quyền đọc Performance Schema có thể bị giới hạn. Tên cột, trạng thái và chi tiết hiển thị phụ thuộc phiên bản MySQL. Hãy kiểm tra schema thực tế trước khi đưa truy vấn giám sát vào công cụ vận hành.

## 10. Thử nghiệm hai phiên để xác nhận phạm vi khóa

Execution plan chỉ là một phần bằng chứng. Cách trực tiếp hơn là giữ transaction A mở rồi thử thao tác có khả năng xung đột từ transaction B. Thực hiện trong database thử nghiệm với dữ liệu có kiểm soát.

### Chuẩn bị dữ liệu

```sql
CREATE TABLE jobs_test (
    id BIGINT PRIMARY KEY,
    status VARCHAR(20) NOT NULL,
    priority INT NOT NULL,
    note VARCHAR(100),
    KEY ix_jobs_test (status, priority, id)
) ENGINE = InnoDB;

INSERT INTO jobs_test (id, status, priority, note) VALUES
(1, 'READY', 1, 'a'),
(2, 'READY', 2, 'b'),
(3, 'READY', 3, 'c'),
(4, 'READY', 4, 'd'),
(5, 'READY', 5, 'e'),
(6, 'READY', 6, 'f'),
(7, 'DONE', 1, 'g');
```

### Session A: lấy khóa và giữ transaction

```sql
SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ;
START TRANSACTION;

SELECT id, priority
FROM jobs_test
WHERE status = 'READY'
ORDER BY priority, id
LIMIT 3
FOR UPDATE;

-- Giữ transaction mở để quan sát.
```

### Session B: thử cập nhật các hàng khác nhau

Thử từng câu một, ghi nhận câu nào chạy ngay và câu nào chờ:

```sql
-- Hàng nằm trong top 3 đã được chọn.
UPDATE jobs_test SET note = 'locked-row' WHERE id = 2;

-- Hàng READY ở ngoài top 3.
UPDATE jobs_test SET note = 'later-ready' WHERE id = 5;

-- Hàng thuộc trạng thái khác.
UPDATE jobs_test SET note = 'done-row' WHERE id = 7;

-- Chèn một key có vị trí nằm trong vùng sắp xếp của READY.
INSERT INTO jobs_test (id, status, priority, note)
VALUES (8, 'READY', 2, 'new-row');
```

Không chạy tất cả câu lệnh trong cùng một transaction nếu câu đầu tiên đã bị block; mỗi lần thử cần được kiểm soát riêng để dễ quan sát. Khi Session B đang chờ, kiểm tra `performance_schema.data_locks` và `data_lock_waits` từ Session giám sát thứ ba.

### So sánh access path và isolation level

Lặp lại thí nghiệm với các biến thể:

1. Giữ index `(status, priority, id)` và xác nhận optimizer sử dụng index đó.
2. Dùng `IGNORE INDEX (ix_jobs_test)` trong môi trường thử nghiệm để xem kế hoạch và lock thay đổi thế nào khi không dùng index phù hợp.
3. Thử `READ COMMITTED` thay cho `REPEATABLE READ` để quan sát khác biệt về gap lock.
4. Thử `LIMIT 1`, `LIMIT 3` và `LIMIT 5`.
5. Thử `ORDER BY priority, id` và một thứ tự không được index hỗ trợ.

Sau mỗi lượt, kết thúc transaction A bằng `ROLLBACK` hoặc `COMMIT`, xác nhận các session chờ được giải phóng rồi mới bắt đầu lượt tiếp theo. Không dùng `KILL` tùy tiện để dọn thí nghiệm.

Kết quả cần ghi lại gồm:

- SQL chính xác và isolation level.
- Kết quả `EXPLAIN` cùng index được chọn.
- Các dòng liên quan trong `performance_schema.data_locks`.
- Thao tác Session B và việc nó chạy ngay, chờ hay bị từ chối.
- Phiên bản MySQL, engine và cấu hình liên quan.

Thí nghiệm này cho thấy phạm vi khóa trong môi trường cụ thể. Không lấy kết quả từ một bộ dữ liệu nhỏ để khẳng định mọi execution plan production sẽ có cùng hành vi.

## 11. Những thay đổi có thể làm phạm vi khóa khác đi

| Thay đổi | Điều cần kiểm tra lại |
|---|---|
| Thêm hoặc bỏ composite index | Optimizer có đổi từ range/ref scan sang full scan hoặc filesort không? |
| Thay đổi thứ tự cột index | Equality predicate và `ORDER BY` còn khớp prefix của index không? |
| Thay đổi tỷ lệ `READY` | Số index entry phải quét để tìm đủ N hàng có tăng không? |
| Thay đổi `LIMIT` | Scan có dừng sớm hơn không; các gap/record lock nào được giữ? |
| Thay đổi isolation level | Gap/next-key lock có khác không? |
| Thêm điều kiện phụ | Điều kiện được áp dụng trong index hay sau khi lấy row? |
| Dữ liệu phân bố lệch | Thống kê có khiến optimizer chọn access path khác không? |
| Thay đổi phiên bản MySQL | Optimizer, lock instrumentation và hành vi engine có thay đổi không? |

Một thay đổi schema tưởng như chỉ để tăng tốc có thể thay đổi cả đường quét và lock footprint. Vì vậy, sau khi thêm index hoặc nâng cấp MySQL, cần kiểm chứng lại các truy vấn locking quan trọng.

## 12. Cách thu hẹp phạm vi khóa

### Thiết kế index theo điều kiện và thứ tự

Với truy vấn có equality predicate rồi đến thứ tự sắp xếp, xem xét composite index theo dạng:

```text
(các cột equality, các cột range/order, khóa duy nhất làm tie-breaker)
```

Ví dụ `(status, priority, id)` cho `status = ? ORDER BY priority, id`. Không tạo index chỉ dựa trên một truy vấn; cần cân nhắc chi phí ghi, dung lượng và các truy vấn khác.

### Chỉ chọn các cột cần thiết

Tránh `SELECT *` nếu worker chỉ cần `id` để nhận việc. Projection nhỏ có thể giảm I/O và đôi khi cho phép index-only/covering access trong những trường hợp phù hợp, nhưng không nên mặc định rằng covering index sẽ loại bỏ mọi lock trên clustered index đối với locking read.

### Giữ transaction ngắn

Lấy khóa, cập nhật trạng thái và commit nhanh. Không giữ `FOR UPDATE` trong khi gọi HTTP, xử lý file hoặc chờ worker hoàn thành công việc. Lock footprint rộng trong thời gian ngắn vẫn có thể ảnh hưởng, nhưng transaction kéo dài làm tăng xác suất xung đột và thời gian chặn.

### Dùng SKIP LOCKED có chủ đích

Đối với queue, `SKIP LOCKED` có thể giúp worker lấy hàng khác thay vì chờ. Cần chấp nhận rằng thứ tự xử lý có thể bỏ qua hàng đang bận và không bảo đảm FIFO tuyệt đối. Theo dõi hàng bị bỏ qua lâu để tránh starvation.

### Không hạ isolation level chỉ để giảm lock

`READ COMMITTED` thường giảm gap lock trong các range scan thông thường của InnoDB, nhưng thay đổi semantics về snapshot và phantom. Chỉ chọn isolation level theo yêu cầu nghiệp vụ và kiểm thử các bất biến cần bảo vệ.

## 13. Checklist khi truy vấn ORDER BY LIMIT khóa rộng hơn dự kiến

1. Xác nhận câu lệnh có thực sự là locking read (`FOR UPDATE` hoặc `FOR SHARE`) và transaction có đang mở hay không.
2. Ghi lại isolation level, autocommit và thời gian transaction giữ khóa.
3. Chạy `EXPLAIN` để xác định index, access type, ước lượng hàng và `Using filesort`.
4. Kiểm tra index có khớp equality predicate, range và thứ tự `ORDER BY` hay không.
5. Xem `performance_schema.data_locks` để biết index, lock mode và key đang bị khóa.
6. Xem `data_lock_waits` để xác định phiên chờ và phiên chặn.
7. Dùng một session khác thử cập nhật hoặc chèn vào các vị trí trong/ngoài vùng kết quả.
8. Lặp lại với dữ liệu đại diện, isolation level và execution plan thực tế.
9. Điều chỉnh index hoặc query, sau đó kiểm chứng lại cả hiệu năng lẫn lock footprint.
10. Đảm bảo transaction kết thúc ngay sau thao tác cần khóa.

## 14. Tự kiểm tra

**Truy vấn `ORDER BY priority LIMIT 10 FOR UPDATE` có bảo đảm chỉ khóa 10 hàng trả về không?**

Không. `LIMIT` giới hạn số hàng kết quả. Lock footprint còn phụ thuộc index được quét, điều kiện lọc, thứ tự thực thi, isolation level và các next-key/gap lock có liên quan.

**Vì sao index `(status, priority, id)` có thể phù hợp với truy vấn queue?**

Điều kiện `status = ?` cố định cột đầu tiên; các cột tiếp theo cung cấp thứ tự `priority, id`. Engine có thể quét đúng vùng và thứ tự cần thiết hiệu quả hơn nếu optimizer chọn index đó.

**`Using filesort` có ý nghĩa gì khi điều tra khóa?**

Đó là dấu hiệu MySQL cần một bước sắp xếp bổ sung thay vì lấy kết quả trực tiếp theo thứ tự index. Cần kiểm tra số ứng viên và lock thực tế; không suy ra phạm vi khóa chỉ từ số hàng cuối cùng.

**Next-key lock khác record lock thế nào?**

Record lock bảo vệ một index record. Next-key lock kết hợp record lock với gap lock trên khoảng trước record, giúp ngăn chèn key mới vào khoảng đó.

**Làm sao biết truy vấn có khóa rộng hơn dự kiến?**

Đọc execution plan, xem `performance_schema.data_locks` và `data_lock_waits`, rồi dùng session thứ hai thử cập nhật/chèn vào các key liên quan trong transaction thử nghiệm.

Khi đánh giá một locking query có `ORDER BY` và `LIMIT`, hãy tách rõ **kết quả logic, đường quét vật lý và các khóa được cấp**. Chỉ khi đối chiếu cả ba với execution plan và quan sát lock thực tế, ta mới biết giới hạn kết quả có thật sự giúp thu hẹp phạm vi khóa trong hệ thống đang chạy hay không.
