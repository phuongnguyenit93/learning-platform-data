# Node pool, loại máy và phân tách workload theo nhu cầu

Trong Kubernetes, Pod chỉ được lập lịch lên Node có đủ tài nguyên và đáp ứng các ràng buộc của workload. Nếu toàn bộ cluster dùng một nhóm máy giống nhau, ứng dụng web, batch job, database cache, GPU workload và thành phần hệ thống sẽ cạnh tranh cùng một loại capacity. Cách tổ chức node pool theo profile tài nguyên giúp chọn đúng loại máy, cô lập tải, kiểm soát chi phí và duy trì khả năng mở rộng.

**Node pool** là một nhóm Node được quản lý theo cùng cấu hình hoặc cùng chính sách vòng đời, thường có chung machine type, image, kiến trúc CPU, vùng triển khai, labels, taints và giới hạn autoscaling. Một cluster có thể có nhiều pool: pool hệ thống, pool ứng dụng tổng quát, pool compute-optimized, memory-optimized, GPU, Spot hoặc pool dành riêng cho workload nhạy cảm.

Chọn node pool không chỉ là chọn số vCPU và RAM. Cần dựa trên profile workload, Kubernetes requests/limits, storage và network, failure domain, khả năng autoscaling, yêu cầu bảo mật và ngân sách. Bài học này trình bày cách thiết kế node pool, chọn loại máy và phân tách workload bằng cơ chế scheduling chuẩn của Kubernetes.

## 1. Node, node pool và cluster

### Node là gì?

Node là máy tính chạy workload Kubernetes. Node có thể là VM trên cloud, máy vật lý hoặc một môi trường compute được nhà cung cấp quản lý. Mỗi Node thường chạy:

- Kubelet để giao tiếp với control plane và quản lý Pod.
- Container runtime như containerd.
- Kube-proxy hoặc cơ chế dataplane tương đương.
- CNI plugin để cung cấp mạng cho Pod.
- CSI node plugin nếu cluster dùng persistent storage.
- Các system DaemonSet như log agent, monitoring agent, security agent và network component.

Node có tài nguyên vật lý/ảo hóa như CPU, memory, local disk, network và accelerator. Kubernetes báo cáo một phần tài nguyên thành capacity và allocatable.

### Capacity và allocatable

- **Capacity:** tổng tài nguyên Node nhìn thấy và công bố.
- **Allocatable:** phần tài nguyên có thể dành cho Pod sau khi trừ system reserved, kube reserved và một số reservation khác.
- **Requested:** tổng requests của Pod đã được scheduler đặt trên Node.
- **Actual usage:** mức CPU/memory thực tế workload đang tiêu thụ.

Ví dụ Node có 16 vCPU và 64 GiB RAM, nhưng sau khi dành tài nguyên cho hệ điều hành và Kubernetes, allocatable còn 15 vCPU và 58 GiB. Scheduler dùng allocatable để quyết định đặt Pod, không thể giả định toàn bộ 16 vCPU và 64 GiB đều dành cho ứng dụng.

### Node pool là gì?

Node pool gom các Node có cấu hình và chính sách tương tự. Tùy nền tảng, nó có thể được gọi là node group, machine pool, agent pool hoặc managed node group.

Một node pool thường quản lý:

- Machine type hoặc instance family.
- CPU architecture và accelerator.
- OS image, kernel và container runtime.
- Disk boot, local SSD hoặc ephemeral storage.
- Network interface và subnet.
- Availability zone hoặc topology.
- Minimum, maximum và desired node count.
- Labels và taints.
- Upgrade strategy, autoscaling và repair policy.

Tên và khả năng cụ thể khác nhau giữa các dịch vụ Kubernetes managed. Cần phân biệt object Kubernetes chuẩn với resource riêng của cloud provider.

### Cluster có nhiều node pool

~~~mermaid
flowchart TB
    CP["Kubernetes control plane"] --> CL["Cluster scheduler"]
    CL --> SYS["System pool"]
    CL --> GEN["General-purpose pool"]
    CL --> CPU["Compute-optimized pool"]
    CL --> MEM["Memory-optimized pool"]
    CL --> GPU["GPU / accelerator pool"]
    CL --> SPOT["Spot / interruptible pool"]
    SYS --> S1["DNS, monitoring, ingress, agents"]
    GEN --> G1["Web/API workloads"]
    CPU --> C1["CPU-heavy workers"]
    MEM --> M1["Cache, memory-heavy services"]
    GPU --> G1A["Training / inference jobs"]
    SPOT --> P1["Retryable batch jobs"]
~~~

Scheduler chọn Node phù hợp theo requests, node selectors, affinity, taints/tolerations, topology constraints và các policy khác. Node pool tự nó không đảm bảo workload được đưa vào đúng nhóm; cần khai báo các ràng buộc scheduling tương ứng.

## 2. Vì sao cần nhiều node pool?

Một cluster có thể dùng một pool đồng nhất nếu workload đơn giản, nhu cầu tài nguyên gần giống nhau và việc vận hành cần tối giản. Khi workload đa dạng, nhiều pool đem lại các lợi ích:

- **Phù hợp tài nguyên:** chọn CPU, RAM, disk, network và GPU theo đặc tính ứng dụng.
- **Giảm tranh chấp:** tách batch job hoặc workload burst khỏi API latency-sensitive.
- **Cô lập lỗi:** một pool bị cạn capacity hoặc nâng cấp không nhất thiết ảnh hưởng toàn cluster.
- **Tối ưu chi phí:** dùng loại máy nhỏ hoặc Spot cho workload có thể retry; giữ máy ổn định cho dịch vụ quan trọng.
- **Đáp ứng bảo mật:** dành Node riêng cho workload có yêu cầu compliance, dữ liệu nhạy cảm hoặc thiết bị đặc biệt.
- **Tách kiến trúc:** chạy workload amd64 và arm64 trên các Node tương ứng.
- **Quản lý nâng cấp:** nâng cấp image hoặc kernel theo từng nhóm, giảm blast radius.

