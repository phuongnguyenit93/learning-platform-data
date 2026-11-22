# So sánh thay đổi bằng cùng bộ dữ liệu và điều kiện đo

Khi tối ưu cơ sở dữ liệu, một thay đổi có thể làm truy vấn nhanh hơn trong lần chạy thử nhưng chậm hơn khi tải tăng, dữ liệu lớn hơn hoặc cache ở trạng thái khác. Nếu benchmark trước và sau dùng hai bộ dữ liệu, hai cấu hình máy, hai mức concurrency hoặc hai trạng thái cache khác nhau, ta không thể biết phần cải thiện đến từ thay đổi đang đánh giá hay từ điều kiện thử nghiệm. Muốn kết luận đáng tin cậy, cần giữ các yếu tố liên quan giống nhau, chỉ thay đổi yếu tố đang kiểm tra và lặp lại phép đo đủ nhiều để nhận ra biến động tự nhiên.

Trong chương **Kiểm thử hiệu năng**, bài học này trình bày cách so sánh thay đổi bằng cùng bộ dữ liệu và điều kiện đo. Nội dung gắn với mục tiêu của module **DATABASE_PERFORMANCE**: rèn phương pháp tối ưu hiệu năng cơ sở dữ liệu dựa trên đo đạc tải, execution plan, thống kê và cơ chế truy cập dữ liệu. Ta sẽ xây dựng baseline, chuẩn hóa dữ liệu và workload, kiểm soát cấu hình và trạng thái cache, tổ chức thứ tự chạy, đo latency/throughput/tài nguyên, đánh giá độ biến động rồi đưa ra quyết định dựa trên kết quả có thể tái lập.

Một benchmark tốt phải trả lời được: đã thay đổi điều gì, điều kiện nào được giữ cố định, phép đo nào chứng minh lợi ích, kết quả có lặp lại không và có truy vấn hoặc chỉ số nào bị regression không.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích vì sao so sánh trước/sau cần cùng bộ dữ liệu và điều kiện đo.
- Xác định biến thử nghiệm, biến kiểm soát và yếu tố gây nhiễu.
- Tạo snapshot dữ liệu có thể tái sử dụng và bảo đảm phân bố dữ liệu đại diện.
- Chuẩn hóa schema, index, statistics, DBMS version, cấu hình và môi trường.
- Thiết kế workload với cùng query mix, tham số, concurrency và thời lượng.
- Phân biệt cold cache, warm cache và trạng thái steady state.
- Chọn thứ tự chạy, warm-up và số lần lặp để giảm ảnh hưởng của drift.
- Đo latency theo percentile, throughput, CPU, memory, I/O, waits và plan.
- Đánh giá biến động, độ tin cậy và mức cải thiện có ý nghĩa thực tế.
- Viết báo cáo benchmark có đủ thông tin để người khác tái lập.
- Xác định điều kiện chấp nhận, rollback và theo dõi sau triển khai.

## 1. Vì sao phải giữ điều kiện đo giống nhau?

### 1.1. So sánh không kiểm soát dễ dẫn đến kết luận sai

Giả sử một index mới được thêm vào. Lần đo trước chạy trên database có cache lạnh; lần đo sau chạy ngay sau khi dữ liệu đã nằm trong buffer cache. Latency giảm có thể do cache nóng, không phải do index mới.

Một ví dụ khác: phiên bản A chạy với 10 client đồng thời, phiên bản B chạy với 5 client. Nếu B có latency thấp hơn, không thể kết luận thay đổi SQL đã cải thiện hiệu năng vì tải đầu vào đã khác.

Các yếu tố gây nhiễu phổ biến:

- Dữ liệu khác về số dòng, kích thước, phân bố hoặc mức skew.
- Statistics được cập nhật ở một lần chạy nhưng cũ ở lần còn lại.
- Index, partition hoặc schema không giống nhau.
- DBMS version, parameter hoặc execution plan cache khác nhau.
- CPU, RAM, storage, network hoặc quota máy khác nhau.
- Cache nóng/lạnh, background checkpoint, backup hoặc vacuum khác nhau.
- Query parameters và tỷ lệ truy vấn khác nhau.
- Concurrency, connection pool và thời lượng test khác nhau.
- Một lần chạy có người dùng hoặc job khác cạnh tranh tài nguyên.
- Client load generator hoặc network path khác nhau.

Nếu nhiều yếu tố thay đổi cùng lúc, kết quả không cho biết yếu tố nào tạo ra khác biệt.

### 1.2. Nguyên tắc thay đổi một yếu tố có chủ đích

Khi đánh giá một thay đổi, xác định rõ:

- **Biến thử nghiệm:** yếu tố được thay đổi, ví dụ index mới, cách viết SQL, cấu hình DOP hoặc batch size.
- **Biến kiểm soát:** yếu tố phải giữ tương đương, ví dụ dữ liệu, query mix, concurrency, DBMS version và cache condition.
- **Biến kết quả:** metric dùng để đánh giá, ví dụ p95 latency, transactions/s, CPU time hoặc logical reads.
- **Yếu tố gây nhiễu:** yếu tố ngoài ý muốn có thể tác động đến kết quả, ví dụ checkpoint trùng thời điểm hoặc storage noisy neighbor.

Thay đổi một yếu tố mỗi lần giúp quy kết kết quả rõ hơn. Trong một số trường hợp, cần thử nhiều yếu tố theo ma trận hoặc factorial design để phát hiện tương tác; khi đó phải ghi rõ thiết kế thử nghiệm và không gộp các thay đổi mà không có kế hoạch phân tích.

### 1.3. Cùng điều kiện không có nghĩa mọi thứ phải giống tuyệt đối

