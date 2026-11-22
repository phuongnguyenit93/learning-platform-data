# Thống kê bảng, cột, chỉ mục và thông tin hệ thống

Oracle Database Optimizer sử dụng thống kê để ước lượng số dòng sẽ được đọc, số lần truy cập block, chi phí CPU và I/O của từng phương án thực thi. Từ những ước lượng đó, optimizer chọn access path, join order, join method và các phép biến đổi truy vấn phù hợp.

Thống kê vì vậy ảnh hưởng trực tiếp đến chất lượng execution plan. Một bảng có hàng triệu dòng nhưng thống kê vẫn ghi nhận vài nghìn dòng có thể khiến optimizer chọn nested loops hoặc index access không phù hợp. Một cột có phân bố dữ liệu lệch mạnh nhưng chỉ có thống kê số giá trị phân biệt có thể khiến ước lượng cardinality sai. Một index có clustering factor cao có thể tốn nhiều lần đọc table block hơn dự kiến khi truy cập theo index.

Trong Oracle, cần phân biệt hai nhóm thông tin:

- **Optimizer statistics:** mô tả kích thước, phân bố dữ liệu và đặc điểm I/O/CPU để optimizer ước lượng chi phí. Nhóm này được quản lý chủ yếu bằng package `DBMS_STATS`.
- **Runtime statistics và monitoring metrics:** phản ánh hoạt động thực tế như logical reads, physical reads, thời gian, số dòng thực tế và số lần thực thi. Chúng được quan sát qua execution plan, dynamic performance views và các công cụ giám sát.

Optimizer statistics không phải số đo thời gian chạy của một câu SQL. Thống kê tốt giúp optimizer dự đoán tốt hơn, nhưng vẫn cần so sánh ước lượng với hành vi thực tế của câu lệnh.

## 1. Các nhóm thống kê trong Oracle

Có thể chia optimizer statistics thành các nhóm chính sau:

| Nhóm | Nội dung | Ảnh hưởng chính |
|---|---|---|
| Table statistics | Số dòng, số block, độ dài dòng trung bình, số block rỗng | Ước lượng kích thước bảng và chi phí full table scan |
| Column statistics | Số giá trị phân biệt, số giá trị NULL, min/max, mật độ và histogram | Ước lượng selectivity và cardinality của predicate |
| Index statistics | BLEVEL, leaf blocks, distinct keys, clustering factor | Ước lượng chi phí index range scan, index access và table lookup |
| Partition statistics | Thống kê theo partition/subpartition và thống kê global | Ước lượng truy vấn có partition pruning và truy vấn trên toàn bảng |
| System statistics | Tốc độ CPU và đặc điểm I/O của hệ thống | So sánh chi phí CPU, single-block I/O và multiblock I/O |
| Dictionary/fixed object statistics | Thống kê data dictionary và fixed tables | Giúp optimizer ước lượng các truy vấn quản trị và truy vấn nội bộ |

Những nhóm này bổ sung cho nhau. Table statistics có thể đúng nhưng column histogram thiếu hoặc sai thì optimizer vẫn ước lượng sai predicate. Column statistics tốt nhưng index statistics cũ có thể khiến chi phí index access bị đánh giá sai. System statistics không mô tả một bảng cụ thể mà mô tả đặc tính môi trường thực thi.

## 2. Xem thống kê bảng

Table statistics mô tả quy mô vật lý và logic của bảng. Các thuộc tính thường gặp gồm:

| Thuộc tính | Ý nghĩa |
|---|---|
| `NUM_ROWS` | Số dòng được thống kê tại thời điểm gather |
| `BLOCKS` | Số block được ước lượng là đang chứa dữ liệu của bảng |
| `EMPTY_BLOCKS` | Số block rỗng được ghi nhận theo cách thu thập thống kê |
| `AVG_ROW_LEN` | Độ dài dòng trung bình theo byte |
| `SAMPLE_SIZE` | Số dòng được lấy mẫu khi thu thập thống kê |
| `LAST_ANALYZED` | Thời điểm thu thập thống kê gần nhất |
| `STALE_STATS` | Cho biết thống kê có được đánh dấu là cũ hay không |
| `GLOBAL_STATS` | Cho biết thống kê là global hay được tổng hợp từ các phần thống kê khác, tùy loại object |
| `STATTYPE_LOCKED` | Cho biết loại thống kê đang bị khóa hay không |

Các view thường dùng:

- `USER_TAB_STATISTICS`: thống kê table, partition và subpartition thuộc schema hiện tại.
- `ALL_TAB_STATISTICS`: thống kê các table mà user hiện tại có thể truy cập metadata.
- `DBA_TAB_STATISTICS`: thống kê trên phạm vi database, cần quyền thích hợp.
- `USER_TABLES`, `ALL_TABLES`, `DBA_TABLES`: thông tin bảng cùng một số thuộc tính thống kê quen thuộc.

Ví dụ xem thống kê global của các bảng trong schema hiện tại:

```sql
SELECT table_name,
       num_rows,
       blocks,
       avg_row_len,
       sample_size,
       last_analyzed,
       stale_stats,
       stattype_locked
FROM user_tab_statistics
WHERE partition_name IS NULL
  AND subpartition_name IS NULL
  AND object_type = 'TABLE'
ORDER BY table_name;
```

Với bảng partitioned, các dòng có `PARTITION_NAME` hoặc `SUBPARTITION_NAME` chứa thống kê ở cấp tương ứng. Dòng không có tên partition thường biểu diễn thống kê global của bảng. Khi kiểm tra, cần biết mình đang xem thống kê global hay thống kê của một partition cụ thể.

`NUM_ROWS` và `BLOCKS` là giá trị optimizer sử dụng từ lần gather gần nhất; chúng không nhất thiết bằng số dòng và block hiện tại. Một bảng vừa nạp thêm dữ liệu có thể đã tăng mạnh nhưng thống kê vẫn giữ số liệu cũ cho đến khi được cập nhật.

### 2.1. Table statistics ảnh hưởng đến execution plan như thế nào?

Giả sử một truy vấn đọc bảng `ORDERS`:

```sql
SELECT order_id, order_date, total_amount
FROM orders
WHERE order_date >= DATE '2026-01-01';
```

