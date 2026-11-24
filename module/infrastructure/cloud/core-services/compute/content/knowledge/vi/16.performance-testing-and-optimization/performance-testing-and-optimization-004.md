# Phân biệt nút thắt CPU, bộ nhớ, I/O và dịch vụ phụ thuộc

Khi một ứng dụng trên cloud chạy chậm, tăng số vCPU hoặc RAM ngay lập tức không phải lúc nào cũng giải quyết được vấn đề. Ứng dụng có thể đang chờ đĩa, chờ database, bị giới hạn bởi connection pool, bị CPU throttling hoặc phải xử lý quá nhiều dữ liệu trong bộ nhớ. Muốn tối ưu đúng, cần xác định thành phần nào đang giới hạn throughput hoặc làm tăng latency.

Bài học này tập trung vào bốn nhóm nút thắt thường gặp: **CPU-bound**, **memory-bound**, **I/O-bound** và **dependency-bound**. Đây là cách phân loại theo tài nguyên hoặc thành phần đang giới hạn công việc. Một request thực tế có thể đi qua nhiều trạng thái: xử lý CPU, chờ RAM/cache, đọc đĩa, gọi database rồi quay lại CPU. Vì vậy, cần kết hợp metric, profiling và thử nghiệm có kiểm soát để tìm nguyên nhân chính.

Sau bài học, bạn có thể:

- Nhận diện dấu hiệu của nút thắt CPU, bộ nhớ, I/O và dịch vụ phụ thuộc.
- Chọn metric phù hợp ở cấp ứng dụng, process, VM, container và cloud service.
- Đọc CPU utilization, run queue, memory pressure, page fault, I/O latency, queue depth và dependency latency.
- Dùng profiling, tracing và công cụ hệ điều hành để kiểm chứng giả thuyết.
- Thiết kế benchmark và thử nghiệm thay đổi từng yếu tố để xác nhận hiệu quả.
- Chọn biện pháp tối ưu phù hợp, tránh scale tài nguyên sai hướng hoặc làm tăng chi phí mà không cải thiện SLO.

## 1. Nút thắt hiệu năng là gì?

Nút thắt (bottleneck) là tài nguyên hoặc thành phần giới hạn tốc độ xử lý của hệ thống tại một thời điểm. Khi thành phần đó đạt giới hạn, tăng tải thường làm hàng đợi dài hơn, latency tăng hoặc request thất bại. Các thành phần khác có thể vẫn còn dư năng lực.

Ví dụ:

- Một tiến trình nén ảnh dùng gần hết CPU; thêm vCPU có thể tăng throughput nếu ứng dụng chạy song song tốt.
- Một JVM liên tục garbage collection và working set lớn hơn RAM khả dụng; thêm RAM hoặc giảm allocation có thể cải thiện.
- Một API ghi dữ liệu vào volume có I/O latency cao; thêm CPU thường không giúp.
- Một API chờ database hoặc dịch vụ thanh toán; tăng CPU của API không làm dependency phản hồi nhanh hơn.

Cần phân biệt **utilization** với **saturation**:

- Utilization cho biết tài nguyên đang được sử dụng bao nhiêu phần trăm trong một khoảng đo.
- Saturation cho biết nhu cầu đang vượt hoặc tiến gần năng lực phục vụ, thường thể hiện qua hàng đợi, thời gian chờ, throttling hoặc pressure.

CPU 90% có thể là sử dụng hiệu quả nếu latency vẫn tốt và còn headroom. Ngược lại, CPU tổng thể 30% vẫn có thể có một core hoặc một thread bị bão hòa, khiến request tuần tự bị chậm.

### Mô hình quan sát USE và RED

Hai cách nhìn bổ sung nhau:

- **USE** (Utilization, Saturation, Errors) phù hợp để kiểm tra tài nguyên: CPU, RAM, disk, network và queue.
- **RED** (Rate, Errors, Duration) phù hợp để quan sát dịch vụ: tốc độ request, tỷ lệ lỗi và thời gian xử lý.

Kết hợp hai mô hình giúp nối triệu chứng người dùng với giới hạn hạ tầng.

## 2. Luồng xử lý và vị trí có thể phát sinh chờ

Một request thường đi qua nhiều lớp. Ví dụ API nhận request, kiểm tra quyền, truy vấn cache, đọc database, gọi một dịch vụ khác rồi trả response.

    Client
      |
      v
    Load balancer / ingress
      |
      v
    Application process
      |-- CPU: parse, validate, compute, serialize
      |-- Memory: heap, cache, object allocation
      |-- Local/remote I/O: file, volume, socket
      |-- Dependency: database, queue, external API
      |
      v
    Response

Tổng latency có thể gồm thời gian xử lý CPU, thời gian chờ thread/connection pool, thời gian chờ I/O và thời gian chờ dịch vụ phụ thuộc. Một thread đang chờ database không tiêu thụ nhiều CPU; do đó CPU thấp không chứng minh ứng dụng còn khỏe.

Nên xác định ranh giới đo ở từng bước:

- Client-side latency: tổng thời gian người dùng quan sát.
- Server-side latency: thời gian từ khi request vào server đến khi response rời server.
- Queue wait: thời gian request/job chờ được xử lý.
- Application processing: thời gian trong logic ứng dụng.
- Dependency latency: thời gian chờ database, cache, queue hoặc API khác.

Distributed trace có thể phân tách các khoảng thời gian này thành span. Nếu chưa có tracing, metric theo dependency và log có correlation ID vẫn giúp khoanh vùng.

## 3. Dấu hiệu của nút thắt CPU-bound

CPU-bound xảy ra khi công việc cần nhiều chu kỳ xử lý hơn năng lực CPU hiện có. Các ví dụ thường gặp gồm mã hóa/giải mã, nén, xử lý ảnh/video, tính toán số, phân tích dữ liệu, serialization nặng và thuật toán có độ phức tạp cao.

### Dấu hiệu thường thấy

- CPU utilization cao kéo dài trên các core được workload sử dụng.
- Run queue hoặc CPU pressure tăng; tiến trình phải chờ được scheduler cấp CPU.
- Throughput không tăng tương ứng khi tải tăng; latency tăng.
- CPU profile cho thấy một số hàm chiếm phần lớn thời gian.
- Với container, CPU throttling tăng khi chạm quota/limit.
- Với VM trên môi trường chia sẻ, CPU steal hoặc dấu hiệu contention có thể tăng.
- Một thread đơn lẻ có thể bão hòa một core trong khi CPU tổng thể còn thấp.

CPU utilization cao không tự động có nghĩa phải tăng vCPU. Nếu một request chỉ chạy trên một thread, tăng từ 4 lên 16 vCPU có thể không cải thiện latency của request đó. Nếu bottleneck nằm ở lock hoặc serialization tuần tự, thêm core thậm chí làm tăng contention.

### Metric nên xem

| Metric | Ý nghĩa | Cách diễn giải |
|---|---|---|
| CPU utilization per core | Mức sử dụng từng core | Phát hiện một core bị bão hòa dù trung bình thấp |
| CPU usage per process/container | CPU workload thực sự dùng | Xác định process hoặc container tiêu thụ nhiều CPU |
| Run queue / load average | Nhu cầu chờ CPU và công việc runnable | Đọc cùng số vCPU và loại workload; load average cũng có thể tính cả task ở trạng thái uninterruptible tùy hệ điều hành |
| CPU pressure | Thời gian task bị chậm do thiếu CPU | Giúp nhận diện contention trên Linux hỗ trợ PSI |
| CPU throttling | Thời gian hoặc chu kỳ bị giới hạn bởi quota | Throttling cao có thể làm tăng latency dù node còn CPU |
| CPU steal | Thời gian VM không được host cấp CPU như mong muốn | Có thể gợi ý contention trên host ảo hóa |
| Context switches | Chuyển đổi giữa các task | Tăng bất thường có thể liên quan quá nhiều thread hoặc scheduling overhead |

### Phân biệt CPU-bound với lock-bound

Một ứng dụng có thể có CPU thấp nhưng thread liên tục chờ lock. Khi đó tăng vCPU thường không giải quyết. Thread dump, lock profiling hoặc trace contention có thể cho thấy nhiều thread đang chờ cùng một mutex, monitor hoặc critical section.

### Hướng tối ưu

1. Profile CPU để tìm hàm nóng (hot path), thay vì đoán theo tên service.
2. Giảm thuật toán có độ phức tạp cao, công việc lặp và thao tác serialize không cần thiết.
3. Giảm allocation và copy dữ liệu nếu chúng làm tăng GC hoặc memory bandwidth.
4. Tối ưu mức song song; tránh tạo quá nhiều thread và context switch.
5. Kiểm tra lock contention, thread pool và giới hạn concurrency.
6. Với container, điều chỉnh CPU request/limit dựa trên tải và latency mục tiêu.
7. Nếu công việc thực sự CPU-bound và có thể song song, thử instance có nhiều vCPU hoặc CPU nhanh hơn rồi benchmark lại.

## 4. Dấu hiệu của nút thắt memory-bound

Memory-bound có thể chỉ việc ứng dụng thiếu dung lượng RAM, hoặc bị giới hạn bởi tốc độ truy cập bộ nhớ. Hai trường hợp có biểu hiện khác nhau.

### Memory capacity pressure

Khi working set của ứng dụng vượt RAM khả dụng, hệ điều hành phải thu hồi page cache, swap hoặc kích hoạt OOM killer. Ứng dụng có thể chậm do page fault, GC hoặc liên tục nạp dữ liệu trở lại.

Dấu hiệu:

- Available memory giảm liên tục.
- Swap-in/swap-out hoặc major page fault tăng.
- Memory pressure tăng; process bị OOM kill.
- Container restart với trạng thái OOMKilled.
- Heap hoặc resident set size (RSS) tăng bất thường.
- Garbage collection chạy thường xuyên, pause dài hoặc allocation rate cao.
- Latency tăng theo thời gian khi cache hoặc heap phình ra.

