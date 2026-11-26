# Port-forward và truy cập endpoint phục vụ kiểm chứng

Một Pod đã ở trạng thái `Running`, nhưng bạn vẫn cần biết ứng dụng Spring có trả lời HTTP không, đã nạp đúng cấu hình chưa và instance nào đang phục vụ yêu cầu. Trong phát triển cục bộ, `kubectl port-forward` tạo một đường truy cập tạm thời từ máy làm việc đến cổng TCP của Pod để trả lời những câu hỏi cụ thể đó.

Bài học thuộc chương **Phát triển cục bộ** của module **SPRING_CLOUD_KUBERNETES**. Các ví dụ gắn việc truy cập endpoint với kiểm chứng ConfigMap, Secret, DiscoveryClient, Spring Cloud LoadBalancer và Configuration Watcher. Mục tiêu là chọn phép kiểm tra phù hợp, hiểu bằng chứng thu được và biết khi nào phải kiểm tra thêm từ bên trong cluster.

Sau bài học, bạn có thể:

- Phân biệt cổng cục bộ, cổng Service, `targetPort` và cổng ứng dụng.
- Chọn đúng Pod, Deployment hoặc Service khi mở phiên chuyển tiếp.
- Gọi endpoint nghiệp vụ và endpoint sức khỏe trên cổng tương ứng.
- Kiểm tra quyền của người chạy lệnh, tách biệt với quyền của ServiceAccount ứng dụng.
- Ghi nhận kết quả theo Pod và tránh kết luận quá phạm vi phép thử.

## 1. Đường đi của một yêu cầu qua port-forward

Mô hình quan sát đơn giản:

~~~mermaid
flowchart LR
    C["curl hoặc trình duyệt trên máy làm việc"] --> L["127.0.0.1:18080"]
    L --> K["Tiến trình kubectl port-forward"]
    K --> A["Kubernetes API server"]
    A --> P["Đường chuyển tiếp đến Pod đã chọn"]
    P --> S["Ứng dụng Spring trên cổng 8080"]
~~~

Máy làm việc cần truy cập được API server bằng kubeconfig hợp lệ. Máy đó không nhất thiết phải có route trực tiếp đến Pod IP hoặc ClusterIP. Phiên chuyển tiếp phụ thuộc vào tiến trình `kubectl` và kết nối với cluster; đóng terminal hoặc mất kết nối có thể làm phiên kết thúc.

Cú pháp tổng quát:

~~~text
kubectl port-forward TYPE/NAME LOCAL_PORT:REMOTE_PORT
~~~

Ví dụ:

~~~powershell
kubectl -n spring-cloud-lab port-forward pod/catalog-example 18080:8080 --address 127.0.0.1
~~~

Ở ví dụ này, `catalog-example` chỉ là tên minh họa, phải thay bằng tên Pod thực. Trình duyệt truy cập `http://127.0.0.1:18080`; tiến trình Spring bên Pod vẫn nghe cổng `8080`.

