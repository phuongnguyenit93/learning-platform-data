# Affinity, anti-affinity và topology spread cho pod

Trong Kubernetes, scheduler quyết định pod sẽ chạy trên node nào dựa trên tài nguyên còn trống, ràng buộc của workload và trạng thái cluster. Nếu chỉ dựa vào CPU/RAM, các replica của cùng một ứng dụng có thể bị đặt trên một node hoặc tập trung trong một zone. Khi node hay zone đó gặp sự cố, nhiều replica có thể mất khả năng phục vụ cùng lúc.

**Affinity** diễn tả nơi pod nên hoặc phải được đặt dựa trên nhãn của node hay pod khác. **Anti-affinity** diễn tả những nơi pod nên hoặc không được đặt cùng với một nhóm pod khác. **Topology spread constraints** giúp phân bố các pod tương đồng tương đối đồng đều qua các miền topology như zone hoặc hostname.

Trong **CLOUD_CORE_SERVICES_COMPUTE**, các cơ chế này giúp bố trí workload theo năng lực phần cứng, giảm điểm lỗi tập trung và cân bằng replica giữa các failure domain. Cần chọn đúng mức ràng buộc: điều kiện quá mềm có thể không bảo vệ được availability; điều kiện quá cứng có thể làm pod Pending dù cluster vẫn còn CPU/RAM.

## 1. Scheduling và topology trong Kubernetes

Kubernetes scheduler chọn node cho pod chưa được gán node. Ở mức khái quát, scheduler lọc các node không đáp ứng điều kiện bắt buộc, chấm điểm các node còn lại rồi chọn node có điểm phù hợp. Các ràng buộc về tài nguyên, taint/toleration, affinity, topology spread, volume và policy đều có thể ảnh hưởng kết quả.

### 1.1. Node, pod và topology domain

- **Node:** máy worker chạy pod.
- **Pod:** đơn vị triển khai nhỏ nhất của Kubernetes, chứa một hoặc nhiều container.
- **Topology domain:** nhóm node có cùng giá trị của một nhãn topology.
- **Topology key:** tên label dùng để chia node thành các domain.
- **Replica:** bản sao của một workload do Deployment, StatefulSet hoặc controller khác quản lý.

Các topology key phổ biến:

| Topology key | Miền phân bố | Ví dụ |
| --- | --- | --- |
| kubernetes.io/hostname | Từng node | node-a, node-b, node-c |
| topology.kubernetes.io/zone | Availability zone | zone-a, zone-b, zone-c |
| topology.kubernetes.io/region | Region | region-1, region-2 |
| Label tùy chỉnh | Miền do tổ chức định nghĩa | rack, power-domain, node-pool |

Node cần có label tương ứng thì scheduler mới có thể dùng label đó để xác định topology. Nếu một số node thiếu topology.kubernetes.io/zone, chúng có thể không được tính như một domain hợp lệ cho ràng buộc theo zone.

### 1.2. Vì sao vị trí pod quan trọng?

Giả sử một Deployment có 6 replica. Nếu cả 6 pod chạy trên một node, node đó trở thành điểm lỗi tập trung. Nếu chúng phân bố trên 3 zone, sự cố của một zone ít có khả năng làm mất toàn bộ replica.

~~~mermaid
flowchart TB
    subgraph A["Phân bố tập trung"]
      N1["Zone A / Node 1"]
      P1["Pod 1 · Pod 2 · Pod 3 · Pod 4"]
      N1 --> P1
    end
    subgraph B["Phân bố qua failure domain"]
      Z1["Zone A"] --> B1["Node A1: Pod 1, 2"]
      Z2["Zone B"] --> B2["Node B1: Pod 3, 4"]
      Z3["Zone C"] --> B3["Node C1: Pod 5, 6"]
    end
~~~

Đây là minh họa về placement. Topology spread không tự tạo thêm node hoặc zone; cluster phải có đủ node, tài nguyên, quota và network để đặt pod theo chính sách.

## 2. Các loại affinity và anti-affinity

Kubernetes cung cấp ba nhóm chính:

1. **Node affinity:** chọn node dựa trên label của node.
2. **Pod affinity:** đặt pod gần hoặc cùng topology domain với pod khác có label phù hợp.
3. **Pod anti-affinity:** tránh đặt pod cùng topology domain với pod khác có label phù hợp.

Node affinity nhìn vào thuộc tính của node. Pod affinity và anti-affinity nhìn vào vị trí của những pod đang tồn tại hoặc được scheduler tính đến.

### 2.1. Required và preferred

Các cơ chế affinity có hai kiểu ràng buộc phổ biến:

| Kiểu | Trường cấu hình | Ý nghĩa |
| --- | --- | --- |
| Bắt buộc khi lập lịch | requiredDuringSchedulingIgnoredDuringExecution | Node phải thỏa điều kiện; nếu không, pod không được schedule |
| Ưu tiên khi lập lịch | preferredDuringSchedulingIgnoredDuringExecution | Scheduler cộng điểm ưu tiên; nếu không có node phù hợp, pod vẫn có thể được đặt ở node khác |

