# Cost-based optimizer và các đầu vào để lựa chọn kế hoạch

Trong Oracle Database, một câu lệnh SQL mô tả **kết quả cần lấy**, còn bộ tối ưu hóa (optimizer) quyết định **cách lấy kết quả đó**. Cùng một câu SQL có thể được thực thi bằng nhiều kế hoạch khác nhau: quét toàn bộ bảng, đi qua chỉ mục, đổi thứ tự nối bảng, dùng nested loops, hash join hoặc biến đổi truy vấn con.

Cost-based optimizer (CBO) ước lượng lượng dữ liệu phải xử lý và tài nguyên mà từng phương án có thể tiêu thụ. Nó dùng các ước lượng này để chọn kế hoạch có chi phí ước lượng thấp nhất trong số những phương án được xem xét. Vì vậy, chất lượng kế hoạch phụ thuộc trực tiếp vào chất lượng thông tin mà optimizer nhận được: thống kê đối tượng, thống kê hệ thống, cấu trúc SQL, metadata của schema, giá trị bind, cấu hình phiên và các tính năng tối ưu hóa đang được bật.

Hiểu CBO không có nghĩa là cố ép Oracle dùng một index hay một kiểu join. Mục tiêu là nhận biết optimizer đang dựa vào giả định nào, dữ liệu thực tế có khác giả định đó không, và đầu vào nào cần được cải thiện để kế hoạch phù hợp với workload.

## 1. CBO làm việc ở đâu trong vòng đời SQL?

Khi ứng dụng gửi SQL đến Oracle, database phải phân tích cú pháp, kiểm tra ý nghĩa và quyền truy cập, sau đó tìm hoặc xây dựng một cursor có thể thực thi.

Có thể hình dung các bước chính như sau:

1. **Parse:** phân tích cú pháp SQL, xác định object, cột, kiểu dữ liệu và quyền cần thiết.
2. **Kiểm tra cursor có thể tái sử dụng:** nếu một child cursor phù hợp đã tồn tại trong shared pool, Oracle có thể tái sử dụng kế hoạch đã biên dịch. Đây thường được gọi là soft parse.
3. **Query transformation:** optimizer có thể biến đổi câu SQL sang dạng tương đương về ngữ nghĩa để mở rộng không gian tìm kiếm kế hoạch.
4. **Optimization:** optimizer xem xét access path, thứ tự join, join method, phép biến đổi và các lựa chọn thực thi; sau đó tính cardinality và cost cho các phương án.
5. **Cursor được thực thi:** row source tree trong kế hoạch lần lượt tạo và truyền các dòng dữ liệu giữa các operation.

Nếu không có cursor phù hợp, hoặc cursor cũ không còn hợp lệ, Oracle có thể phải hard parse và tối ưu hóa lại. Việc hard parse thường tốn CPU hơn soft parse. Thay đổi thống kê, DDL, metadata, tham số optimizer, bind hoặc môi trường thực thi có thể khiến cursor cần được tạo lại hoặc tạo thêm child cursor.

Điểm cần nhớ là optimizer không chạy lại toàn bộ quá trình tìm kế hoạch cho mọi lần gọi SQL. Một câu lệnh có thể tái sử dụng cursor, nhưng một SQL text cũng có thể có nhiều child cursor nếu Oracle xác định rằng các lần thực thi cần kế hoạch khác nhau hoặc môi trường của chúng không tương thích.

## 2. Kế hoạch thực thi gồm những quyết định nào?

Một execution plan là cây các operation (row sources). Mỗi operation nhận dữ liệu từ operation con, xử lý rồi trả dòng cho operation cha. Các quyết định quan trọng thường nằm trong bốn nhóm:

| Nhóm quyết định | Câu hỏi optimizer phải trả lời | Ví dụ |
|---|---|---|
| Access path | Đọc dữ liệu từ đâu và bằng cách nào? | Full table scan, index range scan, partition scan |
| Join order | Xử lý bảng nào trước? | CUSTOMERS trước ORDERS, hoặc ngược lại |
| Join method | Nối hai tập dữ liệu bằng thuật toán nào? | Nested loops, hash join, sort merge join |
| Query transformation | Có thể viết lại truy vấn tương đương để thực thi tốt hơn không? | View merging, subquery unnesting, predicate pushdown |

Ngoài ra, optimizer còn có thể lựa chọn partition pruning, parallel execution, phép truy cập dữ liệu theo thứ tự index, phép tổng hợp, phép sắp xếp và nhiều operation khác.

Kế hoạch không phải là bản mô tả câu SQL theo thứ tự từ trên xuống. Với cây execution plan, operation cha thường tiêu thụ kết quả từ operation con. Khi đọc kế hoạch, cần xem quan hệ cha-con và cột Id/Parent Id, thay vì hiểu các dòng như một danh sách lệnh tuần tự đơn giản.

Một số operation thường gặp:

- **TABLE ACCESS FULL:** đọc các block của bảng theo full scan.
- **TABLE ACCESS BY INDEX ROWID:** lấy rowid từ index rồi truy cập dòng tương ứng trong bảng.
- **INDEX UNIQUE SCAN:** tìm một key duy nhất trong unique index.
- **INDEX RANGE SCAN:** đọc một khoảng key trong index.
- **INDEX FAST FULL SCAN:** đọc toàn bộ index như một cấu trúc dữ liệu có thể quét nhiều block; thứ tự key không được bảo đảm như index full scan.
- **NESTED LOOPS:** lặp qua tập ngoài và tìm dòng tương ứng trong tập trong.
- **HASH JOIN:** xây dựng hash table từ một tập rồi dò tập còn lại.
- **SORT MERGE JOIN:** sắp xếp hoặc tận dụng dữ liệu đã có thứ tự, rồi ghép hai tập.
- **HASH GROUP BY, SORT GROUP BY:** thực hiện tổng hợp theo nhóm bằng hash hoặc sort.
- **SORT ORDER BY:** sắp xếp kết quả theo yêu cầu ORDER BY.

Tên operation cho biết kỹ thuật được chọn, nhưng chưa đủ để kết luận kế hoạch tốt hay xấu. Cần kết hợp số dòng ước lượng, số dòng thực tế, số lần bắt đầu operation, buffer gets, physical reads, thời gian, lượng dữ liệu trung gian và bối cảnh workload.

## 3. Cost là gì và không phải là gì?

Cost là thước đo nội bộ để optimizer so sánh các kế hoạch. Tùy loại operation và cấu hình, mô hình costing có thể tính đến các yếu tố như:

- Số lần đọc block và kiểu đọc (single-block hoặc multiblock).
- Khả năng cache và đặc tính I/O của hệ thống.
- CPU cần cho so sánh, join, sort, hash, lọc và chuyển đổi dữ liệu.
- Số dòng và độ rộng dòng phải xử lý.
- Bộ nhớ có thể dùng cho hash/sort và nguy cơ tràn ra temporary tablespace.
- Parallel execution và chi phí điều phối, phân phối dữ liệu.
- Các đặc tính của nền tảng và thống kê hệ thống.

**Cost không phải số giây, không phải số I/O thực tế và cũng không phải lời hứa về thời gian hoàn thành.** Cost 100 không có nghĩa câu SQL chạy trong 100 ms. Nó là ước lượng tương đối trong mô hình của optimizer, hữu ích nhất khi so sánh các phương án trong cùng bối cảnh.

Ví dụ, một full table scan có thể có cost thấp hơn index range scan nếu truy vấn cần phần lớn các dòng của bảng. Khi dùng index, Oracle có thể phải đọc các leaf block của index rồi truy cập nhiều table block qua rowid. Nếu các dòng nằm rải rác, lượng I/O ngẫu nhiên có thể lớn hơn đọc tuần tự một vùng block của bảng.

Ngược lại, nếu điều kiện lọc chỉ trả về vài dòng trên một bảng lớn, index có thể giảm đáng kể số block phải đọc.

