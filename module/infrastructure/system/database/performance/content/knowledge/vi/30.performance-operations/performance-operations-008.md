# Quản lý chi phí tài nguyên theo thông lượng và mục tiêu độ trễ

Vận hành cơ sở dữ liệu hiệu quả đòi hỏi cân bằng giữa lượng công việc hoàn tất, thời gian người dùng phải chờ và tài nguyên tiêu thụ để tạo ra kết quả. Tăng số truy vấn đồng thời có thể làm throughput tăng trong một khoảng, nhưng khi CPU, bộ nhớ, I/O, khóa hoặc connection đạt giới hạn, hàng đợi sẽ dài và p95/p99 tăng nhanh. Ngược lại, giới hạn concurrency quá thấp có thể giữ latency ổn định nhưng bỏ phí năng lực hệ thống. Quản lý chi phí tài nguyên vì thế phải dựa trên số liệu của workload thực tế và mục tiêu dịch vụ đã thống nhất.

Trong chương **Vận hành hiệu năng** của module **DATABASE_PERFORMANCE**, bài học này hướng dẫn quản lý chi phí tài nguyên theo thông lượng và mục tiêu độ trễ. Module **DATABASE_PERFORMANCE** rèn phương pháp tối ưu hiệu năng cơ sở dữ liệu dựa trên đo đạc tải, kế hoạch thực thi, thống kê và cơ chế truy cập dữ liệu; nội dung bao gồm thiết kế chỉ mục, cải thiện SQL, nhận diện tranh chấp giao dịch, nút thắt I/O, bộ nhớ và kiểm chứng sau điều chỉnh. Vì vậy, quyết định vận hành cần liên kết số liệu CPU, bộ nhớ, I/O, dung lượng, kết nối và kế hoạch truy vấn với throughput, latency, độ ổn định và chi phí trên mỗi đơn vị công việc hoàn tất.

## 1. Ba đại lượng phải quản lý cùng nhau

### 1.1. Throughput và goodput

Throughput là lượng công việc được xử lý trong một đơn vị thời gian, ví dụ:

- Giao dịch hoàn tất mỗi giây (TPS).
- Truy vấn hoàn tất mỗi giây (QPS).
- Số hàng được nạp hoặc cập nhật mỗi giây.
- Số sự kiện được xử lý mỗi phút.
- Số báo cáo được tạo trong một giờ.

Cần phân biệt throughput với goodput. Goodput chỉ tính công việc hoàn tất hợp lệ và có ích cho nghiệp vụ. Nếu hệ thống nhận 1.000 request/giây nhưng 300 request timeout, 200 request retry trùng và chỉ 500 request hoàn tất, throughput thô có thể che khuất năng lực thực tế.

Khi so sánh cấu hình, hãy ghi nhận số giao dịch thành công, số lỗi, số timeout, số retry và lượng công việc bị hủy. Không xem việc tăng request được nhận vào là cải thiện nếu số giao dịch hoàn tất không tăng.

### 1.2. Latency và mục tiêu độ trễ

Latency là thời gian từ khi yêu cầu bắt đầu đến khi kết quả được trả về. Với hệ thống cơ sở dữ liệu, cần tách các thành phần:

- Thời gian chờ trong hàng đợi ứng dụng.
- Thời gian chờ lấy connection.
- Thời gian chờ khóa hoặc tài nguyên.
- Thời gian thực thi SQL.
- Thời gian đọc và truyền kết quả.
- Thời gian commit và ghi log.

Đo các phân vị thay vì chỉ đo trung bình:

- p50 phản ánh trải nghiệm phổ biến.
- p95 phản ánh nhóm request chậm đáng kể.
- p99 cho thấy đuôi độ trễ và các trường hợp hiếm nhưng có thể ảnh hưởng lớn.

Một hệ thống có latency trung bình 50 ms nhưng p99 là 8 giây vẫn có thể vi phạm mục tiêu dịch vụ. Các request chậm thường giữ connection, transaction và tài nguyên lâu hơn, làm tăng latency của những request đến sau.

### 1.3. Chi phí tài nguyên

Chi phí tài nguyên là lượng năng lực hệ thống cần để hoàn tất công việc. Với database, cần theo dõi ít nhất:

- CPU time và mức sử dụng core.
- Bộ nhớ cho buffer/cache, sort/hash, connection và tiến trình.
- Logical reads, physical reads, bytes đọc/ghi.
- WAL/redo/transaction log được tạo.
- IOPS, throughput và latency của storage.
- Network bytes và số lượt trao đổi.
- Connection, worker, lock và thời gian giữ transaction.
- Dung lượng bảng, index, temporary storage và backup.

