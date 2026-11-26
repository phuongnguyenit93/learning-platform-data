# Khai báo ConfigMap, Secret, volume và volumeMount

## Mục tiêu bài học

Trong chương **Manifest triển khai** của **SPRING_CLOUD_KUBERNETES**, bài học này nối cấu hình Kubernetes với những tệp mà ứng dụng Spring thực sự đọc. Bạn sẽ khai báo nguồn dữ liệu, chọn khóa cần cấp cho Pod, đặt đường dẫn trong container và cấu hình Spring để nạp đúng định dạng.

Sau bài học, bạn có thể:

- Viết ConfigMap và Secret đúng cấu trúc, đúng namespace.
- Phân biệt tên tài nguyên, tên volume, tên khóa và đường dẫn mount.
- Khai báo `volumes` ở cấp Pod và `volumeMounts` ở cấp container.
- Chọn quyền tệp phù hợp tiến trình không chạy root.
- Nạp YAML và Secret vào Spring Boot, kiểm tra tham chiếu mà không in thông tin nhạy cảm.
- Hiểu giới hạn cập nhật dữ liệu và khi nào cần Spring Cloud Kubernetes hoặc Configuration Watcher.

Các manifest dùng namespace lab `manifest-lab` và ứng dụng `catalog-service`. Token `lab-only-token` là dữ liệu giả, không có quyền truy cập hệ thống nào. Mọi đường dẫn tệp trong hướng dẫn thực hành là ví dụ để người học tạo trong môi trường lab.

## 1. Bốn thành phần và ba lần ánh xạ

ConfigMap/Secret là tài nguyên chứa dữ liệu. Volume mô tả nguồn dữ liệu cấp cho Pod. VolumeMount mô tả nơi một container nhìn thấy volume đó.

```text
ConfigMap hoặc Secret
  metadata.name + khóa dữ liệu
            |
            | volumes[].configMap.name / volumes[].secret.secretName
            v
Volume trong Pod
  volumes[].name + items[].key → items[].path
            |
            | volumeMounts[].name khớp volumes[].name
            v
Đường dẫn trong container
  volumeMounts[].mountPath + items[].path
            |
            | ứng dụng phải được cấu hình đọc đường dẫn này
            v
Thuộc tính của ứng dụng Spring
```

Ví dụ:

```text
Tài nguyên:   catalog-partner-v1
Khóa:         partner.api-token
Tên volume:   partner-secret
Đường mount:  /etc/catalog/secrets
Đường tương đối của khóa: partner.api-token

Tệp container thấy:
  /etc/catalog/secrets/partner.api-token
```

Các tên ở trên phục vụ những vai trò khác nhau. Tên volume không phải bắt buộc trùng tên Secret. Tên tệp cũng có thể khác tên khóa nếu bạn đổi `items[].path`.

| Trường | Thuộc phạm vi nào? | Tham chiếu tới đâu? |
| --- | --- | --- |
| `metadata.name` của ConfigMap/Secret | Namespace | Danh tính tài nguyên Kubernetes |
| `volumes[].name` | Một Pod | Tên nội bộ để container chọn volume |
| `configMap.name` | Nguồn của volume | ConfigMap trong namespace của Pod |
| `secret.secretName` | Nguồn của volume | Secret trong namespace của Pod |
| `items[].key` | Dữ liệu của nguồn | Một khóa đã tồn tại |
| `items[].path` | Bên trong volume | Tên tệp hoặc đường dẫn tương đối |
| `volumeMounts[].name` | Một container | Volume đã khai báo trong Pod |
| `mountPath` | Filesystem của container | Đường dẫn mount tuyệt đối |

Đọc manifest theo chuỗi tham chiếu này sẽ dễ tìm lỗi hơn việc chỉ nhìn tên ứng dụng.

## 2. Khai báo ConfigMap: dữ liệu không nhạy cảm

### 2.1. Một tệp cấu hình YAML là một giá trị chuỗi

Lưu ví dụ thành `catalog-config.yml`:

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: catalog-config-v1
  namespace: manifest-lab
immutable: true
data:
  application.yml: |
    partner:
      base-url: https://partner.sandbox.example
      timeout: 3s
  release-label: "catalog-v1"
```

Có hai khóa Kubernetes:

- `application.yml`: giá trị là toàn bộ một tài liệu YAML.
- `release-label`: giá trị là một chuỗi ngắn.

`partner`, `base-url` và `timeout` nằm bên trong chuỗi của `application.yml`, không phải ba khóa riêng trong `ConfigMap.data`.

Điều này ảnh hưởng trực tiếp đến `items`. Nếu viết `key: partner.timeout`, kubelet sẽ tìm một khóa có tên đó ở ngoài cùng và không tìm thấy trong ví dụ này.

Miền `example` là địa chỉ minh họa. Trước khi thực hành lời gọi đối tác, thay bằng endpoint thử nghiệm do bạn kiểm soát.

### 2.2. Cấu trúc dữ liệu cần chú ý

`data` dành cho giá trị chuỗi. Nếu muốn một khóa phẳng chứa boolean hoặc số, hãy biểu diễn giá trị thành chuỗi:

```yaml
data:
  feature-enabled: "true"
  retry-count: "3"
