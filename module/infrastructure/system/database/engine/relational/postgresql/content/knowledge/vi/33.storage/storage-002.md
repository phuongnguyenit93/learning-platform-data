# ctid, tableoid và giới hạn của định danh vật lý trong PostgreSQL

Khi truy vấn một bảng PostgreSQL, ngoài các cột do ứng dụng định nghĩa, bạn có thể đọc một số **system columns** do PostgreSQL cung cấp. Hai cột thường gây nhầm lẫn nhất là:

- **ctid**: vị trí vật lý của một phiên bản hàng (tuple version) bên trong một bảng.
- **tableoid**: OID của bảng vật lý đang chứa hàng đó.

Chúng hữu ích khi điều tra storage, phân biệt hàng đến từ partition nào hoặc xử lý một nhóm hàng ngay trong cùng câu lệnh SQL. Tuy nhiên, chúng **không phải định danh nghiệp vụ bền vững** như primary key.

Một hàng có thể được UPDATE và tạo phiên bản tuple mới với ctid khác. Một bảng có thể được rewrite bởi VACUUM FULL hoặc CLUSTER, làm các vị trí vật lý thay đổi. Khi truy vấn bảng partitioned hoặc inheritance parent, ctid chỉ có ý nghĩa trong từng bảng con; cần kết hợp với tableoid để phân biệt nguồn chứa.

~~~mermaid
flowchart TD
    R["Một hàng PostgreSQL"] --> V["MVCC tuple version"]
    V --> C["ctid = (block, offset)"]
    V --> T["tableoid = OID bảng vật lý"]
    C --> L["Vị trí vật lý tạm thời"]
    T --> P["Xác định relation chứa hàng"]
    L --> N["Có thể thay đổi sau UPDATE / rewrite"]
    P --> J["Kết hợp tableoid + ctid khi cần locator"]
    J --> U["Không thay thế khóa nghiệp vụ"]
~~~

Bài thuộc chương **Lưu trữ**, module **Database Engine Relational PostgreSQL**. Chúng ta sẽ tìm hiểu cấu trúc tuple, MVCC, các thao tác làm thay đổi ctid, cách tableoid hoạt động với partition, các tình huống dùng locator trong một statement và lý do không nên lưu chúng làm khóa lâu dài.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích ctid là physical tuple identifier kiểu tid.
2. Đọc ctid dưới dạng cặp block number và item/offset number.
3. Giải thích tableoid và cách cast sang regclass để xem tên relation.
4. Phân biệt physical locator với primary key/business key.
5. Hiểu vì sao UPDATE tạo tuple version mới và thường làm ctid thay đổi.
6. Hiểu HOT update vẫn tạo phiên bản tuple mới, dù có thể không cần cập nhật index entries.
7. Phân biệt tác động của VACUUM thường với VACUUM FULL/CLUSTER và các thao tác rewrite.
8. Dùng tableoid để nhận biết partition hoặc inheritance child chứa hàng.
9. Kết hợp tableoid và ctid khi locator phải phân biệt nhiều bảng vật lý.
10. Dùng ctid cho thao tác bảo trì theo lô trong cùng một statement khi có lý do phù hợp.
11. Hiểu giới hạn concurrency, row locks, MVCC snapshot và partition row movement.
12. Tránh dùng ctid làm primary key, foreign key, pagination token, replication key hoặc bookmark lâu dài.
13. Biết các system columns liên quan như xmin và xmax cũng không phải audit fields ổn định.
14. Kiểm tra dữ liệu và catalog mà không dựa vào giá trị vật lý cố định.
15. Chọn logical key và thiết kế index phù hợp cho truy vấn nghiệp vụ.

## 2. System columns là gì?

PostgreSQL lưu thêm metadata cho mỗi tuple. Một số metadata có thể được truy cập qua tên system column:

| System column | Kiểu dữ liệu | Ý nghĩa |
| --- | --- | --- |
| **tableoid** | oid | OID của relation chứa tuple |
| **ctid** | tid | Vị trí vật lý của phiên bản tuple trong relation |
| **xmin** | xid | Transaction ID liên quan tới việc insert tuple version |
| **xmax** | xid | Transaction ID liên quan tới delete/update hoặc một số trạng thái khóa tuple |
| **cmin** | cid | Command ID liên quan tới insert trong transaction |
| **cmax** | cid | Command ID liên quan tới delete/update trong transaction |

Những cột này do PostgreSQL quản lý, không phải các cột bạn khai báo trong CREATE TABLE.

### Không xuất hiện trong SELECT *

Ví dụ:

~~~sql
SELECT *
FROM public.orders;
~~~

thường chỉ trả về các cột được định nghĩa trong bảng, **không tự thêm các system columns**. Muốn đọc, phải gọi tên tường minh:

~~~sql
SELECT
    order_id,
    status,
    tableoid,
    ctid,
    xmin,
    xmax
FROM public.orders;
~~~

Bạn cũng có thể dùng alias của bảng:

~~~sql
SELECT
    o.order_id,
    o.tableoid,
    o.ctid
FROM public.orders AS o;
~~~

System columns là công cụ quan sát storage/MVCC. Không nên xem chúng như những field business bình thường để serialize vào API.

## 3. ctid là gì?

ctid có kiểu PostgreSQL tid, biểu diễn vị trí tuple trong một relation bằng cặp:

~~~text
(block_number, item_offset)
~~~

Ví dụ một giá trị có dạng:

~~~text
(12,7)
~~~

Có thể hiểu:

- 12: block/page number trong relation.
- 7: item identifier/offset number của line pointer trong page đó.

Một page thường có kích thước theo cấu hình PostgreSQL (thường là 8 KiB, nhưng có thể khác tùy build). Một block chứa page header, line pointers và tuple data; item offset xác định một line pointer trong page.

**ctid không phải số thứ tự hàng** và không có nghĩa “hàng thứ 7 của bảng ở trang 12” theo thứ tự SQL.

### Ví dụ xem ctid

~~~sql
SELECT
    order_id,
    status,
    ctid
FROM public.orders
ORDER BY order_id
LIMIT 20;
~~~

Kết quả minh họa:

| order_id | status | ctid |
| ---: | --- | --- |
| 101 | new | (0,1) |
| 102 | paid | (0,3) |
| 103 | new | (1,2) |

Các giá trị trên chỉ để minh họa định dạng. **Không có quy tắc rằng order_id nhỏ phải có ctid nhỏ**, hoặc ctid liên tục không có khoảng trống.

### ctid thuộc về tuple version

PostgreSQL dùng MVCC. Một hàng logic có thể có nhiều phiên bản tuple do UPDATE. ctid chỉ xác định vị trí của **một phiên bản vật lý cụ thể**, không phải danh tính vĩnh viễn của hàng logic.

## 4. tableoid là gì?

tableoid là OID của relation đang chứa tuple. Với bảng thường, mọi hàng được đọc từ bảng đó có cùng tableoid.

Ví dụ:

~~~sql
SELECT
    tableoid,
    tableoid::regclass AS physical_table,
    ctid,
    order_id
FROM public.orders
ORDER BY order_id;
~~~

- tableoid trả giá trị OID.
- tableoid::regclass chuyển OID thành tên relation có thể đọc được.
- ctid cho biết vị trí tuple trong relation đó.

### OID không phải ID nghiệp vụ

OID giúp PostgreSQL tham chiếu object trong catalog tại thời điểm hiện tại. Nó không phải mã bảng bền vững qua mọi vòng đời:

- DROP rồi CREATE lại relation sẽ tạo object mới.
- Dump/restore tạo object mới trong cluster đích; không dùng OID cũ làm định danh ngoài hệ thống.
- OID là không gian định danh có giới hạn và không phải hợp đồng lưu trữ lâu dài.
- Đổi tên relation không nhất thiết đổi OID, nhưng tên hiển thị có thể đổi.

Vì vậy tableoid hữu ích để **nhận diện relation đang chứa row trong database hiện tại**, không phải một global table ID để lưu vào business event mãi mãi.

## 5. ctid và tableoid có quan hệ thế nào?

Trong một bảng đơn, ctid thường đủ để định vị một tuple version trong relation đó ở thời điểm phù hợp.

