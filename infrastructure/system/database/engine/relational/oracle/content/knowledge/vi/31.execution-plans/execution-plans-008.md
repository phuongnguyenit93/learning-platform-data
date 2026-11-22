# So sánh E-Rows/A-Rows, Starts, Buffers và thời gian thực tế

> **Chủ đề:** Database Engine Relational Oracle  
> **Chương:** Kế hoạch thực thi  
> **Mục tiêu:** Đọc execution plan có runtime statistics; phân biệt số hàng ước lượng E-Rows với số hàng thực tế A-Rows; hiểu Starts và cách chuẩn hóa A-Rows theo số lần chạy row source; diễn giải Buffers, Reads và A-Time; phát hiện sai lệch cardinality; thu thập số liệu bằng GATHER_PLAN_STATISTICS, DBMS_XPLAN.DISPLAY_CURSOR và các dynamic performance views; đối chiếu plan với thời gian thực tế, SQL Monitor và workload.

## 1. Vì sao cần so sánh ước lượng với số liệu thực tế?

Oracle Optimizer xây dựng execution plan dựa trên metadata, statistics, cấu trúc SQL, bind values và các tham số tối ưu hóa. Khi chọn plan, optimizer phải ước lượng nhiều đại lượng, đặc biệt là số hàng đi qua từng bước xử lý.

Execution plan thường có các cột quan trọng:

- **E-Rows (Estimated Rows):** số hàng optimizer dự đoán một row source sẽ tạo ra.
- **A-Rows (Actual Rows):** số hàng row source thực tế tạo ra trong lần thực thi được ghi nhận.
- **Starts:** số lần row source được bắt đầu thực thi.
- **Buffers:** số buffer gets, tức logical reads, được ghi nhận cho row source.
- **Reads:** số physical reads được ghi nhận.
- **A-Time:** thời gian thực tế được ghi nhận cho row source.

So sánh các giá trị này giúp trả lời những câu hỏi khác nhau:

- Optimizer dự đoán số hàng có chính xác không?
- Một thao tác được chạy một lần hay hàng nghìn lần?
- Một row source tạo nhiều hàng hơn dự kiến ở mức nào?
- SQL đang tốn logical I/O, physical I/O hay thời gian CPU?
- Một nested loop có lặp inner access quá nhiều lần không?
- Sai lệch cardinality bắt đầu ở bước nào và lan sang join phía trên ra sao?

Không nên đọc từng cột độc lập. E-Rows, A-Rows và Starts cần được xem cùng nhau; Buffers và A-Time phải được đặt trong cấu trúc cây của execution plan và so sánh với số liệu của toàn câu SQL.

## 2. E-Rows: số hàng optimizer ước lượng

E-Rows thể hiện cardinality estimate của một operation trong execution plan. Optimizer dùng estimate này để tính chi phí của access path, join method, join order, sort, aggregation và nhiều thao tác khác.

Ví dụ:

~~~sql
SELECT order_id, customer_id, total_amount
FROM orders
WHERE status = 'OPEN';
~~~

Nếu optimizer ước lượng có 5.000 hàng phù hợp, E-Rows của row source đọc ORDERS có thể là 5.000.

Ước lượng dựa trên nhiều nguồn:

- NUM_ROWS, BLOCKS và AVG_ROW_LEN của table statistics.
- NDV (number of distinct values) và density của column statistics.
- Histogram thể hiện phân bố không đồng đều của giá trị.
- Statistics của index và clustering factor.
- Extended statistics mô tả tương quan giữa các cột.
- Predicate, datatype, bind values và các biểu thức trong SQL.
- Dynamic sampling và các cơ chế optimizer khác.

E-Rows không phải cam kết số hàng sẽ trả về. Đây là dự đoán tại thời điểm tối ưu hóa.

### 2.1. Cardinality sai lệch ảnh hưởng plan như thế nào?

Nếu optimizer nghĩ một predicate trả về 10 hàng nhưng thực tế trả 100.000 hàng, nó có thể chọn nested loops và index access phù hợp với tập nhỏ. Khi chạy thật, inner row source có thể bị gọi quá nhiều lần, tạo nhiều logical reads và elapsed time lớn.

Ngược lại, nếu optimizer dự đoán quá nhiều hàng nhưng thực tế chỉ có vài hàng, nó có thể chọn full scan hoặc hash join khi một index lookup hoặc nested loops rẻ hơn.

Sai lệch ở một row source có thể lan truyền lên các bước cha:

1. Predicate estimate sai số hàng đầu vào.
2. Join estimate dựa trên cardinality đầu vào sai.
3. Optimizer chọn join order hoặc join method không phù hợp.
4. Số Starts, Buffers và A-Time thực tế tăng.
5. Các operation phía trên tiếp tục nhận nhiều hàng hơn dự kiến.

Vì vậy, khi plan chậm, hãy tìm điểm sai lệch đầu tiên từ các row source thấp lên trên, thay vì chỉ nhìn operation cuối cùng.

## 3. A-Rows: số hàng thực tế

A-Rows là số hàng row source thực sự tạo ra trong lần thực thi được thu thập statistics. Đây là số đo runtime, khác với E-Rows là ước lượng trước khi chạy.

Để có A-Rows trong DBMS_XPLAN, phải thu thập row-source execution statistics. Chỉ chạy EXPLAIN PLAN thường không đủ vì EXPLAIN PLAN không thực thi câu SQL.

Ví dụ:

~~~sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       order_id,
       customer_id,
       total_amount
FROM orders
WHERE status = 'OPEN';
~~~

Sau khi thực thi câu SQL, hiển thị plan của cursor:

~~~sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL,
        NULL,
        'ALLSTATS LAST'
    )
);
~~~

Nếu query được chạy hết và runtime statistics được ghi nhận, plan có thể hiển thị E-Rows, A-Rows, Starts, A-Time, Buffers và Reads.

### 3.1. GATHER_PLAN_STATISTICS

Hint GATHER_PLAN_STATISTICS yêu cầu thu thập row-source statistics cho cursor tương ứng:

~~~sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       COUNT(*)
FROM orders
WHERE status = 'OPEN';
~~~

Đây là cách có phạm vi hẹp để kiểm tra một câu SQL. Sau khi chạy, dùng DBMS_XPLAN.DISPLAY_CURSOR với ALLSTATS LAST.