Phần **IgnoredDuringExecution** có nghĩa là scheduler dùng điều kiện khi lập lịch. Nếu label thay đổi sau khi pod đã chạy, Kubernetes không tự động evict pod chỉ vì điều kiện affinity không còn đúng.

Với preferred affinity, mỗi preference có **weight** từ 1 đến 100. Weight lớn hơn làm preference đó đóng góp nhiều điểm hơn khi scheduler chấm điểm; nó không phải tỷ lệ phần trăm và cũng không bảo đảm pod luôn được đặt đúng node mong muốn.

## 3. Node affinity: chọn node theo thuộc tính

Node affinity phù hợp khi workload cần một nhóm node có đặc điểm cụ thể, chẳng hạn:

- CPU-optimized hoặc memory-optimized.
- Có GPU/accelerator.
- Có SSD cục bộ hoặc thiết bị đặc thù.
- Thuộc node pool dành cho workload tin cậy.
- Chạy trên kiến trúc CPU hoặc hệ điều hành được hỗ trợ.

Label có thể do cloud provider, Kubernetes hoặc đội nền tảng gắn vào node. Một số label tiêu chuẩn:

- kubernetes.io/arch
- kubernetes.io/os
- node.kubernetes.io/instance-type
- topology.kubernetes.io/zone
- topology.kubernetes.io/region

### 3.1. Node affinity bắt buộc

Ví dụ pod chỉ được chạy trên node có label workload-tier=compute:

~~~yaml
apiVersion: v1
kind: Pod
metadata:
  name: cpu-worker
  labels:
    app: cpu-worker
spec:
  affinity:
    nodeAffinity:
      requiredDuringSchedulingIgnoredDuringExecution:
        nodeSelectorTerms:
          - matchExpressions:
              - key: workload-tier
                operator: In
                values:
                  - compute
  containers:
    - name: worker
      image: example.invalid/cpu-worker:v1
      resources:
        requests:
          cpu: "1"
          memory: "1Gi"
~~~

Đây là ví dụ cấu trúc YAML; thay image bằng image thực tế trước khi triển khai. Nếu không node nào mang label workload-tier=compute hoặc các node đó không đủ tài nguyên, pod sẽ ở trạng thái Pending.

### 3.2. Node selector expressions

Các operator thường dùng trong matchExpressions:

| Operator | Ý nghĩa |
| --- | --- |
| In | Giá trị label phải nằm trong danh sách |
| NotIn | Giá trị label không nằm trong danh sách |
| Exists | Node phải có label với key đó |
| DoesNotExist | Node không được có label đó |
| Gt | Giá trị số của label phải lớn hơn giá trị so sánh |
| Lt | Giá trị số của label phải nhỏ hơn giá trị so sánh |

Trong một nodeSelectorTerm, các expression được kết hợp theo AND. Nhiều nodeSelectorTerms được kết hợp theo OR. Có thể dùng nhiều expression để yêu cầu node vừa thuộc pool compute vừa ở một kiến trúc CPU phù hợp.

Ví dụ:

~~~yaml
nodeAffinity:
  requiredDuringSchedulingIgnoredDuringExecution:
    nodeSelectorTerms:
      - matchExpressions:
          - key: workload-tier
            operator: In
            values: ["compute"]
          - key: kubernetes.io/arch
            operator: In
            values: ["amd64"]
      - matchExpressions:
          - key: workload-tier
            operator: In
            values: ["compute"]
          - key: kubernetes.io/arch
            operator: In
            values: ["arm64"]
~~~

Hai term trên cho phép node thuộc pool compute với kiến trúc amd64 hoặc arm64. Image ứng dụng phải hỗ trợ cả hai kiến trúc nếu muốn dùng cả hai nhóm node.

### 3.3. Node affinity ưu tiên

Khi workload có thể chạy trên nhiều loại node nhưng muốn ưu tiên một nhóm, dùng preferred:

~~~yaml
affinity:
  nodeAffinity:
    preferredDuringSchedulingIgnoredDuringExecution:
      - weight: 80
        preference:
          matchExpressions:
            - key: storage-tier
              operator: In
              values: ["ssd"]
      - weight: 30
        preference:
          matchExpressions:
            - key: node-pool
              operator: In
              values: ["batch"]
~~~

Scheduler ưu tiên node có điểm phù hợp cao hơn nhưng vẫn có thể chọn node khác khi cần. Nếu workload bắt buộc phải có SSD để đáp ứng correctness hoặc SLO, dùng required thay vì chỉ dùng preferred.

### 3.4. Node affinity và nodeSelector

nodeSelector là cách đơn giản để yêu cầu node có một tập label key/value. nodeAffinity biểu đạt được nhiều điều kiện hơn, bao gồm nhiều operator và preference.

Có thể dùng cả hai; khi đó node phải thỏa cả nodeSelector và nodeAffinity. Nếu điều kiện bị mâu thuẫn, pod không thể được schedule.

## 4. Pod affinity: đặt pod gần pod khác

Pod affinity cho phép scheduler tìm node thuộc topology domain đang có pod khớp với label selector. Ví dụ:

- Đặt worker gần cache replica cùng zone để giảm network latency.
- Đặt sidecar/service phụ trợ cùng node hoặc zone với workload cần nó.
- Đặt pod xử lý dữ liệu gần pod giữ shard dữ liệu.

Pod affinity không có nghĩa hai pod nhất thiết phải nằm trên cùng một node. Phạm vi được quyết định bởi topologyKey:

- kubernetes.io/hostname: cùng node.
- topology.kubernetes.io/zone: cùng zone.
- Label rack hoặc failure domain: cùng miền tùy chỉnh.

### 4.1. Pod affinity bắt buộc

Ví dụ worker cần nằm trong cùng zone với pod cache thuộc namespace platform:

~~~yaml
affinity:
  podAffinity:
    requiredDuringSchedulingIgnoredDuringExecution:
      - labelSelector:
          matchLabels:
            app: cache
        namespaces:
          - platform
        topologyKey: topology.kubernetes.io/zone
~~~

Scheduler tìm topology domain có pod app=cache trong namespace platform, sau đó chỉ xem xét node thuộc domain phù hợp. Nếu không có pod cache phù hợp hoặc node không có topology label cần thiết, điều kiện có thể không thỏa.

### 4.2. Pod affinity ưu tiên

Nếu chỉ muốn ưu tiên cùng zone nhưng vẫn cho phép placement khác khi thiếu node:

~~~yaml
affinity:
  podAffinity:
    preferredDuringSchedulingIgnoredDuringExecution:
      - weight: 60
        podAffinityTerm:
          labelSelector:
            matchLabels:
              app: cache
          namespaces:
            - platform
          topologyKey: topology.kubernetes.io/zone
~~~

Pod affinity có thể tạo phụ thuộc về thứ tự khởi chạy. Nếu một workload bắt buộc phải nằm cùng topology với một pod thuộc workload khác chưa được tạo hoặc chưa thể schedule, pod có thể chờ. Kubernetes có xử lý đặc biệt cho một số trường hợp self-affinity để pod đầu tiên của nhóm có thể khởi chạy; tuy nhiên, không nên dựa vào cơ chế đó để giải quyết dependency giữa hai workload độc lập. Với nhóm replica cần tự khởi tạo độc lập, hãy cân nhắc topology spread hoặc preferred affinity.

### 4.3. Namespace và label selector

Pod affinity/anti-affinity có thể giới hạn pod được so khớp bằng:

- labelSelector: chọn pod theo label.
- namespaces: danh sách namespace được xét.
- namespaceSelector: chọn namespace theo label.

Nếu không khai báo namespace scope, selector mặc định xét pod trong namespace của pod đang được lập lịch. Cần chọn namespace rõ ràng để tránh vô tình tạo quan hệ affinity với workload không liên quan.

## 5. Pod anti-affinity: tránh đặt replica cùng miền lỗi

Pod anti-affinity diễn tả nơi pod không nên hoặc không được đặt cùng các pod có label phù hợp. Đây là cơ chế quan trọng để phân tán replica của một dịch vụ.

Ví dụ, nếu hai pod cùng ứng dụng không được chạy trên cùng hostname, có thể dùng:

~~~yaml
affinity:
  podAntiAffinity:
    requiredDuringSchedulingIgnoredDuringExecution:
      - labelSelector:
          matchLabels:
            app: checkout
        topologyKey: kubernetes.io/hostname
~~~

Điều kiện này ngăn scheduler đặt pod mới trên node đã có pod app=checkout trong cùng topology domain. Khi topology key là hostname, mỗi node chỉ có tối đa một pod khớp selector trong phạm vi ràng buộc.

### 5.1. Required anti-affinity

Required anti-affinity là ràng buộc cứng. Nó hữu ích khi yêu cầu không đồng vị trí là bắt buộc, chẳng hạn:

- Replica chứa thành phần cần độc lập node để giảm ảnh hưởng khi node lỗi.
- Workload cần tách biệt theo host vì license hoặc giới hạn tài nguyên.
- Thành phần có rủi ro tranh chấp tài nguyên nếu đặt cùng node.

Đổi lại, số pod có thể chạy bị giới hạn bởi số topology domain phù hợp. Nếu Deployment có 5 replica nhưng chỉ có 4 node eligible và yêu cầu tối đa một replica trên mỗi hostname, ít nhất một pod sẽ Pending.

### 5.2. Preferred anti-affinity

Nếu phân tán là mong muốn nhưng không phải điều kiện tuyệt đối, dùng preferred:

~~~yaml
affinity:
  podAntiAffinity:
    preferredDuringSchedulingIgnoredDuringExecution:
      - weight: 100
        podAffinityTerm:
          labelSelector:
            matchLabels:
              app: checkout
          topologyKey: kubernetes.io/hostname
~~~

Scheduler cố gắng chọn node không có pod cùng ứng dụng, nhưng khi thiếu lựa chọn, nó vẫn có thể đặt nhiều replica trên một node. Điều này tăng khả năng schedule và tận dụng capacity tốt hơn.

### 5.3. Anti-affinity theo zone

