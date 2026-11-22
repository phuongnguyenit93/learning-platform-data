# CPU cao: phân biệt tính toán, lập kế hoạch và quá nhiều truy vấn nhỏ

CPU database tăng cao có thể xuất phát từ một truy vấn thực hiện quá nhiều phép tính, optimizer phải phân tích và lập kế hoạch cho quá nhiều câu SQL, hoặc ứng dụng gửi hàng nghìn truy vấn nhỏ khiến chi phí xử lý lặp lại cộng dồn. Ba tình huống này có biểu hiện khác nhau và cần cách xử lý khác nhau. Tăng index, tăng connection hay nâng CPU mà chưa xác định nhóm nguyên nhân có thể làm hệ thống tốn thêm tài nguyên nhưng không cải thiện throughput.

Trong phạm vi **DATABASE_PERFORMANCE**, tối ưu hiệu năng cơ sở dữ liệu cần dựa trên đo đạc tải, execution plan, thống kê và cơ chế truy cập dữ liệu. Khi CPU cao, cần xác định CPU được tiêu thụ ở đâu: trong operator thực thi, trong parse/plan/compile, hay trong nhiều lần gọi có chi phí nhỏ. Đồng thời phải phân biệt CPU của database với CPU của ứng dụng, thời gian chờ I/O, lock và network.

Bài học này hướng dẫn chẩn đoán CPU cao theo triệu chứng, xếp hạng truy vấn theo tổng chi phí và chi phí mỗi lần chạy, phân tích execution plan, nhận diện N+1 và chatty SQL, cải thiện thống kê/index, kiểm soát parallelism và concurrency, cùng quy trình đo trước/sau trên PostgreSQL, MySQL InnoDB và SQL Server.

## 1. CPU cao có nghĩa là gì?

CPU cao là dấu hiệu một hoặc nhiều core đang dành nhiều thời gian cho công việc tính toán. Trong database, công việc đó có thể gồm:

- Parse, validate và rewrite câu SQL.
- Lập kế hoạch truy vấn, ước lượng cardinality và chọn access path.
- Thực thi scan, join, sort, hash, aggregate và expression.
- Kiểm tra điều kiện, chuyển đổi kiểu, xử lý JSON, regex hoặc function.
- Duy trì index, transaction metadata và concurrency control.
- Mã hóa/giải mã, nén, checksum hoặc xử lý dữ liệu theo cấu hình.
- Điều phối worker, parallel query và quản lý bộ nhớ.

Một truy vấn có thể dùng CPU nhiều dù không đọc nhiều dữ liệu từ disk. Ví dụ, một truy vấn regex trên hàng triệu chuỗi đã nằm trong buffer cache có thể tiêu thụ CPU cao nhưng physical read thấp.

Ngược lại, truy vấn chậm không nhất thiết là truy vấn CPU-bound. Nếu truy vấn dành phần lớn thời gian chờ storage, lock, network hoặc connection pool, tăng CPU có thể không giúp.

### Phân biệt CPU time và elapsed time

- **CPU time:** tổng thời gian CPU thực sự dùng để xử lý.
- **Elapsed time:** thời gian trôi qua từ lúc bắt đầu đến lúc kết thúc.
- **Wait time:** thời gian chờ tài nguyên hoặc sự kiện khác.
- **Queue time:** thời gian chờ được cấp worker, connection hoặc slot thực thi.

Ví dụ, một câu SQL mất 5 giây elapsed nhưng chỉ dùng 300 ms CPU, còn lại chờ lock. Câu khác mất 800 ms elapsed và dùng gần 780 ms CPU. Câu thứ hai có khả năng CPU-bound rõ hơn.

Với truy vấn chạy song song, tổng CPU time có thể lớn hơn elapsed time vì nhiều worker dùng CPU đồng thời. Vì vậy, không so sánh hai đại lượng này như thể chúng luôn bằng nhau.

## 2. Ba nhóm nguyên nhân cần phân biệt

| Nhóm | Dấu hiệu thường gặp | Câu hỏi chẩn đoán |
|---|---|---|
| CPU thực thi | Một số truy vấn có CPU cao, scan/join/sort/aggregate lớn | Operator nào đang tính toán nhiều? |
| CPU lập kế hoạch | Nhiều câu SQL khác nhau, parse/compile/plan tăng, tỷ lệ plan cao | Có quá nhiều SQL shape hoặc plan phức tạp không? |
| Quá nhiều truy vấn nhỏ | Số lần gọi rất cao, mỗi lần nhanh nhưng tổng CPU lớn | Có N+1, chatty application hoặc thiếu batching không? |

Ba nhóm có thể xuất hiện cùng lúc. Một ứng dụng ORM có thể tạo hàng nghìn câu SELECT nhỏ; mỗi câu lại có plan khác do literal values; một số truy vấn còn chạy expression không cần thiết. Khi đó cả execution, planning và call count đều góp phần.

### Đừng chỉ nhìn CPU tổng của máy

CPU tổng trên host có thể bị dùng bởi application server, backup agent, antivirus, compression, monitoring hoặc tiến trình khác. Cần xác định process và container nào tiêu thụ CPU, rồi liên kết với hoạt động database.

Nếu CPU host cao nhưng database process thấp, điều tra workload ngoài database hoặc giới hạn CPU/virtualization. Nếu database process cao, tiếp tục phân rã theo query, scheduler, thread và engine metrics.

## 3. Phân biệt CPU bottleneck với I/O, lock và memory pressure

Trước khi tối ưu câu SQL, hãy xác định database đang chạy trên CPU hay đang chờ.

### Dấu hiệu CPU-bound

- Database process hoặc container dùng gần hết CPU được cấp.
- Có nhiều session đang thực thi và ít thời gian chờ I/O/lock tương ứng.
- Throughput tăng chậm khi thêm worker.
- CPU time theo query cao.
- Query latency tăng cùng CPU utilization.
- Runnable queue hoặc scheduler pressure tăng.

### Dấu hiệu I/O-bound

- Query elapsed cao nhưng CPU time thấp.
- Physical read/write latency tăng.
- Wait event liên quan data file, page read, log flush hoặc temp I/O tăng.
- Storage queue depth và latency tăng cùng lúc.
- CPU có thể còn nhàn rỗi trong khi truy vấn chờ.

