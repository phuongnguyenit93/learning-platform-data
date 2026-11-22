# Fillfactor, HOT update và không gian trống trên trang trong PostgreSQL

Một bảng PostgreSQL có thể cập nhật hàng triệu lần mỗi ngày nhưng vẫn phát sinh nhiều chi phí không cần thiết nếu mỗi lần UPDATE đều phải tạo thêm index entries. Một phần quan trọng của việc tối ưu lưu trữ là hiểu **một hàng nằm ở đâu trên heap page, PostgreSQL tạo phiên bản hàng mới thế nào, và khi nào một UPDATE có thể trở thành HOT update**.

Hãy xét bảng trạng thái thiết bị:

- Mỗi thiết bị có một khóa định danh ổn định.
- Ứng dụng thường xuyên cập nhật `last_seen`, `status` và `heartbeat_at`.
- Các truy vấn chủ yếu tìm thiết bị theo `device_id`.
- Một số báo cáo lọc theo `status`.

Nếu một UPDATE chỉ thay đổi cột không được index tham chiếu và trang chứa hàng còn đủ chỗ, PostgreSQL có thể lưu phiên bản mới ngay trên **cùng heap page** mà không cần thêm entry vào các index. Đây là **Heap-Only Tuple update (HOT update)**.

Hai yếu tố quan trọng:

- **Fillfactor**: thiết lập mức độ lấp đầy mục tiêu của heap page khi PostgreSQL ghi các tuple mới, qua đó có thể để lại chỗ trống cho những lần cập nhật sau.
- **HOT update**: tối ưu MVCC cho phép tạo tuple version mới trên cùng page và tránh tạo index entries mới khi thỏa các điều kiện cần thiết.

Sơ đồ khái niệm:

```text
Heap page
+--------------------------------------------------+
| Page header | line pointers | tuple data         |
|              ^                                    |
|              |                                    |
|         free space                                |
|                                                  |
+--------------------------------------------------+
        |
        +-- UPDATE không đổi cột được index tham chiếu
        |      + đủ chỗ trên cùng page
        |              |
        |              v
        |          HOT update
        |          - tuple version mới cùng page
        |          - không thêm index entry mới
        |
        +-- thiếu chỗ hoặc thay đổi cột được index tham chiếu
                       |
                       v
                   Non-HOT update
                   - tuple version mới
                   - cần index maintenance
```

Bài học thuộc module **Database Engine Relational PostgreSQL**, chương **Lưu trữ**, tập trung vào **“Fillfactor, HOT update và không gian trống trên trang”**. Nội dung đi từ cấu trúc heap page và MVCC tới cách chọn fillfactor, theo dõi HOT ratio, sử dụng free space map, VACUUM/autovacuum và kiểm chứng bằng một lab có thể chạy trong database thực hành.

---

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích heap page, tuple, line pointer, page header và vùng free space.
2. Phân biệt không gian trống trong page với dung lượng trống của filesystem.
3. Giải thích tại sao UPDATE trong PostgreSQL thường tạo một tuple version mới theo MVCC.
4. Định nghĩa HOT update và nêu hai điều kiện cơ bản để HOT xảy ra.
5. Giải thích vì sao HOT update giảm index maintenance và hạn chế index bloat.
6. Hiểu HOT chain, tuple root, heap-only tuples và page pruning.
7. Phân biệt HOT update với UPDATE thông thường (non-HOT).
8. Hiểu vai trò của table `fillfactor` trong việc để lại chỗ trống trên heap page.
9. Phân biệt table fillfactor với B-tree index fillfactor.
10. Biết vì sao giảm fillfactor không tự động biến mọi UPDATE thành HOT.
11. Hiểu tác động của index key, `INCLUDE` columns, expression indexes và partial-index predicates tới HOT eligibility.
12. Nhận biết các ngoại lệ liên quan summarizing indexes như BRIN theo phiên bản PostgreSQL.
13. Dùng `ALTER TABLE ... SET (fillfactor=...)` và hiểu tác động lên dữ liệu đã tồn tại.
14. Phân biệt VACUUM thường, VACUUM FULL, CLUSTER và thao tác rewrite bảng.
15. Hiểu free space map (FSM) và cách nó hỗ trợ tìm page còn chỗ.
16. Đọc `n_tup_upd`, `n_tup_hot_upd` và tính HOT update ratio.
17. Sử dụng `pg_freespacemap`, `pgstattuple` và `pageinspect` khi cần chẩn đoán.
18. Hiểu tại sao HOT vẫn tạo tuple version, WAL và nhu cầu vacuum.
19. Đánh giá trade-off giữa page density, dung lượng bảng, read performance và update performance.
20. Thiết kế bảng update-heavy với các cột thay đổi thường xuyên được tách khỏi index khi phù hợp.
21. Tuning fillfactor theo workload thay vì chọn một con số cố định cho mọi bảng.
22. Áp dụng fillfactor và HOT considerations cho partitioned tables.
23. Kiểm thử hiệu quả bằng thống kê và workload thực tế, không chỉ nhìn một lần UPDATE thành công.

**Phạm vi:** PostgreSQL hiện đại. Kích thước page thường là 8 KB trong các bản build phổ biến, nhưng có thể khác tùy cách build. Một số tối ưu HOT liên quan summarizing indexes và công cụ thống kê/phân tích phụ thuộc phiên bản; cần xác nhận tài liệu đúng với cluster đang chạy.

---

## 2. Heap page là gì?

PostgreSQL lưu các hàng của một bảng thông thường trong các **heap pages**. Một relation được chia thành các block/page có kích thước cố định trong một bản build PostgreSQL.

Trong cấu hình phổ biến, một page có kích thước 8 KB, nhưng không nên hard-code giả định này vào mọi công cụ hoặc môi trường.

### 2.1. Cấu trúc page ở mức khái niệm

Một heap page chứa:

- **Page header**: thông tin quản lý page, LSN, checksum/flags và các offset liên quan.
- **Line pointer array**: các mục tham chiếu tới tuple nằm trong page.
- **Tuple data area**: bytes của các tuple.
- **Free space**: vùng chưa được sử dụng giữa line pointer array và tuple data.

Sơ đồ:

```text
Đầu page
+------------------------------------------------+
| PageHeaderData                                 |
+------------------------------------------------+
| ItemIdData / line pointer 1                    |
| ItemIdData / line pointer 2                    |
| ItemIdData / line pointer 3                    |
| ...                                            |
+------------------------------------------------+
|                                                |
|              FREE SPACE                        |
|                                                |
+------------------------------------------------+
| Tuple C                                        |
| Tuple B                                        |
| Tuple A                                        |
+------------------------------------------------+
Cuối page
```

Line pointer không phải bản thân hàng. Nó là một mục nhỏ giúp PostgreSQL tìm tuple trong page.

### 2.2. Tuple chứa gì?

Một heap tuple có thể chứa:

- Header của tuple.
- Transaction IDs và thông tin MVCC.
- Null bitmap khi cần.
- Dữ liệu các cột.
- Padding/alignment theo yêu cầu lưu trữ.
- Thông tin liên quan tới giá trị lớn có thể được TOAST.

Vì vậy, số bytes thực tế một hàng chiếm không đơn giản bằng tổng độ dài chuỗi mà ứng dụng nhìn thấy.

### 2.3. Page có free space để làm gì?

Free space có thể được sử dụng khi:

- INSERT tuple mới.
- Tạo tuple version mới trên cùng page trong một số UPDATE.
- Các thao tác quản lý tuple cần không gian phù hợp.

Đối với HOT, điều quan trọng là **phiên bản mới phải nằm được trên chính page chứa phiên bản cũ**.

### 2.4. Free space không phải dung lượng filesystem

Một bảng có thể chiếm 10 GB trên filesystem nhưng vẫn có hàng trăm MB free space bên trong các heap pages. PostgreSQL có thể tái sử dụng một phần không gian này mà không cần giảm kích thước file.

Ngược lại, một page trống không có nghĩa filesystem đã trả lại dung lượng cho hệ điều hành.

### 2.5. `ctid` là vị trí tuple, không phải khóa nghiệp vụ

`ctid` biểu diễn vị trí tuple trong relation, thường gồm block number và offset number. UPDATE có thể tạo version mới ở vị trí khác, nên `ctid` thay đổi.

Không dùng `ctid` làm primary key, business key hoặc định danh ổn định giữa các lần cập nhật.

---

## 3. MVCC: vì sao UPDATE tạo tuple version mới?

PostgreSQL dùng **Multi-Version Concurrency Control (MVCC)**. Thay vì ghi đè trực tiếp mọi giá trị của một hàng đang tồn tại, UPDATE thông thường tạo một phiên bản mới và đánh dấu phiên bản cũ không còn phù hợp với các snapshot tương lai theo quy tắc transaction visibility.

Ví dụ:

```sql
CREATE TABLE storage_lab.accounts (
    account_id BIGINT PRIMARY KEY,
    balance NUMERIC(12,2) NOT NULL
);

INSERT INTO storage_lab.accounts
VALUES (1, 1000.00);

UPDATE storage_lab.accounts
SET balance = 900.00
WHERE account_id = 1;
```

Về mặt khái niệm:

```text
Trước UPDATE:
  Tuple version A: balance = 1000

Sau UPDATE:
  Tuple version A: phiên bản cũ
  Tuple version B: balance = 900

Transaction/snapshot phù hợp có thể còn nhìn thấy A;
transaction mới hơn có thể nhìn thấy B.
```

### 3.1. Không phải mọi session đều nhìn thấy cùng version

MVCC cho phép các transaction đọc snapshot phù hợp mà không phải khóa mọi reader chỉ để ghi một hàng. Visibility phụ thuộc transaction IDs, snapshot và trạng thái commit.

### 3.2. Version cũ chưa thể xóa ngay

Nếu một transaction còn có thể cần đọc phiên bản cũ, PostgreSQL phải giữ nó. Tuple cũ chỉ có thể được dọn khi không còn snapshot cần nó theo quy tắc MVCC.

### 3.3. Dead tuples

Các tuple version không còn visible cho transaction nào có thể trở thành dead tuples. VACUUM có thể thu hồi không gian của chúng để tái sử dụng.

### 3.4. Vì sao UPDATE liên tục có thể làm bảng phình to?

Nếu một bảng được cập nhật thường xuyên:

- Nhiều tuple versions được tạo.
- Một số phiên bản cũ phải chờ snapshot kết thúc.
- Dead tuples cần được VACUUM/prune.
- Nếu index phải thêm entries mới, index cũng có thể tăng kích thước.

