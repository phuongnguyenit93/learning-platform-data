# PodDisruptionBudget và chiến lược gián đoạn có kiểm soát

Một ứng dụng trên **Google Kubernetes Engine (GKE)** có ba Pod khỏe mạnh. Khi đội vận hành bảo trì node, nếu nhiều Pod bị di chuyển cùng lúc, người dùng có thể gặp lỗi dù Kubernetes sẽ tạo lại Pod. **PodDisruptionBudget (PDB)** giúp đặt giới hạn cho những lần *eviction tự nguyện*, nhờ đó công cụ bảo trì biết khi nào phải chờ để ứng dụng còn đủ Pod sẵn sàng.

Trong chương **GKE nâng cao và vận hành** của module **CLOUD_PROVIDERS_GCP**, bài học này tập trung vào cách sử dụng PDB đúng với **Deployment, StatefulSet, node drain và GKE node upgrades**, đồng thời kết hợp readiness, capacity, rollout và giám sát để giữ độ tin cậy. Bối cảnh kiến thức trải từ project/IAM, VPC và Compute Engine đến GKE, Cloud Run, dữ liệu và chi phí; PDB là một mảnh của thiết kế khả dụng chứ không phải giải pháp thay thế những lớp đó.

Sau bài học, bạn có thể:

1. Phân biệt **voluntary disruption**, **involuntary disruption**, Eviction API và hành vi xóa Pod trực tiếp.
2. Chọn `minAvailable` hoặc `maxUnavailable`, đọc `disruptionsAllowed` và tránh những cấu hình khiến drain bị kẹt.
3. Viết PDB tương ứng với số replica, khả năng quorum và mức phục vụ tối thiểu.
4. Lập kế hoạch bảo trì node trên GKE với surge/blue-green upgrades, đủ capacity, graceful shutdown và rollback.
5. Thử nghiệm an toàn trong namespace/node lab, chẩn đoán eviction bị từ chối và theo dõi SLO.

## 1. PDB bảo vệ điều gì?

PDB là tài nguyên Kubernetes thuộc API `policy/v1`. PDB chọn nhóm Pod theo **label selector**, sau đó khai báo số lượng hoặc tỷ lệ Pod cần còn khỏe sau một *eviction được kiểm soát*. PDB không tự tạo Pod, không tự cấp node, không quyết định nơi Pod được đặt và không ngăn mọi sự cố.

~~~mermaid
flowchart LR
    O["Bảo trì node / drain"] --> E["Kubernetes Eviction API"]
    E --> P{"PDB còn ngân sách<br/>gián đoạn?"}
    P -->|"Có"| DEL["Evict Pod, chờ shutdown<br/>theo grace period"]
    P -->|"Không"| WAIT["Từ chối tạm thời;<br/>điều tra hoặc thử lại"]
    DEL --> C["Controller tạo Pod thay thế<br/>trên node đủ điều kiện"]
    C --> R["Pod Ready, cập nhật ngân sách"]
~~~

### 1.1. Gián đoạn tự nguyện và không tự nguyện

| Tình huống | Loại | PDB có giới hạn trực tiếp không? |
| --- | --- | --- |
| `kubectl drain` thực hiện eviction để bảo trì node | Tự nguyện | **Có**, qua Eviction API, nếu Pod khớp PDB. |
| Công cụ nâng cấp node cố gắng drain bằng eviction | Tự nguyện ở bước đầu | **Có điều kiện**; GKE có giới hạn thời gian chờ. |
| Node hỏng phần cứng, zone mất điện | Không tự nguyện | **Không** ngăn được. |
| Container crash hoặc bị OOMKilled | Không tự nguyện | **Không** ngăn được. |
| `kubectl delete pod` trực tiếp | Xóa trực tiếp, không qua Eviction API | **Không** áp ngân sách PDB như một eviction. |
| Deployment rolling update thay Pod theo strategy | Thay đổi do controller rollout | **PDB không trực tiếp khống chế**; dùng `maxUnavailable`/`maxSurge` của Deployment. |
| Người quản trị ép xóa Pod/node | Có thể bỏ qua eviction bình thường | **Không bảo đảm** bảo vệ; rủi ro mất khả dụng. |

**Chốt ý:** PDB điều tiết *cách* gián đoạn diễn ra, không bảo đảm ứng dụng luôn đạt một số Pod khỏe. Lỗi node, thay đổi sai trong rollout, phụ thuộc database một zone hoặc thiếu capacity vẫn có thể làm dịch vụ ngừng hoạt động.

### 1.2. Vì sao cần Eviction API?

Khi một chương trình yêu cầu **evict** Pod, Kubernetes API server kiểm tra PDB trước khi cho phép. Có thể nhận:

- `200 OK`: eviction được cho phép, Pod bước vào quy trình termination.
- `429 Too Many Requests`: PDB chưa cho phép eviction hoặc API đang giới hạn tốc độ; thường cần đợi, tăng capacity hoặc xử lý Pod chưa Ready.
- `500 Internal Server Error`: có thể có cấu hình bất hợp lệ, ví dụ nhiều PDB cùng chọn một Pod.

`kubectl drain` mặc định dùng Eviction API khi được API server hỗ trợ. Không dùng các tùy chọn **bỏ qua eviction** như một cách làm cho drain “thành công”, trừ quy trình ngoại lệ đã đánh giá tác động.

## 2. Cấu hình và phép tính ngân sách gián đoạn

Trong một PDB, phải chọn **một** trong hai trường `minAvailable` và `maxUnavailable`:

- `minAvailable`: số/tỷ lệ Pod **cần còn Ready** sau eviction.
- `maxUnavailable`: số/tỷ lệ Pod **được phép không sẵn sàng** so với số replica mong muốn của controller.

Phần trăm luôn ghi dưới dạng chuỗi, ví dụ `"50%"`. Kubernetes **làm tròn lên** cho cả `minAvailable` và `maxUnavailable` dạng phần trăm; vì vậy phần trăm `maxUnavailable` có thể cho phép gián đoạn nhiều hơn tỷ lệ trực giác với replica nhỏ.

### 2.1. Các ví dụ tính nhanh

| Desired replicas | PDB | Số Pod khỏe tối thiểu để còn đáp ứng ngân sách | `disruptionsAllowed` khi tất cả Ready |
| ---: | --- | ---: | ---: |
| 3 | `minAvailable: 2` | 2 | 1 |
| 3 | `maxUnavailable: 1` | 2 | 1 |
| 5 | `minAvailable: 4` | 4 | 1 |
| 5 | `maxUnavailable: "40%"` | 3 (ceil(40% × 5) = 2 không sẵn sàng) | 2 |
| 7 | `minAvailable: "50%"` | 4 (ceil(3,5)) | 3 |
| 7 | `maxUnavailable: "30%"` | 4 (ceil(2,1) = 3 không sẵn sàng) | 3 |
| 1 | `maxUnavailable: "30%"` | 0 | 1 — **có thể mất 100% dịch vụ** |
| 1 | `minAvailable: 1` | 1 | 0 — **drain có thể bị chặn** |

Các số ở cột cuối giả định đủ replica đã **Ready**, không có eviction đang xử lý và selector khớp đúng workload do controller quản lý. Trong thực tế, ngân sách thay đổi theo Pod khỏe, replica mong muốn và những eviction đang được xử lý.

Ví dụ với ba Pod có PDB `minAvailable: 2`: khi cả ba Ready, có thể evict một Pod. Trong lúc chỉ còn hai Pod khỏe, lần eviction tiếp theo phải chờ cho tới khi Pod thay thế Ready, hoặc số replica khỏe được tăng bằng cách khác.

### 2.2. Manifest cho một Deployment ba replica

~~~yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: orders-api-pdb
  namespace: orders
spec:
  minAvailable: 2
  selector:
    matchLabels:
      app: orders-api
~~~

Một lựa chọn tương đương **khi Deployment có ba replica** là:

~~~yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: orders-api-pdb
  namespace: orders
spec:
  maxUnavailable: 1
  selector:
    matchLabels:
      app: orders-api
~~~

**Không tạo cả hai PDB cùng chọn một nhóm Pod.** Hai manifest ở trên là hai **phương án thay thế**, không phải hai lớp bảo vệ cộng dồn. `maxUnavailable` hữu ích khi số replica biến động theo HPA, nhưng được dùng với Pod do controller có `scale` quản lý; kiểm tra selector và loại controller trước khi chọn.

### 2.3. Đọc PDB status

~~~bash
kubectl get pdb -n orders
kubectl describe pdb orders-api-pdb -n orders
kubectl get pdb orders-api-pdb -n orders -o yaml
~~~

| Trường `status` | Ý nghĩa |
| --- | --- |
| `currentHealthy` | Số Pod được PDB đánh giá là khỏe (**Ready**). |
| `desiredHealthy` | Số Pod khỏe tối thiểu theo budget. |
| `expectedPods` | Số Pod/replica kỳ vọng theo controller. |
| `disruptionsAllowed` | Số eviction mới đang được phép ở thời điểm quan sát. |
| `disruptedPods` | Theo dõi Pod đã chấp nhận eviction nhưng chưa hoàn thành trong cửa sổ liên quan. |
| `observedGeneration` | Thế hệ cấu hình đã được controller PDB quan sát. |

Khi `disruptionsAllowed: 0`, **đừng vội tăng ngân sách**. Hãy kiểm tra số Pod `Ready`, replica mong muốn, tiến độ startup và liệu có một eviction khác đang diễn ra. PDB không tăng capacity cho ứng dụng; nó chỉ dựa trên trạng thái hiện hữu để quyết định có cho phép gián đoạn tiếp hay không.

