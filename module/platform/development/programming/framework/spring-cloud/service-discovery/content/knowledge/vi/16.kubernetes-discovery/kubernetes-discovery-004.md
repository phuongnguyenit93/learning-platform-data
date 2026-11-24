# Các lựa chọn client Kubernetes và phạm vi sử dụng

## Mục tiêu

Sau bài học này, bạn có thể:

- Phân biệt Kubernetes Service DNS với Spring Cloud Kubernetes `DiscoveryClient`.
- Chọn giữa Fabric8 Kubernetes Client, Kubernetes Java Client và HTTP DiscoveryClient.
- Hiểu khi nào cần triển khai Spring Cloud Kubernetes Discovery Server.
- Cấu hình dependency, namespace scope, bộ lọc service và quyền RBAC ở mức cần thiết.
- Đánh giá tác động của EndpointSlice, cache và cách chọn instance đến kiến trúc ứng dụng.

## 1. Không phải ứng dụng nào cũng cần Kubernetes API client

Kubernetes đã cung cấp cơ chế tìm dịch vụ thông qua Service và DNS. Một ứng dụng chạy trong cluster có thể gọi Service bằng tên DNS, ví dụ `inventory` hoặc `inventory.commerce.svc.cluster.local`. Kubernetes Service cung cấp một địa chỉ ổn định; dataplane của cluster chuyển lưu lượng đến backend phù hợp.

Spring Cloud Kubernetes bổ sung các implementation của Spring Cloud abstraction như `DiscoveryClient` để ứng dụng có thể truy vấn danh sách service và instance bằng Java API. Cách này hữu ích khi ứng dụng cần biết từng endpoint, đọc metadata, lọc theo namespace/label hoặc kết hợp với Spring Cloud LoadBalancer.

Tài liệu Spring Cloud Kubernetes hiện hành hỗ trợ ba kiểu `DiscoveryClient`:

1. Fabric8 Kubernetes Client.
2. Kubernetes Java Client.
3. HTTP-based DiscoveryClient kết nối tới Spring Cloud Kubernetes Discovery Server.

Tài liệu Spring Cloud Kubernetes minh họa việc bật discovery bằng `@EnableDiscoveryClient`. Khả năng auto-configuration còn phụ thuộc phiên bản và cloud platform detection; hãy kiểm tra cấu hình của release train đang dùng nếu bean chưa được tạo.

Ngoài ba kiểu trên, gọi trực tiếp qua Kubernetes Service DNS là một lựa chọn native, không cần thêm Spring Cloud Kubernetes chỉ để phân giải hostname. Spring Cloud Kubernetes là thư viện tích hợp hữu ích, nhưng không phải điều kiện bắt buộc để triển khai Spring Boot trên Kubernetes.

## 2. Bốn hướng tiếp cận và phạm vi của chúng

| Lựa chọn | Cách lấy thông tin | Thành phần cần có | Phù hợp khi |
| --- | --- | --- | --- |
| Kubernetes Service DNS | Phân giải hostname Service bằng DNS trong cluster. | Kubernetes Service và cluster DNS. | Chỉ cần gọi một địa chỉ dịch vụ ổn định, không cần danh sách instance trong code. |
| Fabric8 DiscoveryClient | Ứng dụng gọi Kubernetes API qua Fabric8 client. | Fabric8 starter, ServiceAccount/RBAC hoặc kubeconfig. | Muốn dùng Spring Cloud DiscoveryClient và hệ sinh thái Fabric8. |
| Kubernetes Java Client DiscoveryClient | Ứng dụng gọi Kubernetes API qua Kubernetes Java Client. | Kubernetes Client starter, ServiceAccount/RBAC hoặc kubeconfig. | Muốn dùng client Java chính thức của Kubernetes và các model/API của thư viện này. |
| HTTP DiscoveryClient | Ứng dụng gọi Discovery Server qua HTTP; server truy vấn Kubernetes API. | HTTP discovery starter ở client và Discovery Server ở cluster. | Muốn tập trung quyền truy cập Kubernetes API ở một thành phần riêng. |

