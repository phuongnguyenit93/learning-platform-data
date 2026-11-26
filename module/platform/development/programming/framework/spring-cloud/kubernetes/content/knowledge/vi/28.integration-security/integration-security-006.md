# NetworkPolicy và giới hạn kết nối giữa các namespace

## 1. Bối cảnh và mục tiêu

Tách ứng dụng sang các namespace giúp tổ chức tài nguyên, phân quyền và vận hành. Tuy nhiên, không thể dùng việc “khác namespace” làm bằng chứng rằng hai Pod đã bị chặn kết nối mạng.

Trong module **SPRING_CLOUD_KUBERNETES**, bài học này thuộc chương **Bảo mật tích hợp**. Mục tiêu là thiết kế những đường kết nối cần thiết cho ứng dụng Spring: gọi dịch vụ, discovery, nạp ConfigMap/Secret, nhận cập nhật từ Configuration Watcher và kiểm tra sức khỏe.

Sau bài học, bạn có thể:

- Phân biệt phạm vi namespace, RBAC và quyền kết nối mạng.
- Đọc đúng ingress, egress, podSelector và namespaceSelector.
- Tạo chính sách mặc định chặn rồi mở đúng nguồn, đích và cổng.
- Giữ DNS, Kubernetes API và luồng refresh hoạt động theo nhu cầu.
- Kiểm thử cả kết nối được phép lẫn kết nối phải bị chặn.

Ví dụ dùng API chuẩn networking.k8s.io/v1. Các tính năng mở rộng của CNI, service mesh hoặc chính sách quản trị cấp cụm cần được đánh giá thêm trong môi trường triển khai.

## 2. NetworkPolicy kiểm soát điều gì?

