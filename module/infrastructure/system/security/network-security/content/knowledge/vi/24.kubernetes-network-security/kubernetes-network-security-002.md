# Service, ClusterIP, NodePort và LoadBalancer

> **Chương:** Bảo mật mạng Kubernetes  
> **Mô-đun:** SECURITY_NETWORK_SECURITY  
> **Bối cảnh:** Bảo vệ luồng mạng trong hệ thống phân tán từ phân đoạn, firewall, VPN, DNS, TLS/mTLS, IDS/IPS đến ingress cloud và Kubernetes.  
> **Trọng tâm:** Hiểu cơ chế Service discovery, Service VIP, backend endpoints, ba kiểu Service **ClusterIP – NodePort – LoadBalancer**, đường đi và IP nguồn của lưu lượng, cùng cách giảm bề mặt tấn công khi công bố dịch vụ.

## 1. Vấn đề mà Kubernetes Service giải quyết

Một ứng dụng chạy trên Kubernetes thường gồm nhiều Pod. Pod có thể bị tạo lại khi rollout, bị thay thế khi node hỏng hoặc thay đổi địa chỉ IP khi reschedule. Nếu client gọi thẳng **Pod IP**, client phải theo dõi Pod nào còn tồn tại và khi nào địa chỉ thay đổi.

**Service** cung cấp một điểm truy cập logic ổn định tới **một tập backend endpoints**, thường là các Pod có nhãn khớp với selector. Client kết nối theo **tên DNS của Service hoặc địa chỉ ClusterIP**; cơ chế xử lý Service đưa kết nối tới endpoint tương ứng theo loại Service và implementation của cluster.

Một ví dụ:

- Ba Pod của ứng dụng inventory lắng nghe TCP 8080, có nhãn **app: inventory**.
- Service **inventory** có cổng 80, dùng selector **app: inventory** và chuyển đến cổng 8080.
- Client trong cluster gọi **http://inventory.shop.svc.cluster.local:80**, không cần biết Pod cụ thể nào đang nhận request.
- Nếu một Pod bị thay thế, Kubernetes cập nhật dữ liệu endpoint tương ứng; hệ thống thực thi Service điều chỉnh hướng chuyển tiếp theo dữ liệu đó.

**Điểm cần nhớ:** Service giải quyết **service discovery và cách đưa kết nối đến backend**, nhưng **không phải firewall, hệ thống đăng nhập, mTLS policy hay cơ chế bảo đảm backend an toàn**. Việc Service tồn tại không tự cho phép người dùng vượt qua Kubernetes NetworkPolicy, IAM, route, WAF hoặc xác thực ứng dụng.

### Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt **Pod IP, ClusterIP, Node IP, public/private load balancer address**, và các loại port.
2. Giải thích cách Service dùng **selector, EndpointSlice, kube-proxy hoặc dataplane thay thế** để chọn backend.
3. Chọn đúng **ClusterIP, NodePort, LoadBalancer** theo nhu cầu truy cập và threat model.
4. Phân tích đường đi **client → load balancer/node → Service → Pod**, source IP và NAT.
5. Hiểu vai trò và giới hạn của **externalTrafficPolicy, internalTrafficPolicy, loadBalancerSourceRanges, allocateLoadBalancerNodePorts**.
6. Viết YAML Service và NetworkPolicy mẫu, tránh nhầm namespace hoặc Service type với một security boundary.
7. Kiểm tra phơi lộ mạng, hiệu lực DNS/EndpointSlice/NetworkPolicy, đồng thời xử lý lỗi an toàn.
8. Thiết kế quan sát, RBAC, audit, IaC guardrail và quy trình ứng phó khi Service bị public ngoài ý muốn.

## 2. Các khái niệm phải phân biệt

| Thành phần | Vai trò | Nguy cơ khi hiểu sai |
|---|---|---|
| **Pod IP** | Địa chỉ mạng của một Pod theo CNI | Không ổn định sau khi thay Pod; không phải cổng dịch vụ công khai |
| **Node IP** | Địa chỉ của một node Kubernetes | NodePort có thể làm tăng bề mặt kết nối đến node |
| **Service** | Tài nguyên API trừu tượng hóa endpoint và tập cổng | Không tự bảo vệ ứng dụng |
| **ClusterIP** | IP ảo được cấp cho Service trong dải dịch vụ cluster | Không mặc định truy cập được từ Internet, nhưng cũng không phải access control |
| **NodePort** | Cổng cấp trên node để chuyển traffic tới Service | Không mặc định cần một LB; cần bảo vệ node và firewall |
| **LoadBalancer** | Loại Service yêu cầu một implementation cấp load balancer bên ngoài/ngoài cluster | Public/private tùy provider và cấu hình; không mặc định có WAF/TLS |
| **EndpointSlice** | Tài nguyên chứa các endpoints và metadata liên quan, được dùng để phân phối backend | Một Service không có endpoint sẵn sàng thường không phục vụ request như kỳ vọng |
| **Selector** | Cách Service tự động liên kết tập Pod qua labels | Selector quá rộng hoặc nhầm labels có thể đưa request tới Pod sai |
| **kube-proxy / CNI service dataplane** | Thực thi chuyển tiếp Service ở node hoặc qua dataplane thay thế | Cách triển khai NAT, health và policy có khác biệt |
| **NetworkPolicy** | Chính sách L3/L4 cho Pod theo CNI hỗ trợ | Không kiểm tra user, JWT, URL hay tự động bảo vệ mọi kiểu traffic |
| **Ingress / Gateway API** | API/quản lý đường vào theo host/path/protocol với controller | Không đồng nghĩa Service type LoadBalancer |
| **Cloud network firewall/SG/NSG** | Kiểm soát network reachability ngoài/đến node và LB | Phải kết hợp với Kubernetes policy và IAM |
| **DNS/CoreDNS** | Phân giải tên Service tới địa chỉ thích hợp | Tên tìm ra dịch vụ, không thay TLS identity verification |

### 2.1. Ba địa chỉ, ba lớp ý nghĩa

~~~text
Client Pod:          10.244.1.19       (Pod IP ví dụ)
Inventory Pod:       10.244.2.25       (Pod IP có thể đổi)
Inventory Service:   10.96.20.10       (ClusterIP ví dụ)
Worker Node:         10.0.2.11         (Node IP ví dụ)
Cloud LB frontend:   203.0.113.20      (địa chỉ tài liệu ví dụ)

Client gọi ClusterIP/Service DNS, dataplane chọn Pod IP.
Client ngoài cluster có thể gọi LB frontend hoặc NodeIP:NodePort
nếu mạng/firewall/route/Service policy thực sự cho phép.
~~~

Các dải địa chỉ trên **chỉ minh họa**, không phản ánh cụm thực tế. Node có thể có nhiều interface và cả IPv4/IPv6; public LB có thể trả hostname thay vì IP cố định.

## 3. Kiến trúc tối giản: Service, selector và EndpointSlice

~~~mermaid
flowchart LR
    C[Client Pod] --> DNS[Cluster DNS]
    DNS --> S[Service inventory / ClusterIP]
    S --> D[Service dataplane kube-proxy hoặc eBPF]
    D --> P1[Pod A app=inventory]
    D --> P2[Pod B app=inventory]
    D --> P3[Pod C app=inventory]
    SEL[Service selector app=inventory] -. Theo dõi nhãn .-> ES[EndpointSlice controller]
    ES -. Danh sách backend + readiness .-> D
~~~

Dòng chảy khái niệm:

1. Tài nguyên Service định nghĩa **tên, type, ports, selector** và chính sách traffic liên quan.
2. Controller tạo/cập nhật **EndpointSlice** cho các Pod mà selector chọn, cùng địa chỉ, port và trạng thái endpoint thích hợp.
3. Dataplane của cluster nhận Service + EndpointSlice state, điều phối kết nối tới backend.
4. Client gọi Service qua **tên DNS** hoặc ClusterIP; kết nối đến Pod cụ thể thường do routing/NAT hoặc dataplane chọn.
5. Khi rollout/reschedule thay Pod, endpoint set thay đổi; các kết nối hiện có có thể tiếp tục hoặc bị gián đoạn tùy protocol, NAT, runtime và connection state.

### 3.1. Service không phải một proxy L7 mặc định

Ở trường hợp điển hình TCP/UDP, Service xử lý ở tầng vận chuyển/đường mạng; **không đọc JWT, HTTP path, user ID hay tenant** để ra quyết định phân quyền. Nếu ứng dụng cần host/path routing, TLS termination, WAF hoặc authorization, phải có **Ingress/Gateway API controller, API gateway, service mesh hoặc ứng dụng** tương ứng.

### 3.2. Không phải mọi Service đều cần selector

Service **không có selector** có thể được cấu hình với EndpointSlices do bên quản lý khác tạo. Điều này hữu ích cho endpoint đặc thù nhưng tăng trách nhiệm kiểm tra: **ai được tạo/sửa EndpointSlices và địa chỉ backend là gì?** Không tự tin một Service sẽ chỉ chuyển tới Pod có nhãn đúng nếu nó không dùng selector.

## 4. Phân biệt port, targetPort và nodePort

Một Service thường có các trường:

| Trường | Ví dụ | Vai trò |
|---|---|---|
| **spec.ports[].port** | 80 | Cổng của chính Service mà client gọi |
| **spec.ports[].targetPort** | 8080 hoặc tên cổng http | Cổng trên endpoint/Pod backend |
| **spec.ports[].nodePort** | 31080 | Cổng node dành cho NodePort hoặc LoadBalancer có cấp NodePort |
| **containerPort** trong Pod | 8080 | Metadata khai báo cổng trong container spec; không tự mở firewall |
| **protocol** | TCP, UDP hoặc SCTP khi hỗ trợ | Protocol được chuyển đến backend |
| **name** | http | Tên cổng dùng để tham chiếu, đặc biệt khi Service có nhiều ports |
| **appProtocol** | http hoặc protocol hint | Gợi ý giao thức cho controller/hệ sinh thái, **không tự thực thi auth/TLS** |

Ví dụ **port: 80, targetPort: 8080** nghĩa là client gọi Service cổng 80, còn backend nhận trên cổng 8080.

### 4.1. targetPort có thể là tên

~~~yaml
# Đoạn cấu hình minh họa trong Pod template:
containers:
  - name: api
    image: registry.example.invalid/inventory:v1
    ports:
      - name: http
        containerPort: 8080
        protocol: TCP

# Service có thể sử dụng:
ports:
  - name: http
    port: 80
    targetPort: http
    protocol: TCP
~~~

Tên cổng chỉ được resolve khi endpoint có port phù hợp; **không mở cổng container chỉ vì ghi containerPort**. Ứng dụng thật phải lắng nghe đúng địa chỉ/cổng, còn NetworkPolicy/CNI/firewall phải cho traffic theo policy.

### 4.2. Không hiểu sai số port hiển thị

Nếu truy cập **http://NODE_IP:31080**, đây là NodePort ở phía ngoài; **http://SERVICE_IP:80** là Service port; trên Pod thì process lắng nghe **8080**. Một rule NetworkPolicy thường cần xét **cổng đến Pod** theo hành vi CNI và thời điểm NAT, không chỉ lấy NodePort 31080 làm đích mà kết luận đã chặn backend.

## 5. ClusterIP: đường vào nội bộ theo mặc định

**ClusterIP** là loại Service mặc định nếu không chỉ định type khác. Kubernetes cấp một địa chỉ IP ảo trong dải Service CIDR của cluster; truy cập qua DNS Service hoặc IP đó thường được sử dụng **từ bên trong cluster**.

~~~mermaid
flowchart LR
    A[Pod frontend / Namespace web] -->|inventory.shop.svc.cluster.local:80| S[ClusterIP Service]
    S --> P1[Inventory Pod 1 :8080]
    S --> P2[Inventory Pod 2 :8080]
    X[Internet Client] -. Không có direct path mặc định .-> S
~~~

### 5.1. ClusterIP không phải một security boundary chắc chắn

- **ClusterIP không được cấp public LB hay NodePort chỉ vì là ClusterIP**, nhưng client có network route đặc biệt, VPN, mạng pod/service được expose, node hoặc môi trường có proxy riêng **có thể truy cập được** trong điều kiện nhất định.
- **Namespace không tự ngăn kết nối tới Service ở namespace khác.** Nếu CNI cho phép và không có NetworkPolicy/kiểm soát khác, một Pod ở namespace test có thể gọi Service ở namespace production.
- **ClusterIP không chứng minh caller identity.** Bất kỳ workload có khả năng kết nối có thể thử gọi endpoint; API vẫn cần token, mTLS, service authorization và network restrictions theo yêu cầu.
- **ClusterIP có thể có cổng nhạy cảm** (database, Redis, admin API). Đừng xem loại Service này là lý do để bỏ NetworkPolicy và auth.

### 5.2. Khi nào chọn ClusterIP?

- API nội bộ được truy cập từ các Pod khác, không có nhu cầu expose trực tiếp.
- Database/queue chỉ phục vụ các workload được phép và có NetworkPolicy.
- Backend sau Ingress/controller hoặc Gateway API, trong đó ingress controller có thể truy cập Service nội bộ.
- Services mà cloud LB chỉ nên expose thông qua một API gateway thay vì tạo LB riêng cho từng ứng dụng.

**Lựa chọn mặc định cho backend không cần truy cập trực tiếp ngoài cluster là ClusterIP**, rồi cấp đúng đường vào ở phía trước nếu nghiệp vụ yêu cầu.

## 6. NodePort: đưa Service ra cổng của node

**NodePort** cấp một cổng trên node để kết nối tới Service, đồng thời vẫn có cơ chế ClusterIP tương ứng trong triển khai thông thường. Kubernetes mặc định sử dụng dải **30000–32767**, nhưng cluster administrator có thể cấu hình dải khác qua API server.

Đường đi phổ biến:

~~~mermaid
flowchart LR
    C[Client được phép] -->|Node IP :31080| N[Node A / NodePort]
    N --> D[Service dataplane]
    D --> P1[Pod trên Node A :8080]
    D --> P2[Pod trên Node B :8080]
~~~

**Không nên hiểu NodePort tự công bố Internet.** Một NodePort có thể chỉ reachable từ private VPC/VNet, VPN hoặc mạng quản trị. Nó có thể trở thành public nếu node có public IP, firewall/cloud security group mở và có đường đi. Mức phơi lộ thực tế phải xác minh bằng **node addresses, nodePort binding, route, cloud ACL và CNI**.

