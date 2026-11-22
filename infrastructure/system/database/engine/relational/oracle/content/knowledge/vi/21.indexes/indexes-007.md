## 4. Bitmap index trong truy vấn phân tích

### 4.1. Lọc theo một thuộc tính

```sql
SELECT COUNT(*)
FROM sales
WHERE status = 'PAID';
```

Nếu index và thống kê phù hợp, Oracle có thể dùng bitmap index trên STATUS để tìm ROWID của hàng PAID. Nhưng nếu PAID chiếm phần lớn bảng, full scan có thể hiệu quả hơn. Optimizer quyết định dựa trên cost estimate, không phải cứ có bitmap index là bắt buộc dùng.

### 4.2. Kết hợp nhiều thuộc tính

```sql
SELECT
    region_code,
    channel,
    SUM(amount) AS total_amount,
    COUNT(*) AS transaction_count
FROM sales
WHERE region_code IN ('NORTH', 'SOUTH')
  AND channel = 'WEB'
  AND status = 'PAID'
GROUP BY region_code, channel;
```

Nếu có bitmap index phù hợp trên REGION_CODE, CHANNEL và STATUS, Oracle có thể kết hợp bitmap để xác định tập hàng trước khi đọc AMOUNT và thực hiện aggregate.

### 4.3. Predicate OR

```sql
SELECT COUNT(*)
FROM sales
WHERE status = 'PAID'
   OR status = 'REFUNDED';
```

Oracle có thể kết hợp các bitmap bằng phép OR. Một điều kiện IN ('PAID', 'REFUNDED') cũng có thể được xử lý theo cách tương tự về logic. Plan cụ thể phụ thuộc optimizer và thống kê.

### 4.4. Kết hợp bitmap với B-tree

Một truy vấn có thể có predicate trên cột low-cardinality và predicate trên khóa high-cardinality. Oracle có thể sử dụng nhiều loại access path hoặc kết hợp bitmap với ROWID từ index khác tùy plan. Không cần chuyển tất cả index của bảng sang bitmap; bảng kho dữ liệu thường có thể dùng B-tree cho khóa truy cập cụ thể và bitmap cho thuộc tính phân loại.

### 4.5. Bitmap operations trong execution plan

Khi xem plan, có thể gặp operation như:

| Operation | Ý nghĩa khái quát |
| --- | --- |
| BITMAP INDEX SINGLE VALUE | Lấy bitmap cho một giá trị index |
| BITMAP INDEX RANGE SCAN | Lấy bitmap cho một phạm vi giá trị |
| BITMAP AND | Kết hợp bitmap bằng phép AND |
| BITMAP OR | Kết hợp bitmap bằng phép OR |
| BITMAP MERGE | Hợp nhất các bitmap |
| BITMAP CONVERSION TO ROWIDS | Chuyển bitmap phù hợp thành ROWID |
| TABLE ACCESS BY INDEX ROWID | Truy cập hàng bảng theo ROWID |

Tên operation và plan thực tế thay đổi theo phiên bản Oracle, predicate, partitioning và optimizer transformations. Hãy đọc toàn bộ plan, cardinality estimate và số hàng thực tế, không kết luận chỉ từ một dòng operation.

## 5. Vì sao bitmap index phù hợp với data warehouse?

### 5.1. Workload đọc nhiều, ghi theo lô

Kho dữ liệu thường có mô hình:

- Dữ liệu được nạp theo batch hoặc ETL.
- Truy vấn đọc hàng triệu dòng để tổng hợp.
- Người dùng phân tích theo nhiều chiều: thời gian, vùng, kênh, loại sản phẩm, trạng thái.
- Các dimension ít thay đổi hơn so với giao dịch OLTP.

Bitmap index có thể giúp lọc dữ liệu theo nhiều thuộc tính phân loại với chi phí lưu trữ hợp lý, đặc biệt khi giá trị cột lặp lại nhiều lần.

### 5.2. Ad hoc query và tổ hợp predicate

Người dùng BI có thể chọn bộ lọc tùy ý:

- Vùng NORTH hoặc EAST.
- Kênh WEB.
- Trạng thái PAID.
- Loại khách hàng BUSINESS.
- Nhóm sản phẩm ELECTRONICS.

Không thể tạo một B-tree composite index cho mọi tổ hợp cột mà người dùng có thể chọn. Các bitmap index riêng có thể được kết hợp linh hoạt theo predicate của từng truy vấn.

### 5.3. Bitmap join index là một chủ đề liên quan

Oracle còn có bitmap join index, cho phép tạo bitmap index trên cột của dimension table theo quan hệ join với fact table. Ví dụ khái niệm:

```sql
CREATE BITMAP INDEX ix_sales_region_join_bm
ON sales(region.region_name)
FROM sales, region
WHERE sales.region_id = region.region_id;
```

Đây là loại index chuyên biệt cho star schema và có cú pháp/ràng buộc riêng; ví dụ chỉ minh họa ý tưởng. Không nhầm bitmap index thông thường trên cột của một bảng với bitmap join index. Bài này tập trung vào bitmap index thông thường; bitmap join index cần được thiết kế và kiểm tra theo Oracle Data Warehousing Guide của phiên bản đang sử dụng.

