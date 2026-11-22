# Giới hạn của cost và tránh kết luận chỉ từ một ảnh chụp kế hoạch

Execution plan là bằng chứng quan trọng khi phân tích hiệu năng SQL, nhưng một bản chụp kế hoạch chỉ mô tả một phần của câu chuyện. Nó cho biết Oracle dự định hoặc đã tổ chức các operation như thế nào trong một ngữ cảnh nhất định. Nó không tự chứng minh câu SQL chạy nhanh hay chậm, không cho biết đầy đủ tải hệ thống tại thời điểm chạy, và cũng không đại diện cho mọi lần thực thi với các bind value khác nhau.

Tương tự, cost trong execution plan là một ước lượng nội bộ để optimizer so sánh các phương án. Cost không phải số mili giây, không phải số block đọc thực tế và không phải chỉ số hiệu năng có thể so sánh tùy tiện giữa các hệ thống, thời điểm hoặc câu SQL khác nhau.

Muốn kết luận đáng tin cậy, cần kết hợp kế hoạch với runtime statistics, bind values, cursor identity, thống kê dữ liệu, môi trường phiên và workload. Cần quan sát nhiều lần thực thi đại diện, xác định điều gì thay đổi và đo tác động trước khi chỉnh SQL, index hoặc optimizer settings.

## 1. Cost biểu diễn điều gì?

Cost là giá trị do cost model của Oracle tính ra trong giai đoạn tối ưu hóa. Optimizer dùng cost để so sánh các kế hoạch khả thi theo mục tiêu tối ưu hiện tại. Mô hình có thể xét số block cần đọc, loại I/O, CPU, cardinality, độ rộng dòng, khả năng dùng bộ nhớ, parallel execution và system statistics.

Cost có các đặc điểm quan trọng:

- Là ước lượng, không phải kết quả đo sau khi chạy.
- Phụ thuộc vào thống kê, tham số optimizer và môi trường được dùng khi parse.
- Có ý nghĩa chủ yếu trong việc so sánh các phương án của cùng một bài toán tối ưu hóa.
- Có thể thay đổi khi thống kê, phiên bản, tham số, bind hoặc metadata thay đổi.
- Không trực tiếp biểu diễn elapsed time, CPU seconds, logical reads hay physical reads.

Ví dụ, cost 500 không có nghĩa câu SQL chạy 500 ms. Một câu SQL cost 500 trên môi trường A cũng không mặc nhiên chậm hơn câu SQL cost 200 trên môi trường B. Hai hệ thống có CPU, storage, cache, system statistics, parallel policy và workload khác nhau.

### 1.1 Vì sao cost thấp chưa chắc thời gian thực thi thấp?

Cost được tính dựa trên giả định và thông tin có sẵn tại thời điểm tối ưu hóa. Thực thi thật có thể chịu ảnh hưởng của:

- Buffer cache đang nóng hay lạnh.
- Các session khác cùng tranh chấp CPU, I/O, latch, lock hoặc memory.
- Độ trễ storage thay đổi theo thời điểm.
- Số dòng thực tế khác cardinality ước lượng.
- Bind value thực tế khác bind value được dùng khi parse.
- Hash join hoặc sort spill ra TEMP.
- Parallel worker thiếu tài nguyên hoặc phân phối dữ liệu không cân bằng.
- Client fetch chậm hoặc chỉ lấy một phần kết quả.
- Network latency giữa ứng dụng và database.

Một kế hoạch có cost thấp có thể chạy lâu khi bị chờ I/O hoặc lock. Ngược lại, một kế hoạch có cost cao hơn có thể hoàn thành nhanh trong lần chạy cụ thể nhờ dữ liệu nằm sẵn trong cache và hệ thống đang rảnh.

### 1.2 Cost có thể thay đổi mà hiệu năng thực tế không đổi nhiều

Sau khi gather statistics, optimizer có thể ước lượng cardinality hoặc cost khác trước. Kế hoạch có thể vẫn giữ cùng operation và cùng thứ tự join. Nếu thời gian thực tế và số buffer gets gần như không đổi, thay đổi cost đơn thuần không chứng minh có vấn đề.

Ngược lại, một thay đổi nhỏ về cost có thể khiến optimizer chọn access path hoặc join order khác. Khi đó phải đo tác động của kế hoạch mới, thay vì chỉ nhìn mức tăng/giảm cost.

### 1.3 Cost không phải thước đo để xếp hạng mọi SQL

