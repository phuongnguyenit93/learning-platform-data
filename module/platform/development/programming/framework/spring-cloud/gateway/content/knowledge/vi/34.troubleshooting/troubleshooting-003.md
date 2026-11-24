# 503 do không tìm thấy ServiceInstance hoặc không kết nối được đích

## 1. Nhận diện đúng hai tình huống khác nhau

Trong module **SPRING_CLOUD_GATEWAY**, Gateway nhận request từ client, chọn route bằng predicate, chạy filter chain, chuyển đổi path/header rồi gọi microservice thông qua URL cố định hoặc Spring Cloud LoadBalancer. Khi route dùng service discovery, Gateway cần tìm một **ServiceInstance** có thể phục vụ request. Khi route dùng host/port cụ thể, hoặc LoadBalancer đã chọn một instance, Gateway còn phải mở được kết nối mạng tới đích đó.

Hai lỗi thường cùng xuất hiện dưới dạng HTTP 503 ở phía client nhưng có nguyên nhân rất khác nhau:

1. **Không tìm thấy ServiceInstance:** LoadBalancer nhận danh sách instance rỗng, không chọn được host/port. Với Gateway WebFlux dùng URI `lb://SERVICE-ID`, hành vi mặc định được tài liệu mô tả là trả **503 Service Unavailable**; có thể cấu hình 404 theo property của release đang chạy.
2. **Đã chọn được đích nhưng không kết nối được:** Gateway có host/port, nhưng TCP connect bị refused, DNS không resolve, TLS handshake thất bại, pool acquire timeout hoặc đích không trả response đúng hạn. Đây là **transport failure**, không phải empty ServiceInstance list. Status cuối phụ thuộc error handling, retry, circuit breaker và policy của ứng dụng; không mặc định mọi `ConnectException` đều được Gateway tự đổi thành 503.

Ngoài ra, upstream có thể **tự trả HTTP 503** khi đã nhận request nhưng đang quá tải/bảo trì. Vì vậy, chỉ nhìn status 503 không đủ để kết luận lỗi nằm ở discovery, network hay backend.

### 1.1. Ba đường đi tạo ra status 503

~~~mermaid
flowchart TD
    C["Client request"] --> R["Gateway route matched"]
    R --> LB{"URI uses lb:// ?"}
    LB -->|Yes| S{"LoadBalancer finds ServiceInstance?"}
    S -->|No| E["Gateway default: 503"]
    S -->|Yes| N["Connect to selected host:port"]
    LB -->|No, fixed http(s) URI| N
    N -->|Connection / DNS / TLS / timeout error| X["Gateway error pipeline<br/>status depends on handling"]
    N -->|HTTP response received| U{"Upstream status"}
    U -->|503| P["Proxy upstream 503"]
    U -->|Other status| O["Proxy or transform response"]
~~~

| Nguồn 503/transport failure | Gateway đã chọn được instance? | Có HTTP response từ upstream? | Điểm điều tra đầu tiên |
| --- | --- | --- | --- |
| LoadBalancer không có instance | Không | Không | DiscoveryClient, service ID, instance list, filters/cache |
| TCP connection refused | Có thể đã có | Không | Host/port, listener, endpoint, NetworkPolicy |
| DNS lookup thất bại | Có thể đã có hostname | Không | DNS, service name, namespace, resolver |
| TLS handshake/certificate fail | Có | Chưa có HTTP response hợp lệ | Scheme, certificate, truststore, SNI |
| Connect/response timeout | Có | Có thể chưa có hoặc response đến quá muộn | Timeout, latency, pool, backend saturation |
| Upstream tự trả 503 | Có | Có, status 503 | Backend logs/health/capacity |
| Circuit breaker fallback | Có thể không gọi backend ở request này | Không nhất thiết | Circuit state, fallback policy, prior failures |

**Nguyên tắc của bài:** phân biệt **không có đích để chọn** với **có đích nhưng không đi tới được**, rồi mới sửa đúng tầng.

## 2. LoadBalancer của Gateway hoạt động thế nào?

### 2.1. Route dùng lb://SERVICE-ID