```

`binaryData` dành cho dữ liệu nhị phân được biểu diễn Base64. Không khai báo cùng một khóa trong cả `data` và `binaryData`. ConfigMap không phải kho lưu cấu hình dung lượng lớn; dữ liệu của một ConfigMap bị giới hạn ở mức 1 MiB. Xem [khái niệm ConfigMap](https://kubernetes.io/docs/concepts/configuration/configmap/).

Một YAML Kubernetes hợp lệ không đảm bảo chuỗi YAML bên trong cũng hợp lệ với Spring. API server có thể chấp nhận `application.yml` như văn bản dù bên trong sai indentation hoặc sai tên thuộc tính ứng dụng.

Không đặt token, mật khẩu hoặc private key vào ConfigMap. Tên khóa mang chữ `secret` không làm dữ liệu trở thành bí mật.

## 3. Khai báo Secret: phân biệt data và stringData

### 3.1. Manifest lab với stringData

Lưu thành `catalog-secret-lab.yml`:

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: catalog-partner-v1
  namespace: manifest-lab
type: Opaque
immutable: true
stringData:
  partner.api-token: "lab-only-token"
```

`type: Opaque` phù hợp một cặp khóa/giá trị tùy ứng dụng. `stringData` giúp nhập chuỗi mà không tự encode trước. API server chuyển dữ liệu này sang dạng lưu trữ của Secret.

Giá trị trong ví dụ chỉ dùng cho lab. Đối với Secret thật, hệ thống quản lý bí mật hoặc pipeline được cấp quyền nên cung cấp dữ liệu; không commit manifest chứa giá trị rõ vào Git.

### 3.2. Biểu diễn cùng dữ liệu bằng data

Một cách khai báo thay thế cho cùng token giả:

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: catalog-partner-v1
  namespace: manifest-lab
type: Opaque
immutable: true
data:
  partner.api-token: bGFiLW9ubHktdG9rZW4=
```

Chỉ chọn một cách tạo tài nguyên này. Không áp dụng cả hai bản như hai tài nguyên độc lập.

Base64 ở trên biểu diễn chuỗi `lab-only-token`; nó không phải cơ chế mã hóa bảo mật. Khi mount Secret, tệp chứa dữ liệu đã giải mã Base64, không chứa chuỗi Base64 trong manifest.

Nếu cùng khóa xuất hiện trong `data` và `stringData`, `stringData` được ưu tiên. Tránh khai báo trùng để người đọc không phải đoán giá trị cuối cùng. Tài liệu cũng lưu ý `stringData` không hoạt động tốt với server-side apply. Xem [cấu trúc và ràng buộc Secret](https://kubernetes.io/docs/concepts/configuration/secret/#constraints-on-secret-names-and-data).

### 3.3. Cấp Secret thật từ tệp

Một phương án ngoài manifest rõ:

```bash
kubectl -n manifest-lab create secret generic catalog-partner-v1 \
  --from-file=partner.api-token=/secure/runtime/partner-token
```

`/secure/runtime/partner-token` là tệp do cơ chế quản lý bí mật cấp, nằm ngoài repository và build context. Nội dung phải đúng định dạng token, không có dòng xuống hàng ngoài ý muốn.

Lệnh này là phương án thay thế bước tạo Secret lab và yêu cầu tên tài nguyên chưa tồn tại. Không thực hiện nó sau khi đã tạo `catalog-partner-v1` bằng manifest rồi mong giá trị tự được thay thế.

Không đưa token thật vào `--from-literal=...` trên terminal hoặc pipeline ghi lại câu lệnh. Cũng không xuất Secret thành YAML để chuyển qua log. Quyền truy cập kho lưu trữ, API, bản sao lưu và máy chạy pipeline vẫn cần được bảo vệ.

## 4. Đặt volumes và volumeMounts đúng cấp

Với Deployment, nội dung Pod nằm dưới `spec.template`:

```yaml
spec:
  template:
    spec:
      containers:
        - name: app
          image: example-placeholder
          volumeMounts:
            - name: app-config
              mountPath: /etc/catalog/config
              readOnly: true
      volumes:
        - name: app-config
          configMap:
            name: catalog-config-v1
