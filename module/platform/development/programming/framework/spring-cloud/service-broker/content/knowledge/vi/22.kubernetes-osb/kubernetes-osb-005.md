# Phân phối credentials bằng Secret và ánh xạ cho workload

Khi tích hợp Open Service Broker API (OSB API) với Kubernetes, broker có thể cấp credentials cho một service binding, chẳng hạn username/password của PostgreSQL, token truy cập Redis hoặc thông tin kết nối tới một dịch vụ nội bộ. Ứng dụng chạy trong Pod cần nhận được những credentials này để kết nối tới backing service. Kubernetes Secret là một cơ chế phổ biến để lưu và phân phối dữ liệu nhạy cảm cho workload.

Luồng tích hợp thường gồm ba phần: platform hoặc controller gửi yêu cầu bind tới broker; broker tạo credentials và trả binding response theo OSB API; lớp tích hợp Kubernetes chuyển credentials thành Secret trong đúng namespace rồi ánh xạ Secret vào Pod hoặc workload. Khi binding bị thu hồi hoặc credentials được xoay vòng, controller phải đồng bộ lại Secret và cấu hình workload theo vòng đời tương ứng.

Secret giúp tách dữ liệu nhạy cảm khỏi image và manifest ứng dụng, nhưng bản thân Secret không tự bảo đảm mọi dữ liệu đã được mã hóa, phân quyền đúng hoặc tự động xoay vòng. Một triển khai an toàn cần kết hợp namespace isolation, RBAC, mã hóa etcd, kiểm soát quyền đọc Secret, quy trình rotation/revocation và cơ chế tích hợp phù hợp.

Bài học này trình bày cách chuyển credentials từ OSB binding sang Kubernetes Secret, cách đặt tên và quản lý Secret, cách ánh xạ Secret vào Deployment/StatefulSet, cách xoay vòng và thu hồi credentials, cùng những lựa chọn như External Secrets Operator và Secrets Store CSI Driver.

## 1. Vai trò của Secret trong mô hình OSB trên Kubernetes

OSB API định nghĩa service binding để broker trả thông tin cho consumer. Với binding database thông thường, response có thể chứa credentials:

~~~json
{
  "credentials": {
    "hostname": "postgres.database.svc",
    "port": 5432,
    "database": "orders",
    "username": "orders_app",
    "password": "example-secret"
  }
}
~~~

Trong mô hình Cloud Foundry, platform có thể cung cấp binding credentials cho ứng dụng dưới dạng environment variables hoặc file. Với Kubernetes, một integration controller có thể nhận binding response rồi tạo Kubernetes Secret trong namespace chứa workload.

Kubernetes Secret là object namespaced lưu các key/value nhạy cảm. Pod có thể tiêu thụ Secret thông qua:

- Environment variables.
- Volume mount.
- Projected volume.
- Một controller hoặc sidecar đọc Secret từ Kubernetes API.
- External secret provider hoặc CSI driver, tùy kiến trúc.

Luồng khái quát:

~~~mermaid
sequenceDiagram
    participant W as Workload owner
    participant C as Kubernetes integration controller
    participant B as OSB Service Broker
    participant K as Kubernetes API
    participant P as Pod
    W->>C: Yêu cầu tạo ServiceBinding
    C->>B: OSB PUT service_bindings
    B-->>C: Binding response + credentials
    C->>K: Tạo Secret trong namespace
    K-->>C: Secret reference
    C->>K: Cập nhật Deployment/StatefulSet
    K-->>P: Cung cấp Secret qua env hoặc volume
    P->>B: Kết nối backing service bằng credentials
~~~

Controller có thể được triển khai dưới dạng operator, controller riêng hoặc thành phần platform. OSB API không tự định nghĩa một Kubernetes Secret object; việc chuyển đổi binding response thành Secret là trách nhiệm của lớp tích hợp.

## 2. Ranh giới trách nhiệm giữa broker, controller và workload

Nên tách rõ ai sở hữu từng phần của luồng:

| Thành phần | Trách nhiệm |
|---|---|
| OSB service broker | Tạo, quản lý và thu hồi binding credentials; trả binding response |
| Kubernetes integration controller | Gọi broker, quản lý binding state, tạo/cập nhật/xóa Secret và tham chiếu workload |
| Kubernetes API server | Xác thực request, áp dụng RBAC/admission và lưu object |
| etcd | Lưu trạng thái cluster, bao gồm Secret theo cấu hình cluster |
| Kubelet | Cung cấp Secret cho Pod theo cơ chế volume hoặc environment |
| Workload | Đọc credentials và sử dụng để kết nối backing service |
| External secret manager | Lưu hoặc phát hành secret bên ngoài Kubernetes nếu kiến trúc sử dụng |

