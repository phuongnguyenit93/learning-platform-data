# ServiceAccount và quyền đọc tài nguyên phục vụ khám phá

Khi Spring Cloud Kubernetes dùng Kubernetes API để khám phá service, ứng dụng chạy trong Pod cần một danh tính để xác thực với API server. Danh tính đó thường là **ServiceAccount** được gán cho Pod. Kubernetes RBAC quyết định ServiceAccount được đọc những tài nguyên nào, trong namespace nào và bằng những thao tác nào.

ServiceAccount chỉ cung cấp danh tính; nó không tự cấp quyền đọc Service, Endpoint hay Pod. Muốn discovery hoạt động, cần cấp đúng quyền `get`, `list` và `watch` cho các resource mà implementation đang sử dụng. Cấp thiếu quyền thường dẫn đến lỗi `Forbidden`; cấp quá rộng có thể khiến một microservice đọc được topology của những namespace không liên quan.

## 1. ServiceAccount là danh tính của workload

Kubernetes ServiceAccount đại diện cho một ứng dụng hoặc workload khi workload gọi Kubernetes API. Mỗi namespace có ServiceAccount `default`, nhưng production nên tạo ServiceAccount riêng cho từng ứng dụng hoặc nhóm ứng dụng có cùng quyền.

Khi Pod khai báo `spec.serviceAccountName`, kubelet cung cấp thông tin xác thực cho container theo cấu hình của ServiceAccount. Với cơ chế token projected hiện đại, token có thời hạn và được kubelet tự làm mới. Client trong Pod sử dụng token cùng CA certificate của cluster để xác thực TLS đến API server.

Danh tính được Kubernetes nhận diện theo dạng:

```text
system:serviceaccount:<namespace>:<service-account-name>
```

Ví dụ, Pod trong namespace `commerce` dùng ServiceAccount `checkout-discovery` sẽ có danh tính:

```text
system:serviceaccount:commerce:checkout-discovery
```

Khi Spring Cloud Kubernetes discovery client gọi API để liệt kê Service hoặc Endpoint, API server xác thực token, sau đó kiểm tra RBAC của danh tính này. Nếu không có binding phù hợp, API server trả `403 Forbidden`.

### Tạo ServiceAccount riêng

```yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: checkout-discovery
  namespace: commerce
automountServiceAccountToken: true
```

`automountServiceAccountToken: true` cho phép Kubernetes tự mount token vào Pod sử dụng ServiceAccount này. Đây là thiết lập cần thiết khi ứng dụng dùng in-cluster Kubernetes client theo cách mặc định. Nếu ứng dụng không gọi Kubernetes API, có thể tắt auto-mount để giảm credential không cần thiết.

Không nên dùng ServiceAccount `default` cho mọi workload. Khi nhiều ứng dụng dùng chung một danh tính, rất khó cấp quyền tối thiểu và khó xác định ứng dụng nào đã thực hiện một truy vấn API.

## 2. Gắn ServiceAccount vào Pod

Pod hoặc Deployment phải khai báo đúng ServiceAccount. Ví dụ Deployment cho `checkout-service`:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: checkout-service
  namespace: commerce
spec:
  replicas: 2
  selector:
    matchLabels:
      app: checkout-service
  template:
    metadata:
      labels:
        app: checkout-service
    spec:
      serviceAccountName: checkout-discovery
      containers:
        - name: application
          image: example/checkout-service:1.0.0
          ports:
            - name: http
              containerPort: 8080
