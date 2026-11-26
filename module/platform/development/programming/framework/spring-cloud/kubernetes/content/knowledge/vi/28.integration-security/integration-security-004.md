# Nguyên tắc tối thiểu quyền đối với Secret

Trong chương **Bảo mật tích hợp** của module **SPRING_CLOUD_KUBERNETES**, bài học này hướng dẫn xác định đúng ai cần nhận Secret, nhận bằng cách nào và cần những quyền gì. Mục tiêu là để ứng dụng Spring sử dụng được credential cần thiết mà một lỗi ở ứng dụng không mở rộng thành quyền đọc toàn bộ Secret của namespace hoặc cluster.

Các quyết định về DiscoveryClient, ConfigMap, Spring Cloud LoadBalancer và Configuration Watcher đều phải được xét riêng. Việc ứng dụng cần biết địa chỉ một dịch vụ không tự tạo ra nhu cầu đọc Secret; việc cần cập nhật cấu hình cũng không tự tạo ra nhu cầu theo dõi tất cả Secret.

## 1. Tình huống và mục tiêu của bài học

Giả sử dịch vụ `orders` chạy trong namespace `payments` và cần kết nối cơ sở dữ liệu bằng credential trong Secret `orders-db-runtime`. Secret có hai key `username` và `password`. Một tác vụ migration sử dụng tài khoản mạnh hơn, được lưu trong Secret riêng `orders-db-migrator`.

Yêu cầu của tiến trình phục vụ request:

- Nhận được credential runtime cần thiết để truy cập cơ sở dữ liệu.
- Không nhận credential migration hoặc credential của dịch vụ khác.
- Không tạo, sửa hay xóa Secret.
- Không được tự sửa workload hoặc RBAC để mở rộng khả năng truy cập.
- Cập nhật credential theo một quy trình có thể kiểm chứng mà không ghi giá trị vào log.

Ví dụ trong bài giả định namespace và Secret thử nghiệm đã được cấp qua quy trình quản lý bí mật của môi trường. Các manifest không chứa giá trị credential thật. Khi triển khai, thay image minh họa bằng image của ứng dụng đã chuẩn bị.

Sau bài học, bạn có thể lựa chọn giữa Secret volume và đọc API, viết Role cho một hợp đồng GET theo tên, nhận diện quyền gián tiếp, đồng thời kiểm chứng cả quyền cần có và quyền phải nằm ngoài phạm vi.

## 2. Xác định đường dữ liệu trước khi viết RBAC

Có hai đường nhận Secret rất khác nhau:

```text
Đường A: Kubernetes API → kubelet → Secret volume → tiến trình Spring
Đường B: tiến trình Spring + credential ServiceAccount → Kubernetes API → Secret
```

