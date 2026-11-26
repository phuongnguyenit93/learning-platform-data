# ConfigMap, Secret và cách đưa dữ liệu vào container

Kubernetes cung cấp ConfigMap và Secret để tách dữ liệu cấu hình khỏi image của ứng dụng. ConfigMap phù hợp với dữ liệu cấu hình không nhạy cảm; Secret dành cho thông tin cần được kiểm soát chặt hơn như token, mật khẩu hoặc khóa. Hai tài nguyên này chỉ là nơi lưu và cung cấp dữ liệu trong Kubernetes. Ứng dụng vẫn phải được cấu hình để nhận dữ liệu, kiểm tra giá trị và áp dụng chúng đúng thời điểm.

Với một ứng dụng Spring chạy trong Kubernetes, dữ liệu từ ConfigMap hoặc Secret có thể đi vào container qua biến môi trường, file được mount hoặc API Kubernetes được thư viện trong ứng dụng gọi trực tiếp. Mỗi cách có yêu cầu vận hành khác nhau. Đặc biệt, thay đổi ConfigMap hoặc Secret không đồng nghĩa mọi bean Spring đang chạy đã dùng giá trị mới.

Bài học thuộc chương **Nền tảng Kubernetes** của module **SPRING_CLOUD_KUBERNETES**. Mục tiêu là chọn đúng loại tài nguyên, hiểu đường đi của dữ liệu vào container, bind dữ liệu vào cấu hình Spring Boot, thiết kế cập nhật và cấp quyền theo đúng thành phần sử dụng.

## 1. ConfigMap và Secret giải quyết vấn đề gì?

Image ứng dụng nên có thể chạy ở nhiều môi trường mà không cần build lại chỉ vì đổi tên dịch vụ, giới hạn xử lý hoặc credential. ConfigMap và Secret cho phép manifest cấp dữ liệu theo môi trường triển khai.

| Tài nguyên | Dữ liệu phù hợp | Ví dụ | Điều cần nhớ |
| --- | --- | --- | --- |
| ConfigMap | Cấu hình không nhạy cảm | Tên môi trường, URL nội bộ không có credential, giới hạn request | Không phải kho bí mật |
| Secret | Dữ liệu nhạy cảm cần kiểm soát truy cập | Mật khẩu, token, khóa API, chứng thư | Base64 trong manifest không phải mã hóa |
| Image | Mã và mặc định an toàn | File JAR, giá trị mặc định hợp lý | Không nên đóng credential vào image |
| Biến môi trường hoặc volume | Cách truyền dữ liệu vào container | Giá trị lấy từ ConfigMap/Secret | Ứng dụng cần đọc và áp dụng theo cách đã chọn |

ConfigMap và Secret là tài nguyên theo namespace. Một Pod thường chỉ tham chiếu tài nguyên trong cùng namespace, trừ khi có cơ chế khác được thiết kế rõ ràng. Vì vậy, cùng tên ConfigMap ở hai namespace có thể là hai cấu hình hoàn toàn khác nhau.

ConfigMap không làm cấu hình trở thành bất biến. Secret cũng không tự tạo ra cơ chế xoay vòng credential. Các chính sách lưu trữ, mã hóa tại nơi lưu, audit, RBAC và quy trình cập nhật của cluster quyết định mức bảo vệ thực tế.

## 2. Tạo ConfigMap cho dữ liệu không nhạy cảm

ConfigMap có thể lưu dữ liệu dạng key-value trong trường data. Mỗi giá trị trong data thường là chuỗi:

~~~yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: order-settings
  namespace: shop
data:
  APP_ENV: production
  ORDER_MAX_ITEMS: "20"
  CATALOG_BASE_URL: http://catalog-api
  CATALOG_TIMEOUT: 2s
~~~

Các giá trị số hoặc thời lượng vẫn nên được biểu diễn rõ ràng là chuỗi trong YAML. Ứng dụng sẽ chuyển đổi chúng sang kiểu int, Duration hoặc kiểu domain phù hợp. Giá trị hợp lệ theo YAML chưa chắc hợp lệ theo nghiệp vụ; ví dụ ORDER_MAX_ITEMS có thể parse được nhưng vẫn không được phép là số âm.

