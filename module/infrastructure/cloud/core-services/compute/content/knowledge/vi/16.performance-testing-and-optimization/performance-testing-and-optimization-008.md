# Đánh giá cache, locality và chi phí truyền dữ liệu giữa máy

Hiệu năng của một workload compute không chỉ phụ thuộc vào số vCPU hoặc dung lượng RAM. Ứng dụng còn chịu ảnh hưởng bởi việc dữ liệu có nằm gần nơi xử lý hay không, dữ liệu có được tái sử dụng từ cache hay phải đọc lại từ nguồn, và mỗi lần trao đổi giữa các máy mất bao lâu cũng như phát sinh bao nhiêu chi phí. Một hệ thống có CPU còn nhàn rỗi vẫn có thể chậm nếu request liên tục chờ cache miss, storage hoặc network.

**Cache** giữ dữ liệu hoặc kết quả tính toán thường được dùng để giảm thời gian truy cập và tải lên hệ thống nguồn. **Locality** mô tả mức độ gần gũi giữa compute và dữ liệu theo CPU cache, bộ nhớ, storage, host, zone hoặc region. **Chi phí truyền dữ liệu giữa máy** bao gồm ảnh hưởng hiệu năng của latency/bandwidth và chi phí tài chính theo cách tính của nền tảng cloud.

Trong **CLOUD_CORE_SERVICES_COMPUTE**, đánh giá ba yếu tố này giúp chọn cách bố trí workload, thiết kế cache, phân vùng dữ liệu và đường truyền phù hợp. Mục tiêu là cải thiện latency và throughput mà vẫn giữ tính nhất quán dữ liệu, khả năng mở rộng, độ sẵn sàng và chi phí trong giới hạn dự kiến.

## 1. Vì sao cache, locality và data transfer cần được đánh giá cùng nhau?

Một request có thể đi qua nhiều tầng:

1. CPU đọc dữ liệu từ cache gần nhất hoặc RAM.
2. Ứng dụng kiểm tra cache trong process hoặc cache dùng chung.
3. Nếu cache miss, ứng dụng truy vấn database, object storage hoặc dịch vụ khác.
4. Dữ liệu có thể phải đi qua NIC, switch ảo, load balancer, gateway hoặc liên kết giữa các zone.
5. Kết quả quay về ứng dụng, được xử lý rồi gửi đến client.

Mỗi lần chuyển sang một tầng xa hơn thường làm tăng thời gian chờ và số thành phần có thể gây nghẽn. Cache tốt có thể giảm số lần đọc từ nguồn; locality tốt có thể rút ngắn đường đi; nhưng một cache đặt ở máy khác hoặc ở region xa có thể tạo thêm network hop và làm mất lợi ích dự kiến.

Ví dụ, một dịch vụ API có thể lưu dữ liệu tham chiếu trong cache local của từng instance. Request đọc nhanh và không cần gọi Redis ở mỗi lần truy cập. Tuy nhiên, khi dữ liệu thay đổi, nhiều cache local phải được cập nhật hoặc hết hạn. Nếu dùng Redis dùng chung, việc đồng bộ dễ kiểm soát hơn nhưng mỗi cache lookup lại đi qua network. Quyết định đúng phụ thuộc tỷ lệ đọc/ghi, yêu cầu nhất quán, kích thước working set, số instance và vị trí cache.

### 1.1. Các thành phần của thời gian phản hồi

Thời gian một request có thể gồm:

- Thời gian xếp hàng và lập lịch CPU.
- Thời gian xử lý CPU và truy cập bộ nhớ.
- Thời gian tra cache và xử lý cache miss.
- Thời gian đọc/ghi storage hoặc database.
- Thời gian truyền dữ liệu giữa các tiến trình/máy.
- Thời gian chờ dịch vụ phụ thuộc và retry.

Không nên cộng các thành phần như thể chúng luôn nối tiếp. Một số tác vụ chạy song song hoặc overlap I/O với tính toán. Khi phân tích, dùng distributed tracing và timestamp ở từng span để nhận diện critical path.

### 1.2. Những câu hỏi cần trả lời

| Khía cạnh | Câu hỏi đánh giá |
| --- | --- |
| Cache | Dữ liệu nào được đọc lặp lại? Hit ratio và miss penalty ra sao? |
| Locality | Compute và dữ liệu có nằm cùng host, gần nhau trong network hay cùng zone không? |
| Network | Latency, throughput, packet loss và queue có đáp ứng tải không? |
| Chi phí | Byte truyền qua từng ranh giới nào bị tính phí? Có request, NAT, gateway hoặc replication cost không? |
| Nhất quán | Dữ liệu cache cũ được chấp nhận trong bao lâu? Cách invalidate là gì? |
| Mở rộng | Khi tăng số instance, cache có bị phân mảnh hoặc backend có bị quá tải không? |

## 2. Các tầng cache

Cache tồn tại ở nhiều tầng, từ bên trong CPU đến các dịch vụ phân tán.

### 2.1. CPU cache

CPU thường có nhiều cấp cache:

- **L1:** rất gần lõi CPU, dung lượng nhỏ và độ trễ thấp.
- **L2:** thường lớn hơn L1 và có thể riêng cho từng lõi hoặc nhóm lõi tùy kiến trúc.
- **L3/last-level cache:** dung lượng lớn hơn, có thể được chia sẻ giữa nhiều lõi.

Khi dữ liệu cần xử lý đã nằm trong cache CPU, lõi có thể truy cập nhanh hơn so với phải lấy từ RAM. Nếu working set vượt khả năng cache hoặc truy cập bộ nhớ thiếu locality, cache miss tăng và CPU phải chờ dữ liệu.

