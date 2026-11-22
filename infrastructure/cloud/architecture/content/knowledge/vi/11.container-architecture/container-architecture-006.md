# Quản lý cấu hình, bí mật và định danh của workload

Một container image nên có thể được triển khai ở dev, staging và production mà không cần build lại chỉ vì URL database, mức log hay tên dịch vụ thay đổi. Đồng thời, mật khẩu database, API key, token và chứng chỉ không được đóng gói tùy tiện vào image hoặc source code. Workload còn cần chứng minh danh tính của chính nó khi gọi cloud API, object storage, message queue hoặc dịch vụ nội bộ.

Ba khái niệm liên quan chặt chẽ nhưng giải quyết những câu hỏi khác nhau:

- **Cấu hình (configuration):** Ứng dụng cần những giá trị nào để hoạt động trong môi trường hoặc với tính năng cụ thể?
- **Bí mật (secret):** Giá trị nhạy cảm nào cần được bảo vệ, cấp phát, xoay vòng và thu hồi?
- **Định danh workload (workload identity):** Ứng dụng hoặc tiến trình nào đang yêu cầu quyền truy cập, và hệ thống xác minh điều đó ra sao?

Trong module **CLOUD_ARCHITECTURE**, quản lý đúng ba phần này giúp thiết kế compute/container có thể thay thế và mở rộng, giới hạn quyền truy cập dữ liệu, hỗ trợ tự động hóa triển khai, đồng thời kiểm soát rủi ro bảo mật, độ tin cậy, chi phí và vận hành theo tư duy Well-Architected.

## 1. Phân biệt cấu hình, bí mật và định danh

| Khái niệm | Câu hỏi cần trả lời | Ví dụ | Cách quản lý điển hình |
|---|---|---|---|
| **Configuration** | Ứng dụng cần hành vi hoặc endpoint nào ở môi trường này? | Log level, feature flag, URL API, timeout, tên queue | Config file, environment variable, config service |
| **Secret** | Giá trị nhạy cảm nào chứng minh quyền hoặc bảo vệ dữ liệu? | Database password, API token, private key, signing key | Secret manager, KMS/key vault, cơ chế cấp phát credential |
| **Workload identity** | Ai/tiến trình nào đang gọi tài nguyên? | Booking API production, notification worker, CI deploy job | IAM role, managed identity, service account, federation |
| **Authorization policy** | Danh tính được phép làm gì trên tài nguyên nào? | Booking API chỉ ghi dữ liệu booking và gọi operation tạo payment | IAM/RBAC, resource policy, application authorization |
| **Certificate/trust material** | Làm sao xác minh endpoint hoặc workload? | CA bundle, chứng chỉ mTLS | PKI, certificate manager, rotation process |

Một URL không chứa credential thường là cấu hình; connection string có mật khẩu nhúng bên trong là dữ liệu nhạy cảm; tên role hoặc service account có thể là thông tin nhận diện nhưng bản thân nó không phải credential bí mật. Ngược lại, access key và private key dùng để chứng minh quyền phải được bảo vệ.

Quy tắc thực tế:

- Cấu hình không nhạy cảm có thể đặt trong image defaults, ConfigMap, file cấu hình hoặc environment variable tùy yêu cầu.
- Bí mật nên được cấp từ hệ thống quản lý secret hoặc cơ chế credential ngắn hạn; tránh đặt trực tiếp trong image, Git hay log.
- Định danh workload nên được nền tảng cấp và xác minh theo runtime, hạn chế dùng credential dài hạn do nhóm tự tạo.

## 2. Nguyên tắc thiết kế cấu hình cho container

### 2.1. Tách image khỏi cấu hình môi trường

Cùng một image ứng dụng nên có thể chạy ở nhiều môi trường nếu code và cấu hình được thiết kế phù hợp:

~~~text
                    Cùng một application image
                              |
                 +------------+------------+
                 |            |            |
                DEV         STAGING        PROD
                 |            |            |
              config-dev   config-stage  config-prod
                 |            |            |
                 +------ Runtime behavior -+
~~~

Ví dụ, Booking API có thể sử dụng cùng image:

| Giá trị | Dev | Staging | Production |
|---|---|---|---|
| APP_ENV | dev | staging | prod |
| LOG_LEVEL | debug | info | warn |
| PAYMENT_API_URL | Endpoint sandbox | Endpoint staging | Private production endpoint |
| DB_POOL_MAX | 5 | 10 | 30 |
| FEATURE_NEW_CHECKOUT | true | true | Theo kế hoạch phát hành |

Các giá trị chỉ minh họa. Production có thể dùng pool, timeout và log khác; không nên tăng mọi thông số chỉ vì môi trường quan trọng hơn. Khác biệt schema/database và phiên bản dịch vụ cần quản lý bằng migration và tương thích API, không chỉ đổi biến môi trường.

### 2.2. Thứ tự ưu tiên cấu hình

Ứng dụng có thể nhận cấu hình từ giá trị mặc định trong code, file cấu hình, environment variable, config service và tham số triển khai. Cần quy định rõ thứ tự ưu tiên để tránh cùng một key có các giá trị mâu thuẫn.

Một quy ước tham khảo:

1. Giá trị mặc định an toàn trong ứng dụng.
2. File cấu hình đóng gói cho các giá trị mặc định không nhạy cảm.
3. Cấu hình môi trường được mount hoặc cung cấp lúc triển khai.
4. Tham số override được phê duyệt cho workload cụ thể.

Nguồn và thứ tự thực tế phụ thuộc framework. Một số framework có precedence riêng; cần ghi rõ và kiểm thử. Không giả định environment variable luôn thắng mọi nguồn.

