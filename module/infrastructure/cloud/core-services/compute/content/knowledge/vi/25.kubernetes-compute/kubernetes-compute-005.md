# Taint, toleration và bố trí workload đặc thù

## 1. Vì sao cần điều khiển workload chạy trên node nào?

Một Kubernetes cluster có thể gồm nhiều nhóm node với đặc điểm khác nhau: node CPU thông thường, node có GPU, node RAM lớn, node tối ưu I/O, node chạy workload có thể bị thu hồi, hoặc node dành riêng cho một nhóm dịch vụ. Nếu scheduler chỉ nhìn vào CPU và bộ nhớ còn trống, workload có thể được đặt lên node không phù hợp hoặc chiếm tài nguyên mà nhóm khác cần.

Kubernetes cung cấp nhiều cơ chế để điều khiển vị trí workload. **Taint** đánh dấu node để đẩy lùi pod không được phép hoặc không phù hợp. **Toleration** khai báo pod chấp nhận một hoặc nhiều taint. **Node selector và node affinity** giúp pod chọn node có nhãn phù hợp. **Pod affinity/anti-affinity** và **topology spread constraints** điều khiển quan hệ giữa pod và cách phân bố chúng theo node, zone hoặc fault domain.

Các cơ chế này bổ sung cho nhau. Toleration chỉ cho phép pod đi qua rào cản do taint tạo ra; nó không tự chọn node. Muốn workload GPU chạy đúng node GPU, cần vừa toleration cho taint của node, vừa selector hoặc affinity để chọn node có GPU. Muốn node chuyên dụng chỉ chạy workload của một nhóm, cần kết hợp taint với nhãn và affinity phù hợp.

Trong module **CLOUD_CORE_SERVICES_COMPUTE**, việc bố trí workload ảnh hưởng trực tiếp đến lựa chọn CPU, bộ nhớ, GPU, mạng, tính sẵn sàng và chi phí. Bài học này trình bày cách dùng taint, toleration và các quy tắc placement để bố trí workload đặc thù an toàn, có thể mở rộng và dễ vận hành.

Sau bài học, người học có thể:

- Phân biệt taint, toleration, node selector, node affinity và pod affinity.
- Giải thích ba effect `NoSchedule`, `PreferNoSchedule` và `NoExecute`.
- Đọc và viết toleration theo `key`, `value`, `operator`, `effect` và `tolerationSeconds`.
- Dành node cho workload GPU, high-memory, stateful, batch/Spot hoặc tenant cụ thể.
- Phối hợp placement với resource request/limit, topology spread và autoscaling.
- Xử lý taint trong bảo trì, node pressure, eviction và sự cố node.
- Kiểm tra nguyên nhân pod ở trạng thái Pending hoặc bị evict.

## 2. Taint và toleration hoạt động như thế nào?

### 2.1. Taint gắn trên node

Taint là thuộc tính trên node, có cấu trúc gồm:

```text
key=value:effect
```

Ví dụ:

```text
workload-class=gpu:NoSchedule
```

Taint này đánh dấu node dành cho workload GPU và yêu cầu pod phải có toleration phù hợp nếu muốn được scheduler đặt lên node đó.

Taint có ba phần:

- `key`: tên thuộc tính, ví dụ `workload-class`, `dedicated` hoặc `capacity-type`.
- `value`: giá trị mô tả, ví dụ `gpu`, `payments` hoặc `spot`.
- `effect`: hành vi áp dụng với pod không toleration taint đó.

Một node có thể mang nhiều taint cùng lúc. Pod phải toleration tất cả taint có effect ngăn cản việc lập lịch, trừ khi một toleration được viết đủ rộng để khớp nhiều taint.

### 2.2. Toleration khai báo trên pod

Toleration nằm trong `spec.template.spec.tolerations` của Pod hoặc workload template. Nó mô tả taint mà pod chấp nhận.

Ví dụ:

```yaml
tolerations:
  - key: workload-class
    operator: Equal
    value: gpu
    effect: NoSchedule
```

Toleration trên khớp taint `workload-class=gpu:NoSchedule`. Nó không buộc pod phải chạy trên node GPU; pod vẫn có thể được đặt trên node khác nếu node đó không có taint không được toleration và các điều kiện scheduling khác phù hợp.

### 2.3. Taint không phải bộ chọn node

Đây là nguyên tắc quan trọng nhất:

- Taint nói: “Pod nào không chấp nhận điều kiện này thì không được đặt lên node.”
- Toleration nói: “Pod này chấp nhận điều kiện đó.”
- Node selector/affinity nói: “Pod này cần hoặc ưu tiên node có các nhãn này.”

Do đó, muốn dành riêng node cho GPU, cần gắn taint để đẩy workload không liên quan ra ngoài, đồng thời dùng label và node affinity để GPU workload tìm đúng node.

## 3. Ba effect của taint

### 3.1. `NoSchedule`

`NoSchedule` ngăn scheduler đặt pod mới lên node nếu pod không toleration taint tương ứng. Pod đã chạy trên node trước khi taint được thêm thường vẫn tiếp tục chạy.

Dùng `NoSchedule` khi muốn dành node cho một nhóm workload, ví dụ:

```bash
kubectl taint nodes gpu-node-01 accelerator=nvidia:NoSchedule
```