Không có một chỉ số đơn lẻ mô tả đầy đủ chi phí. CPU thấp có thể đi cùng lock wait cao; buffer cache hit tốt có thể che khuất temp I/O lớn; throughput cao có thể đạt được bằng cách tăng concurrency đến mức p99 không chấp nhận được.

## 2. Định nghĩa SLO trước khi tối ưu

SLO (Service Level Objective) mô tả mục tiêu dịch vụ trong một khoảng thời gian. Ví dụ một API đọc đơn hàng có thể đặt:

- p95 dưới 200 ms.
- p99 dưới 700 ms.
- Tỷ lệ lỗi dưới 0,1%.
- Throughput tối thiểu 800 request/giây ở tải đã định nghĩa.

Một job báo cáo có thể có SLO khác:

- Hoàn tất trong 20 phút.
- Không làm p95 của giao dịch OLTP vượt ngưỡng.
- Dùng tối đa một ngân sách CPU hoặc I/O đã thống nhất.
- Kết quả phải đầy đủ và có thể đối soát.

SLO cần nêu rõ phạm vi request, điều kiện tải, dữ liệu thử, khoảng đo và cách tính percentile. Không so sánh hai lần benchmark nếu một lần dùng cache nóng và lần còn lại dùng cache lạnh, hoặc nếu số tenant, kích thước dữ liệu và concurrency khác nhau.

Một mục tiêu hữu ích cần bao gồm cả latency lẫn throughput. Chỉ đặt latency thấp có thể khiến hệ thống giới hạn concurrency quá mức; chỉ đặt throughput cao có thể khiến hàng đợi và p99 tăng vượt ngưỡng.

## 3. Hiểu quan hệ giữa concurrency, thời gian xử lý và throughput

Concurrency là số công việc đang được xử lý hoặc chờ tài nguyên cùng lúc. Tăng concurrency có thể giúp che giấu thời gian chờ I/O và sử dụng CPU tốt hơn. Tuy nhiên, sau một điểm bão hòa, các công việc cạnh tranh nhau và throughput không tăng tương ứng.

Định luật Little mô tả quan hệ ở trạng thái ổn định:

~~~text
Số công việc đang ở trong hệ thống (L)
    = tốc độ đến hoặc hoàn tất trung bình (λ)
      × thời gian ở trong hệ thống trung bình (W)
~~~

Ví dụ, nếu hệ thống hoàn tất 400 request/giây và mỗi request ở trong hệ thống trung bình 0,1 giây, số request đồng thời trung bình xấp xỉ 40.

Nếu thời gian xử lý tăng lên 0,5 giây trong khi throughput vẫn là 400 request/giây, số request đồng thời trung bình có thể tăng lên khoảng 200. Điều này giải thích vì sao một truy vấn chậm có thể làm pool và hàng đợi cạn nhanh dù lưu lượng đầu vào không đổi.

Little's Law là quan hệ trung bình, không thay thế phân tích p95/p99 hoặc burst. Hãy dùng nó để kiểm tra tính hợp lý của số liệu, sau đó đo phân bố thời gian và độ sâu hàng đợi thực tế.

## 4. Utilization, saturation và queueing

Ba khái niệm cần phân biệt:

- **Utilization:** tỷ lệ tài nguyên đang được sử dụng.
- **Saturation:** mức độ công việc phải chờ vì tài nguyên không đủ.
- **Errors:** công việc thất bại hoặc bị từ chối.

CPU utilization cao chưa chắc là vấn đề nếu throughput tăng và latency vẫn trong SLO. Ngược lại, utilization trung bình có thể không cao nhưng một tài nguyên cụ thể như connection pool, disk queue hoặc lock manager đã bão hòa.

Khi một tài nguyên tiến gần giới hạn, thời gian chờ thường tăng không tuyến tính. Một hệ thống chạy ổn ở 60% mức tải có thể tăng p99 mạnh khi tiến đến vùng 90–100%, tùy đặc tính workload và khả năng song song.

Hãy theo dõi cùng lúc:

- Mức sử dụng tài nguyên.
- Độ sâu và thời gian chờ trong hàng đợi.
- Throughput hoàn tất.
- Latency p50/p95/p99.
- Timeout, error và retry.
- Thời gian phục hồi sau burst.

Mục tiêu vận hành là giữ đủ headroom để hấp thụ biến động và tránh để hàng đợi phát triển mất kiểm soát.

## 5. Xây dựng ngân sách tài nguyên theo đơn vị công việc

