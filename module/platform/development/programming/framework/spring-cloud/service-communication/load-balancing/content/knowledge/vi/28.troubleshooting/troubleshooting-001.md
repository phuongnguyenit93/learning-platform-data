# Không có bản sao khả dụng: kiểm tra từ nguồn danh sách đến bộ lọc

Trong một hệ thống microservices dùng **Spring Cloud LoadBalancer**, caller gửi request đến service ID như `http://inventory-service/api/stock/SKU-001`. Spring Cloud tìm danh sách `ServiceInstance`, có thể lấy qua discovery, cache và các bộ lọc health/zone/hint/version, rồi thuật toán Round Robin, Random hoặc thuật toán tùy biến chọn một instance.

Khi gặp cảnh báo kiểu **“No servers available for service: inventory-service”**, thông báo **“No instances available for inventory-service”** hoặc một lỗi 503 tại phía caller, cách xử lý hiệu quả nhất **không phải** tăng retry hay tự thêm một IP vào code. Cần tìm đúng điểm mà danh sách ứng viên trở thành rỗng: **nguồn discovery, bước làm mới/cache, các supplier lọc, hay bộ chọn cuối cùng**.

Bài thuộc chương **Chẩn đoán sự cố** của module **SPRING_CLOUD_SERVICE_COMMUNICATION_LOAD_BALANCING**. Ta sẽ xây một quy trình kiểm tra có thể áp dụng cho RestClient, WebClient, OpenFeign, health check, zone/hint routing và chính sách tùy biến. Kèm theo đó là lab với hai replica, đoạn mã chẩn đoán cục bộ, câu lệnh quan sát, bảng phân biệt lỗi và kiểm thử hồi quy.

> **Nguyên tắc:** “Không có instance được chọn” và “đã chọn instance nhưng kết nối đến nó thất bại” là **hai hiện tượng khác nhau**. Lỗi do LoadBalancer không có ứng viên thường cần kiểm tra service ID/discovery/supplier. Lỗi `Connection refused`, `ConnectTimeoutException` hoặc HTTP 503 từ backend cần kiểm tra network, instance và retry/timeout.

## 1. Xác định chính xác triệu chứng trước khi sửa

Cùng một request thất bại, các tầng có thể biểu hiện khác nhau:

| Triệu chứng | Gợi ý ban đầu | **Chưa thể kết luận** |
|---|---|---|
| Log `No servers available for service: inventory-service` | LoadBalancer không chọn được `ServiceInstance` | Không đồng nghĩa toàn bộ tiến trình backend đã dừng |
| `Response.hasServer() == false` | Bộ chọn trả response không có server | Không biết tại tầng nào list bị rỗng |
| `HTTP 503` từ caller/gateway | Có thể không có instance, hoặc upstream thật trả 503 | Không mặc định đây là lỗi discovery |
| `UnknownHostException: inventory-service` | HTTP client có thể đang cố giải DNS service ID trực tiếp | Không chắc LoadBalancer đã được tích hợp |
| `Connection refused` tới `10.0.0.12:8081` | Có host/port được chọn nhưng không thể kết nối | Không nên chẩn đoán là “discovery rỗng” |
| `Read timeout` | Request có thể đã đến backend nhưng backend không phản hồi kịp | Không chắc list supplier rỗng |
| `CallNotPermittedException` | Circuit breaker đang OPEN nên chặn HTTP call | Không kết luận LoadBalancer không có instance |
| Một số request thành công, số khác `503` | Có thể khác caller replicas, cache snapshots hoặc route/version | Không chứng minh registry luôn rỗng |

Phải lấy bằng chứng ở **đúng thời điểm** và **đúng caller replica** gặp lỗi. Việc chạy `curl` vào backend trực tiếp cho thấy một tiến trình đang phản hồi, **không chứng minh** Spring Cloud ở caller có thể nhìn thấy nó với đúng service ID.

### Quy ước dùng trong bài

- **Raw discovery list:** danh sách `DiscoveryClient` hoặc `ReactiveDiscoveryClient` trả về trước các bộ lọc LoadBalancer.
- **Candidate snapshot:** danh sách `ServiceInstanceListSupplier` trả về sau một hoặc nhiều decorators.
- **Selected response:** kết quả `ReactorServiceInstanceLoadBalancer.choose(Request)`; có instance hoặc không.
- **Attempt:** một lần HTTP client thật sự cố kết nối/gửi request.
- **Logical request:** một yêu cầu nghiệp vụ có thể sinh nhiều attempts do retry.

Không được trộn các số liệu này khi điều tra.

## 2. Sơ đồ đường đi của danh sách instance

~~~mermaid
flowchart TB
    REQ["Caller: service ID + Request context"] --> FACT["LoadBalancerClientFactory / client context"]
    REG["Registry / SimpleDiscoveryClient / DiscoveryClient"] --> SRC["Nguồn ServiceInstanceListSupplier"]
    FACT --> SRC
    SRC --> CACHE["Caching hoặc HealthCheck theo cấu hình"]
    CACHE --> FIL["Zone / Hint / Version / Custom filters"]
    FIL --> CHOOSE["RoundRobin / Random / Custom chooser"]
    CHOOSE --> DEC{"Có instance?"}
    DEC -->|Có| HTTP["RestClient / WebClient / OpenFeign transport"]
    DEC -->|Không| EMPTY["EmptyResponse / no-server"]
    HTTP --> DEST["Instance host:port"]
~~~

Đây là **sơ đồ khái niệm**. Không phải mọi ứng dụng đều bật cả cache, health, zone, hint và version; thứ tự thực tế được quyết định bởi `ServiceInstanceListSupplier` được cấu hình, các built-in/custom decorators và release train. Một số supplier có fallback hoặc có state riêng.

Hãy xác định **danh sách ở từng điểm**:

~~~text
serviceId = inventory-service

Registry / discovery                  [A, B, C]    size=3
Caching / health layer                [A, B]       size=2
Zone preference                       [A, B]       size=2
Hint preference                       [B]          size=1
API version strict filter             []           size=0
LoadBalancer choose                   no server
HTTP transport                        KHÔNG chạy
~~~

Tình huống trên minh họa một **version filter nghiêm ngặt** làm rỗng danh sách. Nếu ta chỉ nhìn registry còn ba instance thì vẫn chưa tìm được nguyên nhân.

## 3. Quy trình khoanh vùng theo ba phép so sánh

~~~mermaid
flowchart TD
    A["Request lỗi: không có instance"] --> B{"Service ID/caller client đúng?"}
    B -->|Không| B1["Sửa URL logic, @LoadBalanced, Feign name/url"]
    B -->|Có| C{"Raw discovery có instance?"}
    C -->|Không| C1["Kiểm tra registry, registration, namespace, network, cấu hình"]
    C -->|Có| D{"Final supplier list có instance?"}
    D -->|Không| D1["Kiểm tra cache, health và từng filter"]
    D -->|Có| E{"choose() trả hasServer?"}
    E -->|Không| E1["Kiểm tra custom chooser/request context/EmptyResponse"]
    E -->|Có| F["Kiểm tra HTTP transport, instance host:port, timeout/retry"]
~~~

**Thứ tự thực hành:**

1. Ghi lại **service ID**, URI logic, loại client, caller instance, trace/correlation ID, thời gian, status và exception class.
2. Kiểm tra chính HTTP client có tích hợp LoadBalancer chưa, hay đang dùng DNS trực tiếp/static URL.
3. Kiểm tra raw discovery list đúng **service ID**.
4. Kiểm tra kết quả cuối của `ServiceInstanceListSupplier` với **request context tương ứng**.
5. Nếu list cuối rỗng, tắt/kiểm tra **từng decorator** bằng môi trường thử nghiệm hoặc test supplier độc lập.
6. Nếu list cuối không rỗng nhưng `choose()` vẫn trả empty, xem custom chooser hoặc bug xử lý `Request`.
7. Nếu instance đã được chọn, chuyển sang network/health/timeout thay vì tiếp tục điều tra danh sách rỗng.

Đừng thay đồng thời discovery server, cache TTL, health path và retry: khi lỗi biến mất sẽ không biết thay đổi nào đã tác động.

## 4. Xác minh service ID và cách HTTP client gọi

Một lỗi rất dễ mắc là đăng ký `inventory-service` nhưng gọi `http://inventory` hoặc `http://INVENTORY-SERVICE` rồi dựa vào việc tên “trông có vẻ tương đương”. Service ID có thể được chuẩn hóa bởi một số registry, nhưng không nên giả định mọi provider, key và cache đều xử lý chữ hoa/thường/alias giống nhau.

