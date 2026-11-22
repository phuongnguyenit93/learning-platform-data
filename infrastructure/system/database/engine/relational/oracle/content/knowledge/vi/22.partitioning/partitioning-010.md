# Thống kê theo partition và incremental statistics trong Oracle Database

Với bảng được chia partition, optimizer cần thống kê đủ chính xác ở nhiều cấp để ước lượng số hàng, chọn thứ tự join, quyết định access path và tận dụng partition pruning. DBA có thể thu thập thống kê cho từng partition, cho toàn bảng hoặc cho cả hai cấp. Với bảng rất lớn nhưng chỉ một vài partition thay đổi mỗi ngày, việc quét toàn bộ bảng để tính lại global statistics có thể tốn thời gian và tài nguyên.

Oracle hỗ trợ **incremental statistics** để giảm công việc này. Khi bật incremental statistics cho bảng partitioned, Oracle duy trì các synopsis (bản tóm tắt thống kê) cho partition. Khi một partition thay đổi và được thu thập thống kê, Oracle có thể kết hợp các synopsis cùng partition statistics để cập nhật global statistics mà không cần quét lại toàn bộ dữ liệu của các partition không đổi.

Cần phân biệt ba cấp thông tin:

- **Partition statistics:** mô tả dữ liệu trong từng partition.
- **Global statistics:** mô tả toàn bộ bảng partitioned như một đối tượng logic.
- **Incremental statistics:** cơ chế giúp duy trì một số global statistics từ các synopsis của partition, giảm chi phí khi chỉ một phần dữ liệu thay đổi.

Bài học trình bày vì sao optimizer cần thống kê theo partition, cách xem và thu thập partition/global statistics, cách bật incremental statistics bằng DBMS_STATS, cách synopsis hỗ trợ global statistics, quy trình xử lý partition mới hoặc partition thay đổi, giám sát stale statistics và các lưu ý vận hành.

## 1. Vì sao bảng partitioned cần thống kê ở nhiều cấp?

### 1.1. Partition pruning chỉ là một phần của quyết định thực thi

Giả sử bảng SALES được partition theo tháng dựa trên SALE_DATE. Truy vấn:

```sql
SELECT product_id,
       SUM(amount)
FROM   sales
WHERE  sale_date >= DATE '2026-03-01'
AND    sale_date <  DATE '2026-04-01'
GROUP  BY product_id;
```

Optimizer có thể loại các partition không chứa dữ liệu tháng 3/2026 nhờ partition pruning. Nhưng sau khi xác định partition cần đọc, optimizer vẫn cần thống kê để ước lượng số hàng, số block, độ chọn lọc của predicate và chi phí join/aggregate.

Partition pruning giúp giảm phạm vi dữ liệu cần truy cập; statistics giúp optimizer chọn cách xử lý phạm vi đó.

### 1.2. Partition statistics

Partition statistics mô tả một partition riêng. Ví dụ một partition tháng 3 có:
- Số hàng.
- Số block.
- Average row length.
- Thống kê cột.
- Histogram nếu được thu thập.
- Thời điểm thống kê gần nhất và trạng thái stale.

Các partition có thể có phân bố dữ liệu rất khác nhau. Một partition mới có thể có nhiều hàng hơn các partition cũ; một partition theo khu vực có thể chứa một nhóm giá trị tập trung. Nếu chỉ nhìn thống kê tổng thể, optimizer có thể không ước lượng tốt khi truy vấn chỉ truy cập một partition cụ thể.

### 1.3. Global statistics

Global statistics mô tả toàn bộ bảng partitioned. Chúng có ích khi:
- Truy vấn truy cập nhiều partition.
- Predicate không giới hạn trực tiếp partition key.
- Optimizer cần ước lượng tổng thể cho join với bảng khác.
- Truy vấn tổng hợp dữ liệu trên toàn bảng.
- Cần ước lượng cardinality trên phạm vi nhiều partition.

Ví dụ truy vấn theo PRODUCT_ID mà không giới hạn SALE_DATE:

```sql
SELECT *
FROM   sales
WHERE  product_id = 500;
```

Truy vấn có thể phải xét nhiều partition. Global statistics về PRODUCT_ID trên toàn bảng có thể quan trọng cho ước lượng tổng thể.

### 1.4. Partition statistics và global statistics bổ sung cho nhau

| Cấp thống kê | Phạm vi | Thường hữu ích khi |
| --- | --- | --- |
| Partition | Một partition | Truy vấn được partition pruning xuống một hoặc vài partition |
| Subpartition | Một subpartition trong bảng composite partitioned | Truy vấn và chiến lược truy cập cần thống kê chi tiết hơn ở cấp subpartition |
| Global | Toàn bộ bảng | Truy vấn nhiều partition hoặc cần ước lượng tổng thể |

Không nên giả định global statistics luôn thay thế partition statistics hoặc ngược lại. Optimizer có thể cần cả hai tùy predicate, partition pruning, kiểu partitioning và kế hoạch truy vấn.

## 2. Các loại thống kê trên bảng partitioned

### 2.1. Thống kê ở cấp bảng

Ở cấp bảng, Oracle lưu các thông tin tổng hợp như:
- NUM_ROWS: số hàng ước lượng.
- BLOCKS: số block được thống kê.
- AVG_ROW_LEN: độ dài hàng trung bình.
- Thống kê cột và histogram.
- LAST_ANALYZED: thời điểm thu thập.
- GLOBAL_STATS: thông tin về nguồn/cách tạo thống kê toàn cục theo dictionary.
- STALE_STATS: trạng thái stale theo cơ chế monitoring và ngưỡng cấu hình.

