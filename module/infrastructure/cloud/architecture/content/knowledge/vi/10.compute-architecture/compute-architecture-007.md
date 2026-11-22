# Đặt giới hạn tài nguyên và kiểm soát nhiễu giữa các tải

Khi nhiều ứng dụng hoặc nhóm cùng chạy trên một cụm máy ảo, node container hay nền tảng compute dùng chung, một workload tăng tải đột ngột có thể chiếm CPU, bộ nhớ, I/O hoặc kết nối vượt mức dự kiến. Những workload còn lại bắt đầu chậm, timeout hoặc bị dừng dù bản thân chúng không thay đổi. Hiện tượng này thường được gọi là **noisy neighbor** — một tải “ồn” làm suy giảm chất lượng của các tải dùng chung tài nguyên.

Để kiểm soát vấn đề, kiến trúc cần xác định **ai được dùng tài nguyên nào, tối đa bao nhiêu, trong bao lâu và điều gì xảy ra khi chạm giới hạn**. Các cơ chế như quota, request/limit, concurrency limit, reservation, isolation, priority và autoscaling giúp phân bổ tài nguyên có chủ đích. Giới hạn đặt quá thấp có thể làm ứng dụng bị throttling hoặc OOM; đặt quá cao khiến một workload chiếm phần lớn năng lực và làm tăng chi phí.

Bài học thuộc phần **Kiến trúc tính toán** trong học phần thiết kế kiến trúc đám mây. Việc đặt giới hạn phải gắn với mục tiêu nghiệp vụ và SLO, đồng thời cân bằng độ tin cậy, bảo mật, khả năng mở rộng, chi phí và vận hành. Các khái niệm được trình bày từ VM, container và Kubernetes đến nền tảng serverless.

Sau bài học, bạn có thể:

- Giải thích noisy neighbor và nhận diện tranh chấp CPU, memory, disk, network, connection và quota.
- Phân biệt **request/reservation**, **limit/cap**, **quota** và **concurrency limit**.
- Chọn ranh giới isolation và mức giới hạn phù hợp với VM, container, Kubernetes và serverless.
- Ước lượng capacity, headroom, mức dự phòng và tác động của autoscaling.
- Thiết kế quan sát, cảnh báo và thử tải để chứng minh giới hạn không phá vỡ SLO.
- Đề xuất chính sách công bằng, có ưu tiên và có quy trình xử lý khi workload vượt ngân sách tài nguyên.

## 1. Noisy neighbor là gì?

Trong môi trường compute dùng chung, nhiều tiến trình hoặc workload có thể cùng cạnh tranh một hoặc nhiều tài nguyên:

- **CPU:** job tính toán nặng chiếm thời gian xử lý, khiến API khác phải chờ scheduler.
- **Memory:** tiến trình tăng heap hoặc cache, làm node thiếu RAM, gây reclaim, swap, OOM hoặc eviction.
- **Storage I/O:** job batch đọc/ghi lớn gây tăng độ trễ cho database hay workload khác trên cùng thiết bị.
- **Network:** một luồng upload/download chiếm băng thông hoặc làm tăng packet processing và connection tracking.
- **Tài nguyên runtime:** thread pool, file descriptor, process, ephemeral port, connection pool hoặc lock.
- **Giới hạn nền tảng:** quota API, số instance, số IP, số volume, request rate hoặc giới hạn dịch vụ của nhà cung cấp.

Ví dụ, một hệ thống đặt lịch có API phục vụ khách hàng và job báo cáo chạy ban đêm trên cùng nhóm node. Job báo cáo đọc hàng triệu bản ghi và nén kết quả. Nếu không có giới hạn CPU, memory và I/O, job có thể làm p95 API tăng từ 200 ms lên vài giây. Nếu job còn mở quá nhiều kết nối database, API có thể timeout dù CPU node chưa đạt 100%.

Noisy neighbor không chỉ xuất hiện giữa hai khách hàng khác nhau. Nó có thể xảy ra giữa hai microservice, giữa API và worker của cùng sản phẩm hoặc giữa workload production và batch job do chính đội vận hành triển khai.

### Phân biệt tranh chấp với thiếu capacity tổng thể

| Tình huống | Dấu hiệu | Hướng điều tra |
| --- | --- | --- |
| Noisy neighbor | Một workload tăng mạnh, tài nguyên hoặc độ trễ workload khác suy giảm tương quan | Tách tải, giới hạn, điều chỉnh priority/isolation, kiểm tra shared resource |
| Thiếu capacity tổng thể | Nhiều workload đồng thời gần bão hòa dù phân bổ tương đối hợp lý | Mở rộng capacity, tối ưu code, query và sizing |
| Nút thắt downstream | Compute còn dư nhưng API chờ DB, queue hoặc dịch vụ ngoài | Theo dõi dependency latency, connection pool, quota và retry |
| Giới hạn cấu hình quá thấp | Workload thường xuyên bị throttling/OOM trong khi node còn năng lực | Xem lại request/limit, memory sizing và policy |

Không phải mọi spike latency đều là noisy neighbor. Cần đối chiếu **workload-level metrics**, **node-level metrics** và độ trễ phụ thuộc trước khi kết luận.

## 2. Tài nguyên cần được quản lý theo nhiều lớp

Một workload có thể chạy trong VM, container, pod, process hoặc function. Mỗi lớp có giới hạn riêng; tổng năng lực của máy không đồng nghĩa mọi tiến trình đều được sử dụng toàn bộ năng lực đó.

~~~mermaid
flowchart TD
    CLOUD["Cloud account / subscription / project<br/>Service quota và ngân sách"] --> POOL["Compute pool / VM scale set / node group"]
    POOL --> NODE["Host / VM node<br/>CPU, RAM, disk, network"]
    NODE --> CG["Container / cgroup / runtime limits"]
    CG --> POD["Pod / service / process"]
    POD --> THREAD["Thread, worker, request, connection"]
    THREAD --> DEP["Database, queue, storage, external API"]