Các mẫu truy cập ảnh hưởng cache:

- Truy cập tuần tự trên mảng liên tục thường tận dụng cache line và hardware prefetch tốt.
- Truy cập ngẫu nhiên qua nhiều con trỏ có thể gây cache miss.
- Cấu trúc dữ liệu lớn và nhiều object phân tán có thể làm tăng memory footprint.
- Nhiều thread cập nhật cùng cache line có thể gây cache-line bouncing hoặc false sharing.

Với workload compute-bound, cải thiện layout dữ liệu, giảm allocation và tăng tính tuần tự có thể hiệu quả hơn việc tăng số vCPU. Tuy nhiên, cần profile trước khi thay đổi cấu trúc dữ liệu.

### 2.2. OS page cache

Hệ điều hành có thể dùng RAM để cache nội dung file đã đọc hoặc dữ liệu ghi chưa được flush xuống storage. Khi ứng dụng đọc lại file còn trong page cache, hệ thống có thể tránh truy cập storage vật lý/ảo.

Điều này làm cho benchmark đọc file lần đầu và những lần tiếp theo có kết quả khác nhau. Cần phân biệt:

- **Cold cache:** dữ liệu chưa nằm trong cache hoặc cache đã bị loại bỏ.
- **Warm cache:** dữ liệu thường dùng đã được nạp.
- **Cache pressure:** working set lớn hoặc nhiều workload cạnh tranh khiến page cache bị đẩy ra.

Không nên diễn giải một lần đọc nhanh sau lần đầu là hiệu năng storage thuần. Nếu muốn đo storage, cần thiết kế benchmark kiểm soát cache và đọc hướng dẫn của công cụ đo.

### 2.3. Cache trong ứng dụng

Ứng dụng có thể lưu kết quả ở:

- Bộ nhớ của process.
- Cache theo thread hoặc request.
- Cache local trên từng VM/container.
- Cache phân tán dùng chung.
- CDN hoặc edge cache cho nội dung phù hợp.

Cache local có latency thấp và không cần network, nhưng mỗi instance có bản sao riêng. Cache phân tán giúp nhiều instance chia sẻ dữ liệu, nhưng phụ thuộc network và dịch vụ cache. CDN phù hợp với nội dung có thể phân phối gần người dùng, thường không phù hợp với dữ liệu động nhạy cảm nếu chưa có cơ chế kiểm soát.

### 2.4. Cache phân tán

Redis, Memcached và các dịch vụ managed cache thường được dùng để chia sẻ dữ liệu giữa nhiều instance. Chúng có thể giảm tải database và giữ latency ổn định hơn khi working set phù hợp với bộ nhớ cache.

Cache phân tán có chi phí riêng:

- Network round trip cho mỗi lần đọc/ghi.
- CPU và RAM của cache node.
- Replication, persistence, backup hoặc failover.
- Kết nối, TLS, request và data transfer theo cách tính của dịch vụ.
- Vận hành cluster, shard, key distribution và hot key.

Nếu giá trị cache nhỏ hoặc hit ratio thấp, gọi cache từ xa có thể chậm hơn truy vấn nguồn nằm gần hoặc truy cập local. Cần đo end-to-end thay vì mặc định mọi cache đều nhanh hơn.

## 3. Chọn chiến lược cache

Chiến lược cache cần phản ánh cách dữ liệu được đọc, ghi và thay đổi.

### 3.1. Cache-aside (lazy loading)

Ứng dụng kiểm tra cache trước. Nếu không có dữ liệu, ứng dụng đọc từ nguồn, ghi kết quả vào cache rồi trả về:

~~~text
function getItem(key):
    value = cache.get(key)
    if value exists:
        return value

    value = database.read(key)
    if value exists:
        cache.set(key, value, ttl)
    return value
~~~

Ưu điểm là chỉ cache dữ liệu thực sự được truy cập. Nhược điểm là request đầu tiên sau khi hết hạn phải chờ nguồn dữ liệu; nhiều request đồng thời có thể cùng cache miss và tạo tải đột biến lên database.

### 3.2. Read-through và write-through

Với read-through, cache layer tự tải dữ liệu từ nguồn khi miss. Với write-through, thao tác ghi cập nhật nguồn và cache theo một luồng đồng bộ. Hai cách này có thể đơn giản hóa logic ở ứng dụng nhưng phụ thuộc tính năng và semantics của cache client/service.

Write-through giúp giảm khả năng cache chứa dữ liệu cũ sau khi ghi thành công, nhưng tăng thời gian ghi và phụ thuộc vào khả năng ghi đồng bộ cả hai nơi. Cần xác định hành vi khi một bên thành công còn bên kia thất bại.

### 3.3. Write-behind/write-back

Write-behind ghi trước vào cache rồi cập nhật nguồn bất đồng bộ. Cách này có thể giảm latency ghi nhưng tạo rủi ro mất dữ liệu khi cache lỗi trước khi flush, hoặc dữ liệu nguồn bị trễ.

Chỉ dùng khi có cơ chế durable queue/log, retry, deduplication, ordering và phục hồi phù hợp. Không dùng write-behind cho dữ liệu giao dịch quan trọng nếu chưa xác định rõ mức mất dữ liệu chấp nhận được.

### 3.4. TTL, invalidation và consistency

TTL (time to live) quy định thời gian một entry được xem là hợp lệ. TTL ngắn giúp dữ liệu mới hơn nhưng tăng cache miss; TTL dài tăng hit ratio nhưng có thể trả dữ liệu cũ lâu hơn.

Các cách invalidation:

- Xóa key sau khi nguồn dữ liệu cập nhật.
- Cập nhật cache cùng transaction logic của ứng dụng.
- Dùng version hoặc generation key để vô hiệu hóa nhóm entry.
- Dựa vào TTL khi chấp nhận độ trễ cập nhật.
- Phát sự kiện invalidation qua message bus.

Cache invalidation khó khi nhiều instance cùng giữ bản sao. Cần xác định rõ consistency model: strong, read-after-write, eventual hoặc stale-while-revalidate. Không tuyên bố cache nhất quán tức thời nếu việc invalidate chạy bất đồng bộ.

### 3.5. Tránh cache stampede và hot key

**Cache stampede** xảy ra khi nhiều request cùng lúc miss một key và đồng thời gọi backend. Biện pháp giảm thiểu:

- Single-flight hoặc request coalescing để chỉ một request tải dữ liệu.
- TTL jitter để nhiều key không hết hạn cùng lúc.
- Refresh-ahead để làm mới trước khi hết hạn.
- Stale-while-revalidate khi nghiệp vụ cho phép trả dữ liệu cũ tạm thời.
- Rate limit hoặc concurrency limit cho backend.
- Negative caching cho kết quả không tồn tại, với TTL phù hợp.

**Hot key** là key nhận lượng truy cập lớn hơn đáng kể so với các key khác. Có thể dùng local cache, replication, key sharding hoặc precompute, nhưng cần cân nhắc nhất quán và cách cập nhật các bản sao.

## 4. Đo hiệu quả cache

Không thể đánh giá cache chỉ bằng hit ratio. Một cache có hit ratio cao nhưng mỗi lần hit vẫn tốn network round trip lớn có thể không cải thiện latency tổng thể như kỳ vọng.

### 4.1. Chỉ số quan trọng

| Chỉ số | Ý nghĩa | Cách diễn giải |
| --- | --- | --- |
| Hit ratio | Tỷ lệ yêu cầu được phục vụ từ cache | Cao thường tốt, nhưng phải xét latency và chi phí |
| Miss ratio | Tỷ lệ yêu cầu phải tải từ nguồn | Miss tăng có thể làm backend quá tải |
| Hit/miss latency | Thời gian xử lý cache hit và miss | So sánh p50, p95, p99 |
| Eviction rate | Tần suất entry bị loại khỏi cache | Cao kéo dài có thể báo working set vượt capacity |
| Memory utilization | Mức RAM cache đang dùng | Quá cao làm tăng eviction hoặc rủi ro OOM |
| Backend request rate | Số truy vấn nguồn | Nên giảm khi cache phục vụ tốt |
| Network bytes | Lưu lượng đến/đi cache | Phát hiện overhead truyền dữ liệu |
| Stale response rate | Tỷ lệ dữ liệu cũ được trả | Đánh giá đánh đổi consistency |
| Refresh failure | Số lần cập nhật cache thất bại | Phát hiện dữ liệu có thể cũ kéo dài |

Hit ratio có thể tính:

\[
\text{Hit ratio} =
\frac{\text{Cache hits}}{\text{Cache hits}+\text{Cache misses}}
\]

Ví dụ có 900 hit và 100 miss thì hit ratio là 90%. Nhưng nếu hit mất 8 ms, miss mất 12 ms, lợi ích latency nhỏ hơn nhiều so với một cache hit local có thời gian thấp hơn đáng kể. Luôn đo latency thực tế của request end-to-end.

### 4.2. Đo theo percentile

Average latency có thể che giấu các request chậm. Nên theo dõi:

- p50: trải nghiệm của request điển hình.
- p95: nhóm request chậm hơn phần lớn lưu lượng.
- p99: tail latency, thường bị ảnh hưởng bởi cache miss, hot key, GC, queue hoặc network.

Nếu p50 cải thiện nhưng p99 tăng, có thể cache đang gây stampede hoặc backend bị dồn tải vào những lúc nhiều key hết hạn.

### 4.3. Kiểm tra working set và cache capacity

Working set là tập dữ liệu thường xuyên được truy cập trong khoảng thời gian liên quan. Nếu cache nhỏ hơn working set, entry có thể liên tục bị đẩy ra trước khi được tái sử dụng. Nếu cache quá lớn, chi phí RAM và replica có thể cao mà lợi ích tăng thêm rất nhỏ.

Nên đo:

- Kích thước entry trung bình và phân phối kích thước.
- Số key duy nhất được truy cập.
- Tần suất truy cập theo key.
- Tốc độ thay đổi dữ liệu.
- Eviction theo thời gian.
- Memory overhead của key, object và metadata.

Không chỉ lấy tổng dung lượng dữ liệu nguồn làm cache size. Cần xác định phần dữ liệu nóng và chính sách eviction.

## 5. Locality ở tầng CPU và bộ nhớ

Locality mô tả xu hướng chương trình truy cập lại dữ liệu hoặc truy cập các vị trí gần nhau. Có hai dạng cơ bản:

- **Temporal locality:** dữ liệu vừa được dùng có khả năng được dùng lại sớm.
- **Spatial locality:** dữ liệu ở gần vị trí vừa truy cập có khả năng được truy cập tiếp.

Thiết kế thuật toán và cấu trúc dữ liệu tận dụng hai dạng locality này có thể giảm cache miss và cải thiện hiệu năng CPU.

### 5.1. Cache locality trong chương trình

Ví dụ, duyệt mảng tuần tự thường có locality tốt hơn truy cập danh sách liên kết phân tán trong bộ nhớ:

~~~text
for each row in contiguous_array:
    process(row)

for each node in linked_structure:
    process(node.value)
    node = node.next
~~~