Với bảng partitioned, dòng table-level thường thể hiện thống kê global.

### 2.2. Thống kê partition và subpartition

Partitioned table có thể có một dòng thống kê cho mỗi partition. Composite partitioned table còn có thống kê subpartition.

Ví dụ bảng RANGE-HASH:

```sql
CREATE TABLE sales_demo (
    sale_id     NUMBER NOT NULL,
    sale_date   DATE NOT NULL,
    product_id  NUMBER NOT NULL,
    amount      NUMBER(12,2)
)
PARTITION BY RANGE (sale_date)
SUBPARTITION BY HASH (product_id)
SUBPARTITIONS 4
(
    PARTITION p2026_01 VALUES LESS THAN (DATE '2026-02-01'),
    PARTITION p2026_02 VALUES LESS THAN (DATE '2026-03-01'),
    PARTITION pmax     VALUES LESS THAN (MAXVALUE)
);
```

Trong ví dụ:
- Partition chia dữ liệu theo khoảng SALE_DATE.
- Mỗi partition được chia tiếp thành bốn subpartition theo HASH(PRODUCT_ID).
- Thống kê có thể được quản lý ở cấp table, partition và subpartition.

### 2.3. Thống kê cột và histogram

Thống kê cột giúp optimizer ước lượng predicate như:

```sql
SELECT *
FROM   sales_demo
WHERE  product_id = 500;
```

Nếu giá trị PRODUCT_ID phân bố lệch, histogram có thể giúp ước lượng selectivity tốt hơn. Với bảng partitioned, phân bố trong một partition có thể khác phân bố global. Cần chọn METHOD_OPT phù hợp với workload và tránh tạo histogram hàng loạt không có lý do.

### 2.4. Thống kê index cũng quan trọng

Optimizer còn dùng thống kê index như:
- NUM_ROWS.
- DISTINCT_KEYS.
- LEAF_BLOCKS.
- CLUSTERING_FACTOR.
- BLEVEL.

Partitioned index có thống kê ở cấp global/partition tùy loại index và cách thu thập. Khi đánh giá plan trên bảng partitioned, đừng chỉ xem USER_TAB_STATISTICS; hãy kiểm tra USER_IND_STATISTICS và metadata index nếu truy vấn phụ thuộc index.

## 3. Xem thống kê hiện có

### 3.1. USER_TAB_STATISTICS

Xem thống kê table, partition và subpartition trong schema hiện tại:

```sql
SELECT table_name,
       partition_name,
       subpartition_name,
       num_rows,
       blocks,
       avg_row_len,
       last_analyzed,
       global_stats,
       stale_stats
FROM   user_tab_statistics
WHERE  table_name = 'SALES_DEMO'
ORDER  BY partition_name, subpartition_name;
```

Dòng table-level có PARTITION_NAME và SUBPARTITION_NAME rỗng; các dòng khác đại diện cho partition hoặc subpartition. Các cột và giá trị chi tiết cần đối chiếu dictionary reference của phiên bản Oracle đang dùng.

### 3.2. DBA_TAB_STATISTICS

DBA có thể xem nhiều schema:

```sql
SELECT owner,
       table_name,
       partition_name,
       subpartition_name,
       num_rows,
       blocks,
       last_analyzed,
       stale_stats
FROM   dba_tab_statistics
WHERE  owner = 'APP'
AND    table_name = 'SALES'
ORDER  BY partition_name, subpartition_name;
```

Nếu không có quyền DBA, dùng USER_TAB_STATISTICS hoặc ALL_TAB_STATISTICS theo phạm vi quyền được cấp.

### 3.3. Xem thống kê index

```sql
SELECT index_name,
       table_name,
       partition_name,
       num_rows,
       distinct_keys,
       leaf_blocks,
       clustering_factor,
       last_analyzed,
       visibility
FROM   user_ind_statistics
WHERE  table_name = 'SALES_DEMO'
ORDER  BY index_name, partition_name;
```

Thống kê index cần được xem cùng thống kê bảng để hiểu access path. Với index partitioned, kiểm tra các dòng global và partition phù hợp.

### 3.4. Xem cấu trúc partition

```sql
SELECT partition_name,
       partition_position,
       high_value,
       num_rows,
       last_analyzed
FROM   user_tab_partitions
WHERE  table_name = 'SALES_DEMO'
ORDER  BY partition_position;
```

USER_TAB_PARTITIONS cho biết metadata partition. HIGH_VALUE thường được hiển thị dưới dạng LONG trong một số dictionary view, nên việc lọc hoặc xử lý trực tiếp cột này có giới hạn. Dùng view phù hợp và công cụ metadata nếu cần trích xuất ranh giới partition phức tạp.

### 3.5. Phân biệt stale statistics

Statistics có thể được đánh dấu stale khi số thay đổi dữ liệu được ghi nhận vượt ngưỡng STALE_PERCENT. Mặc định phổ biến là 10%, nhưng có thể thay đổi theo preference và cách quản lý thống kê.

Stale không có nghĩa statistics chắc chắn sai nghiêm trọng. Nó là tín hiệu để đánh giá hoặc thu thập lại. Ngược lại, statistics chưa stale vẫn có thể không phản ánh tốt phân bố dữ liệu nếu workload hoặc phân bố giá trị thay đổi đáng kể.

Có thể flush thông tin monitoring trước khi xem trạng thái:

```sql
BEGIN
    DBMS_STATS.FLUSH_DATABASE_MONITORING_INFO;
END;
/
```

Thao tác này cập nhật thông tin monitoring trong dictionary. Cần cân nhắc quyền và chi phí trên hệ thống lớn.