~~~

Một request chỉ được phục vụ khi **tất cả lớp cần thiết còn năng lực và không bị giới hạn**. Ví dụ pod có thể được cấp 2 CPU nhưng database chỉ cho phép 30 connection; tăng số pod lên 20 có thể làm tổng connection pool vượt giới hạn database.

| Tài nguyên | Chỉ số hữu ích | Khi tranh chấp có thể thấy |
| --- | --- | --- |
| CPU | usage, throttled time, load, run queue, steal time | Request chậm, CPU throttling, tiến trình runnable chờ |
| Memory | working set, RSS, heap, cache, page faults, OOM | GC tăng, reclaim/swap, OOM kill, eviction |
| Disk/storage | IOPS, throughput, queue depth, latency, burst balance | Database query hoặc ghi log chậm |
| Network | throughput, packet rate, drops, retransmits, connection count | Timeout, packet loss, queueing, NAT/port exhaustion |
| Threads/processes | active/blocked threads, process count, file descriptors | Thread pool cạn, lỗi mở file/socket |
| Downstream pools | DB connections, queue depth, API quota | Chờ connection, backlog tăng, rate limit |
| Nền tảng | quota, pending allocation, scaling events, throttling | Không tạo được instance dù ứng dụng yêu cầu scale |

Metric trung bình toàn node có thể che khuất một container hoặc một CPU core bị bão hòa. Cần xem **theo workload và theo thời gian**, đặc biệt p95/p99 latency và mức tranh chấp trong cửa sổ tải đỉnh.

## 3. Phân biệt request, limit, quota và concurrency

Các thuật ngữ có ý nghĩa khác nhau tùy nền tảng, nhưng có thể hiểu theo các vai trò sau:

| Cơ chế | Ý nghĩa | Mục đích |
| --- | --- | --- |
| **Request / reservation** | Năng lực được khai báo cần thiết hoặc được giữ chỗ khi lập lịch/cấp phát | Giúp scheduler bố trí workload và dự phòng capacity |
| **Limit / cap** | Mức sử dụng tối đa hoặc giới hạn cứng/mềm được thực thi | Ngăn một workload sử dụng vượt phần được phép |
| **Quota** | Hạn mức tổng theo account, project, tenant, region hoặc dịch vụ | Giới hạn tổng số tài nguyên/tác vụ có thể tạo hay sử dụng |
| **Concurrency limit** | Số tác vụ/request/instance được xử lý đồng thời | Bảo vệ tài nguyên hoặc downstream khỏi quá tải |
| **Priority / class** | Mức ưu tiên khi tranh chấp hoặc lập lịch | Bảo vệ workload quan trọng hoặc quy định thứ tự phục vụ |
| **Reservation pool** | Capacity được dành trước cho nhóm workload | Giảm nguy cơ workload khác chiếm hết năng lực cần thiết |

Một request không nhất thiết là mức tối thiểu mà ứng dụng luôn tiêu thụ, và một limit không phải lúc nào cũng là capacity được giữ sẵn. Ví dụ request CPU của Kubernetes phục vụ scheduler; CPU limit thường tạo quota cgroup để giới hạn thời gian CPU. Memory limit được thực thi theo cơ chế khác, không giống CPU throttling.

### Ví dụ: workload A và B dùng chung node

Giả sử một node có 8 vCPU và 16 GiB RAM. Đội nền tảng muốn bố trí:

| Workload | CPU request | CPU limit | Memory request | Memory limit |
| --- | ---: | ---: | ---: | ---: |
| Booking API | 2 CPU | 3 CPU | 3 GiB | 4 GiB |
| Notification worker | 1 CPU | 2 CPU | 2 GiB | 3 GiB |
| Reporting batch | 1 CPU | 2 CPU | 2 GiB | 3 GiB |
| Tổng khai báo | 4 CPU | 7 CPU | 7 GiB | 10 GiB |

Phần còn lại của node phải dành cho hệ điều hành, agent, daemon, overhead và năng lực dự phòng. Request không cộng đúng bằng số vCPU vật lý cũng chưa bảo đảm không có contention: giới hạn burst, CPU share/weight, I/O và các workload khác vẫn ảnh hưởng. Phải tính tài nguyên hệ thống và kiểm thử trong tải thật.

### Hành vi khi chạm giới hạn

- **CPU cap:** runtime có thể throttling tiến trình; ứng dụng vẫn sống nhưng phản hồi chậm hơn.
- **Memory cap:** allocation có thể thất bại hoặc tiến trình bị OOM-kill; việc vượt giới hạn thường gây hậu quả đột ngột hơn CPU.
- **Quota account:** yêu cầu tạo thêm VM/function/IP có thể bị từ chối hoặc chờ cấp phép; autoscaler không thể tự vượt quota.
- **Concurrency cap:** request mới có thể bị xếp hàng, từ chối, retry hoặc bị throttling tùy nền tảng.
- **Storage/network cap:** throughput có thể bị giới hạn hoặc tính phí tăng; một số dịch vụ có burst capacity rồi quay về baseline.

Vì vậy, tài liệu cấu hình cần nêu **hành vi khi chạm ngưỡng**, không chỉ ghi con số.

## 4. Đặt giới hạn trên VM và compute instance

Với VM, nhà cung cấp thường cung cấp cấu hình vCPU, RAM, network và storage. VM là ranh giới isolation tương đối rõ so với process trong cùng hệ điều hành, nhưng nhiều VM vẫn có thể dùng chung hạ tầng vật lý hoặc giới hạn của host/cloud.

Sizing cần dựa trên:

- CPU profile: bursty, sustained, CPU-bound hay chờ I/O?
- Memory footprint và peak working set, không chỉ heap khai báo.
- Network throughput và số kết nối đồng thời.
- Storage IOPS, throughput, độ trễ và mô hình burst.
- Phụ thuộc vào kiến trúc CPU, accelerator, local NVMe hoặc thiết bị chuyên dụng.
- Mức dự phòng cho lỗi một instance hoặc một zone.

