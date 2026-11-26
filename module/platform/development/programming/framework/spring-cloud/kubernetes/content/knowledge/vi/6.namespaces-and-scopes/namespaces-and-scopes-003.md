# Khám phá dịch vụ trong một namespace

Trong Kubernetes, một Service có tên duy nhất trong namespace của nó, không phải duy nhất trong toàn cluster. Vì vậy, catalog-api ở namespace shop và catalog-api ở namespace billing là hai dịch vụ khác nhau dù cùng tên. Khi ứng dụng Spring cần khám phá dịch vụ, namespace là một phần của danh tính đích và phải được thiết kế cùng với DNS, DiscoveryClient, RBAC và policy mạng.

Nếu ứng dụng chỉ gọi một Service đã biết tên trong cùng namespace, DNS của Kubernetes thường đã đủ. Nếu ứng dụng cần lấy danh sách Service hoặc instance bằng abstraction Spring Cloud, DiscoveryClient có thể đọc thông tin từ Kubernetes API hoặc từ một Discovery Server. Khi đó, phạm vi namespace quyết định dữ liệu được nhìn thấy, quyền nào cần cấp và khả năng tránh nhầm dịch vụ trùng tên.

Bài học thuộc chương **Namespace và phạm vi** của module **SPRING_CLOUD_KUBERNETES**. Mục tiêu là thiết kế discovery trong một namespace theo nguyên tắc tối thiểu: hiểu tên Service, selector và EndpointSlice; chọn DNS hay DiscoveryClient; giới hạn RBAC; và xử lý readiness, cache cùng lỗi namespace.

## 1. Namespace là một phần của tên dịch vụ

Namespace tạo phạm vi tên và phạm vi của nhiều tài nguyên Kubernetes. Một Service có tên catalog-api trong namespace shop không trùng với Service cùng tên trong namespace billing.

~~~text
shop/catalog-api
billing/catalog-api
~~~

Hai Service có thể có:

- Selector khác nhau.
- Tập Pod khác nhau.
- Port khác nhau.
- ServiceAccount và policy mạng khác nhau.
- Owner và vòng đời release khác nhau.

Từ Pod trong namespace shop, tên catalog-api thường được phân giải tới Service trong shop. Từ Pod ở namespace khác, tên ngắn catalog-api thường chỉ tìm trong search domain của namespace hiện tại. Muốn gọi rõ Service ở shop, dùng tên có namespace:

~~~text
http://catalog-api.shop:80/products/42
~~~

Tên đầy đủ thường có dạng:

~~~text
catalog-api.shop.svc.cluster.local
~~~

Hậu tố cluster domain có thể thay đổi theo môi trường. Ứng dụng nên dùng quy ước DNS được platform công bố, không hard-code hậu tố nếu cluster có cấu hình riêng.

DNS name phân biệt được namespace nhưng không cho ứng dụng Java danh sách từng instance. DNS và DiscoveryClient giải quyết hai nhu cầu khác nhau:

| Nhu cầu | Cách phù hợp |
| --- | --- |
| Gọi một Service logic đã biết tên | DNS + HTTP client |
| Lấy danh sách Service/instance | DiscoveryClient hoặc Discovery Server |
| Chọn endpoint ở phía client | Discovery source + Spring Cloud LoadBalancer |
| Giới hạn resource được đọc | Namespace và RBAC |

## 2. Service chọn Pod trong chính namespace của nó

Service có selector thường chọn Pod cùng namespace theo nhãn. Ví dụ Service catalog-api trong shop:

~~~yaml
apiVersion: v1
kind: Service
metadata:
  name: catalog-api
  namespace: shop
spec:
  selector:
    app: catalog-api
  ports:
    - name: http
      port: 80
      targetPort: http
~~~

Pod được chọn cũng phải nằm trong namespace shop và có nhãn app: catalog-api:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: catalog-api
  namespace: shop
spec:
  replicas: 2
  selector:
    matchLabels:
      app: catalog-api
  template:
    metadata:
      labels:
        app: catalog-api
    spec:
      containers:
        - name: catalog-api
          image: registry.example.com/shop/catalog-api:1.0.0
          ports:
            - name: http
              containerPort: 8080
