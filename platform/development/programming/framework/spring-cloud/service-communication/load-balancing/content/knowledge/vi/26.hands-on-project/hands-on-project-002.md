# So sánh URL cố định với gọi bằng tên dịch vụ

Khi hai microservice giao tiếp qua HTTP, mã nguồn có thể dùng **URL vật lý cố định** như `http://127.0.0.1:8081` hoặc **tên dịch vụ logic** như `http://catalog-service`. Hai URL trông tương tự, nhưng **không mang cùng ngữ nghĩa định tuyến**.

Trong **Spring Cloud LoadBalancer**, `catalog-service` có thể là **service ID**: client lấy danh sách `ServiceInstance`, chọn một bản sao, thay host/port logic bằng địa chỉ vật lý rồi gửi HTTP. Ngược lại, với URL cố định, HTTP client đi thẳng tới một endpoint đã biết; không có bước chọn instance qua Spring Cloud LoadBalancer.

Bài thực hành thuộc chương **Thực hành tổng hợp** của module Spring Cloud LoadBalancer. Bạn sẽ khởi chạy **hai bản sao `catalog-service` và một `order-service`**, thử hai cách gọi trong cùng ứng dụng, quan sát phân phối request và kiểm tra điều gì xảy ra khi một instance dừng.

Sau bài học, người học có thể:

1. Phân biệt URL vật lý, service ID và hostname DNS.
2. Cấu hình một `RestClient` trực tiếp và một `@LoadBalanced RestClient.Builder` trong cùng caller.
3. Cung cấp hai bản sao bằng `SimpleDiscoveryClient` mà không cần cài Eureka/Consul.
4. Quan sát chính xác instance xử lý request từ response.
5. Giải thích hành vi scale-up, instance chết, discovery tĩnh, cache và retry.
6. Chuyển nguyên tắc tương tự sang `WebClient` và OpenFeign.

> Ví dụ chạy ở localhost, chỉ dành cho môi trường học tập. Trong Docker/Kubernetes, `127.0.0.1` trỏ tới chính network namespace của tiến trình/container, không mặc nhiên tới một dịch vụ khác.

## 1. Hai chiến lược gọi HTTP

### 1.1. Gọi URL cố định

~~~java
RestClient direct = RestClient.create("http://127.0.0.1:8081");

CatalogItem item = direct.get()
        .uri("/api/products/{id}", 42)
        .retrieve()
        .body(CatalogItem.class);
~~~

Đường đi:

~~~text
order-service
    |
    | GET http://127.0.0.1:8081/api/products/42
    v
catalog-service replica A (8081)
~~~

Client biết host/port cụ thể. Nếu một bản sao mới chạy ở port 8082, URL trên **không tự chuyển sang 8082**. Một URL direct có thể vẫn trỏ tới proxy/load balancer bên ngoài, nhưng **Spring Cloud LoadBalancer của caller** không tự tham gia khi client không được cấu hình load-balanced.

### 1.2. Gọi bằng service ID

~~~java
// Builder đã được @LoadBalanced và Spring Cloud cấu hình.
RestClient logical = loadBalancedBuilder
        .baseUrl("http://catalog-service")
        .build();

CatalogItem item = logical.get()
        .uri("/api/products/{id}", 42)
        .retrieve()
        .body(CatalogItem.class);
~~~

Khi integration hoạt động, hostname `catalog-service` được coi là **service ID**, còn địa chỉ gửi HTTP thực tế được LoadBalancer xác định từ danh sách instance.

~~~mermaid
flowchart LR
    A["order-service<br/>GET http://catalog-service"]
    B["Spring Cloud LoadBalancer"]
    C["ServiceInstanceListSupplier"]
    D["catalog-a<br/>127.0.0.1:8081"]
    E["catalog-b<br/>127.0.0.1:8082"]
    A --> B
    B <--> C
    B --> D
    B --> E
~~~

### Bảng so sánh

| Tiêu chí | URL cố định | Service ID + Spring Cloud LoadBalancer |
|---|---|---|
| Base URL | `http://127.0.0.1:8081` | `http://catalog-service` |
| Giá trị host | Host vật lý hoặc proxy đã biết | Service ID cần resolve qua supplier |
| Chọn instance tại caller | Không | Có, nếu client có LB interceptor/filter |
| Thêm instance | Không tự đổi URL | Có thể dùng sau khi discovery cập nhật |
| Một instance chết | Request tới nó lỗi | Có thể vẫn bị chọn nếu discovery/cache stale |
| Round-robin/weight/zone | Không tại caller | Có thể cấu hình |
| DNS | Có thể dùng nếu URL chứa hostname | Không cần DNS cho service ID logic trong lab |
| Retry, pool, timeout | Do HTTP/resilience layer | Vẫn do HTTP/resilience layer sau selection |

**Quan trọng:** chỉ viết `http://catalog-service` không tự bật LoadBalancer. HTTP client thường có thể cố phân giải `catalog-service` như một hostname DNS và báo lỗi nếu không có bản ghi tương ứng.

## 2. Kiến trúc bài thực hành

