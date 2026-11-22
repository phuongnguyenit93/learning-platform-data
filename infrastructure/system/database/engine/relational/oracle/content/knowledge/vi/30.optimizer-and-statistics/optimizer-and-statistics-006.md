# Histogram và dữ liệu phân bố lệch

Oracle Database sử dụng Cost-Based Optimizer (CBO) để lựa chọn cách thực thi câu SQL. Optimizer dựa vào thống kê như số hàng, số giá trị phân biệt, số giá trị NULL, kích thước block, thống kê index và phân bố dữ liệu để ước lượng số hàng sẽ thỏa điều kiện. Ước lượng này ảnh hưởng tới lựa chọn access path, join method, join order và nhiều quyết định khác.

Khi dữ liệu phân bố đều, thống kê tổng quát như NUM_DISTINCT và DENSITY có thể đủ để ước lượng predicate. Nhưng nếu dữ liệu phân bố lệch (skewed distribution), một số giá trị xuất hiện rất nhiều còn các giá trị khác xuất hiện rất ít, giả định phân bố đều có thể sai nghiêm trọng. Histogram bổ sung thông tin về phân bố giá trị để optimizer ước lượng selectivity và cardinality tốt hơn.

Ví dụ bảng ORDERS có 1.000.000 hàng:

- 990.000 hàng có STATUS = 'OPEN'.
- 10.000 hàng có STATUS = 'CANCELLED'.

Nếu optimizer chỉ biết cột có hai giá trị phân biệt và giả định chúng xuất hiện như nhau, nó có thể ước lượng mỗi giá trị chiếm khoảng một nửa bảng. Nhưng thực tế OPEN chiếm 99%, còn CANCELLED chỉ chiếm 1%. Histogram giúp optimizer nhận biết chênh lệch đó.

Bài học trình bày cách đọc dữ liệu phân bố, hiểu histogram, thu thập thống kê bằng DBMS_STATS, kiểm tra execution plan và xử lý các vấn đề liên quan bind variables, tương quan giữa cột và tính ổn định của plan.

## 1. Thống kê và Cost-Based Optimizer

Oracle CBO lựa chọn execution plan bằng cách ước lượng chi phí của nhiều phương án. Thống kê là đầu vào quan trọng cho các ước lượng này.

Một số thống kê thường gặp:

| Thống kê | Ý nghĩa |
|---|---|
| NUM_ROWS | Số hàng ước lượng của bảng |
| BLOCKS | Số block được thống kê cho bảng |
| AVG_ROW_LEN | Độ dài hàng trung bình |
| NUM_DISTINCT | Số giá trị phân biệt của cột |
| NUM_NULLS | Số hàng có giá trị NULL |
| DENSITY | Thống kê mật độ dùng trong ước lượng selectivity |
| LOW_VALUE / HIGH_VALUE | Giá trị thấp nhất/cao nhất được thống kê |
| HISTOGRAM | Loại histogram của cột |
| NUM_BUCKETS | Số bucket histogram |
| CLUSTERING_FACTOR | Mức độ tương quan giữa thứ tự index và vị trí hàng trong table |
| LAST_ANALYZED | Thời điểm thu thập thống kê gần nhất |

Thống kê được lưu trong data dictionary và có thể xem qua các view USER_*, ALL_* hoặc DBA_* tùy quyền.

Ví dụ xem thống kê bảng:

~~~sql
SELECT table_name,
       num_rows,
       blocks,
       avg_row_len,
       last_analyzed
FROM user_tables
WHERE table_name = 'ORDERS';
~~~

Xem thống kê cột:

~~~sql
SELECT table_name,
       column_name,
       num_distinct,
       num_nulls,
       density,
       histogram,
       num_buckets,
       last_analyzed
FROM user_tab_col_statistics
WHERE table_name = 'ORDERS'
ORDER BY column_name;
~~~

Optimizer không chỉ dựa vào histogram. Nó còn xét index, partition, system statistics, bind values, constraints, query transformations và nhiều yếu tố khác. Histogram chỉ cải thiện một phần thông tin về phân bố dữ liệu.

## 2. Dữ liệu phân bố đều và phân bố lệch

### 2.1 Phân bố đều (uniform distribution)

Giả sử bảng có 100.000 hàng và cột STATUS có 4 giá trị, mỗi giá trị xuất hiện 25.000 lần:

| STATUS | Số hàng | Tỷ lệ |
|---|---:|---:|
| NEW | 25.000 | 25% |
| OPEN | 25.000 | 25% |
| CLOSED | 25.000 | 25% |
| CANCELLED | 25.000 | 25% |

Đây là phân bố gần đều. Nếu không có histogram, optimizer có thể dùng giả định phân bố đều dựa trên số giá trị phân biệt để ước lượng một giá trị chiếm khoảng 1/4 số hàng.

### 2.2 Phân bố lệch (skewed distribution)

Một bảng khác có cùng 100.000 hàng và 4 giá trị:

| STATUS | Số hàng | Tỷ lệ |
|---|---:|---:|
| NEW | 2.000 | 2% |
| OPEN | 92.000 | 92% |
| CLOSED | 5.000 | 5% |
| CANCELLED | 1.000 | 1% |

Nếu optimizer giả định đều, nó có thể ước lượng mỗi giá trị khoảng 25.000 hàng. Sai số đối với OPEN và CANCELLED rất lớn.

Phân bố lệch thường xuất hiện ở:

- Cột trạng thái nghiệp vụ: ACTIVE/INACTIVE, OPEN/CLOSED.
- Cột loại giao dịch: một loại chiếm phần lớn.
- Cột tenant/customer: một số tenant có dữ liệu áp đảo.
- Cột vùng địa lý hoặc category: một số giá trị phổ biến.
- Cột cờ boolean mô phỏng bằng CHAR hoặc NUMBER.
- Cột thời gian được nhóm thành ngày/tháng có mật độ khác nhau.

### 2.3 Skew không chỉ là số lượng giá trị phân biệt

Một cột có hàng nghìn giá trị vẫn có thể lệch nếu vài giá trị xuất hiện rất thường xuyên. Ngược lại, cột chỉ có hai giá trị có thể phân bố gần 50/50 và không cần histogram để thể hiện khác biệt.

Do đó, NUM_DISTINCT thấp không tự động có nghĩa cột cần histogram. Cần xem tần suất thực tế và cách ứng dụng lọc cột đó.

## 3. Selectivity và cardinality

Hai khái niệm cần hiểu khi đọc execution plan:

- Selectivity: tỷ lệ hàng dự kiến thỏa một predicate.
- Cardinality: số hàng optimizer dự kiến nhận được tại một bước của plan.

Ước lượng khái quát:

~~~text
Cardinality ≈ Number of input rows × Selectivity
~~~

Ví dụ bảng có 100.000 hàng:

- Predicate có selectivity 1% → cardinality ước lượng khoảng 1.000 hàng.
- Predicate có selectivity 90% → cardinality ước lượng khoảng 90.000 hàng.

Cardinality ảnh hưởng tới:

- Index range scan hay full table scan.
- Nested loops hay hash join.
- Join order.
- Sort và aggregation strategy.
- Bộ nhớ dự kiến cho hash area/sort area.

Nếu cardinality sai nhiều, optimizer có thể chọn plan tốn kém.

### 3.1 Ví dụ giả định phân bố đều

Giả sử:

- Bảng có 100.000 hàng.
- Cột STATUS có 4 giá trị phân biệt.
- Không có histogram.

Ước lượng đơn giản theo phân bố đều:

~~~text
Selectivity ≈ 1 / NUM_DISTINCT
           ≈ 1 / 4
           ≈ 25%

Cardinality ≈ 100,000 × 25%
            ≈ 25,000 rows
~~~

Nếu predicate STATUS = 'CANCELLED' thực tế chỉ có 1.000 hàng, ước lượng 25.000 cao hơn thực tế 25 lần.

