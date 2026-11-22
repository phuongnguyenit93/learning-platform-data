# JIT và chi phí biên dịch đối với từng loại truy vấn PostgreSQL

PostgreSQL có thể dùng Just-In-Time compilation (JIT) để chuyển một số biểu thức trong execution plan thành mã máy thông qua LLVM. Với truy vấn đọc nhiều hàng và tiêu tốn CPU để đánh giá điều kiện, tính toán projection hoặc giải mã tuple, mã đã biên dịch có thể chạy nhanh hơn interpreter thông thường.

Đổi lại, JIT phải tạo mã, có thể inline function và chạy các bước tối ưu hóa LLVM trước khi query thực thi. Thời gian biên dịch là chi phí bổ sung cho mỗi lần thực thi cần JIT. Một truy vấn ngắn có thể mất nhiều thời gian biên dịch hơn phần thời gian tiết kiệm được. Vì vậy, JIT phù hợp với một số workload và query shape nhất định, không phải nút tăng tốc chung cho mọi câu SQL.

PostgreSQL quyết định có dùng JIT hay không dựa trên cấu hình và estimated cost của execution plan. Các ngưỡng như `jit_above_cost`, `jit_inline_above_cost` và `jit_optimize_above_cost` cho phép điều chỉnh thời điểm bắt đầu JIT, inlining và tối ưu hóa tốn kém. Những giá trị cost này là đơn vị ước lượng của planner, không phải milliseconds.

~~~text
                 SQL query
                     |
                     v
               Query planner
                     |
              Estimated plan cost
                     |
                     v
               JIT eligibility
             /                 \
            /                   \
      Below threshold       Above threshold
           |                      |
           v                      v
    Normal execution        JIT decision
                                  |
                         +--------+--------+
                         |        |        |
                         v        v        v
                    Expressions Inline  Optimize
                    / tuple       calls  LLVM IR
                    deforming
                         |
                         v
                  Native code emission
                         |
                         v
                  Execute query plan
                         |
                         v
                Compare saved CPU time
                with compilation cost
~~~

Bài này thuộc chương **Tối ưu tài nguyên** của module *Database Engine Relational PostgreSQL*, tập trung vào cơ chế JIT, chi phí biên dịch và cách lựa chọn cấu hình theo từng loại truy vấn.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích JIT compilation trong PostgreSQL và vai trò của LLVM.
2. Phân biệt interpreted expression evaluation với JIT-generated native code.
3. Nêu các phần của execution engine mà JIT có thể tăng tốc.
4. Phân biệt expression compilation và tuple deforming.
5. Giải thích chi phí generation, inlining, optimization và emission.
6. Hiểu vì sao JIT có thể làm truy vấn ngắn chậm hơn.
7. Phân biệt planner cost với thời gian thực thi và milliseconds.
8. Kiểm tra JIT availability bằng pg_jit_available().
9. Đọc và điều chỉnh jit, jit_above_cost và các ngưỡng liên quan.
10. Hiểu jit_inline_above_cost và jit_optimize_above_cost.
11. Kiểm soát expression compilation và tuple deforming.
12. Phân tích JIT cho OLTP point lookup và short transaction.
13. Phân tích JIT cho sequential scan, aggregation và analytical query.
14. Đánh giá JIT với join, filter, projection và biểu thức phức tạp.
15. Nhận diện query bị giới hạn bởi I/O, lock, network hoặc compilation.
16. Đọc JIT section trong EXPLAIN ANALYZE.
17. Kết hợp EXPLAIN với pg_stat_statements để đo chi phí biên dịch.
18. Benchmark JIT on/off một cách công bằng.
19. Cấu hình JIT theo session, role, database và workload class.
20. Theo dõi tác động CPU, latency, throughput và concurrency.
21. Tránh kết luận sai từ một lần chạy hoặc một query plan.
22. Xây dựng chính sách JIT và quy trình troubleshooting.

## 2. JIT compilation là gì?

JIT là kỹ thuật biên dịch mã tại thời điểm chương trình chạy. Thay vì chỉ diễn giải một biểu thức qua execution engine, hệ thống tạo mã máy chuyên biệt cho biểu thức đó rồi thực thi.

### 2.1. Expression evaluation thông thường

PostgreSQL xây dựng execution plan gồm scan, join, aggregate, sort và các plan nodes khác. Khi cần đánh giá một expression, executor sử dụng cơ chế expression evaluation của PostgreSQL.

Ví dụ:

~~~sql
SELECT
    order_id,
    quantity * unit_price * (1 - discount_rate) AS net_amount
FROM app.order_items
WHERE quantity * unit_price > 1000;
~~~

Executor cần đọc các cột, tính toán biểu thức và kiểm tra điều kiện cho những rows được xử lý.

### 2.2. JIT expression compilation

Khi JIT được bật và query đủ điều kiện, PostgreSQL có thể chuyển một số expression operations thành mã native thông qua LLVM. Mã đó được dùng trong quá trình thực thi query hiện tại.

### 2.3. LLVM

LLVM cung cấp hạ tầng compiler và optimizer. PostgreSQL tạo biểu diễn trung gian (IR), sau đó LLVM tối ưu và phát mã máy cho kiến trúc đang chạy.

### 2.4. JIT không biên dịch toàn bộ SQL thành một chương trình độc lập

PostgreSQL vẫn lập execution plan và chạy các plan nodes như trước. JIT tập trung vào một số phần của executor, đặc biệt là expression evaluation và tuple deforming.

### 2.5. JIT không thay thế query planner

Planner vẫn quyết định scan, join order, join algorithm, index usage và các node khác. JIT không tự chọn index tốt hơn hoặc sửa một execution plan kém.

### 2.6. JIT không thay thế indexing và statistics

Nếu query đọc quá nhiều pages do thiếu index hoặc statistics sai, cần sửa nguyên nhân đó. JIT có thể giảm CPU cho một số biểu thức nhưng không biến một access path kém thành access path tốt.

## 3. Điều kiện để PostgreSQL sử dụng JIT

JIT cần PostgreSQL được build với hỗ trợ LLVM và runtime/compiler provider tương thích.

### 3.1. Build có LLVM

Các binary PostgreSQL phải được build với tùy chọn hỗ trợ LLVM. Nếu bản cài không có JIT support, bật cấu hình JIT cũng không làm compiler xuất hiện.

### 3.2. Kiểm tra availability

~~~sql
SELECT pg_jit_available();
~~~

Kết quả true cho biết JIT provider có thể được sử dụng trong session hiện tại. Kết quả false có nghĩa JIT không khả dụng, dù cấu hình có thể đang bật.

### 3.3. Kiểm tra cấu hình

~~~sql
SHOW jit;
SHOW jit_provider;
SHOW jit_above_cost;
SHOW jit_inline_above_cost;
SHOW jit_optimize_above_cost;
SHOW jit_expressions;
SHOW jit_tuple_deforming;
~~~

Một số tham số có thể khác theo major version hoặc build. Dùng SHOW trên server thật để xác nhận.

### 3.4. Phiên bản PostgreSQL

JIT được giới thiệu trong PostgreSQL 11. Khả năng, default values, provider và chi tiết thống kê phụ thuộc major version và cách đóng gói PostgreSQL.

### 3.5. Provider không tải được

Nếu LLVM provider hoặc shared libraries không có, không tương thích hay không load được, JIT có thể không khả dụng. Kiểm tra startup logs và package dependencies.

### 3.6. JIT bật nhưng query không dùng

`jit = on` chỉ cho phép JIT. Query vẫn có thể không dùng JIT vì estimated cost thấp hơn threshold, provider không khả dụng hoặc execution plan không có phần phù hợp để compile.

## 4. Những phần JIT có thể tăng tốc

PostgreSQL JIT tập trung vào expression evaluation và tuple deformation.

### 4.1. Expression evaluation

JIT có thể biên dịch các biểu thức như:
- So sánh và điều kiện WHERE.
- Arithmetic expressions.
- Boolean expressions và CASE.
- Projection expressions trong SELECT.
- Một số expressions dùng trong join và aggregate.
- Các biểu thức được executor đánh giá lặp lại trên nhiều rows.

### 4.2. Tuple deforming

Tuple deforming là quá trình lấy các giá trị column từ tuple representation để executor sử dụng. Với workload xử lý rất nhiều tuples, chi phí giải mã tuple có thể đáng kể.

### 4.3. Function inlining

