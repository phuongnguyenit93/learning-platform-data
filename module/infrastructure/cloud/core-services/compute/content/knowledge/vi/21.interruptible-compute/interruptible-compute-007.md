# Đa dạng hóa instance type, zone và nguồn cấp tài nguyên

## Mục tiêu bài học

Trong môi trường cloud, capacity không phải lúc nào cũng có sẵn ở đúng loại máy, đúng vùng và đúng thời điểm cần thiết. Điều này đặc biệt quan trọng với Spot hoặc preemptible compute: một pool có thể cạn capacity hoặc bị thu hồi trong khi pool khác vẫn còn tài nguyên. Nếu fleet chỉ phụ thuộc vào một instance type hoặc một Availability Zone, khả năng mở rộng và phục hồi sẽ bị giới hạn.

Đa dạng hóa capacity là thiết kế nhóm tài nguyên có nhiều lựa chọn tương thích về cấu hình máy, vùng triển khai và nguồn cấp tài nguyên. Mục tiêu là tăng khả năng tìm được compute khi nhu cầu thay đổi, giảm tác động khi một pool bị thiếu hoặc gián đoạn, đồng thời giữ hiệu năng và chi phí trong giới hạn.

Sau bài học này, bạn có thể:

- Giải thích capacity pool và các yếu tố tạo nên một pool.
- Chọn nhiều instance type có khả năng thay thế nhau.
- Phân tán workload qua nhiều zone và cân nhắc mở rộng sang region khác.
- Kết hợp Spot, on-demand và capacity được bảo đảm.
- Phân biệt cam kết chi phí với cam kết capacity.
- Thiết kế fleet allocation, fallback và giới hạn ngân sách.
- Dùng label, taint, affinity và topology spread trong Kubernetes.
- Đo mức độ đa dạng hóa, khả năng cấp máy và chi phí trên mỗi đơn vị công việc.

## 1. Vì sao cần đa dạng hóa capacity?

Nhà cung cấp cloud chia hạ tầng thành các nhóm tài nguyên có khả năng cấp phát khác nhau. Một yêu cầu máy ảo thường phụ thuộc vào instance type, Availability Zone, kiến trúc CPU, loại accelerator và purchase option. Khi một tổ hợp không còn capacity, yêu cầu có thể thất bại dù region vẫn còn nhiều máy ở các cấu hình khác.

Với Spot hoặc preemptible compute, rủi ro rõ hơn vì nhà cung cấp có thể thu hồi capacity để phục vụ nhu cầu ưu tiên cao hơn. Nếu fleet chỉ dùng một loại máy trong một zone, một đợt thiếu capacity có thể ảnh hưởng đồng thời tới phần lớn worker.

Đa dạng hóa giúp:

- Tăng số capacity pool có thể đáp ứng workload.
- Giảm phụ thuộc vào một instance family, một zone hoặc một nguồn cấp.
- Tăng cơ hội scale-out khi nhu cầu tăng đột ngột.
- Giảm tác động khi một pool có interruption rate cao.
- Tạo lựa chọn fallback khi Spot không cấp đủ máy.
- Cân bằng chi phí, hiệu năng và độ sẵn sàng.

Đa dạng hóa không có nghĩa là chấp nhận mọi loại máy. Các lựa chọn phải đáp ứng cùng yêu cầu chức năng, hiệu năng tối thiểu, kiến trúc phần mềm, network, storage và chính sách bảo mật.

~~~mermaid
flowchart TD
    W["Workload cần thêm capacity"] --> P["Capacity policy"]
    P --> T1["Instance family / size A"]
    P --> T2["Instance family / size B"]
    P --> T3["Instance family / size C"]
    T1 --> Z1["Zone 1"]
    T1 --> Z2["Zone 2"]
    T2 --> Z1
    T2 --> Z3["Zone 3"]
    T3 --> Z2
    T3 --> Z3
    Z1 --> S1["Spot pool"]
    Z2 --> S2["Spot pool"]
    Z3 --> S3["Spot pool"]
    P --> O["On-demand / reserved capacity"]
~~~

## 2. Capacity pool là gì?

Capacity pool là tập tài nguyên mà nhà cung cấp có thể cấp phát theo một tập điều kiện nhất định. Cách định nghĩa chính xác tùy dịch vụ, nhưng các yếu tố thường gồm:

- Region và Availability Zone.
- Instance family, generation và size.
- Kiến trúc CPU, ví dụ x86-64 hoặc Arm.
- CPU, RAM, GPU hoặc accelerator.
- Network bandwidth, số NIC hoặc khả năng enhanced networking.
- Local storage, loại volume và giới hạn IOPS/throughput.
- Hệ điều hành, hypervisor, tenancy hoặc placement requirement.
- Purchase option: on-demand, Spot hoặc loại capacity khác.