### 5.4. Bitmap không làm truy vấn luôn nhanh hơn

Một truy vấn cần đọc 80% bảng có thể chạy nhanh bằng full table scan, đặc biệt khi đọc tuần tự và parallel query. Bitmap index không loại bỏ chi phí đọc dữ liệu cần thiết cho SELECT list, GROUP BY hoặc phép tính.

Hãy so sánh:

- Full table scan.
- Bitmap index access + table access by ROWID.
- B-tree access.
- Partition pruning nếu bảng được partition.
- Parallel execution nếu workload cho phép.

Mục tiêu là tổng chi phí workload và SLA, không phải làm mọi truy vấn đều dùng index.

## 6. Bitmap index và B-tree index

Hai loại index có cấu trúc và đặc điểm workload khác nhau. Không có loại nào luôn tốt hơn loại còn lại.

| Tiêu chí | Bitmap index | B-tree index |
| --- | --- | --- |
| Cấu trúc khái niệm | Bitmap cho từng giá trị, ánh xạ tới nhiều ROWID | Cây cân bằng gồm các key và ROWID |
| Cột thường phù hợp | Cardinality thấp hoặc các chiều phân loại trong DW | Cardinality cao, khóa định danh, truy vấn điểm/phạm vi |
| Kết hợp nhiều điều kiện | Mạnh với bitmap AND/OR/NOT | Có thể dùng composite index hoặc nhiều access path; cách kết hợp khác |
| Truy vấn tổng hợp | Thường hữu ích cho ad hoc filtering trên bảng lớn | Hữu ích khi predicate chọn lọc tốt hoặc truy cập theo key |
| DML đồng thời | Có thể contention do bitmap entry bao phủ nhiều hàng | Thường phù hợp hơn với cập nhật OLTP thường xuyên |
| NULL | Có thể lưu bitmap cho NULL | B-tree không lưu entry nếu toàn bộ key columns đều NULL |
| Unique constraint | Không dùng làm unique index | Có thể là unique index và thực thi PK/UNIQUE |
| Dung lượng | Có thể nén tốt khi giá trị lặp lại nhiều | Phụ thuộc key, ROWID và phân bố dữ liệu |

### 6.1. Ví dụ chọn index theo workload

Một bảng FACT_SALES có 200 triệu hàng:

- STATUS có 4 giá trị, được dùng trong báo cáo lọc kết hợp nhiều dimension và gần như không cập nhật từng hàng: bitmap là ứng viên.
- CHANNEL có 3 giá trị, chỉ thay đổi trong ETL hàng đêm: bitmap có thể phù hợp.
- CUSTOMER_ID có hàng triệu giá trị, ứng dụng tìm giao dịch của một khách hàng cụ thể: B-tree thường phù hợp hơn.
- SALE_ID là khóa duy nhất: dùng primary key/unique B-tree, không dùng bitmap.

Nếu cùng bảng FACT_SALES lại nhận UPDATE từng giao dịch từ hàng trăm session suốt ngày, cần đánh giá lại bitmap index trên các cột bị cập nhật. Workload thực tế quan trọng hơn nhãn “fact table”.

### 6.2. Bitmap index không phải index ghép duy nhất cho mọi truy vấn

Một bitmap index riêng trên REGION, một trên CHANNEL và một trên STATUS có thể kết hợp cho nhiều tổ hợp predicate. Một bitmap index ghép (REGION, CHANNEL, STATUS) có thể phù hợp với một số truy vấn cụ thể nhưng kém linh hoạt hơn khi người dùng chỉ lọc theo cột không đứng đầu hoặc có tổ hợp khác.

Quyết định cần dựa vào truy vấn phổ biến, kích thước index, thống kê và chi phí ETL. Không tạo index chỉ vì cột có ít giá trị distinct.

## 7. Tranh chấp cập nhật: nhược điểm quan trọng của bitmap

### 7.1. Vì sao cập nhật một hàng có thể ảnh hưởng bitmap của nhiều hàng?

Trong B-tree, entry thường ánh xạ một key tới một hoặc nhiều ROWID; thao tác DML cập nhật cấu trúc index liên quan tới hàng được sửa. Với bitmap index, một bitmap entry đại diện cho tập nhiều ROWID có cùng giá trị khóa. Khi giá trị một hàng thay đổi, Oracle phải sửa các bitmap tương ứng với giá trị cũ và giá trị mới.

Do bitmap entry bao phủ nhiều hàng, khóa đồng thời có thể được giữ ở phạm vi bitmap entry hoặc vùng ROWID liên quan, rộng hơn một hàng logic. Vì vậy hai transaction sửa các hàng bảng khác nhau vẫn có thể chờ nhau nếu cùng cần thay đổi các bitmap entry giao nhau.

Đây là lý do bitmap index có thể làm giảm khả năng ghi đồng thời trong hệ thống OLTP. Không có nghĩa mọi UPDATE trên bảng có bitmap index đều khóa toàn bảng; mức độ tranh chấp phụ thuộc index, giá trị cũ/mới, vị trí ROWID, thời gian transaction và pattern DML.

