# Database In-Memory, column store và khác biệt với buffer cache

## 1. Database In-Memory là gì?

Oracle Database In-Memory là khả năng lưu một bản biểu diễn dữ liệu dạng cột (columnar format) trong bộ nhớ SGA để tăng tốc các truy vấn phân tích. Tính năng này được thiết kế cho workload cần quét nhiều dòng, đọc một số cột, lọc, join và tổng hợp trên tập dữ liệu lớn.

Oracle vẫn lưu dữ liệu bền vững trên datafile theo định dạng row store truyền thống. Database In-Memory bổ sung một bản biểu diễn trong bộ nhớ cho các bảng, partition hoặc cột được đánh dấu `INMEMORY`. Cùng một dữ liệu có thể được truy cập qua:

- **Row format:** các cột của một dòng được lưu cùng nhau trong database block; phù hợp cho OLTP, truy cập theo khóa và DML.
- **Columnar format:** các giá trị của cùng một cột được tổ chức gần nhau trong In-Memory Column Store (IM column store); phù hợp cho scan và phân tích trên nhiều dòng.

Đây là kiến trúc dual-format. Oracle có thể sử dụng row format trong buffer cache và columnar format trong IM column store tùy câu SQL, execution plan và trạng thái population. Hai định dạng cùng đại diện cho dữ liệu của một đối tượng, không phải hai bản dữ liệu nghiệp vụ độc lập mà ứng dụng phải tự đồng bộ.

## 2. Column store hoạt động như thế nào?

### 2.1. Row store và column store

Giả sử bảng `SALES` có các cột `SALE_ID`, `CUSTOMER_ID`, `SALE_DATE`, `REGION_ID`, `AMOUNT`, `STATUS`.

Trong row store, dữ liệu được tổ chức theo dòng:

```text
Row 1: SALE_ID | CUSTOMER_ID | SALE_DATE | REGION_ID | AMOUNT | STATUS
Row 2: SALE_ID | CUSTOMER_ID | SALE_DATE | REGION_ID | AMOUNT | STATUS
Row 3: SALE_ID | CUSTOMER_ID | SALE_DATE | REGION_ID | AMOUNT | STATUS
```

Trong column store, các giá trị của từng cột được tổ chức theo nhóm:

```text
SALE_ID:      101 | 102 | 103 | 104 | ...
CUSTOMER_ID:  501 | 720 | 501 | 881 | ...
SALE_DATE:    ... | ... | ... | ... | ...
REGION_ID:    10  | 20  | 10  | 30  | ...
AMOUNT:       ... | ... | ... | ... | ...
STATUS:       ... | ... | ... | ... | ...
```

Nếu báo cáo chỉ cần `REGION_ID` và `AMOUNT`, column store có thể đọc hai cột cần thiết mà không phải giải mã toàn bộ các cột khác trong mỗi row. Với dữ liệu có nhiều giá trị lặp hoặc miền giá trị nhỏ, biểu diễn cột còn có cơ hội nén tốt.

### 2.2. In-Memory Compression Units

Oracle tổ chức dữ liệu columnar trong các đơn vị nén gọi là In-Memory Compression Units (IMCU). IMCU chứa các cột được nén cho một nhóm dòng. Metadata hỗ trợ ánh xạ và truy cập các giá trị trong IMCU.

Columnar format hỗ trợ các thao tác scan theo cột, lọc dữ liệu, vector processing và các phép tổng hợp. Thay vì xử lý từng row theo cách truyền thống, Oracle có thể xử lý một nhóm giá trị cùng lúc bằng các kỹ thuật vector hóa phù hợp với CPU.

### 2.3. Column store không phải một index

IM column store không phải B-tree index hoặc bitmap index. Nó là một bản biểu diễn dữ liệu trong bộ nhớ được tổ chức theo cột. Optimizer có thể chọn In-Memory scan thay vì table scan/index access khi chi phí và điều kiện truy vấn phù hợp.

Vì vậy:

- Không cần tạo một index cho mỗi cột chỉ để có thể dùng column store.
- Index vẫn có giá trị cho truy vấn OLTP tra cứu một vài dòng theo khóa.
- Column store đặc biệt hữu ích cho scan và tổng hợp trên lượng lớn dòng.
- Đánh dấu bảng `INMEMORY` không bảo đảm mọi truy vấn trên bảng đều dùng IM column store.

## 3. Khác biệt giữa IM column store và buffer cache

### 3.1. Buffer cache

Database buffer cache là vùng SGA lưu các database block được đọc từ datafile. Đây là thành phần cốt lõi của Oracle Database, phục vụ cả đọc và ghi dữ liệu theo row format.

Khi một session đọc một block, Oracle có thể tìm block trong buffer cache. Nếu block chưa có, database đọc block từ storage vào cache. DML sửa block trong buffer cache; block đã thay đổi trở thành dirty buffer và DBWR ghi về datafile theo cơ chế checkpoint/write-back.

Buffer cache tối ưu việc tái sử dụng block và truy cập dữ liệu theo cấu trúc row store. Ví dụ, truy vấn lấy một đơn hàng theo primary key thường cần một hoặc vài block chứa dòng đó; index và buffer cache là cơ chế phù hợp.

### 3.2. In-Memory Column Store

IM column store là một vùng SGA riêng dành cho columnar data của các đối tượng được bật `INMEMORY`. Dữ liệu được populate từ row store vào định dạng cột nén.

Khi optimizer chọn In-Memory access, Oracle đọc các cột cần thiết từ IM column store. Các kỹ thuật như In-Memory pruning, vectorized execution và In-Memory aggregation có thể giảm lượng dữ liệu phải xử lý và tăng tốc analytic query.

IM column store không thay thế buffer cache và cũng không phải nơi lưu bản dữ liệu bền vững duy nhất. Datafile vẫn chứa row format; buffer cache tiếp tục phục vụ các thao tác database thông thường.

### 3.3. So sánh trực tiếp

| Tiêu chí | Buffer cache | In-Memory Column Store |
|---|---|---|
| Định dạng chính | Row-oriented database blocks | Columnar, compressed representation |
| Phạm vi dữ liệu | Block được đọc/ghi theo nhu cầu | Object/partition/column được khai báo `INMEMORY` và đã populate |
| Mục tiêu | Tăng tốc truy cập block nói chung, OLTP và DML | Tăng tốc scan, filter, join và analytic aggregation |
| Dữ liệu bền vững | Block tương ứng được lưu trong datafile | Là bản biểu diễn trong SGA; dữ liệu gốc vẫn ở row store/datafile |
| Cách cấp phát | Buffer cache trong SGA | IM column store pool riêng trong SGA |
| DML | Thực hiện trên row format/buffer cache | Duy trì tính nhất quán của columnar representation theo cơ chế In-Memory |
| Chọn sử dụng | Oracle dùng buffer cache trong hoạt động đọc/ghi bình thường | Optimizer chọn khi query và object đủ điều kiện, dữ liệu đã sẵn sàng |
| Thay thế index? | Không | Không; là định dạng lưu trữ trong memory, không phải index |

### 3.4. Một truy vấn có thể dùng cả hai định dạng

Một ứng dụng có thể có query OLTP tra cứu theo primary key và query báo cáo quét hàng triệu dòng trên cùng bảng. Query OLTP có thể dùng index và row blocks trong buffer cache; query báo cáo có thể dùng columnar data trong IM column store.

Việc chọn đường truy cập do optimizer quyết định theo SQL, statistics, cardinality, object population và cost. DBA không cần chuyển bảng qua lại giữa row store và column store khi đổi workload; hai định dạng có thể cùng tồn tại.

## 4. SGA và tham số INMEMORY_SIZE

### 4.1. IM column store là một pool trong SGA

Oracle dành riêng một vùng nhớ trong SGA cho In-Memory Column Store. Kích thước vùng này được điều khiển bởi tham số `INMEMORY_SIZE`.

Kiểm tra cấu hình:

```sql
SHOW PARAMETER inmemory_size;

SELECT name,
       value,
       isdefault,
       issys_modifiable
FROM v$parameter
WHERE name = 'inmemory_size';
```