Không nên sắp xếp toàn bộ SQL trong hệ thống theo cost rồi gọi các câu có cost lớn nhất là các câu chậm nhất. Một SQL có thể được chạy một lần mỗi ngày, còn một SQL cost nhỏ có thể chạy hàng chục nghìn lần mỗi phút.

Để xác định SQL gây tải, cần xét cả số lần thực thi, tổng CPU, tổng elapsed time, logical reads, physical reads, wait time, số dòng xử lý và mức độ quan trọng đối với người dùng.

## 2. Một execution plan cho biết điều gì?

Execution plan biểu diễn cây operation mà Oracle dự kiến dùng hoặc đã dùng cho một cursor. Tùy cách lấy plan, thông tin có thể là:

- **Estimated plan:** kế hoạch được tạo khi chạy EXPLAIN PLAN; câu SQL chưa được thực thi bởi thao tác đó.
- **Cursor plan:** kế hoạch gắn với một child cursor trong shared pool.
- **Adaptive plan:** kế hoạch có thể chứa các nhánh lựa chọn mà Oracle quyết định trong lúc thực thi.
- **Runtime plan statistics:** số dòng, số lần bắt đầu operation, buffer gets, reads và thời gian được thu thập trong quá trình thực thi, nếu đã bật cơ chế thu thập phù hợp.

Một bản plan thông thường có thể cho biết:

- Access path của từng bảng/index.
- Join order và join method.
- Predicate được dùng cho access hoặc filter.
- Cardinality ước lượng.
- Cost ước lượng.
- Partition pruning và parallel operations nếu có.
- Một số note về dynamic statistics, adaptive behavior hoặc optimizer environment.

Nó không nhất thiết cho biết đầy đủ:

- Thời gian chờ lock, network hoặc client.
- Bind value của mọi lần thực thi.
- Mức tranh chấp tài nguyên tại thời điểm chạy.
- Số dòng thực tế nếu không thu thập row-source statistics.
- Toàn bộ lịch sử các lần chạy trước.
- Vì sao một cursor khác của cùng SQL text có kế hoạch khác.
- Chi phí của toàn bộ ứng dụng, bao gồm thời gian xử lý ngoài database.

Vì vậy, ảnh chụp plan là một lát cắt của cursor và thời điểm, không phải hồ sơ đầy đủ của SQL trong suốt vòng đời.

## 3. Phân biệt EXPLAIN PLAN với kế hoạch cursor thực tế

EXPLAIN PLAN yêu cầu Oracle tạo một kế hoạch ước lượng và ghi kết quả vào plan table. Nó không thực thi câu SQL được giải thích.

Ví dụ:

~~~sql
EXPLAIN PLAN FOR
SELECT order_id, order_date
FROM orders
WHERE status = 'RETURNED';

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
~~~

Kết quả hữu ích để xem optimizer có thể chọn access path nào trong ngữ cảnh của lệnh EXPLAIN PLAN. Nhưng nó có thể khác kế hoạch của ứng dụng vì:

- Bind datatype và bind value khác.
- Session parameters khác.
- Schema hiện hành, synonym hoặc object resolution khác.
- Optimizer environment khác.
- Cursor ứng dụng đã được parse trước đó với một bind value khác.
- Có nhiều child cursor.
- Statistics hoặc metadata thay đổi giữa hai lần parse.
- Adaptive plan hoặc runtime information chưa được phản ánh.

Khi phân tích SQL đã chạy, nên kiểm tra cursor thực tế bằng DBMS_XPLAN.DISPLAY_CURSOR. Cần xác định đúng SQL_ID và child number khi có nhiều child cursor.

~~~sql
SELECT *
FROM TABLE(
  DBMS_XPLAN.DISPLAY_CURSOR(
    sql_id          => 'SQL_ID_HERE',
    cursor_child_no => 0,
    format          => 'TYPICAL +PREDICATE +ALIAS +NOTE'
  )
);
~~~

Tên SQL_ID và child number trong ví dụ phải được thay bằng giá trị thực tế. Nếu dùng NULL cho SQL_ID và child number, DBMS_XPLAN thường chọn cursor gần nhất của session hiện tại; cách này không phù hợp để điều tra một cursor chạy từ session ứng dụng khác.

### 3.1 SQL_ID không đồng nghĩa với một kế hoạch duy nhất

SQL_ID nhận diện câu SQL đã chuẩn hóa theo cơ chế của Oracle. Cùng SQL_ID có thể có nhiều child cursor. Mỗi child cursor có thể có plan hash value và execution plan riêng.

Các nguyên nhân có thể tạo nhiều child cursor gồm:

- Bind metadata hoặc bind sensitivity khác nhau.
- Optimizer environment khác nhau.
- Object hoặc privilege metadata khác nhau.
- Một số khác biệt về NLS, schema hoặc session settings.
- Cursor sharing incompatibility.
- Adaptive cursor sharing tạo kế hoạch phù hợp với nhóm bind value khác nhau.

Khi một báo cáo chỉ ghi SQL_ID mà không ghi child number, plan hash value và thời điểm quan sát, kết luận về kế hoạch có thể thiếu chính xác.

### 3.2 PLAN_HASH_VALUE cũng có giới hạn

PLAN_HASH_VALUE là giá trị hash giúp nhận diện và so sánh cấu trúc kế hoạch trong nhiều tình huống. Nó hữu ích để phát hiện thay đổi plan, nhưng không phải chữ ký đầy đủ của mọi đặc tính thực thi.

Không nên dùng plan hash như bằng chứng duy nhất rằng hai lần chạy hoàn toàn giống nhau hoặc khác nhau về hiệu năng. Một số chi tiết, runtime conditions, bind values, adaptive choices hoặc môi trường thực thi có thể khác dù plan hash giống nhau. Ngược lại, plan hash khác không tự chứng minh kế hoạch mới tệ hơn.

## 4. Ước lượng cardinality có thể sai

Optimizer phải dự đoán số dòng đi qua từng operation trước khi câu SQL được thực thi. Cardinality sai có thể làm cost và lựa chọn kế hoạch sai theo.

Một số nguyên nhân phổ biến:

- Thống kê bảng/cột cũ hoặc thiếu.
- Dữ liệu phân bố lệch nhưng histogram không phù hợp.
- Điều kiện lọc trên nhiều cột có tương quan.
- Biểu thức hoặc hàm làm mô hình ước lượng khó hơn.
- Bind value có selectivity khác nhau.
- Dữ liệu mới nằm ngoài phạm vi thống kê.
- Join key có phân bố không đồng đều.
- Thống kê partition/global chưa phản ánh dữ liệu.
- Dynamic statistics hoặc feedback không áp dụng cho trường hợp đó.

Ví dụ, bảng ORDERS có 10 triệu dòng. Trạng thái NEW chiếm 70%, còn RETURNED chiếm 0,1%. Nếu optimizer ước lượng cả hai trạng thái như có phân bố đồng đều, access path phù hợp cho từng bind value có thể khác đáng kể so với thực tế.

Một bản EXPLAIN PLAN với literal RETURNED không đại diện cho lần chạy của ứng dụng bind NEW. Ngay cả khi SQL text giống nhau, bind peeking và adaptive cursor sharing có thể dẫn đến child cursor khác nhau.

### 4.1 E-Rows và A-Rows

Khi có runtime row-source statistics, DBMS_XPLAN có thể hiển thị:

- **E-Rows:** số dòng ước lượng.
- **A-Rows:** số dòng thực tế được operation trả về trong lần chạy có statistics.
- **Starts:** số lần operation được bắt đầu.
- **Buffers:** logical reads/buffer gets.
- **Reads:** physical reads được ghi nhận.
- **A-Time:** thời gian thực tế theo số liệu thu thập và format.

Để thu thập số liệu cho lần chạy thử:

~~~sql
SELECT /*+ gather_plan_statistics */
       order_id, order_date
FROM orders
WHERE status = :status;
~~~

Sau khi chạy và fetch kết quả, trong cùng session có thể xem:

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

ALLSTATS LAST chỉ có ý nghĩa khi row-source statistics đã được thu thập cho lần thực thi phù hợp. Hint gather_plan_statistics là một cách kiểm soát cho truy vấn thử nghiệm; có thể dùng cấu hình thống kê khác theo chính sách môi trường.

### 4.2 Đọc sai lệch đúng cách

Nếu E-Rows là 10 nhưng A-Rows là 100.000, operation đã trả nhiều dòng hơn ước lượng. Điều này có thể làm các operation phía trên xử lý nhiều dữ liệu hơn dự kiến.

Tuy nhiên, với inner side của nested loops, operation có thể được bắt đầu nhiều lần. Cần đọc A-Rows cùng Starts và cấu trúc plan, tránh so sánh hai con số mà không hiểu số liệu được tích lũy như thế nào.

Hãy tìm operation đầu tiên có sai lệch đáng kể từ dưới lên. Sai lệch ở một operation thấp có thể lan lên toàn bộ nhánh. Chỉ ép join method ở operation trên cùng có thể che triệu chứng mà không sửa nguyên nhân.

