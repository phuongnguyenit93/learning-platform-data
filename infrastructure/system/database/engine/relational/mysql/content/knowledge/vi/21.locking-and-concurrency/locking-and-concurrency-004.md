# Truy vấn điểm theo khóa duy nhất so với truy vấn theo khoảng

Trong InnoDB, hai câu truy vấn có thể trả về số hàng gần giống nhau nhưng tạo ra phạm vi khóa rất khác nhau. Một truy vấn điểm dùng đầy đủ khóa duy nhất thường chỉ cần khóa bản ghi được tìm thấy. Một truy vấn theo khoảng có thể khóa cả các khoảng trống giữa những bản ghi trong chỉ mục để ngăn transaction khác chèn hàng mới vào phạm vi đang được bảo vệ.

Sự khác biệt này ảnh hưởng trực tiếp đến khả năng chạy đồng thời. Truy vấn điểm thường có phạm vi khóa hẹp và dễ dự đoán. Truy vấn phạm vi hữu ích khi cần bảo vệ một tập hàng hoặc một khoảng giá trị, nhưng có thể khiến thao tác chèn hay cập nhật của phiên khác phải chờ. Muốn hiểu đúng phạm vi khóa, cần xét cả điều kiện truy vấn, chỉ mục mà bộ tối ưu chọn, mức cô lập và loại câu lệnh đọc.

## Mục tiêu

Sau bài học, bạn có thể:

- Phân biệt record lock, gap lock và next-key lock của InnoDB.
- Giải thích vì sao phép tìm kiếm bằng đầy đủ khóa duy nhất thường khóa hẹp hơn truy vấn theo khoảng.
- Dự đoán ảnh hưởng của truy vấn phạm vi đến thao tác chèn và cập nhật đồng thời.
- Nhận biết tác động của chỉ mục ghép, chỉ mục không duy nhất và kế hoạch thực thi đến phạm vi khóa.
- So sánh hành vi khóa ở `REPEATABLE READ` và `READ COMMITTED`.
- Quan sát khóa đang giữ và điều chỉnh truy vấn để giảm tranh chấp.

Các ví dụ giả định MySQL 8.0 trở lên và bảng dùng storage engine InnoDB.

## 1. Khóa InnoDB gắn với chỉ mục

InnoDB tổ chức dữ liệu theo clustered index. Khóa bản ghi của InnoDB được đặt trên các bản ghi chỉ mục, chứ không phải một đối tượng trừu tượng tách rời khỏi chỉ mục. Nếu truy vấn dùng secondary index, InnoDB có thể cần khóa cả bản ghi secondary index và bản ghi tương ứng trong clustered index để bảo vệ hàng dữ liệu.

Ba khái niệm cần phân biệt:

- **Record lock:** khóa một bản ghi chỉ mục cụ thể. Khóa này bảo vệ hàng tương ứng khỏi thao tác xung đột.
- **Gap lock:** khóa một khoảng trống giữa các giá trị chỉ mục. Nó ngăn transaction khác chèn bản ghi vào khoảng đó, nhưng bản thân gap lock không khóa một bản ghi dữ liệu đã tồn tại.
- **Next-key lock:** kết hợp record lock với gap lock ở phía trước bản ghi chỉ mục. Đây là cơ chế InnoDB thường dùng cho tìm kiếm hoặc quét phạm vi ở `REPEATABLE READ` để bảo vệ cả bản ghi và khoảng liên quan.

Ví dụ, chỉ mục có các giá trị `10`, `20`, `30`. Các khoảng trống có thể hình dung là:

```text
(-∞, 10)   10   (10, 20)   20   (20, 30)   30   (30, +∞)
```

Record lock trên `20` bảo vệ bản ghi chỉ mục mang giá trị `20`. Gap lock trên `(10, 20)` bảo vệ khoảng trống trước `20`. Next-key lock gắn với `20` bao gồm bản ghi `20` và khoảng trống ngay trước nó. Đây là mô hình giúp hiểu phạm vi; phạm vi thực tế phụ thuộc thứ tự chỉ mục và những bản ghi mà kế hoạch truy cập quét qua.

## 2. Truy vấn điểm bằng đầy đủ khóa duy nhất

Giả sử bảng đơn hàng có khóa chính `order_id` và mã tham chiếu ngoài được bảo đảm duy nhất:

```sql
CREATE TABLE orders (
    order_id BIGINT UNSIGNED NOT NULL,
    external_ref VARCHAR(64) NOT NULL,
    customer_id BIGINT UNSIGNED NOT NULL,
    status VARCHAR(20) NOT NULL,
    created_at DATETIME NOT NULL,
    PRIMARY KEY (order_id),
    UNIQUE KEY uq_orders_external_ref (external_ref),
    KEY ix_orders_status_created (status, created_at)
) ENGINE = InnoDB;
```