```

`serviceAccountName` phải trùng với tên ServiceAccount trong cùng namespace của Pod. Nếu bỏ trường này, Pod thường dùng ServiceAccount `default` của namespace; quyền RBAC gán cho `checkout-discovery` khi đó không có tác dụng.

Nếu Pod đặt `automountServiceAccountToken: false`, thiết lập ở Pod có thể ngăn token tự động được mount ngay cả khi ServiceAccount cho phép. Chỉ tắt auto-mount khi ứng dụng không cần gọi Kubernetes API hoặc đã cấu hình một cơ chế credential khác có chủ đích.

## 3. Discovery client đọc những tài nguyên nào?

Kubernetes biểu diễn dịch vụ và các địa chỉ backend bằng nhiều resource. Spring Cloud Kubernetes có thể dùng Service, Endpoints, EndpointSlice hoặc Pod tùy discovery mode, phiên bản thư viện và cấu hình. Cần cấp quyền theo đúng loại dữ liệu mà ứng dụng thực sự truy vấn.

| Resource | API group | Dữ liệu dùng cho discovery | Khi nào cần quyền |
| --- | --- | --- | --- |
| `services` | Core API (`""`) | Tên Service, selector, port, namespace và metadata | Khi client liệt kê hoặc đọc Kubernetes Service |
| `endpoints` | Core API (`""`) | Địa chỉ và port backend được Service chọn | Khi implementation đọc Endpoints truyền thống |
| `endpointslices` | `discovery.k8s.io` | Danh sách endpoint được chia thành các slice | Khi implementation đọc EndpointSlice |
| `pods` | Core API (`""`) | Pod IP, label, readiness, metadata hoặc discovery theo Pod | Khi chế độ discovery hoặc bộ lọc cần đọc Pod trực tiếp |
| `namespaces` | Core API (`""`) | Danh sách namespace khi khám phá trên nhiều namespace | Khi client thực sự liệt kê namespace |

Không phải ứng dụng nào cũng cần tất cả resource trên. Ví dụ, nếu client chỉ tra cứu Service và Endpoints trong namespace hiện tại, không cần cấp quyền đọc Pod hoặc Namespace. Nếu phiên bản discovery client đọc EndpointSlice, quyền `endpoints` đơn thuần có thể chưa đủ.

### Service và Endpoint khác nhau thế nào?

- **Service** định nghĩa endpoint ổn định, selector, port và chính sách truy cập.
- **Endpoints** hoặc **EndpointSlice** phản ánh các backend thực tế mà Service đang trỏ đến.
- **Pod** chứa trạng thái và metadata của từng workload. Một số discovery mode cần đọc Pod để lấy thông tin chi tiết hoặc lọc theo trạng thái.

Service có thể tồn tại nhưng chưa có Endpoint nếu selector không khớp Pod, Pod chưa Ready hoặc workload chưa tạo endpoint. Trường hợp này không nhất thiết là lỗi RBAC.

## 4. Các verb RBAC cần thiết

RBAC phân biệt quyền theo resource và verb. Với service discovery, các quyền đọc thường dùng là:

| Verb | Ý nghĩa | Tình huống |
| --- | --- | --- |
| `get` | Đọc một resource cụ thể | Lấy chi tiết Service, Endpoint hoặc Pod |
| `list` | Liệt kê resource trong phạm vi được cấp | Tìm các Service hoặc backend theo namespace |
| `watch` | Theo dõi thay đổi resource | Cập nhật danh sách khi Service, Endpoint hoặc Pod thay đổi |

Nhiều client thực hiện `list` để lấy snapshot ban đầu rồi `watch` để nhận cập nhật. Nếu chỉ cấp `get`, client có thể đọc một object đã biết tên nhưng không thể khám phá danh sách động. Nếu thiếu `watch`, ứng dụng có thể khởi động được nhưng không nhận thay đổi kịp thời hoặc phải dựa vào polling tùy implementation.

Với discovery chỉ đọc, thông thường không cần các verb `create`, `update`, `patch` hoặc `delete` trên Service, Endpoints, EndpointSlices hay Pods. Các quyền ghi thuộc về controller, deployment pipeline hoặc thành phần quản trị tạo resource.

## 5. Cấp quyền trong một namespace bằng Role và RoleBinding

Nếu `checkout-service` chỉ khám phá service trong namespace `commerce`, hãy dùng Role và RoleBinding trong chính namespace đó.

Ví dụ Role cho discovery qua Service và Endpoints:

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: checkout-service-discovery-reader
  namespace: commerce
rules:
  - apiGroups: [""]
    resources:
      - services
      - endpoints
    verbs:
      - get
      - list
      - watch
```