Broker không nhất thiết cần quyền truy cập trực tiếp vào Kubernetes API. Trong nhiều kiến trúc, controller là client OSB và Kubernetes API cùng lúc. Cách này giúp credential của broker/provider không phải kiêm thêm quyền quản trị toàn cluster.

Nếu broker trực tiếp tạo Secret, phải giới hạn quyền tới namespace và loại object cần thiết. Không cấp cluster-admin chỉ để tạo một Secret.

## 3. Kubernetes Secret lưu dữ liệu như thế nào?

Một Secret cơ bản có thể dùng trường data hoặc stringData.

- data chứa giá trị dạng Base64 trong biểu diễn YAML/JSON.
- stringData cho phép khai báo chuỗi rõ trong request; API server chuyển chúng thành data khi lưu.
- type mô tả loại Secret, ví dụ Opaque hoặc một type chuyên biệt.

Ví dụ Secret Opaque:

~~~yaml
apiVersion: v1
kind: Secret
metadata:
  name: orders-db-binding
  namespace: orders
type: Opaque
stringData:
  hostname: postgres.database.svc
  port: "5432"
  database: orders
  username: orders_app
  password: example-secret
~~~

Ví dụ trên chỉ minh họa cấu trúc. Không commit password thật vào Git hoặc manifest được lưu trong repository. Nếu tạo Secret bằng kubectl hoặc controller, dữ liệu nên đến từ binding response qua một kênh bảo vệ và chỉ tồn tại trong bộ nhớ trong thời gian cần thiết.

Base64 không phải mã hóa. Người có quyền đọc Secret có thể decode giá trị data. Do đó, không coi việc chuyển password thành Base64 là biện pháp bảo vệ.

Secret Opaque phù hợp cho tập key/value do ứng dụng định nghĩa. Không nên chọn các type như kubernetes.io/tls hoặc kubernetes.io/dockerconfigjson nếu dữ liệu binding không tuân theo schema tương ứng.

## 4. Chuyển binding credentials thành Secret

Controller cần chuyển đổi binding response thành các key có tên ổn định, phù hợp với ứng dụng. Ví dụ mapping:

| Binding response key | Secret key | Mục đích |
|---|---|---|
| hostname | host | Host của database |
| port | port | Cổng kết nối |
| database | database | Tên database |
| username | username | Tài khoản |
| password | password | Mật khẩu |
| uri | connection-uri | URI kết nối nếu broker cung cấp |

Không nên sao chép mọi field trong binding response một cách mù quáng. Controller cần schema mapping theo service hoặc plan, loại bỏ metadata không cần thiết và không đưa dữ liệu nhạy cảm vào annotation hoặc label.

Một Secret có thể lưu từng field riêng để workload tự ghép connection string. Cách khác là lưu một key connection-uri. Chọn cách nào phụ thuộc vào framework ứng dụng và khả năng xử lý secret. Nếu URI chứa password, nó vẫn là dữ liệu nhạy cảm và cần cùng mức bảo vệ.

Nên thống nhất key names và encoding giữa các phiên bản chart/operator để ứng dụng không bị hỏng khi controller nâng cấp.

## 5. Đặt tên và định danh Secret theo binding

Một service instance có thể có nhiều binding cho nhiều workload. Vì vậy, không nên chỉ dùng service instance ID làm tên Secret nếu mỗi binding có credentials riêng.

Một quy tắc tên có thể dựa trên binding ID:

~~~text
<service-name>-<binding-id-suffix>
~~~

Ví dụ:

~~~text
orders-db-bind-7f2a
orders-db-bind-a91c
~~~

Tên object cần tuân thủ quy tắc DNS label của Kubernetes. Nếu binding ID chứa ký tự không hợp lệ hoặc quá dài, controller nên tạo suffix ổn định bằng cách chuẩn hóa hoặc hash một phần ID. Không dùng secret value để tạo tên.

Metadata có thể chứa các tham chiếu không nhạy cảm:

~~~yaml
metadata:
  labels:
    app.kubernetes.io/managed-by: service-binding-controller
    broker.example.com/service-instance: instance-123
    broker.example.com/binding-ref: binding-456
  annotations:
    broker.example.com/credential-version: "3"
~~~

Không đặt username/password/token vào label hoặc annotation. Metadata thường được trả trong list/watch và có thể được nhiều thành phần đọc hơn data của Secret. Nếu ID nội bộ được xem là nhạy cảm, hãy dùng reference đã rút gọn hoặc mã hóa phù hợp với chính sách.

## 6. Namespace isolation và phạm vi Secret

Secret là tài nguyên namespaced. Pod chỉ có thể tham chiếu Secret trong cùng namespace. Một Secret trong namespace orders không thể được Pod ở namespace payments tham chiếu trực tiếp.

Đây là ranh giới hữu ích để tách workload theo tenant hoặc môi trường:

~~~text
Namespace orders
  - Deployment orders-api
  - Secret orders-db-binding

Namespace payments
  - Deployment payments-api
  - Secret payments-db-binding