Pod cần toleration `accelerator=nvidia:NoSchedule` mới được scheduler đặt lên node đó. Nếu pod không có toleration, scheduler sẽ tìm node khác phù hợp.

### 3.2. `PreferNoSchedule`

`PreferNoSchedule` là ràng buộc mềm. Scheduler cố gắng tránh đặt pod không toleration lên node có taint này, nhưng vẫn có thể dùng node nếu không có lựa chọn tốt hơn.

Dùng effect này khi muốn ưu tiên dành node cho một workload nhưng vẫn cho phép sử dụng tài nguyên khi cluster thiếu capacity. Không dùng nó nếu yêu cầu là cách ly cứng hoặc tuân thủ bắt buộc.

### 3.3. `NoExecute`

`NoExecute` có hai tác dụng:

- Pod mới không toleration taint sẽ không được đặt lên node.
- Pod đang chạy trên node nhưng không toleration taint sẽ bị evict.

Pod có thể khai báo `tolerationSeconds` để tiếp tục ở lại node trong một khoảng thời gian sau khi taint `NoExecute` xuất hiện. Hết thời gian này, pod sẽ bị evict nếu taint vẫn còn.

Ví dụ:

```yaml
tolerations:
  - key: node.kubernetes.io/unreachable
    operator: Exists
    effect: NoExecute
    tolerationSeconds: 60
```

Pod chấp nhận taint `node.kubernetes.io/unreachable` trong tối đa 60 giây trước khi bị evict theo cơ chế taint-based eviction. Đây là ví dụ về hành vi; cần cân nhắc loại workload, storage và khả năng phục hồi trước khi đặt thời gian cụ thể.

`NoExecute` thường được dùng trong xử lý node không sẵn sàng, unreachable hoặc các tình huống cần loại pod khỏi node. Nó có tác động mạnh hơn `NoSchedule`, vì vậy cần kiểm thử kỹ với workload stateful và job dài.

### 3.4. Bảng so sánh

| Effect | Pod mới không toleration | Pod đang chạy không toleration | Mục đích |
|---|---|---|---|
| `NoSchedule` | Không được schedule lên node | Tiếp tục chạy | Dành node cho nhóm workload |
| `PreferNoSchedule` | Scheduler cố tránh, nhưng có thể vẫn đặt | Tiếp tục chạy | Ưu tiên mềm khi phân bổ |
| `NoExecute` | Không được schedule lên node | Bị evict; tolerationSeconds có thể trì hoãn | Loại pod khỏi node hoặc phản ứng với tình trạng node |

### 3.5. Nhiều taint trên cùng node

Nếu node có nhiều taint, scheduler xét tất cả taint và loại bỏ những taint mà pod toleration được. Những taint còn lại có effect ngăn scheduling sẽ ảnh hưởng quyết định.

Ví dụ node có:

```text
accelerator=nvidia:NoSchedule
capacity-type=spot:NoSchedule
```

Một pod muốn chạy trên node này phải toleration cả hai taint. Tuy nhiên, pod vẫn cần node affinity hoặc selector phù hợp để chọn node có GPU và loại capacity mong muốn.

## 4. Quy tắc matching của toleration

### 4.1. `operator: Equal`

`Equal` yêu cầu key, value và effect khớp theo toleration. Ví dụ:

```yaml
tolerations:
  - key: dedicated
    operator: Equal
    value: analytics
    effect: NoSchedule
```

Toleration này khớp `dedicated=analytics:NoSchedule`. Nó không khớp `dedicated=payments:NoSchedule` hoặc `dedicated=analytics:NoExecute`.

Nếu bỏ `operator`, mặc định là `Equal`.

### 4.2. `operator: Exists`

`Exists` chỉ yêu cầu key tồn tại; không cần value cụ thể. Ví dụ:

```yaml
tolerations:
  - key: capacity-type
    operator: Exists
    effect: NoSchedule
```

Toleration này khớp các taint có key `capacity-type` và effect `NoSchedule`, bất kể value. Nó hữu ích khi workload chấp nhận nhiều giá trị capacity trong cùng một nhóm policy.

Với `operator: Exists`, trường `value` phải để trống. Nếu cần khớp một giá trị cụ thể, dùng `operator: Equal`.

Không nên dùng `Exists` quá rộng nếu các giá trị khác nhau mang ý nghĩa bảo mật hoặc vận hành khác nhau.

### 4.3. Bỏ trống key hoặc effect

Khi `operator: Exists` và `key` để trống, toleration có thể khớp mọi key; đây là toleration rất rộng. Nếu `effect` để trống, toleration có thể khớp mọi effect của key/value phù hợp.

Ví dụ toleration wildcard:

```yaml
tolerations:
  - operator: Exists
```

Toleration này cho phép pod toleration mọi taint theo quy tắc wildcard của Kubernetes. Chỉ dùng khi có lý do rõ ràng, chẳng hạn một số DaemonSet hạ tầng cần chạy trên hầu hết node. Không cấp toleration wildcard đại trà cho ứng dụng thông thường vì nó làm suy yếu ranh giới placement.

### 4.4. `tolerationSeconds`

`tolerationSeconds` chỉ có ý nghĩa với effect `NoExecute`. Nó xác định pod có thể ở lại node bao lâu sau khi taint tương ứng được thêm vào.

