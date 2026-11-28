# Namespace isolation và cross-namespace traffic trong Kubernetes

Một cụm Kubernetes có thể chứa nhiều nhóm ứng dụng: **team-a** vận hành API gateway, **team-b** vận hành catalog service và **data** vận hành database. Mỗi nhóm có namespace, ServiceAccount và quyền RBAC riêng. Nhưng nếu các Pod nằm trên cùng một mạng cluster, một workload trong **team-a** vẫn có thể gọi Service thuộc **team-b**, thậm chí trực tiếp kết nối Pod IP nếu các lớp mạng không hạn chế. **Namespace không mặc nhiên là ranh giới cách ly lưu lượng.**

**Namespace isolation** là thiết kế ranh giới quản trị, danh tính và lưu lượng nhằm ngăn các workload của một namespace truy cập trái phép vào namespace khác. **Cross-namespace traffic** là mọi luồng giữa các workload, Service, controller hoặc điểm ingress/egress thuộc những namespace khác nhau. Để bảo vệ đúng, phải kết hợp **Kubernetes NetworkPolicy (khi CNI thực thi), DNS/service discovery, service identity, TLS/mTLS, authorization, RBAC, admission và các lớp mạng cloud/on-prem**.

Trong mô-đun **SECURITY_NETWORK_SECURITY**, bài học thuộc chương **Bảo mật mạng Kubernetes**, kết nối với phân đoạn mạng, firewall, VPN, IDS/IPS, DNS, NAC, cloud networking và mô hình hóa mối đe dọa. Tập trung vào **cách xác định luồng cần thiết, mặc định từ chối, cấp phép chính xác và kiểm chứng đường đi thực tế**, không xem việc đặt ứng dụng vào hai namespace khác nhau là đủ an toàn.

> **Nguyên tắc cốt lõi:** Namespace **tách phạm vi tên tài nguyên và chính sách quản trị**; **NetworkPolicy** khi được CNI hỗ trợ mới có thể giới hạn traffic L3/L4 tới Pod; **mTLS và authorization** tiếp tục quyết định danh tính và quyền nghiệp vụ. Một phép thử TCP kết nối được không chứng minh lời gọi API được phép, và một manifest NetworkPolicy tồn tại không chứng minh CNI đã thực thi nó.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt **namespace scope, RBAC isolation, Pod network reachability, NetworkPolicy enforcement và application authorization**.
2. Giải thích cách Pod và Service trong **các namespace khác nhau** phát hiện và gọi nhau qua DNS.
3. Hiểu semantics của **podSelector, namespaceSelector, ingress, egress, policyTypes, ports, ipBlock** và quy tắc **cộng dồn (additive union)** của NetworkPolicy.
4. Thiết kế **default-deny ingress/egress** và các rule **allow có mục đích**, bao gồm luồng DNS hợp lệ.
5. Phân biệt **selector AND trong một phần tử**, **OR giữa các phần tử** và trường hợp selector rỗng.
6. Phân tích đường **Service/ClusterIP, Pod IP, Ingress, NodePort, LoadBalancer, Gateway API và cross-namespace references**.
7. Nêu giới hạn của **NetworkPolicy chuẩn** với traffic từ node/hostNetwork, egress theo FQDN, IP translation và chính sách theo HTTP method.
8. Kết hợp **RBAC, ServiceAccount, Pod Security Admission, mTLS/service mesh, secrets và tenant authorization** với NetworkPolicy.
9. Dùng công cụ **chỉ đọc và test có phép** để điều tra DNS failure, policy selector sai, egress bị chặn và workload bypass.
10. Xây ma trận kiểm thử **ALLOW/DENY** và runbook trước/sau khi thay đổi chính sách production.

## 2. Namespace thực sự cô lập những gì?

**Namespace** là phạm vi logic để nhóm nhiều loại resource Kubernetes và đặt tên chúng. Ví dụ Deployment **catalog** trong **team-a** và Deployment **catalog** trong **team-b** không xung đột tên vì nằm trong hai namespace khác nhau.

~~~text
Kubernetes Cluster
|
+-- Namespace: team-a
|     Deployment / Pod / Service / Secret / Role
|
+-- Namespace: team-b
|     Deployment / Pod / Service / Secret / Role
|
+-- Namespace: data
|     StatefulSet / Service / Secret / Role
|
+-- Cluster-scoped resources
      Nodes / Namespaces / ClusterRoles / CRDs / ...
~~~

Namespace giúp phân chia **đối tượng quản trị** và là phạm vi áp dụng cho nhiều chính sách. Nhưng:

- Pod ở namespace A **không được cấp network isolation tự động** khỏi Pod namespace B chỉ vì khác namespace.
- Một số tài nguyên như **Node, Namespace, ClusterRole** là **cluster-scoped**, không thuộc riêng một namespace.
- Quyền **RBAC đối với Kubernetes API** không tự tạo firewall giữa workload A và B.
- Mỗi namespace **không có kernel hoặc cluster control plane riêng**; tenant chia sẻ hạ tầng theo kiến trúc.
- Một **ServiceAccount token** hoặc Kubernetes Secret không mặc nhiên trở nên bất khả tiếp cận trước Pod bị xâm nhập nếu còn lỗi RBAC, mount hoặc lộ credential.

### Ba ranh giới phải phân biệt

| Ranh giới | Ngăn điều gì? | Không tự ngăn điều gì? |
|---|---|---|
| **Namespace naming/scope** | Trùng tên resource trong các namespace; giới hạn phạm vi đối tượng | Pod A kết nối IP/port của Pod B |
| **RBAC** | User/ServiceAccount thao tác Kubernetes API ngoài quyền | TCP/HTTP trực tiếp giữa Pod nếu mạng cho phép |
| **NetworkPolicy/CNI** | Các kết nối L3/L4 không khớp chính sách áp dụng | Caller có JWT hợp lệ cho tenant/resource hay không |

**Đừng dùng từ “namespace isolation” như cam kết bảo mật tuyệt đối** nếu chưa nêu rõ lớp nào được kiểm soát và những đường nào còn ngoại lệ.

## 3. Mô hình mạng Pod mặc định và ý nghĩa an ninh

Kubernetes kỳ vọng mô hình networking cho Pod nơi **Pod có địa chỉ IP trên mạng cluster** và có thể giao tiếp theo cách CNI triển khai. Trong nhiều cụm, Pod ở các namespace khác nhau có thể kết nối nhau bằng **Pod IP hoặc Service**, trừ khi có network policy, firewall hoặc các cơ chế chặn khác.

~~~text
Namespace team-a                      Namespace team-b
----------------                      ----------------
Pod gateway                           Pod catalog
IP 10.244.1.10                        IP 10.244.2.20
        |                                   ^
        | TCP / HTTP :8080                  |
        +-----------------------------------+
                 cluster network

Điều cần kiểm chứng: có NetworkPolicy/CNI/SG/mesh
đang áp một quyết định DENY nào cho flow này không?
~~~

Đây là **mô hình logic**; Pod CIDR, overlay, routing, NAT và nơi áp firewall thay đổi giữa các CNI/cloud provider.

### Vì sao phân namespace không ngăn lateral movement?

Nếu một service trong **team-a** bị xâm nhập, tác nhân có thể cố truy cập Redis/database, API quản trị hoặc metrics của **team-b** nếu đường mạng tới chúng vẫn mở. Namespace có thể che bớt một số object khỏi API theo RBAC, nhưng **không bắt buộc workload chỉ gọi những Service mà nó thấy qua Kubernetes API**. Pod IP, DNS name hoặc địa chỉ được biết qua cấu hình/log vẫn có thể được dùng để mở kết nối.

Đây là lý do **east–west segmentation** phải dựa trên **luồng cần thiết và danh tính**, không chỉ chia folder/tên.

## 4. Defense-in-depth cho nhiều namespace

~~~text
      External / VPN / Partner
                |
         Cloud Firewall / LB
                |
         Ingress / Gateway
                |
     +------------------------+
     | Kubernetes Cluster     |
     |                        |
     | Namespace team-a       |
     |   Pod gateway          |
     |      |                 |
     |      | NetworkPolicy   |
     |      | + mTLS          |
     |      v                 |
     | Namespace team-b       |
     |   Pod catalog          |
     |      |                 |
     |      | NetworkPolicy   |
     |      v                 |
     | Namespace data         |
     |   Database Pod         |
     +------------------------+
                |
        App auth / IAM / Audit
~~~

| Lớp | Câu hỏi phải trả lời |
|---|---|
| **Cloud routing/firewall** | Nguồn mạng nào có route tới cluster/LB/node/Pod? |
| **Gateway/Ingress** | Ai được vào cluster, hostname và TLS termination ở đâu? |
| **NetworkPolicy** | Pod nào được gửi/nhận traffic tới Pod nào ở protocol/port nào? |
| **Service mesh / mTLS** | Workload peer có danh tính được xác thực không? |
| **Application authorization** | Caller có quyền trên method và object/tenant cụ thể không? |
| **Kubernetes RBAC** | Principal nào được quản trị Pod, Service, Secret, NetworkPolicy? |
| **Admission / Pod Security** | Ai được tạo Pod privileged/hostNetwork/hostPath hoặc sửa label? |
| **Observability** | Có bằng chứng ALLOW/DENY, traffic bypass và policy drift không? |

**Phải xác định trách nhiệm của từng lớp.** Một CNI có thể lọc L3/L4 hiệu quả nhưng không tự biết ServiceAccount có được phép đọc hồ sơ của tenant B hay không.

## 5. Service discovery giữa các namespace

Kubernetes DNS thường cho phép Pod tìm Service thuộc namespace khác bằng tên đầy đủ hoặc tên có namespace.

~~~text
Namespace: team-b
Service:   catalog-api
DNS FQDN:  catalog-api.team-b.svc.cluster.local
Port:      8080/TCP (ví dụ)

Caller tại team-a:
  catalog-api.team-b.svc.cluster.local:8080
~~~

**cluster.local là một cluster domain thường gặp**, không cố định ở mọi cluster. Trong thực tế phải kiểm tra **cluster domain, DNS search path và Service names** từ cấu hình được cấp quyền.

### Tên ngắn và tên đầy đủ

| Caller ở namespace team-a dùng | Ý nghĩa có thể |
|---|---|
| **catalog-api** | Trước tiên được phân giải theo search domain của team-a nếu có |
| **catalog-api.team-b** | Có thể được DNS search expansion thành Service ở team-b |
| **catalog-api.team-b.svc.cluster.local** | Chỉ rõ Service và namespace trong cluster domain minh họa |
| **10.244.2.20** | Gọi Pod IP trực tiếp, bypass tên Service nhưng không tự vượt NetworkPolicy |

**DNS resolution không phải authorization.** Việc một Pod resolve được **catalog-api.team-b.svc.cluster.local** không có nghĩa nó được phép kết nối hoặc được phép gọi API. Ngược lại, **chặn DNS** chỉ làm tên khó phân giải, không đảm bảo traffic tới một IP đã biết bị chặn.

