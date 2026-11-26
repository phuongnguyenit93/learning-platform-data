# Cluster, control plane, node và Kubernetes API

## 1. Bức tranh tổng thể

Kubernetes là hệ thống điều phối container. Người dùng khai báo trạng thái mong muốn, Kubernetes lưu trạng thái đó, quan sát trạng thái thực tế và liên tục điều chỉnh để hai trạng thái tiến gần nhau.

Một cluster gồm hai nhóm vai trò:

1. **Control plane** tiếp nhận yêu cầu, lưu trạng thái và điều khiển các thay đổi.
2. **Node** cung cấp CPU, memory, mạng và container runtime để chạy Pod.

Ranh giới này là ranh giới logic. Cluster nhỏ có thể dùng một máy cho cả control plane và workload; môi trường sản xuất thường tách chúng để giảm tranh chấp tài nguyên và giảm tác động dây chuyền khi workload gặp sự cố.

~~~text
                         Kubernetes cluster
       +--------------------------------------------------+
       |                  Control plane                   |
       | API server | scheduler | controllers | datastore |
       +-------------------------+------------------------+
                                 |
                         Kubernetes API
                                 |
       +-------------------------+------------------------+
       |                         Nodes                    |
       | kubelet + runtime + network + Pods               |
       | kubelet + runtime + network + Pods               |
       +--------------------------------------------------+
~~~

Một lệnh kubectl apply có thể thành công trước khi container thực sự chạy. API server chấp nhận đối tượng, controller tạo tài nguyên con, scheduler chọn node, kubelet khởi chạy container và readiness probe xác nhận khả năng phục vụ là các bước khác nhau.

Hiểu chuỗi này là nền tảng để tích hợp ứng dụng Spring với DiscoveryClient, ConfigMap, Secret, Spring Cloud LoadBalancer và Configuration Watcher. Mỗi integration có thể dùng Kubernetes API, nhưng gọi Kubernetes API là một nhu cầu khác với gọi một HTTP Service trong cluster.

## 2. Cluster, control plane và node

### 2.1. Cluster

Cluster là tập hợp các máy được Kubernetes quản lý như một môi trường thống nhất. Cluster cung cấp API, cơ chế điều phối, mạng Pod, DNS và các tài nguyên để chạy workload.

Cluster không phải một máy chủ duy nhất. Pod có thể được lập lịch trên nhiều node, trong khi trạng thái của chúng được điều khiển từ control plane. Khi một Pod bị lỗi, Kubernetes có thể tạo Pod thay thế trên node khác nếu các ràng buộc và tài nguyên cho phép.

### 2.2. Control plane

Control plane duy trì trạng thái của cluster. Các thành phần chính thường có vai trò sau:

| Thành phần | Vai trò |
| --- | --- |
| kube-apiserver | Cổng HTTP của Kubernetes API; xác thực, phân quyền, admission và phục vụ resource |
| Kho dữ liệu control plane | Lưu trạng thái resource và thông tin cần cho việc điều khiển cluster |
| kube-scheduler | Chọn node cho Pod chưa được gán node |
| Controller manager | Chạy các vòng lặp reconciliation để đưa trạng thái thực tế về trạng thái mong muốn |

Tên và cách đóng gói các thành phần có thể khác giữa các bản phân phối, nhưng mô hình trách nhiệm vẫn tương tự.

### 2.3. Node

Node là máy có thể chạy Pod. Các thành phần quan trọng gồm:

- **Kubelet** nhận Pod được gán cho node, yêu cầu runtime tạo container, thực hiện probe và cập nhật status.
- **Container runtime** kéo image, tạo sandbox, khởi chạy và dừng container.
- **Thành phần mạng** cung cấp kết nối Pod, Service và DNS theo cách triển khai của cluster.

Kubelet không phải scheduler. Nó không tự chọn Pod nào thuộc node nào. Kubelet cũng không biến container đang chạy thành Service; Service là một resource API và đường dữ liệu của Service do các thành phần mạng của cluster cung cấp.

Ứng dụng Spring nên dựa trên hợp đồng ổn định như tên DNS của Service, cổng Service và trạng thái readiness. Ứng dụng không nên phụ thuộc vào cách một bản phân phối cụ thể hiện thực proxy hoặc dataplane.