Nếu implementation cần EndpointSlice, bổ sung rule tương ứng:

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: checkout-endpointslice-reader
  namespace: commerce
rules:
  - apiGroups: ["discovery.k8s.io"]
    resources:
      - endpointslices
    verbs:
      - get
      - list
      - watch
```

Nếu discovery mode cần đọc Pod, thêm rule `pods` vào API group core:

```yaml
rules:
  - apiGroups: [""]
    resources:
      - pods
    verbs:
      - get
      - list
      - watch
```

Chỉ thêm rule thực sự cần. Các đoạn Role riêng ở trên là ví dụ minh họa; trong manifest triển khai có thể gộp các rule vào một Role để quản lý tập trung.

### Gắn Role với ServiceAccount

Role không tự cấp quyền cho Pod. Cần RoleBinding tham chiếu Role và ServiceAccount:

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: checkout-service-discovery
  namespace: commerce
subjects:
  - kind: ServiceAccount
    name: checkout-discovery
    namespace: commerce
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: Role
  name: checkout-service-discovery-reader
```

RoleBinding giới hạn quyền trong namespace `commerce`. ServiceAccount chỉ có quyền đọc các resource được nêu trong Role ở namespace đó.

## 6. Khám phá service ở namespace khác

Một ứng dụng có thể chạy trong namespace `commerce` nhưng cần tìm service trong namespace `catalog`. Không nhất thiết phải cấp quyền cluster-wide. Có thể tạo Role trong namespace đích và RoleBinding tại namespace đó, tham chiếu ServiceAccount từ namespace nguồn.

Ví dụ RoleBinding được đặt trong namespace `catalog`:

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: checkout-read-catalog-services
  namespace: catalog
subjects:
  - kind: ServiceAccount
    name: checkout-discovery
    namespace: commerce
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: Role
  name: catalog-discovery-reader
```

Role `catalog-discovery-reader` cũng phải tồn tại trong namespace `catalog`. Binding này cấp quyền cho danh tính `commerce/checkout-discovery` đọc tài nguyên trong `catalog`, nhưng không cấp quyền tương tự ở các namespace khác.

Nếu cần truy vấn nhiều namespace cụ thể, có thể tạo RoleBinding tương ứng ở từng namespace đích. Cách này giúp quyền truy cập rõ ràng và dễ kiểm toán hơn một ClusterRoleBinding áp dụng toàn cluster.

## 7. Khi nào cần ClusterRole và ClusterRoleBinding?

Nếu discovery client được cấu hình để liệt kê Service/Endpoint trên toàn cluster, hoặc cần liệt kê Namespace, Role đơn namespace không đủ. Khi đó có thể tạo ClusterRole và ClusterRoleBinding.

Ví dụ ClusterRole chỉ cấp quyền đọc Service và Endpoints trên mọi namespace:

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: checkout-global-discovery-reader
rules:
  - apiGroups: [""]
    resources:
      - services
      - endpoints
    verbs:
      - get
      - list
      - watch
```

Gắn quyền đó với ServiceAccount:

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: checkout-global-discovery
subjects:
  - kind: ServiceAccount
    name: checkout-discovery
    namespace: commerce
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: checkout-global-discovery-reader
```

ClusterRoleBinding cấp quyền trên toàn cluster cho ServiceAccount này. Chỉ dùng khi ứng dụng thực sự cần phạm vi đó. Nếu chỉ cần một vài namespace, ưu tiên RoleBinding ở từng namespace đích.

Nếu cần liệt kê namespace để tìm service trên nhiều namespace, bổ sung quyền đọc `namespaces` trong core API. Không cấp quyền này chỉ vì thấy ví dụ trên Internet có nó; hãy xác nhận discovery client thực sự gọi API namespace.

## 8. EndpointSlice và khả năng tương thích phiên bản

Kubernetes hiện đại hỗ trợ EndpointSlice qua API group `discovery.k8s.io`. EndpointSlice chia endpoint của một Service thành nhiều object, giúp xử lý service có số lượng backend lớn hiệu quả hơn.

Một discovery client có thể đọc Endpoints, EndpointSlices hoặc cả hai tùy phiên bản và cấu hình. Vì vậy:

- Kiểm tra tài liệu của đúng phiên bản Spring Cloud Kubernetes đang dùng.
- Kiểm tra log API client để xác định resource và API group bị gọi.
- Cấp `get`, `list`, `watch` cho `endpointslices` nếu implementation thực sự sử dụng chúng.
- Không cấp `*` trên mọi resource hoặc mọi API group chỉ để xử lý lỗi `Forbidden`.

Ví dụ rule EndpointSlice:

```yaml
- apiGroups: ["discovery.k8s.io"]
  resources:
    - endpointslices
  verbs:
    - get
    - list
    - watch