Nếu `INMEMORY_SIZE=0`, IM column store không được cấp dung lượng và các object có thể mang thuộc tính `INMEMORY` nhưng không thể populate vào IM area cho tới khi cấu hình được bật phù hợp.

### 4.2. Cấp dung lượng IM column store

Ví dụ cấu hình 4 GB trong SPFILE:

```sql
ALTER SYSTEM SET inmemory_size = 4G SCOPE=SPFILE;
```

Sau đó cần restart instance nếu tham số của release đang dùng là static:

```sql
SHUTDOWN IMMEDIATE;
STARTUP;
```

Thực hiện theo quy trình bảo trì của môi trường thật; không restart production chỉ để thử câu lệnh. `INMEMORY_SIZE` phải nằm trong giới hạn SGA và cấu hình memory tổng thể. Đảm bảo `SGA_MAX_SIZE`/`SGA_TARGET` và headroom cho buffer cache, shared pool, redo buffer cùng các thành phần SGA khác.

Không đặt IM area quá lớn chỉ dựa trên kích thước bảng trên disk. Columnar compression làm dung lượng trong memory khác kích thước segment row store; hãy đo `INMEMORY_SIZE`, `INMEMORY_SIZE` thực dùng và `V$IM_SEGMENTS` sau population.

### 4.3. Xem vùng In-Memory đang dùng

```sql
SELECT *
FROM v$inmemory_area;
```

View này cho biết các vùng pool In-Memory, dung lượng cấp phát và sử dụng theo thông tin phiên bản. Cột cụ thể có thể khác theo release; kiểm tra `DESC V$INMEMORY_AREA` hoặc Oracle Database Reference tương ứng.

## 5. Bật Database In-Memory cho bảng, partition và cột

### 5.1. Bật cho toàn bảng

Ví dụ bật In-Memory cho bảng fact:

```sql
ALTER TABLE sales.fact_sales
  INMEMORY
  MEMCOMPRESS FOR QUERY LOW
  PRIORITY HIGH;
```

Ý nghĩa:

- `INMEMORY`: đánh dấu object đủ điều kiện được populate vào IM column store.
- `MEMCOMPRESS FOR QUERY LOW`: chọn mức nén hướng tới hiệu năng truy vấn với mức nén thấp hơn các chế độ ưu tiên capacity.
- `PRIORITY HIGH`: yêu cầu ưu tiên populate object cao hơn các object có priority thấp.

Đây là thuộc tính của object. Lệnh thành công không đồng nghĩa toàn bộ dữ liệu đã được populate ngay lập tức; cần kiểm tra trạng thái population.

### 5.2. Tắt In-Memory cho bảng

```sql
ALTER TABLE sales.fact_sales NO INMEMORY;
```

Thao tác này bỏ thuộc tính In-Memory của object. Nó không xóa bảng hoặc dữ liệu trong datafile. Các truy vấn tiếp theo sẽ dùng các đường truy cập row store/index/buffer cache phù hợp.

### 5.3. Chỉ đưa một số cột vào IM column store

Với bảng rộng, query có thể chỉ dùng một số cột. Oracle hỗ trợ khai báo In-Memory ở mức cột trong các release có hỗ trợ:

```sql
ALTER TABLE sales.fact_sales
  INMEMORY (
    sale_date,
    product_id,
    customer_id,
    region_id,
    amount
  )
  MEMCOMPRESS FOR QUERY LOW;
```

Việc chọn cột nên dựa trên query workload. Cột không cần cho báo cáo có thể không cần chiếm chỗ trong IM column store. Kiểm tra cú pháp và khả năng column-level In-Memory trong Oracle release đang triển khai.

### 5.4. Chọn partition thay vì toàn bảng

Với bảng partition lớn, có thể bật In-Memory cho các partition thường xuyên được truy vấn:

```sql
ALTER TABLE sales.fact_sales
  MODIFY PARTITION p2026q1
  INMEMORY MEMCOMPRESS FOR QUERY LOW PRIORITY HIGH;
```

Các partition lịch sử ít truy cập có thể để row store, trong khi partition gần đây được populate vào IM column store. Cách này giúp quản lý dung lượng memory theo vùng dữ liệu nóng.

