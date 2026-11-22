# Extended statistics trong Oracle Database

## 1. Vì sao optimizer cần extended statistics?

Oracle Cost-Based Optimizer (CBO) chọn execution plan dựa trên chi phí ước lượng. Một đầu vào quan trọng của phép ước lượng là **cardinality**: số dòng mà optimizer dự đoán sẽ đi qua mỗi bước của execution plan. Cardinality ảnh hưởng đến thứ tự join, lựa chọn nested loops hay hash join, lựa chọn access path và lượng bộ nhớ cần dùng.

Với thống kê thông thường, Oracle lưu thông tin riêng cho từng cột, chẳng hạn số giá trị phân biệt (NDV), số giá trị NULL, density và histogram nếu cần. Khi một câu SQL lọc đồng thời nhiều cột, optimizer có thể phải ước lượng xác suất của các điều kiện kết hợp. Nếu các cột độc lập, phép nhân selectivity riêng lẻ là một xấp xỉ hợp lý. Nhưng dữ liệu thực tế thường có quan hệ giữa các cột.

Ví dụ, trong bảng `CUSTOMERS`, `COUNTRY_ID` và `CUST_STATE_PROVINCE` có quan hệ rõ ràng: giá trị `CA` của bang California chỉ xuất hiện cùng quốc gia `US`. Giả sử 50% khách hàng thuộc `US`, còn 5% khách hàng có bang `CA`. Nếu giả định hai cột độc lập, optimizer có thể ước lượng:

\[
P(COUNTRY\_ID = 'US' \land CUST\_STATE\_PROVINCE = 'CA')
\approx 0.50 \times 0.05 = 0.025
\]

Kết quả là 2,5% số dòng, trong khi tỷ lệ thực tế có thể là 5%. Sai lệch này khiến optimizer đánh giá thấp số dòng cần xử lý. Với các bảng lớn hoặc chuỗi join dài, sai lệch cardinality ở một bước có thể dẫn đến lựa chọn plan kém hiệu quả ở nhiều bước tiếp theo.

Một tình huống khác xuất hiện khi câu SQL lọc theo biểu thức, ví dụ `UPPER(EMAIL)`, `TRUNC(ORDER_DATE)` hoặc `SUBSTR(CODE, 1, 3)`. Thống kê riêng trên cột gốc không nhất thiết mô tả đúng phân bố của giá trị sau khi tính biểu thức.

**Extended statistics** bổ sung thông tin thống kê cho một nhóm cột có tương quan hoặc cho một biểu thức. Nhờ đó optimizer có thêm dữ liệu để ước lượng selectivity và cardinality sát thực tế hơn.

## 2. Extended statistics là gì?

Extended statistics là phần thống kê mở rộng do `DBMS_STATS` quản lý cho một bảng. Có hai dạng chính:

| Dạng | Đối tượng được thống kê | Trường hợp sử dụng |
|---|---|---|
| Column group statistics | Một nhóm từ hai cột trở lên, xét các giá trị kết hợp của chúng | Nhiều cột có tương quan và thường xuất hiện cùng nhau trong điều kiện truy vấn |
| Expression statistics | Kết quả của một biểu thức trên cột | Điều kiện truy vấn áp dụng hàm hoặc phép tính lên cột |

Extended statistics phục vụ **ước lượng của optimizer**. Việc tạo chúng không tạo index, không lưu thêm một bản sao các dòng dữ liệu và không tự làm cho truy vấn có thêm access path. Chúng cũng không thay thế thống kê thông thường của từng cột; hai loại thống kê bổ sung cho nhau.

Oracle tạo metadata cho extension trước, sau đó thu thập giá trị thống kê khi `DBMS_STATS` gather statistics cho bảng. Vì vậy, chỉ gọi `CREATE_EXTENDED_STATS` rồi dừng lại là chưa đủ để có số liệu mới dùng cho optimizer: cần gather statistics theo quy trình phù hợp.

## 3. Column group statistics cho các cột tương quan

### 3.1. Nhận biết trường hợp cần column group

Nên xem xét column group khi có đủ các dấu hiệu sau:

- Một câu SQL thường lọc hoặc nhóm theo nhiều cột của cùng một bảng.
- Giá trị của các cột có quan hệ thực tế, nên phân bố kết hợp khác đáng kể so với giả định độc lập.
- Execution plan cho thấy `E-Rows` (số dòng ước lượng) lệch đáng kể so với `A-Rows` (số dòng thực tế) tại bước lọc bảng.

