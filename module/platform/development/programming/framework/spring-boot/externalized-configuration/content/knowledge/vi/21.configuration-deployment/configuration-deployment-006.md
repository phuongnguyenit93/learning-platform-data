# Nạp ConfigMap hoặc Secret dưới dạng biến môi trường hay volume trong Spring Boot trên Kubernetes

## 1. Bài toán triển khai: cùng một JAR, nhiều môi trường cấu hình

Một ứng dụng Spring Boot thường được đóng gói thành một JAR hoặc container image duy nhất, rồi triển khai lên môi trường phát triển, kiểm thử và production. Mã ứng dụng nên giữ nguyên, còn cấu hình cần thay đổi tùy môi trường:

- Số lần thử lại và timeout của HTTP client.
- Tên topic, giới hạn hàng đợi hoặc danh sách dịch vụ phụ trợ.
- Chế độ bật/tắt chức năng.
- Địa chỉ máy chủ và thông tin kết nối.
- Token, mật khẩu, client secret hoặc khóa dùng để xác thực.

Khi chạy trên Kubernetes, hai đối tượng nền tảng thường dùng là:

- **ConfigMap**: giữ cấu hình **không nhạy cảm**, dưới dạng các cặp key-value hoặc dữ liệu tệp.
- **Secret**: giữ dữ liệu cần kiểm soát truy cập, như credential, token, khóa, certificate; không tự đồng nghĩa với giải pháp bảo mật toàn diện.

Kubernetes có thể cấp giá trị của ConfigMap/Secret cho container theo hai nhóm cách:

1. **Biến môi trường** qua `env.valueFrom` hoặc `envFrom`.
2. **Tệp trong volume** qua `volumes` và `volumeMounts`.

Spring Boot nhận dữ liệu từ biến môi trường thông qua `Environment`. Với tệp mount, Spring Boot có thể nhận dữ liệu bằng `spring.config.import=file:...` cho một tệp cấu hình hoàn chỉnh, hoặc `spring.config.import=configtree:...` khi mỗi tệp trong thư mục biểu diễn một thuộc tính.

**Mục tiêu:** hiểu đầy đủ đường đi từ ConfigMap/Secret → Pod/container → Spring Boot Environment → `@ConfigurationProperties` hoặc auto-configuration; biết lựa chọn cách cấp dữ liệu phù hợp, kiểm tra thiếu dữ liệu, tránh tiết lộ secret và xử lý cập nhật cấu hình.

## 2. Bản đồ tổng quan

~~~text
Kubernetes API
  |
  +-- ConfigMap: app-runtime
  |      APP_JOBS_BATCHSIZE=200
  |      APP_JOBS_TIMEOUT=15s
  |
  +-- Secret: app-credentials
         PARTNER_AUTH_CLIENTSECRET=<giá trị bí mật>
  |
  v
Pod specification / Deployment
  |
  +------------------------+-----------------------------+
  |                                                      |
  v                                                      v
env / envFrom                                        volumes / volumeMounts
Biến môi trường                                      File trong container
  |                                                   |
  |                                                   +-- configtree:/etc/app/config/
  |                                                   +-- configtree:/etc/app/secrets/
  |                                                   +-- file:/etc/app/application.yaml
  |                                                      |
  +-------------------------+----------------------------+
                            |
                            v
                    Spring Environment
                      PropertySources
                            |
                            v
                @ConfigurationProperties
                 hoặc auto-configuration
                            |
                            v
                    Service / Client
~~~

Hai cách cấp dữ liệu đều thực hiện **externalized configuration**: ứng dụng không cần chứa giá trị riêng cho từng môi trường trong image. Tuy nhiên, chúng khác nhau về tên key, quyền đọc, tính năng cập nhật và cách Spring Boot nạp giá trị.

## 3. Phân biệt ConfigMap và Secret

| Vấn đề | ConfigMap | Secret |
| --- | --- | --- |
| Mục đích | Cấu hình không nhạy cảm | Dữ liệu bí mật/credential |
| Ví dụ | `app.jobs.batch-size`, timeout, feature flag | API token, password, private key |
| Dữ liệu văn bản | `data` | `stringData` hoặc `data` |
| Dữ liệu byte | `binaryData` | `data` biểu diễn dưới dạng base64 |
| Cấp qua env | `configMapKeyRef`, `configMapRef` | `secretKeyRef`, `secretRef` |
| Cấp qua volume | `volumes[].configMap` | `volumes[].secret` |
| File mount | Key thành file name | Key thành file name |
| Cập nhật file mount | Thường eventual update | Thường eventual update |
| Environment của process khi object đổi | Không tự cập nhật | Không tự cập nhật |
| Yêu cầu bảo vệ | Vẫn cần RBAC và kiểm soát truy cập | Cần RBAC chặt, encryption at rest phù hợp, audit, rotation |

**Không đưa credential thật vào ConfigMap** chỉ vì nó dễ tạo. Cũng không đưa mọi cấu hình thông thường vào Secret: điều này gây phức tạp vận hành và không thay thế phân loại dữ liệu.

### Secret.data là base64, không phải mã hóa bảo mật

Trong manifest Secret, trường `data` chứa biểu diễn base64, không phải ciphertext an toàn. Người có quyền đọc Secret object có thể giải mã. Vì vậy:

- Hạn chế quyền đọc Secret bằng Kubernetes RBAC.
- Xem xét mã hóa dữ liệu Secret ở nơi lưu trữ của control plane.
- Hạn chế quyền tạo workload có thể mount Secret.
- Không commit Secret YAML chứa giá trị production, kể cả khi ở dạng base64.
- Dùng hệ thống quản lý bí mật hoặc quy trình cấp riêng cho từng môi trường.

`stringData` có thể tiện trong ví dụ kiểm thử nhưng không nên coi là hình thức che giấu secret.

## 4. ConfigMap có thể có key như thế nào?

Ví dụ ConfigMap không chứa dữ liệu nhạy cảm:

~~~yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: app-runtime
data:
  APP_JOBS_BATCHSIZE: "200"
  APP_JOBS_TIMEOUT: "15s"
  APP_FEATURE_EXPORT_ENABLED: "false"
~~~

Tất cả giá trị của `data` trong manifest này là **String**. Dấu nháy quanh `"200"` và `"false"` giúp tránh YAML biểu diễn chúng thành number hoặc Boolean không phù hợp với schema Kubernetes.

Tên key được chọn theo cú pháp biến môi trường Spring Boot để dùng trực tiếp cùng `envFrom` ở ví dụ sau. Nếu dùng volume + `configtree:`, có thể chọn tên **canonical** như `app.jobs.batch-size` thay vì tên chữ hoa.

### Tách tên theo cách cấp dữ liệu

Khi dùng **environment**, nên dùng tên:

~~~text
APP_JOBS_BATCHSIZE
APP_JOBS_TIMEOUT
APP_FEATURE_EXPORT_ENABLED
~~~

Khi dùng **configuration tree**, nên dùng tên file:

~~~text
app.jobs.batch-size
app.jobs.timeout
app.feature.export.enabled
~~~

Không có yêu cầu mọi ConfigMap phải dùng cùng hệ thống tên key cho cả hai cách. Nhưng nếu chuyển từ env sang volume thì **cần kiểm tra và có thể đổi tên key/file** để Springer Boot nhận đúng property.

## 5. Cách 1 — cấp ConfigMap bằng env.valueFrom.configMapKeyRef

`env.valueFrom.configMapKeyRef` cho phép chọn **một key** từ ConfigMap và đặt nó vào một biến môi trường với tên bạn quyết định.

Ví dụ ConfigMap:

~~~yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: order-settings
data:
  batchSize: "250"
  requestTimeout: "20s"
~~~

Deployment fragment:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: order-service
spec:
  replicas: 1
  selector:
    matchLabels:
      app: order-service
  template:
    metadata:
      labels:
        app: order-service
    spec:
      containers:
        - name: app
          image: example/order-service:1.0.0
          env:
            - name: APP_JOBS_BATCHSIZE
              valueFrom:
                configMapKeyRef:
                  name: order-settings
                  key: batchSize
            - name: APP_JOBS_TIMEOUT
              valueFrom:
                configMapKeyRef:
                  name: order-settings
                  key: requestTimeout
~~~

Kết quả trong environment của JVM:

~~~text
APP_JOBS_BATCHSIZE=250
APP_JOBS_TIMEOUT=20s
~~~

Spring Boot có thể bind thành:

~~~text
app.jobs.batch-size = 250
app.jobs.timeout = 20s
~~~