### 7.2. Minh họa hai session

Giả sử bitmap index trên STATUS và nhiều hàng đang có STATUS = NEW. Hai session cập nhật hai SALE_ID khác nhau nhưng đều chuyển NEW sang PAID:

```text
Session A                              Session B
---------                              ---------
UPDATE sale_id = 101: NEW -> PAID      UPDATE sale_id = 202: NEW -> PAID
Sửa bitmap NEW và PAID                 Cần sửa bitmap NEW và PAID
Giữ khóa bitmap liên quan              Có thể phải chờ khóa bitmap
COMMIT                                 Tiếp tục khi khóa được giải phóng
```

Hai SALE_ID khác nhau không đồng nghĩa bitmap entry khác nhau. Cả hai hàng có thể thuộc cùng bitmap cho NEW và cùng bitmap cho PAID. Mức chờ thực tế tùy cấu trúc index và vùng bitmap được cập nhật; ví dụ này giải thích cơ chế chứ không bảo đảm hai session nào cũng luôn block trong mọi dataset.

### 7.3. INSERT, UPDATE và DELETE đều có chi phí

- INSERT cần thêm ROWID mới vào bitmap tương ứng với giá trị cột.
- UPDATE đổi giá trị cần xóa bit ở bitmap cũ và thêm bit ở bitmap mới.
- DELETE cần loại ROWID khỏi bitmap liên quan.
- UPDATE một cột không được index vẫn có thể phát sinh công việc index nếu ROWID/định danh hàng làm bitmap entry cần thay đổi do thao tác khác, nhưng trọng tâm contention là các DML tác động lên cột/bitmap index.

Các thao tác thay đổi hàng loạt có thể gây nhiều công việc bảo trì index. Với data warehouse, thường thiết kế quy trình nạp theo batch và bảo trì index theo cửa sổ ETL.

### 7.4. Cập nhật cột không nằm trong bitmap index

Nếu UPDATE chỉ đổi AMOUNT và không thay đổi cột được bitmap index, bitmap index đó thường không cần thay đổi key bitmap cho giá trị cột. Tuy nhiên, DML vẫn có thể có chi phí từ các index khác, trigger, constraint, row movement hoặc thao tác partition. Không kết luận mọi UPDATE trên bảng có bitmap index đều gây contention bitmap như nhau.

### 7.5. Transaction dài làm tăng thời gian chờ

Nếu transaction cập nhật một hàng rồi giữ transaction mở trong lúc gọi dịch vụ ngoài hoặc xử lý nhiều công việc khác, khóa liên quan có thể được giữ lâu hơn. Các session khác cần cập nhật bitmap entry giao nhau phải chờ lâu hơn.

Giữ transaction ngắn, commit theo ranh giới hợp lý và tránh chờ I/O ngoài database trong khi đang giữ khóa. Với batch lớn, xác định chunk size và cách phối hợp writer để hạn chế thời gian tranh chấp.

## 8. Vì sao bitmap index không phù hợp OLTP nhiều cập nhật?

OLTP thường có các đặc điểm:

- Nhiều session ghi đồng thời.
- UPDATE/INSERT/DELETE từng hàng diễn ra liên tục.
- Transaction cần độ trễ thấp và thời gian khóa ngắn.
- Cột trạng thái hoặc phân loại có thể thay đổi thường xuyên.

Nếu bitmap index đặt trên cột được cập nhật nhiều, một số lượng lớn session có thể tranh chấp các bitmap entry. Điều này có thể làm tăng enqueue/lock waits, giảm throughput và tạo đuôi độ trễ lớn.

### 8.1. Khi nào nên tránh bitmap index?

- Bảng giao dịch có nhiều writer đồng thời.
- Cột index thường xuyên thay đổi trạng thái.
- Hệ thống cần cập nhật từng hàng với latency thấp.
- Các transaction thường giữ khóa lâu.
- Index được tạo trên cột low-cardinality chỉ vì thấy ít distinct nhưng không có workload phân tích chứng minh lợi ích.

### 8.2. Khi nào vẫn có thể cân nhắc?

- Bảng gần như chỉ đọc.
- Dữ liệu được nạp theo lô vào thời điểm có kiểm soát.
- Truy vấn chủ yếu là báo cáo và tổng hợp.
- Cột phân loại ít giá trị và được dùng kết hợp nhiều predicate.
- Các truy vấn được benchmark cho thấy bitmap giảm chi phí tổng thể.

### 8.3. Phân biệt bitmap contention với row lock thông thường

Một transaction UPDATE hàng vẫn khóa hàng bảng theo cơ chế Oracle. Bitmap index có thể thêm một nguồn tranh chấp ở index entry. Do đó, hai session sửa hai hàng khác nhau có thể không xung đột row lock trên table nhưng vẫn chờ nhau khi cần sửa bitmap entry liên quan.

