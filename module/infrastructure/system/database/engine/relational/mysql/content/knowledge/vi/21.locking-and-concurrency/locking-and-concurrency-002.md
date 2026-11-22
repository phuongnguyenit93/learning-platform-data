# Record lock, gap lock, next-key lock và insert intention lock

InnoDB dùng khóa để bảo vệ dữ liệu khi nhiều transaction cùng đọc, thêm, sửa hoặc xóa hàng. Các khóa này được đặt trên **index record và khoảng giữa các index record**, vì vậy phạm vi khóa phụ thuộc vào index mà execution plan sử dụng. Bốn khái niệm cần phân biệt là `record lock`, `gap lock`, `next-key lock` và `insert intention lock`.

- **Record lock** khóa một index record cụ thể.
- **Gap lock** khóa khoảng trống giữa các index record để ngăn transaction khác chèn khóa mới vào khoảng đó.
- **Next-key lock** kết hợp record lock với gap lock ngay trước index record.
- **Insert intention lock** thể hiện ý định chèn một index record vào gap; các transaction chèn ở vị trí khác nhau trong cùng gap có thể không phải chờ nhau.

Các cơ chế này đặc biệt quan trọng ở isolation level `REPEATABLE READ`, khi InnoDB dùng next-key/gap locking trong nhiều locking read và thao tác ghi theo phạm vi để ngăn phantom row. Hiểu đúng phạm vi khóa giúp giải thích vì sao một câu INSERT bị chặn dù không sửa cùng hàng, vì sao truy vấn thiếu index có thể khóa quá rộng và vì sao nhiều thao tác chèn vào cùng khoảng có thể vẫn chạy đồng thời.

## 1. Khóa của InnoDB gắn với index

InnoDB tổ chức dữ liệu theo clustered index. Nếu bảng có primary key, primary key là clustered index. Nếu không khai báo primary key, InnoDB chọn một unique index phù hợp hoặc tạo clustered index ẩn. Các secondary index lưu khóa phụ cùng với giá trị primary key để tìm hàng tương ứng.

Do đó, khi nói “khóa hàng”, cần hiểu InnoDB thực tế khóa các index record liên quan. Một truy vấn dùng secondary index có thể khóa entry trên secondary index và cả record tương ứng trong clustered index. Khóa không đơn thuần là một nhãn logic gắn vào dòng hiển thị trong kết quả SELECT.

Điều này dẫn tới ba hệ quả:

1. Index được chọn bởi optimizer ảnh hưởng đến các record và gap bị khóa.
2. Truy vấn có thể khóa những index record đã được quét để đánh giá điều kiện, kể cả một số hàng cuối cùng không xuất hiện trong kết quả.
3. Thiếu index phù hợp có thể khiến InnoDB quét và khóa phạm vi lớn hơn dự kiến, làm tăng cạnh tranh và lock wait.

Vì vậy, khi điều tra lock, cần xem cả điều kiện SQL, index, execution plan và isolation level.

## 2. Chuẩn bị bảng thực hành

Tạo bảng InnoDB có primary key và secondary index không unique:

```sql
CREATE TABLE lock_demo (
    id BIGINT UNSIGNED NOT NULL,
    code INT NOT NULL,
    note VARCHAR(100) NOT NULL,
    PRIMARY KEY (id),
    KEY idx_lock_demo_code (code)
) ENGINE=InnoDB;

INSERT INTO lock_demo (id, code, note)
VALUES
    (1, 10, 'ten'),
    (2, 20, 'twenty'),
    (3, 30, 'thirty');
```

Index `idx_lock_demo_code` có các giá trị 10, 20 và 30. Vì index không unique, một `code` có thể xuất hiện ở nhiều hàng. Khoảng giữa các giá trị index có thể được dùng để minh họa gap lock và insert intention lock.

Kiểm tra:

```sql
SELECT id, code, note
FROM lock_demo
ORDER BY code, id;

SHOW INDEX FROM lock_demo;
```

Các ví dụ hai session bên dưới giả định bảng dùng InnoDB, transaction mở tường minh và isolation level được đặt như chỉ dẫn. Chạy trên database thử nghiệm vì một số bước cố ý tạo lock wait.

## 3. Record lock: khóa một index record

Record lock khóa index record cụ thể. Với primary key, truy vấn equality tìm đúng một hàng có thể chỉ cần khóa record đó nếu điều kiện dùng đầy đủ unique key và hàng tồn tại.

Ví dụ Session A:

```sql
SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ;
START TRANSACTION;

SELECT id, code, note
FROM lock_demo
WHERE id = 2
FOR UPDATE;
```

InnoDB đặt exclusive record lock trên record primary key `id = 2`. Trong khi Session A chưa commit, Session B thử sửa cùng hàng:

```sql
START TRANSACTION;

UPDATE lock_demo
SET note = 'updated by B'
WHERE id = 2;
```

UPDATE ở Session B phải chờ vì Session A đang giữ khóa không tương thích trên cùng record. Khi Session A chạy:

```sql
COMMIT;
```

Session B có thể tiếp tục. Kết thúc Session B bằng `COMMIT` hoặc `ROLLBACK`.

### Record lock không đồng nghĩa chỉ khóa một hàng theo nghĩa ứng dụng

Record lock luôn thuộc về một index record. Nếu truy vấn dùng secondary index, InnoDB có thể khóa secondary index record và clustered record liên quan. Nếu một điều kiện không unique khớp nhiều hàng, nhiều record có thể bị khóa.

Với một phép tìm kiếm equality trên toàn bộ cột của unique index và tìm thấy hàng, InnoDB thường chỉ cần record lock, không cần khóa gap trước record đó. Quy tắc này không áp dụng khi chỉ tìm một phần của composite unique key, dùng range predicate hoặc không tìm thấy hàng.

## 4. Gap lock: khóa khoảng trống giữa các index record

Gap lock khóa khoảng giữa các index record, không khóa bản thân một record hiện hữu. Mục đích chính là ngăn transaction khác chèn index entry mới vào gap đó.

Với index `code` trong dữ liệu mẫu, các giá trị hiện hữu là 10, 20 và 30. Có thể hình dung các khoảng:

```text
(-∞, 10)   10   (10, 20)   20   (20, 30)   30   (30, +∞)
```

Một truy vấn locking read tìm giá trị chưa tồn tại trong gap có thể khiến InnoDB khóa gap chứa giá trị đó ở `REPEATABLE READ`.

Session A:

```sql
SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ;
START TRANSACTION;

SELECT id, code, note
FROM lock_demo FORCE INDEX (idx_lock_demo_code)
WHERE code = 15
FOR UPDATE;
```

Truy vấn không trả về hàng nào vì chưa có `code = 15`. Tuy vậy, do đây là locking read trên nonunique index ở `REPEATABLE READ`, InnoDB có thể đặt gap lock ở khoảng chứa giá trị 15, giữa index entry 10 và 20.

Session B thử chèn vào gap:

```sql
START TRANSACTION;

INSERT INTO lock_demo (id, code, note)
VALUES (4, 15, 'fifteen');
```

INSERT có thể phải chờ gap lock do Session A đang giữ. Khi Session A `COMMIT` hoặc `ROLLBACK`, thao tác chèn ở Session B mới có thể tiếp tục.

### Gap lock không khóa record hiện hữu

Gap lock có tính chất **inhibitive**: nó ngăn chèn index entry mới vào khoảng, nhưng không phải khóa đọc/ghi trên một record hiện hữu trong khoảng vì không có record nào ở đó. Nhiều transaction có thể cùng giữ gap lock trên cùng gap; gap lock không xung đột với gap lock khác theo cách S/X record lock xung đột. Tuy nhiên, insert intention của transaction muốn chèn vào gap có thể bị chặn.

Không nên diễn giải gap lock là “khóa tất cả hàng có giá trị trong một range”. Nó khóa khoảng trống trong index. Với một truy vấn range, InnoDB thường kết hợp record lock và gap lock thành next-key lock.

Ở cuối index, InnoDB dùng một pseudo-record có tên `supremum` để biểu diễn khoảng sau index record lớn nhất. Vì vậy, chẩn đoán lock ở cuối index đôi khi hiển thị `supremum pseudo-record`; đây là mốc nội bộ biểu diễn gap, không phải một hàng dữ liệu do ứng dụng chèn.

## 5. Next-key lock: record lock cộng gap trước record

Next-key lock là tổ hợp:

```text
next-key lock = record lock trên index record + gap lock ngay trước record đó
```

Nếu index có các giá trị 10, 20 và 30, next-key lock gắn với record 20 bảo vệ record 20 và gap `(10, 20)`. Next-key lock gắn với record 30 bảo vệ record 30 và gap `(20, 30)`.

Hình dung:

```text
Gap (-∞,10)  [10]  Gap (10,20)  [20]  Gap (20,30)  [30]  Gap (30,+∞)
                    <------ next-key lock của record 20 ------>
```

Trong `REPEATABLE READ`, next-key locking được dùng phổ biến cho locking range scan để ngăn transaction khác chèn phantom row vào phạm vi đã đọc/khóa.

Ví dụ Session A:

```sql
SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ;
START TRANSACTION;

SELECT id, code, note
FROM lock_demo FORCE INDEX (idx_lock_demo_code)
WHERE code >= 10
  AND code <= 20
FOR UPDATE;
```

