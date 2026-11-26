# Xác thực trong cluster bằng ServiceAccount

## 1. ServiceAccount giải quyết vấn đề gì?

Khi ứng dụng Spring chạy trong Kubernetes và cần đọc ConfigMap, Secret, Service hoặc EndpointSlice qua Kubernetes API, API server phải biết request đến từ danh tính nào. ServiceAccount cung cấp danh tính cho workload trong cluster.

ServiceAccount không phải tài khoản người dùng của con người và cũng không phải credential của API nghiệp vụ. Nó là một identity namespaced được Pod sử dụng khi gọi Kubernetes API.

Một đường gọi đầy đủ có hai bước:

1. **Authentication** xác định request thuộc ServiceAccount nào.
2. **Authorization** kiểm tra ServiceAccount đó được phép làm gì bằng RBAC.

~~~text
Spring Pod
   |
   | token + CA + API endpoint
   v
kube-apiserver
   |
   +--> Authentication: đây là ServiceAccount nào?
   |
   +--> Authorization: identity này có verb/resource/scope phù hợp không?
   |
   v
Kubernetes API response
~~~

Nếu checkout chỉ gọi http://orders:8080 bằng Service DNS, nó không cần ServiceAccount có quyền list Pod để gửi HTTP. Nếu checkout dùng Spring Cloud Kubernetes Discovery hoặc Config integration dựa trên Kubernetes API, ServiceAccount và RBAC trở thành một phần của thiết kế.

## 2. ServiceAccount và User khác nhau

Kubernetes có thể xác thực nhiều loại danh tính:

- người vận hành dùng certificate, token hoặc cơ chế tích hợp;
- controller dùng ServiceAccount;
- Pod dùng ServiceAccount được gán;
- hệ thống bên ngoài dùng identity được cluster hỗ trợ.

ServiceAccount được định danh theo namespace và tên, có dạng khái niệm:

~~~text
system:serviceaccount:<namespace>:<name>
~~~

Ví dụ ServiceAccount tên checkout trong namespace shop được nhận diện khác với ServiceAccount checkout trong namespace staging.

Không nên dùng ServiceAccount mặc định cho mọi workload. Dùng danh tính riêng giúp:

- ghi rõ ứng dụng nào đang gọi API;
- cấp quyền theo đúng nhu cầu;
- thu hồi hoặc thay đổi quyền của một workload riêng;
- đọc audit log dễ hơn;
- tránh một ứng dụng thừa hưởng quyền của ứng dụng khác.

Tạo ServiceAccount không tự cấp quyền đọc resource. Quyền đến từ Role, ClusterRole và Binding.

## 3. Gán ServiceAccount cho Pod

Manifest tối thiểu:

~~~yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: checkout
  namespace: shop
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: checkout
  namespace: shop
spec:
  replicas: 1
  selector:
    matchLabels:
      app: checkout
  template:
    metadata:
      labels:
        app: checkout
    spec:
      serviceAccountName: checkout
      containers:
        - name: checkout
          image: registry.example.com/checkout:1.0.0
~~~

Trường serviceAccountName nằm trong Pod template. Với Deployment, mọi Pod mới tạo từ template sẽ dùng ServiceAccount checkout. Pod đã tồn tại không tự đổi identity chỉ vì Deployment template được sửa; rollout hoặc thay Pod là một phần của quy trình cập nhật.

Nếu không chỉ rõ serviceAccountName, Pod có thể dùng ServiceAccount mặc định trong namespace theo cấu hình cluster. Không nên dựa vào hành vi mặc định cho workload cần quyền đặc biệt.

## 4. Token trong cluster

### 4.1. Client trong cluster lấy thông tin gì?

Một Kubernetes client chạy trong Pod thường cần:

- endpoint API server;
- CA certificate để xác minh server;
- token hoặc credential của ServiceAccount;
- namespace mặc định nếu client cần giới hạn phạm vi.

Kubernetes có thể đưa thông tin ServiceAccount vào Pod qua projected volume. Đường dẫn thường gặp trong container là:

~~~text
/var/run/secrets/kubernetes.io/serviceaccount/token
/var/run/secrets/kubernetes.io/serviceaccount/ca.crt
/var/run/secrets/kubernetes.io/serviceaccount/namespace
~~~

Đây là đường dẫn phổ biến, không nên coi là hợp đồng để ứng dụng tự hard-code trong mọi môi trường. Client library thường cung cấp cơ chế in-cluster configuration để đọc thông tin theo cách phù hợp.

Spring Cloud Kubernetes và client library bên dưới có thể dùng in-cluster configuration khi ứng dụng chạy trong Pod. Ứng dụng thường không cần tự viết code đọc token nếu integration đã hỗ trợ cách cấu hình này.

### 4.2. Token không phải mật khẩu ứng dụng

ServiceAccount token dùng để xác thực với Kubernetes API. Nó không tự xác thực checkout với orders và không nên được gửi vào header của API nghiệp vụ trừ khi đó là một thiết kế identity rõ ràng, được bảo vệ riêng.

Không:

- đưa token vào image;
- commit token vào source;
- ghi token vào log;
- truyền token qua URL;
- dùng token Kubernetes làm credential chung cho nhiều API.

Nếu orders cần xác thực checkout, dùng cơ chế authentication của API nghiệp vụ, mTLS, workload identity hoặc token audience phù hợp theo thiết kế bảo mật của hệ thống.

### 4.3. Token ngắn hạn và projected token

Các cluster hiện đại thường dùng ServiceAccount token có thời hạn và audience. Token có thể được kubelet hoặc cơ chế projected volume cập nhật khi sắp hết hạn. Ứng dụng hoặc client library cần đọc và refresh theo cách được hỗ trợ, thay vì giả định token là chuỗi vĩnh viễn.

Một client tự giữ token trong memory phải biết thời hạn của token và cách refresh. Thông thường nên dùng thư viện Kubernetes hoặc integration đã xử lý in-cluster authentication.

Audience của token cũng quan trọng. Token dành cho một audience không nhất thiết hợp lệ với một API khác. Không mở rộng audience tùy tiện chỉ để làm lỗi authentication biến mất.

## 5. Authentication không phải authorization

Authentication trả lời “đây là ai?”. Authorization trả lời “identity này được phép làm gì?”.

Ví dụ:

- Token hợp lệ xác thực request là ServiceAccount checkout.
- RBAC không có rule phù hợp khiến request bị từ chối 403.
- Token hết hạn hoặc sai CA có thể khiến authentication hoặc TLS thất bại.
- API server không truy cập được là lỗi kết nối, không phải lỗi RBAC.

Bảng phân loại:

| Hiện tượng | Lớp cần kiểm tra |
| --- | --- |
| Không kết nối được API server | DNS, route, Service và port API |
| TLS certificate không hợp lệ | CA bundle, endpoint và trust configuration |
| 401 Unauthorized | Token, audience, expiration hoặc authentication |
| 403 Forbidden | Role, ClusterRole, Binding, verb, resource và namespace |
| 404 Not Found | API path, group/version hoặc tên resource |
| Request thành công nhưng không có dữ liệu | Selector, namespace, resource state và filter |

Không giải quyết 403 bằng cách thay token nếu token đã xác thực đúng nhưng identity không có quyền. Khi đó cần điều chỉnh RBAC theo nguyên tắc tối thiểu.

## 6. Role giới hạn trong một namespace

Giả sử checkout cần đọc ConfigMap tên checkout-settings trong namespace shop. Có thể tạo Role:

~~~yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: checkout-config-reader
  namespace: shop
rules:
  - apiGroups: [""]
    resources: ["configmaps"]
    resourceNames: ["checkout-settings"]
    verbs: ["get"]
~~~

Role này thể hiện phạm vi hẹp:

- core API group được biểu diễn bằng chuỗi rỗng;
- chỉ đọc ConfigMap;
- chỉ một resource name;
- chỉ verb get;
- chỉ namespace shop.

