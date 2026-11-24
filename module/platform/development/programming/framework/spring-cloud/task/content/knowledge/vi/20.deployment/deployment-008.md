# ConfigMap, Secret và tài khoản dịch vụ

## 1. Vì sao ba thành phần này quan trọng với Spring Cloud Task?

**Spring Cloud Task** được dùng để xây dựng các ứng dụng Spring Boot có **thời gian chạy hữu hạn**: khởi động, nhận tham số, thực hiện công việc, ghi lại kết quả trong **TaskRepository** rồi kết thúc. Khi đưa ứng dụng lên Kubernetes, một `Job` có thể tạo Pod để chạy task một lần; `CronJob` có thể tạo Job theo lịch.

Một ứng dụng task đối soát cuối ngày thường cần ít nhất:

- **Cấu hình vận hành không bí mật:** profile, tên task, nơi xuất báo cáo, các ngưỡng xử lý.
- **Thông tin xác thực:** URL hoặc tài khoản kết nối cơ sở dữ liệu metadata, mật khẩu, token gọi dịch vụ ngoài.
- **Danh tính khi tương tác Kubernetes API:** Pod có được phép đọc Pod khác, tạo Job, hoặc đọc ConfigMap qua API không?
- **Chính sách kết thúc:** khi nào Job được coi là thành công/thất bại, thử lại ra sao, hết hạn lúc nào, log và metadata được giữ ở đâu?

Kubernetes có ba đối tượng quan trọng cho những nhu cầu này:

1. **`ConfigMap`:** chứa cấu hình **không bí mật**, tách khỏi container image.
2. **`Secret`:** lưu hoặc tham chiếu dữ liệu nhạy cảm và cấp cho Pod khi cần.
3. **`ServiceAccount`:** danh tính của workload khi truy cập **Kubernetes API**; quyền được cấp qua RBAC hoặc tích hợp danh tính nền tảng.

Bài thuộc chương **Triển khai** sẽ ghép chúng vào một `Job` chạy Spring Cloud Task, giải thích đường đi của cấu hình, quyền tối thiểu và các điểm cần kiểm chứng trước production.

### Mục tiêu học tập

Sau bài này, bạn có thể:

- Chọn đúng `ConfigMap`, `Secret` và `ServiceAccount` cho từng loại thông tin.
- Đọc, viết manifest Kubernetes cấp cấu hình và credentials cho một task hữu hạn.
- Giải thích `serviceAccountName`, `automountServiceAccountToken`, `Role` và `RoleBinding`.
- Phân biệt **Kubernetes ServiceAccount**, **tài khoản database**, **imagePullSecret** và danh tính cloud workload.
- Cấu hình kết nối `TaskRepository` bền vững và giải thích vì sao không nên dùng H2 in-memory trong production.
- Triển khai cùng image thành Kubernetes Job chạy theo yêu cầu hoặc CronJob theo lịch.
- Kiểm tra việc load cấu hình, thất bại do Secret/RBAC, exit code, Job status và metadata task.
- Thiết kế xoay vòng secret, retry, idempotency và giám sát khi Pod bị dừng bất thường.

## 2. Bảng so sánh: ConfigMap, Secret, ServiceAccount

| Đối tượng | Chứa hoặc biểu diễn | Ví dụ phù hợp | Không nên dùng để |
| --- | --- | --- | --- |
| **ConfigMap** | Cặp key-value hoặc tệp cấu hình **không bí mật** | `SPRING_PROFILES_ACTIVE`, `APP_REPORT_BUCKET`, chế độ xử lý | Lưu password, API token, khóa riêng |
| **Secret** | Dữ liệu cần bảo vệ, cấp cho container qua environment hoặc volume | `SPRING_DATASOURCE_PASSWORD`, token bên ngoài | Coi base64 là mã hóa bảo mật |
| **ServiceAccount** | Danh tính Kubernetes của Pod | `daily-task-sa` | Lưu mật khẩu PostgreSQL hoặc thay thế quyền SQL |
| **Role/RoleBinding** | Quyền của danh tính trên tài nguyên Kubernetes API | Chỉ cho phép `get` một tài nguyên khi thực sự cần | Cấp `cluster-admin` cho mọi task |
| **DB role** | Danh tính trong database, **khác ServiceAccount** | `task_writer` có quyền `INSERT/UPDATE` `TASK_EXECUTION` | Truy cập Kubernetes API |
| **imagePullSecret** | Credential để kubelet kéo image private | Secret registry | Truyền password database tới Java app |

**Tách bạch quan trọng:** `ServiceAccount` **không cấp quyền SELECT/INSERT PostgreSQL**. Nó là danh tính đối với Kubernetes API. Muốn task ghi `TaskRepository`, bạn vẫn cần cấu hình `DataSource` và database privileges phù hợp.

Với task không gọi Kubernetes API, có thể tạo ServiceAccount riêng nhưng **tắt tự động mount API token**. Việc Kubernetes truyền giá trị từ `ConfigMap`/`Secret` vào environment của Pod **không đòi hỏi bản thân ứng dụng phải gọi API để đọc các đối tượng đó**.

## 3. Kiến trúc mẫu

Giả sử tác vụ `daily-reconciliation` đọc dữ liệu nghiệp vụ của ngày `2026-11-23` và ghi trạng thái chạy vào PostgreSQL.

