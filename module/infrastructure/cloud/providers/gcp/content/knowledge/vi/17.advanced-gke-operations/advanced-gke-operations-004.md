# Network policies và phân đoạn lưu lượng Pod trong GKE

Một doanh nghiệp thương mại điện tử vận hành các dịch vụ `storefront`, `orders-api` và worker thanh toán trong **Google Kubernetes Engine (GKE)**. Frontend cần gọi API đơn hàng, API cần kết nối **Cloud SQL**, còn worker thanh toán phải liên hệ một số dịch vụ nhất định. Nếu toàn bộ Pod trong cluster mặc nhiên kết nối được với nhau, một container bị xâm nhập có thể thử quét cổng, truy cập dịch vụ không liên quan hoặc di chuyển ngang sang namespace khác.

**Kubernetes NetworkPolicy** là cơ chế khai báo **Pod nào được phép nhận hoặc khởi tạo kết nối mạng** dựa trên tập chọn Pod/namespace, địa chỉ IP, giao thức và cổng. Trên GKE, chính sách này được thực thi bởi data plane/network policy provider tương thích. Sử dụng NetworkPolicy đúng giúp thiết kế **microsegmentation** ở tầng mạng, giới hạn phạm vi ảnh hưởng khi ứng dụng bị xâm nhập, tách môi trường hoặc dịch vụ và kiểm soát luồng egress.

Bài học thuộc chương **GKE nâng cao và vận hành** của mô-đun **CLOUD_PROVIDERS_GCP**. Nội dung kết nối kiến thức project/IAM/VPC, Compute Engine, GKE, Cloud Run, Cloud Storage, Cloud SQL và Artifact Registry với thiết kế bảo vệ tài nguyên, triển khai theo GitOps/CI/CD, quản lý độ tin cậy và theo dõi chi phí. Trọng tâm là **phân đoạn lưu lượng Pod bằng NetworkPolicy trong GKE**, không thay thế toàn bộ kiến trúc bảo mật mạng của Google Cloud.

## 1. Mục tiêu học tập và phạm vi

Sau bài này, người học có thể:

1. Giải thích **ingress**, **egress**, **isolation** và nguyên tắc allow-list của Kubernetes NetworkPolicy.
2. Hiểu chính xác `podSelector`, `namespaceSelector`, `ipBlock`, `policyTypes`, `ports` và quy tắc hợp nhất nhiều policy.
3. Phân biệt engine **Calico network policy** với **GKE Dataplane V2**, cũng như các ràng buộc khi triển khai trên Standard/Autopilot.
4. Thiết kế mô hình **default-deny → allow đúng luồng** cho frontend, API, database và DNS.
5. Phân biệt NetworkPolicy với **VPC firewall**, **IAM**, **Kubernetes RBAC**, **Cloud Armor**, **Service mesh authorization** và chính sách egress nâng cao.
6. Viết manifest, áp dụng từng bước, tạo kiểm thử allow/deny và xử lý lỗi không làm ngắt dịch vụ production.
7. Giám sát, kiểm toán, rollback và đo tác động về bảo mật, độ tin cậy, vận hành.

**Quy ước ví dụ:** tên namespace, service, IP, project và region chỉ phục vụ học tập. Các lệnh có `apply`, `create`, `label` hoặc `delete` **làm thay đổi tài nguyên thật**; chỉ chạy trong cluster lab được phép. Một số tính năng phụ thuộc GKE release channel, phiên bản, loại cluster và data plane hiện hành; cần đối chiếu tài liệu chính thức khi triển khai.

## 2. Vì sao cần phân đoạn mạng giữa các Pod?

### 2.1. Kết nối mặc định không phải biên giới bảo mật

Trong Kubernetes, khi **không có policy nào cô lập một Pod**, lưu lượng Pod theo hướng tương ứng thường được phép ở tầng NetworkPolicy, dù vẫn có thể chịu các chính sách khác của mạng/ứng dụng. Mô hình này thuận tiện khi phát triển, nhưng có rủi ro:

- Pod bị chiếm quyền có thể kết nối thử tới các service khác mà người viết ứng dụng không chủ đích cho phép.
- Một service public ở namespace `web` có thể thăm dò backend nhạy cảm tại `payments`.
- Một batch worker cần đọc Cloud Storage nhưng lại có đường mạng tới hệ thống database không liên quan.
- Một nhóm triển khai sai cấu hình mạng có thể vô tình cho phép traffic không mong đợi giữa các tenant.

**Namespace không tự là một firewall.** Namespace giúp phân nhóm tài nguyên, cấu hình RBAC, quota và ownership; muốn hạn chế Pod-to-Pod traffic theo namespace cần cấu hình NetworkPolicy hoặc lớp mạng khác.

### 2.2. Ví dụ hệ thống trước và sau phân đoạn

~~~mermaid
flowchart LR
    W["storefront Pod"] --> A["orders-api Pod"]
    W -. "Kết nối không cần thiết" .-> D["postgres Pod trong lab"]
    A --> D
    P["payments-worker Pod"] -. "Kết nối trái mục đích" .-> W
~~~

Sau khi thiết lập chính sách, ta muốn:

~~~mermaid
flowchart LR
    W["storefront: retail-web"] -->|"TCP 8080"| A["orders-api: retail-api"]
    A -->|"TCP 5432"| D["postgres: retail-data"]
    P["payments-worker"] -. "Không được phép trực tiếp" .-> D
    W -. "Không được phép trực tiếp" .-> D
~~~

Các mũi tên thể hiện **ý định bảo mật**; cấu hình thực tế chỉ đúng khi cả policy ở nguồn/đích, namespace labels, Pod labels, data plane và luồng dịch vụ đều khớp. Không được mặc định sơ đồ trở thành hiện thực ngay khi đã tạo ba namespace.

### 2.3. Quy tắc “chỉ những luồng cần thiết”

Trước khi viết YAML, đội vận hành nên xây **traffic matrix**:

| Nguồn | Đích | Protocol/port | Lý do | Quyết định |
| --- | --- | --- | --- | --- |
| `storefront` trong `retail-web` | `orders-api` trong `retail-api` | TCP 8080 | Gửi yêu cầu đơn hàng. | Allow. |
| `orders-api` | PostgreSQL lab trong `retail-data` | TCP 5432 | Truy vấn dữ liệu đơn hàng. | Allow. |
| `storefront` | PostgreSQL lab | TCP 5432 | Không cần kết nối trực tiếp. | Deny. |
| `payments-worker` | `storefront` | TCP 8080 | Không thuộc luồng nghiệp vụ. | Deny. |
| Các Pod sử dụng DNS | DNS resolver được cluster cấu hình | UDP/TCP 53 hoặc cơ chế cụ thể | Phân giải service/API hostname. | Allow có kiểm soát. |
| `orders-api` production | Cloud SQL private endpoint | TCP 5432 nếu dùng PostgreSQL | Database nằm ngoài cluster. | Allow theo đích thực tế. |

**Không phải mọi traffic đều đi qua Pod:** Cloud SQL, Google APIs, load balancer proxy, control plane và kết nối node có đường mạng và cơ chế phân quyền riêng. Chính sách Pod chỉ là một lớp trong bức tranh đó.

## 3. Kubernetes NetworkPolicy hoạt động như thế nào?

### 3.1. Phạm vi namespace và tập Pod được chọn

Một NetworkPolicy là resource Kubernetes **nằm trong một namespace**. Trường `spec.podSelector` chọn **những Pod trong chính namespace đó** mà policy sẽ tác động tới.

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: api-ingress-example
  namespace: retail-api
spec:
  podSelector:
    matchLabels:
      app: orders-api
  policyTypes:
    - Ingress
  ingress: []
~~~

Policy này **cô lập ingress** của Pod có label `app=orders-api` trong namespace `retail-api`. Vì `ingress: []` không có quy tắc allow, các kết nối mới thuộc phạm vi ingress được thực thi sẽ bị chặn theo semantics NetworkPolicy. Policy trên **không tự cô lập egress** của chính Pod.

Nếu `podSelector: {}` thì policy chọn **mọi Pod trong namespace**; nó không chọn toàn bộ Pod ở tất cả namespaces trong cluster.

### 3.2. Ingress và egress là hai chiều độc lập

**Ingress:** kiểm soát traffic **đi vào** Pod đích được policy chọn.

**Egress:** kiểm soát traffic **đi ra từ** Pod nguồn được policy chọn.

Một Pod có thể:

- Bị cô lập ingress nhưng không bị cô lập egress.
- Bị cô lập egress nhưng không bị cô lập ingress.
- Bị cô lập cả hai chiều.
- Chưa bị cô lập chiều nào.

Để một kết nối **Pod A → Pod B** được phép khi cả hai phía đều có policy isolation, **egress tại A và ingress tại B đều phải cho phép**. Cho phép một phía không tự mở phía còn lại.

### 3.3. Policy là tập quy tắc cộng dồn

Kubernetes NetworkPolicy tiêu chuẩn có semantics **allow-list**:

1. Nếu chưa có policy nào chọn Pod theo một chiều, Pod không bị isolation từ NetworkPolicy theo chiều đó.
2. Khi có ít nhất một policy chọn Pod và cô lập chiều đó, chỉ những kết nối được **một hoặc nhiều policy cho phép** mới qua được.
3. Khi nhiều policies cùng chọn một Pod, tập lưu lượng được phép là **hợp của các quy tắc allow**.
4. **Không có thứ tự ưu tiên** giữa các NetworkPolicy tiêu chuẩn; không có hành động `deny` có độ ưu tiên cao hơn `allow` trong API `networking.k8s.io/v1` cơ bản.

Ví dụ một policy cho phép ingress TCP 8080 từ frontend và một policy khác cho phép TCP 9090 từ monitoring, thì Pod có thể nhận **cả hai luồng** khi phù hợp. Tạo thêm `default-deny` không ghi đè một policy allow đã tồn tại.

### 3.4. `policyTypes` và mặc định

`policyTypes` có thể chứa `Ingress`, `Egress` hoặc cả hai. Nếu không khai báo, Kubernetes mặc định thêm `Ingress`, và có thể thêm `Egress` khi có egress rules theo semantics API. Trong bài học này, mọi policy đều **khai báo `policyTypes` tường minh** để tránh hiểu nhầm.

| Trường | Ý nghĩa |
| --- | --- |
| `spec.podSelector` | Các Pod được policy kiểm soát trong namespace của policy. |
| `spec.policyTypes` | Những chiều ingress/egress được cô lập và xét quy tắc. |
| `spec.ingress` | Danh sách các quy tắc allow ingress; `[]` nghĩa là không thêm ngoại lệ allow. |
| `spec.egress` | Danh sách các quy tắc allow egress; `[]` nghĩa là không thêm ngoại lệ allow. |
| `from` / `to` | Peer hoặc CIDR được phép theo từng quy tắc. |
| `ports` | Protocol/cổng được phép; không khai báo có thể rộng hơn dự định. |

**Trả lời của kết nối đã được cho phép** thường được xử lý bằng cơ chế theo dõi trạng thái kết nối của dataplane; không cần tự viết quy tắc đảo chiều cho từng gói ACK/response. Tuy nhiên, mỗi **kết nối mới** từ phía ngược lại là vấn đề riêng và có thể bị chặn.

## 4. Đọc đúng `podSelector`, `namespaceSelector` và `ipBlock`

### 4.1. Pod selector trong cùng namespace

Ở trường peer `from`/`to`, một `podSelector` đứng riêng chọn những Pod trong **namespace của NetworkPolicy**. Ví dụ policy đặt ở `retail-api`:

~~~yaml
from:
  - podSelector:
      matchLabels:
        app: internal-client
~~~

Quy tắc này cho phép peer Pod `app=internal-client` **trong `retail-api`**, không tự cho phép Pod trùng label tại `retail-web`.

### 4.2. Namespace selector

~~~yaml
from:
  - namespaceSelector:
      matchLabels:
        access-zone: web
~~~

Quy tắc trên chọn **tất cả Pods thuộc các namespace có label `access-zone=web`** nếu các điều kiện khác của rule khớp. Nếu namespace label có thể do người dùng tùy ý thay đổi, họ có thể đưa một namespace vào phạm vi được allow; vì vậy phải **kiểm soát RBAC quyền sửa Namespace labels**.

### 4.3. AND trong một peer, OR giữa hai peers

Đây là lỗi YAML rất phổ biến. Cách viết **một phần tử** có cả `namespaceSelector` và `podSelector` nghĩa là **AND**:

~~~yaml
from:
  - namespaceSelector:
      matchLabels:
        access-zone: web
    podSelector:
      matchLabels:
        app: storefront
~~~

Chỉ Pod `app=storefront` **trong namespace có nhãn `access-zone=web`** khớp.

Ngược lại, **hai phần tử danh sách** nghĩa là **OR**:

~~~yaml
from:
  - namespaceSelector:
      matchLabels:
        access-zone: web
  - podSelector:
      matchLabels:
        app: storefront
~~~

Quy tắc thứ hai cho phép các Pod `app=storefront` **trong namespace của policy**; quy tắc thứ nhất cho phép **mọi Pod của các namespace `access-zone=web`**. Đây là tập rộng hơn đáng kể. **Thụt lề và dấu `-` có thể làm thay đổi biên giới bảo mật.**

### 4.4. `ipBlock` dành cho địa chỉ IP/CIDR

~~~yaml
to:
  - ipBlock:
      cidr: 10.70.0.0/24
      except:
        - 10.70.0.128/25
~~~

`ipBlock` biểu diễn mạng IP được phép, trừ một số dải con với `except`. Nó phù hợp khi **đích là mạng ngoài tập Pod** có địa chỉ ổn định và semantics data plane hỗ trợ. Với lưu lượng qua Kubernetes Service, việc DNAT/SNAT trước hoặc sau khi kiểm tra policy có thể ảnh hưởng đến IP được thấy; **không dựa vào `ipBlock` một cách mù quáng để chọn Pod**.

Đặc biệt trên **GKE Dataplane V2**, `ipBlock` **không được dùng để chọn Pod IP** theo cơ chế của sản phẩm; hãy dùng `podSelector` và `namespaceSelector` cho lưu lượng Pod-to-Pod. Nếu muốn giới hạn Google APIs/cloud service theo IP, cần tính cả DNS, NAT, private endpoints và thay đổi IP; đôi khi một giải pháp egress chuyên dụng phù hợp hơn.

### 4.5. Rule `ports`, `from` và `to`

Trong một ingress rule, danh sách peers (`from`) và danh sách ports (`ports`) được kết hợp để xác định tập traffic được phép. Nếu có nhiều phần tử trong danh sách peers hoặc ports, các phần tử đó là các lựa chọn **OR** tương ứng. Một ví dụ:

~~~yaml
ingress:
  - from:
      - podSelector:
          matchLabels:
            app: metrics-scraper
    ports:
      - protocol: TCP
        port: 9090
~~~

Nghĩa là cho phép Pod `app=metrics-scraper` trong cùng namespace đi vào Pod được chọn ở TCP 9090. Các thông số `endPort` hoặc named ports có thể hữu ích ở các môi trường được hỗ trợ, nhưng **không thay thế việc xác định cổng thật mà ứng dụng lắng nghe**.

**Cẩn thận với quy tắc allow rỗng:** một phần tử `ingress` đã tồn tại mà **bỏ `from` hoặc dùng `from: []`** không giới hạn nguồn, nên có thể cho phép mọi nguồn tới những cổng của rule. Tương tự, bỏ `ports` có thể mở cho mọi cổng. Điều này khác với **`ingress: []`** ở cấp `spec`, nghĩa là không có rule allow ingress nào trong policy.

### 4.6. Một số giới hạn của NetworkPolicy tiêu chuẩn

Kubernetes NetworkPolicy tiêu chuẩn hoạt động chủ yếu ở **L3/L4**:

- Không phân biệt HTTP `GET /orders` với `POST /payments` chỉ bằng NetworkPolicy.
- Không hiểu OAuth user, JWT claims hoặc Kubernetes RBAC.
- Không tự giải quyết TLS, chứng chỉ mTLS hoặc xác thực database.
- Không có trường FQDN/hostname đích trong API NetworkPolicy tiêu chuẩn.
- Không tự chặn tài nguyên Google Cloud API chỉ dựa vào service account.
- Không nhất thiết quản lý giống nhau lưu lượng từ **host network**, node hoặc control plane; phải kiểm tra hành vi thực tế của dataplane.

Khi cần L7 authorization, service identity, FQDN-aware egress hoặc kiểm soát tới external services, đánh giá **GKE Dataplane V2 extensions**, service mesh, egress gateway/proxy, IAM và firewall theo yêu cầu; không tự coi các tính năng nâng cao là một phần của YAML `networking.k8s.io/v1`.

## 5. GKE thực thi NetworkPolicy bằng cơ chế nào?

### 5.1. Kubernetes API cần một enforcement provider

Kubernetes API server có thể lưu đối tượng `NetworkPolicy`, nhưng **có đối tượng không đồng nghĩa policy được enforcement** nếu data plane/CNI không hỗ trợ hoặc chưa bật tính năng tương ứng.

Trên GKE, hai hướng kiến trúc thường được nhắc tới:

| Mô hình | Cách thực thi | Điểm vận hành cần chú ý |
| --- | --- | --- |
| **GKE Standard dùng legacy Network Policy/Calico** | Tính năng network policy được cấu hình trên cluster/node pools theo cơ chế hỗ trợ. | Bật sau khi cluster chạy có thể làm thay đổi/recreate node pools; kiểm tra maintenance window và tác động Pod. |
| **GKE Dataplane V2** | Data plane eBPF của GKE thực thi Kubernetes NetworkPolicy như một khả năng tích hợp. | Có khác biệt về IPBlock/Pod IP và công cụ quan sát; không áp lệnh/cơ chế bật Calico riêng vào cluster Dataplane V2. |

Với **GKE Autopilot**, nhiều lựa chọn data plane/networking do GKE quản lý; việc khai báo và thử NetworkPolicy vẫn cần được kiểm chứng theo chế độ cluster hiện hành. Không giả định Autopilot cho phép chỉnh sửa node-level CNI hoặc cài Calico như một Standard cluster tự quản.

