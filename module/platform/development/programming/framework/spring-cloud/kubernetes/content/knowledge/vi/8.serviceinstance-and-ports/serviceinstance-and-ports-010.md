# Kiểm thử ánh xạ cổng và địa chỉ trong các manifest khác nhau

## 1. Mục tiêu và phạm vi

Trong chương **ServiceInstance và cổng** của module **SPRING_CLOUD_KUBERNETES**, bài này xây dựng một quy trình kiểm thử để trả lời câu hỏi: sau khi thay đổi manifest, ứng dụng gọi dịch vụ có nhận được đúng địa chỉ, đúng cổng và đúng giao thức hay không?

Một Service tồn tại, Pod đang Running hoặc `/actuator/health` trả về 200 chưa chứng minh đường gọi nghiệp vụ hoạt động. Cần nối được chuỗi bằng chứng:

```text
Manifest đã được API server chấp nhận
    -> Pod thực sự lắng nghe
    -> Service chọn đúng backend
    -> EndpointSlice chứa đúng địa chỉ và cổng
    -> DiscoveryClient trả về ServiceInstance phù hợp
    -> request từ ứng dụng gọi đến đúng backend
```

Bài thực hành tập trung vào DiscoveryClient, RBAC và trạng thái sẵn sàng của Pod; cuối bài phân biệt thêm đường gọi qua Spring Cloud LoadBalancer. ConfigMap, Secret và Configuration Watcher không phải điều kiện bắt buộc để kiểm tra ánh xạ mạng. Chỉ đưa các thành phần đó vào một ca kiểm thử riêng khi chúng thực sự tham gia thay đổi cấu hình của ứng dụng.

Sau bài học, bạn cần có khả năng:

- Thiết lập dữ liệu kiểm thử mà `port` khác `targetPort`, tránh kết quả đúng do các số cổng tình cờ bằng nhau.
- Đối chiếu từng `ServiceInstance` với đúng nhóm địa chỉ và cổng của EndpointSlice.
- Kiểm thử Service một cổng, nhiều cổng, headless và NodePort.
- Phân biệt lỗi khám phá dịch vụ, lỗi quyền API, lỗi mạng và lỗi ứng dụng.
- Chờ dữ liệu hội tụ sau thay đổi, đồng thời đặt giới hạn thời gian để ca kiểm thử không treo.

Các manifest, đoạn Java và lệnh bên dưới là vật liệu để người học triển khai trong cụm thử nghiệm; các kết quả mẫu là kỳ vọng, không phải biên bản của một lần chạy thực tế.

## 2. Hợp đồng địa chỉ–cổng phải xác định trước

### 2.1. Ba lớp cổng thường bị nhầm

Xét Service công bố cổng 80 và chuyển đến ứng dụng lắng nghe ở 8080:

```yaml
ports:
  - name: http
    port: 80
    targetPort: 8080
    protocol: TCP
```

| Thành phần | Ý nghĩa trong ca thử | Cặp địa chỉ–cổng cần kiểm tra |
| --- | --- | --- |
| Tiến trình ứng dụng | Socket đang mở trong Pod | `PodIP:8080` |
| `containerPort` | Khai báo cổng trong Pod; tên cổng có thể được `targetPort` tham chiếu | Không tự làm tiến trình mở socket |
| `Service.spec.ports[].port` | Cổng của Service | `ServiceDNS:80` hoặc `ClusterIP:80` |
| `targetPort` | Cổng đích, là số hoặc tên cổng của Pod | Được giải thành cổng backend |
| `EndpointSlice.ports[].port` | Cổng cụ thể gắn với các endpoint trong slice đó | 8080 trong ví dụ |
| `nodePort` | Cổng công bố trên node khi dùng NodePort | `NodeIP:nodePort` trên đường truy cập đó |