Một instance nhiều vCPU chưa chắc nhanh hơn với mọi workload; một máy nhiều RAM chưa chắc cải thiện dịch vụ nếu bottleneck nằm ở database hoặc lock. Tìm profile phù hợp bằng benchmark cùng loại CPU/memory/network và cấu hình thực tế.

Nếu nhiều ứng dụng cùng chạy trong một VM, cần kiểm soát ở cấp process/service:

- Linux cgroups và systemd slices có thể giới hạn CPU, memory, I/O và số process tùy cấu hình.
- Windows Job Objects và cơ chế quản trị service có thể kiểm soát một số tài nguyên process.
- Thread pool, connection pool, queue nội bộ, file descriptors và process limits phải có ngưỡng riêng.
- Batch job nên có priority thấp hơn API tương tác, nếu hệ điều hành và runtime được cấu hình đúng.

Ranh giới process không mạnh bằng việc tách VM cho mọi trường hợp. Nếu các tiến trình cùng chạy bằng quyền administrator/root hoặc dùng chung kernel, sự cố bảo mật và kernel-level resource exhaustion vẫn có thể ảnh hưởng lẫn nhau.

### Burst instance và tín dụng CPU

Một số nhóm VM có đặc tính **burstable**: khi tải thấp, tích lũy credit để dùng CPU cao trong thời gian giới hạn; khi credit cạn, năng lực CPU có thể bị hạn chế hoặc tính phí theo chế độ tương ứng. Cần quan sát credit balance, mức sử dụng sustained và hành vi khi tải dài. Không sizing production theo benchmark vài phút rồi giả định hiệu năng đó duy trì cả ngày.

## 5. Đặt giới hạn trên container và Kubernetes

Container giúp đóng gói ứng dụng, nhưng nhiều container thường chia sẻ kernel và tài nguyên host. Cơ chế cgroup, namespace, runtime và scheduler phối hợp để giới hạn cũng như cô lập workload.

### CPU request và limit trong Kubernetes

- **CPU request** là giá trị scheduler sử dụng để tìm node đủ tài nguyên khai báo. Nó cũng ảnh hưởng trọng số phân chia CPU trong một số trường hợp cạnh tranh.
- **CPU limit** là mức trần được runtime thực thi qua CPU quota/cgroup. Container có thể bị throttle khi cố dùng nhiều hơn mức cho phép.
- CPU thường được biểu diễn bằng core hoặc millicore, ví dụ 500m tương đương nửa CPU logic theo cách khai báo tài nguyên Kubernetes.

Ví dụ manifest:

~~~yaml
apiVersion: v1
kind: Pod
metadata:
  name: booking-api
spec:
  containers:
    - name: api
      image: example.invalid/booking-api:1.0
      resources:
        requests:
          cpu: "500m"
          memory: "768Mi"
        limits:
          cpu: "1500m"
          memory: "1Gi"
~~~

Đây là **ví dụ cấu hình minh họa**, chưa phải sizing cho production. Nếu workload Java cần heap, metaspace, thread stack và native memory, tổng memory container phải lớn hơn Xmx. Đặt memory limit sát heap max có thể khiến tiến trình bị OOM-kill dù heap chưa đạt ngưỡng.

### Memory limit khác CPU limit

CPU có thể được phân chia theo thời gian; khi vượt CPU quota, container thường bị throttling. Bộ nhớ khó chia sẻ theo cùng cách: khi container vượt memory limit, hệ thống có thể chọn tiến trình để OOM-kill. Memory request ảnh hưởng scheduler và eviction priority, còn memory limit là ranh giới thực thi.

Đặt memory limit quá thấp có thể tạo vòng lặp restart và làm giảm throughput. Đặt quá cao làm scheduler khó xếp workload hoặc có thể khiến node bị overcommit. Phải đo **working set**, heap, direct buffer, metaspace, native allocations, sidecar và peak khi garbage collection.

### CPU có cần limit không?

Không có một con số mặc định phù hợp mọi container. Một số workload API cần khả năng burst CPU ngắn và có thể hoạt động tốt hơn khi không bị CPU throttling quá chặt, trong khi batch job cần cap rõ để bảo vệ API cùng node.

1. Đảm bảo request đủ để scheduler phân bố workload hợp lý.
2. Dựa trên latency và CPU throttling metrics để xem limit có gây ảnh hưởng không.
3. Cân nhắc limit, priority, node pool riêng hoặc tách workload nếu yêu cầu isolation mạnh hơn.
4. Kiểm thử cạnh tranh khi node gần bão hòa, không chỉ chạy một pod riêng lẻ.

### QoS classes và eviction

Kubernetes phân loại Pod thành các nhóm QoS như **Guaranteed**, **Burstable** và **BestEffort** dựa trên cách đặt requests/limits (chi tiết chính xác phụ thuộc resource và cấu hình). Khi node thiếu bộ nhớ, kubelet có thể eviction Pod dựa trên nhiều yếu tố gồm QoS, mức sử dụng so với request và priority. QoS không thay thế policy availability hoặc phân tách node.

Với workload quan trọng, cần:

- Thiết lập request dựa trên mức sử dụng đã đo.
- Memory limit có headroom cho peak và native memory.
- PodDisruptionBudget khi phù hợp để giới hạn gián đoạn do voluntary disruption; PDB không bảo đảm sống sót trước mọi lỗi.
- Anti-affinity/topology spread constraints để tránh tất cả replica ở cùng node/zone.
- PriorityClass được dùng có kiểm soát; priority cao không tạo thêm tài nguyên vật lý.
- Node pool riêng cho workload nhạy cảm hoặc đặc thù khi cần isolation mạnh hơn.

### Namespace quota và LimitRange

Ở cấp cluster/namespace, Kubernetes có thể dùng:

- **ResourceQuota** để giới hạn tổng requests/limits, số Pod, Service, PVC hoặc object được hỗ trợ.
- **LimitRange** để áp default/min/max cho tài nguyên của container hoặc PVC theo loại.
- Admission policy để ngăn workload không có request/limit hoặc vượt quy định.

Ví dụ ResourceQuota:

~~~yaml
apiVersion: v1
kind: ResourceQuota
metadata:
  name: booking-team-quota
  namespace: booking
spec:
  hard:
    requests.cpu: "8"
    requests.memory: 16Gi
    limits.cpu: "12"
    limits.memory: 24Gi
    pods: "30"
~~~

Quota trên là **hạn mức tổng cho namespace theo các trường được khai báo**, không phải capacity đã được giữ sẵn. Node pool vẫn cần đủ tài nguyên để scheduler xếp Pod; quota được sử dụng hết có thể khiến deployment mới không tạo được replica.

## 6. Đặt giới hạn trên serverless và nền tảng managed

Không quản trị node trực tiếp không có nghĩa hết tranh chấp hoặc giới hạn. Serverless/platform managed vẫn có hạn mức theo account, vùng, function, request, memory, timeout hoặc concurrency.

| Nền tảng | Cơ chế cần xem xét | Rủi ro khi bỏ qua |
| --- | --- | --- |
| Function/serverless compute | Memory/CPU gắn với cấu hình, timeout, concurrency, request rate, số execution đồng thời | Throttling, cold start, queue backlog, vượt quota |
| Managed container platform | CPU/memory per instance, max/min replicas, request concurrency, scale-to-zero, quota vùng | Một instance nhận quá nhiều request hoặc không scale kịp |
| PaaS web/app service | Worker size, instance count, plan capacity, connection limit | Nhiều app cùng plan tranh chấp tài nguyên |
| Managed batch/job | VCPU, memory, GPU, số job đồng thời, queue và quota | Batch chiếm hết capacity, job chờ hoặc bị reject |
| Managed database | Connection limit, storage, IOPS, throughput, query concurrency, replica lag | Compute API dư nhưng database nghẽn |

### Concurrency là giới hạn quan trọng

Một function có thể xử lý nhiều invocation đồng thời. Nếu mỗi invocation tạo 5 kết nối database và nền tảng scale lên 100 invocation, nhu cầu có thể tăng tới 500 connection. Nếu database chỉ chịu được số connection thấp hơn, autoscaling function sẽ khuếch đại nghẽn.

~~~text
Số connection cực đại ước lượng
  = số instance/invocation đồng thời
    × connection pool tối đa mỗi instance
    + connection từ worker và tác vụ quản trị
~~~

Đây là giới hạn trên theo cấu hình, không phải mức sử dụng thực tế. Pool có thể lazy-create hoặc multiplex, nhưng phải đo và xác nhận hành vi runtime.

### Backpressure thay vì chỉ scale

Khi downstream đạt giới hạn, hệ thống nên **kiểm soát tốc độ đầu vào**:

- Queue để hấp thụ burst với giới hạn độ dài và tuổi thông điệp.
- Concurrency cap cho worker và function.
- Rate limit theo client, tenant hoặc loại tác vụ.
- Timeout, retry có backoff và jitter, circuit breaker khi downstream không sẵn sàng.
- Load shedding: từ chối hoặc giảm chức năng ít quan trọng khi quá tải, trả phản hồi rõ ràng.

Mở rộng đầu vào khi downstream đã bão hòa thường làm tình hình xấu hơn. Backpressure giúp giữ hệ thống trong vùng có thể phục hồi.

## 7. Isolation: chia sẻ đến đâu là hợp lý?

Có nhiều mức cách ly, đổi lại các mức chi phí và độ phức tạp khác nhau:

| Mức isolation | Ví dụ | Điểm mạnh | Đánh đổi |
| --- | --- | --- | --- |
| Cùng process | Thread pools, executor, bounded queue | Ít overhead, dễ trao đổi dữ liệu | Lỗi process ảnh hưởng mọi workload cùng process |
| Cùng container/Pod | Nhiều process hoặc sidecar | Chia sẻ network namespace/volume theo thiết kế | Tài nguyên và vòng đời có liên hệ |
| Container khác nhau cùng node | Pod/container với cgroup và namespace | Có ranh giới tài nguyên và quản lý riêng | Chia sẻ kernel, node, disk/network và phần cứng |
| VM riêng cùng host/zone | Nhiều VM trên hạ tầng cloud | Ranh giới hệ điều hành rõ hơn | Có thể còn contention ở hạ tầng vật lý và dịch vụ chung |
| Node pool/host riêng | Dedicated node group hoặc dedicated host | Có thể giảm nhiễu và tăng kiểm soát | Tốn chi phí và công suất nhàn rỗi |
| Account/project/subscription riêng | Tách workload hoặc tenant ở cấp quản trị | Ranh giới quản trị/quota rõ hơn | Cấu hình, logging, networking và vận hành phân tán hơn |

**Isolation có nhiều chiều:** cách ly bảo mật không đồng nghĩa cách ly hiệu năng. Một VM riêng vẫn có thể chia sẻ network gateway hoặc database; một namespace riêng không nhất thiết được dành riêng CPU vật lý. Phải chỉ rõ loại nhiễu nào cần kiểm soát.

### Multi-tenancy và fairness

Nếu nền tảng phục vụ nhiều khách hàng hoặc nhóm, chính sách tài nguyên cần cân bằng:

- **Fair share:** không để một tenant chiếm toàn bộ capacity khi tenant khác còn nhu cầu.
- **Priority:** giao dịch quan trọng hoặc luồng trả phí cao có thể được ưu tiên theo chính sách minh bạch.
- **No starvation:** workload ưu tiên thấp vẫn có cơ hội được xử lý khi capacity cho phép.
- **Per-tenant quota:** giới hạn tổng requests, storage, concurrency hoặc tài nguyên theo khách hàng.
- **Burst policy:** cho phép vượt mức cơ sở trong khoảng thời gian quy định, có kiểm soát.
- **Noisy tenant detection:** theo dõi mức dùng và hành vi bất thường theo tenant, không chỉ tổng tải.