## 4. Thu thập partition statistics bằng DBMS_STATS

### 4.1. GATHER_TABLE_STATS

Oracle cung cấp package DBMS_STATS để thu thập thống kê. Không nên dùng ANALYZE TABLE COMPUTE STATISTICS cho quy trình quản lý optimizer statistics hiện đại; dùng DBMS_STATS.

Ví dụ thu thập thống kê cho toàn bảng:

```sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname          => USER,
        tabname          => 'SALES_DEMO',
        estimate_percent => DBMS_STATS.AUTO_SAMPLE_SIZE,
        method_opt       => 'FOR ALL COLUMNS SIZE AUTO',
        granularity      => 'AUTO',
        cascade          => DBMS_STATS.AUTO_CASCADE,
        no_invalidate    => DBMS_STATS.AUTO_INVALIDATE
    );
END;
/
```

Các tham số:
- OWNNAME và TABNAME: schema và bảng.
- ESTIMATE_PERCENT: tỷ lệ lấy mẫu; AUTO_SAMPLE_SIZE để Oracle chọn.
- METHOD_OPT: chính sách thống kê cột và histogram.
- GRANULARITY: cấp thống kê cần thu thập.
- CASCADE: cách xử lý thống kê index liên quan.
- NO_INVALIDATE: kiểm soát invalidation cursor sau khi publish statistics.

### 4.2. GRANULARITY

Một số giá trị GRANULARITY thường dùng:

| Giá trị | Ý nghĩa |
| --- | --- |
| AUTO | Oracle chọn cấp thống kê phù hợp với kiểu partitioning và cấu hình |
| ALL | Thu thập thống kê ở các cấp liên quan, gồm global và partition/subpartition khi áp dụng |
| GLOBAL | Chỉ thu thập global statistics |
| PARTITION | Thu thập partition statistics |
| SUBPARTITION | Thu thập subpartition statistics |
| DEFAULT | Dùng hành vi mặc định theo phiên bản |

Các lựa chọn và hành vi cụ thể có thể khác theo release và loại partitioning. Với bảng composite partitioned, AUTO thường là lựa chọn thực tế để Oracle quyết định cấp phù hợp.

### 4.3. Thu thập thống kê cho một partition

Nếu chỉ partition P2026_01 thay đổi:

```sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname          => USER,
        tabname          => 'SALES_DEMO',
        partname         => 'P2026_01',
        estimate_percent => DBMS_STATS.AUTO_SAMPLE_SIZE,
        method_opt       => 'FOR ALL COLUMNS SIZE AUTO',
        granularity      => 'PARTITION',
        cascade          => DBMS_STATS.AUTO_CASCADE,
        no_invalidate    => DBMS_STATS.AUTO_INVALIDATE
    );
END;
/
```

Thao tác này tập trung vào partition được chỉ định. Với bảng rất lớn, thu thập thống kê cho partition thay đổi có thể rẻ hơn nhiều so với quét toàn bảng.

### 4.4. Thu thập global statistics

Nếu cần cập nhật thống kê global:

```sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname          => USER,
        tabname          => 'SALES_DEMO',
        estimate_percent => DBMS_STATS.AUTO_SAMPLE_SIZE,
        method_opt       => 'FOR ALL COLUMNS SIZE AUTO',
        granularity      => 'GLOBAL',
        cascade          => DBMS_STATS.AUTO_CASCADE,
        no_invalidate    => DBMS_STATS.AUTO_INVALIDATE
    );
END;
/
```

Với incremental statistics được bật và synopsis có sẵn, Oracle có thể tính global statistics từ thông tin tổng hợp của các partition thay vì quét mọi hàng trong toàn bảng. Nếu synopsis chưa có hoặc không thể dùng, công việc thu thập có thể phải đọc nhiều dữ liệu hơn dự kiến.

### 4.5. Thu thập thống kê cho subpartition

Với composite partitioned table, có thể chỉ định SUBPARTITION và GRANULARITY phù hợp:

```sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname          => USER,
        tabname          => 'SALES_DEMO',
        partname         => 'SYS_SUBP123',
        estimate_percent => DBMS_STATS.AUTO_SAMPLE_SIZE,
        granularity      => 'SUBPARTITION',
        cascade          => DBMS_STATS.AUTO_CASCADE
    );
END;
/
```

Tên subpartition chỉ là ví dụ. Lấy đúng tên từ USER_TAB_SUBPARTITIONS hoặc DBA_TAB_SUBPARTITIONS. Không tự đoán tên do Oracle sinh.

## 5. Incremental statistics là gì?

### 5.1. Vấn đề khi gather global statistics truyền thống

Giả sử bảng SALES có 120 partition theo tháng, mỗi partition chứa hàng chục triệu hàng. Mỗi ngày chỉ partition tháng hiện tại thay đổi.

Nếu mỗi lần cập nhật global statistics đều phải quét toàn bộ bảng, chi phí sẽ tăng theo tổng số dữ liệu, dù chỉ một partition thay đổi.

Incremental statistics được thiết kế để giảm chi phí duy trì global statistics cho bảng partitioned có thay đổi cục bộ.

### 5.2. Synopsis

Khi incremental statistics được bật, Oracle duy trì các synopsis cho partition. Có thể hiểu synopsis là bản tóm tắt nhỏ gọn về dữ liệu partition, đặc biệt hữu ích cho việc tổng hợp số lượng giá trị phân biệt (NDV — number of distinct values) trên toàn bảng.

Khi cần global statistics, Oracle kết hợp synopsis của các partition cùng thông tin partition statistics để tổng hợp kết quả. Cách này giúp tránh phải quét lại toàn bộ dữ liệu của các partition không đổi chỉ để tính global NDV.

