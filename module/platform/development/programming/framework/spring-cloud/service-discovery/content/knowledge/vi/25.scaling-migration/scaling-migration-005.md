# Chuyển từ địa chỉ cố định hoặc SimpleDiscoveryClient sang registry

Khi một microservice gọi dịch vụ khác bằng IP và port cố định, mỗi lần provider đổi địa chỉ hoặc tăng/giảm replica, consumer có thể phải sửa cấu hình và triển khai lại. `SimpleDiscoveryClient` giúp đưa các URI tĩnh vào cấu hình và tra cứu chúng qua abstraction `DiscoveryClient`, nhưng danh sách instance vẫn do con người quản lý; nó không tự phát hiện replica mới hoặc nhận biết instance đã dừng.

Chuyển sang registry như Eureka, Consul hoặc Zookeeper giúp provider đăng ký instance theo service name, còn consumer tìm instance bằng tên logic. Nếu consumer đã dùng `DiscoveryClient` và Spring Cloud LoadBalancer, phần lớn code gọi dịch vụ có thể giữ nguyên; thay đổi chính nằm ở discovery provider, cấu hình registry, địa chỉ được quảng bá và cách vận hành health check.

Bài học thuộc chương `Mở rộng và chuyển đổi` trong module `SPRING_CLOUD_SERVICE_DISCOVERY`. Module giúp người học hiểu cơ chế tìm instance theo tên dịch vụ qua `DiscoveryClient`, `ServiceRegistry`, Eureka hoặc Consul, cùng vòng đời đăng ký, health check, load balancing, bảo mật và xử lý sai lệch registry. Nội dung này hướng dẫn chuyển đổi từ URL cố định hoặc `SimpleDiscoveryClient` sang registry động theo từng giai đoạn, có kiểm chứng và rollback.

## 1. Ba cách định vị service thường gặp

Trước khi chuyển đổi, cần xác định ứng dụng hiện đang dùng cách nào. Ba cách dưới đây có thể cùng xuất hiện trong một hệ thống.

| Cách gọi | Ví dụ | Ai quản lý danh sách địa chỉ? | Hạn chế chính |
|---|---|---|---|
| Hard-coded address | `http://10.0.1.21:8080` trong code | Lập trình viên hoặc file cấu hình riêng. | Địa chỉ gắn chặt với môi trường; đổi IP/port phải cập nhật consumer. |
| `SimpleDiscoveryClient` | `http://inventory-service` với URI tĩnh trong YAML | Người vận hành khai báo từng URI trong cấu hình. | Có abstraction discovery nhưng không tự đăng ký, theo dõi hoặc cập nhật instance. |
| Registry-backed discovery | `http://inventory-service` với Eureka/Consul | Provider đăng ký; registry lưu trạng thái; consumer truy vấn. | Cần vận hành registry, bảo mật, health check và xử lý cache/độ trễ. |

Mục tiêu của migration không chỉ là thay IP bằng tên. Mục tiêu là chuyển trách nhiệm cập nhật danh sách instance từ các file cấu hình rời rạc sang vòng đời đăng ký và khám phá có kiểm soát.

## 2. Vì sao địa chỉ cố định khó mở rộng?

Giả sử `order-service` gọi `inventory-service` bằng địa chỉ `http://10.0.1.21:8080`.

- Khi inventory chuyển máy, địa chỉ cũ không còn hợp lệ.
- Khi scale từ một lên ba replica, consumer không biết các địa chỉ mới.
- Khi một replica dừng, consumer vẫn có thể tiếp tục gửi request tới địa chỉ cũ.
- Mỗi môi trường dev, test, staging và production cần một bộ địa chỉ khác nhau.
- Nhiều consumer phải cập nhật cùng lúc, tạo phụ thuộc triển khai giữa các service.
- Địa chỉ nội bộ có thể bị hard-code trong source, Docker image hoặc manifest, khiến việc đổi topology khó kiểm soát.

Ví dụ cấu hình cũ:

```yaml
clients:
  inventory:
    base-url: http://10.0.1.21:8080
```

Consumer đọc URL trực tiếp:

```java
WebClient client = WebClient.builder()
        .baseUrl("http://10.0.1.21:8080")
        .build();
```

Code này không biết có registry. Nó luôn gọi đúng một địa chỉ được cấu hình và không có bước lựa chọn instance.

## 3. SimpleDiscoveryClient giải quyết được gì và chưa giải quyết được gì?