ConfigMap cũng có thể lưu một đoạn file trong data:

~~~yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: order-file-settings
  namespace: shop
data:
  application-extra.yaml: |
    order:
      max-items: 20
      catalog-timeout: 2s
    features:
      express-checkout: false
~~~

Cách lưu file hữu ích khi ứng dụng đã có cơ chế đọc file cấu hình. Tuy nhiên, cần xác định rõ ứng dụng đọc file một lần khi khởi động hay đọc lại trong lúc chạy. Kubernetes có thể cập nhật nội dung volume theo cơ chế của nó, nhưng không tự buộc một bean Spring đã khởi tạo phải nạp lại file.

Không nên đưa mật khẩu, token hoặc khóa riêng vào ConfigMap để tiện tham chiếu. Tách dữ liệu nhạy cảm sang Secret giúp mô hình quyền và audit rõ hơn, dù vẫn phải bảo vệ Secret ở các lớp lưu trữ, truyền tải, log và backup.

## 3. Tạo Secret và hiểu giới hạn bảo mật

Secret có thể dùng trường stringData để khai báo giá trị dạng chữ khi tạo tài nguyên. API server chuyển dữ liệu sang data theo định dạng phù hợp:

~~~yaml
apiVersion: v1
kind: Secret
metadata:
  name: order-credentials
  namespace: shop
type: Opaque
stringData:
  api-token: replace-at-deploy-time
  database-password: replace-at-deploy-time
~~~

Ví dụ trên chỉ là mẫu cấu trúc. Credential thật không nên được commit vào repository công khai hoặc ghi trực tiếp vào lịch sử shell. Quy trình triển khai có thể lấy giá trị từ hệ thống quản lý bí mật, công cụ tạo manifest hoặc cơ chế secret management phù hợp.

Nếu dùng data thay vì stringData, giá trị phải ở dạng Base64:

~~~yaml
apiVersion: v1
kind: Secret
metadata:
  name: order-credentials
  namespace: shop
type: Opaque
data:
  api-token: cmVwbGFjZS1hdC1kZXBsb3ktdGltZQ==
~~~

Base64 chỉ là cách biểu diễn dữ liệu, không phải mã hóa bảo mật. Người có quyền đọc Secret hoặc đọc dữ liệu đã giải mã trong Pod vẫn có thể lấy giá trị. Cần kiểm soát tối thiểu các quyền get, list và watch; tránh đưa Secret vào log, exception message, metric label hoặc endpoint debug.

Secret có nhiều type dành cho mục đích khác nhau, chẳng hạn TLS hoặc thông tin registry. Type giúp thể hiện ý nghĩa và kích hoạt một số hành vi hỗ trợ, nhưng không thay thế xác thực giá trị và chính sách bảo vệ.

Khi một credential bị lộ, đổi giá trị trong Secret chỉ là một bước. Cần xác định các container, client hoặc dịch vụ đã giữ bản sao cũ, thời điểm restart hoặc reload, thời gian credential cũ bị thu hồi và bằng chứng cho thấy tất cả replica đã dùng credential mới.

## 4. Cách 1: đưa từng key vào biến môi trường

Một key từ ConfigMap có thể được đưa vào biến môi trường bằng configMapKeyRef:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: order-api
  namespace: shop
spec:
  replicas: 2
  selector:
    matchLabels:
      app: order-api
  template:
    metadata:
      labels:
        app: order-api
    spec:
      containers:
        - name: order-api
          image: registry.example.com/shop/order-api:1.0.0
          env:
            - name: ORDER_MAX_ITEMS
              valueFrom:
                configMapKeyRef:
                  name: order-settings
                  key: ORDER_MAX_ITEMS
            - name: ORDER_CATALOG_TIMEOUT
              valueFrom:
                configMapKeyRef:
                  name: order-settings
                  key: CATALOG_TIMEOUT
            - name: ORDER_API_TOKEN
              valueFrom:
                secretKeyRef:
                  name: order-credentials
                  key: api-token
~~~

Với configMapKeyRef và secretKeyRef, manifest chỉ đưa từng key cần dùng vào container. Cách này làm rõ dependency của container và tránh đưa toàn bộ dữ liệu vào môi trường khi ứng dụng chỉ cần một phần.