Inlining có thể thay lời gọi function đủ điều kiện bằng phần thân tương ứng trong mã được biên dịch. Điều này có thể giảm call overhead và mở thêm cơ hội tối ưu hóa.

### 4.4. LLVM optimization

LLVM có thể tối ưu biểu diễn trung gian, ví dụ đơn giản hóa expression và loại bỏ một số phép tính dư thừa. Tối ưu hóa sâu hơn thường làm tăng thời gian biên dịch.

### 4.5. Code emission

Sau khi tạo và tối ưu IR, compiler phát mã máy. Đây là một phần của compilation overhead cần được tính vào tổng query latency.

### 4.6. Những gì JIT không tự giải quyết

JIT không tự:
- Làm storage nhanh hơn hoặc loại bỏ disk I/O.
- Giảm lock waits hoặc deadlocks.
- Tăng network throughput.
- Sửa cardinality estimates.
- Tạo index hoặc chọn lại join order.
- Thay thế sort/hash algorithms bằng thuật toán mới.
- Biên dịch mọi PL/pgSQL procedure hoặc C extension thành native code của query.

### 4.7. JIT và plan nodes

Một scan node có thể gọi expression đã biên dịch để kiểm tra predicate hoặc tạo output. Với join/aggregate, JIT có thể tăng tốc các expressions mà node cần đánh giá; nó không đồng nghĩa toàn bộ thuật toán join hay aggregate được biên dịch lại.

## 5. Chi phí của JIT

JIT giúp giảm chi phí thực thi sau khi mã được tạo, nhưng bản thân quá trình tạo mã cũng tiêu tốn tài nguyên.

### 5.1. Generation time

PostgreSQL tạo JIT context và IR/code structures. Công việc này dùng CPU và memory.

### 5.2. Inlining time

Compiler phân tích và inline các function đủ điều kiện. Inlining có thể tạo mã lớn hơn và làm compilation chậm hơn.

### 5.3. Optimization time

LLVM chạy các optimization passes. Query có nhiều expressions có thể cần thêm thời gian và tài nguyên cho giai đoạn này.

### 5.4. Emission time

LLVM phát mã máy. Thời gian emission cũng được tính trong JIT compilation cost.

### 5.5. Compilation memory

Compiler cần memory cho IR, optimization passes và generated code. Nhiều query JIT đồng thời có thể tăng memory pressure.

### 5.6. CPU contention

Nếu nhiều backend cùng compile query phức tạp, CPU dành cho compilation có thể cạnh tranh với CPU của workload và các process PostgreSQL khác.

### 5.7. Tổng latency

Một mô hình khái niệm:

\[
T_{\text{total}} =
T_{\text{planning}} +
T_{\text{JIT}} +
T_{\text{execution}} +
T_{\text{other}}
\]

Trong đó JIT time gồm generation, inlining, optimization và emission khi các giai đoạn đó được thực hiện. PostgreSQL có thể hiển thị riêng một số thành phần trong EXPLAIN.

### 5.8. Khi JIT có lợi

JIT có lợi khi phần CPU tiết kiệm trong execution lớn hơn compilation overhead và các chi phí tài nguyên liên quan.

### 5.9. Khi JIT có hại

Nếu query chỉ chạy vài milliseconds hoặc chủ yếu chờ I/O/lock, thời gian compile có thể làm tổng latency tăng.

## 6. Planner cost và các ngưỡng JIT

PostgreSQL dùng estimated cost để quyết định khi nào kích hoạt JIT.

### 6.1. Cost không phải milliseconds

Planner cost là đơn vị tương đối được tính từ các tham số như page cost, CPU tuple cost và CPU operator cost. Một plan cost 100000 không có nghĩa query chạy 100000 milliseconds.

### 6.2. Estimated total cost

Ngưỡng JIT thường được so sánh với total estimated cost của query plan. Đây là dự báo của planner dựa trên statistics và cost settings.

### 6.3. jit_above_cost

`jit_above_cost` là ngưỡng estimated cost để bắt đầu sử dụng JIT. Nếu query cost vượt ngưỡng và JIT khả dụng, PostgreSQL có thể compile các phần đủ điều kiện.

~~~sql
SHOW jit_above_cost;
~~~

### 6.4. jit_inline_above_cost

`jit_inline_above_cost` là ngưỡng cost để cho phép inlining. Inlining có thêm chi phí compile nên thường có threshold riêng.

~~~sql
SHOW jit_inline_above_cost;
~~~

### 6.5. jit_optimize_above_cost

`jit_optimize_above_cost` là ngưỡng để bật các bước optimization tốn kém hơn.

~~~sql
SHOW jit_optimize_above_cost;
~~~

### 6.6. Ngưỡng độc lập

Một query có thể đủ điều kiện JIT nhưng chưa đủ cost để bật inlining hoặc optimization sâu. Điều này cho phép chọn mức compile phù hợp với độ lớn dự kiến của workload.

### 6.7. Giá trị -1

Với các threshold hỗ trợ giá trị -1, giá trị này vô hiệu hóa giai đoạn tương ứng. Ví dụ, jit_above_cost = -1 ngăn threshold tự động kích hoạt JIT; jit_inline_above_cost = -1 tắt inlining qua threshold đó.

### 6.8. Ước lượng sai

Nếu statistics cũ hoặc parameter estimates sai, planner cost có thể không phản ánh thời gian CPU thực tế. Query có thể JIT dù ngắn, hoặc không JIT dù thực tế rất nặng.

## 7. Các tham số JIT quan trọng

| Tham số | Vai trò | Câu hỏi cần trả lời |
| --- | --- | --- |
| jit | Cho phép JIT | Có cho phép JIT trong session không? |
| jit_provider | Provider compiler | Provider nào cung cấp JIT? |
| jit_above_cost | Ngưỡng bắt đầu JIT | Query nào đủ cost để compile? |
| jit_inline_above_cost | Ngưỡng inlining | Khi nào đáng inline function? |
| jit_optimize_above_cost | Ngưỡng optimization | Khi nào đáng chạy tối ưu hóa sâu? |
| jit_expressions | Compile expressions | Có compile expression evaluation không? |
| jit_tuple_deforming | Compile tuple deformation | Có compile việc giải mã tuple không? |

### 7.1. jit

~~~sql
SHOW jit;
SET jit = off;
SET jit = on;
~~~

`jit = off` tắt JIT trong session. Đây là cách hữu ích để benchmark đối chứng hoặc tắt JIT cho workload không phù hợp.

### 7.2. jit_expressions

~~~sql
SET jit_expressions = on;
~~~

Điều khiển việc JIT compile expression evaluation.

### 7.3. jit_tuple_deforming

~~~sql
SET jit_tuple_deforming = on;
~~~

Điều khiển việc JIT compile tuple deformation. Hiệu quả phụ thuộc số lượng tuples và schema/query shape.

### 7.4. Thay đổi theo session

Dùng SET để thử nghiệm trên một connection riêng, tránh ảnh hưởng session khác.

### 7.5. Thay đổi trong transaction

~~~sql
BEGIN;
SET LOCAL jit = off;
SELECT count(*) FROM app.events;
COMMIT;
~~~

SET LOCAL chỉ có hiệu lực trong transaction hiện tại. Cách này hữu ích khi application muốn kiểm soát JIT cho một nhóm truy vấn.

### 7.6. Thiết lập theo role/database

Có thể dùng ALTER ROLE ... SET hoặc ALTER DATABASE ... SET để áp dụng policy mặc định cho session mới. Cần kiểm tra lại sau reconnect vì setting ở cấp session không thay đổi các session đang mở.

## 8. JIT threshold không phải query timeout

Các ngưỡng JIT quyết định có compile hay không, không giới hạn thời gian query chạy.

### 8.1. Không phải statement_timeout

`statement_timeout` giới hạn thời gian một statement được phép chạy. `jit_above_cost` dùng estimated planner cost để chọn compilation.

### 8.2. Không phải CPU budget

JIT threshold không cấp hoặc giới hạn số CPU milliseconds. Một query có cost cao có thể chờ I/O lâu; một query cost thấp vẫn có thể tiêu tốn CPU nếu estimates không chính xác.

### 8.3. Không phải giới hạn row count

Query xử lý nhiều rows có thể có cost thấp hoặc cao tùy plan và cost settings. Không dùng số rows đơn lẻ để suy ra JIT có bật hay không.

### 8.4. Không phải ngưỡng latency

Nếu mục tiêu là query latency dưới 100 ms, không đặt jit_above_cost = 100. Cost units không ánh xạ trực tiếp sang milliseconds.

