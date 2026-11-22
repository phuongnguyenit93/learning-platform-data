# Vì sao MVCC cần VACUUM và vai trò của autovacuum

PostgreSQL cho phép nhiều transactions đọc và ghi đồng thời mà phần lớn truy vấn đọc không phải chờ writers. Cơ chế nền tảng là **MVCC (Multi-Version Concurrency Control)**: một lần UPDATE thường tạo ra phiên bản tuple mới, còn phiên bản cũ được giữ lại cho đến khi không còn transaction nào cần nhìn thấy nó. DELETE cũng không lập tức xóa bytes của row khỏi file dữ liệu; nó đánh dấu phiên bản cũ là đã bị xóa theo ngữ nghĩa transaction.

Thiết kế này giúp readers nhìn thấy snapshot nhất quán, nhưng để lại các **dead tuples** khi những phiên bản cũ không còn cần thiết. Nếu không được thu hồi và tái sử dụng, heap/index phình to, truy vấn phải quét nhiều pages hơn, planner statistics lỗi thời và hệ thống có thể tiến gần nguy cơ **transaction ID wraparound**. PostgreSQL dùng **VACUUM** để dọn các phiên bản không còn cần thiết, cập nhật visibility information và đóng băng tuple đủ cũ. **Autovacuum** là daemon tự động lên lịch VACUUM/ANALYZE dựa trên thống kê và ngưỡng cấu hình.

Hiểu VACUUM không chỉ là nhớ một lệnh quản trị. Bạn cần nắm MVCC visibility, snapshot horizon, dead tuples, freezing, visibility map, autovacuum thresholds, vacuum workers và các nguyên nhân khiến vacuum không tiến triển. Những khái niệm này liên quan trực tiếp đến hiệu năng, dung lượng, replication, transaction design và độ sẵn sàng của PostgreSQL.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích MVCC và vì sao UPDATE/DELETE không lập tức thu hồi tuple cũ.
2. Phân biệt tuple version, live tuple, dead tuple, snapshot và transaction visibility.
3. Hiểu vai trò của xmin/xmax ở mức khái niệm và vì sao không nên tự đọc chúng như business timestamps.
4. Phân biệt heap pruning, VACUUM, ANALYZE và VACUUM FULL.
5. Giải thích VACUUM thu hồi không gian để PostgreSQL tái sử dụng nhưng thường không trả file size cho hệ điều hành.
6. Hiểu freezing, transaction ID wraparound và MultiXact wraparound.
7. Giải thích visibility map và lợi ích với index-only scans.
8. Nắm cách autovacuum quyết định một bảng cần vacuum/analyze.
9. Đọc các ngưỡng threshold/scale factor và cấu hình per-table khi workload lệch.
10. Phát hiện long-running transactions, replication slots hoặc standby feedback đang chặn vacuum horizon.
11. Theo dõi tiến trình bằng pg_stat_user_tables, pg_stat_progress_vacuum, pg_stat_activity và catalog.
12. Xử lý bảng lớn, partitioned tables, TOAST, temporary tables và import/update workloads.
13. Thiết kế vận hành VACUUM/ANALYZE có kiểm soát, không dùng VACUUM FULL như phản xạ.

> **Phiên bản:** Các tên setting và một số hành vi autovacuum có thể khác theo PostgreSQL version. Bài dùng các khái niệm và views phổ biến ở PostgreSQL hiện đại; trước khi đặt cấu hình production, đối chiếu các giá trị trong pg_settings và tài liệu đúng major version.

## 2. Vì sao PostgreSQL cần MVCC?

Giả sử hai transactions đồng thời:

```text
Transaction A: đọc account 10
Transaction B: cập nhật account 10
```

Nếu database chỉ cho một phiên bản row và writer ghi đè trực tiếp, reader có thể thấy dữ liệu đang sửa dở hoặc phải chờ writer kết thúc. MVCC giải quyết bằng cách giữ các phiên bản tuple có thông tin transaction, rồi quyết định phiên bản nào visible đối với snapshot của từng transaction.

### Ý tưởng

- Readers lấy snapshot và đọc phiên bản phù hợp với snapshot.
- Writers tạo phiên bản mới thay vì sửa nội dung row cũ theo cách khiến mọi reader lập tức thấy nó.
- Một phiên bản cũ chỉ được dọn khi không còn snapshot nào có thể cần nhìn thấy nó.

Nhờ vậy, nhiều SELECT có thể chạy song song với UPDATE/DELETE mà không phải khóa row để chờ mọi readers kết thúc. MVCC không loại bỏ mọi lock: writers vẫn có row/table locks và DDL vẫn có thể chặn operations.

## 3. Tuple version và xmin/xmax

Một row trong PostgreSQL được lưu dưới dạng **tuple** trong heap page. Ở mức khái niệm, tuple có metadata transaction:

- `xmin`: transaction ID liên quan đến việc tạo phiên bản tuple.
- `xmax`: transaction ID hoặc thông tin liên quan đến việc kết thúc hiệu lực/xóa/khóa tuple; không phải lúc nào cũng đơn giản là “ID transaction đã DELETE”.

Ví dụ logic:

```text
Ban đầu:
  tuple version V1: balance = 100

UPDATE balance = 150:
  V1 được đánh dấu hết hiệu lực theo transaction
  tuple version V2 được tạo: balance = 150

DELETE:
  phiên bản hiện hành được đánh dấu deleted
```

Đây là mô hình giải thích. Nội bộ `xmax` có thể biểu diễn lock/Multixact và nhiều trạng thái khác; đừng dùng phép so sánh số học `xmin`/`xmax` như business ordering hay timestamp.

### Vì sao không xóa V1 ngay khi UPDATE?

Một transaction cũ có thể đã lấy snapshot trước khi B commit. Với snapshot đó, V1 vẫn là phiên bản visible; V2 chưa được commit hoặc không visible trong snapshot. Nếu PostgreSQL xóa V1 ngay, transaction A sẽ mất dữ liệu mà snapshot của nó cần.

## 4. Ví dụ hai sessions nhìn hai phiên bản

Tạo bảng thực hành:

```sql
CREATE SCHEMA IF NOT EXISTS lesson_vacuum;

CREATE TABLE lesson_vacuum.accounts (
    account_id BIGINT PRIMARY KEY,
    balance NUMERIC(14,2) NOT NULL
);

INSERT INTO lesson_vacuum.accounts
VALUES (10, 100.00);
```

**Session A**:

```sql
BEGIN ISOLATION LEVEL REPEATABLE READ;

SELECT balance
FROM lesson_vacuum.accounts
WHERE account_id = 10;
-- 100.00
```

**Session B**:

```sql
BEGIN;

UPDATE lesson_vacuum.accounts
SET balance = 150.00
WHERE account_id = 10;

COMMIT;
```

**Session A**:

```sql
SELECT balance
FROM lesson_vacuum.accounts
WHERE account_id = 10;
-- Vẫn nhìn thấy 100.00 trong snapshot REPEATABLE READ.

COMMIT;
```

Một transaction mới sau khi B commit sẽ nhìn thấy 150.00:

```sql
SELECT balance
FROM lesson_vacuum.accounts
WHERE account_id = 10;
```

### Bài học

Trong lúc A còn giữ snapshot, phiên bản cũ có thể vẫn cần thiết. VACUUM không được xóa một tuple chỉ vì có phiên bản mới hơn; nó phải xét **visibility horizon** của những transactions/snapshots còn liên quan.

## 5. DELETE không xóa ngay bytes khỏi heap

Thử:

```sql
DELETE FROM lesson_vacuum.accounts
WHERE account_id = 10;
```

DELETE đánh dấu tuple cũ không còn visible với snapshots thích hợp sau khi transaction commit. Dữ liệu vật lý vẫn có thể nằm trong heap page cho đến khi pruning/vacuum làm sạch và không còn snapshot cần tuple ấy.

### Hệ quả

- `DELETE 1` không đồng nghĩa file table giảm kích thước ngay.
- UPDATE nhiều lần có thể tạo nhiều dead tuple versions.
- `TRUNCATE` là thao tác khác, thay đổi storage theo cách riêng và không tạo một DELETE row event cho từng hàng.
- VACUUM là một phần bình thường của quản lý MVCC, không phải chỉ chạy khi database “bị đầy”.

## 6. Live tuple, dead tuple và tuple còn có thể cần

Các từ này cần được hiểu theo visibility:

| Khái niệm | Ý nghĩa |
|---|---|
| Live tuple | Phiên bản hiện hành có thể visible với snapshot phù hợp |
| Dead tuple | Phiên bản không còn visible với bất kỳ transaction nào đang cần nó và có thể được thu hồi |
| Recently dead / potentially removable later | Phiên bản đã bị thay thế/xóa nhưng còn snapshot cũ có thể cần |
| Unused/free space | Vị trí trên page có thể tái sử dụng cho tuple mới |

Một tuple bị đánh dấu deleted không lập tức là **reclaimable**. Điều kiện quan trọng là không còn transaction/snapshot có thể nhìn thấy nó.

## 7. Vì sao dead tuples làm bảng phình to?

Giả sử bảng có 1 triệu accounts và mỗi ngày cập nhật 30%:

```text
UPDATE 300,000 rows
  → tạo tuple versions mới
  → phiên bản cũ dần trở thành dead
  → heap pages cần chứa phiên bản mới
  → indexes cần xử lý entries liên quan
```

Nếu dead tuples không được dọn:

- Sequential scans đọc nhiều pages có tuple không còn visible.
- Index scans có thể gặp entries dẫn đến dead heap tuples.
- Cache bị chiếm bởi pages ít giá trị.
- Table/index bloat có thể tăng.
- Disk và backup size có thể tăng.
- Planner statistics có thể không còn phản ánh phân bố dữ liệu.

**VACUUM giúp thu hồi/reuse space bên trong relation** và duy trì thông tin visibility/free space. Nó không tự làm mọi index/table trở về kích thước nhỏ nhất có thể.

## 8. HOT updates và liên hệ với VACUUM

PostgreSQL có thể dùng **Heap-Only Tuple (HOT) update** nếu các điều kiện phù hợp, tiêu biểu:

- UPDATE không thay đổi các cột được index theo cách ngăn HOT.
- Page chứa tuple có đủ free space cho phiên bản mới.

HOT update có thể giảm việc tạo index entries mới, vì chuỗi phiên bản được quản lý trong heap page. Điều này giảm index churn và công việc vacuum index ở một số workload.

### Fillfactor

Với bảng UPDATE thường xuyên, giảm fillfactor có thể chừa không gian trên heap pages để tăng khả năng HOT:

```sql
ALTER TABLE lesson_vacuum.accounts
SET (fillfactor = 80);
```

Đây chỉ là ví dụ cấu hình. Fillfactor thấp hơn làm table cần nhiều pages hơn ngay từ đầu và không bảo đảm mọi UPDATE thành HOT. Chỉ thay đổi sau khi đo n_tup_hot_upd, update pattern và disk/cache trade-off.

## 9. Heap pruning khác VACUUM thế nào?

**Pruning** có thể dọn một số dead tuple versions ngay trên heap page khi page được truy cập và điều kiện visibility cho phép. Nó giúp giảm chain length và tái sử dụng chỗ trống tại page.

**VACUUM** thực hiện công việc rộng hơn trên relation:

- Quét heap để tìm dead tuples.
- Thu hồi space để relation tái sử dụng.
- Xử lý index entries liên quan khi cần.
- Cập nhật visibility map.
- Freeze tuple đủ cũ.
- Cập nhật metadata phục vụ lần vacuum sau.

Pruning không thay thế một lần VACUUM đầy đủ: nó không bảo đảm quét mọi pages hay hoàn tất mọi nhiệm vụ freezing/index cleanup.

## 10. VACUUM làm gì?

Lệnh:

```sql
VACUUM lesson_vacuum.accounts;
```

VACUUM thông thường:

1. Tìm dead tuples có thể thu hồi dựa trên visibility horizon.
2. Xử lý các index entries tương ứng.
3. Đánh dấu vùng trống để PostgreSQL tái sử dụng.
4. Cập nhật visibility map và thông tin liên quan.
5. Freeze các tuple đủ cũ khi cần để ngăn transaction ID wraparound.

