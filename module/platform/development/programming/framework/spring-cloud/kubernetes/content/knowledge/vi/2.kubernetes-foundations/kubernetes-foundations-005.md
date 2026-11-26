# Endpoints, EndpointSlice và mối liên hệ với Service

## 1. Vì sao Service chưa phải là Pod đích?

Khi một ứng dụng Spring gọi tên `inventory-service`, nó thường không muốn biết từng Pod đang chạy ở đâu. Ứng dụng cần một điểm truy cập ổn định, còn Kubernetes cần một cách ghi nhận những địa chỉ nào có thể nhận lưu lượng.

Ba đối tượng có vai trò liên quan nhưng không đồng nhất:

- **Service** định nghĩa điểm truy cập ổn định, cổng và cách chọn tập workload.
- **EndpointSlice** ghi các địa chỉ backend được nhóm cho một Service, cùng cổng và trạng thái liên quan.
- **Pod** là nơi tiến trình container thực sự chạy.

Có thể hình dung luồng dữ liệu như sau:

```text
Ứng dụng Spring
    |
    | gọi inventory-service:8080
    v
Service (ClusterIP/DNS/port)
    |
    | liên kết tới các backend phù hợp
    v
EndpointSlice
    |
    | các địa chỉ Pod và điều kiện sẵn sàng
    v
Pod inventory
```

Service không chứa mã ứng dụng và cũng không tự biến thành một Pod. EndpointSlice không phải một địa chỉ duy nhất để ứng dụng tùy ý lưu lại lâu dài. Đây là dữ liệu nền tảng dùng để hướng lưu lượng tới những backend mà Service đang đại diện.

Trong module **Spring Cloud Kubernetes**, hiểu ranh giới này giúp chọn đúng cách tích hợp. Ứng dụng có thể gọi Service qua DNS mà không đọc Kubernetes API. Khi cần danh sách instance cho DiscoveryClient hoặc Spring Cloud LoadBalancer, một integration có thể lấy dữ liệu Service và endpoint từ Kubernetes. Mỗi lựa chọn kéo theo một mô hình quyền, cache và xử lý thay đổi khác nhau.

## 2. Service cung cấp tên và chính sách truy cập

Một Service thường có các thông tin chính:

- Tên và namespace tạo nên tên DNS ổn định trong cluster.
- Một hoặc nhiều `port` mà client gọi.
- `targetPort`, là cổng mà lưu lượng được chuyển tới trên backend.
- Loại Service, chẳng hạn `ClusterIP`, `NodePort`, `LoadBalancer` hoặc headless Service.
- Selector, nếu Service dùng nhãn để tìm backend tự động.

Ví dụ Service nội bộ:

```yaml
apiVersion: v1
kind: Service
metadata:
  name: inventory-service
  namespace: shop
spec:
  selector:
    app: inventory
  ports:
    - name: http
      port: 8080
      targetPort: 8080
  type: ClusterIP
```

Với Service có ClusterIP, client trong cluster có thể dùng:

```text
http://inventory-service:8080
```

Nếu client ở namespace khác, tên đầy đủ thường có dạng:

```text
http://inventory-service.shop.svc.cluster.local:8080
```

Tên miền cluster có thể được cấu hình khác, nên ví dụ trên không nên được hard-code khi môi trường dùng hậu tố khác. Spring Boot có thể nhận base URL qua ConfigMap, Secret hoặc biến môi trường phù hợp với cách triển khai.

Khi client gọi Service, nó không cần tự đọc danh sách Pod chỉ để gửi một request HTTP. DNS cung cấp địa chỉ của Service, còn lớp mạng và cơ chế proxy của cluster xử lý việc đưa kết nối tới backend. Đây thường là lựa chọn đơn giản nhất cho lời gọi giữa các dịch vụ có tên ổn định.

## 3. Selector tạo mối liên hệ với backend

Selector của Service là một tập điều kiện nhãn. Với ví dụ trên, Service tìm các đối tượng phù hợp với:

```text
app = inventory
```

Chỉ có Pod mang nhãn tương ứng mới được xem xét cho Service. Selector không dựa vào tên Deployment, tên container hay tên Java class.

Một Deployment mẫu có thể gắn nhãn ở đúng Pod template:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: inventory
  namespace: shop
spec:
  replicas: 3
  selector:
    matchLabels:
      app: inventory
  template:
    metadata:
      labels:
        app: inventory
    spec:
      containers:
        - name: app
          image: example/inventory:1.0
          ports:
            - name: http
              containerPort: 8080