Hint không làm query tự động nhanh hơn. Mục đích là thu thập số liệu để chẩn đoán; việc thu thập statistics runtime có thể có overhead, vì vậy nên dùng có chủ đích.

### 3.2. STATISTICS_LEVEL = ALL

Một cách khác trong session kiểm thử:

~~~sql
ALTER SESSION SET statistics_level = ALL;
~~~

Sau đó chạy câu SQL và xem DBMS_XPLAN.DISPLAY_CURSOR. Khi kết thúc thử nghiệm, có thể trả session về:

~~~sql
ALTER SESSION SET statistics_level = TYPICAL;
~~~

STATISTICS_LEVEL = ALL có thể làm tăng chi phí thu thập runtime statistics cho workload trong session. Ưu tiên GATHER_PLAN_STATISTICS khi chỉ cần kiểm tra một số statement cụ thể.

### 3.3. Cần fetch hết kết quả khi đo

Với SELECT trả về nhiều hàng, nếu client chỉ fetch một phần rồi dừng, số liệu runtime có thể phản ánh phần công việc đã thực hiện đến thời điểm đó, không phải toàn bộ lượng công việc nếu query được fetch hết.

Khi so sánh hai lần chạy, bảo đảm cả hai lần có cùng cách fetch kết quả. Một query trả 1 triệu hàng nhưng client chỉ fetch 10 hàng không thể so trực tiếp với lần fetch hết 1 triệu hàng.

Đối với SELECT INTO, aggregate hoặc DML, cần hiểu chính xác statement hoàn tất đến đâu trước khi đọc statistics.

## 4. Starts: row source được khởi chạy bao nhiêu lần?

Starts cho biết số lần một operation được bắt đầu thực thi trong cursor execution được báo cáo.

Starts thường bằng 1 với một full table scan hoặc một hash build operation. Nhưng một số operation có thể được chạy lặp nhiều lần, đặc biệt ở phía trong của nested loops.

Ví dụ cấu trúc:

~~~text
NESTED LOOPS
  TABLE ACCESS FULL CUSTOMERS
  INDEX RANGE SCAN ORDERS_CUSTOMER_IX
~~~

Oracle có thể:

1. Đọc một customer từ outer row source.
2. Chạy index range scan ORDERS_CUSTOMER_IX để tìm orders của customer đó.
3. Đọc customer tiếp theo.
4. Chạy lại index range scan.
5. Lặp cho mỗi customer.

Nếu outer row source tạo 10.000 hàng, inner index scan có thể có Starts gần 10.000.

### 4.1. Starts lớn không tự động là lỗi

Starts lớn có thể hoàn toàn hợp lý nếu mỗi lần chạy chỉ xử lý một lượng nhỏ dữ liệu và tổng chi phí thấp.

Cần xem cùng lúc:

- E-Rows cho mỗi lần start.
- A-Rows tổng được tạo ra.
- A-Rows chia cho Starts.
- Buffers và A-Time của operation.
- Số hàng outer row source cung cấp.

Một index scan có Starts = 10.000, mỗi start trả một hàng, có thể là hành vi đúng của nested loops. Nhưng nếu mỗi start đọc hàng nghìn block, đó có thể là vấn đề.

### 4.2. Starts và operation không được thực thi

Một số nhánh plan có thể không chạy trong lần thực thi cụ thể do điều kiện, branch pruning hoặc execution path. Starts = 0 cho biết operation không được bắt đầu trong lần đó; không nên diễn giải A-Rows trống/0 của operation này như bằng chứng optimizer ước lượng sai.

Hãy phân biệt operation không chạy với operation đã chạy nhưng không tìm được hàng.

## 5. Vì sao phải chuẩn hóa A-Rows theo Starts?

Đây là điểm quan trọng nhất khi đọc plan có nested loops.

Trong plan output, A-Rows thường là tổng số hàng row source tạo ra qua tất cả các lần start. E-Rows là ước lượng số hàng cho mỗi lần thực thi row source. Vì vậy, với operation có Starts lớn hơn 1, so sánh trực tiếp A-Rows tổng với E-Rows có thể gây kết luận sai.

Công thức kiểm tra gần đúng:

\[
\text{A-Rows per Start} =
\frac{\text{A-Rows}}{\text{Starts}}
\]

Ví dụ:

| Operation | E-Rows | Starts | A-Rows | A-Rows/Starts |
|---|---:|---:|---:|---:|
| INDEX RANGE SCAN | 1 | 10.000 | 10.000 | 1 |
| TABLE ACCESS BY INDEX ROWID | 1 | 10.000 | 9.800 | 0,98 |
| HASH JOIN | 5.000 | 1 | 50.000 | 50.000 |

Ở hai operation đầu, E-Rows = 1 và A-Rows tổng = 10.000 có vẻ chênh lệch 10.000 lần. Nhưng operation được chạy 10.000 lần, trung bình trả một hàng mỗi lần; estimate per start là hợp lý.

Ở HASH JOIN, Starts = 1, E-Rows = 5.000 và A-Rows = 50.000. Đây là underestimate khoảng 10 lần tại operation đó.

### 5.1. Ví dụ nested loops

Giả sử plan có:

| Operation | E-Rows | Starts | A-Rows |
|---|---:|---:|---:|
| TABLE ACCESS FULL CUSTOMERS | 10.000 | 1 | 10.000 |
| INDEX RANGE SCAN ORDERS_CUST_IX | 2 | 10.000 | 20.000 |
| NESTED LOOPS | 20.000 | 1 | 20.000 |

Inner index scan dự đoán 2 hàng mỗi customer, chạy 10.000 lần, tổng cộng tạo 20.000 hàng. Estimate và actual khớp.

Nếu chỉ nhìn 20.000 A-Rows so với 2 E-Rows, có thể nhầm rằng estimate sai 10.000 lần. Starts giải thích chênh lệch đó.

### 5.2. Ví dụ sai lệch thật sự

Giả sử:

| Operation | E-Rows | Starts | A-Rows | A-Rows/Starts |
|---|---:|---:|---:|---:|
| TABLE ACCESS FULL CUSTOMERS | 100 | 1 | 50.000 | 50.000 |
| INDEX RANGE SCAN ORDERS_CUST_IX | 2 | 50.000 | 100.000 | 2 |
| NESTED LOOPS | 200 | 1 | 100.000 | 100.000 |

Estimate ở CUSTOMERS thấp hơn thực tế 500 lần. Inner index scan vẫn trả trung bình hai hàng mỗi lần đúng như estimate, nhưng nó bị gọi 50.000 lần thay vì 100 lần như optimizer dự đoán.

Sai lệch đầu tiên nằm ở outer row source. Đây có thể là nguyên nhân khiến nested loops tốn nhiều công việc hơn dự kiến.

### 5.3. Starts có thể không bằng số hàng cha

Với nested loops đơn giản, Starts của inner row source thường liên quan số hàng outer. Nhưng filter, scalar subquery caching, partition pruning, adaptive plan và các operation khác có thể làm quan hệ không còn một-một.

Không dùng công thức Starts = số hàng outer như một quy tắc tuyệt đối. Hãy đọc plan tree và predicate cụ thể.

## 6. Đo mức sai lệch cardinality

Một cách thực tế là tính tỷ lệ giữa actual rows per start và estimated rows:

\[
\text{Cardinality Ratio} =
\frac{\text{A-Rows}/\text{Starts}}{\text{E-Rows}}
\]

Ví dụ:

- E-Rows = 100.
- Starts = 1.
- A-Rows = 10.000.
- A-Rows per Start = 10.000.
- Ratio = 100 lần underestimate.

Nếu ratio gần 1, estimate khá sát. Nếu ratio lớn hơn nhiều 1, optimizer underestimate. Nếu ratio nhỏ hơn nhiều 1, optimizer overestimate.

Không có một ngưỡng duy nhất áp dụng cho mọi workload. Sai lệch 10 lần ở operation trả vài hàng có thể ít quan trọng; sai lệch 2 lần ở operation lặp hàng triệu lần có thể rất tốn kém.

### 6.1. Ưu tiên sai lệch có tác động lớn

Khi đọc plan:

1. Bắt đầu từ các row source thấp.
2. So sánh E-Rows với A-Rows/Starts.
3. Tìm operation đầu tiên có sai lệch đáng kể.
4. Xem sai lệch đó có làm tăng Starts ở operation phía trên không.
5. Đánh giá Buffers, A-Time và join method bị ảnh hưởng.
6. Ưu tiên sửa nguyên nhân ở đầu chuỗi thay vì chỉ xử lý operation cuối.

### 6.2. Không chỉ nhìn ratio

Ngoài ratio, xem quy mô tuyệt đối. E-Rows = 1 và A-Rows/Starts = 10 là sai lệch 10 lần nhưng chỉ thêm 9 hàng mỗi lần. E-Rows = 100.000 và A-Rows/Starts = 200.000 là sai lệch 2 lần nhưng có thể ảnh hưởng lớn hơn nhiều đến sort, hash join và TEMP.

Kết hợp ratio, số hàng tuyệt đối, Starts và chi phí downstream.

## 7. Buffers: logical reads của row source

Buffers trong DBMS_XPLAN là số buffer gets được ghi nhận cho operation. Buffer get là truy cập block qua buffer cache, thường bao gồm consistent gets và current gets theo ngữ cảnh thống kê.

Buffers là logical I/O:

- Database phải truy cập block để kiểm tra dữ liệu.
- Block có thể đã nằm trong buffer cache.
- Logical read vẫn tiêu tốn CPU và latch/latch-like synchronization work.
- Cùng một block có thể được đọc logic nhiều lần.

Vì vậy, Buffers không phải số block duy nhất, không phải số byte dữ liệu trả cho client và cũng không phải số physical reads.

### 7.1. Buffers cao nói lên điều gì?

Buffers cao có thể đến từ:

- Full table scan trên bảng lớn.
- Index range scan trả nhiều ROWID.
- Nested loops gọi inner operation rất nhiều lần.
- Predicate không chọn lọc.
- Join tạo intermediate rows lớn.
- Truy cập lặp lại cùng block.
- LOB hoặc table access phát sinh nhiều logical I/O.

Buffers cao không tự động có nghĩa plan sai. Full scan có thể là access path tốt nếu query cần phần lớn bảng. Cần so sánh số hàng trả về, selectivity, thời gian và workload.

### 7.2. Buffers và Reads khác nhau

| Chỉ số | Ý nghĩa |
|---|---|
| Buffers | Logical buffer gets |
| Reads | Physical reads được ghi nhận cho operation |
| A-Rows | Số hàng thực tế được tạo ra |
| A-Time | Thời gian row source được ghi nhận |

Một query có 100.000 Buffers nhưng chỉ 100 Reads có thể đã đọc phần lớn block từ cache. Nó vẫn tiêu tốn công việc logical I/O lớn.

Một query có Reads cao có thể đang phải lấy block từ storage; thời gian phụ thuộc storage latency, parallelism và caching.

Không kết luận “Buffers thấp nghĩa là nhanh” nếu query còn chờ lock, network, CPU scheduling hoặc external wait.

### 7.3. Buffers ở operation cha và con

Plan là cây operation. Một số thống kê hiển thị ở operation cha có thể phản ánh công việc của cả cây con hoặc cùng một phần công việc được nhìn từ nhiều mức trong row-source statistics.

Không cộng tất cả Buffers trên mọi dòng plan để tạo “tổng logical reads” nếu chưa hiểu semantics của từng operation. Dùng thống kê cấp cursor trong V$SQL hoặc SQL Monitor để xem tổng thể; dùng Buffers theo operation để định vị nơi phát sinh I/O.

### 7.4. Buffers per Start

Với row source được gọi nhiều lần, có thể xem thêm:

\[
\text{Buffers per Start} =
\frac{\text{Buffers}}{\text{Starts}}
\]

Đây là chỉ số phân tích bổ sung, không thay thế tổng Buffers. Ví dụ inner index scan có 50.000 Starts và 100.000 Buffers, trung bình 2 Buffers mỗi start. Nếu mỗi start chỉ trả một hàng, access path có thể hợp lý; nếu 100 Buffers mỗi start, cần xem index range rộng hoặc table lookup đắt.