Truy vấn đọc các entry có `code` từ 10 đến 20 và yêu cầu khóa để cập nhật. InnoDB dùng các record/next-key lock trên index range được quét; vùng gap liên quan có thể khiến một INSERT mới trong range phải chờ. Phạm vi chính xác phụ thuộc index được chọn, điều kiện biên và cách InnoDB duyệt index; không suy ra chỉ từ số hàng được trả về.

Session B có thể thử:

```sql
START TRANSACTION;

INSERT INTO lock_demo (id, code, note)
VALUES (5, 15, 'inside range');
```

INSERT có thể bị chặn bởi gap/next-key lock của Session A. Khi A kết thúc transaction, B tiếp tục.

### Vì sao cần next-key lock?

Giả sử Session A đọc các đơn hàng có `amount` từ 100 đến 200 để tính một quyết định nghiệp vụ. Nếu transaction khác có thể chèn một hàng mới `amount = 150` trước khi A kết thúc, lần đọc sau có thể có thêm hàng trong cùng phạm vi (phantom). Next-key locking ngăn chèn vào các gap liên quan trong isolation level và loại truy vấn sử dụng nó.

Next-key lock là một cơ chế bảo vệ phantom, không phải bảo đảm rằng mọi SELECT đều khóa range. SELECT thông thường dùng consistent read của MVCC và không đặt next-key lock chỉ vì có WHERE.

## 6. Insert intention lock: ý định chèn vào gap

Trước khi chèn một index entry mới, InnoDB đặt insert intention lock trên gap nơi entry sẽ được chèn. Đây là một dạng gap lock đặc biệt, báo hiệu transaction muốn chèn tại một vị trí cụ thể.

Điểm quan trọng là insert intention lock của hai transaction muốn chèn vào **hai vị trí khác nhau** trong cùng gap có thể cùng tồn tại mà không phải chờ nhau, miễn không có gap/next-key lock khác ngăn chèn.

Giả sử index có hai giá trị 10 và 20, nên gap `(10, 20)` đang trống. Session B:

```sql
START TRANSACTION;

INSERT INTO lock_demo (id, code, note)
VALUES (6, 12, 'twelve');
```

Session C, trên connection khác:

```sql
START TRANSACTION;

INSERT INTO lock_demo (id, code, note)
VALUES (7, 18, 'eighteen');
```

Hai INSERT có thể cùng tiến hành vì chúng muốn chèn vào hai vị trí khác nhau trong gap `(10, 20)`. Mỗi transaction giữ khóa record mới của chính nó và insert intention tại vị trí cần chèn; insert intention locks không tự động chặn lẫn nhau chỉ vì cùng gap.

Nếu một transaction khác đang giữ gap lock hoặc next-key lock bao phủ `(10, 20)`, các INSERT vẫn có thể phải chờ. Insert intention không phải quyền bỏ qua gap lock.

### Insert intention khác gap lock thông thường ở đâu?

| Loại khóa | Mục đích | Ảnh hưởng tới INSERT |
|---|---|---|
| Gap lock | Ngăn chèn index entry vào gap | Có thể chặn insert intention trong gap. |
| Insert intention lock | Báo ý định chèn tại vị trí trong gap | Hai insert intention ở vị trí khác nhau có thể tương thích. |
| Next-key lock | Khóa record và gap trước record | Có thể chặn insert intention trong gap được bảo vệ. |
| Record lock | Khóa một index record hiện hữu | Chặn thao tác không tương thích trên record đó; không phải khóa gap đơn thuần. |

## 7. Bốn loại khóa trong cùng một mô hình index

Với index có các giá trị 10, 20, 30, có thể tóm tắt:

| Loại khóa | Đối tượng được bảo vệ | Tác dụng chính |
|---|---|---|
| Record lock | Một index record, ví dụ record `20` | Ngăn thao tác không tương thích trên record đó. |
| Gap lock | Khoảng giữa hai index record, ví dụ `(10, 20)` | Ngăn chèn entry mới vào gap. |
| Next-key lock | Record `20` và gap `(10, 20)` | Bảo vệ record và ngăn phantom ở gap trước nó. |
| Insert intention lock | Vị trí dự định chèn trong gap | Điều phối concurrent insert; các vị trí khác nhau có thể không chặn nhau. |

Không thể kết luận loại khóa chỉ từ câu SQL mà không biết index được dùng và isolation level. Cùng một điều kiện WHERE có thể tạo phạm vi khóa khác nhau nếu optimizer chọn index khác, nếu cột có unique constraint hoặc nếu transaction chạy ở isolation level khác.

## 8. Isolation level ảnh hưởng gap và next-key locking