Ta xây dựng hai ứng dụng Spring Boot, chạy thành **ba tiến trình**:

- `catalog-service` A chạy ở cổng `8081`, trả `instanceId=catalog-a`.
- `catalog-service` B chạy ở cổng `8082`, trả `instanceId=catalog-b`.
- `order-service` chạy ở cổng `8080`, có hai endpoint: gọi trực tiếp hoặc gọi bằng service ID.

~~~mermaid
flowchart TB
    U["Người học / curl"]
    O["order-service :8080"]
    D["RestClient direct<br/>127.0.0.1:8081"]
    L["RestClient load-balanced<br/>catalog-service"]
    LB["LoadBalancer"]
    S["SimpleDiscoveryClient<br/>A + B"]
    A["catalog-a :8081"]
    B["catalog-b :8082"]
    U --> O
    O -->|"/compare/direct/42"| D --> A
    O -->|"/compare/service/42"| L --> LB
    LB <--> S
    LB --> A
    LB --> B
~~~

Gợi ý cấu trúc source:

~~~text
url-vs-service-id-demo/
├── settings.gradle.kts
├── catalog-service/
│   ├── build.gradle.kts
│   └── src/main/java/com/example/catalog/
│       ├── CatalogApplication.java
│       └── CatalogController.java
└── order-service/
    ├── build.gradle.kts
    ├── src/main/java/com/example/orders/
    │   ├── OrderApplication.java
    │   ├── CatalogItem.java
    │   ├── CatalogClientConfiguration.java
    │   └── ComparisonController.java
    └── src/main/resources/application.yml
~~~

Sơ đồ trên là **các file người học tạo cho lab**, không phải file đã được bài viết tạo sẵn. Có thể làm với Maven thay vì Gradle.

## 3. Chuẩn bị môi trường và dependency

Điều kiện:

- JDK phù hợp với Spring Boot của project; với Spring Boot 3.x thường sử dụng Java 17+.
- Spring Framework **6.1+** nếu dùng `RestClient`.
- Spring Boot và Spring Cloud BOM/release train **tương thích**, không tự trộn phiên bản starter.
- Cổng 8080, 8081, 8082 còn trống; ba terminal và curl hoặc PowerShell.

`settings.gradle.kts`:

~~~kotlin
rootProject.name = "url-vs-service-id-demo"
include("catalog-service", "order-service")
~~~

Dependency `catalog-service/build.gradle.kts`:

~~~kotlin
plugins {
    java
    id("org.springframework.boot")
    id("io.spring.dependency-management")
}

dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
}
~~~

Dependency `order-service/build.gradle.kts`:

~~~kotlin
plugins {
    java
    id("org.springframework.boot")
    id("io.spring.dependency-management")
}

dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    implementation("org.springframework.cloud:spring-cloud-starter-loadbalancer")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
}
~~~

Các đoạn Gradle chỉ minh họa phần liên quan bài: cấu hình build đầy đủ vẫn cần plugin versions, Maven Central và Spring Cloud BOM `spring-cloud-dependencies` ở parent/root. Ở Spring Boot 4, cần chọn starter WebMVC và dependency management đúng thế hệ Boot 4. **Không chép nguyên snippet từ Boot 3 vào một project Boot 4 khi chưa kiểm tra tên starter.**

`spring-cloud-starter-loadbalancer` phải có trong caller nếu muốn Spring Cloud chọn instance. `spring-boot-starter-web` không thay thế dependency đó.

## 4. Viết backend catalog-service

### Application entry point

Tạo `CatalogApplication.java`:

~~~java
package com.example.catalog;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CatalogApplication {

    public static void main(String[] args) {
        SpringApplication.run(CatalogApplication.class, args);
    }
}
~~~

### Controller trả instance ID

Tạo `CatalogController.java`:

~~~java
package com.example.catalog;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/products")
public class CatalogController {

    private final String instanceId;
    private final int port;

    public CatalogController(
            @Value("${demo.instance-id}") String instanceId,
            @Value("${server.port}") int port) {
        this.instanceId = instanceId;
        this.port = port;
    }

    @GetMapping("/{id}")
    public CatalogItem get(@PathVariable long id) {
        return new CatalogItem(
                id, "Product-" + id, instanceId, port);
    }

    public record CatalogItem(
            long id, String name, String instanceId, int port) {
    }
}
~~~

Nếu chạy với port 8081 và `demo.instance-id=catalog-a`, response:

~~~json
{
  "id": 42,
  "name": "Product-42",
  "instanceId": "catalog-a",
  "port": 8081
}
~~~

Bản sao ở port 8082 sẽ trả `catalog-b` và `8082`. Mục đích của hai field này là **giúp bài thử nhận diện backend thực sự xử lý request**. Không nhất thiết công khai thông tin topology trong API production.

## 5. Viết order-service và cấu hình discovery

### 5.1. Application class

~~~java
package com.example.orders;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OrderApplication {
    public static void main(String[] args) {
        SpringApplication.run(OrderApplication.class, args);
    }
}
~~~

### 5.2. DTO nhận JSON từ catalog

Tạo `CatalogItem.java`:

~~~java
package com.example.orders;