Nhưng khi query nhiều relation qua inheritance hoặc partitioned table, nhiều bảng có thể cùng có tuple ctid như (0,1). ctid không duy nhất giữa các bảng.

Do đó khi cần locator trên kết quả có thể chứa nhiều relation:

~~~sql
SELECT
    tableoid::regclass AS source_table,
    ctid,
    order_id
FROM public.orders_parent;
~~~

Có thể coi cặp **(tableoid, ctid)** là locator vật lý để phân biệt tuple trong nhiều relation tại thời điểm truy vấn.

### Cặp này vẫn không phải khóa bền vững

- ctid có thể thay đổi khi tuple được UPDATE hoặc relation được rewrite.
- tableoid có thể thay đổi khi relation bị drop/recreate, thay đổi cấu trúc hoặc dữ liệu được chuyển sang relation khác.
- Một transaction khác có thể làm trạng thái vật lý thay đổi sau khi locator được lưu.
- Restore sang cluster khác không bảo đảm OID giữ nguyên.

**(tableoid, ctid) là locator vật lý có phạm vi ngắn, không phải composite primary key.**

## 6. Vì sao PostgreSQL cần ctid?

PostgreSQL lưu table data trong heap pages. Index cần tham chiếu tới vị trí tuple trong heap để tìm row version tương ứng. TID/ctid là một phần của cơ chế định vị vật lý.

Một cách nhìn khái quát:

~~~text
B-tree index entry
       |
       v
Heap TID (block, offset)
       |
       v
Heap page
       |
       v
Line pointer
       |
       v
Tuple version
~~~

Đây là mô hình khái niệm. PostgreSQL còn có MVCC visibility checks, HOT chains, page pruning và nhiều chi tiết nội bộ khác. Một index entry trỏ tới vị trí heap không có nghĩa tuple đó chắc chắn visible với mọi transaction.

### Vì sao người dùng SQL nhìn thấy ctid?

Nó hữu ích trong một số công việc kỹ thuật:

- Điều tra tuple/version.
- Chẩn đoán page/heap behavior.
- Chọn một nhóm row vật lý cho maintenance cùng statement.
- Phân biệt row đến từ child relation.
- Kiểm tra một số vấn đề duplicate data không có khóa logic.

Nhưng việc PostgreSQL cung cấp cột này **không biến nó thành API định danh bền vững cho ứng dụng**.

## 7. MVCC: UPDATE không sửa tuple cũ tại chỗ theo cách đơn giản

PostgreSQL sử dụng Multi-Version Concurrency Control (MVCC). Khi một transaction UPDATE một row, hệ thống thường tạo một tuple version mới và đánh dấu version cũ là không còn visible cho những snapshot phù hợp.

Mô hình đơn giản:

~~~text
Trước UPDATE:
  ctid=(4,2) -> tuple version A, status='new'

Sau UPDATE:
  ctid=(4,2) -> tuple version A (old version)
  ctid=(4,5) -> tuple version B (new version, status='paid')
~~~

Transaction khác nhau có thể nhìn thấy version khác nhau tùy snapshot/visibility rules.

### Xem ctid trước và sau UPDATE

Dùng bảng lab ở phần sau hoặc bảng thử nghiệm của riêng bạn:

~~~sql
BEGIN;

SELECT order_id, status, ctid
FROM jdbc_storage_lab.orders
WHERE order_id = 1;

UPDATE jdbc_storage_lab.orders
SET status = 'paid'
WHERE order_id = 1
RETURNING order_id, status, ctid;

ROLLBACK;
~~~

Trong transaction, RETURNING ctid cho biết vị trí tuple version mới được tạo cho hàng sau UPDATE. Giá trị cụ thể phụ thuộc trạng thái vật lý của bảng; không được hard-code kết quả ví dụ.

Sau ROLLBACK, thay đổi bị hủy và version mới không trở thành dữ liệu đã commit. Ví dụ này chỉ minh họa lifecycle, không phải bài test yêu cầu ctid phải tăng theo một quy luật số học.

## 8. HOT update vẫn tạo tuple version mới

**HOT (Heap-Only Tuple) update** là một tối ưu PostgreSQL khi điều kiện phù hợp, chẳng hạn những cột được cập nhật không cần sửa index entries và page còn đủ chỗ theo điều kiện HOT.

HOT có thể tránh thêm index entries cho phiên bản mới bằng cách duy trì chain trong cùng page.

Nhưng:

- HOT vẫn tạo tuple version mới.
- ctid của phiên bản mới vẫn có thể khác phiên bản cũ.
- Việc tuple ở cùng page không có nghĩa ctid không đổi, vì item offset có thể khác.
- HOT eligibility phụ thuộc schema/indexes, cập nhật cột nào và không gian page; không được ép buộc chỉ bằng việc viết SQL UPDATE.

**Không dùng ctid để phát hiện “hàng có thay đổi hay không” như một audit mechanism.** Hãy dùng cột version/timestamp nghiệp vụ hoặc audit logic được thiết kế rõ.

## 9. UPDATE có thể làm ctid thay đổi ngay cả khi chỉ sửa một cột

Ví dụ:

~~~sql
UPDATE jdbc_storage_lab.orders
SET status = 'paid'
WHERE order_id = 1;
~~~

Dù chỉ đổi status, PostgreSQL vẫn xử lý MVCC tuple version. Không có bảo đảm ctid giữ nguyên.

Một trường hợp khác:

~~~sql
UPDATE jdbc_storage_lab.orders
SET status = status
WHERE order_id = 1;
~~~

Một UPDATE vẫn có thể tạo tuple version mới dù giá trị nhìn thấy không thay đổi, trừ khi câu lệnh/trigger/điều kiện được thiết kế để bỏ qua thao tác. Không dựa vào việc “giá trị y nguyên” để kết luận ctid sẽ ổn định.

Nếu muốn tránh update no-op, có thể viết:

~~~sql
UPDATE jdbc_storage_lab.orders
SET status = 'paid'
WHERE order_id = 1
  AND status IS DISTINCT FROM 'paid';
~~~

Đây là tối ưu theo semantics dữ liệu. Nó không biến ctid thành stable identifier.

## 10. VACUUM thường và VACUUM FULL khác nhau

Hai lệnh cùng có chữ VACUUM nhưng tác động vật lý rất khác:

| Lệnh | Mục đích | Tác động vật lý cần hiểu |
| --- | --- | --- |
| VACUUM table | Thu hồi/reuse space từ dead tuples và hỗ trợ visibility map | Thường không rewrite toàn bộ heap để compact live rows |
| VACUUM (ANALYZE) table | Vacuum và cập nhật thống kê | Không đồng nghĩa rewrite table |
| VACUUM FULL table | Compact relation bằng rewrite | Tạo bản relation mới và thay đổi vị trí tuple |
| CLUSTER table USING index | Rewrite table theo thứ tự index | Có thể thay đổi ctid của các rows |
| Một số ALTER TABLE cần rewrite | Chuyển đổi cấu trúc/kiểu dữ liệu | Có thể tạo physical layout mới |

### Không nên nói quá về VACUUM thường

VACUUM thường chủ yếu đánh dấu/reclaim các vùng dead tuple để có thể tái sử dụng và cập nhật metadata; nó không giống VACUUM FULL compaction. Không nên khẳng định mọi lần chạy VACUUM thường đều đổi ctid của tất cả hàng sống.

Nhưng kết luận thiết kế vẫn là: **ctid không có cam kết ổn định lâu dài**. UPDATE, table rewrite và các thao tác storage khác đủ để làm locator cũ mất hiệu lực.

### VACUUM FULL cần lock mạnh

VACUUM FULL rewrite relation và cần lock mạnh, có thể chặn truy cập đồng thời trong thời gian thực hiện. Đây không phải nút “dọn dẹp định kỳ” nên chạy tùy tiện trên bảng lớn.

## 11. CLUSTER và các thao tác rewrite

CLUSTER sắp xếp lại table theo index được chỉ định bằng cách rewrite relation. Sau thao tác, các tuple vật lý có thể nằm ở block/offset mới.

