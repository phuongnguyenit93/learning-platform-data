# Theo dõi thay đổi NetworkPolicy trong Kubernetes: Từ cấu hình mong muốn đến bằng chứng thực thi

## 1. Vì sao cần theo dõi thay đổi network policy?

**Theo dõi thay đổi network policy** là quá trình ghi nhận, đánh giá và xác minh những thay đổi có thể làm **mở rộng, thu hẹp hoặc thay đổi đường giao tiếp mạng** của workload trong Kubernetes. Đối tượng theo dõi không chỉ là thao tác tạo/sửa/xóa tài nguyên **NetworkPolicy**: thay đổi **nhãn Pod/Namespace, Service/EndpointSlice, CNI, routing, hostNetwork, cluster network configuration** và các chính sách mở rộng của plugin cũng có thể làm thay đổi hiệu quả thực thi dù bản YAML NetworkPolicy không đổi.

Trong chương **Bảo mật mạng Kubernetes** thuộc học phần **SECURITY_NETWORK_SECURITY**, khả năng phát hiện thay đổi chính sách là mắt xích giữa **phân đoạn, firewall, giám sát xâm nhập, bảo vệ DNS, mTLS, kiểm soát truy cập dịch vụ và quản trị cloud**. Một default-deny đúng hôm qua có thể không còn bảo vệ như mong muốn hôm nay nếu một selector bị mở rộng, một policy allow mới xuất hiện hoặc workload có thêm đường đi không qua CNI enforcement.

**Tình huống mở đầu:** namespace **payments** có policy chỉ cho frontend đã được phê duyệt gọi API TCP/8443. Một lần sửa manifest làm namespaceSelector từ điều kiện theo namespace cụ thể thành selector rỗng, hoặc làm hai điều kiện namespaceSelector/podSelector từ **AND** thành **OR**. Kết quả có thể là nhiều workload hơn được phép truy cập payments, dù manifest vẫn hợp lệ và hệ thống không báo lỗi cú pháp.

Ngược lại, một sửa đổi làm **DNS egress bị chặn** có thể khiến cả một ứng dụng thất bại. Hệ thống giám sát phải phát hiện cả **mở quyền ngoài ý định** lẫn **giảm khả dụng do chặn nhầm**, phân biệt thay đổi được duyệt với drift, và đưa ra bằng chứng dữ liệu mạng thực.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Nêu rõ semantics của Kubernetes NetworkPolicy chuẩn và các trường hợp **không được bảo vệ** bởi policy mặc định.
2. Theo dõi create/update/patch/delete qua **Kubernetes API audit**, object watches và GitOps/IaC history mà không nhầm **khai báo** với **thực thi**.
3. Đánh giá ảnh hưởng của thay đổi **Pod/Namespace labels, selectors, ports, ipBlock, policyTypes, ingress/egress, Service/NAT và CNI mode**.
4. Thiết kế pipeline phát hiện drift giữa desired state, API state và **effective data-plane enforcement**.
5. Xây rule cảnh báo cho **default-deny deletion, broad allow, cross-namespace reachability, rule scope changes, unexpected egress** và các lỗi vận hành.
6. Tương quan thời gian thay đổi với **flow verdicts, DNS, service availability, audit identity** để xác minh.
7. Thực hành kiểm chứng **read-only**, review YAML, kiểm thử allow/deny trong lab, rollout/rollback và quy trình ứng phó.

## 2. NetworkPolicy chuẩn thật sự kiểm soát những gì?

### 2.1. Phạm vi của NetworkPolicy

Tài nguyên **networking.k8s.io/v1 NetworkPolicy** chọn một tập Pod trong **một namespace** thông qua **spec.podSelector**, và mô tả traffic ingress/egress được phép theo **peers, protocol, port** với các trường có trong API. Việc enforcement yêu cầu một **CNI/network plugin thực sự hỗ trợ NetworkPolicy**. API server có thể nhận manifest hợp lệ dù plugin không áp chính sách trên data plane.

Các khái niệm cần phân biệt:

| Thành phần | Ý nghĩa | Ảnh hưởng khi đổi |
| --- | --- | --- |
| **metadata.namespace** | Namespace chứa NetworkPolicy | Quyết định nhóm Pod mà spec.podSelector có thể chọn |
| **spec.podSelector** | Chọn Pod đích của chính policy trong namespace đó | Có thể mở/thu tập workloads chịu isolation và allowances |
| **spec.policyTypes** | Chỉ định Ingress, Egress hoặc cả hai | Làm thay đổi hướng traffic được policy xử lý |
| **spec.ingress** | Danh sách các điều kiện traffic vào được phép | Có thể mở hoặc thu hẹp những nguồn vào |
| **spec.egress** | Danh sách các điều kiện traffic ra được phép | Có thể mở hoặc thu hẹp đích outbound |
| **from/to** | Chọn peers theo pod, namespace hoặc IPBlock | Đổi phạm vi nguồn/đích được kết nối |
| **ports** | Chọn giao thức/cổng theo semantics API | Đổi loại dịch vụ được phép |
| **metadata.labels/annotations** | Metadata cho quản trị và một số controller | Không tự thay hành vi Kubernetes NetworkPolicy chuẩn, nhưng có thể tác động tool ngoài |

**NetworkPolicy không mặc nhiên là firewall L7:** nó không tự kiểm tra đường dẫn HTTP, JWT, người dùng cuối, JSON body hoặc quyền truy cập object của API. Các CNI có CRD chính sách L7 riêng phải được theo dõi như **một tập tài nguyên bổ sung**, không đánh đồng với API NetworkPolicy cơ sở.

### 2.2. Isolation và tính cộng dồn của các allow rules

Một Pod ban đầu **không bị isolation bởi NetworkPolicy** ở một hướng tương ứng thường không bị NetworkPolicy chuẩn hạn chế traffic ở hướng đó. Khi một hoặc nhiều policies chọn Pod và tác động hướng ingress/egress, những kết nối được phép dựa trên **hợp các rules allow tương ứng**, không phải rule đầu tiên được áp.

Đối với kết nối Pod A → Pod B, cần cân nhắc cả:

- **Egress** từ A, nếu A chịu isolation ở chiều egress.
- **Ingress** vào B, nếu B chịu isolation ở chiều ingress.

Một allow ở A **không tự vượt qua deny/default-deny** ở B. Ngược lại, thêm một policy allow mới có thể **mở rộng hợp rules**, kể cả khi default-deny policy cũ vẫn còn nguyên.

**Kết luận quan trọng cho giám sát:** chỉ kiểm tra “default-deny có tồn tại” là chưa đủ. Một allow policy mới, selector đổi hoặc workload đổi nhãn có thể làm phạm vi kết nối mở rộng dù default-deny vẫn hiển thị.

### 2.3. Ví dụ default deny ingress

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: deny-all-ingress
  namespace: payments-lab
spec:
  podSelector: {}
  policyTypes:
    - Ingress
~~~

Manifest chọn toàn bộ Pod trong namespace **payments-lab** để cách ly ingress theo API chuẩn. Nó **không đặt default-deny egress**. Không áp manifest này vào production chỉ vì muốn kiểm tra; bài viết sử dụng nó như dữ liệu phân tích và lab.

### 2.4. Ví dụ default deny egress

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: deny-all-egress
  namespace: payments-lab
spec:
  podSelector: {}
  policyTypes:
    - Egress
~~~

Nếu không có allow egress khác, các Pod được chọn chịu isolation chiều egress theo semantics NetworkPolicy. Trong hệ thống thật, phải xác định đường DNS, Kubernetes API, mTLS/identity service, health và telemetry cần được cho phép thế nào; **chặn nhầm dependencies** có thể gây outage.

### 2.5. PolicyTypes và bẫy khi bỏ trường

Trong Kubernetes NetworkPolicy, khi **policyTypes** không được chỉ định, API có quy tắc mặc định dựa trên ingress và sự hiện diện của egress rules. Bởi vậy thay đổi một manifest từ ghi rõ **Ingress, Egress** sang bỏ trường **không phải** thao tác chỉ mang tính trình bày.

**Để review và theo dõi dễ hơn, nên khai báo policyTypes rõ ràng** và đưa nó vào các điều kiện phân tích semantics. Khi so sánh desired/live objects, cần xét **defaulted/normalized fields** do API server lưu trả về, tránh cảnh báo giả do manifest và object hiển thị khác cú pháp nhưng không khác hiệu lực.

## 3. Mối nguy: Một thay đổi nhỏ có thể mở rộng quyền rất lớn

### 3.1. NamespaceSelector và podSelector cùng một phần tử là AND

Ví dụ chỉ cho các Pod có nhãn **role: frontend** trong namespace **web-lab** gọi **payments** ở TCP/8443:

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-web-frontend
  namespace: payments-lab
spec:
  podSelector:
    matchLabels:
      app: payment-api
  policyTypes:
    - Ingress
  ingress:
    - from:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: web-lab
          podSelector:
            matchLabels:
              role: frontend
      ports:
        - protocol: TCP
          port: 8443
~~~

Trong **một** mục from, namespaceSelector và podSelector được kết hợp theo nghĩa **chọn những Pods có nhãn phù hợp nằm trong namespace phù hợp**.

### 3.2. Tách selectors ra hai phần tử có thể thành OR

Ví dụ biến thể **rủi ro nếu không chủ ý**:

~~~yaml
# Trích đoạn from — KHÔNG coi là thay thế an toàn cho ví dụ trên.
from:
  - namespaceSelector:
      matchLabels:
        kubernetes.io/metadata.name: web-lab
  - podSelector:
      matchLabels:
        role: frontend
~~~

Ở đây có **hai phần tử** trong danh sách from. Chúng cho phép:

1. Pods trong **bất kỳ namespace nào khớp namespaceSelector** (không còn yêu cầu role=frontend), **hoặc**
2. Pods có **role=frontend trong namespace của chính NetworkPolicy** (vì podSelector riêng thường xét namespace của policy).

Ví dụ không đơn giản là “frontend của mọi namespace”; phạm vi thứ hai nằm trong **payments-lab**. Điều này minh họa vì sao cần **parse cấu trúc YAML và tính tập đối tượng phù hợp**, không chỉ grep từ khóa.

### 3.3. Selector rỗng và thiếu selector

Trong NetworkPolicy chuẩn:

- **spec.podSelector: {}** chọn **tất cả Pods trong namespace của policy**.
- **namespaceSelector: {}** trong peer có thể chọn **tất cả namespaces**, với cách kết hợp các selectors khác như API quy định.
- **podSelector: {}** trong peer có thể chọn **tất cả Pods thuộc phạm vi namespace được xác định**.
- **from: []** và một rule with omitted/empty from có semantics khác nhau tùy cấu trúc API cụ thể. Không thay thế bằng text processing trước khi hiểu schema.

**Không thể khẳng định policy rộng hay hẹp chỉ từ ký tự {}.** Phải xét nó nằm ở trường nào, có selectors khác đồng thời không, và những labels hiện tồn tại.

### 3.4. Thay đổi nhãn có thể thay đổi quyền mà không sửa NetworkPolicy

Giả sử policy cho phép mọi Pods trong namespace có nhãn **access: payments**. Một admin sửa nhãn **namespace analytics** từ access=none thành access=payments. NetworkPolicy không đổi một byte, nhưng namespace analytics giờ có thể trở thành nguồn được cho phép.

Hoặc một Pod đổi nhãn từ **role: worker** sang **role: frontend**, vô tình lọt vào allow selector. Vì vậy phải giám sát **Namespace và Pod/PodTemplate labels** bên cạnh NetworkPolicy resources.

**Cần phân biệt tính năng động hợp lệ:** Deployment rollout, Pod replacement, autoscaling làm tập IP/pod names thay đổi; không phải cứ endpoint member đổi là có vi phạm. Phát hiện nên theo **workload owner, labels được bảo vệ và intended access graph**.

### 3.5. ipBlock và NAT/Service translation

Một rule dùng **ipBlock.cidr** có thể được dùng cho những dải mạng cụ thể:

~~~yaml
# Trích đoạn policy egress minh họa:
egress:
  - to:
      - ipBlock:
          cidr: 198.51.100.0/24
    ports:
      - protocol: TCP
        port: 443
~~~

Dải **198.51.100.0/24** dành cho tài liệu theo RFC 5737; không phải mạng production hoặc IP thật được đề xuất mở. Khi review, cần đánh giá:

- CIDR có mở rộng bất thường tới **0.0.0.0/0** hoặc **::/0** không?
- **except** có bị gỡ không, hoặc phạm vi ngoại lệ có bị thay đổi?
- Đích thực tế ở IP sau/before NAT/Service translation có đúng với kỳ vọng policy không?
- Plugin thực thi ipBlock với **Pod IP, Service IP và ipBlock exceptions** như thế nào?

**Không dùng ipBlock để tự suy ra pod identity mạnh.** Pod IP động và hành vi NAT/Service có khác nhau theo datapath/CNI; network identity theo Pod/Namespace selectors thường phù hợp hơn cho traffic cluster nội bộ.

## 4. Những thay đổi cần đưa vào phạm vi giám sát

### 4.1. Tài nguyên trực tiếp và tác động gián tiếp

