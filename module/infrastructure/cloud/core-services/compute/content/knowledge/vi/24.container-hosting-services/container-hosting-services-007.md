# Rolling update, phân chia lưu lượng và rollback phiên bản

Ứng dụng chạy container thường được cập nhật bằng cách phát hành image mới rồi thay dần các container đang phục vụ. Nếu thay toàn bộ cùng lúc, dịch vụ có thể mất khả năng phục vụ trong lúc container mới khởi động; nếu đưa phiên bản mới tới toàn bộ người dùng mà chưa kiểm chứng, một lỗi ứng dụng có thể ảnh hưởng toàn hệ thống. Vì vậy, nền tảng container cần phối hợp ba cơ chế: **rolling update** để thay thế workload theo từng bước, **traffic splitting** để kiểm soát tỷ lệ request tới từng phiên bản và **rollback** để quay lại phiên bản ổn định khi rollout không đạt yêu cầu.

Ba cơ chế này giải quyết các phần khác nhau của một lần phát hành. Rolling update điều khiển vòng đời replica; traffic splitting điều khiển request tới phiên bản; rollback điều khiển cách khôi phục ứng dụng và cấu hình khi phát hiện lỗi. Chúng cần dựa trên image bất biến, readiness, quan sát SLI/SLO và khả năng tương thích dữ liệu. Bài học này trình bày cách thiết kế và vận hành quy trình phát hành container có kiểm soát trong môi trường compute.

## 1. Mục tiêu của một lần cập nhật an toàn

Một deployment tốt cần đạt các mục tiêu:

- Duy trì đủ replica khỏe trong suốt quá trình thay phiên bản.
- Chỉ gửi traffic tới container đã sẵn sàng xử lý request.
- Giới hạn phạm vi ảnh hưởng của phiên bản mới.
- Phát hiện lỗi qua metrics, logs, traces và health checks.
- Có tiêu chí dừng rollout và quy trình rollback rõ ràng.
- Bảo đảm phiên bản cũ và mới có thể cùng tồn tại trong thời gian chuyển tiếp.
- Không làm hỏng dữ liệu hoặc giao dịch đang xử lý.
- Có thể xác định chính xác image, config và release đang chạy ở mỗi replica.

Không thể bảo đảm zero downtime chỉ bằng cách chọn rolling update. Ứng dụng cần hỗ trợ graceful shutdown, readiness đúng, session phù hợp và dependency tương thích. Nếu mọi replica cùng lỗi do database migration hoặc cấu hình dùng chung, rolling update vẫn có thể gây gián đoạn.

## 2. Các khái niệm cần thống nhất

| Khái niệm | Ý nghĩa |
|---|---|
| Release | Một lần phát hành ứng dụng cùng image, cấu hình và metadata liên quan |
| Image tag | Tên tham chiếu tới image, ví dụ checkout:2.4.1 |
| Image digest | Định danh nội dung image bất biến, ví dụ sha256:... |
| Replica | Một bản chạy của workload, thường là container hoặc Pod |
| ReplicaSet | Kubernetes controller duy trì số Pod theo một Pod template |
| Deployment | Kubernetes resource quản lý rollout và các ReplicaSet của ứng dụng stateless |
| Readiness | Tín hiệu cho biết instance có thể nhận traffic |
| Rollout | Quá trình chuyển workload từ phiên bản hiện tại sang phiên bản mới |
| Canary | Phát hành phiên bản mới cho một phần nhỏ traffic trước khi mở rộng |
| Blue-green | Duy trì hai môi trường/nhóm phiên bản và chuyển traffic từ nhóm cũ sang nhóm mới |
| Rollback | Quay lại release đã biết là ổn định |
| Roll forward | Phát hành bản sửa tiếp theo để khắc phục lỗi |

Nên ghi nhận release ID, image digest, source revision, thời điểm deploy và người hoặc automation khởi tạo. Tag như latest có thể thay đổi theo thời gian; dùng digest hoặc tag phiên bản bất biến giúp xác định chính xác artifact đã được triển khai.

## 3. Rolling update hoạt động như thế nào?

Rolling update thay thế replica cũ theo từng đợt. Orchestrator tạo một số replica mới, chờ chúng sẵn sàng rồi giảm số replica cũ. Quá trình tiếp tục cho tới khi toàn bộ workload chạy phiên bản mới.

