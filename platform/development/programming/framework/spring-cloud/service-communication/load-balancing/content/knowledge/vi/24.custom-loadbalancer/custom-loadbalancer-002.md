# Viết ServiceInstanceListSupplier cho nguồn bản sao riêng

Khi dùng Spring Cloud LoadBalancer, thông thường danh sách `ServiceInstance` được lấy từ `DiscoveryClient` (Eureka, Consul, Kubernetes hoặc cơ chế discovery tương thích). Tuy nhiên, một số hệ thống sử dụng **nguồn danh sách bản sao riêng**: API quản lý topology nội bộ, dữ liệu do control plane sinh ra, inventory service chuyên biệt, hoặc danh sách động do một hệ thống không tích hợp `DiscoveryClient` cung cấp.

Thay vì viết một thuật toán cân bằng tải hoàn toàn mới, có thể triển khai **`ServiceInstanceListSupplier`** để biến dữ liệu từ nguồn riêng thành `List<ServiceInstance>`. Spring Cloud LoadBalancer vẫn đảm nhiệm phần **chọn một instance** từ danh sách đó (ví dụ Round Robin), còn RestClient, WebClient hoặc OpenFeign tiếp tục gọi bằng **service ID**.

Bài thuộc chương **Tùy biến LoadBalancer** của module **SPRING_CLOUD_SERVICE_COMMUNICATION_LOAD_BALANCING**. Mục tiêu là hiểu hợp đồng của `ServiceInstanceListSupplier`, tự viết supplier lấy instance qua HTTP, tích hợp vào context theo service ID, kiểm soát chất lượng dữ liệu, cache/health check, timeout, retry và observability. Ví dụ dùng Java 17+, Spring Boot/Spring Cloud tương thích và một nguồn HTTP **độc lập với LoadBalancer**.

> **Ranh giới trách nhiệm:** `ServiceInstanceListSupplier` cung cấp **tập ứng viên**, không tự quyết định instance nào được chọn cho request. Nếu chỉ muốn đổi Round Robin thành một chính sách lựa chọn khác, hãy cân nhắc tùy biến `ReactorServiceInstanceLoadBalancer` thay vì đặt logic chọn một instance trong supplier.

## 1. Khi nào cần tự viết ServiceInstanceListSupplier?

Một nguồn riêng có thể là:

- API quản trị tự xây, lưu các bản sao đang được phép nhận traffic.
- Control plane triển khai dịch vụ không có adapter `DiscoveryClient`.
- Endpoint trả về topology theo môi trường, cụm, vùng hoặc phiên bản.
- Danh sách instance được chuẩn hóa từ nhiều hệ thống inventory.
- Một nguồn có thông tin bổ sung như `zone`, `weight` và `version` nhưng chưa có Spring Cloud Discovery integration.

**Không cần custom supplier** nếu đã có `DiscoveryClient` phù hợp và chỉ muốn lọc instance theo zone, health, request hint hoặc weight: Spring Cloud có các supplier/decorator tích hợp cho những mục tiêu này. Không nên tạo thêm nguồn dữ liệu thứ hai nếu registry hiện tại đã là nguồn sự thật đáng tin.

### Một câu hỏi kiến trúc

Nếu hệ thống có hàng trăm dịch vụ, custom `DiscoveryClient` có thể thích hợp hơn khi bạn muốn mọi thành phần Spring Cloud Discovery đều dùng được nguồn mới. **Custom `ServiceInstanceListSupplier`** phù hợp hơn khi chỉ một số **LoadBalancer clients** cần dùng topology riêng, hoặc bạn muốn giới hạn thay đổi vào đúng service ID.

| Tiêu chí | Custom DiscoveryClient | Custom ServiceInstanceListSupplier |
|---|---|---|
| Phạm vi | Tích hợp chung vào discovery abstraction | Phục vụ khâu cung cấp ứng viên cho LoadBalancer |
| Khả năng dùng ở thành phần khác | Có thể được nhiều consumer của DiscoveryClient dùng | Chủ yếu trong LoadBalancer supplier chain |
| Chọn áp dụng theo service ID | Qua logic discovery hoặc cấu hình | Dễ dùng `@LoadBalancerClient(name=...)` |
| Nguồn dữ liệu | Registry hoặc hệ thống discovery riêng | Registry, API, snapshot hoặc aggregator |
| Có quyết định Round Robin không? | Không | Không |

## 2. Chuỗi xử lý từ nguồn riêng đến HTTP client

~~~mermaid
flowchart LR
    S["Topology API / nguồn bản sao riêng"] --> F["Custom ServiceInstanceListSupplier"]
    F --> C["Cache / health / zone / weight decorators tùy chọn"]
    C --> LB["RoundRobinLoadBalancer hoặc chính sách khác"]
    LB --> I["Chọn ServiceInstance"]
    I --> HTTP["RestClient / WebClient / OpenFeign"]
    HTTP --> B["Instance thực tế host:port"]

    Caller["Caller gọi http://catalog-service/..."] --> LB
~~~

Mối quan hệ có thể tóm tắt:

1. Caller tạo HTTP request với URL logic `http://catalog-service/api/items/42`.
2. Spring Cloud LoadBalancer nhận service ID `catalog-service`.
3. Supplier trả về **danh sách ứng viên** tương ứng với ID đó.
4. Chính sách chọn instance lấy một phần tử hợp lệ.
5. HTTP client thực hiện kết nối tới host/port thật của instance được chọn.
6. Response hoặc exception được chuyển về caller; supplier không thay thế status/timeout handling của HTTP client.

**Một HTTP request không nhất thiết tạo một truy vấn mạng mới tới topology API:** điều đó phụ thuộc cache, refresh và cách triển khai supplier. Nếu không có cache, một supplier gọi HTTP trên mỗi lần lựa chọn có thể trở thành nút nghẽn.

## 3. Hợp đồng cốt lõi của ServiceInstanceListSupplier

Interface thuộc package:

~~~java
org.springframework.cloud.loadbalancer.core.ServiceInstanceListSupplier
~~~

Hai phương thức cần hiểu:

~~~java
String getServiceId();

Flux<List<ServiceInstance>> get();
~~~