Synopses là metadata nội bộ do Oracle quản lý. Không cập nhật hoặc xóa trực tiếp các bảng SYS nội bộ chứa synopsis.

### 5.3. Incremental không phải chỉ gather partition

Thu thập thống kê riêng cho một partition là một thao tác. Incremental statistics là cơ chế duy trì synopsis và hỗ trợ cập nhật global statistics hiệu quả.

Chỉ chạy GATHER_TABLE_STATS với PARTITION không tự chứng minh global statistics đã được cập nhật. Cần xác định mục tiêu:
- Cập nhật partition statistics.
- Cập nhật global statistics.
- Duy trì synopsis cho partition thay đổi.
- Xác nhận global statistics phản ánh dữ liệu mới.

### 5.4. Điều kiện và giới hạn

Incremental statistics áp dụng cho bảng partitioned. Hiệu quả phụ thuộc:
- Preference INCREMENTAL của bảng.
- Synopsis đã được tạo cho các partition cần thiết.
- Granularity và thao tác gather phù hợp.
- Partition maintenance operations.
- Phiên bản Oracle và các tính năng thống kê được hỗ trợ.

Lần bật incremental đầu tiên có thể cần thu thập dữ liệu trên nhiều hoặc toàn bộ partition để tạo synopsis ban đầu. Chi phí khởi tạo vì thế có thể đáng kể. Lợi ích lớn nhất thường xuất hiện ở các lần cập nhật sau, khi chỉ một phần partition thay đổi.

## 6. Bật incremental statistics

### 6.1. Thiết lập preference ở cấp bảng

Có thể bật incremental cho một bảng:

```sql
BEGIN
    DBMS_STATS.SET_TABLE_PREFS(
        ownname => USER,
        tabname => 'SALES_DEMO',
        pname   => 'INCREMENTAL',
        pvalue  => 'TRUE'
    );
END;
/
```

Preference gắn với bảng, không phải một tham số toàn cục áp dụng tự động cho mọi bảng. Đây là cách kiểm soát phạm vi triển khai.

### 6.2. Kiểm tra preference

```sql
SELECT DBMS_STATS.GET_PREFS(
           pname   => 'INCREMENTAL',
           ownname => USER,
           tabname => 'SALES_DEMO'
       ) AS incremental_pref
FROM dual;
```

Kết quả TRUE cho biết incremental preference đang bật cho bảng theo cấu hình DBMS_STATS.

### 6.3. Khởi tạo statistics và synopses

Sau khi bật incremental, thu thập thống kê để Oracle tạo/duy trì synopsis:

```sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname          => USER,
        tabname          => 'SALES_DEMO',
        estimate_percent => DBMS_STATS.AUTO_SAMPLE_SIZE,
        method_opt       => 'FOR ALL COLUMNS SIZE AUTO',
        granularity      => 'ALL',
        cascade          => DBMS_STATS.AUTO_CASCADE,
        no_invalidate    => DBMS_STATS.AUTO_INVALIDATE
    );
END;
/
```

Với bảng lớn, lần chạy đầu có thể tốn tài nguyên vì cần tạo thông tin synopsis cho các partition chưa có. Lên lịch và giám sát như một công việc bảo trì lớn.

### 6.4. Thu thập incremental sau khi một partition thay đổi

Ví dụ partition P2026_03 nhận dữ liệu mới. Một quy trình minh họa:

Bước 1 — thu thập partition statistics:

```sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname          => USER,
        tabname          => 'SALES_DEMO',
        partname         => 'P2026_03',
        estimate_percent => DBMS_STATS.AUTO_SAMPLE_SIZE,
        method_opt       => 'FOR ALL COLUMNS SIZE AUTO',
        granularity      => 'PARTITION',
        cascade          => DBMS_STATS.AUTO_CASCADE
    );
END;
/
```

Bước 2 — cập nhật global statistics:

```sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname          => USER,
        tabname          => 'SALES_DEMO',
        estimate_percent => DBMS_STATS.AUTO_SAMPLE_SIZE,
        method_opt       => 'FOR ALL COLUMNS SIZE AUTO',
        granularity      => 'GLOBAL',
        cascade          => DBMS_STATS.AUTO_CASCADE
    );
END;
/
```

Khi incremental statistics được cấu hình và synopsis đầy đủ, Oracle có thể dùng synopsis để tính global statistics mà không quét lại tất cả các partition không đổi. Hãy kiểm tra hành vi và thời gian gather trên release đang vận hành.

Trong một số lịch bảo trì, có thể dùng GRANULARITY AUTO để Oracle quyết định các cấp cần cập nhật. Hãy xác nhận global và partition statistics sau khi gather thay vì chỉ dựa vào việc thủ tục chạy thành công.

### 6.5. Tắt incremental preference

Nếu không muốn tiếp tục dùng incremental statistics:

```sql
BEGIN
    DBMS_STATS.SET_TABLE_PREFS(
        ownname => USER,
        tabname => 'SALES_DEMO',
        pname   => 'INCREMENTAL',
        pvalue  => 'FALSE'
    );
END;
/
```

Tắt preference không đồng nghĩa mọi synopsis nội bộ bị xóa ngay. Hãy quản lý thống kê theo API DBMS_STATS và quy trình được hỗ trợ; không xóa dữ liệu SYS trực tiếp.

## 7. Incremental statistics giúp global statistics ra sao?

### 7.1. Không cần quét lại mọi partition không đổi

Ví dụ bảng có 36 partition:

```text
P01 P02 P03 P04 ... P34 P35 P36
 |   |   |   |       |   |   |
đã  đã  đã  đã      đã  đã  mới
có  có  có  có      có  có  thay
syn syn syn syn     syn syn đổi

Chỉ P36 cần gather lại.
Oracle cập nhật synopsis của P36 rồi kết hợp synopsis các partition
để duy trì global statistics.
```

Đây là lợi ích chính của incremental statistics trên bảng lớn có workload thay đổi theo partition.

### 7.2. Global NDV

Một trong những thống kê khó tổng hợp trên nhiều partition là NDV của cột. Không thể cộng đơn giản NDV của từng partition vì cùng một giá trị có thể xuất hiện ở nhiều partition.

Ví dụ:

| Partition | Các PRODUCT_ID | NDV |
| --- | --- | ---: |
| P1 | 10, 20, 30 | 3 |
| P2 | 20, 30, 40 | 3 |
| P3 | 30, 40, 50 | 3 |

Tổng NDV toàn bảng là 5, không phải 9. Synopsis giúp Oracle ước lượng/duy trì NDV global mà không cần quét lại toàn bộ hàng trong mọi partition.

### 7.3. Các loại thống kê khác

Incremental statistics không có nghĩa mọi thống kê global đều được xử lý chỉ bằng synopsis theo cùng một cách. Oracle có thể tổng hợp nhiều thông tin từ partition statistics và synopsis; chi tiết hỗ trợ phụ thuộc phiên bản, loại thống kê và cấu hình.

Đặc biệt, hãy xem riêng:
- Histogram và phân bố giá trị.
- Extended statistics.
- Thống kê index global/local.
- Partition mới hoặc partition vừa exchange.
- Các cột có độ lệch dữ liệu lớn.

Không suy ra rằng incremental bật thì mọi histogram global luôn phản ánh chính xác mọi phân bố mới. Kiểm tra dictionary statistics và execution plan của workload quan trọng.

### 7.4. Incremental không thay thế gather partition statistics

Nếu dữ liệu trong một partition thay đổi nhưng partition statistics không được cập nhật, synopsis có thể không phản ánh dữ liệu mới. Quy trình cần gather partition đã thay đổi trước khi dựa vào global incremental statistics.

## 8. Partition mới và partition maintenance operations

### 8.1. ADD PARTITION

Khi thêm partition mới, partition ban đầu có thể rỗng hoặc được nạp dữ liệu sau đó. Sau khi nạp:
- Thu thập partition statistics.
- Đảm bảo synopsis được tạo/duy trì nếu incremental bật.
- Cập nhật global statistics theo quy trình phù hợp.
- Kiểm tra partition stats và global stats.

Ví dụ:

```sql
ALTER TABLE sales_demo
ADD PARTITION p2026_04
VALUES LESS THAN (DATE '2026-05-01');
```

Sau khi nạp dữ liệu vào partition, gather thống kê cho partition đó. Không giả định chỉ ADD PARTITION đã tạo đầy đủ statistics cho dữ liệu sẽ được nạp sau này.

### 8.2. TRUNCATE hoặc DROP PARTITION

Khi truncate/drop partition, số hàng và phân bố dữ liệu toàn bảng thay đổi. Cần xem xét:
- Partition statistics có còn phản ánh đúng không?
- Global statistics có cần cập nhật không?
- Synopsis của partition đã bị loại bỏ/điều chỉnh theo thao tác chưa?
- Local/global index có cần maintenance không?

DBMS_STATS và Oracle xử lý một số metadata liên quan đến partition maintenance, nhưng quy trình cụ thể phụ thuộc thao tác và phiên bản. Kiểm tra stats sau mỗi đợt PMOP quan trọng.

### 8.3. EXCHANGE PARTITION

EXCHANGE PARTITION thường dùng để nạp dữ liệu nhanh bằng cách hoán đổi metadata giữa một bảng staging và partition. Thống kê của staging table có thể hữu ích để chuẩn bị cho partition sau exchange.

Một quy trình thường cân nhắc:
1. Nạp dữ liệu vào staging table.
2. Thu thập table statistics trên staging table.
3. Thực hiện EXCHANGE PARTITION theo đúng constraint/index requirements.
4. Dùng DBMS_STATS API phù hợp để chuyển/copy stats nếu được hỗ trợ cho trường hợp đó, hoặc gather partition stats sau exchange.
5. Cập nhật global incremental statistics.
6. Xác nhận partition/global stats và plan.

DBMS_STATS có thủ tục hỗ trợ sao chép thống kê giữa table/partition trong các tình huống phù hợp. Cần tra chữ ký và giới hạn của COPY_TABLE_STATS trong đúng phiên bản; không tự chép các dòng dictionary nội bộ.

### 8.4. Partition mới không có synopsis

Nếu incremental statistics mới được bật hoặc partition mới chưa có synopsis, lần gather global có thể cần bổ sung synopsis và đọc nhiều dữ liệu hơn. Đây là lý do nên khởi tạo incremental statistics trước khi kỳ vọng các lần gather sau chỉ xử lý partition thay đổi.

## 9. Stale statistics và lịch thu thập

### 9.1. STALE_PERCENT

Oracle dùng thông tin monitoring về số hàng thay đổi để xác định statistics có thể stale. Preference STALE_PERCENT đặt ngưỡng phần trăm thay đổi. Mặc định phổ biến là 10%.

Có thể xem preference:

```sql
SELECT DBMS_STATS.GET_PREFS(
           'STALE_PERCENT',
           USER,
           'SALES_DEMO'
       ) AS stale_percent
FROM dual;
```