VACUUM thông thường được thiết kế để chạy đồng thời với nhiều hoạt động đọc/ghi thông thường. Tuy nhiên nó vẫn dùng I/O/CPU, có lock riêng và có thể cạnh tranh với workload. “Online” không có nghĩa là miễn phí.

### VACUUM không làm gì?

- Không xóa mọi dữ liệu cũ khỏi file hệ điều hành.
- Không tự sửa dữ liệu nghiệp vụ sai.
- Không thay thế ANALYZE.
- Không thể xóa tuple mà snapshot cũ còn cần.
- Không đảm bảo thu nhỏ index/table về mức tối thiểu.
- Không tự xử lý mọi dạng bloat ngay lập tức.

## 11. Space reuse khác disk shrink

Sau VACUUM:

- Một page có thể chứa free space để PostgreSQL tái sử dụng cho INSERT/UPDATE sau.
- Relation file thường giữ kích thước vật lý như trước.
- PostgreSQL có thể trả một phần space ở cuối relation cho hệ điều hành trong những điều kiện thích hợp, nhưng không nên kỳ vọng VACUUM thường làm file nhỏ rõ rệt.

### Ví dụ

Một bảng từng chiếm 20 GB, xóa phần lớn rows rồi VACUUM. PostgreSQL có thể dùng lại space đó cho các INSERT sau mà file vẫn gần 20 GB.

Điều này không tự chứng minh vacuum thất bại. Nếu workload sẽ tiếp tục tăng lại, giữ space để reuse có thể hiệu quả hơn việc shrink rồi lại mở rộng file.

## 12. VACUUM FULL khác VACUUM

```sql
VACUUM FULL lesson_vacuum.accounts;
```

VACUUM FULL viết lại relation để loại bỏ phần lớn free space nội bộ và thu nhỏ file khi có thể.

| Đặc điểm | VACUUM | VACUUM FULL |
|---|---|---|
| Có thể chạy cùng DML thông thường | Thường có | Không, cần lock mạnh |
| Reclaim dead tuples | Có | Có, qua rewrite |
| Thu nhỏ file relation | Thường không đáng kể | Có thể |
| Viết lại toàn relation | Không theo cách FULL | Có |
| Disk tạm | Thường thấp hơn | Cần thêm không gian cho rewrite |
| Blocking | Ít blocking hơn, vẫn có lock/IO | ACCESS EXCLUSIVE trong thời gian thực hiện |
| Dùng thường xuyên? | Là công việc bảo trì định kỳ | Chỉ khi có kế hoạch đặc biệt |

### Vì sao không chạy VACUUM FULL định kỳ?

Nó có thể chặn SELECT/INSERT/UPDATE/DELETE trên bảng trong thời gian rewrite, cần dung lượng tạm và tạo tải I/O lớn. Với bảng online quan trọng, đây có thể là downtime đáng kể.

Nếu cần xử lý bloat mà không thể chặn lâu, đánh giá các công cụ/chiến lược online phù hợp (ví dụ tái cấu trúc theo kế hoạch hoặc extension như pg_repack khi được phê duyệt), nhưng hiểu lock/space/replication trade-offs của chúng.

## 13. VACUUM và ANALYZE là hai công việc khác nhau

```sql
ANALYZE lesson_vacuum.accounts;
VACUUM lesson_vacuum.accounts;
VACUUM (ANALYZE) lesson_vacuum.accounts;
```

| Lệnh | Mục đích |
|---|---|
| ANALYZE | Thu thập thống kê phân bố dữ liệu cho query planner |
| VACUUM | Thu hồi dead tuples, cập nhật visibility/freeze metadata |
| VACUUM (ANALYZE) | Thực hiện vacuum và thu thập statistics trong cùng tác vụ |

Một bảng vừa COPY hàng triệu rows có thể cần ANALYZE để planner biết phân bố mới ngay cả khi không có nhiều dead tuples.

Một bảng UPDATE/DELETE liên tục có thể cần VACUUM để dọn dead tuples, đồng thời statistics cũng có thể cần cập nhật.

### VACUUM không tự có nghĩa ANALYZE

Autovacuum có cơ chế quyết định autovacuum và autoanalyze theo các ngưỡng khác nhau. Đừng giả định mọi lần vacuum đều tự động thu thập statistics mới như một VACUUM (ANALYZE).

## 14. Freezing là gì?

PostgreSQL dùng transaction IDs có không gian hữu hạn. Để một tuple cũ không bị diễn giải sai khi transaction ID quay vòng, engine có thể **freeze** tuple đủ cũ: thay vì phải dựa vào một XID rất cũ để xác định visibility mãi mãi, tuple được đánh dấu theo semantics frozen đặc biệt.

### Vì sao cần freeze?

Transaction IDs truyền thống là 32-bit và được sử dụng theo vòng. Nếu database chạy đủ lâu mà không freeze các tuple cũ, một transaction ID có thể quay lại giá trị số từng được dùng trong quá khứ. Khi đó tuple cũ có nguy cơ bị xem như được tạo bởi một transaction “tương lai” hoặc sai visibility.

Đây là **wraparound hazard** có thể gây mất khả năng truy cập an toàn nếu không xử lý trước ngưỡng nguy hiểm. VACUUM vì vậy không chỉ dọn dead tuples; nó còn phải giữ tuổi transaction của dữ liệu trong giới hạn an toàn.

### Freeze không phải xóa dữ liệu

Tuple đang live có thể được freeze. Việc freeze không làm mất row; nó làm metadata transaction của tuple an toàn trước vòng quay XID.

## 15. Transaction ID wraparound

XID là bộ đếm 32-bit, quay vòng sau một số lượng transaction nhất định. PostgreSQL dùng quy tắc so sánh modular và giới hạn khoảng cách XID để xác định transaction nào cũ/mới.

### Nguy cơ

Nếu các tuple còn mang XID quá cũ mà hệ thống tiến sát wraparound:

- Visibility semantics có thể trở nên không an toàn.
- PostgreSQL có thể phải buộc chạy anti-wraparound vacuum.
- Khi đến ngưỡng phòng vệ nghiêm trọng, server có thể từ chối một số writes/new transactions để tránh corruption.
- Hệ thống có thể rơi vào tình huống chỉ còn cho phép các thao tác cần thiết để vacuum cứu database.

### Đừng đợi disk đầy mới quan tâm

Wraparound là vấn đề **tuổi transaction**, không phải đơn giản dung lượng đĩa. Một database ít rows nhưng tạo rất nhiều transactions vẫn có thể cần freeze; một bảng lớn ít thay đổi cũng có thể chứa tuple rất cũ cần được freeze.

## 16. Anti-wraparound vacuum

Autovacuum có cơ chế ưu tiên vacuum để freeze tuple trước khi vượt giới hạn an toàn. Một số setting quan trọng:

| Setting | Ý nghĩa khái niệm |
|---|---|
| `autovacuum_freeze_max_age` | Ngưỡng tuổi XID khiến vacuum freeze cần được kích hoạt theo cơ chế chống wraparound |
| `vacuum_freeze_min_age` | Tuổi XID tối thiểu mà vacuum cân nhắc freeze tuple |
| `vacuum_freeze_table_age` | Tuổi relation khiến vacuum thực hiện quét/freeze mạnh hơn theo chính sách |
| `vacuum_failsafe_age` | Ngưỡng failsafe ở các phiên bản hỗ trợ, làm vacuum ưu tiên cứu wraparound và giảm một số chi phí |
| `autovacuum_multixact_freeze_max_age` | Ngưỡng tuổi MultiXact liên quan đến anti-wraparound |

Tên, defaults và chi tiết tương tác thay đổi theo phiên bản. Kiểm tra cấu hình thực tế:

```sql
SELECT
    name,
    setting,
    unit,
    context,
    source
FROM pg_catalog.pg_settings
WHERE name LIKE '%freeze%'
   OR name LIKE '%multixact%'
ORDER BY name;
```

### Không tắt autovacuum để “giảm tải”

Autovacuum có thể bị điều chỉnh hoặc tạm dừng trong một số tình huống bảo trì, nhưng tắt lâu dài mà không có quy trình manual vacuum/freeze thay thế là nguy hiểm. Anti-wraparound vacuum có thể vẫn được kích hoạt ở mức ưu tiên đặc biệt ngay cả khi autovacuum thông thường bị tắt ở table, tùy setting/version.

## 17. MultiXact wraparound

Không chỉ XID đơn lẻ cần freeze. PostgreSQL còn có **MultiXact IDs** để biểu diễn nhiều transactions cùng giữ row locks theo một số tình huống.

Nếu MultiXact age tăng quá cao mà không được xử lý, database có nguy cơ MultiXact wraparound. Vì vậy cần theo dõi cả:

- XID age.
- MultiXact age.
- Autovacuum/freeze progress.
- Những bảng có tuple cũ/transaction horizon bị giữ lâu.

### Quan trọng

Không suy luận database an toàn chỉ vì `age(datfrozenxid)` còn thấp. Kiểm tra thêm `mxid_age(datminmxid)` và các cảnh báo MultiXact của phiên bản.

## 18. Theo dõi XID age ở cấp database

Truy vấn:

```sql
SELECT
    datname,
    age(datfrozenxid) AS xid_age,
    mxid_age(datminmxid) AS multixact_age
FROM pg_catalog.pg_database
ORDER BY xid_age DESC;
```

### Đọc kết quả

- `age(datfrozenxid)` ước lượng độ tuổi transaction ID cũ nhất còn được database metadata theo dõi.
- `mxid_age(datminmxid)` đo độ tuổi MultiXact theo cách tương ứng.
- Giá trị tăng cần được so với ngưỡng cấu hình và xu hướng theo thời gian.

Đây là các số **age**, không phải thời gian tính bằng giây/ngày và cũng không phải số transactions đang chạy.

### Alert

Thiết lập cảnh báo theo cả ngưỡng tuyệt đối và tốc độ tăng. Một database có XID age đang ở mức vừa phải nhưng tăng nhanh trong lúc autovacuum không theo kịp cần được điều tra sớm.

## 19. Theo dõi XID age ở cấp bảng

```sql
SELECT
    n.nspname AS schema_name,
    c.relname AS table_name,
    age(c.relfrozenxid) AS xid_age,
    mxid_age(c.relminmxid) AS multixact_age,
    pg_size_pretty(pg_total_relation_size(c.oid)) AS total_size
FROM pg_catalog.pg_class AS c
JOIN pg_catalog.pg_namespace AS n
  ON n.oid = c.relnamespace
WHERE c.relkind IN ('r', 'm', 't')
ORDER BY age(c.relfrozenxid) DESC
LIMIT 30;
```

### Vì sao cần bảng-level?

Một bảng ít thay đổi nhưng chứa tuple cũ có thể cần freeze; bảng có nhiều writes có thể cần vacuum thường xuyên vì dead tuples. Database-level age cho biết tình trạng tổng quát, còn table-level giúp tìm relation cần ưu tiên.

### Lưu ý

Catalog columns và đối tượng relation có thể khác nhau theo loại bảng/phiên bản. Query chỉ là công cụ điều tra, không thay các cảnh báo wraparound của PostgreSQL.

## 20. Freeze và visibility map

PostgreSQL duy trì **visibility map (VM)** với các bits theo heap pages, trong đó các trạng thái quan trọng gồm:

- **All-visible:** mọi tuples trên page được biết là visible với tất cả transactions hiện tại theo điều kiện VM.
- **All-frozen:** các tuples trên page đã được freeze theo semantics cần thiết.

VACUUM cập nhật các bits này khi có thể.

### Tại sao hữu ích?

VM giúp PostgreSQL biết một page có thể bỏ qua một số kiểm tra visibility trong các đường truy cập phù hợp. Đặc biệt, nó hỗ trợ **index-only scans**: nếu index chứa đủ columns cho query và heap page được đánh dấu all-visible, executor có thể không cần đọc heap page để kiểm tra visibility cho từng tuple.

### Không phải index-only scan luôn chỉ đọc index

Nếu VM bit chưa được set hoặc page bị thay đổi sau vacuum, executor có thể phải truy cập heap để xác nhận tuple visibility. Vì vậy một query dùng index-only scan trong EXPLAIN vẫn có thể có Heap Fetches.

## 21. VACUUM giúp index-only scan như thế nào?

Ví dụ index:

```sql
CREATE INDEX ix_accounts_balance_cover
ON lesson_vacuum.accounts (account_id)
INCLUDE (balance);

EXPLAIN (ANALYZE, BUFFERS)
SELECT account_id, balance
FROM lesson_vacuum.accounts
WHERE account_id BETWEEN 1 AND 1000;
```

Index có đủ columns trả về. Nếu heap pages tương ứng all-visible, PostgreSQL có thể thực hiện index-only scan với ít heap fetches hơn.

### Thử nghiệm

1. Nạp nhiều rows.
2. Chạy query và đọc Heap Fetches.
3. Chạy VACUUM.
4. Chạy lại query trên dữ liệu không thay đổi.
5. So sánh plan, heap fetches và buffers.

Kết quả tùy cache, page visibility, workload và planner; không đảm bảo chỉ cần VACUUM là query luôn chọn index-only scan.

## 22. INSERT mới và all-visible pages

Một page vừa có INSERT/UPDATE mới có thể không còn all-visible. Dữ liệu mới cần được kiểm tra visibility theo MVCC. VACUUM sau đó có thể đánh dấu lại page khi điều kiện cho phép.

### Vì sao điều này quan trọng?

Một bảng append-only có thể ít dead tuples nhưng vẫn cần vacuum vì:

- Freeze tuple cũ.
- Thiết lập all-visible/all-frozen bits.
- Phục vụ index-only scans.
- Giữ XID age an toàn.

Vì vậy autovacuum có cả **insert-triggered vacuum threshold** ở các phiên bản hỗ trợ, không chỉ dựa trên số UPDATE/DELETE.

## 23. Freeze không có nghĩa mọi page đều được quét mỗi lần

VACUUM có nhiều chiến lược và có thể tận dụng visibility map để tránh quét những pages không cần thiết trong một số công việc. Khi đến ngưỡng freeze mạnh, cần quét nhiều pages hơn để đảm bảo tuple cũ được freeze.

### Tác động

- Một bảng lớn, ít updates có thể không cần dead-tuple cleanup thường xuyên nhưng vẫn cần freeze theo tuổi.
- Một bảng có nhiều writes có thể cần vacuum liên tục để thu hồi space và cập nhật VM.
- Một vacuum thông thường không nhất thiết làm toàn relation trở thành all-frozen.

Đừng dùng số dead tuples duy nhất để quyết định một bảng đã được bảo trì đầy đủ.

## 24. Snapshot horizon: vì sao VACUUM không dọn được?

Một tuple cũ chỉ reclaimable khi không còn snapshot nào có thể nhìn thấy nó. Các nguồn giữ horizon:

- Long-running transaction ở REPEATABLE READ/SERIALIZABLE.
- Transaction đang chạy query lâu và giữ snapshot.
- Session `idle in transaction`.
- Prepared transactions chưa được resolve.
- Replication slots giữ `xmin`/`catalog_xmin`.
- Standby feedback giữ xmin trên primary khi cấu hình bật.

### Kết quả

VACUUM có thể chạy xong nhưng không dọn được nhiều dead tuples nếu visibility horizon vẫn bị giữ bởi transaction/replication state cũ.

Đây là lý do “autovacuum đang chạy” không đồng nghĩa “dead tuples chắc chắn được dọn hết”.

## 25. Long-running transactions giữ dead tuples

Ví dụ:

```text
Session A:
BEGIN ISOLATION LEVEL REPEATABLE READ;
SELECT ...;   -- snapshot cũ được giữ

Session B:
UPDATE nhiều hàng;
COMMIT;

Autovacuum:
quét bảng nhưng không thể loại những tuple mà A còn cần
```

Khi A giữ transaction hàng giờ, phiên bản cũ có thể phải tồn tại hàng giờ. Bảng tiếp tục nhận writes và tạo dead tuples mới, khiến bloat tăng.

### Nguy hiểm của idle in transaction

Một application mở transaction, chạy SELECT rồi chờ người dùng hoặc gọi API bên ngoài mà không commit/rollback có thể giữ snapshot lâu dù không còn query active.

### Cách phòng tránh

- Transaction boundary ngắn.
- Không chờ network/user input trong transaction.
- `idle_in_transaction_session_timeout` theo policy.
- Monitoring xact age và `backend_xmin`.
- Xử lý connection/transaction leaks ở application.

## 26. Kiểm tra các transactions cũ

```sql
SELECT
    pid,
    usename,
    application_name,
    state,
    xact_start,
    now() - xact_start AS xact_age,
    backend_xmin,
    wait_event_type,
    wait_event,
    left(query, 160) AS query_preview
FROM pg_catalog.pg_stat_activity
WHERE xact_start IS NOT NULL
ORDER BY xact_start
LIMIT 30;
```

### Tìm các session đặc biệt

```sql
SELECT
    pid,
    usename,
    application_name,
    state,
    now() - state_change AS state_age,
    now() - xact_start AS xact_age,
    backend_xmin
FROM pg_catalog.pg_stat_activity
WHERE state LIKE 'idle in transaction%'
ORDER BY xact_start NULLS LAST;
```

### Không terminate mù quáng

Một transaction cũ có thể là migration, report quan trọng hoặc prepared workflow. Trước khi `pg_terminate_backend`, xác định owner, tác động rollback, lock dependencies và liệu ứng dụng có thể retry an toàn.

## 27. Prepared transactions và VACUUM horizon

Two-phase commit có thể để lại prepared transaction chưa COMMIT PREPARED/ROLLBACK PREPARED. Một prepared transaction tồn tại lâu có thể giữ transaction ID/snapshot-related state và làm vacuum không tiến triển.

Kiểm tra:

```sql
SELECT
    transaction,
    gid,
    prepared,
    owner,
    database
FROM pg_catalog.pg_prepared_xacts
ORDER BY prepared;
```

### Cần xử lý

Mỗi prepared transaction phải được coordinator xác định commit hay rollback dựa trên trạng thái giao dịch phân tán. Không tự rollback chỉ vì thấy nó cũ; hành động sai có thể làm lệch state giữa các hệ thống.

Không dùng prepared transactions như cách giữ transaction mở lâu để “đợi khi cần”.

## 28. Replication slots có thể giữ VACUUM horizon

Replication slots có thể giữ WAL cần thiết cho consumer và trong một số cấu hình cũng giữ tuple/catalog horizons để logical decoding có thể tiếp tục đúng. Một logical slot không được consumer đọc có thể giữ `xmin` hoặc `catalog_xmin` lâu, làm dead tuples/catalog rows không thể thu hồi.

Kiểm tra:

```sql
SELECT
    slot_name,
    slot_type,
    database,
    active,
    xmin,
    catalog_xmin,
    restart_lsn,
    confirmed_flush_lsn
FROM pg_catalog.pg_replication_slots
ORDER BY slot_name;
```

### Đọc các trường

- `active`: slot hiện có consumer đang kết nối hay không.
- `xmin`: horizon liên quan đến tuple visibility nếu slot giữ giá trị này.
- `catalog_xmin`: horizon liên quan catalog tuples.
- `restart_lsn`: WAL position mà slot còn cần.
- `confirmed_flush_lsn`: vị trí consumer đã xác nhận với logical slot trong trường hợp tương ứng.

### Rủi ro

Một slot inactive lâu có thể vừa giữ WAL làm disk tăng, vừa cản vacuum cleanup. Không xóa slot tùy tiện: consumer có thể mất khả năng tiếp tục từ vị trí cũ và cần reinitialize/re-snapshot.

## 29. Kiểm tra replication xmin và WAL retention

Một truy vấn tổng hợp:

```sql
SELECT
    slot_name,
    active,
    age(xmin) AS xmin_age,
    age(catalog_xmin) AS catalog_xmin_age,
    pg_size_pretty(
        pg_wal_lsn_diff(pg_current_wal_lsn(), restart_lsn)::bigint
    ) AS retained_wal_estimate
FROM pg_catalog.pg_replication_slots
ORDER BY retained_wal_estimate DESC NULLS LAST;
```

### Chú ý

`age(xmin)`/`age(catalog_xmin)` có thể trả NULL nếu trường tương ứng không có giá trị. Phép ước lượng WAL ở đây so với current LSN; mức retention thực tế còn phụ thuộc các slots khác, archiving, WAL recycling, checkpoint và cấu hình server.

Không lấy một replication slot inactive rồi xóa ngay trong production chỉ để vacuum chạy nhanh hơn. Xác định consumer, owner, dữ liệu có thể tái tạo và kế hoạch tạo lại slot trước.

## 30. hot_standby_feedback và primary vacuum

Standby có thể gửi feedback về xmin để primary không loại những tuple mà queries trên standby còn cần. Điều này giúp giảm một số recovery conflicts trên standby, nhưng có thể khiến primary giữ dead tuples lâu hơn.

Kiểm tra setting:

```sql
SHOW hot_standby_feedback;
```

Trên primary có thể xem replication status:

```sql
SELECT
    application_name,
    state,
    sent_lsn,
    write_lsn,
    flush_lsn,
    replay_lsn,
    write_lag,
    flush_lag,
    replay_lag,
    backend_xmin
FROM pg_catalog.pg_stat_replication;
```

### Trade-off

- Bật feedback có thể giảm query cancellations trên standby.
- Nhưng xmin feedback cũ có thể giữ dead tuples trên primary, tăng bloat.
- Tắt feedback có thể khiến standby queries bị cancel bởi recovery conflicts.

Chọn theo SLA của primary/replica, long-running reports và dung lượng; không có setting đúng cho mọi hệ thống.

## 31. Replication slot và standby feedback khác nhau

| Cơ chế | Chủ yếu phục vụ | Rủi ro nếu giữ lâu |
|---|---|---|
| Replication slot | Giữ WAL và/hoặc logical decoding horizon | WAL disk growth, vacuum horizon giữ cũ |
| hot_standby_feedback | Báo xmin từ standby về primary | Primary giữ dead tuples lâu hơn |
| Long-running standby query | Cần snapshot trên standby | Recovery conflict hoặc feedback horizon kéo dài |
| Logical consumer chậm | Chưa xác nhận LSN mới | Slot giữ WAL và có thể giữ catalog/data xmin |

Đây là những nguồn khác nhau, cần quan sát cả replication slot và standby activity để hiểu vì sao vacuum bị chặn.

## 32. Autovacuum là gì?

Autovacuum gồm các thành phần daemon/launcher và workers tự động thực hiện vacuum/analyze theo thống kê, thresholds và giới hạn tài nguyên.

### Hai nhiệm vụ chính

**Autovacuum (VACUUM):**

- Thu hồi dead tuples.
- Freeze tuple cũ.
- Duy trì visibility map/free space.
- Giảm nguy cơ wraparound.

**Autoanalyze (ANALYZE):**

- Thu thập thống kê sau khi đủ nhiều dữ liệu thay đổi.
- Giúp planner cập nhật ước lượng cardinality/distribution.

Một autovacuum worker có thể thực hiện vacuum và/hoặc analyze cho relation tùy lý do được kích hoạt.

## 33. Vì sao không chạy VACUUM thủ công liên tục?

VACUUM thủ công hữu ích cho tác vụ có chủ đích, nhưng với workload liên tục, daemon tự động có lợi:

- Tự theo dõi số tuples thay đổi.
- Chọn relation đến ngưỡng.
- Chạy nhiều workers trong giới hạn.
- Tự freeze theo tuổi XID.
- Giảm nhu cầu cron job VACUUM mọi bảng theo lịch cứng.

### Nhưng autovacuum không phải “bật là xong”

Nếu thresholds không phù hợp với bảng rất lớn, workload có tốc độ update cao hoặc vacuum workers không đủ tài nguyên, daemon có thể không theo kịp. Cần theo dõi metrics và điều chỉnh có căn cứ.

## 34. Công thức ngưỡng autovacuum VACUUM

Đối với một bảng, ngưỡng vacuum do UPDATE/DELETE được mô tả khái quát:

\[
\text{vacuum threshold}
= \text{autovacuum\_vacuum\_threshold}
+ \text{autovacuum\_vacuum\_scale\_factor}
\times \text{estimated table rows}
\]

Khi số tuples thay đổi vượt ngưỡng theo thống kê, bảng đủ điều kiện được autovacuum xét đến.

### Ví dụ giả định

Giả sử:

- Bảng 10 triệu rows.
- Threshold 50.
- Scale factor 0.2.

\[
50 + 0.2 \times 10,000,000
= 2,000,050
\]

