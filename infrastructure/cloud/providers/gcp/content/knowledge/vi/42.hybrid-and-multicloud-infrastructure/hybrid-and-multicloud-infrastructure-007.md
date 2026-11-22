# Cloud Service Mesh trong kiến trúc nhiều môi trường

Một doanh nghiệp có hệ thống microservices trên hai cụm Google Kubernetes Engine (GKE), một số dịch vụ cũ chạy Compute Engine VM và một trung tâm dữ liệu riêng. Nhóm muốn các dịch vụ gọi nhau an toàn, định tuyến được khi một region gặp sự cố, quan sát độ trễ giữa môi trường và triển khai dần phiên bản mới mà không phải viết lại từng ứng dụng. Kết nối VPC, Cloud VPN hay Cloud Interconnect chỉ tạo đường mạng: chúng chưa tự cung cấp nhận dạng workload, chính sách truy cập giữa các dịch vụ hoặc điều khiển traffic ở tầng ứng dụng.

**Cloud Service Mesh** là giải pháp service mesh của Google Cloud, dựa trên các công nghệ như Istio và Envoy hoặc các API định tuyến dịch vụ của Google Cloud tùy nền tảng. Service mesh đặt một lớp điều khiển lưu lượng và chính sách giữa các workload: service discovery, cân bằng tải, mTLS, xác thực danh tính, authorization, traffic splitting và telemetry. Nó giúp thống nhất cách vận hành nhiều dịch vụ, nhưng **không thay thế kết nối mạng bên dưới** và **không bảo đảm mọi loại cluster, VM hay cloud có thể nhập vào cùng một mesh managed**.

Trong module **CLOUD_PROVIDERS_GCP**, kiến trúc lai và đa đám mây phải phối hợp project, IAM, VPC, GKE, Compute Engine, cloud networking, kiểm soát truy cập và khả năng quan sát. Bài này đặt Cloud Service Mesh vào bức tranh đó, so sánh lựa chọn control plane theo môi trường, mô tả đường kết nối east-west, đưa ra ví dụ cấu hình Istio và quy trình triển khai có kiểm soát.

Sau bài học, bạn có thể:

- Phân biệt service mesh, API gateway, load balancer, VPC peering và VPN/Interconnect.
- Hiểu control plane, data plane, sidecar Envoy, proxyless gRPC, service identity và trust domain.
- Chọn managed Cloud Service Mesh cho GKE hoặc Compute Engine, và nhận diện giới hạn của Kubernetes bên ngoài Google Cloud.
- Thiết kế multi-cluster cùng fleet, certificate authority, DNS, pod connectivity và east-west gateway.
- Áp mTLS STRICT, AuthorizationPolicy và định tuyến canary bằng Istio APIs ở nền tảng hỗ trợ.
- Lập kế hoạch chuyển từ mesh một cluster sang nhiều cluster hoặc nhiều môi trường.
- Đặt SLI/SLO cho liên lạc giữa dịch vụ, kiểm soát tác động của proxy và chi phí vận hành.
- Troubleshoot lỗi discovery, routing, certificate, policy và telemetry.

## 1. Khi nào một hệ thống cần service mesh?

Giả sử dịch vụ checkout gọi payment, inventory và notification. Khi có thêm cluster ở region khác hoặc on-premises, phát sinh các câu hỏi:

1. Checkout nhận diện payment bằng hostname nào?
2. Endpoint nào đang khỏe và nên nhận request?
3. Có cho checkout gọi payment nhưng chặn service khác không?
4. Làm sao mã hóa traffic service-to-service mà không mỗi nhóm tự quản lý TLS certificate?
5. Làm sao gửi 5% traffic tới phiên bản payment mới và rollback nhanh?
6. Làm sao biết lỗi nằm ở client, proxy, gateway hay backend bên kia mạng WAN?

Service mesh giúp giải quyết các vấn đề ở lớp giao tiếp giữa workloads. Nhưng nếu chỉ có hai service đơn giản, traffic nhỏ và không cần chính sách nhất quán, chi phí vận hành mesh có thể lớn hơn lợi ích. Nên đánh giá nhu cầu trước khi cài đặt.

### Mesh không thay thế thành phần nào?

| Thành phần | Vấn đề chính giải quyết | Quan hệ với service mesh |
|---|---|---|
| VPC, subnet, route, firewall | Kết nối IP và kiểm soát mạng | Mesh cần đường mạng hợp lệ trước |
| Cloud VPN/Cloud Interconnect | Kết nối on-premises và Google Cloud | Mang traffic giữa mạng; không tự tạo identity workload |
| Cloud Load Balancing/GKE Gateway | Điểm vào north-south, TLS/public/private entry | Có thể đứng trước mesh hoặc gateway của mesh |
| API gateway | API policy, xác thực consumer, quota và developer experience | Bổ sung cho chính sách east-west, không hoàn toàn tương đương |
| Service mesh | Chính sách và điều phối giao tiếp giữa workloads | Có thể dùng ingress/egress gateway, mTLS, routing, telemetry |
| IAM | Quyền truy cập Google Cloud resource/control plane | Không tự thay thế AuthorizationPolicy cho từng request trong mesh |
| Kubernetes NetworkPolicy | Kiểm soát traffic ở lớp mạng của pod | Bổ sung defense in depth cho service identity policy |

Vì vậy, thiết kế tốt thường dùng kết hợp: Global/Regional Load Balancer cho traffic ngoài vào, Cloud Service Mesh cho giao tiếp nội bộ, IAM cho Google APIs và VPC firewall/NetworkPolicy để khóa đường mạng không cần thiết.

## 2. Các thành phần của Cloud Service Mesh

### Control plane

Control plane lưu và phân phối cấu hình routing, endpoint discovery và chính sách bảo mật cho data plane. Với cấu hình sử dụng Istio APIs, Kubernetes custom resources như VirtualService, DestinationRule, PeerAuthentication và AuthorizationPolicy mô tả hành vi mong muốn. Envoy proxies nhận cấu hình thực thi qua xDS.

