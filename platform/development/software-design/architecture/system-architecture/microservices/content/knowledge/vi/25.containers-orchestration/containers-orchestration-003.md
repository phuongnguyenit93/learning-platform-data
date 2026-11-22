# Pod, workload, Service và định tuyến trong Kubernetes

> **Chủ đề:** Software Design · System Architecture · Microservices  
> **Nhóm kiến thức:** Container và điều phối  
> **Mục tiêu:** Hiểu cách Kubernetes đưa container thành ứng dụng có khả năng tự phục hồi, duy trì nhiều replica, cấp địa chỉ ổn định và định tuyến lưu lượng từ bên trong lẫn bên ngoài cluster. Biết đọc manifest, mô tả đường đi request, lựa chọn đúng workload và chẩn đoán khi Service không tới được Pod.

## 1. Bài toán mà Kubernetes giải quyết

Giả sử có một ứng dụng Java/Spring gồm **Order API**, **Payment API**, **Inventory API** và một **notification worker**. Mỗi thành phần được đóng gói thành container image. Chạy một container trên một máy đơn lẻ khá đơn giản, nhưng hệ thống production cần trả lời những câu hỏi khác:

- Nếu container chết, thành phần nào tạo lại?
- Nếu node hỏng, ứng dụng có được chạy trên node khác không?
- Nếu tăng từ 2 lên 8 replica, client tìm địa chỉ nào để gọi?
- Khi Pod bị xóa và được thay bằng Pod mới có IP khác, điều gì cập nhật nơi nhận traffic?
- Khi một Pod chạy process nhưng chưa kết nối được database, có nên chuyển request vào đó?
- API nội bộ, giao diện từ Internet và worker chạy nền có nên dùng cùng một loại tài nguyên?
- Muốn cập nhật image mà không dừng toàn bộ hệ thống thì dùng cơ chế nào?

Kubernetes cung cấp các abstraction và controller cho những vấn đề đó:

- **Pod:** đơn vị triển khai và lập lịch nhỏ nhất; chứa một hoặc nhiều container có chung một số tài nguyên.
- **Workload controller:** duy trì trạng thái mong muốn, tạo/thay Pod, rollout hoặc quản lý vòng đời công việc.
- **Service:** danh tính mạng ổn định và cách tiếp cận một tập backend, thường là các Pod được chọn theo labels.
- **EndpointSlice:** mô tả các endpoint thực tế của một Service.
- **DNS, data plane, Ingress/Gateway:** giúp ứng dụng tìm nhau và đưa traffic tới đúng backend theo nhu cầu.

**Điểm mấu chốt:** Không dùng địa chỉ IP của Pod làm hợp đồng giữa các microservice. **Workload controller giữ số lượng và vòng đời Pod; Service cung cấp điểm truy cập ổn định trước tập Pod có thể thay đổi.**

## 2. Bức tranh tổng quan của một Kubernetes cluster

~~~text
                           +----------------------------+
                           | Kubernetes Control Plane   |
                           | API Server                 |
                           | Scheduler                  |
                           | Controller Managers        |
                           | etcd                       |
                           +-------------+--------------+
                                         |
                         Desired state / observed state
                                         |
                     +-------------------+-------------------+
                     |                                       |
              Worker Node A                           Worker Node B
              +-------------------+                   +-------------------+
              | kubelet / runtime |                   | kubelet / runtime |
              | network components|                   | network components|
              |                   |                   |                   |
              | Pod order-api-1   |                   | Pod order-api-2   |
              |  +------------+   |                   |  +------------+   |
              |  | Java app   |   |                   |  | Java app   |   |
              |  +------------+   |                   |  +------------+   |
              |                   |                   |                   |
              | Pod worker-1      |                   | Pod payment-api-1 |
              +-------------------+                   +-------------------+
                     ^                                       ^
                     +-------------------+-------------------+
                                         |
                            Service + endpoint discovery
                                         |
                                Other clients/Services
~~~

**Control plane** giữ và điều phối trạng thái mong muốn: API Server tiếp nhận tài nguyên; controllers so sánh trạng thái thực tế với trạng thái mong muốn; scheduler quyết định nơi đặt những Pod chưa được gán node; etcd lưu dữ liệu trạng thái của cluster.

**Worker node** thực thi các Pod nhờ kubelet và container runtime, đồng thời có hệ thống mạng tương ứng với cách cluster được cấu hình. Các thành phần mạng có thể bao gồm kube-proxy, CNI plugin và/hoặc eBPF data plane tùy triển khai.

Kubernetes vận hành chủ yếu theo **reconciliation loop**: khai báo muốn có ba replica, controller liên tục tìm cách đưa cluster đến trạng thái đó. Không phải cứ gọi **kubectl apply** là container lập tức sẵn sàng nhận traffic.

Khi phân tích sự cố, tách ba lớp:

1. **Desired state:** manifest và tài nguyên trong Kubernetes API nói muốn gì?
2. **Actual state:** Pod/containers/nodes thực sự đang ở trạng thái nào?
3. **Traffic state:** endpoint nào đã ready, DNS và routing có đưa request tới backend đó không?

## 3. Pod là gì?

**Pod** là đơn vị nhỏ nhất được Kubernetes scheduler lên lịch như một khối. Pod có thể chứa một container ứng dụng hoặc nhiều container phối hợp chặt chẽ.

Trong cùng một Pod, các container:

- Chia sẻ **network namespace**: cùng Pod IP, dùng **localhost** để liên lạc, không thể cùng bind một port/protocol trên cùng địa chỉ nếu xung đột.
- Có thể chia sẻ **volumes** được khai báo và mount vào từng container.
- Có lifecycle gắn với Pod, nhưng từng container có thể được restart độc lập theo policy.
- Không tự động chia sẻ mọi namespace hay filesystem; phải hiểu resource isolation và cấu hình security context.

Ví dụ Pod chứa app Java và một sidecar thu thập dữ liệu:

~~~text
Pod: order-api-78d4d9c6cb-abc12
  Pod IP: 10.42.3.17
  |
  +-- Container A: order-api
  |      listens on 0.0.0.0:8080
  |
  +-- Container B: telemetry-agent
  |      sends data to collector
  |
  +-- Volume: shared-config
~~~

**Pod không đồng nghĩa với một container.** Một Pod có thể gồm init containers, app containers và các dạng sidecar được hỗ trợ tùy phiên bản/cấu hình Kubernetes. Không nhồi các microservice độc lập vào cùng một Pod chỉ để chúng gọi nhau qua localhost: chúng sẽ bị ghép chặt về placement, scale, deploy và failure domain.

### 3.1. Pod IP không phải danh tính vĩnh viễn

Một Pod mới thay thế Pod cũ thường nhận **IP mới**. Container restart trong cùng Pod có thể giữ Pod IP, nhưng **Pod recreation** là một đối tượng mới. IP cũng có thể thay đổi khi Pod bị evict, controller tạo lại hoặc node gặp sự cố.

Vì vậy:

- Không lưu Pod IP trong cấu hình client như một endpoint lâu dài.
- Không mặc định một Pod khi tự khởi động lại vẫn có địa chỉ cũ.
- Không dùng Pod name/IP thay thế business identity hoặc dữ liệu transaction.
- Dùng Service hoặc cơ chế discovery được thiết kế để tìm backend.
- Nếu cần network identity ổn định cho mỗi replica có state, cân nhắc **StatefulSet + headless Service** và hiểu rõ persistence.

### 3.2. Pod là ephemeral, dữ liệu phải được thiết kế riêng

Writable layer của container hoặc một số volume theo Pod lifecycle có thể mất khi Pod bị thay. **emptyDir** tồn tại theo Pod, không tồn tại sau khi Pod bị xóa, dù container trong cùng Pod có thể restart.

Nếu Order API lưu đơn hàng chỉ trên filesystem local của Pod, khi Pod bị thay có thể mất dữ liệu. Dùng database hoặc persistent storage phù hợp; không coi Kubernetes workload replication là replication dữ liệu nghiệp vụ.

## 4. Một Pod manifest cơ bản

~~~yaml
apiVersion: v1
kind: Pod
metadata:
  name: order-api-demo
  namespace: shop
  labels:
    app: order-api
    tier: backend
spec:
  containers:
    - name: order-api
      image: registry.example.com/shop/order-api:1.4.2
      ports:
        - name: http
          containerPort: 8080
      resources:
        requests:
          cpu: "100m"
          memory: "256Mi"
        limits:
          memory: "512Mi"
~~~