~~~text
Registered service ID: inventory-service
Caller URI:           http://inventory-service/api/items/1  <-- cùng ID
Wrong URI:            http://inventory/api/items/1          <-- service khác
Physical URI:         http://localhost:8081/api/items/1     <-- bypass selection
~~~

### RestClient (đồng bộ)

~~~java
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;

@Configuration(proxyBeanMethods = false)
class HttpClientConfiguration {

    @Bean
    @LoadBalanced
    RestClient.Builder loadBalancedRestClientBuilder() {
        return RestClient.builder();
    }

    @Bean("inventoryRestClient")
    RestClient inventoryRestClient(
            @LoadBalanced RestClient.Builder builder) {
        return builder.clone()
                .baseUrl("http://inventory-service")
                .build();
    }
}
~~~

Chỉ có một `RestClient.Builder` bình thường và gọi hostname `inventory-service` mà **không gắn LoadBalancer** có thể dẫn đến `UnknownHostException`, không phải `EmptyResponse`.

### WebClient (reactive)

~~~java
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.web.reactive.function.client.WebClient;

@Bean
@LoadBalanced
WebClient.Builder loadBalancedWebClientBuilder() {
    return WebClient.builder();
}

@Bean("inventoryWebClient")
WebClient inventoryWebClient(
        @LoadBalanced WebClient.Builder builder) {
    return builder.clone()
            .baseUrl("http://inventory-service")
            .build();
}
~~~

WebClient chỉ thực hiện network I/O khi reactive publisher được subscribe. Nếu không có subscription, không có request và có thể cũng không có selection; đừng đọc “chưa thấy log LoadBalancer” như một bằng chứng list rỗng.

### OpenFeign

~~~java
import org.springframework.cloud.openfeign.FeignClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;

@FeignClient(name = "inventory-service")
public interface InventoryFeignClient {

    @GetMapping("/api/items/{sku}")
    ItemView get(@PathVariable("sku") String sku);
}
~~~

Cần `spring-cloud-starter-openfeign`, `@EnableFeignClients` và LoadBalancer integration phù hợp. Nếu cấu hình `@FeignClient(url = "http://localhost:8081", name = "inventory-service")`, hoặc URL cấu hình được gắn cố định, Feign có thể **không chọn qua discovery**, dù `name` vẫn hiện diện. Vì thế một request thành công từ Feign URL cố định **không chứng minh** supplier đang hoạt động.

## 5. Kiểm tra nguồn discovery trước khi xem bộ lọc

Spring Cloud Commons có cả `DiscoveryClient` (blocking) và `ReactiveDiscoveryClient`. Khi thêm một implementation như Eureka/Consul/Zookeeper, client truy vấn registry tương ứng. Khi không có registry-backed client, `SimpleDiscoveryClient` có thể lấy các instances từ properties.

Những nguyên nhân raw list rỗng thường gặp:

- Caller hỏi sai **service ID**.
- Provider chưa đăng ký, chưa đạt trạng thái đăng ký phù hợp, hoặc registry vừa xóa instance.
- Caller và provider không thuộc cùng namespace/cluster/environment.
- Caller thiếu discovery client dependency, bị disable/disconnect hoặc trỏ sai registry endpoint.
- Credentials/TLS/network đến registry lỗi; application vẫn startup nhưng discovery không có dữ liệu mong muốn.
- Với discovery tĩnh, YAML/properties khai báo sai key `spring.cloud.discovery.client.simple.instances` hoặc sai profile.
- Registry chỉ trả một phần thông tin vì health/status/capability filter ở phía registry.
- Có nhiều `DiscoveryClient` và thứ tự/composite behavior khiến kết quả không như dự kiến.

### Kiểm tra nhanh với `DiscoveryClient`

Đoạn probe **chỉ dành cho môi trường local/test**, chạy ở caller cùng application context với HTTP client:

~~~java
package com.example.order.diagnostics;

import java.util.List;
import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.discovery.DiscoveryClient;
import org.springframework.stereotype.Component;

@Component
public class DiscoverySnapshotProbe {

    private final DiscoveryClient discovery;

    public DiscoverySnapshotProbe(DiscoveryClient discovery) {
        this.discovery = discovery;
    }

    public void inspect() {
        List<ServiceInstance> instances =
                discovery.getInstances("inventory-service");

        System.out.println("raw discovery count=" + instances.size());

        for (ServiceInstance instance : instances) {
            System.out.printf(
                    "id=%s service=%s host=%s port=%d secure=%s%n",
                    instance.getInstanceId(),
                    instance.getServiceId(),
                    instance.getHost(),
                    instance.getPort(),
                    instance.isSecure()
            );
        }
    }
}
~~~

Đây chỉ là **phương thức inspect**, chưa tự động được gọi khi startup. Có thể gọi từ một `ApplicationRunner` trong profile local hoặc unit test; không publish trực tiếp địa chỉ backend ra endpoint công khai. Nếu ứng dụng chỉ dùng reactive discovery, hãy kiểm tra `ReactiveDiscoveryClient.getInstances(serviceId)` bằng một subscription trong test và so kết quả. Không gọi `block()` tùy tiện trên event loop của WebFlux.

**Lưu ý:** `DiscoveryClient.getInstances(...)` ở caller là phép đo nguồn registry/discovery, không phải final candidates sau các supplier. Nếu raw list vẫn có A/B/C nhưng HTTP client báo no-server, cần tiếp tục đến tầng supplier.

### Kiểm tra ở registry và provider

Với registry thật, kiểm tra đăng ký trực tiếp bằng công cụ/endpoint chính thức của registry đang sử dụng. Cần xác nhận **service ID, instance ID, host, port, protocol, metadata, trạng thái và thời điểm lease/heartbeat cuối**. Không dựa hoàn toàn vào UI từ một môi trường khác (ví dụ staging registry trong khi caller đang trỏ production registry).

Với Kubernetes, nếu discovery thông qua service/endpoints hoặc custom provider, cần kiểm tra selector/labels, endpoints và namespace ở **đúng cluster**. Nếu hạ tầng thực sự dùng DNS/server-side LB thay vì DiscoveryClient, câu chuyện chẩn đoán có thể khác: hãy xác nhận kiến trúc trước khi buộc một `ServiceInstanceListSupplier` phải có dữ liệu.

## 6. Tạo môi trường tái hiện với SimpleDiscoveryClient

Để cô lập vấn đề mà không cần registry bên ngoài, dùng một caller `order-service` tại 8080 và hai backend `inventory-service` tại 8081/8082.

~~~mermaid
flowchart LR
    O["order-service :8080"] --> LB["Spring Cloud LoadBalancer"]
    REG["SimpleDiscoveryClient"] --> LB
    LB --> A["inventory A :8081"]
    LB --> B["inventory B :8082"]
~~~

Caller `application.yml`:

~~~yaml
server:
  port: 8080

spring:
  application:
    name: order-service
  cloud:
    discovery:
      client:
        simple:
          instances:
            inventory-service:
              - instance-id: inventory-a
                uri: http://localhost:8081
                metadata:
                  zone: hcm
                  hint: blue
                  weight: "3"
              - instance-id: inventory-b
                uri: http://localhost:8082
                metadata:
                  zone: hn
                  hint: green
                  weight: "1"
    loadbalancer:
      zone: hcm
      retry:
        enabled: false
~~~

**Phân biệt dữ liệu cấu hình:**

- `inventory-service` là service ID cần gọi.
- `instance-id` dùng để đối chiếu log; `uri` là đích mạng thực tế.
- Metadata `zone/hint/weight` chỉ có tác dụng nếu các supplier tương ứng được bật.
- `spring.cloud.loadbalancer.zone=hcm` **không tự bảo đảm** policy zone được áp dụng; cần `ZonePreferenceServiceInstanceListSupplier` trong supplier chain hoặc configuration tương ứng.
- `retry.enabled=false` dùng trong lab để một request dễ tương ứng một lần chọn. Nếu có retry ở Feign/WebClient/gateway, phải tắt/kiểm soát riêng.
- `SimpleDiscoveryClient` là nguồn tĩnh; khi một backend dừng, nó có thể vẫn trả địa chỉ cũ.

Backend có thể dùng một controller đơn giản:

~~~java
package com.example.inventory;