~~~mermaid
flowchart LR
    U["Operator / CronJob controller"] --> J["Kubernetes Job"]
    J --> P["Pod Spring Cloud Task"]
    C[("ConfigMap: profile, tên task, cấu hình không bí mật")] --> P
    S[("Secret: credentials DataSource")] --> P
    SA["ServiceAccount daily-task-sa"] --> P
    P --> T[("PostgreSQL: TASK_EXECUTION / TASK_EXECUTION_PARAMS")]
    P --> B[("Database nghiệp vụ")]
    P -. "Chỉ nếu chủ động gọi API" .-> K["Kubernetes API"]
    R["Role/RoleBinding nếu cần"] -. "Ủy quyền" .-> K
~~~

Có ba ranh giới bảo mật:

1. **Kubernetes control plane:** người hoặc controller nào được tạo Job, Pod, ConfigMap, Secret, ServiceAccount và RoleBinding.
2. **Runtime của container:** Java process nhận những biến/tệp cấu hình nào và có được mount Kubernetes API token hay không.
3. **Database và hệ thống ngoài:** tài khoản kết nối có được ghi metadata TaskRepository và xử lý nghiệp vụ không; đây là phạm vi quyền **độc lập** với Kubernetes RBAC.

Không nên cấp cho process task quyền quản trị cluster chỉ vì hạ tầng điều phối phải tạo Pod. Khi Spring Cloud Data Flow hoặc một Kubernetes controller là bên tạo Job, **danh tính của hệ thống điều phối** và **danh tính của Pod task** cần được phân quyền riêng.

## 4. Chuẩn bị ứng dụng Spring Cloud Task hữu hạn

Ví dụ Spring Boot sau nhận tham số ngày, chạy nghiệp vụ đồng bộ rồi trả về. Phần nghiệp vụ được rút gọn để tập trung vào triển khai.

~~~java
import java.time.LocalDate;
import java.util.List;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cloud.task.configuration.EnableTask;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
@EnableTask
public class DailyReconciliationApplication {

    private static final Logger log =
            LoggerFactory.getLogger(DailyReconciliationApplication.class);

    public static void main(String[] args) {
        SpringApplication.run(
                DailyReconciliationApplication.class, args);
    }

    @Bean
    ApplicationRunner reconcile() {
        return args -> {
            List<String> dates =
                    args.getOptionValues("businessDate");

            if (dates == null || dates.size() != 1) {
                throw new IllegalArgumentException(
                        "Required: --businessDate=yyyy-MM-dd");
            }

            LocalDate day = LocalDate.parse(dates.get(0));
            log.info("RECONCILIATION_BEGIN day={}", day);

            // Thực hiện nghiệp vụ đồng bộ.
            // Nếu thất bại, đừng âm thầm nuốt exception.

            log.info("RECONCILIATION_DONE day={}", day);
        };
    }
}
~~~

Cấu hình trong image, ví dụ `application.yml`:

~~~yaml
spring:
  main:
    web-application-type: none
  cloud:
    task:
      initialize-enabled: false
~~~

- `web-application-type: none` tránh khởi động HTTP server không cần thiết cho CLI task.
- `initialize-enabled: false` có nghĩa schema TaskRepository **phải đã tồn tại** do migration chuẩn bị; chỉ dùng khi đã quản lý schema tương ứng.
- `@EnableTask` kích hoạt tích hợp Spring Cloud Task trong ví dụ.
- `ApplicationRunner` chỉ kết thúc khi nghiệp vụ đã hoàn tất; không tạo công việc nền rồi trả về trước khi kết quả được ghi.
- Cần đóng gói Spring Cloud Task, JDBC driver và cấu hình tương thích với Spring Boot phiên bản dự án. Container image phải chứa jar tại đường dẫn sẽ được dùng trong Kubernetes manifest.

Để lưu metadata bền vững qua nhiều Pod, hãy dùng PostgreSQL/MySQL hoặc database phù hợp, thay vì một H2 in-memory riêng trong mỗi Pod. **TaskRepository** ghi thời gian và kết quả từng lần chạy; dữ liệu nghiệp vụ và checkpoint retry vẫn cần quản lý riêng.

## 5. ConfigMap: cấu hình không bí mật

Ví dụ `task-config.yaml`:

~~~yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: daily-task-config
  namespace: batch-jobs
data:
  SPRING_APPLICATION_NAME: "daily-reconciliation"
  SPRING_PROFILES_ACTIVE: "task"
  APP_REPORT_BUCKET: "reports-demo"
  APP_RECONCILE_MODE: "safe"
~~~

Các giá trị trong `data` đều là chuỗi. Khi sử dụng `envFrom.configMapRef`, mỗi key hợp lệ sẽ trở thành một biến môi trường trong container.

| Key | Tác dụng |
| --- | --- |
| `SPRING_APPLICATION_NAME` | Tên ứng dụng để Spring Boot và Spring Cloud Task sử dụng theo cấu hình tên task |
| `SPRING_PROFILES_ACTIVE` | Chọn profile mà image đã cung cấp |
| `APP_REPORT_BUCKET` | Ví dụ tên bucket nghiệp vụ không bí mật |
| `APP_RECONCILE_MODE` | Chế độ nghiệp vụ minh họa, do ứng dụng tự diễn giải |

**Không đặt secret vào ConfigMap.** Dù tên là “cấu hình”, một mật khẩu, private key, bearer token hoặc connection string có credential vẫn là dữ liệu nhạy cảm.

### Hai cách lấy giá trị từ ConfigMap

Lấy **tất cả** key hợp lệ:

~~~yaml
envFrom:
  - configMapRef:
      name: daily-task-config
~~~

Lấy **một key cụ thể**, đồng thời đặt lại tên biến:

~~~yaml
env:
  - name: SPRING_PROFILES_ACTIVE
    valueFrom:
      configMapKeyRef:
        name: daily-task-config
        key: SPRING_PROFILES_ACTIVE
~~~