~~~

Service selector không tìm Pod ở namespace khác. Nếu muốn ứng dụng trong shop gọi workload ở billing, client phải gọi Service billing/catalog-api qua DNS có namespace hoặc một abstraction discovery có phạm vi cross-namespace. Không thể đổi namespace của Service chỉ bằng cách thêm namespace vào selector.

Luồng chọn đích:

~~~text
order-api trong shop
       |
       v
catalog-api.shop
       |
       v
Service catalog-api trong shop
       |
       v
EndpointSlice của Service
       |
       v
Pod catalog-api trong shop đủ điều kiện
~~~

Nếu selector không khớp, Service có thể tồn tại nhưng không có endpoint. DNS vẫn có thể phân giải tên Service; điều đó chưa chứng minh có Pod đang phục vụ.

## 3. Gọi trong cùng namespace bằng DNS

Nếu order-api và catalog-api cùng ở shop, client có thể gọi:

~~~text
http://catalog-api/products/42
~~~

Port mặc định trong URL phải phù hợp với Service. Nếu Service công bố port 80, client có thể gọi hostname không kèm port khi dùng HTTP; nếu công bố port khác, phải dùng port tương ứng.

Gọi qua DNS có một số đặc điểm:

- Client không cần biết IP của từng Pod.
- Kubernetes Service xử lý việc chọn endpoint theo cơ chế của cluster.
- Ứng dụng thường không cần đọc Service hoặc EndpointSlice qua Kubernetes API chỉ để gọi HTTP.
- ServiceAccount token không cần được mount chỉ cho đường gọi DNS.
- Readiness ảnh hưởng đến endpoint được xem là có thể nhận traffic.

Ví dụ một Pod chỉ gọi Service qua DNS có thể tắt automount token:

~~~yaml
spec:
  automountServiceAccountToken: false
  containers:
    - name: order-api
      image: registry.example.com/shop/order-api:1.0.0
~~~

Cấu hình này không ngăn HTTP traffic tới Service. Nó chỉ tránh đưa token Kubernetes API vào Pod khi ứng dụng không cần tự gọi API. Nếu sau đó bật DiscoveryClient đọc Service trực tiếp, phải thiết kế lại authentication và RBAC.

DNS không thay thế timeout, retry, circuit breaker hoặc xử lý mã HTTP. catalog-api vẫn có thể chậm, trả 500 hoặc đóng connection. Discovery chỉ giúp tìm đích; nó không sửa lỗi nghiệp vụ ở đích.

## 4. DiscoveryClient trong phạm vi một namespace

Khi ứng dụng cần abstraction Spring Cloud để truy vấn dịch vụ và instance, DiscoveryClient có thể là lựa chọn phù hợp. Trong mô hình truy cập Kubernetes API trực tiếp, client thường cần đọc resource discovery trong namespace được cấu hình.

Một lookup có thể được mô tả:

~~~text
DiscoveryClient
      |
      | serviceId = catalog-api
      | namespace = shop
      v
Kubernetes API
      |
      +--> Service
      +--> EndpointSlice hoặc resource liên quan
      v
Danh sách instance/địa chỉ theo implementation
~~~

Tên serviceId không tự chứa namespace theo mọi implementation. Cần kiểm tra cách integration chọn namespace, service label, port và loại endpoint. Không nên đoán rằng serviceId catalog-api luôn chỉ có một kết quả trên toàn cluster.

Nếu DiscoveryClient được giới hạn ở shop:

- Cache chỉ cần giữ resource trong phạm vi cần thiết.
- RBAC có thể dùng Role thay vì ClusterRole.
- Dữ liệu trùng tên ở billing không làm nhiễu lookup.
- Sự cố discovery có phạm vi ảnh hưởng nhỏ hơn.
- Audit request dễ đọc hơn.

Nếu implementation list toàn cluster dù ứng dụng chỉ cần một namespace, cần xem property và client behavior. Tên cấu hình namespace không có giá trị nếu integration thực tế vẫn dùng cluster scope do một tính năng khác yêu cầu.

