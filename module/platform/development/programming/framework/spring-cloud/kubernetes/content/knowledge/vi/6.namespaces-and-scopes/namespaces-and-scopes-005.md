# Đọc ConfigMap hoặc Secret từ namespace được chỉ định

## 1. Namespace ảnh hưởng đến việc đọc cấu hình

ConfigMap và Secret là resource namespaced. Cùng một tên resource có thể tồn tại ở nhiều namespace và chứa dữ liệu khác nhau. Vì vậy, ứng dụng Spring Cloud Kubernetes phải biết:

- resource nằm ở namespace nào;
- resource tên gì;
- dữ liệu được đưa vào bằng environment, volume hay Kubernetes API;
- ServiceAccount đang thuộc namespace nào;
- RoleBinding cấp quyền ở namespace nào;
- ứng dụng có được phép đọc khác namespace hay không.

ConfigMap checkout-settings trong shop khác ConfigMap checkout-settings trong staging. Đọc nhầm namespace có thể trả 404, đọc dữ liệu sai hoặc trả 403 do thiếu RBAC.

Namespace là một phần của scope API, không phải tiền tố tùy ý gắn vào tên. Một object namespaced được xác định bởi cặp namespace và name.

## 2. Ba cách đưa cấu hình vào Pod

### 2.1. Environment hoặc volume

Kubernetes có thể đưa dữ liệu vào Pod mà ứng dụng không trực tiếp gọi Kubernetes API:

~~~yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: checkout-settings
  namespace: shop
data:
  ORDERS_BASE_URL: http://orders:8080
  CHECKOUT_TIMEOUT_MS: "800"
---
apiVersion: v1
kind: Secret
metadata:
  name: checkout-credentials
  namespace: shop
type: Opaque
stringData:
  api-token: replace-me
~~~

Tham chiếu trong Deployment:

~~~yaml
spec:
  template:
    spec:
      containers:
        - name: checkout
          image: registry.example.com/checkout:1.0.0
          envFrom:
            - configMapRef:
                name: checkout-settings
          env:
            - name: ORDERS_API_TOKEN
              valueFrom:
                secretKeyRef:
                  name: checkout-credentials
                  key: api-token
~~~

Trong mô hình này, ứng dụng không cần quyền get ConfigMap chỉ để đọc environment đã được inject. Environment của process không tự đổi khi ConfigMap thay đổi. Muốn giá trị mới có hiệu lực, thường cần rollout hoặc cơ chế nạp lại.

Volume có behavior cập nhật khác, nhưng ứng dụng vẫn phải đọc lại file và xử lý việc thay đổi dữ liệu.

### 2.2. Đọc trực tiếp bằng integration

Spring Cloud Kubernetes Config hoặc Kubernetes client có thể đọc ConfigMap và Secret qua API server. Khi đó Pod cần:

- endpoint API và CA;
- ServiceAccount phù hợp;
- Role hoặc ClusterRole;
- Binding đúng namespace;
- timeout, retry và fallback;
- chính sách bảo vệ dữ liệu Secret.

Đọc trực tiếp không tự làm cấu hình runtime an toàn hơn. Nó chỉ đưa thêm một đường gọi Kubernetes API vào ứng dụng.

### 2.3. Theo dõi thay đổi

Nếu cần nhận thay đổi khi resource sửa, integration có thể dùng list và watch. Cần thiết kế resource, namespace, validation, refresh, giá trị cũ, reconnect và rollback.

Không phải ứng dụng nào cũng cần watch. Rollout có kiểm soát thường đơn giản hơn nếu cấu hình thay đổi không thường xuyên.

## 3. Namespace của Pod và namespace của resource

Nếu checkout chạy ở shop và đọc ConfigMap trong shop, Role namespaced là lựa chọn dễ giới hạn:

~~~text
Pod checkout
namespace: shop
ServiceAccount: checkout
        |
        | Kubernetes API request
        v