Khi cấu hình phức tạp cần một tệp thay vì environment, ConfigMap còn có thể được mount thành volume. Với Spring Boot, phải cấu hình ứng dụng đọc đúng vị trí tệp đó; việc mount tự nó không bảo đảm Spring tự nạp mọi tệp bất kỳ.

### Hành vi cập nhật

ConfigMap được truyền qua **environment** chỉ được lấy khi container được tạo; sửa ConfigMap **không cập nhật environment của Pod đã chạy**. Với ứng dụng task hữu hạn, một lựa chọn dễ kiểm soát là tạo Job mới với image/config version rõ ràng. Giá trị mount qua ConfigMap volume có cơ chế cập nhật khác, nhưng ứng dụng vẫn cần nạp lại cấu hình nếu muốn thay đổi khi đang chạy.

**Không dựa vào việc thay ConfigMap giữa chừng để sửa tham số của một TaskExecution đang thực thi.** Điều đó có thể làm mất khả năng tái hiện kết quả.

## 6. Secret: mật khẩu và token không được hardcode

Task muốn dùng một PostgreSQL metadata database có thể nhận:

- `SPRING_DATASOURCE_URL` — JDBC URL (có thể coi là thông tin hạ tầng nhạy cảm theo chính sách tổ chức).
- `SPRING_DATASOURCE_USERNAME` — database principal.
- `SPRING_DATASOURCE_PASSWORD` — mật khẩu cần bảo vệ.

Trong ví dụ, đặt cả ba vào một Secret có tên `daily-task-db` trong namespace `batch-jobs`. Các **tên key** như trên là giao diện mà manifest Job kỳ vọng; **giá trị thật phải đến từ secret manager/quy trình cấp phát được phê duyệt**.

### 6.1. Tạo Secret từ nguồn an toàn

Ví dụ lệnh dành cho môi trường lab, **không chạy tại bước soạn tài liệu**:

~~~bash
kubectl create namespace batch-jobs

kubectl create secret generic daily-task-db \
  --from-env-file=./daily-task-db.local.env \
  --namespace=batch-jobs
~~~

Tệp `daily-task-db.local.env` được tạo tạm thời từ nguồn bí mật đã được cấp quyền, có đúng các key `SPRING_DATASOURCE_URL`, `SPRING_DATASOURCE_USERNAME`, `SPRING_DATASOURCE_PASSWORD`. **Không commit tệp đó lên Git, không in nội dung ra console/log và xử lý xóa/lưu trữ theo chính sách bảo mật**. Trong production, ưu tiên giải pháp đồng bộ Secret từ kho quản lý bí mật hoặc quy trình CI/CD đã được bảo vệ.

Nếu cần tự lưu YAML Secret, đừng coi `stringData` hoặc `data` mã hóa base64 là biện pháp bảo mật đủ mạnh: ai đọc được Secret từ Kubernetes API vẫn có thể lấy dữ liệu. **Bật encryption at rest cho Kubernetes Secrets (theo cấu hình cluster), kiểm soát RBAC, audit và quyền đọc sao lưu etcd.**

### 6.2. Truyền Secret vào Pod

Ví dụ lấy tất cả key đúng tên biến môi trường:

~~~yaml
envFrom:
  - secretRef:
      name: daily-task-db
~~~

Hoặc một biến riêng:

~~~yaml
env:
  - name: SPRING_DATASOURCE_PASSWORD
    valueFrom:
      secretKeyRef:
        name: daily-task-db
        key: SPRING_DATASOURCE_PASSWORD
~~~

Kubernetes đưa giá trị vào container; Spring Boot có thể bind `SPRING_DATASOURCE_PASSWORD` sang thuộc tính `spring.datasource.password`. **Không cần gắn Secret vào CLI bằng `--spring.datasource.password=...`**, vì đối số dòng lệnh dễ lộ qua process metadata hoặc công cụ quan sát.

### 6.3. Secret mount dưới dạng tệp

Một số thư viện cần chứng chỉ hoặc credential trong file. Khi đó, dùng `volume.secret` và `volumeMounts` thay vì environment. Nhưng **Spring Boot không tự đọc mọi đường dẫn file tùy ý**: cần chỉ định property/config tree hoặc code đọc chứng chỉ theo thư viện.

Sự khác biệt về cập nhật:

| Cách cung cấp | Khi Secret được thay đổi | Hướng xử lý |
| --- | --- | --- |
| **Environment variable** | Pod đang chạy **không tự nhận giá trị mới** | Tạo Pod/Job mới hoặc restart có kiểm soát |
| **Secret volume** | Kubelet có thể cập nhật nội dung volume sau một khoảng trễ | Ứng dụng phải hỗ trợ reload; tránh `subPath` nếu cần cập nhật |
| **Kết nối đã được mở** | Thay mật khẩu trong Secret không tự cập nhật connection pool hoặc phiên giao dịch | Có kế hoạch rotate credential và tái tạo kết nối |

Với task hữu hạn, thường dễ vận hành hơn khi một lần chạy được gắn với một phiên bản cấu hình/secret và sau đó kết thúc, thay vì đổi thông số trong lúc xử lý.

## 7. ServiceAccount: danh tính của Pod khi truy cập Kubernetes API

Mỗi Pod gắn với một `ServiceAccount` trong namespace. Nếu không chỉ định, Pod thường dùng ServiceAccount `default`. Nên tạo **ServiceAccount riêng cho ứng dụng task** để không vô tình kế thừa quyền rộng đã cấp cho default account.

Ví dụ `task-sa.yaml`:

~~~yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: daily-task-sa
  namespace: batch-jobs
automountServiceAccountToken: false
~~~

