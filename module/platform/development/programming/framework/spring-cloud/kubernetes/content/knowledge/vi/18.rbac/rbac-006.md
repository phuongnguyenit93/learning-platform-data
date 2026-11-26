# Quyền trên Service, endpoint, Pod và tài nguyên cấu hình

Trong module **SPRING_CLOUD_KUBERNETES**, các tính năng như DiscoveryClient, nạp ConfigMap/Secret qua API và Configuration Watcher cần đọc những tài nguyên Kubernetes khác nhau. Một ứng dụng chỉ gọi Service bằng DNS không có nhu cầu quyền giống ứng dụng tự truy vấn API để chọn từng instance.

Bài học thuộc chương **Phân quyền RBAC**, hướng dẫn chuyển nhu cầu của từng tính năng thành tài nguyên, API group, động từ và phạm vi namespace. Các cấu hình Spring minh họa theo nhánh **Spring Cloud Kubernetes 3.3.x**. Khi dùng phiên bản hoặc implementation khác, cần đối chiếu tài liệu và các yêu cầu API thực tế; không sao chép một Role chứa tất cả tài nguyên cho mọi ứng dụng.

## 1. Bắt đầu từ đường truy cập dữ liệu

Trước khi viết Role, hãy xác định **tiến trình nào gọi Kubernetes API**.

~~~mermaid
flowchart TD
    A["Ứng dụng cần thông tin gì?"] --> B["Gọi Service qua DNS"]
    A --> C["Tự truy vấn Kubernetes API"]
    A --> D["Đọc tệp ConfigMap/Secret đã mount"]
    B --> E["Không cần quyền đọc API chỉ để gọi HTTP qua Service"]
    C --> F["Xác định ServiceAccount, tài nguyên, verb và namespace"]
    D --> G["Kubelet cung cấp volume; ứng dụng đọc tệp"]
    F --> H["Role hoặc ClusterRole phù hợp"]
    H --> I["Binding đến đúng ServiceAccount"]
~~~

Ví dụ, gọi `http://inventory.sck-lab.svc.cluster.local:8080` là giao tiếp ứng dụng qua mạng, với tên miền cụm minh họa là `cluster.local`. Nó không tương đương yêu cầu đọc đối tượng `Service` từ Kubernetes API. Nếu các tính năng khác vẫn gọi API thì chúng vẫn cần quyền riêng.

| Tính năng thực sự sử dụng | Nguồn dữ liệu | Hướng xác định quyền |
| --- | --- | --- |
| Gọi Service bằng DNS | DNS và kết nối mạng đến Service | Không thêm quyền API chỉ cho cuộc gọi này |
| DiscoveryClient truy cập API trực tiếp | Service, địa chỉ backend, thông tin Pod | Quyền đọc các tài nguyên discovery mà client dùng |
| DiscoveryClient lấy dữ liệu từ Discovery Server | HTTP đến server trung gian | Quyền Kubernetes API nằm ở tiến trình server |
| Spring Cloud LoadBalancer chọn instance từ discovery | Danh sách instance do nguồn discovery cung cấp | Xem nguồn instance gọi API ở đâu |
| Đọc ConfigMap qua API | Đối tượng ConfigMap | Quyền trên `configmaps` |
| Đọc Secret qua API | Đối tượng Secret | Quyền trên `secrets` khi tính năng này được bật |
| Đọc cấu hình qua volume | Tệp trong container | Không cần quyền API của ứng dụng chỉ để đọc tệp |
| Configuration Watcher | Sự kiện cấu hình và thông tin đích nhận refresh | Quyền theo dõi cấu hình và quyền discovery của Watcher |

Bảng này giúp tránh suy luận “đang chạy trên Kubernetes thì phải có quyền đọc toàn namespace”. Hãy giữ riêng nhu cầu của ứng dụng nghiệp vụ, Discovery Server và Configuration Watcher.

## 2. Gọi đúng tên tài nguyên và API group

Trong RBAC, `resources` dùng tên tài nguyên ở dạng API, thường là số nhiều và viết thường.

| Đối tượng | `resources` | `apiGroups` | Vai trò trong tích hợp Spring |
| --- | --- | --- | --- |
| Service | `services` | `""` | Tên dịch vụ, cổng, selector và metadata |
| Endpoints | `endpoints` | `""` | Địa chỉ và cổng backend theo API Endpoints |
| EndpointSlice | `endpointslices` | `discovery.k8s.io` | Các nhóm địa chỉ backend theo API EndpointSlice |
| Pod | `pods` | `""` | Metadata, trạng thái và thông tin Pod mà client cần |
| ConfigMap | `configmaps` | `""` | Cấu hình không nhạy cảm qua API |
| Secret | `secrets` | `""` | Dữ liệu nhạy cảm qua API |

`apiGroups: [""]` biểu thị **core API group**, không phải mọi API group. Với EndpointSlice, không viết `apiGroups: ["discovery.k8s.io/v1"]`: trường này chỉ chứa group, không kèm version.