```

Có hai nơi cần phân biệt:

- `spec.selector.matchLabels` của Deployment quyết định Pod nào thuộc quyền quản lý của Deployment.
- `spec.selector` của Service quyết định Pod nào được Service chọn.

Chúng thường dùng cùng nhãn `app: inventory`, nhưng Kubernetes không tự bắt buộc hai selector phải giống nhau. Nếu chỉnh một bên mà quên bên kia, Deployment vẫn có thể chạy Pod trong khi Service không có backend.

Service selector cũng không tự kiểm tra một tiến trình có thực sự lắng nghe đúng cổng. `targetPort: 8080` chỉ có ý nghĩa khi container hoặc Pod có dịch vụ nhận kết nối ở cổng đó. Tên cổng có thể giúp tham chiếu nhất quán, nhưng vẫn cần kiểm tra ứng dụng và manifest phối hợp đúng.

## 4. Endpoint và EndpointSlice

### 4.1. Endpoint là dữ liệu backend

Kubernetes từng biểu diễn backend của Service qua đối tượng Endpoints. Đối tượng này có thể chứa tập địa chỉ và cổng của các backend. Với hệ thống lớn, một danh sách quá dài trong một đối tượng duy nhất khó mở rộng và khó cập nhật hiệu quả.

EndpointSlice chia tập backend thành những phần nhỏ hơn. Một Service có thể liên quan tới nhiều EndpointSlice. Mỗi slice chứa một nhóm endpoint và thông tin cổng dùng chung trong slice đó.

Ví dụ rút gọn một EndpointSlice:

```yaml
apiVersion: discovery.k8s.io/v1
kind: EndpointSlice
metadata:
  name: inventory-service-abcde
  namespace: shop
  labels:
    kubernetes.io/service-name: inventory-service
addressType: IPv4
ports:
  - name: http
    protocol: TCP
    port: 8080
endpoints:
  - addresses:
      - 10.20.1.15
    conditions:
      ready: true
      serving: true
      terminating: false
    nodeName: worker-a
  - addresses:
      - 10.20.2.22
    conditions:
      ready: false
      serving: true
      terminating: false
    nodeName: worker-b
```

Manifest trên minh họa cấu trúc và không nên được xem là một cách thủ công để duy trì backend cho Service có selector. Trong thông thường, controller của Kubernetes tạo và cập nhật EndpointSlice dựa trên Service, Pod, readiness và các điều kiện liên quan.

Nhãn `kubernetes.io/service-name` liên kết EndpointSlice với tên Service trong cùng namespace. Một Service có thể có nhiều slice, vì vậy client đọc discovery phải gộp dữ liệu từ các slice phù hợp trước khi tạo danh sách instance.

### 4.2. EndpointSlice không phải lúc nào cũng chỉ chứa endpoint sẵn sàng

Một endpoint có thể mang nhiều điều kiện:

| Điều kiện | Ý nghĩa khi đọc discovery |
|---|---|
| `ready` | Backend sẵn sàng nhận lưu lượng theo trạng thái mà Kubernetes công bố |
| `serving` | Backend vẫn đang phục vụ; có thể hữu ích trong giai đoạn chuyển tiếp |
| `terminating` | Endpoint thuộc Pod đang dừng và cần được xử lý theo chính sách kết nối |

Các chi tiết xử lý chuyển tiếp phụ thuộc phiên bản Kubernetes, loại Service và thành phần sử dụng dữ liệu. Ứng dụng không nên tự coi mọi địa chỉ trong mọi EndpointSlice là lựa chọn hợp lệ cho request mới.

Với client nghiệp vụ thông thường, backend chưa sẵn sàng không nên được đưa vào tập instance mới. Với quá trình graceful termination, một endpoint có thể còn phục vụ kết nối đang mở trong khi không nhận request mới. Chính sách của kube-proxy, ingress, service mesh hoặc client riêng có thể làm hành vi quan sát được khác nhau.

Khi điều tra một request đi nhầm Pod, cần xem cả:

1. Pod có readiness probe và probe đang thành công không?
2. EndpointSlice công bố điều kiện gì?
3. Service có cấu hình đặc biệt như `publishNotReadyAddresses` không?
4. Client hoặc load balancer có cache dữ liệu endpoint không?
5. Kết nối HTTP có được giữ lại qua thời điểm endpoint thay đổi không?

## 5. Readiness quyết định backend có nên nhận lưu lượng mới

Một ứng dụng Spring có thể đã mở cổng nhưng chưa sẵn sàng xử lý nghiệp vụ. Ví dụ, ứng dụng còn đang chạy migration, chưa kết nối được kho dữ liệu hoặc chưa nạp cấu hình bắt buộc.

Readiness probe mô tả điều kiện để Pod được xem là sẵn sàng. Ví dụ với Spring Boot Actuator:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: inventory
  namespace: shop
spec:
  template:
    spec:
      containers:
        - name: app
          image: example/inventory:1.0
          ports:
            - name: http
              containerPort: 8080
          readinessProbe:
            httpGet:
              path: /actuator/health/readiness
              port: http
            periodSeconds: 5
            failureThreshold: 3
          livenessProbe:
            httpGet:
              path: /actuator/health/liveness
              port: http
            periodSeconds: 10
```