### Memory bandwidth hoặc access latency

Một workload có thể không thiếu RAM nhưng liên tục đọc/ghi lượng dữ liệu lớn, ví dụ xử lý ma trận, phân tích dữ liệu hoặc quét cấu trúc dữ liệu lớn. Khi đó giới hạn có thể nằm ở memory bandwidth, cache miss hoặc NUMA locality.

Dấu hiệu này thường cần profiler phần cứng, performance counter hoặc công cụ chuyên sâu. Chỉ nhìn phần trăm RAM đã dùng không đủ để xác định.

### Metric nên xem

| Metric | Ý nghĩa | Lưu ý |
|---|---|---|
| Available memory | RAM có thể cấp cho workload mà không gây áp lực lớn | Thường hữu ích hơn chỉ nhìn free memory |
| RSS / working set | Bộ nhớ vật lý tiến trình hoặc container đang dùng | Phân biệt shared memory và memory cache theo công cụ |
| Heap used/committed | Bộ nhớ heap của runtime | Với JVM cần xem cùng GC và native memory |
| Allocation rate | Tốc độ tạo object | Allocation cao có thể gây GC nhiều |
| GC pause / frequency | Thời gian và tần suất garbage collection | Pause dài có thể trực tiếp tăng tail latency |
| Page faults | Lỗi trang khi truy cập bộ nhớ | Major page fault có thể cần đọc từ storage |
| Swap activity | Hoạt động chuyển trang ra/vào swap | Swap-in/out cao thường là dấu hiệu pressure |
| OOM events | Sự kiện hết bộ nhớ | Kiểm tra limit container và node, không chỉ RAM VM |

### Hướng tối ưu

- Xác định memory leak hoặc object giữ tham chiếu quá lâu.
- Giảm allocation, copy và dữ liệu trung gian; dùng streaming khi phù hợp.
- Điều chỉnh cache size và eviction policy; cache quá lớn có thể làm tăng GC hoặc pressure.
- Tối ưu heap/runtime dựa trên profile và GC log; không tăng heap tùy tiện nếu native memory hoặc container limit là nguyên nhân.
- Cấp memory limit đủ cho cả heap, metaspace, thread stack, direct buffer và native allocation.
- Với workload có working set lớn, cân nhắc RAM nhiều hơn hoặc chia dữ liệu thành partition.
- Kiểm tra NUMA placement và memory bandwidth khi workload nhạy với kiến trúc phần cứng.

## 5. Dấu hiệu của nút thắt I/O-bound

I/O-bound xảy ra khi tiến trình dành nhiều thời gian chờ đọc/ghi dữ liệu hoặc truyền dữ liệu qua network. I/O có thể là block storage, file system, object storage, network filesystem, socket hoặc thiết bị khác.

### Storage I/O

Dấu hiệu thường gặp:

- CPU không cao nhưng request latency tăng.
- Disk read/write latency tăng.
- IOPS hoặc throughput chạm giới hạn của volume/instance.
- I/O queue depth tăng; tiến trình chờ I/O lâu.
- Filesystem gần đầy hoặc inode cạn.
- Một số tác vụ đọc/ghi nhỏ ngẫu nhiên chậm hơn tác vụ tuần tự.

Phân biệt ba đại lượng:

- **IOPS:** số thao tác đọc/ghi mỗi giây.
- **Throughput:** lượng dữ liệu truyền mỗi giây, thường tính MiB/s hoặc MB/s.
- **Latency:** thời gian hoàn thành một thao tác I/O.

Volume có thể chạm giới hạn IOPS khi thực hiện nhiều thao tác nhỏ, hoặc chạm throughput khi truyền các block lớn. Tăng kích thước volume đôi khi tăng giới hạn hiệu năng ở một số dịch vụ, nhưng quy tắc này phụ thuộc provider và loại volume.

### Network I/O

Dấu hiệu thường gặp:

- Network throughput gần giới hạn NIC hoặc instance.
- Packet drop, retransmission hoặc RTT tăng.
- Socket ở trạng thái chờ, connection establishment chậm.
- DNS lookup hoặc TLS handshake chiếm thời gian lớn.
- Cross-zone/region traffic có latency hoặc chi phí cao.
- NAT gateway, load balancer hoặc connection tracking chạm quota.

### Metric nên xem

| Metric | Ý nghĩa | Dấu hiệu cần chú ý |
|---|---|---|
| Read/write IOPS | Số thao tác I/O mỗi giây | Chạm giới hạn được cấp |
| Read/write throughput | Dữ liệu đọc/ghi mỗi giây | Bão hòa băng thông volume |
| I/O latency | Thời gian hoàn thành thao tác | Tăng cùng queue depth |
| Queue depth | Số yêu cầu đang chờ hoặc xử lý | Tăng kéo dài cho thấy thiết bị không theo kịp |
| Disk utilization | Thời gian thiết bị bận theo cách exporter định nghĩa | Không phải lúc nào cũng tương đương mức bão hòa của storage cloud |
| Network throughput | Byte/bit truyền mỗi giây | So với giới hạn NIC/instance |
| Retransmission/drop | Gói tin truyền lại hoặc bị mất | Có thể làm tăng latency và giảm throughput |
| Connection count | Số socket/kết nối đang mở | Phát hiện cạn connection hoặc quá nhiều kết nối ngắn |

