# Khám phá nhiều namespace và điều kiện cấp quyền

## 1. Khi nào một ứng dụng cần nhìn nhiều namespace?

Namespace tạo ranh giới logic cho tài nguyên Kubernetes. Hai Service có thể cùng tên nhưng thuộc hai namespace khác nhau; ConfigMap, Secret, Pod, EndpointSlice và ServiceAccount cũng có phạm vi namespaced.

Một ứng dụng Spring thường bắt đầu với phạm vi hẹp:

~~~text
order-service ở namespace shop
    -> discovery inventory-service trong namespace shop
    -> gọi qua Service/DNS
~~~

Nhưng yêu cầu có thể mở rộng:

- Một gateway cần khám phá Service ở nhiều namespace.
- Một nền tảng nội bộ dùng các Service cùng nhãn trong các namespace tenant.
- Một watcher theo dõi ConfigMap của nhiều team.
- Một controller quản lý tài nguyên trên toàn cluster.
- Một ứng dụng cần gọi Service cùng tên ở namespace khác theo cấu hình.

Khi đó phải trả lời hai câu hỏi riêng:

1. Client có thật sự cần đọc Kubernetes API ở nhiều namespace không?
2. Nếu cần, danh tính của workload được cấp đúng quyền ở từng namespace như thế nào?

Mở phạm vi discovery làm tăng cả dữ liệu nhìn thấy, số request list/watch, độ phức tạp cache và tác động nếu credential bị lộ. Không chọn multi-namespace chỉ vì tên Service ở namespace hiện tại bị trùng.

Bài học thuộc phần **Namespace và phạm vi** của module **Spring Cloud Kubernetes**. Mục tiêu là thiết kế discovery nhiều namespace cho DiscoveryClient, ConfigMap, Secret hoặc Configuration Watcher với RBAC tối thiểu và hành vi vận hành có thể kiểm soát.

## 2. Namespace ảnh hưởng tới tên và dữ liệu

Service DNS thường chứa tên Service và namespace:

~~~text
inventory-service.shop.svc.cluster.local
~~~

Nếu client và Service ở cùng namespace, tên ngắn có thể đủ:

~~~text
inventory-service
~~~

Nếu client cần gọi Service cùng tên ở namespace khác, phải dùng tên đầy đủ hoặc nguồn discovery có namespace rõ ràng. Kubernetes không coi hai Service cùng tên ở hai namespace là một đối tượng.

Namespace cũng là một phần của đường dẫn API. Ví dụ khái quát:

~~~text
/api/v1/namespaces/shop/services/inventory-service
/apis/discovery.k8s.io/v1/namespaces/shop/endpointslices
~~~

Đổi namespace trong property không đổi quyền. Client vẫn phải có Role hoặc binding phù hợp ở namespace đích.

Phân biệt ba cách chọn đích:

| Cách | Client cần biết gì | Có cần discovery API không? |
|---|---|---|
| Gọi Service cùng namespace | Tên Service và port | Không nhất thiết |
| Gọi Service namespace khác bằng DNS đầy đủ | Tên Service, namespace, DNS suffix | Không nhất thiết |
| Lấy danh sách instance động | Service/EndpointSlice và filter | Thường có |
| Theo dõi ConfigMap/Secret nhiều namespace | Tài nguyên, namespace, watch | Có |

Nếu DNS đầy đủ đáp ứng nhu cầu, không thêm DiscoveryClient chỉ để thay thế một chuỗi hostname.

## 3. Phạm vi discovery của client

Một integration discovery có thể hỗ trợ một hoặc nhiều chế độ:

- Chỉ namespace hiện tại.
- Một namespace được cấu hình rõ.
- Danh sách namespace.
- Tất cả namespace mà ServiceAccount được phép đọc.
- Một controller trung gian tổng hợp dữ liệu.

Tên property và hành vi cụ thể phụ thuộc release train của Spring Cloud Kubernetes. Không giả định property “all namespaces” luôn có cùng tên hoặc cùng semantics. Hãy kiểm tra metadata của dependency, Condition Evaluation Report và log startup.

Luồng logic:

~~~text
Cấu hình namespace
    |
    +-- current namespace
    +-- one explicit namespace
    +-- list of namespaces
    '-- cluster-wide
         |
         v
Kubernetes client list/watch resource
         |
         v