### Đánh đổi khi chia quá nhiều pool

Mỗi pool làm tăng số cấu hình cần quản lý:

- Nhiều machine type và image hơn.
- Nhiều chính sách autoscaling và quota hơn.
- Có thể xuất hiện Node rỗng do workload bị ràng buộc quá chặt.
- Khó phân bổ Pod đều và giữ đủ capacity.
- Nhiều biến thể cần patch, scan và kiểm thử.
- Chi phí quản trị, monitoring và upgrade tăng.

Không tạo pool riêng cho từng ứng dụng nếu chúng có cùng profile tài nguyên và yêu cầu vận hành. Bắt đầu từ các nhóm workload có khác biệt rõ về compute, memory, accelerator, isolation hoặc availability.

## 3. Phân loại workload theo profile tài nguyên

Trước khi chọn machine type, hãy phân loại workload dựa trên số liệu thực tế.

### CPU-bound

Workload CPU-bound dành phần lớn thời gian tính toán:

- API thực hiện transform hoặc mã hóa dữ liệu.
- Video transcoding.
- Compression và decompression.
- Worker xử lý dữ liệu hoặc tính toán mô hình.
- Build và compile.
- Simulation hoặc batch computation.

Các dấu hiệu:
- CPU usage cao và ổn định.
- Run queue tăng khi tải tăng.
- Throughput tăng theo CPU cho tới điểm bão hòa.
- Memory working set không phải giới hạn chính.
- Latency tăng khi CPU throttling hoặc contention xảy ra.

Có thể cân nhắc compute-optimized Node với CPU mạnh, tỷ lệ CPU/RAM cao và network đủ đáp ứng. Kiểm tra hiệu năng single-core nếu workload có phần tuần tự.

### Memory-bound

Workload memory-bound cần working set lớn hoặc truy cập RAM thường xuyên:

- In-memory cache.
- Search/indexing.
- JVM heap lớn.
- Data processing giữ nhiều bản ghi trong RAM.
- Analytics engine.
- Stateful service có working set lớn.

Các dấu hiệu:
- Memory usage và working set cao.
- OOM hoặc eviction xảy ra khi thiếu RAM.
- GC hoặc paging tăng.
- CPU chưa bão hòa nhưng latency tăng do memory pressure.
- Memory bandwidth hoặc NUMA locality ảnh hưởng hiệu năng.

Có thể chọn memory-optimized Node với RAM lớn trên mỗi vCPU. Cần kiểm tra memory limit của Pod, heap sizing và giới hạn allocatable của Node.

### Storage-bound

Workload storage-bound phụ thuộc IOPS, throughput hoặc latency:

- Database.
- Stateful workload.
- Search index.
- Queue/log broker.
- File processing.
- Workload ghi log hoặc checkpoint nhiều.

Phải đánh giá cả loại volume và Node. Node có nhiều vCPU/RAM không bù được volume IOPS thấp. Kiểm tra:
- IOPS và throughput provisioned.
- Read/write latency.
- Queue depth.
- Local NVMe hoặc ephemeral disk.
- Persistent volume topology.
- CSI driver và attach limits.
- Durability và backup.

### Network-bound

Workload network-bound cần throughput hoặc packet rate cao:

- API gateway và proxy.
- Service mesh sidecar nhiều kết nối.
- Streaming và message broker.
- Data transfer giữa các vùng.
- Distributed storage.
- Network function hoặc packet processing.

Kiểm tra bandwidth, packet-per-second, connection tracking, NIC limit, CNI overhead, MTU, NAT và cross-zone traffic. Một loại VM có CPU cao nhưng network limit thấp vẫn có thể là lựa chọn kém.

### GPU/accelerator-bound

Workload GPU hoặc accelerator:
- Machine learning training/inference.
- Video processing.
- Rendering.
- Scientific computing.
- Một số workload mã hóa hoặc xử lý vector.

Cần xác minh GPU model, memory, driver, CUDA/ROCm hoặc stack tương ứng, device plugin, runtime, node image và quota. Không chỉ xem số GPU; hai accelerator cùng số lượng có thể khác VRAM, bandwidth và throughput.

### Workload hỗn hợp và burst

Một số workload có CPU burst ngắn, memory working set ổn định hoặc I/O không đều. Hãy xem p95/p99 và peak theo thời gian, không chỉ average. Workload burst có thể cần headroom hoặc autoscaling nhanh, nhưng không nên giữ máy lớn liên tục nếu queue có thể hấp thụ tải.

## 4. Chọn machine family và loại máy

Các cloud provider thường cung cấp một số nhóm máy phổ biến. Tên family khác nhau, nhưng cách phân loại thường tương tự.

| Nhóm máy | Đặc tính | Workload phù hợp | Điều cần kiểm tra |
|---|---|---|---|
| General-purpose | Cân bằng CPU và RAM | Web/API, microservice, control workload | Tỷ lệ CPU/RAM, network và cost |
| Compute-optimized | CPU mạnh, tỷ lệ CPU/RAM cao | CPU-bound, build, transcoding | Single-core, sustained CPU và quota |
| Memory-optimized | RAM lớn trên mỗi vCPU | Cache, JVM, analytics, database phù hợp | RAM allocatable, NUMA, memory bandwidth |
| Storage-optimized | IOPS/throughput hoặc local disk cao | Data-intensive, local scratch, log processing | Durability, disk failure và backup |
| Network-optimized | Bandwidth/packet capacity cao | Proxy, streaming, network-intensive | NIC limit, packet rate và topology |
| GPU/accelerator | Có thiết bị tăng tốc | ML, rendering, HPC | GPU model, VRAM, driver và device plugin |
| Burstable | CPU baseline và credit/burst | Dev/test hoặc workload burst nhẹ | Credit balance, throttling và sustained load |
| Arm-based | CPU architecture Arm64 | Workload portable và multi-arch | Binary, native library, image và performance |

### Không so sánh chỉ bằng vCPU

