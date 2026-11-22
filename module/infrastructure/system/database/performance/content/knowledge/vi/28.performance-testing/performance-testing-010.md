# Lập báo cáo kết quả gồm mục tiêu, điều kiện, số liệu và giới hạn

Kiểm thử hiệu năng cơ sở dữ liệu chỉ có giá trị khi kết quả có thể được giải thích, so sánh và tái lập. Một con số như “truy vấn nhanh hơn 30%” chưa đủ để quyết định thay đổi có nên đưa lên production hay không. Người đọc cần biết truy vấn nào được đo, tải được tạo ra ra sao, dữ liệu có quy mô và phân bố thế nào, hệ thống chạy trong điều kiện nào, số liệu được thu thập bằng cách nào và kết quả còn giới hạn gì.

Báo cáo kết quả kiểm thử hiệu năng là hồ sơ kỹ thuật ghi lại mục tiêu, giả thuyết, phạm vi, môi trường, workload, phương pháp đo, số liệu, phân tích, giới hạn và khuyến nghị. Báo cáo phải giúp người khác trả lời được ba câu hỏi: phép đo có đại diện cho workload cần phục vụ không, kết quả có đủ tin cậy để đưa ra quyết định không, và thay đổi nào cần thực hiện tiếp theo.

Trong phạm vi DATABASE_PERFORMANCE, báo cáo cần liên kết số liệu tải với kế hoạch thực thi, thống kê optimizer, chỉ mục, đường đọc/ghi, tranh chấp giao dịch, bộ nhớ, I/O và replication. Mục tiêu là biến dữ liệu đo được thành quyết định tối ưu có thể kiểm chứng, thay vì chỉ ghi lại một bảng latency hoặc một ảnh chụp dashboard.

## 1. Vai trò của báo cáo hiệu năng

Báo cáo là cầu nối giữa phép thử và quyết định kỹ thuật. Nó có thể được dùng để:

- Xác nhận một thay đổi SQL, index, schema hoặc cấu hình có cải thiện workload mục tiêu.
- So sánh hai phương án thiết kế dưới cùng điều kiện.
- Xác định giới hạn năng lực hiện tại và điểm bão hòa.
- Đánh giá ảnh hưởng của tải đọc, ghi, transaction contention, I/O và bộ nhớ.
- Xác nhận hệ thống đáp ứng SLO/SLA đã thống nhất.
- Ghi lại rủi ro, điều kiện áp dụng và việc cần đo tiếp.
- Cung cấp bằng chứng cho review, triển khai, capacity planning hoặc rollback.

Một báo cáo tốt không chỉ nêu kết quả tốt. Nếu phép thử thất bại, kết quả không ổn định hoặc thay đổi không cải thiện, báo cáo vẫn hữu ích khi chỉ rõ điều kiện, số liệu và nguyên nhân có thể.

### Phân biệt kết quả đo và kết luận

**Kết quả đo** là dữ liệu quan sát được: p95 latency, throughput, CPU, I/O wait, lock wait, số lỗi, số transaction/giây hoặc số hàng đọc.

**Kết luận** là cách diễn giải kết quả trong phạm vi mục tiêu: truy vấn đạt p95 dưới 100 ms ở 250 request/giây; throughput không tăng thêm khi CPU đạt gần mức bão hòa; hoặc index mới giảm logical reads nhưng làm tăng thời gian ghi.

**Khuyến nghị** là hành động dựa trên kết luận: triển khai có điều kiện, điều chỉnh batch size, cập nhật statistics, sửa predicate, giảm concurrency hoặc thực hiện thêm một phép thử.

Không trình bày suy đoán như số đo. Nếu chưa xác định được nguyên nhân, hãy ghi “nguyên nhân chưa được xác nhận” và nêu phép đo tiếp theo cần thiết.

## 2. Xác định mục tiêu và câu hỏi kiểm thử

Trước khi chạy benchmark, hãy viết mục tiêu dưới dạng câu hỏi có thể kiểm chứng. Mục tiêu càng cụ thể thì càng dễ chọn workload và metric.

Ví dụ:

- Sau khi thêm index trên (tenant_id, created_at), p95 của truy vấn lịch sử có giảm dưới 120 ms ở tải 300 request/giây không?
- Khi tăng writer từ 8 lên 16, throughput ghi có tăng mà lock wait và p99 vẫn nằm trong SLO không?
- Thay đổi batch size từ 500 lên 2.000 có rút ngắn thời gian nạp dữ liệu mà không làm replica lag vượt 5 giây không?
- Khi cache lạnh, database có duy trì được p95 dưới 250 ms với 150 request/giây không?
- Sau khi cập nhật statistics, optimizer có chọn plan phù hợp hơn với phân bố dữ liệu mới không?

### Mục tiêu định lượng

Một mục tiêu nên có:

| Thành phần | Ví dụ |
|---|---|
| Đối tượng | Truy vấn tìm đơn hàng theo tenant và khoảng ngày |
| Tải | 300 request/giây, 70% đọc và 30% ghi |
| Điều kiện | 20 triệu hàng, cache nóng, 16 client đồng thời |
| Metric chính | p95 latency và throughput thành công |
| Ngưỡng đạt | p95 dưới 120 ms, lỗi dưới 0,1% |
| Ràng buộc | CPU dưới 80%, replica lag dưới 5 giây |

Ngưỡng cần đến từ SLO, yêu cầu sản phẩm hoặc capacity target. Không tự đặt ngưỡng sau khi xem kết quả chỉ để làm cho phép thử có vẻ đạt.

### Giả thuyết

Giả thuyết mô tả cơ chế dự kiến tạo ra thay đổi. Ví dụ:

“Index ghép (tenant_id, created_at) sẽ giảm số hàng và trang phải đọc vì workload luôn lọc tenant bằng equality rồi lọc thời gian theo range. Dự kiến logical reads và p95 giảm; chi phí insert tăng nhẹ do phải duy trì thêm index.”

Giả thuyết tốt có cả lợi ích và chi phí có thể phát sinh. Nhờ đó báo cáo đánh giá được trade-off, không chỉ tìm một metric cải thiện.

## 3. Xác định phạm vi và đối tượng đo

Ghi rõ phép thử bao gồm thành phần nào:

- Một câu SQL, một transaction hay một API nghiệp vụ.
- Một bảng hay một nhóm bảng có join và foreign key.
- Một database instance hay toàn bộ topology primary/replica.
- Đọc, ghi, upsert, batch, report hay workload hỗn hợp.
- Tầng ứng dụng, connection pool, proxy, cache và database.
- Một query fingerprint hay toàn bộ workload theo tỷ trọng.