Optimizer cần ước lượng:

1. Bảng có khoảng bao nhiêu dòng và block?
2. Predicate `order_date >= ...` có thể giữ lại bao nhiêu dòng?
3. Đọc qua index rồi truy cập table block có rẻ hơn đọc toàn bảng không?
4. Nếu truy vấn join thêm bảng khác, nên bắt đầu từ bảng nào?

`NUM_ROWS`, `BLOCKS` và các column/index statistics cùng tham gia vào các ước lượng này. Nếu `NUM_ROWS` quá thấp, optimizer có thể đánh giá thấp lượng công việc cần thực hiện. Nếu `BLOCKS` không phản ánh kích thước thực tế, chi phí full table scan có thể bị ước lượng sai.

Không nên sửa tay số liệu thống kê chỉ để ép optimizer chọn một plan. Nếu số liệu không đúng, hãy tìm nguyên nhân ở quy trình gather, sampling, partition hoặc workload rồi cập nhật thống kê theo dữ liệu thực tế.

## 3. Thống kê cột và selectivity

Column statistics mô tả phân bố giá trị của từng cột. Các thuộc tính thường dùng gồm:

| Thuộc tính | Ý nghĩa |
|---|---|
| `NUM_DISTINCT` | Số giá trị khác nhau được ước lượng |
| `NUM_NULLS` | Số giá trị NULL được ước lượng |
| `DENSITY` | Thông tin mật độ được optimizer sử dụng khi ước lượng predicate; cách diễn giải phụ thuộc loại thống kê và histogram |
| `LOW_VALUE` / `HIGH_VALUE` | Giá trị thấp nhất/cao nhất được ghi nhận, lưu dưới dạng biểu diễn nội bộ |
| `NUM_BUCKETS` | Số bucket của histogram, nếu có |
| `HISTOGRAM` | Loại histogram được tạo cho cột |
| `AVG_COL_LEN` | Độ dài dữ liệu trung bình của cột |
| `SAMPLE_SIZE` | Kích thước mẫu dùng để thu thập thống kê |

Xem thống kê cột trong schema hiện tại:

```sql
SELECT table_name,
       column_name,
       num_distinct,
       num_nulls,
       density,
       histogram,
       num_buckets,
       avg_col_len,
       last_analyzed
FROM user_tab_col_statistics
WHERE table_name = 'ORDERS'
ORDER BY column_name;
```

Tên bảng trong data dictionary thường được lưu dưới dạng chữ hoa nếu object được tạo bằng tên không đặt trong dấu nháy kép. Nếu object được tạo bằng quoted identifier, cần dùng đúng cách viết tên đã khai báo.

### 3.1. NUM_DISTINCT và ước lượng selectivity

Selectivity biểu diễn tỷ lệ dòng mà một điều kiện lọc có thể giữ lại. Với một cột phân bố gần đồng đều, có thể hình dung predicate bằng một giá trị cụ thể sẽ giữ lại khoảng một phần số giá trị phân biệt. Tuy nhiên, đây chỉ là trực giác ban đầu; optimizer sử dụng nhiều thông tin hơn, và không nên tự suy ra mọi cardinality bằng công thức `1 / NUM_DISTINCT`.

Ví dụ, cột `ORDER_STATUS` có 5 giá trị khác nhau:

| ORDER_STATUS | Số dòng |
|---|---:|
| NEW | 500,000 |
| PAID | 400,000 |
| SHIPPED | 90,000 |
| CANCELLED | 9,000 |
| RETURNED | 1,000 |

`NUM_DISTINCT = 5` không nói rằng mỗi giá trị xuất hiện 20% số dòng. Nếu optimizer giả định phân bố đồng đều trong khi ứng dụng thường truy vấn `RETURNED`, cardinality có thể bị ước lượng cao hơn thực tế rất nhiều. Histogram cung cấp thêm thông tin về độ lệch này.

### 3.2. Histogram giúp mô tả dữ liệu lệch

Histogram chia miền giá trị thành các bucket để mô tả phân bố dữ liệu chi tiết hơn. Chúng đặc biệt hữu ích khi một số giá trị xuất hiện thường xuyên hơn hẳn các giá trị khác và workload có predicate trên cột đó.

Các dạng histogram thường gặp:

- **Frequency histogram:** lưu tần suất cho từng giá trị khi số giá trị phân biệt phù hợp với số bucket.
- **Top-frequency histogram:** tập trung mô tả các giá trị phổ biến nhất và phần còn lại của phân bố.
- **Hybrid histogram:** kết hợp thông tin tần suất và phân bố trong bucket để cải thiện ước lượng với dữ liệu lệch.
- **Height-balanced histogram:** dạng histogram xuất hiện trong các phiên bản hoặc cấu hình cũ; cần hiểu bối cảnh phiên bản khi đọc metadata.

Ví dụ một cột trạng thái có số dòng rất khác nhau:

```text
NEW        ##############################
PAID       ########################
SHIPPED    ######
CANCELLED  #
RETURNED   .
```

Nếu truy vấn lọc `ORDER_STATUS = 'RETURNED'`, histogram có thể giúp optimizer biết predicate này chọn rất ít dòng. Nếu truy vấn lọc `ORDER_STATUS = 'NEW'`, optimizer có thể đánh giá rằng phần lớn bảng cần được đọc và full table scan có thể phù hợp hơn index access.

Thu thập histogram qua `METHOD_OPT` của `DBMS_STATS`:

```sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname          => 'APP',
        tabname          => 'ORDERS',
        estimate_percent => DBMS_STATS.AUTO_SAMPLE_SIZE,
        method_opt       => 'FOR ALL COLUMNS SIZE AUTO',
        cascade          => DBMS_STATS.AUTO_CASCADE
    );
END;
/
```

`SIZE AUTO` cho phép Oracle quyết định cột nào cần histogram dựa trên thông tin sử dụng cột và phân bố dữ liệu. Histogram không phải lúc nào cũng tốt hơn. Khi dữ liệu thay đổi hoặc bind value khác nhau có độ chọn lọc rất khác, histogram có thể làm các lần parse chọn plan khác nhau. Cần kiểm tra execution plan của workload thực tế sau khi thay đổi histogram.

Có thể yêu cầu số bucket cụ thể cho một cột:

```sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname    => 'APP',
        tabname    => 'ORDERS',
        method_opt => 'FOR COLUMNS ORDER_STATUS SIZE 10'
    );
END;
/
```

Đây là cấu hình chủ động; chỉ nên dùng khi đã hiểu phân bố và predicate của workload. Không nên đặt cùng một số bucket tùy ý cho tất cả cột trong mọi bảng.

### 3.3. Xem histogram

`USER_TAB_HISTOGRAMS`, `ALL_TAB_HISTOGRAMS` và `DBA_TAB_HISTOGRAMS` cung cấp các endpoint của histogram. Ví dụ:

```sql
SELECT table_name,
       column_name,
       endpoint_number,
       endpoint_value
FROM user_tab_histograms
WHERE table_name = 'ORDERS'
  AND column_name = 'ORDER_STATUS'
ORDER BY endpoint_number;
```

`ENDPOINT_VALUE` là biểu diễn endpoint trong metadata và không phải lúc nào cũng hiển thị trực tiếp như giá trị gốc của cột. Một số phiên bản có thêm `ENDPOINT_ACTUAL_VALUE`; cần kiểm tra data dictionary của phiên bản đang chạy trước khi dựa vào cột đó. `LOW_VALUE` và `HIGH_VALUE` trong column statistics cũng được lưu dưới dạng RAW, không nên đọc như chuỗi văn bản thông thường.

## 4. Thống kê nhiều cột và expression statistics

Thống kê từng cột riêng lẻ không mô tả được mọi quan hệ giữa các cột. Giả sử bảng `CUSTOMERS` có `COUNTRY_CODE` và `STATE_CODE`. Nếu một bang chỉ thuộc một quốc gia, hai cột có tương quan mạnh. Optimizer có thể đánh giá quá cao hoặc quá thấp số dòng khi gặp predicate đồng thời trên cả hai cột nếu chỉ biết thống kê riêng lẻ.

Oracle hỗ trợ **extended statistics** để mô tả nhóm cột hoặc biểu thức. Ví dụ tạo column group:

```sql
SELECT DBMS_STATS.CREATE_EXTENDED_STATS(
           ownname   => 'APP',
           tabname   => 'CUSTOMERS',
           extension => '(COUNTRY_CODE, STATE_CODE)'
       )
FROM dual;
```

Sau khi tạo extension, thu thập lại thống kê bảng:

```sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname          => 'APP',
        tabname          => 'CUSTOMERS',
        estimate_percent => DBMS_STATS.AUTO_SAMPLE_SIZE,
        method_opt       => 'FOR ALL COLUMNS SIZE AUTO'
    );
END;
/
```

Với predicate dùng expression, có thể tạo expression statistics. Ví dụ truy vấn thường lọc bằng `UPPER(CUSTOMER_NAME)`:

```sql
SELECT DBMS_STATS.CREATE_EXTENDED_STATS(
           ownname   => 'APP',
           tabname   => 'CUSTOMERS',
           extension => '(UPPER(CUSTOMER_NAME))'
       )
FROM dual;
```

Extended statistics cung cấp thông tin cho optimizer; chúng không tự tạo index và cũng không thay thế việc kiểm tra access path. Nếu workload cần index trên expression, hãy xem xét function-based index như một quyết định thiết kế riêng.

Có thể xem các extension đã tạo trong `USER_STAT_EXTENSIONS` hoặc view tương ứng có phạm vi rộng hơn. Trước khi tạo column group hàng loạt, nên quan sát cột nào thực sự được dùng cùng nhau trong predicate. `DBMS_STATS.REPORT_COL_USAGE` có thể giúp xem thông tin column usage mà Oracle ghi nhận:

```sql
SELECT DBMS_STATS.REPORT_COL_USAGE('APP', 'CUSTOMERS')
FROM dual;
```

Kết quả giúp nhận biết các cột thường xuất hiện trong equality predicate, range predicate hoặc nhóm điều kiện. Việc ghi nhận column usage phụ thuộc workload đã chạy và thời điểm quan sát; nó không đại diện cho mọi truy vấn có thể xuất hiện trong tương lai.

## 5. Thống kê chỉ mục

Index statistics mô tả cấu trúc và mối quan hệ giữa thứ tự key trong index với vị trí dòng trong table. Các thuộc tính quan trọng gồm:

| Thuộc tính | Ý nghĩa |
|---|---|
| `BLEVEL` | Số cấp branch từ root đến leaf; index càng sâu thì đường đi đến leaf có thể càng dài |
| `LEAF_BLOCKS` | Số leaf block của index |
| `DISTINCT_KEYS` | Số key khác nhau được thống kê; với composite index là số tổ hợp key khác nhau |
| `AVG_LEAF_BLOCKS_PER_KEY` | Số leaf block trung bình cho một key |
| `AVG_DATA_BLOCKS_PER_KEY` | Số table block trung bình được truy cập cho một key |
| `CLUSTERING_FACTOR` | Mức độ tương quan giữa thứ tự key của index và vị trí vật lý của dòng trong table |
| `NUM_ROWS` | Số dòng được thống kê cho index |
| `LAST_ANALYZED` | Thời điểm thống kê index gần nhất |

Xem thống kê index của bảng `ORDERS`:

```sql
SELECT index_name,
       blevel,
       leaf_blocks,
       distinct_keys,
       avg_leaf_blocks_per_key,
       avg_data_blocks_per_key,
       clustering_factor,
       num_rows,
       last_analyzed,
       stale_stats
FROM user_ind_statistics
WHERE table_name = 'ORDERS'
  AND partition_name IS NULL
ORDER BY index_name;
```

### 5.1. BLEVEL và LEAF_BLOCKS

Index B-tree có các branch block dẫn đến leaf block chứa key và rowid. `BLEVEL` mô tả số cấp branch; `LEAF_BLOCKS` mô tả số leaf block. Những giá trị này tham gia vào việc ước lượng số lần đọc block khi sử dụng index.

Một index có nhiều leaf block có thể lớn do bảng có nhiều dòng hoặc key chiếm nhiều dung lượng. BLEVEL cao hơn có thể làm đường đi đến leaf dài hơn, nhưng không thể kết luận index cần rebuild chỉ dựa vào một con số BLEVEL. Cần xét kích thước index, workload, tốc độ tăng trưởng và plan thực tế.