- Không khai báo `tolerationSeconds`: pod toleration `NoExecute` có thể ở lại node vô thời hạn khi taint còn đó.
- Khai báo số giây: pod được giữ lại trong khoảng đó rồi bị evict nếu taint vẫn còn.
- Không dùng trường này để trì hoãn `NoSchedule`; effect đó không evict pod đang chạy.

### 4.5. Một pod có thể có nhiều toleration

Pod có thể khai báo nhiều toleration để chấp nhận nhiều nhóm node, ví dụ GPU Spot ở zone cụ thể hoặc node có nhãn dedicated. Mỗi toleration nên có mục đích và owner rõ ràng. Tránh tích lũy toleration cũ sau khi workload đã đổi kiến trúc.

## 5. Node label, selector và affinity

### 5.1. Label trên node

Label mô tả thuộc tính node, ví dụ:

```bash
kubectl label nodes gpu-node-01 accelerator=nvidia
kubectl label nodes gpu-node-01 workload-class=ml
kubectl label nodes gpu-node-01 topology.kubernetes.io/zone=zone-a
```

Label được dùng bởi node selector, node affinity, topology spread và một số controller. Chỉ gắn label khi thuộc tính đã được xác minh; label sai có thể khiến workload được đặt lên node không tương thích.

### 5.2. `nodeSelector`

`nodeSelector` là cách đơn giản để yêu cầu pod chỉ chạy trên node có các label key/value nhất định.

```yaml
spec:
  nodeSelector:
    accelerator: nvidia
    workload-class: ml
```

Các điều kiện trong `nodeSelector` đều phải đúng. Cách này dễ đọc nhưng không biểu diễn được các biểu thức phức tạp hoặc lựa chọn ưu tiên.

### 5.3. Required node affinity

`requiredDuringSchedulingIgnoredDuringExecution` là điều kiện bắt buộc khi scheduler lập lịch. Nếu không có node phù hợp, pod ở trạng thái Pending.

```yaml
affinity:
  nodeAffinity:
    requiredDuringSchedulingIgnoredDuringExecution:
      nodeSelectorTerms:
        - matchExpressions:
            - key: accelerator
              operator: In
              values:
                - nvidia
            - key: workload-class
              operator: In
              values:
                - ml
```

Các biểu thức trong cùng một `nodeSelectorTerm` được kết hợp theo AND. Nhiều term trong `nodeSelectorTerms` được kết hợp theo OR.

### 5.4. Preferred node affinity

`preferredDuringSchedulingIgnoredDuringExecution` là lựa chọn ưu tiên, không bắt buộc. Scheduler cộng điểm cho node phù hợp nhưng vẫn có thể chọn node khác nếu điểm tổng thể hoặc các ràng buộc khác dẫn đến lựa chọn đó.

```yaml
affinity:
  nodeAffinity:
    preferredDuringSchedulingIgnoredDuringExecution:
      - weight: 80
        preference:
          matchExpressions:
            - key: capacity-type
              operator: In
              values:
                - spot
```

Trường `weight` nằm trong khoảng 1–100. Dùng preferred affinity khi workload có thể chạy trên nhiều loại node nhưng muốn ưu tiên một loại cụ thể, chẳng hạn Spot để tiết kiệm chi phí.

### 5.5. `IgnoredDuringExecution` có ý nghĩa gì?

Các loại node affinity ở trên được đánh giá khi scheduling. Nếu label node thay đổi sau khi pod đã chạy, Kubernetes không tự động evict pod chỉ vì điều kiện affinity không còn đúng. Nếu cần phản ứng với thay đổi trong runtime, phải có cơ chế riêng như taint-based eviction, controller hoặc quy trình vận hành.

### 5.6. Taint không thay thế affinity

Ví dụ, node có:

```text
accelerator=nvidia:NoSchedule
```

Pod toleration taint này có thể được schedule lên node GPU, nhưng cũng có thể chạy trên node CPU khác nếu không có ràng buộc placement. Muốn chắc chắn pod chỉ chạy trên node có GPU, thêm `nodeSelector` hoặc required node affinity cho label `accelerator=nvidia`.

## 6. Pod affinity, anti-affinity và topology spread

### 6.1. Pod affinity

Pod affinity cho phép đặt pod gần các pod khác có label phù hợp, ví dụ đặt service sidecar hoặc cache worker trong cùng zone với ứng dụng để giảm độ trễ. Điều kiện có thể bắt buộc hoặc ưu tiên.

Không dùng pod affinity chỉ vì hai workload thuộc cùng một ứng dụng. Đặt chúng gần nhau có thể tăng tương quan lỗi nếu cả hai nằm trên cùng node hoặc zone.

### 6.2. Pod anti-affinity

Pod anti-affinity giúp tránh đặt pod cùng nhóm trên cùng topology domain. Ví dụ, tránh đặt hai replica API trên cùng node để giảm ảnh hưởng khi một node lỗi.

```yaml
affinity:
  podAntiAffinity:
    preferredDuringSchedulingIgnoredDuringExecution:
      - weight: 100
        podAffinityTerm:
          topologyKey: kubernetes.io/hostname
          labelSelector:
            matchLabels:
              app: orders-api
```

Ví dụ này ưu tiên phân tán các pod có label `app=orders-api` qua các hostname khác nhau. Nếu dùng `requiredDuringSchedulingIgnoredDuringExecution`, cluster có thể không schedule đủ replica khi số node không đủ.

### 6.3. Topology spread constraints