Nếu đo API end-to-end, latency bao gồm network, application processing, connection acquisition, proxy và DB. Nếu đo trực tiếp SQL ở DB, latency không đại diện cho toàn bộ request. Báo cáo phải nêu rõ ranh giới đo.

### Chọn workload đại diện

Không nên chỉ chọn truy vấn dễ chạy hoặc truy vấn có kết quả tốt. Hãy dùng query fingerprint, log đã chuẩn hóa, trace hoặc thống kê workload để chọn các thao tác chiếm phần lớn:

- Tổng số request.
- Tổng DB time hoặc CPU time.
- I/O và số hàng đọc.
- Transaction log generation.
- Lock wait hoặc deadlock.
- Độ trễ ở percentile cao.

Một truy vấn ít xuất hiện nhưng chiếm phần lớn DB time có thể quan trọng hơn một truy vấn phổ biến nhưng rất rẻ. Ghi rõ cách chọn workload để người đọc hiểu phạm vi đại diện.

### Workload hỗn hợp

Nếu production chạy nhiều loại truy vấn đồng thời, một benchmark chỉ chạy SELECT đơn lẻ có thể đánh giá sai năng lực. Hãy tái tạo tỷ lệ đọc/ghi, transaction, batch, report và background job gần thực tế. Khi không thể tái tạo toàn bộ, ghi rõ nhóm nào được mô phỏng và nhóm nào bị loại.

## 4. Ghi điều kiện môi trường

Kết quả benchmark chỉ có thể so sánh khi điều kiện môi trường được ghi đủ và tương đương. Các thông tin tối thiểu gồm:

| Nhóm | Thông tin nên ghi |
|---|---|
| DBMS | Tên, phiên bản, edition, engine và patch |
| Hạ tầng | CPU/vCPU, RAM, storage, IOPS/throughput, network |
| Topology | Primary, replica, cluster, shard, proxy và cache |
| OS/runtime | Hệ điều hành, kernel hoặc runtime liên quan |
| Cấu hình DB | Memory, connection limit, parallelism, durability, isolation |
| Pool/proxy | Pool size, timeout, pooling mode, routing |
| Ứng dụng | Driver, ORM, phiên bản, số instance và worker |
| Schema | DDL, index, constraint, partition và trigger |
| Dữ liệu | Số hàng, dung lượng, phân bố và độ lệch |
| Trạng thái cache | Cold, warm, hit ratio hoặc cách làm nóng |
| Tải nền | Backup, replication, vacuum, ETL, batch và tác vụ khác |
| Thời điểm | Ngày giờ, múi giờ, cửa sổ chạy và trạng thái hệ thống |

Không chỉ ghi tên instance. Hai database cùng loại nhưng khác RAM, storage class, cấu hình durability hoặc số replica có thể cho kết quả khác đáng kể.

### Ghi cấu hình quan trọng

Không cần sao chép mọi tham số DB vào phần chính, nhưng phải lưu các tham số có thể ảnh hưởng phép đo. Ví dụ:

- PostgreSQL: shared_buffers, work_mem, effective_cache_size, max_connections, synchronous_commit, autovacuum và parallel worker settings.
- MySQL/InnoDB: innodb_buffer_pool_size, redo capacity, isolation level, flush policy, thread/concurrency và binlog settings.
- SQL Server: max server memory, MAXDOP, cost threshold, recovery model, tempdb và Query Store settings.
- Oracle: SGA/PGA, optimizer settings, parallelism, undo và redo configuration.

Tên tham số chỉ là gợi ý theo DBMS. Báo cáo phải ghi giá trị thực của hệ thống đang thử và nêu thay đổi cấu hình giữa các lượt.

### Phân biệt môi trường thử và production

Nếu benchmark chạy trên môi trường nhỏ hơn production, ghi rõ tỷ lệ CPU/RAM/storage, số node, dữ liệu và workload. Không nhân tuyến tính kết quả từ một máy nhỏ để kết luận năng lực cụm lớn nếu chưa chứng minh scaling behavior.

## 5. Mô tả dữ liệu kiểm thử

Khối lượng dữ liệu ảnh hưởng trực tiếp đến plan, cache, index và I/O. Báo cáo nên ghi:

- Tổng số hàng và dung lượng bảng.
- Kích thước index và số lượng index.
- Phân bố giá trị của cột lọc/join.
- Tỷ lệ NULL, giá trị lặp và độ lệch (skew).
- Tỷ lệ dữ liệu nóng so với dữ liệu lạnh.
- Phạm vi thời gian được truy vấn.
- Tỷ lệ insert/update/delete và dữ liệu đến muộn.
- Tình trạng partition và statistics.

### Dữ liệu tổng hợp có thể gây sai lệch

Dữ liệu sinh ngẫu nhiên đều có thể không phản ánh production. Ví dụ, tenant có quy mô rất khác nhau; một vài customer chiếm phần lớn order; trạng thái mới chiếm tỷ lệ cao; dữ liệu thời gian gần hiện tại được đọc thường xuyên hơn.

Nếu dữ liệu thử phân bố đều nhưng production lệch mạnh, optimizer có thể chọn plan khác và hot key contention cũng khác. Hãy dùng dữ liệu đã ẩn danh hoặc sinh dữ liệu có phân bố gần thực tế, đồng thời ghi rõ phương pháp tạo.

### Statistics và histogram

Optimizer dựa trên statistics để ước lượng số hàng. Báo cáo cần ghi thời điểm cập nhật statistics, sampling hoặc histogram nếu chúng ảnh hưởng plan. Nếu thay đổi dữ liệu đáng kể nhưng statistics cũ, kết quả có thể phản ánh plan sai do ước lượng lỗi.

Khi mục tiêu là so sánh index hoặc SQL, giữ statistics và dữ liệu tương đương giữa các lượt. Nếu một lượt cập nhật statistics còn lượt kia không, ghi đó là một biến độc lập hoặc chạy lại theo điều kiện thống nhất.

## 6. Mô tả workload và mô hình tải

Workload cần mô tả cả loại thao tác lẫn cách request đến hệ thống.

### Thành phần workload