### Dấu hiệu lock-bound

- Session chờ lock, latch hoặc transaction khác.
- Query elapsed tăng nhưng CPU không tăng tương ứng.
- Một transaction dài chặn nhiều session.
- Deadlock hoặc lock timeout tăng.

### Dấu hiệu memory-bound hoặc spill

- Sort/hash spill xuống temp.
- Memory grant hoặc work memory không đủ.
- Page eviction và cache churn tăng.
- GC hoặc memory pressure ở tầng ứng dụng làm request giữ connection lâu.
- CPU có thể tăng do hash/sort nhiều vòng hoặc xử lý lại dữ liệu.

Một hệ thống có thể cùng lúc bị CPU và I/O giới hạn. Hãy đọc wait events, execution plan và metrics của host theo cùng khoảng thời gian; tránh kết luận chỉ từ một dashboard.

## 4. Đo CPU ở đúng phạm vi

Nên đo ít nhất bốn lớp:

1. **Host/VM:** CPU utilization theo core, run queue, context switch, CPU steal hoặc throttling.
2. **Database process/container:** CPU time, quota, memory và số thread.
3. **Database scheduler/session:** active, runnable, waiting, parallel workers.
4. **Query fingerprint:** tổng CPU, CPU trung bình, số lần gọi, elapsed, rows và logical I/O nếu engine cung cấp.

### CPU tổng và CPU mỗi query

CPU tổng cao có thể do một truy vấn cực nặng hoặc do hàng triệu truy vấn nhỏ. Cần xếp hạng theo hai cách:

- Tổng CPU hoặc tổng chi phí trong khoảng quan sát: tìm phần đóng góp lớn nhất vào toàn hệ thống.
- CPU trung bình mỗi lần gọi: tìm truy vấn đắt ở từng lần thực thi.

Nếu một query dùng 20 ms CPU mỗi lần và chạy 100.000 lần, tổng CPU xấp xỉ 2.000 giây. Một query khác dùng 2 giây mỗi lần nhưng chỉ chạy 10 lần, tổng CPU xấp xỉ 20 giây. Query nhỏ có thể là nguồn tiêu thụ CPU lớn nhất vì tần suất.

### Chuẩn hóa theo fingerprint

Nhóm các câu SQL cùng cấu trúc thành fingerprint hoặc digest, bỏ qua giá trị literal để xem tổng số lần gọi và tổng chi phí. Sau đó tách theo tham số hoặc tenant khi cần tìm phân bố dữ liệu khác nhau.

Không gộp mù quáng mọi truy vấn vào một fingerprint nếu khác biệt tham số dẫn đến plan hoặc cardinality khác nhau. Dùng fingerprint để tìm nhóm, rồi phân tích các nhóm tham số đại diện.

## 5. Tổng chi phí, chi phí trung bình và tần suất gọi

Với một query shape, có thể ước lượng tổng CPU đóng góp:

~~~text
Tổng CPU ≈ số lần gọi × CPU trung bình mỗi lần
~~~

Nếu chỉ có elapsed time thay vì CPU time, công thức vẫn có thể xếp hạng thời gian thực thi tích lũy, nhưng không được gọi đó là CPU. Một truy vấn chờ I/O hoặc lock lâu có thể đứng đầu theo elapsed mà không đứng đầu theo CPU.

Hãy xem đồng thời:

- Calls / executions.
- Total CPU hoặc worker time nếu có.
- Average CPU per execution.
- Total elapsed và average elapsed.
- Rows returned và rows examined.
- Logical reads/buffers.
- Sort/hash/temp metrics.
- Plan count hoặc compile/plan time nếu có.

### Ví dụ phân loại

| Query | Calls | CPU trung bình | Tổng CPU ước lượng |
|---|---:|---:|---:|
| Tra cứu trạng thái | 200.000 | 0,4 ms | 80 giây |
| Báo cáo tổng hợp | 20 | 1.500 ms | 30 giây |
| Tìm kiếm khách hàng | 5.000 | 8 ms | 40 giây |

Truy vấn tra cứu trạng thái có chi phí mỗi lần rất nhỏ nhưng tổng CPU cao nhất. Báo cáo tổng hợp đắt mỗi lần nhưng tần suất thấp hơn. Cách tối ưu sẽ khác: giảm số lần gọi hoặc gom truy vấn cho trường hợp thứ nhất; xem plan, scan và aggregate cho trường hợp thứ hai.

## 6. CPU thực thi: đọc execution plan để tìm operator tốn kém

Execution plan mô tả cách database lấy dữ liệu và thực hiện các bước xử lý. Khi CPU cao, hãy tìm operator xử lý nhiều dòng, thực hiện nhiều vòng lặp hoặc tính toán phức tạp.

Các operator thường cần chú ý:

- Table/Sequential Scan trên phạm vi lớn.
- Nested Loop có inner side bị chạy quá nhiều lần.
- Hash Join hoặc Hash Aggregate xử lý tập dữ liệu lớn.
- Sort lớn, DISTINCT hoặc Window Function.
- Expression, function hoặc conversion áp dụng trên nhiều dòng.
- Scalar subquery hoặc correlated subquery lặp lại.
- Partition scan không được prune như dự kiến.
- Parallel plan tạo quá nhiều worker và coordination overhead.

Không kết luận operator đắt chỉ dựa trên tên. Hãy xem actual rows, loops, CPU/elapsed time, buffers, spill và số dòng đầu vào/đầu ra.

### Estimated rows và actual rows

Optimizer chọn plan dựa trên ước lượng. Nếu estimated rows là 100 nhưng actual rows là 5 triệu, nó có thể chọn Nested Loop hoặc cấp bộ nhớ không phù hợp. Sai lệch cardinality thường dẫn đến CPU tăng vì thực hiện quá nhiều lookup, join hoặc sort.

Tìm những node có chênh lệch lớn giữa estimated và actual rows, đặc biệt ở các bước đầu của plan. Kiểm tra thống kê, histogram, correlation, predicate và parameter distribution.

### Loops nhân chi phí

