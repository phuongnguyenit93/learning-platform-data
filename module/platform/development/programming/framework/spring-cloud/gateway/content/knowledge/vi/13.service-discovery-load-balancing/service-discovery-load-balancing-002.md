# Tích hợp Spring Cloud LoadBalancer với Gateway Server WebFlux

## 1. Bài toán: một service ID, nhiều instance

Ban đầu, API Gateway có thể chuyển yêu cầu đến backend cố định:

~~~yaml
uri: http://localhost:9091
~~~

Nhưng trong hệ thống microservices, cùng một `catalog-service` có thể chạy tại `localhost:9091`, `localhost:9092` hoặc nhiều pod với IP thay đổi liên tục. Nếu khai báo cứng một URL thì mỗi lần mở rộng, thay instance hoặc chuyển vùng triển khai đều phải chỉnh cấu hình gateway.

**Spring Cloud LoadBalancer** chọn một instance cụ thể của một dịch vụ logic. **Spring Cloud Gateway Server WebFlux** tích hợp nó qua URI đặc biệt:

~~~yaml
uri: lb://catalog-service
~~~

Client vẫn gọi một endpoint công khai ổn định như `GET /api/catalog/items/42`. Gateway chọn route bằng predicate, chạy filter chain, hỏi danh sách instance của `catalog-service`, chọn một instance và gửi HTTP request thật đến instance đó.

Bài thuộc chương **Khám phá và cân bằng tải** của **SPRING_CLOUD_GATEWAY**. Kiến thức này nối route predicate, filter chain, biến đổi path/header và service discovery với các yêu cầu vận hành: xác thực, rate limiting, circuit breaker, retry, TLS và quan sát request. Mục tiêu là hiểu **tại sao `lb://` hoạt động và cách kiểm chứng nó**, không chỉ chép một dòng cấu hình.

Sau bài này bạn sẽ:

1. Phân biệt **route**, **service ID**, **ServiceInstance**, **service discovery** và **load balancing**.
2. Giải thích luồng `ReactiveLoadBalancerClientFilter` của Gateway Server WebFlux.
3. Thêm dependency LoadBalancer và cung cấp instance bằng `SimpleDiscoveryClient` hoặc registry.
4. Dựng một gateway kết nối hai instance và quan sát backend được chọn qua header.
5. Phân biệt lỗi không khớp route, không tìm được instance, backend không kết nối được và backend tự trả lỗi.
6. Biết cách xem xét cache, health, retry, circuit breaker, TLS và metrics khi triển khai thật.

> **Phạm vi:** Bài dùng **Spring Cloud Gateway Server WebFlux** (reactive, thường kết hợp Reactor Netty). Gateway Server MVC có API tích hợp khác. Cần chọn Spring Boot, Spring Cloud BOM và starter tương thích với phiên bản đang chạy; tên property routes trong dòng WebFlux 4.x và 5.x khác nhau.

## 2. Năm khái niệm rất dễ nhầm

| Khái niệm | Ví dụ | Trả lời câu hỏi |
| --- | --- | --- |
| **Gateway route** | `catalog-api` | Request nào khớp, chạy filter gì, đích logic ở đâu? |
| **Service ID** | `catalog-service` | Tên logic cần tìm instance; **không phải** URL HTTP có thể gọi trực tiếp |
| **Discovery client** | `SimpleDiscoveryClient`, Eureka, Consul, Kubernetes discovery | Có những instance nào của service? |
| **`ServiceInstance`** | `catalog-service → localhost:9092` | Một backend cụ thể nằm tại host/port nào, secure/metadata ra sao? |
| **Spring Cloud LoadBalancer** | `RoundRobinLoadBalancer` | Với danh sách đã có, request này chọn instance nào? |

Ví dụ:

~~~text
catalog-service
  ├── instance A: http://localhost:9091
  ├── instance B: http://localhost:9092
  └── instance C: http://localhost:9093
~~~

Gateway chỉ cần route `uri: lb://catalog-service`, còn danh sách instance được cung cấp bằng một nguồn độc lập. **Discovery tìm danh sách; LoadBalancer chọn một phần tử; Gateway routing gọi HTTP** sau khi đã biết địa chỉ đích.