Ví dụ:

```sql
SELECT customer_id, cust_state_province
FROM customers
WHERE country_id = 'US'
  AND cust_state_province = 'CA';
```

Hai điều kiện cùng xuất hiện trong một truy vấn và có quan hệ ngữ nghĩa. Thống kê riêng của `COUNTRY_ID` và `CUST_STATE_PROVINCE` chỉ mô tả từng cột; column group `(COUNTRY_ID, CUST_STATE_PROVINCE)` bổ sung thống kê cho các tổ hợp giá trị.

Column group cũng có thể hữu ích khi các cột thường được dùng cùng nhau trong workload, chẳng hạn điều kiện lọc, join predicate hoặc `GROUP BY`. Hãy dựa vào workload thực tế và execution plan để chọn nhóm cột, thay vì tạo mọi tổ hợp có thể có.

### 3.2. Tạo column group bằng DBMS_STATS

Hàm `DBMS_STATS.CREATE_EXTENDED_STATS` nhận tên schema, tên bảng và biểu thức mô tả extension. Với column group, biểu thức có dạng danh sách cột đặt trong ngoặc:

```sql
SELECT DBMS_STATS.CREATE_EXTENDED_STATS(
         ownname   => USER,
         tabname   => 'CUSTOMERS',
         extension => '(COUNTRY_ID, CUST_STATE_PROVINCE)'
       ) AS extension_name
FROM dual;
```

Hàm trả về tên extension do Oracle tạo. Tiếp theo, gather statistics cho bảng:

```sql
BEGIN
  DBMS_STATS.GATHER_TABLE_STATS(
    ownname    => USER,
    tabname    => 'CUSTOMERS',
    method_opt => 'FOR ALL COLUMNS SIZE AUTO'
  );
END;
/
```

Khi statistics của bảng được thu thập, Oracle cũng thu thập statistics cho extension đã tạo. Có thể dùng job gather statistics tự động của Oracle để cập nhật về sau; nếu cần kiểm soát thời điểm hoặc xác nhận kết quả ngay, hãy gọi `GATHER_TABLE_STATS` như ví dụ.

### 3.3. Tạo và gather column group bằng METHOD_OPT

Một cách khác là khai báo nhóm cột trực tiếp trong tham số `METHOD_OPT` của `GATHER_TABLE_STATS`. Oracle có thể tạo extension và thu thập thống kê cho nhóm đó trong cùng thao tác:

```sql
BEGIN
  DBMS_STATS.GATHER_TABLE_STATS(
    ownname    => USER,
    tabname    => 'CUSTOMERS',
    method_opt =>
      'FOR ALL COLUMNS SIZE AUTO ' ||
      'FOR COLUMNS (COUNTRY_ID, CUST_STATE_PROVINCE) SIZE AUTO'
  );
END;
/
```

`SIZE AUTO` cho phép Oracle quyết định có cần histogram hay không dựa trên thông tin sử dụng và phân bố dữ liệu. Khi cần kiểm soát rõ hơn, có thể chọn cách tạo extension riêng rồi cấu hình `METHOD_OPT` theo chính sách histogram của hệ thống. Không cần tạo cùng một column group lặp lại bằng cả hai cách.

### 3.4. Column group giúp optimizer điều chỉnh ước lượng như thế nào?

Giả sử câu SQL có hai điều kiện:

```sql
WHERE country_id = 'US'
  AND cust_state_province = 'CA'
```

Nếu chỉ có thống kê từng cột, optimizer có thể kết hợp selectivity của hai điều kiện theo giả định độc lập. Column group cung cấp thông tin về các tổ hợp giá trị xuất hiện trong dữ liệu, chẳng hạn số tổ hợp phân biệt và density của nhóm. Khi phù hợp với predicate của câu SQL, optimizer có thể dùng thông tin kết hợp này để ước lượng số dòng sau bộ lọc chính xác hơn.

Histogram trên column group có thể hữu ích khi các tổ hợp giá trị cũng bị lệch phân bố. Tuy nhiên, histogram không phải lúc nào cũng cần thiết: hãy để `SIZE AUTO` quyết định trước, sau đó kiểm tra plan và workload nếu có lý do để điều chỉnh.

## 4. Expression statistics cho điều kiện có hàm hoặc phép tính

### 4.1. Vấn đề với predicate trên biểu thức

Xét câu SQL:

```sql
SELECT customer_id, cust_state_province
FROM customers
WHERE UPPER(cust_state_province) = 'CALIFORNIA';
```

