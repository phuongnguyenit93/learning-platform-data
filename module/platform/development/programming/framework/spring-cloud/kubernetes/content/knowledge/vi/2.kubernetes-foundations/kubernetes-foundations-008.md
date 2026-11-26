# ServiceAccount, Role và RoleBinding

## 1. Tại sao Pod cần một danh tính?

Khi ứng dụng Spring chỉ gọi một Service qua DNS, Pod thường không cần đọc Kubernetes API. Nhưng các tính năng như discovery qua Kubernetes, đọc ConfigMap hoặc Secret bằng API, và một số cơ chế theo dõi cấu hình cần gửi yêu cầu tới API server. Kubernetes phải biết yêu cầu đó đến từ ai và danh tính đó được phép làm gì.

RBAC tách ba câu hỏi:

1. **Ai gọi API?** ServiceAccount cung cấp danh tính cho workload.
2. **Được làm thao tác nào trên tài nguyên nào?** Role hoặc một loại quyền tương đương mô tả các quy tắc.
3. **Quy tắc được gắn cho ai ở phạm vi nào?** RoleBinding liên kết danh tính với quyền trong một namespace.

Mối quan hệ khái quát:

```text
Pod Spring
    |
    | serviceAccountName
    v
ServiceAccount
    |
    | RoleBinding
    v
Role
    |
    | apiGroups + resources + verbs
    v
Kubernetes API quyết định allow/deny
```

ServiceAccount là danh tính, không phải danh sách quyền. Role là tập quy tắc, không tự cấp quyền cho Pod. RoleBinding là liên kết, không phải một tài khoản mới. Chỉ khi ba phần được ghép đúng, request của ứng dụng mới được phép.

Bài học thuộc phần **Nền tảng Kubernetes** của module **Spring Cloud Kubernetes**. Mục tiêu là cấp quyền vừa đủ cho DiscoveryClient, ConfigMap, Secret hoặc Configuration Watcher mà vẫn giữ ranh giới namespace và giảm phạm vi ảnh hưởng khi một Pod bị xâm nhập.

## 2. ServiceAccount: danh tính của workload

Một namespace có thể dùng ServiceAccount mặc định, nhưng ứng dụng nên có ServiceAccount riêng để dễ truy vết và giới hạn quyền:

```yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: order-runtime
  namespace: shop
```

Pod hoặc Deployment dùng danh tính này qua `serviceAccountName`:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: order-service
  namespace: shop
spec:
  replicas: 2
  selector:
    matchLabels:
      app: order
  template:
    metadata:
      labels:
        app: order
    spec:
      serviceAccountName: order-runtime
      containers:
        - name: app
          image: example/order-service:1.0
          ports:
            - name: http
              containerPort: 8080
```

Tên ServiceAccount phải nằm trong cùng namespace với Pod. Việc khai báo tên không tự tạo RoleBinding. Nếu không có binding, API server vẫn có thể trả `403 Forbidden`.

Nếu Pod không chỉ định `serviceAccountName`, Kubernetes thường dùng ServiceAccount `default` của namespace. Đây là lý do không nên cấp quyền rộng cho `default`: một workload mới trong cùng namespace có thể vô tình thừa hưởng quyền mà nó không cần.

ServiceAccount không đồng nghĩa với tài khoản người dùng. Nó đại diện cho workload trong cluster, có tên dạng namespace và tên tài khoản. Ví dụ:

```text
system:serviceaccount:shop:order-runtime
```

Khi kiểm tra RoleBinding, cần đối chiếu đúng namespace, đúng tên và đúng loại subject. Một RoleBinding cho ServiceAccount `shop/order-runtime` không cấp quyền cho ServiceAccount cùng tên ở namespace khác.

## 3. Role mô tả quyền theo tài nguyên

Role chứa các quy tắc RBAC trong một namespace:

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: order-discovery-reader
  namespace: shop
rules:
  - apiGroups: [""]
    resources: ["services"]
    verbs: ["get", "list", "watch"]
  - apiGroups: ["discovery.k8s.io"]
    resources: ["endpointslices"]
    verbs: ["get", "list", "watch"]
```

Mỗi rule thường trả lời bốn phần:

| Thành phần | Câu hỏi |
|---|---|
| `apiGroups` | Tài nguyên thuộc API group nào? |
| `resources` | Được truy cập loại tài nguyên nào? |
| `verbs` | Được thực hiện thao tác gì? |
| `resourceNames` | Có giới hạn vào một số tên tài nguyên cụ thể không? |

API group rỗng `[""]` là core API group, nơi có Service, ConfigMap, Secret và Pod. EndpointSlice thuộc `discovery.k8s.io`. Một lỗi thường gặp là cấp quyền trên `endpoints` nhưng integration lại đọc EndpointSlice, hoặc ngược lại.

Các verb thường gặp:

- `get`: đọc một tài nguyên theo tên.
- `list`: đọc danh sách tài nguyên.
- `watch`: theo dõi thay đổi để cập nhật cache.
- `create`, `update`, `patch`: tạo hoặc thay đổi tài nguyên.
- `delete`: xóa tài nguyên.

Ứng dụng đọc discovery thường chỉ cần `get/list/watch`. Không thêm `create`, `update`, `patch` hoặc `delete` nếu ứng dụng không điều khiển tài nguyên. Quyền ghi có thể biến một lỗi trong ứng dụng hoặc một lỗ hổng dependency thành thay đổi hạ tầng.

### 3.1. Quyền đọc ConfigMap

Nếu ứng dụng cần đọc ConfigMap bằng Kubernetes API, có thể cấp quyền theo namespace:

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: order-config-reader
  namespace: shop
rules:
  - apiGroups: [""]
    resources: ["configmaps"]
    verbs: ["get", "list", "watch"]
```

Cần xác định integration dùng cách nào. Một ứng dụng đọc đúng một ConfigMap đã biết tên có thể chỉ cần `get`, nhưng cơ chế refresh hoặc discovery theo nhãn có thể cần `list/watch`. Không tự rút gọn quyền chỉ theo ý định “chỉ đọc cấu hình” nếu chưa biết request API thực tế.

Nếu dùng ConfigMap được mount thành file hoặc biến môi trường, ứng dụng có thể không cần quyền API để lấy giá trị đó. Khi ấy thay đổi ConfigMap vẫn có quy tắc cập nhật riêng: biến môi trường thường gắn với vòng đời container, còn file mount có độ trễ cập nhật và không tự làm bean Spring đổi giá trị.

### 3.2. Quyền đọc Secret

Secret nhạy cảm hơn ConfigMap:

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: order-secret-reader
  namespace: shop
rules:
  - apiGroups: [""]
    resources: ["secrets"]
    verbs: ["get"]
    resourceNames: ["order-credentials"]
```

`resourceNames` có thể thu hẹp quyền đọc khi client dùng thao tác theo tên. Nhưng nếu cơ chế cần `list` hoặc `watch`, việc giới hạn theo tên có thể không đáp ứng được hành vi đó. Cần kiểm tra thiết kế và thư viện trước khi chọn cách ràng buộc.

Quyền đọc Secret có thể cho phép lấy nội dung dữ liệu bí mật, không chỉ xem tên. Vì vậy:

- Chỉ cấp quyền khi ứng dụng thật sự cần tự đọc Secret.
- Không ghi token, mật khẩu hoặc nội dung Secret vào log.
- Cân nhắc mount Secret hoặc dùng secret manager nếu ứng dụng không cần API.
- Không cấp `list secrets` cho tiện lợi nếu chỉ cần một Secret đã biết tên.
- Đánh giá vòng đời khi Secret thay đổi: tiến trình có đọc lại, khởi tạo lại kết nối hay cần rollout?

Dữ liệu Secret được biểu diễn bằng base64 trong manifest hoặc API không có nghĩa là dữ liệu đã được mã hóa theo cách bảo vệ khỏi mọi bên có quyền đọc.

## 4. RoleBinding gắn quyền với danh tính

RoleBinding nối một Role với một hoặc nhiều subject trong namespace:

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: order-discovery-reader
  namespace: shop
subjects:
  - kind: ServiceAccount
    name: order-runtime
    namespace: shop
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: Role
  name: order-discovery-reader