```

Đây là đoạn giải thích cấu trúc, chưa phải manifest hoàn chỉnh để áp dụng.

Các đường dẫn schema cần nhớ:

```text
Deployment:
  spec.template.spec.volumes
  spec.template.spec.containers[].volumeMounts

Pod trực tiếp:
  spec.volumes
  spec.containers[].volumeMounts
```

Đặt `volumes` bên trong container là sai cấp. Đặt `volumeMounts` cạnh `containers` cũng sai cấp.

Volume được khai báo cho Pod nhưng chỉ container có mount tương ứng mới nhìn thấy ở đường dẫn đó. Nếu thêm sidecar chỉ để gửi log, không mount Secret cho sidecar khi nó không cần dùng.

Không khai báo lặp hai khóa `volumeMounts` trong cùng một container để “thêm mount”. Tất cả mount phải là các phần tử trong một danh sách; parser hoặc API có thể từ chối hay làm mất dữ liệu khi có khóa YAML trùng.

## 5. items: chọn khóa và đặt tên tệp

### 5.1. Chỉ đưa khóa cần dùng vào volume

```yaml
volumes:
  - name: app-config
    configMap:
      name: catalog-config-v1
      items:
        - key: application.yml
          path: application.yml
```

ConfigMap có hai khóa nhưng volume chỉ nhận `application.yml`. `release-label` không xuất hiện thành tệp trong volume này.

Nếu bỏ `items`, các khóa của nguồn được đưa thành các tệp tương ứng. Dùng `items` để thể hiện rõ tập dữ liệu mà container được cấp. Xem [dùng ConfigMap dưới dạng tệp](https://kubernetes.io/docs/concepts/configuration/configmap/#using-configmaps-as-files-from-a-pod).

### 5.2. Đổi path mà không đổi key

```yaml
volumes:
  - name: app-config
    configMap:
      name: catalog-config-v1
      items:
        - key: application.yml
          path: runtime/settings.yml
```

Nếu mount tại `/etc/catalog`, tệp sẽ ở:

```text
/etc/catalog/runtime/settings.yml
```

`path` là đường dẫn tương đối bên trong volume. Không dùng đường dẫn tuyệt đối hoặc thành phần `..` để đi ra ngoài volume.

Chỉ đổi `path` không làm Spring tự tìm ra vị trí mới. Phải cập nhật đường dẫn import hoặc cấu hình đọc tệp của ứng dụng cùng lúc.

### 5.3. Nguồn và khóa bắt buộc

Khi không bật tùy chọn bỏ qua:

- ConfigMap/Secret được tham chiếu phải tồn tại trong namespace của Pod.
- Những khóa được liệt kê trong `items` phải tồn tại.
- Nếu chuẩn bị volume thất bại, container có thể chưa chạy nên chưa có log Spring để xem.

Có thể dùng `optional: true` ở nguồn khi dữ liệu thật sự tùy chọn. Ví dụ một ConfigMap bổ sung:

```yaml
volumes:
  - name: optional-overrides
    configMap:
      name: catalog-optional-overrides
      optional: true
```

Đây là ví dụ riêng, không cần thêm vào manifest chính.

`optional` chỉ điều chỉnh hành vi Kubernetes khi cấp dữ liệu. Nếu Spring vẫn import một tệp bắt buộc không tồn tại, Spring vẫn có thể thất bại. Ngược lại, `optional:` trong Spring Config Data không tạo một ConfigMap còn thiếu cho Kubernetes.

## 6. Manifest Deployment hoàn chỉnh

### 6.1. Điều kiện của image ứng dụng

Ví dụ giả định image của bạn:

- Chạy được với UID/GID `10001` trên Linux.
- Có ứng dụng Spring Boot hỗ trợ Config Data và `configtree:`, có từ Spring Boot 2.4.
- Có Web starter và Actuator, lắng nghe cổng `8080`.
- Dùng các thuộc tính `partner.base-url`, `partner.timeout` và `partner.api-token`.
- Kiểm tra giá trị token bắt buộc khi khởi động, không log token.
- Không bật các tích hợp Kubernetes API trong lab volume tối thiểu này.

Cấu hình Actuator an toàn có thể được đóng gói trong ứng dụng:

```yaml
spring:
  application:
    name: catalog-service

management:
  endpoints:
    web:
      exposure:
        include: health
  endpoint:
    health:
      probes:
        enabled: true
      show-details: never
```

Không có token mặc định trong JAR. URL và timeout được nhận từ ConfigMap bên ngoài.

### 6.2. Tạo namespace riêng

Lưu thành `namespace.yml`:

```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: manifest-lab
```

ConfigMap, Secret, ServiceAccount và Deployment bên dưới phải thuộc cùng namespace. Nguồn volume không có trường để trỏ sang một Secret ở namespace khác.

### 6.3. Deployment với hai volume dữ liệu

Lưu thành `catalog-deployment.yml`. Trước khi áp dụng, thay image placeholder bằng image digest đã build và push trong môi trường của bạn:

```yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: catalog-runtime
  namespace: manifest-lab