Đối chiếu đường dẫn API:

~~~text
/api/v1/namespaces/sck-lab/services
/api/v1/namespaces/sck-lab/endpoints
/api/v1/namespaces/sck-lab/pods
/api/v1/namespaces/sck-lab/configmaps
/api/v1/namespaces/sck-lab/secrets

/apis/discovery.k8s.io/v1/namespaces/sck-lab/endpointslices
~~~

“Endpoint” còn được dùng để nói về URL ứng dụng như `/actuator/health`. URL đó không phải tài nguyên `endpoints` của Kubernetes. Quyền đọc `endpoints` không cho phép vượt qua xác thực của Actuator.

Theo [tài liệu EndpointSlices](https://kubernetes.io/docs/concepts/services-networking/endpoint-slices/), EndpointSlice lưu thông tin backend và có thể có nhiều đối tượng cho một Service. Vì thế không nên giả định tên EndpointSlice bằng tên Service để giới hạn `resourceNames`.

## 3. Phân biệt get, list và watch

Ba động từ đọc không thay thế cho nhau:

| Động từ | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `get` | Đọc một đối tượng đã biết tên | Đọc ConfigMap `catalog-api` |
| `list` | Đọc tập đối tượng | Liệt kê Service trong namespace |
| `watch` | Theo dõi thay đổi theo thời gian | Nhận thay đổi Pod từ một informer |
| `create` | Tạo đối tượng | Tạo một ConfigMap mới |
| `update`, `patch` | Sửa đối tượng | Đổi dữ liệu ConfigMap |
| `delete` | Xóa đối tượng | Xóa Pod |

Dù nhiều thao tác sử dụng HTTP GET, authorization vẫn phân biệt `get`, `list` và `watch` theo dạng yêu cầu. Xem [Kubernetes Authorization](https://kubernetes.io/docs/reference/access-authn-authz/authorization/#request-verbs-and-authorization).

Ví dụ:

~~~text
GET /api/v1/namespaces/sck-lab/configmaps/catalog-api
    -> get configmaps, tên catalog-api

GET /api/v1/namespaces/sck-lab/configmaps
    -> list configmaps

GET /api/v1/namespaces/sck-lab/configmaps?watch=true
    -> watch configmaps
~~~

Một informer thường cần lấy danh sách ban đầu rồi theo dõi thay đổi. Chỉ cấp `watch` không bảo đảm quá trình khởi tạo hoặc kết nối lại hoạt động. Ngược lại, một client chỉ nạp cấu hình tại startup không mặc nhiên cần `watch`.

Ứng dụng đọc và theo dõi tài nguyên không cần quyền sửa chúng chỉ vì Kubernetes liên tục cập nhật backend. Việc tạo/xóa Pod và cập nhật Endpoints thuộc trách nhiệm của các controller tương ứng, không phải của client discovery.

### Quyền Pod không đồng nghĩa quyền thao tác bên trong Pod

Đọc `pods` có thể lấy trường trạng thái trong đối tượng Pod. Không cần thêm quyền sửa `pods/status` chỉ để xem readiness.

Các subresource như `pods/log`, `pods/exec` và `pods/portforward` là đường truy cập riêng. Vai trò discovery thông thường không cần quyền đọc log hoặc mở phiên exec. Khi chẩn đoán, người vận hành dùng danh tính và quyền của người vận hành, không mở rộng ServiceAccount ứng dụng để tiện thao tác.

## 4. Ghép ServiceAccount, Role và Binding

Một yêu cầu chỉ thành công khi danh tính sử dụng token được cấp quyền phù hợp trên đúng tài nguyên và phạm vi.

- **ServiceAccount** là danh tính gắn cho Pod.
- **Role** mô tả quyền trong một namespace.
- **RoleBinding** gắn Role hoặc ClusterRole với subject trong phạm vi namespace của binding.
- **ClusterRoleBinding** có thể cấp quyền của ClusterRole trên phạm vi toàn cụm.

RoleBinding tham chiếu ClusterRole vẫn giới hạn quyền trên tài nguyên namespaced vào namespace của binding. Tạo ClusterRole không đồng nghĩa mọi ServiceAccount đã nhận được quyền đó.

Quyền RBAC mang tính cộng dồn: một Role hẹp không thu hồi quyền từ binding rộng khác. Các nguyên tắc này được mô tả trong [Kubernetes RBAC](https://kubernetes.io/docs/reference/access-authn-authz/rbac/#role-and-clusterrole).

Khi xem một cấu hình, kiểm tra riêng:

1. Pod chạy với `spec.serviceAccountName` nào?
2. Subject trong binding có đúng tên và namespace của ServiceAccount đó không?
3. `roleRef` trỏ đúng tên, kind và API group chưa?
4. Role hoặc binding đặt ở namespace chứa tài nguyên cần đọc chưa?
5. Có binding khác làm tổng quyền rộng hơn dự định không?

## 5. Ví dụ nền: chỉ discovery trong một namespace

Giả sử `catalog-api` cần DiscoveryClient truy cập API trực tiếp trong `sck-lab`, sử dụng API Endpoints và không đọc ConfigMap/Secret qua API.

[Tài liệu bảo mật Spring Cloud Kubernetes 3.3](https://docs.spring.io/spring-cloud-kubernetes/reference/3.3/security-service-accounts.html) liệt kê `pods`, `services` và `endpoints` cho các starter discovery Fabric8/Kubernetes Java Client. Đây là nhóm quyền khởi điểm cho ví dụ, không phải khẳng định mọi chế độ của mọi phiên bản đều gửi cùng các yêu cầu.

~~~yaml
apiVersion: v1
kind: Namespace
metadata:
  name: sck-lab
---
apiVersion: v1
kind: ServiceAccount
metadata:
  name: catalog-api
  namespace: sck-lab
---
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: sck-discovery-reader
  namespace: sck-lab
rules:
  - apiGroups: [""]
    resources: ["services", "endpoints", "pods"]
    verbs: ["get", "list", "watch"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: catalog-api-discovery
  namespace: sck-lab
subjects:
  - kind: ServiceAccount
    name: catalog-api
    namespace: sck-lab
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: Role
  name: sck-discovery-reader
~~~

Trong template Pod của Deployment ứng dụng, đặt:

~~~yaml
spec:
  template:
    spec:
      serviceAccountName: catalog-api
~~~

Đây là đoạn ghép vào Deployment hiện có, không phải manifest Deployment hoàn chỉnh. Thay đổi template cần được triển khai để Pod mới dùng đúng ServiceAccount.

Giới hạn discovery về namespace phù hợp trong cấu hình ứng dụng:

~~~yaml
spring:
  cloud:
    kubernetes:
      discovery:
        all-namespaces: false
        namespaces:
          - sck-lab
        use-endpoint-slices: false
~~~

Cấu hình tìm kiếm và phạm vi RBAC phải phù hợp với nhau. Danh sách namespace trong Spring chỉ quyết định nơi client tìm kiếm; nó không tự cấp quyền.

Role này cố ý không có `configmaps`, `secrets`, quyền ghi hoặc tài nguyên toàn cụm như `nodes`. Nếu ứng dụng báo thiếu các quyền đó, hãy xác định tính năng nào đang gọi API trước khi bổ sung.

## 6. Khi client sử dụng EndpointSlice

Endpoints và EndpointSlice là hai tài nguyên khác nhau. Quyền đọc `endpoints` trong core group không bao gồm `endpointslices`.

Theo [DiscoveryClient của Spring Cloud Kubernetes 3.3](https://docs.spring.io/spring-cloud-kubernetes/reference/3.3/discovery-client.html), có thể chọn EndpointSlice bằng:

~~~properties
spring.cloud.kubernetes.discovery.use-endpoint-slices=true
~~~

Nếu toàn bộ luồng discovery trong ví dụ đã chuyển sang EndpointSlice, Role tương ứng có thể được khai báo như sau:

~~~yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: sck-discovery-reader
  namespace: sck-lab
rules:
  - apiGroups: [""]
    resources: ["services", "pods"]
    verbs: ["get", "list", "watch"]
  - apiGroups: ["discovery.k8s.io"]
    resources: ["endpointslices"]
    verbs: ["get", "list", "watch"]
~~~

Đây là **biến thể thay thế** Role discovery ở phần trước, không phải một yêu cầu cấp cả hai API trong mọi môi trường. Chỉ loại bỏ quyền Endpoints khi đã xác nhận không còn thành phần nào sử dụng nó. Cần đồng thời xác nhận cluster và implementation client hỗ trợ EndpointSlice.

Có thể kiểm tra tài nguyên mà cluster công bố bằng:

~~~powershell
kubectl api-resources --api-group=discovery.k8s.io
~~~

Lệnh này do người vận hành chạy. Việc cluster công bố tài nguyên không chứng minh ServiceAccount ứng dụng đã có quyền đọc nó.

Nếu client vẫn gửi yêu cầu `list endpoints`, thêm quyền EndpointSlice sẽ không sửa lỗi đó. Hãy đối chiếu cấu hình đang có hiệu lực và phiên bản client.

## 7. Thêm quyền ConfigMap khi thực sự nạp qua API

Giả sử ngoài discovery, `catalog-api` còn nạp ConfigMap qua Spring Cloud Kubernetes tại startup, chưa dùng reload theo sự kiện.

Có thể tách quyền cấu hình thành Role riêng:

~~~yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: sck-configmap-reader
  namespace: sck-lab
rules:
  - apiGroups: [""]
    resources: ["configmaps"]
    verbs: ["get", "list"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: catalog-api-configmap
  namespace: sck-lab
subjects:
  - kind: ServiceAccount
    name: catalog-api
    namespace: sck-lab
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: Role
  name: sck-configmap-reader
~~~

Ví dụ cấu hình ứng dụng, với starter Config phù hợp đã có trên classpath:

~~~yaml
spring:
  application:
    name: catalog-api
  config:
    import: "kubernetes:"
  cloud:
    kubernetes:
      config:
        enabled: true
        enable-api: true
        namespace: sck-lab
        name: catalog-api
      secrets:
        enabled: false
~~~

Đoạn này bổ sung cho cấu hình discovery trước đó. Không tạo thêm một khóa `spring` trùng lặp trong cùng tài liệu YAML; ghép các nhánh vào cấu hình hiện có.

[Tài liệu ConfigMap PropertySource 3.3](https://docs.spring.io/spring-cloud-kubernetes/reference/3.3/property-source-config/configmap-propertysource.html) mô tả cách chọn nguồn theo tên, namespace, label và profile. Tên được cấu hình là đầu vào cho thuật toán tìm nguồn; không phải lời cam kết rằng client chỉ gửi đúng một yêu cầu GET theo tên.

Trong [mã nguồn Fabric8ConfigUtils 3.3.3](https://raw.githubusercontent.com/spring-cloud/spring-cloud-kubernetes/v3.3.3/spring-cloud-kubernetes-fabric8-config/src/main/java/org/springframework/cloud/kubernetes/fabric8/config/Fabric8ConfigUtils.java), luồng chọn cấu hình theo tên vẫn lấy dữ liệu từ cache theo namespace rồi lọc. Vì vậy, không nên suy luận “đã đặt `config.name` thì chỉ cần `get` trên một ConfigMap”.

Khi bật thành phần theo dõi sự kiện, có thể cần thêm `watch` cho đúng tài nguyên. Hãy kiểm tra cả quá trình khởi tạo và kết nối lại. Nếu reload hoặc Watcher không được sử dụng, không cấp quyền theo dõi chỉ vì một manifest mẫu có nó.

Role cấu hình tách riêng giúp nhìn rõ lý do mỗi quyền xuất hiện. Nếu chỉ tắt tính năng trong Spring mà binding vẫn còn, quyền Kubernetes vẫn được cấp.

## 8. Secret là phạm vi dữ liệu khác với ConfigMap

Không thêm `secrets` vào Role discovery theo thói quen. Theo [Secrets PropertySource 3.3](https://docs.spring.io/spring-cloud-kubernetes/reference/3.3/property-source-config/secrets-propertysource.html), truy cập Secret qua API mặc định bị tắt; thuộc tính `spring.cloud.kubernetes.secrets.enableApi` có mặc định `false` trong nhánh này.

Khi có nhu cầu bật API Secret, cần xác định rõ:

- Những Secret nào ứng dụng thực sự cần.
- Client lấy từng Secret theo tên hay lấy danh sách rồi lọc.
- Có theo dõi thay đổi qua API hay chỉ đọc lúc khởi động.
- Có thể sử dụng Secret mount thành tệp thay thế hay không.

Điểm quan trọng là `list` và `watch` trên Secret có thể trả về **dữ liệu Secret**, không chỉ tên và metadata. Xem [thực hành RBAC về quyền liệt kê Secret](https://kubernetes.io/docs/concepts/security/rbac-good-practices/#listing-secrets).

Nếu client cần `list secrets` trong namespace, quyền đó không giới hạn vào Secret được Pod tham chiếu. Label selector trong cấu hình Spring cũng không tự tạo hàng rào authorization cho ServiceAccount.

### Ví dụ giới hạn theo tên và điều kiện áp dụng

Role sau minh họa quyền API **GET một Secret đã biết tên**:

~~~yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: catalog-db-getter
  namespace: sck-lab
rules:
  - apiGroups: [""]
    resources: ["secrets"]
    resourceNames: ["catalog-db"]
    verbs: ["get"]
~~~

Đây chưa phải bộ quyền bảo đảm mọi client Spring Cloud Kubernetes hoạt động. Chỉ bind Role này khi đường đọc thực tế tương thích với GET theo tên. Một client cần lấy danh sách toàn namespace vẫn có thể bị `403` dù cuối cùng chỉ sử dụng `catalog-db`.

Theo [quy tắc resourceNames của Kubernetes](https://kubernetes.io/docs/reference/access-authn-authz/rbac/#referring-to-resources), nếu giới hạn `list/watch` bằng tên, yêu cầu phải mang field selector `metadata.name` phù hợp. Chỉ có label selector hoặc thao tác lọc phía client là chưa đủ.

Không mở rộng thành `list secrets` toàn namespace để chữa lỗi một cách máy móc. Có thể chọn đường đọc khác, tách namespace theo mức tin cậy hoặc điều chỉnh kiến trúc phân phối Secret. Nếu cần quyền rộng hơn vì implementation, phải hiểu rõ phạm vi dữ liệu được cấp.

Giới hạn theo tên cũng không giới hạn theo key trong Secret. Khi được GET đối tượng `catalog-db`, client có thể đọc các trường dữ liệu của đối tượng đó; RBAC thông thường không chọn riêng một khóa mật khẩu.

## 9. Ứng dụng đọc volume không cần trở thành API client

Khi ConfigMap hoặc Secret được khai báo làm volume, kubelet thực hiện việc cung cấp dữ liệu cho Pod. Ứng dụng đọc tệp không tự gửi GET tài nguyên cấu hình bằng token ServiceAccount.

Một cấu hình phù hợp cho ứng dụng chỉ dùng DNS và tệp là ServiceAccount riêng không có các binding đọc API trong bài:

~~~yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: catalog-files
  namespace: sck-lab
automountServiceAccountToken: false
~~~

Đoạn ghép vào template Pod:

~~~yaml
spec:
  template:
    spec:
      serviceAccountName: catalog-files
      automountServiceAccountToken: false
      containers:
        - name: app
          volumeMounts:
            - name: app-config
              mountPath: /etc/runtime/config
              readOnly: true
            - name: app-secret
              mountPath: /etc/runtime/secrets
              readOnly: true
      volumes:
        - name: app-config
          configMap:
            name: catalog-api
        - name: app-secret
          secret:
            secretName: catalog-db
~~~

Đây là phần cấu hình volume cần ghép với container và image hiện có. Các đối tượng ConfigMap/Secret phải tồn tại theo yêu cầu của workload.

Ứng dụng có thể dùng `spring.config.import` để nạp tệp hoặc `configtree:` tùy cách tổ chức dữ liệu. Không bật các tính năng Kubernetes API không sử dụng rồi chỉ tắt token; chúng có thể tiếp tục cố gọi API và báo lỗi.

Theo [cấu hình ServiceAccount cho Pod](https://kubernetes.io/docs/tasks/configure-pod-container/configure-service-account/#opt-out-of-api-credential-automounting), `automountServiceAccountToken: false` tắt tự động mount credentials. Nó không xóa các RoleBinding đã tồn tại và không cấm ứng dụng dùng một credential khác nếu credential đó được cung cấp.

Cũng cần phân biệt:

- Ứng dụng không có quyền API đọc Secret vẫn có thể đọc **Secret đã được mount cho nó**.
- Người có quyền tạo workload có thể có khả năng yêu cầu mount dữ liệu nhạy cảm; đây là quyền của người triển khai, không phải nhu cầu cần cấp thêm cho ứng dụng.
- Token mount và volume Secret nghiệp vụ là hai volume có mục đích khác nhau.

Dữ liệu Secret mount và việc cập nhật volume được mô tả trong [tài liệu Secrets của Kubernetes](https://kubernetes.io/docs/concepts/configuration/secret/#using-secrets-as-files-from-a-pod). Việc đọc tệp thành công chưa chứng minh Spring đã refresh bean; đó là bước xử lý cấu hình tiếp theo.

## 10. Quyền của Configuration Watcher và phạm vi nhiều namespace

### Watcher dùng danh tính riêng

Configuration Watcher chạy ngoài ứng dụng nên nên có ServiceAccount riêng, chẳng hạn `configuration-watcher`. Luồng HTTP thường gồm:

1. Theo dõi ConfigMap/Secret theo cấu hình.
2. Tìm Service và instance đích.
3. Gọi endpoint refresh của ứng dụng.

[Tài liệu Watcher 3.3](https://docs.spring.io/spring-cloud-kubernetes/reference/3.3/spring-cloud-kubernetes-configuration-watcher.html) đưa ra nhóm tài nguyên ConfigMap, Secret, Service, Endpoints và Pod cho controller mẫu. Không lấy toàn bộ nhóm này cấp cho mọi ứng dụng nghiệp vụ.

Đặc biệt, không kết luận một tài nguyên không cần quyền API chỉ vì nó không có label kích hoạt refresh. Thành phần theo dõi có thể vẫn liệt kê hoặc theo dõi tài nguyên trước khi lọc sự kiện. Muốn bỏ quyền Secret phải xác nhận phiên bản và cấu hình thực sự không khởi tạo đường truy cập Secret tương ứng.

| Tiến trình | Ví dụ nhu cầu | Danh tính cấp quyền |
| --- | --- | --- |
| Ứng dụng đọc tệp | Đọc ConfigMap/Secret đã mount | Không cần Role đọc API chỉ cho thao tác đọc tệp |
| Watcher | Theo dõi cấu hình và tìm instance | ServiceAccount của Watcher |
| Pipeline phát hành | Tạo/sửa ConfigMap hoặc rollout | Danh tính triển khai |
| Người chẩn đoán | Xem log hoặc exec theo nhu cầu | Danh tính người vận hành |

RBAC Kubernetes cho Watcher đọc tài nguyên không tự cấp quyền vào `/actuator/refresh`. Kết nối mạng và xác thực endpoint ứng dụng vẫn cần được cấu hình riêng.

### Chỉ mở rộng namespace khi có yêu cầu

Nếu ứng dụng ở `sck-lab` cần đọc dịch vụ ở `shared-services`, có thể tạo Role/RoleBinding phù hợp trong `shared-services`, với subject:

~~~yaml
subjects:
  - kind: ServiceAccount
    name: catalog-api
    namespace: sck-lab
~~~

Namespace của subject xác định danh tính; namespace của RoleBinding xác định phạm vi tài nguyên namespaced được cấp. Hai giá trị không bắt buộc giống nhau.

Cấu hình client tìm đúng danh sách namespace. Nhiều RoleBinding cho một số namespace không đồng nghĩa client được phép gửi một yêu cầu liệt kê **toàn cụm**. Đường API không có thành phần namespace, chẳng hạn `/api/v1/services`, cần quyền phù hợp trên phạm vi đó.

Chỉ dùng ClusterRoleBinding khi có nhu cầu toàn cụm đã xác định. Client biết rõ tên namespace cần tìm không mặc nhiên cần quyền liệt kê tài nguyên `namespaces`.

## 11. Thực hành kiểm tra quyền theo từng cấu hình

Các lệnh dưới đây dùng PowerShell và giả định bạn đã áp dụng manifest tương ứng trong cụm lab có RBAC.

Người áp dụng RBAC cần quyền quản trị phù hợp. Người dùng `--as` phải được phép impersonate danh tính đích; không cấp quyền impersonate cho ứng dụng chỉ để thực hiện bài học. Xem [kubectl auth can-i](https://kubernetes.io/docs/reference/kubectl/generated/kubectl_auth/kubectl_auth_can-i/).

### Bước 1: xác nhận Pod dùng đúng ServiceAccount

Với Deployment ứng dụng tên `catalog-api`:

~~~powershell
kubectl -n sck-lab get deployment catalog-api -o jsonpath='{.spec.template.spec.serviceAccountName}'
kubectl -n sck-lab get pods -l app=catalog-api -o custom-columns='NAME:.metadata.name,SA:.spec.serviceAccountName'
~~~

Tên trong template và các Pod đang kiểm tra phải phù hợp với cấu hình mong muốn. Template đã đổi nhưng Pod cũ chưa được thay thế là một tình huống cần nhận ra.

Không dùng kết quả `kubectl get ...` từ tài khoản quản trị để kết luận ứng dụng có quyền. Hai danh tính có thể nhận kết quả authorization khác nhau.

### Bước 2: kiểm tra cấu hình chỉ discovery bằng Endpoints

~~~powershell
$targetSa = "system:serviceaccount:sck-lab:catalog-api"

kubectl auth can-i get services -n sck-lab --as=$targetSa
kubectl auth can-i list services -n sck-lab --as=$targetSa
kubectl auth can-i watch services -n sck-lab --as=$targetSa

kubectl auth can-i list endpoints -n sck-lab --as=$targetSa
kubectl auth can-i watch endpoints -n sck-lab --as=$targetSa
kubectl auth can-i list pods -n sck-lab --as=$targetSa

kubectl auth can-i list configmaps -n sck-lab --as=$targetSa
kubectl auth can-i get secrets/catalog-db -n sck-lab --as=$targetSa
kubectl auth can-i list secrets -n sck-lab --as=$targetSa

kubectl auth can-i patch services -n sck-lab --as=$targetSa
kubectl auth can-i delete pods -n sck-lab --as=$targetSa
kubectl auth can-i get pods --subresource=log -n sck-lab --as=$targetSa
kubectl auth can-i get nodes --as=$targetSa
~~~

Kỳ vọng của cấu hình nền, khi không có binding rộng khác:

| Phép kiểm tra | Kết quả mong đợi |
| --- | --- |
| Đọc Service, Endpoints, Pod theo Role discovery | `yes` |
| Đọc ConfigMap qua API | `no` |
| GET Secret `catalog-db` hoặc LIST Secret | `no` |
| Sửa Service, xóa Pod, đọc log Pod, đọc Node | `no` |

Các kết quả `no` ở đây xác nhận ranh giới dự định, không phải lỗi cần sửa.

Nếu sử dụng Role biến thể EndpointSlice, kiểm tra thêm:

~~~powershell
kubectl auth can-i list endpointslices.discovery.k8s.io -n sck-lab --as=$targetSa
kubectl auth can-i watch endpointslices.discovery.k8s.io -n sck-lab --as=$targetSa
~~~

Động từ `get` không chứng minh `list` hoặc `watch` thành công. Tương tự, quyền đúng tại `sck-lab` không chứng minh có quyền ở namespace khác.

### Bước 3: kiểm tra sau khi bổ sung Role ConfigMap

~~~powershell
kubectl auth can-i get configmaps/catalog-api -n sck-lab --as=$targetSa
kubectl auth can-i list configmaps -n sck-lab --as=$targetSa
kubectl auth can-i watch configmaps -n sck-lab --as=$targetSa
kubectl auth can-i list secrets -n sck-lab --as=$targetSa
~~~

Với Role startup `get/list` đã minh họa, hai phép kiểm tra đầu chuyển thành `yes`; hai phép kiểm tra sau vẫn là `no`. Nếu tính năng thực tế đòi `watch`, cần thiết kế lại quyền tương ứng, không bỏ qua lỗi.

`can-i` đánh giá quyền cho hành động yêu cầu, không xác nhận tài nguyên tồn tại hay dữ liệu đã nạp đúng vào Spring. Kiểm tra này cũng không thử DNS, TLS hoặc kết nối mạng từ Pod.

Nếu hệ thống có binding theo nhóm, cần kiểm tra cả nhóm mà ServiceAccount thực tế thuộc về bằng cơ chế impersonation được quản trị viên cho phép. Chỉ giả danh username không phải lúc nào cũng mô phỏng đầy đủ các thuộc tính của danh tính thật.

### Bước 4: thử yêu cầu đọc và hành vi Spring

Có thể thử các yêu cầu API thực tế bằng đúng danh tính:

~~~powershell
kubectl -n sck-lab get services --as=$targetSa
kubectl -n sck-lab get endpoints --as=$targetSa
kubectl -n sck-lab get pods --as=$targetSa
~~~

Với cấu hình EndpointSlice, thay lệnh đọc Endpoints bằng:

~~~powershell
kubectl -n sck-lab get endpointslices.discovery.k8s.io --as=$targetSa
~~~

Sau đó kiểm tra DiscoveryClient trong ứng dụng. Một controller quan sát đơn giản, đặt trong package được Spring Boot quét:

~~~java
package example.catalog;

import java.util.List;
import java.util.Map;

import org.springframework.cloud.client.discovery.DiscoveryClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/demo/discovery")
public class DiscoveryProbeController {

    private final DiscoveryClient discoveryClient;

    public DiscoveryProbeController(DiscoveryClient discoveryClient) {
        this.discoveryClient = discoveryClient;
    }

    @GetMapping("/services")
    public List<String> services() {
        return discoveryClient.getServices();
    }

    @GetMapping("/instances/{serviceId}")
    public List<Map<String, Object>> instances(
            @PathVariable("serviceId") String serviceId) {
        return discoveryClient.getInstances(serviceId).stream()
                .map(instance -> Map.<String, Object>of(
                        "host", instance.getHost(),
                        "port", instance.getPort()))
                .toList();
    }
}
~~~

Ví dụ dành cho ứng dụng Java 17 trở lên đã cấu hình DiscoveryClient với một starter phù hợp. Endpoint quan sát nên được truy cập trong phạm vi lab hoặc nội bộ.

Với Service `inventory` có backend sẵn sàng trong namespace được phép, gọi:

~~~text
GET /demo/discovery/services
GET /demo/discovery/instances/inventory
~~~

Kỳ vọng ứng dụng nhìn thấy dịch vụ và instance tương ứng. Nếu danh sách rỗng, chưa thể kết luận thiếu RBAC: cần kiểm tra Service, selector, backend sẵn sàng và bộ lọc discovery.

Khi tính năng theo dõi đang bật, kiểm tra thêm một thay đổi backend hợp lệ có được phản ánh sau thời gian hội tụ hay không. Quyền đọc lúc startup thành công chưa chứng minh watch hoặc kết nối lại hoạt động.

## 12. Đọc lỗi 403 theo yêu cầu bị từ chối

Ví dụ thông điệp rút gọn:

~~~text
User "system:serviceaccount:sck-lab:catalog-api"
cannot list resource "endpointslices"
in API group "discovery.k8s.io"
in the namespace "sck-lab"
~~~

Tách lỗi thành các thuộc tính:

| Thành phần | Giá trị trong ví dụ | Câu hỏi kiểm tra |
| --- | --- | --- |
| Danh tính | `system:serviceaccount:sck-lab:catalog-api` | Có đúng ServiceAccount dự kiến? |
| Động từ | `list` | Role có cấp đúng verb không? |
| Tài nguyên | `endpointslices` | Có nhầm với `endpoints` không? |
| API group | `discovery.k8s.io` | Rule có đặt nhầm core group không? |
| Namespace | `sck-lab` | RoleBinding có nằm đúng phạm vi không? |

Quy trình xử lý nên bám vào yêu cầu cụ thể:

1. Xác nhận lỗi đến từ Kubernetes API hay từ endpoint của ứng dụng.
2. Xác định tính năng đã gửi yêu cầu và lý do cần dữ liệu đó.
3. Đối chiếu danh tính và binding.
4. Kiểm tra đúng verb, resource, group và namespace bằng `can-i`.
5. Bổ sung quyền cần thiết hoặc tắt đường truy cập không sử dụng.
6. Chạy lại yêu cầu và kiểm tra cả ranh giới quyền không mong muốn.

Không biến một lỗi `list endpointslices` thành lý do thêm `resources: ["*"]` hoặc cấp `cluster-admin`.

### Phân biệt một số biểu hiện gần nhau

| Biểu hiện | Hướng kiểm tra ban đầu |
| --- | --- |
| Kubernetes API trả `401` | Credential, token, audience hoặc xác thực |
| Kubernetes API trả `403` | Danh tính đã được xử lý và hành động bị authorization từ chối; đọc thông điệp cụ thể |
| Không có token do tắt automount nhưng API client vẫn bật | Cách cấp credential và nhu cầu sử dụng API |
| Timeout hoặc lỗi TLS | Kết nối tới API, CA, proxy và NetworkPolicy |
| API đọc được nhưng không có instance | Service selector, endpoint sẵn sàng, namespace và bộ lọc |
| Tệp cấu hình đổi nhưng bean còn cũ | Cơ chế refresh và vòng đời bean |
| `/actuator/refresh` trả `403` | Cơ chế bảo vệ endpoint ứng dụng, không mặc định là Kubernetes RBAC |

`403` không có nghĩa nên mở thêm quyền trước khi xác định danh tính. Ví dụ Pod vô tình dùng ServiceAccount `default` phải được sửa cấu hình danh tính, thay vì cấp quyền cho `default` để che lỗi.

## 13. Giữ chính sách sát với nhu cầu thực tế

Một tập quyền phù hợp cần giải thích được từng nhóm tài nguyên:

| Quyền xuất hiện | Lý do hợp lệ cần nêu |
| --- | --- |
| `services` | Thành phần nào đọc định nghĩa và metadata Service |
| `endpoints` hoặc `endpointslices` | Implementation lấy backend qua API nào |
| `pods` | Nhu cầu discovery, metadata hoặc health cụ thể |
| `configmaps` | Nạp hoặc theo dõi cấu hình qua API |
| `secrets` | Nhu cầu dữ liệu nhạy cảm và phạm vi chấp nhận |
| `watch` | Thành phần theo dõi sự kiện và quá trình kết nối lại |
| Quyền ngoài namespace ứng dụng | Namespace đích và lý do cần truy cập |

Không lấy việc một dependency có mặt làm lý do cấp tất cả quyền của module. Có thể dependency kích hoạt thêm tính năng không dùng; khi đó nên điều chỉnh tính năng hoặc dependency trước khi mở rộng chính sách.

Khi nâng phiên bản Spring Cloud Kubernetes, đổi Fabric8 sang Kubernetes Java Client, chuyển Endpoints sang EndpointSlice hoặc thêm Watcher, rà lại tập yêu cầu thực tế. Một Role từng đủ có thể thiếu API mới; một Role cũ cũng có thể giữ quyền không còn cần.

Nếu giảm quyền trong môi trường thử nghiệm, kiểm tra cả startup, lần nạp cấu hình, cập nhật backend và kết nối lại. Cache đã có dữ liệu có thể làm một luồng trông như vẫn hoạt động trong khi quyền để nạp lại đã thiếu.

RBAC, NetworkPolicy và xác thực của ứng dụng giải quyết các đường truy cập khác nhau. Thiết kế chúng theo đúng nơi thực thi: Kubernetes API, kết nối mạng và endpoint nghiệp vụ/quản trị.

## 14. Tình huống củng cố

**Tình huống:** `catalog-api` gọi `inventory` qua DiscoveryClient dùng EndpointSlice, nạp ConfigMap qua API lúc khởi động và nhận mật khẩu từ Secret mount. Ứng dụng không dùng reload theo sự kiện.

Một phương án cần kiểm chứng với implementation đang triển khai:

- Quyền discovery trên `services`, `pods` và `endpointslices`, đúng API group và namespace.
- Quyền nạp ConfigMap phù hợp đường đọc startup; không mặc định thêm watch cho cấu hình.
- Không cấp quyền đọc API Secret chỉ vì mật khẩu nằm trong Secret mount.
- Không cấp quyền ghi Service/EndpointSlice, xóa Pod hoặc exec.
- Có token/credential để thực hiện phần discovery và ConfigMap API; không áp dụng mẫu tắt token dành cho ứng dụng chỉ đọc tệp.
- Kiểm tra ServiceAccount thực tế, hành vi tìm instance và các kết quả từ chối mong đợi.

Nếu sau đó thêm Watcher riêng, hãy đánh giá và cấp quyền cho ServiceAccount của Watcher. Không gộp tự động mọi quyền của controller vào ứng dụng.

Hoàn thành bài thực hành khi bạn chứng minh được luồng discovery/cấu hình cần dùng hoạt động, chỉ ra được tài nguyên và verb tương ứng, và xác nhận các quyền ngoài nhu cầu vẫn không được cấp. Một Role rộng làm ứng dụng hết báo lỗi chưa đủ chứng minh thiết kế RBAC phù hợp.
