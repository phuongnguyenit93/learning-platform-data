# So sánh lợi ích tối ưu truy vấn với chi phí thay đổi kiến trúc

## Mục tiêu bài học

Khi cơ sở dữ liệu chậm hoặc không còn đáp ứng được tải, đội kỹ thuật thường đứng trước hai hướng: tối ưu truy vấn và cách truy cập dữ liệu hiện tại, hoặc thay đổi kiến trúc bằng cách thêm cache, read replica, partition, sharding hay một read model riêng. Tối ưu truy vấn thường có phạm vi nhỏ và dễ kiểm chứng hơn. Thay đổi kiến trúc có thể mở rộng năng lực phục vụ ở quy mô lớn, nhưng tạo thêm chi phí phát triển, vận hành, đồng bộ dữ liệu, xử lý lỗi và phục hồi.

Trong chương **Mở rộng hệ thống** của module **DATABASE_PERFORMANCE**, bài học này cung cấp cách so sánh lợi ích tối ưu truy vấn với chi phí thay đổi kiến trúc. Module **DATABASE_PERFORMANCE** rèn phương pháp tối ưu hiệu năng cơ sở dữ liệu dựa trên đo đạc tải, kế hoạch thực thi, thống kê và cơ chế truy cập dữ liệu; nội dung hướng dẫn thiết kế chỉ mục, cải thiện SQL, nhận diện tranh chấp giao dịch, nút thắt I/O, bộ nhớ và kiểm chứng kết quả sau điều chỉnh. Do đó, quyết định mở rộng phải dựa trên bằng chứng về nút thắt, mục tiêu SLA, tốc độ tăng tải và tổng chi phí sở hữu, đồng thời kiểm tra tác động tới tính đúng đắn và khả năng vận hành.

Sau bài học, bạn có thể:

- Phân biệt vấn đề do truy vấn/kế hoạch thực thi với giới hạn năng lực của kiến trúc.
- Xây dựng baseline và định lượng lợi ích có thể đạt được từ tối ưu cục bộ.
- Ước lượng chi phí kỹ thuật, hạ tầng và vận hành của một thay đổi kiến trúc.
- So sánh scale-up, read replica, cache, partitioning, sharding và read model theo workload.
- Đánh giá tác động của replication lag, cache staleness, cross-shard operation và eventual consistency.
- Xác định ngưỡng mà tối ưu truy vấn không còn đủ và thay đổi kiến trúc trở nên hợp lý.
- Lập thử nghiệm có đối chứng, kế hoạch triển khai, rollback và tiêu chí dừng.

## 1. Hai nhóm giải pháp và câu hỏi cần trả lời

**Tối ưu truy vấn** cải thiện cách hệ thống hiện tại đọc, lọc, nối, sắp xếp, tổng hợp hoặc ghi dữ liệu. Các thay đổi thường gồm sửa SQL, tạo hoặc điều chỉnh index, cập nhật thống kê, giảm số round trip, rút ngắn transaction, phân trang theo khóa và loại bỏ công việc không cần thiết.

**Thay đổi kiến trúc** thay đổi cách phân phối, lưu trữ hoặc phục vụ dữ liệu giữa các thành phần. Ví dụ: tăng tài nguyên máy chủ, thêm read replica, đưa cache vào đường đọc, phân vùng dữ liệu, chia dữ liệu qua nhiều node, tách read model hoặc chuyển workload phân tích sang hệ thống riêng.

Hai nhóm giải pháp có thể phối hợp. Một hệ thống có thể tối ưu truy vấn trước, sau đó dùng read replica để mở rộng tải đọc còn lại. Một hệ thống sharding vẫn cần index và SQL tốt trên từng shard. Kiến trúc mới không loại bỏ nhu cầu tối ưu truy vấn.

Trước khi chọn hướng, cần trả lời bốn câu hỏi:

1. **Nút thắt nằm ở đâu?** CPU, I/O, memory, lock, connection pool, network, kế hoạch truy vấn hay giới hạn phân phối tải?
2. **Có thể cải thiện bao nhiêu trong kiến trúc hiện tại?** Một truy vấn đang đọc thừa 99% dữ liệu có thể được cải thiện rất nhiều mà chưa cần thêm node.
3. **Phần tải còn lại có vượt năng lực hiện tại không?** Sau khi loại bỏ công việc lãng phí, hệ thống còn thiếu năng lực đọc/ghi, dung lượng hay khả năng cô lập workload nào?
4. **Lợi ích có bù chi phí và rủi ro không?** Cần tính cả phát triển, migration, giám sát, đồng bộ, trực vận hành, sự cố và chi phí cloud/hạ tầng.

## 2. Xác định vấn đề trước khi chọn giải pháp

Một triệu chứng như “database chậm” không đủ để quyết định thay đổi kiến trúc. Cùng một biểu hiện có thể đến từ nguyên nhân rất khác nhau.

| Triệu chứng | Nguyên nhân có thể | Hướng điều tra ban đầu |
|---|---|---|
| Một endpoint chậm, các endpoint khác bình thường | Một SQL cụ thể, index thiếu, plan regression hoặc N+1 query | Query fingerprint, trace, `EXPLAIN (ANALYZE, BUFFERS)` |
| Mọi truy vấn đều chậm vào giờ cao điểm | CPU/I/O bão hòa, quá nhiều connection, memory pressure | Throughput, utilization, queue depth, pool pending, wait events |
| Truy vấn đọc chậm dù CPU thấp | Storage latency, cache miss, lock wait hoặc network | Buffer read, I/O latency, wait event, blocking chain |
| Ghi chậm và nhiều phiên chờ nhau | Hot row, transaction dài, deadlock hoặc index maintenance | Lock graph, transaction age, WAL rate, write latency |
| Tải đọc tăng theo số người dùng | Năng lực đọc tập trung tại primary hoặc truy vấn quét lớn | Read/write ratio, top queries, replica/cache suitability |
| Dung lượng tăng nhanh | Retention, dữ liệu lặp, index, WAL, temp hoặc bloat | Growth rate theo relation/volume, WAL retention, temp usage |
| Chậm sau lần deploy gần đây | Thay đổi SQL, schema, statistics, parameter hoặc application pattern | So sánh plan, query count, release diff và metric trước/sau |