Đây là manifest minh họa; namespace **shop** phải tồn tại, registry/image phải hợp lệ. **containerPort** cung cấp thông tin mô tả cổng mà ứng dụng dự định lắng nghe; nó **không tự tạo Service** và không làm cổng được mở ra Internet.

Không nên trực tiếp tạo **bare Pod** cho một API production có yêu cầu tự phục hồi. Khi Pod bị xóa hoặc node bị mất, thiếu workload controller nghĩa là không có cùng cơ chế bảo đảm replica như Deployment.

**Quy tắc sử dụng:** Học Pod để hiểu đơn vị chạy; sử dụng controller thích hợp để quản lý Pod trong ứng dụng thật.

## 5. Labels, selectors và annotations

Kubernetes cần cách tìm những Pod thuộc một nhóm.

**Labels** là các cặp key/value phục vụ phân loại và lựa chọn đối tượng. **Selectors** tìm đối tượng theo labels.

Ví dụ:

~~~yaml
metadata:
  labels:
    app.kubernetes.io/name: order-api
    app.kubernetes.io/part-of: shop
    app.kubernetes.io/component: backend
    environment: production
~~~

Một Service có selector:

~~~yaml
selector:
  app.kubernetes.io/name: order-api
~~~

sẽ chọn Pod có label khớp **trong cùng namespace**, chứ không dựa vào tên Pod có chứa chuỗi "order-api". Nếu selector sai, Service có thể tồn tại nhưng không có backend.

**Annotations** dùng lưu metadata không nhằm mục đích chọn tập đối tượng, ví dụ checksum cấu hình, liên kết với observability, build SHA hay thông tin do controller tiêu thụ.

Vài lưu ý:

- Đặt nhãn ổn định cho **app/component**, không dùng request ID hoặc ID nghiệp vụ làm label chọn workload.
- Cân nhắc scope/version labels nếu triển khai canary với nhiều revision.
- Thay đổi label trên Pod hoặc selector có thể làm Pod đi vào/ra khỏi Service ngay cả khi code không đổi.
- Một Service không có selector có thể sử dụng endpoint được quản lý ngoài cơ chế chọn Pod tự động; cần hiểu rõ trust boundary khi dùng.

## 6. Workload là gì?

**Workload** là ứng dụng/công việc chạy trên Kubernetes; nhóm tài nguyên điều khiển vòng đời workload gồm **Deployment**, **StatefulSet**, **DaemonSet**, **Job** và **CronJob**. Chúng không thay thế Pod mà **tạo, quản lý hoặc tổ chức Pod** theo những cách khác nhau.

| Workload | Dùng khi | Đặc điểm chính |
|---|---|---|
| **Deployment** | API web, backend stateless, service có nhiều replica thay thế được | Quản lý ReplicaSets, rolling update, rollback, scale |
| **ReplicaSet** | Duy trì một số Pod replicas được chọn | Thường do Deployment quản lý, hiếm khi tạo trực tiếp |
| **StatefulSet** | Database/broker/member có danh tính ổn định theo replica | Pod identity có thứ tự, stable network identity với headless Service, PVC templates |
| **DaemonSet** | Agent cần chạy trên các node được chọn | Thường một Pod trên mỗi node đủ điều kiện: log/metrics/network agents |
| **Job** | Tác vụ hữu hạn, chạy đến completion | Theo dõi success/failure, retries và parallelism |
| **CronJob** | Tác vụ hữu hạn theo lịch | Tạo Job theo schedule; cần kiểm soát concurrency và missed schedules |
| **Bare Pod** | Demo, debug đặc biệt, trường hợp hiếm | Không có controller cấp cao bảo đảm rollout/desired replicas |

Chọn workload theo **đặc tính vòng đời**, không theo ngôn ngữ lập trình. Một ứng dụng Java có thể là Deployment nếu phục vụ HTTP liên tục, hoặc Job nếu chỉ chạy migration định kỳ rồi kết thúc.

### 6.1. Workload controller không đồng nghĩa với scheduler

Deployment controller tạo Pod template và giữ replica count. **Scheduler** chọn node phù hợp cho Pod chưa được gán dựa trên requests, node constraints, taints/tolerations, affinity và chính sách khác.

Nếu Pod ở trạng thái **Pending**, tăng replicas hoặc tạo lại Deployment không giải quyết được nếu cluster thiếu CPU, storage hoặc Pod không có node nào thỏa điều kiện.

## 7. Deployment, ReplicaSet và rolling update

Deployment dùng phổ biến cho microservice stateless như Order API:

~~~text
Deployment order-api
      |
      +-- ReplicaSet revision A (image 1.4.1)
      |      +-- Pod A1
      |      +-- Pod A2
      |
      +-- ReplicaSet revision B (image 1.4.2)
             +-- Pod B1
             +-- Pod B2
~~~

Khi thay image hoặc Pod template, Deployment điều phối replica mới và thu hồi cũ theo strategy. **ReplicaSet** là controller trung gian giúp giữ số Pod theo template.

Ví dụ:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: order-api
  namespace: shop
spec:
  replicas: 3
  revisionHistoryLimit: 5
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0
  selector:
    matchLabels:
      app: order-api
  template:
    metadata:
      labels:
        app: order-api
    spec:
      containers:
        - name: order-api
          image: registry.example.com/shop/order-api:1.4.2
          ports:
            - containerPort: 8080
              name: http
          readinessProbe:
            httpGet:
              path: /actuator/health/readiness
              port: http
            periodSeconds: 5
          livenessProbe:
            httpGet:
              path: /actuator/health/liveness
              port: http
            periodSeconds: 10
          resources:
            requests:
              cpu: 100m
              memory: 256Mi
            limits:
              memory: 512Mi
~~~

**Lưu ý với ví dụ:** Các đường dẫn Actuator cần được kích hoạt/cấu hình trong Spring Boot tương ứng. **replicas: 3** là mong muốn, không bảo đảm ba Pod sẽ ready nếu node thiếu tài nguyên, image kéo không được hoặc app lỗi. Chiến lược **maxUnavailable: 0** có thể khiến rollout chờ vô hạn nếu Pod mới không ready, là hành vi an toàn hơn việc làm mất capacity trong nhiều trường hợp nhưng cần timeout/cảnh báo và đủ cluster capacity.

### 7.1. Thế nào là rolling update an toàn?

- Pod mới được tạo theo Pod template mới.
- Scheduler đặt Pod lên node phù hợp.
- Kubelet kéo image, thiết lập volume/network và chạy containers.
- Application khởi động, sau đó readiness probe cho biết có thể nhận traffic.
- Endpoint liên quan được phản ánh trong EndpointSlice và routing.
- Pod cũ được thu hồi theo chiến lược khi điều kiện rollout cho phép.

Không thể khẳng định **zero downtime** chỉ từ **strategy: RollingUpdate**. Còn phải có readiness đúng, graceful shutdown, đủ replicas/capacity, xử lý connections in flight và client retries có kiểm soát.

### 7.2. Rollback trong Deployment

Có thể quay về Pod template của revision trước trong phạm vi lịch sử có sẵn. **Rollback image không tự rollback database migration hoặc dữ liệu mới**. Với thay đổi schema, cần chiến lược **expand–migrate–contract** để hai version cùng chạy trong giai đoạn chuyển tiếp.

## 8. StatefulSet: Khi replica cần identity ổn định

Deployment thường phù hợp cho các Pod tương đương và có thể thay thế lẫn nhau. **StatefulSet** phù hợp hơn khi mỗi Pod cần định danh ổn định và storage riêng.

Ví dụ cluster database/broker:

~~~text
StatefulSet: catalog-db
   |
   +-- catalog-db-0 → PVC data-catalog-db-0
   +-- catalog-db-1 → PVC data-catalog-db-1
   +-- catalog-db-2 → PVC data-catalog-db-2
~~~

Đặc điểm:

- Pod names có ordinal ổn định.
- Thường kết hợp **headless Service** và trường **spec.serviceName** để cung cấp hostname riêng cho từng replica.
- Có thể dùng **volumeClaimTemplates** để mỗi replica có PersistentVolumeClaim riêng.
- Có cơ chế cập nhật/thứ tự theo chính sách của StatefulSet.

**StatefulSet không tự giải quyết replication dữ liệu, leader election, quorum, backup hoặc consistency**. Những phần này là trách nhiệm của chính database/broker hoặc operator chuyên biệt. StatefulSet cũng không bảo đảm mọi Pod luôn có IP cũ; nó cung cấp **identity DNS/ordinal** có thể ổn định.

