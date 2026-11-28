# Ingress rule và Egress rule của NetworkPolicy trong Kubernetes

Một nhóm phát triển triển khai ba thành phần trong Kubernetes: frontend, API xử lý đơn hàng và cơ sở dữ liệu. Mặc định, nhiều cluster cho phép Pod liên lạc với các Pod khác ở mức mạng. Nếu frontend bị xâm nhập, nó có thể thử kết nối tới database không cần thiết cho chức năng của mình. Đội an ninh muốn **frontend chỉ gọi API trên cổng 8080**, **API mới được kết nối database trên cổng 5432**, và chỉ các workload được phê duyệt mới gửi DNS queries tới hệ thống phân giải tên.

Kubernetes `NetworkPolicy` cung cấp một cách khai báo **traffic được phép tới Pod (Ingress)** và **traffic từ Pod đi ra (Egress)** dựa trên label selector, namespace, IP range, protocol và port. Nhưng NetworkPolicy **không tự tạo network isolation nếu cluster thiếu CNI hỗ trợ thực thi policy**; policy cũng không xác minh danh tính người dùng, đường dẫn HTTP, tenant hay nội dung gói tin ở L7.

Bài thuộc chương **Bảo mật mạng Kubernetes** của module **SECURITY_NETWORK_SECURITY**, liên hệ với phân đoạn mạng, firewall, xác thực kết nối, DNS, VPN, IDS/IPS, TLS, cloud network và mô hình hóa mối đe dọa.

**Nguyên tắc cốt lõi:** **Ingress/Egress trong NetworkPolicy là hướng lưu lượng tương đối với những Pod được policy chọn**. Những rule cho phép là **cộng dồn**, không có thứ tự ưu tiên kiểu firewall ACL và không có trường `deny` chuẩn. Mỗi policy chỉ có hiệu lực đúng khi **CNI, topology mạng và phạm vi đối tượng** thực sự hỗ trợ.

## 1. Mục tiêu học tập

Sau bài này, bạn cần:

1. Giải thích khác nhau giữa **Ingress của NetworkPolicy**, **Egress của NetworkPolicy** và Kubernetes **Ingress HTTP resource**.
2. Đọc đúng `podSelector`, `namespaceSelector`, `ipBlock`, `policyTypes`, `ports`, `from` và `to`.
3. Phân biệt một danh sách rules **rỗng**, một rule **rỗng `- {}`**, và một danh sách peers/ports bỏ trống.
4. Xây dựng **default-deny ingress/egress**, rồi thêm những luồng **allow tối thiểu** cho DNS và ứng dụng.
5. Giải thích các policy **cộng dồn bằng phép hợp (union)**, cách phối hợp ingress/egress ở hai phía và hành vi của traffic phản hồi.
6. Viết policy đa namespace bằng cách đặt `namespaceSelector` và `podSelector` trong **cùng một phần tử peer**.
7. Nhận diện giới hạn của IP-based egress, Service/ClusterIP, NAT, CNI, `hostNetwork`, node traffic, service mesh và các kết nối đang hoạt động.
8. Thiết kế kiểm thử positive/negative, giám sát, rollout, rollback và checklist cho một phân đoạn mạng Kubernetes.

## 2. Phân biệt Ingress rule, Egress rule và Ingress resource

| Thuật ngữ | Thuộc đối tượng | Ý nghĩa | Không nên hiểu là |
|---|---|---|---|
| **NetworkPolicy Ingress** | `NetworkPolicy.spec.ingress` | Cho phép traffic **đi vào Pod được chọn** | Một HTTP Ingress rule định tuyến hostname/path |
| **NetworkPolicy Egress** | `NetworkPolicy.spec.egress` | Cho phép traffic **đi ra từ Pod được chọn** | NAT gateway hoặc cloud Internet egress policy |
| **Kubernetes Ingress** | Resource `Ingress` | Khai báo HTTP/HTTPS routing tới Service qua ingress controller | Network firewall áp cho Pod theo nguồn/đích |
| **Gateway API HTTPRoute** | Resource `HTTPRoute` | Routing L7 theo hostname/path/header và Gateway | Cơ chế chặn toàn bộ traffic L3/L4 giữa Pod |
| **Cloud security group/firewall** | Cloud VPC/VNet hoặc host | Quy định luồng ở các lớp tương ứng | Cơ chế thay thế hoàn toàn NetworkPolicy |

Ví dụ từ góc nhìn Pod API:

~~~text
  [Frontend Pod] -- TCP/8080 --> [Orders API Pod] -- TCP/5432 --> [DB Pod]
                                  ^
                                  |
                      Ingress của Orders API

  Egress của Frontend:  tới Orders API:8080
  Egress của Orders API: tới DB:5432 và DNS theo chính sách
  Ingress của DB:       chỉ từ Orders API:5432
~~~

Tên `Ingress` dễ gây nhầm vì Kubernetes còn có Ingress Controller/Ingress resource. Trong bài này, nếu không nêu rõ khác, **Ingress/Egress rule luôn là hướng của NetworkPolicy đối với Pod**.

### 2.1. Policy hoạt động ở lớp nào?

`NetworkPolicy` chuẩn tập trung vào connectivity ở **L3/L4**: Pod, namespace, IP ranges, TCP/UDP/SCTP ports nếu plugin hỗ trợ. Nó **không** quy định:

- HTTP URL path `/admin`, hostname HTTP `Host` hay request header.
- Quyền OAuth/JWT, user role, tenant ID hoặc object ID.
- TLS certificate/hostname verification và mTLS peer identity.
- DNS FQDN allowlist bằng một trường chuẩn của Kubernetes NetworkPolicy.
- Kiểm soát lưu lượng host/node hoặc mọi đường xuyên NAT trong tất cả CNI.

Một số CNI/service mesh có **CRD mở rộng** cho FQDN, L7, identity hoặc host policy; đó là **tính năng riêng của sản phẩm**, không tự có trong `networking.k8s.io/v1`.

## 3. Kubernetes NetworkPolicy được thực thi ở đâu?

API server nhận và lưu tài nguyên NetworkPolicy. **Network plugin (CNI) hoặc policy engine tích hợp** chịu trách nhiệm biến các yêu cầu thành quy tắc xử lý gói thực tế theo triển khai. Kubernetes API chấp nhận manifest **không có nghĩa các rule đã được enforce**.

~~~mermaid
flowchart LR
    OPS["Operator / GitOps"] --> API["kube-apiserver"]
    API --> NP["NetworkPolicy API object"]
    NP --> ENGINE["CNI / network-policy enforcement"]
    ENGINE --> VETH["Pod networking / datapath"]
    A["Source Pod"] --> VETH --> B["Destination Pod"]
    POLICY["RBAC / admission / workload identity"] -.-> API
    L7["TLS / App AuthN/AuthZ"] -.-> B
~~~

### 3.1. Điều kiện tiên quyết

Trước khi viết policy cho production, cần biết:

1. Cluster chạy **CNI/plugin nào**, phiên bản nào, và hỗ trợ **Ingress/Egress NetworkPolicy** ra sao?
2. Có hỗ trợ `ipBlock.except`, named ports, SCTP, `endPort`, IPv6 và policy ở traffic path hiện dùng không?
3. Các Pod có dùng `hostNetwork`, secondary interfaces, Multus, egress gateway, eBPF datapath hoặc service mesh không?
4. DNS đi tới **CoreDNS Service, DNS Pods, NodeLocal DNSCache hay resolver ngoài cluster**?
5. Có cloud security groups, host firewall, VPC routing, NAT và endpoint policy ở đường đi không?
6. Có thể thu **flow verdict/logs** từ CNI hoặc công cụ quan sát tương ứng không?

**Không lấy việc tạo một `NetworkPolicy` thành công làm bằng chứng an ninh.** Cần kiểm tra traffic thực tế từ Pod được chọn và Pod đối chứng, trong môi trường được phép.

## 4. Cấu trúc một NetworkPolicy

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-orders-api-from-web
  namespace: orders
spec:
  podSelector:
    matchLabels:
      app: orders-api
  policyTypes:
    - Ingress
  ingress:
    - from:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: edge
          podSelector:
            matchLabels:
              app: web
      ports:
        - protocol: TCP
          port: 8080
~~~

**Cách đọc từ ngoài vào trong:**

- `metadata.namespace: orders`: NetworkPolicy **nằm trong namespace orders**; nó chọn Pod trong namespace này.
- `spec.podSelector.matchLabels.app: orders-api`: **chỉ những Pod orders-api thuộc namespace orders** được policy này áp dụng.
- `policyTypes: [Ingress]`: policy xác định isolation và allowance cho **chiều vào** của những Pod được chọn.
- `ingress.from`: nguồn phải là Pod mang label `app=web` **trong namespace có label `kubernetes.io/metadata.name=edge`**.
- `ports`: lưu lượng **TCP tới cổng đích 8080** được cho phép nếu còn các lớp network/identity khác cũng cho phép.
- Policy này **không tạo quyền egress cho Pod web** và **không chọn Pod của namespace edge** làm target policy.

Label `kubernetes.io/metadata.name` là label namespace được Kubernetes cung cấp ở những phiên bản hỗ trợ; trong môi trường đặc thù cần **kiểm tra label đang tồn tại**. Không tự mặc định một namespace bất kỳ mang những label tùy biến mà đội vận hành chưa gắn.