### 6.1. Tại sao NodePort cần bảo vệ?

- Cổng có thể được xử lý trên nhiều node theo cấu hình Service proxy; **mỗi node mới có thể mở rộng số địa chỉ nhận lưu lượng**.
- Service không tự yêu cầu MFA, OAuth2 hoặc mTLS.
- Node và host firewall/security group có thể cho phép port từ quá nhiều nguồn.
- Các hệ thống quan sát chỉ giám sát Ingress có thể bỏ sót traffic đi trực tiếp NodePort.
- Nếu người dùng có quyền tạo/sửa NodePort Service quá rộng, họ có thể tạo đường vào backend ngoài kiến trúc WAF/API gateway.

### 6.2. NodePort không có nghĩa Pod chạy trên mọi node

Một node nhận kết nối NodePort có thể **chuyển đến Pod ở node khác** khi traffic policy cho phép. Vì thế **node không có Pod backend** vẫn có thể là một entrypoint trong mode thông thường. Khi dùng **externalTrafficPolicy: Local**, hành vi lại phụ thuộc có endpoint local hay không.

### 6.3. nodePort và giới hạn cấu hình

Có thể để Kubernetes tự chọn NodePort trong dải được cấp, hoặc khai báo **nodePort** cụ thể nếu hợp lệ và chưa bị sử dụng. Xung đột cổng hoặc giá trị ngoài dải sẽ làm Service bị từ chối. **nodePortAddresses** của kube-proxy hay tương đương trong dataplane có thể giới hạn địa chỉ node nhận NodePort; điều kiện và cú pháp phụ thuộc môi trường.

## 7. LoadBalancer: yêu cầu một bộ điều khiển cung cấp điểm vào ngoài cluster

**type: LoadBalancer** yêu cầu hệ thống controller tích hợp (cloud controller manager, load balancer controller hoặc implementation khác) cung cấp **địa chỉ/hostname và đường traffic tới backend** theo cách của nền tảng.

~~~mermaid
flowchart LR
    C[Client Internet / VPN / Partner] -->|LB frontend :443 hoặc :80| LB[Cloud / On-prem LB]
    LB -->|NodePort hoặc Pod direct tùy provider| D[Service dataplane / Backend]
    D --> P1[Pod inventory-1]
    D --> P2[Pod inventory-2]
    K[Kubernetes Service type LoadBalancer] -. Yêu cầu controller .-> LB
    F[Cloud firewall / SG / ACL] -. Hạn nguồn và cổng .-> LB
~~~

**Một LoadBalancer Service không tự bảo đảm:**

- Là **private/internal**: nhiều cloud integration có thể tạo **public/external** LB nếu thiếu cấu hình nội bộ.
- Có **WAF**, API authentication hoặc TLS termination.
- Không có **NodePort**: nhiều implementation vẫn cấp NodePort làm backend, dù có cách direct-to-Pod/IP theo controller hỗ trợ.
- Có public IP ngay lập tức: môi trường local hoặc cluster thiếu controller có thể giữ **EXTERNAL-IP: pending**.
- Hành vi source-IP preservation, health check và routing giống nhau giữa cloud providers.

### 7.1. Public và private LB là lựa chọn khác nhau

Public LB dùng Internet-routable frontend phù hợp với endpoint công khai đã thiết kế. Private/internal LB có địa chỉ trong VPC/VNet/on-prem network, thường dành cho client qua private network, VPN hoặc interconnect. Tuy nhiên **private LB vẫn cần firewall, IAM, mTLS/app authorization**, không phải "đã private thì ai cũng được gọi".

**Cấu hình LB nội bộ phần lớn là provider-specific annotation hoặc cơ chế controller riêng**; không có một annotation portable áp dụng cho AWS, Azure, Google Cloud, MetalLB hay mọi implementation.

### 7.2. Controller thay đổi cả cloud resources

Tạo hoặc cập nhật LoadBalancer Service có thể kích hoạt **cloud API mutations**: cấp frontend, backend pool, health check, rules hoặc security groups. Vì vậy quyền tạo **Service type LoadBalancer** trong cluster và **IAM của cloud controller** là một phần threat model. Một principal Kubernetes có quyền tạo Service không nhất thiết có cloud IAM trực tiếp, nhưng controller **có thể thực hiện thay đổi cloud dưới identity riêng của nó**.

## 8. Bảng so sánh ClusterIP – NodePort – LoadBalancer

| Thuộc tính | ClusterIP | NodePort | LoadBalancer |
|---|---|---|---|
| Mục tiêu chính | Điểm vào logic nội bộ | Điểm vào qua cổng node | Điểm vào qua LB do controller quản lý |
| ClusterIP thông thường | Có | Có | Có |
| NodePort | Không | Có | Thường có; có thể bỏ cấp nếu implementation hỗ trợ |
| Frontend bên ngoài | Không do loại này tự tạo | NodeIP:nodePort khi reachable | LB IP/hostname nếu controller cấp |
| DNS Service nội bộ | Có | Có | Có |
| Công bố Internet mặc định | Không | Không tự động; phụ thuộc node/network | Có thể public tùy provider/defaults |
| Cần cloud LB controller | Không | Không | Có implementation LB thích hợp |
| Điều phối backend | Dataplane Service | Dataplane Service | LB + dataplane hoặc direct Pod |
| TLS/WAF/AuthN mặc định | Không | Không | Không |
| Giới hạn client IP | Qua network/policy | Node FW/SG + policy | LB firewall/source ranges + policy |
| Rủi ro chủ yếu | Cross-namespace lateral access | Node-level exposure/bypass ingress | LB công khai ngoài ý muốn, chi phí/route/ACL |
| Dùng cho | Service nội bộ | On-prem/lab, backend của LB/ingress | Dịch vụ cần entrypoint riêng bên ngoài |

**Đây là so sánh về cách kết nối, không phải bảng xếp hạng bảo mật.** ClusterIP có thể bị truy cập trái quyền từ Pod khác; LoadBalancer có thể bảo mật tốt nếu đúng private scope, WAF, mTLS và firewall; NodePort có thể hợp lý trong một hạ tầng được thiết kế chặt.

## 9. YAML mẫu 1 — Service ClusterIP cho API nội bộ

Giả sử namespace **shop** đã tồn tại và ba Pod có **app: inventory**, ứng dụng lắng nghe TCP 8080. Manifest sau chỉ tạo Service, **không tạo Pod**.

~~~yaml
apiVersion: v1
kind: Service
metadata:
  name: inventory
  namespace: shop
  labels:
    app.kubernetes.io/name: inventory
spec:
  type: ClusterIP
  selector:
    app: inventory
  ports:
    - name: http
      protocol: TCP
      port: 80
      targetPort: 8080
~~~

Kết quả mong đợi: một Service VIP và tên DNS như **inventory.shop.svc.cluster.local** (nếu cluster domain là **cluster.local**). Việc tên phân giải đúng **chưa chứng minh backend có endpoint sẵn sàng hoặc app đã authenticate client**.

### 9.1. Điều cần kiểm tra

- **kubectl get svc -n shop inventory -o wide**: type, ClusterIP, port, selector.
- **kubectl get endpointslices -n shop -l kubernetes.io/service-name=inventory**: có endpoints không?
- Pod có **app: inventory** thật không, Pod có **Ready** không?
- Container lắng nghe 8080 và app xử lý request đúng không?
- NetworkPolicy có cho **đúng caller namespace/pod** và backend port không?

### 9.2. Selector phải đủ hẹp

Nếu cùng namespace có Pod staging hoặc admin mang nhãn **app: inventory**, một selector quá rộng có thể route request không mong đợi. Thiết kế label thêm **component, environment hoặc instance** phù hợp; kết hợp **admission policy/RBAC** bảo vệ quyền thay nhãn và tạo Pod. Selector không phải lớp authorization độc lập.

## 10. YAML mẫu 2 — NodePort cho môi trường thử nghiệm có giới hạn

Ví dụ dưới đây dùng cùng Pod selector nhưng tạo một Service khác trong môi trường lab. Chỉ thực hiện trên cluster được quản lý; **không mở cổng ở public firewall cho demo này**.

~~~yaml
apiVersion: v1
kind: Service
metadata:
  name: inventory-nodeport
  namespace: shop
spec:
  type: NodePort
  selector:
    app: inventory
  ports:
    - name: http
      protocol: TCP
      port: 80
      targetPort: 8080
      nodePort: 31080
~~~

Luồng thường gặp:

~~~text
Client -> NODE_IP:31080 -> Service dataplane
       -> PodIP:8080 (Pod có thể ở node khác)
~~~

Nếu **31080** đã được dùng hoặc ngoài dải NodePort của cluster, manifest bị từ chối. Một Service NodePort có thể vẫn nhận **ClusterIP:80** từ Pod trong cluster. **Đừng cấp mặc định firewall allow 0.0.0.0/0 hoặc ::/0 tới NodePort.**

### 10.1. Port cố định hay tự cấp?

Để Kubernetes tự cấp NodePort thường đơn giản hơn cho automation. Port cố định có ích khi tích hợp firewall/LB ngoài cluster, nhưng cần **quản lý registry cổng và tránh xung đột**. Dải mặc định có thể được chia vùng cho dynamic/static allocation theo cấu hình và phiên bản; không dựa vào một ngưỡng tĩnh mà không kiểm tra API server thực tế.

## 11. YAML mẫu 3 — LoadBalancer và nguồn được phép

~~~yaml
apiVersion: v1
kind: Service
metadata:
  name: inventory-lb
  namespace: shop
  # Bổ sung metadata.annotations theo cloud controller nếu cần internal LB.
  # Không có một annotation internal-LB portable cho mọi nhà cung cấp.
spec:
  type: LoadBalancer
  selector:
    app: inventory
  ports:
    - name: http
      protocol: TCP
      port: 80
      targetPort: 8080
  loadBalancerSourceRanges:
    - 192.0.2.0/24
~~~

**192.0.2.0/24 là dải TEST-NET chỉ dùng trong tài liệu.** Trong môi trường thật, danh sách nguồn phải là CIDR **được phê duyệt**, có đánh giá IPv6 và đường proxy/NAT; ví dụ này **không cung cấp kết nối thực** từ địa chỉ trên. Chế độ và mức hỗ trợ **loadBalancerSourceRanges** phụ thuộc controller, dataplane và cloud firewall; phải **kiểm chứng enforcement thực**, không chỉ thấy field xuất hiện trong YAML.

### 11.1. Tại sao cấu hình trên chưa phải production?

- Chưa chỉ định **internal LB** theo provider, do vậy không được coi là private.
- Frontend là HTTP port 80 và **không có TLS**; ứng dụng nhạy cảm cần TLS ở điểm thích hợp, thiết kế mTLS/identity khi cần.
- Chưa có WAF/API gateway/rate limit/authorization; LoadBalancer không tự tạo.
- Chưa có NetworkPolicy, owner, admission policy, monitoring, logging và change approval.
- Không bảo đảm Pod backend chỉ truy cập qua LB; có thể vẫn có ClusterIP, NodePort hoặc đường khác.

### 11.2. Nếu cluster không có LoadBalancer implementation

Service có thể giữ **EXTERNAL-IP: pending**, trong khi ClusterIP/NodePort vẫn tồn tại theo Service spec. Các môi trường bare metal có thể sử dụng implementation như MetalLB hoặc LB appliance phù hợp, nhưng phải quản lý **address pools, BGP/L2 advertisement, external routing và firewalls**. Không suy diễn pending là lỗi ứng dụng.

## 12. Một dịch vụ có thể được truy cập theo nhiều cách

Với NodePort hoặc LoadBalancer, loại Service thường **bổ sung đường vào** chứ không nhất thiết bỏ đường nội bộ.

~~~mermaid
flowchart TB
    IN[Pod trong cluster] -->|Service DNS / ClusterIP| S[Service inventory]
    EXT[Client private network] -->|NodeIP:NodePort nếu reachable| NP[Node Port]
    PUB[Client Internet/Partner] -->|LB frontend nếu allowed| LB[LoadBalancer]
    NP --> S
    LB --> S
    S --> P[Inventory Pods]
~~~

### 12.1. Ý nghĩa bảo mật

Nếu chỉ đặt WAF ở phía **LoadBalancer**, nhưng NodePort vẫn được cloud firewall mở tới node, một client có đường trực tiếp **NodeIP:NodePort** có thể bỏ qua WAF. Phải kiểm kê **mọi điểm vào**: Ingress/Gateway API, LoadBalancer, NodePort, pod hostNetwork/hostPort, port-forward, externalIPs, private connectivity và các proxy khác.

### 12.2. Không nhầm Kubernetes Service type với chính sách Internet

Một Service type LoadBalancer có thể chỉ có private frontend; một NodePort Service có thể reachable công khai nếu node có public IP và ACL mở; một ClusterIP có thể được client đặc quyền tiếp cận qua VPN/routes. Tên type **không đủ** để đánh giá exposure.

## 13. DNS của Service và truy cập xuyên namespace

Kubernetes DNS thường tạo tên:

~~~text
<service>.<namespace>.svc.<cluster-domain>

Ví dụ, nếu cluster domain = cluster.local:
inventory.shop.svc.cluster.local

Trong cùng namespace shop:
inventory

Từ namespace web:
inventory.shop
inventory.shop.svc.cluster.local
~~~

### 13.1. DNS không phải access control

Một Pod biết tên **inventory.shop.svc.cluster.local** chưa chắc được phép kết nối nếu có NetworkPolicy, CNI policy hoặc firewall. Ngược lại, một Pod có thể gọi trực tiếp ClusterIP mà không hỏi DNS; **chặn DNS không tương đương chặn dữ liệu đến service**.

### 13.2. Endpoint và DNS phải cùng được kiểm tra

Lỗi có thể ở nhiều lớp:

1. DNS không phân giải Service name vì CoreDNS/kube-dns, search domain hoặc cấu hình client.
2. DNS phân giải ClusterIP đúng nhưng **Service không có endpoints** do selector/readiness.
3. Endpoints đúng nhưng app không lắng nghe targetPort hoặc NetworkPolicy chặn.
4. Kết nối có thể đến backend nhưng app trả 401/403/404/500; đây là lớp HTTP/auth khác.
5. Headless Service trả về tập endpoint IPs, không có VIP theo mô hình ClusterIP thông thường.

### 13.3. CoreDNS cũng là workload cần bảo vệ