public record CatalogItem(
        long id, String name, String instanceId, int port) {
}
~~~

Lab tạo cùng JSON contract ở cả hai ứng dụng. Trong hệ thống thật, không nhất thiết dùng chung lớp DTO Java; điều bắt buộc là client/server thống nhất HTTP contract.

### 5.3. application.yml

~~~yaml
server:
  port: 8080

demo:
  catalog:
    direct-url: http://127.0.0.1:8081

spring:
  cloud:
    discovery:
      client:
        simple:
          instances:
            catalog-service:
              - uri: http://127.0.0.1:8081
              - uri: http://127.0.0.1:8082
    loadbalancer:
      cache:
        enabled: false
      retry:
        enabled: false
~~~

| Thuộc tính | Tác dụng |
|---|---|
| `demo.catalog.direct-url` | Property riêng của ứng dụng cho client direct |
| `spring.cloud.discovery.client.simple.instances.catalog-service` | Danh sách hai `ServiceInstance` tĩnh |
| `uri` | Endpoint vật lý của mỗi instance |
| `spring.cloud.loadbalancer.cache.enabled=false` | Tắt cache LB để đơn giản hóa lab |
| `spring.cloud.loadbalancer.retry.enabled=false` | Tắt LB retry để phân biệt một lần gọi với nhiều attempts |

`SimpleDiscoveryClient` không có heartbeat hay tự xóa instance khi port 8081 bị đóng. Nếu A dừng, YAML vẫn chứa A. Đặt cache disabled **không có nghĩa discovery tự cập nhật**.

Một project production nên xem xét lại cache phù hợp với discovery client; không dùng cấu hình lab làm khuyến nghị triển khai mặc định.

## 6. Cấu hình hai RestClient trong cùng caller

Tạo `CatalogClientConfiguration.java`:

~~~java
package com.example.orders;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;

@Configuration(proxyBeanMethods = false)
public class CatalogClientConfiguration {

    // A: RestClient thường gọi URL vật lý.
    @Bean("catalogDirectClient")
    RestClient catalogDirectClient(
            @Value("${demo.catalog.direct-url}") String url) {
        return RestClient.builder()
                .baseUrl(url)
                .build();
    }

    // B: Builder được Spring Cloud LoadBalancer tùy biến.
    @Bean("catalogLoadBalancedBuilder")
    @LoadBalanced
    RestClient.Builder catalogLoadBalancedBuilder() {
        return RestClient.builder();
    }

    @Bean("catalogServiceClient")
    RestClient catalogServiceClient(
            @Qualifier("catalogLoadBalancedBuilder")
            RestClient.Builder builder) {
        return builder
                .baseUrl("http://catalog-service")
                .build();
    }
}
~~~

**Khác biệt quan trọng nằm ở builder**, không nằm ở tên biến `directClient` hoặc `serviceClient`:

- `catalogDirectClient` được tạo từ `RestClient.builder()` thông thường với URL 8081.
- `catalogServiceClient` dùng `RestClient.Builder` có `@LoadBalanced` và hostname service ID.
- `@Qualifier` theo tên bean tránh inject nhầm client khi có nhiều bean cùng kiểu.

Ở project dùng nhiều customizer Spring Boot cho observability, encoding hay SSL, cân nhắc `RestClientBuilderConfigurer`/builder được Boot quản lý theo version, thay vì dùng builder thô như lab tối giản.

### Điều không nên làm

~~~java
// Không phải "direct" nếu builder đang được @LoadBalanced:
RestClient wrongDirect = catalogLoadBalancedBuilder
        .baseUrl("http://127.0.0.1:8081")
        .build();
~~~

Khi LoadBalancer interceptor đã gắn, hostname `127.0.0.1` có thể bị diễn giải như **service ID** cần resolve, dẫn đến lỗi không có instance. Để gọi URL vật lý, sử dụng client **không load-balanced**.

Ngược lại:

~~~java
// Chỉ là RestClient thường, không tự chọn ServiceInstance.
RestClient ordinary = RestClient.create("http://catalog-service");
~~~

`ordinary` có thể gửi hostname qua DNS và hoạt động nếu môi trường có DNS record; kết quả đó **không chứng minh** Spring Cloud LoadBalancer đang chạy.

## 7. Controller đặt hai cách gọi cạnh nhau

Tạo `ComparisonController.java`:

~~~java
package com.example.orders;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.client.RestClient;

@RestController
@RequestMapping("/compare")
public class ComparisonController {

    private final RestClient directClient;
    private final RestClient serviceClient;

    public ComparisonController(
            @Qualifier("catalogDirectClient")
            RestClient directClient,
            @Qualifier("catalogServiceClient")
            RestClient serviceClient) {
        this.directClient = directClient;
        this.serviceClient = serviceClient;
    }

    @GetMapping("/direct/{id}")
    public CatalogItem direct(@PathVariable long id) {
        return directClient.get()
                .uri("/api/products/{id}", id)
                .retrieve()
                .body(CatalogItem.class);
    }