~~~mermaid
flowchart TD
    A[4 replica phiên bản v1] --> B[Tạo 1 replica v2]
    B --> C[Chờ readiness v2 đạt]
    C --> D[Giảm 1 replica v1]
    D --> E[Tạo replica v2 tiếp theo]
    E --> F[Chờ readiness rồi giảm v1]
    F --> G[Hoàn tất: 4 replica v2]
~~~

Trong giai đoạn chuyển tiếp, phiên bản cũ và mới cùng tồn tại. Điều này giúp giữ capacity nhưng yêu cầu hai phiên bản tương thích với cùng database, message schema, cache và API contract.

### 3.1. MaxSurge và MaxUnavailable

Với Kubernetes Deployment, maxSurge giới hạn số Pod được tạo vượt quá số replica mong muốn trong rolling update; maxUnavailable giới hạn số Pod có thể không khả dụng trong quá trình cập nhật.

Ví dụ, Deployment có 4 replica:

- maxSurge: 1 cho phép tạo tối đa 1 Pod vượt số replica mong muốn.
- maxUnavailable: 1 cho phép tối đa 1 Pod không khả dụng theo cách tính của Deployment trong rollout.
- Cấu hình maxSurge: 1, maxUnavailable: 0 ưu tiên giữ đủ số replica khả dụng nhưng cần capacity bổ sung để chạy Pod mới.

Kubernetes thường mặc định các giá trị này là 25% nếu không chỉ định, nhưng hãy khai báo rõ theo capacity và SLO. Giá trị phần trăm được làm tròn theo quy tắc của Kubernetes; với workload ít replica, kết quả có thể khác trực giác.

Không nên đặt maxSurge cao nếu cluster không còn CPU/RAM hoặc quota để tạo thêm Pod. Ngược lại, maxUnavailable quá cao có thể làm giảm capacity phục vụ trong rollout.

## 4. Readiness, liveness và startup probe

Rolling update chỉ an toàn nếu orchestrator biết khi nào container mới có thể nhận traffic.

- **Startup probe:** cho ứng dụng thời gian khởi động; liveness/readiness chưa được đánh giá theo cách thông thường cho tới khi startup probe thành công.
- **Readiness probe:** xác định Pod có đủ điều kiện nhận request hay không.
- **Liveness probe:** xác định container có cần được khởi động lại vì không còn hoạt động đúng hay không.

Readiness không nên chỉ kiểm tra process còn sống hoặc port đã mở. Nếu ứng dụng chưa tải xong cấu hình, chưa kết nối dependency thiết yếu hoặc chưa warm-up, nó có thể trả lỗi dù port vẫn mở.

Liveness không nên phụ thuộc vào một dịch vụ ngoài dễ chập chờn. Nếu database tạm thời lỗi và liveness probe thất bại trên tất cả Pod, Kubernetes có thể restart hàng loạt container trong khi restart không giải quyết được dependency outage.

Ví dụ cấu hình probe trong Pod template:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: checkout-api
spec:
  replicas: 4
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0
  minReadySeconds: 10
  progressDeadlineSeconds: 600
  revisionHistoryLimit: 5
  selector:
    matchLabels:
      app: checkout-api
  template:
    metadata:
      labels:
        app: checkout-api
    spec:
      terminationGracePeriodSeconds: 45
      containers:
        - name: api
          image: registry.example.com/checkout-api@sha256:REPLACE_WITH_DIGEST
          ports:
            - name: http
              containerPort: 8080
          startupProbe:
            httpGet:
              path: /health/startup
              port: http
            periodSeconds: 5
            failureThreshold: 30
          readinessProbe:
            httpGet:
              path: /health/ready
              port: http
            periodSeconds: 5
            failureThreshold: 2
          livenessProbe:
            httpGet:
              path: /health/live
              port: http
            periodSeconds: 10
            failureThreshold: 3
~~~

Đây là mẫu minh họa. Thay registry, digest, endpoint và ngưỡng theo ứng dụng. Probe quá nhạy có thể tạo restart loop hoặc làm Pod liên tục bị loại khỏi Service; probe quá lỏng có thể để request đi vào Pod chưa khỏe.