### 5.5. Kiểm tra thuộc tính object

```sql
SELECT owner,
       table_name,
       inmemory,
       inmemory_priority,
       inmemory_compression,
       inmemory_distribute,
       inmemory_duplicate
FROM dba_tables
WHERE owner = 'SALES'
  AND table_name = 'FACT_SALES';
```

Với partition:

```sql
SELECT table_owner,
       table_name,
       partition_name,
       inmemory,
       inmemory_priority,
       inmemory_compression
FROM dba_tab_partitions
WHERE table_owner = 'SALES'
  AND table_name = 'FACT_SALES'
ORDER BY partition_position;
```

Các cột metadata và khả năng hiển thị phụ thuộc release và quyền data dictionary. Có thể dùng `USER_TABLES`, `ALL_TABLES` hoặc các view partition tương ứng nếu không có quyền DBA.

## 6. Compression và population priority

### 6.1. MEMCOMPRESS FOR QUERY

Các mức `MEMCOMPRESS FOR QUERY LOW` và `MEMCOMPRESS FOR QUERY HIGH` hướng tới tăng tốc truy vấn. Mức nén cao hơn thường giảm memory footprint tốt hơn nhưng có thể tăng chi phí CPU giải nén/xử lý tùy workload.

### 6.2. MEMCOMPRESS FOR CAPACITY

`MEMCOMPRESS FOR CAPACITY LOW` và `MEMCOMPRESS FOR CAPACITY HIGH` ưu tiên tiết kiệm dung lượng IM area. Chúng phù hợp khi cần chứa nhiều dữ liệu hơn trong một vùng memory hữu hạn, nhưng cần benchmark vì mức nén cao hơn có thể ảnh hưởng CPU và thời gian truy vấn.

Ví dụ:

```sql
ALTER TABLE sales.fact_sales
  INMEMORY MEMCOMPRESS FOR CAPACITY HIGH
  PRIORITY MEDIUM;
```

Không có một mức compression tối ưu cho mọi bảng. Dữ liệu có giá trị lặp, kiểu dữ liệu và pattern query khác nhau sẽ cho tỷ lệ nén và hiệu năng khác nhau.

### 6.3. PRIORITY

`PRIORITY` điều khiển thứ tự ưu tiên population của object. Các mức thường gặp gồm `NONE`, `LOW`, `MEDIUM`, `HIGH` và `CRITICAL`.

- `NONE`: object thường được populate khi được truy cập theo chính sách population của Oracle.
- Các mức priority cao hơn: object được ưu tiên population sớm hơn khi database mở/IM area sẵn sàng, theo thứ tự ưu tiên.

Priority không bảo đảm object sẽ luôn nằm trong memory nếu IM area không đủ hoặc có điều kiện vận hành khác. Cần kiểm tra population status và dung lượng thực tế.

### 6.4. Population không nhất thiết hoàn tất ngay sau ALTER

Khi bật `INMEMORY`, Oracle cần đọc row store và tạo columnar representation trong IM area. Quá trình này có thể diễn ra nền hoặc khi object được truy cập tùy priority/cấu hình. Trong giai đoạn population chưa hoàn tất, query vẫn có thể dùng đường truy cập khác.

Với báo cáo cần hiệu năng ổn định, cần xác nhận object/partition đã populate trước thời điểm workload chạy. Không chỉ kiểm tra `DBA_TABLES.INMEMORY='ENABLED'`; thuộc tính bật và dữ liệu đã nằm trong IM area là hai trạng thái khác nhau.

## 7. Tính nhất quán khi DML thay đổi dữ liệu

### 7.1. Row format vẫn là nền tảng cho DML

Oracle tiếp tục thực hiện DML trên row format và quản lý thay đổi bằng cơ chế transaction/undo/redo thông thường. IM column store được duy trì để các truy vấn analytic có thể đọc bản columnar với tính nhất quán giao dịch.

Khi dữ liệu thay đổi, Oracle theo dõi thay đổi liên quan tới In-Memory representation bằng metadata/journal và các cơ chế duy trì phù hợp. Truy vấn phải nhìn thấy dữ liệu nhất quán theo transaction semantics; ứng dụng không cần tự ghi đồng thời vào buffer cache và IM column store.