Ví dụ Java:

~~~java
package com.example.demo.config;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.jobs")
public record JobsProperties(
        int batchSize,
        Duration timeout) {
}
~~~

Khi `JobsProperties` đã được đăng ký qua `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties(JobsProperties.class)`, các giá trị tương ứng sẽ được Binder chuyển thành `int` và `Duration`.

### Ưu điểm của chọn key

- Container chỉ nhận những thuộc tính thực sự cần.
- Tên key của ConfigMap có thể khác tên biến môi trường.
- Có thể ghép ConfigMap được chia sẻ với nhiều ứng dụng mà không nhập mọi key.
- Dễ nhìn vào Deployment để biết từng biến lấy từ đâu.

### Điểm cần lưu ý

`name` dưới `configMapKeyRef` là **tên ConfigMap**. `key` là **key bên trong ConfigMap**; `env.name` là **tên biến trong container**.

Đừng nhầm:

~~~text
ConfigMap name: order-settings
ConfigMap key:  batchSize
Environment:    APP_JOBS_BATCHSIZE
Spring property: app.jobs.batch-size
Java member:    batchSize
~~~

Đây là bốn tầng tên có ý nghĩa khác nhau.

## 6. Cách 2 — cấp toàn bộ ConfigMap bằng envFrom.configMapRef

Nếu ConfigMap đã dùng những tên key hợp lệ cho biến môi trường, `envFrom` cho phép nhập **nhiều key cùng lúc**.

ConfigMap:

~~~yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: order-runtime-env
data:
  APP_JOBS_BATCHSIZE: "200"
  APP_JOBS_TIMEOUT: "15s"
  APP_FEATURE_EXPORT_ENABLED: "false"
~~~

Deployment:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: order-service
spec:
  replicas: 1
  selector:
    matchLabels:
      app: order-service
  template:
    metadata:
      labels:
        app: order-service
    spec:
      containers:
        - name: app
          image: example/order-service:1.0.0
          envFrom:
            - configMapRef:
                name: order-runtime-env
~~~

Container nhận các biến có cùng tên với key trong ConfigMap.

**`envFrom` không tự chuyển key `app.jobs.batch-size` thành `APP_JOBS_BATCHSIZE`.** Nó cung cấp biến dựa trên tên key, còn Spring Boot thực hiện việc nhận diện tên environment theo các quy tắc của nó.

Vì vậy, khi muốn `envFrom`, nên thiết kế ConfigMap với các key dạng environment phù hợp.

### Khi nào dùng envFrom?

Phù hợp khi một ConfigMap được thiết kế **dành riêng cho một workload**, chứa các biến đều cần thiết và tên biến đã chuẩn hóa.

Không phù hợp bằng việc chọn từng key khi:

- ConfigMap chứa nhiều mục không liên quan.
- Các team dùng chung ConfigMap.
- Bạn muốn giới hạn những giá trị được đưa vào process.
- Cần gán tên biến khác tên key.

### Key không hợp lệ để thành tên biến

Kubernetes có các quy tắc đặt tên biến môi trường và có thể bỏ qua những key từ `envFrom` không chuyển thành tên biến hợp lệ; Pod vẫn có thể chạy, đồng thời có event cảnh báo tương ứng.

Đừng suy luận rằng vì ConfigMap tồn tại nên **tất cả key đều đã vào môi trường**. Trong quá trình chẩn đoán, hãy kiểm tra tên biến **mà không in giá trị nhạy cảm**.

## 7. Tên biến môi trường và relaxed binding của Spring Boot

Trong binding `@ConfigurationProperties`, tên cấu hình canonical:

~~~text
app.jobs.batch-size
~~~

được chuyển sang tên biến môi trường bằng quy tắc:

1. `.` → `_`.
2. Bỏ dấu gạch ngang `-`.
3. Viết hoa.

Kết quả:

~~~text
APP_JOBS_BATCHSIZE
~~~

Bảng ví dụ:

| Tên canonical | Biến môi trường tương ứng |
| --- | --- |
| `app.jobs.batch-size` | `APP_JOBS_BATCHSIZE` |
| `app.jobs.timeout` | `APP_JOBS_TIMEOUT` |
| `spring.datasource.password` | `SPRING_DATASOURCE_PASSWORD` |
| `partner.auth.client-secret` | `PARTNER_AUTH_CLIENTSECRET` |
| `app.feature.export.enabled` | `APP_FEATURE_EXPORT_ENABLED` |

Hãy cẩn thận khi đổi gạch ngang thành gạch dưới. Đối với `batch-size`, dạng canonical là `BATCHSIZE` trong biến môi trường, không mặc định là `BATCH_SIZE` theo quy tắc tài liệu hóa.

Trong trường hợp ConfigMap có key nguyên văn `app.jobs.batch-size`, cách dùng `configMapKeyRef` là một lối đi rõ ràng:

~~~yaml
env:
  - name: APP_JOBS_BATCHSIZE
    valueFrom:
      configMapKeyRef:
        name: order-settings
        key: app.jobs.batch-size
~~~

Kubernetes tìm đúng key, còn bạn chủ động đặt tên environment thuận tiện cho Spring Boot.

## 8. Secret dưới dạng environment với secretKeyRef

Ví dụ ứng dụng cần token cho dịch vụ đối tác:

~~~java
import jakarta.validation.constraints.NotBlank;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "partner.auth")
public record PartnerCredentials(
        @NotBlank String clientId,
        @NotBlank String clientSecret) {
}
~~~

Giả sử Secret Kubernetes tên `partner-credentials` đã được nền tảng cấp an toàn và chứa key `client-secret`.

Deployment fragment:

~~~yaml
env:
  - name: PARTNER_AUTH_CLIENTID
    value: "DEMO_CLIENT_ID"
  - name: PARTNER_AUTH_CLIENTSECRET
    valueFrom:
      secretKeyRef:
        name: partner-credentials
        key: client-secret
~~~

Ứng dụng nhận:

~~~text
partner.auth.client-id
partner.auth.client-secret
~~~

Qua Spring Boot relaxed binding.

### Không để giá trị thật trong Deployment

Tránh:

~~~yaml
env:
  - name: PARTNER_AUTH_CLIENTSECRET
    value: "REAL_PRODUCTION_TOKEN"
~~~

Dù Kubernetes chấp nhận cấu hình này, giá trị literal có thể nằm trong Git, Pod spec và công cụ quản lý triển khai. Với secret, dùng `valueFrom.secretKeyRef` hoặc volume.

### Dùng secretRef với envFrom

Nếu Secret đã dùng tên key hợp lệ cho environment:

~~~text
PARTNER_AUTH_CLIENTSECRET
PAYMENT_GATEWAY_PASSWORD
~~~

có thể viết:

~~~yaml
envFrom:
  - secretRef:
      name: partner-env
~~~

Mọi key hợp lệ được cấp vào container. Cách này ngắn nhưng tăng phạm vi giá trị mà container nhận. Với secret chia sẻ hoặc chỉ cần vài key, thường nên ưu tiên `secretKeyRef` tường minh.

### Tránh ghi Secret data trong tài liệu

Không cần đặt một chuỗi base64 của token giả mà dễ bị người đọc copy nhầm thành “mẫu production”. Các manifest trong README tập trung vào **tham chiếu tới Secret đã cấp**, không phải dữ liệu thật. Trong môi trường thực, Secret nên được tạo từ một quy trình quản lý bí mật được kiểm soát.

## 9. env, envFrom, configMapKeyRef, secretKeyRef: nên chọn gì?

| Mục đích | Cú pháp Kubernetes | Hành vi |
| --- | --- | --- |
| Một key từ ConfigMap | `env[].valueFrom.configMapKeyRef` | Chọn key, tự đặt tên env. |
| Tất cả key hợp lệ từ ConfigMap | `envFrom[].configMapRef` | Nhập nhiều env. |
| Một key từ Secret | `env[].valueFrom.secretKeyRef` | Chọn secret key, tự đặt tên env. |
| Tất cả key hợp lệ từ Secret | `envFrom[].secretRef` | Nhập nhiều secret env. |
| Giá trị literal không nhạy cảm | `env[].value` | Gán trực tiếp cho một biến. |

Có thể phối hợp các kiểu trên trong cùng container, nhưng cần tránh tên môi trường trùng lặp. Theo cơ chế Kubernetes, `env` được ưu tiên hơn các biến từ `envFrom` nếu cùng tên; với nhiều mục `envFrom`, thứ tự trong danh sách có thể quyết định giá trị được dùng khi trùng tên. Không nên dựa vào sự trùng tên như một cơ chế override khó quan sát; hãy chọn một nguồn rõ ràng cho mỗi thuộc tính.