Topology spread constraints giúp phân phối pod đồng đều qua các miền như zone hoặc hostname. Ví dụ:

```yaml
topologySpreadConstraints:
  - maxSkew: 1
    topologyKey: topology.kubernetes.io/zone
    whenUnsatisfiable: DoNotSchedule
    labelSelector:
      matchLabels:
        app: orders-api
```

`maxSkew: 1` yêu cầu chênh lệch số pod giữa các topology domain đủ điều kiện không vượt quá 1 theo cách tính của scheduler. Với `DoNotSchedule`, pod mới sẽ Pending nếu không thể duy trì phân bố theo constraint. `ScheduleAnyway` cho phép schedule nhưng ưu tiên node giúp giảm skew.

Topology spread khác anti-affinity: spread điều khiển độ lệch số lượng trên nhiều domain; anti-affinity diễn tả quan hệ tránh giữa các pod. Có thể kết hợp nhưng cần tránh constraint quá chặt làm thiếu khả năng schedule.

### 6.4. Kết hợp placement nhiều lớp

Một workload có thể đồng thời cần:

- Toleration để được phép vào node GPU.
- Required node affinity để chọn GPU model tương thích.
- Resource request `nvidia.com/gpu` để xin accelerator.
- Topology spread để phân bố replica qua zone.
- Pod anti-affinity để tránh hai replica cùng node.
- Node affinity hoặc taint riêng cho Spot/stable capacity.

Scheduler phải tìm node đáp ứng tất cả điều kiện bắt buộc và đủ tài nguyên. Nếu bất kỳ điều kiện nào không thỏa, pod có thể Pending dù cluster vẫn còn CPU/RAM ở node khác.

## 7. Bố trí node chuyên dụng cho GPU

### 7.1. Gắn label và taint

Node có GPU nên được gắn label mô tả loại accelerator và taint để workload không liên quan không chiếm node:

```bash
kubectl label nodes gpu-node-01 accelerator=nvidia
kubectl label nodes gpu-node-01 accelerator-model=a100
kubectl taint nodes gpu-node-01 accelerator=nvidia:NoSchedule
```

Tên label và giá trị là ví dụ. Trong production, dùng convention nhất quán và thông tin do node feature discovery hoặc cloud node controller quản lý nếu phù hợp.

### 7.2. Khai báo GPU pod

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: image-inference
  labels:
    app: image-inference
spec:
  nodeSelector:
    accelerator: nvidia
    accelerator-model: a100
  tolerations:
    - key: accelerator
      operator: Equal
      value: nvidia
      effect: NoSchedule
  containers:
    - name: inference
      image: registry.example.com/ml/inference@sha256:0123456789abcdef...
      resources:
        limits:
          nvidia.com/gpu: 1
        requests:
          cpu: "4"
          memory: "16Gi"
```

Manifest minh họa. GPU resource thường được quảng bá qua device plugin hoặc cơ chế tương ứng của vendor. Pod phải yêu cầu đúng extended resource; chỉ toleration taint không cấp GPU cho container. Digest image là placeholder cần thay bằng digest thật.

### 7.3. Kiểm tra khả năng tương thích

Ngoài số lượng GPU, kiểm tra:

- Model GPU và dung lượng VRAM.
- Driver, CUDA/runtime và framework version.
- Topology NVLink/PCIe hoặc interconnect cần thiết.
- CPU/RAM đủ cho data loader và preprocessing.
- Network throughput nếu job phân tán nhiều node.
- Storage throughput để tải model và dữ liệu.
- Node có được device plugin quảng bá GPU healthy không.

Nếu pod Pending, xem resource `nvidia.com/gpu`, taint, label, node affinity và event của device plugin. Node có GPU vật lý nhưng plugin lỗi có thể không quảng bá resource cho scheduler.

## 8. Bố trí workload high-memory, high-CPU và I/O

### 8.1. High-memory workload

Workload như in-memory analytics, JVM lớn hoặc cache có thể cần node RAM cao. Gắn label theo memory class và dùng taint để tránh pod nhỏ lấp đầy node chuyên dụng.

```text
instance-class=memory-optimized
workload-class=high-memory:NoSchedule
```

Ở đây `instance-class` là label tùy chỉnh mô tả nhóm phần cứng; `workload-class=high-memory:NoSchedule` là taint thực sự trên node.

Pod cần toleration và affinity tương ứng, đồng thời khai báo memory request/limit phù hợp. Nếu chỉ gắn label mà không có taint, workload khác vẫn có thể chiếm node. Nếu chỉ có taint và toleration mà không có affinity, pod có thể chạy trên node không đủ RAM.

### 8.2. CPU-intensive workload

Batch compute, compression hoặc compiler có thể cần node CPU nhiều core. Kiểm tra CPU generation, core count, NUMA, frequency, throttling và network. Resource request giúp scheduler đặt pod theo lượng CPU dự kiến; CPU limit có thể gây throttling nếu đặt quá thấp cho workload nhạy latency.

Taint `workload-class=compute-intensive:NoSchedule` có thể giữ node cho nhóm job này. Nhưng cần affinity chọn đúng label và request CPU để scheduler tính khả năng phù hợp.

### 8.3. Storage và I/O intensive workload

Database, search index hoặc streaming processor có thể cần node có local NVMe, network-attached volume hiệu năng cao hoặc đường mạng đặc thù. Label nên phản ánh capability đã xác minh, ví dụ `storage-tier=nvme` hoặc `network-tier=high-throughput`.

Taint có thể ngăn workload không phù hợp chiếm node, nhưng không đảm bảo storage performance. Cần kiểm tra CSI driver, volume topology, IOPS, throughput, zone và giới hạn của instance. Local ephemeral storage cần kế hoạch mất dữ liệu khi node bị thay thế.

### 8.4. Workload latency-sensitive

Workload nhạy latency có thể cần CPU pinning, topology manager, huge pages, low-latency NIC hoặc node pool riêng. Taint/affinity chỉ điều khiển placement ở mức node; chúng không tự cấu hình CPU manager, NUMA alignment hay real-time kernel.

Đặt yêu cầu tài nguyên và runtime policy tương ứng, kiểm thử latency percentile và tránh overcommit quá mức trên node chuyên dụng.

## 9. Bố trí workload trên Spot/interruptible node

### 9.1. Tách node pool

Node có thể bị thu hồi nên được đánh dấu rõ bằng label và taint:

```bash
kubectl label nodes spot-node-01 capacity-type=spot
kubectl taint nodes spot-node-01 capacity-type=spot:NoSchedule
```

Workload batch có thể toleration taint này. Workload quan trọng không có toleration sẽ tránh node Spot.

### 9.2. Ví dụ worker có thể fallback

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: batch-worker
spec:
  replicas: 5
  selector:
    matchLabels:
      app: batch-worker
  template:
    metadata:
      labels:
        app: batch-worker
    spec:
      tolerations:
        - key: capacity-type
          operator: Equal
          value: spot
          effect: NoSchedule
      affinity:
        nodeAffinity:
          preferredDuringSchedulingIgnoredDuringExecution:
            - weight: 80
              preference:
                matchExpressions:
                  - key: capacity-type
                    operator: In
                    values:
                      - spot
      containers:
        - name: worker
          image: registry.example.com/batch/worker@sha256:0123456789abcdef...
          resources:
            requests:
              cpu: "2"
              memory: "4Gi"
```