Control plane không nhất thiết xử lý trực tiếp từng request người dùng. Trong mô hình sidecar, phần lớn traffic chạy giữa các Envoy proxies; control plane cập nhật danh sách endpoint và policy khi hệ thống thay đổi.

### Data plane

Data plane thực thi routing, mTLS, policy, load balancing, retry và thu telemetry. Trên GKE dùng Istio APIs, nó thường là **Envoy sidecar** cùng Pod với ứng dụng. Sidecar có footprint CPU/RAM và có thể thêm độ trễ; cần đưa vào capacity planning.

Với triển khai dựa trên **Google Cloud Service Routing APIs** cho VM và các workload phù hợp, data plane có thể là Envoy proxy hoặc **proxyless gRPC** hỗ trợ xDS. Proxyless gRPC thay thế một phần vai trò sidecar trong ứng dụng hỗ trợ và không tương đương mọi tính năng của Istio APIs.

### Service identity và CA

Workload sử dụng định danh gắn với service account và trust domain. Certificate Authority cấp/luân chuyển certificate, cho phép các workload xác thực lẫn nhau bằng mTLS. Trong hệ thống GKE, có thể dùng **Mesh CA** hoặc **Certificate Authority Service (CA Service)** theo các tổ hợp được hỗ trợ.

Nếu hai cluster dùng các CA/trust domain không tương thích, có route mạng đúng vẫn chưa đủ để mTLS thành công. Đường tin cậy (trust chain), thời gian certificate, danh tính source và authorization policy phải phù hợp.

~~~mermaid
flowchart TB
    CP[Cloud Service Mesh control plane]
    CA[Mesh CA hoặc CA Service]
    subgraph G1[GKE Cluster A]
      PA[Envoy sidecar A]
      SA[Service checkout]
    end
    subgraph G2[GKE Cluster B]
      PB[Envoy sidecar B]
      SB[Service payment]
    end
    CP -. xDS discovery / policy .-> PA
    CP -. xDS discovery / policy .-> PB
    CA -. certificates / trust .-> PA
    CA -. certificates / trust .-> PB
    SA --> PA
    PA <-->|mTLS / service routing| PB
    PB --> SB
~~~

Sơ đồ chỉ là mô hình logic cho một mesh nhiều cluster tương thích; không ngụ ý mọi workload qua các mạng vật lý khác nhau sẽ tự động có kết nối trực tiếp. Nếu Pod IP không định tuyến được giữa các mạng, cần gateway hoặc giải pháp kết nối thích hợp.

## 3. Chọn mô hình triển khai theo môi trường

Tên sản phẩm **Cloud Service Mesh** bao trùm nhiều kiểu triển khai. Hai hệ thống có cùng nhãn “Cloud Service Mesh” không nhất thiết dùng cùng control plane, API hoặc cơ chế quản lý.

| Môi trường | Lựa chọn chính | Cách điều khiển | Điều cần kiểm tra |
|---|---|---|---|
| GKE trên Google Cloud | Managed Cloud Service Mesh, khuyến nghị cho triển khai mới | Istio APIs với managed control plane TRAFFIC_DIRECTOR | Fleet, GKE version, region, Mesh CA/CA Service, tính năng được hỗ trợ |
| Compute Engine VM hoặc kết hợp VM + GKE/proxyless gRPC | Managed Cloud Service Mesh theo Service Routing APIs | Google Cloud networking/service routing APIs, Envoy hoặc proxyless gRPC | Không sao chép nguyên Istio VirtualService/AuthorizationPolicy sang API khác |
| Google Distributed Cloud software-only on-premises | In-cluster Cloud Service Mesh | Istio APIs và control plane do tổ chức vận hành | Version/platform support, connectivity, gateway, CA và trách nhiệm upgrade |
| Kubernetes ở cloud khác, ví dụ EKS/AKS | Chỉ theo lựa chọn off-Google Cloud đang được hỗ trợ | In-cluster Istio APIs; kiểm tra giới hạn attached clusters | Deprecation, support lifecycle, cross-platform discovery, network |
| Legacy GKE có in-cluster ISTIOD hoặc managed ISTIOD | Legacy/deprecated | Cần kế hoạch hiện đại hóa lên managed TRAFFIC_DIRECTOR | Tương thích API, thứ tự rollout, downtime và thời hạn hỗ trợ |

**Điểm quan trọng:** managed control plane cho GKE trên Google Cloud không đồng nghĩa managed control plane cho một Kubernetes cluster ở AWS, Azure hoặc on-premises. Với cluster ngoài Google Cloud, tài liệu hiện hành mô tả **in-cluster control plane**; hỗ trợ của từng nền tảng có điều kiện. Các hướng dẫn hybrid/multi-cloud cũ có thể dựa trên phiên bản hoặc mô hình control plane khác, không nên áp dụng nguyên xi cho fleet mới.

### Lưu ý vòng đời sản phẩm

Theo release notes công bố tháng 9/2026, cả in-cluster ISTIOD lẫn managed ISTIOD trên GKE Google Cloud đã bị deprecated, với mốc ngừng hỗ trợ dự kiến **1/3/2028**. In-cluster control plane trên Google Distributed Cloud software-only vẫn được mô tả là được hỗ trợ. Hỗ trợ cho một số attached EKS/AKS cluster và GKE on AWS/Azure có lịch deprecation riêng; với attached clusters có thông báo mốc **17/3/2027**. Trước khi thiết kế mở rộng, phải kiểm tra trang Supported Platforms, Deprecations và Release Notes cho đúng platform/version.

Một thiết kế hybrid bền vững có thể là **hai mesh quản trị riêng**, kết nối qua giao thức/gateway và API contract, thay vì cố ép mọi workload vào một control plane không hỗ trợ.

## 4. Single-cluster, multi-cluster và multi-network