Ví dụ route WebFlux:

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: orders-api
              uri: lb://ORDER-SERVICE
              predicates:
                - Path=/api/orders/**
              filters:
                - StripPrefix=1
~~~

Với route `lb://ORDER-SERVICE`, `ReactiveLoadBalancerClientFilter` đọc service ID, yêu cầu Spring Cloud Reactor LoadBalancer chọn một `ServiceInstance`, sau đó thay URL logic bằng host/port của instance đã chọn. Gateway mới thực hiện outbound HTTP request tới địa chỉ đó.

Ví dụ service registry cung cấp:

~~~text
ORDER-SERVICE
  instance A: 10.20.1.15:8081
  instance B: 10.20.2.18:8081
  instance C: 10.20.3.21:8081
~~~

Gateway chọn một instance theo LoadBalancer configuration, ví dụ round-robin mặc định. Nếu danh sách instance trả về rỗng, không có host/port để mở kết nối. Đây là trường hợp **no ServiceInstance**.

### 2.2. URI cố định không dùng service discovery

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: orders-fixed
              uri: http://orders.internal:8081
              predicates:
                - Path=/api/orders/**
~~~

Route này gọi thẳng hostname/port đã cấu hình. Nó không hỏi LoadBalancer chọn instance từ `lb://`. DNS failure, connection refused hay timeout vẫn có thể xảy ra, nhưng việc kiểm tra phải tập trung vào DNS/network/host/port của target.

**Nếu bạn nghĩ route đang dùng discovery nhưng URI thực tế là `http://...`, việc sửa Eureka/Consul/Kubernetes registry sẽ không tác động route đó.** Hãy kiểm route definition hiệu lực và route ID trước.

### 2.3. Thành phần nào cung cấp ServiceInstance?

Spring Cloud LoadBalancer sử dụng `DiscoveryClient` có trong classpath để lấy instances; ví dụ:

- Eureka Discovery Client.
- Consul Discovery Client.
- Kubernetes Discovery Client.
- Zookeeper hoặc một discovery implementation khác.
- `SimpleDiscoveryClient`/danh sách cấu hình tĩnh trong môi trường phù hợp.
- Custom `ServiceInstanceListSupplier` của ứng dụng.

LoadBalancer dùng `ServiceInstanceListSupplier` để lấy danh sách, sau đó `ReactiveLoadBalancer` chọn instance. Vì thế lỗi rỗng có thể đến từ registry, supplier, filter theo zone/hint/version/health hoặc cache — không nhất thiết registry đã mất toàn bộ service.

### 2.4. Đảm bảo dependency đúng

Một cấu hình discovery thường cần:

- Gateway Server WebFlux starter tương thích release train.
- `spring-cloud-starter-loadbalancer`.
- Discovery client starter tương ứng nếu dùng registry thật.
- Registry endpoint/configuration và credentials/network policy đúng.
- Cấu hình đăng ký instance của các backend.

Không thêm một DiscoveryClient dependency bất kỳ rồi mặc định mọi service ID sẽ có instances. Cần kiểm dependency thực tế, auto-configuration, kết nối registry và dữ liệu được trả về.

## 3. Hiểu chính xác default 503 và tùy chọn 404

### 3.1. Không tìm thấy instance: default là 503

Tài liệu Spring Cloud Gateway mô tả: nếu `ReactorLoadBalancer` không tìm thấy service instance cho URI `lb://...`, Gateway mặc định trả **503**. Đây là phản hồi hợp lý vì route tồn tại nhưng service hiện không có instance có thể chọn.

**404 là một tùy chọn cấu hình**, không phải cách sửa discovery. Nó chỉ thay đổi status cho trường hợp LoadBalancer không chọn được instance; nó không tạo ra instance và không sửa connection refused.

### 3.2. Property theo release

Ví dụ namespace mới của **Gateway Server WebFlux 5.x**:

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          loadbalancer:
            use404: false
~~~

Ở các tài liệu/nhánh Gateway dùng namespace cũ, property thường được ghi:

~~~yaml
spring:
  cloud:
    gateway:
      loadbalancer:
        use404: true
~~~

**Đừng đặt cả hai biến thể theo kiểu copy/paste.** Tên property phải khớp version Gateway thực tế. Tài liệu Configuration Properties của Gateway 5.x liệt kê `spring.cloud.gateway.server.webflux.loadbalancer.use404`; tài liệu một số nhánh trước ghi `spring.cloud.gateway.loadbalancer.use404`. Kiểm `configprops`/effective configuration sau khi nâng cấp.

Chọn 404 chỉ khi public API contract thực sự muốn che giấu việc không có instance bằng “not found”. Với vận hành microservices, 503 thường phân biệt tốt hơn giữa **route không tồn tại** (404) và **service đang unavailable** (503).

### 3.3. Không biến mọi lỗi upstream thành 404

| Trường hợp | Status có thể phù hợp |
| --- | --- |
| Không có route match | 404 |
| Route `lb://` match nhưng không có ServiceInstance | 503 mặc định; 404 nếu bật tùy chọn |
| Backend nhận request và trả resource 404 | Giữ 404 theo business contract |
| Gateway connect không được tới upstream | 502 hoặc policy transport-error khác; cần cấu hình/kiểm chứng |
| Gateway chờ upstream quá deadline | 504 thường phù hợp với gateway timeout |
| Upstream quá tải và trả 503 | Giữ 503 nếu không có retry/fallback thành công |

**Không dùng `use404` để chữa DNS/connect/TLS/timeout**. Cấu hình này chỉ tác động nhánh LoadBalancer không chọn được instance.

## 4. Đọc log để phân biệt nguồn lỗi

### 4.1. Dấu hiệu no ServiceInstance

Các log thường có thông điệp tương tự:

~~~text
No servers available for service: ORDER-SERVICE
~~~

Thông điệp cụ thể phụ thuộc implementation/version và log level. Điểm quan trọng là LoadBalancer nhận danh sách rỗng hoặc không có server response.

Kiểm tra:

1. Service ID trong route có đúng tên mà DiscoveryClient công bố?
2. Có instance đăng ký không?
3. Instances có bị health supplier/filter loại hết không?
4. LoadBalancer context có được tạo và enabled không?
5. Registry có truy cập được từ Gateway?
6. Cache có đang giữ list cũ/rỗng không?

### 4.2. Dấu hiệu connect refused

Ví dụ log có thể thấy:

~~~text
java.net.ConnectException: Connection refused
Caused by: io.netty.channel.AbstractChannel$AnnotatedConnectException
~~~

Đây là dấu hiệu Gateway đã thử kết nối đến một địa chỉ cụ thể nhưng TCP handshake bị từ chối. Kiểm host/port đã chọn, process đang listen, Service/Endpoint và network path.

### 4.3. Dấu hiệu DNS

~~~text
java.net.UnknownHostException: orders-service.default.svc.cluster.local
~~~

Hostname không resolve trong môi trường Gateway. Kiểm service DNS, namespace/search domain, DNS policy, CoreDNS/resolver và tên target URI.

### 4.4. Dấu hiệu timeout

Log có thể cho biết connect timeout, response timeout, pool acquire timeout hoặc cancellation. Phải phân biệt:

- **Connect timeout:** không thiết lập được TCP connection trong thời gian cho phép.
- **Response timeout:** đã kết nối/gửi request nhưng không nhận response đủ sớm.
- **Pool acquire timeout:** chờ connection từ pool quá lâu, có thể chưa gửi request tới backend.
- **TLS handshake timeout:** đã bắt đầu kết nối bảo mật nhưng handshake không hoàn tất.

Tên exception/message khác nhau theo Netty, Gateway và version. Ghi lại **root cause**, route ID, selected target (đã redact), thời gian và upstream attempts, không chỉ dòng log ngoài cùng `500 Server Error`.

### 4.5. Dấu hiệu upstream tự trả HTTP 503

Nếu Gateway nhận response status 503 từ backend, đó không phải lỗi kết nối. Hãy kiểm:

- Backend logs tại đúng timestamp/trace ID.
- HTTP response headers/body đã được backend trả.
- Recorded request hoặc server access log chứng minh request tới backend.
- Gateway Retry/CircuitBreaker có thay đổi response cuối hay không.

Không phân loại upstream 503 thành "No servers available" nếu LoadBalancer đã chọn instance và backend đã trả HTTP response.

## 5. Checklist đầu tiên khi thấy 503

Thực hiện theo thứ tự, bắt đầu bằng dữ liệu ít gây thay đổi:

1. Ghi lại timestamp, request path/method, route ID, trace/correlation ID và status cuối.
2. Xác định route có URI `lb://SERVICE-ID` hay `http(s)://host:port`.
3. Kiểm log Gateway để tìm `No servers available`, `ConnectException`, `UnknownHostException`, timeout hoặc lỗi SSL.
4. Kiểm route ID, target service ID và path sau `StripPrefix`/`RewritePath`.
5. Nếu dùng LoadBalancer, xác minh DiscoveryClient trả bao nhiêu instances tại thời điểm lỗi.
6. Nếu đã chọn instance, kiểm hostname/port và kết nối từ network namespace của Gateway.
7. Kiểm xem upstream có nhận request và tự trả 503 hay không.
8. Kiểm retry, circuit breaker và fallback có thay đổi status/attempt count không.
9. So sánh một request thành công với request lỗi qua cùng route.
10. Chỉ sau khi khoanh vùng mới thay đổi registry, network, timeout, pool hoặc retry.

~~~text
Cần trả lời ba câu hỏi trước khi sửa:
  A. Gateway đã có ServiceInstance để chọn chưa?
  B. Gateway đã mở được kết nối tới host:port đã chọn chưa?
  C. Nếu đã có kết nối, upstream có trả HTTP response hay không?
~~~

## 6. Chẩn đoán ServiceInstance rỗng

### 6.1. Xác nhận service ID khớp registry

Route:

~~~yaml
routes:
  - id: orders-api
    uri: lb://ORDER-SERVICE
    predicates:
      - Path=/api/orders/**
~~~

Service ID phải trùng giá trị mà DiscoveryClient/LoadBalancer sử dụng. Ví dụ registry có thể công bố `ORDER-SERVICE` trong khi route lại gọi `lb://orders-service`. Không giả định mọi registry tự normalize chữ hoa/thường.

Nếu dùng Discovery Locator tự sinh routes, Gateway có tùy chọn `lower-case-service-id` ở một số discovery integrations để điều chỉnh tên service ID trong path/route. Điều này **không tự sửa mọi explicit route URI**. Kiểm service ID trong registry và route thực tế thay vì sửa hoa/thường theo cảm tính.

### 6.2. Xác minh DiscoveryClient có trong ứng dụng

Các câu hỏi cần trả lời:

- Starter của Eureka/Consul/Kubernetes/Zookeeper có đúng với Spring Cloud release train không?
- Có `spring-cloud-starter-loadbalancer` trong runtime classpath?
- Registry URI, TLS, credentials, namespace và network policy đúng?
- Gateway có thực sự nhận metadata/instances từ DiscoveryClient?
- Có tắt LoadBalancer qua `spring.cloud.loadbalancer.enabled=false` hoặc cấu hình custom không?
- Có nhầm tên application name với service ID được đăng ký không?

Nếu ứng dụng chỉ dùng `lb://ORDER-SERVICE` nhưng không có nguồn service instances, LoadBalancer không tự đoán IP/port từ tên đó.

### 6.3. Kiểm registry và trạng thái đăng ký

Đối với service registry:

1. Mở dashboard/API của registry trên network quản trị.
2. Tìm chính xác service ID.
3. Kiểm số instance, host, port, scheme/secure flag và metadata.
4. Kiểm trạng thái health/lease/heartbeat và thời điểm đăng ký.
5. Xem instance có vừa restart, đổi IP hoặc rời registry không.
6. So thời điểm Gateway bắt đầu thấy list rỗng với deploy/rollout/config change.

Không expose registry admin dashboard công khai để debug. Dùng credentials và private management network.

### 6.4. Kiểm service registration ở backend

Một backend có thể chạy nhưng không đăng ký vào registry vì:

- Chưa có discovery client dependency.
- Registration bị disable.
- App khởi động trước khi registry reachable và không retry registration đúng.
- Sai profile hoặc application name/service ID.
- Metadata/zone/health status không hợp lệ.
- Service bind port khác port đã đăng ký.
- Pod chưa Ready hoặc readiness probe fail.
- Instance bị deregister trong shutdown/rollout.

Kiểm logs của **backend service**, không chỉ Gateway. Một registry list rỗng có thể do upstream service chưa bao giờ đăng ký.

### 6.5. Kiểm service ID với discovery locator

Nếu muốn Gateway tự sinh route từ DiscoveryClient, ví dụ Gateway 5.x:

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          discovery:
            locator:
              enabled: true
              lower-case-service-id: true
~~~

Discovery Locator mặc định có thể sinh URI dạng `lb://serviceId`. Chỉ bật khi chủ động muốn expose những services đó qua Gateway. Không bật rộng trên mọi service nội bộ mà thiếu authentication, route allowlist và path policy. Nếu đã khai báo explicit routes, xác minh chúng không trùng route tự sinh hoặc có precedence khác mong muốn.

## 7. Registry có instances nhưng LoadBalancer vẫn không chọn được

Không phải lúc nào registry dashboard hiển thị instance cũng đồng nghĩa LoadBalancer nhận được danh sách không rỗng. Các tầng sau có thể lọc danh sách:

~~~text
DiscoveryClient
    -> DiscoveryClientServiceInstanceListSupplier
    -> optional cache
    -> health / zone / hint / version / custom supplier filters
    -> ReactorLoadBalancer.choose()
    -> selected ServiceInstance or EmptyResponse
~~~

### 7.1. Caching có thể giữ dữ liệu cũ

Spring Cloud LoadBalancer có cache danh sách instance. Tài liệu Spring Cloud Commons nêu TTL mặc định của cache built-in là 35 giây trong cấu hình được tài liệu mô tả; ứng dụng có thể thay đổi `spring.cloud.loadbalancer.cache.ttl` và `capacity`.

Khi deploy/scale service:

- Registry có thể đã cập nhật nhưng Gateway còn dùng cached list.
- Instance cũ có thể đã bị terminate trong khi cache chưa refresh.
- Nếu DiscoveryClient implementation đã tự cache, thêm LoadBalancer cache có thể tạo **double caching**.
- Tắt toàn bộ cache có thể tăng load lên registry; không phải giải pháp mặc định.

Ví dụ cấu hình TTL minh họa:

~~~yaml
spring:
  cloud:
    loadbalancer:
      cache:
        ttl: 15s
        capacity: 256
~~~

Chọn TTL theo tốc độ thay đổi instances, SLA và năng lực registry. Nếu provider đã cache, xem khuyến nghị của provider; có thể cần `spring.cloud.loadbalancer.cache.enabled=false` để tránh cache hai lần.

### 7.2. Health check có thể loại instance

`HealthCheckServiceInstanceListSupplier` kiểm tra các instances từ delegate supplier và chỉ cung cấp những instance được coi là khỏe theo cơ chế/phiên bản. Nó đặc biệt hữu ích khi dùng `SimpleDiscoveryClient` hoặc các cấu hình nhỏ; discovery-backed registry thường đã trả health status, nên thêm health check lặp lại có thể không cần thiết.

Một custom LoadBalancer configuration theo builder API được tài liệu hướng dẫn:

~~~java
package example.gateway.lb;

import org.springframework.cloud.loadbalancer.core.ServiceInstanceListSupplier;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;

public class OrdersLoadBalancerConfiguration {

    @Bean
    ServiceInstanceListSupplier discoveryClientServiceInstanceListSupplier(
            ConfigurableApplicationContext context) {

        return ServiceInstanceListSupplier.builder()
                .withDiscoveryClient()
                .withHealthChecks()
                .build(context);
    }
}
~~~

Đây là ví dụ cấu hình supplier. Khi dùng riêng cho một service, cần gắn qua cơ chế `@LoadBalancerClient` phù hợp với release train, và đảm bảo class cấu hình không bị component-scan như cấu hình toàn cục ngoài ý muốn. Không đăng ký cùng một custom supplier toàn cục nếu chỉ một service cần health-check.

### 7.3. Health endpoint và port phải đúng

Health check mặc định thường dùng path `/actuator/health`; có thể đặt path mặc định hoặc riêng cho service:

~~~yaml
spring:
  cloud:
    loadbalancer:
      health-check:
        path:
          default: /actuator/health
          ORDER-SERVICE: /actuator/health/readiness
        interval: 25s
        initial-delay: 10s
~~~

Đây là ví dụ property; xác nhận tên/kiểu duration theo version. Kiểm endpoint:

- Có thật trên instance không?
- Có yêu cầu authentication mà health checker không gửi không?
- Có đang chạy trên management port khác service port không?
- Trả 200/healthy theo đúng semantics chưa?
- Có bị gateway/network policy chặn request health check?
- Path readiness có phản ánh khả năng nhận traffic chứ không chỉ process alive?

Nếu health check dùng sai path/port, instance đang chạy có thể bị đánh dấu unhealthy. Nếu cần port riêng, LoadBalancer có property health-check port trong các release hỗ trợ; xác minh trước khi cấu hình.

**Lưu ý theo version:** hành vi supplier khi tất cả instance không vượt health check có thể khác giữa các release/supplier. Không tự giả định nó luôn fail-open hoặc luôn fail-closed; kiểm implementation/version và metrics list thực tế.

### 7.4. Zone, hint và version filtering

Danh sách có thể rỗng sau khi lọc:

- Zone preference chỉ giữ instances ở zone mong muốn.
- Hint/header chọn subset không có instance tương ứng.
- API version routing tìm metadata version không tồn tại.
- Custom supplier bỏ các instance không đúng tenant/capability.
- Health filter đánh dấu tất cả không healthy.

Đặc biệt nếu sử dụng API versioning qua metadata, một request chọn version không có instance có thể dẫn đến **empty list** dù service vẫn có instance version khác. Kiểm request headers/query, LoadBalancer hint, zone metadata và version metadata.

### 7.5. Không nhầm health của Gateway với health của backend

Gateway `/actuator/health` UP không chứng minh mọi service đích đều có instances. Một số health indicators chỉ cho biết process Gateway hoạt động; health của từng downstream cần metrics/health checks riêng, không nên làm Gateway readiness phụ thuộc tất cả services nếu yêu cầu kiến trúc không muốn cascade failure.

## 8. Nếu đã chọn ServiceInstance: kiểm host và port

### 8.1. Connection refused thường là TCP target sai hoặc không lắng nghe

Ví dụ LoadBalancer chọn:

~~~text
host = 10.20.1.15
port = 8081
secure = false
~~~

Nhưng backend thực tế đang nghe port 8080. Hoặc service đã dừng process, container đang restart, port mapping sai, hoặc app chỉ bind loopback. Khi Gateway kết nối tới địa chỉ không có listener, TCP có thể trả `Connection refused`.

Kiểm:

1. `ServiceInstance.host` và `ServiceInstance.port`.
2. Port process thật sự listen bên trong container.
3. Service port và targetPort (nếu Kubernetes).
4. Registry metadata có đúng port/scheme?
5. Backend bind address có thể nhận traffic từ Pod network?
6. Instance có vừa terminate nhưng vẫn còn trong registry/cache?
7. Service mesh sidecar có nhận và chuyển đúng port không?

### 8.2. Kubernetes: Service, EndpointSlice, Pod

Với Kubernetes, kiểm cùng namespace của service:

~~~bash
kubectl get svc -n app
kubectl get endpointslices -n app \
  -l kubernetes.io/service-name=orders
kubectl get pods -n app -o wide
kubectl describe svc orders -n app
~~~

Các kết quả cần đối chiếu:

- Service selector có match labels của Pod?
- EndpointSlice có địa chỉ/port endpoint nào?
- Endpoint có condition Ready/Serving/Terminating như thế nào?
- `targetPort` có trỏ tới đúng container port?
- Readiness probe có pass?
- Pod có bị restart/crashloop?
- NetworkPolicy có cho phép Gateway namespace/pod tới port service?
- Service có ở namespace khác và DNS/service discovery config có đúng?

**Service tồn tại không đồng nghĩa có endpoints sẵn sàng.** Một Kubernetes Service không có ready endpoints có thể dẫn đến connection failure hoặc discovery list rỗng, tùy integration và routing path.

### 8.3. Kiểm từ network namespace của Gateway

Không chỉ chạy curl trên laptop hoặc node. Cần kiểm từ nơi Gateway thực sự chạy, vì DNS, routes, security groups và NetworkPolicies khác nhau.

~~~bash
# Thay hostname/port bằng target thực tế đã xác định.
getent hosts orders.default.svc.cluster.local
nc -vz orders.default.svc.cluster.local 8081
curl -sv --connect-timeout 2 \
  http://orders.default.svc.cluster.local:8081/actuator/health
~~~

Nếu image Gateway không có `curl`/`nc`, dùng ephemeral debug container hoặc công cụ network được tổ chức cho phép trong cùng network namespace. Không cài thêm debug packages vào production image chỉ để kiểm tra tạm thời.

### 8.4. Phân biệt refused và timeout

| Kết quả | Ý nghĩa thường gặp |
| --- | --- |
| Connection refused ngay | Có thể đến được host nhưng port không có listener hoặc thiết bị chủ động reject |
| Connect timeout | Gói tin bị drop, network path/ACL/security group sai, hoặc target quá tải |
| DNS NXDOMAIN/UnknownHost | Tên service/namespace/search domain sai hoặc DNS lỗi |
| TLS handshake error | TCP kết nối được nhưng TLS/certificate/protocol không phù hợp |
| HTTP 404/503 trả nhanh | Đã có HTTP server trả response; kiểm route/app/upstream |
| Response timeout sau khi gửi | Backend xử lý chậm, deadlock, queueing hoặc response path bị nghẽn |

Không dùng `ping` thành bằng chứng duy nhất: ICMP có thể bị chặn trong khi TCP hoạt động, hoặc ping được nhưng cổng service vẫn đóng.

## 9. Kiểm scheme HTTP/HTTPS và chứng chỉ

### 9.1. isSecure của ServiceInstance có thể thay scheme

Gateway LoadBalancer có thể sử dụng giá trị `isSecure` của `ServiceInstance` để quyết định outbound scheme. Ví dụ client đến Gateway qua HTTPS nhưng instance được đánh dấu không secure, downstream có thể dùng HTTP; trường hợp ngược lại cũng có thể xảy ra. Nếu route sử dụng scheme prefix `lb` theo semantics đặc biệt, scheme của route có thể chi phối theo tài liệu.

Do đó, kiểm:

- Route URI `lb://...` hay `lb:https://...`/scheme prefix theo đúng syntax release?
- ServiceInstance secure flag/metadata có đúng?
- Backend có thật sự phục vụ TLS trên port được đăng ký?
- Certificate SAN có khớp hostname mà client verify?
- Certificate chain có đầy đủ và CA đã được trust?
- SNI có được gửi đúng theo target hostname?
- Cert có hết hạn hoặc chưa có hiệu lực?
- TLS version/cipher có tương thích?

### 9.2. Không tắt certificate verification để “sửa 503”

Property `use-insecure-trust-manager` tồn tại ở một số cấu hình Netty HttpClient nhưng tài liệu đánh dấu **không an toàn và không phù hợp production**. Đừng dùng nó để che lỗi CA/SAN. Cấu hình truststore/SSL bundle/certificate đúng và kiểm hostname.

Ví dụ cấu hình timeout và trusted certificates theo Gateway WebFlux 5.x:

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          httpclient:
            ssl:
              trusted-x509-certificates:
                - classpath:certs/orders-ca.pem
              handshake-timeout: 10s
~~~

Đây là ví dụ property cần đối chiếu release và định dạng certificate được hỗ trợ. Nếu dùng mTLS, cấu hình thêm client key/certificate theo SSL bundle/keystore phù hợp; không đưa password/key vào Git.

## 10. Khi nào là DNS, khi nào là service discovery?

### 10.1. Hai đường phân giải tên

~~~text
Route: lb://ORDER-SERVICE
   -> DiscoveryClient
   -> ServiceInstance(host, port, secure, metadata)
   -> Netty HttpClient

Route: http://orders.default.svc.cluster.local:8081
   -> DNS resolver
   -> IP address
   -> Netty HttpClient
~~~

Với `lb://`, DNS có thể không được Gateway gọi trực tiếp cho service ID; DiscoveryClient trả host/port thực tế. Với URI cố định dùng hostname, Netty/DNS resolver cần phân giải tên đó. Một service ID không tìm thấy trong registry khác với một hostname không resolve.

### 10.2. Các câu hỏi khi UnknownHostException

- Hostname được lấy từ route config hay ServiceInstance?
- Nếu từ registry, instance host có phải IP/hostname hợp lệ?
- Nếu là Kubernetes DNS, service/namespace/domain suffix đúng chưa?
- Gateway Pod có DNS policy và nameserver đúng?
- CoreDNS có lỗi hoặc throttling?
- Hostname có ký tự, dấu chấm hoặc suffix sai?
- DNS cache/TTL có giữ IP cũ?

### 10.3. Registry reachable không có nghĩa backend reachable

Gateway có thể kết nối thành công Eureka/Consul nhưng không thể kết nối instance IP do network ACL. Registry chỉ cung cấp metadata; nó không đảm bảo data-plane route từ Gateway tới backend mở được. Phải test hai đường riêng:

1. Gateway → Discovery Registry API.
2. Gateway → selected ServiceInstance host:port.

## 11. Timeout, connection pool và stale connections

### 11.1. Ba timeout khác nhau

Gateway WebFlux cho phép cấu hình connect timeout, response timeout và connection-pool acquire timeout.

| Timeout | Đợi điều gì? | Dấu hiệu |
| --- | --- | --- |
| Connect timeout | TCP connection tới target | Connect timeout / network unreachable |
| Response timeout | Response downstream | Read/response timeout |
| Pool acquire timeout | Lấy connection từ pool | Pending acquire timeout, pool saturation |

Ví dụ Gateway WebFlux 5.x:

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          httpclient:
            connect-timeout: 1000
            response-timeout: 5s
            pool:
              type: fixed
              max-connections: 200
              acquire-timeout: 1000
              metrics: true
~~~

Các giá trị chỉ là **ví dụ minh họa**, không phải sizing production. Connect timeout được nhập theo milliseconds; response timeout dùng Duration; pool acquire timeout áp dụng cho pool type FIXED. Kiểm version và cấu hình thực tế.

### 11.2. Timeout quá ngắn cũng tạo 503/5xx giả cảm nhận

Nếu backend p99 2 giây mà Gateway response timeout là 500 ms, request hợp lệ có thể bị cắt trước khi backend trả. Tăng timeout vô hạn lại giữ connections/in-flight requests lâu hơn, có thể làm quá tải khi backend đã chậm.

Đặt timeout theo latency budget:

~~~text
Client deadline
  > Gateway processing + outbound budget
  > backend service budget
  > database/dependency budget
~~~

Các deadline phải phối hợp để downstream có thời gian trả lỗi trước client. Không đặt mọi tầng cùng timeout hoặc để backend timeout dài hơn client mà không có lý do.

### 11.3. Connection pool và idle connection

Một số lỗi có thể xuất hiện sau thời gian idle: Gateway lấy lại một connection đã bị load balancer/proxy/backend đóng do idle timeout, sau đó request mới thất bại. Kiểm:

- Pool type và max connections.
- Max idle time/lifetime của Gateway.
- Idle timeout ở ingress/load balancer/backend.
- Pool pending acquire/active/idle metrics.
- TCP keepalive và server-side idle close behavior.
- Connection reset sau reuse.

Có thể điều chỉnh `max-idle-time` để không giữ connection lâu hơn upstream idle timeout. Không tắt pool ngay như giải pháp mặc định: nó làm tăng TCP/TLS handshake và connection churn. Chỉ thử pool disabled trong staging khi có bằng chứng pool reuse là nguyên nhân.

### 11.4. Pool metrics giúp phân biệt connection starvation

Gateway 5.x có property bật metrics cho Netty HttpClient pool:

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          httpclient:
            pool:
              metrics: true
~~~

Quan sát active/idle/pending connections, pending acquire timeouts và request latency. Nếu pool acquire timeout xảy ra trước khi request rời Gateway, việc tăng replicas backend có thể không giải quyết được pool capacity/traffic policy ở Gateway.

## 12. Retry và CircuitBreaker: hỗ trợ phục hồi, không thay sửa nguyên nhân

### 12.1. Retry có thể thử instance khác

Spring Cloud LoadBalancer hỗ trợ retry theo instance tiếp theo. Một số property thường gặp:

~~~yaml
spring:
  cloud:
    loadbalancer:
      retry:
        enabled: true
        max-retries-on-same-service-instance: 0
        max-retries-on-next-service-instance: 1
        avoid-previous-instance: true
~~~

Tên và behavior cần đối chiếu release train/integration. Retry theo instance tiếp theo hữu ích khi có **nhiều instances** và lỗi chỉ xảy ra trên một instance. Nếu danh sách instance rỗng, retry không thể tạo ra instance mới. Nếu mọi instance sai port hoặc NetworkPolicy chặn, retry chỉ tăng attempts và latency.

Gateway có `Retry` GatewayFilter riêng, còn LoadBalancer có retry policy riêng. Nếu bật cả hai, tổng số attempts có thể lớn hơn dự kiến. Hãy ghi số request thực đến upstream, phân biệt retry ở Gateway và retry ở LoadBalancer.

### 12.2. Chỉ retry thao tác có semantics phù hợp

- GET/HEAD thường dễ retry hơn khi backend idempotent.
- POST tạo order/payment có thể đã commit dù Gateway không nhận response.
- Retry sau connect failure khác retry sau timeout giữa lúc backend xử lý.
- Nếu retry write request, cần idempotency key, backend deduplication và kiểm tra side effects.
- Dùng backoff/jitter phù hợp; tránh tất cả Gateway replicas retry đồng thời.

### 12.3. Circuit breaker không tạo ServiceInstance

Circuit breaker có thể mở khi failure rate/slow calls vượt ngưỡng. Khi mở, request bị short-circuit và có thể đi tới fallback. Nếu fallback trả 503, client có thể thấy 503 dù backend **không được gọi** ở request đó.

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: orders-api
              uri: lb://ORDER-SERVICE
              predicates:
                - Path=/api/orders/**
              filters:
                - name: CircuitBreaker
                  args:
                    name: ordersCircuit
                    fallbackUri: forward:/fallback/orders
~~~

Đây là ví dụ Gateway 5.x; fallback handler phải được cài đặt và policy phải rõ. Fallback không nên trả 200 giả cho lệnh ghi chưa được xác nhận. Có thể trả Problem Details 503 hoặc response business-specific nếu contract xác định chính xác trạng thái thao tác.

### 12.4. Khi Retry/CircuitBreaker đang bật

1. Kiểm circuit state (closed/open/half-open).
2. Đếm request có thật sự đi vào upstream không.
3. Xem số retry ở Gateway filter và LoadBalancer.
4. Kiểm instance được chọn ở mỗi attempt.
5. Xác định response cuối đến từ upstream, fallback hay exception handler.
6. Không tắt circuit breaker production để debug nếu chưa giới hạn tải; dùng staging/canary.

## 13. Quan sát Gateway và LoadBalancer

### 13.1. Metrics cần bật

Ví dụ Gateway Server WebFlux 5.x:

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          metrics:
            enabled: true
    loadbalancer:
      stats:
        include-path: false
~~~

Cần Actuator/Micrometer registry tương ứng. Tài liệu Gateway mô tả timer `spring.cloud.gateway.requests` với tags như route ID, route URI, outcome, status, HTTP status code và method. Spring Cloud LoadBalancer cung cấp các meters:

- `loadbalancer.requests.success`: request LoadBalancer kết thúc với response.
- `loadbalancer.requests.failed`: request kết thúc bằng exception.
- `loadbalancer.requests.discard`: không lấy được ServiceInstance để thực hiện request.

**Discard** là tín hiệu hữu ích khi nghi instance list rỗng. Nó khác failed connection tới một instance đã chọn.

### 13.2. Ma trận quan sát

| Chỉ số/log | Dấu hiệu | Cách đọc |
| --- | --- | --- |
| Gateway requests status 503 | Client nhận 503 | Chưa xác định nguồn; cần route/error source |
| LoadBalancer discard tăng | Không lấy được instance | Kiểm registry, suppliers, cache/filters |
| LoadBalancer failed tăng | LB request kết thúc bằng exception | Kiểm selected instance và transport |
| LoadBalancer success tăng, upstream 503 | Có HTTP response | Backend trả status hoặc response pipeline |
| Connection refused logs | TCP connect bị từ chối | Host/port/listener/network |
| UnknownHostException | Không resolve hostname | DNS/service ID/registry host |
| Pool pending acquire tăng | Chờ connection pool | Capacity/pool saturation |
| Connect timeout | TCP handshake quá thời gian | Network path/firewall/target |
| Response timeout | Đích phản hồi chậm | Backend latency/dependency |
| TLS handshake error | Kết nối bảo mật lỗi | Cert/SAN/SNI/truststore/scheme |

Metric 503 tổng hợp không đủ phân biệt nguyên nhân. Kết hợp **route ID + error category + LoadBalancer meters + upstream request count**.

### 13.3. Actuator metrics trong mạng quản trị

~~~bash
curl -s http://localhost:8080/actuator/metrics/spring.cloud.gateway.requests
curl -s http://localhost:8080/actuator/metrics/loadbalancer.requests.discard
curl -s http://localhost:8080/actuator/metrics/loadbalancer.requests.failed
~~~

Tên metrics/availability phụ thuộc dependencies, version, observations và registry. Nếu không có metric, kiểm Actuator, LoadBalancer stats instrumentation và Micrometer registry đã được cấu hình chưa.

Không public Actuator metrics/routes/env cho Internet. Chỉ expose endpoints cần thiết trên management network và có authentication/access control.

### 13.4. Log level tạm thời

~~~yaml
logging:
  level:
    org.springframework.cloud.gateway: DEBUG
    org.springframework.cloud.loadbalancer: DEBUG
~~~

Chỉ bật trong staging/canary hoặc trong thời gian ngắn có kiểm soát. Kiểm volume log và tránh dump Authorization/cookies/body. Logger names và mức chi tiết thay đổi theo version. Không bật DEBUG toàn bộ Netty ở production như giải pháp mặc định; wiretap có thể tạo log volume lớn và lộ payload.

### 13.5. Log theo route và error category

Một event vận hành hữu ích:

~~~text
timestamp=...
routeId=orders-api
serviceId=ORDER-SERVICE
outcome=UPSTREAM_CONNECT_FAILURE
selectedInstance=orders-7.internal:8081
exceptionCategory=CONNECT_REFUSED
attempt=1
durationMs=18
traceId=...
~~~

Đây là schema minh họa, không phải output mặc định. Host/port của instance chỉ nên nằm trong logs nội bộ có phân quyền; không trả cho client hoặc dùng hostname động làm metric label.

## 14. Quy trình chẩn đoán theo từng tầng

### Bước 1 — Kiểm route thực tế

- Route ID có match request?
- URI là `lb://ORDER-SERVICE` hay fixed host?
- Service ID có đúng tên/case?
- Predicate path/method/host có match?
- StripPrefix/RewritePath có ảnh hưởng đường dẫn?
- Discovery Locator có sinh route trùng hoặc precedence khác mong muốn?

Nếu route không match, đây là no-route 404, chưa phải LoadBalancer 503.

### Bước 2 — Kiểm instance list

- DiscoveryClient có nhận service ID?
- Có instance nào?
- Host/port/secure flag đúng?
- Registry status/heartbeat/lease còn hiệu lực?
- Zone/hint/version/health filters có loại hết?
- Cache có giữ dữ liệu cũ?
- Có custom ServiceInstanceListSupplier?

Nếu list rỗng, xử lý discovery/supplier trước khi kiểm port.

### Bước 3 — Nếu có instance, kiểm kết nối

- DNS resolve target?
- TCP port mở?
- Backend process đang listen?
- Kubernetes EndpointSlice có ready endpoint?
- NetworkPolicy/security group cho phép?
- Gateway và backend có cùng service mesh/TLS policy?
- Pool có stale connection/pending acquire?

### Bước 4 — Kiểm response của upstream

- Backend có nhận request không?
- Backend trả HTTP status nào?
- Response bị timeout hay body streaming bị ngắt?
- Retry/CircuitBreaker có thay đổi final response?
- Request ID có tương quan được giữa Gateway và backend?

### Bước 5 — Kiểm lỗi tại Gateway

- Log có ConnectException, UnknownHostException, SSLException?
- Có custom error handler/fallback mapping status?
- Có pool acquire timeout hoặc event-loop pressure?
- Gateway Pod có CPU/memory/DNS/network pressure?

### Bước 6 — Xác minh sau sửa

- Chạy lại cùng request trên route.
- Xác nhận upstream request count tăng đúng.
- Xác nhận target instance đúng.
- Xác nhận response status/body phù hợp.
- Kiểm nhiều Gateway replicas.
- Theo dõi metrics discard/failed/latency sau rollout.

## 15. Kubernetes: Service, EndpointSlice và Pod readiness

### 15.1. Kiểm Service và endpoints

~~~bash
kubectl get svc orders -n app -o yaml
kubectl get endpointslices -n app -l kubernetes.io/service-name=orders -o yaml
kubectl get pods -n app -l app=orders -o wide
kubectl describe svc orders -n app
~~~

Đối chiếu:

- Service selector có match Pod labels?
- `port` và `targetPort` có đúng?
- EndpointSlice có địa chỉ/port endpoint nào?
- Endpoint conditions Ready/Serving/Terminating ra sao?
- Pod có restart/crash loop/OOMKilled?
- Readiness probe có pass?
- NetworkPolicy có cho phép Gateway namespace/pod tới service port?

**Service tồn tại không đồng nghĩa có endpoints sẵn sàng.** Một Service không có ready endpoints có thể dẫn đến connection failure hoặc discovery list rỗng tùy integration.

### 15.2. Kiểm Pod và logs

~~~bash
kubectl describe pod <orders-pod> -n app
kubectl logs <orders-pod> -n app --since=15m
kubectl logs <orders-pod> -n app --previous
~~~

Tìm startup failure, readiness/liveness probe, port binding, restart count và startup delay. Nếu app chỉ bind loopback thay vì Pod interface, Service/Pod IP không thể kết nối dù process đang chạy.

### 15.3. Kiểm NetworkPolicy

~~~bash
kubectl get networkpolicy -A
kubectl describe networkpolicy -n app
~~~

Xác nhận egress từ Gateway đến backend port và ingress vào backend. Kiểm CNI thực sự enforce policy, namespace labels và pod selectors. Default-deny có thể gây timeout dù Service và EndpointSlice đúng.

Không nới NetworkPolicy/port trên production theo kiểu thử-và-sai. Thu thập selected endpoint, port, TCP probe, EndpointSlice và effective network policy trước khi đổi.

## 16. Phân biệt DNS và Service Discovery

### 16.1. Hai cách phân giải target

~~~text
Route: lb://ORDER-SERVICE
   -> DiscoveryClient
   -> ServiceInstance(host, port, secure, metadata)
   -> Netty HttpClient

Route: http://orders.app.svc.cluster.local:8081
   -> DNS resolver
   -> IP address
   -> Netty HttpClient
~~~

Với `lb://`, Gateway hỏi DiscoveryClient lấy instance; DNS có thể không được gọi trực tiếp cho service ID. Với URI cố định dùng hostname, Netty/DNS resolver phải phân giải tên đó. Service ID không có trong registry khác với hostname không resolve.

### 16.2. UnknownHostException

- Hostname lấy từ route config hay ServiceInstance?
- Nếu từ registry, instance host có phải IP/hostname hợp lệ?
- Nếu Kubernetes DNS, service/namespace/domain suffix đúng chưa?
- Gateway Pod có DNS policy/nameserver đúng?
- CoreDNS có lỗi/throttling?
- DNS cache/TTL có giữ IP cũ?

### 16.3. Registry reachable không có nghĩa backend reachable

Gateway có thể kết nối Eureka/Consul nhưng không thể kết nối instance IP do network ACL. Registry chỉ cung cấp metadata; nó không đảm bảo data-plane path từ Gateway đến backend. Kiểm hai đường riêng:

1. Gateway → Discovery Registry API.
2. Gateway → selected ServiceInstance host:port.

## 17. Chọn hướng sửa dựa trên bằng chứng

| Bằng chứng | Hướng xử lý |
| --- | --- |
| Service ID route sai | Sửa URI/registry name |
| Registry không có registration | Sửa backend registration/registry connectivity |
| EndpointSlice rỗng do Pod chưa Ready | Sửa readiness/rollout/backend startup |
| Host/port đăng ký sai | Sửa metadata/registration/service targetPort |
| Tất cả instances bị health filter loại | Sửa health path/port/security/health policy |
| LoadBalancer cache stale | Điều chỉnh cache TTL/refetch theo evidence |
| DNS fixed URI lỗi | Sửa DNS/service name/resolver |
| Connection refused | Sửa listener/port/target/endpoint |
| Network timeout | Sửa routing/ACL/NetworkPolicy/firewall |
| TLS handshake error | Sửa cert/truststore/SNI/scheme |
| Backend trả HTTP 503 thật | Sửa capacity/dependency/maintenance hoặc giữ 503 đúng contract |
| Gateway pool acquire timeout | Sửa pool capacity/concurrency/upstream latency |
| Circuit breaker mở liên tục | Điều tra underlying failures và thresholds |
| Retry tạo nhiều attempts | Sửa retry scope/idempotency/backoff |

Đừng tăng timeout nếu service ID sai. Đừng restart Gateway nếu registry không có instance. Đừng bật retry nếu mọi instance đều bị connection refused. Đừng chuyển 503 thành 404 chỉ để dashboard bớt đỏ.

## 18. Bài thực hành tổng hợp

**Bối cảnh:** Gateway Server WebFlux có route `lb://ORDER-SERVICE` cho `/api/orders/**`. Sau một lần deploy backend, client bắt đầu nhận 503. Bạn cần tìm xem LoadBalancer không có ServiceInstance, hay đã chọn instance nhưng kết nối tới host/port thất bại.

### Yêu cầu

1. Ghi Gateway/Spring Boot/Spring Cloud release train và runtime WebFlux.
2. Khai báo route `orders-api` dùng `lb://ORDER-SERVICE`.
3. Dùng mock DiscoveryClient hoặc test ServiceInstance supplier cho ba trường hợp: list rỗng, instance đúng và instance sai port.
4. Với list rỗng, xác minh default 503; thử use404 trong test riêng.
5. Với instance đúng, dùng MockWebServer hoặc backend local để xác minh request thực được proxy.
6. Với instance sai port, ghi nhận ConnectException/transport failure và status thực tế của error handler.
7. Tạo upstream chủ động trả HTTP 503 và chứng minh nó khác no-instance case.
8. Thử service ID sai hoa/thường.
9. Thử registry unreachable và registry có service nhưng zero healthy instances.
10. Thử cache TTL để quan sát thời gian hội tụ sau khi instance thay đổi.
11. Nếu dùng health check, cấu hình path/port đúng và chứng minh supplier behavior.
12. Thử Gateway connect timeout và response timeout riêng.
13. Thử DNS unknown host và TCP refused riêng.
14. Thử certificate không trust và hostname/SAN không khớp trong test TLS.
15. Bật metrics và kiểm LoadBalancer discard/failed/success.
16. Kiểm Retry/CircuitBreaker attempts và status/fallback cuối.
17. Viết runbook dùng logs/metrics/Actuator/kubectl/curl.
18. Không ghi token, secret, private key hoặc raw customer payload vào logs.

### Ma trận nghiệm thu

| ID | Tình huống | Kỳ vọng |
| --- | --- | --- |
| T01 | Route không match | 404 no-route, không có LB attempt |
| T02 | `lb://` list rỗng | Gateway default 503 |
| T03 | use404 bật | 404 chỉ cho no-instance path theo version |
| T04 | Có instance đúng | Backend nhận request |
| T05 | Service ID sai | LB discard/empty selection được nhận diện |
| T06 | Instance port sai | Transport error, không nhầm empty list |
| T07 | TCP refused | Xác định host/port/listener |
| T08 | DNS failure | Xác định hostname/resolver |
| T09 | TLS certificate fail | Xác định trust/SAN/SNI |
| T10 | Connect timeout | Phân biệt với response timeout |
| T11 | Backend trả HTTP 503 | Có upstream response và request record |
| T12 | Health filter loại hết | Xác minh supplier/version behavior |
| T13 | Retry next instance | Attempt count đúng, không retry mù |
| T14 | Circuit breaker open | Fallback rõ, không giả business success |
| T15 | Pool acquire timeout | Metrics pool cho thấy saturation |
| T16 | Sau rollout/refresh | Instance list hội tụ và route hoạt động |

Đây là **test expectations**, không phải lệnh đã chạy trên môi trường hiện tại.

## 19. Checklist xử lý 503

- [ ] Xác định route ID và URI thực tế.
- [ ] Phân biệt `lb://SERVICE-ID` với URI host/port cố định.
- [ ] Kiểm service ID chính xác và case.
- [ ] Kiểm dependency LoadBalancer và DiscoveryClient.
- [ ] Kiểm registry có instances và trạng thái registration.
- [ ] Kiểm ServiceInstance host/port/secure metadata.
- [ ] Kiểm supplier/filter theo zone, hint, version và health.
- [ ] Kiểm cache TTL/double caching.
- [ ] Nếu Kubernetes, kiểm Service, EndpointSlice, Pod Ready, targetPort và NetworkPolicy.
- [ ] Nếu đã chọn instance, test DNS và TCP từ Gateway network namespace.
- [ ] Phân biệt refused, timeout, DNS, TLS và pool acquire.
- [ ] Kiểm connect/response/pool timeouts.
- [ ] Kiểm upstream có thực sự trả HTTP 503 không.
- [ ] Kiểm retry attempts và circuit breaker state/fallback.
- [ ] Bật metrics LoadBalancer discard/failed/success và Gateway route status.
- [ ] Giữ Actuator/registry dashboards ở management network.
- [ ] Không bật insecure trust manager hoặc retry mọi request như giải pháp chữa cháy.
- [ ] Xác minh sau sửa qua upstream recorded request và nhiều Gateway replicas.
- [ ] Có rollback/monitoring sau thay đổi.

## 20. Tổng kết và tài liệu tham khảo

Khi client nhận 503 từ Spring Cloud Gateway, hãy trả lời lần lượt:

1. **Route có dùng `lb://` không?**
2. **LoadBalancer có nhận được ServiceInstance để chọn không?**
3. **Nếu đã chọn, Gateway có kết nối được host/port không?**
4. **Nếu kết nối được, upstream đã tự trả 503 hay Retry/CircuitBreaker tạo response cuối?**

Không tìm được ServiceInstance trong Gateway WebFlux mặc định dẫn tới 503; property `use404` chỉ đổi status của nhánh empty instance list. Connection refused, DNS failure, TLS failure và timeout là các lỗi transport riêng, cần điều tra endpoint/network/client configuration và error mapping thực tế. Một backend tự trả 503 lại là một HTTP response đã nhận được.

Hãy dùng **route ID, instance list, LoadBalancer metrics, upstream request count và root-cause exception** để xác định tầng hỏng. Sau đó sửa đúng registry, supplier/cache/health, port/network, TLS, pool hoặc backend. Retry và CircuitBreaker chỉ hỗ trợ phục hồi; chúng không thể tạo ra instance đang thiếu hoặc mở một cổng TCP bị chặn.

### Tài liệu tham khảo chính thức

- [Spring Cloud Gateway Server WebFlux — Global Filters / ReactiveLoadBalancerClientFilter](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/global-filters.html).
- [Spring Cloud Gateway Server WebFlux — HTTP timeouts configuration](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/http-timeouts-configuration.html).
- [Spring Cloud Gateway — Configuration Properties 5.x](https://docs.spring.io/spring-cloud-gateway/reference/configprops.html).
- [Spring Cloud Commons — Spring Cloud LoadBalancer](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html).
- [Spring Cloud Commons — LoadBalancer Configuration Properties](https://docs.spring.io/spring-cloud-commons/reference/configprops.html).
- [Spring Guide — Client-Side Load-Balancing with Spring Cloud LoadBalancer](https://spring.io/guides/gs/spring-cloud-loadbalancer/).