automountServiceAccountToken: false
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: catalog-service
  namespace: manifest-lab
spec:
  replicas: 2
  selector:
    matchLabels:
      app: catalog-service
  template:
    metadata:
      labels:
        app: catalog-service
      annotations:
        example.com/config-version: "v1"
        example.com/secret-version: "v1"
    spec:
      serviceAccountName: catalog-runtime
      automountServiceAccountToken: false
      securityContext:
        runAsNonRoot: true
        runAsUser: 10001
        runAsGroup: 10001
        fsGroup: 10001
        seccompProfile:
          type: RuntimeDefault
      containers:
        - name: app
          image: registry.example.com/catalog-service@sha256:REPLACE_WITH_REAL_DIGEST
          ports:
            - name: http
              containerPort: 8080
          env:
            - name: SPRING_CONFIG_IMPORT
              value: "file:/etc/catalog/config/application.yml,configtree:/etc/catalog/secrets/"
          volumeMounts:
            - name: app-config
              mountPath: /etc/catalog/config
              readOnly: true
            - name: partner-secret
              mountPath: /etc/catalog/secrets
              readOnly: true
            - name: app-tmp
              mountPath: /tmp
          securityContext:
            allowPrivilegeEscalation: false
            readOnlyRootFilesystem: true
            capabilities:
              drop: ["ALL"]
          startupProbe:
            httpGet:
              path: /actuator/health/liveness
              port: http
            periodSeconds: 5
            failureThreshold: 30
          readinessProbe:
            httpGet:
              path: /actuator/health/readiness
              port: http
            periodSeconds: 5
          livenessProbe:
            httpGet:
              path: /actuator/health/liveness
              port: http
            periodSeconds: 10
          resources:
            requests:
              cpu: 100m
              memory: 256Mi
            limits:
              memory: 512Mi
      volumes:
        - name: app-config
          configMap:
            name: catalog-config-v1
            defaultMode: 0444
            items:
              - key: application.yml
                path: application.yml
        - name: partner-secret
          secret:
            secretName: catalog-partner-v1
            defaultMode: 0440
            items:
              - key: partner.api-token
                path: partner.api-token
        - name: app-tmp
          emptyDir:
            sizeLimit: 128Mi
```

Các mức tài nguyên là điểm bắt đầu cho lab, cần đo trước khi dùng cho workload thật. Registry riêng có thể cần `imagePullSecrets`; thông tin kéo image là một nhu cầu khác với Secret runtime đang mount.

Volume `app-tmp` không chứa cấu hình. Nó cung cấp vùng ghi tạm khi root filesystem chỉ đọc và mất dữ liệu khi Pod bị xóa.

Không cần PersistentVolumeClaim để mount các nguồn ConfigMap/Secret này. Dữ liệu cấu hình không được ghi ngược về tài nguyên nguồn qua thao tác sửa tệp trong container.

### 6.4. Kết quả ánh xạ

```text
/etc/catalog/
├── config/
│   └── application.yml
└── secrets/
    └── partner.api-token

/tmp/
└── vùng ghi tạm của ứng dụng
```

| Tài nguyên nguồn | Khóa | Volume | Tệp cuối cùng |
| --- | --- | --- | --- |
| `catalog-config-v1` | `application.yml` | `app-config` | `/etc/catalog/config/application.yml` |
| `catalog-partner-v1` | `partner.api-token` | `partner-secret` | `/etc/catalog/secrets/partner.api-token` |

Khóa `release-label` không được mount vì không nằm trong `items`.

## 7. Spring phải biết cách đọc tệp đã mount

Deployment truyền:

```text
SPRING_CONFIG_IMPORT=file:/etc/catalog/config/application.yml,configtree:/etc/catalog/secrets/
```

Hai tiền tố có chức năng khác nhau:

- `file:` đọc nội dung YAML thành tập thuộc tính.
- `configtree:` đọc một cây tệp, trong đó tên tệp/đường dẫn tạo tên thuộc tính và nội dung tạo giá trị.

Với cây thư mục chính:

```text
application.yml:
  partner.base-url và partner.timeout

partner.api-token:
  giá trị partner.api-token
