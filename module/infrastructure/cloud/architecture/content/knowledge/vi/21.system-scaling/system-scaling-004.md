# Phân phối tải, skew và xử lý điểm nghẽn

> **Chương:** Mở rộng hệ thống  
> **Phạm vi:** Thiết kế kiến trúc ứng dụng trên đám mây từ yêu cầu nghiệp vụ đến lựa chọn mạng, compute, dữ liệu và mô hình triển khai. Bài học tập trung vào phân phối lưu lượng và công việc, nhận diện lệch tải (skew), tìm điểm nghẽn và xử lý chúng để giữ độ tin cậy, hiệu năng, khả năng mở rộng, chi phí và khả năng vận hành theo tư duy Well-Architected.

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích vai trò của load balancer, routing, partitioning, queue và autoscaling trong phân phối tải.
2. Nhận diện các dạng skew: hot key, hot partition, tenant lệch tải, truy vấn lệch, vùng/availability zone quá tải và tài nguyên không đồng đều.
3. Đọc các chỉ số latency, throughput, saturation, queue age, utilization và error rate để tìm bottleneck theo đường đi của request.
4. Phân biệt bottleneck tại edge, network, compute, connection pool, database, broker và dependency bên ngoài.
5. Chọn biện pháp điều tiết, cân bằng, chia nhỏ hoặc cô lập tải; đánh giá tác động tới tính nhất quán, thứ tự, độ tin cậy và chi phí.
6. Lập kế hoạch kiểm thử tải, fault test, capacity forecast và đo lường sau thay đổi.

## 1. Phân phối tải là bài toán kiến trúc đầu cuối

Một hệ thống có thể có nhiều máy chủ và nhiều replica nhưng vẫn chậm nếu request không được phân phối hợp lý. Ví dụ, ứng dụng đặt chỗ có 20 replica API nhưng chỉ một database primary, một partition queue đang nhận phần lớn booking hoặc một tenant chạy báo cáo nặng. Tăng replica API không giải quyết được các nút nghẽn đó.

**Load distribution** là cách đưa request, job, message hoặc dữ liệu đến tài nguyên có thể xử lý chúng sao cho phù hợp với mục tiêu về độ trễ, throughput, khả năng phục hồi, tính công bằng và chi phí.

Cần phân biệt ba ý:

- **Load balancing:** phân phối request hoặc connection giữa các backend.
- **Work partitioning:** chia tập dữ liệu/công việc thành phần có thể xử lý song song.
- **Load shedding/admission control:** từ chối hoặc trì hoãn tải vượt quá năng lực có thể phục vụ an toàn.

Một load balancer chỉ là một thành phần trong hệ thống phân phối tải. Nó không tự sửa được truy vấn DB chậm, khóa tranh chấp, hot key, queue consumer không đủ năng lực hoặc dependency bên ngoài bị giới hạn.

### Một request đi qua những đâu?

~~~mermaid
flowchart LR
    U["Client"] --> CDN["DNS / CDN / WAF"]
    CDN --> LB["Load balancer / API gateway"]
    LB --> APP["API replicas"]
    APP --> CACHE["Cache"]
    APP --> DB[("Database")]
    APP --> Q["Queue / broker"]
    Q --> W["Worker pool"]
    W --> DB
    DB --> EXT["External services / data stores"]
~~~

Đường đi thực tế có thể khác, nhưng mỗi hop đều có thể tạo latency, queue, lỗi và giới hạn năng lực. Khi đo hiệu năng, phải xác định cả thời gian ở từng lớp lẫn thời gian end-to-end.

## 2. Load balancing ở lớp mạng và ứng dụng

### 2.1. Load balancer làm gì?

Load balancer nhận kết nối hoặc request và chọn backend theo thuật toán cùng trạng thái sức khỏe. Nó có thể phân phối ở lớp mạng (L4) hoặc hiểu giao thức ứng dụng như HTTP (L7).

| Loại | Phạm vi | Khả năng điển hình | Điểm cần xem xét |
| --- | --- | --- | --- |
| L4 load balancing | TCP/UDP flow | Phân phối connection/flow theo địa chỉ và port | Một connection lâu dài có thể tạo skew dù số connection cân bằng |
| L7 load balancing | HTTP/gRPC request | Routing theo host, path, header, cookie, rule | Cần quản lý TLS, timeout, header, retry và request semantics |
| Global traffic management | Nhiều region/edge | Điều hướng theo health, latency, geography hoặc policy | DNS cache, failover convergence và dữ liệu giữa vùng |
| Internal load balancing | Service-to-service | Phân phối lưu lượng giữa backend nội bộ | Service discovery, identity, network policy và telemetry |

Một backend được đánh dấu unhealthy cần được loại khỏi lựa chọn theo health check đã thiết kế. Tuy nhiên health check quá sâu có thể tạo hiệu ứng dây chuyền: database chập chờn khiến mọi API pod bị đánh unhealthy dù chúng vẫn có thể phục vụ chức năng khác. Cần tách liveness, readiness và dependency health.

### 2.2. Các thuật toán phân phối phổ biến

| Thuật toán | Cách chọn backend | Ưu điểm | Hạn chế |
| --- | --- | --- | --- |
| Round robin | Lần lượt theo danh sách | Đơn giản, công bằng theo số request khi tải tương tự | Không hiểu chi phí request và trạng thái backend |
| Weighted round robin | Theo trọng số cấu hình | Phù hợp backend có capacity khác nhau | Trọng số tĩnh có thể lỗi thời khi tải biến động |
| Least connections | Ưu tiên backend ít connection | Hữu ích với connection có thời gian sống khác nhau | Số connection không luôn phản ánh mức CPU/chi phí request |
| Least requests / least outstanding | Ưu tiên backend ít request đang xử lý | Có thể thích ứng với request dài/ngắn | Phụ thuộc cách đếm và thông tin đang xử lý |
| Random / power of two choices | Chọn ngẫu nhiên, có thể so sánh hai backend | Giảm tập trung và dễ mở rộng thuật toán | Không thay thế health/capacity policy |
| Consistent hashing | Ánh xạ key về backend ổn định | Giữ locality/cache affinity, giảm remapping | Hot key vẫn dồn vào một backend |
| Latency/health-aware | Ưu tiên backend theo tín hiệu quan sát | Có thể tránh backend suy giảm | Telemetry trễ/noisy gây dao động hoặc feedback loop |