## 3. Vai trò của control plane

### 3.1. kube-apiserver

kube-apiserver cung cấp Kubernetes API qua HTTP. kubectl, scheduler, controller và các ứng dụng được cấp quyền đều trao đổi với cluster qua API server.

Một request thường trải qua các lớp:

1. Xác thực danh tính, chẳng hạn certificate hoặc token.
2. Phân quyền bằng RBAC và các authorizer được cấu hình.
3. Admission để kiểm tra, mặc định hóa hoặc biến đổi đối tượng.
4. Đọc hoặc ghi trạng thái qua kho dữ liệu control plane.
5. Trả kết quả hoặc giữ watch để client nhận thay đổi.

Ứng dụng Spring nhìn thấy API server không có nghĩa là được phép đọc mọi resource. ServiceAccount có danh tính và quyền riêng. Quyền get một ConfigMap trong một namespace khác với quyền list mọi Secret trong toàn cluster.

### 3.2. Kho dữ liệu

Trong cluster Kubernetes chuẩn, etcd thường giữ trạng thái resource phía sau API server. Ứng dụng không nên truy cập trực tiếp kho dữ liệu này. Mọi thao tác cần đi qua API server để được xác thực, phân quyền và áp dụng chính sách.

API server lưu một Deployment chưa có nghĩa container đã chạy. Deployment controller và ReplicaSet controller mới biến khai báo đó thành Pod; scheduler gán Pod vào node; kubelet và runtime khởi chạy container.

### 3.3. Scheduler

Scheduler theo dõi Pod chưa được gán node và tìm node phù hợp dựa trên:

- CPU và memory yêu cầu;
- taint của node và toleration của Pod;
- nodeSelector hoặc node affinity;
- topology spread và anti-affinity;
- các ràng buộc tài nguyên hoặc policy khác.

Scheduler chỉ đưa ra quyết định gán node. Nó không trực tiếp kéo image và không chạy process trong container. Quyết định được ghi qua API, sau đó kubelet trên node tương ứng tiếp nhận Pod.

### 3.4. Controller

Controller quan sát resource rồi thực hiện reconciliation. Ví dụ:

- Deployment controller quản lý ReplicaSet.
- ReplicaSet controller duy trì số lượng Pod.
- Node controller phản ứng khi node mất liên lạc.
- Job controller theo dõi số lần chạy hoàn thành.

Controller không phải script chạy một lần sau khi apply. Nếu một Pod bị xóa trong khi Deployment vẫn yêu cầu hai replica, controller sẽ thấy trạng thái thực tế thiếu Pod và yêu cầu tạo Pod thay thế.

## 4. Pod và vòng đời workload

Pod là đơn vị nhỏ nhất Kubernetes lập lịch. Một Pod có thể có một hoặc nhiều container dùng chung network namespace và có thể dùng chung volume. Mẫu phổ biến cho ứng dụng Spring là một container ứng dụng trong mỗi Pod.

~~~yaml
apiVersion: v1
kind: Pod
metadata:
  name: catalog
  namespace: shop
  labels:
    app: catalog
spec:
  containers:
    - name: catalog
      image: registry.example.com/catalog:1.0.0
      ports:
        - name: http
          containerPort: 8080
~~~

Trong triển khai thực tế, Deployment thường được dùng để tạo Pod, mở rộng replica và cập nhật theo rollout. Pod có IP riêng nhưng IP có thể đổi khi Pod bị thay thế. Client không nên lưu IP Pod làm địa chỉ lâu dài; Service cung cấp tên và điểm truy cập ổn định hơn.

Với Deployment sau:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: catalog
  namespace: shop
spec:
  replicas: 2
  selector:
    matchLabels:
      app: catalog
  template:
    metadata:
      labels:
        app: catalog
    spec:
      containers:
        - name: catalog
          image: registry.example.com/catalog:1.0.0
          ports:
            - name: http
              containerPort: 8080
          readinessProbe:
            httpGet:
              path: /actuator/health/readiness
              port: http
~~~

Luồng chính là:

1. Client gửi Deployment đến API server.
2. API server xác thực, phân quyền, chạy admission nếu có rồi lưu đối tượng.
3. Deployment controller tạo hoặc cập nhật ReplicaSet.
4. ReplicaSet controller tạo hai Pod theo template.
5. Scheduler chọn node cho các Pod chưa được gán.
6. Kubelet yêu cầu runtime kéo image và khởi chạy container.
7. Kubelet chạy readiness probe và cập nhật status.
8. Khi Pod sẵn sàng, EndpointSlice của Service có thể nhận Pod làm backend.

kubectl apply thành công thường chỉ xác nhận API server đã chấp nhận object. Nó không bảo đảm endpoint HTTP đã sẵn sàng.

## 5. Kubernetes API và resource

### 5.1. Cấu trúc resource

Một object API thường có apiVersion, kind, metadata và phần đặc tả riêng. Deployment thuộc nhóm apps; Service và ConfigMap thuộc core API.

~~~yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: catalog-settings
  namespace: shop
data:
  catalog.timeout-ms: "800"
~~~

metadata.name xác định tên trong namespace. metadata.namespace chỉ có ở resource namespaced. Node là ví dụ resource cấp cluster và không thuộc một namespace.

### 5.2. Spec và status

spec biểu đạt trạng thái mong muốn. status phản ánh quan sát hiện tại. Deployment có thể yêu cầu hai replica trong spec nhưng status tạm thời cho biết chỉ một replica Available.

Khi chẩn đoán, cần xem cả hai phía. Selector không khớp label của Pod template sẽ khiến controller quản lý sai. Spec đúng nhưng status chưa đạt có thể dẫn đến scheduler, image, runtime, probe, mạng hoặc ứng dụng.

### 5.3. Get, list và watch

Client có thể:

- get một object;
- list một tập object;
- watch sự kiện thay đổi.

Watch giúp controller và integration component phản ứng với thay đổi mà không phải liên tục tải lại toàn bộ danh sách. Tuy nhiên, watch có thể bị đóng do kết nối, resource version hoặc lỗi API. Component cần reconnect và xử lý trạng thái nhất quán.

Khi Spring Cloud Kubernetes dùng API cho discovery, ConfigMap, Secret hoặc Configuration Watcher, mỗi thao tác là request có danh tính và quyền. Có quyền get một ConfigMap không tự động có quyền watch mọi ConfigMap trong namespace.

## 6. Kubernetes API khác với đường gọi Service

Hai đường sau cần được phân biệt:

| Nhu cầu | Đường đi chính | Thành phần hoặc quyền |
| --- | --- | --- |
| checkout gọi HTTP đến orders | DNS nội bộ → ClusterIP → endpoint Pod | Service, readiness, mạng và API nghiệp vụ |
| Đọc danh sách Service hoặc Pod | Ứng dụng → Kubernetes API | Authentication và RBAC |
| Đọc cấu hình bằng API | Ứng dụng → Kubernetes API | get, list hoặc watch trên ConfigMap/Secret |
| Theo dõi resource thay đổi | Ứng dụng → Kubernetes API bằng watch | watch, reconnect và xử lý resource version |
| Gọi API để chẩn đoán | kubectl → Kubernetes API | Quyền của người vận hành |

Nếu checkout chỉ gọi http://orders:8080 thì không cần liệt kê Pod để tìm IP. Service và DNS đã đảm nhiệm việc định địa chỉ. Nếu ứng dụng cần chọn instance theo metadata hoặc cần biết các endpoint riêng lẻ, khi đó mới đánh giá DiscoveryClient và quyền API phù hợp.

Phân biệt này ảnh hưởng trực tiếp đến bảo mật. Không cấp list và watch Pod cho mọi ứng dụng chỉ vì ứng dụng chạy trong Kubernetes. Bắt đầu bằng câu hỏi: ứng dụng có thật sự gọi Kubernetes API không, nó cần resource nào và cần verb nào?

## 7. Service, DNS và trạng thái Pod