```

Giữ dấu `/` cuối đường dẫn configuration tree. Ví dụ không dùng `optional:` vì cấu hình bắt buộc phải được cấp. Xem [configuration trees trong Spring Boot](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.files.configtree).

Nếu đổi tên tệp Secret thành `token` rồi vẫn import cùng thư mục, thuộc tính nhận được sẽ là `token` thay vì `partner.api-token`. Có thể giữ tên tệp mang dấu chấm như manifest chính để tránh thêm một lớp ánh xạ.

Mount tệp không tự động gọi `DiscoveryClient`, tạo LoadBalancer hay kích hoạt Configuration Watcher. Nó cũng không yêu cầu starter Spring Cloud Kubernetes để Spring Boot đọc tệp cục bộ.

Nếu thuộc tính có giá trị khác dự kiến, rà soát nguồn ghi đè như biến môi trường, đối số dòng lệnh và import khác. Không in toàn bộ Spring Environment để tìm một token đang dùng.

## 8. Quyền đọc tệp và ranh giới mount

### 8.1. Đọc defaultMode theo quyền POSIX

Ví dụ chính dùng:

```text
ConfigMap: 0444 = đọc cho owner, group, others
Secret:    0440 = đọc cho owner và group
```

`defaultMode` nằm dưới nguồn volume, không nằm trong `volumeMount`. Có thể dùng `items[].mode` để điều chỉnh từng tệp.

Trong YAML, ví dụ dùng số octal; không đặt trong dấu nháy thành chuỗi. Nếu biểu diễn bằng JSON, dùng số thập phân tương ứng:

| Octal | Decimal | Quyền đọc |
| --- | --- | --- |
| `0400` | `256` | Owner |
| `0440` | `288` | Owner và group |
| `0444` | `292` | Owner, group và others |

Tài liệu [cấp Secret thành tệp](https://kubernetes.io/docs/tasks/inject-data-application/distribute-credentials-secure/#set-posix-permissions-for-secret-keys) giải thích `defaultMode` và khác biệt YAML/JSON.

Tiến trình UID `10001` cần đọc được tệp Secret. `fsGroup: 10001` ở cấp Pod giúp thiết lập quyền truy cập theo nhóm cho các volume hỗ trợ cơ chế đó. Hãy kiểm tra quyền thực tế trên loại volume và nền tảng đang chạy, nhất là khi chuyển sang CSI.

Không đổi `0440` thành `0777` để sửa lỗi `Permission denied`. Cần kiểm tra UID/GID, quyền đi qua thư mục và loại volume.

### 8.2. readOnly không phải cơ chế che giấu dữ liệu

`readOnly: true` thể hiện container không được sửa qua mount đó. Nó không ngăn chính tiến trình được cấp quyền đọc token, và không thay thế RBAC, kiểm soát exec hoặc quyền tạo workload.

Mount Secret cho đúng container cần dùng. Một sidecar không cần token thì không nên có mount tương ứng.

### 8.3. Mount cả thư mục có thể che nội dung sẵn có

Nếu mount volume vào `/app`, những tệp image vốn nằm dưới `/app` có thể bị che khuất ở đường nhìn của container. Đây là lý do ví dụ dùng thư mục riêng dưới `/etc/catalog`.

Không mount chồng các nguồn khác nhau vào cùng đường dẫn mà chưa xác định rõ kết quả. Nếu cần ghép dữ liệu, dùng một projected volume có cấu trúc đường dẫn rõ ràng.

Cơ chế volume và filesystem container được mô tả trong [tài liệu Volumes](https://kubernetes.io/docs/concepts/storage/volumes/).

## 9. Projected volume: gom nhiều nguồn vào một cây thư mục

Khi muốn một mount duy nhất cho cả ConfigMap và Secret, có thể dùng projected volume.

Đoạn dưới là **phương án thay thế** cho `app-config` và `partner-secret` trong manifest chính. Giữ `app-tmp`, nhưng thay hai mount dữ liệu bằng:

```yaml
volumeMounts:
  - name: runtime-settings
    mountPath: /etc/catalog
    readOnly: true
  - name: app-tmp
    mountPath: /tmp
```

Phần `volumes` tương ứng:

```yaml
volumes:
  - name: runtime-settings
    projected:
      defaultMode: 0440
      sources:
        - configMap:
            name: catalog-config-v1
            items:
              - key: application.yml
                path: config/application.yml
                mode: 0444
        - secret:
            name: catalog-partner-v1
            items:
              - key: partner.api-token
                path: secrets/partner.api-token
  - name: app-tmp
    emptyDir:
      sizeLimit: 128Mi