### REPEATABLE READ

`REPEATABLE READ` là isolation level mặc định thường dùng của InnoDB. Trong isolation level này:

- Locking read (`FOR UPDATE`, `FOR SHARE`) và UPDATE/DELETE theo range thường sử dụng next-key locking trên index scan để ngăn phantom.
- Tìm kiếm equality trên toàn bộ unique index và tìm thấy hàng thường chỉ cần record lock.
- Tìm kiếm khóa không tồn tại hoặc tìm kiếm trên nonunique index có thể khóa gap để ngăn chèn vào vị trí đó.
- INSERT cần insert intention lock trước khi tạo index entry.

### READ COMMITTED

Ở `READ COMMITTED`, InnoDB thường tắt gap locking cho search và index scan, ngoại trừ các trường hợp cần thiết để kiểm tra foreign key và duplicate-key. Record lock vẫn được dùng để bảo vệ hàng được sửa hoặc khóa. Vì vậy, một locking range read ở READ COMMITTED thường cho phép transaction khác chèn hàng mới vào gap mà REPEATABLE READ có thể bảo vệ.

Không nên đổi sang READ COMMITTED chỉ để giảm lock wait mà chưa xem xét yêu cầu isolation và replication/configuration của hệ thống. Hãy xác minh phantom có được phép xuất hiện trong logic nghiệp vụ hay không.

### Kiểm tra isolation level hiện tại

```sql
SELECT
    @@SESSION.transaction_isolation AS session_isolation,
    @@GLOBAL.transaction_isolation AS global_isolation;
```

Một số phiên bản MySQL cũ dùng tên biến `tx_isolation`. Nếu làm việc với phiên bản cũ, kiểm tra biến phù hợp trước khi chạy truy vấn chẩn đoán.

## 9. Unique lookup và phạm vi khóa

Index unique có thể giúp giảm phạm vi khóa khi truy vấn tìm đúng một hàng bằng toàn bộ unique key.

Ví dụ:

```sql
CREATE TABLE account_lock_demo (
    account_id BIGINT UNSIGNED NOT NULL,
    email VARCHAR(254) NOT NULL,
    balance DECIMAL(12,2) NOT NULL,
    PRIMARY KEY (account_id),
    UNIQUE KEY uq_account_lock_demo_email (email)
) ENGINE=InnoDB;

SELECT account_id, balance
FROM account_lock_demo
WHERE email = 'a@example.test'
FOR UPDATE;
```

Nếu tìm thấy hàng bằng equality trên toàn bộ unique index, InnoDB thường khóa record khớp thay vì khóa gap trước record. Điều này thu hẹp phạm vi khóa so với tìm kiếm range hoặc nonunique key.

Các trường hợp không tương đương:

- `WHERE email LIKE 'a%'` là range/prefix search, không phải unique equality lookup.
- Với unique index ghép `(tenant_id, email)`, điều kiện chỉ có `email = ...` chưa chỉ rõ toàn bộ unique key.
- Nếu unique key không tìm thấy hàng, InnoDB có thể khóa gap tại vị trí cần bảo vệ, tùy isolation level và loại truy vấn.
- Nếu optimizer không dùng unique index, phạm vi khóa có thể khác dự kiến.

Thiết kế unique index đúng nghiệp vụ vừa bảo vệ tính duy nhất, vừa giúp optimizer và InnoDB có cơ hội dùng lookup hẹp hơn.

## 10. Index và phạm vi khóa thực tế

Phạm vi khóa phụ thuộc index record mà execution plan quét, không chỉ các hàng cuối cùng thỏa WHERE. Hãy so sánh hai truy vấn:

```sql
EXPLAIN
SELECT id, code, note
FROM lock_demo
WHERE code = 15
FOR UPDATE;

EXPLAIN
SELECT id, code, note
FROM lock_demo IGNORE INDEX (idx_lock_demo_code)
WHERE code = 15
FOR UPDATE;
```

Truy vấn thứ nhất có thể dùng secondary index `idx_lock_demo_code`; truy vấn thứ hai yêu cầu optimizer bỏ qua index đó và có thể quét clustered index. Khi quét nhiều index record hơn, số record/gap có thể bị khóa cũng có thể tăng.

Không nên chạy truy vấn `IGNORE INDEX` trên bảng production chỉ để thử. Ví dụ này dùng để giải thích vì sao index và access path ảnh hưởng khóa. Hãy kiểm tra bằng `EXPLAIN` trên môi trường thử nghiệm.

### Điều kiện không sargable

Điều kiện bọc hàm hoặc ép kiểu trên cột có thể khiến index không được dùng như mong muốn:

```sql
-- Thân thiện với index thông thường hơn
SELECT *
FROM lock_demo
WHERE code = 15
FOR UPDATE;

-- Có thể làm mất khả năng range/ref lookup trên index code
SELECT *
FROM lock_demo
WHERE CAST(code AS CHAR) = '15'
FOR UPDATE;
```

Nếu optimizer phải quét nhiều record hơn, phạm vi lock và thời gian giữ lock có thể tăng. Hãy chuẩn hóa kiểu dữ liệu và tránh biểu thức không cần thiết trên cột tìm kiếm.

## 11. Gap lock có thể xuất hiện dù SELECT không trả hàng

Một điểm dễ gây nhầm lẫn là truy vấn trả về 0 hàng nhưng vẫn giữ lock. Ví dụ:

```sql
START TRANSACTION;

SELECT id, code
FROM lock_demo FORCE INDEX (idx_lock_demo_code)
WHERE code = 15
FOR UPDATE;
```

Nếu không có `code = 15`, kết quả rỗng. Nhưng ở REPEATABLE READ với nonunique index, InnoDB vẫn có thể khóa gap chứa 15. Transaction khác chèn `code = 15` sẽ chờ cho đến khi transaction đọc kết thúc.

Điều này không mâu thuẫn: locking read bảo vệ điều kiện tìm kiếm, không chỉ các hàng đã trả về. Nếu không khóa gap, một transaction khác có thể chèn hàng thỏa điều kiện vào giữa transaction hiện tại và tạo phantom.

Không dùng số hàng trả về để suy luận số lock đang được giữ. Hãy kiểm tra `performance_schema.data_locks` hoặc InnoDB status.

## 12. Foreign key và duplicate-key check

Ngay cả ở `READ COMMITTED`, InnoDB vẫn có thể sử dụng gap locking trong một số trường hợp cần thiết cho kiểm tra ràng buộc, đặc biệt là:

- Kiểm tra foreign key khi thêm hoặc thay đổi hàng con.
- Kiểm tra duplicate-key khi INSERT/UPDATE trên unique index.

Vì vậy, phát biểu “READ COMMITTED không có gap lock” là quá tuyệt đối. Cách diễn đạt chính xác là gap locking cho search/index scan thông thường bị tắt ở READ COMMITTED, ngoại trừ các trường hợp phục vụ kiểm tra foreign key và duplicate-key.

Khi điều tra lock wait ở READ COMMITTED, hãy xem cả thao tác DML và constraint của bảng, không chỉ SELECT ... FOR UPDATE.

## 13. Thực nghiệm insert intention lock

Để quan sát hai INSERT ở vị trí khác nhau trong cùng gap, cần trạng thái ban đầu có `code` 10 và 20, không có gap lock từ transaction khác. Sau khi bảo đảm mọi transaction thử nghiệm trước đã kết thúc, làm sạch các hàng được chèn trong các ví dụ trước:

```sql
DELETE FROM lock_demo
WHERE id IN (4, 5, 6, 7, 8, 9);
```

Giữ lại các hàng gốc có `code` 10, 20 và 30; gap `(10, 20)` trở lại trống.

Session B:

```sql
START TRANSACTION;

INSERT INTO lock_demo (id, code, note)
VALUES (8, 12, 'insert at twelve');
```

Giữ transaction B mở. Session C:

```sql
START TRANSACTION;

INSERT INTO lock_demo (id, code, note)
VALUES (9, 18, 'insert at eighteen');
```

Hai INSERT vào hai vị trí khác nhau trong gap `(10, 20)` có thể cùng hoàn tất mà không chờ nhau. Commit cả hai:

```sql
COMMIT;
```

Chạy ở từng session tương ứng. Nếu một transaction trước đó đã giữ gap lock bao phủ khoảng này, kết quả sẽ khác: các INSERT phải chờ gap lock được giải phóng.

### Kiểm tra thứ tự chèn và index entry

```sql
SELECT id, code, note
FROM lock_demo FORCE INDEX (idx_lock_demo_code)
ORDER BY code, id;
```

Các giá trị 12 và 18 được đặt giữa 10 và 20. Insert intention lock giúp các thao tác chèn khác vị trí không chặn nhau một cách không cần thiết; record lock trên các entry mới vẫn bảo vệ chính hàng vừa chèn.

## 14. Lock wait, deadlock và cách giải quyết

Lock wait xảy ra khi transaction cần một lock không tương thích với lock đang được transaction khác giữ. Transaction chờ có thể tiếp tục khi blocker commit/rollback hoặc thất bại khi vượt `innodb_lock_wait_timeout`.

Deadlock xảy ra khi các transaction tạo thành vòng chờ. Ví dụ:

```text
Transaction A giữ lock hàng 1, chờ hàng 2
Transaction B giữ lock hàng 2, chờ hàng 1

A ---- waits for ----> B
^                     |
|                     v
<---- waits for ------
```

Ví dụ hai session:

Session A:

```sql
START TRANSACTION;

UPDATE lock_demo
SET note = 'A updates row 1'
WHERE id = 1;
```

Session B:

```sql
START TRANSACTION;

UPDATE lock_demo
SET note = 'B updates row 2'
WHERE id = 2;
```

Sau đó Session A:

```sql
UPDATE lock_demo
SET note = 'A updates row 2'
WHERE id = 2;
```

Session A phải chờ B. Tiếp theo Session B:

```sql
UPDATE lock_demo
SET note = 'B updates row 1'
WHERE id = 1;
```

Lúc này có vòng chờ. InnoDB phát hiện deadlock và chọn một transaction làm nạn nhân để rollback; transaction còn lại có thể tiếp tục. Ứng dụng phải bắt lỗi deadlock và retry toàn bộ transaction theo chính sách có giới hạn, vì transaction bị chọn làm nạn nhân đã bị rollback.

### Lock wait timeout khác deadlock

| Tình huống | Ý nghĩa | Xử lý |
|---|---|---|
| Lock wait timeout (thường lỗi 1205) | Chờ lock quá thời gian cấu hình | Xác định blocker, giảm thời gian giữ lock và retry có kiểm soát nếu phù hợp. Mặc định InnoDB thường rollback statement bị timeout, không nhất thiết rollback toàn transaction. |
| Deadlock (thường lỗi 1213) | Có vòng chờ giữa transaction | InnoDB rollback toàn bộ transaction được chọn làm nạn nhân; ứng dụng retry toàn bộ transaction. |

Không retry vô hạn. Dùng backoff ngẫu nhiên, giới hạn số lần thử và bảo đảm thao tác có tính idempotent hoặc được bảo vệ bằng khóa nghiệp vụ.

## 15. Chẩn đoán khóa bằng Performance Schema

Trên MySQL 8.0, `performance_schema.data_locks` hiển thị các lock đang tồn tại và `performance_schema.data_lock_waits` liên kết lock đang chờ với lock đang chặn.

Liệt kê lock:

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
  AND OBJECT_NAME = 'lock_demo'
ORDER BY ENGINE_TRANSACTION_ID, INDEX_NAME;
```

Các cột hữu ích:

- `INDEX_NAME`: index đang được khóa; NULL có thể xuất hiện tùy loại lock.
- `LOCK_TYPE`: loại đối tượng khóa, ví dụ TABLE hoặc RECORD.
- `LOCK_MODE`: chế độ và thuộc tính lock; có thể thấy các dạng như `X`, `S`, `X,GAP`, `X,REC_NOT_GAP`, hoặc mode có `INSERT_INTENTION`.
- `LOCK_STATUS`: trạng thái như GRANTED hoặc WAITING.
- `LOCK_DATA`: thông tin index key được khóa nếu có thể hiển thị.

Giá trị mode cụ thể có thể khác theo phiên bản và trường hợp. Đọc `LOCK_MODE` cùng `INDEX_NAME`, `LOCK_TYPE`, `LOCK_STATUS` và lock wait graph, không chỉ dựa vào một chuỗi mode.

### Xem transaction đang chờ và transaction đang chặn

```sql
SELECT
    waiting.ENGINE_TRANSACTION_ID AS waiting_trx,
    waiting.THREAD_ID AS waiting_thread,
    waiting.OBJECT_SCHEMA,
    waiting.OBJECT_NAME,
    waiting.INDEX_NAME,
    waiting.LOCK_MODE AS waiting_lock_mode,
    blocking.ENGINE_TRANSACTION_ID AS blocking_trx,
    blocking.THREAD_ID AS blocking_thread,
    blocking.LOCK_MODE AS blocking_lock_mode,
    blocking.LOCK_DATA AS blocking_lock_data
FROM performance_schema.data_lock_waits AS waits
JOIN performance_schema.data_locks AS waiting
  ON waiting.ENGINE = waits.ENGINE
 AND waiting.ENGINE_LOCK_ID = waits.REQUESTING_ENGINE_LOCK_ID
JOIN performance_schema.data_locks AS blocking
  ON blocking.ENGINE = waits.ENGINE
 AND blocking.ENGINE_LOCK_ID = waits.BLOCKING_ENGINE_LOCK_ID;
