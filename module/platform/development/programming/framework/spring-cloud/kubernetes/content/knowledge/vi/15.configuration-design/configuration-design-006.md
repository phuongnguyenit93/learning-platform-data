# Phiên bản hóa ConfigMap và Secret cùng manifest triển khai

## Mục tiêu của thiết kế

Trong module **SPRING_CLOUD_KUBERNETES**, cấu hình ứng dụng phải được quản lý cùng cách ứng dụng được triển khai. Một bản phát hành cần trả lời được: chạy image nào, đọc ConfigMap nào, dùng phiên bản thông tin xác thực nào và có thể khôi phục tổ hợp đó bằng cách nào?

Sau bài học này, bạn có thể:

- Xây dựng một bản phát hành gồm image, ConfigMap, tham chiếu Secret và Pod template nhất quán.
- Chọn giữa tên có phiên bản, hậu tố băm và checksum trong Pod template.
- Triển khai thay đổi cấu hình, quan sát Pod và quay lui có điều kiện.
- Phân biệt cập nhật tài nguyên Kubernetes với cập nhật giá trị trong Spring.
- Chọn đúng vai trò của Spring Cloud Kubernetes Config, Configuration Watcher và RBAC.

Bài học thuộc chương **Thiết kế cấu hình**. Các ví dụ dùng dịch vụ đặt hàng `orders` trong namespace `shop`. Đây là thiết kế theo hướng **cấu hình cố định trong vòng đời một Pod; thay cấu hình bằng rollout**, phù hợp khi cần truy vết và khôi phục rõ ràng.

## 1. Đơn vị phát hành là một tổ hợp

Nếu Deployment dùng tên cố định `orders-config` và `orders-db`, sửa dữ liệu của hai tài nguyên này sẽ làm thay đổi ý nghĩa của cùng một manifest. Một commit cũ chỉ lưu được tên tham chiếu, chưa chắc khôi phục được dữ liệu cũ.

Hãy coi một release là tổ hợp:

```text
Release =
  image đã định danh
  + phiên bản cấu hình không nhạy cảm
  + phiên bản/tham chiếu bí mật
  + Pod template
  + namespace và profile
  + điều kiện tương thích với hệ thống bên ngoài
```

Ví dụ thiết kế:

| Release | Image minh họa | ConfigMap | Secret | Mục đích |
|---|---|---|---|---|
| R1 | orders:1.8.0 | orders-config-r1 | orders-db-v1 | Mốc ban đầu |
| R2 | orders:1.8.0 | orders-config-r2 | orders-db-v1 | Chỉ thay cấu hình nghiệp vụ |
| R3 | orders:1.8.1 | orders-config-r3 | orders-db-v2 | Đổi ứng dụng và thông tin xác thực |

Image trong bảng là ký hiệu dễ đọc. Trong môi trường cần tái lập chính xác, manifest nên ghim image theo digest `registry/path@sha256:...`; tag có thể bị gán lại nếu registry không chặn thao tác đó.

Không cần tạo Secret mới cho mọi lần đổi timeout. Chỉ tạo phiên bản Secret mới khi nội dung bí mật hoặc hợp đồng sử dụng nó thay đổi. Sổ phát hành lưu **định danh phiên bản**, không lưu mật khẩu.

Một quy ước hữu ích là: **một tên cấu hình đã phát hành chỉ có một nội dung trong thời gian còn được giữ lại**. Tên có hậu tố giúp nhận diện; quy trình và chính sách bảo vệ mới duy trì được quy ước này.

## 2. Đổi dữ liệu không đồng nghĩa ứng dụng đã đổi cấu hình

| Cách ứng dụng nhận dữ liệu | Điều xảy ra khi sửa tài nguyên cùng tên | Cách kiểm soát trong bài |
|---|---|---|
| `env`, `envFrom`, `secretKeyRef` | Biến môi trường trong container đang chạy không được cập nhật | Tạo Pod mới |
| ConfigMap/Secret mount thành volume | File được chiếu vào volume có thể cập nhật sau một khoảng trễ | Dùng tài nguyên có tên phiên bản và đọc khi khởi động |
| Volume mount qua `subPath` | Không nhận cập nhật tự động của nguồn ConfigMap/Secret | Không dùng để minh họa cập nhật trực tiếp |
| Spring đọc file cấu hình lúc khởi động | File đổi không tự làm mọi bean đọc lại giá trị | Rollout hoặc thiết kế refresh riêng |
| Spring Cloud Kubernetes đọc qua API | Kết quả còn phụ thuộc nguồn đã cấu hình và cơ chế refresh | Chỉ rõ tên nguồn và quyền truy cập |