Không cần StatefulSet chỉ vì một API truy cập PostgreSQL: API stateless vẫn dùng Deployment, còn PostgreSQL cần được vận hành qua giải pháp storage/operator thích hợp.

## 9. DaemonSet, Job và CronJob

### 9.1. DaemonSet

Dùng khi một agent cần chạy trên mỗi node đủ điều kiện, ví dụ log collector, metrics agent hoặc network agent.

~~~text
Node A -> telemetry-agent Pod
Node B -> telemetry-agent Pod
Node C -> telemetry-agent Pod
~~~

DaemonSet không phải cách thông thường để scale Order API theo traffic. Quy tắc scheduling, tolerations và node selectors quyết định agent thực tế chạy ở node nào.

### 9.2. Job

Dùng cho công việc hữu hạn: migration, import batch, tính báo cáo hoặc xử lý một lô dữ liệu. Job theo dõi Pod hoàn tất thành công hoặc thất bại, có **backoffLimit**, parallelism/completions và các tùy chọn khác.

Cần thiết kế **idempotency**: một Job/Pod có thể được chạy lại hoặc có nhiều execution trong trường hợp retry/failure. Nếu chuyển tiền hoặc gửi email, phải có business key và chính sách chống tác dụng phụ trùng, không dựa vào giả định "Kubernetes chỉ chạy đúng một lần".

### 9.3. CronJob

CronJob tạo Job theo lịch. Ví dụ đối soát mỗi ngày. Cần chú ý **concurrencyPolicy** (Allow, Forbid, Replace) và logic missed starts/timezone theo phiên bản/thiết kế cluster.

**CronJob không phải transaction scheduler exactly-once.** Với công việc nhạy cảm, dùng khóa nghiệp vụ, deduplication và checkpoint để chấp nhận chạy trễ, chạy lại hoặc job trước chưa kết thúc.

## 10. Service: Điểm truy cập ổn định trước các Pod biến động

Một Service thường cung cấp **tên DNS**, **ClusterIP** hoặc cách phơi bày endpoint ổn định hơn Pod, rồi liên kết đến các backend thích hợp.

~~~text
Order Client
    |
    | HTTP http://order-api.shop.svc.cluster.local:80
    v
Service: order-api
    |  ClusterIP: virtual service address
    |
    +----> Pod order-api-abc (10.42.1.7:8080)
    +----> Pod order-api-def (10.42.2.9:8080)
    +----> Pod order-api-ghi (10.42.3.5:8080)
~~~

Khi một Pod được thay, service name vẫn có thể giữ nguyên. Hệ thống endpoint discovery cập nhật backend Pod mới và loại backend không còn phù hợp. Service tránh việc từng client phải biết mọi Pod IP.

Một Service **không tạo Pod**, **không tự scale Deployment**, **không tự kiểm tra logic nghiệp vụ của ứng dụng**, và cũng không bảo đảm tải được phân phối theo round-robin đúng nghĩa cho từng HTTP request. Cách phân phối có thể diễn ra ở mức connection/flow tùy networking implementation.

### 10.1. Service selector và EndpointSlice

Với Service có selector, control plane thường tạo/quản lý **EndpointSlice** mô tả các endpoint. EndpointSlice giúp biểu diễn tập backend và thông tin như address, port, readiness/serving/terminating conditions theo khả năng/phiên bản API.

Ví dụ Service có:

~~~yaml
selector:
  app: order-api
~~~

nhưng Pod đang mang label:

~~~yaml
labels:
  app: orders-api
~~~

thì **không có Pod khớp selector**, dẫn đến tình trạng Service/DNS tồn tại nhưng request không đến được backend.

Khi debug cần kiểm tra cả **Service selector → Pod labels → EndpointSlice → Pod readiness**; chỉ nhìn **kubectl get svc** là chưa đủ.

## 11. Cổng Service: port, targetPort và nodePort

Ví dụ:

~~~yaml
apiVersion: v1
kind: Service
metadata:
  name: order-api
  namespace: shop
spec:
  type: ClusterIP
  selector:
    app: order-api
  ports:
    - name: http
      protocol: TCP
      port: 80
      targetPort: 8080
~~~

- **port: 80:** cổng mà client dùng khi kết nối tới Service.
- **targetPort: 8080:** cổng ở backend Pod, nơi ứng dụng thực sự lắng nghe. Có thể là số hoặc tên port được định nghĩa trong Pod.
- **nodePort:** khi Service loại NodePort/LoadBalancer cần node port theo chính sách, traffic có thể vào qua cổng được ánh xạ trên node.
- **containerPort:** trường trên Pod khai báo cổng container dự định lắng nghe; bản thân nó không khởi chạy server, không phải quy tắc NAT.

Ví dụ client gọi **order-api:80**, Service chuyển tới **PodIP:8080**. Nếu app thực sự listen 9090 nhưng targetPort=8080, Service có endpoint hợp lệ nhưng kết nối có thể bị từ chối hoặc timeout.

**Một sai lầm phổ biến:** Thấy cổng 8080 trong Dockerfile hoặc containerPort và cho rằng Service tự tìm đúng port. Phải xác nhận server bind đúng interface/cổng và mapping đã khai báo.

## 12. Các loại Service và trường hợp sử dụng

| Service type | Mục đích | Đặc điểm |
|---|---|---|
| **ClusterIP** | API nội bộ trong cluster | IP ảo nội bộ; là loại mặc định |
| **NodePort** | Mở cổng ở các node theo cơ chế Service | Cho phép truy cập qua NodeIP:nodePort nếu network/firewall cho phép |
| **LoadBalancer** | Yêu cầu hạ tầng tích hợp cấp LB ngoài/ở cấp mạng | Thường xây trên cơ chế Service/NodePort hoặc LB trực tiếp tùy provider |
| **ExternalName** | Ánh xạ tên Service đến DNS name bên ngoài | Chủ yếu là CNAME/DNS; không tạo proxy hoặc backend Pod như Service thông thường |
| **Headless Service** | Discovery trực tiếp endpoint hoặc identity từng replica | **clusterIP: None**; DNS trả endpoint phù hợp thay vì một ClusterIP ảo |

### 12.1. ClusterIP

Phù hợp cho Order API được Payment API hoặc Gateway gọi **nội bộ**. Không trực tiếp phơi một IP public chỉ vì đặt type ClusterIP.

### 12.2. NodePort

Ví dụ expose port 30080 trên node. NodePort phụ thuộc firewall, route và node network. Nó không tự mang TLS, WAF, authentication hay DNS hostname thân thiện. Thường dùng làm thành phần hạ tầng, lab, hoặc khi có thiết kế truy cập rõ, không mặc định dùng làm Internet edge cho mọi microservice.

### 12.3. LoadBalancer

Trên cloud tích hợp, service loại LoadBalancer thường kích hoạt việc tạo LB để người dùng có địa chỉ ngoài cluster. **Service manifest không bảo đảm LB được cấp thành công** nếu cluster không có cloud controller hoặc implementation tương ứng. Có thể thấy external IP ở trạng thái pending.

### 12.4. ExternalName

~~~yaml
apiVersion: v1
kind: Service
metadata:
  name: legacy-payments
  namespace: shop
spec:
  type: ExternalName
  externalName: payments.legacy.example.com
~~~

DNS cho service name có thể ánh xạ đến DNS name bên ngoài. **ExternalName không tự làm HTTP reverse proxy**, không tự sửa Host header, không bảo đảm TLS certificate của đích khớp với hostname Kubernetes mà client sử dụng. Cần hiểu behavior của client, SNI và certificate validation.

### 12.5. Headless

~~~yaml
apiVersion: v1
kind: Service
metadata:
  name: catalog-db-headless
  namespace: shop
spec:
  clusterIP: None
  selector:
    app: catalog-db
  ports:
    - name: db
      port: 5432
~~~

Dùng cho discovery trực tiếp các endpoint hoặc danh tính StatefulSet. Không kỳ vọng kube-proxy tạo VIP cân bằng tải như ClusterIP thông thường. Client/library có thể phải tự xử lý lựa chọn và kết nối tới endpoint cụ thể.

## 13. DNS nội bộ và cách gọi Service giữa các namespace

DNS của cluster thường cung cấp tên như:

~~~text
order-api
order-api.shop
order-api.shop.svc
order-api.shop.svc.cluster.local
~~~

**cluster.local** là ví dụ domain thường gặp, nhưng domain thực tế có thể được cấu hình khác. Trong cùng namespace, **http://order-api** có thể hoạt động nhờ DNS search suffix; từ namespace khác nên dùng **order-api.shop** hoặc FQDN để tránh nhầm tên.