### 4.1. `podSelector` của spec và `podSelector` trong peer khác nhau

| Vị trí | Ý nghĩa | Phạm vi |
|---|---|---|
| `spec.podSelector` | Chọn **Pod chịu tác động của policy** | Namespace chứa NetworkPolicy |
| `ingress[].from[].podSelector` không kèm `namespaceSelector` | Chọn **Pod nguồn** | Cùng namespace với NetworkPolicy |
| `egress[].to[].podSelector` không kèm `namespaceSelector` | Chọn **Pod đích** | Cùng namespace với NetworkPolicy |
| Peer có cả `namespaceSelector` và `podSelector` | Chọn Pod có nhãn phù hợp **trong các namespace được chọn** | Cross-namespace |
| `namespaceSelector` đơn lẻ | Chọn tất cả Pod trong các namespace phù hợp | Cross-namespace có thể rộng |
| `ipBlock` | Match IP thuộc CIDR và ngoại lệ `except` | IPv4/IPv6 theo khả năng CNI/datapath |

**Bẫy phổ biến:** đặt `namespaceSelector` và `podSelector` ở **hai phần tử `from` khác nhau** tạo phép **OR**, không tạo AND.

## 5. Isolation: khi nào Pod mặc định bị chặn?

NetworkPolicy có mô hình **default allow khi chưa có policy cô lập Pod ở hướng tương ứng**, trong phạm vi datapath/CNI thực thi.

- Nếu **không policy nào** chọn Pod theo hướng Ingress: Pod **không bị cô lập ingress** bởi NetworkPolicy.
- Nếu **có ít nhất một policy** chọn Pod và khai báo `Ingress` trong `policyTypes`: Pod **bị cô lập ingress**; chỉ những luồng khớp **ít nhất một ingress allow rule** của các policy chọn Pod đó được phép.
- Tương tự, `Egress` cô lập **chiều ra** của Pod, không tự cô lập chiều vào.

Mức cô lập có thể khác giữa các Pod trong cùng namespace nếu label selectors chọn các tập khác nhau.

### 5.1. Default-deny Ingress

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: default-deny-ingress
  namespace: orders
spec:
  podSelector: {}
  policyTypes:
    - Ingress
  ingress: []
~~~

Giải thích:

- `podSelector: {}` chọn **mọi Pod trong namespace orders**, không phải mọi Pod toàn cluster.
- `policyTypes: [Ingress]` cô lập chiều Ingress của các Pod đó.
- `ingress: []` không có rule cho phép nào **trong policy này**.
- Nếu còn **policy Ingress khác** cùng chọn Pod, các allow rules của chúng vẫn có hiệu lực vì chính sách cộng dồn.
- Hướng **Egress không bị policy này cô lập** nếu không có policy Egress khác phù hợp.

### 5.2. Default-deny Egress

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: default-deny-egress
  namespace: orders
spec:
  podSelector: {}
  policyTypes:
    - Egress
  egress: []
~~~

Hậu quả có thể gặp: Pod không phân giải DNS được vì DNS query cũng là **egress**; ứng dụng mất kết nối database, API, telemetry hoặc dịch vụ identity cho tới khi có allow rules phù hợp.

### 5.3. Default-deny hai hướng

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: default-deny-both
  namespace: orders
spec:
  podSelector: {}
  policyTypes:
    - Ingress
    - Egress
  ingress: []
  egress: []
~~~

Đây là **baseline policy** cho namespace orders, **không phải deny tuyệt đối không thể vượt**. Một policy khác cho phép traffic vẫn được cộng vào. Không thể áp một NetworkPolicy “deny mới” để ghi đè một allow rule có sẵn: phải sửa/xóa allow policy gây phạm vi quá rộng.

### 5.4. Trường `policyTypes` bỏ trống có nguy cơ gì?

Nếu `policyTypes` không được khai báo, Kubernetes suy ra loại policy theo rules: **Ingress luôn nằm trong tập mặc định**, còn **Egress được bổ sung khi có egress rules**. Vì vậy:

- Đừng đoán `egress: []` mà **không khai báo `policyTypes: [Egress]`** sẽ tạo default-deny egress như ý.
- Để dễ review và tránh mơ hồ, **khai báo `policyTypes` tường minh**.
- Không dùng một ví dụ chỉ có `ingress` rồi kết luận outbound traffic đã được cô lập.

## 6. Quy tắc cộng dồn: NetworkPolicy không có `deny` chuẩn

Nếu Pod `orders-api` khớp ba policy Ingress:

~~~text
Policy A: cho frontend vào TCP/8080.
Policy B: cho monitoring vào TCP/9090.
Policy C: cho namespace staging vào TCP/8080.

Ingress thực được phép cho Pod:
  union(A.allow, B.allow, C.allow)

Không có:
  "C là policy cuối, ghi đè A"
  "default-deny có priority cao hơn allow"
  "một policy deny riêng xóa quyền của B"
~~~

Một policy mới **có thể mở rộng thêm** các luồng được phép, không thể tự thu hẹp những allowance do policy khác đã tạo.

### 6.1. Điều này khác firewall ACL có thứ tự

| Mô hình | Cơ chế ra quyết định |
|---|---|
| Kubernetes NetworkPolicy chuẩn | Các allow rules của mọi policy phù hợp được **hợp lại**; cô lập theo từng hướng |
| Firewall rule list truyền thống | Có thể có deny/allow với thứ tự, priority, first-match hoặc các semantics riêng |
| Cloud security group điển hình | Thường additive allow, nhưng chi tiết theo cloud |
| CNI vendor policy CRD | Có thể hỗ trợ explicit deny, tiers/priority và L7; **không phải** NetworkPolicy API chuẩn |

Khi một luồng bị cho phép ngoài ý định, phải tìm **tất cả NetworkPolicies chọn Pod** và so các rule, không chỉ xem manifest cuối được GitOps áp.

### 6.2. Test trước khi tin policy

Ví dụ default-deny được áp nhưng kết nối tới API vẫn thành công:

1. Pod đích có đúng namespace và labels được policy chọn không?
2. CNI có hỗ trợ NetworkPolicy và thực thi thành công không?
3. Có **policy khác** cho phép cùng luồng không?
4. Đây là Pod traffic thông thường hay `hostNetwork`/node/service special path?
5. Kết nối TCP đã tồn tại **trước khi policy thay đổi** không?

Không sửa bằng cách thêm một “deny policy” tưởng tượng vào NetworkPolicy chuẩn.

## 7. Cách đánh giá một Ingress rule

Ví dụ:

~~~yaml
ingress:
  - from:
      - podSelector:
          matchLabels:
            role: gateway
      - namespaceSelector:
          matchLabels:
            environment: observability
    ports:
      - protocol: TCP
        port: 8080
      - protocol: TCP
        port: 9090
~~~

Đối với **Pod đích đã được `spec.podSelector` chọn**, rule này cho phép:

- Traffic từ Pod `role=gateway` **cùng namespace với policy**; **HOẶC**
- Traffic từ **mọi Pod** trong các namespace có label `environment=observability`;
- Và cổng đích phải là **TCP/8080 HOẶC TCP/9090**.

Hai phần tử `from` có quan hệ **OR**. Hai phần tử `ports` cũng có quan hệ **OR**. Điều kiện peer và port ở trong **cùng một ingress rule** phải cùng thỏa để tạo allowance.

### 7.1. Cách viết AND đúng cho namespace và Pod

~~~yaml
ingress:
  - from:
      - namespaceSelector:
          matchLabels:
            kubernetes.io/metadata.name: edge
        podSelector:
          matchLabels:
            app: web
    ports:
      - protocol: TCP
        port: 8080
~~~

Đây là **một peer** có hai selectors; kết quả là **Pod app=web AND nằm trong namespace edge**, không phải tất cả Pod namespace edge.

### 7.2. Một lỗi YAML thụt đầu dòng mở rộng quyền

~~~yaml
# ANTI-PATTERN: 2 phần tử trong from => OR, KHÔNG phải AND.
ingress:
  - from:
      - namespaceSelector:
          matchLabels:
            kubernetes.io/metadata.name: edge
      - podSelector:
          matchLabels:
            app: web
    ports:
      - protocol: TCP
        port: 8080
~~~

Hệ quả là allow:

1. **Mọi Pod của namespace edge**, dù không có label `app=web`; **hoặc**
2. **Mọi Pod app=web trong namespace chứa policy**, kể cả chúng không thuộc namespace edge.

Đây là một ví dụ dễ gặp về **cross-namespace privilege expansion** không phải do lỗi CNI, mà do cấu trúc list items trong YAML.

### 7.3. Không khai báo `from` hoặc `ports`

Một ingress rule không giới hạn `from` thường match **mọi nguồn** trong phạm vi semantics của NetworkPolicy; một rule không khai báo `ports` thường match **mọi port/protocol được mô hình hỗ trợ**. Vì vậy rule sau rất rộng:

~~~yaml
# ANTI-PATTERN: cho phép inbound từ mọi nguồn tới Pod được chọn.
ingress:
  - {}
~~~

**Khác hoàn toàn** `ingress: []` là **không có allow rule trong policy**. Khi review YAML, phân biệt **empty list** với **list chứa empty rule** là bắt buộc.

## 8. Cách đánh giá một Egress rule