Nếu key không tồn tại, hành vi phụ thuộc trường optional. Mặc định, tham chiếu bắt buộc bị thiếu có thể khiến Pod không được tạo container thành công. Có thể đặt optional: true cho dữ liệu thực sự tùy chọn, nhưng ứng dụng phải có mặc định và kiểm tra rõ ràng:

~~~yaml
env:
  - name: ORDER_PROMOTION_MODE
    valueFrom:
      configMapKeyRef:
        name: order-settings
        key: PROMOTION_MODE
        optional: true
~~~

optional không có nghĩa giá trị luôn là chuỗi rỗng theo mọi cách đọc. Ứng dụng cần xử lý trường hợp biến không tồn tại và phân biệt với giá trị rỗng nếu nghiệp vụ yêu cầu.

Với Secret, biến môi trường thường thuận tiện cho ứng dụng nhưng có các giới hạn:

- Giá trị nằm trong môi trường của tiến trình và có thể xuất hiện trong dump, chẩn đoán hoặc log do thư viện tạo ra.
- Container đang chạy không tự nhận giá trị mới khi ConfigMap hoặc Secret được sửa.
- Một tiến trình con có thể kế thừa biến môi trường nếu ứng dụng khởi chạy tiến trình đó.
- Không thể dùng cơ chế mount file để đọc lại dữ liệu nếu ứng dụng chỉ nhận environment lúc khởi động.

Khi dùng biến môi trường cho credential, hãy giới hạn quyền đọc process environment trong môi trường debug và không in toàn bộ environment khi chẩn đoán lỗi.

## 5. Cách 2: đưa nhiều key vào biến môi trường bằng envFrom

envFrom đưa toàn bộ key của ConfigMap hoặc Secret vào môi trường container:

~~~yaml
containers:
  - name: order-api
    image: registry.example.com/shop/order-api:1.0.0
    envFrom:
      - configMapRef:
          name: order-settings
      - secretRef:
          name: order-credentials
~~~

Cách này ngắn gọn nhưng tạo coupling rộng: thêm một key mới vào ConfigMap có thể làm xuất hiện một biến mới trong container; trùng tên giữa các nguồn có thể gây khó hiểu; và toàn bộ Secret được tham chiếu có khả năng đi vào môi trường tiến trình.

Có thể thêm prefix để tránh đụng tên:

~~~yaml
envFrom:
  - configMapRef:
      name: order-settings
    prefix: ORDER_
  - secretRef:
      name: order-credentials
    prefix: CRED_
~~~

Tên key phải phù hợp với quy tắc tên biến môi trường và cách Spring Boot phân giải property. Các key trong ConfigMap có ký tự không phù hợp có thể không trở thành biến môi trường như mong đợi. Với cấu hình quan trọng, tham chiếu từng key qua env thường dễ kiểm tra hơn envFrom.

Không nên dùng envFrom cho Secret lớn hoặc Secret chứa nhiều dữ liệu mà ứng dụng không cần. Cấp dữ liệu tối thiểu làm giảm phạm vi lộ khi process bị chẩn đoán hoặc bị khai thác.

## 6. Cách 3: mount ConfigMap và Secret thành file

Kubernetes có thể mount key của ConfigMap hoặc Secret thành file trong volume:

~~~yaml
volumes:
  - name: order-config
    configMap:
      name: order-file-settings
  - name: order-credentials
    secret:
      secretName: order-credentials
containers:
  - name: order-api
    image: registry.example.com/shop/order-api:1.0.0
    volumeMounts:
      - name: order-config
        mountPath: /etc/order
        readOnly: true
      - name: order-credentials
        mountPath: /var/run/order-secrets
        readOnly: true
~~~

Mỗi key thường được biểu diễn thành một file trong thư mục mount. Ví dụ key application-extra.yaml có thể xuất hiện ở /etc/order/application-extra.yaml, còn api-token có thể xuất hiện ở /var/run/order-secrets/api-token.

Có thể giới hạn hoặc đổi tên file bằng items:

~~~yaml
volumes:
  - name: order-config
    configMap:
      name: order-file-settings
      items:
        - key: application-extra.yaml
          path: spring/application.yaml
  - name: order-credentials
    secret:
      secretName: order-credentials
      items:
        - key: api-token
          path: api-token
~~~

Một số thuộc tính file như defaultMode có thể dùng để giới hạn quyền đọc file theo cơ chế của volume. Quyền Unix thực tế còn phụ thuộc user, group, securityContext và runtime. Không nên chỉ dựa vào mode mặc định để bảo vệ Secret.

Mount file phù hợp khi ứng dụng hoặc thư viện đã hỗ trợ đọc file và có thể reload. Với chứng thư TLS, file mount còn thuận tiện cho việc thay thế file theo chu kỳ xoay vòng, nhưng thư viện TLS vẫn phải reload context hoặc khởi động lại tiến trình để dùng chứng thư mới.

Không nên mount Secret vào filesystem rộng hơn cần thiết. Đặt mountPath riêng, readOnly: true và tránh cho phép ứng dụng ghi đè file credential.

## 7. Cập nhật ConfigMap và Secret có hiệu lực ra sao?

Cần phân biệt cách truyền dữ liệu:

| Cách truyền | Khi tài nguyên thay đổi | Ứng dụng có tự dùng giá trị mới không? |
| --- | --- | --- |
| Biến môi trường từ env hoặc envFrom | Environment của container đang chạy giữ giá trị cũ | Không; thường cần tạo Pod mới |
| Volume từ ConfigMap hoặc Secret | Nội dung volume có thể được kubelet cập nhật theo cơ chế của Kubernetes | Chỉ nếu ứng dụng đọc lại hoặc có watcher/reload |
| subPath mount | Không nên giả định file tự được cập nhật theo thay đổi nguồn | Thường cần mount/cập nhật theo thiết kế khác |
| Đọc trực tiếp qua Kubernetes API | Client có thể đọc giá trị mới khi truy vấn lại | Tùy cache, thời điểm đọc và cơ chế refresh |
| Spring refresh | Cập nhật property source không tự cập nhật mọi object | Chỉ các bean/thành phần hỗ trợ refresh mới đổi hành vi |

Thay đổi resource và thay đổi hành vi là hai sự kiện khác nhau. Một quy trình kiểm chứng có thể theo dõi:

1. ConfigMap hoặc Secret đã có giá trị mới.
2. Pod hoặc nguồn cấu hình đã nhận giá trị mới.
3. Ứng dụng đã đọc giá trị mới.
4. Thành phần nghiệp vụ đang xử lý request đã sử dụng giá trị mới.
5. Tất cả replica cần thiết đã chuyển trạng thái.

Với biến môi trường, rollout Deployment là cách phổ biến để tạo Pod mới:

~~~yaml
spec:
  template:
    metadata:
      annotations:
        config-revision: "2026-11-24-01"
~~~

Thay đổi trong Pod template tạo ra revision mới của Deployment. Annotation chỉ là ví dụ kích hoạt rollout; giá trị revision phải được quản lý bởi quy trình triển khai. Không nên sửa thủ công một Pod riêng lẻ rồi coi đó là cập nhật nhất quán cho Deployment.

Với volume, Kubernetes có thể cập nhật nội dung sau một khoảng thời gian. Ứng dụng cần đọc file theo cách an toàn, tránh đọc nửa chừng khi file đang được thay thế, và xác định hành vi khi file không hợp lệ. Một file mới không tự làm connection pool hoặc bean @ConfigurationProperties đã tạo thay đổi.

## 8. Bind dữ liệu vào Spring Boot

Spring Boot có thể bind property từ environment hoặc file theo quy tắc tên. Ví dụ class thuộc tính:

~~~java
import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "order")
public class OrderProperties {

    private int maxItems = 20;
    private Duration catalogTimeout = Duration.ofSeconds(2);

    public int getMaxItems() {
        return maxItems;
    }

    public void setMaxItems(int maxItems) {
        this.maxItems = maxItems;
    }

    public Duration getCatalogTimeout() {
        return catalogTimeout;
    }

    public void setCatalogTimeout(Duration catalogTimeout) {
        this.catalogTimeout = catalogTimeout;
    }
}
~~~