import java.util.Map;
import org.springframework.core.env.Environment;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class InventoryDebugController {

    private final Environment env;

    InventoryDebugController(Environment env) {
        this.env = env;
    }

    @GetMapping("/whoami")
    Map<String, String> whoami() {
        return Map.of(
                "instance", env.getProperty("server.port", "?"),
                "service", "inventory-service"
        );
    }
}
~~~

Chạy hai tiến trình backend trên 8081 và 8082 (ví dụ bằng `--server.port=8081`/`--server.port=8082`), rồi thử:

~~~powershell
Invoke-RestMethod http://localhost:8081/whoami
Invoke-RestMethod http://localhost:8082/whoami
~~~

Nếu hai lệnh này thành công nhưng caller vẫn báo no-server, vấn đề ở **kết nối tới discovery/config/supplier ở caller**, không phải backend không có process. Nếu hai lệnh thất bại, cần khắc phục backend/network trước khi test chọn instance.

## 7. Quan sát nguồn và kết quả sau supplier ở cùng caller

Một kỹ thuật hữu ích là ghi **hai ảnh chụp danh sách** trong một phương thức chẩn đoán được kích hoạt có chủ đích: một từ `DiscoveryClient`, một từ supplier bean của **LoadBalancer child context theo service ID**.

Ví dụ dùng trong **caller Spring MVC/test**, không chạy trên Reactor event-loop:

~~~java
package com.example.order.diagnostics;

import java.time.Duration;
import java.util.List;
import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.discovery.DiscoveryClient;
import org.springframework.cloud.client.loadbalancer.DefaultRequest;
import org.springframework.cloud.loadbalancer.core.ServiceInstanceListSupplier;
import org.springframework.cloud.loadbalancer.support.LoadBalancerClientFactory;
import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Component;

@Component
@Profile("local")
public class InventorySupplierProbe {

    private static final String SERVICE = "inventory-service";

    private final DiscoveryClient discovery;
    private final LoadBalancerClientFactory factory;

    public InventorySupplierProbe(
            DiscoveryClient discovery,
            LoadBalancerClientFactory factory) {
        this.discovery = discovery;
        this.factory = factory;
    }

    public void inspect() {
        List<ServiceInstance> raw = discovery.getInstances(SERVICE);

        ServiceInstanceListSupplier supplier = factory.getInstance(
                SERVICE, ServiceInstanceListSupplier.class
        );

        System.out.println("discovery=" + instanceIds(raw));

        if (supplier == null) {
            System.out.println("supplier bean is absent");
            return;
        }

        List<ServiceInstance> finalList = supplier
                .get(new DefaultRequest<>())
                .next()
                .block(Duration.ofSeconds(3));

        System.out.println("finalSupplier=" +
                instanceIds(finalList == null ? List.of() : finalList));
        System.out.println("supplierType=" +
                supplier.getClass().getName());
    }

    private static List<String> instanceIds(
            List<ServiceInstance> instances) {

        return instances.stream()
                .map(ServiceInstance::getInstanceId)
                .toList();
    }
}
~~~

**Giới hạn của probe:**

1. `@Profile("local")` nhằm giới hạn sử dụng; không để endpoint hay log metadata backend công khai trong production.
2. `LoadBalancerClientFactory` tạo/đọc child context theo service ID. Lấy bean ở **context của `inventory-service`**, không từ parent context nơi có thể không tìm thấy supplier thật.
3. `DefaultRequest<>` không có HTTP headers, hint hoặc API version context. Probe này chỉ phản ánh **đường đi không có request-specific filter**; nó không chứng minh hint/version path của request lỗi.
4. `block(Duration)` chỉ phù hợp thread chẩn đoán local blocking, không được gọi trên Reactor event loop.
5. Một số supplier phát nhiều snapshots theo thời gian; `next()` lấy **snapshot đầu tiên**, không bảo đảm đó là snapshot mà một request khác đã dùng vài giây trước.
6. Nếu `raw` và `final` khác, cần quan sát **từng decorator**, không kết luận ngay health filter là thủ phạm.
7. Với nhiều caller replicas, lặp lại phép đo **trên replica gặp lỗi** vì mỗi JVM có client context/cache/scheduler riêng.

Nếu code dùng Spring Framework/JDK cũ hơn, điều chỉnh `Stream.toList()` và các APIs cho phù hợp. Các ví dụ cần chạy với BOM Spring Boot/Spring Cloud tương thích.

### Đo có an toàn với request-specific hint không?

Để kiểm tra một request mang `X-SC-LB-Hint` hay API version, hãy dùng **test/client integration đưa đúng `RequestDataContext`** vào `supplier.get(request)` hoặc quan sát `LoadBalancerLifecycle`. Không tự thêm một string vào `DefaultRequest<>` rồi cho rằng nó tương đương HTTP headers. Ưu tiên viết test của chính supplier decorator hoặc chạy endpoint WebClient/RestClient/OpenFeign thật với request context phù hợp.


## 8. Tầng cache: danh sách rỗng hoặc cũ có thể tồn tại sau khi registry đã đúng

`CachingServiceInstanceListSupplier` có thể cache kết quả lấy từ discovery để tránh truy vấn registry cho mỗi selection. Điều này giảm overhead, nhưng khiến trạng thái quan sát tại caller **không đồng bộ tức thời** với registry.

Ví dụ:

~~~text
14:00:00  Registry chưa có inventory-service
14:00:01  Caller lấy danh sách [] và cache snapshot
14:00:05  Inventory A/B đã đăng ký thành công
14:00:06  Registry trả [A, B], nhưng caller có thể vẫn dùng cache []
14:00:36  Cache refresh/expire; caller có thể thấy [A, B]
~~~

Timeline chỉ để minh họa, không phải cam kết cụ thể về lúc refresh. TTL thực tế còn phụ thuộc cách cache được tạo, eviction, traffic và cấu hình release train. Spring Cloud Commons mô tả `spring.cloud.loadbalancer.cache.ttl` có mặc định **35s** ở các bản tài liệu tương ứng, và cache có thể dùng Caffeine hoặc default implementation tùy classpath.

### Ba câu hỏi dành cho cache

1. `DiscoveryClient.getInstances(serviceId)` **đang** trả gì?
2. `CachingServiceInstanceListSupplier` hoặc discovery provider bên dưới đang trả gì?
3. Cache nằm ở đâu trong supplier chain, và có bao nhiêu tầng cache?

Đặc biệt, không nên cùng lúc cấu hình cache ở Eureka/registry client **và** cache ở LoadBalancer mà không biết TTL tổng. Spring Cloud khuyến nghị tránh double caching khi discovery client đã cache.

Cấu hình minh họa:

~~~yaml
spring:
  cloud:
    loadbalancer:
      cache:
        enabled: true
        ttl: 35s
~~~

Để **cô lập nguyên nhân trên môi trường lab**, có thể thử tắt caching:

~~~yaml
spring:
  cloud:
    loadbalancer:
      cache:
        enabled: false
~~~

**Không coi việc tắt cache là biện pháp chữa production mặc định.** Nếu request rate cao, mỗi selection truy vấn discovery có thể đẩy tải lớn lên registry. Nên xác định đúng nơi cache stale, TTL hợp lý và cách cập nhật/invalidate khi topology thay đổi.

### Đặt cache trước bộ lọc theo request

Cấu hình đúng ý tưởng:

~~~java
return ServiceInstanceListSupplier.builder()
        .withDiscoveryClient()
        .withCaching()
        .withZonePreference()
        .withHints()
        .build(context);
~~~

Cần đặt `CachingServiceInstanceListSupplier` ngay sau supplier lấy instance từ mạng, **trước** các bộ lọc theo zone/hint/request, tránh vô tình cache một danh sách đã lọc theo request A rồi trả cho request B có context khác.

Trong lúc chẩn đoán, nếu final list rỗng mà discovery đã có A/B, hãy thử kiểm tra lại sau TTL hoặc dùng test no-cache để xác định liệu cache có phải điểm khác biệt.

## 9. Tầng health: probe fail không nhất thiết đồng nghĩa danh sách rỗng

`HealthCheckServiceInstanceListSupplier` định kỳ thăm dò endpoint health rồi tạo danh sách các instance được xem là alive. Nó đặc biệt hữu ích khi `SimpleDiscoveryClient` chỉ có địa chỉ tĩnh. Nhưng các lỗi health thường làm người vận hành nhầm:

- Backend nghiệp vụ phản hồi HTTP 200 tại `/api/items`, nhưng `/actuator/health` trả 404 vì chưa cài Actuator.
- Endpoint health chạy ở management port khác với service port mà LoadBalancer đang dùng.
- Spring Security chặn health endpoint (401/403) hoặc TLS certificate/truststore chưa đúng.
- Health path của từng service ID khác nhau.
- Probe timeout dù business endpoint vẫn có thể trả response (hoặc ngược lại).
- Thời gian startup/chạy probe/refetch khiến dữ liệu health chưa ổn định.
- Health supplier không được bật nhưng đội ngũ tưởng đã bật chỉ vì cấu hình properties.

### Kiểm tra endpoint từ vị trí caller

Ví dụ inventory A/B là localhost trong lab:

~~~powershell
Invoke-WebRequest "http://localhost:8081/actuator/health"
Invoke-WebRequest "http://localhost:8082/actuator/health"
~~~

Trong môi trường container/Kubernetes, `localhost` của caller là **caller container**, không phải backend. Phải dùng host/port/thông tin đã được discovery trả về, từ đúng network namespace của caller.

Cấu hình tham khảo:

~~~yaml
spring:
  cloud:
    loadbalancer:
      health-check:
        initial-delay: 0
        interval: 25s
        path:
          default: /actuator/health
          inventory-service: /actuator/health
~~~

Trong các bản Spring Cloud được tài liệu mô tả, default path là `/actuator/health`, `initial-delay` mặc định `0` và `interval` mặc định `25s`. `initial-delay/interval` là lịch probe, **không phải** connect/read timeout của lời gọi nghiệp vụ.

Nếu Actuator không có, có thể dùng endpoint readiness riêng được kiểm soát. Nếu management chạy trên port khác, kiểm tra `spring.cloud.loadbalancer.health-check.port` và cách port ấy áp dụng cho các instances; một port chung có thể không phù hợp khi backend dùng cổng quản trị khác nhau.

### Cấu hình supplier đúng tầng

Reactive app / WebClient:

~~~java
return ServiceInstanceListSupplier.builder()
        .withDiscoveryClient()
        .withHealthChecks()
        .build(context);
~~~

Blocking app / RestClient:

~~~java
return ServiceInstanceListSupplier.builder()
        .withDiscoveryClient()
        .withBlockingHealthChecks()
        .build(context);
~~~

Spring Cloud lưu ý health supplier có replay/caching riêng; không tùy tiện chồng thêm `withCaching()` khi chưa hiểu thứ tự và cập nhật snapshot. Health check nên đứng ngay sau nguồn discovery và trước các filter theo request.

### Nếu tất cả health probes thất bại thì sao?

**Không đoán kết quả từ tên “HealthCheck”.** Tài liệu Spring Cloud Commons cho các bản ổn định được tham khảo (chẳng hạn 4.3 và 5.0/5.1) mô tả hành vi: nếu không còn instance healthy, health supplier có thể **trả lại toàn bộ danh sách đã truy xuất** để giữ availability (*fail-open*). Nhưng source/nhánh phát triển và custom implementation có thể có chính sách khác, bao gồm trả danh sách rỗng (*fail-closed*). Hãy xác minh **release train và implementation đang chạy**.

Vì vậy:

- Nếu raw discovery đã là `[]`, health supplier không thể “cứu” bằng việc tự tạo instance.
- Nếu raw discovery có A/B nhưng tất cả probes fail, **không mặc định** điều đó sẽ dẫn tới no-instance; một số phiên bản trả lại A/B và sau đó caller có thể gặp connect/read failure.
- Nếu một custom strict health filter trả `[]`, nó có thể chính là tầng làm rỗng candidate set.
- Nếu health list bị stale, xem cơ chế replay/refetch, không chỉ giảm interval bừa bãi.

### Refetch instances khác với lặp probes

Các thuộc tính có thể hữu ích:

~~~yaml
spring:
  cloud:
    loadbalancer:
      health-check:
        refetch-instances: true
        refetch-instances-interval: 25s
        repeat-health-check: true
        update-results-list: true
~~~

`refetch-instances` chủ động lấy lại **danh sách instance**, trong khi `repeat-health-check` kiểm tra lại tình trạng health. `update-results-list` ảnh hưởng cách kết quả được phát; chúng không phải HTTP timeout.

Đừng bật refetch liên tục trong production chỉ để che một registry đang cấu hình sai. Khi discovery provider cập nhật list tự nhiên, có thể không cần tự refetch; hãy đo actual event flow.

## 10. Tầng zone: ưu tiên mềm, không phải hard filter mặc định

`ZonePreferenceServiceInstanceListSupplier` so `spring.cloud.loadbalancer.zone` (zone của caller) với metadata key `zone` trên từng `ServiceInstance`.

Ví dụ:

~~~text
Discovery: [A(zone=hcm), B(zone=hn)]
Caller zone=hcm
After zone preference: [A]
~~~

Nếu caller zone sai hoặc **không có instance nào cùng zone**:

~~~text
Discovery: [A(hcm), B(hn)]
Caller zone=unknown-zone
After ZonePreference: [A, B] (fallback)
~~~

Theo tài liệu Spring Cloud, `ZonePreferenceServiceInstanceListSupplier` **trả lại toàn bộ danh sách delegate** nếu zone là null/không có match. Vì vậy, một lỗi no-instance khi raw discovery có A/B **thường không xuất phát từ riêng ZonePreference mặc định**; cần xem custom filter, filter khác sau zone hoặc trạng thái list delegate đã rỗng.

### Checklist zone

- Caller có đúng `spring.cloud.loadbalancer.zone` không?
- Metadata mỗi instance có key **`zone`** đúng chữ/giá trị không?
- `ZonePreferenceServiceInstanceListSupplier` có thực sự được bật không, hay chỉ đặt property?
- Nếu policy là **hard isolation** theo khu vực, có custom filter nào chủ động trả `[]` khi không có match?
- Nếu zone list rỗng sau một strict filter, nó có báo no-instance thay vì lén chọn cross-zone?

Đừng “sửa” lỗi bằng cách tắt hard zone filter khi nó bảo vệ data residency hoặc an ninh. Khi đó đúng hành vi là trả lỗi có kiểm soát, đồng thời mở rộng capacity cùng zone hoặc sửa registry metadata.

## 11. Tầng hint: xem cả header và Request context

`HintBasedServiceInstanceListSupplier` tìm giá trị hint trong request header, mặc định `X-SC-LB-Hint`, hoặc hint cấu hình trong properties khi request không mang hint. Nó lọc theo metadata key `hint`.

~~~text
Discovery: [A(hint=blue), B(hint=green)]
Request header: X-SC-LB-Hint: blue
After HintBased: [A]
~~~

Nếu hint unknown:

~~~text
Discovery: [A(blue), B(green)]
X-SC-LB-Hint: unknown
After HintBased: [A, B] (fallback mặc định)
~~~

**Không phải mọi missing hint sẽ gây `EmptyResponse`.** Supplier hint mặc định trả lại delegate list nếu không có hint hoặc không tìm thấy matching instance. Lỗi no-instance sau hint thường cần kiểm tra list đã rỗng ở delegate hoặc một custom **strict hint filter**.

### Hai câu hỏi rất dễ bỏ sót

1. HTTP client đã gửi header chưa?
2. `ServiceInstanceListSupplier.get(request)` **có thực sự nhận hint context** chưa?

Backend nhìn thấy header không tự chứng minh supplier đã lọc theo hint: đó là hai thời điểm khác nhau. Với WebClient, RestClient và OpenFeign, cách context được chuyển vào LoadBalancer có thể khác nhau giữa transport/release train.

Cấu hình minh họa:

~~~yaml
spring:
  cloud:
    loadbalancer:
      hint-header-name: X-SC-LB-Hint
      hint:
        default: blue
~~~

Trong bài kiểm tra “không hint”, đừng quên `hint.default` vẫn có thể ảnh hưởng policy. Để cô lập, thử request không có header/default rồi so với request có `X-SC-LB-Hint` được cung cấp từ nguồn tin cậy.

**Bảo mật:** hint không phải quyền truy cập. Không truyền nguyên xi user-controlled header để chọn nhóm dữ liệu nhạy cảm hoặc một version không đủ quyền.

## 12. Version filter và custom hard filter có thể làm rỗng list thật sự

Đây là chỗ dễ bị bỏ sót khi raw discovery vẫn có instances, zone/hint đều fallback, nhưng LoadBalancer cuối cùng không tìm được server.