Egress áp dụng cho những Pod được `spec.podSelector` chọn, nhưng các fields `to` và `ports` mô tả **đích và cổng của lưu lượng gửi đi**.

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: orders-api-to-db
  namespace: orders
spec:
  podSelector:
    matchLabels:
      app: orders-api
  policyTypes:
    - Egress
  egress:
    - to:
        - podSelector:
            matchLabels:
              app: orders-db
      ports:
        - protocol: TCP
          port: 5432
~~~

Đọc như sau: chỉ Pod `app=orders-api` ở namespace orders được **phép gửi TCP tới cổng 5432 của các Pod `app=orders-db` trong cùng namespace**, nếu những lớp kiểm soát khác cho phép.

Nó **không**:

- Cho phép mọi app đọc database bằng một tài khoản bất kỳ.
- Tự cấp ingress tại Pod `orders-db` nếu database đã bị ingress-isolated.
- Đảm bảo DNS hay service IP đến database hoạt động trong mọi CNI.
- Tự loại bỏ egress allowance khác được policy khác cấp.

### 8.1. Egress không giới hạn đích là một lỗ hổng có thể có

~~~yaml
# ANTI-PATTERN nếu mục tiêu là kiểm soát egress Internet:
egress:
  - ports:
      - protocol: TCP
        port: 443
~~~

Vì **không có `to`**, rule thường cho các Pod đã chọn gửi TCP/443 tới **mọi đích** thuộc phạm vi match, không chỉ dịch vụ HTTPS hợp lệ. Egress TCP/443 **không đồng nghĩa chỉ tới website tin cậy hoặc đúng tenant**.

Nếu mục tiêu là giới hạn đúng FQDN/SaaS, Kubernetes NetworkPolicy chuẩn **không có selector tên miền**. Cần kiến trúc egress proxy/gateway, cloud firewall hoặc CNI extension có DNS/FQDN policy phù hợp và được kiểm thử.

## 9. Hai phía của kết nối: khi nào cần cả Ingress và Egress?

Đối với kết nối Pod A → Pod B, xét hướng đi **từ Pod A** và hướng đến **Pod B**:

~~~mermaid
flowchart LR
    A["Pod web (namespace edge)"] -->|"Egress của web: TCP/8080"| LINK["Datapath / Service / routing"]
    LINK -->|"Ingress của orders-api: TCP/8080"| B["Pod orders-api (namespace orders)"]
    B -.->|"Response traffic theo flow state/CNI"| A
~~~

- Nếu web **egress-isolated**, phải có policy cho phép **web → orders-api**.
- Nếu orders-api **ingress-isolated**, phải có policy cho phép **web → orders-api** ở phía orders-api.
- Nếu một phía **không isolated theo hướng tương ứng**, NetworkPolicy tại phía đó không yêu cầu allowance bổ sung.
- Nếu cả hai phía đều isolated, **cả hai điều kiện** phải thỏa.
- **Lưu lượng phản hồi** cho một kết nối được cho phép thường được datapath/CNI xử lý theo trạng thái kết nối, không cần tạo explicit reverse rule chỉ cho response. Các protocol/connection-tracking và CNI có chi tiết riêng cần test.

### 9.1. Ma trận hai hướng

| Egress Pod A | Ingress Pod B | Kết quả A → B do NetworkPolicy |
|---|---|---|
| Không isolated | Không isolated | Không bị chặn bởi NetworkPolicy |
| Isolated, không có allow | Không isolated | Bị chặn tại phía A |
| Không isolated | Isolated, không có allow | Bị chặn tại phía B |
| Isolated, có allow tới B | Isolated, không allow từ A | Bị chặn tại phía B |
| Isolated, không allow tới B | Isolated, có allow từ A | Bị chặn tại phía A |
| Isolated, có allow tới B | Isolated, có allow từ A | Được NetworkPolicy cho phép; còn tùy DNS, route, service và AuthZ |

**Được NetworkPolicy cho phép ≠ kết nối sẽ thành công**. Pod đích có thể không listening, Service selector sai, TLS sai chứng chỉ, database không cho login hoặc cloud firewall còn chặn.

## 10. Thiết kế một ứng dụng ba tầng

Ta dựng một mô hình lab với:

| Thành phần | Namespace | Labels minh họa | Cổng ứng dụng |
|---|---|---|---|
| Frontend | `edge` | `app=web` | Gửi tới API |
| Orders API | `orders` | `app=orders-api` | Nhận TCP/8080 |
| Orders DB | `orders` | `app=orders-db` | Nhận TCP/5432 |
| DNS | `kube-system` | Label tùy triển khai CoreDNS | UDP/TCP/53 hoặc đường node-local khác |

**Policy mục tiêu:**

- Namespace edge và orders bắt đầu bằng **default-deny ingress/egress** cho mọi Pod trong hai namespace.
- Pod web được gửi TCP/8080 tới Pod orders-api; không được kết nối trực tiếp DB.
- Pod orders-api chỉ nhận TCP/8080 từ web của namespace edge.
- Pod orders-api được gửi TCP/5432 tới Pod orders-db.
- Pod orders-db chỉ nhận TCP/5432 từ orders-api.
- Web/API được gửi DNS tới resolver được phê duyệt; đường DNS thực phụ thuộc cluster.
- Quyền API/DB/TLS và Secret management vẫn áp dụng riêng.

### 10.1. Sơ đồ flow

~~~mermaid
flowchart TD
    subgraph EDGE["Namespace edge"]
      WEB["Pod app=web"]
    end
    subgraph ORDERS["Namespace orders"]
      API["Pod app=orders-api"]
      DB[("Pod app=orders-db")]
    end
    subgraph DNS["Namespace kube-system / node DNS"]
      RES["CoreDNS hoặc NodeLocal DNSCache"]
    end
    WEB -->|"ALLOW TCP/8080"| API
    API -->|"ALLOW TCP/5432"| DB
    WEB -->|"ALLOW DNS theo topology"| RES
    API -->|"ALLOW DNS theo topology"| RES
    WEB -.->|"DENY TCP/5432"| DB
    WEB -.->|"DENY không được cấp phép"| OUT["Các đích khác"]
~~~

Trong lab này, các label namespace và Pod phải đúng như thiết kế. Đây là **tình huống minh họa**; chưa có Deployment/Service/DB thật được tạo bởi việc đọc bài.

## 11. Bước 1 — Baseline default-deny cho từng namespace

Một NetworkPolicy chỉ chọn Pod **trong namespace của chính nó**; vì vậy phải tạo baseline cho **mỗi namespace** muốn cô lập.

~~~yaml
# Namespace edge
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: default-deny-both
  namespace: edge
spec:
  podSelector: {}
  policyTypes: [Ingress, Egress]
  ingress: []
  egress: []
---
# Namespace orders
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: default-deny-both
  namespace: orders
spec:
  podSelector: {}
  policyTypes: [Ingress, Egress]
  ingress: []
  egress: []
~~~

**Cảnh báo vận hành:** việc áp default-deny Egress vào một namespace production có thể làm hỏng **DNS, gọi API, registry access, telemetry, OAuth/IdP, database, message queue và webhook**. Không áp mù lên namespace hệ thống hoặc cluster đang phục vụ khách hàng. Cần inventory các luồng, có canary và kế hoạch khôi phục.

## 12. Bước 2 — Cho phép đúng các luồng ứng dụng

### 12.1. Ingress của API chỉ từ frontend ở namespace edge

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: api-ingress-from-edge-web
  namespace: orders
spec:
  podSelector:
    matchLabels:
      app: orders-api
  policyTypes: [Ingress]
  ingress:
    - from:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: edge
          podSelector:
            matchLabels:
              app: web
      ports:
        - protocol: TCP
          port: 8080
~~~

Khi review, để ý **`namespaceSelector` và `podSelector` cùng nằm dưới một ký hiệu `-` của danh sách `from`**. Nếu sai indent hoặc tách thành hai peers sẽ mở rộng quyền ngoài ý định.

### 12.2. Egress của frontend chỉ đến API

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: web-egress-to-orders-api
  namespace: edge
spec:
  podSelector:
    matchLabels:
      app: web
  policyTypes: [Egress]
  egress:
    - to:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: orders
          podSelector:
            matchLabels:
              app: orders-api
      ports:
        - protocol: TCP
          port: 8080
~~~

Hai policy ở mục 12.1 và 12.2 phối hợp cho kết nối **web → orders-api** trong trường hợp cả web egress và API ingress đã bị cô lập.

### 12.3. Egress của API chỉ đến database

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: api-egress-to-orders-db
  namespace: orders
spec:
  podSelector:
    matchLabels:
      app: orders-api
  policyTypes: [Egress]
  egress:
    - to:
        - podSelector:
            matchLabels:
              app: orders-db
      ports:
        - protocol: TCP
          port: 5432
~~~

### 12.4. Ingress của database chỉ từ API

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: db-ingress-from-orders-api
  namespace: orders
spec:
  podSelector:
    matchLabels:
      app: orders-db
  policyTypes: [Ingress]
  ingress:
    - from:
        - podSelector:
            matchLabels:
              app: orders-api
      ports:
        - protocol: TCP
          port: 5432
~~~