Không phải mọi thư viện đều chỉ dùng get một tên cụ thể. Một integration có thể cần list và watch để tìm hoặc theo dõi resource. Quyền phải khớp behavior thực tế của integration, nhưng không nên thêm list/watch chỉ vì thuận tiện khi chưa cần.

Binding ServiceAccount vào Role:

~~~yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: checkout-config-reader
  namespace: shop
subjects:
  - kind: ServiceAccount
    name: checkout
    namespace: shop
roleRef:
  kind: Role
  name: checkout-config-reader
  apiGroup: rbac.authorization.k8s.io
~~~

RoleBinding là namespaced. Subject ServiceAccount cần ghi đúng namespace; RoleBinding trong shop không làm ServiceAccount checkout ở namespace khác được quyền.

## 7. Role cho DiscoveryClient

Nếu DiscoveryClient cần đọc Service và EndpointSlice trong namespace shop, ví dụ khái niệm:

~~~yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: checkout-discovery-reader
  namespace: shop
rules:
  - apiGroups: [""]
    resources: ["services"]
    verbs: ["get", "list", "watch"]
  - apiGroups: ["discovery.k8s.io"]
    resources: ["endpointslices"]
    verbs: ["get", "list", "watch"]
~~~

Binding:

~~~yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: checkout-discovery-reader
  namespace: shop
subjects:
  - kind: ServiceAccount
    name: checkout
    namespace: shop
roleRef:
  kind: Role
  name: checkout-discovery-reader
  apiGroup: rbac.authorization.k8s.io
~~~

Resource và verb cụ thể phụ thuộc implementation, phiên bản và cách discovery được cấu hình. Có integration đọc Endpoints, có integration dùng EndpointSlice hoặc đọc thêm resource liên quan. Không sao chép rule này mà không kiểm tra nhu cầu thực tế.

Nếu checkout chỉ dùng DNS Service, không cần Role discovery này.

## 8. ClusterRole và khi nào cần phạm vi cluster

ClusterRole có thể mô tả quyền cấp cluster hoặc quyền có thể bind vào một namespace. Dùng ClusterRoleBinding sẽ cấp quyền theo phạm vi cluster cho subject, nên cần thận trọng.

Chỉ cân nhắc phạm vi cluster khi yêu cầu thật sự là:

- discovery trên nhiều namespace;
- controller quản lý resource toàn cluster;
- policy hoặc operator cần đọc resource cấp cluster;
- một integration được thiết kế rõ để quan sát nhiều namespace.

Nếu ứng dụng chỉ đọc ConfigMap và Service trong shop, Role và RoleBinding trong shop thường dễ kiểm tra hơn.

Một ClusterRole có thể được bind vào một namespace bằng RoleBinding, nhưng cần đọc rõ namespace của binding và resource scope. Không suy ra rằng mọi ClusterRole đều buộc phải dùng ClusterRoleBinding.

## 9. Automount và giảm bề mặt credential

Pod có thể tự động nhận ServiceAccount token theo cấu hình. Nếu workload không gọi Kubernetes API, có thể cân nhắc tắt automount cho Pod hoặc ServiceAccount:

~~~yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: orders
  namespace: shop
automountServiceAccountToken: false
~~~

Hoặc ở Pod:

~~~yaml
spec:
  automountServiceAccountToken: false
  containers:
    - name: orders
      image: registry.example.com/orders:1.0.0
~~~

Không tắt token một cách máy móc nếu Spring Cloud Kubernetes integration cần gọi API. Cần xác định workload nào thực sự cần identity Kubernetes.

Nếu Pod có sidecar hoặc agent cần token, việc tắt ở Pod có thể ảnh hưởng thành phần đó. Phạm vi automount phải được đánh giá cùng toàn bộ Pod design.

Nguyên tắc là không đưa credential Kubernetes vào workload chỉ gọi HTTP Service. Giảm token không cần thiết giúp hạn chế tác động khi một container bị khai thác.

## 10. ServiceAccount cho Spring Cloud Kubernetes

Trước khi bật discovery hoặc config integration, ghi rõ:

~~~text
Workload: checkout
Namespace: shop
ServiceAccount: checkout
API resources: ConfigMap, Service, EndpointSlice
Verbs: get/list/watch theo integration
Scope: namespace shop
Fallback: giá trị cache hoặc fail startup theo chính sách
~~~

Spring Cloud Kubernetes có thể dùng Kubernetes client library để tự nhận in-cluster configuration. Ứng dụng cần cấu hình đúng namespace, tên resource và mode discovery/config. Tên property và starter phải khớp phiên bản dependency của dự án.

Nếu integration không cần API server vì ConfigMap được inject bằng env hoặc volume, không bật client API chỉ để đọc lại dữ liệu đã có trong Pod.

Khi API server tạm thời lỗi:

- discovery có thể dùng danh sách cache trong thời gian giới hạn;
- config có thể dùng giá trị hiện hành;
- startup có thể fail nếu cấu hình bắt buộc;
- watcher cần reconnect;
- ứng dụng phải có metric để cho biết dữ liệu đã cũ.

Các lựa chọn này là chính sách ứng dụng, không tự sinh ra từ ServiceAccount.

## 11. Kiểm tra quyền của ServiceAccount

Người vận hành có thể kiểm tra quyền dự kiến bằng auth can-i:

~~~bash
kubectl auth can-i get configmaps/checkout-settings \
  --as=system:serviceaccount:shop:checkout -n shop

kubectl auth can-i list endpointslices \
  --as=system:serviceaccount:shop:checkout -n shop

kubectl auth can-i list secrets \
  --as=system:serviceaccount:shop:checkout -n shop
~~~

Kết quả mong muốn trong ví dụ:

- get ConfigMap cần thiết: yes;
- list EndpointSlice nếu discovery cần: yes;
- list Secret khi không dùng Secret: no.

Lệnh này kiểm tra authorization theo policy hiện tại. Nó không chứng minh Pod có thể kết nối API server, token còn hạn, CA đúng hoặc integration dùng đúng namespace.

Không cấp quyền list Secret chỉ để thử xem RBAC có hoạt động hay không. Kiểm tra đúng resource cần thiết và thu hồi quyền tạm thời sau chẩn đoán.

## 12. Kiểm tra từ bên trong Pod

Khi cần chẩn đoán sâu, một client trong Pod có thể gọi API server bằng token và CA theo cơ chế được cluster hỗ trợ. Tuy nhiên, không nên in token ra terminal hoặc log.

Một quy trình an toàn hơn:

1. Xác định Pod dùng ServiceAccount nào.
2. Kiểm tra Role và Binding bằng quyền người vận hành.
3. Dùng auth can-i để kiểm tra authorization.
4. Xem event và log của integration.
5. Kiểm tra endpoint API, CA và lỗi TLS mà không tiết lộ credential.
6. Chỉ gọi resource tối thiểu cần kiểm tra.

Ứng dụng production không nên tích hợp lệnh shell chẩn đoán vào health endpoint. Health endpoint không nên đọc toàn bộ Secret hoặc list mọi resource chỉ để báo “UP”.

## 13. Token và rotation

Khi token được cấp theo projected volume, nội dung file có thể được thay đổi trong vòng đời Pod. Client library cần biết cách reload token hoặc tạo request bằng credential mới.

Không đọc token một lần ở static initializer rồi giữ mãi nếu token có thời hạn. Nếu thư viện được dùng đã cung cấp in-cluster authentication và refresh, ưu tiên cơ chế đó.

Khi rotation hoặc đổi Role:

- request mới có thể thấy quyền mới sau khi policy được cập nhật;
- client không nên cache authorization decision vô thời hạn;
- token mới không tự mở quyền nếu RBAC chưa đổi;
- token cũ không nên được coi là an toàn sau khi identity bị thu hồi;
- cần theo dõi lỗi 401 và 403 riêng.

Token authentication và RBAC update là hai sự kiện khác nhau. Đổi một không tự đổi sự kiện kia.

## 14. Những lỗi phổ biến

### Pod dùng nhầm ServiceAccount

Deployment không có serviceAccountName hoặc template chưa rollout. Kiểm tra identity của Pod thật, không chỉ manifest mong muốn.

