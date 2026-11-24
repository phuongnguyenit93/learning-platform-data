# ReactiveLoadBalancerClientFilter và phân giải ServiceInstance

## 1. Từ tên service đến một địa chỉ HTTP thực

Trong kiến trúc microservices, mỗi service có thể chạy nhiều instance, tự tăng/giảm số replica và thay địa chỉ khi triển khai lại. Nếu **Spring Cloud Gateway** luôn proxy request tới một host cố định, ví dụ `http://10.0.0.17:8080`, cấu hình trở nên dễ lỗi thời khi instance đó bị thay thế.

Thay vì biết địa chỉ của từng instance, route có thể trỏ đến **tên service logic**:

~~~yaml
uri: lb://inventory-service
~~~

Scheme `lb` (load-balanced) không có nghĩa Gateway sẽ thực hiện kết nối đến host tên `lb`. Gateway cần chọn một **ServiceInstance** của `inventory-service`, sau đó đổi URL đích thành địa chỉ HTTP(S) mà mạng thực sự truy cập được. Trong **Spring Cloud Gateway Server WebFlux**, bước phân giải đó do **ReactiveLoadBalancerClientFilter** phối hợp với **Spring Cloud LoadBalancer** thực hiện.

~~~mermaid
flowchart LR
    Client[Client] --> Gateway[Spring Cloud Gateway]
    Gateway --> Route[Route: lb://inventory-service]
    Route --> LB[ReactiveLoadBalancerClientFilter]
    LB --> Choices[ServiceInstance candidates]
    Choices --> A[Instance A: port 9001]
    Choices --> B[Instance B: port 9002]
    LB --> HTTP[HTTP routing to chosen instance]
    HTTP --> Client
~~~

Trong bài thuộc chương **Khám phá và cân bằng tải**, bạn sẽ học:

1. Vai trò của `ReactiveLoadBalancerClientFilter`, `ReactorLoadBalancer` và `ServiceInstance`.
2. Đường đi từ route `lb://service-id` đến URL `http(s)://host:port`.
3. Cách **service discovery**, nguồn danh sách instance và thuật toán chọn instance phối hợp.
4. Ví dụ hai backend thực và cấu hình load balancing trong Gateway.
5. Hành vi khi không có instance, khi instance lỗi kết nối và khi TLS được bật.
6. Cách vận hành an toàn cùng route predicate, filter chain, retry, circuit breaker, rate limiting và observability.

> **Phạm vi:** Nội dung hướng tới **Spring Cloud Gateway Server WebFlux**, dựa trên Reactor. Gateway Server Web MVC có những thành phần định tuyến và filter khác. Namespace YAML, dependency starter và một số API khác nhau theo phiên bản; cần đối chiếu với stack thực tế.

## 2. Vị trí của ReactiveLoadBalancerClientFilter trong filter chain

Sau khi một request khớp route predicate, Gateway thực hiện các filter của route cùng các GlobalFilter được sắp xếp theo order. Có thể hình dung luồng đi như sau:

~~~mermaid
flowchart TD
    A[Incoming HTTP request] --> B[RoutePredicateHandlerMapping]
    B --> C[FilteringWebHandler]
    C --> D[Path / header filters]
    D --> E[RouteToRequestUrlFilter]
    E --> F{Target scheme}
    F -->|lb| G[ReactiveLoadBalancerClientFilter]
    G --> H[Choose a ServiceInstance]
    H --> I[Reconstruct http/https target URI]
    I --> J[NettyRoutingFilter]
    F -->|http/https| J
    J --> K[Upstream HTTP server]
    K --> L[NettyWriteResponseFilter / HTTP response]
~~~

Sơ đồ đã đơn giản hóa các pha pre/post, filters bảo mật, metrics, xử lý lỗi và các phương thức định tuyến đặc biệt như `forward:` hay WebSocket. Các vai trò:

| Thành phần | Trách nhiệm |
| --- | --- |
| **RoutePredicateHandlerMapping** | Chọn route theo `Path`, `Method`, `Header`, `Host`... |
| **FilteringWebHandler** | Thực hiện chuỗi GlobalFilter và GatewayFilter cho route |
| **RouteToRequestUrlFilter** | Tạo URL đích logic từ URI route và request |
| **ReactiveLoadBalancerClientFilter** | Nếu URL yêu cầu cân bằng tải, chọn instance và cập nhật URL |
| **NettyRoutingFilter** | Gửi request HTTP(S) tới host/port cuối bằng Reactor Netty |
| **NettyWriteResponseFilter** | Tham gia ghi response upstream về client |

**ReactiveLoadBalancerClientFilter không trực tiếp gửi HTTP request đến backend.** Nó chọn địa chỉ và để routing filter tiếp theo thực hiện I/O. Điều này giúp tách trách nhiệm chọn instance khỏi trách nhiệm kết nối mạng.

### Ví dụ một request xuyên suốt

Client gửi:

~~~http
GET /api/inventory/items/42?warehouse=HCM HTTP/1.1
Host: api.example.test
~~~

Route:

~~~yaml
id: inventory-api
uri: lb://inventory-service
predicates:
  - Path=/api/inventory/**
filters:
  - StripPrefix=2
~~~

`StripPrefix=2` chuyển path thành `/items/42`. URL logic sau giai đoạn dựng URL đích có dạng:

~~~text
lb://inventory-service/items/42?warehouse=HCM
~~~

Giả sử load balancer chọn instance có địa chỉ `10.2.0.17:8080` và kết nối HTTP, URL dùng để gửi request có dạng:

~~~text
http://10.2.0.17:8080/items/42?warehouse=HCM
~~~

Load balancer tập trung giải quyết **service ID → instance**, không tự ý xóa query hoặc chuyển `/items/42` sang endpoint nghiệp vụ khác. Sự thay đổi path là trách nhiệm của `StripPrefix` trong ví dụ.

## 3. ServiceInstance chứa những thông tin nào?

`ServiceInstance` là một abstraction của Spring Cloud mô tả một phiên bản đang được cung cấp để phục vụ một service logic.

| API hoặc thuộc tính | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `getServiceId()` | Tên service logic | `inventory-service` |
| `getHost()` | Host hoặc IP | `10.2.0.17` |
| `getPort()` | Cổng dịch vụ | `8080` |
| `isSecure()` | Thông tin kết nối bảo mật của instance | `true` / `false` |
| `getUri()` | URI mô tả instance | `http://10.2.0.17:8080` |
| `getMetadata()` | Metadata tùy nguồn discovery | Zone, version, thông tin môi trường |
| `getInstanceId()` | ID riêng nếu nguồn hỗ trợ | `inventory-a7c` |

Ví dụ, cùng một `serviceId=inventory-service` có thể có hai ứng viên:

~~~text
A: host=10.2.0.17, port=8080, secure=false
B: host=10.2.0.18, port=8080, secure=false
~~~

**Có ServiceInstance không đồng nghĩa với instance thật sự khỏe mạnh.** Registry có thể vừa nhận heartbeat, cache có thể còn một địa chỉ đã bị thu hồi, hoặc ứng dụng chưa sẵn sàng vì dependency chưa hoạt động. Load balancer chọn trong những ứng viên nó nhận được, không tự bảo đảm kết nối HTTP sẽ thành công.

### Service ID khác DNS hostname

`lb://inventory-service` là yêu cầu phân giải theo danh sách ServiceInstance của Spring Cloud LoadBalancer. Nó khác với `http://inventory-service`, trong đó HTTP client sử dụng hostname và có thể dựa vào DNS của môi trường. Trong Kubernetes, một DNS Service có thể cân bằng tải, nhưng điều đó không tự biến `http://inventory-service` thành phân giải instance của Spring Cloud LoadBalancer.

Đừng suy ra chỉ từ service ID rằng hệ thống dùng Eureka, Consul, Kubernetes hay registry khác: cần biết **nguồn cấp danh sách instance** thật sự.

## 4. Các bước ReactiveLoadBalancerClientFilter thực hiện

Ở mức khái niệm, thành phần này:

1. Đọc URL hiện tại từ một **exchange attribute** mà các routing filter dùng chung.
2. Nhận ra URL có scheme `lb` (hoặc một scheme prefix cân bằng tải được hỗ trợ).
3. Tách service ID từ URL logic, ví dụ `inventory-service`.
4. Gọi cơ chế reactive load balancer để chọn một `ServiceInstance` cho service ID.
5. Nếu không có ứng viên, tạo phản hồi lỗi phù hợp (thường 503 theo cấu hình mặc định).
6. Nếu có ứng viên, dựng URI đích mới dùng host, port và scheme HTTP/HTTPS tương ứng.
7. Cập nhật URL đích trong `ServerWebExchange`, lưu URL gốc theo cơ chế của Gateway rồi tiếp tục filter chain.
8. Để routing filter thực hiện HTTP request dựa trên URL cụ thể vừa được chọn.

~~~mermaid
sequenceDiagram
    participant Client
    participant Gateway as Gateway filter chain
    participant Filter as ReactiveLoadBalancerClientFilter
    participant Load as ReactorLoadBalancer
    participant Supplier as ServiceInstanceListSupplier
    participant Netty as NettyRoutingFilter
    participant Service as Inventory instance

    Client->>Gateway: GET /api/inventory/items/42
    Gateway->>Gateway: Target lb://inventory-service/items/42
    Gateway->>Filter: Continue chain
    Filter->>Load: Choose inventory-service
    Load->>Supplier: Request candidate instances
    Supplier-->>Load: [A, B]
    Load-->>Filter: Selected B
    Filter->>Gateway: Target http://B:8080/items/42
    Gateway->>Netty: Continue routing
    Netty->>Service: HTTP request
    Service-->>Netty: HTTP response
    Netty-->>Client: Response via Gateway
~~~

Trong Spring Cloud LoadBalancer, bộ chọn reactive có thể được cung cấp qua `ReactorLoadBalancer<ServiceInstance>` (và các interface/cơ chế factory liên quan); danh sách ứng viên thường được cung cấp bởi `ServiceInstanceListSupplier`. Cơ chế tự động cấu hình và các class cụ thể thay đổi theo release; thông thường **không cần tự khởi tạo ReactiveLoadBalancerClientFilter bằng tay**.

## 5. Exchange attributes và thời điểm URL được thay đổi

Những attribute quan trọng trong `ServerWebExchange`:

~~~java
ServerWebExchangeUtils.GATEWAY_ROUTE_ATTR
ServerWebExchangeUtils.GATEWAY_REQUEST_URL_ATTR
ServerWebExchangeUtils.GATEWAY_ORIGINAL_REQUEST_URL_ATTR
~~~

| Attribute | Nội dung điển hình | Vì sao hữu ích |
| --- | --- | --- |
| `GATEWAY_ROUTE_ATTR` | Định nghĩa route đã chọn | Xác định route ID và URI route |
| `GATEWAY_REQUEST_URL_ATTR` | Trước chọn: `lb://inventory-service/items/42`; sau chọn: `http://10.2.0.17:8080/items/42` | Biết URL đích tại từng giai đoạn |
| `GATEWAY_ORIGINAL_REQUEST_URL_ATTR` | Các URL trước khi được thay thế | Theo dõi lịch sử biến đổi URL |

`ReactiveLoadBalancerClientFilter` đọc `GATEWAY_REQUEST_URL_ATTR`, phân giải instance, rồi cập nhật chính attribute đó. Các giá trị này là **dữ liệu nội bộ của exchange**, không phải HTTP header do client gửi.

### Scheme prefix

Một số cách viết URI route dùng **scheme prefix** để kết hợp load balancing với scheme như HTTP hoặc WebSocket. Khi đó Gateway có thể sử dụng attribute `GATEWAY_SCHEME_PREFIX_ATTR` để xác định bước xử lý phù hợp. Không nên tự ghép các scheme tùy tiện hoặc kết luận scheme cuối cùng bằng cách đọc URL client; phải kiểm tra cú pháp được **phiên bản Gateway thực tế** hỗ trợ.

### Vì sao custom filter cần biết thứ tự?

Nếu một custom GlobalFilter đọc `GATEWAY_REQUEST_URL_ATTR` trong pha **pre** rất sớm, giá trị có thể còn là `lb://...` hoặc chưa được chuẩn bị. Sau khi load balancer chạy thành công, giá trị thường là một HTTP(S) URI cụ thể. Cần đặt điểm quan sát đúng giai đoạn, chẳng hạn trong tín hiệu kết thúc của publisher downstream, hoặc dùng instrumentation có sẵn của load balancer và HTTP client.

## 6. Nguồn danh sách instance: service discovery và supplier

**Service discovery** trả lời: “Những instance nào được hệ thống biết tới?”. **Load balancing** trả lời: “Trong danh sách đó, chọn instance nào cho request này?”. **HTTP routing** trả lời: “Gửi request tới URL được chọn ra sao?”.

~~~mermaid
flowchart TD
    D[Registry hoặc cấu hình tĩnh] --> S[ServiceInstanceListSupplier]
    S --> F[Optional caching / filtering]
    F --> L[ReactorLoadBalancer]
    L --> I[Selected ServiceInstance]
    I --> G[ReactiveLoadBalancerClientFilter]
~~~

| Nguồn | Cách dùng | Giới hạn cần nhớ |
| --- | --- | --- |
| Danh sách tĩnh | Khai báo instance qua cấu hình hoặc custom supplier | Không tự biết replica mới nếu cấu hình không đổi |
| Eureka | Các service đăng ký tới registry | Phụ thuộc heartbeat, client và trạng thái registry |
| Consul | Catalogue/service discovery phù hợp | Cần dependency, network và health integration |
| Kubernetes | Discovery qua tích hợp Spring Cloud Kubernetes hoặc cơ chế tương đương | Phụ thuộc namespace, RBAC, endpoint readiness và cấu hình |
| Custom supplier | Lấy từ nguồn quản lý riêng | Tự chịu trách nhiệm cache, thread safety và xử lý lỗi |

Danh sách còn có thể qua các lớp lọc ứng viên theo zone/metadata, health check và cache nếu được cấu hình. **Các lớp này không tự hoạt động chỉ nhờ có metadata**. Tên chính xác và hành vi phụ thuộc Spring Cloud LoadBalancer và version.

### Đừng nhầm với DiscoveryClient Route Definition Locator

Hai việc khác nhau:

- **Route khai báo sẵn** với `uri: lb://inventory-service`: một API rõ ràng dùng service ID; ReactiveLoadBalancerClientFilter chọn instance khi request đã khớp route.
- **DiscoveryClient Route Definition Locator**: nếu được bật và cấu hình, có thể **tự sinh route definitions** từ các service được discovery biết tới.

Tự phát sinh route cho tất cả service có thể vô tình công khai API nội bộ. Ở Gateway public, cần kiểm soát route predicate, xác thực, phân quyền, giới hạn lưu lượng và chính sách mạng thay vì tự động phơi bày mọi service trong registry.

## 7. Ví dụ: cấu hình Gateway với hai instance tĩnh

Để thực hành mà chưa cần registry riêng, có thể dùng **SimpleDiscoveryClient** cung cấp hai instance của cùng một service logic. Đây là ví dụ cấu hình cho một dòng **Spring Cloud Gateway Server WebFlux** có namespace `server.webflux`:

~~~yaml
spring:
  cloud:
    discovery:
      client:
        simple:
          instances:
            inventory-service:
              - uri: http://localhost:9001
              - uri: http://localhost:9002

    gateway:
      server:
        webflux:
          routes:
            - id: inventory-api
              uri: lb://inventory-service
              predicates:
                - Path=/api/inventory/**
              filters:
                - StripPrefix=2
~~~

Để ví dụ hoạt động, cần:

1. Starter **Spring Cloud Gateway Server WebFlux** phù hợp với Spring Boot/Spring Cloud BOM.
2. **Spring Cloud LoadBalancer** trên classpath, thường qua dependency `spring-cloud-starter-loadbalancer`.
3. Khả năng cung cấp instance của **SimpleDiscoveryClient** từ bộ Spring Cloud Discovery đã cấu hình; load balancer phải nhìn thấy hai instance.
4. Hai backend thực chạy trên cổng 9001 và 9002, cùng hỗ trợ `GET /items/{id}`.

Đối với nhiều phiên bản trước, route YAML dùng `spring.cloud.gateway.routes` thay vì `spring.cloud.gateway.server.webflux.routes`. Chọn **đúng namespace và starter** cho release của dự án, không chép hai cấu hình song song rồi giả định chúng đều hoạt động.

`SimpleDiscoveryClient` phù hợp để hiểu thuật toán chọn instance; trong production, instance thường đến từ registry/orchestrator để có thể theo dõi scale-out/scale-in.

### Backend thử nghiệm có dấu nhận diện

Hai backend có thể dùng cùng một controller, chỉ khác giá trị cấu hình `instance.id`:

~~~java
import java.util.Map;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
class InventoryController {
    private final String instanceId;

    InventoryController(@Value("${instance.id:unknown}") String instanceId) {
        this.instanceId = instanceId;
    }

    @GetMapping("/items/{id}")
    Mono<Map<String, String>> getItem(@PathVariable String id) {
        return Mono.just(Map.of(
                "itemId", id,
                "handledBy", instanceId
        ));
    }
}
~~~

Khởi chạy hai bản ứng dụng backend, đặt `server.port` lần lượt là 9001 và 9002, `instance.id` là A và B. Nếu cấu hình được nạp đúng, response có dạng:

~~~json
{"itemId":"42","handledBy":"A"}
~~~

Hoặc:

~~~json
{"itemId":"42","handledBy":"B"}
~~~

Đó là **response minh họa**, chưa được chạy thực tế trong bài. `handledBy` chỉ là trường do backend demo tạo; nó không phải header mặc định của Gateway.

## 8. Kiểm thử route và hành vi chọn instance

Gửi nhiều lần qua Gateway:

~~~bash
curl -i 'http://localhost:8080/api/inventory/items/42?warehouse=HCM'
curl -i 'http://localhost:8080/api/inventory/items/42?warehouse=HCM'
curl -i 'http://localhost:8080/api/inventory/items/42?warehouse=HCM'
~~~

Một request sẽ trải qua:

1. `Path=/api/inventory/**` khớp route `inventory-api`.
2. `StripPrefix=2` tạo path `/items/42`.
3. URL logic tương đương `lb://inventory-service/items/42?warehouse=HCM`.
4. Load balancer lấy danh sách instance rồi chọn một trong A/B.
5. HTTP routing gọi `http://localhost:9001/items/42?warehouse=HCM` hoặc `http://localhost:9002/items/42?warehouse=HCM`.
6. Response có `handledBy` cho biết backend thử nghiệm nào đã xử lý.

Với cấu hình thường gặp, **round-robin** là thuật toán mặc định phổ biến. Nhưng đừng yêu cầu tuyệt đối rằng ba request đầu luôn là A-B-A: việc chọn phụ thuộc state load balancer, thứ tự danh sách, phiên bản, mức đồng thời, số Gateway replica và các request khác đang diễn ra.

| Tình huống | Kết quả cần kiểm chứng |
| --- | --- |
| Hai instance chạy | Sau nhiều request, có thể thấy cả A và B được chọn |
| Chỉ B có trong danh sách cung cấp | Request được chọn tới B |
| A đã tắt nhưng vẫn nằm trong danh sách tĩnh | Một số request có thể lỗi kết nối tới A |
| Danh sách rỗng | Bước phân giải không chọn được instance, thường trả 503 |
| URI dùng sai service ID | Không tìm đúng nhóm instance |
| Path không khớp route | Không đi qua route Inventory; status tùy các route/handler khác |
| Backend trả 404 | Route có thể đã đúng, nhưng tài nguyên backend không tồn tại |
| Query có `warehouse=HCM` | Backend nên nhận query tương ứng nếu các filter/proxy không sửa |

### Phân biệt route đã chọn với backend phản hồi thành công

Request trả HTTP 404 không nhất thiết có nghĩa Gateway không khớp route: có thể Gateway đã định tuyến thành công nhưng backend trả 404 cho `/items/42`. Tương tự, HTTP 503 có thể đến từ bước không chọn được instance, từ một service không sẵn sàng, hoặc từ filter fallback. Cần xem route ID, URL đích, exception và response upstream để xác định chính xác.

## 9. Khi không có ServiceInstance

Khi URL đích yêu cầu `lb` nhưng load balancer không tìm thấy instance cho service ID, **ReactiveLoadBalancerClientFilter** thông thường tạo phản hồi **503 Service Unavailable**. Một số phiên bản hỗ trợ chọn **404 Not Found** thay vì 503 qua tùy chọn `use404`.

Ví dụ tên thuộc tính được dùng ở một số dòng phiên bản:

~~~properties
spring.cloud.gateway.loadbalancer.use404=true
~~~

Ở các dòng mới, namespace có thể khác; hãy xác nhận trong tài liệu cấu hình của đúng phiên bản Gateway Server WebFlux. **Đổi sang 404 không chữa được lỗi discovery**.

| Trường hợp | Bước gặp lỗi | Cách hiểu |
| --- | --- | --- |
| Không có ứng viên cho service ID | Khi load balancer gọi chọn instance | Gateway thường có thể trả 503 |
| Có ứng viên nhưng cổng sai | Sau khi instance được chọn, tại HTTP client | Có thể lỗi kết nối hoặc timeout |
| Có instance nhưng chứng chỉ TLS sai | Sau bước chọn, tại TLS handshake | Lỗi trust/hostname/TLS policy |
| Có instance và kết nối được nhưng backend trả 503 | Backend ứng dụng | Response 503 phát sinh từ service |

Không nên dùng retry vô hạn hoặc đổi mọi 503 thành 200 để che lỗi phân giải. Nếu một service quan trọng không có instance, hệ thống cần tín hiệu giám sát độc lập và chính sách fallback theo nghiệp vụ.

## 10. Round-robin, metadata, zone và tình trạng health

Spring Cloud LoadBalancer có thể dùng các cơ chế lựa chọn và lọc ứng viên khác nhau tùy dependency, phiên bản và cách cấu hình:

| Khả năng | Ý nghĩa | Điều không nên suy diễn |
| --- | --- | --- |
| **Round-robin** | Lần lượt lựa chọn từ danh sách ứng viên | Không có bảo đảm mọi khoảng thời gian đều chia đều tuyệt đối |
| **Random selection** | Chọn ngẫu nhiên một ứng viên | Không có bảo đảm A và B được gọi bằng nhau trong một mẫu nhỏ |
| **Zone preference** | Ưu tiên một vùng/zone khi có cơ chế cấu hình phù hợp | Có metadata zone không tự làm Gateway chọn cùng zone |
| **Health-check supplier** | Có thể lọc các ứng viên theo tín hiệu health | Không thay thế readiness ở orchestrator và chính sách mạng |
| **Caching** | Giảm chi phí gọi nguồn discovery liên tục | Có khả năng thấy instance đã rời khỏi hệ thống trong một khoảng ngắn |
| **Hint/request-aware policy** | Điều chỉnh lựa chọn dựa trên context hoặc hint đáng tin cậy | Không mặc nhiên bật chỉ vì client tự đặt một header |

Một vấn đề thường gặp: instance A còn được liệt kê dù vừa tắt. Với danh sách tĩnh, Gateway **không tự loại A** chỉ vì request đến A bị lỗi. Khi dùng registry động, thông tin cũng cần thời gian để cập nhật qua heartbeat, cache hoặc sự kiện thay đổi.

### Health, readiness và mạng là ba khái niệm khác

1. **Liveness:** tiến trình ứng dụng có còn hoạt động không?
2. **Readiness:** instance đã sẵn sàng nhận request thực hay chưa?
3. **Reachability:** từ tiến trình Gateway, host/port hoặc TLS endpoint có thể truy cập được không?

Một backend có thể vẫn chạy, nhưng không sẵn sàng vì cơ sở dữ liệu bị lỗi. Nó cũng có thể sẵn sàng theo health endpoint nhưng không thể truy cập từ Gateway vì network policy. Tổ chức nào sử dụng health filtering cần xác định tín hiệu nào **thực sự điều khiển danh sách instance**.

### Sticky session không tự xuất hiện

Nếu backend lưu trạng thái phiên người dùng chỉ trong RAM của instance A, request tiếp theo được chọn tới B có thể không nhìn thấy dữ liệu. Round-robin không bảo đảm session affinity. Nên ưu tiên service stateless hoặc lưu session ở kho chia sẻ; nếu có nhu cầu sticky routing, cần cấu hình và kiểm thử cơ chế riêng, tính đến việc instance biến mất hoặc lưu lượng bị dồn không đều.

## 11. HTTPS phía client và HTTPS phía backend là hai kết nối khác

Một sự nhầm lẫn phổ biến: **client sử dụng HTTPS tới Gateway không đồng nghĩa Gateway sẽ dùng HTTPS tới backend**.

~~~mermaid
flowchart LR
    Browser[Client] -->|TLS hop 1| Gateway[Spring Cloud Gateway]
    Gateway -->|HTTP hoặc TLS hop 2| Service[Chosen ServiceInstance]
~~~

Trong bước tái dựng URL upstream, `ReactiveLoadBalancerClientFilter` có thể dùng thông tin `ServiceInstance.isSecure()` để quyết định scheme HTTP hay HTTPS. Ví dụ, nếu instance được mô tả không bảo mật, kết nối backend có thể dùng HTTP dù request từ client tới Gateway là HTTPS. Ngược lại, một instance secure có thể dùng HTTPS ở hop sau. Khi route dùng **scheme prefix** cụ thể, thứ tự ưu tiên scheme có thể khác; phải xác minh hành vi trong release đang chạy.

**isSecure không tự bảo đảm TLS đúng.** Bảo mật hop Gateway → backend còn phụ thuộc:

- Backend thật sự lắng nghe HTTPS tại cổng tương ứng.
- Chứng chỉ được ký bởi CA tin cậy hoặc nằm trong truststore hợp lệ.
- Tên máy chủ/IP dùng để kết nối phù hợp với tên trong chứng chỉ.
- Cấu hình HTTP client, giao thức TLS và cipher đáp ứng chính sách.
- Nếu có yêu cầu **mTLS**, chứng chỉ client của Gateway và xác minh phía backend được cấu hình đúng.
- Các proxy/sidecar giữa hai bên có thể tạo thêm TLS termination hoặc đường đi mạng riêng.

Không nên giải quyết lỗi trust/hostname bằng cách tắt xác minh chứng chỉ. Hãy sửa đúng DNS, chứng chỉ, truststore hoặc cách quảng bá địa chỉ của ServiceInstance.

### Header Forwarded và Host

Trong kiến trúc có TLS termination tại ingress, URL client công khai có thể là `https://api.example.test` dù Gateway nhận HTTP ở mạng nội bộ. Những header như `Forwarded`, `X-Forwarded-Proto` hoặc `X-Forwarded-Host` chỉ đáng tin khi được **proxy đáng tin cậy** thiết lập và client không thể giả mạo chúng để định tuyến hoặc tạo redirect.

Load balancer chọn **địa chỉ upstream**, không phải cơ chế xác thực danh tính của client. Backend cần nhận thông tin danh tính qua Spring Security/propagation phù hợp và kiểm tra quyền tài nguyên, không tin mọi `X-User-Id` do client tự cung cấp.

## 12. Tương tác với path rewriting và header filters

Một route có thể kết hợp nhiều filter:

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: product-api
              uri: lb://product-service
              predicates:
                - Path=/api/products/**
                - Method=GET
              filters:
                - StripPrefix=1
                - AddRequestHeader=X-Gateway-Source, edge
~~~

Request `GET /api/products/42?lang=vi` được route `product-api` xử lý. `StripPrefix=1` tạo path `/products/42`, sau đó load balancer chọn instance của `product-service`. Header `X-Gateway-Source: edge` có thể được thêm vào request gửi tới backend.

**Điều mà bước chọn ServiceInstance không tự làm:**

- Không thay path `/api/products/42` thành `/products/42` nếu không có path filter.
- Không quyết định query `lang=vi` phải có ý nghĩa gì.
- Không xác thực danh tính hay cấp quyền người dùng.
- Không bảo đảm `X-Gateway-Source` hoặc `X-Role` là header đáng tin chỉ vì nó tồn tại.
- Không kiểm soát dung lượng request body hoặc số kết nối dài hạn.
- Không bảo đảm mỗi POST chỉ được xử lý một lần khi có retry.

Khi kết hợp nhiều filter, hãy phân biệt **route order** (route nào được chọn) với **filter order** (filter nào chạy trước/sau). Nếu custom filter cần quan sát URL đã chọn, việc đọc quá sớm có thể chỉ thấy `lb://...`, không phải host cuối. Nếu custom filter tự thay đổi `GATEWAY_REQUEST_URL_ATTR` ngoài ý muốn, nó có thể bỏ qua bước load balancing hoặc gửi request tới địa chỉ khác.

## 13. Ví dụ GlobalFilter quan sát URL đã phân giải

Trong môi trường thử nghiệm, có thể dùng filter để xem route ID và target URI sau khi downstream hoàn tất. Đoạn code này **chỉ quan sát**, không quyết định instance:

~~~java
import java.net.URI;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.cloud.gateway.filter.GatewayFilterChain;
import org.springframework.cloud.gateway.filter.GlobalFilter;
import org.springframework.cloud.gateway.route.Route;
import org.springframework.core.Ordered;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

import static org.springframework.cloud.gateway.support.ServerWebExchangeUtils
        .GATEWAY_REQUEST_URL_ATTR;
import static org.springframework.cloud.gateway.support.ServerWebExchangeUtils
        .GATEWAY_ROUTE_ATTR;

@Component
public class ResolvedTargetObservationFilter implements GlobalFilter, Ordered {

    private static final Logger log =
            LoggerFactory.getLogger(ResolvedTargetObservationFilter.class);

    @Override
    public int getOrder() {
        return -1000;
    }

    @Override
    public Mono<Void> filter(ServerWebExchange exchange, GatewayFilterChain chain) {
        return chain.filter(exchange)
                .doFinally(signal -> {
                    Route route = exchange.getAttribute(GATEWAY_ROUTE_ATTR);
                    URI target = exchange.getAttribute(GATEWAY_REQUEST_URL_ATTR);

                    String routeId = route == null ? "none" : route.getId();
                    String scheme = target == null ? "none" : target.getScheme();
                    String host = target == null ? "none" : target.getHost();

                    log.debug("route={}, upstreamScheme={}, upstreamHost={}, signal={}",
                            routeId, scheme, host, signal);
                });
    }
}
~~~

**Giải thích:**

1. `chain.filter(exchange)` cho các filter downstream cơ hội lựa chọn instance và gửi request.
2. `doFinally` nhận tín hiệu khi publisher hoàn tất, lỗi hoặc bị cancel; lúc này attribute thường phản ánh URL đã được resolve nếu quá trình lựa chọn thành công.
3. Nếu load balancing lỗi sớm, `target` có thể còn là URI logic `lb://...`, chứ không có host upstream thực.
4. `doFinally` không đồng nghĩa request chắc chắn thành công ở backend; phải kiểm tra status và exception.
5. Không log raw query, Authorization, cookie hoặc body. Host và instance ID cũng cần giới hạn số lượng nhãn nếu đưa vào metric.

Trong production, nên ưu tiên **Micrometer/Actuator/tracing** mà Spring Cloud Gateway và HTTP client hỗ trợ. Ví dụ trên nhằm minh họa cách theo dõi kết quả của filter chain mà không tự gọi `subscribe()` hoặc `block()`.

## 14. Retry, circuit breaker và lựa chọn instance lỗi

**Chọn instance** chỉ là một bước. Hệ thống vẫn phải xử lý instance không phản hồi, timeout, mất kết nối, lỗi HTTP, circuit breaker và các thao tác không idempotent.

| Cơ chế | Vai trò | Rủi ro nếu dùng sai |
| --- | --- | --- |
| Discovery | Cho biết các instance được biết đến | Registry/cache có dữ liệu cũ |
| Load balancing | Chọn instance theo chính sách | Không bảo đảm instance được chọn khỏe mạnh |
| Timeout | Giới hạn thời gian chờ I/O | Deadline quá ngắn cắt request hợp lệ |
| Retry | Thử lại khi điều kiện cho phép | Làm tăng tải hoặc lặp side effect |
| Circuit breaker | Ngăn liên tục gọi dependency lỗi | Fallback có thể che dấu sự cố |
| Rate limiting | Giới hạn lượng HTTP request vào Gateway | Không tự cân tải giữa các instance |

### Retry có tự đổi sang instance khác không?

**Không nên mặc định là có.** Retry có thể chọn lại cùng instance hoặc chọn một instance khác, phụ thuộc filter retry, cơ chế load balancing, việc lựa chọn có được gọi lại hay không, policy tránh instance lỗi và version. Muốn bảo đảm loại bỏ instance vừa lỗi, phải cấu hình và kiểm chứng rõ ở stack hiện tại.

Đặc biệt với `POST /orders` hoặc thanh toán, backend có thể đã xử lý request nhưng response bị mất. Retry vào instance khác cũng có thể tạo đơn hàng/thanh toán trùng. Cần idempotency key và chính sách retry an toàn cho thao tác có side effect.

### Circuit breaker không tự xóa instance khỏi discovery

Circuit breaker giúp bảo vệ trước dependency đang suy giảm nhưng không nhất thiết thay đổi danh sách `ServiceInstance`. Nếu muốn hạn chế chọn instance không sẵn sàng, cần readiness probe, registry health, TTL/caching hoặc supplier/filter thích hợp. Dùng cả circuit breaker và health filtering một cách có chủ đích.

Với response SSE hoặc NDJSON đã gửi một phần, lỗi upstream xuất hiện **sau khi HTTP response được commit** không thể sửa status cũ thành 503. Retry toàn bộ stream có thể gây trùng event; cần thiết kế resume/replay ở cấp ứng dụng.

## 15. Bảo mật nguồn instance và service ID

Load balancing là một ranh giới định tuyến quan trọng: request sẽ được gửi đến host/port xuất hiện trong danh sách instance, vì vậy không chỉ code Gateway mà cả **nguồn service discovery** cần được bảo vệ.

1. **Không lấy service ID tùy ý từ path/header/query không tin cậy** rồi ghép trực tiếp thành `lb://...` để định tuyến động. Nếu business yêu cầu chọn một số service, hãy có allowlist và phân quyền.
2. **Bảo vệ quyền ghi vào registry**. Một bản ghi ServiceInstance giả có thể khiến Gateway gửi request đến địa chỉ nội bộ không mong muốn, gây rủi ro tương tự SSRF ở tầng định tuyến.
3. **Giới hạn mạng mà Gateway được phép kết nối**. Dùng network policy/firewall, phân vùng môi trường và TLS/mTLS theo chính sách.
4. **Tách staging/production và tenant**. Một service ID giống nhau ở nhiều vùng không được tự cho phép request vượt ranh giới.
5. **Xác thực/ủy quyền ở backend** vẫn cần thiết; Gateway route predicate và load balancer không chứng minh người dùng có quyền xem hoặc sửa tài nguyên.
6. **Không log thông tin nhạy cảm** khi debug URL đã resolve: token, cookie, query riêng tư, client identity và các header xác thực phải được bảo vệ.

Một registry đáng tin và một hạ tầng TLS đúng giúp Gateway tránh gửi dữ liệu tới nơi không được phép. Không nên dựa chỉ vào một header `X-Service-Id` do client gửi để quyết định route đến hệ thống nội bộ.

## 16. Quan sát và chẩn đoán lỗi theo từng chặng

Khi request thất bại, tách **route selection → instance selection → HTTP connection → backend response**.

| Hiện tượng | Nguyên nhân có thể | Cách kiểm chứng |
| --- | --- | --- |
| `lb://...` không hoạt động | Thiếu Spring Cloud LoadBalancer hoặc dependency/starter không tương thích | Kiểm tra classpath, auto-configuration, route đã nạp |
| Gateway trả 503 rất sớm | Nguồn instance không có ứng viên, service ID sai | Xem instance list, tên đăng ký, log bước choose |
| Đã chọn instance nhưng kết nối bị từ chối | Backend tắt, cổng sai, firewall | Gọi trực tiếp host/port từ mạng Gateway |
| Chỉ một backend được gọi | Nguồn chỉ có một instance, cache cũ hoặc policy chọn khác | Quan sát danh sách và thử nhiều request |
| Instance đã tắt vẫn được chọn | Danh sách tĩnh/registry cache chưa cập nhật | Kiểm tra health, TTL, refresh và supplier |
| Request backend nhận sai path | `StripPrefix` hoặc `RewritePath` sai | Log path ở backend thử nghiệm |
| Client thấy HTTPS nhưng upstream dùng HTTP | Hai TLS hop độc lập và `isSecure()`/scheme khác | Xem URL resolved và cấu hình TLS của backend |
| HTTP 404 sau routing | Backend không có tài nguyên hoặc route khác được chọn | Phân biệt 404 Gateway với 404 backend |
| Retry gây duplicate POST | Không có idempotency contract | Kiểm tra ID nghiệp vụ, retry và side effect |
| CircuitBreaker trả fallback mã 200 | Sự cố bị che trong metric status | Đo số fallback và lỗi upstream riêng |
| Custom filter thấy `lb://` thay vì host | Filter đọc attribute trước khi load balancing | Đổi thời điểm quan sát hoặc dùng instrumentation phù hợp |

### Quy trình chẩn đoán khuyến nghị

1. **Route:** request có khớp predicate và route ID mong đợi không?
2. **URI:** route có `lb://inventory-service` thật không, hay là `http://...`?
3. **Classpath:** dependency load balancer và discovery đã được tự động cấu hình đúng chưa?
4. **Ứng viên:** load balancer nhìn thấy bao nhiêu instance, host/port gì?
5. **Choose:** đã chọn được `ServiceInstance` chưa?
6. **Target URL:** `GATEWAY_REQUEST_URL_ATTR` đã thành `http(s)://host:port` hợp lệ chưa?
7. **HTTP/TLS:** request đã tới backend chưa; có lỗi kết nối, TLS hoặc timeout không?
8. **Nghiệp vụ:** backend nhận path, query, header và trả status/body có đúng hợp đồng không?
9. **Độ tin cậy:** retry, circuit breaker hoặc filter khác có làm thay đổi kết quả không?

Đừng khắc phục sự cố không có instance bằng cách tăng số lần retry vô hạn hoặc tắt TLS. Cần chẩn đoán đúng lớp hỏng rồi mới điều chỉnh cấu hình.

## 17. Metrics và năng lực vận hành

Trong production, nên theo dõi ít nhất các nhóm tín hiệu:

| Tín hiệu | Câu hỏi được trả lời |
| --- | --- |
| Request rate theo route và service | Route nào đang có tải cao? |
| Latency Gateway và upstream | Độ trễ xuất hiện ở proxy hay backend? |
| Instance count | Hệ thống có cập nhật scale-in/scale-out không? |
| No-instance / choose errors | Bao nhiêu request không chọn được ứng viên? |
| Connection/TLS/timeouts | Bao nhiêu lỗi xuất hiện sau bước chọn instance? |
| Retry và CircuitBreaker | Có hiện tượng retry storm hoặc fallback liên tục không? |
| HTTP 4xx/5xx | Lỗi ở client, Gateway hay backend? |
| Active connections, event-loop latency | Gateway có bị nghẽn tài nguyên reactive I/O không? |

Sử dụng tích hợp **Micrometer**, **Spring Boot Actuator**, logging và tracing phù hợp với phiên bản Spring Cloud Gateway. Endpoint quản trị phải có xác thực và giới hạn mạng; không để lộ toàn bộ route hay chi tiết hạ tầng ra internet.

**Cardinality của metrics rất quan trọng.** Route ID là nhãn hữu ích và thường có tập giá trị hữu hạn; raw URL query, request ID hoặc user ID có thể tạo vô hạn nhãn. Instance ID và IP cũng thay đổi nhiều khi autoscale; cân nhắc cách nhóm thay vì đưa trực tiếp vào mọi series.

Với nhiều Gateway replica, mỗi replica có thể có trạng thái round-robin riêng. Quan sát một Gateway không đủ để đánh giá phân phối traffic trên toàn cụm; cần tổng hợp theo route/service và phân biệt sai lệch do khác nguồn discovery.

## 18. Bài thực hành tổng hợp

**Bối cảnh:** Hệ thống bán hàng có Inventory service chạy hai instance. Gateway cung cấp API `GET /api/inventory/items/{id}` và dùng `lb://inventory-service`.

### Phần A — Cấu hình

1. Chạy hai backend Inventory trên cổng 9001 và 9002, cùng có endpoint `GET /items/{id}`, nhưng khác `handledBy`.
2. Cấu hình SimpleDiscoveryClient hoặc một registry động với hai ServiceInstance.
3. Bảo đảm có dependency Spring Cloud LoadBalancer tương thích.
4. Tạo route có `uri: lb://inventory-service`, predicate `Path=/api/inventory/**` và filter `StripPrefix=2`.

### Phần B — Chứng minh URL được phân giải

1. Gửi nhiều request qua Gateway; quan sát `handledBy` và đừng giả định A-B-A-B cố định.
2. So sánh `lb://inventory-service` ở cấu hình với URL `http://localhost:9001` hoặc `http://localhost:9002` mà HTTP client dùng.
3. Thử query `?warehouse=HCM`, kiểm chứng backend nhận path/query đúng.
4. Thêm filter quan sát đã nêu ở phần 13 trong môi trường thử nghiệm; kiểm tra URL đích và route ID mà không log token.

### Phần C — Mô phỏng lỗi

1. Dừng backend A nhưng **không sửa** danh sách tĩnh. Ghi lại trường hợp A vẫn được chọn và request lỗi kết nối.
2. Chỉ giữ B trong danh sách ứng viên; kiểm tra các request có thể đến B.
3. Đổi service ID trong route thành tên không có instance; quan sát hành vi no-instance.
4. Thử một timeout/retry GET có giới hạn, xem số lần backend được gọi và instance nào được chọn khi retry.
5. Đo riêng lỗi chọn instance và lỗi kết nối; xác nhận fallback không che giấu tỷ lệ hỏng.

### Phần D — Bảo mật

1. Xác minh kết nối Gateway → backend dùng HTTP hay HTTPS đúng chính sách.
2. Kiểm tra một header `X-User-Id` do client tự đặt không tự được tin như danh tính đã xác thực.
3. Nếu dùng registry động, thử scale lên/xuống và đo độ trễ phát hiện instance mới hoặc loại instance cũ.
4. Xác minh Spring Security và phân quyền dữ liệu được thực hiện ở đúng tầng.

**Tiêu chí đạt:** Route được chọn đúng, danh sách ServiceInstance được phân giải, địa chỉ HTTP(S) được chọn và path/query không bị đổi ngoài ý muốn. Phải phân biệt được **no-instance**, **connection failure** và **backend error** bằng bằng chứng từ logs/traces, backend và HTTP client; không dùng retry hoặc status rewrite để che sự cố.

## 19. Ghi nhớ

- **ReactiveLoadBalancerClientFilter** là bước phân giải URI load-balanced như `lb://service-id` sang một URL upstream cụ thể trong **Spring Cloud Gateway Server WebFlux**. Filter chọn instance, **không trực tiếp thực hiện HTTP request**.
- **Service discovery cung cấp danh sách**, **Spring Cloud LoadBalancer chọn ServiceInstance**, còn **routing filter** gửi HTTP(S) tới instance đã chọn.
- `GATEWAY_REQUEST_URL_ATTR` chứa URL tại giai đoạn định tuyến, `GATEWAY_ORIGINAL_REQUEST_URL_ATTR` hỗ trợ truy vết các URL trước thay đổi. Chúng là exchange attributes, không phải HTTP headers.
- Muốn route `lb://` hoạt động cần **load-balancer dependency**, **nguồn instance phù hợp** và namespace cấu hình tương thích. Route khai báo thủ công khác với việc tự động sinh route từ discovery.
- **Không có instance** thường dẫn đến **503**; **đã chọn instance nhưng không kết nối được** là lỗi ở bước khác. Quan sát từng tầng trước khi chọn retry/fallback.
- **TLS phía client và TLS phía backend độc lập**; `ServiceInstance.isSecure()` không thay thế cấu hình truststore, kiểm tra chứng chỉ hoặc mTLS.
- Load balancing không thay thế **health/readiness, security, authorization, rate limiting, circuit breaker, retry an toàn, metrics và tracing**. Phải kiểm chứng toàn bộ luồng request để vận hành cổng vào microservices đúng đắn và an toàn.
