# Tạo dữ liệu ConfigMap và Secret phục vụ thử nghiệm

Trong chương **Phát triển cục bộ** của module **SPRING_CLOUD_KUBERNETES**, dữ liệu thử nghiệm cần dễ tạo lại, dễ phân biệt phiên bản và đủ rõ để biết ứng dụng đang dùng giá trị nào. Bài này xây dựng một bộ ConfigMap và Secret cho ứng dụng Spring, kiểm chứng dữ liệu trong Kubernetes rồi đưa chúng vào một Pod.

Bộ dữ liệu này có thể dùng tiếp khi thử cập nhật cấu hình, Configuration Watcher hoặc phân quyền đọc tài nguyên. DiscoveryClient và Spring Cloud LoadBalancer không phải điều kiện để nạp cấu hình; hãy bật từng tính năng Spring Cloud Kubernetes theo nhu cầu của phép thử.

## 1. Kết quả cần đạt

Sau bài học, bạn có thể:

- Chọn đúng dữ liệu cho ConfigMap và Secret, đặt tên resource và key nhất quán.
- Tạo fixture bằng manifest UTF-8 hoặc sinh manifest từ `kubectl`.
- Phân biệt `Secret.stringData` với `Secret.data` và phát hiện lỗi thừa xuống dòng.
- Mount dữ liệu vào ứng dụng Spring Boot bằng `configtree:` mà không cấp quyền gọi API cho ứng dụng.
- Chứng minh sự khác nhau giữa cập nhật resource, cập nhật dữ liệu được mount và cập nhật giá trị mà bean đang giữ.
- Tạo tình huống lỗi thiếu resource, thiếu key, sai kiểu dữ liệu; sau đó phục hồi bộ dữ liệu chuẩn.

Fixture là bộ dữ liệu đầu vào đã biết trước, có thể tái tạo cho mỗi lần chạy. Trong bài này, **mọi token đều là chuỗi giả**, không kết nối được tới dịch vụ thật.

## 2. Thiết kế bộ dữ liệu trước khi tạo resource

Dùng một namespace dành riêng cho bài:

| Thành phần | Giá trị trong lab | Mục đích |
| --- | --- | --- |
| Namespace | `sck-data-lab` | Cô lập dữ liệu thử nghiệm |
| ConfigMap | `catalog-settings` | Chứa cấu hình công khai |
| Secret | `catalog-credentials` | Chứa token giả và dấu hiệu phiên bản |
| Deployment | `catalog-config-probe` | Đọc và báo trạng thái cấu hình |
| Nhãn chung | `app.kubernetes.io/part-of: sck-data-lab` | Tìm các tài nguyên của lab |

Hợp đồng dữ liệu của ứng dụng:

| Property Spring | Nguồn | Giá trị ban đầu | Ý nghĩa |
| --- | --- | --- | --- |
| `demo.message` | ConfigMap | `Xin chào từ ConfigMap` | Kiểm tra chuỗi Unicode |
| `demo.limit` | ConfigMap | `"10"` | Kiểm tra chuyển chuỗi sang số |
| `demo.enabled` | ConfigMap | `"true"` | Kiểm tra chuyển sang boolean |
| `demo.config.revision` | ConfigMap | `config-v1` | Dấu hiệu phiên bản cấu hình |
| `demo.partner.url` | ConfigMap | `http://partner-mock:8080` | URL giả, ứng dụng mẫu không gọi |
| `demo.partner.token` | Secret | `local-only-token-v1` | Dữ liệu giả mô phỏng thông tin xác thực |
| `demo.secret.revision` | Secret | `secret-v1` | Dấu hiệu phiên bản, không phải bí mật |

`demo.secret.revision` giúp quan sát lần nạp dữ liệu mà không trả token qua HTTP. Marker này chỉ chứng minh marker đã được nạp; nó không thay thế phép thử xác thực với đối tác.

ConfigMap và Secret là tài nguyên có namespace. Khi tham chiếu bằng volume hoặc `valueFrom` trong Pod, resource cần nằm trong cùng namespace với Pod. Hai loại resource có thể có cùng tên, nhưng bài này dùng tên riêng để dễ đọc kết quả.

## 3. Hiểu cấu trúc ConfigMap và Secret

### ConfigMap

`data` là ánh xạ từ key tới chuỗi UTF-8. Vì vậy, số và boolean ở lớp dữ liệu Kubernetes phải được đặt trong dấu nháy:

~~~yaml
data:
  demo.limit: "10"
  demo.enabled: "true"
~~~

Spring sẽ chuyển chuỗi sang kiểu phù hợp khi đọc property. Nếu viết `demo.limit: 10` trực tiếp trong `data`, YAML tạo ra số thay vì chuỗi và có thể bị Kubernetes từ chối.