Optimizer mode cũng ảnh hưởng mục tiêu tối ưu:

- **ALL_ROWS** hướng đến throughput: giảm tổng tài nguyên ước lượng để hoàn thành toàn bộ câu lệnh. Đây là chế độ mặc định phổ biến.
- **FIRST_ROWS_n** hướng đến response time cho n dòng đầu tiên, phù hợp một số truy vấn tương tác có yêu cầu trả kết quả sớm. Chế độ này có thể ưu tiên kế hoạch trả dòng đầu nhanh hơn, dù tổng công việc không nhất thiết thấp nhất.

Không nên suy luận rằng FIRST_ROWS_n luôn nhanh hơn cho ứng dụng hoặc rằng ALL_ROWS luôn tạo kế hoạch tốt hơn. Mục tiêu thực tế phụ thuộc cách ứng dụng fetch dữ liệu, số dòng cần dùng và workload tổng thể.

## 4. Cardinality và selectivity: nền tảng của ước lượng

Hai khái niệm quan trọng nhất khi đọc cách optimizer ước lượng dữ liệu là **cardinality** và **selectivity**.

- **Cardinality** là số dòng optimizer ước lượng một operation sẽ trả về.
- **Selectivity** là tỷ lệ dòng thỏa mãn một điều kiện so với tập dữ liệu đầu vào, thường nằm trong khoảng từ 0 đến 1.

Nếu bảng có 1.000.000 dòng và optimizer ước lượng điều kiện STATUS = 'PAID' có selectivity 0,1, cardinality ước lượng là:

**1.000.000 × 0,1 = 100.000 dòng**

Đây là ước lượng, không phải kết quả truy vấn thực tế.

### 4.1 Ước lượng điều kiện lọc

Giả sử bảng ORDERS có 1.000.000 dòng và cột STATUS có 4 giá trị khác nhau. Nếu không có thông tin về phân bố dữ liệu, một giả định đơn giản là các giá trị phân bố tương đối đồng đều. Khi đó, điều kiện bằng một giá trị có thể được ước lượng gần:

**Selectivity ≈ 1 / NUM_DISTINCT**

Với NUM_DISTINCT = 4, optimizer có thể bắt đầu từ selectivity xấp xỉ 0,25, tức khoảng 250.000 dòng.

Nhưng dữ liệu thực tế có thể lệch mạnh:

| STATUS | Số dòng thực tế | Tỷ lệ |
|---|---:|---:|
| NEW | 700.000 | 70% |
| PAID | 250.000 | 25% |
| CANCELLED | 49.000 | 4,9% |
| RETURNED | 1.000 | 0,1% |

Giả định đồng đều sẽ đánh giá sai đáng kể đối với RETURNED. Nếu optimizer nghĩ truy vấn trả 250.000 dòng trong khi thực tế chỉ có 1.000 dòng, lựa chọn giữa full scan và index access có thể bị ảnh hưởng. Histogram có thể cung cấp thêm thông tin về độ lệch này.

### 4.2 Ước lượng join

Với phép nối:

~~~sql
SELECT c.customer_id, o.order_id
FROM customers c
JOIN orders o
  ON o.customer_id = c.customer_id
WHERE c.region = 'NORTH';
~~~

Optimizer cần ước lượng:

1. Bao nhiêu khách hàng thỏa REGION = 'NORTH'.
2. Bao nhiêu đơn hàng liên quan đến nhóm khách hàng đó.
3. Phân bố khóa nối ở hai bảng.
4. Khả năng có nhiều đơn hàng cho một khách hàng.
5. Các điều kiện lọc khác có làm giảm dữ liệu trước khi join hay không.

Nếu cardinality của một nhánh bị ước lượng sai, sai lệch có thể lan sang các operation phía trên. Một join được dự đoán là vài chục dòng nhưng thực tế tạo ra hàng triệu dòng có thể làm kế hoạch nested loops trở nên rất tốn kém. Ngược lại, dự đoán quá nhiều dòng có thể khiến optimizer chọn hash join và đọc lượng dữ liệu lớn không cần thiết.

### 4.3 Tương quan giữa các cột

Optimizer có thể ước lượng sai khi các điều kiện trên nhiều cột có tương quan.

Ví dụ, bảng CUSTOMERS có hai cột COUNTRY và POSTAL_CODE. Nếu POSTAL_CODE gần như xác định COUNTRY, hai điều kiện:

~~~sql
WHERE country = 'VN'
  AND postal_code = '700000'
~~~

không độc lập. Nếu optimizer nhân selectivity của hai điều kiện như thể chúng độc lập, cardinality có thể thấp hơn hoặc cao hơn thực tế đáng kể.

Extended statistics, đặc biệt column group statistics, giúp optimizer mô tả một số tương quan giữa các cột. Thống kê trên biểu thức cũng hữu ích khi truy vấn thường lọc theo một biểu thức ổn định.

Không phải mọi tương quan đều được mô hình hóa hoàn hảo. Extended statistics cải thiện các trường hợp cụ thể, nhưng vẫn cần kiểm tra ước lượng so với dữ liệu thực tế.

## 5. Những loại thống kê Oracle sử dụng

Optimizer dựa vào nhiều lớp thống kê. Không có một con số duy nhất nào đại diện cho toàn bộ đặc tính của bảng.

### 5.1 Table statistics

Thống kê bảng có thể bao gồm:

- **NUM_ROWS:** số dòng được ghi nhận tại thời điểm thu thập.
- **BLOCKS:** số block được thống kê cho bảng.
- **AVG_ROW_LEN:** độ dài dòng trung bình.
- Thông tin về empty blocks và chain count trong một số ngữ cảnh.
- Thống kê riêng cho từng partition hoặc subpartition nếu bảng được phân vùng.

Các thông tin này giúp optimizer ước lượng kích thước dữ liệu, số block phải đọc và chi phí xử lý bảng.

NUM_ROWS không phải bộ đếm realtime. Sau khi dữ liệu thay đổi, giá trị trong dictionary có thể không phản ánh ngay số dòng hiện tại cho đến khi thống kê được cập nhật hoặc optimizer sử dụng một cơ chế bổ sung.

### 5.2 Column statistics

Thống kê cột thường gồm:

- **NUM_DISTINCT:** số giá trị khác nhau được ghi nhận.
- **NUM_NULLS:** số giá trị NULL.
- **DENSITY:** một thành phần trong mô hình ước lượng selectivity; cách sử dụng phụ thuộc loại histogram và phiên bản.
- **LOW_VALUE, HIGH_VALUE:** biên giá trị được thống kê.
- Histogram: mô tả phân bố giá trị khi cần thiết.

Column statistics ảnh hưởng trực tiếp đến ước lượng điều kiện bằng, khoảng, IN, IS NULL và các phép lọc khác.

Giá trị min/max có thể giúp optimizer nhận biết một điều kiện nằm ngoài phạm vi dữ liệu được thống kê. Tuy nhiên, nếu dữ liệu tăng liên tục hoặc có giá trị mới sau lần thu thập thống kê, min/max có thể trở nên cũ.

### 5.3 Index statistics

Các thông tin thường gặp:

- **BLEVEL:** độ sâu của B-tree index.
- **LEAF_BLOCKS:** số leaf block.
- **DISTINCT_KEYS:** số khóa phân biệt.
- **CLUSTERING_FACTOR:** mức độ tương quan giữa thứ tự rowid trong index và vị trí các dòng trong table block.

Clustering factor rất quan trọng khi index access cần quay lại bảng. Nếu các rowid của những key gần nhau thường trỏ đến cùng một số ít table block, clustering factor có xu hướng thấp và truy cập bảng qua index có thể hiệu quả. Nếu rowid phân tán trên nhiều block, clustering factor có thể cao và chi phí table access tăng.

Clustering factor không đo chất lượng index theo nghĩa chung. Một index có clustering factor cao vẫn hữu ích cho truy vấn rất chọn lọc, nhưng có thể kém hấp dẫn khi điều kiện trả về nhiều dòng.