`SimpleDiscoveryClient` là một implementation của `DiscoveryClient` trong Spring Cloud Commons. Khi classpath không có một registry-backed `DiscoveryClient`, Spring Cloud có thể dùng implementation này và đọc các instance từ cấu hình tĩnh dưới prefix `spring.cloud.discovery.client.simple.instances`.

Ví dụ:

```yaml
spring:
  cloud:
    discovery:
      client:
        simple:
          instances:
            inventory-service:
              - uri: http://10.0.1.21:8080
              - uri: http://10.0.1.22:8080
            pricing-service:
              - uri: http://10.0.2.31:8090
```

Consumer có thể tra cứu qua abstraction chung:

```java
List<ServiceInstance> instances =
        discoveryClient.getInstances("inventory-service");
```

Đây là bước tiến so với hard-code URL trong code: consumer chỉ biết service ID và có thể dùng Spring Cloud LoadBalancer để chọn một URI trong danh sách. Tuy nhiên, các URI vẫn là dữ liệu tĩnh. Khi replica thay đổi, người vận hành phải cập nhật cấu hình và triển khai lại hoặc refresh cấu hình theo cơ chế riêng.

### 3.1. SimpleDiscoveryClient không phải registry server

`SimpleDiscoveryClient` không cung cấp một server tập trung để provider đăng ký. Nó không tự phát hiện process mới, không nhận heartbeat từ provider và không có cơ chế tự xóa instance đã dừng. Nó trả danh sách đã khai báo trong cấu hình.

Do đó:

- Có thể dùng `SimpleDiscoveryClient` trong local development, test hoặc topology nhỏ và ổn định.
- Có thể dùng nó như một bước trung gian để loại service ID khỏi code consumer trước khi triển khai registry.
- Không nên xem danh sách static URI là bằng chứng instance đang khỏe.
- Cần tự cập nhật cấu hình nếu địa chỉ hoặc số replica thay đổi.

### 3.2. SimpleDiscoveryClient và DiscoveryClient là hai khái niệm khác nhau

`DiscoveryClient` là abstraction; `SimpleDiscoveryClient`, `EurekaDiscoveryClient` và `ConsulDiscoveryClient` là các implementation cụ thể. Vì vậy, nếu code đã phụ thuộc vào `DiscoveryClient`, việc chuyển từ Simple sang Eureka/Consul thường không đòi hỏi viết lại logic tra cứu.

Điều cần thay là implementation được cấu hình trong application context và nguồn dữ liệu mà nó sử dụng. Cần kiểm tra bean thực tế, đặc biệt khi ứng dụng có nhiều discovery integration hoặc `CompositeDiscoveryClient` tổng hợp nhiều nguồn.

Khi có nhiều discovery implementation cùng classpath, không mặc định mọi client đều được cộng danh sách theo cùng một cách. Các client có thứ tự (`Ordered`); với reactive composite, mặc định có thể dùng kết quả non-empty nhanh nhất, còn `spring.cloud.discovery.reactive.combine-instances=true` yêu cầu kết hợp kết quả từ các client. Có thể dùng `spring.cloud.discovery.reactive.order-enforced=true` để truy vấn theo thứ tự đã cấu hình. Vì vậy, khi chuyển nguồn, hãy xác định rõ implementation nào được dùng, thứ tự và chế độ combine; đừng để URI static cũ tiếp tục xuất hiện ngoài ý muốn.

## 4. Chuyển từ hard-coded URL sang service ID trước

Nếu consumer đang gọi trực tiếp IP/port, nên tách URL khỏi code và chuyển sang service ID trước. Trong giai đoạn này có thể dùng `SimpleDiscoveryClient` để giữ danh sách tĩnh.

Ví dụ cấu hình:

```yaml
spring:
  cloud:
    discovery:
      client:
        simple:
          instances:
            inventory-service:
              - uri: http://10.0.1.21:8080
              - uri: http://10.0.1.22:8080
```

Tạo `WebClient.Builder` có LoadBalancer:

```java
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
public class HttpClientConfiguration {

    @Bean
    @LoadBalanced
    WebClient.Builder loadBalancedWebClientBuilder() {
        return WebClient.builder();
    }
}
```

Consumer chỉ sử dụng service ID:

```java
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

@Service
public class InventoryClient {

    private final WebClient webClient;

    public InventoryClient(WebClient.Builder builder) {
        this.webClient = builder
                .baseUrl("http://inventory-service")
                .build();
    }

    public Mono<Item> findItem(String id) {
        return webClient.get()
                .uri("/api/items/{id}", id)
                .retrieve()
                .bodyToMono(Item.class);
    }
}
```

`Item` là DTO do ứng dụng định nghĩa. URL `http://inventory-service` là service ID, không phải DNS hostname thực tế. `@LoadBalanced` cho phép Spring Cloud LoadBalancer phân giải service ID thông qua discovery client.

Sau bước này, consumer đã tách khỏi địa chỉ vật lý. Danh sách vẫn tĩnh nhưng có thể được thay bằng registry-backed discovery mà không đổi URL trong client code, miễn là service ID được giữ ổn định.

## 5. Chuẩn hóa service name trước khi thêm registry

Chọn một tên logic cho mỗi service và dùng nhất quán ở provider, consumer, dashboard, manifest và tài liệu triển khai.

Ví dụ:

| Thành phần | Giá trị |
|---|---|
| `spring.application.name` của provider | `inventory-service` |
| Service name đăng ký trong registry | `inventory-service` |
| Service ID consumer gọi | `inventory-service` |
| URL trong LoadBalanced client | `http://inventory-service` |

Không dùng IP, hostname Pod hoặc instance ID làm service name. Service name là định danh nhóm; instance ID định danh từng bản chạy.

Trước khi migration, cần kiểm tra:

- Có service nào đang dùng tên khác nhau giữa các môi trường không?
- Có consumer nào đang gọi tên alias cũ không?
- Có registry-specific override như `eureka.instance.appname` hoặc `spring.cloud.consul.discovery.service-name` không?
- Có khác biệt chữ hoa/thường hoặc dấu gạch nối không?
- Service name có trùng với tên service khác trong cùng registry/namespace không?

Nếu cần đổi service name, nên làm như một thay đổi tương thích riêng: đăng ký tên mới, chuyển consumer theo từng nhóm, quan sát traffic rồi mới bỏ tên cũ. Không đổi tên provider và consumer đồng thời trên toàn hệ thống nếu chưa có cửa sổ chuyển đổi hoặc alias tương thích.

## 6. Chọn registry và chuẩn bị hạ tầng

Chọn registry theo môi trường vận hành và yêu cầu hệ thống:

| Lựa chọn | Khi phù hợp | Những việc cần chuẩn bị |
|---|---|---|
| Eureka | Hệ sinh thái Spring Cloud Netflix hiện hữu, cần registry client/server và health/lease integration. | Eureka Server cluster, peer configuration, TLS/auth ở lớp phù hợp, backup/monitoring và client starter. |
| Consul | Cần service catalog, health checks, ACL và có thể tích hợp các workload ngoài JVM. | Consul agent/server, datacenter, ACL token, TLS, health check và network access. |
| Zookeeper | Hệ thống đã dùng ZooKeeper/Curator hoặc cần service discovery dựa trên znode. | ZooKeeper ensemble, ACL/authentication, root path, Curator client và lifecycle registration. |
| Kubernetes Service/DNS | Các workload chạy trong Kubernetes và cần định vị service bằng tên cluster. | Kubernetes Service, selector, readiness, DNS, NetworkPolicy và port mapping. |

Không cần đưa thêm registry vào nếu nền tảng đã cung cấp discovery phù hợp. Ví dụ, ứng dụng chỉ chạy trong Kubernetes có thể dùng Service DNS trực tiếp; Spring Cloud Kubernetes DiscoveryClient hữu ích khi cần danh sách Pod/ServiceInstance hoặc tích hợp với Spring Cloud LoadBalancer.

Các ví dụ registry-backed trong bài bao gồm Eureka, Consul và Zookeeper. Chọn một registry làm nguồn chính cho mỗi service trong giai đoạn chuyển đổi để tránh kết quả discovery khó giải thích.

## 7. Chuyển provider sang tự đăng ký

Provider cần có discovery starter tương ứng và cấu hình kết nối registry. `spring.application.name` là service name mặc định phổ biến; instance ID, host, port và metadata cần được công bố đúng.

### 7.1. Provider với Eureka

Dependency:

```xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-netflix-eureka-client</artifactId>
</dependency>
```

Cấu hình ví dụ:

```yaml
spring:
  application:
    name: inventory-service

server:
  port: 8080

eureka:
  client:
    service-url:
      defaultZone: http://eureka.internal:8761/eureka/
    register-with-eureka: true
    fetch-registry: true
  instance:
    instance-id: "${spring.application.name}:${POD_UID:${spring.cloud.client.hostname}:${server.port}}"
    prefer-ip-address: true
```

`POD_UID` có thể được truyền từ Kubernetes Downward API hoặc từ nền tảng triển khai. Trên VM/container khác, dùng hostname hoặc instance ID do nền tảng cấp để bảo đảm các replica đồng thời không trùng ID trong phạm vi application name.

Ví dụ inject Pod UID vào container:

```yaml
env:
  - name: POD_UID
    valueFrom:
      fieldRef:
        fieldPath: metadata.uid
```

Eureka client thường tự đăng ký và renew lease theo lifecycle. Không cần tự gọi `ServiceRegistry.register()` nếu auto-registration đang hoạt động; thao tác thủ công có thể tạo đăng ký trùng hoặc xung đột lifecycle.

### 7.2. Provider với Consul

Dependency:

```xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-consul-discovery</artifactId>
</dependency>
```

Cấu hình ví dụ:

```yaml
spring:
  application:
    name: inventory-service
  cloud:
    consul:
      host: consul.internal
      port: 8500
      discovery:
        register: true
        service-name: inventory-service
        instance-id: "${spring.application.name}:${POD_UID:${spring.cloud.client.hostname}:${server.port}}"
        health-check-path: /actuator/health
        health-check-interval: 15s

server:
  port: 8080

management:
  endpoints:
    web:
      exposure:
        include: health,info
```

Consul Agent cần truy cập được host/port và health endpoint đã đăng ký. Nếu ứng dụng nằm sau NAT, trong container hoặc nhiều network, địa chỉ công bố phải là địa chỉ consumer/agent có thể truy cập; không mặc định `localhost` hoặc container IP luôn đúng.

### 7.3. Provider với Zookeeper

Dependency:

```xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-zookeeper-discovery</artifactId>
</dependency>
```

Cấu hình ví dụ:

```yaml
spring:
  application:
    name: inventory-service
  cloud:
    zookeeper:
      connect-string: zk-1.internal:2181,zk-2.internal:2181,zk-3.internal:2181
      discovery:
        enabled: true
        register: true
        root: /services/production
        instance-id: "${spring.application.name}:${POD_UID:${spring.cloud.client.hostname}:${server.port}}"
```

Zookeeper integration lưu service instance dưới root path. Cần cấu hình authentication/ACL và instance ID phù hợp với môi trường, sau đó xác nhận znode thực tế, host/port được công bố và session lifecycle trước khi chuyển consumer.

Các ví dụ Maven chỉ thể hiện starter. Hãy quản lý phiên bản Spring Cloud bằng release train BOM tương thích với phiên bản Spring Boot của ứng dụng; không tự trộn phiên bản Eureka, Consul, Zookeeper và LoadBalancer khác release train.

### 7.4. Kiểm tra provider đã đăng ký đúng

Trước khi chuyển consumer, xác nhận:

1. Service name đúng chuẩn.
2. Mỗi replica có instance ID riêng.
3. Host và port được công bố có thể truy cập từ consumer.
4. Health check phản ánh khả năng nhận traffic.
5. Metadata cần thiết như zone/version có mặt.
6. Khi provider dừng graceful, registration được deregister hoặc chuyển trạng thái phù hợp.

Không chuyển consumer chỉ vì provider log báo “registered”. Hãy kiểm tra registry catalog/dashboard và gọi endpoint từ network path thực tế.

## 8. Chuyển consumer sang registry-backed DiscoveryClient

Khi provider đã đăng ký ổn định, thêm discovery starter phía consumer và cấu hình registry endpoint. Nếu consumer đã dùng `DiscoveryClient` hoặc `@LoadBalanced WebClient`, phần lớn business code có thể giữ nguyên.

### 8.1. Consumer với Eureka

Dependency:

```xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-netflix-eureka-client</artifactId>
</dependency>
```

Nếu dùng `@LoadBalanced WebClient.Builder` và dependency graph của phiên bản đang dùng chưa đưa LoadBalancer vào classpath, thêm starter tương ứng:

```xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-loadbalancer</artifactId>
</dependency>
```

Cấu hình:

```yaml
spring:
  application:
    name: order-service

eureka:
  client:
    service-url:
      defaultZone: http://eureka.internal:8761/eureka/
    register-with-eureka: true
    fetch-registry: true
```

