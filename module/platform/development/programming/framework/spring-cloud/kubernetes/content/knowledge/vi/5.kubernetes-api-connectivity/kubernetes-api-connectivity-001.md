# Địa chỉ API server và thông tin truy cập

## 1. API server là điểm nào trong kiến trúc?

Kubernetes API server là cổng HTTP(S) trung tâm để client đọc và thay đổi tài nguyên Kubernetes. Kubernetes client trong ứng dụng Spring Cloud Kubernetes không gọi trực tiếp kubelet hay database của control plane. Nó gửi request tới API server, kèm thông tin xác thực và yêu cầu tài nguyên cụ thể.

Luồng đơn giản:

~~~text
Ứng dụng Spring
    |
    | HTTPS + credential + API path
    v
Kubernetes API server
    |
    +-- xác minh TLS và danh tính
    +-- kiểm tra authentication
    +-- kiểm tra authorization/RBAC
    '-- đọc hoặc thay đổi resource
~~~

Để request thành công, ít nhất bốn điều kiện phải đúng:

1. Client biết địa chỉ và cổng API server.
2. Client thiết lập được kết nối mạng và TLS.
3. Client trình bày credential hợp lệ.
4. Danh tính có quyền trên resource, verb và namespace được yêu cầu.

Một bean Kubernetes client được tạo trong ApplicationContext chỉ chứng minh Spring đã khởi tạo được client. Nó chưa chứng minh API server truy cập được hoặc ServiceAccount có quyền discovery, ConfigMap, Secret hay watch.

Bài học thuộc phần **Kết nối Kubernetes API** của module **Spring Cloud Kubernetes**. Mục tiêu là hiểu nguồn địa chỉ API server và thông tin truy cập trong local, CI và Pod, từ đó cấu hình DiscoveryClient, ConfigMap, Secret hoặc Configuration Watcher đúng phạm vi.

## 2. Địa chỉ API server trong cluster

Trong cluster, API server thường được công bố qua một Service nội bộ có tên quen thuộc là kubernetes trong namespace hệ thống. Một client trong Pod có thể dùng DNS nội bộ tương ứng, thường có dạng:

~~~text
https://kubernetes.default.svc
~~~

Nhiều môi trường dùng cổng HTTPS 443. Tuy nhiên, client không nên hard-code hostname và port chỉ dựa trên một cluster cụ thể. Thư viện in-cluster configuration có thể lấy endpoint từ biến môi trường được Kubernetes đưa vào Pod hoặc từ cấu hình triển khai.

Một số biến môi trường thường xuất hiện trong Pod:

~~~text
KUBERNETES_SERVICE_HOST
KUBERNETES_SERVICE_PORT
~~~

Các biến này mô tả địa chỉ Service API nội bộ theo cách nền tảng cung cấp. Ứng dụng Spring nên để Kubernetes client hoặc integration đọc cấu hình in-cluster thay vì tự viết logic ghép URL nếu thư viện đã hỗ trợ.

Kiểm tra endpoint không đồng nghĩa kiểm tra quyền. DNS có thể phân giải và TCP có thể kết nối trong khi API trả 401 hoặc 403. Ngược lại, request có credential đúng vẫn thất bại nếu NetworkPolicy, proxy hoặc route không cho phép tới API server.

## 3. Địa chỉ API server ngoài cluster

Khi chạy local hoặc trong CI ngoài cluster, client thường lấy server URL từ kubeconfig:

~~~yaml
clusters:
  - name: dev-cluster
    cluster:
      server: https://api.dev.example:6443
      certificate-authority-data: <base64-ca>
~~~

Kubeconfig ghép ba phần:

~~~text
cluster
  -> API server URL + CA

user
  -> token, certificate hoặc exec credential

context
  -> cluster + user + namespace
~~~

Context hiện tại quyết định cluster và user mà công cụ hoặc client sử dụng nếu không có override. Đây là nguồn rủi ro lớn trên máy có nhiều cluster: ứng dụng có thể gọi nhầm môi trường hoặc dùng credential rộng hơn dự kiến.