### 5.4 System statistics

System statistics mô tả đặc tính xử lý và I/O của hệ thống, ví dụ khả năng CPU, thời gian đọc single-block/multiblock và thông lượng I/O. Optimizer sử dụng chúng để so sánh các kiểu truy cập trong điều kiện phần cứng và workload cụ thể.

Thống kê hệ thống không thay thế thống kê bảng, cột và index. Một bảng có thống kê hoàn hảo nhưng system statistics không phù hợp với hệ thống vẫn có thể dẫn đến ước lượng cost thiếu sát thực tế.

Việc thu thập hoặc thay đổi system statistics nên được thực hiện có chủ đích, dựa trên đặc tính workload và hướng dẫn vận hành của môi trường. Không nên sao chép system statistics từ một máy khác mà không đánh giá khác biệt về CPU, storage, cấu hình I/O và concurrency.

### 5.5 Partition statistics

Với bảng partitioned, optimizer có thể cần thống kê ở nhiều cấp:

- Global statistics mô tả toàn bảng.
- Partition statistics mô tả từng partition.
- Subpartition statistics mô tả từng subpartition.
- Thống kê index có thể ở cấp global hoặc local tùy loại index.

Khi một truy vấn chỉ đọc một vài partition, partition pruning và thống kê partition giúp ước lượng phạm vi dữ liệu cần xử lý. Thống kê global vẫn quan trọng cho truy vấn đi qua nhiều partition hoặc cần ước lượng toàn bảng.

Việc chỉ cập nhật một partition có thể khiến thống kê global cần được đồng bộ hoặc ước lượng lại. Chiến lược incremental statistics có thể hữu ích với bảng partition rất lớn, nhưng cần cấu hình và kiểm tra theo phiên bản Oracle, kiểu partition và quy trình nạp dữ liệu.

## 6. Histogram giúp xử lý dữ liệu phân bố lệch

Khi một cột có phân bố không đồng đều, chỉ biết NUM_DISTINCT là chưa đủ. Histogram cung cấp thêm thông tin để optimizer ước lượng selectivity theo giá trị hoặc khoảng giá trị.

Ví dụ, STATUS có bốn giá trị nhưng 70% dòng là NEW, trong khi RETURNED chỉ chiếm 0,1%. Không có histogram phù hợp, optimizer có thể dùng một ước lượng gần đồng đều cho các giá trị. Có histogram, optimizer có cơ hội nhận biết rằng hai điều kiện này có cardinality rất khác nhau.

Một số dạng histogram thường được nhắc đến:

- **Frequency histogram:** lưu thông tin tần suất cho các giá trị khi số lượng giá trị phù hợp với giới hạn bucket.
- **Top-frequency histogram:** tập trung vào các giá trị xuất hiện nhiều nhất, hữu ích khi có nhiều giá trị nhưng một nhóm nhỏ chiếm phần lớn dữ liệu.
- **Hybrid histogram:** biểu diễn phân bố bằng bucket và endpoint để hỗ trợ ước lượng tốt hơn cho dữ liệu lệch.
- **Height-balanced histogram:** dạng lịch sử, vẫn có thể gặp trong hệ thống hoặc tài liệu cũ.

Optimizer quyết định cách dùng histogram dựa trên metadata, thống kê, bind và ngữ cảnh truy vấn. Không nên giả định rằng có histogram là mọi truy vấn đều được ước lượng chính xác.

### 6.1 Thu thập histogram

DBMS_STATS hỗ trợ kiểm soát histogram qua tham số METHOD_OPT. Ví dụ:

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

SIZE AUTO cho phép Oracle quyết định cột nào cần histogram dựa trên thông tin sử dụng và phân bố dữ liệu mà database quan sát được. Đây là điểm khởi đầu phổ biến, không phải bảo đảm rằng mọi cột quan trọng đều có histogram đúng nhu cầu ứng dụng.

Có thể chỉ định histogram cho cột cụ thể, ví dụ:

~~~sql
BEGIN
  DBMS_STATS.GATHER_TABLE_STATS(
    ownname    => USER,
    tabname    => 'ORDERS',
    method_opt => 'FOR COLUMNS SIZE 254 STATUS',
    cascade    => TRUE
  );
END;
/
~~~

Số bucket và kiểu histogram thực tế do Oracle quyết định theo dữ liệu, phiên bản và quy tắc triển khai. Tránh tạo histogram hàng loạt trên mọi cột mà không có lý do, vì histogram có thể làm thay đổi kế hoạch của SQL phụ thuộc vào cột đó.

## 7. Extended statistics và thống kê biểu thức

Thống kê từng cột riêng lẻ không mô tả đầy đủ quan hệ giữa các cột. Extended statistics có thể bổ sung thông tin cho column group hoặc expression.

Ví dụ, nếu ứng dụng thường lọc đồng thời COUNTRY và POSTAL_CODE, có thể tạo column group:

~~~sql
SELECT DBMS_STATS.CREATE_EXTENDED_STATS(
         ownname   => USER,
         tabname   => 'CUSTOMERS',
         extension => '(COUNTRY, POSTAL_CODE)'
       )
FROM dual;
~~~

Sau khi tạo extension, cần thu thập lại thống kê bảng để Oracle tính giá trị cho extension đó:

~~~sql
BEGIN
  DBMS_STATS.GATHER_TABLE_STATS(
    ownname => USER,
    tabname => 'CUSTOMERS',
    method_opt => 'FOR ALL COLUMNS SIZE AUTO'
  );
END;
/
~~~

Đối với điều kiện trên biểu thức, chẳng hạn UPPER(email), có thể cân nhắc function-based index hoặc thống kê biểu thức tùy nhu cầu truy vấn. Function-based index phục vụ access path; expression statistics cải thiện ước lượng. Hai mục đích này liên quan nhưng không giống nhau.

Không nên tạo extended statistics chỉ vì hai cột cùng xuất hiện trong một câu SQL. Hãy xác định rằng chúng có tương quan và sai lệch cardinality thực sự ảnh hưởng đến kế hoạch.

## 8. Thống kê cũ, thiếu hoặc không đại diện cho dữ liệu

Thống kê có thể không phù hợp trong nhiều tình huống:

- Bảng vừa nạp một lượng dữ liệu lớn.
- Dữ liệu bị xóa hoặc cập nhật mạnh khiến phân bố thay đổi.
- Một partition mới được nạp nhưng thống kê global chưa phản ánh đúng.
- Cột có giá trị mới nằm ngoài min/max đã ghi nhận.
- Bảng tạm hoặc bảng staging có quy mô thay đổi mạnh theo phiên.
- Dữ liệu tăng theo thời gian và phân bố ngày gần nhất khác xa lịch sử.
- Thống kê được thu thập trên mẫu không đại diện cho phân bố thực tế.
- Histogram không phản ánh nhóm giá trị mà workload thường truy vấn.
- Thống kê index không được cập nhật sau khi cấu trúc hoặc dữ liệu thay đổi đáng kể.

Oracle có cơ chế theo dõi thay đổi để xác định thống kê có thể đã stale. Ngưỡng stale và hành vi auto statistics gathering phụ thuộc preference, phiên bản và cấu hình. Vì vậy, không nên mặc định rằng cứ thay đổi một số phần trăm cố định thì mọi bảng đều được thu thập lại ngay.

DBMS_STATS là API chính để thu thập và quản lý optimizer statistics. Ngoài GATHER_TABLE_STATS, có các thủ tục thu thập ở cấp schema/database, quản lý preference, lock/unlock, export/import và publish pending statistics.

Một số thao tác phổ biến:

~~~sql
-- Xem các cột thống kê cơ bản của bảng
SELECT table_name, num_rows, blocks, avg_row_len, last_analyzed, stale_stats
FROM user_tab_statistics
WHERE table_name = 'ORDERS';