Khi Pod không cần gọi Kubernetes API, giá trị `automountServiceAccountToken: false` giúp tránh tự mount token API vào container. Có thể đặt thuộc tính đó ở **Pod spec**; nếu Pod spec và ServiceAccount đều chỉ định, giá trị ở Pod spec được ưu tiên.

### 7.1. Ba danh tính dễ nhầm

| Danh tính | Ví dụ | Ai xác thực? |
| --- | --- | --- |
| Kubernetes **ServiceAccount** | `system:serviceaccount:batch-jobs:daily-task-sa` | Kubernetes API |
| **Database user** | `task_writer` | PostgreSQL, MySQL... |
| **Cloud workload identity** | IAM role/service account liên kết với Kubernetes ServiceAccount | Nhà cung cấp cloud và cơ chế federation tương ứng |

Một Kubernetes ServiceAccount **không tự biến thành** IAM role hoặc DB user. Nếu ứng dụng dùng identity federation để đọc cloud bucket, phải thiết lập trust relationship/binding theo nhà cung cấp. Nếu dùng DB password trong Secret, tài khoản DB vẫn phải có quyền SQL thích hợp.

### 7.2. Có cần cấp Role/RoleBinding cho task này không?

**Không**, nếu ứng dụng Java chỉ nhận environment, đọc/ghi database và kết thúc, **không tự gọi Kubernetes API**. Kubernetes vẫn có thể đưa ConfigMap và Secret vào Pod theo spec; Java process không cần quyền `get secrets` qua API.

**Có thể cần**, khi mã ứng dụng thực sự gọi Kubernetes API, ví dụ đọc thông tin trạng thái Pod khác hoặc lấy một ConfigMap động qua client. Khi đó:

1. Cấp **Role** chỉ có verbs/resources cần thiết trong namespace.
2. Tạo **RoleBinding** gắn Role với ServiceAccount cụ thể.
3. Bảo đảm Pod nhận được phương thức xác thực Kubernetes API (mount token có kiểm soát hoặc projected token thích hợp).
4. Không cấp quyền tạo/sửa Pod, Job hoặc đọc Secret nếu nghiệp vụ không cần.

Ví dụ **chỉ dành cho trường hợp worker cần đọc Pod qua Kubernetes API**, không áp dụng cho task minh họa ở phần tiếp theo:

~~~yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: pod-status-reader
  namespace: batch-jobs