## 5. RBAC cho discovery một namespace

Ứng dụng discovery trực tiếp cần quyền khớp với resource và verb mà client gọi. Ví dụ một Role chỉ đọc Service trong shop:

~~~yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: order-discovery-reader
  namespace: shop
rules:
  - apiGroups: [""]
    resources: ["services"]
    verbs: ["get", "list", "watch"]
~~~

Nếu client dùng EndpointSlice:

~~~yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: order-endpoint-reader
  namespace: shop
rules:
  - apiGroups: ["discovery.k8s.io"]
    resources: ["endpointslices"]
    verbs: ["get", "list", "watch"]
~~~

Gắn Role với ServiceAccount của order-api:

~~~yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: order-api
  namespace: shop
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: order-discovery-reader
  namespace: shop
subjects:
  - kind: ServiceAccount
    name: order-api
    namespace: shop
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: Role
  name: order-discovery-reader
~~~

Đây là ví dụ minh họa, không phải bộ quyền đúng cho mọi implementation. Một client có thể chỉ đọc Service, có thể đọc EndpointSlice, hoặc có thể cần resource khác theo release train. Hãy xác nhận request thực tế.

Không nên cấp ClusterRole chỉ vì ứng dụng chạy trong cluster. Nếu discovery chỉ cần shop, Role namespaced giúp giới hạn tác động khi credential bị lộ hoặc code bị lỗi.

## 6. get, list và watch không giống nhau

Các verb có ý nghĩa khác:

| Verb | Dùng cho | Rủi ro/phạm vi |
| --- | --- | --- |
| get | Đọc một resource đã biết tên | Hẹp nếu tên cố định |
| list | Lấy danh sách resource trong scope | Có thể thấy nhiều tên và metadata |
| watch | Nhận thay đổi liên tục | Giữ stream, cần reconnect và RBAC |
| create/update/delete | Thay đổi cluster | Không cần cho discovery read-only |

Nếu DiscoveryClient chỉ đọc Service catalog-api bằng get, không nhất thiết cần list/watch. Nếu integration xây cache bằng list/watch, Role phải phản ánh điều đó.

Một Role có resourceNames phù hợp với get một Service đã biết tên nhưng thường không đáp ứng list/watch. Không nên thêm resourceNames rồi suy ra mọi thao tác discovery vẫn hoạt động.

Khi bật watch trong một namespace, hãy xem số replica và số workload. Mỗi Pod giữ một watch có thể tạo tải lên API server. Một Discovery Server hoặc cache dùng chung có thể giảm số watch trực tiếp, nhưng làm tăng phụ thuộc vận hành vào server đó.

## 7. Headless Service và discovery từng Pod

Service thông thường cung cấp một địa chỉ logic để client gọi. Headless Service với clusterIP: None có thể để DNS trả về các địa chỉ endpoint, phù hợp với một số hệ thống cần biết từng thành viên:

~~~yaml
apiVersion: v1
kind: Service
metadata:
  name: catalog-nodes
  namespace: shop
spec:
  clusterIP: None
  selector:
    app: catalog-node
  ports:
    - name: http
      port: 8080
      targetPort: http
~~~

Headless Service không tự cung cấp chính sách chọn instance phía client. Ứng dụng nhận danh sách địa chỉ vẫn phải xử lý:

- Endpoint readiness và terminating.
- Địa chỉ stale khi Pod thay đổi.
- Retry và timeout.
- Thứ tự hoặc trọng số lựa chọn.
- Session affinity nếu giao thức cần.
- Tình trạng node hoặc Pod thực tế.

Với API stateless thông thường, Service có ClusterIP thường đơn giản hơn. Chỉ chọn headless khi client hoặc giao thức cần danh sách thành viên hoặc cần tự quản lý việc chọn đích.

Spring Cloud LoadBalancer có thể chọn instance phía client nếu được tích hợp với nguồn discovery tương thích. Không nên nhầm headless DNS với LoadBalancer: DNS trả kết quả theo semantics DNS; LoadBalancer là logic chọn instance trong client.