~~~sql
-- Ví dụ cú pháp; chỉ chạy trên bảng lab sau khi đã tạo index phù hợp.
CLUSTER jdbc_storage_lab.orders
USING idx_orders_customer;
~~~

Cần có index tên idx_orders_customer thật sự tồn tại. CLUSTER có chi phí IO/lock và không tự duy trì thứ tự vật lý sau các lần ghi tiếp theo.

Một số thay đổi DDL có thể rewrite bảng, tùy phiên bản PostgreSQL và loại ALTER. Hãy kiểm tra tài liệu ALTER TABLE và plan triển khai cụ thể.

### Điều gì không được phép giả định?

Không lưu ctid hôm nay rồi dựa vào nó ngày mai sau một migration/rewrite. Không coi ctid là khóa để đồng bộ với hệ thống ngoài. Không dùng nó trong URL/API.

## 12. tableoid trong partitioned tables

Giả sử có bảng orders chia partition theo tháng:

~~~sql
CREATE TABLE jdbc_storage_lab.partitioned_orders (
    order_id bigint NOT NULL,
    created_at date NOT NULL,
    amount numeric(12,2) NOT NULL,
    PRIMARY KEY (order_id, created_at)
) PARTITION BY RANGE (created_at);

CREATE TABLE jdbc_storage_lab.orders_2026_01
PARTITION OF jdbc_storage_lab.partitioned_orders
FOR VALUES FROM ('2026-01-01') TO ('2026-02-01');

CREATE TABLE jdbc_storage_lab.orders_2026_02
PARTITION OF jdbc_storage_lab.partitioned_orders
FOR VALUES FROM ('2026-02-01') TO ('2026-03-01');
~~~

Insert qua parent:

~~~sql
INSERT INTO jdbc_storage_lab.partitioned_orders (
    order_id, created_at, amount
)
VALUES
    (1, DATE '2026-01-10', 100.00),
    (2, DATE '2026-02-15', 200.00);
~~~

Đọc:

~~~sql
SELECT
    order_id,
    created_at,
    tableoid::regclass AS physical_partition,
    ctid
FROM jdbc_storage_lab.partitioned_orders
ORDER BY order_id;
~~~

Kết quả cho thấy:

- Hàng tháng 1 nằm trong orders_2026_01.
- Hàng tháng 2 nằm trong orders_2026_02.
- tableoid::regclass cho biết partition vật lý thực sự chứa hàng.
- ctid chỉ là vị trí trong partition đó.

### Parent partitioned table không chứa những rows này

Partitioned table là relation cha định tuyến; rows được lưu ở các partition con. Query parent thường đọc các partition phù hợp. System column tableoid trên kết quả cho biết relation con đã chứa tuple.

Nếu chỉ SELECT ctid từ parent, các partition khác nhau có thể có cùng ctid. Muốn phân biệt locator vật lý, lấy cả tableoid.

## 13. tableoid trong inheritance tables

PostgreSQL còn hỗ trợ table inheritance:

~~~sql
CREATE TABLE jdbc_storage_lab.assets (
    asset_id bigint,
    description text
);

CREATE TABLE jdbc_storage_lab.vehicles (
    max_speed integer
) INHERITS (jdbc_storage_lab.assets);
~~~

Query parent:

~~~sql
SELECT
    tableoid::regclass AS source_relation,
    ctid,
    asset_id,
    description
FROM jdbc_storage_lab.assets;
~~~

Mặc định truy vấn parent có thể bao gồm rows từ các child tables theo semantics inheritance. tableoid cho biết row thực sự nằm trong parent hay child.

Dùng ONLY để chỉ truy vấn chính relation đó:

~~~sql
SELECT tableoid::regclass, ctid, asset_id
FROM ONLY jdbc_storage_lab.assets;
~~~

### Partitioning và inheritance không hoàn toàn giống nhau

Partitioning có quy tắc partition key, routing, constraints và partition pruning. Inheritance là cơ chế quan hệ cha-con tổng quát hơn. Trong cả hai trường hợp, tableoid giúp nhận diện relation vật lý chứa row, nhưng không nên suy ra mọi semantics của partitioning từ inheritance.

## 14. Vì sao ctid không duy nhất giữa các partition?

Mỗi heap relation có page/block numbering riêng. Vì vậy:

~~~text
orders_2026_01: ctid = (0,1)
orders_2026_02: ctid = (0,1)
~~~

là điều có thể xảy ra.

Nếu query parent trả cả hai rows và chỉ lưu ctid, locator không xác định duy nhất relation chứa tuple.

Cặp:

~~~sql
SELECT tableoid, ctid
FROM jdbc_storage_lab.partitioned_orders;
~~~

giúp phân biệt.

Để hiển thị dễ đọc:

~~~sql
SELECT
    tableoid::regclass AS relation_name,
    ctid,
    order_id
FROM jdbc_storage_lab.partitioned_orders;
~~~

**Ngay cả cặp này cũng chỉ là physical locator trong trạng thái hiện tại**, không phải business key.

## 15. UPDATE partition key có thể chuyển row sang partition khác

Một UPDATE thay partition key có thể làm PostgreSQL chuyển row từ partition cũ sang partition mới:

~~~sql
UPDATE jdbc_storage_lab.partitioned_orders
SET created_at = DATE '2026-02-20'
WHERE order_id = 1
  AND created_at = DATE '2026-01-10';
~~~

Nếu partition đích tồn tại và nhận giá trị mới, row có thể được di chuyển. Hệ quả:

- Relation vật lý thay đổi.
- tableoid thay đổi.
- ctid ở partition mới không còn là locator cũ.
- Các index/constraints và trigger behavior liên quan đến partition movement cần được hiểu theo PostgreSQL version.

Trong concurrent workloads, UPDATE row đang bị một transaction khác di chuyển giữa partitions có thể dẫn đến lỗi serialization theo các trường hợp PostgreSQL mô tả. Không dùng locator cũ để tiếp tục thao tác sau partition movement.

## 16. Dùng ctid để điều tra một row vật lý

Nếu một query đã trả về tableoid/ctid và bạn muốn quan sát lại ngay trong một transaction phù hợp, có thể dùng locator với điều kiện rất chặt.

Ví dụ trên một bảng đơn:

~~~sql
BEGIN;

SELECT order_id, ctid
FROM jdbc_storage_lab.orders
WHERE order_id = 1;

-- Chỉ minh họa dạng so sánh; không hard-code ctid lấy từ ví dụ.
-- Dùng giá trị vừa quan sát trong cùng ngữ cảnh phù hợp.

ROLLBACK;
~~~

Không nên viết API nhận ctid do client gửi rồi UPDATE row tương ứng. Client có thể gửi locator cũ, locator của row khác hoặc locator không còn visible.

### Không lưu ctid trong bảng tham chiếu

Anti-pattern:

~~~sql
CREATE TABLE app.pending_work (
    source_ctid tid NOT NULL
);
~~~

và sau đó dùng source_ctid để tìm lại row trong nhiều transaction. UPDATE/rewrite/partition move có thể làm reference mất hiệu lực hoặc trỏ tới tuple khác sau khi slot được tái sử dụng.

Hãy lưu **primary key/business key**, và nếu cần kiểm soát phiên bản, lưu version column hoặc điều kiện optimistic locking.

## 17. Dùng ctid trong cùng một statement để xóa duplicate

Một use case kỹ thuật quen thuộc là bảng cũ có duplicate và chưa có primary key. Có thể chọn một tuple vật lý để xóa trong cùng statement.

Ví dụ minh họa với bảng contacts:

~~~sql
WITH ranked AS (
    SELECT
        ctid,
        row_number() OVER (
            PARTITION BY email
            ORDER BY created_at, ctid
        ) AS rn
    FROM jdbc_storage_lab.contacts
)
DELETE FROM jdbc_storage_lab.contacts AS c
USING ranked AS r
WHERE c.ctid = r.ctid
  AND r.rn > 1;
~~~

**Đoạn trên chỉ chạy nếu bảng jdbc_storage_lab.contacts với các cột email/created_at đã được tạo.** Nó là ví dụ về kỹ thuật, không phải một phần của schema lab ban đầu.

### Cần chú ý