Đây là một phần lý do HOT và fillfactor có ý nghĩa.

### 3.5. HOT không loại bỏ MVCC

HOT vẫn tạo tuple version mới. Nó chỉ tối ưu cách các index tham chiếu tới các phiên bản đó. HOT không biến UPDATE thành ghi đè tại chỗ và không loại bỏ nhu cầu VACUUM.

---

## 4. HOT update là gì?

**HOT** là viết tắt của **Heap-Only Tuple**.

Một UPDATE có thể là HOT khi thỏa các điều kiện cơ bản:

1. UPDATE không sửa các cột được những index liên quan tham chiếu, theo quy tắc HOT của PostgreSQL.
2. Page chứa tuple cũ có đủ không gian để lưu tuple version mới trên **cùng page**.

Khi HOT thành công:

- PostgreSQL tạo tuple version mới trên cùng heap page.
- Index entries hiện có có thể tiếp tục dẫn tới tuple root của HOT chain.
- Không cần thêm index entry mới cho phiên bản mới.
- Các phiên bản cũ/mới được liên kết trong HOT chain và có thể được prune khi an toàn.

### 4.1. Ví dụ dễ hình dung

Bảng:

```sql
CREATE TABLE storage_lab.device_state (
    device_id BIGINT PRIMARY KEY,
    status TEXT NOT NULL,
    last_seen TIMESTAMPTZ NOT NULL
);
```

Giả sử chỉ có primary key index trên `device_id`.

Câu UPDATE:

```sql
UPDATE storage_lab.device_state
SET last_seen = clock_timestamp()
WHERE device_id = 1001;
```

`last_seen` không được index tham chiếu. Nếu page chứa hàng còn đủ chỗ, PostgreSQL có thể thực hiện HOT update.

### 4.2. Ví dụ khó trở thành HOT

Nếu tạo index:

```sql
CREATE INDEX device_state_last_seen_idx
ON storage_lab.device_state(last_seen);
```

rồi chạy:

```sql
UPDATE storage_lab.device_state
SET last_seen = clock_timestamp()
WHERE device_id = 1001;
```

UPDATE thay đổi cột `last_seen`, cột được index tham chiếu. Theo quy tắc HOT thông thường, cập nhật này không đủ điều kiện HOT.

### 4.3. HOT giảm điều gì?

Một non-HOT UPDATE thường cần index maintenance cho tuple version mới. HOT có thể tránh thêm index entries mới, giảm:

- Số index tuples được tạo.
- WAL liên quan tới index maintenance.
- Index bloat do nhiều phiên bản cập nhật.
- Chi phí cleanup các index entries chết.
- Một phần I/O và CPU cho index updates.

### 4.4. HOT không có nghĩa “không cần index”

Các index vẫn được dùng để tìm tuple root. HOT chỉ tránh phải tạo thêm index entries cho từng version trong chain khi thỏa điều kiện.

### 4.5. HOT không bảo đảm UPDATE nhanh trong mọi trường hợp

Câu UPDATE vẫn phải tìm hàng, kiểm tra điều kiện, khóa tuple phù hợp, ghi version mới, phát WAL và duy trì các semantics khác. Nếu bottleneck nằm ở lock contention, network hoặc WAL, HOT có thể không phải yếu tố chi phối.

---

## 5. HOT eligibility: index tham chiếu tới cột nào?

Điều kiện “không sửa cột được index tham chiếu” rộng hơn việc nhìn thấy tên cột trong một danh sách key đơn giản.

### 5.1. B-tree index trên cột trực tiếp

```sql
CREATE INDEX idx_device_status
ON storage_lab.device_state(status);
```

UPDATE thay đổi `status` thường không phải HOT vì `status` là index key.

### 5.2. INCLUDE columns

```sql
CREATE INDEX idx_device_status_cover
ON storage_lab.device_state(device_id)
INCLUDE (status);
```

Cột `status` được lưu trong index như included column. UPDATE thay đổi `status` có thể làm mất điều kiện HOT.

Đừng nghĩ INCLUDE là “không liên quan tới index maintenance”.

### 5.3. Expression index

```sql
CREATE INDEX idx_customer_lower_email
ON storage_lab.customers (lower(email));
```

Dù index definition không chỉ ghi `email` như một key đơn giản, expression phụ thuộc vào cột đó. UPDATE `email` có thể làm index entry cần thay đổi.

### 5.4. Partial index predicate

```sql
CREATE INDEX idx_active_devices
ON storage_lab.device_state(device_id)
WHERE status = 'ACTIVE';
```

Cột `status` xuất hiện trong predicate. Thay đổi status có thể làm hàng đi vào hoặc ra khỏi index, vì vậy có thể cần index maintenance và không đủ điều kiện HOT.

### 5.5. Một cột được nhiều index tham chiếu

Nếu một bảng có 5 index, HOT eligibility phải xét tất cả index liên quan. Một index duy nhất phụ thuộc vào cột đang thay đổi có thể làm UPDATE không còn là HOT.

### 5.6. Summarizing indexes và BRIN

Một số phiên bản PostgreSQL có ngoại lệ cho **summarizing indexes**, đáng chú ý là BRIN, vì index loại này tóm tắt phạm vi block thay vì lưu một TID entry cho từng hàng theo cách B-tree thông thường.

Không áp dụng quy tắc “bất cứ cột nào xuất hiện trong mọi index đều tuyệt đối cấm HOT” mà không kiểm tra tài liệu phiên bản và loại index đang dùng. Với B-tree và các index thông thường, hãy giả định cột được index tham chiếu là yếu tố cần xem xét chặt chẽ.

### 5.7. Xem định nghĩa index thực tế

```sql
SELECT
    indexrelid::regclass AS index_name,
    pg_catalog.pg_get_indexdef(indexrelid) AS index_definition
FROM pg_catalog.pg_index
WHERE indrelid = 'storage_lab.device_state'::regclass
ORDER BY indexrelid::regclass::TEXT;
```

Trước khi tuning HOT, hãy đọc index definitions thay vì chỉ nhìn primary key.

---

## 6. HOT chain và tuple root

Khi HOT update xảy ra, index entry không cần trỏ tới mỗi phiên bản mới. Thay vào đó, PostgreSQL sử dụng một **HOT chain** trên cùng heap page.

Mô hình khái niệm:

```text
Index entry
    |
    v
Root tuple A (phiên bản cũ)
    |
    | HOT link
    v
Tuple B (phiên bản kế tiếp)
    |
    | HOT link
    v
Tuple C (phiên bản mới hơn)
```

### 6.1. Vì sao gọi là Heap-Only Tuple?

Các version sau root được lưu trong heap page và không cần index entry riêng cho từng version. Chúng là heap-only tuples trong chain.

### 6.2. Index entry vẫn có tác dụng

Một index scan tìm tới root tuple. PostgreSQL có thể lần theo chain và xét visibility để tìm version phù hợp với snapshot.

### 6.3. HOT chain có thể dài

Nếu cùng một hàng được UPDATE nhiều lần trước khi các version cũ được prune, chain có thể chứa nhiều version.

Một chain dài có thể làm tăng công việc kiểm tra visibility khi truy cập hàng. Page pruning và VACUUM giúp dọn các phiên bản không còn cần thiết.

### 6.4. Page pruning

Khi an toàn theo MVCC, PostgreSQL có thể prune các tuple version chết trong page. Việc này có thể diễn ra khi page được truy cập hoặc trong VACUUM, tùy tình huống.

### 6.5. HOT không làm mất primary key

Index entry tiếp tục dẫn tới chain root. Khóa chính vẫn xác định hàng theo giá trị key, còn HOT chỉ thay đổi cách quản lý các tuple versions phía heap.

### 6.6. Không lưu ctid vào ứng dụng

Do HOT chain và các lần UPDATE có thể làm vị trí tuple thay đổi, `ctid` không phải identifier bền vững. Dùng primary key hoặc business key.

---

## 7. Fillfactor của heap table

**Table fillfactor** là storage parameter xác định mục tiêu phần trăm page space được lấp đầy bởi tuple data trong quá trình ghi dữ liệu.

Giá trị hợp lệ thường nằm trong khoảng **10 đến 100**; mặc định là **100**.

### 7.1. Fillfactor = 100

Mặc định PostgreSQL cố gắng sử dụng page space theo mục tiêu lấp đầy cao. Đây thường là lựa chọn hợp lý cho bảng chủ yếu INSERT và ít UPDATE.

### 7.2. Fillfactor = 80

```sql
CREATE TABLE storage_lab.device_state (
    device_id BIGINT PRIMARY KEY,
    status TEXT NOT NULL,
    last_seen TIMESTAMPTZ NOT NULL
) WITH (fillfactor = 80);
```

Mục tiêu là để lại một phần không gian trong heap pages khi ghi các tuple mới, tạo cơ hội để những UPDATE sau lưu version mới trên cùng page.

### 7.3. Fillfactor không phải cam kết chính xác mỗi page còn 20% trống

Page header, line pointers, tuple headers, alignment, kích thước hàng biến đổi và quá trình UPDATE/DELETE làm page fullness thay đổi.

Giá trị 80 không có nghĩa mọi page luôn còn đúng 20% bytes trống hoặc mọi hàng có thể tăng thêm 20% kích thước.

### 7.4. Fillfactor ảnh hưởng INSERT placement

Fillfactor chủ yếu tác động cách PostgreSQL lấp đầy các page khi ghi tuple mới. Khi page mới được sử dụng, hệ thống cố gắng giữ mức occupancy theo thiết lập.

### 7.5. Fillfactor tạo cơ hội, không bảo đảm HOT

Một UPDATE vẫn không HOT nếu:

- Thay đổi cột được index tham chiếu.
- Tuple version mới không vừa trong page cũ.
- Page không còn đủ chỗ vì dữ liệu biến đổi hoặc các cập nhật khác.
- Những điều kiện khác của HOT không được đáp ứng.

### 7.6. Fillfactor 100 vẫn có thể có HOT update

Nếu VACUUM/pruning đã thu hồi không gian, hoặc page còn chỗ vì dữ liệu thực tế chưa lấp đầy, một UPDATE trên cột không được index tham chiếu vẫn có thể là HOT.

Không nên hiểu fillfactor 100 là “tắt HOT”.

---

## 8. Vì sao fillfactor thấp có thể giúp bảng update-heavy?