Khi dùng biến môi trường, tên ORDER_MAX_ITEMS thường được ánh xạ tới order.max-items theo quy tắc relaxed binding của Spring Boot. Việc class có getter và setter chỉ hỗ trợ bind; nó không tự tạo khả năng refresh.

Ở lớp khởi động, cần đăng ký ConfigurationProperties, chẳng hạn bằng @ConfigurationPropertiesScan hoặc cơ chế đăng ký tương ứng của phiên bản Spring Boot:

~~~java
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@ConfigurationPropertiesScan
@SpringBootApplication
public class OrderApplication {
}
~~~

Nên kiểm tra dữ liệu khi bind hoặc sau bind:

- maxItems phải lớn hơn 0 và có giới hạn tối đa hợp lý.
- catalogTimeout phải dương và không vượt ngưỡng hệ thống.
- URL phải đúng scheme, hostname và port được phép.
- Token không được kiểm tra bằng cách ghi giá trị thật vào log.
- Nếu property bắt buộc thiếu, ứng dụng nên fail fast với thông báo không tiết lộ bí mật.

Có thể dùng ConfigMap dạng file làm nguồn application.yaml, nhưng cần tránh trộn nhiều nguồn mà không biết thứ tự ưu tiên. Khi một property xuất hiện ở image, environment, file mount và nguồn Kubernetes API, hãy lập bảng nguồn và thứ tự ưu tiên trước khi vận hành.

## 9. Tích hợp trực tiếp với Kubernetes API và Spring Cloud Kubernetes

Một ứng dụng Spring có thể dùng tích hợp Spring Cloud Kubernetes để đọc ConfigMap hoặc Secret qua Kubernetes API và đưa dữ liệu vào Spring Environment. Cách này khác với việc Kubernetes inject biến môi trường hoặc mount volume:

| Khía cạnh | Injection của Kubernetes | Tích hợp đọc API trong ứng dụng |
| --- | --- | --- |
| Mã đọc | Container runtime/kubelet cung cấp dữ liệu | Thư viện trong JVM gọi API server |
| Danh tính API | Có thể không cần mount token | Cần ServiceAccount, token hoặc cơ chế xác thực tương ứng |
| RBAC | Không cần quyền đọc API chỉ để dùng env/volume đã inject | Cần quyền trên ConfigMap/Secret được đọc |
| Cập nhật | Theo semantics của env/volume | Theo thời điểm đọc, cache và cơ chế watch/refresh |
| Ảnh hưởng lỗi | Container có thể khởi động với dữ liệu đã cấp | Ứng dụng có thể phụ thuộc API server lúc khởi động hoặc runtime |

Nếu ứng dụng chỉ dùng envFrom hoặc volume, không nên cấp quyền đọc ConfigMap/Secret qua API chỉ vì nó chạy trong Kubernetes. Nếu ứng dụng dùng Spring Cloud Kubernetes để đọc trực tiếp, hãy cấp quyền cho đúng ServiceAccount và đúng namespace.

Một Role chỉ có get có thể phù hợp với client đọc một resource đã biết tên. Cơ chế theo dõi thay đổi thường cần list và watch theo tài nguyên, tùy implementation. Không suy ra bộ quyền từ tên starter; hãy kiểm tra hành vi client và giới hạn quyền theo nhu cầu.

Secret thường cần chính sách chặt hơn ConfigMap. Một ứng dụng chỉ cần ORDER_MAX_ITEMS không nên có quyền đọc toàn bộ Secret của namespace. Tách Role, ServiceAccount hoặc workload theo trách nhiệm giúp giảm phạm vi khi có lỗi.

## 10. Configuration Watcher và cập nhật dữ liệu

Configuration Watcher triển khai riêng có thể theo dõi thay đổi ConfigMap hoặc Secret rồi gửi tín hiệu đến ứng dụng theo cơ chế đã chọn. Watcher không tự sửa bộ nhớ của JVM ứng dụng. Ứng dụng phải có phần nhận tín hiệu và cơ chế áp dụng giá trị mới.

Luồng cần được kiểm chứng:

~~~text
ConfigMap hoặc Secret đổi
          |
          v
