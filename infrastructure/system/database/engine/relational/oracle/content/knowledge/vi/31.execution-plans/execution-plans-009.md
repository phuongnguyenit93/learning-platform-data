# Thu thập thống kê thực thi bằng GATHER_PLAN_STATISTICS trong phiên thử nghiệm

Khi tối ưu một câu SQL trong Oracle Database, execution plan cho biết Oracle dự định truy cập bảng, dùng index, join và tổng hợp dữ liệu như thế nào. Tuy nhiên, một kế hoạch chỉ có ước lượng của optimizer chưa đủ để kết luận câu SQL chạy thực tế ra sao. Để so sánh ước lượng với số liệu thực thi, có thể yêu cầu Oracle thu thập row-source statistics bằng hint **GATHER_PLAN_STATISTICS**, sau đó xem kết quả qua **DBMS_XPLAN.DISPLAY_CURSOR** với định dạng **ALLSTATS LAST**.

Phương pháp này phù hợp với phiên thử nghiệm vì có thể bật thống kê cho đúng câu SQL đang khảo sát, thực thi câu lệnh bằng dữ liệu đại diện, rồi xem số hàng thực tế, số lần bắt đầu mỗi operation, logical reads, physical reads, thời gian và bộ nhớ của các bước trong execution plan.

## 1. Phân biệt ba loại thông tin

Trước khi thu thập số liệu, cần phân biệt:

| Loại thông tin | Nguồn thường dùng | Ý nghĩa |
|---|---|---|
| Optimizer statistics | DBMS_STATS và dictionary statistics | Mô tả bảng, cột, index, số hàng, độ phân tán dữ liệu để optimizer ước lượng chi phí |
| Estimated execution plan | EXPLAIN PLAN hoặc phần estimated trong DBMS_XPLAN | Kế hoạch Oracle dự định dùng và số hàng ước lượng |
| Runtime row-source statistics | GATHER_PLAN_STATISTICS hoặc STATISTICS_LEVEL=ALL, xem bằng DISPLAY_CURSOR | Số hàng và tài nguyên thực tế của các operation đã chạy |

GATHER_PLAN_STATISTICS thu thập số liệu của lần thực thi câu SQL. Nó **không** thay thế việc thu thập optimizer statistics bằng DBMS_STATS.GATHER_TABLE_STATS. Hai việc giải quyết hai câu hỏi khác nhau:

- DBMS_STATS: optimizer có đủ thông tin về dữ liệu để ước lượng tốt không?
- GATHER_PLAN_STATISTICS: khi câu SQL thực sự chạy, từng operation tạo ra bao nhiêu hàng và tiêu thụ tài nguyên thế nào?

Ví dụ, nếu E-Rows ước lượng 10 hàng nhưng A-Rows thực tế là 100.000 hàng, vấn đề có thể nằm ở cardinality estimate, histogram, tương quan giữa các cột hoặc điều kiện lọc. Runtime statistics giúp xác định operation bắt đầu sai lệch.

## 2. GATHER_PLAN_STATISTICS là gì?

GATHER_PLAN_STATISTICS là optimizer hint đặt trong câu SQL. Khi hint được áp dụng, Oracle thu thập runtime statistics cho các row source của câu lệnh đó để có thể xem sau khi thực thi.

Cú pháp đặt hint:

~~~sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       ...
  FROM ...
 WHERE ...;
~~~

Hint thường được đặt ngay sau từ khóa SELECT. Với câu UPDATE, DELETE hoặc INSERT ... SELECT, có thể đặt hint trong phần câu lệnh tương ứng nếu muốn khảo sát runtime statistics của DML.

Ví dụ:

~~~sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       e.department_id,
       COUNT(*) AS employee_count,
       AVG(e.salary) AS average_salary
  FROM employees e
 WHERE e.salary >= 5000
 GROUP BY e.department_id;
~~~

Sau khi chạy câu lệnh, dùng DBMS_XPLAN để xem kế hoạch cùng thống kê thực tế. Hint có phạm vi ở câu SQL được gắn; vì vậy nó phù hợp khi chỉ muốn đo một truy vấn trong phiên thử nghiệm mà không thay đổi cấu hình thu thập thống kê cho toàn bộ session.