Giả sử mỗi hàng có `device_id`, `status`, `last_seen`, `heartbeat_at`.

- `device_id` được dùng để tìm hàng và có primary key index.
- `last_seen` và `heartbeat_at` thay đổi thường xuyên.
- Truy vấn không cần index trên hai cột timestamp này.

Nếu các cột thường thay đổi không được index tham chiếu và page có đủ chỗ, HOT có thể xảy ra.

### 8.1. Giữ chỗ gần tuple cũ

HOT yêu cầu tuple version mới nằm trên cùng page. Để lại free space trên page lúc INSERT tăng xác suất version mới vừa vào page.

### 8.2. Giảm index churn

Nếu phần lớn UPDATE là HOT, index không phải nhận thêm entries cho mọi lần thay đổi trạng thái. Điều này có thể giảm tăng trưởng index.

### 8.3. Tăng hiệu quả page locality

Các version của một hàng nằm cùng page, giúp quá trình index lookup/visibility có cơ hội làm việc trong cùng một page thay vì cần nhiều heap pages.

### 8.4. Không nhất thiết mọi update-heavy table đều cần fillfactor thấp

Nếu ứng dụng thường xuyên sửa indexed columns, giảm fillfactor có thể làm bảng lớn hơn nhưng HOT vẫn không xảy ra cho những UPDATE đó.

### 8.5. Kích thước hàng thay đổi là yếu tố quan trọng

Nếu `description` tăng từ 100 bytes lên 2 KB, phần free space đã để lại có thể không đủ cho tuple version mới. HOT eligibility phải xét kích thước version thực tế.

### 8.6. Chọn fillfactor theo pattern, không theo tên bảng

Một bảng tên `events` có thể chỉ INSERT; bảng `sessions` có thể UPDATE liên tục. Tuning theo hành vi dữ liệu, không theo nhãn domain.

---

## 9. Trade-off khi giảm fillfactor

Fillfactor thấp hơn có thể giúp update-heavy workload nhưng phải trả chi phí.

| Lợi ích tiềm năng | Chi phí/rủi ro |
| --- | --- |
| Nhiều cơ hội HOT hơn | Nhiều heap pages hơn |
| Ít index entries mới hơn | Bảng có thể chiếm nhiều disk hơn |
| Giảm index churn/bloat | Full table scans đọc nhiều pages hơn |
| Có không gian cho tuple version | Buffer cache chứa ít rows hơn |
| Có thể giảm WAL/index maintenance | Backup và physical replication có thể truyền nhiều bytes hơn |
| Cải thiện một số update patterns | INSERT có thể dùng nhiều page hơn |

### 9.1. Read-heavy table

Nếu bảng hầu như không UPDATE và query thường scan nhiều hàng, fillfactor 100 có thể hợp lý hơn vì tăng density.

### 9.2. Update-heavy table

Nếu bảng thay đổi nhiều cột không index và HOT ratio thấp vì thiếu page space, thử giảm fillfactor trong staging/benchmark.

### 9.3. Bảng có hàng rất lớn

Một phần trăm free space trên page không đủ nếu tuple version mới lớn hơn khoảng trống thực tế. Cần kiểm tra row width, TOAST và update growth.

### 9.4. Bảng có nhiều partitions

Mỗi leaf partition có physical pages và storage parameters riêng. Không giả định đổi fillfactor trên partitioned parent tự động rewrite/tuning mọi partition đã tồn tại.

### 9.5. Không chọn 70 hoặc 80 theo cảm tính

Đây là các giá trị thử nghiệm phổ biến, không phải chuẩn tối ưu. Có thể thử 100, 90, 80 hoặc thấp hơn tùy dữ liệu và đo throughput, storage, read latency, HOT ratio.

---

## 10. Thay đổi fillfactor trên bảng đã tồn tại

Có thể đổi storage parameter:

```sql
ALTER TABLE storage_lab.device_state
SET (fillfactor = 80);
```

### 10.1. Có rewrite toàn bảng ngay không?

Không. `ALTER TABLE ... SET (fillfactor=80)` thay đổi storage parameter cho các thao tác ghi tiếp theo, không tự di chuyển toàn bộ tuple cũ để tạo 20% free space trên từng page hiện hữu.

### 10.2. Dữ liệu cũ vẫn nằm trên các page cũ

Những page đã lấp đầy có thể tiếp tục thiếu chỗ cho HOT. Chỉ đổi setting không có nghĩa HOT ratio lập tức tăng.

### 10.3. Khi nào free space xuất hiện?

- UPDATE/DELETE cũ tạo dead tuples.
- VACUUM/pruning thu hồi không gian để tái sử dụng.
- Page chưa từng lấp đầy.
- Các thao tác rewrite/repack có thể bố trí lại tuple theo storage settings.

### 10.4. Rewrite bảng

Các cách rewrite như VACUUM FULL, CLUSTER hoặc công cụ như pg_repack có thể sắp xếp lại dữ liệu và tạo page layout mới. Mỗi cách có lock, disk space, thời gian và rủi ro vận hành riêng.

### 10.5. VACUUM thường không đồng nghĩa compact toàn bộ live tuples

VACUUM thường thu hồi dead tuple space để tái sử dụng, cập nhật FSM và xử lý visibility/freeze. Nó thường không dồn mọi live tuples để thu nhỏ file về kích thước tối thiểu.

### 10.6. VACUUM FULL

VACUUM FULL rewrite relation và cần lock mạnh (ACCESS EXCLUSIVE), đồng thời cần thêm dung lượng đĩa để tạo bản mới trong quá trình thực hiện. Không chạy trên bảng lớn production mà không lập kế hoạch.

### 10.7. CLUSTER

CLUSTER rewrite bảng theo một index được chọn và có thể giúp locality theo thứ tự đó. Nó cần lock mạnh và có chi phí vận hành. Không nên chạy thường xuyên như một cách thay thế thiết kế index/fillfactor.

### 10.8. pg_repack

`pg_repack` là extension/tool bên ngoài PostgreSQL core, có thể hỗ trợ reorganize với mức khóa khác VACUUM FULL trong các điều kiện cụ thể. Cần kiểm tra tương thích, quyền, dung lượng và vận hành trước khi dùng.

---

## 11. Table fillfactor khác B-tree index fillfactor

Một nhầm lẫn phổ biến là cho rằng `fillfactor=80` trên bảng cũng điều chỉnh cách index được lấp đầy.

Đó là hai storage parameters riêng.

| Thuộc tính | Table fillfactor | B-tree index fillfactor |
| --- | --- | --- |
| Áp dụng cho | Heap table | B-tree index |
| Mặc định phổ biến | 100 | 90 |
| Mục tiêu | Để chỗ cho tuple versions/updates | Điều chỉnh độ lấp đầy các index pages |
| Ảnh hưởng HOT | Có thể tăng cơ hội HOT qua page free space | Không trực tiếp làm HOT đủ điều kiện |
| Trade-off | Table size, scan density, update locality | Index size, page splits, cache |
| Thiết lập | `CREATE TABLE ... WITH (fillfactor=...)` | `CREATE INDEX ... WITH (fillfactor=...)` |

### 11.1. Tạo B-tree index với fillfactor

```sql
CREATE INDEX device_state_status_idx
ON hot_lab.device_state(status)
WITH (fillfactor = 85);
```

### 11.2. Thay đổi fillfactor của index

```sql
ALTER INDEX storage_lab.device_state_status_idx
SET (fillfactor = 80);
```

Giá trị mới ảnh hưởng cách index được duy trì trong các thao tác phù hợp; các pages cũ không tự được sắp xếp lại chỉ vì ALTER INDEX.

### 11.3. REINDEX khi cần xây lại page layout

```sql
REINDEX INDEX storage_lab.device_state_status_idx;
```

REINDEX xây dựng lại index và cần được lập kế hoạch theo locking/concurrency/phiên bản. Không chạy trên production lớn mà chưa đánh giá tác động.

### 11.4. Vì sao B-tree cần free space?

B-tree cần split pages khi chèn index entries vào page không còn chỗ. Fillfactor thấp có thể để room cho một số insert patterns và giảm split trong một số workload.

### 11.5. Index fillfactor không sửa vấn đề HOT

Nếu UPDATE thay đổi indexed column, B-tree fillfactor thấp hơn không biến UPDATE đó thành HOT. Điều kiện HOT liên quan đến việc index có phải cập nhật entry cho cột đã thay đổi hay không, cùng không gian trên heap page.

---

## 12. Free Space Map (FSM)

PostgreSQL duy trì **Free Space Map** để theo dõi xấp xỉ dung lượng trống có sẵn trong các pages của relation.

### 12.1. FSM dùng để làm gì?

Khi cần chèn tuple mới, PostgreSQL có thể tham khảo FSM để tìm page có khả năng chứa tuple thay vì quét tuần tự mọi page.

### 12.2. FSM là thông tin xấp xỉ

FSM không phải một bản đồ byte-by-byte luôn chính xác theo thời gian thực. Các thao tác đồng thời và thay đổi page có thể khiến lượng free space thực tế khác với giá trị được ghi nhận.

### 12.3. FSM và HOT có quan hệ nhưng không giống nhau

FSM hữu ích trong việc tìm page trống cho một số thao tác ghi. HOT yêu cầu phiên bản mới nằm **trên chính page chứa tuple cũ**. Một page khác còn nhiều chỗ không thể giúp một UPDATE trở thành HOT nếu page cũ không vừa.

### 12.4. VACUUM cập nhật free space information

VACUUM có thể cập nhật FSM khi thu hồi dead tuple space để các lần ghi sau tái sử dụng.

### 12.5. Free space không đồng nghĩa bloat

Một bảng có fillfactor thấp có thể cố ý giữ free space để hỗ trợ UPDATE. Không xem mọi byte trống là lãng phí hoặc bloat.

---

## 13. Xem free space bằng pg_freespacemap

Extension `pg_freespacemap` cung cấp hàm đọc thông tin free space map.

### 13.1. Tạo extension nếu có quyền

```sql
CREATE EXTENSION IF NOT EXISTS pg_freespacemap;
```

Extension có thể cần quyền cài đặt phù hợp và phải được quản trị viên cho phép trên môi trường được quản lý.

### 13.2. Xem free space theo page

```sql
SELECT
    blkno,
    avail AS available_bytes
FROM pg_freespace(
    'storage_lab.device_state'::regclass
)
ORDER BY blkno
LIMIT 30;
```

Tên schema của hàm phụ thuộc nơi extension được cài; nếu search_path không chứa schema đó, hãy qualify theo schema thực tế.

