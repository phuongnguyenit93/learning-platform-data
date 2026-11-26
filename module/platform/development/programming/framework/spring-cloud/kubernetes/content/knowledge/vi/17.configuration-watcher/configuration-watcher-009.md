# Điều chỉnh độ trễ để chờ dữ liệu volume được đồng bộ

Trong module **SPRING_CLOUD_KUBERNETES**, Configuration Watcher giúp ứng dụng Spring nhận thông báo khi ConfigMap hoặc Secret thay đổi. Nếu ứng dụng đọc cấu hình qua volume, có một khoảng thời gian cần tính đến: Kubernetes API đã nhận dữ liệu mới, nhưng tệp bên trong từng Pod có thể vẫn chứa dữ liệu cũ. Refresh trong khoảng này có thể thành công về HTTP mà chưa áp dụng được cấu hình mới.

Bài học tập trung vào cách đặt độ trễ của Watcher, đo thời gian đồng bộ volume và kiểm tra cấu hình mà ứng dụng thực sự đang sử dụng. Ví dụ dùng Spring Cloud Kubernetes **3.3.x**, đối chiếu mã nguồn **3.3.3**, với ứng dụng Spring Boot 3.5.x chạy trên JVM và Spring Cloud BOM tương thích. Khi dùng nhánh khác, cần đối chiếu thuộc tính với phiên bản đã triển khai.

## 1. Mục tiêu

Sau bài học, bạn có thể:

- Giải thích vì sao sự kiện thay đổi ConfigMap không chứng minh tệp trong mọi Pod đã đổi.
- Cấu hình `refreshDelay` đúng nơi, đúng đơn vị và phân biệt giá trị ví dụ với mặc định của một phiên bản.
- Đo riêng thời điểm volume đổi và thời điểm ứng dụng sử dụng cấu hình mới trên từng replica.
- Phân biệt lỗi do độ trễ với lỗi mount, nguồn cấu hình, RBAC, discovery và endpoint refresh.
- Chọn refresh động hoặc triển khai lại Pod dựa trên nhu cầu cập nhật cấu hình.

## 2. Hai đường xử lý chạy độc lập

Xét `catalog-api` đọc `demo.revision` từ tệp `/etc/runtime/application.properties` được mount bằng ConfigMap. Khi cập nhật ConfigMap, có hai đường xử lý:

~~~mermaid
flowchart TD
    A["Cập nhật ConfigMap trên Kubernetes API"] --> B["Watcher quan sát sự kiện"]
    A --> C["Kubelet đồng bộ volume của từng Pod"]
    B --> D["Chờ refreshDelay"]
    D --> E["Gửi thông báo refresh"]
    C --> F["Tệp trong Pod chứa revision mới"]
    E --> G["Spring đọc lại nguồn cấu hình"]
    F --> G
    G --> H["Bean và hành vi sử dụng revision mới"]
~~~

Hai mũi tên đi vào bước đọc cấu hình thể hiện hai điều kiện cần phối hợp. Sơ đồ không có nghĩa Watcher tự kiểm tra volume đã sẵn sàng. Nếu thông báo đến trước khi tệp đổi, Spring vẫn có thể đọc phiên bản cũ.