Nếu chỉ một câu truy vấn chậm, thêm read replica thường không sửa được access path kém. Nếu mọi truy vấn đều chậm vì CPU đã bão hòa trong thời gian dài dù các plan hợp lý, tăng năng lực hoặc phân phối workload có thể cần thiết.

### 2.1. Đo ở cả mức request và database

Ở tầng ứng dụng, ghi nhận:

- Request rate và throughput theo endpoint.
- p50, p95, p99 và tỷ lệ timeout.
- Thời gian chờ connection pool và thời gian thực thi SQL.
- Số câu SQL trên mỗi request, số round trip và kích thước kết quả.
- Số lần retry, cancellation và lỗi kết nối.

Ở tầng database, ghi nhận:

- Top SQL theo tổng thời gian, số lần gọi và thời gian trung bình.
- Estimated rows so với actual rows trong execution plan.
- Buffer hit/read, số trang đọc, sort/hash spill và temp bytes.
- CPU, memory, IOPS, throughput và storage latency.
- Lock wait, deadlock, transaction age và số connection đang hoạt động.
- WAL generation, commit latency, checkpoint và replication lag nếu có.

Đo theo cùng một khoảng thời gian để liên hệ triệu chứng ở ứng dụng với hoạt động database. Một truy vấn chạy 2 giây nhưng chỉ gọi một lần mỗi ngày có thể ít quan trọng hơn truy vấn 30 ms được gọi 20.000 lần mỗi phút.

### 2.2. Xây baseline có thể so sánh

Baseline là tập số liệu trước thay đổi, được thu thập dưới tải đại diện. Ít nhất cần có:

| Nhóm | Chỉ số baseline |
|---|---|
| Trải nghiệm | p50/p95/p99, timeout và error rate |
| Năng lực | Requests/s, transactions/s, rows/s hoặc GB/s |
| Truy vấn | Tổng thời gian theo fingerprint, calls, actual rows, buffers |
| Tài nguyên | CPU, memory, I/O latency, IOPS, queue depth |
| Đồng thời | Active connections, pool pending, lock waits, deadlocks |
| Vận hành | Chi phí máy chủ, storage, replica, cache và thời gian quản trị |

Ghi rõ kích thước dữ liệu, trạng thái cache, số client, concurrency, phiên bản phần mềm và cấu hình. Nếu workload hoặc dữ liệu khác nhau giữa hai lần thử, kết quả so sánh có thể sai lệch.

## 3. Đánh giá cơ hội tối ưu truy vấn

Trước khi thay đổi kiến trúc, hãy xác định phần công việc có thể loại bỏ hoặc làm rẻ hơn trong hệ thống hiện tại.

### 3.1. Đọc execution plan

Trong PostgreSQL, một truy vấn đại diện có thể được kiểm tra bằng:

```sql
EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
SELECT order_id, created_at, total_amount
FROM orders
WHERE customer_id = 42
  AND created_at >= TIMESTAMPTZ '2026-10-01 00:00:00+00'
ORDER BY created_at DESC
LIMIT 50;
```

Quan sát:

- Scan type: sequential scan, index scan, bitmap scan hoặc partition scan.
- Estimated rows so với actual rows: sai lệch lớn có thể dẫn tới join order hoặc thuật toán join không phù hợp.
- Rows Removed by Filter: engine đã đọc nhiều dòng rồi loại bỏ bao nhiêu.
- Buffers hit/read: lượng truy cập cache và đọc từ storage.
- Sort/hash: có dùng nhiều memory hoặc spill ra disk không.
- Loops: một node có bị thực thi lặp nhiều lần không.
- Planning Time và Execution Time: phân biệt chi phí lập kế hoạch với thực thi.

`EXPLAIN ANALYZE` thực thi câu lệnh. Với `UPDATE`, `DELETE` hoặc câu lệnh có tác dụng phụ, cần dùng transaction có thể rollback hoặc môi trường thử nghiệm phù hợp. Không chạy một truy vấn nặng trên production chỉ để lấy plan mà chưa đánh giá tác động.

### 3.2. Sửa SQL và access path

Các cơ hội thường gặp:

- Chỉ chọn các cột cần thiết thay vì `SELECT *`.
- Đẩy điều kiện lọc gần nguồn dữ liệu và tránh áp dụng hàm lên cột khiến index không được dùng khi có thể viết predicate tương đương.
- Dùng điều kiện range trên kiểu dữ liệu gốc, chẳng hạn khoảng thời gian nửa mở.
- Tránh N+1 query bằng join hoặc batch fetch phù hợp.
- Dùng keyset pagination cho luồng duyệt tuần tự ở trang sâu.
- Giảm sort, aggregate hoặc join lặp không cần thiết.
- Chọn batch size để giảm round trip nhưng không giữ transaction quá lâu.
- Tránh cập nhật cùng giá trị nếu không có thay đổi thực tế.

Ví dụ, truy vấn sau áp dụng hàm lên cột thời gian:

```sql
SELECT order_id
FROM orders
WHERE date(created_at) = DATE '2026-10-15';
```

Một cách viết range thường dễ tận dụng B-tree index trên `created_at` hơn:

```sql
SELECT order_id
FROM orders
WHERE created_at >= TIMESTAMPTZ '2026-10-15 00:00:00+00'
  AND created_at <  TIMESTAMPTZ '2026-10-16 00:00:00+00';
```

Mốc thời gian cần được tạo theo timezone nghiệp vụ. Viết lại SQL chỉ có lợi nếu semantics không đổi và execution plan thực sự tốt hơn.

### 3.3. Index và thống kê

Index có thể giảm số dòng phải đọc, hỗ trợ thứ tự và tránh sort. Nhưng index cũng chiếm storage, tăng WAL và làm các thao tác ghi tốn thêm công việc.

Ví dụ index ghép cho bộ lọc khách hàng và thứ tự thời gian:

```sql
CREATE INDEX idx_orders_customer_created
ON orders (customer_id, created_at DESC);
```

Chỉ tạo index sau khi xem query pattern, selectivity, thứ tự cột và chi phí ghi. Một index không được dùng hoặc trùng lặp có thể làm hệ thống ghi chậm hơn và tăng dung lượng.

