# Song song trong truy vấn và tranh chấp tài nguyên giữa các truy vấn

Cơ sở dữ liệu có thể xử lý nhiều công việc cùng lúc theo hai cách: chia một truy vấn thành nhiều phần để nhiều worker thực hiện song song, hoặc chạy nhiều truy vấn độc lập đồng thời. Cả hai cách đều có thể tăng throughput và rút ngắn thời gian hoàn tất. Nhưng chúng cũng khiến các truy vấn cạnh tranh CPU, bộ nhớ, worker, buffer cache, băng thông lưu trữ và vùng dữ liệu tạm. Khi tài nguyên dùng chung đạt giới hạn, tăng mức song song hoặc tăng số truy vấn đồng thời có thể làm toàn hệ thống chậm hơn.

Trong chương **Lưu trữ và tài nguyên**, bài học này giải thích song song trong truy vấn và tranh chấp tài nguyên giữa các truy vấn. Nội dung gắn với mục tiêu của module **DATABASE_PERFORMANCE**: rèn phương pháp tối ưu hiệu năng cơ sở dữ liệu dựa trên đo đạc tải, execution plan, thống kê và cơ chế truy cập dữ liệu. Ta sẽ phân biệt song song bên trong một truy vấn với concurrency giữa nhiều truy vấn, phân tích CPU, memory grant, I/O, temporary storage, data skew và các dạng contention, rồi xây dựng cách benchmark để xác định mức song song có lợi cho workload thực tế.

Mục tiêu không phải làm mọi truy vấn chạy với nhiều worker nhất có thể. Mục tiêu là sử dụng tài nguyên có kiểm soát để đạt độ trễ và throughput phù hợp, đồng thời giữ p95/p99 ổn định khi nhiều loại truy vấn cùng hoạt động.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt intra-query parallelism và concurrency giữa nhiều truy vấn.
- Giải thích cách parallel scan, repartition, exchange và gather phối hợp dữ liệu.
- Đánh giá lợi ích và overhead của Degree of Parallelism (DOP).
- Nhận diện CPU oversubscription, worker starvation và queueing.
- Hiểu memory grant, hash/sort spill và áp lực bộ nhớ khi nhiều truy vấn chạy cùng lúc.
- Phân tích I/O bandwidth, queue depth, buffer cache và temporary storage.
- Nhận diện data skew, lock contention, latch/mutex contention và tranh chấp tài nguyên dùng chung.
- Đọc actual execution plan và wait metrics để tìm điểm nghẽn.
- Thiết kế benchmark có nhiều mức concurrency và hỗn hợp truy vấn đại diện.
- Đề xuất giới hạn DOP, admission control, resource governance và thay đổi truy vấn dựa trên số liệu.

## 1. Hai dạng song song cần phân biệt

### 1.1. Song song bên trong một truy vấn

Intra-query parallelism chia công việc của một câu SQL thành các phần có thể thực hiện đồng thời. Ví dụ, thay vì một worker đọc toàn bộ partition của bảng lớn, DBMS có thể phân chia phạm vi hoặc partition cho nhiều worker đọc cùng lúc. Các worker sau đó xử lý filter, join hoặc aggregate và phối hợp để tạo kết quả cuối.

Ví dụ truy vấn báo cáo:

~~~sql
SELECT region_id, SUM(total_amount) AS revenue
FROM orders
WHERE created_at >= TIMESTAMP '2026-01-01 00:00:00'
GROUP BY region_id;
~~~

Nếu bảng orders rất lớn, DBMS có thể chia scan thành nhiều phần. Các worker lọc và tổng hợp một phần dữ liệu, sau đó kết quả được kết hợp. Nếu storage, CPU và memory còn đủ, thời gian chạy một truy vấn có thể giảm.

Song song hóa thường hữu ích với scan lớn, join dữ liệu lớn, sort, aggregate và một số thao tác xử lý theo lô. Nó có overhead để khởi tạo worker, phân phối công việc, trao đổi dữ liệu và đồng bộ kết quả.

### 1.2. Nhiều truy vấn chạy đồng thời

Concurrency giữa truy vấn (inter-query concurrency) xảy ra khi nhiều session hoặc request thực hiện các câu SQL độc lập cùng lúc. Ví dụ một hệ thống thương mại điện tử có thể đồng thời:

- API đọc chi tiết đơn hàng.
- API tìm kiếm sản phẩm.
- Transaction tạo đơn và cập nhật tồn kho.
- Dashboard tổng hợp doanh thu.
- Job nền archive dữ liệu cũ.

Mỗi truy vấn có thể chạy tuần tự bên trong nó, nhưng nhiều truy vấn vẫn sử dụng CPU, memory và I/O cùng lúc. Concurrency tăng có thể cải thiện throughput vì CPU và storage được khai thác tốt hơn khi một truy vấn đang chờ I/O. Khi tài nguyên bão hòa, các truy vấn bắt đầu xếp hàng và latency tăng.

### 1.3. Hai dạng song song có thể cộng dồn

Một truy vấn được cấp DOP 8 có thể dùng tối đa nhiều worker cho cùng một câu SQL. Nếu 20 truy vấn như vậy chạy đồng thời, số worker yêu cầu tiềm năng có thể rất lớn. DBMS thường có scheduler, giới hạn worker, memory grant và cơ chế queue để ngăn hệ thống bị quá tải, nhưng cấu hình và cách điều phối khác nhau theo sản phẩm.

Vì vậy, không thể đánh giá DOP của một truy vấn riêng lẻ mà bỏ qua số truy vấn đồng thời. Cần đo tải toàn hệ thống.

## 2. Cách một truy vấn được chia việc

### 2.1. Chia phạm vi scan

Với bảng hoặc partition lớn, DBMS có thể chia phạm vi dữ liệu cho các worker. Mỗi worker đọc một phần và thực hiện các bước có thể song song như filter hoặc projection.