Hai máy có cùng số vCPU và RAM chưa chắc nằm trong cùng pool hoặc có hiệu năng tương đương. Khác biệt về CPU generation, memory bandwidth, network baseline, local NVMe hoặc GPU có thể ảnh hưởng đáng kể đến workload.

### 2.1. Pool có thể cạn độc lập

Giả sử fleet yêu cầu máy thuộc family compute-optimized, size lớn, tại một zone duy nhất. Nếu pool đó không còn capacity Spot, yêu cầu launch có thể không được đáp ứng. Một máy memory-optimized hoặc compute-optimized khác family ở zone khác có thể vẫn được cấp.

Do đó, capacity của cả region không đồng nghĩa mọi cấu hình máy đều có thể được tạo ngay. Hãy theo dõi kết quả cấp phát theo tổ hợp instance type, zone và purchase option thay vì chỉ xem tổng số VM trong region.

### 2.2. Số lượng pool hữu ích quan trọng hơn số lựa chọn trên giấy

Một danh sách gồm 30 instance type không tạo ra 30 lựa chọn thực tế nếu phần lớn không tương thích với ứng dụng, chỉ có trong một zone hoặc có giới hạn quota riêng.

Đánh giá từng lựa chọn theo:

- Tương thích kiến trúc và binary.
- CPU/RAM tối thiểu và tỷ lệ CPU-to-memory.
- Hiệu năng benchmark trên workload thật.
- Network và storage cần thiết.
- Tính sẵn có theo zone.
- Giá, interruption history và khả năng cấp capacity.
- Quota, license và giới hạn nền tảng.

## 3. Đa dạng hóa instance type

Instance type thường được nhóm theo mục đích và đặc điểm phần cứng.

| Nhóm máy | Đặc điểm thường gặp | Workload phù hợp |
|---|---|---|
| General purpose | Cân bằng CPU, RAM và network | Web/API, service tổng quát |
| Compute optimized | Tỷ lệ CPU trên RAM cao | Batch tính toán, xử lý song song |
| Memory optimized | RAM lớn, memory bandwidth cao | Cache, in-memory database, analytics |
| Storage optimized | Local storage hoặc I/O cao | Data processing, cache tạm, workload I/O |
| Accelerated computing | GPU hoặc accelerator chuyên dụng | ML inference/training, rendering, HPC |

Đây là phân nhóm khái quát; tên family và đặc tính cụ thể phụ thuộc nhà cung cấp. Không thay một instance type bằng loại khác chỉ vì cùng vCPU. Một workload có thể nhạy với CPU clock, memory bandwidth, cache, network throughput hoặc local disk latency.

### 3.1. Tạo nhóm instance tương đương

Trước khi thêm type mới vào fleet, xác định yêu cầu tối thiểu:

- Số vCPU hoặc năng lực xử lý tương đương.
- Dung lượng RAM và memory bandwidth.
- Kiến trúc CPU được ứng dụng hỗ trợ.
- Network throughput và packet rate.
- Storage throughput, IOPS và dung lượng ephemeral.
- GPU model, VRAM và driver nếu workload dùng accelerator.
- Yêu cầu kernel, OS image, runtime và license.

Sau đó benchmark một tập đại diện. Có thể chuẩn hóa theo một đơn vị năng lực như vCPU, worker slot hoặc throughput đo được, nhưng không giả định 1 vCPU trên hai family luôn có hiệu năng giống nhau.

### 3.2. Khác biệt kiến trúc CPU

Đa dạng hóa giữa x86-64 và Arm có thể mở rộng capacity pool, nhưng cần kiểm tra:

- Container image có manifest đa kiến trúc hay không.
- Native library, JNI và binary có bản build phù hợp không.
- JDK, runtime, agent bảo mật và monitoring có hỗ trợ không.
- Hiệu năng và chi phí trên mỗi request/job.
- Các instruction set hoặc extension mà ứng dụng phụ thuộc.

Nếu image chỉ có bản x86-64, thêm instance Arm vào fleet có thể làm launch thành công nhưng container không chạy được. Nên build và kiểm thử multi-architecture image trước khi đưa cả hai kiến trúc vào cùng policy.

### 3.3. Chọn size và hiệu năng tương đương

Các size khác nhau có thể dùng chung một family nhưng không nhất thiết có cùng đặc tính network hoặc storage. Một size nhỏ có thể có throughput thấp hơn hoặc bị giới hạn burst. Với workload cần một mức capacity cụ thể, cân nhắc:

- Dùng weighted capacity theo vCPU, worker slot hoặc benchmark unit.
- Chia job thành task có kích thước phù hợp nhiều loại máy.
- Tránh đặt một task cần RAM lớn lên instance nhỏ.
- Thiết lập concurrency khác nhau theo size.
- Theo dõi throughput thực tế theo instance type.

Nếu fleet tính desired capacity bằng số instance, một máy 4 vCPU và một máy 32 vCPU đều có thể bị tính là một đơn vị. Điều đó làm capacity thực tế thay đổi mạnh khi autoscaler chọn type khác nhau. Dùng weighted capacity hoặc metric workload-level để phản ánh năng lực thực.

### 3.4. Tránh đa dạng hóa làm giảm tính nhất quán

Không thêm loại máy chỉ để tăng số pool nếu nó buộc workload phải có nhiều cấu hình đặc biệt. Ví dụ, một số máy có local NVMe nhưng máy khác chỉ có network block storage; ứng dụng phải xử lý khác biệt về durability, mount và I/O. Hãy giới hạn danh sách vào các lựa chọn có thể dùng chung image, bootstrap và vận hành, hoặc tách thành các pool workload khác nhau.

## 4. Đa dạng hóa Availability Zone

Availability Zone (AZ) là miền triển khai độc lập trong một region, thường có hạ tầng và failure domain riêng. Chạy workload qua nhiều AZ giúp giảm phụ thuộc vào một vùng hạ tầng cục bộ.

Với Spot, mỗi AZ có thể có capacity pool và mức sẵn có khác nhau. Nếu một AZ thiếu capacity, fleet vẫn có thể tìm máy ở AZ khác nếu cấu hình và kiến trúc ứng dụng cho phép.

### 4.1. Phân tán theo zone

Một fleet có thể:

- Cho phép launch ở nhiều AZ.
- Phân phối replica hoặc worker qua các AZ.
- Duy trì minimum capacity trong các zone quan trọng.
- Theo dõi interruption và capacity fulfillment theo AZ.
- Tránh đặt toàn bộ worker vào một zone vì giá hoặc capacity hiện tại.

Phân phối đều không phải lúc nào cũng là mục tiêu tối ưu. Một AZ có thể có capacity ít hơn hoặc chi phí network khác. Cần cân bằng khả năng chịu lỗi, độ trễ, chi phí liên AZ và yêu cầu của storage.

### 4.2. Storage và state ảnh hưởng lựa chọn zone

Một số volume block storage gắn với một AZ. Nếu instance bị thu hồi và máy thay thế nằm ở AZ khác, volume có thể không attach được trực tiếp. Các lựa chọn gồm:

- Dùng object storage hoặc database có khả năng truy cập đa AZ.
- Replicate dữ liệu giữa các zone.
- Dùng storage có semantics multi-AZ nếu dịch vụ hỗ trợ.
- Giữ worker gần data partition và dùng scheduler hiểu locality.
- Thiết kế checkpoint không phụ thuộc local disk hoặc volume đơn zone.

Không nên mở rộng worker sang AZ khác mà chưa kiểm tra vị trí và khả năng truy cập dữ liệu. Chi phí và latency liên AZ cũng có thể làm thay đổi tổng chi phí xử lý.

### 4.3. Topology và tính sẵn sàng

Với service nhiều replica, dùng topology spread hoặc anti-affinity để tránh tất cả replica nằm cùng zone hoặc node. Cần kết hợp với minimum replica, PodDisruptionBudget và capacity đủ ở các zone còn lại.

Nếu một zone mất hoàn toàn, các zone khác phải có khả năng nhận thêm workload. Chỉ phân phối đều ở trạng thái bình thường chưa đủ; hãy kiểm tra capacity dự phòng sau khi mất một zone.

## 5. Khi nào cần đa dạng hóa region?

Đa dạng hóa region có thể tăng khả năng phục hồi trước sự cố hoặc thiếu capacity diện rộng. Tuy nhiên, region khác nhau kéo theo thay đổi lớn hơn so với AZ:

- Network latency và chi phí data transfer.
- Data residency, compliance và vị trí dữ liệu.
- Khả năng replicate database/object storage.
- DNS, routing, load balancing và failover.
- Quota, service availability và instance family khác nhau.
- Vận hành image, secret, certificate và observability đa region.

Đối với Spot worker stateless, chạy ở nhiều region có thể phù hợp nếu input và output nằm trong storage có thể truy cập an toàn, hoặc dữ liệu được replicate. Với workload phụ thuộc database ở một region, chuyển worker sang region khác có thể tăng latency và phí truyền dữ liệu, khiến phần tiết kiệm compute không còn đáng kể.