Một số Spring Cloud release train cung cấp `BlockingApiVersionServiceInstanceListSupplier` và `ReactiveApiVersionServiceInstanceListSupplier`. Theo tài liệu, khi đã xác định API version nhưng **không có instance khớp**, supplier **trả danh sách rỗng** theo mặc định; có tùy chọn fallback to available instances nếu policy cho phép.

Ví dụ:

~~~text
Discovery: [A(version=1), B(version=1)]
Caller yêu cầu: API version=2
Version filtering: []
LoadBalancer: EmptyResponse
HTTP client: không gửi attempt tới A/B
~~~

Đây có thể là **hành vi đúng** nếu version 2 không tương thích version 1. Bật fallback bừa bãi có thể khiến caller nhận JSON sai schema hoặc ghi dữ liệu sai.

Các câu hỏi bắt buộc:

- API version thực sự được lấy từ header/query/path/media type nào?
- Có default version trong config không?
- Metadata instance có key version đúng theo supplier/release train chưa?
- Có version filter **custom** hoặc feature flag route cứng theo canary không?
- Có policy `fallback-to-available-instances` không, và có được phép dùng?
- Khi no match, code trả `EmptyResponse` có kiểm soát hay ném exception bất ngờ?

### Ví dụ một custom filter nghiêm ngặt

Pseudo-code:

~~~text
request = {requiredVersion: "v2"}
candidates = discoverySupplier.get(request)

eligible = candidates.filter(
    instance -> instance.metadata["version"] == request.requiredVersion
)

if eligible.isEmpty():
    return []  // Không tự fallback qua version khác.

return eligible
~~~

Một custom filter có thể **đúng theo security/business contract** khi trả empty. Trong trường hợp này, mục tiêu chẩn đoán là tìm **vì sao không có eligible candidates**, không phải “cố bắt LoadBalancer luôn chọn một server”.

## 13. Trọng số, subset, sticky và retry: đừng đánh đồng tác dụng

Một số supplier/policy khác cũng làm thay đổi tập ứng viên hoặc thứ tự ưu tiên:

| Policy | Tác động chính | Điều cần kiểm tra khi no-instance |
|---|---|---|
| `WeightedServiceInstanceListSupplier` | Thay tỷ trọng lựa chọn dựa metadata `weight` | List delegate có rỗng không? WeightFunction có lỗi/số không hợp lệ không? |
| Subset supplier | Lấy tập con từ danh sách lớn | Input subset có rỗng, có quá ít instance, subset size/config phù hợp không? |
| Same-instance preference | Ưu tiên instance được chọn trước đó | Instance trước đó có còn trong candidates không? Fallback semantics ra sao? |
| Request-based sticky session | Ưu tiên theo cookie/context | Cookie trỏ tới instance đã mất, supplier có fallback không? |
| Retry-aware supplier | Ưu tiên tránh instance vừa thất bại | Nếu chỉ còn một instance, policy có cho phép thử lại không? |
| Custom zone/version/tenant filter | Giới hạn eligibility | Có lọc hết do metadata thiếu, sai key, sai case hoặc không có quyền? |

`WeightedServiceInstanceListSupplier` theo tài liệu mặc định đọc metadata `weight`; nếu thiếu dùng weight 1. Không suy ra `weight: 0` mặc nhiên đồng nghĩa instance bị xóa khỏi discovery. Tương tự, retry-aware supplier có thể thay đổi danh sách cho một attempt mới, không tạo ra một instance mới từ hư không.

Nếu custom picker thấy candidates không rỗng nhưng vẫn trả no-server, kiểm tra nhánh `choose()` và data race, không đổ lỗi cho weight/hint trước khi nhìn code.

## 14. Xác minh thứ tự cấu hình supplier

Với cấu hình tùy biến theo `inventory-service`:

~~~java
package com.example.order.config;

import org.springframework.cloud.loadbalancer.annotation.LoadBalancerClient;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@LoadBalancerClient(
        name = "inventory-service",
        configuration = InventoryLoadBalancerConfiguration.class
)
public class InventoryLoadBalancerRegistration {
}
~~~

Và class cấu hình supplier đặt **ngoài component scan của ứng dụng**:

~~~java
package com.example.lb;

import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.cloud.loadbalancer.core.ServiceInstanceListSupplier;

public class InventoryLoadBalancerConfiguration {

    @Bean
    ServiceInstanceListSupplier inventorySupplier(
            ConfigurableApplicationContext context) {

        return ServiceInstanceListSupplier.builder()
                .withDiscoveryClient()
                .withCaching()
                .withZonePreference()
                .withHints()
                .build(context);
    }
}
~~~

Lưu ý:

- `@LoadBalancerClient` định nghĩa cấu hình trong **child ApplicationContext theo service ID**.
- Đừng vô tình để `InventoryLoadBalancerConfiguration` bị component scan thành config **global**; nó có thể thay đổi supplier của service ID khác.
- `withDiscoveryClient()` phải lấy đúng nguồn. Nếu đang dùng reactive discovery, hãy chọn builder/provider phù hợp với release train.
- `withCaching()`/`withHealthChecks()` nên trực tiếp theo sau retrieval và **trước** request-aware filter.
- Khi thêm health, có thể dùng `.withDiscoveryClient().withHealthChecks().withZonePreference().withHints()` cho reactive; với blocking cần `withBlockingHealthChecks()`.
- Không đăng ký thêm một supplier khác cùng service ID mà không biết bean nào được client context thực sự chọn.
- Nếu có nhiều decorators custom, ghi rõ thứ tự và kết quả khi input empty/error.

### Cách cô lập mà không phá production

Trong profile kiểm thử riêng, có thể **tạm cấu hình** chuỗi supplier tăng dần:

~~~text
Test 1: Discovery
Test 2: Discovery -> Cache
Test 3: Discovery -> Cache -> Zone
Test 4: Discovery -> Cache -> Zone -> Hint
Test 5: Discovery -> Cache -> Zone -> Hint -> Version/custom
~~~

Với **cùng service ID, cùng snapshot, cùng request context**, lấy độ dài kết quả ở mỗi bước. Tầng nào chuyển từ `size>0` sang `size=0` chính là nơi cần đọc contract/metadata/config sâu hơn.

Không yêu cầu bật những mode test bằng cách sửa config production đang phục vụ traffic; dùng test context, profile local/staging hoặc component test có supplier giả.

## 15. Một list không rỗng vẫn có thể bị custom chooser trả EmptyResponse

Sau `ServiceInstanceListSupplier`, `ReactorServiceInstanceLoadBalancer.choose(Request)` sẽ chọn server.

Một custom chooser có thể sai ở các tình huống:

- Tính `index % candidates.size()` khi list rỗng và ném exception thay vì trả `EmptyResponse`.
- Đọc candidates từ nguồn riêng hoặc cache cũ, không dùng list supplier đã inject.
- Có điều kiện `if (requestContext == null) return new EmptyResponse()` quá nghiêm ngặt.
- Yêu cầu metadata chưa tồn tại và trả empty cho mọi instance.
- Quản lý index không thread-safe hoặc giữ index từ snapshot size cũ.
- Dùng `Mono.empty()` thay vì phát `Response<ServiceInstance>` có `hasServer=false`, khiến phía gọi xử lý khác dự kiến.
- Không gọi `ServiceInstanceListSupplier.get(request)` nên bỏ qua thông tin hint/version/retry, rồi lọc sai.

Một nhánh xử lý no-instance tối thiểu:

~~~java
import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.loadbalancer.DefaultResponse;
import org.springframework.cloud.client.loadbalancer.EmptyResponse;
import org.springframework.cloud.client.loadbalancer.Response;

Response<ServiceInstance> chooseFrom(
        java.util.List<ServiceInstance> candidates) {

    if (candidates == null || candidates.isEmpty()) {
        return new EmptyResponse();
    }

    return new DefaultResponse(candidates.get(0));
}
~~~

Đây chỉ là **helper minh họa**, không phải thuật toán production. Nó luôn chọn phần tử đầu tiên nên có nguy cơ làm traffic mất cân bằng. Nó thể hiện contract rằng `EmptyResponse` phù hợp khi thực sự không có candidate; không đưa `new DefaultResponse(null)` để “có response”.

Một chooser có thể hợp lệ khi từ chối một subset vì điều kiện cứng (version, tenant), nhưng phải **đưa nguyên nhân** vào metrics/log/test để phân biệt “không có instance trong registry” với “không có instance được phép phục vụ”.

## 16. “Raw discovery có nhưng final list rỗng”: bảng tìm đúng tầng