Việc thu thập thống kê có chi phí phụ. Kết quả đo được có thể chậm hơn một chút so với lần chạy không bật thống kê. Hãy dùng số liệu để hiểu execution plan, rồi đo lại thời gian thực tế với cấu hình vận hành dự kiến.

## 3. Quy trình cơ bản trong một phiên thử nghiệm

Một quy trình đơn giản gồm bốn bước:

1. Mở một session thử nghiệm có quyền xem cursor và execution plan.
2. Thêm hint GATHER_PLAN_STATISTICS vào câu SQL cần khảo sát.
3. Thực thi hết câu lệnh và bảo đảm client fetch hết kết quả nếu muốn số liệu đại diện cho toàn bộ truy vấn.
4. Gọi DBMS_XPLAN.DISPLAY_CURSOR với ALLSTATS LAST để xem thống kê của lần thực thi gần nhất.

Ví dụ đầy đủ:

~~~sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       e.department_id,
       COUNT(*) AS employee_count,
       AVG(e.salary) AS average_salary
  FROM employees e
 WHERE e.salary >= 5000
 GROUP BY e.department_id;

SELECT *
  FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
      NULL,
      NULL,
      'ALLSTATS LAST'
    )
  );
~~~

Trong SQL*Plus hoặc SQLcl, có thể tăng độ rộng hiển thị để tránh dòng execution plan bị xuống hàng:

~~~sql
SET LINESIZE 220
SET PAGESIZE 1000
~~~

DISPLAY_CURSOR(NULL, NULL, ...) yêu cầu hiển thị cursor của câu lệnh gần nhất trong session theo cơ chế của DBMS_XPLAN. Cách này thuận tiện khi vừa chạy xong truy vấn thử nghiệm. Nếu session đã chạy nhiều câu lệnh, hoặc cần chọn đúng child cursor, hãy lấy SQL_ID và child number rồi truyền rõ hai giá trị đó.

## 4. ALLSTATS LAST hiển thị những gì?

ALLSTATS yêu cầu hiển thị cả thống kê I/O và memory của row source khi có sẵn. LAST chọn số liệu của lần thực thi gần nhất của cursor. Tùy phiên bản và operation, các cột thường gặp gồm:

| Cột | Ý nghĩa | Cách đọc |
|---|---|---|
| Id | Số thứ tự operation trong plan | Dùng để liên hệ với cây execution plan |
| Operation | Loại thao tác, ví dụ TABLE ACCESS, INDEX RANGE SCAN, HASH JOIN | Cho biết Oracle đang thực hiện bước nào |
| Name | Tên bảng hoặc index | Đối tượng được truy cập |
| Starts | Số lần operation được khởi chạy | Có ích khi operation nằm bên trong nested loop hoặc được gọi lặp |
| E-Rows | Số hàng optimizer ước lượng | Dùng để so với số hàng thực tế |
| A-Rows | Số hàng thực tế do operation tạo ra | Cho biết cardinality trong lần chạy |
| A-Time | Thời gian thực thi được ghi nhận cho operation | Xem để tìm vùng tốn thời gian; không cộng cơ học các dòng |
| Buffers | Logical reads, số buffer được truy cập | Thước đo quan trọng về công việc đọc trong buffer cache |
| Reads | Physical reads được ghi nhận | Cho biết có đọc vật lý từ storage hay không |
| Writes | Physical writes nếu operation có ghi | Có thể xuất hiện ở operation dùng temporary segment |
| OMem, 1Mem, Used-Mem | Thông tin bộ nhớ workarea | Giúp hiểu sort/hash có đủ bộ nhớ hay phải xử lý nhiều lượt |
| TempSpc | Không gian temporary ước lượng hoặc được hiển thị tùy định dạng | Gợi ý operation có thể dùng TEMP |

Không phải mọi operation đều có đủ các cột. Ví dụ, operation không dùng workarea có thể không có thông tin OMem/1Mem/Used-Mem.

Để hiển thị thêm predicate và alias, có thể dùng:

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

+PREDICATE hiển thị access predicate và filter predicate; +ALIAS hiển thị alias đối tượng theo query block. Các phần này giúp liên hệ operation trong plan với điều kiện SQL cụ thể.

## 5. Đọc E-Rows, A-Rows và Starts