**Kết quả kỳ vọng trong mô hình lab:** web tới API/8080 thành công theo NetworkPolicy; API tới DB/5432 được phép; web trực tiếp tới DB/5432 không được phép. Tuy nhiên **database authorization vẫn độc lập**: một user chưa được cấp quyền DB phải bị từ chối ngay cả khi network đã allow.

## 13. Bước 3 — Egress DNS sau default-deny

**DNS là một trong những kết nối bị quên nhiều nhất khi áp default-deny Egress.** Pod có thể cần phân giải `orders-api.orders.svc.cluster.local` thành địa chỉ Service để thực hiện kết nối. Khi DNS bị chặn, ứng dụng thường báo lỗi "không tìm thấy host" trước khi có cơ hội thử TCP đến API.

### 13.1. Ví dụ allow DNS tới CoreDNS Pods

Trong một cluster lab, giả sử các CoreDNS Pods thuộc namespace `kube-system` và có label `k8s-app=kube-dns` (đây là **giả định phải xác minh**):

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: web-egress-to-cluster-dns
  namespace: edge
spec:
  podSelector:
    matchLabels:
      app: web
  policyTypes: [Egress]
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

**Kiểm tra trước khi sử dụng:**

1. Xem **labels của DNS Pods** thực tế; nhiều cluster dùng labels khác.
2. Xác định địa chỉ Service DNS trong `/etc/resolv.conf` của Pod, và có sử dụng NodeLocal DNSCache hay không.
3. Kiểm tra cách CNI thực thi policies khi request gửi tới **Service ClusterIP** rồi được NAT/định tuyến tới DNS Pod. Không giả định mọi datapath xử lý trước/sau DNAT giống nhau.
4. Kiểm tra DNS có đi qua node-local IP, địa chỉ link-local hoặc proxy không; ví dụ Pod-to-Pod selector ở trên có thể **không đủ**.
5. Kiểm tra cả **UDP/53 và TCP/53** khi hệ thống yêu cầu. DNS response lớn, retries hoặc một số chế độ resolver có thể cần TCP.
6. Không dùng `egress: - {}` để "chữa DNS" vì nó có thể cho phép **mọi egress** theo semantics NetworkPolicy.

Nếu Orders API cũng cần phân giải DNS, phải tạo policy tương ứng trong **namespace orders** chọn `app=orders-api`. Một policy ở edge không tự áp sang orders.

### 13.2. Tại sao không chỉ cho tất cả Pod gọi UDP/53 ra ngoài?

Rule chỉ giới hạn **cổng 53** nhưng không giới hạn **đích** vẫn cho phép workload gửi DNS tới resolver bất kỳ có thể tới được theo route. Điều này có thể làm mất kiểm soát tên miền nội bộ hoặc khả năng quan sát.

Để bảo vệ DNS:

- Hạn chế nguồn và **đích DNS resolver** theo policy có khả năng thực thi.
- Dùng resolver được quản trị, logging/retention theo chính sách và cơ chế chống DNS abuse.
- Xử lý các client sử dụng **DoH/DoT**: chuẩn NetworkPolicy không thể suy tên miền từ một TCP/443 connection.
- Có đường egress cho các hệ thống identity, certificate validation hoặc cloud APIs liên quan nếu thật sự cần; không bỏ tất cả vào "DNS exception".

## 14. `ipBlock`: giới hạn theo địa chỉ IP và CIDR

`ipBlock` hữu ích trong một số trường hợp muốn match **IP/CIDR**, thường thích hợp hơn với các địa chỉ **ngoài cluster** được quản lý ổn định. Ví dụ:

~~~yaml
# Ví dụ cho lab, KHÔNG tạo kết nối tới một dịch vụ Internet thật.
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: demo-egress-to-documentation-range
  namespace: sandbox
spec:
  podSelector:
    matchLabels:
      app: cidr-lab-client
  policyTypes: [Egress]
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

`203.0.113.0/24` là dải IPv4 dành riêng cho **tài liệu**, không phải đích dịch vụ thật. Rule minh họa ý định cho TCP/443 tới một phần CIDR và loại trừ nửa dải qua `except`.

### 14.1. Các giới hạn thường gặp

- **Địa chỉ của SaaS, CDN, storage, cloud API có thể đổi**, được dùng chung bởi nhiều tenant hoặc phụ thuộc DNS/region.
- IP sau **SNAT/DNAT**, Service, ingress hoặc egress gateway có thể khác địa chỉ ứng dụng tưởng mình đang kết nối. **Thứ tự NAT và network policy không được chuẩn hóa đồng nhất cho mọi CNI**.
- Pod IP là địa chỉ có vòng đời động; dùng `podSelector`/`namespaceSelector` thay `ipBlock` để mô tả **workload trong cluster** khi phù hợp.
- IPv6 cần policy/IP ranges tương ứng và CNI hỗ trợ dual-stack; chỉ bảo vệ IPv4 có thể để lọt luồng IPv6 khác.
- `ipBlock.except` là ngoại lệ đối với CIDR trong **chính một peer**, không phải một quy tắc **deny toàn cục** ghi đè policy khác.

Nếu policy A cho phép `203.0.113.0/24` trừ nửa sau, nhưng policy B khác cho phép toàn bộ `203.0.113.0/24` với cùng port, **B có thể mở lại dải đã loại trong A** vì allowances hợp nhau.

### 14.2. `ipBlock` không phải FQDN firewall

Không dùng danh sách `ipBlock` thủ công để giả định an toàn khi service public thường xuyên đổi IP. Khi cần hạn chế theo **tên miền/service identity**, cân nhắc egress proxy, private endpoint, cloud firewall, API gateway, service mesh hoặc CNI extension có semantics rõ về DNS cache, TTL và source identity.

Một public IP của CDN được cho phép ở L3/L4 không chứng minh ứng dụng đã gửi dữ liệu tới **đúng hostname và đúng TLS peer**. HTTPS client vẫn cần certificate/hostname verification và application authorization.

## 15. Các trường `ports`, named ports và protocol

### 15.1. Port là cổng của đích

Ví dụ Ingress:

~~~yaml
ports:
  - protocol: TCP
    port: 8080
~~~

Nghĩa là cho phép traffic tới **cổng 8080 của Pod đích** theo điều kiện của rule. Với Egress, `port` cũng biểu thị cổng ở **đích kết nối**, không phải ephemeral source port của client.

Nếu bỏ `protocol`, giá trị mặc định trong Kubernetes NetworkPolicy là **TCP**; tuy nhiên ghi tường minh trong tài liệu production giúp review dễ hơn, đặc biệt khi DNS dùng UDP.

### 15.2. Named ports

Pod có thể công bố một container port mang tên:

~~~yaml
# Đoạn trích Pod container spec, không phải manifest Pod hoàn chỉnh.
containers:
  - name: orders-api
    image: registry.example.test/orders/api:demo
    ports:
      - name: http-api
        containerPort: 8080
        protocol: TCP
~~~

Ingress NetworkPolicy có thể tham chiếu:

~~~yaml
ports:
  - protocol: TCP
    port: http-api
~~~

Named port được giải quyết dựa trên **port name của Pod đích** theo semantics NetworkPolicy và khả năng hỗ trợ của CNI. Không coi named port là tên Service port hay tự động lấy từ một HTTP route. Với Egress named ports, cần kiểm tra support và cách resolve Pod đích của plugin, đặc biệt khi kết nối không đi tới Pod thông thường.

### 15.3. Port ranges và SCTP

Một số cấu hình NetworkPolicy hỗ trợ `endPort` để chỉ định một khoảng port khi `port` là số nguyên, và SCTP theo điều kiện hạ tầng/runtime/CNI. Không dựa vào việc Kubernetes API chấp nhận field để kết luận tất cả plugin thực thi đúng.

Nếu ứng dụng thực sự dùng nhiều port động (như một số multimedia protocols), cần thiết kế riêng với service/policy engine hỗ trợ; không mở `all ports` theo thói quen.

## 16. Selectors và những lỗi logic dễ bị bỏ sót

### 16.1. Label matching không phải identity mật mã

Selectors dựa trên **labels trong Kubernetes API objects**. Nếu một developer có quyền tạo Pod với label `app=web` trong namespace edge, họ có thể khiến Pod mới **khớp rule cho phép web → orders-api**, trừ khi có admission/policy khác hạn chế quyền tạo và gắn label.

Vì vậy:

- Kiểm soát **RBAC create/update Pod/Deployment** và quyền thay label.
- Đặt label conventions, namespace ownership và admission policy khi cần.
- Với service nhạy cảm, kết hợp **mTLS/workload identity, IAM và application authorization**, không chỉ label.
- Không coi `app=trusted` là tương đương danh tính đã chứng minh của một service.

### 16.2. Empty selectors rất rộng

| Biểu thức | Phạm vi thông thường |
|---|---|
| `spec.podSelector: {}` | Mọi Pod của namespace chứa policy |
| Peer `podSelector: {}` không kèm namespace selector | Mọi Pod của **cùng namespace** |
| Peer `namespaceSelector: {}` đơn lẻ | Pod ở **mọi namespace** |
| Peer có `namespaceSelector: {}` và `podSelector: {}` | Mọi Pod ở mọi namespace |
| Peer `ipBlock: {cidr: 0.0.0.0/0}` | Toàn bộ IPv4 theo IP matching, chịu giới hạn CNI/NAT |
| `ingress: []` hoặc `egress: []` | Không có allow rules trong policy cho hướng đó |
| `ingress: - {}` hoặc `egress: - {}` | Một allow rule không giới hạn peer/port, **rất rộng** |