Không có thuật toán tốt nhất trong mọi trường hợp. Round robin có thể phù hợp với API stateless và request tương đối đồng đều; least outstanding có thể phù hợp với công việc có thời gian xử lý biến động. Hashing hữu ích khi cần locality, nhưng phải xử lý hot key riêng.

### 2.3. Sticky session và tính stateless

Sticky session cố định một client vào một backend trong một khoảng thời gian. Nó có thể giữ cache/session local và tương thích với ứng dụng legacy, nhưng làm mất khả năng phân phối đều khi một số client có hoạt động nặng hơn, giảm linh hoạt khi backend lỗi hoặc scale.

Với hệ thống cloud cần mở rộng, nên ưu tiên session/data bên ngoài process (ví dụ session store hoặc token stateless có kiểm soát) để backend có thể thay thế. Nếu vẫn cần affinity, xác định TTL, hành vi khi backend chết và cách không làm dữ liệu phiên bị mất.

## 3. Phân phối tải không đồng nghĩa chia đều request

Đếm số request đến mỗi replica không đủ để kết luận tải cân bằng. Một request tìm kiếm nhẹ có thể tốn 5 ms, trong khi request tạo báo cáo tốn 5 giây và gấp nhiều lần CPU/IO. Một tenant có thể gửi ít request nhưng truy vấn rất đắt.

Nên xem xét:

- **Request rate:** số request/giây.
- **Concurrency/in-flight requests:** số công việc đang xử lý.
- **Resource cost:** CPU, memory, IO, connection, network hoặc thời gian xử lý.
- **Latency distribution:** p50, p95, p99 thay vì chỉ trung bình.
- **Queue age:** công việc cũ nhất đang chờ bao lâu.
- **Error/rejection rate:** backend có phải từ chối, timeout hoặc retry không.
- **Fairness:** một nhóm tenant hoặc luồng ưu tiên có chiếm tài nguyên của nhóm khác không.

### Ví dụ đơn giản

Hai backend nhận cùng 100 request/giây. Backend A xử lý request trung bình 10 ms; backend B nhận nhiều request nặng trung bình 300 ms. Số request bằng nhau nhưng thời gian CPU, connection và số công việc đồng thời có thể khác đáng kể.

Định luật Little mô tả quan hệ trong một hệ thống ổn định:

\[
L = \lambda W
\]

Trong đó:

- \(L\): số công việc trung bình đang ở trong hệ thống (in-flight hoặc queue, tùy ranh giới đo).
- \(\lambda\): throughput trung bình (công việc/giây).
- \(W\): thời gian trung bình một công việc ở trong hệ thống (giây).

Ví dụ với throughput 200 request/giây và thời gian trong hệ thống 0,25 giây, số request trung bình đang hiện diện ở ranh giới đó xấp xỉ 50. Nếu latency tăng trong khi throughput không tăng, số request in-flight và áp lực bộ nhớ/connection có thể tăng nhanh.

Đây là quan hệ cho hệ thống ổn định theo định nghĩa ranh giới phù hợp; không dùng để suy ra trực tiếp capacity tối đa hoặc bỏ qua phân phối latency.

## 4. Skew là gì?

**Skew** là sự phân bố không đồng đều của tải, dữ liệu hoặc thời gian xử lý giữa các thành phần. Một số node/partition/tenant nhận hoặc xử lý nhiều hơn đáng kể so với phần còn lại.

Skew thường xuất hiện khi:

- Một key rất phổ biến (hot key) nhận phần lớn request/event.
- Hash hoặc partition key không phân bố đều.
- Một tenant có tải cao hơn nhiều tenant khác.
- Một partition lưu nhiều dữ liệu hoặc truy vấn tốn kém hơn.
- Một vùng/availability zone có phần lớn user hoặc đường mạng tốt hơn.
- Job có kích thước hoặc độ phức tạp dữ liệu khác nhau nhưng được chia đều theo số lượng record.
- Cache key có cardinality/độ phổ biến lệch; cache miss tập trung vào một số object.

### 4.1. Phân biệt skew với quá tải tổng thể

| Hiện tượng | Dấu hiệu | Hướng xử lý ban đầu |
| --- | --- | --- |
| Tổng tải vượt capacity | Hầu hết backend đều saturation | Scale đúng tầng, admission control, tối ưu công việc |
| Skew | Một vài backend/partition rất nóng, phần khác nhàn | Điều chỉnh key/partition, phân tán hot workload |
| Dependency bottleneck | Nhiều backend cùng chờ DB/API ngoài | Tối ưu dependency, pool, cache hoặc giới hạn concurrency |
| Queue backlog | Producer nhanh hơn consumer | Scale consumer, tối ưu sink, backpressure |
| Thundering herd | Nhiều request đồng loạt tới một tài nguyên | Request coalescing, jitter, cache, rate limit |

Scale toàn hệ thống khi chỉ một partition nóng có thể làm tăng chi phí mà không giảm bottleneck. Cần tìm skew trước khi tăng capacity.

## 5. Hot key, hot partition và chiến lược partitioning

### 5.1. Hot key

Trong cache, database hoặc broker, một key được truy cập quá thường xuyên có thể trở thành điểm nóng. Ví dụ một trang sự kiện phổ biến, một mã khuyến mãi hoặc một tenant lớn nhận tỷ lệ request vượt xa các key khác.

Biện pháp tùy loại dữ liệu:

- Cache bản sao đọc-only tại nhiều node/edge nếu tính nhất quán cho phép.
- Dùng local cache có TTL ngắn kết hợp cache trung tâm.
- Tách luồng đọc và ghi nếu workload cho phép.
- Với phép đếm tăng liên tục, chia counter thành nhiều shard rồi cộng hợp nhất.
- Throttle hoặc quota riêng cho key/tenant nóng.
- Precompute/materialize kết quả thay vì tính lại trên mọi request.

Không thể nhân bản tùy tiện dữ liệu có ghi cạnh tranh hoặc cần thứ tự toàn cục. Với inventory hoặc số lượng chỗ còn lại, phân tán counter có thể gây overselling nếu không có giao thức giữ chỗ/đồng bộ đúng.

### 5.2. Hot partition trong stream/broker

Nếu message được partition theo key và một key chiếm phần lớn sự kiện, một partition có thể quá tải trong khi các partition khác nhàn. Thêm consumer không giải quyết nếu số partition hoặc phân phối key là giới hạn.

Các lựa chọn:

- Chọn partition key có cardinality và phân bố phù hợp, đồng thời giữ đúng phạm vi ordering.
- Với workload cần tổng hợp, có thể chia key nóng thành sub-key/shard rồi aggregate sau; phải thiết kế thứ tự/nhất quán.
- Tách tenant lớn hoặc luồng ưu tiên sang topic/partition/cell riêng nếu lợi ích đủ lớn.
- Theo dõi bytes/messages per partition và consumer lag theo từng partition, không chỉ tổng topic.
- Kiểm soát partition count, replication và retention theo throughput cùng recovery time.

Ví dụ, partition theo tenant_id giữ thứ tự của tenant nhưng một tenant lớn có thể tạo hot partition. Thêm random suffix giúp phân tán ghi nhưng làm mất thứ tự tenant toàn cục; nếu cần thứ tự theo booking, dùng booking_id hoặc một khóa hẹp hơn.

### 5.3. Chọn partition key

Một key tốt cân bằng bốn mục tiêu:

1. **Phân bố:** tránh một số key chiếm phần lớn tải.
2. **Ordering:** giữ thứ tự ở đúng phạm vi nghiệp vụ cần.
3. **Locality:** dữ liệu thường truy vấn cùng nhau được đặt gần nhau.
4. **Operability:** có thể di chuyển, split, merge và xử lý hot shard.

Không có key hoàn hảo cho mọi kiểu truy vấn. Partition theo customer_id có thể tốt cho truy vấn khách hàng nhưng xấu cho báo cáo theo thời gian hoặc một tenant rất lớn. Có thể cần nhiều read model/index hoặc data layout riêng thay vì cố tối ưu mọi truy vấn bằng một partition key.

## 6. Tenant skew và noisy neighbor

Trong SaaS multi-tenant, tổng tải có thể có phân bố long-tail: phần lớn tenant nhỏ và một số ít tenant cực lớn. Nếu tất cả cùng dùng connection pool, queue hoặc database, tenant lớn có thể làm giảm SLO của tenant khác.

### Các lớp bảo vệ

- **Quota:** giới hạn request/giây, concurrency, dung lượng, số job hoặc số kết nối theo tenant.
- **Fair scheduling:** chia lượt xử lý hoặc trọng số giữa tenant.
- **Bulkhead:** tách pool, queue, worker hoặc thread/resource cho workload khác nhau.
- **Priority class:** bảo vệ tác vụ quan trọng, tránh để batch/analytics chiếm capacity giao dịch.
- **Cell architecture:** chia tenant thành nhóm có compute/data isolation để giới hạn blast radius.
- **Dedicated tier:** đưa tenant cực lớn sang tài nguyên riêng khi yêu cầu và economics chứng minh cần thiết.

~~~mermaid
flowchart TB
    GW["Gateway + tenant-aware limits"] --> SCHED["Fair scheduler"]
    SCHED --> C1["Pool / Cell A"]
    SCHED --> C2["Pool / Cell B"]
    SCHED --> D["Dedicated tier"]
    C1 --> DB1[("Data A")]
    C2 --> DB2[("Data B")]
    D --> DB3[("Dedicated data")]
~~~

Cần tính hạn mức theo workload thực tế, không chỉ số request. Một tenant có thể gửi 100 request rất đắt; tenant khác gửi 1.000 request cache hit rất nhẹ.

Quota nên có hành vi rõ khi vượt ngưỡng: trả 429/Retry-After, trì hoãn job, giảm chất lượng tính năng phụ trợ hoặc đưa sang queue riêng. Đừng tự động trả lỗi chung hoặc làm ảnh hưởng tenant không liên quan.

## 7. Queueing và backpressure để hấp thụ biến động

Queue tách tốc độ producer và consumer trong thời gian ngắn. Nó giúp hấp thụ burst, nhưng không tạo capacity xử lý vô hạn.

~~~mermaid
flowchart LR
    P["Producers"] --> Q["Queue / broker"]
    Q --> W1["Worker 1"]
    Q --> W2["Worker 2"]
    Q --> W3["Worker N"]
    W1 --> S["Sink / database"]
    W2 --> S
    W3 --> S
    S --> M["Metrics: age, lag, throughput, errors"]
~~~

Các chính sách cần thiết:

- **Bounded queue:** có giới hạn dung lượng/thời gian; tránh backlog không kiểm soát.
- **Backpressure:** giảm tốc độ producer hoặc điều tiết admission khi consumer không theo kịp.
- **Retry with backoff/jitter:** giảm retry đồng loạt; lỗi không thể phục hồi cần DLQ.
- **Visibility/ack timeout:** đủ dài cho công việc, có heartbeat/extend nếu phù hợp; xử lý duplicate bằng idempotency.
- **Concurrency limit:** giới hạn số worker đồng thời theo capacity của sink/dependency.
- **Priority/fairness:** tách luồng khẩn cấp khỏi batch dài và tránh tenant chiếm toàn queue.
- **Queue age alert:** cảnh báo theo thời gian chờ cũ nhất và SLA, không chỉ theo số lượng message.