Ví dụ từ Payment Service ở namespace **billing**:

~~~text
http://order-api.shop.svc.cluster.local:80/orders/ORD-1001
~~~

Lưu ý:

- DNS giải tên Service thành địa chỉ, **không có nghĩa mọi Pod backend đều ready**.
- Với headless Service, DNS có thể trả nhiều endpoint addresses tùy điều kiện; ứng dụng cần hành vi client phù hợp.
- DNS cache trong JVM/client có TTL riêng. Đặc biệt khi kết nối trực tiếp Pod IP qua headless Service, cần hiểu cache và connection lifetimes.
- Nếu tên Service trùng trong namespace khác, tên ngắn có thể dẫn tới nhầm đích.
- **ServiceAccount không phải Service**: ServiceAccount là identity của workload khi tương tác với Kubernetes API hoặc cơ chế xác thực liên quan, không tạo tên DNS để client gọi API.

## 14. Luồng định tuyến nội bộ khi client gọi ClusterIP

Một luồng điển hình:

~~~text
Payment Pod
    |
    | DNS lookup: order-api.shop.svc.cluster.local
    v
Cluster DNS (ví dụ CoreDNS)
    |
    | trả ClusterIP của order-api
    v
Payment Pod kết nối tới Service IP:80
    |
    v
Service data plane ở node/network
    | sử dụng thông tin EndpointSlice/backend
    v
Một Order Pod phù hợp tại PodIP:8080
    |
    v
Order API trả response theo connection hiện tại
~~~

Về implementation:

- Một số cluster dùng **kube-proxy** và luật forwarding ở node; những cluster khác dùng **CNI/eBPF-based service routing** hoặc implementation tương đương.
- Service/EndpointSlice là API abstraction; đường đi gói tin thực tế khác nhau theo cluster.
- **Load balancing thường ở L4/flow**, không có bảo đảm phân phối đều theo từng HTTP request. HTTP keep-alive có thể khiến nhiều request dùng cùng một kết nối tới một Pod.
- Không giả định Service định tuyến theo **HTTP path**, JWT claim hoặc gRPC method; đó là nhu cầu của proxy/Ingress/Gateway/service mesh ở lớp phù hợp.

**Câu hỏi để phân biệt:** "Gọi Pod nào?" thường do Service/data plane giải quyết; "Request tới path /payments hay /orders?" thường cần một lớp HTTP routing.

## 15. Readiness quyết định backend có nhận traffic không

Một Pod có process chạy chưa chắc đã đủ khả năng phục vụ. **Readiness probe** giúp Kubernetes biết khi nào đưa Pod vào danh sách endpoint sẵn sàng của Service theo hành vi của controller/network.

Ví dụ Spring Boot:

~~~yaml
readinessProbe:
  httpGet:
    path: /actuator/health/readiness
    port: 8080
  initialDelaySeconds: 5
  periodSeconds: 5
  timeoutSeconds: 2
  failureThreshold: 3
~~~

Khi readiness thất bại, Pod vẫn có thể đang chạy nhưng thông thường **không được lựa chọn làm endpoint ready để nhận traffic mới**. Quá trình cập nhật endpoint/forwarding không phải chuyển trạng thái tức thì trên mọi thành phần; ứng dụng vẫn cần xử lý graceful shutdown và in-flight requests.

**Readiness tốt:** phản ánh application có khả năng phục vụ request theo hợp đồng hiện tại. **Readiness kém:** trả true ngay khi JVM chạy nhưng chưa load config, chưa init dependency bắt buộc hoặc chưa apply migration cần thiết.

Không nên biến readiness thành chuỗi gọi remote của **mọi** service phụ nếu việc đó khiến một outage nhỏ loại bỏ toàn bộ replicas đồng thời. Chọn dependency kiểm tra theo đường phục vụ thực tế.

## 16. Phân biệt startup, liveness và readiness probes

| Probe | Câu hỏi | Khi thất bại |
|---|---|---|
| **startupProbe** | Ứng dụng đã hoàn tất giai đoạn khởi động ban đầu chưa? | Có thể restart container nếu vượt ngưỡng; liveness/readiness được trì hoãn trong giai đoạn startup |
| **livenessProbe** | Process có bị kẹt/hỏng đến mức cần restart không? | Kubelet có thể restart container theo policy |
| **readinessProbe** | Có thể nhận traffic lúc này không? | Pod bị đánh dấu not-ready, ảnh hưởng routing tới Service |

Ví dụ:

~~~yaml
startupProbe:
  httpGet:
    path: /actuator/health/liveness
    port: http
  periodSeconds: 5
  failureThreshold: 24

livenessProbe:
  httpGet:
    path: /actuator/health/liveness
    port: http
  periodSeconds: 10
  timeoutSeconds: 2

readinessProbe:
  httpGet:
    path: /actuator/health/readiness
    port: http
  periodSeconds: 5
  timeoutSeconds: 2
~~~

Trong ví dụ, **http** là tên container port đã khai báo. Đường dẫn phụ thuộc cấu hình Spring Boot Actuator, không tự xuất hiện ở mọi ứng dụng. Chọn thời gian probe theo thời gian startup bình thường, GC pauses, khả năng hồi phục và SLO.

Một anti-pattern là **liveness gọi đồng bộ database, Config Server và ba service khác**. Khi downstream lỗi tạm thời, Kubernetes restart hàng loạt container và tạo thêm tải. Một dependency outage nên thường ảnh hưởng readiness/degraded behavior của chức năng phù hợp hơn là làm process restart loop.

## 17. Định tuyến từ Internet: Ingress và Gateway API

**Service** cung cấp abstraction endpoint/L4. Để route theo **hostname**, **HTTP path**, TLS termination và policy ở biên, thường dùng **Ingress controller** hoặc một implementation **Gateway API**.

Ví dụ người dùng gọi:

~~~text
https://shop.example.com/orders/1001
             |
             v
   Cloud Load Balancer / Edge
             |
             v
   Ingress Controller / Gateway
             |
     host + path routing, TLS
             |
             +---- /orders   → order-api Service/Endpoints
             |
             +---- /payments → payment-api Service/Endpoints
                             |
                             v
                            Pods
~~~

**Ingress resource chỉ là khai báo quy tắc**. Phải có **Ingress controller** phù hợp mới thực thi routing. **Gateway API** cung cấp tập tài nguyên như GatewayClass, Gateway, HTTPRoute, ReferenceGrant, ... để mô tả vai trò hạ tầng, listener và route linh hoạt hơn; cũng cần controller triển khai.

Không nên phát biểu mọi traffic bắt buộc đi qua đúng chuỗi **LB → Ingress → Service VIP → Pod**. Một số controller đọc endpoint rồi gửi trực tiếp tới Pod IP; những implementation khác đưa traffic qua ClusterIP. **Hợp đồng cấu hình Kubernetes** không quy định một packet path duy nhất cho mọi controller.

### 17.1. Ví dụ Ingress

~~~yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: shop-public
  namespace: shop
spec:
  ingressClassName: nginx
  tls:
    - hosts:
        - shop.example.com
      secretName: shop-tls
  rules:
    - host: shop.example.com
      http:
        paths:
          - path: /orders
            pathType: Prefix
            backend:
              service:
                name: order-api
                port:
                  number: 80
~~~

Manifest chỉ hoạt động nếu cluster có controller cho **ingressClassName: nginx** hoặc cấu hình tương đương, chứng chỉ TLS hợp lệ được đặt ở **shop-tls**, DNS public trỏ tới edge và networking cho phép. **Ingress không mặc định rewrite /orders**; backend cần hiểu path hoặc controller phải được cấu hình rewrite đúng hợp đồng.

Cần thêm authentication, authorization, rate limit, WAF hoặc mTLS theo yêu cầu hệ thống. **Ingress resource không tự động cung cấp đủ các năng lực bảo mật đó**.

### 17.2. Gateway API

Ở hệ thống nhiều team, **Gateway API** có thể phân tách rõ hơn:

- **GatewayClass:** loại gateway/controller chịu trách nhiệm.
- **Gateway:** listener/entry point do nhóm hạ tầng quản lý.
- **HTTPRoute:** điều kiện match hostname/path/header và backend references do team ứng dụng quản lý theo quyền.
- **ReferenceGrant:** cho phép một số tham chiếu xuyên namespace khi API yêu cầu và đã cấp quyền.

Cần kiểm tra implementation/controller và API versions phù hợp; không mặc định mọi tính năng/filters đều được mọi gateway hỗ trợ.