## 5. Graceful shutdown và drain traffic

Khi Pod bị thay thế, container cũ cần thời gian kết thúc request đang chạy. Nếu process bị kill ngay, client có thể nhận connection reset, request bị xử lý dở hoặc worker làm mất message.

Quy trình shutdown thường gồm:

1. Đánh dấu instance không còn readiness.
2. Chờ endpoint controller, proxy hoặc load balancer cập nhật backend.
3. Ngừng nhận request/job mới.
4. Hoàn tất request hiện tại trong thời gian cho phép.
5. Ngừng consumer nhận message mới; hoàn tất hoặc requeue job an toàn.
6. Flush log, đóng connection và giải phóng tài nguyên.
7. Thoát trước khi hết termination grace period.

Trong Kubernetes, terminationGracePeriodSeconds đặt giới hạn thời gian kết thúc Pod. preStop hook, nếu có, chạy trong khoảng grace period đó; thời gian hook không được cộng thêm ngoài giới hạn. Sau deadline, container có thể bị kết thúc cưỡng bức.

Cần kiểm tra ứng dụng có xử lý SIGTERM không. Chỉ tăng grace period không giải quyết được process không có graceful shutdown hoặc request không có timeout.

## 6. Rollout Deployment trên Kubernetes

Các lệnh thường dùng:

~~~bash
# Áp dụng manifest mới
kubectl apply -f deployment.yaml

# Theo dõi rollout
kubectl rollout status deployment/checkout-api

# Xem lịch sử các revision
kubectl rollout history deployment/checkout-api

# Xem chi tiết một revision
kubectl rollout history deployment/checkout-api --revision=3

# Xem Pod theo label
kubectl get pods -l app=checkout-api -o wide

# Xem sự kiện và lý do Pod chưa sẵn sàng
kubectl describe deployment checkout-api
kubectl describe pod POD_NAME
~~~

kubectl rollout status cho biết tiến độ rollout theo trạng thái của Deployment. Lệnh hoàn tất không thay thế kiểm tra nghiệp vụ, latency, error rate hoặc dữ liệu. Cần tiếp tục quan sát sau khi tất cả replica đã chuyển phiên bản.

### 6.1. MinReadySeconds và progress deadline

minReadySeconds yêu cầu Pod phải ở trạng thái Ready liên tục trong một khoảng thời gian trước khi được xem là available cho Deployment. Điều này giảm nguy cơ coi một Pod vừa qua readiness trong chốc lát là đã ổn định.

progressDeadlineSeconds giới hạn thời gian Deployment được phép không có tiến triển. Khi vượt ngưỡng, Deployment có thể báo ProgressDeadlineExceeded; controller không tự động rollback chỉ vì điều kiện này xảy ra. Pipeline phát hành cần phát hiện trạng thái và kích hoạt quyết định dừng/rollback theo policy.

### 6.2. PodDisruptionBudget có vai trò gì?

PodDisruptionBudget (PDB) giới hạn số Pod có thể bị gián đoạn trong các voluntary disruption đi qua eviction API, ví dụ khi drain node. PDB hữu ích cho bảo trì node và một số thao tác điều phối, nhưng không thay thế maxSurge, maxUnavailable, readiness hoặc capacity planning của Deployment rollout. Không nên giả định PDB tự bảo vệ mọi lần rollout do Deployment controller thực hiện.

## 7. Phân chia lưu lượng giữa các phiên bản

Rolling update thay replica theo tiến trình controller. Traffic splitting chủ động chọn tỷ lệ request tới các phiên bản khác nhau. Hai cách có thể kết hợp nhưng không đồng nghĩa.

Ví dụ, phiên bản stable nhận 95% request và phiên bản canary nhận 5%. Nếu canary đáp ứng SLO, tỷ lệ có thể tăng dần.

~~~mermaid
flowchart LR
    C[Client traffic] --> R[Ingress / Gateway / Service Mesh]
    R -->|95%| S[Stable v1]
    R -->|5%| K[Canary v2]
    S --> M[Metrics and traces]
    K --> M
    M --> D{SLO đạt?}
    D -->|Có| P[Tăng tỷ lệ canary]
    D -->|Không| X[Ngừng canary và rollback]
~~~

Các cách triển khai traffic split:

- Gateway hoặc ingress có weighted routing.
- Service mesh có traffic policy theo subset/version.
- Global traffic manager nếu phiên bản nằm ở các cụm/region khác nhau.
- Feature flag để bật tính năng mới cho nhóm người dùng được chọn.
- Header/cookie routing để thử nghiệm có kiểm soát.

Khả năng hỗ trợ trọng số và độ chính xác phụ thuộc controller, proxy và nền tảng. Một số cấu hình chia theo connection thay vì từng request; keep-alive hoặc HTTP/2 multiplexing có thể khiến tỷ lệ request quan sát khác tỷ lệ connection.

### 7.1. Canary release theo từng bước

Một kế hoạch minh họa:

| Giai đoạn | Tỷ lệ canary | Điều kiện tiếp tục |
|---|---:|---|
| Khởi đầu | 1% | Smoke test và health check đạt |
| Bước 2 | 5% | Error rate và latency không xấu hơn ngưỡng |
| Bước 3 | 10% | Không có lỗi nghiệp vụ hoặc dependency bất thường |
| Bước 4 | 25% | p95/p99, throughput và resource utilization đạt |
| Bước 5 | 50% | Không có regression có ý nghĩa |
| Hoàn tất | 100% | Đạt SLO trong thời gian quan sát đã định |

Tỷ lệ và thời gian chỉ là ví dụ. Với lượng request thấp, 1% có thể tạo quá ít mẫu để kết luận. Cần đủ số request, đủ thời gian và đại diện cho các nhóm người dùng/workload quan trọng.

### 7.2. Chọn nhóm người dùng cho canary

Có thể chọn canary theo:

- Tỷ lệ ngẫu nhiên của request.
- Một tập user/account nội bộ.
- Header hoặc cookie do test client gửi.
- Khu vực, tenant hoặc loại workload.
- Một nhóm job nền có thể chạy lại.

Không nên đưa nhóm người dùng dễ bị ảnh hưởng nhất vào canary đầu tiên. Với thao tác ghi dữ liệu hoặc thanh toán, cần có idempotency, audit và giới hạn tác động. Canary không phải nơi để thử thay đổi có thể gây mất dữ liệu.

### 7.3. Sticky routing và session

Nếu cùng một người dùng được chuyển qua lại giữa hai phiên bản, session hoặc cache cục bộ có thể không tương thích. Sticky routing giữ người dùng ở một phiên bản trong thời gian thử nghiệm, nhưng có thể làm traffic không phân phối đều.

Ứng dụng stateless hoặc dùng session store tương thích giúp chuyển traffic an toàn hơn. Khi cần sticky routing, xác định hành vi khi backend lỗi, cookie hết hạn hoặc phiên bản bị rollback.

## 8. Blue-green deployment

Blue-green duy trì hai nhóm môi trường:

- **Blue:** phiên bản hiện tại đang phục vụ.
- **Green:** phiên bản mới đã được triển khai và kiểm thử.

Sau khi Green đạt readiness và smoke test, load balancer hoặc service routing chuyển traffic từ Blue sang Green. Nếu phát hiện lỗi, traffic có thể chuyển lại Blue khi Blue vẫn còn sẵn sàng.

~~~mermaid
flowchart TD
    U[Users] --> L[Load balancer]
    L -->|Trước cutover| B[Blue: version v1]
    L -.->|Sau cutover| G[Green: version v2]
    G --> H[Health and smoke tests]
    H --> D{Đạt yêu cầu?}
    D -->|Có| C[Chuyển toàn bộ traffic sang Green]
    D -->|Không| R[Giữ hoặc chuyển lại Blue]
~~~

Ưu điểm:

- Có thể kiểm thử phiên bản mới trước khi nhận traffic production.
- Chuyển traffic nhanh khi endpoint và dữ liệu tương thích.
- Dễ quay lại nhóm cũ trong cửa sổ rollback.

Trade-off:

- Cần capacity cho hai nhóm cùng tồn tại.
- Database và queue có thể được cả hai phiên bản truy cập đồng thời.
- Session, cache và side effect phải tương thích.
- Blue không thể bị xóa quá sớm nếu còn cần rollback.