### 8.5. Dùng EXPLAIN để xác nhận

Đọc plan cost và JIT section của chính query thay vì suy đoán từ tham số.

## 9. JIT với OLTP point lookup

OLTP thường gồm nhiều transaction ngắn, thao tác một vài rows và có yêu cầu latency thấp.

### 9.1. Ví dụ point lookup

~~~sql
SELECT order_id, status, created_at
FROM app.orders
WHERE order_id = 9000123;
~~~

Nếu primary key index tìm được một row nhanh, phần expression evaluation thường nhỏ so với thời gian lập kế hoạch, access và trả kết quả.

### 9.2. Compilation overhead chiếm tỷ lệ lớn

Một query hoàn tất trong thời gian ngắn không có đủ số phép tính để bù chi phí tạo mã.

### 9.3. Nhiều lần thực thi

OLTP có thể chạy cùng query hàng nghìn lần. Nếu mỗi lần execution lại cần JIT generation, tổng CPU compile có thể rất lớn.

### 9.4. Prepared statements

Prepared statement có thể tái sử dụng query plan, nhưng không nên giả định việc cache plan đồng nghĩa native code JIT được cache và tái sử dụng qua mọi execution. Đo generation time và calls trên phiên bản thực tế.

### 9.5. Chính sách thường phù hợp

Với workload OLTP latency-sensitive, có thể thử jit=off cho role/database/session ứng dụng rồi benchmark. Không áp dụng toàn cluster nếu vẫn có analytical queries cần JIT.

### 9.6. Ngoại lệ

Một query OLTP có biểu thức CPU-intensive và xử lý lượng rows lớn có thể hưởng lợi. Phân loại theo query shape và số công việc thực tế, không chỉ theo nhãn OLTP.

## 10. JIT với sequential scan lớn

Sequential scan có thể xử lý rất nhiều tuples. Nếu mỗi tuple phải đánh giá expressions, JIT có cơ hội giảm CPU.

~~~sql
SELECT
    sum(quantity * unit_price * (1 - discount_rate))
FROM app.order_items
WHERE extract(year FROM created_at) = 2025
  AND quantity * unit_price > 1000;
~~~

### 10.1. Nhiều rows

Một expression được đánh giá trên hàng triệu tuples có thể tạo lượng CPU work đủ lớn để amortize compilation.

### 10.2. Predicate phức tạp

Arithmetic, Boolean logic, CASE và projection calculations có thể là các phần được JIT compile.

### 10.3. I/O vẫn quan trọng

Nếu table không nằm trong cache và query chủ yếu chờ storage, JIT có thể chỉ giảm một phần CPU mà không cải thiện nhiều elapsed time.

### 10.4. Predicate không sargable

JIT không tự biến biểu thức trên column thành index condition. Nếu có thể dùng expression index, generated column hoặc predicate rewrite phù hợp, hãy đánh giá access path riêng.

### 10.5. Đo CPU và elapsed time

Nếu CPU time giảm nhưng elapsed time gần như không đổi, query có thể bị giới hạn bởi I/O hoặc wait khác.

## 11. JIT với aggregation

Aggregation có thể xử lý số lượng rows lớn và tính toán nhiều expressions.

### 11.1. Aggregate expression

~~~sql
SELECT
    customer_id,
    sum(quantity * unit_price) AS gross_amount,
    avg(quantity * unit_price) AS average_line_amount,
    count(*) FILTER (WHERE status = 'returned') AS returned_lines
FROM app.order_items
GROUP BY customer_id;
~~~

### 11.2. Expression work

JIT có thể tăng tốc expression evaluation cho giá trị đầu vào và projection. Lợi ích thường phụ thuộc số tuples và độ phức tạp phép tính.

### 11.3. Hash aggregate

JIT không thay thế hash table algorithm. Nó có thể compile expressions mà executor dùng khi lấy key, filter hoặc tạo aggregate input.

### 11.4. Sort aggregate

Nếu plan sort trước khi aggregate, thời gian sort vẫn cần được xem riêng. JIT không tự loại bỏ chi phí sắp xếp.

### 11.5. Aggregate có ít rows

Một aggregate trên vài rows thường không có đủ công việc để bù compile overhead.

## 12. JIT với joins

Join có thể xử lý nhiều tuples và đánh giá join/filter expressions lặp lại.

~~~sql
SELECT
    o.region_id,
    sum(oi.quantity * oi.unit_price) AS revenue
FROM app.orders AS o
JOIN app.order_items AS oi
  ON oi.order_id = o.order_id
WHERE o.created_at >= DATE '2025-01-01'
  AND o.created_at < DATE '2026-01-01'
GROUP BY o.region_id;
~~~

### 12.1. Join condition

Biểu thức join condition có thể là một phần của expression evaluation được JIT compile.

### 12.2. Filter sau join

Filter expressions được đánh giá trên tuples đi qua plan nodes. Nếu có nhiều tuples và nhiều phép tính, JIT có thể giảm CPU.

### 12.3. Hash join

JIT có thể giúp expression evaluation xung quanh hash join. Nó không tự thay đổi hash table size, batch count, memory usage hoặc join algorithm.

### 12.4. Nested loop

Nếu nested loop lặp lại inner scan rất nhiều lần, expression work có thể đáng kể. Tuy nhiên, một join order kém vẫn cần được sửa ở planner/index level.

### 12.5. Merge join

JIT không thay thế sorting/merge mechanics. Đánh giá riêng expression CPU và chi phí sort/access.

### 12.6. Cardinality estimates

Join estimates sai có thể làm plan cost và JIT eligibility sai lệch. Cập nhật statistics và kiểm tra estimated rows so với actual rows.

## 13. JIT với biểu thức và function

JIT tập trung vào các expressions được executor xử lý. Không nên hiểu rằng mọi function hoặc ngôn ngữ procedural đều được compile.

### 13.1. Arithmetic và Boolean

Các phép toán số, so sánh và logic trên nhiều rows là trường hợp dễ thấy lợi ích khi expression work chiếm tỷ trọng lớn.

### 13.2. CASE

CASE expressions được đánh giá trên nhiều rows có thể có cơ hội được compile.

### 13.3. Built-in functions

Expression có thể gọi built-in functions. JIT không đảm bảo nội dung của mọi function được inline hoặc biên dịch; một số lời gọi vẫn đi qua function call bình thường.

### 13.4. PL/pgSQL

JIT không biên dịch toàn bộ thân PL/pgSQL thành native program. SQL statements và expressions được thực thi bên trong có thể đi qua executor/JIT theo điều kiện của chúng.

### 13.5. C extensions

JIT không tự biên dịch lại mã C của extension. Extension được build và load theo cơ chế riêng.

### 13.6. Regex và JSON

Query dùng regex hoặc JSON có thể chịu chi phí trong function implementation, parsing và allocation. JIT có thể tối ưu phần expression xung quanh, nhưng không nên mặc định nó loại bỏ chi phí nội bộ của các function phức tạp.

### 13.7. Function volatility

Volatility, strictness và khả năng inline của function ảnh hưởng planner/executor behavior. Không đánh giá JIT chỉ từ việc query có nhiều function calls.

## 14. JIT với sort, window và analytic queries

Analytical queries có thể chứa nhiều expressions nhưng thời gian thực thi cũng có thể bị chi phối bởi sort, memory và I/O.

### 14.1. Sort key

JIT có thể giúp một số expressions dùng để tạo sort key. Thuật toán sort và việc so sánh/di chuyển dữ liệu vẫn có chi phí riêng.

### 14.2. Window functions

Các expressions đầu vào, filter và projection có thể được JIT compile. Window processing và partition/order work không được thay thế toàn bộ bởi JIT.

### 14.3. Wide rows

Tuple deforming có thể đáng kể khi query đọc nhiều columns hoặc nhiều tuples. Kiểm tra projection pruning và chỉ chọn columns cần thiết.

### 14.4. Large analytical scan

Đây là nhóm có khả năng hưởng lợi nếu CPU expression evaluation là bottleneck và query đủ dài.

### 14.5. Memory spills

Nếu sort/hash spill ra temporary files, I/O và memory configuration có thể chi phối thời gian. JIT không thay thế việc xử lý work_mem, query shape hoặc storage.

## 15. JIT và parallel query

Parallel query chia một số công việc giữa leader và workers. JIT vẫn cần được đánh giá cùng chi phí compilation và scheduling.

### 15.1. Parallel plan