```

Ba điểm phải khớp:

- `subjects[].kind` là `ServiceAccount`.
- `subjects[].name` là tên ServiceAccount.
- `subjects[].namespace` và namespace của binding là namespace chứa danh tính và Role.

`roleRef` trỏ tới Role bằng tên. Sau khi tạo RoleBinding, sửa rule của Role sẽ ảnh hưởng tới các subject đang được binding. Không cần tạo một binding mới cho mỗi thay đổi nhỏ trong rule.

Một RoleBinding có thể tham chiếu ClusterRole. Khi đó quyền được định nghĩa ở ClusterRole nhưng binding vẫn giới hạn việc gắn quyền trong namespace của RoleBinding. Đây là khác biệt quan trọng với ClusterRoleBinding:

| Kiểu | Quyền được định nghĩa | Phạm vi gắn quyền |
|---|---|---|
| Role + RoleBinding | Trong Role của namespace | Một namespace |
| ClusterRole + RoleBinding | Trong ClusterRole | Namespace của RoleBinding |
| ClusterRole + ClusterRoleBinding | Trong ClusterRole | Toàn cluster hoặc tài nguyên cấp cluster |

Nếu ứng dụng chỉ hoạt động trong namespace `shop`, Role và RoleBinding thường dễ kiểm soát hơn. ClusterRoleBinding cấp quyền trên nhiều namespace và nên dành cho nhu cầu thật sự cần phạm vi đó, chẳng hạn một controller quản lý tài nguyên toàn cluster.

## 5. Ví dụ hoàn chỉnh cho DiscoveryClient

Giả sử `order-service` cần lấy danh sách backend của Service trong namespace `shop`. Một bộ manifest tối giản có thể gồm:

```yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: order-runtime
  namespace: shop
---
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: order-discovery-reader
  namespace: shop
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
  name: order-discovery-reader
  namespace: shop
subjects:
  - kind: ServiceAccount
    name: order-runtime
    namespace: shop
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: Role
  name: order-discovery-reader
```

Deployment cần trỏ tới ServiceAccount:

```yaml
spec:
  template:
    spec:
      serviceAccountName: order-runtime
```

Quyền trên chỉ là điểm bắt đầu minh họa. Integration cụ thể có thể cần đọc `endpoints`, `pods`, `configmaps` hoặc metadata khác tùy cấu hình. Cũng có thể cần quyền trên nhiều namespace nếu ứng dụng được thiết kế để discovery xuyên namespace. Khi đó nên xem xét lại ranh giới kiến trúc thay vì mặc định cấp ClusterRoleBinding.

Nếu Order chỉ gọi `inventory-service.shop.svc` qua DNS, có thể bỏ phần discovery API khỏi Pod Order. Khi đó Service/DNS đảm nhiệm điểm truy cập; Pod không cần Role đọc Service hoặc EndpointSlice chỉ cho lời gọi HTTP cố định.

## 6. Quyền cho Configuration Watcher và cập nhật cấu hình

Một ứng dụng có thể đọc ConfigMap hoặc Secret trực tiếp. Một Configuration Watcher riêng cũng có thể theo dõi thay đổi rồi gửi tín hiệu refresh tới ứng dụng. Hai thiết kế có phạm vi quyền khác nhau.

### 6.1. Ứng dụng trực tiếp đọc cấu hình

```text
Pod ứng dụng
    | ServiceAccount của ứng dụng
    | get/list/watch ConfigMap hoặc Secret
    v
Kubernetes API
```

Ứng dụng cần quyền đọc tài nguyên cấu hình. Nếu chỉ dùng file mount, ứng dụng có thể không cần Role tương ứng, nhưng phải xử lý việc đọc lại file và áp dụng giá trị mới.

### 6.2. Watcher đọc cấu hình

```text
Configuration Watcher
    | ServiceAccount của watcher
    | watch tài nguyên cấu hình
    v
Kubernetes API