Trong cluster có **default-deny egress NetworkPolicy**, các Pod thường cần luồng DNS đến hệ thống DNS thực tế theo TCP/UDP 53 nếu sử dụng CoreDNS/kube-dns. Cần xác định Pod/namespace DNS và policy CNI phù hợp; không mở egress tới **toàn bộ namespace kube-system hoặc mọi Pod** chỉ để DNS chạy.

## 14. Selector, EndpointSlice và trạng thái sẵn sàng

Kubernetes Service thường xác định backend nhờ **selector**, còn **EndpointSlices** chứa địa chỉ/ports và các điều kiện sẵn sàng liên quan.

| Thành phần | Cần xem | Hậu quả nếu sai |
|---|---|---|
| **Service selector** | Match labels nào? | Không có backend hoặc chọn nhầm Pod |
| **Pod labels** | Có đồng nhất với workload/owner không? | Route traffic qua Pod không mong muốn |
| **Readiness probe** | Pod có Ready để phục vụ không? | Endpoint có thể chưa được chọn để nhận request |
| **EndpointSlice** | Addresses, ports, endpoint conditions, node | Load balancing không tìm được backend |
| **Target port** | Container có listener đúng không? | Connection refused hoặc timeout |
| **Terminating endpoints** | Endpoint đang shutdown/drain thế nào? | Connection drain/rollout có thể gặp lỗi |
| **Topology/node placement** | Pod có ở node nhận traffic khi policy Local không? | Node không có endpoint local có thể không phục vụ được |

### 14.1. Readiness không phải security validation

Readiness probe cho biết Pod đã đáp ứng điều kiện phục vụ theo định nghĩa của ứng dụng/controller. Nó không chứng minh Pod sạch mã độc, có quyền truy cập data đúng hoặc certificate xác thực hợp lệ. Cần kết hợp **image provenance, admission, runtime security, NetworkPolicy, mTLS và application authorization**.

### 14.2. Một nhãn bị đổi có thể đổi đích Service

Nếu một principal có quyền sửa Pod labels hoặc EndpointSlices ngoài phạm vi, nó có thể ảnh hưởng cách traffic được chuyển. Điều tra hiện tượng "Service trỏ nhầm" cần **Kubernetes audit logs và RBAC** bên cạnh log mạng. Nên giới hạn quyền **create/update/patch Service, Pod, EndpointSlice** theo role.

### 14.3. EndpointSlice không phải một proxy

EndpointSlice là **dữ liệu khám phá endpoints**, không trực tiếp nhận kết nối từ client. Dataplane/connections chọn endpoint dựa trên Service data, policy và implementation. Với Service không selector, EndpointSlices có thể được quản lý thủ công bởi controller có quyền; đảm bảo địa chỉ backend là nguồn đáng tin.

## 15. Dataplane Service: kube-proxy, nftables, IPVS và eBPF

Khi Service dùng VIP, Kubernetes không nhất thiết chạy một process reverse proxy riêng cho mỗi Service. Node có thể dùng **kube-proxy** tạo luật trong kernel, hoặc một **CNI/dataplane khác** hỗ trợ Service load balancing.

### 15.1. Các triển khai thường gặp

| Kiểu triển khai | Ý tưởng | Cần thận trọng |
|---|---|---|
| **iptables** | Luật kernel chọn backend, NAT/forwarding | Conntrack, quy mô luật, vị trí NAT liên quan NetworkPolicy |
| **IPVS** | Virtual server ở kernel và scheduler | Hỗ trợ/thiết lập có thể khác theo phiên bản cluster |
| **nftables** | Dataplane dùng nftables theo khả năng/kube-proxy mode | Không giả định mọi distro hỗ trợ hoặc bật giống nhau |
| **eBPF CNI** | Dataplane/eBPF thay hoặc bổ sung Service forwarding | Semantics SNAT/source IP/policy tùy nhà cung cấp/CNI |
| **Cloud/controller-specific** | LB trực tiếp tới node hoặc Pod endpoints | Kiểm tra health, route, controller IAM và backend mode |

**Không dùng một mô hình iptables duy nhất để lý giải mọi cluster.** Phiên bản Kubernetes, kube-proxy config, CNI, cloud provider, host firewall và overlay/underlay ảnh hưởng đường đi thực tế.

### 15.2. Kết nối mới và kết nối đang tồn tại

Một request TCP được chọn backend khi tạo kết nối; nhiều HTTP requests trên cùng keepalive/HTTP/2 connection có thể dùng **cùng Pod**, không tự round-robin per HTTP request. Khi backend thay/Pod chết, **conntrack/session state** có thể gây reset hoặc thời gian chuyển đổi; **Service không đảm bảo zero downtime** nếu ứng dụng chưa drain, readiness/termination chưa phù hợp.

### 15.3. Load balancing không luôn chia đều

Distribution phụ thuộc implementation, session affinity, connection reuse, topology preferences, health và traffic policy. Đừng suy từ số replicas rằng mỗi Pod sẽ nhận chính xác 1/N requests.

## 16. Đường đi traffic và NAT/SNAT: vì sao IP nguồn bị thay?

Một client truy cập Service từ bên ngoài có thể đi qua **cloud LB → node → Pod**, nhiều chặng có thể thay đổi địa chỉ source/destination. Với một số kiểu Service networking, **SNAT** khiến Pod thấy IP của node hoặc proxy thay vì IP client gốc.

~~~mermaid
sequenceDiagram
    autonumber
    participant C as Client 198.51.100.44
    participant L as External LB
    participant N as Node + Service dataplane
    participant P as Backend Pod
    C->>L: TCP tới LB frontend
    L->>N: Forward tới NodePort hoặc backend
    N->>P: NAT/forward theo traffic policy
    P-->>N: Response
    N-->>L: Reply qua đường NAT/route
    L-->>C: Client response
~~~

### 16.1. Có thể thấy ba nguồn khác nhau

- **Socket source IP** tại Pod có thể là IP client, node hoặc LB tùy đường đi.
- **X-Forwarded-For/Forwarded** chỉ có ý nghĩa với proxy L7 có tạo/truyền header và **trusted proxy chain**.
- **mTLS identity, token/user identity** thuộc tầng xác thực, không thể tự suy từ IP socket.

**Không dùng địa chỉ IP được client tự ghi trong HTTP header làm bằng chứng user identity.** Với API access control, xác minh token/mTLS và scope độc lập với network client IP. Với điều tra, kết hợp LB logs, proxy logs, Kubernetes Service/endpoint và firewall flow telemetry.

### 16.2. Đọc log ở đúng điểm quan sát

Một firewall ở trước LB nhìn IP của client; một Pod có thể nhìn IP của node. Hai log khác source IP không nhất thiết mâu thuẫn. Dùng **request ID/trace ID, timestamps, LB connection logs, service name, backend Pod IP và NAT context** để liên kết.

## 17. externalTrafficPolicy: Cluster và Local

Với Service type **NodePort** và **LoadBalancer**, **externalTrafficPolicy** định nghĩa cách xử lý traffic từ bên ngoài cluster qua những điểm vào được hỗ trợ.

| Giá trị | Hành vi khái quát | Ảnh hưởng |
|---|---|---|
| **Cluster** (mặc định thường gặp) | Node nhận traffic có thể chuyển tới backend ở node khác | Cho phép phân phối rộng hơn; source IP có thể bị SNAT theo implementation |
| **Local** | Node chỉ chuyển external traffic đến endpoint local đủ điều kiện | Có thể bảo tồn client source IP qua node dataplane; node không có backend local không phục vụ như mode Cluster |

### 17.1. externalTrafficPolicy: Local không tự là “giữ IP thật” trong mọi kiến trúc

Nếu trước node có **L7 proxy/CDN** hoặc LB đã SNAT, Pod vẫn có thể thấy IP proxy/LB. **Local chỉ ảnh hưởng một phần đường traffic trong cluster**, không đảo những NAT trước đó.

### 17.2. Vấn đề khi endpoint local bằng 0

Nếu LB gửi request tới node không có backend Pod local trong mode **Local**, request có thể thất bại. LB implementation cần dùng **health checks và endpoint/node readiness** thích hợp để chỉ chọn node đủ điều kiện. Khi Pod reschedule, rolling deploy hoặc autoscaling, tập node healthy có thể thay đổi.

### 17.3. Health check của LoadBalancer

Một số LB Service sử dụng **healthCheckNodePort** khi **externalTrafficPolicy: Local**, theo cơ chế Kubernetes/provider hỗ trợ. Không phải mọi LB thực hiện health check giống nhau, và không nên mở health check port từ toàn Internet nếu chỉ cần cloud health probes. Đánh giá security groups, source CIDRs và provider-specific health check logic.

### 17.4. Local có thể làm mất cân bằng

Khi có 3 Pod trên node A và 1 Pod trên node B, LB phân phối đều theo node **không nhất thiết** tạo chia tải đều theo Pod. Cần quan sát per-node/per-pod traffic, zone distribution và HPA, không bật Local chỉ vì một mục tiêu tưởng tượng về hiệu suất.

## 18. internalTrafficPolicy và phân phối traffic nội bộ

**internalTrafficPolicy** có thể định hướng traffic nội bộ trong cluster với các giá trị như **Cluster** (phạm vi toàn cluster) hoặc **Local** (chỉ endpoints local trên node) theo khả năng của Kubernetes.

### 18.1. Khi dùng Local cho traffic nội bộ

- Có thể giảm đường xuyên node cho cache/agent hoặc tối ưu locality.
- **Nếu node không có endpoint local thích hợp**, traffic qua Service có thể không có backend được chọn; client có thể thấy lỗi dù Service vẫn có endpoints trên node khác.
- Không nên dùng Local như **authorization**. Một Pod có thể có đường khác tới backend theo network policy; Local chỉ là một lựa chọn phân phối.
- Cần kiểm tra cùng **readiness, autoscaling, topology spreading và failure domains**.

### 18.2. Topology preferences khác chính sách bảo mật

Những tính năng phân phối gần node/zone hoặc traffic hints hỗ trợ locality/performance, nhưng không nên xem như **quy định bắt buộc không vượt subnet/zone**. Muốn ràng buộc mạng thực sự, cần **CNI policy, routing/firewall và workload authorization**.

## 19. LoadBalancer nâng cao: NodePort allocation, class và source ranges

### 19.1. allocateLoadBalancerNodePorts

Một Service LoadBalancer thông thường có thể được Kubernetes cấp NodePorts. Trường **spec.allocateLoadBalancerNodePorts: false** có thể dùng với những implementation LB định tuyến **trực tiếp tới Pod** hoặc không cần NodePorts.

~~~yaml
# Mảnh spec minh họa, chỉ dùng với controller hỗ trợ direct routing.
spec:
  type: LoadBalancer
  allocateLoadBalancerNodePorts: false
  selector:
    app: inventory
  ports:
    - name: http
      port: 80
      targetPort: 8080
      protocol: TCP
~~~

**Giới hạn:**

- Nếu controller vẫn cần NodePort, tắt cấp NodePort có thể khiến LB không hoạt động.
- Nếu **NodePorts đã cấp trước khi đổi giá trị field**, đổi thành false không tự xóa những nodePort có sẵn; cần thực hiện thay đổi Service ports/cấu hình một cách có kế hoạch theo hướng dẫn nền tảng.
- Không tự suy **không NodePort = an toàn**: LB vẫn có thể public, Pod endpoints có thể có đường khác.

### 19.2. loadBalancerClass và controller ownership

Trong hệ có nhiều controller LB, trường **spec.loadBalancerClass** có thể chỉ định implementation phù hợp. Nó liên quan **ai sẽ thực thi yêu cầu tạo LB**, và theo semantics Kubernetes thường không được sửa sau khi thiết lập. Hãy kiểm tra controller có thực sự quản lý class đó, IAM của controller, public/internal defaults và cơ chế giải phóng LB khi xóa Service.

### 19.3. loadBalancerSourceRanges

Dùng **CIDR nguồn được cho phép** để hạn chế client tới LB khi implementation hỗ trợ. Tuy nhiên:

- Hiệu lực có thể được áp ở cloud firewall, node rules hoặc tầng khác tùy controller.
- NAT/proxy đứng trước LB có thể khiến địa chỉ nguồn khác client ban đầu.
- Cần hỗ trợ/kiểm thử **IPv4 và IPv6** nếu service dual-stack.
- Không dùng danh sách source IP để thay **mTLS, OAuth/JWT, API scopes và application authorization**.
- Rà soát LB public endpoints và cả **NodePort bypass paths**.

### 19.4. Không nên tùy tiện đặt loadBalancerIP hoặc address annotations

Việc gán IP cố định, chọn address pool, tạo internal LB hoặc giới hạn subnet thường **phụ thuộc provider/controller**. Trường **spec.loadBalancerIP** không có semantics portable trên mọi implementation và đã không còn được khuyến nghị trong các Kubernetes hiện đại; hãy dùng cơ chế controller được hỗ trợ và review trước khi deploy.

## 20. Dual-stack IPv4/IPv6 và phạm vi phơi lộ

Kubernetes cluster có thể hỗ trợ **IPv4-only, IPv6-only hoặc dual-stack**. Một Service có thể sử dụng các trường **ipFamilyPolicy** và **ipFamilies** theo cấu hình cluster, đồng thời có nhiều ClusterIPs nếu dual-stack được cấp phát.

~~~yaml
# Phần spec minh họa: yêu cầu cluster hỗ trợ dual-stack.
spec:
  type: ClusterIP
  ipFamilyPolicy: PreferDualStack
  selector:
    app: inventory
  ports:
    - port: 80
      targetPort: 8080
      protocol: TCP
~~~

**PreferDualStack** không đảm bảo hai địa chỉ luôn được cấp trong mọi cluster; xem **spec.ipFamilies**, **spec.clusterIPs** thực tế và trạng thái CNI/DNS.

### 20.1. Kiểm tra cả hai họ địa chỉ

| Thành phần | IPv4 | IPv6 |
|---|---|---|
| NodePort bind/route | Node IPv4, security group/host firewall | Node IPv6, security group/host firewall |
| LoadBalancer frontend | IPv4 address/hostname | IPv6 frontend và policy nếu provider hỗ trợ |
| Service VIP | IPv4 ClusterIP | IPv6 ClusterIP nếu được cấp |
| DNS | A record | AAAA record |
| Source ranges | CIDR IPv4 | CIDR IPv6 |
| NetworkPolicy/ipBlock | CIDR IPv4 | CIDR IPv6, implementation-dependent semantics |
| Backend Pod | Pod IPv4 | Pod IPv6 khi CNI/pod network hỗ trợ |