Khi so sánh một thay đổi phần cứng, tài nguyên phần cứng chính là biến thử nghiệm nên không thể giữ nguyên. Khi đó cần giữ dữ liệu, DBMS version, schema, workload và các yếu tố khác tương đương, đồng thời ghi rõ phần cứng nào khác nhau.

Khi so sánh một thay đổi SQL trên cùng máy, nên giữ cấu hình và topology không đổi. Khi không thể dùng cùng máy, cần dùng môi trường tương đương, đo capacity của từng môi trường và thừa nhận sai số còn lại.

Mục tiêu là kiểm soát những yếu tố không thuộc câu hỏi thử nghiệm, không phải tạo ra một điều kiện nhân tạo không giống production.

## 2. Xác định câu hỏi và giả thuyết benchmark

### 2.1. Viết câu hỏi cụ thể

Câu hỏi quá rộng như “bản mới có nhanh hơn không?” khó xác định cách đo. Hãy chuyển thành câu hỏi có thể kiểm chứng:

- Index ghép mới có giảm logical reads và p95 latency của truy vấn tìm đơn hàng theo tenant/status không?
- Batch size 100 có tăng inserts/s mà không làm p99 commit latency hoặc lock wait vượt ngưỡng không?
- Thay JOIN lặp bằng một truy vấn set-based có giảm round trips và API p95 không?
- Tăng memory grant có giảm hash spill mà không làm các truy vấn đồng thời phải chờ memory không?
- Instance có thêm RAM có giảm physical reads và tổng chi phí mỗi transaction không?

### 2.2. Viết giả thuyết và tiêu chí trước khi chạy

Ví dụ:

~~~text
Giả thuyết:
Index (tenant_id, status, created_at) sẽ giảm lượng page đọc
cho truy vấn lọc theo tenant, status và khoảng thời gian.

Metric chính:
- p95 latency của query fingerprint.
- Logical reads mỗi lần thực thi.

Metric bảo vệ:
- Insert/update throughput.
- Log bytes và storage write latency.
- Dung lượng index.
- p99 latency của workload OLTP hỗn hợp.

Điều kiện chấp nhận:
- Metric chính cải thiện vượt mức tối thiểu đã thống nhất.
- Metric bảo vệ không vượt giới hạn SLA.
- Kết quả lặp lại trong các lần chạy đại diện.
~~~

Không đặt tiêu chí sau khi đã xem kết quả vì dễ chọn metric có lợi và bỏ qua tác động xấu.

### 2.3. Phân biệt metric chính và metric bảo vệ

Một thay đổi có thể tối ưu một truy vấn nhưng làm workload tổng thể kém đi. Ví dụ index mới giảm read latency nhưng tăng chi phí INSERT và dung lượng storage.

Metric chính đo mục tiêu trực tiếp; metric bảo vệ phát hiện regression hoặc trade-off. Với thay đổi index, nên đo cả đọc và ghi. Với tăng DOP, đo cả query duration, CPU tổng và p95 của các query khác.

### 2.4. Xác định phạm vi kết luận

Kết quả benchmark chỉ áp dụng cho:
- Bộ dữ liệu và phân bố đã thử.
- Query mix và tham số đã dùng.
- Mức concurrency và thời lượng đã chạy.
- DBMS version, cấu hình và topology đã ghi nhận.
- Cache condition và trạng thái nền của hệ thống.

Không suy rộng một kết quả từ một query đơn lẻ thành cam kết cho toàn bộ production.

## 3. Chuẩn bị cùng một bộ dữ liệu

### 3.1. Dùng snapshot hoặc bản sao nhất quán

Tạo một snapshot hoặc bản sao từ cùng một trạng thái dữ liệu ban đầu. Từ snapshot đó, tạo môi trường A và B để so sánh. Nếu không thể clone vật lý, dùng quy trình restore/reload có thể tái lập và kiểm tra row counts/checksums phù hợp.

Cần ghi:
- Thời điểm snapshot.
- Phiên bản schema.
- Số dòng theo bảng và partition.
- Kích thước data và index.
- Phân bố các giá trị quan trọng.
- Tỷ lệ NULL, duplicate và skew.
- Cách tạo dữ liệu và seed ngẫu nhiên nếu có.
- Các bước cleanup/reset giữa các lần chạy.

Nếu A chạy trước và đã thay đổi dữ liệu, B không được dùng trạng thái đã bị A làm biến đổi ngoài dự kiến.

### 3.2. Kích thước dữ liệu phải đại diện

Bộ dữ liệu quá nhỏ có thể nằm hoàn toàn trong RAM, khiến benchmark không phản ánh production. Dữ liệu quá lớn có thể làm môi trường thử nghiệm không đủ capacity và tạo bottleneck không tồn tại trong hệ thống mục tiêu.

Chọn dữ liệu theo:
- Tổng số dòng và kích thước bảng/index.
- Working set nóng và tỷ lệ truy cập.
- Phân bố theo tenant, status, thời gian hoặc key.
- Tỷ lệ insert/update/delete.
- Tỷ lệ giá trị phổ biến và hiếm.
- Mức độ trùng lặp và quan hệ giữa bảng.
- Tỷ lệ dữ liệu mới so với dữ liệu cũ.

### 3.3. Giữ phân bố, không chỉ giữ row count

Hai bảng có cùng một triệu dòng vẫn có thể có hiệu năng rất khác nếu phân bố khác nhau. Ví dụ, một tenant chiếm 50% dữ liệu ở bộ A nhưng chỉ 2% ở bộ B. Predicate theo tenant có selectivity khác; optimizer có thể chọn plan khác.