### optional: true ở Kubernetes không đồng nghĩa với bắt buộc của Spring

`configMapKeyRef`, `secretKeyRef`, `configMapRef` và `secretRef` có khả năng khai báo `optional` theo API Kubernetes. Khi một tham chiếu là bắt buộc nhưng resource/key thiếu, container có thể không được tạo/start bình thường. Nếu khai báo optional, nền tảng cho phép một số trường hợp thiếu nguồn.

Điều này **không thay thế** validation cấu hình của Spring Boot. Một app có thể khởi động được với một tham chiếu optional nhưng sau đó thiếu credential bắt buộc; cần kiểm tra tại tầng ứng dụng.

## 10. Hạn chế quan trọng: environment không tự cập nhật khi nguồn đổi

Giả sử Pod đang chạy với:

~~~text
APP_JOBS_BATCHSIZE=200
~~~

Người vận hành sửa ConfigMap thành:

~~~text
APP_JOBS_BATCHSIZE=400
~~~

Kubernetes **không tự thay đổi biến môi trường của process đang chạy** chỉ vì ConfigMap được cập nhật. Điều tương tự áp dụng cho Secret đã được cấp bằng `secretKeyRef`.

Trong trường hợp này:

- ConfigMap/Secret object đã đổi.
- Environment của Pod hiện tại có thể vẫn giữ giá trị cũ.
- Spring Boot bean `@ConfigurationProperties` đã tạo có thể vẫn giữ cấu hình cũ.
- Một **Pod mới/recreated** nhận dữ liệu mới khi được tạo.

Một cách thường dùng với Deployment:

~~~bash
kubectl rollout restart deployment/order-service -n demo
kubectl rollout status deployment/order-service -n demo
~~~

Đây là lệnh minh họa; cần thay tên workload/namespace cho môi trường thật và có kế hoạch rollout phù hợp. Không được tự ý restart production nếu chưa tính đến availability, connection draining và sự tương thích giữa credential cũ/mới.

### Vì sao không chỉ sửa Secret?

Với environment variable, dữ liệu được cung cấp lúc container khởi tạo. Không có cơ chế chuẩn để Kubernetes sửa trực tiếp một biến môi trường trong một tiến trình JVM đã chạy.

Do đó, nếu yêu cầu tự cập nhật secret không downtime, cần thiết kế cơ chế chuyên biệt, không thể đạt được chỉ bằng `envFrom`.

## 11. Cách 3 — mount ConfigMap thành volume

Một ConfigMap có thể được trình bày thành **các file trong container**.

ConfigMap dành cho volume:

~~~yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: order-config-files
data:
  app.jobs.batch-size: "200"
  app.jobs.timeout: "15s"
  app.feature.export.enabled: "false"
~~~

Deployment fragment:

~~~yaml
spec:
  template:
    spec:
      containers:
        - name: app
          image: example/order-service:1.0.0
          volumeMounts:
            - name: app-config
              mountPath: /etc/app/config
              readOnly: true
      volumes:
        - name: app-config
          configMap:
            name: order-config-files
~~~

Trong container, các key trở thành tên file:

~~~text
/etc/app/config/
├── app.jobs.batch-size
├── app.jobs.timeout
└── app.feature.export.enabled
~~~

Nội dung của mỗi file là giá trị tương ứng.

**Lưu ý:** đoạn `spec.template.spec` ở trên chỉ minh họa phần của một Deployment hoàn chỉnh; không phải manifest độc lập.

### Spring Boot chưa tự đọc file nếu chưa cấu hình đường nạp

Việc mount thành công chỉ chứng minh file có mặt. Để Spring Boot đưa các file này vào `Environment` dưới dạng key-value, có thể khai báo:

~~~yaml
spring:
  config:
    import: "configtree:/etc/app/config/"
~~~

Spring Boot sử dụng tên file làm tên property:

~~~text
app.jobs.batch-size = 200
app.jobs.timeout = 15s
app.feature.export.enabled = false
~~~

Sau đó record `JobsProperties` ở phần trước có thể bind giá trị tương tự cách dùng environment.

## 12. Configuration tree: cơ chế chủ chốt khi mỗi file là một property

`spring.config.import=configtree:...` là cơ chế Config Data của Spring Boot.

Nó dành cho cấu trúc:

~~~text
directory/
├── property.one
├── property.two
└── property.three
~~~

Mỗi file đóng vai trò một giá trị:

~~~text
tên file / đường dẫn tương đối → property name
nội dung file                    → property value
~~~

Ví dụ:

~~~text
/etc/app/config/
└── messaging/
    ├── host
    └── timeout
~~~

Import:

~~~properties
spring.config.import=configtree:/etc/app/config/
~~~

Có thể cung cấp:

~~~text
messaging.host
messaging.timeout
~~~

Nếu import root sâu hơn:

~~~properties
spring.config.import=configtree:/etc/app/config/messaging/
~~~

thì các key tương ứng là:

~~~text
host
timeout
~~~

**Root import thay đổi tên property.** Đây là lỗi thường gặp khi Kubernetes mount đúng file nhưng Spring Boot không bind được: ứng dụng đang tìm `messaging.host` trong khi configuration tree cung cấp `host`, hoặc ngược lại.

### Tên file có dấu chấm

Spring Boot hỗ trợ tên file dạng:

~~~text
/etc/app/config/app.jobs.batch-size
~~~

và ánh xạ thành:

~~~text
app.jobs.batch-size
~~~

Vì vậy, cách đặt tên file khớp hoàn toàn với tên property canonical thường đơn giản, dễ kiểm tra và không cần alias.

## 13. Cách 4 — mount Secret thành volume

Secret cũng có thể được cung cấp thành file.

Giả sử Secret Kubernetes tên `partner-credentials` có key `client-secret`. Một volume mount có thể đổi tên file thông qua `items`:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: order-service
spec:
  replicas: 1
  selector:
    matchLabels:
      app: order-service
  template:
    metadata:
      labels:
        app: order-service
    spec:
      containers:
        - name: app
          image: example/order-service:1.0.0
          volumeMounts:
            - name: app-secrets
              mountPath: /etc/app/secrets
              readOnly: true
      volumes:
        - name: app-secrets
          secret:
            secretName: partner-credentials
            items:
              - key: client-secret
                path: partner.auth.client-secret
~~~

File trong container:

~~~text
/etc/app/secrets/partner.auth.client-secret
~~~

Với:

~~~yaml
spring:
  config:
    import: "configtree:/etc/app/secrets/"
~~~

Spring Boot có property:

~~~text
partner.auth.client-secret
~~~

và binder có thể liên kết vào `PartnerCredentials.clientSecret`.

### items có tác dụng gì?

Nếu bỏ `items`, Kubernetes thường mount mỗi key được chọn của Secret thành file có tên giống key. Với `items`, bạn có thể chọn key cụ thể và đặt đường dẫn file phù hợp cho ứng dụng.

Trong ví dụ:

~~~text
Secret object: partner-credentials
Secret key:    client-secret
Mounted file:  partner.auth.client-secret
Spring key:    partner.auth.client-secret
Java member:   clientSecret
~~~

Bốn tên có thể khác nhau. Chúng được kết nối bằng `items.key`, `items.path` và `configtree:`.

### Quyền file

Với secret volume có thể đặt `defaultMode` hoặc mode trên item:

~~~yaml
volumes:
  - name: app-secrets
    secret:
      secretName: partner-credentials
      defaultMode: 0440
      items:
        - key: client-secret
          path: partner.auth.client-secret
~~~

Quyền file cần tương thích với user/group đang chạy JVM. Mức `0440` cho phép owner/group đọc trên môi trường POSIX, nhưng container chạy non-root có thể vẫn không đọc được nếu owner/group không phù hợp.

Không đặt `0777` chỉ để vượt lỗi quyền. Cần cấu hình `runAsUser`, `runAsGroup`, `fsGroup` hoặc chính sách quyền theo runtime thật, với nguyên tắc ít quyền nhất.

## 14. Một Deployment đầy đủ: ConfigMap volume + Secret volume + Spring Boot

Trong ví dụ sau, ConfigMap/Secret đã được tạo trước bởi cơ chế triển khai tương ứng.

ConfigMap:

~~~yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: order-runtime-files
data:
  app.jobs.batch-size: "250"
  app.jobs.timeout: "20s"
  app.feature.export.enabled: "false"