-- Xem thống kê cột
SELECT column_name, num_distinct, num_nulls, density,
       histogram, num_buckets, last_analyzed
FROM user_tab_col_statistics
WHERE table_name = 'ORDERS';

-- Xem thống kê index
SELECT index_name, blevel, leaf_blocks, distinct_keys,
       clustering_factor, last_analyzed
FROM user_ind_statistics
WHERE table_name = 'ORDERS';
~~~

Các view dictionary có thể hiển thị khác nhau theo quyền và phiên bản. Nếu truy vấn view USER_* không thấy object thuộc schema khác, cần dùng view phù hợp với quyền được cấp, chẳng hạn ALL_* hoặc DBA_*.

### 8.1 Thu thập thống kê có kiểm soát

Ví dụ thu thập thống kê cho một bảng:

~~~sql
BEGIN
  DBMS_STATS.GATHER_TABLE_STATS(
    ownname          => 'APP',
    tabname          => 'ORDERS',
    estimate_percent => DBMS_STATS.AUTO_SAMPLE_SIZE,
    method_opt       => 'FOR ALL COLUMNS SIZE AUTO',
    cascade          => TRUE,
    degree           => DBMS_STATS.AUTO_DEGREE,
    granularity      => 'AUTO'
  );
END;
/
~~~

Một số lưu ý:

- AUTO_SAMPLE_SIZE để Oracle chọn cách lấy mẫu phù hợp.
- CASCADE => TRUE yêu cầu thu thập thống kê index liên quan.
- GRANULARITY => 'AUTO' cho Oracle chọn mức thống kê phù hợp với partitioning.
- DEGREE ảnh hưởng mức độ song song khi thu thập, cần cân nhắc tải hệ thống.
- METHOD_OPT quyết định chính sách histogram.
- Thu thập thống kê có thể làm thay đổi kế hoạch SQL; cần theo dõi các câu lệnh quan trọng sau khi publish.

Không nên chạy một lệnh gather toàn schema trong giờ cao điểm chỉ vì một SQL chậm. Hãy xác định object và thống kê đang thiếu, đánh giá phạm vi ảnh hưởng, rồi chọn thời điểm và cách triển khai phù hợp.

### 8.2 Pending statistics

Với thay đổi có nguy cơ ảnh hưởng nhiều SQL, pending statistics cho phép kiểm tra thống kê mới trong phiên thử nghiệm trước khi publish rộng rãi.

Một quy trình khái quát:

1. Đặt preference PUBLISH của object thành FALSE.
2. Thu thập thống kê mới; kết quả được lưu ở trạng thái pending.
3. Trong phiên kiểm thử, bật OPTIMIZER_USE_PENDING_STATISTICS = TRUE.
4. Chạy các SQL đại diện và so sánh kế hoạch/hiệu năng.
5. Nếu kết quả đạt yêu cầu, publish pending statistics; nếu không, bỏ pending statistics và điều tra tiếp.

Ví dụ phần thiết lập preference:

~~~sql
BEGIN
  DBMS_STATS.SET_TABLE_PREFS(
    ownname => 'APP',
    tabname => 'ORDERS',
    pname   => 'PUBLISH',
    pvalue  => 'FALSE'
  );
END;
/
~~~

Trong phiên kiểm thử:

~~~sql
ALTER SESSION SET optimizer_use_pending_statistics = TRUE;
~~~

Tên preference và thủ tục publish/delete pending statistics cần được đối chiếu với phiên bản Oracle đang vận hành. Pending statistics là công cụ kiểm soát rollout, không thay thế việc kiểm thử workload thực tế.

## 9. Dynamic statistics và các cơ chế hỗ trợ ước lượng

Khi thống kê thông thường thiếu hoặc không đủ để ước lượng một truy vấn, optimizer có thể dùng các cơ chế bổ sung.

### 9.1 Dynamic statistics

Dynamic statistics (trước đây thường được gọi là dynamic sampling) lấy mẫu dữ liệu trong giai đoạn parse/optimization để bổ sung thông tin cho một số object hoặc phép kết hợp. Cơ chế này có thể hữu ích với bảng thiếu thống kê, điều kiện phức tạp hoặc một số truy vấn mà thống kê hiện có không đủ.

Đổi lại, việc lấy mẫu có thể làm tăng chi phí parse và không phải lúc nào cũng cải thiện ước lượng. Mức dynamic statistics chịu ảnh hưởng của tham số như OPTIMIZER_DYNAMIC_SAMPLING, cấu hình và quyết định của optimizer.

Dynamic statistics không phải lý do để bỏ qua việc thu thập thống kê cơ bản. Với bảng quan trọng và workload ổn định, thống kê được quản lý đúng thường tạo nền tảng đáng tin cậy hơn.

### 9.2 Statistics feedback và adaptive behavior

Oracle có thể so sánh ước lượng với kết quả thực tế và sử dụng feedback để cải thiện ước lượng ở lần tối ưu hóa sau trong những trường hợp phù hợp. Các cơ chế như statistics feedback, adaptive cursor sharing và adaptive plans có hành vi phụ thuộc phiên bản, cấu hình và loại truy vấn.

Cần phân biệt:

- **Statistics feedback:** dùng chênh lệch giữa cardinality ước lượng và thực tế để điều chỉnh ước lượng trong lần tối ưu hóa sau khi đủ điều kiện.
- **Adaptive cursor sharing:** cho phép một SQL dùng nhiều child cursor/kế hoạch phù hợp với các nhóm bind value có selectivity khác nhau.
- **Adaptive plans:** trong một số phiên bản/cấu hình, kế hoạch có thể chứa lựa chọn phụ được quyết định trong quá trình thực thi dựa trên thông tin quan sát được.

Không nên giả định các cơ chế này luôn bật, luôn áp dụng hoặc tự sửa mọi sai lệch. Khi phân tích, hãy đọc phần Note trong execution plan và kiểm tra child cursor, bind sensitivity, feedback cùng tham số optimizer của phiên.

## 10. Cấu trúc SQL và query transformation

Optimizer không chỉ chọn operation cho câu SQL nguyên trạng. Nó có thể biến đổi truy vấn khi chứng minh được tính tương đương về ngữ nghĩa.

Một số phép biến đổi thường gặp:

- **View merging:** gộp view vào truy vấn bên ngoài để optimizer có thêm khả năng đẩy điều kiện và chọn join order.
- **Predicate pushing:** đẩy điều kiện lọc xuống gần nguồn dữ liệu để giảm số dòng phải truyền qua các operation.
- **Subquery unnesting:** chuyển một số subquery thành join hoặc cấu trúc tương đương để mở rộng lựa chọn kế hoạch.
- **OR expansion:** biến một điều kiện OR thành các nhánh phù hợp, trong một số trường hợp có thể giúp sử dụng index.
- **Join elimination:** loại bỏ một join khi ràng buộc và ngữ nghĩa chứng minh rằng join không ảnh hưởng kết quả.
- **Star transformation:** hỗ trợ một số truy vấn phân tích trên mô hình star schema.
- **Partition pruning:** bỏ qua partition không thể chứa dữ liệu thỏa điều kiện.

Không phải mọi phép biến đổi đều được áp dụng cho mọi câu SQL. Ràng buộc, tính null, kiểu join, aggregation, analytic function, hàm không xác định hoặc cấu trúc truy vấn có thể giới hạn phép biến đổi.

### 10.1 Viết điều kiện thân thiện với access path

Một điều kiện lọc có thể khiến index khó được sử dụng nếu áp dụng hàm trực tiếp lên cột.

Ví dụ:

~~~sql
-- Có thể làm index thông thường trên ORDER_DATE khó được dùng
SELECT order_id
FROM orders
WHERE TRUNC(order_date) = DATE '2026-11-14';
~~~

Có thể viết lại thành khoảng nửa mở:

~~~sql
SELECT order_id
FROM orders
WHERE order_date >= DATE '2026-11-14'
  AND order_date <  DATE '2026-11-15';