Ngoài ra, API có phương thức nhận request context như `get(Request request)` để những supplier có logic phụ thuộc request có thể sử dụng. Bài học xây dựng supplier **không phụ thuộc request**, nên chỉ cần triển khai `get()` và `getServiceId()` theo interface hiện hành.

**Điểm đặc biệt là kiểu trả về `Flux<List<ServiceInstance>>`, không phải `Flux<ServiceInstance>`.**

~~~text
Đúng:  onNext([A, B, C])      -> một snapshot danh sách ứng viên
Sai:   onNext(A), onNext(B)   -> từng phần tử riêng lẻ
~~~

Một subscription có thể nhận một danh sách rồi hoàn tất; một supplier khác có thể phát nhiều danh sách khi nguồn topology thay đổi. Với bài thực hành, **mỗi lần subscribe sẽ phát một snapshot và hoàn tất**.

| Giá trị/tín hiệu | Nghĩa cần hiểu |
|---|---|
| `Flux.just(List.of(A, B))` | Có hai ứng viên |
| `Flux.just(List.of())` | Snapshot hợp lệ nhưng không có ứng viên |
| `Flux.error(ex)` | Không lấy hoặc không xác thực được snapshot |
| `Flux.empty()` | Publisher hoàn tất mà **không phát snapshot nào** |
| `Flux.never()` | Không phát/không hoàn tất; có thể làm treo bước lựa chọn |

Không thay `Flux.just(List.of())` bằng `Flux.empty()` một cách tùy tiện: “có snapshot rỗng” và “không có snapshot” không phải tín hiệu giống nhau đối với mọi consumer.

### ServiceInstance gồm gì?

Một `ServiceInstance` tối thiểu có những thông tin quan trọng:

- `getServiceId()`: tên logic, phải khớp `catalog-service`.
- `getInstanceId()`: định danh ổn định trong phạm vi hợp đồng.
- `getHost()` và `getPort()`: nơi gửi HTTP request.
- `isSecure()` / `getUri()`: giao thức và thông tin URL.
- `getMetadata()`: map dữ liệu như zone, weight, version.

Có thể dùng `DefaultServiceInstance` để ánh xạ dữ liệu thay vì tự viết đầy đủ implementation của `ServiceInstance`.

## 4. Thiết kế nguồn riêng cho bài thực hành

Giả sử có topology API độc lập tại:

~~~text
GET http://127.0.0.1:18100/api/v1/services/catalog-service/instances
~~~

Response của nguồn:

~~~json
{
  "serviceId": "catalog-service",
  "instances": [
    {
      "id": "catalog-a",
      "host": "127.0.0.1",
      "port": 18081,
      "secure": false,
      "zone": "zone-a",
      "weight": 50
    },
    {
      "id": "catalog-b",
      "host": "127.0.0.1",
      "port": 18082,
      "secure": false,
      "zone": "zone-b",
      "weight": 50
    }
  ]
}
~~~

Đây là **hợp đồng JSON ví dụ**, không phải định dạng tiêu chuẩn của Eureka/Kubernetes. Đội tự xây topology API phải chịu trách nhiệm kiểm soát access, độ mới của dữ liệu và ngữ nghĩa trạng thái instance.

Trong lab:

| Thành phần | Địa chỉ | Vai trò |
|---|---|---|
| Topology API | `127.0.0.1:18100` | Cung cấp snapshot danh sách |
| catalog-a | `127.0.0.1:18081` | Backend A |
| catalog-b | `127.0.0.1:18082` | Backend B |
| order-service | `127.0.0.1:18090` | Caller dùng LoadBalancer |

**Chỉ sử dụng HTTP loopback cho lab.** Trong production, nguồn registry phải được xác thực, mã hóa và phân quyền, còn địa chỉ instance phải được kiểm tra bằng chính sách độc lập; không lấy URI trực tiếp từ dữ liệu người dùng rồi dùng để kết nối.

## 5. Dependency cần có

Ví dụ Gradle (Groovy DSL), dự án quản lý version bằng Spring Boot/Spring Cloud BOM tương thích:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.cloud:spring-cloud-starter-loadbalancer'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}
~~~

Ở đây:

- `spring-boot-starter-web` phục vụ caller MVC/lab HTTP controller và RestClient.
- `spring-boot-starter-webflux` cung cấp WebClient dùng để gọi topology API **bất đồng bộ**.
- `spring-cloud-starter-loadbalancer` cung cấp LoadBalancer và supplier API.
- `reactor-test` dùng cho ví dụ `StepVerifier` ở phần kiểm thử.

**Không bắt buộc một dự án production phải dùng cả MVC và WebFlux cho inbound requests.** Trong bài này, `WebClient` chỉ là HTTP client của topology lookup và có thể dùng trong ứng dụng MVC. Nếu nguồn dữ liệu của bạn đã có reactive SDK, có thể thay WebClient bằng SDK đó.

## 6. Biểu diễn DTO của topology API

Tạo các record trong module caller, package `demo.lbconfig`:

~~~java
package demo.lbconfig;

import java.util.List;

public record DirectorySnapshot(
    String serviceId,
    List<DirectoryNode> instances
) {
}
~~~

~~~java
package demo.lbconfig;

public record DirectoryNode(
    String id,
    String host,
    int port,
    boolean secure,
    String zone,
    int weight
) {
}
~~~

Khi dùng Spring Boot/Jackson tương thích, JSON ở phần 4 có thể được giải mã thành các record đó.

DTO phải được **validate trước khi biến thành `ServiceInstance`**. Những giá trị như port âm, host ngoài policy, trùng instance ID hoặc không khớp service ID không nên được đưa thẳng tới thuật toán cân bằng tải.

### Tách abstraction của nguồn khỏi HTTP client

~~~java
package demo.lbconfig;

import reactor.core.publisher.Mono;

@FunctionalInterface
public interface InstanceDirectory {
    Mono<DirectorySnapshot> find(String serviceId);
}
~~~

Lợi ích của interface nhỏ này: supplier không cần biết dữ liệu tới từ HTTP, database hay một mock; nó chỉ cần một `Mono<DirectorySnapshot>`. Unit test có thể cung cấp `InstanceDirectory` giả mà không khởi động web server.

## 7. Gọi nguồn riêng bằng WebClient **không** load-balanced

Một lỗi thiết kế dễ gây vòng lặp là tạo WebClient gọi topology API từ một `@LoadBalanced WebClient.Builder`, trong khi chính LoadBalancer cần supplier để biết đích của topology API.