Nếu dữ liệu nằm trên nhiều partition, DBMS có thể đọc nhiều partition cùng lúc. Tuy nhiên, số partition không tự động bằng số worker; cách phân phối phụ thuộc optimizer, storage layout và engine.

### 2.2. Exchange, repartition và gather

Một parallel plan thường cần trao đổi dữ liệu giữa các worker:

- **Distribute:** phân phối đầu vào cho các worker.
- **Repartition:** chia lại dòng theo khóa, thường để các dòng cùng join key đến cùng worker.
- **Gather:** thu kết quả từ nhiều worker về một điểm.
- **Gather Merge:** hợp nhất các luồng đã có thứ tự theo một khóa.

Tên operator thay đổi theo DBMS. Trong SQL Server có các exchange operators; PostgreSQL có Gather và Gather Merge; Oracle có các bước PX SEND/PX RECEIVE.

Trao đổi dữ liệu có chi phí CPU, memory và đồng bộ. Nếu lượng dữ liệu phải chuyển lớn hoặc các worker không cân bằng, exchange có thể trở thành bottleneck. Một plan có nhiều worker chưa chắc nhanh nếu phần lớn thời gian dành cho repartition hoặc gather.

### 2.3. Pipeline và blocking operators

Một số operator có thể truyền dòng tiếp theo ngay khi xử lý xong dòng hiện tại, tạo thành pipeline. Một số operator cần đọc hoặc giữ nhiều đầu vào trước khi xuất kết quả, chẳng hạn sort, hash build hoặc aggregate nhất định.

Blocking operator có thể cần memory đáng kể và làm các worker chờ nhau. Nếu dữ liệu vượt vùng memory được cấp, operator có thể spill ra temporary storage.

Khi đọc plan, hãy xem node nào tạo ra dữ liệu trung gian lớn, node nào cần sort/hash, và dữ liệu được truyền giữa worker ở đâu.

### 2.4. DOP và số worker thực tế

Degree of Parallelism (DOP) mô tả mức song song của một truy vấn hoặc operator. DOP 4 thường có nghĩa một phần công việc có thể được thực hiện bởi tối đa khoảng bốn worker, tùy định nghĩa của DBMS và cách tính coordinator. Không nên giả định DOP luôn bằng tổng số thread hệ điều hành được sử dụng.

Kế hoạch có thể yêu cầu một số worker nhưng chỉ khởi chạy được một phần do worker pool đã bận. Vì vậy cần phân biệt:

- Worker dự kiến trong plan.
- Worker thực sự được cấp.
- Số worker đang hoạt động tại một thời điểm.
- Coordinator hoặc leader xử lý phần việc nào.
- Thời gian worker chờ được cấp hoặc chờ trao đổi dữ liệu.

Số worker thực tế thấp hơn dự kiến có thể là dấu hiệu worker pool cạn, nhưng cũng có thể do DBMS điều chỉnh theo thiết kế hoặc điều kiện thực thi.

## 3. Khi nào parallel query có lợi?

Song song hóa có khả năng đem lại lợi ích khi:

- Truy vấn xử lý lượng dữ liệu lớn.
- Công việc có thể chia thành các phần độc lập.
- Có đủ CPU cores và worker.
- Storage có đủ băng thông và IOPS để phục vụ nhiều luồng đọc.
- Memory đủ cho hash, sort và các operator song song.
- Chi phí khởi tạo và trao đổi dữ liệu nhỏ so với phần công việc được chia.
- Các phần dữ liệu có khối lượng tương đối cân bằng.

Ví dụ, scan và aggregate vài trăm triệu dòng để tạo báo cáo thường có cơ hội hưởng lợi từ parallelism. Ngược lại, truy vấn tìm một đơn hàng theo primary key thường đã rất nhanh; khởi tạo nhiều worker có thể tốn nhiều hơn phần công việc cần thực hiện.

### 3.1. Truy vấn nhỏ có thể chậm hơn khi song song

Parallel execution có overhead: cấp worker, khởi tạo context, trao đổi dữ liệu và hợp nhất kết quả. Với truy vấn nhỏ, overhead này có thể lớn hơn thời gian scan hoặc tính toán tuần tự.

Một truy vấn OLTP có predicate chọn lọc cao và trả về vài dòng thường phù hợp với index seek và một worker. Ép DOP cao có thể tăng CPU mà không cải thiện latency.

### 3.2. Giới hạn bởi phần tuần tự

Không phải toàn bộ truy vấn đều có thể song song. Một số bước phải chạy ở coordinator hoặc thực hiện theo thứ tự. Nếu phần lớn thời gian nằm ở một bước tuần tự, thêm worker không đem lại mức tăng tương ứng.

Có thể dùng định luật Amdahl như mô hình trực quan: nếu tỷ lệ công việc tuần tự là s, tốc độ tăng tối đa với P worker bị giới hạn xấp xỉ bởi:

~~~text
speedup <= 1 / (s + (1 - s) / P)
~~~

Công thức không tính đầy đủ overhead, I/O contention, skew và scheduler; hiệu quả thực tế thường thấp hơn giới hạn này. Ý nghĩa chính là phần tuần tự càng lớn thì lợi ích từ tăng worker càng nhỏ.

### 3.3. Parallelism không sửa một plan sai

Nếu optimizer ước lượng sai cardinality, chọn join order không hợp lý hoặc đọc quá nhiều dòng do thiếu predicate, tăng DOP có thể chỉ làm nhiều worker thực hiện công việc dư thừa nhanh hơn một chút. Hãy sửa nguyên nhân như statistics, index, predicate hoặc query shape trước khi tăng parallelism.

## 4. CPU contention và oversubscription

### 4.1. CPU utilization và runnable queue

Khi tổng số thread muốn chạy vượt số CPU cores khả dụng, scheduler phải luân phiên cấp CPU. Thread chờ trong runnable queue, context switching tăng và mỗi truy vấn mất nhiều thời gian hơn để hoàn thành.