Một node chạy 1 lần với 1 triệu dòng có chi phí khác node chạy 1 triệu lần, mỗi lần lookup vài dòng. Trong Nested Loop, inner node có thể có loops rất cao. Hãy nhân số vòng lặp với số dòng và chi phí mỗi vòng để hiểu quy mô thực tế.

## 7. CPU lập kế hoạch: parse, optimize và compile

Database phải xử lý câu SQL trước khi thực thi. Tùy engine, các bước gồm parse, name resolution, rewrite/normalization, kiểm tra quyền, ước lượng cardinality, tìm join order, chọn index và tạo execution plan.

Planning CPU có thể tăng khi:

- Ứng dụng gửi quá nhiều SQL text khác nhau.
- Giá trị literal được nối trực tiếp vào câu SQL.
- Query có rất nhiều join hoặc biểu thức phức tạp.
- Query generator tạo nhiều biến thể không cần thiết.
- Prepared statement bị tạo và hủy liên tục.
- Plan cache bị churn hoặc không tái sử dụng.
- Schema/statistics thay đổi làm invalidation hoặc recompile.
- Partition count lớn khiến planning phải xem xét nhiều đối tượng.

### Parse/plan time khác execution time

Một câu lệnh có thể được lập kế hoạch trong vài mili giây nhưng thực thi hàng trăm mili giây. Với hàng chục nghìn câu SQL mỗi giây, vài mili giây planning có thể trở thành chi phí CPU đáng kể.

Ngược lại, một câu SQL phức tạp có thể tốn nhiều planning CPU nhưng chỉ chạy một lần. Cần xem tổng planning time và số plans, không chỉ thời gian thực thi.

### SQL text ổn định

Nên dùng bind parameters/PreparedStatement để giữ cấu trúc SQL ổn định. Điều này có thể giúp driver hoặc database tái sử dụng statement và giảm lượng SQL text biến thể. Cơ chế cụ thể phụ thuộc driver và engine; không phải mọi PreparedStatement đều mặc định tạo server-side prepared plan hoặc dùng lại cùng một plan.

### Plan cache không phải lúc nào cũng có lợi

Một plan dùng chung có thể không phù hợp với mọi giá trị tham số nếu phân bố dữ liệu lệch mạnh. Ví dụ tenant nhỏ chỉ có vài trăm dòng, tenant lớn có hàng chục triệu dòng. Plan tốt cho tenant này có thể kém cho tenant kia.

Hãy đo planning CPU cùng runtime theo các nhóm tham số. Nếu cần plan riêng, dùng cơ chế parameter-sensitive plan hoặc cách kiểm soát được engine hỗ trợ sau khi benchmark; tránh nối literal tùy tiện để tạo vô số plan.

## 8. Quá nhiều truy vấn nhỏ: vì sao tổng CPU lại lớn?

Một truy vấn nhỏ có thể chỉ mất vài trăm micro giây CPU. Nhưng nếu ứng dụng gọi nó hàng trăm nghìn lần, database vẫn phải lặp lại các bước nhận lệnh, kiểm tra session, bind, execute, trả kết quả và ghi nhận thống kê.

Chi phí có thể gồm:

- Parse/plan nếu statement không được tái sử dụng.
- Kiểm tra quyền và metadata.
- Đọc index/heap page và xử lý predicate.
- Tạo ResultSet/cursor và serialize dữ liệu.
- Network protocol và round trip.
- Quản lý transaction, lock và statement state.
- Ghi log nếu mỗi câu là một transaction ghi riêng.

Round trip chủ yếu làm tăng elapsed time và concurrency; nó không đồng nghĩa mỗi millisecond network là CPU database. Tuy nhiên, số lượng statement lớn có thể làm tăng CPU xử lý mỗi statement và số session hoạt động.

### N+1 query

N+1 là mẫu phổ biến trong ORM:

1. Query đầu lấy danh sách 500 đơn hàng.
2. Với mỗi đơn, ứng dụng chạy thêm một query lấy khách hàng hoặc dòng chi tiết.
3. Tổng số query có thể là 1 + 500 hoặc nhiều hơn.

Nếu mỗi query nhỏ, từng lần chạy có thể trông nhanh nhưng tổng calls, parse/execute overhead và round trips rất lớn.

Ví dụ dạng N+1:

~~~java
List<Order> orders = orderRepository.findRecentOrders();

for (Order order : orders) {
    Customer customer = customerRepository.findById(order.customerId());
    order.setCustomer(customer);
}
~~~

Có thể thay bằng join hoặc truy vấn lấy tất cả customer cần thiết theo một tập khóa, tùy mô hình dữ liệu:

~~~sql
SELECT
    o.order_id,
    o.created_at,
    c.customer_id,
    c.customer_name
FROM orders o
JOIN customers c ON c.customer_id = o.customer_id
WHERE o.created_at >= ?;
~~~

Hoặc dùng hai query theo batch: lấy orders, gom customer_id, rồi truy vấn customer bằng IN/array parameter và ánh xạ trong ứng dụng. Chọn cách phù hợp với cardinality và kích thước dữ liệu.

### Chatty SQL

Ứng dụng chatty gửi nhiều câu lệnh nhỏ tuần tự:

~~~text
Request
  |
  +--> SELECT account
  |
  +--> SELECT settings
  |
  +--> SELECT permissions
  |
  +--> SELECT preferences
  |
  +--> UPDATE last_seen
  |
  +--> INSERT audit row
~~~

Nếu các câu lệnh độc lập, có thể gom bằng join, batch, stored procedure hoặc một query có projection phù hợp. Nếu các câu lệnh phụ thuộc kết quả trước, cân nhắc giảm số round trip hoặc thực hiện logic gần database khi hợp lý.

Không gom mọi thứ thành một query khổng lồ nếu điều đó làm cardinality, memory hoặc plan phức tạp hơn. Mục tiêu là giảm tổng chi phí, không phải tối thiểu số câu SQL bằng mọi giá.

## 9. Nhận diện nhiều query từ ORM hoặc tầng ứng dụng

Một số dấu hiệu:

- Số query/second tăng mạnh nhưng số request API không tăng tương ứng.
- Nhiều câu SQL cùng fingerprint chạy lặp lại theo từng entity.
- Query nhỏ trả một hoặc vài dòng nhưng calls rất cao.
- Connection acquisition và network round trip chiếm tỷ trọng lớn.
- ORM bật lazy loading trong vòng lặp.
- Log SQL cho thấy cùng một câu được gọi liên tiếp với key khác nhau.
- Nhiều câu UPDATE một dòng có thể gom thành batch.
- Một request API tạo hàng chục hoặc hàng trăm database spans.

### Dùng trace để liên kết query với request

Gắn trace/correlation id cho request và database spans. Một trace có 1.000 span database nhỏ là tín hiệu cần điều tra N+1 hoặc chatty SQL. Kết hợp với query fingerprint để xác định câu lệnh lặp lại.

Không ghi toàn bộ giá trị bind nhạy cảm vào log. Dùng fingerprint, parameter type, số dòng và thông tin đã được che/mask theo chính sách.

### Đo số query trên mỗi request

Theo dõi query count per request theo p50/p95/p99. Nếu một endpoint thường tạo 5 query nhưng p95 tạo 200 query, có thể có nhánh logic hoặc lazy-loading bất thường.

So sánh số query với số entity được trả về. Mối quan hệ gần tuyến tính giữa số entity và số query phụ thường là dấu hiệu N+1.

## 10. Giảm số lần gọi mà vẫn giữ semantics

Các cách thường dùng:

### Join và projection có chủ đích

Lấy dữ liệu liên quan trong một query khi quan hệ và cardinality phù hợp. Chỉ chọn cột cần dùng để tránh truyền dữ liệu dư thừa.

### Batch lookup

Gom các khóa cần tra cứu rồi lấy theo một truy vấn IN, array hoặc table-valued parameter tùy engine. Giới hạn kích thước danh sách để tránh vượt giới hạn bind và tạo plan xấu.

### Batch write

Dùng PreparedStatement batching, multi-row insert hoặc bulk API. Chọn batch size dựa trên commit cost, lock duration, log throughput và memory.

### Fetch size và streaming

Nếu đọc nhiều dòng, dùng fetch size/cursor phù hợp driver để tránh một query cho mỗi dòng và tránh tải toàn bộ kết quả vào heap. Fetch size là hint và hành vi phụ thuộc driver.

### Cache dữ liệu ít thay đổi

Có thể cache metadata hoặc reference data nếu consistency policy cho phép. Cache giúp giảm calls nhưng cần TTL, invalidation và kiểm soát stale data.

### Materialize hoặc precompute

Với phép tính tổng hợp được lặp lại nhiều lần, có thể dùng summary table, materialized view hoặc cache kết quả. Cần cân nhắc chi phí refresh, độ trễ dữ liệu và write amplification.

## 11. Truy vấn tính toán nặng: scan, filter và expression

CPU có thể tăng khi database phải kiểm tra quá nhiều dòng hoặc tính expression cho từng dòng.

Ví dụ:

~~~sql
SELECT order_id
FROM orders
WHERE LOWER(email) = LOWER(?);
~~~

Nếu không có expression index hoặc chiến lược tương ứng, database có thể phải tính LOWER trên nhiều dòng. Cách xử lý phụ thuộc collation, chuẩn hóa dữ liệu và yêu cầu tìm kiếm.

Một số mẫu cần xem xét:

- Function trên cột trong WHERE.
- CAST/CONVERT trên cột có index.
- LIKE có wildcard đầu chuỗi.
- Regex hoặc full-text expression trên tập lớn.
- JSON extraction lặp lại cho từng row.
- UDF/scalar function gọi cho hàng triệu dòng.
- OR conditions làm optimizer khó chọn access path.
- Predicate không chọn lọc hoặc filter được áp dụng quá muộn.

### SARGability

Predicate có thể tận dụng index để tìm phạm vi dữ liệu thường được gọi là SARGable. Điều kiện không SARGable có thể buộc database tính biểu thức trên nhiều dòng.

Ví dụ lọc theo ngày:

~~~sql
-- Có thể làm mất khả năng seek trên index created_at
WHERE DATE(created_at) = ?

-- Dùng khoảng nửa mở trên cột gốc
WHERE created_at >= ?
  AND created_at < ?;
~~~

Cách thứ hai thường cho phép range seek nếu index và kiểu tham số phù hợp. Cần tính đúng timezone và ranh giới ngày.

### Implicit conversion

Nếu cột là BIGINT nhưng ứng dụng bind VARCHAR, database có thể chuyển đổi ngầm. Nếu conversion áp dụng lên cột hoặc làm thay đổi collation, index seek có thể không được dùng.

Bind đúng kiểu và xem plan/cảnh báo conversion của engine. Không sửa bằng cách thêm index trước khi hiểu conversion.

## 12. Sort, hash, join và aggregate tiêu thụ CPU

### Sort

ORDER BY, DISTINCT, window functions và merge join có thể cần sắp xếp lượng dữ liệu lớn. Nếu dữ liệu đầu vào lớn hoặc không có thứ tự phù hợp, sort có thể tiêu thụ CPU và bộ nhớ; khi spill, nó còn tạo temp I/O.

Có thể giảm chi phí bằng cách filter sớm, giảm row width, giới hạn số dòng, hoặc tạo index hỗ trợ thứ tự nếu lợi ích tổng thể lớn hơn chi phí ghi.

### Hash Join và Hash Aggregate

Hash join xây dựng hash table từ một phía rồi dò phía còn lại. Hash aggregate nhóm dữ liệu theo key. Nếu input lớn, số nhóm cao hoặc memory grant không đủ, CPU và temp I/O có thể tăng.

Kiểm tra build/probe rows, estimated vs actual cardinality, memory grant, spill và số vòng xử lý.

### Nested Loop

Nested Loop hiệu quả khi outer input nhỏ và inner side có index phù hợp. Nếu outer input lớn và inner side bị scan hoặc lookup lặp lại nhiều lần, CPU có thể tăng rất mạnh.

### DISTINCT và GROUP BY

DISTINCT/GROUP BY có thể yêu cầu sort hoặc hash. Nếu dữ liệu đầu vào đã duy nhất theo khóa hoặc có thể tổng hợp sớm hơn, hãy xem xét query shape. Không loại bỏ DISTINCT nếu nó đang bảo vệ semantics chống trùng.

## 13. Statistics và cardinality estimation