Thống kê cũng quan trọng. Nếu dữ liệu thay đổi mạnh nhưng planner dùng thống kê cũ, estimated rows có thể sai. `ANALYZE` hoặc extended statistics phù hợp có thể cải thiện kế hoạch mà không cần thêm node.

### 3.4. Tối ưu transaction và tranh chấp

Truy vấn ghi có thể chậm do giữ khóa lâu hoặc tranh một dòng nóng. Các biện pháp gồm:

- Rút ngắn transaction và không gọi dịch vụ ngoài khi đang giữ khóa.
- Khóa nhiều dòng theo một thứ tự nhất quán.
- Chỉ cập nhật các dòng thực sự thay đổi.
- Chia batch để giới hạn transaction và WAL.
- Phân tán counter hoặc summary row nóng nếu nghiệp vụ cho phép.
- Dùng `NOWAIT`/`SKIP LOCKED` đúng mục đích, không áp dụng cho truy vấn cần đầy đủ dữ liệu.

Nếu nguyên nhân là lock contention, thêm read replica không giải quyết được transaction ghi đang chờ khóa trên primary.

### 3.5. Tối ưu có thể giải quyết phần lớn tải lãng phí

Giả sử một endpoint gọi 40 truy vấn nhỏ cho mỗi request, mỗi truy vấn trung bình 10 ms. Dù mỗi SQL riêng lẻ nhanh, tổng round trip và pool occupancy có thể lớn. Gộp truy vấn hoặc batch fetch có thể giảm đáng kể số lần gọi mà không thay đổi kiến trúc.

Tương tự, một truy vấn quét 10 triệu dòng để trả 20 dòng có thể được cải thiện bằng index và predicate phù hợp. Trong cả hai trường hợp, thay đổi cục bộ có thể tạo lợi ích lớn hơn việc thêm máy chủ.

## 4. Khi nào tối ưu truy vấn là đủ?

Tối ưu truy vấn thường là lựa chọn phù hợp khi:

- Một số ít query fingerprint chiếm phần lớn tổng database time.
- Plan có dấu hiệu đọc thừa, ước lượng sai hoặc sort/hash spill không cần thiết.
- Số round trip hoặc query count trên mỗi request cao bất thường.
- Database còn headroom CPU/I/O sau khi sửa access path.
- Tải tăng chủ yếu do một endpoint hoặc một thao tác chưa hiệu quả.
- Có thể đáp ứng SLA bằng thay đổi SQL/index/cấu hình nhỏ với rủi ro thấp.
- Dữ liệu và workload vẫn phù hợp với một primary database.

Một quy tắc hữu ích là ưu tiên query chiếm tổng thời gian lớn, không chỉ query có latency cao nhất. Nếu một truy vấn 5 giây chạy một lần/ngày, còn truy vấn 20 ms chạy 5.000 lần/giây, truy vấn thứ hai có thể tiêu tốn nhiều tài nguyên hơn.

### 4.1. Đo tác động theo tổng thời gian

Có thể ước lượng tổng thời gian tiêu thụ của một fingerprint trong cửa sổ đo:

\[
TotalQueryTime \approx Calls \times MeanExecutionTime
\]

Ví dụ:

| Query | Số lần gọi/phút | Mean time | Tổng thời gian/phút |
|---|---:|---:|---:|
| A | 60 | 1.000 ms | 60 giây |
| B | 6.000 | 20 ms | 120 giây |
| C | 300 | 100 ms | 30 giây |

Query B có latency riêng thấp nhưng tiêu thụ tổng thời gian lớn nhất trong ví dụ. Công thức là ước lượng để xếp hạng; các truy vấn chạy đồng thời và số liệu thống kê có thể khiến tổng thời gian cộng dồn không bằng thời gian đồng hồ thực tế.

### 4.2. Lợi ích tối ưu có giới hạn

Một truy vấn không thể được tối ưu vô hạn. Khi đã loại bỏ scan thừa, dùng access path hợp lý, giảm round trip và xử lý đúng concurrency, giới hạn còn lại có thể là dung lượng CPU, I/O, memory bandwidth hoặc năng lực ghi của một node.

Nếu tải tiếp tục tăng nhanh hơn năng lực của máy chủ, tối ưu cục bộ chỉ trì hoãn thời điểm chạm giới hạn. Khi đó cần xem xét mở rộng năng lực hoặc phân phối workload.

## 5. Đánh giá chi phí thay đổi kiến trúc

Một thay đổi kiến trúc thường có chi phí vượt xa phần code được triển khai. Cần tính đủ các nhóm sau.

### 5.1. Chi phí phát triển và migration

- Thiết kế schema, data flow, API và cơ chế routing mới.
- Viết dual-write, backfill hoặc chuyển dữ liệu hiện hữu.
- Thay đổi ứng dụng, query repository và quy trình triển khai.
- Xử lý dữ liệu trùng, thiếu, sai thứ tự hoặc không đồng bộ.
- Viết công cụ đối soát và chuyển traffic theo giai đoạn.
- Kiểm thử failover, restore, rebalancing và tình huống mạng bị phân vùng.

### 5.2. Chi phí vận hành

- Thêm node, storage, network, license hoặc dịch vụ managed.
- Theo dõi replication lag, cache hit rate, shard health và queue backlog.
- Backup/restore nhiều thành phần và kiểm tra tính nhất quán giữa chúng.
- Tăng số cảnh báo, runbook, dashboard và tình huống trực vận hành.
- Nâng cấp, vá lỗi, thay đổi schema và quản lý phiên bản giữa các node.
- Tăng yêu cầu kỹ năng và thời gian xử lý sự cố.

### 5.3. Chi phí về tính đúng đắn và trải nghiệm

Một kiến trúc phân tán có thể thay đổi semantics mà ứng dụng đang dựa vào:

- Read replica có thể trả dữ liệu cũ hơn primary.
- Cache có thể giữ giá trị cũ sau khi dữ liệu nguồn thay đổi.
- Sharding làm truy vấn liên shard, unique constraint và transaction nhiều shard phức tạp hơn.
- Read model bất đồng bộ tạo độ trễ đồng bộ.
- Failover có thể làm gián đoạn kết nối và khiến client không biết transaction đã commit hay chưa.