**Bảo vệ IPv4 không tự bảo vệ IPv6.** Một LoadBalancer có firewall chặn public SSH trên IPv4 nhưng cấp thêm IPv6 frontend không được review có thể tạo đường ngoài dự kiến. Ghi rõ **cả A/AAAA, IPv4/IPv6 routes và rule parity** trong test plan.

## 21. NetworkPolicy: kiểm soát Pod traffic, không phải Service type

**Kubernetes NetworkPolicy** mô tả những luồng **L3/L4** mà các Pod được phép gửi/nhận theo namespace, pod labels, IP blocks và ports. NetworkPolicy chỉ có hiệu lực khi **network plugin/CNI hỗ trợ enforcement**; nếu plugin không thực thi, việc tạo object NetworkPolicy đơn thuần **không bảo vệ lưu lượng**.

### 21.1. Semantics cơ bản

- Mặc định một Pod chưa bị NetworkPolicy nào cô lập theo hướng nhất định thường **không bị NetworkPolicy mặc định chặn**.
- **Ingress isolation** xảy ra khi Pod được một policy có hiệu lực cho hướng Ingress chọn; **Egress isolation** tương tự cho hướng Egress.
- Với Pod đã bị cô lập, **các rules allow từ nhiều NetworkPolicies được cộng dồn (additive union)**; NetworkPolicy chuẩn không đưa ra thứ tự deny/allow để ưu tiên.
- Kết nối Pod A → Pod B cần thỏa **egress của A nếu bị cô lập egress**, và **ingress của B nếu bị cô lập ingress**.
- NetworkPolicy chuẩn không kiểm tra path HTTP, JWT, user account, TLS certificate hoặc application action.
- Các phần mở rộng **GlobalNetworkPolicy, FQDN policies hoặc L7 policies** của CNI/vendor không đồng nghĩa với khả năng NetworkPolicy Kubernetes chuẩn.

### 21.2. Default deny không phải một cú click trên toàn cluster

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: default-deny-ingress-egress
  namespace: shop
spec:
  podSelector: {}
  policyTypes:
    - Ingress
    - Egress
~~~

Policy này chọn tất cả Pod trong namespace **shop** và không khai báo allow rules, nên yêu cầu deny cả ingress lẫn egress theo NetworkPolicy semantics nếu CNI thực thi. **Áp dụng trực tiếp lên production có thể cắt DNS, API, metrics, readiness, cơ chế quản lý và các luồng nghiệp vụ.** Chỉ áp dụng qua kế hoạch kiểm thử, canary và allowlist bắt buộc.

### 21.3. NetworkPolicy nên chọn đích là Pod, không dựa duy nhất vào Service VIP

Để cho phép truy cập **inventory Service**, nên xây rule theo **Pod backend inventory** và **Pod/namespace caller** khi có thể, thay vì chỉ dùng **ipBlock** tới ClusterIP. Thứ tự NAT (DNAT/SNAT) và policy evaluation có thể khác theo CNI, dẫn tới rule dựa trên Service VIP cho kết quả khác mong đợi.

### 21.4. Nhớ kiểm tra phần traffic từ node

Lưu lượng giữa **node/host processes** và Pod, traffic của hostNetwork pods, health checks, kubelet và cơ chế quản lý có thể có xử lý đặc thù theo CNI/implementation. **Không dùng NetworkPolicy chuẩn để khẳng định đã chặn mọi dạng node-origin hoặc host-network traffic.** Cần host firewall, cloud security groups, admission/security policy và test đường thực.

## 22. YAML mẫu — chỉ cho Orders gọi Inventory

Giả sử:

- Namespace **shop** tồn tại; Pod gọi mang label **app: orders**.
- Pod nhận mang label **app: inventory**, lắng nghe TCP 8080.
- Service **inventory** có **port: 80, targetPort: 8080**.
- CNI hỗ trợ NetworkPolicy.

### 22.1. Policy cho ingress của Inventory

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: inventory-allow-orders
  namespace: shop
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

Policy này cô lập hướng ingress cho **Pod inventory** nếu chưa có policy ingress khác, chỉ cho traffic từ những Pod **app: orders trong cùng namespace** tới TCP 8080; traffic từ Pod khác chỉ có thể được phép nếu có NetworkPolicy khác cho phép hoặc ngoại lệ CNI/node-specific.

**Quan trọng:** một Pod khác có khả năng tự thay label thành **app: orders** hoặc một người có quyền tạo Pod/patch labels trong namespace có thể lạm dụng cách xác định nguồn này. NetworkPolicy label selector phải đi cùng **Kubernetes RBAC, admission, namespace ownership và workload identity**.

### 22.2. Policy cho egress của Orders

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: orders-allow-inventory
  namespace: shop
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

Nếu có default-deny egress, Pod Orders chỉ có route egress được policy cho phép **theo NetworkPolicy**, nên **DNS hoặc các dependencies khác vẫn cần allow riêng**. Kết quả thực còn phụ thuộc CNI và các policy bổ sung.

### 22.3. Mở DNS có kiểm soát

~~~yaml
# Ví dụ cần CHỈNH theo labels và topology DNS của cluster cụ thể.
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: orders-allow-cluster-dns
  namespace: shop
spec:
  podSelector:
    matchLabels:
      app: orders
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

**Không phải mọi cluster có Pod DNS label k8s-app: kube-dns.** NodeLocal DNSCache có thể chạy qua node-local address hoặc host network và cần cách cho phép khác. Hãy tìm đúng endpoint DNS và kiểm tra NetworkPolicy/CNI của cluster; không tự mở tất cả egress vào **kube-system**.

### 22.4. Vì sao policy này chưa đủ làm ứng dụng an toàn?

- **Orders** có thể hợp lệ ở mức IP/port nhưng user hiện tại không được phép xem dữ liệu.
- **Pod inventory** có thể phục vụ HTTP không mã hóa hoặc thiếu mTLS nếu đường tin cậy yêu cầu.
- **NodePort/LoadBalancer** có thể tạo đường ngoài cluster; các network policies cần được kiểm thử với source/NAT thực tế.
- **Default-deny ingress** không thay việc chặn direct-to-node hoặc cloud firewall ở đúng điểm.
- **Egress** của ứng dụng có thể vẫn truy cập mạng khác qua chính sách CNI bổ sung, hostNetwork hoặc quyền/node routing tùy môi trường.

## 23. NetworkPolicy với Ingress controller và LoadBalancer

Khi client Internet truy cập:

~~~text
Client -> WAF/Cloud LB -> Ingress Controller Pod
       -> Service ClusterIP -> Backend Pod
~~~

Với một kiến trúc như vậy:

1. **Cloud firewall/LB** hạn nguồn/port tới ingress controller, điều phối TLS/edge behavior.
2. **Ingress controller** kiểm tra host/path, TLS và policy phù hợp.
3. **NetworkPolicy ingress của backend** cho phép traffic từ **ingress controller Pods** ở namespace được định nghĩa, không mở cho mọi Pod.
4. **Backend application** thực hiện AuthN/AuthZ và có thể dùng **mTLS** giữa proxy–backend theo yêu cầu.
5. **Egress của ingress controller** đến backend phải được cho phép nếu controller bị cô lập egress.
6. **DNS, tracing/logging và service discovery** cần được tính trong policy, tránh cắt luồng vận hành.

### 23.1. Khi traffic đi thẳng qua Service LoadBalancer

Với LoadBalancer Service trỏ trực tiếp đến Pod, **source mà CNI thấy** có thể phụ thuộc LB SNAT/direct-to-pod mode. Một policy chỉ cho IP client trực tiếp hoặc một policy chỉ cho IP node **có thể hoạt động khác mong đợi**. Phải kiểm thử trên CNI/controller thực tế, không copy nguyên mẫu NetworkPolicy từ môi trường khác.

### 23.2. Không mở ingress backend cho toàn namespace chỉ vì proxy cùng namespace

Nếu namespace có nhiều Pod, **namespaceSelector-only** có thể cho cả Pod không phải ingress controller gọi backend. Hãy chọn cả **namespace và pod labels đáng tin** ở mức phù hợp, tách ingress namespace và kiểm soát quyền sửa nhãn.

## 24. Ingress, Gateway API, API gateway và Service LoadBalancer

Các khái niệm này liên quan nhau nhưng ở các lớp trừu tượng khác nhau:

| Thành phần | Chức năng | Trường hợp thường gặp |
|---|---|---|
| **Service ClusterIP** | Trỏ một điểm đến TCP/UDP/... tới backend | Backend nội bộ |
| **Service NodePort** | Cổng trên node chuyển đến Service | Bare metal hoặc backend của proxy/LB |
| **Service LoadBalancer** | Yêu cầu controller cấp LB external/internal frontend | Service cần LB riêng |
| **Ingress** | Mô tả HTTP/HTTPS host/path routing cho Ingress controller | Công bố nhiều backend qua một edge |
| **Gateway API** | Mô hình Gateway/Route/GatewayClass với controller, phân quyền giữa các vai trò | Kiến trúc edge/mesh có route policy phong phú |
| **API gateway** | Product/application layer quản lý auth, quotas, policy, observability, routing | API có AuthN/AuthZ, throttling, logs |
| **Service mesh** | Chính sách và kết nối giữa workloads, thường gồm mTLS/authorization | East-west service-to-service |

Một **Ingress controller** có thể được công bố qua một Service **LoadBalancer**; controller tiếp nhận HTTP, chọn route và gọi các Service **ClusterIP**. Sự tồn tại của tài nguyên **Ingress** không tự tạo dataplane nếu không có controller phù hợp.

### 24.1. Ví dụ Ingress routing

~~~yaml
# Minh họa, yêu cầu có Ingress controller và TLS Secret đúng.
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: shop-api
  namespace: shop
spec:
  ingressClassName: nginx
  tls:
    - hosts:
        - api.example.com
      secretName: shop-api-tls
  rules:
    - host: api.example.com
      http:
        paths:
          - path: /inventory
            pathType: Prefix
            backend:
              service:
                name: inventory
                port:
                  number: 80
~~~

**Không tự xem cấu hình trên có WAF/auth/rate-limit.** Ingress resource mô tả routing/TLS references; security behavior phụ thuộc Ingress controller, policy, secrets, lớp LB và NetworkPolicy. Nếu cùng app còn một NodePort công khai, khách có thể bỏ qua Ingress.

### 24.2. Gateway API và phân quyền giữa platform/app

Gateway API có thể giúp tách **Gateway ownership** (platform team) và **Route ownership** (app team) theo mô hình ReferenceGrant/allowedRoutes/namespace policy, nhưng controller và version vẫn quan trọng. Không cấp quyền sửa Gateway listener hay cross-namespace references cho mọi app developer chỉ vì họ có quyền tạo HTTPRoute.

## 25. Headless Service, ExternalName, externalIPs và các đường phụ

Bên cạnh ba kiểu chính, một số biến thể/thành phần mở rộng ảnh hưởng đáng kể đến kết nối và bảo mật.

### 25.1. Headless Service — clusterIP: None

~~~yaml
apiVersion: v1
kind: Service
metadata:
  name: database-peers
  namespace: shop
spec:
  clusterIP: None
  selector:
    app: database-peer
  ports:
    - port: 5432
      targetPort: 5432
~~~

Headless Service không có **ClusterIP ảo** theo mô hình thông thường; DNS có thể trả **địa chỉ endpoints** để client trực tiếp chọn peer. Nó thường hữu ích cho StatefulSet/discovery, không phải một security boundary. Quyền truy cập **Pod IP, network policies và app authentication** vẫn cần kiểm soát.

### 25.2. ExternalName

~~~yaml
apiVersion: v1
kind: Service
metadata:
  name: external-report
  namespace: shop
spec:
  type: ExternalName
  externalName: reports.partner.example
~~~

**ExternalName không hoạt động như kube-proxy LB**: DNS tạo alias/CNAME theo quy ước; Kubernetes không tự mở kết nối hay TLS proxy cho endpoint. **Host/SNI/certificate identity** có thể không trùng tên Service được client gọi; cần kiểm tra ứng dụng và không bỏ hostname verification. Nếu người dùng có quyền tạo/sửa ExternalName, phải xét khả năng thay đích DNS, SSRF/service discovery abuse và egress policy.

### 25.3. externalIPs

Một Service có thể khai báo **spec.externalIPs** theo cấu hình. Kubernetes **không tự cấp phát/quản lý route bên ngoài cho IP này**; khi traffic tới một external IP có đường đi đến node/dataplane, Service có thể xử lý theo cơ chế hỗ trợ.

**Đây là một đường exposure dễ bị quên trong review ClusterIP/NodePort/LoadBalancer.** Hạn quyền dùng **externalIPs** bằng admission policy và bảo vệ route/firewall, không coi một Service type cụ thể là đủ để kết luận chỉ có một điểm vào.

### 25.4. hostPort, hostNetwork và port-forward

- **hostPort** hoặc **hostNetwork** đưa ứng dụng gần/đến node networking, **không phải Service type** nhưng có thể tạo đường vào node khác chính sách Ingress.
- **kubectl port-forward** thiết lập tunnel do người có quyền mở; quyền Kubernetes API **pods/portforward** và truy cập control plane phải được bảo vệ, không dùng nó làm bằng chứng rằng Service mạng luôn reachable.
- Port-forward có thể đi qua đường control plane/kubelet với semantics khác Service data path và NetworkPolicy; **không lấy kết quả port-forward thành công để kết luận NetworkPolicy cho phép ứng dụng bình thường**.

## 26. TLS, mTLS, identity và authorization của Kubernetes Service

Một Service type **ClusterIP, NodePort hoặc LoadBalancer** không mặc định tạo TLS/mTLS. Nó cũng không tự xử lý OAuth2 token, API key, session cookie hoặc quyền dữ liệu.

### 26.1. Những mô hình bảo vệ thường gặp

| Đường kết nối | Kiểm soát |
|---|---|
| **Internet → CDN/WAF/Gateway** | HTTPS/TLS, DNS, WAF, rate limiting, API auth |
| **LB → Ingress controller** | Network ACL/SG, TLS mode theo thiết kế, trusted proxy headers |
| **Ingress → Backend Service** | NetworkPolicy, TLS/mTLS nếu cần, backend AuthZ |
| **Service A → Service B** | Service identity/mTLS, L3/L4 NetworkPolicy, service authorization |
| **Backend → Database** | Egress allowlist, DB TLS/auth, credentials scoped, query permissions |
| **Node → control plane/metadata** | Node IAM, kubelet/API RBAC, metadata endpoint protection |
| **Monitoring/health checks** | Least-privilege endpoint, source restrictions, không tiết lộ secrets |