### 5.2. Dataplane V2 không phải Calico cộng thêm

**GKE Dataplane V2** là lựa chọn data plane có khả năng enforcement và quan sát riêng. Nếu cluster dùng Dataplane V2, không nên chạy các bước “bật Calico network policy” dành cho chế độ cũ. Các giới hạn và semantics của implementation cần được xem trong tài liệu theo đúng release channel/version.

Tương tự, không cài thêm một CNI hay daemonset can thiệp dataplane chỉ vì thấy file NetworkPolicy chưa hoạt động. Việc thay networking engine có thể ảnh hưởng toàn cluster và đòi hỏi quy trình migration riêng.

### 5.3. Kiểm tra cấu hình bằng gcloud

~~~bash
PROJECT_ID="retail-lab"
REGION="asia-southeast1"
CLUSTER="retail-gke"

# READ-ONLY: xác định đúng cluster và chế độ data plane.
gcloud container clusters describe "$CLUSTER" \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --format=yaml
~~~

Trong kết quả có thể có các trường như `networkPolicy`, `datapathProvider`, `networkConfig` hoặc thông tin tương ứng tùy schema/version. Đối chiếu chúng với **loại GKE cluster** và tài liệu đang hiệu lực. `kubectl get networkpolicy` chỉ chứng minh đã lưu policy; muốn chứng minh enforcement phải **thử kết nối allow và deny thực tế**.

### 5.4. Cân nhắc khi bật trên cluster đang chạy

Nếu là Standard cluster chưa được cấu hình network policy enforcement:

1. Kiểm kê Pod/workload, ứng dụng critical, maintenance window và PodDisruptionBudget.
2. Xác định cơ chế Calico hoặc Dataplane V2 nào thực sự được hỗ trợ ở cluster hiện tại.
3. Đọc hướng dẫn bật tính năng, các yêu cầu node recreation, version và khả năng rollback.
4. Thử thay đổi trong môi trường nonproduction tương tự, với cả lưu lượng cho phép và bị chặn.
5. Lên phương án bảo vệ SLO trước khi bật enforcement hoặc áp default-deny trên production.

**Không tự kết luận chỉ thêm YAML `NetworkPolicy` là đủ** khi engine chưa hỗ trợ; nhưng cũng không được bật network policy bằng một lệnh cluster-wide trong production mà chưa đánh giá node disruptions.

## 6. Chuẩn bị phòng lab: namespaces, labels và workload

### 6.1. Bối cảnh ba tầng

Ta dùng ba namespace:

~~~text
retail-web
  Pod: app=storefront
  Service: storefront

retail-api
  Pod: app=orders-api
  Service: orders-api (TCP 8080)

retail-data
  Pod: app=postgres (lab-only)
  Service: postgres (TCP 5432)
~~~

Trong production, Cloud SQL nên được cân nhắc thay cho database Pod tự quản khi phù hợp yêu cầu, nhưng ở đây dùng PostgreSQL lab trong cluster để minh họa **quy tắc Pod-to-Pod**. Sau đó có ví dụ egress **tới Cloud SQL private IP bên ngoài cluster**.

### 6.2. Tạo và gắn nhãn namespace

Những lệnh sau **thay đổi Kubernetes cluster**:

~~~bash
# WRITE: chỉ thực hiện ở cluster lab đã chọn đúng context.
kubectl create namespace retail-web
kubectl create namespace retail-api
kubectl create namespace retail-data

# WRITE: nhãn namespace dùng cho NetworkPolicy selectors.
kubectl label namespace retail-web access-zone=web --overwrite
kubectl label namespace retail-api access-zone=api --overwrite
kubectl label namespace retail-data access-zone=data --overwrite

# READ-ONLY: kiểm chứng namespace labels.
kubectl get namespaces --show-labels
~~~

Lệnh tạo namespace sẽ báo `AlreadyExists` nếu chạy lại trên tài nguyên có sẵn. Khi áp dụng trong hệ thống đã có namespace, đừng “sửa nhanh” label đang được dùng bởi admission policies, CI/CD hoặc các NetworkPolicies khác mà không kiểm tra tác động. **Quyền sửa label namespace cần được hạn chế**, vì một label có thể mở ra đường traffic mới.

### 6.3. Kiểm tra labels ở Pod đích

~~~bash
# READ-ONLY: xác nhận selector thực sự khớp các Pod nào.
kubectl -n retail-web get pods --show-labels
kubectl -n retail-api get pods --show-labels
kubectl -n retail-data get pods --show-labels

# READ-ONLY: Service endpoints trỏ tới đâu?
kubectl -n retail-api get service orders-api
kubectl -n retail-api get endpointslices \
  -l kubernetes.io/service-name=orders-api
~~~

**NetworkPolicy chọn Pod bằng labels**, không chọn Kubernetes Service bằng tên. Một Service có tên `orders-api` nhưng chọn Pod `app=order-worker` sẽ không tự khớp với policy chọn `app=orders-api`. Trong troubleshooting phải so khớp **cả Service selector và NetworkPolicy podSelector**.

## 7. Bắt đầu bằng default-deny

### 7.1. Default-deny ingress ở một namespace

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: default-deny-ingress
  namespace: retail-api
spec:
  podSelector: {}
  policyTypes:
    - Ingress
  ingress: []
~~~

Policy chọn toàn bộ Pod trong `retail-api` và cô lập ingress. **Egress vẫn chưa bị cô lập** bởi policy này. Nếu cần một giai đoạn áp dụng ít rủi ro, đội vận hành có thể bắt đầu từ ingress và thêm các ngoại lệ thật cần thiết trước khi cô lập egress.

### 7.2. Default-deny cả ingress và egress

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: default-deny-all
  namespace: retail-api
spec:
  podSelector: {}
  policyTypes:
    - Ingress
    - Egress
  ingress: []
  egress: []
~~~

Đây là **baseline isolation**. Sau khi nó có hiệu lực, những Pod được chọn sẽ không có quy tắc allow mới ở hai chiều, trừ khi **policy khác** cấp. Tuy nhiên cần hiểu:

- Policies là **additive**: default-deny không xóa bỏ allow đã tồn tại.
- Các lưu lượng từ node/host hoặc thành phần hệ thống có semantics phụ thuộc implementation; không khẳng định policy chặn mọi packet trong toàn bộ VPC.
- Một ứng dụng có thể cần DNS, metrics, tracing, registry/Google APIs, database và webhooks; bật deny toàn bộ trước khi thêm ngoại lệ có thể làm gián đoạn production.

### 7.3. Có cần tạo policy cho từng namespace?

Policy có phạm vi namespace, vì vậy `default-deny-all` trong `retail-api` **không tự cô lập `retail-web` hay `retail-data`**. Để áp cùng chính sách cho nhiều namespace, dùng GitOps/Helm/Kustomize hoặc mẫu IaC quản lý nhiều `NetworkPolicy` riêng và bảo đảm ownership rõ ràng.

Kubernetes NetworkPolicy tiêu chuẩn **không phải một resource cluster-scoped để đặt default-deny toàn cluster chỉ với một đối tượng**. Một số giải pháp bổ sung có policy cấp cluster, nhưng phải xác định implementation và bảo đảm chúng không bị hiểu nhầm với API tiêu chuẩn.

## 8. Cho phép DNS sau khi cô lập egress

### 8.1. Vì sao DNS thường là luồng đầu tiên bị quên?

Pod thường gọi service qua tên như `orders-api.retail-api.svc.cluster.local` hoặc gọi Google APIs bằng hostname. Khi egress bị cô lập và không có policy cho DNS, ứng dụng có thể báo:

~~~text
lookup orders-api.retail-api.svc.cluster.local: i/o timeout
Temporary failure in name resolution
connection timeout to external API
~~~

Người vận hành dễ kết luận API/database bị lỗi, trong khi vấn đề thực sự là Pod **không phân giải được DNS**.

### 8.2. Policy minh họa với kube-dns Pods

Trong một cluster dùng **kube-dns Pods** có labels phù hợp, policy có thể cho phép `orders-api` gửi truy vấn DNS tới những Pod đó:

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-dns-to-kube-dns
  namespace: retail-api
spec:
  podSelector:
    matchLabels:
      app: orders-api
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

**Đây là mẫu chỉ hợp lệ khi DNS resolver thực sự là các kube-dns Pods có labels đó.** Trước khi áp dụng:

~~~bash
# READ-ONLY: xem DNS implementation thực tế.
kubectl -n kube-system get pods --show-labels
kubectl -n kube-system get services
kubectl -n retail-api exec deploy/orders-api -- cat /etc/resolv.conf
~~~

Nếu cluster sử dụng **NodeLocal DNSCache, Cloud DNS for GKE hoặc resolver khác**, đường đi gói tin/địa chỉ đích có thể khác; policy chọn kube-dns Pods ở trên **có thể không đủ**. Cần dựa trên cluster DNS architecture và hướng dẫn GKE tương ứng. Lệnh `kubectl exec` đọc từ container đang chạy và đòi container có `cat`; nếu image tối giản không có shell, dùng debug Pod được phê duyệt.