Ví dụ này cho phép worker chạy trên node Spot và ưu tiên Spot. Vì affinity là preferred, worker vẫn có thể chạy trên node không mang label Spot nếu node đó có thể nhận pod và không có taint khác ngăn cản. Đây là cách biểu diễn fallback placement; trong production cần bảo đảm stable node còn headroom và worker có checkpoint/retry.

### 9.3. Xử lý node bị thu hồi

Taint và toleration không tự xử lý toàn bộ interruption lifecycle. Cần node termination handler hoặc integration với cloud provider để nhận event, cordon/drain node, cho worker ngừng nhận job mới và checkpoint. Thiết kế vẫn phải chịu được trường hợp node biến mất đột ngột.

### 9.4. Tránh workload critical vô tình vào Spot

Không thêm toleration `capacity-type=spot` vào namespace hoặc service account một cách đại trà. Dùng admission policy để giới hạn workload nào được chấp nhận toleration này. Workload critical nên có node affinity hoặc placement policy rõ ràng, đồng thời không được schedule lên Spot nếu không đáp ứng khả năng gián đoạn.

## 10. Dành node cho tenant hoặc nhóm dịch vụ

### 10.1. Taint và label theo tenant

Ví dụ node dành cho nhóm thanh toán:

```bash
kubectl label nodes payments-node-01 tenant=payments
kubectl taint nodes payments-node-01 dedicated=payments:NoSchedule
```

Pod của nhóm thanh toán cần toleration và required node affinity:

```yaml
spec:
  tolerations:
    - key: dedicated
      operator: Equal
      value: payments
      effect: NoSchedule
  affinity:
    nodeAffinity:
      requiredDuringSchedulingIgnoredDuringExecution:
        nodeSelectorTerms:
          - matchExpressions:
              - key: tenant
                operator: In
                values:
                  - payments
```

Taint giữ workload không được phép ra khỏi node; affinity đảm bảo pod có toleration chỉ chọn node mang label tenant tương ứng. Nếu chỉ thêm toleration, pod có thể được schedule lên node không thuộc tenant.

### 10.2. Taint không phải ranh giới bảo mật hoàn chỉnh

Taint/toleration là cơ chế scheduling, không phải cơ chế xác thực hay cách ly dữ liệu. Người có quyền tạo pod có thể tự khai báo toleration nếu không có policy ngăn chặn. Vì vậy, tenant isolation cần kết hợp:

- RBAC giới hạn ai được tạo workload và sửa node.
- Admission policy giới hạn toleration, node selector và host-level privilege.
- Namespace, service account và workload identity tách biệt.
- NetworkPolicy hoặc cơ chế network segmentation.
- Pod Security Standards, seccomp, capabilities và filesystem restrictions.
- Node label được bảo vệ và quyền quản trị node hạn chế.
- Storage class, volume permission và encryption phù hợp.

Không dùng taint như bằng chứng duy nhất rằng dữ liệu của tenant đã được cách ly.

Ngoài ra, `spec.nodeName` cho phép chỉ định trực tiếp node và bỏ qua bước lựa chọn của scheduler. Không cấp quyền tùy ý đặt `nodeName` cho tenant hoặc workload thông thường; dùng admission policy để kiểm soát trường này. `NoExecute` vẫn có thể tác động đến pod sau khi được kubelet nhận trên node.