Optimizer dựa trên thống kê để ước lượng số dòng và phân bố giá trị. Thống kê cũ hoặc không đủ chi tiết có thể làm chọn plan đắt CPU.

Kiểm tra:

- Last analyze/update statistics.
- Estimated rows so với actual rows.
- Histogram và độ chọn lọc.
- Data skew theo tenant/status/time.
- Correlation giữa nhiều cột.
- Parameter values đại diện.
- Partition-level và global statistics theo engine.

### Cập nhật thống kê sau thay đổi lớn

Bulk load, delete lớn, backfill hoặc thay đổi phân bố có thể khiến thống kê không còn đại diện. Cập nhật statistics/analyze có thể giúp optimizer chọn plan tốt hơn.

Không chạy analyze liên tục mà không có lý do. Thu thập thống kê cũng tiêu tốn CPU và I/O; cần lập lịch phù hợp và theo dõi kết quả.

### Extended statistics và multi-column statistics

Nếu các cột có tương quan, giả định độc lập có thể làm cardinality sai. Một số engine hỗ trợ thống kê nhiều cột hoặc expression statistics. Dùng khi plan cho thấy ước lượng sai có hệ thống và truy vấn lọc trên nhiều cột tương quan.

## 14. Index có thể giảm CPU nhưng cũng có thể tăng CPU

Index phù hợp có thể giảm số dòng phải đọc và số predicate phải tính. Tuy nhiên, mỗi index bổ sung làm INSERT/UPDATE/DELETE phải duy trì thêm cấu trúc và tăng dung lượng/cache pressure.

Trước khi thêm index, xác định:

- Query fingerprint nào sẽ được cải thiện.
- Predicate và order by nào cần hỗ trợ.
- Số dòng ước lượng và actual.
- Selectivity của leading columns.
- Index có giúp tránh sort hoặc lookup không.
- Chi phí ghi, storage và cache.
- Có index trùng lặp hay không.

### Index không thay thế query design

Nếu query cần 70% số dòng của bảng, scan có thể rẻ hơn index lookup cộng heap fetch. Nếu truy vấn trả 5 dòng nhưng scan 10 triệu dòng, index phù hợp có thể giảm CPU và I/O rõ rệt.

### Covering index

Index chứa đủ cột cần truy vấn có thể giảm lookup về heap/table trong một số engine. Nhưng index rộng làm tăng kích thước, cache footprint và write cost. Chỉ thêm INCLUDE columns hoặc covering columns khi workload chứng minh lợi ích.

### Partial/filtered index

Nếu chỉ một tập nhỏ thường được truy vấn, partial/filtered index có thể nhỏ và chọn lọc hơn. Predicate truy vấn phải tương thích với điều kiện index và engine phải hỗ trợ.

## 15. Parallelism: tăng tốc truy vấn hay làm CPU quá tải?

Parallel query chia công việc cho nhiều worker. Nó có thể giảm elapsed time của một truy vấn lớn nhưng làm tổng CPU tiêu thụ tăng hoặc cạnh tranh với các truy vấn khác.

Ví dụ, một truy vấn scan/aggregate có thể dùng 8 worker. Nếu 20 truy vấn như vậy chạy đồng thời, database có thể cần rất nhiều runnable worker và CPU scheduling overhead.

### Khi parallelism hữu ích

- Truy vấn phân tích đọc nhiều dữ liệu.
- Operator có thể chia nhỏ hiệu quả.
- Có đủ CPU và memory bandwidth.
- Workload tương tác vẫn được bảo vệ.
- Tổng throughput tăng và p95/p99 chấp nhận được.

### Khi parallelism gây hại

- Nhiều truy vấn lớn chạy cùng lúc.
- Query nhỏ bị khởi tạo worker quá mức.
- Worker coordination và data exchange tốn kém.
- CPU đã bão hòa.
- Memory grant nhân lên theo worker.
- Một workload báo cáo chiếm CPU của OLTP.

### Điều chỉnh theo workload

Có thể giới hạn parallelism toàn cục, theo query hoặc workload group tùy engine. SQL Server có MAXDOP và cost threshold settings; PostgreSQL có parallel worker settings; MySQL có parallelism riêng theo engine/feature và phiên bản. Không sao chép một giá trị cấu hình giữa các hệ quản trị.

Benchmark workload hỗn hợp, không chỉ một query chạy riêng. Mục tiêu là throughput toàn hệ thống và tail latency, không phải elapsed time của một truy vấn đơn lẻ.

## 16. Planning CPU và nhiều SQL text khác nhau

Nếu ứng dụng tạo SQL bằng cách nối literal:

~~~java
String sql = "SELECT balance FROM accounts WHERE account_id = " + accountId;
~~~

Mỗi account_id có thể tạo một SQL text khác. Tùy engine, điều này có thể làm tăng parse/compile, giảm plan reuse hoặc làm cache churn.

Dùng bind parameter:

~~~java
String sql = "SELECT balance FROM accounts WHERE account_id = ?";
try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setLong(1, accountId);
    // execute
}
~~~

Cách này giữ SQL shape ổn định và bảo vệ giá trị đầu vào. Tuy nhiên, server-side preparation và plan reuse phụ thuộc driver/database. Nếu tham số có phân bố lệch, plan dùng chung có thể không phù hợp cho mọi trường hợp.

### Query generator và số biến thể

ORM có thể sinh SQL khác nhau do:

- Thứ tự điều kiện thay đổi.
- Danh sách IN có độ dài khác nhau.
- Projection khác nhau theo màn hình.
- Tên bảng hoặc schema động.
- Literal được nhúng vào query text.
- Các predicate optional được thêm/bỏ.

Hãy kiểm tra số fingerprint và số plan. Chuẩn hóa SQL shape khi hợp lý, nhưng không cố ép mọi trường hợp thành một câu lệnh phức tạp nếu plan trở nên kém.

## 17. PostgreSQL: tìm query có chi phí cao

Nếu pg_stat_statements được cài và bật, có thể xem calls, execution time, rows và buffer statistics theo query fingerprint.

~~~sql
SELECT
    queryid,
    calls,
    round(total_exec_time::numeric, 2) AS total_exec_ms,
    round(mean_exec_time::numeric, 3) AS mean_exec_ms,
    rows,
    shared_blks_hit,
    shared_blks_read,
    temp_blks_written,
    left(query, 160) AS query_sample