Watcher -> thông báo refresh -> ứng dụng Spring
```

Tách watcher không tự xóa mọi quyền của ứng dụng. Nếu sau khi nhận tín hiệu, ứng dụng vẫn gọi API để đọc ConfigMap mới, ứng dụng vẫn cần quyền đọc. Nếu watcher gửi cả giá trị cấu hình qua một kênh khác, có thể giảm phần quyền API của ứng dụng nhưng phải bảo vệ kênh và dữ liệu.

Cần cấp ServiceAccount riêng cho watcher và ứng dụng khi hai thành phần có nhu cầu khác nhau. Không dùng một tài khoản có quyền đọc Secret cho mọi Pod chỉ vì việc chia sẻ manifest dễ hơn.

## 7. Token và cách Pod xác thực

Trong cluster, client Kubernetes thường sử dụng thông tin ServiceAccount được cung cấp cho Pod để xác thực với API server. Cách thư viện đọc token, CA và địa chỉ API server phụ thuộc client và phiên bản nền tảng.

Một số nguyên tắc vận hành:

- Không coi token là bí mật có thể đưa vào log hoặc đưa vào image.
- Không tắt xác minh TLS để vượt qua lỗi chứng thư.
- Không copy kubeconfig quản trị vào container.
- Kiểm tra Pod thực sự chạy với ServiceAccount nào.
- Hiểu cách token được cấp và thay mới trong môi trường hiện tại.
- Cân nhắc tắt việc tự gắn token cho Pod không cần Kubernetes API, sau khi kiểm tra các thành phần trong Pod.

Tự gắn token và quyền RBAC là hai lớp khác nhau. Tắt token không thay thế việc thu hẹp Role; cấp token không đồng nghĩa token đó có quyền đọc tài nguyên.

Khi chạy ngoài cluster trong môi trường phát triển, client có thể dùng kubeconfig của người lập trình. Điều này dễ che giấu lỗi RBAC vì tài khoản phát triển thường có quyền rộng hơn ServiceAccount sản xuất. Cần kiểm thử bằng danh tính có phạm vi tương đương production.

## 8. Kiểm tra quyền theo bằng chứng

Khi ứng dụng nhận `403 Forbidden`, kiểm tra theo thứ tự:

1. Pod có dùng đúng `serviceAccountName` không?
2. ServiceAccount có nằm trong đúng namespace không?
3. RoleBinding có trỏ đúng subject không?
4. RoleBinding có trỏ đúng Role hoặc ClusterRole không?
5. Rule có đúng `apiGroups`, `resources` và `verbs` không?
6. Client đang đọc namespace nào?
7. Client đang gọi EndpointSlice hay Endpoints?
8. Có NetworkPolicy hoặc TLS làm lỗi trước khi RBAC được đánh giá không?

Có thể kiểm tra theo nguyên tắc “can I” bằng công cụ quản trị phù hợp:

```text
kubectl auth can-i list endpointslices \
  --api-group=discovery.k8s.io \
  --as=system:serviceaccount:shop:order-runtime \
  -n shop
```

Lệnh trên là ví dụ điều tra của người vận hành, không phải mã mà ứng dụng cần chạy. Kết quả `yes` chỉ xác nhận một thao tác cụ thể; nó không chứng minh ServiceAccount có mọi quyền cần thiết.

Bảng suy luận nhanh:

| Lỗi quan sát được | Khả năng cần kiểm tra |
|---|---|
| `401 Unauthorized` | Token, thông tin xác thực hoặc endpoint API |
| `403 Forbidden` | ServiceAccount, RoleBinding, resource, verb, namespace |
| DNS gọi Service thất bại | DNS, Service, mạng; không mặc định là RBAC |
| Discovery rỗng | Quyền đọc, bộ lọc, namespace, endpoint hoặc cache |
| ConfigMap đổi nhưng ứng dụng giữ giá trị cũ | Cơ chế refresh và khả năng áp dụng của bean |
| Pod mới có token nhưng gọi API bị từ chối | Token có danh tính nhưng thiếu binding hoặc rule |

Không chữa mọi lỗi bằng cách cấp ClusterRoleBinding hoặc `cluster-admin`. Hãy lấy request cụ thể bị từ chối làm cơ sở mở rộng đúng một phần quyền cần thiết.

## 9. Mô hình cấp quyền tối thiểu

Một quy trình thực tế:

1. Liệt kê tính năng thực sự bật: DNS, DiscoveryClient, ConfigMap, Secret, watcher hay controller.
2. Xác định thành phần nào trực tiếp gọi Kubernetes API.
3. Ghi nhận request cần dùng: API group, resource, namespace và verb.
4. Tạo ServiceAccount riêng cho từng workload có ranh giới quyền khác nhau.
5. Tạo Role trong namespace nhỏ nhất có thể.
6. Binding đúng ServiceAccount và không dùng tài khoản mặc định cho quyền nhạy cảm.
7. Kiểm thử khởi động, refresh, mất API tạm thời và rollout Pod.
8. Quan sát lỗi `401/403`, thời điểm watch và nội dung cache mà không lộ dữ liệu bí mật.
9. Loại bỏ quyền thừa sau khi xác nhận tính năng vẫn hoạt động.

Sơ đồ lựa chọn:

```text
Ứng dụng chỉ gọi Service/DNS?
    |
    +-- Có --> Không cần RBAC đọc API cho lời gọi đó
    |
    '-- Không --> Cần API?
                |
                +-- Discovery --> ServiceAccount + Role đọc discovery
                +-- ConfigMap --> Role đọc ConfigMap
                +-- Secret --> Role đọc Secret, giới hạn chặt hơn
                '-- Watcher/controller --> Tài khoản riêng theo phạm vi quản lý