### Tính backlog

Giả sử producer tạo 1.200 job/giây, worker pool xử lý 900 job/giây. Backlog tăng 300 job/giây. Sau 15 phút:

\[
B = (1{,}200 - 900)\times 900 = 270{,}000\text{ jobs}
\]

Nếu producer dừng, worker tiếp tục xử lý 900 job/giây thì riêng backlog này cần khoảng 300 giây (5 phút), chưa tính thời gian xử lý thay đổi theo tải và lỗi retry.

Để backlog giảm trong khi producer vẫn hoạt động, throughput consumer phải lớn hơn producer. Ví dụ scale worker lên 1.500 job/giây thì backlog giảm khoảng 300 job/giây, với giả định năng suất ổn định và sink chịu được tải.

## 8. Tìm bottleneck theo phương pháp có hệ thống

### 8.1. Quan sát bốn tín hiệu vàng

Một cách sàng lọc phổ biến là quan sát:

- **Latency:** thời gian phản hồi, phân bố p50/p95/p99 và theo endpoint/tenant/region.
- **Traffic:** request rate, throughput, concurrency và kích thước payload.
- **Errors:** HTTP 4xx/5xx, timeout, retry, rejected job và lỗi dependency.
- **Saturation:** mức sử dụng/độ đầy của tài nguyên như CPU, memory, disk, network, thread, connection pool và queue.

Không kết luận bottleneck chỉ từ CPU cao hoặc thấp. API CPU thấp nhưng p99 rất cao có thể đang chờ database lock, network hoặc pool connection.

### 8.2. Phân rã latency theo hop

~~~mermaid
flowchart LR
    A["Client / DNS / TLS"] --> B["CDN / WAF / Gateway"]
    B --> C["Load balancer"]
    C --> D["API processing"]
    D --> E["Cache / DB / broker"]
    E --> F["External dependency"]
    F --> G["Response"]
~~~

Trong trace, đo span theo từng thành phần. Tổng thời gian có thể bao gồm queueing, service time, serialization, network và retry. Một dependency chỉ chiếm 20 ms trung bình nhưng thỉnh thoảng 2 giây có thể chi phối p99.

### 8.3. Bảng tín hiệu và giả thuyết bottleneck

| Tín hiệu | Giả thuyết | Điều tra tiếp |
| --- | --- | --- |
| CPU cao, throughput không tăng | CPU-bound, lock contention hoặc quá nhiều serialization | Profile, flame graph, thread state, lock |
| CPU thấp, latency cao | Chờ I/O, DB, network, connection pool | Distributed trace, pool wait, query latency |
| Memory tăng đều | Leak, cache không giới hạn, object retention | Heap profile, GC, cache cardinality |
| DB connection pool cạn | Query chậm, leak connection, concurrency cao | Active/idle/wait, query plan, timeout |
| DB CPU/IO cao | Scan lớn, index thiếu, lock, write contention | Query plan, slow query, index/partition |
| Một partition lag cao | Hot key, consumer skew, poison message | Metrics theo partition/key, event age |
| Network retransmit/packet loss | Congestion, MTU, routing hoặc dependency xa | Network telemetry, flow logs, path test |
| 429/503 tăng | Quota, admission control hoặc backend capacity | Rate limit metrics, autoscaling, provider quota |
| Latency tăng sau autoscale | Warm-up, cold start, cache cold, DB connection storm | Scale timeline, startup, connection burst |
| Chỉ một tenant chậm | Tenant skew, query pattern, quota hoặc data volume | Segment latency/cost theo tenant |
| Cache miss đột biến | Deploy/purge, key fragmentation, TTL đồng loạt | Hit ratio theo key/path/PoP, invalidation |
| Worker throughput thấp | CPU/IO, dependency, batch size hoặc concurrency | Profile, queue age, sink latency |

### 8.4. Đừng bỏ qua coordinated omission và tail latency

Một load test chỉ gửi request mới sau khi request trước hoàn tất có thể đánh giá thấp latency khi hệ thống bị chậm, vì nó ngừng tạo tải trong lúc chờ. Cần chọn công cụ/kiểu tải có mô hình arrival rate phù hợp mục tiêu kiểm thử và đọc cách công cụ tính histogram.

Đừng chỉ xem trung bình. Nếu p50 là 80 ms nhưng p99 là 2 giây, một nhóm người dùng có trải nghiệm rất tệ dù trung bình nhìn tốt. Phân tích theo route, tenant, vùng, request size và dependency để tìm nguồn tail latency.

## 9. Xử lý bottleneck theo đúng tầng

### 9.1. Edge, gateway và load balancer

Nếu điểm nghẽn ở gateway/edge:

- Kiểm tra connection limit, TLS handshakes, request body size, WAF rule và rate limit.
- Bật keep-alive/connection reuse phù hợp và tránh tạo connection mới cho mọi request.
- Điều chỉnh timeout/deadline xuyên suốt; timeout gateway phải tương thích với deadline backend.
- Tách API public, private và workload có ưu tiên khác nhau.
- Xem xét CDN/cache cho static và public read-only content; bypass dữ liệu riêng tư.

### 9.2. Compute/application

Nếu service CPU-bound:
- Profile để tối ưu phần tốn CPU thực sự; giảm serialization, algorithm cost hoặc xử lý lặp.
- Tăng replica khi workload stateless và dependency đủ capacity.
- Dùng async I/O hoặc concurrency có giới hạn; không tạo thread/task vô hạn.
- Tách workload CPU-heavy khỏi API latency-sensitive.
- Right-size request/limit và kiểm tra throttling.