~~~mermaid
flowchart TD
    A["Caller cần catalog-service"] --> B["LoadBalancer chọn instance"]
    B --> C["Custom supplier gọi topology API"]
    C --> D{"Topology API cũng đi qua cùng LoadBalancer?"}
    D -->|Có, sai cấu hình| E["Nguy cơ lookup đệ quy, không có dữ liệu để chọn"]
    D -->|Không, dùng client trực tiếp| F["Đọc danh sách rồi trả ServiceInstance"]
    F --> B
~~~

Dùng một WebClient **trực tiếp**, có base URL cố định đã được tin cậy cho control plane:

~~~java
package demo.lbconfig;

import java.time.Duration;

import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

public final class HttpInstanceDirectory implements InstanceDirectory {

    private final WebClient webClient;

    public HttpInstanceDirectory(WebClient webClient) {
        this.webClient = webClient;
    }

    @Override
    public Mono<DirectorySnapshot> find(String serviceId) {
        return webClient.get()
            .uri("/api/v1/services/{id}/instances", serviceId)
            .retrieve()
            .bodyToMono(DirectorySnapshot.class)
            .switchIfEmpty(Mono.error(
                new IllegalStateException("Empty topology response")
            ))
            .timeout(Duration.ofSeconds(2));
    }
}
~~~

Cơ chế này trả về publisher và không chặn thread bằng `block()`. Nó cũng không retry vô hạn khi topology API lỗi. Đối với sản xuất, cần cấu hình connection pool, connect timeout, TLS identity, client authentication, response size limits và deadline phù hợp.

**Tránh viết:**

~~~java
// Không nên trong get() của reactive supplier:
DirectorySnapshot snapshot = directory.find(serviceId).block();
~~~

Việc `block()` trong pipeline reactive có thể gây nghẽn event-loop hoặc deadlock. Dùng các toán tử Reactor để ánh xạ danh sách, không chuyển sang blocking chỉ vì logic chuẩn hóa dữ liệu thuận tiện hơn.

## 8. Viết supplier ánh xạ bản sao riêng sang ServiceInstance

Triển khai `CatalogDirectorySupplier` trong cùng package `demo.lbconfig`:

~~~java
package demo.lbconfig;

import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Objects;
import java.util.Set;

import org.springframework.cloud.client.DefaultServiceInstance;
import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.loadbalancer.core.ServiceInstanceListSupplier;

import reactor.core.publisher.Flux;

public final class CatalogDirectorySupplier
        implements ServiceInstanceListSupplier {

    public static final String SERVICE_ID = "catalog-service";

    private final InstanceDirectory directory;

    public CatalogDirectorySupplier(InstanceDirectory directory) {
        this.directory = Objects.requireNonNull(directory);
    }

    @Override
    public String getServiceId() {
        return SERVICE_ID;
    }

    @Override
    public Flux<List<ServiceInstance>> get() {
        return Flux.defer(() ->
            directory.find(SERVICE_ID)
                .map(this::validateAndConvert)
                .flux()
        );
    }

    private List<ServiceInstance> validateAndConvert(
            DirectorySnapshot snapshot) {

        if (snapshot == null
                || !SERVICE_ID.equals(snapshot.serviceId())
                || snapshot.instances() == null) {
            throw new IllegalArgumentException(
                "Invalid catalog-service snapshot");
        }

        Set<String> seenIds = new HashSet<>();
        List<ServiceInstance> result = new ArrayList<>();

        for (DirectoryNode node : snapshot.instances()) {
            if (!allowedInLab(node)) {
                // Trong production, ghi metric/audit an toàn tại đây.
                continue;
            }

            if (!seenIds.add(node.id())) {
                throw new IllegalArgumentException(
                    "Duplicate instance ID in snapshot");
            }

            DefaultServiceInstance instance = new DefaultServiceInstance(
                node.id(),
                SERVICE_ID,
                node.host(),
                node.port(),
                node.secure()
            );

            instance.getMetadata().put("zone", node.zone());
            instance.getMetadata().put(
                "weight", Integer.toString(node.weight())
            );

            result.add(instance);
        }

        return List.copyOf(result);
    }

    private static boolean allowedInLab(DirectoryNode node) {
        return node != null
            && node.id() != null
            && !node.id().isBlank()
            && "127.0.0.1".equals(node.host())
            && (node.port() == 18081 || node.port() == 18082)
            && !node.secure()
            && node.zone() != null
            && Set.of("zone-a", "zone-b").contains(node.zone())
            && node.weight() >= 1
            && node.weight() <= 100;
    }
}
~~~

### Vì sao chọn kiểu triển khai này?

- `getServiceId()` trả đúng service ID mà LoadBalancer sẽ yêu cầu.
- `get()` trả `Flux<List<ServiceInstance>>`, phát **một snapshot** cho mỗi subscription thành công.
- `Flux.defer(...)` tạo luồng truy xuất mới khi được subscribe; không dùng dữ liệu cố định từ lúc khởi tạo bean.
- `validateAndConvert(...)` kiểm tra snapshot thuộc đúng service ID, danh sách không null, bỏ node không được phép và chặn trùng ID.
- `DefaultServiceInstance` cung cấp implementation `ServiceInstance` sẵn có, tránh phải viết lại `getUri()`, `getHost()`, `getPort()`...
- `List.copyOf(result)` trả danh sách bất biến ở mức collection; không nên sửa metadata của `DefaultServiceInstance` sau khi đã công bố snapshot.
- Khi cả hai backend bị loại, kết quả là **danh sách rỗng** chứ không cố tự kết nối tới một host ngoài policy.

**Đây là chính sách allowlist dành riêng cho lab**: host loopback, cổng 18081/18082 và HTTP. Production phải thay bằng xác minh danh tính nguồn, trust policy, endpoint/network egress và TLS/mTLS phù hợp, không hardcode localhost.

### Một số trường hợp không được che giấu

Nếu nguồn trả `serviceId=payment-service` thay vì `catalog-service`, code phát lỗi. Nếu snapshot bị lỗi cấu trúc hoặc có trùng ID, code phát lỗi thay vì âm thầm chọn ngẫu nhiên. Nhưng nếu nguồn trả **mảng rỗng hợp lệ**, supplier phát `List.of()` để LoadBalancer biết không có ứng viên.