CPU utilization cao không tự động là xấu nếu throughput vẫn tăng và latency đáp ứng SLA. Dấu hiệu bão hòa thường là CPU gần mức tối đa kéo dài, runnable queue tăng, throughput không tăng tương ứng và p95/p99 xấu đi.

### 4.2. Oversubscription do DOP và concurrency

Giả sử máy chủ có 16 logical CPUs. Nếu 10 truy vấn cùng yêu cầu DOP 8, nhu cầu worker lý thuyết có thể lên đến 80 worker, chưa kể các session và background processes. DBMS có thể giới hạn hoặc xếp hàng, nhưng workload có nguy cơ oversubscription.

Một truy vấn báo cáo có DOP 8 có thể nhanh hơn khi chạy một mình, nhưng khi nhiều báo cáo chạy cùng lúc, tất cả có thể chậm hơn vì CPU bị chia nhỏ và memory grant tăng.

### 4.3. Worker pool và parallel worker starvation

DBMS thường giới hạn số worker song song để bảo vệ tài nguyên. Khi worker pool cạn, truy vấn có thể phải chờ hoặc chạy với ít worker hơn dự kiến. Một số hệ thống có thể tiếp tục chạy phần tuần tự hoặc giảm DOP; hành vi phụ thuộc engine.

Hãy quan sát:
- Số worker đang dùng và worker tối đa.
- Thời gian chờ worker.
- Truy vấn được yêu cầu DOP cao.
- Số truy vấn song song đồng thời.
- CPU queue và throughput.

Tăng giới hạn worker có thể làm tình hình xấu hơn nếu CPU đã bão hòa. Cần kiểm tra nút thắt CPU, memory và I/O trước khi tăng.

### 4.4. Logical CPU, physical core và giới hạn container

Logical CPU không luôn tương đương một physical core đầy đủ. Hyper-threading/SMT chia sẻ một số tài nguyên thực thi của core. Máy ảo có thể có vCPU nhưng bị host oversubscription; container có thể bị giới hạn bằng CPU quota hoặc cpuset.

Khi benchmark, ghi nhận số CPU thực sự được cấp cho tiến trình DBMS, không chỉ số CPU hiển thị trong hệ điều hành. Nếu container có quota tương đương 4 core nhưng DBMS nhìn thấy 32 CPU, cấu hình parallelism dựa trên con số 32 có thể gây oversubscription.

### 4.5. NUMA và truy cập bộ nhớ

Máy chủ NUMA có nhiều node CPU và vùng RAM cục bộ. Truy cập bộ nhớ từ node khác có thể có latency và băng thông khác. Parallel worker phân tán trên nhiều node có thể tạo truy cập remote memory hoặc mất cân bằng nếu memory placement không phù hợp.

Không nên điều chỉnh NUMA chỉ dựa trên giả thuyết. Hãy xem kiến trúc máy, CPU utilization theo node, memory locality và tài liệu DBMS/hệ điều hành.

## 5. Memory contention và memory grant

### 5.1. Vì sao truy vấn cần memory?

Sort, hash join, hash aggregate, window functions và một số operator khác cần memory để giữ dữ liệu trung gian. DBMS có thể ước lượng nhu cầu và cấp memory grant trước khi thực thi hoặc dùng các vùng memory theo cấu hình.

Một truy vấn chạy song song có thể cần memory cho nhiều worker hoặc một cấu trúc chung. Cách cấp phát tùy DBMS. Khi nhiều truy vấn lớn chạy đồng thời, tổng memory grant có thể vượt ngân sách mà hệ thống có thể phục vụ.

### 5.2. Memory grant queue

Một số DBMS xếp hàng truy vấn nếu chưa thể cấp memory cần thiết. Truy vấn có thể chờ memory grant dù CPU còn rảnh. Khi đọc wait metrics, cần phân biệt chờ memory với chờ CPU hoặc storage.

Trong SQL Server, memory grant và wait liên quan đến resource semaphore là các dấu hiệu quan trọng. PostgreSQL không dùng cùng mô hình memory grant toàn truy vấn; work_mem áp dụng theo từng operation và có thể nhân lên theo số node, worker và session. Oracle quản lý work areas qua PGA. Không áp dụng cùng một công thức memory cho mọi DBMS.

### 5.3. Spill ra temporary storage

Nếu sort hoặc hash không đủ memory, DBMS có thể ghi dữ liệu tạm xuống disk hoặc temp tablespace. Spill làm tăng I/O và có thể gây độ trễ lớn.

Dấu hiệu cần xem:
- Sort spill hoặc sort runs.
- Hash batches tăng.
- Temp bytes read/written.
- Workfile/worktable hoặc temp tablespace usage.
- Memory grant thực tế so với nhu cầu.
- Số worker và mức skew.

Spill có thể do memory cấp thấp, ước lượng sai, dữ liệu tăng hoặc concurrency quá cao. Tăng memory grant cho một truy vấn có thể khiến nhiều truy vấn khác phải chờ. Hãy đánh giá tổng workload.

### 5.4. Buffer cache và query memory cạnh tranh

Buffer cache giữ data/index pages được truy cập gần đây; query memory giữ cấu trúc trung gian cho sort/hash. Hai nhu cầu cùng dùng RAM vật lý. Nếu truy vấn báo cáo tiêu thụ nhiều memory, hệ thống có thể giảm vùng cache hiệu dụng hoặc tăng áp lực lên bộ nhớ.

Không chỉ nhìn tổng RAM còn trống. Theo dõi cache hit/read, page eviction, memory pressure, process working set và temp I/O cùng thời điểm.

### 5.5. PostgreSQL work_mem và hệ quả nhân bản

Trong PostgreSQL, work_mem là giới hạn cơ bản cho một số operation sort/hash trước khi spill, không phải ngân sách tối đa cho cả session. Một truy vấn có nhiều sort/hash nodes và nhiều parallel workers có thể tiêu thụ nhiều lần work_mem. Nhiều session đồng thời còn nhân mức sử dụng này lên.

