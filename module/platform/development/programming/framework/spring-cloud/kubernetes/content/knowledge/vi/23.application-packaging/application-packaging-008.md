# Kiểm tra image chạy được với các nguồn cấu hình đã chọn

## Mục tiêu của bài học

Trong chương **Đóng gói ứng dụng** của module **SPRING_CLOUD_KUBERNETES**, một image build thành công mới chứng minh rằng bước tạo image đã hoàn tất. Trước khi triển khai, cần chứng minh tiến trình Spring trong image thực sự đọc được các nguồn cấu hình đã chọn, nhận đúng giá trị và phản ứng đúng khi thiếu cấu hình bắt buộc.

Bài học hướng dẫn thiết kế phép kiểm tra có thể lặp lại cho biến môi trường, tệp cấu hình ngoài JAR, ConfigMap, Secret và nguồn Kubernetes API nếu ứng dụng sử dụng Spring Cloud Kubernetes để đọc API. Nguyên tắc xuyên suốt là **giữ nguyên image, thay đầu vào lúc chạy, đối chiếu đầu ra có thể quan sát**.

Sau bài học, bạn có thể:

- Lập ma trận kiểm tra theo đúng phương án cấu hình của ứng dụng.
- Nhận biết ứng dụng dùng giá trị từ nguồn được chọn hay đang âm thầm dùng mặc định.
- Kiểm tra image bằng Docker và trên Kubernetes với cùng artifact.
- Tách lỗi mount, quyền Linux, binding, RBAC và thứ tự ghi đè cấu hình.
- Thu thập bằng chứng đủ để quyết định image đã sẵn sàng cho môi trường triển khai hay chưa.

Các ví dụ dùng Linux container, Java 21 và một dự án Spring Boot tương thích có web server, Actuator và Bean Validation. Lệnh trên máy cá nhân viết theo PowerShell. Chọn phiên bản Spring Boot, Spring Cloud và Spring Cloud Kubernetes tương thích với dự án; không nâng phiên bản chỉ để sao chép ví dụ.

## 1. Chốt hợp đồng cấu hình trước khi chạy image

### 1.1. Chọn nguồn, cách đọc và hành vi khi thiếu

Với mỗi cấu hình, hãy ghi rõ ba điều: nguồn cung cấp, cơ chế đưa vào Spring và hành vi khi không có dữ liệu.

| Nguồn được chọn | Cơ chế đọc | Điều cần kiểm tra |
| --- | --- | --- |
| Cấu hình đóng gói trong JAR | Spring Boot đọc classpath | Giá trị mặc định có mặt và không chứa bí mật |
| Biến môi trường | Environment và binding của Spring | Tên biến, giá trị và thứ tự ghi đè |
| Tệp YAML ngoài JAR | Đường dẫn cấu hình ngoài hoặc import | Tệp có tồn tại, đọc được và thực sự được nạp |
| ConfigMap qua volume | Kubelet mount tệp, Spring Boot đọc tệp | Tên tài nguyên, key, mount path và cơ chế nạp tệp |
| Secret qua từng tệp | Volume và `configtree:` | Tên tệp ánh xạ đúng property, quyền đọc phù hợp |
| ConfigMap/Secret qua API | Spring Cloud Kubernetes client | Starter, import, namespace, tên nguồn, token và RBAC |

ConfigMap và Secret cũng có thể được ánh xạ sang biến môi trường bằng `configMapKeyRef` hoặc `secretKeyRef`. Khi đó, Spring nhận biến môi trường; ứng dụng không cần tự gọi Kubernetes API để lấy chúng.

Không bắt mọi ứng dụng kiểm tra tất cả các hàng. Nếu triển khai chỉ dùng ConfigMap qua volume và Secret qua tệp, đó là hai cơ chế bắt buộc của bản triển khai. Cách đọc qua API là một lựa chọn riêng.

### 1.2. Xác định đầu vào bắt buộc

Trong bài thực hành, ứng dụng có ba property:

| Property | Ý nghĩa | Quy tắc |
| --- | --- | --- |
| `lesson.marker` | Dấu nhận biết nguồn cấu hình | Mỗi ca thử dùng một giá trị khác nhau |
| `lesson.endpoint` | Địa chỉ dịch vụ phụ thuộc giả lập | Phải khớp giá trị mong đợi của ca thử |
| `lesson.token` | Token giả phục vụ thực hành | Bắt buộc, không có mặc định trong JAR |

Ví dụ `env-v1`, `file-v1` và `k8s-file-v1` là các marker khác nhau. Nếu mong đợi `file-v1` mà nhận `packaged-default`, tiến trình có thể vẫn chạy nhưng phép kiểm tra phải thất bại.

Trong ứng dụng thực tế, thay bộ property minh họa bằng hợp đồng thật: URL, timeout, tên hàng đợi, thông tin kết nối hoặc lựa chọn discovery/load balancing. Những thay đổi này cần được chuẩn bị trước khi build image cần kiểm tra.

## 2. Tạo điểm quan sát an toàn trong ứng dụng thực hành