Một query parallel có thể xử lý nhiều tuples và có expression workload lớn, tạo cơ hội cho JIT.

### 15.2. Compilation overhead

Parallelism không làm compilation cost biến mất. Đo JIT timing và tổng elapsed time trong cùng điều kiện concurrency.

### 15.3. CPU saturation

Nếu workers đã sử dụng hết CPU, compile thêm code có thể làm contention tăng. So sánh throughput toàn hệ thống, không chỉ latency một query.

### 15.4. Worker variability

Số workers thực tế có thể khác số dự kiến vì giới hạn tài nguyên. Ghi nhận plan và worker counts khi benchmark.

### 15.5. Đánh giá theo concurrency

Một query chạy đơn lẻ có thể hưởng lợi nhưng khi nhiều query JIT cùng chạy, compilation có thể làm p95/p99 latency tăng. Benchmark với concurrency gần workload thật.

## 16. JIT và prepared statements

Prepared statements giảm chi phí parse/plan cho các lần chạy lặp, nhưng JIT là một bước riêng.

### 16.1. Plan reuse

Prepared statement có thể dùng custom plan hoặc generic plan tùy execution history và planner decisions.

### 16.2. JIT eligibility

JIT dựa trên plan cost của execution plan đang được dùng. Generic plan có estimates khác custom plan, do đó có thể dẫn tới quyết định JIT khác.

### 16.3. Parameter sensitivity

Một parameter có thể làm số rows thực tế khác biệt lớn. Generic plan không phản ánh mọi giá trị parameter cụ thể.

### 16.4. JIT code lifetime

Không nên giả định native code được lưu vĩnh viễn chỉ vì prepared statement còn tồn tại. Kiểm tra JIT generation time qua các lần execute và theo dõi theo version.

### 16.5. EXPLAIN EXECUTE

Dùng EXPLAIN EXECUTE để quan sát plan của prepared statement. Benchmark custom/generic plan theo workload thực tế nếu parameter sensitivity lớn.

### 16.6. Connection pool

Session-level SET có thể không được áp dụng như dự kiến khi connection được tái sử dụng. Dùng role/database settings hoặc SET LOCAL có kiểm soát.

## 17. Quan sát JIT bằng EXPLAIN ANALYZE

EXPLAIN là công cụ quan trọng để biết query có JIT và compilation tốn bao nhiêu.

~~~sql
EXPLAIN (ANALYZE, BUFFERS, SETTINGS)
SELECT
    customer_id,
    sum(quantity * unit_price * (1 - discount_rate))
FROM app.order_items
WHERE created_at >= DATE '2025-01-01'
GROUP BY customer_id;
~~~

### 17.1. Plan cost

Đọc estimated cost và actual time ở từng node. So sánh estimated rows với actual rows để đánh giá planner estimates.

### 17.2. JIT section

Khi query dùng JIT, output có thể chứa section JIT với số functions, các options và timing.

### 17.3. Functions

Số JIT functions cho biết lượng function code được tạo cho query. Không đồng nghĩa với số SQL functions mà ứng dụng gọi.

### 17.4. Options

Output có thể cho biết Inlining, Optimization, Expressions và Deforming đang bật hay tắt cho lần thực thi.

### 17.5. Timing

Timing có thể tách:
- Generation.
- Inlining.
- Optimization.
- Emission.

Tổng hợp các giai đoạn này để thấy compilation overhead.

### 17.6. Execution Time

Execution Time tổng thể bao gồm tác động của quá trình thực thi và JIT theo cách đo của EXPLAIN. Đừng chỉ nhìn actual time ở scan node rồi bỏ qua JIT timing.

### 17.7. EXPLAIN ANALYZE thực thi query

EXPLAIN ANALYZE thật sự chạy statement. Dùng cẩn thận với DML hoặc query có side effects. Với test DML, có thể dùng transaction và ROLLBACK nhưng sequence values và side effects ngoài database có thể không rollback.

### 17.8. BUFFERS

BUFFERS giúp phân biệt query đọc nhiều buffers với query có CPU expression work lớn. Kết hợp với OS metrics để hiểu physical I/O.

## 18. So sánh JIT on và off

Để biết JIT có giúp query cụ thể hay không, chạy cùng query với cùng dữ liệu và điều kiện.

### 18.1. Lần chạy JIT on

~~~sql
SET jit = on;

EXPLAIN (ANALYZE, BUFFERS, SETTINGS)
SELECT sum(amount * tax_rate)
FROM app.sales
WHERE region_id = 10;
~~~

### 18.2. Lần chạy JIT off

~~~sql
SET jit = off;

EXPLAIN (ANALYZE, BUFFERS, SETTINGS)
SELECT sum(amount * tax_rate)
FROM app.sales
WHERE region_id = 10;
~~~

### 18.3. Giữ các yếu tố giống nhau

Dùng cùng dataset, parameter values, cache conditions, concurrency, plan settings và thời gian đo. Nếu plan thay đổi vì setting khác, tách riêng ảnh hưởng đó.

### 18.4. Warm cache và cold cache

Thử workload warm-cache và cold-cache theo kịch bản có thể tái lập. Không so sánh một lần cold-cache với một lần warm-cache.

### 18.5. Lặp lại nhiều lần

Chạy đủ repetitions và so median, p95/p99, variance, CPU và throughput. Một lần chạy có thể bị ảnh hưởng bởi OS cache, checkpoint, background workers hoặc load khác.

### 18.6. Không chỉ đo query đơn

Kiểm tra nhiều concurrent sessions. JIT có thể giúp một query nhưng giảm throughput nếu compile overhead làm CPU bão hòa.

### 18.7. Giữ plan ổn định khi cần

Nếu mục tiêu là so sánh JIT thuần túy, xác nhận plan shape giống nhau. Nếu plan khác, ghi rõ sự khác biệt.

## 19. pg_stat_statements và JIT statistics

pg_stat_statements tổng hợp statistics theo query identity và có thể cung cấp các trường JIT trên phiên bản hỗ trợ.

### 19.1. Kiểm tra extension

~~~sql
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;
~~~

Extension cần được cấu hình theo hướng dẫn phiên bản, thường gồm shared_preload_libraries và restart server.

### 19.2. Các trường JIT

Trên các phiên bản hỗ trợ, view có thể cung cấp:
- jit_functions
- jit_generation_time
- jit_inlining_count
- jit_inlining_time
- jit_optimization_count
- jit_optimization_time
- jit_emission_count
- jit_emission_time

### 19.3. Truy vấn thống kê

~~~sql
SELECT
    queryid,
    calls,
    total_exec_time,
    mean_exec_time,
    jit_functions,
    jit_generation_time,
    jit_inlining_count,
    jit_inlining_time,
    jit_optimization_count,
    jit_optimization_time,
    jit_emission_count,
    jit_emission_time
FROM pg_stat_statements
ORDER BY total_exec_time DESC
LIMIT 20;
~~~

Nếu một cột chưa có trên phiên bản đang chạy, kiểm tra schema view trước khi dùng query này.

### 19.4. Generation time per call

Có thể tính tỷ lệ compilation time trung bình theo calls khi calls lớn hơn zero. Đây là tín hiệu hữu ích để tìm query đang trả nhiều chi phí JIT.

### 19.5. Cumulative statistics

Các trường trong pg_stat_statements thường là số tích lũy từ lần reset. Tính delta theo khoảng thời gian và ghi nhận reset events.

### 19.6. Query identity

queryid nhóm các câu lệnh tương tự theo cơ chế fingerprint của extension. Không dùng query text raw làm label metric.

### 19.7. Không nhầm tổng JIT time với latency

jit_generation_time và các trường liên quan là tổng thời gian compile được thống kê. Muốn đánh giá per-call cần chia cho calls thích hợp và xem phân bố latency bằng công cụ khác.

## 20. Phân loại query theo lợi ích JIT

| Loại query | Khả năng hưởng lợi | Lý do chính |
| --- | --- | --- |
| Primary-key point lookup | Thấp | Ít rows, ít expression work |
| Short OLTP transaction | Thấp | Compilation overhead dễ chiếm tỷ trọng lớn |
| Large sequential scan | Trung bình đến cao | Nhiều tuples và expressions lặp lại |
| CPU-heavy aggregation | Trung bình đến cao | Nhiều phép tính trên nhiều rows |
| Large join với filters | Trung bình đến cao | Nhiều expression evaluations |
| Sort-dominated query | Thường hạn chế | Sort mechanics không được thay thế |
| I/O-bound scan | Thường hạn chế | Thời gian chờ storage chi phối |
| Lock-bound query | Thấp | JIT không giảm lock waits |
| Complex projection trên nhiều rows | Có thể cao | Expression work lớn |
| Query có ít rows nhưng function đắt | Phụ thuộc | Function body không nhất thiết được JIT compile |
| Parallel analytical query | Phụ thuộc | Có thể giảm CPU nhưng tăng compile contention |
| Prepared statement chạy lặp | Phụ thuộc | Plan reuse không bảo đảm loại bỏ JIT generation |