Không nên xem bốn lựa chọn này là các tên gọi khác nhau cho cùng một cơ chế. DNS trả về địa chỉ theo quy tắc DNS của Service; hai API client trực tiếp truy vấn Kubernetes API; HTTP client truy vấn một dịch vụ discovery trung gian.

## 3. Lựa chọn 1: Kubernetes Service DNS

Mỗi Kubernetes Service có thể được truy cập bằng DNS name. Ví dụ Service `inventory` trong namespace `commerce` thường có tên đầy đủ:

~~~~text
inventory.commerce.svc.cluster.local
~~~~

Pod cùng namespace có thể dùng tên ngắn `inventory`. Pod ở namespace khác cần chỉ rõ namespace, ví dụ `inventory.commerce`. Hậu tố cluster domain có thể được cấu hình khác nhau theo cluster.

Với Service kiểu ClusterIP, DNS phân giải tên thành ClusterIP ổn định. Kubernetes dataplane chuyển traffic từ ClusterIP đến các endpoint phù hợp. Ứng dụng chỉ cần biết hostname và port của Service:

~~~~java
import org.springframework.web.reactive.function.client.WebClient;

public class InventoryGateway {

    private final WebClient webClient;

    public InventoryGateway(WebClient.Builder builder) {
        this.webClient = builder
                .baseUrl("http://inventory.commerce.svc.cluster.local")
                .build();
    }

    public String getStatus() {
        return webClient.get()
                .uri("/actuator/health")
                .retrieve()
                .bodyToMono(String.class)
                .block();
    }
}
~~~~

Ví dụ trên gọi Service qua DNS. Ứng dụng không cần gọi Kubernetes API để lấy IP Pod, không cần `DiscoveryClient` và không cần quyền `list/watch` Service hoặc Endpoint chỉ để thực hiện lookup DNS.

### Headless Service

Nếu Service đặt `clusterIP: None`, DNS có thể trả về địa chỉ của các Pod endpoint thay vì một ClusterIP dùng chung. Mô hình này phù hợp khi client cần biết từng Pod, chẳng hạn một số hệ thống stateful. Khi dùng headless Service, ứng dụng hoặc thư viện mạng phải xử lý nhiều địa chỉ và thay đổi endpoint theo vòng đời Pod.

### Phạm vi và giới hạn

- DNS cung cấp hostname và địa chỉ; nó không trả về toàn bộ metadata Kubernetes dưới dạng `ServiceInstance`.
- ClusterIP giúp caller dùng một điểm truy cập ổn định; việc chọn backend do Kubernetes dataplane thực hiện.
- Headless Service có thể trả về nhiều địa chỉ Pod; cách phân phối và cache DNS phụ thuộc resolver và client.
- DNS không thay thế các nhu cầu như lọc service theo label, đọc namespace metadata hoặc truy vấn danh sách instance từ Java.
- Service kiểu `ExternalName` được phân giải bằng DNS CNAME; đây là trường hợp DNS đặc biệt.

Ở phía Spring Cloud Kubernetes, `ExternalName` không được đưa vào kết quả `getInstances()` mặc định. Nếu cần discovery loại Service này, bật `spring.cloud.kubernetes.discovery.include-external-name-services=true` theo phiên bản đang dùng.

Chọn DNS khi ứng dụng chỉ cần gọi một Service trong cluster. Nếu yêu cầu nghiệp vụ cần đọc từng endpoint, metadata hoặc tự chọn instance bằng Spring Cloud LoadBalancer, hãy cân nhắc DiscoveryClient.

## 4. Lựa chọn 2: Fabric8 Kubernetes Client

Fabric8 là thư viện Java client cung cấp API dạng fluent DSL để giao tiếp với Kubernetes API server. Spring Cloud Kubernetes cung cấp starter tích hợp Fabric8:

### Maven dependency