Trong CI, chỉ dùng kubeconfig tạm với quyền tối thiểu. Không đưa kubeconfig quản trị vào image hoặc commit vào repository. Nếu client hỗ trợ chỉ định đường dẫn kubeconfig hoặc context bằng biến môi trường, cần ghi lại precedence giữa biến đó, property Spring và command-line.

Kubeconfig local không đại diện cho cấu hình in-cluster. Việc local gọi API thành công bằng user quản trị không chứng minh Pod production có thể gọi API bằng ServiceAccount của nó.

## 4. TLS và CA

API server thường được truy cập qua HTTPS. Client cần xác minh chứng thư máy chủ bằng CA phù hợp. CA trả lời câu hỏi: “Tôi có thể tin rằng endpoint này là API server mà tôi định kết nối không?”

Trong Pod, CA của cluster thường được cấp qua volume ServiceAccount hoặc cơ chế triển khai tương ứng. Ngoài cluster, CA có thể nằm trong kubeconfig dưới dạng dữ liệu nhúng hoặc đường dẫn file.

Các lỗi phổ biến:

- Server URL dùng hostname không khớp chứng thư.
- CA không được đọc hoặc trỏ nhầm file.
- Client dùng truststore không chứa CA của cluster.
- Proxy thay chứng thư nhưng client chưa tin CA của proxy.
- Môi trường local dùng endpoint khác với endpoint trong kubeconfig.

Không tắt xác minh TLS để vượt qua lỗi:

~~~text
verifySsl=false
trustAll=true
skipTlsVerify=true
~~~

Tên property có thể khác nhau, nhưng ý tưởng đều làm giảm bảo vệ xác minh máy chủ. Nếu cần điều tra, chỉ dùng trong môi trường cô lập với thời gian ngắn và sửa nguyên nhân CA/hostname trước khi triển khai. Không đưa cấu hình trust-all vào production.

Phân biệt CA và token:

~~~text
CA
  -> xác minh danh tính của máy chủ

Token/certificate của client
  -> xác minh danh tính của bên gọi

RBAC
  -> quyết định danh tính đó được làm gì
~~~

Có CA đúng nhưng token sai vẫn không xác thực được. Có token đúng nhưng CA sai vẫn không thiết lập được kết nối TLS.

## 5. Thông tin xác thực trong Pod

### 5.1. ServiceAccount

Pod có thể dùng ServiceAccount riêng:

~~~yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: order-runtime
  namespace: shop
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: order-service
  namespace: shop
spec:
  template:
    spec:
      serviceAccountName: order-runtime
      containers:
        - name: app
          image: example/order-service:1.0
~~~

ServiceAccount tạo danh tính cho Pod, không tự cấp quyền. Role và RoleBinding mới quyết định danh tính được đọc hoặc thay đổi resource nào.

Client trong Pod thường có thể đọc:

- Token ServiceAccount theo vị trí volume được mount.
- CA của cluster theo vị trí volume tương ứng.
- Namespace của Pod qua file được mount hoặc property.
- Địa chỉ API server qua in-cluster detection.

Vị trí file và cách đọc có thể phụ thuộc phiên bản Kubernetes, security settings và client Java. Ứng dụng nên dùng cơ chế được client hỗ trợ thay vì giả định mọi file luôn tồn tại.

### 5.2. Token không phải quyền

Token chỉ giúp API server nhận diện bên gọi. Nếu RoleBinding thiếu quyền:

~~~text
token hợp lệ
    + danh tính đúng
    - thiếu rule RBAC
    = 403 Forbidden
~~~

Ứng dụng dùng DiscoveryClient có thể cần đọc Service và EndpointSlice. Ứng dụng đọc ConfigMap hoặc Secret cần rule trên resource tương ứng. Configuration Watcher cần watch đúng API group và namespace.

Không cấp cluster-admin chỉ để kiểm tra token. Hãy xác định request thất bại rồi cấp quyền nhỏ nhất có thể.

### 5.3. Tắt token khi không cần API

Nếu Pod chỉ gọi Service bằng DNS, không tự đọc Kubernetes API và không có sidecar cần token, có thể cân nhắc tắt tự gắn token ServiceAccount:

~~~yaml
spec:
  automountServiceAccountToken: false
~~~

Chỉ áp dụng sau khi kiểm tra toàn bộ container và sidecar trong Pod. Một ứng dụng có thể không gọi API trực tiếp nhưng thư viện hoặc agent đi kèm lại cần token.

## 6. RBAC gắn với request cụ thể

Role trong một namespace có thể cấp quyền đọc API:

~~~yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: order-api-reader
  namespace: shop
rules:
  - apiGroups: [""]
    resources: ["services"]
    verbs: ["get", "list", "watch"]
  - apiGroups: ["discovery.k8s.io"]
    resources: ["endpointslices"]
    verbs: ["get", "list", "watch"]
~~~

Binding với ServiceAccount:

~~~yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: order-api-reader
  namespace: shop
subjects:
  - kind: ServiceAccount
    name: order-runtime
    namespace: shop
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: Role
  name: order-api-reader
~~~

Bảng kiểm tra:

| Thành phần | Phải khớp với |
|---|---|
| API group | Group của resource client gọi |
| Resource | Service, EndpointSlice, ConfigMap, Secret hoặc resource thật |
| Verb | get, list, watch theo hành vi integration |
| Namespace | Namespace mà client đang đọc |
| Subject | ServiceAccount được gán cho Pod |
| roleRef | Role/ClusterRole có rule phù hợp |

EndpointSlice thuộc API group discovery.k8s.io, còn Service, ConfigMap và Secret thuộc core API group rỗng. Nhầm API group là lý do thường gặp khiến client có token nhưng vẫn nhận 403.

## 7. Địa chỉ API server và namespace không phải một thứ

API server là endpoint control plane. Namespace là phạm vi logic của resource namespaced. Ví dụ:

~~~text
API server: https://kubernetes.default.svc
Namespace đọc: shop
Resource: EndpointSlice/inventory-service-abcde
~~~

Đổi namespace không đổi API server. Đổi API server không tự cấp quyền cho namespace mới.

Một ứng dụng có thể gọi cùng API server nhưng:

- Đọc Service ở namespace shop.
- Đọc ConfigMap ở namespace config.
- Không được phép đọc Secret ở namespace security.

Mỗi phạm vi cần được thiết kế và binding tương ứng. Nếu discovery cần nhiều namespace, hãy đánh giá liệu ClusterRole có thực sự cần thiết hay có thể dùng nhiều RoleBinding theo namespace. Cấp ClusterRoleBinding toàn cluster làm tăng phạm vi khi ứng dụng bị xâm nhập.

## 8. Cấu hình trong Spring Cloud Kubernetes

Các property cụ thể phụ thuộc release train, nhưng có thể phân loại:

~~~yaml
spring:
  cloud:
    kubernetes:
      client:
        # endpoint, namespace, TLS hoặc credential tùy dòng
      discovery:
        enabled: true
      config:
        enabled: true
~~~

Không chép nguyên ví dụ property này vào mọi dự án mà không kiểm tra metadata của dependency. Tên nhóm có thể khác giữa các dòng client hoặc cách tích hợp.

Khi cấu hình, hãy xác định:

- API URL lấy từ in-cluster, kubeconfig hay property?
- Client có tự phát hiện ServiceAccount token không?
- CA lấy từ volume, kubeconfig hay truststore?
- Namespace lấy từ context, file Pod hay property?
- Property nào override property nào?
- Discovery và config có dùng cùng client bean không?
- Đang bật tính năng nào thực sự cần?

Một ứng dụng có thể dùng Service/DNS cho lời gọi nghiệp vụ, ConfigMap mount cho cấu hình khởi động và Actuator probe cho sức khỏe. Trong thiết kế này, Pod có thể không cần gọi Kubernetes API. Không thêm quyền RBAC chỉ vì module có khả năng discovery.

Nếu bật ConfigMap/Secret integration, xác định rõ dữ liệu được đọc qua API hay file mount. Nếu bật DiscoveryClient, xác định resource và verb. Nếu dùng Configuration Watcher, xác định watcher hay ứng dụng là bên gọi API.