Route `order` dùng để phân xử các route có predicate chồng lấn. Nó **không phải thuật toán cân bằng tải**: sau khi route đã được chọn, LoadBalancer mới quyết định instance.

## 3. Luồng request của lb:// trong Gateway WebFlux

~~~mermaid
sequenceDiagram
    participant C as Client
    participant G as Gateway WebFlux
    participant L as Spring Cloud LoadBalancer
    participant D as Discovery / ServiceInstanceListSupplier
    participant A as catalog A :9091
    participant B as catalog B :9092
    C->>G: GET /api/catalog/items/42
    Note over G: Path predicate khớp catalog-api
    Note over G: StripPrefix=1 → /catalog/items/42
    G->>L: Chọn instance của catalog-service
    L->>D: Lấy danh sách instance
    D-->>L: A:9091 và B:9092
    L-->>G: Chọn B
    G->>B: GET /catalog/items/42
    B-->>G: 200 + X-Backend-Instance: B
    G-->>C: HTTP 200 + JSON + headers
~~~

Sơ đồ là **minh họa**, không ngụ ý request đầu tiên luôn được chọn vào B. Trình tự xử lý chính:

1. `RoutePredicateHandlerMapping` chọn route dựa trên request ban đầu.
2. `FilteringWebHandler` tổ chức `GlobalFilter` và các `GatewayFilter` của route theo thứ tự thích hợp; `StripPrefix` hoặc `RewritePath` có thể đổi đường dẫn.
3. `RouteToRequestUrlFilter` tạo URL đích logic, lưu trong exchange attribute `ServerWebExchangeUtils.GATEWAY_REQUEST_URL_ATTR`. Với `lb://catalog-service`, URL chứa scheme `lb` và service ID.
4. **`ReactiveLoadBalancerClientFilter`** nhận diện URI scheme `lb` (hoặc scheme prefix tương ứng), nhờ Spring Cloud `ReactorLoadBalancer` chọn một `ServiceInstance`, sau đó ghi đè URL logic bằng URL chứa **host, port và scheme** đã chọn. URL ban đầu được lưu ở attribute lịch sử của exchange.
5. Khi URL đã là `http://...` hoặc `https://...`, `NettyRoutingFilter` dùng HTTP client gửi request đến backend. Response được xử lý và ghi về client qua phần response của filter chain.

~~~text
Client URL:              http://localhost:8080/api/catalog/items/42?lang=vi
Route URI:               lb://catalog-service
Path sau StripPrefix:    /catalog/items/42
URL logic:               lb://catalog-service/catalog/items/42?lang=vi
Instance được chọn:      localhost:9092
URL HTTP thực tế:        http://localhost:9092/catalog/items/42?lang=vi
~~~

`lb://` không phải là scheme HTTP để browser tự gửi request và cũng không tự biến service ID thành địa chỉ IP bằng DNS. Để nó hoạt động, Gateway cần **starter LoadBalancer, nguồn instance và kết nối mạng đến instance**. Query, body và method không bị LoadBalancer sửa chỉ vì nó chọn instance; các gateway filter khác vẫn có thể tác động.

## 4. Dependency cần có

Ở các dòng Gateway **Server WebFlux mới**, dependency Maven điển hình:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-gateway-server-webflux</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-loadbalancer</artifactId>
    </dependency>
</dependencies>
~~~

Nhiều bản Gateway WebFlux trước đây dùng `spring-cloud-starter-gateway` thay cho starter Server WebFlux mới. **Dùng Spring Cloud BOM/release train tương thích với Spring Boot của dự án** để quản lý các phiên bản dependency. Không chọn các version Spring Cloud độc lập theo cảm tính và không thêm `spring-boot-starter-web` (Servlet MVC) khi muốn chạy Gateway Server WebFlux.

**Có bắt buộc có Eureka hay Consul không?** Không. Spring Cloud Commons cung cấp `SimpleDiscoveryClient`, có thể đọc danh sách instance tĩnh từ properties. Đây là cách lý tưởng để học tích hợp và kiểm thử `lb://` trước khi dùng registry thật. Trong production, registry hoặc discovery provider phù hợp sẽ cập nhật instance động khi scale hoặc thay pod/VM.

**Có cần `@EnableDiscoveryClient` không?** Với các dòng Spring Cloud hiện đại, thông thường không cần: implementation discovery client trên classpath có thể được tự cấu hình. Annotation không thay thế việc cấu hình registry và dependency.