Thay vì chỉ nói database dùng 70% CPU, hãy tính tài nguyên trên mỗi đơn vị công việc hoàn tất. Một số chỉ số hữu ích:

~~~text
CPU cost per transaction =
    tổng CPU time / số transaction thành công

Read cost per transaction =
    tổng bytes đọc hoặc logical reads / số transaction thành công

Write cost per transaction =
    tổng bytes ghi hoặc WAL/redo bytes / số transaction thành công

Retry amplification =
    tổng số lần thực thi / số request nghiệp vụ ban đầu
~~~

Ví dụ giả định: trong 10 phút, database dùng 120 CPU-seconds và hoàn tất 60.000 giao dịch. CPU cost là 2 ms trên mỗi giao dịch thành công. Nếu sau thay đổi CPU time tăng lên 180 giây nhưng số giao dịch chỉ tăng lên 63.000, CPU cost tăng lên khoảng 2,86 ms/giao dịch. Throughput tăng nhẹ nhưng hiệu quả tài nguyên giảm.

Các phép tính cần dùng cùng phạm vi thời gian và cùng định nghĩa transaction. Nếu một request gọi ba câu SQL, hãy quyết định ngân sách được tính theo request nghiệp vụ hay theo statement.

## 6. Xây dựng mô hình chi phí đa tài nguyên

Một workload có thể tiêu thụ nhiều tài nguyên khác nhau. Có thể biểu diễn hồ sơ tài nguyên bằng vector:

~~~text
Resource profile =
    (CPU time,
     memory peak,
     logical reads,
     physical bytes,
     write/WAL bytes,
     network bytes,
     connection hold time)
~~~

Không nên cộng trực tiếp các đại lượng khác đơn vị thành một con số nếu chưa có cách quy đổi rõ ràng. Thay vào đó, hãy đặt ngân sách hoặc ngưỡng cho từng tài nguyên và xác định tài nguyên đang giới hạn throughput.

Ví dụ:

| Tài nguyên | Đơn vị theo dõi | Câu hỏi vận hành |
|---|---|---|
| CPU | CPU-seconds/1.000 giao dịch | SQL hoặc biểu thức nào tiêu thụ CPU? |
| Memory | Peak MB, grant, spill | Có thao tác sort/hash vượt ngân sách? |
| Read I/O | MB hoặc pages/1.000 giao dịch | Có scan lặp hoặc cache miss? |
| Write I/O | MB, IOPS, WAL bytes | Ghi log hoặc index maintenance có đắt? |
| Storage latency | ms p95/p99 | Queue hoặc thiết bị lưu trữ có bão hòa? |
| Connections | Active, pending, hold time | Có giữ connection quá lâu? |
| Network | Bytes và round trips | Có truyền quá nhiều hàng hoặc gửi lệnh nhỏ lẻ? |

Một workload có thể bị giới hạn bởi nhiều tài nguyên nối tiếp. Ví dụ query scan nhiều dữ liệu làm tăng I/O; kết quả lớn làm tăng network; sort lớn tạo temp I/O; thời gian dài làm connection bị giữ và gây queue ở ứng dụng.

## 7. Phân loại workload trước khi phân bổ tài nguyên

Không phải mọi truy vấn đều có cùng yêu cầu. Nên phân nhóm:

- **OLTP quan trọng:** thao tác đọc/ghi ngắn, cần latency thấp và độ tin cậy cao.
- **Dashboard tương tác:** đọc nhiều hàng hơn, có yêu cầu phản hồi trong vài giây.
- **Batch import/export:** throughput cao, có thể chạy theo lịch và chia chunk.
- **Báo cáo lịch sử:** scan và aggregate lớn, thường ít nhạy với latency tức thời.
- **Maintenance:** vacuum, index rebuild, backup, statistics và tác vụ quản trị.
- **Background workers:** queue consumer, event processor và tác vụ đồng bộ.

Mỗi nhóm cần ngân sách concurrency, timeout, priority và lịch chạy riêng. Một job backfill không nên chiếm toàn bộ I/O và connection khiến thao tác thanh toán hoặc đặt hàng không đạt SLO.

Có thể tách bằng connection pool, workload group, resource governor, queue hoặc replica tùy hệ quản trị. Cần đo tổng tài nguyên trên database và tác động của các nhóm lên nhau.

## 8. Quy thuộc chi phí cho query và service

Số liệu tổng thể cho biết hệ thống đang chịu tải nhưng không chỉ ra workload nào gây ra tải. Cần liên kết tài nguyên với query fingerprint, application name, tenant hoặc service.

Nên thu thập:

- Query fingerprint hoặc normalized SQL.
- Số lần thực thi.
- Tổng và trung bình execution time.
- CPU time nếu hệ quản trị cung cấp.
- Logical/physical reads.
- Rows returned và rows processed.
- Temp reads/writes hoặc spill.
- Wait events và lock waits.
- Application/service name.
- Tần suất và nhóm tham số đại diện.

Tránh lưu toàn bộ literal nhạy cảm hoặc gắn user ID làm nhãn metric có cardinality rất cao. Dùng fingerprint cho thống kê tổng hợp và trace/log có kiểm soát để điều tra request cụ thể.

### 8.1. Ví dụ PostgreSQL với pg_stat_statements

Nếu extension pg_stat_statements được bật và quyền cho phép, có thể xem các câu SQL tiêu thụ nhiều thời gian:

~~~sql
SELECT
    queryid,
    calls,
    total_exec_time,
    mean_exec_time,
    rows,
    shared_blks_read,
    shared_blks_hit,
    temp_blks_read,
    temp_blks_written,
    left(query, 160) AS query_sample
FROM pg_stat_statements
ORDER BY total_exec_time DESC
LIMIT 20;
~~~

Các trường và đơn vị có thể thay đổi theo phiên bản. Bảng thống kê thường tích lũy từ lần reset gần nhất; hãy ghi nhận thời điểm reset và so sánh các khoảng thời gian tương đương. Tổng thời gian cao có thể do query chạy rất nhiều lần dù mỗi lần nhanh; mean execution time cao có thể chỉ ra query riêng lẻ chậm. Cần xem cả calls, total và phân vị từ hệ thống tracing.

Không dùng riêng total_exec_time để quyết định tối ưu. Hãy cân nhắc số request thành công, mức quan trọng nghiệp vụ, latency tail và tài nguyên khác.

## 9. Xác định bottleneck bằng bằng chứng

Một quy trình chẩn đoán nên tìm tài nguyên đang giới hạn throughput:

**CPU-bound:** CPU cao, runnable queue tăng, thời gian CPU trên query lớn. Xem biểu thức, số hàng, join, aggregate, parallelism và query plan.

**I/O-bound:** storage latency hoặc queue cao, physical reads/writes tăng, query chờ I/O. Xem scan volume, index, cache working set, temp I/O và log flush.

**Lock-bound:** lock wait và blocking chain tăng, CPU có thể thấp. Xem transaction giữ khóa, thứ tự cập nhật và phạm vi transaction.

**Memory-bound:** memory grant wait, spill, swap hoặc áp lực cache. Xem sort/hash, row width, cardinality estimate, concurrency và cấu hình.

**Connection-bound:** active pool đạt giới hạn, pending waiters tăng, acquire latency cao. Xem hold time, leak, transaction và tổng pool trên mọi instance.

**Network-bound:** thời gian truyền kết quả hoặc round trip cao. Xem số hàng trả về, fetch size, chatty query, payload và network latency.

Một chỉ số bất thường chỉ là manh mối. Cần kết hợp thời gian, query fingerprint, execution plan và trace để xác định nguyên nhân.

## 10. Chọn concurrency tối ưu bằng thử nghiệm

Tăng số worker hoặc connection có thể làm throughput tăng cho đến khi tài nguyên bị bão hòa. Sau điểm đó, throughput có thể đi ngang trong khi latency và queue tiếp tục tăng.

Một phép thử nên chạy ở nhiều mức concurrency, chẳng hạn 1, 4, 8, 16, 32 và 64 worker tùy hệ thống. Với mỗi mức, ghi:

- Goodput hoặc giao dịch thành công/giây.
- p50/p95/p99 latency.
- CPU, memory, I/O và network.
- Active/pending connections.
- Lock wait, deadlock và timeout.
- Retry rate.
- Temp I/O và transaction log.
- Thời gian phục hồi khi ngừng tải.

Chọn concurrency gần vùng throughput tốt nhưng vẫn giữ latency trong SLO và còn headroom. Không mặc định mức concurrency cao nhất là tốt nhất.

Dùng workload đại diện: cùng phân bố tham số, tỷ lệ đọc/ghi, kích thước dữ liệu, cache state và transaction mix. Thử cả burst ngắn và tải kéo dài vì hệ thống có thể chịu burst nhưng không chịu được tải liên tục.

## 11. Quản lý headroom và capacity planning

Headroom là năng lực dự phòng để hấp thụ peak, tăng trưởng và sự cố một phần. Không có một tỷ lệ headroom phù hợp cho mọi database; cần dựa trên độ biến động tải, thời gian scale, mục tiêu phục hồi và mức độ quan trọng.