Đây là minh họa về cách bố trí dữ liệu. Hiệu năng thực tế còn phụ thuộc compiler, runtime, kích thước object, prefetch, branch prediction và workload.

Một số cách cải thiện:

- Dùng cấu trúc dữ liệu liên tục khi phù hợp.
- Giảm pointer chasing và object allocation không cần thiết.
- Xử lý theo batch để tái sử dụng dữ liệu đã nạp.
- Tránh nhiều thread ghi vào cùng cache line nếu có thể.
- Profile cache miss và memory stall trước khi tối ưu.

### 5.2. NUMA locality

Một số VM lớn hoặc host đa socket sử dụng kiến trúc NUMA (Non-Uniform Memory Access). CPU có thể truy cập RAM gắn với node cục bộ nhanh hơn RAM thuộc node khác. Nếu thread chạy trên một NUMA node nhưng dữ liệu được cấp phát ở node khác, truy cập remote memory có thể tăng latency và giảm throughput.

Các khái niệm:

- **NUMA node:** nhóm CPU và vùng bộ nhớ có quan hệ truy cập cục bộ.
- **CPU affinity:** ràng buộc thread/process vào một tập CPU.
- **Memory affinity:** định hướng cấp phát bộ nhớ từ một NUMA node.
- **First-touch policy:** trên nhiều hệ Linux, trang nhớ thường được gắn với node của CPU đầu tiên chạm vào trang.

Trên Linux có thể quan sát topology và chính sách NUMA bằng:

~~~bash
lscpu
numactl --hardware
numastat
~~~

Không phải mọi instance cloud đều phơi bày topology NUMA cho guest OS, và một số nền tảng có thể thay đổi cách bố trí theo loại máy. Chỉ dùng pinning hoặc memory binding sau khi đo trên đúng instance type. Ràng buộc quá chặt có thể làm giảm khả năng scheduler cân bằng tải.

### 5.3. False sharing và contention

False sharing xảy ra khi các thread cập nhật các biến khác nhau nhưng những biến đó nằm trên cùng cache line. CPU phải đồng bộ cache line giữa các lõi dù logic ứng dụng không chia sẻ cùng biến. Padding hoặc bố trí lại dữ liệu có thể giảm vấn đề này.

Contention trên lock, atomic counter hoặc cấu trúc dùng chung cũng có thể khiến cache line di chuyển giữa các lõi. Khi tối ưu, xem cả CPU utilization, lock wait, context switch và hardware performance counter nếu môi trường hỗ trợ.

## 6. Locality ở tầng storage và dữ liệu

Đặt compute gần dữ liệu có thể giảm thời gian truyền, chi phí và số lần lỗi ở đường mạng.

### 6.1. Các dạng locality

- **Local disk:** dữ liệu nằm trên thiết bị cục bộ của host; có thể nhanh nhưng thường có vòng đời và độ bền khác persistent volume.
- **Attached block volume:** volume gắn với VM theo giới hạn vùng và dịch vụ; truy cập qua storage network của provider.
- **Shared file storage:** nhiều máy truy cập chung filesystem qua NFS/SMB hoặc dịch vụ managed.
- **Object storage:** dữ liệu truy cập qua API, thường phù hợp object lớn, artifact và dữ liệu phi cấu trúc.
- **Database locality:** ứng dụng và database ở cùng zone hoặc gần nhau về network có thể giảm round trip.

Không nên chuyển dữ liệu quan trọng sang local/ephemeral disk chỉ vì benchmark thấy nhanh hơn. Cần tính đến mất dữ liệu khi host bị thay thế, khả năng phục hồi và yêu cầu replication.

### 6.2. Data locality trong xử lý phân tán

Với hệ thống xử lý dữ liệu lớn, di chuyển compute đến gần dữ liệu thường rẻ hơn kéo lượng dữ liệu lớn qua network. Ví dụ, thay vì tải toàn bộ dataset về một VM để lọc, có thể chạy worker gần object storage hoặc database và chỉ gửi kết quả đã tổng hợp.

Các kỹ thuật:

- Partition/shard dữ liệu theo khóa truy cập phổ biến.
- Đưa worker đến gần partition mà worker xử lý.
- Batch nhiều thao tác nhỏ thành một request lớn hơn.
- Chỉ truyền cột hoặc trường cần thiết.
- Nén dữ liệu khi tiết kiệm network lớn hơn chi phí CPU nén/giải nén.
- Dùng streaming để tránh tải toàn bộ dataset vào RAM.
- Tránh gọi service-to-service quá nhiều lần cho một request.

Data locality không chỉ là đặt hai VM cùng zone. Nó còn là thiết kế cách chia dữ liệu, lịch chạy job và số lần dữ liệu phải đi qua mạng.

### 6.3. Locality và khả năng sẵn sàng

Đặt compute và data cùng một zone có thể giảm latency và một số loại transfer charge, nhưng tạo thêm phụ thuộc vào một vùng lỗi. Với workload cần high availability, có thể phải replication sang zone khác và chấp nhận thêm chi phí truyền dữ liệu.

Thiết kế cần cân bằng:

- Latency của đường truy cập thường xuyên.
- Khả năng chịu lỗi zone/region.
- Độ trễ replication và consistency.
- Chi phí inter-zone/inter-region.
- Quy trình failover và khôi phục.

Không nên gom mọi thành phần vào một zone chỉ để tối ưu latency nếu yêu cầu availability cần nhiều failure domain.

## 7. Đánh giá latency và bandwidth giữa các máy

Latency và bandwidth là hai đại lượng khác nhau:

- **Latency:** thời gian để một gói tin hoặc một request đi từ nguồn đến đích và nhận phản hồi. Ping thường đo round-trip time (RTT).
- **Bandwidth:** tốc độ truyền dữ liệu tối đa hoặc được cấp, thường biểu diễn bằng bit/s.
- **Throughput:** tốc độ dữ liệu thực tế đạt được trong điều kiện workload và giao thức cụ thể.
- **Packet loss:** tỷ lệ gói bị mất; có thể làm tăng retry và tail latency.
- **Jitter:** mức dao động của latency, quan trọng với workload nhạy thời gian.

Một kết nối có bandwidth cao vẫn có thể có latency lớn. Với request nhỏ, latency thường quan trọng hơn bandwidth; với truyền file lớn, throughput và bandwidth có thể chi phối.

### 7.1. Ước lượng thời gian truyền dữ liệu

Thời gian truyền lý tưởng có thể ước lượng:

\[
T_{\text{transfer}} \approx \frac{\text{Data size in bits}}{\text{Effective throughput in bits/s}}
\]

Tổng thời gian thực tế còn gồm RTT, thiết lập kết nối, TLS, protocol overhead, congestion, retry, queue và thời gian xử lý ở hai đầu.

Ví dụ, truyền 1 GiB qua đường truyền có throughput hiệu dụng 1 Gbit/s cần khoảng 8.6 giây trong điều kiện lý tưởng, chưa tính overhead. Nếu chia dữ liệu thành hàng nghìn request nhỏ, tổng thời gian có thể bị chi phối bởi round trip hơn là dung lượng.

### 7.2. Những phép đo cơ bản

Trên Linux, các công cụ thường dùng:

~~~bash
# Đo RTT và kiểm tra mất gói cơ bản
ping -c 20 TARGET_HOST

# Quan sát tuyến đường và các điểm có thể gây mất gói
mtr -rw TARGET_HOST

# Đo throughput giữa hai host do nhóm kiểm soát
# Host nhận:
iperf3 -s

# Host gửi:
iperf3 -c TARGET_HOST -t 30

# Đo theo chiều ngược lại nếu cần
iperf3 -c TARGET_HOST -R -t 30
~~~

Thay TARGET_HOST bằng địa chỉ của máy kiểm thử. Chỉ chạy iperf3 giữa các endpoint được phép và trong cửa sổ thử nghiệm đã thống nhất; công cụ tạo lưu lượng có thể ảnh hưởng workload khác và phát sinh transfer charge.

Ping không phản ánh chính xác latency của ứng dụng nếu ICMP bị giới hạn hoặc ưu tiên khác traffic thực tế. MTR/traceroute có thể bị ảnh hưởng bởi thiết bị trung gian không trả lời probe. Cần kết hợp network metric của provider, TCP/TLS trace và distributed tracing.

### 7.3. Đo theo cặp vị trí

Đối với kiến trúc nhiều zone hoặc region, đo ma trận:

| Nguồn | Đích | Mục tiêu đo |
| --- | --- | --- |
| Cùng VM/process | Local cache hoặc local socket | Chi phí truy cập trong máy |
| VM cùng zone | Cache/database cùng zone | Đường truy cập thường xuyên |
| VM khác zone | Database/cache ở zone khác | Latency và transfer cross-zone |
| VM khác region | Dịch vụ ở region xa | Latency, throughput và egress |
| VM đến object storage | Endpoint nội bộ hoặc public endpoint | Đường đi, gateway và chi phí |

Không giả định hai máy cùng zone luôn có latency cố định hoặc cùng host. Placement và network topology do provider quản lý. Dùng phép đo trên instance type, zone, thời điểm và tải tương ứng với production.

## 8. Chi phí truyền dữ liệu giữa máy

Cloud provider có thể tính phí theo lượng dữ liệu, vị trí nguồn/đích, loại dịch vụ và đường truyền. Cùng một GB dữ liệu có thể có mức giá khác nhau tùy transfer đi Internet, giữa zone, giữa region, qua NAT, load balancer, peering hoặc dịch vụ kết nối riêng.

### 8.1. Những luồng dữ liệu cần kiểm kê

- **Ingress:** dữ liệu đi vào cloud từ Internet hoặc mạng ngoài.
- **Egress:** dữ liệu rời cloud đến Internet hoặc mạng ngoài.
- **Inter-zone:** dữ liệu giữa các availability zone trong một region.
- **Inter-region:** dữ liệu giữa các region.
- **Service-to-service:** dữ liệu giữa VM, container, database, cache, load balancer và storage.
- **NAT/gateway path:** dữ liệu đi qua NAT gateway, transit gateway hoặc dịch vụ trung gian.
- **Replication/backup:** dữ liệu sao chép sang zone, region hoặc tài khoản khác.

Một số luồng ingress có thể miễn phí trong một số dịch vụ, nhưng không được giả định điều đó cho mọi provider hoặc mọi loại endpoint. Phải kiểm tra bảng giá và billing meter hiện hành của nền tảng.

### 8.2. Mô hình tính chi phí

Một ước lượng cơ bản:

\[
\text{Transfer cost} =
\sum_i \left(\frac{\text{Bytes}_i}{\text{Billing unit}}\times\text{Rate}_i\right)
\]

Trong đó mỗi nhóm i đại diện một loại luồng có mức giá riêng, chẳng hạn egress Internet, cross-zone hoặc inter-region. Tổng chi phí thực tế có thể cộng thêm:

- Phí NAT gateway hoặc data processing.
- Phí load balancer hoặc transit gateway theo byte/giờ.
- Phí request, API operation hoặc object retrieval.
- Phí replication, interconnect hoặc dedicated connection.
- Chi phí cache/storage node và bản sao dữ liệu.