## 8. Tên trùng giữa các namespace

Giả sử có:

~~~text
shop/catalog-api
billing/catalog-api
~~~

Ứng dụng shop có thể cần gọi catalog-api của shop, còn một batch job ở platform có thể cần gọi catalog-api của billing. Nếu dùng tên ngắn trong ứng dụng platform, kết quả phụ thuộc namespace của Pod. Đây là nguồn lỗi dễ bỏ sót khi copy manifest.

Bảng lựa chọn:

| Caller | Đích | Hostname rõ ràng |
| --- | --- | --- |
| shop/order-api | shop/catalog-api | catalog-api hoặc catalog-api.shop |
| billing/invoice-api | billing/catalog-api | catalog-api hoặc catalog-api.billing |
| platform/job | shop/catalog-api | catalog-api.shop |
| platform/job | billing/catalog-api | catalog-api.billing |

Tên có namespace giúp tránh nhầm nhưng không cấp quyền network hoặc API. NetworkPolicy vẫn phải cho phép traffic, Service vẫn cần endpoint và ứng dụng đích vẫn phải xác thực request nếu có.

Nếu DiscoveryClient trả nhiều instance cùng serviceId vì scope quá rộng, hãy giới hạn namespace hoặc dùng service identity có namespace rõ. Không nên chọn instance đầu tiên trong danh sách mà không kiểm tra namespace và metadata.

## 9. Cross-namespace có phải luôn là lựa chọn tốt?

Cross-namespace có thể cần khi một dịch vụ nền tảng dùng chung được gọi bởi nhiều team. Nhưng nó làm tăng coupling:

- Caller phải biết namespace của đích.
- NetworkPolicy phải cho phép cross-namespace.
- RBAC discovery có thể cần đọc nhiều namespace.
- Tên resource trùng cần được phân biệt.
- Rollout và ownership khó theo dõi hơn.
- Sai namespace có thể chuyển request tới workload khác.

Trước khi cho phép cross-namespace discovery, hãy hỏi:

1. Có thể đặt caller và callee trong cùng namespace logic không?
2. Có thể dùng một Service facade hoặc gateway rõ ràng không?
3. Caller cần DNS ổn định hay danh sách instance?
4. Ai sở hữu API và policy mạng?
5. Có cần đọc Kubernetes API cross-namespace không?
6. Dữ liệu discovery có chứa metadata của namespace khác không?

Nếu chỉ cần gọi Service cross-namespace, DNS có namespace thường ít quyền hơn DiscoveryClient đọc toàn cluster. Nếu cần danh sách instance cross-namespace, hãy thiết kế một platform service hoặc Discovery Server có phạm vi và authorization rõ.

## 10. Namespace scope của Discovery Server

Discovery Server triển khai riêng có thể tập trung việc đọc Kubernetes API cho nhiều ứng dụng. Một mô hình:

~~~text
order-api trong shop
       |
       | HTTP discovery request
       v
Discovery Server
       |
       | Kubernetes API với ServiceAccount riêng
       v
Services/EndpointSlices trong phạm vi cho phép
~~~

Ưu điểm:

- Ứng dụng nghiệp vụ không cần trực tiếp đọc API cho discovery.
- Có thể tập trung cache và watch.
- Có thể chuẩn hóa filter namespace và metadata.
- Có thể tách quyền đọc API khỏi quyền của từng ứng dụng.

Rủi ro:

- Discovery Server trở thành dependency dùng chung.
- Server có thể nhìn thấy nhiều namespace hơn caller cần.
- Cần phân quyền caller ở API của server.
- Lỗi hoặc cache stale có thể ảnh hưởng nhiều ứng dụng.
- Network path và timeout thêm một lớp.

Discovery Server không tự trở thành reverse proxy của request nghiệp vụ. Nó trả thông tin đích; caller vẫn phải gọi Service/endpoint theo đường mạng được phép.

Nếu server phục vụ shop và billing, hãy ghi rõ namespace allowlist và chính sách caller. Không nên cho mọi application query mọi namespace chỉ vì server có ClusterRole rộng.