Các vấn đề này cần được thể hiện thành yêu cầu sản phẩm và hợp đồng API, không chỉ xử lý bằng cấu hình hạ tầng.

## 6. So sánh các hướng mở rộng

### 6.1. Scale-up (mở rộng theo chiều dọc)

Scale-up tăng CPU, RAM, IOPS hoặc dung lượng cho một database node.

**Lợi ích:**

- Ít thay đổi ứng dụng và mô hình dữ liệu.
- Không tạo thêm replication lag hay routing logic chỉ vì tăng tài nguyên.
- Có thể cải thiện nhiều workload cùng lúc nếu đúng tài nguyên đang thiếu.
- Thường đơn giản hơn sharding hoặc CQRS.

**Chi phí và giới hạn:**

- Phần cứng lớn hơn thường có chi phí cao và có giới hạn trên.
- Một node vẫn là miền lỗi chính nếu chưa có HA.
- Tăng RAM không sửa được query plan đọc thừa hoặc lock contention.
- Tăng CPU không giải quyết thiết bị WAL/volume đang bị giới hạn I/O.
- Nâng cấp lớn có thể cần restart, failover hoặc thay đổi maintenance window.

Scale-up phù hợp khi workload vẫn tập trung hợp lý trên một node và bottleneck là năng lực tài nguyên có thể mở rộng.

### 6.2. Read replica

Read replica nhận thay đổi từ primary qua replication và phục vụ một phần truy vấn đọc. Nó có thể mở rộng năng lực đọc và tách báo cáo khỏi primary.

**Lợi ích:**

- Phân phối truy vấn đọc sang nhiều node.
- Cô lập một số workload báo cáo hoặc truy vấn dài.
- Có thêm bản sao phục vụ HA hoặc đọc, tùy kiến trúc.
- Giảm áp lực CPU/I/O đọc trên primary nếu routing phù hợp.

**Chi phí và giới hạn:**

- Phát sinh chi phí node, storage, network và giám sát.
- Replica có thể lag; truy vấn đọc sau ghi có thể không thấy thay đổi vừa commit.
- Một số thao tác trên standby có thể bị conflict với replay WAL.
- Write workload vẫn tập trung ở primary trong kiến trúc primary/replica thông thường.
- Ứng dụng phải định tuyến truy vấn theo yêu cầu nhất quán.

Không gửi tất cả truy vấn đọc sang replica một cách máy móc. Truy vấn cần read-your-writes, quyết định giao dịch hoặc dữ liệu mới nhất có thể phải đọc primary hoặc dùng cơ chế chờ replica bắt kịp.

### 6.3. Cache

Cache lưu kết quả hoặc dữ liệu thường đọc ở một tầng gần ứng dụng hơn, giảm số lần truy vấn database.

**Lợi ích:**

- Giảm tải cho query lặp lại và dữ liệu có tỷ lệ đọc cao.
- Có thể giảm latency do tránh network/database round trip.
- Hấp thụ một phần burst nếu cache có hit rate tốt.

**Chi phí và giới hạn:**

- Cần chính sách invalidation, TTL và xử lý cache miss.
- Có thể trả dữ liệu cũ hoặc không nhất quán giữa các key.
- Cache stampede xảy ra khi nhiều request cùng làm mới một key hết hạn.
- Cache thêm một hệ thống cần giám sát, capacity và bảo mật.
- Dữ liệu có cardinality cao hoặc ít được đọc lại có thể không đáng cache.

Cache phù hợp với dữ liệu đọc lặp lại, có thể định nghĩa rõ độ cũ chấp nhận được và có cách xử lý invalidation.

### 6.4. Partitioning

Partitioning chia một bảng logic thành nhiều phần vật lý theo range, list hoặc hash. Trong PostgreSQL, partition pruning có thể loại bỏ partition không liên quan nếu predicate phù hợp.

**Lợi ích:**

- Giảm vùng dữ liệu cần scan khi truy vấn lọc theo partition key.
- Quản lý retention bằng detach/drop partition thay vì xóa hàng triệu dòng.
- Có thể hỗ trợ bảo trì và phân bổ dữ liệu theo thời gian hoặc tenant.
- Tổ chức index và lifecycle theo từng partition.

**Chi phí và giới hạn:**

- Truy vấn không lọc theo partition key có thể vẫn phải truy cập nhiều partition.
- Quản lý partition, index, constraint và migration phức tạp hơn.
- Quá nhiều partition có thể tăng planning overhead và operational overhead.
- Partitioning không tự động phân phối tải ghi sang nhiều máy chủ nếu vẫn nằm trên cùng một database instance.
- Thiết kế partition key sai có thể tạo partition nóng hoặc mất cân bằng.

Partitioning chủ yếu là chiến lược tổ chức dữ liệu và quản trị vòng đời; không đồng nghĩa sharding.

### 6.5. Sharding

Sharding chia dữ liệu qua nhiều database node theo shard key, ví dụ `tenant_id` hoặc `customer_id`. Mỗi shard chịu trách nhiệm cho một phần dữ liệu.

**Lợi ích:**

- Mở rộng dung lượng và throughput ghi/đọc bằng cách phân phối dữ liệu.
- Giảm kích thước tập dữ liệu trên mỗi node.
- Có thể cô lập tenant hoặc workload theo shard.

**Chi phí và giới hạn:**

- Cần routing layer và quản lý shard map.
- Cross-shard join, aggregate và transaction khó hơn.
- Unique constraint toàn cục khó bảo đảm nếu khóa không chứa shard key hoặc không có dịch vụ phối hợp.
- Rebalancing khi thêm/bớt shard có thể tốn thời gian và I/O.
- Shard key phân bố lệch tạo hot shard; một tenant lớn có thể vượt năng lực node của nó.
- Backup, restore, schema migration và failover phải được phối hợp trên nhiều shard.

Sharding phù hợp khi một node đã chạm giới hạn bền vững, dữ liệu và workload có khóa phân vùng tự nhiên, đồng thời ứng dụng có thể chấp nhận hoặc xử lý chi phí phân tán.