### 7.2. DML không yêu cầu ứng dụng đồng bộ hai định dạng

Ứng dụng chỉ chạy `INSERT`, `UPDATE`, `DELETE` như bình thường. Oracle quản lý row store, undo/redo và tính nhất quán của columnar representation. Không viết hai câu SQL để cập nhật “row copy” và “column copy”; IM column store không phải bảng phụ do ứng dụng sở hữu.

### 7.3. DML-heavy workload có thể không phù hợp

Database In-Memory chủ yếu tối ưu analytic read. Với bảng có tốc độ DML rất cao, chi phí duy trì columnar representation, memory và population có thể không đem lại lợi ích tương xứng. Cần đo tỷ lệ read/write, tốc độ thay đổi, mức nén và query latency trước khi bật In-Memory cho bảng OLTP nóng.

## 8. Optimizer sử dụng column store như thế nào?

### 8.1. Cost-based optimizer quyết định

Khi query tham chiếu object có thuộc tính `INMEMORY`, optimizer xem xét khả năng dùng In-Memory scan cùng với các đường truy cập khác. Việc chọn phụ thuộc:

- Object/partition đã được populate hay chưa.
- Các cột cần thiết có sẵn trong IM column store không.
- Predicate, join, aggregation và số dòng ước lượng.
- Statistics và cardinality estimate.
- Chi phí CPU, memory và I/O.
- Tính tương thích của query với các phép xử lý In-Memory.

Do đó, `INMEMORY` là khả năng cho optimizer lựa chọn, không phải cam kết ép mọi SQL đọc từ column store.

### 8.2. In-Memory pruning

Column store có thể loại bỏ các vùng dữ liệu không cần đọc dựa trên metadata về giá trị trong IMCU. Nếu predicate chỉ cần một khoảng giá trị hoặc một tập dữ liệu nhỏ, Oracle có thể bỏ qua IMCU không thể chứa kết quả.

Điều này tương tự mục tiêu partition pruning ở mức khác: partition pruning bỏ qua partition không liên quan; In-Memory pruning bỏ qua vùng columnar không liên quan. Hai cơ chế có thể bổ trợ nhau.

### 8.3. Vectorized execution

Columnar representation cho phép Oracle xử lý một nhóm giá trị cùng lúc thay vì giải mã và xử lý từng row theo cách truyền thống. Vector processing có thể tận dụng khả năng SIMD của CPU cho các phép lọc và tính toán phù hợp.

### 8.4. In-Memory Aggregation và vector group-by

Với query tổng hợp trên dimension/fact, Oracle có thể sử dụng In-Memory Aggregation hoặc vector group-by để giảm lượng dữ liệu trung gian và tăng tốc aggregation. Tính năng cụ thể phụ thuộc phiên bản và dạng SQL; không phải mọi `GROUP BY` đều được biến thành vector group-by.

## 9. Kiểm tra population và dung lượng IM column store

### 9.1. Xem các segment đã populate

```sql
SELECT owner,
       segment_name,
       partition_name,
       segment_type,
       bytes,
       inmemory_size,
       bytes_not_populated,
       inmemory_priority,
       inmemory_compression
FROM v$im_segments
ORDER BY inmemory_size DESC;
```

`V$IM_SEGMENTS` cho biết các segment có biểu diễn In-Memory và dung lượng tương ứng. `BYTES` là kích thước row-store segment; `INMEMORY_SIZE` là dung lượng columnar đã sử dụng; `BYTES_NOT_POPULATED` giúp nhận biết phần chưa được populate. Các cột chính xác cần được xác nhận theo release.

### 9.2. Xem các cột được cấu hình In-Memory

```sql
SELECT owner,
       table_name,
       column_name,
       inmemory_compression
FROM dba_inmemory_column_level
WHERE owner = 'SALES'
  AND table_name = 'FACT_SALES'
ORDER BY column_name;
```

View `DBA_INMEMORY_COLUMN_LEVEL` có thể được dùng để kiểm tra cấu hình ở cấp cột trong các release hỗ trợ. Nếu view không tồn tại trong phiên bản đang dùng, kiểm tra các view dictionary In-Memory tương ứng của release đó.