### Hướng tối ưu

- Dùng batch để giảm số I/O nhỏ; chọn kích thước block phù hợp.
- Cache dữ liệu đọc thường xuyên nếu tính nhất quán cho phép.
- Tối ưu query và index để giảm lượng dữ liệu đọc từ storage.
- Dùng persistent volume có IOPS/throughput phù hợp; kiểm tra giới hạn ở cả volume và instance.
- Tách log, scratch data và dữ liệu nghiệp vụ theo nhu cầu I/O.
- Dùng async I/O hoặc pipeline khi có thể xử lý song song mà không làm tăng tải quá mức.
- Với network, tái sử dụng connection, dùng keep-alive, giảm payload và tránh truyền dữ liệu không cần thiết.
- Kiểm tra MTU, DNS, route, packet loss, NAT và giới hạn băng thông trước khi thay đổi instance.

## 6. Dấu hiệu của nút thắt dịch vụ phụ thuộc (dependency-bound)

Dependency-bound xảy ra khi ứng dụng phải chờ một dịch vụ khác hoàn tất công việc. Dependency có thể là database, cache, message broker, object storage, API bên thứ ba, identity provider hoặc dịch vụ cloud control/data plane.

Ví dụ: API nhận request trong 20 ms nhưng mất 800 ms chờ database; CPU của API chỉ 15%. Tăng vCPU của API hầu như không thay đổi thời gian truy vấn.

### Dấu hiệu thường gặp

- Application latency cao nhưng CPU và memory của ứng dụng còn thấp.
- Trace cho thấy một span dependency chiếm phần lớn tổng thời gian.
- Connection pool cạn hoặc request phải chờ lấy connection.
- Database query latency, lock wait hoặc replication lag tăng.
- Queue depth và tuổi message tăng vì consumer xử lý chậm.
- External API trả lỗi, timeout hoặc rate limit.
- Retry rate tăng, làm số request đến dependency cao hơn số request người dùng.
- Một dependency có lỗi làm nhiều service downstream đồng thời chậm.

### Phân biệt thời gian chờ connection pool và thời gian query

Một request gọi database có thể chờ ở nhiều nơi:

1. Chờ lấy connection từ pool.
2. Thiết lập TCP/TLS hoặc xác thực nếu tạo kết nối mới.
3. Chờ database nhận và lập lịch query.
4. Query thực thi, chờ lock hoặc I/O.
5. Truyền kết quả về ứng dụng.
6. Ứng dụng deserialize và xử lý kết quả.

Nếu chỉ đo tổng database call duration, khó biết phần nào là nguyên nhân. Instrument riêng pool acquisition, connect time, query execution và result processing khi framework hỗ trợ.

### Metric nên xem

| Dependency | Metric quan trọng |
|---|---|
| Database | Query latency, active connections, pool wait, lock wait, slow query, CPU, I/O, replication lag |
| Cache | Hit ratio, miss rate, command latency, evictions, memory, connection count |
| Message broker | Queue depth, oldest message age, publish/consume rate, consumer lag, retry, dead-letter |
| External API | Request rate, latency percentile, timeout, error rate, 429/rate limit, retry |
| Object storage | Request latency, throughput, throttling, 4xx/5xx, request quota |
| Identity/secrets service | Token/secret retrieval latency, throttling, failure rate, cache hit |

### Hướng tối ưu

- Tối ưu query, index, transaction scope và lock contention ở database.
- Điều chỉnh connection pool theo giới hạn database; pool quá lớn có thể làm database quá tải.
- Cache kết quả phù hợp với yêu cầu nhất quán và thời hạn dữ liệu.
- Dùng queue để tách workload đồng bộ khỏi công việc nền, nhưng theo dõi queue age và consumer lag.
- Đặt timeout theo ngân sách latency end-to-end.
- Retry có giới hạn, exponential backoff và jitter; không retry lỗi vĩnh viễn hoặc mọi mã lỗi.
- Dùng circuit breaker hoặc bulkhead để ngăn dependency lỗi làm cạn thread/connection của toàn ứng dụng.
- Đàm phán quota/SLA hoặc dùng phương án fallback cho dịch vụ bên ngoài quan trọng.
- Giảm fan-out request; một request gọi nhiều dependency song song có thể có latency bị chi phối bởi dependency chậm nhất.

## 7. So sánh bốn nhóm nút thắt

