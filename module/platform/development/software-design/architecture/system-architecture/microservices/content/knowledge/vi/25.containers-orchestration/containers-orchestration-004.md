# Cấp cấu hình, bí mật và tài khoản dịch vụ

Trong hệ thống microservices chạy bằng container, một image có thể được triển khai tại development, staging và production với cơ sở dữ liệu, endpoint phụ thuộc, hạn mức tài nguyên và quyền truy cập khác nhau. Nếu đưa toàn bộ thiết lập vào source code hoặc nhúng vào image, mỗi thay đổi môi trường có thể đòi hỏi build lại, làm lộ thông tin bí mật và khiến việc thu hồi quyền trở nên khó khăn.

Ba yếu tố cần được thiết kế riêng nhưng phối hợp chặt chẽ:

- **Cấu hình (configuration):** các tham số thay đổi theo môi trường, chẳng hạn URL nội bộ, timeout, feature flag, log level.
- **Bí mật (secret):** thông tin cần bảo mật, chẳng hạn mật khẩu, API key, chứng chỉ hoặc khóa ký; phải kiểm soát ai có thể lấy, dùng và thay thế.
- **Tài khoản dịch vụ (service account / workload identity):** danh tính của workload, dùng để chứng minh nó là ai và xin quyền tối thiểu khi gọi Kubernetes API, cloud API hoặc hệ thống khác.

Bài học lấy Kubernetes làm ví dụ điều phối chính, đồng thời giải thích nguyên tắc áp dụng cho Docker Compose, các nền tảng container và trình quản lý bí mật khác. Tên công cụ và cấu hình minh họa cần được điều chỉnh theo cluster và phiên bản đang vận hành.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt config, secret, identity, quyền truy cập và token xác thực.
2. Thiết kế một image bất biến dùng ở nhiều môi trường mà không nhúng dữ liệu nhạy cảm.
3. Chọn ConfigMap, Secret, biến môi trường hoặc volume theo đặc tính của ứng dụng.
4. Hiểu cách Kubernetes ServiceAccount, Role, RoleBinding và cơ chế workload identity tương tác.
5. Thực hiện **least privilege**: service chỉ có quyền thực sự cần, trong đúng namespace hoặc tài nguyên.
6. Cấp secret qua hệ thống quản lý tập trung, giới hạn thời gian sống, xoay vòng và thu hồi mà không làm gián đoạn không cần thiết.
7. Biết khi nào thay đổi cấu hình được phản ánh vào Pod đang chạy và khi nào cần rollout mới.
8. Kiểm thử tính đúng đắn của cấu hình, quyền hạn và trạng thái sau khi xoay secret mà không in lộ giá trị nhạy cảm.
9. Thiết kế ranh giới trách nhiệm giữa CI/CD, cluster, application, secret manager và chủ sở hữu dịch vụ.

## 2. Ba lớp khác nhau: giá trị, bí mật và danh tính

Giả sử `order-service` cần địa chỉ `inventory-service` và `payment-service`, timeout gọi downstream, tên topic của message broker, credential kết nối database, quyền đọc object cloud storage và quyền truy vấn một ConfigMap qua Kubernetes API. Không nên gom tất cả vào một file `application-prod.yml` chứa cả endpoint, password và cloud key rồi copy vào image.

| Dữ liệu/capability | Bản chất | Cách cấp phù hợp |
|---|---|---|
| `INVENTORY_BASE_URL` | Cấu hình không bí mật | ConfigMap hoặc config service có kiểm soát |
| `PAYMENT_TIMEOUT_MS` | Cấu hình không bí mật | ConfigMap, environment hoặc deployment config |
| `DB_PASSWORD` | Secret có vòng đời riêng | Secret được đồng bộ từ secret manager hoặc cơ chế cấp bí mật tương đương |
| Quyền đọc object storage | Quyền gắn với danh tính workload | Workload identity liên kết tài khoản dịch vụ với cloud IAM |
| Quyền `get` một ConfigMap | Quyền Kubernetes API | ServiceAccount + Role/RoleBinding với tài nguyên xác định |
| Image private registry credential | Credential để node kéo image | `imagePullSecrets` hoặc cơ chế registry identity của nền tảng |
| TLS key của Ingress | Bí mật terminate TLS | TLS Secret/certificate manager theo thiết kế ingress |
| Access token từ client | Thông tin xác thực request bên ngoài | Security middleware và giao thức auth; không đưa vào ConfigMap hoặc baggage |

**Tên tài khoản không tự sinh ra quyền.** ServiceAccount là danh tính trong Kubernetes; RBAC xác định quyền dùng Kubernetes API. Quyền đọc cloud storage thường đến từ cloud IAM cùng một liên kết workload identity. Secret chứa dữ liệu bí mật; bản thân nó không phải một permission grant.

## 3. Nguyên tắc “build một lần, cấu hình khi chạy”

Một container image nên chứa code, runtime, dependency và tài nguyên không bí mật cần thiết để thực thi. Các giá trị khác nhau giữa môi trường được đưa vào khi triển khai hoặc khi chạy:

~~~text
Source code
   |
   v
CI: build, test, scan
   |
   v
Immutable image
  order-service@sha256:<digest>
   |
   +------------------------+-------------------------+
   |                        |                         |
   v                        v                         v
Development              Staging                  Production
  Config DEV              Config STG               Config PROD
  Secret DEV              Secret STG               Secret PROD
  Identity DEV            Identity STG             Identity PROD
   |                        |                         |
   v                        v                         v
Containers cùng image bytes, khác cấu hình và quyền
~~~

Lợi ích:

- Biết chính xác phiên bản code đang chạy ở mỗi môi trường.
- Không cần rebuild image khi đổi endpoint, timeout hoặc credentials.
- Mỗi môi trường giữ secret và quyền riêng; giảm rủi ro đọc chéo dữ liệu.
- Có thể thay hoặc thu hồi secret theo vòng đời bảo mật độc lập.
- Lịch sử thay đổi application và configuration được theo dõi rõ.

Cần phân biệt **cấu hình khởi động** với **cấu hình động**. Khi service chỉ đọc một giá trị lúc startup, thay đổi ở kho cấu hình không làm giá trị trong tiến trình tự đổi. Muốn cập nhật động phải có cơ chế refresh, validation và hành vi an toàn khi refresh thất bại.