Không nên dùng một quota cố định cho mọi khách hàng nếu quy mô và hợp đồng khác nhau. Ngược lại, ưu tiên tenant mà không có giới hạn có thể tạo ra starvation cho tenant khác.

## 8. Autoscaling không thay thế giới hạn tài nguyên

Autoscaling điều chỉnh số lượng instance/replica theo metric hoặc policy. Nó có thể giúp cung cấp thêm capacity nhưng không bảo đảm hệ thống scale kịp burst hay downstream chịu được tải mới.

Ba lớp scaling:

1. **Horizontal scaling:** tăng hoặc giảm số instance/Pod/function worker.
2. **Vertical scaling:** thay cấu hình CPU/RAM/IOPS cho instance hoặc workload.
3. **Cluster/account scaling:** thêm node/VM, tăng quota hoặc thay pool khi capacity hiện tại không đủ.

Mỗi lớp có thời gian phản ứng, giới hạn và chi phí riêng. Vertical scaling có thể yêu cầu restart; thêm node phụ thuộc quota, thời gian provision và khả năng phân vùng. Autoscaler không thể tạo tài nguyên nếu quota của cloud đã hết.

| Metric | Khi hữu ích | Cảnh báo |
| --- | --- | --- |
| CPU utilization | Workload CPU-bound, request rate tương quan CPU | Không phản ánh nghẽn DB hoặc I/O |
| Memory utilization/working set | Workload có footprint tăng theo tải | Scale sau khi đã gần OOM có thể quá muộn |
| Request rate / concurrency | API có tải biến động, mỗi request có chi phí tương đối ổn định | Phải tính tải nặng/nhẹ khác nhau |
| Queue depth / oldest message age | Worker bất đồng bộ | Queue cao có thể do downstream lỗi, scale thêm chưa chắc xử lý được |
| Request latency / saturation | Gắn với SLO và mục tiêu trải nghiệm | Latency có thể tăng vì dependency chứ không phải thiếu compute |
| Custom business metric | Ví dụ lịch đặt chưa xác nhận hoặc tác vụ chưa xử lý | Metric phải được định nghĩa và tránh tạo dao động |

Thiết kế autoscaling nên có **min/max replicas**, scale-out nhanh hơn scale-in, cooldown/stabilization, threshold hoặc target phù hợp, và kiểm thử dao động. Min capacity giúp giữ năng lực warm; max capacity bảo vệ ngân sách và downstream.

### Ví dụ queue worker

Giả sử worker xử lý trung bình 10 thông điệp/giây mỗi instance. Hệ thống nhận 300 thông điệp/giây trong một giờ. Chỉ xét năng lực xử lý lý thuyết:

~~~text
Số worker cần thiết = 300 / 10 = 30 instance
~~~

Nếu mỗi worker mở tối đa 4 DB connections, pool có thể cần tới 120 connections. Nếu database chỉ còn khả năng cấp 80 connections cho worker, tăng worker từ 20 lên 30 có thể làm cạn connection pool. Cần giảm pool mỗi worker, thêm tầng giới hạn đồng thời, tối ưu transaction hoặc tăng capacity database theo phép đo.

## 9. Sizing capacity và dành headroom

Đặt limit mà không tính tổng capacity có thể khiến workload thường xuyên bị tranh chấp. Sizing cần đưa **đỉnh tải, thời gian scale, failure scenario và nhu cầu hệ thống** vào cùng phép tính.

### Ước lượng theo CPU

Giả sử một API instance đạt 100 request/giây ở mục tiêu p95 đã thống nhất, trong khi hệ thống cần 400 RPS:

~~~text
N_instance = ceil(400 / 100) = 4
~~~

Nếu phải chịu lỗi một zone với hai zone cân bằng, mỗi zone cần đủ số instance để khi zone còn lại mất, tải vẫn được phục vụ. Với giả định năng lực trên, ít nhất 4 instance còn lại trong zone sống sót. Cần thêm headroom vì benchmark lý tưởng không phản ánh biến động, deploy, cold start và traffic skew.

### Headroom và overcommit

**Headroom** là năng lực để trống hoặc chưa sử dụng nhằm hấp thụ burst, lỗi và scale-out delay. **Overcommit** là cho phép tổng request khai báo hoặc kỳ vọng vượt capacity vật lý dựa trên giả định không phải tất cả workload dùng đỉnh đồng thời.

Overcommit có thể cải thiện utilization nhưng tăng rủi ro noisy neighbor. Mức chấp nhận phụ thuộc:

- Workload có burst đồng thời hay không.
- Mức criticality và SLO của từng workload.
- Khả năng throttle, queue, retry hoặc từ chối yêu cầu.
- Thời gian cung cấp capacity mới.
- Kịch bản mất node/AZ và khả năng dồn tải lên phần còn lại.

Không dùng trung bình utilization của tuần làm cơ sở duy nhất. Cần xem percentile, correlated peak và stress test.

### Ví dụ chia capacity cho các nhóm tải

Một node pool có 32 vCPU và 128 GiB RAM. Giả sử đội nền tảng giữ 20% CPU làm headroom và 16 GiB cho hệ thống/agent:

~~~text
CPU có thể lập kế hoạch = 32 × (1 - 0,20) = 25,6 vCPU
Memory có thể lập kế hoạch = 128 - 16 = 112 GiB
~~~

Nhóm API cần request tổng 12 vCPU/48 GiB; nhóm worker 8 vCPU/32 GiB; batch 4 vCPU/24 GiB. Tổng request là 24 vCPU/104 GiB, nằm trong capacity lập kế hoạch theo phép tính giả định. Nhưng nếu node mất, capacity còn lại có thể không đủ; phép tính còn cần topology, allocatable resource, DaemonSet/sidecar overhead và failure domain.