~~~

Secret đã có tên:

~~~text
partner-credentials
  key: client-secret
~~~

Deployment:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: order-service
spec:
  replicas: 2
  selector:
    matchLabels:
      app: order-service
  template:
    metadata:
      labels:
        app: order-service
    spec:
      containers:
        - name: app
          image: example/order-service:1.0.0
          ports:
            - containerPort: 8080
          env:
            - name: PARTNER_AUTH_CLIENTID
              value: "DEMO_CLIENT_ID"
          volumeMounts:
            - name: runtime-config
              mountPath: /etc/app/config
              readOnly: true
            - name: credentials
              mountPath: /etc/app/secrets
              readOnly: true
      volumes:
        - name: runtime-config
          configMap:
            name: order-runtime-files
        - name: credentials
          secret:
            secretName: partner-credentials
            items:
              - key: client-secret
                path: partner.auth.client-secret
~~~

Trong JAR, `application.yaml`:

~~~yaml
spring:
  application:
    name: order-service
  config:
    import:
      - "configtree:/etc/app/config/"
      - "configtree:/etc/app/secrets/"
~~~

Spring Boot nạp hai tree. Mỗi key được ánh xạ vào `Environment` như một property bình thường.

Java:

~~~java
package com.example.demo.config;

import java.time.Duration;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.jobs")
public record JobsProperties(
        @Min(1) int batchSize,
        @NotNull Duration timeout) {
}

@Validated
@ConfigurationProperties(prefix = "partner.auth")
public record PartnerCredentials(
        @NotBlank String clientId,
        @NotBlank String clientSecret) {
}
~~~

Đăng ký:

~~~java
@SpringBootApplication
@ConfigurationPropertiesScan
public class OrderApplication {
    public static void main(String[] args) {
        SpringApplication.run(OrderApplication.class, args);
    }
}
~~~

Khi cần, service inject bean:

~~~java
@Service
public class OrderService {

    private final JobsProperties jobs;
    private final PartnerCredentials credentials;

    public OrderService(
            JobsProperties jobs,
            PartnerCredentials credentials) {
        this.jobs = jobs;
        this.credentials = credentials;
    }

    public int configuredBatchSize() {
        return jobs.batchSize();
    }

    // Không in hoặc trả clientSecret ra response/log.
}
~~~

**Điểm nổi bật:** `JobsProperties` từ ConfigMap mount và `PartnerCredentials` từ Secret mount có thể được xử lý bằng cùng cơ chế `@ConfigurationProperties`. Java code không cần biết data được lưu trong một Kubernetes object tên gì.

### Import bắt buộc và optional

Ví dụ trên dùng đường dẫn bắt buộc. Nếu một directory không tồn tại, Spring Boot thường báo lỗi Config Data và không hoàn tất startup.

Trong môi trường local không có mount, có thể dùng:

~~~yaml
spring:
  config:
    import: "optional:configtree:/etc/app/config/"
~~~

Nhưng `optional:` chỉ cho phép thiếu **vị trí Config Data**, không có nghĩa một credential bắt buộc được phép vắng mặt. Với secret dùng cho production, nên giữ kiểm tra `@NotBlank` và chính sách startup rõ ràng.

## 15. Một file YAML hoàn chỉnh trong ConfigMap: import file thay vì configtree

Không phải volume nào cũng dùng “mỗi file là một key”. Có thể lưu toàn bộ YAML làm **một entry** của ConfigMap:

~~~yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: order-application-yaml
data:
  application.yaml: |
    app:
      jobs:
        batch-size: 200
        timeout: 15s
~~~

Mount:

~~~yaml
volumeMounts:
  - name: external-yaml
    mountPath: /etc/app/external
    readOnly: true
volumes:
  - name: external-yaml
    configMap:
      name: order-application-yaml
~~~

Trong container:

~~~text
/etc/app/external/application.yaml
~~~

Đây là **một file YAML có nhiều thuộc tính**, nên có thể import:

~~~properties
spring.config.import=optional:file:/etc/app/external/application.yaml
~~~

Không dùng:

~~~properties
spring.config.import=configtree:/etc/app/external/
~~~

nếu mục tiêu là parse **nội dung YAML** thành `app.jobs.batch-size` và `app.jobs.timeout`. Với `configtree:`, tên file `application.yaml` chính là key, nội dung YAML không được phân tích theo cấu trúc ấy.

### Nếu file không có đuôi

Một số nền tảng mount file tên:

~~~text
/etc/app/external/application
~~~

vẫn chứa YAML. Có thể dùng extension hint:

~~~properties
spring.config.import=optional:file:/etc/app/external/application[.yaml]
~~~

Cách dùng này cho Spring Boot biết định dạng file không extension.

### Trường hợp không cần spring.config.import

Spring Boot cũng có các vị trí tìm `application.properties`/`application.yaml` mặc định và các cấu hình `spring.config.location`, `spring.config.additional-location`. Nếu volume được mount đúng một vị trí đang được Spring Boot tìm ở startup, có thể không cần import riêng. Tuy nhiên, với path Kubernetes như `/etc/app/external/`, khai báo import tường minh thường giúp rõ ràng và ít phụ thuộc working directory.

## 16. configtree so với file: và cách chọn đường nạp

| Dạng mount | Cấu trúc | Cách nhận trong Spring Boot |
| --- | --- | --- |
| Mỗi key là một file | `/etc/config/app.jobs.batch-size` | `configtree:/etc/config/` |
| Nhiều thư mục con đại diện key phân cấp | `/etc/config/app/jobs/timeout` | `configtree:/etc/config/` |
| Một file `application.yaml` | `/etc/config/application.yaml` | `file:/etc/config/application.yaml` |
| Một file `application.properties` | `/etc/config/application.properties` | `file:/etc/config/application.properties` |
| File YAML không có extension | `/etc/config/application` | `file:/etc/config/application[.yaml]` |
| ConfigMap cấp bằng `envFrom` | `APP_JOBS_TIMEOUT=15s` | Không cần import; system environment source |
| Secret cấp bằng `secretKeyRef` | `PARTNER_AUTH_CLIENTSECRET=...` | Không cần import; system environment source |

Chọn dựa trên **cách dữ liệu tồn tại bên trong container**, không chỉ dựa trên việc nguồn là ConfigMap hay Secret.

## 17. Projected volume: ghép ConfigMap và Secret trong một mount

Kubernetes hỗ trợ **projected volume** cho phép nhiều nguồn được chiếu vào cùng một directory. Có thể dùng để ghép dữ liệu từ ConfigMap, Secret và các loại nguồn được hỗ trợ khác.

Ví dụ:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: order-service
spec:
  replicas: 1
  selector:
    matchLabels:
      app: order-service
  template:
    metadata:
      labels:
        app: order-service
    spec:
      containers:
        - name: app
          image: example/order-service:1.0.0
          volumeMounts:
            - name: app-settings
              mountPath: /etc/app/settings
              readOnly: true
      volumes:
        - name: app-settings
          projected:
            sources:
              - configMap:
                  name: order-runtime-files
                  items:
                    - key: app.jobs.batch-size
                      path: config/app.jobs.batch-size
                    - key: app.jobs.timeout
                      path: config/app.jobs.timeout
              - secret:
                  name: partner-credentials
                  items:
                    - key: client-secret
                      path: secret/partner.auth.client-secret
~~~

Trong mount:

~~~text
/etc/app/settings/
├── config/
│   ├── app.jobs.batch-size
│   └── app.jobs.timeout
└── secret/
    └── partner.auth.client-secret
~~~

Spring Boot có thể import:

~~~yaml
spring:
  config:
    import:
      - "configtree:/etc/app/settings/config/"
      - "configtree:/etc/app/settings/secret/"
~~~

Sử dụng hai nhánh tách biệt giúp tránh trường hợp một import root quá rộng vô tình đưa thành key `config.app.jobs.batch-size` hay `secret.partner.auth.client-secret`, khiến prefix cần bind không còn khớp.

### Những rủi ro cần quản lý

- Cần tránh hai nguồn cùng ghi vào một path tương đối trong projected volume.
- Phân quyền và tính nhạy cảm của file vẫn phải được xem xét.
- Cơ chế cập nhật mount không đồng nghĩa Spring Boot tự bind lại khi file thay đổi.
- Nếu cần rotation động, phải thiết kế rõ thời điểm nạp lại bean và client.