### 9.3. Xem memory area

```sql
SELECT pool,
       alloc_bytes,
       used_bytes
FROM v$inmemory_area;
```

So sánh dung lượng được cấp và đang sử dụng với `INMEMORY_SIZE`. Nếu object chưa populate, kiểm tra priority, IM area còn đủ hay không, object có được hỗ trợ và có lỗi population trong alert/trace log không.

## 10. Xác nhận execution plan có dùng In-Memory

### 10.1. Xem execution plan

Chạy query với statistics phù hợp trong môi trường kiểm thử:

```sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       region_id,
       SUM(amount) AS total_amount
FROM sales.fact_sales
WHERE sale_date >= DATE '2026-01-01'
GROUP BY region_id;
```

Sau đó xem plan của cursor:

```sql
SELECT *
FROM TABLE(
  DBMS_XPLAN.DISPLAY_CURSOR(
    NULL,
    NULL,
    'ALLSTATS LAST +MEMSTATS'
  )
);
```

Tùy phiên bản và query, operation có thể hiển thị dạng `TABLE ACCESS INMEMORY FULL` hoặc các operation liên quan In-Memory/vector processing. Không dựa vào một tên operation duy nhất; đọc toàn bộ plan, predicate, row estimates và runtime statistics.

### 10.2. So sánh với buffer-cache/row-store access

Thử cùng query trước và sau khi bật In-Memory trên một môi trường kiểm thử có dữ liệu đại diện. Ghi nhận:

- Elapsed time và CPU time.
- Logical reads và physical reads.
- Số dòng đầu vào/đầu ra tại từng operation.
- TEMP usage và memory usage.
- Plan operation và In-Memory scan metrics nếu có.

Đừng so sánh lần chạy đầu tiên khi IM population chưa xong với lần chạy sau khi đã populate rồi kết luận chỉ dựa vào thời gian. Cần tách chi phí population khỏi thời gian truy vấn ổn định.

### 10.3. Không ép dùng In-Memory chỉ để thấy operation

Nếu optimizer chọn index access hoặc buffer cache scan vì chi phí thấp hơn, điều đó có thể là lựa chọn đúng. Mục tiêu là hiệu năng và tài nguyên tổng thể, không phải làm cho plan luôn xuất hiện operation `INMEMORY`.

## 11. Thiết kế workload phù hợp

### 11.1. Workload thường hưởng lợi

- Data warehouse và star schema.
- Báo cáo tổng hợp trên fact table lớn.
- Truy vấn đọc một số cột trên bảng rất rộng.
- Phân tích ad-hoc với nhiều filter/group-by.
- Workload hỗn hợp OLTP và analytic cần cùng truy cập dữ liệu hiện tại.

### 11.2. Workload ít hưởng lợi

- Truy vấn chỉ lấy một dòng theo primary key.
- Query trả rất ít dòng và đã có index tốt.
- Bảng nhỏ đã nằm hoàn toàn trong buffer cache và không có bottleneck đáng kể.
- Workload ghi liên tục, ít truy vấn phân tích.
- Bảng/partition không được truy cập hoặc không có đủ memory để populate.

### 11.3. Chọn bảng/partition/cột theo workload

Không nên đánh dấu toàn bộ schema `INMEMORY` một cách mặc định. Hãy dùng SQL workload, AWR/ASH hoặc công cụ theo dõi phù hợp với license để xác định các query tốn thời gian và các bảng/partition/cột thường xuyên được quét. Sau đó chọn tập dữ liệu có lợi ích cao nhất trên mỗi byte IM area.

Nếu báo cáo chỉ dùng 5 cột trong bảng 80 cột, column-level In-Memory có thể giảm memory footprint. Nếu chỉ phân tích dữ liệu 3 tháng gần nhất, partition-level In-Memory có thể hiệu quả hơn việc populate toàn bộ lịch sử.

## 12. Oracle RAC và phân phối In-Memory data

Trong RAC, mỗi instance có SGA và IM column store riêng. Cần xác định dữ liệu columnar được phân phối hoặc duplicate giữa các instance như thế nào để cân bằng memory, scan workload và tính sẵn sàng.