Vì vậy, tăng work_mem toàn cục có thể tạo nguy cơ memory exhaustion khi concurrency cao. Hãy cân nhắc thay đổi ở phạm vi session/transaction phù hợp và benchmark nhiều truy vấn đồng thời.

## 6. I/O contention và băng thông lưu trữ

### 6.1. Nhiều worker không làm storage nhanh hơn vô hạn

Parallel scan có thể tăng số yêu cầu đọc đồng thời. Nếu storage còn dư băng thông, throughput đọc có thể tăng. Khi đạt giới hạn IOPS, bandwidth hoặc queue depth, thêm worker chỉ làm hàng đợi dài hơn và latency tăng.

Một truy vấn có thể nhanh hơn khi chạy riêng nhưng làm truy vấn khác chậm hơn do chiếm băng thông storage. Cần xem throughput và latency ở cấp thiết bị/volume, không chỉ thời gian query.

### 6.2. Sequential I/O và random I/O

Scan tuần tự lớn có thể tận dụng read-ahead và băng thông. Index lookup ngẫu nhiên có thể tạo nhiều I/O nhỏ rải rác. Parallelism thay đổi mức đồng thời của các yêu cầu nhưng không tự biến random I/O thành sequential I/O.

Nếu storage latency cao, hãy xem access pattern, buffer cache, index selectivity và khả năng đọc trước. Một scan song song trên bảng lớn có thể bão hòa storage nhanh hơn; một index lookup có thể giảm bytes nhưng tạo nhiều IOPS.

### 6.3. Queue depth

Queue depth là số yêu cầu I/O đang chờ hoặc đang được xử lý. Queue depth tăng có thể giúp tận dụng storage có khả năng xử lý nhiều request, nhưng khi vượt điểm tối ưu, latency sẽ tăng.

Đo IOPS, throughput, average/p95 latency và queue depth cùng lúc. Không tối ưu chỉ theo một chỉ số như IOPS cao nhất.

### 6.4. Buffer cache và cache pollution

Một truy vấn scan bảng rất lớn có thể đẩy các trang nóng của workload OLTP ra khỏi cache, tùy cơ chế cache của DBMS. Sau khi báo cáo kết thúc, truy vấn point lookup có thể phải đọc storage nhiều hơn.

Hãy theo dõi buffer/cache hit, physical reads và latency của các query fingerprint khác trong lúc chạy scan lớn. Resource governance, giới hạn DOP, partition pruning hoặc replica báo cáo có thể giảm tác động.

## 7. Temporary storage và vùng dữ liệu trung gian

### 7.1. Temp space được dùng khi nào?

DBMS có thể dùng temporary storage cho:
- Sort vượt memory.
- Hash join hoặc hash aggregate spill.
- Materialize intermediate result.
- Temporary table và worktable.
- Một số thao tác index build, online maintenance hoặc query plan.

Tên và cấu trúc khác nhau: PostgreSQL dùng temporary files/tablespaces; SQL Server có tempdb; Oracle có temporary tablespace; MySQL có internal temporary tables và các cơ chế spill tùy operator/engine.

### 7.2. Tranh chấp temp storage

Nhiều truy vấn cùng spill có thể cạnh tranh cùng volume temp. Điều này làm tăng I/O latency, tăng thời gian sort/hash và tạo vòng lặp phản hồi: query chạy lâu hơn, giữ memory/worker lâu hơn, làm truy vấn khác xếp hàng.

Hãy đo temp bytes, temp file count, spill count, latency và dung lượng còn trống. Temp disk đầy có thể khiến truy vấn thất bại; temp I/O cao có thể làm toàn workload chậm.

### 7.3. Cách giảm temp I/O

Có thể giảm lượng dữ liệu trung gian bằng cách:
- Lọc sớm và giảm số cột được truyền qua plan.
- Chọn join order và index phù hợp.
- Cải thiện statistics để memory/plan estimates chính xác hơn.
- Giảm số dòng cần sort hoặc aggregate.
- Tránh materialize kết quả lớn không cần thiết.
- Điều chỉnh memory trong giới hạn tổng thể.
- Giới hạn concurrency của truy vấn báo cáo nặng.

Tăng temp storage capacity giúp tránh hết dung lượng nhưng không loại bỏ chi phí spill. Cần tìm nguyên nhân tạo dữ liệu tạm.

## 8. Data skew và mất cân bằng worker

### 8.1. Skew là gì?

Data skew xảy ra khi dữ liệu không phân bố đều theo khóa hoặc partition. Ví dụ một tenant chiếm 70% số đơn hàng, còn hàng nghìn tenant khác chia phần còn lại. Nếu DBMS chia công việc theo tenant_id, một worker có thể nhận phần lớn dữ liệu trong khi worker khác hoàn tất sớm.

Thời gian truy vấn song song bị giới hạn bởi worker chậm nhất và bước tổng hợp cuối. Vì vậy, nhiều worker không đồng nghĩa công việc được chia đều.

### 8.2. Skew trong hash join và repartition

Nếu repartition theo khóa có một giá trị xuất hiện rất nhiều lần, một worker hoặc partition có thể nhận phần lớn dòng. Hash table của worker đó lớn hơn, có thể spill, trong khi worker khác gần như rảnh.

Kiểm tra rows per worker, hash batches, memory, spill và thời gian hoàn thành từng nhánh nếu DBMS cung cấp. So sánh phân bố khóa bằng thống kê hoặc truy vấn phân tích phù hợp.

### 8.3. Skew trong partition scan

Partition có kích thước rất khác nhau hoặc predicate chọn một số partition lớn có thể làm worker mất cân bằng. Partition pruning giúp bỏ vùng không cần đọc, nhưng không tự bảo đảm phần còn lại được chia đều.

Thiết kế partition key dựa trên access pattern và tốc độ tăng dữ liệu. Tránh chọn key chỉ có vài giá trị hoặc phân bố lệch nặng nếu workload cần chia song song theo key đó.

### 8.4. Cách xử lý skew

