# Dynamic statistics, cardinality feedback và khác biệt theo phiên bản Oracle Database

Khi tối ưu một câu SQL, Oracle không biết trước chính xác mỗi bước sẽ trả về bao nhiêu dòng. Optimizer phải **ước lượng cardinality** dựa trên thống kê bảng, cột, index, histogram, biểu thức và các thông tin liên quan. Ước lượng này ảnh hưởng đến thứ tự join, join method, access path, độ song song, memory và chi phí của execution plan.

Nếu ước lượng sai đáng kể, optimizer có thể chọn một kế hoạch rất đắt. Ví dụ, optimizer nghĩ một predicate chỉ trả 10 dòng nhưng thực tế trả 500.000 dòng. Một nested loops join được chọn dựa trên giả định 10 dòng có thể trở nên tốn kém khi phải thực hiện hàng trăm nghìn lần lookup.

Oracle có một số cơ chế để cải thiện thông tin cardinality:

- **Dynamic statistics** (tên cũ là dynamic sampling): lấy mẫu block dữ liệu trong lúc parse để bổ sung ước lượng khi thống kê hiện có thiếu hoặc chưa đủ.
- **Statistics feedback** (tên cũ là cardinality feedback): so sánh cardinality ước lượng với số dòng thực tế sau execution, rồi dùng feedback để tối ưu lại các lần chạy sau.
- **SQL plan directives:** ghi nhớ những dạng predicate/biểu thức mà optimizer thường ước lượng sai, để áp dụng dynamic statistics hoặc hỗ trợ thu thập extended statistics cho những câu SQL có cấu trúc tương tự.
- **Adaptive cursor sharing:** với SQL có bind variable và độ chọn lọc thay đổi mạnh theo giá trị bind, Oracle có thể tạo các child cursor với plan khác nhau.

Các cơ chế này liên quan nhưng không giống nhau. Dynamic statistics bổ sung thông tin trước khi chọn plan; statistics feedback học từ execution trước; SQL plan directive lưu kinh nghiệm ở mức query expression; adaptive cursor sharing xử lý vấn đề cùng một SQL text nhưng bind values có độ chọn lọc khác nhau.

Tài liệu này giải thích cách hoạt động, cách quan sát execution plan, các tham số/hint quan trọng và những thay đổi theo phiên bản từ Oracle Database 11g đến Oracle AI Database 26ai.

## 1. Cardinality là gì và vì sao quan trọng?

Cardinality của một operation là số dòng mà operation đó trả về. Trong execution plan, optimizer hiển thị cardinality ước lượng ở cột **Rows** hoặc **E-Rows**. Khi có runtime statistics, số dòng thực tế thường xuất hiện ở cột **A-Rows**.

Ví dụ:

~~~text
| Id | Operation          | E-Rows | A-Rows |
|----|--------------------|-------:|-------:|
|  3 | TABLE ACCESS FULL  |     10 | 500000 |
|  2 | NESTED LOOPS       |     10 | 500000 |
|  1 | SELECT STATEMENT   |     10 | 500000 |
~~~

Optimizer dự kiến chỉ có 10 dòng, nhưng thực tế có 500.000 dòng. Sai lệch này có thể làm thay đổi đáng kể chi phí thực tế:

- Nested loops có thể thực hiện quá nhiều lần truy cập bảng/index phía trong.
- Hash join có thể được chọn với kích thước build/probe không phù hợp.
- Sort hoặc hash aggregation có thể cần nhiều memory và spill ra TEMP.
- Join order có thể đặt bảng lớn ở vị trí không phù hợp.
- Parallel execution có thể chọn DOP hoặc distribution method không tốt.

Cardinality sai không tự động chứng minh optimizer chọn plan sai; cần xem toàn bộ plan, dữ liệu, buffers, elapsed time và operation thực tế. Tuy nhiên, chênh lệch lớn giữa E-Rows và A-Rows là tín hiệu quan trọng để điều tra.

### 1.1 Selectivity và cardinality

Selectivity là tỷ lệ dòng thỏa mãn một điều kiện. Một công thức khái niệm:

\[
\text{Cardinality} \approx \text{Table rows} \times \text{Selectivity}
\]

Nếu bảng có 1.000.000 dòng và predicate có selectivity 0,01 (1%), cardinality ước lượng là khoảng 10.000 dòng.

Với equality predicate trên một cột, khi không có histogram và phân bố được giả định tương đối đồng đều, optimizer có thể ước lượng gần đúng bằng:

\[
\text{Selectivity} \approx \frac{1}{NDV}
\]

Trong đó NDV là số giá trị phân biệt của cột. Ví dụ một cột có NDV = 100 thì equality predicate có selectivity ước lượng khoảng 1%, nếu không có thông tin phân bố khác.

Giả định đồng đều có thể sai khi dữ liệu bị skew. Một giá trị có thể xuất hiện trong 70% số dòng, trong khi phần lớn giá trị khác chỉ xuất hiện rất ít. Histogram giúp optimizer hiểu phân bố lệch này.

### 1.2 Thống kê optimizer có những gì?

Optimizer dùng nhiều nhóm thống kê:

| Nhóm | Ví dụ | Ảnh hưởng |
|---|---|---|
| Table statistics | NUM_ROWS, BLOCKS, AVG_ROW_LEN | Ước lượng kích thước bảng và chi phí scan |
| Column statistics | NDV, NUM_NULLS, LOW_VALUE, HIGH_VALUE | Ước lượng selectivity |
| Histogram | Frequency, top-frequency, hybrid, height-balanced | Mô tả phân bố lệch/skew |
| Extended statistics | Column group, expression statistics | Mô tả tương quan giữa cột hoặc biểu thức |
| Index statistics | LEAF_BLOCKS, BLEVEL, CLUSTERING_FACTOR | Ước lượng chi phí truy cập index |
| System statistics | CPU và I/O characteristics | So sánh chi phí CPU/I/O của các plan |

Dynamic statistics và feedback bổ sung cho thông tin optimizer đã có. Chúng không phải giải pháp thay thế cho việc thu thập thống kê cơ bản bằng DBMS_STATS.

### 1.3 Tương quan giữa nhiều cột

Giả sử bảng CUSTOMERS có hai cột:

- CITY
- STATE_PROVINCE

Trong dữ liệu thực tế, Los Angeles thuộc California. Hai predicate sau có tương quan:

~~~sql
WHERE city = 'Los Angeles'
  AND state_province = 'CA'
~~~

Nếu optimizer ước lượng hai điều kiện độc lập, nó có thể nhân selectivity của từng cột và ước lượng số dòng thấp hơn nhiều so với thực tế. Extended column-group statistics có thể mô tả mối tương quan này.

Dynamic statistics có thể lấy mẫu để ước lượng tốt hơn trong một số trường hợp; statistics feedback có thể phát hiện sai lệch sau execution; SQL plan directive có thể ghi nhận query expression cần thêm thông tin. Mỗi cơ chế giải quyết một thời điểm và phạm vi khác nhau.

## 2. Dynamic statistics (dynamic sampling)

Dynamic statistics là kỹ thuật optimizer thực thi một recursive SQL để quét một mẫu ngẫu nhiên nhỏ các block của bảng trong giai đoạn parse/optimization. Từ mẫu này, optimizer ước lượng predicate selectivity và cardinality để bổ sung thông tin còn thiếu.

Trước Oracle Database 12c Release 1 (12.1), tính năng này có tên **dynamic sampling**. Từ 12.1, tên được đổi thành **dynamic statistics** để nhấn mạnh đây là thông tin thống kê được thu thập động trong lúc tối ưu.

Dynamic statistics không phải thao tác gather statistics đầy đủ vào data dictionary giống DBMS_STATS.GATHER_TABLE_STATS. Nó giúp optimizer có thêm thông tin cho câu SQL đang được parse và có thể chia sẻ/tái sử dụng kết quả trong những tình huống phù hợp.

### 2.1 Khi nào optimizer cân nhắc dynamic statistics?

Các trường hợp thường gặp:

- Bảng chưa có optimizer statistics.
- Thống kê hiện có bị thiếu hoặc không đủ cho predicate phức tạp.
- Predicate kết hợp nhiều điều kiện AND/OR trên cùng bảng.
- Predicate dùng biểu thức mà optimizer khó ước lượng selectivity.
- Các cột có tương quan hoặc dữ liệu skew mà thống kê cơ bản chưa mô tả đủ.
- Câu SQL chạy parallel hoặc có SQL plan directive phù hợp.