## 4. Đường đi cấp phát cấu hình, secret và quyền

~~~text
Git / CI / GitOps
  | build image, validate manifest, phân quyền triển khai
  v
Cluster API / Deployment Controller
  |
  +--> ConfigMap (non-secret settings)
  |
  +--> Secret reference <--- Secret manager / operator / CSI
  |
  +--> ServiceAccount + RBAC
  |
  v
Kubelet tạo Pod trên node
  |
  +--> Inject env vars hoặc mount volumes
  |
  +--> Cấp token danh tính có audience/thời hạn theo policy
  |
  v
Order Service container
  |
  +--> Dùng config để chọn hành vi
  |
  +--> Dùng secret để xác thực DB/provider
  |
  +--> Dùng workload identity để xin token đến cloud service
  |
  +--> Chỉ gọi Kubernetes API nếu được cấp quyền cụ thể
~~~

Không phải lúc nào cả ba nhánh đều cần. Ví dụ một web service chỉ gọi downstream HTTP bằng token nhận từ issuer thì có thể **không cần quyền Kubernetes API**, và không cần mount ServiceAccount token vào container.

### Ranh giới trách nhiệm

| Thành phần | Trách nhiệm chính |
|---|---|
| Developer/service owner | Xác định danh sách key, kiểu dữ liệu, default, ý nghĩa, cách xử lý khi thiếu và reload |
| Platform team | Cung cấp namespace, chính sách Pod, networking, admission, secret integration, identity mapping |
| Security/IAM owner | Cấp quyền, bảo vệ secret, vòng đời token, điều kiện truy cập, audit |
| CI/CD hoặc GitOps | Quản lý phiên bản manifest, triển khai artifact đúng môi trường, ghi lịch sử thay đổi |
| Kubelet/runtime | Tạo container, áp cấu hình Pod, mount secrets/token theo khai báo |
| Ứng dụng | Kiểm tra config, dùng credential đúng mục đích, không log secret, xử lý rotation |
| Observability team | Theo dõi lỗi cấu hình/quyền, không thu giá trị secret vào log/trace/metrics |

## 5. ConfigMap: cấu hình không bí mật

Kubernetes `ConfigMap` lưu dữ liệu dạng key–value hoặc file config, phù hợp với endpoint, cờ kỹ thuật và tham số vận hành **không cần giữ bí mật**.

~~~yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: orders-config-v1
  namespace: orders
data:
  INVENTORY_BASE_URL: "http://inventory.orders.svc.cluster.local:8080"
  PAYMENT_TIMEOUT_MS: "300"
  ORDER_EVENTS_TOPIC: "order-events"
  LOG_LEVEL_ROOT: "INFO"
~~~

Cách cấp cho container:

1. **`env.valueFrom.configMapKeyRef`:** lấy từng key vào biến môi trường.
2. **`envFrom.configMapRef`:** đưa nhiều key có tên hợp lệ vào environment.
3. **ConfigMap volume:** mount thành một hoặc nhiều file, phù hợp ứng dụng đọc file cấu hình.
4. **Kubernetes API:** ứng dụng trực tiếp truy vấn ConfigMap khi thật sự cần, lúc đó phải cấp RBAC tương ứng.

Lấy từng key giúp xác định chính xác những gì service sử dụng. `envFrom` tiện nhưng làm bề mặt cấu hình rộng hơn, dễ gây xung đột tên hoặc vô tình đưa key không cần vào tiến trình.

**Không dùng ConfigMap để chứa password, API key hoặc private key.** Người có quyền đọc ConfigMap có thể xem nội dung; đây không phải kho bí mật. ConfigMap cũng không phù hợp để lưu dữ liệu lớn hoặc thay thế một hệ thống cấu hình chuyên dụng có schema và workflow phê duyệt.

### 5.1. Cấu hình theo môi trường

~~~text
orders-dev:
  INVENTORY_BASE_URL = http://inventory.dev.svc...
  PAYMENT_TIMEOUT_MS = 1000

orders-staging:
  INVENTORY_BASE_URL = http://inventory.staging.svc...
  PAYMENT_TIMEOUT_MS = 500

orders-production:
  INVENTORY_BASE_URL = http://inventory.orders.svc...
  PAYMENT_TIMEOUT_MS = 300
~~~

Các giá trị chỉ là ví dụ; timeout phải được thiết kế theo deadline, năng lực downstream và SLO. Không copy endpoint production vào development nếu có nguy cơ môi trường test ghi dữ liệu thật.

Nhóm nên duy trì hợp đồng cấu hình: tên, kiểu, phạm vi hợp lệ, default, nguồn, có phải bí mật hay không và hành động khi thiếu. Đừng để hàng trăm key tự phát triển mà không có chủ sở hữu.

## 6. Secret: giá trị bí mật với vòng đời riêng

Kubernetes `Secret` là object dành cho dữ liệu nhạy cảm như credential, chứng chỉ hoặc token. Nhiều manifest của Secret dùng `data` mã hóa **base64** để biểu diễn bytes.

**Base64 không phải mã hóa bảo mật.** Ai đọc được Secret object có thể giải mã thành giá trị gốc. Bảo vệ Secret phụ thuộc vào kiểm soát API/RBAC, mã hóa dữ liệu lưu trữ (etcd encryption at rest), backup, node, memory, distribution và quyền của workload.

Kubernetes không tự trở thành secret manager đầy đủ chỉ vì object có tên `Secret`. Khi cần quy trình cấp quyền, rotation, phiên bản, audit hoặc credential ngắn hạn, tổ chức có thể dùng cloud secret manager, Vault hoặc hệ thống tương đương.

### 6.1. Những cách cấp secret cho Pod