Blue-green có thể dùng hai Deployment/Service trong Kubernetes, hai node pool, hai cụm hoặc hai môi trường độc lập. Tên Blue/Green là nhãn logic; cách triển khai cụ thể tùy nền tảng.

## 9. So sánh rolling, canary và blue-green

| Tiêu chí | Rolling update | Canary | Blue-green |
|---|---|---|---|
| Cách thay phiên bản | Thay dần replica | Mở traffic nhỏ cho bản mới rồi tăng dần | Chuẩn bị nhóm mới rồi chuyển traffic |
| Kiểm soát traffic | Thường dựa readiness và rollout strategy | Có trọng số/nhóm người dùng rõ | Chuyển traffic giữa hai nhóm |
| Capacity tạm thời | Cần surge capacity theo cấu hình | Cần chạy đồng thời stable và canary | Có thể cần gần gấp đôi capacity |
| Phát hiện lỗi | Qua rollout và telemetry | Qua so sánh stable/canary | Qua test trước/sau cutover |
| Tốc độ rollback | Phụ thuộc rollout và revision | Ngừng canary, đưa tỷ lệ về 0 | Chuyển traffic về Blue |
| Phù hợp | Thay đổi tương thích, release thường xuyên | Thay đổi cần kiểm chứng dưới traffic thật | Release cần cutover nhanh hoặc môi trường kiểm thử độc lập |

Không có chiến lược nào luôn phù hợp. Rolling update đơn giản và tiết kiệm capacity hơn trong nhiều trường hợp. Canary phù hợp khi cần đo tác động với traffic thật. Blue-green phù hợp khi cần kiểm thử phiên bản mới tách biệt và có capacity để giữ hai nhóm.

## 10. Đo lường và tiêu chí tự động dừng rollout

Không nên quyết định rollout chỉ dựa trên trạng thái Pod Ready. Cần theo dõi các chỉ số ở cả phiên bản stable và canary:

- Request rate và successful throughput.
- Error rate theo status code và loại lỗi nghiệp vụ.
- Latency p50/p95/p99.
- CPU, memory, throttling và restart count.
- Queue depth, message age và retry.
- DB connection pool, query latency và lock wait.
- Dependency timeout và circuit breaker open count.
- Saturation của node, network và storage.
- Business metric như giao dịch hoàn tất, đơn hàng thành công hoặc tỷ lệ thanh toán.

Một policy canary có thể yêu cầu:

- Error rate không vượt baseline quá ngưỡng cho phép.
- p95/p99 không tăng vượt biên đã định.
- Không xuất hiện lỗi correctness hoặc data integrity.
- Không có OOM/restart loop.
- Không tăng bất thường retry, queue age hoặc dependency saturation.
- Đủ số request và thời gian quan sát tối thiểu.

Nên so canary với stable trong cùng thời điểm để giảm ảnh hưởng của biến động tải. So sánh với một baseline cũ có thể gây hiểu nhầm nếu demand hoặc dependency đã thay đổi.

### 10.1. Phân biệt lỗi của phiên bản và lỗi toàn hệ thống

Nếu stable và canary cùng tăng latency, nguyên nhân có thể là database, network hoặc tải tổng thể. Nếu chỉ canary tăng lỗi, khả năng regression trong phiên bản mới cao hơn. Dùng label version/release trong metrics và traces để tách hai nhóm.

Tránh dùng user ID hoặc giá trị cardinality cao làm label metrics nếu hệ thống không hỗ trợ; có thể làm tăng chi phí và tải ingestion. Giữ định danh chi tiết trong log/trace có kiểm soát.

## 11. Tương thích schema và contract khi hai phiên bản cùng chạy

Trong rolling update hoặc canary, v1 và v2 có thể cùng truy cập một database hoặc queue. Thay đổi schema theo kiểu phá vỡ tương thích có thể làm phiên bản cũ lỗi ngay khi bản mới bắt đầu rollout.

Một quy trình an toàn thường dùng mô hình **expand and contract**:

1. **Expand:** thêm cột/table/field mới theo cách tương thích ngược.
2. **Deploy compatible code:** phiên bản mới có thể đọc dữ liệu cũ và ghi dữ liệu mới theo quy tắc đã định.
3. **Migrate data:** backfill hoặc chuyển dữ liệu theo batch có kiểm soát.
4. **Switch usage:** chuyển dần code sang field/schema mới.
5. **Contract:** chỉ xóa field hoặc cấu trúc cũ sau khi mọi phiên bản cũ đã ngừng dùng và rollback window kết thúc.

