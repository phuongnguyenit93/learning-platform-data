# Tích hợp ConfigMap, Secret hoặc configtree: ranh giới với module Kubernetes

Ứng dụng Spring Boot chạy trên Kubernetes có thể nhận cấu hình từ nhiều nơi: Spring Cloud Config Server, Kubernetes ConfigMap, Kubernetes Secret, biến môi trường và file được mount vào container. Những cơ chế này có thể cùng tồn tại, nhưng cần xác định rõ nguồn nào chịu trách nhiệm cho từng nhóm thuộc tính và Spring Boot nạp chúng theo cách nào.

Điểm cần phân biệt là **Kubernetes cung cấp và mount dữ liệu**, còn **Spring Boot/Spring Cloud chuyển dữ liệu đó thành cấu hình ứng dụng**. `configtree:` là một cơ chế Config Data của Spring Boot để đọc file theo dạng mỗi file tương ứng một property; nó không phải Config Server backend và cũng không tự theo dõi thay đổi của volume. Spring Cloud Kubernetes Config là một integration riêng để đọc ConfigMap/Secret qua Kubernetes API. Spring Cloud Config Client lại đọc remote `Environment` từ Config Server.

## 1. Ba đường đưa cấu hình từ Kubernetes vào Spring

Có ba cách thường gặp:

| Cách | Cơ chế | Khi phù hợp |
|---|---|---|
| Mount ConfigMap/Secret thành file rồi dùng `configtree:` | Kubelet mount dữ liệu vào filesystem; Spring Boot ánh xạ tên file thành property key. | Secret dạng file hoặc từng property riêng, muốn tránh đọc Kubernetes API trực tiếp từ ứng dụng. |
| Đọc file cấu hình YAML/properties được mount | Kubernetes mount một file cấu hình; Spring Boot nạp file qua Config Data `file:` hoặc location phù hợp. | ConfigMap chứa tài liệu `application.yaml`/`.properties` hoàn chỉnh. |
| Spring Cloud Kubernetes Config | Spring Cloud Kubernetes đọc ConfigMap/Secret qua Kubernetes API và tạo property source. | Muốn ứng dụng lấy cấu hình theo ConfigMap/Secret và dùng cơ chế integration/watch của Spring Cloud Kubernetes. |

Ngoài ra, ứng dụng có thể nhận giá trị qua environment variables từ `env`, `envFrom`, `configMapKeyRef` hoặc `secretKeyRef`. Khi đó Spring Boot dùng các biến môi trường như một nguồn cấu hình tiêu chuẩn.

Không nhầm các cách này với Spring Cloud Config Server. Config Server cung cấp cấu hình remote theo application/profile/label; Kubernetes ConfigMap/Secret là đối tượng của cluster; `configtree:` chỉ đọc file trong filesystem của process.

## 2. Ranh giới trách nhiệm giữa Config Server và Kubernetes

Một cách phân chia phổ biến:

- **Spring Cloud Config Server:** cấu hình dùng chung nhiều môi trường, cấu hình nghiệp vụ theo application/profile, revision/label, review qua Git và quy trình phát hành tập trung.
- **ConfigMap:** tham số triển khai gắn với Kubernetes như tên service, namespace logic, cờ vận hành theo cluster, cấu hình không nhạy cảm hoặc file cấu hình được mount.
- **Secret:** credential, password, token, certificate hoặc private key cần được cấp vào workload qua cơ chế quản lý secret.
- **Spring Boot Config Data:** nạp và phân giải property từ Config Server, file, configtree và environment.
- **Spring Cloud Kubernetes:** integration đọc Kubernetes API khi ứng dụng cần lấy ConfigMap/Secret trực tiếp và có quyền RBAC tương ứng.

Ví dụ, ConfigMap có thể chứa URL của Config Server và tên profile; Config Server cung cấp timeout, retry policy và cấu hình nghiệp vụ; Kubernetes Secret mount database password vào `/run/secrets`; Spring Boot dùng `configtree:` để bind password vào `DataSource`.