### 13.3. Ý nghĩa kết quả

- `blkno`: số block/page trong relation.
- `avail`: lượng free space ước tính mà FSM ghi nhận cho page đó.

### 13.4. Đây không phải số đo chính xác tuyệt đối

Nếu cần phân tích sâu, đối chiếu với `pgstattuple`, `pageinspect` hoặc workload thật. Không dùng một dòng FSM để kết luận chắc chắn UPDATE tiếp theo sẽ HOT.

### 13.5. Tóm tắt phân bố free space

```sql
SELECT
    COUNT(*) AS pages,
    MIN(avail) AS min_free_bytes,
    AVG(avail)::NUMERIC(12,2) AS avg_free_bytes,
    MAX(avail) AS max_free_bytes
FROM pg_freespace(
    'storage_lab.device_state'::regclass
);
```

Một số pages có thể không xuất hiện như bạn kỳ vọng nếu relation nhỏ hoặc thông tin FSM chưa được cập nhật theo trạng thái gần nhất.

---

## 14. Xem live tuples, dead tuples và free space bằng pgstattuple

Extension `pgstattuple` có thể cung cấp thống kê chi tiết hơn về relation.

### 14.1. Cài extension

```sql
CREATE EXTENSION IF NOT EXISTS pgstattuple;
```

Cần quyền phù hợp và xem xét chi phí quét dữ liệu.

### 14.2. Thống kê bảng

```sql
SELECT *
FROM pgstattuple(
    'storage_lab.device_state'::regclass
);
```

Kết quả có thể bao gồm:

- `table_len`: kích thước relation.
- `tuple_count`: số live tuples được đếm.
- `tuple_len`: tổng bytes live tuple data.
- `tuple_percent`: tỷ lệ live tuple data.
- `dead_tuple_count`: số dead tuples.
- `dead_tuple_len`: bytes của dead tuples.
- `dead_tuple_percent`: tỷ lệ dead tuple data.
- `free_space`: free space được quan sát.
- `free_percent`: tỷ lệ free space.

### 14.3. pgstattuple có chi phí

Một số hàm quét relation để thống kê; trên bảng rất lớn, việc này có thể tốn I/O và thời gian. Chọn thời điểm chạy phù hợp.

### 14.4. pgstattuple_approx

Một số phiên bản có `pgstattuple_approx`, dùng thông tin free space map/visibility map để ước lượng nhanh hơn trong những điều kiện nhất định. Đây là ước lượng, không thay thế exact scan khi cần.

### 14.5. Đọc kết quả theo mục tiêu

- Free space cao có thể là thiết kế fillfactor hoặc do delete/update.
- Dead tuple percent cao có thể cho thấy vacuum không theo kịp.
- Tuple percent thấp có thể là page density thấp hoặc bloat.
- Không kết luận chỉ từ một phần trăm; cần xem workload, table/index sizes và xu hướng.

---

## 15. Theo dõi HOT update bằng pg_stat_user_tables

PostgreSQL cung cấp thống kê cập nhật trên table.

```sql
SELECT
    schemaname,
    relname,
    n_tup_upd,
    n_tup_hot_upd,
    n_dead_tup
FROM pg_catalog.pg_stat_user_tables
WHERE schemaname = 'storage_lab'
ORDER BY relname;
```

### 15.1. n_tup_upd

Số tuple updates được thống kê cho bảng.

### 15.2. n_tup_hot_upd

Số HOT updates được thống kê.

### 15.3. HOT update ratio

Có thể tính:

```sql
SELECT
    relname,
    n_tup_upd,
    n_tup_hot_upd,
    ROUND(
        100.0 * n_tup_hot_upd / NULLIF(n_tup_upd, 0),
        2
    ) AS hot_update_percent
FROM pg_catalog.pg_stat_user_tables
WHERE schemaname = 'storage_lab'
ORDER BY relname;
```

### 15.4. Không có ngưỡng HOT ratio chung

- Một bảng append-only gần như không có UPDATE thì HOT ratio không có nhiều ý nghĩa.
- Một bảng cập nhật cột indexed thường xuyên có thể có HOT ratio thấp theo thiết kế.
- Một bảng update-heavy thay đổi cột không indexed có thể kỳ vọng HOT ratio cao hơn nếu đủ chỗ.
- Một ratio 90% không tự chứng minh query latency tốt hoặc index không bloat.

### 15.5. Thống kê có tính tích lũy

Các counters có thể được reset theo cơ chế thống kê và thời điểm triển khai. Hãy so sánh trong một khoảng thời gian xác định, không lấy một giá trị tuyệt đối mà không biết lịch sử.

### 15.6. Cập nhật thống kê có độ trễ

Thống kê có thể chưa phản ánh ngay một transaction vừa hoàn thành. Đọc lại sau khi transaction commit và trong một snapshot phù hợp. Đừng coi kết quả tức thời là phép đo đồng bộ chính xác cho từng statement.

---

## 16. Tại sao HOT ratio thấp?

Một số nguyên nhân thường gặp:

### 16.1. UPDATE thay đổi cột được index tham chiếu

Ví dụ index trên `last_seen`, trong khi mỗi heartbeat cập nhật `last_seen`.

Giải pháp có thể là bỏ index nếu truy vấn không thực sự cần, hoặc thay đổi mô hình dữ liệu/index. Không bỏ index quan trọng chỉ để tăng HOT ratio.

### 16.2. Page không đủ free space

Fillfactor 100 và các pages đã lấp đầy có thể không còn chỗ cho tuple version mới.

Giải pháp: thử fillfactor thấp hơn cho dữ liệu mới hoặc lên kế hoạch rewrite/repack để áp dụng cho dữ liệu cũ.

### 16.3. Tuple version mới lớn hơn

Một cột TEXT/JSONB tăng kích thước có thể làm version mới không vừa page, kể cả page ban đầu có free space.

### 16.4. Nhiều index phụ thuộc vào cột thay đổi

Expression index, partial index hoặc INCLUDE columns có thể làm HOT không khả thi.

### 16.5. Fillfactor chưa được áp dụng lên partition thực tế

Nếu bảng là partitioned table, dữ liệu nằm ở leaf partitions. Parent có fillfactor nhưng các partition cũ có thể vẫn dùng setting khác.

### 16.6. UPDATE nhiều cột không ổn định

Nếu mỗi lần UPDATE thay đổi cả status, indexed timestamp, key và các trường khác, thiết kế khó đạt HOT.

### 16.7. Không có free space dù fillfactor thấp đã cấu hình

Thay đổi storage parameter không tự tạo free space trên các pages đã tồn tại. Có thể cần vacuum/rewrite hoặc đợi dữ liệu được ghi theo cấu hình mới.

### 16.8. HOT không phải mục tiêu duy nhất

Nếu UPDATE phải đổi index key vì truy vấn cần tìm theo giá trị mới, non-HOT có thể là chi phí hợp lý. Đừng tối ưu HOT bằng cách làm mất khả năng truy vấn nghiệp vụ.

---

## 17. Thiết kế bảng để hỗ trợ HOT

Một số nguyên tắc thiết kế:

### 17.1. Phân biệt cột ổn định và cột thay đổi thường xuyên

Ví dụ:

```sql
CREATE TABLE storage_lab.device_state (
    device_id BIGINT PRIMARY KEY,
    hardware_serial TEXT NOT NULL,
    status TEXT NOT NULL,
    last_seen TIMESTAMPTZ,
    heartbeat_at TIMESTAMPTZ,
    metadata JSONB
);
```

- `device_id`, `hardware_serial`: tương đối ổn định.
- `last_seen`, `heartbeat_at`: cập nhật thường xuyên.
- `metadata`: có thể thay đổi kích thước lớn.

Nếu workload chủ yếu cập nhật timestamp, không index timestamp nếu không có nhu cầu query đủ mạnh.

### 17.2. Không index mọi cột “có thể cần tìm”

Mỗi index tạo chi phí ghi và storage. Chỉ index khi có query pattern cần thiết và đo được lợi ích.

### 17.3. Đánh giá INCLUDE columns

Covering index giúp index-only scans trong một số tình huống, nhưng nếu INCLUDE một cột thay đổi liên tục, nó có thể làm UPDATE mất HOT eligibility.

### 17.4. Đánh giá partial index

Partial index giảm kích thước bằng cách chỉ index một subset rows, nhưng predicate columns cũng ảnh hưởng HOT. Một status column thay đổi thường xuyên có thể khiến index predicate trở thành nguồn non-HOT updates.

### 17.5. Tách bảng khi có update frequency rất khác nhau

Một bảng có nhiều cột profile ổn định và một nhóm cột heartbeat thay đổi liên tục có thể được tách thành bảng trạng thái riêng theo khóa chính nếu workload và consistency model phù hợp.

Ví dụ:

```sql
CREATE TABLE storage_lab.devices (
    device_id BIGINT PRIMARY KEY,
    serial_number TEXT NOT NULL,
    model TEXT NOT NULL
);

CREATE TABLE storage_lab.device_heartbeats (
    device_id BIGINT PRIMARY KEY
        REFERENCES storage_lab.devices(device_id),
    last_seen TIMESTAMPTZ NOT NULL,
    heartbeat_state TEXT NOT NULL
) WITH (fillfactor = 80);
```

Việc tách có trade-offs về JOIN, transaction và schema complexity; chỉ làm khi workload cho thấy có lợi.

### 17.6. Tránh UPDATE không thay đổi giá trị

Một UPDATE không thực sự thay đổi giá trị vẫn có thể tạo tuple version mới. Nếu logic ứng dụng có thể tránh update vô ích:

```sql
UPDATE storage_lab.device_state
SET status = $1
WHERE device_id = $2
  AND status IS DISTINCT FROM $1;
```

có thể giảm số tuple versions và WAL không cần thiết.

### 17.7. Dùng conditional update có kiểm soát

Đừng UPDATE mọi hàng chỉ để refresh timestamp nếu nghiệp vụ không yêu cầu. Một job chạy định kỳ có thể tạo nhiều versions và tăng áp lực vacuum.

---

## 18. HOT, VACUUM và autovacuum

HOT giảm index maintenance nhưng không loại bỏ dead tuple versions. VACUUM vẫn là thành phần cần thiết.

### 18.1. VACUUM thường làm gì?

- Thu hồi dead tuple space để tái sử dụng.
- Cập nhật free space map.
- Hỗ trợ page pruning/cleanup.
- Cập nhật visibility map theo điều kiện.
- Thực hiện freezing theo nhu cầu và các quy tắc tuổi transaction.

