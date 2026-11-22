# Nhân bản dịch vụ theo nhu cầu tải riêng trong Microservices

## Mục tiêu học tập

Sau bài này, người học có thể giải thích vì sao microservices cho phép mở rộng từng dịch vụ độc lập; phân biệt tăng tài nguyên cho một instance với nhân bản nhiều instance; xác định nhu cầu mở rộng dựa trên lưu lượng, độ trễ, mức sử dụng tài nguyên và hàng đợi; áp dụng các điều kiện về trạng thái, cân bằng tải, database và concurrency; thiết kế autoscaling bằng Kubernetes HPA hoặc cơ chế dựa trên sự kiện; và xác nhận rằng việc tăng replica thực sự cải thiện năng lực phục vụ, độ tin cậy và chi phí.

Bài học tập trung vào **mở rộng ngang từng dịch vụ theo nhu cầu tải riêng** (independent horizontal scaling). Mục đích không phải tăng số pod càng nhiều càng tốt, mà là cấp năng lực cho đúng nơi đang gây nghẽn trong toàn bộ đường đi nghiệp vụ.

## 1. Vì sao nhu cầu tải giữa các microservice khác nhau?

Một hệ thống thương mại điện tử có thể gồm:

~~~text
                         Client / Mobile / Web
                                   |
                            API Gateway
                                   |
                 +-----------------+----------------+
                 |                 |                |
                 v                 v                v
          Catalog Service     Cart Service     Order Service
                 |                 |                |
                 v                 v                v
            Search DB          Cart Store      Order Database
                                   |                |
                                   |                +----> Event Broker
                                   |                         |
                                   |                   +-----+-----+
                                   |                   |           |
                                   |                   v           v
                                   |             Payment Service  Inventory Service
                                   |                   |           |
                                   +-------------------+-----------+
~~~

Vào giờ cao điểm, người dùng xem danh sách sản phẩm hàng nghìn lần mỗi giây nhưng chỉ một phần nhỏ tiến hành đặt hàng. Tải Catalog/Search chủ yếu là đọc, tải Cart liên quan các thao tác ngắn với session, tải Order gồm validation và transaction, còn Payment bị giới hạn bởi tốc độ phản hồi và hạn mức của nhà cung cấp bên ngoài.

Nếu mọi thành phần nằm trong một tiến trình monolith duy nhất, phương án tăng replica của toàn ứng dụng có thể đồng thời nhân bản những phần không hề cần thêm năng lực. Với microservices được triển khai độc lập, ta có thể tăng số instance của Catalog mà giữ nguyên số instance Payment. Tuy nhiên, cần cân đối giữa số lượng thành phần vận hành và lợi ích thật: tách dịch vụ thành nhiều đơn vị chỉ có ý nghĩa khi ranh giới nghiệp vụ và quyền sở hữu dữ liệu đủ rõ.

### Ví dụ phân bổ năng lực

| Dịch vụ | Đặc tính tải | Dấu hiệu căng thẳng | Quyết định minh họa |
| --- | --- | --- | --- |
| Catalog API | Rất nhiều truy vấn đọc, có thể cache | p95 tăng, CPU cao, cache miss | Tăng từ 3 lên 9 replica, xem xét cache |
| Order API | Ít request hơn nhưng transaction quan trọng | Đợi connection, lock DB, lỗi timeout | Chỉ tăng từ 3 lên 4 nếu DB còn dư năng lực |
| Payment adapter | Nhiều thời gian chờ API bên ngoài | Rate limit/429, latency nhà cung cấp | Giới hạn concurrency, queue, không tăng pod vô hạn |
| Inventory consumer | Xử lý event bất đồng bộ | Consumer lag tăng | Tăng worker tới giới hạn partition |
| Reporting worker | Batch theo giờ/ngày | Backlog lớn trong một khung giờ | Scale theo độ dài queue hoặc lịch xử lý |

Những con số là giả định để minh họa cách quyết định, không phải cấu hình khuyến nghị mặc định. Mỗi nhóm phải đo tải và khả năng chịu tải của chính dịch vụ mình.

## 2. Phân biệt mở rộng dọc và mở rộng ngang

**Vertical scaling (scale up)** tăng CPU/RAM/I/O cho một instance. Ví dụ nâng tài nguyên một pod từ 500m CPU và 512 MiB RAM lên 2 CPU và 2 GiB RAM. Cách này đơn giản với ứng dụng không hỗ trợ nhiều instance, nhưng vẫn bị giới hạn bởi kích thước node, khả năng chịu lỗi của một tiến trình và chi phí tài nguyên lớn.

**Horizontal scaling (scale out)** tạo thêm các instance cùng loại và phân phối request/công việc giữa chúng. Ví dụ Order API từ 2 replica lên 6 replica, mỗi replica có cấu hình tài nguyên tương đương.

~~~text
Trước:
                   Load Balancer
                         |
                     Order #1
                         |
                     Order DB

Sau:
                   Load Balancer
                  /      |      \
            Order #1  Order #2  Order #3
                  \      |      /
                       Order DB
~~~

Mở rộng ngang đem lại tính linh hoạt và khả năng chịu lỗi instance, nhưng chỉ hoạt động hiệu quả khi:
- Các instance có thể phục vụ công việc tương đương và không phụ thuộc bộ nhớ cục bộ của một instance khác.
- Có cơ chế điều phối request hoặc phân chia công việc.
- Dịch vụ phía sau (database, cache, broker, API khác) còn đủ năng lực.
- Dữ liệu và tác động nghiệp vụ vẫn đúng khi nhiều instance chạy đồng thời.
- Quá trình thêm/bớt instance không làm mất request hoặc công việc đang xử lý.

**Independent scaling** nghĩa là mỗi dịch vụ có chính sách replica, resource request/limit, tín hiệu autoscaling và ngân sách riêng. Không có nghĩa các dịch vụ hoàn toàn độc lập về hiệu năng: chúng vẫn tạo tải qua các lời gọi và tài nguyên dùng chung.

## 3. Xác định điểm nghẽn trước khi nhân bản