Nếu chỉ dùng ngưỡng minh họa này, cần khoảng 2 triệu thay đổi tuples trước khi trigger vacuum theo ngưỡng đó. Với bảng lớn, 20% có thể là quá nhiều dead tuples trước lần vacuum tiếp theo.

### Cẩn thận

Đây là công thức khái quát cho threshold UPDATE/DELETE; có ngưỡng riêng cho INSERT-triggered vacuum, wraparound và các điều kiện bổ sung. Thống kê rows là ước lượng, không phải count chính xác tức thời.

## 35. Ngưỡng INSERT-triggered vacuum

Ở các PostgreSQL versions hỗ trợ, autovacuum có:

- `autovacuum_vacuum_insert_threshold`
- `autovacuum_vacuum_insert_scale_factor`

Ngưỡng insert có dạng khái quát:

\[
\text{insert vacuum threshold}
= \text{insert threshold}
+ \text{insert scale factor}
\times \text{estimated table rows}
\]

Điều này quan trọng với bảng **append-only**: dù ít UPDATE/DELETE, các tuples mới vẫn cần freeze theo thời gian và vacuum có thể cải thiện visibility map cho index-only scans.

Không giả định bảng append-only không cần vacuum.

## 36. Ngưỡng autoanalyze

Autoanalyze dùng ngưỡng thay đổi dữ liệu riêng, khái quát:

\[
\text{analyze threshold}
= \text{autovacuum\_analyze\_threshold}
+ \text{autovacuum\_analyze\_scale\_factor}
\times \text{estimated table rows}
\]

Sau khi số modifications kể từ lần analyze vượt ngưỡng, bảng có thể được chọn để autoanalyze.

### Ví dụ

Với bảng 5 triệu rows, threshold 50 và scale factor 0.1:

\[
50 + 0.1 \times 5,000,000 = 500,050
\]

Planner có thể tiếp tục dùng statistics cũ trong khi dữ liệu đã thay đổi đáng kể. Với bảng lớn, scale factor nhỏ hơn có thể giúp statistics được cập nhật sớm hơn.

### Analyze không chỉ dành cho UPDATE/DELETE

INSERT cũng làm phân bố dữ liệu thay đổi. Một bảng append-only vừa tăng từ 1 triệu lên 20 triệu rows có thể cần autoanalyze để planner không ước lượng theo dữ liệu cũ.

## 37. Threshold và scale factor: tác động của bảng lớn

Scale factor là tỷ lệ trên số rows ước lượng. Vì vậy cùng một cấu hình có thể có hành vi rất khác:

| Table size | Scale factor 0.2 | Ý nghĩa |
|---:|---:|---|
| 10.000 rows | 2.000 rows | Ngưỡng tương đối nhỏ |
| 1.000.000 rows | 200.000 rows | Có thể tích tụ nhiều changes |
| 100.000.000 rows | 20.000.000 rows | Có thể quá muộn cho workload write-heavy |

### Tại sao threshold tuyệt đối vẫn hữu ích?

Scale factor một mình làm bảng nhỏ có ngưỡng rất thấp; một threshold tuyệt đối giúp tránh chạy vacuum/analyze quá thường xuyên cho bảng nhỏ nhưng có một số modifications.

### Không chọn scale factor bằng cảm tính

Đặt quá thấp làm autovacuum chạy liên tục và cạnh tranh I/O; quá cao làm dead tuples/statistics stale tích tụ. Hãy căn cứ:

- Tốc độ UPDATE/DELETE/INSERT.
- Relation size và tuple width.
- Tốc độ vacuum thực tế.
- Query plans và freshness cần thiết.
- Disk/WAL/CPU headroom.

## 38. Xem cấu hình autovacuum hiện tại

```sql
SELECT
    name,
    setting,
    unit,
    context,
    source
FROM pg_catalog.pg_settings
WHERE name LIKE 'autovacuum%'
   OR name LIKE 'vacuum%'
ORDER BY name;
```

Một số settings thường gặp:

| Setting | Vai trò |
|---|---|
| `autovacuum` | Bật/tắt launcher behavior ở mức server |
| `autovacuum_naptime` | Khoảng thời gian launcher chờ giữa các lần kiểm tra database |
| `autovacuum_max_workers` | Số workers autovacuum tối đa đồng thời |
| `autovacuum_vacuum_threshold` | Threshold tuyệt đối cho vacuum do UPDATE/DELETE |
| `autovacuum_vacuum_scale_factor` | Tỷ lệ theo table size cho vacuum threshold |
| `autovacuum_vacuum_insert_threshold` | Threshold tuyệt đối cho vacuum do INSERT trên version hỗ trợ |
| `autovacuum_vacuum_insert_scale_factor` | Tỷ lệ theo table size cho insert threshold |
| `autovacuum_analyze_threshold` | Threshold tuyệt đối cho autoanalyze |
| `autovacuum_analyze_scale_factor` | Tỷ lệ theo table size cho autoanalyze |
| `autovacuum_vacuum_cost_limit` | Cost budget của autovacuum workers |
| `autovacuum_vacuum_cost_delay` | Delay giữa các chu kỳ cost-based throttling |
| `autovacuum_work_mem` | Memory budget riêng cho vacuum workers nếu cấu hình |

Tên setting có thể không tồn tại trên một phiên bản cũ; chỉ cấu hình các tham số được server công bố.

## 39. Workers và autovacuum throughput

`autovacuum_max_workers` giới hạn số autovacuum workers có thể hoạt động đồng thời. Nếu nhiều bảng cùng vượt ngưỡng, chúng có thể phải chờ đến lượt.

### Tăng workers có thể giúp khi

- Nhiều bảng độc lập cần vacuum.
- CPU/I/O còn headroom.
- Worker queue thường xuyên có backlog.
- Mỗi worker hoàn thành công việc nhưng launcher không kịp xử lý tất cả relations.

### Tăng workers có thể làm xấu khi

- Disk đã bão hòa.
- Workload OLTP đang nhạy latency.
- Vacuum workers cùng scan các bảng/index lớn gây I/O contention.
- RAM không đủ cho số workers và query workloads.

### Cần phân biệt

Tăng `autovacuum_max_workers` không làm một vacuum đơn lẻ nhanh lên theo tỷ lệ tương ứng; nó tăng số vacuum jobs có thể chạy đồng thời. Với một bảng lớn, tốc độ phụ thuộc scan/index work, I/O, cost throttling và horizon.

## 40. Cost-based vacuum delay

Autovacuum dùng cơ chế cost-based throttling để tránh chiếm toàn bộ I/O:

- Mỗi loại page access/update có cost.
- Worker cộng dồn cost.
- Khi vượt budget, worker sleep theo delay được cấu hình.

Settings:

```sql
SHOW autovacuum_vacuum_cost_limit;
SHOW autovacuum_vacuum_cost_delay;
SHOW vacuum_cost_limit;
SHOW vacuum_cost_delay;
```

### Trade-off

- Cost limit cao hoặc delay thấp: vacuum có thể tiến nhanh hơn nhưng cạnh tranh I/O nhiều hơn.
- Cost limit thấp hoặc delay cao: giảm tác động tức thời lên workload, nhưng vacuum có thể không theo kịp write rate.

Không tắt throttling chỉ vì vacuum chậm; trước tiên đo I/O saturation, old snapshots và số dead tuples được dọn thực tế.

## 41. Autovacuum memory

`autovacuum_work_mem` có thể giới hạn memory dùng cho mỗi autovacuum worker (nếu setting/version hỗ trợ). Vacuum cần quản lý các tuple identifiers và index cleanup; khi bảng/index lớn, memory budget có thể ảnh hưởng số lần xử lý index và hiệu quả.

### Không tính memory đơn giản

Nếu có 8 workers và mỗi worker được phép dùng 1 GB, không có nghĩa chúng luôn lập tức allocate đủ 8 GB. Nhưng capacity planning phải xem **worst-case/concurrent memory pressure**, các allocations khác và query workloads.

Đừng nâng memory của autovacuum mà không tính tổng RAM của PostgreSQL host/container.

## 42. Per-table autovacuum settings

Một bảng write-heavy có thể cần threshold riêng:

```sql
ALTER TABLE lesson_vacuum.accounts
SET (
    autovacuum_vacuum_threshold = 1000,
    autovacuum_vacuum_scale_factor = 0.02,
    autovacuum_analyze_threshold = 500,
    autovacuum_analyze_scale_factor = 0.01
);
```

Các số trên **chỉ minh họa** cho một bảng; phải benchmark và căn cứ tốc độ thay đổi thực tế.

Xem reloptions:

```sql
SELECT
    c.oid::regclass AS relation,
    c.reloptions
FROM pg_catalog.pg_class AS c
WHERE c.oid = 'lesson_vacuum.accounts'::regclass;
```

### Khi nào dùng per-table settings?

- Bảng lớn có update rate cao.
- Bảng append-only cần insert-triggered vacuum/freeze.
- Bảng ít thay đổi, không cần thresholds thấp.
- Bảng có query latency nhạy cảm và cần điều chỉnh vacuum impact.

Không sao chép một bộ reloptions cho toàn bộ tables nếu workload khác nhau.

## 43. Có thể tắt autovacuum trên một bảng không?

PostgreSQL cho phép reloption `autovacuum_enabled` trên một số relation:

```sql
-- Minh họa để hiểu cấu hình; không khuyến nghị dùng lâu dài:
ALTER TABLE lesson_vacuum.accounts
SET (autovacuum_enabled = false);
```

### Rủi ro

- Dead tuples tích tụ.
- Statistics không được tự cập nhật.
- XID/MultiXact freeze maintenance bị trì hoãn.
- Relation có thể tiến gần wraparound.

### Anti-wraparound

Không nên nghĩ `autovacuum_enabled=false` có thể vô hiệu hóa mọi anti-wraparound protection. PostgreSQL có cơ chế buộc vacuum để bảo vệ database; hành vi chi tiết phụ thuộc phiên bản và trạng thái server.

Nếu một bảng cần workflow bảo trì riêng, phải có **manual vacuum/analyze/freeze schedule**, alerts theo XID age và người chịu trách nhiệm. Tắt autovacuum không có runbook là cấu hình nguy hiểm.

## 44. Vì sao autovacuum có thể không theo kịp?

Các nguyên nhân:

1. UPDATE/DELETE rate lớn hơn tốc độ vacuum.
2. Table scale factor tạo threshold quá cao.
3. Quá ít autovacuum workers cho nhiều tables.
4. Cost throttling quá thấp so với workload.
5. I/O/CPU bão hòa.
6. Long-running transaction giữ snapshot horizon.
7. Replication slot hoặc standby feedback giữ xmin.
8. Vacuum bị cancel bởi conflicting operations.
9. Bảng/partition có reloptions không phù hợp.
10. Autovacuum không xử lý relation theo cách người vận hành kỳ vọng (ví dụ temporary tables).

Không chỉ tăng workers khi vacuum không dọn được tuple; nếu horizon bị giữ, thêm workers không giải quyết gốc rễ.

## 45. Theo dõi bảng qua pg_stat_user_tables

```sql
SELECT
    schemaname,
    relname,
    n_live_tup,
    n_dead_tup,
    n_mod_since_analyze,
    last_vacuum,
    last_autovacuum,
    vacuum_count,
    autovacuum_count,
    last_analyze,
    last_autoanalyze
FROM pg_catalog.pg_stat_user_tables
WHERE schemaname = 'lesson_vacuum'
ORDER BY n_dead_tup DESC;
```

### Đọc các cột

- `n_live_tup` và `n_dead_tup` là **ước lượng thống kê**, không phải exact counts.
- `n_mod_since_analyze` cho biết số modifications ước tính kể từ lần analyze gần nhất.
- `last_autovacuum` và `autovacuum_count` cho biết lịch sử worker autovacuum.
- `last_vacuum`/`vacuum_count` tương ứng với vacuum thủ công theo thống kê.
- `last_autoanalyze` cho biết lần autoanalyze gần nhất.

### Không có last_autovacuum không đồng nghĩa lỗi

Bảng có thể mới tạo, ít thay đổi hoặc chưa đến ngưỡng. Với temporary tables, autovacuum không thể truy cập session-local temp relation như bảng persistent; session tạo temp table phải tự quản lý ANALYZE/VACUUM khi cần.

## 46. Ước lượng dead tuples không phải count chính xác