| Thuộc tính | Cần ghi |
|---|---|
| Tỷ lệ thao tác | Read, insert, update, delete, upsert, report |
| Transaction | Số statement mỗi transaction và ranh giới commit |
| Arrival rate | Request/transaction mỗi giây hoặc mô hình người dùng |
| Concurrency | Client, worker, thread và connection đồng thời |
| Think time | Khoảng nghỉ giữa thao tác nếu mô phỏng người dùng |
| Payload | Kích thước request, số hàng trả về và số hàng ghi |
| Key distribution | Uniform, skewed, hot key hoặc theo tenant |
| Parameter distribution | Giá trị phổ biến, hiếm và biên |
| Duration | Warm-up, steady-state và tổng thời gian |
| Retry | Chính sách retry, timeout và backoff |

### Closed workload và open workload

Trong closed workload, một số lượng client cố định gửi request mới sau khi request trước hoàn thành. Khi hệ thống chậm, tốc độ đến tự giảm vì client đang chờ. Điều này có thể che giấu mức quá tải.

Trong open workload, request được phát theo arrival rate định trước, độc lập với thời gian hoàn thành request trước. Mô hình này phù hợp hơn khi muốn mô phỏng traffic đến từ bên ngoài, nhưng generator phải có khả năng duy trì tốc độ và không tự trở thành bottleneck.

Hãy ghi rõ mô hình được dùng. Nếu load generator không giữ được arrival rate dự kiến, kết quả không đại diện cho mục tiêu tải.

### Tỷ lệ đọc/ghi

Ví dụ workload có:

- 60% đọc chi tiết đơn hàng.
- 20% tìm kiếm theo tenant và khoảng thời gian.
- 10% cập nhật trạng thái.
- 5% insert event.
- 5% báo cáo tổng hợp.

Tỷ lệ phải được đo theo request hoặc transaction và nêu cách tính. Không trộn tỷ lệ câu SQL với tỷ lệ transaction nếu một transaction có nhiều statement.

### Phân bố khóa và hot key

Benchmark ghi cần mô phỏng cả khóa phân tán và khóa nóng. Nếu production nhiều worker cập nhật cùng một tài khoản, counter hoặc trạng thái, một workload phân bố đều sẽ đánh giá thấp contention.

Ghi rõ tỷ lệ request trên top 1%, top 10% key, số tenant và cách chọn key. Với dữ liệu nhạy cảm, lưu phân bố thống kê thay vì lưu giá trị thực.

## 7. Các loại kiểm thử và mục đích

Không dùng một lượt load test để trả lời mọi câu hỏi. Chọn loại test theo mục tiêu:

| Loại test | Mục tiêu | Kết quả cần ghi |
|---|---|---|
| Smoke | Xác nhận workload và công cụ chạy đúng | Lỗi cấu hình, kết nối, dữ liệu |
| Baseline | Ghi hiệu năng hiện tại | Latency, throughput, tài nguyên và lỗi |
| Load | Đo ở tải dự kiến | SLO, ổn định và headroom |
| Stress | Tăng tải đến khi suy giảm | Điểm bão hòa, kiểu lỗi và phục hồi |
| Spike | Tăng tải đột ngột | Khả năng hấp thụ burst và thời gian ổn định |
| Soak | Duy trì tải dài | Rò rỉ, bloat, memory growth, queue và lag |
| Capacity | Tìm năng lực tối đa theo SLO | Throughput tối đa và tài nguyên tương ứng |
| Regression | So sánh trước/sau thay đổi | Chênh lệch và mức biến động |
| Failover/recovery | Kiểm tra chuyển node và phục hồi | Gián đoạn, lỗi, retry và consistency |

### Baseline

Baseline là phép đo tham chiếu trước thay đổi. Ghi rõ commit, schema, cấu hình và dữ liệu tương ứng. Nếu baseline đã cũ hoặc chạy trên môi trường khác, phải nêu hạn chế khi so sánh.

### Load và stress

Load test xác minh mục tiêu ở tải dự kiến. Stress test vượt tải mục tiêu để hiểu cách hệ thống suy giảm. Không dùng kết quả stress để tuyên bố SLO load test đã đạt.

### Soak

Soak test giúp phát hiện vấn đề chỉ xuất hiện theo thời gian như transaction dài, connection leak, table/index bloat, memory pressure, replication backlog hoặc job bảo trì không theo kịp.

## 8. Thiết kế quy trình đo có thể tái lập

Một quy trình so sánh nên cố định các yếu tố không phải biến thử nghiệm.

1. Chốt mục tiêu, workload, dataset và ngưỡng đạt trước khi chạy.
2. Chuẩn bị schema, index, statistics và dữ liệu.
3. Kiểm tra load generator, network và connection pool.
4. Ghi baseline trong điều kiện đã định.
5. Chạy warm-up theo quy tắc rõ ràng.
6. Đo steady-state trong khoảng thời gian đủ dài.
7. Lặp lại nhiều lượt nếu kết quả có biến động.
8. Thu thập metric DB, OS, ứng dụng và load generator đồng bộ thời gian.
9. Lưu execution plan và query fingerprint cho workload quan trọng.
10. Thay đổi một yếu tố chính mỗi lần nếu mục tiêu là xác định tác động nhân quả.
11. Chạy lại với cùng dữ liệu và workload.
12. Đối chiếu kết quả, kiểm tra dữ liệu và ghi giới hạn.

### Warm-up và steady-state

Warm-up cho phép buffer pool, plan cache, connection pool và JIT/compiled path đạt trạng thái gần vận hành bình thường. Không đưa warm-up vào số liệu steady-state nếu mục tiêu là đo trạng thái ổn định.

Tuy nhiên, nếu production thường xuyên có cold start hoặc cache miss, cần một phép thử riêng cho cold-cache behavior. Không được bỏ qua cold start chỉ vì steady-state cho kết quả tốt.

Ghi rõ:

- Thời gian warm-up.
- Điều kiện dừng warm-up.
- Cache có được làm sạch giữa các lượt hay không.
- Plan cache có được giữ hay reset không.
- Buffer/cache state được xác định bằng metric nào.

### Thời lượng và số lần lặp

Một lượt quá ngắn có thể không đủ mẫu để tính percentile hoặc quan sát checkpoint, autovacuum, purge và replication. Một lượt quá dài có thể bị ảnh hưởng bởi tải nền thay đổi.

Chọn thời lượng đủ để:

- Có số request hoàn thành phù hợp.
- Bao phủ các chu kỳ xử lý liên quan.
- Quan sát steady-state và độ biến động.
- Phát hiện queue hoặc memory tăng theo thời gian.