### 10.3. Nhãn node được bảo vệ

Với ranh giới placement nhạy cảm, cần ngăn kubelet tự gắn nhãn để giả mạo node đủ điều kiện. Kubernetes có Node authorizer và NodeRestriction admission plugin để giới hạn một số thao tác của kubelet. Có thể dùng label với prefix được bảo vệ như `node-restriction.kubernetes.io/` theo tài liệu Kubernetes và cấu hình cluster.

Ví dụ nhãn:

```text
example.com.node-restriction.kubernetes.io/pci-dss=true
```

Prefix cụ thể cần tuân theo quy tắc label và cơ chế bảo vệ của cluster. Việc dùng label có prefix không thay thế kiểm soát RBAC, admission và quản trị node.

## 11. Node hệ thống và DaemonSet

### 11.1. Dành node cho thành phần hệ thống

Cluster có thể dành node cho ingress, monitoring, logging, storage daemon hoặc control-plane workload. Một taint như:

```text
node-role.kubernetes.io/control-plane:NoSchedule
```

có thể ngăn workload ứng dụng thông thường vào node control plane. Thành phần hệ thống cần toleration tương ứng theo cách cluster được cài đặt.

Không tự ý xóa taint control-plane hoặc taint node hệ thống để giải quyết pod Pending. Trước tiên, xác định pod nào cần chạy ở đó và policy của cluster.

### 11.2. DaemonSet

DaemonSet thường cần chạy pod trên mỗi node đủ điều kiện, ví dụ log collector, node exporter, CNI hoặc storage agent. Kubernetes tự thêm một số toleration mặc định cho DaemonSet để chúng có thể hoạt động trong các tình huống node condition nhất định; hành vi cụ thể phụ thuộc loại taint và phiên bản.

DaemonSet vẫn có thể bị ảnh hưởng bởi taint tùy chỉnh. Nếu agent phải chạy trên GPU, Spot hoặc node chuyên dụng, cần xác định toleration tương ứng. Tránh wildcard toleration nếu agent không cần truy cập mọi node.

### 11.3. Kiểm tra DaemonSet coverage

Sau khi thêm taint mới, kiểm tra số node mong muốn và số pod DaemonSet thực sự Ready. Nếu log collector hoặc network agent không chạy trên node mới, việc giám sát và networking có thể bị thiếu dù workload ứng dụng đã được schedule.

## 12. Taint tự động do node condition

### 12.1. Các taint phổ biến

Kubernetes có thể thêm taint dựa trên tình trạng node, ví dụ:

- `node.kubernetes.io/not-ready`
- `node.kubernetes.io/unreachable`
- `node.kubernetes.io/memory-pressure`
- `node.kubernetes.io/disk-pressure`
- `node.kubernetes.io/pid-pressure`
- `node.kubernetes.io/unschedulable`
- `node.kubernetes.io/network-unavailable`

Effect và thời điểm thêm taint phụ thuộc controller, node condition và cấu hình cluster. Các taint này giúp scheduler tránh đặt pod mới lên node không đủ điều kiện hoặc xử lý pod đang chạy khi node mất liên lạc.

### 12.2. Không xóa taint áp lực thay cho xử lý nguyên nhân

Nếu node có `memory-pressure` hoặc `disk-pressure`, xóa taint thủ công không làm node có thêm RAM hoặc disk. Kubelet/controller có thể thêm lại taint, trong khi pod mới có thể bị đặt lên node đang thiếu tài nguyên.

Hãy xử lý nguyên nhân: giải phóng dung lượng theo runbook, điều chỉnh resource request/limit, tăng node capacity hoặc thay node lỗi. Sau đó xác minh node condition và taint được cập nhật tự nhiên.

### 12.3. Taint not-ready và unreachable

Khi node không Ready hoặc controller không liên lạc được, taint `NoExecute` có thể kích hoạt eviction sau thời gian toleration. Kubernetes thường thêm toleration mặc định cho một số taint not-ready/unreachable vào pod; giá trị mặc định thường là 300 giây nếu không cấu hình khác. Cần kiểm tra manifest thực tế và phiên bản cluster trước khi dựa vào con số này.

Với workload stateful hoặc có local data, eviction và reschedule có thể ảnh hưởng consistency. Cần dùng storage có semantics phù hợp, fencing và cơ chế phục hồi ứng dụng; không chỉ kéo dài `tolerationSeconds` để che giấu node mất liên lạc.

## 13. Kết hợp taint với autoscaling và node pool

### 13.1. Autoscaler cần biết label và taint của node group

Khi pod Pending vì không có node phù hợp, cluster autoscaler có thể tăng node group nếu một nhóm node có thể đáp ứng yêu cầu scheduling. Node group cần khai báo hoặc cung cấp đúng label, taint, resource và topology mà pod yêu cầu.

Nếu pod toleration `accelerator=nvidia:NoSchedule` nhưng node group GPU không được cấu hình taint/label nhất quán, autoscaler có thể không dự đoán đúng khả năng schedule hoặc node mới tạo ra không đáp ứng placement.

### 13.2. Scale-to-zero và workload đặc thù

Node pool GPU hoặc high-memory có thể scale về 0 để giảm chi phí. Khi có pod yêu cầu GPU, autoscaler cần nhận diện node group tương thích và tạo node. Thời gian boot, tải driver, device plugin và image có thể kéo dài; cần tính vào startup latency và deadline.