### 2.1. Kiểm tra cấu hình đã bind vào bean

Dự án mẫu cần các thành phần web MVC, Actuator và Bean Validation. Với dự án Spring Boot 3 dùng Maven, đó thường là `spring-boot-starter-web`, `spring-boot-starter-actuator` và `spring-boot-starter-validation`; dùng các dependency tương ứng của phiên bản dự án.

Tạo các lớp sau trong cùng package `example.configprobe`.

~~~java
package example.configprobe;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.EnableConfigurationProperties;

@SpringBootApplication
@EnableConfigurationProperties(LessonSettings.class)
public class ConfigProbeApplication {
    public static void main(String[] args) {
        SpringApplication.run(ConfigProbeApplication.class, args);
    }
}
~~~

~~~java
package example.configprobe;

import jakarta.validation.constraints.NotBlank;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "lesson")
public record LessonSettings(
        @NotBlank String marker,
        @NotBlank String endpoint,
        @NotBlank String token) {

    @Override
    public String toString() {
        return "LessonSettings[marker=" + marker
                + ", endpoint=" + endpoint
                + ", token=<redacted>]";
    }
}
~~~

~~~java
package example.configprobe;

import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ConfigCheckController {
    private final LessonSettings settings;

    public ConfigCheckController(LessonSettings settings) {
        this.settings = settings;
    }

    @GetMapping("/internal/config-check")
    public Map<String, Object> check() {
        return Map.of(
                "marker", settings.marker(),
                "endpoint", settings.endpoint(),
                "secretConfigured", !settings.token().isBlank());
    }
}
~~~

Endpoint trả giá trị không nhạy cảm và một cờ boolean; nó không trả token, độ dài token hoặc bản băm token. Ghi đè `toString()` cũng tránh để phương thức mặc định của record đưa token vào chuỗi khi vô tình log object.

Đây là endpoint của **ứng dụng thực hành**. Trong sản phẩm, chỉ cung cấp chẩn đoán tương tự qua kênh nội bộ được bảo vệ. Không mở toàn bộ `/actuator/env` hoặc `/actuator/configprops` ra bên ngoài để làm phép kiểm tra.

Cờ `secretConfigured` chỉ chứng minh giá trị đã bind và không rỗng. Nếu cần chứng minh token có nội dung đúng và được hệ thống đích chấp nhận, bổ sung thao tác tích hợp với stub hoặc dịch vụ kiểm thử có kiểm tra xác thực. Không lấy việc cấu hình không rỗng làm bằng chứng đã gọi dịch vụ phụ thuộc thành công.

### 2.2. Cấu hình đóng gói không chứa token

Chuẩn bị `application.yaml` trong tài nguyên của ứng dụng trước khi build:

~~~yaml
spring:
  application:
    name: config-probe
  cloud:
    kubernetes:
      config:
        enabled: false
      secrets:
        enabled: false
server:
  port: 8080
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
lesson:
  marker: packaged-default
  endpoint: https://inventory.example.test
~~~

Hai cờ `spring.cloud.kubernetes.*.enabled` ở đây tắt các PropertySource tương ứng trong chế độ thử bằng môi trường/tệp. Chúng không phải công tắc tắt mọi tính năng Spring Cloud Kubernetes. Không bật DiscoveryClient, LoadBalancer dựa trên discovery hoặc watcher nếu bài thử không cần các tính năng đó.

Không khai báo token dự phòng, cũng không chép token vào image. Thiếu `lesson.token` phải khiến validation ngăn ứng dụng khởi động thành công.

Health endpoint hỗ trợ kiểm tra khả năng phục vụ; marker giúp kiểm tra giá trị cấu hình. Hai phép kiểm tra có mục đích khác nhau. Xem [Spring Boot Actuator endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html).

## 3. Giữ một image cho toàn bộ ma trận đã chọn

Sau khi hoàn tất mã và cấu hình đóng gói, build executable JAR bằng quy trình có sẵn của dự án. Ví dụ dưới đây giả định artifact được đặt tại `target/config-probe.jar`:

~~~dockerfile
# syntax=docker/dockerfile:1
FROM eclipse-temurin:21-jre-jammy
WORKDIR /app
COPY --chown=0:0 --chmod=0444 target/config-probe.jar /app/app.jar
USER 10001:10001
EXPOSE 8080
ENTRYPOINT ["java", "-Djava.io.tmpdir=/tmp", "-jar", "/app/app.jar"]
~~~

Dùng UID/GID dạng số và root filesystem chỉ đọc để bài thử gần với điều kiện triển khai hạn chế quyền. Image này không tạo tài khoản có tên trong `/etc/passwd`; runtime sử dụng UID/GID số. Nếu ứng dụng cần thông tin tài khoản hoặc home directory, chuẩn bị chúng phù hợp trong image của dự án.

~~~powershell
$TestImage = "config-probe:config-test"
docker build -t $TestImage .
docker image inspect $TestImage --format '{{.Id}}'
~~~