- ctid được lấy và dùng trong cùng một statement.
- Với bảng đơn, ctid phân biệt tuple trong relation đó.
- Nếu query bao gồm nhiều partitions/inherited relations, cần mang tableoid và join bằng cả hai.
- ORDER BY created_at, ctid chọn survivor theo quy tắc kỹ thuật; nếu nghiệp vụ cần giữ bản ghi mới nhất/được xác nhận, phải dùng tiêu chí nghiệp vụ.
- Backup và preview duplicates trước khi DELETE.
- Chạy trong transaction, review số rows và có kế hoạch rollback.

Không xóa duplicate chỉ dựa vào ctid mà chưa xác định row nào là bản ghi canonical.

## 18. Dùng ctid + tableoid cho batch maintenance

Một số tác vụ bảo trì cần lấy một nhóm hàng, khóa chúng rồi update/delete trong cùng statement. Với partitioned table, có thể kết hợp tableoid và ctid.

Ví dụ ý tưởng xử lý 500 sự kiện pending:

~~~sql
WITH batch AS (
    SELECT
        tableoid,
        ctid
    FROM jdbc_storage_lab.partitioned_events
    WHERE processed_at IS NULL
    ORDER BY event_id
    FOR UPDATE SKIP LOCKED
    LIMIT 500
)
UPDATE jdbc_storage_lab.partitioned_events AS e
SET processed_at = clock_timestamp()
FROM batch AS b
WHERE e.tableoid = b.tableoid
  AND e.ctid = b.ctid
RETURNING e.event_id, e.tableoid::regclass;
~~~

Đoạn này yêu cầu một bảng partitioned partitioned_events có các cột phù hợp; nó minh họa mẫu, không phải lệnh chạy trực tiếp trên schema lab hiện tại.

### Vì sao dùng FOR UPDATE SKIP LOCKED?

- FOR UPDATE khóa những hàng được chọn trong transaction.
- SKIP LOCKED bỏ qua rows đang bị lock bởi transaction khác, hữu ích với một số worker queue.
- CTE giữ locator của những tuple được chọn.
- UPDATE trong cùng statement dùng locator để xác định đúng các hàng đã khóa.

### Vì sao không lưu ctid sang lần chạy sau?

Transaction hiện tại khóa và thao tác cùng nhóm rows. Sau COMMIT, locator không được coi là token bền. Lần chạy tiếp theo phải truy vấn lại bằng điều kiện nghiệp vụ như processed_at IS NULL.

### Không thay ORDER BY nghiệp vụ bằng ctid

ORDER BY event_id giúp xác định ưu tiên theo business key. ctid không biểu diễn thứ tự thời gian hay ưu tiên xử lý. Chỉ dùng ctid làm locator sau khi đã chọn row theo điều kiện có nghĩa.

## 19. Batch DELETE với ctid

Một mẫu cùng statement:

~~~sql
WITH batch AS (
    SELECT
        tableoid,
        ctid
    FROM jdbc_storage_lab.partitioned_events
    WHERE expires_at < current_date
    ORDER BY expires_at, event_id
    FOR UPDATE SKIP LOCKED
    LIMIT 500
)
DELETE FROM jdbc_storage_lab.partitioned_events AS e
USING batch AS b
WHERE e.tableoid = b.tableoid
  AND e.ctid = b.ctid
RETURNING e.event_id;
~~~

Mẫu này:

- Chọn một nhóm row theo business condition.
- Khóa rows để các worker khác không xử lý cùng lúc theo cách thông thường.
- Xóa trong cùng statement/transaction.
- Trả về logical IDs để log/checkpoint.

**Không ghi lại ctid để thực hiện DELETE ở job chạy ngày mai.** Nếu cần resume, ghi khóa nghiệp vụ hoặc checkpoint.

## 20. Concurrency: vì sao cùng statement quan trọng?

Giả sử:

1. Transaction A SELECT ctid của row 100.
2. A COMMIT.
3. Transaction B UPDATE row 100, tạo tuple version mới.
4. Transaction A dùng lại ctid cũ ở một transaction khác.

Locator A giữ có thể đã trỏ tới phiên bản cũ không còn visible hoặc slot vật lý đã được tái sử dụng theo thời gian. Nó không còn là định danh logic đáng tin.

Một mẫu an toàn hơn cho batch maintenance là **chọn, khóa và thao tác trong cùng statement/transaction**, ví dụ CTE FOR UPDATE SKIP LOCKED ở trên.

### MVCC và khóa

- ctid không thay thế row lock.
- ctid không giải quyết lost update.
- ctid không thay optimistic version check.
- SKIP LOCKED có semantics bỏ qua hàng đang khóa; kết quả không phải snapshot đầy đủ của mọi row đủ điều kiện.
- Isolation level vẫn ảnh hưởng cách transaction nhìn và xử lý concurrent changes.

## 21. Optimistic locking nên dùng version column

Nếu application cần phát hiện row đã bị sửa kể từ lúc đọc, thêm version column:

~~~sql
ALTER TABLE jdbc_storage_lab.orders
ADD COLUMN version bigint NOT NULL DEFAULT 1;
~~~

Update:

~~~sql
UPDATE jdbc_storage_lab.orders
SET
    status = 'paid',
    version = version + 1
WHERE order_id = 1
  AND version = 3
RETURNING order_id, status, version;
~~~

Nếu không có row trả về, có thể version đã thay đổi hoặc row không còn tồn tại; application cần xử lý conflict theo business contract.

### Vì sao tốt hơn ctid?

- Version là field logic được thiết kế rõ.
- Có thể truyền qua API/checkpoint theo contract.
- Không phụ thuộc physical page/offset.
- Có thể dùng cùng primary key để phát hiện concurrent modification.

Không dùng ctid làm version counter. ctid có định dạng vật lý và không có cam kết tăng tuần tự.

## 22. Pagination bằng ctid là thiết kế không bền

Một anti-pattern:

~~~sql
SELECT order_id, ctid
FROM jdbc_storage_lab.orders
WHERE ctid > '(10,1)'::tid
ORDER BY ctid
LIMIT 100;
~~~

Rồi trang sau lưu ctid cuối cùng và dùng làm cursor token lâu dài.

Các vấn đề:

- UPDATE làm tuple version mới có ctid khác.
- Row có thể bị di chuyển/rewrite.
- Thứ tự vật lý không phải business order.
- Concurrent updates có thể làm row đổi vị trí vật lý.
- Partitioned table cần tableoid để phân biệt.
- VACUUM/rewrite và các hoạt động storage làm physical locator không phù hợp cho bookmark dài hạn.

### Dùng keyset theo khóa logic

~~~sql
SELECT order_id, status
FROM jdbc_storage_lab.orders
WHERE order_id > ?
ORDER BY order_id
LIMIT ?;
~~~

Khóa order_id được thiết kế cho pagination; có index/constraint và semantics ổn định hơn nhiều so với ctid.

## 23. ctid có thể dùng thay primary key không?

**Không.**

Primary key cần:

- Duy nhất theo quy tắc dữ liệu.
- NOT NULL.
- Ổn định theo business lifecycle.
- Được tham chiếu bởi foreign keys.
- Dùng trong API, event, replication và application code.
- Có semantics được hệ thống thống nhất.

ctid:

- Là vị trí vật lý của tuple version.
- Có thể đổi khi UPDATE.
- Có thể thay đổi sau rewrite.
- Không có nghĩa nghiệp vụ.
- Không phù hợp foreign key.
- Không đảm bảo ổn định qua restore/migration.

### Nếu bảng chưa có primary key?

Hãy tìm một natural/business key hợp lệ hoặc tạo surrogate key (identity/UUID) theo thiết kế. Đừng chọn ctid chỉ vì nó “đang unique”.

## 24. ctid không phải replication identity

Logical replication cần xác định row nguồn để truyền UPDATE/DELETE theo cơ chế replica identity. Thông thường primary key hoặc unique index phù hợp được dùng.

Nếu bảng không có key phù hợp, PostgreSQL có REPLICA IDENTITY FULL để dùng toàn bộ row image theo giới hạn/chi phí của nó.

**ctid không phải replica identity bền vững để đồng bộ giữa hai database.** Physical TID ở publisher không có ý nghĩa tương đương ở subscriber, vì hai heap layouts độc lập.