## 9. Proxy và đường mạng tới API server

API server có thể nằm sau proxy, load balancer hoặc mạng private. Client cần biết:

- Proxy có áp dụng cho hostname API server không?
- NO_PROXY có chứa hostname nội bộ và service CIDR phù hợp không?
- NetworkPolicy có cho Pod đi tới API server không?
- DNS của Service API có phân giải trong namespace của Pod không?
- Cổng 443 hoặc cổng kubeconfig có được mở không?
- Proxy có thay chứng thư TLS không?

Timeout giúp phân biệt lỗi mạng với lỗi API:

| Hiện tượng | Hướng kiểm tra |
|---|---|
| DNS failure | Resolver, Service API, search domain |
| Connection refused | Cổng, route, endpoint |
| Timeout | NetworkPolicy, proxy, firewall, API server tải cao |
| TLS handshake failure | CA, hostname, proxy certificate |
| 401 | Token hoặc credential |
| 403 | RBAC |
| 404 | API path, resource version, URL hoặc namespace |

Không thử bằng cách gọi một endpoint không được phép rồi coi 403 là lỗi mạng. Cần dùng một request an toàn và biết trước expected result trong môi trường kiểm thử.

## 10. Kiểm tra thông tin truy cập an toàn

Một quy trình điều tra trong Pod:

1. Xác định serviceAccountName trong workload.
2. Kiểm tra Pod có được cấp thông tin in-cluster không.
3. Xác nhận endpoint client đang chọn, chỉ log hostname/port không nhạy cảm.
4. Kiểm tra CA có được nạp mà không in nội dung certificate private key.
5. Xác nhận token hiện diện bằng boolean hoặc metadata an toàn, không in token.
6. Kiểm tra namespace hiệu lực.
7. Thử một request read-only phù hợp với Role.
8. Đối chiếu 401, 403, TLS và timeout.
9. Kiểm tra cache/watch nếu discovery hoặc config đã khởi động.
10. Ghi lại nguồn cấu hình và profile, không ghi secret value.

Có thể dùng công cụ quản trị với danh tính ServiceAccount để kiểm tra quyền:

~~~text
kubectl auth can-i get services \
  --as=system:serviceaccount:shop:order-runtime \
  -n shop

kubectl auth can-i list endpointslices \
  --api-group=discovery.k8s.io \
  --as=system:serviceaccount:shop:order-runtime \
  -n shop
~~~

Các lệnh này là ví dụ điều tra bên ngoài ứng dụng. Kết quả cần được đối chiếu với request thật của integration. Một lệnh can-i thành công trên Service không chứng minh EndpointSlice hoặc ConfigMap cũng được phép.

## 11. Kubeconfig, in-cluster và precedence

Một client có thể hỗ trợ nhiều nguồn cùng lúc. Khi đó phải biết thứ tự ưu tiên thực tế. Các khả năng thường gặp:

~~~text
command-line/property cụ thể
    -> biến môi trường
    -> cấu hình ứng dụng
    -> kubeconfig/context
    -> in-cluster detection
~~~

Đây chỉ là sơ đồ cần kiểm chứng, không phải thứ tự chung cho mọi thư viện. Kubeconfig có thể được chọn trước nếu đường dẫn explicit được đặt. Một property Spring có thể override giá trị client mặc định. Một profile cluster có thể ghi đè profile base.

Rủi ro khi không biết precedence:

- Local dùng nhầm context dù tưởng đang dùng in-cluster.
- Endpoint production bị override bởi property dev.
- Namespace trong kubeconfig khác namespace trong Pod.
- Credential cũ thắng credential mới.
- Test chạy qua kubeconfig quản trị và che lỗi RoleBinding.

Nên thiết kế mỗi môi trường với nguồn chính rõ ràng và loại bỏ nguồn cạnh tranh. In log tên profile, nguồn mode hoặc endpoint đã che dữ liệu nhạy cảm; tránh in toàn bộ environment.

## 12. Token và CA được thay mới