## 18. Một manifest tổng hợp: Namespace, Deployment, Service, Ingress

Ví dụ dưới đây gắn kết ba khái niệm cốt lõi:

~~~yaml
apiVersion: v1
kind: Namespace
metadata:
  name: shop
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: order-api
  namespace: shop
spec:
  replicas: 3
  selector:
    matchLabels:
      app: order-api
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0
  template:
    metadata:
      labels:
        app: order-api
        component: http-api
    spec:
      terminationGracePeriodSeconds: 30
      containers:
        - name: order-api
          image: registry.example.com/shop/order-api:1.4.2
          ports:
            - name: http
              containerPort: 8080
          readinessProbe:
            httpGet:
              path: /actuator/health/readiness
              port: http
            periodSeconds: 5
            timeoutSeconds: 2
          livenessProbe:
            httpGet:
              path: /actuator/health/liveness
              port: http
            periodSeconds: 10
            timeoutSeconds: 2
          resources:
            requests:
              cpu: 100m
              memory: 256Mi
            limits:
              memory: 512Mi
---
apiVersion: v1
kind: Service
metadata:
  name: order-api
  namespace: shop
spec:
  type: ClusterIP
  selector:
    app: order-api
  ports:
    - name: http
      port: 80
      targetPort: http
---
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: shop-public
  namespace: shop
spec:
  ingressClassName: nginx
  tls:
    - hosts: [shop.example.com]
      secretName: shop-tls
  rules:
    - host: shop.example.com
      http:
        paths:
          - path: /orders
            pathType: Prefix
            backend:
              service:
                name: order-api
                port:
                  name: http
~~~

**Đọc luồng:**

1. Deployment mong muốn ba Pod mang label **app=order-api**.
2. Service trong **shop** chọn Pod theo label đó; client nội bộ gọi **order-api.shop.svc** ở port **80**.
3. **targetPort: http** trỏ tới container port mang tên **http**, ở đây là **8080**.
4. Ingress quy định hostname **shop.example.com** và path prefix **/orders** chuyển tới Service.
5. Readiness probe quyết định thời điểm Pod được xem là sẵn sàng để định tuyến.
6. Khi Deployment thay Pod, Service identity giữ nguyên và endpoint list cập nhật.

Điều kiện hoạt động thực tế: image có tồn tại/được pull, namespace và controller được setup, Spring app nghe trên cổng 8080, health endpoints hợp lệ, TLS/DNS/Ingress controller đã được cấu hình. Những object này không tự tạo một hạ tầng cluster hoàn chỉnh.

## 19. Áp dụng và kiểm tra manifest bằng kubectl

Giả sử đã có kubeconfig đúng cluster và file **shop.yaml** chứa manifest ở trên:

~~~bash
kubectl apply -f shop.yaml

kubectl get deployments -n shop
kubectl get replicasets -n shop
kubectl get pods -n shop -l app=order-api -o wide
kubectl get services -n shop
kubectl get ingress -n shop

kubectl rollout status deployment/order-api -n shop
~~~

Để kiểm tra quan hệ Service/Endpoints:

~~~bash
kubectl describe service order-api -n shop
kubectl get endpointslices -n shop \
  -l kubernetes.io/service-name=order-api
kubectl describe endpointslices -n shop \
  -l kubernetes.io/service-name=order-api
~~~

**Lệnh là ví dụ học tập**: cần xác nhận cluster context và quyền trước khi apply vào môi trường thực. Lệnh **describe endpointslices** với label selector cho phiên bản kubectl tương thích sẽ trả thông tin slice liên quan; nếu không hỗ trợ cú pháp cụ thể, dùng **kubectl get endpointslices -o yaml** trong namespace và lọc đúng tên Service.

Xem tình trạng Pod và sự kiện:

~~~bash
kubectl describe pod <pod-name> -n shop
kubectl logs deployment/order-api -n shop --tail=100
kubectl get events -n shop --sort-by=.metadata.creationTimestamp
~~~

Để thử từ máy local trong môi trường có quyền:

~~~bash
kubectl port-forward service/order-api 8080:80 -n shop
# Terminal khác:
curl -i http://localhost:8080/orders/1001
~~~

**port-forward** là đường truy cập tạm thời để debug, không phải một chiến lược phơi bày production hoặc bằng chứng Ingress/LB hoạt động.

## 20. Lệnh chẩn đoán DNS và lưu lượng từ bên trong cluster

Một Pod debug có công cụ DNS/HTTP, được triển khai với image tin cậy và chính sách RBAC phù hợp, có thể kiểm tra:

~~~bash
# Chạy các lệnh dưới đây bên trong Pod debug:
nslookup order-api.shop.svc.cluster.local
curl -v --max-time 5 http://order-api.shop.svc.cluster.local:80/actuator/health
~~~

Nếu DNS không trả tên, kiểm tra:

- Namespace và Service name đã đúng chưa?
- DNS pods và Service của cluster có đang hoạt động?
- Pod debug có cấu hình dnsPolicy hoặc resolv.conf khác thường không?
- NetworkPolicy egress có chặn DNS UDP/TCP tới DNS service không?

Nếu DNS trả ClusterIP nhưng curl timeout:

- Service selector có endpoints ready không?
- Container có thực sự listen đúng targetPort trên interface phù hợp không?
- Pod có đang CrashLoopBackOff hoặc readiness fail?
- NetworkPolicy có chặn traffic giữa namespaces không?
- Pod-to-Pod networking và CNI plugin có lỗi không?
- Application có đòi TLS/authentication hoặc protocol khác không?

**Chẩn đoán theo lớp** giúp tránh sửa sai thứ không liên quan. Một lỗi HTTP 403 nghĩa là đã đến được thành phần trả response và cần xem authorization/policy, không phải mặc định do DNS. Một lỗi 503 từ Gateway có thể liên quan zero healthy upstream, routing config hoặc backend timeout; cần xem logs/metrics của chính Gateway và Service endpoints.

## 21. NetworkPolicy không giống Service routing

Service cung cấp **đích đến ổn định**, còn **NetworkPolicy** thể hiện quy tắc traffic **được phép** giữa các Pod/IP theo hỗ trợ của CNI.

Ví dụ mô hình:

~~~text
Gateway Pod ───── allowed ─────> Order API Pods
Billing Pod ───── allowed ─────> Order API Pods
Unknown Pod ───── denied ──────> Order API Pods
~~~

Một NetworkPolicy chọn Pod đích bằng **podSelector** và quy định ingress/egress theo labels, namespaces, IP blocks hoặc ports. Chính sách thực thi phụ thuộc **network plugin có hỗ trợ NetworkPolicy**; tạo object nhưng plugin không thực thi sẽ không tạo bảo vệ mong muốn.

### 21.1. Ví dụ chỉ cho phép một nhóm client gọi API

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: order-api-ingress
  namespace: shop
spec:
  podSelector:
    matchLabels:
      app: order-api
  policyTypes:
    - Ingress
  ingress:
    - from:
        - podSelector:
            matchLabels:
              role: trusted-client
      ports:
        - protocol: TCP
          port: 8080
~~~

Manifest này chọn traffic đến Order Pod từ Pod có **role=trusted-client trong cùng namespace shop**. Nó **không tự cho phép Ingress controller ở namespace khác**, không bảo đảm đáp ứng mọi đường health/monitoring, và không kiểm soát egress nếu chưa khai báo egress policy. Không copy chính sách này vào production khi chưa lập bản đồ nguồn traffic hợp lệ.

**NetworkPolicy không làm authentication/authorization ở lớp HTTP.** Một Pod có thể được phép kết nối TCP tới Order API nhưng vẫn phải trình access token, được kiểm tra scope và ownership theo chính sách ứng dụng.

### 21.2. Default deny và chiều egress

Nếu thiết kế **default deny ingress/egress**, phải có allow rules cho DNS, API/DB, monitoring, và egress thiết yếu. Chính sách sai có thể khiến Pod ready nhưng không kết nối được downstream, hoặc làm readiness fail. Các network policy cho traffic đến ingress controller và từ ingress controller tới backend cần được xét theo vị trí Pod/namespace thực tế.

Không mặc định Kubernetes có network isolation hoàn chỉnh khi chưa triển khai policy và CNI phù hợp. Trong nhiều cluster, **không có NetworkPolicy** nghĩa là Pod thường có thể giao tiếp khá tự do trong phạm vi network được cấp.

## 22. Routing L4 và L7: Đặt đúng trách nhiệm