Hãy so sánh histogram hoặc các thống kê phân bố cần thiết, như:
- NDV và tỷ lệ NULL.
- Top values/MCV.
- Phân bố theo khoảng thời gian.
- Tỷ lệ dữ liệu theo tenant hoặc category.
- Tương quan giữa các cột predicate.
- Tỷ lệ hot key.

Nếu workload phụ thuộc một số tham số đặc biệt, cố định và ghi lại danh sách tham số dùng cho cả A và B.

### 3.4. Dữ liệu đọc và dữ liệu ghi

Với read benchmark, snapshot cố định giúp các lần chạy đọc cùng dữ liệu. Với write benchmark, cần xác định trạng thái đầu vào và cách reset:

- Mỗi lần chạy từ cùng snapshot sạch.
- Dùng các key range độc lập nhưng có phân bố tương đương.
- Tạo lại database sau mỗi vòng nếu write workload không thể hoàn tác an toàn.
- Dùng transaction rollback chỉ khi thao tác rollback không làm thay đổi đặc tính cần đo.
- Kiểm tra row count và business invariants sau mỗi vòng.

Không chạy hai phiên bản ghi lên cùng một database theo thứ tự mà phiên bản sau nhận dữ liệu đã bị phiên bản trước thay đổi.

### 3.5. Kiểm tra tính đúng đắn của dữ liệu

Trước benchmark, xác minh:
- Row count và partition count.
- Primary/foreign key và constraint.
- Tổng hoặc checksum trên tập dữ liệu phù hợp.
- Phân bố các cột quan trọng.
- Không có dữ liệu test cũ hoặc transaction chưa kết thúc.
- Schema và index đúng với phiên bản thử nghiệm.

Nếu thay đổi làm kết quả truy vấn khác nhau, cần kiểm tra correctness trước khi so sánh tốc độ.

## 4. Chuẩn hóa schema, index và statistics

### 4.1. Schema phải tương đương

Hai môi trường cần cùng:
- Table definitions và data types.
- Constraint, trigger và generated columns.
- Partitioning strategy.
- Collation và encoding nếu ảnh hưởng so sánh.
- Isolation level và transaction semantics.
- Stored procedures, functions và extensions cần thiết.

Nếu schema là biến thử nghiệm, ghi chính xác phần khác nhau và giữ phần còn lại giống nhau.

### 4.2. Index phải được ghi nhận đầy đủ

Index ảnh hưởng cả execution plan lẫn write cost. Ghi lại:
- Tên, thứ tự key columns và included columns.
- Unique, partial/filtered hoặc expression index.
- Index size và page count.
- Fill factor hoặc storage parameters nếu có.
- Partitioned/local/global index properties.
- Trạng thái valid/usable.
- Thời điểm tạo và rebuild.

Nếu so sánh một index mới, A không có index đó và B có index đó theo đúng giả thuyết. Không để B vô tình có thêm một index khác hoặc A có index đã lỗi thời.

### 4.3. Statistics và plan cache

Statistics cần có trạng thái được kiểm soát. Có thể chọn một trong các cách:

- Thu thập statistics tương đương trên cả hai môi trường sau khi dữ liệu được nạp.
- Dùng cùng snapshot statistics nếu mục tiêu là cô lập một biến khác.
- Cố ý để statistics khác nhau nếu chính việc cập nhật statistics là biến thử nghiệm.

Ghi lại last analyzed/updated, sampling, histogram hoặc metadata quan trọng. Không để A dùng statistics mới còn B dùng statistics cũ ngoài ý muốn.

Plan cache cũng ảnh hưởng. Cần quyết định benchmark cold plan hay warm plan. Nếu xóa plan cache ở một phiên bản nhưng không ở phiên bản còn lại, phép đo không còn tương đương. Chỉ xóa cache trong môi trường thử nghiệm được kiểm soát và ghi lại hành động đó.

### 4.4. So sánh execution plan

Lưu actual plan hoặc thông tin plan phù hợp của cả hai phiên bản:
- Access path.
- Join order và join algorithm.
- Estimated rows và actual rows.
- Loops và rows per loop.
- Sort/hash operators.
- Memory grant và spill.
- Parallel workers/DOP.
- Logical/physical reads.
- Waits hoặc operator timing nếu có.

Plan khác nhau không nhất thiết là sai. Cần xác định plan khác là kết quả mong muốn của thay đổi hay do điều kiện thử nghiệm không đồng nhất.

## 5. Chuẩn hóa môi trường thực thi

### 5.1. Phần cứng và giới hạn tài nguyên

Ghi lại:
- CPU model, core, socket, NUMA và CPU quota.
- RAM, memory limit và swap policy.
- Storage type, volume, IOPS/throughput limit và latency.
- Network topology, RTT và bandwidth.
- Virtual machine/container limits.
- Cloud instance class và burst credits nếu có.
- OS, filesystem và kernel version.

Nếu A và B chạy trên hai máy khác nhau, hãy kiểm tra capacity thực tế của từng máy. Hai instance cùng nhãn cấu hình không luôn có hiệu năng giống nhau do noisy neighbor, quota hoặc khác biệt nền tảng.

### 5.2. DBMS version và cấu hình

Ghi lại DBMS product/version/build, compatibility level, extension/plugin và các tham số liên quan:
- Memory/buffer settings.
- Parallelism/DOP.
- Connection limits.
- Durability, fsync và log flush settings.
- Checkpoint và background maintenance.
- Isolation level.
- Optimizer settings.
- Query cache/plan cache nếu có.
- Compression, encryption và replication mode.