### Service không có nghĩa “chỉ namespace cùng tên được gọi”

Kubernetes Service thông thường **không tự chặn nguồn ở namespace khác**. Một Service kiểu **ClusterIP** có thể được các Pod khác trong cluster gọi nếu đường mạng và policy cho phép. Namespace của Service giúp phân định tên/resource, không phải danh sách caller được phép.

## 6. NetworkPolicy: mô hình chuẩn

**NetworkPolicy** thuộc API **networking.k8s.io/v1** mô tả những kết nối mạng nào được phép tới/từ **Pod được chọn**. Chính sách chỉ có hiệu lực khi **network implementation/CNI hỗ trợ và thực thi** chúng.

~~~text
NetworkPolicy object
      |
      +-- namespace (policy scope)
      +-- podSelector (Pod được policy áp dụng)
      +-- policyTypes: Ingress / Egress
      +-- ingress rules: source peers + ports
      +-- egress rules: destination peers + ports
      |
      v
CNI/network dataplane implements allowed flows
      |
      v
Actual Pod traffic
~~~

Những điểm quan trọng:

1. **NetworkPolicy là resource có namespace**; **podSelector chỉ chọn Pod trong namespace chứa policy**.
2. **namespaceSelector** trong ingress/egress peer có thể mô tả các Pod ở namespace khác.
3. **policyTypes** xác định hướng Pod được cô lập theo chính sách.
4. Quy tắc **Ingress** xác định nguồn được phép gửi tới Pod được chọn.
5. Quy tắc **Egress** xác định đích được phép nhận từ Pod được chọn.
6. **Không có explicit deny action với thứ tự ưu tiên first-match trong NetworkPolicy chuẩn**. Đường được phép là hợp của các policy chọn Pod.
7. CNI và cloud dataplane có thể có **chính sách mở rộng** khác NetworkPolicy chuẩn; không suy semantics của chúng chỉ từ resource chuẩn.

### NetworkPolicy chủ yếu diễn đạt L3/L4

Quy tắc có thể chọn nguồn/đích theo Pod/namespace/IP block và cổng/protocol. Nó **không phải firewall theo HTTP method, URL path, gRPC service, JWT claim hoặc user tenant**. Muốn kiểm soát những thuộc tính này cần gateway, service mesh authorization hoặc ứng dụng.

## 7. podSelector chọn Pod nào?

Một NetworkPolicy trong **team-b**:

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: catalog-policy
  namespace: team-b
spec:
  podSelector:
    matchLabels:
      app: catalog-api
  policyTypes:
    - Ingress
  ingress: []
~~~

Khi CNI thực thi đúng, policy này cô lập **ingress** cho **Pod có nhãn app=catalog-api trong namespace team-b**, không trực tiếp chọn Pod cùng nhãn ở team-a.

### Trường hợp selector rỗng

~~~yaml
podSelector: {}
~~~

Ở **spec.podSelector**, một selector rỗng nghĩa là **tất cả Pod trong namespace chứa policy**. Điều đó rất hữu ích để đặt **default-deny ingress/egress cho cả namespace**, nhưng cũng là nguồn sai lầm nếu người viết tưởng **{}** là “không Pod nào”.

### Không giả định mọi Pod có cùng nhãn là cùng workload

Labels là dữ liệu điều phối; nếu tenant có quyền sửa nhãn Pod trong namespace của mình, việc dùng nhãn để cấp quyền mạng **có thể cho phép tenant tự gia nhập tập nguồn được phép**. Chính sách thực tế phải đi cùng **RBAC/admission/namespace ownership** để tránh giả mạo identity bằng cách tự gắn label.

## 8. namespaceSelector và podSelector: AND so với OR

Đây là lỗi cấu hình cross-namespace quan trọng nhất cần hiểu.

### Một phần tử from có cả hai selector: AND

~~~yaml
ingress:
  - from:
      - namespaceSelector:
          matchLabels:
            kubernetes.io/metadata.name: team-a
        podSelector:
          matchLabels:
            app: approved-gateway
    ports:
      - protocol: TCP
        port: 8080
~~~

Ý nghĩa: chỉ những **Pod app=approved-gateway nằm trong namespace team-a** mới khớp phần tử peer đó. Hai selector được **kết hợp AND** trong cùng một phần tử danh sách.

### Hai phần tử from độc lập: OR

~~~yaml
ingress:
  - from:
      - namespaceSelector:
          matchLabels:
            kubernetes.io/metadata.name: team-a
      - podSelector:
          matchLabels:
            app: approved-gateway
    ports:
      - protocol: TCP
        port: 8080
~~~

Ý nghĩa khác hẳn: **mọi Pod trong namespace team-a** *hoặc* **Pod app=approved-gateway trong namespace team-b (namespace chứa policy)** có thể khớp. Đây có thể là quyền lớn hơn nhiều so với dự định ban đầu.

| Cách viết | Tập nguồn được chọn |
|---|---|
| Cả **namespaceSelector + podSelector** trong một phần tử | Pod có nhãn khớp ở namespace có nhãn khớp |
| Hai phần tử, một cái namespaceSelector, một cái podSelector | Hợp của cả namespace được chọn và Pod có nhãn trong namespace policy |
| Chỉ **podSelector** trong một peer | Pod ở **cùng namespace policy** |
| Chỉ **namespaceSelector** | Mọi Pod thuộc namespace được chọn |
| Peer **podSelector: {}** | Tất cả Pod trong namespace policy (nếu không có namespaceSelector đi kèm) |
| Peer **namespaceSelector: {}** | Namespace bất kỳ, theo semantics selector rỗng |

**Không chỉnh indentation bằng cảm tính.** Một dấu gạch đầu dòng YAML có thể thay đổi toàn bộ tập nguồn được phép. Hãy kiểm thử chính những trường hợp bất ngờ: Pod khác trong team-a, Pod cùng nhãn trong team-b và Pod ở namespace không được duyệt.

### Nhãn kubernetes.io/metadata.name

Trong các Kubernetes hiện đại hỗ trợ label chuẩn này, **kubernetes.io/metadata.name** trên Namespace phản ánh tên namespace và giúp selector rõ ràng. Khi làm việc với cluster cũ hoặc môi trường đặc thù, phải **xem nhãn thực tế**. Nếu dùng nhãn tự đặt như **security-zone=trusted**, chỉ nhóm được ủy quyền mới nên có quyền gắn/sửa nhãn làm thay đổi membership của ranh giới bảo mật.

## 9. Ingress isolation và egress isolation là hai quyết định riêng

Giả sử Pod gateway ở **team-a** gọi Pod catalog ở **team-b**.

~~~text
team-a / gateway                  team-b / catalog
          |                               ^
          |  TCP destination port 8080    |
          +-------------------------------+
               egress            ingress
          policy at A        policy at B
~~~

Để lời gọi được phép, theo mô hình NetworkPolicy chuẩn, cần xem:

1. **Egress của source Pod** có bị cô lập hay không? Nếu có, phải có rule egress cho đích.
2. **Ingress của destination Pod** có bị cô lập hay không? Nếu có, phải có rule ingress cho nguồn.
3. Các chính sách khác cùng chọn Pod có đang **cho phép thêm luồng** không?
4. Có cơ chế cloud firewall, CNI extension, mTLS hoặc application auth chặn tiếp không?

### Khi chưa có policy chọn Pod

Theo semantics NetworkPolicy chuẩn, một Pod không bị cô lập theo hướng ingress hoặc egress bởi policy áp dụng thường **không bị giới hạn bởi NetworkPolicy cho hướng đó**, dù cluster còn có các kiểm soát khác. Vì vậy một namespace mới **không tự trở thành default deny** chỉ vì đã tạo namespace.

### Traffic phản hồi

Khi một kết nối được cho phép đi qua theo chính sách, **traffic phản hồi cho kết nối đã được chấp nhận** thường được phép theo semantics NetworkPolicy; không cần tự viết rule reverse chiều như với stateless NACL. Tuy vậy, mức độ tracking và các loại traffic bất thường/phân mảnh có thể phụ thuộc dataplane. **Đừng suy một phép kiểm thử HTTP thành công đủ bao phủ mọi giao thức hoặc CNI**.

## 10. Additive union: nhiều policy không ghi đè nhau

NetworkPolicy chuẩn có semantics **additive**: khi nhiều policy chọn cùng một Pod, các kết nối được cho phép là **hợp của những rule allow áp dụng**. Không có rule “deny có priority cao hơn allow” trong resource này.

~~~text
Policy A cho catalog:
  allow ingress from team-a gateway -> TCP/8080

Policy B cũng chọn catalog:
  allow ingress from any namespace -> TCP/8080

Effective ingress:
  rộng tới bất kỳ namespace được chọn bởi Policy B

Policy A không thể thu hẹp Policy B.
~~~

| Tình huống | Kết quả logic |
|---|---|
| Có một policy **ingress: []** chọn Pod | Pod bị cô lập ingress, trừ khi có policy khác allow |
| Có policy allow A→Pod TCP/8080 | Kết nối A→Pod TCP/8080 được phép trong phạm vi các lớp khác |
| Thêm policy allow B→Pod TCP/8080 | A và B đều có thể được phép |
| Thêm policy default-deny mới khi policy allow-all đã tồn tại | **Không thu hẹp** allow-all đã có |
| Xóa policy allow duy nhất | Những luồng trước đây được allow có thể bị chặn |

**Không có thứ tự policy như firewall rule number.** Muốn giảm quyền, phải tìm mọi policy đang chọn Pod và mọi allow mà chúng cộng lại, bao gồm policy do controller hoặc chart khác tạo.

## 11. Default deny ingress và egress đúng cách

### Default deny ingress cho một namespace

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: default-deny-ingress
  namespace: team-b
spec:
  podSelector: {}
  policyTypes:
    - Ingress
  ingress: []
~~~

Chính sách này chọn **mọi Pod trong team-b** và đưa chúng vào trạng thái ingress isolation. Nếu không có allow policy khác, inbound mới không được phép theo NetworkPolicy semantics, **trong phạm vi CNI thực thi**.

### Default deny egress

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: default-deny-egress
  namespace: team-b
spec:
  podSelector: {}
  policyTypes:
    - Egress
  egress: []
~~~

Điều này cô lập outbound từ Pod team-b. Nếu không có allow bổ sung, những flow như DNS, database, telemetry, token validation và các dịch vụ thiết yếu có thể thất bại. **Không rollout default deny ở production khi chưa kiểm kê dependency và có kế hoạch cứu hộ.**

### Default deny cả hai hướng

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: default-deny-all
  namespace: team-b
spec:
  podSelector: {}
  policyTypes:
    - Ingress
    - Egress
  ingress: []
  egress: []
~~~