~~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-kubernetes-fabric8</artifactId>
</dependency>
~~~~

Hãy import Spring Cloud BOM tương thích với Spring Boot của dự án và để BOM quản lý phiên bản starter. Không tự chọn một phiên bản Fabric8 khác với dependency management của Spring Cloud Kubernetes.

Starter này cung cấp implementation `DiscoveryClient` dựa trên Fabric8. Ứng dụng có thể inject abstraction Spring Cloud thay vì tự gọi Fabric8 API trong code nghiệp vụ:

~~~~java
import java.util.List;

import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.discovery.DiscoveryClient;
import org.springframework.stereotype.Service;

@Service
public class ServiceCatalog {

    private final DiscoveryClient discoveryClient;

    public ServiceCatalog(DiscoveryClient discoveryClient) {
        this.discoveryClient = discoveryClient;
    }

    public List<String> listServices() {
        return discoveryClient.getServices();
    }

    public List<ServiceInstance> findInstances(String serviceId) {
        return discoveryClient.getInstances(serviceId);
    }
}
~~~~

`getServices()` trả về tên các Kubernetes Service mà client hiện nhìn thấy. `getInstances(serviceId)` trả về danh sách `ServiceInstance` tương ứng với service đó.

`getServices()` trả về tên service duy nhất, kể cả khi cùng tên xuất hiện ở nhiều namespace. `getInstances()` bổ sung namespace và metadata instance để caller có thêm ngữ cảnh. Nếu nhiều namespace có Service trùng tên, hãy giới hạn namespace hoặc lọc theo label để tránh chọn nhầm. Với Service có nhiều port, nên đặt tên port rõ ràng và cấu hình primary port thay vì phụ thuộc vào việc chọn port đầu tiên.

### Khi nào chọn Fabric8?

- Dự án đã dùng Fabric8 để làm việc với Kubernetes resource.
- Đội ngũ quen với fluent DSL và các model `io.fabric8.kubernetes.api.model`.
- Muốn dùng cùng client cho discovery và những tích hợp Spring Cloud Kubernetes khác có hỗ trợ Fabric8.
- Muốn chạy ứng dụng ngoài cluster để phát triển/debug bằng cấu hình Kubernetes client phù hợp, ví dụ kubeconfig.

Fabric8 là một thư viện client. Nó không thay thế Kubernetes API server, scheduler hoặc dataplane của cluster. Quyền truy cập của ứng dụng vẫn phải được giới hạn bằng ServiceAccount/RBAC hoặc credential phù hợp.

## 5. Lựa chọn 3: Kubernetes Java Client

Kubernetes Java Client là thư viện Java chính thức của Kubernetes, cung cấp API và model Java tương ứng với Kubernetes API. Spring Cloud Kubernetes tích hợp client này qua starter riêng:

### Maven dependency

~~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-kubernetes-client</artifactId>
</dependency>
~~~~

Starter này cũng cung cấp implementation `DiscoveryClient`. Ở tầng Spring Cloud, cách gọi `getServices()` và `getInstances()` giống với lựa chọn Fabric8. Khác biệt nằm ở thư viện Kubernetes nền, model Java và cách tùy biến client cấp thấp.

Ví dụ filter SpEL cho client này được đánh giá trên model `io.kubernetes.client.openapi.models.V1Service`. Với Fabric8, model tương ứng là `io.fabric8.kubernetes.api.model.Service`. Vì vậy, nếu ứng dụng dùng filter tùy chỉnh hoặc truy cập model client trực tiếp, cần viết theo đúng loại client đã chọn.

### Khi nào chọn Kubernetes Java Client?

- Dự án muốn dùng thư viện Java chính thức do Kubernetes SIG API Machinery duy trì.
- Đội ngũ đã có code hoặc tiện ích dựa trên các model `io.kubernetes.client`.
- Muốn giữ nhất quán với các tích hợp nội bộ đang dùng Kubernetes Java Client.
- Cần làm việc trực tiếp với các API/model được thư viện chính thức cung cấp.