Ba cột quan trọng nhất khi tìm sai lệch cardinality là E-Rows, A-Rows và Starts.

- **E-Rows** là số hàng optimizer ước lượng cho operation.
- **A-Rows** là số hàng operation thực sự tạo ra trong lần thực thi.
- **Starts** là số lần operation được bắt đầu.

Ví dụ minh họa:

| Operation | Starts | E-Rows | A-Rows |
|---|---:|---:|---:|
| TABLE ACCESS FULL EMPLOYEES | 1 | 500 | 50.000 |
| INDEX RANGE SCAN ORDERS_CUSTOMER_IX | 100 | 5 | 500 |

Ở dòng EMPLOYEES, thực tế trả 50.000 hàng trong khi optimizer ước lượng 500. Đây là sai lệch lớn, có thể khiến optimizer chọn join method hoặc thứ tự join không phù hợp.

Ở dòng index ORDERS_CUSTOMER_IX, operation chạy 100 lần. E-Rows thường thể hiện ước lượng cho mỗi lần bắt đầu; A-Rows có thể là tổng số hàng qua các lần chạy. Khi Starts lớn hơn 1, hãy xem A-Rows cùng Starts để hiểu số hàng trung bình mỗi lần và tránh so sánh trực tiếp mà bỏ qua số lần lặp.

Một sai lệch lớn ở operation đầu tiên có thể lan sang các operation phía trên. Ví dụ:

1. Oracle đánh giá thấp số hàng sau filter.
2. Optimizer chọn nested loop vì cho rằng tập dữ liệu bên ngoài nhỏ.
3. Nested loop thực tế chạy hàng trăm nghìn lần.
4. Index lookup lặp lại tạo nhiều logical reads và thời gian cao.

Khi đọc plan, hãy tìm operation đầu tiên có sai lệch đáng kể giữa E-Rows và A-Rows. Sau đó kiểm tra predicate, dữ liệu phân bố, thống kê cột, histogram và cách các điều kiện có tương quan với nhau.

Không phải cứ A-Rows khác E-Rows là plan sai. Sai lệch nhỏ có thể không ảnh hưởng quyết định; sai lệch lớn chỉ đáng lo khi nó làm thay đổi chi phí hoặc lựa chọn access path/join method.

## 6. Đọc Buffers, Reads và thời gian

Buffers biểu thị số buffer logical được truy cập. Một truy vấn có nhiều logical reads có thể tiêu tốn CPU và latch dù dữ liệu đã nằm trong buffer cache. Vì vậy, truy vấn chạy nhanh ở lần thứ hai không đồng nghĩa nó làm ít công việc hơn.

Reads phản ánh physical reads được ghi nhận. Nếu Buffers cao nhưng Reads thấp, phần lớn dữ liệu có thể được lấy từ buffer cache. Nếu Reads cao, truy vấn phải đọc nhiều block từ storage hoặc cache không đáp ứng được workload.

A-Time là thời gian được ghi nhận cho row source. Các operation trong cây plan có thể lồng nhau, nên thời gian ở các dòng không phải các khoảng độc lập để cộng lại. Với parallel execution, cách phân bổ thời gian còn phức tạp hơn vì nhiều process có thể chạy đồng thời.

Khi phân tích:

- Xem operation nào tạo nhiều hàng hoặc được Starts lặp lại nhiều lần.
- Xem Buffers tập trung ở operation nào.
- Kiểm tra Reads để phân biệt công việc logical với physical I/O.
- Đối chiếu thời gian của các nhánh lớn với thời gian toàn câu SQL.
- Không kết luận chỉ dựa trên một cột; cần xem cả cardinality và access path.

Nếu plan cho thấy một full table scan, điều đó không mặc nhiên là xấu. Full scan có thể tối ưu khi truy vấn cần phần lớn bảng hoặc bảng nhỏ. Ngược lại, index range scan cũng không luôn tốt nếu nó bị lặp hàng trăm nghìn lần.

## 7. Đọc thông tin bộ nhớ và TEMP

Các operation như SORT ORDER BY, HASH JOIN, HASH GROUP BY có thể dùng workarea trong PGA. ALLSTATS có thể hiển thị các cột:

- **OMem:** lượng bộ nhớ ước tính cần để operation chạy ở chế độ optimal.
- **1Mem:** lượng bộ nhớ ước tính cho chế độ one-pass.
- **Used-Mem:** bộ nhớ thực tế đã dùng; một số định dạng có thể kèm số lượt xử lý.
- **TempSpc:** thông tin về không gian temporary liên quan đến operation, nếu có.

Sort hoặc hash operation có thể chạy theo các chế độ:

| Chế độ | Ý nghĩa |
|---|---|
| Optimal | Workarea xử lý hoàn toàn trong bộ nhớ được cấp |
| One-pass | Cần một lượt ghi/đọc dữ liệu qua TEMP để hoàn tất |
| Multi-pass | Cần nhiều lượt xử lý qua TEMP; thường có thể làm tăng I/O đáng kể |

Nếu một HASH JOIN hoặc SORT dùng TEMP nhiều, hãy xem số hàng thực tế, kích thước hàng, PGA workarea policy và các operation trước đó. Tăng bộ nhớ không phải lúc nào cũng là giải pháp đầu tiên; có thể truy vấn đang tạo quá nhiều hàng do join sai hoặc filter được áp dụng muộn.

Thông tin memory có thể khác nhau theo phiên bản Oracle, loại operation và cấu hình. Hãy đọc đúng các cột xuất hiện trong output thực tế.

## 8. Xem đúng SQL_ID và child cursor

Trong phiên thử nghiệm, cách gọi DISPLAY_CURSOR với NULL thuận tiện. Khi cần lưu kết quả hoặc so sánh nhiều câu SQL, nên lấy SQL_ID và child number của câu lệnh đã chạy.

Đặt một comment nhận diện riêng trong câu SQL:

~~~sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       /* row420_trial_department_salary */
       e.department_id,
       COUNT(*) AS employee_count
  FROM employees e
 WHERE e.salary >= 5000
 GROUP BY e.department_id;
~~~

Sau đó tìm cursor tương ứng:

~~~sql
SELECT sql_id,
       child_number,
       executions,
       last_active_time,
       sql_text
  FROM v$sql
 WHERE sql_text LIKE 'SELECT /*+ GATHER_PLAN_STATISTICS */%'
   AND sql_text LIKE '%row420_trial_department_salary%'
 ORDER BY last_active_time DESC;
~~~

Lấy SQL_ID và CHILD_NUMBER trong kết quả rồi truyền trực tiếp vào DBMS_XPLAN:

~~~sql
SELECT *
  FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
      'sql_id_from_v_sql',
      0,
      'ALLSTATS LAST +PREDICATE +ALIAS'
    )
  );
~~~

Thay chuỗi sql_id_from_v_sql bằng SQL_ID thực tế và số 0 bằng child number đã tìm được. Một SQL_ID có thể có nhiều child cursor do bind metadata, optimizer environment, object metadata hoặc các nguyên nhân khác. Chọn nhầm child có thể xem một plan khác với lần chạy cần khảo sát.

Các view như V$SQL và V$SQL_PLAN_STATISTICS_ALL yêu cầu quyền truy cập phù hợp. Nếu tài khoản thử nghiệm không có quyền, hãy nhờ DBA cấp quyền đọc cần thiết hoặc cung cấp output DBMS_XPLAN từ một session có quyền.

## 9. ALLSTATS LAST và nhiều lần thực thi

Từ khóa LAST có ý nghĩa quan trọng: DBMS_XPLAN hiển thị runtime statistics của lần thực thi gần nhất được ghi nhận cho cursor đó. Nếu cùng một SQL cursor được nhiều session chạy, lần thực thi gần nhất có thể không phải lần chạy của session hiện tại.

Để kết quả dễ diễn giải:

1. Dùng một session thử nghiệm riêng.
2. Gắn comment nhận diện riêng cho câu SQL.
3. Chạy truy vấn rồi xem DBMS_XPLAN ngay sau đó.
4. Nếu có nhiều child cursor, chọn đúng child number.
5. Không để một session khác chạy cùng cursor trong lúc đang thu thập số liệu so sánh.

Nếu muốn so sánh nhiều giá trị bind, hãy thực hiện từng lần có ghi nhận rõ giá trị đầu vào và thời điểm chạy. Bind peeking, adaptive cursor sharing hoặc các child cursor khác nhau có thể dẫn đến plan khác nhau.