Có thể đặt topologyKey là topology.kubernetes.io/zone để tránh cùng zone. Tuy nhiên, required anti-affinity theo zone có nghĩa các pod khớp selector không được chia sẻ zone. Nếu có 3 replica và 3 zone, mỗi zone chỉ có thể nhận một replica. Nếu có 4 replica, replica thứ tư không thể schedule theo điều kiện này.

Đối với mục tiêu phân bố cân bằng giữa các zone, topology spread thường phù hợp hơn anti-affinity cứng. Anti-affinity theo zone chỉ nên dùng khi thật sự cần tách từng pod sang các zone khác nhau.

### 5.4. Giới hạn và chi phí scheduler

Pod anti-affinity cần scheduler kiểm tra quan hệ giữa pod và topology domain. Với cluster lớn, nhiều pod và selector rộng, việc đánh giá có thể làm tăng chi phí lập lịch. Chỉ nên áp dụng selector đủ hẹp, topology key cần thiết và mức required khi nghiệp vụ thật sự yêu cầu.

Một số cluster còn có admission policy giới hạn topology key được dùng cho required pod anti-affinity. Kiểm tra policy của cluster nếu manifest hợp lệ nhưng bị từ chối khi tạo.

## 6. Topology spread constraints

Topology spread constraints giúp phân phối các pod khớp selector đồng đều hơn qua các topology domain. Thay vì cấm hoàn toàn hai pod cùng domain như required anti-affinity, spread giới hạn độ chênh lệch số pod giữa các domain.

Ví dụ, 7 replica trên 3 zone có thể được phân bố 3-2-2. Chênh lệch giữa domain có nhiều pod nhất và ít nhất là 1.

### 6.1. Các trường quan trọng

| Trường | Ý nghĩa |
| --- | --- |
| maxSkew | Độ chênh lệch tối đa cho phép giữa domain có nhiều và ít pod theo cách tính của scheduler |
| topologyKey | Label node dùng để chia topology domain |
| whenUnsatisfiable | Cách xử lý nếu placement làm vượt maxSkew |
| labelSelector | Chọn nhóm pod được đếm trong từng domain |
| minDomains | Số topology domain tối thiểu mong muốn trong một số điều kiện spread |
| nodeAffinityPolicy | Xác định node affinity/selector có được dùng khi tính eligible domains hay không, nếu phiên bản hỗ trợ |
| nodeTaintsPolicy | Xác định taint/toleration có được xét khi tính eligible domains hay không, nếu phiên bản hỗ trợ |

maxSkew là số nguyên dương, tối thiểu là 1. topologyKey phải tồn tại trên node liên quan. labelSelector cần chọn đúng các pod thuộc workload muốn phân bố.

### 6.2. DoNotSchedule và ScheduleAnyway

whenUnsatisfiable có hai lựa chọn:

- **DoNotSchedule:** nếu đặt pod vào domain làm độ lệch vượt maxSkew, scheduler không đặt pod đó ở node đó. Pod có thể Pending cho đến khi có domain hoặc capacity phù hợp.
- **ScheduleAnyway:** scheduler vẫn có thể đặt pod dù độ lệch vượt mục tiêu, nhưng ưu tiên node giúp cải thiện cân bằng. Đây là preference, không phải bảo đảm phân bố tuyệt đối.

Chọn DoNotSchedule khi phân bố là yêu cầu availability cứng và tổ chức chấp nhận pod Pending nếu thiếu domain. Chọn ScheduleAnyway khi muốn phân bố tốt nhưng vẫn ưu tiên workload chạy được.

### 6.3. Cách hiểu maxSkew

Giả sử có 3 zone eligible và 6 pod khớp selector:

| Zone | Số pod |
| --- | ---: |
| zone-a | 2 |
| zone-b | 2 |
| zone-c | 2 |

Độ lệch là 2 - 2 = 0. Nếu có 7 pod, phân bố 3-2-2 có độ lệch 1.

Với maxSkew: 1, scheduler cố giữ chênh lệch không quá 1 khi dùng DoNotSchedule. Nếu chỉ còn hai zone eligible nhưng minDomains: 3, cách tính global minimum có thể khiến scheduler không cho đặt thêm pod vào một domain đã có pod nếu việc đó làm lệch vượt ngưỡng. Đây là cách dùng để tránh dồn replica vào số zone ít hơn mục tiêu, nhưng có thể làm giảm capacity chạy được khi một zone mất.

### 6.4. minDomains

minDomains quy định số domain eligible tối thiểu để áp dụng cách tính spread. Khi số domain eligible ít hơn minDomains, global minimum được coi là 0 cho mục đích tính skew. Trường này chỉ dùng cùng whenUnsatisfiable: DoNotSchedule và cần cluster version hỗ trợ.

Ví dụ minDomains: 3 thể hiện ý định cần ít nhất ba domain đủ điều kiện để giữ phân bố theo chính sách. Nếu chỉ còn hai zone, pod có thể bị Pending thay vì tập trung vào hai zone còn lại. Đây là một lựa chọn availability/capacity có đánh đổi rõ ràng.

Nếu mục tiêu là tiếp tục phục vụ khi một zone lỗi, cần cân nhắc minDomains, số replica, capacity còn lại và việc có chấp nhận phân bố lệch tạm thời hay không.