Nếu memory-bound:
- Giới hạn cache, queue trong process và buffer; thiết kế eviction.
- Phân tích heap/GC và object lifetime.
- Tránh tải toàn bộ dataset vào RAM nếu có thể stream/partition.
- Kiểm tra memory limit/OOM và headroom khi rollout.

### 9.3. Database

Database thường trở thành bottleneck khi ứng dụng scale nhanh hơn khả năng đọc/ghi:

- Tối ưu query plan, index và truy vấn N+1.
- Giới hạn connection pool trên mỗi replica; tổng kết nối từ tất cả replica phải nằm trong capacity database.
- Dùng read replica/read model cho workload đọc có thể chịu replication lag.
- Partition/shard khi dữ liệu và throughput cần phân tán, nhưng xác định key và transaction boundary trước.
- Batch write, queue write hoặc bulk operation để giảm overhead khi phù hợp.
- Cache dữ liệu hot/read-only với invalidation và freshness policy rõ.
- Tách analytics/reporting ra khỏi đường giao dịch nếu chúng cạnh tranh tài nguyên.

Không tăng pool connection vô hạn. Quá nhiều connection có thể làm DB tốn bộ nhớ và context switching, khiến latency tệ hơn.

### 9.4. Network và dependency ngoài

- Đo DNS, connect, TLS, TTFB và thời gian xử lý dependency.
- Đặt timeout/deadline theo ngân sách end-to-end.
- Retry có exponential backoff và jitter; chỉ retry thao tác idempotent hoặc có idempotency key.
- Circuit breaker/bulkhead để dependency chậm không làm cạn tài nguyên toàn hệ thống.
- Dùng cache hoặc async flow khi business semantics cho phép.
- Đàm phán quota/limit với provider và monitor rate-limit response.

### 9.5. Queue và worker

- Tăng consumer theo throughput và queue age, không chỉ CPU.
- Chọn batch size phù hợp; batch quá lớn tăng memory/latency và làm retry tốn kém.
- Tách loại job có thời gian xử lý khác nhau; tránh job dài chặn job ngắn.
- Xử lý poison message, retry storm, DLQ và duplicate.
- Bảo vệ sink bằng concurrency limit và bulkhead.
- Có khả năng pause producer hoặc giảm admission khi sink đang quá tải.

## 10. Autoscaling không thể thay thế capacity engineering

Autoscaling giúp điều chỉnh số replica theo tín hiệu tải, nhưng cần hiểu cả độ trễ phản ứng và giới hạn dependency.

### 10.1. Scale ngang và scale dọc

| Hướng | Cách làm | Phù hợp | Giới hạn |
| --- | --- | --- | --- |
| Scale up | Tăng CPU/RAM/IOPS cho instance | Workload khó chia nhỏ, cần tài nguyên lớn hơn | Trần instance, chi phí tăng, có thể phải restart |
| Scale out | Thêm replica/node/partition | Workload có thể phân phối và ít state local | Dependency, coordination và data partition có thể thành bottleneck |

Nên scale theo bottleneck: service CPU-bound có thể scale out; database write-bound có thể cần tối ưu schema/partition hoặc thay đổi data flow thay vì thêm API pod.

### 10.2. Autoscaling signals

- CPU/memory cho workload tương ứng.
- Request rate hoặc in-flight concurrency cho API.
- Queue age, lag hoặc backlog cho worker.
- Custom business metric khi CPU không phản ánh demand.
- Node capacity, pending pods và regional quota để phát hiện thiếu compute.

Cấu hình scale cần min/max, cooldown/stabilization, scale-up policy, scale-down behavior, warm capacity và giới hạn dependency. Autoscaling theo CPU có thể trễ nếu queue tăng rất nhanh; dùng queue age hoặc predictive/pre-warming khi có mùa vụ rõ.

### 10.3. Connection storm khi scale-out

Khi thêm nhiều replica, mỗi replica có thể tạo pool DB mới. Nếu pool tối đa là 50 và hệ thống scale lên 100 replica, lý thuyết có thể tạo tối đa 5.000 kết nối. DB có thể quá tải ngay khi API autoscaling thành công.

Phải tính tổng connection budget trên toàn hệ thống, gồm worker, migration, admin và ứng dụng khác. Dùng pool proxy, giới hạn per-instance, connection reuse và kiểm soát rollout nếu phù hợp.

## 11. Cache và phân phối tải đọc

Cache có thể giảm tải database nhưng cũng tạo skew và rủi ro stale:

- Một key nóng có thể đánh vào một cache node nếu không có replication hoặc sharding phù hợp.
- TTL đồng nhất có thể làm nhiều key hết hạn cùng lúc.
- Cache miss hàng loạt khi deploy/purge có thể tạo thundering herd lên origin.
- Cache quá nhiều biến thể làm phân mảnh và giảm hit ratio.
- Negative caching có thể giữ lỗi quá lâu nếu cấu hình không phù hợp.

Biện pháp:
- Jitter TTL, request coalescing/single-flight và stale-while-revalidate khi an toàn.
- Replicate popular read-only values hoặc edge caching phù hợp.
- Giới hạn cardinality và memory; eviction policy có quan sát.
- Invalidation theo phiên bản nội dung hoặc event khi phù hợp.
- Fallback có kiểm soát nếu cache lỗi; không biến cache thành source of truth.

Với dữ liệu tồn kho hoặc trạng thái thanh toán, chỉ cache trong giới hạn freshness được nghiệp vụ phê duyệt. Một cache hit nhanh nhưng trả sai trạng thái có thể gây tổn thất lớn hơn latency cao.

## 12. Load shedding, rate limiting và admission control

Khi hệ thống vượt ngưỡng capacity, cố gắng nhận tất cả request thường làm toàn bộ dịch vụ chậm và thất bại. Admission control chọn công việc nào được nhận, trì hoãn hoặc từ chối.