### 18.2. VACUUM thường không thu nhỏ file relation

Không gian được thu hồi thường được giữ lại để PostgreSQL tái sử dụng cho dữ liệu mới. File có thể vẫn giữ kích thước lớn trên filesystem.

### 18.3. Autovacuum

Autovacuum chạy VACUUM/ANALYZE tự động theo ngưỡng và chính sách. Với bảng update-heavy, cần quan sát:

- `n_dead_tup`.
- `last_autovacuum`.
- `autovacuum_count`.
- Transaction age và vacuum progress.
- Replication slots hoặc long-running transactions có thể ngăn cleanup cần thiết.

### 18.4. Cấu hình theo bảng khi có lý do

Ví dụ minh họa:

```sql
ALTER TABLE storage_lab.device_state
SET (
    autovacuum_vacuum_threshold = 1000,
    autovacuum_vacuum_scale_factor = 0.05
);
```

Các giá trị phải dựa vào row count, update rate, thời gian vacuum và tài nguyên. Không sao chép một con số vào mọi bảng.

### 18.5. HOT chain cần cleanup

Page pruning/VACUUM giúp thu hồi các tuple versions không còn cần thiết. Nếu có transaction/snapshot kéo dài hoặc replication slot giữ xmin, cleanup có thể bị trì hoãn.

### 18.6. HOT không phải giải pháp chống bloat hoàn chỉnh

Nếu bảng có DELETE nhiều, non-HOT updates nhiều, long transactions hoặc autovacuum không theo kịp, vẫn có thể có bloat. Cần đo heap và indexes riêng.

---

## 19. Table bloat và free space có chủ đích

**Bloat** thường nói tới không gian relation tăng do các tuple chết, page splits hoặc phân bố không hiệu quả so với lượng dữ liệu live. Tuy nhiên, một page có free space không mặc nhiên là bloat.

### 19.1. Free space có chủ đích

Với fillfactor 80, một phần không gian được để lại nhằm hỗ trợ UPDATE. Đây là thiết kế có chủ đích.

### 19.2. Dead tuple space

Các tuple versions cũ chưa được thu hồi có thể chiếm chỗ. VACUUM có thể đánh dấu không gian để tái sử dụng.

### 19.3. Index bloat

Non-HOT updates có thể thêm index entries mới; các entries cũ trở nên dead và cần cleanup. Index có thể lớn hơn theo thời gian.

### 19.4. Table size và live data size

Không chỉ xem `pg_relation_size`. Cần xem tuple count, tuple length, dead tuple length, free space và indexes.

### 19.5. Không cố làm free_percent bằng 0

Một table update-heavy có fillfactor thấp có thể cố ý có free space. Ép mọi page đầy có thể làm giảm HOT và tăng index churn.

---

## 20. Lab: tạo bảng update-heavy với fillfactor

Các ví dụ dưới đây dùng schema `hot_lab`.

> **Cảnh báo:** `DROP SCHEMA ... CASCADE` xóa các đối tượng trong schema cùng tên. Chỉ chạy trên database lab có thể reset. Không chạy trên production hoặc schema đang chứa dữ liệu cần giữ.

### 20.1. Tạo schema

```sql
DROP SCHEMA IF EXISTS hot_lab CASCADE;
CREATE SCHEMA hot_lab;
```

### 20.2. Tạo bảng có fillfactor 70

```sql
CREATE TABLE hot_lab.device_state (
    device_id BIGINT PRIMARY KEY,
    status TEXT NOT NULL,
    last_seen TIMESTAMPTZ NOT NULL,
    description TEXT
) WITH (fillfactor = 70);
```

### 20.3. Chèn nhiều rows

```sql
INSERT INTO hot_lab.device_state (
    device_id,
    status,
    last_seen,
    description
)
SELECT
    g,
    'ONLINE',
    clock_timestamp(),
    'device-' || g::TEXT
FROM generate_series(1, 20000) AS g;
```

Bảng có primary key index trên `device_id`. Chưa tạo index trên `last_seen`.

### 20.4. Kiểm tra reloptions

```sql
SELECT
    c.relname,
    c.reloptions
FROM pg_catalog.pg_class AS c
WHERE c.oid = 'hot_lab.device_state'::regclass;
```

Kỳ vọng thấy cấu hình `fillfactor=70`.

### 20.5. Kiểm tra kích thước

```sql
SELECT
    pg_catalog.pg_relation_size(
        'hot_lab.device_state'::regclass
    ) AS heap_bytes,
    pg_catalog.pg_indexes_size(
        'hot_lab.device_state'::regclass
    ) AS index_bytes,
    pg_catalog.pg_total_relation_size(
        'hot_lab.device_state'::regclass
    ) AS total_bytes;
```

### 20.6. Xem indexes

```sql
SELECT
    indexrelid::regclass AS index_name,
    pg_catalog.pg_get_indexdef(indexrelid) AS definition
FROM pg_catalog.pg_index
WHERE indrelid = 'hot_lab.device_state'::regclass;
```

Trong trạng thái ban đầu, index chính là primary key trên `device_id`.

---

## 21. Lab: tạo HOT update trên cột không index

Thử cập nhật `last_seen`:

```sql
UPDATE hot_lab.device_state
SET last_seen = last_seen + INTERVAL '1 second'
WHERE device_id % 10 = 0;
```

### 21.1. Vì sao có cơ hội HOT?

- Cột `last_seen` chưa được index.
- Page có thể còn free space nhờ fillfactor 70.
- Tuple version mới thường có kích thước tương tự version cũ.
- Nếu page có đủ chỗ, update có thể HOT.

### 21.2. Kiểm tra thống kê

```sql
SELECT
    relname,
    n_tup_upd,
    n_tup_hot_upd,
    ROUND(
        100.0 * n_tup_hot_upd / NULLIF(n_tup_upd, 0),
        2
    ) AS hot_update_percent,
    n_dead_tup
FROM pg_catalog.pg_stat_user_tables
WHERE schemaname = 'hot_lab'
  AND relname = 'device_state';
```

### 21.3. Kết quả kỳ vọng

Trong điều kiện lab thông thường, `n_tup_hot_upd` có thể tăng vì UPDATE chỉ đổi cột không được index tham chiếu và table đã để chỗ trên page.

Không yêu cầu mọi row update đều HOT. Page layout, kích thước tuple, trạng thái free space và điều kiện thực thi có thể làm kết quả khác nhau.

### 21.4. Thống kê có thể cập nhật trễ

Chạy sau khi statement/transaction đã hoàn thành. Nếu vừa truy vấn trong một snapshot thống kê cũ, có thể cần truy vấn lại trong một transaction mới.

### 21.5. Không reset toàn bộ thống kê cluster chỉ để làm lab

`pg_stat_reset()` có thể ảnh hưởng metrics toàn hệ thống. Nếu cần số liệu delta, ghi lại counters trước/sau và so sánh; chỉ reset single-table counters khi hiểu quyền và tác động.

---

## 22. Lab: tạo index trên cột thường xuyên thay đổi

Bây giờ tạo index:

```sql
CREATE INDEX device_state_last_seen_idx
ON hot_lab.device_state(last_seen);
```

Sau đó cập nhật `last_seen` lần nữa:

```sql
UPDATE hot_lab.device_state
SET last_seen = last_seen + INTERVAL '2 seconds'
WHERE device_id % 10 = 0;
```

### 22.1. Điều gì đã thay đổi?

`last_seen` hiện là cột được B-tree index tham chiếu. Khi UPDATE thay đổi cột này, HOT thông thường không còn đủ điều kiện.

### 22.2. Đọc lại thống kê

```sql
SELECT
    relname,
    n_tup_upd,
    n_tup_hot_upd,
    ROUND(
        100.0 * n_tup_hot_upd / NULLIF(n_tup_upd, 0),
        2
    ) AS hot_update_percent
FROM pg_catalog.pg_stat_user_tables
WHERE schemaname = 'hot_lab'
  AND relname = 'device_state';
```

Counters là tích lũy; để so sánh chính xác hai giai đoạn, lấy số trước/sau mỗi giai đoạn và tính delta.

### 22.3. Kết quả kỳ vọng

Các UPDATE sau khi tạo index trên `last_seen` thường không tăng HOT counter theo cùng cách giai đoạn đầu; PostgreSQL phải duy trì index cho giá trị mới.

### 22.4. Bài học thiết kế

Một index giúp query theo `last_seen` có thể làm UPDATE heartbeat tốn kém hơn. Cần đo trade-off giữa read performance và write amplification.

### 22.5. Không xóa index chỉ để làm HOT ratio đẹp

Nếu query production phụ thuộc index đó, bỏ index có thể làm latency tăng nghiêm trọng. HOT ratio là một chỉ số chẩn đoán, không phải mục tiêu duy nhất.

---

## 23. Lab: xem free space map

Cài extension nếu quyền cho phép:

```sql
CREATE EXTENSION IF NOT EXISTS pg_freespacemap;
```

### 23.1. Xem một số pages

```sql
SELECT
    blkno,
    avail AS free_bytes
FROM pg_freespace(
    'hot_lab.device_state'::regclass
)
ORDER BY blkno
LIMIT 30;
```

### 23.2. Tổng hợp phân bố

```sql
SELECT
    COUNT(*) AS page_count,
    MIN(avail) AS minimum_free_bytes,
    ROUND(AVG(avail)::NUMERIC, 2) AS average_free_bytes,
    MAX(avail) AS maximum_free_bytes
FROM pg_freespace(
    'hot_lab.device_state'::regclass
);
```

### 23.3. Đối chiếu fillfactor

Page có free space không nhất thiết còn đúng tỷ lệ 30% theo fillfactor ban đầu. UPDATE, VACUUM, tuple size và page occupancy đã thay đổi.

### 23.4. FSM không dự báo chắc chắn HOT

Nó cho biết free space ước tính theo page. HOT còn cần kiểm tra cột index tham chiếu và đủ chỗ cho tuple version mới trên đúng page.

---

## 24. Lab: quan sát dead tuples và VACUUM

Cài `pgstattuple` nếu được phép:

```sql
CREATE EXTENSION IF NOT EXISTS pgstattuple;
```

### 24.1. Đọc thống kê trước VACUUM

```sql
SELECT *
FROM pgstattuple(
    'hot_lab.device_state'::regclass
);
```

### 24.2. Chạy VACUUM thường