    @GetMapping("/service/{id}")
    public CatalogItem byServiceName(@PathVariable long id) {
        return serviceClient.get()
                .uri("/api/products/{id}", id)
                .retrieve()
                .body(CatalogItem.class);
    }
}
~~~

Hai endpoint giống nhau về kiểu HTTP, path backend và JSON DTO. **Khác biệt duy nhất có chủ đích** là client được inject:

~~~text
GET /compare/direct/42
  -> direct RestClient
  -> http://127.0.0.1:8081/api/products/42

GET /compare/service/42
  -> @LoadBalanced RestClient
  -> LoadBalancer chọn ServiceInstance
  -> http://127.0.0.1:8081 hoặc :8082/api/products/42
~~~

Nếu backend trả JSON không hợp lệ, cả hai client đều có thể gặp lỗi decoder. Lỗi đó thuộc HTTP contract, không chứng minh rằng LoadBalancer đã hoặc chưa chọn được instance.

## 8. Khởi động ba tiến trình

Với project Gradle có cấu hình plugin/BOM hợp lệ, mở **ba terminal riêng**.

**Terminal 1 — catalog A**

~~~powershell
./gradlew :catalog-service:bootRun --args="--server.port=8081 --demo.instance-id=catalog-a"
~~~

**Terminal 2 — catalog B**

~~~powershell
./gradlew :catalog-service:bootRun --args="--server.port=8082 --demo.instance-id=catalog-b"
~~~

**Terminal 3 — order-service**

~~~powershell
./gradlew :order-service:bootRun --args="--server.port=8080"
~~~

Nếu dùng jar build sẵn, chạy cùng jar `catalog-service` hai lần với tham số `--server.port` và `--demo.instance-id` tương ứng. Cả hai backend phải còn chạy đồng thời trong lúc thử.

Trên Windows PowerShell, dùng `curl.exe` để tránh nhầm với alias `curl`.

Kiểm tra trực tiếp hai backend:

~~~powershell
curl.exe -s http://127.0.0.1:8081/api/products/42
curl.exe -s http://127.0.0.1:8082/api/products/42
~~~

Đường đầu phải trả `catalog-a`, đường sau trả `catalog-b`. Nếu chưa đạt, hãy kiểm tra port, `demo.instance-id`, ứng dụng có khởi động thành công và các endpoint có cùng path.

## 9. Thí nghiệm A — URL cố định

Gọi caller:

~~~powershell
curl.exe -s http://127.0.0.1:8080/compare/direct/42
~~~

Kết quả kỳ vọng:

~~~json
{
  "id": 42,
  "name": "Product-42",
  "instanceId": "catalog-a",
  "port": 8081
}
~~~

Lặp lại 10 lần:

~~~powershell
1..10 | ForEach-Object {
    (Invoke-RestMethod "http://127.0.0.1:8080/compare/direct/42").instanceId
}
~~~

Với cấu hình URL 8081, các kết quả thành công đều phải đến từ `catalog-a`.

**Bài thử chứng minh:** request của client direct đi tới endpoint vật lý đã định. Nó chưa chứng minh một hostname cố định trong môi trường khác không thể trỏ đến gateway hoặc DNS load balancer.

## 10. Thí nghiệm B — Tên dịch vụ và nhiều instance

Gọi client load-balanced:

~~~powershell
curl.exe -s http://127.0.0.1:8080/compare/service/42
~~~

Lặp lại nhiều lần:

~~~powershell
1..12 | ForEach-Object {
    (Invoke-RestMethod "http://127.0.0.1:8080/compare/service/42").instanceId
}
~~~

Trong một lab không có policy đặc biệt, với hai instance sẵn sàng và thuật toán round-robin thông dụng, kết quả thường bao gồm **cả `catalog-a` và `catalog-b`**.

Ví dụ minh họa:

~~~text
catalog-a
catalog-b
catalog-a
catalog-b
...
~~~

**Không assert lần đầu tiên luôn chọn A**, hoặc 12 request luôn chia đúng 6/6 nếu có concurrency/khác biệt trạng thái. Lựa chọn ban đầu và thứ tự có thể phụ thuộc state của LoadBalancer. Bài kiểm thử có giá trị ở đây là **cả hai backend được quan sát**.

Nếu tất cả request đều trả A, kiểm tra:

- `catalogServiceClient` có thật sự được xây từ `@LoadBalanced RestClient.Builder` không?
- `SimpleDiscoveryClient` đã bind đủ hai URI chưa?
- Có zone/hint, weight, health hoặc custom supplier đang chỉ cung cấp A không?
- Có URL cố định được đặt nhầm ở client gọi service không?
- Backend B có trả đúng instance ID và vẫn sẵn sàng không?

## 11. Bóc tách đường đi của một request

~~~mermaid
sequenceDiagram
    participant U as Người học
    participant O as order-service
    participant LB as BlockingLoadBalancerClient
    participant S as ServiceInstanceListSupplier
    participant HTTP as HTTP transport
    participant B as catalog-b:8082
    U->>O: GET /compare/service/42
    O->>LB: Chọn đích cho catalog-service
    LB->>S: Lấy các ServiceInstance
    S-->>LB: catalog-a, catalog-b
    LB-->>O: catalog-b
    O->>HTTP: Request tới URI vật lý :8082
    HTTP->>B: GET /api/products/42
    B-->>HTTP: JSON instanceId=catalog-b
    HTTP-->>O: CatalogItem
    O-->>U: CatalogItem
