# Không tìm thấy namespace hoặc tên tài nguyên mong đợi

## 1. Mục tiêu và tình huống

Trong chương **Chẩn đoán sự cố** của module **SPRING_CLOUD_KUBERNETES**, bài này hướng dẫn xử lý tình huống ứng dụng không tìm được namespace, ConfigMap, Secret hoặc Service mà người vận hành cho rằng đã tồn tại.

Sau bài học, bạn có thể:

- Xác định ứng dụng thực sự đang tìm loại tài nguyên nào, tên gì và trong namespace nào.
- Phân biệt sai phạm vi truy vấn với thiếu quyền, lỗi DNS và thiếu endpoint.
- Kiểm tra quy tắc chọn namespace, tên nguồn cấu hình và service ID.
- Sửa đúng cấu hình của ứng dụng, DiscoveryServer hoặc Configuration Watcher.
- Xác minh kết quả bằng danh tính và đường truy cập thực tế của thành phần lỗi.

Ví dụ xuyên suốt:

| Thành phần | Vị trí/tên thực tế |
| --- | --- |
| Deployment ứng dụng | `apps-lab/orders-api` |
| `spring.application.name` | `orders-api` |
| Service của ứng dụng | `apps-lab/orders-service` |
| Service phụ thuộc | `apps-lab/inventory` |
| ConfigMap ứng dụng cần | `config-lab/orders-settings` |
| Configuration Watcher nếu dùng | Chạy trong `ops-lab` |

Tên ứng dụng, Deployment, Service và ConfigMap trong ví dụ cố ý khác nhau. Mỗi tên có vai trò riêng; không giả định chúng tự ánh xạ sang nhau.

Các lệnh dưới đây dành cho môi trường lab đã chuẩn bị. Tài liệu tham chiếu Spring Cloud Kubernetes nhánh 5.1; với dự án nhánh khác, kiểm tra đúng dependency, loại client và cơ chế nạp cấu hình trước khi áp dụng tên thuộc tính.

## 2. Biến thông báo “không tìm thấy” thành một câu hỏi cụ thể

### 2.1. Ghi đủ địa chỉ của lần tìm kiếm

Thay vì ghi “không thấy orders”, hãy ghi:

~~~text
Thành phần gửi request: ConfigMap PropertySource của orders-api
Đích Kubernetes: cluster lab-a
API group/tài nguyên: core/configmaps
Namespace được truy vấn: apps-lab
Tên được tìm: orders-api
Danh tính: system:serviceaccount:apps-lab:orders-api
Kết quả: không chọn được nguồn mong đợi

Đối tượng người vận hành muốn dùng:
cluster lab-a / config-lab / ConfigMap / orders-settings
~~~

Hai địa chỉ trên khác cả namespace lẫn tên. Tạo thêm một ConfigMap tên `orders-api` trong `apps-lab` có thể làm lỗi tạm biến mất nhưng chưa chắc phù hợp thiết kế ban đầu.

Với một request API, cần xác định tối thiểu:

~~~text
cluster + API group/resource + namespace + name/selector + verb + identity
~~~

Với lời gọi discovery, bổ sung service ID, phạm vi namespace của discovery, bộ lọc Service và trạng thái đồng bộ. Với DNS, ghi hostname thực sự được resolver nhận và namespace của Pod gọi.

### 2.2. Phân loại kết quả trước khi thay đổi cấu hình

| Dấu hiệu | Chưa thể kết luận | Hướng kiểm tra đầu tiên |
| --- | --- | --- |
| Không phân giải được namespace lúc khởi động | Namespace `default` là lựa chọn đúng | Nguồn xác định namespace và cấu hình sớm |
| API trả `404 NotFound` | Toàn cluster không có đối tượng đó | Đúng cluster, loại tài nguyên, namespace và tên chưa |
| API trả `403 Forbidden` | Namespace hoặc tài nguyên không tồn tại | Danh tính, động từ và phạm vi quyền |
| API trả `401 Unauthorized` | Sai tên ConfigMap | Credential được gửi và được chấp nhận chưa |
| LIST thành công nhưng rỗng | Tài nguyên không tồn tại ở mọi nơi | Namespace, label/field selector và dữ liệu trong phạm vi đó |
| Discovery trả không có instance | Không có Service | Tên Service, endpoint, readiness, filter và đồng bộ |
| DNS trả NXDOMAIN/không phân giải được | ServiceAccount thiếu quyền GET Service | Hostname, DNS search path và hệ thống DNS |
| Timeout hoặc lỗi TLS | Tên namespace sai | Đường mạng, API endpoint, CA và credential tương ứng |

Đọc lỗi gốc và thành phần trả phản hồi. Một HTTP 404 từ Ingress hoặc ứng dụng không phải bằng chứng Kubernetes API trả NotFound.

Không biến mọi ngoại lệ thành danh sách rỗng rồi chẩn đoán như “không có Service”. Cách xử lý đó làm mất khác biệt giữa lỗi quyền, lỗi kết nối và kết quả truy vấn hợp lệ.

## 3. Kiểm tra cluster, namespace và danh tính của người quan sát

### 3.1. Kubectl và ứng dụng có thể đang nhìn hai nơi khác nhau

~~~powershell
kubectl config current-context
kubectl config view --minify -o jsonpath='{.contexts[0].context.namespace}'
~~~

Namespace rỗng trong context của kubectl thường dẫn tới việc kubectl dùng namespace mặc định cho request namespaced không có `-n`. Điều đó không xác định namespace mà Spring Cloud Kubernetes trong Pod đã chọn.