Điều kiện lọc áp dụng `UPPER` lên giá trị cột. Thống kê thông thường của `CUST_STATE_PROVINCE` mô tả dữ liệu gốc, trong khi optimizer cần ước lượng phân bố của kết quả `UPPER(CUST_STATE_PROVINCE)`. Nếu không có thống kê phù hợp cho biểu thức, ước lượng selectivity có thể thiếu chính xác.

Các ví dụ thường gặp khác:

```sql
WHERE TRUNC(order_date) = DATE '2026-11-14'
WHERE SUBSTR(product_code, 1, 3) = 'ABC'
WHERE amount + tax_amount > 1000
```

Trong mỗi trường hợp, biểu thức có thể làm thay đổi phân bố giá trị mà optimizer cần ước lượng.

### 4.2. Tạo expression statistics

Có thể tạo extension cho biểu thức bằng `CREATE_EXTENDED_STATS`. Biểu thức được đặt trong ngoặc:

```sql
SELECT DBMS_STATS.CREATE_EXTENDED_STATS(
         ownname   => USER,
         tabname   => 'CUSTOMERS',
         extension => '(UPPER(CUST_STATE_PROVINCE))'
       ) AS extension_name
FROM dual;
```

Sau đó gather statistics cho bảng:

```sql
BEGIN
  DBMS_STATS.GATHER_TABLE_STATS(
    ownname    => USER,
    tabname    => 'CUSTOMERS',
    method_opt => 'FOR ALL COLUMNS SIZE AUTO'
  );
END;
/
```

Hoặc khai báo biểu thức trực tiếp trong `METHOD_OPT`:

```sql
BEGIN
  DBMS_STATS.GATHER_TABLE_STATS(
    ownname    => USER,
    tabname    => 'CUSTOMERS',
    method_opt =>
      'FOR ALL COLUMNS SIZE AUTO ' ||
      'FOR COLUMNS (UPPER(CUST_STATE_PROVINCE)) SIZE AUTO'
  );
END;
/
```

Biểu thức cần phản ánh cách truy vấn thực sự viết predicate. Ví dụ, thống kê cho `UPPER(CUST_STATE_PROVINCE)` không nên được giả định là sẽ thay thế thống kê cho một biểu thức khác như `LOWER(CUST_STATE_PROVINCE)` hoặc `SUBSTR(CUST_STATE_PROVINCE, 1, 3)`. Nếu truy vấn thay đổi cách viết biểu thức, hãy kiểm tra lại khả năng optimizer sử dụng extension.

### 4.3. Expression statistics và function-based index

Hai tính năng này giải quyết hai phần khác nhau của bài toán:

| Tính năng | Vai trò chính |
|---|---|
| Expression statistics | Cung cấp thống kê để optimizer ước lượng selectivity và cardinality của predicate trên biểu thức |
| Function-based index | Tạo access path dựa trên giá trị của biểu thức, giúp Oracle có thể tìm dòng qua index khi plan phù hợp |

Ví dụ, statistics cho `UPPER(EMAIL)` có thể giúp optimizer ước lượng tốt hơn điều kiện `UPPER(EMAIL) = :email`. Chúng không tự tạo index trên `UPPER(EMAIL)`. Nếu mục tiêu còn là tăng tốc việc truy cập dòng, cần đánh giá riêng function-based index và chi phí duy trì index đó. Có thể dùng cả expression statistics và function-based index khi workload và execution plan cho thấy cả hai đều có ích.

## 5. Tìm column group từ workload

Khi chưa rõ nhóm cột nào đáng tạo, Oracle cung cấp `DBMS_STATS.SEED_COL_USAGE` và `DBMS_STATS.REPORT_COL_USAGE` để ghi nhận cách workload sử dụng cột.

### 5.1. Thu thập thông tin sử dụng cột

Trong cửa sổ giám sát phù hợp, chạy:

```sql
EXEC DBMS_STATS.SEED_COL_USAGE(USER, 'CUSTOMERS', 300);
```

Lệnh trên yêu cầu Oracle ghi nhận thông tin sử dụng cột cho bảng trong khoảng thời gian chỉ định (300 giây). Trong khoảng thời gian đó, cho workload đại diện chạy hoặc compile các câu SQL đại diện; `EXPLAIN PLAN` cho các câu truy vấn phù hợp cũng có thể giúp Oracle ghi nhận cách các cột được sử dụng. Nên chọn workload gần với hoạt động thực tế thay vì chỉ dùng một câu SQL hiếm gặp.