Watcher hoặc client theo dõi nhận sự kiện
          |
          v
Xác định ứng dụng và replica đích
          |
          v
Gửi tín hiệu cập nhật theo cơ chế đã cấu hình
          |
          v
Ứng dụng đọc lại nguồn cấu hình
          |
          v
Bean hoặc thành phần hỗ trợ refresh dùng giá trị mới
~~~

Nếu ứng dụng vẫn nhận cấu hình bằng biến môi trường được đọc tại startup, Watcher không thể làm biến môi trường của container đang chạy thay đổi. Khi đó, rollout hoặc cơ chế nạp khác là phương án phù hợp hơn.

Nếu Secret chứa credential được thay đổi, cần tránh tạo log chứa giá trị cũ và mới. Chỉ log metadata an toàn như tên resource, revision hoặc thời điểm xử lý. Endpoint quản trị nhận refresh phải được xác thực, giới hạn mạng và bảo vệ khỏi người dùng cuối.

## 11. RBAC và ServiceAccount

Nếu Pod chỉ dùng giá trị đã được inject qua env hoặc volume, nó có thể không cần gọi Kubernetes API cho phần cấu hình. Có thể tắt automount token cho Pod không cần API:

~~~yaml
spec:
  serviceAccountName: order-api
  automountServiceAccountToken: false
~~~

serviceAccountName ở đây vẫn có thể được dùng cho các mục đích khác, nhưng automountServiceAccountToken: false tránh tự động đưa token API vào filesystem của container. Nếu ứng dụng dùng client in-cluster để đọc ConfigMap hoặc Secret, không được tắt token mà không thay bằng cơ chế xác thực tương ứng.

Ví dụ quyền đọc một ConfigMap đã biết tên:

~~~yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: order-config-reader
  namespace: shop
---
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: order-settings-reader
  namespace: shop