### 5.2. DISTINCT_KEYS và selectivity của index

`DISTINCT_KEYS` cho biết số key khác nhau được ghi nhận. Nếu index có nhiều key khác nhau so với số dòng, equality predicate trên key có thể chọn lọc tốt. Nếu index chỉ có một vài giá trị lặp lại trên phần lớn dòng, truy cập index có thể kém hấp dẫn hơn full table scan tùy kích thước bảng và clustering factor.

Với composite index, thứ tự cột trong key rất quan trọng đối với khả năng sử dụng index. `DISTINCT_KEYS` mô tả tổ hợp key; cần xem thêm column statistics và predicate thực tế để hiểu độ chọn lọc của từng phần cột.

### 5.3. CLUSTERING_FACTOR

Clustering factor ước lượng mức độ các rowid theo thứ tự key của index nằm gần nhau trong các table block.

- Giá trị tương đối thấp, gần số block của table, thường cho thấy các dòng có key gần nhau cũng nằm trong ít table block hơn. Index range scan có thể cần ít lần đọc table block.
- Giá trị tương đối cao, gần số dòng của table, thường cho thấy các rowid dẫn đến nhiều table block khác nhau. Index range scan có thể cần nhiều lần truy cập table block.

Ví dụ, một bảng lưu đơn hàng theo thứ tự `ORDER_DATE` có thể có clustering factor thuận lợi cho index trên `ORDER_DATE`. Nếu bảng được ghi theo thứ tự `CUSTOMER_ID` nhưng truy vấn range theo một cột khác, clustering factor của index tương ứng có thể cao.

Clustering factor là chỉ số ước lượng, không phải chỉ tiêu chất lượng tuyệt đối. Nó cần được so sánh với số block và số dòng của chính bảng đó. Không nên so sánh clustering factor của hai bảng có quy mô rất khác nhau rồi kết luận index nào tốt hơn.

### 5.4. Thu thập thống kê index

Khi gather table statistics, tham số `CASCADE` quyết định cách thu thập thống kê index liên quan:

```sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname          => 'APP',
        tabname          => 'ORDERS',
        estimate_percent => DBMS_STATS.AUTO_SAMPLE_SIZE,
        method_opt       => 'FOR ALL COLUMNS SIZE AUTO',
        cascade          => DBMS_STATS.AUTO_CASCADE
    );
END;
/
```

`AUTO_CASCADE` để Oracle quyết định việc gather index statistics. Có thể dùng `CASCADE => TRUE` khi chủ động muốn thu thập thống kê cho các index liên quan. Không nên giả định thống kê bảng luôn đảm bảo mọi thống kê index đã được cập nhật theo đúng ý muốn; hãy kiểm tra `LAST_ANALYZED` và `STALE_STATS` của index.

## 6. Thống kê partition và global statistics

Với partitioned table, Oracle có thể lưu thống kê ở nhiều cấp:

- **Partition statistics:** mô tả dữ liệu trong từng partition.
- **Subpartition statistics:** mô tả dữ liệu trong từng subpartition nếu bảng được subpartition.
- **Global statistics:** mô tả toàn bộ bảng partitioned.

Truy vấn chỉ đọc một partition sau partition pruning có thể hưởng lợi từ thống kê của partition đó. Truy vấn đọc nhiều partition hoặc toàn bảng cần thống kê global phù hợp để optimizer ước lượng tổng thể.

Có thể yêu cầu Oracle chọn granularity thích hợp khi gather:

```sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname          => 'APP',
        tabname          => 'SALES',
        estimate_percent => DBMS_STATS.AUTO_SAMPLE_SIZE,
        method_opt       => 'FOR ALL COLUMNS SIZE AUTO',
        granularity      => 'AUTO',
        cascade          => DBMS_STATS.AUTO_CASCADE
    );
END;
/
```

Với bảng partitioned rất lớn, có thể bật incremental statistics ở cấp table:

```sql
BEGIN
    DBMS_STATS.SET_TABLE_PREFS(
        ownname => 'APP',
        tabname => 'SALES',
        pname   => 'INCREMENTAL',
        pvalue  => 'TRUE'
    );
END;
/
```

Incremental statistics sử dụng synopses để tổng hợp global statistics từ các partition, giúp giảm lượng dữ liệu phải quét lại khi chỉ một số partition thay đổi. Cần kiểm tra khả năng hỗ trợ và cấu hình phù hợp với phiên bản Oracle, loại partition và chính sách vận hành đang dùng. Bật incremental không có nghĩa mọi truy vấn sẽ tự động nhanh hơn; lợi ích chính nằm ở quy trình duy trì global statistics cho bảng lớn.

Sau khi gather, kiểm tra cả dòng global và các partition:

```sql
SELECT table_name,
       partition_name,
       num_rows,
       blocks,
       sample_size,
       last_analyzed,
       stale_stats,
       global_stats
FROM user_tab_statistics
WHERE table_name = 'SALES'
ORDER BY partition_name NULLS FIRST;
```

Nếu chỉ gather partition mới mà không cập nhật global statistics phù hợp, optimizer có thể sử dụng số liệu tổng thể cũ. Đây là nguyên nhân cần kiểm tra sau các đợt bulk load, partition exchange hoặc tạo partition mới.

## 7. System statistics và đặc tính CPU/I/O

Table, column và index statistics mô tả dữ liệu. **System statistics** mô tả đặc tính phần cứng và I/O mà optimizer dùng trong mô hình chi phí. Chúng giúp optimizer so sánh chi phí của các phương án phụ thuộc CPU, single-block read và multiblock read.

Một số giá trị system statistics thường gặp:

| Tên | Ý nghĩa khái quát |
|---|---|
| `CPUSPEED` | Tốc độ CPU được đo trong workload statistics |
| `CPUSPEEDNW` | Tốc độ CPU trong thống kê kiểu no-workload |
| `SREADTIM` | Thời gian đọc single block trung bình |
| `MREADTIM` | Thời gian đọc multiblock trung bình |
| `MBRC` | Số block trung bình trong một lần multiblock read |
| `IOSEEKTIM` | Thành phần thời gian seek I/O trong mô hình no-workload |
| `IOTFRSPEED` | Tốc độ truyền I/O trong mô hình no-workload |