Điều quan trọng là không để cùng một property có hai nguồn chủ sở hữu không rõ ràng. Nếu `app.payment.timeout` vừa được sửa trong Git Config Server vừa được ghi trong ConfigMap, reviewer và người vận hành phải biết nguồn nào thắng và ai có quyền thay đổi.

## 3. ConfigMap: dữ liệu không nhạy cảm

ConfigMap lưu dữ liệu cấu hình không nhạy cảm dưới dạng key/value hoặc file. Ví dụ:

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: orders-runtime
  namespace: production
data:
  APP_REGION: ap-southeast-1
  FEATURE_STATUS_ENDPOINT: "true"
```

Có thể đưa key thành environment variable trong Pod:

```yaml
envFrom:
  - configMapRef:
      name: orders-runtime
```

Hoặc chỉ lấy một key:

```yaml
env:
  - name: APP_REGION
    valueFrom:
      configMapKeyRef:
        name: orders-runtime
        key: APP_REGION
```

Spring Boot có thể ánh xạ `APP_REGION` thành property `app.region` theo relaxed binding. Tên key và biến môi trường cần tuân theo quy tắc đặt tên hợp lệ của Kubernetes và Spring Boot.

ConfigMap phù hợp với dữ liệu không bí mật. Không đưa password, token, private key hoặc credential vào ConfigMap chỉ vì nó dễ mount hơn Secret.

## 4. Secret: dữ liệu nhạy cảm và giới hạn bảo vệ

Kubernetes Secret được thiết kế để phân phối dữ liệu nhạy cảm đến Pod. Ví dụ cấu trúc manifest:

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: orders-database
  namespace: production
type: Opaque
stringData:
  spring.datasource.username: orders_app
  spring.datasource.password: <injected-by-secret-pipeline>
```

Giá trị trong ví dụ là placeholder. Không commit password thật vào manifest, Git hoặc tài liệu. Hãy tạo Secret qua secret manager, External Secrets Operator, sealed/encrypted secret workflow hoặc pipeline được tổ chức phê duyệt.

Kubernetes Secret không tự động đồng nghĩa với dữ liệu đã được mã hóa ở mọi nơi. Trường `data` trong API manifest được biểu diễn bằng Base64; Base64 là encoding, không phải encryption. Cần cấu hình encryption at rest cho etcd, RBAC tối thiểu, bảo vệ backup và hạn chế quyền đọc Secret.

Chỉ cấp quyền truy cập Secret cho service account cần dùng. Tránh quyền `list`/`watch` trên tất cả Secret trong mọi namespace nếu workload chỉ cần một Secret cụ thể.

## 5. Mount ConfigMap hoặc Secret thành file

Pod có thể mount ConfigMap và Secret thành volume chỉ đọc:

```yaml
spec:
  containers:
    - name: orders-service
      image: example/orders-service:1.0.0
      volumeMounts:
        - name: runtime-config
          mountPath: /etc/orders-config
          readOnly: true
        - name: database-secret
          mountPath: /run/secrets
          readOnly: true
  volumes:
    - name: runtime-config
      configMap:
        name: orders-runtime-files
    - name: database-secret
      secret:
        secretName: orders-database
```

Mỗi key trong ConfigMap/Secret thường trở thành một file trong mount directory. Ví dụ key `spring.datasource.password` tạo file cùng tên, nội dung file là giá trị tương ứng.

Khi dùng `subPath` để mount một file đơn lẻ, cần lưu ý cập nhật ConfigMap/Secret không được phản ánh vào mount đó theo cơ chế cập nhật volume thông thường. Với volume mount cả thư mục, kubelet có thể cập nhật nội dung sau một khoảng trễ; ứng dụng vẫn cần cơ chế đọc lại nếu muốn dùng giá trị mới.

## 6. Dùng configtree: mỗi file là một property