## 8. A-Time và thời gian thực tế

A-Time là thời gian thực tế được ghi nhận cho row source trong runtime plan statistics. Đây là số đo hữu ích để tìm operation tốn thời gian, nhưng cần hiểu cách nó được tổng hợp trong plan tree.

Một số điểm cần lưu ý:

- A-Time thường được hiển thị ở độ phân giải giới hạn; operation rất nhanh có thể hiển thị 0 hoặc giá trị làm tròn.
- Thời gian ở operation cha và operation con có thể bao gồm/đóng góp cùng phần công việc trong cây thực thi.
- Không cộng A-Time của mọi dòng để tính tổng thời gian SQL.
- A-Time là số đo row-source execution, không phải lúc nào cũng bằng thời gian người dùng cảm nhận ở client.
- Wait ngoài row source, parse, fetch phía client và network có thể làm thời gian end-to-end khác biệt.

### 8.1. So sánh A-Time với elapsed time

Có nhiều loại thời gian:

| Chỉ số | Phạm vi |
|---|---|
| Row-source A-Time | Thời gian ghi nhận cho operation trong plan |
| SQL elapsed time | Thời gian thực thi SQL ở database theo thống kê cursor/monitor |
| CPU time | Thời gian CPU tiêu thụ |
| Client elapsed time | Thời gian ứng dụng/client đo từ lúc gửi đến lúc nhận xong |
| Wait time | Thời gian chờ I/O, lock, concurrency, network hoặc tài nguyên khác |

Ví dụ SQL có A-Time row source thấp nhưng client chậm có thể do client fetch chậm, network latency hoặc chờ ở tầng ứng dụng. Ngược lại, SQL elapsed cao có thể do physical I/O, lock wait hoặc CPU contention.

### 8.2. Đừng cộng A-Time của mọi operation

Một phép join có thể có child row source chạy trước, sau đó parent join kết hợp kết quả. Thời gian của parent có thể phản ánh thời gian tích lũy trong quá trình thực hiện cây con. Cộng A-Time của parent và child có thể đếm trùng công việc.

Hãy dùng A-Time để xác định tương quan giữa operation và thời gian, sau đó đối chiếu elapsed time của toàn cursor hoặc SQL Monitor.

### 8.3. Thời gian rất nhỏ và làm tròn

Nếu A-Time hiển thị 00:00:00.01 hoặc 00:00:00.00, không nên kết luận operation không tốn thời gian. Với query rất nhanh, overhead đo và độ phân giải hiển thị có thể gần bằng thời gian thực thi.

Chạy nhiều lần, đo workload tổng thể và dùng công cụ runtime phù hợp nếu cần phân tích microsecond.

## 9. Thu thập plan có actual statistics bằng DBMS_XPLAN

Quy trình phổ biến trong session kiểm thử:

### Bước 1: chạy câu SQL có hint

~~~sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       o.customer_id,
       COUNT(*) AS order_count,
       SUM(o.total_amount) AS total_amount
FROM orders o
WHERE o.status = :p_status
GROUP BY o.customer_id;
~~~

Dùng bind variable tương tự ứng dụng. Nếu query trả kết quả nhiều hàng, fetch hết khi muốn đo toàn bộ execution.

### Bước 2: hiển thị cursor vừa chạy

~~~sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL,
        NULL,
        'ALLSTATS LAST +PREDICATE +ALIAS'
    )
);
~~~

ALLSTATS yêu cầu hiển thị runtime row-source statistics. LAST chọn số liệu của lần thực thi gần nhất được ghi nhận cho cursor.

### Bước 3: đọc các cột

Tập trung vào:

- Id và Operation: node trong cây plan.
- Name: table/index/object được truy cập.
- Starts: số lần operation được chạy.
- E-Rows: ước lượng số hàng.
- A-Rows: số hàng thực tế.
- A-Time: thời gian row source.
- Buffers: logical reads.
- Reads: physical reads.
- Predicate Information: điều kiện access/filter.

### Bước 4: tìm sai lệch đầu tiên

Đọc từ các row source lá lên operation cha. Tìm chỗ E-Rows khác nhiều so với A-Rows/Starts. Sau đó xem sai lệch có làm tăng Starts hoặc lượng hàng qua join phía trên không.

### 9.1. Chỉ rõ SQL_ID và child number

Trong session có nhiều query, dùng SQL_ID và child number cụ thể sẽ đáng tin cậy hơn việc chỉ truyền NULL:

~~~sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        sql_id          => 'SQL_ID_HERE',
        cursor_child_no => 0,
        format          => 'ALLSTATS LAST +PREDICATE +ALIAS'
    )
);
~~~

Thay SQL_ID_HERE và child number bằng giá trị thực từ V$SQL. Một SQL_ID có thể có nhiều child cursor do bind metadata, optimizer environment, object changes hoặc các nguyên nhân khác.

### 9.2. ALLSTATS LAST và ALLSTATS

ALLSTATS LAST hiển thị runtime statistics của lần thực thi gần nhất được giữ cho cursor. ALLSTATS yêu cầu hiển thị cả các thống kê row source hiện có theo format mà DBMS_XPLAN hỗ trợ.

Nếu cursor được thực thi đồng thời hoặc nhiều lần, xác định đúng child cursor và execution trước khi kết luận. LAST không phải trung bình của mọi execution.

### 9.3. Khi plan không có A-Rows

Nếu A-Rows, Starts hoặc Buffers không xuất hiện, kiểm tra:

- Statement có GATHER_PLAN_STATISTICS hoặc session STATISTICS_LEVEL = ALL không?
- Cursor có thực sự được thực thi trong session đó không?
- Đã gọi đúng SQL_ID và child cursor chưa?
- Query có fetch đủ kết quả chưa?
- Cursor còn trong shared pool không?
- Quyền truy cập DBMS_XPLAN và dynamic performance views có đủ không?

EXPLAIN PLAN chỉ cho estimated plan; nó không cung cấp A-Rows của một execution thật.

## 10. Ví dụ đọc plan từ đầu đến cuối

Giả sử query tìm đơn hàng theo vùng khách hàng:

~~~sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       o.order_id,
       o.order_date,
       o.total_amount
FROM customers c
JOIN orders o
  ON o.customer_id = c.customer_id