~~~

Cách viết này giữ nguyên ý nghĩa lọc theo ngày khi ORDER_DATE lưu cả phần thời gian, đồng thời tạo điều kiện cho range scan trên index thông thường nếu các yếu tố khác phù hợp.

Một lựa chọn khác là function-based index trên TRUNC(order_date) nếu biểu thức đó xuất hiện thường xuyên và phù hợp với workload. Khi thiết kế index, cần cân nhắc chi phí lưu trữ và DML.

### 10.2 Tránh implicit conversion không cần thiết

Kiểu dữ liệu của bind và literal nên phù hợp với kiểu cột. Ví dụ, nếu ORDER_ID là NUMBER, hãy bind một giá trị NUMBER thay vì gửi chuỗi rồi để Oracle chuyển đổi ngầm.

~~~sql
-- ORDER_ID là NUMBER
SELECT *
FROM orders
WHERE order_id = :order_id;
~~~

Nếu ứng dụng bind :order_id dưới kiểu VARCHAR2, Oracle có thể phải chuyển đổi dữ liệu. Tùy biểu thức và kiểu dữ liệu, phép chuyển đổi có thể ảnh hưởng khả năng dùng index, cardinality và kế hoạch.

Định dạng ngày nên được chỉ định rõ khi chuyển chuỗi thành ngày:

~~~sql
WHERE order_date >= TO_DATE(:from_date, 'YYYY-MM-DD')
~~~

Trong ứng dụng, tốt hơn là bind giá trị DATE/TIMESTAMP đúng kiểu thay vì truyền chuỗi ngày và phụ thuộc NLS_DATE_FORMAT.

### 10.3 OR, IN và subquery

Điều kiện nhiều nhánh có thể tạo ra nhiều lựa chọn kế hoạch:

~~~sql
WHERE status = 'NEW'
   OR status = 'RETURNED'
~~~

Trong một số tình huống, optimizer có thể OR-expand để tận dụng các access path riêng. Với IN, subquery và EXISTS, optimizer cũng có thể chọn semijoin, antijoin hoặc phép biến đổi khác.

Không nên tự thay mọi OR bằng UNION ALL, hoặc mọi IN bằng EXISTS, theo một quy tắc tuyệt đối. Cần giữ đúng ngữ nghĩa về NULL, duplicate và tập kết quả, sau đó đo kế hoạch thực tế.

## 11. Access path: full scan hay index?

Index là một cấu trúc giúp tìm dữ liệu nhanh trong một số trường hợp. Nó không phải đường truy cập luôn rẻ nhất.

### 11.1 Full table scan

Full scan đọc các block của bảng. Nó thường hợp lý khi:

- Truy vấn cần phần lớn dòng trong bảng.
- Bảng nhỏ.
- Điều kiện lọc không chọn lọc.
- Đọc tuần tự nhiều block rẻ hơn nhiều lần truy cập ngẫu nhiên qua index.
- Truy vấn cần tổng hợp lượng dữ liệu lớn.

Một full scan không mặc nhiên là dấu hiệu SQL tệ. Với truy vấn phân tích, full scan có thể là kế hoạch tối ưu.

### 11.2 Index range scan và table access by rowid

Index range scan phù hợp khi điều kiện xác định một khoảng key có độ chọn lọc đủ tốt. Sau khi lấy rowid, Oracle có thể truy cập table block để lấy các cột còn thiếu.

Chi phí phụ thuộc vào:

- Số key phải đọc trong index.
- Số leaf block cần duyệt.
- Clustering factor.
- Số table block phải truy cập.
- Số cột có thể lấy ngay từ index.
- Khả năng các block đã nằm trong buffer cache.

Một index có thể đáp ứng toàn bộ cột của truy vấn, khi đó Oracle có thể không cần quay lại bảng. Đây thường được gọi là covering index theo cách diễn đạt phổ biến, dù thuật ngữ trong execution plan có thể thể hiện bằng các operation cụ thể như index fast full scan.

### 11.3 Các dạng index access thường gặp

| Operation | Ý nghĩa khái quát |
|---|---|
| Index unique scan | Tìm một key duy nhất trong unique index |
| Index range scan | Đọc các key trong một khoảng |
| Index skip scan | Tận dụng index composite khi điều kiện không có cột leading, trong trường hợp phù hợp |
| Index full scan | Đọc toàn bộ index theo thứ tự key |
| Index fast full scan | Đọc toàn bộ index theo hướng tối ưu I/O, không bảo đảm thứ tự key |
| Bitmap index access | Dùng bitmap để kết hợp điều kiện, thường phù hợp workload phân tích với DML được kiểm soát |

Index composite có thứ tự cột quan trọng. Nếu index là (CUSTOMER_ID, ORDER_DATE), điều kiện trên CUSTOMER_ID thường tận dụng leading column trực tiếp. Điều kiện chỉ trên ORDER_DATE có thể cần một lựa chọn khác, như skip scan nếu phù hợp, hoặc một index khác.

Không nên tạo index chỉ dựa trên việc cột xuất hiện trong WHERE. Cần xem độ chọn lọc, thứ tự cột, truy vấn thực tế, DML, kích thước index và chi phí bảo trì.

## 12. Join order và join method

Với truy vấn nhiều bảng, thứ tự join có thể ảnh hưởng rất lớn đến lượng dữ liệu trung gian. Optimizer thường tìm cách lọc sớm và giữ các tập dữ liệu trung gian nhỏ, nhưng quyết định cụ thể phụ thuộc cardinality và ràng buộc của truy vấn.

### 12.1 Nested loops

Nested loops thường phù hợp khi tập ngoài nhỏ và tập trong có access path hiệu quả.

Mô hình đơn giản:

1. Lấy một dòng từ tập ngoài.
2. Dùng giá trị dòng đó để tìm dòng khớp trong tập trong.
3. Lặp lại cho dòng tiếp theo của tập ngoài.

Ví dụ, lấy một khách hàng theo khóa duy nhất rồi tìm các đơn hàng của khách hàng đó qua index ORDERS(CUSTOMER_ID) có thể là trường hợp tốt cho nested loops.

Nếu optimizer đánh giá tập ngoài chỉ có 10 dòng nhưng thực tế có 500.000 dòng, nested loops có thể gây ra rất nhiều lần truy cập vào tập trong. Sai lệch cardinality ở nhánh ngoài là một nguyên nhân thường gặp.

### 12.2 Hash join

Hash join thường phù hợp khi cần nối hai tập tương đối lớn và điều kiện nối hỗ trợ hash join.

Mô hình đơn giản:

1. Chọn một tập làm build input.
2. Đọc tập build và xây dựng hash table theo join key.
3. Đọc tập còn lại (probe input), tính hash key và tìm phần tử khớp.

Kích thước tập build, độ rộng dòng, bộ nhớ PGA và số dòng thực tế ảnh hưởng hiệu quả. Nếu hash area không đủ, operation có thể spill ra temporary tablespace, làm tăng I/O và thời gian.

Hash join không đòi hỏi index trên join key để hoạt động. Vì vậy, việc không có index trên cột nối không đồng nghĩa truy vấn chắc chắn chậm.

### 12.3 Sort merge join

Sort merge join sắp xếp hai tập theo join key (hoặc tận dụng dữ liệu đã có thứ tự), sau đó ghép các dòng theo thứ tự. Nó có thể phù hợp với tập dữ liệu lớn, một số kiểu điều kiện nối hoặc khi đầu vào đã được sắp xếp.

Không có quy tắc đơn giản rằng nested loops dành cho bảng nhỏ, hash join dành cho bảng lớn và sort merge chỉ dùng khi không có index. Optimizer cân nhắc cardinality, access path, thứ tự dữ liệu, điều kiện nối, memory và cost.

### 12.4 Join order