| Lớp / Thành phần | Nhận biết chính | Ví dụ việc nên làm |
|---|---|---|
| **Cluster DNS** | Tên Service | Tra **order-api.shop.svc** thành endpoint Service |
| **Service + data plane** | IP, port, protocol và tập backend | Chuyển kết nối tới Pod endpoint phù hợp |
| **Ingress/Gateway HTTPRoute** | Host, path, header và các thuộc tính HTTP được hỗ trợ | **shop.example.com/orders** đến Order API |
| **Service mesh** | Workload identity, proxy, policy traffic | mTLS, timeouts, routing theo version khi triển khai |
| **Application** | JWT claims, user, tenant, order ownership, business rules | Xác thực và quyết định user có quyền xem đơn hay không |

Không giao responsibility authorization của Order API cho ClusterIP Service. Service không hiểu “người dùng Alice chỉ đọc đơn của Alice”.

Nếu cần **canary traffic 5% sang version B**, một Service thường không biểu diễn routing HTTP weighted một cách tiện dụng. Dùng Gateway API, service mesh hoặc progressive delivery controller có hỗ trợ thật; hoặc thiết kế canary ở tầng khác có observability và rollback.

**Không nên khẳng định Kubernetes Service luôn round-robin.** Khi có HTTP keep-alive, traffic có thể dồn vào một Pod dù số request nhiều, bởi lựa chọn backend thường gắn với connection hoặc implementation chi tiết.

## 23. Request path thực tế: Gateway → Order → Payment

Ví dụ trình duyệt tạo đơn:

~~~text
1. Browser → https://shop.example.com/orders
2. External DNS/LB đưa traffic tới Ingress/Gateway controller
3. Controller match hostname/path theo rule
4. Controller chọn backend thuộc Order Service/Endpoints
5. Order Pod nhận HTTP request tại port 8080
6. Order Pod gọi Payment Service tại payment-api.billing.svc:80
7. Payment Service routing tới một Payment Pod ready
8. Payment Pod xử lý quyền và giao dịch, trả kết quả
9. Order trả response về browser
~~~

Mỗi lớp có một kiểu failure khác nhau:

- **DNS bên ngoài:** hostname không trỏ đúng edge.
- **Ingress/Gateway:** không có controller, không match rule, TLS lỗi hoặc controller không có backend.
- **Service:** selector sai, endpoint list trống, targetPort sai.
- **Pod:** crash, chưa ready, không bind port, bị OOM, config thiếu.
- **Network:** CNI/NetworkPolicy/mTLS/firewall gây timeout.
- **Application:** HTTP 401/403/5xx do policy hoặc nghiệp vụ.
- **Downstream:** Payment không sẵn sàng, timeout, retry storm.

Dùng **traceId/correlation ID** xuyên Gateway/Order/Payment để liên kết request; metrics theo service/route/status cho biết lỗi lan ở đâu. Không đưa traceId hoặc orderId thành metric label có cardinality vô hạn.

## 24. Scaling: Replica count không giống số request được xử lý

Deployment có thể scale bằng cách đổi **spec.replicas** hoặc dùng **HorizontalPodAutoscaler (HPA)** dựa trên metrics được hỗ trợ.

Ví dụ HPA CPU:

~~~yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: order-api
  namespace: shop
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: order-api
  minReplicas: 2
  maxReplicas: 10
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 70
~~~

HPA CPU utilization dựa trên **CPU requests** và hệ thống cung cấp metrics phù hợp (ví dụ metrics-server). Nếu không có requests hoặc không có metrics, HPA có thể không tính scale theo mong muốn. HPA phản ứng có độ trễ, không thay queueing/backpressure và thiết kế capacity.

Khi tăng replicas:

1. HPA/controller thay desired replica count.
2. Deployment/ReplicaSet tạo thêm Pods.
3. Scheduler cần đủ node resources.
4. Pod mới kéo image, khởi động, đạt readiness.
5. Endpoint list cập nhật; traffic mới có thể đi tới backend mới.

**Scale-out không tức thì.** Nếu startup mất 90 giây và traffic tăng đột ngột, cần cân nhắc min replicas, resource requests, cluster autoscaler và giới hạn downstream. Scale Order API gấp 10 lần mà database pool hoặc Payment API không tăng tương ứng có thể gây overload.

### 24.1. HPA và lệnh scale thủ công

Khi HPA quản lý replicas, việc chỉnh **Deployment.spec.replicas** thủ công có thể bị HPA ghi lại theo điều kiện điều khiển. Cần phân định ownership của replicas và deployment configuration để tránh controllers “giằng co”.

### 24.2. PodDisruptionBudget

**PodDisruptionBudget (PDB)** giới hạn số Pod có thể bị gián đoạn bởi một số hành động **voluntary eviction** trong các điều kiện áp dụng. Nó không bảo vệ tuyệt đối khỏi node crash, application bug hoặc mọi hình thức Pod deletion. Kết hợp replicas, readiness, topology spread và rolling updates để giảm ảnh hưởng downtime.

## 25. Scheduling và resource management ảnh hưởng tới định tuyến

Nếu Pod nằm ở trạng thái **Pending**, Service không thể gửi traffic tới backend chưa chạy/ready. Những nguyên nhân:

- Requests CPU/RAM vượt capacity node khả dụng.
- Node selector/affinity quá chặt.
- Taints chưa có tolerations phù hợp.
- PVC chưa bind/mount được.
- Không phù hợp topology/zone hoặc constraint khác.

**Resources.requests** dùng để scheduler ước lượng tài nguyên đặt Pod. **Limits** giới hạn tài nguyên theo cơ chế thực thi tương ứng; với memory limit, ứng dụng vượt giới hạn có thể bị OOMKilled. CPU throttling hoặc memory pressure làm tăng latency, dẫn đến readiness/liveness không ổn định.

Không chạy mọi replica của Payment API trên một node nếu yêu cầu chịu lỗi node. Có thể dùng **topologySpreadConstraints** hoặc pod anti-affinity được thiết kế hợp lý, đồng thời cân bằng với khả năng schedule khi cluster ít node.

Kubernetes controller bảo đảm desired state theo khả năng cluster; nó **không thể tự tạo năng lực tính toán vô hạn**.

## 26. Graceful shutdown và traffic draining

Khi Deployment rollout, Pod cũ có thể nhận tín hiệu termination. Nếu Java process đóng ngay trong khi có request thanh toán đang xử lý, client sẽ gặp lỗi hoặc retry không kiểm soát.

Một lộ trình an toàn thường gồm:

1. Pod bắt đầu termination; Kubernetes cập nhật điều kiện endpoint theo cơ chế tương ứng.
2. Ứng dụng hoặc lifecycle hook ngăn nhận công việc mới trong phạm vi có thể kiểm soát.
3. Các kết nối/in-flight requests được xử lý hoặc đóng có kiểm soát.
4. Consumer/worker hoàn tất checkpoint hoặc chuyển việc lại một cách an toàn.
5. Container kết thúc trước khi hết **terminationGracePeriodSeconds**; nếu không, kubelet có thể buộc dừng.

Một số hệ thống cần **preStop hook** hoặc graceful shutdown configuration của Spring Boot, nhưng không nên chỉ thêm **sleep 30** rồi coi đã bảo đảm zero downtime. Phải xét độ trễ propagation endpoint, keep-alive, LB target drain, readiness, request budget và tính idempotent ở client.

**Không có bảo đảm mọi connection cũ sẽ lập tức chuyển sang Pod khác** khi endpoint bị remove. Client retry cho request không idempotent phải có idempotency key/operation state để tránh tạo đơn hoặc thanh toán hai lần.

## 27. Tính sẵn sàng cao: Replica không bảo đảm HA hoàn chỉnh

Một Deployment có 3 replicas chỉ có HA thực chất nếu:

- Replica được schedule phân tán trên failure domains đủ độc lập.
- Service có các endpoints ready, network route hoạt động.
- Dependency bắt buộc như DB/secret provider/config không là single point of failure ngoài chính sách.
- Database/state có cơ chế backup, replication hoặc recovery thích hợp.
- Rollout không làm cả 3 replicas not-ready cùng lúc.
- Autoscale và resource quotas đủ khả năng xử lý peak traffic.

Nếu cả ba Pod chạy trên một node, node chết sẽ khiến cả ba mất cùng lúc. Nếu mỗi Pod gọi một database đơn lẻ đang down, có 100 Pod cũng không giúp giao dịch database thành công.