### 8.3. Kiểm thử DNS

~~~bash
# READ-ONLY network probe: chỉ chạy trong Pod có công cụ hỗ trợ.
kubectl -n retail-api exec deploy/orders-api -- \
  nslookup orders-api.retail-api.svc.cluster.local
~~~

Nếu DNS thành công nhưng HTTP vẫn lỗi, hãy tiếp tục kiểm tra egress TCP 8080 từ nguồn và ingress TCP 8080 tại đích. **DNS resolution và quyền mở kết nối TCP là hai bước khác nhau.**

## 9. Cho phép frontend gọi API qua nhiều namespace

### 9.1. Policy ingress tại API

Đặt trong namespace `retail-api`; chỉ Pod `app=orders-api` nhận TCP 8080 từ Pod `app=storefront` thuộc namespace có label `access-zone=web`:

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: orders-api-allow-storefront
  namespace: retail-api
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
              access-zone: web
          podSelector:
            matchLabels:
              app: storefront
      ports:
        - protocol: TCP
          port: 8080
~~~

Lưu ý đây là **một peer có cả hai selectors** nên điều kiện là AND. Không viết chúng thành hai phần tử `-` vì sẽ mở rộng phạm vi.

### 9.2. Policy egress ở frontend

Nếu `retail-web` đã có default-deny egress, cần cho phép nguồn `storefront` đi tới `orders-api`:

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: storefront-egress-orders
  namespace: retail-web
spec:
  podSelector:
    matchLabels:
      app: storefront
  policyTypes:
    - Egress
  egress:
    - to:
        - namespaceSelector:
            matchLabels:
              access-zone: api
          podSelector:
            matchLabels:
              app: orders-api
      ports:
        - protocol: TCP
          port: 8080
~~~

Nếu chưa cô lập egress ở `retail-web`, policy egress này **làm cô lập egress của những Pod `app=storefront`** và chỉ cho phép luồng được liệt kê trong tổng các policy. Vì thế, **không áp dụng riêng lẻ policy này ở production** mà quên DNS, metrics, outbound APIs hay các dịch vụ khác mà storefront cần. Mô hình nên được triển khai thành **bộ policy hoàn chỉnh** trong cùng kế hoạch rollout.

### 9.3. Cách đọc kết quả

| Traffic | Có được phép nếu default-deny tương ứng đã bật? | Điều kiện |
| --- | --- | --- |
| `storefront` → `orders-api:8080` | Có, khi cả hai policy trên và labels khớp. | Nguồn egress + đích ingress cùng allow. |
| `storefront` → `orders-api:9090` | Không, nếu không có policy allow nào khác. | Port 9090 không được liệt kê. |
| `random-pod` trong `retail-web` → `orders-api:8080` | Không, nếu đích bị isolation. | Không khớp `app=storefront`. |
| `storefront` → `postgres:5432` | Không, nếu Postgres đích cũng có ingress isolation và không có allow khác. | Không có đường allow cho luồng đó. |
| `orders-api` → Internet | Tùy các policy egress khác chọn Pod. | Policy ingress không quyết định egress. |

Một lưu lượng được cho phép theo NetworkPolicy vẫn có thể thất bại vì **Kubernetes Service selector**, Pod readiness, VPC firewall, ứng dụng không lắng nghe cổng hoặc authorization ở lớp trên.

## 10. Cho phép API kết nối database trong cluster

### 10.1. Phía nguồn: egress tại `retail-api`

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: orders-egress-postgres
  namespace: retail-api
spec:
  podSelector:
    matchLabels:
      app: orders-api
  policyTypes:
    - Egress
  egress:
    - to:
        - namespaceSelector:
            matchLabels:
              access-zone: data
          podSelector:
            matchLabels:
              app: postgres
      ports:
        - protocol: TCP
          port: 5432
~~~

### 10.2. Phía đích: ingress tại `retail-data`

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: postgres-allow-orders-api
  namespace: retail-data
spec:
  podSelector:
    matchLabels:
      app: postgres
  policyTypes:
    - Ingress
  ingress:
    - from:
        - namespaceSelector:
            matchLabels:
              access-zone: api
          podSelector:
            matchLabels:
              app: orders-api
      ports:
        - protocol: TCP
          port: 5432
~~~

Nếu database Pod được bảo vệ bằng policy ingress, **Policy egress phía API và ingress phía database đều quan trọng**. Việc dùng Service `postgres.retail-data.svc.cluster.local:5432` không thay thế cho việc chính sách phải khớp với **Pod endpoint đích**.

**Cần thêm database authentication và least-privilege SQL roles.** NetworkPolicy chỉ giới hạn **đường TCP**, không biết user SQL nào được chạy `DROP TABLE`.

### 10.3. Database Pod chỉ là ví dụ lab

Trong production, database có thể chạy bên ngoài cluster trên **Cloud SQL**. Khi đó `podSelector: app=postgres` ở `retail-data` sẽ **không chọn được Cloud SQL**; phải thiết kế luồng egress đến private endpoint, proxy hoặc kiến trúc kết nối thật. Phần tiếp theo mô tả khác biệt đó.

## 11. Egress tới Cloud SQL, Google APIs và các đích bên ngoài

### 11.1. Cloud SQL private IP không phải Pod

Giả sử Cloud SQL for PostgreSQL có private IP minh họa `10.70.4.12` trong mạng có định tuyến phù hợp. Nếu `orders-api` cần kết nối trực tiếp TCP 5432 và data plane hỗ trợ hành vi địa chỉ đó, policy egress có thể dùng `ipBlock`:

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: orders-egress-cloudsql
  namespace: retail-api
spec:
  podSelector:
    matchLabels:
      app: orders-api
  policyTypes:
    - Egress
  egress:
    - to:
        - ipBlock:
            cidr: 10.70.4.12/32
      ports:
        - protocol: TCP
          port: 5432
~~~

Đây là **ví dụ địa chỉ IP**, không phải hướng dẫn dùng IP cứng trong mọi hệ thống. Cần kiểm tra:

- Cloud SQL dùng **Private Service Access**, **Private Service Connect** hay phương án kết nối nào?
- Địa chỉ backend thực tế có ổn định không và đã có route/peering/DNS phù hợp chưa?
- Workload kết nối **trực tiếp** hay qua Cloud SQL Auth Proxy/connector? Proxy/connector có thể gọi thêm Google APIs cần TCP 443 và DNS.
- IAM/Cloud SQL Client role, database credentials và TLS được cấu hình như thế nào?
- Có chính sách egress của namespace, VPC firewall hoặc VPC Service Controls ảnh hưởng tới đường đi không?

Một NetworkPolicy không tự cấp phép IAM và không tự thiết lập VPC peering hoặc Private Service Connect.

### 11.2. Google APIs và Artifact Registry

`orders-api` có thể gọi Cloud Storage hoặc Pub/Sub qua Google APIs. Node GKE còn cần kết nối tới Artifact Registry để pull image. Cần **phân biệt nơi phát sinh kết nối**:

| Luồng | Ai thực sự khởi tạo? | NetworkPolicy có ý nghĩa ra sao? |
| --- | --- | --- |
| Pod gọi Cloud Storage REST API | Pod/application hoặc proxy do Pod chạy. | Pod egress policy có thể cần cho phép DNS/TCP 443 theo topology. |
| Pod gọi Cloud SQL Auth Proxy sidecar | Pod/sidecar. | Egress theo địa chỉ/port proxy thực sự dùng, kể cả Google APIs nếu có. |
| Node kéo image từ Artifact Registry | Node runtime/kubelet theo kiến trúc. | Không coi policy của app Pod là cách cấp quyền image pull cho node. |
| Frontend Application LB tới Pod NEG | Hạ tầng LB/proxy/health checker tới backend. | Cần xét ingress Pod và khả năng LB/health checker thực sự được phép; phụ thuộc mô hình mạng. |
| Pod gọi API Kubernetes | Pod tới API server endpoint. | Có thể chịu policy egress theo đường đi, nhưng vẫn cần Kubernetes RBAC/IAM. |

Không nên cho phép `0.0.0.0/0:443` một cách mặc định chỉ vì ứng dụng cần Google APIs. Nếu phải áp rule tạm trong migration, ghi nhận ngoại lệ, phân tích luồng và thu hẹp bằng mô hình **Private Google Access/restricted endpoint, egress gateway, firewall hoặc FQDN-aware policy** được hỗ trợ.

### 11.3. FQDN và thay đổi IP

NetworkPolicy tiêu chuẩn **không có** selector kiểu:

~~~text
allow egress to api.example.com on TCP 443
~~~

Với dịch vụ Internet có IP thay đổi, một `ipBlock` tĩnh có thể không ổn định. GKE có những tính năng kiểm soát lưu lượng FQDN nâng cao trong điều kiện Dataplane V2/phiên bản hỗ trợ; nhưng **không viết YAML FQDN như thể đó là API NetworkPolicy chuẩn**. Cần xem tài liệu GKE FQDN Network Policies, giới hạn DNS caching và khả năng enforcement trước khi dùng.

### 11.4. Cloud NAT và VPC firewall vẫn có vai trò