Đây là bài toán planning đơn giản, không phải công thức sizing chung. Capacity thật phụ thuộc node allocatable sau overhead, memory pressure, I/O và phân bố từng node. Không thể cộng toàn cụm rồi bỏ qua trường hợp một node không còn chỗ cho Pod cần được lên lịch.

## 10. Kiểm soát tài nguyên không chỉ là CPU và RAM

**Storage:** IOPS, throughput, queue depth, burst credit, latency và dung lượng. Một workload batch có thể làm volume database tăng latency dù CPU còn dư. Tách volume hoặc class storage, giới hạn I/O nếu nền tảng hỗ trợ và thử với pattern đọc/ghi tương ứng.

**Network:** bandwidth, packet per second, connection tracking, NAT port, số kết nối, giới hạn load balancer và egress. Tải lớn có thể đẩy chi phí truyền dữ liệu tăng mà CPU không tăng tương ứng.

**Database:** connection, transaction, locks, query concurrency, storage IOPS, throughput, replica lag. Dùng connection pool có giới hạn; cache chỉ khi có chiến lược invalidation và nhất quán phù hợp.

**Queue/event system:** message age, queue depth, in-flight messages, partition/consumer capacity, retry và dead-letter volume. Scale consumer phải xét năng lực downstream và tính idempotent.

**Accelerator/GPU:** số GPU, memory trên GPU, thời gian chạy kernel và chia sẻ thiết bị. Workload AI có thể gây tranh chấp VRAM và I/O; cần profile, node pool và quota phù hợp.

**Control plane/API quota:** tốc độ gọi API quản trị cloud, số resource, IP, volume, rule, function concurrency. Nền tảng có thể từ chối scale hoặc deploy dù node còn dư.

Giải pháp thường là giới hạn ở đúng **tài nguyên đang trở thành bottleneck**. Tăng CPU cho một workload đang chờ disk I/O có thể chỉ tăng chi phí mà không cải thiện throughput.

## 11. Quan sát và chẩn đoán noisy neighbor

Một chính sách giới hạn chỉ hiệu quả khi đội vận hành nhìn thấy tác động. Cần thiết kế metric từ cả workload, host và downstream.

| Lớp | Tín hiệu | Cách dùng |
| --- | --- | --- |
| Workload | CPU, throttling, memory working set, restarts, OOM, requests/concurrency | Biết workload nào đang dùng/chạm giới hạn |
| Node/VM | allocatable, pressure, run queue, steal, disk latency, packet drops | Xác định tranh chấp ở hạ tầng dùng chung |
| Ứng dụng | latency p50/p95/p99, error rate, saturation, thread pool | Kết nối tài nguyên với trải nghiệm người dùng |
| Dependency | DB connections/locks, queue age, downstream latency, quota errors | Tránh nhầm nghẽn downstream thành thiếu compute |
| Platform | scale events, pending pods, failed provisioning, account quota | Tìm giới hạn scheduler hoặc cloud |
| Cost | CPU/RAM hours, storage/IOPS, egress, idle capacity | Đánh giá hiệu quả phân bổ và overprovision |

### Cách điều tra theo trình tự

1. Xác định thời điểm SLO suy giảm và workload bị ảnh hưởng.
2. So sánh metric của workload đó với các workload cùng node/pool.
3. Kiểm tra CPU throttling, memory pressure, I/O queue, packet drop và connection contention.
4. Đối chiếu log deploy, batch job, autoscaler, quota và thay đổi cấu hình.
5. Kiểm tra downstream: database, cache, queue, external API.
6. Tạo thử nghiệm có kiểm soát: giới hạn workload gây nghi ngờ hoặc chuyển sang node pool riêng, rồi so sánh latency và tài nguyên.
7. Điều chỉnh policy, sizing, isolation hoặc code; đo lại để xác nhận nguyên nhân.

Không nên lập tức tăng limit cho workload bị ảnh hưởng. Nếu node đã đầy, tăng limit có thể làm tranh chấp nặng hơn. Trước tiên xác định **capacity còn hay không**, ai đang chiếm và giới hạn nào đang được thực thi.

### Alert theo triệu chứng và nguyên nhân

- p95/p99 latency và error rate vượt mục tiêu.
- CPU throttling cao kéo dài cùng latency tăng.
- Memory pressure/OOM/restarts hoặc eviction vượt baseline.
- Queue oldest message age tăng vượt thời hạn xử lý nghiệp vụ.
- DB connection pool gần cạn hoặc query latency vượt ngưỡng.
- Pending workload kéo dài do thiếu allocatable capacity hoặc quota.
- Egress, log ingestion hoặc compute cost vượt budget.

CPU 90% trong một phút không nhất thiết là incident nếu ứng dụng còn đáp ứng SLO và có headroom phù hợp; ngược lại CPU 40% vẫn có thể có p99 rất xấu do lock, I/O hoặc downstream.

## 12. Chính sách ưu tiên và bảo vệ workload quan trọng

Không phải mọi workload có tầm quan trọng như nhau. API đặt lịch trong giờ cao điểm có thể cần được bảo vệ trước job báo cáo có thể chạy chậm vài phút.

| Nhóm | Ví dụ | Chính sách tài nguyên gợi ý |
| --- | --- | --- |
| Critical interactive | API đăng nhập, đặt lịch, thanh toán | Reservation/request đủ, limit được thử nghiệm, nhiều replica/AZ, alert theo SLO |
| Important background | Worker gửi thông báo, xử lý đơn | Queue, concurrency cap, retry/backoff, SLA tuổi thông điệp |
| Batch/analytics | Báo cáo, tổng hợp dữ liệu | Priority thấp hơn, schedule ngoài giờ, giới hạn I/O và concurrency |
| Best-effort | Tác vụ thử nghiệm, job tái tạo được | Quota thấp, có thể preempt/evict theo nền tảng và policy |