### 6.6. Read model, CQRS và materialized view

Một read model lưu dữ liệu theo cách tối ưu cho truy vấn hoặc màn hình cụ thể. Nó có thể là bảng tổng hợp, materialized view, index tìm kiếm hoặc database riêng.

**Lợi ích:**

- Giảm join và aggregate lặp lại.
- Tách workload phân tích khỏi transaction path.
- Cho phép tổ chức dữ liệu theo nhu cầu đọc thay vì chỉ theo mô hình ghi.

**Chi phí và giới hạn:**

- Phải cập nhật read model khi nguồn thay đổi.
- Đồng bộ bất đồng bộ có thể tạo eventual consistency.
- Cần xử lý event duplication, ordering, retry, replay và rebuild.
- Có thêm storage, pipeline, dashboard và runbook.

Materialized view có thể được refresh theo lịch hoặc cơ chế phù hợp với engine. Read model theo sự kiện có thể cập nhật gần thời gian thực nhưng cần idempotency và giám sát lag.

### 6.7. Tách workload phân tích

Nếu truy vấn phân tích quét dữ liệu lớn cạnh tranh CPU/I/O với OLTP, có thể đưa dữ liệu sang data warehouse hoặc query engine riêng qua ETL/ELT, CDC hoặc replication.

Điều này giúp cô lập tài nguyên và dùng columnar storage, nhưng phát sinh pipeline, độ trễ dữ liệu, chi phí lưu trữ và trách nhiệm đối soát. Không nên đưa mọi báo cáo sang hệ thống riêng nếu một materialized view hoặc index đã đáp ứng SLA với chi phí thấp hơn.

## 7. Bảng so sánh nhanh

| Giải pháp | Vấn đề phù hợp | Độ phức tạp tương đối | Rủi ro nhất quán chính |
|---|---|---|---|
| SQL/index/statistics tuning | Truy vấn kém hiệu quả, đọc thừa, plan xấu | Thấp đến trung bình | Thường thấp nếu giữ nguyên semantics |
| Scale-up | Một node thiếu CPU/RAM/I/O nhưng workload vẫn tập trung | Thấp đến trung bình | Ít thay đổi semantics; vẫn cần HA |
| Read replica | Tải đọc vượt năng lực primary | Trung bình | Replication lag, stale read |
| Cache | Dữ liệu đọc lặp, có thể chấp nhận TTL/invalidation | Trung bình | Cache staleness và invalidation race |
| Partitioning | Bảng lớn, truy vấn/retention theo partition key | Trung bình | Thường không đổi semantics nếu thiết kế đúng; routing/pruning cần kiểm tra |
| Materialized view/read model | Join/aggregate lặp lại, dashboard có SLA riêng | Trung bình đến cao | Refresh lag hoặc eventual consistency |
| Sharding | Một node không còn đủ năng lực hoặc dung lượng dài hạn | Cao | Cross-shard transaction, unique và routing |
| Data warehouse riêng | Phân tích nặng cạnh tranh với OLTP | Cao | Dữ liệu trễ, pipeline sai lệch hoặc thiếu dữ liệu |

Độ phức tạp trong bảng là tương đối. Một hệ thống managed có thể giảm công việc vận hành của replica nhưng không loại bỏ vấn đề nhất quán hoặc chi phí ứng dụng.

## 8. Định lượng lợi ích và tổng chi phí sở hữu

Không nên so sánh một thay đổi SQL vài giờ với một kiến trúc mới chỉ bằng chi phí triển khai ban đầu. Hãy tính lợi ích và chi phí trong cùng khoảng thời gian, ví dụ 12 hoặc 24 tháng.

### 8.1. Lợi ích kỹ thuật

Đo các thay đổi:

- p95/p99 của request và query.
- Throughput ở cùng mức concurrency.
- CPU seconds hoặc I/O bytes cho mỗi request/giao dịch.
- Số connection cần thiết để đạt cùng throughput.
- Tỷ lệ timeout, deadlock và lỗi.
- Headroom còn lại trước khi chạm giới hạn tài nguyên.
- Khả năng chịu burst và thời gian phục hồi sau lỗi.

Một thay đổi có thể giảm query latency nhưng không tăng throughput nếu bottleneck chuyển sang connection pool hoặc network. Vì vậy cần đánh giá toàn đường đi.

### 8.2. Lợi ích kinh doanh

Quy đổi cải thiện kỹ thuật thành tác động có ý nghĩa:

- Giảm số request lỗi hoặc timeout.
- Giảm thời gian người dùng chờ.
- Tăng số giao dịch xử lý được trong giờ cao điểm.
- Tránh phải mua thêm dung lượng hoặc máy chủ trong một khoảng thời gian.
- Giảm thời gian batch/report hoàn tất.
- Giảm nguy cơ vi phạm SLA hoặc mất doanh thu do hệ thống không đáp ứng.

Không gán giá trị tiền tệ cho một cải thiện latency nếu chưa có mô hình liên hệ tới trải nghiệm, chuyển đổi hoặc chi phí vận hành.

### 8.3. Tổng chi phí sở hữu (TCO)

Một mô hình đơn giản:

\[
TCO = Infrastructure + Engineering + Operations + Migration + RiskCost
\]

Trong đó:

- **Infrastructure:** compute, storage, network, license, cache, replica và backup.
- **Engineering:** thiết kế, code, kiểm thử, migration, công cụ và tài liệu.
- **Operations:** giám sát, trực sự cố, nâng cấp, backup/restore, capacity planning.
- **Migration:** dual-write, backfill, cutover, đối soát và thời gian chạy song song.
- **RiskCost:** chi phí kỳ vọng từ lỗi dữ liệu, downtime, stale read, rollback hoặc độ phức tạp mới.

Chi phí rủi ro có thể ước lượng theo xác suất và tác động, nhưng cần ghi rõ giả định. Không nên bỏ qua chỉ vì khó đo chính xác.

### 8.4. Giá trị của headroom

Một giải pháp có thể không giảm latency nhiều nhưng tạo thêm headroom để chịu tăng trưởng. Ví dụ, query tuning giảm CPU mỗi request 40%, giúp cùng một node phục vụ gấp nhiều lần số request trước khi bão hòa. Lợi ích này có thể trì hoãn việc mở rộng hạ tầng.