Truy vấn:

```sql
SELECT
    relname,
    n_live_tup,
    n_dead_tup,
    CASE
        WHEN n_live_tup + n_dead_tup > 0
        THEN round(
            100.0 * n_dead_tup
            / (n_live_tup + n_dead_tup),
            2
        )
        ELSE 0
    END AS estimated_dead_pct
FROM pg_catalog.pg_stat_user_tables
WHERE schemaname = 'lesson_vacuum'
ORDER BY n_dead_tup DESC;
```

Tỷ lệ ở đây là **ước lượng thô**, hữu ích để tìm relation cần điều tra chứ không phải phép đo bloat chuẩn. Không đặt alert duy nhất theo dead_pct mà bỏ qua table size, tuple width, tốc độ tạo dead tuples và vacuum progress.

## 47. Xem autovacuum workers đang chạy

```sql
SELECT
    pid,
    datname,
    usename,
    application_name,
    backend_type,
    state,
    query_start,
    now() - query_start AS query_age,
    wait_event_type,
    wait_event,
    left(query, 200) AS query_preview
FROM pg_catalog.pg_stat_activity
WHERE backend_type = 'autovacuum worker'
ORDER BY query_start;
```

Tên backend type có thể phụ thuộc version. Query giúp nhận diện workers, nhưng không cung cấp đầy đủ phần trăm tiến độ; dùng progress view tương ứng.

## 48. pg_stat_progress_vacuum

Trong khi VACUUM đang chạy, có thể xem:

```sql
SELECT
    pid,
    datid,
    relid::regclass AS relation,
    phase,
    heap_blks_total,
    heap_blks_scanned,
    heap_blks_vacuumed,
    index_vacuum_count,
    num_dead_tuples,
    max_dead_tuples
FROM pg_catalog.pg_stat_progress_vacuum;
```

### Các phases thường gặp

- Scanning heap: quét heap pages.
- Vacuuming indexes: xử lý index entries liên quan.
- Vacuuming heap: xử lý các heap pages.
- Cleaning up indexes: hoàn tất index cleanup theo cơ chế/version.
- Truncating heap: có thể truncate pages trống ở cuối relation khi điều kiện cho phép.
- Performing final cleanup: cập nhật metadata/final work.

Tên phases/cột thay đổi theo phiên bản và loại công việc; đọc catalog/view schema của server thực tế.

### Đọc progress đúng cách

`heap_blks_scanned` trên `heap_blks_total` cho biết tiến độ scan trong phase tương ứng, không phải một phần trăm “toàn bộ vacuum” luôn chính xác. Một worker có thể chuyển phase và tiến độ biểu diễn lại.

## 49. Theo dõi tiến độ VACUUM thủ công và autovacuum

`pg_stat_progress_vacuum` có thể hiển thị cả manual VACUUM lẫn autovacuum worker. Kết hợp với `pg_stat_activity`:

```sql
SELECT
    p.pid,
    p.relid::regclass AS relation,
    p.phase,
    a.backend_type,
    a.application_name,
    now() - a.query_start AS elapsed,
    a.wait_event_type,
    a.wait_event
FROM pg_catalog.pg_stat_progress_vacuum AS p
JOIN pg_catalog.pg_stat_activity AS a
  ON a.pid = p.pid
ORDER BY a.query_start;
```

### Điều tra nếu tiến độ đứng lâu

- Worker có chờ I/O hay lock không?
- Có transaction horizon quá cũ không?
- Index cleanup có tốn thời gian không?
- Có vacuum khác trên relation đang chạy không?
- Disk throughput/latency có đang bão hòa?
- Worker có bị cancel/restart không?

Đừng kill worker chỉ vì một phase kéo dài; vacuum có thể cần nhiều phút/giờ với bảng lớn và index nhiều.

## 50. Log autovacuum

Setting:

```sql
SHOW log_autovacuum_min_duration;
```

`log_autovacuum_min_duration` cho phép ghi log các hoạt động autovacuum kéo dài hơn ngưỡng cấu hình (hoặc tất cả khi dùng giá trị phù hợp theo version).

### Log có thể giúp thấy

- Relation được vacuum/analyze.
- Số pages/tuples xử lý.
- Dead tuples được loại hoặc còn lại.
- Thời gian thực hiện.
- Index cleanup và memory details theo version.
- Lý do/đặc điểm của worker.

### Không bật logging chi tiết mà không tính log volume

Một database có hàng nghìn tables và nhiều autovacuum runs có thể tạo log đáng kể. Chọn threshold, retention, structured logging và alert theo mục tiêu điều tra.

## 51. Phân biệt VACUUM, autoanalyze và autovacuum logs

Trong bảng stats:

- `last_autovacuum` nói lần autovacuum vacuum gần nhất theo thống kê.
- `last_autoanalyze` nói lần autoanalyze gần nhất.
- Một autovacuum worker có thể thực hiện cả hai công việc trong một lượt.
- `last_vacuum` phản ánh vacuum thủ công, không thay cho auto counters.

Không suy ra “bảng đã được analyze” chỉ vì `last_autovacuum` mới; kiểm tra `last_autoanalyze`/`last_analyze` và statistics cần thiết.

## 52. ANALYZE thủ công sau bulk load

Sau một lần nạp dữ liệu lớn:

```sql
ANALYZE lesson_vacuum.accounts;
```

Hoặc:

```sql
ANALYZE lesson_vacuum.accounts (balance);
```

Có thể thu thập statistics cho toàn bảng hoặc một số columns cụ thể.

### Vì sao không đợi autovacuum?

Sau bulk load, một query quan trọng có thể chạy ngay. Nếu statistics cũ không phản ánh phân bố mới, planner có thể chọn plan kém. Manual ANALYZE giúp cập nhật trước khi mở workload.

### ANALYZE có dọn dead tuples không?

Không. Nó cập nhật planner statistics, không thay thế VACUUM.

## 53. VACUUM thủ công và cú pháp quan trọng

Ví dụ:

```sql
VACUUM (VERBOSE, ANALYZE) lesson_vacuum.accounts;

VACUUM (FREEZE, VERBOSE) lesson_vacuum.accounts;
```

- `VERBOSE` in chi tiết tiến trình/kết quả theo client/server output.
- `ANALYZE` cập nhật statistics.
- `FREEZE` yêu cầu freeze mạnh hơn theo semantics của VACUUM.

### Transaction block

`VACUUM` và `VACUUM FULL` không được chạy bên trong transaction block tường minh. Chạy như lệnh top-level riêng, không đặt trong `BEGIN ... COMMIT` hoặc một migration framework luôn bao DDL/DML trong transaction.

### FREEZE không phải lệnh phải chạy hàng ngày

Autovacuum đã quản lý freezing theo tuổi XID. Dùng manual FREEZE khi có lý do rõ ràng, chẳng hạn chuẩn bị một bảng mới/cửa sổ vận hành cụ thể và đã hiểu chi phí scan/locks.

## 54. VACUUM FULL và phương án xử lý bloat

Nếu cần thu nhỏ relation, trước hết xác định:

- Có dead tuples chưa được vacuum?
- Có long-running transactions giữ horizon?
- Bloat ở heap hay index?
- Bảng có tăng trưởng lại sau cleanup không?
- Có đủ disk cho rewrite và WAL/replication không?

### VACUUM FULL

```sql
VACUUM FULL lesson_vacuum.accounts;
```

Yêu cầu lock `ACCESS EXCLUSIVE` và rewrite relation. Lên kế hoạch downtime/maintenance window, kiểm tra free disk, replication và dependent objects.

### REINDEX

Nếu bloat chủ yếu ở index, có thể cân nhắc `REINDEX INDEX`/`REINDEX TABLE` hoặc biến thể CONCURRENTLY khi version hỗ trợ và yêu cầu phù hợp. REINDEX không thay vacuum heap hay giải quyết snapshot horizon.

### Không đo bloat bằng file size duy nhất

Một bảng 100GB có thể chứa 50GB space reusable nhưng vẫn là thiết kế phù hợp cho workload sắp nạp lại; một index nhỏ có thể có bloat tương đối cao nhưng không gây latency đáng kể. Dùng measurements/extension phù hợp và workload impact trước khi rewrite.

## 55. VACUUM và partitioned tables

Với partitioned table, dữ liệu vật lý thường nằm ở **leaf partitions**. Autovacuum xử lý các partition có storage như relations thông thường theo thống kê/threshold của chúng.

### Analyze parent

Partitioned parent không chứa heap rows như leaf. Autovacuum không phải lúc nào cũng tự cập nhật statistics tổng hợp cho partitioned parent theo cách người vận hành mong đợi; nhiều phiên bản yêu cầu chạy `ANALYZE` thủ công trên parent sau khi thay đổi partitions để planner có statistics ở cấp partitioned relation.

### Quy trình

1. Kiểm tra vacuum/analyze của từng leaf partition.
2. Sau attach/load partition, chạy ANALYZE trên parent khi cần.
3. Theo dõi XID age của các relations.
4. Lập kế hoạch detach/drop partition theo retention.
5. Kiểm tra index/constraint inheritance và DDL lock behavior.

### Không nhầm DROP PARTITION với DELETE từng row

Detach/drop partition có semantics DDL/storage khác DELETE; không tạo một dead tuple cho mỗi row và không được kỳ vọng row-level DELETE triggers ghi một event cho mọi row khi partition bị drop.

## 56. TOAST tables cũng cần vacuum

PostgreSQL có thể lưu giá trị lớn như TEXT/BYTEA/JSONB ngoài dòng trong **TOAST relation**. Khi các row values lớn bị UPDATE/DELETE, TOAST data cũng có thể tạo dead tuples.

VACUUM bảng chính sẽ quản lý cả các TOAST relations liên quan theo cơ chế PostgreSQL.

### Khi điều tra

- Xem `pg_total_relation_size`, không chỉ `pg_relation_size` heap.
- Quan sát TOAST relation size nếu table có payload lớn.
- Đừng chỉ vacuum heap rồi kết luận không gian đã thu hồi hết.
- Đo index/TOAST storage và update pattern.

Một bảng có ít rows nhưng mỗi row chứa JSONB lớn có thể phát sinh write amplification đáng kể khi update payload.

## 57. Temporary tables và autovacuum

Autovacuum daemon không thể xử lý temporary tables thuộc session khác như các bảng persistent thông thường. Session sở hữu temp table cần tự đảm bảo statistics/vacuum khi cần.

Ví dụ:

```sql
CREATE TEMP TABLE temp_events AS
SELECT *
FROM lesson_vacuum.accounts;

ANALYZE temp_events;
```

### Vì sao quan trọng?

Một session tạo temp table hàng triệu rows rồi chạy join phức tạp có thể cần ANALYZE để planner chọn plan tốt. Không thấy `last_autovacuum` cho temp table không phải dấu hiệu autovacuum daemon bị lỗi.

### Lifecycle

Temporary relation sống theo session/transaction tùy khai báo ON COMMIT. Khi dùng connection pool, session-local temp table có thể còn trên physical connection sau khi application trả logical lease; cần cleanup và hiểu PgBouncer pooling mode.

## 58. Autovacuum cần thống kê được bật

Autovacuum dựa vào statistics để quyết định relation nào đến ngưỡng. Kiểm tra:

```sql
SHOW autovacuum;
SHOW track_counts;
SHOW autovacuum_naptime;
```

Nếu hệ thống tắt tracking counts hoặc cấu hình autovacuum không hoạt động như dự kiến, launcher có thể không có dữ liệu cần thiết để lên lịch vacuum/analyze bình thường.

### Đừng chỉ kiểm tra một setting

Một bảng có thể có reloption riêng, một database có workload khác và server có giới hạn worker/cost. Điều tra cả:

- Global settings.
- Database/table reloptions.
- Statistics counters.
- Running workers.
- XID horizon và replication state.

## 59. Autovacuum launcher và database scheduling

Launcher định kỳ kiểm tra các databases và kích hoạt workers theo nhu cầu. `autovacuum_naptime` là khoảng thời gian giữa các lần kiểm tra database theo cấu hình; không có nghĩa mỗi bảng được vacuum đúng chu kỳ ấy.

### Vì sao có thể chờ?

- Nhiều databases cùng có bảng vượt ngưỡng.
- Số workers tối đa đã bận.
- Một vacuum job kéo dài.
- Cost throttling hoặc I/O làm worker chậm.
- Relation đang bị lock/conflict.