### Single-cluster

Một cluster, một miền endpoint discovery và các sidecar Envoy. Đây là mô hình dễ triển khai và quan sát nhất. Nên dùng làm pilot để kiểm tra mTLS, authorization, TLS identity và overhead.

### Multi-cluster, cùng mạng

Hai hoặc nhiều GKE clusters trong một mesh, có thể ở nhiều region/project, dùng endpoint discovery và route đến service ở cluster khác. Điều kiện điển hình:

- Các clusters thuộc **cùng fleet host project**.
- Nếu khác project, các GKE clusters dùng Shared VPC trên **cùng network** theo hướng dẫn managed multi-cluster.
- Có đường kết nối Pod-to-Pod hợp lệ và firewall cho traffic giữa clusters.
- Dùng chung mô hình CA/trust thích hợp; cùng Mesh CA hoặc cấu trúc CA Service tương thích.
- Namespace và service identity được đặt nhất quán theo thiết kế.
- FQDN/DNS của service được phân giải đúng; có thể cần DNS proxy/endpoint discovery configuration.

Nếu hai cluster ở các VPC khác nhau, **việc cùng fleet không tự tạo route qua VPC**. Cần quyết định hỗ trợ multi-network/gateway theo đúng phiên bản, không gán giả định “cross-cluster tự hoạt động”.

### Multi-network và hybrid

Khi Pod IP không truy cập trực tiếp giữa các network, một hoặc nhiều **east-west gateways** đóng vai trò điểm liên kết mTLS và định tuyến traffic giữa mesh networks. Kết nối WAN hoặc cross-cloud cần đường mạng, route, firewall và khả năng truy cập gateway. Có thể dùng Cloud VPN/Interconnect, private connectivity hoặc gateway được phép expose phù hợp chính sách tổ chức.

~~~mermaid
flowchart LR
    U[Ứng dụng khách]
    L[Global/Regional LB hoặc API Gateway]
    subgraph GCP[Google Cloud]
      A[Cluster GKE A / service checkout]
      GA[East-west gateway A]
    end
    subgraph EDGE[On-premises hoặc other cloud]
      GB[East-west gateway B]
      B[Service payment / inventory]
    end
    U --> L --> A
    A --> GA
    GA <-->|VPN/Interconnect hoặc kết nối được duyệt| GB
    GB --> B
~~~

Đây là sơ đồ **khả năng tích hợp**; không phải tuyên bố rằng managed GKE mesh và mọi on-prem/EKS mesh đều có thể tham gia cùng control plane. Phải xác minh kiểu topology và feature matrix, nhất là hybrid setup có hướng dẫn riêng, yêu cầu reachability của Kubernetes API server/gateway và có trường hợp không hỗ trợ private clusters.

## 5. Những thành phần cần thống nhất giữa clusters

### Fleet và membership

Fleet là ranh giới logic quản lý các GKE clusters. Trong managed Cloud Service Mesh với Istio APIs, fleet API có thể bật mesh feature và cấp control plane managed cho membership. Nhiều cluster tham gia cùng mesh phải được đăng ký đúng fleet; đồng thời nên thống nhất tên namespace và Kubernetes Service cho những service đa cluster.

### Namespace sameness và service naming

Nếu service payment có cùng tên nhưng chạy ở hai cluster, cách đặt namespace, service account, label và port cần nhất quán. Khác biệt bất ngờ ở namespace hoặc port có thể khiến control plane không ghép endpoints đúng hoặc policy áp vào không đủ.

Sử dụng Kubernetes FQDN như payment.shop.svc.cluster.local trong các ví dụ, nhưng cần kiểm tra DNS proxy/endpoint discovery trong mô hình multi-cluster. Namespace sameness không phải yêu cầu rằng mọi application đều bắt buộc có cùng code version.

### Network identity

Một cluster hoặc network cần định danh mạng nhất quán nếu triển khai multi-network. Gateway và endpoint discovery dùng danh tính/network metadata để biết route tới endpoint ở cùng mạng hay khác mạng.

### Trust domain

Trust domain là ranh giới danh tính của certificate, không phải subnet CIDR. Trong một GKE fleet dùng Mesh CA, service identity thường liên quan tới fleet workload identity pool, có dạng **FLEET_PROJECT_ID.svc.id.goog**. Khi sử dụng AuthorizationPolicy theo principals, phải ghi đúng trust domain thực tế; không copy cố định cluster.local từ môi trường khác.

### CA và certificate

Các clusters cần có khả năng xác minh certificate chain của nhau. Với CA Service, có thể cần subordinate CA pools cùng root CA hoặc trust configuration theo hướng dẫn. Theo dõi certificate rotation, clock skew, SAN identity và lỗi handshake, đặc biệt tại east-west gateway.

## 6. Chuẩn bị và kích hoạt managed Cloud Service Mesh cho GKE

Ví dụ dưới đây chỉ minh họa các bước chính của **GKE managed Cloud Service Mesh dùng Istio APIs**, không dùng để cài off-cloud in-cluster. Cluster phải thỏa điều kiện GKE version, region, quyền IAM, fleet registration và network được Google Cloud công bố.

### Bước 1: Kiểm tra fleet

~~~bash
export FLEET_PROJECT_ID="platform-fleet-prod"
export MEMBERSHIP_NAME="gke-checkout-asia"
export MEMBERSHIP_LOCATION="asia-southeast1"

gcloud container fleet memberships list \
  --project="$FLEET_PROJECT_ID"
~~~

Nếu cluster chưa là membership, thực hiện bước register theo hướng dẫn provisioning hiện hành. Không tiếp tục nếu fleet membership trỏ nhầm project hoặc cluster.

### Bước 2: Bật mesh feature

~~~bash
gcloud container fleet mesh enable \
  --project="$FLEET_PROJECT_ID"
~~~

### Bước 3: Cấu hình automatic management cho membership