| Đối tượng thay đổi | Khả năng tác động | Nguồn sự kiện |
| --- | --- | --- |
| **NetworkPolicy create** | Cách ly Pod hoặc mở thêm allow rules | Kubernetes API audit và watch |
| **NetworkPolicy update/patch** | Đổi selectors, peers, ports, policyTypes | API audit, before/after object diff |
| **NetworkPolicy delete** | Xóa default deny hoặc allow, làm thay policy tổng | API audit, watch deleted object |
| **Namespace labels** | Làm tập namespaces được chọn bởi namespaceSelector thay đổi | Namespace audit/watch |
| **Pod labels** | Thay tập selected sources/destinations | Pod audit/watch, owner rollout |
| **Deployment/StatefulSet/Job Pod template** | Tạo Pod mới với labels/identities khác | Controller workload audit |
| **Service/EndpointSlice updates** | Đổi logical destination và selected target | API watch, traffic evidence |
| **CNI configuration/revision** | Đổi datapath/policy enforcement semantics | Deployment/DaemonSet/IaC và CNI agent status |
| **CNI policy CRDs** | Mở rộng/deny ở L3/L4/L7 tùy plugin | CRD audit/watch theo version |
| **Cloud SG/NSG/firewall changes** | Thay reachability ngoài/phía dưới cluster | Cloud audit + network telemetry |
| **hostNetwork/secondary interface** | Tạo đường đi ngoài điểm giám sát hiện tại | Pod spec/workload/admission events |
| **Ingress/Gateway/Service LoadBalancer** | Tạo hoặc đổi đường public/internal vào service | K8s API audit + controller/cloud audit |
| **Mesh authorization policy** | Đổi danh tính workload/HTTP permissions | Mesh resource audit, proxy configuration |

**Không phải thay đổi nào cũng là NetworkPolicy violation.** Một Service đổi endpoint có thể bình thường khi rollout; một security group mở cổng ngoài cluster vẫn có thể tạo đường bypass nguy hiểm dù NetworkPolicy của pods chưa đổi. Hệ thống theo dõi nên có **phạm vi lớp bảo vệ rõ ràng**.

### 4.2. Khi nào “YAML đổi” chưa chắc “traffic đổi”?

Hai manifest khác nhau về **comment, thứ tự phần tử khi không ảnh hưởng semantics, nhãn quản trị hoặc định dạng** có thể cho cùng chính sách thực. Ngược lại, một trường bị bỏ đi và bị default bởi API server có thể thay hành vi.

Phân biệt ba loại diff:

1. **Text diff:** source file YAML thay đổi dòng nào.
2. **Semantic diff:** tập nguồn/đích/port và hướng kết nối được phép đã thay thế nào.
3. **Effective behavior diff:** data plane thực sự chấp nhận/từ chối traffic nào sau deploy.

**Chỉ text diff là chưa đủ cho security change detection.** Một hệ thống có thể cần parser/schema-aware comparison, Kubernetes object normalization, policy evaluation và kiểm thử traffic.

## 5. Kiến trúc giám sát ba lớp: Desired, observed và enforced

~~~mermaid
flowchart TB
    GIT["GitOps / IaC desired state<br/>reviewed policy"] --> COMPARE["Versioned diff + semantic analysis"]
    API["Kubernetes API actual state<br/>audit/watch"] --> COMPARE
    K8S["Pods/Namespaces/EndpointSlices<br/>time-aware inventory"] --> EVAL["Selector/reachability evaluation"]
    COMPARE --> EVAL
    FLOW["CNI flow verdict + datapath health"] --> CORR["Time-correlated verification"]
    EVAL --> CORR
    CORR --> DETECT["Alerting / investigation"]
    DETECT --> CHANGE["Approval, remediation, rollback"]
    CHANGE -. "Controlled changes" .-> GIT
~~~

### 5.1. Desired state

**Desired state** là policy đã được phê duyệt trong GitOps/IaC hoặc quản trị cấu hình tương đương. Nó cung cấp:

- Ai yêu cầu sửa, mã thay đổi, reviewer và lý do.
- Trạng thái manifest trước/sau và các validation đã chạy.
- Environment/namespace/cluster scope.
- Policy version/commit và lộ trình rollout.

Nếu tổ chức không dùng GitOps, desired state có thể nằm ở một hệ quản trị chính sách có version và approvals khác. Điều cốt lõi là **tồn tại nguồn chính sách được phê duyệt**, không phải bắt buộc một nhà cung cấp GitOps cụ thể.

### 5.2. API observed state

**Kubernetes API state** là objects hiện đang được control plane lưu. Nó cho biết chính sách Kubernetes **được khai báo hiện tại**, nhưng không chứng minh tất cả nodes/CNI đã áp đúng.

Sử dụng **API audit events**, **watch resource changes**, và snapshot/periodic resync để ghi nhận:

- Resource UID/name/namespace và object generation/resourceVersion.
- Verb: create, patch, update, delete.
- Actor/user/service account/impersonation context nếu audit cung cấp.
- Before/after semantics, timestamp và request context.

**ResourceVersion không phải thời gian UTC hoặc global sequence dễ ghép xuyên resources.** Dùng nó để quản lý đồng bộ watch đúng theo Kubernetes API, không thay sự kiện thời gian và audit record.

### 5.3. Enforced data-plane state

**Effective enforcement** là chính sách thực tế trên CNI datapath và network paths liên quan. Kiểm chứng bằng:

- CNI agent/policy repository status và policy revisions theo khả năng.
- Flow logs có **verdict ALLOW/FORWARD/DROP** cùng observation point.
- Test traffic từ nguồn cho phép và nguồn bị cấm trong lab/canary.
- Cloud SG/NSG, node firewall, egress/ingress gateway policies.
- Mesh enforcement khi threat model bao gồm mTLS/L7.

Một flow được **FORWARDED ở một hook** không tự chứng minh ứng dụng đã trả HTTP 200; một ứng dụng trả 403 không tự chứng minh NetworkPolicy đã drop. **Control-plane event và data-plane evidence phải được diễn giải ở đúng lớp.**

### 5.4. Đồng bộ và eventual consistency

Khi API server chấp nhận thay đổi NetworkPolicy, agents trên các nodes có thể cần thời gian nhận watch, tính selector/endpoints, biên dịch rule và áp vào datapath. Trong khoảng ngắn có thể có sự khác biệt giữa **desired/API** và **enforced**.

Theo dõi nên ghi:

- **t0:** đề xuất/merge commit.
- **t1:** API create/patch/delete accepted.
- **t2:** CNI agent nhận/áp policy revision trên từng node nếu có dữ liệu.
- **t3:** lưu lượng lab/synthetic cho thấy verdict đúng.
- **t4:** app availability và metrics trở lại kỳ vọng.

Không gắn nhãn compromise chỉ vì hai tầng lệch trong vài giây nếu triển khai bình thường có độ trễ; cũng không bỏ qua trạng thái **policy chưa được áp suốt nhiều phút**. Ngưỡng phải dựa trên đặc tính triển khai và rủi ro từng namespace.

## 6. Kubernetes API audit: Ai đã sửa NetworkPolicy?

### 6.1. Audit là dữ liệu từ control plane

**Kubernetes auditing** có thể ghi lại các yêu cầu tới API server, bao gồm người/ServiceAccount thực hiện, verb, resource, namespace/name, request URI, giai đoạn xử lý và trạng thái kết quả. Đây là nguồn quan trọng để trả lời:

- Chính sách bị tạo, thay hoặc xóa **lúc nào**?
- Identity nào gọi API và thông qua phương thức xác thực nào?
- Yêu cầu đến **resource nào, namespace nào, verb nào**?
- API server có **chấp nhận** yêu cầu không?
- Có nhiều yêu cầu PATCH/UPDATE/DELETE gần nhau không?
- Có dấu hiệu **impersonation** hoặc controller automation bất thường không?

**Audit log không mặc nhiên chứa trạng thái before/after đầy đủ.** Trường nào được ghi phụ thuộc audit policy **level**, stage, backend và cấu hình; một sự kiện ở level **Metadata** thường không chứa request object/response body. Nếu cần semantic diff, phải kết hợp **object snapshots hoặc GitOps version history** thay vì giả định mọi audit event đã có manifest hoàn chỉnh.

### 6.2. Các audit level có ý nghĩa khác nhau

| Audit level | Nội dung khái quát | Đánh đổi |
| --- | --- | --- |
| **None** | Không ghi log theo rule đó | Mất bằng chứng cho phạm vi bị loại |
| **Metadata** | Metadata request, actor, verb, resource, status/stage theo sự kiện | Ít dữ liệu nhạy cảm; thường không đủ dựng before/after |
| **Request** | Bao gồm request body nếu có theo stage/semantics | Hữu ích cho create/patch nhưng phải bảo vệ dữ liệu và tốn dung lượng |
| **RequestResponse** | Request và response body khi có, theo stage/semantics | Nhiều dữ liệu hơn, tăng privacy/storage risks |

Một audit event **DELETE thành công** ở Metadata level có thể cho biết object bị xóa nhưng **không chứa bản policy trước khi xóa**. Vì vậy cần object history; log audit chỉ là một phần bằng chứng.

### 6.3. Các audit stages

Kubernetes có các giai đoạn như **RequestReceived**, **ResponseStarted** (một số yêu cầu long-running), **ResponseComplete** và **Panic**. Cần phân biệt:

- **RequestReceived:** API server đã nhận yêu cầu; chưa chứng minh thao tác thành công.
- **ResponseComplete:** server đã hoàn thành phản hồi, cần kiểm tra status/result.
- Các sự kiện watch/long-running có thể tạo pattern khác request CRUD thông thường.

**Không đếm tất cả audit events như những lần thay đổi thành công.** Có thể một request được ghi ở nhiều stages; một PATCH trả **403 Forbidden**, **409 Conflict** hoặc lỗi validation không có nghĩa policy đã đổi.

### 6.4. Audit policy minh họa trong lab

Audit policy được cấu hình ở **API server/managed control plane** theo quyền và cơ chế nhà cung cấp hỗ trợ; **không phải NetworkPolicy được apply vào namespace**. Ví dụ dưới thể hiện ý định ghi metadata cho các thao tác ghi đối với NetworkPolicy và đối tượng có thể ảnh hưởng selector.

~~~yaml
# Ví dụ Kubernetes audit policy; do quản trị viên control plane phê duyệt.
apiVersion: audit.k8s.io/v1
kind: Policy
rules:
  # Chỉ metadata để giảm rủi ro log dữ liệu nhạy cảm.
  - level: Metadata
    verbs: ["create", "update", "patch", "delete", "deletecollection"]
    resources:
      - group: "networking.k8s.io"
        resources: ["networkpolicies"]
      - group: ""
        resources: ["namespaces", "pods"]
      - group: "apps"
        resources: ["deployments", "statefulsets", "daemonsets"]
      - group: "batch"
        resources: ["jobs", "cronjobs"]
  # Rule fallback tùy chính sách audit tổng thể của cluster.
  - level: Metadata
~~~

**Quan trọng:**

1. Các rules audit được đánh giá theo thứ tự, quy tắc phù hợp đầu tiên quyết định level; chính sách thực tế cần tích hợp với những rules đã có.
2. Rule fallback ở đây **rộng**, có thể tạo lượng log rất lớn; **không áp nguyên xi** vào control plane production.
3. Chế độ ghi log, backend webhook/log và độ sẵn sàng trên managed Kubernetes khác nhau theo provider/tier; kiểm tra khả năng hỗ trợ.
4. Ghi **Request/RequestResponse** cho resources có Secret/token/PII đòi hỏi đánh giá dữ liệu đặc biệt cẩn trọng.
5. Một audit policy chỉ ghi events; nó **không chặn** thao tác thay NetworkPolicy.

### 6.5. Mẫu audit event giả lập

~~~json
{
  "kind": "Event",
  "apiVersion": "audit.k8s.io/v1",
  "level": "Metadata",
  "stage": "ResponseComplete",
  "requestURI": "/apis/networking.k8s.io/v1/namespaces/payments-lab/networkpolicies/allow-web-frontend",
  "verb": "patch",
  "user": {
    "username": "system:serviceaccount:platform:gitops-controller"
  },
  "objectRef": {
    "resource": "networkpolicies",
    "namespace": "payments-lab",
    "name": "allow-web-frontend",
    "apiGroup": "networking.k8s.io",
    "apiVersion": "v1"
  },
  "responseStatus": {
    "code": 200
  },
  "requestReceivedTimestamp": "2026-11-28T06:00:00Z",
  "stageTimestamp": "2026-11-28T06:00:00Z",
  "auditID": "lab-audit-0001"
}
~~~

Đây là **sự kiện minh họa**, không phải audit log thật từ cluster. Chỉ nhìn event này có thể biết ServiceAccount của controller đã gửi PATCH được chấp nhận, **chưa biết trường nào đã thay**. Muốn xác định ai là **người khởi tạo thay đổi ban đầu**, còn cần liên kết controller với **commit/PR/approval, CI identity, GitOps reconciliation**. Actor tại API server không nhất thiết là người đã merge pull request.

### 6.6. Làm sao tránh thiếu dữ liệu audit?

- Kiểm tra audit policy đang ghi đúng **networkpolicies ở networking.k8s.io** và các resources liên quan.
- Với CNI có CRDs riêng, bổ sung **apiGroup/resource plural** tương ứng theo tài liệu sản phẩm.
- Giám sát **audit log ingestion latency, dropped events, webhook failures, storage retention và clock synchronization**.
- Bảo vệ audit log khỏi người chỉ có quyền sửa chính sách mạng nếu mô hình threat yêu cầu tách trách nhiệm.
- Dùng một **test thay đổi được phê duyệt trong lab** để xác minh một update thành công xuất hiện đúng nguồn và stage.
- Giữ request/auditID, resource UID và timestamps khi tương quan; **không dựa vào username một mình**.

## 7. Watch API: Phát hiện nhanh object thay đổi

### 7.1. Watch khác audit log

**Kubernetes watch** cho phép client theo dõi các sự kiện **ADDED, MODIFIED, DELETED** (và các trường hợp watch protocol khác) đối với một loại resource. Với RBAC phù hợp, nó cung cấp **object state** hoặc thông tin theo semantics watch sau những thay đổi.