Tăng replica chỉ cải thiện phần công việc có thể thực thi song song. Cần phân biệt ít nhất bốn dạng điểm nghẽn:

1. **CPU-bound:** Nén dữ liệu, serialization, mã hóa, tính toán; CPU bão hòa và request xếp hàng trong tiến trình. Thêm replica có thể tăng throughput nếu cụm còn CPU.
2. **Memory-bound:** Giữ quá nhiều object, bộ nhớ cache, heap hoặc tác vụ lớn; lỗi OOM, GC pause và p99 cao. Cần tối ưu bộ nhớ và kích cỡ instance trước hoặc cùng việc mở rộng.
3. **I/O-bound:** Chờ database, Redis, object storage hoặc API ngoài. CPU thấp nhưng request vẫn chậm. Thêm replica có thể làm nghẽn dependency nặng hơn.
4. **Contention/serialization-bound:** Lock, transaction, queue partition, khóa nghiệp vụ hoặc tài nguyên chỉ một worker có thể giữ. Thêm instance không vượt được giới hạn tuần tự này.

Ví dụ Order API tăng từ 4 lên 16 pod nhưng mọi request vẫn tranh một khóa ghi trong database. Tổng throughput có thể tăng rất ít, trong khi số kết nối và mức lock contention tăng mạnh.

**Không đánh giá sức khỏe chỉ bằng CPU.** Một service chờ Payment API liên tục có thể CPU thấp, request p99 cao và thread pool cạn; autoscaling theo CPU sẽ phản ứng kém. Ngược lại, CPU cao vì batch không quan trọng cũng chưa chắc là lý do cần tăng replica trên một API phục vụ ít traffic.

Câu hỏi đầu tiên trước khi scale: *phần nào đang đạt giới hạn, giới hạn có thể chia song song được không, và khi tăng replica thì áp lực sẽ chuyển sang đâu?*

## 4. Hiểu tải, throughput, concurrency và latency

Một số khái niệm cần phân biệt:

- **Arrival rate (λ):** số request hoặc work item đến mỗi giây.
- **Throughput:** số request/work item hoàn thành mỗi giây.
- **Latency:** thời gian hoàn thành một request, thường đo p50, p95 và p99.
- **Concurrency:** số request/work item đang xử lý cùng thời điểm.
- **Utilization:** tỷ lệ sử dụng tài nguyên như CPU, connection pool, worker thread.
- **Backlog:** số công việc đến nhưng chưa được xử lý.

Theo định luật Little, trong hệ thống tương đối ổn định: **L = λ × W**, trong đó L là số công việc trung bình đang nằm trong hệ thống, λ là tốc độ đến và W là thời gian nằm trong hệ thống.

Ví dụ ở tốc độ 200 request/giây, nếu thời gian phản hồi trung bình 0,2 giây thì trung bình có khoảng 40 request đang trong hệ thống. Nếu do DB nghẽn mà thời gian tăng lên 2 giây, số request đồng thời có thể lên khoảng 400 dù lưu lượng đầu vào không đổi. Điều này gây áp lực lên thread, kết nối và bộ nhớ.

### Ước lượng replica khởi đầu

Giả sử qua load test, một replica Catalog xử lý ổn định 40 request/giây **trong khi vẫn đạt SLO độ trễ và lỗi**. Đỉnh dự đoán 200 request/giây. Ước lượng tối thiểu:

~~~text
N = ceil(peak_requests_per_second / sustainable_rps_per_replica)
  = ceil(200 / 40)
  = 5 replica
~~~

Năm replica là điểm bắt đầu tính toán, chưa bao gồm dự phòng cho node failure, mất cân bằng, burst, rolling deploy, cache miss hoặc thời gian khởi tạo pod. Có thể thiết kế mức dự phòng cao hơn sau khi đo và kiểm thử.

Tránh dùng tỷ lệ nhân bản tuyến tính một cách máy móc. Khi tài nguyên hoặc dependency tiến gần bão hòa, latency đuôi thường tăng nhanh, nên throughput đạt SLO có thể thấp hơn đáng kể so với throughput tối đa đo bằng mọi giá.

## 5. Stateless application: điều kiện quan trọng để scale ngang

Một API stateless không phụ thuộc việc request tiếp theo của cùng người dùng phải quay về đúng pod trước đó. Trạng thái cần được lưu ở nơi có thể truy cập từ các instance, ví dụ database, cache phân tán hoặc token có quy tắc bảo mật phù hợp.

**Những thứ dễ làm ứng dụng trở nên phụ thuộc instance:**
- HTTP session chỉ lưu trong RAM cục bộ.
- File upload nằm trên ổ đĩa của một pod.
- Bảng “đã xử lý request” tồn tại trong map cục bộ.
- Job được giữ trong một queue in-memory không durable.
- WebSocket connection gắn chặt với instance nhưng không có cơ chế định tuyến/presence phù hợp.
- Local cache được xem như nguồn dữ liệu chuẩn mà không có cơ chế invalidation.

### Mô hình stateless cho API

~~~text
                       Ingress / Service LB
                        /       |        \
                     Pod A    Pod B      Pod C
                        \       |        /
                       Shared DB / Redis / Object Store
~~~

Mỗi pod có thể nhận bất kỳ request hợp lệ nào. Với JWT, cần kiểm tra chữ ký, thời hạn, quyền và cơ chế thu hồi/đổi khóa theo chính sách; không mặc định JWT tự giải quyết mọi bài toán session. Với cache cục bộ, vẫn có thể dùng làm tầng tối ưu nhưng phải chấp nhận eventual consistency hoặc có chiến lược đồng bộ/invalidation.

Nếu ứng dụng cần sticky session, vẫn có thể scale ngang trong một số trường hợp, nhưng cân bằng tải, failover và scale-down phức tạp hơn. Nên nhận diện sự phụ thuộc này một cách chủ động.

## 6. Phân phối traffic và readiness khi thêm replica

Khi scale Order API từ 2 lên 8 replica, một load balancer hoặc Kubernetes Service phải phân phối request đến các endpoint khỏe mạnh. Tuy nhiên **Pod Running không có nghĩa đã sẵn sàng phục vụ**.