FROM pg_stat_statements
ORDER BY total_exec_time DESC
LIMIT 20;
~~~

**Lưu ý:** total_exec_time và mean_exec_time là thời gian thực thi đã đo theo elapsed time, không phải CPU time thuần. Chúng hữu ích để xếp hạng query tốn thời gian database, nhưng cần kết hợp wait events và số liệu host để xác định CPU. Nếu bật track_planning, pg_stat_statements có thể cung cấp planning metrics; đó cũng là thời gian lập kế hoạch đã đo, không phải phép đo CPU chính xác.

### Quan sát session

~~~sql
SELECT
    pid,
    state,
    wait_event_type,
    wait_event,
    now() - query_start AS elapsed,
    left(query, 160) AS query_sample
FROM pg_stat_activity
WHERE state = 'active'
ORDER BY query_start;
~~~

Session active không có wait_event có thể đang dùng CPU, nhưng cần đối chiếu process CPU và profiling; không nên coi trạng thái này là phép đo CPU trực tiếp.

### Đọc plan

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, created_at
FROM orders
WHERE tenant_id = 42
  AND status = 'PAID'
ORDER BY created_at DESC
LIMIT 50;
~~~

Xem actual rows, loops, buffers, sort, join và chênh lệch estimated/actual. EXPLAIN ANALYZE thực thi câu lệnh và có overhead đo đạc; với lệnh ghi, nó có thể thay đổi dữ liệu. Chạy trong môi trường an toàn hoặc transaction có thể rollback khi phù hợp.

Để đo CPU theo query trên PostgreSQL, có thể dùng profiler ở tầng OS hoặc extension chuyên biệt như pg_stat_kcache nếu đã cài và được phê duyệt. Không giả định extension này có sẵn.

## 18. MySQL InnoDB: digest và statement analysis

Performance Schema lưu thống kê statement theo digest. Ví dụ:

~~~sql
SELECT
    DIGEST_TEXT,
    COUNT_STAR AS calls,
    ROUND(SUM_TIMER_WAIT / 1000000000000, 2) AS total_seconds,
    ROUND(AVG_TIMER_WAIT / 1000000000000, 6) AS avg_seconds,
    SUM_ROWS_EXAMINED,
    SUM_ROWS_SENT
FROM performance_schema.events_statements_summary_by_digest
ORDER BY SUM_TIMER_WAIT DESC
LIMIT 20;
~~~

TIMER_WAIT trong Performance Schema được biểu diễn theo picosecond ở các cấu hình hỗ trợ; phép chia trên chuyển sang giây. Các giá trị này phản ánh thời gian chờ/thực thi được instrument, không phải CPU time thuần.

Có thể dùng sys.statement_analysis nếu sys schema được cài để đọc tổng hợp dễ hơn. Xem rows_examined so với rows_sent, sort rows, temporary tables và query count để phát hiện query xử lý nhiều dữ liệu hoặc quá nhiều lần.

CPU theo process/thread cần kết hợp công cụ OS và công cụ giám sát phù hợp. Không suy ra CPU chính xác từ TIMER_WAIT.

Dùng EXPLAIN hoặc EXPLAIN ANALYZE tùy phiên bản để xem access path, actual rows và iterator timing. Kiểm tra index, join order, rows examined, sort và biểu thức lọc.

## 19. SQL Server: CPU time, worker time và scheduler

SQL Server cung cấp DMV để xếp hạng query theo worker time. Ví dụ:

~~~sql
SELECT TOP (20)
    qs.execution_count,
    qs.total_worker_time / 1000.0 AS total_cpu_ms,
    (qs.total_worker_time / NULLIF(qs.execution_count, 0)) / 1000.0
        AS avg_cpu_ms,
    qs.total_elapsed_time / 1000.0 AS total_elapsed_ms,
    SUBSTRING(
        st.text,
        (qs.statement_start_offset / 2) + 1,
        (
            (CASE qs.statement_end_offset
                WHEN -1 THEN DATALENGTH(st.text)
                ELSE qs.statement_end_offset
             END - qs.statement_start_offset) / 2
        ) + 1
    ) AS statement_text
FROM sys.dm_exec_query_stats AS qs
CROSS APPLY sys.dm_exec_sql_text(qs.sql_handle) AS st
ORDER BY qs.total_worker_time DESC;
~~~

total_worker_time là CPU time tích lũy của worker cho các lần thực thi trong plan cache; nó có thể cộng CPU của nhiều worker chạy song song. DMV chỉ phản ánh các plan còn trong cache và counter từ vòng đời tương ứng, nên lấy mẫu định kỳ và hiểu việc reset/eviction.

Có thể đối chiếu:

- Query Store runtime stats để xem CPU và duration theo khoảng thời gian.
- sys.dm_os_schedulers để quan sát runnable_tasks_count.
- Wait statistics để phân biệt SOS_SCHEDULER_YIELD với wait I/O, lock hoặc memory.
- Actual execution plan và SET STATISTICS TIME, IO ON trong môi trường phù hợp.

SOS_SCHEDULER_YIELD có thể xuất hiện khi worker nhường scheduler sau quantum CPU; cần xem tổng thể chứ không dùng riêng wait này làm kết luận. Query Store và DMV có thể cung cấp CPU time khác với elapsed time.

## 20. Java application: đo query count và loại bỏ N+1

Một endpoint trả danh sách đơn hàng có thể tạo một query lấy orders và một query customer cho mỗi order. Để phát hiện:

- Gắn trace id vào request.
- Ghi số database spans/query trên request.
- Nhóm câu SQL theo fingerprint.
- So sánh query count với số entity trả về.
- Đo thời gian lấy connection, thời gian execute và thời gian đọc ResultSet.
- Kiểm tra ORM lazy loading và log SQL trong môi trường phù hợp.

Ví dụ gom dữ liệu liên quan:

~~~java
List<Order> orders = orderRepository.findRecentOrders();

Set<Long> customerIds = orders.stream()
    .map(Order::customerId)
    .collect(Collectors.toSet());