Không thay durability hoặc isolation chỉ để làm benchmark nhanh hơn nếu đó không phải biến thử nghiệm được phê duyệt. Kết quả chỉ có ý nghĩa khi semantics so sánh giống nhau.

### 5.3. Background activity

Các hoạt động nền có thể làm kết quả dao động:
- Checkpoint và log archive.
- Autovacuum, purge hoặc statistics update.
- Backup, snapshot và replication.
- Index maintenance.
- ETL hoặc batch jobs.
- Monitoring agents và antivirus/endpoint scans.
- Các workload khác cùng dùng storage/network.

Có thể tạm ngừng các tác vụ không thuộc mục tiêu trong môi trường benchmark riêng. Nếu chúng là một phần của production workload, nên thử thêm một kịch bản có chúng để đánh giá tác động thực tế.

### 5.4. Client và load generator

Máy tạo tải cũng có thể trở thành bottleneck. Ghi nhận:
- CPU và memory của load generator.
- Số virtual users/clients.
- Driver version và connection pool.
- Network path tới DBMS.
- Thời gian xử lý/serialization phía client.
- Thread pool và giới hạn file/socket.
- Cách phân phối request và think time.

Nếu load generator đạt 100% CPU hoặc network saturation, DBMS có thể chưa được thử ở capacity thật.

## 6. Chuẩn hóa workload và tham số

### 6.1. Query mix

Tạo một workload đại diện thay vì chỉ chạy một câu SQL. Ví dụ hệ thống bán hàng có:
- 50% point lookup.
- 25% list/range query.
- 15% insert/update transaction.
- 10% báo cáo tổng hợp.

Các tỷ lệ trên chỉ minh họa; phải lấy từ production trace, query statistics hoặc yêu cầu nghiệp vụ. Ghi rõ tỷ lệ và cách sinh request để A và B nhận cùng workload.

### 6.2. Query fingerprint và parameter set

Cùng một câu SQL có thể có chi phí khác nhau với tham số phổ biến và hiếm. Tạo bộ tham số cố định có đại diện:
- Tenant lớn và tenant nhỏ.
- Trạng thái phổ biến và hiếm.
- Khoảng thời gian ngắn và dài.
- Key có nhiều dòng con và ít dòng con.
- Các giá trị NULL hoặc biên nếu hợp lệ.

Không chỉ chạy một parameter thuận lợi cho phiên bản mới. Ghi lại seed hoặc danh sách tham số để tái sử dụng.

### 6.3. Cùng transaction boundary

Nếu A commit từng dòng còn B batch 100 dòng, đây có thể là biến thử nghiệm. Nhưng nếu mục tiêu là so sánh hai cách viết SELECT, transaction boundary cần giống nhau.

Ghi rõ:
- Số statement trong một transaction.
- Số commit/rollback.
- Isolation level.
- Retry policy.
- Autocommit behavior.
- Connection reuse.
- Thứ tự thao tác.

### 6.4. Cùng concurrency và arrival pattern

Cùng số client không bảo đảm tải giống nhau nếu tốc độ gửi request khác. Cần xác định:
- Closed-loop: client gửi request mới sau khi request trước hoàn tất.
- Open-loop: request được phát theo tốc độ mục tiêu, không phụ thuộc tốc độ hoàn thành.
- Số client/virtual users.
- Arrival rate hoặc think time.
- Ramp-up và ramp-down.
- Thời gian giữ tải ổn định.

Closed-loop có thể che giấu latency tăng vì client chậm tự giảm tốc độ gửi. Open-loop phản ánh tốt hơn một số hệ thống có arrival rate cố định, nhưng cần kiểm soát queue và overload. Chọn mô hình theo hành vi production và dùng cùng một mô hình cho A/B.

### 6.5. Cùng thời lượng hoặc cùng lượng công việc

Có hai cách phổ biến:
- **Fixed duration:** chạy cùng khoảng thời gian và đo lượng công việc hoàn thành.
- **Fixed workload:** xử lý cùng số request/transaction và đo thời gian.

Fixed duration phù hợp so throughput khi tải ổn định; fixed workload hữu ích để so tổng thời gian và tài nguyên cho cùng công việc. Ghi rõ cách chọn, tránh dừng một phiên bản sớm hơn khi chưa đạt trạng thái tương đương.

## 7. Cache, warm-up và trạng thái steady state

### 7.1. Cold cache và warm cache là hai kịch bản khác nhau

Cold cache mô phỏng lần truy cập khi dữ liệu chưa nằm trong buffer cache hoặc OS cache. Warm cache mô phỏng workload lặp lại khi working set đã được nạp. Hai kịch bản trả lời các câu hỏi khác nhau.

Không so sánh A ở cold cache với B ở warm cache. Nếu mục tiêu là đo cả hai, chạy hai bộ thử nghiệm độc lập và ghi điều kiện từng bộ.

### 7.2. Warm-up trước khi ghi nhận

Trước khi đo steady state:
1. Khởi động DBMS và load generator.
2. Mở connection pool theo đúng cấu hình.
3. Chạy workload warm-up giống workload đo.
4. Chờ cache, plan cache và background activity ổn định theo tiêu chí đã chọn.
5. Bắt đầu ghi metric sau khi warm-up kết thúc.

Warm-up không có nghĩa phải chạy đến khi latency thấp nhất. Hãy xác định một điều kiện ổn định, ví dụ throughput, cache hit và CPU không còn xu hướng tăng/giảm mạnh trong một khoảng quan sát.

### 7.3. Kiểm soát plan cache

Plan cache có thể làm lần đầu parse/compile khác các lần sau. Nếu benchmark production steady state, hãy warm-up plan cache ở cả A và B. Nếu đánh giá compile latency, đo riêng cold compile và không trộn với query execution steady state.