Ghi lại image ID của bản thử cục bộ. Sau khi đưa image lên registry, dùng digest của image đã phát hành khi triển khai và lưu lại `imageID` mà runtime báo cáo. Image ID cục bộ và manifest digest của registry là các khái niệm khác nhau; không kết luận chúng phải có chuỗi giống nhau.

Không build lại cho từng marker hoặc môi trường. Nếu sửa dependency, JAR hoặc Dockerfile, đó là image mới và phải chạy lại các ca liên quan.

Nếu lựa chọn nguồn qua Kubernetes API, phải thêm đúng một config starter phù hợp, chẳng hạn `spring-cloud-starter-kubernetes-fabric8-config` hoặc `spring-cloud-starter-kubernetes-client-config`, **trước lần build này**. Không thêm đồng thời cả hai client chỉ để thử. Nếu không lựa chọn API, không cần thêm config starter chỉ để đọc biến môi trường hoặc tệp đã mount.

## 4. Ma trận kiểm tra và quy tắc PASS

| Ca | Đầu vào | Marker mong đợi | Điều kiện bổ sung |
| --- | --- | --- | --- |
| ENV | Ba biến `LESSON_*` | `env-v1` | Token được bind, readiness thành công |
| FILE | YAML ngoài JAR và Secret dạng tệp | `file-v1` | Không có biến marker/token che khuất tệp |
| OVERRIDE | Tệp như FILE và một biến marker | `env-override` | Chứng minh quy tắc ghi đè đã chọn |
| PROFILE | Tệp theo profile `staging` | `file-staging` | Profile và tên tệp đều đúng |
| K8S-VOLUME | ConfigMap và Secret qua volume | `k8s-file-v1` | Pod Ready, non-root đọc được tệp |
| K8S-API, nếu chọn | ConfigMap qua API, Secret qua volume | `k8s-api-v1` | Đúng client, token và RBAC |
| MISSING-TOKEN | Không cung cấp token ở bất kỳ nguồn nào | Không có kết quả HTTP hợp lệ | Tiến trình dừng vì thiếu cấu hình |
| MISSING-SOURCE | Nguồn được khai báo bắt buộc không tồn tại | Không được coi là PASS | Xác định đúng lớp lỗi |

Một ca dương chỉ PASS khi tiến trình chạy, readiness đạt và endpoint trả đúng marker/endpoint mong đợi. HTTP `200` với marker sai vẫn là FAIL.

Hàm PowerShell sau chờ ứng dụng trong một khoảng thời gian có giới hạn:

~~~powershell
function Wait-ConfigCheck {
    param(
        [string]$BaseUri,
        [string]$ExpectedMarker,
        [string]$ExpectedEndpoint = "https://inventory.example.test",
        [int]$TimeoutSeconds = 90
    )

    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    do {
        try {
            $config = Invoke-RestMethod -Uri "$BaseUri/internal/config-check" -TimeoutSec 2
            $health = Invoke-RestMethod -Uri "$BaseUri/actuator/health/readiness" -TimeoutSec 2
            if ($config.marker -eq $ExpectedMarker -and
                $config.endpoint -eq $ExpectedEndpoint -and
                $config.secretConfigured -eq $true -and
                $health.status -eq "UP") {
                return $config
            }
        } catch {
            # Ứng dụng có thể chưa khởi động xong.
        }
        Start-Sleep -Milliseconds 500
    } while ([DateTime]::UtcNow -lt $deadline)

    throw "Không đạt cấu hình và readiness mong đợi trong thời gian chờ."
}
~~~

Nếu ứng dụng có Spring Security, điều chỉnh quyền truy cập hoặc client kiểm tra cho phù hợp. Không tắt bảo mật của ứng dụng sản phẩm để làm cho hàm mẫu trả PASS.

## 5. Chạy image bằng biến môi trường

Trong terminal PowerShell đã khai báo `$TestImage` và hàm kiểm tra:

~~~powershell
docker run -d --name config-env --read-only --tmpfs /tmp:rw,nosuid,nodev,size=64m,mode=1777 -p 127.0.0.1:18080:8080 -e LESSON_MARKER=env-v1 -e LESSON_ENDPOINT=https://inventory.example.test -e LESSON_TOKEN=lab-only-env-token $TestImage
Wait-ConfigCheck -BaseUri http://127.0.0.1:18080 -ExpectedMarker env-v1
docker logs config-env
~~~

Các token trong bài đều là dữ liệu giả. Với thông tin thật, dùng cơ chế phân phối bí mật của môi trường triển khai; biến môi trường và lệnh chạy có thể xuất hiện trong công cụ quản trị hoặc lịch sử thao tác.

Kết quả quan sát phải có dạng:

~~~json
{
  "marker": "env-v1",
  "endpoint": "https://inventory.example.test",
  "secretConfigured": true
}
~~~

Tên `LESSON_MARKER` ánh xạ về `lesson.marker`. Với cấu hình khác có dấu gạch nối hoặc cấu trúc phức tạp, đối chiếu quy tắc binding của phiên bản Spring Boot thay vì đoán tên biến.

## 6. Chạy image bằng YAML ngoài JAR và Secret dạng tệp