Projected volume hữu ích khi muốn giảm số mount hoặc tổ chức dữ liệu cấu hình có cấu trúc, không phải một yêu cầu bắt buộc của Spring Boot.

## 18. Mount thông qua subPath: vì sao dễ gây nhầm lẫn?

Kubernetes cho phép mount riêng một file từ volume bằng `subPath`:

~~~yaml
volumeMounts:
  - name: config
    mountPath: /etc/app/application.yaml
    subPath: application.yaml
~~~

Ví dụ này có thể giúp ứng dụng nhìn thấy đúng một file mà không che các file có sẵn trong directory. Nhưng **ConfigMap hoặc Secret được mount qua `subPath` không nhận cập nhật tự động từ object nguồn** theo cơ chế projected volume thông thường.

Phân biệt:

| Kiểu mount | File có thể được Kubernetes cập nhật sau khi object đổi? |
| --- | --- |
| Mount ConfigMap/Secret như một directory thông thường | Thường có, sau một khoảng trễ đồng bộ. |
| Mount từng file qua `subPath` | Không nhận cập nhật tự động theo cơ chế đó. |

Nếu bạn cần nhận bản cấu hình mới sau rollout, thông thường Pod mới sẽ mount giá trị phù hợp tại thời điểm tạo. Nhưng nếu mong một container đang chạy nhìn thấy bản cập nhật, `subPath` là lựa chọn không phù hợp.

**Lưu ý riêng cho Spring Boot:** ngay cả với mount directory thường và file đã đổi, binder không mặc nhiên refresh một bean đã được tạo. Có hai tầng cập nhật: Kubernetes cập nhật file và ứng dụng nạp lại giá trị.

## 19. Cập nhật ConfigMap qua volume: eventual consistency

Kubernetes cập nhật các file ConfigMap đã mount theo cơ chế nhất quán cuối cùng (*eventual consistency*), không đồng bộ tức thì.

Một chuỗi sự kiện điển hình:

~~~text
ConfigMap được sửa trên Kubernetes API
                 |
                 v
kubelet phát hiện thay đổi
      (watch / cache / sync)
                 |
                 v
file trong volume của Pod thay đổi
                 |
                 v
ứng dụng có thể đọc nội dung file mới
                 |
                 v
Spring Boot bean có tự đổi không?
                 |
                 +-- Không, trừ khi có cơ chế reload
                     hoặc được restart/recreated
~~~

Độ trễ từ lúc ConfigMap thay đổi đến lúc file mount được cập nhật phụ thuộc vào cơ chế phát hiện thay đổi, cache và chu kỳ đồng bộ của kubelet.

Vì vậy:

- Không dùng thời điểm `kubectl apply` hoàn thành làm bằng chứng mọi Pod đã đọc giá trị mới.
- Không mong tất cả Pod cập nhật file cùng một mili giây.
- Không đọc nhầm bản cũ nếu ứng dụng cache nội dung file.
- Không tự khẳng định secret rotation hoàn tất chỉ vì đối tượng nguồn đã thay đổi.

Nếu cấu hình rất quan trọng cho tính nhất quán, rolling restart với một phiên bản cấu hình được kiểm soát thường dễ dự đoán hơn việc dựa vào reload động không được thiết kế.

## 20. Cập nhật Secret volume và quá trình rotation

Với Secret volume mount thông thường, Kubernetes cũng có thể cập nhật file theo cơ chế eventual consistency. Nhưng khi credential thay đổi, có nhiều trạng thái cần kiểm tra:

1. Secret object đã chứa phiên bản mới.
2. Kubelet đã cập nhật dữ liệu mount trong Pod.
3. Ứng dụng đã đọc hoặc nạp lại secret mới.
4. Connection pool, HTTP client, TLS context hay token cache đã được tạo lại nếu cần.
5. Dịch vụ phụ trợ đã chấp nhận credential mới.
6. Credential cũ có thể được thu hồi mà không làm gián đoạn workload.

Nhảy từ bước 1 tới bước 6 rất nguy hiểm.

### Rotation với environment variables

Nếu Secret được cấp bằng `secretKeyRef` → env:

- Container đang chạy giữ environment đã được cấp khi tạo.
- Cần restart/recreate Pod để nhận dữ liệu mới theo cách mặc định.
- Phải tính tới số bản sao và khả năng tương thích giữa hai credential trong thời gian rollout.

### Rotation với volume

Nếu Secret được cấp qua file volume:

- File có thể được Kubernetes cập nhật.
- Đọc file trực tiếp ở thời điểm dùng có thể nhận dữ liệu mới nếu app được thiết kế như vậy.
- Spring Boot `configtree:` được xử lý trong giai đoạn khởi động và **không tự refresh mọi `@ConfigurationProperties` hoặc auto-configured clients**.
- Nếu application cần cập nhật động, phải có cơ chế reload/refresh, kiểm thử đồng thời và hành vi lỗi rõ ràng.

### Ví dụ rủi ro với DataSource

Khi password trong Secret mount đã đổi, một connection pool đã khởi tạo có thể vẫn dùng credential cũ. Việc sửa file không bắt buộc pool lấy password mới ở những kết nối tiếp theo.

Một kế hoạch rotation thực tế thường cần phối hợp thay đổi ở database/secret manager, rollout ứng dụng và thu hồi credential cũ sau xác minh.

## 21. Spring Boot PropertySource precedence: nguồn nào thắng?

Với một property như:

~~~text
app.jobs.timeout
~~~

bạn có thể vô tình khai báo nó trong:

- `application.yaml` đóng gói trong image.
- ConfigMap mounted dạng YAML hoặc configtree.
- Environment variable `APP_JOBS_TIMEOUT`.
- Java system property.
- Command-line argument `--app.jobs.timeout=...`.

Spring Boot có thứ tự ưu tiên nguồn cấu hình. Trong thứ tự mặc định, **environment variables** thường có ưu tiên cao hơn **Config Data**, bao gồm các file import; tùy chọn CLI thường có thể ghi đè environment.

Ví dụ:

~~~text
application.yaml           app.jobs.timeout = 5s
mounted configtree         app.jobs.timeout = 20s
environment                APP_JOBS_TIMEOUT = 30s
CLI                        --app.jobs.timeout=45s
~~~

Trong cách nạp mặc định, giá trị có hiệu lực thường là `45s` từ CLI.

### Rủi ro chuyển env sang volume

Nếu trước đây Deployment dùng:

~~~yaml
env:
  - name: APP_JOBS_TIMEOUT
    value: "30s"
~~~

và bạn đã chuyển ConfigMap sang volume có:

~~~text
/etc/app/config/app.jobs.timeout → 20s
~~~

nhưng quên xóa environment cũ, Spring Boot có thể vẫn nhận **30s**.

**Mount đúng không có nghĩa mount đang thắng thứ tự property source.** Khi chuyển phương án, cần kiểm kê và xóa các nguồn trùng tên không còn mong muốn.

### Không dùng argument chứa secret thật

Dù CLI có thể có ưu tiên cao, đừng đưa credential production qua:

~~~bash
java -jar app.jar --partner.auth.client-secret=REAL_SECRET
~~~

Tham số có thể xuất hiện trong process metadata, command history, log hoặc hệ thống giám sát. Secret nên được cấp qua kênh được platform quản lý.

## 22. Chẩn đoán thiếu dữ liệu khi dùng ConfigMap hoặc Secret

### Triệu chứng A — không có biến environment

Nguyên nhân có thể:

- ConfigMap/Secret không tồn tại trong namespace của Pod.
- Key trong `configMapKeyRef` / `secretKeyRef` viết sai.
- `envFrom` gặp key không thể dùng làm tên biến.
- Deployment chưa tạo Pod mới sau khi thay đổi nguồn.
- Container đang xem khác container hoặc namespace.

Cách điều tra: xem cấu hình Pod/Deployment, event và các **tên biến** đã được cấp; tránh in toàn bộ environment nếu có secret.

### Triệu chứng B — volume mount không có file

Nguyên nhân có thể:

- Sai tên ConfigMap/Secret.
- Sai `volumeMounts.name` so với `volumes.name`.
- Mount path khác đường dẫn ứng dụng kỳ vọng.
- `items.key` không tồn tại hoặc `items.path` khác tên file cần.
- Quyền file hoặc directory không cho JVM đọc.

Cách điều tra: kiểm tra tên file, quyền, owner, vị trí mount. Không dùng `cat` để in credential thật lên log hoặc ticket.

### Triệu chứng C — có file nhưng Spring Boot không bind

Nguyên nhân có thể:

- Chưa khai báo `spring.config.import`.
- Dùng `configtree:` trên một file YAML hoàn chỉnh thay vì `file:`.
- Root `configtree:` quá nông hoặc quá sâu làm sai tên property.
- Tên file trong volume không khớp tên canonical của `@ConfigurationProperties`.
- Biến môi trường hoặc source khác ghi đè.
- File có thể được đọc nhưng giá trị sai kiểu.

### Triệu chứng D — cập nhật ConfigMap nhưng app vẫn dùng cũ

Nguyên nhân có thể:

- App đang dùng env, không phải volume.
- Mount qua `subPath`.
- Kubelet chưa đồng bộ bản cập nhật.
- Spring Boot đã bind cấu hình lúc khởi động và giữ object cũ.
- Client/connection pool cache giá trị.

Giải pháp phụ thuộc kiến trúc: rolling restart hoặc cơ chế reload được triển khai và kiểm thử.

## 23. Kiểm tra tình trạng mà không làm lộ secret

Có thể kiểm tra một giá trị có mặt thông qua API mà không in nội dung:

~~~java
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class CredentialsAvailability {

    private final Environment environment;

    public CredentialsAvailability(Environment environment) {
        this.environment = environment;
    }

    public boolean partnerCredentialConfigured() {
        String secret =
                environment.getProperty("partner.auth.client-secret");

        return secret != null && !secret.isBlank();
    }
}
~~~

Chỉ xuất kết luận như:

~~~text
partner.auth.client-secret: configured
~~~

Không xuất:

~~~java
System.out.println(
        environment.getProperty("partner.auth.client-secret"));
~~~

Và không log một record chứa secret:

~~~java
log.info("auth config = {}", partnerCredentials);
~~~

Record Java có `toString()` tự sinh, có thể xuất tất cả thành viên, kể cả `clientSecret`. Nếu cần logging trạng thái cấu hình, hãy chỉ log metadata an toàn và che giá trị.

### Actuator env/configprops

Các endpoint `/actuator/env` và `/actuator/configprops` có thể hỗ trợ chẩn đoán nếu Spring Boot Actuator được cài, bật và giới hạn quyền truy cập thích hợp. Không mặc định rằng mọi giá trị luôn được che hoàn hảo trong mọi phiên bản hoặc cấu hình.

Trong production, không nên mở công khai endpoint cho người dùng bên ngoài chỉ để xem giá trị cấu hình.

## 24. Bảo mật khi dùng Secret volume

Secret volume giúp ứng dụng không phải nhận một giá trị dài qua environment, nhưng vẫn cần bảo vệ:

- Chỉ Pod cần secret mới được mount.
- Chỉ container cần đọc mới được gắn `volumeMounts` phù hợp.
- Mount read-only; thực tế Secret volume thường được mount chỉ đọc.
- Cấu hình user/group và file mode đủ để đọc nhưng không quá rộng.
- Hạn chế `exec` và quyền debug container vào production.
- Hạn chế quyền đọc Secret object thông qua Kubernetes RBAC.
- Xem xét encryption at rest và audit truy cập ở control plane.
- Không in nội dung qua logs, crash dump, trace hoặc script.
- Không dùng token chung cho mọi ứng dụng/môi trường nếu có thể cấp theo scope.

Một Secret không trở thành an toàn tuyệt đối vì đã chuyển từ `env` sang file. Người có quyền đọc file hoặc thực thi mã trong container vẫn có thể lấy dữ liệu.

### Không bỏ qua ConfigMap

ConfigMap không phải kho bí mật, nhưng vẫn có thể chứa thông tin nội bộ như endpoint, hostname, feature flag, tên cluster. Vẫn cần giới hạn quyền đọc/sửa phù hợp và xem xét tính toàn vẹn cấu hình.

## 25. Kiểm tra cấu hình bắt buộc với @Validated

Giả sử một module phải có partner client secret trước khi khởi động.

~~~java
package com.example.demo.config;

import jakarta.validation.constraints.NotBlank;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "partner.auth")
public record PartnerAuthProperties(
        @NotBlank String clientId,
        @NotBlank String clientSecret) {
}
~~~

Nếu có Bean Validation provider, thường qua `spring-boot-starter-validation`, Spring Boot có thể kiểm tra các constraint trong quá trình binding.

Dù bạn dùng `env` hay `configtree:`, nếu property `partner.auth.client-secret` thiếu hoặc rỗng, ứng dụng có thể bị chặn khởi động khi validation được cấu hình phù hợp.

### optional: của Config Data khác optional của Kubernetes

- `optional:configtree:/path/`: cho phép Spring Boot không thất bại ngay khi **vị trí import không tồn tại**.
- `secretKeyRef.optional: true`: cho phép Kubernetes xem một tham chiếu Secret/key là tùy chọn theo API.
- `@NotBlank` / custom validation: xác định **nghiệp vụ** có cho phép credential thiếu hay không.

Ba cấp này không thay thế cho nhau. Với secret bắt buộc ở production, cần có chính sách rõ ràng ở cả Kubernetes và Spring Boot.

## 26. Hai chiến lược triển khai: cấu hình bất biến và cập nhật động

### 26.1. Ưu tiên cấu hình bất biến theo vòng đời Pod

Mô hình dễ vận hành:

1. ConfigMap/Secret do hệ thống deployment/secret manager tạo hoặc cập nhật.
2. Deployment template được thay đổi để tạo Pod mới, hoặc trigger rollout.
3. Pod mới nhận env/volume phiên bản phù hợp.
4. Spring Boot đọc Config Data lúc startup, tạo bean/client.
5. Health/readiness thành công, lưu lượng được chuyển sang Pod mới.
6. Pod cũ được loại bỏ có kiểm soát.

Ưu điểm:

- Dễ truy vết cấu hình mỗi Pod đã khởi chạy với giá trị nào.
- Không cần chương trình tự đọc lại file.
- Dễ xác minh startup validation và readiness.
- Phù hợp hệ thống có nhiều bean bất biến hoặc pool giữ credential.

### 26.2. Cập nhật động qua volume

Mô hình này chỉ phù hợp khi:

- Container dùng volume không qua `subPath`.
- Kubernetes có thể cập nhật file theo cơ chế thông thường.
- Ứng dụng có thiết kế đọc lại file hoặc refresh/rebind bean.
- Từng client/connection pool được cập nhật an toàn.
- Có kiểm thử tính nhất quán, lỗi reload và khả năng rollback.

Không nên nhầm “kubelet thay file” với “mọi class `@ConfigurationProperties` tự đổi”. Đây là hai sự kiện ở hai tầng độc lập.

### 26.3. Thay đổi cấu hình có thể yêu cầu restart ngay cả khi file mới xuất hiện

Ví dụ thay `server.port`, DataSource credentials, TLS config hoặc các thông số khởi tạo framework thường không thể áp dụng đầy đủ chỉ bằng việc cập nhật một field trong `Environment`. Những thành phần đã được tạo trước đó có thể cần tái khởi tạo hoặc restart.

Với thay đổi kiểu này, rolling restart thường là chiến lược dễ dự đoán hơn.

## 27. Kịch bản thực hành: môi trường dev dùng env, production dùng volume

Giả sử cùng một image:

~~~text
example/order-service:1.0.0
~~~

### Development

ConfigMap:

~~~yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: order-dev-env
data:
  APP_JOBS_BATCHSIZE: "25"
  APP_JOBS_TIMEOUT: "3s"
~~~

Deployment dev:

~~~yaml
envFrom:
  - configMapRef:
      name: order-dev-env
~~~

Spring Boot tự nhận các biến này thông qua environment. Không cần `spring.config.import=configtree:` cho riêng env.

### Production

ConfigMap volume:

~~~yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: order-prod-config
data:
  app.jobs.batch-size: "500"
  app.jobs.timeout: "20s"
~~~

Deployment prod:

~~~yaml
env:
  - name: SPRING_CONFIG_IMPORT
    value: "configtree:/etc/app/config/"
volumeMounts:
  - name: runtime-config
    mountPath: /etc/app/config
    readOnly: true
~~~

Volume:

~~~yaml
volumes:
  - name: runtime-config
    configMap:
      name: order-prod-config
~~~

Spring Boot đọc directory từ `SPRING_CONFIG_IMPORT`, và các field Java giống hệt development.

**Lưu ý:** các đoạn ở đây là fragments. Khi đưa vào manifest, phải đặt `env` và `volumeMounts` dưới đúng container, `volumes` dưới Pod spec. Không đặt `volumes` trong container.

### Lợi ích