Kubernetes mô tả riêng hành vi cập nhật của biến môi trường, volume và `subPath` trong tài liệu [ConfigMaps](https://kubernetes.io/docs/concepts/configuration/configmap/) và [Secrets](https://kubernetes.io/docs/concepts/configuration/secret/).

Không có giao dịch nguyên tử bao trùm ConfigMap, Secret, Deployment và trạng thái trong JVM. Vì vậy, quy trình phát hành phải tạo các phụ thuộc trước, chuyển tham chiếu trong Pod template sau, rồi kiểm tra ứng dụng thực sự phục vụ được yêu cầu.

## 3. Chọn cách gắn phiên bản

| Phương án | Điều làm Pod template thay đổi | Điểm cần quản lý |
|---|---|---|
| Tên thủ công, như `orders-config-r2` | Tham chiếu trong volume hoặc biến môi trường | Không tái sử dụng tên với nội dung khác |
| Kustomize sinh tên có hậu tố băm | Tên sinh ra và các tham chiếu được biến đổi | Kiểm tra manifest kết xuất, giữ phiên bản cũ |
| Giữ tên cố định, thêm checksum annotation | Annotation trong `spec.template.metadata` | Giữ riêng bản dữ liệu cũ để có thể khôi phục |

Checksum chỉ nên được tính tự động từ đầu vào xác định, thay vì nhập một giá trị tượng trưng bằng tay. Nếu annotation nằm ở `metadata.annotations` của Deployment mà không nằm dưới `spec.template`, thay annotation đó không tạo rollout.

Deployment tạo rollout khi Pod template thay đổi; sửa riêng ConfigMap hoặc Secret cùng tên không tạo một revision Deployment mới. Xem [cơ chế cập nhật Deployment](https://kubernetes.io/docs/concepts/workloads/controllers/deployment/#updating-a-deployment).

**Lựa chọn cho ví dụ chính:** tên có phiên bản và `immutable: true`. Đối với ConfigMap/Secret immutable, không thể sửa dữ liệu hoặc chuyển lại thành mutable; cần tạo tài nguyên khác. Cờ này không cấm xóa tài nguyên, nên vẫn phải kiểm soát quyền xóa và tránh xóa rồi tạo lại cùng tên. Xem [cấu hình immutable](https://kubernetes.io/docs/tutorials/configuration/updating-configuration-via-a-configmap/).

## 4. Ví dụ R1: cấu hình, bí mật và Deployment khớp nhau

### 4.1. Điều kiện thực hành

Ví dụ giả định:

- Namespace `shop` đã tồn tại và bạn đang dùng đúng Kubernetes context.
- Có một image ứng dụng Spring Boot `orders` hỗ trợ cấu hình ngoài, Spring Boot Actuator, JDBC và trình điều khiển PostgreSQL.
- Service cơ sở dữ liệu `orders-db` trong namespace đó đang hoạt động; tài khoản và mật khẩu được cấp thực sự ở PostgreSQL.
- Ứng dụng nghe cổng `8080`; đường dẫn health không yêu cầu đăng nhập đối với probe nội bộ. Mọi chính sách Spring Security và mạng phải được cấu hình phù hợp.
- Ứng dụng không cần gọi Kubernetes API trong biến thể minh họa này; không bật nguồn `kubernetes:` hoặc bootstrap đọc cấu hình qua API.

Tên image và mật khẩu dưới đây là **giá trị mẫu**, không phải tài nguyên đã được cung cấp. Thay bằng image có thật và thông tin lab khớp cơ sở dữ liệu trước khi triển khai. Các tên file trong ví dụ là cách tổ chức tài liệu triển khai cho người học.

### 4.2. ConfigMap chứa cấu hình công khai

Nội dung minh họa của `configmap-r1.yaml`:

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: orders-config-r1
  namespace: shop
  labels:
    app.kubernetes.io/name: orders
    app.kubernetes.io/part-of: shop-platform
immutable: true
data:
  application.yaml: |
    spring:
      application:
        name: orders
      datasource:
        url: jdbc:postgresql://orders-db:5432/orders
    server:
      port: 8080
    app:
      release-id: r1
      credential-version: db-v1
      checkout:
        timeout: 2s
    management:
      endpoints:
        web:
          exposure:
            include: health
      endpoint:
        health:
          probes:
            enabled: true
          group:
            readiness:
              include: readinessState,db
```

`app.checkout.timeout` là thuộc tính do ứng dụng tự định nghĩa: mã nghiệp vụ phải bind và sử dụng nó. Việc thêm key vào ConfigMap không tự tạo hành vi timeout.

`app.credential-version` là nhãn truy vết không nhạy cảm. Giá trị này giúp đối chiếu bản phát hành, nhưng không chứng minh mật khẩu đã được backend chấp nhận.

Readiness ở đây chủ động bao gồm `db` vì giả định dịch vụ không thể phục vụ khi không truy cập được cơ sở dữ liệu. Với hệ thống có khả năng phục vụ một phần khi DB lỗi, cần xem lại lựa chọn này.

### 4.3. Secret riêng, dùng dữ liệu giả cho lab

Nội dung minh họa của `secret-r1.yaml`:

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: orders-db-v1
  namespace: shop
  labels:
    app.kubernetes.io/name: orders
type: Opaque
immutable: true
stringData:
  username: orders_v1
  password: LAB_ONLY_REPLACE_WITH_MATCHING_DB_PASSWORD
```

`stringData` giúp viết ví dụ dễ đọc; tài liệu này không chứa bí mật thật. Không đưa manifest có thông tin xác thực thật vào Git công khai hoặc log pipeline. Dữ liệu base64 trong trường `data` cũng không phải mã hóa bảo mật. Trong môi trường thật, dùng quy trình cấp bí mật được bảo vệ, quyền tối thiểu và mã hóa khi lưu trữ. Xem [thực hành quản lý Secret](https://kubernetes.io/docs/concepts/security/secrets-good-practices/).

Đặt `immutable: true` không tự tạo tài khoản PostgreSQL, không đổi mật khẩu ở DB và không đảm bảo backend còn chấp nhận phiên bản cũ.

### 4.4. Pod template tham chiếu đúng hai phiên bản

Nội dung minh họa của `deployment-r1.yaml`:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders
  namespace: shop
  annotations:
    kubernetes.io/change-cause: "release r1; config r1; credentials db-v1"
spec:
  replicas: 2
  revisionHistoryLimit: 5
  minReadySeconds: 10
  progressDeadlineSeconds: 300
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxUnavailable: 0
      maxSurge: 1
  selector:
    matchLabels:
      app.kubernetes.io/name: orders
  template:
    metadata:
      labels:
        app.kubernetes.io/name: orders
      annotations:
        learning.example.com/release-id: r1
    spec:
      automountServiceAccountToken: false
      containers:
        - name: orders
          image: registry.example.com/shop/orders:1.8.0
          ports:
            - name: http
              containerPort: 8080
          env:
            - name: SPRING_CONFIG_ADDITIONAL_LOCATION
              value: "file:/etc/orders-config/"
            - name: SPRING_DATASOURCE_USERNAME
              valueFrom:
                secretKeyRef:
                  name: orders-db-v1
                  key: username
            - name: SPRING_DATASOURCE_PASSWORD
              valueFrom:
                secretKeyRef:
                  name: orders-db-v1
                  key: password
          volumeMounts:
            - name: app-config
              mountPath: /etc/orders-config
              readOnly: true
          startupProbe:
            httpGet:
              path: /actuator/health/liveness
              port: http
            periodSeconds: 5
            timeoutSeconds: 2
            failureThreshold: 30
          readinessProbe:
            httpGet:
              path: /actuator/health/readiness
              port: http
            periodSeconds: 5
            timeoutSeconds: 2
          livenessProbe:
            httpGet:
              path: /actuator/health/liveness
              port: http
            periodSeconds: 10
            timeoutSeconds: 2
          resources:
            requests:
              cpu: 200m
              memory: 512Mi
            limits:
              memory: 1Gi
      volumes:
        - name: app-config
          configMap:
            name: orders-config-r1
```

Các liên kết quan trọng:

- `application.yaml` được mount thành `/etc/orders-config/application.yaml`.
- `SPRING_CONFIG_ADDITIONAL_LOCATION` bổ sung thư mục cấu hình ngoài, giữ các vị trí mặc định của Spring Boot. Không dùng `optional:` vì bản cấu hình này là phụ thuộc bắt buộc.
- Username và password đến từ đúng `orders-db-v1`. Biến môi trường có thể ghi đè thuộc tính cùng tên trong Config Data, nên phải kiểm soát cả `env` và `envFrom`.
- Annotation release nằm trong Pod template để mỗi Pod mang dấu vết release.
- Selector của Deployment giữ ổn định qua các release.

Quy tắc vị trí cấu hình và độ ưu tiên được mô tả trong [Spring Boot Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html).

`maxUnavailable: 0` cho phép giữ Pod cũ trong khi chờ Pod mới sẵn sàng, nhưng không phải cam kết không gián đoạn trong mọi tình huống. Cụm phải có tài nguyên cho Pod tăng thêm; ứng dụng và cấu hình cũ/mới phải hoạt động đồng thời được.

## 5. Triển khai R1 và kiểm tra đúng lớp

Áp dụng lần lượt để phụ thuộc tồn tại trước khi tạo Pod:

```bash
kubectl config current-context

kubectl apply -f configmap-r1.yaml
kubectl apply -f secret-r1.yaml
kubectl apply -f deployment-r1.yaml

kubectl rollout status deployment/orders -n shop --timeout=300s
kubectl get pods -n shop -l app.kubernetes.io/name=orders
```

Lệnh áp dụng Secret ở trên dành cho lab với manifest được bảo vệ. Trong production, thay bước đó bằng cơ chế cấp bí mật của hệ thống triển khai.

Đừng chỉ kiểm tra lệnh `apply` trả về thành công. Hãy xác minh ba lớp:

| Lớp | Bằng chứng cần có |
|---|---|
| Kubernetes | Deployment đã hội tụ; Pod mới Ready |
| Định danh release | Pod đang tham chiếu ConfigMap/Secret đúng phiên bản |
| Nghiệp vụ | Giao dịch kiểm thử thành công với cấu hình và thông tin xác thực mới |

Các lệnh sau chỉ đọc tên tham chiếu, không xuất nội dung Secret:

```bash
kubectl get deployment orders -n shop -o jsonpath='{.spec.template.spec.volumes[0].configMap.name}'
kubectl get deployment orders -n shop -o jsonpath='{.spec.template.spec.containers[0].env[1].valueFrom.secretKeyRef.name}'
kubectl get pods -n shop -l app.kubernetes.io/name=orders -o custom-columns='NAME:.metadata.name,RELEASE:.metadata.annotations.learning\.example\.com/release-id,CONFIG:.spec.volumes[0].configMap.name'
```

Chỉ số `[0]` và `[1]` dựa vào cấu trúc manifest ví dụ. Khi thêm volume/container/biến môi trường, cập nhật truy vấn hoặc dùng công cụ chọn theo tên.

Ứng dụng nên ghi `app.release-id` và `app.credential-version` một lần khi khởi động, đồng thời có một phép thử kết nối DB hoặc giao dịch tổng hợp. Không ghi username/password, nội dung Secret hay toàn bộ Spring Environment.

Startup probe cho ứng dụng thời gian khởi động trước khi các probe còn lại hoạt động. Readiness quyết định Pod có sẵn sàng nhận lưu lượng; liveness xử lý tình trạng tiến trình cần khởi động lại. Xem [Kubernetes probes](https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/).

Spring Boot không mặc định đưa kiểm tra DB vào readiness; ví dụ đã bổ sung có chủ ý. Không đưa DB vào liveness vì sự cố DB có thể khiến hàng loạt instance bị khởi động lại. Xem [kiểm tra hệ thống ngoài với Spring Boot probes](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html#actuator.endpoints.kubernetes-probes.external-state).

## 6. Phát hành R2 chỉ thay đổi cấu hình

Giả sử cần tăng `app.checkout.timeout` từ `2s` lên `3s`, không đổi thông tin xác thực.

1. Tạo `orders-config-r2` với toàn bộ cấu hình đã duyệt: `release-id: r2`, timeout `3s` và vẫn `credential-version: db-v1`.
2. Giữ `orders-config-r1` nguyên vẹn.
3. Tạo manifest Deployment R2 từ tổ hợp R1, đổi tên ConfigMap trong volume sang `orders-config-r2` và annotation Pod sang `r2`.
4. Cập nhật `kubernetes.io/change-cause` để mô tả R2; giữ Secret `orders-db-v1` và image cũ.
5. Tạo ConfigMap mới trước, rồi áp dụng Deployment R2.

```bash
kubectl apply -f configmap-r2.yaml
kubectl apply -f deployment-r2.yaml
kubectl rollout status deployment/orders -n shop --timeout=300s
kubectl rollout history deployment/orders -n shop
```

Thay tham chiếu volume nằm trong `spec.template` làm Pod template đổi. Các Pod R1 vẫn đọc cấu hình R1; Pod R2 khởi động với cấu hình R2.

Trong thời gian rolling update, hai giá trị timeout có thể cùng tồn tại. Chọn thay đổi tương thích với giai đoạn này. Nếu nghiệp vụ đòi hỏi chuyển toàn bộ người dùng tại cùng một thời điểm, cần thiết kế chuyển lưu lượng và quản lý trạng thái phù hợp, thay vì mặc định rolling update đáp ứng được.

Với mô hình cấu hình cố định theo Pod, không sửa R1 tại chỗ rồi chạy `rollout restart` để thay cho một bản cấu hình có định danh. Restart có thể tạo Pod mới, nhưng tự nó không lưu lại dữ liệu cấu hình cũ.

## 7. Quay lui: khôi phục đúng tổ hợp

### 7.1. Quay lui R2 về R1

Nếu R2 chỉ thay timeout và `orders-config-r1` còn tồn tại, có thể triển khai lại manifest đã duyệt của R1. Đây là cách làm rõ ràng khi hệ thống vận hành lấy Git hoặc một kho artifact làm nguồn mong muốn.

Trong thao tác khẩn cấp bằng kubectl, xem lịch sử và chọn revision tương ứng:

```bash
kubectl rollout history deployment/orders -n shop
kubectl rollout history deployment/orders -n shop --revision=1

kubectl rollout undo deployment/orders -n shop --to-revision=1
kubectl rollout status deployment/orders -n shop --timeout=300s
```

`1` chỉ là ví dụ về revision; phải đối chiếu lịch sử thực tế. Release `R1` do nhóm đặt tên không phải lúc nào cũng trùng revision số `1` của Kubernetes.

`rollout undo` quay lại Pod template, không khôi phục dữ liệu ConfigMap, Secret hay DB. Vì template R1 tham chiếu tên riêng còn được giữ lại, Pod mới có thể đọc lại cấu hình R1. Xem [phạm vi rollback Deployment](https://kubernetes.io/docs/concepts/workloads/controllers/deployment/#rolling-back-a-deployment).

Nếu GitOps controller vẫn mong muốn R2, thao tác undo có thể bị điều hòa trở lại. Phải cập nhật nguồn mong muốn theo quy trình của nhóm và xác minh trạng thái cuối cùng.

### 7.2. Những điều khiến rollback không còn an toàn

- ConfigMap/Secret cũ đã bị xóa hoặc tên cũ bị tạo lại với dữ liệu khác.
- Credential cũ vẫn có trong Secret nhưng đã bị DB thu hồi.
- Image dùng tag cũ nhưng nội dung tag đã thay đổi hoặc image không còn tải được.
- Ứng dụng mới đã thực hiện migration khiến phiên bản cũ không còn đọc được dữ liệu.
- Cấu hình R1 phụ thuộc endpoint, chứng chỉ hoặc chính sách không còn hiệu lực.

Giữ ReplicaSet cũ bằng `revisionHistoryLimit` hỗ trợ lịch sử Deployment, nhưng không tự giữ các tài nguyên cấu hình độc lập và không sao lưu trạng thái bên ngoài.

## 8. Xoay vòng Secret cần phối hợp với backend

Khi phát hành R3 dùng `orders-db-v2`, chỉ tạo một Secret Kubernetes mới là chưa đủ. Một trình tự thiết kế có khả năng quay lui là:

1. Cấp thông tin xác thực V2 tại backend; xác định có cho V1 và V2 cùng hợp lệ trong giai đoạn chuyển tiếp hay không.
2. Đưa V2 vào kho bí mật được bảo vệ, tạo `orders-db-v2` từ đúng phiên bản đó.
3. Kiểm tra khả năng sử dụng V2 bằng quy trình không làm lộ giá trị.
4. Tạo ConfigMap R3 với dấu vết `credential-version: db-v2` và Deployment R3 tham chiếu V2.
5. Rollout, kiểm tra Pod mới và một giao dịch thực tế; quan sát lỗi xác thực và kết nối.
6. Giữ V1 trong cửa sổ quay lui đã xác định; thu hồi V1 sau khi đủ điều kiện kết thúc.
7. Cập nhật mốc có thể khôi phục và kế hoạch dọn tài nguyên.

Nếu backend chỉ hỗ trợ một mật khẩu đang hiệu lực cho mỗi tài khoản, đổi mật khẩu có thể làm Pod cũ mất khả năng mở kết nối mới. Phương án có thể là dùng hai tài khoản chuyển tiếp, cơ chế nhiều khóa của backend hoặc cửa sổ bảo trì đã thiết kế.

Đây là lựa chọn kiến trúc của hệ thống, không phải bảo đảm của Kubernetes. Sau khi thu hồi V1, quay lui image và ConfigMap có thể vẫn cần giữ credential V2 nếu ứng dụng cũ tương thích; không được mặc định phục hồi nguyên Secret V1 là đủ.

Với bộ điều khiển đồng bộ bí mật bên ngoài, tên Secret ổn định chưa chắc tương ứng với nội dung cố định. Muốn giữ ngữ nghĩa release, cần ghim phiên bản nguồn hoặc cấp một tên đích riêng theo khả năng của công cụ đang dùng.

## 9. Tự động sinh tên bằng Kustomize

Khi số phiên bản tăng, có thể để Kustomize sinh hậu tố băm. Ví dụ này là **phương án thay thế** cho cách đặt tên `r1/r2` thủ công.

Giả sử `deployment-base.yaml` có cùng cấu trúc Deployment phía trên, nhưng tham chiếu tên gốc `orders-config` và `orders-db`. File `application.yaml` là cấu hình không nhạy cảm. Hai file trong `.runtime-secrets` do pipeline cấp trong vùng làm việc được bảo vệ.

Nội dung `kustomization.yaml` minh họa:

```yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization

namespace: shop

resources:
  - deployment-base.yaml

configMapGenerator:
  - name: orders-config
    files:
      - application.yaml=application.yaml

secretGenerator:
  - name: orders-db
    type: Opaque
    files:
      - username=.runtime-secrets/username
      - password=.runtime-secrets/password

generatorOptions:
  disableNameSuffixHash: false
```

Kustomize thêm hậu tố theo nội dung và cập nhật các trường tham chiếu Kubernetes được hỗ trợ, như tên ConfigMap trong volume và tên Secret trong `secretKeyRef`. Dữ liệu thay đổi có thể làm tên tham chiếu trong Pod template thay đổi, từ đó tạo rollout. Xem [quản lý cấu hình bằng Kustomize](https://kubernetes.io/docs/tasks/manage-kubernetes-objects/kustomization/).

```bash
kubectl apply -k .
kubectl rollout status deployment/orders -n shop --timeout=300s
```

Những giới hạn cần đưa vào quy trình:

- File nguồn Secret và manifest kết xuất vẫn chứa bí mật; không commit, lưu artifact công khai hoặc in toàn bộ kết quả build vào log.
- Kiểm soát ký tự xuống dòng trong file mật khẩu vì chúng có thể trở thành một phần giá trị.
- Giữ hậu tố băm giúp nhận diện thay đổi; nó không tự bật `immutable: true` hay cấm người có quyền sửa tài nguyên sinh ra.
- Không giả định Kustomize sửa mọi chuỗi chứa tên ConfigMap. Chuỗi nằm trong nội dung `application.yaml` hay biến môi trường tùy ý cần được xử lý và xác minh riêng.
- Việc giữ hoặc xóa tài nguyên cũ tùy thuộc công cụ triển khai và chính sách prune; cần thiết kế rõ cửa sổ rollback.

Đặc biệt, nếu Spring Cloud Kubernetes đọc qua API, một tên nguồn nằm bên trong `spring.cloud.kubernetes.config.sources` không mặc nhiên được biến đổi như `volumes[].configMap.name`.

## 10. Chọn vai trò phù hợp cho Spring Cloud Kubernetes

### 10.1. Đọc file hoặc biến môi trường lúc khởi động

Ví dụ chính dùng cơ chế Kubernetes mount dữ liệu và Spring Boot đọc cấu hình ngoài. Nó không cần Spring Cloud Kubernetes Config gọi API để lấy cùng nguồn dữ liệu.

`automountServiceAccountToken: false` phù hợp với giả định không có chức năng nào trong Pod cần Kubernetes API. Nếu ứng dụng sử dụng DiscoveryClient, nguồn cấu hình qua API hoặc thành phần khác cần token, phải thiết kế lại việc cấp danh tính và RBAC trước khi dùng manifest này.

Spring Cloud LoadBalancer và DiscoveryClient giải quyết việc tìm/chọn đích gọi dịch vụ. Chúng không gắn phiên bản ConfigMap/Secret với release và không khôi phục credential.

### 10.2. Đọc ConfigMap theo tên qua API

Nếu chọn Spring Cloud Kubernetes Config, hãy cấu hình tên nguồn trùng phiên bản được triển khai, thay vì trông chờ tên mặc định suy từ `spring.application.name`. Cấu hình chọn nguồn phải sẵn có trước khi thực hiện lần đọc nguồn đó.

Ví dụ ý tưởng cho một nguồn đặt tên rõ ràng:

```yaml
spring:
  application:
    name: orders
  config:
    import: "kubernetes:"
  cloud:
    kubernetes:
      config:
        sources:
          - name: orders-config-r2
            namespace: shop
        include-profile-specific-sources: false
```

Đây là cấu hình **phương án API**, không thêm nguyên khối vào ví dụ đọc file. Cần dependency phù hợp với Spring Cloud release train, danh tính gọi API, RBAC và chiến lược xử lý nguồn thiếu. Nếu thực sự cần profile-specific sources, hãy quản lý chúng như một phần tổ hợp release thay vì tắt.

Cách chọn nguồn và profile được mô tả trong [ConfigMap PropertySource](https://docs.spring.io/spring-cloud-kubernetes/reference/property-source-config/configmap-propertysource.html); cơ chế import được mô tả trong [Kubernetes PropertySource implementations](https://docs.spring.io/spring-cloud-kubernetes/reference/property-source-config.html).

### 10.3. Configuration Watcher dành cho chính sách refresh

Watcher hữu ích khi nhóm chủ động muốn thay đổi cấu hình mà không rollout mọi Pod. Nó gửi thông báo refresh; tính đúng đắn vẫn phụ thuộc nguồn được nạp, đường truyền thông báo và các bean có hỗ trợ refresh.

Tạo `orders-config-r2` không tự làm Pod đang mount `orders-config-r1` chuyển sang đọc R2. Một thông báo refresh cũng không sửa tham chiếu trong Pod spec. Nếu tên tài nguyên có hậu tố khác tên ứng dụng, còn phải cấu hình ánh xạ thông báo đúng ứng dụng.

Nếu chọn mô hình refresh, cần kiểm soát endpoint quản trị, quyền của watcher, độ trễ cập nhật volume và giai đoạn các instance đọc giá trị khác nhau. Xem [Spring Cloud Kubernetes Configuration Watcher](https://docs.spring.io/spring-cloud-kubernetes/reference/spring-cloud-kubernetes-configuration-watcher.html).

Với bài toán cấu hình cố định theo release đang thực hành, rollout là cơ chế áp dụng thay đổi chính. Không cần bật watcher chỉ vì ứng dụng chạy trên Kubernetes.

## 11. RBAC và quyền sở hữu vòng đời tài nguyên

Tách trách nhiệm giữa các thành phần:

| Thành phần | Trách nhiệm | Quyền cần xem xét |
|---|---|---|
| Pipeline triển khai | Tạo cấu hình, áp dụng Deployment | Quyền ghi giới hạn namespace và loại tài nguyên |
| Cơ chế cấp bí mật | Cấp đúng Secret từ phiên bản được bảo vệ | Quyền phù hợp với nơi lưu bí mật và Secret đích |
| Ứng dụng đọc file/env | Đọc dữ liệu được đưa vào container | Không cần quyền API `get secrets` chỉ để nhận volume/env |
| Ứng dụng đọc API | Truy vấn nguồn cấu hình đã chọn | Role/RoleBinding khớp thư viện và cách truy vấn |
| Watcher | Theo dõi thay đổi và gửi refresh | Quyền watch/list cùng quyền kết nối quản trị cần thiết |
| Tác vụ dọn dẹp | Xóa phiên bản hết hạn giữ lại | Quyền xóa tách khỏi quyền đọc của ứng dụng |

Không cấp `cluster-admin` để giải quyết lỗi đọc một ConfigMap. Đồng thời, không cho rằng giới hạn `resourceNames` luôn dùng được với mọi chế độ đọc API: một số cách triển khai truy vấn theo danh sách cần quyền khác. Hãy đối chiếu chế độ đọc của phiên bản thư viện và kiểm tra quyền thực tế.

Người có quyền tạo Pod trong namespace có thể tạo Pod tham chiếu Secret ở namespace đó. Vì vậy, bảo vệ bí mật không chỉ là chặn thao tác `get secret`; còn phải kiểm soát ai được triển khai workload. Kubernetes nhấn mạnh các quan hệ quyền này trong [khuyến nghị bảo vệ Secret](https://kubernetes.io/docs/concepts/configuration/secret/#information-security-for-secrets).

## 12. Dọn dẹp mà vẫn giữ khả năng khôi phục

Đừng xóa tất cả ConfigMap/Secret “không còn được Deployment hiện tại trỏ tới”. Một phiên bản cũ có thể vẫn cần cho Pod đang kết thúc, Job, một Deployment khác hoặc release được phép rollback.

Quy trình dọn dẹp nên dựa trên:

1. Danh sách release còn được hỗ trợ khôi phục.
2. Tham chiếu của các workload và Pod còn tồn tại.
3. Thời điểm kết thúc cửa sổ quay lui.
4. Trạng thái còn hiệu lực hay đã thu hồi của credential.
5. Chính sách bảo vệ artifact, dữ liệu bí mật và lịch sử kiểm toán.

Xóa Secret Kubernetes không đồng nghĩa đã thu hồi mật khẩu ở backend. Giữ Secret Kubernetes cũng không đồng nghĩa mật khẩu vẫn hợp lệ.

Với Secret đã bị lộ, ưu tiên thu hồi theo quy trình sự cố; không giữ credential nguy hiểm chỉ để duy trì khả năng rollback nguyên trạng. Sau đó xác lập lại một tổ hợp release an toàn.

## 13. Tình huống thực hành và chẩn đoán

Thực hiện trong môi trường lab, dùng dữ liệu giả:

| Tình huống | Quan sát mong đợi | Hướng xử lý |
|---|---|---|
| R1 → R2 chỉ đổi timeout và tên ConfigMap | Có rollout, Pod mới tham chiếu R2 | Kiểm tra giá trị ứng dụng dùng và giao dịch mẫu |
| Deployment R2 trỏ tới Secret không tồn tại | Pod mới có lỗi tạo cấu hình container; rollout không hoàn tất | Tạo đúng phụ thuộc hoặc khôi phục tham chiếu |
| Sửa dữ liệu ConfigMap immutable R1 | API từ chối thay đổi dữ liệu | Tạo tên phiên bản mới |
| Đổi annotation ngoài Pod template | Không có rollout chỉ vì thay annotation đó | Chuyển dấu vết cần rollout vào `spec.template.metadata` |
| DB đã thu hồi V1 rồi undo về template dùng V1 | Pod có thể chạy nhưng kết nối DB thất bại hoặc không Ready | Chọn credential còn hiệu lực và tương thích |
| Xóa ConfigMap R1 rồi rollback về R1 | Pod mới không mount được cấu hình cần thiết | Khôi phục tài nguyên chính xác từ nguồn được bảo vệ |

Khi rollout thất bại, bắt đầu từ Pod mới và sự kiện của nó:

```bash
kubectl get pods -n shop -l app.kubernetes.io/name=orders
kubectl describe pod TEN_POD_MOI -n shop
kubectl rollout status deployment/orders -n shop --timeout=60s
```

Thay `TEN_POD_MOI` bằng tên Pod thực tế. Phân biệt lỗi không tìm thấy ConfigMap/Secret, thiếu key, không kéo được image, ứng dụng khởi động lỗi, và readiness thất bại. Đọc log theo chính sách che giấu bí mật của hệ thống; tránh xuất toàn bộ Secret để chẩn đoán.

## 14. Điều kiện một release sẵn sàng đưa vào vận hành

Trước khi coi bản phát hành hoàn tất, xác nhận:

- Image, ConfigMap, Secret, namespace và profile có định danh nhất quán.
- Cấu hình không nhạy cảm được lưu phiên bản; bí mật chỉ được tham chiếu qua quy trình được bảo vệ.
- Pod template đổi khi cần rollout; nguồn cấu hình bắt buộc đã tồn tại.
- Pod mới Ready và giao dịch kiểm thử chứng minh hành vi mong muốn.
- Giai đoạn Pod cũ/mới chạy đồng thời đã được cân nhắc.
- Kế hoạch quay lui chỉ rõ tài nguyên cần giữ và credential còn hợp lệ.
- Vai trò của Spring Cloud Kubernetes Config, DiscoveryClient, LoadBalancer và Watcher được chọn theo nhu cầu thực tế.
- Quyền triển khai, đọc API, theo dõi và dọn dẹp được phân công rõ ràng.

Kết quả cần đạt là khả năng xác định chính xác **ứng dụng nào đang dùng cấu hình và phiên bản bí mật nào**, rồi triển khai hoặc khôi phục một tổ hợp đã biết mà không phụ thuộc vào dữ liệu bị sửa âm thầm dưới cùng một tên.