ConfigMap checkout-settings
namespace: shop
~~~

Nếu Pod ở app còn ConfigMap ở config:

~~~text
Pod checkout
namespace: app
ServiceAccount: checkout
        |
        | request đến namespace config
        v
ConfigMap checkout-settings
namespace: config
~~~

ServiceAccount vẫn thuộc app, nhưng quyền phải được bind trong namespace config. Pod chạy ở app không tự có quyền đọc resource ở config.

## 4. Cấu hình namespace trong Spring Cloud Kubernetes

Tên property và starter phụ thuộc phiên bản dependency. Ở mức kiến trúc, ứng dụng cần biết namespace và resource name:

~~~yaml
spring:
  application:
    name: checkout
  cloud:
    kubernetes:
      config:
        enabled: true
        namespace: shop
        name: checkout-settings
~~~

Đây là cấu hình minh họa. Phải đối chiếu key thật với phiên bản đang dùng. Một integration có thể lấy namespace từ file ServiceAccount, một integration khác cho phép chỉ rõ namespace hoặc danh sách namespace.

Cấu hình nên ghi rõ:

- namespace cố định hay lấy từ môi trường;
- resource name;
- key được đọc;
- thứ tự ưu tiên khi có nhiều nguồn;
- behavior khi resource không tồn tại;
- behavior khi API gián đoạn;
- startup hay runtime reload.

Không nên giả định property cùng tên có behavior giống nhau giữa các phiên bản.

## 5. Cùng namespace và khác namespace

Có ba cách chọn namespace:

1. **Namespace của Pod**: đọc resource cùng namespace workload.
2. **Namespace chỉ định**: đọc từ một namespace cấu hình rõ.
3. **Nhiều namespace**: đọc theo danh sách và quy tắc merge.

| Cách chọn | Ưu điểm | Rủi ro |
| --- | --- | --- |
| Cùng namespace | RBAC đơn giản, scope nhỏ | Resource phải được quản lý cùng workload |
| Chỉ rõ namespace | Dễ mô hình hóa kho cấu hình | Cần quyền cross-namespace |
| Nhiều namespace | Linh hoạt cho shared config | Dễ trùng tên, merge khó hiểu, quyền rộng |

Nếu một namespace rõ ràng đáp ứng yêu cầu, tránh đọc nhiều namespace. Cross-namespace config làm tăng coupling giữa team triển khai và team sở hữu dữ liệu.

## 6. RBAC đọc ConfigMap cùng namespace

Giả sử checkout chạy ở shop và chỉ đọc một ConfigMap:

~~~yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: checkout
  namespace: shop
---
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
---
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

Rule giới hạn resource, tên, verb và namespace. Nếu integration cần list hoặc watch để hoạt động, phải bổ sung đúng verb; không thêm quyền theo thói quen.

## 7. RBAC đọc khác namespace

Giả sử Pod checkout chạy ở app nhưng ConfigMap thuộc config. Role và RoleBinding nằm ở namespace config:

~~~yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: checkout-shared-config-reader
  namespace: config