### 4.3 A-Rows cũng chưa kể hết câu chuyện

A-Rows mô tả số dòng đi qua operation trong lần thực thi được đo. Nó không thay thế số liệu về thời gian chờ, network, lock, CPU contention hoặc thời gian client xử lý dữ liệu sau khi fetch.

Một operation có A-Rows thấp vẫn có thể mất nhiều thời gian do I/O chậm hoặc chờ tài nguyên. Một operation có A-Rows lớn có thể chạy nhanh nếu dữ liệu đã có trong cache và phép xử lý đơn giản.

## 5. Một ảnh chụp kế hoạch bị giới hạn bởi thời điểm

Kế hoạch gắn với cursor được tạo ra trong một ngữ cảnh cụ thể. Sau đó môi trường có thể thay đổi:

- Statistics được gather hoặc publish.
- Index được tạo, rebuild, invisible hoặc drop.
- Bảng được partition, exchange partition hoặc thay đổi dữ liệu lớn.
- Optimizer parameters thay đổi.
- Bind value làm phát sinh child cursor mới.
- Cursor bị invalidation và hard parse lại.
- Database được nâng cấp hoặc thay đổi optimizer feature level.
- SQL Profile, SQL Patch hoặc SQL Plan Baseline được áp dụng.
- Session chuyển sang service/module/action khác.
- Adaptive cursor sharing hoặc statistics feedback thay đổi cách tối ưu hóa ở lần sau.

Vì thế, một screenshot lấy hôm qua không chứng minh kế hoạch hiện tại vẫn như vậy. Một screenshot lấy ngay sau khi chạy thử cũng không đại diện cho mọi bind value hoặc mọi thời điểm tải cao.

Khi lưu bằng chứng, hãy ghi thời điểm, database/PDB, SQL_ID, child number, plan hash, instance, module/action, bind group, optimizer environment và cách thu thập runtime statistics.

## 6. Bind variables làm một SQL có nhiều hành vi

Bind variables giúp giảm hard parse và tăng khả năng tái sử dụng cursor. Nhưng selectivity của bind có thể khác nhau rất lớn.

Ví dụ:

~~~sql
SELECT order_id, order_date
FROM orders
WHERE status = :status;
~~~

Nếu NEW chiếm phần lớn bảng, còn RETURNED rất hiếm, một kế hoạch tối ưu cho NEW có thể không tốt cho RETURNED.

### 6.1 Bind peeking

Khi hard parse, optimizer có thể peek bind value hiện tại để ước lượng selectivity. Kế hoạch đầu tiên có thể phản ánh giá trị đã peek. Nếu các lần thực thi sau dùng bind value khác nhiều về selectivity, hiệu năng có thể thay đổi.

### 6.2 Adaptive cursor sharing

Oracle có thể đánh dấu cursor là bind-sensitive hoặc bind-aware và tạo child cursor khác nhau cho các nhóm bind value khi đủ điều kiện. Cơ chế này giúp xử lý một số workload có phân bố lệch.

Không nên giả định Oracle luôn tạo kế hoạch riêng cho mọi bind value hoặc tự sửa mọi trường hợp. Cần xem child cursor, bind capture/peeked binds, plan hash và số liệu runtime của từng nhóm.

### 6.3 Một ảnh chụp chỉ có một nhóm bind

Nếu báo cáo không lưu bind value hoặc nhóm selectivity, rất khó biết kế hoạch đó phù hợp với trường hợp nào. Không cần lưu mọi giá trị bind nhạy cảm vào tài liệu phân tích; có thể phân loại theo nhóm như phổ biến, trung bình, hiếm hoặc theo miền giá trị không nhạy cảm.

Với dữ liệu nhạy cảm, tránh bật trace binds rộng rãi. Nếu cần kiểm tra bind datatype hoặc selectivity, hãy dùng dữ liệu thử nghiệm hoặc biện pháp được phê duyệt để bảo vệ thông tin.

## 7. Thời gian thực thi không chỉ là thời gian operation

Một câu SQL có thể tiêu tốn thời gian ở nhiều nơi:

- CPU xử lý row source.
- I/O đọc block.
- Chờ lock hoặc enqueue.
- Chờ latch, mutex hoặc tài nguyên nội bộ.
- Chờ TEMP do sort/hash spill.
- Chờ PX worker hoặc điều phối parallel.
- Chờ client fetch hoặc network.
- Parse/hard parse và library cache.
- Trigger, PL/SQL, gọi SQL lồng nhau hoặc recursive SQL.

