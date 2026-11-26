# Đưa label, annotation và thông tin tài nguyên vào metadata

> Chương: ServiceInstance và cổng — Module: SPRING_CLOUD_KUBERNETES.

Một `ServiceInstance` cho biết đích dịch vụ qua các thuộc tính như tên dịch vụ, host, cổng và URI. Khi cần biết backend thuộc nhóm nào, Service nằm ở namespace nào hoặc Pod đang chạy bản dựng nào, các thuộc tính địa chỉ chưa đủ. Metadata bổ sung ngữ cảnh để ứng dụng quan sát, phân loại và thực hiện những chính sách đã được thiết kế rõ ràng.

Trong Spring Cloud Kubernetes, dữ liệu này có thể đến từ label và annotation của Service, thông tin cổng, namespace, loại Service hoặc metadata của Pod đứng sau endpoint. Điều quan trọng là giữ đúng nguồn và phạm vi của từng trường, thay vì gom mọi thông tin Kubernetes thành một map không còn phân biệt ý nghĩa.

Bài học tập trung vào cách cấu hình và đọc metadata trong DiscoveryClient. Spring Cloud LoadBalancer chỉ sử dụng những khóa mà chính sách của nó hiểu. ConfigMap, Secret và Configuration Watcher phục vụ bài toán cấu hình; không cần thêm chúng chỉ để đưa label của Service vào kết quả khám phá.

## 1. Phân biệt ba lớp metadata

Từ “metadata” xuất hiện ở cả Kubernetes và Spring nhưng không chỉ cùng một cấu trúc.

| Lớp dữ liệu | Ví dụ | Phạm vi |
| --- | --- | --- |
| `metadata` của đối tượng Kubernetes | `name`, `namespace`, `uid`, `labels`, `annotations` trên một Service | Một đối tượng API cụ thể |
| `ServiceInstance.getMetadata()` | `Map<String, String>` | Góc nhìn của Spring về một instance, có thể chứa dữ liệu được ánh xạ từ nhiều nguồn |
| Metadata mở rộng của Pod | Map label và annotation của Pod liên quan | Từng backend, phụ thuộc implementation và tùy chọn khám phá |

Không phải toàn bộ `ObjectMeta` của Kubernetes được tự động sao chép vào `ServiceInstance.getMetadata()`. Ngược lại, một khóa trong map của Spring có thể là khóa tổng hợp do thư viện tạo, không phải label nguyên bản trên Service.

Một cách đọc luôn cần trả lời đủ bốn câu hỏi: giá trị đến từ đâu, thuộc Service hay Pod, có được ánh xạ tự động không và thành phần nào sẽ sử dụng nó.

## 2. Chọn label và annotation theo ý nghĩa

