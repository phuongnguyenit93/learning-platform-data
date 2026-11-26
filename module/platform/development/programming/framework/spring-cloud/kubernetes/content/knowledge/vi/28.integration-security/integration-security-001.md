# Đánh giá quyền truy cập API server của từng thành phần

## 1. Mục tiêu của việc đánh giá quyền

Trong chương **Bảo mật tích hợp** của module **SPRING_CLOUD_KUBERNETES**, bài này hướng dẫn xác định thành phần nào thực sự cần gọi Kubernetes API server, gọi bằng danh tính nào và cần được phép thực hiện những thao tác nào.

Sau bài học, bạn có thể:

- Lập ma trận quyền cho DiscoveryClient, ConfigMap, Secret, Spring Cloud LoadBalancer và Configuration Watcher.
- Phân biệt quyền của ứng dụng, quyền của controller hỗ trợ và quyền của người triển khai.
- Viết Role và RoleBinding có phạm vi rõ ràng.
- Kiểm tra cả thao tác được phép lẫn thao tác phải bị từ chối.
- Nhận ra những cấu hình chỉ lọc dữ liệu ở client nhưng không giới hạn quyền tại API server.

Tình huống xuyên suốt: namespace `integration-lab` có ứng dụng `orders-api`, dịch vụ `inventory-api`, một DiscoveryServer tùy chọn và một Configuration Watcher. Ứng dụng có thể đọc cấu hình từ tệp mount hoặc từ API, tùy hồ sơ triển khai.

Các hồ sơ trong bài là **những phương án lựa chọn**, không phải yêu cầu cộng tất cả quyền vào cùng một ServiceAccount. Ví dụ dùng cấu trúc RBAC Kubernetes và đối chiếu tính năng với tài liệu Spring Cloud Kubernetes nhánh 5.1. Dự án dùng nhánh khác phải kiểm tra đúng dependency, cấu hình và hành vi của nhánh đó.

Kết quả mong muốn không phải một Role “đủ cho mọi starter”. Đó là bảng giải thích được từng quyền còn lại bằng một tính năng và một đường gọi cụ thể.

## 2. Xác định ai thực sự gửi request

### 2.1. Thư viện không tự có danh tính RBAC riêng

Trong một tiến trình Spring Boot, các thành phần sau có thể cùng dùng một Kubernetes client hoặc cùng đọc credential của Pod:

~~~text
orders-api
  ├─ DiscoveryClient
  ├─ ConfigMap PropertySource
  ├─ Secrets PropertySource nếu được bật
  └─ một số thành phần quan sát metadata
           │
           └─ credential khả dụng trong tiến trình
                    │
                    └─ Kubernetes API server
~~~

Nếu tất cả dùng token của ServiceAccount `orders-api-reader`, API server nhìn thấy cùng một chủ thể:

~~~text
system:serviceaccount:integration-lab:orders-api-reader
~~~

Tạo nhiều bean hoặc đặt nhiều tên package không tạo ra cách ly quyền. Quyền hiệu lực của danh tính phải đáp ứng hợp các thao tác mà những tính năng đã bật thực sự thực hiện.

Muốn tách quyền rõ hơn, có thể tách trách nhiệm sang tiến trình/Pod và ServiceAccount khác, chẳng hạn DiscoveryServer hoặc Configuration Watcher. Cách đó tạo thêm một đường giao tiếp cần bảo vệ và vận hành.

### 2.2. Tách các chủ thể trong hệ thống

| Chủ thể | Ví dụ danh tính | Vai trò trong đánh giá |
| --- | --- | --- |
| Ứng dụng nghiệp vụ | ServiceAccount của `orders-api` | Chỉ giữ quyền cần cho tính năng trong ứng dụng |
| DiscoveryServer | ServiceAccount riêng | Đọc danh mục Kubernetes thay cho HTTP discovery client |
| Configuration Watcher | ServiceAccount riêng | Theo dõi cấu hình và phát thông báo |
| Kubelet | Danh tính node do cluster quản lý | Lấy nguồn volume và vận hành Pod theo cơ chế Kubernetes |
| Pipeline triển khai | Danh tính CI/CD | Tạo hoặc cập nhật workload được phân công |
| Người chẩn đoán | Tài khoản vận hành | Đọc tài nguyên hoặc impersonate khi được cấp quyền |

Ứng dụng đọc Secret đã mount không đồng nghĩa token của ứng dụng đã gửi request đọc Secret. Kubelet và tiến trình ứng dụng là hai chủ thể khác nhau.

Ngược lại, nếu dùng Kubernetes client trong ứng dụng để đọc Secret qua API, phải đánh giá quyền của credential mà chính client đó sử dụng.

### 2.3. Xác minh danh tính trong môi trường thực

Danh tính thực tế có thể khác với dự định nếu:

- Pod dùng nhầm `serviceAccountName`.
- Client được cấu hình bằng kubeconfig hoặc token khác.
- Một sidecar có credential riêng.
- Môi trường chạy ngoài cluster dùng credential của người phát triển.
- Admission hoặc hệ thống quản lý danh tính bổ sung volume/token.

Không dùng kết quả “chạy được trên máy cá nhân” để suy ra ServiceAccount trong cluster có quyền đúng.