| Raw discovery | Cache/health | Zone/hint | Version/custom | Chẩn đoán ưu tiên |
|---|---|---|---|---|
| `[]` | `[]` | `[]` | `[]` | Sai service ID, registry, discovery client hoặc registration |
| `[A,B]` | `[]` | `[]` | `[]` | Cache stale hoặc health/custom strict filter; xác minh implementation |
| `[A,B]` | `[A,B]` | `[A]` | `[A]` | Zone/hint ưu tiên bình thường, lỗi có thể nằm sau selection |
| `[A,B]` | `[A,B]` | `[A,B]` | `[]` | Version/custom hard filter loại hết candidates |
| `[A,B]` | `[A,B]` | `[A,B]` | `[A,B]` | Nếu chooser empty: điều tra custom chooser/Request context |
| `[A,B]` | `[A,B]` | `[A,B]` | `[A]` | Chọn A được, HTTP failure là vấn đề network/backend |

Bảng là **mẫu chẩn đoán**, không khẳng định mọi supplier đều luôn chạy theo các cột này. Dữ liệu quan sát phải đến từ cùng caller và cùng request context hoặc được ghi rõ khác biệt.

### Quy tắc khi các nguồn quan sát mâu thuẫn

Nếu registry UI hiện hai instance nhưng diagnostic probe thấy 0:

- Có thể caller trỏ registry/namespace khác.
- UI cache chưa refresh.
- Service ID sai hoặc đăng ký với tên khác.
- Composite DiscoveryClient có thứ tự hoặc behavior khác.
- Caller không có credentials/TLS để truy vấn registry.
- Profile/override properties làm nguồn discovery thay đổi.

Nếu probe raw thấy hai nhưng final chỉ còn một:

- Một filter hoạt động, có thể hoàn toàn đúng.
- Nhìn **metadata** và policy của filter, không lập tức tắt nó.

Nếu raw và final đều có hai mà HTTP 503:

- Xem `choose().hasServer()`, đường kết nối host/port và **nguồn sinh HTTP 503**.
- Không kết luận 503 do LoadBalancer chỉ từ status code.

## 17. Vì sao một loạt request 503 có thể xuất hiện dù ứng dụng khởi động “UP”?

`/actuator/health` của **caller** phản ánh chính sách health indicator của caller. Nó không bảo đảm rằng `inventory-service` đang có ít nhất một instance đủ điều kiện cho **từng request**.

Ví dụ:

~~~text
order-service process: UP
  - datasource UP
  - local web server UP
  - discovery client bean UP

inventory-service:
  - raw discovery []
  - no eligible instances
  - /api/orders -> 503 từ client-side routing
~~~

Tương tự, health endpoint của inventory là một tín hiệu sống của **backend**, không khẳng định caller đã đăng ký đúng instance, TTL hết hạn, zone/hint match hoặc version filter cho phép.

Không sửa liveness/readiness của caller bằng cách ép nó DOWN chỉ vì một optional dependency tạm thời hết instance: điều này có thể tạo vòng restart và tăng tải. Nếu dependency bắt buộc cho một API, hãy thể hiện degraded status/SLO hoặc business error theo policy ứng dụng; health groups phải cân bằng ý nghĩa “có thể phục vụ” với nguy cơ cascading restarts.


## 18. Bật logging chẩn đoán theo thời gian có giới hạn

Khi ứng dụng vẫn chạy nhưng một service ID thường xuyên báo no-server, có thể tăng log level **tạm thời** ở môi trường thử nghiệm hoặc qua cơ chế quản lý runtime được kiểm soát.

~~~yaml
logging:
  level:
    org.springframework.cloud.loadbalancer: DEBUG
    org.springframework.cloud.client.loadbalancer: DEBUG
    org.springframework.cloud.client.discovery: DEBUG
~~~

Những logger trên là **gợi ý phạm vi package**, không cam kết mọi release train đều in cùng một chuỗi thông báo. Tuỳ implementation và lớp mã, cần kiểm tra log thực tế.

Trình tự đọc logs:

1. Xác định **caller instance**, timestamp, trace/correlation ID và service ID bị gọi.
2. Xem có thông báo lựa chọn no-server/empty candidates không.
3. Kiểm tra cảnh báo từ registry client: không truy vấn được, lease stale, đăng ký sai hoặc thiếu quyền.
4. Kiểm tra các filter logs nếu custom code có instrumentation.
5. Ghi lại exception type và HTTP status **ở client adapter**, không chỉ message của controller/gateway.
6. Sau khi lấy đủ thông tin, trả logger về INFO để tránh log volume lớn và chi phí tăng.

Không log bearer token, cookie, địa chỉ nội bộ nhạy cảm trên hệ thống công khai, payload chứa PII hoặc toàn bộ metadata của registry. Với một HTTP request thất bại, trace ID có thể được dùng trong logs có kiểm soát; không đưa trace ID vào metric labels.

### Cách ghi log candidate counts tại đúng tầng

Khi xây custom supplier, có thể log dữ liệu **đã được giới hạn** như:

~~~text
serviceId=inventory-service
supplierStage=discovery  candidates=3
supplierStage=health     candidates=2
supplierStage=zone      candidates=2
supplierStage=version   candidates=0
outcome=no_server
~~~

Tất cả counts cần đến từ **cùng lần đánh giá request context**. Không ghép một cache snapshot của 10 giây trước với một discovery list vừa đọc rồi coi đó là bằng chứng tuyệt đối.

Không log một bản sao list quá lớn trên mỗi request. Trong production, ưu tiên metrics tổng hợp và sampled debug traces; nếu cần danh sách instance IDs cụ thể, chỉ bật trong thời gian ngắn với quyền truy cập phù hợp.

## 19. Dùng Micrometer phân biệt no-instance với HTTP attempt lỗi

Spring Cloud LoadBalancer có `MicrometerStatsLoadBalancerLifecycle` khi có `MeterRegistry` và cấu hình thích hợp. Với Spring Boot Actuator, ví dụ:

~~~yaml
spring:
  cloud:
    loadbalancer:
      stats:
        micrometer:
          enabled: true
        include-path: false

management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics
~~~

Các meter được tài liệu Spring Cloud mô tả gồm:

| Meter | Diễn giải | Hữu ích khi |
|---|---|---|
| `loadbalancer.requests.discard` | Request không lấy được service instance để chuyển tiếp | Nghi ngờ final candidates rỗng/no-server |
| `loadbalancer.requests.failed` | Request load-balanced kết thúc bằng exception | Transport/caller có lỗi thực thi |
| `loadbalancer.requests.success` | Timer khi load-balanced request đã chuyển response | Xem có response, **không mặc định HTTP business success** |
| `loadbalancer.requests.active` | Gauge requests đang được xử lý | Xác định áp lực/in-flight |

Một request có response HTTP 503 từ backend **không nhất thiết** được tính giống một request `EmptyResponse`. Hãy đối chiếu cả HTTP client metrics, backend access log và loại exception.

### Truy vấn metrics bằng PowerShell

Sau khi có traffic và Actuator được bật:

~~~powershell
Invoke-RestMethod "http://localhost:8080/actuator/metrics"
Invoke-RestMethod "http://localhost:8080/actuator/metrics/loadbalancer.requests.discard"
Invoke-RestMethod "http://localhost:8080/actuator/metrics/loadbalancer.requests.failed"
~~~

Meter chỉ được tạo khi có record; endpoint trả 404 cho một meter chưa xuất hiện **không chứng minh** rằng không có lỗi. Kiểm tra dependency `spring-boot-starter-actuator`, `MeterRegistry`, toggle metrics và traffic đã chạy.

Cần cảnh báo theo các chiều:

- No-instance/discard rate theo service ID và caller replica.
- Failure/connect timeout rate so với no-instance rate.
- Số lượng instance được discovery trả về và số cuối sau filter (nếu ứng dụng có custom metric).
- Thời gian kể từ lần registry refresh/candidate update cuối.
- Tỷ lệ fallback, retry attempts và circuit breaker OPEN.
- HTTP status 503/504 **từ nguồn nào**: LoadBalancer, gateway hay backend.

Với histogram labels, giới hạn cardinality của tag. `spring.cloud.loadbalancer.stats.include-path=false` có thể giảm nguy cơ tag theo path động.

## 20. Lab tái hiện: caller có hai backend nhưng không chọn được server

Ở mục 6, ta đã có discovery tĩnh cho A:8081 và B:8082. Bổ sung caller endpoint để tạo request qua service ID.

### Caller REST endpoint để thử selection