Spring Boot Config Data hỗ trợ location `configtree:` để đọc cấu hình từ một cây thư mục. Tên file được dùng làm property key, nội dung file là property value.

Ví dụ thư mục được mount:

```text
/run/secrets/
├── spring.datasource.username
└── spring.datasource.password
```

Khai báo trong `application.yml`:

```yaml
spring:
  config:
    import: "configtree:/run/secrets/"
```

Hoặc dùng optional khi thư mục thực sự được phép vắng mặt:

```yaml
spring:
  config:
    import: "optional:configtree:/run/secrets/"
```

Khi đó Spring có thể phân giải:

```java
@ConfigurationProperties(prefix = "spring.datasource")
public class DatabaseProperties {
    private String username;
    private String password;
    // getters and setters
}
```

`configtree:` rất phù hợp với secret mount vì ứng dụng đọc nội dung file mà không cần tự gọi Kubernetes API. Nó không tự mã hóa file, không xác minh nguồn Secret và không tự refresh bean khi volume thay đổi; các trách nhiệm đó thuộc về Kubernetes/platform và cơ chế reload của ứng dụng.

### Cẩn thận với file application.yaml

`configtree:` không parse nội dung file `application.yaml` thành nhiều property. Nếu thư mục có file tên `application.yaml`, configtree coi `application.yaml` là tên một property key và nội dung file là giá trị của key đó.

Nếu ConfigMap mount một tài liệu YAML hoàn chỉnh, hãy nạp nó như file Config Data thông thường, ví dụ:

```yaml
spring:
  config:
    import: "optional:file:/etc/orders-config/application.yaml"
```

Hãy phân biệt rõ: **configtree = tên file trở thành property key**; **file import = nội dung YAML/properties được parse như tài liệu cấu hình**.

## 7. Dùng environment variables từ ConfigMap hoặc Secret

Kubernetes có thể inject một key từ Secret thành environment variable:

```yaml
env:
  - name: SPRING_DATASOURCE_PASSWORD
    valueFrom:
      secretKeyRef:
        name: orders-database
        key: spring.datasource.password
```

Spring Boot relaxed binding ánh xạ `SPRING_DATASOURCE_PASSWORD` đến `spring.datasource.password`. Cách này đơn giản với một số property phẳng, nhưng giá trị nằm trong môi trường process và có thể xuất hiện qua diagnostic/process inspection nếu hệ thống không kiểm soát chặt.

Environment variable được inject lúc container khởi động. Khi Secret thay đổi, process đang chạy không tự nhận giá trị environment mới; cần tạo Pod/container mới để nhận giá trị mới. Nếu cần file-based secret rotation, volume mount và configtree có thể phù hợp hơn, nhưng ứng dụng vẫn cần reload hoặc restart để áp dụng.

## 8. Spring Cloud Kubernetes Config đọc ConfigMap/Secret qua API

Spring Cloud Kubernetes cung cấp integration để ứng dụng đọc ConfigMap và Secret từ Kubernetes API. Cơ chế này khác với volume mount/configtree: application dùng Kubernetes client và service account identity để truy vấn object trong namespace được cấp quyền.

Ở các phiên bản Spring Cloud Kubernetes hỗ trợ Config Data API, ứng dụng có thể dùng import dạng:

```yaml
spring:
  config:
    import: "kubernetes:"
  cloud:
    kubernetes:
      config:
        enabled: true
        name: orders-runtime
        namespace: production
      secrets:
        enabled: true
```

Đây là ví dụ định hướng. Cách bật đọc Secret qua API, tên thuộc tính như `enabled`/`enableApi`, cấu trúc `sources`, namespace mặc định và watch/reload có thể thay đổi theo phiên bản Spring Cloud Kubernetes. Hãy kiểm tra reference documentation của đúng release train trước khi đưa cấu hình vào production.