Nếu cần logical replication, thiết kế primary key/unique key và replica identity theo yêu cầu của workload.

## 25. Các system columns xmin và xmax cũng không phải audit fields

xmin/xmax thường được dùng để tìm hiểu MVCC:

- xmin liên quan transaction tạo tuple version.
- xmax liên quan transaction xóa/update tuple hoặc trạng thái khóa/transaction metadata khác theo semantics nội bộ.

Nhưng không nên diễn giải đơn giản:

~~~text
xmin = ai tạo row
xmax = ai xóa row
~~~

Vì:

- Transaction ID không phải actor/user ID.
- XID có vòng đời/wraparound và cách biểu diễn nội bộ.
- xmax có thể phản ánh locking metadata, không đơn giản là row đã bị xóa.
- Freeze và visibility rules làm việc diễn giải raw XID phức tạp.
- Không phải timestamp.
- Không thay audit log.

### Muốn biết ai sửa và lúc nào?

Thêm metadata nghiệp vụ có chủ đích như created_at, updated_at, created_by, updated_by hoặc audit table/CDC. Các field này cũng cần trust boundary rõ ràng; không mặc định client tự gửi actor ID là bằng chứng đáng tin.

## 26. Cẩn thận khi join hai bảng bằng ctid

Sai:

~~~sql
SELECT *
FROM orders AS o
JOIN payments AS p
  ON o.ctid = p.ctid;
~~~

Hai bảng có thể cùng có ctid như (0,1); điều đó không có nghĩa chúng là cùng một hàng hay liên quan nghiệp vụ.

Đúng:

~~~sql
SELECT *
FROM orders AS o
JOIN payments AS p
  ON o.order_id = p.order_id;
~~~

Nếu thực sự đang xử lý physical locator từ nhiều relation, phải giữ cả tableoid và ctid theo ngữ cảnh, nhưng join nghiệp vụ vẫn nên dựa vào foreign key/logical key.

## 27. Tìm tên relation từ tableoid

Một truy vấn hữu ích:

~~~sql
SELECT
    tableoid,
    tableoid::regclass AS relation_name,
    count(*) AS row_count
FROM jdbc_storage_lab.partitioned_orders
GROUP BY tableoid
ORDER BY relation_name;
~~~

Kết quả cho biết số rows theo relation vật lý.

### Vì sao regclass tiện?

regclass là kiểu OID alias cho relation. Cast giúp PostgreSQL hiển thị tên relation theo quy tắc search_path/schema qualification.

Nếu cần ghi log/diagnostic, có thể dùng:

~~~sql
SELECT
    tableoid::regclass::text AS relation_name,
    ctid,
    order_id
FROM jdbc_storage_lab.partitioned_orders;
~~~

Tên hiển thị vẫn có thể thay đổi khi relation được rename. Muốn lịch sử lâu dài, cần record schema/object migration metadata riêng.

## 28. ctid và ORDER BY

Có thể viết:

~~~sql
SELECT ctid, order_id
FROM jdbc_storage_lab.orders
ORDER BY ctid;
~~~

PostgreSQL có thể sắp xếp theo giá trị tid. Nhưng:

- Đây là thứ tự physical locator, không phải thứ tự nghiệp vụ.
- Không đảm bảo cùng thứ tự sau UPDATE/rewrite.
- Không thay ORDER BY trên cột business.
- Không đảm bảo pagination ổn định khi concurrent changes.

Dùng ORDER BY ctid cho một tác vụ chẩn đoán hoặc lựa chọn vật lý tạm thời có thể hợp lý, nhưng không dùng làm thứ tự API/report mà người dùng mong đợi.

## 29. Dùng ctid khi bảng có duplicate và không có key: cẩn thận

Trong một bảng legacy thiếu khóa, ctid có thể là cách xác định một tuple cụ thể trong một câu lệnh maintenance.

Nhưng đây là **giải pháp chuyển tiếp**, không phải thiết kế schema lâu dài.

Quy trình nên là:

1. Xác định duplicate theo business columns.
2. Chọn canonical row theo tiêu chí nghiệp vụ.
3. Dùng ctid trong cùng statement để xóa/cập nhật các tuple đã chọn.
4. Xác minh dữ liệu sau thao tác.
5. Tạo unique constraint/index nếu dữ liệu và business rule cho phép.
6. Bổ sung primary key phù hợp nếu cần.
7. Sửa ứng dụng để tham chiếu logical key.

Nếu bảng thiếu primary key, hãy coi đó là vấn đề mô hình dữ liệu cần giải quyết.

## 30. Lab: quan sát ctid thay đổi

Tạo schema và bảng thực hành:

~~~sql
-- CHỈ CHẠY TRONG DATABASE THỰC HÀNH.
DROP SCHEMA IF EXISTS jdbc_storage_lab CASCADE;
CREATE SCHEMA jdbc_storage_lab;

CREATE TABLE jdbc_storage_lab.orders (
    order_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_ref text NOT NULL,
    status text NOT NULL DEFAULT 'new',
    amount numeric(12,2) NOT NULL CHECK (amount > 0),
    created_at timestamptz NOT NULL
        DEFAULT transaction_timestamp()
);

CREATE INDEX idx_orders_customer
ON jdbc_storage_lab.orders (customer_ref);

INSERT INTO jdbc_storage_lab.orders (
    customer_ref, status, amount
)
SELECT
    'customer-' || (g % 100)::text,
    'new',
    (10 + (g % 1000))::numeric(12,2)
FROM generate_series(1, 1000) AS s(g);

ANALYZE jdbc_storage_lab.orders;
~~~

### Quan sát ban đầu

~~~sql
SELECT
    order_id,
    customer_ref,
    status,
    tableoid::regclass AS physical_table,
    ctid
FROM jdbc_storage_lab.orders
WHERE order_id BETWEEN 1 AND 10
ORDER BY order_id;
~~~

Ghi nhận ctid ở lần quan sát này chỉ để so sánh trong lab. Không đưa các giá trị cụ thể vào code application.

### UPDATE một hàng

~~~sql
BEGIN;

SELECT order_id, status, ctid
FROM jdbc_storage_lab.orders
WHERE order_id = 1;

UPDATE jdbc_storage_lab.orders
SET status = 'paid'
WHERE order_id = 1
RETURNING order_id, status, ctid;

ROLLBACK;
~~~

Quan sát ctid được trả về sau UPDATE trong transaction. Có thể thấy vị trí tuple version khác; giá trị cụ thể phụ thuộc page layout và hoạt động đồng thời.

### Vì sao ROLLBACK?

Để khôi phục trạng thái business row của lab sau khi quan sát. Sequence/identity allocations không nhất thiết được hoàn nguyên; không kỳ vọng ID tiếp theo liền mạch.

## 31. Lab partition để thấy tableoid và ctid

~~~sql
CREATE TABLE jdbc_storage_lab.partitioned_orders (
    order_id bigint NOT NULL,
    created_at date NOT NULL,
    amount numeric(12,2) NOT NULL,
    PRIMARY KEY (order_id, created_at)
) PARTITION BY RANGE (created_at);

CREATE TABLE jdbc_storage_lab.orders_2026_01
PARTITION OF jdbc_storage_lab.partitioned_orders
FOR VALUES FROM ('2026-01-01') TO ('2026-02-01');

CREATE TABLE jdbc_storage_lab.orders_2026_02
PARTITION OF jdbc_storage_lab.partitioned_orders
FOR VALUES FROM ('2026-02-01') TO ('2026-03-01');

INSERT INTO jdbc_storage_lab.partitioned_orders
    (order_id, created_at, amount)
VALUES
    (1, DATE '2026-01-10', 10),
    (2, DATE '2026-01-11', 20),
    (3, DATE '2026-02-10', 30),
    (4, DATE '2026-02-11', 40);
~~~

Query:

~~~sql
SELECT
    order_id,
    tableoid::regclass AS physical_partition,
    ctid
FROM jdbc_storage_lab.partitioned_orders
ORDER BY order_id;
~~~

Quan sát:

- Các hàng có cùng partition có cùng relation name.
- Hai partition độc lập có thể có ctid giống nhau.
- Cặp tableoid/ctid mới phân biệt được locator vật lý giữa chúng trong lần query đó.

## 32. Batch update an toàn trong cùng statement

Dùng bảng đơn orders và điều kiện business:

~~~sql
BEGIN;

WITH selected AS (
    SELECT ctid
    FROM jdbc_storage_lab.orders
    WHERE status = 'new'
    ORDER BY order_id
    FOR UPDATE SKIP LOCKED
    LIMIT 25
)
UPDATE jdbc_storage_lab.orders AS o
SET status = 'paid'
FROM selected AS s
WHERE o.ctid = s.ctid
RETURNING o.order_id, o.status, o.ctid;

ROLLBACK;
~~~

Trong bảng đơn, ctid là locator trong relation đó. SELECT khóa các rows được chọn và UPDATE dùng locator trong cùng statement.

### Phiên bản partitioned table

~~~sql
BEGIN;

WITH selected AS (
    SELECT tableoid, ctid
    FROM jdbc_storage_lab.partitioned_orders
    ORDER BY created_at, order_id
    FOR UPDATE SKIP LOCKED
    LIMIT 2
)
UPDATE jdbc_storage_lab.partitioned_orders AS p
SET amount = amount + 1
FROM selected AS s
WHERE p.tableoid = s.tableoid
  AND p.ctid = s.ctid
RETURNING p.order_id, p.tableoid::regclass, p.ctid;

ROLLBACK;
~~~

Ví dụ này chọn rows ở nhiều partition và giữ cả tableoid/ctid. Nó chỉ minh họa batch locator; không lưu cặp locator sau transaction.

## 33. Tại sao phải giữ logic selection theo business key?

Trong batch mẫu:

~~~sql
ORDER BY created_at, order_id
~~~

xác định thứ tự nghiệp vụ có thể giải thích được. ctid chỉ được dùng ở bước sau để định vị tuple đã khóa.

Nếu thay bằng:

~~~sql
ORDER BY ctid
~~~

thì worker đang ưu tiên theo layout vật lý, không theo thời điểm, ID hay SLA. Sau rewrite, thứ tự có thể khác.

**Hãy chọn row bằng điều kiện/ordering có nghĩa nghiệp vụ, sau đó dùng ctid làm locator tạm nếu có lý do kỹ thuật.**

## 34. DELETE batch có kiểm soát

~~~sql
BEGIN;

WITH selected AS (
    SELECT tableoid, ctid
    FROM jdbc_storage_lab.partitioned_orders
    WHERE amount < 25
    ORDER BY created_at, order_id
    FOR UPDATE SKIP LOCKED
    LIMIT 100
)
DELETE FROM jdbc_storage_lab.partitioned_orders AS p
USING selected AS s
WHERE p.tableoid = s.tableoid
  AND p.ctid = s.ctid
RETURNING p.order_id, p.tableoid::regclass;

ROLLBACK;
~~~

Đây là ví dụ maintenance có transaction rollback. Trong production, chỉ commit sau khi có policy xóa, backup/retention và xác nhận số hàng. Không dùng locator đã lưu từ lần chạy trước.

## 35. Vì sao không lưu ctid trong message queue?

Giả sử một worker gửi message:

~~~json
{
  "table": "public.orders",
  "ctid": "(12,7)"
}
~~~

Consumer nhận message vài phút sau. Trong khoảng đó:

- Row có thể đã UPDATE.
- Tuple version cũ có thể không còn visible.
- Relation có thể được rewrite hoặc partition movement.
- Tên bảng có thể được thay đổi.
- Database có thể restore sang cluster khác.

Message không còn định vị row một cách đáng tin cậy.

### Message nên chứa gì?

~~~json
{
  "event_type": "order.reconcile",
  "order_id": "order-12345",
  "request_id": "req-abc"
}
~~~

Dùng business ID và xác định trạng thái mới nhất bằng truy vấn phù hợp. Nếu cần phát hiện phiên bản, kèm version column hoặc event sequence có semantics rõ.

## 36. ctid và CDC/logical decoding

Change Data Capture thường dựa trên WAL/logical decoding và replica identity để nhận biết thay đổi theo mô hình replication.

Không nên thiết kế consumer coi ctid của publisher là khóa của subscriber:

- Heap layouts độc lập.
- Insert order/physical placement có thể khác.
- Table rewrite không có nghĩa logical identity đổi.
- Logical replication cần primary/unique key hoặc replica identity phù hợp.
- CDC event nên chứa logical keys và metadata event được connector hỗ trợ.

Nếu connector có cung cấp ctid như metadata phụ, chỉ dùng theo contract của connector/version, không biến thành application primary key.

## 37. ctid, tableoid và index scan

Index trong PostgreSQL thường tham chiếu heap tuple qua TID. Khi đọc plan:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, status
FROM jdbc_storage_lab.orders
WHERE order_id = 100;
~~~

Có thể thấy Index Scan hoặc Index Only Scan tùy index/visibility map/columns. ctid là khái niệm physical locator liên quan heap, nhưng không cần SELECT ctid để PostgreSQL sử dụng index.

### Index-only scan không có nghĩa ctid bị thay bằng logical key

Index-only scan có thể lấy dữ liệu cần thiết từ index khi visibility map cho phép xác nhận visibility mà không phải truy cập heap cho mỗi row. Đây là tối ưu query plan riêng, không làm thay đổi vai trò của ctid.

## 38. Page và line pointer: đừng diễn giải offset như byte offset

ctid=(block,offset) không phải:

- Byte offset tuyệt đối trong file.
- Số thứ tự dòng trong SQL result.
- Primary key.
- LSN trong WAL.
- Transaction ID.
- Số partition.

Offset là item/line-pointer number trong page. Tuple có thể có header, alignment, TOAST pointers và storage details. Muốn điều tra sâu page layout, cần công cụ/tài liệu chuyên biệt như pageinspect (extension tùy chọn) và phải hiểu đúng version.

Không tính địa chỉ file bằng cách nhân block number với kích thước page rồi cộng offset như thể offset là byte position của tuple.

## 39. tableoid cast regclass và schema resolution

tableoid::regclass hiển thị tên relation thuận tiện. Tuy nhiên biểu diễn text có thể schema-qualify hay không tùy search_path và khả năng phân giải tên.

Để xem OID và namespace:

~~~sql
SELECT
    c.oid,
    c.oid::regclass AS relation_name,
    n.nspname AS schema_name,
    c.relname
FROM pg_class AS c
JOIN pg_namespace AS n
    ON n.oid = c.relnamespace
WHERE c.oid = (
    SELECT tableoid
    FROM jdbc_storage_lab.orders
    LIMIT 1
);
~~~

Đây là truy vấn catalog read-only. pg_class.oid định danh relation hiện tại trong catalog; không lưu nó làm external identifier lâu dài.

## 40. Các giới hạn của ctid và tableoid

| Đặc điểm | ctid | tableoid |
| --- | --- | --- |
| Định vị vật lý | Có, tuple version | Xác định relation chứa tuple |
| Duy nhất trong một relation tại thời điểm phù hợp | Có cho tuple version | Không, nhiều rows cùng tableoid |
| Duy nhất giữa nhiều relation | Không | Chỉ khi kết hợp locator ctid trong ngữ cảnh phù hợp |
| Ổn định qua UPDATE | Không | Thường relation không đổi nếu row không chuyển table |
| Ổn định qua rewrite | Không | Relation OID có thể còn/đổi tùy thao tác; không phải contract bền |
| Có ý nghĩa nghiệp vụ | Không | Không |
| Dùng làm primary key | Không | Không |
| Dùng làm foreign key | Không | Không |
| Dùng làm pagination lâu dài | Không | Không |
| Dùng trong cùng statement maintenance | Có thể | Có ích với nhiều partitions/relations |
| Dùng nhận biết partition vật lý | Không đủ | Có |

## 41. Thiết kế logical identity đúng cách

Một bảng nghiệp vụ thường nên có khóa:

~~~sql
CREATE TABLE app.orders (
    order_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    external_order_id text UNIQUE,
    customer_id bigint NOT NULL,
    status text NOT NULL,
    version bigint NOT NULL DEFAULT 1,
    created_at timestamptz NOT NULL DEFAULT now()
);
~~~