Khi so sánh hai loại máy, cần xem:
- CPU generation và architecture.
- Core/thread topology.
- Single-thread và multi-thread performance.
- RAM và memory bandwidth.
- Local disk và volume bandwidth.
- Network bandwidth và packet rate.
- GPU/accelerator.
- Giá theo region và pricing model.
- CPU credit hoặc throttling policy.
- Quota và khả năng cấp máy ở zone.

Một VM 8 vCPU có thể không tương đương VM 8 vCPU khác. Benchmark workload thật là cơ sở tốt hơn cho quyết định.

### Dùng nhiều machine type trong một pool?

Một pool có thể hỗ trợ nhiều instance type hoặc shape tương đương nếu dịch vụ managed cho phép. Cần bảo đảm chúng đáp ứng cùng yêu cầu workload:
- CPU architecture tương thích.
- RAM tối thiểu.
- GPU hoặc device requirement.
- Network/storage capability.
- OS image và driver.
- Capacity unit/weight phù hợp.

Nếu pool chứa máy rất khác nhau, scheduler chỉ nhìn requests có thể đặt Pod vào Node nhỏ hơn mức workload thực sự cần. Cần giới hạn bằng labels, resource classes hoặc tách pool.

## 5. Tính requests và limits trước khi sizing Node

Kubernetes scheduler dùng requests để lập lịch. Limits được runtime/cgroup áp dụng khi Pod chạy.

- **CPU request:** lượng CPU được dùng để tính khả năng đặt Pod.
- **CPU limit:** mức CPU tối đa container có thể dùng theo quota.
- **Memory request:** lượng RAM scheduler dành chỗ.
- **Memory limit:** ngưỡng bộ nhớ container có thể sử dụng trước khi bị xử lý OOM theo cơ chế kernel/runtime.

Ví dụ:

~~~yaml
apiVersion: v1
kind: Pod
metadata:
  name: api-example
spec:
  containers:
    - name: api
      image: example.invalid/api:1.0
      resources:
        requests:
          cpu: "500m"
          memory: "512Mi"
        limits:
          cpu: "2"
          memory: "1Gi"
~~~

Trong ví dụ, scheduler tính 500 millicore và 512 MiB request. Container có thể dùng tới 2 CPU và 1 GiB memory theo giới hạn đã khai báo.

### Requests quá thấp

Nếu request thấp hơn nhu cầu thực:
- Scheduler có thể đặt quá nhiều Pod lên một Node.
- CPU/memory contention tăng.
- Node có thể chịu áp lực eviction hoặc OOM.
- Autoscaler đánh giá capacity thiếu chính xác.
- Latency tăng khi workload đồng thời bùng lên.

### Requests quá cao

Nếu request cao hơn nhu cầu:
- Node bị xem là đầy dù actual usage thấp.
- Pod Pending không cần thiết.
- Cluster autoscaler tạo thêm Node.
- Bin packing kém và cost tăng.
- Một số pool có thể không tận dụng hết capacity.

### CPU limit và throttling

CPU limit có thể bảo vệ Node khỏi workload chiếm CPU quá mức, nhưng limit quá thấp làm container bị throttling dù Node còn CPU idle. Với workload latency-sensitive, đo CFS throttling và p95/p99 trước khi đặt limit.

### Memory limit và OOM

Memory limit là hard boundary. Khi container vượt giới hạn, kernel có thể OOM kill process trong container. Đặt limit sát mức memory peak có thể gây restart khi tải burst hoặc GC chưa giải phóng kịp. Dùng working set, peak và runtime overhead để chọn mức an toàn.

### QoS classes

Kubernetes phân loại Pod thành:
- Guaranteed.
- Burstable.
- BestEffort.

QoS class phụ thuộc requests/limits của các container trong Pod. Guaranteed yêu cầu CPU và memory request bằng limit cho tất cả container. QoS ảnh hưởng thứ tự eviction trong một số tình huống node pressure, nhưng không thay thế requests, limits, PDB hoặc thiết kế HA.

## 6. Tính số Node và headroom

Giả sử một pool có Node allocatable 7.5 CPU và 28 GiB RAM. Workload có tổng request 24 CPU và 80 GiB RAM. Số Node tối thiểu theo từng chiều:

\[
N_{CPU} = \left\lceil \frac{24}{7.5} \right\rceil = 4
\]

\[
N_{Memory} = \left\lceil \frac{80}{28} \right\rceil = 3
\]

Capacity bị giới hạn bởi chiều lớn hơn, nên cần ít nhất 4 Node theo phép tính tổng đơn giản. Nhưng đây chưa phải sizing cuối cùng.

Cần cộng:
- DaemonSet và system Pod overhead.
- Pod fragmentation do requests không đóng gói vừa Node.
- Pod anti-affinity hoặc topology spread.
- Max Pod per Node và IP address capacity.
- Persistent volume topology.
- N-1 Node hoặc AZ failure.
- Rolling upgrade surge.
- Autoscaling delay.
- Burst và headroom theo SLO.

### Bin packing và fragmentation

Scheduler không thể luôn lấp đầy mọi CPU/RAM còn trống vì Pod phải vừa cả hai chiều và các constraint khác. Ví dụ một Node còn 2 CPU nhưng chỉ 1 GiB RAM trống sẽ không nhận Pod cần 1.5 CPU và 2 GiB RAM.

Do đó, tổng request chia allocatable chỉ là lower bound. Cần mô phỏng hoặc thử scheduling với phân bố Pod thật.

### Capacity sau khi mất Node

Nếu pool có 4 Node và mỗi Node phục vụ 25% tải, mất một Node làm giảm capacity 25%. Nếu yêu cầu tiếp tục phục vụ đầy đủ sau một Node failure, cần thêm headroom hoặc Node dự phòng. Với multi-AZ, tính capacity còn lại khi mất một zone, không chỉ mất một Node.

## 7. Phân tách workload bằng labels và nodeSelector

Node label là metadata dùng để mô tả thuộc tính Node, ví dụ:
- node-pool.
- workload-class.
- CPU architecture.
- accelerator type.
- storage profile.
- zone.
- compliance boundary.