### ServiceAccount tồn tại nhưng bị 403

Có thể thiếu RoleBinding, binding trỏ sai tên, resource sai apiGroup, verb thiếu hoặc namespace không đúng.

### Token có nhưng API vẫn từ chối

Kiểm tra expiration, audience, CA, endpoint và clock của môi trường. Không mở quyền rộng hơn trước khi xác định lớp lỗi.

### Config integration đọc được một resource nhưng không watch được

get/list thành công không đồng nghĩa watch được. Cần kiểm tra verb watch và behavior của integration.

### Discovery đọc Service nhưng không có instance

Kiểm tra EndpointSlice, selector, readiness, namespace và cách integration lọc endpoint. Quyền API chỉ là một phần của đường discovery.

### Tắt automount làm ứng dụng lỗi

Workload hoặc sidecar thật sự cần Kubernetes API. Khôi phục ở phạm vi cần thiết và cấp quyền tối thiểu thay vì bật quyền cluster-wide.

### Dùng token Kubernetes cho API nghiệp vụ

Hai trust domain bị trộn lẫn. Thiết kế lại authentication của API nghiệp vụ và chỉ dùng ServiceAccount token cho Kubernetes API khi cần.

## 15. Bài tập thiết kế quyền

Giả sử checkout có ba chế độ:

| Chế độ | Nhu cầu | Quyền dự kiến |
| --- | --- | --- |
| DNS only | Gọi orders bằng Service | Không cần đọc Kubernetes API |
| Config startup | Đọc ConfigMap lúc startup qua API | get ConfigMap cụ thể |
| Discovery runtime | Theo dõi Service và EndpointSlice | get/list/watch resource discovery |

Hãy tạo ServiceAccount riêng cho checkout và chọn Role theo chế độ. Không dùng một ClusterRole có quyền đọc Pod, Secret, Service và ConfigMap chỉ vì có thể dùng cho cả ba.

Nếu sau này bật Configuration Watcher, cập nhật thiết kế thành một thay đổi có kiểm soát:

- resource mới cần watch là gì;
- namespace nào;
- verb nào;
- cấu hình mới áp dụng ra sao;
- API mất kết nối thì fallback thế nào;
- log và metric nào chứng minh watcher đang hoạt động.

## 16. Quy trình triển khai an toàn

1. Tạo ServiceAccount riêng trong namespace workload.
2. Gán ServiceAccount vào Pod template.
3. Xác định chính xác resource và verb integration cần.
4. Tạo Role trong namespace nếu phạm vi namespace đủ.
5. Tạo RoleBinding trỏ đúng ServiceAccount.
6. Kiểm tra auth can-i với danh tính đầy đủ.
7. Triển khai một replica và quan sát log authentication/authorization.
8. Kiểm tra hành vi khi API server tạm thời không truy cập được.
9. Bảo vệ token, Secret và log.
10. Chỉ mở rộng sang ClusterRole khi có yêu cầu được ghi rõ.

Không dùng quyền quản trị cluster để chữa lỗi cấu hình namespace. Không dùng token của người vận hành trong image hoặc Secret của ứng dụng.

## 17. Kết luận

ServiceAccount cung cấp danh tính cho Pod khi gọi Kubernetes API. Token và CA giúp client xác thực với API server; RBAC quyết định identity đó được phép đọc hoặc watch resource nào. Tạo ServiceAccount không tự cấp quyền, và có token hợp lệ không đồng nghĩa request được authorization.

Với Spring Cloud Kubernetes, hãy tách ba trường hợp: gọi Service qua DNS không nhất thiết cần Kubernetes API; discovery hoặc config integration có thể cần ServiceAccount và Role; watcher cần thêm quyền watch và cơ chế reconnect. Dùng identity riêng, Role namespaced và quyền tối thiểu giúp ứng dụng dễ kiểm tra hơn và giảm tác động khi credential hoặc container bị lộ.

Authentication trong cluster là nền tảng cho DiscoveryClient, ConfigMap, Secret và Configuration Watcher, nhưng nó không thay thế authentication của API nghiệp vụ giữa các service.