NetworkPolicy kiểm soát traffic Pod ở data plane, còn **VPC firewall** quản lý những luồng mạng theo mô hình VM/node, endpoint, network tags/service accounts và policy hierarchy. **Cloud NAT** hỗ trợ outbound SNAT khi có cấu hình phù hợp, không phải một allow-list per-Pod.

Ví dụ Pod cần Internet:

~~~text
Pod egress allowed by NetworkPolicy
       ↓
VPC route + egress firewall/policy
       ↓
Cloud NAT/proxy (nếu cần)
       ↓
External API
~~~

Nếu bất kỳ lớp nào chặn, kết nối vẫn thất bại. Một policy Kubernetes allow không phải lệnh mở firewall hay tạo NAT.

## 12. Luồng từ Ingress/Gateway và health check tới Pod

### 12.1. Đừng nhầm nguồn client và nguồn gói đến Pod

Khi một trình duyệt truy cập `https://shop.example.com`, đường đi có thể là:

~~~mermaid
flowchart LR
    C["Internet client"] --> LB["Application Load Balancer"]
    LB --> BS["Backend service"]
    BS --> NEG["GKE NEG / Pod endpoints"]
    NEG --> P["storefront Pod"]
    H["Health checker"] -. "Probe theo loại LB" .-> P
~~~

Pod có thể thấy nguồn traffic **khác client IP ban đầu** vì proxy hoặc NAT. Với GKE Ingress/Gateway và container-native load balancing, cần xác định backend là **Pod NEG, node/NodePort hay backend dạng khác**. `namespaceSelector`/`podSelector` **không tự chọn được một Google Front End hoặc Envoy proxy bên ngoài cluster** như một Pod có label.

### 12.2. Allow ingress cho backend phục vụ từ LB

Muốn thiết kế policy cho Pod tiếp nhận traffic từ Application Load Balancer:

1. Xác định loại LB: **global/regional external**, **internal**, Gateway/Ingress implementation và GKE data plane.
2. Xác định backend flow: Pod IP trực tiếp, node, proxy-only subnet, health checker và các dải nguồn cần thiết.
3. Đọc hướng dẫn GKE về NetworkPolicy tương thích LB để biết traffic health check/proxy có nằm trong phạm vi enforcement nào.
4. Chỉ viết `ipBlock` nguồn sau khi xác nhận nguồn IP quan sát và các giới hạn IP/NAT của loại LB.
5. Thử **request người dùng và health check** sau thay đổi; đừng chỉ thử `curl` từ một Pod bên trong cluster.

Nếu đặt `default-deny-ingress` cho `storefront` mà không cho phép đúng luồng LB, có thể khiến backend bị đánh dấu unhealthy hoặc request thất bại. **Không mở `0.0.0.0/0` tới toàn bộ Pod chỉ để health check xanh** khi yêu cầu bảo mật đòi hỏi phạm vi hẹp hơn.

### 12.3. Phân biệt ingress policy và application authorization

Ngay cả khi ingress policy chỉ cho phép nguồn proxy, **bất kỳ người dùng Internet nào đi qua proxy** vẫn có thể yêu cầu API nếu frontend công khai và app không xác thực. Đối với public endpoints, xem xét HTTPS, OAuth/JWT, Cloud Armor, IAP (khi phù hợp), rate limiting và authorization trong ứng dụng.

**NetworkPolicy không thay thế Web Application Firewall hay kiểm tra quyền đọc đơn hàng.**

## 13. Kiểm tra NetworkPolicy trước và sau khi áp dụng

### 13.1. Xem đúng cluster và quyền

~~~bash
# READ-ONLY: context hiện tại, không nhầm production với lab.
kubectl config current-context
kubectl get namespaces --show-labels

# READ-ONLY: kiểm tra người dùng có được phép tạo policy không.
kubectl auth can-i create networkpolicies.networking.k8s.io \
  -n retail-api

# READ-ONLY: liệt kê policies hiện có.
kubectl get networkpolicies -A
~~~

Khi `kubectl get networkpolicy` báo Forbidden, đó là vấn đề Kubernetes authorization, **không phải bằng chứng dataplane đã chặn lưu lượng**.

### 13.2. Review YAML trước khi triển khai

Giả sử đã lưu các manifest trong Git/IaC được duyệt:

~~~bash
# READ-ONLY validation phía API server; không lưu policy mới.
kubectl apply --dry-run=server -f network-policies/ \
  --namespace=retail-api

# WRITE: chỉ thực hiện sau khi duyệt những thay đổi và namespace.
kubectl apply -f network-policies/
~~~

Lưu ý: `metadata.namespace` trong từng file ưu tiên theo cách áp dụng tài nguyên, nên **không trông chờ `--namespace` sửa được manifest đã khai báo sai namespace**. `--dry-run=server` kiểm tra schema/quyền/admission trên API server trong phạm vi cho phép, **không kiểm chứng ý nghĩa selectors, connectivity hoặc SLO**.

### 13.3. Đọc policy thực tế

~~~bash
# READ-ONLY: kiểm tra policy mà API server đã lưu.
kubectl -n retail-api get networkpolicy
kubectl -n retail-api describe networkpolicy orders-api-allow-storefront
kubectl -n retail-api get networkpolicy \
  orders-api-allow-storefront -o yaml

# READ-ONLY: kiểm tra Pod labels/Service endpoints.
kubectl -n retail-api get pods --show-labels
kubectl -n retail-api get endpointslices
~~~

Nếu policy trông đúng nhưng vẫn không có tác dụng, cần xác minh **GKE policy enforcement provider** bằng cluster config và chạy network probes. Không kết luận chỉ dựa vào lệnh `kubectl get`.

### 13.4. Ma trận thử allow và deny

Một bộ kiểm thử cần bao gồm cả **kết nối được phép** và **kết nối phải bị chặn**:

| Nguồn thử | Đích | Kỳ vọng | Mục đích |
| --- | --- | --- | --- |
| `storefront` | `orders-api:8080` | Thành công. | Allow chính của ứng dụng. |
| Pod bất kỳ không thuộc nhóm frontend | `orders-api:8080` | Thất bại khi API bị cô lập. | Chặn lateral movement. |
| `storefront` | `postgres:5432` | Thất bại khi DB bị cô lập. | Không đi tắt database. |
| `orders-api` | `postgres:5432` | Thành công. | Allow data tier. |
| `orders-api` | DNS resolver | Thành công. | Không phá phân giải service. |
| `orders-api` | External endpoint không được duyệt | Thất bại khi egress bị cô lập đúng. | Kiểm tra egress boundary. |
| Ingress/Gateway → storefront | HTTP cùng health check | Thành công theo kiến trúc. | Không phá luồng người dùng. |

Kết quả phụ thuộc **tập policies thực sự đã áp trên cả hai namespace**, engine, namespace labels và network topology. Nếu chưa cô lập DB ingress, lệnh thử `storefront→postgres` có thể thành công dù API có ingress policy đúng.

### 13.5. Cách tạo network probe trong lab

Nếu policy cho phép, một debug Pod có các công cụ `curl`, `nc` hoặc `nslookup` có thể thử:

~~~bash
# READ/CONNECT: thực thi từ Pod đã tồn tại và có curl.
kubectl -n retail-web exec deploy/storefront -- \
  curl -sS --connect-timeout 3 \
  http://orders-api.retail-api.svc.cluster.local:8080/healthz
~~~

Một số production images tối giản không có `curl`; khi đó dùng debug image được duyệt, ephemeral debug container hoặc công cụ quan sát mạng phù hợp. Nếu tạo **Pod thử nghiệm mới**, hãy gắn đúng labels: một Pod `debug=true` **không tự được cho phép bởi policy chỉ chọn `app=storefront`**. Đây chính là điều cần kiểm tra, không phải lỗi policy.

Không xem timeout là bằng chứng chắc chắn NetworkPolicy block. Có thể do DNS, Service selector, Pod readiness, port, VPC firewall hoặc ứng dụng.

## 14. An toàn khi rollout policy trong production

### 14.1. Tại sao default-deny triển khai vội có thể gây outage?

Một Service chạy ổn định thường có **nhiều luồng phụ thuộc hơn sơ đồ nghiệp vụ**:

- DNS.
- Metrics/Prometheus/OpenTelemetry collectors.
- Service mesh sidecars và control plane.
- Cloud SQL connector hoặc Auth Proxy.
- Cloud Storage, Pub/Sub, Secret Manager APIs.
- Webhook/admission, health checks từ load balancer.
- Log export, tracing hoặc license servers.

Áp `default-deny-all` trên namespace production mà chưa kiểm kê có thể làm **Pod vẫn Running/Ready nhưng giao dịch thật thất bại**. Một số probes là local nên không phát hiện lỗi khi kết nối downstream bị chặn.

### 14.2. Kế hoạch rollout từng bước