### 6.5. Eligible topology domains

Scheduler không đếm mọi node trong cluster một cách mù quáng. Tập node eligible có thể bị ảnh hưởng bởi:

- nodeSelector và node affinity của pod.
- Taint/toleration theo chính sách topology spread.
- Node có label topology key cần thiết hay không.
- Các ràng buộc khác khiến node không thể nhận pod.

Nếu một zone không có node phù hợp với node affinity, zone đó không nhất thiết được tính như một domain có thể nhận pod. Khi debug, hãy kiểm tra node labels và điều kiện eligibility, không chỉ nhìn số zone trong cloud console.

## 7. Ví dụ Deployment phân bố replica qua zone và node

Manifest sau minh họa một API có 6 replica:

- Chỉ chạy trên node pool workload-tier=compute.
- Bắt buộc phân bố tương đối đều qua ít nhất 3 zone.
- Ưu tiên phân bố trên các hostname khác nhau.

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: checkout
  labels:
    app: checkout
spec:
  replicas: 6
  selector:
    matchLabels:
      app: checkout
  template:
    metadata:
      labels:
        app: checkout
    spec:
      affinity:
        nodeAffinity:
          requiredDuringSchedulingIgnoredDuringExecution:
            nodeSelectorTerms:
              - matchExpressions:
                  - key: workload-tier
                    operator: In
                    values:
                      - compute
      topologySpreadConstraints:
        - maxSkew: 1
          minDomains: 3
          topologyKey: topology.kubernetes.io/zone
          whenUnsatisfiable: DoNotSchedule
          labelSelector:
            matchLabels:
              app: checkout
        - maxSkew: 1
          topologyKey: kubernetes.io/hostname
          whenUnsatisfiable: ScheduleAnyway
          labelSelector:
            matchLabels:
              app: checkout
      containers:
        - name: api
          image: registry.example.invalid/checkout:v3
          ports:
            - name: http
              containerPort: 8080
          resources:
            requests:
              cpu: "500m"
              memory: "512Mi"
            limits:
              cpu: "2"
              memory: "2Gi"
~~~

Image registry trong ví dụ là placeholder; cần thay bằng image hợp lệ trước khi áp dụng. minDomains yêu cầu phiên bản Kubernetes hỗ trợ trường này. Nếu cluster chưa hỗ trợ, bỏ trường hoặc điều chỉnh chính sách theo phiên bản thực tế.

Với ba zone có node eligible, 6 replica có thể phân bố 2-2-2. Ràng buộc hostname ở chế độ ScheduleAnyway giúp scheduler ưu tiên node khác nhau nhưng vẫn có thể đặt thêm replica trên cùng node nếu thiếu lựa chọn.

Nếu yêu cầu mỗi node tối đa một replica, thay hostname spread bằng required pod anti-affinity. Tuy nhiên, khi số replica lớn hơn số node eligible, các pod dư sẽ Pending.

## 8. Kết hợp node affinity, pod anti-affinity và topology spread

Các cơ chế giải quyết các câu hỏi khác nhau:

| Cơ chế | Câu hỏi |
| --- | --- |
| Node affinity | Pod được chạy trên loại node nào? |
| Pod affinity | Pod nên ở gần nhóm pod nào? |
| Pod anti-affinity | Pod không nên hoặc không được ở cùng miền với nhóm pod nào? |
| Topology spread | Replica nên phân bố đồng đều thế nào qua các miền? |

Có thể kết hợp nhiều cơ chế trong cùng pod spec. Scheduler phải tìm node thỏa tất cả điều kiện bắt buộc; các preference chỉ tác động đến điểm số.

Ví dụ thiết kế:

- Node affinity required chọn node pool có CPU phù hợp.
- Pod anti-affinity preferred giảm khả năng hai replica cùng node.
- Topology spread DoNotSchedule giới hạn chênh lệch replica giữa zone.

Tránh áp dụng đồng thời nhiều ràng buộc cứng có cùng mục tiêu nhưng khác phạm vi. Ví dụ required anti-affinity theo hostname cùng topology spread hostname DoNotSchedule có thể thừa; required anti-affinity theo zone cùng minDomains có thể khiến workload không schedule được khi một zone mất.

## 9. Affinity và topology spread ảnh hưởng đến autoscaling

Scheduler chỉ chọn trong số node hiện có và eligible. Cluster Autoscaler hoặc cơ chế node provisioning có thể thêm node khi pod Pending vì thiếu tài nguyên, nhưng không phải mọi ràng buộc đều có thể được giải quyết bằng cách thêm node.

### 9.1. Khi autoscaler có thể giúp

- Node pool được phép scale-out.
- Cloud provider còn quota và capacity.
- Pod yêu cầu resource nằm trong giới hạn node pool.
- Topology domain mới có thể được tạo và có label phù hợp.
- Ràng buộc affinity/spread có thể được đáp ứng bởi node mới.

### 9.2. Khi autoscaler không giải quyết được