Nếu pod có affinity bắt buộc đến label không tồn tại trong node group, hoặc toleration không khớp taint của nhóm, pod sẽ Pending dù quota còn. Kiểm tra cấu hình template trước khi bật scale-to-zero.

### 13.3. Phối hợp với HPA

HPA tăng số replica dựa trên metric của workload; nó không tự tạo node. Nếu tất cả node phù hợp đều hết CPU/GPU hoặc bị taint, replica mới có thể Pending. Cluster autoscaler xử lý node capacity ở lớp khác.

Đặt min/max replica, node pool min/max và quota cloud đồng bộ. Với GPU, cần tính cả số accelerator, VRAM, zone capacity và quota. Với Spot pool, cần có stable fallback nếu workload không chịu được interruption.

### 13.4. Resource request là điều kiện placement quan trọng

Scheduler dựa trên resource requests để đánh giá node còn đủ tài nguyên không. Toleration không bỏ qua giới hạn CPU, memory, ephemeral storage hoặc extended resource. Nếu request GPU không đúng tên resource do device plugin quảng bá, pod sẽ Pending dù toleration và affinity đều đúng.

Đặt request sát nhu cầu thực tế, kiểm tra overcommit và theo dõi utilization. Request quá lớn làm giảm khả năng bin-pack; quá nhỏ có thể khiến workload bị tranh chấp tài nguyên.

## 14. Bảo trì node và eviction có kiểm soát

### 14.1. Cordon và drain

`kubectl cordon` đánh dấu node unschedulable để scheduler không đặt pod mới lên đó. `kubectl drain` thực hiện eviction pod theo quy trình, có xét một số đối tượng và chính sách như PodDisruptionBudget (PDB).

Ví dụ:

```bash
kubectl cordon worker-01
kubectl drain worker-01 --ignore-daemonsets
```

Lệnh drain có thể cần thêm tùy chọn theo loại pod và storage. Không thêm `--delete-emptydir-data` hoặc `--force` nếu chưa đánh giá dữ liệu và tác động. DaemonSet thường không bị xóa bởi drain; cần xử lý theo hướng dẫn phù hợp.

### 14.2. Taint để đánh dấu bảo trì

Có thể thêm taint `NoSchedule` trước khi drain để ngăn pod mới vào node:

```bash
kubectl taint nodes worker-01 maintenance=true:NoSchedule
```

Sau bảo trì, xác minh node Ready, resource và agent hoạt động rồi xóa taint:

```bash
kubectl taint nodes worker-01 maintenance-
```

Lệnh xóa taint dùng key và dấu `-`; nếu có nhiều taint cùng key nhưng khác effect/value, cần xác định chính xác taint cần xóa theo cú pháp kubectl và kiểm tra kết quả.

### 14.3. PDB và giới hạn bảo vệ

PDB giới hạn số pod có thể bị gián đoạn bởi một số voluntary eviction thông qua Eviction API. PDB không ngăn lỗi node đột ngột, không tạo thêm replica và không bảo đảm mọi loại taint-based eviction đều được trì hoãn. Đặt PDB phù hợp với số replica, topology và khả năng phục hồi ứng dụng.

Nếu PDB chặn drain, kiểm tra replica Ready, selector, `minAvailable`/`maxUnavailable` và khả năng schedule pod thay thế. Không tùy tiện xóa PDB chỉ để hoàn tất bảo trì.

### 14.4. `NoExecute` không phải công cụ drain mặc định

Thêm `NoExecute` có thể evict pod không toleration và làm gián đoạn nhanh hơn drain có kiểm soát. Với bảo trì định kỳ, cordon và drain thường giúp quản lý quá trình tốt hơn. Dùng `NoExecute` khi có mục đích rõ ràng và hiểu tác động của `tolerationSeconds`.

## 15. Troubleshooting pod Pending hoặc bị evict

### 15.1. Kiểm tra pod và event

```bash
kubectl get pods -A -o wide
kubectl describe pod <pod-name> -n <namespace>
kubectl get events -A --sort-by=.lastTimestamp
```

Trong `describe`, xem phần Events để tìm thông báo như `untolerated taint`, `didn't match node selector/affinity`, `Insufficient cpu`, `Insufficient memory` hoặc thiếu extended resource.

### 15.2. Kiểm tra taint và label của node

```bash
kubectl get nodes
kubectl describe node <node-name>
kubectl get nodes --show-labels
```

Đối chiếu `Taints`, `Labels`, `Conditions`, `Allocatable` và resource requests đang sử dụng. Xác minh node có đúng accelerator, memory class, zone hoặc capacity type mà pod yêu cầu.

### 15.3. Kiểm tra toleration trong PodSpec

```bash
kubectl get pod <pod-name> -n <namespace> -o yaml
```

Kiểm tra key, value, operator, effect và `tolerationSeconds`. Một toleration `NoSchedule` không khớp taint `NoExecute`; `Exists` với key cụ thể không tự động khớp key khác.

### 15.4. Phân loại nguyên nhân Pending