- **Environment variable qua `secretKeyRef`:** đơn giản với thư viện chỉ đọc env; thay Secret object không cập nhật biến môi trường trong tiến trình đang chạy.
- **Secret volume:** mount giá trị dưới dạng file, tiện cho chứng chỉ và thư viện đọc file; thay đổi được kubelet cập nhật theo cơ chế đồng bộ, nhưng ứng dụng phải reload.
- **CSI Secrets Store integration:** mount secret từ kho bên ngoài theo driver/provider; cần xác minh cơ chế rotation và sync thực tế.
- **Secret synchronization operator:** controller đọc secret manager và tạo/cập nhật Kubernetes Secret; việc đồng bộ làm tăng số nơi dữ liệu tồn tại, nên phải hiểu mô hình rủi ro.
- **Runtime retrieval:** ứng dụng dùng workload identity lấy secret ngắn hạn trực tiếp từ kho bí mật và cache an toàn; ứng dụng phải xử lý timeout, refresh và lỗi phụ thuộc.

Không có lựa chọn tốt nhất cho mọi trường hợp. Chọn theo thư viện ứng dụng, tần suất xoay, khả năng reload, mô hình quyền, chi phí vận hành và đường phục hồi khi secret manager mất kết nối.

### 6.2. Không đưa secret thô vào Git

Ví dụ lệnh tạo Secret từ file local chỉ để minh họa cơ chế:

~~~bash
kubectl -n orders create secret generic orders-db-credentials \
  --from-file=password=./db-password.txt
~~~

Chỉ dùng file có dữ liệu giả lập trong môi trường học. Production cần đi qua cơ chế cấp bí mật đã được phê duyệt. Không commit file chứa mật khẩu, YAML có `data` hay `stringData` thô, hoặc đẩy chúng vào PR, CI artifact, log và chat. Tránh đưa mật khẩu vào đối số lệnh dạng `--from-literal=password=actual-secret` nếu shell history hoặc process arguments có thể ghi lại.

Kubernetes Secret có các loại `Opaque`, `kubernetes.io/tls`, `kubernetes.io/dockerconfigjson`, tùy mục đích. Không dùng một Secret chứa toàn bộ credentials của mọi service, và không dùng registry credential để thay thế database credential.

## 7. ServiceAccount: danh tính Pod

`ServiceAccount` là danh tính cho workload tương tác với Kubernetes API. Pod có thể chỉ định nó bằng `spec.serviceAccountName`. Nếu không chỉ định, Kubernetes thường sử dụng ServiceAccount `default` trong namespace.

~~~yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: orders-api
  namespace: orders
automountServiceAccountToken: false
~~~

`automountServiceAccountToken: false` thể hiện chủ đích **không tự mount token truy cập Kubernetes API** khi workload không cần. Có thể đặt ở Pod spec để ghi rõ phạm vi. Nếu ứng dụng cần gọi Kubernetes API hoặc sử dụng identity integration dựa trên projected token, phải thiết kế cơ chế token phù hợp.

**ServiceAccount không có quyền Kubernetes API chỉ vì tên của nó.** RBAC mới quyết định khả năng `get`, `list`, `watch`, `create` hoặc `delete` trên tài nguyên cụ thể.

### 7.1. Tránh chia sẻ tài khoản mặc định

~~~text
namespace: orders
  ServiceAccount/orders-api
  ServiceAccount/orders-consumer
  ServiceAccount/orders-migration
  ServiceAccount/default
~~~

API phục vụ HTTP có thể không cần token Kubernetes API; consumer chỉ cần credential broker; migration job có thể cần quyền database cao trong thời gian ngắn. Dùng chung ServiceAccount có quyền rộng khiến ảnh hưởng của một Pod bị xâm nhập lan sang workloads khác.

## 8. RBAC: quyền gì trên tài nguyên nào?

Các đối tượng thường gặp:

- **Role:** tập quyền trên tài nguyên trong một namespace.
- **ClusterRole:** tập quyền có thể dùng ở phạm vi cluster hoặc được bind theo namespace tùy tài nguyên.
- **RoleBinding:** gán Role/ClusterRole cho subject trong phạm vi namespace.
- **ClusterRoleBinding:** gán quyền ở phạm vi cluster.
- **ServiceAccount:** subject đại diện workload được bind quyền.

Ví dụ job cần **đọc duy nhất một ConfigMap** qua Kubernetes API:

~~~yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: orders-config-watcher
  namespace: orders
---
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: read-orders-runtime-config
  namespace: orders