Optimizer tự quyết định có lấy mẫu hay không dựa trên thống kê hiện có, dynamic statistics level, cấu trúc câu SQL và các yếu tố khác. Việc tham số khác 0 không có nghĩa mọi câu SQL đều thực hiện sampling.

### 2.2 Quy trình hoạt động

~~~text
SQL statement được parse
          |
          v
Optimizer đọc object/column/index statistics
          |
          v
Đánh giá thông tin hiện có có đủ không
          |
      +---+---+
      |       |
     Đủ     Chưa đủ hoặc có directive
      |       |
      v       v
Ước lượng   Chọn table/operation phù hợp
bằng stats        |
                  v
          Recursive SQL lấy mẫu block
                  |
                  v
          Ước lượng selectivity/cardinality
                  |
                  v
          Bổ sung thông tin cho optimizer
                  |
                  v
          So sánh cost và chọn execution plan
~~~

Mẫu được lấy trong giai đoạn tối ưu hóa. Chi phí sampling thường làm tăng parse time, đổi lại optimizer có thể chọn plan tốt hơn cho execution. Với câu SQL chạy lâu hoặc chạy nhiều lần, chi phí parse bổ sung có thể nhỏ so với lợi ích execution. Với truy vấn OLTP rất ngắn và chỉ chạy một lần, sampling có thể làm tăng latency tổng.

### 2.3 Dynamic statistics bổ sung chứ không thay thế statistics

Optimizer vẫn ưu tiên dùng thống kê chuẩn khi thông tin đó đủ tốt. Dynamic statistics được dùng để bổ sung các ước lượng mà thống kê hiện có chưa mô tả tốt, ví dụ predicate cardinality, join cardinality hoặc GROUP BY cardinality trong các trường hợp phù hợp.

Khi bảng chưa có statistics, dynamic sampling chỉ tạo một ước lượng cơ bản trong giới hạn thời gian parse; nó không nhất thiết đầy đủ hoặc chính xác như DBMS_STATS thu thập statistics có kiểm soát.

### 2.4 Chi phí và giới hạn

- Recursive sampling thêm công việc trong parse/hard parse.
- Mẫu nhỏ có thể không đại diện hoàn hảo cho dữ liệu hiếm hoặc phân bố lệch mạnh.
- Với workload nhiều hard parse, chi phí sampling lặp lại có thể đáng kể.
- Kết quả không phải persistent table statistics thay thế histogram/extended statistics.
- Dynamic statistics không được dùng cho mọi loại câu SQL; Oracle ghi nhận các giới hạn theo cấu trúc truy vấn, ví dụ truy vấn có AS OF clause.
- Cần xem note trong execution plan để xác nhận optimizer có dùng dynamic statistics hay không.

## 3. Dynamic statistics level

Tham số OPTIMIZER_DYNAMIC_SAMPLING (tên vẫn được giữ trong Oracle Database hiện đại) điều khiển điều kiện và kích thước mẫu dynamic statistics. Có thể đặt ở system, session hoặc statement hint.

Giá trị hợp lệ là 0 đến 11. Mức mặc định thông dụng là **2** khi OPTIMIZER_FEATURES_ENABLE từ 10.0.0 trở lên.

### 3.1 Ý nghĩa các level

Bảng sau tóm tắt hành vi của các level theo SQL Tuning Guide:

| Level | Khi optimizer lấy dynamic statistics | Sample size |
|---:|---|---:|
| 0 | Không dùng dynamic statistics | Không áp dụng |
| 1 | Bảng nonpartitioned không có statistics, không có index và đáp ứng điều kiện số block | 32 blocks |
| 2 | Ít nhất một bảng trong statement không có statistics; đây là mặc định | 64 blocks |
| 3 | Điều kiện level 2 hoặc có expression trong WHERE predicate | 64 blocks |
| 4 | Điều kiện level 3 hoặc có complex predicates AND/OR trên cùng bảng | 64 blocks |
| 5 | Cùng tiêu chí level 4, mẫu lớn hơn | 128 blocks |
| 6 | Cùng tiêu chí level 4, mẫu lớn hơn | 256 blocks |
| 7 | Cùng tiêu chí level 4, mẫu lớn hơn | 512 blocks |
| 8 | Cùng tiêu chí level 4, mẫu lớn hơn | 1.024 blocks |
| 9 | Cùng tiêu chí level 4, mẫu lớn hơn | 4.086 blocks |
| 10 | Cùng tiêu chí level 4, quét toàn bộ blocks | All blocks |
| 11 | Adaptive dynamic sampling; optimizer tự quyết định khi cần | Tự xác định |

Level 11 không đơn giản là “lấy mẫu lớn nhất”. Nó cho phép optimizer tự điều chỉnh dynamic statistics và xác định ngân sách sampling nội bộ khi cần xác minh cardinality. Các điều kiện cụ thể vẫn phụ thuộc release và optimizer environment.

### 3.2 Level 0: tắt dynamic statistics

~~~sql
ALTER SESSION SET OPTIMIZER_DYNAMIC_SAMPLING = 0;
~~~

Mức này có thể hữu ích khi muốn loại bỏ chi phí sampling trong một phép đo hoặc khi đã có statistics đáng tin cậy và cần parse latency thấp. Không nên tắt toàn cục chỉ vì một truy vấn có parse time cao; hãy xác định statement và tác động trước.

### 3.3 Level 2: mặc định thông dụng

Ở level 2, optimizer dùng dynamic statistics khi ít nhất một bảng trong statement không có statistics và các điều kiện của level được đáp ứng. Level 2 không có nghĩa optimizer sẽ lấy mẫu cho mọi bảng không có statistics trong mọi loại câu lệnh.

### 3.4 Level 4: xử lý predicate phức tạp

Level 4 mở rộng điều kiện sử dụng sampling sang các expression và predicate kết hợp AND/OR phức tạp trên cùng bảng. Ví dụ:

~~~sql
SELECT *
FROM customers c
WHERE SUBSTR(c.last_name, 1, 3) = 'SMI'
  AND (c.city = 'Los Angeles' OR c.city = 'San Diego');
~~~

Optimizer có thể khó ước lượng biểu thức và quan hệ giữa các điều kiện nếu chưa có expression/column-group statistics phù hợp.

### 3.5 Level 11: adaptive dynamic statistics

Level 11 cho phép optimizer tự quyết định khi nào và với mức sampling nào cần thiết. Trong các phiên bản hỗ trợ, adaptive dynamic sampling cũng có thể sử dụng thông tin liên quan đến SQL plan directives và parallel execution.

Không nên tự động nâng mọi session lên level 11 mà không đo lường. Sampling có chi phí parse; với workload có nhiều câu SQL ngắn, phần chi phí bổ sung có thể lớn hơn lợi ích.

## 4. Cấu hình dynamic statistics

### 4.1 Xem giá trị hiện tại

Trong SQL*Plus hoặc SQLcl:

~~~sql
SHOW PARAMETER optimizer_dynamic_sampling;
SHOW PARAMETER optimizer_features_enable;
~~~

Hoặc truy vấn:

~~~sql
SELECT name, value, isdefault, isses_modifiable, issys_modifiable
FROM v$parameter
WHERE name IN (
    'optimizer_dynamic_sampling',
    'optimizer_features_enable'
);
~~~

### 4.2 Đặt ở session

Nếu muốn thử một mức cho session thử nghiệm:

~~~sql
ALTER SESSION SET optimizer_dynamic_sampling = 4;
~~~

Session-level change giúp so sánh cùng một workload với level khác nhau mà không thay đổi cấu hình của toàn instance.

### 4.3 Đặt bằng SQL hint

Có thể chỉ định level cho một statement:

~~~sql
SELECT /*+ DYNAMIC_SAMPLING(4) */
       c.customer_id,
       c.city,
       c.state_province
FROM customers c
WHERE c.city = 'Los Angeles'
  AND c.state_province = 'CA';
~~~

Hoặc chỉ định alias bảng:

~~~sql
SELECT /*+ DYNAMIC_SAMPLING(c 4) */
       c.customer_id
FROM customers c
WHERE c.city = 'Los Angeles'
  AND c.state_province = 'CA';
~~~

