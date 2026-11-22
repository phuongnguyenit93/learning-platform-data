# Thử nghiệm lỗi và kiểm chứng khả năng phục hồi trên GCP

Một dịch vụ được xem là đáng tin cậy khi vẫn đáp ứng mục tiêu nghiệp vụ trong điều kiện có lỗi, hoặc có thể khôi phục trong giới hạn thời gian và mất dữ liệu đã chấp nhận. Kiểm tra thành công lúc hệ thống hoạt động bình thường chưa đủ để chứng minh điều đó. Nhóm SRE cần chủ động tạo ra những tình huống lỗi có kiểm soát, quan sát phản ứng của hệ thống và xác minh rằng cơ chế dự phòng, tự phục hồi và quy trình vận hành thực sự hoạt động.

Trên Google Cloud, các thành phần như Google Kubernetes Engine (GKE), Compute Engine, Cloud Run, Cloud SQL, Pub/Sub, Cloud Storage và Cloud Monitoring cung cấp nhiều cách xây dựng khả năng phục hồi. **Chaos engineering** là phương pháp kiểm chứng các giả thuyết về độ tin cậy bằng những thử nghiệm có phạm vi, điều kiện dừng và bằng chứng rõ ràng.

Bài học này hướng dẫn thiết kế thử nghiệm lỗi trên GCP, từ việc xác định SLO và blast radius đến mô phỏng Pod hoặc node gặp sự cố, kiểm tra phụ thuộc mạng, failover cơ sở dữ liệu, backlog message và xác minh phục hồi.

## 1. Khả năng phục hồi và chaos engineering

Khả năng phục hồi (resilience) là năng lực duy trì hoặc nhanh chóng khôi phục chức năng quan trọng khi một thành phần gặp lỗi. Một hệ thống có khả năng phục hồi cần xử lý được cả lỗi đơn lẻ, lỗi phụ thuộc và lỗi vận hành.

Các dạng lỗi thường gặp:

- **Lỗi tiến trình:** container crash, ứng dụng deadlock, memory leak hoặc hết tài nguyên.
- **Lỗi hạ tầng:** VM mất khả năng phục vụ, node GKE ngừng hoạt động, zone gặp sự cố.
- **Lỗi mạng:** latency tăng, packet loss, DNS lỗi, kết nối bị ngắt hoặc firewall chặn nhầm.
- **Lỗi phụ thuộc:** Cloud SQL không truy cập được, API bên ngoài timeout, Pub/Sub subscriber ngừng xử lý.
- **Lỗi dữ liệu:** dữ liệu sai, object bị ghi đè, replication lag hoặc backup không thể khôi phục.
- **Lỗi cấu hình và danh tính:** IAM bị thay đổi, credential hết hạn, quyền truy cập bị thu hồi.
- **Lỗi quy trình:** rollout không thành công, autoscaling không theo kịp tải hoặc runbook không phản ánh trạng thái thực tế.

Chaos engineering kiểm tra hệ thống bằng cách đưa một lỗi có chủ đích vào một phần đã chọn của môi trường, sau đó quan sát phản ứng. Mục tiêu là phát hiện điểm yếu trước khi sự cố thật xảy ra.

| Khái niệm | Ý nghĩa |
|---|---|
| Fault injection | Tạo một lỗi cụ thể như dừng Pod, tăng latency hoặc từ chối kết nối |
| Experiment | Một thử nghiệm có giả thuyết, phạm vi, bước thực hiện và điều kiện dừng |
| Blast radius | Phạm vi dịch vụ, dữ liệu hoặc người dùng có thể bị ảnh hưởng |
| Steady state | Trạng thái hoạt động bình thường được mô tả bằng các chỉ số đo được |
| Recovery | Quá trình hệ thống trở lại trạng thái đáp ứng SLO sau khi lỗi được loại bỏ |
| Game day | Buổi diễn tập có người tham gia, điều phối và đánh giá kết quả |

Thử nghiệm lỗi không phải là tạo sự cố tùy ý. Mỗi thử nghiệm phải có mục tiêu kiểm chứng cụ thể và có cách dừng hoặc khôi phục đã được chuẩn bị.

## 2. Bắt đầu từ SLO, RTO và RPO

Trước khi chọn lỗi để mô phỏng, cần xác định hệ thống phải duy trì điều gì và có thể chịu gián đoạn đến mức nào.

### SLI và SLO

Service Level Indicator (SLI) là chỉ số phản ánh chất lượng dịch vụ, ví dụ:

- Tỷ lệ request thành công.
- Phân vị độ trễ p95 hoặc p99.
- Tỷ lệ message được xử lý trong thời hạn.
- Tỷ lệ kết nối database thành công.
- Tỷ lệ phiên làm việc hoàn thành đúng nghiệp vụ.