`register-with-eureka` quyết định consumer có đăng ký chính nó hay không; `fetch-registry` quyết định client có tải danh sách registry để khám phá service khác hay không. Nếu một ứng dụng chỉ gọi service và không cần tự công bố, hai mục tiêu này có thể được cấu hình độc lập theo vai trò.

### 8.2. Consumer với Consul

Dependency:

```xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-consul-discovery</artifactId>
</dependency>
```

Cấu hình tối thiểu:

```yaml
spring:
  application:
    name: order-service
  cloud:
    consul:
      host: consul.internal
      port: 8500
      discovery:
        register: true
```

Nếu consumer không cần đăng ký vào Consul, có thể tắt registration theo cấu hình integration nhưng vẫn giữ discovery để tra cứu service. Hãy kiểm tra đúng property của release train đang dùng.

### 8.3. Consumer với Zookeeper

Consumer dùng cùng starter và ensemble/root path mà provider sử dụng:

```yaml
spring:
  application:
    name: order-service
  cloud:
    zookeeper:
      connect-string: zk-1.internal:2181,zk-2.internal:2181,zk-3.internal:2181
      discovery:
        enabled: true
        register: false
        root: /services/production
```

`register: false` giữ vai trò consumer-only nếu ứng dụng không cần tự công bố. Discovery vẫn phải đọc được root path và các znode instance theo ACL đã cấp.

### 8.4. DiscoveryClient API không cần biết registry cụ thể

Code kiểm tra service có thể tiếp tục dùng abstraction chung:

```java
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

    public List<ServiceInstance> findInstances() {
        return discoveryClient.getInstances("inventory-service");
    }
}
```

Implementation được Spring cấu hình từ starter/auto-configuration. Không inject `EurekaClient` hoặc Consul client trực tiếp vào business service nếu không cần API đặc thù; giữ abstraction giúp đổi registry dễ hơn.

## 9. Chuyển nguồn danh sách mà không đổi business URL

Nếu consumer đang gọi `http://inventory-service` qua `@LoadBalanced WebClient.Builder`, URL có thể giữ nguyên khi chuyển từ `SimpleDiscoveryClient` sang Eureka, Consul hoặc Zookeeper.

| Trước migration | Sau migration |
|---|---|
| `SimpleDiscoveryClient` trả các URI tĩnh. | Eureka/Consul/Zookeeper trả các instance đã đăng ký. |
| `spring.cloud.discovery.client.simple.instances` chứa IP/port. | Registry starter và registry endpoint được cấu hình. |
| Consumer dùng service ID `inventory-service`. | Consumer tiếp tục dùng service ID `inventory-service`. |
| Người vận hành cập nhật static URI. | Provider tự đăng ký, renew và deregister. |
| Health không tự cập nhật theo process nếu không có cơ chế riêng. | Health/lease/check được registry integration cập nhật theo cấu hình. |

Khi chuyển, cần loại bỏ static entries cũ khỏi cấu hình production. Nếu SimpleDiscoveryClient và registry client cùng được cấu hình hoặc có `CompositeDiscoveryClient`, danh sách có thể được tổng hợp từ nhiều nguồn tùy application context. Một URI cũ có thể tiếp tục xuất hiện và được LoadBalancer chọn.

Không giả định việc thêm Eureka/Consul starter tự động vô hiệu hóa mọi custom `DiscoveryClient` bean hoặc static list. Kiểm tra bean composition và kết quả `getServices()`/`getInstances()` sau khi migration.

## 10. Spring Cloud LoadBalancer và lựa chọn instance

Registry-backed discovery chỉ cung cấp danh sách instance. Spring Cloud LoadBalancer chọn một instance cho request. Có thể dùng thuật toán mặc định hoặc cấu hình theo service ID.

Ví dụ WebClient:

```java
@Bean
@LoadBalanced
WebClient.Builder loadBalancedWebClientBuilder() {
    return WebClient.builder();
}
```

URL dùng service ID:

```java
webClient.get()
        .uri("http://inventory-service/api/items/{id}", id)
        .retrieve();
```

Khi chuyển từ static list sang registry, hãy xác minh:

- Supplier lấy instance từ đúng discovery client.
- Cache LoadBalancer không giữ static hoặc stale URI.
- Health state được áp dụng đúng.
- Zone/metadata filter không vô tình loại hết instance.
- Retry và timeout không che giấu service name sai hoặc registry rỗng.