rules:
  - apiGroups: [""]
    resources: ["configmaps"]
    resourceNames: ["orders-runtime"]
    verbs: ["get"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: config-watcher-reads-runtime
  namespace: orders
subjects:
  - kind: ServiceAccount
    name: orders-config-watcher
    namespace: orders
roleRef:
  kind: Role
  name: read-orders-runtime-config
  apiGroup: rbac.authorization.k8s.io
~~~

Giới hạn cố ý: chỉ `get`, không tạo/sửa/xóa; chỉ ConfigMap `orders-runtime`; chỉ namespace `orders`; không cho `get/list/watch secrets`, `pods/exec` hoặc `cluster-admin`.

Nếu cần `list`/`watch`, kiểm tra cách API áp dụng `resourceNames` và field selector; rule `get` không tự hỗ trợ mọi kiểu watch.

**Ứng dụng đọc ConfigMap hoặc Secret qua env/volume không cần RBAC `get` đối tượng đó.** Kubelet/controller thực hiện việc mount theo Pod specification. Cấp `get secrets` cho mọi ServiceAccount chỉ để sử dụng `secretKeyRef` là lỗi least privilege nghiêm trọng.

## 9. Workload identity và cloud IAM

Microservice có thể cần truy cập cloud object storage, managed database, cloud queue, secret manager hoặc key management service. Một cách cũ là đưa cloud access key dài hạn vào Kubernetes Secret rồi mount cho Pod. Credential dài hạn dễ bị sao chép và khó thu hồi.

**Workload identity** cho phép workload chứng minh danh tính và nhận token/quyền ngắn hạn từ hệ thống tin cậy. Tùy nền tảng, Kubernetes ServiceAccount có thể liên kết với cloud IAM qua OIDC federation hoặc cơ chế Pod identity khác.

~~~text
Pod: order-service
   |
   v
Kubernetes ServiceAccount/orders-api
   |
   | token nhận diện workload (audience và thời hạn đúng)
   v
Identity provider / cloud token service
   |
   | kiểm tra issuer, subject, audience, trust policy
   v
Cloud IAM role/service identity
   |
   | cấp token ngắn hạn, quyền phù hợp
   v
Object Storage / Secret Manager
~~~

Phải phân biệt:

1. Kubernetes RBAC kiểm soát **Kubernetes API**.
2. Cloud IAM kiểm soát **cloud resource**.
3. ServiceAccount có thể là một phần danh tính liên kết, nhưng không tự cấp cloud permission.
4. Annotation, admission, projected token và trust policy khác nhau giữa nền tảng.
5. Thay đổi Kubernetes RBAC không nhất thiết thay đổi quyền cloud và ngược lại.

Nếu `orders-api` chỉ cần đọc object theo prefix `reports/orders/`, không cấp quyền đọc/ghi toàn bucket. Nếu chỉ cần một secret trong secret manager, không cấp quyền liệt kê mọi secret. Development, staging và production nên có danh tính riêng.

### 9.1. Token ngắn hạn và audience

Projected ServiceAccount token có thể mang audience và thời hạn hữu hạn:

~~~yaml
volumes:
  - name: workload-token
    projected:
      sources:
        - serviceAccountToken:
            path: token
            audience: "identity.example.internal"
            expirationSeconds: 3600
containers:
  - name: orders-api
    volumeMounts:
      - name: workload-token
        mountPath: /var/run/workload-identity
        readOnly: true
~~~

Đây chỉ là đoạn cấu hình rút gọn đặt trong `spec` của Pod. Audience phải khớp bên xác thực; token projected không tự cấp quyền Kubernetes hoặc cloud. Không copy token vào log, baggage hay message. SDK cần reload token được xoay; token ngắn hạn giảm rủi ro nhưng không thay cho IAM policy, NetworkPolicy và giám sát truy cập.

## 10. Ví dụ triển khai: Order Service

Giả sử `order-service` chạy trong namespace `orders`, cần Inventory URL, Payment timeout và credential DB được platform cung cấp. Service không gọi Kubernetes API.

### 10.1. Namespace và ConfigMap

~~~yaml
apiVersion: v1
kind: Namespace
metadata:
  name: orders
---
apiVersion: v1
kind: ConfigMap
metadata:
  name: orders-config-v1
  namespace: orders
data:
  INVENTORY_BASE_URL: "http://inventory.orders.svc.cluster.local:8080"
  PAYMENT_TIMEOUT_MS: "300"
  ORDER_EVENTS_TOPIC: "order-events"
~~~

### 10.2. ServiceAccount riêng

~~~yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: orders-api
  namespace: orders
automountServiceAccountToken: false
~~~

Vì ứng dụng không dùng Kubernetes API, không cấp RoleBinding đọc Secrets/ConfigMaps. Pod vẫn được cấp Secret tham chiếu theo spec nếu người triển khai có quyền và kubelet thực thi mount như thiết kế.

### 10.3. Secret từ platform

Giả sử secret management đã tạo `orders-db-credentials` trong namespace `orders` với key `password`. Production có thể dùng secret sync controller hoặc secret manager; không viết credential thật trong file Deployment.

~~~text
Kubernetes Secret:
  name      = orders-db-credentials
  namespace = orders
  key       = password

Giá trị không xuất hiện ở Git, tài liệu, CI stdout
hoặc log ứng dụng.
~~~

### 10.4. Deployment tham chiếu từng key

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders-api
  namespace: orders
spec:
  replicas: 3
  selector:
    matchLabels:
      app: orders-api
  template:
    metadata:
      labels:
        app: orders-api
    spec:
      serviceAccountName: orders-api
      automountServiceAccountToken: false
      containers:
        - name: api
          image: registry.example.invalid/orders-api@sha256:<verified-digest>
          ports:
            - containerPort: 8080
          env:
            - name: INVENTORY_BASE_URL
              valueFrom:
                configMapKeyRef:
                  name: orders-config-v1
                  key: INVENTORY_BASE_URL
            - name: PAYMENT_TIMEOUT_MS
              valueFrom:
                configMapKeyRef:
                  name: orders-config-v1
                  key: PAYMENT_TIMEOUT_MS
            - name: ORDER_EVENTS_TOPIC
              valueFrom:
                configMapKeyRef:
                  name: orders-config-v1
                  key: ORDER_EVENTS_TOPIC
            - name: DB_PASSWORD
              valueFrom:
                secretKeyRef:
                  name: orders-db-credentials
                  key: password
          readinessProbe:
            httpGet:
              path: /actuator/health/readiness
              port: 8080
            initialDelaySeconds: 5
            periodSeconds: 5
          resources:
            requests:
              cpu: "100m"
              memory: "256Mi"
            limits:
              memory: "512Mi"
~~~

Manifest này là ví dụ; cần thay image digest thật, thêm `securityContext`, resources, cluster policy và endpoint readiness đã bật trong Spring Boot Actuator. Không dùng chuỗi `<verified-digest>` để deploy.

Ý nghĩa: mỗi key được tham chiếu rõ; DB credential tách khỏi image/ConfigMap; Pod có danh tính riêng và không tự mount API token vì không cần. Nếu môi trường dùng workload identity dựa trên projected token, thiết kế token phải được điều chỉnh cùng provider và Pod spec.

## 11. Env hay volume: chọn theo hành vi cập nhật

| Tiêu chí | Environment variables | Mounted files/volumes |
|---|---|---|
| Thích hợp | Key nhỏ, config đọc khi startup | Certificate, khóa dạng file, config nhiều dòng |
| Cách đọc | `System.getenv` hoặc config binding | File I/O/keystore |
| Thay đổi sau khi Pod chạy | **Không đổi** env trong process | ConfigMap/Secret volume có thể được cập nhật sau độ trễ |
| Reload ứng dụng | Cần restart/thiết kế riêng | Không tự động reload nếu app không hỗ trợ |
| Bề mặt rủi ro | Process environment | Filesystem/container permissions |
| Kiểm soát file mode | Không áp dụng | `defaultMode`, UID/GID, mount, `fsGroup` |
| Chia sẻ giữa containers | Theo khai báo từng container | Theo volumeMount từng container |

Lưu ý:

- Kubernetes cập nhật một số ConfigMap/Secret volumes theo cơ chế eventual update; không bảo đảm ngay lập tức.
- File mount qua `subPath` **không nhận cập nhật tự động** như volume bình thường.
- Env cần Pod mới/rollout để nhận Secret mới.
- File đã đổi không làm TLS client, connection pool hoặc SDK tự reload; phải kiểm chứng hành vi ứng dụng.
- Với thay đổi config quan trọng, một rollout có version và health checks thường dễ kiểm soát hơn thay đổi ngầm.

## 12. Thay đổi cấu hình phải có version và validation

Thay đổi không bí mật vẫn có thể gây sự cố. Ví dụ giảm `PAYMENT_TIMEOUT_MS` từ 800 xuống 100 ms có thể tăng timeout và retry; đổi endpoint có thể chuyển traffic sang dependency sai.

Thiết kế:

1. Định nghĩa key, kiểu dữ liệu, unit, khoảng cho phép và ý nghĩa.
2. Chỉ có default nếu thiếu giá trị vẫn an toàn.
3. Fail fast khi giá trị bắt buộc thiếu hoặc sai định dạng.
4. Thống nhất thứ tự ưu tiên của env, file, config server và command-line args.
5. Ghi nhận config revision và ai đã đổi, không ghi secret value.
6. Áp dụng canary/rolling rollout với thay đổi ảnh hưởng lớn.
7. Có rollback config và xác minh app đã dùng bản cũ.
8. Theo dõi ảnh hưởng tới SLO, dependency, timeout và error rate.

Ví dụ Spring Boot:

~~~java
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;

@Validated
@ConfigurationProperties(prefix = "orders")
public record OrdersProperties(
        @NotBlank String inventoryBaseUrl,
        @Min(50) @Max(30000) int paymentTimeoutMs
) {}
~~~

Cần bật đăng ký `ConfigurationProperties` và có dependency validation phù hợp. Có thể bind từ các property tên `orders.inventory-base-url` và `orders.payment-timeout-ms`; cách đặt environment tương ứng phải kiểm chứng theo quy tắc binding của framework đang dùng. Không tạo `toString()` ghi secret nếu class properties có credential.

## 13. Xoay vòng Secret an toàn

Secret có thể hết hạn, lộ, cần thay do chính sách hoặc đổi người sở hữu. Rotation cần xét hai thời điểm: **khi application dùng giá trị mới** và **khi backend ngừng chấp nhận giá trị cũ**.

Ví dụ database credential rotation:

~~~text
T0:   Application đang dùng credential A
T1:   Tạo credential B với quyền tối thiểu
T2:   Secret manager/cluster cấp B cho workload
T3:   Rollout/reload để client mới dùng B
T4:   Xác minh mọi replica/job đã dùng B
T5:   Thu hồi credential A
T6:   Kiểm tra không còn truy cập dựa trên A
~~~

Nếu backend chỉ có một password tại một thời điểm, cần cơ chế riêng như hai account tạm cùng quyền, short-lived token hoặc trình tự rotation được backend hỗ trợ. Không giả định mọi DB cho phép hai credentials đồng thời.

### Những chỗ dễ bị quên

- Connection pool đang giữ sessions xác thực bằng A.
- Pod đọc env nên chưa nhận B.
- TLS certificate file đổi nhưng HTTP client không reload.
- Cloud SDK cache token đến khi hết hạn.
- Broker consumer hoặc scheduled job ít chạy vẫn dùng A.
- Vùng/cluster phụ chưa rollout.
- Canary nhận B nhưng background worker vẫn dùng A.

Một Service Ready không bảo đảm rotation thành công. Cần đo xác thực thật tới dependency và biết trạng thái của jobs/consumers. Không ghi raw credential vào release record; chỉ ghi secret reference/version theo chính sách.

### Rollback trong quá trình rotation

Rollback image có thể cần giữ tương thích với secret version mới. Không khôi phục credential cũ đã bị lộ hoặc bị thu hồi chỉ để image cũ hoạt động. Với thay đổi không đảo ngược được, cần phương án roll-forward và bảo đảm phiên bản cũ/hiện tại dùng credential hợp lệ theo giai đoạn chuyển tiếp.

## 14. Mã hóa, backup và ranh giới truy cập

Bảo vệ Secret gồm nhiều lớp:

- **At rest trong cluster:** mã hóa dữ liệu nhạy cảm tại tầng lưu của API server/etcd theo chính sách; backup etcd cũng cần bảo vệ.
- **At rest bên ngoài:** secret manager dùng mã hóa, audit và quyền theo resource.
- **In transit:** TLS/xác thực cho Kubernetes API và secret manager.
- **In memory:** giá trị có thể nằm trong process memory; tránh log và core/heap dumps không kiểm soát.
- **On node:** kubelet đưa dữ liệu cho Pod; compromise node/runtime có thể ảnh hưởng workload đang chạy.
- **In telemetry:** không log env dump, secret files, authorization headers, token projected hay URL có credential.
- **Across backups:** secret có thể tồn tại trong snapshot, restore và log archive; retention phải được xét.

Mã hóa trong etcd không thay thế quyền tạo Pod, RBAC, admission và chính sách node. Một principal có quyền tạo Pod trong namespace có thể cố mount Secret của namespace dù không trực tiếp có quyền `get secret` qua API, nếu không có biện pháp hạn chế bổ sung.

## 15. Quyền tạo Pod có thể gián tiếp làm lộ Secret

Một lỗi phân quyền thường gặp: chặn `get secrets` nhưng cho developer quyền tạo mọi Pod trong namespace có Secret nhạy cảm.

Khi phân quyền phải xem:

- Ai được tạo/sửa Deployment, StatefulSet, Job và Pod?
- Ai được đổi `serviceAccountName` của workload?
- Ai được chạy `exec`, dùng ephemeral containers, xem log hay truy cập pod filesystem?
- Ai được cấu hình secret references hoặc projected tokens?
- Ai có thể dùng ServiceAccount gắn cloud IAM quyền rộng?
- Admission policy có giới hạn Secret reference/ServiceAccount cho workload không?

Least privilege bao gồm **khả năng triển khai workload**, không chỉ quyền đọc Secret trực tiếp. Namespace giúp tổ chức tài nguyên nhưng không tự là một ranh giới bảo mật hoàn chỉnh; với yêu cầu nhiều tenant còn cần node isolation, network, IAM và admission policies.

## 16. ImagePullSecret khác secret ứng dụng

Để node tải image từ private registry:

~~~yaml
apiVersion: v1
kind: Pod
metadata:
  name: private-image-example
  namespace: orders
spec:
  imagePullSecrets:
    - name: registry-pull
  containers:
    - name: api
      image: registry.example.invalid/orders-api:1.2.3
~~~

`imagePullSecrets` phục vụ kubelet/container runtime xác thực với registry, không phải biến môi trường DB password của ứng dụng. Một số nền tảng có registry identity riêng nên không cần Secret dạng Docker config trong từng namespace.

Không cấp quyền push registry cho runtime chỉ cần pull. Tách quyền registry, DB, broker và cloud API để credential lộ ở một chỗ không tác động mọi hệ thống.

## 17. Xác minh RBAC sau triển khai

Một số lệnh kiểm tra:

~~~bash
# Kiểm tra Deployment dùng ServiceAccount nào
kubectl -n orders get deployment orders-api -o yaml

# Kiểm tra orders-api có được đọc Secrets qua Kubernetes API
# Người thực thi cần quyền impersonate để dùng --as
kubectl auth can-i get secrets \
  --as=system:serviceaccount:orders:orders-api \
  -n orders

# Kiểm tra watcher đọc được ConfigMap đích
kubectl auth can-i get configmaps/orders-runtime \
  --as=system:serviceaccount:orders:orders-config-watcher \
  -n orders
~~~

Kỳ vọng `orders-api` không có quyền đọc Secrets qua Kubernetes API; `orders-config-watcher` chỉ đọc tài nguyên được cấp. Nếu lệnh `--as` thất bại vì người dùng kiểm tra thiếu quyền impersonation, không thể kết luận về quyền của SA. Kubernetes RBAC cũng không phản ánh toàn bộ cloud IAM hoặc khả năng mount Secret khi có quyền tạo Pod.

Không chạy `kubectl get secret -o yaml` trong logs CI chỉ để kiểm tra sự tồn tại; output có thể chứa dữ liệu base64 dễ giải mã. Kiểm tra references/metadata bằng phương thức có quyền phù hợp.

## 18. Biết phiên bản cấu hình thực sự đang chạy

Sự cố thường gặp:

~~~text
ConfigMap đã sửa lúc 10:00
  |
  v
Pod cũ vẫn chạy với env load từ 09:00
  |
  v
Người vận hành nhìn ConfigMap mới và tưởng app đã dùng
~~~

Có thể:

1. Dùng tên ConfigMap có version hoặc content hash như `orders-config-v2`.
2. Cập nhật Pod template để tham chiếu tên mới và kích hoạt rollout.
3. Ghi config revision/checksum **không chứa Secret value** trong release record.
4. Startup log chỉ ghi config version, environment và service build ID phi nhạy cảm.
5. Với Secret, ghi reference/version nếu chính sách cho phép, không log value hoặc hash dễ dò.
6. Theo dõi trạng thái Pod và runtime health để biết revision đã được nạp thực tế.

Không cho rằng thay đối tượng ConfigMap/Secret trong cluster đồng nghĩa mọi Pod đã reload. Health/revision cần gắn với ứng dụng, không chỉ trạng thái tồn tại của object.

## 19. Docker Compose và môi trường phát triển

Ngoài Kubernetes, Docker Compose hỗ trợ environment, env file, secrets/configs tùy chế độ sử dụng. Ví dụ local:

~~~yaml
services:
  orders:
    image: orders-api:local
    environment:
      ORDERS_INVENTORY_BASE_URL: "http://inventory:8080"
      ORDERS_PAYMENT_TIMEOUT_MS: "800"
    # Credential thử nghiệm được cấp qua cơ chế riêng của dev.
    # Không commit token hoặc mật khẩu production vào Compose.
~~~

`env_file` và `.env` rất tiện nhưng **không tự bảo vệ bí mật**. Nếu file chứa credential, phải kiểm soát quyền đọc, không commit, không in vào CI logs và dùng data thử nghiệm phù hợp. Không cấp tài khoản production cho local debugging vì tạo bề mặt rò rỉ trên máy phát triển.

## 20. Secret không thay cho xác thực giữa service

Giả sử Order gọi Payment. Có thể dùng shared API key dài hạn từ Secret, hoặc dùng workload identity để xin token với audience, scope và thời hạn ngắn. Cách thứ hai thường giảm rủi ro nếu hạ tầng và API đích hỗ trợ.

~~~text
Order Pod
  -> workload identity hợp lệ
  -> token issuer cấp token ngắn hạn
  -> Payment API xác thực và kiểm tra quyền
~~~

Server đích phải kiểm tra chữ ký, issuer, audience, thời hạn và authorization claims. Không tự coi Kubernetes ServiceAccount JWT là bearer credential chung cho mọi downstream: mỗi API phải chấp nhận rõ identity issuer và audience của nó.

Phân biệt:

- **Authentication:** workload chứng minh nó là ai.
- **Authorization:** workload được làm gì trên tài nguyên nào.
- **Secret:** có thể dùng trong authentication nhưng không định nghĩa toàn bộ quyền.
- **Policy:** xác định ai được xin token, phạm vi, điều kiện và thời hạn.

Ngay cả khi hai service nằm trong một cluster, không mặc định network nội bộ là ranh giới an toàn; có thể cần mTLS, mesh policy và application-level authorization.

## 21. Phân tách danh tính build, deploy và runtime

Pipeline thường cần ba tập quyền khác nhau:

- **Build identity:** đọc source, test, build image và push registry.
- **Deploy identity:** tạo/sửa manifest, Deployment trong đúng môi trường.
- **Runtime identity:** Pod truy cập Kubernetes API, cloud resource hoặc dependency.

~~~text
CI Build Runner
  | push immutable image
  v
Registry
  | digest
  v
GitOps Deployment Controller
  | apply allowed manifests
  v
Kubernetes API
  | create/update Pods
  v
Runtime ServiceAccount
  | cloud IAM/API permissions
  v
Application dependencies
~~~

Builder có quyền push registry không cần đọc production DB Secret. Runtime Pod cần đọc storage object không cần quyền sửa Deployment. Deploy identity cần sửa tài nguyên đúng namespace nhưng không nhất thiết có quyền truy cập dữ liệu nghiệp vụ.

### Gates CI/CD nên có

- Manifest không chứa secret thô, token hoặc private key.
- ConfigMap chỉ chứa field không bí mật theo schema.
- Deployment không dùng SA `default` quyền rộng ngoài thiết kế.
- `automountServiceAccountToken` khớp nhu cầu thực.
- Role/ClusterRole không có wildcard resource/verb vô căn cứ.
- Không grant `cluster-admin` hoặc `secrets list` không cần thiết.
- Admission cho phép đúng SA, image source và Secret references.
- Image digest và config revision đúng bản đã kiểm thử.
- Secret reference tồn tại mà không xuất giá trị vào logs.
- Có readiness, rollout/rollback plan khi config mới gây lỗi.
- Danh tính và secret của dev/staging/prod tách biệt.

## 22. Xử lý lỗi thiếu cấu hình và lỗi quyền

| Tình huống | Biểu hiện | Hướng kiểm tra |
|---|---|---|
| Tên ConfigMap/Secret hoặc key sai | Pod không khởi tạo container, có thể `CreateContainerConfigError` | Namespace, tên object và key |
| Config value sai kiểu | Application startup lỗi | Validation, thông báo tên key và kiểu mong đợi |
| Secret đổi nhưng env không đổi | Pod cũ dùng credential cũ | Rollout/restart hoặc reload strategy |
| Không có RBAC | `403 Forbidden` từ Kubernetes API | Subject, namespace, verb, resource, API group |
| Cloud IAM sai | Access denied từ cloud service | Issuer, subject, audience, IAM scope |
| Token hết hạn | Auth failures sau thời gian chạy | SDK refresh và projected token rotation |
| File secret permission sai | App không đọc được cert/key | Mode, UID/GID, mount path |
| Sai namespace | Pod không thấy Secret | Cấp object đúng namespace |
| App crash/restart | `CrashLoopBackOff` | Logs an toàn, config validation, dependency |
| Secret manager lỗi | Refresh timeout hoặc startup chậm | Timeout, cache, retry giới hạn, phương án phục hồi |

Log nên:

~~~text
Failed to start orders-api:
config ORDERS_PAYMENT_TIMEOUT_MS must be 50..30000
secret reference orders-db-credentials/password unavailable
identity exchange failed: category=AUDIENCE_MISMATCH
~~~

Không log `DB_PASSWORD=...`, raw JDBC URL có password, JWT hoặc toàn bộ environment. Tên Secret/key cũng phải tuân theo chính sách nội bộ, nhưng chúng an toàn hơn rất nhiều so với raw value.

## 23. Bảo vệ Pod ngay cả khi secret đã được mount

Secret cuối cùng phải được process dùng; attacker có quyền đọc process environment/files có thể lấy nó. Các biện pháp giảm ảnh hưởng:

- Chạy container bằng non-root user khi tương thích.
- Giảm Linux capabilities và quyền ghi filesystem.
- Dùng `readOnlyRootFilesystem` nếu ứng dụng hỗ trợ.
- Hạn chế `exec`/debug/ephemeral container qua RBAC.
- Không mount Secret vào sidecar không cần dùng.
- Chỉ mount Secret cho đúng container theo yêu cầu.
- Hạn chế traffic egress bằng NetworkPolicy nếu CNI hỗ trợ.
- Dùng workload identity với tài nguyên cụ thể và token ngắn hạn.
- Bảo vệ heap/core dumps và traces có thể chứa credential.
- Dùng admission policy ngăn workload dùng ServiceAccount quyền cao ngoài scope.

Pod nhiều container có những tài nguyên chia sẻ theo khai báo. Đừng mặc định Secret mount vào một container luôn hoàn toàn vô hình với container khác nếu Pod hoặc node đã bị xâm nhập; cần đánh giá cụ thể threat model.

## 24. Kiểm thử trong môi trường chạy thật

Manifest đúng cú pháp chưa chứng minh ứng dụng nhận config/secret đúng và permission đủ hẹp.

### 24.1. Cấu hình

- Pod mới khởi động với tất cả key bắt buộc.
- Thiếu key quan trọng gây lỗi rõ, không dùng default nguy hiểm.
- Sai kiểu hoặc ngoài phạm vi được từ chối trước khi nhận traffic.
- Staging không trỏ nhầm endpoint production.
- Cập nhật ConfigMap qua env buộc rollout mới mới nhận giá trị.
- Volume cập nhật thì ứng dụng reload đúng như thiết kế, có xét delay.
- Config store mất kết nối không khiến app bỏ qua validation quan trọng.

### 24.2. Bí mật

- App lấy credential qua reference đã chỉ định.
- Không có raw secret trong image layers, manifest Git, CI log, crash log, trace hoặc metrics.
- Secret thiếu/bị thu hồi gây lỗi có category an toàn.
- Sau rotation, mọi replicas/jobs dùng version mới.
- Credential cũ thu hồi không còn cần bởi worker ít hoạt động.
- Env/volume/subPath có hành vi đúng như thiết kế.
- Secret manager outage có timeout và phương án phục hồi phù hợp.

### 24.3. Danh tính và quyền

- Pod thực sự dùng ServiceAccount được chỉ định.
- Không có quyền Kubernetes API cho app không cần gọi API.
- Workload chỉ đọc/ghi đúng cloud resource đã cấp.
- Thao tác **không được phép** thực sự bị từ chối.
- Token audience/subject không đúng bị reject.
- ServiceAccount staging không thể truy cập production resource.
- Quyền tạo Pod không cho phép vượt chính sách Secret/SA.
- Token được reload khi hết hạn nếu integration yêu cầu.

Dùng credential giả và tài nguyên test. Không thử đọc Secret production hoặc đưa secret value ra logs để “chứng minh” quyền.

## 25. Bài tập tình huống

Hệ thống:

~~~text
Gateway
  |
  v
Order Service
  | \
  |  +--> Inventory Service (HTTP)
  |
  +-----> Payment Provider (external HTTPS)
  |
  +-----> PostgreSQL
  |
  +-----> Kafka: OrderCreated
             |
             v
       Notification Worker
~~~

Yêu cầu:

1. Order cần Inventory endpoint, Payment timeout, tên Kafka topic và password PostgreSQL.
2. Notification Worker cần credential gửi email.
3. Một job lưu hóa đơn lên cloud object storage.
4. Cùng image chạy dev, staging và prod.
5. Credential thanh toán có thể rotate mà không dừng cluster.
6. Các service HTTP không cần gọi Kubernetes API.
7. Nhóm muốn biết config revision thực đang chạy trên từng Pod.

**Câu hỏi:**

1. Phân loại giá trị thành ConfigMap, Secret và workload identity.
2. Tạo ServiceAccount nào cho Order, Notification Worker và job hóa đơn?
3. Có cần grant `get secrets` cho Order chỉ vì dùng `secretKeyRef`?
4. Khi DB Secret đổi nhưng Pod đọc qua env, cần làm gì?
5. Job hóa đơn nên dùng cloud key dài hạn hay workload identity nếu được hỗ trợ?
6. Làm sao rollback image mà không tái sử dụng credential đã bị thu hồi?
7. Cần kiểm tra quyền gì của developer có thể sửa Deployment trong namespace?
8. Config volume đã đổi nhưng app chưa reload, có thể tuyên bố triển khai xong không?

**Gợi ý tự đối chiếu:**

- ConfigMap: Inventory URL, Payment timeout, Kafka topic, config version.
- Secret: PostgreSQL password và email provider key, tách theo workload/môi trường.
- Workload identity: job hóa đơn có identity riêng với IAM chỉ ghi đúng bucket/prefix.
- Mỗi workload dùng ServiceAccount riêng, tránh shared identity quyền rộng.
- Không cấp `get secrets` cho Pod chỉ để mount `secretKeyRef`.
- Env cần rollout/restart Pod; rotation có giai đoạn chuyển tiếp đủ an toàn.
- Rollback code/config khác rollback secret; credential bị lộ không được khôi phục.
- Kiểm tra create/patch Pod, ServiceAccount selection, exec, Secret references và admission.
- Chỉ coi config đã áp dụng khi runtime revision/health chứng minh, không chỉ khi object đổi.

## 26. Những sai lầm thường gặp

1. **Đặt password trong ConfigMap hoặc Git:** chuyển sang secret manager và reference.
2. **Tin base64 là encryption:** thêm RBAC, encryption at rest, audit, retention.
3. **Nhúng config/credential vào image:** mất tính bất biến theo môi trường; tách runtime input.
4. **Cấp `get/list secrets` cho mọi ServiceAccount:** mount Secret không cần quyền API đó.
5. **Dùng `default` SA có quyền rộng:** tạo danh tính riêng và giới hạn deploy rights.
6. **Gom Kubernetes RBAC với cloud IAM:** kiểm tra cả hai độc lập.
7. **Mount API token cho mọi Pod:** tắt automount khi không cần và integration không yêu cầu.
8. **Secret đổi tức là app tự nhận mới:** env không tự refresh; file còn cần reload.
9. **Dùng `subPath` rồi mong volume Secret tự đổi:** xem ngoại lệ và restart nếu cần.
10. **Thu hồi credential cũ quá sớm:** kiểm chứng mọi replica/job đã dùng version mới.
11. **Xem namespace là cô lập tuyệt đối:** kiểm tra node, admission và IAM.
12. **Log environment hoặc token để debug:** chỉ ghi category và config version.
13. **Dùng một cloud access key cho mọi service:** thay bằng identity riêng, quyền hẹp.
14. **Không thử quyền bị từ chối:** YAML hẹp chưa chứng minh thực thi hẹp.
15. **Nhầm imagePullSecret với runtime credential:** registry và app credential khác mục đích.
16. **Sửa config production không có lịch sử:** version hóa và rollout có kiểm soát.

## 27. Quy trình áp dụng cho một dự án microservices

**Bước 1 — Liệt kê runtime inputs:** endpoint, port, timeout, flags, DB credentials, certificates, broker và cloud resources. Phân loại ý nghĩa/độ nhạy cảm.

**Bước 2 — Viết hợp đồng cấu hình:** key, kiểu, default, khoảng hợp lệ, có cần restart/reload không và hành vi nếu thiếu.

**Bước 3 — Tách secret khỏi artifact:** image chứa code; ConfigMap chứa giá trị thường; secret manager/Secret giữ credential theo môi trường.

**Bước 4 — Thiết kế danh tính:** mỗi workload một SA; không mount Kubernetes API token nếu không cần; nếu dùng cloud resource thì tích hợp identity.

**Bước 5 — Least privilege:** RBAC cho Kubernetes API, IAM cho cloud, policy riêng database/broker. Xét cả quyền deploy và tạo Pod.

**Bước 6 — Rotation:** xác định version/expiry, env/volume/runtime retrieval, reload, chuyển tiếp, thu hồi và phục hồi.

**Bước 7 — CI/CD/GitOps:** validate schema, policies, image digest và Secret references; không in raw value vào logs hoặc Git.

**Bước 8 — Kiểm thử:** startup, health, access denied, token audience, rotation, rollback và không rò telemetry.

**Bước 9 — Theo dõi vận hành:** release/config revision an toàn, error categories, secret expiry alerts và access anomalies.

**Bước 10 — Dọn quyền thừa:** khi bỏ dependency, gỡ config key, Secret reference, RBAC, IAM role và credential không dùng.

## 28. Kết luận

Cấp cấu hình, bí mật và tài khoản dịch vụ trong microservices đòi hỏi phối hợp **giá trị runtime**, **vòng đời credential** và **quyền danh tính**. ConfigMap dành cho thiết lập không bí mật; Secret/secret manager dành cho dữ liệu phải bảo vệ; ServiceAccount/workload identity xác định workload là ai, còn RBAC/IAM xác định nó được làm gì.

Thiết kế tốt giữ image bất biến, cấp dữ liệu đúng môi trường, dùng quyền tối thiểu, kiểm tra phiên bản cấu hình mà ứng dụng đã áp dụng và có quy trình rotation/thu hồi đã thử nghiệm. Một Pod ở trạng thái Running chỉ cho biết process đang chạy; trạng thái an toàn còn phải xác nhận **đúng cấu hình, đúng Secret version, đúng danh tính và đúng phạm vi quyền**.