~~~

Controller cần xác định namespace đích từ workload hoặc Kubernetes object đã được xác thực. Không tin một namespace tùy ý trong request nếu caller không có quyền trên namespace đó.

Các câu hỏi cần trả lời:

- Namespace do ai tạo và quản lý?
- Một tenant có thể có nhiều namespace không?
- Một binding có được dùng bởi nhiều workload trong cùng namespace không?
- Có cho phép chia sẻ Secret giữa các ứng dụng không?
- Ai được đọc Secret: Pod service account, controller hay operator?
- Khi namespace bị xóa, controller xử lý binding OSB ra sao?

Không nên gom credentials của nhiều tenant vào một namespace dùng chung nếu không có ranh giới RBAC rõ ràng. Namespace isolation là một lớp phân tách, nhưng không tự thay thế authorization, network policy hoặc chính sách quản trị cluster.

## 7. Ánh xạ Secret vào Deployment bằng environment variables

Một cách phổ biến là tham chiếu key của Secret trong env hoặc envFrom.

Ví dụ dùng env:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders-api
  namespace: orders
spec:
  replicas: 2
  selector:
    matchLabels:
      app: orders-api
  template:
    metadata:
      labels:
        app: orders-api
    spec:
      containers:
        - name: app
          image: example/orders-api:1.0
          env:
            - name: DB_HOST
              valueFrom:
                secretKeyRef:
                  name: orders-db-binding
                  key: host
            - name: DB_USERNAME
              valueFrom:
                secretKeyRef:
                  name: orders-db-binding
                  key: username
            - name: DB_PASSWORD
              valueFrom:
                secretKeyRef:
                  name: orders-db-binding
                  key: password
~~~

Kubernetes đưa giá trị Secret vào environment của container khi container được tạo. Một thay đổi Secret không tự cập nhật environment của container đang chạy. Workload thường cần được restart hoặc rollout để nhận giá trị mới.

Cách env phù hợp với ứng dụng đọc cấu hình lúc khởi động. Nếu ứng dụng cần rotation mà không restart, environment variables thường không phải lựa chọn tốt.

Không nên dùng envFrom một cách rộng nếu Secret có nhiều key không liên quan. Khai báo từng key giúp kiểm soát chính xác biến nào được đưa vào container.

## 8. Ánh xạ Secret vào Pod bằng volume mount

Secret có thể được mount thành file trong container:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders-api
  namespace: orders
spec:
  replicas: 2
  selector:
    matchLabels:
      app: orders-api
  template:
    metadata:
      labels:
        app: orders-api
    spec:
      containers:
        - name: app
          image: example/orders-api:1.0
          volumeMounts:
            - name: database-credentials
              mountPath: /var/run/secrets/database
              readOnly: true
      volumes:
        - name: database-credentials
          secret:
            secretName: orders-db-binding
            defaultMode: 0400
            items:
              - key: username
                path: username
              - key: password
                path: password
              - key: host
                path: host
~~~

Ứng dụng có thể đọc các file trong thư mục mount thay vì nhận secret qua environment. Volume mount phù hợp với ứng dụng hỗ trợ reload file hoặc đọc credential từ filesystem.

Kubernetes cập nhật nội dung Secret volume theo cơ chế eventual consistency. Tuy nhiên:

- Ứng dụng phải đọc lại file để nhận giá trị mới.
- Mount bằng subPath không nhận cập nhật Secret tự động.
- Ứng dụng có thể cần reload connection pool hoặc khởi tạo lại client.
- Nếu dùng immutable Secret, cần tạo Secret mới và cập nhật Pod template.

Không giả định volume update đồng nghĩa ứng dụng đã sử dụng credentials mới. Cần có readiness/health check và quy trình rotation xác minh kết nối sau thay đổi.

## 9. Ánh xạ Secret cho StatefulSet và các workload khác

Không chỉ Deployment mới dùng Secret. StatefulSet, DaemonSet, Job và CronJob cũng có thể tham chiếu Secret trong Pod template.

Ví dụ StatefulSet cho database client:

~~~yaml
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: report-worker
  namespace: analytics
spec:
  serviceName: report-worker
  replicas: 2
  selector:
    matchLabels:
      app: report-worker
  template:
    metadata:
      labels:
        app: report-worker
    spec:
      containers:
        - name: worker
          image: example/report-worker:1.0
          env:
            - name: DB_PASSWORD
              valueFrom:
                secretKeyRef:
                  name: analytics-db-binding
                  key: password
~~~

Với Job hoặc CronJob, cần đảm bảo Secret tồn tại trước khi Pod được tạo. Nếu binding bị unbind trong khi Job vẫn đang chạy, controller cần xác định có thu hồi credential ngay hay đợi workload kết thúc theo chính sách.