Khác biệt:

| Đặc tính | API audit | Resource watch |
| --- | --- | --- |
| Câu hỏi chính | Ai gọi API, request/result gì? | Object nào được thêm/sửa/xóa? |
| Actor trực tiếp | Có thể ghi user/service account | Thường không tự có actor của thay đổi |
| Object sau thay đổi | Tùy audit level | Có thể cung cấp object state theo event |
| Old object/before state | Không được bảo đảm | Collector phải giữ snapshot/cache trước |
| Bằng chứng lịch sử | Phụ thuộc retention/backend | Watch không là archive nếu không tự lưu |
| Mất kết nối | Audit backend có thể thiếu logs | Watch có thể disconnect, quá hạn resourceVersion |

**Audit và watch bổ sung nhau**; không thay thế nhau.

### 7.2. Quy trình List + Watch

Một collector đáng tin thường:

1. **LIST** NetworkPolicies/Namespaces/Pods có quyền đọc trong scope.
2. Ghi snapshot và **resourceVersion** phù hợp từ list response.
3. **WATCH** từ resourceVersion theo API semantics.
4. Với ADDED/MODIFIED/DELETED, cập nhật local cache và lưu event/time.
5. Khi watch bị ngắt hoặc resourceVersion không còn khả dụng (ví dụ **410 Gone/ResourceExpired**), **LIST lại để reconcile**, sau đó WATCH mới theo pattern được API hỗ trợ.
6. Định kỳ đối chiếu desired/live state để tránh thiếu sự kiện khi collector downtime.

~~~mermaid
flowchart TD
    START["Collector start"] --> LIST["LIST policy + related resources"]
    LIST --> SNAP["Snapshot + resourceVersion"]
    SNAP --> WATCH["WATCH change events"]
    WATCH --> SAVE["Normalize + diff against cached state"]
    SAVE --> WATCH
    WATCH -->|Disconnect / expired RV| RESYNC["Re-LIST + reconcile current state"]
    RESYNC --> SNAP
    SAVE --> CORRELATE["Audit actor + Git commit + CNI verdict"]
~~~

**Watch không phải một event stream vĩnh viễn bảo đảm mọi thay đổi trong thời gian collector offline được phát lại.** Một policy có thể bị tạo rồi xóa trong khoảng mất kết nối, snapshot sau đó không thể chứng minh đã từng tồn tại nếu thiếu audit hoặc historical event store.

### 7.3. Kubectl watch chỉ để quan sát trong lab

~~~bash
# Chỉ đọc đối tượng; dừng Ctrl+C khi đủ quan sát.
kubectl get networkpolicies -A --watch

# Theo dõi các namespaces, hữu ích khi namespaceSelector đổi membership.
kubectl get namespaces --watch
~~~

**Không dùng cửa sổ terminal watch làm hệ thống monitoring production.** Nó không tự cung cấp lưu trữ bền vững, actor attribution, cross-cluster correlation hay cảnh báo. Một tài khoản chỉ có RBAC xem namespace cụ thể có thể không dùng được cờ **-A**; đó là giới hạn quyền, không chứng minh NetworkPolicies không tồn tại.

### 7.4. Object UID, generation và resourceVersion

| Thuộc tính | Giá trị điều tra |
| --- | --- |
| **metadata.uid** | Phân biệt object cũ bị xóa và object mới được tạo lại cùng tên |
| **metadata.resourceVersion** | Giúp client phối hợp watch/concurrency đúng API |
| **metadata.generation** | Có thể giúp nhận diện thay đổi desired spec theo semantics resource |
| **metadata.creationTimestamp** | Lúc object được tạo, không phải lúc mỗi lần patch |
| **managedFields** | Gợi ý manager/field ownership khi server-side apply hay các update phù hợp |
| **labels/annotations** | Owner/process metadata hoặc selectors gián tiếp |

**managedFields không phải bằng chứng danh tính người hoặc sự phê duyệt thay đổi.** Field manager có thể do công cụ khai báo, không đồng nghĩa một security principal được xác minh.

**resourceVersion không là Unix timestamp**, cũng không là số thứ tự có thể so sánh tùy ý giữa hai clusters. Khi trình bày incident timeline, dùng audit timestamps, collector event/ingest time và object UID.

## 8. GitOps, IaC và phát hiện cấu hình drift

### 8.1. Chu trình thay đổi được phê duyệt

~~~mermaid
flowchart LR
    PR["PR / change request"] --> REVIEW["Owner + security review"]
    REVIEW --> TEST["Schema + semantic checks"]
    TEST --> MERGE["Merge approved Git state"]
    MERGE --> SYNC["GitOps reconciler / IaC apply"]
    SYNC --> API["Kubernetes API NetworkPolicy"]
    API --> CNI["CNI enforcement"]
    API -. "API audit/watch" .-> MON["Change detection"]
    CNI -. "Flow verdict / synthetic tests" .-> MON
    MON -. "Drift / unexpected outcome" .-> REVIEW
~~~

Một thay đổi theo GitOps vẫn có thể sai. PR được merge không bảo đảm policy an toàn hoặc data plane đã áp; do đó cần **validation trước deploy** và **bằng chứng hậu kiểm**.

### 8.2. Các trường hợp drift

| Loại drift | Ví dụ | Cách phát hiện |
| --- | --- | --- |
| **Out-of-band write** | Người có quyền kubectl sửa policy không qua Git | API audit actor + live-vs-Git diff |
| **Git desired chưa được apply** | Controller lỗi, API deny hoặc sync paused | Sync status, desired-vs-live diff |
| **Live policy bị controller ghi đè** | Nhiều operators cùng quản lý object | managedFields context, audit series và reconciliation logs |
| **Label drift** | Namespace/Pod đổi label làm allow selector rộng | Related resource events + membership diff |
| **CNI enforcement drift** | API đã nhận nhưng node agent chưa cập nhật rules | CNI status/revision và negative tests |
| **Multi-cluster parity drift** | Cluster DR thiếu default-deny | Inventory/policy checks theo cluster |
| **Exception hết hạn** | Temporary allow vẫn tồn tại | Metadata/ticket expiration và review |

### 8.3. Source-of-truth và quyền sửa trực tiếp

Khi Git là nguồn được phê duyệt, cần kiểm soát ai có quyền **update/patch/delete NetworkPolicies trực tiếp** trong API. Một emergency break-glass có thể cần thiết, nhưng:

- Phải ghi **người thực hiện, thời gian, lý do, scope và ticket**.
- Có hạn chót để reconcile thay đổi trở lại source-of-truth.
- Tách quyền người duyệt thay đổi và quyền kiểm soát logging khi cần.
- Cảnh báo khi ServiceAccount không thuộc bộ công cụ đã phê duyệt sửa policy.

**Không cấm hoàn toàn sửa nóng trong incident khi quy trình tổ chức cho phép**, nhưng phải coi nó là ngoại lệ có audit và follow-up.

### 8.4. Tránh drift alert do YAML noise

Không phải khác nhau về:

- Field ordering, whitespace và comments.
- Defaulted fields của API server.
- managedFields, resourceVersion, timestamps.
- Annotations của controller không ảnh hưởng chính sách.

...đều là thay đổi quyền mạng. Một tool nên chuẩn hóa object và chỉ tạo **high-severity semantic alert** nếu có thay đổi thực về **selected subjects, peer selectors, ports, protocols, direction hoặc effective reachability**. Các thay đổi metadata vẫn có thể có ý nghĩa audit/ownership nhưng nên có loại cảnh báo riêng.

## 9. Semantic diff: So sánh điều được phép trước và sau

### 9.1. Vì sao so sánh dòng chưa đủ?

Một diff chỉ cho:

~~~diff
-      role: frontend
+      role: finance
~~~

...chỉ cho biết một giá trị selector được đổi, **chưa cho biết số nguồn được mở hoặc bị chặn**. Có thể hiện tại không có Pod nào gắn nhãn finance, hoặc namespace đó lại chứa nhiều Pods finance hơn frontend. Ngoài ra, Kubernetes **matchLabels không hỗ trợ wildcard bằng ký tự dấu sao để khớp mọi giá trị**; muốn phân tích phạm vi, phải dùng đúng cấu trúc LabelSelector theo API thay vì suy đoán từ một ký tự.

Semantic diff đúng phải parse theo **API schema**, biết selector semantics, đánh giá những namespaces/Pods nào được chọn theo snapshot, và xét tập hợp policies khác.

### 9.2. Mô hình quan hệ được phép

Với một thời điểm T, có thể xây một quan hệ khái niệm:

~~~text
AllowedEdge(T) =
  (source_workload, destination_workload, protocol, port, direction, policy_context)

before_set = Evaluate(all_relevant_policies_before, identities_before)
after_set  = Evaluate(all_relevant_policies_after, identities_after)

newly_allowed = after_set - before_set
newly_blocked = before_set - after_set
~~~

Đây là **mô hình logic**. Thuật toán thực tế cần tuân semantics Kubernetes, các CNI extensions, egress/ingress ở hai phía và các network paths đã kiểm soát; không thể giả định một allow edge suy từ NetworkPolicy chuẩn đồng nghĩa kết nối thực sự có route hoặc backend lắng nghe cổng đó.

### 9.3. Một số loại mở rộng quyền cần đánh dấu

| Diff semantics | Rủi ro | Ví dụ |
| --- | --- | --- |
| Selected Pods tăng | Có thêm workload bị policy chọn, có thể thay isolation/allow | spec.podSelector chuyển sang {} |
| Allowed sources tăng | Nhiều namespace/Pod được vào service | namespaceSelector mở rộng |
| Allowed destinations tăng | Workload được gọi thêm dịch vụ | egress to CIDR rộng hơn |
| Allowed ports tăng | Kết nối tới ports mới | TCP/8443 → mọi ports |
| Allowed protocols tăng | Thêm UDP/SCTP nếu được hỗ trợ | Rule mới cho UDP |
| Allow rule mới | Hợp rules có thể tăng dù default-deny còn | Tạo allow-all trong cùng namespace |
| Policy DELETE | Có thể bỏ isolation hoặc bỏ một allowance | Xóa default-deny egress |
| Label membership đổi | Không có NetworkPolicy diff nhưng tập peer đổi | namespace mới được gắn access=prod |

**Xóa một policy không phải lúc nào cũng làm traffic rộng hơn.** Xóa allow policy có thể chặn kết nối; xóa **policy cuối cùng gây isolation** ở một hướng có thể khiến Pods quay về non-isolated và làm traffic rộng hơn. Cần đánh giá **toàn bộ hợp policies**, không dựa trên “DELETE luôn tốt/xấu”.

### 9.4. Named ports và nhãn workload

NetworkPolicy có thể tham chiếu **named port** tùy loại rule; ý nghĩa port đó được giải thích theo object/pod semantics và plugin. Khi Pod spec thay đổi mapping named port, lưu lượng hiệu lực có thể thay đổi dù policy không sửa.

Do vậy bên cạnh selector labels còn cần xem **PodTemplate/spec.ports**, workloads được owner cập nhật, EndpointSlice, và những chỗ CNI hỗ trợ named port matching. Không tự suy ra một tên port luôn tương đương cùng một số TCP/UDP trên mọi Pod.

### 9.5. Thay đổi namespace membership

Nếu policy cho phép namespace có label **network-access=approved**, một namespace mới được gắn nhãn đó làm membership lớn hơn. Để tránh cảnh báo giả do scale, đếm **newly allowed namespace/workload owners** thay vì chỉ số IP/pods mới.

Đối với namespaces nhạy cảm như **data, identity, finance, control**, có thể đặt guardrail: mọi thay đổi làm tăng cross-namespace allowed edges đều cần **owner approval** và hậu kiểm allow/deny.

## 10. Xếp hạng thay đổi: Policy nào đáng báo động?

### 10.1. Không phải mọi PATCH đều có cùng mức nguy cơ

Độ ưu tiên điều tra phụ thuộc:

- **Độ nhạy cảm đích:** database, secret-management, identity, payments hoặc control plane.
- **Hướng thay đổi:** mới được phép, mới bị chặn, hay chỉ metadata.
- **Mức mở rộng:** thêm một workload đã duyệt hay mở toàn namespace/Internet.
- **Đường đi:** public ingress, cross-namespace, egress Internet, cluster control plane.
- **Người thao tác và nguồn thay đổi:** GitOps controller có commit approved hay một principal chưa rõ.
- **Thời điểm và bối cảnh:** ngoài maintenance window, sát incident, sau namespace label change.
- **Xác minh thực thi:** CNI đã áp policy mới chưa, traffic có thật sự thay đổi?
- **Độ tin cậy của dữ liệu:** object snapshot, audit, pipeline loss, CNI mode.

**Không định nghĩa mọi mở quyền là tấn công.** Việc bổ sung microservice mới có thể cần mở một dependency hợp lệ. Công cụ cần đưa ra **rationale có thể kiểm tra** và phân biệt *rủi ro cấu hình*, *vi phạm quy trình* và *hành vi ác ý đã được chứng minh*.

### 10.2. Ví dụ bảng mức ưu tiên