WHERE c.region = 'NORTH'
  AND o.status = 'OPEN';
~~~

Giả sử plan runtime có dạng rút gọn:

~~~text
--------------------------------------------------------------------------------
| Id | Operation                    | Starts | E-Rows | A-Rows | Buffers |
--------------------------------------------------------------------------------
|  0 | SELECT STATEMENT             |      1 |        |  50000 |  82000  |
|  1 |  NESTED LOOPS                |      1 |    500 |  50000 |  82000  |
|  2 |   TABLE ACCESS FULL CUSTOMERS|      1 |    100 |  25000 |   9000  |
|  3 |   INDEX RANGE SCAN ORDERS_IX |  25000 |      5 |  50000 |  73000  |
--------------------------------------------------------------------------------
~~~

Đây chỉ là số liệu minh họa để học cách đọc.

Phân tích:

1. CUSTOMERS được ước lượng 100 hàng nhưng thực tế có 25.000 hàng. Đây là sai lệch lớn ngay tại row source đầu vào.
2. Inner index scan được chạy 25.000 lần vì nested loops nhận nhiều customer.
3. Inner scan ước lượng 5 hàng mỗi start và thực tế trung bình 2 hàng mỗi start (50.000 / 25.000). Ở operation này optimizer đã overestimate khoảng 2,5 lần.
4. Tổng Buffers của inner scan cao vì nó bị gọi nhiều lần.
5. Sai lệch ở CUSTOMERS có thể là nguyên nhân chính khiến nested loops thực hiện nhiều index lookup hơn dự kiến.
6. Cần kiểm tra predicate REGION, statistics/histogram của CUSTOMERS.REGION và khả năng join method khác phù hợp hơn.

Nếu chỉ nhìn E-Rows 5 và A-Rows 50.000 trên index scan, sẽ kết luận sai rằng estimate ở index scan lệch 10.000 lần. Starts cho thấy số liệu cần chuẩn hóa.

## 11. Phân biệt Access Predicate và Filter Predicate

DBMS_XPLAN có thể hiển thị Predicate Information. Đây là phần quan trọng để hiểu vì sao A-Rows khác E-Rows.

- **Access predicate:** điều kiện dùng để tìm vị trí/range truy cập trong index hoặc partition.
- **Filter predicate:** điều kiện lọc các hàng sau khi row source đã đọc chúng.

Ví dụ:

~~~sql
SELECT *
FROM orders
WHERE customer_id = 100
  AND status = 'OPEN';
~~~

Nếu index chỉ có CUSTOMER_ID, Oracle có thể dùng CUSTOMER_ID làm access predicate rồi lọc STATUS sau khi lấy hàng từ table. Nếu customer 100 có rất nhiều orders nhưng chỉ vài hàng OPEN, row source có thể đọc nhiều block trước khi filter.

Một composite index phù hợp có thể giảm số hàng phải truy cập, nhưng quyết định cần dựa trên workload và DML cost.

### 11.1. Sai lệch có thể bắt đầu từ filter

Nếu access predicate trả về nhiều hàng và filter loại bỏ gần hết, E-Rows tại row source có thể phụ thuộc estimate selectivity của filter. Khi histogram hoặc column correlation không mô tả dữ liệu tốt, estimate có thể sai.

Xem predicate information để xác định điều kiện nào được áp dụng tại bước nào, sau đó đối chiếu statistics của các cột liên quan.

## 12. Nguyên nhân thường gặp của E-Rows/A-Rows sai lệch

### 12.1. Statistics cũ hoặc không đại diện

Dữ liệu thay đổi lớn sau lần gather. NUM_ROWS, NDV, histogram hoặc partition statistics không còn phản ánh dữ liệu hiện tại.

Kiểm tra:

~~~sql
SELECT table_name,
       num_rows,
       blocks,
       last_analyzed,
       stale_stats
FROM user_tab_statistics
WHERE table_name IN ('CUSTOMERS', 'ORDERS');
~~~

Không gather statistics mù quáng. Kiểm tra stale stats, data change và workload trước khi chạy DBMS_STATS.

### 12.2. Data skew và histogram

Một giá trị có thể xuất hiện rất nhiều lần trong khi phần lớn giá trị khác hiếm. Uniform distribution assumption sẽ không mô tả đúng.

Ví dụ STATUS có 95% hàng là OPEN và 5% là CLOSED, hoặc một CUSTOMER_ID có số lượng orders vượt xa các customer khác. Histogram có thể giúp optimizer ước lượng tốt hơn cho predicate phù hợp.

~~~sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname    => USER,
        tabname    => 'ORDERS',
        method_opt => 'FOR COLUMNS STATUS SIZE AUTO'
    );
END;
/
~~~

Histogram không phải giải pháp tự động cho mọi sai lệch. Chọn histogram theo data skew, predicate và bind behavior.

### 12.3. Tương quan giữa các cột

Giả sử COUNTRY và REGION có tương quan mạnh. Nếu optimizer giả định hai điều kiện độc lập, nó có thể nhân selectivity riêng và đánh giá thấp số hàng thực tế.

Extended statistics có thể mô tả column group:

~~~sql
SELECT DBMS_STATS.CREATE_EXTENDED_STATS(
           ownname   => USER,
           tabname   => 'CUSTOMERS',
           extension => '(COUNTRY, REGION)'
       )
FROM dual;
~~~

Sau đó gather statistics phù hợp để optimizer sử dụng thông tin mới. Extended statistics không thay thế việc thiết kế index hoặc sửa predicate sai datatype.

### 12.4. Bind variable và bind peeking

Plan có thể được tối ưu dựa trên bind value ở hard parse. Một giá trị rất phổ biến và một giá trị hiếm có thể cần plan khác nhau.

Kiểm tra child cursor, bind sensitivity/adaptive cursor sharing và các lần thực thi với giá trị đại diện. Đừng so sánh một execution với bind hiếm với execution khác có bind phổ biến rồi kết luận statistics sai mà chưa kiểm tra.

### 12.5. Implicit conversion và function trên cột

So sánh NUMBER với VARCHAR2 hoặc áp dụng hàm lên cột có thể làm predicate khó tối ưu hoặc không sử dụng index như mong đợi.