Capacity planning nên xem:

- Peak throughput theo ngày/tuần/mùa vụ.
- Tăng trưởng số hàng và kích thước index.
- Tốc độ tăng CPU, memory và I/O.
- Tốc độ tăng WAL/redo và dung lượng log.
- Tăng số tenant, service instance và background job.
- Tăng kích thước truy vấn hoặc phạm vi báo cáo.
- Thời gian cần để mở rộng storage/compute.
- Tác động khi một replica hoặc node không sẵn sàng.

Một database trung bình dùng 40% CPU nhưng peak hàng ngày đạt 95% có thể không còn headroom đủ. Hãy đánh giá theo cửa sổ peak và p95/p99, không chỉ theo trung bình cả ngày.

Capacity forecast cần có giả định rõ. Nếu throughput tăng 20% mỗi tháng, không thể suy ra CPU hoặc storage cũng tăng đúng 20% nếu query mix, cache và index thay đổi. Định kỳ hiệu chỉnh dự báo bằng số liệu thực tế.

## 12. Scaling: vertical, horizontal và giới hạn của database

**Vertical scaling** tăng CPU, RAM hoặc năng lực storage của một node. Cách này có thể đơn giản và giúp workload tận dụng phần cứng mạnh hơn, nhưng có giới hạn phần cứng, chi phí và thời gian nâng cấp.

**Read scaling** thêm replica để phân phối workload đọc. Cần tính replication lag, consistency, failover và cách định tuyến query. Replica không tự giải quyết write bottleneck trên primary.

**Partitioning/sharding** phân chia dữ liệu hoặc workload để tăng khả năng xử lý, nhưng làm tăng độ phức tạp truy vấn, transaction phân tán, vận hành và cân bằng dữ liệu.

**Caching/precomputation** giảm công việc lặp lại, nhưng thêm freshness lag, storage và logic invalidation.

Trước khi mở rộng hạ tầng, hãy xác định bottleneck. Nếu query đọc quá nhiều hàng do thiếu index hoặc sai cardinality, thêm CPU có thể chỉ làm query lãng phí nhanh hơn. Nếu lock contention là nguyên nhân, tăng RAM không giải quyết được tranh chấp.

## 13. Giảm chi phí truy vấn trước khi tăng tài nguyên

Các thay đổi SQL và data access thường giảm chi phí bền vững hơn:

- Lọc sớm và dùng điều kiện sargable.
- Chỉ chọn các cột cần thiết.
- Dùng index phù hợp với filter, join và order.
- Tránh N+1 query và round trip quá nhỏ.
- Dùng batch cho thao tác ghi phù hợp.
- Giảm fan-out không cần thiết trước aggregate.
- Dùng pagination theo key thay vì OFFSET lớn khi phù hợp.
- Dùng partition pruning cho dữ liệu phân vùng.
- Cập nhật statistics khi phân bố thay đổi.
- Kiểm tra actual rows so với estimated rows.
- Giảm spill bằng cách giảm hàng/row width và điều chỉnh memory có kiểm soát.

Mỗi index bổ sung có chi phí lưu trữ và ghi. Mỗi cache có chi phí refresh và invalidation. Mỗi phép tính precompute có chi phí cập nhật. Đánh giá tổng workload thay vì tối ưu riêng một truy vấn.

## 14. Ngân sách bộ nhớ và memory grant

Bộ nhớ database phục vụ nhiều mục đích: buffer cache, connection/session, sort/hash, plan cache và hoạt động nội bộ. Cấp quá ít cho thao tác có thể gây spill; cấp quá nhiều cho từng query có thể làm hệ thống thiếu RAM khi concurrency tăng.

Cần theo dõi:

- Memory grant requested, granted và used nếu engine cung cấp.
- Sort/hash spill và temp bytes.
- Buffer cache hit cùng physical reads.
- Swap/page fault ở hệ điều hành.
- Memory pressure và grant wait.
- Số query/worker chạy đồng thời.
- Peak memory theo workload.

Không tăng work memory toàn cục chỉ vì một query spill. Trước tiên kiểm tra estimated rows, actual rows, row width, số thao tác sort/hash và số query đồng thời. Giảm dữ liệu trung gian thường làm giảm cả RAM và I/O.

## 15. Ngân sách I/O và storage

I/O cần được đánh giá theo cả lượng dữ liệu và thời gian hoàn tất. Hai database cùng đọc 1 TB có thể có hiệu năng khác nhau do storage throughput, IOPS, queue depth, cache và mẫu truy cập.