Với parameter-sensitive plans, chạy cùng thứ tự tham số hoặc dùng thiết kế thứ tự cân bằng. Thứ tự tham số có thể ảnh hưởng plan được compile/cached đầu tiên.

### 7.4. Không xóa OS cache tùy tiện

Xóa cache hệ điều hành hoặc DB buffer cache có thể ảnh hưởng toàn bộ môi trường và không mô phỏng chính xác production. Chỉ thực hiện trong môi trường test riêng, có quyền và quy trình rõ ràng. Nếu không thể tạo cold-cache một cách lặp lại, ghi nhận giới hạn thay vì tuyên bố đã đo cold cache.

### 7.5. Background cycles

Checkpoint, autovacuum, purge, backup hoặc log rotation có thể xảy ra theo chu kỳ. Một lần chạy 2 phút có thể bỏ qua chu kỳ gây contention; một lần chạy 30 phút có thể bao gồm nhiều chu kỳ.

Chọn thời lượng đủ dài để bao phủ các hoạt động liên quan hoặc chạy riêng một kịch bản có maintenance. Giữ cùng lịch và điều kiện cho A/B.

## 8. Quy trình benchmark A/B có thể tái lập

### Bước 1: Định nghĩa mục tiêu và tiêu chí

Ghi giả thuyết, metric chính, metric bảo vệ, ngưỡng chấp nhận và điều kiện dừng trước khi chạy.

### Bước 2: Tạo baseline

Lưu:
- Dataset snapshot/version.
- Schema và index definitions.
- Statistics metadata.
- DBMS/OS/configuration.
- Topology và resource limits.
- Workload script, query mix và parameters.
- Cache/plan state.
- Thời gian, người chạy và phiên bản công cụ.

### Bước 3: Chuẩn bị A và B

A là baseline; B là candidate. Khởi tạo cả hai từ cùng snapshot hoặc quy trình reset tương đương. Áp dụng đúng thay đổi đang kiểm tra vào B. Kiểm tra dữ liệu và schema trước khi bắt đầu.

### Bước 4: Kiểm tra correctness

Chạy các truy vấn xác minh và business invariants. Với thay đổi SQL, so sánh result sets; với thay đổi ghi, so sánh row counts, totals, uniqueness và constraint. Không benchmark phiên bản cho kết quả sai.

### Bước 5: Warm-up theo cùng quy tắc

Chạy cùng workload warm-up và cùng điều kiện cache. Nếu cần cold-cache test, thực hiện riêng và reset theo cùng quy trình.

### Bước 6: Chạy thử pilot

Chạy thời gian ngắn để phát hiện lỗi script, load generator bottleneck, parameter mismatch hoặc resource limit. Không dùng pilot làm kết quả chính nếu thời lượng chưa đủ.

### Bước 7: Chạy các lần đo lặp

Lặp lại nhiều vòng. Nếu có thể, cân bằng thứ tự A/B để giảm ảnh hưởng drift, ví dụ:

~~~text
Vòng 1: A -> B
Vòng 2: B -> A
Vòng 3: A -> B
Vòng 4: B -> A
~~~

Nếu hai môi trường chạy đồng thời, cần bảo đảm chúng không tranh chấp cùng storage, CPU, network hoặc backend cloud quota. Nếu chạy tuần tự, theo dõi drift của nhiệt độ CPU, cache và background tasks.

### Bước 8: Thu thập metric cùng thời điểm

Thu metrics từ ứng dụng, DBMS, OS và storage trong cùng cửa sổ. Đồng bộ clock hoặc dùng monotonic timestamps để ghép trace. Ghi start/end, warm-up interval, test duration và số request hoàn tất.

### Bước 9: Phân tích kết quả và sai số

Tính median, percentile, throughput và độ biến động theo từng vòng. Kiểm tra outliers và nguyên nhân; không loại bỏ số đo xấu chỉ vì chúng làm kết quả kém đẹp. Chỉ loại khi có quy tắc loại trừ được xác định trước và có bằng chứng sự cố ngoài phạm vi.

### Bước 10: Xác minh regression và quyết định

Kiểm tra query khác, write cost, memory, storage, log, error rate và correctness. Chỉ chấp nhận khi metric chính đạt mục tiêu và metric bảo vệ nằm trong giới hạn đã thống nhất.

## 9. Các metric cần so sánh

### 9.1. Latency

Đo p50, p90, p95, p99 và max nếu phù hợp. Mean có thể che giấu tail latency. Với API hoặc OLTP, p95/p99 thường quan trọng vì một nhóm request chậm có thể ảnh hưởng trải nghiệm và timeout.

Định nghĩa rõ latency bắt đầu/kết thúc ở đâu:
- API end-to-end.
- Pool acquisition.
- DB statement.
- Commit acknowledgement.
- Time to first row.
- Fetch complete.

Không so p95 của DB execution với p95 của API end-to-end.

### 9.2. Throughput

Đo:
- Queries/s.
- Transactions/s.
- Commits/s.
- Rows/s hoặc bytes/s nếu phù hợp.
- Successful requests/s.
- Error/timeout/retry rate.

Throughput chỉ có ý nghĩa khi so cùng loại công việc và tính cả request thất bại hoặc retry. Một candidate có nhiều request lỗi không thể được xem là throughput cao hơn chỉ vì đếm attempt.

### 9.3. CPU và memory

Theo dõi:
- CPU utilization và CPU time.
- Runnable queue/context switching.
- Memory working set và buffer cache.
- Memory grant/usage.
- Cache eviction.
- Spill và temporary memory.
- GC hoặc client memory nếu benchmark qua ứng dụng.