### 20.1. Query ngắn không đồng nghĩa luôn không JIT

Nếu planner cost vượt threshold do một số yếu tố, JIT vẫn có thể được chọn. Đo actual work và JIT timing.

### 20.2. Query dài không đồng nghĩa luôn có lợi

Một query chạy lâu vì chờ I/O hoặc lock có thể không hưởng lợi đáng kể từ expression compilation.

### 20.3. Phân loại theo bottleneck

Hãy phân loại CPU-bound, I/O-bound, lock-bound, network-bound và compile-bound trước khi thay đổi JIT.

## 21. Ví dụ OLTP và OLAP

### 21.1. OLTP lookup

~~~sql
SELECT status
FROM app.orders
WHERE order_id = $1;
~~~

Đây thường là query rất ngắn. Nếu index lookup trả về một row, chi phí JIT có thể lớn hơn phần CPU tiết kiệm được.

### 21.2. OLTP update

~~~sql
UPDATE app.inventory
SET available = available - $1
WHERE product_id = $2;
~~~

Một update đơn lẻ thường không cần JIT. Ngoài ra, query có thể bị giới hạn bởi lock và WAL work.

### 21.3. OLAP aggregate

~~~sql
SELECT
    date_trunc('month', created_at) AS month,
    region_id,
    sum(quantity * unit_price),
    avg(quantity * unit_price)
FROM app.sales
WHERE created_at >= DATE '2024-01-01'
GROUP BY 1, 2;
~~~

Nếu query quét và tính toán trên nhiều rows, JIT có thể giảm CPU expression overhead.

### 21.4. Mixed workload

Một database có thể chạy cả OLTP và OLAP. Cấu hình JIT theo role hoặc workload class có thể phù hợp hơn một threshold chung.

### 21.5. Reporting role

Có thể cho phép JIT với reporting role nếu benchmark cho thấy lợi ích, trong khi tắt cho role ứng dụng latency-sensitive.

### 21.6. Query routing

Nếu analytical workload chạy trên reporting replica, đo JIT và resource contention riêng trên replica. JIT không làm biến mất giới hạn CPU của node.

## 22. Điều chỉnh JIT theo workload

Không nên bắt đầu bằng cách hạ tất cả thresholds. Trước tiên cần đo.

### 22.1. Baseline

Ghi lại query latency, CPU usage, throughput, JIT generation time, plan cost và resource contention trước khi thay đổi.

### 22.2. Tắt JIT cho workload ngắn

~~~sql
ALTER ROLE app_runtime SET jit = off;
~~~

Setting này áp dụng cho session mới của role sau khi kết nối lại. Xác nhận policy với connection pool.

### 22.3. Giữ JIT cho reporting

~~~sql
ALTER ROLE reporting SET jit = on;
~~~

Vẫn cần threshold phù hợp và benchmark. JIT on không bắt buộc mọi query của role phải compile.

### 22.4. Hạ threshold

~~~sql
SET jit_above_cost = 50000;
~~~

Ví dụ này chỉ minh họa cách đặt threshold. Không dùng như giá trị mặc định được khuyến nghị cho mọi cluster.

### 22.5. Tắt inlining nhưng giữ expression JIT

~~~sql
SET jit_inline_above_cost = -1;
~~~

Có thể thử khi inlining time lớn mà execution benefit nhỏ.

### 22.6. Tắt optimization sâu

~~~sql
SET jit_optimize_above_cost = -1;
~~~

Đánh giá khi optimization time lớn hoặc query có latency target chặt.

### 22.7. Tắt tuple deforming

~~~sql
SET jit_tuple_deforming = off;
~~~

Dùng benchmark để xem tuple deforming có tạo lợi ích cho workload hiện tại không.

### 22.8. Không áp dụng toàn cục khi chưa đo

Một thay đổi có thể cải thiện reporting nhưng làm OLTP tệ hơn. Thử theo role/session trước, sau đó mới cân nhắc policy rộng hơn.

## 23. Cấu hình theo role, database và session

PostgreSQL cho phép đặt một số GUC ở nhiều scope.

### 23.1. Session

~~~sql
SET jit = off;
~~~

Chỉ ảnh hưởng connection hiện tại.

### 23.2. Transaction

~~~sql
BEGIN;
SET LOCAL jit = off;
SELECT count(*) FROM app.orders;
COMMIT;
~~~

Hữu ích khi application biết query class của transaction.

### 23.3. Role

~~~sql
ALTER ROLE app_runtime SET jit = off;
ALTER ROLE analytics_runtime SET jit = on;
~~~

Setting role áp dụng cho session mới của role đó.

### 23.4. Database

~~~sql
ALTER DATABASE appdb SET jit = on;
~~~

Setting database là default cho các session mới vào database, trừ khi bị override ở scope khác.

### 23.5. Role trong database

~~~sql
ALTER ROLE reporting IN DATABASE appdb
SET jit_above_cost = 50000;
~~~

Có thể cấu hình riêng cho role/database combination nếu phù hợp.

### 23.6. Thứ tự ưu tiên

Session-level SET có thể override default từ role/database. Khi điều tra, dùng SHOW hoặc current_setting() trong chính connection chạy query.

### 23.7. Connection pool

Nếu pool giữ connection lâu, thay đổi role/database defaults không nhất thiết ảnh hưởng session đang mở. Recycle connection theo quy trình kiểm soát.

## 24. JIT, statistics và plan quality

JIT eligibility phụ thuộc planner cost. Vì vậy chất lượng statistics ảnh hưởng quyết định.

### 24.1. ANALYZE

Statistics cũ có thể làm estimated rows và total cost sai. Chạy ANALYZE phù hợp sau data changes lớn.

### 24.2. Extended statistics

Nếu predicates có correlation giữa nhiều columns, extended statistics có thể cải thiện estimates cho một số query patterns.

### 24.3. Estimated versus actual rows

Trong EXPLAIN ANALYZE, so sánh rows estimate và actual. Sai lệch lớn có thể làm threshold decision thiếu chính xác.

### 24.4. Cost parameters

seq_page_cost, random_page_cost, cpu_tuple_cost và cpu_operator_cost ảnh hưởng planner cost. Không chỉnh các tham số này chỉ để ép JIT bật/tắt vì chúng còn ảnh hưởng plan selection.

### 24.5. JIT không sửa bad plan

Nếu plan dùng nested loop trên hàng triệu rows ngoài dự kiến, cần điều tra statistics/index/join order. JIT có thể tăng tốc expression nhưng không giải quyết plan shape sai.

### 24.6. Parameterized queries

Giá trị parameter khác nhau có thể tạo custom plans khác nhau hoặc cùng generic plan. Benchmark nhiều giá trị đại diện.

## 25. JIT và resource contention

JIT tiêu tốn CPU và memory ngoài chi phí executor thông thường.

### 25.1. CPU usage

Theo dõi process CPU, system CPU và total CPU usage trong benchmark. Nếu CPU bão hòa, compile thêm có thể làm queue tăng.

### 25.2. Memory

LLVM compilation sử dụng memory. Với nhiều query JIT đồng thời, xem process memory và host memory pressure.

### 25.3. Concurrency

Đo số query JIT đồng thời, active sessions và p95/p99 latency. Một query đơn lẻ nhanh hơn không đảm bảo toàn hệ thống nhanh hơn.

### 25.4. Connection pool

Pool có thể tạo burst query đồng thời. Giới hạn concurrency cho reporting workload nếu compile load làm ảnh hưởng OLTP.

### 25.5. Parallel workers

Parallel workers và leader cùng cạnh tranh CPU. Đo worker counts, JIT timing và throughput dưới tải thực tế.

### 25.6. CPU quotas trong container

Container CPU limits có thể làm compile time tăng khi bị throttling. So sánh JIT results trong cùng quota và quan sát throttling metrics.

### 25.7. NUMA và CPU architecture