1. **Discover:** vẽ traffic matrix dựa trên kiến trúc, logs và quan sát lưu lượng hiện có.
2. **Classify:** đánh dấu luồng nghiệp vụ bắt buộc, luồng hạ tầng, luồng chỉ phục vụ debugging và luồng không mong muốn.
3. **Prepare:** tạo các policies allow có scope hẹp, review labels/namespaces/ports, xác minh enforcement.
4. **Test in staging:** áp cùng tập policy lên môi trường có workloads và network topology tương đồng.
5. **Canary:** chọn namespace hoặc nhóm Pod ít nhạy cảm trước; kiểm tra SLI và cả kiểm thử deny.
6. **Enforce default-deny:** áp theo từng namespace với lịch triển khai và đường rollback đã duyệt.
7. **Observe:** giám sát 5xx, p95/p99, DNS, DB connections, rejected flows nếu được hỗ trợ.
8. **Refine:** thu hẹp những ngoại lệ tạm, ghi ownership và cập nhật tài liệu traffic matrix.

Kubernetes NetworkPolicy tiêu chuẩn **không có chế độ audit-only chung**. Một số công cụ/dataplane khác có khả năng quan sát hoặc mô phỏng riêng; không giả định có thể “dry-run connectivity” chỉ từ `kubectl apply --dry-run=server`.

### 14.3. Rollback có kiểm soát

Khi một policy mới gây outage:

- Xác định policy/namespace vừa thay đổi và traffic cụ thể bị chặn.
- Nếu được phép, thêm một **allow rule hẹp** cho luồng bắt buộc thay vì xóa mọi phòng vệ.
- Nếu không thể phục hồi nhanh và có phê duyệt, rollback đúng commit/manifests vừa áp.
- Kiểm tra hệ thống không còn policy allow khác mở rộng ngoài chủ đích sau rollback.
- Lưu incident record: nguyên nhân, nhãn sai, port sai hay thiếu phụ thuộc.

**Không chạy `kubectl delete networkpolicy --all -A` như một cách sửa chung.** Hành động đó có thể mở toàn bộ Pod traffic và phá kiểm soát của các nhóm khác. Rollback nên nhắm đúng object do pipeline/nhóm sở hữu.

### 14.4. GitOps và chống drift

Các manifest NetworkPolicy phù hợp quản lý bằng GitOps/IaC:

~~~text
Git review → policy manifests → CI schema validation
    → staging connectivity tests → approval
    → production apply → telemetry/rollback
~~~

Định nghĩa nhóm nào sở hữu namespace labels, nhóm nào sở hữu network policies, ai được tạo RoleBinding hay policy rộng. Không nên để một công cụ GitOps và một controller khác liên tục ghi đè cùng resource.

## 15. NetworkPolicy khác những cơ chế bảo mật nào?

| Cơ chế | Phạm vi | Ví dụ việc nó giải quyết |
| --- | --- | --- |
| **Kubernetes NetworkPolicy** | Lưu lượng Pod L3/L4 theo selectors/IP/ports. | Chỉ cho `storefront` gọi `orders-api:8080`. |
| **VPC firewall / hierarchical policies** | Luồng mạng cấp VPC, VM, subnet và các mục tiêu hỗ trợ. | Hạn chế nguồn tới GKE nodes, proxy-only subnet hoặc database endpoints. |
| **Kubernetes RBAC** | Ai được gọi Kubernetes API để đọc/sửa resource. | Dev không được xóa `Deployment` hoặc `Secret`. |
| **Google Cloud IAM** | Quyền với Google Cloud resources/APIs, danh tính quản trị. | Worker không được đọc bucket hoặc sửa project IAM. |
| **Workload Identity Federation for GKE** | Danh tính Pod dùng gọi Google APIs. | Pod `orders-api` chỉ đọc Secret Manager secrets được duyệt. |
| **Cloud Armor / WAF** | Lớp HTTP(S)/edge tùy LB topology. | Chặn hoặc hạn chế requests độc hại từ Internet. |
| **Service mesh / mTLS / L7 authorization** | Xác thực và policy cấp ứng dụng/service. | Chỉ service có danh tính xác thực được gọi endpoint thanh toán. |
| **Private GKE control plane** | Đường quản trị Kubernetes API. | SRE chỉ quản trị qua endpoint/đường kết nối được phê duyệt. |
| **Cloud NAT / egress gateway** | Đường đi outbound và kiểm soát tập trung tùy kiến trúc. | Workload ra Internet qua điểm egress được kiểm soát. |

**Không nên dùng một cơ chế để diễn giải thay cơ chế khác.** NetworkPolicy cho phép TCP tới Cloud SQL không khiến Pod có quyền SQL; Kubernetes RBAC cho phép xem Pods không chứng minh HTTP ingress an toàn.

## 16. Quan sát traffic và chẩn đoán khi policy chặn sai

### 16.1. Dấu hiệu thường gặp

| Triệu chứng | Nguyên nhân có thể | Bước kiểm tra |
| --- | --- | --- |
| Pod gọi service bằng tên thất bại | DNS egress bị chặn, DNS resolver khác kỳ vọng. | `/etc/resolv.conf`, DNS implementation và policy TCP/UDP 53. |
| IP Pod đích trực tiếp thành công nhưng Service hostname lỗi | DNS hoặc Service selector/endpoint routing. | `nslookup`, `get svc`, `get endpointslices`. |
| `storefront` → `orders-api` timeout | Thiếu egress phía web, ingress phía API, label/port mismatch. | Cả hai namespace policies, Pod labels và port. |
| Một debug Pod bị chặn trong khi storefront được phép | Debug Pod không có nhãn `app=storefront`. | `kubectl get pods --show-labels`, policy selector. |
| Chỉ Pod ở một namespace kết nối được | Namespace label khác hoặc policies chỉ chọn namespace nhất định. | Labels và cấu trúc AND/OR trong peer. |
| API không kết nối Cloud SQL | Egress chưa mở, sai private IP, DNS/PSC/PSA/route, IAM/DB auth. | Policy, endpoint thực tế, Cloud SQL logs và network. |
| App trả 503 sau khi default-deny | Bị chặn dependency, readiness hoặc health checker. | SLI, backend health, logs, tracing và flow telemetry. |
| Tạo NetworkPolicy xong nhưng test deny vẫn connect | Engine không enforcement hoặc có allow policy khác/host traffic exception. | Cluster dataplane, list toàn bộ policy, source/dest thực tế. |
| `ipBlock` Pod IP không match trên Dataplane V2 | Cơ chế Dataplane V2 không dùng ipBlock cho Pod traffic. | Chuyển sang podSelector/namespaceSelector. |
| SRE không thể `kubectl` vào cluster | Control-plane endpoint/IAM/RBAC, không nhất thiết liên quan policy Pod. | Kiểm tra Kubernetes API reachability và quyền trước. |
| DNS khỏe nhưng HTTP liên tục lỗi `403` | Ứng dụng/IAM/mesh/WAF từ chối. | HTTP logs, token và authorization; không gán mọi lỗi cho NetworkPolicy. |
| Metrics mất sau áp policy | Collector hoặc exporter không còn đường ingress/egress. | Scrape targets, labels, namespace và ports. |

### 16.2. Quy trình chẩn đoán theo lớp

1. **Đúng cluster/context?** Tránh nhầm staging/prod.
2. **Engine có enforce không?** Đọc GKE dataplane/networkPolicy config, xác minh bằng phép thử deny có kiểm soát.
3. **Nguồn và đích là Pod nào?** Lấy Pod IP, namespace, labels, Service endpoints và cổng ứng dụng.
4. **Chiều nào đang cô lập?** Liệt kê mọi policies chọn nguồn (egress) và đích (ingress).
5. **Peer selectors có khớp không?** Kiểm tra AND/OR, namespace label và pod label.
6. **Có phải DNS/IP/NAT không?** Phân giải tên, xác định IP thật, Google APIs/PSC/Cloud SQL và service routing.
7. **Lớp bên ngoài NetworkPolicy có chặn không?** VPC firewall, proxy, NetworkPolicy extensions, service mesh, IAM và ứng dụng.
8. **Đã phục hồi SLI chưa?** Xác nhận request end-to-end, không dừng ở kết quả ping/curl đơn lẻ.

### 16.3. Bộ lệnh đọc để kiểm tra

~~~bash
# READ-ONLY: xác nhận nguồn và đích.
kubectl -n retail-web get pods -o wide --show-labels
kubectl -n retail-api get pods -o wide --show-labels
kubectl -n retail-data get pods -o wide --show-labels

# READ-ONLY: tất cả policies trong cả cluster.
kubectl get networkpolicies -A
kubectl -n retail-api describe networkpolicy

# READ-ONLY: endpoints phía Service.
kubectl -n retail-api get services
kubectl -n retail-api get endpointslices
~~~

Trên cluster GKE Dataplane V2, có thể sử dụng **Network Policy Logging/observability** và các công cụ chẩn đoán được GKE cung cấp khi tính năng tương ứng được bật/hỗ trợ. Đừng hứa rằng mọi gói bị chặn đều được ghi log mặc định; log volume, sampling, retention và chi phí cần cấu hình rõ.

### 16.4. Một số vấn đề kiểm tra nâng cao

**Pod dùng `hostNetwork`:** hành vi policy có thể khác Pod thông thường; đánh giá theo CNI/dataplane cụ thể. Không dùng hostNetwork như cách bypass có chủ đích trong workload production.