~~~bash
gcloud container fleet mesh update \
  --management=automatic \
  --memberships="$MEMBERSHIP_NAME" \
  --location="$MEMBERSHIP_LOCATION" \
  --project="$FLEET_PROJECT_ID"
~~~

Nếu membership nằm trong global location hoặc được register theo phiên bản công cụ khác, hãy tra vị trí thực bằng fleet memberships list. Đối với cấu hình dùng shared VPC, cần cấp role thích hợp cho service agents của mesh trên network project theo tài liệu. Với CA Service, các bước cấu hình CA có thể khác và cần chuẩn bị trước khi enable.

### Bước 4: Xác minh control plane

~~~bash
gcloud container fleet mesh describe \
  --project="$FLEET_PROJECT_ID"
~~~

Kiểm tra membership state, control plane state và version/channel được triển khai. Không suy rằng command thành công nghĩa là data plane trong mọi Pod đã sẵn sàng. Chỉ tạo namespace injection/rollout workload sau khi xem đúng hướng dẫn revision label của môi trường.

### Bước 5: Kiểm tra workload và sidecar

~~~bash
kubectl get pods -n shop -o wide
kubectl get peerauthentications,authorizationpolicies -n shop
kubectl get virtualservices,destinationrules -n shop
~~~

Chọn đúng kubectl context cho từng cluster trước khi chạy lệnh. Namespace shop là ví dụ và phải tồn tại trước. Với managed data plane, cơ chế injection/revision và thành phần in-cluster do hệ thống quản lý; không tự sửa label hoặc webhook theo bài hướng dẫn cũ nếu không phù hợp version đang chạy.

## 7. Bảo mật traffic bằng mTLS và AuthorizationPolicy

### mTLS là gì?

Mutual TLS xác thực cả client và server khi thiết lập kết nối. Trong mesh sidecar, Envoy có thể quản lý certificate và TLS thay cho ứng dụng. Tuy nhiên, một kết nối đã được mã hóa **không có nghĩa là client được phép gọi mọi API**. Cần kết hợp mTLS với AuthorizationPolicy để quyết định service nào có quyền gọi service nào.

### PeerAuthentication STRICT

Ví dụ giới hạn mọi workload có proxy trong namespace shop chỉ chấp nhận mTLS:

~~~yaml
apiVersion: security.istio.io/v1beta1
kind: PeerAuthentication
metadata:
  name: require-mtls
  namespace: shop
spec:
  mtls:
    mode: STRICT
~~~

Áp dụng:

~~~bash
kubectl apply -f peer-authentication.yaml
kubectl -n shop get peerauthentication
~~~

Đây là chính sách namespace-level. Chỉ áp dụng sau khi kiểm tra mọi client và server liên quan có proxy/transport phù hợp; bật STRICT quá sớm có thể khiến workload cũ chưa tham gia mesh bị chặn. Trong managed TRAFFIC_DIRECTOR, PeerAuthentication DISABLE không được hỗ trợ; nếu cần tương thích tạm thời, phải làm theo hướng dẫn transport security/destination policy tương ứng.

### AuthorizationPolicy theo danh tính service account

Giả sử chỉ service account checkout trong namespace shop được gọi service payment có nhãn app=payment. Định danh principal thực phải xác nhận theo **fleet trust domain**:

~~~yaml
apiVersion: security.istio.io/v1beta1
kind: AuthorizationPolicy
metadata:
  name: payment-only-checkout
  namespace: shop
spec:
  selector:
    matchLabels:
      app: payment
  action: ALLOW
  rules:
  - from:
    - source:
        principals:
        - "FLEET_PROJECT_ID.svc.id.goog/ns/shop/sa/checkout-sa"
    to:
    - operation:
        methods: ["POST"]
        paths: ["/payments"]
~~~

Thay FLEET_PROJECT_ID bằng giá trị và trust domain thực tế trước khi apply. Khi có ít nhất một ALLOW policy áp vào workload, những request không khớp rule sẽ bị từ chối theo semantics của Istio authorization. Với traffic không phải HTTP, việc lọc paths/methods không áp dụng giống HTTP và cần thiết kế theo port/identity.

**Thứ tự rollout an toàn:** bật telemetry và quan sát → kiểm tra mTLS PERMISSIVE nếu đang chuyển đổi → kiểm thử client identity → bật STRICT → chạy test quyền âm/dương → áp authorization từng service. Luôn thử việc chặn một workload không được phép, chứ không chỉ xác nhận request hợp lệ thành công.

### Mesh CA không thay thế IAM

AuthorizationPolicy áp vào request service-to-service trong mesh. Khi payment gọi BigQuery hoặc Secret Manager, vẫn cần IAM của Google Cloud API. Khi employee truy cập UI, vẫn cần xác thực người dùng cuối. Cần defense in depth ở các lớp khác nhau.

## 8. Điều khiển traffic bằng VirtualService và DestinationRule

Một lợi ích quan trọng là triển khai phiên bản mới theo canary mà không đưa toàn bộ lưu lượng ngay lập tức.

### DestinationRule định nghĩa subsets

Giả sử Kubernetes Service payment có hai nhóm Pod gắn label version=v1 và version=v2:

~~~yaml
apiVersion: networking.istio.io/v1beta1
kind: DestinationRule
metadata:
  name: payment-destination
  namespace: shop
spec:
  host: payment.shop.svc.cluster.local
  subsets:
  - name: v1
    labels:
      version: v1
  - name: v2
    labels:
      version: v2
~~~

### VirtualService chia 90/10

~~~yaml
apiVersion: networking.istio.io/v1beta1
kind: VirtualService
metadata:
  name: payment-routing
  namespace: shop
spec:
  hosts:
  - payment.shop.svc.cluster.local
  http:
  - route:
    - destination:
        host: payment.shop.svc.cluster.local
        subset: v1
      weight: 90
    - destination:
        host: payment.shop.svc.cluster.local
        subset: v2
      weight: 10