Service Level Objective (SLO) là mục tiêu cho SLI trong một khoảng thời gian. Ví dụ, một API có thể đặt mục tiêu 99,9% request hợp lệ hoàn thành thành công trong cửa sổ 30 ngày. Ngưỡng thực tế phải xuất phát từ yêu cầu nghiệp vụ và thỏa thuận dịch vụ của tổ chức.

Error budget là phần lỗi hoặc gián đoạn còn có thể chấp nhận trong SLO. Thử nghiệm lỗi cần nằm trong chính sách sử dụng error budget và quy trình thay đổi của nhóm.

### RTO và RPO

Hai mục tiêu khôi phục thường dùng:

- **Recovery Time Objective (RTO):** thời gian tối đa chấp nhận để khôi phục dịch vụ sau sự cố.
- **Recovery Point Objective (RPO):** lượng dữ liệu tối đa có thể mất, thường được biểu diễn bằng khoảng thời gian dữ liệu.

Ví dụ:

| Hệ thống | RTO mục tiêu | RPO mục tiêu | Cách kiểm chứng |
|---|---:|---:|---|
| API đọc đơn hàng | 10 phút | Không mất dữ liệu đã xác nhận | Mất một Pod hoặc node và đo thời gian phục vụ lại |
| Cơ sở dữ liệu giao dịch | 15 phút | 5 phút | Thực hiện failover hoặc restore trên môi trường thử nghiệm |
| Consumer xử lý sự kiện | 20 phút | Không mất message đã publish và được lưu giữ | Dừng subscriber, khởi động lại và đối chiếu message |
| Báo cáo phân tích | 4 giờ | 1 giờ | Khôi phục từ backup hoặc dữ liệu đã export |

RTO và RPO trong bảng chỉ là ví dụ minh họa. Không dùng chúng làm cam kết mặc định cho dịch vụ GCP; hãy xác định mục tiêu theo kiến trúc, tier, region, cấu hình backup và hợp đồng vận hành.

Một thử nghiệm chỉ có kết quả tốt khi đo được thời gian phục hồi và mức mất dữ liệu thực tế, rồi so sánh với mục tiêu đã thống nhất.

## 3. Thiết kế giả thuyết thử nghiệm

Một thử nghiệm tốt bắt đầu bằng một giả thuyết có thể kiểm chứng. Ví dụ:

> Nếu một Pod của orders-api bị dừng đột ngột, Deployment sẽ tạo Pod thay thế, các replica còn lại tiếp tục phục vụ và tỷ lệ request thành công không giảm dưới ngưỡng SLO đã đặt.

Giả thuyết cần nêu rõ:

1. **Điều kiện ban đầu:** số replica, tải, trạng thái dependency, zone và cấu hình autoscaling.
2. **Tác động được tạo:** Pod bị dừng, latency tăng, node được drain hoặc subscriber tạm ngừng.
3. **Phạm vi:** namespace, cluster, service, project, zone và nhóm người dùng bị ảnh hưởng.
4. **Tín hiệu quan sát:** availability, latency, error rate, restart, queue backlog, database connections.
5. **Kết quả kỳ vọng:** workload tự phục hồi, traffic được chuyển hướng hoặc cảnh báo được gửi đúng.
6. **Điều kiện thất bại:** SLO bị vi phạm, RTO vượt ngưỡng, dữ liệu mất hoặc có lỗi ngoài phạm vi.
7. **Điều kiện dừng:** chỉ số nào buộc nhóm phải kết thúc thử nghiệm ngay.
8. **Cách khôi phục:** xóa fault injection, rollback cấu hình, scale lại hoặc phục hồi dịch vụ.

Ví dụ một bản mô tả ngắn:

| Thuộc tính | Giá trị |
|---|---|
| Experiment ID | EXP-GKE-001 |
| Giả thuyết | Một Pod lỗi không làm API mất khả năng phục vụ |
| Môi trường | Project và cluster dành riêng cho resilience lab |
| Tác động | Dừng một Pod thuộc Deployment có 3 replica |
| SLI | Tỷ lệ request thành công và p95 latency |
| Tiêu chí đạt | Replica thay thế sẵn sàng, SLO không bị vi phạm |
| Điều kiện dừng | Error rate vượt ngưỡng hoặc dependency bắt đầu lỗi dây chuyền |
| Người điều phối | Incident/experiment lead |
| Người quan sát | SRE và chủ sở hữu ứng dụng |

Không bắt đầu bằng một lỗi lớn như mất toàn bộ region nếu nhóm chưa chứng minh được khả năng phục hồi ở cấp Pod, node và dependency.

## 4. Kiểm soát an toàn và blast radius

Thử nghiệm lỗi có thể làm gián đoạn dịch vụ thật. Vì vậy, kiểm soát phạm vi và quyền dừng thử nghiệm là phần bắt buộc của thiết kế.