Ngưỡng stale là tín hiệu vận hành, không phải bảo đảm optimizer luôn cần gather ngay khi đạt ngưỡng hoặc luôn có thể dùng stats dưới ngưỡng.

### 9.2. GATHER STALE

Có thể yêu cầu DBMS_STATS thu thập thống kê cho đối tượng stale theo quy tắc:

```sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname          => USER,
        tabname          => 'SALES_DEMO',
        estimate_percent => DBMS_STATS.AUTO_SAMPLE_SIZE,
        method_opt       => 'FOR ALL COLUMNS SIZE AUTO',
        granularity      => 'AUTO',
        options          => 'GATHER STALE',
        cascade          => DBMS_STATS.AUTO_CASCADE
    );
END;
/
```

Hành vi cụ thể với partitioned table cần được kiểm tra theo release và preference. Nếu muốn chắc chắn chỉ gather một partition, chỉ định PARTNAME và GRANULARITY phù hợp.

### 9.3. Tự động statistics gathering

Oracle có automatic optimizer statistics gathering task trong maintenance window ở các cấu hình phổ biến. DBA vẫn cần kiểm tra:
- Job có chạy đúng thời điểm không?
- Có bảng/partition bị lock statistics không?
- Bảng có bị exclude hoặc preference khác thường không?
- Incremental có được bật cho đúng bảng không?
- Partition mới có được gather sau khi nạp không?
- Thời lượng job và resource consumption có phù hợp không?

Không mặc định rằng auto task đã xử lý hoàn hảo mọi bảng partitioned hoặc mọi tình huống exchange partition.

### 9.4. LOCK_TABLE_STATS

Statistics có thể bị khóa bằng DBMS_STATS.LOCK_TABLE_STATS. Khi stats bị lock, gather tự động có thể không cập nhật theo cách mong muốn.

Kiểm tra trạng thái:

```sql
SELECT table_name,
       stattype_locked,
       stale_stats,
       last_analyzed
FROM   user_tab_statistics
WHERE  table_name = 'SALES_DEMO';
```

Chỉ unlock khi hiểu lý do khóa và quy trình quản trị:

```sql
BEGIN
    DBMS_STATS.UNLOCK_TABLE_STATS(
        ownname => USER,
        tabname => 'SALES_DEMO'
    );
END;
/
```

Không khóa statistics để giữ plan ổn định nếu chưa đánh giá SQL Plan Management hoặc cơ chế kiểm soát plan phù hợp hơn.

## 10. Pending statistics và thử nghiệm plan

### 10.1. Vì sao dùng pending statistics?

Khi muốn thử statistics mới mà chưa công bố cho toàn bộ workload, có thể dùng pending statistics. Cách này giúp DBA thu thập và kiểm tra thống kê mới trong session thử nghiệm trước khi publish.

Đặt PUBLISH FALSE ở cấp bảng:

```sql
BEGIN
    DBMS_STATS.SET_TABLE_PREFS(
        ownname => USER,
        tabname => 'SALES_DEMO',
        pname   => 'PUBLISH',
        pvalue  => 'FALSE'
    );
END;
/
```

Thu thập statistics. Thống kê mới được giữ ở trạng thái pending theo cơ chế DBMS_STATS.

### 10.2. Dùng pending statistics trong session thử nghiệm

```sql
ALTER SESSION SET optimizer_use_pending_statistics = TRUE;
```

Chạy các SQL đại diện, thu thập runtime plan và so sánh với statistics đã publish. Session khác mặc định tiếp tục dùng published statistics nếu không bật pending statistics.

### 10.3. Publish hoặc xóa pending statistics

Sau khi kiểm tra đạt yêu cầu:

```sql
BEGIN
    DBMS_STATS.PUBLISH_PENDING_STATS(
        ownname => USER,
        tabname => 'SALES_DEMO'
    );
END;
/
```

Nếu không muốn dùng thống kê pending:

```sql
BEGIN
    DBMS_STATS.DELETE_PENDING_STATS(
        ownname => USER,
        tabname => 'SALES_DEMO'
    );
END;
/
```

Sau thử nghiệm, reset session parameter và preference PUBLISH theo quy trình đã định. Pending statistics là một cơ chế kiểm tra plan; nó không thay thế kiểm tra chất lượng dữ liệu và thống kê.

## 11. Thống kê và execution plan

### 11.1. Statistics ảnh hưởng optimizer như thế nào?

Optimizer dùng thống kê để ước lượng:
- Cardinality của từng operation.
- Selectivity của predicate.
- Số block cần đọc.
- Chi phí index access và full scan.
- Join order và join method.
- Chi phí sort, hash và aggregation.

Với partitioned table, global và partition statistics có thể dẫn tới ước lượng khác nhau. Nếu một partition có phân bố rất khác phần còn lại, thống kê cấp partition có thể giúp truy vấn pruning chính xác hơn.

### 11.2. Kiểm tra plan thực tế

Có thể thu thập runtime plan:

```sql
SELECT /*+ gather_plan_statistics */
       product_id,
       SUM(amount)
FROM   sales_demo
WHERE  sale_date >= DATE '2026-03-01'
AND    sale_date <  DATE '2026-04-01'
GROUP  BY product_id;
```

Sau khi fetch kết quả:

```sql
SELECT *
FROM   TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL,
        NULL,
        'ALLSTATS LAST +PARTITION +PREDICATE'
    )
);
```

Xem:
- Partition Start/Stop để hiểu partition pruning.
- E-Rows và A-Rows để so sánh ước lượng với thực tế.
- Buffers và Reads để đánh giá công việc đọc.
- Predicate Information để xác định điều kiện access/filter.
- Join order và join method nếu có nhiều bảng.