Các mức ưu tiên phải có định nghĩa và chủ sở hữu. Nếu một workload được xem là critical, nó cần SLO, capacity và quy trình ứng cứu tương ứng; không chỉ đơn giản đặt priority cao nhất.

### Preemption và fairness

Một số scheduler có thể **preempt** workload ưu tiên thấp để dành chỗ cho workload ưu tiên cao. Cần xem:

- Job bị preempt có lưu checkpoint và chạy lại an toàn không?
- Việc dừng có gây duplicate side effects hoặc mất dữ liệu không?
- Workload ưu tiên thấp có bị starvation liên tục không?
- Có giới hạn số lần preemption hoặc thời gian chạy tối thiểu?
- Người dùng có được thông báo/quy định SLA cho job không?

Một hệ thống công bằng không nhất thiết chia đều CPU mọi lúc; nó phân bổ theo policy minh bạch, bảo vệ mục tiêu quan trọng và tránh để một nhóm không bao giờ có cơ hội sử dụng tài nguyên.

## 13. Quy trình đặt giới hạn tài nguyên trong dự án

1. **Phân loại workload:** ghi loại tải (interactive, streaming, batch, event-driven), criticality, pattern CPU/memory/I/O/network, dữ liệu và downstream. Xác định phạm vi tenant và mức isolation cần thiết.
2. **Xác định mục tiêu chất lượng:** định nghĩa SLI/SLO, throughput, concurrency, latency percentile, error budget, RTO/RPO nếu có. Ghi điều kiện cao điểm và failure scenario cần đáp ứng.
3. **Đo baseline:** chạy tải đại diện, thu working set, CPU, memory, disk, network, pool và dependency metrics. Ghi cấu hình runtime, phiên bản và cách tạo tải.
4. **Chọn reservation, limit và quota:** đặt request/reservation dựa trên nhu cầu ổn định, limit dựa trên peak được chấp nhận và sức chứa pool, quota theo team/tenant/account, concurrency theo downstream. Ghi hành vi khi vượt ngưỡng.
5. **Thiết kế isolation và priority:** chọn process/container/node pool/VM/account theo mức rủi ro; dùng anti-affinity/topology spread, security boundary và priority khi phù hợp. Tách batch khỏi interactive nếu tác động đủ lớn.
6. **Xác nhận autoscaling và headroom:** tính capacity bình thường và khi mất node/AZ; thử thời gian cấp thêm capacity; kiểm tra quota account và max replicas. Không cho scaler tăng vô hạn làm cạn database hoặc ngân sách.
7. **Đặt observability và alert:** theo dõi resource theo workload/node/downstream; cảnh báo theo SLO và dấu hiệu starvation, throttling, OOM, queue age, quota failure và cost.
8. **Thử tải cạnh tranh và failure:** cho các workload chạy đồng thời, tạo noisy load có kiểm soát, thử node drain/eviction, downstream chậm và account quota. Kiểm tra workload quan trọng vẫn đạt mục tiêu.
9. **Review và điều chỉnh theo dữ liệu:** sau triển khai, so sánh utilization, latency, lỗi, chi phí và headroom với giả định. Điều chỉnh request/limit/quota; lưu quyết định kiến trúc và ngoại lệ theo phiên bản.

~~~mermaid
flowchart TD
    A["Phân loại workload"] --> B["Xác định SLO và criticality"]
    B --> C["Đo baseline và peak"]
    C --> D["Đặt request, limit, quota, concurrency"]
    D --> E["Chọn isolation và priority"]
    E --> F["Sizing headroom và autoscaling"]
    F --> G["Quan sát và alert"]
    G --> H["Stress/noisy-neighbor/failure test"]
    H --> I{"SLO đạt và fairness phù hợp?"}
    I -- "Chưa" --> C
    I -- "Đạt" --> J["Triển khai và review định kỳ"]
~~~

## 14. Bài thực hành: kiểm soát noisy neighbor cho ứng dụng đặt lịch

**Bối cảnh giả định:** Một cụm compute có ba nhóm workload:

- **Booking API:** phục vụ người dùng, tải cao điểm 400 RPS; mục tiêu p95 dưới 250 ms, SLO thành công 99,9%.
- **Notification worker:** xử lý thông điệp gửi email/SMS; cần hoàn tất trong vòng 5 phút ở tải bình thường.
- **Reporting batch:** chạy mỗi đêm, đọc dữ liệu lớn và tạo báo cáo; có thể kéo dài hơn khi tải tăng.

Cụm có 4 node, mỗi node 8 vCPU và 32 GiB RAM. Trong giờ cao điểm, batch đột ngột chạy song song với Booking API; p95 API tăng lên 1,8 giây và worker backlog tăng. Metric toàn cluster cho thấy CPU 75%, RAM 70%.

Các số liệu trong đề bài là dữ kiện mô phỏng, chưa đủ để kết luận nguyên nhân.

### Nhiệm vụ

1. **Xác định nguyên nhân:** nêu ít nhất năm giả thuyết gồm CPU throttling, memory pressure, disk I/O, DB connection saturation, network egress hoặc lock/query contention. Với mỗi giả thuyết, xác định metric cần xem.
2. **Đề xuất chính sách resource:** thiết kế request/limit cho Booking API và worker, quota cho namespace/team, concurrency cap cho batch và queue worker. Giải thích headroom dành cho OS, agent, daemon và lỗi node. Nếu chọn node pool riêng, nêu lý do và tác động chi phí.
3. **Bảo vệ downstream:** giả sử database chỉ cho phép ứng dụng sử dụng thêm tối đa 100 connection. Đề xuất connection pool, worker concurrency và rate limit để batch/report không làm cạn khả năng phục vụ của Booking API. Chứng minh tổng connection trong tình huống max replicas.
4. **Thiết kế autoscaling và fairness:** chọn metric scale cho API và worker; đặt min/max replica, cooldown và giới hạn để không scale vô hạn. Định nghĩa priority, hành vi khi preempt batch và cách tránh starvation.
5. **Thiết kế phép thử:** chạy tải cạnh tranh, tạo CPU/memory/I/O pressure có kiểm soát, thử DB connection, node failure, quota exhaustion và cost spike; thu số đo trước/sau.