Ngược lại, thêm replica có thể tăng năng lực đọc nhưng tăng chi phí cố định và lag monitoring. Hãy so sánh cost per request hoặc cost per transaction ở mức tải mục tiêu.

## 9. Ngưỡng chuyển từ tối ưu truy vấn sang thay đổi kiến trúc

Không có một con số phần trăm cố định áp dụng cho mọi hệ thống. Có thể cân nhắc thay đổi kiến trúc khi phần lớn điều kiện sau đã được chứng minh:

1. Top query đã được tối ưu và execution plan hợp lý.
2. Không còn scan, join, sort hoặc round trip lãng phí có tác động lớn.
3. Index và thống kê đã phù hợp với workload, chi phí ghi của index cũng được tính.
4. Transaction và lock contention đã được xử lý ở mức ứng dụng/schema có thể.
5. Database vẫn chạm giới hạn CPU, I/O, memory, connection hoặc dung lượng ở tải bình thường/đỉnh.
6. Tốc độ tăng tải vượt khả năng scale-up hoặc tối ưu cục bộ trong khoảng dự báo.
7. Có một hướng kiến trúc cụ thể giải quyết đúng giới hạn đó.
8. Chi phí và rủi ro của hướng mới thấp hơn lợi ích dự kiến trong thời gian sử dụng.

Ví dụ:

- Nếu CPU cao vì một truy vấn scan toàn bảng do thiếu index, sửa truy vấn/index trước.
- Nếu CPU vẫn bão hòa sau khi plan tốt và workload đọc tăng tuyến tính, read replica hoặc tách read workload có thể phù hợp.
- Nếu một bảng lịch sử rất lớn nhưng truy vấn luôn lọc theo thời gian, partitioning có thể giúp pruning và retention.
- Nếu ghi tập trung vào một node đã đạt giới hạn bền vững và dữ liệu có shard key tự nhiên, mới xem xét sharding.
- Nếu dashboard tính cùng aggregate trên dữ liệu lịch sử liên tục, summary table hoặc read model có thể phù hợp hơn việc tăng máy chủ primary.

## 10. Ví dụ quyết định: API đọc đơn hàng tăng tải

Một hệ thống thương mại điện tử có API danh sách đơn hàng. Khi số người dùng tăng, p95 tăng từ 120 ms lên 900 ms. Database CPU đạt 85% vào giờ cao điểm, read I/O tăng và connection pool có hàng đợi.

### 10.1. Chẩn đoán ban đầu

Trace cho thấy mỗi request gọi nhiều truy vấn để lấy đơn hàng, khách hàng và trạng thái. Một truy vấn danh sách dùng `OFFSET` lớn; execution plan đọc nhiều dòng rồi bỏ qua. Một số truy vấn lặp lại cùng thông tin khách hàng.

Trước khi thêm replica, nhóm kỹ thuật:

- Chuyển phân trang sâu sang keyset pagination với thứ tự ổn định.
- Tạo index ghép theo tenant/customer và thời gian sau khi kiểm tra selectivity.
- Gộp truy vấn N+1 thành truy vấn phù hợp hoặc batch fetch.
- Chỉ lấy các cột cần hiển thị.
- Đo lại pool wait và query count.

Giả sử sau thay đổi, p95 giảm còn 250 ms, CPU giảm còn 55% ở cùng tải. Đây là cải thiện đáng kể mà chưa cần thay đổi kiến trúc.

### 10.2. Tải tiếp tục tăng

Ba tháng sau, số request tăng gấp đôi. Top query vẫn có plan hợp lý nhưng primary CPU và read I/O lại gần bão hòa. Phân tích cho thấy phần lớn workload là đọc danh sách và dashboard; ghi đơn hàng vẫn chiếm tỷ lệ nhỏ hơn và cần tính nhất quán mạnh.

Read replica có thể phù hợp cho một phần truy vấn đọc, với các điều kiện:

- API xác định truy vấn nào chấp nhận dữ liệu trễ.
- Request vừa ghi xong có thể đọc primary trong một khoảng thời gian hoặc dùng cơ chế read-your-writes.
- Dashboard chấp nhận replica lag theo một ngưỡng rõ.
- Có metric replication lag và cơ chế fallback khi replica không theo kịp.
- Tổng số connection và tải trên replica được giới hạn.

Nhóm có thể đưa dashboard và truy vấn lịch sử sang replica trước, sau đó chuyển một phần API đọc không cần dữ liệu mới nhất. Primary vẫn phục vụ ghi và các truy vấn cần read-your-writes.

### 10.3. Đánh giá sau khi thêm replica

So sánh ở cùng request rate:

- p95/p99 API và dashboard.
- CPU/I/O trên primary và replica.
- Replication lag và số truy vấn bị conflict trên standby.
- Pool active/pending của từng node.
- Tổng chi phí compute, storage và vận hành.
- Tỷ lệ fallback về primary.

Nếu replica giảm tải primary nhưng lag vượt yêu cầu sản phẩm hoặc query routing làm lỗi read-your-writes, cần điều chỉnh phạm vi workload hoặc chọn read model khác.

## 11. Rủi ro khi thay đổi kiến trúc

### 11.1. Read replica và stale read

Replication bất đồng bộ có thể khiến replica chưa nhận hoặc replay thay đổi mới nhất. Một luồng người dùng có thể vừa cập nhật đơn hàng rồi đọc lại từ replica và thấy trạng thái cũ.

Các cách xử lý:

- Đọc từ primary trong request cần read-your-writes.
- Gắn session consistency token hoặc LSN và chỉ đọc replica sau khi replica replay tới vị trí cần thiết, nếu hệ thống hỗ trợ.
- Định tuyến truy vấn theo mức nhất quán và nghiệp vụ.
- Chấp nhận dữ liệu trễ rõ ràng cho dashboard hoặc báo cáo.

Không giả định mọi read replica đều có độ trễ bằng 0.

### 11.2. Cache invalidation và stampede