Việc chọn client chính thức không tự động làm discovery nhanh hơn hoặc giảm quyền RBAC. Hai lựa chọn Fabric8 và Kubernetes Java Client đều cần truy cập API server, đọc đúng resource và được cấp quyền tương ứng.

### Không trộn hai hệ client trong cùng ứng dụng

Spring Cloud Kubernetes yêu cầu chọn một trong hai hệ client. Không kết hợp starter bắt đầu bằng `spring-cloud-starter-kubernetes-fabric8` với starter bắt đầu bằng `spring-cloud-starter-kubernetes-client` trong cùng ứng dụng. Hãy chọn một implementation và dùng nhất quán các starter thuộc hệ đó.

Ví dụ:

~~~~text
Được chọn:
- spring-cloud-starter-kubernetes-fabric8
- spring-cloud-starter-kubernetes-fabric8-config

Hoặc:
- spring-cloud-starter-kubernetes-client
- spring-cloud-starter-kubernetes-client-config

Không chọn đồng thời hai nhóm trên.
~~~~

Nếu ứng dụng chỉ cần discovery, dùng starter discovery tương ứng. Các starter hậu tố `-config` phục vụ đọc ConfigMap/Secret; starter hậu tố `-all` đưa vào nhiều tính năng hơn. Không cần thêm toàn bộ tính năng nếu ứng dụng chỉ truy vấn Service.

## 6. Lựa chọn 4: HTTP DiscoveryClient và Discovery Server

Spring Cloud Kubernetes có một implementation `DiscoveryClient` dựa trên HTTP:

~~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-kubernetes-discoveryclient</artifactId>
</dependency>
~~~~

Starter này được thiết kế để dùng cùng Spring Cloud Kubernetes Discovery Server. Discovery Server chạy trong cluster, truy vấn Kubernetes API và cung cấp HTTP endpoint để ứng dụng lấy danh sách service/instance.

Các endpoint chính của Discovery Server:

| Endpoint | Nội dung |
| --- | --- |
| `GET /apps` | Danh sách service và thông tin instance. |
| `GET /apps/{name}` | Danh sách instance của một service. |
| `GET /app/{name}/{instanceid}` | Thông tin của một instance cụ thể. |

Luồng hoạt động:

~~~~mermaid
flowchart LR
    A[Spring Boot app] -->|HTTP DiscoveryClient| D[Discovery Server]
    D -->|Kubernetes API| K[Kubernetes API Server]
    K -->|Services, Pods, Endpoints| D
    D -->|ServiceInstance JSON| A
~~~~

### Phạm vi quyền truy cập

Discovery Server cần ServiceAccount và RBAC để đọc Pod, Service và Endpoint. Ứng dụng tiêu thụ HTTP DiscoveryClient chỉ cần truy cập được endpoint HTTP của Discovery Server; nó không cần quyền đọc Kubernetes API chỉ vì dùng HTTP DiscoveryClient. Nếu ứng dụng còn dùng các tính năng Kubernetes khác, các quyền đó vẫn phải được cấp riêng.

### Khi nào chọn HTTP DiscoveryClient?

- Nhiều ứng dụng cần cùng nguồn discovery và muốn tập trung quyền truy cập Kubernetes API.
- Không muốn mỗi ứng dụng mang theo Kubernetes API client hoặc ServiceAccount có quyền đọc resource.
- Có thể vận hành Discovery Server như một thành phần hạ tầng dùng chung.
- Muốn cung cấp một HTTP boundary cho ứng dụng chạy ngoài cluster hoặc không tích hợp trực tiếp với Kubernetes API.

### Trade-off

- Thêm một dịch vụ trung gian và một network hop.
- Discovery Server trở thành thành phần cần được triển khai, giám sát, scale và bảo vệ.
- Cấu hình namespace/filter nằm ở server; client HTTP không tự quyết định phạm vi API mà server truy vấn.
- Nếu bật catalog watcher, cấu hình cần được bật đúng ở server và client theo phiên bản hỗ trợ.
- Cần căn chỉnh phiên bản HTTP DiscoveryClient và Discovery Server để tránh khác biệt hợp đồng API.