Khi chẩn đoán, đừng chỉ nhìn vào việc SALE_ID khác nhau rồi kết luận không thể có lock wait. Hãy xem wait event, object/index liên quan và transaction đang giữ khóa.

### 8.4. Đừng giải quyết bằng cách xóa mọi bitmap index

Nếu hệ thống vừa có workload đọc phân tích vừa có cập nhật:

- Xác định cột nào thực sự thay đổi trong OLTP.
- Đo thời gian chờ và throughput khi có/không có index.
- Cân nhắc tách fact/history table chỉ đọc khỏi bảng trạng thái vận hành.
- Dùng B-tree cho access path của ứng dụng giao dịch.
- Dùng bitmap cho bảng kho dữ liệu hoặc partition phù hợp với ETL.
- Cân nhắc materialized view hoặc bảng tổng hợp nếu mục tiêu là báo cáo.

Không xóa index trong production chỉ dựa trên lý thuyết. Index có thể đang hỗ trợ các truy vấn quan trọng hoặc constraint khác; cần đánh giá plan và tác động trước khi thay đổi.

## 9. Bộ dữ liệu thực hành

Tạo bảng mô phỏng fact table với các thuộc tính phân loại có cardinality thấp:

```sql
CREATE TABLE lab_sales_bitmap (
    sale_id      NUMBER(12)
        CONSTRAINT pk_lab_sales_bitmap PRIMARY KEY,
    region_code  VARCHAR2(20),
    channel      VARCHAR2(20),
    status       VARCHAR2(20),
    sold_at      DATE,
    amount       NUMBER(12, 2)
);
```

Nạp dữ liệu đủ lớn để optimizer có cơ hội cân nhắc index:

```sql
INSERT INTO lab_sales_bitmap (
    sale_id, region_code, channel, status, sold_at, amount
)
SELECT
    LEVEL,
    CASE MOD(LEVEL, 5)
        WHEN 0 THEN 'NORTH'
        WHEN 1 THEN 'SOUTH'
        WHEN 2 THEN 'EAST'
        WHEN 3 THEN 'WEST'
        ELSE 'CENTRAL'
    END,
    CASE MOD(LEVEL, 3)
        WHEN 0 THEN 'WEB'
        WHEN 1 THEN 'STORE'
        ELSE 'PARTNER'
    END,
    CASE MOD(LEVEL, 4)
        WHEN 0 THEN 'PAID'
        WHEN 1 THEN 'NEW'
        WHEN 2 THEN 'CANCELLED'
        ELSE 'REFUNDED'
    END,
    DATE '2026-01-01' + MOD(LEVEL, 365),
    MOD(LEVEL * 17, 100000) / 100
FROM dual
CONNECT BY LEVEL <= 100000;

COMMIT;
```

Dữ liệu này có 100.000 hàng, 5 vùng, 3 kênh và 4 trạng thái. Phân bố do MOD tạo ra khá đều, chỉ nhằm minh họa. Dữ liệu thực tế thường lệch phân bố và có tương quan giữa các cột.

Kiểm tra cardinality:

```sql
SELECT 'REGION_CODE' AS column_name,
       COUNT(DISTINCT region_code) AS distinct_values
FROM lab_sales_bitmap
UNION ALL
SELECT 'CHANNEL', COUNT(DISTINCT channel)
FROM lab_sales_bitmap
UNION ALL
SELECT 'STATUS', COUNT(DISTINCT status)
FROM lab_sales_bitmap
UNION ALL
SELECT 'SALE_ID', COUNT(DISTINCT sale_id)
FROM lab_sales_bitmap;
```

## 10. Tạo bitmap index và so sánh truy vấn

### 10.1. Tạo bitmap index cho thuộc tính phân loại

```sql
CREATE BITMAP INDEX ix_lsb_region_bm
ON lab_sales_bitmap (region_code);

CREATE BITMAP INDEX ix_lsb_channel_bm
ON lab_sales_bitmap (channel);

CREATE BITMAP INDEX ix_lsb_status_bm
ON lab_sales_bitmap (status);
```

SALE_ID đã có primary key index; không cần tạo bitmap index cho khóa duy nhất. SOLD_AT có nhiều giá trị ngày và có thể cần B-tree hoặc partition pruning tùy workload.

### 10.2. Truy vấn kết hợp ba predicate

```sql
SELECT
    region_code,
    channel,
    SUM(amount) AS total_amount,
    COUNT(*) AS sale_count
FROM lab_sales_bitmap
WHERE region_code IN ('NORTH', 'SOUTH')
  AND channel = 'WEB'
  AND status = 'PAID'
GROUP BY region_code, channel;
```

Oracle có thể dùng bitmap index trên ba cột để kết hợp điều kiện. Nếu bảng nhỏ hoặc thống kê cho thấy full scan rẻ hơn, plan có thể không dùng bitmap. Đó không nhất thiết là lỗi.

### 10.3. Cập nhật thống kê

Trong môi trường lab, có thể thu thập thống kê:

```sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname => USER,
        tabname => 'LAB_SALES_BITMAP',
        cascade => TRUE
    );
END;
/
```