Autovacuum là scheduler có giới hạn tài nguyên, không phải một worker riêng cho mỗi table.

## 60. Tác động lock của VACUUM thường

VACUUM thường lấy lock cho phép nhiều DML/SELECT thông thường tiếp tục, nhưng nó vẫn có thể xung đột với một số DDL/maintenance operations và các vacuum khác trên cùng relation.

### Điều cần nhớ

- VACUUM thường không yêu cầu ACCESS EXCLUSIVE như VACUUM FULL.
- DDL như một số ALTER TABLE operations có thể phải chờ hoặc khiến vacuum chờ tùy lock mode.
- Một migration đang giữ lock có thể làm autovacuum bị chặn.
- Vacuum cũng tạo I/O/CPU pressure dù không khóa toàn bảng.

### Điều tra lock

```sql
SELECT
    a.pid,
    a.application_name,
    a.state,
    a.wait_event_type,
    a.wait_event,
    l.mode,
    l.granted,
    l.relation::regclass AS relation
FROM pg_catalog.pg_locks AS l
JOIN pg_catalog.pg_stat_activity AS a
  ON a.pid = l.pid
WHERE l.relation = 'lesson_vacuum.accounts'::regclass
ORDER BY l.granted, a.pid;
```

Query chỉ là góc nhìn lock hiện tại; cần ghép blocked/blocking PIDs và query text để tìm nguyên nhân.

## 61. Dead tuples sau UPDATE và DELETE

Thực hành:

```sql
CREATE TABLE lesson_vacuum.churn_demo (
    id BIGINT PRIMARY KEY,
    payload TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

INSERT INTO lesson_vacuum.churn_demo (id, payload)
SELECT g, repeat('x', 100)
FROM generate_series(1, 100000) AS g;

UPDATE lesson_vacuum.churn_demo
SET payload = payload || '-v2',
    updated_at = clock_timestamp();

DELETE FROM lesson_vacuum.churn_demo
WHERE id % 10 = 0;
```

Sau khi commit, kiểm tra thống kê:

```sql
SELECT
    relname,
    n_live_tup,
    n_dead_tup,
    n_tup_ins,
    n_tup_upd,
    n_tup_del,
    n_tup_hot_upd
FROM pg_catalog.pg_stat_user_tables
WHERE relid = 'lesson_vacuum.churn_demo'::regclass;
```

Counters có thể cập nhật trễ/ước lượng và phụ thuộc statistics collector. Đây là bài thực hành minh họa tạo churn, không phải phép đo chính xác ngay lập tức sau statement.

## 62. Quan sát trước và sau VACUUM

Chạy:

```sql
VACUUM (VERBOSE) lesson_vacuum.churn_demo;
```

Sau đó truy vấn lại:

```sql
SELECT
    relname,
    n_live_tup,
    n_dead_tup,
    last_vacuum,
    last_autovacuum,
    vacuum_count,
    autovacuum_count
FROM pg_catalog.pg_stat_user_tables
WHERE relid = 'lesson_vacuum.churn_demo'::regclass;
```

### Kỳ vọng

Nếu không có transaction cũ giữ horizon và VACUUM hoàn tất, dead tuples có thể giảm đáng kể. Số liệu thống kê vẫn là estimate và có thể cần đợi cập nhật; output VERBOSE cung cấp thông tin cụ thể hơn về công việc thực hiện.

### Không kỳ vọng file nhỏ lại

Kiểm tra:

```sql
SELECT
    pg_size_pretty(pg_relation_size(
        'lesson_vacuum.churn_demo'
    )) AS heap_size,
    pg_size_pretty(pg_total_relation_size(
        'lesson_vacuum.churn_demo'
    )) AS total_size;
```

VACUUM có thể tạo reusable space mà không làm relation file giảm rõ.

## 63. HOT update counters

Để quan sát HOT:

```sql
SELECT
    relname,
    n_tup_upd,
    n_tup_hot_upd,
    CASE
        WHEN n_tup_upd > 0
        THEN round(
            100.0 * n_tup_hot_upd / n_tup_upd,
            2
        )
        ELSE 0
    END AS hot_update_pct
FROM pg_catalog.pg_stat_user_tables
WHERE schemaname = 'lesson_vacuum';
```

### Diễn giải

Tỷ lệ HOT cao có thể giảm index churn cho update workload, nhưng không phải mục tiêu tối ưu duy nhất. Nếu updates thường đổi indexed columns hoặc page không đủ free space, HOT rate có thể thấp.

### Thử nghiệm

So sánh update trên cột không index và cột có index; quan sát n_tup_hot_upd, relation/index sizes và throughput trên dữ liệu đủ lớn.

## 64. Một ví dụ giữ snapshot để thấy vacuum không dọn được

Tạo một row:

```sql
INSERT INTO lesson_vacuum.churn_demo (id, payload)
VALUES (200001, 'original');
```

**Session A**:

```sql
BEGIN ISOLATION LEVEL REPEATABLE READ;
SELECT payload
FROM lesson_vacuum.churn_demo
WHERE id = 200001;
```

**Session B**:

```sql
UPDATE lesson_vacuum.churn_demo
SET payload = 'changed'
WHERE id = 200001;
COMMIT;

VACUUM (VERBOSE) lesson_vacuum.churn_demo;
```

Khi A còn mở transaction, phiên bản cũ có thể vẫn cần thiết. Kết thúc A:

```sql
COMMIT;
```

Sau đó chạy VACUUM lần nữa. Nếu không có horizon blocker khác, phiên bản cũ có thể được thu hồi.

### Kết luận thực hành

VACUUM không bị “lỗi” khi không dọn tuple còn visible với snapshot cũ. Đó là yêu cầu đúng đắn của MVCC.

## 65. Kiểm tra bloat và free space

Không có một cột duy nhất trong `pg_stat_user_tables` cho biết chính xác số bytes có thể thu hồi ngay. Các số `n_dead_tup`, `n_live_tup` là ước lượng row counts, không cho biết tuple width/page density/index bloat đầy đủ.

### Công cụ điều tra

- `pg_relation_size` và `pg_total_relation_size`.
- `pgstattuple` extension nếu được phép cài và chi phí scan phù hợp.
- `pg_stat_user_tables` dead tuple estimates.
- `pg_stat_progress_vacuum`.
- Index size và query plans.
- OS/provider disk metrics.

### pgstattuple

Extension `pgstattuple` có thể đo live/dead/free space cho relation, nhưng việc quét một bảng lớn có thể tốn I/O. Chỉ dùng sau khi đánh giá quyền, phiên bản, impact và môi trường.

Đừng tự kết luận bloat 50% chỉ từ phép tính dead_tup/(live_tup+dead_tup).

## 66. VACUUM index cleanup

Khi dead heap tuples được thu hồi, các index entries tương ứng cũng cần được xử lý theo chiến lược vacuum/index access method. Với nhiều indexes, phần index cleanup có thể tốn thời gian đáng kể.

### Một số option

Các PostgreSQL versions hiện đại có tùy chọn như `INDEX_CLEANUP` cho một số cách điều khiển index cleanup:

```sql
-- Ví dụ minh họa; xem tài liệu phiên bản trước khi sử dụng:
VACUUM (INDEX_CLEANUP AUTO) lesson_vacuum.churn_demo;
```

`AUTO` cho phép PostgreSQL quyết định theo điều kiện/heuristics. Không dùng `INDEX_CLEANUP OFF` như giải pháp thường xuyên để vacuum chạy nhanh mà bỏ lại index cleanup debt.

### Tại sao cẩn thận?

Nếu index entries chứa dead TIDs không được dọn, index có thể tiếp tục lớn hoặc phát sinh chi phí cho scans. Tùy workload/version, trì hoãn index cleanup có thể chỉ chuyển chi phí sang lần vacuum sau.

## 67. Vacuum failsafe

Ở các phiên bản hỗ trợ, `vacuum_failsafe_age` và cơ chế failsafe giúp vacuum ưu tiên chống wraparound khi tuổi XID tiến sát ngưỡng nghiêm trọng. Failsafe có thể giảm một số cost delays hoặc bỏ qua một số công việc không thiết yếu để đẩy nhanh freeze.

### Điều đó không có nghĩa nên dựa vào failsafe

Failsafe là **lớp bảo vệ cuối**, không phải kế hoạch bảo trì. Nếu alert chỉ xuất hiện khi failsafe đã kích hoạt, hệ thống có thể đã ở tình huống rủi ro và phải xử lý gấp.

### Theo dõi

- XID age trend.
- `relfrozenxid` theo relation.
- `datfrozenxid` theo database.
- MultiXact age.
- Autovacuum worker backlog.
- Transaction/replication horizons.

Đặt alert sớm hơn ngưỡng failsafe để có thời gian điều tra.

## 68. Database có nhiều tables nhỏ

Một database có hàng chục nghìn tables nhỏ có thể khiến autovacuum launcher phải kiểm tra nhiều relations và workers chia thời gian cho nhiều jobs.

### Tác động

- Overhead catalog/scheduling.
- Nhiều vacuum/analyze jobs ngắn.
- Worker contention.
- Threshold tuyệt đối/scale factor khác nhau giữa tables.

### Hướng xử lý

- Giảm số relations không cần thiết.
- Partition theo thiết kế có kiểm soát, tránh một partition cho mỗi key nhỏ.
- Cấu hình thresholds hợp lý theo nhóm workload.
- Theo dõi vacuum counts và scheduling backlog.
- Không tăng workers vô hạn khi CPU/I/O đã bão hòa.

## 69. Ví dụ tuning cho bảng write-heavy

Giả sử bảng orders có 50 triệu rows và nhận 5 triệu UPDATE/DELETE mỗi ngày. Nếu scale factor quá cao, bảng có thể tích tụ nhiều dead tuples trước lần vacuum kế tiếp.

Một cấu hình thử nghiệm:

```sql
ALTER TABLE lesson_vacuum.churn_demo
SET (
    autovacuum_vacuum_threshold = 2000,
    autovacuum_vacuum_scale_factor = 0.01,
    autovacuum_analyze_threshold = 1000,
    autovacuum_analyze_scale_factor = 0.005
);
```

Các giá trị này **không phải khuyến nghị mặc định**. Mục đích là minh họa giảm tỷ lệ scale cho một bảng lớn. Trước khi áp dụng, đo dead tuples tích lũy, thời gian vacuum, tốc độ tạo dead tuples, CPU/I/O, query latency và autoanalyze frequency.

Nếu vacuum chạy quá thường xuyên và gây I/O contention, ngưỡng có thể quá thấp. Nếu dead tuples tăng nhanh hơn vacuum cleanup, ngưỡng có thể quá cao hoặc vacuum throughput/horizon đang bị chặn.

## 70. Ví dụ bảng append-only

Một bảng event chỉ INSERT:

```sql
CREATE TABLE lesson_vacuum.events (
    event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL,
    payload JSONB NOT NULL
);
```

Ít UPDATE/DELETE không có nghĩa không cần VACUUM:

- Tuples mới cần được freeze theo thời gian.
- Visibility map có thể được cập nhật cho index-only scans.
- Statistics cần phản ánh row count và phân bố mới.

Trong bảng append-only rất lớn, theo dõi insert-triggered vacuum và analyze thresholds, XID age, VM coverage và retention strategy.

## 71. Retention bằng DELETE và bằng partition drop

### DELETE theo thời gian

```sql
DELETE FROM lesson_vacuum.events
WHERE occurred_at < now() - interval '90 days';
```

DELETE tạo dead tuples; VACUUM cần dọn chúng. Một lệnh DELETE hàng triệu rows có thể tạo transaction lớn, WAL nhiều và bloat trước khi vacuum.

### Partition retention

Nếu bảng partition theo thời gian, có thể detach/drop partition cũ theo retention policy. Thao tác DDL này loại một relation/partition thay vì tạo dead tuples cho từng row.

### Trade-off

- DELETE cho phép retention theo điều kiện row-level linh hoạt nhưng tạo churn và vacuum work.
- Drop partition có thể nhanh hơn với dữ liệu phân vùng rõ, nhưng có DDL locks/dependencies và không tạo row-level DELETE audit.

Không chọn partitioning chỉ để tránh VACUUM; các truy vấn, uniqueness, FK và lifecycle của partition cũng phải phù hợp.