**Registry outage khác với “registry khỏe nhưng không có instance”.** `Flux.error(...)` từ directory không nên bị biến thành empty list mà không có metric/cảnh báo, vì hai tình huống đòi hướng xử lý vận hành khác nhau.

## 9. Đăng ký supplier trong LoadBalancer context theo service ID

Spring Cloud hỗ trợ cấu hình riêng cho một service ID bằng `@LoadBalancerClient`. Tạo lớp cấu hình ở package `demo.lbconfig`, nằm **ngoài phạm vi component scan mặc định** của ứng dụng caller ở package `demo.caller`.

~~~java
package demo.lbconfig;

import org.springframework.cloud.loadbalancer.core.ServiceInstanceListSupplier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration(proxyBeanMethods = false)
public class CatalogLoadBalancerConfiguration {

    @Bean
    ServiceInstanceListSupplier catalogInstanceSupplier() {
        // Control-plane client riêng, KHÔNG @LoadBalanced.
        WebClient plainDirectoryClient = WebClient.builder()
            .baseUrl("http://127.0.0.1:18100")
            .build();

        InstanceDirectory directory =
            new HttpInstanceDirectory(plainDirectoryClient);

        return new CatalogDirectorySupplier(directory);
    }
}
~~~

**Điểm quan trọng:** URL `127.0.0.1:18100` là endpoint cố định của topology API trong **lab**. Ở production, lấy URL từ cấu hình đáng tin, dùng HTTPS/TLS có xác minh danh tính, credentials riêng và circuit breaker/timeout phù hợp. Không để user input tùy ý quyết định URL nguồn.

Gắn cấu hình vào đúng service:

~~~java
package demo.caller;

import demo.lbconfig.CatalogLoadBalancerConfiguration;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cloud.loadbalancer.annotation.LoadBalancerClient;

@SpringBootApplication
@LoadBalancerClient(
    name = "catalog-service",
    configuration = CatalogLoadBalancerConfiguration.class
)
public class OrderApplication {

    public static void main(String[] args) {
        SpringApplication.run(OrderApplication.class, args);
    }
}
~~~

Khi code caller cần `catalog-service`, LoadBalancer context tương ứng dùng bean `ServiceInstanceListSupplier` do lớp cấu hình cung cấp.

### Lưu ý về component scan

Một `@Configuration` được đăng ký vào application context chung có thể khiến cùng supplier được áp dụng rộng hơn dự định. Vì vậy nên:

- Đặt `CatalogLoadBalancerConfiguration` ngoài package tree được `@SpringBootApplication` scan.
- Hoặc theo hướng dẫn Spring Cloud, không đánh dấu `@Configuration` nếu cách đăng ký hiện tại phù hợp.
- Kiểm tra service ID thực sự dùng custom supplier và những service ID khác vẫn dùng default supplier.
- Không tạo nhiều bean `ServiceInstanceListSupplier` không rõ ưu tiên trong cùng LoadBalancer child context.

Khả năng tạo bean/context cụ thể còn phụ thuộc release train; code ở trên sử dụng kiểu cấu hình `@LoadBalancerClient` phổ biến.

## 10. Tạo caller RestClient gọi theo service ID

Khi supplier đã đăng ký, phần nghiệp vụ không cần biết nguồn discovery là Eureka hay topology API:

~~~java
package demo.caller;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;

@Configuration(proxyBeanMethods = false)
class CatalogHttpClientConfiguration {

    @Bean
    @LoadBalanced
    RestClient.Builder loadBalancedRestClientBuilder() {
        return RestClient.builder();
    }

    @Bean
    RestClient catalogRestClient(
        @Qualifier("loadBalancedRestClientBuilder")
        RestClient.Builder builder
    ) {
        return builder.baseUrl("http://catalog-service").build();
    }
}
~~~

Tạo endpoint minh họa:

~~~java
package demo.caller;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.client.RestClient;

@RestController
class CatalogCallerController {

    private final RestClient catalogRestClient;

    CatalogCallerController(RestClient catalogRestClient) {
        this.catalogRestClient = catalogRestClient;
    }

    @GetMapping("/demo/whoami")
    String whoami() {
        return catalogRestClient.get()
            .uri("/api/whoami")
            .retrieve()
            .body(String.class);
    }
}
~~~

Request logic `GET http://catalog-service/api/whoami` sẽ đi qua Spring Cloud LoadBalancer. Supplier trả A/B; LoadBalancer chọn một instance và RestClient gửi request tới `127.0.0.1:18081` hoặc `127.0.0.1:18082`.

**Đừng tạo `RestClient.create("http://catalog-service")` trực tiếp** rồi cho rằng custom supplier sẽ được dùng: client đó không tự nhận tích hợp `@LoadBalanced`.

### WebClient và OpenFeign cũng có thể dùng cùng supplier

Đối với WebClient, tạo `@LoadBalanced WebClient.Builder` và client có base URL `http://catalog-service`. Với OpenFeign, dùng `@FeignClient(name = "catalog-service")` và tích hợp Spring Cloud LoadBalancer tương thích.

~~~java
@FeignClient(name = "catalog-service")
interface CatalogFeignClient {

    @GetMapping("/api/whoami")
    String whoami();
}
~~~

Ví dụ Feign cần `spring-cloud-starter-openfeign` và `@EnableFeignClients` khi triển khai; đây là **phương án thay thế** cho RestClient demo, không yêu cầu bật cả hai. Cả ba client có thể cùng lấy ứng viên qua supplier cho service ID đó nếu integration được cấu hình đúng.

## 11. Dựng backend A/B để nhìn thấy instance thực sự được chọn

Một ứng dụng Spring Boot Web MVC mẫu:

~~~java
package demo.catalog;

import java.util.Map;

import org.springframework.core.env.Environment;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class WhoAmIController {

    private final String instanceId;

    WhoAmIController(Environment env) {
        instanceId = env.getProperty("instance.id", "unknown");
    }

    @GetMapping("/api/whoami")
    Map<String, String> whoami() {
        return Map.of("instanceId", instanceId);
    }
}
~~~

Cần class entry point `@SpringBootApplication` và dependency Spring Web phù hợp trong backend. Sau khi build giả định có `catalog-service.jar`, khởi chạy:

~~~bash
java -jar catalog-service.jar --server.port=18081 --instance.id=catalog-a
java -jar catalog-service.jar --server.port=18082 --instance.id=catalog-b
~~~

Kiểm tra trước:

~~~bash
curl -i http://127.0.0.1:18081/api/whoami
curl -i http://127.0.0.1:18082/api/whoami
~~~

Nếu backend trả `instanceId` khác nhau, caller có thể quan sát LoadBalancer đã chọn bản sao nào.

## 12. Dựng topology API độc lập

Một ứng dụng Spring Boot khác cung cấp JSON snapshot. Có thể copy các DTO `DirectorySnapshot` và `DirectoryNode` (cùng cấu trúc JSON) vào module này hoặc dùng một shared API contract có version rõ ràng.

~~~java
package demo.directory;

import java.util.List;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

record DirectoryNode(
    String id, String host, int port,
    boolean secure, String zone, int weight
) {}

record DirectorySnapshot(
    String serviceId, List<DirectoryNode> instances
) {}

@RestController
@RequestMapping("/api/v1/services")
class LabDirectoryController {

    @GetMapping("/{serviceId}/instances")
    DirectorySnapshot instances(@PathVariable String serviceId) {
        if (!"catalog-service".equals(serviceId)) {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND);
        }

        return new DirectorySnapshot(
            serviceId,
            List.of(
                new DirectoryNode(
                    "catalog-a", "127.0.0.1", 18081,
                    false, "zone-a", 50
                ),
                new DirectoryNode(
                    "catalog-b", "127.0.0.1", 18082,
                    false, "zone-b", 50
                )
            )
        );
    }
}
~~~

Giả sử backend topology được build thành `topology-directory.jar` và có `@SpringBootApplication`:

~~~bash
java -jar topology-directory.jar --server.port=18100
~~~

Kiểm tra endpoint:

~~~bash
curl -i http://127.0.0.1:18100/api/v1/services/catalog-service/instances
~~~

**Không đặt topology API chạy sau chính `catalog-service` mà nó đang cần tra cứu** nếu điều đó tạo phụ thuộc vòng hoặc khiến việc recovery của discovery không thể thực hiện. Trong lab, topology API dùng địa chỉ cục bộ cố định, tách khỏi danh sách các instance backend.

## 13. Kiểm chứng request được phân phối theo snapshot

Sau khi khởi chạy:

1. Hai backend ở 18081/18082.
2. Topology API ở 18100.
3. Caller `OrderApplication` ở 18090 (qua `--server.port=18090` hoặc `application.yml`).
4. Custom supplier được gắn vào `@LoadBalancerClient(name = "catalog-service", ...)`.

Gọi nhiều lần:

~~~bash
for i in $(seq 1 12); do
  curl -s http://127.0.0.1:18090/demo/whoami
  echo
done
~~~

Kỳ vọng: quan sát response có `instanceId=catalog-a` và `instanceId=catalog-b` khi danh sách ổn định và chính sách Round Robin đang được dùng.

Đây là minh họa hành vi, **không hứa rằng mọi run sẽ xen kẽ A/B đúng từng lượt**: nhiều caller, retry, sự thay đổi danh sách hoặc chính sách khác có thể ảnh hưởng kết quả.

### Thay đổi topology

Sửa response của topology API để chỉ còn A, rồi thử lại. Supplier không cache trong ví dụ cơ sở nên các lần subscription mới sẽ nhận snapshot mới. Nếu bật cache, phải đợi cache refresh hoặc dùng cơ chế invalidation phù hợp.

Thử thêm node cổng 18083 hoặc host lạ vào snapshot: `allowedInLab(...)` sẽ loại node đó. Nếu tất cả node đều không hợp lệ, supplier trả danh sách rỗng; caller phải xử lý trường hợp không chọn được instance.

## 14. Sự cố nguồn bản sao: không có instance khác lỗi không lấy được dữ liệu

Ba tình huống cần phân biệt:

| Tình huống | Tín hiệu trong supplier demo | Ý nghĩa |
|---|---|---|
| API trả snapshot hợp lệ với A/B | `Flux.just(List.of(A,B))` tương đương | Có ứng viên |
| API trả snapshot hợp lệ nhưng `instances=[]` | `Flux.just(List.of())` tương đương | Không có ứng viên |
| API timeout, trả 5xx hoặc JSON sai | `Flux.error(exception)` | Không truy xuất/xác minh được nguồn |

Ví dụ **không nên**:

~~~java
@Override
public Flux<List<ServiceInstance>> get() {
    return directory.find(SERVICE_ID)
        .map(this::validateAndConvert)
        .onErrorReturn(List.of())    // Không nên che mọi lỗi nguồn thành 0 instance
        .flux();
}
~~~

Tại sao? Một outage của topology API có thể bị báo thành “không có backend nào healthy”. Khi điều tra vận hành, hai trường hợp này cần alert và hướng khắc phục khác nhau.

### Fail closed hay giữ snapshot cuối?

Trong một số hệ thống, khi topology API lỗi, có thể dùng **last-known-good snapshot** trong thời gian ngắn nếu chính sách cho phép. Nhưng đây là **quyết định về availability và bảo mật**, không phải fallback mặc định:

- Phải có TTL và tuổi tối đa của snapshot.
- Có thể có instance đã bị thu hồi/cấp quyền thay đổi; stale data gây rủi ro.
- Nếu không còn snapshot hợp lệ hoặc đã quá hạn, fail closed.
- Khi fallback xảy ra, phải có metric/alert phân biệt “using stale” với “fresh”.
- Không lấy danh sách chưa kiểm tra để “cứ gọi thử” khi dữ liệu không đáng tin.

Với nguồn chứa quyền cho phép kết nối, cần phối hợp network egress/TLS identity để việc thu hồi không phụ thuộc duy nhất vào TTL của cache.

## 15. Cache: tránh gọi topology API cho mỗi HTTP request

Supplier hiện tại có thể truy cập nguồn HTTP cho mỗi lần LoadBalancer cần snapshot. Ở hệ thống có throughput cao, điều này làm tăng:

- Latency chọn instance trước khi HTTP request thật được gửi.
- Số request tới topology API.
- Rủi ro khi topology API trở thành dependency nóng hoặc single point of failure.
- Số connection và bộ nhớ/CPU dùng cho control-plane lookup.

Spring Cloud LoadBalancer có `CachingServiceInstanceListSupplier`. Một pattern là **bọc supplier truy vấn mạng bằng cache trước khi đặt các bộ lọc request-dependent**.

~~~text
CustomDirectorySupplier (truy vấn nguồn bên ngoài)
    -> CachingServiceInstanceListSupplier (tùy chọn)
    -> Zone/Hint/Version filtering (tùy chọn)
    -> LoadBalancer chọn instance
~~~

Ví dụ minh họa bọc delegate, với `cacheManager` đã được cấu hình phù hợp cho LoadBalancer:

~~~java
import org.springframework.cache.CacheManager;
import org.springframework.cloud.loadbalancer.core.CachingServiceInstanceListSupplier;
import org.springframework.cloud.loadbalancer.core.ServiceInstanceListSupplier;

// Trong phương thức cấu hình supplier:
ServiceInstanceListSupplier source =
    new CatalogDirectorySupplier(directory);

ServiceInstanceListSupplier cached =
    new CachingServiceInstanceListSupplier(source, cacheManager);
~~~

Đây là **đoạn minh họa thay thế** cho cách đăng ký supplier không cache ở phần 9, không phải bean thứ hai tự động được đăng ký. Cần có `CacheManager` phù hợp với cache LoadBalancer trong context và kiểm tra constructor/API theo Spring Cloud release train của dự án.

Các thuộc tính cache chung thường được dùng:

~~~yaml
spring:
  cloud:
    loadbalancer:
      cache:
        enabled: true
        ttl: 20s
        capacity: 256
~~~

Các giá trị 20 giây/256 chỉ mang tính minh họa. `capacity` trong cấu hình LoadBalancer là **initial capacity**, không phải lời hứa “tối đa chỉ lưu 256 entries”. Nếu sử dụng Caffeine specification tùy biến, đặc tả đó có thể ghi đè TTL/capacity chung theo tài liệu hiện hành.

**Lưu ý bắt buộc:** nếu nguồn riêng đã cache danh sách trong SDK của nó, thêm cache LoadBalancer có thể tạo **double caching**. Mỗi tầng làm tăng thời gian stale; xác định rõ nguồn nào chịu trách nhiệm refresh và thời điểm chặn đích bị thu hồi.

Không sử dụng `ServiceInstanceListSupplier.builder().withDiscoveryClient().withCaching()` nếu mục tiêu là lấy dữ liệu từ **custom source** mà không có DiscoveryClient: phương thức `withDiscoveryClient()` sẽ tạo đường đi dựa trên discovery, không tự biết `HttpInstanceDirectory` của bài này.

## 16. Health check và các filter khác

Bài này mới thay đổi **nguồn ứng viên**. Nếu cần health check, zone preference, weighted routing, request hints hoặc API version, hãy thiết kế supplier chain tương ứng.

| Lớp | Tác dụng | Điều cần kiểm tra |
|---|---|---|
| Custom source supplier | Lấy danh sách A/B từ topology API | Trust, schema, timeout, freshness |
| Cache | Giảm truy vấn nguồn | TTL, stale/revocation |
| Health-check supplier | Đánh giá khả dụng của instance | Endpoint probe, interval, fallback |
| Zone preference | Ưu tiên instance cùng zone | Metadata `zone` do nguồn đáng tin cung cấp |
| Weighted supplier | Ảnh hưởng tỷ lệ chọn theo weight | Không tin giá trị weight chưa validate |
| Request hint/version filter | Lọc dựa trên request context | Không đưa raw input chưa được kiểm tra thành quyền định tuyến |

Spring Cloud hướng dẫn đặt `CachingServiceInstanceListSupplier` hoặc `HealthCheckServiceInstanceListSupplier` **trực tiếp sau supplier truy xuất dữ liệu qua mạng**, trước các supplier lọc khác; tránh vô tình bọc cả caching và health-check theo cách tạo các tầng cache chồng chéo. Với một chain cụ thể, cần kiểm tra constructor và thứ tự delegate theo release train.

**Không tự bật các filter chỉ vì snapshot có metadata.** Ví dụ đưa `weight=50` vào `DefaultServiceInstance.getMetadata()` **không tự biến Round Robin thành weighted routing**; chỉ khi `WeightedServiceInstanceListSupplier` hoặc chính sách khác được cấu hình và sử dụng metadata đó thì weight mới có tác dụng.

Health check cũng không phải authentication: instance giả có thể trả HTTP 200. Bảo vệ nguồn topology, TLS identity và egress policy vẫn phải độc lập với health.

## 17. Tùy biến request-aware supplier khi nào?

Ở ví dụ này, mọi request tới `catalog-service` dùng cùng một danh sách ứng viên. Một số hệ thống muốn chọn theo:

- Zone của caller hoặc tenant routing policy.
- API version/header được phép.
- Canary cohort đã được tính ở boundary có xác thực.
- Request hint có nguồn tin cậy.

Spring Cloud có `ServiceInstanceListSupplier.get(Request request)` cho những supplier cần request context. Tuy nhiên, **không nên lấy raw header từ client và trực tiếp chuyển thành host/port**; cần authorization, validation và tính nhất quán với supplier chain.

Nếu chỉ muốn giới hạn theo zone hoặc weight, trước hết xem các supplier tích hợp như `ZonePreferenceServiceInstanceListSupplier` và `WeightedServiceInstanceListSupplier`. Tự viết một request-aware supplier mới chỉ khi semantics khác rõ ràng và đã có test fail-closed cho request metadata không hợp lệ.

### Không viết thuật toán chọn instance ở trong get()

Một anti-pattern:

~~~java
// Sai trách nhiệm: chỉ trả đúng một instance ngẫu nhiên trong mỗi snapshot.
return directory.find(SERVICE_ID)
    .map(snapshot -> List.of(
        pickRandomInstance(snapshot.instances())
    ))
    .flux();
~~~

Cách này làm mất ứng viên với các lớp health/zone/weight khác và khiến Round Robin chạy trên một danh sách đã bị thu hẹp ngoài ý muốn. Nếu cần chính sách chọn một instance đặc biệt, hãy tùy biến chính sách LoadBalancer thay vì ngầm chọn bên trong nguồn.