Khi một transaction cần khóa một đơn hàng đã tồn tại theo `external_ref`, nó có thể dùng:

```sql
START TRANSACTION;

SELECT order_id, status
FROM orders
WHERE external_ref = 'EXT-2026-001'
FOR UPDATE;

-- Kiểm tra và xử lý đơn hàng trong cùng transaction.
COMMIT;
```

Điều kiện trên dùng phép so sánh bằng với toàn bộ khóa của một unique index. Nếu bản ghi tồn tại và bộ tối ưu dùng chỉ mục duy nhất đó, InnoDB dùng record lock cho hàng được tìm thấy, không cần khóa khoảng trống ngay trước bản ghi như trường hợp next-key lock thông thường. Với unique secondary index, engine có thể cần khóa cả bản ghi secondary index và bản ghi tương ứng trong clustered index. Phạm vi khóa vì vậy thường hẹp và ít ảnh hưởng đến thao tác chèn các mã tham chiếu khác.

`FOR UPDATE` cần nằm trong transaction nếu ứng dụng muốn giữ khóa qua nhiều câu lệnh. Khi `autocommit = 1` và không mở transaction tường minh, transaction của câu lệnh kết thúc ngay sau câu `SELECT`, nên khóa được nhả khi câu lệnh hoàn tất:

```sql
START TRANSACTION;
SELECT order_id
FROM orders
WHERE external_ref = 'EXT-2026-001'
FOR UPDATE;

-- Thực hiện bước kiểm tra/cập nhật cần bảo vệ.
COMMIT;
```

Quy tắc này chỉ áp dụng khi điều kiện xác định đầy đủ một giá trị duy nhất. Ví dụ, với unique index ghép `(tenant_id, external_ref)`, truy vấn điểm cần chỉ rõ cả hai cột:

```sql
SELECT order_id
FROM tenant_orders
WHERE tenant_id = 7
  AND external_ref = 'EXT-2026-001'
FOR UPDATE;
```

Nếu chỉ lọc `tenant_id = 7`, điều kiện chưa xác định một hàng duy nhất; đó là một phép tìm kiếm trên một phần khóa ghép và có thể quét, khóa nhiều bản ghi hoặc khoảng chỉ mục.

Một số trường hợp làm truy vấn không còn là unique point lookup:

- Chỉ cung cấp một phần cột của unique index ghép.
- Dùng điều kiện phạm vi như `>`, `>=`, `<`, `BETWEEN` hoặc tìm kiếm tiền tố.
- Dùng cột không duy nhất, dù điều kiện là `=`.
- Viết biểu thức hoặc chuyển kiểu khiến bộ tối ưu không dùng được unique index như dự kiến.
- Kế hoạch thực thi chọn một đường truy cập khác thay vì unique index.

Nếu khóa duy nhất không tìm thấy hàng, không có record hiện hữu để khóa. Trong `REPEATABLE READ`, phép tìm kiếm có thể bảo vệ vị trí trống bằng gap lock tùy câu lệnh và đường truy cập. Vì vậy, không nên suy rộng quy tắc “unique lookup chỉ khóa bản ghi” sang trường hợp khóa không tồn tại; ví dụ ở trên giả định đơn hàng đã tồn tại.

## 3. Truy vấn theo khoảng

Giả sử ứng dụng cần xử lý các đơn hàng đang chờ được tạo trong một khoảng thời gian:

```sql
START TRANSACTION;

SELECT order_id, created_at
FROM orders
WHERE status = 'PENDING'
  AND created_at >= '2026-11-01 00:00:00'
  AND created_at <  '2026-11-08 00:00:00'
ORDER BY created_at, order_id
FOR UPDATE;

-- Xử lý các đơn hàng đã khóa.
COMMIT;
```

Chỉ mục `(status, created_at)` giúp InnoDB định vị các hàng theo trạng thái rồi quét khoảng thời gian trong nhóm trạng thái đó. Ở `REPEATABLE READ`, locking read theo phạm vi thường dùng next-key lock trên các bản ghi chỉ mục được quét và những khoảng liên quan. Điều này bảo vệ tập dữ liệu đang xử lý khỏi một số thao tác chèn phantom trong phạm vi khóa.