- Required anti-affinity đòi một node/domain riêng nhưng giới hạn node pool đã đạt max.
- Pod yêu cầu zone không còn capacity.
- Node affinity chỉ chọn label không có trong bất kỳ node pool nào.
- PVC bị ràng buộc vào zone khác với nơi pod được phép chạy.
- Taint không có toleration tương ứng.
- Quota hoặc IP subnet không đủ.
- minDomains yêu cầu số domain nhiều hơn số domain có thể cấp phát.

Autoscaler không thể tạo một topology domain vật lý mới nếu cloud region không cung cấp zone đó hoặc provider không còn capacity.

## 10. Tương tác với Deployment, HPA và PodDisruptionBudget

### 10.1. Deployment rollout

Khi Deployment rolling update, scheduler có thể phải đặt pod mới trong lúc pod cũ vẫn đang chạy. Nếu dùng required anti-affinity theo hostname, mỗi node chỉ có một replica, và maxSurge tạo thêm pod mới trước khi pod cũ bị xóa, pod mới có thể Pending do không có node trống.

Hướng xử lý:

- Đảm bảo có node/capacity dự phòng cho surge.
- Chọn maxSurge và maxUnavailable phù hợp.
- Dùng preferred anti-affinity nếu yêu cầu không cần tuyệt đối.
- Dùng topology spread để cân bằng replica nhưng vẫn cho phép placement có kiểm soát.
- Kiểm thử rollout với số node tối thiểu, không chỉ khi cluster dư capacity.

### 10.2. Horizontal Pod Autoscaler

HPA thay đổi số replica dựa trên metric. Khi replica tăng, topology spread và affinity quyết định các pod mới có thể chạy ở đâu.

Nếu HPA tăng từ 3 lên 12 nhưng chỉ có 3 node eligible và required anti-affinity một pod mỗi hostname, tối đa 3 pod có thể chạy. HPA vẫn có thể hiển thị desired replicas là 12 trong khi nhiều pod Pending.

Theo dõi đồng thời:

- HPA desired/current replicas.
- Deployment available/ready replicas.
- Pod Pending và scheduler events.
- Node pool desired/actual capacity.
- Topology distribution theo zone và hostname.

### 10.3. PodDisruptionBudget

PodDisruptionBudget (PDB) giới hạn số pod có thể bị gián đoạn trong các voluntary disruption được hỗ trợ, chẳng hạn drain node. PDB không quyết định pod nằm ở đâu và không thay thế affinity hoặc topology spread.

PDB cũng không bảo đảm chống lại mọi involuntary disruption như node crash hoặc zone outage. Thiết kế cần kết hợp replica, placement, readiness, autoscaling và PDB.

## 11. Stateful workload và volume topology

Với StatefulSet hoặc pod dùng PersistentVolume, placement còn chịu ảnh hưởng bởi topology của storage.

- Một số block volume chỉ attach trong một zone.
- PersistentVolume có thể mang node affinity hoặc topology constraint.
- Pod có thể bị ràng buộc phải chạy cùng zone với volume.
- Replica database có thể cần một volume riêng cho từng pod.

Nếu topology spread yêu cầu phân bố pod qua ba zone nhưng chỉ có volume ở zone-a, scheduler không thể đưa pod gắn volume đó sang zone-b hoặc zone-c. Cần dùng storage class và volume binding mode phù hợp, ví dụ WaitForFirstConsumer khi thích hợp, để volume được provision theo vị trí pod được schedule.

Không di chuyển StatefulSet pod tùy tiện chỉ để cân bằng zone. Kiểm tra replication, quorum, consistency, volume attachment và quy trình failover của database trước khi thay đổi placement.

## 12. Bảo mật label và node isolation

Node affinity có thể được dùng để tách workload nhạy cảm khỏi node pool thông thường. Tuy nhiên, nếu người dùng workload có thể tự gắn label lên node hoặc thay đổi label tin cậy, họ có thể làm sai mục tiêu isolation.

Với yêu cầu bảo mật, cần:

- Giới hạn RBAC ai được sửa node labels.
- Dùng admission policy để kiểm soát pod affinity và node selector.
- Dùng label dành riêng cho node isolation theo cơ chế bảo vệ phù hợp.
- Cân nhắc NodeRestriction admission plugin và label có domain kết thúc bằng .node-restriction.kubernetes.io, ví dụ example.com.node-restriction.kubernetes.io/fips, khi plugin được bật và cấu hình phù hợp.
- Kết hợp taint/toleration, namespace policy và network policy.
- Không xem node affinity là ranh giới bảo mật duy nhất.

Taint/toleration và affinity có vai trò khác nhau: taint với hiệu ứng NoSchedule hoặc NoExecute ngăn pod không có toleration phù hợp; PreferNoSchedule chỉ là ưu tiên tránh node. Toleration cho phép pod được xét trên node có taint nhưng không tự làm pod ưu tiên node đó. Affinity mới là cơ chế chọn hoặc ưu tiên vị trí.

## 13. Kiểm tra topology và placement trong cluster

Trước khi áp dụng policy, kiểm tra node labels:

~~~bash
kubectl get nodes --show-labels