### 3.2 Histogram giúp ước lượng theo giá trị

Histogram lưu thông tin về tần suất hoặc ranh giới phân bố của các giá trị. Optimizer có thể dùng thông tin này để ước lượng khác nhau cho:

- Giá trị phổ biến (popular value).
- Giá trị hiếm (rare value).
- Predicate bằng một giá trị cụ thể.
- Predicate khoảng giá trị.

Vì vậy, hai predicate trên cùng một cột có thể có cardinality rất khác nhau.

## 4. Density và NUM_DISTINCT

NUM_DISTINCT là số giá trị khác nhau được thống kê cho cột. DENSITY là một thống kê optimizer sử dụng trong ước lượng selectivity; không nên coi nó luôn bằng đúng 1/NUM_DISTINCT khi histogram tồn tại hoặc trong mọi loại predicate.

Với mô hình không có histogram và phân bố đều, một cách hình dung cơ bản là:

~~~text
Density ≈ 1 / NUM_DISTINCT
~~~

Ví dụ NUM_DISTINCT = 10:

~~~text
Density ≈ 0.1
~~~

Nhưng khi có histogram, density có thể phản ánh cách ước lượng cho các giá trị không được biểu diễn riêng hoặc các trường hợp khác. Hãy đọc density cùng loại histogram và thống kê liên quan, không diễn giải nó như tần suất chính xác của mọi giá trị.

### 4.1 NUM_NULLS

Histogram thông thường mô tả phân bố các giá trị không NULL. NUM_NULLS lưu số hàng NULL riêng. Nếu ứng dụng lọc IS NULL, optimizer có thể dùng NUM_NULLS để ước lượng selectivity.

Không suy ra tần suất NULL từ endpoint của histogram. Hãy xem NUM_NULLS.

### 4.2 LOW_VALUE và HIGH_VALUE

LOW_VALUE/HIGH_VALUE cho biết miền giá trị được thống kê. Chúng giúp optimizer ước lượng một số range predicate. Nhưng chỉ hai giá trị biên không mô tả đầy đủ dữ liệu nằm giữa hai biên nếu phân bố lệch.

Histogram cung cấp thêm thông tin về phân bố bên trong miền.

## 5. Histogram là gì?

Histogram là cấu trúc thống kê mô tả phân bố các giá trị của một cột hoặc biểu thức để optimizer có thể ước lượng selectivity chính xác hơn giả định uniform.

Histogram không phải:

- Index.
- Bảng dữ liệu nghiệp vụ.
- Cơ chế sắp xếp dữ liệu.
- Cơ chế ép Oracle dùng index.
- Bảo đảm một execution plan cụ thể.

Histogram là thống kê. Nó có thể khiến optimizer chọn một plan khác vì cardinality ước lượng thay đổi.

### 5.1 Khi nào histogram có ích?

Histogram thường có ích khi:

- Cột có dữ liệu phân bố lệch.
- Cột xuất hiện trong predicate WHERE hoặc điều kiện JOIN phù hợp.
- Giá trị phổ biến và hiếm cần plan khác nhau.
- Sai lệch cardinality hiện tại ảnh hưởng lựa chọn plan.

Histogram ít có ích khi:

- Dữ liệu phân bố đều.
- Cột không được dùng trong predicate/join.
- Query không phụ thuộc giá trị cụ thể của cột.
- Bottleneck nằm ở I/O, lock hoặc thuật toán khác.
- Vấn đề chính là tương quan giữa nhiều cột chứ không phải phân bố riêng từng cột.

### 5.2 Histogram không làm thay đổi dữ liệu

Thu thập histogram không cập nhật giá trị trong bảng. Nó cập nhật thống kê trong data dictionary để optimizer dùng khi parse/optimize SQL.

Nếu dữ liệu thay đổi đáng kể sau khi thu thập histogram, thống kê có thể không còn đại diện cho dữ liệu hiện tại.

## 6. Các loại histogram trong Oracle

Oracle có nhiều loại histogram. Loại được tạo phụ thuộc phiên bản, số bucket yêu cầu, số giá trị phân biệt, độ lệch và thuật toán thu thập thống kê.

Các loại thường gặp trong data dictionary:

- NONE: không có histogram.
- FREQUENCY: frequency histogram.
- HEIGHT BALANCED: height-balanced histogram, thường gặp ở thống kê cũ/legacy.
- HYBRID: hybrid histogram.
- TOP-FREQUENCY: top-frequency histogram.

### 6.1 Frequency histogram

Frequency histogram phù hợp khi số giá trị phân biệt không vượt quá số bucket có thể tạo. Mỗi giá trị có thể được biểu diễn riêng, giúp optimizer biết tần suất từng giá trị.

Ví dụ cột STATUS:

| Giá trị | Số hàng |
|---|---:|
| OPEN | 92.000 |
| NEW | 2.000 |
| CLOSED | 5.000 |
| CANCELLED | 1.000 |

Nếu histogram có đủ bucket cho 4 giá trị, nó có thể biểu diễn tần suất từng giá trị. Optimizer có thông tin tốt hơn khi lọc từng status.

Frequency histogram thường phù hợp với cột có số giá trị phân biệt thấp và phân bố lệch.

### 6.2 Height-balanced histogram

Height-balanced histogram là cách biểu diễn histogram truyền thống, trong đó các bucket được xây dựng để chứa số hàng xấp xỉ tương đương. Một số giá trị lặp lại ở ranh giới bucket có thể biểu hiện giá trị phổ biến.

Loại này thường gặp trong thống kê được tạo bởi các phiên bản Oracle cũ hoặc trong một số trường hợp legacy. Từ Oracle 12c, Oracle bổ sung các loại histogram mới để cải thiện ước lượng cho dữ liệu lệch.

Không nên cố tạo height-balanced histogram mới bằng cách dựa vào các giả định cũ. Hãy để DBMS_STATS chọn loại phù hợp hoặc sử dụng policy có chủ đích theo phiên bản đang chạy.

### 6.3 Top-frequency histogram

Top-frequency histogram tập trung biểu diễn các giá trị phổ biến nhất khi số lượng giá trị phân biệt lớn hơn số bucket có thể cấp cho toàn bộ miền.

Ví dụ cột có hàng nghìn giá trị nhưng chỉ một nhóm nhỏ chiếm gần như toàn bộ số hàng. Histogram có thể dành bucket cho nhóm giá trị phổ biến và tóm tắt phần đuôi ít phổ biến.

Điều này giúp optimizer ước lượng tốt hơn cho các giá trị thường gặp mà không cần một bucket riêng cho mọi giá trị phân biệt.

### 6.4 Hybrid histogram

Hybrid histogram kết hợp thông tin ranh giới bucket với thông tin số lần lặp của endpoint. Nó giúp optimizer nhận diện các giá trị phổ biến trong cột có nhiều giá trị phân biệt hơn số bucket.

Hybrid histogram được Oracle giới thiệu từ dòng 12c để cải thiện ước lượng cho dữ liệu lệch, đặc biệt với equality predicate và các giá trị lặp nhiều.

### 6.5 So sánh các loại histogram

| Loại | Cách biểu diễn khái quát | Trường hợp thường gặp |
|---|---|---|
| NONE | Không lưu histogram | Phân bố đủ đều hoặc không được chọn tạo histogram |
| FREQUENCY | Biểu diễn tần suất từng giá trị | NDV thấp, số bucket đủ |
| HEIGHT BALANCED | Bucket có số hàng xấp xỉ bằng nhau | Histogram legacy/kiểu cũ |
| TOP-FREQUENCY | Tập trung vào nhóm giá trị phổ biến | NDV cao, một nhóm nhỏ chiếm phần lớn dữ liệu |
| HYBRID | Ranh giới bucket cùng endpoint repeat count | NDV cao và có giá trị phổ biến/lặp nhiều |