**Mục tiêu:** một baseline có thể bổ sung những **allow policy tách biệt** theo nhu cầu. **Cảnh báo:** vì additive union, chỉ có baseline này **không đủ để loại bỏ quyền rộng đã được các NetworkPolicy khác cấp**. Kiểm tra effective policies là bắt buộc.

## 12. Allow ingress từ gateway ở namespace khác

Giả sử **team-b** có Pod **app=catalog-api**, lắng nghe TCP/8080. Chỉ Pod **app=approved-gateway** trong namespace **team-a** được phép gọi catalog theo hợp đồng luồng mạng.

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-team-a-gateway
  namespace: team-b
spec:
  podSelector:
    matchLabels:
      app: catalog-api
  policyTypes:
    - Ingress
  ingress:
    - from:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: team-a
          podSelector:
            matchLabels:
              app: approved-gateway
      ports:
        - protocol: TCP
          port: 8080
~~~

### Cách đọc chính xác

- Policy **nằm trong team-b** và chọn những Pod **app=catalog-api ở team-b**.
- Một phần tử **from** ghép **namespaceSelector AND podSelector**: chỉ gateway Pod có nhãn khớp trong team-a.
- Port **TCP/8080** là **cổng đích của traffic tới catalog Pod**, không phải cổng client source.
- Nếu **không có policy khác mở rộng**, các nguồn khác không được allow bởi policy này cho chiều ingress.
- Nếu team-b đã có **default-deny ingress**, policy trên bổ sung chính xác luồng cần thiết.

**Không được coi việc Pod được mạng cho phép là quyền nghiệp vụ.** Catalog vẫn cần xác thực service identity/user và phân quyền theo API resource/tenant.

### Điều kiện kiểm chứng thêm

1. Nhãn **app=approved-gateway** có thật và chỉ được gắn bởi owner được phép?
2. Namespace **team-a** có đúng nhãn tương ứng không?
3. Catalog Pod có listen TCP/8080 trên Pod IP không?
4. Có policy khác chọn catalog và allow rộng hơn không?
5. Source gateway có **egress isolation** cần rule bổ sung không?
6. CNI đang enforce NetworkPolicy trên những node chạy Pod này không?

## 13. Allow egress từ source namespace tới catalog

Nếu **team-a** dùng default-deny egress, cần rule egress cho **approved-gateway** tới catalog Pod. Ví dụ:

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-catalog-egress
  namespace: team-a
spec:
  podSelector:
    matchLabels:
      app: approved-gateway
  policyTypes:
    - Egress
  egress:
    - to:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: team-b
          podSelector:
            matchLabels:
              app: catalog-api
      ports:
        - protocol: TCP
          port: 8080
~~~

### Hai phía đều quan trọng

~~~text
team-a / approved-gateway             team-b / catalog-api
      |                                       ^
      |  Egress allow to team-b Pod:8080      |
      +---------------------------------------+
                   Ingress allow from team-a gateway

NetworkPolicy allow ở hai đầu
  + route/CNI đúng
  + process lắng nghe
  + TLS/auth/authorization
  => mới có một ứng dụng hoạt động theo ý định.
~~~

**Egress policy trên đặt source gateway vào egress isolation**: nếu gateway còn phải hỏi DNS, gọi identity service, gửi log, truy cập CA hoặc database khác, những egress đó cần policy riêng. Bật policy này đơn lẻ mà chưa lập bảng dependency có thể gây outage.

## 14. DNS egress khi bật default deny

Trong nhiều cluster, workload cần DNS để phân giải **Service khác namespace**. Khi áp default-deny egress, lỗi ứng dụng thường xuất hiện dưới dạng **name resolution timeout** chứ không phải “NetworkPolicy DENY”.

### Ví dụ allow UDP và TCP/53 tới CoreDNS Pod

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-coredns-egress
  namespace: team-a
spec:
  podSelector:
    matchLabels:
      app: approved-gateway
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

### Tại sao không chép nguyên YAML lên mọi cluster?

Đây là **mẫu cho một cấu hình có CoreDNS Pod gắn nhãn k8s-app=kube-dns trong kube-system**, không phải cấu hình phổ quát. Một cluster có thể dùng:

- **NodeLocal DNSCache** hoặc DNS proxy ở node thay vì kết nối trực tiếp Pod CoreDNS.
- DNS resolver của cloud hoặc endpoint riêng với địa chỉ/namespace/label khác.
- **CNI/eBPF service load balancing** thay đổi giai đoạn translation từ ClusterIP sang backend Pod IP.
- DNS over TCP, split-horizon resolver hoặc dịch vụ định danh khác cần kết nối riêng.
- Chính sách cấp cluster hoặc host-network traffic có semantics riêng.

Vì vậy, trước khi tạo allow DNS:

1. Kiểm tra **resolver thực tế của Pod** (không chỉ giả định một Service IP).
2. Xác định **đường đi, địa chỉ đích trước/sau NAT** và CNI áp policy ở đâu.
3. Kiểm tra namespace/Pod labels và DNS port thực đang dùng.
4. Giới hạn chỉ resolver được phê duyệt, không mở outbound DNS tới Internet tùy ý.
5. Thử cả **DNS resolution và TCP application call**; DNS PASS chưa chứng minh API được phép.

### Vì sao DNS cần TCP/53?

DNS thông thường dùng UDP/53, nhưng TCP/53 cũng là một phần của DNS trong nhiều điều kiện. Đừng cho rằng “chỉ allow UDP” luôn đủ. Nếu dùng DoT/DoH hoặc managed DNS khác, giao thức/port/đích thay đổi và cần được kiểm kê riêng.

## 15. Cho phép traffic cùng namespace có kiểm soát

Namespace không mặc định cho mọi Pod trong nó được liên lạc nếu default-deny policy đã cô lập traffic. Có thể thiết kế cho phép một số kết nối **cùng namespace**, nhưng phải tránh vô tình coi toàn bộ namespace là trust domain đồng nhất.

### Allow tất cả Pod cùng team-b tới TCP/9090 (chỉ ví dụ)

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-same-namespace-metrics
  namespace: team-b
spec:
  podSelector:
    matchLabels:
      app: catalog-api
  policyTypes:
    - Ingress
  ingress:
    - from:
        - podSelector: {}
      ports:
        - protocol: TCP
          port: 9090
~~~

**Peer podSelector: {}** ở đây chọn **mọi Pod trong team-b**, không phải “không Pod nào” hoặc “mọi Pod trong cluster”. Với namespace có nhiều tenant/workload, việc cho cả namespace truy cập metrics có thể quá rộng.

### Phiên bản chặt hơn

~~~yaml
ingress:
  - from:
      - podSelector:
          matchLabels:
            app: approved-metrics-collector
    ports:
      - protocol: TCP
        port: 9090
~~~

Lần này chỉ Pod **app=approved-metrics-collector ở team-b** được chọn bởi peer. Nếu collector nằm namespace khác, dùng **namespaceSelector AND podSelector** và bảo vệ quyền gắn nhãn.

**Cùng namespace không đồng nghĩa cùng quyền trên dữ liệu.** Đặt một môi trường dev thử nghiệm và ứng dụng production vào chung namespace làm phức tạp ranh giới trust, nhưng tách namespace thôi chưa thay thế NetworkPolicy.

## 16. ipBlock: khi nào nên dùng CIDR?

**ipBlock** giúp mô tả những mạng/IP theo CIDR, thường hữu ích cho **đích ngoài tập Pod được chọn bằng labels** như mạng đối tác hoặc địa chỉ dịch vụ bên ngoài cluster.

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-partner-https
  namespace: team-a
spec:
  podSelector:
    matchLabels:
      app: approved-gateway
  policyTypes:
    - Egress
  egress:
    - to:
        - ipBlock:
            cidr: 203.0.113.0/24
            except:
              - 203.0.113.128/25
      ports:
        - protocol: TCP
          port: 443
~~~

**203.0.113.0/24 là dải IP dành cho tài liệu**, không phải địa chỉ đối tác thật để deploy. Trong môi trường thực, IP allowlist phải dựa trên thỏa thuận và thay đổi được quản lý.

### Những lưu ý quan trọng

- Một **ipBlock** chỉ nhìn địa chỉ, không xác minh danh tính máy chủ hay người dùng.
- **except** chỉ loại trừ một dải nằm trong cidr theo cú pháp chính sách; không phải thứ tự firewall rule.
- IP của Pod/Service có thể được cấp phát và chuyển đổi theo CNI; **không nên dùng ipBlock để thay thế namespaceSelector/podSelector cho traffic giữa các Pod** nếu muốn chính sách bền theo workload.
- Với **ClusterIP/NodePort/LoadBalancer**, việc policy nhìn **địa chỉ trước hay sau DNAT/SNAT** phụ thuộc implementation và đường đi; không suy một ipBlock cố định luôn áp đúng.
- Khi cần kiểm soát **FQDN hoặc URL**, NetworkPolicy chuẩn không cung cấp bộ lọc tên miền hoặc HTTP path ổn định; có thể cần egress gateway/proxy hoặc tính năng mở rộng được kiểm chứng.

## 17. Service và Pod IP: policy thực sự chọn đối tượng nào?

NetworkPolicy chuẩn áp dụng cho **Pod**, không trực tiếp là một resource **Service**. Service là abstraction định tuyến load balancing tới các backend Pod hoặc endpoint theo cấu hình.

~~~text
Gateway Pod team-a
       |
       | DNS: catalog-api.team-b.svc.cluster.local
       v
ClusterIP Service team-b
       |
       +----> Pod catalog-1 (10.244.2.20)
       |
       +----> Pod catalog-2 (10.244.3.21)
                         |
             NetworkPolicy at destination Pod
~~~

### Khi Service đã có đúng DNS nhưng request vẫn lỗi

- **EndpointSlice** không có ready endpoint phù hợp vì selectors/readiness sai.
- Service **port/targetPort** khác cổng thực sự lắng nghe trong Pod.
- Source bị **egress deny** hoặc destination bị **ingress deny**.
- NetworkPolicy chọn Pod theo **label khác** với Service selector.
- Gateway/sidecar/service mesh yêu cầu mTLS hoặc identity riêng.
- CNI dataplane hoặc route trên node gặp lỗi.
- Backend ứng dụng trả **401/403/5xx**, không phải L3/L4 denial.

**Service selector và NetworkPolicy selector là hai tập logic độc lập**. Việc Service chọn đúng Pod không bảo đảm policy cho phép source gọi Pod ấy, và việc policy cho phép Pod không bảo đảm Service có endpoint sẵn sàng.

## 18. Cross-namespace traffic qua Ingress, NodePort và LoadBalancer

Một yêu cầu từ bên ngoài không nhất thiết xuất phát từ Pod trong namespace khách hàng. Nó có thể đi qua các proxy, node và địa chỉ được NAT trước khi tới backend.

~~~text
Internet / Partner / VPN
         |
    Cloud LoadBalancer
         |
  Ingress/Gateway controller
    namespace ingress-system
         |
       Service team-b
         |
       Pod catalog team-b