Với message queue, cần version hóa event/schema hoặc thiết kế consumer chấp nhận cả format cũ và mới. Với API, tránh thay đổi contract phá vỡ client đang dùng phiên bản trước.

Rollback ứng dụng không tự động rollback database migration. Nếu schema mới đã nhận dữ liệu không tương thích, quay lại image cũ có thể khiến ứng dụng cũ không đọc được dữ liệu. Cần có migration rollback hoặc forward-fix được thiết kế và kiểm thử riêng.

## 12. Quản lý cấu hình, secret và artifact

Một release không chỉ có container image. Nó còn có:

- ConfigMap hoặc application configuration.
- Secret và identity binding.
- Environment variable.
- Service account và permission.
- Network policy và service routing.
- Database migration version.
- Feature flag.
- Resource request/limit và autoscaling policy.

Nên version hóa cấu hình theo release hoặc quản lý thay đổi config bằng quy trình riêng có thể audit. Không sửa trực tiếp nội dung một ConfigMap đang dùng mà không ghi nhận; Pod có thể không nhận thay đổi hoặc các replica nhận cấu hình ở thời điểm khác nhau.

Dùng image digest để bảo đảm mọi replica chạy đúng cùng artifact. Không dùng tag mutable như latest cho release production nếu không có cơ chế pin digest. Giữ image cũ trong registry đủ lâu cho rollback và tuân thủ chính sách vulnerability scanning.

## 13. Rollback trên Kubernetes

Nếu rollout tạo ra regression, có thể xem lịch sử và quay lại revision trước:

~~~bash
# Xem lịch sử
kubectl rollout history deployment/checkout-api

# Xem trạng thái rollout
kubectl rollout status deployment/checkout-api

# Quay lại revision trước
kubectl rollout undo deployment/checkout-api

# Quay lại revision cụ thể
kubectl rollout undo deployment/checkout-api --to-revision=3

# Xác minh phiên bản và trạng thái Pod
kubectl get deployment checkout-api -o wide
kubectl get rs -l app=checkout-api
kubectl get pods -l app=checkout-api -o wide
~~~

Lệnh rollout undo cập nhật Pod template của Deployment về revision trước theo lịch sử còn lưu. Nó không khôi phục database, message, secret ngoài cluster, dữ liệu object storage hoặc side effect đã phát sinh. Nếu lịch sử revision đã bị dọn hoặc release được quản lý bởi GitOps, cần dùng quy trình rollback phù hợp với nguồn khai báo chuẩn.

### 13.1. Rollback trong GitOps

Nếu Git là nguồn cấu hình chuẩn, thay đổi trực tiếp bằng kubectl rollout undo có thể bị GitOps controller reconcile trở lại phiên bản đang khai báo trong repository. Khi đó, rollback nên được thực hiện bằng cách revert commit hoặc chọn lại manifest/image digest ổn định trong Git, rồi để controller đồng bộ.

Cần xác định một nguồn điều khiển rollout. Tránh để CI/CD, GitOps và thao tác thủ công cùng thay đổi Deployment mà không có quy ước ownership.

## 14. Quy trình rollback có kiểm soát

Khi quyết định rollback:

1. Dừng tăng tỷ lệ traffic tới phiên bản mới.
2. Nếu dùng canary, đưa weight về 0 hoặc chuyển routing về stable.
3. Nếu dùng rolling update, dừng rollout theo cơ chế release controller và khôi phục Pod template ổn định.
4. Xác minh replica cũ đủ capacity và readiness.
5. Kiểm tra schema/database compatibility trước khi chuyển toàn bộ traffic.
6. Theo dõi request đang chạy, queue và transaction.
7. Xác minh error rate, latency và business metric đã trở về baseline.
8. Giữ lại log, trace, image digest và release metadata để điều tra.
9. Ghi nhận nguyên nhân, phạm vi ảnh hưởng và bước khắc phục.
10. Chỉ phát hành lại sau khi có bản sửa và kiểm thử cần thiết.