| Thay đổi phát hiện | Mức quan tâm minh họa | Vì sao |
| --- | --- | --- |
| Xóa policy duy nhất cô lập ingress của database pods | **Rất cao** | Có thể chuyển pods về trạng thái không bị isolation |
| Egress từ namespace nhạy cảm mở CIDR 0.0.0.0/0 | **Cao** | Mở egress rộng, cần kiểm tra IPv6 và mạng dưới |
| Namespace analytics được gắn nhãn nằm trong allow sources của payments | **Cao** | Mở mới cross-namespace trust |
| Allow TCP/8443 từ một workload được duyệt trong approved PR | **Trung bình/kiểm chứng** | Có chủ đích nhưng phải xác minh scope |
| Policy thêm giới hạn egress làm DNS bắt đầu drop | **Cao cho availability** | Có thể gây outage dù mục đích là siết quyền |
| Reorder các YAML fields không đổi semantics | **Thấp/không tạo security alert** | Chỉ thay hình thức |
| NetworkPolicy cập nhật nhưng CNI node chưa áp | **Phụ thuộc thời gian và phạm vi** | Control/data-plane drift |
| CNI flow exporter mất log ngay sau policy change | **Cao cho khả năng quan sát** | Không đủ bằng chứng hậu kiểm |

Các nhãn **cao/thấp** chỉ phục vụ bài học. Trong thực tế thiết lập mức theo **criticality, scope, exploitability, blast radius và mục tiêu dịch vụ**, không theo một bảng cố định.

### 10.3. Risk scoring minh họa

Một hệ thống có thể chấm điểm trên những trục:

~~~text
Risk factors:
  new_reachable_sensitive_targets
  number_of_newly_allowed_workload_owners
  new_internet_egress_scope
  approved_change_reference_present
  unexpected_actor_or_time
  data_plane_mismatch

Decision:
  policy_critical -> require synchronous review
  policy_high -> alert + canary / manual verification
  policy_normal -> log + periodic reconciliation
~~~

Không dùng điểm số như **bằng chứng sự cố**. Một điều kiện mới như **Internet egress từ payment pods** có thể được thiết kế thành hard guardrail bất kể tổng điểm. Đồng thời, số lượng newly-allowed pods bị thay đổi bởi autoscaling không nhất thiết phản ánh quyền mở rộng nếu **workload identity/scope** không đổi.

## 11. Detection engineering: Những rule cần có

### 11.1. Bảng rule theo thay đổi

| Rule | Điều kiện cần quan sát | Nguồn tối thiểu | Giải thích/ngoại lệ |
| --- | --- | --- | --- |
| **Default-deny removed** | Policy cuối gây isolation cho nhóm pod/hướng bị xóa hoặc mất selector | Before/after all policies, Pods | Phải đánh giá hợp rules, không chỉ tên object |
| **Allow-all introduced** | Policy mới tạo ingress/egress rất rộng | Parsed policy, selector evaluation | Phân biệt namespace lab và production |
| **Broad CIDR introduced** | Egress/ingress ipBlock tới 0.0.0.0/0 hoặc ::/0 | Semantic diff, routing context | Rule có thể bị ràng buộc bởi port/other controls |
| **Cross-namespace access widened** | Newly allowed workload owner ở namespace khác | Policy + namespace/Pod labels | Kiểm tra approval/dependency owner |
| **Sensitive port opened** | Đích quản trị/DB/API nhạy cảm được mở thêm | Effective peer/port matrix | Port không tự cho biết ứng dụng/identity |
| **Protected namespace relabeled** | Namespace membership trong allow selector thay đổi | Namespace watch/audit + policy index | Không có NetworkPolicy PATCH cũng có thể rủi ro |
| **Policy modified outside GitOps** | Live object không khớp desired, actor ngoài quy trình | Audit, GitOps, live snapshot | Break-glass có thể hợp lệ nhưng phải audit |
| **CNI policy not applied** | API updated, node revisions cũ quá thời gian kỳ vọng | CNI agent health/status | Ngưỡng dựa trên môi trường |
| **Unexpected egress observed** | Traffic được FORWARDED ngoài intended graph | Flow, NAT/service mapping | Không nhầm with traffic do NAT/mesh |
| **Allowed connectivity lost** | Previously allowed/synthetic flow bị DROPPED sau change | Flow verdict + app tests | Có thể do policy hoặc network path khác |
| **Logging disabled** | Audit/flow exporter/log sink mất dữ liệu quanh change | Pipeline status, config audit | Không tự suy ra actor xóa bằng chứng |
| **Policy object recreated** | Cùng name nhưng UID mới sau delete/create | API audit + UID history | Có thể là reconcile/migration |
| **Temporary exception expired** | Allow exception còn hiệu lực sau deadline | Change registry, policy inventory | Cần owner và approval mới |

### 11.2. Một bản ghi sự kiện chuẩn hóa

~~~json
{
  "event_time_utc": "2026-11-28T06:05:00Z",
  "cluster_id": "lab-east",
  "object": {
    "api_group": "networking.k8s.io",
    "kind": "NetworkPolicy",
    "namespace": "payments-lab",
    "name": "allow-web-frontend",
    "uid": "uid-policy-001",
    "resource_version": "lab-rv-137"
  },
  "operation": "MODIFIED",
  "actor_ref": "system:serviceaccount:platform:gitops-controller",
  "desired_commit_ref": "approved-commit-ref",
  "change_class": "cross_namespace_access_widened",
  "newly_allowed_workload_owners": [
    "analytics-lab/batch-reader"
  ],
  "policy_status": "api_updated_data_plane_not_yet_verified",
  "correlation_id": "lab-change-042"
}
~~~

**Đây là schema tưởng tượng cho giảng dạy**, không phải dữ liệu lấy từ cluster. Trong bản thật:

- **actor_ref** lấy từ audit event, không lấy từ trường do client tự viết.
- **commit_ref** phải được xác minh từ GitOps/CI; không dùng annotation do một editor tự khai làm bằng chứng approvals.
- **newly_allowed_workload_owners** phải là kết quả tính toán policy và membership, không sao chép tên không kiểm chứng.
- **policy_status** phải phân biệt API đã nhận với CNI đã thực thi.

### 11.3. Tương quan thay đổi với dữ liệu lưu lượng

~~~mermaid
sequenceDiagram
    participant G as GitOps / Change source
    participant K as Kubernetes API
    participant A as Audit/Watch collector
    participant C as CNI data plane
    participant F as Flow telemetry
    participant D as Detector
    G->>K: Apply approved NetworkPolicy update
    K-->>A: Audit + watch event
    A->>D: Old vs new semantic diff
    K->>C: Policy change observed by CNI
    C-->>F: Policy revision / allow/drop flows
    F->>D: Actual verdict evidence
    D->>D: Join time + workload identities
    D-->>G: Confirm, alert, or request rollback
~~~

Mỗi hop có thể có **delay/loss**, và một update của Kubernetes API không tự chứng minh policy revision đã được áp trên tất cả nodes. Nếu detector không có CNI integration, phản hồi phải nói **“changed in API; enforcement unknown”** thay vì khẳng định đã mở quyền thành công.

### 11.4. Dấu hiệu cần phân biệt lỗi cấu hình với compromise

**Cấu hình sai** và **tấn công chủ đích** có thể tạo cùng một broad allow policy. Cần đối chiếu:

- Người merge PR, GitOps audit, change ticket và phê duyệt.
- API actor, token/service account privileges và nguồn kết nối control plane.
- Thời điểm policy đổi so với deployment và incident.
- Các flow mới tới namespace nhạy cảm có thực sự xuất hiện không.
- Có sửa log export/secret/RBAC hoặc thay đổi cloud routes đồng thời không.
- Có sự kiện mTLS/authz denial hoặc app data access bất thường không.

Không phát biểu “cluster bị tấn công” chỉ vì phát hiện một rule rộng; cần evidence-driven incident triage.

## 12. Giám sát những nhãn có ảnh hưởng quyền truy cập

### 12.1. Label selectors tạo trust boundary động

Một **namespaceSelector** hoặc **podSelector** dùng labels để xác định peer. Những labels có thể đồng thời dùng cho scheduling, ownership hoặc policy, nhưng khi chúng nằm trong **allow selectors**, thay đổi chúng có thể tương đương thay firewall rules.

Ví dụ:

~~~text
NetworkPolicy ở payments-lab:
  allow ingress từ namespace có:
    network-tier = trusted-app

Namespace web-lab:
  network-tier = trusted-app  -> được chọn

Namespace analytics-lab:
  network-tier = research    -> không được chọn

Change:
  analytics-lab network-tier đổi thành trusted-app

Effective membership:
  analytics-lab có thể trở thành nguồn được phép.
~~~

Vì vậy, nếu API audit chỉ giám sát **networkpolicies**, thay đổi Namespace label này có thể lọt khỏi các cảnh báo.

### 12.2. Các label cần quản trị nghiêm

Nên định nghĩa **protected labels/annotations** dùng trong security selectors, ví dụ:

| Label mục đích | Cần kiểm soát |
| --- | --- |
| **security-zone** | Không cho namespace tự nâng từ guest sang trusted |
| **network-access** | Quyết định namespace nào được vào service nhạy cảm |
| **workload-role** | Vai trò frontend/backend/admin |
| **environment** | Tách prod/dev/test |
| **tenant/security-domain** | Phân vùng tenant và bí mật |
| **node/identity admission labels** | Chỉ các hệ thống đáng tin được cấp/sửa khi được dùng cho security |

Các tên trên chỉ **mang tính gợi ý**, không phải nhãn Kubernetes chuẩn bắt buộc. Kubernetes **không tự bảo vệ một label tùy chọn** khỏi người có quyền sửa object. Cần thiết kế RBAC, admission policy, controller quản lý labels và audit phù hợp để ngăn sửa vượt quyền.

### 12.3. Pod labels sinh từ PodTemplate

Khi Deployment thay **spec.template.metadata.labels**, những Pods mới có thể được gắn labels mới qua rollout, khiến tập được chọn bởi NetworkPolicy thay đổi **theo tiến trình triển khai**. Không chỉ lưu event PATCH Deployment; phải có **effective Pod membership timeline** vì policy áp cho Pod instances thực tế.

Một deployment với 4 replicas có thể từng có cả Pods labels cũ và labels mới. Trong giai đoạn rollout, nguồn/đích được phép có thể là **hợp của hai phiên bản membership**.

### 12.4. Cảnh báo theo membership, không chỉ giá trị label

Khi một label đổi:

1. Tìm những NetworkPolicies (và CNI CRDs) có selector **tham chiếu label đó**.
2. Tính tập namespaces/Pods/workload owners được chọn **trước và sau**.
3. So sánh reachability và các sensitive boundaries.
4. Gắn context actor/change approval và CNI evidence.
5. Cảnh báo nếu **newly allowed** vượt policy hoặc **previously allowed** quan trọng bị mất.

**Không nên quét tất cả policies cho mỗi Pod event nếu cluster rất lớn** mà không có indexing/caching và giới hạn tải. Hệ thống detector cũng phải có budget và backpressure để không làm quá tải API server.

## 13. Admission controls: Ngăn thay đổi rủi ro trước khi xuất hiện

### 13.1. Prevention bổ sung detection

**Theo dõi thay đổi** là phát hiện, còn **admission control** có thể từ chối một object không đáp ứng quy tắc trước khi được API server lưu. Kubernetes có cơ chế admission chuẩn và các hệ thống policy-as-code như **ValidatingAdmissionPolicy** (CEL), hoặc các policy engines bên ngoài theo phiên bản/cấu hình.

Các quy tắc có thể đặt ra:

- Cấm **allow-all ingress/egress** trong namespaces nhạy cảm nếu không có ngoại lệ có phê duyệt.
- Không chấp nhận ipBlock rộng ngoài phạm vi quy định.
- Không cho **xóa default-deny** bởi những service accounts không có quyền hoặc không có quy trình break-glass.
- Hạn chế thay **protected namespace labels** khi không đúng owner.
- Buộc policy có **owner, purpose, review date** dưới metadata quản trị được bảo vệ/kiểm chứng.
- Cấm tạo những entrypoints công khai không có segmentation tương ứng theo policy khác.

**Không nên giả định một CEL policy đơn giản có thể chứng minh toàn bộ effective NetworkPolicy reachability**, vì điều đó phụ thuộc nhiều objects và CNI semantics. Những kiểm tra liên-object phức tạp có thể cần controller/inventory, pre-merge evaluator hoặc admission webhook được thiết kế phù hợp.

### 13.2. Fail behavior của admission webhooks

Khi sử dụng admission webhooks bên ngoài:

- Giới hạn timeout và scope tài nguyên.
- Xác định **failurePolicy** theo rủi ro và mục tiêu availability.
- Không để webhook policy phụ thuộc vào chính traffic bị policy thay đổi mà gây deadlock.
- Có HA, monitoring, logs và cách khôi phục khi webhook outage.
- Kiểm soát quyền tạo/sửa webhook configuration và policy definitions.

**Fail-open** có thể cho phép thay đổi trái policy khi webhook unavailable; **fail-closed** có thể chặn deployment/khắc phục khẩn cấp. Không có lựa chọn đúng tuyệt đối cho mọi namespace.

### 13.3. RBAC là tuyến phòng thủ đầu tiên

Một ví dụ **Role** cấp quyền **chỉ đọc** NetworkPolicies trong namespace lab:

~~~yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  namespace: payments-lab
  name: network-policy-reader
rules:
  - apiGroups: ["networking.k8s.io"]
    resources: ["networkpolicies"]
    verbs: ["get", "list", "watch"]
~~~

**Đây chỉ là Role, chưa gắn với người dùng nào**; cần RoleBinding riêng do admin phê duyệt nếu muốn dùng. Nó không cấp quyền patch/delete và không cấp quyền đọc tất cả namespaces. Để theo dõi cả cluster, một collector có thể cần **ClusterRole** với quyền phù hợp và bảo vệ service account nghiêm ngặt.

Đối với principal thực thi thay đổi, áp least privilege cho **create/update/patch/delete** và quyền sửa **namespaces/PodTemplates** có ảnh hưởng labels. Không trao **cluster-admin** chỉ để quản lý NetworkPolicy của một nhóm ứng dụng.