lọc Service/EndpointSlice -> ServiceInstance
~~~

Nếu cấu hình danh sách namespace nhưng RBAC chỉ cho một namespace, client có thể khởi động rồi trả dữ liệu không đầy đủ, hoặc log lỗi khi đọc namespace còn lại. Cần xác định integration fail-fast hay bỏ qua lỗi từng namespace.

Không coi “không thấy Service” là bằng chứng Service không tồn tại. Có thể namespace filter, RBAC, label selector hoặc cache đang loại dữ liệu.

## 4. RBAC: Role và RoleBinding theo namespace

Role giới hạn rule trong một namespace:

~~~yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: gateway-discovery-reader
  namespace: shop
rules:
  - apiGroups: [""]
    resources: ["services"]
    verbs: ["get", "list", "watch"]
  - apiGroups: ["discovery.k8s.io"]
    resources: ["endpointslices"]
    verbs: ["get", "list", "watch"]
~~~

RoleBinding gắn Role với ServiceAccount:

~~~yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: gateway-discovery-shop
  namespace: shop
subjects:
  - kind: ServiceAccount
    name: gateway-runtime
    namespace: platform
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: Role
  name: gateway-discovery-reader
~~~

Điểm quan trọng: ServiceAccount nằm ở namespace platform, còn RoleBinding được tạo ở namespace shop. Binding này cho phép ServiceAccount platform dùng quyền của Role trong shop. Pod chạy ở platform vẫn có thể được cấp quyền đọc tài nguyên namespaced ở shop nếu binding đúng.

Nếu cần ba namespace, thường có thể tạo một Role và một RoleBinding tương ứng ở mỗi namespace:

~~~text
ServiceAccount platform/gateway-runtime
    + RoleBinding trong shop
    + RoleBinding trong billing
    + RoleBinding trong shipping
    -> quyền được giới hạn riêng ở từng namespace
~~~

Cách này dài hơn một binding toàn cluster nhưng dễ kiểm soát phạm vi. Khi tenant mới được thêm, tạo binding theo quy trình cấp quyền; không tự động cho mọi namespace nếu không có yêu cầu.

## 5. ClusterRole và RoleBinding

ClusterRole có thể mô tả rule dùng ở phạm vi rộng hơn, nhưng RoleBinding vẫn có thể gắn ClusterRole trong một namespace:

~~~yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: discovery-reader
rules:
  - apiGroups: [""]
    resources: ["services"]
    verbs: ["get", "list", "watch"]
  - apiGroups: ["discovery.k8s.io"]
    resources: ["endpointslices"]
    verbs: ["get", "list", "watch"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: gateway-discovery-shop
  namespace: shop
subjects:
  - kind: ServiceAccount
    name: gateway-runtime
    namespace: platform
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: discovery-reader
~~~

Dù rule nằm trong ClusterRole, RoleBinding trên chỉ gắn quyền trong namespace shop. Muốn cùng ServiceAccount đọc billing, cần binding tương ứng ở billing.

ClusterRoleBinding có phạm vi rộng hơn:

~~~yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: gateway-discovery-all
subjects:
  - kind: ServiceAccount
    name: gateway-runtime
    namespace: platform
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: discovery-reader
~~~

Binding này có thể cho phép đọc resource trên toàn cluster theo rule. Chỉ dùng khi yêu cầu thực sự là cluster-wide. Một gateway chỉ gọi ba namespace không nên mặc định nhận ClusterRoleBinding toàn cluster.

Bảng so sánh:

| Mô hình | Phạm vi quyền | Khi nên dùng |
|---|---|---|
| Nhiều Role + RoleBinding | Từng namespace | Danh sách namespace hữu hạn, ranh giới rõ |
| ClusterRole + nhiều RoleBinding | Rule dùng lại, phạm vi binding vẫn hẹp | Nhiều namespace cần cùng rule |
| ClusterRole + ClusterRoleBinding | Toàn cluster theo rule | Controller hoặc nền tảng thật sự cluster-wide |

## 6. ServiceAccount và danh tính xuyên namespace

Pod chỉ có một namespace. ServiceAccount của Pod cũng thuộc namespace đó. Nhưng RoleBinding ở namespace khác có thể gắn quyền cho ServiceAccount đã biết từ namespace của Pod.

Ví dụ:

~~~text
Pod gateway:
  namespace = platform
  serviceAccountName = gateway-runtime

Binding:
  RoleBinding namespace = shop
  subject = platform/gateway-runtime

Kết quả:
  gateway-runtime đọc được resource được Role cho phép trong shop
~~~

Không tạo ServiceAccount trùng tên trong từng namespace rồi tưởng đó là cùng một danh tính. platform/gateway-runtime và shop/gateway-runtime là hai subject khác nhau.

Khi kiểm tra \`403 Forbidden\`, hãy ghi đầy đủ subject:

~~~text
system:serviceaccount:platform:gateway-runtime
~~~

Sau đó kiểm tra RoleBinding ở namespace resource, không chỉ kiểm tra namespace của Pod. Đây là lỗi điều tra phổ biến trong hệ thống multi-namespace.

## 7. Cấp quyền đúng resource và API group

Discovery nhiều namespace thường liên quan tới Service và EndpointSlice. Config và Secret là resource khác:

| Capability | API group | Resource thường gặp |
|---|---|---|
| Service discovery | core API group | services |
| Endpoint discovery | discovery.k8s.io | endpointslices hoặc endpoints |
| ConfigMap | core API group | configmaps |
| Secret | core API group | secrets |
| Pod metadata | core API group | pods |

Không cấp quyền đọc Pod, ConfigMap và Secret chỉ vì discovery cần Service. Không cấp quyền list Secret toàn cluster cho một gateway chỉ để tìm ServiceInstance.

Verb cũng cần khớp:

- get cho một tài nguyên đã biết tên.
- list để lấy tập tài nguyên.
- watch để nhận thay đổi.
- create/update/patch/delete chỉ khi workload thật sự quản lý resource.

Một client dùng list/watch nhiều namespace có thể tạo tải đáng kể lên API server. Nếu chỉ cần gọi Service cố định, DNS tránh được phần quyền và tải đó.

## 8. Discovery nhiều namespace và Spring Cloud Kubernetes

DiscoveryClient tạo abstraction cho ứng dụng Spring hỏi ServiceInstance. Khi mở rộng nhiều namespace, cần xác định:

1. Service ID có bao gồm namespace hay chỉ là tên Service?
2. Nếu hai namespace có cùng Service name, client phân biệt bằng metadata nào?
3. Port và scheme được lấy từ Service hay EndpointSlice?
4. Endpoint chưa ready được lọc như thế nào?
5. Dữ liệu namespace nào được cache cùng nhau?
6. Một namespace bị 403 có làm toàn bộ discovery fail không?
7. Thay đổi namespace list có cần restart hay refresh động không?

Ví dụ dữ liệu mong đợi:

~~~text
shop/inventory-service
billing/inventory-service
shipping/inventory-service
~~~

Nếu ứng dụng chỉ gọi inventory-service nhưng có ba namespace cùng tên, một tên ServiceInstance không đủ để biểu diễn đích. Cần namespace-qualified service ID, property riêng hoặc Service tên khác để tránh định tuyến nhầm.

Không giả định Spring Cloud LoadBalancer tự hiểu namespace. LoadBalancer chỉ chọn từ danh sách instance mà supplier cung cấp. Namespace phải được giữ trong ServiceInstance metadata hoặc đã được chuyển thành host/DNS rõ ràng.

## 9. Cache, watch và chi phí mở rộng

Giả sử gateway theo dõi 20 namespace, mỗi namespace có một hoặc nhiều list/watch. Chi phí không chỉ là số Service:

~~~text
số namespace
  x số loại resource
  x số replica của client
  x số kết nối/watch
  -> tải lên API server, network và cache
~~~

Cần xem xét:

- Một client có dùng watch chung hay watch riêng từng namespace?
- Có list lại khi reconnect không?
- Cache có tách theo namespace không?
- Namespace bị mất quyền xử lý thế nào?
- Thời gian hội tụ sau khi Service/endpoint thay đổi là bao lâu?
- Nhiều replica có tạo watch trùng lặp không?

Watch không phải hàng đợi sự kiện với cam kết exactly-once. Client phải chịu được event mất kết nối, resync và trạng thái tạm thời cũ. Không dùng discovery cache để quyết định giao dịch không thể chịu lỗi mà không có timeout và fallback.

Nếu namespace nhiều nhưng Service ít, có thể dùng một gateway/controller tổng hợp dữ liệu thay vì để mọi ứng dụng tự watch toàn cluster. Thành phần trung gian vẫn cần vận hành và quyền, nhưng có thể giảm số client trực tiếp truy cập API.

## 10. ConfigMap và Secret trong nhiều namespace

Cấu hình nhiều namespace cần ràng buộc phạm vi chặt hơn discovery. Ví dụ gateway có thể cần đọc ConfigMap của từng tenant nhưng không được đọc Secret.

Thiết kế tách quyền:

~~~text
gateway-runtime
  -> RoleBinding shop: đọc services/endpointslices
  -> RoleBinding billing: đọc services/endpointslices
  -> không có quyền secrets
~~~

Nếu một watcher trung tâm đọc ConfigMap hoặc Secret, dùng ServiceAccount riêng cho watcher. Không dùng ServiceAccount của gateway với quyền cao hơn chỉ để chia sẻ manifest.

Khi đọc Secret nhiều namespace:

- Liệt kê chính xác Secret nào và vì sao cần đọc.
- Cân nhắc resourceNames nếu client dùng get theo tên.
- Không cấp list secrets toàn cluster nếu không cần.
- Không log giá trị Secret trong lỗi hoặc metrics.
- Xem xét secret manager hoặc mount file thay cho API access.

ConfigMap/Secret trong namespace A không tự có hiệu lực trong Pod namespace B. Client phải đọc đúng resource hoặc cơ chế đồng bộ phải sao chép dữ liệu theo policy rõ ràng.

## 11. DNS và discovery API không thay thế nhau

DNS có thể gọi Service ở namespace khác:

~~~text
http://inventory-service.shop.svc.cluster.local:8080
~~~

Cách này không yêu cầu ứng dụng list Service hoặc EndpointSlice chỉ để tìm địa chỉ. Kubernetes Service và cơ chế mạng chịu trách nhiệm backend.

Discovery API hữu ích khi ứng dụng cần:

- Danh sách instance cụ thể.
- Metadata để chọn instance.
- Service ID động.
- Tích hợp với Spring Cloud LoadBalancer.
- Theo dõi nhiều Service theo label hoặc namespace.
- Logic phân phối phía client.

Bảng chọn:

| Yêu cầu | Cách nên xem xét trước |
|---|---|
| Gọi một Service ở namespace đã biết | DNS đầy đủ |
| Gọi nhiều namespace nhưng danh sách cố định | Cấu hình nhiều URL/DNS |
| Tìm Service theo metadata | Discovery API với RBAC giới hạn |
| Theo dõi tenant động | Controller/watcher hoặc discovery có scope |
| Cấu hình từ namespace khác | Config integration với binding riêng |
| Kubelet kiểm tra health | Probe, không cần discovery API |

Không thêm cluster-wide discovery chỉ vì DNS name dài hơn.

## 12. Điều tra lỗi multi-namespace

Khi Service xuất hiện ở namespace này nhưng không xuất hiện ở namespace khác:

1. Xác nhận client thực sự cấu hình danh sách namespace nào.
2. Xác nhận Service có tồn tại trong namespace đích.
3. Kiểm tra RoleBinding ở namespace chứa Service.
4. Kiểm tra ServiceAccount của Pod.
5. Kiểm tra API group/resource/verb.
6. Kiểm tra label selector và filter.
7. Kiểm tra EndpointSlice và readiness.
8. Xem log lỗi từng namespace hay lỗi toàn bộ client.
9. Kiểm tra cache và thời điểm refresh.
10. Kiểm tra service ID có bị trùng tên không.

Bảng suy luận:

| Biểu hiện | Nguyên nhân có thể |
|---|---|
| Namespace hiện tại hoạt động, namespace khác 403 | Thiếu RoleBinding ở namespace kia |
| Cả hai namespace đều rỗng | Sai property, client, API endpoint hoặc token |
| Service thấy nhưng instance rỗng | Không có endpoint ready, thiếu EndpointSlice quyền hoặc filter sai |
| Một namespace làm startup fail toàn bộ | Integration fail-fast hoặc retry không có isolation |
| Cùng Service ID nhưng gọi nhầm tenant | Thiếu namespace trong identity/service ID |
| Chỉ local hoạt động | Local kubeconfig có quyền rộng hơn Pod |
| Watch ngắt theo chu kỳ | Proxy, idle timeout hoặc reconnect/resync |

Một lệnh kiểm tra quyền cần dùng đúng subject và namespace resource:

~~~text
kubectl auth can-i list services \
  --as=system:serviceaccount:platform:gateway-runtime \
  -n shop

kubectl auth can-i list services \
  --as=system:serviceaccount:platform:gateway-runtime \
  -n billing
~~~

Kết quả một namespace không đại diện cho namespace khác.

## 13. Thiết kế cô lập lỗi

Trong discovery nhiều namespace, một namespace lỗi không nhất thiết phải làm mọi Service mất khỏi ứng dụng. Cần biết integration có hỗ trợ:

- Cache dữ liệu cũ theo namespace.
- Bỏ qua lỗi một namespace và cảnh báo.
- Retry độc lập theo namespace.
- Giới hạn timeout cho từng namespace.
- Health indicator riêng cho discovery.
- Fallback sang DNS hoặc cấu hình tĩnh.

Nếu mọi namespace dùng một request/stream chung, một lỗi có thể ảnh hưởng toàn bộ cache. Nếu mỗi namespace có watcher riêng, số connection tăng nhưng isolation tốt hơn. Đây là trade-off cần đo bằng workload và API server capacity.

Không dùng liveness để khởi động lại Pod chỉ vì một namespace tenant tạm thời không truy cập được. Readiness nên phản ánh khả năng phục vụ yêu cầu quan trọng, không phải mọi dependency optional.

## 14. Các nhầm lẫn thường gặp

### “ClusterRole luôn cần cho nhiều namespace”

Không nhất thiết. Nhiều RoleBinding dùng chung ClusterRole vẫn có thể giới hạn phạm vi theo từng namespace.

### “Role trong namespace của Pod áp dụng cho mọi namespace”

Role chỉ namespaced. Muốn đọc namespace khác cần binding tương ứng ở namespace chứa resource.

### “ServiceAccount cùng tên là cùng danh tính”

Danh tính gồm cả namespace. platform/gateway-runtime khác shop/gateway-runtime.

### “Discovery thấy Service là chắc chắn gọi được”

Cần EndpointSlice, port, readiness, mạng và connection behavior. Service metadata chưa chứng minh backend hoạt động.

### “Một Service ID không cần namespace”

Nếu nhiều namespace có cùng tên, Service ID phải có cách phân biệt, nếu không client có thể chọn sai instance.

### “Cấp cluster-wide read chỉ là quyền đọc”

Quyền đọc toàn cluster vẫn làm lộ metadata, endpoint và cấu hình; đồng thời tăng blast radius khi credential bị lộ.

### “DNS không cần namespace vì tên Service đủ”

Tên ngắn chỉ phù hợp khi search domain và namespace context đúng. Cross-namespace nên dùng tên đầy đủ hoặc cấu hình rõ.

## 15. Checklist thiết kế multi-namespace

- Ứng dụng có thật sự cần API discovery hay DNS đã đủ?
- Danh sách namespace được cấu hình ở đâu và có thay đổi động không?
- Service ID có phân biệt namespace khi tên bị trùng không?
- ServiceAccount của Pod thuộc namespace nào?
- Mỗi namespace resource có RoleBinding đúng subject chưa?
- Role có đúng Service/EndpointSlice và verb get/list/watch chưa?
- Có vô tình cấp quyền ConfigMap/Secret/Pod không?
- ClusterRoleBinding có thực sự cần thiết không?
- Cache, watch, reconnect và list lại mở rộng theo bao nhiêu namespace?
- Một namespace lỗi có làm toàn bộ ứng dụng fail không?
- Timeout và retry có độc lập theo namespace không?
- Endpoint ready và port có được kiểm tra không?
- Local test có dùng credential rộng hơn production không?
- Metrics có cho biết namespace nào lỗi mà không lộ Secret không?
- Khi tenant bị xóa hoặc mất quyền, cache cũ được loại bỏ thế nào?

Khám phá nhiều namespace là quyết định về phạm vi dữ liệu, quyền RBAC và chi phí vận hành cùng lúc. Khi namespace được đưa vào identity, binding và cache một cách rõ ràng, Spring Cloud Kubernetes có thể hỗ trợ discovery và cấu hình nhiều tenant mà vẫn giữ được ranh giới truy cập, khả năng điều tra và hành vi khi một namespace gặp sự cố.