### 11.3. So sánh trước và sau gather

Sau khi cập nhật partition/global stats, cùng SQL có thể có plan khác. Điều đó không tự động là tốt hơn. So sánh runtime, buffers, reads, CPU, elapsed time và kết quả dữ liệu.

Không thay đổi statistics, index, optimizer parameter và SQL cùng lúc nếu mục tiêu là xác định yếu tố gây plan change. Thay đổi từng yếu tố và giữ bind values/workload tương đương.

### 11.4. NO_INVALIDATE

Tham số NO_INVALIDATE của DBMS_STATS kiểm soát việc invalidation cursor sau khi statistics được publish. AUTO_INVALIDATE cho phép Oracle chọn chính sách invalidation phù hợp.

Không mặc định đặt FALSE để invalidate tất cả cursor ngay lập tức trong hệ thống tải cao. Cần cân nhắc parse overhead, shared pool và kế hoạch triển khai.

## 12. Các lưu ý hiệu năng và vận hành

### 12.1. Lần khởi tạo incremental có thể tốn kém

Bật INCREMENTAL không tự tạo đầy đủ synopsis cho toàn bộ lịch sử partition. Lần gather đầu có thể cần đọc nhiều partition. Lên lịch phù hợp, theo dõi I/O/CPU và tránh chạy trùng các batch lớn.

### 12.2. Không gather toàn bộ bảng mỗi ngày nếu chỉ một partition đổi

Đối với bảng rất lớn theo ngày/tháng, hãy thiết kế quy trình chỉ gather partition vừa thay đổi và cập nhật global statistics theo incremental synopsis. Việc gather toàn bảng liên tục có thể lãng phí tài nguyên và kéo dài maintenance window.

### 12.3. Partition mới và dữ liệu load

Sau load/exchange, cần bảo đảm partition statistics và synopsis phản ánh dữ liệu mới. Nếu không, global statistics có thể vẫn dựa trên thông tin cũ hoặc thiếu synopsis của partition mới.

### 12.4. Histograms cần được cân nhắc

METHOD_OPT như `FOR ALL COLUMNS SIZE AUTO` để Oracle quyết định histogram theo workload và phân bố dữ liệu. Không tạo histogram trên mọi cột chỉ vì muốn thống kê chi tiết hơn. Histogram không phù hợp có thể khiến plan nhạy với bind values hoặc làm tăng biến động kế hoạch.

### 12.5. Statistics không phải dữ liệu thật

Gather statistics không sửa hàng, không xóa partition và không thay đổi business data. Nó cập nhật metadata mà optimizer dùng để lập kế hoạch. Tuy vậy, việc gather có thể đọc lượng dữ liệu lớn và tiêu thụ tài nguyên đáng kể.

### 12.6. Global index và local index

Bảng partitioned có thể dùng local index hoặc global index. Khi partition maintenance operations xảy ra, index statistics và trạng thái index cần được xem xét riêng. Incremental table statistics không tự thay thế việc quản lý thống kê index.

## 13. Quy trình vận hành đề xuất

Với bảng partitioned lớn, có thể tổ chức lịch thống kê như sau:

1. **Thiết kế partition:** xác định partition key, interval và chiến lược load/retention.
2. **Thu thập baseline:** gather table, partition và index statistics phù hợp.
3. **Bật incremental:** đặt INCREMENTAL TRUE cho bảng cần hưởng lợi.
4. **Khởi tạo synopsis:** gather statistics trên các partition hiện có theo granularity phù hợp.
5. **Load partition mới:** nạp dữ liệu hoặc exchange partition.
6. **Gather partition thay đổi:** cập nhật stats của đúng partition/subpartition.
7. **Cập nhật global:** dùng incremental synopsis và granularity phù hợp.
8. **Kiểm tra stale:** xem USER_TAB_STATISTICS/DBA_TAB_STATISTICS.
9. **Kiểm tra plan:** xem partition pruning, A-Rows, E-Rows, buffers và runtime.
10. **Theo dõi:** đo thời gian gather, resource usage và các plan quan trọng.
11. **Điều chỉnh:** thay đổi preference hoặc lịch gather khi workload thay đổi.
12. **Khôi phục nếu cần:** dùng stats history/pending stats theo quy trình quản trị đã định.

Không có lịch gather chung cho mọi bảng. Bảng append-only theo ngày có thể cần quy trình khác bảng có UPDATE/DELETE trên nhiều partition cũ.

## 14. Bài thực hành tổng hợp

Các bài tập sử dụng bảng SALES_DEMO trong mục 2.2. Chạy trên schema học tập.

### Bài 1 — Xem partition statistics

```sql
SELECT table_name,
       partition_name,
       subpartition_name,
       num_rows,
       blocks,
       last_analyzed,
       stale_stats
FROM   user_tab_statistics
WHERE  table_name = 'SALES_DEMO'
ORDER  BY partition_name, subpartition_name;
```

Xác định dòng global, partition và subpartition.

### Bài 2 — Gather partition statistics

```sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname => USER,
        tabname => 'SALES_DEMO',
        partname => 'P2026_01',
        granularity => 'PARTITION',
        estimate_percent => DBMS_STATS.AUTO_SAMPLE_SIZE
    );
END;
/
```

Quan sát LAST_ANALYZED và STALE_STATS.

### Bài 3 — Gather global statistics

Dùng GRANULARITY GLOBAL. So sánh thời gian và kết quả với việc gather toàn bộ cấp ALL.

### Bài 4 — Bật incremental preference

```sql
BEGIN
    DBMS_STATS.SET_TABLE_PREFS(
        USER,
        'SALES_DEMO',
        'INCREMENTAL',
        'TRUE'
    );
END;
/
```