kubectl get nodes \
  -L topology.kubernetes.io/zone,kubernetes.io/hostname,workload-tier
~~~

Kiểm tra vị trí pod:

~~~bash
kubectl get pods -n production -l app=checkout -o wide
kubectl get deployment checkout -n production
kubectl rollout status deployment/checkout -n production
~~~

Nếu pod Pending, xem mô tả và event:

~~~bash
kubectl describe pod POD_NAME -n production
kubectl get events -n production --sort-by=.lastTimestamp
~~~

Các thông báo thường gặp:

| Event/reason | Nguyên nhân cần kiểm tra |
| --- | --- |
| didn't match Pod's node affinity/selector | Node không có label hoặc không thỏa node affinity |
| didn't match pod anti-affinity rules | Required anti-affinity không tìm được node phù hợp |
| didn't match pod topology spread constraints | Placement làm vi phạm maxSkew với DoNotSchedule |
| Insufficient cpu / Insufficient memory | Node eligible không còn đủ resource request |
| untolerated taint | Pod thiếu toleration hoặc node pool không phù hợp |
| Volume node affinity conflict | Pod và persistent volume yêu cầu topology khác nhau |

Không nên gỡ mọi ràng buộc ngay khi thấy pod Pending. Trước tiên xác định ràng buộc nào làm pod không schedule được và vì sao ràng buộc đó được đặt ra.

## 14. Troubleshooting theo tình huống

### 14.1. Pod Pending dù cluster còn CPU

CPU/RAM còn trống trên node không có nghĩa node đó eligible. Kiểm tra node affinity, taint/toleration, pod anti-affinity, topology spread, volume topology và resource request.

### 14.2. Replica dồn vào một zone

Kiểm tra:

- Node có label topology.kubernetes.io/zone đầy đủ không?
- labelSelector có khớp đúng pod template labels không?
- whenUnsatisfiable có đang là ScheduleAnyway không?
- Node affinity có loại bỏ các zone khác không?
- Các zone khác có node eligible và đủ tài nguyên không?
- Có minDomains và giá trị đó có phù hợp khi một zone lỗi không?

Nếu dùng ScheduleAnyway, phân bố lệch có thể được chấp nhận khi scheduler không có lựa chọn tốt hơn.

### 14.3. Deployment rollout bị treo

Nếu pod mới Pending do anti-affinity, xem số node eligible, maxSurge, maxUnavailable và số replica hiện có. Có thể cần tăng tạm node capacity hoặc chuyển sang preferred anti-affinity nếu không cần ràng buộc cứng.

### 14.4. Pod không chuyển sang zone khác khi một zone lỗi

Kiểm tra zone còn lại có đủ node, CPU/RAM, IP và storage không. Nếu minDomains buộc phải có ba domain nhưng chỉ còn hai, DoNotSchedule có thể giữ pod Pending. Đây là hành vi chính sách, không nhất thiết là lỗi scheduler.

### 14.5. Pod affinity tạo phụ thuộc khởi động

Nếu pod cần một pod khác đang chưa tồn tại, required affinity có thể ngăn pod được schedule. Xem xét khởi động dependency trước, dùng preferred affinity hoặc thay bằng topology spread nếu mục tiêu là phân bố replica chứ không phải co-location.

## 15. Chọn cơ chế nào cho từng mục tiêu?

| Mục tiêu | Cơ chế gợi ý | Lưu ý |
| --- | --- | --- |
| Chỉ chạy trên node có GPU | Required node affinity | Kết hợp resource request/extended resource và taint/toleration |
| Ưu tiên node có SSD | Preferred node affinity | Dùng required nếu SSD là điều kiện bắt buộc |
| Đặt worker cùng zone với cache | Pod affinity theo zone | Kiểm soát namespace và dependency |
| Không đặt hai replica trên cùng node | Required pod anti-affinity theo hostname | Cần ít node eligible ít nhất tương ứng số replica |
| Ưu tiên tách replica trên node | Preferred pod anti-affinity | Cho phép scheduler tận dụng capacity khi cần |
| Cân bằng replica giữa zone | Topology spread theo zone | DoNotSchedule nghiêm ngặt; ScheduleAnyway mềm hơn |
| Cân bằng giữa node trong mỗi zone | Topology spread theo hostname | Kết hợp với spread theo zone khi cần |
| Bắt buộc workload nhạy cảm trên node tin cậy | Required node affinity với label được bảo vệ | Kết hợp RBAC, admission policy và taint |

## 16. Quy trình thiết kế placement policy

1. **Xác định mục tiêu:** hiệu năng, phần cứng, isolation hay availability.
2. **Chọn failure domain:** node, rack, zone hay region.
3. **Kiểm tra label:** xác minh topology key và label của node pool.
4. **Chọn hard/soft constraint:** required khi không thỏa là không được chạy; preferred khi chỉ cần ưu tiên.
5. **Chọn selector chính xác:** labelSelector phải chọn đúng nhóm pod, namespace phải đúng phạm vi.
6. **Tính capacity:** số replica, node eligible, CPU/RAM request, max node và quota.
7. **Đánh giá tình huống lỗi:** một node hoặc một zone mất thì còn bao nhiêu domain?
8. **Kiểm tra rollout/HPA:** bảo đảm surge và scale-out không tạo pod Pending ngoài dự kiến.
9. **Kiểm tra storage:** xác minh volume topology phù hợp với placement.
10. **Thử nghiệm và quan sát:** tạo pod, scale replica, drain node và mô phỏng zone unavailable trong môi trường thử.
11. **Đo kết quả:** phân bố thực tế, Pending time, latency liên node/zone và mức sử dụng tài nguyên.
12. **Điều chỉnh:** cập nhật policy theo SLO, capacity và kết quả thử nghiệm.