Phân biệt:

- Sequential read/write và random read/write.
- Data I/O và temporary I/O.
- Transaction log/WAL/redo flush.
- Checkpoint và background maintenance.
- I/O latency p50/p95/p99.
- Queue depth và throughput.
- Cache hit và working set.

Một truy vấn có logical reads cao nhưng physical reads thấp vẫn tiêu tốn CPU và memory bandwidth. Một truy vấn có ít data reads nhưng spill nhiều có thể tạo temp I/O lớn. Một workload ghi có thể bị giới hạn bởi log flush latency dù data file chưa bão hòa.

Đừng chỉ nhìn IOPS. Hãy đo bytes, latency và queue theo từng loại volume; so sánh với SLO và mẫu truy cập của workload.

## 16. Quản lý chi phí ghi và transaction log

INSERT/UPDATE/DELETE tạo chi phí ngoài câu lệnh SQL:

- Cập nhật index.
- Kiểm tra constraint và foreign key.
- Kích hoạt trigger.
- Ghi WAL/redo/transaction log.
- Đồng bộ log theo chính sách durability.
- Replicate thay đổi đến standby.
- VACUUM hoặc maintenance về sau.

Một bảng có nhiều index có thể làm SELECT nhanh hơn nhưng tăng CPU, I/O và log cho mỗi lần ghi. Batch có thể giảm round trip nhưng transaction quá lớn làm log tăng, lock giữ lâu và rollback tốn kém.

Đo write amplification: lượng byte ghi vào storage hoặc log so với lượng dữ liệu nghiệp vụ thay đổi. Nếu một hàng nghiệp vụ nhỏ tạo nhiều page/index/log write, hãy xem lại index, fillfactor, update pattern và thiết kế dữ liệu.

Không tắt durability hoặc constraint chỉ để tăng benchmark nếu production cần các bảo đảm đó. Benchmark phải giữ cùng semantics về commit, replication và tính toàn vẹn.

## 17. Giới hạn concurrency và admission control

Admission control quyết định bao nhiêu công việc được phép bắt đầu tại một thời điểm. Khi hệ thống gần bão hòa, từ chối hoặc trì hoãn một phần công việc có thể bảo vệ latency cho workload quan trọng.

Các cơ chế:

- Semaphore giới hạn số query đồng thời ở ứng dụng.
- Connection pool giới hạn số connection.
- Queue hữu hạn giới hạn số request đang chờ.
- Workload group phân bổ CPU/memory hoặc priority.
- Rate limit giới hạn request theo service/tenant.
- Bulkhead tách tài nguyên của workload khác nhau.
- Load shedding từ chối công việc ít ưu tiên khi quá tải.

Queue không nên không giới hạn. Hàng đợi dài giữ request, thread và memory; khi hệ thống hồi phục, toàn bộ request có thể dồn vào database tạo peak thứ hai. Timeout và deadline phải được truyền qua các tầng.

## 18. Retry làm tăng chi phí tài nguyên

Retry có thể cần thiết cho lỗi tạm thời, nhưng retry không kiểm soát làm tăng số lần thực thi trên mỗi request nghiệp vụ.

Theo dõi:

~~~text
Retry amplification =
    số lần thực thi thực tế / số request nghiệp vụ ban đầu
~~~

Nếu một request trung bình được thực thi 1,4 lần, hệ thống đang tiêu thụ nhiều hơn 40% công việc so với số request ban đầu. Trong thời điểm lỗi, tỷ lệ này có thể tăng nhanh.

Retry cần:

- Phân loại lỗi transient và permanent.
- Giới hạn số lần thử và tổng thời gian.
- Exponential backoff cùng jitter.
- Retry budget ở cấp request hoặc service.
- Idempotency cho thao tác có thể được gửi lại.
- Circuit breaker và load shedding khi dependency quá tải.

Không retry lỗi constraint, syntax hoặc dữ liệu không hợp lệ. Khi timeout xảy ra sau khi gửi COMMIT, trạng thái commit có thể không rõ; cần đối soát bằng khóa idempotency hoặc trạng thái nghiệp vụ trước khi gửi lại.

## 19. Đặt ngân sách cho từng nhóm workload

Một mô hình vận hành hữu ích là xác định ngân sách cho từng nhóm:

| Nhóm workload | Concurrency | Latency | Resource budget | Chính sách |
|---|---:|---|---|---|
| Giao dịch quan trọng | Giới hạn ổn định | p95/p99 nghiêm ngặt | Ưu tiên CPU/connection | Không để batch chiếm tài nguyên |
| Dashboard | Giới hạn theo người dùng | Vài giây | Read I/O và memory | Cache hoặc precompute |
| Batch import | Worker có giới hạn | Theo thời hạn job | Write I/O và log | Chia chunk, retry an toàn |
| Báo cáo lịch sử | Thấp hoặc theo lịch | Có thể dài hơn | Scan/CPU lớn | Replica hoặc analytical store |
| Maintenance | Theo cửa sổ | Theo tiến độ | I/O và CPU có kiểm soát | Theo dõi tác động OLTP |

Các ngân sách không nhất thiết là hard limit ngay từ đầu. Có thể bắt đầu bằng mục tiêu quan sát, sau đó đặt giới hạn concurrency và admission control khi đã hiểu tải. Nếu hệ quản trị có resource governor/workload management, cần kiểm tra semantics và tác động trên phiên bản cụ thể.

## 20. Benchmark theo nhiều mức tải

Một benchmark chỉ chạy một mức concurrency có thể bỏ qua điểm bão hòa. Hãy thử:

1. **Baseline tải thấp:** xác định latency và resource cost khi không có cạnh tranh.
2. **Tăng tải từng bước:** đo throughput, p95/p99 và queue theo mỗi mức concurrency.
3. **Tải mục tiêu:** chạy workload mix đại diện ở mức production dự kiến.
4. **Peak/burst:** mô phỏng đợt tăng đột ngột.
5. **Sustained load:** giữ tải đủ lâu để lộ checkpoint, vacuum, cache eviction và log pressure.
6. **Soak test:** kiểm tra rò rỉ connection, tăng bộ nhớ và xu hướng queue.
7. **Recovery test:** giảm tải hoặc dừng generator, đo thời gian hàng đợi và latency trở về bình thường.

Giữ nguyên dataset, query mix, tham số, cache state, index và cấu hình transaction giữa các lần so sánh. Warm-up trước khi ghi số liệu; ghi rõ có tính thời gian warm-up hay không.

Dùng open-loop generator khi cần mô phỏng tốc độ request đến độc lập với latency. Dùng closed-loop khi muốn mô phỏng số client đồng thời cố định. Cả hai có thể cho kết quả khác nhau; chọn mô hình gần với hành vi production và tránh coordinated omission làm đánh giá thấp latency.

## 21. Ví dụ: throughput tăng nhưng latency và chi phí xấu đi

Giả sử một API đọc/ghi đơn hàng được benchmark ở ba mức concurrency:

| Concurrency | Goodput | p95 latency | CPU | CPU ms/giao dịch |
|---:|---:|---:|---:|---:|
| 16 | 600 TPS | 90 ms | 45% | 1,2 |
| 32 | 900 TPS | 160 ms | 72% | 1,6 |
| 64 | 940 TPS | 850 ms | 96% | 2,7 |

Ở concurrency 64, goodput chỉ tăng khoảng 4,4% so với 32, nhưng p95 tăng hơn 5 lần và CPU cost mỗi giao dịch tăng đáng kể. Hệ thống đang gần bão hòa CPU; queue và latency tăng nhanh.

Nếu mục tiêu là p95 dưới 250 ms, concurrency 32 phù hợp hơn. Có thể thử tối ưu query hoặc giảm CPU cost để tăng goodput trong cùng SLO, thay vì tiếp tục tăng concurrency.

Đây là số liệu giả định để minh họa cách đọc kết quả. Trong thực tế cần đo thêm p99, lỗi, lock wait, I/O, memory, retry và workload khác.

## 22. Quy trình quản lý chi phí tài nguyên

Một quy trình có thể áp dụng:

1. **Xác định đơn vị công việc:** request, transaction, query, batch hoặc sự kiện hoàn tất.
2. **Định nghĩa SLO:** throughput, p95/p99, error rate và điều kiện tải.
3. **Đo baseline:** CPU, memory, I/O, log, network, connections và storage.
4. **Quy thuộc chi phí:** query fingerprint, service, tenant và nhóm workload.
5. **Tìm bottleneck:** CPU, memory, I/O, lock, connection hay network.
6. **Đo concurrency curve:** tìm điểm throughput bão hòa và latency bắt đầu tăng mạnh.
7. **Đặt ngân sách:** resource cost trên mỗi đơn vị công việc và headroom.
8. **Tối ưu truy vấn trước:** SQL, index, statistics, row width và round trips.
9. **Giới hạn tải:** pool, queue, worker, rate limit và workload priority.
10. **Đánh giá scaling:** vertical, replica, partitioning, cache hoặc precompute theo bottleneck.
11. **Benchmark lại:** cùng dữ liệu, query mix, cache và semantics transaction.
12. **Theo dõi production:** cảnh báo theo SLO, queue, retry, resource saturation và cost per transaction.
13. **Cập nhật capacity forecast:** dùng tăng trưởng thực tế và mùa vụ để điều chỉnh ngân sách.