**Kubernetes cấp primitive về orchestration; application architecture vẫn chịu trách nhiệm availability, data consistency và failure semantics.**

## 28. Security boundaries: Namespace, RBAC, ServiceAccount, NetworkPolicy

Các khái niệm dễ nhầm:

- **Namespace:** phạm vi logic để đặt tên, áp chính sách/quota và tổ chức tài nguyên. Không tự bảo đảm cách ly mạng/tenant toàn diện.
- **RBAC:** ai được gọi Kubernetes API để xem/sửa Deployment, Secrets, Pods... Không trực tiếp quyết định user cuối có quyền gọi Order API.
- **ServiceAccount:** danh tính mà workload có thể sử dụng khi tương tác Kubernetes API hoặc cơ chế workload identity liên quan.
- **NetworkPolicy:** cho phép/chặn traffic giữa các Pod/IP theo network plugin.
- **Pod Security:** các chuẩn/điều kiện liên quan quyền container, privilege, host namespaces, seccomp, capabilities, tùy cơ chế admission.
- **Application authorization:** JWT/session/mTLS identity và business policy ở Order/Payment API.

Một Pod không cần dùng Kubernetes API thường có thể đặt **automountServiceAccountToken: false** để giảm tiếp xúc token, nếu không có integration khác yêu cầu. Ví dụ bảo mật container:

~~~yaml
spec:
  automountServiceAccountToken: false
  securityContext:
    runAsNonRoot: true
    seccompProfile:
      type: RuntimeDefault
  containers:
    - name: order-api
      image: registry.example.com/shop/order-api:1.4.2
      securityContext:
        allowPrivilegeEscalation: false
        capabilities:
          drop: ["ALL"]
~~~

Đây là **trích đoạn minh họa** cần đặt vào Pod spec hợp lệ; image phải hỗ trợ non-root và quyền filesystem tương ứng. Không copy vào Pod cần Kubernetes API token mà không hiểu nhu cầu. Cần kết hợp RBAC tối thiểu, NetworkPolicy, Secret management, image provenance, admission policy, TLS và application authorization.

**Service port mở được không có nghĩa được phép truy cập business data.** Đừng tin user identity từ HTTP header do client tùy ý đặt nếu chưa có trust boundary bảo vệ.

## 29. Những trạng thái Pod thường gặp và ý nghĩa

| Trạng thái/tín hiệu | Gợi ý điều tra |
|---|---|
| **Pending** | Chưa được schedule/mount; kiểm tra events, node resources, PVC, affinity |
| **ContainerCreating** | Kubelet đang chuẩn bị sandbox/volume/image; kiểm tra node/runtime/network |
| **ImagePullBackOff** | Không kéo được image hoặc credential/registry lỗi |
| **CrashLoopBackOff** | Process exit lặp, restart backoff; xem logs trước đó và exit code |
| **OOMKilled** | Vượt memory limit hoặc bị memory pressure; xem limits/heap/metaspace |
| **Running nhưng not Ready** | Process chạy nhưng readiness fail hoặc app chưa đáp ứng |
| **Terminating kéo dài** | PreStop, finalizers, graceful shutdown, volume/network detach |
| **Succeeded/Completed** | Thường đúng với Job, không phải trạng thái cần duy trì cho API dài hạn |
| **Service không có endpoints** | Selector không khớp, Pod chưa ready hoặc controller/EndpointSlice issue |
| **Ingress 404/503** | Kiểm tra host/path rule, controller, Service endpoints, backend health |

Một Pod có phase **Running** nhưng **READY 0/1** là dấu hiệu quan trọng: không nên suy ra Service sẽ route traffic đúng chỉ từ Running.

## 30. Quy trình debug khi Service không gọi được Pod

Thay vì sửa ngẫu nhiên, đi theo checklist có thứ tự.

### Bước 1: Xác nhận namespace và tên

~~~bash
kubectl get namespaces
kubectl get svc order-api -n shop -o wide
kubectl get deployment order-api -n shop
~~~

Lỗi phổ biến: client ở namespace **billing** gọi **order-api** rồi DNS search tới Service cùng tên ở **billing**, trong khi đích nằm ở **shop**.

### Bước 2: Xác nhận labels/selectors

~~~bash
kubectl get svc order-api -n shop -o yaml
kubectl get pods -n shop -l app=order-api --show-labels
~~~

Nếu Service selector **app=order-api** nhưng pods có **app=orders-api**, sẽ không có endpoints phù hợp. Sửa nơi quản lý manifest theo đúng release, không vá trực tiếp một Pod do Deployment tạo rồi quên cập nhật template.

### Bước 3: Xem EndpointSlices

~~~bash
kubectl get endpointslices -n shop \
  -l kubernetes.io/service-name=order-api -o wide
~~~

Nếu không có địa chỉ backend ready, kiểm tra Pod readiness và selector. Nếu có nhưng port sai, kiểm tra targetPort và tên container port.

### Bước 4: Xem Pod readiness, events và logs

~~~bash
kubectl get pods -n shop -l app=order-api
kubectl describe deployment order-api -n shop
kubectl describe pod <pod-name> -n shop
kubectl logs <pod-name> -n shop --previous
~~~

**--previous** hữu ích khi container đã restart và vẫn có log của lần chạy trước; không phải Pod nào cũng có previous logs.

### Bước 5: Kiểm tra DNS, network và ứng dụng

Từ debug Pod có quyền, kiểm tra nslookup và curl tới Service DNS. Nếu đã tới ứng dụng nhưng trả 401/403/5xx, phân tích app security/dependency logs thay vì thay cấu hình kube-proxy.

### Bước 6: Kiểm tra ingress/controller nếu lỗi chỉ xuất hiện từ ngoài

~~~bash
kubectl get ingress -n shop
kubectl describe ingress shop-public -n shop
~~~

Xác nhận IngressClass/controller, DNS public, TLS secret, host/path matching, ingress controller logs và tuyến backend. Có thể Gateway controller thực hiện route theo endpoint trực tiếp nên cần xem cấu hình controller thực tế.

### Bước 7: Ghi lại bằng chứng

Lưu tên Deployment/Pod, namespace, Service selector, EndpointSlice, readiness failures, version image, events, request path và traceId. Không paste token/Secrets vào ticket.

## 31. Các anti-pattern thường gặp

**1. Gọi thẳng Pod IP.** Khi Pod bị thay, client mất endpoint. Dùng Service/discovery phù hợp.

**2. Tạo bare Pod cho production API.** Không có Deployment/StatefulSet/Job quản lý lifecycle theo yêu cầu.

**3. Dùng StatefulSet cho mọi service vì muốn tên Pod ổn định.** Tăng coupling không cần thiết; API stateless nên thường dùng Deployment.

**4. Coi Service tự scale Pod.** Service chọn endpoint, Deployment/HPA điều khiển replica count.

**5. Selector không khớp labels.** Service tồn tại nhưng không có backend; kiểm tra EndpointSlices.

**6. Nhầm port và targetPort.** Service trả DNS/IP nhưng kết nối bị từ chối do cổng sai.

**7. Chỉ kiểm tra Pod Running.** Pod có thể chưa ready. Phân biệt startup, liveness, readiness.

**8. Dùng liveness kiểm tra tất cả downstream.** Một outage nhỏ gây restart storm và làm sự cố lan rộng.

**9. Cho rằng ClusterIP route theo HTTP path.** Service chủ yếu ở lớp mạng/transport; dùng Ingress/Gateway/L7 proxy cho host/path routing.

**10. Cho rằng NetworkPolicy tự tồn tại và tự thực thi.** Cần manifest, CNI hỗ trợ và chính sách đúng nguồn/đích.

**11. Dùng NodePort như public API gateway mặc định.** Không tự có TLS, rate limit, auth, WAF và operational policy.

**12. Đặt mọi replicas trên một node.** Mất node đồng nghĩa mất mọi replica; xét topology/failure domains.

**13. Update image mà không readiness/graceful shutdown.** Có thể gửi traffic vào Pod chưa khởi tạo xong hoặc cắt request của Pod cũ.

**14. Giả định Pod volume là database bền vững.** Dữ liệu có thể mất khi Pod được thay; thiết kế persistence riêng.

**15. Scale API nhưng bỏ qua DB/queue và connection budgets.** Downstream bị quá tải; triển khai backpressure và capacity planning.

**16. Dùng một HTTP retry chung cho mọi POST.** Có thể gây side effect trùng; cần idempotency key khi phù hợp.

## 32. Bộ tình huống luyện tập

### Tình huống A: Hai Pod đều Running nhưng client nhận 503