Ví dụ gắn label:

~~~sh
kubectl label node node-a workload-class=general
kubectl label node node-b workload-class=compute
kubectl label node node-gpu accelerator=nvidia
~~~

Deployment có thể dùng nodeSelector:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: video-worker
spec:
  replicas: 4
  selector:
    matchLabels:
      app: video-worker
  template:
    metadata:
      labels:
        app: video-worker
    spec:
      nodeSelector:
        workload-class: compute
      containers:
        - name: worker
          image: example.invalid/video-worker:2.1
          resources:
            requests:
              cpu: "4"
              memory: "8Gi"
            limits:
              cpu: "6"
              memory: "12Gi"
~~~

nodeSelector là điều kiện cứng: Pod chỉ có thể chạy trên Node có tất cả label được chỉ định. Nếu không có Node phù hợp, Pod ở Pending.

### Dùng label do nền tảng quản lý

Với thuộc tính bảo mật hoặc isolation quan trọng, không nên dựa vào label tùy ý mà người dùng có thể tự gắn lên Node. Có thể dùng label thuộc namespace được bảo vệ và cơ chế NodeRestriction/Node authorizer theo cấu hình cluster. Xác minh chính sách admission và quyền ai được phép thay đổi label.

## 8. Node affinity và pod affinity

Node affinity cung cấp biểu thức linh hoạt hơn nodeSelector.

### requiredDuringSchedulingIgnoredDuringExecution

Đây là điều kiện cứng khi scheduler chọn Node. Nếu không có Node thỏa mãn, Pod không được schedule.

### preferredDuringSchedulingIgnoredDuringExecution

Đây là ưu tiên mềm. Scheduler cố gắng chọn Node phù hợp nhưng vẫn có thể chọn Node khác nếu cần.

Ví dụ ưu tiên pool compute nhưng vẫn cho phép fallback:

~~~yaml
apiVersion: v1
kind: Pod
metadata:
  name: report-job
spec:
  affinity:
    nodeAffinity:
      preferredDuringSchedulingIgnoredDuringExecution:
        - weight: 80
          preference:
            matchExpressions:
              - key: workload-class
                operator: In
                values:
                  - compute
  containers:
    - name: report
      image: example.invalid/report:1.0
      resources:
        requests:
          cpu: "2"
          memory: "4Gi"
~~~

Nếu yêu cầu phần cứng là bắt buộc, dùng required affinity hoặc nodeSelector. Preferred affinity không phải cơ chế bảo đảm isolation.

### Pod affinity và anti-affinity

- **Pod affinity:** đặt Pod gần một nhóm Pod khác theo topology, ví dụ cùng zone.
- **Pod anti-affinity:** tránh đặt Pod cùng nhóm trên cùng Node hoặc cùng topology domain.

Anti-affinity có thể giúp phân tán replica nhưng làm giảm khả năng bin packing. Nếu cluster nhỏ hoặc Node pool không đủ zone, Pod có thể Pending.

Dùng label selector chính xác và topologyKey phù hợp; tránh anti-affinity cứng trên cluster có capacity hạn chế nếu không thực sự cần.

## 9. Taints và tolerations: dành Node cho workload phù hợp

Labels và affinity giúp Pod chọn Node. Taints giúp Node từ chối Pod không có toleration phù hợp.

Ví dụ taint một GPU pool:

~~~sh
kubectl taint nodes node-gpu-1 dedicated=gpu:NoSchedule
~~~

Pod cần GPU có thể khai báo toleration:

~~~yaml
apiVersion: v1
kind: Pod
metadata:
  name: inference
spec:
  tolerations:
    - key: dedicated
      operator: Equal
      value: gpu
      effect: NoSchedule
  nodeSelector:
    accelerator: nvidia
  containers:
    - name: model
      image: example.invalid/inference:3.0
      resources:
        limits:
          nvidia.com/gpu: 1
          cpu: "4"
          memory: "16Gi"
~~~

Toleration cho phép Pod được schedule lên Node có taint tương ứng, nhưng không tự chọn Node. Vì vậy ví dụ vẫn dùng nodeSelector để yêu cầu label accelerator.

### Taint effects

- **NoSchedule:** scheduler không đặt Pod mới lên Node nếu thiếu toleration.
- **PreferNoSchedule:** scheduler cố tránh Node nhưng có thể dùng nếu cần.
- **NoExecute:** Pod không tolerate có thể bị evict khỏi Node; Pod tolerate có thể có tolerationSeconds.

Một số taint được Kubernetes hoặc node lifecycle controller tự động thêm, chẳng hạn node not-ready hoặc unreachable. Toleration cho các taint hệ thống cần được hiểu rõ; không thêm rộng rãi để che giấu Node lỗi.

### Dedicated node pool

Một pool dành riêng cho workload có thể dùng cả:
- Label để workload chọn pool.
- Taint để workload khác không vào pool.
- RBAC/admission policy để giới hạn ai có thể tạo toleration.
- Resource quota để kiểm soát tenant.
- Network policy và security context để tăng isolation.

Taint/toleration chỉ là cơ chế scheduling, không phải ranh giới bảo mật đầy đủ. Pod có đặc quyền hoặc quyền điều khiển cluster vẫn có thể phá vỡ mục tiêu cô lập nếu policy không được bảo vệ.

## 10. Tách pool hệ thống và pool ứng dụng

Một cluster production thường có thể tách:

### System pool

Chạy các thành phần nền tảng:
- CoreDNS hoặc DNS service.
- Metrics/monitoring agent.
- Ingress hoặc gateway controller.
- CNI/CSI components.
- Cluster autoscaler hoặc node management agent.
- Security và log agent.
- Các add-on bắt buộc.

Pool này cần đủ capacity để hệ thống quản lý cluster vẫn hoạt động khi app pool quá tải hoặc scale về thấp. Không đặt system pool quá nhỏ; DaemonSet và control workloads có thể cần tài nguyên đáng kể.

### User/application pools