Không đưa secret vào file cấu hình thông thường chỉ vì ứng dụng đã có cơ chế đọc file. Cấu hình có thể được log, hiển thị, copy hoặc lưu trong artifact; secret cần cơ chế bảo vệ riêng.

### 2.3. Validate cấu hình khi khởi động

Ứng dụng nên kiểm tra cấu hình thiết yếu ngay lúc startup:

- Key bắt buộc có tồn tại không?
- Giá trị có đúng kiểu, giới hạn và định dạng không?
- URL dùng scheme mong muốn, có hostname hợp lệ không?
- Timeout, pool size và retry count có nằm trong khoảng cho phép không?
- Feature flag có giá trị được hỗ trợ không?
- Kết nối tới phụ thuộc cần thiết có kiểm tra readiness phù hợp không?

Ví dụ Java kiểm tra một số giá trị không nhạy cảm:

~~~java
public record AppConfig(
        String environment,
        String paymentApiUrl,
        int requestTimeoutMillis,
        int databasePoolMax) {

    public static AppConfig fromEnvironment() {
        String environment = required("APP_ENV");
        String paymentApiUrl = required("PAYMENT_API_URL");
        int timeout = positiveInt("REQUEST_TIMEOUT_MS", 1500);
        int poolMax = positiveInt("DB_POOL_MAX", 10);

        if (!paymentApiUrl.startsWith("https://")) {
            throw new IllegalArgumentException(
                    "PAYMENT_API_URL must use HTTPS");
        }

        return new AppConfig(environment, paymentApiUrl, timeout, poolMax);
    }

    private static String required(String key) {
        String value = System.getenv(key);
        if (value == null || value.isBlank()) {
            throw new IllegalStateException(
                    "Missing required configuration: " + key);
        }
        return value;
    }

    private static int positiveInt(String key, int defaultValue) {
        String raw = System.getenv(key);
        if (raw == null || raw.isBlank()) return defaultValue;

        try {
            int value = Integer.parseInt(raw);
            if (value <= 0) throw new IllegalArgumentException(
                    key + " must be greater than zero");
            return value;
        } catch (NumberFormatException ex) {
            throw new IllegalArgumentException(
                    key + " must be an integer", ex);
        }
    }
}
~~~

Trong thông báo lỗi không in toàn bộ environment hoặc connection string vì chúng có thể chứa bí mật. Kiểm tra định dạng URL cũng không thay thế xác thực chứng chỉ, DNS và quyền truy cập runtime.

### 2.4. Startup config và dynamic config

- **Startup/static config:** Đọc khi ứng dụng khởi động, như port listen, pool initialization hoặc cấu hình TLS. Thay đổi có thể yêu cầu rollout.
- **Dynamic config:** Có thể cập nhật khi ứng dụng đang chạy, như feature flag hoặc một số ngưỡng nghiệp vụ. Cần cơ chế refresh, cache, versioning, fallback và audit.
- **Secret rotation:** Có vòng đời riêng; ứng dụng cần nhận credential mới và ngừng sử dụng credential cũ an toàn.

Dynamic config hữu ích cho thay đổi nhanh nhưng tăng độ phức tạp: nhiều replica có thể nhận phiên bản cấu hình ở thời điểm khác nhau. Nên có version, thời gian cập nhật, xác nhận đã áp dụng và cách rollback.

## 3. Quản lý secret theo vòng đời

Secret không chỉ là mật khẩu được cất trong một chỗ. Một secret có vòng đời gồm tạo, phân phối, sử dụng, xoay vòng, thu hồi, kiểm toán và xử lý khi bị lộ.

~~~mermaid
flowchart LR
    CREATE["Create / issue"] --> STORE["Secret manager / protected store"]
    STORE --> GRANT["Grant access to workload identity"]
    GRANT --> USE["Fetch or mount at runtime"]
    USE --> ROTATE["Rotate / renew"]
    ROTATE --> USE
    ROTATE --> REVOKE["Revoke old credential"]
    STORE -. "Audit events" .-> AUDIT["Central audit and alerting"]
    USE -. "Access logs" .-> AUDIT
    REVOKE -.-> AUDIT
~~~

### 3.1. Phân loại secret

| Loại | Ví dụ | Yêu cầu cần xem xét |
|---|---|---|
| Password | Database user password | Rotation, policy độ mạnh, quyền user |
| API key/token | Credential gọi dịch vụ bên thứ ba | Scope, expiry, revoke, quota |
| Private key | Ký token, mã hóa hoặc xác thực client | Bảo vệ key, HSM/KMS khi phù hợp, rotation |
| Certificate | TLS/mTLS client/server certificate | Trust chain, expiry, issuance và renew |
| Database credential | User/password hoặc token truy cập database | Tách principal theo workload, quyền schema, TTL |
| Signing/encryption key | Ký dữ liệu hoặc mã hóa dữ liệu nghiệp vụ | Key version, rotation, access policy, khả năng decrypt dữ liệu cũ |

Không phải mọi certificate hay key đều có cách lưu như nhau. Private key dùng ký hoặc mã hóa có thể cần HSM hoặc dịch vụ quản lý khóa; certificate public có thể phân phối rộng hơn, nhưng trust và private key đi kèm vẫn phải bảo vệ.

### 3.2. Secret manager và KMS

**Secret manager/key vault** quản lý giá trị bí mật, phiên bản, policy truy cập và audit. **Key Management Service (KMS)** quản lý vòng đời khóa mã hóa và thao tác mã hóa/giải mã hoặc bảo vệ khóa dữ liệu theo năng lực sản phẩm. Hai nhóm dịch vụ có thể tích hợp nhưng không phải lúc nào cũng là một thứ.

Ví dụ dịch vụ:

- AWS Secrets Manager và AWS Systems Manager Parameter Store; AWS KMS cho quản lý khóa.
- Azure Key Vault cho secrets, keys và certificates theo tính năng; Managed HSM là lựa chọn riêng cho nhu cầu HSM.
- Google Cloud Secret Manager cho secret và Cloud KMS cho khóa mật mã; Cloud HSM cho nhu cầu phần cứng mật mã được quản lý.

Khả năng, giá, giới hạn, replication, quyền và cách tích hợp cần đánh giá theo sản phẩm. Không suy rằng secret manager tự động xoay vòng mọi loại credential hoặc mọi rotation đều không gián đoạn.

### 3.3. Cấp secret lúc runtime

Một luồng phổ biến:

1. Workload được nền tảng xác minh danh tính.
2. Workload yêu cầu secret cụ thể từ secret manager.
3. Secret manager kiểm tra policy và trả credential nếu principal được phép.
4. Ứng dụng dùng secret trong phạm vi cần thiết.
5. Secret không được ghi vào log, exception, metric label hoặc file tạm không bảo vệ.
6. Hành động truy cập và thay đổi secret được audit.

| Cách | Mô tả | Ưu điểm | Đánh đổi |
|---|---|---|---|
| Fetch qua SDK/API | Ứng dụng gọi secret manager lúc startup hoặc khi cần refresh | Chủ động version/cache/refresh | Code phải quản lý timeout, retry, cache và lỗi dịch vụ |
| Mount/inject thành file hoặc environment | Nền tảng/agent đưa secret vào runtime | Code đơn giản hơn, có thể tích hợp mount | Có thể lộ qua process environment, debug, file permissions hoặc snapshot; cập nhật không phải lúc nào cũng được ứng dụng tự đọc lại |

Với secret nhạy cảm, fetch theo identity và chỉ giữ trong bộ nhớ khi cần có thể giảm việc secret nằm trong file hoặc environment lâu dài. Đây không phải bảo đảm tuyệt đối: memory dump, debug endpoint và heap dump vẫn cần được kiểm soát.

### 3.4. Rotation không gây gián đoạn

Một cách tiếp cận thường dùng là overlap credential:

1. Tạo credential phiên bản mới.
2. Cấp quyền và xác minh credential mới hoạt động.
3. Cập nhật workload để sử dụng phiên bản mới.
4. Quan sát các replica đã chuyển đổi và lỗi kết nối.
5. Thu hồi credential cũ sau khi chắc chắn không còn client phụ thuộc.

Với database, có thể cần hai principal hoặc cơ chế rotation mà nhà cung cấp hỗ trợ. Nếu thay mật khẩu user ngay lập tức trong khi một số replica vẫn dùng giá trị cũ, request sẽ lỗi. Với mTLS, cần quản lý thời gian overlap giữa trust bundle, certificate mới và certificate cũ.

**Rotation không phải chỉ thay một chuỗi ký tự.** Đó là rollout phối hợp giữa nơi cấp secret, consumer, cache, kết nối đang mở và cơ chế thu hồi.

## 4. Workload identity: mỗi ứng dụng có danh tính riêng

Khi workload gọi cloud service, hệ thống cần biết caller là ai. Access key dài hạn tạo ra nhiều vấn đề: phải lưu, phân phối, xoay vòng và thu hồi; nếu lọt vào image hoặc Git thì khó kiểm soát toàn bộ bản sao.

**Workload identity** cho phép nền tảng xác minh workload và cấp credential hoặc token ngắn hạn theo policy. Mục tiêu là giảm hoặc loại bỏ secret tĩnh dùng cho xác thực giữa workload và cloud API.

Ví dụ:
- Booking API cần đọc một secret và ghi dữ liệu booking.
- Notification Worker chỉ cần đọc queue và lấy credential gửi email.
- CI/CD có quyền deploy Booking API nhưng không được đọc dữ liệu thanh toán.
- Monitoring agent chỉ được gửi telemetry.

Nếu cả bốn dùng chung một service account/role admin, lỗi hoặc xâm nhập một workload có thể mở rộng sang hệ thống khác.

### 4.1. Authentication khác authorization

- **Authentication:** Hệ thống xác minh principal nào đang yêu cầu.
- **Authorization:** Principal đó được phép thực hiện action nào trên resource nào.

Workload identity giúp thiết lập authentication và cung cấp principal để policy đánh giá. Nó không tự quyết định mọi quyền ứng dụng.

Ví dụ, booking-api-prod đã được xác thực nhưng chỉ được đọc secret booking/prod/payment-api-client, truy cập dữ liệu booking cần thiết và gọi API tạo payment intent. Nó không được xóa audit log, thay IAM policy hoặc gọi API refund nếu nghiệp vụ không cho phép.

### 4.2. Credential ngắn hạn và federation

Một mô hình phổ biến là workload nhận token chứng minh danh tính từ môi trường chạy, rồi dùng token đó để đổi lấy credential cloud ngắn hạn. Với federation, cloud trust một issuer hoặc identity provider được cấu hình, kiểm tra claims và điều kiện trước khi cấp role/token.

Claims có thể gồm subject, audience, issuer, namespace, service account, repository hoặc workload attributes tùy nền tảng. **Trust policy phải giới hạn chính xác đối tượng được tin cậy**, không chỉ cho phép mọi token phát ra từ một issuer.

Không đưa token federation vào log; token ngắn hạn vẫn là credential cho tới lúc hết hạn hoặc bị thu hồi theo cơ chế hỗ trợ.

## 5. Cơ chế workload identity trên các nền tảng cloud