Hint là cách thử nghiệm có phạm vi hẹp. Kiểm tra hint report và plan note để biết hint có được optimizer chấp nhận hay bị bỏ qua do alias, cú pháp hoặc điều kiện không phù hợp.

### 4.4 Xác nhận trong execution plan

Ví dụ dùng EXPLAIN PLAN:

~~~sql
EXPLAIN PLAN FOR
SELECT /*+ DYNAMIC_SAMPLING(c 4) */
       c.customer_id
FROM customers c
WHERE c.city = 'Los Angeles'
  AND c.state_province = 'CA';

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
~~~

Khi dynamic statistics được dùng, phần Note của plan có thể hiển thị nội dung như:

~~~text
Note
-----
 - dynamic statistics used: dynamic sampling (level=4)
~~~

Note thực tế thay đổi theo version, statement và các optimizer features đang hoạt động.

### 4.5 Không để level cao thành giải pháp mặc định cho mọi SQL

Level cao có thể cải thiện estimate nhưng cũng làm tăng chi phí parse và có thể dẫn tới sampling lặp lại trong workload có hard parse cao. Nên:

1. Thu thập plan và runtime statistics.
2. Tìm predicate/operation có estimate sai.
3. Kiểm tra statistics, histogram, column group và expression statistics.
4. Thử hint hoặc session level trong môi trường kiểm soát.
5. So sánh parse time, execution time, buffers và throughput.
6. Chỉ áp dụng phạm vi rộng nếu có bằng chứng cho toàn workload.

## 5. Cardinality feedback và statistics feedback

**Cardinality feedback** là tên được dùng cho cơ chế feedback từ Oracle Database 11g. Trong tài liệu Oracle Database 12c và các release mới, tên thường dùng là **statistics feedback**.

Ý tưởng cốt lõi: optimizer tạo plan ban đầu dựa trên thống kê và các ước lượng. Sau lần thực thi đầu tiên, database có thể so sánh số dòng dự kiến với số dòng thực tế ở từng row source. Nếu sai lệch đủ lớn và statement đủ điều kiện, optimizer lưu thông tin feedback để reoptimize khi statement được chạy lại.

### 5.1 Vòng đời statistics feedback

~~~text
Lần chạy đầu tiên
       |
       v
Optimizer tạo plan với E-Rows
       |
       v
Statement thực thi và sinh A-Rows
       |
       v
So sánh estimate với actual rows
       |
       v
Sai lệch đáng kể và đủ điều kiện?
       |
   +---+---+
   |       |
  Không    Có
   |       |
   v       v
Không     Lưu statistics feedback
feedback          |
                  v
          Cursor được đánh dấu
          có thể reoptimization
                  |
                  v
          Lần chạy tiếp theo hard parse/
          reoptimize với thông tin mới
                  |
                  v
          Có thể chọn plan khác
~~~

Feedback không có nghĩa Oracle sửa trực tiếp NUM_ROWS hoặc histogram trong data dictionary của bảng. Nó là thông tin bổ sung cho quá trình tối ưu lại statement. Muốn cập nhật thống kê đối tượng, vẫn dùng DBMS_STATS.

### 5.2 Điều kiện thường khiến optimizer theo dõi feedback

Optimizer có thể theo dõi statistics feedback cho shared SQL area trong các trường hợp như:

- Bảng chưa có statistics.
- Một bảng có nhiều conjunctive hoặc disjunctive filter predicates.
- Predicate chứa operator phức tạp khiến optimizer khó tính selectivity.
- Estimate ban đầu khác đáng kể so với actual cardinality.

Không phải mọi SQL đều được feedback. Một statement chỉ chạy một lần có thể không có cơ hội dùng feedback ở lần chạy sau. Cursor cũng có thể bị aging, invalidation hoặc không còn phù hợp với lần chạy tiếp theo.

### 5.3 E-Rows và A-Rows

Để xem số dòng dự kiến và thực tế, chạy statement với runtime plan statistics:

~~~sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       o.order_id,
       oi.product_id
FROM orders o
JOIN order_items oi
  ON oi.order_id = o.order_id
WHERE o.order_date >= DATE '2025-01-01'
  AND o.status = 'SHIPPED';
~~~

Sau khi fetch hết kết quả, xem plan của cursor:

~~~sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL,
        NULL,
        'ALLSTATS LAST +NOTE +PREDICATE'
    )
);
~~~

Các cột cần chú ý:

| Cột | Ý nghĩa |
|---|---|
| E-Rows | Số dòng optimizer ước lượng |
| A-Rows | Số dòng thực tế do operation trả về |
| Starts | Số lần operation được bắt đầu |
| A-Time | Thời gian thực thi được ghi nhận |
| Buffers | Logical reads |
| Reads | Physical reads được ghi nhận |

Nếu A-Rows và E-Rows lệch nhiều ở một operation, hãy tìm nguyên nhân tại predicate hoặc operation đó. Sai lệch ở một row source đầu vào có thể lan truyền thành sai lệch lớn ở các join phía trên.

### 5.4 Nhìn thấy statistics feedback trong plan

Sau lần chạy tiếp theo, plan có thể có Note:

~~~text
Note
-----
 - statistics feedback used for this statement
~~~

Khi feedback được sử dụng, E-Rows có thể gần với A-Rows hơn và optimizer có thể chọn plan khác. Không nên chỉ nhìn plan hash để kết luận; hãy so sánh operation, E-Rows/A-Rows, buffers và elapsed time.

### 5.5 Kiểm tra cursor có thể reoptimize

Oracle cung cấp cột IS_REOPTIMIZABLE trong V$SQL:

~~~sql
SELECT sql_id,
       child_number,
       executions,
       is_reoptimizable,
       plan_hash_value,
       sql_text
FROM v$sql
WHERE sql_text LIKE 'SELECT /*+ GATHER_PLAN_STATISTICS */%';
~~~

Giá trị thường gặp:

- Y: lần thực thi tiếp theo khớp child cursor này có thể kích hoạt reoptimization.
- R: cursor có thông tin reoptimization nhưng đang ở reporting-only mode, không kích hoạt thay đổi plan.
- N: cursor không có thông tin reoptimization.

Đây là trạng thái của child cursor, không phải lời hứa rằng lần chạy kế tiếp chắc chắn sẽ có plan tốt hơn.

### 5.6 Kiểm tra hard parse do feedback

V$SQL_SHARED_CURSOR có cột USE_FEEDBACK_STATS. Giá trị Y cho biết hard parse bị buộc để optimizer có thể reoptimize query với input tốt hơn, ví dụ cardinality estimates:

~~~sql
SELECT sql_id,
       child_number,
       use_feedback_stats,
       reason
FROM v$sql_shared_cursor
WHERE sql_id = :p_sql_id;
~~~

V$SQL_SHARED_CURSOR giúp giải thích vì sao child cursor không được share với cursor hiện có. Cần xem REASON và các cột mismatch khác cùng lúc, vì không phải mọi child cursor mới đều do statistics feedback.

## 6. SQL plan directives

SQL plan directive (SPD) là thông tin bổ sung do optimizer tự tạo khi phát hiện một số dạng cardinality misestimate. Có thể hiểu directive như một ghi chú cho optimizer: “Với dạng predicate/biểu thức này, ước lượng trước đây không tốt; lần sau cần lấy thêm thông tin hoặc thu thập extended statistics phù hợp”.

Directive không gắn duy nhất với một SQL_ID. Oracle có thể ghi directive trên query expression hoặc pattern predicate để các statement khác có cấu trúc tương tự cũng được hưởng lợi.

### 6.1 Directive được tạo khi nào?

Oracle tự động tạo SQL plan directives dựa trên thông tin thu thập từ automatic reoptimization. Ví dụ:

- Optimizer ước lượng cardinality của một predicate kết hợp hai cột sai đáng kể.
- Hai bảng join trên cột có data skew.
- Optimizer phát hiện thiếu column-group statistics cho các predicate tương quan.

Directive được tạo tự động; người dùng không tạo mới directive bằng một câu lệnh SQL thủ công. Có thể quản lý directive bằng package DBMS_SPD.

### 6.2 Directive được sử dụng như thế nào?

Khi parse statement, optimizer có thể:

1. Kiểm tra có directive phù hợp với table hoặc query expression không.
2. Nếu thiếu thông tin cần thiết, dùng dynamic statistics để lấy mẫu.
3. Nếu phát hiện thiếu column group và AUTO_STAT_EXTENSIONS được bật, DBMS_STATS có thể tạo column-group statistics ở lần gather tiếp theo.
4. Khi extended statistics phù hợp đã tồn tại, optimizer có thể dùng chúng thay cho directive trong trường hợp áp dụng được.

Từ Oracle Database 12c Release 2 (12.2), kết quả của adaptive dynamic sampling có thể được ghi vào SQL plan directives store để dùng lại cho các query khác.

### 6.3 Column group và AUTO_STAT_EXTENSIONS

Ví dụ hai cột có tương quan:

~~~sql
WHERE city = 'Los Angeles'
  AND state_province = 'CA'
~~~

Có thể tạo column-group statistics tường minh:

~~~sql
SELECT DBMS_STATS.CREATE_EXTENDED_STATS(
           ownname   => USER,
           tabname   => 'CUSTOMERS',
           extension => '(CITY, STATE_PROVINCE)'
       ) AS extension_name
FROM dual;

BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname => USER,
        tabname => 'CUSTOMERS',
        cascade => TRUE
    );
END;
/
~~~

Khi workload cần nhiều cột có tương quan, extended statistics thường là giải pháp bền vững hơn việc dựa vào dynamic sampling mỗi lần hard parse.

Oracle có preference AUTO_STAT_EXTENSIONS. Mặc định preference này là OFF trong các tài liệu release phổ biến. Nếu bật ON, SQL plan directive có thể kích hoạt tạo column-group statistics trong lần gather statistics kế tiếp:

~~~sql
BEGIN
    DBMS_STATS.SET_TABLE_PREFS(
        ownname => USER,
        tabname => 'CUSTOMERS',
        pname   => 'AUTO_STAT_EXTENSIONS',
        pvalue  => 'ON'
    );
END;
/
~~~

Không bật ở phạm vi database nếu chưa đánh giá tác động đến workload và quy trình quản lý statistics. Có thể cấu hình preference theo table/schema để giới hạn phạm vi.

### 6.4 Xem SQL plan directives

DBA_SQL_PLAN_DIRECTIVES cung cấp thông tin về directive:

~~~sql
SELECT directive_id,
       type,
       enabled,
       state,
       reason,
       created,
       last_used
FROM dba_sql_plan_directives
ORDER BY created DESC;
~~~

DBA_SQL_PLAN_DIR_OBJECTS hiển thị object và subobject liên quan:

~~~sql
SELECT directive_id,
       owner,
       object_name,
       subobject_name,
       object_type,
       num_rows
FROM dba_sql_plan_dir_objects
ORDER BY directive_id, owner, object_name;
~~~

Các state thường gặp:

- USABLE: directive có thể được optimizer dùng.
- SUPERSEDED: vấn đề đã được xử lý bằng histogram, extension/column group hoặc directive khác phù hợp hơn.

### 6.5 Quản lý directive

DBMS_SPD cung cấp API để bật/tắt, flush, export hoặc drop directive. Ví dụ flush các directive từ memory sang persistent store:

~~~sql
BEGIN
    DBMS_SPD.FLUSH_SQL_PLAN_DIRECTIVE;
END;
/
~~~

Nếu một directive gây sampling overhead không chấp nhận được, DBA có thể điều tra và quản lý directive cụ thể. Không xóa hàng loạt directive để xử lý một vấn đề plan mà chưa hiểu nguyên nhân.

### 6.6 SQL plan directive không phải SQL plan baseline

| Khái niệm | Vai trò |
|---|---|
| SQL plan directive | Nhắc optimizer về dạng cardinality estimate chưa tốt và nhu cầu thêm statistics |
| SQL plan baseline | Quản lý tập plan được chấp nhận cho SQL statement để kiểm soát plan evolution |
| SQL profile | Bổ sung auxiliary statistics để optimizer ước lượng tốt hơn |
| SQL patch | Gắn hint cho statement mà không sửa SQL text |

Directive không khóa plan. Nó có thể làm optimizer lấy thêm thông tin và từ đó chọn plan khác. Baseline lại là cơ chế quản lý plan, có mục tiêu ổn định và kiểm soát plan được dùng.

## 7. Phân biệt statistics feedback với adaptive cursor sharing

Hai cơ chế này thường bị nhầm vì đều có thể dẫn đến child cursor hoặc plan khác.

### 7.1 Statistics feedback

Statistics feedback xử lý sai lệch giữa cardinality optimizer ước lượng và số dòng thực tế của statement đã chạy. Trọng tâm là:

- E-Rows so với A-Rows.
- Estimate sai do statistics thiếu/sai hoặc predicate phức tạp.
- Dùng execution feedback để reoptimize những lần chạy sau.

### 7.2 Adaptive cursor sharing

Adaptive cursor sharing (ACS) xử lý SQL có bind variable mà các giá trị bind khác nhau dẫn tới selectivity rất khác nhau. Một plan duy nhất có thể tốt cho bind value trả vài dòng nhưng rất tệ cho bind value trả hàng trăm nghìn dòng.

Ví dụ:

~~~sql
SELECT employee_id, last_name
FROM employees
WHERE department_id = :dept_id;
~~~

Nếu department 10 chỉ có 2 nhân viên, còn department 50 có 100.000 nhân viên, một plan phù hợp cho department 10 có thể không phù hợp cho department 50.

Optimizer có thể đánh dấu cursor là bind-sensitive, theo dõi behavior của các bind values và sau đó đánh dấu bind-aware. Khi đó, Oracle có thể tạo nhiều child cursors với plan khác nhau cho các selectivity range.

### 7.3 Bảng so sánh

| Tiêu chí | Statistics feedback | Adaptive cursor sharing |
|---|---|---|
| Vấn đề chính | E-Rows khác A-Rows | Bind values có selectivity khác nhau |
| Dữ liệu học | Actual row counts từ execution | Bind value/selectivity và execution behavior |
| Đối tượng thích nghi | Cardinality estimate của statement/row source | Child cursor và plan theo bind selectivity |
| Trigger | Sai lệch cardinality đủ đáng kể và statement đủ điều kiện | Cursor có bind-sensitive behavior và lợi ích từ plan khác |
| Quan sát | Note statistics feedback, IS_REOPTIMIZABLE, USE_FEEDBACK_STATS | IS_BIND_SENSITIVE, IS_BIND_AWARE, V$SQL_CS_* |
| Mục tiêu | Ước lượng chính xác hơn ở lần parse sau | Chọn plan phù hợp với từng nhóm bind value |

### 7.4 Xem bind-sensitive và bind-aware

~~~sql
SELECT sql_id,
       child_number,
       executions,
       is_bind_sensitive,
       is_bind_aware,
       is_shareable,
       plan_hash_value
FROM v$sql
WHERE sql_text LIKE '%FROM employees%'
  AND sql_text LIKE '%department_id = :%';
~~~

Các view bổ sung:

- V$SQL_CS_HISTOGRAM: phân bố số execution theo histogram nội bộ của cursor sharing.
- V$SQL_CS_SELECTIVITY: các selectivity range của predicate có bind.
- V$SQL_CS_STATISTICS: số dòng xử lý, buffer gets và CPU time được dùng để quyết định cursor có nên bind-aware hay không.

### 7.5 Histogram vẫn quan trọng

ACS thường cần optimizer nhận biết bind có thể làm cardinality khác nhau. Histogram giúp mô tả skew của dữ liệu và cải thiện selectivity estimate khi bind peeking. Không nên coi ACS là lý do để bỏ histogram hoặc bỏ gather statistics.

## 8. Các cơ chế này bổ sung nhau như thế nào?

Giả sử một truy vấn join nhiều bảng có predicate trên hai cột tương quan và có bind variable:

~~~sql
SELECT o.order_id, c.customer_name
FROM orders o
JOIN customers c
  ON c.customer_id = o.customer_id
WHERE o.status = :status
  AND o.region = :region;
~~~

Một chuỗi sự kiện có thể diễn ra:

1. Optimizer dùng table/column statistics và histogram để ước lượng cardinality.
2. Nếu statistics không đủ, dynamic statistics có thể lấy mẫu ở parse.
3. Sau execution, statistics feedback có thể nhận ra E-Rows lệch lớn so với A-Rows.
4. Nếu query expression gây sai lệch lặp lại, SQL plan directive có thể ghi nhận pattern.
5. Nếu giá trị bind có selectivity rất khác nhau, adaptive cursor sharing có thể tạo child cursor với plan khác.
6. Nếu workload cần ổn định plan sau khi tune, SQL plan management có thể quản lý baseline riêng.