Oracle cung cấp các tùy chọn phân phối In-Memory như `DISTRIBUTE` và `DUPLICATE` trong các kiến trúc/release được hỗ trợ. Tùy chọn cụ thể có thể phân bố dữ liệu theo partition hoặc rowid range, hoặc duy trì bản duplicate trên các instance.

Ví dụ dạng cấu hình minh họa:

```sql
ALTER TABLE sales.fact_sales
  INMEMORY
  MEMCOMPRESS FOR QUERY LOW
  DISTRIBUTE BY AUTO;
```

Các tùy chọn `DISTRIBUTE`/`DUPLICATE` phụ thuộc phiên bản, cấu hình RAC và loại object. Không áp dụng câu lệnh ví dụ mà chưa kiểm tra cú pháp/reference của release. Cần đo phân bố IM population, memory utilization và query execution trên từng instance.

## 13. Các lưu ý về CDB/PDB và vận hành

Trong môi trường multitenant, thuộc tính In-Memory có thể được cấu hình trên object thuộc PDB, trong khi IM column store là tài nguyên memory của instance/CDB theo kiến trúc triển khai. Vì vậy, capacity planning phải tính tổng nhu cầu của các PDB trên instance, không chỉ từng PDB riêng lẻ.

Kiểm tra container và thuộc tính object từ đúng PDB hoặc từ root bằng các view CDB tương ứng. Trong RAC, mỗi instance có IM area riêng; trong CDB, resource allocation và workload từ nhiều PDB có thể cạnh tranh dung lượng.

Khi restart instance, columnar data cần được populate lại theo priority và cơ chế population của release. Cần tính thời gian warm-up trước khi chạy batch/report SLA quan trọng.

## 14. Giấy phép và khả năng theo phiên bản

Database In-Memory là tính năng có điều kiện hỗ trợ và cấp phép phụ thuộc Oracle Database release, edition, cloud service và hợp đồng. Không suy luận quyền sử dụng chỉ từ việc tham số `INMEMORY_SIZE` tồn tại hoặc câu lệnh `ALTER TABLE ... INMEMORY` được parse.

Trước khi bật trên production, kiểm tra Oracle Database Licensing Information đúng phiên bản và offering đang sử dụng; xác nhận option/feature được cấp phép, đặc biệt với Enterprise Edition on-premises và dịch vụ cloud/BYOL. Cũng cần kiểm tra feature availability theo release/RU vì các khả năng In-Memory được bổ sung theo từng phiên bản.

Không dùng AWR/ASH hoặc các management pack để đánh giá workload nếu tổ chức chưa xác nhận entitlement tương ứng. Chọn nguồn telemetry được cấp phép và phù hợp với môi trường.

## 15. Quy trình triển khai Database In-Memory

1. Xác định workload phân tích có bottleneck ở scan, join, filter hay aggregation; không bắt đầu bằng việc bật In-Memory cho mọi bảng.
2. Xác nhận Oracle release/RU, edition, offering và license cho Database In-Memory.
3. Kiểm tra SGA, `INMEMORY_SIZE`, headroom cho buffer cache/shared pool và cấu hình memory tổng thể.
4. Chọn bảng, partition hoặc cột dựa trên workload và dung lượng dự kiến sau compression.
5. Bật `INMEMORY` với compression/priority phù hợp trong môi trường thử nghiệm.
6. Chờ và xác nhận population bằng `V$IM_SEGMENTS`, `V$INMEMORY_AREA` và dictionary attributes.
7. Chạy query đại diện, xem `DBMS_XPLAN.DISPLAY_CURSOR` và runtime statistics để xác nhận optimizer thực sự sử dụng column store khi phù hợp.
8. Đo elapsed/CPU, I/O, TEMP, memory, population time và concurrency; so sánh với baseline row-store.
9. Kiểm thử DML đồng thời, restart/population warm-up, workload OLTP và nhiều PDB/RAC instance nếu có.
10. Mở rộng dần tập object; theo dõi memory pressure và loại bỏ object ít giá trị nếu IM area thiếu.

## 16. Các lỗi triển khai thường gặp