| Nhóm | CPU | Memory | I/O | Dependency | Bằng chứng nổi bật |
|---|---|---|---|---|---|
| CPU-bound | Cao hoặc một core bão hòa | Có thể bình thường | Không phải phần chờ chính | Không chiếm phần lớn latency | CPU profile, run queue, throttling |
| Memory-bound | Có thể thấp hoặc tăng do GC | Pressure, page fault, OOM hoặc bandwidth limit | Có thể tăng do swap/page-in | Thường không phải nguyên nhân đầu tiên | Working set, GC, swap, memory pressure |
| I/O-bound | Thường thấp khi chờ | Có thể bình thường | Latency/queue/throughput chạm giới hạn | Có thể gồm network service | iostat, volume metrics, retransmission |
| Dependency-bound | Thường thấp trong thời gian chờ | Thường bình thường | Có thể thấp ở máy gọi | Latency, pool wait, queue hoặc lỗi dịch vụ đích cao | Distributed trace, dependency metrics |

Các nhóm không loại trừ lẫn nhau. Ví dụ, database chậm do I/O có thể khiến API trở thành dependency-bound; database là I/O-bound ở phía bên trong. Hãy phân loại theo góc nhìn của thành phần đang điều tra, sau đó đi sâu vào dependency.

## 8. Quy trình chẩn đoán có hệ thống

Không bắt đầu bằng việc thay đổi instance size. Hãy đi theo trình tự từ triệu chứng đến bằng chứng.

### Bước 1: xác định tác động

- Route hoặc workload nào bị ảnh hưởng?
- Bắt đầu từ thời điểm nào và có trùng deployment, maintenance hoặc thay đổi cấu hình không?
- Latency p50/p95/p99, error rate và throughput thay đổi ra sao?
- Ảnh hưởng toàn fleet hay chỉ một instance, zone hoặc tenant?
- SLO/error budget có bị vi phạm không?

### Bước 2: xác nhận dữ liệu đo

- Metric có liên tục và đúng đơn vị không?
- Có khoảng trống telemetry hoặc thay đổi label không?
- Request retry có bị đếm trùng không?
- Client latency và server latency có đang bị trộn không?
- Có đủ dữ liệu trước và sau thời điểm sự cố để so sánh không?

### Bước 3: tìm đoạn thời gian chiếm nhiều nhất

Dùng trace hoặc instrumentation để chia latency thành queue wait, application processing và dependency calls. Nếu không có trace, thêm metric theo từng bước hoặc log duration có correlation ID.

### Bước 4: kiểm tra saturation ở từng lớp

- CPU: per-core, run queue, throttling, steal, pressure.
- Memory: available, working set, GC, page fault, swap, OOM.
- Storage: IOPS, throughput, latency, queue depth, filesystem.
- Network: throughput, drops, retransmission, RTT, connection count.
- Dependency: query latency, pool wait, queue age, timeout và quota.

### Bước 5: hình thành giả thuyết có thể bác bỏ

Ví dụ: “p99 tăng do API chờ connection pool” là giả thuyết có thể kiểm tra bằng pool wait duration, active/pending connections và trace. “VM thiếu CPU” là giả thuyết cần được hỗ trợ bởi CPU pressure, run queue, profile hoặc throttling.

Mỗi giả thuyết cần nêu:

- Metric nào phải tăng hoặc giảm nếu giả thuyết đúng?
- Log/trace/profile nào có thể xác nhận?
- Thay đổi thử nghiệm nhỏ nhất là gì?
- Điều kiện nào chứng minh giả thuyết sai?

### Bước 6: thử một thay đổi có kiểm soát

Thay đổi một yếu tố mỗi lần nếu có thể: thêm vCPU, tăng memory limit, thay loại volume, giảm query, điều chỉnh pool hoặc cache. So sánh cùng workload và cửa sổ đo. Tránh thay đồng thời CPU, RAM, volume và concurrency vì sẽ không biết yếu tố nào tạo kết quả.

### Bước 7: xác minh và ghi nhận

Đo lại throughput, latency percentile, error rate, saturation và chi phí. Nếu không cải thiện hoặc một chỉ số khác xấu đi, rollback và xem lại giả thuyết.

## 9. Công cụ quan sát và profiling trên Linux

Các lệnh sau giúp kiểm tra nhanh trên VM Linux. Tên tùy chọn và mức chi tiết có thể khác theo bản phân phối; một số công cụ cần cài package hoặc quyền phù hợp.

### CPU và tiến trình

    # Tổng quan tiến trình và CPU
    top

    # CPU, run queue, memory, swap và I/O theo chu kỳ
    vmstat 1

    # CPU usage theo từng core
    mpstat -P ALL 1

    # CPU và I/O theo tiến trình
    pidstat -u -d 1

Dùng top hoặc pidstat để xác định process; mpstat để xem có core nào bị bão hòa; vmstat để quan sát run queue, swap và I/O wait. Load average cần được diễn giải theo số CPU và loại task đang chạy.

### Memory

    # Tổng quan RAM và swap
    free -h

    # Thông tin paging và memory pressure
    vmstat 1

    # Xem cgroup memory hiện tại nếu hệ thống dùng cgroup v2
    cat /sys/fs/cgroup/memory.current
    cat /sys/fs/cgroup/memory.max

Đường dẫn cgroup có thể khác khi process nằm trong một cgroup con hoặc dùng cgroup v1. Với container, ưu tiên số liệu của runtime/orchestrator và đối chiếu với node.

