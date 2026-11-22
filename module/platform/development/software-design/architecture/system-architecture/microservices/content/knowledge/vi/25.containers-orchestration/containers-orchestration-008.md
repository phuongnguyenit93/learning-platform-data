# Network policy, phân quyền và cô lập khối lượng công việc

**Chủ đề:** Container và điều phối trong thiết kế kiến trúc hệ thống, microservices và Kubernetes.

Khi nhiều microservice cùng chạy trên một cụm Kubernetes, chúng chia sẻ hạ tầng mạng, node và một phần cơ chế điều hành. Mỗi Pod có thể giao tiếp qua mạng với những Pod khác nếu không có chính sách hạn chế phù hợp. Một ứng dụng có thể sở hữu danh tính Kubernetes có quyền thao tác với API server; một container cấu hình quá rộng có thể đọc tài nguyên của host hoặc truy cập bí mật không cần thiết. Vì vậy, việc “chạy mỗi dịch vụ trong một container” chưa đủ để tạo ranh giới bảo mật.

**NetworkPolicy** kiểm soát các luồng mạng theo Pod, namespace và cổng được hỗ trợ. **RBAC** giới hạn quyền thao tác với tài nguyên qua Kubernetes API. **ServiceAccount và workload identity** định danh tiến trình. **SecurityContext, Pod Security Standards, quota và chính sách admission** hạn chế đặc quyền và tài nguyên. Với tenant có mức độ tin cậy khác nhau, đôi khi cần thêm vùng node hoặc cụm riêng.

Bài học trình bày cách kết hợp các lớp trên theo nguyên tắc **mặc định từ chối, cấp quyền tối thiểu, tách ranh giới tin cậy và kiểm thử cả luồng được phép lẫn luồng bị chặn**.

## 1. Mô hình ranh giới tin cậy trong một cụm

~~~mermaid
flowchart TB
    U["Người dùng"] --> GW["Ingress / API Gateway"]
    subgraph N1["Namespace frontend"]
      FE["frontend Pod"]
    end
    subgraph N2["Namespace commerce"]
      API["checkout Pod"]
      WK["order-worker Pod"]
    end
    subgraph N3["Namespace payments"]
      PAY["payment-api Pod"]
    end
    subgraph N4["Namespace data"]
      DB["database / DB proxy"]
    end
    GW --> FE
    FE --> API
    API --> PAY
    API --> DB
    WK --> DB
    CTRL["Kubernetes API Server"] -.-> API
    CTRL -.-> WK
~~~

Sơ đồ này cần hai kiểu quyền riêng:

1. **Quyền trên đường mạng:** frontend được gọi checkout cổng nào? Checkout có được truy cập Payment và DB không? Order worker có thể giao tiếp trực tiếp với frontend không?
2. **Quyền trên control plane:** workload có được đọc Secret, sửa Deployment, tạo Pod hay lấy danh sách đối tượng trong namespace khác không?

Cho phép traffic TCP 8080 từ frontend đến checkout **không cấp quyền sửa Deployment**. Cấp quyền Kubernetes API đọc ConfigMap **không cấp quyền gọi HTTP đến mọi Pod**. Hai cơ chế độc lập nhưng bổ trợ nhau.

Các mục tiêu thực tế:

- Nếu frontend bị xâm nhập, nó không tự do truy cập DB, hệ thống thanh toán hoặc kube-apiserver.
- Nếu một Pod consumer lỗi và phát quá nhiều lưu lượng, phạm vi tác động được giới hạn.
- Workload chỉ thấy Kubernetes resource cần thiết để làm việc, không dùng credential admin.
- Node không cho container tùy ý chạy privileged, mount host filesystem hoặc truy cập socket runtime.
- Quyền và mạng có thể được kiểm tra tự động, lưu trong Git và truy vết khi thay đổi.

## 2. Phân biệt các lớp bảo vệ

| Lớp | Cơ chế thường gặp | Bảo vệ điều gì | Không giải quyết trực tiếp |
|---|---|---|---|
| **Biên mạng** | Firewall, security group, private endpoint, LB | Đường từ ngoài vào cụm và từ cụm ra môi trường khác | Phân quyền API trên từng Kubernetes resource |
| **Mạng Pod** | NetworkPolicy và cơ chế CNI thực thi | Kết nối Pod ↔ Pod / Pod ↔ địa chỉ đích ở tầng mạng | HTTP path, ý nghĩa nghiệp vụ, danh tính người dùng |
| **API Kubernetes** | Authentication, RBAC, admission | Ai được get/list/create/update/delete tài nguyên | Quyền truy cập ứng dụng qua port dịch vụ |
| **Danh tính workload** | ServiceAccount, token/projected identity, cloud workload identity | Danh tính Pod khi gọi control plane hoặc dịch vụ ngoài | Giới hạn network nếu chưa có policy |
| **Đặc quyền runtime** | SecurityContext, seccomp, capabilities, AppArmor/SELinux khi được hỗ trợ | Quyền của process/container đối với kernel và filesystem | Kiểm soát toàn bộ lưu lượng ứng dụng |
| **Chính sách Pod** | Pod Security Admission, policy engine | Chặn Pod quá đặc quyền hoặc sai tiêu chuẩn | Chứng minh dữ liệu ứng dụng không bị lộ |
| **Tài nguyên** | ResourceQuota, LimitRange, requests/limits | Giảm tình trạng chiếm hết CPU, RAM hoặc số lượng đối tượng | Cấp quyền truy cập dữ liệu |
| **Đường ứng dụng** | TLS/mTLS, JWT, OAuth, ACL nghiệp vụ | Xác thực và phân quyền request ở tầng ứng dụng | Hạn chế kernel privileges |
| **Cách ly hạ tầng** | Node pool, sandbox runtime, cluster riêng | Giảm phạm vi chia sẻ tài nguyên/host | Thay thế mọi cơ chế ứng dụng và mạng |

Không có một manifest đơn lẻ đáp ứng mọi hàng. Một thiết kế phòng thủ theo chiều sâu yêu cầu nhiều lớp, mỗi lớp có điểm kiểm tra riêng.

## 3. Bắt đầu với mô hình đe dọa

Trước khi cấu hình policy, xác định tài sản, danh tính, đường truy cập và hậu quả khi một tài khoản bị lộ.

**Tài sản:** thông tin thanh toán, dữ liệu khách hàng, credential, Secret, API server, service nội bộ, cơ sở dữ liệu, image registry và audit log.

**Nguồn đe dọa:** người dùng bên ngoài, một service đã bị khai thác, credential CI/CD bị lộ, tenant không đáng tin, image chứa mã độc, người vận hành có quyền quá rộng hoặc một dependency bị xâm phạm.

**Điểm vào:** ingress, workload gọi nhau, webhook, Kubernetes API, admission webhook, cổng quản trị, metadata service, DNS, egress tới Internet và kết nối đến DB/broker.

Bảng tình huống:

| Sự cố giả định | Hậu quả nếu không cô lập | Biện pháp cần có |
|---|---|---|
| Frontend bị thực thi mã tùy ý | Quét toàn bộ mạng nội bộ, thử truy cập DB | NetworkPolicy ingress/egress, danh tính ứng dụng, DB auth |
| Container bị khai thác | Đọc filesystem host, lấy socket runtime | Non-root, không privileged, bỏ capabilities, không hostPath tùy ý |
| ServiceAccount token bị lộ | Tạo Pod, đọc Secret hoặc sửa Deployment nếu RBAC rộng | Role tối thiểu, token ngắn hạn, tắt automount khi không cần |
| Developer có quyền sửa namespace của đội khác | Thay workload hoặc lấy secret không được phép | Namespace RBAC, group/role binding theo trách nhiệm |
| Worker gửi traffic bất thường | Nghẽn DB và dịch vụ bên cạnh | Egress policy, quota, rate limit, giới hạn kết nối, alert |
| Một tenant chạy workload không tin cậy | Vượt ranh giới container hoặc tác động host | Node/cluster isolation, sandbox và chính sách admission nghiêm |
| Rule mới chặn DNS | Pod không phân giải tên service, request timeout | Policy DNS tối thiểu và integration test |
| Có quyền đổi nhãn namespace | Tự gắn nhãn để trở thành nguồn được phép | RBAC/admission bảo vệ label làm căn cứ phân quyền |

Mối đe dọa cuối đặc biệt quan trọng: nếu network policy tin nhãn namespace như **trust=payments**, quyền sửa nhãn này phải được bảo vệ. Nhãn phục vụ bảo mật không được do tenant tùy ý tự gán.

## 4. NetworkPolicy thực sự hoạt động thế nào?

Kubernetes NetworkPolicy chuẩn mô tả những kết nối **được phép** dựa trên nhãn Pod, namespace, địa chỉ IP và cổng. Một policy thường có:

- **metadata.namespace:** nơi policy được tạo.
- **spec.podSelector:** các Pod **đích được áp dụng chính sách** trong namespace đó. Giá trị rỗng **{}** chọn tất cả Pod của namespace.
- **policyTypes:** Ingress, Egress hoặc cả hai.
- **ingress:** danh sách luồng vào được cho phép, dựa trên **from** và **ports**.
- **egress:** danh sách luồng ra được cho phép, dựa trên **to** và **ports**.

Để NetworkPolicy có hiệu lực, **plugin mạng (CNI) của cụm phải triển khai cơ chế enforcement tương ứng**. Chỉ tạo đối tượng NetworkPolicy thành công qua API không chứng minh lưu lượng đã bị chặn. Một môi trường không hỗ trợ enforcement có thể chấp nhận YAML nhưng kết nối vẫn thông suốt.

### 4.1. Mặc định khi chưa có NetworkPolicy

Trong một mô hình mạng Pod thông thường, **Pod không bị cô lập bởi NetworkPolicy theo một chiều nếu không có policy nào chọn nó để áp dụng hướng đó**. Do vậy, nếu không có biện pháp khác, giao tiếp giữa các Pod thường được cho phép rộng.

Khi ít nhất một policy chọn một Pod cho **Ingress**, Pod đó chỉ nhận được những luồng ingress được các policy áp dụng cho phép. Tương tự, khi Pod bị chọn để cô lập **Egress**, luồng ra được giới hạn theo các policy egress.

**Chính sách được cộng dồn:** nhiều policy cùng chọn Pod sẽ tạo hợp của các kết nối được phép. NetworkPolicy chuẩn không có thứ tự “allow rule sau ghi đè deny rule trước” và không có deny rule tổng quát kiểu firewall. Một policy allow rộng ngoài ý muốn có thể mở đường bị cho là đã chặn bởi policy khác.

### 4.2. Kết nối hai chiều khi cả nguồn và đích bị cô lập

Với Pod A gọi Pod B:

- Egress của **A** phải cho phép luồng đi, nếu A bị cô lập egress.
- Ingress của **B** phải cho phép luồng đến, nếu B bị cô lập ingress.

Nói cách khác, khi cả hai phía có policy hạn chế, cần thỏa **cả hai ranh giới**. Không phải chỉ tạo một allow ingress ở B là luôn đủ nếu A đã bật default deny egress.

Tùy triển khai mạng, kết nối đến IP node, Service VIP, traffic đặc biệt, traffic bị NAT và giao tiếp với host có thể có hành vi riêng. Cần kiểm thử thực tế trên CNI đang dùng, không suy diễn từ YAML rằng mọi đường mạng của cụm đều được chặn giống nhau.

## 5. Bước đầu: default deny theo namespace

Một nền tảng mới thường bắt đầu bằng **default deny** rồi cho phép từng luồng đã được lập sơ đồ và kiểm thử.

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: default-deny-ingress-egress
  namespace: commerce
spec:
  podSelector: {}
  policyTypes:
    - Ingress
    - Egress
~~~

Manifest chọn mọi Pod trong namespace **commerce** và cô lập ingress/egress. Khi policy này có hiệu lực và không có policy allow tương ứng, các kết nối Pod thông thường sẽ bị hạn chế theo hai hướng.

**Điều phải chuẩn bị trước khi triển khai:**

1. Liệt kê kết nối thực tế: client HTTP, DNS, DB, broker, payment API, metrics và dịch vụ quản trị.
2. Tạo các allow policy tối thiểu cần thiết, kiểm thử trước trong staging.
3. Xác nhận CNI thực thi NetworkPolicy và cách xử lý các trường hợp node/host.
4. Đo lỗi DNS, timeout, readiness, consumer lag và tỷ lệ request thất bại.
5. Có quy trình khôi phục nếu chính sách chặn luồng sống còn.

Không áp dụng default deny trên toàn bộ namespace production mà chưa biết ứng dụng cần gọi đi đâu. Sự cố phổ biến là khóa DNS hoặc đường đến service mesh control plane, khiến nhiều Pod trông như “ứng dụng lỗi”.

### 5.1. Default deny có ảnh hưởng Service hay Ingress controller không?

Policy chọn **Pod**, không chọn đối tượng Service hay Ingress trực tiếp. Client vào Service cuối cùng cần lưu lượng đến Pod backend được phép theo điều kiện mạng. Ingress controller ở namespace khác có thể mang nhãn/identity riêng và cần được cho phép như một nguồn cụ thể.

Cách IP/port đích được nhìn thấy ở điểm áp policy có thể chịu ảnh hưởng từ Service NAT, kube-proxy/eBPF và CNI. Nếu có quy tắc dựa trên địa chỉ IP, phải kiểm thử trên đường thực tế thay vì giả định packet giữ nguyên địa chỉ ở mọi lớp.

## 6. Allow ingress: chỉ frontend được gọi checkout

Giả sử:

- Frontend chạy ở namespace **frontend**, Pod có nhãn **app: web**.
- Checkout chạy ở namespace **commerce**, Pod có nhãn **app: checkout-api**.
- Checkout lắng nghe TCP 8080.

Policy tại **commerce**:

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: checkout-allow-web
  namespace: commerce
spec:
  podSelector:
    matchLabels:
      app: checkout-api
  policyTypes:
    - Ingress
  ingress:
    - from:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: frontend
          podSelector:
            matchLabels:
              app: web
      ports:
        - protocol: TCP
          port: 8080
~~~

Ý nghĩa: Pod checkout cho phép kết nối đến TCP 8080 từ Pod **app=web nằm trong namespace frontend**; các luồng ingress khác sẽ cần policy khác để được chấp nhận khi checkout đã bị cô lập ingress.

### 6.1. AND và OR trong peer selector

Trong ví dụ trên, **namespaceSelector** và **podSelector** nằm **cùng một phần tử** của danh sách from, nên kết hợp theo ý nghĩa **AND**: Pod vừa thuộc namespace được chọn, vừa có nhãn app=web.

Nếu viết:

~~~yaml
from:
  - namespaceSelector:
      matchLabels:
        kubernetes.io/metadata.name: frontend
  - podSelector:
      matchLabels:
        app: web
~~~

thì hai phần tử là hai lựa chọn **OR**: cho phép từ các Pod trong namespace frontend **hoặc** các Pod app=web **ở cùng namespace với NetworkPolicy**. Đây có thể là phạm vi rộng hơn ý định.

Ngoài ra, một **podSelector** đứng riêng trong peer thường được hiểu trong namespace của NetworkPolicy, không tự chọn Pod khắp mọi namespace. Để chọn Pod từ namespace khác, dùng namespaceSelector cùng podSelector như ví dụ đầu.

**Bài học:** YAML hợp cú pháp chưa chắc là policy đúng. Kiểm thử âm tính phải chứng minh rằng một Pod có nhãn app=web nhưng nằm sai namespace vẫn không được phép gọi checkout.

### 6.2. Không bỏ quên quyền của nguồn

Nếu namespace frontend cũng có default deny egress, cần allow egress từ web đến checkout TCP 8080. Policy ingress ở checkout không tự mở chiều đi của frontend. Kết nối chỉ thành công khi cả hai phía thỏa các điều kiện áp dụng.

## 7. Allow egress: checkout chỉ gọi payment

Giả sử Payment API ở namespace **payments**, các Pod có **app: payment-api**, lắng nghe TCP 8080. Policy dưới đây chỉ bổ sung quyền egress tới Payment:

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: checkout-to-payment
  namespace: commerce
spec:
  podSelector:
    matchLabels:
      app: checkout-api
  policyTypes:
    - Egress
  egress:
    - to:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: payments
          podSelector:
            matchLabels:
              app: payment-api
      ports:
        - protocol: TCP
          port: 8080
~~~

Nếu checkout đã bị cô lập egress, rule này cho phép lưu lượng TCP 8080 đến những Pod Payment được chọn. Nó **không** tự cho phép DNS, DB hoặc API ngoài. Để ứng dụng chạy thực tế, các luồng cần thiết phải được khai báo theo hợp đồng.

Đồng thời Payment có thể có default deny ingress; khi đó cần một allow ingress ở namespace **payments** từ checkout ở **commerce**. Hai policy phản ánh hai chủ sở hữu ranh giới: dịch vụ gọi cho phép đi ra; dịch vụ được gọi cho phép đi vào.

### 7.1. Egress tới database ngoài cụm

Với DB có IP hoặc dải địa chỉ cố định thuộc phạm vi đã biết, NetworkPolicy có thể dùng **ipBlock** và cổng. Nhưng **ipBlock là chính sách theo IP/CIDR, không phải theo tên DNS** và hành vi khi đi qua Service/NAT phụ thuộc triển khai.

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: checkout-to-database
  namespace: commerce