HTTP DiscoveryClient hữu ích khi cần tập trung quyền và giảm số ứng dụng gọi Kubernetes API trực tiếp. Với một ứng dụng nhỏ chỉ cần một Service DNS, triển khai Discovery Server thường không cần thiết.

## 7. Phạm vi namespace: tìm service ở đâu?

Khi dùng DiscoveryClient truy vấn Kubernetes API, cần xác định namespace mà client được phép tìm kiếm. Spring Cloud Kubernetes hỗ trợ ba cách:

### Một namespace

Đây là chế độ mặc định nếu không khai báo lựa chọn khác. Ứng dụng tìm service trong namespace được xác định theo quy tắc namespace resolution, thường là namespace nơi Pod đang chạy.

### Một số namespace cụ thể

Ví dụ:

~~~~yaml
spring:
  cloud:
    kubernetes:
      discovery:
        namespaces:
          - commerce
          - platform
~~~~

Chỉ tìm service trong các namespace đã chọn. Đây thường là lựa chọn phù hợp khi một ứng dụng cần gọi một vài nhóm service khác namespace.

### Tất cả namespace

~~~~yaml
spring:
  cloud:
    kubernetes:
      discovery:
        all-namespaces: true
~~~~

Chế độ này có thể làm tăng số lượng resource phải đọc/watch, tải lên Kubernetes API server và bộ nhớ cache của ứng dụng. Nó cũng yêu cầu quyền RBAC rộng hơn, thường là ClusterRole/ClusterRoleBinding. Chỉ bật khi có nhu cầu thực tế và đã đánh giá phạm vi quyền.

Với HTTP DiscoveryClient, cấu hình namespace được đặt ở Discovery Server thông qua deployment environment variables; không chỉ cấu hình ở ứng dụng HTTP client.

## 8. Lọc service và giảm kích thước catalog

Theo mặc định, DiscoveryClient có thể nhìn thấy mọi Service trong namespace scope đã chọn. Khi namespace có nhiều Service, hãy thu hẹp tập dữ liệu bằng label:

~~~~yaml
spring:
  cloud:
    kubernetes:
      discovery:
        service-labels:
          discovery-enabled: "true"
          team: commerce
~~~~

Chỉ những Service có đủ label phù hợp mới được đưa vào kết quả discovery. Tài liệu Spring Cloud Kubernetes lưu ý implementation dùng lister/cache được nạp bất đồng bộ; lọc bằng label giúp thu nhỏ tập Service cần giữ trong cache.

Có thể dùng SpEL qua `spring.cloud.kubernetes.discovery.filter` để lọc sâu hơn. Kiểu model trong expression phụ thuộc client:

| Client | Kiểu model Service trong SpEL |
| --- | --- |
| Fabric8 | `io.fabric8.kubernetes.api.model.Service` |
| Kubernetes Java Client | `io.kubernetes.client.openapi.models.V1Service` |
| HTTP DiscoveryClient | `io.kubernetes.client.openapi.models.V1Service` ở Discovery Server |

SpEL được đánh giá trong read-only context và không cho gọi tùy ý method. Dùng toán tử SpEL và map indexing theo tài liệu. Tránh expression phụ thuộc vào method call không được cho phép.

## 9. Endpoints và EndpointSlices

DiscoveryClient cần biết địa chỉ backend của Service. Spring Cloud Kubernetes hiện dùng API `Endpoints` mặc định; có thể bật `EndpointSlices` bằng:

~~~~yaml
spring:
  cloud:
    kubernetes:
      discovery:
        use-endpoint-slices: true
~~~~