```

Từ `THREAD_ID`, có thể liên hệ với `performance_schema.threads` hoặc `events_statements_current` để tìm connection và statement đang chạy, tùy quyền truy cập và instrumentation được bật.

### SHOW ENGINE INNODB STATUS

```sql
SHOW ENGINE INNODB STATUS;
```

Phần `LATEST DETECTED DEADLOCK` cung cấp thông tin deadlock gần nhất mà InnoDB ghi nhận, bao gồm transaction, câu lệnh và lock liên quan. Phần TRANSACTIONS giúp xem transaction đang hoạt động và trạng thái lock. Đây là ảnh chụp chẩn đoán tại thời điểm truy vấn, không phải lịch sử đầy đủ của mọi lock wait.

## 16. Giảm phạm vi khóa trong thiết kế truy vấn

Một số thực hành giúp hạn chế lock contention:

1. Dùng primary key hoặc unique key khi nghiệp vụ cho phép tìm một hàng duy nhất.
2. Tạo index theo điều kiện JOIN/WHERE và thứ tự truy cập thực tế.
3. Tránh range scan rộng trong transaction ghi nếu chỉ cần một nhóm hàng nhỏ.
4. Chỉ khóa những hàng cần cập nhật; tránh `SELECT ... FOR UPDATE` trên tập quá rộng.
5. Giữ transaction ngắn; không gọi API, chờ người dùng hoặc xử lý file trong lúc giữ lock.
6. Cập nhật nhiều hàng theo cùng thứ tự khóa giữa các transaction để giảm khả năng deadlock.
7. Không dùng `LOCK TABLES` để thay thế thiết kế row/index locking nếu không có lý do đặc biệt.
8. Kiểm tra execution plan vì thay đổi index hoặc thống kê có thể làm phạm vi scan và lock thay đổi.

Ví dụ truy vấn hẹp theo unique key:

```sql
START TRANSACTION;

SELECT account_id, balance
FROM account_lock_demo
WHERE email = 'a@example.test'
FOR UPDATE;

UPDATE account_lock_demo
SET balance = balance - 10.00
WHERE email = 'a@example.test';

