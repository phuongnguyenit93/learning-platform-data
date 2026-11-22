# Tác động của thống kê sau nạp lớn, thay đổi dữ liệu hoặc nâng cấp

Trong Oracle Database, bộ tối ưu hóa dựa trên chi phí (Cost-Based Optimizer, CBO) dùng thống kê để ước lượng số dòng, độ chọn lọc của điều kiện lọc, số lần truy cập khối dữ liệu và chi phí của từng phương án thực thi. Vì vậy, sau một lần nạp dữ liệu lớn, thay đổi mạnh về dữ liệu hoặc nâng cấp Oracle, thống kê cũ có thể khiến CBO chọn execution plan không còn phù hợp.

Thống kê không sửa đổi dữ liệu nghiệp vụ và không bảo đảm một câu SQL sẽ luôn có cùng execution plan. Chúng cung cấp thông tin đầu vào cho CBO. Khi thông tin này thay đổi, hoặc khi thuật toán tối ưu hóa thay đổi sau nâng cấp, kế hoạch thực thi và mức tiêu thụ CPU, I/O, bộ nhớ có thể thay đổi theo.

## 1. Những loại thống kê ảnh hưởng đến execution plan

Oracle duy trì nhiều nhóm thống kê. Cần xác định đúng nhóm liên quan trước khi thu thập hoặc khắc phục.

| Nhóm thống kê | Thông tin chính | Ảnh hưởng thường gặp |
|---|---|---|
| Thống kê bảng | Số dòng (**NUM_ROWS**), số block (**BLOCKS**), độ dài dòng trung bình (**AVG_ROW_LEN**) | Ước lượng kích thước bảng, chi phí full table scan và join |
| Thống kê cột | Số giá trị khác nhau (**NUM_DISTINCT**), số giá trị NULL, mật độ (**DENSITY**), giá trị thấp/cao | Ước lượng độ chọn lọc của điều kiện trên cột |
| Histogram | Phân bố tần suất của giá trị trong một cột | Giúp ước lượng chính xác hơn khi dữ liệu lệch hoặc một số giá trị phổ biến hơn nhiều giá trị khác |
| Thống kê index | Số leaf block, chiều cao cây (**BLEVEL**), clustering factor, số distinct key | Ước lượng chi phí truy cập qua index và truy xuất các dòng từ bảng |
| Thống kê partition | Số dòng và phân bố dữ liệu ở từng partition, cùng thống kê toàn bảng | Ảnh hưởng đến partition pruning, ước lượng join và kế hoạch truy vấn bảng phân vùng |
| Thống kê hệ thống | Đặc tính CPU và I/O của hệ thống | Ảnh hưởng đến cách CBO so sánh chi phí CPU với chi phí I/O |
| Thống kê dictionary và fixed objects | Đặc tính của đối tượng từ điển dữ liệu và fixed objects | Có thể ảnh hưởng đến các câu SQL nội bộ, truy vấn dictionary và hoạt động quản trị |

Thống kê bảng hoặc cột có thể đúng về tổng số dòng nhưng vẫn chưa mô tả tốt phân bố dữ liệu. Ví dụ, một cột **STATUS** có 10 triệu dòng nhưng 95% dòng mang giá trị **CLOSED**; 5% còn lại chia cho nhiều trạng thái khác. Nếu CBO chỉ nhìn thấy số lượng giá trị khác nhau mà không có thông tin phân bố thích hợp, nó có thể ước lượng một điều kiện **STATUS = 'CLOSED'** sai đáng kể.

## 2. Sau khi nạp dữ liệu lớn

### Vì sao thống kê cũ trở nên không phù hợp

Giả sử bảng **ORDERS** trước khi nạp có 1 triệu dòng. Sau một đợt nạp, bảng có 80 triệu dòng, trong đó phần lớn là đơn hàng của một tháng mới. Nếu thống kê vẫn mô tả trạng thái trước khi nạp, CBO có thể:

- Ước lượng số dòng của bảng thấp hơn thực tế.
- Chọn nested loops cho một phép join có tập dữ liệu lớn, trong khi hash join có thể phù hợp hơn.
- Chọn index range scan khi số dòng cần đọc quá lớn, hoặc chọn full table scan trong trường hợp điều kiện lọc thực tế rất chọn lọc.
- Ước lượng sai chi phí sort, hash join, parallel execution hoặc các bước xử lý trung gian.
- Đưa ra kế hoạch khác nhau cho cùng một câu SQL khi dữ liệu mới có phân bố khác dữ liệu cũ.

Các tình huống thường gặp gồm direct-path insert, **INSERT /*+ APPEND */**, CTAS (**CREATE TABLE AS SELECT**), nạp bằng SQL*Loader, nạp theo batch, truncate rồi nạp lại, hoặc trao đổi partition với bảng staging.

### Thời điểm thu thập thống kê

Nên thu thập hoặc xác nhận thống kê sau khi đợt nạp đã hoàn tất và dữ liệu đã đạt trạng thái mà ứng dụng sẽ truy vấn. Nếu thu thập giữa lúc nạp, thống kê có thể mô tả một trạng thái tạm thời. Sau đó, những batch tiếp theo tiếp tục thay đổi số dòng và phân bố dữ liệu.

Với một bảng không phân vùng, có thể thu thập thống kê bảng và index bằng **DBMS_STATS.GATHER_TABLE_STATS**:

~~~sql
BEGIN
  DBMS_STATS.GATHER_TABLE_STATS(
    ownname          => 'APP',
    tabname          => 'ORDERS',
    estimate_percent => DBMS_STATS.AUTO_SAMPLE_SIZE,
    method_opt       => 'FOR ALL COLUMNS SIZE AUTO',
    cascade          => DBMS_STATS.AUTO_CASCADE,
    degree           => DBMS_STATS.AUTO_DEGREE,
    no_invalidate    => DBMS_STATS.AUTO_INVALIDATE
  );
END;
/
~~~

Các tham số đáng chú ý:

- **AUTO_SAMPLE_SIZE** để Oracle tự chọn cách lấy mẫu phù hợp.
- **METHOD_OPT** quyết định cách thu thập thống kê cột và histogram. **SIZE AUTO** cho phép Oracle cân nhắc histogram dựa trên đặc điểm cột và thông tin sử dụng.
- **CASCADE** điều khiển việc thu thập thống kê index cùng với thống kê bảng. **AUTO_CASCADE** để Oracle quyết định.
- **DEGREE** điều khiển mức độ song song khi thu thập.
- **NO_INVALIDATE** điều khiển việc invalidation cursor sau khi thống kê thay đổi. **AUTO_INVALIDATE** giao quyết định cho Oracle.

Không nên mặc định tạo histogram cho mọi cột hoặc đặt một số bucket cố định cho tất cả bảng. Histogram có ích với cột có phân bố lệch, nhưng cũng có thể làm thay đổi ước lượng và execution plan. Hãy chọn **METHOD_OPT** theo đặc điểm dữ liệu và workload thực tế.

### Bảng phân vùng và nạp bằng partition exchange

Với bảng partition, cần quan tâm cả thống kê ở cấp partition và thống kê toàn bảng. Một partition mới có thể chứa dữ liệu rất khác các partition cũ. Nếu chỉ nhìn thống kê toàn bảng, hoặc chỉ cập nhật partition mới mà bỏ qua yêu cầu thống kê toàn cục, CBO có thể ước lượng sai truy vấn chạy trên nhiều partition.

Có thể dùng **GRANULARITY => 'AUTO'** để Oracle chọn mức thống kê phù hợp với cấu trúc phân vùng:

~~~sql
BEGIN
  DBMS_STATS.GATHER_TABLE_STATS(
    ownname          => 'APP',
    tabname          => 'SALES',
    estimate_percent => DBMS_STATS.AUTO_SAMPLE_SIZE,
    method_opt       => 'FOR ALL COLUMNS SIZE AUTO',
    granularity      => 'AUTO',
    cascade          => DBMS_STATS.AUTO_CASCADE,
    degree           => DBMS_STATS.AUTO_DEGREE
  );
END;
/
~~~

Đối với bảng partition rất lớn, thống kê tăng dần (incremental statistics) có thể giúp cập nhật thống kê toàn cục mà không phải quét lại mọi partition. Oracle lưu các synopsis để tổng hợp thống kê toàn cục. Cần bật và cấu hình incremental statistics theo phiên bản Oracle, chính sách quản trị và cách bảo trì partition của hệ thống.

~~~sql
BEGIN
  DBMS_STATS.SET_TABLE_PREFS(
    ownname => 'APP',
    tabname => 'SALES',
    pname   => 'INCREMENTAL',
    pvalue  => 'TRUE'
  );
END;
/
~~~

Với quy trình partition exchange load, hãy kiểm tra riêng thống kê của bảng staging, partition đích và thống kê toàn cục sau thao tác exchange. Việc đổi partition có thể làm thay đổi quan hệ giữa dữ liệu thực tế và thống kê đã lưu. Quy trình sao chép hoặc tính lại thống kê cần theo đúng phiên bản Oracle và cách exchange đang dùng; không nên giả định rằng thống kê của staging luôn tự động trở thành thống kê đúng cho toàn bảng.

## 3. Sau khi dữ liệu thay đổi trong quá trình vận hành

### Thống kê stale và ngưỡng thay đổi

Oracle theo dõi các thao tác insert, update và delete để xác định thống kê bảng có thể đã cũ hay chưa. Trạng thái này thường được thể hiện qua cột **STALE_STATS** trong các view thống kê. Ngưỡng stale mặc định thường là 10% số dòng, nhưng có thể được thay đổi bằng preference **STALE_PERCENT** ở cấp global, schema hoặc table. Hãy kiểm tra cấu hình thực tế thay vì dựa vào giá trị mặc định.

Có thể xem preference của một bảng như sau:

~~~sql
SELECT DBMS_STATS.GET_PREFS(
         pname   => 'STALE_PERCENT',
         ownname => 'APP',
         tabname => 'ORDERS'
       ) AS stale_percent
FROM dual;
~~~

Ngưỡng stale là tín hiệu để cân nhắc thu thập lại thống kê, không phải thước đo đầy đủ về chất lượng thống kê. Một thay đổi nhỏ về số dòng vẫn có thể làm phân bố dữ liệu thay đổi đáng kể. Ngược lại, một bảng tăng nhiều dòng nhưng dữ liệu mới có phân bố tương tự dữ liệu cũ chưa chắc cần xử lý giống một bảng có dữ liệu lệch mạnh.

Các trường hợp cần chú ý:

- Nhiều dòng được cập nhật từ một trạng thái sang trạng thái khác nhưng tổng số dòng gần như không đổi.
- Một giá trị trước đây hiếm trở thành giá trị phổ biến.
- Dữ liệu mới tập trung vào một khoảng ngày hoặc một nhóm khách hàng.
- Các cột có quan hệ tương quan thay đổi, ví dụ **COUNTRY** và **POSTAL_CODE**.
- Một bảng bị xóa phần lớn dữ liệu, truncate, hoặc được nạp lại theo chu kỳ.

### Histogram, bind variable và dữ liệu lệch

Histogram giúp CBO mô tả phân bố giá trị trong cột. Chúng đặc biệt hữu ích khi một số giá trị xuất hiện thường xuyên hơn nhiều so với các giá trị khác.

Tuy nhiên, với SQL dùng bind variable, giá trị bind ở thời điểm parse và cơ chế bind peeking/adaptive cursor sharing có thể ảnh hưởng đến cursor và execution plan. Vì vậy, không nên kết luận rằng chỉ cần thêm histogram là mọi truy vấn sẽ tốt hơn. Hãy kiểm tra nhiều giá trị bind đại diện, các child cursor và số dòng thực tế của từng bước trong execution plan.