## 11. Readiness và tập endpoint trong namespace

Selector khớp nhãn chưa đủ để Pod nhận traffic. Readiness quyết định Pod có được xem là sẵn sàng trong tập endpoint hay không.

Ví dụ:

~~~yaml
readinessProbe:
  httpGet:
    path: /actuator/health/readiness
    port: http
  periodSeconds: 5
  failureThreshold: 3
~~~

Khi catalog-api Pod trong shop not ready:

- Service vẫn có thể tồn tại.
- DNS vẫn có thể phân giải catalog-api.shop.
- EndpointSlice có thể đánh dấu hoặc loại endpoint theo trạng thái.
- Client gọi Service có thể không được chuyển tới Pod đó theo semantics thông thường.
- Discovery cache có thể cần thời gian cập nhật.

Nếu ứng dụng đọc endpoint trực tiếp, phải hiểu cách integration xử lý ready, serving và terminating. Không tự coi mọi địa chỉ trong response là đích tốt.

Readiness cũng là một phần của namespace discovery. Khi rollout catalog-api ở shop, EndpointSlice của billing/catalog-api không nên ảnh hưởng caller shop nếu scope được cấu hình đúng. Scope rộng làm cache và chẩn đoán phức tạp hơn.

## 12. Namespace trong Spring configuration

Có thể đặt namespace bằng property, environment hoặc Downward API. Nếu workload luôn chạy trong một namespace, Downward API giúp tránh lặp giá trị trong image:

~~~yaml
env:
  - name: POD_NAMESPACE
    valueFrom:
      fieldRef:
        fieldPath: metadata.namespace
~~~

Ứng dụng hoặc client integration có thể dùng POD_NAMESPACE làm namespace mặc định nếu cơ chế hỗ trợ. Cần kiểm tra property và behavior của phiên bản Spring Cloud Kubernetes thực tế; không nên giả định mọi starter tự đọc biến tùy ý.

Một cách rõ hơn là đặt property trong Deployment:

~~~yaml
env:
  - name: SPRING_CLOUD_KUBERNETES_NAMESPACE
    value: shop
~~~

Tên property/environment ở đây là minh họa; tên thật phải theo release train và integration đang dùng. Điều quan trọng là namespace runtime phải khớp namespace resource và RBAC.

Không nên lấy namespace từ tên hostname bằng cách cắt chuỗi. Nếu DNS search domain thay đổi, logic đó sẽ sai. Dùng Downward API hoặc cấu hình deployment được kiểm soát.

## 13. Namespace và ConfigMap/Secret discovery

Discovery service không đồng nghĩa discovery config. Một ứng dụng có thể:

- Gọi catalog-api.shop bằng DNS.
- Đọc ConfigMap của namespace shop qua env/volume.
- Đọc Secret qua Kubernetes API.
- Theo dõi Service của shop bằng watch.
- Gọi Discovery Server để lấy instance của billing.

Mỗi đường có scope và RBAC riêng. Không nên cấp quyền đọc Secret chỉ vì ứng dụng cần discovery Service. Không nên cho discovery client list ConfigMap nếu nó không dùng config.

Ví dụ phân tách:

| Thành phần | Namespace | Resource cần |
| --- | --- | --- |
| order-api DNS caller | shop | Không cần đọc API cho DNS |
| order-api config reader | shop | ConfigMap cụ thể |
| order-api discovery reader | shop | Service/EndpointSlice nếu dùng trực tiếp |
| Watcher | shop hoặc allowlist | ConfigMap/Secret và resource định vị đích |
| Discovery Server | Nhiều namespace được phê duyệt | Service/EndpointSlice theo scope |

Tách ServiceAccount theo workload giúp lỗi 403 dễ truy nguyên. Nếu watcher bị từ chối, không mở rộng Role của order-api khi order-api không phải thành phần gọi request.

## 14. Cache discovery trong một namespace

Cache namespaced có thể giảm tải API server và giới hạn dữ liệu trong memory:

~~~text
list Service/EndpointSlice trong shop
              |
              v