**Service DNAT/SNAT:** địa chỉ mà network policy thấy có thể bị ảnh hưởng bởi implementation và thứ tự xử lý, đặc biệt với NodePort/LoadBalancer, traffic ngoài cluster hoặc một số egress. Hãy thử với đường mạng thật thay vì chỉ suy từ ClusterIP.

**Quyền thay Pod labels:** người có thể tự gắn nhãn `app=storefront` có thể làm Pod lọt vào tập được allow. NetworkPolicy là thành phần của mô hình **multi-tenant**, nhưng không thay thế RBAC/admission policy kiểm soát ai được triển khai Pod và sửa labels.

**Nhiều policies:** một policy tưởng như hẹp có thể bị mở rộng bởi policy khác, vì tập allow là phép hợp. Khi audit một Pod, phải xem **tất cả NetworkPolicies chọn Pod theo chiều liên quan**, không chỉ policy có tên `default-deny`.

## 17. Tình huống production: phân đoạn một hệ thống bán hàng

### 17.1. Bối cảnh

Một doanh nghiệp chạy:

- Namespace `retail-web`: `storefront`, được người dùng truy cập qua Application Load Balancer.
- Namespace `retail-api`: `orders-api` giao tiếp với **Cloud SQL for PostgreSQL**.
- Namespace `retail-batch`: worker xử lý ảnh, đọc/ghi **Cloud Storage** và nhận job từ Pub/Sub.
- Namespace `retail-observability`: collector metrics/traces.
- **Artifact Registry** cung cấp image cho GKE node pools.
- **Cloud Run** chạy một số API ngoài cluster và gọi `orders-api` qua gateway được phê duyệt.

Yêu cầu bảo mật: frontend không được truy cập database trực tiếp, worker ảnh không được gọi API thanh toán, chỉ collector được scrape metrics và các Pod chỉ được egress tới dịch vụ cần thiết. Yêu cầu độ tin cậy: trong đợt sale, không làm mất khả năng truy cập DNS, health check, Google APIs và dữ liệu.

### 17.2. Thiết kế theo luồng

~~~mermaid
flowchart TB
    USERS["Browser clients"] --> LB["HTTPS Application Load Balancer"]
    LB --> WEB["storefront Pods"]
    WEB -->|"HTTP 8080"| API["orders-api Pods"]
    API -->|"PostgreSQL 5432 qua mạng riêng"| SQL["Cloud SQL"]
    BATCH["Image workers"] -->|"HTTPS qua egress được duyệt"| STORE["Cloud Storage / Pub/Sub"]
    OBS["Telemetry collector"] -. "Metrics port được duyệt" .-> WEB
    OBS -.-> API
    API -. "Không có allow rule" .-> BATCH
    WEB -. "Không có allow rule" .-> SQL
~~~

Không vẽ mũi tên “NetworkPolicy chặn Cloud Run” một cách đơn giản: Cloud Run nằm ngoài cluster, luồng Cloud Run tới API còn phụ thuộc gateway/LB, nguồn IP thực tế, Kubernetes policy và authentication. Cần thiết kế đúng toàn tuyến, không suy từ label Pod của Cloud Run.

### 17.3. Kế hoạch theo ba giai đoạn

**Giai đoạn 1 — Phát hiện và kiểm chứng:**

1. Kiểm kê namespace/Pod/Service labels, Service endpoints và external dependencies.
2. Lập traffic matrix; thu thập logs hoặc telemetry mạng nếu có.
3. Đọc data plane GKE đang dùng, xác định đúng cách enforcement.
4. Thử chính sách với `retail-batch` trong staging, vì ít nhạy cảm hơn luồng checkout trực tiếp.

**Giai đoạn 2 — Áp isolation:**

1. Thêm policies allow cho DNS và các luồng cần thiết.
2. Cô lập ingress của `orders-api`, sau đó egress từ frontend.
3. Bổ sung egress Cloud SQL theo private endpoint thật, egress Google APIs/Pub/Sub theo topology và security policy.
4. Cô lập ingress/egress của batch workers, giữ một bảng ngoại lệ có owner và thời hạn.
5. Kiểm tra luồng Application LB/health check thực tế và route từ Cloud Run qua gateway.

**Giai đoạn 3 — Vận hành:**

1. Áp default-deny theo từng namespace khi đã có exception đầy đủ.
2. Thực hiện allow/deny connectivity tests trong CI/staging và synthetic checks production.
3. Theo dõi 5xx, p95 checkout, DB connection errors, DNS failures, Pub/Sub backlog và metric exporter.
4. Review policies sau thay đổi app topology, Service ports, node networking hoặc database endpoint.

### 17.4. Phân chia quyền và trách nhiệm

| Nhóm | Quyền nên có | Điều cần kiểm soát |
| --- | --- | --- |
| Platform/network | Quản lý GKE data plane, namespace policy baseline. | Không sửa CNI/node khi thiếu change window; review egress exceptions. |
| Application team | Đề xuất luồng app cần thiết và kiểm thử. | Không tự sửa namespace security labels hoặc tạo allow-all toàn cluster. |
| Security team | Audit policy drift, luồng không mong muốn. | Phê duyệt exception, giới hạn quyền sửa policy/RBAC. |
| CI/CD deployer | Áp những policy/manifests được duyệt ở namespace cho phép. | Không cần Owner toàn project; lưu audit trail và rollback commit. |
| SRE/on-call | Đọc logs/metrics, áp runbook khôi phục được duyệt. | Giải quyết outages mà không vô hiệu hóa mọi phòng vệ. |

Đối với GitOps, nên tách **người định nghĩa mong muốn** và **danh tính pipeline thực thi**; người có quyền cập nhật Namespace labels có thể thay đổi tập nguồn được phép mà không sửa trực tiếp NetworkPolicy.

### 17.5. Kịch bản kiểm thử sự cố

| Sự cố mô phỏng | Hành vi cần đạt |
| --- | --- |
| Pod ở `retail-batch` cố gọi PostgreSQL private endpoint | Bị chặn nếu không có allow theo namespace/pod/đích. |
| `orders-api` cố gọi hostname DNS sau default-deny | DNS vẫn hoạt động qua resolver được duyệt. |
| CI deploy version mới với nhãn Pod thay đổi | Policy được review/cập nhật; không im lặng chặn một service hợp lệ. |
| Một namespace bị gắn nhầm `access-zone=web` | Alert/review namespace label; không mở thêm Pod vào luồng nhạy cảm. |
| L7 backend vẫn Healthy nhưng checkout lỗi | Kiểm tra dependencies/egress và SLI, không dựa duy nhất LB health. |
| Collector metrics bị chặn | Khôi phục đúng metrics port/source, không mở toàn bộ ingress. |
| Cloud SQL chuyển cách kết nối | Cập nhật topology, route, IAM và network policy theo endpoint thật. |

## 18. Chi phí, giám sát và quản lý thay đổi

### 18.1. NetworkPolicy có tự tạo hóa đơn mới?

Kubernetes NetworkPolicy là một API chính sách. Chi phí hạ tầng GKE vẫn đến từ **nodes, cluster, networking, logging/telemetry và công cụ bảo mật bổ sung**; một số tính năng quan sát nâng cao có thể ảnh hưởng volume log hoặc chi phí vận hành. Không tự khẳng định một object NetworkPolicy có mức phí cố định hay miễn mọi chi phí liên quan ở mọi cấu hình.

Các yếu tố nên đo:

- Số lượng policy/namespace và chi phí vận hành/kiểm thử khi ứng dụng đổi topology.
- Network Policy Logging/flow telemetry: số lượng bản ghi, retention và cảnh báo.
- Ảnh hưởng latency/CPU trong data plane theo SLO khi quy mô chính sách lớn.
- Egress qua Cloud NAT, VPC data transfer hoặc gateway.
- Thời gian khắc phục sự cố do rule sai và tác động tới người dùng.

### 18.2. Quan sát bảo mật và SLI ứng dụng song song

| Nhóm tín hiệu | Ví dụ |
| --- | --- |
| **Bảo mật** | Luồng bị từ chối theo namespace/Pod khi có log, policy drift, thay đổi label nhạy cảm. |
| **Network** | DNS errors, TCP resets/timeouts, egress gateway logs, NAT saturation. |
| **Ứng dụng** | HTTP 5xx, p95/p99 latency, checkout success rate, batch backlog. |
| **Nền tảng** | Pod readiness, GKE dataplane health, Deployment rollout, node conditions. |
| **Chi phí** | Logging volume, network transfer, node capacity, dịch vụ egress. |

Một “deny event” có thể là bằng chứng policy đang chặn traffic không mong muốn, **không mặc nhiên là incident**. Ngược lại, một luồng bị chặn làm checkout thất bại dù không có log deny chi tiết vẫn là sự cố SLO cần xử lý.

### 18.3. Nguyên tắc kiểm toán

Lưu bằng chứng:

1. Ai phê duyệt traffic matrix và exception.
2. Commit nào thay đổi NetworkPolicy hoặc namespace labels.
3. Ai áp manifests lên production, từ pipeline/principal nào.
4. Kết quả preflight, test allow/deny và chỉ số trước/sau rollout.
5. Thời điểm rollback, lý do và phạm vi ảnh hưởng.