Với nhiều workload dùng cùng binding, controller cần quản lý tập tham chiếu để không xóa Secret khi một workload vẫn còn sử dụng. Ngược lại, nếu mỗi workload có binding riêng, mỗi Secret cần được thu hồi theo đúng binding tương ứng.

## 10. Tích hợp ServiceBinding controller hoặc operator

Kubernetes không tự động chuyển OSB binding response thành Secret chỉ vì broker tuân thủ OSB API. Cần một thành phần điều phối. Một lựa chọn là controller/operator quản lý custom resource mô tả mong muốn binding.

Ví dụ custom resource minh họa:

~~~yaml
apiVersion: servicebinding.example.com/v1alpha1
kind: ServiceBinding
metadata:
  name: orders-database
  namespace: orders
spec:
  serviceInstanceRef:
    name: orders-postgres
  workload:
    apiVersion: apps/v1
    kind: Deployment
    name: orders-api
  secretName: orders-db-binding
~~~

Đây là CRD minh họa của một integration layer, không phải resource chuẩn mặc định của Kubernetes hoặc OSB API. Controller reconcile resource này theo các bước:

1. Đọc ServiceBinding và xác minh namespace/workload.
2. Tra cứu service instance reference.
3. Gọi OSB bind nếu chưa có binding hợp lệ.
4. Lưu binding ID và operation state.
5. Tạo hoặc cập nhật Secret.
6. Cập nhật Pod template hoặc workload reference.
7. Theo dõi trạng thái và điều kiện Ready.
8. Khi resource bị xóa, gọi unbind và xử lý Secret theo finalizer.

Controller nên idempotent. Reconcile có thể chạy nhiều lần do watch event, restart hoặc resync. Mỗi lần chạy phải kiểm tra trạng thái broker và Kubernetes trước khi tạo mới, tránh tạo binding hoặc Secret trùng.

## 11. Vòng đời binding và Secret

Secret là bản sao credentials ở phía Kubernetes. Nó có vòng đời liên quan đến binding nhưng không nhất thiết đồng nhất hoàn toàn với binding.

| Sự kiện | Broker | Kubernetes controller |
|---|---|---|
| Bind mới | Tạo credentials và binding record | Tạo Secret và tham chiếu workload |
| Reconcile lại | Trả binding hiện có hoặc trạng thái tương ứng | Kiểm tra Secret và workload, sửa drift |
| Rotation | Phát hành credential mới hoặc cập nhật credential | Cập nhật Secret, rollout/reload workload |
| Unbind | Thu hồi binding/credential | Xóa hoặc vô hiệu hóa Secret và gỡ tham chiếu |
| Deprovision | Xóa service instance theo policy | Xử lý binding còn lại và Secret liên quan |
| Namespace deletion | Không tự động biết nếu không có integration | Controller phát hiện và thực hiện cleanup/finalizer |

Không nên xóa Secret trước khi xác định broker đã thu hồi hoặc thay thế credentials theo đúng thứ tự. Nếu xóa Secret quá sớm, workload có thể mất khả năng khởi động lại trong khi binding vẫn còn hiệu lực.

Ngược lại, giữ Secret sau unbind có thể để lại credential không còn cần thiết trong cluster. Controller cần có cleanup policy và retry nếu Kubernetes API hoặc broker tạm thời không sẵn sàng.

## 12. Rotation credentials

Credentials có thể cần xoay vòng do chính sách bảo mật, nghi ngờ lộ secret hoặc thời hạn credential. Rotation thường gồm hai phía:

1. Broker hoặc provider phát hành credential mới.
2. Kubernetes Secret được cập nhật.
3. Workload nhận credential mới.
4. Broker/provider xác minh credential mới hoạt động.
5. Credential cũ được thu hồi.

Nếu provider hỗ trợ hai credential đồng thời, có thể dùng quy trình overlap:

~~~mermaid
sequenceDiagram
    participant B as Broker/Provider
    participant C as Binding Controller
    participant S as Kubernetes Secret
    participant W as Workload
    B->>B: Tạo credential mới
    C->>B: Lấy binding credentials mới
    B-->>C: Credential version N+1
    C->>S: Cập nhật Secret
    C->>W: Rollout hoặc trigger reload
    W->>B: Kết nối bằng credential mới
    B-->>W: Xác thực thành công
    C->>B: Thu hồi credential cũ
~~~

Nếu provider chỉ cho phép một password tại một thời điểm, rotation có thể gây gián đoạn nếu đổi password trước khi workload cập nhật. Cần thiết kế thứ tự hoặc maintenance window phù hợp.

Không nên chỉ cập nhật Secret rồi coi rotation đã hoàn tất. Cần xác minh workload đã nhận và dùng credential mới; có thể theo dõi rollout status, readiness và kết quả kết nối.

## 13. Secret immutable và chiến lược versioned Secret