Cluster có thể thay token hoặc certificate theo vòng đời bảo mật. Client cần được đánh giá về cách đọc lại:

~~~text
Credential file thay đổi
    |
    +-- client đọc lại mỗi request/reconnect -> có thể hội tụ
    '-- client chỉ đọc lúc startup -> cần biết giới hạn và cách restart/refresh
~~~

Không giả định mọi client Java hỗ trợ token rotation giống nhau. Kiểm tra phiên bản thư viện và thử nghiệm trong môi trường không nhạy cảm. Nếu client mở watch dài, cơ chế reconnect có thể là thời điểm đọc credential mới; nếu không reconnect, token cũ có thể tiếp tục được dùng cho tới khi request fail.

Khi credential hết hạn:

- Không log token để xác định lỗi.
- Kiểm tra thời điểm cấp và cơ chế thay mới.
- Kiểm tra client có reload file hoặc cần restart.
- Tách lỗi xác thực khỏi lỗi RBAC.
- Đảm bảo retry có backoff, tránh nhiều Pod cùng reconnect dồn dập.

## 13. Các nhầm lẫn thường gặp

### “API server là địa chỉ của ứng dụng nghiệp vụ”

API server phục vụ tài nguyên Kubernetes. Service của inventory-service là endpoint nghiệp vụ khác. Không gửi request đơn hàng tới API server.

### “Có DNS kubernetes.default.svc là gọi được mọi API”

DNS chỉ giải quyết địa chỉ. TLS, token và RBAC vẫn quyết định request có thành công không.

### “ServiceAccount tự có quyền đọc resource”

ServiceAccount là danh tính. RoleBinding gắn quyền; thiếu binding hoặc rule đúng sẽ nhận 403.

### “Kubeconfig local có thể dùng nguyên trong Pod”

Kubeconfig có thể chứa credential rộng, context sai và CA không phù hợp. Pod nên dùng in-cluster configuration với ServiceAccount được giới hạn.

### “Tắt TLS verification là cách sửa lỗi CA”

Tắt xác minh làm giảm bảo mật và che nguyên nhân. Cần sửa CA, hostname hoặc proxy certificate.

### “API server timeout là lỗi RBAC”

RBAC chỉ được đánh giá sau khi request tới được API server và xác thực đủ để xử lý. Timeout cần điều tra endpoint, mạng, proxy và tải trước.

### “Chỉ cần quyền get”

Discovery hoặc watcher có thể dùng list/watch. Cần cấp đúng verb mà integration thực sự gọi, không đoán theo tên tính năng.

## 14. Checklist trước khi đưa client vào Pod

- API server endpoint trong môi trường cluster được xác định từ nguồn nào?
- Local/CI dùng kubeconfig nào và context nào?
- Pod dùng ServiceAccount riêng hay default?
- CA được cấp và client đọc từ đâu?
- Token được cấp an toàn và có thể thay mới không?
- Namespace hiệu lực là gì?
- Role/RoleBinding có đúng resource, API group và verb không?
- NetworkPolicy/proxy/NO_PROXY có cho đường tới API server không?
- Có phân biệt 401, 403, TLS và timeout trong log/metric không?
- Client có retry, timeout và watch reconnect hợp lý không?
- Discovery, ConfigMap, Secret và watcher có thực sự cần API không?
- Actuator và log có tránh lộ endpoint nhạy cảm, token, Secret và kubeconfig không?
- Test local có đang dùng quyền rộng hơn production không?
- Khi API server tạm thời không sẵn sàng, readiness/liveness phản ứng thế nào?

Địa chỉ API server chỉ là điểm bắt đầu của kết nối. Một ứng dụng Spring Cloud Kubernetes chạy ổn định cần ghép đúng endpoint, TLS, credential, namespace, RBAC và chính sách phục hồi. Khi mỗi lớp được kiểm tra bằng bằng chứng riêng, việc chọn DiscoveryClient, ConfigMap, Secret hoặc Configuration Watcher sẽ rõ ràng hơn và tránh đưa quyền hoặc thông tin truy cập thừa vào workload.