Thống kê giúp optimizer ước lượng số hàng và chi phí. Với dữ liệu skewed, histogram có thể ảnh hưởng ước lượng predicate. Không thu thập thống kê một cách tùy tiện trên production; dùng quy trình quản trị stats của hệ thống.

### 10.4. Xem execution plan

```sql
EXPLAIN PLAN FOR
SELECT SUM(amount)
FROM lab_sales_bitmap
WHERE region_code = 'NORTH'
  AND channel = 'WEB'
  AND status = 'PAID';

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
```

Tìm các operation bitmap như BITMAP INDEX SINGLE VALUE, BITMAP AND và BITMAP CONVERSION TO ROWIDS nếu optimizer chọn đường truy cập bitmap. Nếu plan là TABLE ACCESS FULL, so sánh estimated rows và chi phí; với dữ liệu lab nhỏ/đều, full scan có thể hợp lý.

### 10.5. Xem actual row-source statistics

Có thể chạy query với thống kê thực thi trong môi trường thử nghiệm:

```sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       SUM(amount)
FROM lab_sales_bitmap
WHERE region_code = 'NORTH'
  AND channel = 'WEB'
  AND status = 'PAID';

SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL,
        NULL,
        'ALLSTATS LAST'
    )
);
```

ALLSTATS LAST có thể hiển thị actual rows nếu row-source statistics được thu thập và tài khoản có quyền phù hợp. So sánh E-Rows với A-Rows để xem optimizer ước lượng chính xác hay không. Nếu lệch lớn, xem phân bố dữ liệu, histogram, correlation giữa các cột và freshness của statistics.

### 10.6. So sánh trước/sau khi bỏ bitmap index

Trong schema lab, có thể lưu plan trước rồi drop index và xem plan lại:

```sql
DROP INDEX ix_lsb_region_bm;
DROP INDEX ix_lsb_channel_bm;
DROP INDEX ix_lsb_status_bm;
```

Chạy lại EXPLAIN PLAN và so sánh. Optimizer có thể chọn full scan hoặc access path khác. Việc drop index là thao tác DDL có implicit commit; chỉ thực hiện trong schema lab, không chạy trên bảng production để thử nghiệm.

## 11. Kiểm thử tranh chấp cập nhật bằng hai session

Mục tiêu của lab là quan sát rằng bitmap index có thể gây chờ giữa các DML sửa hàng khác nhau nhưng tác động cùng bitmap entry. Kết quả phụ thuộc cách Oracle tổ chức bitmap, phân bố ROWID và thời điểm session; không phải mọi lần chạy đều tái hiện cùng thời gian chờ.

### 11.1. Chuẩn bị một bitmap index trên STATUS

Tạo lại index nếu đã xóa ở mục 10.6:

```sql
CREATE BITMAP INDEX ix_lsb_status_bm
ON lab_sales_bitmap (status);
```

Tìm hai SALE_ID khác nhau có cùng STATUS = NEW:

```sql
SELECT sale_id, status
FROM lab_sales_bitmap
WHERE status = 'NEW'
  AND ROWNUM <= 10
ORDER BY sale_id;
```

Chọn hai ID khác nhau từ kết quả, ví dụ hai hàng A và B. Không dùng cùng một SALE_ID trong cả hai session vì khi đó có thể phát sinh row lock thông thường, làm sai mục tiêu quan sát bitmap contention.

### 11.2. Thử trong session A và B

Trong session A:

```sql
UPDATE lab_sales_bitmap
SET status = 'PAID'
WHERE sale_id = :sale_id_a;
-- Chưa COMMIT.
```

Trong session B, cập nhật hàng khác có cùng trạng thái cũ:

```sql
UPDATE lab_sales_bitmap
SET status = 'PAID'
WHERE sale_id = :sale_id_b;
-- Quan sát xem statement có phải chờ không.
```

Quay lại session A:

```sql
COMMIT;
```

Quan sát session B tiếp tục hay đã hoàn tất. Có thể lặp lại trong schema lab và so sánh khi bitmap index được drop. Việc không thấy chờ trong một lần chạy không chứng minh bitmap index không thể contention; cần xem timing, entry và concurrency pattern.

### 11.3. So sánh với B-tree index

Trong lab, có thể drop bitmap index và tạo B-tree index trên STATUS:

```sql
DROP INDEX ix_lsb_status_bm;

CREATE INDEX ix_lsb_status_btree
ON lab_sales_bitmap (status);
```

Lặp lại bài test hai session và so sánh. Đây là minh họa định tính; không dùng bảng nhỏ để kết luận benchmark hiệu năng production. B-tree cũng có contention ở block/index và row-level locking, nhưng cấu trúc khóa bitmap có thể tạo tranh chấp rộng hơn theo tập ROWID.

### 11.4. Kiểm tra session đang chờ

DBA có thể kiểm tra session waits/locks bằng các view động như V$SESSION, V$LOCK và thông tin object liên quan nếu được cấp quyền. Người dùng thông thường có thể không có quyền đọc các view này. Không cấp quyền DBA chỉ để chạy lab; nhờ quản trị viên cung cấp dữ liệu wait phù hợp.