Elapsed time là thời gian trôi qua mà người gọi quan sát được. CPU time là thời gian CPU thực sự được sử dụng. Hai giá trị này có thể khác xa nhau.

Nếu elapsed time lớn hơn CPU time nhiều, cần xem wait events và nguyên nhân chờ. Nếu CPU time chiếm phần lớn elapsed time, cần xem số dòng, phép tính, join, sort, parse và mức sử dụng CPU. Chỉ nhìn operation name không đủ để phân biệt hai tình huống.

### 7.1 Logical reads và physical reads

- **Logical reads/buffer gets:** số lần database truy cập block qua buffer cache.
- **Physical reads:** số block phải đọc từ storage trong phạm vi thống kê được báo cáo.

Một truy vấn có nhiều logical reads có thể gây CPU và buffer contention ngay cả khi physical reads thấp. Một truy vấn có physical reads cao có thể phụ thuộc storage latency và cache state.

Không nên kết luận rằng physical reads bằng 0 nghĩa là truy vấn không tốn I/O hoặc truy vấn tốt. Cũng không nên so sánh hai lần chạy nếu cache state và concurrency khác nhau mà không ghi nhận điều kiện đó.

### 7.2 Một lần chạy có thể chỉ fetch một phần kết quả

Ứng dụng có thể mở cursor nhưng chỉ fetch một vài dòng, hoặc người dùng đóng màn hình trước khi đọc hết kết quả. Khi đó số liệu thực thi có thể phản ánh công việc đã thực hiện đến thời điểm dừng, không nhất thiết là toàn bộ công việc nếu fetch hết.

Khi benchmark, cần mô tả rõ ứng dụng fetch toàn bộ, fetch theo trang hay dừng sớm. Nếu so sánh với SQL*Plus hoặc công cụ khác, cần bảo đảm fetch behavior tương đương.

## 8. Adaptive plan và runtime choice

Một số kế hoạch có các nhánh adaptive. Optimizer có thể ghi vào plan các lựa chọn thay thế, rồi quyết định nhánh phù hợp trong khi thực thi khi có đủ thông tin runtime.

Do đó, chỉ đọc plan ở giai đoạn parse có thể không cho biết nhánh cuối cùng được dùng. DBMS_XPLAN có thể hiển thị thông tin adaptive và các operation inactive/active tùy format và phiên bản.

Khi kiểm tra adaptive plan:

1. Lấy plan của đúng child cursor.
2. Xem note về adaptive plan.
3. Dùng format hỗ trợ thông tin adaptive nếu phiên bản cho phép.
4. Thu thập runtime row-source statistics.
5. So sánh các lần thực thi với bind và dữ liệu đại diện.

Không nên xem mọi operation được in ra trong plan adaptive là operation đều đã thực thi. Cần xem trạng thái và runtime statistics.

## 9. Cache và trạng thái hệ thống làm thay đổi kết quả

Hai lần chạy cùng một plan có thể có thời gian khác nhau vì trạng thái hệ thống khác nhau.

Ví dụ:

- Lần đầu đọc block từ storage; lần sau block đã ở buffer cache.
- Lần đầu phải hard parse; lần sau dùng cursor.
- Lần đầu chạy khi hệ thống rảnh; lần sau cạnh tranh CPU với batch job.
- Storage có latency khác nhau do workload khác.
- TEMP hoặc PGA chịu áp lực khác nhau.
- Parallel server process có mức sẵn sàng khác nhau.
- Kết quả được ứng dụng cache hoặc client fetch khác nhau.

Đây là lý do một lần chạy nhanh hoặc chậm không đủ để kết luận một kế hoạch tốt hay xấu. Cần đo nhiều lần, dùng workload đại diện, ghi nhận trạng thái cache và concurrency, đồng thời tránh làm nóng cache có chủ đích nếu mục tiêu là đo cold-start.

Không có một quy trình benchmark phù hợp cho mọi hệ thống. Hãy xác định trước câu hỏi: đo latency người dùng, throughput, CPU tổng, I/O, hay hành vi ở lần chạy đầu.

## 10. Cách thu thập bằng chứng đáng tin cậy

Một báo cáo phân tích plan nên có tối thiểu:

| Nhóm | Thông tin cần lưu |
|---|---|
| Nhận diện SQL | SQL_ID, SQL text hoặc bản đã ẩn dữ liệu nhạy cảm |
| Cursor | Child number, plan hash, parsing schema |
| Thời điểm | Timestamp, database, PDB, instance |
| Ứng dụng | Service, module, action, client identifier |
| Bind | Datatype và nhóm selectivity; chỉ lưu giá trị thật khi được phép |
| Optimizer | Optimizer mode, relevant parameters, plan note |
| Statistics | Table/column/index/partition statistics, last analyzed |
| Plan | DBMS_XPLAN output và predicate information |
| Runtime | E-Rows, A-Rows, Starts, buffers, reads, CPU, elapsed |
| Waits | Wait class/event, tổng thời gian chờ và số lần chờ |
| Workload | Số lần chạy, concurrency, fetch pattern, dữ liệu đại diện |

Không phải lúc nào cũng cần thu thập mọi trường cho mọi SQL. Với sự cố cụ thể, bắt đầu từ SQL_ID, child cursor, plan thực tế, bind group, runtime statistics và wait profile; mở rộng khi bằng chứng chỉ ra cần thêm dữ liệu.

### 10.1 Dùng DBMS_XPLAN cho plan

Ví dụ lấy plan của cursor cụ thể:

~~~sql
SELECT *
FROM TABLE(
  DBMS_XPLAN.DISPLAY_CURSOR(
    sql_id          => 'SQL_ID_HERE',
    cursor_child_no => 0,
    format          => 'ALLSTATS LAST +PEEKED_BINDS +PREDICATE +ALIAS +NOTE'
  )
);
~~~

Nếu không có row-source statistics, ALLSTATS LAST có thể không hiển thị A-Rows và các chỉ số runtime mong đợi. Có thể dùng gather_plan_statistics trong truy vấn thử hoặc cấu hình phù hợp trong môi trường kiểm thử.

### 10.2 Dùng V$SQL và V$SQL_PLAN_STATISTICS_ALL

V$SQL chứa thống kê ở cấp cursor như executions, elapsed time, CPU time, buffer gets, disk reads và rows processed. Các cột thống kê thường là tổng hợp hoặc trung bình trên cursor, nên cần chú ý số lần thực thi và thời điểm snapshot.

Ví dụ truy vấn tổng hợp cursor:

~~~sql
SELECT sql_id,
       child_number,
       plan_hash_value,
       executions,
       ROUND(elapsed_time / 1e6, 3) AS elapsed_seconds,
       ROUND(cpu_time / 1e6, 3) AS cpu_seconds,
       buffer_gets,
       disk_reads,
       rows_processed,
       last_active_time
FROM v$sql
WHERE sql_id = 'SQL_ID_HERE'
ORDER BY child_number;
~~~

V$SQL_PLAN_STATISTICS_ALL kết hợp thông tin plan với một số thống kê thực thi theo operation khi được thu thập. Quyền truy cập các V$ view phụ thuộc quyền được cấp và môi trường CDB/PDB.

### 10.3 Dùng SQL Monitor khi phù hợp

Real-Time SQL Monitoring có thể cung cấp góc nhìn tiến trình thực thi cho câu SQL đủ điều kiện monitor, bao gồm thời gian, CPU, I/O, waits, parallel workers và operation-level metrics. Tính năng và quyền sử dụng phụ thuộc phiên bản, edition, cấu hình và licensing của Oracle Database.

SQL Monitor hữu ích với SQL dài, parallel hoặc có nhiều operation. Nó không thay thế việc xác định đúng SQL execution và không phải mọi câu SQL đều tự động có một report monitor.

## 11. So sánh kế hoạch qua nhiều thời điểm

Khi một SQL đột nhiên chậm, hãy so sánh trước và sau sự kiện thay vì chỉ nhìn plan hiện tại.

Nên đối chiếu:

- SQL_ID và child cursor.
- Plan hash value và plan operation.
- Bind group.
- Statistics last analyzed và thay đổi dữ liệu.
- Optimizer environment.
- SQL Profile, SQL Patch, SQL Plan Baseline.
- Thời điểm DDL, deployment hoặc database upgrade.
- Elapsed, CPU, buffer gets, physical reads và wait events.
- Số executions và mức concurrency.

AWR/ASH có thể giúp phân tích lịch sử khi đã được cấp phép và cấu hình phù hợp. AWR lưu các snapshot thống kê; ASH lấy mẫu hoạt động session theo thời gian. Đây là dữ liệu lịch sử có giới hạn lấy mẫu và retention, không phải bản ghi đầy đủ từng thao tác của mọi session.

Khi dùng dữ liệu lịch sử, cần kiểm tra snapshot interval, retention, instance, startup time và SQL execution identity. Không nên so sánh tổng số liệu của hai khoảng thời gian có độ dài hoặc workload khác nhau mà không chuẩn hóa.