## 9. Khác biệt theo phiên bản Oracle Database

Các thuật ngữ và tham số đã thay đổi qua nhiều release. Khi đọc tài liệu cũ hoặc nâng cấp database, cần phân biệt tên tính năng, tên tham số và default value.

### 9.1 Oracle Database 11g

- Cardinality feedback được giới thiệu để optimizer có thể học từ sai lệch giữa estimate và actual rows.
- Dynamic sampling là tên dùng cho cơ chế lấy mẫu block trong giai đoạn optimization.
- OPTIMIZER_DYNAMIC_SAMPLING điều khiển sampling level; default phổ biến là 2 khi optimizer features tương ứng từ 10g trở lên.
- Adaptive cursor sharing và bind-sensitive/bind-aware cursor cũng là các cơ chế cần xét khi SQL dùng bind variable trên dữ liệu skew.

Ở release này, thuật ngữ cardinality feedback thường xuất hiện trong tài liệu và bài viết kỹ thuật.

### 9.2 Oracle Database 12c Release 1 (12.1)

- Dynamic sampling được đổi tên thành dynamic statistics.
- Optimizer adaptive optimization xuất hiện, gồm adaptive plans và adaptive statistics.
- Tên statistics feedback được dùng trong tài liệu mới thay cho cardinality feedback.
- SQL plan directives được dùng để lưu thông tin về query expression có cardinality misestimate và có thể hướng optimizer dùng dynamic statistics hoặc hỗ trợ extended statistics.
- Các tính năng adaptive ở 12.1 được gom dưới OPTIMIZER_ADAPTIVE_FEATURES; đây là điểm cần lưu ý khi đọc cấu hình 12.1 so với 12.2 trở đi.

Không nên lấy default của 12.2 áp thẳng cho 12.1. Hãy kiểm tra đúng patch level và giá trị tham số của database.

### 9.3 Oracle Database 12c Release 2 (12.2)

Đây là mốc thay đổi cấu hình quan trọng:

- OPTIMIZER_ADAPTIVE_FEATURES bị loại bỏ/desupported.
- OPTIMIZER_ADAPTIVE_PLANS được tách riêng, default TRUE.
- OPTIMIZER_ADAPTIVE_STATISTICS được tách riêng, default FALSE.
- OPTIMIZER_ADAPTIVE_STATISTICS = TRUE bật các adaptive statistics features như SQL plan directives, statistics feedback cho join cardinality, performance feedback và adaptive dynamic sampling.
- Đặt OPTIMIZER_ADAPTIVE_STATISTICS = FALSE vẫn giữ statistics feedback cho single-table cardinality misestimates đã có từ 11g.

Như vậy, “adaptive plans” và “adaptive statistics” là hai nhóm cấu hình khác nhau từ 12.2. Không tắt adaptive plans chỉ vì muốn tắt adaptive statistics.

### 9.4 Oracle Database 18c và 19c

Các nguyên tắc cấu hình của 12.2 tiếp tục được áp dụng:

| Tham số | Default thường gặp | Vai trò |
|---|---|---|
| OPTIMIZER_ADAPTIVE_PLANS | TRUE | Adaptive plan, ví dụ chọn nested loops/hash join hoặc parallel distribution phù hợp trong execution |
| OPTIMIZER_ADAPTIVE_STATISTICS | FALSE | Adaptive statistics: join statistics feedback, SQL plan directive usage và adaptive dynamic sampling |
| OPTIMIZER_DYNAMIC_SAMPLING | 2 | Điều kiện và sample size của dynamic statistics |
| OPTIMIZER_ADAPTIVE_REPORTING_ONLY | FALSE | Khi TRUE, thu thập thông tin adaptive nhưng không thay đổi plan; có thể xem báo cáo bằng DBMS_XPLAN |

Lưu ý: OPTIMIZER_ADAPTIVE_STATISTICS = FALSE không có nghĩa mọi loại statistics feedback đều bị tắt. Single-table statistics feedback vẫn được giữ. Tài liệu Reference cũng làm rõ SQL plan directives vẫn có thể được tạo, nhưng khi adaptive statistics bị tắt, chúng không được dùng để tinh chỉnh plan bằng dynamic sampling.

### 9.5 Oracle Database 21c

21c tiếp tục dùng tên statistics feedback và dynamic statistics. OPTIMIZER_ADAPTIVE_STATISTICS vẫn có default FALSE; OPTIMIZER_ADAPTIVE_PLANS vẫn là cấu hình riêng. Dynamic statistics level mặc định vẫn thường là 2, trừ khi OPTIMIZER_FEATURES_ENABLE hoặc cấu hình session/system được thay đổi.

SQL plan directives, DBA_SQL_PLAN_DIRECTIVES và DBMS_SPD vẫn được mô tả trong tài liệu 21c. Cần xem trạng thái directive, mức sử dụng và chi phí hard parse thay vì mặc định rằng directive nào cũng cải thiện hiệu năng.

### 9.6 Oracle Database 23ai và Oracle AI Database 26ai

Trong các tài liệu 23ai/26ai:

- Statistics feedback tiếp tục được gọi là tên hiện đại của cardinality feedback.
- Dynamic statistics vẫn là thuật ngữ hiện hành; dynamic sampling là tên lịch sử trước 12.1.
- OPTIMIZER_ADAPTIVE_STATISTICS có default FALSE.
- OPTIMIZER_ADAPTIVE_PLANS vẫn là tham số riêng và default TRUE trong tài liệu hiện hành.
- OPTIMIZER_DYNAMIC_SAMPLING vẫn điều khiển level 0 đến 11; level 11 cho phép adaptive dynamic sampling.
- Các view V$SQL, V$SQL_SHARED_CURSOR, DBA_SQL_PLAN_DIRECTIVES và DBMS_XPLAN tiếp tục là công cụ quan sát quan trọng.

26ai có thể bổ sung optimizer features và thay đổi cách chọn plan so với 19c/21c. Không nên giả định một câu SQL luôn có cùng plan sau upgrade chỉ vì tham số adaptive statistics có cùng default.

### 9.7 Bảng mốc thay đổi

| Release | Tên/điểm nổi bật | Lưu ý cấu hình |
|---|---|---|
| 11g | Cardinality feedback; dynamic sampling | Feedback bắt đầu học từ execution; dynamic sampling dùng tên cũ |
| 12.1 | Dynamic statistics; statistics feedback; adaptive query optimization; SQL plan directives | Adaptive features được gom trong OPTIMIZER_ADAPTIVE_FEATURES |
| 12.2 | Tách adaptive plans và adaptive statistics | OPTIMIZER_ADAPTIVE_FEATURES bị bỏ; ADAPTIVE_PLANS TRUE, ADAPTIVE_STATISTICS FALSE mặc định |
| 18c/19c | Tiếp tục statistics feedback, SQL plan directives, dynamic statistics | ADAPTIVE_STATISTICS FALSE mặc định; single-table feedback vẫn còn |
| 21c | Cùng mô hình 12.2+ | Kiểm tra các view và note trong plan |
| 23ai | Optimizer feature set mới, tiếp tục các cơ chế hiện hành | Kiểm tra OFE và patch level |
| 26ai | Tài liệu mang tên Oracle AI Database; tiếp tục statistics feedback và dynamic statistics | Không giả định plan/default optimizer feature tương đương release cũ |

### 9.8 OPTIMIZER_FEATURES_ENABLE ảnh hưởng thế nào?

OPTIMIZER_FEATURES_ENABLE là tham số umbrella để bật nhóm optimizer features tương ứng một release. Khi upgrade, nếu database giữ giá trị OFE cũ, hành vi optimizer có thể không giống database mới cài với default OFE của release mới.

Xem giá trị:

~~~sql
SELECT name, value
FROM v$parameter
WHERE name IN (
    'optimizer_features_enable',
    'optimizer_adaptive_plans',
    'optimizer_adaptive_statistics',
    'optimizer_adaptive_reporting_only',
    'optimizer_dynamic_sampling'
)
ORDER BY name;
~~~