## 12. Bitmap index trên bảng partitioned và quy trình ETL

### 12.1. Local bitmap index

Với fact table được partition theo thời gian, local index chia theo các partition tương ứng. Local bitmap index thường là lựa chọn phù hợp trong kho dữ liệu vì:

- Mỗi partition có index riêng.
- Dữ liệu mới có thể được nạp/bảo trì theo partition.
- Drop/truncate/exchange partition có thể được quản lý cục bộ hơn.
- Công việc bảo trì không nhất thiết phải xử lý toàn bộ index của bảng.

Oracle hỗ trợ bitmap index local trên bảng partitioned; bitmap index partitioned có các giới hạn khác với B-tree global index. Kiểm tra khả năng và cú pháp theo phiên bản Oracle cụ thể trước khi thiết kế.

Ví dụ minh họa:

```sql
CREATE BITMAP INDEX ix_fact_status_local
ON fact_sales (status)
LOCAL;
```

LOCAL yêu cầu bảng đã được partition và index được chia theo partition của bảng.

### 12.2. Tải dữ liệu theo batch

Trong kho dữ liệu, quy trình ETL có thể:

1. Nạp dữ liệu vào staging.
2. Kiểm tra dữ liệu và loại lỗi.
3. Nạp/đổi partition fact table.
4. Cập nhật hoặc rebuild local bitmap index theo chiến lược vận hành.
5. Thu thập statistics.
6. Chạy kiểm tra chất lượng và truy vấn báo cáo đại diện.

Không mặc định phải DROP bitmap index trước mọi lần load. Một số phương thức load có thể duy trì index; một số phương thức/partition operation có thể làm index unusable hoặc cần rebuild. Kiểm tra trạng thái index sau thao tác và theo tài liệu Oracle cho đúng loại load/partition operation.

### 12.3. Kiểm tra trạng thái index và partition

Index không partition:

```sql
SELECT index_name, status, visibility
FROM user_indexes
WHERE table_name = 'FACT_SALES';
```

Index partitioned:

```sql
SELECT
    index_name,
    partition_name,
    status
FROM user_ind_partitions
WHERE index_name = UPPER(:index_name)
ORDER BY partition_position;
```

Nếu index hoặc partition index UNUSABLE, optimizer không thể sử dụng nó như một index hợp lệ cho truy vấn; các thao tác DML tiếp theo cũng có thể bị ảnh hưởng tùy trạng thái/cấu hình. Xử lý bằng rebuild hoặc quy trình khôi phục thích hợp trước khi dựa vào index.

### 12.4. Rebuild và bảo trì

Ví dụ rebuild bitmap index không partition:

```sql
ALTER INDEX ix_lsb_status_bm REBUILD;
```

Với index local partitioned, có thể cần thao tác trên từng index partition hoặc dùng câu lệnh phù hợp. Rebuild là DDL và có tác động về I/O, space, locking và availability; lên lịch trong cửa sổ bảo trì và theo dõi dung lượng tablespace.

## 13. Thực hành thiết kế và vận hành

### 13.1. Đánh giá trước khi tạo bitmap index

Trước khi tạo index, thu thập:

- Tổng số hàng và kích thước bảng.
- Số distinct và phân bố của cột.
- Tỷ lệ predicate thường chọn.
- Tổ hợp WHERE thường gặp trong BI.
- Tần suất INSERT/UPDATE/DELETE trên bảng và từng cột.
- Số session ghi đồng thời và SLA của DML.
- Chi phí index storage, redo/undo và ETL maintenance.

Không chỉ nhìn cardinality thấp rồi tạo bitmap. Một cột trạng thái chỉ có 3 giá trị nhưng được cập nhật 20.000 lần/giây trong OLTP là ứng viên kém.

### 13.2. Kiểm tra workload thay vì ép index

Không dùng hint INDEX hoặc BITMAP để buộc optimizer dùng index khi chưa có benchmark. Hint có thể khiến plan tốt trong một tập dữ liệu nhỏ nhưng tệ khi phân bố dữ liệu thay đổi.

So sánh thời gian thực thi, logical reads, physical reads, CPU, TEMP, số hàng thực tế và thời gian DML khi index có/không có. Đánh giá cả tổng workload: index giúp SELECT nhưng làm UPDATE chậm có thể là trade-off không chấp nhận được.

### 13.3. Histogram và dữ liệu skewed

Nếu một giá trị chiếm 95% và các giá trị khác chiếm 5%, ước lượng selectivity dựa trên phân bố đều sẽ sai. Statistics và histogram có thể giúp optimizer hiểu skew. Tuy nhiên histogram cũng có chi phí quản trị và phụ thuộc workload; dùng DBMS_STATS theo chính sách của hệ thống.

### 13.4. Correlation giữa các cột

REGION_CODE và TAX_ZONE có thể tương quan mạnh. Nếu optimizer giả định hai predicate độc lập, ước lượng số hàng sau khi AND bitmap có thể sai. Extended statistics hoặc cách thiết kế partition/dimension phù hợp có thể giúp, nhưng cần đo và cấu hình theo truy vấn thực tế.