### Storage I/O

    # I/O theo thiết bị
    iostat -xz 1

    # I/O theo tiến trình
    pidstat -d 1

    # Dung lượng filesystem và inode
    df -h
    df -i

Đọc await, aqu-sz, throughput và IOPS theo thiết bị. %util là thời gian thiết bị bận theo cách exporter báo; với storage cloud hoặc thiết bị song song, không nên dùng một mình để kết luận đã bão hòa.

### Network

    # Socket và trạng thái kết nối
    ss -s
    ss -tan

    # Thống kê giao diện
    ip -s link

    # Kiểm tra độ trễ kết nối TCP/HTTPS
    curl -sS -o /dev/null -w 'connect=%{time_connect} tls=%{time_appconnect} starttransfer=%{time_starttransfer} total=%{time_total}\n' https://service.example

Kết quả curl cần được diễn giải theo DNS, proxy, TLS và endpoint cụ thể. Không chạy benchmark mạng hoặc tải lớn trên production nếu chưa có kế hoạch và giới hạn.

### Profiling

- CPU profiler: xác định hàm nóng, call stack và thời gian CPU.
- Heap profiler: tìm object giữ nhiều bộ nhớ, allocation và leak.
- GC log/profiler: đo tần suất, pause và allocation pressure của runtime.
- I/O tracing: xác định syscall đọc/ghi chậm và thời gian chờ.
- Distributed tracing: phân tích span giữa ứng dụng và dependency.
- eBPF/performance tools: quan sát syscall, scheduler, network và kernel khi công cụ được phép.

Profiling có overhead. Bắt đầu bằng thời gian ngắn, sampling phù hợp và môi trường staging hoặc một instance canary. Bảo vệ profile/log vì chúng có thể chứa tên hàm, đường dẫn, dữ liệu nhạy cảm hoặc thông tin nội bộ.

## 10. Công cụ quan sát trên Windows

Với Windows Server, Performance Monitor (PerfMon), Resource Monitor và Event Viewer giúp phân tích tài nguyên.

| Nhóm | Counter hoặc công cụ | Câu hỏi |
|---|---|---|
| CPU | Processor(_Total)\% Processor Time, Process\% Processor Time, System\Processor Queue Length | CPU toàn máy hay một process bị bão hòa? |
| Memory | Memory\Available MBytes, Memory\Pages/sec, Process\Working Set, Committed Bytes | RAM khả dụng, paging và working set ra sao? |
| Disk | PhysicalDisk\Avg. Disk sec/Read, Avg. Disk sec/Write, Disk Reads/sec, Disk Writes/sec | I/O latency và tốc độ thao tác có tăng không? |
| Network | Network Interface\Bytes Total/sec, Output Queue Length, TCPv4\Segments Retransmitted/sec | Throughput, queue và retransmission thế nào? |
| Process/service | Resource Monitor, Event Viewer, application logs | Process nào chờ tài nguyên hoặc phát sinh lỗi? |

Tên counter và cách diễn giải có thể khác theo phiên bản Windows, driver và loại storage. Nên thu thập theo chu kỳ và đối chiếu với metric cloud provider.

## 11. Thiết kế benchmark để xác nhận nút thắt

Một benchmark chỉ hữu ích khi tải thử đại diện cho hành vi thật và kết quả có thể lặp lại.

### Các kiểu thử nghiệm

- **Baseline test:** đo hệ thống ở tải bình thường để có mốc so sánh.
- **Load test:** tăng tải đến mức dự kiến trong vận hành.
- **Stress test:** vượt tải dự kiến để tìm điểm giới hạn và cách hệ thống suy giảm.
- **Spike test:** tăng tải đột ngột để xem autoscaling, queue và recovery.
- **Soak test:** giữ tải trong thời gian dài để phát hiện memory leak, cache drift hoặc resource exhaustion.
- **Component benchmark:** đo riêng database query, storage throughput, serialization hoặc một thuật toán để cô lập chi phí.

### Quy trình thử nghiệm

1. Xác định câu hỏi: CPU, RAM, I/O hay dependency đang giới hạn?
2. Chọn workload đại diện: payload, concurrency, read/write mix, cache hit ratio và request distribution.
3. Chốt tiêu chí thành công: throughput, p95/p99, error rate, resource pressure và chi phí.
4. Giữ môi trường ổn định: cùng image, cấu hình, dataset, region và phiên bản dependency.
5. Chạy warm-up để loại ảnh hưởng khởi động và JIT compilation nếu phù hợp.
6. Tăng tải theo từng mức, giữ đủ lâu để metric ổn định.
7. Ghi lại metric ứng dụng, VM/container, storage, network và dependency.
8. Thay một yếu tố, chạy lại cùng điều kiện và so sánh.
9. Lặp lại để xác định độ biến thiên; không kết luận từ một lần chạy.
10. Kiểm tra hệ thống đã trở về trạng thái bình thường và dọn tài nguyên thử nghiệm.