Ví dụ, nếu ORDER_ID là NUMBER, truyền bind NUMBER phù hợp thay vì VARCHAR2 rồi dựa vào implicit conversion. Dùng datatype nhất quán giữa cột, bind và expression.

### 12.6. Partition statistics và pruning

Với partitioned table, global stats và partition stats có thể khác nhau. Predicate không prune partition như dự kiến có thể làm A-Rows/Starts/Reads tăng.

Kiểm tra PARTITION RANGE/ITERATOR operations, Pstart/Pstop và statistics ở global/partition/subpartition level.

## 13. Buffers, elapsed time và waits: đọc cùng nhau

Một query có thể có Buffers thấp nhưng elapsed time cao do chờ lock hoặc storage. Một query Buffers cao nhưng elapsed time thấp có thể chạy nhanh nhờ cache và CPU đủ.

| Quan sát | Hướng điều tra |
|---|---|
| Buffers cao, A-Rows thấp | Đọc nhiều block rồi filter; access path hoặc predicate có thể chưa tốt |
| Buffers cao, Starts cao | Row source bị gọi lặp; kiểm tra nested loops và outer cardinality |
| Reads cao | Physical I/O; xem storage latency, cache và scan volume |
| A-Time cao ở operation | Xem row source, wait, join, sort/hash và parallel execution |
| E-Rows thấp hơn A-Rows nhiều | Underestimate; xem stats, skew, correlation và bind |
| E-Rows cao hơn A-Rows nhiều | Overestimate; xem histogram, predicate, stale stats và datatype |
| Client chậm nhưng SQL elapsed thấp | Fetch, network, application processing hoặc connection pool |
| SQL elapsed cao nhưng CPU thấp | Có thể chờ I/O, lock hoặc tài nguyên khác |

Không chẩn đoán performance bằng một cột duy nhất. Cần nối plan với session wait, SQL statistics và cách ứng dụng tiêu thụ kết quả.

## 14. V$SQL và số liệu ở cấp cursor

V$SQL cung cấp thống kê tích lũy cho child cursor trong shared pool. Ví dụ:

~~~sql
SELECT sql_id,
       child_number,
       plan_hash_value,
       executions,
       end_of_fetch_count,
       elapsed_time,
       cpu_time,
       buffer_gets,
       disk_reads,
       rows_processed,
       last_active_time
FROM v$sql
WHERE sql_id = 'SQL_ID_HERE'
ORDER BY child_number;
~~~

Các cột thời gian trong V$SQL thường được lưu ở microseconds; hãy dùng đúng đơn vị khi quy đổi.

### 14.1. Thống kê V$SQL là tích lũy

V$SQL thường tổng hợp nhiều lần thực thi của child cursor kể từ khi cursor được nạp vào shared pool hoặc reset thống kê liên quan. Vì vậy:

- ELAPSED_TIME không nhất thiết là thời gian của lần chạy gần nhất.
- BUFFER_GETS là tổng của các execution được tính vào cursor.
- EXECUTIONS là số lần thực thi.
- Một cursor có thể được chạy bởi nhiều session.
- Trung bình ELAPSED_TIME / EXECUTIONS chỉ là số trung bình thô và có thể che giấu phân bố latency.

Để đo một execution cụ thể, dùng SQL Monitor, trace theo session hoặc snapshot/delta có kiểm soát thay vì đọc một giá trị tích lũy rồi gán cho lần chạy cuối.

### 14.2. Tính trung bình tham khảo

~~~sql
SELECT sql_id,
       child_number,
       executions,
       ROUND(elapsed_time / 1e6, 3) AS total_elapsed_seconds,
       ROUND(elapsed_time / 1e6 / NULLIF(executions, 0), 4)
           AS avg_elapsed_seconds,
       ROUND(buffer_gets / NULLIF(executions, 0), 1)
           AS avg_buffer_gets
FROM v$sql
WHERE sql_id = 'SQL_ID_HERE'
ORDER BY child_number;
~~~

Đây chỉ là trung bình trên các execution được thống kê. Nó không thay thế percentile latency hoặc per-execution analysis.

### 14.3. V$SQL_PLAN_STATISTICS_ALL

View này kết hợp plan operation với row-source statistics đã thu thập cho cursor. Có thể dùng để điều tra sâu theo SQL_ID/CHILD_NUMBER/PLAN_HASH_VALUE/ID, nếu tài khoản có quyền.

Các trường runtime thường hữu ích gồm:

- LAST_STARTS.
- LAST_OUTPUT_ROWS.
- LAST_CR_BUFFER_GETS.
- LAST_CU_BUFFER_GETS.
- LAST_DISK_READS.
- LAST_ELAPSED_TIME.

Các trường estimate như CARDINALITY và các metadata operation giúp liên hệ số liệu runtime với plan. Tên/cột có thể thay đổi theo release; kiểm tra Reference của đúng phiên bản trước khi viết script giám sát cố định.

## 15. SQL Monitor cho execution dài hoặc parallel

Real-Time SQL Monitoring cho phép quan sát một execution cụ thể, tiến độ, operation, thời gian, I/O, CPU và wait. Đây là công cụ hữu ích khi query chạy lâu hoặc parallel.

Có thể tạo report:

~~~sql
SELECT DBMS_SQLTUNE.REPORT_SQL_MONITOR(
           sql_id       => 'SQL_ID_HERE',
           type         => 'TEXT',
           report_level => 'ALL'
       )
FROM dual;
~~~

Một số execution được Oracle tự động monitor, chẳng hạn parallel SQL hoặc statement đủ điều kiện về thời gian/tài nguyên. Có thể dùng hint MONITOR trong môi trường được cấp phép và kiểm soát.

SQL Monitor và các tính năng Real-Time SQL Monitoring thuộc phạm vi Oracle Diagnostics/Tuning Pack theo điều khoản license tương ứng. Kiểm tra entitlement và chính sách tổ chức trước khi sử dụng trong production.

### 15.1. Khi nào SQL Monitor hữu ích hơn DBMS_XPLAN?

- SQL kéo dài nhiều giây/phút và cần xem tiến độ.
- Parallel execution có nhiều PX server.
- Cần tách CPU, I/O, wait và hoạt động theo operation.
- Cần phân tích một execution cụ thể thay vì thống kê tích lũy.
- Query chạy theo nhiều bước và cần biết bước nào đang chiếm thời gian.