~~~

Các ví dụ này điều khiển route tới hai phiên bản service, **không tự tạo Deployment/Service v1 và v2**. Chỉ chạy khi Pod labels, port và service đã tồn tại. Trong multi-cluster, rule áp theo phạm vi cấu hình và endpoint discovery; không được giả định một VirtualService đơn giản có thể ép traffic tới region cụ thể mà không cần bổ sung topology/route policy phù hợp.

### Canary có SLO gates

Một kế hoạch hợp lý:

1. Triển khai v2 không nhận traffic công khai; test health và mTLS.
2. Chuyển 1–5% traffic tới v2 nếu chính sách cho phép.
3. So sánh p95 latency, error rate và business success giữa v1/v2.
4. Nâng lên 10%, 25%, 50% rồi 100% theo thời gian quan sát.
5. Nếu SLO xấu, đặt weight v2 về 0 và xác minh config đã phân phối tới data plane.

Mọi thay đổi traffic policy cần theo dõi **config propagation delay**. Managed TRAFFIC_DIRECTOR có thể cần thời gian validate và phân phối policy tới proxies; không coi kubectl apply thành công là traffic lập tức đổi ở mọi Pod.

## 9. Timeout, retry và circuit breaking giữa môi trường

Traffic qua region hoặc WAN có độ trễ và biến động cao hơn traffic cùng node. Retry không đúng cách có thể tăng tải lên hệ thống đang gặp sự cố; timeout quá ngắn có thể tạo false failure.

### Ví dụ timeout và giới hạn retries

~~~yaml
apiVersion: networking.istio.io/v1beta1
kind: VirtualService
metadata:
  name: inventory-policy
  namespace: shop
spec:
  hosts:
  - inventory.shop.svc.cluster.local
  http:
  - timeout: 3s
    retries:
      attempts: 2
      perTryTimeout: 1s
      retryOn: "connect-failure,refused-stream,unavailable"
    route:
    - destination:
        host: inventory.shop.svc.cluster.local
~~~

Đây là policy minh họa; khả năng hỗ trợ cụ thể của retry fields phải được đối chiếu với feature matrix của managed Cloud Service Mesh. Retry chỉ nên áp cho thao tác idempotent hoặc khi API có cơ chế chống thực hiện trùng. Nếu ứng dụng Java/Spring cũng retry, cần tránh nhân số lần gọi ở nhiều tầng.

### Circuit breaking và outlier detection

DestinationRule có thể áp connection pool limits và outlier detection với các mức hỗ trợ khác nhau. Cần kiểm tra version và cách xDS implementation xử lý; không sao chép mọi thuộc tính từ Istio upstream vào managed service. Những cấu hình quá chặt có thể tự biến đợt lỗi tạm thời thành việc loại hết endpoints.

Trong mô hình WAN, đừng dùng mesh để che các vấn đề thiết kế đồng bộ quá nhiều round-trip. Những nghiệp vụ không cần phản hồi tức thời có thể chuyển thành sự kiện Pub/Sub hoặc hàng đợi, giảm phụ thuộc vào kết nối liên vùng trong đường request.

## 10. East-west gateway trong hybrid/multi-network

**North-south** là traffic từ client bên ngoài vào hệ thống. **East-west** là traffic giữa workloads, clusters, VPC hoặc network. Multi-network service mesh thường cần east-west gateway để proxy traffic qua biên mạng khi Pod IP không thể route trực tiếp.

### Gateway phải đáp ứng điều gì?

- Reachable từ mạng bên kia qua IP/port được phép.
- Có certificate/identity và trust chain phù hợp.
- Chỉ expose service/port được policy cho phép.
- Có health checking, capacity, failover và observability.
- Không mở Kubernetes API server hoặc gateway ra Internet ngoài nhu cầu đã xác định.
- Có route phản hồi, NAT/MTU phù hợp và cấu hình DNS/SNI chính xác.

### Những chỗ dễ nhầm

1. **VPC peering không transitive:** nếu traffic phải đi qua mạng trung gian, cần thiết kế route/gateway thực sự; cùng một mesh không làm route tự xuyên qua các VPC.
2. **Gateway không tự giải quyết ACL:** mTLS xác nhận gateway/workload, authorization phải quyết định request có được phép.
3. **SNI, host và trust domain khác nhau:** hostname có thể resolve đúng nhưng TLS handshake vẫn fail vì server identity không khớp.
4. **Một gateway public không phải secure-by-default:** cần firewall/allowlist, rate limiting, auth, log và có thể private connectivity.
5. **Cùng fleet không đồng nghĩa cùng mạng:** phải kiểm tra reachability trước khi bật endpoint discovery đa cluster.

### Hạn chế hybrid cần đọc trước khi triển khai

Google có hướng dẫn “Set up a hybrid mesh” và “Set up a multi-cluster mesh outside Google Cloud” với điều kiện cụ thể. Một số topology yêu cầu tất cả clusters chung fleet host project; control plane address và gateway reachable; **private clusters có thể không được hỗ trợ trong hướng dẫn hybrid tương ứng**. Không áp dụng một hướng dẫn multi-cluster GKE managed cho EKS, AKS hoặc GDC on-premises mà chưa kiểm tra Supported Platforms/Features và deprecation.

## 11. Giám sát và phân tích lỗi xuyên môi trường

Cloud Service Mesh cung cấp service graph và telemetry cho các service phù hợp, sử dụng Cloud Monitoring, Cloud Logging và có thể Cloud Trace tùy cấu hình. Envoy sidecars quan sát HTTP traffic theo nguồn/đích; telemetry có thể phân biệt latency, success/error và service dependencies.

### SLI/SLO nên theo dõi