Giả sử `inventoryRestClient` được cấu hình ở mục 4. Ví dụ controller:

~~~java
package com.example.order.web;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.client.RestClient;

@RestController
public class ProxyController {

    private final RestClient inventoryClient;

    public ProxyController(
            @Qualifier("inventoryRestClient") RestClient inventoryClient) {
        this.inventoryClient = inventoryClient;
    }

    @GetMapping("/proxy/whoami")
    public InstanceView whoami() {
        return inventoryClient.get()
                .uri("/whoami")
                .retrieve()
                .body(InstanceView.class);
    }

    public record InstanceView(String instance, String service) {}
}
~~~

Mã minh họa: cần khai báo đúng Spring Boot Web/LoadBalancer starters, cấu hình REST client và exception handler của dự án. Nếu network error xảy ra, controller có thể trả 500 trừ khi adapter xử lý exception; hãy **đọc exception gốc** thay vì suy từ HTTP status phía ngoài.

Gửi nhiều request:

~~~powershell
1..6 | ForEach-Object {
    try {
        Invoke-RestMethod "http://localhost:8080/proxy/whoami"
    }
    catch {
        Write-Host ("HTTP call failed: " + $_.Exception.Message)
    }
}
~~~

Khi cả hai backend chạy, expected: response có `instance=8081` hoặc `instance=8082` và không có no-server. Không bắt buộc thứ tự replica cố định nếu có concurrent traffic/cursor khác.

### Kịch bản A — Sai service ID

Trong **lab riêng**, thay base URL caller thành `http://inventroy-service` (đảo ký tự), nhưng YAML discovery vẫn đăng ký `inventory-service`.

~~~text
DiscoveryClient.getInstances("inventory-service") -> [A, B]
DiscoveryClient.getInstances("inventroy-service") -> []
LoadBalancer request service ID             -> inventroy-service
Result                                      -> no server
~~~

Bài học: luôn truy vấn **đúng service ID mà URI/Feign thực sự dùng**, không chỉ tên mong muốn trong tài liệu. Khôi phục đúng base URL sau khi test.

### Kịch bản B — Không có instance trong SimpleDiscoveryClient

Trong profile lab, bỏ hai `uri` của service ID `inventory-service` khỏi cấu hình caller (hoặc dùng một profile YAML chỉ chứa empty list). Khởi động lại caller.

Kỳ vọng:

~~~text
raw discovery:   []
final supplier:  []
LoadBalancer:    EmptyResponse
HTTP backend:    không nhận request
~~~

Đây là ví dụ điển hình no-instance **tại nguồn**.

### Kịch bản C — Có instance nhưng backend dừng

Khôi phục YAML [A, B], chạy caller, **dừng tiến trình 8082** và giữ 8081 hoạt động.

~~~text
raw discovery:   [A, B]  (SimpleDiscoveryClient tĩnh)
final supplier:  [A, B]  (không bật health filter)
LoadBalancer:    có thể chọn A hoặc B
Nếu chọn B:      connection refused/timeout
~~~

Đây **không phải** no-instance do list rỗng. Việc tăng cache TTL, đổi zone hay tắt retry không làm 8082 tự sống lại. Khắc phục bằng discovery deregistration/health policy, sửa backend hoặc retry có giới hạn nếu nghiệp vụ phù hợp.

### Kịch bản D — Strict version filter loại hết list

Tạo một **test-only** `ServiceInstanceListSupplier` hoặc adapter minh họa lọc metadata `api-version`:

~~~text
raw discovery:
  A(metadata api-version=v1)
  B(metadata api-version=v1)

request requires: v2

strict filter:
  [A, B] -> []

choose:
  EmptyResponse

transport:
  no HTTP attempt
~~~

Kịch bản này thể hiện chính xác lỗi “discovery có hai instance nhưng không có **instance khả dụng theo policy**”. Khi version v2 là hard requirement, kết quả no-server có thể là **đúng hợp đồng**. Sửa bằng cách triển khai instance v2 hoặc thay đổi yêu cầu caller **được phê duyệt**, không tự fallback về v1.

### Kịch bản E — Cấu hình zone/hint nhưng tưởng là hard filter

Với A metadata zone hcm/hint blue, B zone hn/hint green, bật `ZonePreferenceServiceInstanceListSupplier` và `HintBasedServiceInstanceListSupplier` mặc định.

- Caller zone hcm, hint blue: sau zone+hint có thể chỉ còn A.
- Caller zone unknown: zone supplier fallback thành A/B.
- Hint không tồn tại: hint supplier fallback về input của nó (A/B hoặc A tuỳ kết quả zone trước).
- Nếu bạn **muốn** no-server khi zone/hint không khớp, cần **custom hard policy**; built-in preference mặc định có thể không cho kết quả đó.

**Mục tiêu của bài test:** xác minh không đánh đồng “filter không match” với “filter chắc chắn trả list rỗng”.

## 21. Kiểm thử hồi quy ba tầng

### 21.1. Unit test điều kiện rỗng ở bộ chọn

Một hàm chọn phải xử lý empty input theo contract:

~~~java
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.cloud.client.DefaultServiceInstance;
import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.loadbalancer.EmptyResponse;
import org.springframework.cloud.client.loadbalancer.DefaultResponse;
import org.springframework.cloud.client.loadbalancer.Response;

class SelectionContractTest {

    Response<ServiceInstance> select(
            List<ServiceInstance> candidates) {

        if (candidates.isEmpty()) {
            return new EmptyResponse();
        }

        return new DefaultResponse(candidates.get(0));
    }

    @Test
    void returnsNoServerWhenCandidatesEmpty() {
        assertFalse(select(List.of()).hasServer());
    }

    @Test
    void returnsServerWhenAnyCandidateExists() {
        ServiceInstance a = new DefaultServiceInstance(
                "a", "inventory-service", "localhost", 8081, false
        );

        assertTrue(select(List.of(a)).hasServer());
    }
}
~~~

Hàm minh họa cố ý chọn phần tử đầu tiên để tập trung vào contract empty/nonempty; **không dùng làm thuật toán cân bằng tải production**.

### 21.2. Component test cho supplier chain

Với fake discovery list A/B, kiểm tra ít nhất:

| Test case | Input | Kết quả kỳ vọng |
|---|---|---|
| Empty discovery | `[]` | Final list `[]`, chooser no-server |
| Valid list | `[A,B]` | Final list giữ candidates hoặc lọc theo policy |
| Zone hcm | A(hcm), B(hn) | ZonePreference chọn A |
| Zone unknown | A(hcm), B(hn) | ZonePreference fallback A/B |
| Hint blue | A(blue), B(green) | HintBased chọn A khi request context đúng |
| Hint unknown | A/B | HintBased fallback delegate |
| Strict version v2 | A/B đều v1 | Empty list (fail-closed policy) |
| One unhealthy | A unhealthy, B healthy | Health filter chọn theo policy/release train |
| Both unhealthy | A/B unhealthy | **Kiểm tra actual behavior theo release train**, không assume |
| Cache stale | Registry đổi sau snapshot | Kết quả trước/sau refresh đúng cơ chế |
| Discovery error | Supplier upstream ném error | Không biến lỗi thành success instance giả |
| Request-aware supplier | Hint/version trong `Request` | Không rơi mất context khi gọi `get(request)` |

Nếu dùng Reactor Test, `StepVerifier` có thể assert `Flux<List<ServiceInstance>>` hoặc `Mono<Response<ServiceInstance>>`. Thời gian của health scheduler nên được kiểm soát trong test để tránh flaky assertions.

### 21.3. Integration test qua HTTP client thật

Tái hiện cùng một service ID qua:

- **RestClient:** builder `@LoadBalanced`, xem empty/no-server và connect refused có exception khác nhau không.
- **WebClient:** kiểm tra subscription, request context, `StepVerifier` và reactive error/fallback.
- **OpenFeign:** `@FeignClient(name=...)` không URL tĩnh; verify integration và exception class thực tế.
- **Gateway/proxy:** phân biệt HTTP 503 do no-instance từ client-side và HTTP 503 do backend.
- **Retry:** đảm bảo no-instance không tạo vòng retry vô hạn; nếu có một instance khỏe, retry vẫn nằm trong timeout/deadline tổng.

Trong test, ghi lại số lần backend thực sự nhận request. Khi no-server trước network, backend access logs **không có attempt mới**. Đây là một bằng chứng hữu ích để phân biệt với việc đã gửi request tới instance nhưng backend trả 503.