```sql
VACUUM (VERBOSE, ANALYZE) hot_lab.device_state;
```

Lệnh VACUUM thường phải chạy ngoài transaction block theo cách PostgreSQL quy định.

### 24.3. Đọc lại

```sql
SELECT *
FROM pgstattuple(
    'hot_lab.device_state'::regclass
);
```

### 24.4. Điều cần quan sát

- Dead tuple count/length có thể giảm.
- Free space có thể tăng vì dead tuples được thu hồi để tái sử dụng.
- File relation thường không tự thu nhỏ chỉ vì VACUUM thường.
- Thống kê có thể khác tùy thời điểm và visibility.

### 24.5. HOT chain cleanup

VACUUM và page pruning có thể thu hồi các HOT tuple versions không còn cần thiết, giảm công việc lần theo chain và giúp page tái sử dụng không gian.

---

## 25. Lab: thay đổi fillfactor và hiểu tác động lên dữ liệu cũ

Đổi setting:

```sql
ALTER TABLE hot_lab.device_state
SET (fillfactor = 85);
```

### 25.1. Xác nhận

```sql
SELECT reloptions
FROM pg_catalog.pg_class
WHERE oid = 'hot_lab.device_state'::regclass;
```

### 25.2. Điều gì không xảy ra?

PostgreSQL không lập tức di chuyển mọi tuple hiện có để mỗi page còn 15% free space. Những pages cũ vẫn giữ layout hiện tại.

### 25.3. Rows được INSERT sau đó

Các pages được dùng cho tuple mới sẽ áp dụng storage setting theo cách PostgreSQL quản lý fillfactor.

### 25.4. Muốn áp dụng rộng cho dữ liệu cũ

Cần xem xét table rewrite/repack có kế hoạch. Ví dụ:

```sql
-- Thao tác nặng, minh họa cho môi trường lab:
-- VACUUM (FULL) hot_lab.device_state;
```

VACUUM FULL có thể cần ACCESS EXCLUSIVE lock và thêm disk space. Không chạy chỉ để thử trên bảng production lớn.

### 25.5. Fillfactor mới không tự làm index đổi fillfactor

Table reloptions và index reloptions là độc lập. Kiểm tra `pg_class.reloptions` cho từng relation nếu cần.

---

## 26. B-tree index fillfactor và page splits

B-tree index cũng có storage parameter fillfactor, mặc định phổ biến là 90.

### 26.1. Ví dụ

```sql
CREATE INDEX device_state_status_idx
ON hot_lab.device_state(status)
WITH (fillfactor = 85);
```

### 26.2. Tại sao để trống index page?

Khi chèn entries mới, B-tree có thể phải split page nếu page không còn chỗ. Fillfactor thấp có thể để room cho một số insert patterns và giảm split trong một số workload.

### 26.3. Index fillfactor và table fillfactor có mục tiêu khác

- Heap fillfactor tạo cơ hội để tuple version mới nằm cùng heap page.
- B-tree fillfactor điều chỉnh page occupancy của index.

### 26.4. Không làm HOT bằng cách giảm index fillfactor

Nếu UPDATE đổi indexed column, B-tree index vẫn cần được duy trì. Index fillfactor thấp hơn không biến nó thành HOT.

### 26.5. Index read density

Index fillfactor thấp có thể làm index lớn hơn và giảm số entries trên mỗi page, ảnh hưởng cache và số page đọc. Cần đo cả read/write workload.

---

## 27. Partitioned tables và fillfactor

Một partitioned table trong PostgreSQL là quan hệ cha điều phối; dữ liệu thực tế nằm trong các leaf partitions.

### 27.1. Storage parameter trên parent không thay thế kiểm tra leaf

```sql
CREATE TABLE hot_lab.events (
    event_id BIGINT,
    tenant_id BIGINT,
    event_type TEXT,
    updated_at TIMESTAMPTZ
) PARTITION BY RANGE (event_id);
```

Tạo partition:

```sql
CREATE TABLE hot_lab.events_p1
PARTITION OF hot_lab.events
FOR VALUES FROM (1) TO (100000)
WITH (fillfactor = 80);
```

### 27.2. Mỗi partition có physical pages riêng

HOT update diễn ra trong heap page của partition chứa tuple. Fillfactor và indexes của partition đó ảnh hưởng cơ hội HOT.

### 27.3. Kiểm tra từng partition

Không chỉ đọc reloptions của parent. Liệt kê leaf partitions và kiểm tra reloptions/owner/indexes trên từng bảng vật lý.

### 27.4. Partition pruning không thay HOT

Partition pruning giúp query chọn partition; HOT là tối ưu cập nhật tuple bên trong một partition. Hai cơ chế giải quyết vấn đề khác nhau.

### 27.5. Partition rotation có thể thay đổi workload

Partition mới có thể bắt đầu với fillfactor mới, trong khi partitions cũ giữ layout cũ. Một bảng partitioned có thể có HOT ratio khác nhau theo thời gian và partition.

---

## 28. Chọn fillfactor theo loại workload

| Workload | Hướng xem xét |
| --- | --- |
| Append-only, ít UPDATE | Fillfactor gần 100 thường hợp lý |
| Update nhiều cột không index | Thử 80–90 hoặc mức thấp hơn theo benchmark |
| Heartbeat/timestamp update liên tục | Đánh giá bỏ index timestamp nếu không cần, thử fillfactor thấp |
| UPDATE thường đổi index key | Fillfactor thấp không giải quyết HOT eligibility |
| Hàng có kích thước tăng mạnh | Cần đo tuple growth; reserve cố định có thể không đủ |
| Bảng read-heavy, scan lớn | Density cao có thể có lợi |
| Bảng có nhiều partitions | Tune leaf partitions theo tuổi/workload |
| Bảng delete/update gây dead tuples nhiều | Kiểm tra autovacuum, transaction age, HOT và bloat cùng lúc |

### 28.1. Đừng tối ưu một chỉ số duy nhất

Một HOT ratio cao nhưng heap table lớn gấp đôi có thể làm full scans chậm hơn. Một HOT ratio thấp nhưng query latency và storage tốt có thể là thiết kế đúng.

### 28.2. Dùng workload đại diện

Cần mô phỏng cả:

- Tỷ lệ INSERT/UPDATE/DELETE.
- Tỷ lệ cột indexed được thay đổi.
- Row width và update growth.
- Concurrency.
- Index count.
- Transaction duration.
- Autovacuum và replication.

### 28.3. Benchmark nhiều mức

Ví dụ thử 100, 90, 80 và 70 trong các bản sao staging. So sánh cùng dataset và workload, không so các bảng có kích thước khác nhau rồi kết luận do fillfactor.

### 28.4. Kiểm tra cả reads

Nếu một bảng được đọc bằng sequential scans nhiều hơn UPDATE, tăng page count có thể gây chi phí lớn. Dùng `EXPLAIN (ANALYZE, BUFFERS)` và workload metrics.

---

## 29. Các yếu tố khác ảnh hưởng HOT

### 29.1. Kích thước tuple

Tuple version mới phải vừa cùng page. Cột VARCHAR/TEXT/JSONB có thể làm tuple thay đổi kích thước; TOAST có thể ảnh hưởng cách lưu giá trị lớn.

### 29.2. Số lượng index

Nhiều index làm tăng khả năng một cột thường thay đổi được index tham chiếu. Đồng thời non-HOT UPDATE có thể phải duy trì nhiều indexes hơn.

### 29.3. Partial index predicates

Cột dùng trong predicate có thể làm UPDATE thay đổi membership của hàng trong index.

### 29.4. Expression indexes

Một cột nguồn của expression index vẫn được xem là cột mà index phụ thuộc.

### 29.5. INCLUDE columns

Một covering index có thể làm UPDATE cột included mất HOT eligibility, dù cột đó không phải key đầu tiên.

### 29.6. Page occupancy thực tế

Fillfactor là mục tiêu khi ghi tuple mới, nhưng page có thể bị lấp đầy hoặc có phân bố không đều sau nhiều thao tác.

### 29.7. Concurrent workload

Các phiên khác có thể INSERT/UPDATE cùng page; HOT vẫn cần không gian đủ khi thực hiện. Đừng suy từ một phép thử tuần tự rằng concurrency production sẽ có cùng tỷ lệ.

### 29.8. Transaction snapshots dài

Một transaction chạy lâu có thể giữ các versions cũ cần thiết, làm chậm cleanup và làm free space không được thu hồi đúng lúc.

---

## 30. HOT, WAL và replication

HOT giảm một phần index maintenance, nhưng vẫn là thao tác ghi.

### 30.1. HOT vẫn sinh tuple version

UPDATE tạo version mới và cần ghi dữ liệu/metadata theo durability rules. Không thể coi HOT là “không WAL”.

### 30.2. Giảm index WAL có thể hữu ích

Khi một bảng có nhiều indexes và phần lớn UPDATE là HOT, tránh index entries mới có thể giảm write amplification.

### 30.3. Không loại bỏ heap WAL

Heap tuple changes vẫn cần được ghi theo WAL policy của PostgreSQL. HOT không vô hiệu hóa WAL cho table update.

### 30.4. Replication có thể vẫn nhận lượng WAL đáng kể

Một bảng heartbeat cập nhật hàng triệu lần/ngày vẫn tạo write volume. HOT có thể giảm một phần WAL/index maintenance nhưng không làm replication workload biến mất.

### 30.5. Theo dõi replica lag

Nếu tuning fillfactor làm update throughput tăng, lượng write workload thực tế có thể tăng theo. Cần theo dõi replication lag và disk/WAL capacity.

---

## 31. Không nên nhầm HOT với no-op UPDATE

Một câu:

```sql
UPDATE hot_lab.device_state
SET status = status
WHERE device_id = 100;
```

không nên được xem là “không có thao tác” chỉ vì giá trị cột giống nhau. PostgreSQL có thể tạo tuple version mới theo semantics UPDATE, dù tối ưu HOT có thể áp dụng nếu đủ điều kiện.

Nếu logic ứng dụng không cần ghi lại hàng khi giá trị không thay đổi, hãy thêm điều kiện:

```sql
UPDATE hot_lab.device_state
SET status = $1
WHERE device_id = $2
  AND status IS DISTINCT FROM $1;
```

### 31.1. Lợi ích

- Ít tuple versions hơn.
- Ít WAL hơn.
- Ít dead tuples hơn.
- Giảm vacuum work.
- Giảm lock/write churn trong một số workload.

### 31.2. NULL-safe comparison