System statistics giúp optimizer đánh giá rằng một phép full table scan có thể rẻ hơn hoặc đắt hơn index access trong môi trường cụ thể. Cùng một schema và cùng dữ liệu nhưng hai hệ thống có đặc tính I/O khác nhau có thể có plan khác nhau.

### 7.1. Thu thập system statistics

Có thể thu thập system statistics theo mô hình no-workload:

```sql
BEGIN
    DBMS_STATS.GATHER_SYSTEM_STATS('NOWORKLOAD');
END;
/
```

Hoặc đo trong một khoảng workload đại diện:

```sql
BEGIN
    DBMS_STATS.GATHER_SYSTEM_STATS('START');
END;
/
```

Sau khi hệ thống đã chạy một workload đại diện cho hoạt động bình thường:

```sql
BEGIN
    DBMS_STATS.GATHER_SYSTEM_STATS('STOP');
END;
/
```

Khoảng đo nên phản ánh hoạt động mà database thực sự phục vụ, bao gồm tỷ lệ đọc/ghi và kiểu truy vấn phổ biến. Đo trong thời điểm database gần như nhàn rỗi hoặc chỉ chạy một tác vụ bất thường có thể tạo system statistics không đại diện cho vận hành bình thường.

Có thể đọc từng giá trị bằng API của `DBMS_STATS`:

```sql
DECLARE
    l_value NUMBER;
BEGIN
    DBMS_STATS.GET_SYSTEM_STATS('SREADTIM', l_value);
    DBMS_OUTPUT.PUT_LINE('SREADTIM = ' || NVL(TO_CHAR(l_value), 'NULL'));

    DBMS_STATS.GET_SYSTEM_STATS('MREADTIM', l_value);
    DBMS_OUTPUT.PUT_LINE('MREADTIM = ' || NVL(TO_CHAR(l_value), 'NULL'));

    DBMS_STATS.GET_SYSTEM_STATS('MBRC', l_value);
    DBMS_OUTPUT.PUT_LINE('MBRC = ' || NVL(TO_CHAR(l_value), 'NULL'));
END;
/
```

Không nên sửa trực tiếp các bảng nội bộ lưu system statistics. Hãy dùng API `DBMS_STATS` được Oracle cung cấp và tuân theo quy trình thay đổi có kiểm soát. Việc thu thập lại system statistics có thể làm thay đổi cost model và dẫn đến thay đổi plan trên nhiều câu SQL, vì vậy cần đánh giá tác động trước và sau khi thay đổi.

### 7.2. System statistics khác V$SYSSTAT

Tên gọi dễ gây nhầm lẫn:

- `DBMS_STATS` system statistics là dữ liệu CPU/I/O phục vụ cost-based optimizer.
- `V$SYSSTAT` là các bộ đếm hoạt động của instance, ví dụ logical reads, physical reads hoặc redo size.

Ví dụ xem một số runtime counters:

```sql
SELECT name, value
FROM v$sysstat
WHERE name IN (
    'session logical reads',
    'physical reads',
    'physical writes',
    'redo size'
)
ORDER BY name;
```

Các giá trị trong `V$SYSSTAT` thường là bộ đếm tích lũy từ lúc instance khởi động hoặc theo phạm vi bộ đếm. Muốn đo một khoảng thời gian, cần lấy hai snapshot và tính chênh lệch, đồng thời lưu ý reset do restart hoặc thay đổi instance. Chúng không thay thế `SREADTIM`, `MREADTIM` hoặc `CPUSPEED` trong optimizer system statistics.

## 8. Dictionary statistics và fixed object statistics

Ngoài bảng nghiệp vụ, Oracle còn có data dictionary và fixed tables. Những object này được truy vấn trong quá trình quản trị, phân tích metadata và một số thao tác nội bộ. Khi thống kê của chúng không phù hợp, các truy vấn quản trị hoặc truy vấn sử dụng dictionary có thể được optimizer ước lượng sai.

`DBMS_STATS` cung cấp các thủ tục riêng:

```sql
BEGIN
    DBMS_STATS.GATHER_DICTIONARY_STATS;
END;
/
```

Thủ tục này thu thập thống kê cho data dictionary theo phạm vi và quy tắc Oracle hỗ trợ. Việc chạy nên theo hướng dẫn vận hành của phiên bản database, đặc biệt sau nâng cấp hoặc khi có thay đổi lớn trong dictionary.

Fixed object statistics có thể được thu thập bằng:

```sql
BEGIN
    DBMS_STATS.GATHER_FIXED_OBJECTS_STATS;
END;
/
```

Fixed tables thường cung cấp thông tin động về instance/session và không giống bảng nghiệp vụ thông thường. Nên thu thập fixed object statistics khi database đã có workload đại diện để các ước lượng phản ánh trạng thái hoạt động phù hợp. Không nên chạy thủ tục này một cách máy móc trong mọi lần deploy ứng dụng.

## 9. Thu thập và duy trì statistics bằng DBMS_STATS

`DBMS_STATS` là API chuẩn để thu thập, quản lý, xuất, nhập và khôi phục optimizer statistics. Nên ưu tiên package này thay cho lệnh `ANALYZE` cũ trong các quy trình quản lý optimizer statistics thông thường.

### 9.1. Gather statistics cho một bảng

Ví dụ cơ bản:

```sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname          => 'APP',
        tabname          => 'ORDERS',
        estimate_percent => DBMS_STATS.AUTO_SAMPLE_SIZE,
        method_opt       => 'FOR ALL COLUMNS SIZE AUTO',
        cascade          => DBMS_STATS.AUTO_CASCADE,
        degree           => DBMS_STATS.DEFAULT_DEGREE,
        granularity      => 'AUTO',
        no_invalidate    => DBMS_STATS.AUTO_INVALIDATE
    );
END;
/
```

Ý nghĩa các tham số chính:

- `OWNNAME`, `TABNAME`: schema và bảng cần gather.
- `ESTIMATE_PERCENT`: tỷ lệ lấy mẫu; `DBMS_STATS.AUTO_SAMPLE_SIZE` để Oracle tự chọn cách lấy mẫu phù hợp.
- `METHOD_OPT`: cách thu thập column statistics và histogram.
- `CASCADE`: có thu thập index statistics hay không; `AUTO_CASCADE` để Oracle quyết định.
- `DEGREE`: mức độ song song khi gather.
- `GRANULARITY`: cấp thống kê cần thu thập, đặc biệt với partitioned table.
- `NO_INVALIDATE`: chính sách invalidation cursor phụ thuộc thống kê mới; `AUTO_INVALIDATE` cho Oracle quản lý thời điểm invalidation.

Không cần mặc định dùng `ESTIMATE_PERCENT => 100`. Full scan để lấy mẫu 100% có thể tốn tài nguyên đáng kể và thường không cần thiết vì Oracle có cơ chế chọn mẫu tự động. Chỉ thay đổi cách lấy mẫu khi có lý do đo đạc rõ ràng.

### 9.2. Gather statistics cho schema hoặc database

Có thể thu thập thống kê cho các bảng stale trong schema:

```sql
BEGIN
    DBMS_STATS.GATHER_SCHEMA_STATS(
        ownname          => 'APP',
        options          => 'GATHER STALE',
        estimate_percent => DBMS_STATS.AUTO_SAMPLE_SIZE,
        method_opt       => 'FOR ALL COLUMNS SIZE AUTO',
        cascade          => DBMS_STATS.AUTO_CASCADE,
        degree           => DBMS_STATS.DEFAULT_DEGREE
    );
END;
/
```

Một số giá trị `OPTIONS` thường dùng trong các thủ tục gather schema/database gồm:

- `GATHER`: thu thập theo phạm vi được chỉ định.
- `GATHER STALE`: tập trung vào object được đánh dấu có thống kê cũ.
- `GATHER EMPTY`: tập trung vào object chưa có thống kê.
- `GATHER AUTO`: để Oracle quyết định object nào cần gather theo trạng thái và chính sách hiện tại.

Hãy đối chiếu chữ ký và tùy chọn của thủ tục với phiên bản Oracle đang chạy. Khi schema rất lớn, nên cân nhắc thời gian, degree, mức độ song song và tải I/O trước khi gather trên diện rộng.

### 9.3. Thiết lập preferences

`DBMS_STATS` hỗ trợ đặt preference theo table, schema hoặc database. Cách này giúp quy định chính sách ổn định mà không phải truyền lại mọi tham số ở từng lần gọi.

Ví dụ đặt một số preference cho bảng `ORDERS`:

```sql
BEGIN
    DBMS_STATS.SET_TABLE_PREFS(
        ownname => 'APP',
        tabname => 'ORDERS',
        pname   => 'STALE_PERCENT',
        pvalue  => '10'
    );

    DBMS_STATS.SET_TABLE_PREFS(
        ownname => 'APP',
        tabname => 'ORDERS',
        pname   => 'METHOD_OPT',
        pvalue  => 'FOR ALL COLUMNS SIZE AUTO'
    );
END;
/
```

Một số preference thường được quản lý:

| Preference | Vai trò |
|---|---|
| `STALE_PERCENT` | Ngưỡng thay đổi dữ liệu để xem statistics là stale |
| `ESTIMATE_PERCENT` | Chính sách sampling |
| `METHOD_OPT` | Chính sách column statistics và histogram |
| `CASCADE` | Chính sách gather index statistics |
| `DEGREE` | Degree dùng khi gather |
| `GRANULARITY` | Cấp thống kê cho bảng partitioned |
| `INCREMENTAL` | Bật/tắt incremental statistics cho bảng partitioned phù hợp |
| `PUBLISH` | Quyết định statistics mới có được publish ngay hay giữ ở dạng pending |
| `NO_INVALIDATE` | Chính sách invalidation cursor sau khi publish |

Có thể xem giá trị preference bằng `DBMS_STATS.GET_PREFS`:

```sql
SELECT DBMS_STATS.GET_PREFS(
           pname   => 'STALE_PERCENT',
           ownname => 'APP',
           tabname => 'ORDERS'
       ) AS stale_percent
FROM dual;
```

Preference cấp table có thể ghi đè preference ở phạm vi rộng hơn. Khi chẩn đoán vì sao một lần gather có hành vi khác dự kiến, cần kiểm tra cả tham số truyền trực tiếp lẫn preference đang có hiệu lực.

## 10. Statistics stale và tự động thu thập

Statistics có thể trở nên stale khi dữ liệu thay đổi đáng kể sau lần gather gần nhất. Oracle theo dõi các thay đổi như insert, update và delete để xác định object cần cập nhật. Ngưỡng mặc định thường là 10% thay đổi, nhưng có thể được điều chỉnh bằng preference `STALE_PERCENT`.

Có thể xem trạng thái stale:

```sql
SELECT owner,
       table_name,
       partition_name,
       num_rows,
       last_analyzed,
       stale_stats
FROM dba_tab_statistics
WHERE owner = 'APP'
  AND object_type = 'TABLE'
ORDER BY table_name, partition_name;
```

Để xem thay đổi DML được ghi nhận trong monitoring view, có thể flush thông tin monitoring trước:

```sql
BEGIN
    DBMS_STATS.FLUSH_DATABASE_MONITORING_INFO;
END;
/
```

```sql
SELECT table_owner,
       table_name,
       inserts,
       updates,
       deletes
FROM dba_tab_modifications
WHERE table_owner = 'APP'
ORDER BY table_name;
```

`DBA_TAB_MODIFICATIONS` là thông tin monitoring phục vụ xác định thay đổi, không phải một bản ghi audit đầy đủ mọi câu DML. Số liệu có thể được cập nhật theo cơ chế monitoring và thời điểm flush; hãy kết hợp với `STALE_STATS`, `LAST_ANALYZED` và tình hình nạp dữ liệu thực tế.

Oracle có cơ chế automatic optimizer statistics collection thông qua các tác vụ bảo trì tự động trong maintenance window. Cơ chế này thường xử lý object cần thống kê theo chính sách hệ thống. Tuy nhiên, các bảng có bulk load lớn, partition mới, dữ liệu phân bố thay đổi đột ngột hoặc workload nhạy cảm vẫn cần được giám sát và có thể cần quy trình gather riêng.