Key có thể chứa chữ, số, dấu `-`, `_` và `.`. Dấu chấm trong `demo.partner.url` là một phần của tên key; ConfigMap không tự hiểu đó là một object Java. ConfigMap có giới hạn dung lượng 1 MiB và phù hợp với cấu hình nhỏ. Xem [Kubernetes ConfigMaps](https://kubernetes.io/docs/concepts/configuration/configmap/).

### Secret

Với Secret loại `Opaque`, có hai cách nhập dữ liệu:

| Field | Nội dung trong manifest | Khi nào dùng |
| --- | --- | --- |
| `stringData` | Chuỗi thông thường | Viết fixture giả dễ đọc |
| `data` | Chuỗi base64 của dữ liệu | Dữ liệu đã được công cụ mã hóa base64 |

API chuyển `stringData` thành `data`; đọc lại resource không thấy nguyên field `stringData` là hành vi bình thường. Nếu một key có mặt trong cả hai field, `stringData` được ưu tiên. Lab dùng một cách cho mỗi manifest để tránh nhập nhằng.

`stringData` không phù hợp với mọi quy trình server-side apply; các lệnh `apply` của lab dùng chế độ client-side thông thường. Xem [quản lý Secret bằng manifest](https://kubernetes.io/docs/tasks/configmap-secret/managing-secret-using-config-file/).

Base64 là cách biểu diễn dữ liệu, không phải mã hóa bảo mật. Khả năng bảo vệ Secret còn phụ thuộc phân quyền, cấu hình lưu trữ và cách ứng dụng sử dụng. Vì vậy, bộ fixture chỉ chứa token giả, kể cả khi manifest được lưu cùng tài liệu thực hành.

## 4. Tạo bộ fixture bằng manifest

Cần một cluster thử nghiệm đang hoạt động và `kubectl` truy cập được. Các ví dụ dùng PowerShell.

Chọn context phù hợp với môi trường của bạn; `kind-sck-dev` dưới đây là ví dụ:

~~~powershell
$kubeContext = "kind-sck-dev"
$namespace = "sck-data-lab"

kubectl config get-contexts
kubectl --context $kubeContext cluster-info
kubectl --context $kubeContext get nodes
~~~

Lưu nội dung sau thành `fixtures.yaml` bằng UTF-8 trong thư mục thực hành:

~~~yaml
apiVersion: v1
kind: Namespace
metadata:
  name: sck-data-lab
  labels:
    app.kubernetes.io/part-of: sck-data-lab
---
apiVersion: v1
kind: ConfigMap
metadata:
  name: catalog-settings
  namespace: sck-data-lab
  labels:
    app.kubernetes.io/part-of: sck-data-lab
data:
  demo.message: "Xin chào từ ConfigMap"
  demo.limit: "10"
  demo.enabled: "true"
  demo.config.revision: "config-v1"
  demo.partner.url: "http://partner-mock:8080"
---
apiVersion: v1
kind: Secret
metadata:
  name: catalog-credentials
  namespace: sck-data-lab
  labels:
    app.kubernetes.io/part-of: sck-data-lab
type: Opaque
stringData:
  demo.partner.token: "local-only-token-v1"
  demo.secret.revision: "secret-v1"
~~~

Kiểm tra cú pháp rồi áp dụng:

~~~powershell
kubectl --context $kubeContext apply --dry-run=client -f .\fixtures.yaml
if ($LASTEXITCODE -ne 0) { throw "Manifest fixture không hợp lệ." }

kubectl --context $kubeContext apply -f .\fixtures.yaml
if ($LASTEXITCODE -ne 0) { throw "Không tạo được fixture." }
~~~

Dry-run giúp kiểm tra cấu trúc nhưng không chứng minh workload sẽ đọc được dữ liệu. Việc áp dụng nhiều document cũng không phải một giao dịch nguyên tử: cần kiểm tra cả ConfigMap và Secret sau khi chạy.

Giữ `fixtures.yaml` làm nguồn chuẩn. Sau một phép thử phá dữ liệu, dùng lại manifest này để đưa lab về trạng thái mong muốn.

## 5. Đọc lại dữ liệu và xác minh đúng byte

Trước hết, kiểm tra danh sách resource:

~~~powershell
kubectl --context $kubeContext -n $namespace get configmap,secret -l app.kubernetes.io/part-of=sck-data-lab
~~~

Đọc ConfigMap và kiểm tra từng giá trị quan trọng:

~~~powershell
$configText = kubectl --context $kubeContext -n $namespace get configmap catalog-settings -o json
if ($LASTEXITCODE -ne 0) { throw "Không đọc được ConfigMap." }

$config = ($configText -join [Environment]::NewLine) | ConvertFrom-Json

[pscustomobject]@{
    Name = $config.metadata.name
    Namespace = $config.metadata.namespace
    Message = $config.data.'demo.message'
    Limit = $config.data.'demo.limit'
    Enabled = $config.data.'demo.enabled'
    Revision = $config.data.'demo.config.revision'
}
~~~

Dấu nháy ở `$config.data.'demo.message'` rất quan trọng: nó truy cập một key chứa dấu chấm, thay vì một chuỗi object lồng nhau.

Với Secret, lấy dữ liệu vào biến rồi chỉ hiển thị tên key và kết quả so sánh:

~~~powershell
$secretText = kubectl --context $kubeContext -n $namespace get secret catalog-credentials -o json
if ($LASTEXITCODE -ne 0) { throw "Không đọc được Secret." }

$secret = ($secretText -join [Environment]::NewLine) | ConvertFrom-Json
$encodedToken = $secret.data.'demo.partner.token'
$decodedToken = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($encodedToken))

[pscustomobject]@{
    Name = $secret.metadata.name
    Namespace = $secret.metadata.namespace
    Type = $secret.type
    Keys = ($secret.data.PSObject.Properties.Name -join ", ")
    TokenMatchesFixture = ($decodedToken -ceq "local-only-token-v1")
}

Remove-Variable decodedToken, encodedToken, secret, secretText
~~~

Kết quả mong đợi là `TokenMatchesFixture = True`. Lệnh giải mã này dành cho token giả trong lab. Với dữ liệu thật, tránh xuất toàn bộ Secret, ghi token vào log hoặc đưa kết quả giải mã vào báo cáo.

Lỗi thường gặp là token có thêm ký tự xuống dòng. Chẳng hạn `"local-only-token-v1"` và cùng chuỗi đó cộng `LF` là hai giá trị khác nhau. Khi tạo Secret từ file, nội dung file được dùng theo byte; khi dùng YAML block scalar, `|` và `|-` có cách giữ xuống dòng cuối khác nhau. Xem [quản lý Secret bằng kubectl](https://kubernetes.io/docs/tasks/configmap-secret/managing-secret-using-kubectl/).

## 6. Chuẩn bị ứng dụng Spring để quan sát dữ liệu

Dùng một dự án Spring Boot Maven có Spring Web, Maven Wrapper và `spring-boot-maven-plugin`. Giữ bộ phiên bản phù hợp với module đang học. Ứng dụng mẫu không cần Spring Cloud Kubernetes Config để đọc file được Kubernetes mount.

Ví dụ lớp chính, đặt trong package phù hợp:

~~~java
package com.example.configlab;

import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.core.env.Environment;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class ConfigProbeApplication {

    private final String message;
    private final int limit;
    private final boolean enabled;
    private final String configRevision;
    private final String secretRevision;
    private final String partnerUrl;
    private final boolean tokenConfigured;

    public ConfigProbeApplication(Environment environment) {
        this.message = environment.getRequiredProperty("demo.message");
        this.limit = environment.getRequiredProperty("demo.limit", Integer.class);
        this.enabled = environment.getRequiredProperty("demo.enabled", Boolean.class);
        this.configRevision =
                environment.getRequiredProperty("demo.config.revision");
        this.secretRevision =
                environment.getRequiredProperty("demo.secret.revision");
        this.partnerUrl = environment.getRequiredProperty("demo.partner.url");

        String token = environment.getRequiredProperty("demo.partner.token");
        if (token.isBlank()) {
            throw new IllegalStateException("Thiếu token thử nghiệm");
        }
        if (limit < 1) {
            throw new IllegalStateException("demo.limit phải lớn hơn 0");
        }
        this.tokenConfigured = true;
    }

    public static void main(String[] args) {
        SpringApplication.run(ConfigProbeApplication.class, args);
    }

    @GetMapping("/lab/config")
    public Map<String, Object> config() {
        return Map.of(
                "message", message,
                "limit", limit,
                "enabled", enabled,
                "configRevision", configRevision,
                "secretRevision", secretRevision,
                "partnerUrl", partnerUrl,
                "tokenConfigured", tokenConfigured,
                "pod", System.getenv().getOrDefault("POD_NAME", "local-process"));
    }
}
~~~

Nếu dự án đã có lớp main, giữ lớp đó và đặt phần endpoint vào một controller được component scan. Ví dụ dùng constructor để chụp giá trị lúc khởi tạo bean; đây là hành vi có chủ đích cho phép thử cập nhật bên dưới.

Endpoint chỉ trả các giá trị công khai, marker và trạng thái có token. Nó không trả token, không gọi `partner-mock` và không chứng minh token được một dịch vụ bên ngoài chấp nhận.

Không đặt các property `demo.*` với giá trị dự phòng trong cấu hình đóng gói cho lab này. Nhờ `getRequiredProperty` và kiểm tra kiểu dữ liệu, fixture thiếu hoặc sai sẽ được phát hiện rõ khi khởi động.

Build image mẫu:

~~~powershell
$image = "docker.io/library/catalog-config-probe:dev-001"

.\mvnw.cmd clean spring-boot:build-image "-Dspring-boot.build-image.imageName=$image" "-Dspring-boot.build-image.publish=false"
if ($LASTEXITCODE -ne 0) { throw "Build image thất bại." }
~~~

Với kind có cluster tên `sck-dev`:

~~~powershell
kind load docker-image $image --name sck-dev
~~~

Hoặc với minikube, dùng đúng profile của bạn:

~~~powershell
minikube -p sck-dev image load $image --daemon
~~~

Chọn một nhánh tương ứng với cluster đã chọn, kiểm tra lệnh load thành công và bảo đảm image có trên các node có thể nhận Pod. Quy trình tạo OCI image bằng Maven Plugin được mô tả tại [Spring Boot Packaging OCI Images](https://docs.spring.io/spring-boot/maven-plugin/build-image.html).

## 7. Mount dữ liệu và import bằng configtree

Với key phẳng dạng `demo.message`, Kubernetes có thể tạo file tên `demo.message` trong volume. Spring Boot `configtree:` ánh xạ tên file thành property và nội dung file thành giá trị.

Đường đi của dữ liệu trong lab:

~~~mermaid
flowchart LR
    CM["ConfigMap catalog-settings"] --> CV["/etc/lab/config/demo.*"]
    SC["Secret catalog-credentials"] --> SV["/etc/lab/secret/demo.*"]
    CV --> IMP["Spring Boot configtree import"]
    SV --> IMP
    IMP --> ENV["Spring Environment"]
    ENV --> BEAN["Giá trị chụp lúc tạo bean"]
    BEAN --> HTTP["GET /lab/config: marker và trạng thái"]
~~~

Không cần tự giải mã base64 trong ứng dụng khi đọc Secret qua volume: file đã chứa dữ liệu sử dụng được. Base64 xuất hiện ở lớp biểu diễn `Secret.data` của API.

Lưu manifest sau thành `workload.yaml`:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: catalog-config-probe
  namespace: sck-data-lab
  labels:
    app.kubernetes.io/part-of: sck-data-lab
spec:
  replicas: 1
  selector:
    matchLabels:
      app: catalog-config-probe
  template:
    metadata:
      labels:
        app: catalog-config-probe
        app.kubernetes.io/part-of: sck-data-lab
    spec:
      automountServiceAccountToken: false
      containers:
        - name: app
          image: docker.io/library/catalog-config-probe:dev-001
          imagePullPolicy: Never
          ports:
            - name: http
              containerPort: 8080
          env:
            - name: SPRING_APPLICATION_NAME
              value: catalog-config-probe
            - name: SPRING_CONFIG_IMPORT
              value: "configtree:/etc/lab/config/,configtree:/etc/lab/secret/"
            - name: POD_NAME
              valueFrom:
                fieldRef:
                  fieldPath: metadata.name
          volumeMounts:
            - name: settings
              mountPath: /etc/lab/config
              readOnly: true
            - name: credentials
              mountPath: /etc/lab/secret
              readOnly: true
          readinessProbe:
            httpGet:
              path: /lab/config
              port: http
            periodSeconds: 5
          resources:
            requests:
              cpu: 100m
              memory: 256Mi
            limits:
              cpu: "1"
              memory: 768Mi
      volumes:
        - name: settings
          configMap:
            name: catalog-settings
            items:
              - key: demo.message
                path: demo.message
              - key: demo.limit
                path: demo.limit
              - key: demo.enabled
                path: demo.enabled
              - key: demo.config.revision
                path: demo.config.revision
              - key: demo.partner.url
                path: demo.partner.url
        - name: credentials
          secret:
            secretName: catalog-credentials
            items:
              - key: demo.partner.token
                path: demo.partner.token
              - key: demo.secret.revision
                path: demo.secret.revision
~~~

Các điểm cần giữ nguyên khi thử:

- Hai đường dẫn `configtree:` kết thúc bằng `/`, trỏ tới đúng thư mục được mount.
- Không có `optional:` cho import và không bật `optional` cho volume: fixture là đầu vào bắt buộc.
- `items` liệt kê rõ key cần dùng; sai tên key sẽ trở thành lỗi có thể quan sát.
- Mount cả thư mục, không dùng `subPath`, để giữ cơ chế cập nhật volume của Kubernetes.
- `automountServiceAccountToken: false` phù hợp với ứng dụng chỉ đọc file. Kubelet thiết lập volume từ PodSpec; tiến trình ứng dụng không tự gọi Kubernetes API.
- `imagePullPolicy: Never` yêu cầu đã nạp image vào node trước đó.

Quy tắc tên file có dấu chấm và import configuration tree được giải thích trong [Spring Boot Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.files.configtree).

Triển khai:

~~~powershell
kubectl --context $kubeContext apply -f .\workload.yaml
if ($LASTEXITCODE -ne 0) { throw "Không tạo được workload." }

kubectl --context $kubeContext -n $namespace rollout status deployment/catalog-config-probe --timeout=300s
kubectl --context $kubeContext -n $namespace get pods -l app=catalog-config-probe -o wide
~~~

Lab giả định cổng ứng dụng là 8080 và endpoint thử nghiệm không yêu cầu xác thực. Nếu dự án có Spring Security, context path hoặc cổng khác, cần điều chỉnh endpoint và readiness probe cho khớp.

## 8. Xác nhận ứng dụng đã nhận fixture

Giữ lệnh port-forward trong một terminal:

~~~powershell
kubectl --context $kubeContext -n $namespace port-forward deployment/catalog-config-probe 8080:8080
~~~

Từ terminal khác:

~~~powershell
Invoke-RestMethod http://localhost:8080/lab/config
~~~

Kết quả mong đợi:

~~~json
{
  "message": "Xin chào từ ConfigMap",
  "limit": 10,
  "enabled": true,
  "configRevision": "config-v1",
  "secretRevision": "secret-v1",
  "partnerUrl": "http://partner-mock:8080",
  "tokenConfigured": true,
  "pod": "catalog-config-probe-..."
}
~~~

Cần phân biệt ba bằng chứng:

1. Đọc resource bằng `kubectl` chứng minh dữ liệu hiện đang tồn tại trong API.
2. Volume và import cấu hình đúng giúp dữ liệu đến được Spring Environment.
3. Phản hồi endpoint chứng minh bean của instance đang trả lời đã nhận các giá trị tương ứng.

Thông báo `configmap/... configured` không thay thế bước thứ ba. Ngược lại, một phản hồi từ Pod cũ không phản ánh chắc chắn phiên bản fixture mới nhất trong API.

## 9. Thử cập nhật ConfigMap và Secret

Trong `fixtures.yaml`, đổi các giá trị sau:

| Key | Giá trị mới |
| --- | --- |
| `demo.message` | `Cấu hình thử nghiệm phiên bản 2` |
| `demo.limit` | `"25"` |
| `demo.config.revision` | `config-v2` |
| `demo.partner.token` | `local-only-token-v2` |
| `demo.secret.revision` | `secret-v2` |

Giữ các key còn lại. Áp dụng lại:

~~~powershell
kubectl --context $kubeContext apply -f .\fixtures.yaml
if ($LASTEXITCODE -ne 0) { throw "Cập nhật fixture thất bại." }
~~~

Đọc lại cả hai resource theo cách ở phần 5. Khi so sánh token, đổi giá trị mong đợi thành `local-only-token-v2`. Chỉ tiếp tục khi ConfigMap và Secret đều phản ánh phiên bản mong muốn.

Gọi lại `/lab/config` **trước khi restart**. Với ứng dụng mẫu này, bean vẫn giữ `config-v1` và `secret-v1` vì các field đã được gán trong constructor. Điều đó không có nghĩa thao tác cập nhật resource thất bại.

Yêu cầu tạo lại Pod:

~~~powershell
kubectl --context $kubeContext -n $namespace rollout restart deployment/catalog-config-probe
kubectl --context $kubeContext -n $namespace rollout status deployment/catalog-config-probe --timeout=300s
kubectl --context $kubeContext -n $namespace get pods -l app=catalog-config-probe -o wide
~~~

Dừng và mở lại port-forward nếu nó vẫn gắn với Pod cũ. Gọi endpoint để xác nhận `limit = 25`, `configRevision = config-v2` và `secretRevision = secret-v2`.

Không cần build lại image cho thay đổi fixture: mã ứng dụng giữ nguyên, đầu vào cấu hình thay đổi.

### Ba thời điểm cập nhật khác nhau

| Lớp | Sau khi apply dữ liệu mới |
| --- | --- |
| Resource trong API | Có dữ liệu mới sau khi cập nhật thành công |
| File trong volume | Được kubelet cập nhật theo cơ chế đồng bộ, có độ trễ |
| Field đã gán trong bean | Giữ giá trị cũ cho tới khi có cơ chế tạo lại/cập nhật phù hợp |

Volume mount ConfigMap và Secret thông thường có thể nhận cập nhật. Mount bằng `subPath` không có cơ chế nhận cập nhật tự động đó. Dữ liệu được đưa vào biến môi trường cũng không tự đổi trong tiến trình đang chạy. Xem [cấu hình Pod từ ConfigMap](https://kubernetes.io/docs/tasks/configure-pod-container/configure-pod-configmap/) và [đưa Secret vào container](https://kubernetes.io/docs/tasks/inject-data-application/distribute-credentials-secure/).

Lab không thiết lập refresh bean hoặc Configuration Watcher. Chỉ thêm nhãn vào resource hay chỉ có file mới trên volume chưa tạo ra cơ chế cập nhật field của controller.

ConfigMap và Secret là hai resource độc lập. Trong hệ thống cần nhất quán nhiều giá trị, có thể dùng tên resource theo phiên bản rồi cập nhật Pod template trỏ tới bộ đã chuẩn bị xong. Marker của bài giúp phát hiện bộ dữ liệu trộn phiên bản nhưng không tạo ra giao dịch nguyên tử.

## 10. Tạo tình huống lỗi và quan sát đúng lớp

Trước mỗi phép thử, ghi lại phiên bản chuẩn đang dùng, rồi chỉ thay một yếu tố. Sau mỗi phép thử, khôi phục `fixtures.yaml` và `workload.yaml` về bộ chuẩn đã chọn, apply lại, restart và chờ rollout.

| Tình huống | Cách tạo trong lab | Dấu hiệu cần tìm |
| --- | --- | --- |
| Sai namespace | Trỏ workload sang namespace khác mà không tạo fixture tương ứng | Pod mới không tìm thấy resource cần mount |
| Thiếu Secret | Đổi `secretName` trong bản workload thử thành tên không tồn tại | Events báo lỗi mount, chưa có log ứng dụng |
| Thiếu key | Dùng `kubectl edit secret catalog-credentials` trong đúng context/namespace để xóa key `demo.partner.token` khỏi `data`, rồi tạo Pod mới | Lỗi mount vì `items` yêu cầu key đó |
| Token rỗng | Đặt `demo.partner.token: ""` trong `stringData` rồi apply và restart | Ứng dụng từ chối khởi động |
| Số sai định dạng | Đặt `demo.limit: "khong-phai-so"` rồi apply và restart | Lỗi chuyển kiểu trong Spring |
| Số ngoài miền hợp lệ | Đặt `demo.limit: "0"` rồi apply và restart | Kiểm tra trong constructor từ chối dữ liệu |
| Chữ tiếng Việt bị lỗi | Lưu fixture bằng encoding không phù hợp | Giá trị đọc từ API đã khác chuỗi mong muốn |
| API có v2 nhưng HTTP còn v1 | Cập nhật dữ liệu, chưa restart | Bean snapshot còn giữ dữ liệu cũ |

Khi xóa key bằng `kubectl edit`, thao tác đầy đủ là:

~~~powershell
kubectl --context $kubeContext -n $namespace edit secret catalog-credentials
~~~

Chỉ xóa dòng key đích trong `data` của Secret giả. Với đầu vào `stringData`, việc chỉ bỏ một key khỏi manifest nguồn không nên được dùng làm bằng chứng rằng key trong `data` trên server đã bị xóa; hãy đọc lại resource. Để phục hồi, apply fixture chuẩn có đầy đủ key.

Lấy bằng chứng:

~~~powershell
kubectl --context $kubeContext -n $namespace describe pods -l app=catalog-config-probe
kubectl --context $kubeContext -n $namespace get events --sort-by=.metadata.creationTimestamp
kubectl --context $kubeContext -n $namespace logs deployment/catalog-config-probe --tail=100
~~~

Nếu chưa tạo được container vì mount lỗi, đọc Events trước; có thể chưa có log ứng dụng. Nếu ứng dụng đã chạy rồi thoát, đọc log của đúng Pod, và dùng `--previous` khi cần xem lần chạy container trước.

Workload đã chạy từ trước có thể tiếp tục giữ dữ liệu cũ trong một số tình huống. Để kiểm chứng hành vi thiếu resource/key lúc khởi động, cần quan sát **Pod mới** có tham chiếu bắt buộc. Không suy luận từ việc Pod cũ vẫn trả lời.

## 11. Các cách tạo dữ liệu khác bằng kubectl

Manifest là nguồn chuẩn của lab chính. Những lệnh dưới đây chỉ **sinh bản xem trước**, không ghi đè resource đang chạy.

### Từ giá trị đơn giản

~~~powershell
kubectl --context $kubeContext -n $namespace create configmap catalog-preview --from-literal=demo.limit=10 --from-literal=demo.enabled=true --dry-run=client -o yaml
~~~

`--dry-run=client` sinh object ở phía client; `-o yaml` cho phép xem dạng manifest. Bỏ dry-run sẽ trở thành thao tác tạo resource thật và có thể báo `AlreadyExists` nếu tên đã tồn tại. Tham khảo [kubectl create configmap](https://kubernetes.io/docs/reference/kubectl/generated/kubectl_create/kubectl_create_configmap/).

### Từ một file cấu hình hoàn chỉnh

Nếu có file UTF-8 `application.yaml` chứa:

~~~yaml
demo:
  message: "Xin chào từ file"
  limit: 10
  enabled: true
~~~

Có thể sinh ConfigMap chứa đúng một key `application.yaml`:

~~~powershell
kubectl --context $kubeContext -n $namespace create configmap catalog-file-preview --from-file=application.yaml=.\application.yaml --dry-run=client -o yaml
~~~

Đây là cấu trúc **một file**, khác với các key property phẳng của lab chính. Khi mount file đó vào `/etc/lab/config/application.yaml`, Spring Boot có thể import bằng:

~~~properties
spring.config.import=file:/etc/lab/config/application.yaml
~~~

Không dùng `configtree:` với kỳ vọng nó tự parse nội dung một file `application.yaml` thành toàn bộ property bên trong. Configuration tree dùng tên file làm tên property; import `file:` dùng loader của định dạng file. Chọn cách biểu diễn trước, rồi dùng loader tương ứng.

### Sinh Secret giả từ literal

Để không in toàn bộ manifest Secret ra terminal, giữ kết quả trong biến và chỉ xem cấu trúc:

~~~powershell
$previewText = kubectl --context $kubeContext -n $namespace create secret generic catalog-secret-preview --from-literal=demo.partner.token=local-only-token-v1 --dry-run=client -o json
if ($LASTEXITCODE -ne 0) { throw "Không sinh được Secret mẫu." }

$preview = ($previewText -join [Environment]::NewLine) | ConvertFrom-Json

[pscustomobject]@{
    Kind = $preview.kind
    Name = $preview.metadata.name
    Keys = ($preview.data.PSObject.Properties.Name -join ", ")
}

Remove-Variable preview, previewText
~~~

CLI tạo `data` đã base64 từ literal. Cú pháp `--from-file=key=path` dùng nội dung file thay cho literal; cần kiểm tra newline cuối file. Xem [kubectl create secret generic](https://kubernetes.io/docs/reference/kubectl/generated/kubectl_create/kubectl_create_secret_generic/).

Các literal chứa `$` hoặc ký tự đặc biệt phải được quote theo shell. Dù không in output, giá trị truyền trên command line vẫn có thể nằm trong lịch sử terminal; literal minh họa ở đây chỉ là token giả.

## 12. Chọn cách ứng dụng nhận dữ liệu

Dữ liệu đã tạo có thể được tiêu thụ theo nhiều cách:

| Cách nhận | Thành phần thực hiện | Ứng dụng cần quyền gọi Kubernetes API? | Lưu ý cập nhật |
| --- | --- | --- | --- |
| `configMapKeyRef` / `secretKeyRef` vào env | Kubernetes thiết lập env khi tạo container | Không cần cho thao tác này | Tạo lại container để nhận giá trị mới |
| Volume và Spring Boot `configtree:` | Kubelet mount, Spring đọc cấu hình | Không cần cho thao tác này | File mới không tự thay field đã gán |
| Spring Cloud Kubernetes PropertySource | Client tích hợp đọc nguồn Kubernetes | Cần quyền khi dùng API | Thiết lập refresh/restart theo tính năng và phiên bản |

Ví dụ đưa hai giá trị vào env trong container:

~~~yaml
env:
  - name: DEMO_MESSAGE
    valueFrom:
      configMapKeyRef:
        name: catalog-settings
        key: demo.message
  - name: DEMO_PARTNER_TOKEN
    valueFrom:
      secretKeyRef:
        name: catalog-credentials
        key: demo.partner.token
~~~

Đây là đoạn bổ sung cho `containers[].env`, không phải workload độc lập. Với quy tắc ánh xạ property của Spring Boot, tên env trên tương ứng với `demo.message` và `demo.partner.token`.

Nếu thêm env vào workload chính đồng thời giữ import file, cần tính đến độ ưu tiên: biến môi trường có thể ghi đè giá trị từ Config Data. Do đó, thử từng cách riêng hoặc ghi rõ nguồn ghi đè; không giữ một env cũ rồi kết luận file mới bị bỏ qua.

### Khi chọn Spring Cloud Kubernetes PropertySource

Với bộ fixture hiện tại, tên ứng dụng `catalog-config-probe` khác tên hai resource. Nếu chuyển sang đọc qua API, cần chọn nguồn tường minh:

| Thuộc tính chọn nguồn | Giá trị của lab |
| --- | --- |
| `spring.cloud.kubernetes.config.name` | `catalog-settings` |
| `spring.cloud.kubernetes.config.namespace` | `sck-data-lab` |
| `spring.cloud.kubernetes.secrets.name` | `catalog-credentials` |
| `spring.cloud.kubernetes.secrets.namespace` | `sck-data-lab` |

Trong chế độ Config Data, import `"kubernetes:"` cần starter hỗ trợ tương ứng trên classpath. Cách bật đọc Secret qua API và quyền cần thiết phải theo đúng phiên bản đang dùng. Việc khai báo tên Secret không tự cấp quyền đọc nó.

Đọc Secret qua API cần được bật và phân quyền có chủ đích; quyền `list` trên Secret có thể cho phép đọc giá trị của các Secret trong namespace. Tham khảo [Secrets PropertySource](https://docs.spring.io/spring-cloud-kubernetes/reference/property-source-config/secrets-propertysource.html).

Các chế độ đọc và cách chọn theo tên/nhãn cũng ảnh hưởng yêu cầu RBAC. Khi sử dụng API, thay cấu hình `automountServiceAccountToken: false` của lab bằng cơ chế xác thực phù hợp, tạo ServiceAccount và Role/RoleBinding cần thiết; không lấy thành công của tài khoản `kubectl` làm bằng chứng ServiceAccount của Pod có quyền. Xem [ConfigMap PropertySource](https://docs.spring.io/spring-cloud-kubernetes/reference/property-source-config/configmap-propertysource.html).

Không đồng thời giữ nhiều cơ chế import với kỳ vọng thứ tự luôn hiển nhiên. Spring Cloud Kubernetes Config Data tuân theo quy tắc precedence của Spring Boot; xem [Kubernetes PropertySource implementations](https://docs.spring.io/spring-cloud-kubernetes/reference/property-source-config.html).

## 13. Dùng fixture cho các bài tích hợp tiếp theo

Bộ dữ liệu nhỏ này có các điểm quan sát tách biệt:

- `configRevision` theo dõi phiên bản cấu hình công khai.
- `secretRevision` theo dõi marker của bộ thông tin xác thực.
- `pod` giúp phân biệt instance cũ và mới khi rollout.
- `tokenConfigured` xác nhận token không rỗng ở lần khởi tạo, không tiết lộ token.
- Trạng thái Ready và log giúp phân biệt Pod nhận dữ liệu thành công với tiến trình khởi động lỗi.

Khi thử Configuration Watcher, hãy xác định rõ resource nào được theo dõi, cơ chế thông báo và hành vi ứng dụng khi nhận thông báo. Watcher không tự làm mọi bean cập nhật được. Controller giữ snapshot như ví dụ cần cơ chế tạo lại/cập nhật phù hợp hoặc restart.

Khi thêm DiscoveryClient hoặc Spring Cloud LoadBalancer, tiếp tục dùng marker để xác nhận instance trả lời đang dùng bộ dữ liệu mong muốn. Một lần gọi HTTP không chứng minh tất cả replica đã cập nhật.

Fixture chỉ chứa dữ liệu ứng dụng. Không đặt kubeconfig hoặc token ServiceAccount thật vào Secret này để tiện thử nghiệm. Danh tính gọi Kubernetes API và thông tin xác thực giả của đối tác là hai loại dữ liệu có mục đích khác nhau.

## 14. Tự kiểm chứng và dọn môi trường

Một lần thực hành hoàn chỉnh cần ghi lại được:

1. Context và namespace đang dùng, tên hai resource và danh sách key đúng hợp đồng.
2. Chuỗi Unicode đọc từ ConfigMap đúng nội dung ban đầu.
3. Token giả giải mã khớp chính xác, không bị thêm newline.
4. Endpoint trả đúng kiểu dữ liệu, marker và tên Pod; không trả token.
5. Resource đã lên v2 nhưng bean snapshot còn v1 trước restart; sau rollout, Pod mới trả v2.
6. Ít nhất một lỗi thuộc lớp mount và một lỗi thuộc lớp khởi động Spring được nhận diện bằng đúng bằng chứng.
7. Khôi phục fixture chuẩn thành công mà không build lại image.

Để giữ một bộ bằng chứng có thể so sánh, ghi giá trị mong đợi, kết quả thực tế, tên Pod và phiên bản fixture. Không ghi dữ liệu Secret đã giải mã vào báo cáo.

Khi kết thúc, xóa workload trước:

~~~powershell
kubectl --context $kubeContext delete -f .\workload.yaml --ignore-not-found
~~~

Nếu `sck-data-lab` chỉ dùng riêng cho lab, xóa bộ fixture:

~~~powershell
kubectl --context $kubeContext delete -f .\fixtures.yaml --ignore-not-found
~~~

`fixtures.yaml` có cả Namespace, nên thao tác cuối cũng xóa những tài nguyên còn nằm trong namespace đó. Nếu dùng namespace chung, chỉ xóa các ConfigMap/Secret và workload thuộc lab thay vì xóa Namespace.

Giữ lại manifest chứa dữ liệu giả để tái tạo thử nghiệm. Một fixture hữu ích có đầu vào rõ ràng, bằng chứng kiểm chứng được và cách đưa môi trường trở về trạng thái đã biết.