DBMS_XPLAN vẫn là điểm bắt đầu tốt cho plan và row-source statistics của một cursor.

## 16. Quy trình phân tích một query chậm

Dùng quy trình có thứ tự để không nhảy ngay đến việc tạo index hoặc ép join method.

### Bước 1: xác định đúng SQL execution

Ghi nhận SQL_ID, child number, plan hash value, bind values phù hợp và thời điểm thực thi.

### Bước 2: lấy actual plan

Chạy query có GATHER_PLAN_STATISTICS trong môi trường kiểm thử hoặc dùng runtime statistics sẵn có. Hiển thị DBMS_XPLAN.DISPLAY_CURSOR với ALLSTATS LAST.

### Bước 3: tìm row source đầu tiên có sai lệch

Đọc từ dưới lên. So sánh E-Rows với A-Rows/Starts. Đừng so A-Rows tổng với E-Rows nếu Starts lớn hơn 1.

### Bước 4: kiểm tra Buffers và Starts

Xác định operation nào bị gọi lặp và tạo logical reads lớn. Một index lookup rẻ mỗi lần vẫn có thể đắt khi được gọi hàng trăm nghìn lần.

### Bước 5: kiểm tra A-Time và elapsed time

Định vị operation có thời gian đáng kể, nhưng không cộng A-Time trên mọi dòng. Đối chiếu elapsed time toàn SQL và wait events.

### Bước 6: đọc predicates và join method

Kiểm tra access/filter predicate, join order, nested loops/hash join/merge join, partition pruning và sort/hash operations.

### Bước 7: tìm nguyên nhân estimate

Xem stale stats, histogram, extended stats, bind peeking, datatype conversion, partition stats và biểu thức trên cột.

### Bước 8: thử một thay đổi có kiểm soát

Có thể gather stats, tạo extended stats, sửa datatype/bind, thay predicate hoặc index. Thử trên môi trường đại diện hoặc dùng pending statistics nếu phù hợp.

### Bước 9: đo lại

So sánh cùng SQL, bind values, dữ liệu và cách fetch. Ghi lại E-Rows, A-Rows, Starts, Buffers, Reads, A-Time, elapsed time và kết quả nghiệp vụ.

### Bước 10: theo dõi sau triển khai

Kiểm tra child cursor, plan hash, hard parse, wait, latency và các bind values khác nhau. Một thay đổi cải thiện một truy vấn có thể làm truy vấn khác suy giảm.

## 17. Những lỗi diễn giải thường gặp

| Sai lầm | Vì sao sai | Cách đọc đúng |
|---|---|---|
| So E-Rows trực tiếp với A-Rows khi Starts lớn | A-Rows thường là tổng qua mọi starts | So E-Rows với A-Rows/Starts |
| Starts lớn luôn là plan xấu | Inner row source có thể cần chạy mỗi outer row | Đánh giá cost mỗi start và tổng Buffers/A-Time |
| Buffers là physical reads | Buffers là logical buffer gets | Xem Reads riêng |
| Buffers là số block duy nhất | Một block có thể được get nhiều lần | Xem đây là tổng lượt logical access |
| Cộng A-Time mọi dòng | Parent/child có thể phản ánh cùng công việc | Dùng elapsed time toàn SQL/SQL Monitor |
| EXPLAIN PLAN có A-Rows | EXPLAIN PLAN không thực thi SQL | Thu thập runtime stats và DISPLAY_CURSOR |
| A-Rows thấp nghĩa query nhanh | Có thể query chưa fetch hết hoặc đang chờ | Xác nhận completion và elapsed/waits |
| E-Rows sai thì tạo index ngay | Nguyên nhân có thể là statistics, bind hoặc predicate | Tìm sai lệch đầu tiên và nguyên nhân |
| V$SQL elapsed_time là lần chạy cuối | Thống kê thường tích lũy theo child cursor | Dùng SQL Monitor/trace hoặc delta |
| Một plan hash khác nghĩa chậm hơn | Plan khác không đồng nghĩa kém hơn | Đo runtime và kết quả |
| Cost thấp hơn luôn nhanh hơn | Cost là ước lượng optimizer | Đối chiếu actual rows, I/O và thời gian |
| SQL Monitor dùng được không cần kiểm tra license | Tính năng có yêu cầu licensing | Xác nhận entitlement và chính sách |

## 18. Bài thực hành

Thực hiện trên schema lab hoặc môi trường kiểm thử có dữ liệu đại diện.

### Bài 1 — Thu thập actual plan

Chạy một SELECT với GATHER_PLAN_STATISTICS, fetch hết kết quả và hiển thị DBMS_XPLAN.DISPLAY_CURSOR với ALLSTATS LAST. Ghi lại E-Rows, A-Rows, Starts, Buffers, Reads và A-Time.

### Bài 2 — Tạo sai lệch cardinality

Tạo bảng có cột STATUS phân bố lệch mạnh: một giá trị chiếm phần lớn hàng, các giá trị khác hiếm. Gather statistics và chạy predicate cho giá trị phổ biến/hiếm. So sánh estimate và actual.

### Bài 3 — Quan sát histogram

Thu thập statistics với METHOD_OPT phù hợp cho STATUS. Chạy lại các predicate và so sánh E-Rows. Giải thích vì sao histogram có thể cải thiện estimate cho một số bind values.

### Bài 4 — Starts trong nested loops

Tạo hai bảng CUSTOMER và ORDERS. Dùng query join có index trên ORDERS.CUSTOMER_ID. Quan sát Starts của inner index scan khi số customer tăng.

### Bài 5 — Chuẩn hóa A-Rows

Tìm operation có Starts lớn hơn 1. Tính A-Rows/Starts và so sánh với E-Rows. Viết nhận xét vì sao raw A-Rows có thể gây hiểu nhầm.

### Bài 6 — Buffers và Reads

Chạy cùng query ở các điều kiện cache khác nhau trong môi trường lab được kiểm soát. Quan sát Buffers và Reads. Giải thích vì sao logical reads có thể cao dù physical reads thấp.

### Bài 7 — A-Time và elapsed time