rules:
  - apiGroups: [""]
    resources: ["pods"]
    verbs: ["get", "list"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: task-pod-status-reader
  namespace: batch-jobs
subjects:
  - kind: ServiceAccount
    name: daily-task-sa
    namespace: batch-jobs
roleRef:
  kind: Role
  name: pod-status-reader
  apiGroup: rbac.authorization.k8s.io
~~~

`Role` giới hạn quyền trong namespace; `RoleBinding` gắn nó cho danh tính. Nếu app cần K8s API và dùng service account token mặc định, cần điều chỉnh `automountServiceAccountToken` một cách có kiểm soát. **Đừng triển khai Role/RoleBinding này cho task vốn không dùng Kubernetes API**, vì đó là quyền thừa.

## 8. Manifest Job đầy đủ cho Spring Cloud Task

Giả định đã chuẩn bị:

- Namespace `batch-jobs`.
- ConfigMap `daily-task-config` (phần 5).
- Secret `daily-task-db` (phần 6) có đúng ba key JDBC.
- ServiceAccount `daily-task-sa` (phần 7).
- Image `registry.example.com/tasks/daily-reconciliation:1.4.2` chứa Java runtime và `/app/task.jar`, có driver JDBC, tương thích DB/schema metadata.
- Database đã được khởi tạo bằng migration cho phiên bản Spring Cloud Task đang dùng.

Manifest `daily-task-job.yaml`:

~~~yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: daily-reconciliation-20261123
  namespace: batch-jobs
  labels:
    app: daily-reconciliation
    business-date: "2026-11-23"
spec:
  backoffLimit: 0
  activeDeadlineSeconds: 1800
  ttlSecondsAfterFinished: 86400
  template:
    metadata:
      labels:
        app: daily-reconciliation
    spec:
      serviceAccountName: daily-task-sa
      automountServiceAccountToken: false
      restartPolicy: Never
      terminationGracePeriodSeconds: 60
      securityContext:
        runAsNonRoot: true
        runAsUser: 10001
      containers:
        - name: task
          image: registry.example.com/tasks/daily-reconciliation:1.4.2
          imagePullPolicy: IfNotPresent
          command: ["java", "-jar", "/app/task.jar"]
          args:
            - "--businessDate=2026-11-23"
          envFrom:
            - configMapRef:
                name: daily-task-config
            - secretRef:
                name: daily-task-db
          resources:
            requests:
              cpu: "250m"
              memory: "256Mi"
            limits:
              cpu: "1"
              memory: "512Mi"
          securityContext:
            allowPrivilegeEscalation: false
            capabilities:
              drop: ["ALL"]
~~~

### 8.1. Giải thích từng lựa chọn

| Thuộc tính | Ý nghĩa | Lưu ý triển khai |
| --- | --- | --- |
| `apiVersion: batch/v1`, `kind: Job` | Chạy một công việc hữu hạn | Không dùng `Deployment` nếu không cần service chạy liên tục |
| `metadata.namespace` | Nhóm tài nguyên và quyền | Secret/ConfigMap được tham chiếu phải ở đúng namespace |
| `backoffLimit: 0` | Bài lab không tự tạo Pod retry khi Pod thất bại | Production chỉ tăng nếu xử lý lặp **idempotent** |
| `activeDeadlineSeconds: 1800` | Giới hạn tổng thời gian chạy Job, minh họa 30 phút | Vượt deadline có thể bị dừng đột ngột, TaskRepository không kịp cập nhật |
| `ttlSecondsAfterFinished: 86400` | Job đủ điều kiện tự dọn sau 24 giờ kể từ lúc hoàn tất | Không xóa bản ghi TaskRepository; Pod và log cục bộ có thể mất |
| `restartPolicy: Never` | Container lỗi không restart ngay trong cùng Pod | Job controller vẫn có thể tạo Pod khác nếu chính sách retry cho phép |
| `serviceAccountName` | Chọn danh tính Kubernetes của task | Không có quyền SQL/Cloud IAM chỉ nhờ tên này |
| `automountServiceAccountToken: false` | Không gắn API token cho task không cần API | Đổi nếu app cần API theo mô hình xác thực phù hợp |
| `envFrom` | Nạp biến môi trường từ ConfigMap và Secret | Tham chiếu sai/missing key có thể khiến Pod không chạy đúng |
| `resources` | Hạn mức CPU/RAM | OOMKill có thể làm TaskExecution thiếu thời điểm kết thúc |
| `runAsNonRoot` | Hạn chế quyền tiến trình container | Image/JAR cần cho phép UID chỉ định chạy và đọc file |
| `command`/`args` | Khởi chạy Java jar với tham số nghiệp vụ | Không đặt mật khẩu vào args |
| `terminationGracePeriodSeconds` | Thời gian tạo cơ hội xử lý SIGTERM | Không đảm bảo đủ thời gian nếu có SIGKILL hoặc deadline |

**Bản Job trên là ví dụ học tập, không phải cấu hình production mặc định.** Các số timeout, tài nguyên và phiên bản image phải đo theo tải thật. `runAsNonRoot` chỉ chạy được nếu image có quyền file thích hợp. Nếu ứng dụng cần ghi file tạm, cấu hình volume hoặc thư mục ghi phù hợp thay vì tùy tiện tắt biện pháp bảo vệ.

### 8.2. Quy trình áp dụng minh họa

Các lệnh bên dưới chỉ dùng để **minh họa**, thực thi trong cluster thử nghiệm bằng người vận hành có quyền phù hợp:

~~~bash
kubectl apply -f task-config.yaml
kubectl apply -f task-sa.yaml

# Bảo đảm Secret daily-task-db đã được tạo an toàn.
kubectl get secret daily-task-db -n batch-jobs

kubectl apply -f daily-task-job.yaml

kubectl get job daily-reconciliation-20261123 -n batch-jobs
kubectl describe job daily-reconciliation-20261123 -n batch-jobs
kubectl logs job/daily-reconciliation-20261123 -n batch-jobs
~~~

`kubectl get secret` chỉ xác nhận tên đối tượng; **không dùng các lệnh xuất toàn bộ Secret với giá trị đã giải mã** trong log hoặc tài liệu chia sẻ. Nếu có nhiều Pod retry, lấy logs theo từng Pod và lưu vào hệ thống tập trung vì Job/Pod có thể bị TTL dọn.

**Không chạy tự động các lệnh này từ một process task chỉ để xem trạng thái chính nó.** Vận hành và quyền `kubectl` thường thuộc pipeline/controller hoặc người quản trị, không phải container nghiệp vụ.

## 9. Từ Job theo yêu cầu sang CronJob theo lịch

Khi công việc cần chạy định kỳ, bạn có thể chuyển Pod template sang `CronJob`. Ví dụ rút gọn giữ cấu hình `ConfigMap`, `Secret` và `ServiceAccount`:

~~~yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: daily-reconciliation
  namespace: batch-jobs
spec:
  schedule: "0 2 * * *"
  timeZone: "Asia/Ho_Chi_Minh"
  concurrencyPolicy: Forbid
  jobTemplate:
    spec:
      backoffLimit: 0
      activeDeadlineSeconds: 1800
      ttlSecondsAfterFinished: 86400
      template:
        spec:
          serviceAccountName: daily-task-sa
          automountServiceAccountToken: false
          restartPolicy: Never
          containers:
            - name: task
              image: registry.example.com/tasks/daily-reconciliation:1.4.2
              command: ["java", "-jar", "/app/task.jar"]
              args:
                - "--runMode=daily"
              envFrom:
                - configMapRef:
                    name: daily-task-config
                - secretRef:
                    name: daily-task-db
~~~

**Quan trọng:** `--runMode=daily` chỉ là tham số nghiệp vụ minh họa; ứng dụng ví dụ ở phần 4 chỉ nhận `--businessDate=...`. Để dùng CronJob này, **phải bổ sung logic xác định kỳ xử lý một cách xác định từ lịch hoặc work key**. Đừng tự tính “ngày hôm qua” theo đồng hồ Pod mà không định nghĩa timezone, cách xử lý chạy trễ và backfill. Một cách chặt chẽ hơn là có hệ thống điều phối truyền business date cụ thể.

`concurrencyPolicy: Forbid` chỉ hạn chế các Job **được tạo bởi chính CronJob đó**; chạy tay, CronJob khác hoặc Spring Cloud Data Flow vẫn có thể khởi chạy task cùng tên. Nếu các nguồn kích hoạt cùng một công việc, cần idempotency/khóa nghiệp vụ ở tầng dữ liệu.

Một số phiên bản Kubernetes cũ chưa hỗ trợ `timeZone` ở CronJob; hãy xác nhận phiên bản cluster nếu dùng tính năng này.

## 10. TaskRepository và kết quả của Kubernetes Job không đồng nghĩa

Dù Job đã được tạo, còn nhiều giai đoạn chưa hoàn tất:

~~~mermaid
sequenceDiagram
    participant K as Kubernetes Job Controller
    participant P as Pod / Spring Boot Task
    participant R as TaskRepository
    participant B as Database nghiệp vụ

    K->>P: Tạo Pod, inject env + identity
    P->>R: Ghi TaskExecution START_TIME
    P->>B: Thực hiện nghiệp vụ
    B-->>P: Commit kết quả
    P->>R: Ghi TaskExecution END_TIME / EXIT_CODE
    P-->>K: Kết thúc process với OS exit code
    K->>K: Đánh giá trạng thái Job / retry
~~~

| Tín hiệu | Nguồn | Giới hạn cần hiểu |
| --- | --- | --- |
| `Pod Running` | Kubernetes | Java app có thể chưa bootstrap xong hoặc chưa kết nối database |
| `TaskExecution START_TIME` | TaskRepository | Task đã ghi metadata bắt đầu; không chứng minh nghiệp vụ xong |
| `TaskExecution EXIT_CODE/END_TIME` | TaskRepository | Framework ghi kết quả vòng đời nếu kịp |
| **OS exit code** | Process/container | Kubernetes dựa vào exit status; có thể khác kết quả nghiệp vụ nếu mã lỗi bị xử lý sai |
| `Job Complete` / `Job Failed` | Kubernetes Job controller | Phản ánh chính sách Pod/retry/deadline, không tự xác minh dữ liệu nghiệp vụ |
| Kết quả ở bảng/report | Database hoặc hệ thống đích | Cần kiểm tra theo business key, tránh tác động trùng |

**Một Pod bị OOMKilled/SIGKILL có thể không ghi kịp `TASK_EXECUTION.END_TIME`.** Khi đó metadata có thể trông như vẫn đang chạy dù pod đã chết. Người vận hành phải đối chiếu Pod/Job, log và kết quả nghiệp vụ.

### Trường hợp tích hợp Spring Batch

Nếu task chạy Spring Batch, ngoài `TaskRepository` còn có `JobRepository` với `BATCH_JOB_EXECUTION` và `BATCH_STEP_EXECUTION`. Batch Job thất bại **không nên bị ánh xạ nhầm thành process exit 0**; hãy cấu hình cơ chế lan truyền lỗi/exit code phù hợp phiên bản tích hợp và xác minh bằng integration test trước khi Kubernetes dùng exit code để quyết định retry.

Không gọi `System.exit(0)` vô điều kiện ở cuối runner để “đóng task” vì có thể báo success giả.

## 11. Quyền API, Secret và phạm vi trách nhiệm

### 11.1. Quyền của hệ thống tạo Job khác quyền của task Pod

Nếu Kubernetes CronJob controller tạo Job, controller sử dụng danh tính và quyền hạ tầng riêng để thực hiện công việc đó. Nếu **Spring Cloud Data Flow** hoặc một ứng dụng điều phối dùng `TaskLauncher` để tạo Job, **danh tính của chính deployer/SCDF** mới cần quyền Kubernetes API tạo Job/Pod trong namespace thích hợp.

**Không cấp `create jobs` cho `daily-task-sa` chỉ vì task được tạo từ Job.** Task container chỉ cần quyền đó khi nghiệp vụ thực sự gọi API để tạo Job khác.

### 11.2. Có cần quyền Kubernetes API để sử dụng Secret không?

Với manifest `envFrom.secretRef`, container **không cần** gọi `GET /api/v1/namespaces/.../secrets/...` để nhận giá trị environment. Kubelet thực hiện quá trình cung cấp giá trị theo Pod spec và quyền/hạn chế của platform. Vì thế một Role chỉ có `get secrets` thường là **quyền thừa và có thể nguy hiểm** cho ứng dụng không chủ động gọi Kubernetes API.

Nếu ứng dụng phải gọi Kubernetes API để lấy Secret động, nên cân nhắc lại kiến trúc; nhiều trường hợp tốt hơn khi dùng external secret manager, projected volume hoặc workload identity phù hợp, thay vì cấp quyền đọc hàng loạt Secret qua RBAC.

### 11.3. Secret không thay thế NetworkPolicy và quyền DB

Một Pod có password đúng vẫn có thể không kết nối được DB nếu:

- DNS không phân giải `metadata-db.internal`.
- NetworkPolicy chặn egress hoặc không cho phép DNS.
- Database firewall/VPC chặn nguồn Pod.
- DB role không có quyền với bảng `TASK_EXECUTION` hoặc sequence ID.
- Schema metadata chưa được migrate đúng phiên bản.
- TLS certificate/truststore không khớp.

Ngược lại, việc cho phép egress tới DB **không có nghĩa** tự cấp được SQL privileges. Cần kiểm tra cả ba: **network, credential, schema/quyền**.

## 12. Xoay vòng cấu hình và secret an toàn

### 12.1. Quy trình gợi ý

1. **Chuẩn bị credential mới** ở DB hoặc secret manager; đảm bảo giai đoạn chuyển tiếp khi cần.
2. **Cập nhật Secret** qua pipeline được phê duyệt và xác nhận cấu trúc key vẫn tương thích.
3. **Khởi chạy Job mới** hoặc thay Pod để nhận biến môi trường mới; Pod đang chạy không tự cập nhật env.
4. **Theo dõi kết nối và kết quả TaskRepository** trong những lần chạy mới.
5. **Thu hồi credential cũ** khi không còn các Pod/connection pool cần dùng.
6. **Audit** thay đổi, quyền truy cập và những môi trường đã nhận secret mới.

Không cập nhật mật khẩu giữa transaction dài rồi mặc nhiên kỳ vọng connection pool hiện tại tái xác thực tức thì. Khi thay đổi `ConfigMap` hoặc `Secret`, nên gắn revision/label cho đợt triển khai để xác định chính xác cấu hình mỗi lần chạy.

### 12.2. Lưu log đúng nơi

Nếu `ttlSecondsAfterFinished` xóa Job/Pod, log cục bộ của Pod có thể bị mất. Hãy gửi stdout/stderr đến hệ thống log tập trung, liên kết bằng tên Job, Pod UID, business key và `TASK_EXECUTION_ID` khi có. Nhưng **không log tất cả environment variables** vì chúng có thể chứa password được inject từ Secret.

## 13. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Bước kiểm tra |
| --- | --- | --- |
| Pod ở trạng thái `CreateContainerConfigError` | ConfigMap/Secret được tham chiếu không tồn tại, thiếu key bắt buộc | Xem `kubectl describe pod` và namespace/name, không dump secret |
| Pod chạy nhưng profile không đúng | `SPRING_PROFILES_ACTIVE` chưa được inject, key sai hoặc profile bị ghi đè | Kiểm tra ConfigMap, app startup logs và property precedence |
| Spring Boot không có JDBC URL | Secret thiếu `SPRING_DATASOURCE_URL` hoặc tên key khác | Kiểm tra danh sách tên key, env binding, không in giá trị secret |
| `authentication failed` ở PostgreSQL | Username/password cũ hoặc sai DB | Kiểm tra rotation, vai trò SQL và network |
| `permission denied for relation` | Database role thiếu quyền trên TaskRepository | Kiểm tra role, bảng, sequence và schema |
| `No suitable driver` | Image thiếu JDBC driver | Kiểm tra dependency/runtime image |
| `relation task_execution does not exist` | Schema chưa migrate hoặc sai namespace/schema/prefix | Đối chiếu DDL/version và DataSource |
| ServiceAccount `Forbidden` khi dùng Kubernetes client | RoleBinding thiếu, sai namespace hoặc token bị tắt | Kiểm tra `serviceAccountName`, `automount...`, RBAC cụ thể |
| Không kéo được image | Registry credential/imagePullSecret sai hoặc image không tồn tại | Kiểm tra Pod Events, imagePullSecrets và registry |
| Job Failed, TaskRepository không có END_TIME | Pod bị kill trước bước update metadata | Xem `terminated.reason`, exit code, log và dữ liệu nghiệp vụ |
| Job Complete nhưng nghiệp vụ không đúng | Runner nuốt lỗi hoặc Batch job failure không lan truyền exit code | Kiểm tra nghiệp vụ thật và error propagation |
| Task bị chạy lại hai lần | Job controller retry, CronJob trùng, chạy tay hoặc hệ thống điều phối khác | Kiểm tra job history, business key và idempotency |
| Secret đổi nhưng task vẫn dùng giá trị cũ | Environment của Pod cũ không tự cập nhật | Khởi chạy Pod mới/rollout theo chính sách |
| Mất logs sau một ngày | TTL xóa Job/Pod | Thu thập log tập trung trước khi dọn |

### Các lệnh quan sát an toàn

~~~bash
kubectl get jobs -n batch-jobs
kubectl get pods -n batch-jobs -l app=daily-reconciliation
kubectl describe job daily-reconciliation-20261123 -n batch-jobs
kubectl logs job/daily-reconciliation-20261123 -n batch-jobs
kubectl get configmap daily-task-config -n batch-jobs
kubectl get serviceaccount daily-task-sa -n batch-jobs
~~~

Chỉ người vận hành được cấp phép mới nên thực thi những lệnh này. Việc `describe` Pod thường hiển thị tham chiếu tên Secret và cấu hình không bí mật; vẫn cần xem lại dữ liệu output trước khi chia sẻ. **Không chạy `printenv`, `env` hoặc đọc giá trị Secret để gỡ lỗi trên hệ thống production**.

### Kiểm tra quyền ServiceAccount khi thật sự dùng Kubernetes API

~~~bash
kubectl auth can-i get pods \
  --as=system:serviceaccount:batch-jobs:daily-task-sa \
  --namespace=batch-jobs
~~~

Kết quả `yes/no` phụ thuộc RoleBinding hiện có và quyền impersonation của người chạy lệnh. Với manifest `daily-task-sa` không cần API, **không có lý do bắt buộc kết quả phải là `yes`**. `automountServiceAccountToken=false` là chính sách mount credential; quyền RBAC `can-i` là lớp riêng.

## 14. Kịch bản kiểm thử triển khai

### Kịch bản A — Có đủ cấu hình, Secret và DB

1. Chuẩn bị `daily-task-config`, `daily-task-db` và `daily-task-sa` đúng namespace.
2. Kiểm tra image/driver và schema TaskRepository đã migrate.
3. Tạo Kubernetes Job từ manifest.
4. Đợi Pod bootstrap, chạy nghiệp vụ rồi kết thúc.
5. Đối chiếu Job/Pod exit code với `TASK_EXECUTION` và kết quả nghiệp vụ.
6. Xác nhận secret không có trong log, command args hoặc tài liệu chia sẻ.

### Kịch bản B — Secret bị thiếu

1. Trong namespace lab, cấu hình Job trỏ tới tên Secret không tồn tại.
2. Quan sát Pod không thể tạo container hoặc bị báo lỗi cấu hình.
3. Kiểm tra `kubectl describe pod` để nhận diện Secret reference; **không in giá trị bí mật**.
4. Sửa tên Secret và tạo **Job mới** thay vì sửa Pod template immutable của Job đang tồn tại.

### Kịch bản C — Không có quyền SQL

1. Dùng DB role lab chỉ có `SELECT`.
2. Chạy task; khả năng cao lỗi khi framework cần tạo/cập nhật TaskExecution.
3. Đọc log `permission denied` và kiểm tra DBA đã cấp quyền phù hợp trên bảng/sequence chưa.
4. Khôi phục role task_writer đúng quyền thay vì cấp superuser.

### Kịch bản D — Không mount token Kubernetes API

1. Đặt `automountServiceAccountToken: false`.
2. Chạy task chỉ đọc environment và ghi DB; nó vẫn có thể hoạt động bình thường.
3. Trong một ứng dụng thử nghiệm riêng có client Kubernetes, gọi API và quan sát cách xác thực thất bại nếu không có token/credential khác.
4. Nếu nghiệp vụ thực sự cần API, thiết kế cấp danh tính và Role tối thiểu; không bật mount token tùy tiện cho mọi workload.

### Kịch bản E — Pod bị dừng khi đang xử lý

1. Trong cluster lab, dùng một task có xử lý lâu và dữ liệu idempotent.
2. Cấu hình deadline ngắn để kiểm thử thất bại có kiểm soát.
3. Quan sát trạng thái `Job Failed` và khả năng thiếu `END_TIME` trong TaskRepository.
4. Kiểm tra kết quả đã commit, business key và checkpoint trước khi retry.
5. Không dùng `EXIT_CODE=0` hoặc `Job Complete` làm bằng chứng duy nhất rằng dữ liệu nghiệp vụ chính xác.

## 15. Checklist trước production

### Cấu hình

- [ ] Đã tách ConfigMap không bí mật khỏi Secret credential.
- [ ] Không đưa password/token vào ConfigMap, manifest Git, image hay CLI args.
- [ ] Key environment phù hợp với thuộc tính Spring Boot/Spring Cloud Task.
- [ ] Ứng dụng là process hữu hạn; không giữ HTTP server/thread nền không cần thiết.
- [ ] Mỗi lần chạy có version image/config và business key xác định.

### Danh tính và bảo mật

- [ ] Mỗi nhóm workload có ServiceAccount riêng khi cần phân tách quyền.
- [ ] Task không cần Kubernetes API đã tắt automount API token.
- [ ] Chỉ cấp Role/RoleBinding nếu code thực sự gọi Kubernetes API.
- [ ] Danh tính launcher/deployer không bị nhầm với danh tính Pod task.
- [ ] DB role được cấp quyền DML cần thiết, không cấp DDL/superuser rộng.
- [ ] Có kiểm soát Secret RBAC, encryption at rest, network/TLS và rotation.
- [ ] Registry private dùng imagePullSecret/workload identity phù hợp, tách khỏi DB credentials.

### Vận hành

- [ ] Job `restartPolicy`, `backoffLimit`, deadline và resource limits phù hợp nghiệp vụ.
- [ ] CronJob `concurrencyPolicy` đúng yêu cầu; nhớ phạm vi chỉ trong cùng CronJob.
- [ ] Schema TaskRepository đã chuẩn bị đúng phiên bản và DataSource bền vững.
- [ ] Lỗi nghiệp vụ làm Job/process báo trạng thái phù hợp; không nuốt exception.
- [ ] Có idempotency/checkpoint để retry an toàn khi một Pod bị kill.
- [ ] Có log tập trung vì TTL có thể xóa Job/Pod.
- [ ] Đã thử lỗi Secret thiếu, RBAC, kết nối DB, OOM, timeout và rotation.
- [ ] Có cách đối chiếu Kubernetes Job với TaskExecution và kết quả nghiệp vụ.
- [ ] Đã biết cách xem Pod Events mà không lộ secret hoặc cấp quyền thừa.

## 16. Ghi nhớ

**ConfigMap lưu cấu hình không bí mật; Secret cấp dữ liệu nhạy cảm; ServiceAccount xác định danh tính Pod đối với Kubernetes API.** Chúng giải quyết những vấn đề khác nhau và không thể thay thế nhau. Với **Spring Cloud Task** chạy trong Kubernetes Job/CronJob, hãy dùng cả ba đúng mục đích, tách quyền hạ tầng khỏi quyền database và chỉ cấp quyền tối thiểu cho ứng dụng.

Một bản triển khai được coi là tốt không chỉ khi Pod chuyển sang `Succeeded`. Nó còn phải **ghi TaskRepository vào database bền vững**, xử lý lỗi rõ ràng, không làm lộ thông tin xác thực, có khả năng retry/idempotent và đủ dữ liệu vận hành để điều tra nếu Pod bị dừng trước khi metadata kết thúc được lưu.

### Tài liệu tham khảo

- [Kubernetes — ConfigMaps](https://kubernetes.io/docs/concepts/configuration/configmap/)
- [Kubernetes — Secrets](https://kubernetes.io/docs/concepts/configuration/secret/)
- [Kubernetes — Configure Service Accounts for Pods](https://kubernetes.io/docs/tasks/configure-pod-container/configure-service-account/)
- [Kubernetes — RBAC Authorization](https://kubernetes.io/docs/reference/access-authn-authz/rbac/)
- [Kubernetes — Jobs](https://kubernetes.io/docs/concepts/workloads/controllers/job/)
- [Kubernetes — CronJobs](https://kubernetes.io/docs/concepts/workloads/controllers/cron-jobs/)
- [Kubernetes — TTL-after-finished Jobs](https://kubernetes.io/docs/concepts/workloads/controllers/ttlafterfinished/)
- [Spring Cloud Task — Features / DataSource / TaskRepository](https://docs.spring.io/spring-cloud-task/reference/features.html)
- [Spring Cloud Task — Task Repository Schema](https://docs.spring.io/spring-cloud-task/reference/3.2/appendix-task-repository-schema.html)