### 26.2. Service DNS không chứng minh đúng server

Nếu client kết nối theo tên **inventory.shop.svc.cluster.local**, TLS client cần kiểm tra server certificate có **danh tính phù hợp** hoặc dùng identity của workload như **SPIFFE ID** với validator tương ứng. **ClusterIP và Service DNS chỉ là định tuyến/tìm tên**, không thay việc xác minh chứng thư, trust domain và chính sách mTLS.

### 26.3. Client IP sau proxy không thay user identity

Với **externalTrafficPolicy: Local**, source IP có thể được giữ tại Pod trong một số đường đi, nhưng **X-Forwarded-For vẫn phải dựa trên trusted proxy** và **user authorization vẫn cần token/session/permission checks**. Đừng cấp quyền quản trị API chỉ vì request có vẻ đến từ một IP trong VPC.

### 26.4. TLS termination ở đâu?

Cần biết TLS kết thúc tại **cloud LB, ingress, gateway hay ứng dụng**, và đoạn từ điểm đó tới backend có mã hóa/xác thực hay không. **TLS ở LB frontend không đồng nghĩa end-to-end encryption** nếu backend hop là plaintext.

## 27. Kubernetes RBAC, admission và cloud IAM: ai được public Service?

Bảo mật Service không chỉ là chọn **type: ClusterIP**; phải quản trị người có thể **tạo/sửa/xóa Service** và hạ tầng phụ thuộc.

### 27.1. Quyền sửa Service là quyền thay kiến trúc mạng

Một principal được phép tạo/sửa Service có thể:

- Đổi **ClusterIP → NodePort/LoadBalancer** trong điều kiện API cho phép và controller hỗ trợ, làm xuất hiện đường vào ngoài dự kiến.
- Thay **ports, selector, externalIPs, loadBalancerSourceRanges, externalTrafficPolicy**.
- Gắn annotation khiến cloud controller tạo **public LB** thay vì internal LB.
- Trỏ Service tới **Pod labels khác** và thay đích traffic.
- Xóa Service gây outage hoặc gỡ một cơ chế routing mà API khác đang phụ thuộc.

### 27.2. RBAC không tự giới hạn Service spec theo field

Kubernetes RBAC chuẩn cấp quyền theo **API group/resource/verb/namespace hoặc resource names khi áp dụng**. Nó không có permission phổ quát **“được tạo ClusterIP nhưng không được tạo LoadBalancer”** dựa trên field Service type.

Muốn ràng buộc nội dung Service phải dùng **admission controls** như **ValidatingAdmissionPolicy, policy engine (OPA Gatekeeper/Kyverno) hoặc webhook được kiểm soát**, kết hợp RBAC. Có thể áp các điều kiện:

- Chỉ namespace **ingress-system** hoặc owner được phép tạo **LoadBalancer**.
- Bắt buộc internal LB annotation/class theo provider với các service private.
- Từ chối public NodePort/externalIPs ngoài kế hoạch.
- Bắt buộc owner, environment, approved CIDR và change ID.
- Chặn sửa selector từ backend của một team sang Pod nhạy cảm của team khác khi không được phép.
- Không cho thay firewall/LB security annotations ở namespace không thuộc quyền.

**Admission policy cũng phải được bảo vệ quyền sửa và tính sẵn sàng**. Một webhook luôn fail-open hoặc controller thiếu healthy replicas có thể gây bypass/outage theo cấu hình; cần xác định rõ failurePolicy, phạm vi và quy trình emergency.

### 27.3. Cloud-controller IAM

Khi một người tạo Service type LoadBalancer, **controller** có thể gọi AWS/Azure/GCP API bằng identity mạnh hơn chính người đó. Bảo vệ:

1. Cloud controller chỉ có IAM permissions cho LB/network resources cần thiết.
2. Không cho một Service annotation hoặc field tùy ý dẫn tới tài nguyên ngoài account/subnet/pool đã duyệt.
3. Network resource names/tags/owner, log API changes và cost quotas được quản trị.
4. IaC/governance phát hiện **orphaned LB, firewall rules, public addresses** còn lại sau Service deletion.
5. Audit được cả **Kubernetes API actor** và **cloud IAM actor/controller** liên quan cùng change.

### 27.4. Mẫu tư duy quyền tối thiểu

~~~yaml
# Pseudocode quản trị, không phải Kubernetes RBAC/Admission policy có thể apply.
roles:
  app_team:
    service_read: true
    clusterip_service_create_update: "approved_namespaces_only"
    nodeport_service_create_update: false
    loadbalancer_service_create_update: false
    kubernetes_networkpolicy_edit: "team_namespace_with_review"
  platform_ingress:
    loadbalancer_service_create_update: "ingress_namespaces_only"
    public_frontend_changes: "change_approval_required"
  network_security:
    admission_policy_ownership: true
    public_exposure_audit: true
  cloud_controller:
    cloud_iam: "scoped_lb_and_firewall_actions_only"
    log_control_plane_mutations: true
guardrails:
  - "disallow_unreviewed_NodePort"
  - "disallow_unreviewed_externalIPs"
  - "require_internal_loadbalancer_for_private_apps"
  - "restrict_LB_source_ranges_and_IPV6"
  - "no_direct_to_origin_bypass"
~~~

**Đây là yêu cầu thiết kế, không phải quyền RBAC có sẵn.** Cần chuyển thành RBAC + admission + cloud IAM thật và test trường hợp **ALLOW/DENY**, không giả định chỉ khai báo YAML policy minh họa sẽ được thực thi.

## 28. Threat modeling: thay đổi một Service ảnh hưởng gì?

| Tài sản | Tình huống/rủi ro | Biện pháp phòng vệ |
|---|---|---|
| **Backend riêng tư** | Service bị đổi thành LoadBalancer public | Admission guardrail, private LB policy, cloud firewall |
| **Node network** | NodePort mở tới Internet, bypass Ingress | Node SG/ACL/host FW, restrict NodePort, exposure inventory |
| **Service selector** | Chọn Pod không mong đợi | Ownership labels, Pod admission/RBAC, EndpointSlice audit |
| **EndpointSlice** | Endpoint giả/mapping sai trong selectorless Service | Giới hạn quyền edit endpoints, review custom controller |
| **Pod-to-Pod path** | Namespace khác gọi Service nội bộ | Default-deny + explicit allow NetworkPolicy, mTLS |
| **DNS/Service discovery** | DNS record đổi đích hoặc client tin alias sai | DNS policy, TLS hostname/SPIFFE validation |
| **Cloud LB** | Public frontend, source ranges sai, orphan LB | Provider-specific internal LB, source controls, cloud IAM/audit |
| **NodePort/Local policy** | Chọn node không có endpoint local | LB health checks, Pod spreading, monitoring |
| **NetworkPolicy** | CNI không enforce hoặc policy quá rộng | Verify CNI, negative tests, policy audit |
| **Traffic source identity** | SNAT hoặc XFF spoofing làm sai attribution | externalTrafficPolicy review, trusted proxy chain, verified identity |
| **Ingress/WAF** | Direct NodePort/origin access bypass WAF | Block direct paths, source allowlist, backend authorization |
| **IPv6** | Public IPv6 ngoài policy dù IPv4 chặn | Dual-stack review và tests |
| **TLS/mTLS** | LB TLS termination nhưng backend plaintext | Encrypt/authenticate appropriate hops, certificate validation |
| **Cloud controller** | Role quá mạnh, namespace user có thể cấp LB | Least privilege IAM, admission, cloud audit |
| **Operational availability** | Không có endpoints, NodePort collision, LB pending | Readiness/EndpointSlices, controllers, SLI/health checks |

### 28.1. STRIDE ở mức Service

- **Spoofing:** giả danh caller bằng header, Pod labels hoặc credentials không được bảo vệ; Service không tự xác thực client.
- **Tampering:** đổi Service selector, ports, cloud LB annotations hoặc EndpointSlices.
- **Repudiation:** thiếu Kubernetes API audit/cloud LB change logs khiến không truy được ai công bố Service.
- **Information disclosure:** public LB/NodePort cho endpoint dữ liệu, hoặc API nội bộ không có auth.
- **Denial of service:** selector trống, endpoints không Ready, node unhealthy, LB pending hoặc policy Local thiếu endpoint.
- **Elevation of privilege:** Pod/service account có quyền sửa Service/admission hoặc cloud controller được gọi qua annotation ngoài phạm vi.

**Đây là threat model học tập, không phải mọi môi trường đều có cùng điểm yếu.** Kiểm tra CNI, provider, IAM/RBAC, controllers và đường dữ liệu thật trước khi kết luận.

## 29. Kiến trúc phòng vệ nhiều lớp

Ví dụ ứng dụng thương mại có API công khai và backend nội bộ:

~~~mermaid
flowchart TB
    U[Internet User] --> E[DNS + CDN/WAF + TLS]
    E --> L[Public LB cho Ingress Controller]
    L --> I[Ingress / API Gateway Pods]
    I --> S[Orders ClusterIP Service]
    S --> O[Orders Pods]
    O --> T[Inventory ClusterIP Service]
    T --> V[Inventory Pods]
    V --> D[Private DB]
    P[NetworkPolicy + CNI enforcement] -. Restrict ingress/egress .-> O
    P -. Restrict ingress/egress .-> V
    M[mTLS / App AuthZ] -. Verify service and user .-> O
    M -. Verify service and user .-> V
    G[Admission + RBAC + Cloud IAM] -. Guard Service/LB changes .-> L
    G -. Guard changes .-> S
    G -. Guard changes .-> T
    L -. Logs .-> SIEM[SIEM + Network Observability]
    I -. Request IDs / WAF events .-> SIEM
    O -. App logs .-> SIEM
~~~

### 29.1. Quy tắc kiến trúc đề xuất

1. **Một đường vào public được chủ động chọn**: thường là CDN/WAF → public LB → ingress/API gateway, không mở NodePort ngẫu nhiên cho ứng dụng.
2. **Backend Service mặc định ClusterIP** và chỉ có allow NetworkPolicy cần thiết; database ưu tiên private và yêu cầu xác thực.
3. **Không coi namespace là firewall**, không coi Cloud private IP là chứng minh client được phép.
4. **TLS/mTLS và AuthN/AuthZ** được thực thi tại các lớp phù hợp; kiểm tra user/tenant/object ở application.
5. **Public/private LB được phê duyệt qua admission + cloud networking controls**, rõ owner/region/IP family.
6. **Lưu lượng egress cũng cần giới hạn**, tránh ứng dụng sau Ingress tự gọi metadata endpoint, Internet hoặc management network.
7. **Không bỏ quên kênh quản trị**: Kubernetes API, kubelet, node SSH, port-forward và hostNetwork có security boundary khác.
8. **Có log ở từng lớp và kiểm thử negative**: denied lateral access, denied direct NodePort path, wrong service identity.
9. **Có quy trình thay đổi** Service manifests, EndpointSlice/RBAC, Ingress controllers, NetworkPolicy và cloud LB resources.

### 29.2. Ví dụ phân nhóm trách nhiệm

| Nhóm | Phạm vi |
|---|---|
| **Application team** | Pods, Service ClusterIP, route app được phê duyệt, health/readiness |
| **Platform team** | Ingress/Gateway controller, LB class, CNI, DNS, node/network config |
| **Network security team** | Public exposure guardrails, NetworkPolicy baseline, cloud firewalls, trust boundaries |
| **IAM/Cloud team** | RBAC, admission owner, controller IAM, workload identities |
| **SRE/NOC** | Availability, latency, EndpointSlice/health, rollout và rollback |
| **SOC** | WAF/flow/app/cloud/Kubernetes audit correlation, detection và incident response |

Không tách mỗi vai trò thành một cluster administrator. Tổ chức có thể kết hợp trách nhiệm nhưng cần **SoD, audit và giới hạn đặc quyền thực tế**.

## 30. Quan sát Service: audit, metrics, logs và flow telemetry

Mỗi lớp cần trả lời một câu hỏi riêng:

| Nguồn dữ liệu | Thấy được gì? | Không tự chứng minh điều gì? |
|---|---|---|
| **Kubernetes Service API** | Type, ports, selector, ClusterIPs, LoadBalancer status | Không chứng minh traffic thực sự vào được |
| **EndpointSlice/Pod state** | Backend addresses, readiness, placement | Không chứng minh app đang trả response đúng |
| **Kubernetes Events** | Một số vấn đề provisioning/controller/Pod | Không phải nhật ký đầy đủ mọi API mutation |
| **Kubernetes API audit** | Ai tạo/sửa/xóa Service/NetworkPolicy theo cấu hình audit | Không chứng minh data-plane routing đã đổi thành công |
| **Cloud LB/controller audit** | LB create/update/delete, target/SG changes | Không biết chắc app-level authorization |
| **Ingress/API gateway logs** | Host/route/status/latency, request ID, AuthN/AuthZ/WAF decisions | Không bao trùm NodePort/direct-to-Pod bypass |
| **CNI/NetworkPolicy flow logs** | Allowed/denied connections theo CNI hỗ trợ | Không mặc định có mọi CNI hoặc mọi L7 detail |
| **Node/firewall/VPC flow logs** | IP/port/flow, NAT context khi có | IP không tự là user identity |
| **Application logs/traces** | API status, dependency, business permission, latency | Không thấy request bị chặn trước backend |
| **DNS logs** | Service name resolution, DNS errors và caching | Một DNS lookup thành công không chứng minh TCP kết nối được |

### 30.1. Những metric/cảnh báo nên có

- **Số Services theo type và namespace**; cảnh báo Service mới loại NodePort/LoadBalancer/externalIPs ngoài owner allowlist.
- **Public LB inventory** theo source ranges, IP family, annotations/class, cloud account/subnet và ingress controller.
- **Số Service không có EndpointSlice/endpoints Ready** trong các route đang hoạt động.
- **Endpoint churn**, readiness fail, Pod restart và pod distribution theo node/zone.
- **LB pending/provisioning errors**, health check failure, backend not healthy.
- **Per-Service 4xx/5xx, latency p95/p99, request volume**, gắn với ingress và backend.
- **NetworkPolicy denied flows** và số Pod/namespace không bị cô lập theo baseline.
- **Kubernetes API mutations** đối với Service, NetworkPolicy, EndpointSlice, Ingress, Gateway, RBAC.
- **Cloud IAM/network changes** do controller hoặc admin tạo, gồm public IP, security group, listener, route và DNS.
- **TLS/mTLS failures**, unexpected proxy source IP hoặc authentication bypass signals.
- **Sự kiện tắt logging hoặc lỗ hổng ingestion**, để không hiểu nhầm “không có log = không có traffic”.