Kubernetes cho phép `port` khác `targetPort`; khi bỏ `targetPort`, giá trị mặc định theo `port`. Tên trong `targetPort` được đối chiếu với tên cổng của Pod. Đây là cơ sở để thiết kế các biến thể bên dưới. [Tài liệu Service của Kubernetes](https://kubernetes.io/docs/concepts/services-networking/service/).

**Quy tắc kiểm thử:** luôn ghép địa chỉ với cổng thuộc cùng một đường gọi. `PodIP:80` và `ClusterIP:8080` đều có thể sai mặc dù từng con số xuất hiện hợp lệ trong manifest.

### 2.2. Chốt đường gọi đang được kiểm thử

Bài này chọn DiscoveryClient đọc endpoint, không có thành phần tùy biến thay đổi `ServiceInstance`. Với các Service có selector trong bài, kỳ vọng là địa chỉ backend và cổng endpoint đã được giải, ví dụ `PodIP:8080`.

Đường qua DNS Service là một ca độc lập:

```text
Gọi Service:   orders-named.<namespace>.svc:80 -> backend:8080
Gọi endpoint: ServiceInstance.host:ServiceInstance.port -> backend:8080
```

Nếu dự án sử dụng supplier tùy biến, Discovery Server trung gian hoặc chế độ cân bằng tải qua Service, phải ghi rõ hợp đồng khác đó trước khi so sánh. Không áp dụng kỳ vọng của đường endpoint cho mọi loại client.

Ghi lại cho mỗi đợt kiểm thử: phiên bản Kubernetes, Spring Boot, Spring Cloud BOM, Spring Cloud Kubernetes, loại client, namespace, cách đọc Endpoints/EndpointSlice, cấu hình chọn cổng và image digest. Chọn các phiên bản tương thích theo BOM của dự án; không ghép tùy ý các starter thuộc release khác nhau.

## 3. Thiết kế một backend có thể nhận diện

Dùng ứng dụng `orders-backend` có Spring Web và Actuator. Endpoint nghiệp vụ phải cho biết Pod và cổng đã xử lý request; nhờ đó một phản hồi 200 từ dịch vụ khác không làm ca thử vượt qua.

Ví dụ lớp ứng dụng Java, trong package riêng của backend:

```java
package lab.orders;

import java.util.Map;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class OrdersApplication {
    public static void main(String[] args) {
        SpringApplication.run(OrdersApplication.class, args);
    }

    @RestController
    static class IdentityController {
        private final int port;

        IdentityController(@Value("${server.port:8080}") int port) {
            this.port = port;
        }

        @GetMapping("/demo/identity")
        Map<String, Object> identity() {
            return Map.of(
                "app", "orders-backend",
                "pod", System.getenv().getOrDefault("HOSTNAME", "unknown"),
                "port", port
            );
        }
    }
}
```

Manifest sẽ đặt cổng nghiệp vụ là 8080, cổng quản trị là 9090 và bật probe của Actuator. Đảm bảo tiến trình bind vào giao diện Pod, không chỉ `127.0.0.1`.

Phản hồi mong đợi:

```json
{"app":"orders-backend","pod":"orders-backend-abc12-xyz34","port":8080}
```

Tên Pod và IP được cấp động. Test phải lấy chúng từ trạng thái thực tế, không chép các giá trị mẫu thành hằng số.

## 4. Tạo probe Spring đọc DiscoveryClient và gọi từng instance

Probe là ứng dụng Spring Boot riêng, có Spring Web và starter `spring-cloud-starter-kubernetes-fabric8`, cùng phiên bản do BOM quản lý. Không đưa mã probe vào backend. Ví dụ dùng Java có hỗ trợ `record` và `java.net.http.HttpClient`.

Probe trả về dữ liệu khám phá và kết quả HTTP ngay trong cùng Pod gọi dịch vụ. Cách này kiểm tra được đường mạng của chính probe, thay vì suy ra từ máy người phát triển.

```java
package lab.probe;

import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.List;
import java.util.Set;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.discovery.DiscoveryClient;
import org.springframework.cloud.client.discovery.EnableDiscoveryClient;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@SpringBootApplication
@EnableDiscoveryClient
public class ProbeApplication {
    public static void main(String[] args) {
        SpringApplication.run(ProbeApplication.class, args);
    }

    record Result(String serviceId, String host, int port, boolean secure,
                  String uri, String namespace, Integer httpStatus,
                  String body, String error) {}

    @RestController
    static class ProbeController {
        private static final Set<String> ALLOWED = Set.of(
            "orders-equal", "orders-numeric", "orders-named",
            "orders-default", "orders-multi", "orders-headless",
            "orders-nodeport"
        );
        private final DiscoveryClient discovery;
        private final HttpClient http = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(2))
            .followRedirects(HttpClient.Redirect.NEVER)
            .build();

        ProbeController(DiscoveryClient discovery) {
            this.discovery = discovery;
        }

        @GetMapping("/lab/ready")
        String ready() {
            return "ok";
        }

        @GetMapping("/lab/instances/{serviceId}")
        List<Result> instances(@PathVariable("serviceId") String serviceId) {
            if (!ALLOWED.contains(serviceId)) {
                throw new ResponseStatusException(HttpStatus.BAD_REQUEST);
            }
            return discovery.getInstances(serviceId).stream()
                .map(this::inspect)
                .toList();
        }

        private Result inspect(ServiceInstance instance) {
            Integer status = null;
            String body = null;
            String error = null;
            try {
                var target = instance.getUri().resolve("/demo/identity");
                var request = HttpRequest.newBuilder(target)
                    .timeout(Duration.ofSeconds(3))
                    .GET()
                    .build();
                var response = http.send(
                    request, HttpResponse.BodyHandlers.ofString());
                status = response.statusCode();
                body = response.body();
            }
            catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                error = "InterruptedException";
            }
            catch (Exception ex) {
                error = ex.getClass().getSimpleName();
            }
            return new Result(
                instance.getServiceId(), instance.getHost(),
                instance.getPort(), instance.isSecure(),
                instance.getUri().toString(),
                instance.getMetadata().get("k8s_namespace"),
                status, body, error
            );
        }
    }
}
```

`/lab/ready` chỉ cho biết probe tiếp nhận được HTTP; nó không chứng minh backend đã sẵn sàng hoặc cache discovery đã hội tụ. Danh sách rỗng vẫn là một kết quả cần assertion, không phải thành công mặc định.

Probe chỉ cho phép các tên dịch vụ của bài và chỉ gọi đường dẫn cố định. Dùng nó trong namespace thực hành, truy cập chẩn đoán qua port-forward; không công bố endpoint này qua Ingress công cộng. Ví dụ chỉ có vài replica, vì probe gọi tuần tự từng instance và mỗi request đều có timeout.

Không nối chuỗi `"http://" + host + ":" + port` để tạo URI: cách đó dễ sai với IPv6 và bỏ qua `isSecure()`. Probe dùng URI của instance, rồi thay đường dẫn.

## 5. Manifest nền và RBAC theo namespace

Chuẩn bị hai image chứa ứng dụng backend và probe đã mô tả. Thay `registry.example.com/training/...:lab-1` bằng image thực của bạn; khi dùng trong CI nên khóa bằng digest. Manifest minh họa không tự xây dựng image.

Lưu các tài nguyên nền dưới tên `base.yaml` trong thư mục thực hành của người học:

```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: port-mapping-lab
---
apiVersion: v1
kind: ServiceAccount
metadata:
  name: discovery-probe
  namespace: port-mapping-lab
---
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: discovery-reader
  namespace: port-mapping-lab
rules:
  - apiGroups: [""]
    resources: ["services", "endpoints", "pods"]
    verbs: ["get", "list", "watch"]
  - apiGroups: ["discovery.k8s.io"]
    resources: ["endpointslices"]
    verbs: ["get", "list", "watch"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: discovery-reader
  namespace: port-mapping-lab
subjects:
  - kind: ServiceAccount
    name: discovery-probe
    namespace: port-mapping-lab
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: Role
  name: discovery-reader
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders-backend
  namespace: port-mapping-lab
spec:
  replicas: 2
  selector:
    matchLabels:
      app: orders-backend
  template:
    metadata:
      labels:
        app: orders-backend
    spec:
      automountServiceAccountToken: false
      containers:
        - name: app
          image: registry.example.com/training/orders-backend:lab-1
          ports:
            - name: app-http
              containerPort: 8080
            - name: management
              containerPort: 9090
          env:
            - name: SERVER_PORT
              value: "8080"
            - name: MANAGEMENT_SERVER_PORT
              value: "9090"
            - name: MANAGEMENT_ENDPOINT_HEALTH_PROBES_ENABLED
              value: "true"
            - name: MANAGEMENT_ENDPOINTS_WEB_EXPOSURE_INCLUDE
              value: health
          readinessProbe:
            httpGet:
              path: /actuator/health/readiness
              port: management
            periodSeconds: 2
            timeoutSeconds: 1
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: discovery-probe
  namespace: port-mapping-lab
spec:
  replicas: 1
  selector:
    matchLabels:
      app: discovery-probe
  template:
    metadata:
      labels:
        app: discovery-probe
    spec:
      serviceAccountName: discovery-probe
      containers:
        - name: app
          image: registry.example.com/training/discovery-probe:lab-1
          ports:
            - name: http
              containerPort: 8080
          env:
            - name: SERVER_PORT
              value: "8080"
            - name: SPRING_APPLICATION_NAME
              value: discovery-probe
            - name: SPRING_CLOUD_KUBERNETES_DISCOVERY_NAMESPACES_0
              value: port-mapping-lab
            - name: SPRING_CLOUD_KUBERNETES_DISCOVERY_USE_ENDPOINT_SLICES
              value: "true"
            - name: SPRING_CLOUD_KUBERNETES_DISCOVERY_INCLUDE_NOT_READY_ADDRESSES
              value: "false"
          readinessProbe:
            httpGet:
              path: /lab/ready
              port: http
            periodSeconds: 2
            timeoutSeconds: 1
```

Role trên phục vụ lab có thể chuyển giữa hai nguồn endpoint. Nếu triển khai chỉ dùng EndpointSlice và client không cần đọc Endpoints, có thể thu hẹp quyền theo nhu cầu thực tế đã xác minh. Không cấp quyền đọc Secret, sửa ConfigMap hoặc truy cập toàn cụm chỉ để kiểm thử discovery.

Nếu bản Spring Cloud Kubernetes đang dùng không hỗ trợ cấu hình EndpointSlice tương ứng, chọn phiên bản phù hợp hoặc tạo đợt kiểm thử dùng Endpoints riêng. Khi đó phải đối chiếu `subsets[].addresses` cùng `subsets[].ports` của cùng subset, không dùng trạng thái slice làm bằng chứng rằng client đã đọc slice.

Kiểm tra quyền bằng tài khoản người vận hành có quyền impersonation:

```powershell
kubectl auth can-i list services -n port-mapping-lab --as=system:serviceaccount:port-mapping-lab:discovery-probe
kubectl auth can-i watch endpointslices.discovery.k8s.io -n port-mapping-lab --as=system:serviceaccount:port-mapping-lab:discovery-probe
```

Nếu lệnh bị từ chối quyền impersonation, đó là giới hạn của tài khoản chạy lệnh; chưa thể kết luận ServiceAccount probe thiếu quyền. Đối chiếu RoleBinding hoặc nhờ người có quyền kiểm tra.

## 6. Bộ manifest Service có chủ đích

Lưu các Service sau dưới tên `services.yaml`. Chúng cùng chọn hai backend, nhưng tạo ra các đường ánh xạ khác nhau:

```yaml
apiVersion: v1
kind: Service
metadata:
  name: orders-equal
  namespace: port-mapping-lab
spec:
  selector:
    app: orders-backend
  ports:
    - name: http
      port: 8080
      targetPort: 8080
---
apiVersion: v1
kind: Service
metadata:
  name: orders-numeric
  namespace: port-mapping-lab
spec:
  selector:
    app: orders-backend
  ports:
    - name: http
      port: 80
      targetPort: 8080
---
apiVersion: v1
kind: Service
metadata:
  name: orders-named
  namespace: port-mapping-lab
spec:
  selector:
    app: orders-backend
  ports:
    - name: http
      port: 80
      targetPort: app-http
---
apiVersion: v1
kind: Service
metadata:
  name: orders-default
  namespace: port-mapping-lab
spec:
  selector:
    app: orders-backend
  ports:
    - port: 8080
---
apiVersion: v1
kind: Service
metadata:
  name: orders-multi
  namespace: port-mapping-lab
  labels:
    primary-port-name: business
spec:
  selector:
    app: orders-backend
  ports:
    - name: admin
      port: 90
      targetPort: management
    - name: business
      port: 80
      targetPort: app-http
---
apiVersion: v1
kind: Service
metadata:
  name: orders-headless
  namespace: port-mapping-lab
spec:
  clusterIP: None
  selector:
    app: orders-backend
  ports:
    - name: http
      port: 80
      targetPort: app-http
---
apiVersion: v1
kind: Service
metadata:
  name: orders-nodeport
  namespace: port-mapping-lab
spec:
  type: NodePort
  selector:
    app: orders-backend
  ports:
    - name: http
      port: 80
      targetPort: app-http
```

`orders-default` cố ý không đặt tên cổng và bỏ `targetPort`; đây là Service một cổng. Service nhiều cổng cần đặt tên riêng cho các cổng.

`orders-multi` cố ý đặt cổng quản trị trước. Nhãn `primary-port-name` đặt trên **Service**, với giá trị `business`, là tên cổng Service; `app-http` lại là tên cổng Pod được `targetPort` tham chiếu. Hai tên không cần giống nhau.

NodePort để API server cấp cổng, tránh phụ thuộc một số cố định có thể đã bị chiếm. Ca truy cập qua node, nếu thực hiện, phải đọc `spec.ports[].nodePort` sau khi apply.

### Ma trận kết quả mong đợi khi hệ thống ổn định

| Ca | Đường qua Service | Kỳ vọng từ DiscoveryClient đọc endpoint | Điều cần bắt lỗi |
| --- | --- | --- | --- |
| A — `orders-equal` | DNS:8080 | Backend IP:8080 | Ca nền; chưa đủ bắt nhầm cổng |
| B — `orders-numeric` | DNS:80 | Backend IP:8080 | Lấy nhầm Service port 80 cho Pod |
| C — `orders-named` | DNS:80 | Backend IP:8080 | Giải sai tên `app-http` |
| D — `orders-default` | DNS:8080 | Backend IP:8080 | Xử lý sai một cổng không tên |
| E — `orders-multi` | DNS:80 cho nghiệp vụ | Backend IP:8080 | Chọn admin 9090 vì đứng đầu |
| F — `orders-headless` | DNS trả địa chỉ endpoint | Backend IP:8080 | Giả định luôn có ClusterIP |
| G — `orders-nodeport` | DNS:80; đường node dùng nodePort | Backend IP:8080 | Đưa nodePort vào instance backend |

Với headless có selector, không có VIP Service thực hiện dịch cổng. Nếu DNS trả Pod IP, HTTP client gọi trực tiếp theo địa chỉ đó phải dùng cổng backend 8080 trong ví dụ, không máy móc dùng 80. Chỉ phân giải DNS thành công chưa kiểm chứng ánh xạ.

## 7. Quy tắc chọn cổng của discovery cần được kiểm thử riêng

Với nhiều cổng, khai báo ý định rõ ràng thay vì dựa vào thứ tự danh sách:

```yaml
spring:
  cloud:
    kubernetes:
      discovery:
        primary-port-name: business
```

Tài liệu DiscoveryClient mô tả nhãn `primary-port-name` của Service được xét trước cấu hình cùng mục đích ở ứng dụng; tiếp theo có các lựa chọn dựa vào tên `https`/`http`, cuối cùng mới đến cổng đầu tiên. Không dùng lựa chọn cuối làm hợp đồng ổn định. [Tài liệu DiscoveryClient](https://docs.spring.io/spring-cloud-kubernetes/reference/discovery-client.html).

Đợt thử E có thể tách thành ba bước:

1. Giữ nhãn `primary-port-name: business`, cấu hình ứng dụng là `admin`: kiểm tra nhãn Service vẫn dẫn đến cổng nghiệp vụ.
2. Bỏ nhãn khỏi bản manifest của ca thử, giữ cấu hình ứng dụng là `business`: kiểm tra chọn đúng 8080.
3. Giữ nhãn hoặc cấu hình chọn `business`, đảo thứ tự hai phần tử `ports`: kết quả nghiệp vụ phải giữ nguyên sau hội tụ.

Mỗi bước dùng một cấu hình đầu vào rõ ràng và khôi phục ca nền trước bước kế tiếp. Nếu thay cấu hình ứng dụng qua biến môi trường, phải rollout probe để tiến trình mới nhận giá trị; thay ConfigMap không tự thay môi trường của Pod hiện có.

Tên cổng được chọn không tồn tại là ca lỗi riêng. Không xây dựng production dựa vào một fallback tình cờ quan sát được; ghi nhận hành vi của đúng phiên bản và yêu cầu ca kiểm thử báo không đạt khi không chọn được cổng nghiệp vụ mong muốn.

## 8. Thực hiện theo từng lớp bằng chứng

Các lệnh dưới đây chạy trong thư mục chứa `base.yaml` và `services.yaml` mà người học đã chuẩn bị, trên cụm thử nghiệm có quyền phù hợp.

### 8.1. Xác minh API và trạng thái workload

```powershell
kubectl apply --dry-run=server -f base.yaml
```

Nếu namespace chưa tồn tại, dry-run toàn bộ tập tài nguyên phụ thuộc có thể báo chưa tìm thấy namespace: dry-run không lưu Namespace để các tài nguyên sau sử dụng. Tạo namespace lab trước hoặc apply phần Namespace, rồi chạy lại kiểm tra các tài nguyên phụ thuộc. Không coi tình huống này là lỗi ánh xạ cổng.

```powershell
kubectl apply -f base.yaml
kubectl apply --dry-run=server -f services.yaml
kubectl apply -f services.yaml
kubectl rollout status deployment/orders-backend -n port-mapping-lab --timeout=120s
kubectl rollout status deployment/discovery-probe -n port-mapping-lab --timeout=120s
kubectl get pods -n port-mapping-lab -o wide
kubectl get services -n port-mapping-lab -o wide
```

`--dry-run=server` kiểm tra admission và cấu trúc được server chấp nhận; nó không mở socket hoặc chứng minh `targetPort` đang có ứng dụng lắng nghe.

### 8.2. Đọc trạng thái endpoint thực tế

```powershell
kubectl get service orders-named -n port-mapping-lab -o yaml
kubectl get endpointslices.discovery.k8s.io -n port-mapping-lab -l kubernetes.io/service-name=orders-named -o yaml
kubectl get pods -n port-mapping-lab -l app=orders-backend -o wide
```

Đọc tất cả slice của Service. Trong từng slice, ghép `ports` với các `endpoints` của chính slice đó, ghi nhận `addressType`, `addresses`, `conditions.ready`, `conditions.terminating` và `targetRef` nếu có.

Một named target port có thể được giải thành các số cổng khác nhau ở các Pod khác nhau; chúng được chia thành các slice phù hợp. Vì vậy không lấy tập tất cả IP rồi nhân với tập tất cả cổng. [Tài liệu EndpointSlice](https://kubernetes.io/docs/concepts/services-networking/endpoint-slices/).

Ví dụ trạng thái giả định:

```text
slice A: ports = business:8080; endpoints = 10.20.1.10
slice B: ports = business:8081; endpoints = 10.20.2.11

Đúng:  (10.20.1.10, 8080), (10.20.2.11, 8081)
Sai:   (10.20.1.10, 8081), (10.20.2.11, 8080)
```

### 8.3. Đọc probe và phát request từ Pod probe

Mở một terminal riêng và giữ lệnh này chạy:

```powershell
kubectl port-forward deployment/discovery-probe -n port-mapping-lab 18080:8080
```

Tại terminal còn lại:

```powershell
$observed = @(Invoke-RestMethod -Uri 'http://127.0.0.1:18080/lab/instances/orders-named' -TimeoutSec 30)
$observed | Format-Table serviceId, host, port, secure, httpStatus, error
```

Port-forward chỉ là kênh lấy kết quả từ probe. HTTP đến `/demo/identity` vẫn được Java thực hiện trong Pod probe đến URI của từng instance. Việc port-forward thành công không phải bằng chứng đường Service VIP hoặc đường từ máy cá nhân đến Pod IP hoạt động.

Với các ca HTTP nền, mỗi dòng phải có `port = 8080`, `secure = false`, `httpStatus = 200`, `error` rỗng và body nhận diện `orders-backend`.

## 9. Assertion động cho ca named targetPort

Đoạn PowerShell sau minh họa một phép kiểm tra tích hợp: lấy endpoint hiện tại, gọi probe, kiểm tra tập địa chỉ–cổng và kiểm tra danh tính backend. Chạy khi rollout đã hoàn tất, không có Pod terminating và không có thay đổi manifest đồng thời.

Ca này giới hạn ở `orders-named` một cổng, `publishNotReadyAddresses` không bật, Pod không terminating và địa chỉ IPv4. Các biến thể IPv6, nhiều cổng hoặc đang rollout cần mở rộng phép chọn endpoint tương ứng.

```powershell
function Assert-OrdersNamedMapping {
    $sliceJson = kubectl get endpointslices.discovery.k8s.io `
        -n port-mapping-lab `
        -l kubernetes.io/service-name=orders-named -o json
    if ($LASTEXITCODE -ne 0) {
        throw 'Không đọc được EndpointSlice'
    }
    $slices = $sliceJson | ConvertFrom-Json
    $expected = @{}

    foreach ($slice in $slices.items) {
        if ($slice.addressType -ne 'IPv4') {
            throw 'Ca nền này chỉ kiểm tra IPv4'
        }
        $ports = @($slice.ports | Where-Object {
            $_.name -eq 'http' -and $_.protocol -eq 'TCP'
        })
        if ($ports.Count -ne 1) {
            throw 'Không có đúng một endpoint port http/TCP'
        }
        if ([int]$ports[0].port -ne 8080) {
            throw 'Endpoint port không đúng hợp đồng 8080'
        }
        foreach ($endpoint in $slice.endpoints) {
            if ($endpoint.conditions.terminating -eq $true) {
                throw 'Snapshot còn endpoint terminating'
            }
            if ($endpoint.conditions.ready -ne $true) {
                continue
            }
            if (-not $endpoint.targetRef.name) {
                throw 'Ca có selector này cần targetRef của Pod'
            }
            foreach ($address in $endpoint.addresses) {
                $key = '{0}|{1}' -f $address, $ports[0].port
                $expected[$key] = $endpoint.targetRef.name
            }
        }
    }
    if ($expected.Count -ne 2) {
        throw 'Ca nền cần đúng hai backend Ready'
    }

    $instances = @(Invoke-RestMethod `
        -Uri 'http://127.0.0.1:18080/lab/instances/orders-named' `
        -TimeoutSec 30)
    if ($instances.Count -eq 0) {
        throw 'Discovery trả về danh sách rỗng'
    }
    $actual = @{}
    foreach ($instance in $instances) {
        $key = '{0}|{1}' -f $instance.host, $instance.port
        if (-not $expected.ContainsKey($key)) {
            throw "Instance ngoài tập endpoint hợp lệ: $key"
        }
        if ($instance.serviceId -ne 'orders-named' -or
            $instance.namespace -ne 'port-mapping-lab') {
            throw 'Sai serviceId hoặc namespace'
        }
        if ($instance.secure -ne $false -or
            ([uri]$instance.uri).Scheme -ne 'http') {
            throw 'Sai giao thức của ca HTTP'
        }
        if ($instance.error -or $instance.httpStatus -ne 200) {
            throw "Gọi backend không thành công: $key"
        }
        $identity = $instance.body | ConvertFrom-Json
        if ($identity.app -ne 'orders-backend' -or
            [int]$identity.port -ne 8080 -or
            $identity.pod -ne $expected[$key]) {
            throw "Phản hồi không đúng backend: $key"
        }
        $actual[$key] = $true
    }
    if ($actual.Count -ne $expected.Count) {
        throw 'Discovery thiếu endpoint Ready'
    }
}

$deadline = [DateTime]::UtcNow.AddSeconds(60)
$lastFailure = 'Chưa có snapshot đạt'
$stablePasses = 0
while ([DateTime]::UtcNow -lt $deadline) {
    try {
        Assert-OrdersNamedMapping
        $stablePasses++
        if ($stablePasses -ge 2) { break }
    }
    catch {
        $stablePasses = 0
        $lastFailure = $_.Exception.Message
    }
    Start-Sleep -Seconds 2
}
if ($stablePasses -lt 2) {
    throw "Không hội tụ trong 60 giây: $lastFailure"
}
'PASS: hai snapshot liên tiếp khớp endpoint và phản hồi nghiệp vụ'
```

Ở mỗi vòng, script đọc lại cả kỳ vọng từ API lẫn kết quả probe. So sánh tập hợp giúp tránh phụ thuộc thứ tự trả về và loại trùng địa chỉ–cổng khi một endpoint xuất hiện ở nhiều slice. Nếu mục tiêu riêng là phát hiện instance trùng, thêm assertion số dòng theo hợp đồng của client đang dùng.

Hai snapshot liên tiếp là tiêu chí ổn định thực dụng cho lab, không tạo ra giao dịch nguyên tử giữa API server và cache discovery. Trong CI có rollout liên tục, nên khóa giai đoạn thay đổi hoặc phát hiện thay đổi snapshot rồi thử lại có giới hạn. Nếu request probe bị kẹt, timeout của `Invoke-RestMethod` có thể làm tổng thời gian thực tế vượt deadline một khoảng; cần đặt timeout tổng cho job CI.

Mở rộng hàm sang ca khác bằng tham số rõ ràng cho service, tên cổng, số cổng và số backend. Không sửa assertion thành chỉ kiểm tra `Count > 0` để làm test xanh.

## 10. Các ca lỗi cần chứng minh rằng test bắt được

Chỉ thay một yếu tố mỗi lượt trong namespace thực hành và phục hồi manifest nền trước khi chạy ca tiếp theo.

### 10.1. Sai `targetPort` dạng số

Đổi `orders-numeric.targetPort` từ 8080 thành 8088, trong khi backend vẫn nghe ở 8080.

- Manifest có thể vẫn hợp lệ với API server.
- Slice có thể chứa cổng 8088 vì đây là giá trị được khai báo.
- Readiness ở cổng management có thể vẫn thành công.
- Assertion cổng nghiệp vụ phải báo sai; request đến 8088 cũng phải thất bại nếu không có tiến trình ở đó.

Nếu test chỉ so instance với slice, cả hai có thể cùng sai theo manifest và vẫn khớp nhau. Vì vậy phải giữ thêm hợp đồng nghiệp vụ 8080 và assertion phản hồi ứng dụng.

### 10.2. Sai tên cổng đích

Đổi `orders-named.targetPort` thành `app-htpt`.

Đối chiếu EndpointSlice sau hội tụ để xem tên đó đã được giải hay chưa. Kỳ vọng của test là không được báo PASS khi thiếu hai backend nghiệp vụ hợp lệ. Không bắt buộc một thông báo ngoại lệ duy nhất cho mọi phiên bản client/controller.

Khác với lỗi này, một Service nhiều cổng khai báo tên cổng trùng có thể bị API server từ chối ngay. Cần phân biệt lỗi validation manifest với lỗi chạy thực tế.

### 10.3. Selector không khớp

Đổi selector của Service sang nhãn không có Pod nào mang. Sau hội tụ, danh sách backend hợp lệ phải rỗng và ca dương phải thất bại rõ ràng. Kiểm tra lại selector và nhãn trước khi thay đổi quyền RBAC.

### 10.4. Chọn nhầm cổng quản trị

Đặt `primary-port-name: admin` trên `orders-multi`. Kết quả chọn endpoint quản trị có thể dẫn đến 9090.

`/actuator/health` ở 9090 có thể trả 200 nhưng `/demo/identity` không phải endpoint nghiệp vụ ở cổng đó. Test phải phát hiện cổng không phải 8080 hoặc phản hồi không đúng danh tính. Đây là lý do không dùng health endpoint làm assertion cuối cùng cho routing nghiệp vụ.

### 10.5. Pod Running nhưng chưa Ready

Trong bản Deployment dành riêng cho ca thử, cấu hình readiness probe đến đường dẫn không tồn tại. Chờ trạng thái Ready đổi, rồi quan sát slice và discovery. Với chính sách chỉ lấy endpoint Ready của bài, sau hội tụ không được coi Pod đó là backend phục vụ hợp lệ.

Không dùng `publishNotReadyAddresses: true` hoặc bật `include-not-ready-addresses` để làm ca dương vượt qua. Nếu chủ đích là kiểm thử hai tùy chọn đó, tạo ca riêng và ghi rõ hợp đồng readiness đã thay đổi. Nhất là `publishNotReadyAddresses`, không thể suy luận khả năng phục vụ chỉ từ cờ ready được công bố.

### 10.6. Thiếu RBAC hoặc bị NetworkPolicy chặn

| Tình huống | Dữ liệu cần xem | Kết luận phù hợp |
| --- | --- | --- |
| Log có 403 khi list/watch Service hoặc EndpointSlice | ServiceAccount, Role, RoleBinding và resource/API group | Lỗi quyền khám phá; chưa đánh giá được mapping |
| Instance đúng nhưng HTTP timeout | NetworkPolicy, CNI, route, cổng lắng nghe | Khám phá đúng chưa bảo đảm kết nối được |
| HTTP connection refused | Socket thực của backend, cấu hình bind và cổng | Không suy ra ngay rằng DNS hỏng |
| HTTP 404 | Đường dẫn và cổng đã chọn | Có thể đã đến cổng quản trị hoặc ứng dụng khác |
| Có 200 nhưng identity sai | Body, targetRef, nhãn selector | Request đã tới sai backend |

RBAC cho phép truy cập Kubernetes API; nó không cấp quyền truyền dữ liệu giữa hai Pod. Ngược lại, cho phép traffic không thay thế quyền đọc tài nguyên discovery.

## 11. Kiểm thử rollout khi cùng tên cổng có số khác nhau

Đây là ca có sức phân biệt cao hơn việc chỉ thay thứ tự cổng.

1. Giữ các Pod cũ có cổng tên `app-http` ở 8080.
2. Tạo revision mới của backend: tiến trình nghe 8081 và `containerPort` tên `app-http` cũng là 8081; giữ readiness management ở 9090.
3. Trong giai đoạn có cả hai revision Ready, đọc toàn bộ slice của `orders-named`.
4. Xác minh mỗi địa chỉ instance đi cùng đúng số cổng của nhóm endpoint chứa địa chỉ đó.
5. Gọi `/demo/identity` của từng instance, kiểm tra `port` và `pod` phản hồi khớp nhóm dự kiến.
6. Khi rollout hoàn tất, chờ loại hết endpoint cũ và yêu cầu mọi backend hợp lệ dùng 8081.

Ca này áp dụng cho Service có `targetPort: app-http`. Các Service dùng số cố định 8080 như `orders-numeric` không tự đổi theo revision. Nếu chạy toàn bộ ma trận trong lúc chuyển cổng, phải xác định rõ các ca đó sẽ lỗi hay được cập nhật đồng bộ; không gọi đó là regression của discovery.

Không mặc định số instance luôn bằng `replicas` trong lúc rollout: có thể có Pod surge, Pod chưa Ready hoặc Pod terminating. Giữ assertion hai backend cho trạng thái nền ổn định; dùng snapshot endpoint đủ điều kiện làm kỳ vọng trong ca chuyển tiếp.

## 12. HTTPS, IPv6 và các manifest ngoài ca nền

### 12.1. Scheme đúng chưa đủ để TLS thành công

Để kiểm thử TLS, cần backend thực sự bật TLS, truststore đúng và chứng thư phù hợp địa chỉ được gọi. Tên cổng `https`, nhãn `secured` hoặc quy tắc nhận diện secure chỉ cung cấp dữ liệu để client chọn scheme; chúng không cấu hình TLS cho server.

Ca âm hữu ích là đánh dấu một cổng HTTP thành secure: URI có thể chuyển sang HTTPS nhưng TLS handshake phải thất bại. Không sửa probe thành trust-all để làm xanh kết quả. Khi truy cập Pod IP, chứng thư chỉ hợp lệ cho DNS Service có thể không vượt qua hostname verification; đó là kết quả thiết kế cần giải quyết, không phải lý do bỏ xác minh chứng thư.

### 12.2. Dual-stack và IPv6

Không hard-code regex IPv4 cho mọi môi trường. Mở rộng phép đọc slice theo `addressType`, xác định họ địa chỉ mà ứng dụng gọi hỗ trợ và dùng URI parser. Với IPv6, URI cần dạng `http://[địa-chỉ-ipv6]:8080/...`; `getHost()` và chuỗi URI không phải hai chuỗi có thể so sánh trực tiếp.

Một Pod dual-stack có thể đóng góp nhiều địa chỉ. Vì vậy đếm địa chỉ không luôn bằng đếm Pod; tiêu chí số lượng cần theo hợp đồng của đợt thử và client.

### 12.3. Service không selector và ExternalName

Service không selector không tự tạo backend từ các Pod của bài. Nếu kiểm thử loại đó, tạo EndpointSlice có chủ đích, gắn đúng nhãn Service và kiểm tra nguồn dữ liệu mà discovery đang sử dụng. Không chép Pod IP ngẫu nhiên vào production rồi coi đó là cơ chế đăng ký động.

ExternalName thuộc ca hợp đồng khác: host có thể là tên DNS bên ngoài và việc đưa loại Service này vào kết quả discovery phụ thuộc tùy chọn hỗ trợ của client. Test phải kiểm tra DNS và khả năng kết nối từ Pod, không áp dụng assertion `host` phải thuộc tập Pod IP của namespace. [Phạm vi ExternalName trong DiscoveryClient](https://docs.spring.io/spring-cloud-kubernetes/reference/discovery-client.html).

## 13. Tách assertion của Spring Cloud LoadBalancer

Với Spring Cloud Kubernetes LoadBalancer, chế độ `POD` dùng DiscoveryClient; chế độ `SERVICE` dựng đích qua tên Service và chọn cổng Service. Cấu hình chọn cổng của đường SERVICE có mục riêng `spring.cloud.kubernetes.loadbalancer.port-name`. Không giả định nhãn chọn cổng discovery kiểm soát mọi đường load balancing. [Tài liệu LoadBalancer](https://docs.spring.io/spring-cloud-kubernetes/reference/load-balancer.html).

Ví dụ chọn đường SERVICE cho Service nhiều cổng:

```yaml
spring:
  cloud:
    kubernetes:
      loadbalancer:
        mode: SERVICE
        port-name: business
```

Đích dự kiến của `orders-multi` theo cấu hình này là tên Service trong namespace và cổng Service 80; domain cụm phải lấy từ cấu hình thực tế. Khi dùng POD/discovery, ca nền kiểm tra các endpoint 8080.

Nếu ứng dụng sử dụng `@LoadBalanced` client, bổ sung một request nghiệp vụ qua chính client đó và kiểm tra identity trong phản hồi. Việc probe gọi trực tiếp thành công chỉ xác nhận đường endpoint; nó chưa chứng minh một WebClient, RestClient hay Feign client đã được gắn đúng cơ chế cân bằng tải, đúng scheme và đúng cấu hình.

Nếu nhu cầu chỉ là gọi `orders-named` qua DNS Service ổn định, Kubernetes có thể đáp ứng mà không cần ứng dụng tự khám phá từng Pod. Chỉ dùng DiscoveryClient hoặc cân bằng tải phía ứng dụng khi có yêu cầu cụ thể đối với danh sách instance, metadata hoặc chính sách chọn backend.

## 14. Tiêu chí hoàn tất và bằng chứng bàn giao

Một đợt kiểm thử ánh xạ đạt khi có đủ bằng chứng cho đường gọi đã chọn:

- Manifest hợp lệ và trạng thái thực sau admission đúng với đầu vào cần thử.
- Pod sẵn sàng, tiến trình nghe đúng cổng nghiệp vụ và Service chọn đúng backend.
- Kỳ vọng được lấy từ từng nhóm endpoint đúng namespace, cổng và trạng thái; không ghép chéo IP với cổng của slice khác.
- Sau khoảng hội tụ có giới hạn, tập instance khớp tập endpoint hợp lệ và giao thức đúng.
- Request từ ứng dụng gọi đến từng đích cần kiểm tra trả về đúng mã, đúng `app`, đúng Pod và đúng cổng.
- Các ca âm làm assertion thất bại theo đúng lớp nguyên nhân; sau phục hồi, ca nền đạt trở lại.

Biên bản nên ghi mã ca, phiên bản, cấu hình chọn cổng, nguồn endpoint, image digest, snapshot Service/EndpointSlice/Pod, kết quả probe, thời điểm và kết luận. Không chỉ ghi “curl thành công”, không lưu token ServiceAccount hoặc nội dung Secret vào bằng chứng.

Ví dụ dòng kết quả mô tả kỳ vọng, không phải kết quả đã chạy:

```text
C — named targetPort
Service: orders-named, namespace: port-mapping-lab
Service port: 80, targetPort: app-http
Backend được giải: <IP động của Pod>:8080
Assertion: đúng tập endpoint Ready, HTTP 200, identity khớp Pod
Kết luận: PASS chỉ sau khi quan sát và kiểm tra đủ các điều kiện trên
```

Khi thay đổi cấu hình bằng ConfigMap hoặc Secret, phải chứng minh ứng dụng đã nhận revision mới trước khi kiểm tra mapping. Nếu có Configuration Watcher, quan sát riêng sự kiện cập nhật và trạng thái ứng dụng; một thông báo refresh không tự chứng minh socket đã đổi cổng. Với thay đổi cổng lắng nghe, lập kế hoạch restart/rollout theo khả năng thực tế của ứng dụng rồi chạy lại cùng hợp đồng kiểm thử.