Với API mode, service account cần RBAC cho đúng resource và namespace. Đọc ConfigMap và đọc Secret là hai quyền khác nhau; chỉ bật Secret API nếu ứng dụng thực sự cần và đã được cấp quyền. Nếu chỉ mount Secret thành file rồi dùng configtree, ứng dụng thường không cần quyền gọi API để đọc Secret đó.

## 9. Chọn giữa Config Server, ConfigMap/Secret API và configtree

| Tiêu chí | Spring Cloud Config Server | Spring Cloud Kubernetes API | Mounted file + configtree |
|---|---|---|---|
| Nguồn dữ liệu | Git, Vault hoặc backend được Config Server hỗ trợ. | Kubernetes ConfigMap/Secret. | File trong container filesystem, thường được mount từ ConfigMap/Secret. |
| Selector | Application/profile/label. | Namespace, ConfigMap/Secret name và source rules. | Đường dẫn file và tên file/property. |
| Quyền truy cập | Identity client tới Config Server; server có quyền backend. | Kubernetes service account và RBAC. | Kubernetes kiểm soát quyền mount Pod/volume; process đọc file được mount. |
| Version/review | Git commit/tag/PR và backend metadata. | Kubernetes object revision/resourceVersion; cần quy trình GitOps/audit bên ngoài. | Phiên bản object/rollout của Pod; file tree không tự tạo revision nghiệp vụ. |
| Reload | Refresh endpoint, Bus hoặc cơ chế client. | Watch/reload theo khả năng phiên bản và cấu hình. | Volume update có thể xảy ra; Spring Environment/bean không tự reload chỉ vì file đổi. |
| Phù hợp | Cấu hình tập trung cho nhiều ứng dụng/môi trường. | Cấu hình gắn với cluster/namespace/workload. | Secret/property dạng file và cấu hình runtime được mount. |

Không có một cơ chế phải thay thế tất cả cơ chế còn lại. Có thể dùng Config Server cho cấu hình nghiệp vụ, ConfigMap cho thông tin triển khai và Secret/configtree cho credential; điều cần thiết là phân định owner và precedence.

## 10. Kết hợp Config Server và configtree trong một ứng dụng

Một ứng dụng có thể nạp remote config và secret từ file mount:

```yaml
spring:
  application:
    name: orders-service
  config:
    import:
      - "configserver:https://config.internal"
      - "configtree:/run/secrets/"
```

Config Server có thể cung cấp:

```yaml
app:
  payment:
    timeout: 3s
    retry:
      max-attempts: 4
```

Configtree có thể cung cấp file:

```text
/run/secrets/spring.datasource.username
/run/secrets/spring.datasource.password
```

Trong mô hình này, Config Server không cần lưu password database nếu secret được quản lý ở Kubernetes/secret manager. Cần xác định rõ property nào do remote config sở hữu, property nào do mounted secret sở hữu. Nếu hai nguồn cùng khai báo một key, thứ tự Config Data import và property source precedence sẽ quyết định giá trị cuối.

Không dựa vào thứ tự viết trong YAML để suy đoán khi chưa xác minh theo phiên bản Spring Boot. Hãy kiểm tra `Environment.getPropertySources()` trong integration test và assert nguồn thắng cho các key quan trọng. Không log giá trị secret khi kiểm tra.

## 11. Secret rotation và reload

Khi Secret được cập nhật trong Kubernetes:

- Environment variable của container đang chạy không đổi; cần restart/recreate Pod.
- Secret volume mount thông thường có thể cập nhật nội dung sau một khoảng trễ do kubelet đồng bộ.
- Secret mount qua `subPath` không nhận cập nhật tự động theo cơ chế volume projection.
- Ứng dụng dùng `configtree:` không tự động nạp lại Environment hoặc rebind bean chỉ vì file thay đổi.
- Nếu dùng Spring Cloud Kubernetes API, watch/reload có thể hỗ trợ phát hiện thay đổi tùy phiên bản và cấu hình; cần kiểm tra cơ chế thực tế.

Quy trình rotation an toàn:

1. Cấp secret mới trong secret manager/Kubernetes Secret.
2. Xác nhận Pod nhận được file/giá trị mới theo cơ chế phân phối.
3. Restart hoặc kích hoạt reload được hỗ trợ để ứng dụng sử dụng credential mới.
4. Xác minh kết nối mới hoạt động và không còn consumer dùng credential cũ.
5. Thu hồi credential cũ sau khi toàn bộ workload đã chuyển đổi.

Không thu hồi credential cũ trước khi xác minh tất cả client đã nhận và sử dụng giá trị mới. Với database hoặc broker, có thể cần giai đoạn cho phép cả credential cũ và mới cùng tồn tại để rollout không gián đoạn.

## 12. RBAC và ranh giới bảo mật

Nếu dùng Spring Cloud Kubernetes API, service account của ứng dụng cần quyền phù hợp. Ví dụ Role chỉ đọc một số ConfigMap trong namespace:

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: orders-config-reader
  namespace: production
rules:
  - apiGroups: [""]
    resources: ["configmaps"]
    resourceNames: ["orders-runtime"]
    verbs: ["get"]
```

Nếu cần đọc Secret, phải thêm rule riêng cho resource `secrets` với phạm vi resource name tối thiểu. Một số thao tác watch/list có thể yêu cầu quyền rộng hơn và cần được xác nhận từ đúng integration/version; không cấp `get,list,watch` trên mọi Secret toàn cluster theo mặc định.

Với volume mount, Pod spec tham chiếu Secret name và Kubernetes cấp nội dung vào container. Điều này không loại bỏ yêu cầu bảo vệ Pod creation/update: người có quyền tạo Pod trong namespace có thể có khả năng mount Secret mà Pod đó được phép tham chiếu. RBAC, admission policy và quyền triển khai workload đều là một phần của ranh giới bảo mật.

Không ghi secret vào ConfigMap, log, Actuator `env`, crash dump hoặc CI output. Bảo vệ file mount bằng quyền filesystem phù hợp và chỉ cho process cần thiết đọc.

## 13. Kiểm thử tích hợp

Một bộ kiểm thử nên bao gồm:

| Kịch bản | Cách kiểm tra |
|---|---|
| ConfigMap qua environment variable | Inject `APP_REGION`, xác nhận `Environment`/bean bind đúng. |
| ConfigMap mount thành YAML file | Import đúng file bằng `file:` và xác nhận nội dung được parse. |
| Secret mount qua configtree | Tạo file test có tên property, xác nhận binding thành công mà không in giá trị ra log. |
| Sai đường dẫn configtree | Kiểm tra optional/mandatory behavior và validation required property. |
| Config Server + configtree cùng tồn tại | Assert property source order và owner của từng key. |
| Spring Cloud Kubernetes API | Chạy test trong cluster hoặc môi trường integration có RBAC tương ứng; xác minh đúng namespace/resource. |
| Secret rotation | Cập nhật Secret, kiểm tra volume/env behavior, sau đó restart/reload và xác minh consumer. |
| RBAC thiếu quyền | Xác nhận lỗi authorization rõ ràng, không fallback sang identity rộng hơn. |

Unit test có thể dùng thư mục tạm để kiểm tra `configtree:` và Config Data. Integration test Kubernetes cần xác minh đúng service account, namespace và RBAC; không giả định test chạy local có cùng identity với Pod production.

## 14. Ranh giới với nội dung học Kubernetes

Khi học module Kubernetes, trọng tâm thường là tạo ConfigMap/Secret, khai báo Pod volume/env, namespace, RBAC, rollout và cách kubelet cập nhật projected volume. Trong module Spring Cloud Configuration, trọng tâm là cách ứng dụng Spring Boot **nạp, phân giải, bind và refresh** dữ liệu sau khi Kubernetes đã cung cấp nó.

| Chủ đề | Thuộc trọng tâm Kubernetes | Thuộc trọng tâm Spring Cloud Configuration |
|---|---|---|
| Tạo ConfigMap/Secret và quản lý object | Có | Chỉ dùng object làm nguồn đầu vào. |
| Volume, `env`, `envFrom`, `secretKeyRef` | Có | Giải thích tác động đến property binding. |
| Service account, Role/RoleBinding | Có | Giải thích quyền cần cho Config API và kiểm thử authorization. |
| `configtree:` và Config Data | Không phải cơ chế Kubernetes | Có: Spring Boot đọc file thành PropertySource. |
| Config Server application/profile/label | Không | Có: remote configuration contract. |
| Precedence giữa remote config, file mount và environment | Có thể liên quan deployment | Có: Spring Environment và Config Data order. |
| RefreshScope, rebind và Spring Cloud Bus | Không | Có: vòng đời cấu hình trong Spring runtime. |

Không cần lặp lại toàn bộ cách quản trị Kubernetes object khi bài học chỉ cần giải thích cách Spring tiêu thụ file hoặc API. Ngược lại, không coi `configtree:` là một tính năng Kubernetes: nó là khả năng của Spring Boot và có thể đọc bất kỳ thư mục phù hợp nào, kể cả file được mount từ hệ thống khác.

## 15. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| `configtree:` không tìm thấy property | Sai mount path, file name không khớp property key hoặc file không được mount. | Kiểm tra filesystem trong container và tên file. |
| File `application.yaml` thành một property đơn | Dùng `configtree:` thay vì import file YAML. | Dùng `file:` để parse tài liệu hoặc tách từng property thành file. |
| Secret thay đổi nhưng ứng dụng vẫn dùng giá trị cũ | Environment variable không cập nhật hoặc Spring chưa reload file/property source. | Restart hoặc triển khai cơ chế reload phù hợp. |
| Secret volume không đổi | Mount qua `subPath`, kubelet chưa đồng bộ hoặc Pod tham chiếu Secret khác. | Kiểm tra volume mount, Pod spec và propagation delay. |
| Spring Cloud Kubernetes API trả `403` | Service account thiếu RBAC hoặc namespace/resource không đúng. | Cấp quyền tối thiểu đúng resource và namespace. |
| Config Server và ConfigMap cùng khai báo một key | Chưa có source-of-truth/precedence rõ ràng. | Chỉ định owner, kiểm tra property source order và loại bỏ duplicate không cần thiết. |
| Secret xuất hiện trong log hoặc Actuator | Expose/debug cấu hình quá rộng hoặc log binding. | Redact dữ liệu, giới hạn endpoint và không dump Environment. |
| Secret cũ bị thu hồi quá sớm | Rotation chưa hoàn tất trên mọi replica. | Dùng giai đoạn overlap, rollout và xác minh trước revoke. |

## 16. Tổng kết

- Config Server, Kubernetes ConfigMap/Secret, environment variables và `configtree:` là các nguồn khác nhau; cần phân định owner và precedence.
- ConfigMap dành cho dữ liệu không nhạy cảm; Secret dành cho dữ liệu nhạy cảm nhưng Base64 không phải encryption.
- Kubernetes có thể mount mỗi key thành file; `configtree:` ánh xạ tên file thành property key và nội dung file thành value.
- Nếu mount tài liệu `application.yaml`, dùng Config Data file import; `configtree:` không parse file đó như YAML.
- Spring Cloud Kubernetes Config đọc ConfigMap/Secret qua API và cần service account/RBAC; mounted volume/configtree không cần ứng dụng tự gọi Kubernetes API để đọc file.
- Có thể kết hợp Config Server với configtree, nhưng phải kiểm tra PropertySource precedence và không để hai nguồn sở hữu cùng key một cách mơ hồ.
- Secret rotation cần phối hợp cập nhật object, volume/process, reload/restart và thời điểm thu hồi credential cũ.
- Nội dung Kubernetes quản lý object/volume/RBAC; nội dung Spring Cloud Configuration quản lý cách Spring nạp, bind, phân giải và refresh giá trị.