```

Đường dẫn cuối vẫn giống ví dụ hai volume nên `SPRING_CONFIG_IMPORT` không đổi.

Ba điểm dễ nhầm:

1. Trong `projected.sources[].secret`, trường tham chiếu là `name`, không phải `secretName`.
2. `defaultMode` ở cấp `projected`, không đặt riêng dưới mỗi nguồn.
3. Dùng các `path` khác nhau để hai nguồn không cùng ghi vào một vị trí.

Projected volume là cách trình bày nhiều nguồn trong một cây tệp. Nó không biến các lần sửa ConfigMap và Secret độc lập thành một giao dịch nghiệp vụ nguyên tử. Với cấu hình phải đi cùng nhau, dùng bộ tài nguyên phiên bản tương thích và rollout có kiểm soát.

Xem [Projected Volumes](https://kubernetes.io/docs/concepts/storage/projected-volumes/). Chọn hai volume riêng khi muốn thấy ranh giới dữ liệu rõ hơn; chọn projected volume khi cấu trúc mount thống nhất có ích cho ứng dụng.

## 10. Nếu dùng biến môi trường thay vì tệp

Với một vài khóa, `valueFrom` có thể đơn giản hơn. Ví dụ thay token volume bằng một biến môi trường:

```yaml
env:
  - name: SPRING_CONFIG_IMPORT
    value: "file:/etc/catalog/config/application.yml"
  - name: PARTNER_APITOKEN
    valueFrom:
      secretKeyRef:
        name: catalog-partner-v1
        key: partner.api-token
  - name: APP_RELEASE
    valueFrom:
      configMapKeyRef:
        name: catalog-config-v1
        key: release-label
```

Theo quy tắc binding biến môi trường của Spring Boot, `partner.api-token` tương ứng `PARTNER_APITOKEN`: dấu chấm đổi thành gạch dưới và dấu gạch ngang bị loại bỏ.

Đây là phương án thay thế: bỏ mount/volume `partner-secret` nếu không còn người dùng, đồng thời bỏ import configuration tree như đoạn trên. Không giữ cả hai nguồn token mà không quyết định nguồn nào có quyền ghi đè.

Điểm khác nhau:

| Cách cấp | Ứng dụng nhận gì? | Sau khi nguồn đổi |
| --- | --- | --- |
| `secretKeyRef`/`configMapKeyRef` | Giá trị biến môi trường khi tạo container | Cần container mới để nhận giá trị mới |
| Volume nguyên thư mục | Tệp | Có thể cập nhật theo cơ chế đồng bộ nếu nguồn không bất biến |
| Volume với `subPath` | Một tệp hoặc nhánh được mount riêng | Không nhận cập nhật tự động như mount nguyên thư mục |
| Đọc API từ ứng dụng | Phản hồi Kubernetes API | Theo logic đọc/cache/watch của client |

Biến môi trường không phải nơi an toàn tuyệt đối cho Secret. Tránh dump môi trường, đối số hoặc dữ liệu chẩn đoán có thể làm lộ token.

## 11. Cập nhật dữ liệu, subPath và việc Spring nạp lại

### 11.1. Đừng nhầm tệp đổi với ứng dụng đã dùng giá trị mới

Đối với nguồn cho phép sửa, dữ liệu volume được đồng bộ sau một khoảng trễ. Ứng dụng có thể cần mở lại tệp; một file descriptor giữ từ trước không nhất thiết đại diện cho dữ liệu mới.

Ngay cả khi tệp đã đổi, bean Spring được bind khi khởi động và client đã sao chép token vẫn có thể giữ giá trị cũ. Cần cơ chế refresh đã thiết kế hoặc tạo Pod mới.

Secret mount bằng `subPath` không nhận cập nhật tự động. Xem [Secret dưới dạng tệp](https://kubernetes.io/docs/concepts/configuration/secret/#using-secrets-as-files-from-a-pod).

Ví dụ `subPath` thường gặp:

```yaml
volumeMounts:
  - name: app-config
    mountPath: /etc/catalog/single-application.yml
    subPath: application.yml
    readOnly: true