## 17. Những sai lầm thường gặp

- Dùng required anti-affinity cho mọi replica nhưng không có đủ node.
- Dùng zone anti-affinity cứng trong khi mục tiêu chỉ là phân bố cân bằng.
- Dùng ScheduleAnyway rồi kỳ vọng phân bố luôn đồng đều.
- Đặt maxSkew quá thấp mà không có capacity dự phòng.
- Chọn minDomains lớn hơn số domain có thể cấp phát trong tình huống lỗi.
- Selector không khớp label của pod template nên scheduler đếm sai nhóm pod.
- Node thiếu topology label hoặc label không nhất quán.
- Node affinity loại bỏ toàn bộ node ở một zone.
- Bỏ qua taint/toleration và volume topology.
- Dùng affinity để thay thế network policy hoặc ranh giới bảo mật.
- Không tính đến maxSurge khi rolling update với anti-affinity cứng.
- Cho rằng autoscaler luôn có thể tạo thêm node ở mọi zone.
- Không quan sát event và chỉ nhìn CPU/RAM khi pod Pending.

## 18. Checklist trước khi đưa placement policy vào production

**Topology**

- [ ] Node có label zone/hostname cần thiết và nhất quán.
- [ ] Xác định rõ failure domain cần phân tán.
- [ ] Có đủ node eligible ở các domain.
- [ ] Đã tính trường hợp một node hoặc một zone mất.

**Affinity**

- [ ] Node affinity chọn đúng node pool và kiến trúc.
- [ ] Pod affinity có selector và namespace scope chính xác.
- [ ] Pod anti-affinity required chỉ dùng khi thực sự cần.
- [ ] Preferred weight phản ánh đúng mức ưu tiên.
- [ ] Label bảo mật không thể bị workload không tin cậy tự ý sửa.

**Topology spread**

- [ ] maxSkew phù hợp với số replica và số domain.
- [ ] topologyKey tồn tại trên node eligible.
- [ ] labelSelector chọn đúng workload.
- [ ] DoNotSchedule hoặc ScheduleAnyway được chọn có chủ đích.
- [ ] minDomains phù hợp với chiến lược khi mất zone.
- [ ] Trường tùy chọn được hỗ trợ bởi phiên bản cluster.

**Vận hành**

- [ ] Đã kiểm tra Pending event và scheduler behavior.
- [ ] Rolling update/HPA có đủ capacity.
- [ ] PVC/PV topology tương thích.
- [ ] Autoscaler và quota hỗ trợ node pool cần thiết.
- [ ] PDB, readiness và disruption plan được cấu hình riêng.
- [ ] Có dashboard theo dõi pod distribution theo zone/hostname.

## 19. Nguyên tắc vận hành

1. **Dùng node affinity để chọn phần cứng và node pool:** phân biệt điều kiện bắt buộc với ưu tiên.
2. **Dùng pod affinity để co-location có mục tiêu:** chỉ khi gần nhau đem lại lợi ích rõ ràng.
3. **Dùng pod anti-affinity để tách workload:** required khi không đồng vị trí là yêu cầu cứng; preferred khi cần linh hoạt.
4. **Dùng topology spread để cân bằng replica:** chọn zone hoặc hostname làm topology key.
5. **Hiểu maxSkew và minDomains:** chúng tác động trực tiếp đến khả năng schedule khi thiếu domain.
6. **Đảm bảo label chính xác:** selector và topology labels quyết định scheduler đếm và chọn domain nào.
7. **Tính capacity trước khi đặt hard constraint:** số node/domain phải đủ cho replica và rollout.
8. **Phối hợp với autoscaling và storage:** scheduler không thể vượt quota, tạo zone hoặc di chuyển volume ngoài khả năng nền tảng.
9. **Quan sát Pending event và phân bố thực tế:** CPU còn trống không đồng nghĩa node đủ điều kiện.
10. **Kiểm thử failure scenario:** xác minh workload vẫn phục vụ khi node hoặc zone mất.

Affinity, anti-affinity và topology spread là các công cụ điều khiển placement ở những cấp độ khác nhau. Node affinity chọn loại node, pod affinity/anti-affinity thể hiện quan hệ giữa workload, còn topology spread kiểm soát độ cân bằng giữa các miền. Khi chọn đúng topology key, selector và mức ràng buộc, đồng thời tính đến capacity, storage, autoscaling và rollout, Kubernetes có thể phân bố pod phù hợp hơn với mục tiêu hiệu năng và khả năng chịu lỗi của ứng dụng.