Chạy nhiều lần trong cùng điều kiện giúp phát hiện biến động. Báo cáo nên ghi số lần lặp, median/range hoặc phân bố của từng lượt, không chỉ chọn lượt tốt nhất.

### Thứ tự thử nghiệm

Nếu so sánh A và B, chạy A rồi B một lần có thể bị ảnh hưởng bởi cache nóng lên, tải nền hoặc nhiệt độ/hành vi storage. Có thể chạy xen kẽ A-B-B-A hoặc lặp nhiều lượt để giảm thiên lệch thứ tự. Cách chọn phải phù hợp chi phí và khả năng reset môi trường.

## 9. Chọn metric phù hợp

Không có một metric duy nhất mô tả hiệu năng database. Báo cáo cần chọn metric theo mục tiêu và liên kết chúng với nhau.

### Latency

- p50: thời gian của điểm giữa phân bố.
- p90/p95: thời gian mà 90%/95% request hoàn tất không vượt quá.
- p99/p99.9: phản ánh đuôi phân bố, nơi request chậm có thể ảnh hưởng lớn.
- Mean: hữu ích cho tổng chi phí trung bình nhưng nhạy với outlier.
- Max: có thể chỉ ra sự cố đơn lẻ nhưng không đại diện ổn định.

Luôn ghi đơn vị, số mẫu và ranh giới đo. p95 của SQL server execution khác p95 của API end-to-end. Không so sánh percentile nếu cách thu thập hoặc tập mẫu khác nhau.

### Throughput

Ghi request/giây, transaction/giây, query/giây hoặc rows/giây. Định nghĩa đơn vị rõ ràng. Một transaction có thể gồm nhiều statement; một batch có thể ghi nhiều hàng. Không gọi tất cả là TPS nếu chưa xác định transaction.

Throughput cần đi cùng latency và error rate. Tăng throughput bằng cách cho request chờ lâu hoặc bỏ lỗi không phải cải thiện hữu ích.

### Error và timeout

Ghi:

- Số lượng và tỷ lệ lỗi.
- Timeout ở ứng dụng, pool, proxy hay DB.
- Deadlock, serialization failure, lock timeout.
- Constraint violation và lỗi dữ liệu.
- Connection reset, failover và retry.
- Số request bị từ chối hoặc load shed.

Tách lỗi dự kiến của test khỏi lỗi hệ thống. Không loại request lỗi khỏi mẫu latency mà không công bố; nếu chỉ đo latency của request thành công, kết quả có thể đẹp giả tạo khi phần request chậm nhất bị timeout.

### Concurrency và queue

Ghi client active, connection active, pool wait, request queue depth, transaction đang mở và thời gian giữ connection. Concurrency là số công việc đang diễn ra; arrival rate là tốc độ công việc đến. Hai đại lượng liên hệ nhưng không thể thay thế nhau.

## 10. Metric ở tầng database

Để liên hệ latency với nguyên nhân, thu thập metric của DBMS:

| Nhóm | Ví dụ số liệu |
|---|---|
| Query | Calls, total time, mean time, rows, shared/local blocks |
| Plan | Scan type, join type, estimated/actual rows, sort/hash spill |
| CPU | DB CPU, host CPU, runnable queue |
| Memory | Buffer hit, cache eviction, work memory, memory grant |
| I/O | Read/write bytes, IOPS, latency, queue depth |
| Lock | Lock wait, blocker, deadlock, transaction age |
| Log | WAL/redo/undo/log bytes, flush latency, log reuse |
| Replication | Send/receive/apply lag, queue/backlog |
| Maintenance | Vacuum/purge, checkpoint, statistics update |
| Connection | Active/idle, pool wait, connect/auth time |

Metric cần cùng time window với load test. Nếu dashboard lấy trung bình 5 phút nhưng test kéo dài 60 giây, một đỉnh tải ngắn có thể bị làm mờ. Đồng bộ timestamp giữa load generator, application, proxy, DB và host.

### CPU và I/O

CPU cao có thể đến từ nhiều query, plan tốn CPU, parse/plan, sort/hash hoặc contention. I/O cao có thể do scan lớn, cache miss, checkpoint hoặc log flush. Chỉ số CPU/I/O không tự chứng minh nguyên nhân; cần liên kết với query fingerprint, execution plan và thời gian.

### Lock và transaction contention

Ghi số transaction chờ, loại lock, blocker, deadlock, thời gian chờ và key/table bị tranh chấp. Một workload có throughput trung bình tốt nhưng p99 cao do một số hot key vẫn có thể không đạt SLO.

### Memory và spill

Ghi buffer/cache hit, memory grant, sort/hash spill ra disk, temporary storage và eviction. Một plan có thể nhanh khi dataset vừa trong RAM nhưng suy giảm mạnh khi memory pressure tăng.

## 11. Gắn kết quả với execution plan và statistics

Đối với thay đổi SQL hoặc index, báo cáo cần lưu plan trước và sau:

- Access path: sequential/table scan, index seek/scan, bitmap hoặc partition scan.
- Join strategy: nested loop, hash join, merge join.
- Estimated rows và actual rows.
- Số vòng lặp, rows removed/filter và rows returned.
- Buffer reads/hits, physical reads và I/O.
- Sort/hash memory và spill.
- Parallel workers hoặc degree of parallelism.
- Partition pruning và predicate pushdown.

### Estimated rows so với actual rows

Sai lệch lớn giữa số hàng ước lượng và thực tế có thể khiến optimizer chọn join order hoặc access path không phù hợp. Báo cáo nên nêu node nào sai lệch, mức sai lệch và statistics liên quan.

Ví dụ:

| Node | Estimated rows | Actual rows | Nhận xét |
|---|---:|---:|---|
| Index scan | 100 | 95.000 | Ước lượng thấp gần 950 lần |
| Join output | 500 | 88.000 | Sai lệch lan sang node phía trên |
| Sort input | 600 | 87.500 | Có nguy cơ memory grant thiếu |

Các con số trên là minh họa. Cần lấy từ plan thực tế và kiểm tra cách DBMS báo actual rows, loops và thời gian.

### Không chỉ lưu ảnh chụp plan

Lưu plan ở dạng text/JSON/XML theo DBMS, câu SQL đã chuẩn hóa, parameter class và thời điểm thu thập. Plan có thể thay đổi theo parameter, statistics, schema, cache, version và cấu hình. Một ảnh chụp plan không chứng minh mọi lần thực thi dùng cùng plan.

### EXPLAIN ANALYZE và tác động