~~~

### Từng điểm cần xem

| Điểm | Câu hỏi an ninh |
|---|---|
| **Cloud LB / firewall** | Public hay private? Nguồn CIDR nào được phép tới listener? |
| **Ingress controller/Gateway** | Namespace nào điều hành route và TLS? Auth/rate limit ở đâu? |
| **Service type ClusterIP** | Có đường từ gateway tới backend Pod không? |
| **NodePort** | Cổng trên node có reachable từ mạng bên ngoài không? |
| **LoadBalancer Service** | Provider đã tạo public endpoint ngoài ý định chưa? |
| **Destination NetworkPolicy** | Nó nhìn traffic đến từ gateway Pod, node IP hay địa chỉ sau NAT? |
| **App** | Request có identity hợp lệ và đúng quyền method/tenant không? |

**Không tự suy rằng chọn namespace ingress-system trong NetworkPolicy là đủ** nếu traffic của ingress controller tới backend không xuất hiện với Pod source identity mong đợi do hostNetwork, node traffic hoặc NAT. Phải đo packet path và đối chiếu tài liệu CNI.

### Quyền cross-namespace route không bằng network reachability

Việc người quản trị được phép tạo một Ingress/Gateway route trỏ tới một Service **không làm NetworkPolicy tự mở đường**, cũng không tự cấp quyền nghiệp vụ. Ngược lại, một network allow có thể vẫn cho kết nối trực tiếp tới Pod/Service nếu route hoặc network path cho phép, kể cả khi không có Ingress route tương ứng.

## 19. Gateway API ReferenceGrant và tham chiếu qua namespace

**Gateway API** có cơ chế quản lý **route attachment** và **cross-namespace references**. Khi một route nằm ở một namespace tham chiếu backend Service ở namespace khác, resource **ReferenceGrant** thường được dùng để namespace sở hữu đích **cho phép tham chiếu** theo mô hình Gateway API.

### Ví dụ Service ở team-b cho phép HTTPRoute team-a tham chiếu

~~~yaml
apiVersion: gateway.networking.k8s.io/v1beta1
kind: ReferenceGrant
metadata:
  name: allow-team-a-route-to-catalog
  namespace: team-b
spec:
  from:
    - group: gateway.networking.k8s.io
      kind: HTTPRoute
      namespace: team-a
  to:
    - group: ""
      kind: Service
      name: catalog-api
~~~

Đây là **mẫu minh họa có điều kiện**: chỉ áp dụng khi cluster đã cài Gateway API CRDs/controller hỗ trợ **ReferenceGrant** đúng version/schema hiện hữu. Một số phiên bản Gateway API công bố **ReferenceGrant ở version khác**, do đó phải kiểm tra discovery trước khi sử dụng. **Không deploy nguyên mẫu chưa xác nhận version**.

### Hai quyền độc lập

1. **Route attachment:** Gateway listener quy định loại route nào và namespace nào được phép gắn thông qua **allowedRoutes** hoặc cơ chế hỗ trợ.
2. **Backend reference:** Namespace team-b có thể dùng ReferenceGrant để chấp thuận route từ team-a tham chiếu Service catalog.

**ReferenceGrant không phải NetworkPolicy**, không cấp quyền TCP/8080 từ gateway tới Pod và không thay authorization trong catalog. Nó giải quyết **quyền tham chiếu cấu hình giữa namespace**, không phải mọi lớp bảo mật đường truyền.

### Ingress chuẩn và namespace

Với **Ingress Kubernetes chuẩn**, backend Service của Ingress thông thường được tham chiếu trong **cùng namespace** với Ingress theo schema. Không giả định có thể đặt backend cross-namespace trong Ingress core API giống cách Gateway API dùng ReferenceGrant; các controller extension/ExternalName workaround có semantics khác và cần security review riêng.

## 20. Hệ thống chung: DNS, monitoring, PKI và control-plane dependencies

Một Pod production có thể cần nhiều luồng **cross-namespace hợp lệ**:

| Initiator | Dependency | Luồng | Vì sao cần |
|---|---|---|---|
| App team-b | DNS service kube-system | UDP/TCP DNS | Phân giải Service/backend |
| App team-b | Identity provider/auth API | TCP/TLS theo API | Kiểm tra danh tính/quyền |
| App team-b | PKI/CA hoặc secret mechanism | Theo kiến trúc | Certificate rotation/trust |
| Metrics collector monitoring | App metrics | TCP/9090 (ví dụ) | Đọc telemetry |
| Logging/trace agent | Collector backend | TCP/TLS, protocol tùy agent | Vận hành và forensic |
| Ingress/Gateway | App team-b | TCP/8080 hoặc TLS | Route request từ caller |
| App team-b | Database data | TCP/5432 (ví dụ) | Truy cập dữ liệu có quyền |

**Không mở toàn bộ kube-system hoặc monitoring tới mọi Pod chỉ vì đây là “hệ thống nội bộ”**. Khi có service account đặc quyền, control-plane agents và các thành phần chịu trách nhiệm security, cần **quản trị danh tính, route và policy tách biệt**.

### Control plane thường không đi theo một đường Pod-to-Pod đơn giản

Kubernetes API server, kubelet, CNI agents, DNS daemon, admission webhook, cloud load balancer và metadata service có **đường networking đặc thù theo platform**. NetworkPolicy chuẩn **không bảo đảm bao phủ tất cả node/control-plane traffic**. Trước khi áp default deny, phải lập danh sách **phụ thuộc control plane thật**, đặc biệt khi cluster có webhook hoặc CNI/dataplane eBPF.

## 21. HostNetwork, node traffic và các đường ngoại lệ

**hostNetwork: true** khiến Pod dùng network namespace của node; loại lưu lượng này có thể không được thực thi bởi NetworkPolicy chuẩn giống Pod có Pod IP riêng, tùy CNI và phiên bản.

~~~text
Regular Pod team-b
  Pod IP: 10.244.2.20
  Policy may be enforced at Pod endpoint

hostNetwork Pod / Node process
  Node network namespace
  Node IP / host routing and services
  Different enforcement boundaries possible
~~~

### Những điểm phải kiểm tra

1. **Node-to-Pod traffic** có những semantics đặc biệt; không giả định policy chặn được mọi kết nối phát sinh từ node của Pod.
2. **HostNetwork Pod** có thể dùng node IP/source khác so với Pod thường.
3. Một số CNI có **host firewall/host policies** mở rộng; chúng không phải đặc tính mặc định của resource NetworkPolicy chuẩn.
4. **Kubelet health/readiness probes** và node daemons có đường đi đặc biệt, không chỉ theo namespace.
5. **NodePort, externalTrafficPolicy, source NAT** có thể thay source identity/IP ở điểm policy đánh giá.
6. Nếu dùng sidecar/service mesh, đường redirected traffic có thể tác động tới cách đo source/destination.

**Không mở hostNetwork hoặc privileged Pods chỉ để tránh lỗi NetworkPolicy.** Hãy xác minh network path, phối hợp với owner CNI/cluster và thực hiện change có rollback.

## 22. IPv4, IPv6 và dual-stack policy

Kubernetes có thể chạy IPv4, IPv6 hoặc dual-stack theo cấu hình cluster/CNI. Một Pod có thể có nhiều Pod IP theo stack; Service có thể có nhiều ClusterIPs. **NetworkPolicy phải được kiểm tra trên cả address family đang hỗ trợ**.

~~~text
team-a gateway
  IPv4: 10.244.1.10
  IPv6: 2001:db8:244:1::10  (documentation address)
        |
        v
team-b catalog
  IPv4: 10.244.2.20
  IPv6: 2001:db8:244:2::20  (documentation address)
~~~

**2001:db8::/32** là dải IPv6 dùng cho tài liệu, không phải địa chỉ triển khai thật. Những kiểm tra thiết yếu:

- Có DNS A/AAAA và client lựa chọn address family theo chính sách không?
- NetworkPolicy/pod/namespace selectors có được CNI hỗ trợ trên cả IPv4/IPv6 không?
- Nếu dùng **ipBlock**, CIDR v4 không bao phủ traffic v6.
- Cloud firewall/SG/LB và route v6 có tương thích chính sách ingress/egress không?
- ICMPv6/PMTUD cần thiết có bị các lớp firewall khác chặn không?
- Có đường bypass qua **public IPv6** khi chỉ kiểm tra IPv4 từ cluster hay không?

**Một test IPv4 PASS hoặc DENY không chứng minh IPv6 tương đương**. Khi bật dual-stack hoặc tạo Service địa chỉ mới, chạy lại ma trận connectivity.

## 23. Nhiều cluster và hybrid cloud: vượt ngoài phạm vi NetworkPolicy nội bộ

Namespace trong cluster A **không phải namespace trong cluster B**. NetworkPolicy trong cluster A chủ yếu áp dụng với Pod của cluster A theo CNI; nó **không tự áp chính sách identity hoặc trust** cho các workload ở cluster B.

~~~text
Cluster A                       Cluster B
Namespace team-a                Namespace team-b
    Pod A                            Pod B
       |                              ^
       |     VPN / peering / mesh      |
       +------------------------------+
         Cloud routing + firewall
         mTLS/service identity
         policies at both endpoints
~~~

### Thiết kế cross-cluster

1. Xác định **IP/CIDR có thể chồng lấn** giữa hai cluster không; có NAT/translation không?
2. VPN/peering/transit có route **hai chiều** và policy egress/ingress phù hợp không?
3. Service discovery xuyên cluster dùng **DNS, Multi-Cluster Services, mesh hoặc gateway** theo kiến trúc nào?
4. Service identity/trust domain có chấp nhận **chỉ những workload được phê duyệt** không?
5. Có một gateway trung gian biến traffic bên B thành nguồn IP của gateway, ảnh hưởng selector/ipBlock không?
6. Cloud SG/NACL/network firewall và TLS hai hop được kiểm chứng ra sao?

**Không đồng nhất “team-b” ở hai cluster chỉ vì trùng tên namespace**. Danh tính cần gắn vào cluster/trust domain, service account và cơ chế xác thực có đủ độ tin cậy.

## 24. Service mesh, mTLS và quyền theo workload

**NetworkPolicy** ngăn hoặc cho lưu lượng dựa trên thuộc tính mạng và selector. **Service mesh** có thể cung cấp danh tính workload và **mTLS** cho các kết nối service-to-service, cùng policy authorization theo service identity/route khi implementation hỗ trợ.

~~~text
    Pod gateway in team-a
     workload identity A
             |
    NetworkPolicy egress
             |
           mTLS
             |
    NetworkPolicy ingress
             |
    Pod catalog in team-b
     workload identity B
             |
    Application resource authorization
~~~

### Tách ba câu hỏi