watch thay đổi trong shop
              |
              v
cache catalog-api và service khác
              |
              v
DiscoveryClient lookup theo serviceId
~~~

Cần kiểm tra:

- Cache có thực sự lọc namespace không.
- Cache refresh khi watch mất kết nối thế nào.
- ResourceVersion quá cũ được xử lý ra sao.
- Endpoint stale được loại khi Pod terminating không.
- Cache có chứa metadata nhạy cảm không.
- Memory tăng thế nào khi số Service/Pod tăng.

Cache namespaced không loại bỏ race condition. Một endpoint có thể bị xóa ngay sau lookup. Caller vẫn cần timeout và retry an toàn.

Nếu serviceId không unique trong scope của cache, hãy dùng key gồm namespace và tên Service:

~~~text
shop/catalog-api
billing/catalog-api
~~~

Cách này ngăn code vô tình ghi đè dữ liệu của hai namespace vào cùng một key.

## 15. NetworkPolicy và namespace discovery

RBAC kiểm soát API access; NetworkPolicy kiểm soát network traffic. Hai lớp cần phối hợp:

~~~text
Discovery API request:
Pod -> egress policy -> API server -> authentication/RBAC

Business request:
Pod -> egress policy -> Service namespace -> target Pod
~~~

Một application có thể đọc Service trong shop qua API nhưng không gọi được catalog-api.shop vì NetworkPolicy chặn traffic. Ngược lại, application có thể gọi catalog-api.shop qua DNS nhưng không có quyền list Service để dùng DiscoveryClient.

Khi thiết kế policy, hãy tách:

- Egress tới Kubernetes API server.
- Egress tới Service nghiệp vụ trong namespace.
- Ingress từ caller tới callee.
- Traffic tới endpoint quản trị hoặc Actuator.
- Cross-namespace traffic nếu thật sự cần.

Không mở egress toàn cluster chỉ để sửa lỗi discovery một namespace. Không dùng RBAC để giải quyết lỗi TCP. Ghi rõ namespace selector và Pod selector trong policy để tránh rule quá rộng.

## 16. Chẩn đoán discovery trong một namespace

Giả sử order-api trong shop không tìm thấy catalog-api. Trình tự:

1. order-api đang ở namespace nào?
2. Client dùng serviceId và namespace nào?
3. DNS catalog-api.shop có phân giải được không?
4. Service catalog-api có tồn tại trong shop không?
5. Selector có khớp Pod catalog-api trong shop không?
6. EndpointSlice có đích ready không?
7. Nếu gọi API trực tiếp, ServiceAccount có get/list/watch đúng resource không?
8. Nếu dùng Discovery Server, server có được phép nhìn shop không?
9. NetworkPolicy có cho phép egress tới API server hoặc business Service không?
10. Cache có stale hoặc watch bị ngắt không?

Bảng lỗi:

| Triệu chứng | Hướng kiểm tra |
| --- | --- |
| DNS catalog-api không phân giải | Caller namespace, DNS policy, Service name |
| DNS phân giải nhưng không có response | Service port, endpoint, NetworkPolicy, Pod |
| Service tồn tại không có endpoint | Selector, nhãn, readiness |
| DiscoveryClient 403 | ServiceAccount, Role, RoleBinding, verb/resource |
| DiscoveryClient trả rỗng | Namespace scope, API resource, cache, endpoint |
| Discovery Server trả dữ liệu namespace khác | Filter, tenant authorization, cache key |
| Gọi API được nhưng gọi Service không được | NetworkPolicy, Service port, target readiness |

Không nên bắt đầu bằng việc cấp ClusterRole hoặc đổi serviceId ngẫu nhiên. Hãy ghi request context gồm namespace, resource, verb và hostname để phân biệt lớp lỗi.

## 17. Profile local và namespace production

Ứng dụng chạy local thường không có namespace Kubernetes. Profile local nên dùng URL local, mock discovery hoặc test container; profile kubernetes dùng namespace và Service DNS của cluster.

Không nên để local tự suy ra namespace từ tên mặc định rồi gọi cluster thật. Không nên để profile kubernetes fallback sang localhost khi resource discovery lỗi trong production.