Dùng GET_PREFS để xác nhận.

### Bài 5 — Khởi tạo synopses

Gather statistics với GRANULARITY ALL. Ghi lại thời gian, tài nguyên và kết quả. Giải thích vì sao lần đầu có thể tốn kém.

### Bài 6 — Thay đổi một partition

Thêm dữ liệu vào một partition demo, gather partition stats rồi cập nhật global stats. So sánh thời gian với gather toàn bảng trong môi trường có đủ dữ liệu.

### Bài 7 — So sánh global NDV

Tạo dữ liệu có PRODUCT_ID trùng giữa nhiều partition. Giải thích vì sao tổng NDV partition không thể cộng đơn giản để có NDV global.

### Bài 8 — Kiểm tra stale statistics

Flush monitoring info rồi xem STALE_STATS. Thử thay đổi STALE_PERCENT ở schema test và quan sát cách ngưỡng ảnh hưởng đến stale status.

### Bài 9 — Xem index statistics

Truy vấn USER_IND_STATISTICS và so sánh global/local index stats với table stats.

### Bài 10 — EXCHANGE PARTITION

Tạo staging table có cấu trúc tương thích, gather stats trước exchange, thực hiện exchange trong schema demo nếu đủ quyền, rồi xác nhận partition statistics và global stats. Tra DBMS_STATS.COPY_TABLE_STATS nếu muốn thử chuyển thống kê theo release.

### Bài 11 — Pending statistics

Đặt PUBLISH FALSE, gather stats, bật OPTIMIZER_USE_PENDING_STATISTICS trong session thử nghiệm và so sánh plan. Sau đó publish hoặc xóa pending stats.

### Bài 12 — Chẩn đoán plan sai

Một truy vấn lọc theo partition key nhưng optimizer ước lượng hàng cao gấp 100 lần thực tế. Hãy kiểm tra partition pruning, partition stats, global stats, histogram, bind và thời điểm gather trước khi thay đổi index.

## 15. Những nhầm lẫn thường gặp

**“Partition pruning có nghĩa không cần global statistics.”** Không. Optimizer vẫn cần thống kê phù hợp cho partition được truy cập và cho các phép join/ước lượng tổng thể.

**“Global statistics luôn bằng tổng partition statistics.”** Không phải mọi thống kê đều cộng đơn giản; NDV là ví dụ rõ ràng vì giá trị có thể lặp giữa partition.

**“Incremental statistics tự động gather partition vừa thay đổi.”** Không. Đây là cơ chế synopsis hỗ trợ duy trì global stats; vẫn cần quy trình gather phù hợp.

**“Chỉ bật INCREMENTAL là lập tức có synopsis cho toàn bộ partition.”** Không. Lần khởi tạo có thể cần gather trên các partition hiện có.

**“Gather một partition chắc chắn đã cập nhật global stats.”** Không nên giả định. Xác định GRANULARITY và kiểm tra global row sau gather.

**“Statistics stale nghĩa là sai.”** Không nhất thiết. Stale là tín hiệu theo ngưỡng monitoring, không phải phép đo độ chính xác tuyệt đối.

**“Incremental chỉ áp dụng cho bảng không có subpartition.”** Không. Bảng composite partitioned có thể có statistics ở nhiều cấp; cần chọn granularity và kiểm tra release.

**“Gather statistics không ảnh hưởng workload.”** Sai. Thu thập stats có thể đọc nhiều dữ liệu, dùng CPU/I/O và ảnh hưởng maintenance window.

**“Histogram càng nhiều càng tốt.”** Không. Histogram cần phù hợp với phân bố và workload.

**“Index stats tự động được giải quyết bởi incremental table stats.”** Không. Kiểm tra và quản lý index statistics riêng.

## 16. Tài liệu Oracle tham khảo

- [Oracle Database SQL Tuning Guide — Managing Optimizer Statistics](https://docs.oracle.com/en/database/oracle/oracle-database/19/tgsql/managing-optimizer-statistics.html): quy trình thu thập và quản lý optimizer statistics.
- [Oracle Database SQL Tuning Guide — Incremental Statistics](https://docs.oracle.com/en/database/oracle/oracle-database/19/tgsql/optimizer-statistics-concepts.html): khái niệm optimizer statistics và thông tin liên quan incremental statistics.
- [Oracle Database PL/SQL Packages and Types Reference — DBMS_STATS](https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/DBMS_STATS.html): GATHER_TABLE_STATS, SET_TABLE_PREFS, GET_PREFS và các thủ tục thống kê.
- [Oracle Database Reference — USER_TAB_STATISTICS](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/USER_TAB_STATISTICS.html): thống kê table, partition và subpartition.
- [Oracle Database Reference — USER_TAB_PARTITIONS](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/USER_TAB_PARTITIONS.html): metadata partition.
- [Oracle Database VLDB and Partitioning Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/vldbg/): thiết kế partition và quản lý bảng partitioned.

Thống kê partition giúp optimizer hiểu dữ liệu trong từng partition, còn global statistics mô tả toàn bảng. Với bảng partitioned lớn chỉ thay đổi một phần mỗi lần, incremental statistics duy trì synopsis để hỗ trợ cập nhật global statistics mà không phải quét lại mọi partition không đổi. Hãy bật incremental có chọn lọc, khởi tạo synopsis, gather đúng partition sau load/maintenance, cập nhật global statistics và kiểm tra execution plan thực tế. **Incremental statistics giảm chi phí bảo trì thống kê; nó không thay thế việc xác nhận partition statistics, global statistics và workload của ứng dụng.**