Các điểm cần thiết:
1. **Readiness probe:** chỉ đưa pod vào danh sách nhận traffic sau khi ứng dụng đã khởi tạo và có thể thực hiện chức năng cốt lõi.
2. **Startup probe (khi phù hợp):** cho ứng dụng khởi động chậm cơ hội hoàn tất mà không bị liveness xử lý như một pod treo.
3. **Liveness probe:** phát hiện tiến trình cần được khởi động lại, không nên kiểm tra một dependency tạm thời lỗi theo cách khiến tất cả pod cùng restart.
4. **Graceful shutdown:** khi scale down, ngừng nhận request mới, xử lý request đang chạy trong thời gian hữu hạn, đóng tài nguyên và giải phóng công việc nền an toàn.
5. **Connection draining:** phối hợp ingress/load balancer, termination grace period và ứng dụng để hạn chế request bị cắt ngang.

Readiness không nên yêu cầu mọi hệ thống ngoài luôn khỏe ở mọi thời điểm; nếu dependency dùng chung có sự cố và toàn bộ replica đồng loạt NotReady, có thể tạo outage lớn hơn. Probe cần phản ánh điều kiện ứng dụng thực sự có thể phục vụ theo thiết kế.

Một instance mới cũng cần thời gian **warm-up**: tạo connection pool, làm nóng JIT/cache, load schema hoặc secret. Scaling phản ứng quá muộn có thể vẫn không cứu được burst ngắn.

## 7. Kubernetes Deployment và resource requests/limits

Ví dụ định nghĩa Deployment cho Catalog API:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: catalog-api
spec:
  replicas: 3
  selector:
    matchLabels:
      app: catalog-api
  template:
    metadata:
      labels:
        app: catalog-api
    spec:
      terminationGracePeriodSeconds: 45
      containers:
        - name: catalog
          image: registry.example.com/catalog-api:1.0.0
          ports:
            - containerPort: 8080
          resources:
            requests:
              cpu: "300m"
              memory: "512Mi"
            limits:
              cpu: "1000m"
              memory: "1Gi"
          readinessProbe:
            httpGet:
              path: /actuator/health/readiness
              port: 8080
            initialDelaySeconds: 5
            periodSeconds: 5
          livenessProbe:
            httpGet:
              path: /actuator/health/liveness
              port: 8080
            initialDelaySeconds: 20
            periodSeconds: 10
~~~

YAML chỉ là ví dụ; endpoint readiness/liveness cần được Spring Boot Actuator hoặc ứng dụng cung cấp theo cấu hình thực. Tránh dùng một URI health chưa được triển khai.

**requests.cpu/memory** thể hiện nhu cầu tài nguyên để scheduler đặt pod lên node. **limits.cpu** có thể khiến container bị throttling khi đạt ngưỡng, làm tăng độ trễ dù nhu cầu xử lý tiếp tục tăng. **limits.memory** có thể gây OOM kill nếu tiến trình dùng vượt mức. Cần chọn dựa trên đo lường, đặc biệt với heap/off-heap của JVM.

Khi HPA quản lý số replica, không nên dựa vào một giá trị replicas khai báo thủ công liên tục ghi đè quyết định của HPA qua những lần apply/triển khai. Phải quy định thành phần nào sở hữu trường scale trong quy trình GitOps/deployment.

## 8. Horizontal Pod Autoscaler (HPA) theo CPU

HPA là controller điều chỉnh số replica của workload dựa trên metric. Một cấu hình minh họa:

~~~yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: catalog-api
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: catalog-api
  minReplicas: 3
  maxReplicas: 15
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 70
  behavior:
    scaleUp:
      stabilizationWindowSeconds: 0
      policies:
        - type: Pods
          value: 4
          periodSeconds: 60
        - type: Percent
          value: 100
          periodSeconds: 60
      selectPolicy: Max
    scaleDown:
      stabilizationWindowSeconds: 300
      policies:
        - type: Percent
          value: 20
          periodSeconds: 60
~~~

Ở đây HPA nhằm giữ **CPU trung bình khoảng 70% so với CPU request của container**, không phải 70% CPU limit hay 70% CPU của toàn node. Ví dụ request 300m CPU thì ngưỡng mục tiêu tương ứng khoảng 210m CPU sử dụng trung bình mỗi pod trong cách đo này.

HPA ước tính số replica mong muốn theo tỷ lệ giữa metric hiện tại và metric mục tiêu, có xử lý tolerance, trạng thái pod, metric thiếu và chính sách ổn định. Với giả định đơn giản:

~~~text
desired_replicas ≈ ceil(current_replicas × current_metric / target_metric)
~~~

Nếu có 4 replica, CPU trung bình 84% theo request và mục tiêu 70%, công thức lý tưởng cho ra ceil(4 × 84/70) = 5 replica. Kết quả controller thực tế còn phụ thuộc nhịp thu thập metric, readiness, policy, giới hạn min/max và trạng thái workload.

### Điều kiện để HPA CPU hoạt động có ý nghĩa

- Đặt CPU request hợp lý cho container; metric CPU utilization dựa trên request.
- Có pipeline cung cấp metric, ví dụ metrics-server cho resource metrics trong Kubernetes.
- Hạn chế dao động tăng/giảm liên tục bằng stabilization window và scaling policies.
- Không chọn maxReplicas vượt năng lực thực tế của database và các dependency.
- Thử dưới tải thật để xác định CPU có tương quan với SLO cần bảo vệ hay không.
- Phải có đủ node capacity hoặc Cluster Autoscaler/cơ chế bổ sung node; nếu không, pod mới sẽ Pending.

CPU HPA thích hợp với nhiều API CPU-bound, nhưng không phù hợp làm tín hiệu duy nhất cho tất cả workload.

## 9. Chọn metric riêng cho từng dịch vụ

Independent scaling nên gắn với **bản chất công việc**.