Nếu phiên bản mới đã thực hiện migration phá vỡ tương thích hoặc tạo side effect không thể đảo ngược, rollback đơn thuần có thể làm tình hình xấu hơn. Khi đó, có thể cần roll forward bằng bản sửa tương thích hoặc chạy quy trình phục hồi dữ liệu riêng.

## 15. Xử lý traffic đang mở và kết nối dài

Load balancer thường chọn backend ở thời điểm thiết lập connection hoặc request tùy loại dịch vụ. Khi thay phiên bản:

- HTTP keep-alive có thể giữ connection tới backend cũ.
- HTTP/2 có thể multiplex nhiều request trên một connection.
- WebSocket và gRPC streaming có thể tồn tại lâu hơn thời gian rollout.
- TCP session không tự chuyển sang container mới khi backend cũ bị xóa.

Ứng dụng cần có drain deadline, thông báo đóng kết nối và hỗ trợ client reconnect/resume nếu phù hợp. Với streaming hoặc WebSocket, có thể cần thời gian overlap dài hơn request HTTP ngắn. Đặt termination grace period theo hành vi thực tế và timeout của gateway.

Với worker queue, chỉ acknowledge message sau khi kết quả được ghi bền vững. Nếu dừng giữa job, checkpoint hoặc requeue theo semantics của broker; thiết kế idempotency để xử lý lại an toàn.

## 16. Rollout với workload stateful

Deployment rolling update phù hợp hơn với ứng dụng stateless. Với StatefulSet, database, broker hoặc workload gắn volume:

- Xác định thứ tự cập nhật và quorum requirement.
- Kiểm tra leader/primary và replica health.
- Kiểm tra version compatibility của protocol và on-disk format.
- Xác minh backup và restore trước thay đổi rủi ro.
- Theo dõi replication lag và khả năng failover.
- Không cập nhật đồng thời quá nhiều thành viên của quorum.
- Kiểm tra volume attachment, filesystem và storage class.
- Có quy trình downgrade được vendor hỗ trợ; một số phần mềm không hỗ trợ downgrade data format.

Không nên dùng một manifest rolling update chung cho mọi loại container. Database và distributed system cần runbook nâng cấp theo từng sản phẩm.

## 17. Ví dụ pipeline phát hành có canary và rollback

Một pipeline tham khảo:

~~~mermaid
flowchart TD
    A[Build image] --> B[Scan và test image]
    B --> C[Push image, lưu digest]
    C --> D[Deploy canary]
    D --> E[Readiness và smoke test]
    E --> F[Chuyển 5% traffic]
    F --> G[Đánh giá SLI/SLO]
    G --> H{Đạt ngưỡng?}
    H -- Không --> I[Weight về 0 và rollback]
    H -- Có --> J[Tăng traffic theo từng bước]
    J --> K{Đạt 100% và ổn định?}
    K -- Không --> I
    K -- Có --> L[Promote release]
    L --> M[Giữ revision cũ trong rollback window]
~~~

Các bước nên lưu metadata: commit SHA, image digest, config version, database migration ID, canary weight, thời điểm bắt đầu/kết thúc và kết quả đánh giá. Điều này giúp tái hiện quyết định và xác định chính xác release đang chạy.

### 17.1. Ví dụ policy phát hành

| Điều kiện | Hành động |
|---|---|
| Image scan hoặc test bắt buộc thất bại | Không deploy |
| Canary không qua readiness/smoke test | Dừng rollout |
| Error rate vượt ngưỡng liên tiếp | Đưa traffic về stable |
| p99 vượt ngưỡng trong thời gian quan sát | Dừng tăng weight, điều tra |
| Có lỗi data integrity | Rollback/incident response ngay theo runbook |
| SLO ổn định qua các bước | Tăng weight |
| 100% traffic và đủ thời gian quan sát | Đánh dấu release hoàn tất |

Ngưỡng cần dựa trên SLO và baseline của dịch vụ. Tránh rollback tự động do một spike ngắn hoặc probe lỗi đơn lẻ; dùng cửa sổ quan sát, số mẫu tối thiểu và nhiều tín hiệu độc lập.

## 18. Những lỗi thường gặp khi cập nhật container

**Readiness báo thành công quá sớm.** Traffic đi vào Pod trước khi ứng dụng sẵn sàng. Hãy kiểm tra dependency thiết yếu và startup state.