Service cung cấp điểm truy cập ổn định cho một tập Pod. Selector chọn Pod theo label; EndpointSlice biểu diễn các endpoint được phát hiện. Readiness probe ảnh hưởng đến việc Pod có được xem là backend sẵn sàng hay không.

~~~text
checkout Pod
    |
    | http://orders.shop:8080
    v
DNS Service trong cluster
    |
    v
orders ClusterIP
    |
    v
EndpointSlice của Service orders
    |
    +--> orders Pod A (Ready)
    +--> orders Pod B (Ready)
    +--> orders Pod C (NotReady)
~~~

Kubernetes API cung cấp thông tin về Service, Pod và EndpointSlice; DNS và dataplane thực hiện đường gọi runtime. Một HTTP client không cần đọc API cho mỗi request.

Các lỗi thường bị trộn lẫn:

- Không phân giải được tên: kiểm tra tên Service, namespace, DNS policy và đường đến DNS.
- DNS phân giải được nhưng timeout: kiểm tra NetworkPolicy, endpoint, route và backend.
- Kết nối bị từ chối: kiểm tra cổng Service, targetPort và ứng dụng có lắng nghe không.
- HTTP 503: xem log, endpoint và khả năng API đích không có backend sẵn sàng.
- Pod Running nhưng chưa Ready: container đang chạy nhưng chưa đủ điều kiện phục vụ.

Running là trạng thái vòng đời Pod hoặc container. Ready là tín hiệu phục vụ traffic theo probe và điều kiện workload. Không dùng một trạng thái để suy ra trạng thái kia.

## 8. ServiceAccount và RBAC

### 8.1. Danh tính của Pod

Pod có thể chạy với ServiceAccount. Token hoặc thông tin định danh được cung cấp theo cấu hình cluster; client Kubernetes trong ứng dụng có thể dùng danh tính này để gọi API.

~~~yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: catalog-reader
  namespace: shop
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: catalog
  namespace: shop
spec:
  template:
    spec:
      serviceAccountName: catalog-reader
      containers:
        - name: catalog
          image: registry.example.com/catalog:1.0.0
~~~

ServiceAccount là danh tính, chưa tự cấp quyền. Quyền được tạo bằng Role hoặc ClusterRole và gắn vào danh tính qua RoleBinding hoặc ClusterRoleBinding.

### 8.2. Role giới hạn namespace

Nếu ứng dụng chỉ đọc ConfigMap trong namespace shop:

~~~yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: catalog-config-reader
  namespace: shop