**Lưu ý selector:** selector `{}` trong `policy/v1` có thể chọn **mọi Pod trong namespace**; thiếu cẩn trọng có thể làm drain nhiều workload bị chặn. Nên dùng nhãn rõ và kiểm tra Pod thực sự khớp trước khi áp dụng.

## 3. Khi nào PDB khiến bảo trì bị kẹt?

### 3.1. Pod không Ready và `unhealthyPodEvictionPolicy`

Kubernetes coi Pod **Ready** là khỏe khi tính `currentHealthy`. Nếu Pod bị `CrashLoopBackOff` hoặc chạy nhưng không Ready, ngân sách có thể về 0 ngay cả trước khi bảo trì bắt đầu.

`spec.unhealthyPodEvictionPolicy` quy định cách eviction xử lý **Pod đang Running nhưng không khỏe**:

| Policy | Hành vi | Đánh đổi |
| --- | --- | --- |
| `IfHealthyBudget` (mặc định) | Có thể evict Pod Running/NotReady khi ứng dụng vẫn đáp ứng số Pod khỏe tối thiểu. | Nếu ứng dụng đã thiếu Pod khỏe, một Pod hỏng có thể giữ drain chờ. |
| `AlwaysAllow` | Cho phép evict Pod Running/NotReady ngay cả khi ngân sách khỏe chưa đủ. | Giúp dọn node có Pod lỗi, nhưng có thể loại Pod vẫn còn cơ hội phục hồi. |

Tùy chọn này đã **stable từ Kubernetes 1.31**; xác nhận cluster version trước khi áp dụng cho môi trường cũ. Nó **không cho phép vượt ngân sách đối với Pod Ready**.

Ví dụ:

~~~yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: orders-api-pdb
spec:
  maxUnavailable: 1
  unhealthyPodEvictionPolicy: AlwaysAllow
  selector:
    matchLabels:
      app: orders-api
~~~

Trong production, chỉ chọn `AlwaysAllow` khi đã xác minh cơ chế phục hồi Pod, probes, khả năng tạo replica thay thế và ảnh hưởng dữ liệu. Nó không sửa được lỗi image, registry hoặc dependency khiến mọi Pod đều NotReady.

### 3.2. Replica duy nhất và cluster upgrade

Với **một Pod Ready**, PDB `minAvailable: 1` cho phép **0 eviction tự nguyện**. Một node chứa Pod đó có thể không được drain hoàn tất. Đây là kết quả đúng theo PDB, không phải Kubernetes tự nhiên hỏng.

Phương án nên xem xét theo thứ tự:

1. Nếu ứng dụng **stateless và chạy song song được**, tăng replica lên ít nhất hai, tốt hơn là trải qua nhiều node/zone; chờ replica mới Ready.
2. Đảm bảo **capacity** cho Pod thay thế và startup/readiness hoạt động.
3. Khi không thể chạy song song (ví dụ một writer không có leader election), lên **maintenance window có downtime được chấp nhận**, backup và kế hoạch phục hồi.
4. Nếu cần nới PDB, thực hiện thay đổi tối thiểu và có phê duyệt; ghi lại trạng thái trước/sau.

**Không** đặt `maxUnavailable: "30%"` cho một replica rồi coi là có giới hạn downtime 30%: Kubernetes làm tròn lên thành **một eviction**, tức có thể mất toàn bộ instance.

### 3.3. Trường hợp database dùng quorum

Một cụm có năm thành viên và cần ít nhất **ba thành viên sẵn sàng** để duy trì quorum. Về phép tính, `minAvailable: 3` cho phép tối đa hai eviction khi cả năm Ready. Nhưng nếu thêm một lỗi node không tự nguyện, quorum có thể mất.

Vì thế, với hệ thống consensus, lựa chọn thận trọng hơn có thể là **`maxUnavailable: 1`**, cộng với anti-affinity/topology spread, health checks và orchestration hiểu trạng thái leader/follower. PDB đếm Pod Ready; nó **không tự chứng minh Pod đó đã đồng bộ dữ liệu, có quyền biểu quyết hoặc đáp ứng quorum nghiệp vụ**.

### 3.4. Các nguồn gây bế tắc khác

| Triệu chứng | Kiểm tra trước khi nới PDB |
| --- | --- |
| `disruptionsAllowed=0` dù số replica có vẻ đủ | Có Pod NotReady, terminating, rollout chưa xong hoặc status chưa cập nhật? |
| Eviction bị `429` liên tục | Desired vs current healthy, PDB, readiness và API throttling. |
| Pod mới `Pending` | Thiếu CPU/RAM/IP, quota, node affinity, topology spread, taints hoặc PVC topology. |
| Một Pod khớp nhiều PDB | Sửa selector chồng lấn; Eviction API có thể trả lỗi. |
| Drain chờ rất lâu | Container `preStop`/`terminationGracePeriodSeconds`, Pod chưa khỏe hoặc storage detach chậm. |
| DaemonSet/Pod không do controller quản lý | Kiểm tra hành vi của `kubectl drain` và GKE node upgrade; PDB không thay thế workload controller. |