Tùy nguyên nhân, có thể:
- Chọn partition key hoặc distribution key cân bằng hơn.
- Dùng chiến lược xử lý riêng cho hot key.
- Tách nhóm dữ liệu quá lớn nếu mô hình nghiệp vụ cho phép.
- Cải thiện statistics và ước lượng cardinality.
- Tránh repartition theo khóa có một giá trị áp đảo.
- Giảm lượng cột/dòng truyền qua exchange.
- Chấp nhận DOP thấp hơn nếu overhead mất cân bằng lớn.

Không dùng salting hoặc thay đổi khóa chỉ để cân bằng nếu điều đó làm phức tạp semantics, uniqueness hoặc tính nhất quán.

## 9. Tranh chấp khóa, latch và các đồng bộ nội bộ

### 9.1. Lock contention

Lock bảo vệ tính nhất quán khi transaction đọc/ghi dữ liệu theo isolation và cơ chế của DBMS. Nếu nhiều transaction cùng cập nhật một dòng, phạm vi khóa hoặc tài nguyên liên quan, chúng có thể phải chờ nhau.

Ví dụ mọi request cùng cập nhật một dòng tổng số lượt mua:

~~~sql
UPDATE product_counters
SET purchase_count = purchase_count + 1
WHERE product_id = 101;
~~~

Nếu một sản phẩm rất phổ biến, dòng counter đó trở thành hot row. Thêm worker hoặc tăng concurrency không làm tăng tốc cập nhật cùng một dòng; nó có thể chỉ làm lock wait tăng.

### 9.2. Latch và mutex contention

Latch/mutex là cơ chế đồng bộ nội bộ bảo vệ cấu trúc trong bộ nhớ hoặc metadata. Chúng khác với transaction locks vốn bảo vệ dữ liệu logic và transaction isolation.

Ví dụ có thể xảy ra contention trên:
- Buffer/page structures.
- B-tree index pages hoặc hot insertion points.
- Lock manager hoặc metadata.
- Allocation structures của temp space.
- Shared memory queues.

Tên wait cụ thể tùy DBMS. Cần phân biệt lock wait với latch/mutex wait vì hướng khắc phục khác nhau.

### 9.3. Hot pages và index contention

Nhiều transaction insert khóa tăng dần có thể tập trung vào leaf page cuối của B-tree. Tùy engine và index design, điều này có thể tạo page latch contention hoặc page split. Index có key phân bố ngẫu nhiên có thể giảm hot end nhưng tăng random I/O và fragmentation.

Đánh giá theo metric của DBMS, insert rate, wait events, page split và cấu trúc khóa. Không thay đổi fill factor hoặc key design chỉ dựa trên giả thuyết.

### 9.4. Deadlock và lock escalation

Deadlock xảy ra khi các transaction giữ tài nguyên và chờ nhau theo chu trình. DBMS thường phát hiện và hủy một transaction để phá chu trình. Lock escalation là cơ chế một số DBMS dùng để thay nhiều lock nhỏ bằng lock phạm vi lớn hơn khi vượt ngưỡng hoặc áp lực quản lý lock.

Song song trong một truy vấn không đồng nghĩa deadlock; deadlock thường liên quan đến thứ tự truy cập và tương tác giữa transaction. Hãy xem deadlock graph, thứ tự cập nhật, transaction duration và index hỗ trợ.

### 9.5. Tách biệt resource contention với blocking nghiệp vụ

Một session có thể chờ lock vì transaction khác giữ dữ liệu, trong khi CPU và storage vẫn còn dư. Session khác có thể chờ CPU dù không có lock. Không thể gọi mọi wait là “database chậm” rồi tăng DOP.

Phân loại wait theo CPU, I/O, memory, worker, lock, latch, network và client. Sau đó ghép với query plan và transaction context để tìm nguyên nhân.

## 10. Queueing: vì sao thêm tải làm latency tăng nhanh?

Khi tài nguyên gần bão hòa, một truy vấn phải chờ lâu hơn trước khi được CPU, worker, memory hoặc I/O phục vụ. Thời gian phản hồi gồm thời gian thực thi và thời gian chờ.

Một hệ thống có thể có throughput tăng khi concurrency tăng từ 1 lên 8. Nhưng khi concurrency tiếp tục tăng, throughput có thể chững lại trong khi latency tăng mạnh do queueing.

Little's Law mô tả quan hệ cơ bản trong trạng thái ổn định:

~~~text
Số request trung bình trong hệ thống
  = Throughput trung bình × Thời gian lưu lại trung bình
~~~

Đây là quan hệ tổng quát của hệ thống hàng đợi, không phải công thức xác định trực tiếp DOP tối ưu. Nó giúp hiểu rằng nếu throughput không tăng mà thời gian chờ tăng, số request đang nằm trong hệ thống sẽ tăng.

Hãy đo:
- Active sessions và queued sessions.
- Throughput theo transaction/query type.
- p50/p95/p99 latency.
- CPU runnable queue.
- Worker wait và memory grant wait.
- I/O queue depth.
- Lock/latch wait.
- Connection pool wait ở ứng dụng.

Một connection pool quá lớn có thể đẩy quá nhiều request vào DBMS cùng lúc, tăng queueing mà không tăng throughput. Admission control ở ứng dụng hoặc DBMS có thể giữ concurrency ở vùng hệ thống xử lý hiệu quả.

## 11. Đọc execution plan và metric của truy vấn song song

### 11.1. Những gì cần tìm trong plan

Khi xem actual plan, hãy xác định:

- Có parallel scan hay không?
- DOP dự kiến và worker thực tế là bao nhiêu?
- Công việc được chia theo partition, range hay hash key?
- Có exchange/repartition/gather không?
- Rows per worker có cân bằng không?
- Có sort/hash aggregate hoặc hash join lớn không?
- Có spill, temp I/O hoặc memory grant wait không?
- Có node tuần tự chiếm phần lớn thời gian không?
- Estimated rows có gần actual rows không?

### 11.2. Actual plan quan trọng hơn nhãn Parallel

