# Clustering factor, selectivity và số block cần truy cập trong Oracle Database

Khi Oracle thực thi một truy vấn có thể dùng index, optimizer phải ước lượng chi phí của hai hướng chính: đọc index rồi truy cập các dòng trong bảng qua ROWID, hoặc đọc trực tiếp nhiều block của bảng bằng full table scan. Một index có thể tìm đúng khóa rất nhanh nhưng vẫn không phải lựa chọn tốt nếu các dòng cần lấy nằm rải rác trên nhiều table block.

Ba khái niệm giúp giải thích quyết định đó:

- **Clustering factor:** thống kê mô tả mức độ tương quan giữa thứ tự khóa trong index và vị trí vật lý của các dòng trong table.
- **Selectivity:** tỷ lệ dòng ước lượng thỏa điều kiện lọc; điều kiện càng chỉ trả về ít dòng thì thường càng có tính chọn lọc cao.
- **Số block cần truy cập:** lượng công việc I/O ước lượng để đọc các leaf block của index và các table block chứa dòng kết quả, so với việc quét bảng.

Clustering factor thấp thường thuận lợi cho index range scan vì các ROWID theo thứ tự index có xu hướng nằm gần nhau trong cùng các table block. Clustering factor cao có thể khiến truy cập bảng qua ROWID trở thành nhiều lần đọc rời rạc. Selectivity cho biết cần bao nhiêu dòng; clustering factor giúp optimizer ước lượng việc lấy những dòng đó tốn bao nhiêu block. Cả hai cùng ảnh hưởng đến cost, nhưng không thể dùng một con số đơn lẻ để kết luận index luôn nhanh hơn full scan.

## 1. Index scan phải đọc những gì?

Một B-tree index trong Oracle có cấu trúc gồm root block, branch block nếu cây có nhiều tầng, và leaf block chứa khóa cùng ROWID. Khi truy vấn dùng index để tìm dòng trong table, quy trình thường là:

1. Đi từ root qua branch đến leaf block thích hợp.
2. Đọc các leaf block chứa khóa thỏa điều kiện.
3. Lấy ROWID từ index entry.
4. Dùng ROWID truy cập table block để lấy các cột không có sẵn trong index.

Ví dụ:

~~~sql
SELECT order_id,
       order_date,
       total_amount
FROM orders
WHERE customer_id = 100;
~~~

Nếu có index trên CUSTOMER_ID, Oracle có thể dùng index để tìm các ROWID tương ứng. Nhưng nếu ORDER_DATE và TOTAL_AMOUNT không nằm trong index, Oracle vẫn cần đọc table block chứa các dòng đó.

### 1.1 Index block và table block là hai phần công việc khác nhau

| Phần | Nội dung | Thống kê liên quan |
|---|---|---|
| Root/branch | Điều hướng đến vùng khóa cần tìm | BLEVEL |
| Leaf | Chứa index key và ROWID | LEAF_BLOCKS, DISTINCT_KEYS |
| Table | Chứa các dòng thực tế được lấy qua ROWID | BLOCKS, NUM_ROWS, CLUSTERING_FACTOR |

Một index có thể rất nhỏ, nhưng nếu mỗi ROWID dẫn đến một table block khác nhau thì phần table access vẫn tốn kém. Ngược lại, một index có nhiều leaf block nhưng truy vấn chỉ cần một vùng khóa nhỏ có thể vẫn hiệu quả.

### 1.2 Truy vấn có thể không cần quay lại table

Nếu mọi cột cần trả về và mọi cột cần kiểm tra đều có trong index, Oracle có thể đáp ứng truy vấn chỉ từ index. Đây thường được gọi là index-only access hoặc covering index trong cách diễn đạt phổ biến.

Ví dụ index:

~~~sql
CREATE INDEX ix_orders_customer_date
ON orders (customer_id, order_date);
~~~

Truy vấn chỉ lấy hai cột đó:

~~~sql
SELECT customer_id, order_date
FROM orders
WHERE customer_id = 100;
~~~

Oracle có thể không cần TABLE ACCESS BY INDEX ROWID. Trong trường hợp không truy cập table, clustering factor ít ảnh hưởng trực tiếp đến số table block phải đọc cho truy vấn này. Vẫn cần đọc index block và cân nhắc kích thước index.

## 2. Clustering factor là gì?

### 2.1 Định nghĩa

Clustering factor (CF) là thống kê của index, phản ánh số lần thứ tự ROWID trong index chuyển từ table block này sang table block khác khi duyệt index theo thứ tự khóa.

Hãy tưởng tượng đọc các index entry từ khóa nhỏ đến khóa lớn:

- Nếu nhiều entry liên tiếp trỏ đến các dòng trong cùng table block, số lần chuyển block ít.
- Nếu mỗi entry kế tiếp thường trỏ đến một table block khác, số lần chuyển block nhiều.

Clustering factor thấp cho thấy thứ tự vật lý của dòng trong table tương đối phù hợp với thứ tự khóa của index. Clustering factor cao cho thấy các dòng theo thứ tự index bị phân tán trên table.

### 2.2 Minh họa CF thấp

Giả sử index được sắp theo ORDER_ID và các dòng trong table cũng được lưu gần theo ORDER_ID:

~~~text
Thứ tự index key:  1   2   3   4   5   6   7   8
ROWID table block: A   A   A   B   B   B   C   C

Các lần chuyển block: A -> B -> C
Số lần chuyển xấp xỉ: 3
~~~

Khi index range scan đọc nhiều key liên tiếp, Oracle có thể lấy nhiều dòng từ một block trước khi chuyển sang block kế tiếp. CF thấp thường gần với số table block chứa dữ liệu.

### 2.3 Minh họa CF cao

Nếu các dòng bị phân tán:

~~~text
Thứ tự index key:  1   2   3   4   5   6   7   8
ROWID table block: A   F   C   H   B   G   D   E