EndpointSlice là API Kubernetes dùng để biểu diễn các endpoint backend theo nhóm, giúp Service hỗ trợ số lượng backend lớn và cập nhật endpoint hiệu quả hơn. Một Service có thể có nhiều EndpointSlice; các slice được liên kết bằng label `kubernetes.io/service-name`.

Trước khi bật EndpointSlice:

- Xác nhận Kubernetes cluster hỗ trợ API `discovery.k8s.io/v1`.
- Xác nhận phiên bản Spring Cloud Kubernetes đang dùng hỗ trợ property này.
- Cấp RBAC `get`, `list`, `watch` cho resource `endpointslices`.
- Kiểm tra startup vì cấu hình bật EndpointSlice trên cluster không hỗ trợ có thể khiến ứng dụng không khởi động được.

Ví dụ Role rule trong một namespace:

~~~~yaml
rules:
  - apiGroups: ["discovery.k8s.io"]
    resources: ["endpointslices"]
    verbs: ["get", "list", "watch"]
~~~~

Không bật EndpointSlice chỉ vì đó là API mới hơn. Hãy cân nhắc quy mô endpoint, phiên bản cluster, khả năng tương thích và quyền truy cập thực tế.

## 10. RBAC và xác thực Kubernetes API

Khi Fabric8 hoặc Kubernetes Java Client gọi trực tiếp API server, ứng dụng cần thông tin xác thực và quyền đọc resource. Trong cluster, thường dùng ServiceAccount gắn với Pod. Bên ngoài cluster, client có thể dùng kubeconfig hoặc credential được cấp theo chính sách môi trường.

Một Role tối thiểu minh họa cho discovery trong một namespace:

~~~~yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: service-discovery-reader
  namespace: commerce
rules:
  - apiGroups: [""]
    resources: ["services", "endpoints"]
    verbs: ["get", "list", "watch"]
~~~~

Nếu bật tính năng đọc Pod labels/annotations hoặc Discovery Server cần lấy thông tin Pod, bổ sung `pods` vào resources. Không cấp quyền đọc Pod nếu ứng dụng không dùng dữ liệu đó.

Gắn Role với ServiceAccount của workload bằng RoleBinding:

~~~~yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: inventory-discovery-reader
  namespace: commerce
subjects:
  - kind: ServiceAccount
    name: inventory-service
    namespace: commerce
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: Role
  name: service-discovery-reader
~~~~

Đây là ví dụ cơ bản. Hãy chỉ cấp resource mà feature thực sự dùng. Nếu chỉ đọc Service và Endpoints, không cấp quyền ghi. Nếu bật đọc Pod metadata hoặc EndpointSlices, thêm quyền đọc tương ứng. Với nhiều namespace, cân nhắc Role/RoleBinding riêng theo namespace; chỉ dùng ClusterRole/ClusterRoleBinding khi thật sự cần phạm vi toàn cluster.

Discovery Server cần quyền đọc Pod, Service và Endpoint để tổng hợp dữ liệu. Có thể cấp Role theo từng namespace mà server được phép đọc. Bảo vệ endpoint HTTP của Discovery Server bằng mạng nội bộ, xác thực và chính sách truy cập phù hợp; không biến API discovery thành endpoint công khai.

## 11. Dùng DiscoveryClient và LoadBalancer đúng vai trò

Ví dụ inject Spring Cloud `DiscoveryClient`:

~~~~java
import java.util.List;

import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.discovery.DiscoveryClient;
import org.springframework.stereotype.Service;

@Service
public class InventoryDiscovery {

    private final DiscoveryClient discoveryClient;

    public InventoryDiscovery(DiscoveryClient discoveryClient) {
        this.discoveryClient = discoveryClient;
    }

    public List<ServiceInstance> instances() {
        return discoveryClient.getInstances("inventory");
    }
}
~~~~

`DiscoveryClient` cung cấp danh sách instance mà client hiện biết. Nếu muốn gọi service theo tên và chọn instance cho mỗi request, tích hợp Spring Cloud LoadBalancer với HTTP client tương ứng. Đừng mặc định rằng chỉ thêm DiscoveryClient sẽ khiến mọi HTTP request tự động được cân bằng tải.