- Cùng artifact và class `JobsProperties`.
- Không nhúng cấu hình production vào code.
- Có thể thay cách cấp dữ liệu theo môi trường.
- Giữ namespace thuộc tính logic ổn định.

Đổi kênh cấp cần kiểm tra tên key và thứ tự nguồn, nhưng không cần đổi business service.

## 28. Các lỗi hay gặp với ConfigMap hoặc Secret

### Lỗi 1 — Dùng envFrom với key mang tên property canonical

ConfigMap chứa:

~~~yaml
data:
  app.jobs.batch-size: "100"
~~~

nhưng Deployment dùng:

~~~yaml
envFrom:
  - configMapRef:
      name: app-config
~~~

Không nên mong Kubernetes tự đổi key thành `APP_JOBS_BATCHSIZE`. Hãy dùng `configMapKeyRef` để đặt tên biến rõ ràng, hoặc thay key trong ConfigMap sang dạng environment phù hợp.

### Lỗi 2 — Quên dấu nháy cho số và Boolean trong ConfigMap data

~~~yaml
data:
  APP_JOBS_BATCHSIZE: 100
~~~

Trong YAML, `100` có thể được parse là numeric, trong khi `ConfigMap.data` yêu cầu giá trị String. Nên dùng:

~~~yaml
data:
  APP_JOBS_BATCHSIZE: "100"
~~~

### Lỗi 3 — Có Secret nhưng không tham chiếu từ Pod

Kubernetes Secret tồn tại trong namespace không có nghĩa mọi Pod tự nhận nó. Cần `secretKeyRef`, `secretRef` hoặc volume mount tương ứng.

### Lỗi 4 — Sai namespace

Pod thường tham chiếu ConfigMap/Secret trong cùng namespace. Đừng suy luận rằng một Secret tên giống nhau ở namespace khác sẽ được tự động dùng.

### Lỗi 5 — Chỉ mount volume, không cấu hình Spring đọc

Kubernetes có thể mount file đúng; Spring Boot vẫn cần `configtree:`, `file:`, `spring.config.location` phù hợp hoặc logic đọc file khác. Chỉ có file không đảm bảo có property.

### Lỗi 6 — Dùng configtree trên một file YAML

Nếu chỉ có `application.yaml` trong mount, `configtree:` xử lý file như một key, không parse nội dung YAML thành nhiều property. Hãy import bằng `file:` hoặc dùng cấu hình tìm kiếm vị trí file phù hợp.

### Lỗi 7 — Nhầm root khi import directory

File:

~~~text
/etc/config/app/jobs/timeout
~~~

Import `configtree:/etc/config/` cung cấp `app.jobs.timeout`. Import `configtree:/etc/config/app/` cung cấp `jobs.timeout`. Đổi import root có thể làm binding đổi nghĩa.

### Lỗi 8 — Chỉnh ConfigMap và mong env của Pod đang chạy thay đổi

Environment không tự cập nhật theo sửa đổi ConfigMap. Cần rollout/recreate Pod.

### Lỗi 9 — Dùng subPath và chờ file tự cập nhật

ConfigMap/Secret mounted qua `subPath` không nhận cập nhật tự động. Tránh nếu tính năng này là yêu cầu.

### Lỗi 10 — File đổi nhưng Java bean không đổi

Spring Boot thường nạp Config Data lúc khởi động. Một bean đã tạo không tự rebind chỉ vì kubelet đổi file.

### Lỗi 11 — Secret được ghi vào ConfigMap hoặc manifest literal

Cách đó làm tăng nguy cơ lộ credential qua Git, API, pipeline và log. Dùng Secret được quản lý với quyền truy cập thích hợp, không lưu dữ liệu thật trực tiếp trong ví dụ.

### Lỗi 12 — Nghĩ Secret base64 là mã hóa

Base64 không ngăn người có quyền đọc Secret giải mã giá trị. Bảo mật còn phụ thuộc RBAC và encryption at rest.

### Lỗi 13 — File quyền 0400 nhưng app chạy user khác

Container có thể không đọc được. Sửa ownership/group/mode theo least privilege, không mở quyền toàn bộ.

### Lỗi 14 — Hai nguồn cùng tên property

Env `APP_JOBS_TIMEOUT` có thể ghi đè file ConfigMap `app.jobs.timeout`; cần chọn nguồn chủ đạo và loại bỏ nguồn cũ.

### Lỗi 15 — In log toàn bộ Environment

Mã `System.getenv()` hoặc `Environment`/record `toString()` có thể lộ secret. Chỉ log trạng thái có/không có và tên khóa an toàn.

### Lỗi 16 — Gắn secret volume cho nhiều container không cần thiết

Trong Pod có nhiều container, mount chỉ những secret thật sự cần. Tránh mở phạm vi đọc cho sidecar hoặc debug container không có yêu cầu.

### Lỗi 17 — Cho rằng configMapKeyRef là một file

`configMapKeyRef` cấp **một biến môi trường**, không phải file. Nếu cần file, dùng `volumes[].configMap` và `volumeMounts`.

### Lỗi 18 — Bỏ qua giá trị có hiệu lực

Có thể nhìn YAML đúng nhưng CLI, env hoặc nguồn có ưu tiên cao hơn lại cung cấp giá trị khác. Kiểm tra `PropertySource` và trạng thái của bean đã được bind.

## 29. Kiểm thử và xác minh trên môi trường không có credential thật

### 29.1. Kiểm thử binding với env giả

Trong Spring Boot test:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest(properties = {
        "app.jobs.batch-size=42",
        "app.jobs.timeout=6s"
})
class JobsPropertiesTest {

    @Autowired
    JobsProperties jobs;

    @Test
    void bindsValues() {
        assertEquals(42, jobs.batchSize());
        assertEquals(Duration.ofSeconds(6), jobs.timeout());
    }
}
~~~

Test yêu cầu `JobsProperties` được đăng ký trong context, ví dụ ứng dụng có `@ConfigurationPropertiesScan`. Nó kiểm tra giá trị sau binding nhưng không chứng minh Kubernetes mount đúng trong production.

### 29.2. Kiểm thử volume với dữ liệu giả

Một integration test có thể:

1. Tạo temporary directory.
2. Ghi file `app.jobs.batch-size` với nội dung `42`.
3. Ghi file `app.jobs.timeout` với nội dung `6s`.
4. Khởi chạy context với `spring.config.import=configtree:<test-dir>/` được cung cấp **trước giai đoạn Config Data**.
5. Inject `JobsProperties` và kiểm tra hai giá trị.
6. Xóa temp directory sau test.

Không cần secret production để kiểm tra cơ chế. Nếu tạo file để kiểm thử, dùng marker không có giá trị truy cập thật.

### 29.3. Kiểm thử Secret thiếu

Tạo môi trường thử nghiệm không có mounted file `partner.auth.client-secret`, trong khi class có `@NotBlank`.

Kỳ vọng ứng dụng không hoàn tất tạo properties bean nếu validation được cấu hình phù hợp. Đây là test **chính sách bắt buộc**, không cần một token thật.

### 29.4. Kiểm thử sự khác nhau giữa env và volume khi cập nhật

Trong môi trường dev Kubernetes:

- Tạo Pod dùng một ConfigMap theo env, một Pod khác dùng volume.
- Cập nhật ConfigMap thử nghiệm.
- Quan sát: env cũ không tự thay; file volume có thể thay sau độ trễ.
- Nếu Spring Boot đang dùng file qua `configtree:`, kiểm tra lại bean khi không restart để thấy nó không tự được refresh.
- Recreate Pod và kiểm tra startup với dữ liệu mới.

Đây là test quan trọng để tránh nhầm giữa Kubernetes sync và application reload.

## 30. Bài tập thực hành có đáp án

### Bài 1 — chọn cơ chế cho một key

ConfigMap `app-runtime` có key `batchSize` = `"200"`. Muốn cấp biến `APP_JOBS_BATCHSIZE`.

**Đáp án:**

~~~yaml
env:
  - name: APP_JOBS_BATCHSIZE
    valueFrom:
      configMapKeyRef:
        name: app-runtime
        key: batchSize
~~~

### Bài 2 — nhập toàn bộ ConfigMap

ConfigMap `runtime-env` có key `APP_JOBS_TIMEOUT` và `APP_JOBS_BATCHSIZE`.

**Đáp án:**

~~~yaml
envFrom:
  - configMapRef:
      name: runtime-env
~~~

### Bài 3 — chọn một secret key

Secret `partner-credentials` có key `client-secret`.