Chi tiết thuật toán và điều kiện chọn loại histogram thay đổi theo phiên bản Oracle và cách thu thập thống kê. Hãy xem cột HISTOGRAM trong data dictionary thay vì suy đoán chỉ từ số bucket.

## 7. Bucket và endpoint

Histogram chia thông tin phân bố thành bucket. Một bucket có thể mô tả một giá trị hoặc một vùng giá trị, tùy loại histogram.

Các metadata thường gặp trong USER_TAB_HISTOGRAMS:

- ENDPOINT_NUMBER: số thứ tự/tổng endpoint theo cách biểu diễn của histogram.
- ENDPOINT_VALUE: giá trị endpoint dạng số nội bộ.
- ENDPOINT_ACTUAL_VALUE: biểu diễn giá trị endpoint thực tế ở những phiên bản hỗ trợ.
- ENDPOINT_REPEAT_COUNT: số lần endpoint value lặp lại, hữu ích với hybrid histogram.

Ví dụ xem histogram:

~~~sql
SELECT table_name,
       column_name,
       endpoint_number,
       endpoint_value,
       endpoint_actual_value,
       endpoint_repeat_count
FROM user_tab_histograms
WHERE table_name = 'ORDERS'
  AND column_name = 'STATUS'
ORDER BY endpoint_number;
~~~

Các cột metadata khả dụng có thể khác theo phiên bản. Nếu view không có một cột cụ thể, kiểm tra ALL_TAB_COLUMNS/DBA_TAB_COLUMNS hoặc tài liệu của bản Oracle đang dùng.

### 7.1 Endpoint không phải một hàng dữ liệu

Endpoint là thông tin thống kê, không phải bản sao từng hàng trong bảng. Không thể dùng USER_TAB_HISTOGRAMS để khôi phục toàn bộ dữ liệu gốc.

### 7.2 Số bucket không nhất thiết bằng số giá trị phân biệt

Một histogram có thể dùng ít bucket hơn NUM_DISTINCT. Với loại histogram tóm tắt, nhiều giá trị được đại diện qua một bucket hoặc phần đuôi thống kê.

NUM_BUCKETS cần được đọc cùng HISTOGRAM và endpoint metadata.

## 8. Thu thập histogram bằng DBMS_STATS

Oracle cung cấp package DBMS_STATS để thu thập và quản lý thống kê optimizer.

Ví dụ thu thập thống kê bảng:

~~~sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname          => USER,
        tabname          => 'ORDERS',
        estimate_percent => DBMS_STATS.AUTO_SAMPLE_SIZE,
        method_opt       => 'FOR ALL COLUMNS SIZE AUTO',
        cascade          => TRUE,
        no_invalidate    => DBMS_STATS.AUTO_INVALIDATE
    );
END;
/
~~~

Ý nghĩa:

- ownname: schema sở hữu bảng.
- tabname: tên bảng.
- estimate_percent: tỷ lệ sample; AUTO_SAMPLE_SIZE để Oracle chọn cách lấy mẫu phù hợp.
- method_opt: policy thu thập histogram cho cột.
- cascade: thu thập thống kê index liên quan.
- no_invalidate: điều khiển invalidation cursor; AUTO_INVALIDATE để Oracle quyết định thời điểm phù hợp.

Trong production, quyền, thời điểm và tác động của gather stats cần được quản lý theo quy trình DBA.

### 8.1 SIZE AUTO

SIZE AUTO yêu cầu Oracle tự quyết định có tạo histogram hay không dựa trên thống kê, độ lệch và thông tin sử dụng cột được theo dõi trong workload.

Ví dụ:

~~~sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname    => USER,
        tabname    => 'ORDERS',
        method_opt => 'FOR ALL COLUMNS SIZE AUTO'
    );
END;
/
~~~

SIZE AUTO là lựa chọn thường dùng cho môi trường vận hành bình thường. Oracle không nhất thiết tạo histogram cho mọi cột lệch; thông tin usage và policy ảnh hưởng quyết định.

### 8.2 SIZE SKEWONLY

SIZE SKEWONLY yêu cầu Oracle tạo histogram cho các cột được đánh giá là lệch, không phụ thuộc cùng cách chọn cột dựa trên workload như AUTO.

~~~sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname    => USER,
        tabname    => 'ORDERS',
        method_opt => 'FOR ALL COLUMNS SIZE SKEWONLY'
    );
END;
/
~~~

SKEWONLY không có nghĩa mọi histogram được tạo chắc chắn sẽ cải thiện plan. Nó có thể tạo histogram cho cột không được truy vấn thường xuyên, nên cần xem xét phạm vi và tác động.

### 8.3 SIZE REPEAT

SIZE REPEAT yêu cầu giữ/thu thập lại histogram theo những cột đã có histogram trước đó. Nó có thể hữu ích trong quy trình refresh stats khi muốn duy trì lựa chọn histogram hiện hữu.

~~~sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname    => USER,
        tabname    => 'ORDERS',
        method_opt => 'FOR ALL COLUMNS SIZE REPEAT'
    );
END;
/
~~~

Hãy hiểu rõ policy hiện tại trước khi dùng REPEAT; nếu histogram cần được tạo mới cho một cột chưa từng có, REPEAT có thể không đáp ứng mục đích đó.

### 8.4 SIZE n

SIZE n chỉ định số bucket mong muốn cho histogram:

~~~sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname    => USER,
        tabname    => 'ORDERS',
        method_opt => 'FOR COLUMNS STATUS SIZE 254'
    );
END;
/
~~~

Ví dụ dùng 254 bucket theo cấu hình truyền thống. Số bucket tối đa và thuật toán histogram phụ thuộc phiên bản Oracle; không mặc định 254 là giới hạn chung cho mọi release hiện đại.

### 8.5 SIZE 1

SIZE 1 được dùng để không tạo histogram cho cột được chỉ định:

~~~sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname    => USER,
        tabname    => 'ORDERS',
        method_opt => 'FOR COLUMNS STATUS SIZE 1'
    );
END;
/
~~~

Thao tác này có thể hữu ích khi histogram gây plan instability hoặc không có lợi ích. Trước khi bỏ histogram, cần xác nhận plan và cardinality của workload liên quan.

### 8.6 Chỉ định một cột

Không nhất thiết áp dụng cùng policy cho mọi cột:

~~~sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname    => USER,
        tabname    => 'ORDERS',
        method_opt => 'FOR ALL COLUMNS SIZE AUTO ' ||
                      'FOR COLUMNS STATUS SIZE 20'
    );
END;
/
~~~

Khi khai báo policy riêng cho một cột, hãy kiểm tra cú pháp METHOD_OPT và hành vi override theo phiên bản Oracle đang dùng. Có thể tách lần gather hoặc dùng table preference để quản lý policy rõ ràng.

## 9. Column usage và quyết định SIZE AUTO

Oracle theo dõi cách các cột được sử dụng trong predicate, join và một số ngữ cảnh SQL. Thông tin usage hỗ trợ quyết định tự động về histogram và thống kê mở rộng.

Có thể xem báo cáo usage:

~~~sql
SELECT DBMS_STATS.REPORT_COL_USAGE(
    ownname => USER,
    tabname => 'ORDERS'
)
FROM dual;
~~~

Báo cáo giúp nhận biết cột nào được dùng trong:

- Equality predicate.
- Range predicate.
- Join predicate.
- GROUP BY hoặc các ngữ cảnh khác tùy báo cáo/version.

### 9.1 Chạy workload trước khi gather AUTO

Nếu một cột chưa từng xuất hiện trong workload được theo dõi, SIZE AUTO có thể chưa có đủ thông tin usage để quyết định tạo histogram cho cột đó.

Một quy trình thử nghiệm:

1. Chạy representative SQL workload.
2. Kiểm tra column usage.
3. Gather stats với SIZE AUTO.
4. Xem cột nào có histogram.
5. Kiểm tra plan của SQL quan trọng.

Không chạy một truy vấn duy nhất rồi kết luận AUTO đã quan sát mọi workload production.

### 9.2 Usage tracking không phải SQL workload repository

Column usage ghi nhận kiểu sử dụng cột theo cơ chế Oracle, không thay thế SQL monitoring, AWR, SQL tuning set hoặc log ứng dụng. Nó không cung cấp đầy đủ tần suất, bind distribution hay SLA của mọi câu SQL.

## 10. Ví dụ thực hành: bảng có phân bố STATUS lệch

Tạo bảng thử nghiệm:

~~~sql
CREATE TABLE orders_skew_demo AS
SELECT LEVEL AS order_id,
       CASE
           WHEN MOD(LEVEL, 100) = 0 THEN 'CANCELLED'
           ELSE 'OPEN'
       END AS status,
       TRUNC(SYSDATE) - MOD(LEVEL, 365) AS created_date,
       MOD(LEVEL, 1000) + 1 AS customer_id
FROM dual
CONNECT BY LEVEL <= 100000;
~~~

Kết quả:

- 100.000 hàng.
- 1.000 hàng CANCELLED.
- 99.000 hàng OPEN.

Kiểm tra phân bố:

~~~sql
SELECT status,
       COUNT(*) AS row_count,
       ROUND(COUNT(*) * 100 / SUM(COUNT(*)) OVER (), 2) AS pct
FROM orders_skew_demo
GROUP BY status
ORDER BY status;
~~~

Tạo index để thử access path:

~~~sql
CREATE INDEX ix_orders_skew_status
ON orders_skew_demo(status);
~~~

### 10.1 Thu thập thống kê không có histogram

~~~sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname    => USER,
        tabname    => 'ORDERS_SKEW_DEMO',
        method_opt => 'FOR ALL COLUMNS SIZE 1',
        cascade    => TRUE
    );
END;
/
~~~

Xem thống kê:

~~~sql
SELECT column_name,
       num_distinct,
       density,
       histogram,
       num_buckets
FROM user_tab_col_statistics
WHERE table_name = 'ORDERS_SKEW_DEMO'
  AND column_name = 'STATUS';
~~~

Không có histogram, optimizer có thể phải dựa vào giả định uniform và các thống kê tổng quát.

### 10.2 Thu thập frequency histogram

Vì STATUS chỉ có hai giá trị phân biệt, có thể yêu cầu số bucket đủ để biểu diễn chúng:

~~~sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname    => USER,
        tabname    => 'ORDERS_SKEW_DEMO',
        method_opt => 'FOR COLUMNS STATUS SIZE 10',
        cascade    => TRUE
    );
END;
/
~~~

Sau đó kiểm tra:

~~~sql
SELECT column_name,
       num_distinct,
       density,
       histogram,
       num_buckets
FROM user_tab_col_statistics
WHERE table_name = 'ORDERS_SKEW_DEMO'
  AND column_name = 'STATUS';
~~~

Với NDV thấp và đủ bucket, Oracle thường có thể tạo FREQUENCY histogram. Kiểm tra giá trị HISTOGRAM thực tế thay vì giả định.

### 10.3 Xem endpoint

~~~sql
SELECT endpoint_number,
       endpoint_value,
       endpoint_actual_value,
       endpoint_repeat_count
FROM user_tab_histograms
WHERE table_name = 'ORDERS_SKEW_DEMO'
  AND column_name = 'STATUS'
ORDER BY endpoint_number;
~~~

Tùy loại histogram và phiên bản, một số metadata có thể không có giá trị hoặc không xuất hiện theo cùng cách. Mục đích là quan sát loại histogram và endpoint mà Oracle thực sự lưu.

## 11. Histogram thay đổi ước lượng như thế nào?

Giả sử optimizer biết:

- NUM_ROWS = 100.000.
- NUM_DISTINCT = 2.
- Không có histogram.

Ước lượng uniform đơn giản cho mỗi giá trị là khoảng 50.000 hàng.

Nhưng phân bố thực:

| Giá trị | Actual rows |
|---|---:|
| OPEN | 99.000 |
| CANCELLED | 1.000 |

Khi histogram thể hiện tần suất, optimizer có thể ước lượng gần với:

| Predicate | Ước lượng có histogram (khái niệm) | Actual |
|---|---:|---:|
| STATUS = 'OPEN' | 99.000 | 99.000 |
| STATUS = 'CANCELLED' | 1.000 | 1.000 |

Đây là ví dụ minh họa cách histogram cải thiện thông tin phân bố. Ước lượng thực tế còn phụ thuộc sample, thống kê, predicate, bind, phiên bản và các transformation của optimizer.

### 11.1 Plan có thể khác giữa giá trị phổ biến và hiếm

Với STATUS = 'CANCELLED', index range scan có thể rẻ nếu chỉ cần một tỷ lệ nhỏ hàng và clustering factor phù hợp.

Với STATUS = 'OPEN', predicate trả về 99% bảng. Full table scan có thể rẻ hơn việc đọc index rồi truy cập table gần như toàn bộ hàng.

Histogram giúp optimizer hiểu selectivity khác nhau, từ đó cân nhắc access path khác nhau. Nó không bắt buộc Oracle dùng index.

### 11.2 Index không luôn tốt hơn full scan

Một index trên cột lệch có thể hữu ích cho giá trị hiếm nhưng kém phù hợp cho giá trị phổ biến. Điều này không có nghĩa index sai; nó có nghĩa chi phí phụ thuộc predicate cụ thể.

Khi đánh giá plan, xem:

- A-Rows và E-Rows.
- Buffers.
- Physical reads.
- Clustering factor.
- Số hàng thực tế cần truy cập.
- Các cột được SELECT.
- Join order và join method.

## 12. Xem execution plan và so sánh estimated/actual rows

Dùng GATHER_PLAN_STATISTICS trong truy vấn kiểm thử:

~~~sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       order_id,
       status
FROM orders_skew_demo
WHERE status = 'CANCELLED';
~~~

Sau khi fetch đầy đủ kết quả, xem cursor vừa chạy:

~~~sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL,
        NULL,
        'ALLSTATS LAST +PREDICATE +PEEKED_BINDS'
    )
);
~~~

Trong báo cáo:

- E-Rows: số hàng optimizer ước lượng.
- A-Rows: số hàng thực tế được xử lý ở operation.
- Starts: số lần operation được bắt đầu.
- Buffers: logical reads.
- Reads: physical reads được ghi nhận.
- Predicate Information: điều kiện được áp dụng.

Nếu E-Rows khác A-Rows nhiều lần, hãy điều tra thống kê, histogram, correlation, bind và predicate transformation.

### 12.1 Estimated rows khác actual rows ở đâu?

Ví dụ minh họa:

| Operation | E-Rows | A-Rows |
|---|---:|---:|
| Index range scan | 50.000 | 1.000 |
| Table access by rowid | 50.000 | 1.000 |

Sai lệch 50 lần có thể khiến optimizer đánh giá sai chi phí. Histogram có thể giúp cải thiện nếu nguyên nhân là phân bố lệch của cột STATUS.

### 12.2 EXPLAIN PLAN không thay thế actual plan

EXPLAIN PLAN cho biết plan ước lượng khi câu SQL được phân tích trong ngữ cảnh đó. Nó không luôn phản ánh child cursor thực tế, bind peeking, runtime row counts và waits.

Khi điều tra production, ưu tiên xem cursor đang chạy bằng DBMS_XPLAN.DISPLAY_CURSOR và các nguồn thống kê runtime được cấp quyền.

## 13. Histogram và bind variable peeking

Bind variables giúp tái sử dụng SQL cursor:

~~~sql
SELECT order_id
FROM orders_skew_demo
WHERE status = :status;
~~~