Trong đường A, kubelet cung cấp volume cho Pod theo cơ chế của Kubernetes. ServiceAccount của ứng dụng không cần quyền `get secrets` chỉ để ứng dụng đọc các file đã được mount. Tuy vậy, tiến trình có quyền đọc file vẫn đã nhận giá trị bí mật; không có quyền API không đồng nghĩa không biết Secret. [Kubernetes: Secrets](https://kubernetes.io/docs/concepts/configuration/secret/).

Trong đường B, ứng dụng là client của API server. Cần kiểm tra chính xác danh tính, namespace, tài nguyên, tên và động từ mà client thực sự gọi.

| Cách nhận | Ứng dụng cần quyền đọc Secret qua API? | Phạm vi dữ liệu cần kiểm soát |
| --- | --- | --- |
| Volume tham chiếu một Secret | Không, nếu chỉ đọc file mount | Secret được tham chiếu, các key được chiếu và container được mount |
| `secretKeyRef` cho biến môi trường | Không, nếu chỉ nhận biến do Kubernetes cấp | Từng key được khai báo; vòng đời cập nhật của tiến trình |
| Client GET Secret theo tên | Có | Toàn bộ object được GET, dù code chỉ dùng một key |
| Client LIST/WATCH Secret | Có | Tập object thực tế mà request được phép trả về |
| Controller cấp Secret từ hệ thống ngoài | Quyền thuộc từng thành phần trong chuỗi | Danh tính của controller/provider, nguồn ngoài và đích Kubernetes |

Kubernetes cảnh báo rằng quyền LIST/WATCH Secret có thể cho phép thấy nội dung Secret, và người có quyền tạo Pod có thể tham chiếu Secret trong namespace. Vì thế, “chỉ đọc danh sách” và “không có GET trực tiếp” chưa phải bằng chứng về sự cô lập. [Kubernetes: Good practices for Kubernetes Secrets](https://kubernetes.io/docs/concepts/security/secrets-good-practices/).

### Ba phạm vi quyền phải thiết kế cùng nhau

1. **Quyền lấy dữ liệu:** ServiceAccount hoặc thành phần nào có thể lấy Secret từ API/nguồn ngoài?
2. **Quyền nhận dữ liệu:** Pod, container và tiến trình nào được cấp file hoặc biến môi trường?
3. **Quyền sử dụng credential:** Tài khoản trong Secret có thể làm gì ở cơ sở dữ liệu hay dịch vụ đích?

Một ServiceAccount rất hẹp vẫn không bù được việc Secret chứa tài khoản quản trị cơ sở dữ liệu. Ngược lại, tài khoản cơ sở dữ liệu có quyền runtime hẹp cũng không phải lý do cấp ứng dụng khả năng đọc Secret của các dịch vụ khác.

## 3. Diễn đạt quyền tối thiểu thành một hợp đồng cụ thể

Đừng bắt đầu bằng một Role dùng chung “cho mọi ứng dụng Spring”. Bắt đầu bằng hợp đồng có thể kiểm tra:

| Chiều giới hạn | Quyết định cho ví dụ `orders` |
| --- | --- |
| Danh tính | ServiceAccount riêng cho workload runtime |
| Namespace | Chỉ `payments` |
| Tài nguyên | Chỉ `secrets` khi đường API thật sự cần |
| Tên object | Chỉ `orders-db-runtime` trong phương án GET |
| Thao tác | GET; không mặc định thêm LIST/WATCH hoặc quyền ghi |
| Container nhận dữ liệu | Container ứng dụng cần kết nối cơ sở dữ liệu |
| Dữ liệu được nhận | Credential runtime; credential migration ở Secret khác |
| Thời gian sử dụng | Có cơ chế xoay vòng và thu hồi ở hệ thống đích |

RBAC của Kubernetes cộng các quyền từ những binding liên quan và không có quy tắc deny. Role có `resourceNames` hẹp không vô hiệu hóa quyền rộng đã được cấp bởi một RoleBinding hoặc ClusterRoleBinding khác. Role thuộc namespace; một RoleBinding tham chiếu ClusterRole vẫn có thể cấp quyền namespaced trong namespace của binding. [Kubernetes: Using RBAC Authorization](https://kubernetes.io/docs/reference/access-authn-authz/rbac/).

Từ đó, kiểm tra phải dựa trên **quyền hiệu lực của danh tính**, không chỉ dựa trên manifest mới viết. Cần xem cả binding trực tiếp, binding cho nhóm ServiceAccount và các quyền kế thừa qua nhóm đã được cấp trong môi trường.

### Secret là đơn vị object, không phải đơn vị key của RBAC

Quyền GET một Secret cho phép đọc dữ liệu của object đó. Việc code chỉ truy cập `data.password` không hạn chế người giữ cùng credential API chỉ đọc key `password`.

Nếu hai người nhận không được phép thấy cùng dữ liệu, tách thành các Secret có vòng đời và quyền phù hợp. Ví dụ, để `orders-db-runtime` và `orders-db-migrator` riêng thay vì đặt cả mật khẩu runtime lẫn mật khẩu quản trị trong một object rồi trông chờ code tự bỏ qua key mạnh hơn.

Khi chiếu volume, `items` giới hạn những key xuất hiện trong volume đó. Đây là giới hạn tại đường cấp file, không phải quyền GET theo key và không thay thế việc kiểm soát ai có thể sửa Pod.

## 4. Phương án A: nhận Secret qua volume, không cấp quyền Secret API

Phương án này phù hợp khi ứng dụng chỉ cần nhận credential từ file. Trong ví dụ nền, ứng dụng gọi dịch vụ khác qua DNS Service, không cần trực tiếp dùng Kubernetes API cho discovery hoặc cấu hình.

### 4.1. ServiceAccount riêng và volume được chiếu hẹp

```yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: orders-runtime
  namespace: payments
automountServiceAccountToken: false
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders
  namespace: payments
spec:
  replicas: 2
  selector:
    matchLabels:
      app: orders
  template:
    metadata:
      labels:
        app: orders
    spec:
      serviceAccountName: orders-runtime
      automountServiceAccountToken: false
      securityContext:
        runAsNonRoot: true
        runAsUser: 10001
        runAsGroup: 2000
        fsGroup: 2000
      containers:
        - name: app
          image: registry.example.internal/orders:1.0.0
          ports:
            - containerPort: 8080
          securityContext:
            allowPrivilegeEscalation: false
            capabilities:
              drop:
                - ALL
          volumeMounts:
            - name: database-credentials
              mountPath: /etc/app-secrets
              readOnly: true
      volumes:
        - name: database-credentials
          secret:
            secretName: orders-db-runtime
            defaultMode: 0440
            items:
              - key: username
                path: db.username
              - key: password
                path: db.password
```

Không có Role hoặc RoleBinding cấp quyền đọc Secret cho `orders-runtime` trong phương án này. Điều đó vẫn cần được kiểm chứng với các binding sẵn có của cluster.

Chỉ container có `volumeMounts` tương ứng mới được cấp đường mount đó. Nếu thêm sidecar hoặc init container, xem lại nhu cầu nhận credential của từng container. `readOnly: true` hạn chế ghi vào mount, không ngăn tiến trình đọc rồi gửi dữ liệu ra ngoài.

`0440` là cách biểu diễn octal trong YAML, tương ứng `288` khi phải viết dưới dạng số thập phân JSON. Image cần chạy được với UID/GID đã chọn; kiểm chứng quyền đọc file sau khi áp dụng nhóm cho volume. Không chuyển sang quyền đọc rộng cho mọi user chỉ để xử lý nhanh một lỗi quyền file. [Kubernetes: Distribute Credentials Securely Using Secrets](https://kubernetes.io/docs/tasks/inject-data-application/distribute-credentials-secure/).

Tắt automount giảm một đường cấp credential API không cần thiết. Cấu hình này không thu hồi quyền RBAC đã có, không loại bỏ token được mount thủ công và không chặn cơ chế danh tính bên ngoài nếu Pod có cơ chế đó. [Kubernetes: Configure Service Accounts for Pods](https://kubernetes.io/docs/tasks/configure-pod-container/configure-service-account/).

### 4.2. Nạp file bằng configuration tree của Spring Boot

Cấu hình ứng dụng cho phương án nền:

```yaml
spring:
  application:
    name: orders
  config:
    import: "configtree:/etc/app-secrets/"
  cloud:
    kubernetes:
      discovery:
        enabled: false
      config:
        enabled: false
      secrets:
        enabled: false
```

Hai file `db.username` và `db.password` tạo các thuộc tính tương ứng `db.username` và `db.password`. Spring Boot hỗ trợ `configtree:` để nạp các file thành giá trị cấu hình; tên file có dấu chấm được ánh xạ thành tên thuộc tính. Ví dụ không dùng tiền tố `optional:` vì credential là đầu vào bắt buộc. [Spring Boot: Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html).

Không có `spring.config.import: "kubernetes:"` trong phương án này. Việc tắt property source Secret của Spring Cloud Kubernetes không ngăn Spring Boot đọc volume bằng `configtree:`; đó là hai đường cấu hình khác nhau.

Khai báo bắt buộc thư mục cấu hình chưa thay thế kiểm tra từng thuộc tính. Ứng dụng vẫn phải xác minh các giá trị yêu cầu tồn tại và hợp lệ trước khi nhận lưu lượng, đồng thời tránh mật khẩu mặc định khi thiếu cấu hình.

Các cờ bật/tắt phải được đặt ở giai đoạn cấu hình thực sự có hiệu lực. Ví dụ trên giả định cơ chế Config Data của Spring Boot; nếu dự án chọn bootstrap legacy, cần đối chiếu vị trí cấu hình theo release tương ứng. [Spring Cloud Kubernetes: Kubernetes Ecosystem Awareness](https://docs.spring.io/spring-cloud-kubernetes/reference/kubernetes-awareness.html).

### 4.3. Nếu vẫn cần DiscoveryClient

Một ứng dụng có thể nhận Secret qua volume nhưng vẫn cần token và quyền API để discovery. Khi đó, điều chỉnh ServiceAccount/token và cấp quyền cho đúng tài nguyên discovery mà release sử dụng, chẳng hạn Service cùng Endpoints hoặc EndpointSlice; không tự thêm `secrets` vào Role đó.

Tương tự, chỉ đọc ConfigMap không kéo theo quyền đọc Secret. Spring Cloud LoadBalancer chọn instance dịch vụ; chức năng đó không phải lý do để cấp quyền đọc credential. Mục tiêu của phần này là tách nhu cầu tính năng khỏi quyền Secret, không yêu cầu mọi ứng dụng phải tắt discovery.

## 5. Phương án B: client thật sự chỉ GET một Secret theo tên

Một số ứng dụng cần đọc Secret qua Kubernetes API. Trước khi cấp quyền, xác định hành vi client bằng tài liệu, cấu hình và request thực tế của đúng phiên bản. Trong phương án dưới, hợp đồng đã chọn là:

```http
GET /api/v1/namespaces/payments/secrets/orders-db-runtime
```

Client không cần tìm Secret bằng label, liệt kê namespace hoặc mở informer cho Secret. Mẫu RBAC dưới đây thể hiện chính xác hợp đồng GET đó; không bảo đảm mọi starter Spring Cloud Kubernetes đều chỉ tạo một request như trên.

### 5.1. Role và RoleBinding cho một object

```yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: orders-api-reader
  namespace: payments
---
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: orders-db-read-one
  namespace: payments
rules:
  - apiGroups:
      - ""
    resources:
      - secrets
    resourceNames:
      - orders-db-runtime
    verbs:
      - get
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: orders-db-read-one
  namespace: payments
subjects:
  - kind: ServiceAccount
    name: orders-api-reader
    namespace: payments
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: Role
  name: orders-db-read-one
```

`apiGroups: [""]` chỉ core API group, nơi có Secret. `resourceNames` chứa tên object, không phải tên key trong `data`, không phải label và không phải đường dẫn file.

Pod dùng phương án B phải chỉ định `serviceAccountName: orders-api-reader` và nhận credential API phù hợp, chẳng hạn projected token của ServiceAccount do Kubernetes cấp. Không ghép cấu hình tắt automount của phương án A vào client đang trông chờ token tự động, rồi giải quyết lỗi bằng token quản trị nhúng trong image.

Không có các quyền `list`, `watch`, `create`, `update`, `patch` hoặc `delete` trong Role này. Nếu một binding khác cấp những quyền đó cho danh tính, quyền hiệu lực vẫn rộng hơn mẫu đang thấy.

### 5.2. Liên hệ với property source của Spring Cloud Kubernetes

Để chọn Secret theo tên, các thuộc tính định danh nguồn thường có dạng:

```yaml
spring:
  cloud:
    kubernetes:
      secrets:
        name: orders-db-runtime
        namespace: payments
        include-profile-specific-sources: false
```

Đây là **đoạn chọn nguồn**, không phải cấu hình đầy đủ để bật đọc API. Cần chọn đúng starter/client, cơ chế import/bootstrap và cờ bật tính năng theo BOM của dự án. Một số dòng phiên bản có cờ `enable-api`; không coi tên cờ hay hành vi mặc định của dòng đó là cam kết cho mọi release. [Spring Cloud Kubernetes: Secrets PropertySource](https://docs.spring.io/spring-cloud-kubernetes/reference/property-source-config/secrets-propertysource.html), [Common application properties](https://docs.spring.io/spring-cloud-kubernetes/reference/appendix.html).

Tắt nguồn theo profile trong ví dụ giúp hợp đồng không vô tình yêu cầu thêm một Secret có tên dẫn xuất từ profile. Cũng cần xem lại `sources`, label, namespace bổ sung và cấu hình được nạp từ các vị trí khác; một đoạn cấu hình cục bộ không mô tả hết cấu hình hiệu lực.

Nếu ứng dụng vẫn gọi LIST khi đã khai báo tên, giữ nguyên thông tin lỗi để xác định nguyên nhân: chiến lược đọc, cache, informer, cấu hình nguồn hay một thành phần khác. Không thêm LIST/WATCH theo quán tính chỉ để ứng dụng khởi động được. Các lựa chọn cần cân nhắc là dùng cách đọc theo tên thực sự được hỗ trợ, chuyển sang volume hoặc chấp nhận một phạm vi quyền lớn hơn sau khi đã nêu rõ nhu cầu và giới hạn.

## 6. LIST, WATCH, label selector và giới hạn theo tên

### 6.1. LIST/WATCH là quyền nhận dữ liệu

GET theo tên hướng tới một object. LIST có thể trả một tập object kèm dữ liệu của chúng; WATCH có thể chuyển các thay đổi của object trong luồng sự kiện. Giao diện `kubectl get secrets` chỉ in tên và loại không làm quyền LIST trở thành quyền chỉ xem metadata.

Với yêu cầu runtime chỉ dùng `orders-db-runtime`, việc cấp danh sách toàn bộ Secret của `payments` mở ra một phạm vi dữ liệu không cần thiết. Nếu watcher dùng danh tính riêng, khả năng đọc tập Secret thuộc về watcher đó; nó không tự biến mất vì ứng dụng không trực tiếp mở API.

### 6.2. Label selector không phải ranh giới RBAC của Kubernetes

Một client có thể gửi `labelSelector=app=orders` để chọn dữ liệu. Nếu credential của client có quyền LIST Secret trong cả namespace, client khác dùng cùng credential có thể gửi request không có selector đó. Thiết kế “ứng dụng của tôi luôn lọc label” là hành vi ứng dụng, không phải một quyền RBAC theo label.

Nhãn vẫn hữu ích để điều phối hoặc chọn đối tượng cho controller, nhưng phải tách rõ hai câu hỏi: controller dự định xử lý gì và danh tính của controller được phép đọc gì.

### 6.3. LIST/WATCH với `resourceNames` có điều kiện

Kubernetes có thể kết hợp giới hạn tên với LIST/WATCH, nhưng request của client phải có field selector `metadata.name` phù hợp. Label selector không thay thế yêu cầu này. Nếu client dùng informer để LIST toàn bộ namespace rồi mới lọc trong bộ nhớ, một Role theo tên không khiến request rộng đó tự động được phép. [Kubernetes RBAC: referring to resources](https://kubernetes.io/docs/reference/access-authn-authz/rbac/#referring-to-resources).

Vì vậy, chỉ thêm LIST/WATCH theo tên khi đã chứng minh client gửi loại request tương ứng, bao gồm lần LIST đầu, WATCH và các lần đồng bộ lại. Không dùng việc một request kiểm tra thủ công thành công để suy ra vòng đời informer cũng sẽ thành công.

Quyền theo tên cũng không phải giới hạn tổng quát cho mọi động từ. Chẳng hạn, không thể dùng `resourceNames` để biến quyền tạo object cấp cao nhất thành quyền chỉ tạo một Secret với tên cố định. Tác vụ cấp phát và xoay vòng cần thiết kế quyền riêng, thay vì mở quyền tạo cho tiến trình runtime.

## 7. Tách Configuration Watcher khỏi danh tính ứng dụng

Configuration Watcher là một workload có nhu cầu quyền riêng. Theo tài liệu Spring Cloud Kubernetes, việc theo dõi Secret không được bật mặc định; khi bật, các selector xác định những Secret watcher dự định xử lý. Watcher có thể thông báo refresh bằng HTTP hoặc Spring Cloud Bus. [Spring Cloud Kubernetes Configuration Watcher](https://docs.spring.io/spring-cloud-kubernetes/reference/spring-cloud-kubernetes-configuration-watcher.html).

Đối với tình huống `orders`, có thể chọn một trong các thiết kế sau:

| Thiết kế cập nhật | Nhu cầu quyền và vận hành |
| --- | --- |
| Secret volume và rollout có kiểm soát | Ứng dụng không cần API Secret; quy trình triển khai chịu trách nhiệm cập nhật tiến trình |
| Ứng dụng tự đọc đúng Secret | Danh tính runtime cần quyền API đã chứng minh là cần thiết |
| Watcher nhận thay đổi rồi gửi refresh | Watcher có ServiceAccount riêng; kiểm tra phạm vi Secret và các endpoint được gọi |
| Nguồn bí mật ngoài Kubernetes | Kiểm tra quyền của workload/provider, TTL và khả năng thu hồi ở nguồn ngoài |

Không dùng ServiceAccount của watcher làm ServiceAccount mặc định cho mọi ứng dụng. Nếu controller cần quyền rộng hơn runtime, việc tách danh tính giúp giữ phạm vi đó tập trung và dễ kiểm tra hơn.

Giới hạn namespace và phạm vi object theo khả năng thực tế của implementation. Selector trong cấu hình watcher không làm một quyền LIST rộng tự chuyển thành quyền hẹp theo label. Nếu không thu hẹp được request ở mức tên, ghi rõ phạm vi đọc mà controller có và cân nhắc tách controller/namespace theo miền tin cậy.

Khi refresh qua HTTP, bảo vệ endpoint quản trị bằng cơ chế xác thực, phân quyền và kiểm soát đường mạng phù hợp. Khi dùng Bus, xem xét quyền truy cập broker, tập người nhận và khả năng nhận sự kiện ngoài phạm vi mong muốn. Không cần đưa giá trị Secret vào sự kiện điều phối; mỗi thành phần nhận thông báo vẫn phải có đường lấy dữ liệu đúng phạm vi.

## 8. Kiểm soát các đường truy cập gián tiếp

Chỉ kiểm tra `get secrets` sẽ bỏ sót nhiều khả năng tiếp cận dữ liệu:

| Khả năng được cấp | Tác động cần đánh giá |
| --- | --- |
| Tạo Pod hoặc workload quản lý Pod | Có thể đưa tham chiếu Secret vào Pod mới |
| Sửa Deployment hoặc Pod template | Có thể thay image, thêm mount hoặc thay lệnh để lấy dữ liệu |
| Exec/attach vào container | Có thể tiếp cận file, biến môi trường hoặc trạng thái của ứng dụng |
| Đọc log hoặc artifact chẩn đoán | Có thể thấy credential nếu ứng dụng đã ghi hoặc dump ra đó |
| Sửa RBAC hoặc mạo danh danh tính mạnh hơn | Có thể mở rộng quyền truy cập của chính mình hoặc workload |
| Truy cập node hoặc chạy container đặc quyền | Có thể vượt qua nhiều giới hạn ở tầng workload |

Kubernetes nhấn mạnh rằng quyền tạo workload có thể mở ra quyền tiếp cận các Secret được mount trong namespace; ranh giới bên trong cùng namespace cần được xem xét thận trọng. Vì thế, tách namespace theo miền tin cậy và kiểm soát quyền tạo/sửa workload là một phần của thiết kế Secret. [Kubernetes: RBAC good practices](https://kubernetes.io/docs/concepts/security/rbac-good-practices/).

Trong ví dụ, runtime không cần sửa Deployment, tạo Pod hay chỉnh RoleBinding. Danh tính triển khai và danh tính cấp Secret là các chủ thể riêng; quyền của chúng cũng cần được giới hạn theo công việc thật sự phải làm.

Nếu tổ chức muốn một người được sửa image nhưng không được thay Secret mà workload tham chiếu, chỉ một quyền PATCH Deployment thường chưa diễn đạt đầy đủ ranh giới đó. Cần bổ sung chính sách admission hoặc quy trình triển khai có kiểm soát cho các trường nhạy cảm. Đây là suy luận thiết kế từ quyền điều khiển Pod template, không phải một khả năng deny theo từng trường của RBAC thông thường.

Không coi NetworkPolicy, TLS hoặc mã hóa etcd là cơ chế thay thế quyền đọc. Chúng giải quyết các ranh giới khác nhau. Encryption at rest cần được cấu hình và quản lý khóa đúng cách; nó không ngăn một client đã được API server cho phép đọc Secret. [Kubernetes: Encrypting Confidential Data at Rest](https://kubernetes.io/docs/tasks/administer-cluster/encrypt-data/).

## 9. Bảo vệ dữ liệu sau khi đã nạp vào Spring

Quyền tối thiểu không kết thúc khi request GET thành công hoặc file đã được mount. Credential có thể tiếp tục xuất hiện trong Spring Environment, bean cấu hình, connection pool, log, exception hoặc heap dump.

Những quy ước phù hợp cho `orders`:

- Không log đối tượng cấu hình chứa mật khẩu; tránh `toString()` tự sinh làm lộ trường nhạy cảm.
- Không trả giá trị cấu hình qua endpoint hỗ trợ hoặc response lỗi.
- Không đặt credential trên dòng lệnh chạy Java, trong image hay trong manifest đã chia sẻ.
- Chỉ đưa các key cần dùng vào tiến trình; tránh nhập toàn bộ Secret bằng `envFrom` khi chỉ cần hai key.
- Hạn chế người nhận log, dump và artifact chẩn đoán theo nhu cầu hỗ trợ thực tế.
- Theo dõi trạng thái nạp cấu hình và kết nối bằng dữ liệu không chứa giá trị bí mật.

Base64 chỉ là cách mã hóa biểu diễn, không tạo ra tính bí mật. Việc commit trường `data` đã base64 hoặc `stringData` dạng rõ vẫn làm credential có thể bị người đọc repository tiếp cận. [Kubernetes: Good practices for Kubernetes Secrets](https://kubernetes.io/docs/concepts/security/secrets-good-practices/).

Một cấu hình Actuator minh họa cho ứng dụng chỉ cần công khai health qua HTTP:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health
  endpoint:
    env:
      show-values: never
    configprops:
      show-values: never
```

`show-values: never` giữ việc che giá trị cho các endpoint tương ứng; danh sách exposure giới hạn endpoint HTTP được đưa ra. Cần kiểm tra các kênh JMX, endpoint tùy biến và cơ chế xác thực/phân quyền riêng của ứng dụng. Che giá trị không thay thế kiểm soát quyền truy cập endpoint. [Spring Boot: Actuator endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html).

Trong phương án volume, ứng dụng có thể ánh xạ `db.username` và `db.password` sang cấu hình datasource phù hợp mà không cung cấp giá trị mặc định. Nếu dùng bean cấu hình để kiểm tra tính đầy đủ, thông báo lỗi chỉ nên nêu tên thuộc tính thiếu, không đưa giá trị nhận được vào exception.

## 10. Kiểm chứng quyền hiệu lực mà không in Secret

### 10.1. Điều kiện của phép kiểm tra

Các lệnh dưới đây dùng impersonation để kiểm tra danh tính ứng dụng. Người chạy phải có quyền impersonate user và các nhóm tương ứng. Ví dụ mô phỏng các nhóm chuẩn của ServiceAccount; đối chiếu với cơ chế danh tính thực tế của cluster khi diễn giải kết quả.

`kubectl auth can-i` hỏi hệ thống phân quyền về một hành động, không cần xuất nội dung Secret. Kết quả cho phép không chứng minh object đang tồn tại, credential còn hiệu lực ở cơ sở dữ liệu hoặc ứng dụng thực sự gửi cùng loại request. [Kubernetes: kubectl auth can-i](https://kubernetes.io/docs/reference/kubectl/generated/kubectl_auth/kubectl_auth_can-i/).

### 10.2. Phương án GET: kiểm tra cả quyền cần có và quyền ngoài phạm vi

Ví dụ PowerShell:

```powershell
$identityArgs = @(
    '--as=system:serviceaccount:payments:orders-api-reader'
    '--as-group=system:serviceaccounts'
    '--as-group=system:serviceaccounts:payments'
    '--as-group=system:authenticated'
)

kubectl auth can-i get secrets/orders-db-runtime -n payments @identityArgs
kubectl auth can-i get secrets/orders-db-migrator -n payments @identityArgs
kubectl auth can-i list secrets -n payments @identityArgs
kubectl auth can-i watch secrets -n payments @identityArgs
kubectl auth can-i patch secrets/orders-db-runtime -n payments @identityArgs
kubectl auth can-i get secrets/orders-db-runtime -n another-team @identityArgs
kubectl auth can-i create pods -n payments @identityArgs
kubectl auth can-i patch deployments.apps -n payments @identityArgs
kubectl auth can-i create rolebindings.rbac.authorization.k8s.io -n payments @identityArgs
```

Khi chỉ có đúng quyền theo hợp đồng GET của bài, kết quả mong đợi là:

| Hành động | Kết quả mong đợi |
| --- | --- |
| GET `payments/orders-db-runtime` | `yes` |
| GET `payments/orders-db-migrator` | `no` |
| LIST/WATCH Secret của namespace | `no` |
| PATCH Secret runtime | `no` |
| GET Secret trong `another-team` | `no` |
| Tạo Pod, sửa Deployment, tạo RoleBinding | `no` |

Các câu trả lời `no` ở đây là kết quả chủ đích của phép kiểm tra, thường đi kèm exit code khác 0 của lệnh. Không xử lý mọi exit code đó thành lỗi của môi trường kiểm thử.

Nếu hành động ngoài phạm vi trả `yes`, kiểm tra các binding đang cấp thêm quyền. Tên một Role hẹp không đủ giải thích toàn bộ quyền của danh tính. Người vận hành có quyền phù hợp có thể xem metadata và rules của Role/RoleBinding/ClusterRoleBinding mà không xuất dữ liệu Secret.

### 10.3. Phương án volume: GET API bị từ chối vẫn có thể là kết quả đúng

```powershell
$mountIdentityArgs = @(
    '--as=system:serviceaccount:payments:orders-runtime'
    '--as-group=system:serviceaccounts'
    '--as-group=system:serviceaccounts:payments'
    '--as-group=system:authenticated'
)

kubectl auth can-i get secrets/orders-db-runtime -n payments @mountIdentityArgs
kubectl auth can-i list secrets -n payments @mountIdentityArgs
```

Kết quả mong đợi của cả hai lệnh là `no` trong mô hình không cấp quyền Secret API. Sau đó kiểm chứng riêng rằng container vẫn nạp được thuộc tính cần thiết từ volume và thực hiện được một thao tác cơ sở dữ liệu hợp lệ với quyền runtime.

Không dùng `kubectl get secret -o yaml`, `printenv`, `cat` file mật khẩu hay endpoint trả credential làm bước xác minh mặc định. Có thể chứng minh chức năng bằng trạng thái cấu hình đầy đủ và kết quả kết nối, đồng thời chứng minh phạm vi quyền bằng các hành động không được phép.

`can-i` kiểm tra lớp API authorization; nó không chứng minh quyền đọc file, giới hạn admission theo từng trường hoặc khả năng quan sát dữ liệu đã nằm trong bộ nhớ. Các ranh giới đó cần được kiểm chứng tại đúng lớp.

### 10.4. Đối chiếu audit với hành vi thật của client

Khi có quyền quan sát audit của cluster, tìm theo danh tính ServiceAccount, verb, namespace, resource và tên object. Nếu client cần GET một tên nhưng audit cho thấy LIST nhiều Secret, đó là sai khác quan trọng giữa hợp đồng và triển khai.

Đối với Secret, mức audit `Metadata` ghi thông tin thao tác mà không ghi body request/response. Người quản trị cần bố trí quy tắc này trước quy tắc rộng hơn có thể ghi body, vì thứ tự policy có ý nghĩa. [Kubernetes: Auditing](https://kubernetes.io/docs/tasks/debug/debug-cluster/audit/).

Ví dụ phần rule để tích hợp vào audit policy đang được quản lý:

```yaml
- level: Metadata
  namespaces:
    - payments
  resources:
    - group: ""
      resources:
        - secrets
```

Đây là một phần của danh sách `rules`, không phải toàn bộ cấu hình bật audit cho API server. Việc ghi nhận audit còn phụ thuộc cấu hình và khả năng của môi trường vận hành.

Với volume, ứng dụng đọc file không tạo một request API Secret mới cho từng lần sử dụng credential. Vì thế, audit API không phải nhật ký của mọi lần đọc file hoặc mọi truy vấn cơ sở dữ liệu. Khi điều tra, ghép đúng lớp dữ liệu thay vì kết luận “không có GET của ứng dụng nên ứng dụng không biết Secret”.

## 11. Xoay vòng và thu hồi: quyền nhỏ phải đi cùng thời gian nhỏ

Phân biệt ba sự kiện:

1. Giá trị Secret trong Kubernetes đã đổi.
2. Ứng dụng đã nạp và sử dụng credential mới.
3. Credential cũ đã bị thu hồi tại hệ thống đích.

Ba sự kiện này không xảy ra đồng thời chỉ vì một lệnh cập nhật Secret thành công.

Kubernetes có thể cập nhật dữ liệu của Secret volume theo cơ chế đồng bộ; mount bằng `subPath` không nhận cập nhật tự động theo cách đó. Giá trị đưa vào biến môi trường của container đang chạy cũng không tự đổi khi Secret được sửa. [Kubernetes: Secrets](https://kubernetes.io/docs/concepts/configuration/secret/), [Distribute Credentials Securely Using Secrets](https://kubernetes.io/docs/tasks/inject-data-application/distribute-credentials-secure/).

Ngay cả khi file đã đổi, một bean hoặc connection pool có thể vẫn giữ credential cũ. Cần chọn cơ chế nạp lại hoặc rollout phù hợp với loại thành phần, rồi xác minh kết nối mới thực sự dùng credential mới. Đừng đồng nhất “đã có sự kiện refresh” với “mọi connection đã đổi credential”.

Quy trình minh họa cho `orders`:

| Bước | Bằng chứng cần có |
| --- | --- |
| Chuẩn bị credential mới với quyền runtime | Quyền tại cơ sở dữ liệu được giới hạn đúng công việc |
| Cấp phiên bản Secret mới theo quy trình | Đúng object/namespace và đúng tập người nhận |
| Cập nhật tiến trình hoặc thành phần giữ credential | Các replica chuyển sang phiên bản cấu hình mong muốn |
| Kiểm chứng chức năng | Thao tác hợp lệ thành công; hành động ngoài quyền runtime vẫn bị từ chối |
| Thu hồi credential cũ | Credential cũ không còn dùng được tại hệ thống đích |
| Thu dọn quyền tạm thời | Không để lại Secret hoặc binding mở rộng sau chuyển đổi |

Nếu dùng tên Secret có phiên bản, cập nhật tham chiếu và allowlist tên trong Role tương ứng, rồi bỏ quyền với tên cũ sau giai đoạn chuyển tiếp đã định. Không chuyển sang quyền mọi Secret chỉ để tránh phải quản lý allowlist.

Xóa RoleBinding ngăn những lần lấy dữ liệu tiếp theo theo quyền đó, nhưng không xóa bản sao credential đã nằm trong file, biến môi trường hoặc bộ nhớ tiến trình. Tương tự, xóa Secret không tự vô hiệu hóa mật khẩu ở cơ sở dữ liệu. Thu hồi phải được thực hiện tại nguồn có thẩm quyền, cùng xử lý các bản sao và tiến trình liên quan.

## 12. Thực hành và xử lý sai khác

### 12.1. Bài thực hành trong namespace thử nghiệm

Chuẩn bị Secret runtime và Secret migration bằng dữ liệu giả thông qua công cụ cấp phát của lab. Không dùng credential thật và không thêm giá trị vào repository bài học.

Thực hiện từng phương án riêng để dễ nhận diện danh tính và đường dữ liệu:

1. Triển khai phương án volume với `orders-runtime`, chưa cấp quyền Secret API.
2. Kiểm chứng ứng dụng nhận đủ hai thuộc tính cần thiết và kết nối được bằng tài khoản runtime.
3. Kiểm tra GET/LIST Secret của danh tính runtime đều nằm ngoài phạm vi.
4. Với một deployment thử nghiệm riêng, áp dụng phương án GET cho `orders-api-reader` và client đúng hợp đồng.
5. Chạy ma trận quyền để xác nhận chỉ GET Secret runtime trong `payments` được cho phép.
6. Quan sát request thực tế lúc khởi động, khi cấu hình thay đổi và khi kết nối được khôi phục; tìm các lần LIST/WATCH hoặc tên Secret ngoài dự kiến.
7. Xoay vòng credential giả, xác nhận các replica hội tụ và credential cũ không còn dùng được tại đích.

Nếu cần kiểm tra việc chặn quyền gián tiếp, chỉ dùng workload và credential giả trong lab. Mục tiêu là chứng minh runtime không có các khả năng tạo/sửa workload hoặc cấp thêm quyền, không phải thử trích xuất Secret của workload khác.

### 12.2. Diễn giải lỗi theo đúng lớp

| Hiện tượng | Câu hỏi cần kiểm tra | Hướng xử lý |
| --- | --- | --- |
| Ứng dụng đọc API nhận 403 | Danh tính, namespace, verb và tên object có đúng hợp đồng không? | Sửa điểm sai cụ thể; không cấp wildcard |
| Client gọi LIST dù đã cấu hình tên | Có batch, informer, nguồn bổ sung hoặc cấu hình hiệu lực khác không? | Chọn cách đọc phù hợp hoặc đổi đường nhận dữ liệu |
| Volume không được tạo | Secret/key có tồn tại đúng namespace không? | Kiểm tra tham chiếu và provisioning; quyền GET của ứng dụng không sửa lỗi này |
| File có nhưng ứng dụng không đọc được | UID/GID, mode và mount có phù hợp không? | Điều chỉnh quyền file theo nhu cầu của tiến trình |
| Có file nhưng Spring thiếu thuộc tính | Đường import, tên file và giai đoạn cấu hình có đúng không? | Sửa ánh xạ, không thêm quyền API nếu không dùng API |
| `can-i` trả `yes` cho Secret ngoài phạm vi | Binding hoặc nhóm nào đang cấp thêm quyền? | Thu hẹp quyền hiệu lực sau khi xác định nguồn cấp |
| Secret đã đổi nhưng kết nối vẫn dùng credential cũ | Bean/pool/biến môi trường đã được cập nhật chưa? | Thực hiện cơ chế nạp lại hoặc rollout và kiểm chứng tại đích |
| Đã gỡ quyền API nhưng credential cũ vẫn hoạt động | Credential ở hệ thống đích đã bị thu hồi chưa? | Thu hồi và xử lý bản sao còn tồn tại |

Một cấu hình đạt mục tiêu khi có đủ bằng chứng: ứng dụng làm được công việc hợp lệ, hành động ngoài phạm vi bị chặn tại lớp phù hợp, các request thực tế khớp hợp đồng và việc xoay vòng không để lại credential cũ còn hiệu lực ngoài thời gian cho phép.