Nếu nhiều cột có tương quan, thống kê riêng lẻ trên từng cột có thể chưa đủ. Extended statistics có thể mô tả nhóm cột hoặc biểu thức phù hợp với workload. Ví dụ, nếu điều kiện thường lọc đồng thời **COUNTRY** và **STATE**, có thể cân nhắc thống kê nhóm cột sau khi kiểm tra lợi ích và tác động:

~~~sql
SELECT DBMS_STATS.CREATE_EXTENDED_STATS(
         ownname   => 'APP',
         tabname   => 'CUSTOMERS',
         extension => '(COUNTRY, STATE)'
       )
FROM dual;
~~~

Sau khi tạo extension, cần thu thập lại thống kê bảng để CBO có thể sử dụng thông tin mới. Không nên tạo extended statistics hàng loạt mà không có truy vấn thực tế làm căn cứ.

### Thống kê bị khóa

Một số hệ thống khóa thống kê để giữ execution plan ổn định cho bảng quan trọng. Khi đó, tác vụ thu thập thống kê tự động có thể không cập nhật bảng như mong đợi. Kiểm tra trạng thái khóa trước khi kết luận rằng Oracle bỏ sót bảng:

~~~sql
SELECT owner, table_name, stattype_locked
FROM dba_tab_statistics
WHERE owner = 'APP'
  AND table_name = 'ORDERS';
~~~

Nếu cần thay đổi thống kê, hãy xác nhận lý do khóa và quy trình quản trị trước khi mở khóa. Có thể mở khóa bằng:

~~~sql
BEGIN
  DBMS_STATS.UNLOCK_TABLE_STATS(
    ownname => 'APP',
    tabname => 'ORDERS'
  );
END;
/
~~~

Chỉ khóa lại khi chính sách vận hành yêu cầu. Việc khóa thống kê có thể giữ nguyên một bộ thống kê đã lỗi thời trong khi dữ liệu tiếp tục thay đổi.

## 4. Sau khi nâng cấp Oracle Database

Nâng cấp phiên bản có thể làm execution plan thay đổi ngay cả khi dữ liệu và thống kê ứng dụng không đổi. Những nguyên nhân phổ biến gồm:

- Phiên bản mới thay đổi hành vi hoặc thuật toán của optimizer.
- Giá trị mặc định của một số tham số optimizer thay đổi.
- Một số tính năng tối ưu hóa mới được bật hoặc được sử dụng trong điều kiện khác trước.
- Cách ước lượng cardinality, chi phí CPU/I/O hoặc xử lý một số cấu trúc SQL thay đổi.
- Thống kê dictionary, fixed objects hoặc thông tin hệ thống không còn phản ánh chính xác môi trường sau nâng cấp.

**OPTIMIZER_FEATURES_ENABLE** là một tham số quan trọng khi phân tích khác biệt hành vi optimizer giữa các phiên bản. Không nên thay đổi tham số này trên toàn hệ thống chỉ để xử lý một execution plan bị chậm. Trước hết cần xác định SQL nào bị ảnh hưởng, so sánh plan và kiểm tra hướng dẫn nâng cấp dành cho phiên bản đích.

Sau nâng cấp, hãy thực hiện các công việc thống kê theo đúng hướng dẫn của phiên bản Oracle đang triển khai:

1. Xác nhận thống kê dictionary đã được cập nhật theo khuyến nghị của quy trình nâng cấp. Khi được yêu cầu, dùng **DBMS_STATS.GATHER_DICTIONARY_STATS**.
2. Thu thập fixed object statistics sau khi hệ thống đã chạy workload đại diện. **DBMS_STATS.GATHER_FIXED_OBJECTS_STATS** thực hiện trên các fixed objects; kết quả có ý nghĩa hơn khi database đã có hoạt động thực tế thay vì chỉ vừa khởi động và chưa có workload.
3. Đánh giá system statistics khi có thay đổi đáng kể về phần cứng hoặc đặc tính I/O/CPU và theo quy trình được phê duyệt. Không thu thập system statistics một cách máy móc chỉ vì vừa nâng cấp phiên bản.
4. Xác định các schema và bảng ứng dụng thực sự cần cập nhật thống kê. Tránh thu thập lại toàn bộ thống kê trên diện rộng mà không đánh giá tác động đến execution plan.
5. So sánh các SQL quan trọng trước và sau nâng cấp. Nếu có regression, cân nhắc SQL Plan Management, SQL plan baseline hoặc phương án khôi phục thống kê phù hợp.

Một kế hoạch thực thi thay đổi sau nâng cấp không tự động chứng minh thống kê bị sai. Cần tách biệt tác động của dữ liệu, thống kê, tham số optimizer, phiên bản optimizer và môi trường phần cứng.

## 5. Kiểm tra thống kê và execution plan

### Kiểm tra thống kê bảng

View **DBA_TAB_STATISTICS** cho biết số dòng, block, thời điểm phân tích và trạng thái stale. Ví dụ:

~~~sql
SELECT table_name,
       partition_name,
       num_rows,
       blocks,
       last_analyzed,
       stale_stats,
       global_stats
FROM dba_tab_statistics
WHERE owner = 'APP'
  AND table_name IN ('ORDERS', 'ORDER_ITEMS')
ORDER BY table_name, partition_name NULLS FIRST;
~~~

Với tài khoản không có quyền xem DBA views, dùng các view **ALL_TAB_STATISTICS** hoặc **USER_TAB_STATISTICS** tương ứng với phạm vi quyền truy cập.

### Kiểm tra lượng DML đã phát sinh

~~~sql
SELECT table_name,
       partition_name,
       inserts,
       updates,
       deletes,
       timestamp
FROM dba_tab_modifications
WHERE table_owner = 'APP'
  AND table_name = 'ORDERS'
ORDER BY partition_name;
~~~

Thông tin monitoring có thể chưa được flush vào view tại thời điểm truy vấn. Khi cần đối chiếu, có thể yêu cầu flush:

~~~sql
BEGIN
  DBMS_STATS.FLUSH_DATABASE_MONITORING_INFO;
END;
/
~~~

Các số liệu DML giúp hiểu mức thay đổi kể từ lần thu thập thống kê gần nhất. Chúng không thay thế việc kiểm tra phân bố dữ liệu và execution plan.

### So sánh số dòng ước lượng với số dòng thực tế

Một dấu hiệu quan trọng của thống kê không phù hợp là chênh lệch lớn giữa số dòng CBO ước lượng (**E-Rows**) và số dòng thực tế (**A-Rows**) ở các bước trong plan. Có thể chạy câu SQL thử nghiệm với hint **GATHER_PLAN_STATISTICS**, sau đó xem cursor:

~~~sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       ...
FROM   ...
WHERE  ...;
~~~

~~~sql
SELECT *
FROM TABLE(
  DBMS_XPLAN.DISPLAY_CURSOR(
    sql_id => 'sql_id_here',
    format => 'ALLSTATS LAST +PEEKED_BINDS +OUTLINE'
  )
);
~~~

**ALLSTATS LAST** chỉ hiển thị số liệu thực thi khi cursor đã thu thập plan statistics, chẳng hạn bằng hint **GATHER_PLAN_STATISTICS** hoặc cấu hình thống kê thực thi phù hợp. Hãy chạy với bind value đại diện và workload có thể so sánh. Một lần chạy đơn lẻ không đủ để đại diện cho mọi giá trị bind hoặc mọi tình huống tải.

Khi đọc plan, tập trung vào:

- Bước đầu tiên có chênh lệch lớn giữa **E-Rows** và **A-Rows**.
- Điều kiện lọc, join predicate và partition pruning.
- Số lần thực hiện của từng bước (**Starts**).
- Buffer gets, physical reads, thời gian và các bước sort/hash lớn.
- Bind value, child cursor và các khác biệt về môi trường thực thi.

Nếu cardinality đã hợp lý nhưng thời gian vẫn tăng, nguyên nhân có thể nằm ở I/O, contention, cấu hình song song, memory hoặc workload đồng thời thay vì thống kê.

## 6. Quy trình cập nhật thống kê có kiểm soát

Một quy trình an toàn nên có đủ dữ liệu để so sánh và có phương án xử lý nếu execution plan xấu đi.

1. **Ghi nhận trạng thái trước thay đổi.** Lưu thời điểm và phạm vi nạp dữ liệu, số dòng dự kiến, thống kê hiện tại, SQL quan trọng, execution plan và số liệu thực thi đại diện.
2. **Xác định phạm vi cần thu thập.** Phân biệt bảng thường, bảng partition, index, thống kê cột và thống kê hệ thống. Kiểm tra **STALE_STATS**, lượng DML, histogram, preference và trạng thái khóa.
3. **Thu thập sau khi dữ liệu ổn định.** Dùng **DBMS_STATS** với sample size, method options, granularity và mức song song phù hợp. Với bảng partition lớn, đánh giá incremental statistics và yêu cầu cập nhật global statistics.
4. **Đánh giá thống kê mới.** Kiểm tra **LAST_ANALYZED**, **NUM_ROWS**, thống kê partition, index và histogram. Đối chiếu các giá trị với số liệu dữ liệu thực tế.
5. **Thử execution plan với workload đại diện.** So sánh **E-Rows** và **A-Rows**, buffer gets, reads, elapsed time và các giá trị bind quan trọng.
6. **Triển khai có kiểm soát.** Chỉ công bố thống kê mới khi kết quả thử nghiệm phù hợp. Theo dõi SQL quan trọng sau khi công bố vì cursor có thể được parse lại và chọn plan mới.
7. **Giữ phương án phục hồi.** Bảo đảm stats history còn đủ thời gian lưu, biết cách khôi phục thống kê và có kế hoạch xử lý SQL plan regression.

### Dùng pending statistics để thử trước khi công bố

Pending statistics cho phép thu thập thống kê nhưng chưa công bố ngay cho toàn hệ thống. Có thể đặt preference **PUBLISH** của bảng thành **FALSE**, thu thập thống kê, rồi thử trong session bật **OPTIMIZER_USE_PENDING_STATISTICS**.

~~~sql
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
~~~

Trong session thử nghiệm:

~~~sql
ALTER SESSION SET optimizer_use_pending_statistics = TRUE;
~~~

Chạy SQL với bind value đại diện và kiểm tra plan cùng số liệu thực thi. Sau khi đánh giá:

- Nếu thống kê mới đạt yêu cầu, công bố bằng **DBMS_STATS.PUBLISH_PENDING_STATS**.
- Nếu không đạt yêu cầu, xóa pending statistics bằng **DBMS_STATS.DELETE_PENDING_STATS**.
- Đặt lại preference **PUBLISH** theo chính sách của bảng sau khi hoàn tất thử nghiệm.

Ví dụ công bố:

~~~sql
BEGIN
  DBMS_STATS.PUBLISH_PENDING_STATS(
    ownname => 'APP',
    tabname => 'ORDERS'
  );

  DBMS_STATS.SET_TABLE_PREFS(
    ownname => 'APP',
    tabname => 'ORDERS',
    pname   => 'PUBLISH',
    pvalue  => 'TRUE'
  );
END;
/
~~~

Pending statistics là cơ chế thử nghiệm. Nó không thay thế kiểm thử với workload thực tế và không bảo đảm rằng mọi SQL sẽ có plan tốt hơn.

### Khôi phục thống kê khi có regression