Ví dụ minh họa: một ứng dụng truyền 2 TiB/tháng qua một loại đường truyền có đơn giá giả định 0,02 USD/GiB. Chi phí thành phần đó xấp xỉ 40,96 USD nếu quy đổi 1 TiB = 1024 GiB. Đây chỉ là phép tính ví dụ, không phải bảng giá của nhà cung cấp; cần xác định billing unit và rate đúng theo dịch vụ.

### 8.3. Đọc billing và network metrics

Để tìm nguồn phát sinh phí:

1. Phân nhóm chi phí theo service, region, usage type và network path.
2. Đối chiếu thời điểm chi phí tăng với deploy, batch job, replication hoặc thay đổi traffic.
3. Đo bytes sent/received theo VM, interface, container hoặc service.
4. Xác định luồng nào đi qua NAT, public endpoint hoặc cross-zone.
5. Kiểm tra cache hit ratio, số request và kích thước payload.
6. So sánh chi phí trước/sau thay đổi cùng mức traffic.

Billing thường có độ trễ và mức tổng hợp khác metric vận hành. Không dùng billing data một mình để chẩn đoán latency tức thời.

## 9. Giảm truyền dữ liệu không cần thiết

Một số thay đổi kiến trúc có thể giảm cả latency và chi phí:

- Đặt ứng dụng gần database/cache hoặc endpoint dữ liệu thường xuyên dùng.
- Dùng private endpoint/service endpoint khi phù hợp và được provider hỗ trợ.
- Tránh route qua NAT hoặc public Internet nếu có đường nội bộ an toàn hơn.
- Batch request và giảm số lần round trip.
- Chỉ lấy các trường cần thiết, tránh truyền payload dư thừa.
- Nén payload lớn khi CPU còn dư và tỷ lệ nén có lợi.
- Dùng connection pooling và keep-alive để tránh handshake lặp lại.
- Dùng streaming/chunking cho dữ liệu lớn.
- Đưa CDN hoặc edge cache đến gần người dùng cho nội dung phù hợp.
- Dùng cache local cho dữ liệu đọc nhiều và có thể chấp nhận bản sao cục bộ.
- Tổng hợp dữ liệu tại nơi xử lý trước khi gửi kết quả qua region.

Mỗi tối ưu đều có đánh đổi. Compression làm tăng CPU; batching có thể tăng thời gian chờ để gom đủ batch; cache local làm phức tạp invalidation; private endpoint có thể phát sinh chi phí riêng. Đo end-to-end trước khi chọn.

## 10. Thiết kế benchmark cho cache và data locality

Một benchmark có ý nghĩa phải tái hiện được access pattern và tải thực tế. Chỉ chạy một lệnh đo throughput không đủ để quyết định vị trí cache hoặc topology.

### 10.1. Xác định mục tiêu và baseline

Trước khi đo, ghi rõ:

- Workload: API, database, batch, stream hoặc distributed compute.
- SLO: p95/p99 latency, throughput, error rate và availability.
- Kích thước dữ liệu, working set và tỷ lệ đọc/ghi.
- Kích thước payload và số request/giây.
- Số instance, CPU/RAM, zone/region và loại network.
- Cache đang bật/tắt, TTL, eviction policy và warmup.
- Chi phí hiện tại theo service và transfer type.

Giữ một baseline có thể lặp lại. Nếu thay cache, instance size, database, network placement cùng lúc, sẽ khó biết yếu tố nào tạo ra khác biệt.

### 10.2. Ma trận thử nghiệm

| Thử nghiệm | Cache | Vị trí dữ liệu | Điều muốn biết |
| --- | --- | --- | --- |
| A | Tắt | Nguồn hiện tại | Baseline latency và backend load |
| B | Local cache | Cùng VM | Lợi ích khi bỏ network lookup |
| C | Distributed cache | Cùng zone | Đánh đổi chia sẻ dữ liệu và network RTT |
| D | Distributed cache | Khác zone | Tác động cross-zone |
| E | Local cache + distributed fallback | Cùng zone | Lợi ích của hai tầng cache |
| F | Không đổi cache | Khác region | Chi phí và latency do data placement |

Thử nghiệm cần giữ cùng dữ liệu, request mix, concurrency và thời gian đo. Thực hiện warmup riêng, sau đó đo cold-cache và warm-cache thành các trường hợp khác nhau.

### 10.3. Kịch bản tải

Nên kiểm tra nhiều dạng tải:

- **Read-heavy:** phần lớn request đọc cùng một tập dữ liệu.
- **Write-heavy:** nhiều cập nhật và invalidation.
- **Uniform:** key được truy cập tương đối đồng đều.
- **Zipf/hot-key:** một nhóm nhỏ key nhận phần lớn request.
- **Large payload:** truyền dữ liệu lớn để kiểm tra throughput.
- **Small request/high concurrency:** nhiều request nhỏ để quan sát RTT, queue và connection overhead.
- **Burst:** tải tăng nhanh sau khoảng yên lặng để kiểm tra cache stampede và autoscaling.

Không benchmark production bằng tải vượt ngưỡng khi chưa có giới hạn và kế hoạch dừng. Dùng môi trường thử nghiệm tương đương hoặc traffic replay đã loại bỏ dữ liệu nhạy cảm.

### 10.4. Theo dõi đồng thời

Trong mỗi lần thử, thu thập:

- Application p50/p95/p99, throughput và error rate.
- Cache hit/miss, eviction, memory, command latency và connection count.
- Database query rate, CPU, connection pool và lock wait.
- CPU utilization, memory pressure, GC, context switch và I/O wait.
- Network RTT, throughput, retransmission, packet loss và bytes sent/received.
- Billing usage hoặc ước lượng byte theo từng đường truyền.