- **Rate limiting:** giới hạn tốc độ theo user, tenant, API key, IP hoặc endpoint.
- **Concurrency limiting:** giới hạn số request/job đang chạy.
- **Load shedding:** từ chối request ít ưu tiên hoặc không thiết yếu khi quá tải.
- **Priority queue:** giữ năng lực cho giao dịch quan trọng.
- **Graceful degradation:** tắt gợi ý, analytics hoặc tính năng phụ trợ để bảo vệ checkout.
- **Retry-After/backoff:** giúp caller giảm tốc thay vì retry ngay.

~~~mermaid
flowchart TD
    R["Incoming requests"] --> A["Authenticate + classify"]
    A --> Q{"Quota / concurrency available?"}
    Q -->|"Có"| P["Admit request"]
    Q -->|"Không"| I{"Request priority?"}
    I -->|"Critical"| W["Wait bounded / reserved capacity"]
    I -->|"Best effort"| S["Shed / 429 + Retry-After"]
    P --> APP["Application"]
    W --> APP
~~~

Rate limit không nên chỉ dựa vào IP khi nhiều người dùng hợp lệ cùng chia sẻ NAT. Với SaaS, tenant-aware quota công bằng hơn nếu tenant context đã được xác thực.

Không retry vô hạn khi nhận 429/503. Retry storm có thể biến một sự cố nhỏ thành quá tải kéo dài.

## 13. Reliability: bulkhead, circuit breaker và graceful degradation

| Cơ chế | Mục tiêu | Ví dụ |
| --- | --- | --- |
| Bulkhead | Giới hạn sự cố/tài nguyên trong một vùng | Pool riêng cho report và checkout |
| Circuit breaker | Ngăn gọi liên tục dependency đang lỗi | Dừng tạm request tới payment provider sau ngưỡng lỗi |
| Timeout/deadline | Ngăn request chờ vô hạn | API chỉ chờ dependency trong phần ngân sách còn lại |
| Backpressure | Điều tiết tốc độ downstream | Worker giảm concurrency khi DB lag |
| Retry + jitter | Thử lại lỗi tạm thời mà không đồng loạt | Retry theo exponential backoff có giới hạn |
| Graceful degradation | Giữ đường nghiệp vụ cốt lõi | Tắt recommendation khi search backend quá tải |
| Health-aware routing | Tránh backend thực sự không sẵn sàng | Readiness kiểm tra khả năng nhận traffic |

Circuit breaker có trạng thái open/half-open/closed theo cách triển khai phổ biến; cần tránh probe quá dồn và tránh mở breaker chỉ vì một vài lỗi transient. Health-aware routing cũng cần hysteresis để không liên tục thêm/bớt backend khi metric dao động.

## 14. Kiểm thử tải và tìm giới hạn hệ thống

Một kế hoạch kiểm thử nên trả lời: hệ thống đáp ứng bao nhiêu tải với SLO đã định, bottleneck nằm ở đâu và hành vi khi vượt capacity là gì?

### 14.1. Các dạng test

- **Load test:** tải kỳ vọng trong điều kiện bình thường.
- **Stress test:** tăng dần đến khi hệ thống không còn đáp ứng mục tiêu.
- **Spike test:** tăng tải đột ngột để đánh giá autoscaling, queue và cache cold.
- **Soak test:** chạy lâu để tìm leak, backlog accumulation, GC hoặc resource exhaustion.
- **Concurrency test:** nhiều request đồng thời, tranh chấp cùng key/record.
- **Failover/fault test:** node/zone/dependency lỗi trong lúc tải.
- **Skew test:** phân bố key/tenant/partition lệch như production hoặc tệ hơn.

### 14.2. Workload model

Cần mô phỏng phân bố endpoint, payload size, read/write mix, tenant mix, cache hit, session, think time và hành vi retry. Một test chỉ bắn cùng một endpoint với dữ liệu nhỏ có thể bỏ sót hot key, DB lock hoặc network egress.

### 14.3. Tiêu chí nghiệm thu

| Nhóm | Chỉ số |
| --- | --- |
| Hiệu năng | p50/p95/p99 theo endpoint và tenant |
| Throughput | Requests/jobs/events per second |
| Độ ổn định | Error rate, timeout, retry, rejected requests |
| Tài nguyên | CPU, memory, GC, disk/network, connection pool |
| Queue | Lag, oldest age, backlog drain time |
| Data | Duplicate, ordering, reconciliation, consistency |
| Cost | Chi phí trên 1.000 request/job và tải peak |
| Reliability | Recovery time, availability, blast radius |

Không chỉ ghi kết quả tốt nhất. Lưu cấu hình, phiên bản, dữ liệu, warm/cold cache, vị trí test, thời gian và lỗi đã xảy ra để có thể so sánh lần sau.

## 15. Tình huống thực tế: nền tảng đặt chỗ bị chậm khi chiến dịch

### 15.1. Triệu chứng

Trong chiến dịch bán hàng, hệ thống có:
- p95 checkout tăng từ 250 ms lên 1,8 giây.
- CPU API trung bình chỉ khoảng 45%.
- Database CPU 90%, connection pool wait tăng.
- Một tenant doanh nghiệp tạo nhiều truy vấn báo cáo.
- Queue notification backlog tăng, nhưng người dùng vẫn đặt chỗ thành công.
- Một broker partition nhận phần lớn event do key phân vùng theo tenant_id.

Các số liệu là giả định cho bài tập. Không thể kết luận chỉ từ chúng; cần trace, query plan và metrics theo partition để xác định quan hệ nhân quả.

### 15.2. Phân tích nguyên nhân

| Triệu chứng | Giả thuyết | Phép kiểm chứng |
| --- | --- | --- |
| API CPU thấp, p95 cao | API chờ DB connection/query | Trace span, pool wait, DB query latency |
| DB CPU 90% | Report query tranh chấp với checkout | Query plan, top SQL, lock/IO |
| Một tenant tạo report nặng | Tenant skew/noisy neighbor | Metrics theo tenant, query cost |
| Queue notification lag | Consumer thấp hơn producer hoặc partition skew | Per-partition lag, worker throughput |
| Tenant_id làm partition key | Tenant lớn dồn event vào một partition | Messages/bytes per partition |