Kubernetes cho phép Secret có trường immutable. Khi đặt immutable: true, data không thể được sửa sau khi tạo. Điều này giảm một số thao tác thay đổi ngoài ý muốn nhưng cần chiến lược rotation khác.

Có thể tạo Secret version mới:

~~~text
orders-db-binding-v1
orders-db-binding-v2
orders-db-binding-v3
~~~

Controller cập nhật Pod template để tham chiếu Secret mới, sau đó đợi rollout thành công rồi mới xóa Secret cũ theo retention policy.

Có thể dùng annotation version hoặc hash của dữ liệu đã được bảo vệ để kích hoạt rollout. Không đưa giá trị secret vào annotation để tạo checksum; nếu cần checksum, phải dùng cách không làm lộ secret và đánh giá khả năng dò đoán. Một phương án là tăng version number do controller quản lý.

Versioned Secret giúp rollback workload trong thời gian ngắn nếu credential cũ còn hiệu lực. Tuy nhiên, không giữ credential cũ lâu hơn chính sách cho phép. Sau khi xác minh workload mới hoạt động, broker/provider nên thu hồi credential cũ và controller dọn Secret version cũ.

## 14. RBAC: ai được đọc Secret?

Kubernetes RBAC kiểm soát ai có thể get, list, watch, create, update, patch hoặc delete Secret. Quyền list/watch có thể cho phép đọc nhiều Secret trong namespace, do đó cần hạn chế chặt.

Ví dụ Role chỉ cho phép controller quản lý một số Secret trong namespace:

~~~yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: service-binding-secret-manager
  namespace: orders
rules:
  - apiGroups: [""]
    resources: ["secrets"]
    resourceNames: ["orders-db-binding"]
    verbs: ["get", "update", "patch"]
  - apiGroups: [""]
    resources: ["secrets"]
    verbs: ["create"]
~~~

Lưu ý: Kubernetes RBAC có hạn chế khi dùng resourceNames cho thao tác create vì request tạo object chưa có tên resource được authorize theo cách tương tự get/update. Cần thiết kế quyền create theo namespace và admission policy hoặc controller policy để giới hạn tên/label nếu cần. Không cấp quyền list/watch toàn bộ Secret chỉ để controller kiểm tra một binding.

Một số nguyên tắc:

- Dùng ServiceAccount riêng cho controller.
- Chỉ cấp quyền trên namespace được quản lý.
- Tách quyền tạo Secret khỏi quyền đọc tất cả Secret.
- Không cấp quyền đọc Secret cho mọi workload service account.
- Pod không cần Kubernetes API access thì tắt automount service account token khi phù hợp.
- Kiểm tra RoleBinding/ClusterRoleBinding và quyền kế thừa.
- Audit các thao tác get/list/watch Secret.

RBAC bảo vệ API access, nhưng Pod được mount Secret vẫn có thể đọc dữ liệu trong container. Vì vậy, quyền truy cập filesystem và quyền điều khiển workload cũng là một phần của mô hình bảo mật.

## 15. Mã hóa Secret khi lưu trong etcd

Mặc định, nội dung Secret được Base64 encode trong API representation. Nếu cluster không cấu hình encryption at rest, dữ liệu Secret có thể được lưu trong etcd mà không được mã hóa ở tầng storage.

Nên bật encryption at rest cho Kubernetes Secrets bằng EncryptionConfiguration phù hợp với phiên bản cluster. Có thể dùng provider mã hóa như aescbc hoặc tích hợp KMS tùy cấu hình và phiên bản Kubernetes. Quản lý key mã hóa cần có quy trình backup, rotation và kiểm soát quyền.

Các điểm cần kiểm tra:

- Encryption provider đã áp dụng cho resource secrets.
- Key encryption được lưu và bảo vệ ngoài etcd.
- Có quy trình rotate key và re-encrypt dữ liệu hiện có.
- Backup etcd được mã hóa và quyền truy cập bị giới hạn.
- KMS availability không làm mất khả năng đọc Secret trong quá trình vận hành.
- Test restore trên môi trường kiểm soát.

Encryption at rest không bảo vệ Secret khỏi principal có quyền đọc qua Kubernetes API hoặc Pod đã được cấp mount. Cần kết hợp RBAC, namespace isolation, node security và runtime controls.

## 16. External Secrets Operator

Thay vì để controller OSB ghi credentials trực tiếp vào Kubernetes Secret, có thể lưu credentials trong external secret manager và dùng External Secrets Operator (ESO) đồng bộ vào Kubernetes.

Luồng:

1. Broker hoặc integration controller tạo/nhận credential.
2. Credential được lưu vào secret manager bên ngoài.
3. Controller lưu external secret reference.
4. ESO đọc secret store theo quyền được cấp.
5. ESO tạo hoặc cập nhật Kubernetes Secret.
6. Workload tham chiếu Secret như bình thường.

Ví dụ ExternalSecret minh họa:

~~~yaml
apiVersion: external-secrets.io/v1beta1
kind: ExternalSecret
metadata:
  name: orders-db-binding
  namespace: orders
spec:
  refreshInterval: 1h
  secretStoreRef:
    name: production-secret-store
    kind: SecretStore
  target:
    name: orders-db-binding
    creationPolicy: Owner
  data:
    - secretKey: username
      remoteRef:
        key: broker/orders/database
        property: username
    - secretKey: password
      remoteRef:
        key: broker/orders/database
        property: password
~~~

Ví dụ phụ thuộc phiên bản CRD của ESO và loại secret store được cài đặt. Cần kiểm tra API version và field schema thực tế của release đang dùng.

Ưu điểm của cách này là secret manager bên ngoài có thể cung cấp audit, rotation, policy và quyền truy cập tập trung. Tuy nhiên, controller vẫn phải bảo đảm mapping giữa binding ID và external secret reference; ESO không tự hiểu vòng đời OSB nếu không có integration.

Không đưa credential trực tiếp vào ExternalSecret manifest. Manifest chỉ chứa tham chiếu tới secret store.

## 17. Secrets Store CSI Driver

Một lựa chọn khác là Secrets Store CSI Driver. Driver mount secret từ external provider vào Pod dưới dạng file, có thể tùy cấu hình đồng bộ thành Kubernetes Secret.

Mô hình này phù hợp khi workload có thể đọc credentials từ file và tổ chức muốn tránh lưu bản sao lâu dài trong Kubernetes Secret object.

Ví dụ cấu trúc SecretProviderClass minh họa:

~~~yaml
apiVersion: secrets-store.csi.x-k8s.io/v1
kind: SecretProviderClass
metadata:
  name: orders-db-secrets
  namespace: orders
spec:
  provider: vault
  parameters:
    objects: |
      - objectName: "orders-db-password"
        objectType: "secret"
~~~

Provider parameters và schema cụ thể phụ thuộc provider plugin. Cần tham khảo tài liệu của driver và provider được cài đặt.

Pod mount CSI volume:

~~~yaml
spec:
  containers:
    - name: app
      image: example/orders-api:1.0
      volumeMounts:
        - name: external-secrets
          mountPath: /mnt/secrets
          readOnly: true
  volumes:
    - name: external-secrets
      csi:
        driver: secrets-store.csi.k8s.io
        readOnly: true
        volumeAttributes:
          secretProviderClass: orders-db-secrets
~~~

CSI driver có thể hỗ trợ rotation tùy cấu hình và provider. Ứng dụng vẫn cần đọc lại file hoặc reload kết nối. Nếu đồng bộ secret thành Kubernetes Secret, dữ liệu lại có bản sao trong etcd và cần chính sách mã hóa/RBAC tương ứng.

## 18. Chọn Kubernetes Secret, ESO hay CSI

| Tiêu chí | Kubernetes Secret trực tiếp | External Secrets Operator | Secrets Store CSI Driver |
|---|---|---|---|
| Nơi lưu chính | Kubernetes API/etcd | External secret manager | External secret manager |
| Cách workload nhận | env hoặc volume | Kubernetes Secret được đồng bộ | File qua CSI volume |
| Có bản sao trong etcd | Có | Có nếu target là Secret | Không bắt buộc; có nếu bật sync |
| Rotation | Controller cập nhật Secret | ESO refresh theo policy | Driver/provider rotation tùy hỗ trợ |
| Yêu cầu thành phần | Kubernetes API | ESO và secret store | CSI driver và provider plugin |
| Phù hợp | Hệ thống nhỏ hoặc tích hợp đơn giản | Tổ chức có secret manager tập trung | Workload đọc secret dạng file, muốn giảm bản sao Secret |

Không có lựa chọn nào tự động giải quyết toàn bộ vòng đời binding. Cần xác định ai tạo secret, ai rotate, ai revoke và ai xử lý drift khi một thành phần bị xóa ngoài ý muốn.

## 19. Xử lý unbind và thu hồi Secret

Khi platform hoặc controller yêu cầu unbind, broker thu hồi quyền truy cập hoặc credential theo contract. Kubernetes controller cần gỡ secret khỏi workload và dọn object tương ứng.

Một quy trình có thể là:

1. Đánh dấu binding đang được thu hồi.
2. Gọi broker unbind và chờ kết quả theo cơ chế OSB.
3. Khi broker xác nhận hoặc policy cho phép, cập nhật workload để bỏ tham chiếu Secret.
4. Xóa Kubernetes Secret hoặc ExternalSecret/SecretProviderClass binding-specific.
5. Xác nhận Pod rollout hoặc workload không còn dùng credential cũ.
6. Lưu trạng thái binding UNBOUND và audit event.
7. Retry cleanup nếu Kubernetes API tạm thời lỗi.