Khi hard parse, Oracle có thể peek giá trị bind đầu tiên để ước lượng selectivity. Nếu cột có histogram, giá trị bind có thể dẫn tới ước lượng rất khác nhau.

Ví dụ:

- Lần parse đầu bind STATUS = 'CANCELLED' (hiếm).
- Optimizer chọn plan phù hợp với lượng hàng nhỏ.
- Sau đó cursor được gọi lại với STATUS = 'OPEN' (phổ biến).
- Plan cũ có thể không còn tối ưu cho giá trị mới.

Đây là một nguyên nhân có thể gây plan khác nhau giữa các lần chạy hoặc giữa môi trường test và production.

### 13.1 Bind peeking không có nghĩa mọi lần execute đều hard parse

Oracle thường tái sử dụng cursor đã parse. Bind peeking xảy ra trong quá trình tối ưu hóa khi hard parse; không phải mỗi lần execute đều tối ưu lại toàn bộ câu SQL theo bind mới.

Nếu nhiều giá trị có selectivity khác nhau, một child cursor ban đầu có thể không phù hợp cho mọi giá trị.

### 13.2 Adaptive Cursor Sharing (ACS)

Adaptive Cursor Sharing cho phép Oracle nhận biết một câu SQL dùng bind có thể cần các child cursor khác nhau cho các vùng selectivity khác nhau.

Khái quát:

1. Cursor ban đầu được tối ưu dựa trên thông tin có sẵn, bao gồm bind peeking khi phù hợp.
2. Oracle theo dõi hành vi thực thi và selectivity của bind.
3. Nếu nhận thấy các giá trị bind có selectivity khác nhau đáng kể, cursor có thể trở thành bind-sensitive.
4. Oracle có thể tạo child cursor phù hợp với các vùng bind selectivity, và cursor có thể trở thành bind-aware.

ACS không bảo đảm tạo plan riêng cho mọi giá trị bind và không thay thế việc kiểm tra plan.

### 13.3 Kiểm tra bind sensitivity

Một số cột trong V$SQL:

~~~sql
SELECT sql_id,
       child_number,
       is_bind_sensitive,
       is_bind_aware,
       plan_hash_value,
       executions
FROM v$sql
WHERE sql_text LIKE 'SELECT order_id%ORDERS_SKEW_DEMO%';
~~~

Truy vấn ví dụ có thể cần điều chỉnh theo SQL_TEXT thực tế và quyền truy cập. V$SQL chứa cursor hiện còn trong shared pool; không phải lịch sử đầy đủ vĩnh viễn.

### 13.4 Không tắt bind peeking chỉ để chữa một query

Tắt hoặc thay đổi hành vi bind peeking ở phạm vi hệ thống có thể ảnh hưởng nhiều workload. Trước khi thay đổi:

- Xác định SQL_ID và child cursor.
- Kiểm tra giá trị bind và selectivity.
- Xem actual plan và execution statistics.
- Kiểm tra ACS có hoạt động không.
- Xem SQL Plan Management hoặc giải pháp SQL-specific nếu phù hợp.

Ưu tiên giải quyết ở phạm vi câu SQL hoặc thống kê liên quan thay vì thay đổi tham số toàn database mà chưa có đánh giá.

## 14. Histogram và SQL có literal

Nếu câu SQL dùng literal:

~~~sql
SELECT order_id
FROM orders_skew_demo
WHERE status = 'CANCELLED';
~~~

Optimizer nhìn thấy giá trị literal khi tối ưu hóa và có thể dùng histogram để ước lượng selectivity của giá trị đó.

Với bind:

~~~sql
WHERE status = :status
~~~

Optimizer có thể peek bind khi hard parse và sử dụng histogram tương ứng. Kết quả còn phụ thuộc cursor sharing, bind type, child cursor và ACS.

### 14.1 Literal không phải lúc nào cũng tốt hơn bind

Dùng literal khác nhau có thể tạo nhiều SQL text và tăng hard parse/shared pool pressure. Bind variables thường là lựa chọn tốt cho ứng dụng OLTP, nhưng dữ liệu lệch yêu cầu kiểm tra bind peeking và ACS.

Không bỏ bind variables chỉ để optimizer thấy giá trị, trừ khi có quyết định tuning cụ thể và đã cân nhắc tác động toàn hệ thống.

## 15. Histogram và range predicate

Histogram không chỉ có ích với equality predicate. Nó còn cung cấp thông tin về phân bố để optimizer ước lượng một số range predicate:

~~~sql
SELECT COUNT(*)
FROM orders_skew_demo
WHERE order_id BETWEEN 1000 AND 2000;
~~~

Với cột có phân bố không đều theo miền giá trị, histogram có thể giúp ước lượng số hàng trong khoảng.

Ví dụ cột CREATED_DATE có dữ liệu tập trung ở một số ngày nhất định hoặc có khoảng thời gian rỗng. Giả định phân bố đều từ LOW_VALUE tới HIGH_VALUE có thể không phản ánh dữ liệu thực.

Tuy nhiên:

- Cách ước lượng range phụ thuộc loại histogram và predicate.
- Histogram có số bucket hữu hạn nên không mô tả mọi vùng chính xác tuyệt đối.
- Biểu thức hoặc implicit conversion trên cột có thể làm optimizer khó dùng thống kê như dự kiến.
- Cần xem actual plan và cardinality thực tế.

## 16. Histogram không giải quyết tương quan giữa nhiều cột

Một vấn đề khác với skew là correlation (tương quan giữa cột).

Ví dụ bảng CUSTOMERS:

- COUNTRY_CODE = 'US' thường đi cùng STATE_CODE = 'CA', 'NY', ...
- STATE_CODE = 'CA' chỉ có ý nghĩa trong COUNTRY_CODE = 'US'.

Hai cột có phân bố riêng, nhưng predicate kết hợp:

~~~sql
WHERE country_code = 'US'
  AND state_code = 'CA'
~~~

có thể không độc lập. Nếu optimizer nhân selectivity của từng predicate như thể độc lập, cardinality có thể sai.

Histogram đơn cột mô tả phân bố của từng cột riêng biệt. Nó không mô tả đầy đủ phân bố kết hợp của cặp COUNTRY_CODE và STATE_CODE.

### 16.1 Extended statistics: column group

Oracle hỗ trợ extended statistics cho nhóm cột để mô tả quan hệ thống kê giữa các cột.

Tạo column group:

~~~sql
SELECT DBMS_STATS.CREATE_EXTENDED_STATS(
    ownname   => USER,
    tabname   => 'CUSTOMERS',
    extension => '(COUNTRY_CODE, STATE_CODE)'
)
FROM dual;
~~~

Sau đó gather stats:

~~~sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname => USER,
        tabname => 'CUSTOMERS',
        estimate_percent => DBMS_STATS.AUTO_SAMPLE_SIZE,
        method_opt => 'FOR ALL COLUMNS SIZE AUTO'
    );
END;
/
~~~

Column group statistics có thể giúp optimizer ước lượng predicate kết hợp tốt hơn khi các cột có tương quan.

### 16.2 Extended statistics không phải histogram nhiều chiều tùy ý

Column group statistics lưu thống kê mở rộng cho nhóm cột, thường bao gồm số giá trị phân biệt kết hợp và density. Nó không có nghĩa Oracle tạo một histogram đầy đủ cho mọi tổ hợp giá trị.

Hãy xem đây là thông tin bổ sung về correlation, không phải cách thay thế mọi histogram đơn cột.

### 16.3 Expression statistics

Nếu query thường dùng biểu thức:

~~~sql
WHERE UPPER(customer_name) = 'ALICE'
~~~

thống kê cột CUSTOMER_NAME nguyên bản có thể không phản ánh chính xác phân bố của UPPER(CUSTOMER_NAME). Có thể cân nhắc function-based index hoặc extended statistics cho expression tùy workload.