Cache tăng tốc truy vấn lặp lại nhưng phải có chính sách hết hạn và làm mới. Khi nhiều request cùng gặp cache miss, chúng có thể cùng truy vấn database và tạo stampede. Có thể dùng single-flight/request coalescing, stale-while-revalidate hoặc giới hạn concurrency làm mới.

Nếu invalidation không đáng tin cậy, TTL là giới hạn độ cũ tối đa tương đối, nhưng không bảo đảm dữ liệu mới ngay sau update. Nghiệp vụ cần dữ liệu tức thời phải đọc nguồn chính hoặc dùng cơ chế đồng bộ phù hợp.

### 11.3. Sharding và phân bố lệch

Shard key quyết định nơi lưu dữ liệu. Nếu nhiều request tập trung vào một tenant hoặc một khoảng khóa, một shard có thể nóng trong khi các shard khác nhàn rỗi. Thêm node không giúp nếu routing vẫn dồn vào một shard.

Trước khi sharding, kiểm tra:

- Phân bố cardinality và skew của shard key.
- Truy vấn có thể định tuyến tới một shard hay thường xuyên cross-shard.
- Unique key và foreign key cần bảo đảm ở phạm vi nào.
- Cách xử lý transaction nhiều shard.
- Quy trình rebalancing và chuyển shard key.
- Backup, restore và disaster recovery trên toàn cụm.

### 11.4. Partitioning và chi phí planner

Partitioning chỉ giúp giảm công việc khi query predicate cho phép pruning. Nếu truy vấn không lọc partition key hoặc điều kiện bị viết theo cách planner không nhận diện được, engine có thể phải xét nhiều partition. Quá nhiều partition cũng có thể làm planning và quản trị phức tạp.

### 11.5. Tách read/write và eventual consistency

CQRS hoặc read model có thể tạo dữ liệu đọc bất đồng bộ. Khi pipeline chậm, dashboard hoặc API có thể hiển thị trạng thái cũ. Cần định nghĩa lag tối đa, cách phát hiện dữ liệu thiếu, replay, rebuild và đối soát với nguồn sự thật.

## 12. Quy trình so sánh hai phương án

**Bước 1 — Mô tả vấn đề kinh doanh.** Xác định endpoint, người dùng, SLA, thời điểm tải cao và hậu quả khi không đạt SLA.

**Bước 2 — Thu thập baseline.** Đo p50/p95/p99, throughput, query time, pool wait, CPU, memory, I/O, lock wait, dung lượng và chi phí hiện tại.

**Bước 3 — Xếp hạng nguyên nhân.** Tìm top query theo tổng thời gian, plan kém, scan thừa, N+1, lock contention, storage bottleneck và giới hạn connection.

**Bước 4 — Ước lượng tối ưu cục bộ.** Đề xuất sửa SQL/index/statistics/transaction/batch. Ước lượng lợi ích, phạm vi thay đổi, chi phí ghi và rủi ro semantics.

**Bước 5 — Thử tối ưu trong môi trường đại diện.** Giữ nguyên dữ liệu, workload, concurrency và cache condition; đo lại bằng cùng chỉ số.

**Bước 6 — Xác định giới hạn còn lại.** Nếu bottleneck đã chuyển sang tài nguyên node hoặc tải vượt năng lực dù query đã hợp lý, ghi rõ giới hạn không thể xử lý cục bộ.

**Bước 7 — Đề xuất tối đa vài phương án kiến trúc.** Với mỗi phương án, mô tả thành phần mới, data flow, nhất quán, failure mode, migration, TCO và khả năng rollback.

**Bước 8 — So sánh lợi ích/chi phí.** Dùng cùng thời hạn phân tích, cùng tải mục tiêu và cùng yêu cầu SLA. Tính cả chi phí vận hành và rủi ro.

**Bước 9 — Thử nghiệm nhỏ.** Dùng canary, shadow read, replica cho một nhóm query hoặc partition pilot. Đối chiếu kết quả với nguồn chính.

**Bước 10 — Triển khai từng giai đoạn.** Có feature flag, routing control, giới hạn concurrency, dashboard và ngưỡng rollback.

**Bước 11 — Đánh giá sau triển khai.** Đo lại latency, throughput, error rate, resource headroom, consistency lag, chi phí và thời gian vận hành.

**Bước 12 — Quyết định giữ hoặc hoàn tác.** Chỉ mở rộng khi lợi ích bền vững, dữ liệu đúng và đội vận hành kiểm soát được failure mode.

## 13. Ma trận ra quyết định

| Điều kiện quan sát | Ưu tiên xem xét | Lý do |
|---|---|---|
| Một vài query chiếm phần lớn DB time | SQL/index/statistics tuning | Có thể loại bỏ công việc lãng phí với phạm vi nhỏ |
| N+1 và round trip cao | Batch fetch, join hoặc API/query redesign | Giảm số lần gọi và pool occupancy |
| CPU/RAM/I/O thiếu nhưng plan hợp lý, tải tăng vừa phải | Scale-up | Tăng năng lực mà ít thay đổi semantics |
| Read workload lớn, write workload vừa phải | Read replica | Phân phối tải đọc khỏi primary |
| Cùng một dữ liệu được đọc lặp lại và chấp nhận TTL | Cache | Tránh truy vấn lặp lại |
| Bảng lớn, truy vấn và retention theo thời gian | Partitioning | Pruning và quản lý vòng đời dữ liệu |
| Join/aggregate nặng được lặp lại | Summary table/materialized view/read model | Tính trước hoặc tổ chức dữ liệu cho đường đọc |
| OLTP bị ảnh hưởng bởi dashboard scan lớn | Tách analytical workload | Cô lập CPU/I/O và concurrency |
| Một node đã chạm giới hạn bền vững, dữ liệu phân chia tự nhiên | Sharding | Mở rộng dung lượng và throughput ngang |

Ma trận chỉ định hướng điều tra. Quyết định cuối cùng cần kiểm chứng bằng workload thực tế và yêu cầu nhất quán cụ thể.

## 14. Benchmark và kiểm chứng trước/sau

Một thử nghiệm tốt phải trả lời được liệu giải pháp có giải quyết đúng bottleneck và có tạo ra chi phí mới hay không.

### 14.1. Giữ điều kiện so sánh