Một plan có chữ Parallel không tự chứng minh hiệu quả. Hãy so sánh:
- Elapsed time.
- CPU time tổng.
- Logical/buffer reads và physical reads.
- Worker utilization.
- Rows processed.
- Exchange bytes.
- Temp I/O.
- Wait time và queueing.

Một truy vấn có elapsed time giảm nhưng CPU time tăng nhiều có thể đang dùng tài nguyên hệ thống nhiều hơn. Nếu chỉ có một báo cáo chạy, điều này có thể chấp nhận; nếu có nhiều request OLTP cùng lúc, tác động tổng thể có thể không tốt.

### 11.3. PostgreSQL

PostgreSQL có thể dùng Parallel Seq Scan, Parallel Bitmap Heap Scan, Parallel Hash Join và Parallel Aggregate tùy phiên bản, plan và điều kiện. Gather thu kết quả từ workers; Gather Merge hợp nhất các luồng đã sắp xếp.

Có thể dùng:

~~~sql
EXPLAIN (ANALYZE, BUFFERS, VERBOSE, SETTINGS)
SELECT region_id, SUM(total_amount)
FROM orders
WHERE created_at >= TIMESTAMP '2026-01-01 00:00:00'
GROUP BY region_id;
~~~

Kiểm tra Workers Planned, Workers Launched, actual rows, loops, buffers, sort method, temp blocks và thời gian. PostgreSQL có giới hạn parallel workers toàn hệ thống và theo query. work_mem có thể được dùng bởi nhiều operator và worker, nên cần đánh giá tổng memory khi concurrency tăng.

EXPLAIN ANALYZE thực thi truy vấn thật và tạo tải; chỉ chạy truy vấn nặng trong môi trường phù hợp. Các thiết lập parallel cost và worker limit phải được điều chỉnh theo phiên bản và benchmark.

### 11.4. SQL Server

SQL Server có thể dùng parallel scans, parallel joins, exchange operators và parallel aggregates. Actual Execution Plan có thể hiển thị DOP, actual rows theo thread, exchange, memory grant và spill warnings. Query có thể bị giới hạn bởi MAXDOP, cost threshold for parallelism, Resource Governor hoặc giới hạn worker.

Cần xem wait statistics như CXPACKET/CXCONSUMER ở phiên bản phù hợp, nhưng không kết luận rằng các wait này luôn là lỗi. Chúng có thể xuất hiện bình thường trong plan song song. Tập trung vào mất cân bằng worker, thời gian chờ, CPU và elapsed time. Kiểm tra memory grant và tempdb khi sort/hash spill.

### 11.5. Oracle

Oracle Parallel Execution có thể phân chia công việc giữa parallel execution servers. Plan có thể hiển thị PX SEND/PX RECEIVE và các bước phân phối dữ liệu như hash hoặc broadcast. DOP, parallel server pool, PGA và TEMP tablespace ảnh hưởng đến hiệu năng.

Kiểm tra DOP thực tế, số PX servers, phân phối dữ liệu, skew, temp usage và wait events. Một truy vấn có DOP cao có thể chiếm nhiều parallel servers và làm các truy vấn khác phải chờ.

### 11.6. MySQL

Không nên giả định mọi câu SELECT trên MySQL đều có cơ chế intra-query parallelism tổng quát giống các hệ thống hỗ trợ parallel query. MySQL/InnoDB có concurrency ở nhiều connection và một số thao tác cụ thể có thể dùng nhiều thread, nhưng phạm vi parallel execution của câu truy vấn phụ thuộc phiên bản, engine và tính năng. Hãy đọc tài liệu đúng phiên bản và kiểm tra plan/metrics thực tế thay vì áp dụng DOP chung từ DBMS khác.

Dù một SELECT chủ yếu chạy trên một execution thread, nhiều truy vấn đồng thời vẫn tranh chấp CPU, buffer pool, I/O, locks và temporary tables.

## 12. Benchmark đúng: truy vấn đơn và workload đồng thời

### 12.1. Đo một truy vấn riêng lẻ

Chạy query ở concurrency thấp để hiểu thời gian xử lý khi ít tranh chấp. So sánh DOP khác nhau nếu DBMS hỗ trợ. Ghi elapsed time, CPU time, logical/physical reads, memory, temp I/O và worker count.

Không chỉ đo một lần. Cache state, background tasks và dữ liệu tham số có thể làm kết quả dao động. Dùng nhiều lần chạy và giữ cùng điều kiện.

### 12.2. Đo workload hỗn hợp

Tạo workload gần production với các loại truy vấn:
- Point lookup và API OLTP ngắn.
- Range scan và list query.
- JOIN/aggregate báo cáo.
- INSERT/UPDATE/DELETE.
- Batch job và tác vụ bảo trì nếu chúng thường chạy cùng thời điểm.

Giữ tỷ lệ query, dữ liệu, tham số và transaction mix đại diện. Chạy ở nhiều mức concurrency để tìm điểm throughput bão hòa.

### 12.3. Đo phân vị và throughput

Ghi:
- Throughput tổng và theo nhóm query.
- p50, p95 và p99 latency.
- CPU utilization và runnable queue.
- Memory usage, grant wait và spill.
- IOPS, throughput, storage latency và queue depth.
- Temp bytes và temp file activity.
- Lock/latch wait, deadlock và retry.
- Worker pool usage và connection pool wait.

Mean latency không đủ để đánh giá trải nghiệm. Một số truy vấn có thể bị chậm nghiêm trọng khi memory grant hoặc worker pool phải xếp hàng, trong khi mean vẫn có vẻ chấp nhận được.

### 12.4. Warm-up và cache state

Phân biệt cold-cache, warm-cache và mixed-cache. Không so sánh một lần chạy lạnh ở cấu hình này với một lần chạy nóng ở cấu hình khác. Nếu workload thực tế có working set lớn hơn RAM, benchmark chỉ dùng một tập nhỏ có thể đánh giá quá cao hiệu quả cache.