Tạo expression statistics:

~~~sql
SELECT DBMS_STATS.CREATE_EXTENDED_STATS(
    ownname   => USER,
    tabname   => 'CUSTOMERS',
    extension => '(UPPER(CUSTOMER_NAME))'
)
FROM dual;
~~~

Sau đó thu thập lại thống kê và kiểm tra plan. Cú pháp và khả năng áp dụng phụ thuộc phiên bản và loại biểu thức.

## 17. Histogram và partitioned tables

Với bảng partition, thống kê có thể được thu thập ở cấp:

- Table/global.
- Partition.
- Subpartition.

Dữ liệu giữa các partition có thể phân bố rất khác nhau. Ví dụ partition theo tháng, tháng hiện tại có nhiều OPEN nhưng partition cũ chủ yếu CLOSED.

Optimizer có thể cần global statistics và partition statistics để ước lượng đúng khi truy vấn:

- Một partition.
- Nhiều partition.
- Toàn bảng.

### 17.1 Global và partition-level histogram

Histogram ở từng partition có thể phản ánh phân bố cục bộ. Global histogram phản ánh phân bố trên toàn bảng. Một giá trị hiếm toàn cục có thể phổ biến trong một partition cụ thể.

Khi dùng partition pruning, thống kê partition phù hợp có thể quan trọng. Hãy xem cách thu thập global/partition stats, incremental statistics và granularity theo thiết kế bảng.

### 17.2 Incremental statistics

Với bảng partition lớn, incremental statistics có thể giảm chi phí duy trì global stats khi chỉ một số partition thay đổi, nếu cấu hình và phiên bản hỗ trợ.

Histogram và incremental statistics có các quy tắc riêng theo phiên bản; không tự giả định histogram global được hợp nhất chính xác chỉ vì partition stats đã được gather. Kiểm tra tài liệu Oracle và metadata sau khi gather.

## 18. Thống kê stale và dữ liệu thay đổi

Histogram phản ánh dữ liệu tại thời điểm gather. Nếu phân bố thay đổi đáng kể, histogram cũ có thể không còn chính xác.

Ví dụ:

- Trước đây 99% đơn hàng OPEN.
- Sau chiến dịch xử lý, phần lớn đơn hàng chuyển sang CLOSED.
- Histogram vẫn mô tả phân bố cũ.

Optimizer có thể tiếp tục ước lượng theo thống kê không còn đại diện.

### 18.1 Kiểm tra stale statistics

Có thể xem trạng thái thống kê bảng:

~~~sql
SELECT table_name,
       num_rows,
       stale_stats,
       last_analyzed
FROM user_tab_statistics
WHERE table_name = 'ORDERS';
~~~

STALE_STATS có thể được xác định dựa trên monitoring và preference của DBMS_STATS. Đây là chỉ báo hữu ích, không phải cam kết rằng mọi histogram đều chính xác tại mọi thời điểm.

### 18.2 Gather stats định kỳ

DBMS_STATS và cơ chế automatic statistics gathering có thể duy trì thống kê. DBA nên xác định:

- Tần suất thay đổi dữ liệu.
- Cửa sổ gather stats.
- Bảng/cột quan trọng.
- Mức độ stale chấp nhận được.
- Ảnh hưởng invalidation/reoptimization.
- Quy trình kiểm tra plan sau gather.

Không gather stats liên tục chỉ vì muốn dữ liệu luôn mới; gather stats cũng tiêu tốn tài nguyên và có thể ảnh hưởng cursor/plan.

## 19. Histogram có thể làm plan thay đổi

Khi histogram được thêm hoặc thay đổi, selectivity ước lượng có thể khác. Optimizer có thể chọn:

- Index range scan thay vì full scan.
- Full scan thay vì index access.
- Nested loops thay vì hash join.
- Hash join thay vì nested loops.
- Join order khác.

Plan mới có thể tốt hơn cho một giá trị nhưng kém hơn cho giá trị khác, đặc biệt khi dùng bind variables.

### 19.1 Plan regression sau gather stats

Sau khi gather stats:

- SQL có thể hard parse lại.
- Cursor có thể bị invalidation theo policy.
- Optimizer có thể tạo child cursor/plan mới.
- Histogram có thể thay đổi selectivity.

Vì vậy, gather stats là một thay đổi có thể tác động execution plan. Với hệ thống quan trọng, cần theo dõi SQL có thời gian thực thi hoặc tài nguyên tăng sau stats refresh.

### 19.2 Pending statistics

Oracle hỗ trợ pending statistics trong một số quy trình để kiểm tra thống kê mới trước khi publish cho toàn workload. Có thể dùng DBMS_STATS preferences và SET_TABLE_PREFS/SET_SCHEMA_PREFS tùy cấu hình, sau đó kiểm tra bằng session dùng pending stats.

Quy trình pending stats thường cần DBA thiết lập:

1. Bật publish preference phù hợp.
2. Gather stats thành pending.
3. Dùng session với optimizer_use_pending_statistics để kiểm thử.
4. So sánh plan/kết quả.
5. Publish hoặc discard theo quy trình.

Không bật pending statistics trong production nếu chưa hiểu cách ứng dụng và session nhìn thấy thống kê.

### 19.3 Restore statistics

DBMS_STATS có khả năng lưu và khôi phục thống kê trong một khoảng retention được cấu hình. Trước thay đổi lớn, DBA có thể export stats vào statistics table hoặc dùng cơ chế restore stats phù hợp.

Ví dụ tạo statistics table:

~~~sql
BEGIN
    DBMS_STATS.CREATE_STAT_TABLE(
        ownname => USER,
        stattab => 'STATS_BACKUP'
    );
END;
/
~~~

Export stats:

~~~sql
BEGIN
    DBMS_STATS.EXPORT_TABLE_STATS(
        ownname => USER,
        tabname => 'ORDERS',
        stattab => 'STATS_BACKUP',
        cascade => TRUE
    );
END;
/
~~~

Đây là cơ chế quản trị cần quyền và không thay thế backup dữ liệu. Kiểm tra đúng chữ ký procedure và retention theo phiên bản Oracle đang dùng.

## 20. Histogram và các predicate khó

Không phải mọi predicate đều dùng histogram theo cách đơn giản.

### 20.1 Function trên cột

~~~sql
WHERE UPPER(status) = 'OPEN'
~~~

Histogram trên STATUS không nhất thiết phản ánh trực tiếp biểu thức UPPER(STATUS). Có thể cần expression statistics hoặc function-based index.

### 20.2 Implicit conversion

~~~sql
WHERE numeric_column = '100'
~~~

Kiểu bind/literal không phù hợp có thể khiến Oracle chuyển đổi dữ liệu. Nếu hàm chuyển đổi áp lên cột, index và thống kê có thể không được sử dụng như mong đợi.

Hãy dùng bind đúng kiểu và tránh implicit conversion.

### 20.3 LIKE

Histogram không phải giải pháp chung cho mọi LIKE predicate. Selectivity còn phụ thuộc pattern, wildcard đầu chuỗi, collation và khả năng dùng index.

Ví dụ:

~~~sql
WHERE customer_name LIKE 'AL%'
~~~

khác với:

~~~sql
WHERE customer_name LIKE '%AL%'
~~~

Hãy xem plan và thống kê thực tế.

### 20.4 IS NULL

Số lượng NULL được lưu riêng trong NUM_NULLS. Không giả định histogram endpoint chứa các hàng NULL.

## 21. Cách quyết định cột nào cần histogram

Không nên tạo histogram hàng loạt cho mọi cột. Xem từng cột theo các câu hỏi:

1. Dữ liệu có thực sự lệch không?
2. Cột có được dùng trong WHERE/JOIN không?
3. Giá trị khác nhau có selectivity khác nhau đáng kể không?
4. Cardinality hiện tại có sai và ảnh hưởng plan không?
5. Query dùng literal hay bind?
6. Có correlation với cột khác không?
7. Thống kê có thường stale không?
8. Histogram mới có làm plan ổn định hơn hay tạo plan sensitivity?

Một bảng đánh giá:

| Cột | Skew | Được lọc? | Sai cardinality? | Hướng xử lý |
|---|---|---|---|---|
| STATUS | Cao | Có | Có | Thử histogram |
| COUNTRY_CODE | Trung bình | Có | Có với STATE_CODE | Xem histogram và column group |
| CREATED_BY | Cao | Không | Không ảnh hưởng query | Chưa cần histogram |
| IS_ACTIVE | Gần đều | Có | Không | Có thể không cần |
| CUSTOMER_ID | Nhiều NDV, lệch tenant | Có | Có | Thử hybrid/top-frequency và xem correlation |

## 22. Cách xem metadata histogram

### 22.1 Thống kê cột

~~~sql
SELECT column_name,
       num_distinct,
       density,
       num_nulls,
       histogram,
       num_buckets,
       last_analyzed
FROM user_tab_col_statistics
WHERE table_name = 'ORDERS_SKEW_DEMO';
~~~

### 22.2 Endpoint

~~~sql
SELECT column_name,
       endpoint_number,
       endpoint_value,
       endpoint_actual_value,
       endpoint_repeat_count
FROM user_tab_histograms
WHERE table_name = 'ORDERS_SKEW_DEMO'
ORDER BY column_name, endpoint_number;
~~~

### 22.3 Thống kê bảng

~~~sql
SELECT table_name,
       num_rows,
       blocks,
       stale_stats,
       last_analyzed
FROM user_tab_statistics
WHERE table_name = 'ORDERS_SKEW_DEMO';
~~~

### 22.4 Index statistics

~~~sql
SELECT index_name,
       num_rows,
       distinct_keys,
       leaf_blocks,
       clustering_factor,
       last_analyzed
FROM user_indexes
WHERE table_name = 'ORDERS_SKEW_DEMO';
~~~

Đọc các thống kê cùng nhau. Histogram không quyết định access path một mình; clustering factor, kích thước table, selectivity và số cột cần lấy cũng quan trọng.

## 23. So sánh plan trước và sau histogram

Một thí nghiệm có kiểm soát:

1. Ghi nhận thống kê hiện tại.
2. Chạy query với giá trị phổ biến và hiếm.
3. Thu thập actual plan và A-Rows/E-Rows.
4. Gather stats với SIZE 1 để loại histogram.
5. Chạy lại cùng workload và lưu plan.
6. Gather stats với histogram policy.
7. Chạy lại cùng workload.
8. So sánh estimated rows, actual rows, buffers, CPU và elapsed.
9. Kiểm tra nhiều giá trị bind, không chỉ một giá trị.

Không chỉ so sánh plan hash. Hai plan khác nhau chưa chắc một plan nhanh hơn; cần đo runtime và resource.

### 23.1 Không flush shared pool trong production để benchmark

Flush shared pool hoặc buffer cache làm thay đổi trạng thái toàn hệ thống và có thể ảnh hưởng workload khác. Chỉ thực hiện trong môi trường thử nghiệm được kiểm soát và khi có lý do rõ ràng.

## 24. Các chiến lược xử lý bind và skew

Khi một cột có giá trị phổ biến và hiếm, một SQL dùng bind có thể cần nhiều plan.

Các hướng xem xét:

- Thu thập histogram thích hợp.
- Xác nhận bind peeking và Adaptive Cursor Sharing.
- Xem child cursor và bind selectivity.
- Dùng SQL Plan Management khi cần kiểm soát plan theo quy trình.
- Tách câu SQL cho các trường hợp nghiệp vụ có selectivity khác nhau nếu thiết kế ứng dụng cho phép và có cơ sở đo.
- Tránh hard-code literal hàng loạt làm tăng parse.

Không có một giải pháp đúng cho mọi hệ thống. Chọn cách xử lý dựa trên SQL_ID, workload và plan thực tế.

## 25. Ví dụ dữ liệu tenant lệch

Giả sử bảng EVENTS có TENANT_ID:

- Tenant 1 có 5 triệu hàng.
- Tenant 2 có 100.000 hàng.
- Tenant 3 có 5.000 hàng.
- Hàng nghìn tenant khác chỉ có vài trăm hàng.

Query:

~~~sql
SELECT *
FROM events
WHERE tenant_id = :tenant_id;
~~~

Một plan dùng index có thể tốt cho tenant nhỏ nhưng không tốt cho tenant lớn. Histogram có thể giúp optimizer nhận ra một số tenant phổ biến.

Tuy nhiên, nếu query còn lọc EVENT_TYPE và CREATED_AT, phân bố kết hợp có thể quan trọng hơn phân bố TENANT_ID riêng lẻ. Cần xem extended stats, partitioning và index composite theo workload.

### 25.1 Một index không thể tối ưu mọi tenant

Index:

~~~sql
CREATE INDEX ix_events_tenant
ON events(tenant_id);
~~~

có thể phù hợp với tenant nhỏ nhưng có thể phải truy cập quá nhiều rowid với tenant lớn. Một full scan hoặc partition access có thể rẻ hơn cho tenant lớn.

Histogram giúp optimizer ước lượng selectivity, còn quyết định index phụ thuộc cost model và các thống kê khác.

## 26. Histogram và cột thời gian

Cột ngày/giờ có thể có phân bố không đều:

- Nhiều hàng trong vài ngày gần nhất.
- Ít hàng trong các tháng cũ.
- Một số ngày có batch import lớn.
- Một số thời kỳ không có dữ liệu.

Histogram có thể giúp ước lượng range predicate:

~~~sql
WHERE created_at >= TIMESTAMP '2026-11-01 00:00:00'
  AND created_at <  TIMESTAMP '2026-12-01 00:00:00'
~~~

Nhưng cột thời gian thường có NDV lớn và liên tục tăng. Hãy cân nhắc partitioning, incremental stats, high/low values và cách query theo range. Histogram không thay thế thiết kế partition hoặc index.

## 27. Rủi ro khi tạo histogram quá nhiều

Tạo histogram cho mọi cột có thể gây:

- Tăng chi phí gather statistics.
- Tăng metadata thống kê.
- Thay đổi selectivity estimate của nhiều SQL.
- Tăng plan sensitivity với bind variables.
- Plan regression sau stats refresh.
- Khó kiểm soát nguyên nhân khi plan thay đổi.

Histogram cần có mục tiêu rõ ràng: sửa sai lệch cardinality có tác động thực tế.

## 28. Quy trình vận hành thống kê và histogram

Một quy trình thực tế:

1. Theo dõi SQL chậm hoặc có cardinality misestimate.
2. Xác định predicate và cột liên quan.
3. Kiểm tra dữ liệu thực tế, NUM_DISTINCT, density, num_nulls và histogram.
4. Kiểm tra column usage và workload.
5. Xem actual execution plan.
6. Xác định vấn đề là skew đơn cột, correlation, stale stats hay bind sensitivity.
7. Thử histogram/extended stats trong môi trường kiểm thử.
8. Chạy workload với cả giá trị phổ biến và hiếm.
9. Đo plan, buffers, CPU, elapsed và kết quả.
10. Triển khai theo phạm vi và theo dõi plan sau gather.

## 29. Những lỗi thường gặp