**Kubernetes audit logs** và **Cloud Audit Logs** có phạm vi/cấu hình ghi khác nhau; không mặc định mọi thay đổi hoặc lưu lượng bị chặn được ghi mặc định. Với GKE, kiểm tra những logging features đang bật, retention, quyền đọc và chính sách bảo mật dữ liệu.

## 19. Bài tập tự thực hành

### Bài 1 — Phân biệt namespace và NetworkPolicy

Một cluster có namespace `web`, `api` và `payments`, chưa có policy nào. Có thể khẳng định `web` không gọi được Pod `payments` vì hai namespace tách biệt không? Hãy giải thích cơ chế tách namespace và cơ chế network isolation.

**Gợi ý:** namespace là ranh giới tổ chức tài nguyên và RBAC; Kubernetes NetworkPolicy mới điều chỉnh allow/deny ở mạng Pod theo khả năng enforcement.

### Bài 2 — Ingress hay egress?

Pod A trong `web` gọi Pod B trong `api`. A có egress policy chỉ allow TCP 443, B có ingress policy chỉ allow TCP 8080 từ A. Một client đang gọi TCP 8080 từ A tới B có được không? Phía nào cần sửa? Điều gì sẽ khác nếu A không bị cô lập egress?

### Bài 3 — AND/OR

So sánh hai đoạn:

~~~yaml
# Cách A: một peer có hai selectors
from:
  - namespaceSelector:
      matchLabels: {access-zone: web}
    podSelector:
      matchLabels: {app: storefront}
~~~

~~~yaml
# Cách B: hai peers độc lập
from:
  - namespaceSelector:
      matchLabels: {access-zone: web}
  - podSelector:
      matchLabels: {app: storefront}
~~~

**Câu hỏi:** cách nào chỉ cho phép Pod `storefront` trong các namespace web? Cách nào vô tình mở rộng cho tất cả Pod ở namespace web?

### Bài 4 — Mặc định chặn mọi chiều

Viết manifest cho `default-deny-all` ở namespace `retail-batch`; giải thích vì sao còn cần policy DNS và egress đến dịch vụ dữ liệu. Nêu một trường hợp system traffic có thể phụ thuộc implementation và không nên được coi là bị chặn tuyệt đối.

### Bài 5 — DNS sau policy

`orders-api` có thể gọi `10.70.4.12:5432` theo IP nhưng lỗi khi dùng hostname database. Hãy phân biệt lỗi DNS policy, resolver config và kết nối tới IP. Nếu cluster dùng NodeLocal DNSCache, có nên dùng nguyên policy chọn kube-dns Pod trong phần 8 không?

### Bài 6 — Cloud SQL và danh tính

Một Pod có egress policy cho TCP 5432 đến private IP Cloud SQL, nhưng nhận lỗi `password authentication failed`. Điều này có chứng minh NetworkPolicy sai không? Cần xem những kiểm soát nào ở database/IAM?

### Bài 7 — GKE Dataplane V2

Vì sao không dùng `ipBlock` để chọn dải Pod IP trong GKE Dataplane V2? Hãy thiết kế lại policy chỉ cho namespace `retail-web` và Pod label `app=storefront` gọi API. Nêu các kiểm thử chứng minh enforcement.

### Bài 8 — Cho phép Load Balancer

Sau khi default-deny ingress ở `retail-web`, external Application Load Balancer trả 503. Liệt kê những câu hỏi phải trả lời về backend NEG/node, nguồn health checker/proxy và NetworkPolicy trước khi thêm allow rule. Vì sao không nên mặc định mở tất cả IP tới TCP 8080?

### Bài 9 — Một policy khác mở rộng quyền

Một namespace đã có `default-deny-all` và `allow-api-from-web`. Một thành viên khác thêm policy có một ingress rule chứa `from: []` và `ports: [{protocol: TCP, port: 8080}]`. Điều gì xảy ra với tập nguồn được phép? Hãy phân biệt **`from: []` trong một rule** với **`ingress: []` ở cấp `spec`** và giải thích vì sao tên policy không cho biết chính xác mức bảo vệ.

**Gợi ý:** `from: []` hoặc bỏ `from` trong **một ingress rule** nghĩa là không hạn chế nguồn của rule đó; `ingress: []` nghĩa là policy không có rule allow ingress. Khi nhiều policies cùng chọn Pod, các allow được hợp nhất, nên một rule rộng có thể mở đường dù đã có default-deny.

### Bài 10 — Rollout production

Đề xuất kế hoạch áp NetworkPolicy cho `retail-api` có SLO 99,9%, các phụ thuộc Cloud SQL/Pub/Sub/Secret Manager, health checks và OpenTelemetry. Hãy chỉ ra traffic discovery, thứ tự policy, thời điểm kiểm thử, người phê duyệt và cách rollback mà không xóa policies của nhóm khác.

## 20. Checklist trước khi áp dụng production

| Hạng mục | Điều cần xác nhận |
| --- | --- |
| **GKE data plane** | Cluster dùng Calico/Dataplane V2 hay cơ chế hỗ trợ nào; enforcement thực sự hoạt động. |
| **Standard/Autopilot** | Tính năng network policy và hạn chế node/CNI khớp loại cluster/version. |
| **Traffic matrix** | Nguồn, đích, namespaces, labels, ports, protocol và owner đã được ghi nhận. |
| **Default isolation** | Áp default-deny đúng namespace và đúng ingress/egress, không phá phụ thuộc. |
| **Selector logic** | `podSelector`/`namespaceSelector` AND/OR chính xác, không mở rộng do YAML indent. |
| **Namespace labels** | Quyền chỉnh labels được kiểm soát, không để tenant tự vào nhóm được phép. |
| **Pod labels** | Deployment labels và Service selectors được đồng bộ với policies. |
| **DNS** | Resolver thực tế (kube-dns/NodeLocal/Cloud DNS) và TCP/UDP 53 được xử lý đúng. |
| **Database** | Cloud SQL/private endpoint/Pod DB, port, route, IAM/DB auth và SSL theo kiến trúc. |
| **Google APIs** | Egress, DNS, PGA/NAT/PSC, node image pull identity và Pod runtime identity được phân biệt. |
| **Ingress/Gateway** | LB backend, health checks, proxy nguồn và Pod ingress policy được kiểm thử thật. |
| **L7 & IAM** | NetworkPolicy không thay thế mTLS, service authorization, RBAC và Google IAM. |
| **Testing** | Có positive và negative connectivity tests theo traffic matrix. |
| **Rollout** | Staging, canary, approvals, SLO monitoring và rollback có kiểm soát. |
| **Audit/observability** | Policy changes, labels, flow telemetry khi hỗ trợ, logs và incident evidence. |
| **Cost** | Tính logging, network egress, node performance và chi phí vận hành liên quan. |

## 21. Tài liệu chính thức và điểm cần ghi nhớ

Khả năng enforcement, các tính năng Dataplane V2, NetworkPolicy logging, FQDN-aware policies và xử lý traffic qua Service/load balancer có thể thay đổi theo phiên bản GKE. Trước khi áp chính sách lên cluster thật, đối chiếu tài liệu hiện hành:

- [Kubernetes Network Policies — concepts](https://kubernetes.io/docs/concepts/services-networking/network-policies/)
- [GKE network policy overview](https://cloud.google.com/kubernetes-engine/docs/concepts/network-policy)
- [Configure network policies in GKE](https://cloud.google.com/kubernetes-engine/docs/how-to/network-policy)
- [GKE Dataplane V2 overview](https://cloud.google.com/kubernetes-engine/docs/concepts/dataplane-v2)
- [GKE FQDN network policies](https://cloud.google.com/kubernetes-engine/docs/how-to/fqdn-network-policies)
- [GKE VPC-native clusters](https://cloud.google.com/kubernetes-engine/docs/concepts/alias-ips)
- [GKE Ingress and load balancing](https://cloud.google.com/kubernetes-engine/docs/concepts/ingress)
- [Workload Identity Federation for GKE](https://cloud.google.com/kubernetes-engine/docs/concepts/workload-identity)
- [Cloud SQL private IP connectivity](https://cloud.google.com/sql/docs/postgres/private-ip)
- [GKE troubleshooting](https://cloud.google.com/kubernetes-engine/docs/troubleshooting)
- [Kubernetes NetworkPolicy API](https://kubernetes.io/docs/reference/kubernetes-api/policy-resources/network-policy-v1/)

**Điểm cốt lõi:** NetworkPolicy là một **allow-list ở tầng Pod L3/L4**, có phạm vi namespace và được hợp nhất theo quy tắc cộng dồn. Bảo vệ có hiệu lực khi GKE data plane thực thi chính sách, selector khớp đúng Pod/namespace và cả chiều ingress lẫn egress được thiết kế nhất quán. Hãy bắt đầu từ traffic matrix, kiểm thử default-deny và các ngoại lệ cần thiết (đặc biệt là DNS, load balancer và dữ liệu), đồng thời giữ IAM, RBAC, VPC firewall và kiểm soát ứng dụng như các lớp bảo vệ độc lập. Vận hành tốt được đo bằng **luồng trái phép bị chặn mà giao dịch hợp lệ vẫn đáp ứng SLO**.