Chạy workload của sản phẩm:
- API và frontend.
- Background worker.
- Batch.
- Stateful app nếu kiến trúc hỗ trợ.
- GPU jobs.
- Tenant-specific workload.

Có thể có nhiều pool theo profile, nhưng cần bảo đảm các system DaemonSet được phép chạy trên từng pool khi cần.

### Tại sao không nên chỉ có một pool?

Nếu workload batch chiếm hết Node, CoreDNS hoặc ingress có thể bị thiếu tài nguyên. Tách system pool và app pool giảm cạnh tranh và tạo đường phục hồi khi ứng dụng gặp sự cố.

### Tại sao không nên tạo system pool quá nhỏ?

Nếu system pool không đủ cho DNS, ingress hoặc monitoring, cluster có thể mất khả năng quản trị và quan sát đúng lúc tải cao. Capacity planning phải tính system DaemonSet, rollout và N-1 failure.

## 11. Pool theo kiến trúc CPU: amd64 và arm64

Một cluster có thể chứa Node nhiều kiến trúc. Điều này hữu ích khi một số workload hỗ trợ Arm64 và có thể đạt hiệu năng/chi phí tốt hơn.

Cần kiểm tra:
- Image có manifest cho linux/amd64 và linux/arm64.
- Native library và agent hỗ trợ architecture.
- JDK/runtime version.
- CNI, CSI, security DaemonSet và monitoring agent.
- Binary sidecar.
- CPU feature và benchmark.
- Node labels như kubernetes.io/arch.

Ví dụ chọn architecture:

~~~yaml
spec:
  nodeSelector:
    kubernetes.io/arch: arm64
~~~

Không schedule workload lên Arm64 chỉ vì image pull thành công. Test native dependency, performance, encryption, JIT và operational agent trên Node thật.

Có thể giữ pool amd64 cho workload chưa portable và pool arm64 cho workload đã xác nhận. Đây là cách chuyển đổi từng phần mà không phải migrate toàn cluster cùng lúc.

## 12. Pool GPU và accelerator

Node GPU cần thêm cấu hình ngoài machine type:
- GPU model và VRAM.
- Driver kernel.
- CUDA/ROCm hoặc runtime tương ứng.
- Device plugin hoặc GPU operator.
- Container toolkit.
- Image có thư viện đúng phiên bản.
- Node labels và taints.
- Quota và autoscaling policy.

Kubernetes device plugin quảng bá extended resource, ví dụ nvidia.com/gpu. Pod yêu cầu resource đó trong limits theo plugin hỗ trợ.

Ví dụ:

~~~yaml
resources:
  limits:
    nvidia.com/gpu: 1
    cpu: "8"
    memory: "32Gi"
~~~

GPU resource thường được cấp theo đơn vị thiết bị nguyên hoặc cấu hình chia sẻ riêng của vendor. Không giả định CPU request hoặc GPU utilization tự động phản ánh VRAM và memory bandwidth.

### GPU scheduling và fragmentation

GPU có thể bị lãng phí nếu Pod yêu cầu một GPU nhưng chỉ dùng một phần nhỏ. Một số nền tảng hỗ trợ time-slicing hoặc MIG partitioning, nhưng semantics và isolation khác nhau. Cần kiểm tra:
- VRAM demand.
- GPU compute utilization.
- GPU memory utilization.
- Batch size.
- Concurrent model count.
- Device sharing policy.
- Failure và reset behavior.

Không dùng GPU pool cho workload không cần accelerator nếu chi phí và capacity cao.

## 13. Pool Spot/preemptible và workload có thể gián đoạn

Spot hoặc preemptible Node có giá thấp hơn nhưng có thể bị thu hồi. Phù hợp với:
- Batch có thể retry.
- Stateless worker.
- Build/test job.
- Data processing có checkpoint.
- Queue consumer có thể drain và resume.

Không nên đặt workload cần availability nghiêm ngặt hoặc state chỉ tồn tại trên local disk vào pool dễ bị thu hồi nếu không có cơ chế phục hồi.

### Thiết kế workload chịu interruption

- Dùng durable queue.
- Task idempotent.
- Checkpoint định kỳ.
- Graceful termination.
- Retry với backoff và giới hạn.
- PodDisruptionBudget phù hợp.
- Có fallback sang on-demand pool.
- Theo dõi interruption notice và job completion.

Spot pool có thể dùng taint để workload thường không bị schedule vào đó. Workload được phép gián đoạn khai báo toleration và node affinity tương ứng.

### Không coi PDB là lá chắn trước mọi interruption

PodDisruptionBudget chủ yếu điều khiển voluntary disruption qua eviction API. Nó không ngăn mọi dạng node failure hoặc involuntary disruption. Ứng dụng vẫn phải chịu được Pod bị mất và job được giao lại.

## 14. Pool theo vùng và topology

Node pool có thể trải trên nhiều availability zone hoặc được chia thành pool riêng theo zone, tùy managed service.

Cần xem:
- Zone capacity và quota.
- Persistent volume zone binding.
- Pod topology spread.
- Pod anti-affinity.
- Load balancer cross-zone.
- Network latency và egress.
- Failure scenario khi mất một zone.

### Topology spread constraints

Ví dụ phân tán replica qua các zone:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api
spec:
  replicas: 6
  selector:
    matchLabels:
      app: api
  template:
    metadata:
      labels:
        app: api
    spec:
      topologySpreadConstraints:
        - maxSkew: 1
          topologyKey: topology.kubernetes.io/zone
          whenUnsatisfiable: DoNotSchedule
          labelSelector:
            matchLabels:
              app: api
      containers:
        - name: api
          image: example.invalid/api:1.0
          resources:
            requests:
              cpu: "1"
              memory: "1Gi"
~~~

Nếu một zone không còn capacity, DoNotSchedule có thể khiến Pod Pending để giữ phân bố. Dùng ScheduleAnyway nếu ưu tiên chạy workload hơn phân bố hoàn hảo. Chọn policy theo availability requirement và số zone thực tế.

### Storage topology