spec:
  podSelector:
    matchLabels:
      app: checkout-api
  policyTypes:
    - Egress
  egress:
    - to:
        - ipBlock:
            cidr: 10.42.8.0/24
      ports:
        - protocol: TCP
          port: 5432
~~~

**10.42.8.0/24** chỉ là dải minh họa, phải thay bằng phạm vi thực được duyệt. Dải quá rộng tạo khả năng kết nối không cần thiết; IP database có thể thay đổi qua failover nên cần phương án cập nhật policy và thử phục hồi. Với managed database có private endpoint, cần xác nhận đường routing/NAT và vùng IP thật mà CNI nhìn thấy.

NetworkPolicy chuẩn không phải công cụ lý tưởng để cho phép “chỉ tên miền api.example.com”. Nếu cần FQDN egress policy, có thể phải dùng khả năng mở rộng của CNI, egress proxy/gateway hoặc firewall phù hợp; tính năng và giới hạn khác nhau theo sản phẩm.

## 8. DNS: luồng hạ tầng dễ bị quên nhất

Khi áp default deny egress, một Pod có thể mất khả năng phân giải tên vì không được gọi CoreDNS hoặc resolver của cụm. Điều này làm request HTTP, DB connection và các SDK cloud thất bại dù đường TCP tới đích đã được cho phép.

Cần xác định **DNS thực tế nằm ở đâu**, namespace nào, nhãn Pod nào, cổng/protocol nào và có NodeLocal DNSCache hay không. Một rule mẫu khi CoreDNS thực sự ở kube-system với nhãn **k8s-app: kube-dns**:

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-dns
  namespace: commerce
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

**Đây là ví dụ có điều kiện:** nhãn CoreDNS, tên namespace và địa chỉ resolver thay đổi theo cách triển khai. NodeLocal DNSCache chạy theo mô hình khác có thể không được rule Pod selector này bao phủ. Phải quan sát và kiểm thử DNS trên chính cụm đang vận hành.

Kiểm thử cả UDP 53 và TCP 53 khi ứng dụng và resolver có khả năng sử dụng cả hai. DNS có thể hoạt động mà kết nối HTTPS đến đích vẫn bị chặn, nên kiểm thử riêng quá trình resolve và quá trình connect.

### 8.1. DNS không phải cơ chế cho phép ứng dụng

Resolver có thể trả IP của bất kỳ tên miền nào, nhưng policy egress vẫn quyết định đường kết nối có được phép hay không. Chỉ cho phép DNS **không** có nghĩa mọi kết nối outbound đã được phép. Ngược lại, nếu workload được phép gọi proxy chung có quyền đi mọi nơi, cần bảo vệ proxy và chính sách tại đó để tránh lách giới hạn egress.

## 9. RBAC: kiểm soát ai được thao tác trên Kubernetes API

RBAC là **Role-Based Access Control** của Kubernetes. Nó kiểm tra danh tính và quyền khi một chủ thể gọi API server.

Các đối tượng chính:

- **Role:** nhóm quyền trong một namespace, thường cho tài nguyên namespaced.
- **ClusterRole:** tập quyền có thể áp ở mức cluster hoặc được bind trong một namespace tùy trường hợp.
- **RoleBinding:** gắn Role hoặc ClusterRole với một nhóm chủ thể trong phạm vi namespace.
- **ClusterRoleBinding:** gắn ClusterRole ở phạm vi cluster.
- **Subject:** User, Group hoặc ServiceAccount.
- **ServiceAccount:** danh tính thường gắn với workload trong một namespace.

RBAC có các verb như **get, list, watch, create, update, patch, delete**, ngoài một số verb và subresource đặc biệt. Mỗi quyền phải được hiểu theo **apiGroup, resource, subresource, namespace và resourceNames** khi cần.

RBAC không kiểm tra HTTP request đi vào ứng dụng trên cổng 8080. Nó kiểm tra hành động qua Kubernetes API, ví dụ Pod đọc ConfigMap hay pipeline cập nhật Deployment.

### 9.1. Phân biệt quyền đọc và ghi

Cho phép **get** một ConfigMap cụ thể không có nghĩa cho phép **list** tất cả ConfigMap. Cho phép **update deployments** có thể cho phép thay image workload theo quyền đã cấp, tác động tới mã chạy và danh tính Pod. Quyền **create pods** có thể là một đường tăng tác động nếu được tạo Pod dưới ServiceAccount có quyền cao hoặc mount tài nguyên nhạy cảm.

Một policy không nên chỉ đếm số dòng RBAC; phải đánh giá **khả năng thực hiện được khi các quyền kết hợp**.

Cần hạn chế các quyền đặc biệt như sửa role/rolebinding, cấp quyền, impersonate, truy cập subresource exec, tạo token ServiceAccount hoặc thao tác Secret. Quyền này cần chủ sở hữu và kiểm soát rõ ràng.

## 10. ServiceAccount: danh tính riêng theo workload

Khi một Pod cần gọi Kubernetes API hoặc hệ thống nhận workload identity, nên dùng một ServiceAccount phù hợp với trách nhiệm của Pod, thay vì dùng ServiceAccount chung của namespace.

Ví dụ:

~~~yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: checkout-runtime
  namespace: commerce
automountServiceAccountToken: false
~~~

Đặt **automountServiceAccountToken: false** phù hợp khi Pod không cần token Kubernetes API; ứng dụng HTTP bình thường vẫn có thể chạy. Nếu ứng dụng thực sự cần gọi API server, phải bật việc cung cấp credential theo thiết kế, cấp Role tối thiểu và cân nhắc token projected có vòng đời ngắn.

Lưu ý: trường automount có thể đặt ở ServiceAccount hoặc Pod; cần biết giá trị nào có hiệu lực theo quy tắc Kubernetes. Không bật token chỉ vì “mọi Pod đều cần một ServiceAccount”. Pod vẫn gắn danh tính ServiceAccount dù không mount token.

Trong môi trường cloud, workload identity có thể ánh xạ ServiceAccount Kubernetes sang danh tính cloud. Cơ chế ánh xạ, audience, token, IAM policy và cách thu hồi phụ thuộc nền tảng; hãy kiểm thử quyền cloud thực tế, vì RBAC Kubernetes **không thay thế** IAM của đối tượng lưu trữ, hàng đợi hay database managed.

## 11. RBAC tối thiểu: chỉ đọc một ConfigMap khi ứng dụng thật sự cần

Nếu Checkout Service gọi Kubernetes API để lấy ConfigMap tên **checkout-public-config**, có thể cấp Role giới hạn:

~~~yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: checkout-config-reader
  namespace: commerce
---
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: read-checkout-config
  namespace: commerce