rules:
  - apiGroups: [""]
    resources: ["configmaps"]
    verbs: ["get", "list", "watch"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: catalog-config-reader
  namespace: shop
subjects:
  - kind: ServiceAccount
    name: catalog-reader
    namespace: shop
roleRef:
  kind: Role
  name: catalog-config-reader
  apiGroup: rbac.authorization.k8s.io
~~~

apiGroups: [""] là nhóm core API, nơi có ConfigMap và Secret. Quyền đọc Secret cần được giới hạn vì có thể cho phép tiếp cận dữ liệu nhạy cảm.

Không thêm create, update, patch hoặc delete nếu component chỉ cần đọc. Không dùng ClusterRoleBinding khi phạm vi đúng chỉ là một namespace.

### 8.3. Quyền cho Discovery và watcher

DiscoveryClient dựa trên Kubernetes có thể cần đọc Service và EndpointSlice hoặc resource tương đương, tùy cách triển khai. Component đọc ConfigMap cần quyền trên ConfigMap. Configuration Watcher cần quyền watch resource mà nó theo dõi. Quyền thực tế phải khớp với cách thư viện và phiên bản dependency truy cập API.

| Câu hỏi | Ví dụ |
| --- | --- |
| Đọc loại resource nào? | ConfigMap trong namespace shop |
| Đọc object hay danh sách? | get một tên cụ thể hoặc list/watch theo phạm vi |
| Phạm vi ở đâu? | Một namespace hay toàn cluster |
| Vì sao cần quyền? | Nạp cấu hình, discovery hoặc theo dõi thay đổi |
| API tạm thời không truy cập được? | Dùng giá trị đã nạp, retry có giới hạn hoặc fail startup |

RBAC kiểm soát gọi Kubernetes API. Nó không tự mở cổng mạng đến Service và không thay thế xác thực của API nghiệp vụ giữa hai ứng dụng.

## 9. Ví dụ tích hợp Spring Cloud Kubernetes

Giả sử ứng dụng catalog cần đọc một ConfigMap chứa thời gian timeout và phản ứng khi cấu hình đổi. Thiết kế nên tách:

1. Cấu hình Kubernetes: ConfigMap, ServiceAccount, Role và RoleBinding.
2. Cấu hình Spring Cloud Kubernetes: bật đúng integration và xác định namespace.
3. Chính sách ứng dụng: bean nào được cập nhật, request đang chạy xử lý ra sao và cấu hình sai được rollback hay làm ứng dụng dừng.

~~~yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: catalog-settings
  namespace: shop
data:
  catalog.timeout-ms: "800"
  catalog.feature-recommendation: "true"
~~~

Ứng dụng có thể nhận dữ liệu qua environment hoặc volume mà không cần tự gọi Kubernetes API. Nếu dùng integration dựa trên API để đọc và watch ConfigMap, ServiceAccount phải có quyền tương ứng. Hai mô hình có khác biệt về thời điểm cập nhật và cách ứng dụng nạp lại.

Ví dụ cấu hình ở mức khái niệm:

~~~yaml
spring:
  application:
    name: catalog
  cloud:
    kubernetes:
      discovery:
        enabled: false
      config:
        enabled: true
        name: catalog-settings
~~~

Đây là ví dụ kiến trúc. Tên property, starter và cơ chế reload phải khớp phiên bản Spring Cloud Kubernetes của dự án. Khi chỉ cần gọi Service qua DNS, không cần bật discovery chỉ để phân giải tên orders.

Nếu cần DiscoveryClient, hãy xác định ứng dụng cần danh sách Service, endpoint hay metadata nào. Nếu cần Spring Cloud LoadBalancer, hãy xác định nguồn instance và xem việc chọn ở client có kiểm soát backend cuối cùng hay không. Nếu cần Configuration Watcher, hãy thiết kế reconnect, validation và hành vi khi cấu hình mới không hợp lệ.

## 10. Vòng đời thay đổi từ API đến ứng dụng

Khi đổi số replica từ hai lên ba:

~~~text
Thay đổi spec Deployment
        |
        v
API server lưu trạng thái mới
        |
        v
Deployment và ReplicaSet controller reconciliation
        |
        v
Pod mới được tạo và scheduler gán Node
        |
        v
kubelet và runtime khởi chạy container
        |
        v
readiness probe đạt
        |
        v
EndpointSlice và Service có thể nhận backend
        |
        v
Client thấy khả năng phục vụ thay đổi
~~~

Mỗi bước có độ trễ và có thể thất bại. Configuration Watcher cũng có chuỗi tương tự: resource được sửa, watch nhận sự kiện, component xử lý dữ liệu và ứng dụng áp dụng cấu hình. API đã lưu giá trị mới không có nghĩa mọi request đang chạy đã dùng giá trị đó.

Khi triển khai cấu hình mới, cần biết:

- phiên bản cấu hình nào đang được áp dụng;
- component nào nhận thay đổi;
- giá trị không hợp lệ bị từ chối ở đâu;
- việc áp dụng có nguyên tử với toàn bộ request không;
- cách quan sát và khôi phục khi cập nhật thất bại.

## 11. Chẩn đoán theo lớp

| Triệu chứng | Lớp kiểm tra trước | Câu hỏi |
| --- | --- | --- |
| Không tạo được Pod | API, admission, controller | Manifest có hợp lệ và controller có tạo Pod không? |
| Pod Pending lâu | Scheduler và tài nguyên | Có Node phù hợp và đủ tài nguyên không? |
| ImagePullBackOff | Runtime và registry | Image, credentials và mạng tới registry có đúng không? |
| CrashLoopBackOff | Ứng dụng và cấu hình | Process thoát vì lỗi gì, Secret và environment có đúng không? |
| Running nhưng NotReady | Probe và ứng dụng | Endpoint readiness có phản ánh khả năng phục vụ không? |
| Không gọi được Service | DNS, Service, endpoint, mạng | Tên, cổng, selector, EndpointSlice và policy có khớp không? |
| Discovery hoặc config không hoạt động | API client, RBAC, namespace | ServiceAccount có đúng quyền không? |
| Watch dừng cập nhật | API connection và reconnect | Có lỗi kết nối hoặc resource version không? |

Quyền của người vận hành để chẩn đoán không nên bị nhầm với quyền cần cấp cho ứng dụng runtime. Việc tăng quyền RBAC không chữa được lỗi selector, DNS, cổng Service hoặc readiness.

## 12. Chọn đúng tính năng Spring Cloud Kubernetes

| Tính năng | Câu hỏi quyết định | Tác động |
| --- | --- | --- |
| Service và DNS | Chỉ cần gọi API nội bộ bằng tên ổn định? | Không cần gọi Kubernetes API để tìm Pod |
| DiscoveryClient | Cần danh sách Service hoặc instance theo metadata? | Cần API access và xử lý thay đổi danh sách |
| ConfigMap | Cần đưa cấu hình vào Pod? | Có thể dùng env, volume hoặc integration API |
| Secret | Cần phân phối dữ liệu nhạy cảm? | Giới hạn RBAC, bảo vệ log và đường truyền |
| Spring Cloud LoadBalancer | Cần chọn instance phía client? | Cần nguồn instance và chính sách chọn |
| Configuration Watcher | Cần phản ứng khi resource đổi lúc runtime? | Cần watch, reconnect và quy tắc áp dụng |

Nguyên tắc quyền tối thiểu là cấp đúng verb, resource, namespace và thời điểm cần thiết. Ứng dụng chỉ gọi Service không tự động cần quyền đọc Pod. Ứng dụng đọc ConfigMap không tự động cần quyền đọc Secret. Watcher theo namespace không tự động cần quyền toàn cluster.

## 13. Bài tập tư duy

Xét ứng dụng Spring checkout có yêu cầu:

- gọi API orders trong cùng namespace;
- nhận cờ tính năng từ ConfigMap;
- không cần chọn Pod cụ thể;
- khi ConfigMap đổi, áp dụng sau một chu kỳ kiểm tra hoặc rollout có kiểm soát.

Phân tích:

1. Đường gọi checkout đến orders có thể dùng Service và DNS; chưa có lý do dùng DiscoveryClient.
2. Cờ tính năng có thể được đưa vào Pod bằng ConfigMap. Nếu cần đọc và watch qua Kubernetes API, phải thêm ServiceAccount cùng Role hoặc RoleBinding.
3. Khi cấu hình đổi, cần chọn env, volume, API integration hoặc rollout. Biến môi trường của process đang chạy không tự đổi.
4. Readiness của orders ảnh hưởng khả năng nhận request; nó không xác nhận cấu hình của checkout.
5. Khi lỗi, tách đường gọi HTTP khỏi đường gọi Kubernetes API để xác định lớp lỗi và quyền cần thiết.

## 14. Kết luận

Cluster là môi trường điều phối. Control plane lưu và điều khiển trạng thái qua Kubernetes API; node chạy kubelet, container runtime và thành phần mạng để biến trạng thái đó thành Pod hoạt động. Scheduler chọn Node, controller duy trì workload, còn kubelet thực thi Pod được giao.

Kubernetes API là ranh giới giao tiếp và bảo mật quan trọng. kubectl, controller và các integration như DiscoveryClient, ConfigMap hoặc Configuration Watcher có thể gọi API, nhưng mỗi caller phải có danh tính và quyền phù hợp. Gọi Service qua DNS là đường khác với đọc resource qua API.

Hiểu các lớp này giúp thiết kế ứng dụng Spring Cloud Kubernetes với RBAC vừa đủ, chẩn đoán theo nguyên nhân và chọn tính năng theo nhu cầu. Khi chỉ cần endpoint ổn định, Service và DNS có thể đã đủ. Khi cần metadata, danh sách instance, cấu hình động hoặc watch, hãy bổ sung integration tương ứng và mô tả rõ resource, verb, namespace cùng hành vi khi trạng thái thay đổi.