NetworkPolicy chuẩn mô tả những kết nối được phép tới hoặc từ nhóm Pod, dựa trên địa chỉ/đối tượng mạng, cổng và giao thức. Network plugin phải hỗ trợ thực thi; tạo được tài nguyên NetworkPolicy chưa chứng minh rằng kết nối đã bị giới hạn. [Cơ chế NetworkPolicy](https://kubernetes.io/docs/concepts/services-networking/network-policies/).

Cần tách các lớp bảo vệ:

| Lớp | Ví dụ | Câu hỏi nó giải quyết |
| --- | --- | --- |
| Namespace | shop-edge và shop-core | Tài nguyên được tổ chức ở đâu? |
| RBAC | ServiceAccount được list Service trong shop-core | Ai được gọi hành động nào trên Kubernetes API? |
| NetworkPolicy | Chỉ web ở shop-edge được gọi orders:8080 | Kết nối mạng nào được phép? |
| Xác thực ứng dụng | Spring Security bảo vệ endpoint quản trị | Người gọi endpoint là ai và được làm gì? |
| TLS hoặc mTLS | Xác minh bên giao tiếp và bảo vệ dữ liệu truyền | Kênh giao tiếp có được bảo vệ không? |

Một RoleBinding không mở đường TCP. Một allow rule cũng không cấp quyền đọc Secret, không xác thực người gọi HTTP và không tự mã hóa lưu lượng.

NetworkPolicy dùng nhãn Pod để chọn workload, không xác thực danh tính ServiceAccount trong kết nối HTTP. Vì vậy, quyền tạo Pod và sửa nhãn có liên quan tới mức tin cậy của chính sách. Cô lập môi trường nhiều nhóm vẫn cần kết hợp các lớp kiểm soát. [Cô lập trong môi trường nhiều tenant](https://kubernetes.io/docs/concepts/security/multi-tenancy/).

## 3. Mô hình tình huống

Giả sử có các workload sau:

| Namespace | Deployment | Nhãn Pod | Vai trò và cổng |
| --- | --- | --- | --- |
| shop-edge | web | app: web | Gọi API nghiệp vụ của orders |
| shop-edge | audit | app: audit | Nguồn kiểm thử không được phép gọi orders |
| shop-core | orders | app: orders | Nghiệp vụ TCP 8080, quản trị TCP 9090 |
| shop-core | inventory | app: inventory | API nội bộ TCP 8080 |
| platform-config | config-watcher | app: config-watcher | Theo dõi cấu hình và gửi refresh |
| other-team | web | app: web | Nguồn kiểm thử cùng nhãn nhưng khác namespace |

Các luồng mong muốn:

~~~text
shop-edge / web
    |
    | TCP 8080
    v
shop-core / orders ---- TCP 8080 ----> shop-core / inventory
    ^
    | TCP 9090
    |
platform-config / config-watcher
    |
    +---- kết nối Kubernetes API theo cấu hình thực tế

Pod cần phân giải tên ---- UDP/TCP 53 ----> DNS của cụm
~~~

Bộ policy chính của bài cô lập **shop-core**. Nó không tự tạo default deny cho shop-edge, platform-config, other-team hoặc kube-system. Khi các namespace nguồn đã có egress policy, phía nguồn cũng phải cho phép các luồng tương ứng.

Các manifest bên dưới là chính sách để tích hợp vào môi trường thử nghiệm đã có workload và Service theo bảng. Chúng không tạo ứng dụng Spring hoặc một hệ thống Kubernetes hoàn chỉnh.

## 4. Hiểu hai chiều và cách cộng policy

### 4.1. Ingress và egress được xét riêng

Ingress là lưu lượng đi vào Pod được policy chọn; egress là lưu lượng đi ra từ Pod đó.

Một Pod có thể bị cô lập ingress nhưng chưa bị cô lập egress, hoặc ngược lại. Khi một chiều được policy chọn, các allow rule áp dụng cho chiều đó quyết định những kết nối được phép.

Với một kết nối từ A tới B:

~~~text
Cho phép kết nối mới A -> B
    = egress của A cho phép, hoặc A chưa bị cô lập egress
      VÀ
      ingress của B cho phép, hoặc B chưa bị cô lập ingress
~~~

Các allow rule từ nhiều NetworkPolicy được hợp lại. Lưu lượng trả lời của kết nối được cho phép được xử lý như một phần của kết nối đó; không cần mở riêng cổng tạm của client. [Quy tắc hai chiều và cộng dồn](https://kubernetes.io/docs/concepts/services-networking/network-policies/).

### 4.2. Default deny không có độ ưu tiên cao hơn allow

Giả sử orders được chọn bởi:

- Một policy mặc định chặn ingress.
- Một policy cho phép web gọi TCP 8080.
- Một policy khác vô tình cho phép mọi nguồn gọi mọi cổng.

Policy thứ ba làm mất giới hạn mong muốn. Đặt tên policy đầu là deny-all hoặc tạo nó sau cùng không làm nó thắng các allow rule.

Khi đánh giá một luồng, xem toàn bộ policy chọn Pod cho từng chiều. Trong cụm có chính sách quản trị hoặc tính năng mở rộng của CNI, cần xét thêm các lớp đó theo tài liệu của môi trường.

## 5. Chọn đúng namespace và Pod

### 5.1. Pod đích của policy

Ở cấp spec, podSelector chọn Pod chịu tác động trong namespace của NetworkPolicy:

~~~yaml
metadata:
  namespace: shop-core
spec:
  podSelector:
    matchLabels:
      app: orders
~~~

Đoạn này chọn Pod orders ở shop-core. Nó không chọn Pod cùng nhãn ở namespace khác.

### 5.2. Nguồn hoặc đích của một rule

Trong from hoặc to:

| Peer | Phạm vi lựa chọn |
| --- | --- |
| Chỉ podSelector | Pod phù hợp trong cùng namespace với policy |
| Chỉ namespaceSelector | Pod trong những namespace phù hợp |
| namespaceSelector và podSelector trong cùng peer | Pod phù hợp bên trong namespace phù hợp |
| namespaceSelector: {} | Mọi namespace |
| podSelector: {} trong một peer không có namespaceSelector | Mọi Pod trong namespace của policy |

Một peer ghép hai selector áp dụng điều kiện giao nhau; các peer riêng trong danh sách tạo các lựa chọn thay thế. [Định nghĩa NetworkPolicyPeer](https://kubernetes.io/docs/reference/kubernetes-api/networking/network-policy-v1/).

Ví dụ đúng khi chỉ muốn web trong shop-edge:

~~~yaml
from:
  - namespaceSelector:
      matchLabels:
        kubernetes.io/metadata.name: shop-edge
    podSelector:
      matchLabels:
        app: web
~~~

Ví dụ khác nghĩa, mở rộng quyền hơn dự định:

~~~yaml
from:
  - namespaceSelector:
      matchLabels:
        kubernetes.io/metadata.name: shop-edge
  - podSelector:
      matchLabels:
        app: web
~~~

Ví dụ thứ hai cho phép **mọi Pod trong shop-edge**, hoặc Pod app: web trong namespace của policy. Chỉ một dấu gạch đầu dòng khác vị trí đã làm thay đổi phạm vi.

Bài dùng nhãn namespace kubernetes.io/metadata.name do Kubernetes tự gắn với giá trị là tên namespace. Kiểm tra nhãn thực tế trước khi triển khai. [Nhãn tự động của namespace](https://kubernetes.io/docs/concepts/overview/working-with-objects/namespaces/).

Nhãn tùy biến như team hoặc environment có thể tiện cho nhóm namespace, nhưng phải kiểm soát ai được gán chúng. Nếu người dùng có thể tự đặt nhãn đáng tin cậy hoặc tự tạo Pod mang nhãn được phép trong namespace đã được tin cậy, ý nghĩa an ninh của phép chọn sẽ thay đổi.

## 6. Bước đầu: cô lập shop-core và giữ DNS

### 6.1. Default deny cho cả hai chiều

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: default-deny
  namespace: shop-core
spec:
  podSelector: {}
  policyTypes:
    - Ingress
    - Egress
  ingress: []
  egress: []
~~~

Policy chọn mọi Pod trong shop-core. Khi không có allow rule bổ sung, các luồng Pod thông thường bị chặn theo hai chiều đã chọn.

Dùng danh sách rỗng ở đây. ingress có một rule rỗng, chẳng hạn ingress: [{}], mang nghĩa khác: rule đó không giới hạn nguồn hoặc cổng và có thể mở toàn bộ ingress tương ứng.

Trong một rule, phần nguồn/đích và phần ports cùng ràng buộc kết nối. Nếu bỏ phần nguồn/đích hoặc cổng, không nên tự hiểu rằng nó bị chặn. [Cấu trúc ingress và egress rule](https://kubernetes.io/docs/reference/kubernetes-api/networking/network-policy-v1/).

Default deny trong bài giới hạn cả giao tiếp giữa các Pod cùng namespace. orders không tự được gọi inventory chỉ vì cùng shop-core.

### 6.2. Cho phép truy vấn DNS đúng nơi

Giả sử DNS chạy dưới dạng Pod trong kube-system, có nhãn k8s-app: kube-dns và lắng nghe UDP/TCP 53:

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-cluster-dns
  namespace: shop-core
spec:
  podSelector: {}
  policyTypes:
    - Egress
  egress:
    - to:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: kube-system
          podSelector:
            matchLabels:
              k8s-app: kube-dns
      ports:
        - protocol: UDP
          port: 53
        - protocol: TCP
          port: 53
~~~

Policy này chỉ mở luồng tới các Pod DNS được chọn, trên hai giao thức đã nêu. Không mở UDP/TCP 53 tới mọi địa chỉ.

Trước khi dùng, kiểm tra:

~~~bash
kubectl get pods -n kube-system -l k8s-app=kube-dns --show-labels
kubectl get service kube-dns -n kube-system -o yaml
kubectl exec -n shop-core deployment/orders -- cat /etc/resolv.conf
~~~

Lệnh exec giả định container có cat; với image tối giản, dùng cách chẩn đoán phù hợp. Cấu hình DNS và tên Service có thể khác giữa các cụm. [DNS cho Service và Pod](https://kubernetes.io/docs/concepts/services-networking/dns-pod-service/).

Nếu dùng NodeLocal DNSCache, nameserver của Pod có thể là địa chỉ cục bộ trên node; rule chọn Pod CoreDNS phía trên chưa chắc bao phủ chặng Pod tới bộ đệm DNS. Xác định đích thực tế và cách CNI xử lý trước khi viết ngoại lệ. [NodeLocal DNSCache](https://kubernetes.io/docs/tasks/administer-cluster/nodelocaldns/).

DNS được mở không có nghĩa mọi dịch vụ được mở. Phân giải tên thành công và kết nối tới địa chỉ được trả về là hai bước cần kiểm tra riêng.

## 7. Mở đúng các luồng của ứng dụng

### 7.1. Web gọi nghiệp vụ, Watcher gọi quản trị

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: orders-approved-ingress
  namespace: shop-core
spec:
  podSelector:
    matchLabels:
      app: orders
  policyTypes:
    - Ingress
  ingress:
    - from:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: shop-edge
          podSelector:
            matchLabels:
              app: web
      ports:
        - protocol: TCP
          port: 8080
    - from:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: platform-config
          podSelector:
            matchLabels:
              app: config-watcher
      ports:
        - protocol: TCP
          port: 9090
~~~

Hai rule thể hiện hai trách nhiệm:

- web ở đúng namespace được gọi cổng nghiệp vụ 8080.
- config-watcher ở đúng namespace được gọi cổng quản trị 9090.

Rule không mở 9090 cho web. Nó cũng không mở 8080 cho mọi Pod trong platform-config.

Ở TCP 9090, NetworkPolicy không phân biệt /actuator/refresh với endpoint HTTP khác. Vì vậy, chỉ expose những endpoint cần thiết và giữ xác thực/phân quyền ứng dụng.

### 7.2. Orders gọi inventory

Cho phép egress từ orders tới inventory cùng namespace:

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: orders-to-inventory
  namespace: shop-core
spec:
  podSelector:
    matchLabels:
      app: orders
  policyTypes:
    - Egress
  egress:
    - to:
        - podSelector:
            matchLabels:
              app: inventory
      ports:
        - protocol: TCP
          port: 8080
~~~

inventory cũng bị default deny ingress, nên cần policy ở phía đích:

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: inventory-from-orders
  namespace: shop-core
spec:
  podSelector:
    matchLabels:
      app: inventory
  policyTypes:
    - Ingress
  ingress:
    - from:
        - podSelector:
            matchLabels:
              app: orders
      ports:
        - protocol: TCP
          port: 8080
~~~

Lúc này, orders có egress DNS nhờ allow-cluster-dns và egress inventory nhờ orders-to-inventory. inventory nhận kết nối từ orders; kết nối mới theo chiều inventory tới orders vẫn cần một quyết định riêng.

### 7.3. Nếu muốn giới hạn egress của web

Trong shop-edge, có thể tạo policy chọn riêng web:

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: web-approved-egress
  namespace: shop-edge
spec:
  podSelector:
    matchLabels:
      app: web
  policyTypes:
    - Egress
  egress:
    - to:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: shop-core
          podSelector:
            matchLabels:
              app: orders
      ports:
        - protocol: TCP
          port: 8080
    - to:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: kube-system
          podSelector:
            matchLabels:
              k8s-app: kube-dns
      ports:
        - protocol: UDP
          port: 53
        - protocol: TCP
          port: 53
~~~

Policy này cô lập egress của web, rồi mở hai nhu cầu trong mô hình: orders và DNS. Nếu web còn gọi API ngoài, identity provider hoặc telemetry collector, phải bổ sung các luồng có căn cứ.

Chính sách không chọn audit hoặc các workload khác trong shop-edge. Đồng thời, allow rule từ một policy khác chọn web vẫn có thể mở rộng tổng quyền egress.

## 8. Kubernetes API: một đích đặc biệt cần xác định thực tế

### 8.1. Discovery và kết nối nghiệp vụ là hai đường khác nhau

Với DiscoveryClient trực tiếp:

~~~text
Ứng dụng
    |
    +-- Kubernetes API: lấy Service/endpoint, cập nhật danh sách instance
    |
    +-- Pod hoặc Service đích: thực hiện request nghiệp vụ
~~~

Mở đường tới API không tự mở đường tới inventory. Ngược lại, orders gọi inventory thành công chưa chứng minh discovery vẫn cập nhật được.

Spring Cloud Kubernetes hỗ trợ client trực tiếp và client HTTP dùng DiscoveryServer. Nếu dùng DiscoveryServer, ứng dụng cần đường tới server đó, còn server cần đường tới Kubernetes API. [Các cách triển khai DiscoveryClient](https://docs.spring.io/spring-cloud-kubernetes/reference/discovery-client.html).

Khi dùng Service qua DNS và không có tích hợp nào đọc API trong tiến trình, không thêm ngoại lệ API chỉ vì ứng dụng chạy trong Kubernetes.

### 8.2. Namespace của tài nguyên không phải namespace của đường mạng API

Đọc ConfigMap ở shop-core nghĩa là gửi yêu cầu tới API server có đường dẫn tài nguyên thuộc shop-core. Gói tin mạng không được gửi tới một “Pod ConfigMap” trong namespace đó.

Tương tự:

- RBAC quyết định danh tính có được đọc ConfigMap/Secret hay không.
- Thuộc tính namespace của Spring giới hạn phạm vi tìm tài nguyên.
- NetworkPolicy quyết định tiến trình có kết nối được máy chủ API hay không.

Ba cấu hình phối hợp với nhau; không cấu hình nào tự sinh ra hai cấu hình còn lại.

### 8.3. Không sao chép một IP API dùng chung cho mọi cụm

Trong Pod, client có thể dùng Service Kubernetes hoặc các thông tin môi trường được cấp để tìm API server. Kết nối còn cần CA, thông tin xác thực và quyền phù hợp. [Truy cập Kubernetes API từ Pod](https://kubernetes.io/docs/tasks/run-application/access-api-from-pod/).

Để xác định đường đi của môi trường thử nghiệm:

~~~bash
kubectl get service kubernetes -n default -o yaml
kubectl get endpointslices -n default -l kubernetes.io/service-name=kubernetes -o yaml
~~~

Nếu cơ chế control plane không biểu diễn đầy đủ endpoint qua các tài nguyên này, lấy thông tin từ cấu hình và tài liệu của cụm. Service port có thể khác cổng endpoint sau chuyển địa chỉ.

Ví dụ có điều kiện: giả sử đã xác minh CNI xét đích sau NAT là một endpoint API tại 192.0.2.10, TCP 6443. Một ngoại lệ cho orders có hình thức:

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: orders-to-kubernetes-api
  namespace: shop-core
spec:
  podSelector:
    matchLabels:
      app: orders
  policyTypes:
    - Egress
  egress:
    - to:
        - ipBlock:
            cidr: 192.0.2.10/32
      ports:
        - protocol: TCP
          port: 6443
~~~

**192.0.2.10 là địa chỉ dùng cho tài liệu, không phải địa chỉ của cụm để triển khai.** Thay bằng đích/cổng đã được xác minh. Cụm có nhiều endpoint hoặc IPv6 cần bao phủ đúng những đích hoạt động.

Việc NAT xảy ra trước hay sau bước thực thi policy phụ thuộc môi trường. Với Service, cần kiểm thử địa chỉ và cổng mà CNI thực sự xét; không mặc định chỉ mở ClusterIP:443 hoặc chỉ mở endpoint:6443 là đủ. [Service và cơ chế chuyển tiếp](https://kubernetes.io/docs/concepts/services-networking/service/).

Nếu CNI có quy tắc riêng chọn API server, có thể đánh giá tính năng đó theo tài liệu của CNI. Đây là phần mở rộng, không phải cú pháp NetworkPolicy chuẩn có thể mang sang mọi cụm.

Đối với Configuration Watcher bị cô lập egress trong platform-config, cần ngoại lệ API trên chính Pod Watcher, cùng với DNS và đường tới orders:9090. Policy trong shop-core không cấp egress cho Pod ở platform-config.

## 9. Kết nối Configuration Watcher và cổng quản trị Spring

### 9.1. Đặt đường quản trị rõ ràng

Ví dụ ứng dụng orders dùng cổng nghiệp vụ 8080 và cổng quản trị 9090:

~~~yaml
server:
  port: 8080

management:
  server:
    port: 9090
  endpoints:
    web:
      exposure:
        include: "health,refresh"
~~~

Spring Boot cho phép dùng management.server.port để tách cổng quản trị. Endpoint refresh cần dependency Spring Cloud phù hợp và cấu hình bảo vệ endpoint của ứng dụng. [Quản trị Spring Boot qua HTTP](https://docs.spring.io/spring-boot/reference/actuator/monitoring.html).

Service của ứng dụng có thể khai báo cổng và thông tin đường actuator cho Watcher:

~~~yaml
apiVersion: v1
kind: Service
metadata:
  name: orders
  namespace: shop-core
  annotations:
    boot.spring.io/actuator: "http://:9090/actuator"
spec:
  selector:
    app: orders
  ports:
    - name: http
      port: 8080
      targetPort: 8080
    - name: management
      port: 9090
      targetPort: 9090
~~~

Configuration Watcher hỗ trợ chỉ định đường/cổng actuator không mặc định bằng annotation này. Cần đối chiếu với phiên bản đang dùng. [Đích HTTP của Configuration Watcher](https://docs.spring.io/spring-cloud-kubernetes/reference/spring-cloud-kubernetes-configuration-watcher.html).

Khai báo containerPort hoặc Service port không thay thế allow rule; policy cũng không làm một tiến trình chưa lắng nghe cổng trở nên truy cập được.

### 9.2. Kiểm tra cả chuỗi cập nhật

Một lần đổi cấu hình qua volume và Watcher có thể đi qua:

~~~text
ConfigMap/Secret thay đổi
    |
    +-- Kubelet cập nhật volume
    |
    +-- Watcher nhận thay đổi qua API
            |
            v
       Watcher tìm instance đích
            |
            v
       Watcher gọi endpoint refresh
            |
            v
       Ứng dụng nạp lại cấu hình và cập nhật bean phù hợp
~~~

Mạng chỉ là một phần của chuỗi. File được cập nhật không bảo đảm bean đã được làm mới; nhận HTTP thành công cũng cần được đối chiếu với giá trị cấu hình thực sự sử dụng.

Phân biệt các nhu cầu:

| Thành phần | Đường cần xem xét |
| --- | --- |
| Ứng dụng chỉ đọc file được mount | Đọc filesystem; không cần tự gọi API chỉ để nhận file |
| Ứng dụng dùng API property source | Egress tới API, token/CA và RBAC |
| Watcher HTTP | API, DNS nếu dùng và cổng quản trị của ứng dụng |
| Watcher dùng Spring Cloud Bus | API và broker theo cơ chế được chọn |
| Health contributor truy vấn API | Đường API riêng với nhu cầu của contributor |

Không mở mọi Pod trong platform-config tới mọi cổng của shop-core để xử lý một lỗi refresh. Xác định điểm dừng trong chuỗi trước khi thêm rule.

Khi dùng service mesh, proxy có thể tạo thêm chặng kết nối hoặc thay đổi nguồn mà tầng mạng quan sát. Phải kiểm thử đường đi thực tế, đặc biệt nếu proxy trung gian kết thúc rồi tạo lại kết nối.

## 10. Kiểm thử chính sách bằng ma trận kết nối

### 10.1. Điều kiện của môi trường thử nghiệm

Chuẩn bị workload theo bảng ở mục 3, với các điều kiện:

- orders và inventory có route thử nghiệm /demo trên TCP 8080.
- orders có management endpoint trên TCP 9090.
- Các Pod nguồn thử nghiệm có curl hoặc công cụ tương đương.
- DNS và các Service hoạt động trước khi đánh giá policy.
- CNI thực thi NetworkPolicy, không có allow rule ngoài dự kiến.
- Egress của nguồn kiểm thử được phép theo kịch bản; nếu không, kết quả chặn có thể do phía nguồn.

Không cần dùng endpoint nghiệp vụ có dữ liệu nhạy cảm để kiểm tra đường TCP/HTTP. Một route thử nghiệm đơn giản giúp tách lỗi ứng dụng khỏi lỗi mạng.

### 10.2. Kiểm kê tài nguyên và cách policy được hiểu

~~~bash
kubectl get namespace shop-edge shop-core platform-config other-team --show-labels
kubectl get pods -n shop-core --show-labels
kubectl get pods -n shop-edge --show-labels
kubectl get networkpolicy -n shop-core
kubectl describe networkpolicy orders-approved-ingress -n shop-core
kubectl get service orders inventory -n shop-core -o yaml
kubectl get endpointslices -n shop-core -l kubernetes.io/service-name=orders -o yaml
~~~

Nếu policy nhìn đúng nhưng kết nối vẫn được phép, kiểm tra các policy còn lại chọn cùng Pod và khả năng thực thi của CNI. Không chỉ xem một policy vừa tạo.

Kiểm thử hành vi là bước cần thiết sau khi khai báo policy. [Hướng dẫn thực hành NetworkPolicy](https://kubernetes.io/docs/tasks/administer-cluster/declare-network-policy/).

### 10.3. Ma trận mong đợi

Các dòng dưới giả định Pod thông thường, không dùng hostNetwork và không có chính sách bổ sung mở rộng quyền:

| Nguồn | Đích | Kết quả mong đợi |
| --- | --- | --- |
| web ở shop-edge | orders TCP 8080 | Được phép |
| web ở shop-edge | orders TCP 9090 | Bị chặn |
| audit ở shop-edge | orders TCP 8080 | Bị chặn |
| web ở other-team | orders TCP 8080 | Bị chặn |
| orders ở shop-core | inventory TCP 8080 | Được phép |
| inventory ở shop-core | orders TCP 8080 | Bị chặn |
| config-watcher ở platform-config | orders TCP 9090 | Được phép |
| config-watcher ở platform-config | orders TCP 8080 | Bị chặn |
| orders hoặc inventory | Đích DNS đã cấu hình, UDP/TCP 53 | Được phép theo rule DNS phù hợp |

Dòng audit kiểm tra nhãn Pod; dòng web ở other-team kiểm tra namespace. Nếu bỏ một trong hai phép thử, có thể không phát hiện lỗi ghép selector.

### 10.4. Thực hiện từ đúng nguồn

Kết nối được phép:

~~~bash
kubectl exec -n shop-edge deployment/web -- curl -sS --connect-timeout 2 --max-time 5 -o /dev/null -w '%{http_code}' http://orders.shop-core.svc:8080/demo
kubectl exec -n shop-core deployment/orders -- curl -sS --connect-timeout 2 --max-time 5 -o /dev/null -w '%{http_code}' http://inventory.shop-core.svc:8080/demo
~~~

Các thử nghiệm phải bị chặn:

~~~bash
kubectl exec -n shop-edge deployment/web -- curl -sS --connect-timeout 2 --max-time 5 -o /dev/null -w '%{http_code}' http://orders.shop-core.svc:9090/actuator/health
kubectl exec -n shop-edge deployment/audit -- curl -sS --connect-timeout 2 --max-time 5 -o /dev/null -w '%{http_code}' http://orders.shop-core.svc:8080/demo
kubectl exec -n other-team deployment/web -- curl -sS --connect-timeout 2 --max-time 5 -o /dev/null -w '%{http_code}' http://orders.shop-core.svc:8080/demo
~~~

Các số 2 và 5 là timeout của phép thử để kết thúc có giới hạn, không phải giá trị vận hành bắt buộc.

Với kết nối phải bị chặn, cần đối chiếu lỗi mạng với đích đang sống và một nguồn được phép đang gọi thành công. Không mặc định mọi timeout đều là thành công của NetworkPolicy; DNS, Service rỗng hoặc tiến trình không lắng nghe cũng có thể gây lỗi.

HTTP 401 hoặc 403 cho biết có tầng HTTP trả lời. Không coi đó là bằng chứng NetworkPolicy đã chặn gói tin. Phản hồi này có thể thuộc ứng dụng hoặc proxy; xác định đúng thành phần trả lời.

### 10.5. Tách DNS, Service và Pod IP

Nếu request bằng tên thất bại:

1. Kiểm tra phân giải DNS từ đúng Pod nguồn.
2. Kiểm tra Service port và targetPort.
3. Kiểm tra endpoint và trạng thái sẵn sàng.
4. So sánh kết nối bằng tên Service với địa chỉ Pod lấy từ endpoint.
5. Đối chiếu CNI, NAT và các proxy trên đường đi.

Công cụ DNS trong môi trường thử nghiệm có thể dùng để kiểm tra cả UDP và TCP 53. Nếu công cụ không có sẵn trong image ứng dụng, dùng Pod chẩn đoán được quản lý phù hợp; bảo đảm namespace, nhãn và đường mạng của nó tương ứng với mục tiêu thử nghiệm.

Gọi từ laptop hoặc qua kubectl port-forward không mô phỏng cùng nguồn với web trong shop-edge. Không dùng kết quả đó làm bằng chứng duy nhất cho selector nguồn.

Khi có nhiều replica hoặc nhiều node, kiểm tra các Pod đại diện cho từng đường đi. deployment/web có thể chọn một Pod bất kỳ; dùng tên Pod cụ thể khi cần kết quả có thể lặp lại.

## 11. Các giới hạn cần đưa vào quyết định triển khai

### 11.1. API chuẩn không diễn đạt mọi yêu cầu bảo mật

Những yêu cầu như “chỉ POST /actuator/refresh”, “chỉ gọi tên miền đối tác này”, “xác thực bằng ServiceAccount” hoặc “bắt buộc mTLS” cần thêm cơ chế ngoài NetworkPolicy chuẩn.

CNI có thể cung cấp tính năng FQDN, nhận diện danh tính hoặc chính sách cấp cụm; service mesh hoặc ứng dụng có thể kiểm soát ở tầng cao hơn. Ghi rõ sự phụ thuộc nếu sử dụng chúng, tránh trình bày như một manifest chuẩn chạy ở mọi nơi.

Cùng một Pod có nhiều container dùng chung không gian mạng. NetworkPolicy chọn Pod, không chọn một container riêng để cho phép 9090. Nếu cần ranh giới tin cậy khác nhau giữa các thành phần, xem lại cách tách workload.

### 11.2. Node, hostNetwork và kết nối đang tồn tại

Lưu lượng liên quan node và hostNetwork có giới hạn xử lý riêng tùy môi trường. Không dùng ví dụ Pod thông thường để khẳng định đã cô lập tuyệt đối node hoặc mọi hostNetwork Pod.

Policy cập nhật cũng không bảo đảm mọi kết nối đang tồn tại bị đóng ngay. CNI có thể xử lý khác nhau. Vì vậy, dùng kết nối mới khi xác minh một thay đổi, đồng thời kiểm tra ảnh hưởng tới pool HTTP và WATCH đang mở. [Giới hạn và kết nối hiện hữu](https://kubernetes.io/docs/concepts/services-networking/network-policies/).

Kubelet probe có nguồn từ node nên không thể được suy luận hoàn toàn từ ma trận gọi giữa Pod. Kiểm tra probe thực tế, nhưng tránh mở mọi namespace tới cổng quản trị chỉ để giải quyết một giả định chưa được xác minh.

### 11.3. Chính sách có thời gian hội tụ

API chấp nhận manifest không có nghĩa mọi dataplane đã áp dụng ngay. Kiểm tra lại kết nối mới sau khi hệ thống hội tụ; không coi một kết quả tức thời duy nhất là trạng thái ổn định.

Ứng dụng Spring cần timeout và retry có giới hạn cho lỗi kết nối tạm thời. Liveness không nên tạo vòng restart chỉ vì API hoặc dịch vụ phụ thuộc gián đoạn ngắn; restart đồng loạt có thể tăng tải discovery và cấu hình.

Nếu cần log các kết nối bị chặn, sử dụng công cụ quan sát mà CNI hoặc hạ tầng cung cấp. Tài nguyên NetworkPolicy chuẩn không tự tạo log HTTP hay log từ chối cho từng kết nối.

## 12. Chẩn đoán theo lớp và triển khai thay đổi

### 12.1. Bảng chẩn đoán

| Triệu chứng | Điểm cần kiểm tra | Hành động có căn cứ |
| --- | --- | --- |
| Mọi tên Service đều lỗi | DNS egress, nameserver, NodeLocal DNS | Sửa rule cho đúng đích DNS |
| DNS được nhưng HTTP timeout | Egress nguồn, ingress đích, cổng, endpoint | Kiểm tra hai phía và đích đang lắng nghe |
| Nguồn không được phép vẫn gọi được | Allow policy khác, selector sai, CNI không thực thi | Xem tổng policy và test âm |
| Service gọi được nhưng discovery không cập nhật | Đường API/DiscoveryServer, WATCH và xác thực | Kiểm tra riêng đường discovery |
| API trả 403 | Danh tính và quyền RBAC | Sửa quyền theo nhu cầu; không mở mạng rộng hơn |
| API báo lỗi chứng chỉ hoặc token | CA, audience, thời hạn và nguồn token | Sửa lớp xác thực/TLS |
| Watcher thấy thay đổi nhưng refresh không tới | Đường tới cổng quản trị và cấu hình đích | Kiểm tra 9090 và địa chỉ Watcher sử dụng |
| Refresh tới nhưng giá trị không đổi | File đã cập nhật chưa, property source, bean | Kiểm tra chuỗi cập nhật cấu hình |
| Pod mới lỗi nhưng Pod cũ vẫn chạy | Thời gian hội tụ, kết nối cũ, nhãn Pod mới | Kiểm tra kết nối mới và cấu hình thực tế |
| Chỉ lỗi ở một số node | Dataplane CNI, routing hoặc proxy | So sánh flow và trạng thái theo node |

### 12.2. Trình tự triển khai

Trước khi đổi policy cho workload đang chạy:

1. Lập ma trận nguồn, đích, giao thức và cổng từ các luồng thực tế.
2. Kiểm tra CNI, DNS, Kubernetes API, proxy và policy hiện có.
3. Chuẩn bị default deny cùng các allow rule cần thiết.
4. Thử trên môi trường hoặc phạm vi canary phù hợp.
5. Chạy test dương, test âm và luồng cập nhật cấu hình.
6. Theo dõi lỗi, độ trễ, readiness và hành vi reconnect.
7. Mở rộng phạm vi sau khi có bằng chứng; giữ khả năng khôi phục đúng thay đổi.

Lưu lại cấu hình trước khi thay đổi theo quy trình quản lý triển khai. Nếu gặp sự cố, sửa rule hoặc khôi phục đúng phiên bản liên quan; xóa toàn bộ NetworkPolicy của namespace sẽ làm thay đổi nhiều luồng ngoài phạm vi đang chẩn đoán.

Với cluster có nhiều nhóm, phân quyền quản lý NetworkPolicy và nhãn namespace/Pod phải phù hợp với trách nhiệm vận hành. Một nhóm không nên vô tình mở lại vùng đã được thiết kế là cô lập bằng một allow rule quá rộng.

## 13. Kết quả cần đạt sau bài thực hành

Hoàn thành bài khi có thể chỉ ra:

- CNI thực thi chính sách đã tạo.
- orders chỉ nhận 8080 từ web đúng namespace và 9090 từ config-watcher đúng namespace theo mô hình.
- orders gọi inventory được; các chiều không khai báo không tự được mở.
- DNS hoạt động bằng đường thực tế của cụm.
- Những thành phần cần Kubernetes API có đường mạng, xác thực và RBAC phù hợp.
- Luồng refresh và kiểm tra sức khỏe hoạt động theo thiết kế.
- Cả nguồn sai nhãn và nguồn sai namespace đều bị chặn trong phép thử có kiểm soát.
- Không có allow rule khác vô tình mở rộng phạm vi mong muốn.

Kết quả cuối cùng là một ma trận kết nối được thể hiện bằng policy và được kiểm chứng bằng hành vi thực tế. Mỗi ngoại lệ cần gắn với một chức năng cụ thể của ứng dụng hoặc thành phần tích hợp.