### Chọn môi trường phù hợp

Ưu tiên theo thứ tự:

1. Local hoặc môi trường mô phỏng.
2. Project thử nghiệm riêng.
3. Staging có dữ liệu giả lập và dependency được kiểm soát.
4. Production canary với phạm vi nhỏ, chỉ khi đã có phê duyệt và cơ chế bảo vệ phù hợp.

Không dùng dữ liệu khách hàng thật nếu không cần thiết. Không chạy thử nghiệm có thể xóa dữ liệu, làm lộ bí mật hoặc gây ảnh hưởng đến project ngoài phạm vi đã được phê duyệt.

### Giới hạn blast radius

- Chỉ định rõ project, cluster, namespace, label selector, instance group hoặc service.
- Bắt đầu với một replica, một node hoặc một nhóm request nhỏ.
- Không chọn selector rộng như toàn bộ namespace production nếu thử nghiệm chỉ nhắm một ứng dụng.
- Dùng tài khoản thực hiện riêng và quyền tối thiểu.
- Tách fault injection khỏi hệ thống điều khiển và kênh giám sát.
- Đặt thời lượng tối đa và thời điểm tự động kết thúc cho thử nghiệm có thể kéo dài.
- Không thử nghiệm nhiều loại lỗi đồng thời trong lần đầu, vì sẽ khó xác định nguyên nhân.

### Điều kiện dừng

Dừng thử nghiệm nếu xảy ra một trong các tình huống:

- Availability hoặc error rate vượt ngưỡng dừng đã đặt.
- Latency tăng đến mức ảnh hưởng người dùng hoặc dependency.
- Queue backlog tăng nhanh và không có dấu hiệu giảm.
- Database connections, CPU hoặc memory chạm ngưỡng nguy hiểm.
- Mất khả năng truy cập control plane, hệ thống giám sát hoặc kênh điều phối.
- Fault lan sang workload không nằm trong phạm vi.
- Phát hiện nguy cơ mất hoặc sửa dữ liệu ngoài dự kiến.

Người điều phối phải có quyền kết thúc thử nghiệm mà không cần chờ hết thời gian dự kiến.

### Chuẩn bị rollback

Trước khi chạy, cần biết chính xác cách xóa fault injection, phục hồi replica, uncordon node, rollback revision hoặc khôi phục cấu hình mạng. Ghi lại lệnh và người có quyền thực hiện. Kiểm tra đường truy cập quản trị độc lập để có thể khôi phục ngay cả khi workload thử nghiệm bị lỗi.

## 5. Quy trình thực hiện một experiment

Có thể tổ chức thử nghiệm theo chu trình sau:

~~~mermaid
flowchart TD
    A[Define reliability question] --> B[Set SLO and steady state]
    B --> C[Choose fault and blast radius]
    C --> D[Review permissions and stop conditions]
    D --> E[Capture baseline]
    E --> F[Inject one fault]
    F --> G[Observe system response]
    G --> H{SLO and safety maintained?}
    H -->|Yes| I[Remove fault and verify recovery]
    H -->|No| J[Stop experiment and contain impact]
    J --> K[Restore known-good state]
    I --> L[Compare evidence with hypothesis]
    K --> L
    L --> M[Record findings and actions]
~~~

Một lượt thử nghiệm nên có các giai đoạn:

**Trước thử nghiệm:** xác nhận môi trường, người tham gia, thời gian, SLO, dashboard, alert, baseline và rollback. Chụp trạng thái cấu hình cần thiết.

**Trong thử nghiệm:** chỉ tạo một fault đã chọn, ghi timestamp và theo dõi các chỉ số. Không thay đổi nhiều biến cùng lúc.

**Khi kết thúc:** loại bỏ fault, xác minh trạng thái bình thường, kiểm tra dữ liệu và traffic, ghi lại thời gian phục hồi.

**Sau thử nghiệm:** so sánh số liệu với giả thuyết, ghi vấn đề phát hiện được, phân loại mức độ và tạo action item có owner cùng deadline.

Nếu thử nghiệm thất bại, kết quả vẫn có giá trị. Điều cần tránh là che giấu thất bại hoặc đóng experiment khi chưa khôi phục hoàn toàn.

## 6. Kiểm chứng khả năng phục hồi trên GKE

GKE có nhiều lớp phục hồi: Kubernetes controller tạo Pod thay thế, scheduler bố trí Pod, node pool cung cấp compute, cluster autoscaler bổ sung node và regional cluster giúp giảm phụ thuộc vào một zone. Các lớp này có điều kiện và giới hạn khác nhau; cần kiểm tra từng giả thuyết riêng.

### Chuẩn bị workload có nhiều replica

Ví dụ Deployment trong namespace thử nghiệm:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders-api
  namespace: resilience-lab