Theo tài liệu [ConfigMaps của Kubernetes](https://kubernetes.io/docs/concepts/configuration/configmap/#mounted-configmaps-are-updated-automatically), cập nhật volume diễn ra theo cơ chế nhất quán cuối cùng. Độ trễ phụ thuộc chu kỳ đồng bộ kubelet và cách lan truyền dữ liệu từ cache; cơ chế phát hiện thay đổi mặc định là Watch. Không nên coi một con số cố định là thời hạn bảo đảm cho mọi cụm.

### Ví dụ refresh quá sớm

Bảng sau là tình huống giả định, tính từ lúc cập nhật API:

| Thời điểm | Sự kiện | Kết quả |
| --- | --- | --- |
| 0 giây | API lưu revision `r2` | ConfigMap trên API đã mới |
| 0,3 giây | Watcher nhận thay đổi | Volume chưa chắc đã đổi |
| 10,3 giây | Watcher gửi refresh với độ trễ 10 giây | Hai Pod có thể vẫn đọc `r1` |
| 16 giây | Volume của Pod A chuyển sang `r2` | Tệp đã mới nhưng trạng thái Spring có thể còn cũ |
| 32 giây | Volume của Pod B chuyển sang `r2` | Cả hai Pod đã có tệp mới |

Không được dựa vào giả định Watcher sẽ gửi thêm một refresh chỉ vì volume vừa cập nhật. Sự kiện tài nguyên trên API và thao tác cập nhật volume là hai mốc khác nhau. HTTP `200` từ endpoint refresh không thay thế việc kiểm tra revision đang được ứng dụng sử dụng.

## 3. Cấu hình đúng thuộc tính của Watcher

Thuộc tính dùng trong bài:

~~~properties
spring.cloud.kubernetes.configuration.watcher.refresh-delay=45000
~~~

Dạng biến môi trường được tài liệu Watcher sử dụng:

~~~yaml
env:
  - name: SPRING_CLOUD_KUBERNETES_CONFIGURATION_WATCHER_REFRESHDELAY
    value: "45000"
~~~

Đặt cấu hình trong container chạy **Configuration Watcher**. Nếu chỉ đặt vào Deployment ứng dụng `catalog-api`, Watcher chạy riêng sẽ không nhận được thay đổi.

Trong mã nguồn [ConfigurationWatcherConfigurationProperties của phiên bản 3.3.3](https://raw.githubusercontent.com/spring-cloud/spring-cloud-kubernetes/v3.3.3/spring-cloud-kubernetes-controllers/spring-cloud-kubernetes-configuration-watcher/src/main/java/org/springframework/cloud/kubernetes/configuration/watcher/ConfigurationWatcherConfigurationProperties.java), `refreshDelay` có kiểu `Duration`; giá trị số không có hậu tố dùng đơn vị mili giây; mặc định là **120000 ms**, tức **120 giây**. Giá trị `10000` trong tài liệu hướng dẫn chỉ là ví dụ đặt **10 giây**, không phải mặc định của phiên bản này.

| Giá trị số | Thời gian chờ |
| --- | --- |
| `10000` | 10 giây |
| `45000` | 45 giây |
| `120000` | 120 giây |

Nên ghi tường minh giá trị đã chọn vào manifest hoặc cấu hình triển khai để dễ so sánh môi trường và kiểm soát khi nâng phiên bản.

`refreshDelay` tạo khoảng chờ trước thông báo. Nó không làm kubelet cập nhật nhanh hơn, không phải timeout HTTP và không xác nhận mọi volume đã đồng bộ. Đây cũng không phải chu kỳ polling `spring.cloud.kubernetes.reload.period` của cơ chế reload trong ứng dụng.

## 4. Chọn độ trễ từ số đo

Gọi:

- `E`: thời điểm Watcher quan sát thay đổi.
- `Vᵢ`: thời điểm tệp trong Pod thứ `i` chứa revision cần áp dụng.
- `D`: độ trễ của Watcher.
- `M`: khoảng dự phòng cho dao động và sai số đo.

Một nguyên tắc thiết kế thận trọng là:

~~~text
D >= thời gian chờ Pod chậm nhất có tệp mới, tính từ E + M

Với một lần cập nhật:
D >= max(0, max_i(V_i - E)) + M
~~~

Đây là cách suy luận để chọn cấu hình, không phải thuật toán xác nhận đồng bộ của Watcher. Thời gian gửi thông báo và thực thi refresh còn cộng thêm vào thời gian chờ cấu hình có hiệu lực.

Hãy đo qua nhiều lần cập nhật, nhiều node và các mức tải khác nhau. Khi có đủ mẫu, có thể chọn phân vị cao của thời gian Pod chậm nhất trong mỗi lần cập nhật, rồi cộng dự phòng. Với vài mẫu trong lab, chỉ nên dùng giá trị lớn nhất quan sát được để thử nghiệm; không gọi đó là p99 có ý nghĩa thống kê.

Ví dụ số liệu **minh họa**, không phải kết quả benchmark:

| Lần cập nhật | Pod A có tệp mới | Pod B có tệp mới | Pod chậm nhất |
| --- | --- | --- | --- |
| 1 | 12 giây | 19 giây | 19 giây |
| 2 | 18 giây | 32 giây | 32 giây |
| 3 | 29 giây | 38 giây | 38 giây |
| 4 | 24 giây | 31 giây | 31 giây |

Nếu đo từ trước lúc gửi cập nhật API, các số trên còn bao gồm thời gian ghi API, nên thường là ước lượng thận trọng cho khoảng chờ kể từ `E`. Với tập mẫu này, `45000 ms` là ứng viên thử nghiệm, dự phòng khoảng 7 giây so với mẫu lớn nhất. Nó chưa chứng minh an toàn cho môi trường thật.

Đánh giá đồng thời hai yêu cầu:

1. Đủ lâu để tránh đọc tệp cũ.
2. Đủ nhanh để đáp ứng thời gian cập nhật cấu hình mà nghiệp vụ chấp nhận.

Nếu yêu cầu áp dụng trong 5 giây nhưng volume thường cần hàng chục giây, giảm delay xuống 5 giây không giải quyết được mâu thuẫn. Cần xem lại đường phân phối cấu hình hoặc dùng quy trình triển khai có xác nhận revision.

Đo lại sau khi đổi node pool, cấu hình kubelet, số replica hoặc cách đọc cấu hình. Không lấy thời gian của một Pod làm đại diện cho cả Deployment.

## 5. Chuẩn bị thực hành

Bài thực hành dùng các tên sau:

| Thành phần | Tên hoặc giá trị |
| --- | --- |
| Namespace | `sck-lab` |
| Deployment Watcher đã triển khai | `configuration-watcher` |
| Ứng dụng, Service, ConfigMap | `catalog-api` |
| Số replica ứng dụng | 2 |
| Container ứng dụng | `app` |
| Tệp cấu hình trong container | `/etc/runtime/application.properties` |
| Endpoint quan sát | `GET /demo/config` |
| Endpoint refresh nội bộ | `POST /actuator/refresh` |

Điều kiện trước khi bắt đầu:

- Có Watcher 3.3.x hoạt động và theo dõi namespace `sck-lab`.
- ServiceAccount của Watcher có quyền đọc, liệt kê, theo dõi ConfigMap và quyền discovery cần thiết để tìm instance. Nếu bật theo dõi Secret, cấp quyền Secret theo phạm vi cần dùng.
- Watcher gọi được endpoint refresh của từng instance qua mạng nội bộ.
- Ứng dụng JVM có Spring Web, Actuator và Spring Cloud Context; có thể lấy Context qua `spring-cloud-starter`. Quản lý phiên bản bằng Spring Boot và Spring Cloud BOM tương thích.
- Ảnh ứng dụng lab có `cat` để đọc tệp bằng `kubectl exec`. Với ảnh distroless, chuẩn bị cách quan sát tương đương qua container công cụ mount cùng volume.
- Hai replica đã sẵn sàng. Muốn so sánh giữa các node, xác nhận vị trí bằng `kubectl get pods -o wide`.

Các giả định này giới hạn thí nghiệm vào độ trễ volume; không cần cài broker. Bài dùng phương thức HTTP, không triển khai Spring Cloud Bus.

Theo [tài liệu Configuration Watcher 3.3](https://docs.spring.io/spring-cloud-kubernetes/reference/3.3/spring-cloud-kubernetes-configuration-watcher.html#_http_implementation), HTTP là phương thức mặc định: Watcher dùng DiscoveryClient tìm các instance rồi POST đến endpoint refresh. Ví dụ dùng cùng tên `catalog-api` cho ConfigMap và Service để ánh xạ đích đơn giản.

## 6. Ứng dụng đọc tệp và công bố revision

### Cấu hình cố định của ứng dụng

Đặt trong `application.yml` đóng gói cùng ứng dụng:

~~~yaml
spring:
  application:
    name: catalog-api
  config:
    import: "file:/etc/runtime/application.properties"

management:
  endpoints:
    web:
      exposure:
        include: health,refresh
  endpoint:
    health:
      probes:
        enabled: true
~~~

Theo [Spring Boot Externalized Configuration](https://docs.spring.io/spring-boot/3.5/reference/features/external-config.html#importing-additional-data), `spring.config.import` cho phép nạp tệp ngoài ứng dụng. Ví dụ dùng đường dẫn bắt buộc để phát hiện sớm khi thiếu tệp mount.

Không đặt thêm `DEMO_REVISION` hoặc tham số dòng lệnh ghi đè `demo.revision` trong thí nghiệm. Một nguồn có độ ưu tiên cao hơn có thể che giá trị từ tệp.

### Endpoint quan sát

Đặt lớp sau trong package được ứng dụng Spring Boot quét:

~~~java
package example.catalog;

import java.util.Map;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.cloud.context.config.annotation.RefreshScope;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RefreshScope
public class ConfigProbeController {

    @Value("${demo.revision}")
    private String revision;

    @Value("${HOSTNAME:local}")
    private String pod;

    @GetMapping("/demo/config")
    public Map<String, String> config() {
        return Map.of("pod", pod, "revision", revision);
    }
}
~~~

Endpoint trả về giá trị đã inject vào bean, giúp kiểm tra phần Spring đang sử dụng. Đọc tệp bằng `cat` kiểm tra một lớp khác.

[Spring Cloud Context 4.3](https://docs.spring.io/spring-cloud-commons/reference/4.3/spring-cloud-commons/application-context-services.html#refresh-scope) mô tả bean trong `@RefreshScope` được tạo lại khi được sử dụng sau khi cache của scope bị xóa bởi refresh. Sau thông báo refresh, cần gọi endpoint quan sát để thấy giá trị của bean được khởi tạo lại.

Giữ endpoint quản trị trong phạm vi nội bộ và áp dụng cơ chế truy cập phù hợp. Nếu cụm đã có xác thực, Watcher phải gọi hợp lệ; tăng delay không sửa được lỗi xác thực.

### ConfigMap ban đầu

~~~yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: catalog-api
  namespace: sck-lab
  labels:
    spring.cloud.kubernetes.config: "true"
data:
  application.properties: |
    demo.revision=r1
~~~

Label cho phép nguồn tham gia luồng thông báo của Watcher trong ví dụ 3.3.x. Nếu đã bật bộ lọc informer riêng, cần đáp ứng thêm label selector mà Watcher sử dụng.

### Deployment và Service ứng dụng

Thay `YOUR_REGISTRY/catalog-api:lab` bằng ảnh đã xây dựng với cấu hình và controller ở trên:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: catalog-api
  namespace: sck-lab
spec:
  replicas: 2
  selector:
    matchLabels:
      app: catalog-api
  template:
    metadata:
      labels:
        app: catalog-api
    spec:
      containers:
        - name: app
          image: YOUR_REGISTRY/catalog-api:lab
          ports:
            - name: http
              containerPort: 8080
          readinessProbe:
            httpGet:
              path: /actuator/health/readiness
              port: http
          volumeMounts:
            - name: runtime-config
              mountPath: /etc/runtime
              readOnly: true
      volumes:
        - name: runtime-config
          configMap:
            name: catalog-api
---
apiVersion: v1
kind: Service
metadata:
  name: catalog-api
  namespace: sck-lab
spec:
  selector:
    app: catalog-api
  ports:
    - name: http
      port: 8080
      targetPort: http
~~~

Mount cả thư mục `/etc/runtime`, không dùng `subPath`. Không thêm nguồn API khác cho cùng `demo.revision`: bài cần quan sát đúng việc Spring đọc dữ liệu qua volume.

## 7. Đặt delay và xác nhận baseline

Các lệnh sau dùng PowerShell và môi trường lab đã chuẩn bị. Đặt ứng viên 45 giây:

~~~powershell
kubectl -n sck-lab set env deployment/configuration-watcher SPRING_CLOUD_KUBERNETES_CONFIGURATION_WATCHER_REFRESHDELAY=45000

kubectl -n sck-lab rollout status deployment/configuration-watcher
kubectl -n sck-lab rollout status deployment/catalog-api
kubectl -n sck-lab get pods -l app=catalog-api -o wide
~~~

Với GitOps, thay đổi manifest nguồn rồi đồng bộ. `set env` phù hợp cho thí nghiệm; tránh để bộ điều khiển hoàn nguyên giá trị trong lúc đo.

Đổi biến môi trường làm Watcher được triển khai lại. Chờ Watcher sẵn sàng trước khi cập nhật ConfigMap. Không dùng giai đoạn khởi động Watcher làm mẫu đo.

Nếu cần log để xác định mốc nhận thay đổi, có thể bật tạm:

~~~powershell
kubectl -n sck-lab set env deployment/configuration-watcher LOGGING_LEVEL_ORG_SPRINGFRAMEWORK_CLOUD_KUBERNETES_CONFIGURATION_WATCHER=DEBUG

kubectl -n sck-lab rollout status deployment/configuration-watcher
kubectl -n sck-lab logs deployment/configuration-watcher --timestamps --since=5m
~~~

Thông điệp cụ thể có thể khác giữa phiên bản. Tìm bản ghi nhận thay đổi nguồn, tìm instance và gửi refresh.

### Truy cập từng Pod

Trong terminal PowerShell thứ nhất:

~~~powershell
$podA = kubectl -n sck-lab get pods -l app=catalog-api -o jsonpath='{.items[0].metadata.name}'
kubectl -n sck-lab port-forward ("pod/" + $podA) 18081:8080
~~~

Trong terminal thứ hai:

~~~powershell
$podB = kubectl -n sck-lab get pods -l app=catalog-api -o jsonpath='{.items[1].metadata.name}'
kubectl -n sck-lab port-forward ("pod/" + $podB) 18082:8080
~~~

Trong terminal thứ ba:

~~~powershell
Invoke-RestMethod http://localhost:18081/demo/config
Invoke-RestMethod http://localhost:18082/demo/config
~~~

Cả hai phản hồi phải là `r1` và có tên Pod khác nhau. Giữ port-forward hoạt động trong suốt lần đo. Nếu Pod bị thay thế, thiết lập lại và bắt đầu lần đo mới.

Gọi qua Service hoặc Spring Cloud LoadBalancer có thể đưa nhiều yêu cầu đến cùng một instance. Vì vậy, cần kiểm tra từng Pod. Health `UP` hoặc Pod `Ready` chưa chứng minh revision đã đồng nhất.

## 8. Cập nhật và đo hai lớp trạng thái

Trong terminal thứ ba, ghi mốc bắt đầu và cập nhật `r2`. Here-string được truyền trực tiếp cho `kubectl`, không cần tạo tệp trung gian:

~~~powershell
$updateStarted = [DateTimeOffset]::UtcNow

@'
apiVersion: v1
kind: ConfigMap
metadata:
  name: catalog-api
  namespace: sck-lab
  labels:
    spring.cloud.kubernetes.config: "true"
data:
  application.properties: |
    demo.revision=r2
'@ | kubectl apply -f -

$apiCommandFinished = [DateTimeOffset]::UtcNow
$updateStarted.ToString("o")
$apiCommandFinished.ToString("o")
~~~

Mốc ghi API thực tế nằm trong khoảng thực thi lệnh. `updateStarted` giúp đo thận trọng từ trước cập nhật; nó không phải timestamp chính xác của sự kiện Watcher.

Ngay sau đó chạy vòng quan sát trong cùng terminal:

~~~powershell
$pods = (kubectl -n sck-lab get pods -l app=catalog-api -o json | ConvertFrom-Json).items.metadata.name
$portsByPod = @{}

foreach ($port in @(18081, 18082)) {
    $probe = Invoke-RestMethod -Uri ("http://localhost:" + $port + "/demo/config")
    $portsByPod[$probe.pod] = $port
}

$volumeSeen = @{}
$appSeen = @{}
$deadline = [DateTimeOffset]::UtcNow.AddSeconds(180)

do {
    foreach ($podName in $pods) {
        $fileText = kubectl -n sck-lab exec $podName -c app -- cat /etc/runtime/application.properties
        $fileReadOk = $LASTEXITCODE -eq 0
        $elapsed = [math]::Round(([DateTimeOffset]::UtcNow - $updateStarted).TotalSeconds, 1)

        if ($fileReadOk -and (($fileText -join "`n") -match '(?m)^demo\.revision=r2\r?$')) {
            if (-not $volumeSeen.ContainsKey($podName)) {
                $volumeSeen[$podName] = $elapsed
                "volume: pod=$podName revision=r2 observedAfter=$($elapsed)s"
            }
        }

        if (-not $portsByPod.ContainsKey($podName)) {
            throw "Pod changed or port-forward does not match: $podName"
        }

        try {
            $uri = "http://localhost:" + $portsByPod[$podName] + "/demo/config"
            $live = Invoke-RestMethod -Uri $uri -TimeoutSec 3 -ErrorAction Stop

            if ($live.pod -ne $podName) {
                throw "Unexpected Pod identity"
            }

            if ($live.revision -eq "r2" -and -not $appSeen.ContainsKey($podName)) {
                $elapsed = [math]::Round(([DateTimeOffset]::UtcNow - $updateStarted).TotalSeconds, 1)
                $appSeen[$podName] = $elapsed
                "application: pod=$podName revision=r2 observedAfter=$($elapsed)s"
            }
        }
        catch {
            "probe failed for pod=$podName : $($_.Exception.Message)"
        }
    }

    if ($volumeSeen.Count -eq $pods.Count -and $appSeen.Count -eq $pods.Count) {
        break
    }

    Start-Sleep -Seconds 2
} while ([DateTimeOffset]::UtcNow -lt $deadline)

foreach ($podName in $pods) {
    [pscustomobject]@{
        Pod = $podName
        VolumeObservedSeconds = $volumeSeen[$podName]
        ApplicationObservedSeconds = $appSeen[$podName]
    }
}
~~~

Khoảng lấy mẫu là 2 giây cộng thời gian thực thi lệnh. Đây là thời điểm **quan sát lần đầu**, không phải số đo chính xác đến mili giây. Ô trống trong bảng kết quả nghĩa là chưa xác nhận được trạng thái tương ứng trong thời gian chờ.

Lập bảng từ kết quả thật:

| Pod | Tệp có `r2` sau bao lâu? | Ứng dụng trả `r2` sau bao lâu? | UID/restart có đổi? |
| --- | --- | --- | --- |
| Pod A | Điền số đo | Điền số đo | Điền quan sát |
| Pod B | Điền số đo | Điền số đo | Điền quan sát |

Kiểm tra thêm bằng `kubectl -n sck-lab get pods -l app=catalog-api`. Nếu ứng dụng khởi động lại hoặc Pod được thay thế, revision mới có thể đến từ đọc cấu hình lúc startup; không dùng mẫu đó để chứng minh refresh động thành công.

Với delay 45 giây, kỳ vọng thực nghiệm là tệp đổi trước khi ứng dụng nhận refresh. Thời điểm ứng dụng trả `r2` còn gồm discovery, gửi HTTP, xử lý refresh và lần gọi quan sát tiếp theo.

## 9. Diễn giải và thử delay khác

| Tệp trong Pod | Endpoint ứng dụng | Diễn giải ban đầu |
| --- | --- | --- |
| `r1` | `r1` | Chưa có dữ liệu mới trên volume hoặc mount sai |
| `r2` | `r1` | Có thể refresh quá sớm, chưa nhận refresh hoặc bean/nguồn cấu hình chưa đúng |
| `r2` | `r2` | Pod này đã áp dụng; cần kiểm tra các Pod còn lại |

Có thể thử lần tiếp theo với `1000 ms` để tăng khả năng tái hiện refresh sớm. Chỉ thay một yếu tố mỗi lần, chờ Watcher sẵn sàng rồi dùng revision mới như `r3`. Sửa cả revision mong đợi trong vòng quan sát.

Delay ngắn không bảo đảm luôn thất bại: volume có thể cập nhật nhanh trong lần đó. Cần dựa vào thứ tự các mốc thực tế. Tránh cập nhật dồn dập khi đang đo, vì khó xác định revision nào được đọc bởi mỗi thông báo.

Nếu tệp đã mới nhưng endpoint vẫn cũ, có thể chẩn đoán bằng refresh thủ công sau khi xác nhận volume:

~~~powershell
Invoke-RestMethod -Method Post -Uri http://localhost:18081/actuator/refresh
Invoke-RestMethod http://localhost:18081/demo/config
~~~

Nếu Pod A sau đó trả revision mới, kết quả gợi ý vấn đề nằm ở thời điểm hoặc đường truyền thông báo tự động. Đối chiếu log để phân biệt. Lần đo có refresh thủ công không còn chứng minh luồng Watcher tự động.

Sau khi tìm được ứng viên, lặp lại với revision mới, tải đại diện và đủ mẫu. Ghi số Pod áp dụng thành công, thời gian lớn nhất và các lần vượt ngân sách, thay vì chỉ ghi trung bình.

## 10. Những lỗi không thể sửa bằng cách tăng delay

### Mount bằng subPath hoặc biến môi trường

Kubernetes nêu rõ ConfigMap mount bằng `subPath` không nhận cập nhật tự động; giá trị lấy qua biến môi trường cũng cần khởi động lại Pod để cập nhật. Chờ lâu hơn không thay đổi đường phân phối này. Xem [giới hạn cập nhật ConfigMap](https://kubernetes.io/docs/concepts/configuration/configmap/#mounted-configmaps-are-updated-automatically).

Với Secret, giới hạn `subPath` tương tự được mô tả trong [tài liệu Secrets](https://kubernetes.io/docs/concepts/configuration/secret/#using-secrets-as-files-from-a-pod). Khi quan sát Secret, dùng mã phiên bản không nhạy cảm hoặc phép kiểm tra phù hợp; không in giá trị bí mật để đo độ trễ.

### Watcher không nhận sự kiện hoặc không tìm được instance

Kiểm tra label, namespace, quyền RBAC, ánh xạ tên Service và endpoint sẵn sàng. Không có thông báo hợp lệ thì khoảng chờ không thể tạo ra refresh.

Cấp quyền theo tài nguyên và namespace thực sự cần. Ứng dụng đọc volume không đồng nghĩa phải tự gọi Kubernetes API; quyền API của Watcher và cách ứng dụng tiêu thụ tệp là hai vấn đề riêng.

### Endpoint refresh không gọi được

HTTP `401/403` cần kiểm tra quyền truy cập; `404` cần kiểm tra classpath, exposure, đường dẫn và cổng quản trị; timeout cần kiểm tra kết nối và NetworkPolicy. Không diễn giải các lỗi này như bằng chứng volume cần thêm thời gian.

### Nguồn cấu hình hoặc vòng đời bean không đúng

Tệp đổi nhưng thuộc tính vẫn cũ có thể do biến môi trường, profile hoặc một nguồn khác ghi đè. Một trường `@Value` trong singleton thông thường không tự được inject lại chỉ vì tệp đổi.

Nếu cấu hình đi qua cache hoặc client tạo lúc startup, endpoint quan sát đơn giản chưa đủ chứng minh toàn bộ nghiệp vụ đã chuyển. Cần kiểm tra nơi giá trị thực sự được sử dụng.

### Nhiều tài nguyên cập nhật gần nhau

ConfigMap A và Secret B thay đổi riêng không tạo thành giao dịch nguyên tử trên cả hai tài nguyên và mọi Pod chỉ nhờ delay. Thuộc tính này cũng không cam kết gộp sự kiện hoặc bảo đảm mỗi revision đều được ứng dụng sử dụng.

Nếu các giá trị bắt buộc chuyển cùng nhau, thiết kế revision chung và cơ chế xác nhận tương thích, hoặc dùng bộ tài nguyên có tên theo phiên bản kết hợp rollout. Với immutable ConfigMap, cập nhật tại chỗ không phải đường triển khai phù hợp.

## 11. Vận hành và lựa chọn tính năng

Theo dõi revision không nhạy cảm trên từng instance: revision mong đợi, số Pod đã áp dụng và độ trễ hội tụ. Không dùng một phản hồi qua bộ cân bằng tải để kết luận cả Deployment đã cập nhật.

Delay lớn làm tăng thời gian chờ sau thay đổi. Với nhiều cập nhật, cần quan sát tải và hàng đợi xử lý Watcher; không suy ra khả năng gộp hoặc hủy sự kiện từ riêng thuộc tính delay.

Nếu thay đổi cấu hình có thể phá vỡ hợp đồng giữa các replica, cần thiết kế tương thích trong khoảng chuyển tiếp. Readiness có thể được mở rộng theo điều kiện nghiệp vụ khi cần, nhưng probe mặc định không kiểm tra revision.

Dùng Watcher khi ứng dụng cần đổi cấu hình lúc chạy, bean liên quan hỗ trợ refresh và nhóm vận hành chấp nhận khoảng hội tụ đã đo. Nếu cấu hình chỉ cần áp dụng khi phát hành, rollout với cấu hình có phiên bản có thể đơn giản hơn. Với client không hỗ trợ refresh an toàn, khởi động lại có kiểm soát thường dễ xác nhận hơn việc tiếp tục tăng delay.

Không cần thêm Spring Cloud LoadBalancer hay DiscoveryClient vào ứng dụng chỉ để chờ volume. Trong luồng HTTP này, Watcher dùng discovery tìm đích; lựa chọn thư viện phía ứng dụng vẫn dựa trên nhu cầu thực tế.

## 12. Tự kiểm tra

1. **API đã có `r2` nhưng tệp trong Pod vẫn là `r1`. Refresh ngay có chắc áp dụng `r2` không?**  
   Không. Nếu đọc từ volume, Spring vẫn có thể gặp tệp cũ.

2. **Đặt `SPRING_CLOUD_KUBERNETES_CONFIGURATION_WATCHER_REFRESHDELAY=45` có nghĩa là 45 giây không?**  
   Trong ví dụ 3.3.3, số không có đơn vị được hiểu là mili giây. Dùng `45000` cho 45 giây.

3. **Một Pod trả revision mới có chứng minh cả Service đã đồng bộ không?**  
   Chưa. Phải kiểm tra từng replica và nhận diện Pod nhận yêu cầu.

4. **Tệp đã đổi, refresh thủ công làm ứng dụng đổi nhưng luồng tự động không thành công. Cần xem gì?**  
   So sánh thời điểm refresh với thời điểm tệp đổi, đồng thời kiểm tra discovery, mạng, endpoint và log Watcher.

5. **Mount bằng `subPath` mà đợi 5 phút vẫn không đổi, có nên tăng delay tiếp không?**  
   Cần đổi cách mount hoặc triển khai lại Pod theo cơ chế phù hợp; delay không sửa giới hạn của `subPath`.

6. **Chọn 45 giây sau vài lần đo có tạo ra bảo đảm tuyệt đối không?**  
   Không. Đó là ứng viên vận hành cần kiểm chứng bằng dữ liệu đại diện và theo dõi khi môi trường thay đổi.

Tiêu chí hoàn thành thực hành là xác nhận revision mới ở cả tệp và hành vi của từng Pod, giải thích được các mốc thời gian và lý do chọn độ trễ. Chỉ nhận HTTP thành công hoặc nhìn thấy ConfigMap đổi trên API chưa đáp ứng tiêu chí này.