Thứ tự có thể khác tùy yêu cầu an toàn. Nếu xóa Secret trước khi broker revoke, một Pod cũ có thể vẫn giữ credentials trong memory; xóa object không làm password cũ mất hiệu lực ở provider. Nếu revoke trước, workload có thể gặp lỗi kết nối ngay cả khi Secret còn tồn tại. Controller cần phối hợp hai phía và không nhầm cleanup object với thu hồi credential thật.

Khi binding được chia sẻ bởi nhiều workload, chỉ xóa Secret sau khi tất cả reference đã được gỡ. Có thể dùng owner reference, label selector hoặc một registry mapping rõ ràng; không dựa vào tên object để suy luận quan hệ.

## 20. Reconcile và xử lý drift

Kubernetes controller hoạt động theo mô hình reconcile: đọc trạng thái mong muốn và trạng thái thực tế, sau đó đưa hệ thống về trạng thái mong muốn. Secret có thể bị xóa thủ công, workload đổi tham chiếu hoặc binding bị thu hồi ngoài luồng.

Controller nên kiểm tra:

- Binding record còn ACTIVE không?
- Secret có tồn tại đúng namespace và đúng binding reference không?
- Secret version có khớp với credential version mong muốn không?
- Workload có tham chiếu Secret đúng không?
- Pod đã rollout để nhận version mới chưa?
- External secret reference còn hợp lệ không?
- Binding đã bị unbind nhưng Secret vẫn còn không?

Reconcile phải idempotent. Nếu Secret đã đúng, không cần ghi lại liên tục. Tránh tạo rollout mới ở mỗi lần reconcile vì sẽ gây restart không cần thiết.

Khi phát hiện drift có thể tự sửa, controller thực hiện cập nhật và ghi condition. Nếu trạng thái broker/provider không rõ, nên dừng hành động phá hủy và chuyển sang trạng thái cần điều tra.

## 21. Bảo vệ dữ liệu trong controller

Controller xử lý binding response thường nhìn thấy credentials dạng rõ. Cần giảm thời gian và phạm vi dữ liệu nhạy cảm tồn tại trong process.

Các nguyên tắc:

- Không log request/response body của OSB bind.
- Không log Kubernetes Secret object hoặc data field.
- Không đưa credential vào event message hoặc annotation.
- Hạn chế cache credentials trong memory.
- Không ghi credentials vào status field của custom resource.
- Không expose debug endpoint có thể dump object hoặc heap.
- Dùng TLS khi gọi broker, Kubernetes API và external secret manager.
- Tách service account và quyền của controller.
- Redact exception message nếu provider/client có thể phản chiếu credential.
- Xóa buffer hoặc tham chiếu không cần thiết ở mức phù hợp với ngôn ngữ/runtime.

Java String là immutable và garbage collection không bảo đảm xóa nội dung ngay lập tức. Do đó, thiết kế tốt nhất là giảm việc copy secret qua nhiều object và không lưu chúng vào log, cache hoặc persistent event payload.

## 22. Multi-tenancy và chia sẻ Secret

Nếu một Kubernetes cluster phục vụ nhiều tenant, cần xác định ranh giới tenant rõ ràng.

Một số mô hình:

- Namespace riêng cho mỗi tenant.
- Namespace riêng cho mỗi ứng dụng hoặc nhóm workload.
- Secret riêng theo binding trong namespace.
- External secret path riêng theo tenant và binding.
- Service account riêng cho controller hoặc workload.

Không dùng một Secret chứa credentials của nhiều tenant. Không cho workload có quyền list toàn bộ Secret trong namespace nếu chỉ cần đọc một Secret cụ thể. Nếu nhiều ứng dụng cùng dùng một binding, cần đánh giá liệu việc chia sẻ credential có làm mất khả năng revoke độc lập hay không.

Tenant context trong OSB request phải được xác minh và ánh xạ sang Kubernetes namespace theo policy. Không cho client tự chọn namespace khác để đọc hoặc ghi Secret. Controller cần kiểm tra owner reference và workload namespace để tránh confused deputy, tức controller bị lợi dụng quyền cao hơn để thao tác tài nguyên tenant khác.