Đo thời gian bằng client và so sánh A-Time/elapsed time trong database. Thử query trả nhiều hàng rồi fetch chậm ở client để nhận diện phần thời gian ngoài SQL execution.

### Bài 8 — Sai lệch do correlation

Tạo hai cột có tương quan mạnh. Chạy predicate kết hợp và quan sát E-Rows. Tạo extended statistics column group, gather stats và so sánh.

### Bài 9 — Bind values

Chạy cùng SQL với một bind phổ biến và một bind hiếm. Xem child cursor, plan và actual rows. Giải thích ảnh hưởng của bind peeking/adaptive cursor sharing.

### Bài 10 — Đọc predicate information

Dùng DBMS_XPLAN với +PREDICATE. Xác định access predicate và filter predicate. Thay đổi index hoặc query trong lab rồi so sánh Buffers.

### Bài 11 — V$SQL

Lấy SQL_ID, xem V$SQL executions, elapsed_time, cpu_time, buffer_gets và disk_reads. Chạy query nhiều lần và quan sát các giá trị tích lũy.

### Bài 12 — SQL Monitor

Với môi trường có license và quyền phù hợp, chạy một query đủ dài hoặc parallel, tạo SQL Monitor report và đối chiếu operation timing với DBMS_XPLAN.

### Bài 13 — Viết báo cáo plan

Với một query có plan chậm, ghi:
- Operation sai lệch cardinality đầu tiên.
- E-Rows, Starts, A-Rows và A-Rows/Starts.
- Buffers/Reads/A-Time.
- Predicate liên quan.
- Nguyên nhân giả thuyết.
- Thay đổi thử nghiệm.
- Kết quả trước/sau trên cùng workload.

## 19. Checklist đọc execution plan có runtime statistics

- [ ] Xác định đúng SQL_ID, child number và plan hash value.
- [ ] Xác nhận runtime row-source statistics đã được thu thập.
- [ ] Dùng DBMS_XPLAN.DISPLAY_CURSOR với ALLSTATS LAST.
- [ ] Đảm bảo query được fetch đủ theo mục tiêu đo.
- [ ] Đọc E-Rows, A-Rows và Starts cùng nhau.
- [ ] Chuẩn hóa A-Rows theo Starts khi Starts lớn hơn 1.
- [ ] Tìm sai lệch cardinality đầu tiên từ leaf lên parent.
- [ ] Xem Buffers là logical reads, không phải physical reads.
- [ ] Xem Reads riêng để đánh giá physical I/O.
- [ ] Không cộng Buffers/A-Time các dòng plan một cách máy móc.
- [ ] Đọc predicate information và join method.
- [ ] Kiểm tra histogram, stale stats, extended stats, bind và datatype.
- [ ] Đối chiếu elapsed time toàn SQL, CPU và wait.
- [ ] Dùng V$SQL cho xu hướng tích lũy, không gán cho một execution.
- [ ] Dùng SQL Monitor khi cần per-execution detail và có quyền/license phù hợp.
- [ ] Thay đổi một yếu tố có kiểm soát và đo lại bằng workload tương đương.
- [ ] Ghi lại kết quả trước/sau để có thể hoàn nguyên.

## 20. Ghi nhớ cốt lõi

- E-Rows là số hàng optimizer ước lượng; A-Rows là số hàng row source thực tế tạo ra trong lần execution được ghi nhận.
- Starts là số lần operation được khởi chạy.
- A-Rows thường là tổng qua các lần start; khi Starts lớn hơn 1, so sánh E-Rows với A-Rows/Starts để tránh kết luận sai.
- Inner row source của nested loops thường có Starts lớn vì được gọi lại theo outer rows; Starts cao tự nó không chứng minh plan xấu.
- Sai lệch cardinality ở một row source có thể lan lên join order, join method, Starts và chi phí phía trên.
- Buffers là logical buffer gets; Reads là physical reads. Một block có thể được logical read nhiều lần.
- A-Time là thời gian row-source runtime được ghi nhận; parent/child có thể phản ánh cùng công việc nên không cộng mọi dòng.
- EXPLAIN PLAN chỉ cho estimated plan; muốn A-Rows và runtime statistics, dùng GATHER_PLAN_STATISTICS hoặc STATISTICS_LEVEL = ALL rồi xem DISPLAY_CURSOR.
- ALLSTATS LAST mô tả lần execution được ghi nhận gần nhất của cursor; xác định đúng SQL_ID và child cursor.
- V$SQL chứa số liệu tích lũy theo child cursor; dùng SQL Monitor/trace hoặc delta để phân tích một execution.
- Cardinality sai lệch có thể đến từ stale stats, skew/histogram, correlation, bind values, implicit conversion hoặc partition stats.
- Đọc predicate information cùng plan để phân biệt access và filter.
- Đánh giá query bằng actual rows, Starts, Buffers, Reads, elapsed time, CPU và waits; không dùng cost hoặc plan hash như thước đo hiệu năng duy nhất.
- Thử thay đổi trên workload đại diện, đo trước/sau và theo dõi các bind values khác nhau.

### Tài liệu Oracle nên đối chiếu

- [Oracle Database SQL Tuning Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/tgsql/) — Optimizer estimates, cardinality, execution plans và SQL tuning.
- [Oracle Database PL/SQL Packages and Types Reference — DBMS_XPLAN](https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/DBMS_XPLAN.html) — DISPLAY_CURSOR, ALLSTATS và plan format options.
- [Oracle Database Reference](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/) — V$SQL, V$SQL_PLAN_STATISTICS_ALL, V$SESSION và runtime statistics.
- [Oracle Database Performance Tuning Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/tgdba/) — Buffer gets, physical reads, waits và performance measurement.
- [Oracle Database PL/SQL Packages and Types Reference — DBMS_STATS](https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/DBMS_STATS.html) — Table, index, histogram và extended statistics.
- [Oracle Database SQL Tuning Guide — Monitoring Database Operations](https://docs.oracle.com/en/database/oracle/oracle-database/19/tgsql/) — SQL Monitoring và execution-level diagnostics.

DBMS_XPLAN columns, row-source statistics, SQL Monitor behavior and licensing can vary by Oracle release and contract. Confirm the database version and available privileges/features, then collect measurements in a representative test session before changing production SQL or optimizer statistics.