Nguyên tắc xử lý là **tìm cách tăng số Pod khỏe và capacity trước**, không lấy việc xóa PDB làm phản xạ đầu tiên.

## 4. PDB trong chiến lược nâng cấp node GKE

### 4.1. Surge và blue-green upgrades

Ở GKE Standard node pools, chiến lược nâng cấp ảnh hưởng đáng kể đến cơ hội tôn trọng PDB:

| Chiến lược | Cách làm chính | Vai trò của PDB |
| --- | --- | --- |
| **Surge upgrade** | Cấp thêm node mới trong giới hạn `maxSurge`, rồi cordon/drain node cũ. | Có chỗ cho Pod mới Ready trước khi tiếp tục eviction. |
| **Upgrade với `maxUnavailable` của node pool** | Cho phép một số node không sẵn sàng trong khi nâng cấp. | Cần dự phòng workload đủ lớn để không vi phạm PDB/SLO. |
| **Blue-green upgrade** | Tạo nhóm node mới, chuyển workload và giữ nhóm cũ trong thời gian soak được cấu hình. | Có thêm không gian kiểm tra và khả năng quay lại theo giới hạn sản phẩm. |

`maxUnavailable` của **node pool upgrade** là số **node**, trong khi `maxUnavailable` của **PDB** là số **Pod**. Hai trường cùng tên nhưng không thể thay thế nhau.

### 4.2. Giới hạn chờ PDB khi GKE nâng cấp

Theo tài liệu GKE hiện hành, trong nâng cấp node, GKE tôn trọng **PDB và thời gian kết thúc Pod** tối đa khoảng **một giờ trên mỗi node** đối với quy trình nâng cấp thông thường. Nếu không thể drain, GKE có thể **buộc tiến trình nâng cấp tiếp tục** sau giới hạn này. Với blue-green, thời gian soak có thể cho phép giai đoạn chờ dài hơn theo cấu hình.

**Hệ quả:** PDB **không phải khóa bất biến** để giữ node khỏi mọi lần nâng cấp. PDB quá chặt có thể làm upgrade kéo dài, sau đó workload vẫn bị gián đoạn khi GKE tiến hành bước bắt buộc. Để tránh:

- Bảo đảm số replica và node capacity trước maintenance.
- Đảm bảo Pod thay thế có thể schedule và Ready tại zone khác khi phù hợp.
- Rà soát `PDB disruptionsAllowed=0`, các Pod NotReady và storage affinity.
- Dùng maintenance window/exclusions trong phạm vi GKE hỗ trợ, và lên lịch cho các thành phần stateful nhạy cảm.
- Chọn node upgrade strategy theo nhu cầu RTO, quota surge và khả năng kiểm thử rollback.

Điều kiện trên liên quan hành vi **GKE-managed node upgrade**; không tự suy rằng mọi thao tác `kubectl drain` thủ công cũng tự bỏ qua PDB sau một giờ.

### 4.3. PDB không điều khiển trực tiếp Deployment rollout

Khi chạy `kubectl rollout restart deployment/orders-api`, Deployment controller thay Pod theo `spec.strategy.rollingUpdate.maxUnavailable` và `maxSurge`. PDB không làm lớp admission cho mọi lần xóa Pod của Deployment rollout.

Vì vậy cần đồng bộ **ba thiết lập độc lập**:

| Thiết lập | Bảo vệ phần nào? |
| --- | --- |
| **Deployment `maxUnavailable/maxSurge`** | Giới hạn thay thế Pod trong rolling update của ứng dụng. |
| **PDB `minAvailable/maxUnavailable`** | Giới hạn những voluntary evictions qua Eviction API. |
| **GKE node pool upgrade `maxSurge/maxUnavailable`** | Quy định tốc độ và capacity trong việc tạo/xóa node. |

Ngoài ra, **Pod readiness, graceful termination, topology spread và autoscaling** quyết định liệu các giới hạn trên có thực thi trơn tru hay dẫn tới Pod Pending/503.

### 4.4. Thiết kế drain với graceful shutdown

Một API HTTP cần phối hợp:

1. Đặt `readinessProbe` đúng để Pod chưa sẵn sàng không nhận yêu cầu.
2. Khi nhận `SIGTERM`, dừng nhận request mới, hoàn tất request đang xử lý và đóng kết nối có kiểm soát.
3. Dùng `terminationGracePeriodSeconds` đủ cho yêu cầu đang xử lý nhưng không quá dài đến mức làm bảo trì kẹt.
4. Nếu dùng `preStop`, xử lý đúng timing; thời gian hook nằm trong ngân sách termination grace.
5. Đảm bảo load balancer/EndpointSlice loại backend không còn Ready theo cơ chế hỗ trợ; quan sát thực tế độ trễ hội tụ.

PDB chỉ kiểm soát **trước khi cho phép eviction**; nó không sửa lỗi ứng dụng tắt ngay lập tức, bỏ qua SIGTERM hoặc không hỗ trợ nhiều replica.

## 5. Runbook bảo trì node có kiểm soát

Runbook sau áp dụng cho **GKE Standard** với node pool do đội vận hành quản lý. Với Autopilot, GKE quản lý node; không tự áp dụng một thao tác drain thủ công không được sản phẩm/chính sách cho phép. Mọi thao tác phải sử dụng **đúng project, cluster, context và namespace**, không dựa vào giá trị hiện tại của terminal mà chưa xác nhận.

### 5.1. Trước bảo trì

1. **Xác định phạm vi:** tên node, zone, node pool, chủ ứng dụng và thời điểm bảo trì được duyệt.
2. **Kiểm tra SLO:** tỷ lệ lỗi, latency, số endpoint Ready, sức khỏe database và capacity còn trống.
3. **Kiểm tra tất cả Pod trên node**, gồm các namespace khác, DaemonSet, Pod đơn lẻ, workload dùng local storage hoặc PVC.
4. **Đọc PDB:** `currentHealthy`, `desiredHealthy`, `disruptionsAllowed`, tình trạng Pod NotReady và selector.
5. **Xác nhận nơi chuyển Pod:** CPU, memory, Pod IP, topology, quota, taint/affinity, volume attach và quyền kéo image.
6. **Chuẩn bị rollback:** người chịu trách nhiệm, điểm dừng, quan sát trong khi drain, cách uncordon và kế hoạch khôi phục ứng dụng.

Lệnh **chỉ đọc** trong context đã xác minh:

~~~bash
kubectl config current-context
kubectl get nodes -L topology.kubernetes.io/zone
kubectl get pdb -A
kubectl get pods -A -o wide

# Chọn một node SAU khi đã xác minh quyền sở hữu
NODE="TEN_NODE_DUOC_PHE_DUYET"
kubectl get pods -A --field-selector "spec.nodeName=$NODE" -o wide
kubectl describe node "$NODE"
~~~

Nếu Pod của ứng dụng khác còn nằm trên node, **dừng và phối hợp với owner**. Không thêm `--force`, `--disable-eviction` hoặc `--delete-emptydir-data` chỉ để bỏ qua lỗi: các tùy chọn này có thể gây mất gián đoạn dữ liệu hoặc vượt cơ chế bảo vệ.

### 5.2. Trong bảo trì

Nếu node dành riêng cho lab hoặc thao tác đã được phê duyệt trong runbook production:

~~~bash
# Thao tác ghi: ngăn đặt Pod mới lên node
kubectl cordon "$NODE"

# Chỉ chạy khi đã kiểm tra tất cả Pod và đủ capacity bên ngoài node
# Không dùng --disable-eviction để bỏ qua PDB
kubectl drain "$NODE" --ignore-daemonsets --timeout=2m
~~~

`kubectl drain` có thể dừng do PDB, Pod không được controller quản lý hoặc Pod sử dụng `emptyDir`; đây là thông tin cần điều tra, **không phải yêu cầu xóa cưỡng bức**. Thời hạn `2m` chỉ để bài lab không treo quá lâu, không phải cấu hình RTO khuyến nghị của production.

Trong cửa sổ bảo trì, quan sát:

~~~bash
kubectl get pdb -A
kubectl get pods -A -o wide
kubectl get nodes
~~~

Với một cluster thử nghiệm có PDB `minAvailable: 2` và ba Pod Ready, eviction đầu tiên có thể được phép. Eviction tiếp theo phải chờ cho đến khi đủ Pod khỏe theo budget; nếu không có node nhận Pod mới, drain có thể tiếp tục bị chặn.

### 5.3. Sau bảo trì hoặc khi phải hủy

Nếu **node còn hoạt động** và mục tiêu là đưa nó trở lại nhận workload:

~~~bash
# Thao tác ghi: bỏ đánh dấu unschedulable
kubectl uncordon "$NODE"

kubectl get nodes
kubectl get pods -A -o wide
kubectl get pdb -A
~~~

Không `uncordon` một node đang lỗi hoặc chưa đạt chuẩn bảo mật chỉ để cho Pod trở lại. Nếu node đã bị GKE thay thế/xóa trong quá trình nâng cấp, tên node cũ có thể không còn; xác minh node pool và node mới thay vì cố khôi phục một đối tượng không tồn tại.