| Event/triệu chứng | Nguyên nhân thường gặp | Hướng kiểm tra |
|---|---|---|
| `untolerated taint` | Pod thiếu toleration hoặc effect/value không khớp | So sánh taint trên node với toleration |
| `didn't match node selector` | Label không tồn tại hoặc giá trị sai | Kiểm tra node labels và selector |
| `node(s) didn't match Pod's node affinity` | Required affinity quá chặt | Kiểm tra matchExpressions và node group template |
| `Insufficient nvidia.com/gpu` | Hết GPU hoặc device plugin chưa quảng bá | Kiểm tra allocatable, plugin và GPU health |
| `Insufficient memory/cpu` | Node hết resource theo request | Kiểm tra requests, allocatable và autoscaler |
| Pod bị evict sau taint | `NoExecute` và toleration hết hạn/không khớp | Xem node event, taint và tolerationSeconds |
| Pod không schedule sau scale-out | Node mới không có label/taint mong đợi hoặc quota thiếu | Kiểm tra node group, cloud quota và autoscaler events |

### 15.5. Không sửa bằng wildcard toleration ngay lập tức

Khi pod Pending do taint, thêm toleration `operator: Exists` không giới hạn có thể làm pod schedule được nhưng che giấu lỗi placement. Trước tiên xác định node nào được phép chạy workload và vì sao taint tồn tại. Thêm toleration hẹp theo key/value/effect và bổ sung affinity nếu cần.

## 16. Những sai lầm thường gặp

- **Nghĩ toleration chọn node:** pod chấp nhận taint nhưng không có affinity vẫn có thể chạy ở node khác.
- **Chỉ dùng label để dành node:** workload khác vẫn có thể được schedule lên node nếu không có taint.
- **Chỉ dùng taint mà không có affinity:** workload được phép vào nhưng có thể không chọn đúng node chuyên dụng.
- **Nhầm ba effect:** `NoSchedule`, `PreferNoSchedule` và `NoExecute` có hành vi khác nhau.
- **Dùng wildcard toleration:** vô tình cho ứng dụng vào node control-plane, Spot hoặc node đang có vấn đề.
- **Quên toleration thứ hai:** node có nhiều taint nên pod vẫn Pending.
- **Dùng `NoExecute` cho bảo trì thường xuyên:** có thể evict pod ngoài dự kiến.
- **Bỏ qua resource request:** pod toleration đúng nhưng vẫn không đủ CPU, RAM hoặc GPU.
- **Label không đáng tin:** workload được đặt lên node không có capability thật hoặc bị giả mạo nhãn.
- **Autoscaler không biết node template:** node mới tạo ra không khớp taint/label của pod.
- **Không kiểm tra DaemonSet:** node mới thiếu logging, networking hoặc security agent.
- **Coi taint là bảo mật tenant:** người tạo pod có thể thêm toleration nếu không có admission policy.
- **Xóa taint pressure thủ công:** che triệu chứng mà không giải quyết thiếu tài nguyên.
- **Không thử scale-to-zero:** workload đặc thù có thể Pending vì node pool không thể khởi tạo đúng cấu hình.

## 17. Checklist thiết kế placement

### Node pool và metadata

- [ ] Mỗi node pool có mục đích, owner và capacity class rõ ràng.
- [ ] Label phản ánh capability đã xác minh: CPU, GPU, memory, storage, zone hoặc Spot.
- [ ] Taint có key/value/effect nhất quán và được quản lý bằng automation.
- [ ] Label nhạy cảm được bảo vệ khỏi thay đổi trái phép.
- [ ] DaemonSet hạ tầng cần thiết có toleration phù hợp.

### Workload policy

- [ ] Toleration chỉ bao gồm key/value/effect mà workload cần.
- [ ] Có nodeSelector hoặc node affinity khi cần chọn node cụ thể.
- [ ] Resource requests/limits phản ánh nhu cầu CPU, RAM, GPU và ephemeral storage.
- [ ] Pod affinity/anti-affinity và topology spread phù hợp với HA.
- [ ] Workload Spot có checkpoint, retry và stable fallback.
- [ ] Workload tenant/dedicated có admission policy và RBAC hỗ trợ.

### Autoscaling và vận hành

- [ ] Node group template khai báo label, taint và resource đúng.
- [ ] HPA và cluster autoscaler có min/max đồng bộ với quota.
- [ ] Scale-to-zero đã được thử với startup time thực tế.
- [ ] Maintenance dùng cordon/drain và có kế hoạch PDB.
- [ ] Taint `NoExecute` và tolerationSeconds được kiểm thử trước khi dùng.
- [ ] Có dashboard pod Pending, taint, node condition và autoscaler event.
- [ ] Runbook nêu cách xử lý từng nhóm event và rollback placement.

## 18. Kết luận

Taint và toleration tạo ranh giới scheduling ở phía node và pod: taint đẩy lùi workload không phù hợp, toleration cho phép workload chấp nhận điều kiện đó. Ba effect có hành vi khác nhau: `NoSchedule` ngăn pod mới, `PreferNoSchedule` chỉ ưu tiên tránh node và `NoExecute` còn có thể evict pod đang chạy.

Để bố trí workload chính xác, kết hợp toleration với node selector hoặc node affinity, resource request, topology spread và policy bảo mật. GPU, high-memory, storage-intensive, Spot và tenant-specific workload đều cần label/taint/affinity phù hợp cùng cơ chế vận hành riêng. Cuối cùng, kiểm thử autoscaling, maintenance, interruption và tình huống pod Pending giúp bảo đảm placement vừa đáp ứng hiệu năng, vừa duy trì tính sẵn sàng và kiểm soát chi phí của cluster.