Không tạo tải gây ảnh hưởng tenant khác hoặc vượt giới hạn hợp đồng dịch vụ. Với dependency bên thứ ba, dùng sandbox hoặc môi trường test được phép.

## 12. Ví dụ chẩn đoán theo tình huống

### Tình huống A: CPU-bound ở dịch vụ xử lý ảnh

Triệu chứng: request rate tăng, p95 tăng, CPU của các worker gần 100%, queue depth tăng. CPU profile cho thấy hàm resize và encode chiếm phần lớn thời gian.

Phân tích:

- Memory còn đủ, không có swap hoặc OOM.
- Storage read/write latency bình thường.
- Dependency latency thấp.
- CPU profile xác nhận phần lớn thời gian nằm trong xử lý ảnh.

Hành động:

- Dùng thư viện encode tối ưu hơn và kiểm tra định dạng/quality.
- Giới hạn kích thước ảnh đầu vào.
- Tách queue theo loại tác vụ và scale worker theo backlog.
- Thử instance có nhiều vCPU nếu thuật toán chạy song song tốt.
- Đo throughput trên mỗi vCPU và chi phí trên mỗi ảnh hoàn tất.

### Tình huống B: Memory-bound ở API Java

Triệu chứng: latency tăng dần sau vài giờ, GC pause tăng, container bị OOMKilled dù CPU trung bình không cao.

Phân tích:

- Heap occupancy sau GC tăng theo thời gian.
- Allocation profile cho thấy cache không giới hạn giữ object lâu.
- Container memory còn phải chứa metaspace, thread stack và direct buffer ngoài heap.

Hành động:

- Xác định object retention và sửa cache eviction.
- Đo lại heap, native memory và container working set.
- Điều chỉnh heap dưới memory limit với headroom cho native memory.
- Chạy soak test để xác nhận bộ nhớ không tiếp tục tăng.

### Tình huống C: I/O-bound ở dịch vụ ghi log

Triệu chứng: API có CPU thấp nhưng latency ghi tăng; volume I/O queue và write latency tăng.

Phân tích:

- Nhiều thao tác ghi nhỏ và đồng bộ.
- Volume chạm giới hạn IOPS.
- Application trace cho thấy thời gian chờ flush chiếm phần lớn request.

Hành động:

- Buffer/batch log theo mức mất dữ liệu có thể chấp nhận.
- Tách log khỏi volume dữ liệu nghiệp vụ.
- Điều chỉnh volume theo IOPS và throughput yêu cầu.
- Tránh ghi log đồng bộ trên đường xử lý request nếu không cần.

### Tình huống D: Dependency-bound ở API gọi database

Triệu chứng: p99 tăng, CPU API thấp, request pending trong connection pool, database query latency tăng.

Phân tích:

- Pool acquisition wait chiếm phần đáng kể.
- Database có lock wait và một query chậm.
- Tăng pool size làm số connection database tăng nhưng query latency xấu hơn.

Hành động:

- Phân tích query plan và index.
- Giảm transaction duration và lock contention.
- Điều chỉnh pool theo giới hạn database, không chỉ theo số thread ứng dụng.
- Dùng timeout và retry có giới hạn; tránh retry storm.
- Theo dõi query latency và pool wait sau khi thay đổi.

## 13. Cẩn trọng với các giải pháp tối ưu sai hướng

| Triệu chứng | Phản ứng dễ mắc | Vì sao có thể sai | Hướng kiểm chứng |
|---|---|---|---|
| Latency cao, CPU thấp | Thêm vCPU | Có thể đang chờ database, disk hoặc lock | Trace, I/O wait, pool wait và dependency metrics |
| CPU trung bình thấp | Kết luận CPU không phải bottleneck | Một core hoặc container quota có thể bão hòa | Per-core CPU, throttling, run queue |
| RAM sử dụng cao | Tăng RAM ngay | Có thể là cache có thể thu hồi hoặc memory leak | Available, working set, GC, OOM, growth trend |
| Disk utilization 100% | Tăng kích thước volume | Có thể bị giới hạn IOPS, queue hoặc workload nhiều thao tác nhỏ | IOPS, throughput, await, queue depth |
| API chậm khi gọi database | Tăng connection pool | Database có thể đang quá tải hoặc lock | Pool wait, active connections, query latency |
| Queue tăng | Tăng số worker không giới hạn | Có thể làm dependency phía sau quá tải | Consumer throughput, downstream saturation, retry |
| CPU throttling tăng | Bỏ mọi CPU limit | Có thể gây noisy neighbor và mất kiểm soát tài nguyên | Benchmark limit phù hợp và quan sát node pressure |

Tối ưu cần cải thiện mục tiêu người dùng với chi phí và rủi ro chấp nhận được. Đừng tối ưu một metric cục bộ nếu làm xấu SLO hoặc tăng áp lực lên dependency.

## 14. Tính hiệu quả trước và sau tối ưu

Để so sánh thay đổi, ghi nhận cùng bộ chỉ số trước và sau:

- Throughput ở cùng mức tải.
- p50/p95/p99 latency.
- Error/timeout rate.
- CPU và memory utilization/pressure.
- Disk IOPS, throughput và latency.
- Network throughput, drops và retransmission.
- Dependency latency, pool wait và queue age.
- Chi phí trên một request, giao dịch hoặc job hoàn tất.

Ví dụ, một worker xử lý 100.000 ảnh trong một giờ với 8 vCPU. Sau khi tối ưu thuật toán, worker xử lý 150.000 ảnh trong cùng thời gian với 8 vCPU. Throughput tăng 50%; nếu chất lượng ảnh và error rate không đổi, chi phí trên mỗi ảnh có thể giảm. Nhưng nếu CPU utilization tăng và p99 vượt giới hạn, kết quả chưa chắc phù hợp production.

Có thể dùng công thức:

    Cost per successful operation =
        Tổng chi phí tài nguyên trong kỳ
        / Số operation hoàn tất thành công trong kỳ

Với hệ thống nhiều dependency, cần tính chi phí của cả thành phần gọi và thành phần được gọi nếu mục tiêu là chi phí end-to-end.

## 15. Checklist chẩn đoán bottleneck

### Trước khi điều tra

- [ ] Xác định service, route, workload và khoảng thời gian bị ảnh hưởng.
- [ ] Ghi lại throughput, error rate, p50/p95/p99 và SLO.
- [ ] Đối chiếu deployment, maintenance, scaling và thay đổi cấu hình.
- [ ] Xác nhận telemetry liên tục, đúng đơn vị và không đếm trùng.

### CPU

- [ ] Kiểm tra CPU theo core, process, container và fleet.
- [ ] Kiểm tra run queue, CPU pressure, steal và throttling.
- [ ] Profile hot path, lock contention và thread pool.
- [ ] Xác nhận workload có thể tận dụng thêm vCPU hay không.

### Memory

- [ ] Kiểm tra available memory, RSS/working set và limit.
- [ ] Kiểm tra swap, major page fault, pressure và OOM.
- [ ] Với runtime managed, xem heap, allocation và GC pause.
- [ ] Kiểm tra cache, object retention, native memory và NUMA nếu phù hợp.

### I/O và network

- [ ] Kiểm tra IOPS, throughput, latency và queue depth.
- [ ] Kiểm tra filesystem, inode, disk pressure và I/O wait.
- [ ] Kiểm tra NIC throughput, drops, retransmission, RTT và connection count.
- [ ] Xác định giới hạn của volume, instance, NAT, load balancer hoặc network service.

### Dependency

- [ ] Đo latency và error của từng dependency.
- [ ] Phân biệt pool wait, connect time, query time và response processing.
- [ ] Kiểm tra queue depth, oldest message age, consumer lag và retry.
- [ ] Kiểm tra quota, rate limit, timeout, circuit breaker và fallback.

### Xác nhận thay đổi

- [ ] Mỗi lần thử có giả thuyết và chỉ số xác nhận cụ thể.
- [ ] Chỉ thay một yếu tố chính mỗi lần nếu có thể.
- [ ] Giữ workload và điều kiện benchmark có thể so sánh.
- [ ] Đo lại throughput, latency, errors, saturation và cost.
- [ ] Có rollback nếu SLO hoặc dependency xấu đi.
- [ ] Ghi lại kết quả và cập nhật runbook/dashboard.

## 16. Tự kiểm tra

1. Một API có CPU 20%, p99 latency 2 giây và trace cho thấy 1,7 giây chờ database. Đây có khả năng là loại bottleneck nào? Vì sao thêm vCPU chưa chắc có ích?
2. CPU trung bình của VM là 35%, nhưng một core luôn đạt 100%. Điều này có thể ảnh hưởng request đơn luồng như thế nào?
3. Phân biệt memory capacity pressure với memory bandwidth bottleneck.
4. Vì sao memory limit của container có thể gây OOM dù node vẫn còn RAM?
5. IOPS, throughput và I/O latency mô tả ba khía cạnh nào của storage?
6. Khi queue depth tăng nhưng CPU worker thấp, cần kiểm tra dependency và concurrency nào?
7. Vì sao tăng connection pool có thể làm database chậm hơn?
8. Làm thế nào dùng distributed trace để phân biệt pool wait với query execution time?
9. Vì sao benchmark cần warm-up, tải đại diện và thay đổi từng yếu tố?
10. Những chỉ số nào cần so sánh để chứng minh tối ưu hiệu năng đồng thời giảm chi phí?

Phân biệt đúng nút thắt giúp chọn giải pháp dựa trên bằng chứng. CPU-bound cần profile và tối ưu tính toán; memory-bound cần kiểm soát working set, allocation và pressure; I/O-bound cần phân tích latency, throughput và queue; dependency-bound cần điều tra dịch vụ đích, pool và luồng gọi. Khi thử nghiệm có kiểm soát và đo lại cả SLO lẫn chi phí, đội ngũ có thể cải thiện hiệu năng mà không lãng phí tài nguyên vào sai lớp.