spec:
  replicas: 3
  selector:
    matchLabels:
      app: orders-api
  template:
    metadata:
      labels:
        app: orders-api
    spec:
      containers:
        - name: app
          image: REGION-docker.pkg.dev/PROJECT_ID/lab/orders-api:VERSION
          ports:
            - name: http
              containerPort: 8080
          readinessProbe:
            httpGet:
              path: /health/ready
              port: http
            periodSeconds: 5
            failureThreshold: 3
          livenessProbe:
            httpGet:
              path: /health/live
              port: http
            periodSeconds: 10
            failureThreshold: 3
~~~

Ứng dụng cần thực sự triển khai hai endpoint health check phù hợp. Readiness xác định Pod có thể nhận traffic; liveness giúp kubelet khởi động lại container khi process không còn hoạt động đúng. Không dùng liveness probe quá nhạy để tránh restart dây chuyền khi ứng dụng chỉ đang chịu tải cao.

### Dùng PodDisruptionBudget

PodDisruptionBudget (PDB) giới hạn số Pod có thể bị gián đoạn trong một số thao tác eviction tự nguyện:

~~~yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: orders-api-pdb
  namespace: resilience-lab
spec:
  minAvailable: 2
  selector:
    matchLabels:
      app: orders-api
~~~

Với ba replica, PDB trên yêu cầu ít nhất hai Pod sẵn sàng trong các thao tác eviction được PDB kiểm soát. PDB không ngăn mọi dạng lỗi: xóa Pod trực tiếp, process crash, node mất điện hoặc zone outage có thể làm số Pod sẵn sàng giảm thấp hơn mức này.

### Phân tán Pod theo zone

Để tránh mọi replica tập trung vào một zone, có thể dùng topology spread constraints:

~~~yaml
topologySpreadConstraints:
  - maxSkew: 1
    topologyKey: topology.kubernetes.io/zone
    whenUnsatisfiable: DoNotSchedule
    labelSelector:
      matchLabels:
        app: orders-api
~~~

Đặt cấu hình này trong Pod template. Cần bảo đảm cluster có node ở đủ zone và capacity phù hợp. Nếu không có node ở một zone hoặc selector không khớp, scheduler có thể để Pod ở trạng thái Pending.

### Thử nghiệm mất một Pod

Sau khi xác nhận ba replica đều Ready, ghi lại trạng thái và chọn một Pod trong namespace lab:

~~~bash
kubectl get pods -n resilience-lab -l app=orders-api -o wide
kubectl get pdb -n resilience-lab
~~~

Trong môi trường thử nghiệm đã được phê duyệt, dừng một Pod cụ thể để kiểm tra controller tạo Pod thay thế:

~~~bash
kubectl delete pod POD_NAME -n resilience-lab
kubectl get pods -n resilience-lab -l app=orders-api -w
~~~

Thao tác xóa Pod trực tiếp mô phỏng mất Pod và không được PDB chặn như eviction. Theo dõi số replica Ready, request thành công, latency và thời gian Pod thay thế sẵn sàng.

### Thử nghiệm node drain

Node drain kiểm chứng khả năng di chuyển Pod trong một thao tác bảo trì tự nguyện. Chỉ chạy trên node thuộc cluster lab và sau khi xác nhận PDB, capacity cùng workload khác:

~~~bash
kubectl cordon NODE_NAME
kubectl drain NODE_NAME --ignore-daemonsets
~~~

Sau khi quan sát Pod được di chuyển và workload ổn định, đưa node trở lại trạng thái schedulable:

~~~bash
kubectl uncordon NODE_NAME
~~~

Lệnh drain có thể bị chặn bởi PDB hoặc Pod không được quản lý bởi controller. Không thêm tùy chọn xóa dữ liệu local chỉ để ép lệnh thành công. Nếu node chứa Pod dùng emptyDir hoặc workload có dữ liệu cục bộ, đánh giá tác động trước khi drain.

### Kiểm tra node auto-repair và cluster autoscaler

- Node auto-repair kiểm tra tình trạng node và có thể sửa chữa hoặc tạo lại node theo cấu hình.
- Cluster autoscaler điều chỉnh số node khi Pod không thể được scheduler bố trí do thiếu capacity và điều kiện autoscaling được đáp ứng.
- Node auto-provisioning có thể tạo node pool mới nếu tổ chức đã cấu hình tính năng này.

Thử nghiệm từng cơ chế riêng. Ghi lại thời gian phát hiện node lỗi, thời gian tạo node mới, thời gian Pod Ready và ảnh hưởng đến traffic. Không giả định autoscaler sẽ xử lý ngay mọi tình huống; giới hạn min/max node, quota, capacity zone và yêu cầu scheduling đều có thể ảnh hưởng.

## 7. Thử nghiệm lỗi mạng và dependency