| Phép thử | Tác động tạo ra | Tiêu chí đánh giá |
| --- | --- | --- |
| CPU noisy neighbor | Batch sử dụng CPU liên tục trên node cùng API | API p95, throttling và throughput còn trong mục tiêu |
| Memory pressure | Tăng working set của worker có kiểm soát | Không OOM hàng loạt; eviction theo policy và workload quan trọng được bảo vệ |
| I/O contention | Báo cáo đọc/ghi lớn trên storage dùng chung | Database/API latency và IOPS không vượt ngưỡng |
| DB connection | Tăng đồng thời worker và API tới max replica | Không cạn pool; request quan trọng còn khả năng kết nối |
| Node failure | Drain hoặc mất một node trong môi trường test | Capacity còn lại, pending workload, SLO và thời gian phục hồi |
| Quota exhaustion | Giả lập hết quota tạo node/instance | Alert, hành vi suy giảm và runbook xử lý rõ |
| Cost spike | Tăng tải hoặc kéo dài batch | Không vượt budget ngoài chính sách; cảnh báo hoạt động |

### Gợi ý hướng giải

Không thể kết luận CPU là nguyên nhân chỉ vì batch chạy cùng thời điểm và CPU cluster đạt 75%. Cần kiểm tra CPU usage/throttling theo container, memory pressure, disk latency, DB connection/locks và network. Metric toàn cluster có thể che một node bão hòa hoặc một container bị giới hạn.

Một hướng thiết kế là bảo vệ Booking API bằng reservation phù hợp và giới hạn batch; đưa báo cáo vào queue/schedule với concurrency cap; tách node pool nếu thử nghiệm chứng minh noisy neighbor vẫn ảnh hưởng dù đã giới hạn container. Đặt connection pool tổng trong giới hạn database và dành phần headroom cho tác vụ quản trị/worker. Autoscaler có max capacity và phối hợp với quota của cloud.

Phương án phải được xác nhận bằng **test cạnh tranh đồng thời**. Chỉ chạy riêng Booking API hoặc riêng Reporting batch sẽ không chứng minh khả năng cô lập.

## 15. Đánh giá theo Well-Architected

| Trụ cột | Câu hỏi liên quan đến giới hạn tài nguyên |
| --- | --- |
| **Operational Excellence** | Request/limit/quota có được quản lý bằng IaC, review và cảnh báo không? Runbook xử lý OOM, throttling và quota failure là gì? |
| **Security** | Tenant có thể sử dụng resource exhaustion để gây denial of service không? Có quota, rate limit, resource boundary và least privilege không? |
| **Reliability** | Có headroom khi mất node/AZ? Noisy neighbor có làm SLO workload quan trọng suy giảm? Backpressure và recovery đã thử chưa? |
| **Performance Efficiency** | Sizing dựa trên benchmark đại diện? CPU, memory, I/O, concurrency và downstream bottleneck được quan sát? |
| **Cost Optimization** | Có overprovision, idle capacity, autoscaling runaway hoặc quota/IOPS phí cao không? |
| **Sustainability** | Tài nguyên được sử dụng phù hợp tải, tránh node quá lớn/nhàn rỗi và lưu log/metric không cần thiết không? |

Một thiết kế tốt phải chứng minh được **tác động của workload gây nhiễu đã được giới hạn ở phạm vi có thể chấp nhận**, trong khi workload quan trọng còn đủ capacity và các giới hạn vẫn bảo vệ ngân sách.

## 16. Checklist trước khi đưa compute dùng chung vào production

- [ ] Workload được phân loại theo criticality, pattern tải, tenant và dependency.
- [ ] SLI/SLO, tải cơ sở/đỉnh, concurrency và failure scenario được xác định.
- [ ] Request/reservation, limit, quota và concurrency được phân biệt, có owner và lý do.
- [ ] Memory limit có headroom cho heap, native memory, sidecar và peak; CPU limit đã được thử về throttling.
- [ ] Node/VM có capacity cho hệ điều hành, agent, daemon và kịch bản mất một node/zone.
- [ ] Storage IOPS/throughput, network, connection, file descriptor và quota cũng được xem xét.
- [ ] API, worker và batch có priority/fairness policy; workload quan trọng được bảo vệ.
- [ ] DB connection pool, queue concurrency và downstream quota được tính cho max replica.
- [ ] Autoscaling có min/max, cooldown/stabilization, capacity headroom và kiểm tra cloud quota.
- [ ] Có backpressure, timeout, retry giới hạn, load shedding và idempotency phù hợp.
- [ ] Metric theo workload/node/downstream, alert theo SLO và dấu hiệu starvation/noisy neighbor.
- [ ] Đã thử tải cạnh tranh, OOM/throttling, node drain/failure và quota exhaustion trong môi trường kiểm soát.
- [ ] Chi phí compute, storage, network và tài nguyên dự phòng được theo dõi.
- [ ] Ngoại lệ tài nguyên có thời hạn, người phê duyệt và lịch review.

Đặt giới hạn tài nguyên là cách kiến trúc **phân chia năng lực và giới hạn tác động** giữa các workload. Giới hạn quá chặt làm giảm khả năng phục vụ; giới hạn quá lỏng khiến workload quan trọng dễ bị nhiễu và ngân sách khó kiểm soát. Kết quả tốt đến từ việc đo pattern tải, chọn ranh giới isolation phù hợp, thiết lập request/limit/quota/concurrency, bảo vệ downstream và kiểm chứng khi nhiều tải cạnh tranh. Khi hệ thống phát triển, các con số và policy phải được xem lại theo SLO, chi phí và dữ liệu vận hành thực tế.