Các lần chuyển block: A -> F -> C -> H -> B -> G -> D -> E
Số lần chuyển xấp xỉ: 8
~~~

Mỗi index entry có thể dẫn đến một block khác. Khi truy vấn cần nhiều dòng, table access qua ROWID có thể phát sinh nhiều lần đọc block rời rạc.

### 2.4 Khoảng giá trị thường gặp

Với index B-tree thông thường trên heap table, CF thường nằm trong khoảng từ gần số table block đến gần số dòng của bảng:

- CF gần TABLE BLOCKS: dữ liệu tương đối có thứ tự theo index key.
- CF gần NUM_ROWS: dữ liệu phân tán theo index key.

Đây là cách diễn giải trực quan, không phải một ngưỡng tuyệt đối để quyết định tốt/xấu. Cần xem quy mô bảng, kiểu truy vấn, selectivity, số cột cần lấy và execution plan.

### 2.5 CF không phải số block duy nhất

Không nên diễn giải clustering factor là số table block khác nhau mà index trỏ đến. Khi duyệt index, một block có thể được rời đi rồi được truy cập lại ở vị trí sau. Mỗi lần chuyển từ block này sang block khác đều góp phần vào CF.

Vì vậy CF có thể lớn hơn số table block vật lý của bảng. Nó gần với số lần chuyển block trong chuỗi ROWID theo thứ tự index hơn là số lượng block distinct.

## 3. Clustering factor được lưu ở đâu?

Oracle lưu clustering factor trong thống kê index. Có thể xem bằng USER_INDEXES:

~~~sql
SELECT index_name,
       table_name,
       blevel,
       leaf_blocks,
       distinct_keys,
       num_rows,
       clustering_factor,
       avg_leaf_blocks_per_key,
       avg_data_blocks_per_key,
       last_analyzed
FROM user_indexes
WHERE table_name = 'ORDERS'
ORDER BY index_name;
~~~

Các cột quan trọng:

| Cột | Ý nghĩa |
|---|---|
| BLEVEL | Số tầng branch trong cấu trúc index theo cách Oracle thống kê |
| LEAF_BLOCKS | Số leaf block của index |
| DISTINCT_KEYS | Số khóa index khác nhau |
| NUM_ROWS | Số index entry được thống kê |
| CLUSTERING_FACTOR | Mức độ chuyển table block theo thứ tự index |
| AVG_LEAF_BLOCKS_PER_KEY | Số leaf block trung bình cho một key |
| AVG_DATA_BLOCKS_PER_KEY | Số table block trung bình liên quan đến một key |
| LAST_ANALYZED | Thời điểm thu thập thống kê gần nhất |

Xem thống kê bảng:

~~~sql
SELECT table_name,
       num_rows,
       blocks,
       empty_blocks,
       avg_row_len,
       last_analyzed
FROM user_tables
WHERE table_name = 'ORDERS';
~~~

BLOCKS trong thống kê là số block được ghi nhận theo quá trình gather statistics, không nên đồng nhất máy móc với số block đã cấp phát trong segment hoặc số block hiện có dữ liệu trong mọi trường hợp.

## 4. Selectivity và cardinality

### 4.1 Selectivity là tỷ lệ dòng thỏa predicate

Selectivity của một điều kiện lọc có thể diễn đạt:

\[
\text{Selectivity} =
\frac{\text{Số dòng ước lượng thỏa điều kiện}}
{\text{Tổng số dòng trong tập đầu vào}}
\]

Ví dụ bảng có 1.000.000 dòng:

- Predicate trả 100 dòng: selectivity khoảng 0,0001 (0,01%).
- Predicate trả 100.000 dòng: selectivity khoảng 0,1 (10%).
- Predicate trả 800.000 dòng: selectivity khoảng 0,8 (80%).

Điều kiện trả ít dòng thường được gọi là highly selective. Để tránh nhầm thuật ngữ, trong bài này ta luôn nói rõ tỷ lệ hoặc số dòng ước lượng.

### 4.2 Cardinality là số dòng ước lượng

Cardinality là số dòng optimizer ước lượng một row source sẽ trả về. Với bảng có N dòng và predicate có selectivity S, cardinality cơ bản có thể hình dung:

\[
\text{Cardinality} \approx N \times S
\]

Ví dụ 1.000.000 dòng với selectivity 0,001 sẽ có cardinality ước lượng khoảng 1.000 dòng.

Cardinality ảnh hưởng đến cost của các bước tiếp theo: số ROWID, số lần table access, lượng dữ liệu join và khả năng chọn access path.

### 4.3 Selectivity của equality theo NDV

Nếu một cột có NUM_DISTINCT (NDV) giá trị khác nhau và phân bố gần đồng đều, ước lượng đơn giản cho predicate:

~~~sql
WHERE status_code = 10
~~~

là:

\[
\text{Selectivity} \approx \frac{1}{\text{NDV}}
\]

Nếu STATUS_CODE có 10 giá trị phân bố đều, mỗi giá trị có thể chiếm khoảng 10% dòng. Nhưng nếu một trạng thái chiếm 90% và các trạng thái còn lại rất ít, giả định đồng đều sẽ không chính xác.

### 4.4 Index selectivity và predicate selectivity

Hai cách dùng thuật ngữ thường bị trộn lẫn:

- Predicate selectivity: tỷ lệ dòng thỏa một điều kiện cụ thể.
- Tính chọn lọc của index key: mức độ phân biệt của khóa, thường xem qua DISTINCT_KEYS so với NUM_ROWS hoặc số dòng trung bình trên mỗi key.

Ví dụ:

~~~sql
SELECT index_name,
       num_rows,
       distinct_keys,
       CASE
         WHEN num_rows > 0
         THEN distinct_keys / num_rows
       END AS distinct_key_ratio
FROM user_indexes
WHERE table_name = 'ORDERS';
~~~