rules:
  - apiGroups: [""]
    resources: ["configmaps"]
    resourceNames: ["checkout-public-config"]
    verbs: ["get"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: checkout-config-reader-binding
  namespace: commerce
subjects:
  - kind: ServiceAccount
    name: checkout-config-reader
    namespace: commerce
roleRef:
  kind: Role
  name: read-checkout-config
  apiGroup: rbac.authorization.k8s.io
~~~

Bộ tài nguyên này cho ServiceAccount **checkout-config-reader** quyền **get** ConfigMap cụ thể trong namespace commerce. Nó không cấp quyền đọc Secret, list mọi ConfigMap, sửa Deployment hoặc đọc namespace khác.

**Không tự hiểu ví dụ là cấu hình cho mọi ứng dụng:** nếu Checkout dùng ConfigMap được mount thành volume hoặc biến môi trường và không trực tiếp gọi Kubernetes API, ứng dụng có thể **không cần** quyền get ConfigMap qua RBAC. Tránh cấp Role thừa chỉ để “cho chắc”.

Nếu cần watch/list theo resourceNames, hành vi lọc field selector và sự tương tác với verb cần được kiểm tra theo API. Ví dụ trên chỉ dùng get để giữ hợp đồng đơn giản.

### 11.1. Kiểm tra quyền có thể thực hiện

Lệnh minh họa khi có quyền dùng kubectl và đủ phạm vi impersonation:

~~~bash
kubectl auth can-i get configmaps \
  --resource-name checkout-public-config \
  --namespace commerce \
  --as system:serviceaccount:commerce:checkout-config-reader

kubectl auth can-i list secrets \
  --namespace commerce \
  --as system:serviceaccount:commerce:checkout-config-reader

kubectl auth can-i update deployments \
  --namespace commerce \
  --as system:serviceaccount:commerce:checkout-config-reader
~~~

Kỳ vọng: get ConfigMap được phép; list Secret và update Deployment bị từ chối. Công cụ **kubectl auth can-i** là phép kiểm tra authorization qua API; khả năng impersonate để chạy lệnh cần quyền của người kiểm tra. Không có quyền impersonate không chứng minh ServiceAccount có hoặc không có quyền ứng dụng.

Muốn kiểm chứng đầy đủ, chạy thêm một bài test bằng đúng danh tính của workload với kết nối/cấu hình thật và kiểm tra log API/audit. Không dùng tài khoản cluster-admin để chứng minh quyền tối thiểu của ứng dụng.

## 12. Namespace: đơn vị tổ chức và phạm vi quyền, chưa phải máy ảo riêng

Namespace giúp nhóm các tài nguyên có tên và chính sách riêng. Chúng hữu ích để tách nhóm ứng dụng, môi trường hoặc tenant, nhưng **namespace không tạo ranh giới kernel hay node độc lập**.

Một Pod ở namespace A và Pod ở namespace B có thể chạy cùng node, chia sẻ kernel host và chịu ảnh hưởng tài nguyên chung. Nếu không có NetworkPolicy, mạng giữa chúng vẫn có thể thông. Nếu ServiceAccount bị cấp ClusterRoleBinding quá rộng, namespace không ngăn tài khoản đó thao tác tài nguyên ở namespace khác.

Một thiết kế namespace thường đi kèm:

1. ServiceAccount riêng theo workload.
2. RBAC theo namespace và trách nhiệm.
3. Default deny cùng allow NetworkPolicy rõ ràng.
4. ResourceQuota, LimitRange, request/limit hợp lý.
5. Pod Security Admission hoặc admission policy tương đương.
6. Danh tính và kiểm soát secret theo môi trường.
7. Quyền sửa nhãn namespace/policy được quản trị.
8. Audit, metric và chủ sở hữu namespace.

Khi tách tenant có yêu cầu bảo mật cao, cần xem thêm **node isolation, runtime sandbox và cluster isolation**, thay vì mặc định namespace là đủ cho mã không đáng tin.

## 13. Cô lập process/container bằng SecurityContext

Một Pod có thể hạn chế đặc quyền OS cho process bằng **securityContext**. Ví dụ:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: checkout-api
  namespace: commerce
spec:
  replicas: 2
  selector:
    matchLabels:
      app: checkout-api
  template:
    metadata:
      labels:
        app: checkout-api
    spec:
      serviceAccountName: checkout-runtime
      automountServiceAccountToken: false
      securityContext:
        runAsNonRoot: true
        runAsUser: 10001
        runAsGroup: 10001
        seccompProfile:
          type: RuntimeDefault
      containers:
        - name: checkout
          image: registry.example.com/checkout@sha256:REPLACE_WITH_REAL_DIGEST
          ports:
            - containerPort: 8080
          securityContext:
            allowPrivilegeEscalation: false
            readOnlyRootFilesystem: true
            capabilities:
              drop: ["ALL"]
          resources:
            requests:
              cpu: "250m"
              memory: "512Mi"
            limits:
              memory: "1Gi"
~~~

Manifest minh họa các nguyên tắc:

- **runAsNonRoot/runAsUser:** hạn chế tiến trình chạy với UID root.
- **allowPrivilegeEscalation: false:** ngăn một số kiểu nâng đặc quyền qua exec; đây không phải biện pháp duy nhất chống khai thác.
- **readOnlyRootFilesystem:** giảm khả năng sửa filesystem image; ứng dụng cần đường ghi tạm rõ ràng nếu có.
- **capabilities.drop: ALL:** bỏ năng lực Linux không cần thiết; chỉ thêm lại capability đã xác minh thật sự bắt buộc.
- **seccompProfile RuntimeDefault:** dùng profile syscall của runtime được hỗ trợ.
- **automountServiceAccountToken: false:** giảm lộ credential Kubernetes API khi ứng dụng không cần.
- **requests/limits:** giúp scheduler và runtime quản lý tài nguyên, không phải lớp phân quyền dữ liệu.

Digest và image là placeholder, không deploy nguyên dạng. Ứng dụng Java cần bảo đảm user 10001 đọc được JAR, truststore và thư mục cần thiết. Nếu JVM/framework ghi file tạm, hãy mount **emptyDir** phù hợp ở thư mục cần ghi và xác định quota/giới hạn; không mở read-write toàn bộ root filesystem chỉ vì chưa cấu hình thư mục tạm.

SecurityContext không thay thế việc cập nhật base image, quét dependency, bảo vệ kernel host và giới hạn quyền cloud identity. Một container non-root vẫn có thể gây hại nếu token của nó có quyền đọc mọi object storage.

## 14. Pod Security Standards và admission control

Kubernetes định nghĩa các mức Pod Security Standards thường được mô tả là:

- **Privileged:** phạm vi mở, ít hạn chế đặc quyền.
- **Baseline:** ngăn một số kiểu nâng đặc quyền phổ biến, vẫn hỗ trợ nhiều ứng dụng thông thường.
- **Restricted:** giới hạn nghiêm hơn, phù hợp các workload có thể chạy theo chính sách ít đặc quyền.

Pod Security Admission có thể áp mức chính sách theo namespace ở các chế độ **enforce, audit, warn**. Ví dụ nhãn thể hiện ý định áp Restricted:

~~~yaml
apiVersion: v1
kind: Namespace
metadata:
  name: commerce
  labels:
    pod-security.kubernetes.io/enforce: restricted
    pod-security.kubernetes.io/audit: restricted
    pod-security.kubernetes.io/warn: restricted
~~~

Ví dụ giả định quyền và phiên bản cụm hỗ trợ các tiêu chuẩn tương ứng. Một số workload cần điều chỉnh manifest, runtime, volume và cách chạy trước khi đạt restricted; không bật đột ngột với các Pod hệ thống/ứng dụng chưa kiểm chứng.

**Admission** kiểm tra đối tượng vào thời điểm tạo/sửa theo chính sách. Nó không phải runtime EDR, không liên tục ngăn mọi hành vi của process sau khi được chạy. Ngoài Pod Security Admission, có thể dùng policy engine như Gatekeeper hoặc Kyverno theo năng lực tổ chức để yêu cầu:

- Image từ registry được phép và có digest.
- Không cho privileged, hostNetwork/hostPID/hostIPC khi không được duyệt.
- Không cho hostPath tùy ý hoặc socket container runtime.
- Bắt buộc request/limit và danh tính runtime.
- Hạn chế ServiceAccount mặc định hoặc auto-mount token.
- Yêu cầu nhãn owner/team/environment.
- Chặn image tag mutable ở môi trường nhạy cảm.

Các chính sách tùy chỉnh cần thử với ứng dụng thật để không vô tình ngăn phục hồi khẩn cấp, autoscaler hoặc hệ thống quản lý cụm.

## 15. Host namespace, hostPath và quyền privileged

Một số trường cấu hình làm yếu đáng kể ranh giới container:

| Khả năng | Rủi ro | Chính sách định hướng |
|---|---|---|
| **privileged container** | Gần như bỏ nhiều rào cản cô lập thông thường | Chặn với workload ứng dụng; ngoại lệ rất hẹp cho thành phần hạ tầng |
| **hostNetwork** | Chia sẻ mạng node, thay đổi quan sát và phạm vi NetworkPolicy | Không cấp mặc định cho ứng dụng |
| **hostPID / hostIPC** | Tiếp cận không gian tiến trình/IPC host | Chặn nếu không có nhu cầu rõ |
| **hostPath** | Mount đường dẫn node vào container | Hạn chế; đặc biệt bảo vệ socket runtime và khóa host |
| **hostPort** | Mở port trực tiếp trên node | Quản trị xung đột port và bề mặt tấn công |
| **Docker/container runtime socket** | Có thể cho phép thao tác container/node qua daemon | Không mount vào ứng dụng thông thường |
| **CAP_SYS_ADMIN và capability mạnh** | Cho phép nhiều thao tác kernel nhạy cảm | Drop capabilities, chỉ cấp ngoại lệ được duyệt |
| **Chạy root + filesystem ghi tự do** | Tăng tác động khi process bị khai thác | Non-root, filesystem read-only nếu phù hợp |

Có workload hệ thống như CNI, node agent hoặc CSI cần quyền đặc biệt. Chúng phải có namespace, ServiceAccount, kiểm soát image, node và chính sách ngoại lệ riêng. Không dùng ngoại lệ của system DaemonSet làm mẫu cho ứng dụng thanh toán.

**Không dựa vào NetworkPolicy để cô lập hoàn toàn workload hostNetwork hoặc process trên host.** Hành vi áp chính sách trong các trường hợp đó phụ thuộc CNI và cơ chế enforcement; ranh giới host phải được bảo vệ bằng lớp khác.

## 16. ResourceQuota và LimitRange: cô lập tài nguyên cũng là bảo mật

Một tenant có thể không đọc dữ liệu của tenant khác nhưng vẫn chiếm hết CPU, RAM hoặc tạo hàng nghìn Pod, khiến cụm thiếu năng lực. Đây là rủi ro **noisy neighbor** và từ chối dịch vụ.

Một namespace có thể áp **ResourceQuota**:

~~~yaml
apiVersion: v1
kind: ResourceQuota
metadata:
  name: commerce-budget
  namespace: commerce
spec:
  hard:
    requests.cpu: "8"
    requests.memory: "16Gi"
    limits.cpu: "16"
    limits.memory: "32Gi"
    pods: "80"
    services: "30"
    persistentvolumeclaims: "20"
~~~

Có thể dùng **LimitRange** để đặt mặc định hoặc ràng buộc min/max cho container/Pod trong namespace:

~~~yaml
apiVersion: v1
kind: LimitRange
metadata:
  name: commerce-container-limits
  namespace: commerce
spec:
  limits:
    - type: Container
      defaultRequest:
        cpu: "100m"
        memory: "256Mi"
      default:
        cpu: "1"
        memory: "1Gi"
      min:
        memory: "64Mi"
      max:
        memory: "4Gi"
~~~

Các con số chỉ minh họa. Chúng phải được chọn theo thử tải, khả năng node và nhu cầu sản xuất. Nếu quota quá thấp, Deployment có thể không tạo replica dự phòng khi rolling update. Nếu request quá lớn, Pod không được schedule dù mức sử dụng thực thấp. Nếu memory limit quá thấp, JVM có thể OOM vì metaspace, direct buffer và thread stack ngoài heap.

**Quota hạn chế ngân sách namespace**, nhưng không bảo đảm công bằng tuyệt đối về I/O, network, disk và tài nguyên phụ thuộc như DB. Cần thêm QoS, giới hạn worker/concurrency, storage class policy, network throttling hoặc tách node/cluster khi rủi ro yêu cầu.

## 17. Cô lập node và cụm cho các mức tin cậy khác nhau

Với nhiều tenant cùng thuộc một tổ chức, namespace và RBAC có thể đủ khi họ không chạy mã tùy ý và có mức tin cậy tương đương. Nhưng với mã người dùng hoặc đối tác không đáng tin, cần xét các phương án cách ly mạnh hơn:

1. **Node pool riêng:** tránh chia sẻ kernel host với workload nhạy cảm; dùng taint/toleration, node affinity và quyền tạo Pod được kiểm soát.
2. **Sandbox runtime:** dùng cơ chế như gVisor/Kata Containers ở nền tảng hỗ trợ, kiểm chứng chi phí và khả năng tương thích.
3. **Cluster riêng:** tách control plane, mạng và blast radius vận hành tốt hơn, nhưng tăng chi phí quản trị, nâng cấp và quan sát.
4. **Cloud account/project riêng:** tách IAM, quota và billing boundary khi cần cách ly tổ chức/tenant mạnh.
5. **Network segment/VPC riêng:** giới hạn đường mạng và egress, phối hợp với firewall nền tảng.

**Taint/toleration không phải cơ chế security boundary độc lập.** Một Pod có quyền tạo/sửa cấu hình rộng có thể thêm toleration hoặc nhãn/affinity theo khả năng được cấp. Muốn cô lập đáng tin cậy, cần admission policy và RBAC để ngăn workload tự chọn vùng cấm.

**Cluster riêng không bảo đảm an toàn tuyệt đối** nếu vẫn dùng chung credential quản trị, image registry không kiểm soát hoặc đường mạng mở rộng. Ranh giới phải thống nhất từ quyền CI/CD đến network và data plane.

## 18. Kiến trúc phân quyền nhiều tenant

Ví dụ một nền tảng phục vụ **tenant-a** và **tenant-b**, mỗi tenant có ứng dụng xử lý sự kiện riêng:

~~~text
Cluster
  |
  +-- namespace: tenant-a
  |     ServiceAccount: a-worker
  |     NetworkPolicy: chỉ đến a-db-proxy + DNS
  |     ResourceQuota: A budget
  |     Pod Security: Restricted
  |
  +-- namespace: tenant-b
  |     ServiceAccount: b-worker
  |     NetworkPolicy: chỉ đến b-db-proxy + DNS
  |     ResourceQuota: B budget
  |     Pod Security: Restricted
  |
  +-- namespace: platform-system
        Thành phần điều hành được quản trị riêng
~~~

Các yếu tố quyết định:

- Tenant A không được đọc/sửa Pod, Secret và RoleBinding của tenant B.
- Tenant A không được sửa nhãn namespace để giả dạng namespace được tin.
- Worker A chỉ được kết nối tới endpoint dữ liệu A theo network policy và kiểm tra danh tính tại database.
- Mỗi tenant có ngân sách CPU/RAM và các giới hạn tài nguyên ngoài cụm.
- Tài khoản triển khai chỉ được tạo những loại workload đã qua admission policy.
- Audit có thể truy ra tenant, ServiceAccount, namespace và thao tác, không ghi payload bí mật.
- Khi tenant A bị xâm nhập, B vẫn được bảo vệ ở cả tầng API, mạng, dữ liệu và tài nguyên.

Nếu tenant được phép chạy arbitrary code hoặc có mức đe dọa cao, đánh giá node/cluster isolation và runtime sandbox riêng. **Namespace là công cụ tổ chức và phạm vi chính sách, không phải hợp đồng cách ly tương đương máy ảo phần cứng.**

## 19. Phân quyền triển khai: CI/CD không cần cluster-admin

Pipeline triển khai thường cần thay image của Deployment hoặc áp manifest trong namespace ứng dụng. Không nên cấp cluster-admin chỉ vì cần chạy kubectl apply.

Có thể thiết kế:

- Build pipeline chỉ có quyền xuất bản image vào registry.
- Deploy pipeline có danh tính riêng theo môi trường, quyền cụ thể với Deployment, Service và ConfigMap được quản lý.
- Công cụ platform provisioning có quyền tạo namespace, Role, ResourceQuota và chính sách nền theo quy trình.
- Người kiểm tra chỉ có quyền đọc trạng thái, log/metric theo phạm vi đã duyệt.
- Thay đổi policy mạng, RBAC hoặc admission được review bởi owner của ranh giới.
- Emergency access dùng cơ chế break-glass có thời hạn và audit.

**Không cho pipeline tùy ý tạo RoleBinding tới quyền cao hơn**, hoặc thay ServiceAccount của một Pod nhạy cảm nếu điều đó tạo đường leo thang. RBAC Kubernetes có các cơ chế ngăn một số hình thức leo thang quyền khi sửa Role/Binding, nhưng việc thiết kế role và đường cấp quyền phải được xem xét toàn bộ; đừng coi một rào cản tự động đủ bảo vệ mọi cấu hình.

### 19.1. Chú ý quyền trên subresource

Một số thao tác trông “chỉ là hỗ trợ” nhưng có tác động mạnh:

- **pods/exec:** chạy lệnh trong container, có thể đọc cấu hình và dữ liệu process được phép.
- **pods/attach:** kết nối phiên làm việc với process.
- **pods/log:** có thể xem bí mật nếu ứng dụng lỡ ghi ra log.
- **serviceaccounts/token:** có thể tạo token cho ServiceAccount theo phạm vi quyền được cấp.
- **secrets:** đọc dữ liệu bí mật ở namespace.
- **deployments/scale:** thay số replica, có thể gây gián đoạn hoặc quá tải.
- **roles/rolebindings và clusterroles/clusterrolebindings:** thay ranh giới quyền.

Đánh giá quyền theo hành vi mà nó cho phép, không chỉ theo tên nghe có vẻ vô hại.

## 20. Mã hóa và bảo vệ luồng dịch vụ

NetworkPolicy quyết định luồng nào được phép ở mức mạng nhưng **không tự mã hóa** dữ liệu hoặc xác thực ứng dụng.

Hai Pod được phép giao tiếp có thể vẫn cần TLS/mTLS để bảo vệ dữ liệu và xác nhận dịch vụ đích. Có thể dùng:

- TLS ở ứng dụng, client xác minh hostname và certificate.
- Service mesh cung cấp mTLS và authorization policy, nếu phạm vi vận hành phù hợp.
- Gateway / API proxy kiểm soát danh tính và rate limit.
- Danh tính workload từ nền tảng và chứng chỉ ngắn hạn.
- Kiểm tra JWT/claims hoặc policy nghiệp vụ ở service.

Không mặc định “có mTLS là không cần NetworkPolicy”: mTLS giải quyết xác thực/mã hóa đường truyền, còn NetworkPolicy giúp thu hẹp đường kết nối trước khi đến ứng dụng.

Tương tự, một allow NetworkPolicy giữa hai namespace không chứng minh client được phép gọi API **POST /refund**. Quyền nghiệp vụ phải do ứng dụng/gateway kiểm tra theo danh tính và vai trò phù hợp.

## 21. Đặt chính sách cho traffic phía ngoài cụm

**Ingress từ Internet:** thường đi qua load balancer, ingress controller hoặc API gateway. Kiểm soát public endpoint ở tầng gateway/firewall; NetworkPolicy chọn Pod backend và cần cho phép nguồn/port thực tế của traffic.

**Egress tới Internet:** có thể cần proxy hoặc egress gateway với policy theo domain, danh tính, kiểm toán và DLP. NetworkPolicy chỉ cho phép dải IP/port không thể thay thế chính sách HTTP-aware khi yêu cầu chi tiết theo URL hoặc API.

**Cloud metadata service:** workload có thể cố truy cập endpoint metadata của node hoặc cloud provider nếu không được chặn/thiết kế phù hợp. Cần kiểm tra cơ chế cô lập metadata, cloud workload identity và đường mạng cụ thể.

**Kubernetes API server:** Pod bình thường có thể kết nối đến API endpoint qua địa chỉ service hoặc host. Không nên chỉ kỳ vọng NetworkPolicy chặn API server cho mọi Pod trong mọi triển khai; giảm token automount, hạn RBAC và bảo vệ network/API endpoint theo chính sách cụm.

**Node/host traffic:** kubelet probes, hostNetwork process và một số đường node-local có thể được đối xử khác nhau bởi CNI; đây là lý do cần kiểm chứng trên môi trường thực.

## 22. Quy trình triển khai NetworkPolicy an toàn

### Bước 1 — Lập danh sách luồng dữ liệu

Vẽ từng source → destination với namespace, Pod label, protocol, port, mục đích và owner. Ví dụ:

| Nguồn | Đích | Protocol/port | Mục đích | Chủ sở hữu |
|---|---|---|---|---|
| frontend/web | commerce/checkout-api | TCP 8080 | Đặt hàng | Nhóm commerce |
| commerce/checkout-api | payments/payment-api | TCP 8080 | Thanh toán | Nhóm commerce/payments |
| commerce/order-worker | data/order-db-proxy | TCP 5432 | Cập nhật đơn | Nhóm commerce/data |
| commerce/* | CoreDNS | UDP/TCP 53 | Phân giải tên | Platform |
| ingress-controller | frontend/web | TCP 8080 | Traffic từ ngoài | Platform/frontend |
| observability agent | metrics endpoint | TCP theo cấu hình | Thu metric | Platform |

Tên và cổng là giả định minh họa. Với dịch vụ dùng Service mesh, sidecar, collector hoặc webhook, cần đưa những luồng phụ trợ vào sơ đồ thay vì chỉ ghi những luồng nghiệp vụ chính.

### Bước 2 — Xác minh khả năng enforcement

Xác định CNI nào đang chạy và NetworkPolicy có được thực thi cho ingress, egress, IPv4/IPv6, Pod hostNetwork và tình huống Service/NAT không. Dùng một cặp Pod test có kiểm soát để chứng minh deny thực sự hoạt động trước khi áp cho production.

### Bước 3 — Chuẩn hóa nhãn

Quy ước tên namespace và nhãn Pod: app.kubernetes.io/name, environment, team hoặc nhóm trust phù hợp. Không dựa vào nhãn người dùng có thể tự sửa để mở chính sách nhạy cảm.

### Bước 4 — Triển khai allow tối thiểu rồi default deny

Ở môi trường thử nghiệm, tạo những rule cần thiết và thử đường cho phép. Sau đó bật default deny theo namespace và kiểm tra các luồng âm tính. Với production, dùng rollout theo nhóm namespace/workload và lưu đường phục hồi.

### Bước 5 — Kiểm tra hệ thống và SLO

Đo checkout success rate, latency, DNS failures, connection timeout, consumer lag, database connection và log của CNI. Thông báo policy áp dụng thành công từ API chưa đủ: quan sát traffic phải khớp kỳ vọng.

### Bước 6 — Đưa policy vào GitOps/IaC

Lưu manifest có version, review thay đổi theo owner, kiểm tra policy-as-code trong CI. Giới hạn chỉnh tay ở production; nếu phải sửa khẩn cấp, đồng bộ lại bản được phê duyệt vào nguồn có thẩm quyền.

### Bước 7 — Kiểm tra định kỳ

Dịch vụ có endpoint mới, namespace thay tên hoặc đổi nhãn có thể làm rule cũ quá rộng hoặc vô hiệu. Rà soát quyền và luồng mạng theo vòng đời dịch vụ, kết hợp kiểm thử tự động.

## 23. Kiểm thử NetworkPolicy: phải có cả đường được phép và bị chặn

Một bộ test hạ tầng hiệu quả gồm các ca:

| Ca kiểm thử | Nguồn | Đích | Kỳ vọng |
|---|---|---|---|
| Đúng namespace và label | frontend/web | commerce/checkout-api:8080 | ALLOW |
| Sai namespace nhưng cùng label | attacker/web | commerce/checkout-api:8080 | DENY |
| Đúng namespace nhưng sai label | frontend/random | commerce/checkout-api:8080 | DENY |
| Đúng nguồn, sai cổng | frontend/web | commerce/checkout-api:9090 | DENY |
| Checkout gọi Payment | commerce/checkout-api | payments/payment-api:8080 | ALLOW nếu hai chiều cho phép |
| Checkout gọi Pod khác | commerce/checkout-api | payments/admin:8080 | DENY |
| Checkout gọi DB không thuộc phạm vi | commerce/checkout-api | IP ngoài CIDR được duyệt | DENY |
| DNS thực tế | commerce/checkout-api | resolver của cụm:53 | ALLOW theo chính sách |
| Pod không liên quan | commerce/untrusted | API server nếu policy và mạng chặn | Phải đối chiếu cơ chế áp dụng |

**Đừng dùng Pod debug có quyền cluster-admin hoặc chạy hostNetwork** để làm đại diện cho một Pod thường. Danh tính, namespace, nhãn, network mode và container runtime có thể ảnh hưởng kết quả.

Thử lệnh kết nối trong môi trường được phép; ví dụ:

~~~bash
# Chạy từ Pod kiểm thử cùng cấu hình mạng với workload cần xét.
kubectl -n commerce exec checkout-test -- \
  sh -c 'nc -z -w 3 payment-api.payments.svc.cluster.local 8080'

# Thử một endpoint dự kiến bị chặn.
kubectl -n commerce exec checkout-test -- \
  sh -c 'nc -z -w 3 internal-admin.payments.svc.cluster.local 8080'
~~~

Các tên Pod/service là giả định; image test cần có công cụ nc, còn quyền exec phải được cấp có kiểm soát. Một kết nối thất bại có thể do DNS, Pod không Ready, sai port hoặc NetworkPolicy. Hãy dùng kết hợp DNS, connectivity, log và trạng thái endpoint để xác định nguyên nhân.

**Kết quả ALLOW/DENY cần quan sát ở tầng kết nối thực tế**, không chỉ suy luận từ việc API trả resource đã tạo.

## 24. Kiểm thử RBAC và quyền truy cập API

Một ma trận quyền cũng cần kiểm thử như hợp đồng:

| Danh tính | Hành động | Kỳ vọng |
|---|---|---|
| checkout-config-reader | get configmaps/checkout-public-config trong commerce | ALLOW |
| checkout-config-reader | list secrets trong commerce | DENY |
| checkout-config-reader | update deployments trong commerce | DENY |
| checkout-config-reader | get configmap ở payments | DENY |
| deploy-bot-commerce | thay image Deployment đã được duyệt | ALLOW theo role được thiết kế |
| deploy-bot-commerce | tạo ClusterRoleBinding admin | DENY |
| tenant-a-service | đọc Secret tenant-b | DENY |
| operator-readonly | xem trạng thái theo phạm vi | ALLOW, hạn chế exec và secret |

Có thể dùng **kubectl auth can-i**, kiểm thử API bằng ServiceAccount thật và audit log. Cần nhớ kết quả của lệnh impersonation phụ thuộc quyền người chạy test; tránh dùng kết quả admin như bằng chứng quyền ứng dụng.

Trong CI, kiểm tra thêm thay đổi Role/Binding có vô tình mở wildcard **resources: ["*"]**, **verbs: ["*"]** hoặc **apiGroups: ["*"]** không. Một wildcard có thể hợp lệ với thành phần platform đã được quản lý, nhưng phải có review ngoại lệ rõ ràng.

## 25. Kiểm thử đặc quyền runtime và admission

Không chỉ nhìn spec “có runAsNonRoot”. Một bộ test có thể bao gồm:

1. Pod bình thường đạt chính sách Restricted và khởi động thành công.
2. Pod đặt **privileged: true** hoặc **hostPID: true** bị admission chặn ở namespace đã yêu cầu.
3. Pod xin mount hostPath/socket runtime không được phép bị chặn.
4. Container chạy user không phải root và không có capability không cần thiết.
5. Root filesystem read-only, ứng dụng vẫn ghi được thư mục tạm được khai báo.
6. Ứng dụng không được mount ServiceAccount token khi không có nhu cầu.
7. Image không có secret và được phát hành bằng artifact có thể truy vết.
8. Giới hạn memory/CPU không làm ứng dụng OOM/restart trong tải đã kiểm thử.
9. Các workload hạ tầng cần ngoại lệ được giới hạn riêng và có audit.
10. Tenant không thể tự thay nhãn/node selector để vượt ranh giới hạ tầng.

Kết quả cần phản ánh **hành vi được thực thi** chứ không chỉ sự tồn tại của YAML. Nếu admission chặn Pod hợp lệ, cần sửa workload hoặc thiết kế ngoại lệ có kiểm soát, không tắt toàn bộ policy trong production để khắc phục nhanh.

## 26. Theo dõi và xử lý sự cố policy

Một hệ thống có NetworkPolicy/RBAC nghiêm ngặt cần đủ tín hiệu để phân biệt **lỗi bảo mật được chặn đúng** với **lỗi cấu hình cản luồng hợp lệ**.

### 26.1. Các tín hiệu đáng theo dõi

- Số lần Kubernetes API trả **Forbidden/403**, tách theo principal, verb, resource, namespace và thời gian.
- CNI policy drop/deny events, nếu plugin hỗ trợ xuất telemetry.
- DNS resolution failures, TCP connect timeout, connection refused.
- HTTP 5xx, p95/p99 latency, request timeout, queue lag sau khi cập nhật policy.
- Pod admission rejections, Pod Pending do quota, OOMKilled hoặc CrashLoopBackOff.
- Thay đổi Role, RoleBinding, ClusterRoleBinding, namespace label và NetworkPolicy.
- ServiceAccount token usage, quyền cloud IAM và lưu lượng egress bất thường.
- Các ngoại lệ privileged, hostPath và workload sử dụng node pool nhạy cảm.

Không dùng tên user/tenant hoặc payload tùy ý làm metric label với cardinality vô hạn. Log/audit cần che secret và hạn chế quyền đọc. Cần nối thời điểm thay policy với thời điểm bắt đầu lỗi để nhận diện tương quan.

### 26.2. Chẩn đoán khi checkout không gọi được Payment

Một quy trình chẩn đoán:

~~~text
Checkout request timeout
    |
    +-- DNS có resolve payment-api không?
    |     |
    |     +-- Không -> kiểm tra CoreDNS, DNS egress và DNS policy
    |
    +-- Service/Endpoint có Pod Ready không?
    |     |
    |     +-- Không -> readiness, Deployment, Pod health
    |
    +-- TCP tới Pod/Service có thông không?
    |     |
    |     +-- Không -> source egress, destination ingress,
    |                   port/protocol, CNI, Service NAT
    |
    +-- TCP thông nhưng HTTP trả 401/403?
    |     |
    |     +-- Có -> kiểm tra TLS/mTLS, JWT, quyền ứng dụng
    |
    +-- HTTP được nhưng Kubernetes API trả Forbidden?
          |
          +-- Kiểm tra ServiceAccount/RBAC cho thao tác API
~~~

**Không sửa lỗi kết nối bằng cách cấp cluster-admin.** Lỗi mạng và quyền API là hai tầng riêng; tăng RBAC thường không giải quyết NetworkPolicy deny. Tương tự, không xóa default deny toàn namespace chỉ vì một health check lỗi trước khi xác định luồng cần cho phép.

### 26.3. Rollback policy có kiểm soát

Nếu rule mới làm gián đoạn sản xuất:

1. Dừng rollout policy tới namespace khác.
2. Xác định phiên bản policy vừa triển khai và luồng nào thất bại.
3. Áp bản sửa hoặc khôi phục manifest được biết là tốt qua kênh quản trị được phép.
4. Kiểm chứng CNI thực thi và đường kết nối cần thiết hồi phục.
5. Đo SLO, số lỗi DNS/timeout và luồng bị chặn ngoài ý muốn.
6. Đưa thay đổi khẩn cấp về GitOps/IaC, lưu audit và nguyên nhân.

Không khôi phục bằng cách mở toàn bộ egress/ingress vĩnh viễn nếu có thể sửa rule ở phạm vi hẹp hơn. Trong tình huống khẩn cấp, quyền break-glass phải có chủ sở hữu, thời hạn và dấu vết.

## 27. Hành vi thực tế khác nhau giữa các CNI và nền tảng

Các triển khai có thể khác nhau ở:

- Mức hỗ trợ NetworkPolicy chuẩn và các chính sách mở rộng.
- Dữ liệu telemetry cho packet drop, flow log và DNS proxy.
- Hành vi với hostNetwork, node-local traffic, Service VIP và NAT.
- Egress FQDN, L7 HTTP/gRPC, identity-based policy và cơ chế deny riêng của nhà cung cấp.
- Hỗ trợ IPv6, dual-stack, eBPF và cách áp policy theo phiên bản.
- Tích hợp cùng service mesh hoặc cloud firewall/security group.

Không sao chép CRD độc quyền của Cilium, Calico hay một nhà cung cấp vào cụm khác mà không kiểm tra API/version. NetworkPolicy **networking.k8s.io/v1** là nền tảng chung; tính năng nâng cao cần gắn với sản phẩm cụ thể và thử nghiệm tương ứng.

Đặc biệt, một số hệ thống có **deny policy** mở rộng ở mức CNI; không được suy ra Kubernetes NetworkPolicy chuẩn cũng có semantic deny với độ ưu tiên giống vậy.

## 28. Tình huống tổng hợp: nền tảng thương mại điện tử

Giả sử hệ thống có:

- **frontend/web:** phục vụ giao diện.
- **commerce/checkout-api:** nhận yêu cầu đặt hàng.
- **commerce/order-worker:** xử lý sự kiện đặt hàng.
- **payments/payment-api:** xác nhận thanh toán.
- **data/order-db-proxy:** đại diện kết nối tới DB.
- **platform/monitoring:** hệ thống thu thập metric.

**Mục tiêu quyền:**

| Workload | Network ingress | Network egress | Kubernetes API |
|---|---|---|---|
| frontend/web | Chỉ nguồn gateway được duyệt | checkout-api và hạ tầng cần thiết | Thường không cần token API |
| commerce/checkout-api | frontend/web TCP 8080 | Payment, DB proxy, DNS, telemetry cần thiết | Không cần quyền sửa workload |
| commerce/order-worker | Không mở ingress nghiệp vụ nếu không cần | Broker, DB proxy, DNS | Thường không cần token API |
| payments/payment-api | checkout-api theo cổng hợp đồng | DB/payment provider được duyệt | Không cần quyền sửa namespace |
| data/order-db-proxy | Chỉ Checkout/worker được duyệt | DB backend | Quyền hạ tầng riêng nếu có |
| platform/monitoring | Theo hợp đồng scrape/push | Metric endpoints hoặc collector | Read-only tối thiểu khi discovery cần |

**Thiết kế:**

1. Mỗi namespace bật default deny sau khi có allow list.
2. Mỗi workload dùng ServiceAccount riêng và tắt token automount khi không cần Kubernetes API.
3. Các Pod chạy non-root, có seccomp phù hợp, bỏ capability thừa và giới hạn resource.
4. Namespace commerce áp Pod Security Restricted khi ứng dụng đáp ứng.
5. Deploy bot chỉ sửa các workload của commerce; không tạo RoleBinding cluster-admin.
6. Nhãn làm căn cứ cho phép từ frontend/payments được bảo vệ khỏi sửa tùy ý.
7. Telemetry theo dõi denied flows, API Forbidden, kết nối Payment, DNS, checkout SLO.
8. Bài test canary thử cả đường frontend → checkout được phép lẫn attacker namespace → checkout bị chặn.
9. Khi Payment đổi port hoặc nhãn, cập nhật policy và ứng dụng theo một phiên bản rollout có kiểm chứng.

**Kịch bản bị xâm nhập:** một lỗ hổng frontend cho phép chạy mã trong Pod. Kẻ tấn công có thể thử kết nối checkout đúng tuyến frontend đã được phép; vì vậy checkout vẫn cần xác thực và phân quyền nghiệp vụ. Nhưng nó không nên trực tiếp kết nối DB hoặc kube-apiserver với quyền rộng nếu ranh giới được áp đúng. Đây là **giảm phạm vi ảnh hưởng**, không phải tuyên bố ứng dụng miễn nhiễm khai thác.

## 29. Quy trình thiết kế chính sách cho microservice mới

Một checklist triển khai thực hành:

1. **Xác định owner và mức tin cậy:** workload nội bộ, đối tác hay mã tenant không đáng tin?
2. **Mô tả network graph:** ingress, egress, protocol, port, DNS, control plane, observability và nguồn sự kiện.
3. **Chọn namespace và nhãn:** bảo vệ những nhãn dùng trong security decision.
4. **Tạo ServiceAccount:** ứng dụng có cần Kubernetes API không? Nếu không, tắt token automount.
5. **Thiết kế RBAC:** cấp get/list/watch/create/update/delete đúng resource và namespace; tránh wildcard.
6. **Áp SecurityContext:** non-root, capabilities tối thiểu, seccomp, hạn quyền mount/host.
7. **Đặt resource budget:** requests/limits, ResourceQuota, LimitRange và downstream quota.
8. **Dùng default deny:** thêm allow rule theo network graph; kiểm tra cả ingress và egress.
9. **Kiểm thử hành vi:** allow/deny, DNS, TLS/mTLS, API Forbidden, admission rejection và lưu lượng thực.
10. **Phát hành có kiểm soát:** canary, SLO guardrail, rollback và audit policy.
11. **Rà soát định kỳ:** khi thêm endpoint, đổi label, tạo namespace hoặc thay ServiceAccount.
12. **Tăng mức cô lập nếu cần:** node pool/sandbox/cluster riêng cho tenant hoặc workload rủi ro cao.

Đầu ra nên là **một ma trận quyền và luồng** có owner, cùng manifest và bài test xác nhận. Danh sách YAML dài không thể thay thế quyết định kiến trúc về mức tin cậy.

## 30. Các sai lầm thường gặp

| Sai lầm | Hậu quả | Cách khắc phục |
|---|---|---|
| Tạo NetworkPolicy trên CNI không hỗ trợ | Tưởng đã chặn nhưng traffic vẫn thông | Kiểm thử enforcement trên cụm |
| Chỉ chặn ingress | Pod bị xâm nhập vẫn có thể gọi ra ngoài | Đánh giá egress và downstream ACL |
| Quên DNS sau default deny | Ứng dụng không resolve service | Allow resolver thực tế có kiểm soát |
| Hiểu sai AND/OR của from/to | Mở phạm vi ngoài ý muốn | Test sai namespace/sai label |
| Cho phép CIDR quá rộng | Egress vượt nhu cầu nghiệp vụ | Thu hẹp và theo dõi đường thực |
| Xem NetworkPolicy là firewall L7 | Không chặn được HTTP path hoặc user sai quyền | Thêm app authz/mTLS/gateway |
| Dùng default ServiceAccount mọi Pod | Khó thu hồi và kiểm toán | Workload identity riêng |
| Tự động mount token dù không cần | Tăng nguy cơ lộ quyền API | Disable automount, cấp khi cần |
| Cấp cluster-admin để sửa lỗi kết nối | Mở quyền kiểm soát cluster vô ích | Chẩn đoán mạng và RBAC riêng |
| Role có wildcard verbs/resources | Một credential có tác động quá lớn | Phân quyền thao tác/tài nguyên cụ thể |
| Tin namespace là kernel isolation | Tenant không đáng tin cùng chia sẻ host | Node/cluster/sandbox khi cần |
| Chạy container privileged cho tiện | Có thể vượt nhiều ranh giới runtime | SecurityContext và ngoại lệ hẹp |
| Dùng hostPath/socket runtime tùy ý | Tăng quyền thao tác node | Chặn bằng admission và thiết kế lưu trữ |
| Thiếu ResourceQuota | Một team chiếm tài nguyên cụm | Budget theo namespace và quan sát |
| Chỉ kiểm tra “apply YAML thành công” | Không biết policy có thực thi | Positive/negative connectivity tests |
| Để tenant tự sửa nhãn trust | Giả dạng nguồn được phép | RBAC + admission bảo vệ nhãn |
| Không xét Service/NAT/hostNetwork | Chính sách hoạt động khác dự kiến | Thử trên CNI và đường traffic thật |
| Rollback bằng mở tất cả port vô hạn | Tạo lỗ hổng tồn tại lâu | Khôi phục rule hẹp, audit và TTL ngoại lệ |

## 31. Bài tập thực hành

**Bài A — thiết kế NetworkPolicy:** Frontend ở namespace public gọi API ở namespace commerce cổng 8080. Một Pod khác cùng nhãn app=web ở namespace attacker không được gọi API. Hãy viết ingress rule chọn đúng namespace **và** Pod, rồi xây hai bài test allow/deny.

**Bài B — kiểm thử egress:** Checkout chỉ được gọi Payment, DB proxy và DNS. Hãy lập danh sách port/protocol và đề xuất các egress policy. Nếu checkout dùng Service VIP hoặc database managed, nêu những điểm phải kiểm chứng trong CNI/NAT.

**Bài C — quyền API:** Một consumer chỉ đọc message từ Kafka, ghi DB, không gọi Kubernetes API. Nó có cần quyền get/list Pod và Secret không? Thiết kế ServiceAccount, automount và RBAC tối thiểu. Nếu có một sidecar cần discovery Kubernetes API, làm sao giới hạn quyền riêng?

**Bài D — nhiều tenant:** Tenant A và B chạy mã không tin cậy. So sánh namespace-only, node pool riêng, sandbox runtime và cluster riêng; đưa ra quyết định theo mức rủi ro, độ nhạy dữ liệu và khả năng vận hành.

**Bài E — sự cố DNS:** Sau khi bật default deny, ứng dụng gặp lỗi UnknownHostException. Hãy đưa ra thứ tự chẩn đoán và phân biệt vấn đề DNS egress, resolver thực tế, tên service sai và lỗi network tới dịch vụ đích.

**Bài F — đặc quyền container:** Deployment Java chạy root, mount hostPath và automount ServiceAccount token. Hãy viết bản securityContext an toàn hơn, nêu các trường hợp filesystem cần ghi và cách kiểm tra readiness sau thay đổi.

**Bài G — quyền triển khai:** Deploy bot có quyền update Deployment ở commerce nhưng không được sửa Secret ở payments hoặc tạo ClusterRoleBinding. Viết ma trận RBAC và các ca kiểm thử can-i, nêu nguy cơ nếu bot được tạo Pod với ServiceAccount nhạy cảm.

**Bài H — diễn tập sự cố:** Giả định một Pod web bị khai thác và thử kết nối trực tiếp DB, lấy Secret, gọi Payment API và gửi dữ liệu ra Internet. Xác định lớp nào chặn từng hành động, lớp nào vẫn phải kiểm tra quyền nghiệp vụ, và tín hiệu log/metric cần thu thập.

**Bài I — quota:** Cụm có hai namespace dùng chung node, một tenant triển khai hàng trăm worker Java. Hãy xác định ResourceQuota, LimitRange, max replicas và quota connection DB phù hợp. Giải thích vì sao quota CPU/RAM không hoàn toàn giải quyết noisy neighbor.

**Bài J — đọc YAML:** So sánh một peer chứa đồng thời namespaceSelector và podSelector với hai peer tách riêng. Hãy giải thích bằng một bảng Pod/namespace nào được cho phép và viết test chứng minh ranh giới mong muốn.

## 32. Ghi nhớ

- **NetworkPolicy** điều khiển mạng Pod ở các mức được Kubernetes/CNI hỗ trợ; muốn có tác dụng phải xác nhận plugin mạng thực thi.
- **Default deny + allow tối thiểu** là cơ sở giảm di chuyển ngang, nhưng phải thiết kế đường DNS, gateway, DB, broker và observability.
- **Policy cộng dồn**, peer trong nhiều phần tử là OR; namespaceSelector và podSelector cùng một peer được kết hợp để chọn Pod phù hợp trong namespace được chọn.
- **RBAC** chỉ quyết định quyền trên Kubernetes API; nó không tự giới hạn HTTP/TCP tới ứng dụng và không thay thế xác thực nghiệp vụ.
- **ServiceAccount riêng, tắt token automount khi không cần, quyền tối thiểu và audit** giảm tác động khi một workload bị chiếm quyền.
- **SecurityContext, Pod Security, admission policy và quota** bảo vệ đặc quyền process và tài nguyên ngoài phạm vi NetworkPolicy.
- **Namespace hữu ích để phân vùng chính sách, chưa phải cách ly host vật lý.** Tenant không đáng tin có thể cần node pool, sandbox hoặc cluster riêng.
- **Mã hóa/mTLS và phân quyền ứng dụng** vẫn cần thiết trên các luồng mạng đã được phép.
- **Kiểm thử cả positive và negative cases**, đo traffic thực, bảo vệ nhãn tin cậy, ghi version policy và chuẩn bị rollback.

Một cụm container an toàn không được xác định bởi số lượng manifest, mà bởi khả năng **chứng minh từng workload chỉ có đường mạng, quyền API, đặc quyền runtime và tài nguyên đúng với trách nhiệm của nó**. Khi các lớp bảo vệ được thiết kế nhất quán và kiểm thử trong môi trường vận hành thực, một lỗi tại một dịch vụ ít có cơ hội lan thành sự cố toàn hệ thống.
