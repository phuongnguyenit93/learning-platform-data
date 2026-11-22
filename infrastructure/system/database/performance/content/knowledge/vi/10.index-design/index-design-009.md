# Kiểm chứng chỉ mục mới bằng kế hoạch thực tế và tải đọc ghi hỗn hợp

Tạo được một chỉ mục mới chưa có nghĩa là hiệu năng hệ thống đã tốt hơn. Chỉ mục có thể giúp một câu SELECT đọc ít trang hơn, nhưng đồng thời làm INSERT, UPDATE và DELETE tốn thêm CPU, I/O, log và bộ nhớ. Một truy vấn có thể chạy nhanh trong thử nghiệm đơn lẻ nhưng chậm khi nhiều transaction đồng thời; một execution plan có Index Scan cũng chưa chắc nhanh hơn kế hoạch cũ dùng sequential scan.

Trong chương **Thiết kế chỉ mục**, bài học này trình bày cách kiểm chứng chỉ mục mới bằng kế hoạch thực tế và tải đọc ghi hỗn hợp. Đây là bước cần thiết trong phương pháp tối ưu của module **DATABASE_PERFORMANCE**: dùng đo đạc tải, execution plan, thống kê và hiểu biết về cơ chế truy cập dữ liệu để xác nhận thay đổi. Ta sẽ xây dựng baseline, đọc actual plan, đo lợi ích truy vấn đọc, đo write amplification, mô phỏng concurrency và đánh giá tác động lên toàn workload.

Mục tiêu là trả lời được ba câu hỏi trước khi chấp nhận một chỉ mục: truy vấn mục tiêu có thực sự được cải thiện không, các thao tác ghi và truy vấn khác bị ảnh hưởng thế nào, và kết quả có ổn định trên tải đại diện hay không?

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Thiết lập baseline có thể lặp lại trước khi tạo chỉ mục.
- Phân biệt estimated execution plan với actual execution plan và hiểu giới hạn của từng loại.
- Đọc actual rows, loops, buffer reads, I/O, sort, spill và thời gian thực thi để đánh giá tác động của index.
- Đo riêng hiệu năng đọc, ghi và transaction kết hợp.
- Giải thích write amplification và các nguồn chi phí phát sinh khi duy trì chỉ mục.
- Thiết kế benchmark với dữ liệu, tham số, cache state và concurrency đại diện.
- So sánh p50/p95/p99, throughput, CPU, I/O, lock wait và commit latency trước/sau.
- Xác minh kết quả truy vấn không đổi và xác định điều kiện chấp nhận, theo dõi hoặc hoàn nguyên chỉ mục.

## 1. Vì sao cần kiểm chứng chỉ mục sau khi tạo?

Một chỉ mục bổ sung thay đổi cấu trúc lưu trữ mà optimizer có thể lựa chọn. Sau khi index được tạo, DBMS có thêm một access path. Nhưng optimizer chỉ chọn nó nếu ước lượng chi phí thấp hơn các phương án khác. Kể cả khi index được chọn, truy vấn vẫn có thể phải truy cập nhiều trang bảng, thực hiện sort, lọc nhiều dòng hoặc chờ tài nguyên.

Chỉ mục còn tác động đến các thao tác ghi. Với mỗi dòng được thêm hoặc thay đổi, DBMS phải duy trì các index có liên quan. Một bảng có nhiều index có thể đọc nhanh hơn nhưng ghi chậm hơn. Khi tải hỗn hợp, phần tiết kiệm từ SELECT có thể bị bù trừ bởi chi phí ghi tăng thêm.

Ví dụ, một ứng dụng bán hàng có thể chạy đồng thời:

- SELECT trạng thái đơn hàng theo tenant và order_id.
- SELECT lịch sử đơn hàng theo tenant, trạng thái và thời gian.
- INSERT đơn hàng mới.
- INSERT chi tiết đơn hàng.
- UPDATE tồn kho và trạng thái đơn.
- DELETE hoặc archive dữ liệu cũ theo lô.

Nếu chỉ benchmark truy vấn lịch sử, index mới có thể trông rất hiệu quả. Nhưng nếu index chứa nhiều cột hoặc được cập nhật thường xuyên, throughput ghi có thể giảm. Cần kiểm tra trên workload đại diện, gồm cả thao tác đọc và ghi.

### 1.1. Ba cấp độ bằng chứng

| Cấp độ | Bằng chứng | Câu hỏi trả lời |
|---|---|---|
| Kế hoạch | Estimated/actual execution plan | DBMS đã chọn access path nào và xử lý bao nhiêu dòng? |
| Truy vấn | Latency, CPU, buffer/I/O, rows read | Truy vấn mục tiêu có thực sự chạy tốt hơn? |
| Toàn workload | Throughput, latency phân vị, ghi, lock và tài nguyên | Hệ thống tổng thể có cải thiện khi đọc/ghi đồng thời? |

Một kết quả đáng tin cậy cần cả ba cấp độ. Chỉ nhìn plan không chứng minh trải nghiệm người dùng tốt hơn; chỉ nhìn latency một truy vấn không cho biết hệ thống có bị giảm thông lượng ghi hay không.

## 2. Chuẩn bị phép đo trước khi tạo index

### 2.1. Chọn workload cần kiểm chứng

Bắt đầu từ các query fingerprint hoặc transaction nghiệp vụ đã được xếp hạng. Với mỗi nhóm, ghi:

- Tần suất chạy và tổng thời gian thực thi.
- p50, p95, p99 nếu có dữ liệu histogram hoặc tracing.
- SQL đã chuẩn hóa, kiểu tham số và các nhóm giá trị đại diện.
- Điều kiện WHERE, JOIN, ORDER BY, GROUP BY và cột kết quả.
- Số dòng ước lượng và số dòng thực tế.
- Buffer hit/read, physical I/O và dữ liệu tạm.
- Tần suất INSERT/UPDATE/DELETE trên bảng và các cột được index.
- Mức concurrency và tỷ lệ đọc/ghi trong workload.

Chỉ mục được đề xuất phải gắn với ít nhất một truy vấn hoặc ràng buộc cụ thể. Nếu không thể nêu rõ truy vấn nào cần cải thiện và chỉ số nào sẽ chứng minh cải thiện, chưa đủ cơ sở để tạo index.

### 2.2. Ghi nhận baseline

Baseline là bộ số liệu trước thay đổi. Hãy giữ điều kiện đủ rõ để có thể chạy lại sau khi tạo index.

| Nhóm số liệu | Nội dung cần ghi |
|---|---|
| Môi trường | DBMS, phiên bản, CPU, RAM, storage, cấu hình liên quan |
| Dữ liệu | Số dòng, kích thước bảng, phân bố giá trị, partition, index hiện có |
| Truy vấn | SQL/fingerprint, tham số, số lần chạy, latency |
| Execution plan | Plan đầy đủ, estimated rows, actual rows nếu có |
| Đọc | Logical/buffer reads, physical reads, rows examined, bytes |
| Ghi | Rows inserted/updated/deleted, log bytes, commit latency |
| Đồng thời | Active sessions, connection pool, lock wait, deadlock |
| Tải tổng thể | Throughput, p50/p95/p99, CPU, memory, I/O và queue depth |

Ghi thời điểm lấy snapshot và thời điểm reset counter. Bộ đếm thống kê thường tích lũy từ lúc DBMS khởi động hoặc reset gần nhất. So sánh số liệu tích lũy từ hai mốc không tương đương nếu khoảng thời gian và trạng thái reset khác nhau.

### 2.3. Giữ dữ liệu và tham số đại diện

Dữ liệu benchmark phải phản ánh quy mô và phân bố thực tế. Một bảng thử nghiệm nhỏ, đồng đều có thể làm index có vẻ tốt hơn production. Cần đưa vào:

- Tenant hoặc khách hàng có ít dữ liệu và tenant có rất nhiều dữ liệu.
- Giá trị trạng thái phổ biến và hiếm.
- Khoảng thời gian ngắn và dài.
- Khóa thường xuyên được truy cập và khóa ít được truy cập.
- Dòng có payload rộng, NULL hoặc dữ liệu có độ dài khác nhau.
- Tỷ lệ INSERT/UPDATE/DELETE gần với tải thực tế.

Nếu một truy vấn phụ thuộc tham số, hãy kiểm tra nhiều nhóm tham số thay vì chỉ một giá trị thuận lợi. Skew có thể làm optimizer chọn kế hoạch khác nhau hoặc tạo chênh lệch lớn về số dòng thực tế.

### 2.4. Kiểm soát cache state

Lần chạy đầu có thể đọc dữ liệu từ storage; các lần sau có thể lấy từ buffer cache hoặc cache của hệ điều hành. Vì vậy, so sánh một lần chạy lạnh trước khi tạo index với một lần chạy nóng sau khi tạo index sẽ dẫn đến kết luận sai.

Có thể đánh giá riêng:

- **Cold-cache behavior:** hệ thống chưa có working set trong cache, phản ánh một số tình huống khởi động hoặc dữ liệu ít dùng.
- **Warm-cache behavior:** dữ liệu thường dùng đã ở trong cache, phản ánh tải ổn định khi working set được tái sử dụng.
- **Mixed-cache behavior:** một phần dữ liệu nóng, một phần cần đọc từ storage; thường gần với vận hành thực tế.

Không xóa cache production chỉ để tạo điều kiện benchmark. Việc làm lạnh cache có thể gây ảnh hưởng lớn đến các phiên khác. Hãy dùng môi trường thử nghiệm hoặc phương pháp kiểm soát phù hợp.

## 3. Estimated plan và actual execution plan

### 3.1. Estimated plan

Estimated plan cho biết optimizer dự định thực thi truy vấn như thế nào dựa trên thống kê và mô hình chi phí. Nó có thể hiển thị:

- Scan type và index được chọn.
- Thứ tự JOIN và thuật toán JOIN.
- Estimated rows và estimated cost.
- Sort, aggregate, filter và các toán tử trung gian.
- Partition được dự kiến truy cập.

Estimated plan hữu ích để xem optimizer có nhận biết index mới và xem xét nó trong lựa chọn kế hoạch hay không. Nhưng estimated rows là dự đoán; nếu thống kê cũ hoặc dữ liệu lệch, số dòng thực tế có thể khác xa.

### 3.2. Actual execution plan

Actual plan bổ sung dữ liệu từ lần thực thi, tùy DBMS có thể gồm actual rows, loops, thời gian, số trang đọc, số worker và dữ liệu tạm. Nó cho biết truy vấn đã thực sự làm gì trên lần chạy được đo.

Các chỉ số quan trọng:

- **Actual rows:** số dòng thực tế đi qua hoặc được tạo bởi toán tử.
- **Estimated rows:** số dòng optimizer dự đoán.
- **Loops:** số lần toán tử được thực hiện.
- **Actual time/elapsed:** thời gian theo định nghĩa của DBMS.
- **Buffers/reads:** số lần truy cập trang trong cache hoặc đọc vào buffer.
- **Temp I/O:** dữ liệu tạm được đọc/ghi khi sort hoặc hash không vừa bộ nhớ.
- **Rows removed by filter:** số dòng bị loại sau khi đã được đọc hoặc chuyển đến toán tử.
- **Workers/parallelism:** số worker thực tế và mức cân bằng công việc.

Không cộng trực tiếp thời gian của mọi node trong plan để suy ra thời gian truy vấn nếu các node chạy pipeline hoặc song song. Cần hiểu cách DBMS báo thời gian và loops.

### 3.3. So sánh estimated rows với actual rows

Nếu optimizer ước lượng một điều kiện trả về 100 dòng nhưng actual rows là 200.000, plan có thể được chọn dựa trên giả định sai. Chênh lệch lớn có thể đến từ:

- Thống kê chưa được cập nhật.
- Phân bố dữ liệu lệch hoặc tương quan giữa nhiều cột.
- Giá trị tham số không đại diện.
- Biểu thức hoặc kiểu dữ liệu làm giảm chất lượng ước lượng.
- Dữ liệu thay đổi mạnh sau lần thu thập thống kê.

Chỉ mục mới không tự sửa mọi vấn đề ước lượng. Sau khi tạo index, hãy kiểm tra statistics và actual rows. Nếu cần cập nhật thống kê, hãy thực hiện theo cơ chế của DBMS và quy trình vận hành.

## 4. Đọc execution plan để xác nhận index có tác dụng

### 4.1. Index được chọn có đúng access path không?

Sau khi tạo index, plan có thể cho thấy Index Seek, Index Scan, Index Only Scan hoặc tên toán tử tương ứng. Cần xem:

- Index nào được dùng?
- Những cột nào tham gia seek hoặc index condition?
- Predicate nào vẫn chỉ được đánh giá ở bước filter?
- Có phải truy cập bảng để lấy thêm cột không?
- Số dòng và số trang thực tế giảm bao nhiêu?
- Có sort bổ sung hay không?

Một plan sử dụng index chưa chắc đã tốt. Nếu truy vấn cần 70% số dòng của bảng, index scan cộng hàng loạt table lookup có thể tốn kém hơn sequential scan. Mục tiêu là giảm tổng chi phí, không phải buộc optimizer dùng index.

### 4.2. Index seek và index scan

Index seek thường tìm một vùng khóa xác định; index scan đọc một phần hoặc toàn bộ leaf entries. Tên gọi và semantics cụ thể tùy DBMS. Index scan có thể hoàn toàn hợp lý nếu cần đọc phần lớn index hoặc index nhỏ hơn bảng.

Hãy so sánh số entry được duyệt, số dòng được trả về, số lần truy cập bảng và I/O. Không dùng nhãn seek/scan làm tiêu chí duy nhất.

### 4.3. Covering và truy cập bảng

Nếu truy vấn cần cột không có trong index, DBMS có thể phải truy cập bảng để lấy các giá trị còn thiếu. Trong SQL Server, plan có thể cho thấy Key Lookup hoặc RID Lookup; trong các DBMS khác, plan có thể hiển thị table access hoặc heap fetch.

Covering index có thể giảm các lần truy cập này, nhưng tăng kích thước index và chi phí ghi. Sau khi thêm INCLUDE hoặc cột bao phủ, hãy đo:

- Số lần lookup vào bảng giảm bao nhiêu?
- Buffer reads và physical reads thay đổi thế nào?
- Kích thước index tăng bao nhiêu?
- INSERT/UPDATE có chậm hơn không?
- Cache pressure có tăng không?

Trong PostgreSQL, Index Only Scan còn phụ thuộc visibility map và tình trạng vacuum; node có thể vẫn cần heap fetch. Vì vậy, tên Index Only Scan chưa đủ để kết luận không còn truy cập heap.

### 4.4. Sort và thứ tự index

Index có thứ tự phù hợp có thể giúp DBMS trả kết quả theo ORDER BY mà không cần sort riêng. Kiểm tra plan xem Sort node có biến mất hay giảm số dòng phải sắp xếp không.

Với ORDER BY nhiều cột, chiều ASC/DESC, NULL ordering và tie-breaker, thứ tự index cần khớp yêu cầu. Một index chỉ có prefix phù hợp có thể vẫn cần sort phần còn lại. Nếu truy vấn dùng LIMIT, index có thể cho phép dừng sớm sau khi lấy đủ dòng; đây thường là lợi ích lớn với danh sách mới nhất.

### 4.5. JOIN và thứ tự truy cập

Index trên khóa join có thể giảm chi phí tìm dòng ở phía trong của nested loop. Nhưng nếu đầu vào ngoài lớn, số lần lookup có thể rất cao. Hash join hoặc merge join có thể tốt hơn cho tập dữ liệu lớn.

Khi index mới làm thay đổi plan, hãy xem:

- Số dòng đầu vào của mỗi phía JOIN.
- Actual loops của nested loop.
- Số lần lookup vào index và bảng.
- Hash table có spill không?
- Có sort lớn để phục vụ merge join không?
- Tổng thời gian và I/O của toàn truy vấn.

### 4.6. Partition pruning và phạm vi truy cập