COMMIT;
```

Vì `email` có unique index, lookup có thể khóa một record nếu tìm thấy chính xác một hàng. Nếu nghiệp vụ có account ID, dùng primary key trực tiếp thường còn rõ ràng hơn. Hãy bảo đảm điều kiện UPDATE khớp đúng hàng đã khóa.

## 17. Quy trình điều tra một INSERT bị chặn

Khi INSERT bị chờ dù không sửa cùng hàng với transaction khác, hãy kiểm tra theo trình tự:

1. Xác định bảng, index và giá trị khóa mà INSERT muốn tạo.
2. Xác định gap trong index nơi giá trị mới sẽ được đặt.
3. Kiểm tra `performance_schema.data_lock_waits` để tìm transaction blocker.
4. Xem `data_locks` để xác định lock mode, index name và lock data.
5. Kiểm tra isolation level của transaction đang giữ lock.
6. Tìm locking read, UPDATE hoặc DELETE theo range đã chạy trước đó.
7. Kiểm tra execution plan và index thực tế được dùng.
8. Xác định lock là record, gap, next-key hay insert intention.
9. Kết thúc hoặc điều chỉnh transaction blocker theo nghiệp vụ.
10. Thiết kế lại index/điều kiện để thu hẹp phạm vi nếu cần.

Một INSERT chờ gap lock không nhất thiết là lỗi của INSERT. Có thể transaction trước đó đang bảo vệ một range để ngăn phantom. Điều tra phải bắt đầu từ transaction giữ lock và lý do nó cần bảo vệ khoảng đó.

## 18. Những lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Nghĩ record lock khóa một dòng logic bất kể index | Bỏ qua lock trên secondary/clustered index record | Xem `INDEX_NAME` và access path. |
| Nghĩ gap lock khóa các record hiện hữu | Hiểu sai phạm vi và xung đột | Gap lock bảo vệ khoảng trống để ngăn insert. |
| Nghĩ gap lock xung đột với mọi gap lock khác | Dự đoán sai khả năng cùng giữ gap lock | Gap locks mang tính inhibitive và có thể cùng tồn tại; insert intention có thể bị chặn. |
| Nghĩ next-key lock chỉ là record lock | Bỏ qua gap trước record và phantom protection | Nhớ next-key = record + gap trước record. |
| Nghĩ INSERT chỉ cần record lock mới | Không hiểu insert intention và lock wait trên gap | Xem gap chứa vị trí chèn và các blocker. |
| Nghĩ hai INSERT cùng gap luôn chặn nhau | Giảm concurrency không cần thiết | Insert intention ở vị trí khác nhau có thể tương thích nếu không có gap lock chặn. |
| Nghĩ SELECT không trả hàng thì không có lock | Bỏ sót gap lock của locking read | Kiểm tra data_locks dù result set rỗng. |
| Nghĩ READ COMMITTED tuyệt đối không gap lock | Bỏ sót FK và duplicate-key checks | Nhớ các ngoại lệ của constraint checking. |
| Dùng index không phù hợp hoặc không có index | Scan/lock phạm vi lớn, tăng wait | Thiết kế index và kiểm tra EXPLAIN. |
| Dùng DISTINCT hoặc sửa dữ liệu để né lock wait | Che triệu chứng nhưng không sửa nguyên nhân | Tìm transaction blocker, range và access path. |
| Retry deadlock như retry lock timeout | Có thể tiếp tục với transaction đã rollback hoặc trạng thái sai | Với deadlock, retry toàn bộ transaction; với timeout, kiểm tra transaction state. |

## 19. Bài tập thực hành

### Bài tập A — Record lock

1. Tạo bảng `lock_demo` và nạp ba hàng.
2. Session A chạy `SELECT ... WHERE id = 2 FOR UPDATE`.
3. Session B UPDATE cùng `id = 2`.
4. Quan sát Session B chờ.
5. Commit Session A và ghi lại thời điểm Session B tiếp tục.

### Bài tập B — Gap lock

1. Đặt cả hai session ở `REPEATABLE READ`.
2. Session A tìm `code = 15 FOR UPDATE` khi giá trị này chưa tồn tại.
3. Session B INSERT `code = 15`.
4. Quan sát lock wait dù SELECT của A trả 0 hàng.
5. Commit/rollback A và xác nhận INSERT tiếp tục.

### Bài tập C — Next-key lock

1. Session A chạy locking range read `code BETWEEN 10 AND 20`.
2. Session B thử INSERT một giá trị nằm trong range.
3. Thử INSERT ngoài range.
4. Quan sát phạm vi chặn bằng `data_locks`.
5. Thay đổi index hoặc isolation level trong môi trường thử nghiệm và so sánh.

### Bài tập D — Insert intention lock

1. Bảo đảm gap `(10, 20)` không bị gap lock.
2. Session B INSERT code 12 nhưng chưa commit.
3. Session C INSERT code 18.
4. Quan sát hai INSERT có thể cùng tiến hành.
5. Lặp lại khi Session A giữ gap lock và giải thích vì sao kết quả thay đổi.

### Bài tập E — Chẩn đoán deadlock và lock wait

1. Tạo deadlock bằng hai transaction cập nhật hai hàng theo thứ tự ngược nhau.
2. Đọc `SHOW ENGINE INNODB STATUS`.
3. Tạo lock wait do gap lock và truy vấn `performance_schema.data_lock_waits`.
4. Ghi lại blocker, waiter, index và lock mode.
5. Đề xuất thứ tự cập nhật thống nhất và chiến lược retry có giới hạn.

Bạn hoàn thành bài khi có thể phân biệt bốn loại khóa, dự đoán khi nào INSERT bị chặn, giải thích vai trò của index và isolation level, đồng thời tìm được transaction giữ lock bằng công cụ chẩn đoán của MySQL.

## 20. Nguyên tắc cần ghi nhớ

- InnoDB khóa index record và gap; index/access path ảnh hưởng trực tiếp phạm vi lock.
- Record lock khóa một index record cụ thể.
- Gap lock bảo vệ khoảng trống giữa index record để ngăn chèn mới; nó mang tính inhibitive.
- Next-key lock = record lock cộng gap ngay trước record.
- Insert intention lock báo ý định chèn vào gap; hai insert ở vị trí khác nhau có thể không chặn nhau.
- Locking read và DML range trong REPEATABLE READ thường dùng next-key locking để ngăn phantom.
- Equality lookup trên toàn bộ unique index khi tìm thấy hàng thường chỉ khóa record; range/nonunique/missing-key lookup có thể cần gap lock.
- READ COMMITTED tắt phần lớn gap locking cho search/index scan thông thường, nhưng vẫn có ngoại lệ cho foreign key và duplicate-key checks.
- Một locking read trả 0 hàng vẫn có thể giữ gap lock.
- Không suy ra lock scope chỉ từ WHERE hoặc số hàng trả về; kiểm tra execution plan và `performance_schema.data_locks`.
- Deadlock thường làm rollback toàn bộ transaction được chọn; lock wait timeout mặc định thường chỉ rollback statement bị timeout.
- Giữ transaction ngắn, dùng index phù hợp, cập nhật theo thứ tự nhất quán và retry có giới hạn.

Khi hiểu record, gap, next-key và insert intention lock như các khóa trên index, bạn có thể giải thích chính xác vì sao một thao tác bị chặn, dự đoán tác động của range scan và thiết kế truy vấn có phạm vi khóa nhỏ hơn. Đây là nền tảng để giảm lock contention và xử lý concurrency trong InnoDB.