| Dịch vụ | Metric có thể dùng | Lý do |
| --- | --- | --- |
| Catalog API | CPU, request rate mỗi replica, p95 latency | Request đọc nhiều; cần phát hiện áp lực khi cache miss |
| Image processing | Số task đang chờ, CPU, thời gian mỗi task | Công việc CPU-intensive hoặc xử lý theo batch |
| Checkout/Order API | RPS, in-flight request, p95 latency, DB wait | CPU thấp không loại trừ nghẽn kết nối/transaction |
| Kafka consumer | Consumer lag, tốc độ xử lý, tuổi message | Tải xuất hiện ở broker, không phải HTTP RPS |
| Email/notification worker | Queue length, tuổi message, provider quota | Cần đẩy backlog nhưng vẫn giữ giới hạn bên ngoài |
| Payment adapter | In-flight call, timeout/429 và quota | Hạn chế tăng lưu lượng khi provider đã chạm giới hạn |

**p95 latency** là tín hiệu chất lượng quan trọng nhưng dùng trực tiếp làm trigger scaling cần cân nhắc: độ trễ tăng do database, lock hoặc provider thì tăng replica có thể làm tệ hơn. Nên kết hợp latency với metric cho thấy replica là tài nguyên đang thiếu (CPU, concurrency, request queue).

Đối với metric custom hoặc external, HPA cần adapter cung cấp metric đúng namespace/nhãn và thông tin cần thiết cho controller. Một service không thể scale an toàn nếu metric bị cập nhật chậm hoặc có độ trễ lớn so với thời gian khởi động instance.

### Một ví dụ chọn mục tiêu theo concurrency

Giả sử một instance có thể xử lý ổn định tối đa 50 request đồng thời mà vẫn đáp ứng p95 latency. Nếu toàn dịch vụ có 250 request đồng thời:

~~~text
desired_replicas ≈ ceil(250 / 50) = 5
~~~

Tuy vậy, 50 không phải con số có thể lấy từ cấu hình maxThreads. Nó cần được xác nhận qua load test với CPU, heap, DB connection, timeout và tỷ lệ lỗi thực tế. Nếu các request bị kẹt ở hệ thống ngoài, thêm replica chỉ tăng số lời gọi đang đợi.

## 10. Scale theo hàng đợi và sự kiện

Một microservice tiêu thụ message cần được scale theo tốc độ đến và tốc độ xử lý, không chỉ CPU.

~~~text
Order Service
      |
      v
 Message Broker --------- backlog = 18.000 events
      |
  +---+----+---------+
  |        |         |
Worker A Worker B  Worker C
      |
Inventory Database
~~~

Nếu broker nhận 1.000 event/giây nhưng tổng worker chỉ xử lý được 700 event/giây, backlog tăng 300 event/giây. Trong 10 phút có thể tăng thêm 180.000 event. Tăng số worker chỉ giúp khi broker cho phép chia việc và database chịu được tốc độ cập nhật mới.

**Metric nên xét cùng nhau:**
- Queue depth và tuổi message lâu nhất.
- Arrival rate và processing/ack rate.
- Consumer lag theo partition và consumer group.
- Retry/dead-letter rate.
- Độ trễ xử lý một message, mức sử dụng tài nguyên và sức khỏe database.

KEDA có thể kết hợp với Kubernetes để scale workload theo queue length, Kafka lag hoặc các trigger event-driven khác. Cần cấu hình scaler, xác thực, ngưỡng và giới hạn min/max phù hợp. Với workload có yêu cầu sẵn sàng cao, cân nhắc minReplicaCount lớn hơn 0 để tránh cold start; scale-to-zero phải phù hợp loại công việc và cơ chế kích hoạt.

### Giới hạn do partition

Kafka phân phối các partition trong một consumer group. Nếu một topic có 8 partition, 20 consumer trong cùng một group không có nghĩa 20 consumer đều xử lý dữ liệu song song: tối đa 8 consumer có thể được gán partition đang hoạt động tại cùng một thời điểm cho topic đó, tùy phân bố và mô hình subscribe.

Muốn tăng throughput có thể cần tăng số partition, tối ưu xử lý từng message, hoặc giảm công việc đồng bộ bên trong consumer. Nhưng tăng partition có thể thay đổi đặc tính thứ tự theo key, phân phối dữ liệu và hành vi consumer, nên phải đánh giá hợp đồng nghiệp vụ.

### Autoscaling theo backlog cần thời hạn mục tiêu

Giả sử cần giải quyết thêm 60.000 message trong 5 phút, một worker xử lý an toàn 50 message/giây, và tạm bỏ qua lưu lượng mới:

~~~text
Tốc độ cần xử lý thêm = 60.000 / 300 = 200 message/giây
Số worker lý thuyết = ceil(200 / 50) = 4
~~~

Nếu đồng thời còn 100 message/giây mới đến, tổng năng lực yêu cầu phải cộng lưu lượng mới. Công thức trên cũng chưa tính rebalance, thời gian khởi động, retry và giới hạn downstream; cần dự phòng khi kiểm thử.

## 11. Database có thể trở thành giới hạn khi scale API

Database thường là điểm nghẽn khiến việc nhân bản API không tạo thêm throughput.

Giả sử mỗi pod Order có tối đa 20 kết nối đến PostgreSQL, và scale từ 4 lên 20 pod:

~~~text
4 pod × 20 connection = 80 kết nối tiềm năng
20 pod × 20 connection = 400 kết nối tiềm năng
~~~

Nếu database chỉ đủ tài nguyên xử lý vài chục đến một trăm kết nối hoạt động hiệu quả, 400 kết nối không cải thiện tốc độ; chúng có thể tăng context switching, memory, lock contention và timeout.

Giải pháp tùy nguyên nhân:
- Đo connection pool wait, số connection hoạt động, query latency, lock wait và database CPU/IO.
- Tính tổng connection tối đa giữa các replica và các service dùng chung DB.
- Tối ưu query, index, transaction và cách phân trang trước khi tăng pod.
- Dùng connection pooling/proxy như PgBouncer khi phù hợp với transaction/session semantics.
- Với luồng đọc nhiều, cân nhắc cache, read replica hoặc CQRS/read model nếu bài toán cho phép consistency tương ứng.
- Với ghi dữ liệu lớn, cân nhắc batch, partitioning hoặc chia ranh giới dữ liệu đúng nghiệp vụ; không hứa rằng thêm read replica sẽ cải thiện write throughput.
- Khi DB đạt giới hạn, điều chỉnh tốc độ nhận request hoặc giới hạn số tác vụ đồng thời thay vì tiếp tục tăng worker.