Với unique index trên cột không NULL, mỗi entry có một key riêng nên tỷ lệ distinct key thường gần 1. Với index không unique có nhiều dòng cùng key, tỷ lệ thấp hơn. Đây là chỉ báo về độ phân biệt của index key, không phải selectivity của mọi predicate kết hợp trên bảng.

## 5. Thống kê cột, histogram và phân bố dữ liệu

### 5.1 NUM_DISTINCT không kể hết câu chuyện

Giả sử cột STATUS có 3 giá trị:

| STATUS | Số dòng | Tỷ lệ |
|---|---:|---:|
| ACTIVE | 900.000 | 90% |
| PENDING | 90.000 | 9% |
| CLOSED | 10.000 | 1% |

NDV = 3. Nếu optimizer giả định đồng đều, mỗi giá trị có khoảng 33,3% dòng. Điều này sai rõ rệt đối với ACTIVE và CLOSED.

Histogram giúp optimizer mô tả skew của phân bố cột và ước lượng selectivity chính xác hơn cho một số predicate.

### 5.2 Xem column statistics

~~~sql
SELECT column_name,
       num_distinct,
       density,
       num_nulls,
       histogram,
       num_buckets,
       last_analyzed
FROM user_tab_col_statistics
WHERE table_name = 'ORDERS'
ORDER BY column_name;
~~~

Các thông tin như NUM_DISTINCT, NUM_NULLS, DENSITY và HISTOGRAM giúp hiểu optimizer đang có dữ liệu thống kê gì. Ý nghĩa chi tiết của DENSITY phụ thuộc loại histogram và phiên bản; không dùng một công thức duy nhất để tự thay thế mô hình ước lượng của optimizer.

### 5.3 Thu thập histogram khi cần

Có thể yêu cầu DBMS_STATS thu thập thống kê:

~~~sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname          => USER,
        tabname          => 'ORDERS',
        estimate_percent => DBMS_STATS.AUTO_SAMPLE_SIZE,
        method_opt       => 'FOR ALL COLUMNS SIZE AUTO',
        cascade          => TRUE
    );
END;
/
~~~

SIZE AUTO cho phép Oracle quyết định cột nào cần histogram dựa trên workload và thông tin thống kê theo chính sách. Không nên tạo histogram cho mọi cột theo thói quen; histogram có thể làm kế hoạch phụ thuộc giá trị bind và tăng độ phức tạp trong việc quản lý plan.

### 5.4 Bind variable và data skew

Một câu SQL:

~~~sql
SELECT order_id, total_amount
FROM orders
WHERE status = :p_status;
~~~

có thể được gọi với ACTIVE (rất nhiều dòng) hoặc CLOSED (rất ít dòng). Một access path tốt cho giá trị này có thể không tốt cho giá trị kia.

Oracle có các cơ chế như bind peeking và adaptive cursor sharing để xử lý một số tình huống bind selectivity khác nhau. Tuy nhiên, hành vi phụ thuộc phiên bản, thống kê, cursor và workload. Khi thấy cùng SQL có nhiều child cursor hoặc plan khác nhau, cần kiểm tra bind value, histogram và execution statistics.

### 5.5 Correlation giữa các cột

Nếu truy vấn:

~~~sql
WHERE region_id = 10
  AND status = 'CLOSED'
~~~

và REGION_ID có tương quan với STATUS, giả định độc lập giữa hai predicate có thể ước lượng cardinality sai. Extended statistics cho column group có thể giúp optimizer mô tả tương quan:

~~~sql
SELECT DBMS_STATS.CREATE_EXTENDED_STATS(
           USER,
           'ORDERS',
           '(REGION_ID, STATUS)'
       )
FROM dual;
~~~

Sau khi tạo extended statistics, cần gather stats phù hợp và xem lại cardinality trong execution plan. Không tạo column group cho mọi tổ hợp cột; chọn dựa trên predicate thực tế và bằng chứng ước lượng sai.

## 6. Clustering factor ảnh hưởng đến table access như thế nào?

### 6.1 Hai index có cùng selectivity vẫn có thể có cost khác nhau

Giả sử cùng một predicate trả 1.000 dòng:

- Index A có CF thấp: các dòng theo thứ tự index nằm trong tương đối ít table block.
- Index B có CF cao: các dòng theo thứ tự index rải trên nhiều table block.

Số dòng kết quả giống nhau, nhưng lượng table block cần truy cập có thể khác đáng kể. Index B có thể tạo nhiều random table access hơn.

### 6.2 CF thấp và index range scan

~~~text
Index entries theo key
  k1 -> block A
  k2 -> block A
  k3 -> block A
  k4 -> block B
  k5 -> block B
  k6 -> block C

Table access:
  A, B, C
~~~

Nhiều ROWID dẫn đến cùng block; block có thể được tái sử dụng trong buffer cache khi đọc các dòng gần nhau.

### 6.3 CF cao và index range scan

~~~text
Index entries theo key
  k1 -> block A
  k2 -> block X
  k3 -> block C
  k4 -> block Y
  k5 -> block B
  k6 -> block Z

Table access:
  A, X, C, Y, B, Z
~~~

Các truy cập có thể phân tán, tạo random I/O. Khi cardinality tăng, chi phí quay lại table có thể khiến full table scan rẻ hơn.

### 6.4 CF không trực tiếp bằng số block cho một predicate

Clustering factor được tính trên toàn bộ thứ tự index, còn truy vấn có thể chỉ quét một phần index. Optimizer ước lượng số table block cho predicate dựa trên nhiều thống kê và mô hình cost, trong đó có CF, cardinality, table blocks, index leaf blocks và các yếu tố khác.

Không dùng công thức máy móc:

~~~text
table blocks của truy vấn = clustering_factor * selectivity
~~~

để dự đoán chính xác mọi plan. Đây chỉ có thể là trực giác thô trong một số trường hợp. Oracle còn tính đến phân bố ROWID, số key, caching, batching, partition và chi phí CPU/I/O.