Một số công cụ như EXPLAIN ANALYZE thực thi câu lệnh để đo actual rows và thời gian. Với SELECT thường ít rủi ro dữ liệu hơn, nhưng vẫn tiêu thụ CPU/I/O. Với DML, câu lệnh có thể thay đổi dữ liệu hoặc kích hoạt trigger. Chỉ chạy trên môi trường an toàn hoặc trong transaction có cách rollback đã kiểm chứng; không giả định mọi side effect đều được hoàn tác.

## 12. Phân tích số liệu và độ tin cậy

Một báo cáo cần giải thích độ biến động, không chỉ đưa ra một con số.

### Không chọn lượt tốt nhất

Nếu năm lượt benchmark có p95 lần lượt 90, 94, 92, 140 và 97 ms, không nên chỉ báo 90 ms. Lượt 140 ms có thể phản ánh checkpoint, tải nền hoặc biến động thực. Hãy báo tất cả lượt, median và range, rồi điều tra outlier.

### So sánh percentile đúng cách

Percentile không cộng hoặc trừ tuyến tính như mean. Không lấy p95 của từng batch rồi tính trung bình để thay cho p95 của toàn bộ mẫu nếu mục tiêu là phân vị tổng hợp. Hãy tính từ raw samples hoặc histogram có cách merge chính xác.

Nếu chỉ có histogram, ghi bucket width và sai số xấp xỉ. Nếu công cụ dùng coordinated omission correction, nêu rõ vì nó ảnh hưởng cách ghi nhận request bị trì hoãn khi generator chờ response.

### Sample size

Số request ít khiến p99 không ổn định. Ví dụ, 100 mẫu chỉ có khoảng một mẫu nằm trong 1% đuôi; p99 có thể phụ thuộc một request đơn lẻ. Hãy báo số mẫu và tránh diễn giải percentile quá sâu khi số mẫu không đủ.

### Khoảng tin cậy và biến động

Khi cần kết luận chặt, có thể báo confidence interval cho throughput/latency hoặc so sánh nhiều lượt. Với phân bố latency lệch, bootstrap trên raw samples hoặc phân tích theo từng run có thể phù hợp hơn giả định phân bố chuẩn đơn giản.

Không cần đưa công thức thống kê phức tạp vào mọi báo cáo. Nhưng cần nói rõ kết quả có ổn định giữa các lần chạy hay không và mức độ chắc chắn của kết luận.

### Outlier

Không tự động xóa outlier. Trước tiên xác định:

- Có deploy, backup, checkpoint hoặc failover xảy ra không?
- Load generator có bị CPU/network bottleneck không?
- DB có lock wait, plan change hoặc cache miss không?
- Có lỗi đo, clock skew hoặc mất metric không?

Nếu loại bỏ một lượt, ghi tiêu chí và lý do. Nếu outlier là hành vi production có thể xảy ra, nó phải được giữ trong kết luận hoặc báo riêng.

## 13. Nhận diện điểm bão hòa và bottleneck

Khi tăng tải, throughput thường tăng đến một vùng rồi chậm lại hoặc đứng yên, trong khi latency và queue tăng. Điểm bão hòa là vùng hệ thống không còn tăng throughput tương ứng với tải đến và các tài nguyên bắt đầu tranh chấp.

Các dấu hiệu:

- Throughput phẳng nhưng arrival rate tiếp tục tăng.
- p95/p99 tăng nhanh.
- Connection pool wait và active session tăng.
- CPU gần bão hòa hoặc runnable queue tăng.
- I/O latency/queue depth tăng.
- Lock wait/deadlock tăng.
- Log flush hoặc replication apply trở thành giới hạn.
- Queue ở ứng dụng/proxy tăng liên tục.

### Xác định nút thắt

Không kết luận “DB thiếu CPU” chỉ vì CPU cao. Hãy kiểm tra query fingerprint và plan; nếu CPU tập trung vào một query có nhiều row scan hoặc sort, sửa query có thể hiệu quả hơn tăng vCPU.

Nếu I/O latency cao nhưng read bytes không lớn, có thể vấn đề ở storage queue hoặc random I/O. Nếu log write/flush tăng theo batch commit, transaction batching hoặc durability path có thể là yếu tố.

Nếu lock wait chiếm nhiều thời gian, tăng connection hoặc CPU có thể làm số waiter tăng mà throughput không đổi. Cần xem hot key, transaction duration và thứ tự truy cập tài nguyên.

### Phân biệt DB bottleneck và load generator bottleneck

Load generator cũng có CPU, network, socket và connection limit. Nếu generator không thể phát đủ request, kết quả có thể đánh giá thấp DB. Theo dõi CPU, event loop/thread pool, network throughput, dropped request và achieved arrival rate của generator.

## 14. So sánh trước và sau thay đổi

So sánh cần giữ cùng:

- DBMS version và cấu hình.
- Dataset và phân bố.
- Workload, concurrency và arrival rate.
- Warm-up/cache state.
- Thời lượng và cửa sổ đo.
- Tải nền và topology.
- Metric definition và tool version.

Nếu một yếu tố không thể giữ nguyên, ghi rõ và xem kết quả là so sánh có điều kiện.

### Bảng chênh lệch

| Metric | Baseline | Candidate | Thay đổi | Đạt ngưỡng? |
|---|---:|---:|---:|---|
| p50 latency | 42 ms | 35 ms | -16,7% | Có |
| p95 latency | 180 ms | 112 ms | -37,8% | Có |
| p99 latency | 520 ms | 460 ms | -11,5% | Cần xem SLO |
| Throughput | 240 TPS | 285 TPS | +18,8% | Có |
| CPU | 62% | 74% | +12 điểm % | Trong giới hạn |
| Logical reads/request | 18.000 | 5.200 | -71,1% | Có |
| Write latency | 28 ms | 36 ms | +28,6% | Trade-off |

Các giá trị là ví dụ minh họa, không phải kết quả đo thực. Khi trình bày thay đổi phần trăm, ghi rõ công thức và đơn vị. Với CPU, “tăng 12 điểm phần trăm” khác “tăng 12% tương đối”.

### Cải thiện một metric có thể làm xấu metric khác

Index mới có thể giảm read latency nhưng tăng write amplification, storage và backup time. Batch lớn có thể tăng rows/sec nhưng làm lock duration và replica lag tăng. Parallel query có thể giảm latency một truy vấn nhưng tranh CPU với workload khác.

Báo cáo phải ghi trade-off và đánh giá theo SLO tổng thể, không chọn metric thuận lợi duy nhất.