## 23. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân | Hướng xử lý |
|---|---|---|
| Pod không khởi động vì Secret không tồn tại | Controller tạo workload trước Secret hoặc reconcile chưa hoàn tất | Tạo Secret trước và thể hiện trạng thái binding |
| Ứng dụng nhận password cũ sau rotation | Environment variables chỉ được nạp lúc container khởi động | Rollout/restart hoặc dùng file mount có reload |
| Secret bị lộ trong Git | Commit manifest chứa stringData thật | Dùng secret manager và tham chiếu |
| Nghĩ Base64 là mã hóa | Hiểu sai trường data của Secret | Bật encryption at rest và RBAC |
| Controller đọc được mọi Secret | ClusterRole có quyền list/watch rộng | Thu hẹp Role theo namespace và verb |
| Unbind nhưng credential vẫn dùng được | Chỉ xóa Kubernetes Secret mà chưa revoke ở provider | Gọi broker/provider revoke và xác minh |
| Rotation gây downtime | Thu hồi credential cũ trước khi workload dùng credential mới | Dùng overlap hoặc maintenance window |
| Secret mount không cập nhật | Dùng subPath hoặc ứng dụng không reload file | Tránh subPath, triển khai reload/rollout |
| Kubernetes Secret bị tạo trùng | Reconcile không idempotent | Dùng binding ID và deterministic name |
| Secret của tenant khác bị tham chiếu | Không xác minh namespace và ownership | Tenant scoping và namespace validation |
| ESO không cập nhật Secret | External reference, IAM hoặc refresh policy sai | Kiểm tra controller condition và secret store |
| CSI volume mount thất bại | Provider plugin hoặc SecretProviderClass sai | Kiểm tra driver, node plugin và provider logs |

## 24. Kiểm thử tích hợp end-to-end

Một luồng binding cần được kiểm thử từ OSB tới Pod, không chỉ kiểm tra broker trả JSON.

Các trường hợp nên kiểm thử:

1. Tạo binding thành công và xác nhận Secret được tạo đúng namespace.
2. Kiểm tra chỉ các key cho phép được đưa vào Secret.
3. Tạo Deployment tham chiếu Secret và xác nhận container nhận đúng giá trị.
4. Xác nhận credentials không xuất hiện trong application log, controller log, audit hoặc event.
5. Xoay vòng credential và kiểm tra Pod nhận version mới.
6. Kiểm tra workload kết nối được sau rotation.
7. Unbind và xác nhận broker revoke credential cùng controller cleanup Secret.
8. Xóa Secret thủ công để kiểm tra reconcile.
9. Restart controller trong lúc binding đang xử lý.
10. Kiểm tra namespace khác không thể đọc Secret.
11. Kiểm tra service account không có quyền list Secret ngoài phạm vi.
12. Thử phục hồi từ backup etcd hoặc secret manager theo quy trình được quản trị.

Nên dùng credential giả trong test và marker duy nhất để tìm trong log output. Không dùng password production trong fixture hoặc CI.

## 25. Checklist triển khai production

**Binding và Secret mapping**

- [ ] Binding response được validate trước khi tạo Secret.
- [ ] Secret key mapping ổn định và chỉ chứa field cần thiết.
- [ ] Secret name gắn với binding ID, không dùng secret value.
- [ ] Secret được tạo trong namespace đã xác minh.
- [ ] Workload tham chiếu đúng Secret và key.
- [ ] Controller reconcile idempotent và lưu binding state bền vững.

**Bảo vệ Secret**

- [ ] Không coi Base64 là mã hóa.
- [ ] Encryption at rest cho Secret trong etcd đã được cấu hình.
- [ ] RBAC giới hạn quyền get/list/watch/create/update/delete.
- [ ] Controller dùng ServiceAccount riêng và least privilege.
- [ ] Workload không có quyền đọc Secret khác nếu không cần.
- [ ] Secret không xuất hiện trong log, event, annotation hoặc status.
- [ ] External secret manager/ESO/CSI được cấu hình và kiểm thử nếu sử dụng.

**Rotation và lifecycle**

- [ ] Có credential version và quy trình rotation.
- [ ] Workload được reload hoặc rollout để nhận credential mới.
- [ ] Credential cũ chỉ bị revoke sau khi xác minh chuyển đổi thành công, nếu provider hỗ trợ overlap.
- [ ] Unbind gọi broker/provider revoke, không chỉ xóa Secret.
- [ ] Secret và workload reference được cleanup theo binding.
- [ ] Reconcile xử lý drift và restart controller.
- [ ] Có audit cho bind, rotation, unbind và cleanup.

**Kiểm thử và vận hành**

- [ ] Đã kiểm thử namespace isolation và RBAC.
- [ ] Đã kiểm thử Pod mount Secret và nhận giá trị.
- [ ] Đã kiểm thử rotation, restart và unbind.
- [ ] Có cảnh báo cho Secret sync failure và binding cleanup bị kẹt.
- [ ] Có quy trình backup/restore và quản lý key mã hóa.
- [ ] Không dùng credentials thật trong CI hoặc tài liệu.

Kubernetes Secret là cầu nối phổ biến để đưa credentials của OSB binding vào workload, nhưng an toàn phụ thuộc vào toàn bộ chuỗi: broker cấp và thu hồi credential, controller chuyển đổi và reconcile, Kubernetes API kiểm soát quyền và lưu trữ, còn Pod chỉ nhận đúng dữ liệu cần thiết. Khi thiết kế rõ namespace, RBAC, encryption at rest, rotation, revocation và external secret integration, service broker có thể phân phối credentials cho workload Kubernetes một cách có kiểm soát và truy vết được.