## 5. Cấu hình một Gateway kết nối hai backend

Mô hình lab:

| Thành phần | URL | Công dụng |
| --- | --- | --- |
| Gateway | `http://localhost:8080` | Route `/api/catalog/**` và chọn instance |
| Instance A | `http://localhost:9091` | Trả header `X-Backend-Instance: A` |
| Instance B | `http://localhost:9092` | Trả header `X-Backend-Instance: B` |

### 5.1. application.yml cho Gateway Server WebFlux 5.x

~~~yaml
server:
  port: 8080

spring:
  application:
    name: catalog-gateway-lab
  cloud:
    discovery:
      client:
        simple:
          instances:
            catalog-service:
              - uri: http://localhost:9091
              - uri: http://localhost:9092

    gateway:
      server:
        webflux:
          routes:
            - id: catalog-api
              uri: lb://catalog-service
              predicates:
                - Path=/api/catalog/**
              filters:
                - StripPrefix=1
                - SetRequestHeader=X-Edge-Source, gateway-lab
                - AddResponseHeader=X-Gateway-Route, catalog-api
~~~

`spring.cloud.discovery.client.simple.instances.catalog-service` là danh sách địa chỉ của service logic. `spring.cloud.gateway.server.webflux.routes` chỉ khai báo **một route** có URI `lb://catalog-service`. `StripPrefix=1` bỏ phân đoạn `api` đầu tiên nên backend nhận `/catalog/items/42`, không phải `/api/catalog/items/42`.

Header `X-Edge-Source` và `X-Gateway-Route` dùng để quan sát hai chiều request/response, không phải chứng cứ xác thực người dùng.

### 5.2. application.yml cho Gateway Server WebFlux 4.2.x / 4.3.x

Các dòng WebFlux 4.x tương ứng thường đặt route dưới `spring.cloud.gateway.routes`, còn namespace **SimpleDiscoveryClient của Spring Cloud Commons** không thay đổi:

~~~yaml
server:
  port: 8080

spring:
  cloud:
    discovery:
      client:
        simple:
          instances:
            catalog-service:
              - uri: http://localhost:9091
              - uri: http://localhost:9092
    gateway:
      routes:
        - id: catalog-api
          uri: lb://catalog-service
          predicates:
            - Path=/api/catalog/**
          filters:
            - StripPrefix=1
            - SetRequestHeader=X-Edge-Source, gateway-lab
            - AddResponseHeader=X-Gateway-Route, catalog-api
~~~

Chỉ dùng **một namespace route phù hợp phiên bản** đang chạy. Nếu route không được nạp, request trả 404 trước khi LoadBalancer được gọi. Không nên vội kết luận rằng `SimpleDiscoveryClient` bị hỏng khi chưa xác minh route.

### 5.3. Vì sao ví dụ không bật discovery locator?

Ta chủ động khai báo route `catalog-api`; `SimpleDiscoveryClient` chỉ cung cấp danh sách instance cho service ID. **Discovery của instance** khác với **tự động sinh route từ registry**. Không cần bật `DiscoveryClient Route Definition Locator` để một route thủ công sử dụng `lb://`.

## 6. Xây dựng backend echo với cùng mã nguồn cho A và B

Tạo một Spring Boot project riêng cho backend, có dependency `spring-boot-starter-webflux`. Dùng một controller trả lại instance ID và các thông tin đã nhận.

`src/main/resources/application.yml`:

~~~yaml
server:
  port: ${PORT:9091}

demo:
  instance-id: ${INSTANCE_ID:A}
~~~

`src/main/java/demo/catalog/CatalogApplication.java`:

~~~java
package demo.catalog;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CatalogApplication {
    public static void main(String[] args) {
        SpringApplication.run(CatalogApplication.class, args);
    }
}
~~~

`src/main/java/demo/catalog/CatalogController.java`:

~~~java
package demo.catalog;

import java.util.LinkedHashMap;
import java.util.Map;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.ResponseEntity;
import org.springframework.http.server.reactive.ServerHttpRequest;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
public class CatalogController {
    private final String instanceId;

    public CatalogController(@Value("${demo.instance-id:A}") String instanceId) {
        this.instanceId = instanceId;
    }

    private Map<String, Object> describe(ServerHttpRequest request, String id) {
        Map<String, Object> data = new LinkedHashMap<>();
        data.put("instance", instanceId);
        data.put("method", request.getMethod().name());
        data.put("path", request.getPath().value());
        data.put("query", request.getURI().getRawQuery());
        data.put("itemId", id);
        data.put("edgeSource",
                request.getHeaders().getFirst("X-Edge-Source"));
        return data;
    }

    @GetMapping("/catalog/items/{id}")
    public ResponseEntity<Map<String, Object>> getItem(
            @PathVariable String id, ServerHttpRequest request) {
        return ResponseEntity.ok()
                .header("X-Backend-Instance", instanceId)
                .body(describe(request, id));
    }

    @PostMapping("/catalog/items/{id}")
    public Mono<ResponseEntity<Map<String, Object>>> echoBody(
            @PathVariable String id,
            @RequestBody Mono<Map<String, Object>> payload,
            ServerHttpRequest request) {
        return payload.map(body -> {
            Map<String, Object> data = describe(request, id);
            data.put("body", body);
            return ResponseEntity.ok()
                    .header("X-Backend-Instance", instanceId)
                    .body(data);
        });
    }
}
~~~

Đây là backend **echo**, không thực hiện cập nhật nghiệp vụ hay xác thực phiên. Với dự án production, không expose endpoint phản chiếu header/body nhạy cảm như vậy.

### 6.1. Khởi chạy ba tiến trình

Với Maven Wrapper và hai dự án đã tạo, mở ba terminal riêng.

~~~bash
# Terminal 1: trong project catalog backend
PORT=9091 INSTANCE_ID=A ./mvnw spring-boot:run

# Terminal 2: trong cùng project catalog backend, một terminal khác
PORT=9092 INSTANCE_ID=B ./mvnw spring-boot:run

# Terminal 3: trong project Gateway
./mvnw spring-boot:run
~~~

Cú pháp trên dành cho Bash. Trong Windows PowerShell, với mỗi backend hãy đặt biến môi trường trong cửa sổ tương ứng:

~~~powershell
# Terminal A
$env:PORT = "9091"
$env:INSTANCE_ID = "A"
.\mvnw.cmd spring-boot:run

# Terminal B, cửa sổ khác
$env:PORT = "9092"
$env:INSTANCE_ID = "B"
.\mvnw.cmd spring-boot:run
~~~

Ở terminal Gateway dùng `.\mvnw.cmd spring-boot:run`. Hai instance **phải là hai process** vì cùng mã nguồn nhưng dùng cổng khác nhau.

### 6.2. Kiểm tra backend trực tiếp trước

~~~bash
curl -i "http://localhost:9091/catalog/items/42?lang=vi"
curl -i "http://localhost:9092/catalog/items/42?lang=vi"
~~~

Instance A nên trả status 200, header `X-Backend-Instance: A` và JSON có `"instance":"A"`, `"path":"/catalog/items/42"`. Instance B có `X-Backend-Instance: B`. Nếu gọi trực tiếp không thành công, hãy sửa backend trước khi thử tích hợp gateway.

### 6.3. Kiểm chứng chọn instance qua Gateway

~~~bash
curl -i "http://localhost:8080/api/catalog/items/42?lang=vi"
~~~

Một response **minh họa**:

~~~http
HTTP/1.1 200 OK
X-Backend-Instance: B
X-Gateway-Route: catalog-api
Content-Type: application/json

{"instance":"B","method":"GET","path":"/catalog/items/42","query":"lang=vi","itemId":"42","edgeSource":"gateway-lab"}
~~~

Đây **không phải kết quả đã đo**; A hay B đều có thể được chọn.

Thử nhiều lần (Bash):

~~~bash
for i in $(seq 1 10); do
  curl -sS -D - -o /dev/null \
    "http://localhost:8080/api/catalog/items/42" |
    grep -i -E '^(HTTP/|X-Backend-Instance:|X-Gateway-Route:)'
done
~~~

Các kiểm tra cần thực hiện:

1. **Route:** có response header `X-Gateway-Route: catalog-api`.
2. **Đường dẫn:** backend thấy `/catalog/items/42`, chứng tỏ `StripPrefix=1` chạy.
3. **Query:** `lang=vi` còn nguyên khi không có filter sửa query.
4. **Request header:** `edgeSource=gateway-lab` ở JSON backend.
5. **Instance:** các response có thể mang `X-Backend-Instance: A` hoặc `B`. Với Round Robin mặc định, khi cả hai instance khả dụng, thông thường có thể quan sát cả hai sau nhiều request.

**Không cam kết cứ hai request liên tiếp sẽ luân phiên A–B tuyệt đối**: danh sách instance, concurrency, request khác cùng lúc, retry và số replica Gateway ảnh hưởng kết quả.

### 6.4. Kiểm thử POST body

~~~bash
curl -i -X POST "http://localhost:8080/api/catalog/items/42" \
  -H "Content-Type: application/json" \
  --data-binary '{"stock":12,"active":true}'
~~~

Backend được chọn phải nhận `POST`, path `/catalog/items/42` và JSON gồm `stock` dạng số, `active` dạng boolean. LoadBalancer **chọn instance**, không tự biến đổi body hay method. Nếu body mất, xem lại filter đọc request body, Content-Type, timeout và proxy khác.

## 7. Thuật toán, supplier, cache và health

Spring Cloud LoadBalancer dùng giao diện reactive `ReactorLoadBalancer<ServiceInstance>` và `ServiceInstanceListSupplier` để lấy ứng viên. Spring Cloud Commons cung cấp **`RoundRobinLoadBalancer` làm mặc định** và có thêm `RandomLoadBalancer`. Các thuật toán/supplier nâng cao cần cấu hình riêng; metadata không tự biến một route thành weighted balancing.

### 7.1. Round Robin theo context của Gateway

Với danh sách ổn định `[A, B]`, Round Robin thường chọn A → B → A → B… theo lượt. Nhưng:

- Mỗi **Gateway process** có LoadBalancer context riêng, không chia sẻ một bộ đếm toàn cục giữa mọi gateway replica.
- Danh sách instance có thể thay đổi do discovery/health check/cache.
- Nhiều request đồng thời, retry hoặc phiên traffic khác có thể khiến chuỗi quan sát không đơn giản.
- HTTP keep-alive chỉ tái sử dụng kết nối, không nhất thiết đồng nghĩa mọi request sẽ bám cùng instance.

Để đánh giá phân phối production, đo **request count, lỗi và latency theo instance** trong một khoảng thời gian thích hợp, không chỉ so vài response.

### 7.2. Cache danh sách instance

LoadBalancer hỗ trợ cache mặc định và cache dùng **Caffeine** khi dependency có mặt. Tài liệu Spring Cloud Commons mô tả các tham số như:

~~~yaml
spring:
  cloud:
    loadbalancer:
      cache:
        enabled: true
        ttl: 35s
~~~

`35s` là giá trị minh họa tương ứng mức mặc định trong tài liệu hiện hành; cần cân nhắc theo tốc độ cập nhật registry. Cache giúp giảm tải truy xuất discovery nhưng có thể giữ instance vừa ngừng hoạt động cho đến khi danh sách được làm mới.

Nếu discovery client tự cache danh sách (ví dụ một số cấu hình Eureka), việc cache thêm ở LoadBalancer có thể làm tăng trễ cập nhật. Có thể cân nhắc:

~~~yaml
spring:
  cloud:
    loadbalancer:
      cache:
        enabled: false
~~~

**Không tắt cache vô điều kiện ở production**: lựa chọn phụ thuộc loại discovery và chi phí truy vấn. Khi tự tạo chuỗi `ServiceInstanceListSupplier`, cần đặt cache đúng thứ tự; cache sau supplier lọc theo từng request có thể gây kết quả không mong muốn.

### 7.3. Health check và instance bị tắt

`SimpleDiscoveryClient` có danh sách **tĩnh**. Nếu bạn tắt instance B ở cổng `9092` nhưng vẫn để URI B trong cấu hình, danh sách discovery không tự mất B. LoadBalancer có thể chọn instance B và lỗi kết nối.

Spring Cloud Commons có `HealthCheckServiceInstanceListSupplier` để chủ động thăm dò instance; tính năng này đặc biệt hữu ích với nguồn danh sách tĩnh, nhưng cần **cấu hình supplier và health endpoint phù hợp**. Với registry đã quản lý health và trả instance healthy, thêm một tầng health check nữa có thể không cần thiết.

### 7.4. Weighted, zone, hint

Tài liệu Commons còn mô tả `WeightedServiceInstanceListSupplier`, `ZonePreferenceServiceInstanceListSupplier` và hint-based filtering. Chúng có thể ưu tiên instance mạnh, cùng zone hoặc có metadata phù hợp. Chỉ thêm `weight=5` vào metadata **không bảo đảm** load balancing theo weight nếu chưa kích hoạt supplier tương ứng.

## 8. Phân biệt 404, 503 và lỗi kết nối

| Tình huống | Giai đoạn | Kết quả thường gặp |
| --- | --- | --- |
| Không route nào khớp `Path` hoặc `Method` | Chọn route | **404** nếu không có handler khác |
| Route `lb://catalog-service` khớp, nhưng LoadBalancer nhận **0 instance** | Chọn instance | **503 Service Unavailable** mặc định |
| Instance có trong danh sách nhưng TCP không kết nối được | HTTP client/routing | Lỗi kết nối hoặc timeout, thường là **5xx** |
| Backend nhận sai path sau `StripPrefix` | Backend | Backend có thể trả **404** |
| Backend chủ động trả 500 | Backend | Gateway thường chuyển 500 về nếu filter khác không thay |
| Gateway chặn bởi xác thực/rate limiter | Security/filter trước routing | Có thể **401**, **403**, **429** |

Theo tài liệu Gateway WebFlux, khi không có instance, mặc định trả **503**. Nếu có lý do rõ ràng, có thể chuyển thành 404 bằng property tùy phiên bản:

~~~yaml
# Gateway Server WebFlux 5.x (tùy chọn)
spring:
  cloud:
    gateway:
      server:
        webflux:
          loadbalancer:
            use404: true
~~~

~~~yaml
# Gateway Server WebFlux 4.2/4.3 (tùy chọn)
spring:
  cloud:
    gateway:
      loadbalancer:
        use404: true
~~~

**Đừng đổi 503 sang 404 chỉ để giấu sự cố registry.** No-instance không giống endpoint không tồn tại. Property trên chỉ liên quan trường hợp thiếu instance, không biến lỗi kết nối hoặc HTTP 404 do backend trả thành một loại khác.

Thử nghiệm: tạm thay `lb://catalog-service` thành `lb://missing-service` rồi nạp lại route, request vẫn khớp `Path=/api/catalog/**` nhưng không có instance, nên thường trả 503. Khôi phục service ID sau khi thử. Trường hợp chỉ tắt B, danh sách vẫn chứa B và lỗi có thể là **connection refused**, không phải no-instance.

## 9. Registry và DiscoveryClient Route Definition Locator

Với registry như Eureka, Consul hoặc nền tảng Kubernetes, instance có thể được cập nhật động thay vì khai báo tĩnh. Khi có discovery client tương ứng trên classpath và đã cấu hình truy cập registry, route **khai báo thủ công** vẫn dùng `lb://catalog-service` như cũ; nguồn cung cấp danh sách instance thay đổi, nhưng ý nghĩa route không đổi.

### 9.1. Có nên bật discovery locator để tự tạo route?

`DiscoveryClient Route Definition Locator` có thể tự sinh route từ các service do discovery trả về. Theo tài liệu, mặc định các route này dùng `lb://serviceId`, có predicate kiểu `/serviceId/**` và filter rewrite bỏ phần `serviceId` khỏi path trước khi gửi backend.

Trong WebFlux **5.x**, bảng Configuration Properties chính thức mô tả:

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          discovery:
            locator:
              enabled: true
~~~

Với **WebFlux 4.2/4.3**, cấu hình thường là:

~~~yaml
spring:
  cloud:
    gateway:
      discovery:
        locator:
          enabled: true
~~~

> Một số trang hướng dẫn discovery locator 5.x vẫn hiển thị namespace cũ trong ví dụ; khi khác nhau, đối chiếu **bảng Configuration Properties của phiên bản đang chạy** và xác minh route runtime qua công cụ vận hành có bảo vệ, thay vì suy đoán từ một ví dụ.

**Cảnh báo bảo mật:** service được đăng ký trong registry **không mặc định có nghĩa nó nên public** qua Gateway. Chỉ bật tự sinh route khi đã kiểm soát service được expose, predicate/filter và authorization. Nếu tùy biến danh sách `discovery.locator.filters`, cần kiểm tra có thay mất filter rewrite mặc định bỏ `serviceId` khỏi path hay không.

### 9.2. Case của service ID và mạng Docker/Kubernetes

`catalog-service` trong `lb://catalog-service` phải khớp service ID discovery trả về theo quy tắc của provider; một số registry có thể chuẩn hóa chữ hoa/chữ thường. Trong Docker, `localhost:9091` từ Gateway **chỉ tới container Gateway**, không tới container catalog khác; phải dùng URI/mạng container phù hợp. Với Kubernetes, phân biệt DNS service name của cluster và discovery client cung cấp Pod/ServiceInstance, tránh lẫn chúng chỉ vì có cùng từ “service”.

## 10. TLS, header và các policy khi đã chọn instance

### 10.1. Client dùng HTTPS không đảm bảo backend được gọi qua HTTPS

~~~text
Client ── HTTPS ──> Gateway ── HTTP hoặc HTTPS ──> ServiceInstance
~~~

Theo tài liệu `ReactiveLoadBalancerClientFilter`, thuộc tính `isSecure` của `ServiceInstance` được chọn có thể quyết định scheme outbound. Vì vậy, client vào Gateway qua HTTPS **không bảo đảm** request xuống backend cũng dùng HTTPS. Cần cấu hình metadata URI/secure, truststore/certificate hoặc SSL bundle của Gateway HTTP client cho đúng topology; nếu yêu cầu mTLS, phải triển khai và kiểm tra riêng.

### 10.2. Host và X-Forwarded

Gateway có thể cập nhật `Host` và các header theo từng chặng. Nếu backend cần biết host/scheme gốc của client, hãy dùng `Forwarded`/`X-Forwarded-*` từ **proxy tin cậy** đã làm sạch header do Internet gửi. Header `X-Edge-Source: gateway-lab` trong ví dụ chỉ dùng chẩn đoán, không phải bằng chứng danh tính.

### 10.3. Retry, timeout, circuit breaker và rate limit

| Cơ chế | Quyết định | Lưu ý |
| --- | --- | --- |
| LoadBalancer | Instance nào nhận lần gọi | Có thể chọn instance lỗi nếu discovery chưa cập nhật |
| Timeout | Chờ kết nối/response bao lâu | Giới hạn thời gian và tài nguyên |
| Retry | Có gọi lại backend không | Một request client có thể thành **nhiều backend calls**, có thể tới instance khác |
| Circuit breaker | Có gọi service đang lỗi hay fallback | Không mặc định bảo vệ riêng từng instance |
| Rate limiter | Caller có được qua Gateway không | Khóa hạn mức cần dựa trên danh tính/API key/IP đã xác minh |

Với `POST` tạo đơn hàng/thanh toán, timeout có thể xảy ra **sau khi backend đã ghi dữ liệu**. Retry thiếu idempotency key/logic chống trùng sẽ tạo tác dụng phụ lặp. Đừng nghĩ thêm `spring-cloud-starter-loadbalancer` là tự động bật đầy đủ circuit breaker, retry nghiệp vụ hoặc rate limiter.

## 11. Quan sát và gỡ lỗi

Để theo dõi luồng `lb://`, nên thu thập route ID, service ID, instance host/port đã chọn, method/path client gọi, path gửi backend, status/latency, trace ID và nguồn lỗi. Kết hợp Micrometer/Actuator/Tracing khi dependencies và cấu hình phù hợp; bảo vệ endpoint quản trị, không ghi access token, cookie hoặc body nhạy cảm vào logs.

Trình tự kiểm tra hữu ích:

1. **Request đã tới Gateway?** Xác minh DNS/TLS/ingress/port và access logs.
2. **Có route khớp?** Đúng namespace và `Path=/api/catalog/**`, không có route `order` thấp hơn nuốt request?
3. **Filter sửa path/header đúng?** Backend cần nhận `/catalog/items/42` chứ không phải `/api/catalog/items/42`.
4. **Có LoadBalancer/supplier?** Dependency, service ID, danh sách instance do discovery trả về đúng?
5. **Instance kết nối được từ chính mạng Gateway?** Gọi trực tiếp địa chỉ instance từ môi trường Gateway.
6. **Backend có thấy request?** Kiểm tra response `X-Backend-Instance` và log backend.
7. **Có retry, cache, health, fallback?** So số lần gọi backend, metrics, trạng thái cache và trace.

| Triệu chứng | Nguyên nhân có thể | Bước tiếp theo |
| --- | --- | --- |
| Mọi request 404 | Route chưa được nạp hoặc predicate sai | Xác minh namespace/config runtime |
| Route khớp nhưng 503 | Không có instance cho service ID | Kiểm tra discovery, spelling, registry, health filtering |
| Xen kẽ 200 và lỗi kết nối | Một instance ngừng hoạt động nhưng còn trong danh sách | Gọi trực tiếp A/B, xem health/cache |
| Backend 404 | Path rewrite sai | Đối chiếu path backend nhận |
| Chỉ thấy A | B chưa chạy, danh sách không có B hoặc policy tùy biến | Kiểm tra instance supplier và nhiều request |
| HTTPS vào nhưng HTTP xuống | URI/`ServiceInstance.isSecure` và SSL config | Kiểm tra scheme outbound |
| Một request xuất hiện nhiều lần ở backend | Retry/timeout | Kiểm tra retry policy và idempotency |
| 401/403/429 trước backend | Security/rate limiter | Xác định request đã qua Gateway filter chưa |

## 12. Checklist trước khi triển khai

- [ ] Gateway **Server WebFlux** dùng Boot/Cloud BOM và starters tương thích, có LoadBalancer.
- [ ] Route `lb://...` dùng đúng service ID và có nguồn cung cấp instance.
- [ ] Đã phân biệt thứ tự route với thuật toán chọn instance.
- [ ] Host/port/URI/secure metadata đúng mạng thực tế và policy TLS.
- [ ] Cache/health refresh phù hợp, không tạo double cache không cần thiết.
- [ ] Discovery locator không tự công khai dịch vụ ngoài ý muốn.
- [ ] Đã kiểm tra path/query/header/body/status và instance thực tế bằng request thử.
- [ ] Có test no-instance, một instance down, backend timeout và mất registry.
- [ ] Retry/circuit breaker/timeout có giới hạn, POST ghi dữ liệu được bảo vệ khỏi lặp.
- [ ] Auth/rate limit dựa trên danh tính hoặc khóa tin cậy; backend vẫn phân quyền.
- [ ] Metrics/tracing phân biệt lỗi Gateway/discovery/backend, không log dữ liệu nhạy cảm.

## 13. Tài liệu Spring chính thức

1. [Gateway Server WebFlux — Global Filters](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/global-filters.html): `ReactiveLoadBalancerClientFilter`, cách phân giải `lb://`, lỗi 503 và scheme.
2. [Gateway 4.3 — Global Filters](https://docs.spring.io/spring-cloud-gateway/reference/4.3/spring-cloud-gateway-server-webflux/global-filters.html): hành vi tương ứng và namespace route 4.x.
3. [Spring Cloud Commons — LoadBalancer](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html): Round Robin, suppliers, caching, health checks, weighted/zone.
4. [Spring Cloud Commons — Common Abstractions](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html): `SimpleDiscoveryClient` và nguồn instance.
5. [Gateway — Configuration Properties](https://docs.spring.io/spring-cloud-gateway/reference/configprops.html): tiền tố `server.webflux.routes`, `server.webflux.loadbalancer.use404` và locator.
6. [Gateway — DiscoveryClient Route Definition Locator](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/the-discoveryclient-route-definition-locator.html): tự sinh route theo service ID.

**Ghi nhớ:** `lb://catalog-service` là **địa chỉ logic**, không phải URL HTTP trực tiếp. Gateway WebFlux chọn route bằng predicate, chạy filter của route, `ReactiveLoadBalancerClientFilter` chọn `ServiceInstance` nhờ LoadBalancer và discovery/supplier, rồi routing filter mới gửi HTTP(S) tới backend. Hiểu chuỗi này giúp kiểm soát khả năng mở rộng, bảo mật, timeout/retry, TLS và quan sát khi vận hành API Gateway.