Persistent volume có thể gắn với zone cụ thể. Pod có affinity yêu cầu zone khác có thể không schedule được. Dùng StorageClass và volume binding mode phù hợp; hiểu rằng local PV thường ràng buộc Pod với Node hoặc zone và cần kế hoạch phục hồi dữ liệu.

## 15. Autoscaling node pool

Autoscaling có thể xảy ra ở hai lớp:

- **Horizontal Pod Autoscaler (HPA):** thay đổi số replica của workload.
- **Cluster/node autoscaler:** thêm hoặc bớt Node để đáp ứng Pod Pending hoặc capacity dư.

HPA không tự tạo Node. Nếu Pod cần 4 CPU nhưng không có Node nào còn đủ allocatable CPU, Pod có thể Pending cho tới khi node autoscaler thêm capacity phù hợp.

### Min/max theo pool

Mỗi pool cần:
- Minimum để giữ baseline và system capacity.
- Maximum theo peak, quota và dependency budget.
- Desired/current count.
- Autoscaling signal và cooldown.
- Upgrade surge và failure reserve.

Maximum quá thấp làm Pod Pending khi tải tăng. Maximum quá cao có thể tạo chi phí lớn hoặc vượt quota. Đặt max theo capacity test và giới hạn database/network, không chỉ theo nhu cầu CPU.

### Scale from zero

Một số node autoscaler có thể scale pool từ zero nếu biết Pod yêu cầu labels/resources tương ứng. Cần xác minh:
- Pod khai báo đúng node selector/affinity.
- Autoscaler nhận diện taint và resource.
- Machine image và driver sẵn sàng.
- Thời gian provisioning và warm-up.
- Quota và zone capacity.

GPU pool scale từ zero có thể mất nhiều phút. Nếu workload cần latency thấp, giữ minimum hoặc warm capacity.

### Scale-down và consolidation

Khi Node ít được sử dụng, autoscaler có thể drain và terminate. Nhưng Pod có PDB, local storage, affinity hoặc disruption constraint có thể ngăn scale-down.

Theo dõi:
- Node utilization và allocatable requests.
- Pod eviction và drain duration.
- Empty/underutilized node time.
- Scale-up latency.
- Pending Pod age.
- Cost và interruption.

Không giảm Node chỉ dựa vào CPU average thấp nếu Pod requests cao hoặc có burst.

## 16. Upgrade và bảo trì theo node pool

Tách pool giúp nâng cấp theo từng nhóm, nhưng cần quản lý disruption.

### Rolling upgrade

Quy trình thường gồm:
1. Tạo hoặc nâng Node mới.
2. Chờ Node Ready.
3. Drain Node cũ.
4. Evict Pod theo policy.
5. Chờ workload được schedule sang Node mới.
6. Xác nhận readiness và service health.
7. Xóa Node cũ.

Tùy provider, upgrade có thể dùng surge Node hoặc max unavailable. Cần tính quota và capacity cho giai đoạn hai bộ Node cùng tồn tại.

### PodDisruptionBudget

PDB đặt số Pod tối thiểu khả dụng hoặc tỷ lệ disruption cho các voluntary eviction. PDB không thay thế replica count, readiness probe hay ứng dụng HA. Nếu PDB quá chặt, upgrade hoặc scale-down có thể bị chặn.

### Pool drift

Node trong cùng pool có thể lệch phiên bản do rollout dở dang, autoscaling hoặc manual change. Theo dõi:
- Kubernetes version.
- Node image version.
- Kernel và runtime.
- CNI/CSI agent.
- Security patch.
- Labels/taints.
- Instance type và zone.

Dùng immutable image và quy trình rollout để giảm drift. Không sửa tay một Node theo cách làm cấu hình lệch khỏi pool.

## 17. Bảo mật và isolation giữa workload

Node pool có thể là một lớp phân tách, nhưng không tự tạo ra ranh giới bảo mật hoàn chỉnh.

### Scheduling isolation

Kết hợp:
- Labels và node affinity.
- Taints và tolerations.
- Dedicated pool.
- Namespace và RBAC.
- Admission policy giới hạn toleration.
- ResourceQuota và LimitRange.
- Pod Security Standards.
- NetworkPolicy.
- Secret scope và service account.

### Dedicated node cho workload nhạy cảm

Có thể dành pool riêng cho:
- Workload xử lý dữ liệu nhạy cảm.
- Workload có license ràng buộc.
- GPU/accelerator.
- Workload có yêu cầu kernel hoặc driver đặc biệt.
- Workload có noisy-neighbor risk.
- Workload tuân thủ placement policy.

Cần kiểm tra ai có quyền tạo Pod tolerating taint và ai có quyền sửa Node label. Nếu mọi tenant đều có thể khai báo toleration cho dedicated pool, isolation sẽ mất ý nghĩa.

### Host-level security

Node pool cần có:
- OS image được harden.
- Patch cadence.
- Disk encryption.
- Metadata access control.
- Least-privilege node identity.
- Container runtime security.
- Audit và monitoring.
- Quy trình thay thế Node khi compromise.

Không đặt workload không tin cậy lên cùng Node với workload nhạy cảm chỉ dựa vào namespace. Namespace là phạm vi quản lý API, không phải kernel isolation.

## 18. ResourceQuota, LimitRange và giới hạn theo namespace

Node pool quyết định nơi Pod chạy; quota giới hạn mức tài nguyên tenant hoặc namespace có thể yêu cầu.

### ResourceQuota

Ví dụ giới hạn tổng requests và số Pod:

~~~yaml
apiVersion: v1
kind: ResourceQuota
metadata:
  name: team-quota
  namespace: team-a
spec:
  hard:
    requests.cpu: "40"
    requests.memory: 80Gi
    limits.cpu: "80"
    limits.memory: 160Gi
    pods: "100"
~~~

Quota giúp ngăn một namespace chiếm toàn bộ capacity. Nó không bảo đảm Node pool có đủ tài nguyên và không thay thế autoscaling.

### LimitRange