Không dùng ALTER SYSTEM SET OPTIMIZER_FEATURES_ENABLE để chữa một query chậm đơn lẻ. OFE có phạm vi ảnh hưởng rộng đến optimizer và có thể thay đổi nhiều execution plans. Khi cần kiểm thử hành vi cũ/mới, hãy đặt ở session thử nghiệm, ghi lại plan và so sánh workload đại diện.

## 10. Bài lab: quan sát cardinality misestimate và dynamic statistics

Lab sau tạo một bảng có hai cột tương quan mạnh. Mục tiêu là minh họa vì sao thống kê từng cột riêng lẻ có thể không mô tả được quan hệ giữa hai cột.

### 10.1 Tạo bảng dữ liệu thử nghiệm

~~~sql
CREATE TABLE cardinality_lab AS
SELECT level AS id,
       CASE
           WHEN MOD(level, 100) = 0 THEN 'Los Angeles'
           ELSE 'New York'
       END AS city,
       CASE
           WHEN MOD(level, 100) = 0 THEN 'CA'
           ELSE 'NY'
       END AS state_province
FROM dual
CONNECT BY level <= 100000;
~~~

Trong dữ liệu này:

- Khoảng 1% dòng có CITY = Los Angeles và STATE_PROVINCE = CA.
- Khoảng 99% dòng có CITY = New York và STATE_PROVINCE = NY.
- Hai cột có tương quan gần như hoàn toàn.

### 10.2 Gather statistics cơ bản, không tạo histogram

~~~sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname    => USER,
        tabname    => 'CARDINALITY_LAB',
        method_opt => 'FOR ALL COLUMNS SIZE 1',
        cascade    => TRUE
    );
END;
/
~~~

SIZE 1 yêu cầu histogram không được tạo cho các cột trong ví dụ. Mục đích là để quan sát ước lượng dựa trên thống kê đơn cột, không phải cấu hình nên dùng cho mọi bảng production.

### 10.3 Đếm actual rows

~~~sql
SELECT COUNT(*) AS actual_rows
FROM cardinality_lab
WHERE city = 'Los Angeles'
  AND state_province = 'CA';
~~~

Kết quả dự kiến khoảng 1.000 dòng.

### 10.4 Xem plan với statistics hiện có

~~~sql
EXPLAIN PLAN FOR
SELECT COUNT(*)
FROM cardinality_lab c
WHERE c.city = 'Los Angeles'
  AND c.state_province = 'CA';

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
~~~

Optimizer có thể giả định hai predicate độc lập và nhân selectivity của từng cột. Khi đó E-Rows có thể lệch đáng kể so với actual rows.

### 10.5 Thử dynamic statistics bằng hint

~~~sql
SELECT /*+ GATHER_PLAN_STATISTICS DYNAMIC_SAMPLING(c 4) */
       COUNT(*)
FROM cardinality_lab c
WHERE c.city = 'Los Angeles'
  AND c.state_province = 'CA';
~~~

Sau khi thực thi, xem cursor:

~~~sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL,
        NULL,
        'ALLSTATS LAST +NOTE +PREDICATE'
    )
);
~~~

Quan sát E-Rows, A-Rows và Note về dynamic statistics. Kết quả lấy mẫu có thể không bằng tuyệt đối số dòng thật; mục tiêu là cải thiện estimate và lựa chọn plan.

### 10.6 Thử extended column-group statistics

Tạo column group:

~~~sql
SELECT DBMS_STATS.CREATE_EXTENDED_STATS(
           ownname   => USER,
           tabname   => 'CARDINALITY_LAB',
           extension => '(CITY, STATE_PROVINCE)'
       ) AS extension_name
FROM dual;
~~~

Gather lại statistics:

~~~sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname    => USER,
        tabname    => 'CARDINALITY_LAB',
        method_opt => 'FOR ALL COLUMNS SIZE 1',
        cascade    => TRUE
    );
END;
/
~~~

Chạy lại query và xem E-Rows. Column-group statistics cung cấp thông tin bền vững hơn về mối tương quan giữa hai cột, có thể giúp optimizer estimate tốt mà không phải dựa vào sampling cho mỗi lần parse.

### 10.7 Dọn dữ liệu lab

~~~sql
DROP TABLE cardinality_lab PURGE;
~~~

Chỉ chạy câu lệnh dọn dẹp nếu đây là bảng lab vừa tạo và không chứa dữ liệu cần giữ.

## 11. Adaptive plans không giống statistics feedback

Adaptive query plans và statistics feedback đều dùng thông tin runtime, nhưng chúng thích nghi ở thời điểm khác nhau.

### 11.1 Adaptive plan

Adaptive plan có các lựa chọn thay thế được xây dựng sẵn trong plan. Trong lần execution hiện tại, Oracle thu thập thông tin runtime (ví dụ số dòng qua một row source) rồi chọn nhánh phù hợp giữa các lựa chọn đã có.

Ví dụ adaptive plan có thể chuẩn bị cả nested loops và hash join. Khi execution chạy, optimizer runtime statistics có thể khiến một nhánh được chọn và nhánh còn lại trở thành inactive.

### 11.2 Statistics feedback / automatic reoptimization

Statistics feedback sử dụng thông tin thu thập từ execution để cải thiện estimate khi statement được tối ưu lại ở lần chạy sau. Nó có thể dẫn đến plan mới được tạo ở lần parse/reoptimization tiếp theo.

### 11.3 So sánh thời điểm thích nghi

| Cơ chế | Khi nào thích nghi? | Điều thay đổi |
|---|---|---|
| Adaptive plan | Trong execution hiện tại | Chọn một nhánh trong plan có sẵn |
| Statistics feedback | Ở lần tối ưu lại sau execution | Estimate/cardinality input và có thể là execution plan |
| Dynamic statistics | Trước khi plan được chọn, trong parse | Bổ sung estimate bằng sampling |
| Adaptive cursor sharing | Qua các execution với bind values khác nhau | Child cursor/plan theo selectivity range |

Không nên dùng từ “adaptive” như thể mọi cơ chế đều có cùng cách hoạt động. Cần xác định đang nói adaptive plan, adaptive statistics hay adaptive cursor sharing.

## 12. Quy trình chẩn đoán cardinality misestimate trong hệ thống thật

Khi một SQL chậm, nên bắt đầu từ plan thực thi thực tế và dữ liệu thống kê của object.

### 12.1 Bước 1: xác định SQL_ID và child cursor

~~~sql
SELECT sql_id,
       child_number,
       plan_hash_value,
       executions,
       is_reoptimizable,
       is_bind_sensitive,
       is_bind_aware,
       sql_text
FROM v$sql
WHERE sql_text LIKE '%unique_fragment_of_query%';
~~~

Nếu SQL có nhiều child cursor, không chỉ xem child 0. Các child có thể khác plan, bind peeking, optimizer environment hoặc lý do không share.

### 12.2 Bước 2: xem plan cùng runtime statistics

~~~sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        :p_sql_id,
        :p_child_number,
        'ALLSTATS LAST +NOTE +PREDICATE +PEEKED_BINDS'
    )
);
~~~

Tập trung vào:

- E-Rows và A-Rows ở từng operation.
- Starts: operation có được chạy nhiều lần không.
- Buffers, Reads, A-Time.
- Predicate Information để xác định điều kiện filter/access.
- Note về dynamic statistics hoặc statistics feedback.
- Peeked binds nếu plan được tạo dựa trên bind peeking.

Không dùng EXPLAIN PLAN thay cho runtime plan khi cần biết A-Rows. EXPLAIN PLAN chỉ cho biết plan được giải thích trong môi trường hiện tại, không phải chắc chắn plan/child cursor đã chạy trong session.

### 12.3 Bước 3: tìm operation sai lệch đầu tiên

Một plan có thể có nhiều operation mà E-Rows khác A-Rows. Hãy tìm operation thấp nhất trong cây mà sai lệch xuất hiện lần đầu. Nếu row source đầu vào đã sai, các operation phía trên có thể chỉ phản ánh sai lệch lan truyền.

Ví dụ:

~~~text
TABLE ACCESS FULL CUSTOMERS
  E-Rows = 10
  A-Rows = 500000

HASH JOIN ORDERS/CUSTOMERS
  E-Rows = 100
  A-Rows = 480000
~~~

Trong ví dụ, sai lệch bắt đầu từ TABLE ACCESS FULL CUSTOMERS. Tập trung vào predicate, histogram, column group và dữ liệu của CUSTOMERS trước khi sửa join ở phía trên.