Nếu bảng được partition, index cục bộ trong từng partition có thể giúp tìm dòng sau khi DBMS loại bỏ partition không liên quan. Kiểm tra plan xem bao nhiêu partition được truy cập, có partition pruning hay không và index có được dùng trong các partition đó không.

Index mới trong từng partition có thể tăng dung lượng và chi phí bảo trì. Benchmark phải phản ánh số partition thường được truy cập và phân bố dữ liệu theo partition.

## 5. Ví dụ kiểm tra actual plan

### 5.1. PostgreSQL

Với PostgreSQL, có thể dùng:

~~~sql
EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
SELECT order_id, created_at, total
FROM orders
WHERE tenant_id = 42
  AND status = 'PAID'
ORDER BY created_at DESC
LIMIT 50;
~~~

Các trường cần quan sát:

- Planning Time: thời gian lập kế hoạch.
- Execution Time: thời gian thực thi theo cách PostgreSQL đo.
- actual rows và loops: số dòng và số lần lặp thực tế.
- Buffers: shared/local/temp blocks hit, read, dirtied hoặc written.
- Index Cond: điều kiện được dùng để truy cập index.
- Filter và Rows Removed by Filter: điều kiện lọc sau access path.
- Heap Fetches: số lần phải truy cập heap trong một số dạng Index Only Scan.

EXPLAIN ANALYZE thực sự chạy câu lệnh. Với SELECT nặng, nó tạo tải thật; với INSERT/UPDATE/DELETE, nó có thể thay đổi dữ liệu. Chỉ thực hiện trên môi trường phù hợp và có kế hoạch an toàn. Có thể thêm WAL option ở phiên bản hỗ trợ để xem thông tin WAL của các thao tác ghi, nhưng không dùng điều này như phép đo đầy đủ cho workload production.

### 5.2. MySQL

Trên MySQL 8.0.18 trở lên, EXPLAIN ANALYZE cung cấp actual timing và row counts cho truy vấn SELECT:

~~~sql
EXPLAIN ANALYZE
SELECT order_id, created_at, total
FROM orders
WHERE tenant_id = 42
  AND status = 'PAID'
ORDER BY created_at DESC
LIMIT 50;
~~~

Kết quả dùng iterator tree. Quan sát số dòng thực tế, số vòng lặp, thời gian iterator và khác biệt với ước lượng. Để xem lựa chọn index và access type, có thể dùng EXPLAIN dạng truyền thống hoặc JSON tùy phiên bản.

Không suy diễn rằng mọi phiên bản MySQL hỗ trợ cùng cú pháp hoặc cùng chỉ số. Kiểm tra tài liệu phiên bản đang triển khai; EXPLAIN ANALYZE thực thi truy vấn và có thể tiêu tốn tài nguyên tương tự việc chạy SELECT.

### 5.3. SQL Server

Trong SQL Server, Actual Execution Plan hiển thị số dòng thực tế, số lần thực hiện, lookup, scan, seek, sort, spill và các cảnh báo khác. Có thể kết hợp với:

~~~sql
SET STATISTICS IO ON;
SET STATISTICS TIME ON;

SELECT order_id, created_at, total
FROM dbo.orders
WHERE tenant_id = 42
  AND status = 'PAID'
ORDER BY created_at DESC
OFFSET 0 ROWS FETCH NEXT 50 ROWS ONLY;

SET STATISTICS IO OFF;
SET STATISTICS TIME OFF;
~~~

Các thiết lập thống kê áp dụng cho phiên hiện tại. Kết quả cần được đối chiếu với actual plan và số đo ứng dụng. Không chỉ nhìn estimated subtree cost hoặc phần trăm cost trong graphical plan vì đó là ước lượng tương đối, không phải thời gian thực tế.

## 6. Đo lợi ích cho workload đọc

### 6.1. Chọn chỉ số đọc

Với từng query fingerprint, đo cùng điều kiện trước và sau:

- Calls hoặc số lần chạy trong khoảng.
- p50/p95/p99 latency.
- Mean và total execution time.
- Rows examined/read và rows returned.
- Logical/buffer reads.
- Physical reads và storage latency.
- CPU time.
- Sort, temp reads/writes và spill.
- Số bytes trả về và time to last row nếu client đọc tập kết quả lớn.

Nếu index được tạo cho một query hiếm nhưng quan trọng, vẫn cần đo thời gian hoàn tất và mức độ đáp ứng mục tiêu nghiệp vụ. Không chỉ dựa vào số lần chạy.

### 6.2. Đo cả query và transaction

Một query riêng lẻ có thể nhanh hơn nhưng transaction tổng thể không nhanh hơn nếu các bước khác chiếm phần lớn thời gian. Ví dụ transaction đặt hàng đọc sản phẩm, kiểm tra tồn kho, ghi đơn hàng, cập nhật tồn và commit. Index mới có thể giảm một SELECT nhưng làm UPDATE chậm hơn.

Đo cả transaction duration, thời gian giữ khóa, commit latency và retry rate. Đây là thước đo gần với hành vi ứng dụng hơn so với chỉ đo một câu SQL.

### 6.3. Đánh giá mức giảm công việc

Ví dụ giả định trước/sau:

| Chỉ số của query lịch sử | Trước index | Sau index |
|---|---:|---:|
| Mean latency | 180 ms | 32 ms |
| p95 latency | 420 ms | 75 ms |
| Shared buffer reads | 18.000 | 1.900 |
| Actual rows đọc ở scan | 120.000 | 1.100 |
| Sort rows | 120.000 | 0 |
| Rows returned | 50 | 50 |