ServiceAccount được gắn vào Pod qua `spec.serviceAccountName`; token có thể được tự mount. Có thể tắt tự mount và giá trị ở Pod được ưu tiên nếu khác ServiceAccount. Xem [cấu hình ServiceAccount cho Pod](https://kubernetes.io/docs/tasks/configure-pod-container/configure-service-account/).

## 3. Chuyển mỗi đường gọi thành một yêu cầu quyền cụ thể

Một dòng đánh giá nên mô tả được bộ thông tin sau:

~~~text
chủ thể
+ API group
+ tài nguyên hoặc tài nguyên con
+ động từ
+ namespace
+ tên tài nguyên nếu có giới hạn
+ lý do nghiệp vụ/kỹ thuật
~~~

Ví dụ:

~~~text
Chủ thể:  system:serviceaccount:integration-lab:config-reader
API group: ""
Tài nguyên: configmaps
Động từ: get
Namespace: integration-lab
Tên: orders-settings
Lý do: nạp một ConfigMap đã biết tên lúc khởi động
~~~

### 3.1. HTTP GET không luôn tương đương RBAC get

| Request minh họa | Động từ cần đánh giá |
| --- | --- |
| `GET /api/v1/namespaces/integration-lab/configmaps/orders-settings` | `get` |
| `GET /api/v1/namespaces/integration-lab/configmaps` | `list` |
| `GET /api/v1/namespaces/integration-lab/configmaps?watch=true` | `watch` |
| `POST` tạo một tài nguyên | `create` |
| `PUT` cập nhật tài nguyên | `update` |
| `PATCH` chỉnh một phần tài nguyên | `patch` |

Kubernetes phân loại request theo tài nguyên, phạm vi và thao tác. Quyền `get`, `list`, `watch` đều có thể trả nội dung đối tượng; `list` không chỉ trả tên. Xem [authorization của Kubernetes](https://kubernetes.io/docs/reference/access-authn-authz/authorization/).

Một client dùng informer có thể khởi đầu bằng LIST, sau đó WATCH và có thể LIST lại khi cần đồng bộ. Vì thế, kiểm tra được một lần GET chưa chứng minh đủ quyền cho vòng đời tính năng đó.

### 3.2. Ghi đúng API group và tài nguyên con

| Đối tượng cần truy cập | API group trong RBAC | Tên tài nguyên |
| --- | --- | --- |
| Pod | `""` | `pods` |
| Service | `""` | `services` |
| Endpoints | `""` | `endpoints` |
| ConfigMap | `""` | `configmaps` |
| Secret | `""` | `secrets` |
| EndpointSlice | `discovery.k8s.io` | `endpointslices` |
| Lease | `coordination.k8s.io` | `leases` |
| Log của Pod | `""` | `pods/log` |

Không viết `apiGroups: ["v1"]` cho tài nguyên lõi. Phiên bản API và API group là hai khái niệm khác nhau.

Không suy từ quyền đọc Pod thành quyền đọc log hay chạy lệnh trong container. Các tài nguyên con như `pods/log`, `pods/exec` phải được đánh giá riêng và không phải nhu cầu mặc định của discovery.

### 3.3. Quyền hiệu lực là tổng các quyền được cấp

RBAC cộng các quyền cho phép; không có một dòng “deny” trong Role để trừ quyền đã được binding khác cấp. Role có phạm vi namespace; ClusterRole có thể được tái sử dụng qua RoleBinding hoặc được cấp rộng qua ClusterRoleBinding. Xem [RBAC Kubernetes](https://kubernetes.io/docs/reference/access-authn-authz/rbac/).

Do đó, chỉ xem một Role mới tạo là chưa đủ. Cần xét RoleBinding, ClusterRoleBinding, các nhóm của danh tính và chính sách authorization khác nếu cluster sử dụng.

Một Role hẹp không bảo vệ được ứng dụng nếu cùng ServiceAccount vẫn còn một binding đọc toàn cluster.

## 4. Ma trận đánh giá các thành phần Spring Cloud Kubernetes

Bảng sau là điểm xuất phát để điều tra, không phải một Role chung bảo đảm tối thiểu cho mọi phiên bản.

| Thành phần hoặc cách sử dụng | Có cần ứng dụng gọi API server trực tiếp? | Tài nguyên/thao tác cần xem xét | Chủ thể cần giữ quyền |
| --- | --- | --- | --- |
| HTTP client thông thường gọi DNS của Kubernetes Service đã biết | Không, nếu không có tính năng khác dùng API | Không cấp quyền đọc Service chỉ vì gọi HTTP tới Service | Không phát sinh quyền API ở runtime từ đường gọi này |
| Đọc ConfigMap/Secret đã mount thành tệp | Không từ việc đọc tệp | Đánh giá cấu hình mount và quyền tạo workload ở lớp triển khai | Kubelet thực hiện đường lấy nguồn; ứng dụng chỉ có quyền tệp được cung cấp |
| Nhận Pod name/namespace qua Downward API | Không từ việc đọc dữ liệu được cung cấp | Không cần cấp `list pods` chỉ để biết namespace | Không phát sinh quyền truy vấn từ đường này |
| DiscoveryClient dùng Fabric8 hoặc Kubernetes Java Client | Có | `services`, `endpoints` hoặc `endpointslices`, và `pods` theo implementation/tính năng; thường có `get/list/watch` | ServiceAccount của ứng dụng |
| HTTP DiscoveryClient | Thường gọi DiscoveryServer thay vì API cho discovery | Kiểm tra mọi tính năng khác trong cùng ứng dụng | Client có quyền HTTP; DiscoveryServer có quyền Kubernetes |
| DiscoveryServer | Có | Tài nguyên danh mục trong namespace được phục vụ | ServiceAccount riêng của server |
| Spring Cloud LoadBalancer ở chế độ POD | Theo đường DiscoveryClient được sử dụng | Quyền của nguồn cung cấp instance | Danh tính của tiến trình thực hiện discovery |
| Spring Cloud Kubernetes LoadBalancer ở chế độ SERVICE | Có thể vẫn tìm Service qua API | Đánh giá request đọc/tìm Service thực tế | Danh tính của client được tích hợp |
| ConfigMap PropertySource qua API | Có | `configmaps`; GET theo tên hoặc LIST theo cơ chế đọc, thêm WATCH nếu có luồng theo dõi | ServiceAccount của tiến trình nạp/theo dõi |
| Secrets PropertySource qua API | Có khi bật đường này | `secrets` với phạm vi được duyệt | ServiceAccount của tiến trình đọc |
| Configuration Watcher | Có | ConfigMap/Secret được theo dõi, tài nguyên discovery nếu dùng để tìm đích | ServiceAccount riêng của Watcher |
| Leader election được bật | Có thể cần ghi | Tài nguyên khóa và động từ đúng backend/phiên bản | Chỉ thành phần tham gia bầu leader |
| Probe HTTP cơ bản của ứng dụng | Không chỉ vì có probe | Không cần quyền quản lý Pod để trả tình trạng nội tại | Không phát sinh quyền API từ probe cơ bản |
| Kubernetes health/info contributor | Phải kiểm tra implementation đang dùng | Có thể bổ sung đường đọc metadata Pod | Danh tính thực tế của contributor |

Hướng dẫn bảo mật của Spring Cloud Kubernetes liệt kê nhóm tài nguyên liên quan tới các starter, gồm Pod, Service, Endpoints, ConfigMap và Secret. Bảng đó là căn cứ ban đầu; vẫn phải thu hẹp theo tính năng bật thực tế. Xem [Security Configurations Inside Kubernetes](https://docs.spring.io/spring-cloud-kubernetes/reference/security-service-accounts.html).

### 4.1. DiscoveryClient trực tiếp và HTTP discovery

Spring Cloud Kubernetes có các lựa chọn Fabric8, Kubernetes Java Client và HTTP DiscoveryClient. Các cấu hình namespace và EndpointSlice ảnh hưởng phạm vi truy vấn, loại tài nguyên cần cấp quyền. Xem [DiscoveryClient for Kubernetes](https://docs.spring.io/spring-cloud-kubernetes/reference/discovery-client.html).

Với HTTP discovery, quyền được chuyển sang một tiến trình hỗ trợ. DiscoveryServer vẫn cần quyền đọc danh mục; tài liệu mô tả nhu cầu đọc Pod, Service và Endpoint. Xem [DiscoveryServer](https://docs.spring.io/spring-cloud-kubernetes/reference/spring-cloud-kubernetes-discoveryserver.html).

Đánh giá hai mặt:

- Runtime client có thể giảm quyền Kubernetes dành riêng cho discovery.
- DiscoveryServer trở thành nơi tập trung metadata và quyền đọc; cần giới hạn namespace và bảo vệ HTTP endpoint.
- Nếu runtime vẫn nạp ConfigMap qua API, nó vẫn cần credential và quyền cho cấu hình.
- Không kết luận “ứng dụng không cần token” chỉ vì đã đổi loại discovery.

### 4.2. LoadBalancer không tự xóa nhu cầu discovery

Spring Cloud Kubernetes LoadBalancer có chế độ `POD` và `SERVICE`. Chế độ SERVICE vẫn có bước tìm Service; không đồng nhất nó với HTTP client thông thường gọi một DNS cố định. Xem [LoadBalancer for Kubernetes](https://docs.spring.io/spring-cloud-kubernetes/reference/load-balancer.html).

Khi lập ma trận, đi theo chuỗi:

~~~text
HTTP client
  -> bộ chọn đích
  -> ServiceInstanceListSupplier hoặc thành phần tương đương
  -> DiscoveryClient/Kubernetes client
  -> tài nguyên và namespace thực sự bị truy vấn
~~~

Thêm cache có thể giảm tần suất gọi, nhưng không làm mất nhu cầu cấp quyền cho khởi tạo, cache miss hoặc đồng bộ lại.

### 4.3. Quan sát sức khỏe không mặc định cần quyền quản trị Pod

Pod health indicator và info contributor của Spring Cloud Kubernetes cung cấp metadata của Pod. Có thể tắt từng contributor nếu không dùng; cần xem cách lấy metadata của implementation trước khi cấp thêm quyền. Xem [Pod Health Indicator](https://docs.spring.io/spring-cloud-kubernetes/reference/pod-health-indicator.html) và [Info Contributor](https://docs.spring.io/spring-cloud-kubernetes/reference/info-contributor.html).

Nếu chỉ cần Pod name, namespace hoặc một số trường được hỗ trợ, có thể cung cấp qua Downward API thay vì xây thêm truy vấn danh mục. Xem [Downward API](https://kubernetes.io/docs/concepts/workloads/pods/downward-api/).

Không cấp `get nodes` chỉ vì health response có tên node. Tên node được cung cấp trong Pod metadata không đồng nghĩa cần đọc đối tượng Node.

## 5. Lập hồ sơ quyền trước khi viết Role

Với từng tiến trình, ghi ít nhất các thông tin sau:

| Trường hồ sơ | Ví dụ |
| --- | --- |
| Tiến trình | `orders-api` |
| Tính năng | Đọc cấu hình qua API lúc khởi động |
| Phiên bản/client | Ghi đúng BOM và implementation triển khai |
| Credential | Token của ServiceAccount `config-reader` |
| Tài nguyên | `configmaps` |
| Động từ | `get` nếu đường chạy chỉ GET tài nguyên theo tên |
| Phạm vi | Namespace `integration-lab`, tên `orders-settings` |
| Giai đoạn | Khởi động; đánh giá lại nếu bật refresh/watch |
| Bằng chứng | Tài liệu đúng phiên bản và request quan sát được trong lab |
| Quyền phải không có | Đọc Secret, sửa ConfigMap, tạo Pod, đọc namespace khác |

Để tìm phần dư, lần lượt hỏi:

1. Tính năng này có thật sự được dùng hay chỉ được auto-configure do dependency?
2. Có đường dùng DNS hoặc tệp mount đáp ứng cùng yêu cầu không?
3. Client lấy đúng một đối tượng hay liệt kê cả namespace rồi lọc?
4. Nó có mở informer/watch cho tài nguyên bổ sung không?
5. Khi reconnect, bật profile khác hoặc có replica mới, request có đổi không?
6. Nếu cấp quyền này cho toàn bộ tiến trình, phạm vi ảnh hưởng khi credential bị lộ là gì?

Một quyền chỉ xuất hiện trong ví dụ triển khai tổng quát chưa đủ để giữ lại trong Role sản xuất. Ngược lại, một quyền chưa xuất hiện trong vài phút quan sát cũng chưa đủ để xóa nếu đường phục hồi chưa được thử.

## 6. Hồ sơ A: runtime chỉ dùng DNS và tệp mount

Giả sử `orders-api` gọi `inventory-api` qua DNS đã biết và đọc cấu hình/Secret từ volume. Các tích hợp gọi API khác đã được tắt hoặc loại bỏ sau khi xác minh.

ServiceAccount riêng:

~~~yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: orders-runtime
  namespace: integration-lab
automountServiceAccountToken: false
~~~

Phần Pod template sau là **đoạn ghép vào Deployment đã có**, không phải manifest Deployment hoàn chỉnh. Container `orders-api` cần giữ nguyên image và các cấu hình nghiệp vụ của dự án.

~~~yaml
spec:
  template:
    spec:
      serviceAccountName: orders-runtime
      automountServiceAccountToken: false
      containers:
        - name: orders-api
          env:
            - name: POD_NAMESPACE
              valueFrom:
                fieldRef:
                  fieldPath: metadata.namespace
          volumeMounts:
            - name: orders-config
              mountPath: /etc/orders/config
              readOnly: true
            - name: orders-secret
              mountPath: /etc/orders/secret
              readOnly: true
      volumes:
        - name: orders-config
          configMap:
            name: orders-settings
        - name: orders-secret
          secret:
            secretName: orders-db
~~~

ConfigMap và Secret tham chiếu phải tồn tại trong namespace của Pod; ứng dụng phải được cấu hình để thực sự đọc các tệp đó. Không dùng `subPath` nếu mong nhận cập nhật volume theo cơ chế thông thường.

Ở hồ sơ này, không tạo RoleBinding đọc ConfigMap/Secret cho runtime chỉ để cho phép mount. Cần đánh giá đường truy cập tệp và quyền triển khai workload riêng. Kubernetes mô tả việc phân phối Secret tới Pod thông qua cơ chế volume/kubelet. Xem [Secrets](https://kubernetes.io/docs/concepts/configuration/secret/).

Tắt automount giảm việc tự cung cấp credential vào Pod; nó không phải quy tắc cấm mạng tới API server, không xóa binding đã có và không ngăn credential được cung cấp qua đường khác.

Việc mount Secret cũng không biến dữ liệu đó thành vô hại: tiến trình được đọc tệp vẫn có thể đọc chính bí mật được mount. Phạm vi giảm ở đây là khả năng dùng credential để truy vấn thêm tài nguyên ngoài những nguồn đã được cung cấp.

## 7. Hồ sơ B: discovery trực tiếp trong một namespace

Ví dụ dưới đây dùng hồ sơ discovery qua **Endpoints** theo nhóm quyền thường gặp trong tài liệu. Nó cố ý tách khỏi quyền đọc cấu hình và Secret.

Đây là điểm xuất phát để kiểm chứng với client đang dùng; không khẳng định ba tài nguyên đều là tối thiểu cho mọi cấu hình.

~~~yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: discovery-reader
  namespace: integration-lab
---
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: discovery-catalog-reader
  namespace: integration-lab
rules:
  - apiGroups: [""]
    resources: ["pods", "services", "endpoints"]
    verbs: ["get", "list", "watch"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: discovery-reader-catalog
  namespace: integration-lab
subjects:
  - kind: ServiceAccount
    name: discovery-reader
    namespace: integration-lab
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: Role
  name: discovery-catalog-reader
~~~

Pod hoặc Deployment chọn `serviceAccountName: discovery-reader` khi dùng hồ sơ này. Cần credential phù hợp cho client, bao gồm cơ chế token và xác minh CA; không ghép nguyên cấu hình tắt token của hồ sơ A rồi giả định API client vẫn xác thực được.

Nếu dùng EndpointSlice, phải đối chiếu cấu hình `spring.cloud.kubernetes.discovery.use-endpoint-slices` và thêm đúng nhóm tài nguyên tương ứng:

~~~yaml
- apiGroups: ["discovery.k8s.io"]
  resources: ["endpointslices"]
  verbs: ["get", "list", "watch"]
~~~

Đây là một phần tử trong `rules`. Khi đã chuyển đường truy vấn sang EndpointSlice, xem liệu còn cần quyền Endpoints hay không bằng tài liệu và hành vi của client. Không giữ cả hai chỉ vì muốn “chắc chắn”.

Tương tự, đánh giá nhu cầu `pods` theo implementation và tính năng metadata. Không tự xóa quyền từ một cấu hình chưa được quan sát đầy đủ, cũng không dùng việc cần Pod metadata để biện minh cho quyền đọc log, exec hay sửa workload.

### 7.1. Nhiều namespace không nhất thiết cần ClusterRoleBinding

Nếu chỉ cần hai namespace xác định, có thể dùng cùng một ClusterRole đọc tài nguyên namespaced và tạo RoleBinding ở từng namespace đích.

~~~text
ServiceAccount ở integration-lab
  -> RoleBinding trong integration-lab
  -> RoleBinding trong inventory-lab
  -> không có binding ở namespace ngoài danh sách
~~~

RoleBinding phải nằm trong namespace chứa tài nguyên đích; `subjects[].namespace` xác định namespace của ServiceAccount. Đây là hai vị trí có ý nghĩa khác nhau.

Cấu hình `all-namespaces` có thể dẫn tới request liệt kê trên toàn cluster. Đừng bật nó rồi cấp ClusterRoleBinding để chữa một lỗi phát sinh từ cấu hình vượt nhu cầu.

Danh sách namespace ở client và giới hạn quyền tại API server cần khớp nhau. Chỉ đặt namespace trong cấu hình ứng dụng chưa làm mất quyền đọc namespace khác nếu credential vẫn đang được cấp quyền đó.

## 8. Hồ sơ C: đọc một ConfigMap đã biết tên

Giả sử đã xác minh đường nạp cấu hình chỉ GET `orders-settings` trong `integration-lab`, không dùng batch listing, profile bổ sung, reload hoặc watch.

~~~yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: config-reader
  namespace: integration-lab
---
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: orders-settings-getter
  namespace: integration-lab
rules:
  - apiGroups: [""]
    resources: ["configmaps"]
    resourceNames: ["orders-settings"]
    verbs: ["get"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: config-reader-orders-settings
  namespace: integration-lab
subjects:
  - kind: ServiceAccount
    name: config-reader
    namespace: integration-lab
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: Role
  name: orders-settings-getter
~~~

Role này thể hiện hợp đồng GET theo tên. Nó không tự làm Spring Cloud Kubernetes đổi từ LIST sang GET.

Tài liệu ConfigMap PropertySource nhánh 5.x phân biệt `BATCH` và `SINGLE`: batch có thể lấy tập tài nguyên trong namespace trước khi lọc; single lấy theo tên. Cần kiểm tra chế độ đọc và các nguồn cấu hình được bật trước khi áp dụng Role giới hạn tên. Xem [ConfigMap PropertySource](https://docs.spring.io/spring-cloud-kubernetes/reference/property-source-config/configmap-propertysource.html).

Ví dụ định hướng cho nhánh hỗ trợ chế độ này:

~~~yaml
spring:
  cloud:
    kubernetes:
      config:
        read-type: SINGLE
        name: orders-settings
        namespace: integration-lab
        include-profile-specific-sources: false
~~~

Đây là phần cấu hình chế độ đọc, không thay thế cấu hình dependency và cơ chế import nguồn cấu hình của dự án. Các nguồn khác, profile, label lookup và tính năng reload phải được xét riêng.

### 8.1. resourceNames không phải bộ lọc hậu xử lý

Với LIST/WATCH bị giới hạn tên bằng RBAC, client cần gửi `metadata.name` field selector phù hợp để được cấp quyền. Label selector không thay cho yêu cầu đó. Không giả định informer của mọi client đều gửi selector cần thiết.

Nếu client cần LIST cả namespace, hãy lựa chọn rõ:

- Đổi cơ chế đọc sang đường hỗ trợ giới hạn theo tên.
- Chấp nhận quyền rộng hơn sau khi đánh giá dữ liệu trong namespace.
- Chuyển sang mount tệp nếu đáp ứng yêu cầu.

Không thêm `list/watch` một cách máy móc để làm biến mất lỗi 403.

### 8.2. Secret là một quyết định cấp quyền khác

Secrets PropertySource có đường đọc mount và đường đọc API; đường API cần được bật và đánh giá riêng. Tài liệu lưu ý quyền list Secret có thể cho đọc giá trị Secret trong namespace. Xem [Secrets PropertySource](https://docs.spring.io/spring-cloud-kubernetes/reference/property-source-config/secrets-propertysource.html).

Không thêm `secrets` vào cùng Role chỉ vì ConfigMap và Secret đều là nguồn cấu hình.

Nếu có nhu cầu GET Secret theo tên, thiết kế quy tắc riêng và xác minh client thực sự chỉ GET những tên được duyệt. Bật API Secret phải đi cùng quyết định ai được nhìn thấy nội dung, trong phạm vi nào và để làm gì.

## 9. Đánh giá Configuration Watcher như một controller độc lập

Watcher có hai hướng quyền khác nhau:

~~~mermaid
flowchart LR
    API["Kubernetes API server"]
    W["Configuration Watcher"]
    APP["orders-api /actuator/refresh"]
    BUS["Spring Cloud Bus nếu dùng"]
    W -->|"credential Kubernetes và RBAC"| API
    W -->|"quyền gọi HTTP ứng dụng"| APP
    W -->|"credential và quyền broker"| BUS
~~~

### 9.1. Quyền phía Kubernetes

Lập riêng các dòng hồ sơ:

| Chức năng của Watcher | Quyền cần điều tra |
| --- | --- |
| Theo dõi ConfigMap | Động từ và phạm vi trên `configmaps` |
| Theo dõi Secret nếu được bật | Động từ và phạm vi trên `secrets` |
| Tìm instance đích bằng discovery | Tài nguyên danh mục đúng client đang dùng |
| Leader election/HA nếu được bật | Tài nguyên khóa và các thao tác ghi đúng backend |

Một hồ sơ Watcher chỉ theo dõi ConfigMap không nên mặc nhiên được đọc Secret. Phải tắt đường theo dõi Secret tương ứng và xác minh lúc khởi động, theo dõi và reconnect không có request Secret ngoài dự định.

Ví dụ quy tắc đọc cho hồ sơ **ConfigMap + discovery qua Endpoints**, khi đã xác định các nhóm tài nguyên cần dùng:

~~~yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: config-watcher-reader
  namespace: integration-lab
rules:
  - apiGroups: [""]
    resources: ["configmaps"]
    verbs: ["get", "list", "watch"]
  - apiGroups: [""]
    resources: ["pods", "services", "endpoints"]
    verbs: ["get", "list", "watch"]
~~~

Role này cần được bind cho ServiceAccount riêng của Watcher, không bind cho mọi Pod nghiệp vụ. Nếu Watcher không sử dụng một đường discovery hoặc một nhóm tài nguyên nêu trên, tiếp tục thu hẹp theo bằng chứng.

Label theo dõi có thể giảm số nguồn xử lý; nó không phải ranh giới bảo mật của RBAC thông thường. Một credential có LIST Secret cả namespace không bị giới hạn chỉ còn các Secret có label mà client tự chọn.

### 9.2. Quyền cập nhật khóa không phải quyền cập nhật cấu hình ứng dụng

Với cơ chế HA dùng Lease được tài liệu nhánh 5.1 mô tả, Watcher cần các thao tác như `get/create/update` trên `leases` thuộc `coordination.k8s.io`. Xem [Configuration Watcher](https://docs.spring.io/spring-cloud-kubernetes/reference/spring-cloud-kubernetes-configuration-watcher.html).

Chỉ bổ sung khi thực sự bật tính năng đó. Không chuyển mọi quy tắc ConfigMap/Secret sang `verbs: ["*"]` để làm leader election hoạt động.

Nếu backend khác dùng ConfigMap làm khóa, tách đối tượng khóa khỏi ConfigMap cấu hình nghiệp vụ. Việc giới hạn tên và thao tác phải tương thích với đường tạo/cập nhật khóa; giới hạn `resourceNames` không tự áp dụng được cho mọi request CREATE tài nguyên cấp cao nhất.

### 9.3. Quyền gọi refresh thuộc ứng dụng

Quyền Kubernetes `get configmaps` không cấp quyền HTTP `POST /actuator/refresh`. Ngược lại, caller được phép gọi refresh không tự được quyền đọc Secret từ Kubernetes.

Vì thế cần đánh giá riêng:

- Ai được gọi endpoint quản trị.
- Cách xác thực và phân quyền caller.
- Giới hạn mạng tới endpoint.
- Những replica được chọn làm đích.
- Cách xác nhận cấu hình đã được áp dụng thành công.

Không giả định token ServiceAccount tự được Spring Security chấp nhận. Nếu muốn dùng nó làm credential cho HTTP nội bộ, ứng dụng và cơ chế xác minh danh tính phải được thiết kế tương ứng.

Nếu dùng Bus, đánh giá credential và quyền broker theo đường đó; không dùng RBAC Kubernetes để thay cho quyền publish/subscribe trên broker.

## 10. Kiểm chứng quyền bằng can-i và request thực tế

### 10.1. Kiểm tra danh tính runtime trước

Các lệnh dưới đây là hướng dẫn cho lab, chạy từ máy quản trị có quyền đọc workload:

~~~powershell
kubectl -n integration-lab get deployment orders-api -o jsonpath='{.spec.template.spec.serviceAccountName}'
kubectl -n integration-lab get deployment orders-api -o jsonpath='{.spec.template.spec.automountServiceAccountToken}'
kubectl -n integration-lab get pods -l app=orders-api -o custom-columns=NAME:.metadata.name,SA:.spec.serviceAccountName,AUTOMOUNT:.spec.automountServiceAccountToken
~~~

Giá trị automount rỗng ở một vị trí chưa đủ kết luận là false; cần xét cấu hình ServiceAccount và Pod thực tế. Workload template và Pod đã chạy cũng có thể khác trong thời gian rollout.

Không đọc token ra màn hình để xác minh danh tính. Dùng cấu hình Pod, log được lọc và dữ liệu audit phù hợp.

### 10.2. Mô phỏng chủ thể bằng impersonation

`kubectl auth can-i` kiểm tra khả năng thực hiện một hành động; có thể dùng `--as` để kiểm tra danh tính khác khi người chạy có quyền impersonation. Xem [kubectl auth can-i](https://kubernetes.io/docs/reference/kubectl/generated/kubectl_auth/kubectl_auth_can-i/).

Ví dụ PowerShell cho `discovery-reader`:

~~~powershell
$discoveryIdentity = @(
  '--as=system:serviceaccount:integration-lab:discovery-reader'
  '--as-group=system:serviceaccounts'
  '--as-group=system:serviceaccounts:integration-lab'
  '--as-group=system:authenticated'
)

kubectl auth can-i list services -n integration-lab @discoveryIdentity
kubectl auth can-i watch endpoints -n integration-lab @discoveryIdentity
kubectl auth can-i list secrets -n integration-lab @discoveryIdentity
kubectl auth can-i patch services -n integration-lab @discoveryIdentity
kubectl auth can-i create pods -n integration-lab @discoveryIdentity
kubectl auth can-i get pods --subresource=log -n integration-lab @discoveryIdentity
kubectl auth can-i list services -n integration-other @discoveryIdentity
~~~

Trong môi trường lab áp dụng đúng hồ sơ B và không có grant bổ sung, hai dòng đầu dự kiến `yes`, các dòng còn lại dự kiến `no`.

Các nhóm được ghi rõ để không bỏ sót binding cấp theo nhóm ServiceAccount. Người chạy cần quyền impersonate cả danh tính và các nhóm được yêu cầu. Nếu bị từ chối impersonation, đó chưa phải kết quả từ chối của ServiceAccount đích. Xem [user impersonation](https://kubernetes.io/docs/reference/access-authn-authz/authentication/#user-impersonation).

Không cấp quyền impersonate cho ứng dụng chỉ để các lệnh kiểm tra này chạy được. Đây là quyền của kênh kiểm thử/vận hành được quản lý.

### 10.3. Kiểm tra riêng Role giới hạn tên

~~~powershell
$configIdentity = @(
  '--as=system:serviceaccount:integration-lab:config-reader'
  '--as-group=system:serviceaccounts'
  '--as-group=system:serviceaccounts:integration-lab'
  '--as-group=system:authenticated'
)

kubectl auth can-i get configmaps/orders-settings -n integration-lab @configIdentity
kubectl auth can-i get configmaps/unrelated-settings -n integration-lab @configIdentity
kubectl auth can-i list configmaps -n integration-lab @configIdentity
kubectl auth can-i update configmaps/orders-settings -n integration-lab @configIdentity
kubectl auth can-i get secrets/orders-db -n integration-lab @configIdentity
~~~

Khi chỉ có hồ sơ C, dự kiến chỉ dòng đầu trả `yes`.

Tiếp theo, dùng request đọc trên ConfigMap lab không nhạy cảm:

~~~powershell
kubectl -n integration-lab get configmap orders-settings -o name @configIdentity
kubectl -n integration-lab get configmaps -o name @configIdentity
~~~

GET theo tên dự kiến thành công; LIST không giới hạn dự kiến bị từ chối. `-o name` chỉ thay cách hiển thị của kubectl, không biến một request LIST thành quyền “chỉ đọc tên”.

### 10.4. can-i chưa kiểm tra toàn bộ đường kết nối

Kết quả authorization không chứng minh:

- Pod thực sự có token đúng.
- Token còn hạn, đúng audience và được client nạp lại khi xoay vòng.
- CA và hostname của API server được xác minh đúng.
- Mạng từ Pod tới API server hoạt động.
- Informer đã hoàn tất khởi tạo và reconnect đúng.
- Tính năng thật sự chỉ gửi những request đã dự đoán.

ServiceAccount token hiện đại có cơ chế projected token và xoay vòng; không thiết kế ứng dụng dựa trên việc sao chép token tĩnh vào cấu hình. Xem [Service Accounts](https://kubernetes.io/docs/concepts/security/service-accounts/).

Do đó, phải thử bằng chính tiến trình triển khai trong lab, với cùng client và cấu hình dự kiến sử dụng. Chỉ nhìn kết quả của người quản trị không kiểm chứng được credential runtime.

## 11. Dùng audit để đối chiếu quyền đã cấp và quyền đã dùng

Khi có quyền truy cập kênh audit của cluster, đối chiếu tối thiểu:

~~~text
user.username
user.groups
verb
objectRef.apiGroup
objectRef.resource
objectRef.subresource
objectRef.namespace
objectRef.name
responseStatus.code
requestURI
~~~

Mức audit `Metadata` ghi thông tin request mà không ghi body request/response; nội dung cụ thể phụ thuộc chính sách audit và dịch vụ cluster. Xem [Auditing](https://kubernetes.io/docs/tasks/debug/debug-cluster/audit/).

Ví dụ diễn giải một bản ghi được rút gọn:

~~~text
user=system:serviceaccount:integration-lab:config-reader
verb=list
resource=configmaps
namespace=integration-lab
code=403
~~~

Đây là dấu hiệu client đã LIST, trái giả định “chỉ GET một ConfigMap”. Hướng xử lý là kiểm tra chế độ đọc, nguồn theo label, profile hoặc client đang sử dụng. Không mặc định thêm LIST ngay lập tức.

Các giai đoạn cần quan sát:

1. Khởi động lạnh.
2. Lần gọi discovery đầu tiên.
3. Cập nhật ConfigMap hoặc Secret được phép theo dõi.
4. Watch bị ngắt và nối lại.
5. Replica mới tham gia.
6. Leader thay đổi nếu bật cơ chế bầu leader.
7. Credential được xoay vòng.

Không thấy request trong một cửa sổ audit ngắn chỉ là bằng chứng trong cửa sổ đó. Cache hoặc đường code chưa được kích hoạt có thể che mất nhu cầu thực.

Không bật ghi body Secret để tiện đánh giá quyền. Tránh đưa Authorization header, token hoặc giá trị bí mật vào log ứng dụng và báo cáo kiểm thử.

## 12. Những giới hạn dễ bị hiểu nhầm

### 12.1. Label và namespace selector của client không thay RBAC

Nếu Role cho LIST toàn bộ ConfigMap trong namespace, client có thể gửi request với label khác hoặc không có label. Bộ lọc ở thư viện giúp chọn dữ liệu và giảm công việc; nó không tạo quyền chỉ được đọc một tập label ở API server bằng RBAC thông thường.

Tương tự, namespace được cấu hình trong ứng dụng là dự định truy vấn. Phạm vi quyền thực tế còn phụ thuộc binding.

### 12.2. “Chỉ đọc” vẫn có thể lộ dữ liệu nhạy cảm

Đọc Secret có thể dẫn tới lộ credential truy cập cơ sở dữ liệu hoặc hệ thống khác. Đọc Pod/Service metadata cũng có thể lộ địa chỉ nội bộ, tên ứng dụng và annotation không nên công khai.

Vì vậy, đánh giá tác động của nội dung được trả về, không chỉ hỏi quyền có sửa được tài nguyên hay không.

### 12.3. Không đọc Secret qua API vẫn phải xét quyền tạo workload

Chủ thể có quyền tạo workload có thể có khả năng tham chiếu Secret hoặc chọn ServiceAccount trong namespace, tùy các kiểm soát admission liên quan. Đây là lý do quyền triển khai và ranh giới namespace cần được xét cùng quyền đọc trực tiếp. Xem [RBAC good practices](https://kubernetes.io/docs/concepts/security/rbac-good-practices/).

Không dùng việc runtime thiếu `get secrets` để kết luận pipeline có thể tạo Pod tùy ý mà không ảnh hưởng bí mật.

### 12.4. NetworkPolicy, TLS và RBAC giải quyết các lớp khác nhau

- Giới hạn mạng quyết định đường kết nối nào có thể tới đích.
- TLS giúp xác minh đích và bảo vệ đường truyền theo cấu hình.
- Credential xác định chủ thể được xác thực.
- Authorization quyết định thao tác mà chủ thể được làm.

Kết nối thành công không chứng minh đủ quyền. Lỗi TLS không được chữa bằng cách cấp thêm Role. Lỗi 403 không được chữa bằng cách tắt xác minh chứng thư.

### 12.5. Thu hồi quyền không xóa dữ liệu đã được đọc

Loại bỏ binding không tự xóa Secret đã đọc vào RAM, tệp đã mount hoặc dữ liệu đã được sao chép. Watch/connection đang mở và quá trình xoay credential cũng cần được đánh giá theo cơ chế thực tế.

Nếu credential đã lộ, kế hoạch xử lý phải xét cả credential bị lộ và bí mật mà nó có thể đã đọc. Không coi việc sửa một Role là đủ để thu hồi mọi bản dữ liệu đã phân phối.

## 13. Bài thực hành: tách quyền của một triển khai đang dùng chung tài khoản

Giả sử thiết kế ban đầu dùng một ServiceAccount cho `orders-api`, DiscoveryServer và Watcher. Tài khoản đó được đọc ConfigMap, Secret, Pod, Service và Endpoint ở nhiều namespace.

Yêu cầu thực tế:

- `orders-api` chỉ gọi DNS của `inventory-api`, đọc ConfigMap/Secret đã mount.
- DiscoveryServer chỉ phục vụ danh mục của `integration-lab`.
- Watcher chỉ theo dõi ConfigMap và tìm replica cần refresh.
- Không bật leader election trong phiên bản triển khai lab này.
- Pipeline có trách nhiệm cập nhật Deployment; runtime không tự sửa workload.

### 13.1. Thiết kế mục tiêu

| Thành phần | ServiceAccount/danh tính | Quyền mục tiêu | Quyền loại bỏ khỏi thành phần này |
| --- | --- | --- | --- |
| `orders-api` | `orders-runtime` | Không cần quyền API cho các đường đã nêu; tắt token tự mount | Đọc danh mục và Secret qua API |
| DiscoveryServer | `discovery-reader` | Đọc tài nguyên discovery đã xác định trong một namespace | Đọc ConfigMap/Secret và sửa workload |
| Watcher | `config-watcher` | Theo dõi ConfigMap, đọc danh mục cần cho chọn đích | Đọc Secret nếu tính năng này tắt; ghi khóa khi không bật election |
| Pipeline | Danh tính CI/CD riêng | Quyền triển khai đúng phạm vi được quản lý | Không tái sử dụng credential này cho runtime |

Đây là kết quả thiết kế cần kiểm chứng, không phải báo cáo rằng hệ thống lab đã chạy thành công.

### 13.2. Trình tự kiểm chứng trong môi trường riêng

1. Chuẩn bị namespace `integration-lab` và một namespace đối chứng `integration-other`.
2. Tạo các tài nguyên cấu hình không nhạy cảm phục vụ thử nghiệm; Secret lab chỉ chứa dữ liệu giả.
3. Ghi lại đúng phiên bản, tính năng bật và ServiceAccount của từng Pod.
4. Áp dụng hồ sơ quyền tương ứng bằng kênh triển khai được phân quyền.
5. Kiểm tra các quyền được phép và phải bị từ chối bằng `can-i`.
6. Khởi động lại từng thành phần lab để quan sát đường khởi tạo không dựa vào cache cũ.
7. Gọi discovery, cập nhật ConfigMap và xác minh từng replica nhận cấu hình theo cơ chế đã thiết kế.
8. Thử ngắt/kết nối lại đường API trong lab để quan sát LIST/WATCH phát sinh.
9. Đối chiếu audit và log đã lọc với ma trận dự kiến.
10. Xóa binding dùng chung cũ qua quy trình triển khai, sau khi xác nhận các workload đã chuyển sang danh tính mục tiêu.

Không giữ nguyên binding cũ rồi tuyên bố thành công vì các Role hẹp mới không gây lỗi. Khi grant rộng vẫn tồn tại, chưa chứng minh được ranh giới quyền mới.

### 13.3. Dấu hiệu cần điều tra thêm

| Hiện tượng | Điều cần kiểm tra |
| --- | --- |
| Runtime không cần API nhưng vẫn có request đọc Pod | Contributor hoặc tính năng auto-configure còn bật |
| ConfigMap theo tên vẫn phát sinh LIST | Chế độ đọc, label source, profile hoặc implementation |
| Watcher phát sinh request Secret dù hồ sơ chỉ ConfigMap | Tính năng theo dõi/nạp Secret chưa được tắt như dự định |
| ServiceAccount đọc được namespace đối chứng | Binding cấp rộng hoặc cấp theo nhóm |
| Chạy được bằng kubectl quản trị nhưng Pod bị 403 | Sai chủ thể, sai nhóm quyền hoặc request thực tế khác |
| Discovery qua HTTP vẫn yêu cầu token trong runtime | Tính năng khác còn gọi Kubernetes API hoặc cấu hình client chưa đúng |
| Chỉ lỗi khi reconnect | Thiếu quyền cho giai đoạn đồng bộ lại hoặc khác biệt đường khởi tạo |

## 14. Kết quả đánh giá cần bàn giao

Một đánh giá có thể dùng để quyết định triển khai nên chứa:

- Danh sách tiến trình và danh tính thực tế của từng tiến trình.
- Tính năng Spring Cloud Kubernetes bật/tắt và phiên bản liên quan.
- Ma trận tài nguyên, API group, động từ, namespace và tên giới hạn.
- Role/Binding được chọn cùng lý do giữ từng nhóm quyền.
- Các quyền nhạy cảm đã xác nhận không cần, như Secret, exec, log hoặc sửa workload.
- Bằng chứng cho phép/từ chối và hành vi ở các giai đoạn khởi tạo, theo dõi, phục hồi.
- Các giả định chưa kiểm chứng và phạm vi cần đánh giá lại khi bật tính năng mới.

Mỗi lần thêm starter, đổi loại client, chuyển Endpoints sang EndpointSlice, bật Secret monitoring hoặc leader election đều có thể thay đổi hồ sơ quyền. Đánh giá lại theo đường gọi phát sinh, thay vì tái sử dụng một Role rộng cho mọi thành phần.