Nhiều sự cố không làm Pod chết nhưng khiến request bị chậm hoặc thất bại. Ứng dụng cần có timeout, retry có giới hạn, exponential backoff, circuit breaker và xử lý lỗi dependency phù hợp.

### Các dạng lỗi nên kiểm chứng

| Fault | Hành vi cần kiểm tra |
|---|---|
| Latency tăng | Request có timeout đúng hạn? Queue có tăng không? |
| Packet loss | Retry có làm khuếch đại tải không? |
| DNS lỗi | Ứng dụng có cache DNS quá lâu hoặc fail fast? |
| Dependency unavailable | Circuit breaker có ngắt request lặp lại? |
| Connection reset | Client có phục hồi kết nối và xử lý request idempotent? |
| Egress bị chặn | Alert có phát hiện và runbook có chỉ đúng lớp mạng? |

### Dùng công cụ fault injection

Chaos Mesh là một công cụ mã nguồn mở có thể chạy trên Kubernetes để tạo một số dạng lỗi như Pod failure, network delay hoặc packet loss. Đây không phải dịch vụ được Google Cloud tự động bật trong GKE; nhóm cần triển khai, bảo mật và quản lý vòng đời công cụ riêng.

Ví dụ một NetworkChaos chỉ nhắm Pod có label `app: orders-api` trong namespace lab:

~~~yaml
apiVersion: chaos-mesh.org/v1alpha1
kind: NetworkChaos
metadata:
  name: orders-api-delay
  namespace: chaos-mesh
spec:
  action: delay
  mode: all
  selector:
    namespaces:
      - resilience-lab
    labelSelectors:
      app: orders-api
  delay:
    latency: "150ms"
    correlation: "25"
    jitter: "30ms"
  direction: to
  duration: "2m"
~~~

Manifest này chỉ là ví dụ cho cluster đã cài Chaos Mesh và CRD tương ứng. Kiểm tra phiên bản, quyền, schema và cách chọn target của công cụ trước khi áp dụng. Không triển khai controller chaos với quyền cluster-admin rộng nếu không cần.

Áp dụng trong lab:

~~~bash
kubectl apply -f orders-api-delay.yaml
kubectl get networkchaos -n chaos-mesh
~~~

Khi hết thời gian hoặc cần dừng sớm, xóa đối tượng experiment:

~~~bash
kubectl delete -f orders-api-delay.yaml
~~~

Sau khi xóa, xác minh latency trở lại baseline. Nếu hệ thống vẫn chậm, kiểm tra kết nối, retry storm, connection pool và trạng thái dependency. Xóa đối tượng fault injection không bảo đảm mọi tác động phụ đã biến mất.

### Kiểm tra timeout và retry

Ví dụ một API gọi dịch vụ inventory. Thử tăng latency ở dependency và quan sát:

- Client timeout có nhỏ hơn timeout của request tổng thể hay không.
- Retry có giới hạn số lần và có backoff hay không.
- Retry có dùng jitter để tránh nhiều client gọi lại cùng lúc hay không.
- Request ghi dữ liệu có idempotency key hoặc cơ chế chống xử lý trùng hay không.
- Circuit breaker có ngăn request mới khi dependency đang lỗi hay không.
- Queue và connection pool có trở về bình thường sau khi fault kết thúc hay không.

Retry không giới hạn có thể biến một dependency chậm thành sự cố toàn hệ thống. Mục tiêu của thử nghiệm là xác minh ứng dụng suy giảm có kiểm soát.

## 8. Kiểm chứng phục hồi trên Compute Engine và Cloud Run

### Compute Engine Managed Instance Groups

Managed Instance Group (MIG) có thể duy trì số lượng VM mong muốn, thay thế instance lỗi và hỗ trợ cập nhật theo rolling update. Regional MIG phân phối instance qua nhiều zone trong region theo cấu hình.

Các giả thuyết cần kiểm chứng:

- Health check phát hiện instance không khỏe trong thời gian dự kiến.
- Autohealing tạo VM thay thế.
- Load balancer ngừng gửi traffic đến backend không khỏe.
- MIG duy trì số instance mục tiêu nếu quota và capacity cho phép.
- Rolling update không làm giảm số instance phục vụ dưới mức đã định.

Trên một MIG dành riêng cho lab, có thể xóa một instance để kiểm tra việc tạo lại:

~~~bash
gcloud compute instance-groups managed list-instances "MIG_NAME" \
  --region="REGION" \
  --project="PROJECT_ID"
~~~

Chỉ thực hiện thao tác xóa instance sau khi xác nhận đúng MIG thử nghiệm, không có dữ liệu cục bộ cần giữ và autohealing đã được cấu hình. Sau đó theo dõi trạng thái instance, health check và backend service.