Tùy hệ thống:

- order_id là surrogate primary key.
- external_order_id là key từ hệ thống ngoài nếu có uniqueness contract.
- version dùng optimistic concurrency.
- created_at phục vụ thời gian nghiệp vụ.
- ctid/tableoid chỉ dùng khi cần chẩn đoán hoặc thao tác storage ngắn hạn.

### Natural key hay surrogate key?

Chọn theo semantics nghiệp vụ, độ ổn định, kích thước, uniqueness và yêu cầu tích hợp. Không phải mọi bảng cần cả hai, nhưng hầu hết bảng quan trọng cần một logical key đáng tin.

## 42. Những thao tác có thể làm locator cũ mất hiệu lực

| Thao tác | Ảnh hưởng cần lưu ý |
| --- | --- |
| UPDATE | Tạo tuple version mới; ctid mới có thể khác |
| HOT UPDATE | Vẫn tạo tuple version mới; vị trí line pointer có thể khác trong cùng page |
| VACUUM thường | Reclaim/prune dead tuples; không phải rewrite toàn bộ live rows như VACUUM FULL |
| VACUUM FULL | Rewrite/compact relation; ctid thay đổi |
| CLUSTER | Rewrite table theo index; ctid thay đổi |
| Một số ALTER TABLE | Có thể rewrite relation tùy operation/version |
| Partition key UPDATE | Có thể di chuyển row sang partition khác |
| DROP/CREATE table | Relation identity mới, tableoid mới |
| Restore sang cluster khác | OID và physical layout không được giữ như external contract |
| DELETE rồi INSERT lại | Row mới, locator mới có thể được cấp |

Điểm quan trọng: **không cần mọi thao tác đều làm ctid thay đổi** để kết luận nó không bền vững. Chỉ cần các thao tác nghiệp vụ bình thường như UPDATE đã đủ khiến ctid không phù hợp làm ID.

## 43. Các lỗi thường gặp

1. **Dùng ctid làm primary key** vì thấy nó unique ở bảng hiện tại.
2. **Lưu ctid trong application cache** và dùng lại sau UPDATE.
3. **Dùng ctid làm foreign key** giữa hai bảng.
4. **Dùng ctid làm pagination token** trong API.
5. **Join hai bảng chỉ bằng ctid**, khiến các vị trí vật lý trùng ngẫu nhiên.
6. **Truy vấn parent partitioned table chỉ SELECT ctid**, bỏ qua tableoid.
7. **Cho rằng tableoid là global ID bền vững** qua dump/restore.
8. **Nghĩ ctid là byte offset**, thay vì block/line-pointer pair.
9. **Nghĩ ctid tăng theo order_id hoặc created_at**.
10. **Nghĩ HOT update giữ nguyên ctid**, dù vẫn có tuple version mới.
11. **Cho rằng VACUUM thường và VACUUM FULL đều rewrite giống nhau**.
12. **Chạy VACUUM FULL/CLUSTER trên production mà không tính lock/IO**.
13. **Dùng ctid để theo dõi mọi lần UPDATE**, thay cho audit/version column.
14. **Dùng xmin/xmax làm actor ID hoặc timestamp**.
15. **Dùng ctid cũ ở transaction sau**, khi row có thể đã thay đổi.
16. **Dùng locator mà không row lock trong batch maintenance concurrent**.
17. **Bỏ tableoid khi xử lý nhiều partitions**, gây định vị sai relation.
18. **Dùng ORDER BY ctid làm business order**.
19. **Dùng ctid để thay CDC replica identity**.
20. **SELECT * và nghĩ system columns luôn được trả**, trong khi cần chọn tường minh.
21. **Tưởng tableoid là tên bảng**, dù nó có kiểu OID; dùng cast regclass khi cần hiển thị.
22. **Không phân biệt parent relation và physical child partition**.
23. **Dùng ctid làm message queue locator** qua thời gian.
24. **Không có primary key ở bảng legacy và trì hoãn thiết kế logical identity**.
25. **Không backup/preview trước khi xóa duplicate bằng ctid**.

## 44. Bài tập thực hành có đáp án

Dùng schema jdbc_storage_lab nếu câu hỏi cần SQL. Các câu DELETE/UPDATE chỉ chạy trên database lab; dùng transaction rollback khi chỉ thử.

### Bài 1. ctid là gì?

**Đáp án:** Physical tuple identifier kiểu tid, biểu diễn block number và item/line-pointer offset của một tuple version trong relation.

### Bài 2. tableoid là gì?

**Đáp án:** OID của relation chứa tuple; hữu ích nhận biết partition/inheritance child.

### Bài 3. SELECT * có trả ctid không?

**Đáp án:** Không tự động. Chọn system columns tường minh.

### Bài 4. Đọc ctid của 10 đơn

~~~sql
SELECT order_id, ctid
FROM jdbc_storage_lab.orders
ORDER BY order_id
LIMIT 10;
~~~

**Đáp án:** Trả ctid cho các tuple version hiện visible được chọn.

### Bài 5. Đọc tên bảng từ tableoid

~~~sql
SELECT tableoid, tableoid::regclass
FROM jdbc_storage_lab.orders
LIMIT 5;
~~~

**Đáp án:** Cột đầu là OID; cột thứ hai hiển thị tên relation.

### Bài 6. ctid có phải primary key không?

**Đáp án:** Không. UPDATE/rewrite có thể làm thay đổi và nó không có business semantics.

### Bài 7. ctid có dạng gì?

**Đáp án:** Cặp (block_number, item_offset), ví dụ định dạng minh họa (12,7).

### Bài 8. UPDATE có thể làm ctid đổi không?

**Đáp án:** Có. PostgreSQL tạo tuple version mới theo MVCC.

### Bài 9. HOT update có nghĩa ctid giữ nguyên?

**Đáp án:** Không. HOT có thể giữ index entries và chain trong cùng page nhưng vẫn tạo tuple version mới.

### Bài 10. VACUUM thường có giống VACUUM FULL?

**Đáp án:** Không. VACUUM thường reclaim/reuse dead space; VACUUM FULL rewrite/compact relation.

### Bài 11. CLUSTER có thể làm ctid thay đổi?

**Đáp án:** Có. Nó rewrite relation theo thứ tự index.

### Bài 12. tableoid trong partition query có ích gì?

**Đáp án:** Xác định child partition thực tế chứa row.

### Bài 13. Hai partition có cùng ctid được không?

**Đáp án:** Có. Block/offset numbering độc lập theo relation.

### Bài 14. Locator cho nhiều partition nên gồm gì?

**Đáp án:** Kết hợp tableoid và ctid trong cùng ngữ cảnh vật lý phù hợp.

### Bài 15. Cặp tableoid/ctid có phải khóa lâu dài?

**Đáp án:** Không. ctid đổi theo tuple version/rewrite; tableoid không phải external durable identity.

### Bài 16. Vì sao join hai bảng bằng ctid sai?

**Đáp án:** Hai relation độc lập có thể cùng physical TID nhưng không liên quan nghiệp vụ; dùng foreign key/business key.

### Bài 17. Khi nào dùng ctid trong batch maintenance?

**Đáp án:** Khi chọn và thao tác tuple trong cùng statement/transaction, thường kết hợp row lock; không lưu locator để dùng sau.

### Bài 18. Vì sao dùng tableoid trong batch partitioned?

**Đáp án:** ctid chỉ có phạm vi từng relation; tableoid phân biệt partition chứa tuple.

### Bài 19. FOR UPDATE SKIP LOCKED làm gì?

**Đáp án:** Khóa rows được chọn và bỏ qua rows đang bị lock, phù hợp một số worker queue/batch processing.

### Bài 20. ctid thay optimistic locking được không?

**Đáp án:** Không. Dùng logical primary key kết hợp version column/conditional UPDATE.

### Bài 21. xmin có phải created_by không?

**Đáp án:** Không. Nó là transaction metadata, không phải user identity.

### Bài 22. xmax luôn có nghĩa row đã bị xóa?

**Đáp án:** Không. Nó có semantics nội bộ phức tạp, có thể liên quan lock metadata và visibility.