- Cùng snapshot hoặc dữ liệu có phân bố tương đương.
- Cùng request mix và query parameters.
- Cùng concurrency và thời gian warm-up.
- Ghi rõ cache nóng/lạnh và trạng thái replica.
- Cùng SLA và ngưỡng lỗi.
- Đo đủ lâu để thấy chu kỳ checkpoint, batch hoặc traffic peak nếu chúng ảnh hưởng kết quả.

### 14.2. So sánh theo hai lớp

**Lớp truy vấn:** execution time, actual rows, buffers, temp spill, query calls, lock wait.

**Lớp hệ thống:** p95/p99 request, throughput, CPU, memory, I/O, connection pool, replication lag, cache hit rate và chi phí.

Không kết luận thành công nếu query nhanh hơn nhưng request vẫn chậm do pool wait, network hoặc một dịch vụ phụ thuộc khác.

### 14.3. Tiêu chí chấp nhận

Trước khi thử, ghi rõ điều kiện đạt, ví dụ:

- p95 endpoint dưới ngưỡng SLA ở tải mục tiêu.
- p99 không tăng vượt giới hạn khi tải đọc/ghi đồng thời.
- Throughput tăng mà không tạo lock wait hoặc error rate mới.
- Replica lag hoặc cache staleness nằm trong giới hạn nghiệp vụ.
- CPU/I/O còn headroom cho tăng trưởng dự kiến.
- Chi phí hạ tầng và vận hành nằm trong ngân sách.
- Có thể rollback hoặc chuyển traffic về đường cũ trong thời gian xác định.

Các con số phải lấy từ SLA và yêu cầu thực tế của hệ thống, không dùng một bộ ngưỡng chung cho mọi ứng dụng.

## 15. Những nhầm lẫn thường gặp

- **“Database chậm thì phải sharding.”** Một query hoặc index kém có thể là nguyên nhân; sharding làm tăng độ phức tạp mà không sửa access path.
- **“Thêm read replica sẽ làm ghi nhanh hơn.”** Trong mô hình primary/replica, ghi vẫn chủ yếu đi qua primary; replica chủ yếu mở rộng đọc.
- **“Scale-up giải quyết được mọi bottleneck.”** Tăng CPU không sửa lock contention, query logic sai hoặc WAL volume chậm.
- **“Partitioning là sharding.”** Partitioning thường chia relation trong cùng một database; sharding phân phối dữ liệu qua nhiều node.
- **“Cache luôn giảm tải.”** Cache miss, stampede và invalidation sai có thể tăng tải hoặc trả dữ liệu cũ.
- **“Read replica luôn trả dữ liệu mới nhất.”** Replication bất đồng bộ có thể lag; phải định tuyến theo consistency requirement.
- **“Tối ưu query chỉ cần giảm thời gian một lần chạy.”** Cần xem tổng calls, tổng database time, concurrency và tác động ghi.
- **“Index càng nhiều càng tốt.”** Index tăng storage, WAL và chi phí INSERT/UPDATE/DELETE.
- **“Tách read model không cần đối soát.”** Pipeline bất đồng bộ cần replay, deduplication, lag monitoring và kiểm tra sai lệch.
- **“Thêm node là tăng throughput tuyến tính.”** Skew, network, coordination và hot key có thể giới hạn mức mở rộng.
- **“Benchmark thấp tải đủ để quyết định.”** Nút thắt thường chỉ xuất hiện ở concurrency và dữ liệu production-like.
- **“Chi phí kiến trúc chỉ là tiền máy chủ.”** Engineering, migration, trực vận hành, backup, restore và rủi ro nhất quán cũng là chi phí.

## 16. Checklist chọn tối ưu truy vấn hay thay đổi kiến trúc

- [ ] Đã xác định endpoint/workload và yêu cầu SLA cụ thể.
- [ ] Đã có baseline p50/p95/p99, throughput, error rate và tài nguyên.
- [ ] Đã xếp hạng query theo tổng thời gian và số lần gọi.
- [ ] Đã đọc execution plan và kiểm tra actual rows, buffers, sort/hash spill.
- [ ] Đã xem index, statistics, N+1, transaction duration và lock contention.
- [ ] Đã thử các tối ưu cục bộ có rủi ro thấp và đo lại.
- [ ] Đã xác định bottleneck còn lại là giới hạn tài nguyên, phân phối tải hay dung lượng.
- [ ] Đã mô tả ít nhất một phương án kiến trúc giải quyết đúng giới hạn đó.
- [ ] Đã tính chi phí compute, storage, network, engineering, migration và operations.
- [ ] Đã đánh giá replication lag, cache staleness, cross-shard operation hoặc eventual consistency nếu có.
- [ ] Đã xác định cách backup, restore, failover, rebalancing và xử lý sự cố.
- [ ] Đã thiết kế thử nghiệm có đối chứng và tiêu chí chấp nhận.
- [ ] Đã có canary/feature flag, đối soát dữ liệu và rollback plan.
- [ ] Đã đo lại p95/p99, throughput, resource headroom và TCO sau triển khai.

## Kết luận

Tối ưu truy vấn loại bỏ công việc lãng phí trong kiến trúc hiện tại; thay đổi kiến trúc mở rộng hoặc phân phối năng lực khi giới hạn còn lại không thể xử lý hợp lý bằng tuning cục bộ. Quyết định đúng bắt đầu từ baseline, execution plan và bằng chứng về CPU, I/O, memory, lock, connection hoặc dung lượng. Sau đó mới so sánh scale-up, read replica, cache, partitioning, sharding, read model hoặc tách workload phân tích theo lợi ích và chi phí.

Chi phí kiến trúc bao gồm hạ tầng, phát triển, migration, vận hành và rủi ro về tính nhất quán. Replica có thể lag, cache có thể stale, sharding làm cross-shard operation phức tạp và read model bất đồng bộ cần đối soát. Hãy thử nghiệm với tải đại diện, xác định tiêu chí chấp nhận và rollback trước khi chuyển traffic. Chỉ mở rộng giải pháp khi nó cải thiện SLA và headroom một cách bền vững, đồng thời đội ngũ có thể vận hành và phục hồi hệ thống mới.