Số liệu này minh họa cách đánh giá, không phải kết quả của một DBMS cụ thể. Lợi ích được củng cố khi plan cho thấy phạm vi truy cập nhỏ hơn, sort được loại bỏ và số buffer reads giảm. Tuy nhiên, vẫn phải đánh giá chi phí ghi và toàn workload.

## 7. Đo write amplification và chi phí duy trì index

### 7.1. Write amplification là gì?

Write amplification mô tả lượng công việc ghi phát sinh ở tầng lưu trữ hoặc DBMS so với lượng thay đổi logic mà ứng dụng yêu cầu. Trong bối cảnh index, một INSERT một dòng có thể làm phát sinh cập nhật ở bảng và nhiều cấu trúc index; một UPDATE có thể thay đổi entry trong một hoặc nhiều index; tất cả còn có thể tạo log và page split.

Khái niệm này có thể được đo theo nhiều cách tùy tầng:

- Số block hoặc page được ghi.
- Số byte transaction log/WAL.
- Số I/O ghi ở storage.
- CPU time cho thao tác ghi.
- Số entry index được thêm, xóa hoặc thay đổi.
- Thời gian commit và replication traffic.

Không có một counter write amplification thống nhất cho mọi DBMS. Hãy chọn các chỉ số hệ thống thực sự cung cấp và so sánh cùng khoảng tải.

### 7.2. Những thao tác ghi cần thử

Đừng chỉ benchmark INSERT. Index mới có thể tác động khác nhau lên:

- INSERT dòng mới.
- UPDATE cột không thuộc index.
- UPDATE cột key của index.
- UPDATE cột INCLUDE hoặc cột được lưu trong index.
- DELETE một dòng.
- DELETE/UPDATE theo phạm vi lớn.
- UPSERT hoặc thao tác kiểm tra unique constraint.
- Ghi theo batch và transaction nhiều dòng.

Nếu index có predicate, một dòng có thể đi vào hoặc ra khỏi index khi trạng thái thay đổi. Đây vẫn là chi phí duy trì cần đo.

### 7.3. Số index và độ rộng index

Mỗi index bổ sung có thể làm tăng:

- Kích thước database và backup.
- Số trang cạnh tranh trong buffer cache.
- CPU và I/O khi ghi.
- Lượng WAL/transaction log.
- Thời gian tạo và bảo trì.
- Khả năng xảy ra page split và contention.

Một index ghép rộng hoặc covering index có thể tăng kích thước đáng kể. Cần đo kích thước trước/sau và quan sát cache hit, eviction, I/O. Đừng chỉ xem truy vấn mục tiêu.

### 7.4. Chỉ mục và cập nhật không làm thay đổi key

Một số DBMS có thể tránh cập nhật index nếu các cột key hoặc included columns không đổi; cơ chế cụ thể phụ thuộc engine. PostgreSQL có HOT update trong một số điều kiện, nhưng index mới trên cột được cập nhật có thể làm giảm khả năng HOT cho các dòng liên quan. SQL Server, MySQL/InnoDB và các engine khác có cơ chế bảo trì riêng.

Vì vậy, khi đo UPDATE, phải mô phỏng đúng những cột mà ứng dụng thay đổi. Benchmark chỉ cập nhật một cột không liên quan có thể đánh giá thấp chi phí của index mới.

### 7.5. Page split và contention

Index có khóa tăng dần có thể tập trung insert vào vùng cuối; khóa ngẫu nhiên có thể phân tán vị trí ghi nhưng tăng truy cập ngẫu nhiên và page split. Một số DBMS cung cấp wait events, page split counters hoặc thống kê index để điều tra. Cần xem mức đồng thời, cấu trúc khóa và wait thực tế trước khi kết luận.

## 8. Benchmark tải đọc ghi hỗn hợp

### 8.1. Vì sao benchmark riêng lẻ chưa đủ?

Benchmark chỉ SELECT trả lời index có giúp một truy vấn đọc không. Benchmark chỉ INSERT cho biết chi phí ghi ở một mẫu. Nhưng production thường có nhiều luồng cùng chạy: đọc lịch sử, tạo đơn, cập nhật tồn kho và tác vụ nền.

Khi chạy đồng thời, các luồng chia sẻ CPU, RAM, buffer cache, storage bandwidth, connection pool và khóa. Một index mới có thể giảm I/O đọc nhưng tăng I/O ghi; hai thay đổi này tương tác với nhau. Tải hỗn hợp mới cho biết hiệu quả tổng thể.

### 8.2. Xác định tỷ lệ đọc/ghi

Bắt đầu bằng cách đo tỷ lệ thực tế theo transaction hoặc statement. Ví dụ một workload thử nghiệm có thể gồm:

- 70% transaction đọc.
- 20% transaction ghi mới.
- 10% transaction cập nhật.

Đây chỉ là tỷ lệ minh họa. Dùng tỷ lệ production hoặc mô hình tải đã được nghiệp vụ xác nhận. Ngoài tỷ lệ, cần giữ kích thước transaction và phân bố thao tác tương đương.

### 8.3. Mô phỏng concurrency

Chạy benchmark ở nhiều mức đồng thời, ví dụ 1, 8, 16, 32 và 64 client nếu tài nguyên thử nghiệm cho phép. Mục tiêu là tìm điểm throughput bắt đầu bão hòa và xem p95/p99 tăng như thế nào.