Giả sử truy vấn nối CUSTOMERS, ORDERS và ORDER_ITEMS. Nếu CUSTOMERS được lọc xuống 100 dòng trước, rồi join với ORDERS, tập trung gian có thể nhỏ hơn nhiều so với việc đọc toàn bộ ORDER_ITEMS trước.

Nhưng nếu điều kiện lọc trên CUSTOMERS không chọn lọc, hoặc bảng ORDERS đã được giới hạn bởi một partition rất nhỏ, thứ tự khác có thể rẻ hơn.

Khi thấy join order bất ngờ, hãy kiểm tra cardinality tại từng nhánh trước khi kết luận optimizer chọn sai. Một join method có vẻ không phù hợp thường là hệ quả của ước lượng sai ở operation phía dưới.

## 13. Partition pruning và parallel execution

Partitioning thay một bảng logic thành các partition vật lý theo một chiến lược như RANGE, LIST, HASH hoặc kết hợp. Nếu điều kiện truy vấn cho phép xác định partition cần đọc, Oracle có thể pruning các partition không liên quan.

Ví dụ bảng ORDERS partition theo tháng trên ORDER_DATE:

~~~sql
SELECT COUNT(*)
FROM orders
WHERE order_date >= DATE '2026-10-01'
  AND order_date <  DATE '2026-11-01';
~~~

Điều kiện trên cột partition key theo khoảng rõ ràng giúp optimizer và execution engine xác định phạm vi partition phù hợp. Nếu bọc cột trong biểu thức hoặc dùng kiểu dữ liệu không tương thích, khả năng pruning có thể bị hạn chế tùy biểu thức và cấu trúc partition.

Parallel execution cho phép nhiều process xử lý một phần công việc. Nó có thể giảm elapsed time cho truy vấn lớn, nhưng tiêu thụ nhiều CPU, I/O, memory và tài nguyên đồng thời. Parallel không tự động tốt hơn serial; một truy vấn nhỏ có thể tốn thêm thời gian điều phối.

Các đầu vào liên quan gồm degree of parallelism, chính sách parallel, giới hạn Resource Manager, kích thước dữ liệu, khả năng I/O và số truy vấn chạy đồng thời. Khi xem kế hoạch parallel, cần chú ý operation phân phối dữ liệu như PX SEND/PX RECEIVE, số lượng process và điểm tập trung dữ liệu.

## 14. Bind variables, bind peeking và adaptive cursor sharing

Bind variables giúp tái sử dụng SQL và giảm hard parse do literal khác nhau. Tuy nhiên, cùng một SQL với các bind value khác nhau có thể có selectivity rất khác nhau.

Ví dụ:

~~~sql
SELECT order_id, order_date
FROM orders
WHERE status = :status;
~~~

Nếu :status = 'NEW' trả 70% bảng còn :status = 'RETURNED' trả 0,1%, một kế hoạch duy nhất có thể không tối ưu cho cả hai trường hợp.

### 14.1 Bind peeking

Trong một số lần hard parse, Oracle có thể peek giá trị bind hiện tại để ước lượng selectivity và tạo kế hoạch. Kế hoạch ban đầu có thể phù hợp với giá trị đã peek nhưng không phù hợp với các giá trị về sau.

Đây là một lý do SQL có thể chạy nhanh với một bind value nhưng chậm với giá trị khác, dù SQL text giống nhau.

### 14.2 Adaptive cursor sharing

Adaptive cursor sharing cho phép Oracle nhận biết một số SQL là bind-sensitive/bind-aware và tạo các child cursor khác nhau cho những nhóm bind value có đặc tính selectivity khác nhau.

Điều này có thể cải thiện hiệu năng cho workload có phân bố bind lệch. Tuy nhiên, không nên mặc định rằng Oracle sẽ luôn tạo đúng số child cursor cần thiết hoặc tự động giải quyết mọi trường hợp. Cần kiểm tra các child cursor, bind capture/peeked binds và execution statistics.

### 14.3 Ứng dụng cần làm gì?

- Dùng bind đúng kiểu dữ liệu của cột.
- Không chuyển mọi truy vấn sang literal chỉ để ép kế hoạch thay đổi.
- Xem nhiều lần thực thi với bind value đại diện cho các nhóm dữ liệu khác nhau.
- Kiểm tra child cursor và lý do không share cursor khi có nhiều child.
- Đánh giá histogram trên cột bind nếu phân bố lệch và workload thực sự cần.
- Kiểm thử cả trường hợp phổ biến lẫn trường hợp hiếm nhưng có cardinality rất khác.

## 15. Các tham số và môi trường ảnh hưởng đến optimizer

Kế hoạch có thể phụ thuộc vào nhiều yếu tố ngoài SQL text:

- **OPTIMIZER_MODE:** mục tiêu tối ưu như ALL_ROWS hoặc FIRST_ROWS_n.
- **OPTIMIZER_FEATURES_ENABLE:** mức tính năng optimizer tương thích với phiên bản được chỉ định.
- **OPTIMIZER_DYNAMIC_SAMPLING:** mức dynamic statistics.
- Các tham số adaptive liên quan, tùy phiên bản Oracle.
- **CURSOR_SHARING:** cách xử lý literal và cursor sharing.
- **STATISTICS_LEVEL:** mức thu thập một số runtime statistics.
- Degree of parallelism và chính sách parallel.
- NLS settings, kiểu dữ liệu bind, schema hiện hành và object resolution.
- Thống kê object/system và metadata như constraint, index, partition.
- Quyền, synonym và cấu trúc object có thể ảnh hưởng việc phân giải SQL.

Không nên thay đổi tham số optimizer ở cấp hệ thống chỉ để chữa một câu SQL mà chưa chứng minh nguyên nhân. Nếu cần thử nghiệm, có thể kiểm tra ở session hoặc SQL-level khi phù hợp, sau đó đánh giá ảnh hưởng đến workload liên quan.

OPTIMIZER_FEATURES_ENABLE đặc biệt cần thận trọng. Hạ hoặc nâng mức tương thích có thể thay đổi hành vi optimizer của nhiều SQL, không chỉ câu đang điều tra.

## 16. Hints: công cụ điều khiển có chủ đích

Hints cho phép đưa chỉ dẫn vào SQL, ví dụ gợi ý join order, join method, access path hoặc parallelism.

Ví dụ cú pháp:

~~~sql
SELECT /*+ LEADING(c o) USE_NL(o) INDEX(o ORDERS_CUSTOMER_IX) */
       c.customer_id, o.order_id
FROM customers c
JOIN orders o
  ON o.customer_id = c.customer_id
WHERE c.customer_id = :customer_id;
~~~

Hint có thể hữu ích khi đã có bằng chứng rõ ràng rằng optimizer không chọn được kế hoạch phù hợp trong một tình huống cụ thể, hoặc khi cần kiểm thử giả thuyết về kế hoạch.

Nhưng hints có các rủi ro:

- Dữ liệu và phân bố thay đổi khiến giả định ban đầu không còn đúng.
- Index hoặc alias thay đổi khiến hint không còn áp dụng như dự định.
- Hint có thể bị bỏ qua nếu sai cú pháp, sai tên object hoặc không hợp lệ trong ngữ cảnh.
- Ép một access path có thể làm một nhóm bind value khác chậm hơn.
- Hint làm tăng chi phí bảo trì SQL và khiến hành vi khó giải thích khi hệ thống thay đổi.

Nếu dùng hint, hãy kiểm tra execution plan và phần Hint Report (nếu phiên bản/format hỗ trợ) để biết hint có được chấp nhận hay bị bỏ qua. Không suy luận rằng chỉ cần viết hint là Oracle chắc chắn thực hiện đúng ý định.

## 17. Giữ ổn định kế hoạch với SQL Plan Management

Sau khi đã xác định một kế hoạch tốt và muốn giảm rủi ro kế hoạch thay đổi ngoài ý muốn, Oracle cung cấp SQL Plan Management (SPM).

Các khái niệm cần phân biệt:

- **SQL Plan Baseline:** tập các execution plan được chấp nhận cho SQL. Optimizer có thể dùng các plan được chấp nhận và quản lý quá trình plan evolution.
- **SQL Profile:** cung cấp thông tin hỗ trợ ước lượng/costing để optimizer tạo kế hoạch phù hợp hơn; bản thân profile không đơn giản là lệnh khóa một execution plan.
- **SQL Patch:** gắn một số hint vào SQL thông qua cơ chế quản trị, hữu ích trong một số tình huống điều chỉnh có kiểm soát.
- **Stored Outline:** cơ chế cũ hơn, có thể xuất hiện trong hệ thống legacy.

SPM giúp kiểm soát thay đổi kế hoạch, nhưng không thay thế việc hiểu nguyên nhân. Một baseline giữ kế hoạch cũ có thể bảo vệ workload trong giai đoạn chuyển đổi, song kế hoạch đó vẫn có thể trở nên kém hiệu quả khi dữ liệu hoặc workload thay đổi.

Trước khi cố định kế hoạch, cần xác nhận nó tốt trên tập bind value và dữ liệu đại diện, theo dõi sau khi triển khai, và có phương án thay đổi baseline khi điều kiện thực tế khác đi.

## 18. Đọc execution plan để xác minh giả định

EXPLAIN PLAN tạo một kế hoạch dự kiến mà không thực thi câu SQL. Nó hữu ích để xem một khả năng kế hoạch, nhưng có thể khác kế hoạch của cursor thực tế do bind, child cursor, session settings, thống kê hoặc môi trường parse.

Khi điều tra SQL đã chạy, nên xem cursor thực tế bằng DBMS_XPLAN.DISPLAY_CURSOR.

Ví dụ, thêm hint thu thập row-source statistics cho lần chạy kiểm thử:

~~~sql
SELECT /*+ gather_plan_statistics */
       order_id, order_date
FROM orders
WHERE status = 'RETURNED';
~~~

Sau khi chạy xong, xem kế hoạch của cursor gần nhất trong session:

~~~sql
SELECT *
FROM TABLE(
  DBMS_XPLAN.DISPLAY_CURSOR(
    NULL,
    NULL,
    'ALLSTATS LAST +PEEKED_BINDS +PREDICATE +ALIAS +NOTE'
  )
);
~~~

Trong hệ thống nhiều session hoặc nhiều child cursor, nên xác định đúng SQL_ID và child number thay vì phụ thuộc NULL, NULL.

Một số cột/thành phần đáng chú ý:

| Thành phần | Cách đọc |
|---|---|
| E-Rows | Số dòng optimizer ước lượng |
| A-Rows | Số dòng thực tế ghi nhận cho lần thực thi có statistics |
| Starts | Số lần operation được bắt đầu |
| Buffers | Logical reads/buffer gets được ghi nhận |
| Reads | Physical reads được ghi nhận |
| A-Time | Thời gian thực tế của operation theo thống kê thu thập |
| TempSpc | Thông tin vùng temporary sử dụng/ước lượng tùy format |
| Predicate Information | Điều kiện access và filter |
| Peeked Binds | Giá trị bind được peek khi cursor được parse, nếu có |
| Note | Thông tin bổ sung như dynamic statistics, adaptive plan hoặc lý do liên quan |

ALLSTATS LAST cần row-source statistics được thu thập cho lần thực thi. Có thể dùng /*+ gather_plan_statistics */ cho câu kiểm thử hoặc cấu hình thống kê phù hợp trong môi trường được kiểm soát. Thu thập runtime statistics cho mọi SQL trong production mà không cân nhắc overhead là không nên.

### 18.1 So sánh E-Rows và A-Rows

Đây là bước quan trọng để tìm sai lệch cardinality.

- Nếu E-Rows gần A-Rows, ước lượng tại operation đó tương đối sát.
- Nếu E-Rows nhỏ hơn A-Rows nhiều lần, optimizer đã đánh giá thấp lượng dữ liệu.
- Nếu E-Rows lớn hơn A-Rows nhiều lần, optimizer đã đánh giá quá cao lượng dữ liệu.

Với operation chạy nhiều lần, cần xem Starts và cách format thể hiện số dòng. Chẳng hạn inner side của nested loops có thể được bắt đầu nhiều lần; chỉ nhìn A-Rows mà không xét Starts dễ dẫn đến kết luận sai.

Hãy tìm **điểm sai lệch đầu tiên** từ dưới lên trong cây plan. Nếu operation đầu tiên đã ước lượng sai rất lớn, các operation cha có thể chỉ đang phản ánh sai lệch đó. Điều tra operation đầu tiên thường hiệu quả hơn việc chỉnh join method ở operation trên cùng.

### 18.2 Access predicate và filter predicate

Predicate Information có thể cho biết điều kiện nào được dùng để truy cập index/table và điều kiện nào chỉ lọc sau khi dữ liệu đã được đọc.

- **Access predicate:** tham gia xác định vùng dữ liệu cần truy cập.
- **Filter predicate:** lọc dòng sau khi operation đã lấy được đầu vào.

Một điều kiện xuất hiện trong filter không nhất thiết sai. Nhưng nếu điều kiện rất chọn lọc chỉ được áp dụng sau khi đã đọc nhiều dữ liệu, có thể cần xem lại index, cách viết predicate hoặc khả năng query transformation.

### 18.3 Đừng chỉ nhìn cost trong plan

Khi so sánh hai kế hoạch, hãy xem cả:

- Số dòng thực tế và estimated rows.
- Starts của các operation.
- Buffers và physical reads.
- Thời gian elapsed/CPU trong cùng điều kiện thử nghiệm.
- Temporary I/O, spill và parallel distribution.
- Số lần parse, số child cursor và bind value.
- Ảnh hưởng đến các SQL khác cùng dùng object/index.

Một plan có cost thấp hơn chưa chắc chạy nhanh hơn trong workload thực tế nếu thống kê, cache, concurrency hoặc môi trường thử khác biệt.

## 19. Quy trình điều tra một SQL có kế hoạch kém

Một quy trình thực tế có thể đi theo thứ tự sau.

### Bước 1: Xác định chính xác câu SQL và cursor

Thu thập SQL text, SQL_ID, child number, plan hash value, schema, module/action, thời điểm chạy, bind value đại diện và session environment. Nếu SQL có nhiều child cursor, không gộp chúng thành một kế hoạch duy nhất.

### Bước 2: Lấy execution plan thực tế

Dùng DBMS_XPLAN.DISPLAY_CURSOR với runtime statistics nếu có. Xác định plan đang được thực thi, không chỉ dựa vào một EXPLAIN PLAN được chạy trong session khác.

### Bước 3: Tìm sai lệch cardinality đầu tiên

So sánh E-Rows và A-Rows, xem Starts, rồi tìm operation thấp nhất có sai lệch đáng kể. Đặt câu hỏi: sai lệch xuất phát từ predicate, join, thống kê cột, tương quan giữa cột, bind hay dữ liệu thay đổi?

### Bước 4: Kiểm tra thống kê liên quan

Kiểm tra table/partition, column, histogram, index và system statistics. Xem LAST_ANALYZED, stale status, NDV, NULL count, histogram type, clustering factor và phân bố dữ liệu thực tế.

Không chỉ kiểm tra thống kê của bảng lớn nhất. Một bảng nhỏ được ước lượng sai ở đầu nhánh join cũng có thể làm optimizer chọn join order không phù hợp.

### Bước 5: Kiểm tra SQL và kiểu dữ liệu

Xem implicit conversion, hàm trên cột, bind datatype, điều kiện có sargable không, join predicate có đúng kiểu dữ liệu không, và query transformation có bị giới hạn bởi cấu trúc truy vấn không.

### Bước 6: So sánh với bind value khác