```

Lưu ý rằng quyền trên `endpoints` thuộc core API group `""`, còn `endpointslices` thuộc `discovery.k8s.io`. Đặt nhầm API group khiến RBAC không khớp dù tên resource có vẻ đúng.

## 9. Cấu hình Spring Cloud Kubernetes Discovery

Khi ứng dụng chạy trong Pod, Kubernetes client thường có thể tự phát hiện in-cluster configuration, đọc API server address, token và CA certificate được mount. Ứng dụng cần có starter discovery phù hợp và ServiceAccount được gắn vào Pod.

Ví dụ dependency Maven:

```xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-kubernetes-client</artifactId>
</dependency>
```

Spring Cloud Kubernetes có các biến thể dựa trên Kubernetes Client hoặc Fabric8; chọn starter phù hợp với implementation mà dự án sử dụng và quản lý version qua Spring Cloud BOM. Tên starter cụ thể có thể khác theo release train.

Ví dụ cấu hình discovery trong một namespace:

```yaml
spring:
  application:
    name: checkout-service
  cloud:
    kubernetes:
      discovery:
        enabled: true
        all-namespaces: false
```

Với cấu hình giới hạn namespace, client thường khám phá service trong namespace của ứng dụng hoặc namespace được cấu hình. Nếu bật khám phá trên nhiều namespace, cần xác minh property của phiên bản đang dùng và cấp RBAC tương ứng ở từng namespace hoặc phạm vi cluster.

Các thuộc tính namespace và discovery mode có thể thay đổi theo phiên bản Spring Cloud Kubernetes. Không sao chép cấu hình từ release train khác mà không kiểm tra reference của dependency đang dùng. RBAC phải phản ánh đúng resource mà implementation cụ thể truy vấn.

## 10. Service discovery bằng Kubernetes DNS có cần RBAC không?

Không phải mọi cách gọi service trong Kubernetes đều cần Spring Cloud Kubernetes DiscoveryClient.

Nếu consumer gọi Kubernetes Service bằng DNS nội bộ, ví dụ:

```text
http://inventory-service.commerce.svc.cluster.local:8080
```

Kubernetes DNS phân giải tên Service và dataplane của Kubernetes chuyển traffic đến backend. Ứng dụng chỉ cần mạng và DNS hoạt động; nó không cần đọc Service hoặc Endpoint qua Kubernetes API cho mỗi lần gọi.

Nếu ứng dụng dùng `DiscoveryClient` để liệt kê service, đọc metadata hoặc tự chọn instance, nó cần truy cập Kubernetes API và ServiceAccount/RBAC phù hợp. Hai mô hình có mục tiêu khác nhau:

| Cách gọi | Thành phần phân giải | Cần quyền đọc API? |
| --- | --- | --- |
| Kubernetes Service DNS | CoreDNS và Kubernetes Service dataplane | Không, nếu chỉ dùng DNS/network thông thường |
| Spring Cloud Kubernetes DiscoveryClient | Kubernetes API và discovery implementation | Có, theo resource/verb được truy vấn |
| Spring Cloud LoadBalancer với Kubernetes discovery | DiscoveryClient cung cấp instance, LoadBalancer chọn instance | Có, nếu nguồn discovery truy vấn API |

Chọn cách đơn giản nhất đáp ứng yêu cầu. Nếu chỉ cần gọi một Service ổn định trong cùng cluster, DNS thường đã đủ. Nếu cần danh sách instance, metadata hoặc logic chọn backend ở phía client, DiscoveryClient có thể phù hợp hơn.

## 11. Kiểm tra quyền bằng kubectl

Sau khi áp dụng ServiceAccount, Role và RoleBinding, kiểm tra quyền với danh tính thực tế. Ví dụ:

```bash
# ServiceAccount có thể liệt kê Service trong namespace commerce?
kubectl auth can-i list services \
  --as=system:serviceaccount:commerce:checkout-discovery \
  -n commerce