Port-forward hỗ trợ TCP. Nó không tự chuyển HTTP thành HTTPS, không đổi URL path và không bổ sung thông tin xác thực của ứng dụng. Các giới hạn giao thức và quyền truy cập được mô tả trong [hướng dẫn port-forward của Kubernetes](https://kubernetes.io/docs/tasks/access-application-cluster/port-forward-access-application-cluster/).

## 2. Chuẩn bị một tình huống kiểm chứng rõ ràng

Các lệnh trong bài dùng PowerShell và giả định bạn đã có một ứng dụng Spring triển khai trong cluster phát triển:

| Thành phần | Giá trị dùng trong ví dụ |
| --- | --- |
| Context | `docker-desktop`, thay theo cluster thực của bạn |
| Namespace | `spring-cloud-lab` |
| Deployment | `catalog` |
| Nhãn chọn Pod | `app.kubernetes.io/name=catalog` |
| Service | `catalog`, có selector trỏ tới các Pod của ứng dụng |
| Cổng HTTP của ứng dụng | `8080` |
| Cổng management riêng | `8081` |
| Cổng Service | `80`, có tên `http` |
| Cổng trên máy làm việc | `18080` cho ứng dụng, `18081` cho management |

Ứng dụng cần có Web starter và Actuator để chạy các ví dụ HTTP và health. Spring Cloud Kubernetes chỉ cần cho những tính năng ứng dụng thực sự sử dụng, chẳng hạn đọc ConfigMap qua API hoặc DiscoveryClient. Riêng thao tác port-forward không yêu cầu thêm starter Spring Cloud Kubernetes vào ứng dụng.

Bài học không giả định mọi dự án đều có sẵn endpoint chẩn đoán. Mục 6 cung cấp một endpoint nhỏ để bạn bổ sung trong profile phòng thực hành nếu cần. Không gọi một đường dẫn chưa được triển khai rồi coi HTTP 404 là lỗi port-forward.

### 2.1. Cấu hình cổng và health của ứng dụng

Cấu hình minh họa cho ứng dụng Spring Boot có Actuator:

~~~yaml
spring:
  application:
    name: catalog

server:
  port: 8080

management:
  server:
    port: 8081
  endpoints:
    web:
      exposure:
        include: health
  endpoint:
    health:
      show-details: never
      probes:
        enabled: true
        add-additional-paths: true
~~~

Với cấu hình này, các đường dẫn dự kiến là:

| Đường dẫn | Cổng trong Pod | Mục đích |
| --- | --- | --- |
| `/actuator/health` | `8081` | Trạng thái health tổng hợp |
| `/actuator/health/liveness` | `8081` | Nhóm liveness |
| `/actuator/health/readiness` | `8081` | Nhóm readiness |
| `/livez` | `8080` | Đường dẫn liveness bổ sung trên cổng chính |
| `/readyz` | `8080` | Đường dẫn readiness bổ sung trên cổng chính |

Ví dụ này dùng các thuộc tính được mô tả trong [Spring Boot Actuator — Kubernetes Probes](https://docs.spring.io/spring-boot/3.5/reference/actuator/endpoints.html#actuator.endpoints.kubernetes-probes). Khi áp dụng, đối chiếu với phiên bản Spring Boot của dự án. Nếu dự án đổi base path, context path, cổng hoặc quy tắc Spring Security, URL và quyền truy cập phải theo cấu hình thực.

Nếu ứng dụng không tách management port, bỏ `management.server.port` và truy cập các endpoint Actuator trên cổng chính. Không mở một cổng `8081` mà ứng dụng không thực sự lắng nghe.

### 2.2. Cổng trong Pod template và Service

Phần liên quan trong container spec của ứng dụng:

~~~yaml
ports:
  - name: http
    containerPort: 8080
  - name: management
    containerPort: 8081
env:
  - name: POD_NAME
    valueFrom:
      fieldRef:
        fieldPath: metadata.name
~~~

Khai báo `containerPort` mô tả cổng; nó không khởi động HTTP server. Ứng dụng vẫn phải bind đúng cổng theo cấu hình Spring.

Service minh họa:

~~~yaml
apiVersion: v1
kind: Service
metadata:
  name: catalog
  namespace: spring-cloud-lab
spec:
  selector:
    app.kubernetes.io/name: catalog
  ports:
    - name: http
      port: 80
      targetPort: http
      protocol: TCP
~~~

Ở đây, `targetPort: http` tham chiếu đến cổng tên `http` trong Pod, tức `8080`. Service chỉ khai báo cổng ứng dụng; chưa khai báo cổng management.

## 3. Chốt context, namespace và quyền truy cập

### 3.1. Kiểm tra đúng cluster trước khi mở phiên

~~~powershell
kubectl config current-context
kubectl config get-contexts
~~~

Sau khi xác định context phát triển, khai báo rõ:

~~~powershell
$kubeContext = "docker-desktop"
$namespace = "spring-cloud-lab"

kubectl --context $kubeContext -n $namespace get deployment/catalog
kubectl --context $kubeContext -n $namespace get service/catalog -o yaml
kubectl --context $kubeContext -n $namespace get pods -l app.kubernetes.io/name=catalog -o wide
~~~

Thay `docker-desktop` nếu cluster của bạn có tên khác. Trong các terminal chạy lệnh Kubernetes tiếp theo, khai báo lại hai biến này. Biến PowerShell không tự được chia sẻ giữa các cửa sổ terminal.

Việc gắn `--context` và `-n` vào lệnh giúp phiên kiểm chứng không phụ thuộc vào một lần đổi context mặc định ở cửa sổ khác.

### 3.2. Phân biệt hai danh tính Kubernetes

Có hai luồng quyền độc lập:

| Luồng | Danh tính | Quyền liên quan |
| --- | --- | --- |
| Máy làm việc mở port-forward | Người dùng hoặc danh tính trong kubeconfig | Đọc tài nguyên đích và truy cập `pods/portforward` |
| Ứng dụng gọi Kubernetes API | ServiceAccount của Pod, khi ứng dụng dùng danh tính đó | Đọc/theo dõi đúng ConfigMap, Secret, Service hoặc EndpointSlice cần thiết |

Bạn mở được tunnel không có nghĩa ServiceAccount ứng dụng được phép đọc ConfigMap. Ngược lại, ứng dụng đọc được Secret không chứng minh tài khoản của bạn có quyền port-forward.

Kiểm tra quyền của danh tính đang dùng:

~~~powershell
kubectl --context $kubeContext -n $namespace auth can-i get pods
kubectl --context $kubeContext -n $namespace auth can-i list pods
kubectl --context $kubeContext -n $namespace auth can-i get services
kubectl --context $kubeContext -n $namespace auth can-i get deployments.apps
kubectl --context $kubeContext -n $namespace auth can-i create pods --subresource=portforward
kubectl --context $kubeContext -n $namespace auth can-i get pods --subresource=portforward
~~~

Các kiểm tra đọc Service hoặc Deployment tương ứng với cách chọn tài nguyên ở mục 4. Tùy giao thức và phiên bản client/server, cần chú ý cả quyền `get` và `create` trên subresource. Kubernetes đã bổ sung kiểm tra quyền `create` cho yêu cầu WebSocket của các subresource tương tác; không suy rằng quyền `get` luôn đủ. Xem [thay đổi kiểm tra quyền port-forward của Kubernetes](https://github.com/kubernetes/kubernetes/pull/134577) và [cú pháp kubectl auth can-i](https://kubernetes.io/docs/reference/kubectl/generated/kubectl_auth/kubectl_auth_can-i/).

Nếu nhận `Forbidden`, xem chính xác tài nguyên, namespace và verb trong thông báo rồi sửa Role/RoleBinding theo phạm vi được cấp. Không thêm quyền đọc Secret chỉ để giải quyết lỗi mở tunnel. Quyền xem log hoặc EndpointSlice, nếu dùng ở các bước sau, cũng là quyền đọc riêng.

## 4. Chọn tài nguyên đích và hiểu ánh xạ cổng

### 4.1. Chọn một Pod cụ thể để kết quả có danh tính rõ ràng

Liệt kê Pod rồi nhập tên chính xác:

~~~powershell
kubectl --context $kubeContext -n $namespace get pods -l app.kubernetes.io/name=catalog -o wide

$podName = Read-Host "Nhap chinh xac ten Pod catalog can kiem chung"
kubectl --context $kubeContext -n $namespace get pod $podName -o wide
kubectl --context $kubeContext -n $namespace wait --for=condition=Ready "pod/$podName" --timeout=120s
~~~

Lệnh `wait` hữu ích khi mục tiêu là kiểm tra một instance sẵn sàng. Nếu bạn đang điều tra Pod chưa Ready, vẫn có thể thử port-forward khi Pod và tiến trình cho phép, nhưng phải ghi rõ tình trạng đó.

Trong terminal A:

~~~powershell
kubectl --context $kubeContext -n $namespace port-forward "pod/$podName" 18080:8080 18081:8081 --address 127.0.0.1
~~~

Đầu ra dự kiến:

~~~text
Forwarding from 127.0.0.1:18080 -> 8080
Forwarding from 127.0.0.1:18081 -> 8081
~~~

Giữ terminal A đang chạy. Dùng terminal B để gửi HTTP request. Dòng `Forwarding from` cho biết listener đã được tạo; bạn vẫn cần gửi yêu cầu để kiểm tra ứng dụng ở phía sau.

### 4.2. Chọn Deployment khi chỉ cần một instance để thử nhanh

~~~powershell
kubectl --context $kubeContext -n $namespace port-forward deployment/catalog 18080:8080 18081:8081 --address 127.0.0.1
~~~

Kubectl chọn một Pod phù hợp. Phiên không luân phiên qua mọi replica. Khi Pod đã chọn kết thúc, bạn cần chạy lại lệnh; không coi đây là cơ chế tự chuyển sang replica khác. Hành vi chọn Pod và kết thúc phiên được nêu trong [tham chiếu kubectl port-forward](https://kubernetes.io/docs/reference/kubectl/generated/kubectl_port-forward/).

Khi cần điều tra một replica lệch cấu hình, hãy dùng tên Pod cụ thể và kiểm tra trường `pod` trong phản hồi chẩn đoán.

### 4.3. Chọn Service và dùng cổng của Service

Với Service ở mục 2:

~~~powershell
kubectl --context $kubeContext -n $namespace port-forward service/catalog 18080:http --address 127.0.0.1
~~~

Hoặc:

~~~powershell
kubectl --context $kubeContext -n $namespace port-forward service/catalog 18080:80 --address 127.0.0.1
~~~

Hai lệnh là phương án thay thế, không chạy đồng thời trên cùng cổng local.

| Thành phần ánh xạ | Giá trị |
| --- | --- |
| Cổng trên máy làm việc | `18080` |
| Cổng được chọn trên Service | `http`, có `port: 80` |
| Cổng đích trong Pod đã chọn | `targetPort: http`, tương ứng `8080` |

Với `service/catalog`, không thay cổng phía phải bằng `8080` chỉ vì Spring nghe `8080`: Service trong ví dụ không có `port: 8080`. Tương tự, `18081:8081` qua Service này không hợp lệ vì Service chưa khai báo cổng management. Muốn kiểm tra management, dùng Pod hoặc Deployment như trên.

Port-forward đến Service dùng thông tin Service để chọn Pod và ánh xạ cổng; nó không gửi yêu cầu qua ClusterIP như một client trong cluster. Do đó, phép thử này chưa kiểm chứng đường đi qua Service, DNS hoặc sự phân phối tải giữa các backend.

Service không có selector và `ExternalName` không phù hợp với cách chọn Pod này. Giới hạn đó được giải thích trong [Kubernetes — Service không có selector](https://kubernetes.io/docs/concepts/services-networking/service/#services-without-selectors).

### 4.4. Dùng một cổng local khác hoặc để kubectl chọn

Nếu `18080` đã bị dùng, có thể đổi:

~~~powershell
kubectl --context $kubeContext -n $namespace port-forward "pod/$podName" 28080:8080 --address 127.0.0.1
~~~

Hoặc để kubectl chọn một cổng local còn trống:

~~~powershell
kubectl --context $kubeContext -n $namespace port-forward "pod/$podName" :8080 --address 127.0.0.1
~~~

Đọc cổng thực trong đầu ra rồi dùng đúng URL tương ứng. Không giữ nguyên `18080` trong lệnh HTTP sau khi đã đổi ánh xạ.

## 5. Gửi HTTP request và đọc đúng tín hiệu

Với phiên Pod ở mục 4.1 đang chạy, mở terminal B:

~~~powershell
curl.exe --noproxy "*" --connect-timeout 3 --max-time 10 -i http://127.0.0.1:18081/actuator/health
curl.exe --noproxy "*" --connect-timeout 3 --max-time 10 -i http://127.0.0.1:18081/actuator/health/readiness
curl.exe --noproxy "*" --connect-timeout 3 --max-time 10 -i http://127.0.0.1:18080/readyz
~~~

Trên Windows, dùng `curl.exe` để gọi chương trình curl, tránh nhầm với alias `curl` của một số phiên PowerShell. `--noproxy "*"` giúp các request này không đi qua HTTP proxy trên máy làm việc. Hai tùy chọn timeout giữ phép thử có thời gian chờ hữu hạn.

Một phản hồi minh họa:

~~~http
HTTP/1.1 200
Content-Type: application/vnd.spring-boot.actuator.v3+json

{"status":"UP"}
~~~

HTTP header và body thực tế có thể khác theo phiên bản và cấu hình. Điều cần kiểm tra là mã HTTP, nội dung health và endpoint thực sự được gọi.

| Kết quả | Ý nghĩa ban đầu |
| --- | --- |
| Có HTTP response | Đã có thành phần HTTP trả lời qua đường vừa mở |
| `200` với JSON health phù hợp | Endpoint health tương ứng trả trạng thái thành công |
| `401` hoặc `403` | Yêu cầu gặp chính sách xác thực/phân quyền HTTP |
| `404` | Có HTTP server trả lời nhưng không tìm thấy tài nguyên theo URL đó |
| `503` từ health endpoint | Xem trạng thái health và log; không mặc định tunnel bị hỏng |
| Lỗi kết nối, không có HTTP status | Kiểm tra listener local, tiến trình chuyển tiếp và cổng đích |

Nếu có sidecar hoặc proxy trong Pod, một HTTP response có thể đến từ thành phần đó. Xác nhận nội dung nghiệp vụ và danh tính instance để biết yêu cầu đã đến đúng ứng dụng.

Với curl, lệnh chỉ dùng `-i` không tự coi HTTP 4xx/5xx là lỗi tiến trình. Khi cần điều kiện thất bại cho một bước kiểm tra tự động, có thể dùng:

~~~powershell
curl.exe --noproxy "*" --connect-timeout 3 --max-time 10 --silent --show-error --fail http://127.0.0.1:18081/actuator/health/readiness

if ($LASTEXITCODE -ne 0) {
    throw "Khong dat phep kiem tra HTTP readiness"
}
~~~

Mã thoát thành công của lệnh HTTP vẫn chưa thay thế việc kiểm tra body hoặc kết quả nghiệp vụ. Chẳng hạn một trang đăng nhập trả HTTP 200 không phải bằng chứng endpoint nghiệp vụ đã thành công.

## 6. Endpoint nhỏ để nhận diện Pod và cấu hình đã đọc

Một marker không nhạy cảm giúp kiểm tra “request này đến instance nào?” và “instance đó đang đọc giá trị cấu hình nào?”. Ví dụ dưới đây dùng Spring MVC và chỉ đăng ký trong profile `lab`:

~~~java
package com.example.catalog;

import java.util.Map;

import org.springframework.context.annotation.Profile;
import org.springframework.core.env.Environment;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@Profile("lab")
@RestController
public class RuntimeCheckController {

    private final Environment environment;

    public RuntimeCheckController(Environment environment) {
        this.environment = environment;
    }

    @GetMapping("/api/debug/runtime")
    public Map<String, String> runtime() {
        return Map.of(
            "service", environment.getProperty(
                "spring.application.name", "catalog"),
            "pod", environment.getProperty("POD_NAME", "unknown"),
            "configRevision", environment.getProperty(
                "demo.config-revision", "unset"),
            "message", environment.getProperty(
                "demo.message", "unset")
        );
    }
}
~~~

Đặt class trong package được ứng dụng component-scan, kích hoạt profile `lab` trong Pod thử nghiệm và bảo đảm Spring Security cho phép người kiểm chứng truy cập theo chính sách của ứng dụng. Khi dùng `SPRING_PROFILES_ACTIVE`, giữ cả những profile khác mà môi trường đang cần.

`POD_NAME` lấy từ Downward API ở mục 2.2. Hai thuộc tính `demo.config-revision` và `demo.message` do bạn định nghĩa trong nguồn cấu hình đang thử. Ví dụ dữ liệu không nhạy cảm:

~~~yaml
demo:
  config-revision: cfg-001
  message: Xin chao tu ConfigMap
~~~

Các giá trị này cần được ứng dụng nạp bằng cơ chế đã chọn. Có dữ liệu trong ConfigMap chưa có nghĩa Spring đã đưa dữ liệu vào `Environment`.

Nếu dự án đã cấu hình Spring Cloud Kubernetes Config để đọc qua API, kiểm tra đúng starter, namespace, tên nguồn, quyền ServiceAccount và cách import cấu hình của phiên bản đang dùng. Cơ chế Config Data sử dụng `spring.config.import: "kubernetes:"`; không chỉ thêm import mà bỏ qua các điều kiện còn lại. Xem [Spring Cloud Kubernetes — PropertySource implementations](https://docs.spring.io/spring-cloud-kubernetes/reference/property-source-config.html).

Gọi endpoint qua cổng ứng dụng:

~~~powershell
curl.exe --noproxy "*" --connect-timeout 3 --max-time 10 -i http://127.0.0.1:18080/api/debug/runtime
~~~

Phản hồi minh họa, trong đó tên Pod thực sẽ khác:

~~~json
{
  "service": "catalog",
  "pod": "catalog-7b68f9894c-2whtp",
  "configRevision": "cfg-001",
  "message": "Xin chao tu ConfigMap"
}
~~~

Đây là mã endpoint do bài học đề xuất, không phải endpoint có sẵn của Actuator hoặc Spring Cloud Kubernetes. Nó đọc `Environment` khi nhận request. Kết quả không tự chứng minh một bean đã bind cấu hình từ trước hoặc một tài nguyên như connection pool đã được cập nhật tương ứng.

Không trả về toàn bộ `Environment`, token, mật khẩu hoặc nội dung Secret. Với Secret, ưu tiên kiểm chứng hành vi cần bí mật đó, chẳng hạn một thao tác kết nối được thiết kế cho lab, rồi chỉ trả kết quả phù hợp. Một endpoint kiểm chứng không cần trở thành nơi hiển thị thông tin xác thực.

## 7. Kiểm chứng sức khỏe Pod theo từng lớp

Ba câu hỏi cần tách biệt:

1. Tiến trình có đang chạy và nhận kết nối không?
2. Ứng dụng tự đánh giá liveness/readiness ra sao?
3. Kubernetes đang ghi nhận Pod và đưa Pod vào tập backend như thế nào?

Quan sát từ Kubernetes, trong terminal có khai báo `$kubeContext`, `$namespace` và `$podName`:

~~~powershell
kubectl --context $kubeContext -n $namespace get pod $podName -o wide
kubectl --context $kubeContext -n $namespace describe pod $podName
kubectl --context $kubeContext -n $namespace get endpointslices -l kubernetes.io/service-name=catalog -o yaml
kubectl --context $kubeContext -n $namespace logs "pod/$podName" --all-containers=true --tail=100
~~~

Nếu Pod có nhiều container, khi điều tra cụ thể nên chọn `-c` với đúng tên container để dễ theo dõi log. Việc đọc các tài nguyên trên cần quyền tương ứng.

Đối chiếu các bằng chứng:

| Bằng chứng | Câu hỏi được hỗ trợ trả lời |
| --- | --- |
| Pod `Running` | Pod đã vào pha chạy; chưa đủ kết luận endpoint sẵn sàng |
| Condition `Ready` và event probe | Kubernetes đang quan sát readiness của Pod ra sao |
| `/actuator/health/readiness` | Nhóm readiness của ứng dụng đang trả gì |
| `/readyz` trên cổng chính | Đường health bổ sung trên web server chính có trả lời không |
| Runtime marker | Đúng Pod và giá trị mẫu đang được đọc hay chưa |
| EndpointSlice và điều kiện của endpoint | Service đang có những backend nào, với trạng thái gì |

Nếu management chạy trên web server riêng, health ở cổng management có thể thành công dù web server chính gặp vấn đề. Đó là lý do bài học kiểm tra cả cổng chính.

Nội dung nhóm readiness do ứng dụng cấu hình quyết định; không mặc định nó đã kiểm tra mọi dịch vụ phụ thuộc. Phần phân nhóm và ý nghĩa health cần theo [tài liệu health của Spring Boot](https://docs.spring.io/spring-boot/3.5/reference/actuator/endpoints.html#actuator.endpoints.health).

Port-forward trực tiếp có thể truy cập một Pod chưa Ready nếu Pod và tiến trình vẫn cho phép. Vì vậy, “gọi qua localhost được” và “Pod đang đủ điều kiện nhận lưu lượng Service” là hai quan sát phải đối chiếu riêng.

## 8. Dùng endpoint để kiểm chứng tính năng Spring Cloud Kubernetes

### 8.1. ConfigMap: kiểm tra giá trị có hiệu lực

Một quy trình phòng thực hành:

1. Xác định nguồn cấu hình mà ứng dụng đang đọc: API, file mount hoặc biến môi trường.
2. Đặt marker ban đầu, chẳng hạn `cfg-001`, và ghi lại Pod đích.
3. Gọi `/api/debug/runtime`, so sánh giá trị với mong đợi.
4. Thay đổi cấu hình bằng quy trình của môi trường lab.
5. Chờ hoặc tạo lại Pod theo cơ chế cập nhật đã chọn.
6. Gọi lại, kiểm tra cả marker và tên Pod.

Nếu cấu hình được cấp bằng biến môi trường lúc tạo container, đừng mong một lần sửa ConfigMap sẽ tự thay biến môi trường của container đang chạy. Nếu dùng file mount, cần phân biệt file đã thay đổi với việc Spring đã nạp lại và đối tượng nghiệp vụ đã sử dụng giá trị mới.

Giả sử health là `UP` nhưng `configRevision` vẫn `unset`: trước hết kiểm tra tên thuộc tính, nguồn đã nạp, profile, namespace, cấu hình import và log. Thử một cổng local khác không giải quyết việc thiếu property source.

### 8.2. Secret: kiểm tra hành vi, không in nội dung

Ví dụ ứng dụng cần một Secret để kết nối tới dịch vụ phụ thuộc. Kết quả mong đợi có thể là thao tác nghiệp vụ đọc một bản ghi thử nghiệm thành công hoặc health indicator phù hợp báo kết nối hoạt động.

Không dùng response chứa mật khẩu làm bằng chứng. Cũng cần phân biệt:

- Người dùng máy làm việc có mở được port-forward hay không.
- Ứng dụng có nhận được Secret qua cơ chế đã thiết kế hay không.
- Thông tin xác thực đó có còn được hệ thống đích chấp nhận hay không.

Một lỗi `Forbidden` trong log Kubernetes client của ứng dụng thuộc luồng API và ServiceAccount. HTTP 403 mà bạn nhận từ endpoint ứng dụng cần được điều tra trong luồng HTTP tương ứng; hai lỗi có thể có nguyên nhân hoàn toàn khác nhau.

### 8.3. DiscoveryClient: tìm được địa chỉ chưa chắc gọi được

Spring Cloud Kubernetes DiscoveryClient có thể trả về instance hoặc endpoint trong mạng cluster. Xem [Spring Cloud Kubernetes — DiscoveryClient](https://docs.spring.io/spring-cloud-kubernetes/reference/discovery-client.html).

Một ứng dụng Spring chạy trực tiếp trên laptop có thể gọi Kubernetes API thành công nhưng không có route tới Pod IP mà DiscoveryClient trả về. Port-forward một Pod không viết lại danh sách instance và không tạo route cho mọi Pod IP.

Vì vậy, cần xác định ứng dụng gọi downstream đang chạy ở đâu:

- Nếu caller chạy trong cluster, mở port-forward vào caller rồi gọi endpoint của caller có thực hiện lời gọi downstream. Request downstream vẫn xuất phát từ Pod caller.
- Nếu caller chạy trên laptop, dùng base URL local được cấu hình rõ cho bài thử hoặc một môi trường phát triển có kết nối mạng phù hợp.
- Khi thay downstream bằng URL local, ghi rõ phép thử đang kiểm tra đường gọi với URL đó; chưa đủ chứng minh cơ chế chọn instance từ DiscoveryClient.

### 8.4. Spring Cloud LoadBalancer: mở tunnel vào đúng phía cần kiểm tra

Giả sử luồng nghiệp vụ là:

~~~text
caller-service -> Spring Cloud LoadBalancer -> một instance catalog
~~~

Nếu port-forward thẳng vào `catalog`, bạn đã đến backend và chưa thực hiện đoạn chọn instance của caller.

Để kiểm chứng hành vi của caller, mở phiên vào Pod caller, gọi endpoint nghiệp vụ của caller, rồi đối chiếu log hoặc marker backend được trả về. Chỉ thực hiện cách này khi endpoint đó thực sự dùng client đã cấu hình load balancing.

Ngay cả khi gửi nhiều request, không bắt buộc quan sát được sự xen kẽ hoàn hảo giữa mọi replica. Chiến lược cân bằng, cache danh sách instance, retry và số backend hợp lệ đều ảnh hưởng kết quả. Cần đọc cấu hình thực tế và dùng bằng chứng ở caller.

Spring Cloud Kubernetes hỗ trợ các chế độ load balancing `POD` và `SERVICE`; hai chế độ có đường gọi khác nhau. Đối chiếu [Spring Cloud Kubernetes — LoadBalancer](https://docs.spring.io/spring-cloud-kubernetes/reference/load-balancer.html) trước khi đặt kỳ vọng cho phép thử. Port-forward không chuyển đổi một chế độ thành chế độ còn lại.

### 8.5. Configuration Watcher: quan sát việc cập nhật ở từng instance

Port-forward là kênh quan sát thuận tiện khi thử Configuration Watcher, nhưng không làm thay công việc của watcher.

Một phép thử có ý nghĩa:

1. Ghi Pod UID và marker cấu hình hiện tại.
2. Thay ConfigMap lab bằng marker mới qua quy trình được phép.
3. Quan sát log watcher, thời điểm phát hiện thay đổi và kết quả thông báo.
4. Gọi lại endpoint của từng Pod, xác nhận marker thay đổi theo cơ chế ứng dụng hỗ trợ.
5. Kiểm tra chức năng sử dụng cấu hình, đồng thời xem Pod có bị thay thế hay không.

Nếu chỉ dùng một phiên `port-forward deployment/catalog`, bạn đang quan sát một Pod. Kết quả đó không đủ kết luận mọi replica đã cập nhật.

Không gọi thủ công endpoint refresh rồi dùng kết quả ấy làm bằng chứng watcher đã tự gửi thông báo. Nếu phép thử cần refresh thủ công, ghi rõ đó là một phép thử riêng.

Watcher cần cấu hình theo dõi, quyền truy cập và cơ chế thông báo phù hợp với phiên bản đang dùng. Nếu dùng refresh qua HTTP, endpoint đích phải được cho phép và truy cập được từ watcher. Chỉ mở `health` như ví dụ đầu bài chưa làm `refresh` xuất hiện. Xem [Spring Cloud Kubernetes — Configuration Watcher](https://docs.spring.io/spring-cloud-kubernetes/reference/spring-cloud-kubernetes-configuration-watcher.html).

Bạn không cần cài watcher chỉ để kiểm tra một ứng dụng nhận cấu hình lúc khởi động. Chọn tính năng dựa trên hành vi cần triển khai và kiểm chứng.

## 9. Chẩn đoán lỗi theo nơi phát sinh

Đi từ phía máy làm việc đến ứng dụng sẽ dễ khoanh vùng hơn việc thay nhiều cấu hình cùng lúc.

| Triệu chứng | Kiểm tra tiếp | Cách xử lý phù hợp |
| --- | --- | --- |
| `address already in use` | Cổng local có tiến trình khác đang nghe | Dừng đúng phiên cũ hoặc chọn cổng local khác |
| `Forbidden` khi mở tunnel | Danh tính kubeconfig, namespace, tài nguyên và verb bị từ chối | Sửa quyền port-forward đúng phạm vi |
| Không tìm thấy Pod hoặc Service | Context, namespace và tên tài nguyên | Liệt kê lại trong đúng cluster |
| Hết thời gian chờ Pod chạy | Trạng thái scheduling, image pull và startup | Xem Pod/event trước khi thử HTTP |
| Service không có cổng được yêu cầu | `spec.ports`, tên cổng, `port`, `targetPort` | Dùng cổng Service đúng hoặc chuyển sang Pod |
| `connection refused` trong terminal tunnel | Spring có nghe đúng cổng không | Kiểm tra startup log, `server.port`, `management.server.port` |
| Tunnel đã dừng sau rollout | Pod được chọn còn tồn tại không | Chọn lại Pod, mở phiên mới và ghi danh tính mới |
| HTTP 404 | Đúng cổng, path, profile và context path chưa | Dùng URL khớp cấu hình ứng dụng |
| HTTP 401/403 | Spring Security hoặc proxy HTTP | Cung cấp thông tin xác thực theo cấu hình lab |
| Health management thành công, API chính thất bại | Cổng chính, web server chính và handler nghiệp vụ | Kiểm tra trực tiếp endpoint trên cổng ứng dụng |
| Runtime marker không đổi | Đúng Pod, nguồn cấu hình và cơ chế cập nhật chưa | Kiểm tra cấu hình có hiệu lực và refresh/rollout |
| Pod truy cập được, client trong cluster thất bại | DNS, Service, readiness, policy và đường mạng thực | Kiểm tra từ caller trong cluster |

Nếu có quyền và cần tìm tiến trình đang dùng cổng local trên Windows:

~~~powershell
Get-NetTCPConnection -LocalPort 18080 -State Listen -ErrorAction SilentlyContinue
~~~

Đọc `OwningProcess` và xác định đúng tiến trình trước khi dừng nó. Không cần dừng ngẫu nhiên các tiến trình Java để khắc phục một phiên port-forward trùng cổng.

Với lỗi kết nối API server, kiểm tra thêm VPN, proxy và kết nối kubeconfig trước khi sửa manifest ứng dụng. Với lỗi HTTP đã có status code, ưu tiên kiểm tra đường dẫn và lớp HTTP đã trả lời.

## 10. HTTP, HTTPS và phạm vi lắng nghe local

Dùng `--address 127.0.0.1` khiến ví dụ chỉ nghe trên IPv4 loopback của máy chạy kubectl. Dùng `127.0.0.1` trong URL cũng tránh nhầm khi `localhost` được ưu tiên phân giải sang IPv6.

Port-forward giữ giao thức mà tiến trình đích đang dùng. Nếu ứng dụng được cấu hình TLS ở cổng `8443`, có thể mở `18443:8443`, nhưng client vẫn phải dùng HTTPS và kiểm tra chứng chỉ theo hostname phù hợp. Không đổi sang HTTP chỉ vì đích truy cập ở máy local.

Nếu cần hostname khớp chứng chỉ trong môi trường lab, curl có thể ánh xạ hostname đó về loopback bằng `--resolve`, với CA tin cậy hoặc `--cacert` tương ứng. Port-forward không tự tạo chứng chỉ cho `127.0.0.1` và không tự kết thúc TLS thay ứng dụng.

Một listener local cũng không thay thế chính sách bảo vệ endpoint ứng dụng. Giữ endpoint chẩn đoán trong phạm vi lab, chỉ trả dữ liệu cần quan sát và đóng phiên khi kiểm chứng xong.

## 11. Ghi nhận bằng chứng và kết thúc phiên

Một bản ghi kiểm chứng nên đủ để người khác hiểu đã thử cái gì:

~~~text
Context: docker-desktop
Namespace: spring-cloud-lab
Target: pod/catalog-7b68f9894c-2whtp
Pod UID: gia-tri-thuc-da-doc-tu-cluster
Forward: 127.0.0.1:18080 -> 8080; 127.0.0.1:18081 -> 8081
Observed at: thoi-diem-thuc-hien
Request: GET /api/debug/runtime
Observed pod: catalog-7b68f9894c-2whtp
Observed configRevision: cfg-001
Readiness: HTTP 200, status UP
Business check: ten-phep-thu-va-ket-qua-thuc
Scope: instance da-chon, qua-port-forward
~~~

Các giá trị trên minh họa cấu trúc ghi nhận, không phải kết quả đã chạy trên cluster của bạn.

Có thể đọc UID và image đã khai báo của Pod:

~~~powershell
kubectl --context $kubeContext -n $namespace get pod $podName -o 'jsonpath={.metadata.uid}'
kubectl --context $kubeContext -n $namespace get pod $podName -o 'jsonpath={.spec.containers[*].image}'
~~~

Khi kết thúc, nhấn **Ctrl+C** trong từng terminal đang chạy port-forward. Gửi lại request với timeout ngắn để xác nhận đường truy cập đó đã đóng. Nếu cổng vẫn trả lời, kiểm tra xem còn phiên chuyển tiếp hoặc tiến trình khác đang nghe hay không. Đóng tunnel không xóa Deployment, Service, Pod hay dữ liệu ứng dụng.

## 12. Bài thực hành

Thực hiện trong cluster phát triển đã chuẩn bị:

1. Ghi context, namespace, tên Pod và UID.
2. Mở một phiên chuyển tiếp hai cổng của Pod.
3. Gọi health, readiness, `/readyz` và endpoint runtime nếu đã bổ sung.
4. Đối chiếu Pod trong response với Pod đã chọn.
5. Dừng phiên, mở lại qua Service bằng cổng tên `http`, rồi giải thích ánh xạ `18080 -> 80 -> 8080` về mặt lựa chọn cổng.
6. Giải thích vì sao truy cập management qua Service hiện tại chưa thực hiện được, dù Pod có cổng `8081`.
7. Nếu có hai replica, mở hai phiên vào hai Pod bằng các cổng local khác nhau và so sánh marker cấu hình.
8. Nếu đang học watcher, thực hiện một thay đổi ConfigMap lab và ghi nhận kết quả của từng instance theo mục 8.5.
9. Dừng mọi phiên port-forward đã mở.

Bài thực hành đạt mục tiêu khi bạn đưa ra được URL đúng, xác định được instance đã trả lời và giải thích được phạm vi bằng chứng. Với một tính năng cần lưu lượng giữa các dịch vụ, bổ sung phép thử từ caller trong cluster để xác nhận phần đường đi mà port-forward chưa quan sát.