Không xóa cache trên production chỉ để tạo phép đo. Hãy dùng môi trường kiểm thử hoặc phương pháp replay an toàn.

### 12.5. Tăng concurrency có kiểm soát

Tăng client theo từng bước, ví dụ 1, 4, 8, 16, 32 nếu phù hợp với tài nguyên. Ở mỗi mức, chạy đủ lâu để quan sát trạng thái ổn định và ghi throughput, latency, queue và waits.

Điểm phù hợp thường nằm trước khi throughput chững lại và p95/p99 tăng nhanh. Không chọn concurrency chỉ dựa vào mức sử dụng CPU cao nhất.

## 13. Quy trình điều tra tranh chấp tài nguyên

### Bước 1: Xác định triệu chứng

Xác định truy vấn nào chậm, nhóm người dùng nào bị ảnh hưởng và thời điểm xảy ra. So sánh p95/p99 với baseline, không chỉ tổng CPU.

### Bước 2: Phân loại wait

Phân nhóm thời gian chờ:
- CPU/runnable queue.
- Worker availability.
- Memory grant hoặc memory pressure.
- Data I/O và log I/O.
- Temporary I/O.
- Lock/latch/mutex.
- Network/client consumption.

### Bước 3: Ghép wait với execution plan

Xem query plan, actual rows, loops, DOP, exchange, memory grant, spill và số dòng mỗi worker. Xác định node nào tạo ra nhiều dữ liệu trung gian hoặc sử dụng tài nguyên lớn.

### Bước 4: Kiểm tra workload đồng thời

Xác định query nào chạy cùng thời điểm và chia sẻ cùng tài nguyên. Một báo cáo scan lớn có thể làm cache miss tăng; một batch sort có thể làm tempdb bận; nhiều transaction cùng cập nhật hot row có thể gây lock contention.

### Bước 5: Đưa ra giả thuyết có thể đo

Ví dụ:
- DOP cao tạo CPU oversubscription.
- Hash join spill do memory grant thấp hoặc cardinality sai.
- Parallel repartition mất cân bằng do hot key.
- Storage queue tăng vì nhiều parallel scans.
- Một dòng counter tạo lock contention.
- Worker pool cạn vì nhiều báo cáo chạy song song.

### Bước 6: Thử một thay đổi

Thử giảm DOP, giới hạn concurrency, cải thiện index/filter, cập nhật statistics, giảm cột trung gian, tách workload báo cáo hoặc điều chỉnh memory trong phạm vi phù hợp. Chỉ thay một yếu tố mỗi lần nếu cần xác định quan hệ nhân quả.

### Bước 7: Benchmark lại toàn workload

Xác nhận query mục tiêu cải thiện và các query khác không bị regression. Đo throughput, p95/p99, CPU, memory, I/O, waits và lỗi.

### Bước 8: Theo dõi sau triển khai

Quan sát giờ cao điểm, batch window và các chu kỳ checkpoint/maintenance. Lưu lại cấu hình trước thay đổi và kế hoạch rollback.

## 14. Các biện pháp giảm tranh chấp

### 14.1. Đặt giới hạn DOP hợp lý

Không cấp DOP cao cho mọi truy vấn. Dùng cấu hình toàn hệ thống hoặc hint theo query trong phạm vi DBMS hỗ trợ. Truy vấn nhỏ thường không cần song song; truy vấn phân tích lớn có thể được cấp DOP cao hơn trong cửa sổ hoặc resource group phù hợp.

Đánh giá DOP bằng throughput và tail latency của workload hỗn hợp, không chỉ elapsed time của một báo cáo.

### 14.2. Admission control và resource governance

Giới hạn số truy vấn nặng được chạy đồng thời. Có thể dùng workload groups, resource pools, query queues hoặc giới hạn ở application layer. Mục tiêu là không để một nhóm truy vấn chiếm hết CPU, memory grant, worker hoặc I/O.

Đặt ngưỡng dựa trên capacity test và SLA. Hạn chế quá chặt có thể tạo queue dài; quá lỏng không ngăn được bão hòa.

### 14.3. Tách workload OLTP và báo cáo

Nếu báo cáo scan lớn gây ảnh hưởng OLTP, cân nhắc:
- Read replica hoặc reporting database.
- ETL/ELT sang analytical store.
- Materialized view hoặc summary table.
- Lịch chạy batch ngoài giờ cao điểm.
- Resource group riêng cho báo cáo.

Replica có thể lag; nếu nghiệp vụ cần đọc dữ liệu mới nhất, phải xem consistency và replication delay. Tách workload cũng có chi phí hạ tầng và vận hành.

### 14.4. Giảm lượng dữ liệu phải xử lý

Lọc sớm, projection chỉ lấy cột cần thiết, partition pruning và index phù hợp giúp giảm scan, exchange và memory. Với JOIN, kiểm tra cardinality và loại bỏ fan-out không cần thiết. Với sort, chỉ sắp xếp tập dòng cần thiết nếu semantics cho phép.

### 14.5. Xử lý hot key và hot row

Nếu một khóa hoặc dòng bị nhiều transaction truy cập, có thể:
- Giảm số lần cập nhật cùng một counter bằng batch.
- Dùng sharded counters rồi tổng hợp.
- Rút ngắn transaction và giữ khóa ít lâu.
- Sắp xếp thứ tự truy cập tài nguyên nhất quán để giảm deadlock.
- Xem lại index key và partitioning.

Sharded counter làm tăng chi phí đọc/tổng hợp và cần bảo đảm cập nhật chính xác. Chỉ dùng khi số liệu chứng minh hot row là bottleneck.

### 14.6. Quản lý memory và temp

Tối ưu statistics, query shape và index để giảm hash/sort spill. Đặt ngân sách memory cho workload, theo dõi temp capacity và tránh tăng work_mem hoặc grant cho mọi truy vấn mà không tính concurrency.

### 14.7. Bảo đảm storage đủ khả năng