Không nên gather lại toàn bộ database sau mỗi lần deploy ứng dụng. Hãy xác định object thay đổi, kiểm tra trạng thái statistics và chỉ thu thập trong phạm vi cần thiết. Gather statistics cũng tiêu thụ CPU, I/O và có thể ảnh hưởng plan của nhiều SQL.

## 11. Pending statistics và kiểm tra plan trước khi publish

Khi thay đổi statistics có rủi ro ảnh hưởng nhiều SQL, có thể thu thập dưới dạng **pending statistics**. Khi đó, statistics mới chưa được publish cho mọi session. Một session kiểm thử có thể bật sử dụng pending statistics để đánh giá plan.

Ví dụ cấu hình bảng không publish ngay:

```sql
BEGIN
    DBMS_STATS.SET_TABLE_PREFS(
        ownname => 'APP',
        tabname => 'ORDERS',
        pname   => 'PUBLISH',
        pvalue  => 'FALSE'
    );

    DBMS_STATS.GATHER_TABLE_STATS(
        ownname          => 'APP',
        tabname          => 'ORDERS',
        estimate_percent => DBMS_STATS.AUTO_SAMPLE_SIZE,
        method_opt       => 'FOR ALL COLUMNS SIZE AUTO',
        cascade          => DBMS_STATS.AUTO_CASCADE
    );
END;
/
```

Trong session kiểm thử:

```sql
ALTER SESSION SET optimizer_use_pending_statistics = TRUE;
```

Chạy các SQL đại diện và kiểm tra execution plan. Session không bật tham số này tiếp tục sử dụng published statistics. Khi kết quả kiểm thử đạt yêu cầu, có thể publish:

```sql
BEGIN
    DBMS_STATS.PUBLISH_PENDING_STATS(
        ownname => 'APP',
        tabname => 'ORDERS'
    );
END;
/
```

Nếu không muốn dùng pending statistics, có thể xóa chúng:

```sql
BEGIN
    DBMS_STATS.DELETE_PENDING_STATS(
        ownname => 'APP',
        tabname => 'ORDERS'
    );
END;
/
```

Sau khi hoàn tất, khôi phục preference `PUBLISH` theo chính sách của bảng. Pending statistics giúp kiểm tra plan trước khi công bố, nhưng test cần đại diện cho bind values, workload, session settings và môi trường thực tế. Một vài câu SQL đơn lẻ không đảm bảo mọi truy vấn đều có plan tốt hơn.

## 12. Khóa, lưu trữ và khôi phục statistics

### 12.1. Lock statistics

Trong một số trường hợp đặc biệt, DBA có thể khóa statistics của bảng hoặc schema để tránh automatic gather thay đổi chúng ngoài dự kiến:

```sql
BEGIN
    DBMS_STATS.LOCK_TABLE_STATS(
        ownname => 'APP',
        tabname => 'REFERENCE_CODES'
    );
END;
/
```

Mở khóa khi cần cập nhật:

```sql
BEGIN
    DBMS_STATS.UNLOCK_TABLE_STATS(
        ownname => 'APP',
        tabname => 'REFERENCE_CODES'
    );
END;
/
```

Lock statistics là công cụ kiểm soát thay đổi, không phải cách sửa lỗi cardinality lâu dài. Nếu dữ liệu đã thay đổi mạnh nhưng statistics bị khóa, optimizer có thể tiếp tục sử dụng số liệu cũ. Cần ghi rõ lý do lock, người chịu trách nhiệm và điều kiện mở khóa.

### 12.2. Statistics history và restore

Oracle lưu lịch sử statistics trong khoảng thời gian cấu hình. Nếu statistics mới làm plan xấu đi, DBA có thể khôi phục số liệu cũ nếu bản lịch sử vẫn còn trong retention.

Ví dụ khôi phục table statistics về thời điểm trước đó:

```sql
BEGIN
    DBMS_STATS.RESTORE_TABLE_STATS(
        ownname         => 'APP',
        tabname         => 'ORDERS',
        as_of_timestamp => SYSTIMESTAMP - INTERVAL '1' DAY
    );
END;
/
```

Thời điểm cần khôi phục phải nằm trong khoảng history còn khả dụng. Có thể xem thời điểm cũ nhất còn được giữ bằng API `DBMS_STATS.GET_STATS_HISTORY_AVAILABILITY` và xem retention bằng `DBMS_STATS.GET_STATS_HISTORY_RETENTION`. Việc tăng retention cần cân nhắc dung lượng lưu trữ trong SYSAUX và chính sách quản trị.

Restore statistics thay đổi dữ liệu optimizer statistics, không khôi phục dữ liệu bảng về trạng thái cũ và cũng không hoàn tác DML. Sau restore, cần kiểm tra plan và trạng thái cursor liên quan.

### 12.3. Export/import statistics bằng statistics table

Đối với thay đổi quan trọng, có thể lưu bản statistics riêng để đối chiếu hoặc chuyển sang môi trường khác. Tạo statistics table một lần:

```sql
BEGIN
    DBMS_STATS.CREATE_STAT_TABLE(
        ownname => 'APP',
        stattab => 'STATS_BACKUP'
    );
END;
/
```

Export statistics của bảng:

```sql
BEGIN
    DBMS_STATS.EXPORT_TABLE_STATS(
        ownname => 'APP',
        tabname => 'ORDERS',
        stattab => 'STATS_BACKUP',
        statid  => 'ORDERS_BEFORE_CHANGE'
    );
END;
/
```

Khi cần import lại:

```sql
BEGIN
    DBMS_STATS.IMPORT_TABLE_STATS(
        ownname => 'APP',
        tabname => 'ORDERS',
        stattab => 'STATS_BACKUP',
        statid  => 'ORDERS_BEFORE_CHANGE'
    );
END;
/
```

Statistics được export là một bản sao metadata. Khi chuyển statistics giữa môi trường có cấu trúc, dữ liệu, phiên bản hoặc đặc tính CPU/I/O khác nhau, không nên mặc định rằng plan sẽ phù hợp. Statistics table cũng cần được bảo vệ như dữ liệu quản trị và có quy trình backup/cleanup riêng.

## 13. Đối chiếu optimizer estimates với thực tế