## 12. Tránh các kết luận sai thường gặp

| Kết luận vội vàng | Vì sao chưa đủ bằng chứng |
|---|---|
| Cost cao nghĩa là SQL chậm | Cost là ước lượng nội bộ, không phải thời gian thực |
| Cost giảm nghĩa là hiệu năng đã tốt hơn | Runtime có thể bị chi phối bởi cache, waits và concurrency |
| Full scan luôn là lỗi | Full scan có thể tối ưu khi cần nhiều dòng |
| Index xuất hiện trong plan nghĩa là truy vấn hiệu quả | Index access có thể đọc nhiều leaf/table blocks |
| Một SQL_ID chỉ có một plan | Một SQL_ID có thể có nhiều child cursor |
| Plan hash giống nhau nghĩa là thời gian giống nhau | Runtime conditions và bind values có thể khác |
| EXPLAIN PLAN là plan ứng dụng đã chạy | Bind và session environment có thể khác |
| E-Rows và A-Rows khớp nghĩa là SQL tốt | Waits, CPU, I/O, fetch và contention vẫn có thể lớn |
| A-Rows lớn nghĩa là operation chậm | Cần đo thời gian và tài nguyên thực tế |
| Một lần chạy chậm chứng minh regression | Có thể là tải hệ thống, cache hoặc chờ tạm thời |
| Một lần chạy nhanh chứng minh đã sửa lỗi | Cần lặp lại với workload và bind đại diện |
| Hint đã viết chắc chắn được áp dụng | Cần kiểm tra Hint Report và plan thực tế |

## 13. Quy trình phân tích khi chỉ có một screenshot

Nếu nhận được một screenshot execution plan từ đồng nghiệp hoặc hệ thống giám sát, hãy dùng nó như điểm bắt đầu.

### Bước 1: Xác định nguồn và thời điểm

Hỏi screenshot đến từ EXPLAIN PLAN, DISPLAY_CURSOR, SQL Monitor hay công cụ khác. Ghi nhận timestamp, database, PDB, instance và session.

### Bước 2: Xác định cursor

Thu thập SQL_ID, child number và plan hash. Nếu thiếu, cần lấy lại từ database khi có thể. Đừng đoán child cursor dựa trên SQL text.

### Bước 3: Xác định bind và môi trường

Ghi nhận bind datatype, nhóm selectivity, optimizer mode, relevant session parameters, parsing schema và application module/action.

### Bước 4: Lấy plan đầy đủ

Yêu cầu output dạng text đầy đủ, bao gồm predicate information, alias, notes, partition information và adaptive details nếu liên quan. Screenshot có thể cắt mất cột, operation hoặc note quan trọng.

### Bước 5: Thu thập runtime statistics

Nếu có thể tái hiện, chạy truy vấn với row-source statistics trong môi trường phù hợp. So sánh E-Rows/A-Rows, Starts, Buffers, Reads và A-Time.

### Bước 6: Thu thập waits và workload context

Nếu elapsed time cao nhưng CPU thấp, xem wait events. Nếu CPU cao, kiểm tra số dòng, join, sort, parse và concurrency. Ghi nhận fetch pattern và số lần thực thi.

### Bước 7: Lặp lại với tình huống đại diện

Chạy với bind value phổ biến, hiếm và trường hợp biên. Lặp lại đủ để phân biệt xu hướng với biến động nhất thời. Dùng cùng điều kiện thử nghiệm khi so sánh.

### Bước 8: Chỉ đề xuất thay đổi sau khi xác định nguyên nhân

Có thể cần gather statistics, extended statistics, sửa predicate, điều chỉnh index, xử lý bind-sensitive cursor hoặc kiểm soát plan. Mỗi đề xuất phải gắn với bằng chứng đo được và cần đánh giá ảnh hưởng đến workload liên quan.

## 14. Ví dụ: cost thấp nhưng ứng dụng vẫn chậm

Giả sử plan cho thấy:

- INDEX RANGE SCAN trên ORDERS_STATUS_IX.
- TABLE ACCESS BY INDEX ROWID.
- E-Rows thấp.
- Cost thấp.

Ứng dụng vẫn phản ánh truy vấn chậm.

Có nhiều giả thuyết cần kiểm tra:

1. Index range scan trả nhiều dòng thực tế hơn E-Rows.
2. Clustering factor cao khiến table block bị truy cập rải rác.
3. Physical reads chậm do storage.
4. Session chờ I/O hoặc tài nguyên khác.
5. Ứng dụng fetch nhiều dòng qua mạng chậm.
6. SQL chạy nhiều lần liên tiếp, tổng thời gian lớn dù từng lần nhanh.
7. Cursor được dùng cho bind value khác với bind value trong screenshot.