Đóng thay đổi khi đã kiểm tra **ứng dụng phục vụ lại đúng SLO**, không còn Pod Pending ngoài dự kiến, PVC/leader đã phục hồi nếu có và có bằng chứng lỗi/latency trước–sau.

## 6. Bài thực hành trên cluster thử nghiệm

**Mục tiêu:** xem PDB thay đổi theo số Pod Ready và thử một rollout không gây lỗi có chủ đích. Phần đầu chỉ tạo **Deployment, PDB và namespace** trong **cluster lab đã có sẵn**; không tạo GKE cluster hay node pool mới. Phần drain node là **tùy chọn nâng cao** và chỉ thực hiện với node riêng được phép.

### 6.1. Kiểm tra context rồi triển khai ba replica

Trên máy đã cài `kubectl` và có quyền trong cluster lab:

~~~bash
kubectl config current-context
kubectl get nodes -o wide

# Chỉ tạo trong cluster thử nghiệm đã xác minh
kubectl create namespace pdb-lab

kubectl apply -n pdb-lab -f - <<'YAML'
apiVersion: apps/v1
kind: Deployment
metadata:
  name: web-lab
spec:
  replicas: 3
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxUnavailable: 0
      maxSurge: 1
  selector:
    matchLabels:
      app: web-lab
  template:
    metadata:
      labels:
        app: web-lab
    spec:
      terminationGracePeriodSeconds: 30
      containers:
        - name: nginx
          image: nginx:stable-alpine
          ports:
            - containerPort: 80
          resources:
            requests:
              cpu: 100m
              memory: 64Mi
            limits:
              memory: 128Mi
          readinessProbe:
            httpGet:
              path: /
              port: 80
            periodSeconds: 5
---
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: web-lab-pdb
spec:
  minAvailable: 2
  selector:
    matchLabels:
      app: web-lab
YAML

kubectl rollout status deployment/web-lab -n pdb-lab
kubectl get pods -n pdb-lab -o wide
kubectl get pdb web-lab-pdb -n pdb-lab -o yaml
~~~

Trong điều kiện tất cả ba Pod Ready, bạn kỳ vọng `currentHealthy: 3`, `desiredHealthy: 2` và `disruptionsAllowed: 1`. Nếu một Pod chưa Ready, kiểm tra sự kiện/khả năng kéo image rồi chỉ đánh giá khi trạng thái ổn định.

### 6.2. Quan sát rollout và phân biệt với eviction

Ở một terminal, theo dõi:

~~~bash
kubectl get pods -n pdb-lab -w
~~~

Ở terminal khác:

~~~bash
# Thay Pod bằng rolling update: đây KHÔNG phải test Eviction API/PDB
kubectl rollout restart deployment/web-lab -n pdb-lab
kubectl rollout status deployment/web-lab -n pdb-lab
kubectl get pdb web-lab-pdb -n pdb-lab
~~~

Việc rollout hoàn thành phản ánh **Deployment strategy và Pod readiness**, không chứng minh rằng PDB đã cho phép/từ chối eviction. Trong production, image version nên được ghim và rollout có giám sát, không dựa vào tag thay đổi theo thời gian như `stable-alpine` của demo.

### 6.3. Tùy chọn: thử drain trên node dành riêng cho lab

Chỉ thực hiện nếu **cluster có ít nhất hai node**, node được chọn **chỉ chạy workload lab và các system DaemonSet phù hợp**, không dùng chung với đội khác, và đủ capacity để tạo Pod thay thế.

~~~bash
# Thay bằng node LAB đã được người quản trị phê duyệt
NODE="TEN_NODE_LAB"

# BẮT BUỘC đọc kỹ danh sách trước khi drain
kubectl get pods -A --field-selector "spec.nodeName=$NODE" -o wide
kubectl get pdb -n pdb-lab

# Sau khi xác minh node đủ an toàn để rút khỏi cluster
kubectl cordon "$NODE"
kubectl drain "$NODE" --ignore-daemonsets --timeout=2m

# Nếu drain bị chặn/hết giờ: DỪNG, xem Pod/PDB/events
# Sau khi hoàn tất bài thử và node còn khỏe:
kubectl uncordon "$NODE"
~~~

Nếu Pod còn nằm ở trạng thái không thể evict, xem `kubectl describe pdb web-lab-pdb -n pdb-lab` và `kubectl describe pod`. **Không chạy lại drain với `--disable-eviction` hoặc `--force` để làm biến mất lỗi**. Không thực hiện thử này trong một cluster chia sẻ hoặc một-node cluster.

### 6.4. Dọn sạch tài nguyên

~~~bash
# Kiểm tra đúng context và namespace thử nghiệm
kubectl config current-context
kubectl get all,pdb -n pdb-lab