### 30.2. Request ID khác kết nối TCP

Một kết nối TCP HTTP/2 có thể mang nhiều HTTP requests. Service proxy có thể theo dõi connection/flow ở L4, còn Ingress/backend ghi **request ID/trace ID** ở L7. Không giả định **một flow log = một API request**. Với gRPC, HTTP status và **grpc-status** cũng có thể khác nhau; chỉ tính SLI theo đúng tầng cần đo.

### 30.3. Tách event time và ingest time

Cloud controller logs, CNI flow telemetry và application traces có thể được gửi trễ. Cần timestamp kèm timezone, đồng bộ NTP/clock, ghi **event time, ingest time, source component** và mức sai lệch để không đảo ngược timeline giữa LB, Service, Pod và cloud firewall.

### 30.4. Không log credentials để điều tra mạng

Chỉ lưu **request ID, route, status, client/source context đã xác minh, service/Pod/namespace, policy decision, endpoint, latency** khi cần. Không đưa **Authorization, JWT, API key, cookie, TLS private key hoặc toàn bộ query/body nhạy cảm** vào SIEM chỉ để xác định một NodePort.

## 31. Chẩn đoán chỉ đọc bằng kubectl

Các lệnh sau **không sửa tài nguyên**, nhưng vẫn có thể tiết lộ topology, labels, địa chỉ và security policies. Chỉ sử dụng với kubeconfig, namespace và cluster được cấp quyền. **kubectl context** rất quan trọng: đọc nhầm production thay vì staging cũng có thể làm lộ thông tin ngoài nhiệm vụ.

### 31.1. Xác định cluster và Service types

~~~bash
# Xem context hiện hành và danh sách contexts được cấu hình.
kubectl config current-context
kubectl config get-contexts

# Liệt kê Services ở mọi namespace mà tài khoản được đọc.
kubectl get services --all-namespaces -o wide

# Xem đầy đủ một Service đã được giao quản lý.
kubectl describe service inventory -n shop
kubectl get service inventory -n shop -o yaml
~~~

**Lưu ý:** Một user có quyền read ở nhiều namespace không có nghĩa có quyền **tạo NodePort hoặc LoadBalancer** ở các namespace đó.

### 31.2. Kiểm tra endpoint set

~~~bash
# Đối chiếu Service selector, Pods và EndpointSlices.
kubectl get service inventory -n shop -o wide
kubectl get pods -n shop -l app=inventory -o wide
kubectl get endpointslices -n shop \
  -l kubernetes.io/service-name=inventory -o wide

# Xem tình trạng và lý do một Pod không Ready.
kubectl describe pod INVENTORY_POD_NAME -n shop
~~~

Thay **INVENTORY_POD_NAME** bằng tên Pod thuộc scope được cấp quyền. Các thông tin Events/Pod spec có thể chứa dữ liệu nhạy cảm; không đưa bản dump nguyên vào ticket công khai.

### 31.3. Kiểm tra node và NetworkPolicy

~~~bash
kubectl get nodes -o wide

kubectl get networkpolicies --all-namespaces
kubectl describe networkpolicy inventory-allow-orders -n shop

# Kiểm tra IAM Kubernetes hiện tại, không cấp/thay quyền.
kubectl auth can-i get services -n shop
kubectl auth can-i create services -n shop
kubectl auth can-i patch services -n shop
kubectl auth can-i get endpointslices -n shop
~~~

**kubectl auth can-i create services** trả lời về **resource/verb** cho identity hiện tại trong phạm vi cụ thể; nó **không phân biệt được tạo ClusterIP so với LoadBalancer** theo field type và không chứng minh admission/controller sẽ chấp nhận manifest.

### 31.4. Kiểm tra LoadBalancer pending

~~~bash
kubectl get service inventory-lb -n shop -o wide
kubectl describe service inventory-lb -n shop

# Xem Events gần đây trong namespace theo quyền.
kubectl get events -n shop --sort-by=.metadata.creationTimestamp
~~~

Nếu EXTERNAL-IP pending, kiểm tra controller/provisioner, quota, LB class, annotation nội bộ, subnet/IP pool và quyền cloud IAM theo nền tảng. **Không tạo public LoadBalancer khác để “thử nhanh” trên production**.

### 31.5. Debug ứng dụng từ một test Pod có phép

Có thể sử dụng **Pod test đã được chuẩn bị trong namespace thử nghiệm** để truy vấn DNS hoặc gửi request tới **health endpoint được cấp phép**. Lệnh sau mang tính kiểm tra ứng dụng, không phải hoàn toàn read-only ở góc độ mạng; chỉ dùng khi được cho phép:

~~~bash
# Ví dụ: Pod test có công cụ nslookup/curl và endpoint lab.
kubectl exec -n shop TEST_POD_NAME -- \
  nslookup inventory.shop.svc.cluster.local

kubectl exec -n shop TEST_POD_NAME -- \
  curl --silent --show-error --max-time 5 \
  http://inventory.shop.svc.cluster.local:80/health
~~~

**Không dùng kiểm tra HTTP không mã hóa cho dữ liệu nhạy cảm.** Đây chỉ là health-check lab. Nếu Service yêu cầu TLS/mTLS hoặc token, dùng cơ chế được cấp đúng danh tính test, không tắt certificate validation hoặc sao chép token production vào lệnh/chat.

## 32. Chẩn đoán theo triệu chứng

| Triệu chứng | Khả năng cần kiểm tra | Bằng chứng chính |
|---|---|---|
| **Tên Service không phân giải** | CoreDNS, namespace, cluster domain, DNS policy | nslookup/dig từ Pod test, DNS logs |
| **ClusterIP phân giải đúng nhưng timeout** | NetworkPolicy, route/CNI, node networking, backend hang | EndpointSlice, denied flows, Pod logs |
| **Connection refused** | Không có listener/port target, endpoint lỗi, dataplane path | App process/Pod ports, Endpoints, proxy logs |
| **Service không có endpoint** | Selector sai, Pod không Ready, namespace nhầm | Service selector, Pod labels, EndpointSlice |
| **Một số Pod gọi được, số khác không** | Namespace-specific NetworkPolicy, node/zone reachability | Source Pod/namespace, CNI logs |
| **NodePort hoạt động ở một số node** | externalTrafficPolicy Local, nodePortAddresses, node firewall, endpoint placement | Node, policy, Pod locations |
| **NodePort reachable ngoài dự kiến** | Public node IP, cloud SG/ACL, firewall rule, route | Node address inventory, cloud policy, flow logs |
| **LB có EXTERNAL-IP: pending** | Chưa có controller, IAM/quota/subnet/class lỗi | Service Events, LB controller logs |
| **LB có IP nhưng không nhận traffic** | LB health, source ranges, subnet, route, port/protocol, CNI | Cloud target health, flow logs |
| **LB gửi traffic chỉ vài Pod** | Local node policy, session affinity, connection reuse, health | Endpoint placement và per-Pod traffic |
| **Pod thấy IP node thay vì client** | SNAT/NAT, externalTrafficPolicy Cluster, upstream proxy | Dataplane config, LB/proxy logs |
| **Frontend 502/503** | Không có healthy endpoints, targetPort sai, backend readiness | Ingress logs, EndpointSlice, app logs |
| **Frontend 401/403** | JWT/mTLS/route authorization/WAF/app policy | Gateway/app security event, request ID |
| **DNS đúng nhưng TLS hostname lỗi** | Certificate SAN khác tên gọi, SNI/proxy config | TLS validation logs, server certificate |
| **Policy object tồn tại nhưng traffic vẫn đi được** | CNI không enforce, selectors không match, policy khác allow | CNI/policies, controlled negative test |
| **Sau rollout kết nối cũ reset** | Pod termination, conntrack, readiness, connection drain | Pod lifecycle, TCP/gateway logs |
| **IPv4 chạy, IPv6 lỗi hoặc lộ ngoài dự kiến** | LB dual-stack, AAAA, IPv6 SG/ACL, CNI, route | IPv6 test, Service families, flow logs |

### 32.1. Một checklist điều tra theo thứ tự

1. **Client đang gọi tên/IP/port nào?** ClusterIP, NodePort, LB, Ingress hay một endpoint phụ?
2. **Service type, ports và selector là gì?**
3. **EndpointSlice có endpoint đủ điều kiện không?**
4. **Đích backend có listener và có Ready không?**
5. **Đường đi L3/L4 và NetworkPolicy có cho phép không?**
6. **CNI/kube-proxy/eBPF dataplane hoặc LB controller có healthy không?**
7. **Ứng dụng có trả HTTP/TLS/auth lỗi riêng không?**
8. **ID/log ở lớp nào giúp xác định chính xác vị trí lỗi?**
9. **Có IPv6, hostNetwork, externalIPs, direct NodePort hoặc route bypass không?**

Không giải quyết mọi vấn đề bằng **mở SG 0.0.0.0/0, xóa NetworkPolicy hoặc thay Service thành LoadBalancer public**.

## 33. Runbook triển khai Service an toàn

### Bước 1 — Xác định đối tượng truy cập

Ghi rõ **service owner, namespaces, cluster, môi trường, callers, ports, protocols, data classification**. Nếu chỉ Pod nội bộ gọi, ưu tiên **ClusterIP**. Nếu public API, chọn **Ingress/API Gateway đã phê duyệt** với private backend, không tự tạo LoadBalancer cho từng backend nhạy cảm.

### Bước 2 — Thiết kế ranh giới truy cập

Vẽ **Internet → CDN/WAF → LB → ingress/controller → ClusterIP → Pod → data store** hoặc mô hình riêng tương ứng. Kiểm kê **NodePort, externalIPs, hostNetwork, peering/VPN, IPv4/IPv6** để không bỏ sót đường phụ.

### Bước 3 — Chọn Service type và port

Dùng **ClusterIP** khi chỉ cần nội bộ, **NodePort** chỉ khi đã có lý do vận hành/route/firewall/owner, **LoadBalancer** khi có controller và external/internal front end được phê duyệt. Không dùng port cố định tùy tiện hoặc source ranges mơ hồ.

### Bước 4 — Kiểm soát danh tính và cấu hình

- RBAC giới hạn ai được tạo/patch Service, EndpointSlice và Ingress/Gateway.
- Admission policy kiểm tra Service type, externalIPs, source CIDR, LB annotation/class và labels.
- Cloud IAM giới hạn permissions của LB controller.
- IaC/Helm/Kustomize được review, có owner, change ID, plan/diff và rollback.

### Bước 5 — Thiết kế NetworkPolicy và identity

Áp **default deny có kiểm soát** rồi allow đúng **caller Pod/namespace, backend ports, DNS, health/observability traffic** theo thiết kế và CNI. Đặt **TLS/mTLS và API authorization** tại điểm xử lý phù hợp. Không coi namespace hoặc ClusterIP là ranh giới an toàn duy nhất.

### Bước 6 — Canary/staging

Thử **Service DNS, endpoints, readiness, NodePort/LB health, positive/negative reachability, client IP behavior, TLS hostname, IPv4/IPv6** và route ngoài dự kiến. Chỉ dùng identity/endpoint test đã được duyệt.

### Bước 7 — Rollout và theo dõi

Theo dõi **EndpointSlice churn, Pod rollout, LB target health, 5xx, latency, NetworkPolicy denies, cloud IAM/network changes và public exposure inventory**. Nếu chuyển traffic policy Cluster ↔ Local, kiểm tra node placement/health checks để tránh blackout.

### Bước 8 — Thu hồi/cleanup

Khi dịch vụ không còn dùng, xóa đối tượng theo quy trình, xác minh **cloud LB, public IP, security groups/firewall rules, DNS records, service account permissions, policy exceptions** không trở thành orphaned exposure. Đừng mặc định mọi cloud resource biến mất ngay cùng Service object.

~~~mermaid
flowchart TD
    A[Caller + Data Classification] --> B[Chọn Service type và entrypoint]
    B --> C[RBAC/Admission/Cloud IAM Guardrails]
    C --> D[NetworkPolicy + TLS/mTLS + AuthZ]
    D --> E[Staging positive/negative tests]
    E --> F{Allow đúng, deny đúng, health đúng?}
    F -- Không --> G[Fix Service/Endpoint/CNI/LB/Policy]
    G --> E
    F -- Có --> H[Canary production rollout]
    H --> I[Observability + drift/exposure audit]
    I --> J[Decommission/cleanup khi hết dùng]
~~~

## 34. Runbook ứng phó khi Service bị công khai ngoài ý muốn

### Tình huống giả định

SOC phát hiện Service **inventory** trước đó chỉ có ClusterIP nay trở thành **LoadBalancer** có frontend public. Kubernetes audit cho thấy một lần patch Service; cloud audit cũng ghi controller tạo frontend và security group. Chưa xác định đã có client trái phép truy cập hay chưa.

### Giai đoạn 1 — Xác nhận và thu thập

1. Ghi **incident ID, namespace, Service UID/name, owner, time, loại trước/sau, ports, selector, LB address, NodePorts, source ranges, IP families**.
2. Kiểm tra **Kubernetes API audit, IaC change/PR, admission events, controller logs, cloud IAM/network audit** để biết nguồn thay đổi.
3. Xác minh frontend **thực sự reachable từ nguồn nào** qua LB/cloud firewall/route/DNS; không chỉ nhìn **EXTERNAL-IP** rồi kết luận có tấn công.
4. Xem **WAF/ingress bypass, access logs, VPC/flow logs, app auth logs** và các dữ liệu còn trong retention để đánh giá có request thật.
5. Kiểm tra **IPv6, NodePort, externalIPs, hostPort/hostNetwork và các service khác cùng selector**.

### Giai đoạn 2 — Khoanh vùng và chặn exposure

- Nếu đây là thay đổi không được phép, phối hợp owner để **giới hạn nguồn tại LB/cloud firewall hoặc rollback Service tới thiết kế được duyệt**, ưu tiên giảm phơi lộ mà không gây outage lan rộng.
- **Không xóa Service, NetworkPolicy hoặc LB ngay lập tức** khi chưa tính ảnh hưởng, đặc biệt nếu nhiều ứng dụng phụ thuộc.
- Ngăn tái phát qua **admission, RBAC, cloud controller IAM**, xem principal có thể sửa tiếp tài nguyên khác không.
- Nếu có dấu hiệu token/service account bị lộ, xử lý credential lifecycle và Kubernetes/cloud access theo incident plan.
- Bảo toàn audit và traffic metadata; **không ghi/xuất token, body hoặc secrets thô** chỉ để điều tra.