## 7. Ước lượng số block và so sánh access path

### 7.1 Index range scan

Chi phí khái niệm của index range scan có thể chia thành:

~~~text
Index access:
    root/branch traversal
  + leaf blocks cần đọc

Table access:
    các table block chứa ROWID thỏa predicate

Tổng chi phí:
    index work + table rowid work + CPU
~~~

Với truy vấn cần lấy cột ngoài index, table access có thể là phần chi phí lớn nhất.

### 7.2 Full table scan

Full table scan đọc các block của segment trong phạm vi cần quét, thường tận dụng multiblock I/O. Oracle có thể đọc nhiều block trong một thao tác I/O, tùy cấu hình, storage và execution plan.

Full scan có thể rẻ hơn index range scan khi:

- Predicate trả về tỷ lệ lớn số dòng.
- CF cao làm table access qua ROWID phân tán.
- Bảng nhỏ và có thể đọc nhanh trong ít I/O.
- Truy vấn cần phần lớn cột hoặc gần như toàn bộ dòng.
- Index có nhiều leaf block phải đọc và vẫn phải quay lại table.

### 7.3 Index range scan có thể rẻ hơn khi

- Predicate trả về ít dòng.
- Index key có tính chọn lọc tốt.
- CF thấp hoặc các dòng được lấy nằm trong ít block.
- Truy vấn chỉ cần các cột có trong index.
- Index có cấu trúc và thống kê phù hợp.

### 7.4 Không có ngưỡng selectivity cố định

Không có quy tắc phổ quát như “dưới 5% thì dùng index, trên 5% thì full scan”. Ngưỡng phụ thuộc:

- Clustering factor.
- Số block của bảng.
- Số leaf block và chiều cao index.
- Kích thước dòng và số cột cần lấy.
- MBRC và đặc điểm storage.
- Buffer cache và workload.
- Histogram, cardinality estimate và bind values.
- Partition pruning, parallelism và các predicate khác.

Optimizer chọn phương án có cost ước lượng thấp theo thống kê và tham số môi trường. Một plan hợp lý trên bảng nhỏ có thể khác plan tối ưu trên bảng lớn.

## 8. Ví dụ selectivity và CF cùng tác động

Giả sử bảng có 1.000.000 dòng, 20.000 table block và một index trên CUSTOMER_ID.

| Tình huống | Cardinality ước lượng | CF | Diễn giải |
|---|---:|---:|---|
| A | 100 dòng | 20.000 | Rất ít dòng; có thể lấy từ số block tương đối nhỏ |
| B | 100 dòng | 900.000 | Ít dòng nhưng ROWID có thể phân tán; vẫn có thể index, cần so cost |
| C | 300.000 dòng | 20.000 | Dòng có thể tập trung tốt, nhưng lượng dữ liệu lớn |
| D | 300.000 dòng | 900.000 | Nhiều dòng và truy cập phân tán; full scan có thể hấp dẫn |

Các con số chỉ minh họa xu hướng, không phải công thức tính cost. Tình huống B vẫn có thể có index range scan tốt vì chỉ 100 dòng; tình huống C không mặc định dùng index chỉ vì CF thấp.

Điểm cốt lõi:

- Selectivity/cardinality quyết định lượng dòng cần lấy.
- Clustering factor giúp ước lượng tính phân tán của table access theo index order.
- Số leaf/table block và kiểu I/O quyết định lượng công việc.
- Optimizer cân nhắc tổng cost, không tối ưu một thống kê riêng lẻ.

## 9. Index range scan, full scan và index-only access

| Access path | Công việc chính | Vai trò của CF |
|---|---|---|
| INDEX RANGE SCAN + TABLE ACCESS BY INDEX ROWID | Quét vùng key rồi lấy dòng trong table | Quan trọng vì quyết định mức độ phân tán của table access |
| INDEX RANGE SCAN chỉ trên index | Đọc index entry và trả cột có trong index | Ít quan trọng hơn vì không quay lại table |
| INDEX UNIQUE SCAN + TABLE ACCESS BY INDEX ROWID | Tìm một key duy nhất rồi lấy dòng | Thường chỉ một dòng; CF ít chi phối hơn |
| TABLE ACCESS FULL | Quét block của table | CF của index không quyết định trực tiếp |
| INDEX FAST FULL SCAN | Đọc toàn bộ index như cấu trúc dữ liệu, không bảo đảm thứ tự key | CF ít liên quan nếu không quay lại table |
| TABLE ACCESS BY INDEX ROWID BATCHED | Gom/batch ROWID để cải thiện truy cập table | Có thể giảm random access thực tế, nhưng không thay đổi thống kê CF |

### 9.1 BATCHED rowid access

Oracle có thể dùng TABLE ACCESS BY INDEX ROWID BATCHED để gom các ROWID rồi truy cập table block theo cách cải thiện locality. Cách này có thể giảm số lần chuyển block so với truy cập từng ROWID độc lập.

Batched access không có nghĩa clustering factor đã thấp hơn. CF là thống kê của quan hệ giữa thứ tự index và vị trí dòng; batching là cách thực thi có thể giảm chi phí table access cho một truy vấn.

### 9.2 Index unique scan

Nếu predicate khớp unique key:

~~~sql
SELECT *
FROM orders
WHERE order_id = 10001;
~~~

Oracle có thể dùng INDEX UNIQUE SCAN. Vì chỉ tìm tối đa một index entry, chi phí table access thường giới hạn ở dòng đó. CF toàn index ít quan trọng hơn so với một range scan trả hàng nghìn dòng.

### 9.3 Index fast full scan

INDEX FAST FULL SCAN đọc toàn bộ leaf block của index như một nguồn dữ liệu, thường dùng multiblock I/O và không bảo đảm thứ tự index. Nếu index chứa đủ cột cho truy vấn, nó có thể rẻ hơn full table scan vì segment index nhỏ hơn table. Đây là một access path khác với index range scan.