Không nhầm lẫn autohealing với backup. MIG tạo lại VM từ template; dữ liệu nằm trên boot disk hoặc local disk có thể không được giữ lại theo cách nhóm kỳ vọng. Dữ liệu cần tồn tại qua vòng đời VM phải nằm trong dịch vụ lưu trữ phù hợp.

### Cloud Run

Cloud Run quản lý hạ tầng container và khởi tạo instance theo nhu cầu. Thử nghiệm có thể tập trung vào:

- Revision mới khởi động lỗi hoặc không vượt readiness/startup check.
- Dependency chậm khiến request timeout.
- Instance đạt giới hạn concurrency hoặc max instances.
- Một revision có error rate cao sau khi nhận traffic.
- Traffic được chuyển về revision ổn định khi rollback.

Có thể triển khai revision thử nghiệm và dùng traffic splitting trên dịch vụ lab. Ghi lại revision, image digest, cấu hình concurrency, timeout, min/max instances và tỷ lệ traffic trước khi thử.

Ví dụ xem revision và traffic:

~~~bash
gcloud run services describe "SERVICE_NAME" \
  --region="REGION" \
  --project="PROJECT_ID" \
  --format=yaml
~~~

Rollback cần dùng revision đã biết tốt và xác minh lại traffic, không chỉ kiểm tra lệnh cập nhật thành công. Nếu ứng dụng có side effect hoặc migration database, rollback container không tự đảo ngược thay đổi dữ liệu. Cần thiết kế migration tương thích ngược và quy trình phục hồi dữ liệu riêng.

## 9. Kiểm chứng Cloud SQL, Pub/Sub và Cloud Storage

### Cloud SQL: HA, failover và khôi phục dữ liệu

Cloud SQL HA trong một region sử dụng primary và standby với cơ chế failover được quản lý. Khi failover, endpoint kết nối của instance được giữ theo thiết kế dịch vụ, nhưng các kết nối hiện hữu có thể bị ngắt và ứng dụng phải kết nối lại.

HA và disaster recovery là hai mục tiêu khác nhau:

- HA xử lý lỗi trong region theo cấu hình của instance.
- Backup và point-in-time recovery (PITR) hỗ trợ phục hồi dữ liệu.
- Cross-region DR cần chiến lược sao lưu, replica hoặc kiến trúc dự phòng phù hợp với mục tiêu RTO/RPO.

Thử nghiệm trên instance không phục vụ production:

1. Ghi nhận cấu hình HA, backup, PITR, maintenance và connection pool.
2. Tạo tải thử đại diện cho nghiệp vụ.
3. Thực hiện failover theo quy trình và quyền được phê duyệt.
4. Đo thời gian kết nối thất bại, thời điểm kết nối lại và thời gian nghiệp vụ ổn định.
5. Kiểm tra dữ liệu giao dịch, tính nhất quán và lỗi retry.
6. Thử restore từ backup hoặc PITR trên instance riêng để xác minh RPO.

Không thực hiện failover hoặc restore trên instance production chỉ để diễn tập nếu chưa có kế hoạch thay đổi và phê duyệt rõ ràng. Backup thành công không chứng minh restore thành công; phải định kỳ thử phục hồi và xác minh dữ liệu.

### Pub/Sub: subscriber dừng hoạt động

Một subscriber có thể tạm ngừng trong khi publisher vẫn gửi message. Thử nghiệm này giúp kiểm tra backlog, retry, ack deadline và dead-letter topic.

Quy trình:

1. Ghi nhận số lượng message, throughput, oldest unacked message age và subscription backlog.
2. Dừng subscriber trong môi trường lab.
3. Tiếp tục publish message có ID kiểm thử.
4. Khởi động lại subscriber và quan sát tốc độ xử lý backlog.
5. Kiểm tra duplicate delivery, thứ tự message nếu có yêu cầu ordering và logic idempotency.
6. Xác minh message không bị mất trước thời hạn retention và subscriber phục hồi trong RTO.

Pub/Sub có semantics at-least-once trong các cấu hình phổ biến; consumer cần xử lý message trùng an toàn. Không mặc định một message chỉ được xử lý đúng một lần. Nếu dùng dead-letter topic, kiểm tra số lần delivery, quyền IAM và quy trình phát lại message.

### Cloud Storage: truy cập và khôi phục object

Có thể kiểm chứng việc ứng dụng xử lý lỗi permission hoặc object không tồn tại bằng bucket lab:

- Thu hẹp quyền đọc của service account thử nghiệm và xác minh ứng dụng xử lý 403 đúng cách.
- Thử truy cập object bị thiếu và kiểm tra lỗi 404.
- Bật object versioning trong bucket lab, ghi một phiên bản object thử nghiệm rồi kiểm tra khả năng khôi phục generation cũ.
- Kiểm tra retention policy và quy trình phục hồi object.