| Chỉ số | Cách hiểu | Vì sao quan trọng |
|---|---|---|
| Request success rate | Tỷ lệ request hoàn tất không lỗi theo định nghĩa nghiệp vụ | Phát hiện lỗi ở đường mesh và backend |
| p50/p95/p99 latency | Độ trễ theo source, destination và route | Nhìn rõ WAN/gateway overhead và tail latency |
| Error code distribution | 4xx, 5xx, gRPC status, connection failures | Phân biệt lỗi auth và lỗi dịch vụ |
| mTLS handshake failure | Số lỗi xác thực certificate/trust | Phát hiện CA/clock/trust-domain mismatch |
| Authorization denied | Request bị policy chặn | Xác minh least privilege, phát hiện bất thường |
| Endpoint health | Số endpoint sẵn sàng ở từng cluster | Phát hiện failover/routing sai |
| Cross-region bytes | Egress và băng thông qua biên mạng | Theo dõi cost, bottleneck |
| Proxy resource utilization | CPU/memory/connection count | Capacity planning cho sidecar/gateway |
| Configuration age | Độ trễ từ thay đổi policy tới proxy nhận | Phát hiện stale policy |

Các SLO, ví dụ 99,9% availability trong 28 ngày hoặc p95 latency dưới 250 ms, **chỉ là minh họa**; phải điều chỉnh theo giao thức, loại dịch vụ và vùng phục vụ. Mesh HTTP telemetry chưa đủ để đo nghiệp vụ như đơn hàng thành công; thêm application instrumentation và tracing.

### Công cụ kiểm tra

~~~bash
gcloud container fleet mesh describe \
  --project="$FLEET_PROJECT_ID"

kubectl -n shop get pods -o wide
kubectl -n shop get svc,endpoints
kubectl -n shop get peerauthentication,authorizationpolicy
kubectl -n shop get virtualservice,destinationrule
~~~

Với Istio APIs, công cụ istioctl có thể hỗ trợ kiểm tra proxy config và policy nếu được hỗ trợ trong phiên bản bạn sử dụng. Ví dụ:

~~~bash
istioctl proxy-status
istioctl analyze -n shop
~~~

Đối với managed data plane distroless, không kỳ vọng có bash/curl sẵn trong sidecar. Nếu cần phân tích packet hoặc network, dùng ephemeral debug container hoặc công cụ log/tracing phù hợp, theo quyền tổ chức.

### Phân tầng khi điều tra một request lỗi

1. DNS có resolve đúng host không?
2. Service và endpoint có tồn tại ở đúng cluster/namespace không?
3. Network, route, firewall, gateway port có thông không?
4. Workload có sidecar/proxy và đã nhận config mới chưa?
5. mTLS certificate, trust domain và SNI có hợp lệ không?
6. AuthorizationPolicy có chặn request không?
7. VirtualService/DestinationRule có route đúng subset và port không?
8. Backend application có trả lỗi hoặc timeout không?
9. Có retry/circuit breaker làm lỗi tăng lên không?
10. Telemetry và tracing có chỉ ra vị trí lỗi rõ ràng không?

## 12. Thiết kế một hệ thống mẫu ở ba môi trường

### Bối cảnh

Doanh nghiệp có:

- **GKE A (asia-southeast1):** checkout và payment production, nhiều traffic.
- **GKE B (asia-east1):** phiên bản dự phòng để giảm ảnh hưởng sự cố vùng.
- **On-premises:** inventory service giao tiếp với ERP cũ; có kết nối Cloud Interconnect.

Mục tiêu: checkout gọi payment bảo mật trong hai cluster GKE; inventory vẫn nằm on-premises nhưng có thể được truy cập qua endpoint hạn chế; hệ thống theo dõi latency và sẵn sàng chuyển dần dịch vụ inventory lên GKE.

### Giai đoạn 1: mesh trên GKE

1. Chuẩn hóa GKE version, vùng hỗ trợ, Fleet host project và Shared VPC.
2. Enable managed Cloud Service Mesh cho từng membership tương thích.
3. Kiểm tra proxy injection, endpoint discovery, CA/trust domain và telemetry.
4. Bật mTLS STRICT và AuthorizationPolicy trong namespace shop theo rollout.
5. Áp canary route v1/v2 trong cùng cluster trước khi mở rộng multi-cluster.

### Giai đoạn 2: GKE multi-cluster

1. Bảo đảm Pod-to-Pod reachability nếu chọn same-network topology.
2. Kiểm tra firewall/route giữa clusters và namespace sameness.
3. Dùng cùng fleet và CA trust theo managed multi-cluster guide.
4. Kiểm tra discovery, DNS và traffic tới endpoints ở cả hai cluster.
5. Test mất endpoint, lỗi một cluster và cách traffic fallback.

### Giai đoạn 3: tích hợp inventory on-premises

Có hai lựa chọn có thể cân nhắc:

**A. Giữ inventory ngoài mesh:** expose inventory qua private endpoint hoặc gateway mTLS chuyên dụng, dùng Cloud Interconnect/VPN, gateway/proxy ở GKE gọi tới endpoint theo contract. Quản lý certificate và ACL riêng tại boundary. Cách này ít phụ thuộc vào khả năng một mesh thống nhất cross-platform.

**B. Xây hybrid mesh được hỗ trợ:** dùng off-Google Cloud in-cluster Cloud Service Mesh trong nền tảng on-premises tương thích, kiểm tra hỗ trợ version/topology, kết nối east-west gateway, CA/trust domain và service discovery theo hướng dẫn. Cần xác nhận rõ không dùng managed control plane của GKE cho off-cloud workload khi nền tảng không hỗ trợ.

Trong cả hai phương án, inventory service có thể cần timeout dài hơn các service cùng cluster; hạn chế synchronous call chain, dùng retry có giới hạn và cân nhắc event-based integration cho luồng không yêu cầu nhất quán tức thời.

### Giai đoạn 4: validate và cutover

Chạy contract tests, canary và chaos test có kiểm soát. Xác nhận:

- Lưu lượng hợp lệ được mã hóa và đúng danh tính.
- Service không được phép không truy cập được payment.
- Service inventory reachable qua đường kết nối được phê duyệt.
- Lỗi một gateway/cluster không làm toàn bộ sản phẩm ngừng hoạt động ngoài SLO.
- Telemetry có nguồn/đích và trace đủ để điều tra.
- Có rollback nếu config mới làm tăng lỗi.

## 13. Chi phí và tác động hiệu năng

Service mesh giúp giảm trùng lặp việc quản trị bảo mật và routing nhưng phát sinh chi phí:

| Thành phần | Nguồn chi phí |
|---|---|
| Envoy sidecars | CPU/memory cho mỗi Pod, tăng requests của cluster |
| East-west gateways | Pod/VM capacity, load balancer, public/private IP |
| Cross-region/cross-cloud traffic | Network egress, VPN/Interconnect, WAN bandwidth |
| Telemetry | Cloud Monitoring metrics, logging ingestion, traces và lưu trữ |
| Certificate/CA | Chi phí CA Service nếu chọn, vận hành chính sách và khóa |
| Control plane/mô hình license | Chính sách định giá Cloud Service Mesh/GKE Enterprise theo cấu hình |
| Vận hành | Thời gian làm policy review, upgrade, incident response |

Không ước lượng mesh cost chỉ theo số lượng cluster. Một cluster nhiều Pod có thể cần nhiều sidecar tài nguyên; một thiết kế cross-region chatty có thể phát sinh egress lớn hơn chi phí control plane.

### Đo trước và sau khi bật mesh

1. Baseline request latency, error rate, pod CPU/memory trước triển khai.
2. Bật mesh trên một nhóm service đại diện.
3. So sánh sidecar overhead, p95/p99, network egress, throughput.
4. Tăng traffic và số Pod để kiểm tra control plane propagation/endpoint churn.
5. Điều chỉnh proxy resource requests/limits và telemetry sampling theo SLO.
6. Ghi rõ phần giá trị đạt được: policy nhất quán, thời gian triển khai, incident MTTR.

## 14. Quy trình thay đổi an toàn trong production

Mesh là hạ tầng có blast radius lớn: một AuthorizationPolicy sai có thể chặn hàng loạt services; một VirtualService sai có thể gửi traffic tới tập Pod chưa sẵn sàng.

Quy trình đề xuất:

1. Lưu Istio manifests, gateway config và fleet config trong Git.
2. Kiểm tra schema và supported feature matrix của control plane thực tế.
3. Đánh giá tác động theo namespace/service và review người sở hữu.
4. Test trên cluster riêng hoặc môi trường staging tương đương.
5. Áp policy ở phạm vi hẹp trước khi áp toàn mesh.
6. Theo dõi config propagation và request errors.
7. Mở rộng rollout bằng từng cohort/namespace.
8. Có bản cấu hình rollback, dashboard và contact on-call.
9. Kiểm tra policy sau khi upgrade GKE/channel/mesh version.
10. Định kỳ audit principal rules, certificate trust và các gateway được expose.

### Nguyên tắc rollout security

Không áp ngay mesh-wide STRICT nếu còn workload chưa có sidecar. Bắt đầu ở service ít rủi ro, xác minh traffic từ non-mesh workload, rồi nâng dần. Khi một service có cả HTTP và TCP, cần kiểm tra chính sách riêng theo port; không coi một rule HTTP method là bộ lọc cho mọi giao thức.

## 15. Các lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| GKE mesh chưa ACTIVE sau enable | Fleet/permissions, GKE version hoặc API chưa đạt điều kiện | Fleet membership, feature state, service agent roles, release channel |
| Service không tìm thấy endpoint ở cluster khác | Chưa bật endpoint discovery, DNS/FQDN hoặc namespace mismatch | asm-options, DNS proxy, namespace sameness, service port |
| Có endpoint nhưng timeout giữa clusters | Pod network không route hoặc firewall chặn | VPC/Shared VPC, route, firewall, gateway reachability |
| mTLS handshake failure | CA/trust domain khác, certificate lỗi/expired hoặc SNI mismatch | Certificate chain, Mesh CA/CAS config, time sync |
| Một client bị HTTP 403 sau policy | Principal sai hoặc rule thiếu method/path | AuthZ policy, trust domain, source SA, access logs |
| Workload cũ bị mất kết nối khi bật STRICT | Client chưa tham gia mesh hoặc vẫn plaintext | Audit client, PERMISSIVE transition theo policy được hỗ trợ |
| Canary traffic không theo 90/10 | Label subset sai, proxy chưa nhận config, low sample size | VirtualService, DestinationRule, Pod labels, rollout delay |
| Lỗi tăng khi bật retries | Multiple retry layers, request không idempotent | Retry policy Istio + ứng dụng, request IDs và timeout budget |
| Cross-cloud gateway reachable nhưng không gọi được service | Endpoint discovery, TLS identity hoặc auth boundary không đúng | Gateway config, SNI, CA, service mapping, policy |
| Mesh UI thiếu metrics | Sidecar/telemetry/export chưa hoạt động hoặc giao thức không hỗ trợ | Proxy status, Cloud Monitoring, sampling, protocol |
| Proxy CPU/memory tăng mạnh | Sidecar quá nhỏ, traffic/telemetry tăng | Resource sizing, connection pools, sampling |
| Control plane đổi policy chậm | Đặc tính TRAFFIC_DIRECTOR config propagation | Monitor config age và endpoint health, không lặp apply bừa bãi |

## 16. Checklist thiết kế trước khi production