Oracle lưu lịch sử thống kê trong khoảng thời gian được cấu hình. Nếu thống kê mới gây regression và lịch sử vẫn còn bản phù hợp, có thể khôi phục thống kê bảng về một thời điểm trước đó:

~~~sql
BEGIN
  DBMS_STATS.RESTORE_TABLE_STATS(
    ownname         => 'APP',
    tabname         => 'ORDERS',
    as_of_timestamp => SYSTIMESTAMP - INTERVAL '1' DAY
  );
END;
/
~~~

Thời điểm trong ví dụ chỉ mang tính minh họa; cần chọn timestamp tương ứng với trạng thái đã ghi nhận và còn trong thời gian lưu lịch sử. Khôi phục thống kê không đồng nghĩa mọi cursor sẽ lập tức quay lại execution plan cũ. Cần kiểm tra cursor, invalidation và SQL plan baseline sau thao tác.

## 7. Những sai lầm thường gặp

- **Chỉ dựa vào STALE_STATS.** Trạng thái stale không mô tả đầy đủ độ lệch phân bố dữ liệu. Một bảng có thể cần cập nhật thống kê dù tỷ lệ DML thấp.
- **Thu thập thống kê khi nạp chưa xong.** Kết quả chỉ phản ánh trạng thái tạm thời và nhanh chóng lỗi thời.
- **Bỏ qua thống kê index.** Thống kê bảng mới nhưng thống kê index cũ có thể làm CBO đánh giá sai chi phí truy cập.
- **Chỉ cập nhật một partition mà quên thống kê toàn cục.** Điều này đặc biệt đáng chú ý với truy vấn truy cập nhiều partition.
- **Tạo histogram cho mọi cột.** Histogram có thể cải thiện ước lượng nhưng cũng làm thay đổi plan và hành vi với bind variable.
- **Thu thập lại thống kê toàn schema hoặc toàn database theo thói quen.** Thao tác diện rộng có thể làm nhiều SQL parse lại và thay đổi plan cùng lúc.
- **Nhầm lẫn giữa lỗi thống kê và lỗi tài nguyên.** Nếu ước lượng cardinality hợp lý nhưng thời gian vẫn cao, cần điều tra I/O, CPU, contention, memory và workload.
- **Nâng cấp rồi thay đổi nhiều tham số optimizer cùng lúc.** Khi có regression, sẽ khó xác định nguyên nhân nếu phiên bản, tham số, thống kê và plan đều thay đổi đồng thời.

## 8. Checklist vận hành

Sau một đợt nạp lớn, thay đổi dữ liệu đáng kể hoặc nâng cấp Oracle, hãy xác nhận:

- [ ] Dữ liệu đã nạp hoặc chuyển đổi hoàn tất trước khi thu thập thống kê.
- [ ] Đã xác định đúng bảng, partition, index và loại thống kê cần cập nhật.
- [ ] Đã kiểm tra **LAST_ANALYZED**, **STALE_STATS**, lượng DML và trạng thái khóa thống kê.
- [ ] Histogram và extended statistics phù hợp với phân bố dữ liệu và truy vấn thực tế.
- [ ] Thống kê toàn cục được xử lý đúng với bảng partition.
- [ ] SQL quan trọng đã được so sánh execution plan và số dòng ước lượng/thực tế.
- [ ] Các giá trị bind đại diện và workload quan trọng đã được thử.
- [ ] Có lịch sử thống kê hoặc phương án phục hồi khi xảy ra regression.
- [ ] Sau nâng cấp, dictionary/fixed object/system statistics được xử lý theo hướng dẫn của phiên bản đích.
- [ ] Việc công bố thống kê và theo dõi sau thay đổi có người chịu trách nhiệm.

Thống kê tốt giúp CBO ước lượng gần với dữ liệu thực tế và chọn execution plan phù hợp. Hiệu quả đạt được phụ thuộc vào việc thu thập đúng thời điểm, đúng phạm vi, hiểu phân bố dữ liệu và kiểm chứng bằng workload thực tế.