Không chỉ tăng số client rồi lấy kết quả cao nhất. Cần quan sát:

- Throughput read và write riêng.
- Tổng transaction throughput.
- p95/p99 của transaction.
- CPU utilization và run queue.
- Storage latency, IOPS, throughput và queue depth.
- Connection pool wait.
- Lock wait, deadlock và retry.
- Buffer cache pressure và temporary I/O.

Nếu concurrency tăng nhưng throughput gần như không tăng, trong khi latency tăng mạnh, hệ thống có thể đã đạt điểm bão hòa.

### 8.4. Burst và thời gian chạy

Nếu production có giờ cao điểm hoặc batch job, hãy mô phỏng burst thay vì chỉ chạy tải đều. Chạy đủ lâu để cache và background maintenance đi vào trạng thái ổn định. Một bài test 30 giây có thể bỏ qua checkpoint, vacuum, purge, log flush hoặc các tác vụ nền khác.

Không chạy benchmark nặng trên production nếu chưa có kế hoạch được phê duyệt. Dùng staging có dữ liệu và tài nguyên tương đồng, hoặc công cụ replay có giới hạn tốc độ và kiểm soát tác động.

### 8.5. Đo riêng từng nhóm và toàn bộ

Kết quả benchmark cần phân tách:

| Nhóm | Chỉ số chính |
|---|---|
| Read queries | p50/p95/p99, rows read, buffer reads |
| Insert | rows/s, latency, log bytes |
| Update | latency, lock wait, index maintenance |
| Delete/batch | thời gian hoàn tất, log, lock duration |
| Transaction hỗn hợp | transaction/s, p95/p99, lỗi/retry |
| Toàn DBMS | CPU, RAM, I/O, cache, connections |

Tách số liệu giúp biết nhóm nào được lợi và nhóm nào chịu chi phí. Nếu chỉ có tổng throughput, một nhóm đọc tăng mạnh có thể che giấu nhóm ghi bị giảm.

## 9. Ví dụ xuyên suốt: chỉ mục cho lịch sử đơn hàng

Giả sử API lấy 50 đơn PAID mới nhất của một tenant:

~~~sql
SELECT order_id, created_at, total
FROM orders
WHERE tenant_id = 42
  AND status = 'PAID'
ORDER BY created_at DESC
LIMIT 50;
~~~

Một index được đề xuất:

~~~sql
CREATE INDEX idx_orders_tenant_status_created
ON orders (tenant_id, status, created_at DESC);
~~~

Có thể bổ sung cột bao phủ tùy DBMS và kết quả đo. Trước khi chấp nhận, thiết kế phép kiểm chứng như sau.

### 9.1. Baseline truy vấn đọc

Chạy query với tenant nhỏ, trung bình và rất lớn. Lưu estimated/actual rows, plan, buffer reads, sort, latency và số dòng trả về. Ghi cả lần chạy cache nóng và tải có concurrency đại diện.

### 9.2. Xác minh actual plan sau index

Sau khi tạo index và cập nhật thống kê theo quy trình phù hợp, chạy lại cùng tham số. Kiểm tra optimizer có dùng index, có giảm rows scanned, có loại bỏ sort và có giảm table lookup không.

Nếu plan vẫn scan toàn bảng, hãy kiểm tra điều kiện, thống kê, tỷ lệ chọn lọc và chi phí optimizer. Không ép dùng index chỉ để thấy tên index xuất hiện trong plan.

### 9.3. Đo ghi trên cùng bảng

Trong khi chạy read workload, mô phỏng:

~~~sql
INSERT INTO orders
    (order_id, tenant_id, status, created_at, total)
VALUES
    (990001, 42, 'PENDING', CURRENT_TIMESTAMP, 125.00);

UPDATE orders
SET status = 'PAID'
WHERE order_id = 990001;

DELETE FROM orders
WHERE order_id = 990001;
~~~

Đây là ví dụ thao tác, không phải script benchmark hoàn chỉnh. Benchmark cần nhiều khóa và transaction phù hợp, đồng thời dọn dữ liệu thử nghiệm an toàn. Vì status nằm trong index, UPDATE status có thể phải thay đổi entry index. Đo thời gian, log bytes, I/O, throughput và lock wait.

### 9.4. Chạy tải hỗn hợp

Chạy song song API đọc lịch sử với transaction tạo đơn và cập nhật trạng thái. So sánh trước/sau:

- Read p95/p99 có giảm không?
- Insert/update throughput có giảm không?
- Commit latency có tăng không?
- CPU và storage queue có thay đổi không?
- Lock wait và deadlock có tăng không?
- Các query khác trên orders có bị plan regression không?

Chỉ mục có thể được chấp nhận nếu lợi ích đọc đủ lớn so với chi phí ghi và mục tiêu SLA toàn hệ thống vẫn được đáp ứng.

## 10. Kiểm soát tính đúng đắn và tính công bằng của phép thử

### 10.1. Kết quả phải giống nhau

Index không được làm thay đổi kết quả logic. So sánh số dòng, giá trị, duplicate, NULL và thứ tự nếu có ORDER BY. Đặc biệt kiểm tra các trường hợp biên như tenant không có đơn, status NULL, timestamp trùng và giá trị ở ranh giới thời gian.

### 10.2. So sánh cùng điều kiện

Trước và sau phải dùng:

- Cùng snapshot hoặc cùng tập dữ liệu.
- Cùng tham số và phân bố tham số.
- Cùng mức concurrency và tỷ lệ read/write.
- Cùng cache state hoặc đo riêng các trạng thái cache.
- Cùng thời lượng warm-up và đo.
- Cùng cấu hình tài nguyên và các tác vụ nền.
- Cùng phiên bản DBMS và driver.

Nếu thay đổi nhiều yếu tố cùng lúc, không thể xác định index tạo ra bao nhiêu lợi ích.

### 10.3. Lặp lại và dùng phân vị

Chạy nhiều vòng, bỏ qua giai đoạn warm-up nếu không thuộc phạm vi đo, và so sánh p50/p95/p99. Một lần chạy nhanh bất thường không đủ chứng minh. Ghi lại cả biến thiên giữa các lần chạy.

Nếu hệ thống dùng connection pool, phải giữ cấu hình pool tương đương. Nếu benchmark mở một kết nối mới cho mỗi query trong khi production dùng pool, kết quả sẽ không đại diện.

### 10.4. Tránh benchmark chỉ với cache nóng

Nếu cùng một tập nhỏ được lặp lại, working set có thể nằm hoàn toàn trong RAM. Index mới có thể có vẻ rất nhanh nhưng không phản ánh phân bố truy cập rộng. Dùng tham số và khóa có phân bố thực tế, bao gồm những vùng dữ liệu ít được truy cập.

## 11. Theo dõi index sau khi triển khai

Một index có thể hữu ích lúc đầu nhưng ít được dùng sau khi workload thay đổi. Cần theo dõi:

- Số lần index được scan hoặc seek.
- Số tuple/row được đọc qua index.
- Kích thước index và tốc độ tăng.
- Số lần ghi và chi phí bảo trì.
- Buffer hit/read và cache residency nếu có.
- Page split, fragmentation hoặc bloat theo cơ chế DBMS.
- Query plan và latency của fingerprint liên quan.
- Tác động lên replica, backup và replication lag.

Thống kê index usage có thể reset khi restart hoặc reset counter. Index không được dùng trong khoảng quan sát ngắn chưa chắc dư thừa; có thể query chỉ chạy theo tháng hoặc theo mùa vụ. Hãy dùng khoảng quan sát đủ dài và kiểm tra các job định kỳ.

## 12. Triển khai an toàn và phương án hoàn nguyên

### 12.1. Xây dựng index trong môi trường phù hợp

Tạo index trên bảng lớn có thể tiêu thụ I/O, CPU, storage tạm và ảnh hưởng đến concurrency. Một số DBMS hỗ trợ online hoặc concurrent index build với giới hạn riêng. PostgreSQL có CREATE INDEX CONCURRENTLY nhưng có các ràng buộc vận hành và có thể để lại index invalid nếu thao tác thất bại. SQL Server và MySQL có các tùy chọn online/in-place DDL phụ thuộc phiên bản, engine và loại thay đổi.

Trước khi triển khai, xác nhận:

- Thời gian build ước tính và dung lượng cần thêm.
- DDL có khóa bảng hoặc hạn chế ghi không.
- Có hỗ trợ concurrent/online cho đúng loại index không.
- Tác động lên replication và backup.
- Cách phát hiện build thất bại hoặc index invalid.
- Quy trình hủy, retry hoặc dọn index lỗi.
- Cửa sổ triển khai và điều kiện dừng.

Không giả định từ khóa ONLINE hoặc CONCURRENTLY có cùng semantics giữa các DBMS.

### 12.2. Đặt tiêu chí chấp nhận trước

Ví dụ tiêu chí cho một index phục vụ API:

- p95 truy vấn mục tiêu giảm ít nhất mức đã thống nhất.
- p99 không xấu đi đáng kể ở tenant lớn.
- Throughput insert/update không giảm quá ngân sách cho phép.
- Commit latency và lock wait vẫn trong SLO.
- CPU và storage queue không tăng đến điểm bão hòa.
- Kết quả SQL giữ nguyên.
- Các query fingerprint quan trọng khác không bị regression.

Ngưỡng cụ thể phải do yêu cầu dịch vụ và baseline quyết định, không có một phần trăm chung cho mọi hệ thống.

### 12.3. Theo dõi sau khi bật tải thật

Sau khi triển khai, quan sát trong giờ thấp điểm và giờ cao điểm. So sánh cùng khoảng thời gian hoặc cùng chu kỳ nghiệp vụ. Kiểm tra cả latency truy vấn mục tiêu lẫn throughput ghi, replication lag, cache và lỗi.

### 12.4. Hoàn nguyên

Nếu chỉ mục làm hệ thống xấu đi, có thể cần loại bỏ index hoặc điều chỉnh thiết kế. Trước khi drop, xác định query nào đang dùng index, có ràng buộc uniqueness/constraint phụ thuộc không và DBMS có yêu cầu khóa hoặc thời gian thực hiện nào. Việc drop cũng là một DDL cần được lên kế hoạch.

Không xóa index chỉ vì một lần benchmark không tốt. Xác minh lỗi do index, do cache state, thống kê, tham số, concurrency hoặc môi trường trước khi hoàn nguyên.

## 13. Cách đọc kết quả và ra quyết định

Bảng dưới đây minh họa cách diễn giải các kết quả thường gặp:

| Kết quả sau khi tạo index | Diễn giải có thể có | Việc cần làm |
|---|---|---|
| Query latency giảm, reads giảm, write gần như không đổi | Index hỗ trợ access path hiệu quả với chi phí thấp | Xác nhận trên workload hỗn hợp và theo dõi |
| Query latency giảm nhưng write throughput giảm mạnh | Index tạo write amplification đáng kể | Cân nhắc index hẹp hơn, partial index hoặc bỏ index |
| Plan dùng index nhưng latency không giảm | Nhiều table lookup, selectivity thấp, cache/I/O hoặc wait vẫn cao | Xem actual rows, loops, buffers và wait |
| Estimated rows sai xa actual rows | Thống kê hoặc skew chưa được mô tả tốt | Kiểm tra/cập nhật thống kê và tham số |
| Read nhanh hơn nhưng p99 transaction xấu đi | Ghi, khóa hoặc tài nguyên dùng chung bị ảnh hưởng | Phân tích transaction, lock và tải hỗn hợp |
| Index không được chọn | Không phù hợp chi phí, predicate hoặc thống kê | Xem query pattern và plan; không ép dùng máy móc |
| Buffer reads giảm nhưng storage I/O không đổi | Dữ liệu có thể đã nằm trong cache hoặc cache tầng khác | Đối chiếu OS/storage metrics và trạng thái cache |
| Index size tăng lớn, usage thấp | Index có thể quá rộng hoặc không phục vụ workload | Theo dõi đủ chu kỳ và đánh giá lại thiết kế |

Không có một dấu hiệu đơn lẻ quyết định kết luận. Hãy ghép plan, query metrics, system metrics và transaction behavior trong cùng khoảng thời gian.

## 14. Những sai lầm thường gặp khi kiểm chứng index

**Chỉ xem index có xuất hiện trong plan.** Plan có index access vẫn có thể thực hiện hàng nghìn lookup hoặc đọc nhiều trang. Cần xem actual rows, loops, buffers và latency.

**Chỉ đo SELECT.** Index làm tăng chi phí ghi. Tải hỗn hợp mới cho biết lợi ích ròng.

**Dùng dữ liệu nhỏ và đồng đều.** Kết quả không phản ánh skew, working set hoặc cardinality production.

**So sánh cache nóng với cache lạnh.** Khác biệt cache làm sai kết luận.

**Chỉ lấy thời gian trung bình.** Mean có thể che giấu p95/p99 và các tham số gây tail latency.

**Tăng concurrency mà không đo throughput.** Latency tăng khi hệ thống bão hòa có thể bị nhầm là index kém.

**Bỏ qua write amplification.** Log bytes, I/O, page split và chi phí cập nhật index có thể làm giảm hiệu năng tổng thể.

**Reset thống kê ngay trước khi thu baseline mà không lưu snapshot.** Mất dữ liệu lịch sử khiến việc so sánh và điều tra khó khăn.

**Chấp nhận kết quả từ một lần chạy.** Cache, checkpoint, background jobs và tải khác có thể làm số đo biến động.

**Không có kế hoạch hoàn nguyên.** Index mới có thể gây regression sau khi workload thay đổi hoặc tải cao hơn dự kiến.

## 15. Checklist kiểm chứng chỉ mục mới

- [ ] Đã xác định query fingerprint và workload nghiệp vụ cần cải thiện chưa?
- [ ] Đã lưu baseline về plan, latency, rows, buffers, CPU và I/O chưa?
- [ ] Đã chuẩn bị dữ liệu và tham số có phân bố đại diện chưa?
- [ ] Đã kiểm soát cache state và thời gian warm-up chưa?
- [ ] Đã thu actual execution plan sau khi tạo index chưa?
- [ ] Đã so sánh estimated rows với actual rows và loops chưa?
- [ ] Đã xác nhận index condition, table lookup, sort và partition pruning chưa?
- [ ] Đã đo p50/p95/p99 và throughput của truy vấn đọc chưa?
- [ ] Đã đo INSERT, UPDATE, DELETE, log bytes và commit latency chưa?
- [ ] Đã chạy workload đọc/ghi đồng thời ở nhiều mức concurrency chưa?
- [ ] Đã kiểm tra CPU, memory, I/O, lock wait, deadlock và connection pool chưa?
- [ ] Đã xác minh kết quả truy vấn giống nhau trước/sau chưa?
- [ ] Đã đánh giá tác động đến các query fingerprint khác chưa?
- [ ] Đã đặt tiêu chí chấp nhận và phương án hoàn nguyên chưa?
- [ ] Đã có kế hoạch theo dõi sau triển khai chưa?

## Kết luận

Kiểm chứng chỉ mục mới phải kết hợp execution plan thực tế với đo tải đọc và ghi hỗn hợp. Actual plan cho biết DBMS đã dùng index ra sao, bao nhiêu dòng được xử lý, có phải truy cập bảng, sort hoặc spill hay không. Benchmark đọc cho biết truy vấn mục tiêu có nhanh hơn; benchmark ghi cho biết chi phí duy trì index; tải hỗn hợp cho thấy lợi ích ròng khi nhiều transaction cùng sử dụng tài nguyên.

Một chỉ mục chỉ nên được chấp nhận khi kết quả SQL được bảo toàn, truy vấn quan trọng cải thiện trên tham số đại diện, chi phí ghi vẫn nằm trong ngân sách và các mục tiêu toàn hệ thống được duy trì. Hãy giữ baseline, so sánh trong điều kiện tương đương, đo phân vị và throughput, rồi tiếp tục theo dõi sau triển khai. Đó là cách biến một index mới thành một thay đổi hiệu năng có bằng chứng.