### Bài 23. tableoid::regclass trả gì?

**Đáp án:** Tên relation dễ đọc theo quy tắc regclass/search_path.

### Bài 24. ctid có thể làm API cursor token không?

**Đáp án:** Không nên. Dùng keyset theo primary/business key ổn định.

### Bài 25. Partition key UPDATE có thể làm gì?

**Đáp án:** Có thể di chuyển row sang partition khác, khiến tableoid và ctid thay đổi.

### Bài 26. SELECT parent inheritance có thể trả rows từ đâu?

**Đáp án:** Parent và các child theo semantics mặc định; dùng ONLY để chỉ đọc relation cha.

### Bài 27. Vì sao ctid không dùng làm logical replication key?

**Đáp án:** Publisher và subscriber có physical layouts riêng; replication identity cần key/replica identity logic.

### Bài 28. Cách xem số rows theo partition?

~~~sql
SELECT tableoid::regclass, count(*)
FROM jdbc_storage_lab.partitioned_orders
GROUP BY tableoid
ORDER BY 1;
~~~

**Đáp án:** Nhóm theo relation OID vật lý của các partition chứa rows.

### Bài 29. Vì sao không hard-code '(0,1)' trong UPDATE?

**Đáp án:** Locator có thể thuộc row khác hoặc đã cũ; phải lấy trong đúng statement/transaction và có logic khóa phù hợp.

### Bài 30. Thiết kế nào phù hợp để phát hiện row đã bị sửa?

**Đáp án:** Logical primary key kết hợp version column hoặc điều kiện optimistic locking, không dùng ctid.

## 45. Checklist sử dụng system columns an toàn

- [ ] Hiểu ctid là TID của tuple version, không phải business ID.
- [ ] Đọc ctid như block/line-pointer pair, không phải byte offset.
- [ ] Chọn system columns tường minh; không kỳ vọng SELECT * trả chúng.
- [ ] Dùng tableoid::regclass để quan sát relation chứa row.
- [ ] Kết hợp tableoid + ctid khi locator đi qua nhiều relation/partitions.
- [ ] Không lưu ctid làm primary key, foreign key hoặc external identifier.
- [ ] Không dùng ctid làm API pagination/checkpoint lâu dài.
- [ ] Không dùng xmin/xmax làm actor/timestamp audit.
- [ ] Hiểu UPDATE tạo tuple version mới và ctid có thể đổi.
- [ ] Phân biệt HOT update với “không có tuple version mới”.
- [ ] Phân biệt VACUUM thường với VACUUM FULL/CLUSTER.
- [ ] Tính tới DDL rewrite và partition movement.
- [ ] Chọn row theo business conditions/order, dùng ctid làm locator tạm khi cần.
- [ ] Nếu thao tác nhiều partitions, giữ tableoid cùng ctid.
- [ ] Dùng row locks/transaction phù hợp cho batch maintenance concurrent.
- [ ] Không lưu locator qua COMMIT để xử lý sau.
- [ ] Dùng primary key/business key cho application logic.
- [ ] Dùng version column cho optimistic concurrency.
- [ ] Dùng replica identity phù hợp cho logical replication/CDC.
- [ ] Preview/backup và xác định survivor criteria trước khi deduplicate.
- [ ] Đo lock/IO và chọn thời điểm bảo trì cho VACUUM FULL/CLUSTER.
- [ ] Không coi ctid là business ordering.
- [ ] Kiểm tra catalog/version khi điều tra storage.
- [ ] Ghi rõ giới hạn physical locator trong code review và tài liệu vận hành.

## 46. Tài liệu PostgreSQL chính thức

Đọc theo major version đang triển khai:

- [System Columns](https://www.postgresql.org/docs/current/ddl-system-columns.html) — tableoid, ctid, xmin, xmax và các system columns.
- [MVCC Introduction](https://www.postgresql.org/docs/current/mvcc-intro.html) — Multi-Version Concurrency Control.
- [Routine Vacuuming](https://www.postgresql.org/docs/current/routine-vacuuming.html) — VACUUM, dead tuples, visibility map và freeze.
- [VACUUM](https://www.postgresql.org/docs/current/sql-vacuum.html) — VACUUM và FULL.
- [CLUSTER](https://www.postgresql.org/docs/current/sql-cluster.html) — rewrite/sắp xếp relation.
- [Table Partitioning](https://www.postgresql.org/docs/current/ddl-partitioning.html) — partitioned tables, routing và partition movement.
- [Inheritance](https://www.postgresql.org/docs/current/ddl-inherit.html) — table inheritance.
- [UPDATE](https://www.postgresql.org/docs/current/sql-update.html) — UPDATE và RETURNING.
- [DELETE](https://www.postgresql.org/docs/current/sql-delete.html) — DELETE và USING/RETURNING.
- [SELECT](https://www.postgresql.org/docs/current/sql-select.html) — locking clauses như FOR UPDATE/SKIP LOCKED.
- [Explicit Locking](https://www.postgresql.org/docs/current/explicit-locking.html) — row locks và concurrency.
- [Transaction Isolation](https://www.postgresql.org/docs/current/transaction-iso.html) — snapshots/MVCC.
- [Data Types: Object Identifier Types](https://www.postgresql.org/docs/current/datatype-oid.html) — OID, regclass và các alias.
- [System Catalog pg_class](https://www.postgresql.org/docs/current/catalog-pg-class.html) — relation metadata.
- [System Catalog pg_namespace](https://www.postgresql.org/docs/current/catalog-pg-namespace.html) — schema metadata.
- [Logical Replication](https://www.postgresql.org/docs/current/logical-replication.html) — logical replication concepts.
- [ALTER TABLE](https://www.postgresql.org/docs/current/sql-altertable.html) — các thao tác có thể thay đổi cấu trúc/storage.
- [EXPLAIN](https://www.postgresql.org/docs/current/sql-explain.html) — quan sát execution plan.

Đường dẫn /current/ trỏ tới tài liệu PostgreSQL hiện hành. Chi tiết storage, HOT, partition movement và một số DDL rewrite có thể phụ thuộc major version; hãy đối chiếu tài liệu của server thực tế.

## 47. Tổng kết

**ctid và tableoid mô tả vị trí vật lý và relation chứa tuple, không định nghĩa danh tính lâu dài của một hàng nghiệp vụ.**

Những điểm cần nhớ:

1. **ctid là TID của một tuple version**, gồm block number và item offset trong relation.
2. **tableoid là OID relation vật lý chứa row**, có thể cast sang regclass để hiển thị tên bảng/partition.
3. **UPDATE tạo tuple version mới**, vì vậy ctid có thể thay đổi; HOT update cũng tạo version mới.
4. **VACUUM thường khác VACUUM FULL**. VACUUM thường reclaim/reuse dead space, còn VACUUM FULL và CLUSTER rewrite relation và có thể đổi vị trí tuple.
5. **Partition/inheritance query cần tableoid để nhận biết child relation**. ctid riêng lẻ không phân biệt tuple ở hai bảng khác nhau.
6. **(tableoid, ctid) hữu ích như physical locator tạm thời**, nhất là khi thao tác cùng statement/transaction.
7. **Không lưu ctid/tableoid làm primary key, foreign key, pagination token, queue message hay replication identity**.
8. **Dùng primary/business key cho identity** và version column cho optimistic locking.
9. **Dùng FOR UPDATE/transaction phù hợp** khi batch maintenance cần khóa các rows được chọn; ctid không thay concurrency control.
10. **xmin/xmax cũng là metadata MVCC**, không phải actor ID, timestamp hay audit history.
11. **Các thao tác storage/rewrite/migration có thể làm locator cũ mất hiệu lực**, vì vậy phải giới hạn phạm vi sử dụng.
12. **Thiết kế schema với logical identity ngay từ đầu** giúp ứng dụng, CDC và vận hành ổn định hơn.

Khi phân biệt rõ **địa chỉ vật lý của tuple** với **danh tính logic của dữ liệu**, bạn có thể tận dụng system columns để chẩn đoán và bảo trì PostgreSQL mà không tạo ra phụ thuộc mong manh vào cách database đang lưu rows.