Ví dụ, transaction khác muốn chèn đơn hàng mới có `status = 'PENDING'` và `created_at` nằm giữa ngày 1 và ngày 7 tháng 11 có thể phải chờ nếu vị trí chèn nằm trong gap đang bị khóa. Một thao tác chèn nằm ngoài khoảng đó thường không bị cùng phạm vi khóa cản trở. Ranh giới cụ thể phụ thuộc chỉ mục và kế hoạch thực thi.

Truy vấn phạm vi không nhất thiết trả về nhiều hàng mới tạo ra phạm vi khóa rộng. Một điều kiện chỉ khớp một vài hàng vẫn có thể quét một vùng chỉ mục lớn nếu điều kiện không phù hợp với chỉ mục. Ngược lại, một chỉ mục ghép phù hợp có thể thu hẹp đáng kể vùng quét và khóa.

## 4. So sánh phạm vi khóa

| Kiểu truy vấn | Ví dụ điều kiện | Hành vi thường gặp ở InnoDB `REPEATABLE READ` | Tác động đồng thời |
|---|---|---|---|
| Điểm theo khóa chính | `order_id = 100` | Record lock trên hàng tìm thấy | Transaction khác cập nhật/xóa cùng hàng phải chờ; hàng khác thường vẫn xử lý được |
| Điểm theo unique index | `external_ref = 'EXT-1'` | Record lock trên bản ghi tìm thấy nếu dùng đầy đủ unique key | Thường không chặn insert vào gap trước bản ghi đó |
| Bằng trên chỉ mục không duy nhất | `status = 'PENDING'` | Có thể khóa các bản ghi trùng giá trị và gap liên quan | Insert thêm hàng có cùng giá trị có thể phải chờ |
| Phạm vi trên chỉ mục | `created_at >= a AND created_at < b` | Thường dùng next-key lock trên vùng chỉ mục được quét | Insert trong vùng có thể phải chờ |
| Không có chỉ mục phù hợp | Lọc trên cột không được lập chỉ mục | Có thể quét và khóa phạm vi rất rộng | Nhiều transaction không liên quan có thể bị ảnh hưởng |

Bảng mô tả xu hướng phổ biến, không phải cam kết số lượng lock cố định cho mọi câu lệnh. Cần xem execution plan, chỉ mục thực tế và mức cô lập để kết luận.

## 5. Quan sát hai phiên làm việc

### Trường hợp A: khóa điểm trên unique index

Giả sử mã `EXT-2026-001` đã tồn tại.

**Phiên A**

```sql
START TRANSACTION;

SELECT order_id
FROM orders
WHERE external_ref = 'EXT-2026-001'
FOR UPDATE;
```

**Phiên B** có thể cập nhật một đơn hàng khác:

```sql
UPDATE orders
SET status = 'CANCELLED'
WHERE external_ref = 'EXT-2026-002';
```

Nếu hai truy vấn định vị hai hàng khác nhau và không có ràng buộc hoặc khóa khác xung đột, phiên B không cần chờ khóa hàng mà A đang giữ. Nếu B cập nhật chính `EXT-2026-001`, B phải chờ A kết thúc transaction.

### Trường hợp B: khóa phạm vi trên chỉ mục ghép

**Phiên A** giữ khóa các đơn hàng đang chờ trong khoảng ngày:

```sql
START TRANSACTION;

SELECT order_id
FROM orders
WHERE status = 'PENDING'
  AND created_at >= '2026-11-01 00:00:00'
  AND created_at <  '2026-11-08 00:00:00'
FOR UPDATE;
```

**Phiên B** thử chèn một đơn hàng mới thỏa điều kiện phạm vi:

```sql
INSERT INTO orders
    (order_id, external_ref, customer_id, status, created_at)
VALUES
    (9001, 'EXT-2026-9001', 77, 'PENDING', '2026-11-04 10:30:00');
```

Ở `REPEATABLE READ`, nếu kế hoạch của A quét và khóa đúng khoảng chỉ mục tương ứng, thao tác chèn của B có thể phải chờ gap/next-key lock. Sau khi A `COMMIT` hoặc `ROLLBACK`, B mới có thể tiếp tục. Hãy thử lại với thời điểm nằm ngoài khoảng để quan sát sự khác biệt.

Khi thử nghiệm, mở hai kết nối MySQL độc lập. Không chạy A và B trong cùng một session vì một session chỉ có một transaction hiện hành.

## 6. Mức cô lập thay đổi hành vi khóa phạm vi

InnoDB mặc định dùng `REPEATABLE READ`. Ở mức này, gap lock và next-key lock được dùng cho nhiều phép tìm kiếm hoặc quét chỉ mục để ngăn phantom trong các thao tác khóa.