**Database per service** là nguyên tắc quản lý sở hữu dữ liệu, không có nghĩa mỗi service đương nhiên nhận được một database vô hạn năng lực. Có thể dùng chung hạ tầng nhưng cần đo giới hạn vật lý và quota riêng.

## 12. Hiệu ứng lan truyền qua chuỗi lời gọi

Giả sử mỗi request Checkout gọi 1 lần Pricing, 1 lần Inventory và 1 lần Payment. Scale Checkout lên 10 lần mà không xét các service phía sau có thể tăng đột ngột tổng số request đến chúng.

~~~text
Checkout (2 -> 12 replicas)
          |
     +----+-----+
     |          |
     v          v
Inventory     Payment provider
(giữ 2 pod)   (quota 100 req/s)
~~~

Nếu throughput Checkout thực sự tăng, mức tải xuống các dependency cũng tăng. Hệ thống có thể chuyển từ nghẽn CPU Checkout sang nghẽn Inventory DB hoặc rate limit Payment; p99 toàn hành trình không cải thiện.

Nên có:
1. **Timeout hữu hạn** theo ngân sách độ trễ của request end-to-end.
2. **Bounded concurrency/bulkhead** để giới hạn lời gọi đồng thời tới dependency.
3. **Backpressure/queue có giới hạn** để hệ thống phản ứng có kiểm soát khi tải đến vượt năng lực xử lý.
4. **Rate limiting** theo tenant, nguồn gọi hoặc giới hạn thực tế của nhà cung cấp.
5. **Retry có backoff, jitter và giới hạn**, đặc biệt với HTTP 429/503; tránh bão retry.
6. **Circuit breaker/fallback** khi phù hợp nghiệp vụ, không dùng để che các lỗi dữ liệu cần khắc phục.
7. **Idempotency** cho thao tác ghi/thanh toán vì timeout và retry có thể khiến một yêu cầu được xử lý lại.

Autoscaling và bảo vệ dependency bổ sung cho nhau. Một hệ thống không thể được làm an toàn chỉ bằng việc tăng maxReplicas.

## 13. Chọn scale theo service, không theo một công thức chung

Có thể định nghĩa chính sách cho từng deployment:

| Workload | minReplicas | maxReplicas | Trigger chính | Ràng buộc |
| --- | ---: | ---: | --- | --- |
| Catalog API | 3 | 15 | CPU/RPS | Cache và search backend còn năng lực |
| Order API | 3 | 8 | Concurrency hoặc CPU đã được hiệu chuẩn | Connection pool và transaction |
| Payment adapter | 2 | 4 | Queue lag kết hợp quota | Nhà cung cấp chỉ cho tốc độ giới hạn |
| Inventory worker | 2 | 12 | Kafka lag | Số partition, khả năng ghi DB |
| Reporting worker | 0 hoặc 1 | 10 | Pending work/queue depth | Tác vụ idempotent và thời gian cold start |

Bảng là ví dụ giải thích, không phải giá trị vận hành đã được chứng minh. Đôi khi minReplicas=1 là đủ cho ứng dụng thử nghiệm; với dịch vụ yêu cầu tính sẵn sàng cao, minReplicas≥2 hoặc lớn hơn còn phụ thuộc failure domain, pod distribution và SLO.

Đối với mỗi service, tài liệu vận hành nên nêu:
- SLO về độ trễ, tỉ lệ thành công, năng lực xử lý hoặc thời gian hoàn thành backlog.
- Điều kiện tăng/giảm, min/max và resource requests/limits.
- Giới hạn số connection, worker threads, request đang xử lý và rate tới dependency.
- Thời gian khởi động/cold start và kỳ vọng phản ứng trước burst.
- Ai sở hữu cảnh báo và có thể can thiệp thủ công.
- Chi phí và hệ quả khi scale ở mức tối đa.

Chính sách đủ tốt phải được đánh giá theo ảnh hưởng lên nghiệp vụ, không chỉ việc HPA có tạo thêm pod hay không.

## 14. Tự động tăng và giảm replica cần tránh dao động

Nếu metric dao động quanh ngưỡng, autoscaler có thể liên tục tạo và xóa pod (**thrashing**). Việc này làm tốn tài nguyên, tăng số connection mở/đóng, cache warm-up và thời gian GC/JIT.

Một số biện pháp:
- Đo metric bằng cửa sổ phù hợp để giảm nhiễu nhất thời mà vẫn phát hiện burst có ý nghĩa.
- Dùng stabilization window cho scale down, tránh rút replica quá sớm ngay khi tải giảm vài giây.
- Cho phép scale up nhanh hơn scale down trong hệ thống cần phản ứng nhanh với tăng tải.
- Chọn bước tăng/giảm hợp lý để tránh tạo quá nhiều pod trong một chu kỳ.
- Dự trữ minReplicas ở mức chấp nhận được cho tải nền.
- Kết hợp predictive/scheduled scaling nếu biết rõ đỉnh lưu lượng định kỳ, sau đó dùng metric thực để điều chỉnh.

**Phản ứng có trễ** là thuộc tính tự nhiên của autoscaling: phải thu thập metric, controller ra quyết định, scheduler bố trí pod, kéo image, khởi động JVM và vượt readiness. Vì vậy, một spike kéo dài 10 giây có thể kết thúc trước khi pod mới Ready. Hạn chế rủi ro bằng headroom, cache, queue/buffer, rate limiting hoặc pre-scale có kiểm soát.

## 15. Scale ngang và tính sẵn sàng

Tăng replica giúp giảm phụ thuộc vào một instance, nhưng chỉ khi chúng không cùng nằm trên một failure domain.