- [ ] Chọn rõ workload GKE, Compute Engine VM, on-premises hay Kubernetes cloud khác.
- [ ] Đã kiểm tra Managed vs in-cluster option theo Supported Platforms và deprecation.
- [ ] Không giả định off-Google Cloud cluster có cùng managed control plane với GKE.
- [ ] Fleet host project/memberships được chuẩn hóa cho managed multi-cluster.
- [ ] Có sơ đồ network routes, Pod CIDRs, DNS, gateway và firewall.
- [ ] Multi-network có lựa chọn east-west gateways hoặc giao thức boundary khác.
- [ ] CA, trust domain, certificate rotation và service accounts được xác minh.
- [ ] Có triển khai mTLS theo lộ trình và authorization dựa trên workload identity.
- [ ] Không nhầm IAM Google APIs với authorization request trong mesh.
- [ ] Định nghĩa namespace, Kubernetes Service names, labels và port nhất quán.
- [ ] Có chính sách timeout/retry/circuit breaking không làm trùng thao tác ghi.
- [ ] VirtualService/DestinationRule được test canary và có đường rollback.
- [ ] Đã đo request success, latency, auth denies và certificate errors.
- [ ] Có health checks, capacity và failover cho east-west gateways.
- [ ] Đã kiểm tra giới hạn hybrid/private cluster/attached cluster đúng version.
- [ ] Đã đánh giá chi phí sidecar, egress, telemetry và license.
- [ ] Có GitOps/IaC, review, audit và runbook sự cố xuyên môi trường.

## 17. Bài thực hành thiết kế

Hãy thiết kế cho hệ thống gồm GKE A ở Singapore, GKE B ở Taiwan và inventory ở on-premises:

1. Quyết định GKE A/B thuộc một fleet và Shared VPC hay có mạng tách biệt.
2. Chọn managed Cloud Service Mesh cho GKE, kiểm tra region và GKE version.
3. Vẽ đường giao tiếp checkout → payment và checkout → inventory.
4. Liệt kê những nơi cần CA trust, mTLS, AuthorizationPolicy và IAM.
5. Chọn topology inventory ngoài mesh qua private gateway hoặc một hybrid mesh được hỗ trợ.
6. Thiết kế source identity được phép gọi payment; các danh tính khác phải bị chặn.
7. Tạo plan canary payment v2, kèm SLI và điều kiện rollback.
8. Liệt kê cách ứng dụng hoạt động nếu liên kết tới on-premises bị lỗi 5 phút.
9. Tính chi phí sơ bộ của extra proxies, gateways và egress.
10. Tạo bảng kiểm chứng tối thiểu: network, DNS, policy, certificate, traffic và telemetry.

**Câu hỏi tự đánh giá:** Nếu cả hai GKE clusters cùng fleet nhưng Pod-to-Pod traffic không đi được, liệu cùng fleet có đủ để Cloud Service Mesh hoạt động xuyên cluster không? **Không.** Endpoint discovery, route/firewall và đôi khi east-west gateways vẫn phải thỏa điều kiện topology. Nếu inventory nằm ở cloud khác, cần xác nhận mô hình control plane và support status trước khi tuyên bố hợp nhất thành một mesh.

## 18. Kết luận

Cloud Service Mesh tạo một lớp giao tiếp thống nhất cho microservices thông qua discovery, routing, mTLS, authorization và telemetry. Trong kiến trúc nhiều môi trường, giá trị lớn nhất là **áp chính sách nhất quán giữa các workload được hỗ trợ** và giảm công sức lập trình lại TLS/routing trong từng service.

Tuy nhiên, nền tảng triển khai quyết định khả năng thực tế: GKE trên Google Cloud nên ưu tiên managed Cloud Service Mesh với control plane hiện hành; Compute Engine VM có lựa chọn Service Routing APIs; on-premises hoặc Kubernetes cloud khác có mô hình in-cluster Istio APIs và giới hạn riêng. Một hệ thống hybrid không tự động biến thành một mesh managed duy nhất chỉ bằng việc kết nối VPN hoặc đăng ký fleet.

Hãy bắt đầu từ **platform support → network reachability → identity/trust → endpoint discovery → mTLS/authorization → traffic policy → observability → rollout**. Khi các tầng được kiểm tra riêng và tích hợp dần, service mesh có thể tăng an toàn và độ tin cậy mà không tạo thêm một điểm lỗi khó vận hành.

## Tài liệu tham khảo

- [Cloud Service Mesh overview](https://docs.cloud.google.com/service-mesh/docs/overview)
- [Cloud Service Mesh supported platforms](https://docs.cloud.google.com/service-mesh/docs/supported-platforms)
- [Supported features: managed control plane and Istio APIs](https://docs.cloud.google.com/service-mesh/docs/supported-features-managed)
- [Supported features: in-cluster control plane](https://docs.cloud.google.com/service-mesh/docs/supported-features-in-cluster)
- [Managed control plane overview and modernization](https://docs.cloud.google.com/service-mesh/docs/managed-control-plane-overview)
- [Provision a managed Cloud Service Mesh control plane on GKE](https://docs.cloud.google.com/service-mesh/docs/onboarding/provision-control-plane)
- [Set up a multi-cluster mesh on managed Cloud Service Mesh](https://docs.cloud.google.com/service-mesh/docs/operate-and-maintain/multi-cluster)
- [Set up a hybrid mesh](https://docs.cloud.google.com/service-mesh/docs/operate-and-maintain/hybrid-mesh)
- [Set up multi-cluster Cloud Service Mesh outside Google Cloud](https://docs.cloud.google.com/service-mesh/docs/operate-and-maintain/off-gcp-multi-cluster-setup)
- [Configure mTLS transport security](https://docs.cloud.google.com/service-mesh/docs/security/configuring-mtls)
- [Cloud Service Mesh authorization policy](https://docs.cloud.google.com/service-mesh/docs/security/authorization-policy-overview)
- [Cloud Service Mesh observability overview](https://docs.cloud.google.com/service-mesh/docs/observability-overview)
- [Cloud Service Mesh release notes](https://docs.cloud.google.com/service-mesh/docs/release-notes)
- [Architecture: GKE Gateway and Cloud Service Mesh](https://docs.cloud.google.com/architecture/build-apps-using-gateway-and-cloud-service)