**Dùng tag mutable.** Replica có thể pull image khác nhau ở những thời điểm khác nhau. Pin digest cho mỗi release.

**maxSurge vượt capacity cluster.** Pod mới ở Pending khiến rollout đứng lại. Kiểm tra quota, node capacity, affinity và autoscaler.

**maxUnavailable quá cao.** Capacity phục vụ giảm dưới mức cần thiết. Tính toán theo replica, peak load và failure scenario.

**Liveness phụ thuộc database.** Database chập chờn khiến toàn bộ Pod restart liên tục. Phân biệt liveness với readiness và dependency health.

**Không drain kết nối dài.** Request hoặc stream bị ngắt giữa chừng. Dùng graceful shutdown, deadline và client reconnect.

**Canary quá ít mẫu.** Một tỷ lệ nhỏ traffic trong thời gian ngắn không đủ phát hiện lỗi hiếm. Tăng thời gian hoặc mẫu theo traffic thực tế.

**So sánh canary và stable ở thời điểm khác nhau.** Biến động tải hoặc dependency có thể làm kết luận sai. So sánh song song và chuẩn hóa workload.

**Rollback image nhưng quên schema.** Phiên bản cũ không tương thích dữ liệu mới. Dùng expand-and-contract và kiểm thử rollback.

**GitOps ghi đè rollback thủ công.** Controller đưa cấu hình cũ trở lại. Thực hiện rollback qua nguồn khai báo chuẩn.

**Xóa ReplicaSet/image cũ quá sớm.** Mất khả năng quay lại nhanh. Giữ revision và artifact theo rollback window.

## 19. Checklist trước, trong và sau rollout

### Trước rollout

- [ ] Image đã được test, scan và pin bằng digest.
- [ ] Release có commit SHA, config version và owner rõ ràng.
- [ ] Readiness, liveness và startup probe đã được kiểm thử.
- [ ] maxSurge, maxUnavailable, capacity và quota đã được tính.
- [ ] Phiên bản cũ/mới tương thích API, database và message schema.
- [ ] Có kế hoạch migration expand-and-contract.
- [ ] Graceful shutdown, drain và termination grace period phù hợp.
- [ ] Có baseline metrics, logs, traces và SLO để so sánh.
- [ ] Có revision/image cũ và runbook rollback.

### Trong rollout

- [ ] Theo dõi rollout status và Pod events.
- [ ] Chỉ gửi traffic tới replica Ready.
- [ ] Theo dõi error rate, p95/p99, throughput và resource saturation.
- [ ] Canary weight tăng theo bước và đủ mẫu.
- [ ] Theo dõi database, queue và dependency metrics.
- [ ] Dừng tăng traffic nếu vượt ngưỡng.
- [ ] Không xóa phiên bản cũ trước khi hết rollback window.

### Sau rollout

- [ ] 100% traffic tới phiên bản mới và đủ thời gian quan sát.
- [ ] Business metric và data integrity đạt.
- [ ] Không có backlog hoặc retry bất thường.
- [ ] Release metadata và kết quả được lưu.
- [ ] Rollback artifact và revision được giữ theo chính sách.
- [ ] Có post-release review nếu xảy ra regression hoặc rollback.

## 20. Kết luận

Rolling update thay replica theo từng bước để duy trì capacity; traffic splitting kiểm soát tỷ lệ request tới stable và phiên bản mới; rollback đưa dịch vụ về release ổn định khi rollout không đạt yêu cầu. Để phối hợp ba cơ chế, cần pin image bằng digest, dùng readiness/startup probe đúng, tính maxSurge và maxUnavailable, drain kết nối, theo dõi SLO và bảo đảm phiên bản cũ/mới tương thích dữ liệu.

Chọn rolling update cho thay đổi tương thích và quy trình đơn giản; dùng canary khi cần kiểm chứng dưới traffic thật; dùng blue-green khi cần kiểm thử nhóm mới độc lập và có capacity dự phòng. Rollback phải bao gồm routing, application artifact, cấu hình và kế hoạch dữ liệu. Một lần phát hành chỉ hoàn tất khi phiên bản mới phục vụ ổn định, nghiệp vụ đúng và có thể truy vết đầy đủ.