Đã có Deployment replicas=2 và Service **order-api**, nhưng EndpointSlice không có backend ready.

Điều tra nên bắt đầu từ **readiness probe**, **selector** và **targetPort**. Nếu readiness fail vì database chưa sẵn sàng thì tăng replicas không giúp. Nếu selector sai, sửa manifest Service hoặc Deployment labels đúng nguồn quản lý.

### Tình huống B: Pod mới rollout xong nhưng timeout tăng mạnh

Deployment đã scale từ 2 lên 10 Pod. Lượng connection tới PostgreSQL tăng vì mỗi Pod có pool size=30: tổng khả năng connection từ ứng dụng có thể tăng từ khoảng 60 lên 300 trước khi tính process khác.

**Kubernetes scale thêm Pod không tự scale database.** Cần tính connection pool budget, saturation, request queue và SLO. Có thể đặt giới hạn pool, dùng proxy/pooling phù hợp hoặc thay chiến lược autoscale.

### Tình huống C: API chỉ lỗi qua public hostname

**kubectl port-forward svc/order-api** hoạt động, nhưng **https://shop.example.com/orders** trả 404.

Điều đó gợi ý ứng dụng/Service có thể hoạt động qua đường debug; cần xem **Ingress host/path rules**, HTTP method, TLS, rewrite, controller logs và DNS. Port-forward không xác nhận public ingress route.

### Tình huống D: Tất cả Pod bị restart khi Payment Service down

Liveness probe Order API gọi Payment API, nên khi Payment down, kubelet kết luận Order unhealthy và restart toàn bộ Order Pod.

Cần **tách liveness của process khỏi availability của downstream**. Readiness/degraded mode và circuit breaker nên phản ánh những dependency thực sự quyết định khả năng phục vụ; không dùng restart như giải pháp cho outage của hệ thống khác.

### Tình huống E: StatefulSet có ba Pod nhưng dữ liệu không replicate

Ba Pod **db-0**, **db-1**, **db-2** tồn tại với ba PVC riêng. Tuy nhiên database process chưa cấu hình replication/quorum.

StatefulSet bảo đảm một số thuộc tính về **identity và lifecycle**, không tự thiết lập replication. Cần operator hoặc cấu hình database phù hợp, backup/recovery và quy trình failover.

### Tình huống F: Worker gửi cùng email hai lần

CronJob chạy lại sau sự cố node; handler xử lý lại cùng một business event. Đó không nhất thiết là bug Kubernetes: scheduling/retry là at-least-once ở nhiều tình huống thực tế. Thiết kế **deduplication/idempotency bằng business key**, giao dịch và audit để không gửi tác dụng phụ trùng.

## 33. Kiểm tra bằng CI/CD và thử nghiệm rollout

Trước khi triển khai, pipeline nên:

1. Validate schema Kubernetes API của Deployment/Service/Ingress/Gateway/NetworkPolicy.
2. Kiểm tra Service selector khớp labels trong Pod template do team sở hữu.
3. Kiểm tra targetPort, container port names và application port configuration.
4. Xác nhận health endpoints có tồn tại và phản ánh đúng readiness/liveness.
5. Scan container image, IaC policy, Secret reference và quyền ServiceAccount.
6. Kiểm tra resource requests/limits theo budget, không mở privileged mode không cần.
7. Chạy integration tests với dependency chính và smoke tests qua Service.
8. Triển khai ở staging, kiểm tra rollout status, EndpointSlice và access nội bộ.
9. Kiểm tra public hostname/path/TLS thông qua đúng Ingress/Gateway implementation.
10. Mô phỏng Pod termination/rollout khi có request in flight.
11. Đo latency/error rate trước/sau khi tăng giảm replica.
12. Kiểm tra NetworkPolicy deny/allow theo nguồn hợp lệ.
13. Đảm bảo có rollback/roll-forward strategy và cấu hình migration tương thích.

**Sau deploy**, quan sát số desired/available replicas, Pod restart, OOM, HPA decisions, ingress 4xx/5xx, service latency p95/p99, network drops và downstream saturation. Tự động rollback chỉ nên dựa trên tín hiệu đủ tin cậy, tránh loop rollout không kết thúc.

## 34. Bảng đối chiếu nhanh

| Câu hỏi | Thành phần cần nhìn đầu tiên |
|---|---|
| Một Pod có những container nào và chia sẻ network ra sao? | **Pod spec** |
| Ai duy trì ba replica Order API? | **Deployment → ReplicaSet** |
| Ai quyết định Pod chạy trên node nào? | **Scheduler**, node constraints |
| API cần stable hostname nội bộ? | **Service + DNS** |
| Service thực sự có backend nào? | **EndpointSlice**, selector, Pod readiness |
| Cần truy cập từ Internet theo hostname/path? | **Ingress/Gateway + controller + edge LB** |
| Cần một agent mỗi node? | **DaemonSet** |
| Cần chạy tác vụ hữu hạn? | **Job** |
| Cần chạy tác vụ theo lịch? | **CronJob** |
| Cần identity và storage riêng từng replica? | **StatefulSet + headless Service/PVC** |
| Muốn tự scale theo tải? | **HPA** và metrics/capacity |
| Muốn chặn Pod-to-Pod traffic không hợp lệ? | **NetworkPolicy + CNI hỗ trợ** |
| Muốn kiểm soát ai sửa Kubernetes API? | **RBAC / ServiceAccount / admission** |
| Muốn kiểm soát user được xem đơn nào? | **Authorization trong ứng dụng** |
| Muốn biết vì sao request chậm? | **Metrics + logs + distributed traces** |

## 35. Checklist quyết định khi thiết kế một microservice

Trước khi tạo manifest production, trả lời:

1. Service là **HTTP API lâu dài**, background worker, Job, CronJob hay ứng dụng có state?
2. Có cần tự động giữ **replicas** và rolling update không? Nếu có, controller nào?
3. Pod lưu trạng thái gì? Những dữ liệu nào cần persistence ở ngoài Pod?
4. Labels của Pod và selector của Service có được version/review nhất quán?
5. Client cần stable hostname nội bộ hay public host/path route?
6. Cần **ClusterIP**, LoadBalancer, Ingress/Gateway hay headless discovery?
7. App nghe port nào? **Service port/targetPort/containerPort** có khớp?
8. Readiness có phản ánh chính xác khả năng nhận traffic?
9. Liveness có tránh phụ thuộc quá mức vào downstream?
10. Startup time và graceful termination có phù hợp traffic/SLO?
11. Resource requests/limits và failure domains có đủ cho HA?
12. HPA có đúng metrics và requests cần thiết không?
13. NetworkPolicy, mTLS, RBAC, Secrets và application authorization có ranh giới rõ không?
14. Nếu một Pod/node/zone chết, request và dữ liệu được xử lý thế nào?
15. Nếu rollout phải rollback, schema và config cũ/mới có tương thích không?
16. Có thể từ **DNS → Service → EndpointSlice → Pod → app** xác định nơi traffic bị chặn bằng lệnh/telemetry thực tế không?

## 36. Kết luận

Kubernetes tổ chức microservices bằng những abstraction có trách nhiệm tách biệt:

- **Pod** là nơi container được chạy cùng nhau và chia sẻ network identity ở mức Pod; Pod thường có vòng đời ngắn.
- **Workload controller** biến yêu cầu về replicas, lifecycle, stateful identity hoặc lịch tác vụ thành các Pod đang chạy.
- **Service** tạo điểm truy cập ổn định và liên kết tới tập endpoints thay đổi; **EndpointSlice** phản ánh các backend thực tế.
- **DNS, CNI/service routing, Ingress/Gateway** đưa kết nối và request vào đúng đường đi theo lớp phù hợp.
- **Readiness, probes, resource scheduling, NetworkPolicy và observability** quyết định ứng dụng có thể phục vụ an toàn khi deploy, scale và gặp lỗi hay không.

**Câu hỏi kiểm tra cuối:** *Khi Order API đang có ba Pod, một node mất điện và Deployment tạo lại Pod với IP mới, vì sao Payment Service vẫn có thể gọi tên order-api.shop.svc mà không cần cập nhật danh sách Pod IP thủ công?*

Câu trả lời nằm ở sự phối hợp của **controller duy trì Pod**, **Service giữ identity mạng**, **EndpointSlice cập nhật backend** và **data plane định tuyến tới các endpoint phù hợp, thường dựa trên readiness**. Hiểu được chuỗi này là nền tảng để thiết kế, triển khai và gỡ lỗi Kubernetes microservices.