# Chỉ xóa namespace đã tạo trong bài lab
kubectl delete namespace pdb-lab
~~~

Nếu đã cordon node lab mà chưa uncordon, xử lý nó theo **trạng thái node thực tế** và quyền được giao; xóa namespace không tự mở lại một node bị cordon. Lab không xóa hoặc thay đổi node pool, cluster, VPC hay tài nguyên Google Cloud ngoài phạm vi bài tập.

## 7. Giám sát và xử lý sự cố

### 7.1. Tín hiệu trước, trong và sau gián đoạn

| Tín hiệu | Ý nghĩa thực tế |
| --- | --- |
| `PDB disruptionsAllowed` và `currentHealthy` | Còn cơ hội eviction an toàn hay không; có Pod chưa Ready không. |
| Deployment/StatefulSet desired, ready, available replicas | Controller có đáp ứng số Pod cần phục vụ không. |
| Pod `Pending`, `Terminating` và events | Thiếu node, scheduling, PVC, image pull hoặc graceful shutdown chậm. |
| Node Ready/cordoned; autoscaler events | Có đủ capacity thay thế, có node bị rút khỏi scheduling không. |
| HTTP 5xx, latency p95/p99, request success rate | Ứng dụng có đạt SLO thật, không chỉ số lượng Pod. |
| Database quorum/replication lag, PVC attach | Stateful service có đủ dữ liệu/leader để phục vụ không. |
| Thời gian upgrade, số node cần bảo trì và thời gian đợi drain | Bảo trì có kẹt trước giới hạn chờ GKE không. |

Nên cảnh báo khi **`disruptionsAllowed=0` kéo dài** trên workload cần bảo trì thường xuyên, kết hợp Pod Ready và sự kiện nâng cấp. Không cảnh báo chỉ vì ngân sách bằng 0 ngay lúc một eviction hợp lệ đang chạy; cần có ngưỡng thời gian và bối cảnh.

### 7.2. Khi drain bị từ chối, làm theo thứ tự

1. **Dừng thao tác tiếp theo** và đọc `kubectl get pdb -A`, `kubectl get pods -A -o wide`, `kubectl describe pdb`.
2. Xác định Pod nằm trên node và PDB nào chọn nó; tránh hai PDB chồng selector.
3. Đối chiếu desired/current/Ready replicas, readiness probe, HPA và rollout đang chạy.
4. Kiểm tra node còn sống có capacity: CPU, RAM, Pod IP, quota, affinity/taints, topology spread và volume.
5. Nếu Pod **Running/NotReady** giữ drain, đánh giá `unhealthyPodEvictionPolicy`; không bật `AlwaysAllow` nếu Pod vẫn cần bảo vệ trạng thái nghiệp vụ.
6. Nếu chỉ có một replica, quyết định **scale-out** hay nhận downtime bảo trì theo yêu cầu ứng dụng.
7. Thực hiện thay đổi được phê duyệt, thử một node, quan sát endpoint/SLO rồi mới tiếp tục các node khác.

Trong GKE, theo dõi **thời gian đợi drain** vì nâng cấp quản lý có thể tiếp tục cưỡng bức sau giới hạn chờ nêu ở mục 4.2. Tránh để một PDB vô tình làm cả node pool upgrade kéo dài mà không có người nhận cảnh báo.

### 7.3. Chi phí của chiến lược gián đoạn thấp

PDB là cấu hình Kubernetes, không cần mua một dịch vụ riêng. **Chi phí gián tiếp** đến từ các replica/node dự phòng, surge nodes trong nâng cấp, tài nguyên theo zone, lưu lượng liên zone, disk/backup và giám sát. Quyết định đúng cần cân nhắc:

\[
\text{Khả năng phục vụ sau gián đoạn}
=\text{Replica khỏe còn lại}
\times\text{năng lực thực tế của mỗi replica}
\]

Đây chỉ là mô hình ước lượng tải đơn giản, không thay thế phép đo; khi database quá tải hoặc traffic không phân bố đều, năng lực thật thấp hơn. Để đạt SLO, cần đo **tải peak**, **error budget**, giới hạn node/quota và thời gian Pod mới Ready trước khi chọn `minAvailable`.

## 8. Bài tập tình huống

### Tình huống A — API có 5 replica

Deployment `payments-api` có năm Pod Ready, phân tán trên ba zone. SLO yêu cầu còn ít nhất bốn Pod phục vụ trong bảo trì thường lệ.

**Yêu cầu:** viết PDB, tính eviction được phép ban đầu, rồi tính lại khi một Pod đã NotReady.

**Gợi ý:** `minAvailable: 4` hoặc `maxUnavailable: 1` là lựa chọn phù hợp khi desired replicas bằng năm. Ban đầu `disruptionsAllowed=1`; khi chỉ còn bốn Pod khỏe, ngân sách eviction mới bằng **0**. Nếu yêu cầu thực tế là năng lực xử lý chứ không chỉ số Pod, kiểm tra mức tải bốn Pod có đáp ứng SLO không.