Readiness và liveness có mục đích khác nhau:

- **Readiness:** tạm ngừng đưa lưu lượng mới tới Pod khi Pod chưa thể phục vụ an toàn.
- **Liveness:** cho biết container có cần được khởi động lại vì bị kẹt hoặc không còn hoạt động không.
- **Startup:** cho phép ứng dụng khởi động lâu có thời gian vượt qua giai đoạn ban đầu trước khi liveness bắt đầu áp dụng.

Không dùng liveness để biểu diễn một phụ thuộc tạm thời như API server hoặc database nếu việc đó khiến tất cả Pod liên tục bị khởi động lại. Liveness sai có thể biến một sự cố bên ngoài thành vòng lặp khởi động, làm mất cache và tạo thêm tải.

Readiness cũng không thay thế kiểm tra nghiệp vụ hoàn chỉnh. Một endpoint health có thể trả thành công trong khi một chức năng riêng đang lỗi. Hãy chọn nhóm kiểm tra phản ánh điều kiện nhận lưu lượng của dịch vụ, với timeout hợp lý và không gây tải lớn lên hệ thống phụ thuộc.

## 6. Khi nào Service không dùng selector?

Một Service có thể không có selector. Cách này hữu ích khi backend không phải Pod được chọn bằng nhãn, hoặc khi cần quản lý ánh xạ tới một đích ở bên ngoài cluster theo cơ chế riêng.

Ví dụ, Service không selector tạo ra tên và cổng ổn định:

```yaml
apiVersion: v1
kind: Service
metadata:
  name: legacy-inventory
  namespace: shop
spec:
  ports:
    - name: http
      port: 8080
      targetPort: 8080
```

Service như vậy không tự có endpoint backend chỉ vì đã khai báo `port`. Cần một cơ chế phù hợp cung cấp EndpointSlice hoặc dùng kiểu liên kết được Kubernetes hỗ trợ cho trường hợp đó. Không được gán tùy ý một EndpointSlice có dữ liệu không khớp rồi kỳ vọng hệ thống chấp nhận.

Điểm cần nhớ là “có Service” và “có backend được Service định tuyến tới” là hai điều kiện khác nhau. Khi DNS phân giải được tên nhưng kết nối thất bại, hãy kiểm tra cả endpoint, không chỉ kiểm tra Service tồn tại.

Service headless với `clusterIP: None` cũng có mô hình khác:

```yaml
apiVersion: v1
kind: Service
metadata:
  name: inventory-headless
  namespace: shop
spec:
  clusterIP: None
  selector:
    app: inventory
  ports:
    - name: http
      port: 8080
      targetPort: 8080
```

DNS của headless Service có thể trả về địa chỉ của các Pod thay vì một ClusterIP duy nhất. Đây là lựa chọn phù hợp cho một số hệ thống cần nhận diện từng backend, nhưng nó thay đổi giả định của client về DNS, cân bằng tải và vòng đời địa chỉ. Không đổi từ ClusterIP sang headless chỉ để “nhìn thấy Pod” mà chưa xác định rõ trách nhiệm của client.

## 7. Liên hệ với DiscoveryClient và Spring Cloud LoadBalancer

### 7.1. Gọi Service qua DNS

Nếu `order-service` chỉ cần gọi `inventory-service`, cấu hình URL tới tên Service thường đủ:

```properties
inventory.base-url=http://inventory-service.shop.svc.cluster.local:8080
```