## 72. VACUUM và autovacuum trên hệ thống có write spikes

Một batch update lớn có thể vượt threshold rất nhanh. Autovacuum bắt đầu sau khi worker được lên lịch; trong khoảng đó dead tuples vẫn tích tụ.

### Biện pháp

- Chia batch updates để giới hạn transaction size.
- Chạy ANALYZE sau bulk load nếu planner cần statistics mới.
- Chọn per-table thresholds phù hợp.
- Đảm bảo autovacuum workers/cost budget đủ headroom.
- Tránh transaction lâu giữ snapshot.
- Theo dõi WAL, replica lag và vacuum progress.

### Không chạy VACUUM sau mỗi statement

VACUUM sau từng UPDATE nhỏ thường tạo overhead và không cần thiết. Để autovacuum gom công việc theo ngưỡng, trừ khi có một lý do vận hành cụ thể để vacuum thủ công.

## 73. ANALYZE và thống kê đa cột

Nếu planner ước lượng sai các điều kiện tương quan giữa columns, ANALYZE mặc định có thể chưa đủ cho một số query.

Ví dụ:

```sql
CREATE STATISTICS lesson_vacuum.stats_tenant_status
(dependencies, mcv)
ON tenant_id, status
FROM lesson_vacuum.accounts;

ANALYZE lesson_vacuum.accounts;
```

Extended statistics giúp planner mô hình hóa một số quan hệ giữa columns. Nó không thay VACUUM và không phải mọi query đều sử dụng mọi loại statistics.

## 74. VACUUM trong môi trường managed PostgreSQL

Managed database thường vẫn chạy PostgreSQL autovacuum, nhưng người dùng có thể không được quyền:

- Đọc mọi server logs.
- Thay đổi mọi postgresql.conf settings.
- Terminate mọi backend.
- Cài extensions tùy ý.
- Truy cập filesystem trực tiếp.

### Cách vận hành

- Dùng views và metrics mà provider cho phép.
- Xem provider alerts về XID age/wraparound.
- Theo dõi replica/slot lag qua control plane.
- Dùng parameter groups/flags được hỗ trợ.
- Liên hệ provider trước khi can thiệp vào anti-wraparound emergency.

Không giả định superuser trên managed service có quyền tương đương PostgreSQL self-hosted superuser.

## 75. Các cảnh báo wraparound cần phân biệt

Khi XID age tiến gần ngưỡng, PostgreSQL có thể log cảnh báo về database/table cần vacuum freeze. Nếu tiến sát giới hạn nghiêm trọng, server có thể bắt đầu chặn writes để bảo vệ dữ liệu.

### Phản ứng đúng

1. Xác định database và relation có XID age cao nhất.
2. Kiểm tra autovacuum workers có đang chạy hay bị chặn.
3. Tìm long-running transactions, prepared transactions.
4. Kiểm tra replication slots và standby feedback.
5. Đảm bảo disk/CPU/I/O đủ để vacuum hoàn thành.
6. Chạy manual VACUUM FREEZE theo kế hoạch và quyền phù hợp nếu cần.
7. Theo dõi age giảm và relfrozenxid tiến triển.

### Không chỉ tăng max_connections hoặc restart

Restart không tự freeze tuples. Tăng connections cũng không giúp; thậm chí có thể thêm tải. Mục tiêu là để vacuum tiến triển và giải phóng horizon blocker.

## 76. VACUUM FREEZE và khi nào dùng

```sql
VACUUM (FREEZE, VERBOSE) lesson_vacuum.churn_demo;
```

Đây là lệnh top-level, không nằm trong transaction block.

### Tác dụng

Yêu cầu VACUUM freeze tuples theo chính sách tương ứng; hữu ích trong một số kịch bản bảo trì, chuẩn bị snapshot/clone hoặc xử lý freeze age.

### Cẩn trọng

- Quét relation lớn có thể gây I/O đáng kể.
- Không giải quyết được tuple còn cần bởi snapshot cũ theo cách bỏ qua visibility.
- Không thay việc tìm horizon blockers.
- Không nên chạy tùy tiện trên mọi bảng production cùng lúc.

Autovacuum bình thường đã quản lý freeze; manual FREEZE cần một lý do cụ thể.

## 77. Cấu hình vacuum failsafe và cost

Xem các settings liên quan:

```sql
SELECT
    name,
    setting,
    unit,
    context
FROM pg_catalog.pg_settings
WHERE name IN (
    'autovacuum_freeze_max_age',
    'vacuum_failsafe_age',
    'vacuum_cost_delay',
    'vacuum_cost_limit',
    'autovacuum_vacuum_cost_delay',
    'autovacuum_vacuum_cost_limit'
)
ORDER BY name;
```

Không tăng các age thresholds quá cao để trì hoãn freeze. Mức giới hạn an toàn của XID/MultiXact là một bảo vệ toàn database; đẩy ngưỡng lên có thể làm giảm thời gian phản ứng trước wraparound.

## 78. Các relation nào đang có XID age cao?

Truy vấn mở rộng:

```sql
SELECT
    n.nspname,
    c.relname,
    c.relkind,
    age(c.relfrozenxid) AS xid_age,
    mxid_age(c.relminmxid) AS mxid_age,
    c.reltuples,
    pg_size_pretty(pg_total_relation_size(c.oid)) AS total_size
FROM pg_catalog.pg_class AS c
JOIN pg_catalog.pg_namespace AS n
  ON n.oid = c.relnamespace
WHERE c.relkind IN ('r', 'm', 't')
ORDER BY age(c.relfrozenxid) DESC
LIMIT 50;
```

### Lưu ý về relkind

Các loại relation được đưa vào danh sách là những loại có thể có storage liên quan. Một số internal/system relations cũng quan trọng cho catalog freeze; không lọc chỉ schema ứng dụng khi điều tra cảnh báo wraparound toàn database.

## 79. Kiểm tra table có vacuum lâu chưa

```sql
SELECT
    schemaname,
    relname,
    last_autovacuum,
    last_vacuum,
    autovacuum_count,
    vacuum_count,
    n_dead_tup,
    n_live_tup
FROM pg_catalog.pg_stat_user_tables
ORDER BY last_autovacuum NULLS FIRST;
```

Một bảng không có last_autovacuum không tự động là vấn đề. Kết hợp số rows, churn, relfrozenxid age và insert/update rate để đánh giá.

## 80. Vì sao autovacuum có thể bị cancel?

Một số tình huống:

- DDL hoặc lock conflict.
- Relation bị drop/alter trong lúc worker đang xử lý.
- Server shutdown/restart.
- Worker bị terminate bởi administrator.
- Resource pressure hoặc lỗi storage.

Autovacuum sẽ có thể thử lại ở vòng scheduling sau, nhưng nếu cùng nguyên nhân lặp lại thì backlog tăng. Theo dõi logs và `pg_stat_progress_vacuum`, không chỉ nhìn lần chạy thất bại.

### Cẩn thận với migration

Migration chờ lock của autovacuum hoặc vacuum chờ DDL lock có thể tạo chuỗi blocking. Dùng lock timeout và lịch deploy hợp lý, nhưng không tắt autovacuum rộng rãi để migration “chạy cho nhanh”.

## 81. Runbook: dead tuples tăng liên tục

Khi dashboard cho thấy số dead tuples tăng qua nhiều lần scrape:

1. Xác định top tables theo estimated dead tuples và total relation size.
2. So tốc độ tăng với autovacuum_count/last_autovacuum.
3. Kiểm tra pg_stat_progress_vacuum xem worker có chạy/tiến triển không.
4. Kiểm tra transactions cũ và backend_xmin.
5. Kiểm tra replication slots, prepared transactions và standby feedback.
6. Đo I/O, CPU, WAL và replica lag.
7. Xem reloptions của table và global thresholds.
8. Xác định dead tuples có được dọn nhưng file giữ space để reuse hay không.
9. Điều chỉnh threshold/cost/workers có kiểm soát.
10. Theo dõi xu hướng sau thay đổi, không chỉ một lần query.

### Không nhầm bloat với dead tuple estimate

Nếu dead tuples giảm nhưng relation size không giảm, VACUUM có thể vẫn làm đúng nhiệm vụ: space đã được thu hồi để reuse. Nếu bloat thật sự ảnh hưởng query/storage, cần đo heap/index separately và lên kế hoạch rewrite/reindex phù hợp.

## 82. Runbook: autovacuum không dọn được dù worker hoàn tất

Nếu một vacuum hoàn tất nhưng dead tuple estimate còn cao:

1. Xem VACUUM VERBOSE/autovacuum log để biết số tuples còn lại.
2. Kiểm tra long-running transactions và snapshot horizons.
3. Kiểm tra replication slot xmin/catalog_xmin.
4. Kiểm tra standby feedback và query lâu trên replica.
5. Kiểm tra prepared transactions.
6. Kiểm tra relation có continuous writes trong lúc vacuum.
7. Xác định vacuum có bị giới hạn bởi index cleanup/cost.

Nếu tuple vẫn có thể visible với snapshot đang tồn tại, vacuum **không được phép** loại bỏ nó. Hãy giải quyết horizon blocker theo business/replication policy, không ép vacuum bỏ qua visibility.

## 83. Runbook: XID age tiến sát ngưỡng

1. Đọc age(datfrozenxid) và mxid_age(datminmxid) theo database.
2. Tìm relations có age(relfrozenxid)/MultiXact age cao.
3. Xem autovacuum workers, progress và logs.
4. Xác định old snapshots, prepared transactions và replication slots.
5. Xác nhận disk còn đủ để vacuum tiến triển.
6. Hạn chế workloads không thiết yếu tạo thêm churn/transactions nếu cần.
7. Chạy manual VACUUM/FREEZE theo phiên bản, quyền và kế hoạch phù hợp.
8. Theo dõi tuổi XID/MultiXact giảm và cảnh báo được giải quyết.
9. Sau sự cố, tìm nguyên nhân vì sao autovacuum không theo kịp.
10. Đặt alert sớm hơn để tránh lặp lại emergency.

### Không tùy tiện nâng freeze max age

Nâng ngưỡng không phải cách giải quyết vacuum chậm; nó trì hoãn cảnh báo/forced work và có thể giảm safety margin.

## 84. Runbook: query chậm do table/index bloat

1. Đo latency và buffers bằng EXPLAIN (ANALYZE, BUFFERS) trên workload đại diện.
2. Xem statistics có stale không; chạy ANALYZE khi cần.
3. Xem dead tuple estimates và vacuum history.
4. Kiểm tra long snapshots và vacuum progress.
5. Đo heap/index sizes và free space bằng công cụ phù hợp.
6. Kiểm tra HOT update rate, indexes và fillfactor.
7. Chọn VACUUM thường, REINDEX hoặc rewrite tùy phần bloat.
8. Đánh giá lock/disk/WAL/replica impact.
9. Thử trong staging/maintenance window.
10. Xác nhận query plans/latency sau xử lý.

Không chạy VACUUM FULL chỉ vì một query chậm; query plan, index design, locks hoặc I/O có thể là nguyên nhân khác.

## 85. Checklist thiết kế autovacuum

### Workload

- Table nào insert-heavy, update-heavy, delete-heavy?
- Tốc độ churn theo giờ/ngày là bao nhiêu?
- Table/partition size và tuple width?
- Có index/TOAST/audit overhead nào lớn?
- Query latency cần statistics freshness tới mức nào?

### Cấu hình

- Autovacuum và track_counts có bật không?
- Threshold/scale factor có phù hợp với table lớn?
- Insert-triggered vacuum có cần tune?
- Có đủ workers/cost/memory budget?
- Per-table reloptions có bị vô hiệu hóa ngoài ý muốn?

### Horizon và an toàn

- Có transaction/idle-in-transaction lâu?
- Prepared transactions còn sót?
- Replication slots inactive giữ xmin/WAL?
- Standby feedback có giữ horizon quá lâu?
- XID/MultiXact age có alert?

### Quan sát

- Dashboard dead tuples, vacuum/analyze timestamps/counts.
- pg_stat_progress_vacuum và autovacuum logs.
- pg_stat_activity/backend_xmin/wait events.
- Database/table XID age.
- Disk/WAL/replication lag.

## 86. Các nguyên tắc dễ hiểu nhầm