~~~

Ba ranh giới phải phân biệt:

1. **Discovery:** trả danh sách `ServiceInstance` cho service ID.
2. **Selection:** dùng round-robin/random/weight/zone hoặc policy khác để chọn một instance.
3. **Transport:** thực hiện DNS (nếu cần), pool, TCP/TLS, gửi request, đọc response.

Một instance được chọn thành công vẫn có thể từ chối kết nối, timeout hoặc trả HTTP 500. Đừng mô tả mọi lỗi HTTP sau selection là “LoadBalancer chọn sai”.

## 12. Thí nghiệm C — Dừng replica A

Dừng tiến trình catalog-service tại port 8081; giữ catalog B và order-service hoạt động.

### Direct URL

~~~powershell
curl.exe -i http://127.0.0.1:8080/compare/direct/42
~~~

Direct client tiếp tục trỏ 8081, nên request thường lỗi kết nối. Vì controller không có custom exception handler, lỗi downstream có thể được ứng dụng caller biểu diễn thành HTTP 500. **Không khẳng định chắc chắn status HTTP đối với caller bằng một mã cụ thể**, vì nó phụ thuộc cách xử lý exception của ứng dụng.

### Service ID

~~~powershell
1..8 | ForEach-Object {
    try {
        (Invoke-RestMethod "http://127.0.0.1:8080/compare/service/42").instanceId
    } catch {
        "FAILED"
    }
}
~~~

**Điểm quan trọng:** YAML của `SimpleDiscoveryClient` vẫn chứa cả A và B. Với LB retry đã tắt và danh sách không đổi, các request chọn A có thể lỗi, còn các request chọn B thành công.

| Đường gọi | A dừng, B còn sống |
|---|---|
| Direct tới 8081 | Gọi tới A thất bại |
| Service ID, danh sách tĩnh còn A/B | Có thể vừa lỗi vừa thành công tùy instance được chọn |
| Service ID, nguồn danh sách chỉ còn B | Chọn B và thành công nếu B khỏe |

Đây không phải bằng chứng LoadBalancer “không có ích”. Nó minh họa giới hạn của **dữ liệu discovery stale**: chọn instance chỉ tốt bằng danh sách mà supplier cung cấp.

## 13. Thí nghiệm D — Thay đổi danh sách discovery

Giữ A đã dừng, chỉnh cấu hình `order-service/application.yml` trong **project lab** để danh sách chỉ còn B:

~~~yaml
spring:
  cloud:
    discovery:
      client:
        simple:
          instances:
            catalog-service:
              - uri: http://127.0.0.1:8082
    loadbalancer:
      cache:
        enabled: false
      retry:
        enabled: false
~~~

Giữ nguyên `demo.catalog.direct-url: http://127.0.0.1:8081`. **Khởi động lại caller** để chắc chắn cấu hình tĩnh được áp dụng; không giả định YAML tự hot reload.

Lặp lại hai đường:

~~~powershell
curl.exe -i http://127.0.0.1:8080/compare/direct/42

1..8 | ForEach-Object {
    (Invoke-RestMethod "http://127.0.0.1:8080/compare/service/42").instanceId
}
~~~

Kỳ vọng:

- Đường direct tiếp tục lỗi vì vẫn trỏ A.
- Đường service ID chỉ chọn B và thành công.

**Lợi ích của service ID:** caller không cần hardcode “B” vào mỗi phương thức gọi; việc chọn endpoint phụ thuộc nguồn instance. Với registry động (Eureka/Consul), membership có thể cập nhật qua heartbeat/registration/deregistration, nhưng vẫn có độ trễ do cache và health check; không có bảo đảm failover tức thời.

## 14. Thí nghiệm E — Service ID khác với DNS

Hai dòng sau cùng có `http://catalog-service` nhưng **không giống nhau**:

~~~java
// Có @LoadBalanced builder:
RestClient springLbClient = catalogLoadBalancedBuilder
        .baseUrl("http://catalog-service")
        .build();

// Không có LoadBalancer interceptor:
RestClient dnsClient = RestClient.create("http://catalog-service");
~~~

| Client | Cách giải quyết hostname |
|---|---|
| `springLbClient` | Spring Cloud LoadBalancer dùng `catalog-service` làm service ID |
| `dnsClient` | HTTP transport/DNS xử lý hostname thông thường |
| `dnsClient` trên laptop không có record DNS | Có thể gặp `UnknownHostException` |
| `dnsClient` trong Kubernetes có Service DNS | Có thể hoạt động qua ClusterIP/mesh **mà không dùng Spring Cloud LB** |

Không dùng “gọi được bằng tên dịch vụ” làm bằng chứng rằng client-side LoadBalancer đang hoạt động. Phải xem **bean, interceptor/filter, danh sách candidate và instance được chọn**.

Với Kubernetes/service mesh, hai kiến trúc đều hợp lệ:

1. Gọi service DNS/ClusterIP và để hạ tầng phân phối.
2. Sử dụng Spring Cloud LoadBalancer và discovery để chọn `ServiceInstance` ngay ở caller.

Tránh vô tình chồng nhiều tầng load balancing khi không cần và không hiểu ranh giới của từng tầng.

## 15. Cùng một nguyên tắc với WebClient và OpenFeign

### WebClient

~~~java
@Configuration(proxyBeanMethods = false)
class CatalogReactiveClientConfiguration {

    @Bean
    @LoadBalanced
    WebClient.Builder loadBalancedWebClientBuilder() {
        return WebClient.builder();
    }

    @Bean
    WebClient directWebClient() {
        return WebClient.builder()
                .baseUrl("http://127.0.0.1:8081")
                .build();
    }

    @Bean
    WebClient serviceWebClient(
            @LoadBalanced WebClient.Builder builder) {
        return builder
                .baseUrl("http://catalog-service")
                .build();
    }
}
~~~

Đoạn code này lược bỏ imports và giả định đã thêm Spring WebFlux cùng dependency LoadBalancer tương thích. `WebClient` dùng LoadBalancer exchange filter trong đường service, còn direct client không được gắn filter.

### OpenFeign

~~~java
@FeignClient(name = "catalog-service")
interface CatalogFeignByName {
    @GetMapping("/api/products/{id}")
    CatalogItem findById(@PathVariable("id") long id);
}

@FeignClient(
        contextId = "catalogDirectFeign",
        name = "catalog-service",
        url = "http://127.0.0.1:8081")
interface CatalogFeignDirect {
    @GetMapping("/api/products/{id}")
    CatalogItem findById(@PathVariable("id") long id);
}
~~~

Muốn dùng Feign cần starter OpenFeign, `@EnableFeignClients`, và starter LoadBalancer nếu muốn tích hợp chọn instance theo name. **Feign có `url` cố định sẽ đi trực tiếp**; không qua LoadBalancer selection theo service ID cho client đó. Kiểm tra cả cấu hình URL trong properties vì chúng cũng có thể làm Feign bỏ qua LoadBalancer.

Không đồng nhất transport của Feign với Spring Cloud LoadBalancer: HTTP pool, read timeout và retry vẫn là các concern riêng.

## 16. URL cố định không phải lúc nào cũng sai

Direct URL có thể phù hợp khi đích là:

- Một API bên ngoài có hostname ổn định và cơ chế cân bằng tải do nhà cung cấp quản lý.
- Một gateway/reverse proxy làm điểm vào chung.
- Một endpoint admin/health/debug cần chỉ rõ đúng một replica.
- Một dịch vụ đơn lẻ hoặc bài thử cần cố định host để tái hiện vấn đề.

Service ID đặc biệt có ích khi:

- Caller phải lựa chọn trong nhiều replica thay đổi theo discovery.
- Cần chính sách round-robin, weighted, zone/hint hoặc filter.
- Việc quản lý endpoint muốn được tách khỏi mã nghiệp vụ.
- Cần quan sát theo service ID và biết instance nào đã được chọn.

Nên hỏi: **“URL cố định tới instance cuối, hay tới virtual IP/gateway có load balancing riêng?”** Một URL hostname cố định vẫn có thể ẩn phía sau một cụm nhiều server.

## 17. Retry, health check và timeout không tự xuất hiện khi đổi URL

Một kỳ vọng sai phổ biến là chỉ cần đổi từ `http://127.0.0.1:8081` sang `http://catalog-service` sẽ tự có failover.

| Thành phần | Direct URL | Service ID qua LoadBalancer |
|---|---|---|
| Connect/read timeout | HTTP transport quyết định | HTTP transport vẫn quyết định sau khi chọn instance |
| Connection pool | Theo địa chỉ/route của HTTP client | Theo endpoint vật lý đã chọn |
| Retry | HTTP/resilience policy | Có thể thêm LB retry nếu được bật/cấu hình |
| Health check | Cơ chế riêng hoặc phía hạ tầng | Có thể dùng health supplier khi cấu hình |
| Circuit breaker | Cần cấu hình riêng | Vẫn cần cấu hình riêng |
| Discovery cache | Không cần tra service ID | Có thể có cache riêng và stale entries |
| Graceful shutdown | Backend/hạ tầng phối hợp | Vẫn cần backend/discovery/cache phối hợp |

Trong lab, `spring.cloud.loadbalancer.retry.enabled=false` được đặt rõ để một request logic tương ứng một attempt không bị LB tự retry. Nếu bật retry về sau, cần kiểm tra:

- Retry cùng instance hay instance khác.
- Lỗi/status nào được retry.
- Backoff, timeout tổng, giới hạn số attempts.
- Request body có replay được không, đặc biệt với upload/streaming.
- Tính idempotency của POST/PUT.

**Retry không làm `SimpleDiscoveryClient` tự cập nhật danh sách.** Nếu nguồn tĩnh vẫn chứa A, vẫn cần policy hoặc nguồn discovery cập nhật mới loại bỏ hoàn toàn A.