Không thử xóa hàng loạt, ghi đè dữ liệu thật hoặc thay đổi retention của bucket production. Nếu versioning chưa được bật trước khi object bị ghi đè hoặc xóa, không thể giả định có thể phục hồi phiên bản cũ.

## 10. Quan sát và đo lường trong khi thử nghiệm

Thử nghiệm không có quan sát sẽ không chứng minh được khả năng phục hồi. Cần ghi lại baseline, thời điểm bắt đầu fault, thời điểm phát hiện, thời điểm hệ thống phản ứng và thời điểm phục hồi.

### Các chỉ số nên theo dõi

| Nhóm | SLI/metric gợi ý | Mục đích |
|---|---|---|
| Availability | Request success ratio, uptime check | Xác định dịch vụ có tiếp tục phục vụ |
| Latency | p50, p95, p99 | Phát hiện suy giảm trải nghiệm |
| Errors | 4xx/5xx, timeout, retry count | Xác định tác động của fault |
| Saturation | CPU, memory, queue depth, connection pool | Phát hiện cạn tài nguyên |
| Kubernetes | Pod Ready, restart, Pending, node condition | Đo phản ứng của scheduler và controller |
| Database | Connection errors, failover duration, replication lag | Kiểm chứng HA và data recovery |
| Messaging | Backlog, oldest unacked age, dead-letter count | Đo khả năng xử lý lại sự kiện |
| Cost/capacity | Instance count, node count, autoscaling events | Phát hiện phục hồi làm tăng tải hoặc chi phí |

Cloud Monitoring cung cấp dashboard, alerting và metrics cho nhiều dịch vụ GCP. Với metrics ứng dụng, có thể dùng Managed Service for Prometheus trên GKE và truy vấn bằng PromQL. Log từ Cloud Logging và Cloud Audit Logs giúp ghép thời điểm lỗi với hành động quản trị.

### Tính thời gian phục hồi

Ghi ít nhất các mốc:

- T0: bắt đầu tạo fault.
- T1: hệ thống hoặc người vận hành phát hiện.
- T2: cơ chế tự phục hồi bắt đầu.
- T3: workload hoặc dependency trở lại trạng thái sẵn sàng.
- T4: SLI trở lại trong giới hạn SLO.

Có thể tính:

\[
\text{Detection Time} = T1 - T0
\]

\[
\text{Recovery Time} = T4 - T0
\]

Recovery Time nên được đo từ lúc fault bắt đầu đến khi dịch vụ thực sự trở lại SLO, không chỉ đến lúc Pod hoặc VM mới xuất hiện.

### Kết hợp log, metric và trace

- Metrics cho biết mức độ và thời gian ảnh hưởng.
- Logs cung cấp sự kiện và chi tiết nguyên nhân.
- Traces giúp tìm dependency hoặc đoạn xử lý làm tăng latency.

Dùng cùng correlation ID hoặc trace context nếu ứng dụng hỗ trợ. Đồng bộ thời gian giữa các thành phần và ghi timestamp UTC trong hồ sơ experiment.

## 11. Đánh giá kết quả và cải thiện kiến trúc

Sau mỗi thử nghiệm, phân loại kết quả:

| Kết quả | Diễn giải | Hành động |
|---|---|---|
| Pass | Giả thuyết đúng, SLO được giữ và recovery đạt mục tiêu | Lưu bằng chứng, tiếp tục mở rộng phạm vi từng bước |
| Pass with degradation | Dịch vụ vẫn hoạt động nhưng latency hoặc error tăng | Đánh giá ngưỡng SLO, tối ưu capacity và dependency |
| Fail | SLO hoặc RTO/RPO không đạt | Tạo remediation, sửa kiến trúc hoặc quy trình |
| Invalid experiment | Fault không được tạo đúng hoặc dữ liệu quan sát thiếu | Sửa thiết kế và chạy lại trong phạm vi an toàn |
| Aborted | Điều kiện dừng được kích hoạt | Khôi phục, phân tích tác động và điều chỉnh guardrail |

Các vấn đề thường phát hiện được:

- PDB cấu hình quá chặt khiến drain node bị chặn.
- Replica tập trung ở một zone.
- Readiness probe không phản ánh khả năng xử lý request thật.
- HPA không scale kịp hoặc thiếu node capacity.
- Retry không giới hạn gây retry storm.
- Connection pool không phục hồi sau failover database.
- Consumer xử lý message trùng gây ghi dữ liệu lặp.
- Backup có nhưng không thể restore trong RTO.
- Alert phát hiện quá muộn hoặc không có người nhận.
- Runbook yêu cầu quyền mà người trực không có.

Mỗi finding cần có owner, mức độ ưu tiên, deadline và cách kiểm chứng sau khi sửa. Không đóng action item chỉ vì cấu hình đã được thay đổi; cần chạy lại thử nghiệm để chứng minh vấn đề đã được khắc phục.