### 6.1. Chuẩn bị dữ liệu thử ở host

Tạo thư mục và các tệp UTF-8 không BOM cho lab:

~~~powershell
$LabRoot = Join-Path (Get-Location) ".config-image-lab"
$ConfigDir = Join-Path $LabRoot "config"
$SecretDir = Join-Path $LabRoot "secrets"
New-Item -ItemType Directory -Force -Path $ConfigDir, $SecretDir | Out-Null
$Utf8 = [System.Text.UTF8Encoding]::new($false)

$FileConfig = @'
lesson:
  marker: file-v1
  endpoint: https://inventory.example.test
'@

[System.IO.File]::WriteAllText((Join-Path $ConfigDir "application.yaml"), $FileConfig, $Utf8)
[System.IO.File]::WriteAllText((Join-Path $SecretDir "lesson.token"), "lab-only-file-token", $Utf8)
~~~

Các lệnh này dành cho người học tạo fixture trong môi trường thực hành. Không chép thư mục Secret thử vào build context của image phát hành.

### 6.2. Mount và nạp đúng cơ chế

~~~powershell
docker run -d --name config-file --read-only --tmpfs /tmp:rw,nosuid,nodev,size=64m,mode=1777 -p 127.0.0.1:18081:8080 --mount "type=bind,source=$ConfigDir,target=/etc/app-config,readonly" --mount "type=bind,source=$SecretDir,target=/run/secrets/app,readonly" -e SPRING_CONFIG_ADDITIONAL_LOCATION=file:/etc/app-config/ -e SPRING_CONFIG_IMPORT=configtree:/run/secrets/app/ $TestImage
Wait-ConfigCheck -BaseUri http://127.0.0.1:18081 -ExpectedMarker file-v1
~~~

Hai đường dẫn có vai trò khác nhau:

- `/etc/app-config/` chứa `application.yaml` được nạp như tài liệu cấu hình.
- `/run/secrets/app/` chứa tệp `lesson.token`, được `configtree:` chuyển thành property có cùng tên.

Không khai báo thêm `LESSON_MARKER` hoặc `LESSON_TOKEN` trong ca này. Vì token không có mặc định, ứng dụng chỉ có thể bind được token nếu nguồn tệp được đọc thành công.