Ví dụ 6 replica trên cùng một node không bảo vệ được sự cố node. Với ứng dụng quan trọng, cân nhắc pod anti-affinity hoặc topology spread constraints để phân bổ giữa node/zone, kết hợp tài nguyên dự trữ để có thể phục hồi.

**PodDisruptionBudget (PDB)** có thể giới hạn số replica tự nguyện bị gián đoạn đồng thời trong những hoạt động hỗ trợ eviction, chẳng hạn bảo trì node. PDB không bảo đảm tránh mọi outage: node hỏng đột ngột, lỗi ứng dụng chung, DB lỗi, cấu hình sai hoặc pod không đủ resource vẫn có thể làm dịch vụ ngừng hoạt động.

Ngoài ra cần xét:
- Replica có thể cùng phụ thuộc một database hoặc Redis duy nhất; nhân bản API không tạo HA cho các dependency đó.
- Liveness/readiness sai có thể khiến toàn bộ replica bị loại khỏi load balancer.
- Rolling update phải giữ năng lực tối thiểu; cấu hình maxSurge/maxUnavailable cần cân bằng khả năng tiếp nhận tải và tài nguyên cluster.
- Scale-down phải tôn trọng request đang xử lý, consumer partition rebalance và task chưa commit.
- Một API stateless có thể an toàn khi bị scale-down, nhưng worker xử lý sự kiện phải hoàn tất hoặc chuyển giao công việc một cách có kiểm soát.

Independent scaling tạo thêm đòn bẩy vận hành; độ tin cậy đòi hỏi thiết kế failure domain và dependency tương ứng.

## 16. Scale worker mà không chạy trùng hiệu ứng nghiệp vụ

Với HTTP GET stateless, thêm replica thường tương đối đơn giản. Với worker xử lý event, cron job, thanh toán hoặc ghi dữ liệu, việc tăng instance đòi hỏi kiểm soát concurrency và idempotency.

Ví dụ, Inventory Service có 8 worker cùng nhận sự kiện OrderCreated. Broker có thể gửi lại cùng message sau lỗi hoặc retry. Nếu mỗi worker chỉ kiểm tra “đã xử lý chưa?” bằng SELECT, hai worker vẫn có thể cùng vượt qua kiểm tra trước khi ghi.

Có thể dùng định danh sự kiện/operation và ràng buộc duy nhất:

~~~sql
CREATE TABLE processed_event (
    event_id UUID PRIMARY KEY,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
~~~

Trong **cùng transaction** với cập nhật tồn kho, worker thử ghi event_id; nếu ràng buộc UNIQUE cho biết sự kiện đã xử lý, không tạo tác động thứ hai. Cách triển khai cụ thể phải bảo đảm transaction của processed_event và thay đổi tồn kho có chung phạm vi atomic; nếu có gọi hệ thống ngoài thì cần idempotency tương ứng ở đầu nhận.

Với cron job nằm trong mỗi pod API, scale từ 2 lên 10 replica có thể tạo 10 lần kích hoạt cùng lịch. Nên chuyển scheduler sang deployment riêng, dùng distributed lock/job store hoặc hệ thống điều phối như Kubernetes CronJob/Quartz theo yêu cầu. Dù có lock, vẫn cần thiết kế retry/lease và tính idempotent do tiến trình có thể chết hoặc lock hết hạn.

Một dịch vụ xử lý nghiệp vụ có thể tăng replica độc lập với số partition hoặc số khóa xử lý đồng thời, nhưng mỗi đơn vị dữ liệu xung đột phải có quy tắc tuần tự hoặc kiểm soát cạnh tranh rõ ràng.

## 17. Scale dữ liệu và cache

Khi một dịch vụ được nhân bản, những thay đổi về cache và đường truy cập dữ liệu dễ tạo ra hiệu ứng bất ngờ.

### Local cache trên mỗi pod

Nếu Catalog có 3 pod với local cache, mỗi pod giữ một phần dữ liệu nóng. Scale lên 15 pod làm tăng số bản cache phải warm up; request ban đầu có thể chuyển vào database đồng thời (**cache stampede**). Nên kiểm soát TTL, làm nóng cache có chọn lọc, request coalescing và giới hạn số lần truy vấn fallback.

### Distributed cache

Redis/cache dùng chung có thể giảm trùng dữ liệu giữa instance, nhưng trở thành một dependency chung. Cần đo hit ratio, memory eviction, latency, network và giới hạn số connection. Cache không thay database chuẩn trong những nghiệp vụ đòi hỏi giao dịch mạnh.

### Read replicas và partitioning

Đối với service đọc nhiều, read replica có thể phân tán truy vấn nhưng thường có replication lag. Một yêu cầu vừa ghi xong rồi đọc ngay từ replica có thể thấy giá trị cũ; cần chọn consistency level phù hợp. Partitioning/sharding giúp chia dữ liệu theo khóa nhưng tăng độ phức tạp truy vấn và giao dịch xuyên shard.

### Không scale vượt giới hạn dữ liệu

Mỗi replica có thể tạo thêm thread và pool kết nối; một chiến lược scale thành công ở tầng ứng dụng vẫn thất bại nếu storage, index, I/O hoặc transaction serialization bị bão hòa. Quan sát metrics giữa các tầng để biết điểm nghẽn mới xuất hiện ở đâu.

## 18. Ví dụ thực tế: khuyến mãi làm Catalog tăng tải đột biến

Giả sử trong giờ flash sale:
- Catalog nhận 1.200 request/giây, tăng 4 lần so với bình thường.
- Cart nhận 250 request/giây, tăng 2 lần.
- Order nhận 80 request/giây, tăng 1,5 lần.
- Payment bị giới hạn 100 lệnh/giây ở nhà cung cấp.
- Inventory nhận event có thể tăng đột biến và tạo backlog.

**Bước 1 — Đo giới hạn hiện tại.** Load test cho thấy một Catalog replica xử lý ổn định 100 request/giây ở p95 mục tiêu khi cache nóng. 1.200 request/giây cần ít nhất 12 replica theo tính toán lý tưởng, và có thể cần headroom lớn hơn tùy burst. Đo lại khi cache lạnh.

**Bước 2 — Scale riêng Catalog.** Cấu hình HPA theo CPU/RPS đã hiệu chuẩn, tăng maxReplicas trong mức node và search backend chịu được. Bảo đảm pod có readiness, warm-up và phân phối traffic.

**Bước 3 — Giữ Cart, Order ở mức phù hợp.** Không tăng chúng theo hệ số của Catalog vì tải thực khác. Nếu Order nghẽn connection pool, tối ưu giao dịch và pool trước khi tăng pod. Theo dõi p95 và error rate từng dịch vụ.

**Bước 4 — Bảo vệ Payment.** Thay vì cố tăng Payment để vượt quota bên ngoài, dùng giới hạn concurrency, kiểm soát retry, idempotency key và queue phù hợp. Nếu nghiệp vụ cho phép bất đồng bộ, thông báo trạng thái thanh toán đang xử lý thay vì giữ request vô hạn.

**Bước 5 — Scale Inventory theo lag.** Tăng worker khi backlog tăng, nhưng bị chặn bởi số Kafka partition và năng lực ghi database; đồng thời kiểm tra cùng event không làm trừ tồn kho hai lần.

**Bước 6 — Quan sát đầu cuối.** Tăng replica Catalog có thể giảm p95 Catalog nhưng checkout vẫn chậm vì Inventory/Payment. SLO end-to-end mới quyết định kết quả tốt hay chưa.

### Bảng kế hoạch vận hành minh họa

| Service | Trạng thái ban đầu | Khi flash sale | Điều kiện dừng tăng |
| --- | --- | --- | --- |
| Catalog | 4 replicas | 12–16 replicas | Search DB/cache hết headroom |
| Cart | 3 replicas | 5–6 replicas | Redis/DB latency hoặc CPU |
| Order | 3 replicas | 4–5 replicas | Lock/connection saturation |
| Payment | 2 replicas | 2–4 replicas | Provider rate limit |
| Inventory worker | 3 workers | 6–8 workers | Kafka partitions và DB write throughput |

Đây là minh họa cách lập kế hoạch, không phải dự đoán chính xác kết quả. Giá trị thực phải được suy ra từ load test, quan sát production và SLO.

## 19. Load test để chứng minh việc scale thực sự có ích

Trước khi kết luận một service có thể scale ngang, cần chạy kiểm thử chịu tải theo vài hình dạng tải:

1. **Baseline:** tải bình thường trong thời gian đủ dài, ghi throughput, p95/p99, CPU, memory và dependency latency.
2. **Step load:** tăng tải từng bậc, xem throughput có tăng tuyến tính hay chuyển sang bão hòa.
3. **Ramp:** tăng từ từ để quan sát autoscaler hoạt động.
4. **Spike:** tăng đột ngột để đánh giá headroom, cold start và rate limiting.
5. **Soak:** tải cao kéo dài để phát hiện memory leak, connection leak và backlog tích tụ.
6. **Failure test:** mất một node/pod hoặc dependency chậm, xem liệu SLO và dữ liệu có được bảo vệ hay không.
7. **Scale-down:** tải giảm; quan sát pod termination, request đang xử lý và trạng thái worker.

Dùng bộ phát tải có kiểm soát arrival rate và theo dõi request **thành công**; tổng số request gửi hoặc số pod chạy không đủ nói lên năng lực thực.

Nên so sánh các cấu hình N=2, 4, 8, 12 replicas với cùng workload và dependency capacity. Nếu throughput không tăng tương ứng, tìm điểm nghẽn ở database, broker, network, lock, CPU throttling hoặc nguồn phát tải trước khi tăng thêm.

### Chỉ số kiểm chứng

- **Throughput thành công:** request/giây hoặc message/giây hoàn thành đúng.
- **Latency p50/p95/p99:** đuôi chậm thường phản ánh saturation và queueing.
- **Error rate:** HTTP 5xx, timeout, 429, retry exhaustion.
- **CPU/memory/GC:** trên mỗi pod và tổng của service.
- **Saturation:** thread/connection pool, executor queue, DB lock và I/O.
- **Queue lag:** backlog và thời gian hoàn thành.
- **Autoscaler behavior:** desired/current/ready replicas, pending pod, số lần scale và thời gian đến Ready.
- **Chi phí:** CPU/RAM được đặt chỗ, node-hour, cache/DB/egress và cost per successful request.

Một bộ test chỉ cho thấy 12 replica xử lý nhiều request hơn 4 replica trong điều kiện lý tưởng chưa đủ để khẳng định toàn hệ thống an toàn. Cần nhìn thêm lỗi và tính đúng đắn khi retry, deploy và scale-down.

## 20. Vận hành autoscaling qua CI/CD

Từng service nên có cấu hình và quy trình phát hành riêng, nhưng vẫn cần quản lý các ràng buộc chung.

- **Capacity budget:** định nghĩa min/max replica trong giới hạn node, database và quota.
- **SLO guardrails:** đánh giá độ trễ, lỗi và backlog trước/sau khi điều chỉnh HPA.
- **Canary/rolling deployment:** một phiên bản mới có thể dùng CPU/RAM khác phiên bản cũ; metric cũ không bảo đảm ngưỡng scale vẫn hợp lý.
- **Resource requests:** giữ đủ chính xác để scheduler bố trí pod; tránh yêu cầu tài nguyên quá lớn khiến pod Pending.
- **Cluster capacity:** nếu nhu cầu pod vượt sức chứa node, phải có phương án tăng node hoặc giới hạn/giảm tải.
- **Emergency manual override:** ghi nhận ai điều chỉnh replica hoặc HPA, lý do và khi nào trả về chính sách bình thường.
- **Cost visibility:** theo dõi chi phí theo service và nhóm chức năng, tránh để autoscaler tạo chi phí tăng mà không cải thiện SLO.
- **Change tracking:** lưu phiên bản Deployment, HPA, config và rollout để điều tra khi latency thay đổi.

Một release làm giảm CPU mỗi request có thể giúp chạy ít replica hơn. Ngược lại, một thay đổi khiến cache miss tăng có thể tạo autoscaling bất thường. Cần liên kết metric với phiên bản để biết nguyên nhân.

## 21. Các sai lầm thường gặp

**Scale mọi service cùng một số replica.** Mỗi thành phần có lưu lượng và điểm nghẽn riêng; scale đồng loạt tốn tài nguyên và có thể không giải quyết nút thắt.

**Chỉ nhìn CPU.** Dịch vụ I/O-bound có thể CPU thấp nhưng p99 tăng và pool cạn. Chọn metric dựa trên công việc thực.

**Thêm pod khi DB đã nghẽn.** Nhiều replica tạo thêm query/kết nối, có thể làm DB chậm hơn. Cần tối ưu hoặc điều tiết nguồn tải.

**HPA maxReplicas rất lớn để phòng rủi ro.** Không có node, database hoặc quota tương ứng thì giới hạn lớn chỉ chuyển lỗi sang tầng khác.

**Lưu session hoặc dữ liệu chuẩn trong RAM một pod.** Cân bằng tải và scale-down làm mất tính liên tục. Thiết kế nguồn trạng thái chung hoặc mô hình session phù hợp.

**Coi request timeout là lệnh chưa thực hiện.** Retry trong hệ phân tán có thể tạo tác động lặp. Dùng idempotency cho nghiệp vụ ghi.

**Tăng số Kafka worker vượt số partition rồi kỳ vọng throughput tiếp tục tăng.** Concurrency thực tế phụ thuộc partition, message key và downstream.

**Không có readiness/cold-start kế hoạch.** Pod vừa tạo nhận traffic quá sớm hoặc đến lúc đủ nóng thì burst đã kết thúc.

**Scale-down cắt ngang công việc.** Cần graceful shutdown, checkpoint và chính sách chuyển giao/hoàn lại message.

**Đánh giá chỉ theo số replica.** KPI thật là throughput thành công, latency, error rate, backlog, độ đúng của dữ liệu và chi phí.

**Tăng concurrency không kiểm soát.** Dù nhiều replica hơn, tổng concurrency có thể vượt giới hạn DB hoặc provider; phải giới hạn phù hợp.

## 22. Checklist triển khai

- [ ] Dịch vụ có ranh giới triển khai và trách nhiệm xử lý rõ ràng.
- [ ] Đã xác định loại tải chính: CPU, I/O, memory, queue hay contention.
- [ ] Có SLO của riêng dịch vụ và SLO nghiệp vụ xuyên dịch vụ.
- [ ] Biết throughput bền vững mỗi replica dưới tải có kiểm soát.
- [ ] Các replica có thể phục vụ request độc lập; session và dữ liệu chuẩn không bị khóa ở một pod.
- [ ] Có readiness, startup/graceful shutdown và cách xử lý in-flight request.
- [ ] Requests/limits được đo, có quan sát CPU throttling và OOM.
- [ ] Min/max replicas phù hợp tải nền, burst và khả năng cung cấp node.
- [ ] Metric autoscaling tương quan với giới hạn thực tế, có ổn định khi scale down.
- [ ] Đã tính ngân sách database connection, broker partition, cache và quota API bên ngoài.
- [ ] Có timeout, rate limiting, backpressure và bounded concurrency ở dependency nhạy cảm.
- [ ] Worker/job bảo đảm retry và xử lý trùng an toàn khi scale ngang.
- [ ] Đã thử baseline, ramp, spike, soak, scale-down và sự cố instance/node.
- [ ] Có dashboard/alert về latency, lỗi, saturation, backlog, replica và chi phí.
- [ ] Kết quả scale được quyết định từ SLO và throughput thành công, không chỉ số pod.

## 23. Bài tập thực hành

Cho hệ thống gồm Gateway, Catalog, Cart, Order, Payment, Inventory Consumer và PostgreSQL. Bình thường Catalog nhận 150 request/giây, Order 40 request/giây và Inventory xử lý 200 event/giây. Khi flash sale, Catalog lên 900 request/giây, Order 90 request/giây, Inventory có 40.000 event tồn đọng; Payment Provider giới hạn 100 giao dịch/giây.

Một Catalog replica xử lý bền vững 75 request/giây dưới SLO. Inventory worker xử lý 40 event/giây và topic có 8 partition. Cơ sở dữ liệu Order bị tăng lock wait khi số kết nối hoạt động vượt ngưỡng đã quan sát.

Hãy thiết kế:
1. Số replica Catalog tối thiểu theo thông lượng lý tưởng và mức dự phòng cần kiểm thử.
2. HPA metric phù hợp cho Catalog; min/max và behavior để tránh thrashing.
3. Giới hạn scale Inventory, cách tính thời gian rút backlog khi còn traffic mới.
4. Vì sao Payment không thể tăng vô hạn dù có thêm replica.
5. Cách giữ Order ổn định khi PostgreSQL là điểm nghẽn.
6. Bộ metric và load test chứng minh thay đổi thực sự cải thiện p95 và thông lượng thành công.

Giải thích luôn điều gì xảy ra nếu node thiếu CPU để đặt pod mới, nếu 8 consumer Kafka đã dùng hết partition, và nếu gateway vẫn gửi request đến pod chưa sẵn sàng. Những tình huống này giúp phân biệt việc *muốn* mở rộng với khả năng mở rộng hiệu quả trong môi trường triển khai thật.

## Kết luận

Nhân bản dịch vụ theo nhu cầu tải riêng là lợi thế vận hành quan trọng của microservices: phần nào chịu nhiều tải thì có thể tăng năng lực phần đó, mà không buộc các dịch vụ khác phải tăng cùng tỷ lệ. Để điều này phát huy hiệu quả, cần biết điểm nghẽn thật, có ứng dụng đủ stateless, phân phối traffic an toàn, chọn metric và giới hạn autoscaling đúng với từng workload, đồng thời tính tới database, broker, API bên ngoài và xử lý trùng. Chỉ khi throughput thành công và SLO được cải thiện với chi phí chấp nhận được, việc tăng replica mới thực sự có giá trị.