### 16.3. `matchExpressions` và label drift

Ngoài `matchLabels`, selector hỗ trợ các biểu thức như `In`, `NotIn`, `Exists`, `DoesNotExist` với semantics label selector tương ứng. Dùng chúng có thể hợp lý nhưng cần kiểm tra trường hợp Pod không có label hoặc label bị đổi bởi Helm/GitOps/rollout.

Vì các policy dựa trên **Pod labels tại thời điểm thực thi**, đổi label có thể làm Pod **vào hoặc ra khỏi tập được phép** mà không cần sửa trực tiếp NetworkPolicy. Theo dõi cả thay đổi selectors **và** thay đổi labels của workloads/namespaces.

## 17. NetworkPolicy, Service VIP, NAT và multi-path

### 17.1. Kết nối tới Service có đi qua policy giống Pod IP không?

Ứng dụng thường gọi `orders-api.orders.svc.cluster.local` rồi kết nối tới **ClusterIP của Service**, trong khi datapath chuyển tiếp tới một **Pod endpoint**.

~~~mermaid
flowchart LR
    WEB["Web Pod"] -->|"DNS query"| DNS["CoreDNS"]
    DNS -.->|"ClusterIP answer"| WEB
    WEB -->|"TCP đến Service VIP"| SVC["Service ClusterIP / kube-proxy/eBPF"]
    SVC -->|"Chọn Pod endpoint"| API["orders-api Pod"]
    NP["NetworkPolicy engine"] -.->|"Thực thi tùy datapath/CNI"| SVC
    NP -.->|"Thực thi tùy datapath/CNI"| API
~~~

NetworkPolicy định nghĩa selectors theo Pod, nhưng **thời điểm áp policy so với Service DNAT/SNAT** có thể khác theo plugin, chế độ kube-proxy/eBPF, ingress/egress gateway và topology. Vì thế:

1. Test kết nối qua **Service DNS/ClusterIP**, không chỉ gọi Pod IP trực tiếp.
2. Quan sát actual source/destination mà policy engine thấy khi NAT diễn ra.
3. Không mặc định `ipBlock` của public LoadBalancer IP sẽ được diễn giải như Pod IP.
4. Khi Service endpoint chuyển Pod, selectors phải theo workload labels chứ không hardcode Pod IP.

### 17.2. Ingress từ Internet qua LoadBalancer/Ingress Controller

~~~text
Internet client
   -> Cloud Load Balancer / edge WAF
   -> Kubernetes Ingress/Gateway controller
   -> Service VIP
   -> Application Pod
~~~

Pod ứng dụng có thể nhìn thấy source IP của **Ingress Controller Pod**, node IP hoặc client IP sau các lớp NAT theo cấu hình. Một NetworkPolicy Ingress chỉ cho `ipBlock` của địa chỉ công khai client có thể **không match** như mong đợi.

Để bảo vệ ứng dụng sau proxy:

- Chỉ cho phép traffic từ **Ingress Controller Pods/namespace được phê duyệt** tới app port khi topology cho phép.
- Bảo vệ public edge bằng **cloud firewall, WAF/rate limit, TLS và HTTP routing policy**.
- Kiểm tra forwarded headers, user identity và AuthN/AuthZ tại backend; không tin raw `X-Forwarded-For` như chứng cứ danh tính.
- Thử node-local, hostNetwork và service routing path của cluster.

### 17.3. Những kết nối hiện có khi đổi NetworkPolicy

NetworkPolicy thường được enforce bởi datapath có **connection tracking**. Khi cập nhật policy, hành vi đối với **TCP connection đã được thiết lập trước đó** có thể phụ thuộc plugin/implementation và trạng thái flow. Đừng lấy một socket giữ mở từ trước rồi kết luận rule mới không có tác dụng.

Trong kiểm thử:

- Tạo **kết nối mới** sau khi policy/controller đã hội tụ.
- Ghi thời điểm apply, policy version và flow evidence.
- Kiểm tra cả long-lived gRPC/WebSocket/database sessions theo yêu cầu nghiệp vụ.
- Khi thu hồi quyền khẩn cấp, cân nhắc cơ chế ngắt phiên/identity bên cạnh NetworkPolicy.

## 18. Phạm vi không được NetworkPolicy chuẩn bảo đảm

| Thành phần / luồng | Hạn chế cần nhớ | Biện pháp bổ sung |
|---|---|---|
| `hostNetwork` Pod | Có thể không chịu cùng policy semantics như Pod networking thông thường | Host firewall, CNI host policies nếu hỗ trợ, Pod Security Admission |
| Host/node IP, kubelet, runtime socket | NetworkPolicy không phải firewall tổng quát của node; một số node traffic được xử lý đặc biệt | Host ACL, kubelet AuthN/AuthZ, Unix socket permissions |
| Kubernetes API server | Private/public endpoint có thể đi đường control-plane riêng | Cluster API access policy, IAM/RBAC, TLS, audit |
| etcd | Không tự bị bảo vệ bởi Pod policy khi nằm trên host/control plane | Network segmentation và mTLS/client cert |
| DNS via NodeLocal DNSCache | Resolver có thể là node-local endpoint, không phải CoreDNS Pod trực tiếp | DNS topology-specific controls/tests |
| Secondary CNI interfaces | Không phải plugin nào cũng enforce trên mọi interface | Multus/CNI-specific network policy |
| Traffic với `ipBlock` qua NAT | IP tại enforcement point có thể khác IP ban đầu | Route/NAT evidence, cloud firewall |
| IPv6 | Policy IPv4 không tự chặn toàn bộ IPv6 | Dual-stack policy và validation |
| HTTP path, header, JWT, tenant | NetworkPolicy chỉ ở lớp mạng/transport | WAF, API gateway, mTLS, application AuthZ |
| Egress đến SaaS bằng FQDN | API chuẩn không match domain names | Egress proxy/gateway, service-specific policy |

**Không có một policy tên `default-deny-all` bảo đảm mọi kết nối trên host/cluster bị chặn.** Tên tài nguyên do người dùng đặt; phạm vi thật phụ thuộc selectors, `policyTypes`, các policy khác và CNI.

### 18.1. NetworkPolicy và service mesh

Service mesh có thể mã hóa mTLS và ủy quyền theo workload identity, đồng thời chuyển traffic qua sidecar hoặc dataplane node. NetworkPolicy có thể dùng để **giới hạn đường mạng giữa các workload/sidecar/ingress gateways** nhưng cần:

- Kiểm tra port interception, health probes, injected proxy labels, DNS và egress gateway paths.
- Không mặc định Pod-to-Pod route trực tiếp giống đường thực khi mesh có sidecar hoặc ambient dataplane.
- Dùng service identity/AuthZ ở mesh hoặc ứng dụng để tránh tenant spoofing, không chỉ labels.
- Test bypass đường sidecar/proxy hoặc direct Pod IP khi topology cho phép.

Mesh mTLS **không tự thay thế NetworkPolicy** cho những nguồn chưa tham gia mesh; NetworkPolicy **không thay mTLS** khi cần xác thực peer ở L7.

## 19. Threat modeling: 22 rủi ro thường gặp

| ID | Rủi ro | Kịch bản | Kiểm soát / bằng chứng |
|---|---|---|---|
| NP01 | **CNI không enforce policy** | API tạo NetworkPolicy thành công nhưng traffic không đổi | Kiểm tra CNI capabilities và negative tests |
| NP02 | **Nhầm Ingress resource với policy ingress** | Có HTTP Ingress nên tưởng Pod đã bị phân đoạn | NetworkPolicy riêng và data path review |
| NP03 | **Default-deny chỉ có Ingress** | Egress ra DB/Internet vẫn mở | Khai báo `policyTypes` tường minh và egress tests |
| NP04 | **Default-deny làm tê liệt DNS** | Pod không resolve Service sau rollout | Allow DNS đúng resolver và protocol |
| NP05 | **Rule `- {}` mở toàn bộ** | Thêm rule rỗng để sửa lỗi kết nối | Diff/review tìm empty rules, reject broad exception |
| NP06 | **Hai peer selectors bị tách thành OR** | Mọi Pod namespace edge vào được API | AND selectors trong một list item |
| NP07 | **Policy cộng dồn mở lại traffic** | Policy khác cho `0.0.0.0/0` / all port | Inventory toàn bộ selecting policies |
| NP08 | **Không cấp cả egress và ingress** | Source egress allow nhưng dest ingress deny | Two-sided policy matrix |
| NP09 | **Label được sửa để khớp trusted role** | Tenant tạo Pod `app=web` | RBAC/admission label ownership, workload identity |
| NP10 | **IPBlock sai do NAT** | Service IP và Pod endpoint match khác mong đợi | Test Pod IP, ClusterIP và packet path |
| NP11 | **Cổng/protocol nhầm** | Chỉ cho TCP/53, DNS UDP fail | UDP/TCP DNS, port/protocol inventory |
| NP12 | **NodeLocal DNS khác CoreDNS path** | Policy DNS Pod selector không đủ | NodeLocal DNS configuration review |
| NP13 | **HostNetwork bypass/coverage gap** | Pod/agent dùng network namespace host | Host firewall, PSA, CNI-specific enforcement |
| NP14 | **IPv6 không được kiểm soát** | IPv4 deny nhưng còn IPv6 route hợp lệ | Dual-stack negative tests |
| NP15 | **Đường từ LoadBalancer có source IP khác** | IPBlock client không match vì SNAT | Ingress controller policy, cloud LB review |
| NP16 | **Rule egress TCP/443 quá rộng** | Workload gửi dữ liệu tới host ngoài ý định | Egress proxy/identity, allowlist chuẩn và audit |
| NP17 | **Tenant API AuthZ thiếu** | Network allowed dẫn đến dữ liệu tenant khác | App/service AuthN/AuthZ, DB roles |
| NP18 | **Rule không kiểm soát Pod trực tiếp** | Deployment đổi labels khiến Pod không được chọn | Selector/label drift monitoring |
| NP19 | **NetworkPolicy update chưa hội tụ** | Existing sessions tiếp tục hoặc flow khác | New-connection tests, convergence metrics |
| NP20 | **System namespace bị default-deny** | CNI, DNS hoặc metrics ngừng hoạt động | Namespace ownership, canary, rollback |
| NP21 | **Network flow logs không đầy đủ** | Không biết bị deny ở source hay destination | CNI flow verdict + app/DNS/TLS evidence |
| NP22 | **Cross-namespace selector vượt phạm vi** | `namespaceSelector: {}` chọn toàn cluster | Policy review, scope labels, namespace permissions |