## 15. Định dạng và cấu trúc báo cáo

Một báo cáo dễ review nên có phần tóm tắt trước, sau đó mới đến phương pháp và dữ liệu chi tiết.

### 15.1. Thông tin chung

- Tên bài kiểm thử và mã run.
- Ngày giờ, người thực hiện và người review.
- Hệ thống/database và môi trường.
- Commit hoặc phiên bản ứng dụng/schema.
- Mục tiêu và phạm vi.
- Trạng thái: đạt, không đạt, chưa kết luận.

### 15.2. Tóm tắt điều hành

Viết ngắn gọn:

- Câu hỏi cần trả lời.
- Kết quả chính và ngưỡng.
- Tác động tích cực/tiêu cực đáng kể.
- Kết luận và khuyến nghị.
- Giới hạn quan trọng nhất.

Người đọc phải hiểu được quyết định ngay cả khi chưa xem phụ lục.

### 15.3. Điều kiện thử nghiệm

Mô tả topology, tài nguyên, cấu hình, schema, index, dataset, statistics, cache state, tải nền, workload, arrival model, concurrency và thời lượng.

### 15.4. Phương pháp

Ghi công cụ, phiên bản, cách tạo tải, cách thu metric, warm-up, steady-state, số lần lặp, tiêu chí loại lượt và cách tính percentile.

### 15.5. Kết quả

Trình bày latency, throughput, error rate, concurrency, resource utilization, lock wait, I/O, memory, log, replication và plan. Dùng bảng/biểu đồ có đơn vị, trục, time window và chú giải.

### 15.6. Phân tích

Liên kết kết quả với execution plan, statistics, query fingerprint và tài nguyên. Giải thích điều gì thay đổi, điều gì không đổi và nguyên nhân nào đã được xác nhận.

### 15.7. Giới hạn và rủi ro

Nêu khác biệt môi trường, thiếu workload, dữ liệu tổng hợp, thời lượng ngắn, số mẫu, cache state, tải nền, metric thiếu hoặc giả định chưa xác nhận.

### 15.8. Khuyến nghị và bước tiếp theo

Mỗi khuyến nghị nên có:

- Hành động cụ thể.
- Bằng chứng hỗ trợ.
- Tác động dự kiến.
- Rủi ro/trade-off.
- Điều kiện triển khai.
- Phép đo sau triển khai và tiêu chí rollback.

### 15.9. Phụ lục

Đính kèm raw result, query fingerprint, execution plan, cấu hình, script workload, log đã loại dữ liệu nhạy cảm, dashboard snapshot và mã commit. Không đưa secret, password, token hoặc dữ liệu cá nhân vào báo cáo.

## 16. Mẫu báo cáo có thể tái sử dụng

Có thể dùng khung sau cho mỗi lượt benchmark:

```markdown
# Báo cáo kiểm thử hiệu năng: <tên>

## Trạng thái
- Kết luận: PASS / FAIL / INCONCLUSIVE
- Run ID:
- Thời gian:
- Người thực hiện:
- Commit/schema version:

## 1. Mục tiêu
- Câu hỏi:
- Giả thuyết:
- SLO/ngưỡng đạt:
- Phạm vi:

## 2. Điều kiện thử nghiệm
- DBMS/version:
- Hạ tầng/topology:
- Cấu hình liên quan:
- Schema/index:
- Dataset/phân bố:
- Statistics:
- Cache state:
- Tải nền:

## 3. Workload
- Query/transaction mix:
- Arrival model/rate:
- Concurrency:
- Key/parameter distribution:
- Duration/warm-up:
- Retry/timeout:

## 4. Phương pháp đo
- Tool/version:
- Metric source:
- Ranh giới latency:
- Số lần lặp:
- Cách tính percentile:
- Tiêu chí loại lượt:

## 5. Kết quả
| Metric | Baseline | Candidate | Delta | Ngưỡng |
|---|---:|---:|---:|---:|

## 6. Phân tích
- Throughput/latency:
- Execution plan/statistics:
- CPU/memory/I/O:
- Lock/transaction:
- Log/replication:
- Error/retry:

## 7. Giới hạn
- Khác biệt môi trường:
- Workload chưa mô phỏng:
- Thiếu mẫu/metric:
- Giả định chưa xác nhận:

## 8. Kết luận và khuyến nghị
- Kết luận:
- Trade-off:
- Hành động:
- Điều kiện triển khai:
- Rollback trigger:
- Phép đo tiếp theo:

## Phụ lục
- Script/config:
- Query fingerprint/plan:
- Raw result/dashboard:
- Commit và artifact:
```

Mẫu này là cấu trúc tối thiểu. Với một phép thử nhỏ, có thể gộp các phần; với capacity test hoặc thay đổi ảnh hưởng lớn, nên giữ đầy đủ bằng chứng và phụ lục.

## 17. Ví dụ: đánh giá index mới cho truy vấn lịch sử

Một hệ thống quản lý đơn hàng cần truy vấn theo tenant và khoảng thời gian:

```sql
SELECT order_id, status, total_amount, created_at
FROM orders
WHERE tenant_id = :tenant_id
  AND created_at >= :from_time
  AND created_at < :to_time
ORDER BY created_at DESC
LIMIT 100;
```

Giả thuyết là index ghép (tenant_id, created_at DESC) sẽ giảm số hàng phải đọc. Test dùng 30 triệu hàng, 2.000 tenant với phân bố lệch, 16 client, 70% đọc truy vấn lịch sử và 30% cập nhật trạng thái. Baseline và candidate chạy trên cùng loại máy, cùng DBMS version, cùng dataset snapshot và cùng warm-up.

### Kết quả minh họa

| Metric | Baseline | Candidate |
|---|---:|---:|
| p50 | 58 ms | 31 ms |
| p95 | 210 ms | 96 ms |
| p99 | 640 ms | 410 ms |
| Throughput thành công | 220 TPS | 270 TPS |
| Logical reads/query | 24.000 | 3.800 |
| CPU DB | 68% | 72% |
| Insert/update latency p95 | 44 ms | 51 ms |
| Index storage | 0 | +8,5 GB |

Plan trước thay đổi đọc nhiều hàng qua scan rồi lọc tenant/time. Plan sau dùng index range scan và trả gần đủ 100 hàng cần thiết. Logical reads giảm mạnh, p95 đọc cải thiện. Tuy nhiên, write latency tăng và index chiếm thêm storage.