### 16.1. Bật INMEMORY nhưng không có dữ liệu được populate

Nguyên nhân có thể là `INMEMORY_SIZE=0`, IM area không đủ, priority chưa kích hoạt population hoặc object chưa được truy cập. Kiểm tra tham số, memory area và `V$IM_SEGMENTS` thay vì chỉ nhìn thuộc tính `DBA_TABLES.INMEMORY`.

### 16.2. Tưởng IM column store thay thế buffer cache

Buffer cache vẫn cần cho row store, DML và nhiều truy vấn OLTP. Giảm buffer cache quá mức để dành memory cho IM area có thể làm các workload khác chậm hơn. Sizing SGA phải cân bằng cả hai.

### 16.3. Query không dùng In-Memory dù object đã bật

Optimizer có thể chọn index/buffer cache access vì chi phí thấp hơn; object/partition có thể chưa populate; query có thể tham chiếu cột không có trong IM column store hoặc có dạng không phù hợp. Kiểm tra plan, population và statistics.

### 16.4. Chọn compression quá mạnh

Mức nén cao giảm memory nhưng có thể tăng CPU/ảnh hưởng query. Benchmark theo dữ liệu thật, không chỉ dựa vào tỷ lệ nén lý thuyết.

### 16.5. Populate quá nhiều dữ liệu

Nếu chọn toàn bộ bảng lịch sử, IM area có thể không đủ. Object có priority thấp có thể chưa được populate hoặc bị cạnh tranh dung lượng. Chọn partition/cột có giá trị cao hơn trên mỗi byte memory.

### 16.6. Không tính thời gian warm-up sau restart

Sau restart, columnar data cần được populate theo cơ chế của Oracle. Nếu report chạy ngay lập tức, có thể chưa đạt hiệu năng mong đợi. Đưa population readiness vào quy trình khởi động và kiểm tra SLA.

## 17. Nguyên tắc cần ghi nhớ

- Database In-Memory bổ sung columnar representation trong SGA; dữ liệu bền vững vẫn ở row store trên datafile.
- Buffer cache lưu database blocks theo row format và phục vụ đọc/ghi thông thường; IM column store phục vụ scan/analytic workload.
- Hai định dạng cùng tồn tại trong kiến trúc dual-format; IM column store không thay thế buffer cache hoặc index.
- Chỉ object/partition/cột được cấu hình `INMEMORY` mới là ứng viên population; thuộc tính bật không đồng nghĩa population hoàn tất.
- `INMEMORY_SIZE` điều khiển dung lượng IM area; phải cân bằng với buffer cache/shared pool và SGA tổng thể.
- Compression và priority ảnh hưởng memory footprint, CPU và thời điểm population; cần benchmark.
- Oracle duy trì tính nhất quán giữa DML row format và truy vấn columnar; ứng dụng không tự đồng bộ hai bản biểu diễn.
- Optimizer quyết định có dùng In-Memory hay không; xác nhận bằng execution plan và runtime metrics.
- Chọn dữ liệu phân tích có giá trị cao, cân nhắc column-level/partition-level In-Memory và workload RAC/CDB.
- Kiểm tra feature availability và licensing theo đúng release, edition, cloud offering và hợp đồng trước khi triển khai.

## Tài liệu Oracle tham khảo

- [Oracle Database 19c Database In-Memory Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/inmem/)
- [Oracle Database 19c Database In-Memory Guide — In-Memory Column Store](https://docs.oracle.com/en/database/oracle/oracle-database/19/inmem/introduction-to-database-in-memory.html)
- [Oracle Database 19c Database Reference — INMEMORY_SIZE](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/INMEMORY_SIZE.html)
- [Oracle Database 19c Database Reference — V$IM_SEGMENTS](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-IM_SEGMENTS.html)
- [Oracle Database 19c Database Reference — V$INMEMORY_AREA](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-INMEMORY_AREA.html)
- [Oracle Database 19c SQL Language Reference — ALTER TABLE](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/ALTER-TABLE.html)
- [Oracle Database 19c Licensing Information](https://docs.oracle.com/en/database/oracle/oracle-database/19/dblic/)