Luồng này không yêu cầu Order đọc Service hoặc EndpointSlice qua Kubernetes API. Pod chỉ cần mạng, DNS và cấu hình endpoint đúng. Đây là cách giảm quyền RBAC và giảm số kết nối control plane.

Kubernetes chịu trách nhiệm cập nhật backend của Service. Client HTTP vẫn phải xử lý timeout, retry có kiểm soát, connection pool và lỗi tạm thời. DNS thành công không bảo đảm backend đang khỏe; endpoint và mạng vẫn cần được quan sát.

### 7.2. Dùng DiscoveryClient khi cần danh sách instance

DiscoveryClient tạo một abstraction để thành phần Spring hỏi danh sách instance theo tên dịch vụ. Backend tích hợp Kubernetes có thể lấy thông tin từ Service và EndpointSlice, tùy tính năng, phiên bản và cấu hình.

Luồng khái quát:

```text
DiscoveryClient
    -> bộ tích hợp Spring Cloud Kubernetes
    -> Service và EndpointSlice
    -> danh sách ServiceInstance
    -> thành phần gọi dịch vụ
```

Khi dùng cách này, cần xác minh:

- Tài nguyên nào được client đọc: Service, Endpoints, EndpointSlice, Pod hay metadata khác?
- Client đọc trong namespace hiện tại hay nhiều namespace?
- Dữ liệu được cache và refresh như thế nào?
- Endpoint chưa ready có bị loại ra không?
- Service port được ánh xạ thành host và port của ServiceInstance ra sao?
- ServiceAccount có đúng quyền `get/list/watch` cần thiết không?

Không cấp quyền đọc toàn cluster chỉ vì một ứng dụng gọi DiscoveryClient. Nếu module và client cho phép giới hạn namespace, hãy đặt giới hạn theo phạm vi nghiệp vụ.

### 7.3. Dùng Spring Cloud LoadBalancer

Spring Cloud LoadBalancer có thể chọn một instance từ danh sách mà DiscoveryClient cung cấp. Khi đó có hai lớp cần phân biệt:

| Lớp | Vai trò |
|---|---|
| Kubernetes Service | Điểm truy cập và chính sách định tuyến ở cấp cluster |
| DiscoveryClient | Đọc và chuyển đổi thông tin backend thành ServiceInstance |
| Spring Cloud LoadBalancer | Chọn một instance theo chiến lược client-side |
| HTTP client | Mở kết nối, timeout, retry và xử lý phản hồi |

Nếu LoadBalancer chọn địa chỉ Pod từ EndpointSlice, ứng dụng đang tham gia cân bằng tải phía client. Nếu ứng dụng gọi ClusterIP của Service, Kubernetes tiếp tục chịu trách nhiệm chọn backend ở lớp nền tảng. Chồng nhiều lớp có thể hợp lệ, nhưng cần biết mỗi lớp đang chọn gì.

Một thiết kế có thể gặp hiện tượng request phân phối không như mong đợi vì:

- LoadBalancer chọn một instance, nhưng connection pool giữ kết nối lâu.
- Cache discovery chưa kịp loại endpoint không còn ready.
- Service và client-side load balancing cùng áp dụng chiến lược riêng.
- Retry gửi lại request sang instance khác sau khi request đầu đã có thể được xử lý.
- Cổng của Service và cổng của Pod bị ánh xạ sai.

Retry chỉ nên bật khi thao tác có thể lặp an toàn hoặc có cơ chế idempotency. Không biến việc endpoint thay đổi thành lý do retry vô hạn.

## 8. RBAC cho việc đọc endpoint

Đọc EndpointSlice là quyền trên tài nguyên thuộc API group `discovery.k8s.io`. Ví dụ Role tối giản trong một namespace:

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

Role này chỉ minh họa phạm vi tài nguyên; quyền thực tế phải khớp hành vi của integration đang dùng. Một client có thể còn cần `endpoints`, `pods` hoặc `configmaps` cho tính năng khác. Không đoán quyền từ tên dependency.

Một RoleBinding gắn Role với ServiceAccount:

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

Các lỗi thường gặp:

| Lỗi | Hậu quả |
|---|---|
| Có ServiceAccount nhưng không có RoleBinding | API trả `403 Forbidden` |
| Chỉ cấp quyền trên core API nhưng bỏ qua `discovery.k8s.io` | Không đọc được EndpointSlice |
| Role ở namespace `shop`, nhưng client đọc namespace khác | Quyền không áp dụng cho tài nguyên ngoài namespace |
| Chỉ có `get`, trong khi client dùng `list/watch` | Discovery khởi động hoặc refresh thất bại |
| Cấp `cluster-admin` để chữa `403` | Quyền vượt xa nhu cầu và tăng rủi ro |