## 18. Kiểm thử tự động thay cho quan sát thủ công

Một integration test nên khởi chạy **hai fake HTTP servers ở cổng động**, rồi truyền URI thực của chúng cho `SimpleDiscoveryClient` bằng `@DynamicPropertySource`. Test chạy cả hai bean RestClient trong Spring context thật.

Ví dụ những assertion cần có:

~~~java
// Đây là helper minh họa trong integration test,
// không phải một @SpringBootTest độc lập hoàn chỉnh.
static void assertRouting(
        RestClient directClient,
        RestClient serviceClient) {

    for (int i = 0; i < 5; i++) {
        CatalogItem direct = directClient.get()
                .uri("/api/products/{id}", 42)
                .retrieve()
                .body(CatalogItem.class);

        assertEquals("catalog-a", direct.instanceId());
    }

    Set<String> observed = new HashSet<>();

    for (int i = 0; i < 12; i++) {
        CatalogItem item = serviceClient.get()
                .uri("/api/products/{id}", 42)
                .retrieve()
                .body(CatalogItem.class);
        observed.add(item.instanceId());
    }

    assertEquals(Set.of("catalog-a", "catalog-b"), observed);
}
~~~

Đoạn mã giả định `assertEquals` và `Set`/`HashSet` từ JUnit/Java đã import. Trong test hoàn chỉnh cần khởi chạy backend fake trước khi tạo Spring context, inject hai RestClient đúng tên và đóng server sau khi test. Giữ retry/cache theo đúng điều kiện test, tránh context reuse với các URI đã ngừng hoạt động.

**Unit test** của `ServiceInstanceListSupplier` có thể chứng minh tập ứng viên đúng, nhưng không chứng minh `@LoadBalanced` đã gắn vào HTTP client. Ngược lại, vài request integration thành công chưa chứng minh hệ thống chịu tải hoặc failover ổn định khi scale.

### Ma trận kiểm thử

| Kịch bản | Direct URL | Service ID + LB |
|---|---|---|
| Hai backend chạy | Chỉ A | Có thể tới A và B |
| Đổi direct URL sang B | Chỉ B | Không đổi nếu discovery giữ nguyên |
| Discovery chỉ còn B | Vẫn theo direct URL | Chỉ chọn B |
| Discovery rỗng | Không phụ thuộc list | Không có instance để chọn |
| A dừng nhưng discovery còn A/B | Gọi A lỗi | Một số attempts có thể lỗi |
| HTTP 200 JSON sai kiểu | Decoder có thể lỗi | Decoder cũng có thể lỗi |
| Connect/read timeout | Thuộc HTTP transport | Thuộc HTTP transport sau selection |
| Không gắn `@LoadBalanced` | Không ảnh hưởng direct | Host logic có thể bị resolve qua DNS |
| Thêm retry | Phụ thuộc transport/resilience | Phụ thuộc LB/transport/resilience policy |

## 19. Ghi nhận quan sát và chẩn đoán lỗi

Ghi bảng sau **bằng số đo thật** từ máy thử:

| Lượt | Đường | Instance list | Backend nhận | Status | Latency | Nhận xét |
|---|---|---|---|---|---|---|
| A1 | Direct | A/B | A | Tự đo | Tự đo | Endpoint cố định |
| B1 | Service ID | A/B | A hoặc B | Tự đo | Tự đo | Có selection |
| C1 | Direct, A dừng | A/B | Không trả lời | Tự đo | Tự đo | Direct vẫn trỏ A |
| C2 | Service, A dừng | A/B | B hoặc thất bại ở A | Tự đo | Tự đo | Nguồn tĩnh stale |
| D1 | Service, chỉ B | B | B | Tự đo | Tự đo | Discovery thay đổi |
| D2 | Direct, vẫn A | B | Không trả lời | Tự đo | Tự đo | Không dùng discovery |

Không điền những con số thời gian hay tỷ lệ lỗi ước lượng thành kết quả thực tế. Với ứng dụng có observability, nên ghi:

- `serviceId`, route template và loại thao tác.
- `instanceId` hoặc identifier hạ tầng được phép.
- HTTP status, elapsed time và error category.
- `NO_INSTANCE`, `CONNECT_FAILURE`, `READ_TIMEOUT`, `DECODE_FAILURE`.
- Retry attempt, nếu policy thực sự bật.
- `traceId` giúp đối chiếu log caller/backend.

Không log nguyên `Authorization`, `Cookie`, raw URL có query, body nhạy cảm hoặc exception message chưa được kiểm soát.

## 20. Các lỗi thường gặp