**Đáp án:**

~~~yaml
env:
  - name: PARTNER_AUTH_CLIENTSECRET
    valueFrom:
      secretKeyRef:
        name: partner-credentials
        key: client-secret
~~~

### Bài 4 — mount một ConfigMap thành nhiều file

ConfigMap `runtime-files` có key `app.jobs.batch-size` và `app.jobs.timeout`.

**Đáp án:** đặt `volumes[].configMap.name=runtime-files`, mount vào `/etc/app/config`, rồi dùng `spring.config.import=configtree:/etc/app/config/`.

### Bài 5 — đọc tệp YAML từ ConfigMap

ConfigMap có entry `application.yaml` chứa nhiều khóa.

**Đáp án:** mount file đó rồi import `file:/etc/app/config/application.yaml` hoặc dùng location search phù hợp, không dùng `configtree:` để parse nội dung YAML.

### Bài 6 — phân biệt key path với property name

File mount:

~~~text
/etc/app/secrets/partner.auth.client-secret
~~~

Import `configtree:/etc/app/secrets/`.

**Đáp án:** property là `partner.auth.client-secret`.

### Bài 7 — đổi root

File:

~~~text
/etc/app/secrets/partner/auth/client-secret
~~~

Import `configtree:/etc/app/secrets/partner/`.

**Đáp án:** property là `auth.client-secret`, không có đoạn `partner` vì root được đặt sâu hơn.

### Bài 8 — update ConfigMap, env không đổi

Pod đang có `APP_JOBS_TIMEOUT=10s` qua `envFrom`. ConfigMap được sửa thành `20s`.

**Đáp án:** Pod đang chạy không tự có environment mới; cần recreate/restart Pod để nhận khi khởi tạo.

### Bài 9 — volume đã đổi nhưng bean giữ cũ

File mount `app.jobs.timeout` đổi từ `10s` thành `20s`.

**Đáp án:** Kubernetes có thể cập nhật file, nhưng bean `JobsProperties` đã được bind trong Spring Boot không tự đổi nếu không có cơ chế refresh/restart riêng.

### Bài 10 — Secret qua subPath

Một Secret được mount thành một file bằng `subPath`; Secret object đổi.

**Đáp án:** file được mount theo cách này không nhận cập nhật tự động như volume directory thông thường.

### Bài 11 — khóa nhiều nguồn

ConfigMap file có `app.jobs.timeout=10s`, environment có `APP_JOBS_TIMEOUT=30s`.

**Đáp án:** trong thứ tự nguồn Spring Boot thông thường, environment có thể thắng Config Data. Cần bỏ nguồn dư hoặc kiểm soát ưu tiên rõ ràng.

### Bài 12 — xác minh không lộ bí mật

Bạn muốn biết `partner.auth.client-secret` đã được bind chưa.

**Đáp án:** dùng `@NotBlank`, startup validation và một thông báo trạng thái an toàn; không in giá trị secret hoặc record `toString()`.

### Bài 13 — key của ConfigMap có dấu chấm

ConfigMap có key `app.jobs.timeout` nhưng dùng `envFrom`.

**Đáp án:** đừng giả định Kubernetes tự đổi tên thành `APP_JOBS_TIMEOUT`. Dùng `configMapKeyRef` để chọn key và đặt `env.name` rõ ràng, hoặc dùng volume `configtree:`.

### Bài 14 — cần cập nhật certificate

Một thư viện chỉ nhận file path đến certificate và private key.

**Đáp án:** mount file với quyền hạn chế có thể phù hợp hơn chuyển toàn bộ dữ liệu sang env. Cần xem thư viện có hỗ trợ reload file không; nếu không, restart/recreate client hoặc Pod.

### Bài 15 — giải thích optional

`spring.config.import=optional:configtree:/etc/app/secrets/` trong khi secret bắt buộc cho production.

**Đáp án:** `optional:` chỉ làm vị trí import được phép vắng. Vẫn cần validation và chính sách triển khai để không chạy với credential thiếu.

## 31. Checklist trước khi lên production

### Phân loại dữ liệu

- ConfigMap chỉ chứa thông số không nhạy cảm.
- Secret chứa credential/token/key với scope phù hợp.
- Không có secret thật trong Git, image hoặc manifest literal.
- Quy trình cấp và đổi secret được quản lý tập trung khi cần.

### Chọn cách cấp

- `envFrom` khi nhiều biến đều cần và tên key hợp lệ.
- `configMapKeyRef` / `secretKeyRef` khi muốn chọn key hoặc đổi tên env.
- Volume khi cần file hoặc cấu trúc nhiều key theo tree.
- `file:` cho một tệp YAML/Properties hoàn chỉnh.
- `configtree:` cho directory mỗi file một giá trị.

### Spring Boot

- Prefix và tên biến môi trường ánh xạ đúng.
- Root configtree khớp tên property cần bind.
- Bean `@ConfigurationProperties` được đăng ký.
- Cấu hình bắt buộc có validation.
- Thứ tự nguồn không để env cũ ghi đè volume mới.
- Không có logging toàn bộ secret.

### Kubernetes

- Namespace của Pod và resource phù hợp.
- ConfigMap/Secret tồn tại trước khi workload dùng.
- `volumes.name` và `volumeMounts.name` khớp nhau.
- Container mount đúng path và có quyền đọc.
- Không dùng `subPath` nếu cần file cập nhật tự động.
- Có chính sách rollout khi ConfigMap/Secret đổi.
- RBAC, image hardening, runtime isolation và encryption at rest được xem xét.

### Rotation và vận hành

- Biết env không tự cập nhật.
- Biết volume có thể cập nhật sau độ trễ.
- Biết Spring Boot không tự rebind mọi cấu hình khi file đổi.
- Biết cần recreate client/connection pool hay Pod.
- Có readiness, rollback và cách thu hồi credential cũ.
- Không xác minh bằng cách in giá trị bí mật ra log hoặc terminal.

## 32. Kết luận

Kubernetes cung cấp hai đường cấp ConfigMap/Secret cho Spring Boot:

**Qua biến môi trường:** dùng `env.valueFrom.configMapKeyRef` / `secretKeyRef` để chọn từng key, hoặc `envFrom.configMapRef` / `secretRef` để cấp nhiều key. Spring Boot đọc từ OS environment với quy tắc tên thuộc tính tương ứng. Cách này gọn và trực tiếp nhưng **biến môi trường của process không tự đổi khi ConfigMap/Secret được cập nhật**.

**Qua volume:** Kubernetes mount dữ liệu thành file. Spring Boot có thể dùng `configtree:` cho directory chứa các file key-value hoặc `file:` cho một YAML/Properties file hoàn chỉnh. File mounted thường được Kubernetes cập nhật theo cơ chế eventual consistency, ngoại trừ một số tình huống như `subPath`; nhưng **Spring Boot không mặc nhiên làm mới bean/client đã khởi tạo khi file thay đổi**.

Dù lựa chọn cách nào, ba tầng cần được phân biệt:

1. **Kubernetes cấp dữ liệu:** chọn ConfigMap/Secret, key, env hoặc path.
2. **Spring Boot nạp và bind:** Environment/Config Data, prefix, PropertySource precedence, `@ConfigurationProperties`.
3. **Ứng dụng áp dụng thay đổi:** startup, validation, dependency injection, refresh hoặc rolling restart.

Khi hiểu đúng ba tầng này, bạn có thể triển khai cùng một artifact Spring Boot ở nhiều môi trường mà không hard-code cấu hình, giảm rủi ro lộ credential và đưa ra kế hoạch cập nhật/rotation dễ kiểm soát hơn.

## Tài liệu tham khảo

- [Kubernetes — ConfigMaps](https://kubernetes.io/docs/concepts/configuration/configmap/).
- [Kubernetes — Secrets](https://kubernetes.io/docs/concepts/configuration/secret/).
- [Kubernetes — Volumes](https://kubernetes.io/docs/concepts/storage/volumes/).
- [Kubernetes — Projected Volumes](https://kubernetes.io/docs/concepts/storage/projected-volumes/).
- [Kubernetes — Configure a Pod to Use a ConfigMap](https://kubernetes.io/docs/tasks/configure-pod-container/configure-pod-configmap/).
- [Kubernetes — Distribute Credentials Securely Using Secrets](https://kubernetes.io/docs/tasks/inject-data-application/distribute-credentials-secure/).
- [Spring Boot — Externalized Configuration and Configuration Trees](https://docs.spring.io/spring-boot/reference/features/external-config.html).