## 11. Địa chỉ quảng bá phải truy cập được từ consumer

Một lỗi migration phổ biến là provider đăng ký thành công nhưng công bố địa chỉ không thể truy cập. Ví dụ, ứng dụng trong container đăng ký `127.0.0.1:8080`; consumer ở container khác không thể gọi loopback của provider.

Khi cấu hình registry, xác định rõ:

1. Provider bind vào interface nào?
2. Registry ghi host/IP nào?
3. Consumer chạy trong cùng subnet, VPC, Kubernetes cluster hay mạng khác?
4. Port có được publish/mapping qua container hoặc service mesh không?
5. TLS certificate có khớp hostname mà registry công bố không?

Với Eureka, có thể điều chỉnh `eureka.instance.hostname`, `eureka.instance.ip-address` và `prefer-ip-address` tùy môi trường. Với Consul, kiểm tra địa chỉ instance được đăng ký, agent network và các thuộc tính discovery tương ứng. Không chọn IP chỉ vì nó là IP của container; phải chọn địa chỉ có thể định tuyến từ mọi consumer liên quan.

## 12. Migration theo từng giai đoạn

Không nên đổi toàn bộ provider và consumer cùng lúc. Một lộ trình có thể chia thành các giai đoạn sau:

### Giai đoạn 1 – Lập bản đồ phụ thuộc

- Liệt kê tất cả URL/IP/port nội bộ đang được hard-code.
- Phân biệt endpoint nội bộ với endpoint external không thuộc service discovery.
- Ghi lại service name hiện tại, port, protocol, health path và số replica.
- Xác định consumer nào đã dùng `DiscoveryClient`, `SimpleDiscoveryClient` hoặc `@LoadBalanced`.
- Xác định network path và địa chỉ provider có thể quảng bá.

### Giai đoạn 2 – Chuẩn hóa service ID

- Chọn tên logic ổn định cho mỗi service.
- Chuẩn hóa `spring.application.name` và registry-specific override.
- Chốt instance ID strategy riêng cho từng replica.
- Định nghĩa metadata như zone/version nếu cần.
- Giữ alias cũ nếu cần một giai đoạn tương thích.

### Giai đoạn 3 – Triển khai registry

- Cài đặt Eureka/Consul cluster hoặc xác nhận nền tảng discovery đã sẵn sàng.
- Cấu hình network, TLS, authentication, ACL và monitoring.
- Kiểm tra failover, backup và quyền truy cập.
- Chưa chuyển toàn bộ consumer khi registry chưa ổn định.

### Giai đoạn 4 – Chuyển provider trước

- Thêm discovery starter và cấu hình registry endpoint.
- Bật auto-registration.
- Xác nhận service name, instance ID, host/port và health check.
- Scale provider lên nhiều replica và xác nhận mọi instance xuất hiện riêng biệt.
- Kiểm thử graceful shutdown và deregistration.

### Giai đoạn 5 – Chuyển consumer theo canary

- Chọn một consumer ít rủi ro.
- Thêm registry client và giữ service ID đã chuẩn hóa.
- Chuyển URL từ IP sang service ID qua LoadBalancer.
- Theo dõi số instance, tỷ lệ lỗi, timeout, latency và cache age.
- Mở rộng sang consumer khác sau khi canary ổn định.

### Giai đoạn 6 – Loại bỏ static source

- Xóa `spring.cloud.discovery.client.simple.instances` khỏi profile production khi không còn dùng.
- Xóa property chứa base URL nội bộ cũ và code tạo client trực tiếp từ IP.
- Kiểm tra không còn bean discovery tùy chỉnh trả static URI ngoài ý muốn.
- Giữ cấu hình static chỉ trong test/local nếu vẫn có ích.

### Giai đoạn 7 – Xác minh và đóng migration

- Scale up/down provider.
- Dừng một instance và xác nhận nó bị loại khỏi discovery/health.
- Thử registry hoặc một peer tạm thời không khả dụng.
- Xác nhận consumer xử lý timeout/retry và cache stale.
- Ghi lại runbook rollback và chủ sở hữu registry.

## 13. Ví dụ migration trước và sau

### Trước: địa chỉ cố định trong application config

```yaml
clients:
  inventory:
    base-url: http://10.0.1.21:8080
```