Một truy vấn nhanh hơn nhưng tăng CPU gấp nhiều lần có thể làm capacity toàn hệ thống giảm khi concurrency cao.

### 9.4. I/O và log

Theo dõi:
- Logical reads/buffer gets.
- Physical reads và bytes đọc.
- Data writes và bytes ghi.
- IOPS, throughput và latency theo volume.
- Queue depth.
- WAL/redo/log bytes.
- Log flush count và latency.
- Checkpoint activity và temp I/O.

Đối với thay đổi index, so sánh cả read savings và write amplification. Đối với thay đổi commit/batch, xem log bytes và commit latency.

### 9.5. Waits và concurrency

Theo dõi lock waits, latch/mutex waits, memory grant waits, worker waits, I/O waits, log flush waits và network waits tùy DBMS.

Wait time cần được phân tích cùng active sessions và throughput. Tổng wait có thể tăng chỉ vì số session tăng; hãy chuẩn hóa theo transaction hoặc query execution khi phù hợp.

### 9.6. Plan và correctness

Lưu actual execution plan, estimated/actual rows, join order, index access, DOP, memory grant, spills và rows returned. Kiểm tra kết quả đúng, transaction atomicity, constraint và isolation semantics.

Plan khác nhau không tự động là regression. Đánh giá runtime và resource consumption trên workload.

## 10. Phân tích biến động và độ tin cậy

### 10.1. Lặp lại nhiều lần

Một lần chạy có thể bị ảnh hưởng bởi background task, network jitter hoặc cache. Lặp lại nhiều vòng để xem kết quả có ổn định không.

Số lần lặp phụ thuộc mức biến động và chi phí test. Nếu chênh lệch nhỏ hơn độ dao động tự nhiên, cần tăng số lần lặp hoặc cải thiện kiểm soát môi trường trước khi kết luận.

### 10.2. Median và percentile

Median ít nhạy với một số outliers hơn mean. Percentile thể hiện tail latency. Hãy lưu phân phối hoặc histogram thay vì chỉ một con số trung bình.

Với throughput, tính theo các cửa sổ thời gian ổn định. Không gộp warm-up vào steady-state throughput nếu mục tiêu là đo steady state.

### 10.3. Confidence interval và bootstrap

Nếu có đủ mẫu độc lập hoặc các vòng chạy phù hợp, có thể ước lượng confidence interval cho chênh lệch median/mean hoặc percentile. Bootstrap là một phương pháp lấy mẫu lại từ dữ liệu quan sát để ước lượng khoảng bất định, nhưng cần lấy mẫu theo đơn vị phù hợp.

Các request trong cùng một vòng tải có thể tương quan; coi hàng triệu request liên tiếp là hàng triệu mẫu độc lập có thể làm khoảng tin cậy quá hẹp. Có thể phân tích theo từng run/block hoặc dùng phương pháp thống kê phù hợp với dữ liệu phụ thuộc.

### 10.4. Mức cải thiện tương đối

Với latency, phần trăm giảm có thể tính:

~~~text
Improvement (%) = (Latency_before - Latency_after)
                  / Latency_before * 100
~~~

Với throughput:

~~~text
Gain (%) = (Throughput_after - Throughput_before)
           / Throughput_before * 100
~~~

Ví dụ latency p95 giảm từ 200 ms xuống 160 ms thì mức giảm là 20%. Nhưng cần xem p99, error rate, CPU và throughput có giữ trong giới hạn không.

Không chỉ báo phần trăm. Ghi cả giá trị tuyệt đối, số mẫu, khoảng thời gian và độ biến động.

### 10.5. Statistical significance và practical significance

Một chênh lệch có thể có ý nghĩa thống kê nhưng không đủ lớn để đáng triển khai. Ngược lại, một cải thiện lớn nhưng mẫu quá ít có thể chưa đủ tin cậy.

Đánh giá cả:
- Mức chênh lệch tuyệt đối và tương đối.
- Confidence interval hoặc độ biến động.
- SLA và tác động nghiệp vụ.
- Chi phí vận hành và bảo trì.
- Trade-off lên query khác và workload ghi.

### 10.6. Outliers

Không xóa outlier chỉ vì latency cao. Tìm nguyên nhân như checkpoint, failover, GC pause, network retransmission, backup hoặc noisy neighbor. Nếu outlier thuộc hoạt động production bình thường, nó phải được tính trong kịch bản workload phù hợp.

Nếu có sự cố test ngoài phạm vi, ghi lại thời điểm, bằng chứng và quy tắc loại trừ trước khi phân tích.

## 11. Ví dụ: so sánh index mới bằng cùng dữ liệu

Giả sử truy vấn tìm đơn hàng theo tenant, trạng thái và khoảng thời gian:

~~~sql
SELECT order_id, created_at, total_amount
FROM orders
WHERE tenant_id = :tenant_id
  AND status = :status
  AND created_at >= :from_time
ORDER BY created_at DESC
LIMIT 100;
~~~

Giả thuyết là index ghép giúp giảm số page đọc và tránh sort lớn. So sánh:

- **A:** schema và index hiện tại.
- **B:** cùng schema và dữ liệu, thêm index ghép phù hợp.
- Cùng DBMS version, CPU/RAM/storage, connection pool và durability.
- Cùng snapshot dữ liệu và statistics tương đương.
- Cùng query parameters gồm tenant lớn/nhỏ, status phổ biến/hiếm và time range ngắn/dài.
- Cùng concurrency và request arrival pattern.
- Cùng cache condition và warm-up.
- Cùng thời lượng, số vòng và metric collection.