Ở `READ COMMITTED`, InnoDB thường tắt gap locking cho tìm kiếm và quét chỉ mục. Khi đó, các thao tác đọc khóa chủ yếu khóa bản ghi chỉ mục; gap lock vẫn có thể xuất hiện cho mục đích kiểm tra khóa ngoại và kiểm tra khóa trùng. Một số record lock trên hàng không thỏa điều kiện có thể được nhả sau khi MySQL đánh giá điều kiện `WHERE`.

| Đặc điểm | `REPEATABLE READ` | `READ COMMITTED` |
|---|---|---|
| Consistent read | Dùng cùng read view trong transaction | Tạo read view mới cho mỗi câu lệnh đọc nhất quán |
| Gap/next-key lock cho range search | Được dùng phổ biến để ngăn phantom | Thường không dùng cho tìm kiếm/quét thông thường |
| Kiểm tra khóa ngoại và khóa trùng | Có khóa cần thiết | Vẫn có thể dùng gap lock trong các trường hợp này |
| Phantom giữa hai lần đọc | Snapshot nhất quán cho consistent read; locking read dùng khóa phạm vi | Có thể thấy hàng commit mới ở câu lệnh tiếp theo |

Không nên hạ mức cô lập chỉ để tránh chờ khóa mà chưa kiểm tra yêu cầu nghiệp vụ. Nếu nghiệp vụ phụ thuộc vào việc không có hàng mới xuất hiện trong một phạm vi cho đến khi transaction hoàn tất, cần chọn cơ chế bảo vệ phù hợp.

## 7. Execution plan quyết định phạm vi quét

Điều kiện `WHERE` mô tả hàng cần tìm, còn execution plan cho biết InnoDB tiếp cận dữ liệu bằng chỉ mục nào và phải quét bao nhiêu bản ghi. Phạm vi khóa gắn với đường truy cập thực tế.

Ví dụ, chỉ mục ghép `(status, created_at)` phù hợp với điều kiện:

```sql
WHERE status = 'PENDING'
  AND created_at >= '2026-11-01'
  AND created_at <  '2026-11-08'
```

Thứ tự cột trong chỉ mục có ý nghĩa. Nếu chỉ có index `(status, created_at)`, truy vấn chỉ lọc `created_at` mà không có điều kiện trên `status` có thể không tận dụng tốt phần đầu chỉ mục. Khi đó, engine có thể phải quét nhiều bản ghi hơn.

Hãy kiểm tra kế hoạch trước khi dùng locking read trên bảng lớn:

```sql
EXPLAIN
SELECT order_id
FROM orders
WHERE status = 'PENDING'
  AND created_at >= '2026-11-01 00:00:00'
  AND created_at <  '2026-11-08 00:00:00'
FOR UPDATE;
```

Chú ý các cột `type`, `key`, `key_len`, `rows` và `Extra`. `key` cho biết chỉ mục được chọn; `rows` là ước lượng số hàng cần đọc, không phải số hàng chắc chắn bị khóa. Nếu thấy `type = ALL` trên bảng lớn, truy vấn có thể phải quét rất nhiều bản ghi. Sau khi thêm hoặc thay đổi chỉ mục, chạy lại `EXPLAIN` để xác nhận đường truy cập.

Một số nguyên tắc thiết kế:

1. Dùng khóa chính hoặc unique index cho thao tác cần khóa một thực thể cụ thể.
2. Với truy vấn theo khoảng, tạo composite index theo thứ tự cột phù hợp với điều kiện lọc và thứ tự sắp xếp.
3. Tránh bọc cột tìm kiếm trong hàm nếu việc đó khiến chỉ mục không được sử dụng; nếu cần, cân nhắc cột sinh hoặc chỉ mục phù hợp.
4. Chỉ dùng `FOR UPDATE` khi cần bảo vệ dữ liệu cho bước ghi tiếp theo; truy vấn báo cáo thường nên dùng consistent read.
5. Giữ transaction ngắn để nhả record/gap lock sớm.

## 8. Xem khóa đang giữ và transaction đang chờ

MySQL 8.0 cung cấp thông tin khóa InnoDB trong Performance Schema. Có thể xem các khóa của schema hiện tại bằng:

```sql
SELECT OBJECT_SCHEMA,
       OBJECT_NAME,
       INDEX_NAME,
       LOCK_TYPE,
       LOCK_MODE,
       LOCK_STATUS,
       LOCK_DATA
FROM performance_schema.data_locks
WHERE OBJECT_SCHEMA = DATABASE();
```

Để xem quan hệ giữa transaction đang chờ và transaction chặn nó:

```sql
SELECT waiting.ENGINE_TRANSACTION_ID AS waiting_trx,
       waiting.OBJECT_NAME,
       waiting.INDEX_NAME,
       waiting.LOCK_MODE AS waiting_lock_mode,
       blocking.ENGINE_TRANSACTION_ID AS blocking_trx,
       blocking.LOCK_MODE AS blocking_lock_mode
FROM performance_schema.data_lock_waits AS waits
JOIN performance_schema.data_locks AS waiting
  ON waiting.ENGINE = waits.ENGINE
 AND waiting.ENGINE_LOCK_ID = waits.REQUESTING_ENGINE_LOCK_ID
JOIN performance_schema.data_locks AS blocking
  ON blocking.ENGINE = waits.ENGINE
 AND blocking.ENGINE_LOCK_ID = waits.BLOCKING_ENGINE_LOCK_ID;
```

Các bảng này cần quyền đọc Performance Schema phù hợp. Có thể kết hợp `SHOW ENGINE INNODB STATUS` để xem thông tin transaction, deadlock gần nhất và trạng thái engine. Khi phân tích, đối chiếu `INDEX_NAME`, `LOCK_MODE`, `LOCK_DATA`, truy vấn đang chạy và execution plan; đừng chỉ dựa vào tên câu lệnh.

## 9. Những lỗi thiết kế thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Cập nhật một mã nhưng transaction khác vẫn bị chặn | Điều kiện không dùng đầy đủ unique index hoặc kế hoạch quét rộng | Kiểm tra `EXPLAIN`, điều kiện và chỉ mục |
| Insert bị chờ dù chưa có hàng trùng khóa | Gap/next-key lock đang bảo vệ vị trí chèn | Xác định transaction khóa phạm vi và mức cô lập |
| Khóa nhiều hàng hơn số hàng trả về | Engine quét thêm bản ghi chỉ mục để đánh giá điều kiện | Thu hẹp access path bằng chỉ mục phù hợp |
| Một truy vấn theo trạng thái gây tranh chấp lớn | Cột trạng thái có ít giá trị và index không chọn lọc | Kết hợp cột lọc khác trong composite index |
| Transaction chờ lâu | Transaction khác giữ khóa quá lâu hoặc truy vấn khóa phạm vi lớn | Tìm blocker, rút ngắn transaction, chia lô công việc |
| Deadlock xuất hiện khi nhiều worker xử lý cùng tập dữ liệu | Các transaction khóa hàng theo thứ tự khác nhau | Truy cập theo thứ tự ổn định, xử lý retry khi deadlock |

## 10. Bài thực hành

Với bảng `orders` ở phần 2, thực hiện các bài sau trên hai session MySQL độc lập:

1. Dùng `EXPLAIN` cho truy vấn `WHERE external_ref = 'EXT-2026-001' FOR UPDATE`. Xác định index và loại truy cập được chọn.
2. Mở transaction A và khóa đơn hàng theo `external_ref`. Từ session B, cập nhật cùng đơn hàng rồi cập nhật một đơn hàng khác. Ghi nhận thao tác nào phải chờ.
3. Tạo truy vấn phạm vi theo `status` và `created_at`. Dùng `EXPLAIN` xác nhận index `(status, created_at)` được chọn.
4. Trong transaction A, chạy truy vấn phạm vi với `FOR UPDATE`. Từ session B, thử chèn hàng nằm trong khoảng và hàng nằm ngoài khoảng. So sánh thời gian chờ.
5. Lặp lại thử nghiệm ở `READ COMMITTED`. Ghi nhận thay đổi trong hành vi gap lock.
6. Truy vấn `performance_schema.data_locks` và `data_lock_waits` để xác định index, loại khóa và transaction đang chặn.

## Ghi nhớ

- Unique point lookup chỉ khóa hẹp khi điều kiện dùng đầy đủ khóa duy nhất và tìm thấy bản ghi; không áp dụng máy móc cho khóa ghép thiếu cột hoặc khóa không tồn tại.
- Range scan ở `REPEATABLE READ` thường dùng next-key lock để bảo vệ bản ghi và khoảng trống liên quan.
- Điều kiện `WHERE` chưa đủ để dự đoán phạm vi khóa; cần biết chỉ mục và execution plan mà InnoDB thực sự sử dụng.
- `READ COMMITTED` thường giảm gap locking cho tìm kiếm/quét thông thường, nhưng không loại bỏ mọi loại gap lock.
- Dùng `EXPLAIN`, Performance Schema và transaction ngắn để kiểm soát tranh chấp khóa.