| Tầng | Câu hỏi |
|---|---|
| **NetworkPolicy** | Nguồn Pod/namespace nào tới port của Pod đích? |
| **mTLS/service identity** | Peer nào được xác thực bằng chứng thư/identity tin cậy? |
| **Authorization** | Caller đó được gọi method và truy cập tenant/object nào? |

Một cổng mTLS hợp lệ **không tự cấp quyền trên mọi RPC**. Khi gateway đại diện user, identity của gateway khác identity của người dùng cuối; backend cần token/chữ ký hoặc ngữ cảnh đáng tin để phân quyền người dùng.

### Đường bypass và kiểm chứng

- Sidecar được inject nhưng Pod/port khác có đường **trực tiếp không đi qua proxy**?
- Có namespace được cấu hình **không bắt buộc mTLS** hoặc policy PERMISSIVE tạo đường cleartext không?
- Có workload/port bị loại trừ khỏi redirect theo cấu hình proxy?
- CA/trust domain/certificate rotation có hoạt động trên cả đường HA/DR không?
- Peer trong **team-a** có ServiceAccount khác nhưng dùng cùng pod labels được allow bởi NetworkPolicy không?

**Không xem mesh dashboard “mTLS enabled” là bằng chứng không còn đường bypass**; cần test identity và network ở đúng điểm.

## 25. RBAC, ServiceAccount, Pod Security và ranh giới tenant

Namespace isolation an toàn phải giới hạn **ai được thay đổi đối tượng có thể ảnh hưởng ranh giới**:

| Thành phần | Quyền cần xem | Tác động |
|---|---|---|
| **Namespace RBAC** | Ai có thể create/update Pod, Deployment, Service? | Có thể tạo endpoint mới hoặc gắn Pod labels |
| **NetworkPolicy RBAC** | Ai có thể thêm allow policy? | NetworkPolicy cộng dồn: thêm policy rộng có thể làm giảm cách ly |
| **Namespace labels** | Ai có thể thay security-zone/tenant labels? | Namespace có thể tự gia nhập trusted selector |
| **ServiceAccount** | Token, quyền gọi Kubernetes API và quyền cloud workload | Lộ credentials hoặc quyền quá rộng |
| **Pod Security Admission** | Admission theo standard/policy namespace | Hạn privileged, hostNetwork/hostPath/capabilities theo profile |
| **ResourceQuota/LimitRange** | Giới hạn tài nguyên workload trong namespace | Giảm sự cố noisy neighbor, không phải network firewall |
| **Secrets/ConfigMaps** | Scope và khả năng đọc/mount | Không đưa token/secret vào namespace dùng chung thiếu kiểm soát |
| **Controllers/CRDs** | Controller nào có quyền tạo Service/LB/policy? | Có thể thay exposure mà người dùng không sửa Pod trực tiếp |

### Labels là tín hiệu chính sách, không phải danh tính mật mã

Nếu NetworkPolicy cho phép mọi Pod ở namespace có **environment=trusted**, người có quyền sửa nhãn Namespace có thể thay đổi membership. Nếu policy chỉ cho **app=approved-gateway**, người được phép tạo Pod cùng nhãn có thể được mạng đối xử như gateway.

Để bảo vệ ranh giới:

- Dùng **RBAC/admission** kiểm soát việc sửa nhãn và chính sách.
- Dùng **mTLS identity/ServiceAccount attestation** phù hợp cho kết nối nhạy cảm.
- Tách namespace và trách nhiệm quản trị giữa tenant không tin cậy nhau.
- Giới hạn quyền tạo **privileged/hostNetwork** workload.
- Với yêu cầu cô lập mạnh giữa những tenant đối kháng, đánh giá **separate clusters/nodes/trust domains** thay vì chỉ namespace.

**RBAC kiểm soát Kubernetes API, không phải mọi HTTP request tới ứng dụng**. Cần cả NetworkPolicy và application authorization theo tài nguyên.

## 26. Mô hình hóa mối đe dọa cho traffic liên namespace

Một thiết kế namespace isolation bắt đầu từ **tài sản cần bảo vệ, caller hợp lệ và đường vượt trust boundary**. Giả sử:

~~~text
External user
     |
Ingress/Gateway (team-a)
     |
     | Allowed: HTTPS/TCP -> catalog:8080
     v
Catalog API (team-b)
     |
     | Allowed: TCP -> inventory-db:5432
     v
Inventory DB (data)

Untrusted workloads (sandbox)
     X no direct access to catalog admin/DB
~~~

### Các kịch bản rủi ro

| Threat | Đường có thể xảy ra | Biện pháp bổ trợ |
|---|---|---|
| **Lateral movement** | Pod sandbox gọi thẳng Pod catalog/admin | Default-deny + allow theo nguồn Pod/namespace |
| **Direct database access** | Pod team-a gọi DB thay vì qua catalog | DB ingress allow riêng cho catalog Pod |
| **Label impersonation** | Tenant tự gắn app=approved-gateway | RBAC/admission + mTLS service identity |
| **Policy widening** | Chủ namespace tạo NetworkPolicy allow rộng | Hạn quyền update policy; lint + approval |
| **Cross-tenant data access** | Caller được TCP/8080 nhưng gọi item tenant khác | Object-level authorization |
| **Ingress bypass** | Pod trong cluster gọi Pod IP, không đi qua WAF/gateway | NetworkPolicy + app auth, không tin chỉ có ingress route |
| **Control-plane bypass** | hostNetwork/privileged or node path khác Pod bình thường | Admission + host controls + CNI extension khi cần |
| **Egress exfiltration** | Pod bị xâm nhập gửi dữ liệu tới external API/DNS | Egress policy/proxy, logging, DLP/monitoring phù hợp |
| **Availability disruption** | Default deny chặn DNS/CA/telemetry | Dependency inventory, staged rollout, runbook |
| **Resource exhaustion** | Một tenant chiếm hết node/service | ResourceQuota, runtime limits, rate limits, autoscaling |

### Đặt câu hỏi trust boundary

1. Namespace nào đại diện **tổ chức/nhóm môi trường**, namespace nào thực sự có tenant không tin cậy?
2. Ai có quyền **create Pod, change labels, create NetworkPolicy, modify Gateway/Service**?
3. Những ứng dụng nào cần liên lạc hai chiều theo business flow?
4. Có **Pod IP direct path** hoặc đường qua NodePort/hostNetwork ngoài gateway không?
5. Service identity và network identity có thể **khác nhau sau NAT/mesh** không?
6. Một service bị xâm nhập có thể dùng **Kubernetes API token** làm gì theo RBAC?

**Không xây policy chỉ từ danh sách tên namespace.** Cần danh mục **initiator → destination → protocol/port → owner → authorization → tests** cho từng luồng.

## 27. Thiết kế hợp đồng traffic và rollout từng bước

### Ví dụ bảng luồng được phê duyệt

| Flow ID | Nguồn | Đích | Cổng | Kỳ vọng |
|---|---|---|---|---|
| **FLOW-01** | team-a/approved-gateway | team-b/catalog-api | TCP/8080 | ALLOW |
| **FLOW-02** | team-b/catalog-api | data/inventory-db | TCP/5432 | ALLOW |
| **FLOW-03** | team-a/approved-gateway | DNS được phê duyệt | UDP/TCP/53 | ALLOW |
| **FLOW-04** | monitoring/collector | team-b/catalog-api | TCP/9090 | ALLOW nếu có metrics port |
| **FLOW-05** | sandbox/unknown-pod | team-b/catalog-api | TCP/8080 | DENY |
| **FLOW-06** | team-a/approved-gateway | data/inventory-db | TCP/5432 | DENY |
| **FLOW-07** | team-b/catalog-api | External Internet tùy ý | TCP/443 | DENY trừ egress đã duyệt |
| **FLOW-08** | team-b/catalog-api | API auth/PKI/logging | Theo dịch vụ thật | ALLOW có giới hạn |

### Thứ tự triển khai an toàn

1. **Khảo sát:** inventory Services, EndpointSlices, Pod labels, NetworkPolicies, ingress/egress, DNS, IAM/mesh.
2. **Baseline:** xác định các đường hiện đang dùng, owner và mức quan trọng.
3. **Thiết kế:** tạo default-deny + allow policies và test cases; tính **additive union** từ mọi policy hiện có.
4. **Lint/review:** kiểm tra namespace/Pod selectors, YAML list indentation, ports, IP blocks, policyTypes.
5. **Staging:** xác nhận CNI enforce và đo positive/negative traffic, DNS, dual-stack.
6. **Canary:** áp tại một tập Pod/namespace đã được chọn, nếu kiến trúc và công cụ cho phép.
7. **Production:** rollout theo change window có metrics, owner và rollback.
8. **Hậu kiểm:** liên tục đối chiếu drift, nguồn ngoài quyền, policy bypass và quyền RBAC sửa policy.

**Lưu ý:** Một policy default-deny toàn namespace tác động **toàn bộ Pod được chọn ngay khi được thực thi**, không nhất thiết cho canary trực tiếp. Để giảm ảnh hưởng, có thể bắt đầu với **podSelector chọn workload cụ thể**, rồi mở rộng sau khi kiểm chứng dependency và bảo đảm không có policy allow rộng ngoài ý định.

## 28. Observability và lệnh kiểm tra chỉ đọc

Không có một lệnh Kubernetes API tiêu chuẩn duy nhất trả về **effective allow/deny matrix** sau khi hợp tất cả NetworkPolicy và các chính sách cloud/CNI mở rộng. Phải ghép **đối tượng cấu hình, topology, CNI telemetry và phép thử từ nguồn đại diện**.

### Xem namespace và nhãn dùng trong selector

~~~bash
# Chỉ dùng kubeconfig/context và quyền đọc được cấp.
kubectl get namespaces --show-labels
kubectl get pods -n team-a -L app -o wide
kubectl get pods -n team-b -L app -o wide
~~~

### Xem policy ở các namespace liên quan

~~~bash
kubectl get networkpolicy -n team-a
kubectl get networkpolicy -n team-b
kubectl describe networkpolicy -n team-b allow-team-a-gateway

# Đọc nội dung policy để thấy danh sách selectors/ports.
kubectl get networkpolicy -n team-b -o yaml
~~~

**Không coi câu lệnh get/describe trả thành công là bằng chứng CNI đã enforce**. Nó chỉ xác nhận resource trong Kubernetes API; phải kiểm tra cluster network implementation và kết quả lưu lượng thực.

### Xem Service và endpoint đích

~~~bash
kubectl get svc -n team-b
kubectl get endpointslices -n team-b
kubectl describe svc catalog-api -n team-b
~~~

Endpoints có thể đổi theo readiness/rollout; nên lấy **timestamp** và xem trạng thái backend phù hợp, không suy một lần inspect đại diện toàn phiên.

### Xem RBAC và quyền của tài khoản thử

~~~bash
# Lệnh truy vấn quyền hiện tại, không tạo chính sách.
kubectl auth can-i get networkpolicies -n team-b
kubectl auth can-i create networkpolicies -n team-b
kubectl auth can-i get secrets -n team-b
~~~