### Giai đoạn 3 — Kiểm chứng

1. **Client hợp lệ** vẫn truy cập được qua đường chuẩn.
2. **Client ngoài allowlist** không thể dùng LB/NodePort/direct-origin.
3. **NetworkPolicy** từ namespace không được phép có hiệu lực.
4. **TLS/mTLS/authorization** vẫn chặn danh tính không hợp lệ.
5. LB/cloud network, DNS, EndpointSlices và IPv4/IPv6 đúng baseline.
6. Các bản ghi SIEM có thể liên kết **Kubernetes actor → Service change → cloud LB creation → traffic**.

### Giai đoạn 4 — Phân tích nguyên nhân

Vấn đề có thể nằm ở **namespace RBAC quá rộng, admission policy không chọn namespace, annotation internal LB không có hiệu lực, provider controller lỗi quyền, CI/IaC sai environment hoặc owner bỏ qua risk review**. Đưa rule tự động phát hiện **NodePort/LoadBalancer mới, externalIPs, public source ranges, LB orphaned** vào quy trình.

**Chỉ khi có evidence về network access và application activity mới kết luận phạm vi truy cập dữ liệu; public exposure không tự chứng minh data exfiltration.**

## 35. Mười hai tình huống thực tế

### A — ClusterIP vẫn bị gọi từ namespace không thuộc quyền

**Triệu chứng:** ứng dụng ở namespace test có thể gọi inventory.shop.svc.cluster.local.

**Giải thích:** **Namespace không phải firewall**. ClusterIP thường truy cập được trong cluster nếu không bị policy khác chặn. Cần CNI thực thi default deny/allow đúng Pod + namespace, mTLS caller identity và API AuthZ. Không chỉ đổi tên Service.

### B — Một Service không có endpoints

**Triệu chứng:** DNS resolve được ClusterIP nhưng request không có backend healthy.

**Kiểm tra:** selector Service, labels Pods, readiness probes, EndpointSlice, targetPort. Không sửa bằng public LB hoặc mở SG; sửa sự không khớp **Service → Pod**.

### C — NodePort reachable từ Internet ngoài dự kiến

**Triệu chứng:** Node có public IP và cloud security group mở dải NodePort, bypass WAF.

**Xử lý:** đóng direct path không được phê duyệt, giới hạn SG/node firewall, review NodePort Service và chuyển qua ingress công bố đúng thiết kế. Duy trì backend auth/NetworkPolicy.

### D — NodePort chỉ chạy trên vài node sau khi bật Local

**Triệu chứng:** client tới node A thành công, node B timeout.

**Phân tích:** **externalTrafficPolicy: Local** chỉ chuyển đến endpoint local; node B có thể không có Pod sẵn sàng. Cần LB health check/target selection, deployment topology và failover; không mở cả NodePort cho Internet để thử.

### E — LB có IP nhưng health checks fail

**Triệu chứng:** status.loadBalancer.ingress đã có IP, nhưng LB không healthy.

**Kiểm tra:** backend node/pod health, target port, network policy/CNI, SG, firewall, Local endpoint distribution, readiness và healthCheckNodePort khi áp dụng.

### F — LoadBalancer vô tình public

**Triệu chứng:** service nội bộ được tạo type LoadBalancer, controller mặc định cấp public frontend.

**Xử lý:** xác minh internal LB mechanism của provider, giới hạn IAM/admission, cloud source ranges, rollback và kiểm tra đã có traffic ngoài danh sách chưa. **Không coi LB type là internal mặc định**.

### G — externalTrafficPolicy Local nhưng ứng dụng vẫn thấy IP proxy

**Triệu chứng:** Pod source IP không phải IP user.

**Giải thích:** CDN/L7 proxy/LB đã NAT trước node hoặc dataplane có behavior khác. Cần trusted proxy chain và source IP logs ở điểm vào; không tin XFF do Internet client tự điền.

### H — NetworkPolicy được tạo nhưng không chặn

**Triệu chứng:** Pod lạ vẫn gọi được inventory dù default deny manifest đã áp.

**Điều tra:** CNI có thực thi NetworkPolicy không, podSelector/namespaceSelector có match không, có policy khác mở thêm không, traffic đến từ hostNetwork/node hoặc NAT có đặc thù không. **Policy object hiện diện không chứng minh enforcement.**

### I — Chuyển sang headless Service làm client thay đổi behavior

**Triệu chứng:** ứng dụng nhận nhiều Pod IP từ DNS, connection persistence/failover khác trước.

**Giải thích:** headless không dùng VIP kube-proxy theo mô hình thông thường; **client tự chọn endpoint**. Cần retry, DNS TTL/caching và TLS identity phù hợp; không tự dùng headless để thay LoadBalancer công khai.

### J — API trả 403 dù Service healthy

**Triệu chứng:** EndpointSlices, TCP và LoadBalancer đều healthy, nhưng API trả 403.

**Giải thích:** 403 có thể do **Ingress/WAF/gateway auth hoặc backend object authorization**; không phải Service routing lỗi. Tra request ID, policy decision và verified identity, không tắt WAF/mTLS để xử lý.

### K — Sau rollout, vài requests 502 và connections reset

**Triệu chứng:** Pod replacement nhanh, Service endpoints đổi, một số kết nối cũ thất bại.

**Phân tích:** readiness, preStop/terminationGracePeriod, drain của ingress/LB, conntrack/keepalive và dependency behavior. Service không tự đảm bảo zero-downtime; cần graceful termination và readiness test.

### L — Cloud LB bị xóa nhưng NodePort vẫn tồn tại

**Triệu chứng:** team nghĩ đã hết public exposure vì không còn LB, nhưng Service vẫn có NodePort và node firewall mở.

**Xử lý:** kiểm tra Service type/ports, cloud LB resources, NodePorts còn được cấp, node public IP và SG/routing. Không chỉ rà soát danh sách cloud LBs; inventory cần nhìn **mọi kiểu entrypoint**.

## 36. Ma trận 40 kiểm thử an toàn

Tất cả test chỉ chạy trong **cluster hoặc môi trường test được cấp phép**; kiểm thử network reachability dùng test Pods/users hợp lệ. Không quét Internet, không thử thay Service production không được phê duyệt, không dùng traffic gây quá tải.

| ID | Kịch bản | Kết quả mong đợi | Bằng chứng |
|---|---|---|---|
| **T-01** | ClusterIP Service có đúng selector/Pod labels | Backend EndpointSlices đúng | Service/Pod/EndpointSlice |
| **T-02** | Client cùng namespace gọi ClusterIP | Thành công khi policy cho phép | Test request + Pod logs |
| **T-03** | Client namespace ngoài allowlist gọi ClusterIP | Bị chặn bởi NetworkPolicy/CNI | Denied flow/test result |
| **T-04** | Pod selector sai nhãn | Không có endpoint phù hợp | EndpointSlice + Pod labels |
| **T-05** | Backend chưa Ready | Không được chọn như endpoint sẵn sàng theo policy | Readiness/EndpointSlice |
| **T-06** | targetPort sai | Phát hiện fail, không tự mở cổng tùy ý | App listener/connection test |
| **T-07** | DNS Service FQDN đúng | Resolve VIP/records theo mode | Cluster DNS test |
| **T-08** | DNS sai namespace | Không nhầm FQDN giữa các namespaces | DNS/route check |
| **T-09** | NodePort tự cấp trong dải hợp lệ | Service có nodePort đúng | Service spec |
| **T-10** | NodePort được khai báo trùng trong lab | API validation không nhận cấu hình xung đột | Admission/API response |
| **T-11** | NodePort với public SG bị chặn theo policy | Internet source ngoài danh sách không reachable | Node/cloud firewall test |
| **T-12** | NodePort chỉ reachable từ VPN/private | Client được cấp quyền thành công | VPN/route/firewall logs |
| **T-13** | NodePort externalTrafficPolicy Cluster | Đường liên node phù hợp với CNI | Per-node/Pod test |
| **T-14** | NodePort externalTrafficPolicy Local có local Pod | Node nhận local traffic phù hợp | Endpoint placement |
| **T-15** | NodePort Local không có local endpoint | Không gửi tới Pod trên node khác | Per-node test/LB health |
| **T-16** | LoadBalancer có controller và quota đủ | Được provision đúng class/pool | Events/cloud LB inventory |
| **T-17** | LoadBalancer không có controller | Pending được phát hiện, không tự public workaround | Service status/controller health |
| **T-18** | Internal LB annotation đúng provider | Frontend private như được phê duyệt | Cloud LB state |
| **T-19** | Internal LB annotation không được controller hỗ trợ | Test phát hiện ngoài ý muốn | Admission/cloud config |
| **T-20** | Public LB hạn source ranges | Client ngoài allowlist bị từ chối thực | LB FW/flow logs |
| **T-21** | Service LB có NodePort backend | NodePort cũng nằm trong inventory exposure | Service ports/SG |
| **T-22** | LB direct-to-Pod không cấp NodePort | Controller hỗ trợ và target healthy | LB config/EndpointSlices |
| **T-23** | LB Local health checks sau reschedule | Chỉ node/target healthy được phục vụ | Health checks + Pod placement |
| **T-24** | Traffic source IP preservation | Ghi đúng peer IP/NAT path | Gateway/LB/Pod logs |
| **T-25** | Client tự khai X-Forwarded-For | Không được dùng làm identity đã xác minh | Trusted proxy processing |
| **T-26** | NetworkPolicy default deny ingress | Unauthorized Pod không kết nối được | CNI test logs |
| **T-27** | NetworkPolicy allow Orders → Inventory | Allowed caller đến đúng port | Pod/namespace selector test |
| **T-28** | NetworkPolicy default deny egress + DNS allow | DNS và endpoint cụ thể chạy, nguồn khác bị deny | DNS/CNI tests |
| **T-29** | CNI không hỗ trợ NetworkPolicy | Phát hiện thiếu enforcement trước production | CNI capability report |
| **T-30** | Rule chọn Pod labels bị thay ở lab | Detect/reject unauthorized selector drift | Audit/admission |
| **T-31** | App team tạo ClusterIP được phép | Admission/RBAC allow | Kubernetes API audit |
| **T-32** | App team yêu cầu NodePort ngoài policy | Admission deny | Policy response/audit |
| **T-33** | App team yêu cầu LB public không duyệt | Admission deny | Admission/cloud controller |
| **T-34** | externalIPs ngoài allowlist | Request bị từ chối theo policy | Admission test |
| **T-35** | Direct-to-origin/NodePort bypass WAF | Path không được cho phép bị chặn | SG/CNI/network logs |
| **T-36** | Service API qua TLS/mTLS với wrong identity | Certificate/AuthZ deny theo thiết kế | TLS/app security event |
| **T-37** | IPv4/IPv6 dual-stack exposure | Cả hai họ IP đúng allow/deny | LB/DNS/CNI/flow test |
| **T-38** | Backend rollout/drain | Healthy requests tiếp tục theo SLO, lỗi được phân tích | EndpointSlice/ingress/SLO |
| **T-39** | Kubernetes Service thay đổi qua CI | Audit actor/change ID và cloud resource mapping | API + cloud audit |
| **T-40** | Xóa Service test | LB/NodePort/SG/DNS cleanup theo controller | Cloud/network inventory |

### 36.1. Phải kiểm thử cả ALLOW và DENY

Nếu chỉ thử **client hợp lệ kết nối được**, bạn chưa chứng minh NodePort không public hoặc namespace lạ không thể gọi Service. Nếu chỉ thử **DENY**, có thể security policy đã cắt luôn DNS, health probes, monitoring hoặc các service hợp lệ. Một triển khai an toàn phải có **positive và negative tests** với evidence ở đúng lớp.

### 36.2. NetworkPolicy và Service cùng test nhưng không cùng nghĩa

- **Service check:** VIP/DNS/endpoint/port có được cấu hình và load balance đúng không?
- **NetworkPolicy check:** Pod/namespace/port được phép hoặc từ chối theo security intent không?
- **Cloud firewall/LB check:** nguồn ngoài cluster có thể đến node/LB theo allowlist không?
- **TLS/AuthZ check:** peer/user/service identity và quyền truy cập API có hợp lệ không?
- **Observability check:** log không bị mất và event mapping đúng không?

## 37. Những ngộ nhận thường gặp