Label phù hợp để tổ chức, phân loại và chọn tài nguyên. Annotation phù hợp với thông tin mô tả bổ sung, ví dụ liên kết runbook hoặc ghi chú vận hành. Cả hai đều là map có khóa và giá trị dạng chuỗi, nhưng giá trị label chịu giới hạn cú pháp chặt hơn. Xem [Labels and Selectors](https://kubernetes.io/docs/concepts/overview/working-with-objects/labels/) và [Annotations](https://kubernetes.io/docs/concepts/overview/working-with-objects/annotations/).

Ví dụ Service `inventory` trong namespace `shop`:

```yaml
apiVersion: v1
kind: Service
metadata:
  name: inventory
  namespace: shop
  labels:
    app.kubernetes.io/name: inventory
    learning.example.com/tier: backend
    learning.example.com/owner: catalog-team
  annotations:
    learning.example.com/owner: "Nhóm Danh mục sản phẩm"
    learning.example.com/runbook: "https://ops.example.com/runbooks/inventory"
    learning.example.com/build-revision: "svc-definition-v1"
spec:
  type: ClusterIP
  selector:
    app.kubernetes.io/name: inventory
  ports:
    - name: http
      protocol: TCP
      port: 8080
      targetPort: http
    - name: management
      protocol: TCP
      port: 9090
      targetPort: management
```

Trong ví dụ, các Pod backend được giả định khai báo cổng `http:8080` và `management:9090`, đồng thời mang nhãn phù hợp với selector. Manifest trên mô tả Service; nó không tạo Pod hoặc ứng dụng backend.

Chú ý khóa `learning.example.com/owner` xuất hiện trong cả label lẫn annotation với hai giá trị khác nhau. Kubernetes cho phép điều này vì chúng nằm trong hai map riêng. Khi chuyển vào một map phẳng của Spring, cần phân biệt nguồn để tránh đè giá trị.

Giá trị có vẻ là số hoặc boolean vẫn nên được viết như chuỗi nếu đặt trong label hoặc annotation:

```yaml
metadata:
  labels:
    learning.example.com/generation: "7"
  annotations:
    learning.example.com/audit-enabled: "true"
```

Annotation có thể chứa nội dung dài hoặc JSON, nhưng ứng dụng đọc metadata vẫn nhận chuỗi. Chỉ phân tích cấu trúc đó khi có hợp đồng dữ liệu, giới hạn kích thước và cách xử lý lỗi rõ ràng.

## 3. Bật ánh xạ và đặt prefix rõ ràng

Ví dụ cấu hình ứng dụng Spring chạy trong cluster, sử dụng Kubernetes DiscoveryClient:

```yaml
spring:
  application:
    name: order-service
  cloud:
    kubernetes:
      discovery:
        enabled: true
        all-namespaces: false
        namespaces:
          - shop
        use-endpoint-slices: true
        primary-port-name: http
        metadata:
          add-labels: true
          labels-prefix: "svc.label."
          add-annotations: true
          annotations-prefix: "svc.annotation."
          add-ports: true
          ports-prefix: "port."
          add-pod-labels: false
          add-pod-annotations: false
```

Đây là cấu hình của ứng dụng đọc discovery, không phải annotation cần thêm vào Service. Dùng bộ phiên bản Spring Boot, Spring Cloud và Spring Cloud Kubernetes tương thích do dự án quản lý; đối chiếu thuộc tính với nhánh tài liệu đúng phiên bản.

| Thuộc tính trong `spring.cloud.kubernetes.discovery.metadata` | Chức năng |
| --- | --- |
| `add-labels` | Đưa label của Service vào metadata trả về |
| `labels-prefix` | Thêm tiền tố vào khóa label khi xuất ra map |
| `add-annotations` | Đưa annotation của Service vào metadata trả về |
| `annotations-prefix` | Thêm tiền tố vào khóa annotation khi xuất ra map |
| `add-ports` | Thêm thông tin cổng vào metadata |
| `ports-prefix` | Đặt tiền tố cho các khóa cổng |
| `add-pod-labels` | Yêu cầu thêm label của Pod liên quan nếu implementation có thể lấy được |
| `add-pod-annotations` | Yêu cầu thêm annotation của Pod liên quan |

Tên và giá trị mặc định của các tùy chọn được công bố trong [Common application properties](https://docs.spring.io/spring-cloud-kubernetes/reference/appendix.html). Ví dụ ghi rõ các giá trị cần dùng để người đọc không phải suy đoán dựa trên mặc định.

Prefix là chuỗi được ghép với khóa gốc. Hãy tự viết dấu chấm cuối nếu đó là quy ước muốn có. Với cấu hình trên:

```text
learning.example.com/owner của label
    -> svc.label.learning.example.com/owner

learning.example.com/owner của annotation
    -> svc.annotation.learning.example.com/owner
```

Dấu `/` trong khóa Kubernetes vẫn là một phần của khóa map. Nó không tự biến thành thuộc tính lồng nhau hoặc dấu chấm.

Đặt prefix tách biệt cũng giúp tránh dùng nhầm khóa ứng dụng với những khóa tổng hợp như `k8s_namespace` và `type`. Không dựa vào thứ tự ghi đè khi hai nguồn cùng sinh một khóa.

## 4. Đọc kết quả và hiểu thông tin tài nguyên có sẵn

Với Service ở mục 2, backend có hai cổng đúng như giả định và cấu hình ở mục 3, một phần metadata minh họa là:

```json
{
  "svc.label.app.kubernetes.io/name": "inventory",
  "svc.label.learning.example.com/tier": "backend",
  "svc.label.learning.example.com/owner": "catalog-team",
  "svc.annotation.learning.example.com/owner": "Nhóm Danh mục sản phẩm",
  "svc.annotation.learning.example.com/runbook": "https://ops.example.com/runbooks/inventory",
  "svc.annotation.learning.example.com/build-revision": "svc-definition-v1",
  "port.http": "8080",
  "port.management": "9090",
  "k8s_namespace": "shop",
  "type": "ClusterIP"
}
```

Đây là dữ liệu dự kiến để giải thích cách ánh xạ, không phải log thu được từ một cluster cụ thể. Thứ tự khóa trong JSON không mang ý nghĩa.

Spring Cloud Kubernetes mô tả label, annotation, thông tin cổng và các khóa namespace, loại Service trong [DiscoveryClient for Kubernetes](https://docs.spring.io/spring-cloud-kubernetes/reference/discovery-client.html).

Các trường sau không nên bị nhầm lẫn:

| Dữ liệu cần biết | Nơi nên đọc trước | Điều không nên suy diễn |
| --- | --- | --- |
| Tên Service | `instance.getServiceId()` | Không mặc định tồn tại thêm khóa `metadata.name` |
| Host và cổng chính | `instance.getHost()`, `instance.getPort()` | Các khóa cổng phụ không tự thay cổng chính |
| Namespace được xuất trong map | `metadata.get("k8s_namespace")` | Không suy namespace từ một label cùng tên |
| Loại Service | `metadata.get("type")` | Không đồng nhất `ClusterIP` với trạng thái khỏe của backend |
| Label và annotation của Service | Khóa sau khi thêm prefix đã cấu hình | Không coi đó là label riêng của Pod |
| UID, resourceVersion của tài nguyên | Đối tượng Kubernetes nguồn, nếu ứng dụng thực sự cần | Không giả định có sẵn khóa tương ứng trong metadata phẳng |

`getMetadata()` trả các giá trị dạng `String`. Vì vậy, `"9090"` cần được phân tích nếu ứng dụng thật sự cần một số nguyên. Nếu chỉ muốn gọi cổng chính đã được chọn, dùng trực tiếp `getPort()` sẽ rõ ràng hơn.

Trong ví dụ này, Service port và backend port cố ý bằng nhau. Khi hai giá trị khác nhau, phải đối chiếu đường khám phá và phiên bản implementation để biết thông tin cổng nào đang được đưa vào map. Không lấy một khóa phụ rồi thay `getPort()` một cách tùy tiện.

`add-ports: true` không khiến client tự gửi request tới cổng quản trị. Tương tự, thêm một label `track: canary` chưa tạo ra phân phối lưu lượng canary; phải có chính sách lựa chọn đọc và hiểu thông tin đó.

## 5. Đọc metadata trong ứng dụng Spring

Ví dụ dùng Java 17 trở lên, Spring Web và starter discovery Fabric8. Các dependency sau được đặt trong dự án Spring Boot đã quản lý BOM tương thích:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-kubernetes-fabric8</artifactId>
</dependency>
```

Ứng dụng chính bật discovery và đặt cùng package cha với controller:

```java
package example.metadata;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cloud.client.discovery.EnableDiscoveryClient;

@SpringBootApplication
@EnableDiscoveryClient
public class Application {
    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }
}
```

Để quan sát metadata, nên tạo bản chiếu chỉ chứa những khóa cần dùng. Đừng sửa trực tiếp map nhận từ client: nó có thể thuộc dữ liệu được cache hoặc được chia sẻ giữa các thành phần.

```java
package example.metadata;

import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;

import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.discovery.DiscoveryClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class InventoryMetadataController {
    private static final Set<String> EXPORTED_KEYS = Set.of(
            "k8s_namespace",
            "type",
            "svc.label.learning.example.com/tier",
            "svc.label.learning.example.com/owner",
            "svc.annotation.learning.example.com/owner",
            "svc.annotation.learning.example.com/build-revision",
            "port.http",
            "port.management");

    private final DiscoveryClient discoveryClient;

    public InventoryMetadataController(DiscoveryClient discoveryClient) {
        this.discoveryClient = discoveryClient;
    }

    @GetMapping("/internal/discovery/inventory/metadata")
    public List<InstanceMetadataView> inventory() {
        return discoveryClient.getInstances("inventory").stream()
                .map(this::toView)
                .toList();
    }

    private InstanceMetadataView toView(ServiceInstance instance) {
        return new InstanceMetadataView(
                instance.getServiceId(),
                instance.getInstanceId(),
                instance.getHost(),
                instance.getPort(),
                selected(instance.getMetadata(), EXPORTED_KEYS));
    }

    private static Map<String, String> selected(
            Map<String, String> source, Set<String> keys) {
        if (source == null || source.isEmpty()) {
            return Map.of();
        }

        Map<String, String> result = new HashMap<>();
        for (String key : keys) {
            String value = source.get(key);
            if (value != null) {
                result.put(key, value);
            }
        }
        return Map.copyOf(result);
    }

    public record InstanceMetadataView(
            String serviceId,
            String instanceId,
            String host,
            int port,
            Map<String, String> metadata) {
    }
}
```

Controller giữ nguyên giá trị chuỗi rỗng nếu nó thật sự tồn tại; không dùng một giá trị mặc định để che việc thiếu khóa. Việc thiếu khóa có thể do tùy chọn ánh xạ bị tắt, prefix khác, đối tượng nguồn không có dữ liệu hoặc implementation trả một dạng instance khác.

Endpoint trên dành cho quan sát nội bộ, chưa kiểm tra kết nối tới backend và chưa áp dụng chính sách định tuyến. Khi đưa vào môi trường thật, đặt sau cơ chế kiểm soát truy cập vì phản hồi chứa địa chỉ và thông tin vận hành.

Nếu cần lọc theo owner, hãy đọc đúng khóa từ Service trong cấu hình này:

```java
boolean belongsToCatalogTeam = "catalog-team".equals(
        instance.getMetadata().get("svc.label.learning.example.com/owner"));
```

Đó chỉ là một biểu thức phân loại. Muốn dùng nó để chọn backend cần thiết kế thêm cách xử lý khi không có ứng viên, khi thiếu khóa và khi dữ liệu thay đổi.