Statistics chỉ hữu ích khi các ước lượng gần với thực tế. Khi một câu SQL chạy chậm, hãy kiểm tra execution plan và so sánh estimated rows với actual rows.

Có thể yêu cầu Oracle thu thập runtime row-source statistics cho một câu SQL bằng hint:

```sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       order_id,
       total_amount
FROM app.orders
WHERE order_status = 'RETURNED';
```

Sau khi chạy câu SQL trong cùng session, xem cursor vừa thực thi:

```sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL,
        NULL,
        'ALLSTATS LAST'
    )
);
```

Trong output, cần chú ý:

- `E-Rows`: số dòng optimizer ước lượng.
- `A-Rows`: số dòng thực tế ở row source, nếu runtime statistics đã được thu thập.
- `Starts`: số lần row source được khởi chạy.
- `Buffers`: số logical reads được ghi nhận cho row source.
- `Reads`: số physical reads được ghi nhận nếu có.
- `A-Time`: thời gian thực tế được ghi nhận cho row source theo định dạng của plan.

Nếu `E-Rows` chênh lệch lớn so với `A-Rows`, hãy kiểm tra column statistics, histogram, extended statistics, bind values, predicate, partition statistics và các điều kiện lọc. Nếu estimated rows gần đúng nhưng thời gian vẫn cao, vấn đề có thể nằm ở I/O, contention, join method, phân bổ tài nguyên, network hoặc các yếu tố runtime khác.

Không nên kết luận statistics là nguyên nhân duy nhất chỉ vì SQL chậm. Cũng cần kiểm tra plan hash, optimizer environment, bind peeking, adaptive cursor sharing, SQL profile/baseline nếu hệ thống có sử dụng và thay đổi dữ liệu kể từ lần gather.

## 14. Quy trình thực hành khi statistics không còn phù hợp

Khi phát hiện plan xấu hoặc ước lượng cardinality sai, có thể điều tra theo thứ tự sau:

1. **Xác định SQL và plan thực tế:** lấy SQL ID, child cursor, plan hash và runtime row-source statistics.
2. **Tìm bước lệch ước lượng:** so sánh `E-Rows` với `A-Rows` để xác định predicate hoặc join nào bắt đầu sai lệch.
3. **Kiểm tra table statistics:** xem `NUM_ROWS`, `BLOCKS`, `LAST_ANALYZED`, `STALE_STATS` và thống kê partition/global.
4. **Kiểm tra column statistics:** xem `NUM_DISTINCT`, `NUM_NULLS`, `DENSITY`, histogram và độ lệch dữ liệu thực tế.
5. **Kiểm tra index statistics:** xem `BLEVEL`, `LEAF_BLOCKS`, `DISTINCT_KEYS`, `CLUSTERING_FACTOR` và thời điểm gather.
6. **Kiểm tra tương quan cột:** nếu có nhiều predicate trên các cột liên quan, đánh giá nhu cầu extended statistics.
7. **Kiểm tra system statistics:** nếu cost CPU/I/O có vẻ không phù hợp, xác nhận system statistics phản ánh môi trường hiện tại.
8. **Gather trong phạm vi cần thiết:** dùng `DBMS_STATS` với sampling, histogram và cascade phù hợp.
9. **Kiểm thử trước khi publish nếu rủi ro cao:** dùng pending statistics và session riêng để so sánh plan.
10. **Theo dõi sau thay đổi:** kiểm tra SQL đại diện, cursor invalidation, thời gian chạy và workload tổng thể.

Một số sai lầm cần tránh:

- Gather statistics toàn database một cách tùy tiện sau mỗi lần deploy.
- Dùng `ESTIMATE_PERCENT => 100` cho mọi bảng mà không cân nhắc chi phí.
- Tạo histogram cho mọi cột hoặc đặt số bucket giống nhau cho tất cả cột.
- Rebuild index chỉ vì `BLEVEL` hoặc `CLUSTERING_FACTOR` có vẻ cao mà chưa phân tích workload.
- Chỉ kiểm tra thống kê global trong khi vấn đề nằm ở partition, hoặc ngược lại.
- Sửa trực tiếp bảng nội bộ của Oracle để thay đổi optimizer statistics.
- Dùng `V$SYSSTAT` như thể đó là system statistics của cost-based optimizer.
- Khóa statistics rồi quên cập nhật khi dữ liệu thay đổi.
- Publish statistics mới mà không kiểm tra những câu SQL quan trọng bị ảnh hưởng.

## 15. Checklist vận hành

Khi quản lý statistics cho một bảng nghiệp vụ quan trọng, DBA hoặc developer có thể dùng danh sách sau:

| Nội dung | Câu hỏi cần trả lời |
|---|---|
| Table statistics | `NUM_ROWS`, `BLOCKS` và `LAST_ANALYZED` có phản ánh dữ liệu hiện tại không? |
| Column statistics | Cột lọc/join có `NUM_DISTINCT`, `NUM_NULLS` và histogram phù hợp không? |
| Skew | Có giá trị hiếm hoặc phổ biến bất thường ảnh hưởng predicate không? |
| Column correlation | Các predicate có dùng nhiều cột tương quan cần extended statistics không? |
| Index statistics | BLEVEL, leaf blocks, distinct keys và clustering factor có hợp lý với cấu trúc dữ liệu không? |
| Partition | Partition stats và global stats đã được cập nhật tương ứng chưa? |
| System statistics | CPU/I/O statistics có đại diện cho phần cứng và workload hiện tại không? |
| Freshness | Object có bị stale hoặc bị khóa statistics không? |
| Execution plan | Estimated rows có gần actual rows ở các bước quan trọng không? |
| Change control | Có history hoặc bản export để khôi phục nếu plan xấu đi không? |

Statistics là một phần của quy trình vận hành database. Thu thập đúng loại, đúng phạm vi và đúng thời điểm giúp optimizer có dữ liệu tốt để lựa chọn execution plan. Khi plan có vấn đề, hãy dùng dictionary views và runtime plan statistics để tìm chính xác chỗ sai lệch, sau đó cập nhật hoặc thử nghiệm statistics có kiểm soát. Cách làm này giúp duy trì hiệu năng ổn định mà không phải dựa vào việc ép plan hoặc thay đổi cấu trúc database theo cảm tính.