```java
WebClient inventoryClient = WebClient.builder()
        .baseUrl(inventoryBaseUrl)
        .build();
```

### Bước trung gian: SimpleDiscoveryClient

```yaml
spring:
  cloud:
    discovery:
      client:
        simple:
          instances:
            inventory-service:
              - uri: http://10.0.1.21:8080
              - uri: http://10.0.1.22:8080
```

Consumer chuyển sang `@LoadBalanced WebClient.Builder` và gọi `http://inventory-service`.

### Sau: Eureka registry

Provider:

```yaml
spring:
  application:
    name: inventory-service

eureka:
  client:
    service-url:
      defaultZone: http://eureka.internal:8761/eureka/
```

Consumer:

```yaml
spring:
  application:
    name: order-service

eureka:
  client:
    service-url:
      defaultZone: http://eureka.internal:8761/eureka/
```

Consumer vẫn gọi `http://inventory-service`; nguồn danh sách chuyển từ static YAML sang registry. Provider đăng ký từng replica, registry duy trì trạng thái và LoadBalancer chọn instance từ kết quả discovery.

## 14. Rollback có kiểm soát

Migration cần có phương án quay lại nếu registry hoặc client integration gặp lỗi.

Một rollback plan có thể gồm:

1. Giữ static URI list trong một profile/secret/config version tạm thời trong giai đoạn canary.
2. Dùng feature flag hoặc cấu hình deployment để chọn nguồn discovery đã được kiểm thử.
3. Nếu registry gặp sự cố, chỉ chuyển consumer canary về static source đã xác minh còn hoạt động.
4. Không bật đồng thời hai nguồn mà không biết cách `CompositeDiscoveryClient` tổng hợp kết quả.
5. Khi quay về static, xác nhận danh sách URI không chứa instance đã dừng và có đủ replica.
6. Ghi lại thời điểm rollback, service ID, consumer và lý do.

Static fallback không tự động an toàn. Nếu địa chỉ cũ đã thay đổi, rollback về static config có thể làm lỗi nặng hơn. Hãy duy trì danh sách fallback có kiểm tra và đặt thời hạn loại bỏ sau khi migration ổn định.

## 15. Những lỗi thường gặp khi chuyển đổi

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| `getInstances()` trả rỗng | Provider chưa đăng ký, sai service ID hoặc consumer dùng sai registry. | Kiểm tra service name, registry endpoint, profile và provider log. |
| Provider có trong registry nhưng consumer không thấy | Consumer trỏ sai cluster/datacenter/namespace hoặc cache chưa refresh. | So sánh endpoint, namespace và lần fetch gần nhất. |
| Consumer vẫn gọi IP cũ | URL hard-coded còn trong code/config hoặc static discovery source vẫn hoạt động. | Tìm toàn bộ cấu hình base URL, SimpleDiscoveryClient và custom bean. |
| Có hai bản ghi cùng một replica | Simple và registry sources được tổng hợp hoặc provider đăng ký nhiều lần. | Kiểm tra `DiscoveryClient` beans, `CompositeDiscoveryClient` và auto-registration. |
| Registry có instance nhưng gọi timeout | Host/port quảng bá không truy cập được từ consumer. | Kiểm tra route, container mapping, DNS, firewall và TLS. |
| Chỉ thấy một instance khi scale nhiều replica | Instance ID trùng hoặc provider registration thất bại. | Kiểm tra ID theo từng replica và registry-native record. |
| Instance cũ vẫn được chọn | Registry health/lease hoặc cache chưa cập nhật. | Kiểm tra health check, deregistration và LoadBalancer cache. |
| Local chạy nhưng production không chạy | Khác profile, service URL, credentials hoặc network. | So sánh cấu hình đã resolve và connectivity từ runtime production. |
| Consumer dùng nhầm service name | `spring.application.name` hoặc override khác nhau. | Chuẩn hóa service ID và kiểm tra `getServices()`. |
| Sau khi thêm starter có nhiều DiscoveryClient | Nhiều registry integration hoặc custom bean cùng tồn tại. | Xác định source chính, thứ tự và kết quả composite; loại nguồn thừa. |

## 16. Kiểm thử sau migration

Không chỉ kiểm tra một request thành công. Cần kiểm thử lifecycle và hành vi khi topology thay đổi:

- Khởi động hai hoặc nhiều provider replica và xác nhận registry có đủ instance.
- Xác nhận mỗi instance có ID riêng và địa chỉ có thể truy cập.
- Gọi consumer nhiều lần qua LoadBalancer và quan sát instance được chọn.
- Scale provider lên và xác nhận consumer nhìn thấy instance mới sau khoảng refresh dự kiến.
- Dừng một provider và xác nhận health/deregistration làm instance bị loại khỏi lựa chọn.
- Restart provider và xác nhận registration mới không ghi đè replica đang chạy.
- Tạm ngắt registry hoặc một peer để xác nhận consumer xử lý lỗi discovery và cache hiện có.
- Kiểm tra TLS/ACL/token và quyền tối thiểu.
- Xác nhận static source cũ không còn ảnh hưởng danh sách production.

Ví dụ kiểm tra bằng DiscoveryClient:

```java
List<ServiceInstance> instances =
        discoveryClient.getInstances("inventory-service");

assertThat(instances).isNotEmpty();
assertThat(instances)
        .allSatisfy(instance -> {
            assertThat(instance.getHost()).isNotBlank();
            assertThat(instance.getPort()).isPositive();
        });
```

Test cần chạy trong context đã cấu hình registry và sau khi provider test instance đăng ký thành công. Với test đơn vị, có thể mock `DiscoveryClient`; với test tích hợp, nên dùng registry test container hoặc môi trường kiểm thử có registry thật.

## 17. Checklist hoàn tất migration

| Nhóm | Câu hỏi |
|---|---|
| Inventory | Đã tìm hết URL/IP nội bộ hard-code chưa? |
| Service ID | Provider và consumer dùng cùng tên logic chưa? |
| SimpleDiscoveryClient | Static URI còn được cấu hình ở profile production không? |
| Registry | Registry cluster/agent có health, TLS, ACL và monitoring chưa? |
| Provider | Mọi replica đăng ký với instance ID riêng và address đúng chưa? |
| Health | Health check có phản ánh readiness và endpoint thực tế không? |
| Consumer | Đã dùng `DiscoveryClient`/LoadBalancer thay vì URL vật lý chưa? |
| Composite sources | Có nhiều discovery source hoặc static custom bean ngoài ý muốn không? |
| Network | Host/port công bố có truy cập được từ consumer không? |
| Cache | TTL/refresh của registry client và LoadBalancer đã được đánh giá chưa? |
| Rollout | Đã canary, scale test và rollback chưa? |
| Security | Credential không nằm trong source/config công khai và quyền là tối thiểu chưa? |
| Observability | Có metric/log về registration, health, discovery empty và request failure không? |

## Kết luận

Địa chỉ cố định gắn consumer với một endpoint vật lý. `SimpleDiscoveryClient` đưa danh sách URI tĩnh vào abstraction `DiscoveryClient`, giúp consumer dùng service ID và LoadBalancer nhưng vẫn yêu cầu người vận hành cập nhật danh sách. Registry như Eureka, Consul hoặc Zookeeper chuyển việc duy trì danh sách instance sang provider registration, heartbeat/session/health và consumer discovery.

Một migration an toàn bắt đầu bằng việc loại địa chỉ khỏi business code, chuẩn hóa service ID và chuyển consumer sang `DiscoveryClient`/LoadBalancer. Sau đó triển khai registry, chuyển provider đăng ký trước, xác minh instance ID, host/port và health, rồi chuyển consumer theo canary. Cuối cùng loại bỏ static source, kiểm tra không có discovery source trùng và thử scale, shutdown, registry outage cùng rollback. Nếu giữ service ID ổn định, phần lớn code gọi dịch vụ có thể không cần thay đổi khi đổi nguồn danh sách.

## Tài liệu tham khảo

- [Spring Cloud Commons – DiscoveryClient and SimpleDiscoveryClient](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html): abstraction DiscoveryClient và cấu hình static instances.
- [Spring Cloud LoadBalancer](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html): tích hợp discovery, supplier, cache và chọn instance.
- [Spring Cloud Netflix Eureka Client](https://docs.spring.io/spring-cloud-netflix/reference/spring-cloud-netflix.html): đăng ký instance và cấu hình Eureka client.
- [Spring Cloud Consul – Service Discovery](https://docs.spring.io/spring-cloud-consul/reference/discovery.html): service name, instance ID, health check và đăng ký Consul.
- [Spring Cloud Zookeeper – Service Discovery](https://docs.spring.io/spring-cloud-zookeeper/reference/discovery.html): service registration, discovery và cấu hình root path.