| Nền tảng | Cơ chế phổ biến | Kịch bản |
|---|---|---|
| **AWS** | IAM role cho compute (EC2 instance profile, ECS task role), IAM Roles for Service Accounts (IRSA) hoặc EKS Pod Identity | Pod/service nhận role riêng thay cho lưu access key |
| **Azure** | Managed Identity (system-assigned hoặc user-assigned), Workload Identity Federation cho workload phù hợp | VM, App Service, Container Apps, AKS hoặc pipeline lấy token theo identity |
| **Google Cloud** | Service Account gắn với workload, Workload Identity Federation, Workload Identity cho GKE | Compute hoặc Kubernetes workload truy cập Google Cloud API mà không nhúng key JSON |

Các cơ chế không hoàn toàn tương đương về cách trust, token exchange, giới hạn, networking và audit. Cần kiểm tra dịch vụ/phiên bản đang dùng trước khi chọn.

### 5.1. AWS

EC2 instance có thể gắn instance profile chứa IAM role; ứng dụng lấy temporary credentials qua metadata service với biện pháp bảo vệ phù hợp. ECS task role gắn credential với task. Với EKS, IRSA hoặc EKS Pod Identity cho phép cấp quyền theo Kubernetes workload thay vì dùng role rộng của node cho tất cả pod.

Cần tránh dùng access key của developer trong image, cho toàn bộ node role quyền đọc mọi secret, trust condition quá rộng cho mọi service account hoặc để pod truy cập metadata credential của node khi không cần nếu nền tảng có thể hạn chế.

### 5.2. Azure

Managed Identity cho phép workload lấy token thông qua nền tảng mà không lưu client secret. System-assigned identity gắn vòng đời với resource; user-assigned identity tồn tại độc lập và có thể gắn vào nhiều resource theo nhu cầu. Việc chia sẻ một identity giữa nhiều workload cần cân nhắc blast radius và trách nhiệm thu hồi.

Với AKS, Workload Identity sử dụng federation giữa Kubernetes service account và Microsoft Entra application/managed identity theo cấu hình phù hợp. Trust cần giới hạn đúng issuer, subject và audience. Không gắn một identity có quyền rộng cho mọi pod chỉ để đơn giản hóa cấu hình.

### 5.3. Google Cloud

Google Cloud service account đại diện cho workload hoặc ứng dụng. Workload Identity Federation giúp workload bên ngoài Google Cloud hoặc môi trường Kubernetes được xác minh qua identity provider tin cậy và nhận quyền phù hợp. Trong GKE, Workload Identity cho phép Kubernetes service account ánh xạ tới Google Cloud IAM principal theo cấu hình.

Tránh tải service account key JSON lên image, lưu ở repository hoặc chia sẻ giữa các nhóm. Nếu có trường hợp đặc biệt cần key tĩnh, phải có lý do rõ, scope hẹp, bảo vệ nơi lưu và kế hoạch rotation/revocation.

## 6. Cấu hình và định danh trong Kubernetes

Kubernetes có các primitive để cấu hình workload; cần hiểu giới hạn của từng loại.

### 6.1. ConfigMap

**ConfigMap** lưu dữ liệu cấu hình không nhạy cảm. Có thể cung cấp qua environment variable hoặc mount thành file. ConfigMap không phải secret store và dữ liệu không được bảo vệ như credential chỉ vì được lưu trong Kubernetes API.

~~~yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: booking-api-config
  namespace: booking-prod
data:
  APP_ENV: "prod"
  LOG_LEVEL: "info"
  PAYMENT_API_URL: "https://payments.internal"
  REQUEST_TIMEOUT_MS: "1500"
~~~

### 6.2. Secret

Kubernetes **Secret** lưu dữ liệu nhạy cảm dưới dạng dữ liệu được mã hóa biểu diễn (thường là base64 khi xuất YAML), nhưng **base64 không phải mã hóa**. Mặc định, mức bảo vệ dữ liệu trong etcd phụ thuộc cấu hình cluster; cần encryption at rest, RBAC hạn chế, bảo vệ backup và kiểm soát quyền truy cập API.

~~~yaml
apiVersion: v1
kind: Secret
metadata:
  name: booking-db-credential
  namespace: booking-prod
type: Opaque
stringData:
  username: "booking_runtime"
  password: "INJECT_AT_DEPLOYMENT_TIME"
~~~

Đây là placeholder, không phải mật khẩu có thể dùng. Không đưa secret thật vào file YAML, Git hoặc lệnh shell lưu trong lịch sử. Có thể tích hợp external secret manager qua CSI driver hoặc controller phù hợp, nhưng phải xem cơ chế đồng bộ, quyền đọc và vòng đời secret.

### 6.3. ServiceAccount và RBAC

Kubernetes ServiceAccount cung cấp danh tính cho pod khi tương tác với Kubernetes API; Kubernetes RBAC giới hạn quyền trong cluster. Nó **khác với cloud IAM identity**, dù có thể được federation/ánh xạ để workload truy cập cloud service.

~~~yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: booking-api
  namespace: booking-prod
automountServiceAccountToken: false
~~~

Nếu pod không cần gọi Kubernetes API và không cần token service account, có thể tắt tự động mount theo cấu hình phù hợp. Nếu cần truy cập API, cấp token và quyền đúng scope; không tắt token một cách máy móc khiến workload không hoạt động.

Ví dụ RBAC cho workload chỉ đọc ConfigMap trong namespace:

~~~yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: booking-config-reader
  namespace: booking-prod