### 13.4. GitOps policy-as-code gate

Trong một pipeline review:

~~~text
PR opened
  → YAML schema validation
  → Admission/policy rules on rendered manifests
  → Semantic diff vs approved baseline
  → Affected namespaces/workloads analysis
  → Security/owner review if risk threshold exceeded
  → Merge + controlled apply
  → Post-apply CNI/traffic verification
~~~

**Chính sách kiểm tra trước merge và admission tại API không thay thế nhau.** Một người có quyền sửa trực tiếp có thể bỏ qua PR gate nhưng vẫn phải qua admission; ngược lại admission bị cấu hình sai có thể cần được phát hiện bằng GitOps drift và audit.

## 14. Từ API state đến CNI: Xác minh thay đổi đã có hiệu lực

### 14.1. API server không thực thi packet forwarding

Kubernetes API server lưu các NetworkPolicy objects, còn **CNI/network plugin** và những thành phần data plane liên quan chịu trách nhiệm chuyển chúng thành điều kiện lọc mạng. Các plugin có thể thực thi bằng **iptables/nftables, eBPF, Open vSwitch hoặc cơ chế khác**, tùy sản phẩm, version và mode.

Một update NetworkPolicy có thể:

1. Được API server **chấp nhận**.
2. Được controller/CNI agent **nhận qua watch**.
3. Được giải quyết selectors thành identities/endpoints tương ứng.
4. Được cài thành policy rules trên từng node/datapath.
5. Có hoặc không tạo **thay đổi traffic thực tế**, tùy những policies khác, app readiness và network paths.

**Không báo đã bảo vệ đầy đủ chỉ khi bước (1) thành công.** Cần xem policy status/agent health và kiểm thử cho các nguồn bị cấm quan trọng.

### 14.2. Các datasource để xác minh

| Nguồn | Có thể chứng minh | Không tự chứng minh |
| --- | --- | --- |
| **NetworkPolicy GET/LIST** | Object tồn tại và spec hiện tại | Plugin đã áp cho mọi node |
| **Kubernetes API audit** | Yêu cầu, actor và kết quả ở control plane | Packets bị chặn/cho qua |
| **CNI agent/policy status** | Node/endpoint đã đồng bộ rule theo khả năng | Tất cả lớp SG/mesh/app đều cho phép |
| **Flow verdict logs** | ALLOW/FORWARD/DROP tại một hook | HTTP operation đã thành công |
| **Cloud VPC flow logs** | Luồng mạng tại điểm đo cloud | Pod identity đầy đủ, trước/sau NAT |
| **Service mesh policy logs** | Workload identity và L7/mTLS verdict nếu có | Traffic bỏ qua mesh |
| **Synthetic allow/deny tests** | Kết quả của những đường thử cụ thể | Toàn bộ edge của cluster đều đã được kiểm |
| **Application traces** | Operation/status/latency ở tầng ứng dụng | CNI packet policy đã áp đúng ở mọi lối |

**Negative tests** có giá trị đặc biệt: test một request **không được phép** và xác minh nó thật sự không tới ứng dụng. Tuy nhiên, phải thiết kế sao cho thất bại do NetworkPolicy được phân biệt với thất bại do DNS sai, ứng dụng không lắng nghe hoặc authentication.

### 14.3. NAT, Service và vị trí đo

Một client pod có thể gọi:

~~~text
Before service translation:
  source Pod A  -> Service ClusterIP:8080

After destination translation:
  source Pod A  -> destination Pod B:8080

On node underlay:
  node-A IP    -> node-B IP    (nếu encapsulated/routed phù hợp)
~~~

Nếu sensor chỉ thấy VIP trước DNAT, không thể quy ngay kết nối cho một Pod B mà chưa xem endpoint selection. Với **ipBlock**, Service/NAT và CNI mode có thể làm ý nghĩa matching khác mong đợi. Khi đánh giá ảnh hưởng policy, kết hợp **EndpointSlice, conntrack/NAT context, CNI flow logs** và thời điểm.

### 14.4. Truy cập tới host và đường đi đặc thù

NetworkPolicy chuẩn tập trung vào pod network traffic theo mô hình API. Một số đường đi như:

- **hostNetwork Pods** và node-originated traffic.
- Truy cập từ node/host đến Pods theo semantics plugin.
- SR-IOV/Multus secondary network interfaces.
- Host ports/NodePort/externalTrafficPolicy và ingress entrypoints.
- Service mesh proxy/ambient paths.
- Cloud private endpoints, SG/NSG hoặc network firewall bên ngoài CNI.

...có thể cần các kiểm soát khác. **Không áp kết luận “NetworkPolicy đang bảo vệ tất cả”** nếu deployment có những data paths chưa được đo.

### 14.5. Flow verdict và ứng dụng không phải cùng một mức quan sát

Ví dụ chuỗi sự kiện:

~~~text
t=12:00:00 Kubernetes API: patch accepted
t=12:00:02 CNI node-a: policy updated
t=12:00:03 CNI flow: payments-lab ingress DROPPED
t=12:00:04 Client: TCP timeout
t=12:00:05 App: không có HTTP access log cho request đó
~~~

Đây là ví dụ dữ liệu giả lập cho phép liên kết **đúng thời điểm, đúng hook và đúng Pod identity**. Không kết luận timeout là do policy chỉ từ TCP timeout; cần flow verdict/agent log hoặc test đối chứng. Với stream đã tồn tại trước khi policy đổi, **connection tracking và semantics thực thi** có thể khiến kết quả khác việc mở kết nối mới; phải kiểm tra cách plugin xử lý established connections.

### 14.6. Chênh lệch giữa các nodes

Khi một policy áp trên namespace có Pods chạy ở nhiều nodes, một node bị lỗi agent có thể chưa áp revision mới. Dữ liệu cần có nếu sản phẩm hỗ trợ:

- Node ID, agent version và health.
- Policy revision applied/desired.
- Số endpoints chưa đồng bộ.
- Thời gian từ API update tới enforcement.
- Số flow drop/forward bất thường trên từng node.
- Kết quả canary tests trên đại diện nodes/AZs.

Không dùng một request tới Service VIP làm bằng chứng **mọi endpoints** đúng policy; load balancer có thể chọn cùng một healthy pod nhiều lần.

## 15. Theo dõi chính sách CNI mở rộng

### 15.1. NetworkPolicy chuẩn và CRDs khác nhau

Nhiều CNI cung cấp các policy CRDs mở rộng, ví dụ hỗ trợ:

- Global hoặc cluster-scoped policy.
- Deny rules và priority/order theo sản phẩm.
- L7 HTTP/gRPC/DNS policy.
- FQDN-based egress, policy theo identities hoặc entities.
- Host endpoints / node policies.
- Staged/dry-run policy theo edition hoặc mode.

**Không suy ra semantics của một CNI từ tài liệu CNI khác.** Tên field, thứ tự ưu tiên, additive/deny behavior, default action và API versions khác nhau.

Ví dụ, một Kubernetes NetworkPolicy chuẩn có mô hình **allow cộng dồn**; một policy engine riêng có thể hỗ trợ **explicit deny/priority** với cách giải xung đột khác. Một detector chỉ đọc NetworkPolicy chuẩn sẽ bỏ qua thay đổi hiệu lực từ CRDs đó.

### 15.2. Inventory có phiên bản

Đối với mỗi cluster:

~~~text
cluster_id
kubernetes_version
cni_product / cni_version / mode
service_proxy_mode
policy_api_resources
custom_policy_kinds_and_groups
admission_policy_engines
network_topology: IPv4/IPv6, overlay, hostNetwork, secondary interfaces
flow_telemetry_capabilities
~~~

Đừng tự biến những trường này thành file metadata mới ngoài phạm vi bài. Đây là **mẫu inventory cần tồn tại trong hệ thống vận hành thực tế**, để detector biết đang phân tích policy semantics nào.

### 15.3. Một số sai lệch khi nâng cấp CNI

Sau upgrade:

- Policy CRD version/fields có thể thay đổi.
- Chế độ kube-proxy replacement hoặc service routing thay đổi.
- Flow schema/verdict names thay đổi.
- Agent cần thời gian đồng bộ lại policy.
- L7 proxy integration hoặc FQDN policy có thể hoạt động theo giới hạn mới.
- Collector cũ có thể mất events mà không báo “NetworkPolicy đổi”.

Vì vậy, **theo dõi thay đổi network policy** cũng bao gồm **CNI deployment change, agent health và post-upgrade regression tests**, không chỉ audit CREATE/PATCH/DELETE.

### 15.4. Thực hành vendor-specific

Nếu dùng Cilium, Calico hoặc network policy engine cloud-specific, hãy đối chiếu tài liệu chính thức của **đúng phiên bản** về policy status, flow visibility và các lệnh inspection được hỗ trợ. Không đưa lệnh vendor-specific thiếu context vào runbook chung rồi coi nó là công cụ có sẵn trên mọi cluster.

## 16. Thiết kế pipeline giám sát có khả năng phục hồi

### 16.1. Các thành phần chính

~~~mermaid
flowchart TD
    API["Kubernetes audit sink"] --> RECEIVE["Collector / ingest"]
    WATCH["Resource List+Watch"] --> RECEIVE
    GIT["GitOps/IaC approvals"] --> RECEIVE
    INVENTORY["Historical pod / namespace / endpoint state"] --> ENRICH["Temporal identity + selector enrichment"]
    RECEIVE --> NORM["Normalize event, schema and clock"]
    NORM --> ENRICH
    ENRICH --> DIFF["Semantic policy diff + reachability change"]
    CNI["CNI/mesh/cloud flow verdicts"] --> CORR["Correlate enforcement evidence"]
    DIFF --> CORR
    CORR --> ALERT["Prioritized alert / investigation"]
    ALERT --> CASE["Ticket / incident / corrective change"]
~~~

Mỗi nguồn dữ liệu có độ trễ/thiếu khác nhau. Pipeline cần ghi **bằng chứng có thật và mức tin cậy**, không gán actor/policy verdict bằng suy đoán.

### 16.2. Một record chuẩn hóa

| Trường | Tại sao cần? |
| --- | --- |
| **event_time_utc / ingest_time_utc** | Dựng timeline và đo log lag |
| **cluster_id, environment** | Tránh lẫn nhiều clusters |
| **resource apiGroup/kind/namespace/name/UID** | Gắn đúng object, kể cả delete/recreate |
| **operation, API outcome, auditID** | Phân biệt request thất bại và thay đổi thành công |
| **actor principal, auth context** | Truy vết quyền thực thi |
| **source commit/change ID** | Liên hệ mục đích/phê duyệt nếu được xác minh |
| **before/after object hash** | Kiểm tra integrity và idempotency của diff |
| **semantic delta** | Newly allowed/blocked peer/port/direction |
| **affected workload owners** | Đo blast radius bền vững hơn Pod IP |
| **policy revision, CNI node health** | Kiểm tra enforcement |
| **observed verdict evidence** | Xác minh behavior trên data plane |
| **collector/sensor version, loss status** | Biết khi nào dữ liệu không đầy đủ |
| **triage outcome, reviewer, deadline** | Hoàn tất vòng phản hồi |

Không dùng **full YAML dumps chứa annotation nhạy cảm** làm dữ liệu alert mặc định nếu chỉ cần các trường semantics. Hash/UID/links tới kho có RBAC phù hợp thường đủ, tùy yêu cầu pháp lý và điều tra.

### 16.3. Đảm bảo thứ tự, trùng lặp và mất sự kiện

Một event có thể được ghi qua **audit, watch, GitOps logs** cùng lúc. Detector phải tránh:

- Đếm **ba lần** một thao tác như ba policy changes khác nhau.
- Tạo một incident mới cho mỗi watch reconnect.
- Đánh giá current-state snapshot là bản ghi quá khứ trước khi sửa.
- Gán actor audit của một PATCH này cho MODIFIED watch event khác vì cùng name nhưng khác UID/time.

Thiết kế idempotency theo **cluster + resource UID + observed version/event identity** tùy data source, lưu auditID và diff hash để liên kết. Một **khoảng thời gian gần nhau** chỉ là tín hiệu correlation, chưa đủ chứng minh hai sự kiện là cùng transaction.

### 16.4. Khi watch/audit bị mất dữ liệu

| Tình huống | Ứng xử đúng |
| --- | --- |
| Watch timeout hoặc disconnect | Reconnect/resync với List+Watch theo API |
| ResourceVersion expired / 410 Gone | Re-LIST và ghi nhận khoảng trống history |
| Audit sink mất kết nối | Alert telemetry outage; không giả định không có changes |
| Cluster API unavailable | Giữ trạng thái chưa xác minh, thử theo runbook |
| Object bị xóa rồi tạo lại cùng tên | Dùng UID, không nối nhầm lifecycle |
| CNI flow exporter drop nhiều events | Hạ độ tin cậy của verification và phát cảnh báo sensor |
| Node time drift | Dùng event/ingest timestamps và đồng bộ clock |
| GitOps reconciler bị paused | Phát hiện desired/live divergence kéo dài |

**Không có alert có thể là do collector ngừng hoạt động.** Monitoring phải có **heartbeat/coverage, last event timestamps, queue depth, parsing errors, audit sink health và test events đã được phê duyệt**.

### 16.5. Quyền riêng tư và integrity của telemetry

Logs về policy có thể tiết lộ **sơ đồ mạng nội bộ, các vùng nhạy cảm, workloads, service accounts và lịch thay đổi**. Kubernetes audit nếu cấu hình Request/RequestResponse có thể chứa thông tin nhạy cảm từ nhiều resource types.

Cần:

1. Dùng mức audit tối thiểu đáp ứng use case.
2. Giới hạn service account đọc policies/Pod metadata và quyền truy cập SIEM.
3. Không log raw authentication tokens, secrets hoặc body từ resources không cần thiết.
4. Dùng TLS/xác thực từ agents đến sinks và hạn chế egress collector.
5. Có retention, tách quyền sửa policy với quyền xóa audit và backup logs theo yêu cầu.
6. Lưu evidence references, content hash, timestamps và chain of custody khi incident.
7. Quản lý **metric cardinality**: tránh metric labels theo mọi pod UID/IP/name của từng event.

Một hệ thống giám sát policy quá đặc quyền hoặc log quá nhiều secrets **có thể trở thành điểm xâm nhập mới**.

## 17. Từ phát hiện đến ứng phó: Runbook thay đổi NetworkPolicy

### 17.1. Phân loại cảnh báo trước khi thao tác

Khi phát hiện **policy changed**, đừng lập tức xóa rule hoặc cô lập toàn cluster. Trước tiên:

1. Xác định **cluster, namespace, object UID, thời điểm, before/after semantic diff**.
2. Tìm **audit actor, API response, GitOps commit, change ticket** và owner.
3. Kiểm tra các **labels/PodTemplates** khiến selector membership thay đổi.
4. Xác định rủi ro **newly allowed** và **newly blocked** ở các workloads nhạy cảm.
5. Kiểm tra **CNI enforcement status** và flow verdicts trên nodes liên quan.
6. Xem **business availability**: 5xx, DNS errors, latency, health probes.
7. Phân loại thay đổi **approved/expected**, **unapproved config drift**, **maliciously suspicious**, **unable to verify**.

**Không kết luận malicious chỉ từ một ServiceAccount lạ** nếu đó là một controller mới được triển khai hợp lệ; cần đối chiếu quản lý identities và approval.

### 17.2. Quyết định theo mức tác động

| Tình huống | Hành động phù hợp | Cần tránh |
| --- | --- | --- |
| PR được duyệt, semantic delta phù hợp, tests PASS | Ghi nhận và theo dõi canary | Tạo incident chỉ vì policy thay đổi |
| Broad allow không có approval vào namespace nhạy cảm | Tăng ưu tiên, xác minh actor và reachability, đề xuất rollback hẹp | Bỏ qua vì default-deny vẫn tồn tại |
| Default-deny bị xóa và đã mở đường Internet | Áp incident response/containment theo quyền được cấp | Xóa log hoặc thử khai thác ngoài lab |
| Egress bị chặn làm DNS outage | Xác nhận policy drop, khôi phục allow DNS chính xác | Mở egress 0.0.0.0/0 để sửa nhanh |
| CNI agents không đồng bộ | Điều tra agent/node, giảm phạm vi rollout, dùng guardrails tầng khác | Chỉ tin trạng thái API |
| Collector mất dữ liệu | Phục hồi telemetry, đánh dấu verification unknown | Kết luận không có vi phạm |
| False positive từ YAML formatting | Điều chỉnh normalization/severity | Tắt toàn bộ semantic change detector |

### 17.3. Bảo toàn bằng chứng trước khi rollback

Trước khi thay đổi trạng thái (khi không ảnh hưởng yêu cầu containment khẩn cấp):

- Lưu reference **audit event ID**, actor, request/result và timestamp.
- Ghi snapshot/commit ID của before/after policy theo quyền được phép.
- Lưu **Pod UID, Namespace labels, CNI policy revision, flow samples, Node IDs**.
- Ghi lại **policy dependency graph** và các đường newly allowed/blocked.
- Lưu phiên bản thay đổi được phê duyệt hoặc ticket.

Không tải xuống toàn bộ secrets hoặc PCAP có nội dung cá nhân chỉ để điều tra policy; giảm thiểu dữ liệu và dùng kho bằng chứng có RBAC.

### 17.4. Rollback đúng cách

**Rollback** không phải xóa policy vừa thêm một cách mù quáng. Nếu xóa policy đã làm một pod từ isolated trở lại non-isolated, nguy cơ có thể tăng.

Quy trình an toàn:

1. Xác định **source of truth** và object UID.
2. So sánh desired before/after, tính **reachability trước khi revert**.
3. Kiểm tra một phiên bản rollback có làm **mất các thay đổi hợp lệ khác** được merge sau không.
4. Thực hiện qua GitOps/change pipeline hoặc break-glass được phê duyệt.
5. Theo dõi API audit và CNI applied revisions.
6. Chạy allow/deny tests cho đúng **nguồn/đích/port**.
7. Xác minh app health, DNS, mTLS và metrics.
8. Ghi lý do, outcome, owner và follow-up.

**Rollback source manifest chưa bảo đảm rollback data plane ngay lập tức**; phải có kiểm chứng hậu triển khai.

### 17.5. Ví dụ chuỗi sự kiện cần phân tích

~~~text
14:00   PR #123 merged: allow catalog -> payment TCP/8443
14:01   GitOps starts sync
14:02   Kubernetes API accepts NetworkPolicy PATCH
14:03   CNI node-a applied revision 18
14:05   CNI node-b still reports revision 17
14:06   Synthetic test from catalog on node-a passes
14:07   Synthetic test on node-b fails
14:08   Change monitor raises PARTIAL_ENFORCEMENT alert
~~~

Đây là timeline giả định. **Một test pass trên node-a không chứng minh node-b đã đúng policy**. Nếu môi trường không expose per-node revision, cần có đại diện tests/flow evidence và ghi hạn chế coverage.

## 18. Thực hành chỉ đọc: Kiểm tra policies và nguồn thay đổi

**An toàn:** các lệnh bên dưới chỉ nhằm đọc dữ liệu trong Kubernetes cluster bạn **được phép quản trị/quan sát**, không phải để quét hay sửa cluster ngoài quyền. Một số lệnh có thể cần RBAC; lỗi Forbidden không chứng minh resource không tồn tại. Các tên namespace trong ví dụ là giả định.

### 18.1. Xem policies, namespaces và pods liên quan

~~~bash
# Xem toàn bộ policies nếu tài khoản có quyền list cluster-wide.
kubectl get networkpolicies -A

# Xem chi tiết policy trong namespace lab.
kubectl describe networkpolicy -n payments-lab allow-web-frontend
kubectl get networkpolicy -n payments-lab allow-web-frontend -o yaml

# Liệt kê namespace labels và Pod labels đang ảnh hưởng selectors.
kubectl get namespaces --show-labels
kubectl get pods -n payments-lab --show-labels -o wide
kubectl get pods -n web-lab --show-labels -o wide
~~~

**Giới hạn:** output GET hiện tại không cho biết **ai đã sửa** và **trạng thái trước đó**. Để trả lời, dùng audit/GitOps/history; không suy từ metadata.creationTimestamp hoặc managedFields là người sửa cuối.

### 18.2. Đọc objects với field chi tiết

~~~bash
# Đọc định danh duy nhất và resourceVersion của policy.
kubectl get networkpolicy -n payments-lab allow-web-frontend \
  -o jsonpath='{.metadata.uid}{"\n"}{.metadata.resourceVersion}{"\n"}{.metadata.generation}{"\n"}'

# Đọc namespace labels và resource version.
kubectl get namespace web-lab \
  -o jsonpath='{.metadata.labels}{"\n"}{.metadata.resourceVersion}{"\n"}'

# Kiểm tra Pod UID/owner/node/IP hiện tại.
kubectl get pods -n payments-lab \
  -o custom-columns=NAME:.metadata.name,UID:.metadata.uid,NODE:.spec.nodeName,IP:.status.podIP
~~~

Các lệnh đọc chỉ hiển thị **current state**. Một Pod IP hiện tại có thể không phải owner của flow từ tuần trước; khi dựng incident timeline cần object history hoặc CNI identity snapshots theo thời điểm.

### 18.3. Theo dõi live events bằng kubectl

~~~bash
# Watch object changes; dùng Ctrl+C để dừng.
kubectl get networkpolicies -n payments-lab --watch

# Theo dõi namespace membership hiện tại.
kubectl get namespaces --watch
~~~

CLI watch hữu ích để **quan sát trong lab**, không thay một collector có snapshot/resync/audit và retention. Một MODIFIED event có thể do field không thay semantics; cần parse diff.

### 18.4. Kiểm tra quyền đọc và sửa

~~~bash
# Kiểm tra quyền của identity đang sử dụng, không thay RBAC.
kubectl auth can-i get networkpolicies -n payments-lab
kubectl auth can-i list networkpolicies --all-namespaces
kubectl auth can-i patch networkpolicies -n payments-lab
kubectl auth can-i delete networkpolicies -n payments-lab
~~~

**can-i trả lời về quyền theo ngữ cảnh auth đang dùng**, không chứng minh principal đã sửa object. Việc principal có quyền patch/delete rộng là một **rủi ro cần đánh giá**, không mặc định rằng nó đã lạm dụng quyền.

### 18.5. Tìm Pod membership của một selector

Giả sử policy dùng **role=frontend** và namespace được giới hạn là **web-lab**:

~~~bash
# Chỉ liệt kê các Pods ở web-lab có nhãn role=frontend.
kubectl get pods -n web-lab -l role=frontend -o wide

# Xem namespaces nào có nhãn mạng được phép.
kubectl get namespaces -l network-tier=trusted-app --show-labels
~~~

**Hai truy vấn trên chưa đánh giá full effective NetworkPolicy.** Cần xét selectors kết hợp, toàn bộ allow policies, hướng egress/ingress, port/protocol và những CNI extensions liên quan.

### 18.6. Đọc events có giới hạn

~~~bash
# Sự kiện Kubernetes về namespace lab (không phải API audit log).
kubectl get events -n payments-lab --sort-by=.lastTimestamp
~~~

**Kubernetes Events không thay API audit.** Một thao tác sửa NetworkPolicy có thể không tạo Event ứng dụng rõ ràng, và Events thường có retention ngắn hơn audit logs. Để tìm actor của một PATCH, dùng audit backend của control plane.

### 18.7. Kiểm tra resources trước khi thiết kế policy

~~~bash
# Pod/Service inventory hữu ích khi phân tích đường đi.
kubectl get services -n payments-lab -o wide
kubectl get endpointslices -n payments-lab -o wide
kubectl get deployments,statefulsets,daemonsets -n payments-lab

# Xem cấu hình pod spec của một workload đã được phép đọc.
kubectl describe deployment -n payments-lab payment-api
~~~

Việc truy vấn EndpointSlices chỉ mô tả endpoints hiện có; nó không cho biết source app có được gọi vào hay policy ở source có allow egress không. Kết quả phải được đưa vào **sơ đồ trust boundary**.

### 18.8. Xuất bản cấu hình để review mà không sửa cluster

Một nhóm có thể xuất dữ liệu policy từ **cluster lab được phép** và so sánh với **GitOps state** bằng công cụ nội bộ. Nhưng:

- Không đăng manifest chứa topology nhạy cảm lên nơi công khai.
- Loại/ẩn annotations chứa URLs/tokens/identifiers nếu có.
- Tránh so toàn bộ runtime metadata như resourceVersion khi mục đích là semantics.
- Sử dụng file history theo nguồn đã phê duyệt; không tự chỉnh live policy trong bước kiểm tra.

### 18.9. Thử allow/deny đã chuẩn bị sẵn

Trong một lab đã có hai endpoints/Pods và NetworkPolicy được cấp quyền:

| Test | Source | Destination | Kỳ vọng |
| --- | --- | --- | --- |
| **Positive ingress** | frontend được duyệt | payment TCP/8443 | Kết nối được phép ở L3/L4 |
| **Negative ingress** | analytics không được duyệt | payment TCP/8443 | Bị NetworkPolicy từ chối nếu CNI thực thi |
| **Positive egress** | payment | DNS resolver cho phép | DNS hoạt động |
| **Negative egress** | payment | đích Internet ngoài policy | Bị policy chặn theo coverage |
| **Selector change** | Pod/Namespace nhãn mới trong lab | payment | Reachability đổi theo semantics đã tính |
| **Deletion/recreation test** | Policy test duy nhất trong lab | nguồn/đích lab | UID history khác, update pipeline đầy đủ |
| **Failure test** | Node agent test mất sync có kiểm soát | được chỉ định | Alert phát hiện enforcement lag |

Không thử truy cập admin/database thật hoặc quét cả subnet để chứng minh deny. Chọn **đích lab có listener và logs** để phân biệt policy DROP với app không lắng nghe. Một TCP timeout đơn lẻ chưa chứng minh mạng đã được chặn đúng bởi NetworkPolicy.

### 18.10. Đọc CNI evidence

Nếu cluster dùng CNI hỗ trợ policy verdict logs, nên thu:

~~~text
event_time
cluster + node
source: namespace / Pod UID / workload identity
destination: namespace / Pod UID / workload identity
protocol / port / direction
policy name or revision if supported
verdict: FORWARDED or DROPPED
observation point
sensor version and event-loss status
~~~

**Không giả định Cilium/Hubble, Calico flow logs hoặc công cụ khác có sẵn**. Hãy dùng nguồn telemetry mà cluster thực tế hỗ trợ và ghi điểm mù. Flow verdict có thể phản ánh một hook trước NAT, sau NAT hoặc service mesh; cần tìm đúng điểm đo.

## 19. Bảng xử lý sự cố khi policy change gây lỗi