## 10. Tại sao index rebuild không tự sửa clustering factor?

Clustering factor mô tả mối quan hệ giữa thứ tự index key và vị trí ROWID trong table. Rebuild index sắp xếp lại cấu trúc index, nhưng không tự di chuyển các dòng của table sang block khác theo thứ tự key.

Vì vậy:

- REBUILD có thể thay đổi leaf block, blevel, phân bổ không gian và cấu trúc index.
- REBUILD không phải công cụ trực tiếp để sắp xếp lại dữ liệu heap table theo index key.
- CF thường không được cải thiện đáng kể chỉ bằng rebuild index nếu table row placement không thay đổi.

Nếu cần cải thiện CF, phải xem xét cách tổ chức lại dữ liệu table theo khóa truy cập quan trọng, chẳng hạn CTAS/reload theo thứ tự phù hợp, table move/reorganization hoặc lựa chọn cấu trúc khác. Sau khi thay đổi row placement, cần kiểm tra và rebuild/recreate index theo yêu cầu của thao tác.

### 10.1 Tổ chức lại table có đánh đổi

Một bảng có nhiều index với các thứ tự key khác nhau. Sắp xếp vật lý theo CUSTOMER_ID có thể cải thiện CF của index CUSTOMER_ID nhưng làm CF của index ORDER_DATE xấu hơn.

Không thể mặc định một heap table có thể được sắp xếp tối ưu cho mọi index cùng lúc. Hãy chọn access path quan trọng theo workload, tần suất truy vấn, độ chọn lọc và chi phí ghi.

### 10.2 Index-organized table

Với bảng có primary key là trục truy cập chủ đạo, index-organized table (IOT) lưu dữ liệu bảng trong cấu trúc B-tree theo primary key. IOT có thể phù hợp khi truy cập theo khóa chính chiếm ưu thế, nhưng secondary index, row overflow và workload cập nhật cần được cân nhắc riêng.

IOT là lựa chọn thiết kế storage, không phải một cách đơn giản để sửa CF của mọi index trên heap table.

## 11. Thu thập và làm mới optimizer statistics

### 11.1 Gather table và index statistics

DBMS_STATS có thể thu thập thống kê bảng và index:

~~~sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname          => USER,
        tabname          => 'ORDERS',
        estimate_percent => DBMS_STATS.AUTO_SAMPLE_SIZE,
        method_opt       => 'FOR ALL COLUMNS SIZE AUTO',
        cascade          => TRUE,
        degree           => DBMS_STATS.AUTO_DEGREE
    );
END;
/
~~~

CASCADE => TRUE yêu cầu thu thập thống kê index liên quan. AUTO_SAMPLE_SIZE và AUTO_DEGREE để Oracle chọn sampling/parallelism phù hợp theo phiên bản và môi trường.

### 11.2 Kiểm tra stats có stale không

~~~sql
SELECT table_name,
       num_rows,
       blocks,
       stale_stats,
       last_analyzed
FROM user_tab_statistics
WHERE table_name = 'ORDERS';
~~~

Thông tin stale giúp biết thống kê có thể đã cũ sau nhiều thay đổi. Stats stale không tự chứng minh optimizer đang chọn plan sai, nhưng là một dấu hiệu cần xem xét cùng execution plan và workload.

### 11.3 Không gather stats tùy tiện giữa giờ cao điểm

Thu thập stats có thể tiêu tốn CPU/I/O và làm thay đổi kế hoạch của nhiều SQL. Với hệ thống production:

- Xác định cửa sổ gather phù hợp.
- Kiểm tra thống kê hiện tại và mức thay đổi dữ liệu.
- Dùng DBMS_STATS thay vì ANALYZE TABLE COMPUTE STATISTICS cho optimizer statistics.
- Cân nhắc pending statistics và kiểm soát publish khi thay đổi plan có rủi ro.
- Theo dõi SQL plan sau khi publish stats.

### 11.4 Pending statistics

Oracle hỗ trợ thu thập pending statistics để thử đánh giá trước khi publish theo cấu hình phù hợp. Cách này giúp giảm rủi ro thay đổi plan ngoài ý muốn, nhưng cần DBA quản lý preference, session dùng pending stats và thời điểm publish.

Không dùng pending stats như một bước bắt buộc cho mọi lần gather; đây là công cụ kiểm soát thay đổi thống kê trong môi trường cần quản lý plan chặt.

## 12. Xem execution plan và số block thực tế

### 12.1 EXPLAIN PLAN chỉ cho kế hoạch ước lượng

~~~sql
EXPLAIN PLAN FOR
SELECT order_id, order_date, total_amount
FROM orders
WHERE customer_id = 100;

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
~~~

EXPLAIN PLAN cho biết plan được tạo cho câu lệnh theo môi trường và bind context tại thời điểm giải thích. Nó không cung cấp actual rows/buffers của lần chạy thực tế.

### 12.2 Thu thập runtime statistics

Có thể dùng GATHER_PLAN_STATISTICS:

~~~sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       order_id,
       order_date,
       total_amount
FROM orders
WHERE customer_id = 100;
~~~

Ngay sau khi chạy câu SQL:

~~~sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL,
        NULL,
        'ALLSTATS LAST +PREDICATE +COST'
    )
);
~~~

Trong plan, chú ý:

- E-Rows: số dòng optimizer ước lượng.
- A-Rows: số dòng thực tế ở row source.
- Buffers: logical reads, tức số buffer được truy cập.
- Reads: physical reads được ghi nhận cho row source theo format/runtime statistics.
- Operation: INDEX RANGE SCAN, TABLE ACCESS BY INDEX ROWID, TABLE ACCESS FULL...
- Predicate Information: điều kiện access và filter.