### Tình huống B — Một StatefulSet có 3 replica

Một cụm database cần **quorum hai thành viên** để nhận ghi. Khi bảo trì, một thành viên đang mất kết nối với leader và báo `NotReady`.

**Yêu cầu:** có thể tiếp tục evict một thành viên Ready khác không? `AlwaysAllow` giải quyết vấn đề nào, không giải quyết vấn đề nào?

**Gợi ý:** với `minAvailable: 2`, hai Pod Ready nghĩa là ngân sách eviction tiếp theo **0**. `AlwaysAllow` có thể giúp evict thành viên **không khỏe**, nhưng không được dùng để bỏ qua quorum hoặc xóa một thành viên Ready. Kiểm tra đồng bộ dữ liệu, cơ chế bầu leader và quy trình operator/database trước khi di chuyển.

### Tình huống C — Node upgrade kéo dài

GKE Standard đang surge-upgrade node pool. Một số Pod `Pending` do PV gắn ở zone khác; PDB liên quan báo `disruptionsAllowed=0`. Thời gian upgrade tăng liên tục.

**Yêu cầu:** xếp thứ tự điều tra và đề xuất hành động ít rủi ro nhất.

**Gợi ý:** kiểm tra PVC topology, node locations, capacity và Pod events trước; nếu không có node có thể gắn volume thì tăng `maxUnavailable` của PDB không làm Pod mới chạy được. Cần phương án storage/failover phù hợp, đánh giá giới hạn thời gian chờ GKE, bảo vệ dữ liệu và lên lịch thay đổi sau khi sửa nguyên nhân.

### Tự kiểm tra

1. **PDB có bảo vệ khỏi mất zone không?** Không; cần replica ở những zone sống sót và dữ liệu phù hợp.
2. **`kubectl delete pod` có luôn tôn trọng PDB không?** Không; xóa trực tiếp không phải eviction được admission qua PDB.
3. **Vì sao `maxUnavailable: "30%"` với một replica nguy hiểm?** Phần trăm được làm tròn lên, có thể cho phép evict Pod duy nhất.
4. **`disruptionsAllowed=0` có luôn là lỗi cấu hình?** Không; có thể ngân sách đang được dùng đúng hoặc Pod chưa Ready.
5. **Rollout Deployment có bị PDB trực tiếp khống chế không?** Không; cần xem rolling update strategy.
6. **Có thể trông chờ GKE đợi PDB vô hạn khi node upgrade?** Không; GKE có giới hạn chờ và có thể tiếp tục cưỡng bức.
7. **Làm sao giảm gián đoạn thực tế?** Phối hợp PDB, đủ replica/node, readiness, graceful shutdown, topology và chiến lược upgrade, sau đó xác minh SLO.

## 9. Tài liệu chính thức

- [Kubernetes — Configure a PodDisruptionBudget](https://kubernetes.io/docs/tasks/run-application/configure-pdb/): selector, `minAvailable`/`maxUnavailable`, làm tròn, unhealthy eviction.
- [Kubernetes — API-initiated Eviction](https://kubernetes.io/docs/concepts/scheduling-eviction/api-eviction/): Eviction API, mã phản hồi và khác biệt với direct deletion.
- [Kubernetes — Safely Drain a Node](https://kubernetes.io/docs/tasks/administer-cluster/safely-drain-node/): cách dùng drain/cordon và giới hạn thao tác.
- [GKE — Node pool upgrade strategies](https://cloud.google.com/kubernetes-engine/docs/concepts/node-pool-upgrade-strategies): surge, blue-green, giới hạn chờ PDB.
- [GKE — Manually upgrade a cluster](https://cloud.google.com/kubernetes-engine/docs/how-to/upgrading-a-cluster): trình tự upgrade và ảnh hưởng tới Pod.
- [GKE — Troubleshoot cluster upgrades](https://cloud.google.com/kubernetes-engine/docs/troubleshooting/upgrades): PDB kẹt, termination grace, PVC và capacity.
- [Kubernetes — Deployment](https://kubernetes.io/docs/concepts/workloads/controllers/deployment/): `maxSurge`, `maxUnavailable` và rolling updates.
- [Kubernetes — Pod lifecycle](https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/): readiness, termination và Pod conditions.

**Kết luận:** một PDB tốt phải cho phép **đủ bảo trì** để hệ thống luôn có thể được cập nhật, nhưng không evict quá nhiều Pod khỏe cùng lúc. Giá trị của PDB chỉ được kiểm chứng khi nó đi cùng capacity dự phòng, luồng dữ liệu an toàn, đo lường SLO và runbook rõ ràng — không phải khi mọi lệnh drain đều bị chặn.