Ví dụ bảng kết quả:

| Metric | A: baseline | B: candidate | Đánh giá |
|---|---:|---:|---|
| p50 latency | 42 ms | 30 ms | Giảm |
| p95 latency | 110 ms | 68 ms | Giảm |
| p99 latency | 240 ms | 150 ms | Giảm |
| Logical reads/query | 820 | 145 | Giảm |
| CPU/query | 3.8 ms | 2.9 ms | Giảm |
| Insert throughput | 12.000/s | 10.900/s | Giảm |
| Index storage | 0 | 1.8 GB | Tăng |

Các số trên chỉ minh họa cách trình bày, không phải benchmark thực tế hay mục tiêu mặc định. Candidate có thể cải thiện truy vấn đọc nhưng làm INSERT chậm hơn và tăng dung lượng. Quyết định phụ thuộc tỷ lệ đọc/ghi, SLA, storage budget và tổng throughput.

Sau khi chạy, lưu actual plan của A và B. Nếu B dùng index mới nhưng p95 không cải thiện, kiểm tra selectivity, key order, sort, parameter distribution và cache. Nếu logical reads giảm nhưng latency không đổi, bottleneck có thể nằm ở network, lock, CPU khác hoặc client processing.

## 12. Ví dụ: so sánh thay đổi batch size

Giả sử hệ thống nhập order_items. So sánh batch size 1, 50, 100 và 500.

Giữ cố định:
- Cùng số dòng đầu vào và thứ tự key.
- Cùng schema, index, constraints và trigger.
- Cùng transaction semantics nếu đang so cách gửi batch.
- Cùng concurrency, connection pool và storage.
- Cùng log durability và replication settings.
- Cùng cách reset database giữa các lần chạy.

Đo:
- Rows/s và transactions/s.
- p50/p95/p99 transaction latency.
- Commit latency.
- Log bytes/row.
- Lock wait và deadlock.
- Memory/packet size.
- Rollback duration và error rate.

Batch lớn có thể giảm round trips và commits nhưng tăng lock duration, log burst và rollback cost. Chọn batch size theo tổng workload và SLA, không chỉ tốc độ import cao nhất.

## 13. So sánh theo loại thay đổi

| Loại thay đổi | Điều kiện cần giữ | Metric chính | Metric bảo vệ |
|---|---|---|---|
| SQL rewrite | Dữ liệu, tham số, plan/cache policy, concurrency | Latency, reads, CPU | Kết quả đúng, lock, memory |
| Thêm/bớt index | Snapshot, query mix, statistics, DBMS config | Read latency/reads | Write throughput, log, storage |
| Statistics update | Dữ liệu, schema, workload, cache policy | Estimate accuracy, plan, latency | Recompile, maintenance I/O |
| Tăng DOP | CPU quota, workload, query mix, concurrency | Query duration, throughput | CPU, worker, memory, temp I/O |
| Tăng memory | Workload, concurrency, DBMS config | Cache reads, spill, latency | OS memory, grant wait, swap |
| Thay storage | Dữ liệu, DBMS, workload, durability | I/O latency/throughput | Cost, flush semantics, capacity |
| Connection pool change | Arrival rate, DB capacity, network | Pool wait, API latency | DB sessions, CPU, lock waits |
| Batch size change | Input rows, transaction semantics, durability | Rows/s, round trips | Commit p99, log, rollback |

Bảng này giúp chuẩn bị phép đo; mỗi thay đổi vẫn cần giả thuyết và thiết kế cụ thể.

## 14. Báo cáo benchmark có thể tái lập

Một báo cáo tối thiểu nên có các phần sau:

### 14.1. Thông tin thử nghiệm

- Mã thử nghiệm và ngày giờ.
- Người thực hiện.
- Mục tiêu và giả thuyết.
- Phiên bản ứng dụng, DBMS và driver.
- Cấu hình A/B và biến được thay đổi.

### 14.2. Dữ liệu và môi trường

- Snapshot/dataset identifier.
- Row counts, sizes và phân bố.
- Schema/index/statistics state.
- CPU, RAM, storage, network và quota.
- DBMS settings, durability và isolation.
- Background tasks và điều kiện cache.

### 14.3. Workload

- Query fingerprint và tỷ lệ query mix.
- Parameter set/seed.
- Concurrency và arrival pattern.
- Connection pool và transaction boundaries.
- Warm-up, thời lượng và số lần lặp.
- Cách reset dữ liệu ghi.

### 14.4. Kết quả

- p50/p95/p99 latency.
- Throughput và successful request rate.
- CPU, memory, I/O, log và waits.
- Actual plan và estimated/actual rows.
- Error, timeout, retry và correctness.
- Giá trị từng vòng, median và độ biến động.

### 14.5. Kết luận và giới hạn

- Metric chính đạt hay không đạt.
- Metric bảo vệ có regression không.
- Kết quả có lặp lại không.
- Giải thích nguyên nhân có bằng chứng.
- Phạm vi workload có thể suy rộng.
- Điều kiện chưa được kiểm thử.
- Quyết định triển khai, thử tiếp hoặc rollback.

Lưu script, configuration snapshot và raw result ở nơi quản lý thử nghiệm của nhóm để có thể tái chạy. Không ghi dữ liệu nhạy cảm hoặc credential vào artifact benchmark.

## 15. Tiêu chí dừng, chấp nhận và rollback

### 15.1. Tiêu chí dừng thử nghiệm