~~~mermaid
flowchart TD
    A["Sau một change, service lỗi hoặc trust boundary thay đổi"] --> B{"Có API audit/watch change?"}
    B -->|Có| C["Actor + UID + semantic before/after"]
    B -->|Không| D["Kiểm tra label changes, CNI/cloud/mesh và telemetry gap"]
    C --> E{"CNI đã áp đúng policy?"}
    E -->|Không| F["Node/agent health, policy revision, resync"]
    E -->|Có| G{"Flow có policy DROP/ALLOW khác kỳ vọng?"}
    G -->|Có| H["Tính lại selectors, peer, port, ingress/egress"]
    G -->|Không| I["DNS, Service/NAT, TLS/mTLS, app authz, dependencies"]
    D --> J["Tìm source-of-truth và đường bypass"]
    F --> K["Canary test + bounded remediation"]
    H --> K
    I --> K
    J --> K
    K --> L["Verify negative + positive flows and record outcome"]
~~~

### 19.1. Một ứng dụng timeout ngay sau default-deny egress

**Khả năng:** ứng dụng không được phép gọi DNS resolver, identity/token service, database hoặc external API. Kiểm tra **DNS events, CNI DROPPED, egress policy của source**, network path và business dependency.

**Khắc phục:** thêm allow hẹp cho đúng destination/port/identity đã được duyệt; không bỏ default-deny hoặc mở Internet toàn bộ để chữa lỗi.

### 19.2. Thấy allow-all mới nhưng traffic vẫn bị từ chối

**Khả năng:** ingress destination allow nhưng source egress deny; CNI chưa áp; node/cloud firewall drop; route thiếu; mesh mTLS reject hoặc backend không ready.

**Khắc phục:** xem cả hai hướng NetworkPolicy, CNI status, flow hook, service endpoint và logs ở các tầng. **Không coi một allow object là lệnh vượt mọi lớp firewall.**

### 19.3. GitOps đã merge nhưng object không đổi

**Khả năng:** sync paused, controller mất quyền, admission deny, manifest không render đến cluster/namespace mong muốn, hoặc controller lỗi.

**Khắc phục:** kiểm tra reconcile status, Kubernetes API audit outcome và desired-vs-live; không áp thủ công bản khác mà chưa biết source-of-truth.

### 19.4. Policy đã cập nhật nhưng một số nodes chưa nhận

**Khả năng:** CNI agent trên node offline, watch lag, networking lỗi, agent phiên bản không tương thích hoặc policy rebuild chưa hoàn tất.

**Khắc phục:** theo dõi agent health/revision, giảm phạm vi rollout, canary theo node, dùng control bổ sung nếu cần. Không đánh dấu PASS chỉ vì một pod test hoạt động.

### 19.5. Alert cross-namespace allow xuất hiện sau label change

**Khả năng:** Namespace label hoặc Pod template label làm selector membership mở rộng. Audit NetworkPolicy có thể hoàn toàn trống.

**Khắc phục:** kiểm tra Kubernetes Namespace/Pod/workload events, quyền sửa labels, temporal mapping và effective allowed peers; xem thêm approval. Không giải thích bằng “không ai sửa policy nên an toàn”.

### 19.6. Có flow FORWARDED nhưng API vẫn 403

**Khả năng:** network path cho kết nối nhưng **mTLS service identity, gateway authorization hoặc ứng dụng** từ chối.

**Khắc phục:** đọc mesh/proxy/app access logs, JWT authorization, user identity và route; không mở NetworkPolicy vì 403 chưa chứng minh network drop.

### 19.7. Không có audit events trong thời gian nghi vấn

**Khả năng:** audit policy loại resource, sink mất kết nối, retention hết, cluster sai, watch collector lỗi hoặc thật sự không có thay đổi.

**Khắc phục:** xác minh audit config, sink/collector health, clock, cluster identity và GitOps/object history. Không tự kết luận “không có thay đổi” khi coverage chưa chứng minh.

### 19.8. CNI policy cho phép mới nhưng không thấy traffic

Điều đó có thể tốt (không ai gọi dịch vụ), hoặc telemetry gap, endpoint không ready hoặc request đi đường khác. **Không cần tạo traffic trái phép** để kiểm chứng: dùng **synthetic allow/deny lab tests**, đối chiếu sensor health và policy evaluator.

### 19.9. Flow drops tăng sau phiên bản app mới

Không nhất thiết là policy vừa bị sửa: app có thể gọi một dependency mới ngoài allowlist, Port đổi hoặc labels mới không khớp. Gắn timeline **Deployment revision, Pod UID, source/destination and CNI policy revision** rồi xem lại yêu cầu nghiệp vụ.

## 20. Case study: Namespace label change mở quyền vào payment API

### 20.1. Kiến trúc ban đầu

Cluster **lab-east** có:

~~~text
Namespace web-lab:
  frontend Pods:
    labels: role=frontend

Namespace analytics-lab:
  batch-reader Pods:
    labels: role=reader

Namespace payments-lab:
  payment-api Pods:
    labels: app=payment-api
    listening port: TCP/8443

Security objective:
  Chỉ frontend đã được phê duyệt truy cập payment-api TCP/8443.
  analytics batch-reader KHÔNG được truy cập payment-api.
~~~

Giả sử policy hiện tại cho phép **role=frontend trong namespace có label security-zone=trusted**; namespace **web-lab** đang có security-zone=trusted, còn **analytics-lab** có security-zone=restricted.

### 20.2. Policy kiểm soát access trong lab

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-trusted-frontend
  namespace: payments-lab
spec:
  podSelector:
    matchLabels:
      app: payment-api
  policyTypes:
    - Ingress
  ingress:
    - from:
        - namespaceSelector:
            matchLabels:
              security-zone: trusted
          podSelector:
            matchLabels:
              role: frontend
      ports:
        - protocol: TCP
          port: 8443
~~~

**Lưu ý:** security-zone là **nhãn tổ chức tự đặt**, không phải Kubernetes security principal mặc định. Chỉ những namespace và pods thỏa **cả hai selectors trong cùng phần tử** được rule này cho vào payment-api TCP/8443. Thực tế còn phải xét **những NetworkPolicies khác và egress ở source**.

### 20.3. Hai lần thay đổi tạo hiệu ứng khác nhau

**Lần A — nhãn namespace:** quản trị viên gắn **security-zone=trusted** cho analytics-lab. Tuy nhiên Pods batch-reader vẫn có **role=reader**, nên **chưa** thỏa điều kiện Pod role=frontend.

**Lần B — PodTemplate label:** một ứng dụng batch khác trong analytics-lab được đổi **role=frontend** (ví dụ để tái dùng template). Các Pods mới của workload đó có thể thỏa **cả security-zone=trusted và role=frontend**, nên trở thành peer mới được policy cho phép tới payment-api.

Điểm mấu chốt là **hai sự kiện riêng lẻ có thể chưa làm mở đầy đủ đường đi**, nhưng **kết hợp** lại làm thay đổi effective allowed graph. Detector cần giữ lịch sử membership và không chỉ dò NetworkPolicy PATCH.

### 20.4. Timeline giả lập

| UTC | Nguồn | Sự kiện |
| --- | --- | --- |
| 08:00 | GitOps | Bản NetworkPolicy allow-trusted-frontend không đổi |
| 08:10 | Kubernetes API audit | PATCH namespace analytics-lab, security-zone trở thành trusted |
| 08:12 | Watch snapshot | analytics-lab nằm trong namespaceSelector membership |
| 08:25 | GitOps Deployment update | batch-frontend template gắn role=frontend |
| 08:27 | Pod watch | Pods mới trong analytics-lab khớp cả hai điều kiện |
| 08:28 | Semantic evaluator | Newly allowed peer tới payment-api được phát hiện |
| 08:29 | CNI agent | Target node đã nhận identity/policy changes |
| 08:30 | Lab synthetic test | Kết nối từ workload test mới được phép ở network layer |
| 08:31 | Payment application | Một request nhận HTTP 403 do authorization |

**Đây là dữ liệu bài tập giả lập.** Nó chứng minh nhiều lớp: network policy có thể cho phép kết nối mới nhưng ứng dụng vẫn có **authorization** ngăn truy cập nghiệp vụ. HTTP 403 không biến network exposure thành không đáng quan tâm.

### 20.5. Vì sao detector chỉ đọc NetworkPolicy sẽ thất bại?

Vì bản NetworkPolicy **không đổi**. Một hệ thống chỉ theo dõi resource **networkpolicies** sẽ không có MODIFIED event cho object đó. Cần:

1. Audit/watch **Namespaces và PodTemplates/Pods**.
2. Chỉ mục selectors đang phụ thuộc labels **security-zone** và **role**.
3. Đánh giá membership trước/sau bằng **workload owner + Pod UID + event time**.
4. Tính lại newly allowed edges theo **all policies**.
5. Xác minh traffic thực qua CNI hoặc test an toàn.

### 20.6. Kịch bản ứng phó

Nhóm security/platform:

- Xác minh **ý định thay namespace label và workload role** từ hai change owners.
- Xem có sự phê duyệt mở quyền payments cho analytics hay không.
- Nếu không hợp lệ, đề xuất **khôi phục đúng label/PodTemplate** hoặc bổ sung policy kiểm soát theo thiết kế, tránh xóa default-deny.
- Kiểm tra liệu một allow policy khác vẫn cho analytics vào payments không.
- Thực hiện change được phê duyệt và kiểm thử **negative**: analytics không thể kết nối network tới payment-api.
- Thực hiện **positive**: web-lab/frontend vẫn truy cập được.
- Kiểm tra CNI flow, app errors, endpoint readiness và tình trạng collector.

**Không nên cố sửa trực tiếp Pod labels rồi bỏ qua Deployment template**, vì controller có thể tiếp tục tạo Pods với nhãn cũ. Sửa tại nguồn quản lý hợp lệ để tránh drift/reconcile loop.

### 20.7. Biến thể: Xóa default deny có thể nghiêm trọng hơn

Giả sử một namespace có **chỉ một policy tạo ingress isolation cho payment-api**, và policy đó bị xóa. Nếu không còn policies nào chọn Pod cho ingress, nó có thể trở thành **non-isolated** ở chiều ingress theo Kubernetes NetworkPolicy.

Một detector chỉ cảnh báo khi **ALLOW rule mới được thêm** sẽ bỏ lỡ nguy cơ này. Cần kiểm tra **isolation state transitions** khi policy DELETE/selector changes:

~~~text
Before:
  payment-api ingress isolated = true
  permitted sources = limited

After removal:
  payment-api ingress isolated = false
  NetworkPolicy API no longer restricts ingress there

Network/firewall/app controls may still restrict traffic,
but Kubernetes NetworkPolicy boundary has changed.
~~~

Không kết luận “mọi người đều truy cập được payment API” vì **routing, SG, mesh mTLS, application authorization** vẫn có thể giới hạn. Nhưng đó là **mất một lớp phòng vệ mạng** phải được nhận diện.

## 21. Checklist vận hành: Theo dõi thay đổi chính sách đúng lớp

| Hạng mục | Câu hỏi nghiệm thu | Bằng chứng mong đợi |
| --- | --- | --- |
| **Desired state** | Có source-of-truth, owner và version cho policy không? | GitOps/IaC review history hoặc system of record |
| **Policy inventory** | Có danh sách NetworkPolicies/CRDs theo cluster/version? | Cluster-scoped inventory |
| **API audit** | Ai create/patch/update/delete và status thế nào? | Audit event, actor, response status |
| **Watch** | Collector bắt events và re-list sau disconnect? | Watch health/reconciliation tests |
| **Object identity** | Phân biệt delete/recreate cùng name? | metadata.uid và history |
| **Semantic diff** | Tính được allowed/isolation changes chứ không chỉ line diff? | Before/after peer/port/direction matrix |
| **Additive policies** | Có xét hợp mọi policies chọn Pod? | Policy evaluation report |
| **Namespace labels** | Có biết selector membership đổi khi labels đổi? | Related resource audit + diff |
| **PodTemplate labels** | Rollout làm source/destination membership thay đổi có được ghi? | Deployment + Pod UID timeline |
| **PolicyTypes** | Có theo dõi ingress/egress và defaulting? | Normalized policy parse |
| **ipBlock** | CIDR và except được review, không lầm Pod CIDR/NAT? | CIDR diff + topology context |
| **Named ports** | Pod spec/port changes có được tính? | Workload spec + effective policy mapping |
| **CNI support** | Plugin thực thi policy theo mode hiện tại? | Agent status, verified negative test |
| **Node consistency** | Có kiểm tra nodes/applied revision khi hỗ trợ? | Node-level telemetry và canary |
| **CNI extensions** | Có monitor deny/priority/L7 CRDs? | Versioned list của CNI policy kinds |
| **Cloud paths** | SG/NSG, NodePort, hostNetwork, IPv6 được xem xét? | Path inventory + negative tests |
| **TLS/mesh** | Phân biệt network allow với mTLS/authz? | Mesh/proxy/app logs |
| **GitOps drift** | Có cảnh báo out-of-band modifications? | Desired/live diff + audit actor |
| **Admission** | Có guardrail chặn broad changes tại API? | Policy test + admission outcomes |
| **RBAC** | Quyền edit/delete policies và labels được hạn chế? | Authz review, can-i results |
| **Audit retention** | Log không bị xóa bởi cùng principal sửa policy? | Security log ownership và storage policy |
| **Detection quality** | FP/FN, test coverage và detector lag được đo? | Labeled lab tests + metrics |
| **Pipeline health** | Có alert khi audit/watch/CNI flow logs mất? | Synthetic events, queue/loss metrics |
| **Rollback** | Có quy trình khôi phục không phá changes hợp lệ khác? | Versioned runbook, canary/negative test |
| **Privacy** | Log không lộ secrets, PII và topology quá mức? | Access control, retention, audit |

**Một checkbox “default-deny tồn tại” không đủ nghiệm thu**. Phải có bằng chứng rằng **những kết nối bị cấm thực sự bị chặn và những kết nối hợp lệ vẫn hoạt động**, kể cả sau một lần thay đổi labels hoặc CNI.