Map<Long, Customer> customers =
    customerRepository.findByIds(customerIds).stream()
        .collect(Collectors.toMap(Customer::id, Function.identity()));

for (Order order : orders) {
    order.setCustomer(customers.get(order.customerId()));
}
~~~

Đoạn mã minh họa batch lookup. Repository có thể dùng IN placeholders, array parameter hoặc table-valued parameter tùy database/driver. Cần xử lý danh sách rỗng, giới hạn kích thước batch và bảo đảm thứ tự/semantics của dữ liệu.

Không bật SQL logging chứa giá trị nhạy cảm ở production. Dùng fingerprint và bind metadata đã được che để tìm N+1 mà vẫn tuân thủ chính sách dữ liệu.

## 21. Quy trình điều tra CPU cao theo từng bước

Một quy trình thực tế:

1. **Xác định phạm vi:** CPU host, VM, container hay database process đang cao?
2. **Chọn khoảng thời gian:** xác định thời điểm bắt đầu, kéo dài và có trùng batch/backup/traffic peak không.
3. **Đo throughput:** QPS/TPS, request rate, số session và concurrency.
4. **Phân biệt CPU với wait:** xem CPU time, elapsed, lock waits, I/O waits và queue.
5. **Xếp hạng fingerprint:** tổng CPU nếu có, tổng elapsed, calls, average và rows examined.
6. **Tách nhóm nguyên nhân:** execution nặng, planning/compile hoặc quá nhiều query nhỏ.
7. **Đọc execution plan:** estimated/actual rows, loops, access path, join, sort, hash và spill.
8. **Kiểm tra thống kê:** độ mới, skew, correlation và parameter distribution.
9. **Kiểm tra application trace:** query count/request, N+1, chatty SQL, batch và connection hold time.
10. **Kiểm tra concurrency:** worker, parallelism, pool size và workload classes.
11. **Đưa ra một thay đổi có giả thuyết:** giảm rows, giảm calls, cải thiện plan hoặc điều tiết concurrency.
12. **Benchmark lại:** cùng dữ liệu, query mix, concurrency và điều kiện cache.
13. **Theo dõi production:** p95/p99, CPU, throughput, error, lock, I/O và write cost.
14. **Ghi lại kết quả:** baseline, thay đổi, tác động và điều kiện rollback.

### Chọn thứ tự ưu tiên

Ưu tiên query hoặc nhóm query có tổng đóng góp lớn, có đường sửa rõ và ít rủi ro. Không nhất thiết tối ưu query có CPU trung bình cao nhất nếu nó chỉ chạy vài lần và không ảnh hưởng SLO.

## 22. Ví dụ chẩn đoán: CPU tăng nhưng từng query đều nhanh

Một dịch vụ thương mại có CPU database tăng từ 35% lên 90% sau khi triển khai phiên bản ứng dụng mới. p95 API tăng từ 120 ms lên 260 ms. Query log cho thấy nhiều SELECT lấy customer theo id; mỗi query mất dưới 1 ms.

### Bằng chứng ban đầu

- Calls của fingerprint customer lookup tăng gấp 40 lần.
- CPU trung bình mỗi lần gọi thấp.
- Tổng thời gian thực thi của fingerprint đứng đầu.
- Một request trả 50 orders tạo khoảng 51 query database.
- Database không có dấu hiệu I/O latency tăng đáng kể.
- Execution plan của lookup dùng index seek/lookup hợp lý.

### Giả thuyết

Plan của một query riêng lẻ không phải bottleneck chính. Ứng dụng phát sinh N+1 khiến số lần gọi tăng và chi phí parse/execute/protocol cộng dồn.

### Cách sửa và xác nhận

1. Dùng batch lookup lấy customer theo tập customer_id.
2. Giữ projection chỉ gồm cột cần dùng.
3. Giới hạn kích thước IN batch theo driver/database.
4. Đo query count mỗi request trước và sau.
5. So sánh total CPU, calls, p95/p99 và throughput.
6. Kiểm tra memory và response payload để bảo đảm không overfetch.

Nếu query count giảm từ khoảng 51 xuống 2 và CPU database giảm trong cùng mức traffic, giả thuyết được hỗ trợ. Nếu CPU vẫn cao, tiếp tục xem query khác và planning/compile.

## 23. Ví dụ chẩn đoán: một truy vấn tổng hợp tiêu thụ CPU

Một báo cáo tính tổng doanh thu theo tenant trong 90 ngày chạy trên bảng orders lớn. CPU database tăng mạnh mỗi khi báo cáo chạy.

### Bằng chứng

- Calls thấp nhưng CPU mỗi lần và tổng CPU đều cao.
- Plan scan hàng chục triệu dòng.
- Hash Aggregate xử lý nhiều nhóm.
- Estimated rows lệch xa actual rows.
- Một số predicate dùng function trên cột thời gian.
- Temp spill có thể xuất hiện khi memory grant không đủ.

### Hướng xử lý

- Viết predicate thời gian dạng range trên cột gốc.
- Kiểm tra thống kê và phân bố tenant.
- Đánh giá index phù hợp với filter/grouping.
- Giảm số cột và dòng đầu vào.
- Xem có thể tổng hợp incremental hoặc dùng summary table không.
- Giới hạn concurrency báo cáo để bảo vệ OLTP.
- Benchmark với cùng khoảng thời gian và tenant đại diện.

Không chỉ thêm index. Nếu báo cáo cần đọc phần lớn dữ liệu, scan có thể vẫn là access path hợp lý; pre-aggregation hoặc workload isolation có thể mang lại lợi ích lớn hơn.

## 24. Ví dụ chẩn đoán: CPU lập kế hoạch tăng

Một ứng dụng tạo SQL text bằng cách nối literal và có nhiều biến thể theo filter. Sau khi traffic tăng, CPU database tăng dù execution time trung bình không thay đổi nhiều.

### Bằng chứng

- Số query fingerprint hoặc plan cache entries tăng.
- Nhiều câu SQL chỉ khác literal hoặc thứ tự predicate.
- Planning/compile count tăng.
- Calls phân tán trên nhiều query text.
- Mỗi câu có ít rows và execution time ngắn.

### Hướng xử lý