Nếu không cần đọc Kubernetes API, có thể dùng Service/DNS và tránh cấp các quyền này. Nếu cần discovery động, hãy bắt đầu từ log hoặc tài liệu cấu hình của integration để xác định thao tác API thực tế, sau đó thu hẹp quyền.

## 9. EndpointSlice thay đổi và tính nhất quán tạm thời

Endpoint không phải dữ liệu tĩnh. Khi Pod mới vượt readiness, địa chỉ có thể được thêm vào tập ready. Khi Pod dừng hoặc mất readiness, địa chỉ có thể bị loại hoặc chuyển trạng thái. Những bước này diễn ra qua các controller và cơ chế mạng, nên có độ trễ giữa thay đổi của Pod và quan sát của từng client.

Một client discovery cần chịu được:

- EndpointSlice đến theo nhiều sự kiện.
- Watch bị ngắt và phải nối lại.
- Cache tạm thời chứa dữ liệu cũ.
- Một Pod vừa sẵn sàng nhưng ứng dụng chưa được mọi nơi nhìn thấy.
- Một Pod vừa dừng nhưng connection pool vẫn còn kết nối cũ.
- Các instance thay đổi trong lúc request đang thực hiện.

Không dùng cache discovery như nguồn sự thật tuyệt đối cho giao dịch. Cache giúp giảm truy vấn và phản ứng nhanh hơn, nhưng logic nghiệp vụ vẫn phải xử lý lỗi kết nối và phản hồi không thành công.

Với Spring Cloud Kubernetes, cần quan sát thời điểm đồng bộ gần nhất, lỗi watch, kích thước danh sách instance và độ trễ refresh nếu integration cung cấp các tín hiệu này. Không ghi token, Secret hoặc toàn bộ nội dung nhạy cảm vào log khi chẩn đoán.

## 10. Quy trình điều tra khi Service không tới được Pod

Khi `order-service` không gọi được `inventory-service`, kiểm tra theo lớp:

1. Tên Service có đúng namespace và DNS suffix không?
2. Service có port và `targetPort` đúng với ứng dụng không?
3. Selector của Service có khớp nhãn Pod không?
4. Có EndpointSlice liên quan tới Service không?
5. Endpoint có địa chỉ và cổng đúng không?
6. Điều kiện `ready` của endpoint là gì?
7. Pod có lắng nghe trên đúng interface và cổng không?
8. NetworkPolicy hoặc firewall có chặn lưu lượng không?
9. Client có cache địa chỉ cũ hoặc giữ connection lâu không?
10. Nếu dùng DiscoveryClient, ServiceAccount có quyền trên đúng namespace và API group không?

Bảng sau giúp tách nguyên nhân:

| Hiện tượng | Lớp nên kiểm tra trước | Diễn giải |
|---|---|---|
| DNS không phân giải | Namespace, tên Service và DNS | Chưa tới bước kiểm tra EndpointSlice |
| DNS có kết quả nhưng connection refused | Pod, cổng, targetPort và ứng dụng | Có địa chỉ nhưng không có tiến trình nhận kết nối |
| Timeout | Mạng, NetworkPolicy, node và Pod | Cần phân biệt bị chặn với backend không phản hồi |
| Service không có backend | Selector, nhãn Pod và readiness | Có thể Deployment chạy nhưng Service chọn nhầm |
| Discovery trả danh sách rỗng | RBAC, namespace, API group và cache | Client có thể không đọc được hoặc lọc hết endpoint |
| Request tới Pod cũ | Cache, connection pool và thời điểm refresh | Endpoint đã đổi nhưng client chưa hội tụ |
| API trả 403 | Role, RoleBinding, ServiceAccount | Đây là lỗi quyền đọc control plane, khác lỗi HTTP nghiệp vụ |

Không giải quyết lỗi DNS bằng cách cấp thêm RBAC. Không giải quyết lỗi `403` bằng cách đổi readiness. Mỗi lớp có bằng chứng riêng cần kiểm tra.

## 11. Thực hành nhỏ: thêm một Pod mà không làm gián đoạn