| Triệu chứng | Khả năng | Cách chẩn đoán |
|---|---|---|
| Direct/service đều chỉ trả A | Builder service không có LB; discovery chỉ thấy A; policy chỉ chọn A | Kiểm tra bean, candidate list, instance ID |
| `UnknownHostException: catalog-service` | Gọi bằng RestClient thường, không gắn LB | Kiểm tra `@LoadBalanced` và dependency |
| `No instances available` | Sai service ID hoặc discovery/supplier rỗng | Kiểm tra property và metadata |
| Client dùng LB với URL `127.0.0.1` bị no-server | IP bị coi là service ID | Dùng builder thường cho direct |
| A đã dừng nhưng vẫn bị chọn | Static discovery hoặc cache stale | Loại A khỏi list, refresh/discovery health |
| Hai backend trả cùng `instanceId` | Tham số startup sai | Kiểm tra từng terminal |
| Trùng port khi khởi động | 8080/8081/8082 đã dùng | Đổi port và cập nhật URI |
| Docker không gọi được localhost backend | Khác network namespace | Dùng hostname/container network |
| URL service ID vẫn chạy khi thiếu LB | DNS/mesh xử lý hostname | Kiểm tra interceptor/filter và network path |
| YAML sửa nhưng đường đi không đổi | Context chưa reload hoặc cache cũ | Restart caller, xác minh config |
| Instance được chọn nhưng request timeout | Lỗi HTTP transport/backend | Kiểm tra selected URI và phase latency |
| OpenFeign chỉ dùng một IP | Có `url` trong annotation/properties | Bỏ URL nếu muốn chọn theo service name |

**Chẩn đoán theo thứ tự:** đã có danh sách `ServiceInstance` → chọn được instance → kết nối tới URI vật lý → nhận HTTP response → decode và validate body. Không sửa lỗi network bằng cách tăng cache TTL, hoặc sửa lỗi JSON contract bằng cách đổi thuật toán round-robin.

## 21. Bài tập mở rộng

**Bài 1 — URL qua biến môi trường.** Đổi property direct thành:

~~~yaml
demo:
  catalog:
    direct-url: ${CATALOG_DIRECT_URL:http://127.0.0.1:8081}
~~~

Chạy caller với biến `CATALOG_DIRECT_URL` trỏ tới 8082. Dự đoán direct chuyển sang B, còn service ID vẫn dùng instance list.

**Bài 2 — Thêm replica C.** Khởi chạy catalog ở 8083, thêm vào `SimpleDiscoveryClient`, restart caller và quan sát service ID có thể gọi cả ba, trong khi direct không tự gọi C.

**Bài 3 — Weighted selection.** Thêm metadata `weight` và áp dụng supplier weighted đúng version. Đo phân phối trên nhiều lượt. Không khẳng định chính xác tỉ lệ trên một số ít request.

**Bài 4 — Health check và graceful shutdown.** Thử supplier health hoặc registry động; đo thời gian instance bị loại khỏi candidate list. Phân biệt health/cache với idle sockets trong HTTP pool.

**Bài 5 — Load test qua caller.** Dùng k6 hoặc công cụ tương đương gửi tải vào `/compare/service/42`, **không gọi thẳng backend** nếu muốn đo lựa chọn của Spring Cloud LoadBalancer. Theo dõi số request mỗi replica, p95/p99, lỗi và pool.

## 22. Checklist nghiệm thu

1. Hai tiến trình `catalog-service` thật sự chạy với `instanceId` khác nhau?
2. `order-service` có hai RestClient độc lập, một direct và một load-balanced?
3. Có dependency `spring-cloud-starter-loadbalancer` và `@LoadBalanced RestClient.Builder` đúng bean?
4. `SimpleDiscoveryClient` định nghĩa đúng service ID `catalog-service` và hai URI?
5. Đường `/compare/direct/42` gọi lặp lại chỉ trả A?
6. Đường `/compare/service/42` có thể trả cả A/B khi cùng khỏe?
7. Khi A dừng, đã giải thích vì sao static discovery vẫn chứa A?
8. Khi chỉ giữ B trong list và restart caller, service ID chỉ gọi B dù direct vẫn trỏ A?
9. Đã phân biệt service ID do Spring Cloud giải quyết và hostname DNS/service mesh?
10. Đã kiểm tra timeout/retry/health không tự được bật chỉ bằng cách thay URL?
11. Đã ghi bảng kiểm kết quả thật, không giả lập số liệu?
12. Có cách biến các bước kiểm chứng thành integration test cổng động và không phụ thuộc thứ tự round-robin?

**Kết luận:** URL vật lý và service ID không phải hai cách viết cùng một kiểu địa chỉ. Với **RestClient trực tiếp**, caller xác định endpoint cần gọi. Với **RestClient được xây từ `@LoadBalanced RestClient.Builder`**, caller cung cấp **service ID**, còn Spring Cloud LoadBalancer chọn `ServiceInstance` trước khi HTTP transport gửi request. Việc hiểu và kiểm chứng ranh giới này là nền tảng để xử lý đúng scaling, registry cache, một replica chết, retry, timeout và các chính sách định tuyến trong hệ thống microservices.

**Tài liệu tham khảo chính thức:**

- [Spring Cloud Commons – RestClient as a LoadBalancer Client](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html)
- [Spring Cloud Commons – Spring Cloud LoadBalancer, discovery và caching](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html)
- [Spring Framework – REST Clients](https://docs.spring.io/spring-framework/reference/integration/rest-clients.html)
- [Spring Cloud OpenFeign – Declarative HTTP Client](https://docs.spring.io/spring-cloud-openfeign/reference/spring-cloud-openfeign.html)