Native code chạy trên host architecture. Khi di chuyển workload giữa hosts khác nhau, benchmark lại thay vì giả định compile cost và performance giống nhau.

## 26. Monitoring JIT

Theo dõi JIT cần kết hợp query-level statistics, EXPLAIN và host resource metrics.

### 26.1. EXPLAIN ANALYZE

Dùng cho query cụ thể để đọc số functions và compilation timings.

### 26.2. pg_stat_statements

Theo dõi tổng JIT functions, generation, inlining, optimization và emission time nếu view cung cấp các cột đó.

### 26.3. Compile time per call

Một chỉ số phân tích có thể là:

\[
\text{JIT generation per call} =
\frac{\text{jit generation time}}
{\text{calls}}
\]

Đây là trung bình tích lũy, không thay thế latency distribution.

### 26.4. Compilation share

So sánh tổng JIT time với total execution time của cùng query group. Nếu compilation chiếm tỷ lệ cao, thử threshold cao hơn hoặc giảm các giai đoạn compile.

### 26.5. JIT function count

Số functions tăng không tự động xấu. Đối chiếu với compilation time và execution savings.

### 26.6. CPU và throughput

Kết hợp host CPU, run queue, query throughput, p95 latency và database wait events.

### 26.7. Reset statistics

pg_stat_statements counters có thể reset. Tính delta theo khoảng scrape và ghi nhận reset time để không tạo spike/negative rate giả.

## 27. Ví dụ truy vấn monitoring JIT

### 27.1. Kiểm tra JIT availability và settings

~~~sql
SELECT
    pg_jit_available() AS jit_available,
    current_setting('jit') AS jit_enabled,
    current_setting('jit_provider') AS jit_provider,
    current_setting('jit_above_cost') AS jit_above_cost,
    current_setting('jit_inline_above_cost') AS jit_inline_above_cost,
    current_setting('jit_optimize_above_cost') AS jit_optimize_above_cost;
~~~

### 27.2. Kiểm tra pg_stat_statements columns

Dùng psql:

~~~text
\d+ pg_stat_statements
~~~

Hoặc query information_schema/catalog để xác định các cột JIT đang có trên version hiện tại.

### 27.3. Top query theo JIT generation time

Trên version có các cột tương ứng:

~~~sql
SELECT
    queryid,
    calls,
    total_exec_time,
    mean_exec_time,
    jit_functions,
    jit_generation_time,
    jit_inlining_time,
    jit_optimization_time,
    jit_emission_time,
    left(query, 200) AS query_sample
FROM pg_stat_statements
ORDER BY jit_generation_time DESC
LIMIT 20;
~~~

### 27.4. Tính generation time trung bình

~~~sql
SELECT
    queryid,
    calls,
    jit_generation_time,
    jit_generation_time / NULLIF(calls, 0) AS generation_ms_per_call
FROM pg_stat_statements
WHERE calls > 0
ORDER BY generation_ms_per_call DESC
LIMIT 20;
~~~

### 27.5. Đọc cẩn thận

Các trường JIT có thể không tồn tại trên phiên bản cũ. Chạy query kiểm tra schema trước khi đưa vào exporter/custom dashboard.

### 27.6. Export metrics

Nếu dùng postgres_exporter custom queries, có thể xuất counters JIT tổng hợp từ pg_stat_statements. Dùng queryid hoặc nhóm ổn định làm label; không xuất raw SQL hoặc parameter values.

## 28. Benchmark JIT đúng cách

Một benchmark tốt phải đo cả thời gian compile lẫn phần thực thi được tăng tốc.

### 28.1. Chọn query đại diện

Chọn query OLTP ngắn, scan lớn, aggregate, join và query CPU-heavy từ workload thực tế.

### 28.2. Chuẩn bị dataset

Dùng data volume, distribution, indexes và statistics gần production. Synthetic data quá đơn giản có thể làm estimates và expression behavior khác thực tế.

### 28.3. Giữ plan tương đương

Lưu EXPLAIN plan của JIT on/off. Nếu plan shape khác, phân tích riêng thay đổi planner.

### 28.4. Warm-up

Thực hiện warm-up để giảm ảnh hưởng của cache cold-start và library loading. Ghi rõ benchmark cold hay warm.

### 28.5. Lặp lại

Chạy nhiều lần, lưu từng sample và so median, p95/p99 cùng độ phân tán. Không chỉ lấy lần nhanh nhất.

### 28.6. Đo CPU

Dùng OS monitoring/performance tooling để quan sát CPU utilization và CPU time. JIT có thể giảm elapsed time hoặc chỉ thay đổi cách sử dụng CPU.

### 28.7. Đo compile stages

Đọc JIT timing trong EXPLAIN và pg_stat_statements. Xác định generation, inlining hay optimization là phần tốn nhất.

### 28.8. Concurrency test

Chạy ở mức concurrency đại diện. Quan sát throughput và tail latency, không chỉ latency trung bình.

### 28.9. Tách query classes

Tạo bảng kết quả riêng cho OLTP, reporting, ETL và background jobs. Không gộp tất cả thành một trung bình.

### 28.10. Rollback thay đổi

Lưu cấu hình cũ và dùng session/role scope khi thử. Nếu kết quả xấu, khôi phục policy đã ghi nhận.

## 29. Cách đọc kết quả benchmark

| Quan sát | Diễn giải có thể | Hướng điều tra |
| --- | --- | --- |
| JIT time lớn, query ngắn | Compile overhead chiếm tỷ trọng cao | Tăng threshold hoặc tắt JIT cho workload |
| JIT time nhỏ, execution giảm rõ | JIT có thể có lợi | Kiểm tra concurrency và throughput |
| CPU giảm nhưng elapsed time không đổi | Query có thể bị I/O/wait bound | Xem buffers, waits và storage |
| JIT on nhanh khi chạy đơn, chậm khi concurrent | Compile contention | Đo CPU saturation và concurrency |
| Inlining time lớn | Inline work tốn kém | Thử tăng jit_inline_above_cost hoặc tắt inlining |
| Optimization time lớn | LLVM optimization overhead cao | Thử tăng jit_optimize_above_cost |
| Query không có JIT section | Không đủ threshold hoặc JIT unavailable | Kiểm tra pg_jit_available, settings và plan cost |
| Query JIT nhưng ít functions | Có ít code được compile | Đánh giá lợi ích thực tế thay vì chỉ nhìn JIT flag |

### 29.1. So sánh theo tỷ lệ

Tính phần compilation time trong tổng latency để biết JIT có đáng bật cho query class đó không.

### 29.2. So sánh theo throughput

Nếu latency query đơn giảm nhưng số queries/second giảm, policy có thể không phù hợp cho production.

### 29.3. So sánh tail latency

p95/p99 thường quan trọng hơn mean trong OLTP. Compilation spikes có thể ảnh hưởng tail latency.

### 29.4. Không tối ưu theo một query duy nhất

Tối ưu database cho workload tổng thể. Một báo cáo nhanh hơn không nên làm hàng nghìn requests OLTP chậm đi mà không có lý do chấp nhận được.

## 30. Các chiến lược tuning thường gặp

### 30.1. JIT off cho OLTP

Dùng jit=off cho role hoặc session latency-sensitive khi benchmark cho thấy compile overhead lớn hơn lợi ích.

### 30.2. JIT on cho reporting

Giữ JIT cho analytical queries xử lý nhiều rows và CPU-bound, nhưng vẫn dùng thresholds phù hợp.

### 30.3. Tăng jit_above_cost

Tăng threshold làm ít query được compile hơn, phù hợp khi nhiều query ngắn bị JIT ngoài ý muốn.

### 30.4. Tách inlining và optimization

Nếu generation có lợi nhưng inlining/optimization tốn quá nhiều, thử điều chỉnh từng threshold để xác định stage nào tạo lợi ích.

### 30.5. Giữ tuple deforming khi có lợi

Query quét nhiều tuples/wide rows có thể hưởng lợi từ tuple deforming. Benchmark riêng trước khi tắt.

### 30.6. Tách workload class

Dùng role/database/service endpoint riêng cho OLTP và reporting để áp dụng JIT policy khác nhau.

### 30.7. Kết hợp với query tuning

Index phù hợp, projection hẹp, predicate tốt, statistics đúng và giảm rows sớm thường đem lại lợi ích lớn hơn việc chỉ chỉnh JIT.

## 31. Troubleshooting JIT

### Lỗi 1. pg_jit_available() trả false