Giả sử `inventory-service` đang có hai Pod. Mục tiêu là thêm Pod thứ ba an toàn.

Luồng mong đợi:

```text
Pod mới được tạo
    -> ứng dụng Spring khởi động
    -> startup probe vượt qua (nếu có)
    -> readiness probe thành công
    -> EndpointSlice công bố endpoint ready
    -> Service/LoadBalancer có thể chọn backend
```

Cần xác định:

- Readiness chỉ thành công sau khi ứng dụng đã có cấu hình bắt buộc.
- Cổng ứng dụng và `targetPort` khớp.
- Pod mới mang đúng nhãn Service selector.
- EndpointSlice có thêm địa chỉ với cổng đúng.
- Lưu lượng thử nghiệm tới Pod mới thành công trước khi tăng tải.
- Khi Pod bị dừng, readiness giảm hoặc quá trình termination loại Pod khỏi lựa chọn mới trước khi tiến trình kết thúc.

Với một ứng dụng Spring dùng DiscoveryClient, danh sách instance có thể cập nhật sau thời điểm EndpointSlice thay đổi. Vì vậy “Pod đã ready” và “mọi client đã thấy Pod” không phải cùng một thời điểm. Test rollout cần có khoảng hội tụ và kiểm tra lỗi thực tế.

## 12. Các nhầm lẫn thường gặp

### “Service là một Pod đặc biệt”

Service là abstraction truy cập và định tuyến. Pod chạy ứng dụng; EndpointSlice ghi backend mà Service có thể liên quan. Ba khái niệm có vòng đời và trách nhiệm khác nhau.

### “Service tồn tại là chắc chắn có backend”

Service không selector hoặc selector sai có thể không có endpoint phù hợp. Hãy kiểm tra EndpointSlice và nhãn Pod.

### “Tất cả địa chỉ trong EndpointSlice đều nhận request mới”

Endpoint có thể chưa ready hoặc đang terminating. Client phải tôn trọng điều kiện và chính sách của integration.

### “Readiness làm ứng dụng khỏe tuyệt đối”

Readiness chỉ mô tả khả năng nhận lưu lượng theo tiêu chí đã chọn tại thời điểm kiểm tra. Nó không bảo đảm mọi giao dịch sẽ thành công.

### “Dùng EndpointSlice nghĩa là ứng dụng phải gọi API server”

Không bắt buộc. Client thường gọi Service qua DNS; thành phần discovery mới có thể đọc EndpointSlice để tạo danh sách instance.

### “Có DiscoveryClient là không cần Service”

DiscoveryClient vẫn cần một nguồn discovery và chính sách kết nối. Trong Kubernetes, Service thường là phần định danh và cấu hình nền tảng; DiscoveryClient không tự xóa mọi vai trò của Service.

## 13. Checklist thiết kế

Trước khi triển khai ứng dụng Spring cùng Service, hãy trả lời:

- Tên Service, namespace, port và targetPort là gì?
- Selector của Service khớp chính xác nhãn trên Pod template chưa?
- Backend cần ClusterIP hay headless Service?
- Readiness probe kiểm tra điều kiện nào để endpoint được nhận lưu lượng?
- Có cần xem EndpointSlice trong ứng dụng, hay gọi Service qua DNS đã đủ?
- Nếu dùng DiscoveryClient, client cần đọc tài nguyên và namespace nào?
- Spring Cloud LoadBalancer đang chọn ClusterIP hay instance backend?
- Cache, watch, timeout và retry xử lý thay đổi endpoint ra sao?
- Khi Pod termination bắt đầu, lưu lượng mới được dừng trước khi container thoát thế nào?
- Có metric hoặc log cho số instance, thời điểm refresh và lỗi discovery không?

Nếu câu trả lời chỉ là “ứng dụng cần gọi một dịch vụ có tên cố định”, Service/DNS thường là điểm bắt đầu hợp lý. Nếu ứng dụng cần danh sách instance hoặc lựa chọn theo metadata, DiscoveryClient và Spring Cloud LoadBalancer có thể phù hợp, nhưng cần kèm RBAC tối thiểu, cache có giới hạn và xử lý lỗi rõ ràng.

Endpoints và EndpointSlice là cầu nối giữa trạng thái Pod và lưu lượng Service. Hiểu cầu nối đó giúp thiết kế readiness đúng, điều tra lỗi theo lớp và quyết định khi nào tính năng Spring Cloud Kubernetes thật sự cần thiết.