**can-i** đánh giá quyền theo Kubernetes authorization theo ngữ cảnh hiện tại (và các cơ chế policy liên quan), không nhất thiết tái hiện mọi điều kiện admission/identity của người dùng khác. Chỉ dùng identity có quyền và **không in nội dung Secret** ra tài liệu/log.

### Những nguồn log cần ghép

| Nguồn | Có thể cho biết | Giới hạn |
|---|---|---|
| **Kubernetes API audit** | Ai tạo/sửa Namespace, Pod, NetworkPolicy, Service | Không chứng minh packet bị chặn |
| **CNI flow/deny telemetry** | Nguồn/đích/port và hành động ở dataplane nếu hỗ trợ | Có thể phụ thuộc sampling/aggregation/path |
| **DNS/CoreDNS metrics** | Resolution errors/latency, query count | DNS resolve PASS không bằng TCP allow |
| **Cloud firewall/flow logs** | Lưu lượng ở LB/node/SG/VPC | Có thể không thấy toàn bộ east–west overlay |
| **Service mesh/gateway** | Peer identity, method, auth decisions | Có thể bỏ sót đường bypass proxy |
| **Application logs** | JWT/tenant/resource authorization, response status | Không thay packet-level evidence |
| **Tracing** | Chuỗi hop và độ trễ/cancellation | Sampling có thể bỏ sót lỗi hiếm |

**Không thấy drop log không chứng minh không có DENY.** Có thể do exporter chưa bật, log chưa được thu, probe sai đường hoặc CNI không hỗ trợ log theo policy.

## 29. Runbook: request qua namespace khác bị timeout hoặc bị từ chối

### Bước 1 — Thu bối cảnh

1. Nguồn **namespace/Pod/labels/ServiceAccount/node/Pod IP** và đích **namespace/Service/backend Pod/port**.
2. DNS name thực tế, kết quả phân giải, ClusterIP, Pod IP, address family và thời gian.
3. Trạng thái **CNI, NetworkPolicy, mesh, cloud route/SG, Ingress/Gateway** trên đường.
4. Lỗi là **DNS timeout, TCP timeout/refused, TLS failure, HTTP 401/403/5xx hay gRPC status**?
5. Change gần nhất về **labels, policies, endpoint selectors, Service, deployment, CNI hoặc namespace**?

### Bước 2 — Phân nhánh nguyên nhân

~~~text
Client team-a cannot call catalog team-b
                     |
             DNS resolves?
              /           \
             No            Yes
             |              |
     DNS egress path     Service has ready endpoints?
                              /        \
                             No         Yes
                             |           |
                      Readiness/labels   TCP reaches Pod?
                                          /      \
                                         No      Yes
                                         |        |
                                  Source egress   TLS/mTLS and
                                  + target ingress app authorization
                                  + route/CNI     + service behavior
~~~

### Bước 3 — Tính effective policy

- Liệt kê **mọi policy chọn source Pod** cho egress.
- Liệt kê **mọi policy chọn destination Pod** cho ingress.
- Kiểm tra **podSelector/namespaceSelector AND vs OR**, các nhãn thật, protocol/port.
- Tìm **allow-all/additive rule** có thể đang cấp rộng ngoài dự định.
- Nếu dùng ipBlock hoặc Service, xem **NAT/source identity** tại điểm CNI thực thi.
- Kiểm tra **CNI plugin/version** và những policy mở rộng, hostNetwork/node traffic.

### Bước 4 — Khắc phục có phê duyệt

1. Xác định **rule tối thiểu thực sự thiếu** và owner của nguồn/đích.
2. Nếu thiếu DNS, chỉ allow resolver được phép theo topology đã xác minh.
3. Nếu selector sai, sửa **đúng namespace/Pod membership**, không thêm namespaceSelector rỗng để cho chạy bằng mọi giá.
4. Nếu policy rộng, thu hẹp/xóa **chính policy cấp quyền vượt quá**; thêm default-deny khác không thu hẹp additive allow.
5. Nếu CNI không enforce, không tuyên bố policy có hiệu lực; triển khai giải pháp network enforcement phù hợp.
6. Có change ticket, tác động dự kiến, rollback owner và phép thử ALLOW/DENY trước/sau.

### Bước 5 — Hậu kiểm

Xác nhận **gateway hợp lệ được gọi catalog**, **catalog gọi đúng database**, **sandbox không vào catalog**, **gateway không gọi thẳng DB**, DNS hoạt động, authentication/authorization vẫn đúng và observability ghi nhận bằng chứng. Nếu chỉ nhìn một GET trả HTTP 200 mà không thử nguồn không được phép, kết luận bảo mật vẫn chưa đủ.

## 30. Case study 1: namespace riêng nhưng database vẫn reachable

**Bối cảnh giả định:** Một cluster có **sandbox**, **team-b** và **data**. Admin tách mỗi workload thành namespace và cấu hình RBAC chỉ cho developer xem tài nguyên trong sandbox. Tuy nhiên, chưa có NetworkPolicy nào, và database có Service ClusterIP lắng nghe TCP/5432.

### Quan sát

~~~text
Namespace sandbox:
  Pod demo-client
  Kubernetes API RBAC: không đọc được Secrets ở namespace data

Namespace data:
  Service inventory-db.data.svc.cluster.local:5432
  Pod inventory-db
  NetworkPolicy: chưa có policy cô lập DB ingress

Network result in hypothetical cluster:
  Pod sandbox -> inventory-db:5432
  TCP connection succeeds
~~~

**Rủi ro:** Network reachability tồn tại dù RBAC ngăn đọc API objects. Nếu database auth yếu hoặc credentials bị lộ, một Pod ít tin cậy có thể trở thành điểm xuất phát truy cập dữ liệu.

### Sửa đúng ranh giới

1. Thiết kế **default-deny ingress** ở namespace data/DB Pods.
2. Chỉ allow traffic từ **catalog Pod thuộc team-b** tới TCP/5432 theo selector AND.
3. Nếu catalog có egress isolation, allow chiều source tương ứng.
4. Kiểm tra **database authentication/TLS**, credentials và quyền schema.
5. Tạo test từ sandbox tới DB **DENY**, từ catalog tới DB **ALLOW**.
6. Bảo vệ quyền tạo/sửa NetworkPolicy và các labels dùng làm trust signals.

**Bài học:** RBAC namespace không ngăn một TCP connection trực tiếp; NetworkPolicy và DB identity phải cùng hoạt động.

## 31. Case study 2: sai indentation khiến mọi Pod team-a được gọi catalog

**Bối cảnh giả định:** Chỉ **approved-gateway** thuộc team-a được gọi catalog trong team-b. Policy reviewer không phát hiện một dấu gạch đầu dòng bị đặt sai:

~~~yaml
from:
  - namespaceSelector:
      matchLabels:
        kubernetes.io/metadata.name: team-a
  - podSelector:
      matchLabels:
        app: approved-gateway
~~~

### Hệ quả

- Phần tử **namespaceSelector** cho phép **mọi Pod team-a**.
- Phần tử **podSelector** cho phép **Pod cùng nhãn trong team-b**.
- Hai phần tử được **OR**, không phải AND.
- Một Pod không phải gateway nhưng thuộc team-a có thể đi qua L3/L4 network allow nếu các lớp khác cũng cho phép.

### Cách sửa

~~~yaml
from:
  - namespaceSelector:
      matchLabels:
        kubernetes.io/metadata.name: team-a
    podSelector:
      matchLabels:
        app: approved-gateway
~~~

Hai selector nằm **cùng một phần tử**, tạo AND. Sau khi sửa, kiểm tra các policies khác **có allow team-a rộng** không; nếu có, kết quả vẫn có thể rộng vì additive semantics.

### Negative tests quan trọng

1. **approved-gateway team-a** → catalog TCP/8080: ALLOW.
2. **unapproved-worker team-a** → catalog TCP/8080: DENY.
3. **approved-gateway label trong team-b** → catalog TCP/8080: DENY trừ luồng same-namespace khác được duyệt.
4. **client trong sandbox** → catalog TCP/8080: DENY.

**Bài học:** YAML hợp lệ về cú pháp vẫn có thể là **lỗ hổng phân đoạn**. Cần reviewer hiểu cấu trúc danh sách và ma trận nguồn được phép.

## 32. Case study 3: bật default-deny egress làm DNS lỗi

**Bối cảnh giả định:** team-a đã có egress policy chỉ cho **approved-gateway → catalog**. Sau khi bật default-deny egress cho toàn namespace, gateway không resolve được tên Service thuộc team-b và ghi lỗi **name resolution timeout**.

### Bằng chứng giả lập

~~~text
Client: team-a/approved-gateway
Destination DNS name: catalog-api.team-b.svc.cluster.local
Destination TCP: catalog-api:8080
Egress policy:
  allow catalog Pod TCP/8080
  no verified allowance for actual DNS path

Observed:
  DNS resolution fails
  Direct TCP outcome: not yet tested
~~~

### Điều tra đúng

1. Xem Pod DNS configuration, resolver address và **cluster DNS mode**.
2. Kiểm tra CoreDNS/NodeLocal DNSCache, labels, port và CNI path.
3. Đối chiếu source egress policies và chính sách provider nếu có.
4. Tạo allow DNS **hẹp theo resolver thực**, cả UDP/TCP theo nhu cầu.
5. Thử name resolution rồi thử RPC/HTTP tới catalog.
6. Vẫn kiểm tra **sandbox không được gọi catalog**, tránh mở egress/ingress rộng để khắc phục DNS.

**Bài học:** NetworkPolicy egress có thể làm lỗi **service discovery** trước cả khi RPC bắt đầu; phải phân biệt DNS failure với TCP ingress deny, TLS failure và application authorization.

## 33. Bài thực hành an toàn: đánh giá cross-namespace isolation

Bài lab này sử dụng **ba namespace giả định team-a, team-b và sandbox**, có thể thực hiện **trên giấy** hoặc bằng cluster **lab/staging được phê duyệt**. Không tự apply default-deny lên production hoặc xóa NetworkPolicy đang hoạt động chỉ để tạo bằng chứng. Nếu thiếu quyền chạy test Pod, dùng **manifests và dữ liệu giả lập** để phân tích.

### 33.1. Bối cảnh

~~~text
Namespace team-a:
  Pod app=approved-gateway
  Pod app=unapproved-worker

Namespace team-b:
  Service catalog-api :8080
  Pod app=catalog-api

Namespace sandbox:
  Pod app=sandbox-client

Desired:
  team-a/approved-gateway -> team-b/catalog-api TCP/8080: ALLOW
  team-a/unapproved-worker -> team-b/catalog-api TCP/8080: DENY
  sandbox/sandbox-client -> team-b/catalog-api TCP/8080: DENY
  team-a/approved-gateway -> approved DNS: ALLOW