Dùng đường dẫn tuyệt đối ở host. Với Docker daemon từ xa, bind mount tham chiếu filesystem của máy chạy daemon; thư mục trên máy client không tự được chuyển tới đó. Docker Desktop có cơ chế chia sẻ đường dẫn riêng. Xem [Docker bind mounts](https://docs.docker.com/engine/storage/bind-mounts/).

### 6.3. Kiểm tra ghi đè và profile

Chạy một container mới với cùng hai mount và thêm đúng một biến marker:

~~~powershell
docker run -d --name config-override --read-only --tmpfs /tmp:rw,nosuid,nodev,size=64m,mode=1777 -p 127.0.0.1:18082:8080 --mount "type=bind,source=$ConfigDir,target=/etc/app-config,readonly" --mount "type=bind,source=$SecretDir,target=/run/secrets/app,readonly" -e SPRING_CONFIG_ADDITIONAL_LOCATION=file:/etc/app-config/ -e SPRING_CONFIG_IMPORT=configtree:/run/secrets/app/ -e LESSON_MARKER=env-override $TestImage
Wait-ConfigCheck -BaseUri http://127.0.0.1:18082 -ExpectedMarker env-override
~~~

Để kiểm tra profile, tạo thêm tệp ngoài image:

~~~powershell
$StagingConfig = @'
lesson:
  marker: file-staging
'@

[System.IO.File]::WriteAllText((Join-Path $ConfigDir "application-staging.yaml"), $StagingConfig, $Utf8)

docker run -d --name config-profile --read-only --tmpfs /tmp:rw,nosuid,nodev,size=64m,mode=1777 -p 127.0.0.1:18084:8080 --mount "type=bind,source=$ConfigDir,target=/etc/app-config,readonly" --mount "type=bind,source=$SecretDir,target=/run/secrets/app,readonly" -e SPRING_CONFIG_ADDITIONAL_LOCATION=file:/etc/app-config/ -e SPRING_CONFIG_IMPORT=configtree:/run/secrets/app/ -e SPRING_PROFILES_ACTIVE=staging $TestImage
Wait-ConfigCheck -BaseUri http://127.0.0.1:18084 -ExpectedMarker file-staging
~~~

Container đã chạy từ trước không tự bind lại `LessonSettings` chỉ vì bạn thêm tệp staging. Ca PROFILE kiểm tra quá trình khởi động mới với profile tương ứng.

Trong cấu hình Config Data của ví dụ, biến môi trường có thể ghi đè dữ liệu tệp. `spring.config.additional-location` bổ sung vị trí tìm kiếm; `spring.config.location` thay các vị trí mặc định. Thư mục dùng làm search location cần dấu `/` ở cuối. `optional:` chỉ dùng cho nguồn thật sự được phép thiếu. Các quy tắc tìm kiếm, import và binding được mô tả trong [Externalized Configuration của Spring Boot](https://docs.spring.io/spring-boot/reference/features/external-config.html).

## 7. Kiểm tra ConfigMap và Secret trên Kubernetes

Docker bind mount kiểm tra được cách Spring đọc tệp, nhưng chưa chứng minh kubelet mount đúng ConfigMap/Secret hoặc UID của container đọc được chúng. Vì vậy, nếu triển khai đích là Kubernetes, cần một ca chạy trên cluster.

### 7.1. Manifest cho cách đọc qua volume

Lưu manifest sau thành `config-probe-volume.yaml` trong môi trường thực hành:

~~~yaml
apiVersion: v1
kind: Namespace
metadata:
  name: config-image-lab
---
apiVersion: v1
kind: ServiceAccount
metadata:
  name: config-probe
  namespace: config-image-lab
automountServiceAccountToken: false
---
apiVersion: v1
kind: ConfigMap
metadata:
  name: config-probe-file
  namespace: config-image-lab
data:
  application.yaml: |
    lesson:
      marker: k8s-file-v1
      endpoint: https://inventory.example.test
---
apiVersion: v1
kind: Secret
metadata:
  name: config-probe-secret
  namespace: config-image-lab
type: Opaque
stringData:
  lesson.token: lab-only-kubernetes-token
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: config-probe
  namespace: config-image-lab
spec:
  replicas: 1
  selector:
    matchLabels:
      app: config-probe
  template:
    metadata:
      labels:
        app: config-probe
    spec:
      serviceAccountName: config-probe
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
          image: config-probe:config-test
          imagePullPolicy: IfNotPresent
          ports:
            - name: http
              containerPort: 8080
          env:
            - name: SPRING_CONFIG_ADDITIONAL_LOCATION
              value: file:/etc/app-config/
            - name: SPRING_CONFIG_IMPORT
              value: configtree:/run/secrets/app/
          securityContext:
            allowPrivilegeEscalation: false
            readOnlyRootFilesystem: true
            capabilities:
              drop: ["ALL"]
          resources:
            requests:
              cpu: 100m
              memory: 256Mi
            limits:
              cpu: "1"
              memory: 512Mi
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
          volumeMounts:
            - name: config
              mountPath: /etc/app-config
              readOnly: true
            - name: credentials
              mountPath: /run/secrets/app
              readOnly: true
            - name: tmp
              mountPath: /tmp
      volumes:
        - name: config
          configMap:
            name: config-probe-file
            defaultMode: 0444
        - name: credentials
          secret:
            secretName: config-probe-secret
            defaultMode: 0440
        - name: tmp
          emptyDir:
            sizeLimit: 128Mi
~~~

Image cần được nạp vào node của cluster cục bộ hoặc đẩy lên registry. Với registry, thay `image` bằng địa chỉ và digest của chính image đã kiểm tra. Chỉ build trên host chưa đảm bảo node có image đó.

Secret trong manifest chỉ chứa dữ liệu giả. Giá trị CPU, RAM, dung lượng và ngưỡng probe là số minh họa; điều chỉnh theo ứng dụng và môi trường.

### 7.2. Xác nhận ở cả lớp Pod và lớp ứng dụng

~~~powershell
kubectl apply -f config-probe-volume.yaml
kubectl rollout status deployment/config-probe -n config-image-lab --timeout=180s
kubectl get pods -n config-image-lab -l app=config-probe
kubectl logs -n config-image-lab deployment/config-probe
kubectl exec -n config-image-lab deployment/config-probe -- id
kubectl exec -n config-image-lab deployment/config-probe -- ls -ln /etc/app-config/application.yaml /run/secrets/app/lesson.token
kubectl exec -n config-image-lab deployment/config-probe -- sh -c 'test -r /run/secrets/app/lesson.token && echo readable'
~~~

Không dùng `cat` trên Secret để chứng minh tệp đọc được. Nếu image không có `sh`, `id` hoặc `ls`, dùng công cụ chẩn đoán được nền tảng cho phép và kiểm tra đúng ngữ cảnh của ứng dụng.

Mở port-forward trong một terminal:

~~~powershell
kubectl port-forward -n config-image-lab deployment/config-probe 18083:8080
~~~

Trong terminal PowerShell có hàm kiểm tra:

~~~powershell
Wait-ConfigCheck -BaseUri http://127.0.0.1:18083 -ExpectedMarker k8s-file-v1
~~~

Đối với cách đọc volume, không cần Role cho ServiceAccount của ứng dụng để tự `get` ConfigMap/Secret. Kubelet thực hiện việc cung cấp volume theo Pod spec và quyền của hạ tầng. Không suy ra rằng bất kỳ ai cũng được quyền tạo Pod tham chiếu Secret; quyền triển khai workload vẫn phải được kiểm soát.

`fsGroup` và quyền tệp cần phù hợp với loại volume và storage driver. Kiểm tra metadata sau mount và UID thực tế thay vì chỉ nhìn mode ghi trong YAML.

Nếu production dùng `configMapKeyRef` hoặc `secretKeyRef` thay cho volume, tạo thêm ca tương ứng bằng cách ánh xạ rõ từng key tới biến `LESSON_*`. Không lấy kết quả của ca volume làm bằng chứng cho cách truyền qua biến môi trường.

## 8. Kiểm tra nguồn qua Kubernetes API nếu đã chọn

### 8.1. Điều kiện trước khi chạy

Chỉ thực hiện mục này khi image đã có config starter tương ứng từ trước lần build ở mục 3. Nếu image hiện tại không có starter và triển khai không cần đọc API, đánh dấu ca API là **không áp dụng** kèm lý do.

Nếu triển khai có yêu cầu đọc API mà image chưa có starter, đó là thiếu sót cần sửa và build image mới. Không đánh dấu ca đó là PASS bằng kết quả đọc volume.

Spring Cloud Kubernetes hỗ trợ nhập nguồn Kubernetes qua `spring.config.import: "kubernetes:"`. Chế độ Config Data và cơ chế bootstrap cũ là hai lựa chọn khác nhau; không bật đồng thời để thử khắc phục lỗi. Xem [Kubernetes PropertySource implementations](https://docs.spring.io/spring-cloud-kubernetes/reference/property-source-config.html).

Cấu hình API phải được cung cấp đủ sớm từ môi trường hoặc cấu hình đóng gói. Không đặt duy nhất tên namespace, import hoặc danh tính truy cập trong chính ConfigMap mà client chưa biết cách tải.

### 8.2. Tạo nguồn và quyền dành riêng cho ca API

Lưu các tài nguyên sau thành `config-probe-api-resources.yaml`:

~~~yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: config-probe-api
  namespace: config-image-lab
data:
  application.yaml: |
    lesson:
      marker: k8s-api-v1
      endpoint: https://inventory.example.test
---
apiVersion: v1
kind: ServiceAccount
metadata:
  name: config-probe-api
  namespace: config-image-lab
---
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: config-probe-api-reader
  namespace: config-image-lab
rules:
  - apiGroups: [""]
    resources: ["configmaps"]
    verbs: ["get", "list"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: config-probe-api-reader
  namespace: config-image-lab
subjects:
  - kind: ServiceAccount
    name: config-probe-api
    namespace: config-image-lab
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: Role
  name: config-probe-api-reader
~~~

Role phục vụ việc đọc ConfigMap khi khởi động, không cấp quyền đọc Secret hoặc các tài nguyên discovery. Nếu phiên bản/client/chức năng được chọn cần thêm thao tác như watch, đối chiếu request thực tế và cấp quyền đúng phạm vi.

Tên ConfigMap cần khớp cấu hình client, không chỉ khớp tên Deployment. Spring Cloud Kubernetes có các thuộc tính chọn tên, namespace và nguồn; xem [Using a ConfigMap PropertySource](https://docs.spring.io/spring-cloud-kubernetes/reference/property-source-config/configmap-propertysource.html). Cách đọc theo lô hoặc từng tên có thể ảnh hưởng RBAC; không thêm `resourceNames` rồi mặc định mọi thao tác `list` vẫn hoạt động.

### 8.3. Chuyển đúng cơ chế mà vẫn giữ nguyên image

Đây là strategic merge patch cho Deployment ở mục 7. Lưu thành `config-probe-api-patch.yaml`:

~~~yaml
spec:
  template:
    spec:
      serviceAccountName: config-probe-api
      automountServiceAccountToken: true
      containers:
        - name: app
          env:
            - name: SPRING_CONFIG_ADDITIONAL_LOCATION
              $patch: delete
            - name: SPRING_CONFIG_IMPORT
              value: "kubernetes:,configtree:/run/secrets/app/"
            - name: SPRING_CLOUD_KUBERNETES_CONFIG_ENABLED
              value: "true"
            - name: SPRING_CLOUD_KUBERNETES_CONFIG_NAME
              value: config-probe-api
            - name: SPRING_CLOUD_KUBERNETES_CONFIG_NAMESPACE
              value: config-image-lab
            - name: SPRING_CLOUD_KUBERNETES_CONFIG_FAILFAST
              value: "true"
            - name: SPRING_CLOUD_KUBERNETES_CONFIG_RETRY_ENABLED
              value: "false"
            - name: SPRING_CLOUD_KUBERNETES_SECRETS_ENABLED
              value: "false"
          volumeMounts:
            - mountPath: /etc/app-config
              $patch: delete
      volumes:
        - name: config
          $patch: delete
~~~

Patch giữ nguyên image, volume Secret và cấu hình an toàn của container. Nó gỡ nguồn YAML qua volume để marker không thể đến từ đường dẫn cũ, đồng thời bật token tại Pod để client xác thực với API.

Chạy:

~~~powershell
kubectl apply -f config-probe-api-resources.yaml
kubectl patch deployment config-probe -n config-image-lab --type=strategic --patch-file config-probe-api-patch.yaml
kubectl rollout status deployment/config-probe -n config-image-lab --timeout=180s
kubectl logs -n config-image-lab deployment/config-probe
~~~

Sau rollout, mở lại port-forward tới Deployment nếu kết nối cũ đã kết thúc, rồi kiểm tra:

~~~powershell
Wait-ConfigCheck -BaseUri http://127.0.0.1:18083 -ExpectedMarker k8s-api-v1
~~~

Client cần truy cập được Kubernetes API, xác minh được CA và đọc được token. UID Linux non-root không thay thế các điều kiện này. Quyền ServiceAccount phải tương ứng với chức năng client; xem [Security Configurations Inside Kubernetes](https://docs.spring.io/spring-cloud-kubernetes/reference/security-service-accounts.html).

Ca này chứng minh **ConfigMap qua API kết hợp Secret qua volume**. Nó chưa chứng minh Secret được đọc qua API. Nếu triển khai chọn Secret qua API, cần một ca độc lập: bật cơ chế Secret tương ứng của phiên bản đang dùng, gỡ các nguồn Secret thay thế và cấp RBAC cần thiết cho đúng namespace. Không mở quyền Secret chỉ để làm cho ca ConfigMap chạy được.

DiscoveryClient, Spring Cloud LoadBalancer và Configuration Watcher cũng cần kiểm tra riêng nếu chúng thuộc phạm vi triển khai. Việc image tải được ConfigMap không chứng minh discovery tìm đúng instance, LoadBalancer chọn đúng đích hoặc watcher cập nhật bean thành công.

## 9. Ca âm tính: chứng minh hệ thống không che giấu lỗi cấu hình

### 9.1. Thiếu token bắt buộc

Chạy một container không có token, không mount Secret và không khai báo import:

~~~powershell
docker run --name config-missing-token --read-only --tmpfs /tmp:rw,nosuid,nodev,size=64m,mode=1777 -e LESSON_MARKER=missing-token -e LESSON_ENDPOINT=https://inventory.example.test $TestImage
docker inspect config-missing-token --format '{{.State.ExitCode}}'
docker logs config-missing-token
~~~

Kỳ vọng là Java kết thúc với mã lỗi và log cho thấy validation của `lesson.token` thất bại. Phân biệt lỗi này với Docker không tạo được container, thiếu image hoặc lỗi runtime khác. Không chỉ kiểm tra “mã khác 0” rồi kết luận đã thử thành công thiếu cấu hình.

Nếu ứng dụng vẫn khởi động, tìm token mặc định, biến được truyền gián tiếp, nguồn cấu hình không nằm trong hợp đồng hoặc việc thiếu validation provider.

### 9.2. Thiếu nguồn hoặc sai key

Các phép thử sau thực hiện trên fixture và tài nguyên lab riêng:

| Tình huống cố ý gây lỗi | Dấu hiệu cần xác định |
| --- | --- |
| `--mount` trỏ tới thư mục host không tồn tại | Docker từ chối mount trước khi Java chạy |
| Import bắt buộc trỏ tới thư mục không có trong container | Lỗi nạp Config Data khi khởi động |
| Secret volume không có key `lesson.token` | Có thể mount được thư mục nhưng binding thiếu token |
| ConfigMap/Secret bắt buộc trong Pod không tồn tại | Pod có sự kiện mount hoặc cấu hình container thất bại |
| Token file không đọc được bởi UID ứng dụng | Lỗi quyền Linux, không phải RBAC của API |
| ServiceAccount thiếu quyền đọc API | Lỗi truy cập tài nguyên, thường là HTTP `403` |
| API không truy cập được hoặc CA không hợp lệ | Timeout, lỗi DNS/kết nối hoặc TLS |
| Marker bị biến môi trường cũ ghi đè | Ứng dụng có thể Ready nhưng trả marker sai |

Đối với nguồn API, `fail-fast` giúp làm rõ lỗi tải cấu hình theo khả năng của phiên bản/client. Tuy nhiên, một ConfigMap không được tìm thấy có thể được xử lý khác với lỗi truy cập API. Nếu vẫn còn mặc định trong JAR, ứng dụng có thể khởi động với marker mặc định; assertion marker phải phát hiện tình huống đó.

`optional:` cho phép bỏ qua việc không có một số vị trí cấu hình; nó không làm một giá trị bắt buộc tự trở nên hợp lệ và không phải cơ chế bỏ qua mọi lỗi parser, binding, TLS hoặc RBAC.

Không sửa ca âm tính bằng cách cấp `cluster-admin`, chuyển tiến trình sang root hoặc thêm bí mật dự phòng vào JAR. Cần giữ hợp đồng ban đầu và sửa đúng điều kiện bị thiếu.

## 10. Cập nhật cấu hình khác với khởi động bằng cấu hình

Cần tách hai câu hỏi:

1. Image có khởi động đúng với cấu hình được cung cấp không?
2. Tiến trình đang chạy có nhận thay đổi cấu hình theo cơ chế đã thiết kế không?

ConfigMap đưa vào biến môi trường không cập nhật trực tiếp các biến đã có của tiến trình; thường cần tạo lại Pod để nhận giá trị mới. Volume ConfigMap có thể được kubelet cập nhật sau một khoảng đồng bộ, nhưng mount bằng `subPath` không nhận cập nhật tự động. Xem [ConfigMaps của Kubernetes](https://kubernetes.io/docs/concepts/configuration/configmap/).

Ngay cả khi tệp trên volume đã đổi, bean `LessonSettings` của ví dụ không tự được bind lại chỉ nhờ thay đổi filesystem. Với chiến lược rollout, cập nhật tài nguyên, chạy lại Deployment và kiểm tra marker trên Pod mới. Với chiến lược refresh hoặc Configuration Watcher, kiểm tra riêng toàn bộ luồng từ sự kiện thay đổi tới giá trị mà bean nghiệp vụ thực sự dùng.

Record immutable trong ví dụ phục vụ kiểm tra lúc khởi động; không giả định nó hỗ trợ mọi cơ chế refresh. Nếu yêu cầu cập nhật tại chỗ, chọn kiểu bean và cơ chế cập nhật được phiên bản thư viện hỗ trợ.

Khi thử thay đổi cấu hình, đặt marker mới và ghi nhận UID của Pod hoặc số lần restart. Nhờ đó có thể phân biệt thay đổi tại chỗ với việc tiến trình đã được khởi động lại.

## 11. Thu thập bằng chứng và khoanh vùng lỗi

### 11.1. Thông tin tối thiểu cho mỗi ca

Ghi lại trong kết quả kiểm tra của dự án:

- Image tham chiếu, digest/image ID thực tế và nền tảng kiến trúc liên quan.
- Ca thử, nguồn cấu hình, profile, marker và endpoint mong đợi.
- Giá trị không nhạy cảm mà ứng dụng thực sự trả về.
- Trạng thái container/Pod, readiness và lỗi khởi động nếu có.
- Kết quả PASS/FAIL hoặc không áp dụng với lý do rõ ràng.
- Với Secret, chỉ ghi bằng chứng đọc/bind hoặc xác thực thành công; không ghi nội dung.

Đối chiếu image của các container Docker mà không in toàn bộ environment:

~~~powershell
docker inspect config-env config-file config-override config-profile --format '{{.Name}} {{.Image}}'
~~~

Trên Kubernetes, lấy các trường image thay vì dump Secret:

~~~powershell
$PodSnapshot = kubectl get pods -n config-image-lab -l app=config-probe -o json | ConvertFrom-Json
$PodSnapshot.items | ForEach-Object {
    $_.status.containerStatuses | Select-Object name, image, imageID
}
~~~

Nếu sử dụng tag có thể bị ghi đè, kết quả chạy trước và sau không nhất thiết là cùng image. Ưu tiên digest trong bước phát hành.

### 11.2. Trình tự chẩn đoán

1. **Runtime có tạo được container không?** Kiểm tra lỗi pull image, mount và sự kiện Pod.
2. **Java có khởi động không?** Xem log, exit code và lỗi nạp Config Data.
3. **Cấu hình có bind đúng không?** Kiểm tra tên key, profile, đường dẫn và validation.
4. **Ứng dụng có dùng đúng giá trị không?** Đối chiếu marker và endpoint thực tế.
5. **Nguồn API có đủ điều kiện không?** Kiểm tra namespace, danh tính, RBAC, kết nối và CA.
6. **Nếu cần cập nhật động, bean nghiệp vụ có nhận giá trị mới không?** Không dừng ở quan sát tệp hoặc sự kiện watcher.

Khi container đã chạy rồi thoát, xem log của lần chạy tương ứng; với Pod có restart, có thể cần `kubectl logs --previous` cho đúng Pod/container. Khi chưa tạo được container, `kubectl describe pod` thường hữu ích hơn việc chờ log ứng dụng.

Sau thực hành, dừng các container và workload lab mà bạn đã tạo theo quy trình của môi trường. Không dùng lệnh dọn dẹp theo tên rộng có thể ảnh hưởng tài nguyên khác.

## 12. Điều kiện hoàn thành

Một image được xác nhận dùng được với các nguồn cấu hình đã chọn khi:

- Cùng artifact vượt qua các ca dương thuộc hợp đồng triển khai.
- Marker và cấu hình không nhạy cảm khớp kỳ vọng, không bị mặc định hoặc nguồn khác che khuất.
- Secret được cung cấp qua đúng cơ chế và không bị lộ trong đầu ra kiểm tra.
- Thiếu cấu hình bắt buộc hoặc nguồn bắt buộc được phát hiện theo hợp đồng.
- Phép kiểm tra trên Kubernetes bao gồm cách mount hoặc cách gọi API thực tế của môi trường đích.
- Các chức năng discovery, load balancing và cập nhật cấu hình được đánh giá riêng khi ứng dụng sử dụng chúng.

Mục tiêu là có bằng chứng cụ thể rằng image hoạt động với đầu vào triển khai, từ việc nạp cấu hình tới giá trị ứng dụng sử dụng. Chỉ lựa chọn và cấp quyền cho những tính năng Spring Cloud Kubernetes thực sự tham gia vào luồng đó.