## 18. Timeout, retry và giới hạn tải cho lookup topology

HTTP call tới topology API là **control-plane lookup**. Nó cần giới hạn riêng, không nên dùng chung deadline của một thao tác nghiệp vụ mà không tính tổng.

~~~mermaid
sequenceDiagram
    participant C as Caller
    participant LB as LoadBalancer
    participant S as Custom Supplier
    participant API as Topology API
    participant I as catalog instance

    C->>LB: GET catalog-service/api/whoami
    LB->>S: get()
    S->>API: GET /instances (deadline riêng)
    API-->>S: A/B hoặc lỗi/timeout
    S-->>LB: Snapshot hoặc error
    LB-->>C: Instance được chọn / lỗi
    C->>I: HTTP request thật nếu đã chọn được
    I-->>C: HTTP response
~~~

**Thời gian tổng** có thể gồm cả lookup topology, lấy connection từ pool, kết nối tới backend, chờ response và các lần retry. Nếu caller đặt deadline 2 giây nhưng topology lookup đã mất 1,8 giây, không nên để HTTP request tiếp theo tiếp tục chờ 3 giây rồi mới tính retry.

Một chính sách lookup hợp lý cần:

1. Connect/response timeout cho HTTP client của topology API.
2. Concurrency cap và connection pool phù hợp để bảo vệ nguồn.
3. Cache hoặc snapshot refresh thay vì gọi registry nóng cho mọi request.
4. Retry lookup **rất hạn chế** khi an toàn, có backoff và tổng deadline.
5. Phân biệt outage của topology API với backend 503 và với không có instance.
6. Circuit breaker/limit nếu nguồn bị lỗi kéo dài.
7. Không để lookup dùng chính `@LoadBalanced` đang cần snapshot từ nó.

Nếu nhiều caller đồng thời miss cache, có thể xảy ra **thundering herd** đến topology API. Chọn caching/single-flight refresh hoặc cơ chế push/watch có backpressure theo thiết kế thực tế.

## 19. Kiểm thử supplier độc lập với HTTP stack

Do đã tách `InstanceDirectory` thành interface, test dễ tạo dữ liệu giả.

~~~java
package demo.lbconfig;

import java.util.List;

import org.junit.jupiter.api.Test;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.assertj.core.api.Assertions.assertThat;

class CatalogDirectorySupplierTest {

    @Test
    void keepsOnlyAllowedInstances() {
        InstanceDirectory fake = serviceId -> Mono.just(
            new DirectorySnapshot(
                serviceId,
                List.of(
                    new DirectoryNode(
                        "catalog-a", "127.0.0.1", 18081,
                        false, "zone-a", 50
                    ),
                    new DirectoryNode(
                        "not-allowed", "127.0.0.1", 18083,
                        false, "zone-b", 10
                    )
                )
            )
        );

        var supplier = new CatalogDirectorySupplier(fake);

        StepVerifier.create(supplier.get().next())
            .assertNext(instances -> {
                assertThat(instances).hasSize(1);
                assertThat(instances.get(0).getInstanceId())
                    .isEqualTo("catalog-a");
                assertThat(instances.get(0).getServiceId())
                    .isEqualTo("catalog-service");
            })
            .verifyComplete();
    }
}
~~~

Đoạn test minh họa, **không được chạy trong STEP 4** theo quy trình hiện tại. Ở giai đoạn QA/build sau, có thể bổ sung:

| Ca kiểm thử | Kỳ vọng |
|---|---|
| Snapshot hợp lệ A/B | Phát một danh sách gồm hai instance |
| Snapshot rỗng | Phát một danh sách rỗng |
| Snapshot có serviceId khác | Error; không chọn host sai |
| Snapshot có port không hợp lệ | Bị loại theo policy |
| Snapshot có instanceId trùng | Error; không chọn dữ liệu mâu thuẫn |
| Directory HTTP 401/403 | Error nguồn, không fallback bừa |
| Directory HTTP 500 | Error hoặc last-good snapshot theo policy rõ ràng |
| Directory timeout | Error có giới hạn thời gian |
| JSON parse/schema fail | Error; metric decode |
| Thay đổi A/B theo thời gian | Supplier không cache lấy snapshot mới |
| Cache TTL chưa hết | Có thể vẫn trả snapshot cũ |
| Tất cả instance bị lọc | Không request tới đích ngoài policy |
| Cùng tên bean supplier ở nhiều context | Chỉ đúng service ID được override |

## 20. Integration test: chứng minh client dùng custom supplier

Một unit test `get()` PASS **không đủ** chứng minh LoadBalancer đã dùng đúng supplier.

Trong integration test hoặc lab:

1. Khởi động topology API tại 18100 với response A/B.
2. Khởi động backend A/B tại 18081/18082.
3. Khởi động caller có `@LoadBalancerClient` cho `catalog-service`.
4. Gửi nhiều GET vào `/demo/whoami`.
5. Quan sát backend A/B đã nhận request thực, không chỉ nhìn kết quả từ mock.
6. Thay snapshot chỉ còn A, xác minh request mới chỉ tới A sau refresh/cache.
7. Thêm bản ghi không hợp lệ, xác minh không có HTTP request tới cổng ngoài policy.
8. Cho topology API trả 503; kiểm tra lỗi được phân loại là **source unavailable**.
9. Làm topology API chậm, quan sát lookup latency và deadline tổng.
10. Kiểm tra một service ID khác vẫn dùng configuration riêng/default như dự kiến.

### Hai loại log cần phân biệt

~~~text
supplier: serviceId=catalog-service candidates=2 source=topology-api
loadbalancer: serviceId=catalog-service selected=catalog-b
http-client: destination=catalog-b status=200 duration=35ms
~~~

Dòng trên là **format log mục tiêu**, không phải log mà framework tự phát ra nguyên văn. Đừng lạm dụng event logs có cardinality cao hoặc log raw metadata/credential từ topology API.

## 21. Quan sát và vận hành nguồn riêng

Một custom supplier đi vào đường đi quan trọng của mỗi remote call. Nên đo:

| Metric / log field | Mục đích |
|---|---|
| `serviceId` | Xác định tập ứng viên nào đang được lấy |
| Source endpoint label | Phân biệt control plane và data plane |
| Lookup latency p50/p95/p99 | Phát hiện topology API chậm |
| Lookup success/error/timeout | Phân biệt outage nguồn |
| Snapshot age / cache hit | Đo độ mới của thông tin |
| Candidate count before/after validation | Nhận ra dữ liệu lỗi hoặc thay đổi bất thường |
| Rejected instance count/reason | Bảo vệ routing và audit |
| Duplicate ID / schema error | Phát hiện nguồn dữ liệu mâu thuẫn |
| Selected instance | So sánh phân phối load balancing |
| No-instance count | Phân biệt snapshot hợp lệ rỗng |
| Downstream connect/read timeout | Phân biệt lỗi backend với lỗi source |
| Retry attempts và deadline remaining | Tránh retry storm |
| Circuit breaker state của source | Biết khi nào control plane bị cô lập |

Không đưa `instanceId` tùy ý hoặc URL dài không kiểm soát vào nhãn metric có cardinality cao. Khi log host/port, phải bảo đảm không lộ topology nhạy cảm ra hệ thống công khai.

Với tracing, có thể liên kết ba span/operation: **lookup danh sách**, **chọn instance** và **HTTP request thực**. Một lỗi chọn instance có thể xảy ra **trước khi có HTTP request tới backend**, nên dashboard chỉ đếm HTTP 5xx sẽ bỏ sót trường hợp này.

## 22. Những sai lầm thường gặp

1. Trả `Flux<ServiceInstance>` thay vì `Flux<List<ServiceInstance>>`.
2. Trả `Flux.empty()` khi snapshot hợp lệ nhưng không có ứng viên.
3. Dùng `block()` trong reactive supplier, chặn event-loop.
4. Dùng client `@LoadBalanced` để gọi chính topology API, tạo phụ thuộc vòng.
5. Tạo một client HTTP mới cho mỗi lần gọi `get()`, làm mất cơ hội reuse pool.
6. Đăng ký custom config trong component scan chung, khiến service ID khác bị ảnh hưởng.
7. Dùng `ServiceInstanceListSupplier.builder().withDiscoveryClient()` rồi tưởng dữ liệu tự đến từ custom directory.
8. Chỉ cần một instance nên trả luôn đúng một phần tử trong supplier, làm mất thuật toán chọn.
9. Không kiểm tra service ID, host, port, scheme, ID trùng và metadata.
10. Tin metadata `weight/zone` là bằng chứng identity hoặc tự bật chính sách weight.
11. Biến mọi lỗi topology API thành danh sách rỗng mà không có alert.
12. Fallback vô thời hạn sang last-known-good snapshot đã hết hạn.
13. Gọi topology API trên mỗi request với QPS cao mà không cache/concurrency cap.
14. Bật caching rồi health-check thêm nhiều tầng làm tăng độ trễ hội tụ.
15. Giả định LoadBalancer cache và HTTP connection pool là cùng một thứ.
16. Chỉ kiểm thử supplier unit, không chứng minh `@LoadBalancerClient` đã kích hoạt.
17. Không phân biệt lỗi source, no instance, connect timeout và backend HTTP 503.
18. Không có network egress/TLS identity khi dùng nguồn topology do nhiều bên có thể sửa.
19. Không chú ý retry có thể chọn instance khác, làm lộ vấn đề stateful session/idempotency.
20. Không có metric về số instance bị loại, độ tuổi snapshot và lookup latency.

## 23. Checklist trước khi triển khai

- Đã xác định **nguồn sự thật** cho tập instance và ai được phép cập nhật chưa?
- Custom supplier có trả đúng `serviceId`, `Flux<List<ServiceInstance>>` và một snapshot hợp lệ không?
- Nguồn đã có reactive API hoặc client không blocking phù hợp chưa?
- HTTP client của control plane có **độc lập với LoadBalancer** cần nó không?
- Có giới hạn timeout, pool, concurrency và retry budget cho lookup nguồn không?
- Có kiểm tra schema, host/port/scheme, instance ID, zone/weight và duplicated IDs không?
- Khi không còn instance, có fail closed theo policy không?
- Khi nguồn lỗi, có phân biệt error với valid empty snapshot không?
- Nếu dùng cache, đã xác định TTL, refresh, stale cap và cơ chế thu hồi chưa?
- Supplier có được đăng ký **đúng service ID** và ngoài component scan chung không?
- RestClient/WebClient/OpenFeign caller có thực sự dùng LoadBalancer integration không?
- Health, zone, weight, hints/version có được kết hợp đúng thứ tự và đúng semantics không?
- Có integration test thay đổi topology A/B, source outage và invalid record không?
- Có quan sát lookup latency, rejected candidates và selected instance không?
- Trong sản xuất, registry/metadata có TLS, RBAC và network egress control không?

## 24. Kết luận

**`ServiceInstanceListSupplier` là điểm mở rộng phù hợp khi Spring Cloud LoadBalancer phải lấy `ServiceInstance` từ một nguồn riêng.** Custom supplier chịu trách nhiệm **truy xuất, chuyển đổi, kiểm tra và phát danh sách ứng viên**; LoadBalancer tiếp tục chọn instance theo chính sách, còn HTTP client thực hiện request theo service ID. Ví dụ `CatalogDirectorySupplier` cho thấy cách trả một `Flux<List<ServiceInstance>>` từ API topology độc lập và dùng `@LoadBalancerClient` để chỉ áp dụng cấu hình cho `catalog-service`.

Muốn vận hành ổn định, không nên dừng ở “danh sách trả về đúng”: cần bảo đảm **nguồn tin cậy, dữ liệu hợp lệ, lookup không blocking, cache không quá stale, health/filter đúng thứ tự, timeout/retry có ngân sách và observability đầy đủ**. Khi những điều kiện đó được kiểm chứng, RestClient, WebClient và OpenFeign có thể tiếp tục giao tiếp theo tên dịch vụ mà không cần biết danh sách bản sao được lấy từ Eureka, Kubernetes hay một control plane tùy biến.

## Tài liệu tham khảo

- Spring Cloud Commons – Spring Cloud LoadBalancer: https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html
- Spring Framework – WebClient: https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html
- Spring Framework – RestClient: https://docs.spring.io/spring-framework/reference/integration/rest-clients.html