Mọi thay đổi cần có giả thuyết rõ: tài nguyên nào sẽ giảm, throughput hoặc latency nào sẽ cải thiện và tác động phụ nào cần theo dõi.

## 23. Những sai lầm thường gặp

- **Tối ưu throughput mà bỏ qua p95/p99.** Hệ thống có thể xử lý nhiều hơn nhưng người dùng phải chờ lâu hơn.
- **Chỉ nhìn CPU trung bình.** Một pool, disk hoặc lock manager có thể bão hòa khi CPU còn thấp.
- **Tăng pool hoặc worker không giới hạn.** Concurrency quá cao có thể làm queue và contention tăng.
- **Đồng nhất request rate với goodput.** Timeout và retry có thể làm request rate cao nhưng công việc hữu ích thấp.
- **Chỉ xem chi phí ở cấp database.** Cần quy thuộc đến query, service và workload.
- **Cộng các tài nguyên khác đơn vị thành một con số tùy ý.** CPU, byte và memory cần ngân sách riêng hoặc cách quy đổi có căn cứ.
- **Benchmark với dữ liệu nhỏ hoặc cache nóng duy nhất.** Không đại diện cho production.
- **Bỏ qua write amplification.** Index và log có thể làm chi phí ghi tăng nhiều.
- **Scale trước khi tìm bottleneck.** Thêm CPU không sửa lock contention hoặc SQL đọc quá nhiều hàng.
- **Không dành headroom.** Peak hoặc node failure có thể làm hệ thống vượt SLO.
- **Chạy batch cùng ưu tiên với OLTP.** Báo cáo hoặc backfill có thể chiếm I/O và connection.
- **Không đo thời gian phục hồi.** Queue có thể tiếp tục gây tải sau khi sự cố ban đầu đã hết.

## 24. Checklist vận hành throughput, latency và resource cost

- [ ] Đã định nghĩa goodput và đơn vị công việc hoàn tất.
- [ ] Đã đặt SLO cho throughput, p95/p99 và error rate.
- [ ] Đã đo queue time, connection wait, SQL time và transaction duration.
- [ ] Đã theo dõi CPU, memory, read/write I/O, log, network và storage.
- [ ] Đã tính resource cost trên mỗi giao dịch hoặc request thành công.
- [ ] Đã theo dõi retry amplification và request bị hủy.
- [ ] Đã quy thuộc chi phí cho query fingerprint, service và workload.
- [ ] Đã phân biệt utilization với saturation và queueing.
- [ ] Đã đo concurrency curve và điểm bão hòa.
- [ ] Đã đặt ngân sách connection, worker, queue và resource theo nhóm workload.
- [ ] Đã dự phòng headroom cho peak, autoscaling và sự cố một phần.
- [ ] Đã đánh giá scaling theo bottleneck thực tế.
- [ ] Đã kiểm tra SQL, index, statistics, spill và write amplification.
- [ ] Đã benchmark với dữ liệu, cache và query mix đại diện.
- [ ] Đã đo p95/p99, goodput và chi phí sau điều chỉnh.
- [ ] Đã theo dõi thời gian phục hồi và xu hướng capacity.

## 25. Nguyên tắc cần ghi nhớ

Quản lý chi phí tài nguyên theo throughput và mục tiêu độ trễ là bài toán cân bằng năng lực xử lý, thời gian chờ và mức tài nguyên trên mỗi công việc hoàn tất. Tăng concurrency có thể tăng goodput đến một điểm; khi tài nguyên bão hòa, queue và p95/p99 tăng nhanh trong khi throughput gần như không đổi. CPU, memory, I/O, log, network, connection và lock cần được quan sát cùng nhau.

Hãy định nghĩa SLO trước, đo goodput thay vì chỉ request rate, quy thuộc chi phí cho query và workload, tìm bottleneck bằng execution plan cùng wait metrics, rồi chọn concurrency và headroom phù hợp. Tối ưu SQL và đường truy cập trước khi mở rộng tài nguyên; dùng admission control, queue hữu hạn và retry có ngân sách để bảo vệ hệ thống. Sau mỗi điều chỉnh, benchmark trên workload đại diện và xác nhận throughput, p95/p99, error rate cùng resource cost trên mỗi giao dịch.