## 22. Câu hỏi thực hành tổng hợp

### 22.1. Câu hỏi

1. NetworkPolicy được ghi nhận thành công trong API có chắc CNI đã áp cho mọi nodes không?
2. Vì sao không thể chỉ theo dõi sự kiện PATCH trên resources networkpolicies?
3. Một Pod có nhiều NetworkPolicies cùng chọn, rules cho phép được kết hợp như thế nào?
4. Xóa policy có luôn làm hệ thống an toàn hơn vì giảm số rules không?
5. PodSelector rỗng ở spec của NetworkPolicy chọn tập nào?
6. NamespaceSelector rỗng trong peer có nghĩa gì, và khi nào nó nguy hiểm?
7. Trong một phần tử from, namespaceSelector + podSelector được kết hợp thế nào?
8. Nếu tách selectors thành hai phần tử from, phạm vi có thể đổi ra sao?
9. Audit level Metadata có luôn chứa nội dung manifest trước và sau PATCH không?
10. Audit RequestReceived có chắc nghĩa là PATCH được chấp nhận không?
11. Nếu ServiceAccount GitOps là actor trong Kubernetes audit, đã biết ai merge PR chưa?
12. Watch collector bị mất kết nối và nhận 410 Gone thì làm gì?
13. Vì sao metadata.resourceVersion không nên dùng như timestamp?
14. Tên NetworkPolicy giống nhau sau delete/recreate có bảo đảm là một object không?
15. Vì sao YAML text diff không đủ để phát hiện thay đổi quyền mạng?
16. Nếu một NetworkPolicy không đổi nhưng namespace label đổi, điều gì có thể xảy ra?
17. Cách đánh giá một newly allowed edge phải xét hai hướng nào?
18. Vì sao allow-all ở NetworkPolicy không đồng nghĩa chắc chắn HTTP 200?
19. Tại sao bộ giám sát NetworkPolicy cần biết CNI product/version?
20. Làm thế nào phân biệt CNI DROP với HTTP 403?
21. Vì sao kiểm tra một request qua ClusterIP chưa đủ để chứng minh mọi Pod endpoints được áp policy?
22. Nếu một egress policy mới làm DNS lỗi, có nên mở 0.0.0.0/0 không?
23. Khi lệnh kubectl get networkpolicies -A trả Forbidden, có thể kết luận policy không tồn tại không?
24. Khi có policy change không được duyệt, cần lưu những bằng chứng nào trước rollback?
25. Nếu audit logs đột nhiên không có policy changes, điều gì phải kiểm tra?

### 22.2. Gợi ý trả lời

**(1)** Không, API acceptance khác CNI enforcement. **(2)** Label changes, CNI/SG/mesh paths và policy CRDs có thể đổi reachability. **(3)** Allow rules được tính theo hợp theo từng hướng isolation. **(4)** Không: xóa policy cuối gây isolation có thể mở traffic. **(5)** Tất cả Pods trong namespace của policy. **(6)** Có thể chọn tất cả namespaces trong phạm vi peer, cần xét selectors khác và policy intent. **(7)** Cùng phần tử là AND. **(8)** Các phần tử riêng trong from là OR, có thể mở rộng scope.

**(9)** Không, Metadata thường không có request/response bodies. **(10)** Không, phải xem kết quả ở giai đoạn phản hồi và status. **(11)** Không, cần CI/GitOps commit, PR/approval history. **(12)** Re-LIST/reconcile rồi WATCH lại theo API, ghi nhận gap history. **(13)** Nó phục vụ API versioning/watch, không phải wall clock. **(14)** Không, dùng object UID. **(15)** Phải xét parser/defaulting, selectors, mọi policies, workloads và datapath. **(16)** Tập sources/destinations khớp selector có thể thay đổi.

**(17)** Source egress và destination ingress khi các bên chịu isolation. **(18)** Route, SG, mTLS/authz và app còn có thể chặn. **(19)** CRDs, enforcement semantics, policy revisions, flow visibility khác nhau. **(20)** CNI verdict cho packet tại hook khác L7 status do app/mesh trả. **(21)** Service có thể chọn một endpoint, nodes khác có thể thiếu policy. **(22)** Không; bổ sung allow hẹp đúng resolver/port/path theo phê duyệt. **(23)** Không, đó là lỗi phân quyền. **(24)** Audit actor/UID/time, trước/sau policies, labels, Git commit, CNI revision, flow evidence. **(25)** Audit sink/collector health, audit policy scope, watch gap, retention, cluster/time context.

## 23. Những hiểu lầm thường gặp

| Nhận định sai | Cách hiểu đúng |
| --- | --- |
| “NetworkPolicy có trong API nghĩa là đã được thực thi.” | Cần CNI hỗ trợ, agents khỏe và bằng chứng enforcement. |
| “Bật audit là đã chặn được thay đổi sai.” | Audit ghi nhận; admission/RBAC/pre-merge controls mới giúp ngăn. |
| “Audit Metadata chứa cả YAML cũ và mới.” | Metadata không bảo đảm request/response body, cần object history. |
| “Thấy RequestReceived là thao tác đã thành công.” | Request có thể bị deny/validation error; phải xem response/result. |
| “Actor trong audit là người merge PR.” | Actor có thể là GitOps controller; cần liên kết CI/PR/approval. |
| “Chỉ theo dõi NetworkPolicy resources là đủ.” | Namespace/Pod labels, CNI CRDs, cloud policies và ingress paths cũng ảnh hưởng. |
| “Một policy default-deny bảo đảm không có allow khác.” | Allow policies cộng dồn; rule mới có thể mở rộng nguồn/đích. |
| “Xóa NetworkPolicy luôn siết bảo mật.” | Xóa policy cuối gây isolation có thể mở rộng traffic. |
| “Một allow ingress đồng nghĩa source egress đã được phép.” | Nếu source chịu egress isolation, phải thỏa allow tương ứng. |
| “Kubernetes NetworkPolicy kiểm tra API permission.” | Nó tập trung vào network peers/ports; application vẫn cần auth/authz. |
| “Mỗi NetworkPolicy rule giống một firewall rule có deny/priority.” | NetworkPolicy chuẩn sử dụng allow semantics cộng dồn; deny/priority là phần mở rộng của plugin khi có. |
| “NamespaceSelector và podSelector luôn là OR.” | Trong cùng peer item chúng được kết hợp; các peer items riêng là OR. |
| “Dấu sao trong matchLabels là wildcard cho mọi Pod.” | LabelSelector API không dùng kiểu wildcard đó; cần semantics chuẩn. |
| “Một diff chỉ đổi indentation là không quan trọng.” | YAML indentation có thể làm thay đổi cấu trúc selectors/rules. |
| “YAML formatting đổi là thay security policy.” | Có thể chỉ là whitespace/metadata, cần semantic diff. |
| “Một label là danh tính bất biến đã xác thực.” | Labels có thể bị sửa theo RBAC/admission; cần bảo vệ protected labels. |
| “Pod IP hiện tại xác định chủ thể của flow cũ.” | Pod IP có thể tái sử dụng; dùng Pod UID và thời gian. |
| “ManagedFields chứng minh ai phê duyệt change.” | Field manager không thay audit identity hoặc PR approval. |
| “resourceVersion là Unix timestamp và so được trên mọi cluster.” | Là giá trị version dùng theo API semantics, không thay event time. |
| “Watch không thể mất events khi collector ngừng.” | Có thể hết lịch sử; cần re-list/resync và audit history. |
| “Một test qua Service chứng minh tất cả nodes giống nhau.” | Service chọn endpoint; cần node coverage/telemetry và canaries. |
| “Flow FORWARDED nghĩa là ứng dụng trả 200.” | Network verdict khác TLS, authorization và business logic. |
| “HTTP 403 có nghĩa NetworkPolicy đang drop.” | 403 là status L7; CNI DROP là sự kiện data plane khác. |
| “Một CIDR rộng luôn có nghĩa client chắc chắn tới được đích.” | Routes, SG/NSG, mesh, policies khác và app có thể vẫn ngăn. |
| “Không thấy policy changes thì không có thay đổi quyền mạng.” | Có thể do label change, CRD, SG, log gap hoặc CNI behavior. |
| “Policy ghi trong Git đủ để khẳng định đang chạy.” | Cần đối chiếu actual API state và CNI enforcement. |
| “GitOps reconcile làm mọi thay đổi ngay lập tức.” | Có độ trễ và failure cases; cần monitor sync/apply. |
| “Tất cả policy engine đều có cùng semantics.” | CNI CRDs, deny/priority/L7 features khác theo sản phẩm. |
| “Mở egress 0.0.0.0/0 là cách sửa DNS timeout tiêu chuẩn.” | Cần cho đúng resolver/port/path, không nới Internet tùy tiện. |
| “Collector không có alert nghĩa là hệ thống đang an toàn.” | Collector có thể mất events, sai schema hoặc ngừng hoạt động. |
| “Một rule rộng đã được merge thì chắc chắn an toàn.” | Approval bổ sung chứ không thay semantic analysis và negative tests. |
| “Rollback = xóa policy mới.” | Xóa có thể bỏ isolation hoặc làm mất những thay đổi hợp lệ khác. |

## 24. Tổng kết

**Theo dõi thay đổi NetworkPolicy** là kiểm tra liên tục sự khác biệt giữa **điều tổ chức muốn cho phép**, **điều Kubernetes API đang lưu** và **điều data plane thực sự đang cho phép/chặn**. Bài toán không kết thúc ở việc thấy một thao tác PATCH trong audit log: NetworkPolicy có **semantics cộng dồn**, selectors phụ thuộc **nhãn Pod/Namespace động**, và CNI có thể cần thời gian/điều kiện để áp rules lên từng node.

Những nguyên tắc quan trọng:

1. **Giám sát đa nguồn:** audit và watch cho change history/state; GitOps/IaC cho intent/approvals; CNI flows cho enforcement; app/mesh/cloud logs cho những lớp còn lại.
2. **So sánh semantics, không chỉ text:** xét isolation state, allowed peer/port/protocol/direction, toàn bộ policies và membership trước/sau.
3. **Bao phủ thay đổi gián tiếp:** Namespace/PodTemplate labels, service routing, named ports, CNI CRDs, cloud firewall, hostNetwork và interface ngoài default datapath.
4. **Dùng identity có thời điểm:** Pod UID, owner, namespace, object UID, audit timestamps và CNI revisions, không dựa vào IP hoặc tên object hiện tại.
5. **Giữ bằng chứng và quyền tối thiểu:** audit actor không thay approval; RBAC/admission/pre-merge checks giảm khả năng phát hành policy rủi ro, logs cần được bảo vệ.
6. **Xác minh bằng hành vi:** chạy cả positive và negative tests trên đúng đường đi, phân biệt API acceptance với CNI enforcement và app authorization.
7. **Có runbook phục hồi:** khi policy gây outage hoặc mở đường nhạy cảm, xác định phạm vi/owner, giữ bằng chứng, rollback hẹp, theo dõi và kiểm chứng lại.

Trong **SECURITY_NETWORK_SECURITY**, việc giám sát chính sách mạng Kubernetes hỗ trợ **phân đoạn, firewall, IDS/IPS, DNS security, xác thực service qua mTLS, quan sát east–west traffic và cloud defense in depth**. Một chính sách tốt không chỉ được viết chính xác một lần, mà phải **duy trì đúng khi workload thay đổi, có khả năng chứng minh bằng lưu lượng thực và được phục hồi có kiểm soát khi sai lệch**.

### Tài liệu tham khảo và hướng đọc thêm

- **Kubernetes Documentation — Network Policies:** mô hình ingress/egress isolation, selectors, peers, ipBlock và semantics additive.
- **Kubernetes API Reference — NetworkPolicy (networking.k8s.io/v1):** schema policyTypes, rules, ports và cách API biểu diễn đối tượng.
- **Kubernetes Documentation — Auditing:** audit policies, levels, stages, backends và ví dụ event.
- **Kubernetes API Concepts — Efficient Detection of Changes:** List/Watch, resourceVersion, bookmarks và xử lý watch disconnect/expired history.
- **Kubernetes Documentation — Labels and Selectors:** matchLabels/matchExpressions, cú pháp và semantics label selector.
- **Kubernetes Documentation — Role-Based Access Control:** service account, Role/ClusterRole, verbs và quy tắc quyền tối thiểu.
- **Kubernetes Documentation — Admission Controllers và ValidatingAdmissionPolicy:** phạm vi policy validation/admission trong control plane.
- **Kubernetes Documentation — Services, EndpointSlices và DNS:** tác động của service routing và endpoint membership đến quan sát traffic.
- **Kubernetes Documentation — Controllers, Pod Lifecycle và Owner References:** cách Deployment/StatefulSet/Job tạo Pod mới và thay labels.
- **Cilium/Hubble Documentation:** network policy identities, eBPF flow verdicts, policy revision và observability theo version.
- **Calico Documentation:** network policies, flow telemetry và những extension/edition-specific semantics.
- **Open Policy Agent / Gatekeeper / Kyverno Documentation:** các phương pháp policy-as-code/admission theo bản triển khai thực tế.
- **OpenTelemetry Documentation:** telemetry pipelines, metrics/logs/traces và Collector health.
- **NIST SP 800-207 — Zero Trust Architecture:** network segmentation phải kết hợp identity, policy và validation.
- **OWASP Kubernetes Security Cheat Sheet:** RBAC, admission controls, network segmentation và audit.
- **Tài liệu cloud provider và CNI đang triển khai:** xác minh chính xác data path, phiên bản chính sách, namespace/Pod identity, log coverage, NetworkPolicy implementation và công cụ kiểm tra tương ứng.