Chỉ số phải có cùng khoảng thời gian và được gắn nhãn theo kịch bản. Nếu chỉ xem cache hit ratio mà không xem database load hoặc request latency, có thể kết luận sai.

## 11. Ví dụ tính toán lợi ích cache

Giả sử một API nhận 10.000 request/giây. Mỗi request cần đọc một bản ghi. Trước tối ưu, mọi request đều gọi database. Sau khi thêm cache, hit ratio đo được là 90%.

Nếu mọi request đều có cùng access pattern và không tính request retry:

\[
\text{Database reads after cache}
=10{,}000\times(1-0.90)=1{,}000\ \text{reads/s}
\]

Số lượt đọc database giảm 90% trong mô hình đơn giản này. Nhưng hệ thống còn phải xử lý 10.000 cache lookup mỗi giây; nếu cache là dịch vụ từ xa, network và cache node phải đủ năng lực.

Để quyết định có lợi hay không, đo:

1. Latency cache hit và miss.
2. Latency database trước và sau khi giảm tải.
3. CPU/RAM và network của cache node.
4. Số request backend phát sinh do miss, refresh và invalidation.
5. Chi phí cache node, transfer và database capacity tiết kiệm được.
6. Tỷ lệ dữ liệu cũ và hành vi khi cache unavailable.

Không dùng phép tính hit ratio để suy ra trực tiếp phần trăm cải thiện latency. Cache hit và miss có thời gian xử lý khác nhau; request còn có các bước khác trên critical path.

## 12. Ví dụ: chọn local cache hay distributed cache

Một dịch vụ Java chạy trên nhiều VM trong cùng region, đọc nhiều dữ liệu cấu hình và danh mục sản phẩm. Dữ liệu thay đổi không thường xuyên nhưng cần được cập nhật trong vài phút.

Hai phương án:

| Tiêu chí | Local cache trên mỗi VM | Distributed cache dùng chung |
| --- | --- | --- |
| Latency lookup | Thấp vì không qua network | Có thêm network round trip |
| Chia sẻ dữ liệu | Mỗi VM giữ bản sao | Các VM truy cập cùng cache |
| Invalidation | Phải gửi sự kiện đến nhiều VM hoặc chờ TTL | Có thể cập nhật một nơi |
| Scale-out | Instance mới cần warmup | Có thể dùng cache đã có dữ liệu |
| Failure mode | Cache mất theo instance; nguồn vẫn là nơi khôi phục | Cache service là dependency chung |
| Chi phí | RAM của từng VM và bản sao dữ liệu | Cache node, network và vận hành dịch vụ |

Một thiết kế hai tầng có thể phù hợp: local cache cho dữ liệu tham chiếu ít thay đổi, distributed cache làm nguồn chia sẻ và fallback về database khi miss. Sự kiện thay đổi dữ liệu có thể invalidation local cache; TTL là lớp bảo vệ khi sự kiện bị mất.

Trước khi chọn, nhóm cần đo p95/p99, tỷ lệ cập nhật, kích thước working set, số VM và độ trễ chấp nhận được của dữ liệu cũ. Nếu yêu cầu read-after-write nghiêm ngặt, phải thiết kế invalidation đồng bộ hoặc bỏ cache cho luồng cần consistency đó.

## 13. Đánh giá chi phí tổng thể

Tối ưu cache hoặc locality không nên chỉ so sánh một dòng giá. Cần tính tổng chi phí của compute, cache, storage, network và vận hành.

Một mô hình đơn giản:

\[
\text{Total cost} =
\text{Compute}+\text{Cache}+\text{Storage}+\text{Transfer}+\text{Gateway}+\text{Operations}
\]

Ví dụ:

- Local cache có thể làm tăng RAM cần thiết và số VM.
- Distributed cache có thể giảm database capacity nhưng thêm cache node và network.
- Đưa database cùng zone có thể giảm latency nhưng tăng rủi ro khi zone lỗi nếu không có replica.
- Replication đa zone/region tăng availability nhưng phát sinh storage và transfer.
- Compression giảm byte truyền nhưng tăng CPU.

Nên đánh giá **cost per request**, **cost per GB processed** hoặc **cost per job** thay vì chỉ xem tổng bill. Một cấu hình đắt hơn theo giờ vẫn có thể rẻ hơn trên mỗi giao dịch nếu hoàn thành nhiều việc hơn hoặc giảm retry.

## 14. Những rủi ro và đánh đổi

### 14.1. Cache chứa dữ liệu cũ

TTL dài hoặc invalidation không đầy đủ có thể trả dữ liệu stale. Với giá, quyền truy cập, số dư hoặc trạng thái giao dịch, dữ liệu cũ có thể gây hậu quả nghiệp vụ. Phân loại dữ liệu theo mức độ chấp nhận stale và không cache luồng cần consistency mạnh nếu không có thiết kế phù hợp.

### 14.2. Cache outage

Nếu mọi request chuyển sang database khi cache lỗi, backend có thể bị quá tải. Cần timeout ngắn hợp lý, circuit breaker, giới hạn concurrency, fallback có kiểm soát và load shedding. Cache không nên trở thành điểm lỗi đơn làm toàn hệ thống mất khả năng phục vụ.

### 14.3. Cache poisoning và dữ liệu nhạy cảm

Cache key phải bao gồm các yếu tố phân biệt tenant, người dùng hoặc quyền truy cập khi nội dung không dùng chung. Nếu cache key không đủ ngữ cảnh, dữ liệu của một người dùng có thể bị trả cho người khác. Không cache secret hoặc dữ liệu nhạy cảm nếu chưa có chính sách mã hóa, phân vùng và retention.