# Có thể watch Endpoints?
kubectl auth can-i watch endpoints \
  --as=system:serviceaccount:commerce:checkout-discovery \
  -n commerce

# Có thể đọc EndpointSlice?
kubectl auth can-i list endpointslices.discovery.k8s.io \
  --as=system:serviceaccount:commerce:checkout-discovery \
  -n commerce

# Liệt kê quyền hiệu lực trong namespace
kubectl auth can-i --list \
  --as=system:serviceaccount:commerce:checkout-discovery \
  -n commerce
```

Lệnh `kubectl auth can-i --as=...` cần người chạy có quyền impersonate danh tính được chỉ định. Nếu không có quyền impersonation, hãy chạy kiểm tra bằng tài khoản quản trị phù hợp hoặc kiểm tra từ chính Pod.

Kiểm tra Pod đang dùng đúng ServiceAccount:

```bash
kubectl get pod -n commerce -l app=checkout-service \
  -o jsonpath='{.items[*].spec.serviceAccountName}'
```

Kiểm tra Service và Endpoints:

```bash
kubectl get service inventory-service -n commerce
kubectl get endpoints inventory-service -n commerce
kubectl get endpointslices -n commerce \
  -l kubernetes.io/service-name=inventory-service
```

Nếu API trả `Forbidden`, đối chiếu danh tính, namespace, resource, API group và verb. Nếu quyền đã đúng nhưng danh sách Endpoint rỗng, kiểm tra selector của Service, label Pod và readiness của backend.

## 12. Lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| `system:serviceaccount:... cannot list services` | Thiếu `list services` hoặc Pod dùng sai ServiceAccount | Kiểm tra `serviceAccountName`, Role và RoleBinding |
| Có thể đọc Service nhưng không thấy backend | Thiếu quyền đọc Endpoints/EndpointSlices hoặc backend chưa Ready | Cấp đúng quyền endpoint; kiểm tra selector và readiness |
| Khởi động được nhưng không nhận thay đổi | Thiếu `watch` hoặc implementation đang polling theo cấu hình | Kiểm tra RBAC watch và log discovery client |
| Local chạy được nhưng trong cluster bị 403 | Local dùng kubeconfig cá nhân có quyền rộng | Kiểm tra ServiceAccount token và RBAC trong Pod |
| Đã tạo Role nhưng vẫn bị từ chối | Chưa tạo RoleBinding hoặc binding sai namespace/name | Kiểm tra subject và roleRef của RoleBinding |
| RoleBinding ở namespace app không đọc được namespace khác | RoleBinding chỉ cấp quyền trong namespace nơi nó tồn tại | Tạo Role/RoleBinding tại namespace đích hoặc dùng ClusterRole theo nhu cầu |
| Bật all-namespaces nhưng chỉ thấy một namespace | RBAC vẫn bị giới hạn hoặc thiếu quyền liệt kê namespace/resource ở phạm vi cần thiết | Kiểm tra cấu hình scope và binding cho từng namespace |
| `endpointslices` bị Forbidden dù `endpoints` được phép | EndpointSlice thuộc API group khác | Thêm rule `discovery.k8s.io` cho `endpointslices` |
| Không có token trong Pod | Auto-mount bị tắt hoặc cấu hình projected token sai | Kiểm tra ServiceAccount và Pod `automountServiceAccountToken` |
| Service có nhưng `DiscoveryClient` trả danh sách rỗng | Service không có backend, sai namespace hoặc filter loại instance | Kiểm tra Endpoint, readiness, namespace và discovery mode |

## 13. Bảo mật và nguyên tắc least privilege

Quyền đọc tài nguyên Kubernetes cũng có thể tiết lộ topology nội bộ: tên service, địa chỉ Pod, port, label và metadata. Hãy giới hạn quyền theo nhu cầu thực tế.

- Tạo ServiceAccount riêng cho từng ứng dụng cần Kubernetes API.
- Dùng Role/RoleBinding khi chỉ khám phá trong một namespace.
- Dùng RoleBinding ở từng namespace đích nếu cần truy cập một số namespace cụ thể.
- Chỉ dùng ClusterRoleBinding khi ứng dụng thực sự cần đọc trên toàn cluster.
- Chỉ cấp `get`, `list`, `watch` cho resource discovery cần dùng.
- Không cấp quyền tạo, sửa hoặc xóa Service, Endpoint, EndpointSlice hay Pod cho consumer discovery.
- Không mount token vào workload không gọi Kubernetes API.
- Không copy token ServiceAccount ra file cấu hình hoặc đưa vào image.
- Bảo vệ API server bằng TLS và giữ network policy phù hợp.
- Theo dõi audit log để biết ServiceAccount nào đã đọc tài nguyên và từ đâu.

Không dùng `resources: ["*"]`, `verbs: ["*"]` hoặc ClusterRoleBinding rộng chỉ để làm cho discovery “chạy được”. Nếu implementation yêu cầu thêm resource, xác định chính xác API call và bổ sung rule tối thiểu.

### Lưu ý về `resourceNames`

RBAC hỗ trợ `resourceNames` cho một số thao tác đọc object cụ thể, nhưng giới hạn này thường không phù hợp với discovery động. Các thao tác `list` và `watch` chỉ có thể được giới hạn theo tên khi request dùng field selector tương ứng; không phải mọi discovery client đều gửi selector đó. Vì vậy, không nên thêm `resourceNames` rồi giả định client vẫn có thể liệt kê mọi service mới.

## 14. Checklist triển khai

- [ ] Tạo ServiceAccount riêng trong namespace của workload.
- [ ] Gắn đúng `serviceAccountName` vào Pod template.
- [ ] Xác nhận token được mount nếu ứng dụng cần gọi Kubernetes API.
- [ ] Xác định discovery client đọc Service, Endpoints, EndpointSlice, Pod hay Namespace.
- [ ] Chỉ cấp `get`, `list`, `watch` cho resource thực sự cần.
- [ ] Dùng Role/RoleBinding cho phạm vi một namespace.
- [ ] Dùng RoleBinding ở namespace đích nếu chỉ cần một vài namespace khác.
- [ ] Chỉ dùng ClusterRoleBinding khi cần phạm vi toàn cluster.
- [ ] Kiểm tra quyền bằng `kubectl auth can-i` với đúng ServiceAccount.
- [ ] Xác minh Endpoint có backend và Pod đã Ready.
- [ ] Kiểm tra `watch` để cập nhật khi service hoặc endpoint thay đổi.
- [ ] Bảo vệ token và giới hạn quyền theo nguyên tắc least privilege.

ServiceAccount xác định ứng dụng nào đang gọi Kubernetes API; RBAC quyết định ứng dụng đó được đọc resource nào và trong phạm vi nào. Với Spring Cloud Kubernetes Discovery, hãy bắt đầu từ resource thực tế mà discovery implementation truy vấn, sau đó cấp quyền đọc tối thiểu bằng Role/RoleBinding. Chỉ mở rộng sang nhiều namespace hoặc toàn cluster khi có yêu cầu rõ ràng. Cách làm này giúp discovery cập nhật được service instance mà vẫn giữ giới hạn truy cập phù hợp cho từng microservice.