rules:
  - apiGroups: [""]
    resources: ["configmaps"]
    resourceNames: ["order-settings"]
    verbs: ["get"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: order-settings-reader
  namespace: shop
subjects:
  - kind: ServiceAccount
    name: order-config-reader
    namespace: shop
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: Role
  name: order-settings-reader
~~~

Ví dụ trên không cấp quyền đọc Secret và không phải bộ quyền cho mọi kiểu watch. Nếu ứng dụng đọc Secret, hãy thêm đúng resource và phạm vi cần thiết sau khi xác định nhu cầu. Không cấp quyền trên mọi Secret chỉ để tránh lỗi triển khai.

Nếu ConfigMap hoặc Secret được tham chiếu trong Pod spec qua env hoặc volume, kubelet và control plane xử lý việc cung cấp dữ liệu theo cơ chế Kubernetes. Điều đó không có nghĩa ứng dụng được phép tự gọi API để liệt kê các resource khác.

## 12. Secret trong log, debug và backup

Dữ liệu nhạy cảm có thể lộ ở những nơi không nằm trong manifest:

- Log startup in toàn bộ environment hoặc cấu hình đã bind.
- Exception chứa URL có username/password hoặc token trong query string.
- Actuator endpoint hoặc endpoint debug trả về property source.
- Thread dump, heap dump, profiling snapshot hoặc crash dump.
- Metric label chứa mã token hoặc tên credential kèm giá trị.
- Backup, artifact CI/CD, file tạm và lịch sử shell.
- Container image hoặc layer được tạo trong một bước build rồi xóa ở bước sau.

Ứng dụng nên che giá trị nhạy cảm khi log, dùng tên key thay vì value trong chẩn đoán và giới hạn endpoint quản trị. Quyền đọc Secret trong Kubernetes cần kết hợp với quyền truy cập node, quyền exec vào Pod và chính sách lưu backup.

Không nên kiểm tra Secret bằng cách in ra stdout của container. Nếu cần xác minh, kiểm tra tên key, độ dài được kiểm soát hoặc fingerprint không thể khôi phục giá trị; tránh dùng fingerprint nếu nó trở thành cách xác thực bí mật yếu.

## 13. Ví dụ đầy đủ cho một ứng dụng dùng env và volume

Mẫu sau minh họa ConfigMap cho cấu hình không nhạy cảm, Secret cho token và hai cách sử dụng khác nhau trong một Pod. Trong hệ thống thực tế, nên chọn cách phù hợp cho từng dữ liệu thay vì đưa cùng một giá trị qua nhiều đường.

~~~yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: order-settings
  namespace: shop
data:
  ORDER_MAX_ITEMS: "20"
  ORDER_CATALOG_TIMEOUT: 2s
---
apiVersion: v1
kind: Secret
metadata:
  name: order-credentials
  namespace: shop
type: Opaque
stringData:
  api-token: replace-at-deploy-time
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: order-api
  namespace: shop
spec:
  replicas: 2
  selector:
    matchLabels:
      app: order-api
  template:
    metadata:
      labels:
        app: order-api
    spec:
      automountServiceAccountToken: false
      containers:
        - name: order-api
          image: registry.example.com/shop/order-api:1.0.0
          env:
            - name: ORDER_MAX_ITEMS
              valueFrom:
                configMapKeyRef:
                  name: order-settings
                  key: ORDER_MAX_ITEMS
            - name: ORDER_CATALOG_TIMEOUT
              valueFrom:
                configMapKeyRef:
                  name: order-settings
                  key: ORDER_CATALOG_TIMEOUT
          volumeMounts:
            - name: api-token
              mountPath: /var/run/order-secrets
              readOnly: true
      volumes:
        - name: api-token
          secret:
            secretName: order-credentials
            items:
              - key: api-token
                path: api-token
~~~

Trong mẫu này, giới hạn và timeout đi qua biến môi trường; token đi qua file riêng. Ứng dụng phải biết token ở /var/run/order-secrets/api-token và phải có cơ chế đọc file an toàn. Token không được in khi khởi động.

Nếu muốn đổi ORDER_MAX_ITEMS trong lúc chạy, cần rollout Pod mới hoặc chuyển sang một nguồn và cơ chế refresh được thiết kế cho việc đó. Nếu muốn xoay token, cần đọc lại file hoặc khởi động lại ứng dụng theo khả năng của client sử dụng token. Manifest không tự bảo đảm cả hai loại dữ liệu được cập nhật cùng thời điểm.

## 14. Chọn cách truyền dữ liệu theo nhu cầu

| Câu hỏi | Lựa chọn thường phù hợp |
| --- | --- |
| Giá trị chỉ cần khi khởi động? | Biến môi trường hoặc file cùng rollout |
| Ứng dụng đã hỗ trợ đọc file cấu hình? | Mount ConfigMap hoặc Secret thành file |
| Ứng dụng chỉ cần một vài key? | env với configMapKeyRef hoặc secretKeyRef |
| Ứng dụng cần nhiều key đồng nhất? | envFrom có prefix hoặc file cấu hình |
| Dữ liệu cần thay đổi khi đang chạy? | Cơ chế đọc lại/refresh rõ ràng; không dựa vào env |
| Cần gọi Kubernetes API trực tiếp? | Spring Cloud Kubernetes với RBAC tối thiểu |
| Dữ liệu là credential? | Secret, quyền hẹp, không log, kế hoạch xoay vòng |
| Cần cùng một cấu hình cho nhiều replica? | Resource dùng chung, kiểm chứng từng replica sau cập nhật |

Một quyết định tốt phải mô tả được nguồn dữ liệu, cách ứng dụng nhận dữ liệu, thời điểm có hiệu lực và cách thu hồi hoặc đổi dữ liệu. Chỉ nói “dùng ConfigMap” chưa cho biết ứng dụng nhận qua env, volume hay API.

## 15. Chẩn đoán lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Kiểm tra trước |
| --- | --- | --- |
| Pod không tạo được container | ConfigMap/Secret bắt buộc hoặc key bị thiếu | Tên resource, namespace, tên key, trường optional |
| Biến môi trường rỗng hoặc không tồn tại | Tên key không đúng hoặc envFrom không phù hợp | Manifest Pod, key thực tế, quy tắc tên biến |
| File mount không có | Volume hoặc volumeMount sai | Tên volume, mountPath, key và quyền đọc |
| Đổi ConfigMap nhưng app vẫn dùng giá trị cũ | Dùng environment hoặc bean chưa refresh | Cách cấp dữ liệu, thời điểm tạo Pod, cơ chế reload |
| Ứng dụng nhận 403 khi đọc API | ServiceAccount hoặc RoleBinding sai | Danh tính Pod, namespace, verbs và resources |
| Secret bị lộ trong log | Logging cấu hình hoặc debug quá rộng | Startup log, exception, Actuator, dump |
| Watcher Running nhưng không đổi hành vi | App không nhận tín hiệu hoặc bean không refresh | Sự kiện, đường truyền, endpoint, bean và replica |
| Config parse được nhưng app không chạy đúng | Giá trị sai theo nghiệp vụ | Validation, default, đơn vị thời gian, giới hạn |

Khi điều tra, hãy xác định trước dữ liệu đang đi theo đường nào. Không nên sửa RBAC nếu ứng dụng chỉ dùng biến môi trường và lỗi thực tế là key ConfigMap bị viết sai. Cũng không nên restart mọi Pod nếu ứng dụng cần đọc lại file nhưng chưa có reload; restart chỉ che khuất thiếu sót trong thiết kế cập nhật.

## 16. Checklist triển khai

Trước khi triển khai ứng dụng Spring với ConfigMap và Secret, hãy kiểm tra:

- Dữ liệu không nhạy cảm và dữ liệu nhạy cảm được tách đúng loại tài nguyên.
- Secret không chứa credential thật trong repository hoặc log CI/CD.
- Tên resource và namespace trong Pod spec chính xác.
- Key được tham chiếu tồn tại và có hành vi rõ khi bị thiếu.
- Biến môi trường có tên phù hợp với property mà Spring Boot bind.
- File mount có đường dẫn, quyền và user/group đúng.
- Ứng dụng không log Secret hoặc toàn bộ environment.
- Đã quyết định dữ liệu có hiệu lực lúc startup hay có thể thay đổi lúc chạy.
- Có rollout hoặc cơ chế refresh phù hợp với cách truyền dữ liệu.
- Nếu đọc API trực tiếp, ServiceAccount và RBAC chỉ có quyền cần thiết.
- automountServiceAccountToken được tắt khi Pod không cần gọi Kubernetes API.
- Có kế hoạch xoay vòng credential và thu hồi giá trị cũ.
- Có bằng chứng kiểm tra giá trị mới trên từng replica sau cập nhật.
- Endpoint quản trị và cơ chế refresh được xác thực, giới hạn mạng.
- Probe không gây restart hàng loạt chỉ vì cấu hình hoặc phụ thuộc tạm thời lỗi.

## 17. Tự kiểm tra

1. Khi nào dùng ConfigMap và khi nào dùng Secret?
2. Vì sao Base64 trong trường data của Secret không phải là mã hóa?
3. Khác biệt vận hành giữa env, envFrom và volume mount là gì?
4. Vì sao sửa ConfigMap không làm biến môi trường của container đang chạy đổi theo?
5. Nếu file Secret mount đã đổi, tại sao bean Spring vẫn có thể giữ credential cũ?
6. Khi ứng dụng dùng Spring Cloud Kubernetes để đọc Secret qua API, ServiceAccount cần những quyền nào?
7. Vì sao Pod chỉ dùng ConfigMap qua env có thể tắt automountServiceAccountToken?
8. Khi nào Configuration Watcher hữu ích, và điều gì vẫn phải được cài trong ứng dụng?
9. Bằng chứng nào cho thấy mọi replica đã dùng cấu hình mới?
10. Những vị trí nào có thể làm Secret lộ ngoài manifest?

ConfigMap và Secret chỉ là một phần của đường đi cấu hình. Hãy bắt đầu từ nhu cầu của ứng dụng: dữ liệu nào cần, dữ liệu được nhận bằng env, file hay API, có hiệu lực khi nào, và cách đổi hoặc thu hồi ra sao. Với Spring Cloud Kubernetes, chỉ thêm tích hợp đọc API hoặc Configuration Watcher khi nó giải quyết một nhu cầu cụ thể; đồng thời giữ RBAC, log, probe và quy trình cập nhật trong cùng một thiết kế vận hành.