~~~

**Điều kiện của lab:** namespace/Pod labels thực sự phù hợp, CNI thực thi NetworkPolicy, Service có backend khỏe và các network controls khác không chặn luồng hợp lệ. Đây là điều kiện phải **xác minh**, không giả định.

### 33.2. Đọc các resource hiện có trước khi thử

~~~bash
# Chỉ dùng trên cluster lab được phê duyệt.
kubectl config current-context
kubectl get namespaces --show-labels
kubectl get pods -n team-a --show-labels
kubectl get pods -n team-b --show-labels
kubectl get networkpolicy -n team-a
kubectl get networkpolicy -n team-b
kubectl get svc -n team-b
kubectl get endpointslices -n team-b
~~~

Mỗi lệnh **get** chỉ đọc Kubernetes API. Tuy nhiên, danh sách tên Pod, endpoint, Service hoặc internal addresses có thể là **thông tin hạ tầng nội bộ**; không đưa dữ liệu thực vào tài liệu công khai.

### 33.3. Tự phân tích selectors trên giấy

Trong team-b, đánh giá hai policy:

~~~yaml
# Policy A: chỉ gateway trong team-a
ingress:
  - from:
      - namespaceSelector:
          matchLabels:
            kubernetes.io/metadata.name: team-a
        podSelector:
          matchLabels:
            app: approved-gateway
    ports:
      - port: 8080
        protocol: TCP
~~~

~~~yaml
# Policy B: có cùng một phần tử từ namespace sandbox
# và cho phép mọi Pod trong sandbox đến TCP/9090
ingress:
  - from:
      - namespaceSelector:
          matchLabels:
            kubernetes.io/metadata.name: sandbox
    ports:
      - port: 9090
        protocol: TCP
~~~

**Câu hỏi:** Nếu Pod catalog có hai listener TCP/8080 và TCP/9090, nguồn nào được gọi mỗi port khi cả Policy A/B đều chọn Pod? Kết luận phải dựa vào **hợp của allow rules**. Nếu metrics TCP/9090 không được phép cho sandbox, Policy B tạo **exposure ngoài ý định** và phải được thu hẹp/xóa; thêm một default-deny thứ ba **không vô hiệu hóa nó**.

### 33.4. Kiểm thử từ Pod lab có quyền

Nếu **đã có sẵn test Pod và được quyền exec**, có thể dùng các phép thử đọc dữ liệu, không tạo tải:

~~~bash
# Ví dụ: test Pod được duyệt phải tồn tại và có nslookup.
kubectl exec -n team-a approved-gateway-test -- \
  nslookup catalog-api.team-b.svc.cluster.local

# Ví dụ: test Pod có curl, endpoint /health được phép.
kubectl exec -n team-a approved-gateway-test -- \
  curl --connect-timeout 2 --max-time 5 \
  --silent --show-error --output /dev/null \
  --write-out 'http=%{http_code} total=%{time_total}\n' \
  http://catalog-api.team-b.svc.cluster.local:8080/health
~~~

**Các lệnh không phải ví dụ chạy được trên mọi cluster**: tên Pod, URL, công cụ trong image, protocol, port và quyền exec đều phụ thuộc môi trường. Dùng **HTTPS và xác minh certificate** nếu đây là đường bảo vệ thực; HTTP cleartext chỉ phù hợp lab được cô lập/được phê duyệt.

Để kiểm thử từ **unapproved-worker** hoặc **sandbox**, chỉ dùng Pod test có phép và **một số lượng request nhỏ**. Một request bị timeout có thể do **DNS, route, Service endpoint, TCP policy hoặc ứng dụng**; cần ghép với CNI logs/effective rules mới kết luận chính xác **NetworkPolicy DENY**.

### 33.5. Kiểm thử application authorization riêng

Giả sử caller được phép kết nối TCP/8080 nhưng **không có quyền với catalog tenant B**. Trạng thái mong đợi có thể là **HTTP 403 hoặc gRPC PERMISSION_DENIED** theo hợp đồng API, **không phải network timeout**. Đừng coi request trả 403 là “NetworkPolicy FAIL”: mạng đã đến application; tầng ứng dụng đang từ chối.

### 33.6. Phiếu kiểm thử

~~~text
Test ID:               KNP-XNS-001
Cluster/context:       [approved cluster ID]
Environment:           [isolated lab or staging]
Timestamp/timezone:    [time]
Source namespace:      [name]
Source Pod + labels:   [resource and verified labels]
Source ServiceAccount: [identity, no token]
Destination namespace: [name]
Target Service/Pod:    [name, ready endpoint]
Destination port:      [TCP/UDP port]
DNS resolution:        [PASS/FAIL/NOT_TESTED]
Applicable egress:     [selected policies and matching rules]
Applicable ingress:    [selected policies and matching rules]
CNI enforcement:       [confirmed/unknown]
Network path:          [PodIP/ClusterIP/LB/Gateway/host path]
Expected network:      [ALLOW/DENY]
Observed transport:    [connect/timeout/refused/inconclusive]
TLS/application:       [verified/denied/not tested]
Effective verdict:     [PASS/FAIL/INCONCLUSIVE]
Evidence:              [flow log, config, trace without secrets]
Owner + next action:   [team/ticket]
~~~

**Chỉ kết luận isolation PASS khi đường trái quyền thực sự bị ngăn từ điểm kiểm thử phù hợp và đường hợp lệ vẫn hoạt động.** Một test từ sai namespace, sai Pod label hoặc sai IP family không đủ để tuyên bố policy đã được thực thi.

## 34. Ma trận nghiệm thu network isolation và traffic liên namespace

| Test ID | Tình huống | Kỳ vọng |
|---|---|---|
| **XNS-01** | Pod team-a gọi Service team-b khi chưa có policy cô lập | Hiểu đúng mặc định không bị NetworkPolicy chặn, kiểm tra lớp khác |
| **XNS-02** | Cài default-deny ingress cho Pod catalog trong lab | Luồng ingress không được allow bị chặn |
| **XNS-03** | approved-gateway team-a gọi catalog TCP/8080 | ALLOW theo ingress/egress và business permission |
| **XNS-04** | unapproved-worker cùng team-a gọi catalog TCP/8080 | DENY tại policy nếu không có allow khác |
| **XNS-05** | Pod sandbox gọi catalog TCP/8080 | DENY theo thiết kế |
| **XNS-06** | Pod cùng label gateway nhưng ở team-b | Không được chọn nhầm bởi peer AND team-a |
| **XNS-07** | YAML from gồm hai selector ở hai phần tử | Phát hiện OR rộng hơn intent |
| **XNS-08** | Namespace label bị sửa ngoài quyền | RBAC/admission ngăn leo quyền network membership |
| **XNS-09** | Pod label app=approved-gateway tự gắn bởi tenant | Detect nguy cơ label impersonation |
| **XNS-10** | Hai policies cùng chọn catalog Pod | Effective allow là union, không có deny override |
| **XNS-11** | Default-deny cùng tồn tại với policy allow-all | Không đánh dấu cô lập thành công giả |
| **XNS-12** | team-a gateway bị egress isolated | Egress tới catalog được phép, các destination ngoài quyền bị chặn |
| **XNS-13** | team-b catalog ingress isolated | Chỉ nguồn đã duyệt được phép trên port dịch vụ |
| **XNS-14** | DNS egress UDP/53 hợp lệ | DNS resolution hoạt động qua resolver thật |
| **XNS-15** | DNS egress TCP/53 cần thiết | Không chặn nhầm DNS fallback/use case hợp lệ |
| **XNS-16** | NodeLocal DNSCache hoặc managed resolver | Policy match đúng topology, không giả định CoreDNS Pod |
| **XNS-17** | Service ClusterIP có selector đúng nhưng EndpointSlice rỗng | Phân loại Service readiness, không báo nhầm NetworkPolicy |
| **XNS-18** | Service targetPort không khớp Pod listener | Triage đúng lỗi port/listener |
| **XNS-19** | Pod trực tiếp gọi Pod IP khác namespace | Policy vẫn bảo vệ backend theo semantics CNI |
| **XNS-20** | ipBlock tới external CIDR được duyệt | Egress match đúng CIDR, không lấy hostname làm IP identity |
| **XNS-21** | Service LB/NodePort chuyển đổi địa chỉ | Nắm source identity/NAT path để đánh giá policy |
| **XNS-22** | Ingress controller dùng hostNetwork | Kiểm tra node/host enforcement, không áp giả định Pod source |
| **XNS-23** | Public Ingress route tới catalog | Gateway auth và backend NetworkPolicy cùng đúng |
| **XNS-24** | Gateway API HTTPRoute tham chiếu Service khác namespace | ReferenceGrant đúng và network authorization tách biệt |
| **XNS-25** | CNI không hỗ trợ NetworkPolicy | Không kết luận PASS chỉ vì resource tồn tại |
| **XNS-26** | CNI policy mở rộng cùng áp cho workload | Xem hiệu lực tổng thể, không chỉ NetworkPolicy chuẩn |
| **XNS-27** | hostNetwork Pod thử truy cập backend | Xác minh node/host path và policies thực thi phù hợp |
| **XNS-28** | Workload cùng namespace không được phép đọc metrics | Restrict Pod selector, không mở cả namespace |
| **XNS-29** | Database namespace chỉ nhận catalog backend | team-b catalog ALLOW, team-a gateway trực tiếp DB DENY |
| **XNS-30** | TLS/mTLS service identity không được tin | Connection bị từ chối dù network ALLOW |
| **XNS-31** | User thuộc tenant A cố đọc object tenant B | Application authorization từ chối |
| **XNS-32** | IPv4 và IPv6 dual-stack | Chính sách và tests bao phủ cả hai address families |
| **XNS-33** | Đường cross-cluster qua VPN/gateway | Route, firewall, mTLS và policies ở từng đầu được kiểm chứng |
| **XNS-34** | Cập nhật NetworkPolicy qua GitOps | Diff, review, owner, rollout và rollback được ghi |
| **XNS-35** | Thêm temporary allow policy rồi hết hạn | Policy bị thu hồi có kiểm chứng, không để cấp quyền mãi |
| **XNS-36** | Sau thay đổi policy, DNS/API/tracing có lỗi | Alert đúng lớp và có đường hồi phục |
| **XNS-37** | Có log traffic REJECT từ CNI | Điều tra source/destination/port và policy thật |
| **XNS-38** | Không có CNI log hoặc trace ở đường thử | Đánh dấu INCONCLUSIVE thay vì khẳng định đã chặn |

### Tiêu chí kết luận

- **PASS:** có bằng chứng rõ đúng source/namespace/labels, policy/CNI enforcement và kết quả network/application theo kỳ vọng.
- **FAIL:** luồng hợp lệ bị chặn ngoài ý định hoặc luồng ngoài quyền được phép qua ranh giới được kiểm thử.
- **INCONCLUSIVE:** thiếu quyền quan sát, sai client path, không xác nhận CNI hoặc không phân biệt được DNS/network/auth.
- **NOT_APPLICABLE:** một đặc tính thực sự không được triển khai, chẳng hạn dual-stack hoặc Gateway API; cần ghi lý do.