### 19.1. Không đánh đồng một kết nối fail với policy đúng

Nếu test từ web tới DB fail, nguyên nhân có thể là DB chưa khởi động, Service selector sai, TLS error hoặc NetworkPolicy đã chặn. Một negative test hợp lệ cần **điểm đối chứng**: DB thực sự khỏe, một nguồn được cấp phép có thể kết nối, và telemetry cho thấy **đúng control** đã từ chối nguồn không được phép.

### 19.2. Hệ quả blast radius theo luồng

~~~mermaid
flowchart TD
    COMP["Frontend bị chiếm quyền"] --> CHOICE{"NetworkPolicy và identity controls"}
    CHOICE -->|"Ingress/Egress quá rộng"| WIDE["Có thể tiếp cận API/DB/dịch vụ khác trên mạng"]
    CHOICE -->|"Phân đoạn đúng"| LIMITED["Chỉ có đường web → API:8080 được thiết kế"]
    LIMITED --> AUTH["API tiếp tục AuthN/AuthZ và giới hạn tenant"]
    WIDE --> IR["Tăng phạm vi điều tra/ứng cứu"]
    AUTH --> IR
~~~

NetworkPolicy có thể giảm **khả năng tiếp cận đường mạng**, nhưng nếu frontend được phép gọi API thì attacker vẫn có thể lạm dụng API trong **phạm vi quyền ứng dụng đã cấp**. Network segmentation và authorization phải phối hợp.

## 20. Quan sát chỉ đọc trước khi áp policy

Những lệnh sau chỉ dùng trong **cluster được phép quản trị**. Chúng chủ yếu đọc cấu hình và trạng thái; không thay đổi NetworkPolicy hoặc tạo Pod mới. Khi RBAC không cho đọc, đó có thể là chính sách đang hoạt động đúng.

### 20.1. Xác định cluster/context

~~~bash
# Xác nhận tránh nhầm production và lab cluster.
kubectl config current-context

# Đọc network policies và namespaces, không chỉnh sửa.
kubectl get networkpolicies -A
kubectl get namespaces --show-labels

# Đọc labels của Pod ở các namespace minh họa.
kubectl get pods -n edge --show-labels
kubectl get pods -n orders --show-labels

# Đối chiếu DNS Pods, Services và labels thực.
kubectl get pods -n kube-system --show-labels
kubectl get services -n kube-system
~~~

Không trích toàn bộ kubeconfig hoặc Secret để lấy quyền kiểm tra. Nếu không có quyền `get networkpolicies`, cần nhờ cluster owner cung cấp kết quả review theo quy trình, không tự nâng quyền.

### 20.2. Đọc hiệu lực policy theo namespace

~~~bash
# Đọc các policy đã được API server lưu, chỉ trong scope được phép.
kubectl get networkpolicy -n edge -o yaml
kubectl get networkpolicy -n orders -o yaml

# Mô tả policy cụ thể (nếu tồn tại).
kubectl describe networkpolicy -n orders api-ingress-from-edge-web

# Xem workload labels/ports để so selectors.
kubectl get deployment -n orders --show-labels
kubectl get services -n orders -o wide
~~~

**Đừng kết luận CNI đã thực thi chỉ từ nội dung YAML hoặc `kubectl describe`**. Cần test kết nối từ nguồn được chọn, đối chiếu CNI flow logs và health của Pod/service đích.

### 20.3. Kiểm tra quyền quản trị

~~~bash
# Chỉ hỏi authorization, không tạo/sửa tài nguyên.
kubectl auth can-i get networkpolicies -n orders
kubectl auth can-i create networkpolicies -n orders
kubectl auth can-i patch deployments -n edge
kubectl auth can-i update namespaces
~~~

Quyền `create`/`patch` có thể quyết định ai được thay đổi labels hoặc policies, từ đó mở rộng network access. Không chỉ review người có quyền sửa NetworkPolicy mà quên người có quyền **tạo/sửa Pod mang label được tin**.

## 21. Kiểm thử connectivity trong lab có kiểm soát

**Khác với những lệnh chỉ đọc ở mục 20**, kết nối thử tạo traffic tới ứng dụng. Chỉ làm trên Pod/Service **thuộc môi trường lab hoặc được cấp phép**, không tự cài công cụ vào container production, không tạo debug Pod đặc quyền hay bật endpoint ngoài chính sách.

### 21.1. Quy trình test theo từng lớp

1. Ghi lại **source namespace/Pod labels**, destination, policy version và thời gian.
2. Kiểm tra DNS resolve và IP/port của Service đích.
3. Mở **một kết nối mới** từ source được phép tới destination/port được phép.
4. Thử từ source không được phép với cùng destination/port; cần có kết quả reject/timeout theo datapath và flow verdict.
5. Kiểm tra cổng không được phép từ source được phép; ví dụ web tới API/5432 phải deny.
6. Đối chiếu cùng luồng qua **Service DNS**, ClusterIP và Pod IP khi phù hợp để phát hiện NAT/path gap.
7. Kiểm tra TLS/HTTP/API authorization sau khi kết nối mạng được cho phép.
8. Lặp lại khi đổi Pod IP/rollout hoặc khi có dual-stack/secondary CNI.

### 21.2. Ví dụ lệnh connectivity từ công cụ lab có sẵn

Nếu lab đã có diagnostic utility bên trong `web` Pod và cluster owner cho phép:

~~~bash
# Kết nối kiểm thử mang tính quan sát, không ghi dữ liệu API.
# Chỉ chạy nếu Pod và công cụ tương ứng đã có trong lab.
kubectl exec -n edge deploy/web -- \
  sh -c 'nc -z -w 3 orders-api.orders.svc.cluster.local 8080'

# Một kết nối trực tiếp tới DB từ web phải bị chặn theo policy mục tiêu.
kubectl exec -n edge deploy/web -- \
  sh -c 'nc -z -w 3 orders-db.orders.svc.cluster.local 5432'
~~~

`nc` có thể không có trong image, `kubectl exec` có thể bị RBAC cấm, và việc kết nối thử **không chứng minh lý do kết nối được/chặn**. Đừng cấp `pods/exec` hoặc thêm debug shell vào production image chỉ vì ví dụ. Có thể dùng approved test workload, CNI connectivity diagnostics hoặc công cụ quan sát tương đương của nền tảng.

**Không dùng lỗi HTTP 401/403 làm bằng chứng NetworkPolicy deny.** Một response HTTP chứng minh traffic đã vượt ít nhất một phần đường TCP/TLS và đã đến lớp ứng dụng/gateway; deny ở API có thể là **AuthN/AuthZ**, không phải network isolation.

## 22. Ma trận kiểm thử positive và negative

Giả sử mẫu ba tầng ở các mục 10–13 đã được triển khai **và các Pod/Service có thật**:

| ID | Nguồn → đích | Kỳ vọng | Bằng chứng |
|---|---|---|---|
| P01 | `edge/web → orders/orders-api:8080/TCP` | ALLOW qua cả egress và ingress | Flow verdict, request/API result |
| P02 | `orders/orders-api → orders/orders-db:5432/TCP` | ALLOW theo network policy | Flow + DB listener/handshake |
| P03 | `edge/web → DNS resolver:53/UDP` | ALLOW đúng resolver | DNS answer, CNI flow |
| P04 | `edge/web → DNS resolver:53/TCP` khi cần | ALLOW đúng resolver | DNS TCP test, flow |
| N01 | `edge/web → orders/orders-db:5432` | DENY theo segmentation | CNI denial + DB healthy control |
| N02 | Pod `app=unknown` ở edge → API/8080 | DENY nếu không khớp source selector | Pod labels và flow verdict |
| N03 | Pod web ở namespace khác → API/8080 | DENY trừ khi có policy khác | Namespace selector + flow |
| N04 | `edge/web → orders-api:9090/TCP` | DENY nếu không allow cổng này | Port-specific test |
| N05 | `orders/orders-api → Internet:443` | DENY trừ khi có egress được duyệt | Egress logs, source evidence |
| N06 | Pod guest namespace → orders-db/5432 | DENY ingress DB theo policy | DB control + flow verdict |
| P05 | orders-api được phép tới DB nhưng sai DB credentials | Network có thể ALLOW, **DB auth DENY** | DB audit và connectivity |
| N07 | Rule `from` tách hai selectors thành OR trong lab | Review/test chứng minh sẽ mở rộng nguồn | Policy diff, cross-namespace tests |
| N08 | Thêm policy mới allow rộng trong lab | Nhận diện union làm tăng quyền | Enumerate selecting policies, flow |
| N09 | Workload đổi label không khớp selectors | Không còn hưởng allowance dự định | Label change and rule-selection evidence |
| P06 | Service ClusterIP → Pod endpoints | Path theo policy và routing đúng | Service/endpoint/flow observation |
| N10 | IPv6 path khi dual-stack | Không có luồng bypass ngoài chính sách | IPv6-specific route/flow test |
| N11 | NodeLocal DNSCache path | DNS được phép **chỉ** theo mô hình thực | DNS topology verification |
| N12 | HostNetwork workload tới node control services | Được bảo vệ bằng host-level controls | Host firewall/identity evidence |
| P07 | CNI datapath hội tụ sau rollout | Kết nối mới theo rule version mới | Change time + new-connection probes |
| N13 | TCP connection có trước khi sửa policy | Không suy kết luận từ session cũ | Separate old/new connections |
| N14 | Egress `0.0.0.0/0` vô tình cho rộng | Rule được phát hiện và sửa qua review | Manifest diff và egress audit |
| N15 | User không có quyền sửa policy/labels | Không thay được NetworkPolicy hoặc trusted Pod label | RBAC/admission result |
| P08 | Approved application traffic sau rollback lab | Phục hồi đúng SLO và allowance mong muốn | Config version/metrics |
| N16 | Egress DNS tới resolver ngoài allowlist | DENY nếu policy và network hỗ trợ | Resolver identity/flow verdict |
| N17 | HTTP API tenant A gọi tenant B qua luồng mạng allowed | Bị **ứng dụng** từ chối | API AuthZ/tenant logs |

### 22.1. Cách định nghĩa kết quả

- **ALLOW của NetworkPolicy**: packet flow phù hợp với policy; vẫn có thể bị firewall, TLS, service hoặc ứng dụng từ chối.
- **DENY của NetworkPolicy**: có bằng chứng datapath/policy engine chặn đúng source/destination/protocol theo phiên bản policy đang active.
- **Negative test không có điểm đối chứng** là bằng chứng yếu; phải chứng minh đích healthy và có nguồn hợp lệ thành công.
- **Một Pod trả lời được DNS** không chứng minh mọi egress đều được kiểm soát.
- **Một policy không có rules** không chứng minh mọi traffic denied nếu Pod không được chọn hoặc có policy khác mở luồng.

## 23. Troubleshooting ingress/egress theo thứ tự

| Triệu chứng | Giả thuyết | Kiểm chứng |
|---|---|---|
| Tất cả Pod trong namespace mất DNS | Default-deny Egress không allow resolver thật | DNS topology, UDP/TCP 53, resolver/flow logs |
| Web không tới API qua Service nhưng tới Pod IP được | Service VIP/DNAT, CNI datapath hoặc kube-proxy rule | Service/EndpointSlice, Pod-IP path, flow observation |
| Web tới API bị chặn dù có ingress allow | Egress web chưa allow hoặc source labels/namespace sai | Both-sided policy + selectors |
| Database nhận kết nối từ Pod lạ | Policy khác đang allow, Pod label spoof hoặc host path | Selecting policies, labels, RBAC, host firewall |
| API/8080 mở cho mọi namespace | `namespaceSelector` riêng khiến OR, hoặc `{ }` selector | YAML list nesting và match scope |
| Rule match nguồn đúng nhưng port fail | Named port/protocol/port mismatch | Pod container ports và CNI support |
| UDP DNS fail, TCP DNS OK | Thiếu UDP/53 hoặc resolver path khác | UDP/TCP-specific logs |
| Policy tồn tại nhưng không thay traffic | CNI không hỗ trợ hoặc policy engine chưa hội tụ | CNI config/metrics, new flow tests |
| Chỉ IPv6 bypass | IPv6 policy coverage hoặc datapath khác | Dual-stack DNS/route/flow |
| Pod restart thì kết nối được | Connection tracking/cached route/policy convergence | Old/new sessions, endpoint state |
| Từ LoadBalancer bị chặn bất ngờ | Source IP SNAT/Ingress Controller identity khác dự kiến | LB/Ingress logs, Pod source as observed |
| Service mesh thêm sidecar rồi hỏng | Port redirection/sidecar labels/egress gateway path | Mesh proxy, CNI flows, ports |
| Truy cập bị trả HTTP 403 | WAF/API/RBAC/tenant AuthZ, không nhất thiết NetworkPolicy | Response source/trace, auth logs |
| Node/etcd vẫn truy cập được sau default-deny | Host/network boundary ngoài phạm vi policy | Host firewall, control-plane reachability |

### 23.1. Sơ đồ chẩn đoán

~~~mermaid
flowchart TD
    A["Không kết nối được service"] --> B{"DNS trả đúng địa chỉ?"}
    B -->|"Không"| DNS["DNS resolver path, egress UDP/TCP 53, Service DNS"]
    B -->|"Có"| C{"Nguồn có bị egress-isolated?"}
    C -->|"Có"| E["Đọc tất cả egress policies chọn source Pod"]
    C -->|"Không"| D{"Đích có bị ingress-isolated?"}
    E --> D
    D -->|"Có"| I["Đọc tất cả ingress policies chọn destination Pod"]
    D -->|"Không"| N["Kiểm tra route, Service, CNI, firewall"]
    I --> N
    N --> T{"TCP/TLS đến được đích?"}
    T -->|"Không"| FLOW["CNI flow verdict, NAT, node/host path, health"]
    T -->|"Có"| AUTH["Ứng dụng, IAM/AuthZ, certificate và data service"]
    DNS --> FIX["Sửa nhỏ nhất có thể, kiểm thử lại"]
    FLOW --> FIX
    AUTH --> FIX
~~~

Tránh “chữa” bằng cách thêm một rule `egress: - {}` hoặc `ingress: - {}`. Những rule này có thể vô hiệu hóa mục tiêu phân đoạn, dù ứng dụng hết lỗi.

## 24. Giám sát và phát hiện policy drift

### 24.1. Tập dữ liệu nên theo dõi

| Nguồn | Dữ liệu | Lý do |
|---|---|---|
| Kubernetes audit | Create/update/delete NetworkPolicy, Pods, namespaces, labels | Theo dõi ai thay đổi control plane |
| CNI flow observability | Source/destination identities, port, protocol, policy verdict | Xác minh enforcement và unexpected flows |
| Kubernetes resources | Pod labels, Namespace labels, Services, EndpointSlices | Giải thích selector và route selection |
| Application logs | AuthN/AuthZ decision, request ID, status/error | Phân biệt policy deny với ứng dụng deny |
| DNS metrics/logs | Resolver, qname, response, failure rate | Chẩn đoán egress DNS bị chặn |
| Cloud/host firewall | Network allow/deny theo VPC/VNet/host | Nhận diện những lớp ngoài NetworkPolicy |
| CI/GitOps/IaC | Policy version, PR approver, rollout state | Drift và rollback |
| Service mesh/WAF | TLS peer, mTLS identity, HTTP policy/trace | L7 security độc lập với NetworkPolicy |

Flow data có thể chứa tên workload, IP, namespace và ứng dụng nội bộ. Cần **least-privilege access, masking/redaction, retention và privacy review**. Không thu raw tokens, HTTP bodies hoặc Secret values chỉ để quan sát một TCP/8080 flow.

### 24.2. Những cảnh báo có giá trị

- Xuất hiện `namespaceSelector: {}`, `podSelector: {}` ở peer hoặc `ingress/egress: - {}` trong namespace nhạy cảm mà không có exemption.
- Policy allow `0.0.0.0/0` hoặc `::/0` mới được thêm vào workload đang default-deny egress.
- Label Pod/namespace thay đổi khiến workload bắt đầu khớp rule được coi là trusted.
- Một policy vừa bị xóa hoặc đổi `policyTypes` ngoài change ticket.
- Số flow denies tăng sau rollout, hoặc flow allows tới network không có trong dependency inventory.
- DNS failures, probe failures và SLO ứng dụng thay đổi trùng mốc policy update.
- CNI health không tốt/agent restart trên node khiến enforcement có dấu hiệu bất thường.

**Không tự động quy mọi deny flow là sự cố:** default-deny thường tạo những kết nối bị chặn do discovery, telemetry hoặc process thử đích không được phép. Cần đối chiếu ownership, baseline và kết quả nghiệp vụ.

## 25. Quy trình triển khai NetworkPolicy an toàn

### Bước 1 — Kiểm kê luồng trước khi chặn

Tạo data flow diagram cho frontend, API, database, DNS, metrics, identity, cloud APIs, external SaaS, ingress controller và service mesh. Ghi **source labels/namespace, destination labels/namespace/IP, port, protocol, direction, owner**.