Cách kiểm tra:

- Lấy đúng child cursor và plan.
- So sánh E-Rows/A-Rows, Starts, Buffers, Reads.
- Xem wait events và CPU.
- Kiểm tra bind group và child cursor.
- Đo thời gian database so với thời gian ứng dụng.
- So sánh nhiều lần chạy trong cùng điều kiện.

Chỉ sau khi biết điểm nghẽn mới quyết định có cần đổi index, statistics hoặc SQL.

## 15. Ví dụ: cost tăng nhưng SQL không chậm hơn

Sau một lần gather statistics, cost tăng từ 80 lên 140 nhưng plan hash không đổi. Elapsed time và buffer gets của nhiều lần chạy vẫn tương đương.

Điều này có thể xảy ra vì optimizer đã cập nhật ước lượng cardinality hoặc system inputs nhưng vẫn chọn cùng một kế hoạch. Cost tăng không phải lý do đủ để rollback statistics.

Nếu plan hash thay đổi, vẫn cần đo runtime. Kế hoạch mới có thể tốt hơn, tương đương hoặc tệ hơn. Hãy so sánh trên bind value và workload đại diện, không dựa vào một con số cost.

## 16. Lập báo cáo regression có thể kiểm chứng

Một báo cáo regression tốt nên phân biệt **quan sát**, **giả thuyết** và **kết luận**.

Ví dụ cấu trúc:

| Phần | Nội dung |
|---|---|
| Quan sát | Elapsed tăng từ 0,4 s lên 3,2 s trong cùng loại workload |
| Định danh | SQL_ID, child number, plan hash, timestamp |
| Khác biệt | Child cursor mới dùng hash join thay nested loops |
| Runtime evidence | A-Rows, Buffers, Reads, CPU, waits |
| Nguyên nhân giả thuyết | Cardinality của predicate REGION bị đánh giá thấp |
| Bằng chứng kiểm tra | Histogram/extended stats và dữ liệu thực tế |
| Thay đổi thử | Pending statistics hoặc SQL rewrite trong môi trường test |
| Kết quả | So sánh nhiều lần chạy với cùng bind group |
| Rủi ro | SQL khác dùng chung thống kê/index có thể bị ảnh hưởng |

Nếu chưa có runtime statistics, hãy ghi rõ đó là giả thuyết. Không chuyển một nhận định dựa trên screenshot thành kết luận chắc chắn.

## 17. Checklist trước khi kết luận từ execution plan

- [ ] Biết plan đến từ EXPLAIN PLAN hay cursor thực tế.
- [ ] Có timestamp, database/PDB, instance và session context.
- [ ] Có SQL_ID, child number và plan hash value.
- [ ] Đã xem toàn bộ plan text và Predicate Information.
- [ ] Đã xác định bind datatype và nhóm selectivity.
- [ ] Đã kiểm tra optimizer environment và các note liên quan.
- [ ] Có E-Rows/A-Rows/Starts khi cần đánh giá cardinality.
- [ ] Đã xem Buffers, Reads, CPU, elapsed và wait events.
- [ ] Đã hiểu ứng dụng fetch một phần hay toàn bộ kết quả.
- [ ] Đã xem concurrency, cache và trạng thái hệ thống.
- [ ] Đã so sánh nhiều lần thực thi đại diện.
- [ ] Đã phân biệt observation với hypothesis.
- [ ] Đã đo tác động trước/sau trên workload tương đương.
- [ ] Đã xem ảnh hưởng đến SQL khác trước khi triển khai thay đổi rộng.

## 18. Kết luận

Cost là công cụ ước lượng để optimizer so sánh các kế hoạch, không phải đồng hồ đo thời gian. Execution plan cho biết cách Oracle tổ chức truy vấn trong một ngữ cảnh cụ thể, nhưng một ảnh chụp đơn lẻ không mô tả đầy đủ runtime, bind values, child cursors, waits, concurrency hoặc lịch sử thay đổi.

Khi điều tra hiệu năng, hãy xác định đúng cursor, lấy plan thực tế, so sánh cardinality ước lượng với số dòng thực tế, xem buffer/physical reads và wait events, rồi lặp lại với bind value và workload đại diện. Chỉ kết luận khi bằng chứng giải thích được cả cấu trúc kế hoạch lẫn hành vi lúc chạy.