Nếu E-Rows khác xa A-Rows, cần điều tra thống kê, histogram, bind value, correlation hoặc predicate expression trước khi kết luận CF là nguyên nhân.

### 12.3 Buffers không đồng nghĩa số physical disk reads

Buffers phản ánh logical I/O. Một block có thể được đọc từ buffer cache và vẫn được tính là buffer get. Physical reads chỉ phát sinh khi cần lấy block từ storage theo trạng thái cache và cơ chế đọc.

Do đó:

- Nhiều buffer gets có thể gây CPU/latch overhead dù physical reads thấp.
- Physical reads phụ thuộc cache, workload và storage.
- So sánh plan cần cùng điều kiện cache/workload hoặc dùng phép đo đủ nhiều lần.

### 12.4 So sánh plan thực tế

Không chỉ nhìn dòng INDEX RANGE SCAN rồi kết luận tốt. Hãy xem cả TABLE ACCESS BY INDEX ROWID, A-Rows, Buffers, Reads và thời gian. Index range scan có thể đọc ít index block nhưng truy cập table rất nhiều block.

## 13. Ví dụ lab: hai index, hai clustering factor

Phần lab tạo một heap table có ORDER_ID tăng dần và CUSTOMER_ID lặp theo chu kỳ. Nếu dữ liệu được nạp gần theo ORDER_ID, index ORDER_ID có xu hướng có CF thấp; index CUSTOMER_ID có xu hướng có CF cao vì các dòng của cùng customer phân tán theo nhiều vùng của table.

Thứ tự vật lý cuối cùng phụ thuộc cách Oracle nạp dữ liệu, segment, parallelism và môi trường. Vì vậy phải đo CF sau khi gather stats; không coi thứ tự INSERT/CTAS là bảo đảm tuyệt đối về physical row order.

### 13.1 Tạo bảng lab

~~~sql
CREATE TABLE lab_orders AS
SELECT LEVEL AS order_id,
       MOD(LEVEL, 100) AS customer_id,
       MOD(LEVEL, 10) AS status_code,
       DATE '2026-01-01' + MOD(LEVEL, 365) AS order_date,
       CAST(LEVEL * 1.25 AS NUMBER(12,2)) AS total_amount,
       RPAD('X', 100, 'X') AS payload
FROM dual
CONNECT BY LEVEL <= 100000;
~~~

Tạo primary key hoặc index cho ORDER_ID:

~~~sql
ALTER TABLE lab_orders
ADD CONSTRAINT pk_lab_orders PRIMARY KEY (order_id);
~~~

Tạo index cho CUSTOMER_ID:

~~~sql
CREATE INDEX ix_lab_orders_customer
ON lab_orders (customer_id);
~~~

### 13.2 Thu thập statistics

~~~sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname          => USER,
        tabname          => 'LAB_ORDERS',
        estimate_percent => DBMS_STATS.AUTO_SAMPLE_SIZE,
        method_opt       => 'FOR ALL COLUMNS SIZE AUTO',
        cascade          => TRUE
    );
END;
/
~~~

### 13.3 Xem clustering factor của hai index

~~~sql
SELECT index_name,
       num_rows,
       distinct_keys,
       leaf_blocks,
       clustering_factor,
       blevel
FROM user_indexes
WHERE table_name = 'LAB_ORDERS'
ORDER BY index_name;
~~~

So sánh CF với NUM_ROWS và BLOCKS của bảng:

~~~sql
SELECT table_name,
       num_rows,
       blocks,
       avg_row_len
FROM user_tables
WHERE table_name = 'LAB_ORDERS';
~~~

Thông thường index ORDER_ID có xu hướng CF thấp hơn index CUSTOMER_ID trong mẫu nạp này. Nếu kết quả không như kỳ vọng, kiểm tra actual segment layout, stats và cách dữ liệu được tạo; điều đó là cơ hội để thấy CF được đo từ ROWID thực tế chứ không chỉ suy ra từ tên cột.

### 13.4 So sánh truy vấn theo ORDER_ID

~~~sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       order_id,
       customer_id,
       payload
FROM lab_orders
WHERE order_id BETWEEN 50000 AND 50100;
~~~

Hiển thị plan:

~~~sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL,
        NULL,
        'ALLSTATS LAST +PREDICATE +COST'
    )
);
~~~

Predicate theo ORDER_ID trả khoảng 101 dòng liên tiếp trong thứ tự key. Nếu physical layout phù hợp, table block cần truy cập thường có locality tốt.

### 13.5 So sánh truy vấn theo CUSTOMER_ID

~~~sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       order_id,
       customer_id,
       payload
FROM lab_orders
WHERE customer_id = 42;
~~~

Hiển thị plan bằng DBMS_XPLAN.DISPLAY_CURSOR như phần trước. Predicate này trả khoảng 1% dòng của bảng. Do các dòng cùng customer có thể nằm rải rác theo vị trí ORDER_ID, index access có thể phải truy cập nhiều table block.

Optimizer có thể chọn index range scan, batched rowid access hoặc full table scan tùy thống kê và cost. Không ép plan bằng hint trong lần đo cơ bản; mục tiêu là quan sát quyết định tự nhiên của optimizer.

### 13.6 Thử truy vấn chỉ lấy cột trong index

~~~sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       customer_id
FROM lab_orders
WHERE customer_id = 42;
~~~

Truy vấn chỉ cần CUSTOMER_ID, đã có trong index. Oracle có thể xử lý bằng index access mà không quay lại table. So sánh buffers với truy vấn lấy PAYLOAD để thấy chi phí table access có thể chi phối.

### 13.7 Thử thay đổi selectivity

So sánh:

~~~sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       order_id,
       payload
FROM lab_orders
WHERE customer_id = 42;
~~~

với:

~~~sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       order_id,
       payload
FROM lab_orders
WHERE customer_id BETWEEN 0 AND 49;
~~~