### 13.5. Tránh index dư thừa

Nhiều bitmap index có thể tăng dung lượng và chi phí ETL. Mỗi index cần được đánh giá theo:

- Có predicate nào dùng nó không?
- Nó có giúp kết hợp bitmap với index khác không?
- Có index ghép hoặc access path khác thay thế không?
- Cột có thay đổi thường xuyên không?
- Có ảnh hưởng đến thời gian load, rebuild và backup không?

Index không được sử dụng có thể là ứng viên loại bỏ, nhưng cần quan sát đủ workload theo chu kỳ kinh doanh và xác nhận không có báo cáo định kỳ ít chạy.

## 14. Những hiểu nhầm thường gặp

| Hiểu nhầm | Thực tế |
| --- | --- |
| Cột cardinality thấp luôn phải dùng bitmap | Còn phụ thuộc DML concurrency, selectivity, bảng và workload |
| Có bitmap index thì optimizer luôn dùng | Full scan hoặc B-tree có thể rẻ hơn |
| Bitmap index chỉ phù hợp cột có đúng 2–3 giá trị | Không có ngưỡng cố định; cần xem phân bố và workload |
| Bitmap index làm khóa toàn bảng khi UPDATE | Không nhất thiết; contention liên quan bitmap entry/vùng ROWID, không phải mọi UPDATE đều khóa toàn bảng |
| Hai session cập nhật hai row khác nhau không thể block | Có thể block trên bitmap entry dù row lock khác nhau |
| Bitmap index có thể làm PRIMARY KEY | Bitmap index không dùng để thực thi unique constraint |
| Public/low-cardinality column thì luôn có bitmap | Một cột có ít giá trị vẫn có thể được index bằng B-tree nếu workload phù hợp |
| Drop index không ảnh hưởng dữ liệu | Dữ liệu bảng còn nguyên nhưng plan và hiệu năng truy vấn có thể thay đổi |
| Bitmap index chỉ có ích khi truy vấn một cột | Điểm mạnh thường là kết hợp nhiều điều kiện phân loại |
| Một lần benchmark SELECT đủ quyết định | Cần benchmark cả DML, concurrency, ETL và workload tổng |

## 15. Bài tập tổng hợp

### Phần A — Đọc bitmap

Với bảng minh họa ở mục 1.1:

1. Bitmap WEB có bao nhiêu bit 1?
2. Bitmap STORE có bao nhiêu bit 1?
3. Phép AND giữa WEB và STORE cho kết quả nào?
4. Nếu truy vấn CHANNEL = WEB OR CHANNEL = STORE thì bitmap kết quả gồm những hàng nào?

### Phần B — Chọn loại index

Một bảng có 50 triệu giao dịch. STATUS có 4 giá trị, CUSTOMER_ID có 3 triệu giá trị, SALE_ID là khóa duy nhất. Workload gồm:

- Dashboard lọc STATUS + REGION + CHANNEL, đọc nhiều.
- API tìm SALE_ID và cập nhật trạng thái từng hàng.
- Báo cáo lịch sử theo CUSTOMER_ID.

Đề xuất index cho từng nhu cầu và giải thích vì sao không nên tạo bitmap trên mọi cột.

### Phần C — Kiểm tra cardinality

Chạy truy vấn COUNT(DISTINCT) ở mục 9. Thêm một giá trị STATUS mới và đo lại cardinality. Thảo luận liệu chỉ thay đổi số distinct có đủ để quyết định bitmap hay không.

### Phần D — Đọc execution plan

Chạy truy vấn ở mục 10.4. Ghi lại:

- Optimizer chọn full scan hay bitmap access?
- Có BITMAP AND/OR không?
- E-Rows ở bước bitmap và table access là bao nhiêu?
- Có khác biệt giữa estimated rows và actual rows không?

Không có một plan bắt buộc cho lab. Điều cần học là cách đọc và lý giải lựa chọn của optimizer.

### Phần E — Mô phỏng tranh chấp

Thực hiện lab hai session ở mục 11:

1. Chọn hai hàng khác nhau cùng STATUS.
2. Session A UPDATE nhưng chưa commit.
3. Session B UPDATE hàng còn lại sang cùng trạng thái đích.
4. Quan sát có chờ không.
5. Commit A, quan sát B.
6. Drop bitmap index, tạo B-tree index và thử lại.

Giải thích vì sao cùng một bảng và hai row khác nhau vẫn có thể có khác biệt về wait khi index thay đổi.

### Phần F — Thiết kế ETL

Một fact table được nạp 20 triệu hàng mỗi đêm, partition theo tháng, có 4 bitmap index trên các cột phân loại. Đề xuất quy trình load, kiểm tra trạng thái index, rebuild khi cần và thu thập statistics. Nêu những câu hỏi cần xác nhận với DBA trước khi dùng partition exchange hoặc direct-path load.

### Phần G — Phân biệt workload

Đánh giá hai hệ thống:

- Hệ thống A: 95% SELECT báo cáo, 5% batch load hàng đêm.
- Hệ thống B: 30% SELECT, 70% UPDATE/INSERT từ hàng trăm session.

Giải thích vì sao cùng một cột STATUS có thể phù hợp bitmap ở A nhưng không phù hợp bitmap ở B.

## 16. Nguyên tắc thực hành tốt

1. **Chọn bitmap theo workload.** Cột ít distinct là tín hiệu ban đầu, không phải quyết định cuối.
2. **Ưu tiên bitmap cho tải phân tích đọc nhiều.** Data warehouse và reporting thường tận dụng tốt khả năng kết hợp bitmap.
3. **Tránh bitmap trên cột cập nhật nóng trong OLTP.** Cập nhật nhiều hàng đồng thời có thể tranh chấp bitmap entry.
4. **Dùng B-tree cho khóa định danh và truy vấn điểm.** Primary key/unique key cần cơ chế uniqueness phù hợp.
5. **Kết hợp nhiều predicate có chủ đích.** Bitmap AND/OR hữu ích khi truy vấn lọc theo nhiều chiều.
6. **Không ép optimizer dùng index.** Full table scan có thể rẻ hơn nếu query đọc phần lớn bảng.
7. **Đo cả SELECT và DML.** Index tốt cho báo cáo có thể làm ghi chậm và tăng lock waits.
8. **Giữ transaction ngắn.** Không giữ khóa trong khi chờ dịch vụ ngoài hoặc xử lý công việc không liên quan.
9. **Quản lý ETL và index cùng nhau.** Kiểm tra trạng thái index sau load/partition operation.
10. **Thu thập statistics phù hợp.** Skew và correlation ảnh hưởng cardinality estimate.
11. **Không dùng bitmap index để bảo vệ uniqueness.** Dùng PK/UNIQUE constraint.
12. **Xem actual plan và wait events.** Kết luận từ dữ liệu và workload thật, không chỉ từ lý thuyết.

## 17. Câu hỏi tự kiểm tra

1. Bitmap index biểu diễn một giá trị cột và các ROWID tương ứng như thế nào?
2. Cardinality khác selectivity ra sao?
3. Vì sao cột STATUS có 4 giá trị thường là ứng viên bitmap trong data warehouse?
4. Vì sao cùng cột STATUS có thể không phù hợp bitmap trong OLTP?
5. Oracle kết hợp bitmap index cho các predicate AND như thế nào?
6. Khi nào full table scan có thể nhanh hơn bitmap access?
7. Bitmap index khác B-tree index ở cấu trúc và khả năng DML ra sao?
8. Vì sao bitmap index có thể biểu diễn NULL trong khi B-tree không lưu entry cho khóa toàn NULL?
9. Bitmap index có thể dùng làm unique index không? Vì sao?
10. Vì sao hai session cập nhật hai row khác nhau vẫn có thể chờ nhau?
11. UPDATE từ NEW sang PAID cần thay đổi những bitmap nào?
12. Vì sao transaction dài có thể làm tăng thời gian chờ bitmap?
13. BITMAP AND, BITMAP OR và BITMAP CONVERSION TO ROWIDS biểu thị điều gì?
14. Tại sao không thể kết luận optimizer sai khi nó chọn full table scan dù bitmap index tồn tại?
15. Local bitmap index giúp gì trong fact table partitioned?
16. Vì sao cần kiểm tra trạng thái index sau ETL hoặc partition maintenance?
17. Histogram và correlation có thể ảnh hưởng optimizer estimate như thế nào?
18. Cần benchmark những chỉ số nào ngoài thời gian SELECT?

## 18. Mô hình ghi nhớ

```text
BITMAP INDEX
    |
    +-- Mỗi giá trị có bitmap ánh xạ tới ROWID
    |
    +-- Thường hiệu quả với cardinality thấp
    |
    +-- Kết hợp predicate bằng AND / OR / NOT
    |
    v
ANALYTIC WORKLOAD
    |
    +-- Bảng lớn, đọc nhiều
    +-- Báo cáo ad hoc nhiều chiều
    +-- ETL theo batch
    |
    v
RỦI RO DML
    |
    +-- Một bitmap entry bao phủ nhiều hàng
    +-- UPDATE đổi bitmap cũ và bitmap mới
    +-- Hai session khác row vẫn có thể contention
    |
    v
LỰA CHỌN
    |
    +-- DW / reporting ít ghi: cân nhắc bitmap
    +-- OLTP ghi đồng thời: thường ưu tiên B-tree
    +-- PK / UNIQUE: dùng unique B-tree constraint
    +-- Luôn đo plan, actual rows, waits và ETL cost
```

**Điểm cần nhớ:** bitmap index tối ưu cho việc lọc và kết hợp nhiều thuộc tính phân loại trong workload đọc nhiều. Cùng cấu trúc bitmap đó có thể làm DML đồng thời tranh chấp vì một entry đại diện cho nhiều hàng. Hãy lựa chọn theo cardinality, selectivity, tần suất cập nhật và pattern truy vấn; kiểm tra execution plan lẫn wait events để xác nhận hiệu quả thực tế.