Region diversification cần được xem là một thiết kế phục hồi và dữ liệu, không chỉ là thêm một lựa chọn instance.

### 5.1. Thứ tự mở rộng phạm vi

Một cách tiếp cận thường dùng:

1. Mở rộng instance type trong cùng workload profile.
2. Cho phép nhiều AZ trong cùng region.
3. Thêm nguồn capacity on-demand hoặc capacity được bảo đảm.
4. Cân nhắc region thứ hai khi dữ liệu, network và vận hành cho phép.
5. Chỉ cân nhắc multi-cloud khi có lý do về resilience, compliance hoặc chiến lược nền tảng đủ rõ.

Mỗi bước làm tăng độ phức tạp. Mở rộng phạm vi khi lợi ích capacity và resilience lớn hơn chi phí network, dữ liệu và vận hành.

## 6. Đa dạng hóa nguồn cấp tài nguyên

Nguồn cấp capacity quyết định cách tài nguyên được cung cấp, giá và khả năng giữ máy. Các nguồn thường gặp:

| Nguồn | Đặc điểm | Vai trò trong fleet |
|---|---|---|
| On-demand | Trả theo mức sử dụng, không cần cam kết dài hạn | Capacity nền hoặc fallback linh hoạt |
| Spot/preemptible | Dùng capacity dư thừa, có thể bị thu hồi | Capacity bổ sung cho workload chịu lỗi |
| Capacity reservation | Giữ trước capacity cụ thể theo điều kiện dịch vụ | Bảo đảm khả năng khởi chạy cho nhu cầu đã xác định |
| Billing commitment (Savings Plans/Reserved Instances) | Cam kết sử dụng hoặc chi tiêu để nhận mức giá ưu đãi; semantics tùy sản phẩm | Tối ưu chi phí cho nhu cầu ổn định |
| Dedicated host/instance | Dành hạ tầng vật lý hoặc tenancy riêng theo sản phẩm | Yêu cầu license, isolation hoặc placement đặc biệt |
| Warm pool | Instance được chuẩn bị trước để rút ngắn thời gian scale-out | Giảm startup delay, có thể phát sinh chi phí duy trì |

Không phải mọi loại nguồn đều có thể trộn trong cùng một fleet policy. Cần kiểm tra API và khả năng hỗ trợ của dịch vụ.

### 6.1. Phân biệt giảm giá và giữ capacity

Một commitment hoặc Savings Plan có thể giảm đơn giá tính phí nhưng không tự động bảo đảm có máy ở một AZ hoặc instance type cụ thể. Reserved Instance cũng có thể mang nghĩa khác nhau theo phạm vi và sản phẩm; một số cam kết theo region chủ yếu là lợi ích billing, trong khi một số cam kết theo zone có thể gắn với capacity theo điều khoản của provider.

Khi cần bảo đảm có thể launch máy, kiểm tra rõ reservation có giữ capacity hay chỉ áp dụng chiết khấu. Không đưa billing commitment vào sơ đồ capacity như thể nó luôn là một pool đã được giữ sẵn.

### 6.2. On-demand baseline và Spot burst

Một mẫu phổ biến là duy trì phần capacity nền bằng on-demand hoặc nguồn đã bảo đảm, rồi dùng Spot để bổ sung khi tải tăng.

Ví dụ:

- Duy trì số worker tối thiểu để đáp ứng tải nền bằng on-demand.
- Bổ sung Spot khi queue backlog hoặc request rate tăng.
- Nếu Spot không được cấp, cho phép fallback on-demand tới một giới hạn.
- Khi tải giảm, scale-in Spot trước theo policy.
- Giữ đủ capacity dự phòng để xử lý interruption và thời gian khởi động worker mới.

Tỷ lệ on-demand/Spot cần dựa trên SLO, interruption rate, thời gian thay thế và ngân sách. Không có tỷ lệ 70/30 hoặc 80/20 đúng cho mọi hệ thống.

### 6.3. Fallback phải có giới hạn

Fallback sang on-demand có thể bảo vệ SLO khi Spot pool cạn, nhưng cũng có thể làm chi phí tăng nhanh. Cần xác định:

- Mức on-demand tối đa.
- Điều kiện bật fallback.
- Thời gian fallback được duy trì.
- Ngưỡng cảnh báo ngân sách.
- Công việc nào được ưu tiên khi capacity không đủ.
- Cách scale-in lại sau khi Spot capacity phục hồi.

Nếu không có guardrail, một đợt Spot shortage có thể khiến fleet chuyển toàn bộ sang on-demand và vượt ngân sách.

## 7. Thiết kế fleet allocation