LimitRange có thể đặt default request/limit và min/max cho container trong namespace. Điều này giảm nguy cơ workload không khai báo resource hoặc khai báo quá lớn.

### Tổng hợp quota và node capacity

Khi thiết kế nhiều team:
- Tính quota toàn namespace.
- Tính pool capacity.
- Trừ system overhead.
- Giữ headroom cho scale và failure.
- Theo dõi quota chưa dùng nhưng capacity đã giữ.
- Kiểm tra Pod có thể bị Pending do quota hay do Node constraint.

Pod Pending có thể do nhiều nguyên nhân; đọc scheduler events trước khi tăng Node.

## 19. Thiết kế ví dụ: cluster cho API, batch và GPU

Một sản phẩm có:
- API latency-sensitive.
- Worker xử lý file CPU-bound.
- Job ML inference cần GPU.
- Add-on hệ thống.

Có thể thiết kế:

| Pool | Machine profile | Taint/label | Workload |
|---|---|---|---|
| system | General-purpose, capacity ổn định | node-role=system | DNS, ingress, monitoring, agents |
| api | General-purpose, nhiều zone, on-demand | workload-class=api | API và frontend |
| compute | Compute-optimized | workload-class=compute | File processing, batch CPU |
| gpu | GPU/accelerator | dedicated=gpu:NoSchedule | Inference/training |
| spot-batch | Compute-optimized Spot | capacity-type=spot:NoSchedule | Job retryable |

### API pool

- Giữ minimum đủ cho tải nền và N-1.
- Spread replica qua zone.
- Requests/limits theo p95/p99.
- Tránh CPU limit quá thấp gây throttling.
- Dùng PDB cho rollout.
- Không để batch job chiếm pool.

### Compute pool

- Dùng requests lớn và queue worker có giới hạn.
- Có thể scale theo queue depth hoặc số job Pending.
- Dùng Spot nếu job idempotent/checkpoint.
- Giới hạn concurrency theo database và storage.

### GPU pool

- Chỉ Pod cần accelerator mới tolerate taint.
- Pin driver/device plugin version.
- Kiểm tra VRAM và GPU utilization.
- Có quota và max node rõ.
- Giữ warm capacity nếu cold start quá dài.

### System pool

- Đủ capacity cho DaemonSet và control workloads.
- Không scale về zero nếu cluster cần system service hoạt động.
- Có headroom cho upgrade.
- Giám sát Node pressure và DNS/ingress.

## 20. Các lệnh kiểm tra và chẩn đoán

Xem Node và label:

~~~sh
kubectl get nodes -o wide --show-labels
kubectl describe node node-a
kubectl get nodes -L kubernetes.io/arch,topology.kubernetes.io/zone,workload-class
~~~

Xem tài nguyên:

~~~sh
kubectl top nodes
kubectl top pods -A
kubectl describe pod api-7c8d9 -n production
kubectl get events -A --sort-by=.lastTimestamp
~~~

Xem requests/limits và placement:

~~~sh
kubectl get pods -A -o wide
kubectl get pod api-7c8d9 -n production -o yaml
kubectl describe node node-a
~~~

Kiểm tra taints:

~~~sh
kubectl get nodes -o custom-columns=NAME:.metadata.name,TAINTS:.spec.taints
~~~

Kiểm tra GPU resource nếu device plugin quảng bá:

~~~sh
kubectl describe node gpu-node-1
kubectl get pods -A -o wide
~~~

### Đọc lỗi scheduling

Các thông báo thường gặp:
- Insufficient cpu.
- Insufficient memory.
- Untolerated taint.
- Node affinity/selector mismatch.
- Too many pods.
- Volume node affinity conflict.
- Pod topology spread constraint.
- Node not ready hoặc cordoned.
- Resource quota exceeded.

Không xử lý mọi Pod Pending bằng cách tăng số Node. Xác định constraint nào không thỏa trước, sau đó sửa request, label, taint, storage topology hoặc capacity đúng chỗ.

## 21. Theo dõi hiệu quả từng node pool

Dashboard theo pool nên có:

| Nhóm | Metric | Mục đích |
|---|---|---|
| Capacity | Node count, allocatable CPU/memory, min/max | Biết capacity được cấp |
| Scheduling | Pending Pod, unschedulable reason, scheduling latency | Phát hiện pool thiếu hoặc constraint sai |
| Utilization | CPU/memory usage, request-to-allocatable ratio | Đánh giá over/under-provisioning |
| Pressure | CPU throttling, memory pressure, disk pressure, eviction | Phát hiện Node bão hòa |
| Scaling | Scale-up/down event, node provisioning time | Đo thời gian phản ứng |
| Availability | Ready Node, zone distribution, PDB disruptions | Đánh giá chịu lỗi |
| GPU | GPU utilization, VRAM, allocated devices | Tối ưu accelerator |
| Cost | Node-hours, instance type, Spot interruption | Phân tích chi phí |
| Operations | Upgrade status, image drift, patch level | Kiểm soát vòng đời |

Đo riêng từng pool. Một cluster có CPU utilization trung bình 35% có thể đồng thời có GPU pool gần 0%, API pool bão hòa memory và batch pool dư CPU. Con số tổng không chỉ ra nơi cần tối ưu.

### Unit cost

Có thể đo:
- Cost per successful API request.
- Cost per completed batch job.
- Cost per GB processed.
- Cost per GPU inference.
- Cost per tenant hoặc workload.

Khi phân bổ node cost, cần chọn driver rõ ràng như CPU/memory request, actual usage hoặc capacity reserved. Shared system overhead và idle headroom cũng cần được phân bổ theo policy.