### Bước 2 — Kiểm tra CNI và các trường hợp ngoại lệ

Xác nhận CNI enforce ingress/egress, IPv6, named ports, traffic tới NodeLocal DNSCache, Service/LoadBalancer NAT, hostNetwork và secondary CNI. Nếu yêu cầu an ninh vượt khả năng NetworkPolicy chuẩn, chọn lớp bảo vệ bổ sung thay vì khai báo policy không enforce được.

### Bước 3 — Tách namespace/workload trust boundaries

Phân loại tenant, ứng dụng, monitoring, management, CI và hệ thống. Kiểm soát **ai được tạo Pod/sửa labels** để không cho người dùng tự mang nhãn của workload đáng tin. Thiết lập RBAC/admission song song với NetworkPolicy.

### Bước 4 — Thiết kế default-deny và allow rules

Viết baseline cho từng namespace muốn cô lập. Tách Ingress và Egress rõ ràng; dùng labels ổn định, AND selectors đúng trong một peer, ports/protocols cụ thể và policy DNS phù hợp.

### Bước 5 — Kiểm thử trong lab hoặc canary

Đánh giá positive/negative tests và luồng thực, bao gồm cả **Service VIP** và **Pod IP** khi cần, dual-stack, DNS, ingress controller, mTLS và DB AuthZ. Có điểm đối chứng cho mỗi deny.

### Bước 6 — Rollout theo nhóm, đo kết quả

Áp namespace ít rủi ro trước; sau đó mở rộng theo workload group. Theo dõi CNI policy synchronization, flows, DNS errors, application p95 latency, HTTP 5xx và critical background jobs.

### Bước 7 — Khôi phục có kiểm soát

Chuẩn bị manifest version trước thay đổi, owner/approval và đường rollback. Khi cần khôi phục availability, **không mặc định xóa toàn bộ default-deny** rồi quên khôi phục; ưu tiên sửa một allow rule nhỏ nhất hoặc dùng rollback đã được review, kèm monitoring blast radius.

### Bước 8 — Rà soát định kỳ

Khi thêm service, namespace, cluster CNI upgrade, cloud ingress, mesh, DNS cache, IPv6, API backend hoặc đổi labels, đánh giá lại policy. Xóa các allowance tạm thời hết hạn và so sánh IaC với policy đang chạy.

## 26. Bài tập tình huống: policy có mà frontend vẫn vào được database

**Bối cảnh giả định:** môi trường lab có ba Pod theo mục 10. Đội platform đã áp `default-deny-both` vào namespace `orders`. Sau đó tạo một policy Ingress cho database:

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: db-ingress-review
  namespace: orders
spec:
  podSelector:
    matchLabels:
      app: orders-db
  policyTypes: [Ingress]
  ingress:
    - from:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: edge
        - podSelector:
            matchLabels:
              app: orders-api
      ports:
        - protocol: TCP
          port: 5432
~~~

Một engineer tin rằng rule trên có nghĩa “chỉ `orders-api` thuộc namespace edge mới gọi được database”. Nhưng `orders-api` thực sự thuộc namespace orders, còn `edge` có nhiều Pod frontend và test workers.

### 26.1. Câu hỏi

1. Hai phần tử `from` trong ví dụ là **AND hay OR**?
2. Theo cấu trúc đó, **những nguồn nào** có thể khớp rule đối với DB?
3. Nếu frontend ở edge gọi DB thành công, có thể xác nhận ngay rằng `default-deny-both` không hoạt động không?
4. Hãy viết lại một ingress policy chỉ cho **Pod `app=orders-api` trong namespace orders** vào DB/5432.
5. Nếu frontend ở edge đồng thời bị **egress-isolated** không có allowance tới DB, kết nối web → DB có được không?
6. Nếu một policy khác đã cho phép mọi namespace vào DB/5432, sửa policy `db-ingress-review` có đủ chặn nguồn lạ không?
7. Nếu Pod DB trả HTTP/TCP connection success nhưng DB login không hợp lệ, control nào phải từ chối?
8. Hãy đề xuất ít nhất ba negative tests và hai positive tests có điểm đối chứng.

### 26.2. Gợi ý lời giải

- Hai peers trong `from` được **OR**. Rule cho phép **mọi Pod trong namespace edge**, hoặc Pod `app=orders-api` **cùng namespace orders**, tới TCP/5432.
- Default-deny chỉ khiến những Pod đã được chọn **bị cô lập**; **allow ingress của `db-ingress-review` đã mở đúng cổng** cho những nguồn khớp. Vì vậy kết nối từ edge có thể là **đúng semantics nhưng sai yêu cầu an ninh**, không phải CNI bị lỗi.
- Để chỉ allow Orders API trong cùng namespace orders, dùng **một peer `podSelector.matchLabels.app: orders-api`** và không cần `namespaceSelector`.
- Nếu frontend egress-isolated nhưng không có egress allow tới DB, **phía nguồn chặn**; cả hai phía phải phù hợp khi đều isolated.
- Nếu policy khác còn allow rộng, allowances **cộng dồn**, nên phải thu hẹp cả policy còn lại.
- Database vẫn cần **xác thực, quyền schema/table, TLS/identity** và audit độc lập với network allow.

Ví dụ ingress policy sửa đúng:

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: db-ingress-only-from-orders-api
  namespace: orders
spec:
  podSelector:
    matchLabels:
      app: orders-db
  policyTypes: [Ingress]
  ingress:
    - from:
        - podSelector:
            matchLabels:
              app: orders-api
      ports:
        - protocol: TCP
          port: 5432
~~~

**Lưu ý:** ví dụ mới **chỉ thay thế logic của policy gây vấn đề sau khi có change approval**; nếu `db-ingress-review` cũ vẫn tồn tại, policy cũ tiếp tục cộng allowance. Không triển khai “thêm policy mới” rồi kỳ vọng nó ghi đè policy cũ.

## 27. Checklist Ingress rule và Egress rule của NetworkPolicy

- [ ] Phân biệt NetworkPolicy Ingress/Egress với HTTP Ingress/Gateway API routing.
- [ ] CNI/network policy engine thực sự hỗ trợ và enforce policy theo datapath triển khai.
- [ ] Xác định đúng namespace và `spec.podSelector` chọn những Pod nào.
- [ ] Hiểu `Ingress`/`Egress` mô tả hướng tương đối với Pod được chọn.
- [ ] Khai báo `policyTypes` tường minh, không suy từ tên tài nguyên.
- [ ] Biết `ingress: []` và `egress: []` không có allow rule; `- {}` lại rất rộng.
- [ ] Có baseline default-deny theo từng namespace cần cô lập, không áp mù lên system namespaces.
- [ ] Hiểu các policy **cộng dồn**, không có explicit deny/priority chuẩn để ghi đè allowance.
- [ ] Mỗi luồng Pod A → Pod B được đánh giá ở cả **egress A** và **ingress B** khi hai phía isolated.
- [ ] Kết nối phản hồi, TCP sessions có trước và CNI connection tracking được xem xét đúng.
- [ ] `namespaceSelector` + `podSelector` trong **cùng một peer** khi cần AND.
- [ ] Không tách hai selectors thành hai phần tử `from/to` gây OR ngoài ý định.
- [ ] Không dùng `namespaceSelector: {}`/`ipBlock: 0.0.0.0/0` nếu không có chủ đích và phê duyệt.
- [ ] Labels dùng để cấp network reachability được bảo vệ bởi RBAC/admission và ownership.
- [ ] Ports/protocols được xác định đúng; DNS UDP/TCP 53 và named ports được kiểm tra.
- [ ] Resolver thực, CoreDNS Service/Pods, NodeLocal DNSCache và private DNS paths được inventory.
- [ ] Service ClusterIP, DNS resolution, NAT/SNAT, Ingress Controller source identity được test.
- [ ] Egress tới cloud/SaaS không chỉ dựa CIDR động nếu không có lifecycle quản trị.
- [ ] IPv4/IPv6, secondary interfaces, hostNetwork và node traffic có lớp bảo vệ bổ sung phù hợp.
- [ ] Không coi NetworkPolicy là điều kiện xác thực TLS, OAuth, mTLS hoặc tenant/resource authorization.
- [ ] Có positive/negative tests với Pod/Service khỏe mạnh và telemetry chứng minh control deny.
- [ ] Có log theo nguồn/đích, namespace, Pod labels, flow verdict, policy version và ứng dụng.
- [ ] Không thu Secret/token/body nhạy cảm vào logs để chứng minh một TCP flow.
- [ ] Có canary rollout, phương án rollback, change approval và owner của các allowance.
- [ ] Rà soát lại khi CNI, DNS, service mesh, workload labels, cloud route hoặc ingress topology thay đổi.

**Ghi nhớ:** **NetworkPolicy Ingress quyết định traffic nào được vào Pod đã chọn; Egress quyết định traffic nào được Pod đó gửi đi**. Quyền truyền thông được hình thành bằng **các allow rules cộng dồn** và có thể phải thỏa **ở cả hai phía của kết nối**. Một thiết kế an toàn kết hợp **default-deny theo đúng scope, selectors chính xác, DNS và Service datapath đã kiểm chứng, CNI enforcement thực tế, giám sát, cùng xác thực/phân quyền ứng dụng độc lập**.