Nếu SQL dùng bind, chạy thử với nhóm giá trị phổ biến, hiếm và có selectivity khác nhau. Kiểm tra bind peeking, bind sensitivity và child cursor. Một kế hoạch tốt cho bind hiếm có thể không tốt cho bind phổ biến.

### Bước 7: Thử giả thuyết trong môi trường kiểm soát

Có thể thử cập nhật thống kê, extended statistics, histogram, viết lại predicate hoặc một access path khác. Với thay đổi thống kê có ảnh hưởng rộng, cân nhắc pending statistics. Ghi lại kế hoạch và runtime trước/sau trong cùng điều kiện.

### Bước 8: Chọn cơ chế ổn định phù hợp

Nếu kế hoạch đã được xác nhận tốt và cần kiểm soát biến động, đánh giá SQL Plan Management. Nếu cần sửa sai lệch ước lượng, tập trung vào statistics/profile phù hợp. Chỉ dùng hint hoặc SQL Patch khi có lý do cụ thể và kế hoạch kiểm tra, bảo trì.

### Bước 9: Theo dõi sau thay đổi

Theo dõi elapsed time, CPU, logical/physical reads, child cursor, plan hash và các SQL liên quan. Một thay đổi cải thiện một truy vấn nhưng làm nhiều truy vấn khác chậm đi vẫn có thể là thay đổi xấu ở cấp hệ thống.

## 20. Ví dụ tổng hợp: truy vấn đơn hàng có phân bố STATUS lệch

Giả sử hệ thống có bảng:

~~~sql
CREATE TABLE orders (
  order_id     NUMBER        NOT NULL,
  customer_id  NUMBER        NOT NULL,
  order_date   DATE          NOT NULL,
  status       VARCHAR2(20)  NOT NULL,
  total_amount NUMBER(12,2),
  CONSTRAINT orders_pk PRIMARY KEY (order_id)
);

CREATE INDEX orders_status_ix
    ON orders(status);

CREATE INDEX orders_customer_date_ix
    ON orders(customer_id, order_date);
~~~

Dữ liệu có 10 triệu dòng. STATUS phân bố như sau:

- NEW: 70%.
- PAID: 25%.
- CANCELLED: 4,9%.
- RETURNED: 0,1%.

Ứng dụng chạy:

~~~sql
SELECT order_id, order_date, total_amount
FROM orders
WHERE status = :status;
~~~

### Trường hợp A: bind là NEW

Truy vấn cần khoảng 7 triệu dòng. Dùng index ORDERS_STATUS_IX rồi quay lại bảng hàng triệu lần có thể tốn kém. Full table scan có thể hợp lý hơn vì database phải đọc phần lớn bảng.

### Trường hợp B: bind là RETURNED

Truy vấn chỉ cần khoảng 10.000 dòng. Index có thể giảm lượng dữ liệu cần đọc đáng kể, đặc biệt nếu clustering factor và số block truy cập phù hợp.

### Vì sao một SQL có thể có hai kế hoạch?

Nếu optimizer dùng giả định phân bố đồng đều, nó có thể ước lượng sai cả hai nhóm. Histogram giúp mô tả độ lệch. Bind peeking và adaptive cursor sharing có thể giúp Oracle nhận biết rằng các bind value thuộc nhóm selectivity khác nhau và cần child cursor phù hợp.

### Cách điều tra

1. Xem ALLSTATS LAST cho từng bind value trong môi trường thử nghiệm.
2. So sánh E-Rows với A-Rows ở filter trên STATUS.
3. Kiểm tra histogram của STATUS và thời điểm thu thập thống kê.
4. Xem index statistics, đặc biệt CLUSTERING_FACTOR.
5. Kiểm tra các child cursor và bind sensitivity.
6. Đánh giá tổng tài nguyên cho cả bind phổ biến lẫn hiếm.
7. Chỉ sau đó mới quyết định có cần histogram, statistics refresh, SQL Plan Management hoặc biện pháp khác.

Ví dụ này cho thấy không tồn tại một access path luôn tốt cho mọi giá trị của bind. Kế hoạch phải được đánh giá theo phân bố dữ liệu và cách ứng dụng thực sự gọi SQL.

## 21. Những hiểu lầm thường gặp

| Nhận định | Cách hiểu chính xác |
|---|---|
| Có index thì Oracle phải dùng index | Index chỉ là một access path; full scan có thể rẻ hơn |
| Full table scan luôn là kế hoạch xấu | Full scan phù hợp khi cần đọc nhiều dòng hoặc bảng nhỏ |
| Cost 100 nghĩa là 100 ms | Cost là thước đo nội bộ, không phải thời gian thực |
| Gather statistics càng thường xuyên càng tốt | Cần thu thập khi dữ liệu/metadata thay đổi đủ đáng kể và theo lịch phù hợp |
| Histogram luôn cải thiện hiệu năng | Histogram cải thiện một số ước lượng nhưng có thể làm kế hoạch thay đổi và cần kiểm soát |
| Một SQL chỉ có một execution plan | Một SQL có thể có nhiều child cursor và nhiều kế hoạch |
| Bind variables luôn làm kế hoạch tốt hơn | Bind giúp cursor sharing; bind peeking và skew có thể tạo vấn đề cần xử lý |
| Nested loops luôn dành cho bảng nhỏ | Nó phụ thuộc cardinality, access path và số lần lặp |
| Hash join luôn nhanh hơn nested loops | Mỗi join method phù hợp với một kiểu dữ liệu và workload |
| Hint luôn được áp dụng | Hint có thể bị bỏ qua hoặc không hợp lệ; cần xác minh trong plan |
| EXPLAIN PLAN chính là kế hoạch đã chạy | Kế hoạch cursor thực tế có thể khác do bind, child cursor và môi trường |
| Optimizer tự sửa mọi sai lệch | Adaptive/feedback mechanisms có phạm vi và điều kiện áp dụng cụ thể |

## 22. Checklist khi phân tích quyết định của CBO

Khi một SQL có kế hoạch bất thường hoặc hiệu năng thay đổi, hãy lần lượt xác nhận:

- [ ] Đã lấy đúng SQL_ID, child cursor và execution plan thực tế.
- [ ] Đã ghi nhận bind value và datatype được ứng dụng gửi.
- [ ] Đã so sánh E-Rows, A-Rows và Starts.
- [ ] Đã tìm operation đầu tiên có sai lệch cardinality đáng kể.
- [ ] Đã kiểm tra table, partition, column, histogram và index statistics.
- [ ] Đã kiểm tra độ lệch dữ liệu và tương quan giữa các cột.
- [ ] Đã xem clustering factor và chi phí truy cập table block qua index.
- [ ] Đã kiểm tra predicate, implicit conversion và hàm áp dụng lên cột.
- [ ] Đã xem join order, join method và kích thước tập trung gian.
- [ ] Đã kiểm tra partition pruning, parallelism và temporary I/O nếu có.
- [ ] Đã xem child cursor, bind peeking và adaptive cursor sharing khi SQL dùng bind.
- [ ] Đã thử thay đổi trong môi trường có thể so sánh trước/sau.
- [ ] Đã đánh giá ảnh hưởng đến các SQL khác dùng cùng object hoặc thống kê.

## 23. Kết luận

Cost-based optimizer lựa chọn execution plan dựa trên ước lượng dữ liệu và tài nguyên. Các đầu vào quan trọng gồm SQL và query transformations, table/column/index/partition statistics, histogram, extended statistics, system statistics, bind value, cấu hình optimizer và môi trường thực thi.

Khi kế hoạch không phù hợp, hãy bắt đầu từ cardinality: xác định operation nào được ước lượng sai đầu tiên, tìm đầu vào khiến sai lệch xuất hiện, rồi kiểm chứng bằng execution statistics. Thống kê chính xác, predicate rõ ràng và hiểu đúng phân bố dữ liệu thường tạo nền tảng tốt hơn cho optimizer. Hints và plan management là các công cụ kiểm soát bổ sung khi có bằng chứng và mục tiêu vận hành cụ thể.