`IS DISTINCT FROM` xử lý NULL rõ ràng hơn so sánh `<>` thông thường khi muốn kiểm tra hai giá trị có khác nhau hay không.

### 31.3. Cần đúng nghiệp vụ

Một số ứng dụng cố ý UPDATE timestamp hoặc audit fields kể cả khi dữ liệu khác không đổi. Không bỏ những cập nhật có ý nghĩa chỉ để tăng HOT ratio.

---

## 32. Chẩn đoán bằng pageinspect

`pageinspect` là extension hỗ trợ xem cấu trúc pages ở mức thấp.

### 32.1. Cài extension

```sql
CREATE EXTENSION IF NOT EXISTS pageinspect;
```

Cần quyền phù hợp; các hàm đọc raw pages có thể yêu cầu đặc quyền bổ sung và phải được dùng có kiểm soát.

### 32.2. Xem page header

```sql
SELECT *
FROM page_header(
    get_raw_page('hot_lab.device_state', 0)
);
```

### 32.3. Xem heap page items

```sql
SELECT *
FROM heap_page_items(
    get_raw_page('hot_lab.device_state', 0)
);
```

### 32.4. Vì sao cần thận trọng?

- Đây là công cụ chẩn đoán cấu trúc nội bộ.
- Cách diễn giải flags/tuple fields đòi hỏi hiểu version và implementation.
- Một page cụ thể không đại diện cả relation.
- Không dùng output pageinspect như API ứng dụng ổn định.

### 32.5. Không sửa raw pages

`pageinspect` chủ yếu phục vụ inspection; không can thiệp bytes page để sửa tuple. Dữ liệu cần được sửa bằng SQL hoặc quy trình recovery chính thức.

---

## 33. Benchmark fillfactor có kiểm soát

Một benchmark có ích nên gồm nhiều biến thể:

### 33.1. Chuẩn bị các bảng giống nhau

- Bảng A: fillfactor 100.
- Bảng B: fillfactor 90.
- Bảng C: fillfactor 80.
- Bảng D: fillfactor 70.

Dùng cùng schema, data distribution, indexes và constraints.

### 33.2. Chọn update patterns

- Chỉ cập nhật cột không index.
- Cập nhật cột có B-tree index.
- Cập nhật cột trong partial-index predicate.
- Cập nhật row width tăng mạnh.
- Cập nhật nhiều rows đồng thời.

### 33.3. Metrics

- `n_tup_upd`.
- `n_tup_hot_upd`.
- HOT ratio.
- `n_dead_tup`.
- Heap bytes.
- Index bytes.
- Total relation bytes.
- WAL volume.
- Update throughput.
- p50/p95 latency.
- Read latency/scan buffers.
- Autovacuum frequency/duration.
- Replication lag.

### 33.4. Công cụ đo

- `pg_stat_user_tables`.
- `pg_relation_size`, `pg_indexes_size`, `pg_total_relation_size`.
- `pgstattuple`.
- `pg_freespacemap`.
- `EXPLAIN (ANALYZE, BUFFERS)`.
- `pg_stat_statements` nếu đã cài và được phép.
- Monitoring WAL/replication của hệ thống.

### 33.5. Không benchmark chỉ một lần

Cache, checkpoint, vacuum, background load và data distribution có thể ảnh hưởng kết quả. Chạy nhiều lần và so sánh điều kiện tương đương.

### 33.6. Không chạy benchmark phá hoại trên production

Tạo bản sao staging/benchmark hoặc dataset riêng. Tránh tạo hàng triệu UPDATE vào bảng đang phục vụ người dùng chỉ để thử fillfactor.

---

## 34. Đọc index definitions để tìm cột cản HOT

Có thể liệt kê indexes của bảng:

```sql
SELECT
    i.indexrelid::regclass AS index_name,
    i.indisprimary,
    i.indisunique,
    i.indisvalid,
    pg_catalog.pg_get_indexdef(i.indexrelid) AS definition
FROM pg_catalog.pg_index AS i
WHERE i.indrelid = 'hot_lab.device_state'::regclass
ORDER BY i.indexrelid::regclass::TEXT;
```

### 34.1. Tìm cột thường thay đổi

Đối chiếu các UPDATE statements của ứng dụng với:

- Key columns.
- INCLUDE columns.
- Expression dependencies.
- Partial-index predicates.
- Index type.

### 34.2. Không chỉ đọc tên index

Một index tên `idx_device_lookup` không cho biết cột nào thực sự được index. Đọc `pg_get_indexdef`.

### 34.3. Index invalid/unready

Các index trong trạng thái đặc biệt hoặc migration đang xây dựng dở có semantics riêng. Kiểm tra `indisvalid`/`indisready` khi điều tra; không giả định tất cả index catalog entries đều hoạt động như index hợp lệ bình thường.

### 34.4. Đánh giá query benefit trước khi bỏ index

Index có thể hỗ trợ latency quan trọng. Một quyết định bỏ index để cải thiện HOT phải dựa trên query plan, tần suất đọc, write amplification và SLA.

---

## 35. Những anti-pattern thường gặp

| Anti-pattern | Hệ quả | Hướng xử lý |
| --- | --- | --- |
| Đặt fillfactor 50 cho mọi bảng | Tăng pages/storage/scan I/O | Tuning theo workload |
| Giảm fillfactor rồi kỳ vọng dữ liệu cũ tự dàn lại | Page cũ vẫn có layout cũ | Lên kế hoạch rewrite/repack |
| Index mọi cột timestamp thường cập nhật | Nhiều UPDATE mất HOT | Chỉ index khi query cần |
| INCLUDE cột heartbeat thay đổi liên tục | UPDATE có thể cần index maintenance | Đánh giá covering index |
| Dùng HOT ratio làm KPI duy nhất | Tối ưu sai hướng | Đo latency, size, WAL, read cost |
| Tin HOT không cần VACUUM | Dead tuple/chain vẫn tồn tại | Giám sát autovacuum |
| Nhầm FSM với page free space chính xác | Dự đoán HOT sai | Đối chiếu page/stats |
| Nhầm free space có chủ đích với bloat | Chạy rewrite không cần thiết | Đọc pgstattuple và workload |
| Dùng VACUUM FULL thường xuyên | Lock mạnh, disk overhead | Autovacuum và công cụ phù hợp |
| Thay fillfactor index để sửa HOT | Không tác động điều kiện heap/index-column | Sửa index design hoặc heap space |
| UPDATE mọi row mỗi phút dù không đổi | Tạo tuple versions/WAL không cần thiết | `IS DISTINCT FROM` |
| Chỉ nhìn primary key khi đánh giá HOT | Bỏ sót expression/partial/INCLUDE index | Audit toàn bộ index definitions |
| Bỏ index mà không đo query plan | Read latency tăng | Benchmark cả reads và writes |
| Giả định fillfactor parent áp dụng mọi partition | Leaf pages vẫn khác nhau | Kiểm tra từng leaf |
| Dùng ctid làm định danh hàng | UPDATE có thể đổi vị trí | Dùng khóa ổn định |
| Cho rằng HOT không tạo WAL | Đánh giá sai replication/write load | Đo WAL thực tế |
| Tăng autovacuum scale factor tùy tiện | Dead tuples tích tụ lâu | Tune theo bảng và tốc độ thay đổi |
| Chạy pageinspect trên production giờ cao điểm | I/O/privilege/inspection overhead | Dùng thời điểm kiểm soát |
| Đo stats trước COMMIT | Counters chưa phản ánh | Đọc sau commit |
| Reset toàn cluster stats để làm lab | Mất baseline monitoring | So sánh delta hoặc dùng lab riêng |

---

## 36. Bài tập thực hành

### Bài 1 — Heap page

Vẽ một heap page với page header, line pointers, tuple data và free space. Giải thích vì sao line pointer không phải tuple.

### Bài 2 — MVCC UPDATE

Một hàng có balance=100. Sau UPDATE thành 90, giải thích tại sao PostgreSQL tạo version mới và transaction cũ có thể còn nhìn thấy version cũ.

### Bài 3 — Dead tuples

Vì sao version cũ không thể được xóa ngay khi UPDATE hoàn tất? Điều gì cho phép VACUUM thu hồi chúng?

### Bài 4 — Định nghĩa HOT

Nêu hai điều kiện cơ bản của HOT update và giải thích mỗi điều kiện.

### Bài 5 — Non-indexed update

Tạo bảng chỉ có primary key index trên id. UPDATE một cột timestamp không index. Điều kiện nào giúp update trở thành HOT?

### Bài 6 — Indexed update

Tạo index trên `last_seen`, rồi UPDATE `last_seen`. Vì sao HOT thông thường không còn đủ điều kiện?

### Bài 7 — INCLUDE index

Tạo B-tree index có INCLUDE(status). UPDATE status có thể ảnh hưởng HOT thế nào?

### Bài 8 — Expression index

Tạo index `lower(email)`. Vì sao UPDATE email cần được xem xét dù email không xuất hiện như một key đơn giản?

### Bài 9 — Partial index

Tạo index `WHERE status='ACTIVE'`. UPDATE status từ ACTIVE sang INACTIVE có ảnh hưởng index membership và HOT thế nào?

### Bài 10 — BRIN

Giải thích vì sao summarizing index như BRIN có thể có ngoại lệ so với quy tắc HOT thông thường. Kiểm tra tài liệu phiên bản đang dùng.

### Bài 11 — HOT chain

Vẽ một index entry trỏ tới tuple root và ba tuple versions trong HOT chain. Vì sao index không cần entry riêng cho mọi version?

### Bài 12 — Page pruning

Page pruning có thể thu hồi những tuple versions nào? Vì sao visibility của các transaction khác quyết định thời điểm cleanup?

### Bài 13 — ctid

Một ứng dụng lưu ctid vào bảng audit để truy cập lại hàng. Vì sao cách này không an toàn sau UPDATE?

### Bài 14 — Fillfactor mặc định

Nêu mặc định và khoảng giá trị fillfactor của heap table. Vì sao 100 không có nghĩa HOT bị tắt?

### Bài 15 — Fillfactor 80

Tạo bảng với fillfactor=80. Giải thích khoảng trống được dùng vào việc gì và vì sao không phải mỗi page luôn có đúng 20% free bytes.

### Bài 16 — Alter fillfactor

Chạy ALTER TABLE SET fillfactor=70 trên bảng đã có dữ liệu. Những page cũ có tự được rewrite không?

### Bài 17 — Rewrite table