Predicate thứ hai có thể trả về khoảng một nửa bảng. Index range scan có thể không còn kinh tế; full scan có thể được chọn. Xem E-Rows/A-Rows và buffers thay vì dựa trên một tỷ lệ phần trăm cố định.

### 13.8 Dọn bảng lab

Chỉ xóa các đối tượng do bạn tạo trong schema lab sau khi đã xác nhận không còn cần dữ liệu. DDL có implicit commit:

~~~sql
DROP TABLE lab_orders PURGE;
~~~

Không chạy lệnh DROP trên bảng không thuộc lab của bạn.

## 14. Các cách cải thiện locality và clustering factor

### 14.1 Nạp dữ liệu theo thứ tự truy cập quan trọng

Nếu workload chủ yếu range scan theo một khóa, việc nạp dữ liệu theo khóa đó có thể giúp các dòng gần nhau hơn trong table. Tuy nhiên, thứ tự vật lý cần được đo lại sau load; SQL result order không phải hợp đồng bảo đảm vị trí block.

### 14.2 Table reorganization

CTAS/reload, table move hoặc công cụ reorganization có thể thay đổi vị trí vật lý của dòng. Khi tổ chức lại:

- Chọn khóa sắp xếp theo access path quan trọng.
- Đánh giá downtime/online availability và row movement.
- Xử lý index, constraint, trigger, grants, statistics và dependency.
- Gather stats sau khi hoàn thành.
- So sánh workload trước/sau.

Reorganization có thể cải thiện CF của một index nhưng làm xấu index khác. Không làm chỉ để tối ưu một báo cáo hiếm khi chạy.

### 14.3 Index rebuild không phải table reorganization

Rebuild index tổ chức lại segment index, không sắp xếp lại các dòng trong heap table theo key. Nếu CF cao do ROWID phân tán, rebuild index đơn thuần thường không giải quyết nguyên nhân.

### 14.4 Partitioning có thể giảm phạm vi dữ liệu

Partition pruning có thể giảm số partition/table block cần truy cập. Với local index, thống kê index theo partition giúp optimizer ước lượng trong phạm vi partition. Partitioning giải quyết phạm vi dữ liệu và quản trị; nó không tự động bảo đảm CF thấp cho mọi local index.

### 14.5 Chọn index phù hợp với workload

Index không chỉ có chi phí đọc:

- INSERT phải duy trì index entry.
- UPDATE cột index có thể phải thay đổi index.
- DELETE phải duy trì index và undo/redo.
- Nhiều index làm tăng storage và chi phí ghi.

Không thêm index chỉ để làm một truy vấn có vẻ nhanh hơn mà chưa đo tổng workload.

## 15. Những yếu tố khác ảnh hưởng số block thực tế

Clustering factor và selectivity là hai yếu tố quan trọng, nhưng số block thực tế còn phụ thuộc:

### 15.1 Buffer cache

Table block có thể đã ở buffer cache. Một lần truy cập logic không nhất thiết cần physical disk read. Tuy nhiên, buffer get vẫn có chi phí CPU và quản lý cache.

### 15.2 Multiblock read và storage

Full table scan thường có thể tận dụng multiblock reads. Index rowid access thường mang tính single-block/random access hơn, dù batching và storage có thể thay đổi chi phí.

### 15.3 Table width và số cột được chọn

SELECT ít cột có thể giảm dữ liệu cần đọc/di chuyển. Nếu index cover được truy vấn, không cần table access. Nếu cần nhiều cột ngoài index, table block access tăng.

### 15.4 Partition pruning

Predicate trên partition key có thể loại bỏ partition không cần đọc trước khi index/table access. Số block cần truy cập phải được xét trong phạm vi partition còn lại.

### 15.5 Parallel query

Full scan song song có thể giảm elapsed time bằng cách dùng nhiều process, nhưng tiêu tốn nhiều tài nguyên hơn. Không so sánh chỉ elapsed time mà bỏ qua CPU, I/O và ảnh hưởng đến workload đồng thời.

### 15.6 Compression và row migration/chaining

Compression, row migration và row chaining có thể thay đổi số block cần đọc để lấy một dòng. Clustering factor không mô tả toàn bộ các chi phí này. Khi một dòng trải trên nhiều block, table access có thể cần thêm I/O ngoài block chứa row header.

## 16. Lỗi và ngộ nhận thường gặp

| Lỗi/ngộ nhận | Thực tế | Cách xử lý |
|---|---|---|
| CF thấp nghĩa index có ít leaf block | CF đo locality giữa index key và table row placement | Xem riêng LEAF_BLOCKS và CF |
| CF là số table block duy nhất | CF đếm các lần chuyển block theo thứ tự index | Không đồng nhất CF với distinct block count |
| CF cao thì index vô dụng | Predicate rất chọn lọc hoặc index-only vẫn có thể hiệu quả | Đo cardinality và plan |
| Selectivity chỉ phụ thuộc NDV | Skew, histogram, NULL và correlation ảnh hưởng estimate | Kiểm tra column/extended stats |
| Predicate trả 5% luôn dùng index | Không có ngưỡng chung; CF và I/O model khác nhau | So sánh cost và actual runtime |
| Rebuild index sẽ làm CF thấp | Rebuild không sắp xếp lại heap table rows | Reorganize table nếu có căn cứ |
| ORDER BY khi SELECT đảm bảo row physical order | ORDER BY chỉ đảm bảo thứ tự kết quả trả về | Đo CF sau khi nạp và gather stats |
| Bảng có nhiều index đều có thể CF thấp | Một thứ tự vật lý không tối ưu cho mọi key order | Ưu tiên workload quan trọng |
| Buffers là physical disk reads | Buffers là logical reads | Xem cả Buffers và Reads |
| EXPLAIN PLAN cho biết actual I/O | Nó chủ yếu cho plan ước lượng | Dùng DISPLAY_CURSOR với runtime stats |
| E-Rows luôn bằng A-Rows | Cardinality estimate có thể sai | Điều tra stats, histogram, bind và correlation |
| Index range scan luôn nhanh hơn full scan | Table access qua ROWID có thể rất đắt | Xem toàn bộ plan |
| CF thay đổi theo predicate | CF là thống kê của index; predicate chỉ dùng một phần index | Phân biệt statistic và query estimate |
| Chỉ cần xem CF để chọn index | Cần thêm selectivity, leaf blocks, table blocks, cache và workload | Đánh giá tổng thể |