Fleet allocation là cách bộ điều khiển chọn pool và phân bổ capacity theo danh sách lựa chọn, trọng số và chiến lược đã cấu hình.

Một policy có thể cân nhắc:

- Giá Spot hoặc discount hiện tại.
- Khả năng cấp capacity của pool.
- Interruption history hoặc tín hiệu rủi ro nếu provider cung cấp.
- Số AZ và instance type có thể dùng.
- On-demand baseline và fallback.
- Weighted capacity và mức ưu tiên của workload.

Các chiến lược như ưu tiên giá thấp, ưu tiên capacity hoặc cân bằng giá/capacity là cách triển khai thường thấy. Tên gọi và thuật toán khác nhau giữa các dịch vụ; cần đọc tài liệu đúng provider.

### 7.1. Dùng weighted capacity

Khi instance type có kích thước khác nhau, fleet nên tính capacity theo đơn vị phù hợp:

- vCPU nếu workload gần CPU-bound.
- GiB RAM nếu workload memory-bound.
- GPU hoặc accelerator unit nếu workload cần GPU.
- Worker slot hoặc throughput benchmark nếu workload có đơn vị xử lý rõ ràng.

Ví dụ một instance 8 vCPU có weight 8 và một instance 16 vCPU có weight 16 nếu mục tiêu là tổng vCPU. Nhưng nếu hiệu năng trên mỗi vCPU khác nhau, có thể dùng weight dựa trên benchmark throughput. Hãy chọn một đơn vị có thể giải thích và đo được.

Không trộn weight CPU, memory và GPU thành một con số duy nhất nếu workload có nhiều ràng buộc tài nguyên. Có thể cần tách pool theo profile hoặc dùng scheduler hiểu nhiều chiều tài nguyên.

### 7.2. Policy minh họa độc lập nhà cung cấp

Ví dụ dưới đây là mô hình cấu hình khái niệm, không phải schema API có thể áp dụng trực tiếp cho một cloud provider:

~~~yaml
fleet:
  workload: batch-worker
  minimumCapacity:
    source: on-demand
    units: 8
  maximumCapacity:
    units: 64

  compatiblePools:
    - instanceFamily: compute-general
      sizes: [large, xlarge]
      architectures: [x86_64]
      zones: [zone-a, zone-b, zone-c]
      weightUnit: vcpu

    - instanceFamily: compute-alternative
      sizes: [large, xlarge]
      architectures: [x86_64]
      zones: [zone-a, zone-b, zone-c]
      weightUnit: vcpu

  allocation:
    spot:
      strategy: capacity-aware
      diversified: true
    onDemand:
      baselineUnits: 8
      fallback:
        enabled: true
        maximumUnits: 24

  interruption:
    checkpointRequired: true
    drainBeforeTerminate: true
~~~

Policy thực tế phải dùng đúng tên instance type, zone ID, allocation strategy, capacity unit và field mà provider hỗ trợ. Ví dụ này chỉ mô tả ý tưởng: giữ capacity nền, mở rộng nhiều pool tương thích và giới hạn fallback.

## 8. Đa dạng hóa trong Kubernetes

Kubernetes có thể điều phối Pod qua nhiều node pool. Một cluster có thể có:

- Node pool on-demand cho control workload hoặc service cần ổn định.
- Node pool Spot cho batch, CI hoặc worker chịu lỗi.
- Nhiều instance family và size trong cùng pool tương thích.
- Node ở nhiều zone.
- Pool riêng cho GPU, memory-intensive hoặc storage-intensive workload.

### 8.1. Dùng label và taint

Node có thể được gắn label mô tả capacity type, zone, instance family hoặc kiến trúc. Taint giúp ngăn workload không phù hợp tự động schedule lên pool đó.

Ví dụ Pod batch chấp nhận chạy trên node Spot và chọn kiến trúc x86-64:

~~~yaml
spec:
  nodeSelector:
    kubernetes.io/arch: amd64
    capacity-type: spot
  tolerations:
    - key: capacity-type
      operator: Equal
      value: spot
      effect: NoSchedule
~~~

Label capacity-type là quy ước ví dụ; provider hoặc node provisioner có thể dùng tên label khác. Kiểm tra label thực tế trên node trước khi dùng.

### 8.2. Node affinity cho nhiều lựa chọn

Nếu workload chấp nhận nhiều family, có thể dùng node affinity với danh sách lựa chọn. Ví dụ dưới đây minh họa cách chấp nhận một trong các family được cho phép:

~~~yaml
spec:
  affinity:
    nodeAffinity:
      requiredDuringSchedulingIgnoredDuringExecution:
        nodeSelectorTerms:
          - matchExpressions:
              - key: nodepool.example.com/instance-family
                operator: In
                values:
                  - compute-family-a
                  - compute-family-b
              - key: topology.kubernetes.io/zone
                operator: In
                values:
                  - zone-a
                  - zone-b
                  - zone-c
~~~

Các label instance-family và zone cần khớp với metadata của cluster. Nếu Pod yêu cầu local storage, GPU hoặc kiến trúc cụ thể, bổ sung điều kiện tương ứng. Không đặt affinity quá chặt khiến scheduler không còn pool nào có thể đáp ứng.

### 8.3. Phân tán replica qua zone

Topology spread constraint có thể giúp phân phối replica qua các zone:

~~~yaml
spec:
  topologySpreadConstraints:
    - maxSkew: 1
      topologyKey: topology.kubernetes.io/zone
      whenUnsatisfiable: ScheduleAnyway
      labelSelector:
        matchLabels:
          app: batch-worker
~~~

ScheduleAnyway ưu tiên phân tán nhưng vẫn cho phép schedule nếu phân phối không hoàn hảo. Với dịch vụ cần bắt buộc phân tán, có thể chọn DoNotSchedule sau khi đánh giá capacity và nguy cơ Pod Pending. Một policy cứng có thể làm workload không khởi chạy khi một zone thiếu capacity.

### 8.4. PDB và node disruption

PodDisruptionBudget giúp kiểm soát một số eviction có kế hoạch. Nó không ngăn provider thu hồi node hoặc mất host đột ngột. Khi dùng Spot node:

- Duy trì đủ replica và phân tán qua node/AZ.
- Cài termination handler để nhận notice và drain khi có thể.
- Dùng checkpoint/retry cho worker.
- Bảo đảm volume và state không phụ thuộc node có thể bị thu hồi.
- Kiểm thử mất node đột ngột, không chỉ drain có kế hoạch.

## 9. Phân phối workload theo khả năng tương thích

Không phải workload nào cũng nên chạy trên mọi pool. Tách workload theo profile giúp policy rõ ràng:

| Profile | Ràng buộc | Nguồn capacity gợi ý |
|---|---|---|
| Stateless API | Latency, network, minimum healthy replicas | On-demand baseline, Spot cho phần mở rộng nếu SLO cho phép |
| Batch worker | Có thể retry/checkpoint, CPU hoặc memory rõ ràng | Nhiều Spot pool và on-demand fallback |
| GPU inference | GPU model, VRAM, driver, network | Pool GPU tương thích; capacity nền được bảo đảm nếu SLO cần |
| Data processing | Data locality, storage throughput, partition | Nhiều pool tương đương, scheduler hiểu locality |
| Stateful database | Quorum, storage, replication và failover | Capacity ổn định, reservation phù hợp và topology có kiểm soát |
| CI runner | Task độc lập, cache và artifact bền vững | Spot đa dạng, fallback khi hàng đợi vượt ngưỡng |

Tách pool cũng giúp tránh việc một workload chiếm hết capacity của workload khác. Ví dụ, batch worker có thể dùng Spot trong nhiều family; API latency-sensitive có thể dùng on-demand ở các zone được bảo đảm.

## 10. Đo lường mức độ đa dạng hóa

Số instance type trong cấu hình không đủ để chứng minh fleet có đa dạng hóa hiệu quả. Hãy đo kết quả cấp capacity và mức độ tập trung thực tế.

Các metric và báo cáo nên có:

| Chỉ số | Ý nghĩa |
|---|---|
| Pool count eligible | Số pool thực sự tương thích và được phép dùng |
| Pool count fulfilled | Số pool đang cấp capacity thực tế |
| Capacity share by type | Tỷ lệ capacity theo instance type/family |
| Capacity share by zone | Tỷ lệ capacity theo AZ |
| Capacity share by source | Tỷ lệ on-demand, Spot và nguồn khác |
| Launch fulfillment rate | Tỷ lệ yêu cầu launch được đáp ứng |
| Launch latency | Thời gian từ yêu cầu tới instance running |
| Time to ready | Thời gian tới khi workload có thể nhận việc |
| Interruption rate by pool | Tỷ lệ interruption theo type/zone/source |
| Fallback rate | Tỷ lệ capacity chuyển sang on-demand |
| Pending workload | Số Pod/job chưa có capacity |
| Cost per completed unit | Chi phí cho mỗi request/job/record hoàn tất |

Có thể dùng tỷ lệ tập trung để phát hiện fleet phụ thuộc quá nhiều vào một pool. Ví dụ, nếu 90% Spot capacity đến từ một type trong một AZ, danh sách cấu hình có nhiều lựa chọn nhưng fleet thực tế vẫn tập trung.