rules:
  - apiGroups: [""]
    resources: ["configmaps"]
    verbs: ["get", "list"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: booking-config-reader-binding
  namespace: booking-prod
subjects:
  - kind: ServiceAccount
    name: booking-api
    namespace: booking-prod
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: Role
  name: booking-config-reader
~~~

Đây chỉ là quyền Kubernetes API trong namespace. Nó không tự cấp quyền đọc secret manager bên ngoài hoặc gọi Payments API; quyền đó được cấp qua cơ chế identity/policy tương ứng.

### 6.4. Đưa ConfigMap và Secret vào Pod

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: booking-api
  namespace: booking-prod
spec:
  replicas: 3
  selector:
    matchLabels:
      app: booking-api
  template:
    metadata:
      labels:
        app: booking-api
    spec:
      serviceAccountName: booking-api
      containers:
        - name: api
          image: registry.example.com/booking-api:1.4.2
          envFrom:
            - configMapRef:
                name: booking-api-config
          env:
            - name: DB_USERNAME
              valueFrom:
                secretKeyRef:
                  name: booking-db-credential
                  key: username
            - name: DB_PASSWORD
              valueFrom:
                secretKeyRef:
                  name: booking-db-credential
                  key: password
          ports:
            - name: http
              containerPort: 8080
~~~

Ví dụ cho thấy cách wiring. Với production, cần kiểm soát cách Secret được tạo/cập nhật, encryption at rest trong Kubernetes, quyền get/list/watch Secret, quyền đọc manifest và khả năng secret lộ qua debug/process environment. Nếu dùng CSI/external secret operator, cách cập nhật file mount và restart/reload ứng dụng tùy driver/controller.

### 6.5. Pod identity không đồng nghĩa node identity

Nhiều workload cùng chạy trên một node không nên mặc nhiên dùng chung quyền của node. Nếu pod lấy được credential node-level, một pod bị xâm nhập có thể truy cập nhiều tài nguyên hơn dự kiến. Ưu tiên identity theo pod/service account hoặc task, hạn chế metadata access khi nền tảng hỗ trợ, và tách quyền của node agent khỏi ứng dụng.

## 7. Phân phối cấu hình và secret an toàn trong CI/CD

Pipeline triển khai là một đường vào quan trọng. Cách truyền cấu hình/secret phải tránh để bí mật tồn tại trong source, artifact hoặc log.

1. Build image không chứa secret môi trường.
2. Quét image và artifact để phát hiện secret vô tình bị đóng gói.
3. Gắn cấu hình không nhạy cảm ở bước deploy hoặc qua config service.
4. Khi workload chạy, identity của nó xin đúng secret cần dùng.
5. Policy admission/cluster/cloud kiểm tra cấu hình triển khai theo baseline.
6. Theo dõi rollout, lỗi đọc secret, thời hạn token/certificate và hành vi truy cập.
7. Khi thay secret, dùng rotation có overlap và xác minh replica đã chuyển đổi.

~~~mermaid
flowchart LR
    SRC["Source + code review"] --> BUILD["Build image without secrets"]
    BUILD --> SCAN["Scan dependencies / image / secrets"]
    SCAN --> REG["Image registry"]
    REG --> DEPLOY["Deploy with non-secret config"]
    DEPLOY --> ID["Workload identity"]
    ID --> SM["Secret manager"]
    SM --> APP["Runtime application"]
    SM -. "Access audit" .-> LOG["Audit / monitoring"]
~~~

Không truyền secret bằng build argument hoặc ghi vào Dockerfile như cách lưu credential; dữ liệu build có thể xuất hiện trong image history, layer hoặc log tùy cơ chế. Docker BuildKit secret mount có thể phù hợp với secret chỉ cần trong build step, nhưng không nên dùng để đóng gói runtime credential vào image.

Một số quy tắc:
- Không commit .env có secret; chỉ commit .env.example với giá trị giả và mô tả.
- Mask secret trong pipeline log, nhưng không dựa hoàn toàn vào masking vì secret có thể được encode, chia nhỏ hoặc in qua debug.
- Dùng OIDC/workload federation nếu có thể thay credential dài hạn của pipeline.
- Tách role build, publish artifact và deploy production.
- Có quy trình revoke nếu phát hiện secret bị lộ; xóa file khỏi commit mới chưa làm credential cũ mất hiệu lực.

## 8. Cập nhật cấu hình, secret và khả năng phục hồi

### 8.1. Config reload

Khi config thay đổi, container có thể nhận giá trị mới qua rollout, mount hoặc config agent. Cần quyết định ứng dụng đọc lại file theo chu kỳ hay chỉ lúc startup; khi cấu hình không hợp lệ thì giữ bản cũ hay dừng tiến trình; các replica có cần cập nhật đồng bộ hay có thể lệch phiên bản; có cần ghi config version vào log/metric; và cách rollback.

Không để config thay đổi âm thầm mà không có audit và version. Với tham số ảnh hưởng nghiệp vụ như giới hạn đặt chỗ hoặc feature flag, cần owner, approval và cách kiểm tra phạm vi áp dụng.

### 8.2. Secret rotation và cache

Ứng dụng có thể cache secret để giảm số lần gọi secret manager và tránh phụ thuộc dịch vụ mỗi request. Nhưng cache phải có thời hạn và cơ chế refresh. TTL quá dài làm việc thu hồi chậm; không cache có thể khiến hệ thống bị ảnh hưởng khi secret manager gián đoạn.

Chiến lược tham khảo:
- Fetch secret khi startup và cache có giới hạn.
- Refresh trước thời điểm hết hạn/rotation.
- Khi credential mới không hợp lệ, không ghi credential vào error log; fallback theo chính sách đã định.
- Không tự động dùng vô thời hạn credential cũ khi đã bị thu hồi.
- Với nhiều replica, rollout dần và hỗ trợ cả credential cũ lẫn mới trong khoảng overlap được kiểm soát.

### 8.3. Khi secret manager không khả dụng

Đây là một phụ thuộc vận hành. Cần quyết định workload có thể tiếp tục với secret đang cache trong bao lâu, hay phải từ chối khởi động. Không có một đáp án chung:

- API đang chạy có thể tiếp tục dùng credential hợp lệ trong bộ nhớ cho tới hết thời hạn.
- Pod mới không có secret và không có cache có thể không khởi động được.
- Worker có thể tiếp tục xử lý job không cần secret, nhưng không nên ghi thành công nếu chưa gọi được nhà cung cấp.
- Quy trình khẩn cấp phải tránh phát tán password tĩnh dùng chung chỉ để cho ứng dụng chạy lại.

Đánh giá phụ thuộc này trong RTO, quy trình recovery, quota và availability target.

## 9. Bảo vệ cấu hình và secret khỏi rò rỉ

| Vị trí | Rủi ro | Kiểm soát |
|---|---|---|
| Source control | Secret trong commit hoặc history | Secret scanning, revoke/rotate, protected branch |
| Container image | Secret nằm trong layer hoặc metadata | Build không chứa runtime secret, scan image |
| Environment/process | Có thể lộ qua debug, crash dump hoặc quyền đọc process | Giới hạn process access, tránh dump chứa secret |
| Kubernetes API/etcd | Người có RBAC rộng đọc secret; backup có thể chứa dữ liệu | RBAC tối thiểu, encryption at rest, backup protection |
| CI/CD log | Lệnh debug hoặc error in secret | Masking, tránh echo/env dump, kiểm tra log |
| Application log/trace | Token, Authorization header, connection string | Redaction, allowlist field và kiểm thử |
| Temporary file | File secret bị copy, lưu trong volume không bảo vệ | Hạn chế file, permissions, memory-backed volume khi phù hợp |
| Developer laptop | Secret được tải về và lưu cục bộ | Ưu tiên runtime access, endpoint policy, device control |
| Support bundle | Heap dump/config snapshot chứa dữ liệu nhạy cảm | Sanitize, encryption, restricted access và retention |

**Base64 không phải mã hóa**, và private network không ngăn workload đã bị xâm nhập đọc secret nếu IAM cho phép. Security phải kết hợp identity, authorization, bảo vệ nơi lưu, mã hóa, giám sát và quy trình phản ứng khi lộ credential.

Khi phát hiện secret có nguy cơ bị lộ:

1. Xác định loại credential và tài nguyên mà nó cho phép truy cập.
2. Revoke/rotate theo ưu tiên rủi ro, có kiểm soát để không làm gián đoạn ngoài dự kiến.
3. Kiểm tra audit log để xác định thời điểm, principal và phạm vi sử dụng.
4. Tìm các bản sao trong image, Git, log, artifact, cache hoặc backup.
5. Cập nhật workload, xác nhận credential mới hoạt động và credential cũ không còn dùng được.
6. Ghi incident, nguyên nhân và biện pháp phòng ngừa tái diễn.

## 10. Quản lý cấu hình theo nhiều môi trường

Dev, staging và prod thường dùng cùng code nhưng khác endpoint, secret và quyền. Không nên chỉ thay APP_ENV rồi cho rằng mọi thứ đã được cách ly.

| Thành phần | Dev | Staging | Production |
|---|---|---|---|
| Identity | Role dev và scope hẹp | Role staging | Role prod được giới hạn và review |
| Secret | Credential sandbox | Credential staging | Credential production riêng |
| Database | Dataset thử nghiệm | Dataset gần prod nhưng dữ liệu được kiểm soát | Dữ liệu thật với bảo vệ phù hợp |
| API endpoint | Môi trường mock/sandbox | Endpoint kiểm thử | Endpoint production private/được kiểm soát |
| Logging | Debug nếu cần, tránh secret | Info và trace kiểm thử | Log có kiểm soát dữ liệu, retention/audit |
| Config changes | Linh hoạt trong phạm vi nhóm | Theo quy trình kiểm thử | Review/approval và theo dõi version |
| Access | Developer theo nhóm | QA/Release roles | Quyền deploy/runtime tách biệt, admin JIT |

Không copy secret prod sang staging để giống dữ liệu thật. Nếu cần kiểm thử tích hợp, dùng credential riêng, dữ liệu đã khử định danh hoặc dữ liệu tổng hợp, và endpoint sandbox khi có thể.

Một naming convention minh họa cho config và secret:

~~~text
booking/dev/database/username
booking/dev/database/password
booking/staging/payment-api/client-token
booking/prod/database/credential
booking/prod/payment-api/client-certificate
~~~

Đây là quy ước minh họa, không phải cú pháp bắt buộc của secret manager. Chọn cấu trúc theo khả năng phân cấp, version, policy và giới hạn tên của nền tảng.

## 11. Đánh đổi theo các khía cạnh Well-Architected

| Khía cạnh | Lợi ích của thiết kế tốt | Rủi ro/chi phí | Câu hỏi review |
|---|---|---|---|
| **Độ tin cậy** | Credential có thể renew; config có version; workload thay thế được | Secret manager/IdP lỗi khiến pod mới không lấy được secret; rotation lỗi làm replica mất kết nối | Có cache hợp lý, overlap, rollback và diễn tập rotation không? |
| **Bảo mật** | Least privilege, workload identity, secret manager, audit | Token/secret bị lộ qua log, heap dump hoặc quyền cloud rộng | Ai có thể đọc từng secret? Có cách revoke và truy vết không? |
| **Khả năng mở rộng** | Nhiều replica nhận identity và config độc lập | Đồng loạt fetch secret gây throttling; config rollout lệch version | Có cache, jitter, rate control và refresh an toàn không? |
| **Hiệu năng** | Credential lấy theo nhu cầu, config phù hợp runtime | Thêm network call đến secret manager hoặc identity provider | Độ trễ bootstrap, refresh và token exchange được đo chưa? |
| **Chi phí** | Giảm quản lý key tĩnh và incident; quyền tự động hóa rõ | Phí secret operations, KMS, HSM, controller và audit | Dịch vụ nào cần mức bảo vệ đắt hơn? Có loại bỏ secret không dùng? |
| **Vận hành** | Rotation/audit/config rollout có thể tự động hóa | Tăng thành phần phụ thuộc, policy và quy trình xử lý | Có owner, runbook, cảnh báo expiry và quy trình break-glass phù hợp? |
| **Bền vững** | Giảm tài nguyên và credential tồn tại lâu hơn nhu cầu | Secret/version cũ, config hoặc identity không còn dùng vẫn tích tụ | Có lifecycle, TTL và lịch rà soát/xóa không? |

### Một số tình huống cần cân nhắc

**Environment variable hay file mount?** Environment variable dễ cấu hình nhưng có thể lộ qua process inspection hoặc debug; file mount có thể quản lý permission tốt nhưng tạo bản sao trên filesystem/volume và cần xử lý cập nhật. Chọn theo threat model, nền tảng và khả năng ứng dụng reload.

**Fetch secret mỗi request hay cache?** Fetch mỗi request có thể tăng latency, cost và phụ thuộc secret manager; cache lâu tăng thời gian sử dụng credential cũ. Thực tế thường chọn cache có TTL, refresh và policy rõ.

**Một identity cho nhiều service hay một identity mỗi workload?** Chia sẻ làm đơn giản hóa onboarding nhưng tăng blast radius, khó truy vết. Tách identity tạo nhiều policy hơn và cần tự động hóa.

**Secret manager hay Kubernetes Secret?** Kubernetes Secret thuận tiện cho tích hợp pod, nhưng cluster admin/RBAC/etcd/backup trở thành phạm vi bảo vệ. External secret manager có thể tập trung vòng đời nhưng thêm phụ thuộc mạng, controller và quyền federation. Một số môi trường dùng kết hợp; cần biết bản secret nào là nguồn chuẩn và bản nào được đồng bộ.

## 12. Kiểm thử và quan sát vòng đời config/secret/identity

Thiết kế cần có cả kiểm thử dương tính (được phép) và âm tính (bị từ chối).

| Kiểm thử | Kết quả mong đợi | Bằng chứng |
|---|---|---|
| Deploy cùng image ở dev và staging | Ứng dụng nhận endpoint/config khác đúng môi trường | Config version, startup validation |
| Pod Booking API đọc secret của mình | Thành công với identity đúng | Secret audit log, workload principal |
| Booking API đọc secret của Payments admin | Bị từ chối | IAM decision/denied audit |
| Pod không có workload identity | Không lấy được cloud credential | Token/federation log và denied event |
| Secret rotation | Replica mới dùng credential mới; replica cũ được chuyển đổi rồi revoke | Rotation event, connection metrics |
| Secret manager tạm lỗi | Workload phản ứng theo chính sách cache/startup | Error metrics, readiness, runbook |
| Log có Authorization header | Giá trị nhạy cảm bị redaction | Log test, scanning |
| Pod không cần Kubernetes API | Không tự mount token nếu đã cấu hình không dùng | Pod spec và API audit |
| Credential cũ bị thu hồi | Request dùng credential cũ bị từ chối | Provider audit và application error metric |
| Thay config dynamic | Replica nhận version mới/rollback theo quy tắc | Config version và rollout status |

### Chỉ số và cảnh báo nên theo dõi

- Secret sắp hết hạn, certificate sắp hết hạn, rotation trễ hoặc thất bại.
- Lượt đọc secret theo principal, secret không được dùng hoặc truy cập đột biến.
- Token issuance/federation errors, credential exchange latency và denied authorization.
- Startup failure vì thiếu config/secret, số lần restart và readiness.
- Config version theo replica, số replica chưa cập nhật và lỗi reload.
- IAM policy thay đổi, workload identity mới được cấp và scope quyền bất thường.
- Secret scanning findings trong repository, artifact và image registry.

Không log giá trị secret để debug các chỉ số này. Ghi secret identifier, version, principal, operation và kết quả theo phạm vi an toàn; tránh log payload hoặc token.

## 13. Quy trình thiết kế và triển khai thực tế

1. **Kiểm kê cấu hình:** Liệt kê các biến, file, feature flag, endpoint, timeout và giá trị mặc định.
2. **Phân loại dữ liệu:** Đánh dấu giá trị không nhạy cảm, secret, key hoặc certificate; xác định nguồn dữ liệu chuẩn.
3. **Thiết kế danh tính:** Tạo principal riêng cho mỗi workload và pipeline; chỉ cấp quyền cần thiết theo môi trường.
4. **Chọn nguồn cấu hình/secret:** ConfigMap/config service cho cấu hình; secret manager/KMS/key vault cho bí mật và khóa; identity federation cho credential runtime.
5. **Thiết kế phân phối:** Environment, mounted file, SDK/API hoặc CSI/controller; xác định TTL, cache, reload và failure behavior.
6. **Thiết kế rotation:** Owner, lịch, overlap, rollout, verify và revoke; quy định xử lý credential bị lộ khẩn cấp.
7. **Bảo vệ đường build/deploy:** Không đóng secret runtime trong image; scan source/artifact; build và deploy dùng identity khác nhau.
8. **Kiểm thử quyền:** Kiểm tra workload đúng đọc được secret cần thiết và workload khác bị từ chối; thử access ngoài scope.
9. **Thiết kế quan sát:** Audit access, version config, expiry, lỗi token/secret, startup và rotation.
10. **Vận hành liên tục:** Rà quyền, xóa secret/identity cũ, cập nhật runbook, diễn tập rotation và incident.

### ADR minh họa — Cấp database credential bằng workload identity

> **Bối cảnh:** Booking API chạy ba replica trong Kubernetes. Hiện tại database password được lưu trong một tệp cấu hình dùng chung cho dev và production.
>
> **Quyết định:** Tách principal database theo môi trường; cấp cloud workload identity cho Kubernetes service account; workload dùng identity để truy cập secret manager hoặc cơ chế xác thực database ngắn hạn được nền tảng hỗ trợ. Image không chứa credential. Cấu hình endpoint và pool size lấy từ ConfigMap/config service.
>
> **Lý do:** Giảm nguy cơ lộ secret trong Git/image và giới hạn quyền theo workload, môi trường.
>
> **Đánh đổi:** Thêm cấu hình federation, IAM policy, secret provider, audit và quy trình rotation; pod mới phụ thuộc identity/secret service khi khởi động.
>
> **Kiểm chứng:** Dev không đọc được secret prod; Booking API đọc được đúng credential; credential cũ bị revoke sau rotation; pod restart khi secret manager gián đoạn phản ứng theo runbook.
>
> **Điều kiện xem xét lại:** Nền tảng thay đổi cơ chế identity, database hỗ trợ token-based auth tốt hơn, số workload tăng hoặc yêu cầu RTO thay đổi.

## 14. Bài tập thực hành

Một hệ thống thương mại điện tử đang chạy ba container: Order API, Payment Worker và Report Worker. Cả ba dùng chung một file .env có database password, API key thanh toán và cloud access key. File này được lưu trong repository nội bộ; mọi workload có thể đọc toàn bộ biến. Khi triển khai staging, nhóm chỉ thay APP_ENV nhưng vẫn dùng chung cloud key production. Một lần log debug đã in toàn bộ environment vào CI log.

**Yêu cầu:**

1. Chia danh sách biến thành cấu hình, secret và định danh/policy.
2. Xác định ít nhất năm rủi ro do dùng chung .env và cloud access key.
3. Thiết kế identity riêng cho Order API, Payment Worker, Report Worker và CI/CD.
4. Chọn secret manager/config mechanism phù hợp; giải thích cách workload lấy giá trị lúc runtime.
5. Đề xuất quy trình rotation không làm gián đoạn thanh toán.
6. Nêu cách xử lý secret đã xuất hiện trong repository và CI log.
7. Viết bảng kiểm thử cho dev/staging/prod, gồm truy cập được phép và bị từ chối.
8. Nếu dùng Kubernetes, mô tả vai trò ConfigMap, Secret, ServiceAccount, RBAC và workload identity.

### Hướng giải quyết

- Loại credential khỏi repository và log. Nếu credential đã commit hoặc lộ, coi là có khả năng bị xâm phạm và rotate/revoke, kể cả khi commit mới đã xóa file.
- Phân principal theo workload: Order API chỉ đọc/ghi order; Payment Worker có quyền xử lý thanh toán và queue cần thiết; Report Worker có quyền đọc dữ liệu được cấp hoặc kho báo cáo; CI/CD có quyền deploy nhưng không cần runtime secret.
- Phân môi trường: dev/staging/prod có endpoint, identity, database principal và secret riêng; không dùng cloud key prod ở staging.
- Cấu hình không nhạy cảm như APP_ENV, LOG_LEVEL, timeout và API endpoint đặt trong config service/ConfigMap tùy môi trường.
- Dùng secret manager và workload identity; nếu bắt buộc mount thành file hoặc Kubernetes Secret, giới hạn RBAC, encryption at rest và vòng đời đồng bộ.
- Rotation: tạo credential mới, xác minh quyền, rollout các worker, quan sát lỗi, rồi thu hồi credential cũ. Với thanh toán, kiểm tra giao dịch đang xử lý và callback/webhook.
- Xử lý log lộ: hạn chế quyền truy cập, retention và bản sao; revoke credential, đánh giá log đã được tải xuống/chia sẻ chưa, lưu incident record.
- Kiểm thử: workload chỉ đọc secret của mình; dev không đọc prod; Report Worker không gọi API thanh toán nếu không có yêu cầu; CI/CD chỉ deploy đúng ứng dụng; log không chứa token hoặc password.

### Câu hỏi tự kiểm tra

1. Vì sao URL database có thể là config nhưng connection string có password cần được bảo vệ như secret?
2. Vì sao base64 của Kubernetes Secret không phải mã hóa?
3. Workload identity khác gì với IAM policy hoặc Kubernetes RBAC?
4. Khi một pod có service account riêng, điều gì cần thêm để pod gọi được cloud API?
5. Vì sao rotation cần overlap và kiểm tra consumer trước khi revoke credential cũ?
6. Khi secret manager lỗi, nên cache secret bao lâu và dựa vào yêu cầu nào để quyết định?
7. Làm thế nào bảo đảm pipeline deploy không thừa hưởng quyền runtime hoặc quyền quản trị không cần thiết?

Một kiến trúc container tốt quản lý **cấu hình như dữ liệu vận hành có version**, **bí mật như tài sản nhạy cảm có vòng đời**, và **định danh workload như cơ sở để cấp quyền theo nguyên tắc tối thiểu**. Khi ba phần được thiết kế riêng nhưng phối hợp đúng, cùng một image có thể triển khai an toàn ở nhiều môi trường, workload có thể thay thế và mở rộng, còn việc xoay vòng hoặc thu hồi credential có thể được kiểm soát và kiểm toán.