Kết quả ALLSTATS LAST là số liệu của một lần thực thi, không phải số trung bình của tất cả các lần chạy. Để đánh giá ổn định, cần lặp lại với dữ liệu và tham số đại diện, đồng thời ghi lại điều kiện thử nghiệm.

## 10. Cách khác: STATISTICS_LEVEL=ALL trong session

Ngoài hint cho từng câu SQL, có thể bật thu thập runtime plan statistics cho session bằng:

~~~sql
ALTER SESSION SET statistics_level = ALL;
~~~

Khi đó Oracle thu thập thêm thống kê cho các câu SQL chạy trong session. Cách này hữu ích khi cần khảo sát nhiều câu lệnh mà không muốn thêm hint vào từng câu.

Tuy nhiên, STATISTICS_LEVEL=ALL có phạm vi rộng hơn và có thể tạo thêm overhead cho mọi câu SQL trong session. Trong phiên thử nghiệm, cần lưu giá trị ban đầu rồi khôi phục đúng giá trị đó sau khi khảo sát. Có thể đọc giá trị hiện tại:

~~~sql
SELECT value
  FROM v$parameter
 WHERE name = 'statistics_level';
~~~

Sau khi ghi lại giá trị ban đầu, mới thay đổi session:

~~~sql
ALTER SESSION SET statistics_level = ALL;
~~~

Khi kết thúc, khôi phục đúng giá trị đã ghi nhận. Ví dụ nếu ban đầu là TYPICAL:

~~~sql
ALTER SESSION SET statistics_level = TYPICAL;
~~~

Không mặc định khôi phục về TYPICAL nếu session ban đầu được cấu hình khác. Thay đổi bằng ALTER SESSION chỉ áp dụng cho session hiện tại; không dùng ALTER SYSTEM chỉ để thử một truy vấn.

Với một câu SQL cụ thể, hint GATHER_PLAN_STATISTICS thường là lựa chọn gọn hơn vì phạm vi thu thập rõ ràng.

## 11. Vì sao DISPLAY_CURSOR không hiện A-Rows?

Một số tình huống phổ biến:

**Câu SQL chưa thu thập runtime statistics:** nếu không có hint GATHER_PLAN_STATISTICS và session không bật STATISTICS_LEVEL=ALL, output có thể chỉ có E-Rows mà không có A-Rows.

**Dùng EXPLAIN PLAN thay cho cursor đã chạy:** EXPLAIN PLAN chỉ tạo kế hoạch ước lượng. Nó không thực thi câu SQL nên không có A-Rows của lần chạy.

**Chọn nhầm cursor hoặc child cursor:** SQL_ID hoặc child number không trỏ đến lần thực thi cần xem.

**Cursor đã bị aged out hoặc invalidated:** cursor không còn trong shared pool hoặc plan đã bị thay đổi, nên DISPLAY_CURSOR không lấy được thông tin mong muốn.

**Client chưa fetch hết kết quả:** một số công cụ chỉ lấy một phần kết quả hiển thị. Runtime statistics có thể phản ánh phần đã thực sự tiêu thụ, không phải toàn bộ tập kết quả.

**Quyền truy cập chưa đủ:** tài khoản không đọc được các fixed view cần thiết hoặc không có quyền thực thi DBMS_XPLAN.

Khi không thấy thống kê, hãy xác nhận hint nằm đúng vị trí, câu lệnh đã thực sự chạy, kết quả đã được fetch hết, và đang xem đúng SQL_ID/child cursor.

## 12. Thu thập số liệu cho SELECT và DML

Với SELECT, có thể chạy truy vấn trong session thử nghiệm và fetch hết kết quả. Với INSERT, UPDATE hoặc DELETE, cần chú ý dữ liệu bị thay đổi:

- Thử trên schema hoặc dữ liệu kiểm thử có thể khôi phục.
- Kiểm tra chế độ auto-commit của client.
- Nếu dùng rollback để hoàn nguyên, bảo đảm câu lệnh và ứng dụng không tự commit.
- Với DML có trigger, cascade hoặc tác động phụ, cần hiểu đầy đủ phạm vi thay đổi trước khi thực thi.