Phân biệt hai đường đi:

- **Service DNS:** caller gọi hostname Service; Kubernetes dataplane chọn backend.
- **DiscoveryClient + LoadBalancer:** ứng dụng lấy danh sách instance; Spring Cloud LoadBalancer chọn một instance ở phía client.

Nếu đã chọn một instance Pod IP từ DiscoveryClient rồi lại gửi request qua ClusterIP của Service, có thể xuất hiện hai lần chọn backend. Điều này đôi khi có chủ đích nhưng cần hiểu rõ để tránh nhầm lẫn về sticky session, health state và locality.

Ngoài ra, `spring.application.name` không tự tạo hoặc đổi tên Kubernetes Service. Nếu Spring Cloud component cần tìm local service instance qua tên ứng dụng, tên Kubernetes Service phải được đồng bộ với `spring.application.name`.

## 12. Chọn client theo tình huống

| Bối cảnh | Lựa chọn gợi ý | Lý do |
| --- | --- | --- |
| Ứng dụng chỉ gọi một Service nội bộ | Kubernetes Service DNS | Ít dependency, không cần quyền đọc Kubernetes API. |
| Ứng dụng cần `getServices()`/`getInstances()` và đội ngũ quen Fabric8 | Fabric8 DiscoveryClient | Dùng Spring abstraction cùng Fabric8 API/model. |
| Dự án đã chuẩn hóa Kubernetes Java Client | Kubernetes Java Client DiscoveryClient | Dùng cùng client/model với code tích hợp hiện có. |
| Nhiều ứng dụng cần discovery nhưng không muốn mỗi ứng dụng có RBAC đọc cluster | HTTP DiscoveryClient + Discovery Server | Tập trung truy cập Kubernetes API và phân quyền ở server. |
| Cần lọc service theo namespace/label và chọn Pod ở phía client | Fabric8 hoặc Kubernetes Java Client + LoadBalancer | Có danh sách instance và metadata để áp dụng logic phía client. |
| Service có nhiều endpoint và cần scale lớn | Đánh giá EndpointSlices | Dùng API endpoint hiện đại khi cluster và Spring Cloud version hỗ trợ. |

Không có một client luôn tốt nhất cho mọi hệ thống. Hãy chọn dựa trên nhu cầu API, mô hình quyền, thư viện mà đội ngũ đã dùng, số lượng ứng dụng, số namespace và chi phí vận hành Discovery Server.

## 13. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| `DiscoveryClient` không được tạo | Thiếu starter, cấu hình cloud platform hoặc auto-configuration không phù hợp. | Kiểm tra dependency, log condition evaluation và cấu hình Spring Cloud Kubernetes. |
| HTTP 403 từ Kubernetes API | ServiceAccount thiếu Role/ClusterRole hoặc thiếu verb/resource. | Kiểm tra ServiceAccount gắn với Pod và `kubectl auth can-i` cho đúng identity. |
| Chỉ tìm thấy Service trong namespace hiện tại | Discovery đang dùng namespace mặc định. | Cấu hình danh sách namespace hoặc all-namespaces nếu thực sự cần. |
| Discovery toàn cluster bị chậm | Quét quá nhiều namespace/resource hoặc cache quá lớn. | Giới hạn namespace, lọc bằng label và theo dõi API server. |
| Không khởi động khi bật EndpointSlice | Cluster không hỗ trợ API hoặc RBAC thiếu `endpointslices`. | Kiểm tra API discovery.k8s.io/v1 và quyền get/list/watch. |
| Hai loại Kubernetes client gây xung đột | Đã thêm đồng thời Fabric8 và Kubernetes Java Client starters. | Chỉ giữ một họ starter nhất quán. |
| HTTP DiscoveryClient không tìm thấy service | Discovery Server không chạy, sai URL hoặc server scope không bao gồm namespace đó. | Kiểm tra endpoint server, log server và cấu hình deployment. |
| Filter SpEL không hoạt động | Expression dùng model của client khác hoặc gọi method bị cấm. | Dùng đúng model Service và cú pháp read-only được hỗ trợ. |
| Service có tên khác với Spring application | `spring.application.name` không tự đổi `metadata.name` của Kubernetes Service. | Đồng bộ tên trong manifest Service và cấu hình ứng dụng. |
| Instance list rỗng hoặc port sai | Service chưa có endpoint ready hoặc port được chọn không rõ ràng. | Kiểm tra selector, readiness, Endpoint/EndpointSlice và tên port. |