Dừng test nếu:
- Error rate vượt ngưỡng an toàn.
- Database hoặc load generator có dấu hiệu mất ổn định.
- Disk/temp/log gần đầy.
- p99 vượt giới hạn gây ảnh hưởng môi trường dùng chung.
- Deadlock, data corruption hoặc kết quả sai xuất hiện.
- Tải test ảnh hưởng hệ thống ngoài phạm vi đã cho phép.

Các ngưỡng cụ thể phải được xác định theo môi trường và SLA.

### 15.2. Tiêu chí chấp nhận

Một candidate có thể được chấp nhận khi:
- Metric chính cải thiện đủ mức có ý nghĩa.
- Kết quả lặp lại trong các vòng đo.
- Metric bảo vệ nằm trong giới hạn.
- Correctness và transaction semantics được giữ.
- Không có regression nghiêm trọng ở query mix khác.
- Chi phí tài nguyên và vận hành hợp lý.

### 15.3. Rollback

Chuẩn bị cách quay lại baseline:
- Lưu DDL và cấu hình trước thay đổi.
- Có snapshot hoặc backup phù hợp.
- Xác định cách drop/revert index hoặc config.
- Biết ảnh hưởng của rollback tới lock, downtime và replication.
- Xác minh dữ liệu sau rollback.
- Có tiêu chí kích hoạt rollback dựa trên metric.

Với thay đổi schema hoặc dữ liệu không thể đảo ngược đơn giản, cần migration có khả năng tương thích và kế hoạch phục hồi riêng.

## 16. Những sai lầm thường gặp

**Chỉ chạy mỗi phiên bản một lần.** Một lần đo có thể bị nhiễu bởi cache, checkpoint hoặc network jitter.

**Dùng dữ liệu khác nhau.** Row count giống nhau nhưng skew, working set hoặc quan hệ dữ liệu khác có thể làm plan và latency khác.

**Không kiểm soát statistics.** Optimizer có thể chọn plan khác do statistics freshness chứ không phải thay đổi đang thử.

**Chỉ đo query đơn.** Một index hoặc DOP tốt cho một query có thể làm workload hỗn hợp chậm hơn.

**So cold cache với warm cache.** Kết quả không thể quy cho thay đổi.

**Chỉ báo mean latency.** Tail latency và error rate có thể xấu đi dù mean giảm.

**Chỉ nhìn throughput.** Throughput có thể tăng nhờ retry hoặc bỏ qua lỗi; cần đếm successful work và kiểm tra correctness.

**Thay nhiều yếu tố cùng lúc.** Không thể xác định yếu tố nào tạo ra lợi ích hoặc regression.

**Xóa outlier tùy ý.** Có thể xóa mất chính các sự cố production cần quan tâm.

**Dùng load generator bị bão hòa.** Kết quả phản ánh máy tạo tải thay vì DBMS.

**Không lưu script và điều kiện.** Benchmark không thể tái lập hoặc giải thích sau này.

**Chấp nhận kết quả chỉ vì execution plan đẹp hơn.** Plan là bằng chứng về cách thực thi; runtime và workload mới quyết định hiệu quả.

## 17. Checklist so sánh thay đổi bằng cùng dữ liệu và điều kiện

- [ ] Đã viết câu hỏi, giả thuyết và biến thử nghiệm chưa?
- [ ] Đã xác định metric chính, metric bảo vệ và tiêu chí chấp nhận trước khi chạy chưa?
- [ ] A và B có cùng snapshot hoặc quy trình reset dữ liệu tương đương không?
- [ ] Đã kiểm tra row count, data size, skew, NULL và parameter distribution chưa?
- [ ] Schema, constraints, index và partition có đúng theo thiết kế thử nghiệm không?
- [ ] Statistics và plan cache có được kiểm soát không?
- [ ] DBMS version, configuration, durability và isolation có tương đương không?
- [ ] CPU/RAM/storage/network/quota của môi trường đã được ghi nhận chưa?
- [ ] Background tasks và competing workload có được kiểm soát hoặc ghi lại không?
- [ ] Query mix, parameters, transaction boundary và concurrency có giống nhau không?
- [ ] Load generator có đủ capacity không?
- [ ] Cold/warm cache và warm-up có cùng quy tắc không?
- [ ] Thời lượng, số vòng và thứ tự A/B có được xác định trước không?
- [ ] Đã đo p50/p95/p99, throughput, errors và successful work chưa?
- [ ] Đã thu CPU, memory, I/O, log, waits và actual plan chưa?
- [ ] Đã đánh giá biến động, outliers và confidence interval phù hợp chưa?
- [ ] Đã kiểm tra correctness và regression của workload khác chưa?
- [ ] Đã lưu script, config, raw results và kế hoạch rollback chưa?

## Kết luận

So sánh thay đổi hiệu năng chỉ đáng tin khi A và B thực hiện cùng công việc trên dữ liệu và điều kiện tương đương. Cần kiểm soát snapshot, phân bố dữ liệu, schema, index, statistics, DBMS configuration, phần cứng, cache, query mix, tham số, concurrency và thời lượng. Khi một yếu tố là biến thử nghiệm, hãy ghi rõ nó và giữ các yếu tố còn lại ổn định trong phạm vi có thể.

Hãy đặt giả thuyết và tiêu chí trước khi chạy, warm-up theo cùng quy tắc, lặp lại phép đo với thứ tự cân bằng, thu latency percentile, throughput, tài nguyên, waits và actual plan. Đánh giá cả metric chính lẫn metric bảo vệ, correctness và độ biến động. Báo cáo cần lưu dữ liệu, script, cấu hình và giới hạn kết luận để người khác có thể tái lập. Nhờ vậy, quyết định tối ưu dựa trên bằng chứng về thay đổi đang thử thay vì khác biệt ngẫu nhiên của môi trường.