| Ngộ nhận | Giải thích đúng |
|---|---|
| **“Service có IP ổn định nghĩa Pod IP cũng ổn định.”** | Service VIP/DNS trừu tượng hóa backend Pod IP có thể thay. |
| **“ClusterIP không thể bị truy cập trái phép.”** | Pod khác, route/VPN phù hợp hoặc đường đặc biệt có thể tiếp cận; cần NetworkPolicy và AuthZ. |
| **“Namespace là firewall.”** | Namespace là ranh giới quản lý, không tự chặn network traffic. |
| **“NodePort tự có public IP.”** | NodePort chỉ cấp node port; public reachability phụ thuộc node addresses/route/firewall. |
| **“NodePort chỉ chạy trên node có Pod.”** | Mode Cluster có thể forward sang node khác; Local hạn backend local. |
| **“LoadBalancer luôn public.”** | Internal/private frontend tùy controller/provider config. |
| **“LoadBalancer luôn có WAF/TLS.”** | LB không tự cung cấp những tính năng này. |
| **“EXTERNAL-IP pending là Pod lỗi.”** | Có thể do chưa có LB controller, quota, IAM/class hoặc subnet. |
| **“LoadBalancer không còn NodePort.”** | Nhiều controller vẫn cấp NodePort; trường tắt cấp chỉ phù hợp mode được hỗ trợ. |
| **“externalTrafficPolicy: Local bảo toàn IP client bất kể mọi proxy.”** | Lớp trước node có thể đã NAT hoặc proxy; cần xem toàn đường. |
| **“Service traffic chia đều từng HTTP request.”** | Dataplane thường cân bằng kết nối/flow; keepalive và policy ảnh hưởng distribution. |
| **“Service tự quản lý quyền truy cập người dùng.”** | Cần TLS/mTLS, IAM, AuthN/AuthZ và ứng dụng. |
| **“Có NetworkPolicy object tức đã chặn traffic.”** | CNI phải hỗ trợ và enforce đúng. |
| **“NetworkPolicy chọn Service ClusterIP như một firewall L7.”** | NetworkPolicy chuẩn chủ yếu chọn Pods/IPBlocks/ports ở L3/L4. |
| **“Một NetworkPolicy deny sẽ có ưu tiên cao nhất.”** | NetworkPolicy chuẩn chủ yếu có additive allow semantics, không thứ tự deny rule. |
| **“Chặn DNS là chặn mọi truy cập Service.”** | Client có thể dùng ClusterIP trực tiếp hoặc cache DNS. |
| **“Pod Ready nghĩa ứng dụng an toàn.”** | Readiness không kiểm tra authentication/permissions hay mã độc. |
| **“Headless Service hoạt động như ClusterIP VIP.”** | Nó không có VIP thông thường; DNS thường trả endpoints. |
| **“ExternalName tự proxy và xác minh TLS.”** | Nó cung cấp DNS alias; app/client phải xác thực endpoint thực. |
| **“Không có LoadBalancer thì không có đường public nào khác.”** | NodePort, externalIPs, hostPort/hostNetwork hoặc route khác có thể tồn tại. |
| **“RBAC giới hạn được Service type bằng verb create.”** | RBAC theo resource/verb; muốn hạn spec fields cần admission policy. |
| **“Ingress đã được WAF bảo vệ thì mọi đường vào Pod đều được bảo vệ.”** | Direct NodePort/origin/LB khác có thể bypass. |
| **“Một 403/502 đều là Service routing lỗi.”** | 403 thường liên quan security/app; 502 có thể từ ingress/backend/health. |
| **“IPv4 firewall đủ cho cluster dual-stack.”** | IPv6 ::/0/routes/LB và AAAA cần policy/test riêng. |
| **“Port-forward thành công nghĩa NetworkPolicy cho phép.”** | Port-forward dùng đường quản trị khác Service data path. |
| **“Xóa Service chắc chắn xóa ngay cloud firewall/LB resource.”** | Controller cleanup có thể trễ/lỗi; phải kiểm tra inventory. |

## 38. Checklist đưa Service vào production

- [ ] Đã xác định service owner, callers, phân loại dữ liệu, môi trường, network trust boundary.
- [ ] Mặc định backend không cần external access dùng **ClusterIP**.
- [ ] Service selector chọn đúng Pod labels; không vô tình chọn Pod test/admin.
- [ ] Có endpoint Ready và targetPort đúng listener thực tế.
- [ ] Service DNS, cluster domain và namespace được xác minh.
- [ ] CNI/dataplane hỗ trợ các tính năng NetworkPolicy/Service networking dự kiến.
- [ ] Có default-deny và explicit NetworkPolicy allow theo caller/port khi thích hợp.
- [ ] DNS, observability, probes và dependencies cần thiết được allow đúng scope.
- [ ] Đã kiểm thử Pod ở namespace khác **không** truy cập trái quyền.
- [ ] Không coi Service VIP/namespace là danh tính hoặc firewall.
- [ ] Từng workload/ứng dụng có AuthN/AuthZ; TLS/mTLS đúng trust boundary.
- [ ] Không mặc định trust X-Forwarded-For do client gửi.
- [ ] Đã phân biệt port, targetPort và nodePort; tránh port xung đột.
- [ ] Mọi NodePort được kiểm kê, có lý do, owner, firewall và hạn truy cập.
- [ ] NodePort không thể bị dùng như direct-to-origin bypass ngoài thiết kế.
- [ ] externalTrafficPolicy Cluster/Local được chọn theo source IP, health và placement.
- [ ] internalTrafficPolicy Local được test khi node không có endpoint local.
- [ ] LoadBalancer controller/Class và cloud IAM phù hợp, có audit.
- [ ] Public/private LB đã được xác minh trong **cloud state**, không chỉ theo annotation.
- [ ] loadBalancerSourceRanges được enforce thực, gồm IPv4/IPv6 theo support.
- [ ] Đã kiểm tra nodePort allocation, direct-to-Pod LB mode và đường phụ.
- [ ] Cloud SG/NSG/firewall/subnet route, private endpoints và peering được review.
- [ ] Ingress/Gateway/API gateway có TLS, WAF, rate limit và policy theo yêu cầu.
- [ ] Backend có network policy chỉ cho ingress/controller/service caller đúng.
- [ ] hostNetwork, hostPort, externalIPs, ExternalName và port-forward được quản trị.
- [ ] Headless Service không bị nhầm là LB VIP hoặc security boundary.
- [ ] Không mở ClusterIP/NodePort tới toàn mạng chỉ để chữa lỗi DNS/timeout.
- [ ] Kubernetes RBAC hạn Service/EndpointSlice/Ingress/Gateway mutation.
- [ ] Admission policy ngăn LoadBalancer public/NodePort ngoài chính sách.
- [ ] Người sửa admission policy/cloud controller IAM có quyền hạn tách biệt.
- [ ] Service changes nằm trong IaC và được review, có rollback.
- [ ] Có logs từ Kubernetes API, cloud LB, ingress/WAF, CNI và ứng dụng.
- [ ] Alert cho public LB/NodePort mới, externalIPs, endpoint zero và source ranges drift.
- [ ] IPv4/IPv6, DNS A/AAAA, LB, firewall và TLS đã được kiểm thử.
- [ ] Có test ALLOW cho caller hợp lệ và DENY cho caller ngoài scope.
- [ ] Đã kiểm tra load balancing, draining và readiness khi rollout/failover.
- [ ] Có runbook xử lý EXTERNAL-IP pending, no endpoints, 502/503, NAT/source IP.
- [ ] Khi decommission, kiểm tra orphaned cloud LB/public IP/firewall/DNS.
- [ ] Không chạy thử network scans, mutate Service hoặc xuất logs nhạy cảm ngoài phạm vi được phép.

## 39. Câu hỏi tự kiểm tra

**1. Vì sao cần Kubernetes Service khi Pod đã có IP?**  
Vì Pod IP có thể thay khi Pod restart/reschedule; Service cung cấp điểm truy cập logic, DNS và cơ chế lựa chọn backend.

**2. ClusterIP và Pod IP khác nhau thế nào?**  
ClusterIP là địa chỉ Service VIP, Pod IP thuộc endpoint cụ thể. Dataplane chuyển traffic từ Service tới Pod theo trạng thái endpoint.

**3. NodePort có bắt buộc tạo public IP không?**  
Không. Nó cấp cổng trên node theo cơ chế Service; client có truy cập được không phụ thuộc node interfaces, route, SG/firewall và cấu hình.

**4. Dải NodePort mặc định của Kubernetes là bao nhiêu?**  
Thông thường là **30000–32767**, có thể được cluster administrator cấu hình khác.

**5. LoadBalancer Service có tự cung cấp HTTPS/WAF và AuthZ không?**  
Không. Những kiểm soát này cần LB/controller, ingress/API gateway, service mesh hoặc ứng dụng hỗ trợ và được cấu hình đúng.

**6. Khi nào một Service type LoadBalancer không có EXTERNAL-IP?**  
Có thể do không có controller, provider chưa cấp, class/annotation không phù hợp, quota/IAM/subnet lỗi hoặc provisioning đang xử lý.

**7. port, targetPort và nodePort khác nhau?**  
port là cổng Service, targetPort là cổng backend Pod, nodePort là cổng node nhận traffic cho NodePort/LoadBalancer khi được cấp.

**8. ExternalTrafficPolicy: Local có tác dụng chính nào?**  
Chỉ chuyển external traffic tới endpoint local trên node, giúp bảo toàn source IP trong một số đường đi nhưng cần cân nhắc endpoint placement và LB health checks.

**9. Vì sao Local không luôn giữ được IP người dùng?**  
Một CDN/L7 proxy/LB trước node có thể SNAT, nên IP nhìn ở Pod đã là địa chỉ của proxy.

**10. Một NetworkPolicy tồn tại có đồng nghĩa CNI đang chặn không?**  
Không. CNI phải hỗ trợ và thực thi; policy selectors/allow rules cũng phải được kiểm tra thực.

**11. Vì sao namespace không phải security boundary mạng?**  
Vì Pod ở namespace khác có thể truy cập Service nếu không có policy/enforcement ngăn cản.

**12. Default deny ingress + egress có thể làm hỏng gì?**  
DNS, kết nối đến backend/dependencies, metrics, probes và luồng quản lý nếu chưa tạo các allow rules phù hợp.

**13. Ingress và LoadBalancer Service giống nhau không?**  
Không. Ingress mô tả host/path HTTP routing cho controller; LoadBalancer Service yêu cầu dataplane LB frontend, thường dùng để công bố ingress controller.

**14. Headless Service khác ClusterIP VIP ở đâu?**  
Nó có clusterIP: None và DNS có thể trả endpoint IPs trực tiếp thay vì một VIP thông thường.

**15. ExternalName có tạo L4 load balancing không?**  
Không. Nó chủ yếu cung cấp DNS alias/CNAME; client và endpoint TLS vẫn cần được xác minh đúng.

**16. Một app có WAF ở Ingress nhưng NodePort công khai có vấn đề gì?**  
Client có thể đi trực tiếp NodePort bypass Ingress/WAF; cần đóng/giới hạn đường NodePort và bảo vệ backend độc lập.

**17. Vì sao tạo/sửa Service cần RBAC và admission?**  
RBAC giới hạn principal và verb; admission kiểm tra **spec type, externalIPs, LB mode, source ranges, labels** để ngăn cấu hình public ngoài chính sách.

**18. Khi thấy Service DNS phân giải đúng nhưng không kết nối được, kiểm tra gì?**  
EndpointSlice, readiness, selector, targetPort, network policy, CNI/routing, LB health và app listener theo đường đi.

**19. Vì sao một Service có ba Pods không đồng nghĩa chia đúng 1/3 requests?**  
Service dataplane có thể cân bằng ở kết nối/flow, cùng keepalive, session affinity, health/locality ảnh hưởng distribution.

**20. Một public LB xuất hiện ngoài kế hoạch có chứng minh dữ liệu đã bị lấy không?**  
Không. Phải xác minh reachability, traffic flows, ứng dụng/AuthZ logs và thời gian phơi lộ; public exposure là rủi ro cần xử lý nhưng không tự chứng minh exfiltration.

## 40. Tài liệu tham khảo

- [Kubernetes — Service](https://kubernetes.io/docs/concepts/services-networking/service/): khái niệm Service, ClusterIP, NodePort, LoadBalancer, traffic policies, EndpointSlices và các lựa chọn Service.
- [Kubernetes — NetworkPolicy](https://kubernetes.io/docs/concepts/services-networking/network-policies/): semantics ingress/egress, isolation và yêu cầu CNI.
- [Kubernetes — EndpointSlices](https://kubernetes.io/docs/concepts/services-networking/endpoint-slices/): khám phá backend endpoints, readiness và topology.
- [Kubernetes — DNS for Services and Pods](https://kubernetes.io/docs/concepts/services-networking/dns-pod-service/): tên DNS và quy tắc phân giải trong cluster.
- [Kubernetes — kube-proxy](https://kubernetes.io/docs/reference/command-line-tools-reference/kube-proxy/): dataplane Service và các lựa chọn vận hành.
- [Kubernetes — Ingress](https://kubernetes.io/docs/concepts/services-networking/ingress/): HTTP routing, TLS và Ingress controller.
- [Kubernetes — Gateway API](https://gateway-api.sigs.k8s.io/): API route/gateway/controller và ownership boundary.
- [Kubernetes — Ingress Controllers](https://kubernetes.io/docs/concepts/services-networking/ingress-controllers/): các controller thực thi tài nguyên Ingress.
- [Kubernetes — Service Internal Traffic Policy](https://kubernetes.io/docs/concepts/services-networking/service-traffic-policy/): internal/external traffic policies theo tài liệu phiên bản áp dụng.
- [Kubernetes — Network Policy Recipes](https://github.com/ahmetb/kubernetes-network-policy-recipes): các ví dụ học tập cần kiểm chứng với CNI thực.
- [Kubernetes — RBAC Good Practices](https://kubernetes.io/docs/concepts/security/rbac-good-practices/): quản trị API permissions và least privilege.
- [Kubernetes — Validating Admission Policy](https://kubernetes.io/docs/reference/access-authn-authz/validating-admission-policy/): giới hạn nội dung tài nguyên Kubernetes theo chính sách.
- [Kubernetes — Auditing](https://kubernetes.io/docs/tasks/debug/debug-cluster/audit/): kiểm toán control-plane API, ai thay Service/NetworkPolicy.
- [Kubernetes — Debug Services](https://kubernetes.io/docs/tasks/debug/debug-application/debug-service/): kiểm tra Service, DNS, EndpointSlices và dataplane khi kết nối lỗi.
- [Kubernetes — Dual-stack networking](https://kubernetes.io/docs/concepts/services-networking/dual-stack/): Service IP families và IPv4/IPv6.
- [Kubernetes — Cloud Controller Manager](https://kubernetes.io/docs/concepts/architecture/cloud-controller/): tích hợp control plane với cloud provider resources.
- [CNCF — CNI](https://www.cni.dev/): giao diện và hệ sinh thái networking plugin trong container environments.
- [NIST SP 800-190 — Application Container Security Guide](https://csrc.nist.gov/pubs/sp/800/190/final): container network isolation, cấu hình và threat model.
- [NIST SP 800-207 — Zero Trust Architecture](https://csrc.nist.gov/pubs/sp/800/207/final): identity, least privilege và phân đoạn kết nối theo policy.
- [OWASP — Kubernetes Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Kubernetes_Security_Cheat_Sheet.html): thực hành bảo vệ cluster, workload, network và RBAC.

**Ghi nhớ:** **Service** là một abstraction để tìm và đưa kết nối tới backend, **không phải một chính sách bảo mật hoàn chỉnh**. **ClusterIP** phù hợp cho giao tiếp nội bộ, **NodePort** mở đường qua cổng node khi mạng cho phép, còn **LoadBalancer** yêu cầu controller cung cấp frontend có thể public hoặc private. Để vận hành an toàn, phải đồng thời kiểm soát **Service selector/EndpointSlice/ports, CNI/NetworkPolicy, NodePort và cloud firewall/LB, TLS/mTLS và application authorization, RBAC/admission/cloud IAM, logging và kiểm thử ALLOW/DENY**. Luôn xác minh đường đi thực tế, kể cả **IPv6, direct NodePort, externalIPs, host networking và các đường bypass ingress**.