## 14. Checklist trước khi chọn client

- [ ] Xác định ứng dụng chỉ cần DNS hostname hay cần danh sách instance qua `DiscoveryClient`.
- [ ] Nếu dùng API client, chọn Fabric8 hoặc Kubernetes Java Client; không trộn hai họ starter.
- [ ] Import Spring Cloud BOM tương thích với Spring Boot.
- [ ] Chọn namespace scope nhỏ nhất đáp ứng yêu cầu.
- [ ] Dùng service label/filter để giảm catalog nếu cluster có nhiều Service.
- [ ] Cấp RBAC read-only cho đúng ServiceAccount và resource.
- [ ] Chỉ bật EndpointSlice khi cluster, library version và RBAC đều hỗ trợ.
- [ ] Nếu dùng HTTP DiscoveryClient, triển khai và bảo vệ Discovery Server.
- [ ] Căn chỉnh phiên bản Discovery Server và HTTP client.
- [ ] Xác định rõ lớp nào chọn backend: Kubernetes dataplane hay Spring Cloud LoadBalancer.
- [ ] Kiểm tra tên Kubernetes Service khớp với `spring.application.name` khi Spring component cần tra cứu local instance.
- [ ] Theo dõi cache, API server load, lỗi 403, endpoint readiness và thời gian refresh.

## Ghi nhớ

- Kubernetes Service DNS là lựa chọn đơn giản khi ứng dụng chỉ cần một hostname ổn định trong cluster.
- Spring Cloud Kubernetes hỗ trợ Fabric8, Kubernetes Java Client và HTTP DiscoveryClient dựa trên Discovery Server.
- Fabric8 và Kubernetes Java Client không được dùng chung starter trong cùng ứng dụng.
- Hai client trực tiếp cần RBAC để đọc resource; HTTP Discovery Server giữ quyền đọc API ở phía server.
- Namespace scope, label filter và EndpointSlice ảnh hưởng đến lượng dữ liệu, quyền và tải Kubernetes API.
- `DiscoveryClient` cung cấp danh sách instance; Spring Cloud LoadBalancer mới đảm nhiệm lựa chọn instance khi được tích hợp.
- Chọn client theo phạm vi quyền, nhu cầu endpoint, thư viện hiện có và chi phí vận hành, không chỉ theo tên thư viện.

## Tài liệu tham khảo chính thức

- [Spring Cloud Kubernetes – DiscoveryClient](https://docs.spring.io/spring-cloud-kubernetes/reference/discovery-client.html)
- [Spring Cloud Kubernetes – Starters](https://docs.spring.io/spring-cloud-kubernetes/reference/getting-started.html)
- [Spring Cloud Kubernetes – Discovery Server](https://docs.spring.io/spring-cloud-kubernetes/reference/spring-cloud-kubernetes-discoveryserver.html)
- [Spring Cloud Kubernetes – Project Overview](https://docs.spring.io/spring-cloud-kubernetes/reference/index.html)
- [Kubernetes – Service](https://kubernetes.io/docs/concepts/services-networking/service/)
- [Kubernetes – DNS for Services and Pods](https://kubernetes.io/docs/concepts/services-networking/dns-pod-service/)
- [Kubernetes – EndpointSlices](https://kubernetes.io/docs/concepts/services-networking/endpoint-slices/)