```

Đoạn này chỉ minh họa một tệp mount riêng, không bổ sung vào manifest chính. Nếu dùng, phải đổi đường import và chọn cơ chế thay thế Pod khi cấu hình đổi.

### 11.2. Ví dụ chính dùng tài nguyên bất biến

Cả ConfigMap và Secret v1 đều có `immutable: true`. Vì thế không sửa trực tiếp dữ liệu v1; tạo tài nguyên tên mới:

```text
catalog-config-v2
catalog-partner-v2
```

Sau đó:

1. Tạo tài nguyên mới với cùng các khóa mà ứng dụng mong đợi.
2. Đổi tên tham chiếu trong `volumes` của Pod template.
3. Đổi annotation phiên bản để thuận tiện theo dõi.
4. Áp dụng Deployment và đợi rollout.
5. Kiểm tra sức khỏe cùng hành vi tích hợp, giữ tài nguyên cũ theo cửa sổ rollback.

Thay tham chiếu volume trong Pod template tạo rollout. Annotation ở ví dụ chỉ là dấu ghi phiên bản, không tự tính checksum hay theo dõi thay đổi nguồn.

Nếu chỉ đổi giá trị của tài nguyên cùng tên trong một thiết kế không bất biến, Deployment không tự rollout chỉ vì dữ liệu đó đổi. Cần refresh hoặc chủ động thay Pod theo quy trình.

### 11.3. Khi nào thêm Configuration Watcher?

Configuration Watcher có thể gửi tín hiệu refresh cho ứng dụng Spring Cloud. Nó cần cấu hình, quyền theo dõi và đường refresh phù hợp; nó không bảo đảm mọi thuộc tính/client đều cập nhật được.

Xem [Configuration Watcher](https://docs.spring.io/spring-cloud-kubernetes/reference/spring-cloud-kubernetes-configuration-watcher.html). Với bài này, phiên bản hóa và rollout là cách kiểm chứng đơn giản; chỉ thêm Watcher khi có yêu cầu cập nhật và đã xác minh hành vi refresh của ứng dụng.

## 12. Volume mount và RBAC là hai đường truy cập khác nhau

Trong manifest chính, `catalog-runtime` không có Role/RoleBinding và không được mount ServiceAccount token. Ứng dụng đọc tệp mà kubelet đã chuẩn bị, không gọi API để lấy Secret.

Vì thế không cấp `get/list/watch secrets` cho ứng dụng chỉ vì nó có Secret volume.

Nếu chọn Spring Cloud Kubernetes Secrets PropertySource qua API, phải xem xét lại xác thực, namespace và RBAC. Tài liệu khuyến nghị volume và giới hạn quyền khi cần đọc Secret qua API. Xem [Secrets PropertySource](https://docs.spring.io/spring-cloud-kubernetes/reference/property-source-config/secrets-propertysource.html).

Quyền vận hành vẫn quan trọng: tài khoản có khả năng tạo Pod hoặc thực thi lệnh trong container có thể tiếp cận dữ liệu được cấp cho workload đó. Cần đánh giá cả quyền tạo workload lẫn quyền đọc Secret, không chỉ nhìn Role của tiến trình Java. Xem [thực hành bảo vệ Secret](https://kubernetes.io/docs/concepts/security/secrets-good-practices/).

DiscoveryClient và Spring Cloud LoadBalancer có thể giải quyết nhu cầu khám phá/chọn instance của ứng dụng. Những nhu cầu đó không thay đổi cú pháp mount, nhưng có thể làm ứng dụng cần ServiceAccount token và quyền API khác. Không sao chép manifest volume tối thiểu sang ứng dụng có các client API rồi bỏ qua phần phân quyền.

## 13. Áp dụng và kiểm tra mà không in token

### 13.1. Kiểm tra cấu trúc và tạo tài nguyên theo thứ tự rõ ràng

Các lệnh dưới đây giả định bạn đã lưu những manifest lab và đã thay image placeholder. Chúng là thao tác thực hành cho người học:

```bash
kubectl apply -f namespace.yml

kubectl apply --dry-run=server -f catalog-config.yml
kubectl apply --dry-run=server -f catalog-secret-lab.yml
kubectl apply --dry-run=server -f catalog-deployment.yml

kubectl apply -f catalog-config.yml
kubectl apply -f catalog-secret-lab.yml
kubectl apply -f catalog-deployment.yml

kubectl -n manifest-lab rollout status deployment/catalog-service --timeout=180s
```

Namespace được tạo trước để kiểm tra phía server đối với các tài nguyên có namespace. Không thêm `-o yaml` cho Secret thật trong pipeline ghi log.

Server dry-run kiểm tra schema và admission của yêu cầu; nó không chứng minh image kéo được, khóa tham chiếu đã đủ, tiến trình đọc được file hoặc Spring parse được YAML bên trong ConfigMap. Những điều đó cần kiểm tra khi Pod chạy.

### 13.2. Kiểm tra danh tính nguồn và trạng thái

```bash
kubectl -n manifest-lab get configmap catalog-config-v1 \
  -o custom-columns=NAME:.metadata.name,IMMUTABLE:.immutable

kubectl -n manifest-lab get secret catalog-partner-v1 \
  -o custom-columns=NAME:.metadata.name,TYPE:.type,IMMUTABLE:.immutable

kubectl -n manifest-lab get deployment catalog-service \
  -o jsonpath='{.spec.template.spec.volumes[?(@.name=="partner-secret")].secret.secretName}{"\n"}'

kubectl -n manifest-lab get pods -l app=catalog-service
```

Các lệnh này không xuất giá trị token. Đừng dùng `kubectl get secret -o yaml`, giải mã Base64 rồi chép lên ticket hoặc chat để chứng minh Secret tồn tại.

### 13.3. Kiểm tra khả năng đọc mà không đọc ra màn hình

Nếu image lab có lệnh `test`, có thể kiểm tra với đúng user của container:

```bash
kubectl -n manifest-lab get pods -l app=catalog-service