### Kết luận có điều kiện

Trong workload và môi trường đã thử, index mới cải thiện truy vấn lịch sử và tăng throughput tổng. Candidate có thể phù hợp nếu workload đọc này quan trọng và chi phí ghi/storage vẫn trong giới hạn. Trước khi triển khai rộng, cần kiểm tra:

- p99 dưới burst và với tenant lớn nhất.
- Insert/update throughput trong giờ cao điểm.
- Backup, restore và replication traffic khi index được duy trì.
- Plan với các parameter có selectivity khác nhau.
- Storage headroom và thời gian tạo index trên production-scale data.

Không kết luận “index làm DB nhanh hơn 50%” từ một truy vấn. Kết luận đúng là truy vấn và workload đã đo cải thiện theo các metric cụ thể, với trade-off được ghi lại.

## 18. Ví dụ: kiểm thử batch ghi và replica lag

Một job import ghi 5 triệu hàng. Nhóm thử ba batch size: 200, 1.000 và 5.000. Mỗi lượt chạy trên cùng snapshot, cùng số worker và cùng cấu hình log/replication.

| Batch size | Rows/s | p95 transaction | Peak replica lag | Log bytes |
|---:|---:|---:|---:|---:|
| 200 | 18.000 | 90 ms | 1,2 s | 4,1 GB |
| 1.000 | 27.000 | 310 ms | 4,8 s | 4,0 GB |
| 5.000 | 29.000 | 1.650 ms | 22 s | 4,2 GB |

Các số liệu là minh họa. Batch 5.000 chỉ tăng throughput khoảng 7,4% so với 1.000 nhưng transaction p95 và replica lag tăng mạnh. Nếu SLO replica lag là dưới 5 giây, batch 5.000 không đạt dù rows/s cao nhất. Batch 1.000 có thể là lựa chọn cân bằng hơn, sau khi kiểm tra workload trực tuyến và độ ổn định qua nhiều lượt.

Báo cáo cần giải thích vì sao log bytes gần tương đương nhưng lag khác nhau: batch lớn tạo burst log và transaction lâu hơn, làm replica apply theo đợt. Cần xác minh bằng log generation rate, apply queue, commit duration và tải nền.

## 19. Giới hạn của kết quả và nguy cơ diễn giải sai

Một phép thử luôn có giới hạn. Nêu giới hạn không làm báo cáo yếu đi; nó giúp người đọc hiểu kết luận áp dụng ở đâu.

### Khác biệt môi trường

CPU, storage, network, RAM, topology, DBMS version hoặc durability khác production có thể thay đổi plan và throughput. Ghi rõ khác biệt và tránh suy rộng khi chưa có bằng chứng.

### Dataset không đại diện

Dataset nhỏ có thể nằm hoàn toàn trong memory; production có thể đọc disk. Phân bố đồng đều không mô phỏng hot tenant. Dữ liệu không có cập nhật/xóa có thể bỏ qua chi phí index maintenance và vacuum/purge.

### Cache state

Một phép thử warm-cache không chứng minh cold-cache behavior. Một phép thử cold-cache cũng không đại diện steady-state. Báo cáo nên tách hai kết quả nếu cả hai có ý nghĩa.

### Workload không đầy đủ

Thiếu report, batch, backup, replication hoặc background job có thể làm benchmark lạc quan. Tỷ lệ đọc/ghi và concurrency khác thực tế làm thay đổi contention.

### Thời lượng quá ngắn

Test ngắn có thể không bao phủ checkpoint, autovacuum, purge, log backup, cache eviction hoặc memory leak. Không dùng nó để kết luận soak behavior.

### Load generator giới hạn

Nếu generator không phát đủ request, throughput đo được là giới hạn generator chứ chưa chắc là giới hạn DB. Báo cáo phải ghi achieved arrival rate và metric của generator.

### Percentile thiếu mẫu

p99 từ vài trăm mẫu có độ bất ổn cao. Ghi số mẫu và cách tính; tránh khẳng định p99 chính xác khi dữ liệu không đủ.

### Tác động của phép đo

Tracing, query logging, execution plan capture và metric polling có thể thêm overhead. Báo cáo nên nêu mức instrumentation và cân nhắc phép đo đối chứng khi overhead đáng kể.

### Plan thay đổi theo tham số

Một parameter value có thể chọn plan khác giá trị khác. Test một tenant nhỏ không đại diện tenant lớn. Hãy lấy các lớp selectivity và parameter skew quan trọng.

### Không suy rộng tuyến tính

Tăng số CPU gấp đôi không bảo đảm throughput gấp đôi. Lock, I/O, memory bandwidth, network, log flush và coordination có thể trở thành giới hạn mới. Capacity projection phải dựa trên nhiều điểm tải và mô hình bottleneck.

## 20. Bằng chứng, khả năng tái lập và quản lý artifact

Báo cáo nên đủ thông tin để một kỹ sư khác chạy lại hoặc kiểm tra kết quả:

- Run ID duy nhất.
- Commit ứng dụng và phiên bản schema.
- DBMS version và cấu hình đã dùng.
- Dataset snapshot hoặc cách sinh dữ liệu.
- Script workload và parameter distribution.
- Tool/version và lệnh chạy.
- Warm-up, duration, arrival rate và concurrency.
- Raw latency sample hoặc histogram.
- Query fingerprint và execution plan.
- Dashboard/metric export có timestamp.
- Log lỗi đã loại thông tin nhạy cảm.
- File tính toán/chuyển đổi metric.

### Bảo vệ dữ liệu nhạy cảm

Không lưu password, connection string có secret, access token, dữ liệu cá nhân hoặc payload nghiệp vụ nguyên bản nếu không cần. Dùng dữ liệu ẩn danh, hash key hoặc thống kê tổng hợp. Quyền truy cập artifact phải tương ứng độ nhạy của dữ liệu.

### Version hóa báo cáo

Nếu kết quả được cập nhật sau khi thay đổi điều kiện hoặc sửa cách tính, tạo version mới hoặc ghi lịch sử thay đổi. Không âm thầm thay raw data hoặc xóa lượt chạy thất bại. Giữ liên kết giữa báo cáo, run ID và commit để truy vết.

## 21. Khuyến nghị và quyết định triển khai

Khuyến nghị cần liên hệ trực tiếp với bằng chứng:

| Bằng chứng | Khuyến nghị có thể phù hợp |
|---|---|
| Estimated rows lệch actual rows lớn | Kiểm tra statistics, histogram và correlation |
| Logical reads cao, predicate có selectivity tốt | Đánh giá index/access path |
| Sort/hash spill | Xem memory grant, cardinality và cách giảm dữ liệu |
| Lock wait trên cùng key | Rút ngắn transaction, giảm hot-key update hoặc đổi mô hình ghi |
| Log flush chiếm latency | Đo commit frequency, durability path và batching |
| Replica lag tăng theo batch size | Giảm batch/concurrency hoặc điều tiết tốc độ |
| Pool wait cao nhưng DB CPU thấp | Kiểm tra pool/proxy limits, connection hold time và routing |
| CPU cao với query fingerprint cụ thể | Tối ưu SQL/plan trước khi tăng tài nguyên |
| p99 tăng nhưng p50 ổn định | Tìm queue, lock, outlier, skew và tail latency |

### Phân loại quyết định

- **PASS:** tất cả ngưỡng bắt buộc đạt và không có trade-off vượt giới hạn.
- **FAIL:** một hoặc nhiều ngưỡng bắt buộc không đạt.
- **INCONCLUSIVE:** phép thử thiếu dữ liệu, điều kiện không tương đương hoặc kết quả biến động chưa giải thích được.
- **PASS WITH CONDITIONS:** đạt trong phạm vi đã thử nhưng cần điều kiện triển khai, giới hạn tải hoặc theo dõi bổ sung.

Không dùng PASS nếu metric chính đạt nhưng error rate, data correctness hoặc replica consistency vi phạm điều kiện bắt buộc.

### Kế hoạch sau triển khai

Với thay đổi production, xác định:

- Metric canary cần theo dõi.
- Baseline và ngưỡng cảnh báo.
- Thời gian quan sát.
- Tỷ lệ traffic tăng theo giai đoạn.
- Điều kiện dừng/rollback.
- Cách kiểm tra plan và data correctness.
- Người chịu trách nhiệm quyết định.

Báo cáo benchmark không thay thế canary/production monitoring. Tải thực tế có thể có phân bố và hành vi khác môi trường thử.

## 22. Những sai lầm thường gặp

- **Chỉ ghi một con số latency:** thiếu percentile, throughput, error rate và số mẫu.
- **Không nêu ranh giới đo:** nhầm SQL latency với API end-to-end latency.
- **Chỉ báo lượt chạy tốt nhất:** che giấu biến động và outlier.
- **Không ghi workload:** người đọc không biết tải đọc/ghi, concurrency và key distribution.
- **Dùng dataset quá nhỏ:** buffer cache làm kết quả lạc quan.
- **Bỏ qua warm-up hoặc không mô tả cache state:** hai lượt không thể so sánh công bằng.
- **Không ghi cấu hình DB:** thay đổi memory, parallelism hoặc durability có thể là nguyên nhân thật.
- **Chỉ xem CPU:** bỏ qua lock, I/O, log, memory spill và pool wait.
- **Chỉ lưu ảnh execution plan:** không có raw plan, parameter class hoặc actual rows.
- **Dùng EXPLAIN ANALYZE trên DML production mà không đánh giá side effect:** phép đo có thể thay đổi dữ liệu.
- **Không theo dõi load generator:** tưởng DB không đạt throughput trong khi generator bị nghẽn.
- **Loại request lỗi khỏi latency mà không công bố:** làm kết quả có vẻ tốt hơn.
- **So sánh percentile bằng cách lấy trung bình percentile từng batch:** không tương đương percentile của toàn bộ mẫu.
- **Tuyên bố nhân đôi tài nguyên sẽ nhân đôi throughput:** bỏ qua bottleneck và scaling phi tuyến.
- **Đưa khuyến nghị không có bằng chứng:** khó review và khó xác minh sau triển khai.
- **Không ghi giới hạn:** kết quả bị áp dụng vượt phạm vi đã thử.

## 23. Checklist trước khi phát hành báo cáo

| Hạng mục | Câu hỏi kiểm tra |
|---|---|
| Mục tiêu | Câu hỏi, giả thuyết và ngưỡng đạt có được chốt trước? |
| Phạm vi | Đối tượng và ranh giới đo có rõ? |
| Môi trường | DBMS, hạ tầng, cấu hình và topology có được ghi? |
| Dữ liệu | Quy mô, phân bố, skew và statistics có được mô tả? |
| Workload | Mix, arrival model, concurrency, key distribution và retry có rõ? |
| Phương pháp | Warm-up, steady-state, duration, số lần lặp và tool có được ghi? |
| Metric | Latency percentiles, throughput, errors và resource metrics có đơn vị? |
| Plan | Có plan trước/sau, estimated/actual rows và query fingerprint? |
| Bottleneck | Có bằng chứng về CPU, I/O, lock, memory, log hoặc replication? |
| So sánh | Điều kiện A/B có tương đương? |
| Thống kê | Có số mẫu, biến động và xử lý outlier minh bạch? |
| Giới hạn | Có nêu khác biệt môi trường và workload chưa mô phỏng? |
| Khuyến nghị | Mỗi hành động có bằng chứng, trade-off và điều kiện? |
| Tái lập | Có run ID, commit, script, config và raw artifact? |
| Bảo mật | Artifact không chứa secret hoặc dữ liệu nhạy cảm không cần thiết? |
| Quyết định | PASS/FAIL/INCONCLUSIVE có dựa trên mọi ngưỡng bắt buộc? |

## 24. Nguyên tắc ra quyết định

Báo cáo kiểm thử hiệu năng phải trả lời mục tiêu nào được kiểm chứng, trong điều kiện nào, bằng workload và phương pháp đo nào, kết quả ra sao và giới hạn áp dụng ở đâu. Mọi con số cần có đơn vị, số mẫu, ranh giới đo và nguồn dữ liệu. Mọi kết luận cần liên hệ với execution plan, statistics, CPU, memory, I/O, lock, log và replication khi các yếu tố đó ảnh hưởng workload.

Khi so sánh trước/sau, giữ điều kiện tương đương, báo cả latency percentiles, throughput, error rate và trade-off. Khi kết quả biến động hoặc thiếu bằng chứng, ghi rõ chưa thể kết luận và đề xuất phép đo tiếp theo. Một báo cáo có thể tái lập, trung thực về giới hạn và gắn khuyến nghị với dữ liệu sẽ giúp nhóm tối ưu cơ sở dữ liệu đưa ra quyết định an toàn, đo lại được và duy trì hiệu năng theo SLO khi tải thay đổi.