## 22. Lựa chọn biện pháp khắc phục theo đúng nguyên nhân

| Nguyên nhân gốc | Biện pháp đúng | Biện pháp dễ gây hại |
|---|---|---|
| Sai service ID | Sửa tên trong URI/`@FeignClient(name)`, registry metadata | Hardcode IP của backend |
| Chưa đăng ký instance | Khôi phục registration/lease, namespace, client credentials | Bật retry vô hạn ở caller |
| Discovery client lỗi | Sửa registry endpoint/TLS/network, quan sát error | Tắt toàn bộ validation/SSL |
| Cache rỗng stale | Chỉnh TTL/refresh/invalidation theo thiết kế | Tắt caching trên production tải cao không đo |
| Health probe sai path/port | Sửa actuator/management path, port, TLS, security | Ép mọi instance “healthy” mà không kiểm chứng |
| All-unhealthy behavior khác kỳ vọng | Xác minh implementation/release train, thiết kế fail policy | Suy rằng health luôn fail closed |
| Zone/hint mismatch | Sửa metadata/request context, kiểm chứng fallback mềm | Tắt hard isolation bắt buộc |
| API version strict filter | Đăng ký instance đúng version hoặc fail fast | Fallback version không tương thích |
| Custom supplier filter sai | Viết test, sửa predicate, log candidate counts | Trả toàn bộ list bỏ qua security policy |
| Custom chooser trả empty | Sửa contract và unit/concurrency test | Trả `DefaultResponse(null)` |
| Có server nhưng connection refused | Sửa host/port/network và deregistration | Tiếp tục truy lỗi “no instance” |
| Circuit breaker OPEN | Quan sát dependency failure/threshold/recovery | Tăng LoadBalancer TTL để “mở circuit” |
| HTTP 503 backend | Đọc backend access logs, capacity, health, overload | Gắn nhãn là registry rỗng chỉ dựa status |

**Recovery tốt** cần nhìn thấy cả thay đổi hạ tầng lẫn khôi phục request path: registry có lại instance, supplier thấy ứng viên phù hợp, chooser trả `hasServer=true`, HTTP attempt đến backend và response đáp ứng SLO.

Không dùng các thay đổi khẩn cấp như vô hiệu hóa version/zone hard filter nếu chúng bảo vệ phân quyền hoặc vùng lưu trữ dữ liệu. Với lỗi no-instance hợp lệ theo policy, ứng dụng cần trả lỗi có cấu trúc và retry/backoff giới hạn thay vì gửi sang backend không được phép.

## 23. Runbook xử lý trong một ca sự cố

Có thể dùng trình tự sau khi nhận cảnh báo liên quan `inventory-service`:

~~~text
[1] Khoanh request lỗi
    caller instance, timestamp, traceId, serviceId,
    status, exception class, logical request vs attempt

[2] Xác nhận tích hợp client
    RestClient/WebClient @LoadBalanced?
    Feign name/url?
    Có gọi đúng service ID hay DNS/static URL?

[3] Hỏi nguồn discovery từ chính caller
    getInstances(serviceId) hoặc reactive counterpart
    Nếu [] -> registry/registration/profile/namespace

[4] Hỏi final supplier theo request context
    Nếu [] nhưng raw != []:
      cache -> health -> zone -> hint -> version/custom

[5] Nếu final != [] mà choose no-server:
    custom chooser / response wrapper / concurrency

[6] Nếu choose có server:
    host:port / connect / TLS / timeout / backend 503

[7] Khắc phục nguyên nhân, không bỏ security policy
    theo dõi refresh, recovery và counters

[8] Đóng ca bằng kiểm thử hồi quy
    test empty, stale, no-match và healthy behavior
~~~

### Đầu ra tối thiểu của báo cáo sự cố

| Trường | Ví dụ minh họa |
|---|---|
| Sự kiện | `inventory-service` không có eligible instances |
| Khoảng thời gian | 14:05–14:12 UTC+7 (ví dụ) |
| Caller replica | `order-2` |
| Service ID | `inventory-service` |
| Raw discovery | 2 instances |
| Final supplier | 0 instances |
| Tầng làm rỗng | Strict version filter yêu cầu v2 |
| HTTP attempt | 0 cho requests bị từ chối |
| Trạng thái backend | Hai replica đều đăng ký v1 |
| Biện pháp | Triển khai v2/cập nhật policy theo kế hoạch |
| Kiểm chứng | Final supplier >0, `hasServer=true`, HTTP SLO đạt |
| Phòng ngừa | Contract test khi rollout API version, alert no-instance |

Đây là **báo cáo mẫu**, không phải kết quả điều tra thực tế của hệ thống nào.

## 24. Checklist trước khi kết luận lỗi đã được sửa

- [ ] Đã xác định chính xác service ID từ URL logic/Feign name.
- [ ] Đã phân biệt no-server, `UnknownHostException`, connect refused, timeout và backend 503.
- [ ] Đã kiểm tra `DiscoveryClient`/`ReactiveDiscoveryClient` từ caller bị ảnh hưởng.
- [ ] Registry/provider đúng namespace, môi trường và trạng thái registration.
- [ ] Đã so raw discovery list với final `ServiceInstanceListSupplier` list.
- [ ] Đã tính đến cache TTL và cache ở nhiều tầng trước khi so thời điểm.
- [ ] Đã kiểm chứng health path, port, security/TLS, schedule và refetch.
- [ ] Đã kiểm chứng fallback all-unhealthy theo version đang chạy.
- [ ] Đã kiểm tra `spring.cloud.loadbalancer.zone` và metadata `zone`.
- [ ] Đã kiểm tra hint header/property, metadata `hint` và `Request` context.
- [ ] Đã kiểm tra API version filter và custom hard filters.
- [ ] Không tắt filter bắt buộc về tenant, version hoặc data residency để “chữa” 503.
- [ ] `@LoadBalancerClient` config đúng child context/service ID, không bị scan toàn cục.
- [ ] Nếu list cuối có server, custom chooser trả response hợp lệ, không null/empty bất thường.
- [ ] Nếu có server được chọn, đã kiểm tra host/port, TLS, network, backend health.
- [ ] Metrics no-instance/discard và HTTP failed/success được đọc đúng định nghĩa.
- [ ] Retry/timeout có giới hạn; không tạo retry storm khi không có eligible instance.
- [ ] Đã chạy test với một instance, nhiều instances, list rỗng, stale cache và no-match filter.
- [ ] Đã quan sát quá trình recovery chứ không chỉ test một HTTP 200.
- [ ] Đã ghi lại root cause, hành động sửa và regression test.

## Tài liệu tham khảo

- [Spring Cloud Commons — Spring Cloud LoadBalancer](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html): `ServiceInstanceListSupplier`, caching, health, zone, hint, API version, retry, metrics và custom LoadBalancer.
- [Spring Cloud Commons — Common Abstractions](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html): `DiscoveryClient`, `ReactiveDiscoveryClient`, `SimpleDiscoveryClient` và registration.
- [Spring Cloud Commons — Configuration Properties](https://docs.spring.io/spring-cloud-commons/reference/configprops.html): cache TTL, health-check path/refetch, hint, retries và thống kê.
- [Spring Framework — RestClient](https://docs.spring.io/spring-framework/reference/integration/rest-clients.html): synchronous HTTP client, URI templates và exception handling.
- [Spring Framework — WebClient](https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html): reactive client, error/cancellation và request filters.
- [Spring Cloud OpenFeign](https://docs.spring.io/spring-cloud-openfeign/reference/spring-cloud-openfeign.html): Feign name, URL, LoadBalancer integration và exceptions.
- [Spring Boot — Actuator Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html): `/actuator/metrics`, MeterRegistry và quan sát ứng dụng.
- [Project Reactor — Testing](https://projectreactor.io/docs/core/release/reference/testing.html): `StepVerifier` cho publisher và reactive state.

**Kết luận:** để chẩn đoán **không có bản sao khả dụng**, đừng chỉ hỏi “inventory-service có đang chạy không?”. Hãy chứng minh bằng dữ liệu ở từng điểm: **caller dùng đúng service ID → discovery có instance → cache/health cập nhật → filter giữ đúng eligible candidates → chooser trả server → HTTP transport thực sự gửi request**. Khi tìm được tầng đầu tiên chuyển danh sách từ có phần tử sang rỗng, bạn có thể sửa đúng cấu hình hoặc policy, giữ nguyên những ràng buộc bảo mật cần thiết và bổ sung kiểm thử để sự cố không lặp lại.