POD=catalog-service-REPLACE_WITH_POD_NAME

kubectl -n manifest-lab exec "$POD" -c app -- \
  test -r /etc/catalog/config/application.yml

kubectl -n manifest-lab exec "$POD" -c app -- \
  test -r /etc/catalog/secrets/partner.api-token

kubectl -n manifest-lab exec "$POD" -c app -- \
  test -s /etc/catalog/secrets/partner.api-token
```

Exit code thành công xác nhận tệp đọc được hoặc không rỗng theo lệnh tương ứng; không xác nhận token hợp lệ tại hệ thống đối tác.

Image tối giản có thể không có `test` hoặc shell. Lỗi không tìm thấy executable không chứng minh tệp cấu hình bị thiếu. Trong trường hợp đó, dùng kiểm tra đầu vào của chính ứng dụng hoặc công cụ chẩn đoán được nền tảng cho phép.

Health endpoint chỉ chứng minh trạng thái sức khỏe được ứng dụng khai báo. Phép thử tích hợp có kiểm soát mới xác nhận endpoint, token và mạng hoạt động cùng nhau.

## 14. Chẩn đoán theo tầng lỗi

| Triệu chứng | Vị trí cần kiểm tra | Cách sửa |
| --- | --- | --- |
| API báo trường không hợp lệ | Cấp của `volumes`/`volumeMounts`, tên trường nguồn | Đối chiếu schema Pod template |
| VolumeMount không tìm thấy volume | `volumeMounts[].name` và `volumes[].name` | Sửa tên nội bộ cho khớp |
| Pod chờ mount, chưa có log Spring | Tên nguồn, namespace, `items[].key` | Tạo đúng nguồn/khóa trước khi xử lý ứng dụng |
| Tệp có tên khác dự kiến | `items[].path`, `mountPath` | Tính lại đường tuyệt đối và import |
| `Permission denied` | UID/GID, mode, quyền thư mục, loại volume | Sửa quyền hẹp và xác minh user thực tế |
| Spring không parse được cấu hình | Nội dung chuỗi `application.yml` | Sửa YAML hoặc giá trị thuộc tính bên trong |
| Thiếu `partner.api-token` | Tên tệp configuration tree và import | Dùng đúng khóa/đường dẫn, không thêm token mặc định |
| Sửa dữ liệu v1 bị từ chối | `immutable: true` | Tạo phiên bản mới và đổi tham chiếu |
| Tệp đổi nhưng bean giữ giá trị cũ | Cơ chế nạp lại Spring/client | Rollout hoặc refresh đã được kiểm chứng |
| Không thấy cập nhật sau mount một tệp | Có dùng `subPath` không | Thay Pod hoặc chuyển sang mount thư mục |
| Bật API loader rồi gặp 403 | ServiceAccount, RBAC và token | Chọn rõ đường volume/API và cấp quyền tối thiểu |

Khi cần xem event:

```bash
kubectl -n manifest-lab get events \
  --field-selector involvedObject.name="$POD" \
  --sort-by=.metadata.creationTimestamp
```

Không sửa một lỗi ở tầng volume bằng cách tắt validation của Spring, và không sửa lỗi cú pháp YAML bằng cách cấp thêm quyền Secret.

## 15. Bài thực hành củng cố

Trong namespace lab và chỉ với dữ liệu giả:

1. Áp dụng bộ ConfigMap, Secret và Deployment chính; ghi lại hai đường dẫn tệp cuối.
2. Giải thích vì sao `release-label` có trong ConfigMap nhưng không có trong thư mục mount.
3. Đổi `items[].path` của ConfigMap sang `runtime/settings.yml` và điều chỉnh cả import; mô tả đường dẫn mới trước khi áp dụng.
4. Thử một tên khóa không tồn tại trong `items`; quan sát Pod events và xác định lỗi xảy ra trước Spring.
5. Khôi phục khóa đúng, rồi kiểm tra tiến trình không root đọc được Secret mà không in token.
6. Thay hai volume bằng projected volume; giữ nguyên đường dẫn và chứng minh cấu hình Spring không cần đổi.
7. Thử phương án token qua `secretKeyRef` trong một lượt riêng; loại nguồn token cũ để tránh ghi đè khó hiểu.
8. Tạo cấu hình v2 và đổi tham chiếu trong Pod template; kiểm tra rollout mà không thay image digest.
9. Giải thích vì sao chỉnh nội dung một tệp đã mount chưa đủ để kết luận bean Spring đã đổi.

Bài làm đạt yêu cầu khi bạn lần được mọi tham chiếu từ tài nguyên đến tệp và thuộc tính Spring, chọn đúng quyền truy cập, và xác định đúng tầng cần sửa khi cấu hình không tới được ứng dụng.