### 5.2. Xem báo cáo sử dụng cột

Sau khi thu thập, xem báo cáo:

```sql
SELECT DBMS_STATS.REPORT_COL_USAGE(USER, 'CUSTOMERS')
FROM dual;
```

Báo cáo cho biết các cột xuất hiện trong filter predicates, join predicates và `GROUP BY`. Dựa trên các nhóm cột thường được dùng cùng nhau, kết hợp với dấu hiệu tương quan dữ liệu và sai lệch cardinality, hãy chọn extension có ích.

Oracle cũng có overload của `CREATE_EXTENDED_STATS` nhận schema và tên bảng mà không cần truyền tham số `extension`; overload này tạo các extension dựa trên thông tin column usage đã ghi nhận và trả về báo cáo. Hãy đọc kết quả trước khi đưa các extension được đề xuất vào quy trình vận hành.

Lưu ý: kỹ thuật column usage hỗ trợ tìm **column group**. Nó không tự tìm mọi expression statistics cần thiết; biểu thức trong predicate cần được xem xét riêng.

### 5.3. Tự động tạo column group

Preference `AUTO_STAT_EXTENSIONS` điều khiển việc tự động tạo extension trong quá trình gather optimizer statistics. Trong các phiên bản Oracle có hỗ trợ preference này, giá trị mặc định là `OFF`. Khi bật `ON`, SQL Plan Directive phù hợp có thể kích hoạt việc tạo column group dựa trên cách workload sử dụng predicate; điều đó không có nghĩa Oracle sẽ tự tạo mọi tổ hợp cột.

Ví dụ cấu hình ở phạm vi một bảng:

```sql
BEGIN
  DBMS_STATS.SET_TABLE_PREFS(
    ownname => USER,
    tabname => 'CUSTOMERS',
    pname   => 'AUTO_STAT_EXTENSIONS',
    pvalue  => 'ON'
  );
END;
/
```

Chỉ bật preference này khi đã hiểu chính sách quản lý statistics và hành vi của phiên bản Oracle đang chạy. Với môi trường cần kiểm soát thay đổi chặt chẽ, tạo extension thủ công sau khi xem workload thường dễ dự đoán hơn.

## 6. Kiểm tra extension và đánh giá hiệu quả

### 6.1. Xem extension đã khai báo

View `USER_STAT_EXTENSIONS` liệt kê các statistics extension thuộc schema hiện tại:

```sql
SELECT table_name, extension, creator
FROM user_stat_extensions
WHERE table_name = 'CUSTOMERS';
```

Có thể dùng `ALL_STAT_EXTENSIONS` hoặc `DBA_STAT_EXTENSIONS` khi cần xem đối tượng ngoài phạm vi schema hiện tại và tài khoản có đủ quyền. View này giúp xác nhận extension đã được khai báo; để xác nhận số liệu đã được cập nhật, hãy kiểm tra thời điểm gather statistics và execution plan của câu SQL.

### 6.2. So sánh estimated rows với actual rows

Chạy câu SQL với runtime plan statistics:

```sql
SELECT /*+ GATHER_PLAN_STATISTICS */ COUNT(*)
FROM customers
WHERE country_id = 'US'
  AND cust_state_province = 'CA';
```

Ngay sau đó, xem execution plan của cursor vừa chạy:

```sql
SELECT *
FROM TABLE(
  DBMS_XPLAN.DISPLAY_CURSOR(
    NULL,
    NULL,
    'ALLSTATS LAST +PREDICATE'
  )
);
```

Trong kết quả, đối chiếu `E-Rows` với `A-Rows` ở bước xử lý bảng và các bước liên quan. `E-Rows` là số dòng optimizer ước lượng; `A-Rows` là số dòng thực tế được quan sát khi câu SQL chạy. Nếu hai giá trị gần nhau hơn sau khi bổ sung extended statistics, đó là dấu hiệu thông tin thống kê đã cải thiện ước lượng. Đồng thời kiểm tra toàn bộ plan và thời gian thực thi: cardinality chính xác hơn là mục tiêu trung gian, không tự bảo đảm mọi truy vấn sẽ nhanh hơn.

Khi so sánh trước và sau, cố gắng giữ các điều kiện thử nghiệm tương đương: cùng câu SQL, bind values, dữ liệu, trạng thái cache và môi trường. Nếu dữ liệu hoặc bind values thay đổi đáng kể, chênh lệch plan có thể đến từ nguyên nhân khác.