Kiểm tra PostgreSQL build có LLVM support, provider library và package/runtime compatibility.

### Lỗi 2. jit=on nhưng không thấy JIT section

Kiểm tra plan cost có vượt jit_above_cost không, provider availability và query có expression work phù hợp không.

### Lỗi 3. Query chậm hơn khi JIT bật

Đọc generation/inlining/optimization/emission time, so sánh JIT off và xem query có quá ngắn hay bị I/O bound.

### Lỗi 4. Inlining làm compile chậm

Tăng jit_inline_above_cost hoặc thử tắt inlining trong session benchmark.

### Lỗi 5. Optimization time cao

Tăng jit_optimize_above_cost hoặc tắt optimization sâu theo workload test.

### Lỗi 6. CPU tăng sau khi bật JIT

Kiểm tra số query JIT đồng thời, compilation time, connection pool và CPU saturation.

### Lỗi 7. p95 tăng dù query trung bình nhanh hơn

Compilation bursts hoặc contention có thể làm tail latency tăng. Kiểm tra concurrency và phân phối latency.

### Lỗi 8. JIT threshold không có tác dụng như dự kiến

Kiểm tra setting thực trong connection chạy query bằng SHOW/current_setting, role/database defaults và connection pool reuse.

### Lỗi 9. pg_stat_statements thiếu JIT columns

Kiểm tra PostgreSQL major version, extension version và schema của view.

### Lỗi 10. Query có cost thấp nhưng CPU cao

Kiểm tra estimates, statistics, actual rows và expression complexity. Cost không phải CPU budget.

### Lỗi 11. Query cost cao nhưng không nhanh hơn

Xác định bottleneck có phải I/O, lock, sort, hash spill, network hoặc function implementation không được JIT compile hay không.

### Lỗi 12. Container bị CPU throttling

Quan sát CPU quota/throttling và lặp lại benchmark trong điều kiện quota ổn định.

### Lỗi 13. JIT availability khác giữa nodes

So sánh PostgreSQL build, LLVM package và configuration trên từng host. Không giả định mọi replica có binary giống nhau.

### Lỗi 14. Prepared query compile lặp lại

Đo JIT generation time theo calls. Không giả định plan cache giữ lại native code; cân nhắc tắt JIT cho query class chạy rất thường xuyên.

### Lỗi 15. Dashboard JIT time bằng zero

Kiểm tra metric/collector có xuất các cột JIT không, JIT có thực sự được dùng và statistics có được reset hay không.

## 32. Quy trình quyết định bật JIT

~~~text
Identify query class
        |
        v
Is JIT available?
    |           |
   No          Yes
    |           |
Check build      v
and provider  Is query CPU-bound?
                 |          |
                No         Yes
                 |          |
             JIT likely     v
             low value  Does cost exceed threshold?
                            |           |
                           No          Yes
                            |           |
                       No JIT yet       v
                                 Measure compilation time
                                          |
                                          v
                                  Compare JIT on/off
                                          |
                                          v
                                  Test concurrency
                                          |
                                +---------+---------+
                                |                   |
                           Benefit stable       No benefit/
                                |               regression
                                v                   |
                         Apply by workload        v
                              class          Raise threshold
                                             or disable JIT
~~~

### 32.1. Xác định workload

Chọn query classes theo latency target, frequency, row volume và CPU profile.

### 32.2. Kiểm tra availability

Xác nhận build/provider và cấu hình thực tế.

### 32.3. Đọc plan cost

Xác nhận threshold có thể kích hoạt JIT.

### 32.4. Đo compilation

Dùng EXPLAIN và pg_stat_statements để ghi lại chi phí JIT.

### 32.5. So sánh execution

Benchmark JIT on/off trên cùng workload và data conditions.

### 32.6. Kiểm tra concurrency

Đo throughput, CPU, memory và tail latency.

### 32.7. Áp dụng có phạm vi

Dùng role/session/database policy phù hợp, theo dõi và có rollback.

## 33. Bài tập thực hành

Các bài tập nên chạy trên PostgreSQL lab với dataset đại diện. EXPLAIN ANALYZE thực thi query thật, nên tránh thử DML có side effects trên production.

### Bài 1. JIT

JIT compilation là gì trong PostgreSQL?

### Bài 2. LLVM

LLVM tham gia vào quá trình JIT như thế nào?

### Bài 3. Scope

JIT có biên dịch toàn bộ SQL thành một executable độc lập không?

### Bài 4. Expressions

Kể bốn loại expression có thể được JIT compile.

### Bài 5. Tuple deforming

Tuple deforming là gì và vì sao nó có thể tốn CPU?

### Bài 6. Compilation stages

Kể bốn thành phần timing chính của JIT.

### Bài 7. Availability

Viết SQL kiểm tra JIT có khả dụng không.

### Bài 8. Build

Vì sao jit=on chưa đủ để bảo đảm JIT hoạt động?

### Bài 9. Cost units

jit_above_cost có đơn vị milliseconds không?

### Bài 10. Threshold

Tham số nào điều khiển ngưỡng bắt đầu JIT?

### Bài 11. Inlining

Tham số nào điều khiển ngưỡng inlining?

### Bài 12. Optimization

Tham số nào điều khiển ngưỡng optimization sâu?

### Bài 13. Disable

Nêu hai cách tắt JIT cho một query/session.

### Bài 14. OLTP

Vì sao point lookup thường ít hưởng lợi từ JIT?

### Bài 15. OLAP

Vì sao analytical scan lớn có thể hưởng lợi?

### Bài 16. I/O bound

Vì sao JIT không giúp nhiều khi query chờ disk?

### Bài 17. Join

JIT có thay thế hash join algorithm không?

### Bài 18. Sort

JIT có loại bỏ chi phí sort không?

### Bài 19. Function

JIT có biên dịch toàn bộ PL/pgSQL function body thành native code không?

### Bài 20. Prepared statement

Plan cache có bảo đảm native JIT code được giữ lại qua mọi lần execute không?

### Bài 21. EXPLAIN

Viết lệnh EXPLAIN để đo query và buffers.

### Bài 22. JIT section

Nêu những thông tin có thể xuất hiện trong JIT section của EXPLAIN.

### Bài 23. pg_stat_statements

Kể bốn JIT-related fields có thể có trong pg_stat_statements.

### Bài 24. Calls

Vì sao cần so JIT generation time với calls?

### Bài 25. Counter reset

Vì sao phải ghi nhận statistics reset khi so sánh JIT metrics?

### Bài 26. Threshold too low

Điều gì có thể xảy ra nếu jit_above_cost đặt quá thấp?

### Bài 27. Inlining cost

Khi inlining time lớn, có thể thử điều chỉnh tham số nào?

### Bài 28. Optimization cost

Khi optimization time lớn, có thể thử điều chỉnh tham số nào?

### Bài 29. Benchmark

Nêu năm yếu tố cần giữ ổn định khi so sánh JIT on/off.

### Bài 30. Concurrency

Vì sao phải benchmark nhiều concurrent sessions?

### Bài 31. Role policy

Viết SQL tắt JIT mặc định cho role app_runtime.

### Bài 32. Reporting policy

Viết SQL bật JIT mặc định cho role reporting.

### Bài 33. Session scope

Khác biệt giữa SET jit=off và SET LOCAL jit=off là gì?

### Bài 34. Plan estimates

Vì sao statistics sai có thể làm quyết định JIT không phù hợp?

### Bài 35. Query classification

Phân loại point lookup, large aggregation, lock-bound query và I/O-bound scan theo khả năng hưởng lợi JIT.

### Bài 36. Metrics

Nêu các chỉ số cần theo dõi khi tuning JIT.

### Bài 37. Container

CPU throttling có thể ảnh hưởng kết quả JIT benchmark thế nào?

### Bài 38. Regression

Query đơn nhanh hơn nhưng throughput toàn cluster giảm, nên điều tra gì?

### Bài 39. Troubleshooting

Kể các bước đầu tiên khi query không có JIT section dù jit=on.

### Bài 40. Thiết kế

Đề xuất chính sách JIT cho database có OLTP và reporting workload chạy chung.

## 34. Lời giải tham khảo

### Bài 1–8. Cơ chế và availability

JIT biên dịch một số expressions thành native code tại runtime. LLVM cung cấp IR optimizer và code generation. JIT không biên dịch toàn bộ SQL thành executable độc lập; PostgreSQL vẫn chạy execution plan. Expressions có thể gồm arithmetic, comparisons, Boolean predicates và projection/CASE. Tuple deforming giải mã column values từ tuple representation. Các timings chính gồm generation, inlining, optimization và emission. Kiểm tra availability bằng:

~~~sql
SELECT pg_jit_available();
~~~

jit=on chưa đủ nếu PostgreSQL build thiếu LLVM support hoặc provider không load được.

### Bài 9–13. Threshold và cấu hình

jit_above_cost dùng planner cost units, không phải milliseconds. jit_above_cost điều khiển bắt đầu JIT; jit_inline_above_cost điều khiển inlining; jit_optimize_above_cost điều khiển optimization sâu. Tắt JIT bằng SET jit=off hoặc SET LOCAL jit=off trong transaction.

### Bài 14–20. Query classes

Point lookup thường xử lý ít rows nên compilation overhead lớn hơn phần CPU tiết kiệm. Analytical scan/aggregation lớn có thể xử lý nhiều expressions trên nhiều rows và amortize compilation. I/O-bound query chủ yếu chờ storage nên JIT ít giúp. JIT có thể compile expressions xung quanh join nhưng không thay thế hash join algorithm hoặc toàn bộ sort. JIT không compile toàn bộ PL/pgSQL body thành native code. Prepared plan cache không bảo đảm native JIT code được tái sử dụng qua mọi execution.

### Bài 21–25. Đo lường

~~~sql
EXPLAIN (ANALYZE, BUFFERS, SETTINGS)
SELECT sum(amount) FROM app.sales;
~~~

JIT section có thể hiển thị functions, options và generation/inlining/optimization/emission timings. pg_stat_statements có thể có jit_functions, jit_generation_time, jit_inlining_time và jit_optimization_time. Chia compilation time cho calls giúp ước lượng chi phí trung bình mỗi lần thực thi. Stats reset làm counters thay đổi baseline, vì vậy cần ghi nhận thời điểm reset.

### Bài 26–30. Benchmark và tuning

Threshold quá thấp có thể compile nhiều query ngắn, làm tăng CPU/latency. Inlining time lớn thì thử tăng jit_inline_above_cost hoặc tắt inlining; optimization time lớn thì thử tăng jit_optimize_above_cost. Giữ data, parameter values, plan, cache condition, concurrency và resource limits ổn định. Concurrent benchmark phát hiện compilation contention và tail latency mà test đơn lẻ không thể hiện.

### Bài 31–35. Policy và plan quality

~~~sql
ALTER ROLE app_runtime SET jit = off;
ALTER ROLE reporting SET jit = on;
~~~

SET áp dụng cho session hiện tại; SET LOCAL chỉ có hiệu lực tới hết transaction. Statistics sai làm planner cost/row estimates sai và có thể kích hoạt hoặc bỏ qua JIT không phù hợp. Point lookup và lock-bound query thường ít hưởng lợi; large CPU-heavy aggregation có thể hưởng lợi; I/O-bound scan thường bị giới hạn bởi storage.

### Bài 36–40. Monitoring và thiết kế

Theo dõi JIT generation/inlining/optimization/emission time, calls, total/mean execution time, CPU, memory, throughput, p95/p99 và query plan. CPU throttling làm compile time tăng và benchmark biến động. Nếu query đơn nhanh hơn nhưng throughput giảm, kiểm tra CPU saturation, concurrent compile, worker count và connection pool.

Khi không có JIT section dù jit=on, kiểm tra pg_jit_available(), provider, plan cost so với threshold, setting thực trong session và query expression eligibility.

Với workload hỗn hợp, có thể tắt JIT cho app_runtime latency-sensitive và bật cho reporting role, sau đó điều chỉnh thresholds theo benchmark. Duy trì dashboard/alert cho compilation overhead và rollback policy nếu tail latency hoặc throughput xấu đi.

## 35. Bảng tra cứu nhanh

| Nhu cầu | Công cụ / tham số |
| --- | --- |
| Kiểm tra JIT availability | pg_jit_available() |
| Bật/tắt JIT | jit |
| Xem provider | jit_provider |
| Ngưỡng bắt đầu JIT | jit_above_cost |
| Ngưỡng inlining | jit_inline_above_cost |
| Ngưỡng optimization sâu | jit_optimize_above_cost |
| Compile expressions | jit_expressions |
| Compile tuple deforming | jit_tuple_deforming |
| Đo plan và execution | EXPLAIN (ANALYZE, BUFFERS, SETTINGS) |
| Query-level JIT stats | pg_stat_statements |
| Compile generation time | jit_generation_time |
| Inlining time | jit_inlining_time |
| Optimization time | jit_optimization_time |
| Emission time | jit_emission_time |
| Tắt trong session | SET jit = off |
| Tắt trong transaction | SET LOCAL jit = off |
| Policy theo role | ALTER ROLE ... SET |
| Policy theo database | ALTER DATABASE ... SET |
| Kiểm tra settings thực | SHOW / current_setting() |
| Kiểm tra plan cache execution | EXPLAIN EXECUTE |
| Kiểm tra PostgreSQL build | pg_config --configure |
| Xem query workload | pg_stat_statements |

## 36. Checklist tuning JIT

1. Xác nhận PostgreSQL version và LLVM/JIT build support.
2. Kiểm tra pg_jit_available() trên instance thực tế.
3. Ghi lại jit, jit_provider và các threshold hiện tại.
4. Phân loại query thành OLTP, reporting, ETL và background workload.
5. Chọn các query đại diện cho từng class.
6. Đọc EXPLAIN plan cost và estimated/actual rows.
7. Xác định query CPU-bound hay I/O/lock/network-bound.
8. Đo JIT generation, inlining, optimization và emission time.
9. Đo total execution time, CPU và buffers.
10. Benchmark JIT on/off với cùng data và parameters.
11. Lặp lại đủ lần và so median, p95/p99.
12. Benchmark dưới concurrency gần production.
13. Kiểm tra throughput toàn hệ thống và CPU saturation.
14. Tăng jit_above_cost nếu query ngắn bị compile quá nhiều.
15. Điều chỉnh jit_inline_above_cost nếu inlining overhead cao.
16. Điều chỉnh jit_optimize_above_cost nếu optimization overhead cao.
17. Benchmark jit_expressions và jit_tuple_deforming riêng khi cần.
18. Dùng role/session policy để tách workload classes.
19. Kiểm tra connection pool có giữ session settings cũ không.
20. Theo dõi pg_stat_statements JIT fields nếu version hỗ trợ.
21. Ghi nhận statistics reset và exporter metric gaps.
22. Không thay đổi planner cost parameters chỉ để ép JIT.
23. Không coi JIT là giải pháp cho bad plan hoặc thiếu index.
24. Kiểm tra container CPU quota và host memory pressure.
25. Ghi lại baseline, setting mới và rollback procedure.
26. Theo dõi sau rollout và điều chỉnh theo workload thực tế.

## 37. Tổng kết

JIT trong PostgreSQL dùng LLVM để biên dịch một số phần expression evaluation và tuple deformation thành native code tại runtime. Điều này có thể giảm CPU cho query xử lý nhiều tuples và thực hiện nhiều phép tính, nhưng tạo thêm chi phí generation, inlining, optimization và code emission.

Các ngưỡng jit_above_cost, jit_inline_above_cost và jit_optimize_above_cost dựa trên planner cost units, không phải milliseconds hay query timeout. Vì vậy, một query có cost cao chưa chắc chạy lâu, và một query có CPU cost thực tế cao chưa chắc được planner ước lượng đúng. Statistics, plan quality và query shape đều ảnh hưởng quyết định JIT.

OLTP point lookup và short transactions thường ít hưởng lợi vì compilation overhead dễ chiếm tỷ trọng lớn. Large scans, joins và aggregations CPU-bound có thể hưởng lợi khi expression work lặp lại trên nhiều rows. Query bị giới hạn bởi disk, lock, network, sort spill hoặc function implementation không được JIT compile có thể không cải thiện đáng kể.

Hãy dùng pg_jit_available(), EXPLAIN (ANALYZE, BUFFERS, SETTINGS) và pg_stat_statements để đo cả compilation time lẫn execution time. Benchmark JIT on/off trên dữ liệu và concurrency đại diện; so median, tail latency, throughput và CPU. Với workload hỗn hợp, cấu hình theo role/session có thể giữ latency cho OLTP và cho reporting cơ hội tận dụng JIT. Chỉ áp dụng thay đổi rộng sau khi có số liệu, monitoring và phương án rollback rõ ràng.