**Không dùng một kết nối thất bại làm chứng cứ duy nhất rằng cross-namespace isolation đang an toàn.** Nó có thể thất bại vì ứng dụng không chạy hoặc sai hostname, trong khi đường khác tới backend vẫn mở.

## 35. Những sai lầm phổ biến

| Sai lầm | Hậu quả | Cách làm phù hợp |
|---|---|---|
| “Đặt workload vào namespace khác là đã network isolated” | Pod vẫn gọi nhau qua PodIP/Service | NetworkPolicy/CNI và identity controls |
| “RBAC cấm xem Service nên không thể kết nối tới Service” | RBAC API không phải packet firewall | Tách Kubernetes API và data plane |
| “ClusterIP chỉ namespace cùng tên truy cập được” | Các namespace khác có thể gọi nếu path cho phép | NetworkPolicy/mesh auth |
| “DNS không resolve được nghĩa network đã cách ly” | Pod IP trực tiếp có thể vẫn reachable | Positive/negative connectivity test |
| “Có YAML NetworkPolicy là đã được bảo vệ” | CNI có thể không enforce | Kiểm tra CNI thực tế và dataplane |
| “default-deny chặn hết mọi thứ kể cả allow cũ” | Additive union có thể giữ allow rộng | Tính mọi policy chọn cùng Pod |
| “Policy có thứ tự DENY rồi ALLOW như NACL” | NetworkPolicy core không có explicit deny priority | Dùng additive allow semantics |
| “podSelector: {} nghĩa không chọn Pod” | Chọn tất cả Pod trong namespace policy | Review selector rỗng |
| “namespaceSelector: {} chỉ namespace hiện tại” | Có thể chọn tất cả namespaces | Tránh selector rỗng ngoài intent |
| “Hai phần tử from là AND” | Chúng tạo OR và mở rộng phạm vi | Ghép selectors vào một phần tử khi cần AND |
| “Một phần tử chứa hai selectors là OR” | Thực tế cần cả hai điều kiện cùng đúng | Dùng YAML linter/test matrix |
| “Chỉ cần ingress policy tại destination” | Source có egress isolation vẫn có thể chặn | Kiểm tra policy ở cả hai đầu |
| “Bật egress deny không ảnh hưởng DNS” | Service resolution có thể thất bại | Kiểm kê resolver và DNS policy |
| “kube-system DNS luôn có nhãn k8s-app=kube-dns” | NodeLocal/managed DNS có đường khác | Xem topology thực |
| “Pod labels là định danh không thể giả mạo” | Tenant có thể sửa labels nếu được quyền | RBAC/admission + mTLS identity |
| “Chỉ namespaceSelector đã bảo vệ một app duy nhất” | Nó có thể allow mọi Pod trong namespace nguồn | Thêm podSelector trong cùng phần tử |
| “Service có NetworkPolicy riêng theo Service name” | NetworkPolicy chuẩn chọn Pod | Bảo vệ backend Pods và caller |
| “ipBlock là cách tốt nhất để chọn Pod CIDR” | Pod IP/translation thay đổi, CNI semantics khác | Dùng Pod/namespace selectors khi phù hợp |
| “Ingress route không public thì Pod không reachable trực tiếp” | Có thể còn Service/Pod IP/NodePort path | Kiểm tra mọi đường |
| “ReferenceGrant là firewall” | Chỉ cấp quyền tham chiếu cấu hình | NetworkPolicy và app authorization riêng |
| “NetworkPolicy chuẩn lọc HTTP method và JWT” | Chủ yếu L3/L4 | Gateway/mesh/app policy |
| “hostNetwork chịu đúng policy Pod bình thường” | Host path/CNI có ngoại lệ | Admission và host firewall/host policies |
| “Một test IPv4 đủ cho dual-stack” | IPv6 có đường đi và CIDR khác | Test cả IPv4/IPv6 |
| “Mesh mTLS enabled nghĩa không còn bypass” | Có thể có excluded ports/direct traffic | Kiểm chứng đường và identity |
| “Một Pod gọi được TCP/8080 thì chắc chắn đã có quyền đọc dữ liệu” | App authz có thể từ chối hoặc bị lỗi | Kiểm tra quyền object/tenant |
| “Tất cả các namespace trong nhiều cluster tương đương nhau” | Trust domain/cluster identity khác | Xác thực và chính sách cross-cluster |
| “Chỉ cần thêm policy mới để thu hẹp allow cũ” | Additive allow không bị trừ bởi policy khác | Sửa/xóa policy cho quyền vượt |
| “Chặn toàn bộ traffic rồi mở từng chút trên production là an toàn” | Có thể gây outage DNS/PKI/webhook/logging | Stage, inventory, rollback và canary |
| “Không thấy CNI drop log nghĩa không có traffic trái phép” | Log coverage và sampling có giới hạn | Kiểm tra nguồn đo và authorized probes |

## 36. Câu hỏi tự kiểm tra

1. Kubernetes Namespace tạo ra những loại isolation nào và **không tự tạo** isolation mạng nào?
2. Vì sao Pod ở team-a có thể gọi Service team-b dù user không có RBAC xem Service ở team-b?
3. DNS của một Service khác namespace thường có cấu trúc tên gì? Cluster domain có luôn là cluster.local không?
4. Vì sao chặn DNS không thay thế chặn Pod-to-Pod traffic?
5. NetworkPolicy chọn Pod ở namespace nào thông qua **spec.podSelector**?
6. **podSelector: {}** ở cấp spec khác thế nào với podSelector rỗng trong một ingress peer?
7. Một phần tử chứa cả **namespaceSelector và podSelector** tạo phép toán logic nào?
8. Hai phần tử from có hai selector tách nhau tạo phép toán logic nào và rủi ro gì?
9. NetworkPolicy chuẩn có explicit DENY với thứ tự rule như AWS NACL không?
10. Nếu hai policy cùng chọn catalog Pod, effective allowed ingress được tính như thế nào?
11. Tại sao thêm một policy default-deny không tự chặn lại allow-all đang tồn tại?
12. Nguồn Pod bị cô lập egress và đích bị cô lập ingress thì cần thiết kế điều gì ở cả hai phía?
13. Vì sao thường không cần thêm rule cho từng gói response như một stateless Network ACL?
14. Khi bật default-deny egress, DNS có thể thất bại vì những nguyên nhân nào?
15. Vì sao ví dụ allow CoreDNS theo label không thể sao chép nguyên cho mọi cluster?
16. Khi nào nên dùng **ipBlock**, và vì sao không nên giả định ipBlock luôn phù hợp để lọc Pod IP?
17. Một Service ClusterIP với EndpointSlice sẵn sàng có chứng minh TCP được NetworkPolicy cho phép không?
18. Vì sao Pod IP direct access cần được kiểm thử ngoài đường gọi Service?
19. Quyền **HTTPRoute tham chiếu Service namespace khác** trong Gateway API liên quan ReferenceGrant thế nào?
20. ReferenceGrant và NetworkPolicy giải quyết những quyền khác nhau ra sao?
21. Vì sao source IP nhìn thấy qua Ingress/LoadBalancer/NodePort có thể khác nguồn Pod mong muốn?
22. HostNetwork Pod và node-originated traffic có thể vượt qua giả định nào của NetworkPolicy chuẩn?
23. Vì sao IPv4 DENY chưa chứng minh IPv6 DENY trong một cluster dual-stack?
24. NetworkPolicy của cluster A có tự bảo vệ namespace cùng tên ở cluster B không?
25. Service mesh mTLS và object-level authorization bổ sung NetworkPolicy theo những lớp nào?
26. Ai có quyền gắn **environment=trusted** vào Namespace, và việc đó ảnh hưởng network isolation ra sao?
27. Vì sao quyền tạo NetworkPolicy có thể mang tác động bảo mật dù user không có quyền trực tiếp sửa firewall cloud?
28. Một developer có thể tự gắn **app=approved-gateway** vào Pod; cần biện pháp nào để giảm rủi ro?
29. Tại sao ResourceQuota và Pod Security Admission không thay network segmentation?
30. Khi catalog không kết nối DB được, làm sao tách lỗi DNS, egress, ingress, TLS và application?
31. Những lệnh chỉ đọc nào giúp kiểm tra Namespace labels, NetworkPolicy và EndpointSlices?
32. Cần những bằng chứng nào để kết luận **CNI thực thi** một policy chứ không chỉ Kubernetes API đã lưu policy?
33. Trong case study 2, tại sao lỗi indentation làm mở rộng tập nguồn được phép?
34. Hãy viết ma trận ALLOW/DENY cho gateway team-a, catalog team-b, DB data và workload sandbox.
35. Sau khi sửa default-deny, tại sao phải kiểm tra **cả giao dịch thành công và quyền truy cập bị từ chối**?

## 37. Ghi nhớ trọng tâm

**Namespace là ranh giới đặt tên và quản trị, không phải network firewall tự động.** Pod ở các namespace khác nhau thường có thể tìm và gọi nhau qua **Service DNS, ClusterIP hoặc Pod IP** nếu đường mạng cho phép. Để tạo **namespace isolation**, phải thiết kế **NetworkPolicy thực sự được CNI enforce**, kết hợp RBAC/admission để bảo vệ nhãn và cấu hình, cùng TLS/mTLS và authorization của ứng dụng.

NetworkPolicy chuẩn chủ yếu điều khiển **ingress/egress L3/L4 trên Pod được chọn**, sử dụng **podSelector, namespaceSelector, ipBlock, protocol/port**. Quy tắc **additive union** có nghĩa allow từ nhiều policy được cộng lại; **default-deny không ghi đè một allow rộng khác**. Trong một phần tử peer, **namespaceSelector AND podSelector**; tách thành hai phần tử sẽ thành **OR**. Khi cô lập egress, hãy kiểm kê **DNS, identity provider, CA/PKI, logging, DB và những luồng phụ thuộc thật**, không mở mọi namespace để chữa lỗi.

Điểm rủi ro cao nằm ở **NAT/Service routing, Ingress/Gateway, ReferenceGrant, hostNetwork/node paths, IPv4/IPv6, multi-cluster và label ownership**. Những nơi này có semantics khác NetworkPolicy chuẩn hoặc tạo đường bypass khi hiểu sai. Vận hành đáng tin cần **port/flow inventory, policy review, staged rollout, CNI telemetry, lệnh kiểm tra chỉ đọc, positive/negative tests, incident runbook và rollback**. Chỉ tuyên bố isolation thành công khi có bằng chứng rằng **luồng đúng được phép, luồng ngoài quyền bị chặn, danh tính được xác thực và quyền dữ liệu vẫn được kiểm tra**.