### 14.4. Cross-zone và cross-region dependency

Đặt một cache hoặc database ở region xa có thể tăng RTT và làm request phụ thuộc vào liên kết liên vùng. Khi link gián đoạn, service có thể lỗi dù compute vẫn khỏe. Cần đánh giá timeout, retry budget, replica, failover và khả năng hoạt động khi mất kết nối.

### 14.5. Tối ưu cục bộ làm giảm hiệu năng tổng thể

Giảm số byte truyền có thể tăng CPU nén; tăng cache size có thể làm GC hoặc memory pressure nặng hơn; pin CPU có thể giảm scheduler flexibility; đặt dữ liệu cùng zone có thể làm giảm resilience. Mỗi thay đổi cần được đo trên toàn request path và theo SLO.

## 15. Checklist đánh giá cache, locality và transfer

**Cache**

- [ ] Xác định dữ liệu nóng và working set.
- [ ] Đo hit/miss ratio cùng p50/p95/p99.
- [ ] Đo eviction, memory pressure và backend request rate.
- [ ] Chọn TTL/invalidation theo yêu cầu consistency.
- [ ] Có cơ chế chống stampede, hot key và cache outage.
- [ ] Phân vùng cache key theo tenant/quyền khi cần.

**Locality**

- [ ] Kiểm tra CPU cache behavior và NUMA nếu workload phù hợp.
- [ ] Xác định vị trí compute, storage, database và cache.
- [ ] Đo latency giữa các cặp VM/zone/region.
- [ ] Đánh giá data partitioning, batching và số round trip.
- [ ] Cân bằng latency với high availability và failure domain.

**Chi phí truyền dữ liệu**

- [ ] Liệt kê ingress, egress, inter-zone, inter-region và service path.
- [ ] Kiểm tra NAT, gateway, load balancer và private endpoint.
- [ ] Đối chiếu byte metric với billing usage type.
- [ ] Tính cost per request/job/GB sau tối ưu.
- [ ] Kiểm tra chi phí replication, backup và cache node.

**Benchmark**

- [ ] Có baseline và mục tiêu SLO.
- [ ] Tách cold-cache và warm-cache.
- [ ] Dùng cùng dataset, request mix và concurrency.
- [ ] Thử read-heavy, write-heavy, hot-key, burst và large payload.
- [ ] Thu thập ứng dụng, cache, database, CPU, storage, network và cost cùng lúc.
- [ ] Lặp lại thử nghiệm và ghi rõ instance type, zone, region, thời gian.

## 16. Quy trình tối ưu đề xuất

1. **Đo baseline:** xác định request path, latency percentile, throughput, lỗi và chi phí hiện tại.
2. **Phân tích access pattern:** tỷ lệ đọc/ghi, working set, hot key, payload và tần suất thay đổi.
3. **Xác định bottleneck:** CPU cache/memory, cache service, database, storage hay network.
4. **Chọn chiến lược cache:** local, distributed, read-through, cache-aside hoặc kết hợp theo consistency.
5. **Cải thiện locality:** đặt compute gần dữ liệu, partition dữ liệu, batch request và giảm round trip.
6. **Đo transfer:** kiểm tra latency, throughput, packet loss và bytes qua từng ranh giới tính phí.
7. **Thử nghiệm có kiểm soát:** thay một yếu tố mỗi lần và chạy các kịch bản tải đại diện.
8. **So sánh hiệu quả:** latency, throughput, backend load, availability và cost per unit of work.
9. **Triển khai dần:** canary, theo dõi và rollback nếu SLO hoặc consistency xấu đi.
10. **Theo dõi liên tục:** phát hiện working set thay đổi, hot key, cache churn, network path và billing bất thường.

## 17. Nguyên tắc vận hành

1. **Đo trước khi tối ưu:** dùng trace và metric để tìm critical path thực sự.
2. **Đánh giá cache theo end-to-end:** hit ratio phải đi cùng latency, backend load và chi phí cache.
3. **Hiểu consistency:** TTL và invalidation phải phù hợp với mức dữ liệu cũ nghiệp vụ chấp nhận.
4. **Tận dụng locality:** giảm pointer chasing, remote memory và round trip không cần thiết.
5. **Đặt compute gần dữ liệu khi hợp lý:** cân bằng latency, transfer cost và failure domain.
6. **Phân biệt latency và bandwidth:** request nhỏ thường nhạy RTT; dữ liệu lớn thường nhạy throughput.
7. **Kiểm kê mọi luồng transfer:** gồm inter-zone, inter-region, NAT, gateway, replication và egress.
8. **Tính tổng chi phí:** gồm compute, cache, storage, transfer và dịch vụ mạng trung gian.
9. **Benchmark có kiểm soát:** so sánh cold/warm cache, tải đọc/ghi, hot key và nhiều vị trí.
10. **Bảo vệ độ sẵn sàng và dữ liệu:** cache outage, stale data và mất liên kết phải có phương án xử lý.

Cache, locality và chi phí truyền dữ liệu có quan hệ chặt chẽ. Cache giảm số lần đọc nguồn nhưng có thể thêm network dependency; locality rút ngắn đường đi nhưng cần cân bằng failure domain; truyền dữ liệu ít hơn có thể giảm bill nhưng không nên đánh đổi CPU, consistency hoặc availability một cách thiếu kiểm chứng. Khi đo đồng thời hiệu năng, độ đúng dữ liệu và chi phí trên cùng workload, đội kỹ thuật có thể chọn topology và chiến lược cache phù hợp với yêu cầu thực tế của hệ thống cloud compute.