## 17. Checklist phân tích một truy vấn dùng index

Khi truy vấn chậm, có thể đi theo trình tự:

1. Xác định SQL thực tế, bind values và execution plan đang dùng.
2. Xem E-Rows và A-Rows ở từng row source.
3. Kiểm tra predicate access/filter và cardinality estimate.
4. Xem NUM_ROWS, BLOCKS của bảng và LEAF_BLOCKS, BLEVEL, DISTINCT_KEYS, CLUSTERING_FACTOR của index.
5. Kiểm tra column statistics, histogram, NULL và correlation.
6. Xác định truy vấn có cần quay lại table hay index có thể cover các cột.
7. Xem TABLE ACCESS BY INDEX ROWID có batching không và bao nhiêu buffers/reads.
8. So sánh với TABLE ACCESS FULL trên dữ liệu và workload đại diện.
9. Kiểm tra stats có stale hoặc thiếu histogram phù hợp không.
10. Nếu CF cao, xác định access path đó có đủ quan trọng để reorganization hay không.
11. Đánh giá chi phí ghi và storage nếu định thêm index hoặc thay đổi cấu trúc.
12. Sau thay đổi, gather stats và đo lại bằng runtime plan.

## 18. Bài tập tự luyện

**Câu 1 — Định nghĩa CF.** Vì sao clustering factor thấp thường thuận lợi cho index range scan?

Gợi ý: Nhiều index entry liên tiếp trỏ đến cùng hoặc các table block gần nhau, giảm số lần chuyển block khi lấy dòng.

**Câu 2 — CF không phải block count.** Một index có CF 80.000 và table có 10.000 block. Điều đó có nghĩa bảng có 80.000 block không?

Gợi ý: Không. CF có thể lớn hơn số block distinct vì cùng block có thể được truy cập lại sau khi đã chuyển sang block khác.

**Câu 3 — Selectivity.** Bảng có 2 triệu dòng, predicate ước lượng trả 2.000 dòng. Selectivity là bao nhiêu?

Gợi ý: 2.000 / 2.000.000 = 0,001, tức 0,1%.

**Câu 4 — NDV.** Cột có 20 giá trị khác nhau và phân bố đồng đều. Selectivity equality ước lượng đơn giản là bao nhiêu?

Gợi ý: Khoảng 1/20 = 5%; nếu phân bố lệch, histogram có thể làm estimate khác.

**Câu 5 — Hai index.** Hai index cùng trả 5.000 dòng, nhưng một index CF thấp và index kia CF gần NUM_ROWS. Vì sao cost có thể khác?

Gợi ý: Số table block phải truy cập qua ROWID có thể khác do locality.

**Câu 6 — Index-only.** Vì sao CF ít quan trọng hơn khi truy vấn chỉ cần các cột có trong index?

Gợi ý: Không cần quay lại table để lấy các cột còn thiếu.

**Câu 7 — Histogram.** Vì sao NDV=3 chưa đủ để ước lượng predicate STATUS='CLOSED'?

Gợi ý: Ba giá trị có thể phân bố lệch mạnh; histogram mô tả skew.

**Câu 8 — Rebuild.** Rebuild index có làm các dòng trong heap table nằm cạnh nhau theo index key không?

Gợi ý: Không. Rebuild tổ chức lại index segment, không sắp xếp lại table rows.

**Câu 9 — Plan.** E-Rows là 100 nhưng A-Rows là 100.000. Nên điều tra gì?

Gợi ý: Stats, histogram, bind peeking, correlation, predicate và dữ liệu skew.

**Câu 10 — Chọn access path.** Predicate trả 60% dòng, index có CF cao và truy vấn cần nhiều cột ngoài index. Vì sao full scan có thể rẻ hơn?

Gợi ý: Index cần đọc nhiều entry và quay lại nhiều table block; full scan có thể đọc block theo multiblock I/O.

## 19. Tổng kết

Clustering factor, selectivity và số block cần truy cập là các khái niệm liên kết khi Oracle optimizer đánh giá index access:

- **Clustering factor** mô tả mức độ chuyển table block khi duyệt ROWID theo thứ tự index key. CF thấp thường biểu thị locality tốt; CF cao biểu thị các dòng phân tán.
- **Selectivity** là tỷ lệ dòng thỏa predicate; cardinality là số dòng optimizer ước lượng. NDV, histogram, NULL và correlation ảnh hưởng estimate.
- **Index range scan** phải tính cả chi phí đọc leaf block và table block qua ROWID nếu truy vấn cần cột ngoài index.
- **Full table scan** có thể rẻ hơn khi truy vấn cần nhiều dòng hoặc CF cao làm random table access đắt.
- **Index-only access** giảm sự phụ thuộc vào CF vì không cần quay lại table.
- **DBMS_STATS** cung cấp thống kê cho optimizer; DBMS_XPLAN giúp so sánh estimated rows với actual rows, buffers và reads.
- **Index rebuild** không tự sắp xếp lại heap table. Muốn thay đổi locality phải xem xét cách tổ chức lại table và đánh đổi giữa các access path.

Không chọn index chỉ vì predicate có vẻ chọn lọc hoặc vì CF thấp. Hãy xem cardinality thực tế, số block, cột cần đọc, execution plan và workload tổng thể. Khi optimizer có thống kê phù hợp và access path được đánh giá bằng runtime evidence, quyết định giữa index range scan và full table scan sẽ có cơ sở hơn.