Trong các bước điều tra, ghi rõ namespace:

~~~powershell
kubectl -n apps-lab get deployment orders-api
kubectl -n apps-lab get service inventory -o name
kubectl -n config-lab get configmap orders-settings -o name
~~~

Nếu cần chọn context khác, dùng context đã xác minh cho đúng môi trường. Không sửa tài nguyên chỉ vì kết quả ở một context không khớp dự kiến.

Namespace phân chia phạm vi tên của nhiều tài nguyên. Cùng tên ConfigMap có thể tồn tại ở nhiều namespace và là những đối tượng khác nhau. Xem [Namespaces](https://kubernetes.io/docs/concepts/overview/working-with-objects/namespaces/).

### 3.2. Namespace của Pod không phải namespace mặc định của mọi tính năng

Lấy một Pod thuộc đúng Deployment:

~~~powershell
kubectl -n apps-lab get pods -l app=orders-api -o custom-columns=NAME:.metadata.name,UID:.metadata.uid,SA:.spec.serviceAccountName
~~~

Label chỉ giúp tìm ban đầu; kiểm tra owner reference nếu có khả năng nhiều workload cùng dùng label.

Có ít nhất bốn phạm vi cần tách:

- Namespace nơi Pod ứng dụng chạy.
- Namespace nơi nguồn ConfigMap/Secret được đặt.
- Namespace mà discovery được cấu hình tìm.
- Namespace mà Watcher được cấu hình theo dõi.

Trong ví dụ, Pod chạy ở `apps-lab` nhưng ConfigMap nằm ở `config-lab`. Hai điều này không mâu thuẫn nếu đường API và RBAC cho phép. Tuy nhiên, mount ConfigMap/Secret bằng tham chiếu volume thông thường phải trỏ nguồn trong namespace của Pod; không thêm trường namespace tùy ý vào nguồn volume để mount xuyên namespace.

### 3.3. Khi cần kiểm tra Namespace object

Người vận hành có quyền tương ứng có thể kiểm tra:

~~~powershell
kubectl get namespace apps-lab
kubectl get namespace config-lab
~~~

Nếu lệnh bị Forbidden, chưa có bằng chứng namespace không tồn tại. Nhờ kênh quản trị có quyền xác minh đối tượng trong đúng cluster.

Ứng dụng đọc ConfigMap trong một namespace không mặc nhiên cần quyền liệt kê mọi Namespace object. Không cấp `list namespaces` hoặc quyền đọc toàn cluster chỉ để chữa một lỗi chọn sai namespace.

Cũng không dùng `kubectl get all` làm bằng chứng đã kiểm tra mọi loại tài nguyên; cần hỏi đúng `configmaps`, `secrets`, `services` hoặc tài nguyên liên quan.

## 4. Namespace được Spring Cloud Kubernetes chọn từ đâu?

### 4.1. Ưu tiên cấu hình cụ thể cho nguồn khi thiết kế yêu cầu

Với ConfigMap/Secret, namespace có thể được chỉ định ở cấu hình nguồn. Khi không có namespace cụ thể, tài liệu mô tả chuỗi tìm gồm:

1. `spring.cloud.kubernetes.client.namespace`.
2. Tệp được cấu hình bằng `spring.cloud.kubernetes.client.serviceAccountNamespacePath`.
3. Tệp chuẩn `/var/run/secrets/kubernetes.io/serviceaccount/namespace`.
4. Cơ chế lấy namespace của client nền nếu client hỗ trợ.

Không xác định được namespace có thể dẫn tới exception; không giả định Spring Cloud Kubernetes luôn tự chọn `default`. Xem [Namespace resolution](https://docs.spring.io/spring-cloud-kubernetes/reference/property-source-config/namespace-resolution.html).

Với dự án cụ thể, ghi cả cấu hình cấp tính năng và cấp từng source. Một `sources[].namespace` cũ có thể vẫn điều hướng việc đọc dù người vận hành vừa sửa namespace mặc định của client.

### 4.2. Kiểm tra giá trị có hiệu lực, không chỉ tệp trong repository

Các nguồn có thể làm giá trị khác với dự định:

| Nguồn | Ví dụ sai lệch |
| --- | --- |
| Env của container | Còn `SPRING_CLOUD_KUBERNETES_CLIENT_NAMESPACE=old-lab` |
| System property/command line | Ghi đè cấu hình đóng gói trong image |
| Profile | Một file profile chọn namespace khác |
| Danh sách sources | Một phần tử vẫn ghi namespace cũ |
| Client nền | Kubeconfig hoặc cơ chế riêng của Fabric8 |
| Template đã render | Pipeline thêm prefix hoặc giá trị môi trường khác |
| Pod cũ | Chưa được thay sau khi sửa env/template |

Spring Boot có quy tắc precedence giữa các nguồn cấu hình. Cần đối chiếu giá trị thực sự được nạp và đúng giai đoạn, không chỉ nhìn một file YAML. Xem [Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html).

Không coi các biến sau là tương đương:

- `POD_NAMESPACE` chỉ là tên biến do bạn đặt; không tự cấu hình mọi client.
- `KUBERNETES_NAMESPACE` có thể được client nền hỗ trợ, nhưng không phải quy ước chung cho mọi implementation.
- `SPRING_CLOUD_KUBERNETES_CLIENT_NAMESPACE` ánh xạ vào thuộc tính Spring tương ứng.
- `KUBERNETES_SERVICE_HOST` chỉ ra đích API theo cơ chế môi trường, không phải namespace ứng dụng.

### 4.3. Cấp namespace Pod bằng Downward API

Nếu mục tiêu là dùng namespace của Pod làm namespace client, có thể cung cấp trực tiếp:

~~~yaml
env:
  - name: POD_NAMESPACE
    valueFrom:
      fieldRef:
        fieldPath: metadata.namespace
  - name: SPRING_CLOUD_KUBERNETES_CLIENT_NAMESPACE
    valueFrom:
      fieldRef:
        fieldPath: metadata.namespace
~~~

Đây là phần ghép vào container đã có. Downward API cung cấp metadata namespace mà ứng dụng không cần gọi API để liệt kê namespace. Xem [Downward API](https://kubernetes.io/docs/concepts/workloads/pods/downward-api/).

Cấu hình này không cấp credential hoặc RBAC. Khi tắt tự mount token, một tệp namespace thường có thể không được cung cấp theo đường mặc định; cấp namespace qua env chỉ giải quyết việc chọn phạm vi, không làm API client tự xác thực được.

### 4.4. Tránh vòng phụ thuộc lúc khởi động

Không đặt thông tin duy nhất giúp tìm ConfigMap vào chính ConfigMap chưa thể tìm.

Ví dụ cấu hình namespace chỉ nằm trong `orders-settings`, nhưng ứng dụng cần biết namespace trước để nạp nguồn đó. Nếu không có một nguồn sớm khác, thiết kế tạo vòng phụ thuộc.

Đặt thông tin định vị cần thiết trong nguồn có sẵn trước lần đọc: cấu hình đóng gói, env, tham số khởi động hoặc cơ chế client đã xác định. Với lỗi xảy ra trong giai đoạn import/bootstrap, một endpoint chỉ tồn tại sau khi ứng dụng khởi động không giúp chứng minh bước import đã chọn gì; cần log và cấu hình của đúng giai đoạn.

## 5. Kiểm tra tên ConfigMap, Secret và các nguồn phụ

### 5.1. Phân biệt tên tài nguyên với khóa dữ liệu

~~~yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: orders-settings
  namespace: config-lab
data:
  application.yaml: |-
    orders:
      display:
        revision: "display-v1"
~~~

Trong ví dụ:

| Giá trị | Ý nghĩa |
| --- | --- |
| `orders-settings` | `metadata.name` của ConfigMap |
| `config-lab` | Namespace của ConfigMap |
| `application.yaml` | Khóa trong `data`, chứa tài liệu cấu hình |
| `orders.display.revision` | Thuộc tính Spring sau khi nội dung được xử lý |

`kubectl get configmap application.yaml` đang tìm một tài nguyên khác, không tìm khóa bên trong `orders-settings`.

Tương tự, tên Secret và tên key `password` bên trong Secret là hai thành phần khác nhau. Có Secret đúng tên nhưng thiếu key được tham chiếu là một lỗi khác với không có Secret.

### 5.2. Quy tắc mặc định có thể tìm tên khác điều bạn nghĩ

Tài liệu ConfigMap PropertySource mô tả tên nguồn dựa vào `spring.cloud.kubernetes.config.name`, tên ứng dụng hoặc `application` theo cấu hình. `sources` cho phép chỉ định nhiều nguồn và namespace. Xem [ConfigMap PropertySource](https://docs.spring.io/spring-cloud-kubernetes/reference/property-source-config/configmap-propertysource.html).

Với ví dụ của bài, nếu không chỉ định nguồn mà tên ứng dụng là `orders-api`, không nên kỳ vọng thư viện tự suy ra ConfigMap `orders-settings` trong namespace khác.

Cấu hình định vị tường minh cho đường Config Data qua API, với starter tương thích đã có:

~~~yaml
spring:
  application:
    name: orders-api
  config:
    import: "kubernetes:"
  cloud:
    kubernetes:
      config:
        enabled: true
        include-profile-specific-sources: false
        sources:
          - name: orders-settings
            namespace: config-lab
      secrets:
        enabled: false
~~~

Mẫu chỉ nạp ConfigMap cho mục tiêu chẩn đoán, không bật đọc Secret ngoài nhu cầu. `kubernetes:` cần dependency và cơ chế import đúng phiên bản; chỉ thêm chuỗi đó không cài đặt một Kubernetes client. Xem [Kubernetes PropertySource implementations](https://docs.spring.io/spring-cloud-kubernetes/reference/property-source-config.html).

Đặt thông tin định vị trên ở nguồn sớm như phần 4.4. Nếu có source khác đang cấu hình ở env hoặc profile, phải kiểm tra cả danh sách thực tế được bind.

### 5.3. Profile có thể phát sinh tên nguồn phụ

Với nguồn có tên và profile `dev`, cấu hình có thể thử tìm thêm nguồn như `orders-settings-dev`. Thông báo thiếu nguồn phụ chưa đủ chứng minh ConfigMap gốc không tồn tại.

Xác định:

- Tên chính xác được thử tìm.
- Profile thực sự đang active.
- Nguồn nào bắt buộc theo hợp đồng khởi động.
- Lỗi đó có làm dừng khởi động hay chỉ phản ánh một lần tìm nguồn phụ.
- Cấu hình `include-profile-specific-sources` có phù hợp phiên bản/cách chọn nguồn không.

Ví dụ trên tắt tìm nguồn theo profile để giảm biến số trong lab. Không tắt cơ chế này trên hệ thống đang dùng nguồn profile như một phần thiết kế chỉ để làm log im lặng.

`fail-fast: false`, import tùy chọn hoặc retry không sửa tên/namespace sai. Ứng dụng khởi động được bằng mặc định cũng chưa chứng minh đã nạp nguồn mong muốn.

### 5.4. Tên sau render và tên ghi trong mã có thể khác nhau

Công cụ đóng gói có thể tạo prefix, suffix hoặc tên gắn hash, chẳng hạn:

~~~text
Dự định trong cấu hình ứng dụng: orders-settings
Đối tượng sau render: lab-orders-settings-7m4d2
~~~

Kiểm tra manifest đã render và tham chiếu thực tế. Không xóa hash hoặc tạo thêm tài nguyên tên ngắn khi chưa hiểu quy trình phát hành.

Các tham chiếu trong PodSpec có thể được công cụ biến đổi, trong khi một chuỗi tên nằm bên trong cấu hình ứng dụng chưa chắc được biến đổi theo. Đối chiếu cả hai nơi.

Nếu được phép tìm trong các namespace dự kiến, chỉ lấy metadata cần thiết:

~~~powershell
kubectl -n config-lab get configmaps -o custom-columns=NAME:.metadata.name,NAMESPACE:.metadata.namespace,UID:.metadata.uid
~~~

Danh sách trả về phụ thuộc quyền và phạm vi của người chạy. Đối với Secret, quyền đọc/liệt kê có thể cho phép nhận nội dung bí mật dù chỉ định dạng hiển thị metadata; không cấp quyền này chỉ để thuận tiện tìm tên. Secrets PropertySource cũng cần được đánh giá đường mount/API và trạng thái bật riêng. Xem [Secrets PropertySource](https://docs.spring.io/spring-cloud-kubernetes/reference/property-source-config/secrets-propertysource.html).

## 6. Xác minh quyền bằng đúng danh tính ứng dụng

### 6.1. “Kubectl của tôi đọc được” chưa đủ

Người vận hành có thể đọc `config-lab/orders-settings` nhưng ứng dụng dùng ServiceAccount `apps-lab/orders-api` lại bị từ chối.

Với tài khoản vận hành được phép impersonate danh tính và các nhóm tương ứng:

~~~powershell
$appIdentity = @(
  '--as=system:serviceaccount:apps-lab:orders-api'
  '--as-group=system:serviceaccounts'
  '--as-group=system:serviceaccounts:apps-lab'
  '--as-group=system:authenticated'
)

kubectl auth can-i get configmaps/orders-settings -n config-lab @appIdentity
kubectl auth can-i list configmaps -n config-lab @appIdentity
kubectl auth can-i watch configmaps -n config-lab @appIdentity
kubectl -n config-lab get configmap orders-settings -o name @appIdentity
~~~

`can-i` kiểm tra khả năng được phép làm một thao tác, không kiểm tra tài nguyên tồn tại. GET cuối kiểm tra một request đọc cụ thể; nó vẫn chưa chứng minh client dùng LIST/WATCH có đủ quyền cho vòng đời của nó. Xem [kubectl auth can-i](https://kubernetes.io/docs/reference/kubectl/generated/kubectl_auth/kubectl_auth_can-i/).

Nếu bị từ chối impersonation, đó là lỗi của kênh kiểm tra, chưa phải phản hồi theo quyền ứng dụng đích. Không cấp quyền impersonate cho runtime chỉ để chạy các lệnh này.

Kết quả chỉ đại diện cho danh tính đã chọn. Nếu Kubernetes client dùng credential khác do kubeconfig, env hoặc cấu hình tùy biến, cần xác định danh tính thật từ cấu hình và kênh audit phù hợp.

### 6.2. GET, LIST và WATCH có thể khác nhau

Một Role cho GET `orders-settings` không tự cho LIST mọi ConfigMap trong namespace. Client đọc theo batch hoặc informer có thể phát sinh request khác với một lệnh GET thử tay.

Khi dùng `resourceNames`, LIST/WATCH cần request tương thích với giới hạn tên và field selector tương ứng. Bộ lọc label trong ứng dụng không tự tạo quyền đọc theo label tại API server. Xem [RBAC](https://kubernetes.io/docs/reference/access-authn-authz/rbac/).

Nếu GET được nhưng ứng dụng vẫn lỗi:

1. Đọc động từ và tài nguyên thật trong lỗi.
2. Kiểm tra client đang dùng chế độ đọc nào.
3. Kiểm tra quyền cho bước khởi tạo, theo dõi và đồng bộ lại.
4. Chọn cơ chế đọc hoặc Role đúng hợp đồng, thay vì cộng quyền toàn cluster.

### 6.3. RoleBinding xuyên namespace phải đặt đúng chỗ

Giả sử Role `orders-config-reader` đã tồn tại trong `config-lab`, có các tài nguyên/động từ phù hợp đường đọc đã kiểm chứng. Binding cho ServiceAccount của ứng dụng phải nằm ở namespace nguồn:

~~~yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: orders-api-config-reader
  namespace: config-lab
subjects:
  - kind: ServiceAccount
    name: orders-api
    namespace: apps-lab
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: Role
  name: orders-config-reader
~~~

Hai trường namespace có nghĩa khác nhau:

- `metadata.namespace: config-lab`: nơi Role và tài nguyên được cấp quyền tồn tại.
- `subjects[].namespace: apps-lab`: nơi ServiceAccount được định danh.

Đặt binding ở `apps-lab` không tự cấp quyền đọc ConfigMap trong `config-lab`. Cũng không cần tạo một ServiceAccount trùng tên ở `config-lab` nếu chủ thể thực tế vẫn là ServiceAccount của Pod trong `apps-lab`.

Không sửa namespace toàn cục của ứng dụng để “đi theo RoleBinding” nếu thiết kế chỉ cần một source ở namespace khác. Sửa đúng phạm vi nguồn và quyền của chủ thể.

## 7. Khi DiscoveryClient hoặc LoadBalancer không tìm được dịch vụ

### 7.1. Service ID thường là tên Service, không phải tên Deployment

Trong ví dụ:

~~~text
Deployment: inventory-api
spring.application.name: inventory-api
Service metadata.name: inventory
~~~

Với đường discovery theo tên Service, việc gọi `getInstances("inventory-api")` không tự ánh xạ sang `inventory`. Tương tự, tên Pod có hậu tố do controller sinh không phải service ID mặc định.

Spring Cloud Kubernetes trả service name theo `Service.metadata.name`; `spring.application.name` không đổi tên đăng ký Kubernetes. Xem [DiscoveryClient for Kubernetes](https://docs.spring.io/spring-cloud-kubernetes/reference/discovery-client.html).

Kiểm tra đối tượng trước:

~~~powershell
kubectl -n apps-lab get service inventory -o custom-columns=NAME:.metadata.name,NAMESPACE:.metadata.namespace,TYPE:.spec.type
kubectl -n apps-lab get service inventory -o jsonpath='{.spec.selector}'
~~~

Nếu ứng dụng dùng một client có LoadBalancer, kiểm tra service ID/hostname mà lớp chọn đích thực sự nhận. Đừng chỉ nhìn tên biến trong code hoặc URL hiển thị ở một trang cấu hình.

### 7.2. Discovery có phạm vi namespace riêng

Cấu hình định hướng khi chỉ cần danh mục `apps-lab`:

~~~yaml
spring:
  cloud:
    kubernetes:
      discovery:
        all-namespaces: false
        namespaces:
          - apps-lab
~~~

Kiểm tra env/profile còn giá trị ghi đè không. Danh sách namespace của discovery khác với `config.sources[].namespace`.

Đặc biệt, đừng đổi `spring.cloud.kubernetes.client.namespace` từ `apps-lab` sang `config-lab` chỉ để tìm ConfigMap rồi vô tình làm một tính năng discovery dùng namespace mặc định tìm sai nơi. Ưu tiên cấu hình đúng cấp khi chỉ một tính năng cần namespace khác.

Với HTTP DiscoveryClient, thành phần đọc Kubernetes có thể là DiscoveryServer. Cần sửa phạm vi trên server tương ứng, không chỉ trên ứng dụng gọi HTTP. Bật namespace trên sai tiến trình không thay đổi request mà server đang gửi.

### 7.3. Service tồn tại nhưng không có instance dùng được

Khi GET Service thành công, chuyển nhánh điều tra:

~~~powershell
kubectl -n apps-lab get endpointslices -l kubernetes.io/service-name=inventory -o wide
kubectl -n apps-lab get pods -l app=inventory -o wide
~~~

Label `app=inventory` ở lệnh Pod chỉ là ví dụ; phải thay bằng selector thực tế của Service.

Cần kiểm tra:

- Service selector có khớp label Pod không.
- Các Pod đích có Ready theo thiết kế không.
- EndpointSlice có địa chỉ và trạng thái phù hợp không.
- Cổng Service, targetPort và quy tắc chọn cổng có đúng không.
- Client dùng Endpoints hay EndpointSlice và có quyền với đúng tài nguyên không.
- Client đã hoàn tất đồng bộ hay còn lỗi nền.

Service và endpoint liên quan là hai lớp khác nhau. Kubernetes có hướng dẫn điều tra selector, endpoint và đường truyền tại [Debug Services](https://kubernetes.io/docs/tasks/debug/debug-application/debug-service/).

Không bật tìm địa chỉ chưa Ready chỉ để che lỗi readiness cho request nghiệp vụ. Nếu cần tính năng đó để giám sát, đánh giá nó như một mục tiêu riêng.

### 7.4. Bộ lọc có thể loại Service đúng tên

Với discovery, phân biệt:

| Cấu hình | Đối tượng được xét |
| --- | --- |
| `discovery.namespaces` | Namespace của tài nguyên trong danh mục |
| `discovery.service-labels` | Label trên đối tượng Service |
| `discovery.filter` | Biểu thức lọc theo implementation hỗ trợ |
| Service `spec.selector` | Label của Pod mà Service chọn |
| Quy tắc readiness | Địa chỉ endpoint được dùng cho mục tiêu tương ứng |

Service có selector `app=inventory` không có nghĩa chính Service cũng có metadata label `app=inventory`. Nếu discovery lọc metadata label đó nhưng Service không mang nó, Service có thể bị loại dù vẫn chọn đúng Pod.

Nếu bật tìm nhiều namespace, các Service cùng tên có thể làm việc diễn giải danh mục khó hơn. Không chỉ nhìn một tên duy nhất trong `getServices()` rồi kết luận đã tìm đúng namespace; đối chiếu dữ liệu instance và phạm vi tìm thực tế.

Cache rỗng, lỗi đồng bộ hoặc lỗi bị lớp bọc nuốt cũng có thể tạo triệu chứng “không có instance”. Ghi nhận exception gốc và tình trạng đồng bộ thay vì tăng retry cho cùng một service ID sai.

### 7.5. Tách lỗi DNS khỏi lỗi discovery

Từ Pod ở `ops-lab`, hostname ngắn `inventory` thường được tìm trong namespace của Pod gọi. Nó không tự trở thành Service `inventory` ở `apps-lab`.

Để gọi xuyên namespace bằng DNS, dùng tên có namespace hoặc FQDN phù hợp, chẳng hạn:

~~~text
inventory.apps-lab.svc.cluster.local
~~~

`cluster.local` là miền cluster minh họa; kiểm tra miền thực tế của môi trường. Xem [DNS for Services and Pods](https://kubernetes.io/docs/concepts/services-networking/dns-pod-service/).

Nếu dùng HTTP client thông thường gọi DNS, đó là đường phân giải tên của hệ thống DNS. Nếu dùng `@LoadBalanced` hoặc bộ lọc LoadBalancer, hostname có thể được hiểu thành service ID của discovery. Đừng thay service ID bằng FQDN rồi giả định mọi implementation xử lý giống resolver DNS.

Spring Cloud Kubernetes LoadBalancer có các chế độ POD/SERVICE với đường tìm đích tương ứng; SERVICE mode không tự đồng nghĩa với một HTTP client thuần DNS không dùng API. Xem [LoadBalancer for Kubernetes](https://docs.spring.io/spring-cloud-kubernetes/reference/load-balancer.html).

Một Service GET được ở API chưa chứng minh DNS của Pod gọi hoạt động. DNS phân giải được cũng chưa chứng minh endpoint đích đang phục vụ đúng cổng.

## 8. Configuration Watcher: hai phạm vi và một ánh xạ tên

Trong ví dụ, Watcher ở `ops-lab`, ConfigMap ở `config-lab`, Service ứng dụng ở `apps-lab`. Cần kiểm tra riêng:

~~~text
Watcher theo dõi nguồn ở đâu?
  -> config-lab / ConfigMap / orders-settings

Watcher tìm ứng dụng nhận refresh ở đâu?
  -> apps-lab / Service / orders-service

Ứng dụng được thông báo đọc nguồn ở đâu?
  -> config-lab / ConfigMap / orders-settings
~~~

### 8.1. Phạm vi theo dõi không phải phạm vi discovery

Cấu hình env minh họa trên Deployment của **Watcher**:

~~~yaml
env:
  - name: SPRING_CLOUD_KUBERNETES_RELOAD_NAMESPACES_0
    value: "config-lab"
  - name: SPRING_CLOUD_KUBERNETES_DISCOVERY_NAMESPACES_0
    value: "apps-lab"
~~~

Đây là hai phần tử ghép vào cấu hình Watcher đã có; cần dependency/image, RBAC, các bộ lọc và cơ chế thông báo phù hợp phiên bản.

Nếu Watcher chỉ theo dõi namespace nơi chính nó chạy, việc đổi ConfigMap ở `config-lab` có thể không tạo thông báo. Nếu đã thấy sự kiện nhưng discovery chỉ nhìn `config-lab`, nó vẫn có thể không tìm được ứng dụng ở `apps-lab`.

### 8.2. Tên nguồn không nhất thiết là tên ứng dụng đích

Theo cơ chế định tuyến được tài liệu mô tả, khi tên nguồn và tên ứng dụng trong discovery khác nhau, có thể chỉ định ứng dụng đích qua annotation phù hợp. Ví dụ:

~~~yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: orders-settings
  namespace: config-lab
  labels:
    spring.cloud.kubernetes.config: "true"
  annotations:
    spring.cloud.kubernetes.configmap.apps: "orders-service"
data:
  application.yaml: |-
    orders:
      display:
        revision: "display-v1"
~~~

`orders-service` ở đây là tên đích trong discovery của ví dụ, không phải suy từ Deployment `orders-api`. Kiểm tra quy tắc chọn đích và label/annotation được hỗ trợ ở đúng phiên bản. Xem [Configuration Watcher](https://docs.spring.io/spring-cloud-kubernetes/reference/spring-cloud-kubernetes-configuration-watcher.html).

Một annotation đúng tên không tự cấp quyền hoặc bảo đảm HTTP endpoint truy cập được. Nếu có cơ chế chọn đích theo label cùng tồn tại, xem quy tắc ưu tiên thực tế thay vì chỉ nhìn một annotation.

### 8.3. Xác minh từng chủ thể

Watcher cần quyền của ServiceAccount **Watcher** để theo dõi ConfigMap và đọc danh mục đích. Ứng dụng cần quyền/cách mount riêng để đọc lại cấu hình. Hai chủ thể không dùng chung quyền chỉ vì cùng tham gia một lần refresh.

Nếu log đã chuyển từ “không tìm được đích” sang lỗi HTTP 401, 403, 404 hoặc timeout của endpoint quản trị, việc tìm nguồn/đích có thể đã qua được một bước. Chuyển sang nhánh xác thực, đường dẫn, cổng hoặc mạng tương ứng; không tiếp tục đổi namespace một cách ngẫu nhiên.

Cuối cùng vẫn cần xác nhận cấu hình có hiệu lực trên từng replica. “Đã tìm được Service” hoặc “đã gửi refresh” chưa chứng minh mọi bean đã áp dụng nguồn mong muốn.

## 9. Cây quyết định để điều tra

~~~mermaid
flowchart TD
    A["Thông báo không tìm thấy"]
    A --> B{"Đã xác định đúng thành phần, đích và danh tính?"}
    B -->|"Chưa"| C["Ghi cluster, resource, namespace, name/selector, verb"]
    B -->|"Rồi"| D{"Kết quả gốc là gì?"}
    D -->|"401 hoặc TLS/timeout"| E["Kiểm tra credential, CA, đích API và mạng"]
    D -->|"403"| F["Kiểm tra quyền đúng chủ thể và thao tác"]
    D -->|"404 hoặc LIST rỗng"| G["So tên/namespace/selector với nguồn đã render và API"]
    D -->|"Discovery không có instance"| H["Kiểm tra Service ID, phạm vi, filter, endpoint và readiness"]
    D -->|"DNS không phân giải"| I["Kiểm tra hostname, namespace gọi và DNS"]
    G --> J{"Đối tượng đúng tồn tại và đọc được?"}
    J -->|"Không"| K["Sửa nguồn triển khai hoặc tham chiếu theo thiết kế"]
    J -->|"Có"| L["Kiểm tra import, profile, client và giá trị có hiệu lực"]
    H --> M["Đối chiếu dữ liệu ứng dụng với API cùng thời điểm"]
    L --> N["Xác minh chức năng và các replica sau sửa"]
    M --> N
    K --> N
~~~

Cây quyết định là hướng dẫn điều tra, không thay cho việc đọc lỗi chi tiết. Nếu proxy hoặc lớp bọc đã chuyển đổi lỗi, cần truy về thành phần phát sinh kết quả gốc.

### 9.1. Một lượt điều tra tối thiểu

| Bước | Bằng chứng cần lấy | Kết luận được phép |
| --- | --- | --- |
| 1 | Context/đích API và namespace Pod | Đang quan sát môi trường nào |
| 2 | Loại, tên, namespace đối tượng mong muốn | Địa chỉ tài nguyên dự kiến |
| 3 | Cấu hình định vị có hiệu lực của thành phần | Nó thực sự đang tìm ở đâu |
| 4 | Request và lỗi theo danh tính thật | Sai phạm vi, thiếu quyền hay lỗi kết nối |
| 5 | Kết quả GET/LIST phù hợp | Có/không có trong phạm vi đã kiểm tra |
| 6 | Filter, endpoint, readiness nếu dùng discovery | Vì sao chưa có instance dùng được |
| 7 | Hành vi sau áp dụng sửa | Đường truy cập dự kiến đã hoạt động chưa |

Không bỏ bước 3: phần lớn nhầm lẫn trong ví dụ đến từ việc người vận hành kiểm tra đúng tài nguyên nhưng ứng dụng lại tìm tài nguyên khác.

### 9.2. Khi tài nguyên thực sự chưa tồn tại

Sau khi xác nhận đúng cluster, loại, namespace, tên và quyền, có thể phát hiện nguồn triển khai chưa tạo đối tượng cần thiết.

Lúc này kiểm tra:

- Manifest đã render có đối tượng đó không.
- Giai đoạn triển khai tạo namespace/nguồn đã hoàn tất chưa.
- Công cụ phát hành có đổi tên hoặc bỏ nguồn theo điều kiện không.
- Tài nguyên có bị thay thế hoặc dọn bởi controller/quy trình khác không.
- Ứng dụng khởi động trước nguồn bắt buộc hay đang giữ tham chiếu cũ.

Tạo tài nguyên theo nguồn được quản lý và nội dung đã duyệt. Không tạo một Secret rỗng hoặc sao chép dữ liệu môi trường khác chỉ để làm hết lỗi NotFound.

## 10. Bài thực hành: tìm đúng nguồn và đúng dịch vụ

### 10.1. Chuẩn bị lab

Chuẩn bị qua quy trình triển khai lab:

- Namespace `apps-lab`, `config-lab`; thêm `ops-lab` nếu thử Watcher.
- Ứng dụng `orders-api` dùng starter đúng phiên bản, có cơ chế quan sát cấu hình không nhạy cảm.
- ConfigMap `config-lab/orders-settings` như ví dụ.
- Service `apps-lab/inventory` có workload đích và endpoint hợp lệ.
- ServiceAccount ứng dụng có quyền đọc đúng nguồn/danh mục cần dùng.
- Một marker an toàn, chẳng hạn `orders.display.revision=display-v1`, để xác nhận nguồn thực sự được nạp.

Đây là hướng dẫn thực hành; bài viết không tự triển khai hay chạy các phép thử trên cluster của bạn.

### 10.2. Tạo từng tình huống độc lập

| Tình huống | Cách tạo trong lab | Dấu hiệu cần phân biệt |
| --- | --- | --- |
| Namespace chưa được xác định | Bỏ các nguồn namespace được dùng bởi cấu hình thử nghiệm | Lỗi xác định namespace, khác với đối tượng không tồn tại |
| Sai namespace nguồn | Cấu hình tìm ConfigMap ở `apps-lab` | Không tìm ở đúng địa chỉ `config-lab/orders-settings` |
| Sai tên nguồn | Tìm `orders-api` thay vì `orders-settings` | Tên ứng dụng không tự ánh xạ tên ConfigMap |
| Nguồn profile phụ không có | Bật profile và cơ chế tìm nguồn phụ phù hợp | Phân biệt nguồn phụ với nguồn bắt buộc |
| Thiếu quyền | Bỏ một grant cần thiết trong lab được kiểm soát | Forbidden/thiếu quyền, không kết luận nguồn biến mất |
| Sai service ID | Hỏi discovery tên Deployment thay vì `inventory` | API có Service nhưng caller hỏi tên khác |
| Service bị filter | Filter label mà Service không có | Khác với Service selector chọn Pod |
| Không có endpoint sẵn sàng | Đích không Ready hoặc selector sai trong lab | Service tồn tại nhưng không có instance dùng được |
| Watcher sai phạm vi | Chỉ theo dõi namespace của Watcher | Không nhận sự kiện của nguồn ngoài phạm vi |
| Watcher sai tên đích | Dùng tên ConfigMap như service ID khi hai tên khác nhau | Nhận sự kiện nhưng không tìm đúng ứng dụng |

Với mỗi tình huống, giữ nguyên những yếu tố khác và thu bằng chứng trước khi sửa. Nếu tạo nhiều lỗi đồng thời, phải ghi rõ thứ tự xử lý vì lỗi sau có thể chỉ xuất hiện khi lỗi trước đã được giải quyết.

Việc bỏ nguồn namespace trong một lab đang dùng credential/file chuẩn có thể vẫn còn fallback hợp lệ. Muốn thử nhánh “không xác định được namespace”, cần hiểu và kiểm soát tất cả fallback của client thử nghiệm; không giả định bỏ một biến env là đủ.

### 10.3. Sửa đúng cấp và xác minh

Với case chính của bài:

1. Giữ namespace mặc định của client phù hợp với Pod/danh mục cần dùng.
2. Chỉ định `config.sources[].name=orders-settings` và namespace `config-lab`.
3. Xác minh quyền của ServiceAccount ứng dụng đối với request đọc thực tế.
4. Dùng service ID `inventory` và giới hạn discovery ở `apps-lab`.
5. Nếu dùng Watcher, đặt phạm vi nguồn `config-lab`, phạm vi discovery `apps-lab` và ánh xạ đích `orders-service`.
6. Áp dụng thay đổi theo cơ chế hỗ trợ của ứng dụng và phiên bản đang dùng.
7. Kiểm tra marker cấu hình, danh mục instance và request nghiệp vụ trên các replica liên quan.

Thay đổi namespace/name có thể liên quan tới khởi tạo nguồn cấu hình hoặc informer. Không mặc định POST refresh sẽ tái cấu hình mọi client và mọi watch; dùng rollout/restart có kiểm soát khi hợp đồng triển khai yêu cầu.

Sau sửa, thử lại cả quyền không được phép. Tìm đúng nguồn không nên đi cùng việc vô tình mở quyền đọc mọi namespace hoặc mọi Secret.

## 11. Những cách sửa dễ che mất nguyên nhân

| Cách sửa vội | Rủi ro/giới hạn | Hướng thay thế |
| --- | --- | --- |
| Bật `all-namespaces` | Đọc rộng, có thể gặp Service trùng tên | Chốt namespace cần thiết và cấp quyền tương ứng |
| Cấp `cluster-admin` | Che lỗi quyền bằng grant quá lớn | Kiểm tra chủ thể, tài nguyên và động từ |
| Tạo nguồn cùng tên ở `default` | Ứng dụng có thể đọc nhầm cấu hình | Sửa tham chiếu về nguồn được thiết kế |
| Đổi `spring.application.name` để chữa mọi lỗi | Tác động tới nhiều tính năng, vẫn không đổi Service metadata | Chỉ định tên nguồn/service ID đúng cấp |
| Sao chép Secret xuyên môi trường | Có thể dùng sai credential hoặc lộ bí mật | Cấp nguồn phù hợp qua quy trình bảo mật |
| Tăng retry | Lặp lại cùng request sai | Sửa đích, tên hoặc phạm vi trước |
| Tắt fail-fast/đánh dấu optional | Có thể chạy bằng mặc định không mong muốn | Phân loại nguồn bắt buộc và xác minh cấu hình có hiệu lực |
| Bật địa chỉ chưa Ready | Có thể gửi việc tới Pod chưa phục vụ được | Sửa readiness/selector hoặc dùng mục tiêu giám sát riêng |
| Restart liên tục | Không sửa tên sai, làm mất dấu vết ban đầu | Ghi lỗi và địa chỉ tìm kiếm trước khi đổi |

Chỉ tạo hoặc đổi namespace/tên khi đó là thay đổi thiết kế được quản lý. Namespace, tên tài nguyên và RBAC là một phần hợp đồng triển khai, không phải các biến thử ngẫu nhiên cho tới khi log hết lỗi.

## 12. Bằng chứng để kết thúc sự cố

Hồ sơ kết thúc nên ghi:

~~~text
Thành phần phát sinh lỗi:
Phiên bản và loại client:
Cluster/API endpoint:
Pod name/UID và ServiceAccount:
Loại tài nguyên, API group:
Namespace/name hoặc selector trước khi sửa:
Địa chỉ nguồn/đích đúng theo thiết kế:
Kết quả gốc và thao tác bị lỗi:
Nguyên nhân xác định:
Thay đổi đã áp dụng:
Bằng chứng đọc/tìm được bằng đúng danh tính:
Bằng chứng cấu hình/instance/hành vi thực tế:
Replica và phạm vi đã kiểm tra:
Giới hạn còn lại hoặc bước theo dõi:
~~~

Không đưa token, nội dung Secret hoặc toàn bộ Environment vào hồ sơ này.

Chỉ kết luận sự cố đã được xử lý khi thành phần lỗi tìm đúng đối tượng trong đúng phạm vi, thực hiện được thao tác được phép và chức năng liên quan hoạt động theo thiết kế. Một lệnh kubectl thành công bằng tài khoản khác hoặc việc không còn log cảnh báo chưa đủ thay thế các bằng chứng đó.