## 7. Quản lý vòng đời và các giới hạn cần nhớ

### 7.1. Chọn extension có mục tiêu

Mỗi column group bổ sung một đối tượng thống kê cần quản lý. Tạo mọi cặp cột trong bảng có thể làm tăng số extension, thời gian và công việc gather statistics, đồng thời khiến cấu hình khó theo dõi. Ưu tiên các nhóm có bằng chứng từ workload và sai lệch cardinality.

### 7.2. Duy trì statistics mới

Extended statistics chỉ hữu ích khi phản ánh dữ liệu hiện tại. Sau các thay đổi dữ liệu lớn, cần bảo đảm quy trình gather statistics cập nhật cả statistics của bảng và extension. Hãy kiểm tra lịch gather, trạng thái stale và thời điểm `LAST_ANALYZED` trong các view statistics thích hợp.

### 7.3. Histogram và data skew

Column group statistics bổ sung thông tin về mối quan hệ giữa các cột; histogram giúp mô tả phân bố lệch của giá trị. Đây là hai khía cạnh liên quan nhưng không đồng nhất. Nếu một nhóm có nhiều tổ hợp rất phổ biến và nhiều tổ hợp hiếm, hãy kiểm tra xem histogram có cần thiết hay không. Không nên tăng số bucket một cách máy móc vì histogram cũng có chi phí lưu trữ và có thể làm plan nhạy hơn với bind values.

### 7.4. Không thay thế các biện pháp tuning khác

Extended statistics xử lý vấn đề **ước lượng**. Chúng không tự sửa predicate không sargable, không thay thế index phù hợp, không loại bỏ full table scan khi full scan là lựa chọn rẻ nhất và không khắc phục SQL viết chưa tốt. Nếu cardinality đã hợp lý nhưng truy vấn vẫn chậm, cần tiếp tục xem access path, join method, I/O, CPU, wait events và cấu trúc SQL.

### 7.5. Xóa extension không còn cần thiết

Nếu workload thay đổi và extension không còn hữu ích, có thể xóa bằng `DBMS_STATS.DROP_EXTENDED_STATS`:

```sql
EXEC DBMS_STATS.DROP_EXTENDED_STATS(
  USER,
  'CUSTOMERS',
  '(COUNTRY_ID, CUST_STATE_PROVINCE)'
);
```

Với expression statistics, truyền đúng biểu thức đã khai báo, ví dụ `'(UPPER(CUST_STATE_PROVINCE))'`. Trước khi xóa trong môi trường production, kiểm tra các câu SQL đang phụ thuộc vào cải thiện ước lượng từ extension đó và theo dõi plan sau thay đổi.

## 8. Quy trình áp dụng thực tế

Một quy trình có thể áp dụng cho từng bảng như sau:

1. Chọn câu SQL đại diện có nhiều predicate trên cùng một bảng hoặc predicate dùng hàm trên cột.
2. Thu thập execution plan kèm runtime statistics; tìm bước có chênh lệch lớn giữa `E-Rows` và `A-Rows`.
3. Kiểm tra thống kê hiện có, histogram, độ mới của statistics và dữ liệu có tương quan hay biểu thức có phân bố đặc biệt hay không.
4. Với các cột tương quan, dùng column usage report hoặc workload để xác định column group. Với predicate biểu thức, xác định chính xác biểu thức cần thống kê.
5. Tạo extension bằng `CREATE_EXTENDED_STATS` hoặc khai báo trong `METHOD_OPT`, rồi gather statistics.
6. Chạy lại workload đại diện và so sánh cardinality, execution plan cùng thời gian thực thi.
7. Giữ extension khi có cải thiện có thể giải thích được; theo dõi và loại bỏ extension không còn giá trị khi workload thay đổi.

Extended statistics đặc biệt hữu ích khi optimizer hiểu đúng phân bố của từng cột riêng lẻ nhưng vẫn ước lượng sai các điều kiện kết hợp hoặc giá trị được biến đổi qua biểu thức. Chúng giúp CBO có thêm bằng chứng về dữ liệu thực tế để chọn execution plan phù hợp hơn.

## Tài liệu Oracle tham khảo

- [Oracle Database 19c SQL Tuning Guide — Managing Extended Statistics](https://docs.oracle.com/en/database/oracle/oracle-database/19/tgsql/managing-extended-statistics.html)
- [Oracle Database 19c PL/SQL Packages and Types Reference — DBMS_STATS](https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/DBMS_STATS.html)