- Dùng bind parameter cho giá trị.
- Chuẩn hóa thứ tự và hình dạng SQL trong query builder.
- Tái sử dụng PreparedStatement trong phạm vi connection hợp lý.
- Kiểm tra driver/server-side prepare và statement cache.
- Theo dõi plan reuse, planning/compile time và memory cache.
- Phân nhóm tham số có data skew để bảo đảm plan dùng chung không gây regression.

Không ép mọi query vào một generic plan nếu parameter skew lớn. Cần đo planning CPU và execution CPU riêng trước khi chọn cách tái sử dụng plan.

## 25. Benchmark xác nhận cải thiện CPU

Benchmark phải giữ điều kiện so sánh tương đương.

### Baseline cần ghi

- Database CPU theo process/core.
- Query throughput và transaction throughput.
- p50/p95/p99 latency.
- Tổng CPU hoặc worker time theo fingerprint nếu có.
- Calls và average cost.
- Planning/compile metrics.
- Logical reads, physical reads, rows examined.
- Lock waits, I/O waits, temp spill.
- Connection pool wait và query count/request.
- Write throughput và index maintenance cost.

### Kịch bản thử

1. Chạy workload ổn định dưới capacity.
2. Chạy burst có kiểm soát.
3. Thử các nhóm tham số nhỏ/lớn và hiếm/phổ biến.
4. So sánh query đơn lẻ với query mix.
5. Thử concurrency thực tế.
6. Warm cache và controlled cold-cache nếu phù hợp.
7. Chạy đủ lâu để quan sát cache, plan và background tasks.
8. Kiểm tra tính đúng của kết quả sau tối ưu.

### Chỉ số thành công

- CPU seconds trên mỗi request hoặc transaction giảm.
- Throughput hoàn tất tăng hoặc giữ nguyên với CPU thấp hơn.
- p95/p99 đạt SLO.
- Query count/request giảm khi xử lý N+1.
- Planning/compile cost giảm khi SQL shape ổn định.
- Rows examined và logical reads giảm khi access path tốt hơn.
- Không làm write latency, lock contention hoặc replication lag xấu đi.

Nếu CPU giảm nhưng latency tăng hoặc throughput giảm, cần xem có phải hệ thống đã bị điều tiết quá mức hay workload bị chuyển sang một bottleneck khác.

## 26. Các sai lầm thường gặp

- **Đồng nhất elapsed time với CPU time:** query chờ lock hoặc I/O có thể elapsed cao nhưng CPU thấp.
- **Chỉ nhìn CPU tổng:** không biết process hoặc query nào tiêu thụ.
- **Chỉ xếp hạng theo average:** bỏ qua query nhỏ có calls rất cao.
- **Chỉ xếp hạng theo total elapsed:** nhầm thời gian chờ thành CPU.
- **Thêm index ngay khi CPU cao:** index có thể tăng write CPU và cache footprint.
- **Tăng connection pool khi CPU đã bão hòa:** thêm concurrency có thể làm CPU scheduling và contention tăng.
- **Bật parallelism tối đa:** có thể làm một query nhanh hơn nhưng tổng CPU và p99 workload khác xấu đi.
- **Chỉ xem estimated plan:** bỏ qua actual rows và loops.
- **Không cập nhật statistics:** optimizer có thể chọn plan dựa trên phân bố cũ.
- **Dùng PreparedStatement nhưng giả định luôn cache plan:** hành vi phụ thuộc driver và engine.
- **Gộp mọi query thành một câu khổng lồ:** có thể làm plan và memory phức tạp.
- **Không phát hiện N+1:** từng query nhỏ trông nhanh nhưng tổng calls rất lớn.
- **Đo CPU database mà không đo application CPU:** có thể tối ưu sai tầng.
- **Chạy EXPLAIN ANALYZE trên lệnh ghi production:** có thể thay đổi dữ liệu và gây tải.
- **Thay nhiều yếu tố cùng lúc:** không biết thay đổi nào tạo kết quả.
- **Chỉ benchmark query đơn:** bỏ qua cạnh tranh và workload hỗn hợp.

## 27. Checklist khi database CPU cao

- Xác định CPU cao ở host, VM, container hay database process.
- Xác định CPU quota, throttling và số core thực sự được cấp.
- Ghi lại QPS/TPS, concurrency và thời điểm bắt đầu.
- Phân biệt CPU time, elapsed time, queue time và wait time.
- Xếp hạng query theo tổng CPU, CPU trung bình và số lần gọi.
- Dùng fingerprint/digest để nhóm SQL shape.
- Đo planning/compile nếu engine cung cấp.
- Tìm query có rows examined lớn, loops cao hoặc operator nặng.
- So sánh estimated rows với actual rows.
- Kiểm tra statistics, data skew và parameter distribution.
- Kiểm tra function trên cột, implicit conversion và predicate không SARGable.
- Tìm sort/hash, spill, regex, JSON và UDF tốn CPU.
- Kiểm tra parallel workers và runnable queue.
- Đếm query trên mỗi request để tìm N+1/chatty SQL.
- Kiểm tra PreparedStatement, plan reuse và statement cache theo driver.
- Đo connection pool wait và thời gian giữ connection.
- Benchmark một thay đổi mỗi lần với workload đại diện.
- Theo dõi p95/p99, throughput, CPU/request và chi phí ghi sau thay đổi.
- Ghi lại baseline, giả thuyết, kết quả và điều kiện rollback.

## Kết luận

CPU database cao cần được phân loại trước khi tối ưu. Một truy vấn tính toán nặng đòi hỏi đọc execution plan, cardinality, operator và access path. CPU lập kế hoạch tăng cần xem số SQL shape, parse/compile, statement reuse và plan cache. Quá nhiều truy vấn nhỏ cần xem calls, query count trên mỗi request, N+1, chatty SQL và cơ hội batching.

Hãy phân biệt CPU time với elapsed/wait time, xếp hạng cả tổng chi phí lẫn chi phí mỗi lần gọi, rồi liên kết fingerprint với execution plan và application trace. Tối ưu đúng nguyên nhân có thể giảm CPU trên mỗi request, tăng throughput và giữ tail latency ổn định. Mọi thay đổi cần được benchmark trong workload hỗn hợp để xác nhận rằng chi phí không chỉ chuyển sang I/O, lock, memory hoặc write path.