```

Mục tiêu không phải là làm Role ngắn nhất bằng mọi giá. Mục tiêu là quyền đủ cho chức năng, dễ giải thích và không mở rộng sang tài nguyên mà workload không sở hữu.

## 10. Những nhầm lẫn dễ gây lỗi

### “ServiceAccount đã có sẵn thì ứng dụng có thể đọc API”

ServiceAccount chỉ cung cấp danh tính. Không có RoleBinding phù hợp, request có thể bị từ chối.

### “Role trong namespace nào cũng cấp quyền cho Pod”

Role chỉ có ý nghĩa trong phạm vi namespace của nó. Pod ở namespace khác không tự nhận quyền từ Role đó.

### “RoleBinding và ClusterRoleBinding chỉ khác tên”

RoleBinding giới hạn việc gắn quyền trong một namespace, dù nó có thể tham chiếu ClusterRole. ClusterRoleBinding có phạm vi rộng hơn và cần thận trọng hơn.

### “Đọc một Secret cũng giống đọc một ConfigMap”

Secret chứa dữ liệu nhạy cảm và quyền đọc có thể dẫn tới lộ thông tin xác thực. Hãy cấp riêng, giới hạn theo tên khi phù hợp và tránh log.

### “Cấp quyền list là chỉ thấy danh sách tên”

Với nhiều tài nguyên, đặc biệt Secret, quyền đọc danh sách có thể cho phép nhận dữ liệu mà ứng dụng không cần. Không dùng list thay cho get một cách tùy tiện.

### “Có watcher thì ứng dụng không cần quyền cấu hình”

Nếu ứng dụng vẫn đọc nguồn mới sau khi nhận tín hiệu, quyền đọc vẫn cần tồn tại. Cần phân tích toàn bộ luồng dữ liệu.

## 11. Checklist trước khi triển khai

- Pod có dùng ServiceAccount riêng với tên rõ nghĩa không?
- ServiceAccount có nằm đúng namespace không?
- Role có đúng API group và resource mà client gọi không?
- Có dùng `watch` khi integration cần theo dõi thay đổi không?
- RoleBinding có subject và `roleRef` chính xác không?
- Quyền có bị mở sang namespace hoặc resource không cần thiết không?
- Có thực sự cần đọc Secret qua API không?
- Có thể dùng Service/DNS hoặc mount cấu hình để giảm quyền không?
- Deployment mới có giữ đúng `serviceAccountName` không?
- Đã kiểm thử bằng danh tính production tương đương chưa?
- Đã có cách quan sát `401`, `403`, lỗi refresh và độ cũ cache chưa?
- Khi thu hồi quyền, ứng dụng phản ứng và báo lỗi có dễ hiểu không?

ServiceAccount, Role và RoleBinding tạo thành nền tảng kiểm soát truy cập cho các tích hợp Spring Cloud Kubernetes. Tách rõ danh tính, quy tắc và binding giúp ứng dụng dùng DiscoveryClient, ConfigMap, Secret hoặc Configuration Watcher theo nhu cầu thực tế, đồng thời giữ quyền RBAC ở mức có thể kiểm soát.