| Sai lầm | Hệ quả | Cách xử lý |
|---|---|---|
| Tạo histogram cho mọi cột | Thống kê phức tạp và plan sensitivity | Dùng SIZE AUTO hoặc policy theo workload |
| Cho rằng NDV thấp luôn cần histogram | Cột có thể phân bố đều | Đo tần suất thực tế |
| Cho rằng histogram ép dùng index | Optimizer vẫn so sánh cost | Xem plan và cardinality |
| Chỉ xem NUM_DISTINCT | Bỏ qua phân bố từng giá trị | Kiểm tra HISTOGRAM và endpoint |
| Dùng SIZE SKEWONLY cho toàn schema không đánh giá | Histogram trên cột không quan trọng | Xác định phạm vi và workload |
| Gather stats nhưng không kiểm tra plan | Có thể gây regression | So sánh actual plan trước/sau |
| Chỉ thử một bind value | Bỏ qua giá trị phổ biến/hiếm | Test nhiều vùng selectivity |
| Tắt bind peeking toàn hệ thống | Ảnh hưởng workload khác | Điều tra SQL_ID và ACS trước |
| Dùng histogram để xử lý correlation | Thống kê đơn cột không đủ | Tạo extended column group stats |
| Dùng histogram cũ khi dữ liệu đã đổi | Cardinality vẫn sai | Theo dõi stale stats và gather phù hợp |
| Nhầm endpoint với từng hàng | Diễn giải sai metadata | Hiểu bucket và loại histogram |
| Dùng EXPLAIN PLAN làm actual plan | Không thấy runtime row count | Dùng DISPLAY_CURSOR với ALLSTATS LAST |
| Coi density luôn bằng 1/NDV | Sai khi có histogram/các trường hợp đặc biệt | Đọc density trong ngữ cảnh thống kê |
| Thấy plan hash đổi là kết luận regression | Plan khác chưa chắc chậm hơn | Đo runtime và resource |

## 30. Bài thực hành tự kiểm tra

Các bài tập nên chạy trong schema thử nghiệm, không thay đổi thống kê production.

### Bài 1 — Phân bố đều

Tạo bảng có 100.000 hàng và bốn giá trị STATUS xuất hiện gần bằng nhau. Gather stats không histogram, kiểm tra NUM_DISTINCT và DENSITY. Dự đoán selectivity của mỗi giá trị.

### Bài 2 — Phân bố lệch

Tạo bảng 100.000 hàng với 99.000 OPEN và 1.000 CANCELLED. So sánh actual row count và ước lượng khi không có histogram.

### Bài 3 — Frequency histogram

Gather stats với SIZE 10 cho cột có hai giá trị. Kiểm tra HISTOGRAM, NUM_BUCKETS và endpoint. Giải thích vì sao có thể dùng frequency histogram.

### Bài 4 — SIZE AUTO và SKEWONLY

Chạy workload có predicate trên cột lệch, xem column usage, gather SIZE AUTO. So sánh với SIZE SKEWONLY và giải thích khác biệt.

### Bài 5 — SIZE 1

Bỏ histogram của một cột trong schema thử nghiệm. So sánh E-Rows/A-Rows với khi có histogram.

### Bài 6 — Histogram và index

Tạo index trên STATUS. So sánh plan cho OPEN và CANCELLED. Quan sát vì sao một giá trị có thể dùng full scan, giá trị kia dùng index.

### Bài 7 — Bind peeking

Viết SQL dùng bind STATUS. Chạy với giá trị hiếm và phổ biến trong các thứ tự khác nhau. Quan sát child cursor và plan.

### Bài 8 — Adaptive Cursor Sharing

Theo dõi IS_BIND_SENSITIVE và IS_BIND_AWARE trong V$SQL sau khi chạy nhiều giá trị bind. Ghi nhận điều kiện để Oracle tạo child cursor.

### Bài 9 — Range predicate

Tạo cột ngày có dữ liệu tập trung theo một số khoảng. So sánh ước lượng range khi có và không có histogram.

### Bài 10 — Column group statistics

Tạo bảng có COUNTRY_CODE và STATE_CODE tương quan. So sánh cardinality ước lượng cho predicate kết hợp trước/sau CREATE_EXTENDED_STATS.

### Bài 11 — Stale statistics

Gather stats, sau đó thay đổi đáng kể phân bố dữ liệu. Kiểm tra STALE_STATS và quan sát sai lệch cardinality. Gather lại và so sánh.

### Bài 12 — Benchmark trước/sau

Chọn một SQL có skew. Lưu plan, E-Rows/A-Rows, buffers, CPU và elapsed. Thử một thay đổi thống kê, chạy nhiều lần với cả giá trị phổ biến/hiếm, rồi ghi kết luận.

## 31. Checklist trước khi thay đổi histogram

**Dữ liệu**

- Đã đo phân bố thực tế?
- Cột có skew đáng kể?
- NUM_DISTINCT và NUM_NULLS có phù hợp?
- Thống kê có stale?

**Workload**

- Cột có xuất hiện trong predicate/join?
- Có SQL_ID cụ thể bị sai cardinality?
- Query dùng literal hay bind?
- Có giá trị phổ biến và hiếm với plan khác nhau?

**Thống kê**

- HISTOGRAM hiện tại là gì?
- SIZE AUTO/SKEWONLY/REPEAT hay explicit size phù hợp?
- Column usage đã được ghi nhận?
- Có correlation cần extended stats?
- Có partition-level/global stats cần xem?

**Plan**

- E-Rows và A-Rows chênh lệch bao nhiêu?
- Buffers, CPU, elapsed có cải thiện?
- Index/full scan được chọn có hợp lý?
- Đã thử nhiều bind values?
- Có regression ở query khác?

**Vận hành**

- Có backup/restore stats hoặc pending stats?
- Có kiểm soát invalidation và reparse?
- Có kế hoạch theo dõi sau gather?
- Phạm vi thay đổi có giới hạn?

## 32. Ghi nhớ

| Khái niệm | Điều cần nhớ |
|---|---|
| Skew | Một số giá trị xuất hiện nhiều hơn đáng kể các giá trị khác |
| Selectivity | Tỷ lệ hàng thỏa predicate |
| Cardinality | Số hàng optimizer ước lượng |
| NUM_DISTINCT | Số giá trị phân biệt |
| DENSITY | Thống kê dùng trong ước lượng selectivity, không luôn là tần suất chính xác |
| Histogram | Mô tả phân bố giá trị cho optimizer |
| Frequency | Biểu diễn từng giá trị khi số bucket đủ |
| Height-balanced | Histogram truyền thống, thường gặp ở legacy |
| Top-frequency | Tập trung nhóm giá trị phổ biến |
| Hybrid | Endpoint và repeat count giúp mô tả giá trị phổ biến |
| SIZE AUTO | Oracle quyết định theo thống kê và usage |
| SIZE SKEWONLY | Chọn histogram theo độ lệch |
| SIZE REPEAT | Duy trì lựa chọn histogram hiện hữu |
| SIZE 1 | Không tạo histogram cho cột |
| Bind peeking | Peek bind trong quá trình hard parse |
| Adaptive Cursor Sharing | Có thể tạo child cursor cho vùng selectivity khác nhau |
| Extended statistics | Hỗ trợ ước lượng correlation giữa các cột/biểu thức |
| Stale stats | Thống kê có thể không còn đại diện dữ liệu hiện tại |
| DBMS_XPLAN | Xem estimated/actual rows và plan |
| DBMS_STATS | Thu thập và quản lý optimizer statistics |

Histogram giúp Oracle nhận biết dữ liệu không phân bố đều, từ đó ước lượng selectivity và cardinality chính xác hơn cho các predicate phù hợp. Hãy xác định cột có skew thật sự, kiểm tra workload và actual plan, chọn policy DBMS_STATS phù hợp, rồi thử với cả giá trị phổ biến lẫn hiếm. Nếu sai lệch đến từ tương quan giữa nhiều cột, hãy xem extended statistics; nếu dữ liệu thay đổi, hãy quản lý stale stats. Histogram là công cụ cải thiện thông tin cho optimizer, không phải lệnh ép dùng index hoặc bảo đảm plan luôn nhanh hơn.