rules:
  - apiGroups: [""]
    resources: ["configmaps"]
    resourceNames: ["checkout-settings"]
    verbs: ["get"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: checkout-shared-config-reader
  namespace: config
subjects:
  - kind: ServiceAccount
    name: checkout
    namespace: app
roleRef:
  kind: Role
  name: checkout-shared-config-reader
  apiGroup: rbac.authorization.k8s.io
~~~

Điểm quan trọng:

- Role bảo vệ resource trong config.
- RoleBinding cũng nằm trong config.
- Subject ServiceAccount thuộc app.
- Pod vẫn chạy bằng ServiceAccount checkout ở app.
- Không cần ClusterRoleBinding nếu chỉ đọc resource ở config.

Sai namespace trong RoleBinding là nguyên nhân phổ biến của 403. ServiceAccount cùng tên ở hai namespace vẫn là hai identity khác nhau.

## 8. Đọc Secret khác ConfigMap

Secret cũng namespaced nhưng dữ liệu nhạy cảm hơn:

~~~yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: checkout-secret-reader
  namespace: shop
rules:
  - apiGroups: [""]
    resources: ["secrets"]
    resourceNames: ["checkout-credentials"]
    verbs: ["get"]
~~~

Chỉ cấp quyền Secret nếu integration thật sự cần đọc Secret qua API. Nếu Secret được inject bằng secretKeyRef, ứng dụng không nhất thiết cần quyền get Secret.

Không:

- đọc toàn bộ Secret trong namespace để tìm key;
- log Secret value;
- expose Secret qua actuator;
- cấp ClusterRole để đọc Secret namespaced;
- gom credential của nhiều workload vào một Secret chung.

Quyền get một Secret thường cho phép đọc toàn bộ dữ liệu của object. Tách Secret theo workload hoặc mục đích giúp giảm phạm vi lộ dữ liệu.

## 9. ServiceAccount và namespace mặc định

Pod nên gán ServiceAccount rõ ràng:

~~~yaml
spec:
  serviceAccountName: checkout
  containers:
    - name: checkout
      image: registry.example.com/checkout:1.0.0
~~~

Nếu không chỉ rõ, Pod có thể dùng ServiceAccount default. Ở môi trường dev, quyền mặc định có thể làm ứng dụng “tự chạy”; sang production với RBAC chặt hơn, ứng dụng trả 403.

Nếu ứng dụng chỉ gọi Service bằng DNS, có thể cân nhắc tắt automount token để giảm credential không cần thiết:

~~~yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: orders
  namespace: shop
automountServiceAccountToken: false
~~~

Không tắt nếu Spring Cloud Kubernetes integration cần gọi API. Nếu Pod có sidecar cần token, phải đánh giá toàn bộ thiết kế Pod.

## 10. Network, authentication và authorization

Đọc ConfigMap khác namespace cần ba lớp:

| Lớp | Câu hỏi |
| --- | --- |
| Mạng | Pod có kết nối được kube-apiserver không? |
| Authentication | Token có xác định đúng ServiceAccount không? |
| Authorization | RoleBinding có cho phép resource, verb và namespace không? |

Phân loại lỗi:

- timeout hoặc connection refused: endpoint, route, NetworkPolicy hoặc API server;
- lỗi TLS: CA và endpoint;
- 401: token, expiration, audience hoặc authentication;
- 403: Role, Binding, subject, verb và namespace;
- 404: resource name, namespace, API path hoặc lifecycle.

Không cấp thêm quyền khi lỗi là NetworkPolicy. Không đổi namespace khi token hết hạn. Chẩn đoán theo lớp trước khi sửa manifest.

## 11. Resource name và key name

Cần tách:

- tên resource: checkout-settings;
- tên key bên trong data: ORDERS_BASE_URL hoặc timeout-ms.

RBAC resourceNames giới hạn object name, không giới hạn từng key bên trong ConfigMap. Nếu một Pod có quyền get ConfigMap, response thường chứa toàn bộ data của object.

Không gom dữ liệu nhạy cảm và không nhạy cảm vào cùng ConfigMap hoặc Secret chỉ để tiện. Nếu ứng dụng chỉ cần một key, xem xét tách resource hoặc dùng env/volume với manifest kiểm soát.

## 12. Kiểm tra quyền theo namespace

Người vận hành có thể kiểm tra ServiceAccount của Pod:

~~~bash
kubectl -n app get pod -l app=checkout -o jsonpath="{.items[0].spec.serviceAccountName}"
~~~

Kiểm tra authorization ở namespace đích:

~~~bash
kubectl auth can-i get configmaps/checkout-settings \
  --as=system:serviceaccount:app:checkout -n config

kubectl auth can-i get secrets/checkout-credentials \
  --as=system:serviceaccount:app:checkout -n config
~~~

Kết quả no có thể là đúng theo nguyên tắc tối thiểu. auth can-i chỉ kiểm tra authorization; nó không chứng minh Pod có network access, token còn hạn hoặc Spring integration dùng đúng namespace.

Không cấp quyền list Secret chỉ để thử RBAC.

## 13. Startup, reload và watcher

### Đọc lúc startup

Nếu ConfigMap bắt buộc để tạo bean, fail startup khi resource thiếu có thể an toàn hơn chạy với giá trị mặc định sai. Cần timeout và backoff để tránh restart loop.

### Đọc runtime

Nếu ứng dụng có thể chạy bằng cache, có thể giữ process và dùng giá trị cũ trong khoảng thời gian giới hạn. Không dùng dữ liệu stale vô hạn.

### Watch runtime

Watcher cần list/get/watch tùy implementation, reconnect, resync và validation. Khi ConfigMap đổi, ứng dụng phải xác định bean nào refresh và request đang chạy dùng giá trị cũ hay mới.

Policy minh họa:

~~~text
ConfigMap thiếu lúc startup:
  fail startup vì cấu hình bắt buộc.
ConfigMap tạm thời không đọc được khi runtime:
  giữ giá trị cũ trong thời hạn cho phép.
ConfigMap mới không hợp lệ:
  không áp dụng và ghi metric.
Watcher mất kết nối:
  reconnect với backoff, sau đó resync.
~~~

## 14. Khi resource hoặc namespace thay đổi

Namespace là ranh giới lifecycle. Khi namespace bị xóa, các resource namespaced có thể bị xóa theo. Ứng dụng đọc cross-namespace phải có behavior khi namespace đích không tồn tại.

Các thay đổi cần xét:

- ConfigMap bị rename;
- Secret bị rotate;
- resource bị xóa trong rollout;
- namespace được tạo lại;
- RoleBinding thay đổi;
- resource version cũ không còn hợp lệ.

Không retry vô hạn 404 khi resource đã bị xóa có chủ đích. Phân biệt resource không tồn tại với API tạm thời lỗi và namespace sai.

## 15. Checklist

- Pod dùng ServiceAccount nào?
- ConfigMap hoặc Secret nằm ở namespace nào?
- Ứng dụng dùng environment/volume hay Kubernetes API?
- Integration lấy namespace mặc định hay namespace rõ ràng?
- Resource name có đúng không?
- Role nằm ở namespace bảo vệ resource chưa?
- RoleBinding subject có đúng tên và namespace ServiceAccount chưa?
- Verb get/list/watch có khớp integration chưa?
- Có cấp quyền Secret rộng hơn cần thiết không?
- API endpoint, CA và network có hoạt động không?
- 404, 403, 401 và timeout có được phân loại đúng không?
- Resource bị thiếu hoặc đổi thì startup, cache và watcher phản ứng thế nào?
- Log có tránh dữ liệu Secret không?

## 16. Kết luận

ConfigMap và Secret là resource namespaced. Muốn đọc đúng, ứng dụng phải xác định resource name, namespace, cách đọc và identity dùng để gọi API. ServiceAccount của Pod thuộc namespace của Pod; Role và RoleBinding phải được đặt và gắn đúng phạm vi bảo vệ resource.

Nếu dữ liệu được inject vào environment hoặc volume, ứng dụng có thể không cần đọc Kubernetes API. Nếu dùng Spring Cloud Kubernetes Config hoặc watcher, cần ServiceAccount, RBAC, timeout, reconnect và chính sách refresh. Đọc khác namespace có thể làm được bằng RoleBinding trong namespace đích, nhưng làm tăng coupling và phạm vi quyền.

Namespace rõ ràng, quyền tối thiểu và behavior được thiết kế cho resource thay đổi giúp ứng dụng Spring đọc đúng cấu hình mà không biến lỗi scope thành lỗi khó chẩn đoán hoặc cấp quyền toàn cluster không cần thiết.