### 10.1. Phân biệt diversity cấu hình và diversity thực tế

**Diversity cấu hình** là số pool được phép chọn.

**Diversity thực tế** là số pool đang cấp capacity và tỷ lệ phân bổ giữa chúng.

Một pool có thể nằm trong policy nhưng chưa bao giờ được dùng vì giá cao, thiếu quota hoặc hiệu năng không đạt. Báo cáo nên thể hiện cả eligible pools lẫn fulfilled pools.

### 10.2. Đặt ngưỡng tập trung

Có thể xây dựng guardrail như:

- Không để một AZ chiếm quá tỷ lệ capacity đã định nếu workload yêu cầu multi-zone.
- Không để một Spot pool duy nhất chiếm phần lớn worker.
- Cảnh báo khi một family bị loại khỏi fleet do lỗi launch.
- Theo dõi fallback on-demand tăng bất thường.
- Kiểm tra minimum healthy capacity khi mất một zone.

Ngưỡng cần theo SLO và cấu trúc hạ tầng. Không áp dụng tỷ lệ giống nhau cho service có 3 replica và batch fleet hàng trăm worker.

## 11. Chi phí của việc đa dạng hóa

Đa dạng hóa có thể tăng resilience nhưng cũng làm phát sinh chi phí và độ phức tạp:

- Data transfer giữa AZ hoặc region.
- Replication storage và database.
- Image, artifact và cache được phân phối ở nhiều vùng.
- Capacity nền ở nhiều AZ.
- License hoặc phần mềm phụ thuộc kiến trúc.
- Monitoring, policy và automation phức tạp hơn.
- Benchmark và kiểm thử nhiều instance type.
- Dư capacity để chịu lỗi một zone hoặc một pool.

Đánh giá chi phí theo workload hoàn tất:

~~~text
Tổng chi phí =
  compute
  + storage
  + network transfer
  + replication
  + retry và checkpoint
  + capacity dự phòng
  + vận hành
~~~

Sau đó chia cho số đơn vị công việc hoàn tất hoặc số request thành công. Một fleet có giá compute thấp nhưng thường xuyên retry hoặc truyền dữ liệu liên vùng có thể đắt hơn fleet ít đa dạng nhưng ổn định.

### 11.1. Tránh tối ưu giá máy riêng lẻ

Khi so sánh hai pool, tính cả:

- Throughput thực tế mỗi giờ.
- Thời gian khởi động và warmup.
- Interruption và công việc phải chạy lại.
- Storage và network cost.
- Khả năng đạt SLO.
- Chi phí fallback và capacity dự phòng.

Nếu instance type rẻ hơn nhưng chạy chậm hơn nhiều, chi phí cho cùng một job có thể cao hơn.

## 12. Quy trình thiết kế danh sách capacity tương thích

Một quy trình thực tế:

1. **Phân loại workload:** CPU-bound, memory-bound, I/O-bound, GPU hoặc latency-sensitive.
2. **Đặt ràng buộc:** vCPU, RAM, architecture, storage, network, accelerator và OS.
3. **Chọn ứng viên:** liệt kê family/size có thể thay thế.
4. **Benchmark:** đo throughput, latency và memory trên mỗi ứng viên.
5. **Kiểm tra zone:** xác minh các type có mặt ở zone dự kiến và storage/data có thể truy cập.
6. **Chọn nguồn:** xác định phần on-demand baseline, Spot burst và reservation cần thiết.
7. **Thiết kế fallback:** giới hạn mức chuyển sang on-demand và xác định ưu tiên job.
8. **Cấu hình fleet:** dùng weighted capacity và allocation strategy phù hợp.
9. **Kiểm thử lỗi:** làm cạn một pool, một zone hoặc nguồn Spot trong môi trường thử nghiệm.
10. **Đo thực tế:** theo dõi fulfillment, interruption, concentration, SLO và cost per completed unit.
11. **Điều chỉnh:** loại ứng viên không hiệu quả và bổ sung pool đã benchmark.

Không cần bật toàn bộ lựa chọn cùng lúc. Có thể mở rộng theo từng bước và quan sát tác động trước khi thêm nhiều biến số.

## 13. Kiểm thử khả năng chịu thiếu capacity

Một fleet chỉ được xem là đa dạng hóa tốt khi vẫn hoạt động trong tình huống một phần pool không thể cấp máy.

Các kịch bản nên kiểm thử:

- Một instance type không còn capacity.
- Một AZ không thể launch máy mới.
- Spot capacity không đủ nhưng on-demand còn.
- Quota của một family bị chạm.
- Một kiến trúc CPU không tương thích với image.
- Node mới có nhưng Pod không schedule được do affinity hoặc taint.
- Storage không thể attach ở zone thay thế.
- Network hoặc dependency liên vùng bị chậm.
- Một đợt interruption ảnh hưởng đồng thời nhiều worker.
- Fallback kích hoạt và chạm giới hạn ngân sách.

Đo xem fleet có tìm được pool thay thế không, thời gian đến khi capacity healthy, backlog tăng bao nhiêu và SLO có bị vi phạm không. Sau thử nghiệm, xác minh dữ liệu và công việc không bị mất.

## 14. Các lỗi thường gặp

**Chỉ cấu hình một instance type:** pool đó cạn capacity là fleet không scale được. Mở rộng sang các type đã benchmark tương đương.

**Thêm nhiều type nhưng khác kiến trúc:** image hoặc native dependency có thể không chạy. Xác minh multi-architecture build và runtime.

**Đa dạng hóa size nhưng tính capacity theo số máy:** một máy nhỏ và máy lớn bị xem như nhau. Dùng weighted capacity hoặc workload-level metric.

**Chỉ dùng một AZ:** một zone shortage hoặc outage ảnh hưởng toàn fleet. Phân tán qua nhiều AZ nếu dữ liệu và ứng dụng hỗ trợ.

**Mở rộng region mà chưa thiết kế dữ liệu:** worker không truy cập được data hoặc phát sinh latency/egress cao. Kiểm tra replication và data locality.

**Nhầm commitment với reservation:** giảm giá billing không nhất thiết giữ capacity. Xác minh semantics của sản phẩm.

**Tất cả capacity đều là Spot:** một đợt thu hồi có thể làm mất phần lớn năng lực. Duy trì on-demand baseline hoặc fallback phù hợp.

**Fallback không có giới hạn:** thiếu Spot có thể làm chi phí on-demand tăng đột biến. Đặt maximum và budget alert.

**Topology constraint quá cứng:** scheduler không tìm được node thay thế khi một zone thiếu capacity. Cân bằng yêu cầu resilience với khả năng schedule.

**PDB được xem là bảo đảm chống thu hồi:** PDB không ngăn mất node đột ngột. Thiết kế retry, checkpoint và replica.

**Không đo concentration:** cấu hình có nhiều lựa chọn nhưng phần lớn capacity vẫn đến từ một pool. Theo dõi share theo type, zone và source.

**Chỉ nhìn giá mỗi giờ:** bỏ qua network, retry, warmup và throughput. Đo cost per completed unit.

## 15. Checklist đa dạng hóa compute

- [ ] Đã xác định profile tài nguyên và ràng buộc của workload.
- [ ] Danh sách instance type gồm nhiều lựa chọn tương thích đã benchmark.
- [ ] Đã xác minh CPU architecture, image, runtime và native dependencies.
- [ ] Đã so sánh CPU, RAM, network, storage và accelerator thực tế.
- [ ] Fleet dùng weighted capacity hoặc đơn vị capacity phù hợp.
- [ ] Có nhiều AZ khi ứng dụng và dữ liệu hỗ trợ.
- [ ] Đã kiểm tra storage locality và chi phí network liên AZ/region.
- [ ] Region thứ hai có kế hoạch data replication, routing và failover.
- [ ] Đã phân biệt on-demand, Spot, reservation và billing commitment.
- [ ] Có on-demand baseline hoặc nguồn capacity được bảo đảm cho phần cần thiết.
- [ ] Spot allocation có chiến lược và danh sách pool tương thích.
- [ ] Fallback on-demand có giới hạn capacity và ngân sách.
- [ ] Kubernetes label, taint, affinity và topology spread phù hợp.
- [ ] PDB và termination handler được dùng đúng phạm vi.
- [ ] Có metric fulfillment, interruption, concentration và time-to-ready.
- [ ] Có dashboard capacity share theo instance type, zone và source.
- [ ] Đã kiểm thử thiếu một pool, một zone và Spot capacity.
- [ ] Đo chi phí trên mỗi đơn vị công việc hoàn tất.

Đa dạng hóa instance type, zone và nguồn cấp tài nguyên giúp fleet có nhiều đường lựa chọn khi một capacity pool thiếu máy hoặc bị gián đoạn. Hãy bắt đầu từ yêu cầu thật của workload, benchmark các cấu hình tương đương, phân tán qua nhiều failure domain và kết hợp Spot với capacity ổn định. Phân biệt rõ capacity được bảo đảm với cam kết giảm giá, giới hạn fallback và đo mức tập trung thực tế sẽ giúp hệ thống mở rộng linh hoạt mà vẫn kiểm soát SLO, dữ liệu và chi phí.