**“DELETE xóa row khỏi file ngay.”** Không. DELETE đánh dấu phiên bản không còn visible; cleanup đến sau.

**“UPDATE chỉ ghi đè giá trị cũ.”** Thường tạo tuple version mới theo MVCC.

**“VACUUM xong thì file phải nhỏ lại.”** Không. Phần lớn space được tái sử dụng bên trong relation.

**“VACUUM FULL là VACUUM nhanh hơn.”** Không. Nó rewrite relation, cần lock mạnh và có thể chặn workload.

**“ANALYZE dọn dead tuples.”** Không. ANALYZE cập nhật planner statistics.

**“VACUUM luôn có thể xóa mọi dead tuple.”** Không nếu snapshot horizon còn cần tuple.

**“Idle connection giữ vacuum horizon.”** Không nhất thiết. Session idle ngoài transaction thường không giữ snapshot như idle-in-transaction.

**“Autovacuum bật nghĩa là không cần giám sát.”** Không. Threshold, worker capacity, horizon và I/O vẫn có thể làm vacuum tụt lại.

**“Bảng append-only không cần vacuum.”** Không. Freeze và visibility map vẫn quan trọng.

**“n_dead_tup là số dead tuples chính xác.”** Không. Đây là estimate.

**“Tăng autovacuum_max_workers luôn làm vacuum nhanh hơn.”** Không. Nó tăng số jobs đồng thời và có thể làm I/O contention nặng hơn.

**“Giảm scale factor luôn tốt.”** Không. Quá thấp có thể tạo vacuum/analyze liên tục.

**“Tắt autovacuum trên bảng sẽ loại bỏ mọi anti-wraparound vacuum.”** Không. PostgreSQL có cơ chế bảo vệ wraparound đặc biệt.

**“Replication slot chỉ giữ WAL.”** Không. Logical slots có thể giữ xmin/catalog_xmin và cản cleanup.

**“hot_standby_feedback chỉ có lợi.”** Không. Nó giảm recovery conflicts nhưng có thể giữ dead tuples ở primary.

**“VACUUM FREEZE bỏ qua transaction cũ.”** Không. Visibility horizon vẫn phải được tôn trọng.

**“Index-only scan không đọc heap.”** Không phải luôn luôn; visibility map quyết định có cần heap fetches hay không.

**“Tăng fillfactor làm mọi UPDATE thành HOT.”** Không. HOT còn phụ thuộc indexed columns và page free space.

**“Partition drop tương đương DELETE từng row.”** Không. Đây là DDL/storage operation khác.

## 87. Bài tập thực hành

### Bài 1 — MVCC là gì?

Giải thích vì sao PostgreSQL dùng nhiều tuple versions thay vì ghi đè row trực tiếp cho mọi UPDATE.

### Bài 2 — xmin và xmax

Mô tả vai trò khái niệm của xmin/xmax. Vì sao xmax không phải lúc nào cũng đơn giản là transaction ID của DELETE?

### Bài 3 — Hai sessions

Mở hai sessions như ví dụ REPEATABLE READ. Session A đọc balance, B cập nhật/commit. Vì sao A vẫn thấy giá trị cũ?

### Bài 4 — DELETE

DELETE một row rồi giải thích vì sao file heap không lập tức giảm kích thước.

### Bài 5 — Dead tuples

UPDATE cùng một row 100 lần. Mô tả tuple versions và điều kiện để các phiên bản cũ được reclaim.

### Bài 6 — Heap pruning

Phân biệt pruning trên page với VACUUM quét relation và xử lý indexes/visibility metadata.

### Bài 7 — VACUUM thường

Chạy VACUUM trên bảng lab. Nêu những công việc nó thực hiện và các việc nó không làm.

### Bài 8 — Space reuse

Xóa phần lớn rows, VACUUM rồi đo pg_relation_size. Vì sao size có thể không giảm dù space đã reusable?

### Bài 9 — VACUUM FULL

So sánh lock, rewrite, disk requirements và availability giữa VACUUM và VACUUM FULL.

### Bài 10 — ANALYZE

Chạy ANALYZE sau bulk load. Giải thích vì sao statistics có thể thay đổi query plan dù dead tuple count gần bằng 0.

### Bài 11 — Visibility map

Giải thích all-visible và all-frozen bits. Vì sao vacuum có thể giúp index-only scans giảm heap fetches?

### Bài 12 — Index-only scan

Tạo index có INCLUDE column, chạy EXPLAIN (ANALYZE, BUFFERS) và quan sát Heap Fetches trước/sau VACUUM.

### Bài 13 — HOT update

Update cột không được index và cột được index. So sánh n_tup_upd/n_tup_hot_upd.

### Bài 14 — Fillfactor

Đặt fillfactor thấp hơn trên bảng lab, chạy update workload và đo HOT rate, heap size. Vì sao không nên áp dụng cho mọi bảng?

### Bài 15 — XID wraparound

Giải thích transaction ID 32-bit quay vòng tạo nguy cơ gì nếu tuple cũ không được freeze.

### Bài 16 — Freeze

Vì sao tuple đang live vẫn có thể cần freeze? Freeze có làm mất dữ liệu nghiệp vụ không?

### Bài 17 — MultiXact

Giải thích MultiXact khác XID đơn lẻ thế nào và vì sao phải theo dõi mxid age.

### Bài 18 — Database age

Chạy truy vấn age(datfrozenxid) và mxid_age(datminmxid). Vì sao các giá trị không phải số ngày?

### Bài 19 — Table age

Dùng pg_class.relfrozenxid/relminmxid để tìm relations có age cao. Vì sao cần xem cả system/catalog relations?

### Bài 20 — Autovacuum thresholds

Tính threshold khi bảng có 20 triệu rows, vacuum threshold 50 và scale factor 0.05. Nêu các giả định của phép tính.

### Bài 21 — Autoanalyze

Tính ngưỡng analyze cho bảng 5 triệu rows, threshold 100, scale factor 0.02. Vì sao insert-only table vẫn cần autoanalyze?

### Bài 22 — Insert-triggered vacuum

Giải thích vai trò autovacuum_vacuum_insert_threshold và autovacuum_vacuum_insert_scale_factor trên bảng append-only.

### Bài 23 — Workers

Một server có nhiều bảng cùng vượt ngưỡng. Nêu khi nào tăng autovacuum_max_workers có ích và khi nào làm I/O contention tệ hơn.

### Bài 24 — Cost delay

So sánh autovacuum_vacuum_cost_limit và autovacuum_vacuum_cost_delay. Tác động của cost limit cao/thấp tới throughput và foreground latency?

### Bài 25 — Per-table settings

Đặt autovacuum scale factor thấp cho một bảng write-heavy. Theo dõi reloptions và đo kết quả trước/sau.

### Bài 26 — Long-running transaction

Giữ một REPEATABLE READ transaction mở, UPDATE cùng row ở session khác rồi chạy VACUUM. Giải thích vì sao old tuple còn lại.

### Bài 27 — Idle in transaction

Tìm sessions idle in transaction lâu bằng pg_stat_activity. Nêu rủi ro với vacuum horizon và cách phòng tránh trong application.

### Bài 28 — Prepared transaction

Đọc pg_prepared_xacts. Vì sao không tự ROLLBACK PREPARED một transaction cũ nếu chưa xác nhận trạng thái coordinator?

### Bài 29 — Replication slot

Truy vấn pg_replication_slots và giải thích xmin, catalog_xmin, restart_lsn. Một logical slot inactive có thể gây những vấn đề gì?

### Bài 30 — Standby feedback

Bật/tắt hot_standby_feedback trong môi trường lab phù hợp. So sánh recovery conflicts trên standby và dead tuple retention trên primary.

### Bài 31 — VACUUM progress

Trong khi vacuum một bảng lớn, truy vấn pg_stat_progress_vacuum. Giải thích các phases và vì sao heap_blks_scanned không phải toàn bộ phần trăm job trong mọi thời điểm.

### Bài 32 — Autovacuum logs

Đặt log_autovacuum_min_duration trong môi trường lab, tạo churn và đọc logs. Những thông tin nào giúp biết vacuum có theo kịp?

### Bài 33 — Dead tuple estimates

Truy vấn n_live_tup/n_dead_tup. Vì sao không dùng dead_pct đơn lẻ để kết luận bloat?

### Bài 34 — Partitioned tables

Tạo partitioned parent và vài leaf partitions. Quan sát autovacuum trên leaves; chạy ANALYZE parent sau khi load và giải thích vì sao cần bước đó ở nhiều versions.

### Bài 35 — TOAST

Nạp JSONB payload lớn, update payload nhiều lần. Đo pg_total_relation_size và giải thích vì sao TOAST cũng cần vacuum.

### Bài 36 — Temporary tables

Tạo TEMP table nhiều rows, ANALYZE và kiểm tra statistics. Vì sao autovacuum daemon không tự xử lý temp table của session?

### Bài 37 — DELETE retention

Xóa dữ liệu cũ theo timestamp, đo dead tuples/WAL, chạy VACUUM. So sánh với retention bằng partition drop.

### Bài 38 — VACUUM FREEZE

Chạy VACUUM (FREEZE, VERBOSE) trên bảng lab. Giải thích mục tiêu và vì sao không nên chạy đồng loạt trên mọi bảng production.

### Bài 39 — Xử lý wraparound alert

Thiết kế runbook khi age(datfrozenxid) tăng nhanh. Bao gồm tìm blocker, kiểm tra workers, replication slots, disk và manual freeze plan.

### Bài 40 — Thiết kế vận hành tổng hợp

Một PostgreSQL server có:

- Một bảng orders 100 triệu rows, UPDATE 5 triệu rows/ngày.
- Một bảng events append-only 1 tỷ rows.
- Một logical replication slot thỉnh thoảng inactive.
- Một reporting transaction có thể chạy 45 phút.
- Nhiều partitions theo tháng.
- Một API OLTP nhạy p99 latency.

Hãy thiết kế:

1. Autovacuum thresholds/scale factors cho từng nhóm bảng.
2. Insert-triggered vacuum và autoanalyze cho events.
3. Worker/cost/memory budget theo CPU/I/O.
4. Dashboard dead tuples, progress, XID/MultiXact age.
5. Runbook xử lý reporting snapshots và replication slot horizon.
6. Chính sách retention DELETE hay partition drop.
7. Kế hoạch ANALYZE parent/partitions và statistics.
8. Khi nào dùng VACUUM, VACUUM FREEZE, REINDEX hoặc VACUUM FULL.
9. Cách bảo vệ p99 latency và replica lag khi vacuum.
10. Alert/escalation trước wraparound failsafe.

## Kết luận

**MVCC tạo ra nhiều phiên bản tuple để readers nhìn thấy snapshot nhất quán trong khi writers tiếp tục thay đổi dữ liệu.** Vì UPDATE/DELETE không lập tức xóa các phiên bản cũ, PostgreSQL cần VACUUM để thu hồi dead tuples khi chúng không còn visible với bất kỳ snapshot nào cần chúng. VACUUM còn cập nhật visibility map, xử lý index cleanup và freeze tuple đủ cũ.

**Autovacuum là cơ chế bảo trì tự động thiết yếu**, không chỉ là tiện ích dọn rác. Nó dựa vào thresholds/scale factors, statistics, worker capacity và cost throttling để quyết định vacuum/analyze. Bảng lớn, write-heavy và append-only có thể cần cấu hình khác nhau; hãy đo dead tuple trends, vacuum duration, analyze freshness và XID/MultiXact age thay vì áp một bộ setting cho toàn database.

**Vacuum horizon là điều kiện cốt lõi:** long-running transactions, idle-in-transaction sessions, prepared transactions, replication slots và standby feedback có thể giữ phiên bản cũ, khiến vacuum không được phép dọn. Khi đó tăng workers không giải quyết được nguyên nhân; cần tìm và xử lý snapshot/replication blocker theo đúng nghiệp vụ.

Cuối cùng, VACUUM thường giúp PostgreSQL **tái sử dụng không gian**, không nhất thiết làm file nhỏ lại. VACUUM FULL rewrite relation và cần lock mạnh; ANALYZE cập nhật statistics; freezing ngăn XID/MultiXact wraparound. Vận hành tốt là kết hợp đúng công cụ, giám sát tiến độ/tuổi transaction, giữ transaction ngắn và có runbook trước khi database tiến gần ngưỡng khẩn cấp.