### 15.3. Biện pháp theo thứ tự

1. **Bảo vệ checkout:** giới hạn/report concurrency và chuyển batch report sang giờ thấp điểm; đặt pool/priority riêng nếu có thể.
2. **Giảm áp lực DB:** tối ưu query plan/index, chuyển báo cáo sang read replica hoặc analytical projection khi tính nhất quán cho phép.
3. **Kiểm soát tenant skew:** quota theo chi phí/concurrency; tách tenant lớn khỏi pool hoặc cell khi cần.
4. **Sửa partitioning:** chọn key hẹp hơn như booking_id nếu ordering theo booking là yêu cầu; hoặc tách tenant lớn sang topic/cell riêng. Kiểm tra ảnh hưởng khi đổi partition count.
5. **Xử lý queue backlog:** scale consumer trong giới hạn sink, phân tách notification priority và theo dõi oldest age; không để notification làm chậm giao dịch.
6. **Kiểm thử lại:** chạy chiến dịch giả lập với key distribution lệch, đo p95 checkout, DB load, per-partition lag và cost.

Không nhất thiết triển khai mọi biện pháp cùng lúc. Thay đổi từng nhóm có thể đo được giúp tránh che lấp nguyên nhân và tạo thêm rủi ro.

### 15.4. Sơ đồ sau điều chỉnh

~~~mermaid
flowchart TB
    U["Clients"] --> GW["Gateway: auth + tenant quota"]
    GW --> API["Checkout API pool"]
    GW --> SEARCH["Search API pool"]
    API --> TXDB[("Transactional DB")]
    REPORT["Report jobs"] --> RQ["Low-priority queue"]
    RQ --> RW["Report workers"]
    RW --> REPLICA[("Read replica / analytics model")]
    API --> EVT["Booking events"]
    EVT --> NQ["Notification topic"]
    NQ --> NW["Notification workers"]
    API -. "SLO / trace / saturation" .-> OBS["Observability"]
    RW -. "Lag / cost / tenant metrics" .-> OBS
    NW -. "Lag / retries" .-> OBS
~~~

## 16. Từ phân phối tải tới capacity planning và TCO

Capacity planning cần ước tính không chỉ trung bình mà cả đỉnh, burst, tăng trưởng và lỗi thành phần:

- Số user/request đồng thời và phân bố endpoint.
- Request/job cost và thời gian xử lý.
- Mức sử dụng database, connection, storage, network và broker.
- Dự phòng khi mất một node/AZ hoặc một nhóm backend.
- Thời gian autoscaling và image startup.
- Backlog cần hấp thụ trong thời gian dependency gián đoạn.
- Chi phí idle capacity để giữ SLO và chi phí khi peak/DR.

Một cách lập mô hình:

\[
C_{\text{required}} \geq
\frac{\lambda_{\text{peak}}\times W_{\text{service}}}{U_{\text{target}}}
\]

Trong đó \(\lambda_{\text{peak}}\) là tốc độ công việc đỉnh, \(W_{\text{service}}\) là mức tài nguyên trung bình cần cho một đơn vị công việc (phải định nghĩa đúng đơn vị), và \(U_{\text{target}}\) là mức sử dụng mục tiêu. Công thức chỉ là mô hình ước lượng giản lược; sizing thực tế phải xét concurrency, resource vector, tail latency, dependency và failure headroom.

TCO cần tính compute, load balancer, cache, database, broker, network egress, observability, license, dự phòng, vận hành và chi phí sự cố. Cân bằng tải tốt có thể giảm lãng phí, nhưng thêm nhiều cache shard, queue, replica hoặc cell cũng làm tăng chi phí nền.

## 17. Architecture Decision Record mẫu

~~~markdown
# ADR-061: Phân phối tải và cô lập workload của nền tảng đặt chỗ

Trạng thái: Đề xuất / chấp thuận có điều kiện
Decision owner: Architecture lead + SRE + Product
Ngày: YYYY-MM-DD

Bối cảnh:
- Checkout p95 tăng mạnh trong chiến dịch.
- Report workload của một tenant chiếm DB capacity.
- Notification stream có partition skew.
- Yêu cầu bảo vệ SLO checkout và fairness giữa tenant.

Phương án:
A. Tăng toàn bộ API/DB capacity.
B. Giới hạn report concurrency, tách read workload,
   điều chỉnh partition key và quota theo tenant.
C. Tách toàn bộ tenant thành dedicated deployment.

Quyết định đề xuất:
- Thực hiện B theo từng bước và đo sau mỗi thay đổi.
- Cân nhắc dedicated cell cho tenant lớn nếu quota/read model
  không đủ giới hạn blast radius.

Đánh đổi:
- Thêm quota, routing, read model và vận hành queue.
- Thay đổi partition key có thể cần migration/replay.

Bằng chứng nghiệm thu:
- Checkout p95/p99 và error rate ở tải đỉnh.
- DB connection wait/CPU/IO giảm trong khi report vẫn đạt SLA.
- Per-partition lag cân bằng hơn; notification age đạt mục tiêu.
- Không tăng duplicate hoặc mất thứ tự nghiệp vụ.
- TCO/chi phí mỗi giao dịch nằm trong ngân sách.

Điều kiện xem xét lại:
- Tải/tenant distribution thay đổi lớn;
  SLO không đạt; hot partition còn tồn tại;
  chi phí cell/read model vượt ngưỡng.
~~~

ADR cần lưu workload profile, trace/query evidence, cost model, giả định và rủi ro còn lại. Chấp thuận thay đổi chỉ sau khi có phương án rollback và kiểm thử phù hợp.

## 18. Sai lầm thường gặp