Bảng mô hình:

| Môi trường | Namespace | Discovery |
| --- | --- | --- |
| Local | Không có hoặc mô phỏng | Cấu hình tĩnh/mock |
| Test | Namespace test nếu có cluster | Resource test và ServiceAccount test |
| Staging | Namespace staging | DNS hoặc DiscoveryClient giới hạn staging |
| Production | Namespace production/team | Scope được phê duyệt và RBAC tối thiểu |

Profile giúp chọn namespace nhưng không thay thế kiểm tra runtime. Log nên ghi profile, namespace và discovery mode ở mức an toàn.

## 18. Thiết kế service identity

Tên Service nên phản ánh identity ổn định của API, không gắn version nếu Service dùng để chuyển traffic giữa các rollout:

~~~text
catalog-api
~~~

Nhãn version có thể dùng để chọn nhóm canary bằng Service riêng hoặc routing policy. Không nên tạo serviceId mơ hồ như api nếu có nhiều namespace và nhiều ứng dụng.

Một key identity đầy đủ có thể gồm:

~~~text
cluster-context / namespace / service-name / port-name
~~~

Application code không nhất thiết phải dùng toàn bộ key này trong URL, nhưng discovery cache và audit nên phân biệt namespace. Khi cùng tên Service xuất hiện ở nhiều namespace, log chỉ serviceId catalog-api là chưa đủ.

## 19. Checklist discovery một namespace

Trước khi bật discovery, hãy kiểm tra:

- Caller và callee có cùng namespace logic không.
- Service name, namespace và port đã rõ.
- DNS có đủ cho nhu cầu hay cần DiscoveryClient.
- Service selector khớp Pod template trong đúng namespace.
- Readiness phản ánh endpoint có thể nhận traffic.
- Nếu dùng API trực tiếp, Role giới hạn trong namespace cần thiết.
- ServiceAccount của Pod đúng với RoleBinding.
- Verb get/list/watch khớp implementation thật.
- EndpointSlice/API resource được cluster serve.
- Cache key bao gồm namespace khi scope có thể mở rộng.
- NetworkPolicy cho API server và Service nghiệp vụ riêng biệt.
- Cross-namespace được dùng có lý do và allowlist.
- Discovery Server có filter và authorization cho caller.
- Profile local không gọi cluster production.
- Log/metric có namespace nhưng không chứa Secret.
- Có kiểm tra selector, endpoint, RBAC và cache sau rollout.

## 20. Tự kiểm tra

1. Vì sao Service name chỉ duy nhất trong namespace?
2. Từ Pod ở namespace khác, gọi catalog-api.shop khác gì gọi catalog-api?
3. Service selector có chọn Pod ở namespace khác không?
4. Khi nào DNS đủ và khi nào cần DiscoveryClient?
5. Vì sao Role namespaced thường phù hợp hơn ClusterRole cho discovery trong một namespace?
6. Khác biệt giữa get, list và watch trong discovery là gì?
7. Vì sao DNS phân giải được nhưng Service vẫn không có backend?
8. Headless Service có tự cung cấp client-side load balancing không?
9. Nếu DiscoveryClient trả 403, cần kiểm tra ServiceAccount nào?
10. NetworkPolicy và RBAC tác động lên hai đường nào?
11. Vì sao cache discovery nên dùng key gồm namespace và Service name?
12. Bằng chứng nào cho thấy một Service trong namespace đã sẵn sàng nhận traffic?

Khám phá dịch vụ trong một namespace bắt đầu từ một identity rõ: namespace, Service name và port. Nếu DNS của Service đã đáp ứng nhu cầu, không cần thêm quyền đọc Kubernetes API. Nếu cần DiscoveryClient, hãy giới hạn resource, verb và namespace; kiểm tra selector, EndpointSlice, readiness, cache cùng NetworkPolicy. Cách thiết kế này giảm nhầm tên giữa các namespace và giữ phạm vi lỗi, dữ liệu cùng quyền truy cập ở mức có thể kiểm soát.