## 22. Những lỗi thiết kế thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Pod Pending dù cluster còn CPU | Pool không có label phù hợp hoặc RAM không đủ | Kiểm tra events, affinity và allocatable theo từng Node |
| API latency tăng khi batch chạy | Hai workload cạnh tranh cùng Node | Tách pool, taint và affinity |
| CPU usage thấp nhưng Pod bị throttling | CPU limit quá thấp | Kiểm tra throttled time và điều chỉnh limit |
| Node memory còn ít, Pod bị OOM | Request/limit hoặc working set sizing sai | Đo peak, heap và memory pressure |
| GPU Node rỗng nhưng job Pending | Driver/device plugin hoặc taint/toleration sai | Kiểm tra extended resource và scheduling |
| Spot Node mất làm job lỗi | Job không checkpoint hoặc không idempotent | Durable queue, retry và graceful termination |
| Node mới tạo nhưng Pod không schedule | Node image/arch/taint không phù hợp | Kiểm tra labels, runtime và image manifest |
| Scale out không kịp | Provisioning và bootstrap lâu | Warm capacity, scale signal sớm hơn |
| Nhiều pool có Node rỗng | Chia pool quá nhỏ hoặc affinity quá chặt | Gộp profile tương tự, dùng preferred affinity khi phù hợp |
| Upgrade bị kẹt | PDB hoặc disruption constraints quá chặt | Kiểm tra replica, PDB và surge capacity |

### Tránh over-segmentation

Nếu mỗi workload có pool riêng, cluster dễ có nhiều capacity nhàn rỗi và khó autoscale. Chỉ tách khi có lý do đo được:
- Khác profile tài nguyên.
- Khác kiến trúc hoặc accelerator.
- Khác yêu cầu isolation.
- Khác availability hoặc interruption tolerance.
- Khác vòng đời hoặc policy.

## 23. Quy trình thiết kế node pool

1. **Inventory workload:** liệt kê service, batch, stateful workload, GPU và system add-on.
2. **Đo profile:** CPU, memory working set, storage I/O, network, peak và duration.
3. **Xác định SLO:** latency, throughput, availability và recovery.
4. **Chọn machine family:** general, compute, memory, storage, network, GPU hoặc Arm.
5. **Xác định pool boundary:** system, application, dedicated, Spot và architecture.
6. **Đặt requests/limits:** dựa trên đo lường và headroom.
7. **Thiết kế scheduling:** labels, nodeSelector, affinity, taints, tolerations và topology spread.
8. **Tính capacity:** allocatable, DaemonSet overhead, fragmentation, N-1 và rollout surge.
9. **Cấu hình autoscaling:** min/max, scale signals, cooldown và warm capacity.
10. **Thiết lập isolation:** RBAC, admission, quota, Pod Security và NetworkPolicy.
11. **Kiểm thử:** scheduling, load, node failure, AZ failure, Spot interruption và upgrade.
12. **Đo chi phí:** node-hours, utilization, unit cost và idle capacity.
13. **Vận hành:** monitor drift, patch, capacity và review pool định kỳ.

### Tiêu chí nghiệm thu

Một thiết kế node pool có thể đưa vào vận hành khi:
- Mỗi pool có workload profile và owner rõ.
- Machine type đáp ứng CPU/RAM/storage/network/GPU.
- Requests/limits dựa trên dữ liệu đo.
- Pod được schedule đúng pool.
- Workload không được phép vào pool dedicated bị chặn bằng taint/policy.
- Hệ thống và DaemonSet có đủ capacity.
- Autoscaler hoạt động trong min/max và quota.
- Cluster chịu được failure scenario đã xác định.
- Upgrade/drain không vi phạm SLO.
- Dashboard thể hiện capacity, pressure, scaling và cost theo pool.

## 24. Checklist node pool và workload separation

### Thiết kế pool
- [ ] Đã inventory và phân loại CPU-bound, memory-bound, storage-bound, network-bound, GPU và burst.
- [ ] Đã quyết định số pool tối thiểu cần thiết.
- [ ] Đã chọn machine family theo benchmark.
- [ ] Đã xác minh architecture và native dependency.
- [ ] Đã xác định OS image, kernel, runtime và driver.
- [ ] Đã tính allocatable sau system/kube reserved.
- [ ] Đã tính DaemonSet, Pod density và IP capacity.
- [ ] Đã tính headroom, N-1 và rolling upgrade surge.

### Scheduling và isolation
- [ ] Labels có quy ước và owner.
- [ ] nodeSelector/affinity dùng cho workload bắt buộc hoặc ưu tiên đúng cách.
- [ ] Taints/tolerations giới hạn pool dedicated.
- [ ] RBAC/admission kiểm soát ai được dùng toleration đặc quyền.
- [ ] Topology spread phân tán replica theo failure domain.
- [ ] PDB phù hợp với upgrade và availability.
- [ ] Namespace quota và LimitRange được thiết lập.
- [ ] NetworkPolicy và security context đáp ứng isolation.

### Autoscaling và vận hành
- [ ] HPA và node autoscaler có mục tiêu riêng.
- [ ] Min/max node pool phù hợp tải và quota.
- [ ] Scale-from-zero đã được kiểm thử nếu dùng.
- [ ] Spot workload có checkpoint, retry và graceful shutdown.
- [ ] Upgrade có surge, drain và rollback.
- [ ] Dashboard theo pool có capacity, usage, pressure và cost.
- [ ] Alert cho Pending Pod, Node NotReady, throttling và quota.
- [ ] Có quy trình rà soát pool rỗng, drift và image patch.
- [ ] Unit cost được đo theo output thành công.

## Kết luận

Node pool cho phép tổ chức compute Kubernetes thành các nhóm Node có machine type, kiến trúc, vùng triển khai và chính sách vòng đời phù hợp với từng workload. Workload CPU-bound, memory-bound, storage-bound, network-bound và GPU cần được chọn tài nguyên theo profile đo được. Requests/limits giúp scheduler và runtime quản lý capacity; labels, affinity, taints/tolerations và topology spread điều khiển Pod chạy ở đâu và được phân tán thế nào. Tách system, application, dedicated và Spot pool có thể giảm tranh chấp, tăng isolation và tối ưu chi phí, nhưng quá nhiều pool làm fragmentation và tăng gánh nặng vận hành. Thiết kế tốt cần được xác minh bằng scheduling test, load test, failure/upgrade rehearsal và dashboard cost theo từng pool.