## 12. Tình huống thực hành: kiểm chứng phục hồi orders-api

Một hệ thống có các thành phần:

- `orders-api` chạy trên GKE với ba replica.
- Cloud SQL lưu đơn hàng.
- Pub/Sub nhận sự kiện đơn hàng mới.
- Cloud Monitoring theo dõi request rate, error rate và latency.

Mục tiêu là xác minh API chịu được mất một Pod và xử lý được tình huống Cloud SQL tạm thời không phản hồi.

### Giai đoạn A — Baseline

1. Xác nhận ba Pod đều Ready và nằm trên các node phù hợp.
2. Kiểm tra PDB, topology spread và HPA.
3. Gửi tải thử ổn định trong thời gian đủ để tạo baseline.
4. Ghi request success ratio, p95 latency, CPU, memory và số kết nối database.
5. Xác nhận dashboard và alert hoạt động.

### Giai đoạn B — Mất một Pod

1. Chọn một Pod trong namespace lab.
2. Ghi tên Pod, node, UID và thời điểm bắt đầu.
3. Xóa Pod đã chọn.
4. Theo dõi Deployment tạo Pod thay thế.
5. Đo thời gian Pod mới Ready và thời gian SLI trở lại baseline.
6. Kiểm tra không có đơn hàng bị ghi trùng hoặc mất.

Giả thuyết đạt nếu hai Pod còn lại tiếp tục phục vụ, Pod thay thế được tạo và SLO không bị vi phạm.

### Giai đoạn C — Dependency chậm

1. Dùng công cụ fault injection đã cài trong lab để tạo latency có giới hạn đến dependency thử nghiệm.
2. Quan sát timeout, retry, connection pool, request queue và error rate.
3. Kết thúc fault theo thời gian đã đặt hoặc dừng ngay nếu chạm ngưỡng.
4. Xác minh connection pool và request latency trở lại bình thường.
5. Kiểm tra dữ liệu đơn hàng và consumer Pub/Sub.

Giả thuyết đạt nếu API suy giảm có kiểm soát, không tạo retry storm và không ghi dữ liệu sai.

### Giai đoạn D — Xác minh phục hồi

- Đối chiếu dữ liệu trước và sau experiment.
- Xác nhận backlog Pub/Sub trở về mức bình thường.
- Kiểm tra không còn fault injection hoặc cấu hình thử nghiệm.
- Xác nhận dashboard, alert và log ghi nhận đầy đủ.
- Tính Recovery Time và so sánh với RTO.
- Ghi finding, remediation và owner.

Không tiến hành giai đoạn dependency fault nếu giai đoạn mất Pod chưa được khôi phục hoàn toàn. Mỗi giai đoạn cần được đánh giá và xác nhận trước khi tiếp tục.

## 13. Checklist tổ chức chaos experiment

### Trước thử nghiệm

- [ ] Có giả thuyết cụ thể và tiêu chí đạt/thất bại.
- [ ] Đã xác định SLI, SLO, error budget, RTO và RPO liên quan.
- [ ] Chọn đúng project, cluster, namespace và workload.
- [ ] Có người điều phối, người quan sát và người có quyền dừng.
- [ ] Có baseline metrics, dashboard, alert và log.
- [ ] Đã kiểm tra backup, rollback và đường quản trị.
- [ ] Đã phê duyệt thời gian, blast radius và điều kiện dừng.

### Trong thử nghiệm

- [ ] Chỉ tạo một fault theo kế hoạch.
- [ ] Ghi timestamp và trạng thái trước/sau mỗi thao tác.
- [ ] Theo dõi availability, latency, errors và saturation.
- [ ] Theo dõi dependency, queue và dữ liệu.
- [ ] Dừng ngay khi điều kiện an toàn bị vi phạm.

### Sau thử nghiệm

- [ ] Đã xóa fault injection và khôi phục cấu hình.
- [ ] Workload, dependency và dữ liệu đã được xác minh.
- [ ] SLI trở lại trong giới hạn SLO.
- [ ] Recovery Time và mức mất dữ liệu được ghi nhận.
- [ ] Kết quả, log và dashboard được lưu làm bằng chứng.
- [ ] Finding có owner, deadline và kế hoạch kiểm chứng lại.
- [ ] Runbook và kiến trúc được cập nhật nếu cần.

Thử nghiệm lỗi trên GCP giúp nhóm SRE biến giả định về độ tin cậy thành bằng chứng đo được. Khi mỗi experiment có giả thuyết, phạm vi, điều kiện dừng, tín hiệu quan sát và quy trình phục hồi rõ ràng, tổ chức có thể phát hiện điểm yếu trước sự cố thật, cải thiện RTO/RPO và nâng cao khả năng phục hồi của các dịch vụ đang vận hành.