Ví dụ minh họa UPDATE trong phiên thử nghiệm:

~~~sql
UPDATE /*+ GATHER_PLAN_STATISTICS */
       employees
   SET salary = salary * 1.02
 WHERE department_id = 50;

SELECT *
  FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
      NULL,
      NULL,
      'ALLSTATS LAST'
    )
  );

ROLLBACK;
~~~

Đoạn trên chỉ là mẫu thử. Không chạy UPDATE trên dữ liệu thật nếu chưa xác nhận phạm vi và khả năng rollback. Một số client có auto-commit, khi đó ROLLBACK sau câu lệnh có thể không còn tác dụng.

## 13. Từ số liệu thực thi đến hướng điều tra

Runtime statistics cho biết nơi cần điều tra tiếp theo, không tự đưa ra một bản sửa tối ưu. Có thể dùng các dấu hiệu sau để định hướng:

| Dấu hiệu trong plan | Hướng điều tra |
|---|---|
| A-Rows lớn hơn E-Rows nhiều lần | Thống kê bảng/cột, histogram, skew, điều kiện lọc và tương quan cột |
| Starts rất lớn ở index lookup | Nested loop lặp quá nhiều; kiểm tra cardinality phía ngoài và join method |
| Buffers cao ở TABLE ACCESS FULL | Phạm vi dữ liệu cần đọc, predicate, partition pruning, index phù hợp và kích thước bảng |
| Reads cao | I/O vật lý, cache, scan lớn, storage latency và số block đọc |
| HASH JOIN hoặc SORT dùng nhiều TEMP | Cardinality, kích thước hàng, PGA workarea và khả năng giảm dữ liệu trước operation |
| Filter predicate loại bỏ rất ít hàng sau khi đã đọc nhiều dữ liệu | Xem xét access path, vị trí áp dụng điều kiện và chỉ mục |
| A-Rows bằng 0 ở operation sớm | Kiểm tra bind value, điều kiện lọc và dữ liệu thử nghiệm |

Một cách làm có hệ thống:

1. Tìm operation đầu tiên có chênh lệch E-Rows/A-Rows đáng kể.
2. Đọc Predicate Information để xác định điều kiện access và filter.
3. Kiểm tra thống kê đối tượng và phân bố dữ liệu liên quan.
4. Xem operation phía trên có bị ảnh hưởng bởi cardinality sai hay không.
5. Đề xuất một thay đổi có giả thuyết rõ ràng.
6. Chạy lại cùng SQL, cùng dữ liệu và cùng bind để so sánh.

Không nên thay đổi index, hint hoặc optimizer parameter chỉ vì một operation trông có vẻ không quen thuộc. Mỗi thay đổi cần được kiểm chứng bằng số liệu trước và sau.

## 14. Phân biệt runtime statistics với SQL Monitor

GATHER_PLAN_STATISTICS và DBMS_XPLAN.DISPLAY_CURSOR phù hợp để xem row-source statistics của cursor. Với truy vấn dài hoặc parallel execution phức tạp, SQL Monitor có thể cung cấp góc nhìn chi tiết hơn về tiến trình thực thi, thời gian, I/O và hoạt động của các process.

SQL Monitor có điều kiện sử dụng, yêu cầu quyền và có thể phụ thuộc gói quản trị được cấp phép. Không nên giả định mọi môi trường đều có quyền hoặc giấy phép phù hợp. Với mục tiêu học cách so sánh E-Rows/A-Rows và đọc từng operation, GATHER_PLAN_STATISTICS thường là điểm bắt đầu đơn giản.

## 15. Lưu kết quả để so sánh

Khi khảo sát một truy vấn, nên lưu lại các thông tin đi kèm output:

- SQL text và SQL_ID.
- Child number.
- Giá trị bind hoặc bộ tham số thử nghiệm.
- Phiên bản Oracle và optimizer environment có liên quan.
- Thời điểm chạy và số lần thực thi.
- Execution plan cùng ALLSTATS LAST.
- Thời gian tổng, số hàng trả về và trạng thái fetch.
- Thay đổi đã thực hiện giữa các lần đo.