So sánh VACUUM thường với VACUUM FULL về dead tuple reuse, table size và locking.

### Bài 18 — B-tree fillfactor

Tạo B-tree index với fillfactor=80. Vì sao điều này không tự làm UPDATE trên cột indexed thành HOT?

### Bài 19 — Index split

Giải thích index fillfactor có thể ảnh hưởng page splits thế nào và trade-off về index size/cache.

### Bài 20 — FSM

Cài pg_freespacemap, truy vấn pg_freespace và giải thích vì sao FSM chỉ là thông tin xấp xỉ.

### Bài 21 — pgstattuple

Dùng pgstattuple đọc live tuples, dead tuples và free space. Vì sao không nên chạy exact scan tùy tiện trên bảng rất lớn?

### Bài 22 — HOT ratio

Viết query tính n_tup_hot_upd / n_tup_upd. Vì sao ratio không có ý nghĩa nhiều khi bảng hầu như không UPDATE?

### Bài 23 — Stats delay

Sau UPDATE, query stats ngay và thấy counters chưa đổi. Nêu những nguyên nhân có thể và cách quan sát lại sau commit.

### Bài 24 — Lab HOT

Tạo bảng fillfactor=70, insert 20.000 rows, update last_seen không index rồi đọc n_tup_hot_upd. Điều kiện nào có thể làm một số update không HOT?

### Bài 25 — Lab non-HOT

Tạo index trên last_seen và lặp lại UPDATE. So sánh counters trước/sau theo delta.

### Bài 26 — Row growth

Một UPDATE tăng description từ 100 bytes lên 2 KB. Vì sao fillfactor 80 không bảo đảm HOT?

### Bài 27 — Index audit

Dùng pg_get_indexdef liệt kê mọi index của bảng. Tìm cột được tham chiếu trong key, INCLUDE, expression và predicate.

### Bài 28 — Bỏ index?

Một index trên last_seen làm HOT ratio giảm nhưng phục vụ truy vấn dashboard quan trọng. Đề xuất benchmark và tiêu chí quyết định giữ/bỏ.

### Bài 29 — No-op UPDATE

So sánh `UPDATE SET status=status` với UPDATE có điều kiện `status IS DISTINCT FROM $1`. Tác động tới tuple versions và WAL là gì?

### Bài 30 — Autovacuum

Một bảng có n_dead_tup tăng nhanh và last_autovacuum cách đây nhiều giờ. Những thông tin nào cần xem trước khi thay autovacuum settings?

### Bài 31 — Long-running transaction

Giải thích transaction snapshot kéo dài có thể làm chậm cleanup HOT chains/dead tuples thế nào.

### Bài 32 — Partition fillfactor

Tạo parent partitioned table và hai leaf partitions với fillfactor khác nhau. Viết query kiểm tra reloptions từng leaf.

### Bài 33 — Workload append-only

Vì sao bảng chỉ INSERT và gần như không UPDATE thường có thể dùng fillfactor 100?

### Bài 34 — Workload heartbeat

Thiết kế bảng heartbeat sao cho các cột thay đổi thường xuyên không bị index không cần thiết tham chiếu.

### Bài 35 — Tách bảng

Một bảng profile chứa cả thông tin ổn định và heartbeat. Nêu lợi ích/chi phí khi tách heartbeat sang bảng riêng.

### Bài 36 — WAL

HOT update có giảm toàn bộ WAL không? Phân biệt heap changes và index maintenance.

### Bài 37 — Replication

Một bảng có HOT ratio cao nhưng vẫn có lượng WAL lớn. Giải thích vì sao standby vẫn có thể lag.

### Bài 38 — Fillfactor benchmark

Thiết kế benchmark so sánh 100/90/80/70. Nêu dữ liệu, index, update pattern và metrics cần cố định.

### Bài 39 — Table size

Dùng pg_relation_size, pg_indexes_size và pg_total_relation_size. Vì sao cần đo heap và indexes riêng?

### Bài 40 — Bloat vs free space

Một bảng có free_percent 25% sau khi đặt fillfactor 75. Có thể kết luận bảng bị bloat không? Cần thêm dữ liệu gì?

### Bài 41 — Pageinspect

Dùng pageinspect đọc page header và heap_page_items. Vì sao đây là công cụ chẩn đoán nội bộ, không phải API ổn định?

### Bài 42 — Fillfactor index vs table

Một DBA hạ B-tree fillfactor từ 90 xuống 70 và kỳ vọng HOT tăng. Hãy giải thích sai lầm.

### Bài 43 — Concurrent updates

Hai sessions cùng UPDATE các hàng trên một page. Vì sao kết quả HOT có thể khác benchmark tuần tự?

### Bài 44 — Large table rewrite

Một bảng 2 TB cần đổi fillfactor từ 100 xuống 80. Lập kế hoạch đánh giá disk space, lock, replication, backup và rollback.

### Bài 45 — Production diagnosis

HOT ratio giảm từ 80% xuống 15% sau một release. Xây dựng quy trình điều tra index mới, query updates, fillfactor, row growth, partitions và autovacuum.

### Bài 46 — Thiết kế end-to-end

Một hệ thống IoT nhận 100.000 heartbeat/giây, đọc trạng thái theo device_id, lọc một số thiết bị theo status và có dashboard theo last_seen. Thiết kế indexes, fillfactor, HOT strategy, partitioning, vacuum policy và benchmark sao cho cân bằng write throughput với query latency.

---

## 37. Checklist tuning Fillfactor và HOT

| Câu hỏi | Điều cần xác nhận |
| --- | --- |
| Bảng có UPDATE thường xuyên? | Tần suất và loại cột thay đổi |
| Cột được UPDATE có index không? | Audit toàn bộ indexes |
| Có expression/partial indexes? | Xét dependencies |
| Có INCLUDE columns? | Xem cột thay đổi |
| Index type có summarizing exception? | Xem BRIN/version |
| Tuple version mới có vừa page? | Row width/growth |
| Table fillfactor hiện tại? | reloptions |
| Fillfactor có áp dụng lên pages mới? | Đúng physical table/partition |
| Dữ liệu cũ có cần rewrite? | Lock/disk/availability |
| HOT ratio bao nhiêu? | n_tup_hot_upd/n_tup_upd |
| Counter có baseline/time window? | Tránh so số tích lũy sai |
| Dead tuples có tăng? | n_dead_tup/pgstattuple |
| FSM free space ra sao? | pg_freespace |
| Vacuum có theo kịp? | last_autovacuum/count/duration |
| Có transaction dài? | Snapshot/xmin |
| Index bloat có giảm? | Index size/statistics |
| Heap size có tăng quá mức? | pg_relation_size |
| Sequential scans có chậm hơn? | Buffers/read latency |
| WAL volume ra sao? | Write amplification |
| Replica lag có thay đổi? | HA metrics |
| Có no-op UPDATE? | IS DISTINCT FROM |
| Có update cột indexed không cần thiết? | Query/index review |
| Có tách hot/cold columns? | Model design |
| Partition settings đồng nhất? | Leaf reloptions |
| B-tree fillfactor có bị nhầm? | Kiểm tra riêng |
| Có benchmark nhiều mức? | 100/90/80/70 hoặc phù hợp |
| Có test concurrency? | Workload tương tự production |
| Có kiểm tra data correctness? | Constraints/transactions |
| Có plan VACUUM FULL/repack? | Lock/disk/rollback |
| Có theo dõi sau triển khai? | HOT, bloat, latency, WAL |
| Có rollback setting? | ALTER TABLE SET/RESET |
| Có tài liệu tuning rationale? | Lý do và workload evidence |

## Kết luận

**Fillfactor, HOT update và không gian trống trên trang** là những khái niệm gắn với nhau ở tầng heap storage và MVCC. Chúng có thể giúp PostgreSQL xử lý UPDATE hiệu quả hơn, đặc biệt ở những bảng có nhiều thay đổi trên các cột không được index tham chiếu.

Những nguyên tắc quan trọng:

1. **UPDATE thường tạo tuple version mới theo MVCC.** Phiên bản cũ cần được giữ cho tới khi không còn snapshot nào cần nó; VACUUM và pruning hỗ trợ cleanup.
2. **HOT update yêu cầu version mới nằm trên cùng heap page và không làm thay đổi các index references theo quy tắc HOT.** Chỉ có free space là chưa đủ.
3. **HOT tránh index entries mới cho version mới.** Điều này có thể giảm index churn, WAL liên quan index và bloat, nhưng heap version và WAL vẫn tồn tại.
4. **Fillfactor của heap table tạo cơ hội HOT.** Giá trị thấp để lại khoảng trống khi ghi tuple mới, nhưng không bảo đảm mọi UPDATE thành HOT.
5. **Fillfactor thấp có chi phí.** Heap lớn hơn, nhiều pages hơn, scans có thể đọc nhiều block và cache density có thể giảm.
6. **Index definitions quyết định HOT eligibility.** Key columns, INCLUDE columns, expression dependencies và partial predicates đều cần được xem xét; summarizing indexes có ngoại lệ theo phiên bản.
7. **Table fillfactor khác B-tree index fillfactor.** Index fillfactor ảnh hưởng index page occupancy/splits, không trực tiếp tạo điều kiện HOT trên heap.
8. **Đổi fillfactor không tự rewrite dữ liệu cũ.** Cần đánh giá VACUUM FULL, CLUSTER hoặc công cụ repack nếu muốn bố trí lại pages, với lock và disk requirements rõ ràng.
9. **FSM, pgstattuple và pg_stat_user_tables giúp chẩn đoán.** Dùng free space, dead tuples, HOT counters và kích thước relation cùng nhau, không dựa vào một metric.
10. **VACUUM vẫn cần thiết.** HOT không xóa nhu cầu dọn dead tuples và HOT chains.
11. **Không index cột thường thay đổi nếu workload không cần.** Nhưng không bỏ index quan trọng chỉ để tăng HOT ratio; phải đo cả query reads và writes.
12. **Tune bằng workload thật.** So sánh fillfactor, HOT ratio, table/index size, WAL, autovacuum, replication lag và latency trước/sau.

Một thiết kế lưu trữ tốt không cố lấp đầy mọi page hoặc tối đa hóa HOT bằng mọi giá. Nó chọn cách phân bố dữ liệu sao cho **UPDATE được xử lý hiệu quả, index không tăng trưởng không cần thiết, VACUUM theo kịp và các truy vấn đọc vẫn đáp ứng yêu cầu vận hành**.