| Sai lầm | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Chỉ cân bằng số request | Request nặng tập trung vào một backend | Đo concurrency, service time, resource cost và latency |
| Scale API khi bottleneck ở DB | Tăng connection và tải lên DB | Tìm bottleneck theo trace và dependency |
| Chọn consistent hashing để xử lý hot key | Key nóng vẫn ánh xạ một nơi | Replicate/read cache, shard key hoặc isolate hot workload |
| Thêm partition nhưng không xét ordering | Thay đổi thứ tự hoặc key mapping | Ghi rõ ordering scope và migration plan |
| Queue không giới hạn | Backlog/retention/storage cạn | Bounded queue, backpressure và admission control |
| Retry ngay khi lỗi | Retry storm và làm dependency quá tải hơn | Exponential backoff, jitter, retry budget |
| Pool connection quá lớn ở mọi replica | Database cạn connection | Tính tổng connection budget, pool proxy và per-instance cap |
| Autoscale quá nhanh/không ổn định | Oscillation, cold start và cache/DB storm | Stabilization, warm capacity, scale policy |
| Chỉ theo dõi CPU | Bỏ qua IO, lock, queue age và network | Metrics theo tầng và distributed tracing |
| Dùng IP limit cho SaaS | Nhiều người dùng hợp lệ chung NAT bị block | Tenant/user-aware quotas |
| Cùng queue cho job quan trọng và batch dài | Job ngắn bị chặn bởi job dài | Priority queue, worker pool/bulkhead |
| Cache dữ liệu nhất quán mạnh vô thời hạn | Trả trạng thái cũ gây sai nghiệp vụ | Freshness policy, invalidation và source of truth |
| Chỉ kiểm thử tải trung bình | Không thấy spike, skew hoặc tail latency | Stress, spike, soak, skew và fault tests |
| Chọn cell/dedicated quá sớm | Chi phí vận hành cao | Dựa trên đo lường, trigger và lợi ích cô lập |

## 19. Bài tập thực hành

Một nền tảng đặt chỗ có 40 API replica và 12 worker. Trong giờ cao điểm, p99 checkout vượt 2 giây dù CPU API dưới 60%. Database connection pool thường xuyên chờ; một tenant chiếm gần một nửa truy vấn báo cáo. Queue có 24 partition nhưng 3 partition chiếm 70% message. Chiến dịch sắp tới dự kiến tăng traffic gấp ba lần.

Hãy thực hiện:

1. Vẽ request path và data flow từ client tới API, cache, DB, queue, worker và external dependency.
2. Liệt kê ít nhất sáu giả thuyết bottleneck; với mỗi giả thuyết ghi metric và phép kiểm chứng.
3. Xác định skew ở tenant, query, queue partition hay backend; phân biệt tổng quá tải và lệch tải.
4. Đề xuất quota/fair scheduling cho tenant lớn và cơ chế bảo vệ checkout khỏi report workload.
5. Chọn partition key cho booking event; giải thích ordering scope và cách xử lý hot tenant.
6. Thiết kế bounded queue, backpressure, retry budget, DLQ và scale consumer.
7. Đề xuất load shedding/rate limit khi peak vượt capacity; nêu request nào được ưu tiên hoặc suy giảm.
8. Tính backlog nếu producer và consumer chênh lệch throughput theo giả định rõ ràng.
9. Lập kế hoạch load/stress/spike/soak/skew/fault test với p95/p99, errors, queue age, DB wait và cost.
10. Viết ADR lựa chọn biện pháp, rủi ro còn lại, owner và trigger đánh giá lại.

**Tiêu chí tự đánh giá:** một giải pháp tốt chỉ ra điểm nghẽn bằng bằng chứng theo từng lớp, xử lý skew ở đúng key/tenant/partition, bảo vệ luồng nghiệp vụ cốt lõi và chứng minh thay đổi không làm tăng lỗi, mất dữ liệu hoặc chi phí quá mức.

## 20. Checklist trước khi phát hành thay đổi phân phối tải

- [ ] Có workload model theo endpoint, tenant, payload, concurrency và thời gian xử lý.
- [ ] Đã xác định SLO p95/p99, throughput, error rate và capacity headroom.
- [ ] Load balancing algorithm phù hợp với request cost và connection lifecycle.
- [ ] Health check, readiness, timeout và failover có hành vi rõ.
- [ ] Sticky session có lý do, TTL và kế hoạch khi backend lỗi.
- [ ] Partition key đáp ứng phân bố, ordering, locality và operability.
- [ ] Có dashboard per backend/partition/tenant, không chỉ metric tổng.
- [ ] Hot key, hot partition và noisy neighbor đã được kiểm thử.
- [ ] Queue bounded; backpressure, retry, DLQ và idempotency có thiết kế.
- [ ] Connection pool tổng không vượt capacity database.
- [ ] Autoscaling có min/max, stabilization, quota, warm capacity và dependency checks.
- [ ] Rate limit, fairness, load shedding và graceful degradation rõ.
- [ ] Có distributed tracing, runbook và người sở hữu từng dependency.
- [ ] Đã chạy load, stress, spike, soak, skew và fault test phù hợp.
- [ ] Đo hiệu quả trước/sau và tính TCO ở steady state, peak và DR.
- [ ] ADR ghi đánh đổi, giả định, rủi ro, rollback và điều kiện xem xét lại.

## Ghi nhớ

Phân phối tải tốt không chỉ làm số request trên mỗi máy gần bằng nhau. Nó phải phân bổ **công việc và chi phí xử lý** phù hợp, giữ công bằng giữa tenant, tránh hot key/partition, bảo vệ dependency và phản ứng đúng khi capacity bị vượt.

Hãy đi theo chuỗi **đo đường đi request → tìm saturation và tail latency → xác định skew/bottleneck → chọn biện pháp đúng tầng → kiểm thử tải và lỗi → đo lại SLO/TCO**. Scale thêm tài nguyên chỉ có giá trị khi nó giải quyết đúng giới hạn đang cản trở hệ thống.