### 12.4 Bước 4: kiểm tra table statistics

~~~sql
SELECT table_name,
       num_rows,
       blocks,
       avg_row_len,
       stale_stats,
       last_analyzed
FROM user_tab_statistics
WHERE table_name IN ('CUSTOMERS', 'ORDERS');
~~~

Kiểm tra:

- Statistics có tồn tại không?
- LAST_ANALYZED có quá cũ so với thay đổi dữ liệu không?
- STALE_STATS có bằng YES không?
- NUM_ROWS/BLOCKS có hợp lý với kích thước thực tế không?
- Có statistics bị khóa hoặc chưa gather sau bulk load không?

### 12.5 Bước 5: kiểm tra column statistics và histogram

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
WHERE table_name = 'CUSTOMERS'
ORDER BY column_name;
~~~

Nếu dữ liệu skew, histogram có thể cần thiết. Nếu hai cột tương quan, histogram riêng từng cột có thể vẫn chưa đủ; xem column group statistics.

### 12.6 Bước 6: xem predicate usage

DBMS_STATS.REPORT_COL_USAGE có thể cho biết các cột được dùng trong predicate, join, group by hoặc expression trong workload:

~~~sql
SELECT DBMS_STATS.REPORT_COL_USAGE(
           ownname => USER,
           tabname => 'CUSTOMERS'
       )
FROM dual;
~~~

Thông tin này hữu ích khi quyết định có cần column-group statistics hoặc expression statistics. Tạo extended statistics theo workload thực tế thay vì tạo nhóm cho mọi tổ hợp cột.

### 12.7 Bước 7: kiểm tra dynamic statistics và feedback

Xem plan Note để biết dynamic statistics hoặc statistics feedback đã được dùng chưa. Nếu nghi ngờ reoptimization:

~~~sql
SELECT sql_id,
       child_number,
       is_reoptimizable,
       plan_hash_value,
       executions
FROM v$sql
WHERE sql_id = :p_sql_id;
~~~

Xem child cursor mismatch:

~~~sql
SELECT child_number,
       use_feedback_stats,
       bind_mismatch,
       optimizer_mismatch,
       stats_row_mismatch,
       reason
FROM v$sql_shared_cursor
WHERE sql_id = :p_sql_id;
~~~

Tên/các cột mismatch có thể khác theo release. Chỉ chọn cột có trong data dictionary của phiên bản đang chạy.

### 12.8 Bước 8: kiểm tra SQL plan directive nếu có quyền

~~~sql
SELECT directive_id,
       type,
       enabled,
       state,
       reason,
       last_used,
       notes
FROM dba_sql_plan_directives
WHERE state = 'USABLE'
ORDER BY last_used DESC;
~~~

Nếu plan note báo có SQL plan directive, dùng DIRECTIVE_ID và DBA_SQL_PLAN_DIR_OBJECTS để tìm object liên quan. Một directive có thể dùng chung cho nhiều statement cùng query expression.

### 12.9 Bước 9: kiểm thử giải pháp theo từng phạm vi

Ưu tiên giải pháp theo thứ tự:

1. Gather hoặc sửa optimizer statistics cơ bản.
2. Bổ sung histogram nếu dữ liệu skew và workload cần.
3. Bổ sung column-group/expression statistics nếu predicate có tương quan hoặc biểu thức.
4. Dùng dynamic statistics ở session/statement nếu sampling mang lại lợi ích rõ.
5. Đánh giá SQL plan directive và adaptive statistics settings.
6. Dùng SQL plan management nếu cần kiểm soát plan sau khi đã tune.

Sau mỗi thay đổi, chạy lại cùng input/bind values, so sánh E-Rows/A-Rows, buffers, elapsed time và parse time.

## 13. Best practices khi dùng dynamic statistics và feedback

### 13.1 Giữ optimizer statistics cơ bản chính xác

Đây là nền tảng. Dynamic statistics và feedback là cơ chế bổ sung; chúng không nên được dùng để bù cho bảng không được gather statistics trong thời gian dài.

### 13.2 Xử lý skew bằng histogram đúng cách

Nếu một giá trị chiếm phần lớn bảng, histogram có thể giúp optimizer ước lượng equality predicate chính xác hơn. Chọn histogram theo workload và kiểu bind; tránh tạo histogram quá nhiều khiến plan thay đổi khó kiểm soát.

### 13.3 Xử lý tương quan bằng extended statistics

Nếu nhiều cột luôn đi cùng nhau theo quy luật nghiệp vụ, column-group statistics có thể bền vững hơn việc chờ statistics feedback. Dynamic sampling có thể giúp trong lúc parse nhưng không thay thế việc mô tả quan hệ dữ liệu một cách có chủ đích.

### 13.4 Đánh giá parse overhead

Dynamic statistics chạy trong giai đoạn parse. Nếu ứng dụng hard parse nhiều hoặc truy vấn rất ngắn, chi phí sampling có thể trở thành phần đáng kể. Theo dõi parse time và hard parse count cùng với execution time.

### 13.5 Không đặt adaptive statistics TRUE chỉ để chữa một query

OPTIMIZER_ADAPTIVE_STATISTICS ảnh hưởng nhiều cơ chế ở cấp session/instance. Nếu cần thử, bắt đầu bằng session trong môi trường test và đo các workload có liên quan. Tránh thay đổi system-wide chỉ dựa trên một execution plan.

### 13.6 Kiểm soát thay đổi plan khi nâng cấp

Một release mới có thể có optimizer transformations, costing và default khác. Trước upgrade:

- Thu thập SQL workload đại diện.
- Ghi lại SQL_ID, plan hash, E-Rows/A-Rows và runtime metrics.
- Kiểm tra OPTIMIZER_FEATURES_ENABLE.
- Test ở môi trường đích với statistics và bind values gần production.
- Dùng SQL plan baselines hoặc công cụ quản lý plan nếu ứng dụng cần kiểm soát rủi ro.

### 13.7 Đừng ép dynamic sampling level cao cho mọi câu lệnh

Hint DYNAMIC_SAMPLING hữu ích để kiểm chứng giả thuyết trên một statement. Nếu cần hint ở production, ghi rõ lý do, phạm vi, kết quả đo và kế hoạch loại bỏ khi statistics nền được cải thiện.

### 13.8 Không coi feedback là cache kết quả

Statistics feedback không cache result rows và không làm câu SQL trả về dữ liệu cũ. Nó là thông tin để optimizer ước lượng cardinality và có thể chọn plan tốt hơn ở lần parse sau. Kết quả truy vấn vẫn được đọc từ dữ liệu theo transaction semantics thông thường.

### 13.9 Đo cả lần chạy đầu và lần chạy sau

Statistics feedback có thể chỉ có tác dụng sau execution đầu tiên. Nếu chỉ đo một lần, có thể bỏ lỡ lợi ích của lần reoptimization hoặc không phát hiện chi phí hard parse bổ sung. Đo nhiều lần và phân biệt cold cursor với warmed cursor.

## 14. Những hiểu lầm thường gặp

| Hiểu lầm | Thực tế |
|---|---|
| Dynamic statistics là gather table statistics | Dynamic statistics lấy mẫu để bổ sung estimate trong parse; DBMS_STATS mới quản lý statistics đối tượng |
| Dynamic sampling level 11 luôn quét toàn bảng | Level 11 là adaptive; sample size do optimizer tự xác định |
| OPTIMIZER_DYNAMIC_SAMPLING khác dynamic statistics | Đây là tên tham số vẫn dùng cho tính năng dynamic statistics |
| Cardinality feedback sửa NUM_ROWS trong dictionary | Feedback là thông tin phục vụ reoptimization, không tự thay thế DBMS_STATS |
| Statistics feedback chạy cho mọi SQL | Chỉ statement đủ điều kiện mới được theo dõi và sử dụng feedback |
| OPTIMIZER_ADAPTIVE_STATISTICS FALSE tắt mọi feedback | Single-table statistics feedback từ 11g vẫn được giữ |
| Adaptive plans và adaptive statistics là một | Từ 12.2 chúng có tham số riêng và mục đích khác nhau |
| SQL plan directive khóa execution plan | Directive ghi nhớ dạng misestimate và có thể kích hoạt thêm statistics |
| SQL plan directive chỉ áp dụng cho một SQL_ID | Directive được định nghĩa theo query expression và có thể áp dụng cho statement tương tự |
| Adaptive cursor sharing giống statistics feedback | ACS xử lý bind selectivity; statistics feedback xử lý sai lệch estimate/actual |
| E-Rows khác A-Rows luôn là lỗi optimizer | Có thể do starts, parallel execution, bind values, predicate hoặc cách đọc plan; cần phân tích theo operation |
| Dynamic statistics level càng cao luôn càng tốt | Sampling lớn hơn có thể tăng parse cost và không cải thiện mọi workload |
| Sau upgrade plan luôn giống bản cũ | Optimizer features, transformations và costing có thể thay đổi theo release |