Nếu I/O là bottleneck, hãy đo storage latency, IOPS, throughput và queue depth. Có thể cần phân tách data/log/temp volume, thay storage class hoặc giới hạn parallel scan. Việc tách volume chỉ hữu ích khi chúng thực sự có tài nguyên backend độc lập hoặc giảm được tranh chấp.

## 15. Ví dụ: báo cáo song song làm API chậm

Giả sử một hệ thống có 16 logical CPUs và 64 GB RAM. API tra cứu đơn hàng bình thường có p95 là 40 ms. Một dashboard doanh thu chạy scan lớn với DOP 8. Khi nhiều người mở dashboard cùng lúc, API tăng p95 lên 350 ms.

Cần điều tra theo hướng:

1. So sánh CPU utilization, runnable queue và throughput trước/sau khi dashboard chạy.
2. Kiểm tra số parallel workers được yêu cầu và thực tế.
3. Xem dashboard có hash aggregate hoặc sort spill không.
4. Đo storage read throughput, latency và queue depth.
5. Kiểm tra buffer cache hit của API trong cùng khoảng thời gian.
6. Xem dashboard có tạo nhiều temp I/O hay chiếm memory grant không.
7. Kiểm tra query plan và số dòng được scan.
8. Thử giảm DOP dashboard hoặc giới hạn số dashboard đồng thời.
9. Thử chạy dashboard trên reporting replica nếu chấp nhận replication lag.
10. Benchmark lại cả dashboard lẫn API ở cùng mức tải.

Nếu giảm DOP làm dashboard chậm hơn một chút nhưng API trở lại p95 gần baseline và throughput tổng thể tăng, đó có thể là cấu hình tốt hơn. Nếu CPU còn dư nhưng temp I/O bão hòa, cần tập trung vào spill và storage thay vì chỉ giảm worker.

## 16. Những ngộ nhận thường gặp

**DOP càng cao thì truy vấn càng nhanh.** Overhead, phần tuần tự, CPU contention và I/O saturation có thể làm truy vấn chậm hơn.

**CPU utilization 100% luôn là mục tiêu tốt.** CPU cao có thể phù hợp nếu throughput tăng và latency đáp ứng SLA; nếu queue và p99 tăng, hệ thống có thể đang bão hòa.

**Một truy vấn chạy nhanh hơn chứng minh cấu hình tốt hơn.** Cần đo nhiều truy vấn đồng thời và tác động lên workload còn lại.

**Worker dự kiến bằng worker thực tế.** Worker pool có thể không cấp đủ; phải xem actual workers launched.

**Parallel query chỉ tranh chấp CPU.** Nó còn sử dụng memory, I/O, temp storage, buffer cache và worker pool.

**Tăng memory luôn loại bỏ spill.** Memory lớn cho một query có thể làm nhiều query khác chờ hoặc gây áp lực RAM.

**Wait event là nguyên nhân gốc.** Wait chỉ cho biết session đang chờ; cần ghép với plan, metrics và workload.

**Mọi DBMS hỗ trợ parallel SELECT theo cùng cách.** Cơ chế và phạm vi song song khác nhau theo sản phẩm, engine và phiên bản.

**Tách data, log và temp volume luôn tăng tốc.** Nếu cùng backend storage hoặc bottleneck là CPU/memory, tách volume có thể không giúp.

**Tăng connection pool sẽ tăng throughput.** Quá nhiều kết nối có thể làm DBMS queueing và contention tăng mà throughput không đổi.

## 17. Checklist đánh giá song song và tranh chấp tài nguyên

- [ ] Đã phân biệt song song trong một query với nhiều query đồng thời chưa?
- [ ] Đã ghi DOP dự kiến và số worker thực tế chưa?
- [ ] Đã xem exchange, repartition, gather và rows per worker chưa?
- [ ] Đã đo CPU utilization, runnable queue và context switching chưa?
- [ ] Đã xác minh CPU quota/vCPU thực sự cấp cho DBMS chưa?
- [ ] Đã xem worker pool usage và worker wait chưa?
- [ ] Đã đo memory grant, memory pressure và grant wait chưa?
- [ ] Đã kiểm tra sort/hash spill và temporary I/O chưa?
- [ ] Đã đo buffer cache hit, physical reads và cache eviction chưa?
- [ ] Đã đo storage IOPS, throughput, latency và queue depth chưa?
- [ ] Đã kiểm tra data skew và mất cân bằng worker chưa?
- [ ] Đã phân biệt lock contention với latch/mutex contention chưa?
- [ ] Đã xác định hot row, hot key hoặc index page contention chưa?
- [ ] Đã benchmark workload hỗn hợp ở nhiều mức concurrency chưa?
- [ ] Đã so sánh throughput và p50/p95/p99 trước/sau chưa?
- [ ] Đã xác minh truy vấn khác không bị regression chưa?
- [ ] Đã cân nhắc giới hạn DOP, admission control hoặc tách workload chưa?
- [ ] Đã lưu baseline và phương án rollback chưa?

## Kết luận

Song song trong truy vấn giúp chia công việc lớn cho nhiều worker; concurrency giúp nhiều truy vấn độc lập cùng sử dụng tài nguyên. Cả hai có thể tăng throughput khi hệ thống còn capacity, nhưng cũng có thể gây CPU oversubscription, worker starvation, memory grant queue, hash/sort spill, I/O saturation, cache pollution, temp contention và lock/latch waits.

DOP tối ưu phụ thuộc kích thước đầu vào sau lọc, khả năng chia việc, phần tuần tự, skew, memory, storage và số truy vấn đồng thời. Hãy đọc actual plan để biết công việc được chia thế nào, ghép wait metrics với CPU/memory/I/O, rồi benchmark workload hỗn hợp ở nhiều mức concurrency. Giới hạn DOP, admission control và tách workload chỉ nên áp dụng khi số liệu chỉ ra đúng nút thắt. Kết quả tốt là throughput tăng hoặc được duy trì với p95/p99 phù hợp, không làm một truy vấn nhanh lên bằng cách khiến phần còn lại của hệ thống chậm đi.