Không chỉ lưu ảnh chụp plan. Nên lưu output dạng text để có thể so sánh các operation, E-Rows, A-Rows, Starts và Buffers giữa các lần thử. Nếu SQL chứa thông tin nhạy cảm hoặc literal nghiệp vụ, hãy xử lý theo chính sách dữ liệu của môi trường trước khi chia sẻ output.

## 16. Ví dụ quy trình thử nghiệm hoàn chỉnh

Giả sử truy vấn tổng hợp lương theo phòng ban đang chạy chậm. Thực hiện trong một session thử nghiệm:

**Bước 1: Chạy truy vấn có hint**

~~~sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       /* row420_salary_by_department */
       department_id,
       COUNT(*) AS employee_count,
       AVG(salary) AS average_salary
  FROM employees
 WHERE salary >= 5000
 GROUP BY department_id;
~~~

**Bước 2: Xem plan và runtime statistics**

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

**Bước 3: Ghi nhận điểm đáng chú ý**

Giả sử plan cho thấy TABLE ACCESS FULL EMPLOYEES ước lượng 500 hàng nhưng thực tế đọc 50.000 hàng. Hãy kiểm tra số liệu thống kê của SALARY, histogram nếu phân bố lệch, số hàng thực tế và điều kiện lọc.

**Bước 4: Đưa ra một giả thuyết**

Ví dụ: optimizer đánh giá thấp số hàng có salary >= 5000 do thống kê không phản ánh phân bố hiện tại. Đây là giả thuyết cần kiểm chứng, không phải kết luận chỉ từ một dòng plan.

**Bước 5: Thử thay đổi trong môi trường kiểm thử**

Nếu cần cập nhật optimizer statistics, hãy làm theo quy trình quản trị thống kê phù hợp và ghi lại trạng thái trước khi thay đổi. Không tự ý gather statistics trên hệ thống production chỉ để thử một câu truy vấn.

**Bước 6: Chạy lại cùng truy vấn và so sánh**

Dùng cùng bộ dữ liệu, bind, session setting và cách fetch. So sánh plan, E-Rows, A-Rows, Starts, Buffers, Reads, A-Time và kết quả trả về. Một thay đổi tốt phải cải thiện workload mục tiêu mà vẫn giữ kết quả đúng và không làm các truy vấn khác suy giảm ngoài dự kiến.

## 17. Những lưu ý quan trọng trong phiên thử nghiệm

- Chỉ thu thập thống kê trên câu SQL cần khảo sát để hạn chế overhead.
- Chạy trên dữ liệu đại diện; một bảng thử quá nhỏ có thể dẫn đến plan khác xa production.
- Fetch hết kết quả nếu muốn thống kê của toàn truy vấn SELECT.
- Dùng SQL_ID và child number rõ ràng khi có nhiều cursor.
- ALLSTATS LAST là lần thực thi cuối của cursor, không phải trung bình nhiều lần.
- A-Rows và E-Rows cần được đọc cùng Starts, đặc biệt với nested loop.
- Không cộng A-Time của các operation lồng nhau để suy ra thời gian tổng.
- Runtime statistics không thay thế optimizer statistics.
- Không dùng ALTER SYSTEM để thử một câu SQL trong một session.
- Nếu thử DML, phải kiểm soát auto-commit và tác động phụ trước khi chạy.
- Output plan có thể chứa SQL text, tên schema, tên đối tượng hoặc giá trị bind; hãy bảo vệ thông tin theo chính sách môi trường.

## 18. Kết luận

GATHER_PLAN_STATISTICS cho phép thu thập runtime statistics cho câu SQL được gắn hint. Sau khi thực thi, DBMS_XPLAN.DISPLAY_CURSOR với ALLSTATS LAST hiển thị execution plan kèm số hàng thực tế, số lần bắt đầu operation, logical/physical I/O và thông tin workarea khi có.

Khi phân tích, hãy bắt đầu bằng chênh lệch giữa E-Rows và A-Rows, đọc cùng Starts, rồi xem Buffers, Reads, A-Time, predicate và thông tin TEMP. Dùng một session thử nghiệm riêng, chạy truy vấn với dữ liệu và bind đại diện, fetch hết kết quả và xem đúng cursor. Kết quả là bằng chứng để hình thành giả thuyết tối ưu; hãy thay đổi từng yếu tố và đo lại trong cùng điều kiện để xác nhận hiệu quả.