## 15. Lỗi thường gặp khi chẩn đoán

| Vấn đề | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Plan vẫn estimate sai sau gather stats | Predicate tương quan, skew, expression hoặc join cardinality | Kiểm tra histogram, column group, dynamic stats và feedback |
| Dynamic statistics không xuất hiện trong plan | Level/điều kiện không phù hợp, statistics đã đủ hoặc hint bị bỏ qua | Kiểm tra parameter, hint report và plan Note |
| Parse time tăng sau khi bật dynamic statistics | Sampling bổ sung trong hard parse | Đo parse overhead, giới hạn hint/level theo workload |
| Lần đầu chậm, lần sau nhanh | Có thể do cache warm-up hoặc statistics feedback | Tách cache effects khỏi reoptimization; xem V$SQL |
| Có nhiều child cursor | Bind selectivity, optimizer environment, feedback hoặc mismatch khác | Xem V$SQL_SHARED_CURSOR và ACS views |
| Statistics feedback không được dùng | Statement không đủ điều kiện, không chạy lại hoặc cursor bị thay thế | Xem IS_REOPTIMIZABLE và USE_FEEDBACK_STATS |
| SQL plan directive tồn tại nhưng không có tác dụng | Directive không enabled/usable hoặc adaptive statistics usage bị tắt | Kiểm tra ENABLED, STATE, parameter và plan note |
| Column group không được tự tạo | AUTO_STAT_EXTENSIONS đang OFF hoặc chưa gather stats | Xem preference và tạo extension tường minh nếu cần |
| Plan mới tốt hơn cho một bind nhưng xấu cho bind khác | Bind selectivity khác nhau | Kiểm tra histogram và adaptive cursor sharing |
| Kết quả test khác production | Data volume/skew, bind, cache hoặc optimizer environment khác | Dùng input và điều kiện đại diện |

## 16. Checklist trước khi thay đổi tham số optimizer

Trước khi thay đổi dynamic statistics hoặc adaptive settings, hãy xác nhận:

1. Đã lấy execution plan thực tế từ cursor cache chưa?
2. Đã xem E-Rows và A-Rows theo từng row source chưa?
3. Đã xác định operation đầu tiên có cardinality misestimate chưa?
4. Table statistics có thiếu, stale hoặc bị khóa không?
5. Histogram có mô tả được data skew không?
6. Các predicate trên nhiều cột có tương quan không?
7. Có expression predicate hoặc function khiến estimate khó không?
8. Có bind values với selectivity khác nhau không?
9. Đã kiểm tra statistics feedback và adaptive cursor sharing chưa?
10. Có SQL plan directive liên quan không?
11. Dynamic statistics có thực sự được dùng trong plan Note không?
12. Đã đo parse time và hard parse overhead chưa?
13. Đã thử session-level hoặc statement-level trước system-level chưa?
14. Đã so sánh cả lần chạy đầu và các lần chạy sau chưa?
15. Đã kiểm thử trên đúng release, patch level và OPTIMIZER_FEATURES_ENABLE chưa?
16. Có cần extended statistics thay vì sampling lặp lại không?
17. Sau khi plan tốt hơn, có làm các bind values hoặc workload khác chậm đi không?
18. Có kế hoạch rollback nếu thay đổi gây regression không?

## 17. Tổng kết

Dynamic statistics, cardinality feedback và SQL plan directives là những cơ chế giúp Oracle cải thiện thông tin cardinality trong quá trình tối ưu:

- **Dynamic statistics** lấy mẫu block trong parse để bổ sung estimate khi optimizer statistics thiếu hoặc chưa đủ. Tên cũ trước 12.1 là dynamic sampling.
- **Cardinality feedback**, tên hiện hành là **statistics feedback**, so sánh estimate với actual rows sau execution và có thể reoptimize statement ở lần chạy sau.
- **SQL plan directives** ghi nhớ query expression có cardinality misestimate, có thể hướng optimizer dùng dynamic statistics hoặc hỗ trợ thu thập column-group statistics.
- **Adaptive cursor sharing** giải quyết trường hợp bind values có selectivity khác nhau và có thể cần child cursor/plan khác nhau.
- **Adaptive plans** chọn nhánh trong plan hiện tại; statistics feedback thường ảnh hưởng đến lần tối ưu lại sau đó.
- Từ Oracle Database 12.2, OPTIMIZER_ADAPTIVE_FEATURES được tách thành OPTIMIZER_ADAPTIVE_PLANS (default TRUE) và OPTIMIZER_ADAPTIVE_STATISTICS (default FALSE). Single-table statistics feedback từ 11g vẫn được giữ khi adaptive statistics tắt.
- Dynamic statistics level mặc định thường là 2; level 11 cho phép adaptive dynamic sampling. Không nên tăng level toàn cục nếu chưa đo parse overhead.
- Khi chẩn đoán, bắt đầu bằng plan thực tế, E-Rows/A-Rows, table/column statistics, bind values, plan note và các view V$SQL/V$SQL_SHARED_CURSOR.

Mục tiêu không phải bật tất cả adaptive features. Mục tiêu là tìm nguyên nhân estimate sai, bổ sung đúng thông tin cho optimizer và xác nhận execution plan cải thiện bằng workload thực tế.

## 18. Tài liệu Oracle tham khảo

- Oracle Database 19c SQL Tuning Guide, “Optimizer Statistics Concepts”: https://docs.oracle.com/en/database/oracle/oracle-database/19/tgsql/optimizer-statistics-concepts.html
- Oracle Database 19c SQL Tuning Guide, “Configuring Options for Dynamic Statistics”: https://docs.oracle.com/en/database/oracle/oracle-database/19/tgsql/options-for-optimizer-statistics-gathering.html
- Oracle Database 19c SQL Tuning Guide, “Query Optimizer Concepts / Statistics Feedback”: https://docs.oracle.com/en/database/oracle/oracle-database/19/tgsql/query-optimizer-concepts.html
- Oracle Database 19c Database Reference, “OPTIMIZER_ADAPTIVE_STATISTICS”: https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/OPTIMIZER_ADAPTIVE_STATISTICS.html
- Oracle Database 19c Database Reference, “OPTIMIZER_DYNAMIC_SAMPLING”: https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/OPTIMIZER_DYNAMIC_SAMPLING.html
- Oracle Database 19c Database Reference, “V$SQL” and “V$SQL_SHARED_CURSOR”: https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-SQL.html and https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-SQL_SHARED_CURSOR.html
- Oracle Database 21c SQL Tuning Guide, “Optimizer Statistics Concepts”: https://docs.oracle.com/en/database/oracle/oracle-database/21/tgsql/optimizer-statistics-concepts.html
- Oracle Database 21c SQL Tuning Guide, “Configuring Options for Dynamic Statistics”: https://docs.oracle.com/en/database/oracle/oracle-database/21/tgsql/options-for-optimizer-statistics-gathering.html
- Oracle AI Database 26ai SQL Tuning Guide, “Query Optimizer Concepts”: https://docs.oracle.com/en/database/oracle/oracle-database/26/tgsql/query-optimizer-concepts.html
- Oracle AI Database 26ai Database Reference, “OPTIMIZER_ADAPTIVE_STATISTICS” and “OPTIMIZER_DYNAMIC_SAMPLING”: https://docs.oracle.com/en/database/oracle/oracle-database/26/refrn/OPTIMIZER_ADAPTIVE_STATISTICS.html and https://docs.oracle.com/en/database/oracle/oracle-database/26/refrn/OPTIMIZER_DYNAMIC_SAMPLING.html

Không phải tất cả các cơ chế đều kích hoạt trong cùng một statement. Chúng có điều kiện, tham số và phạm vi khác nhau.
