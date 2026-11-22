# Thực hành vùng ưu tiên, trọng số và hint

Khi một ứng dụng gọi `http://inventory-service`, **Spring Cloud LoadBalancer** chọn `ServiceInstance` từ danh sách discovery. Mặc định, Round Robin có thể phân phối tương đối đều số lượt chọn giữa các instance. Trong hệ thống thực tế, chúng ta thường cần thêm ba chính sách:

- **Vùng ưu tiên (zone preference):** caller ở vùng `hcm` muốn ưu tiên replica cùng vùng để giảm độ trễ/chi phí mạng.
- **Trọng số (weight):** replica nhiều tài nguyên được nhận tỷ lệ yêu cầu lớn hơn replica nhỏ.
- **Hint:** từng lời gọi có thể chỉ định một nhóm replica ưu tiên, chẳng hạn `blue` và `green` trong quá trình rollout.

Bài **Thực hành tổng hợp** này xây một lab từ đầu để quan sát từng chính sách độc lập rồi ghép chúng theo thứ tự có chủ đích. Lab áp dụng cho module **SPRING_CLOUD_SERVICE_COMMUNICATION_LOAD_BALANCING**: giao tiếp qua **service ID**, chọn instance bằng discovery và `ServiceInstanceListSupplier`, kiểm tra fallback, timeout, retry và khả năng quan sát. Phần chính dùng **WebClient** vì dễ truyền hint qua request header và quan sát chuỗi reactive; cuối bài chỉ ra cách dùng cùng chính sách từ RestClient/OpenFeign.

> **Phạm vi:** đây là lab local với `SimpleDiscoveryClient` và metadata tĩnh. Các con số về phân bố là **kỳ vọng**, không phải kết quả benchmark đã chạy. Không dùng hint/zone preference mặc định để cưỡng chế phân quyền, phân vùng dữ liệu hoặc cách ly bảo mật.

## 1. Kết quả cần đạt

Sau bài học, bạn có thể:

1. Chạy một caller và bốn bản sao `inventory-service` với metadata `zone`, `weight` và `hint`.
2. Tạo `ServiceInstanceListSupplier` theo chế độ `zone`, `weighted`, `hint` hoặc `combined`.
3. Phân biệt **tập instance hợp lệ sau lọc** và **thuật toán chọn một instance** (ví dụ Round Robin).
4. Dùng `spring.cloud.loadbalancer.zone` và `ZonePreferenceServiceInstanceListSupplier` để ưu tiên vùng.
5. Dùng `WeightedServiceInstanceListSupplier` để áp trọng số từ metadata key `weight`.
6. Dùng `HintBasedServiceInstanceListSupplier` và header `X-SC-LB-Hint` để ưu tiên nhóm replica cho từng request.
7. Quan sát cách ba policy kết hợp, bao gồm fallback khi zone/hint không có instance khớp.
8. Thu thập counts, so tỷ lệ phân phối kỳ vọng, kiểm thử lỗi và chuẩn bị giới hạn an toàn cho production.

### Phân biệt ba mục tiêu

| Chính sách | Input | Làm gì? | Không bảo đảm |
|---|---|---|---|
| Zone preference | Zone caller và metadata `zone` của instance | Ưu tiên danh sách cùng zone | Không bắt buộc từ chối cross-zone nếu không có match |
| Weight | Metadata `weight` hoặc `WeightFunction` | Biến tần suất lựa chọn theo trọng số | Không tự nhận biết CPU/queue hoặc năng lực thời gian thực |
| Hint | Request header `X-SC-LB-Hint` hoặc hint property, metadata `hint` | Ưu tiên instance có hint khớp | Không phải hard partition hay cơ chế bảo mật |

Ba policy này được thực hiện chủ yếu bằng các **supplier decorators**, không nhất thiết phải viết `ReactorServiceInstanceLoadBalancer` tùy chỉnh. Thuật toán `RoundRobinLoadBalancer` vẫn có thể lấy một phần tử từ danh sách supplier trả ra.

## 2. Kiến trúc của lab

~~~mermaid
flowchart TB
    U["PowerShell hoặc HTTP client"] --> C["caller :8080 (WebClient)"]
    C --> L["Spring Cloud LoadBalancer / inventory-service"]
    M["SimpleDiscoveryClient: metadata zone, weight, hint"] --> L
    L --> A["inventory HCM blue A :8081 (weight 3)"]
    L --> B["inventory HCM blue B :8082 (weight 1)"]
    L --> D["inventory HCM green C :8083 (weight 2)"]
    L --> E["inventory HN blue D :8084 (weight 4)"]
~~~

Ta đặt tên zone `hcm` và `hn` để minh họa; chúng chỉ là **chuỗi metadata** trong lab, không chứng minh các tiến trình thật sự chạy tại trung tâm dữ liệu khác nhau.

| Instance ID | URI | `zone` | `hint` | `weight` |
|---|---|---|---|---:|
| `hcm-blue-a` | `http://localhost:8081` | `hcm` | `blue` | 3 |
| `hcm-blue-b` | `http://localhost:8082` | `hcm` | `blue` | 1 |
| `hcm-green-c` | `http://localhost:8083` | `hcm` | `green` | 2 |
| `hn-blue-d` | `http://localhost:8084` | `hn` | `blue` | 4 |

Đặt caller ở zone `hcm`:

~~~yaml
spring:
  cloud:
    loadbalancer:
      zone: hcm
~~~

Các tình huống cần quan sát:

- **Zone:** chỉ còn A/B/C khi có replica `hcm`; D ở `hn` không được ưu tiên.
- **Weight:** nếu không lọc, phân bố mục tiêu theo trọng số của A:B:C:D là `3:1:2:4`.
- **Hint = blue:** ưu tiên A/B/D vì metadata `hint: blue`.
- **Hint = green:** ưu tiên C.
- **Combined (zone → hint → weight):** với hint `blue`, cuối cùng ưu tiên A/B với tỷ lệ mục tiêu `3:1`; hint `green` chỉ còn C.
- **Unknown hint:** khi không có instance khớp, supplier hint mặc định **trả về danh sách được delegate cung cấp**, không trả danh sách rỗng theo mặc định.

Các kết quả combined là đặc tính của **thứ tự supplier được cấu hình trong bài**. Đổi thứ tự có thể đổi tập ứng viên được chọn.

## 3. Chuẩn bị công cụ và dependency

Cần có:

- JDK phù hợp với Spring Boot được chọn, Maven và PowerShell hoặc terminal tương đương.
- Một dự án Spring Boot **backend** đơn giản (Spring Web).
- Một dự án Spring Boot **caller** (Spring WebFlux, Spring Cloud LoadBalancer, Actuator tùy chọn).
- Không cần Eureka/Consul/Kubernetes cho lab vì `SimpleDiscoveryClient` dùng danh sách tĩnh.

Lựa chọn Spring Boot và Spring Cloud **từ release train tương thích**. Ví dụ, tài liệu Spring Cloud nêu Spring Cloud `2025.0.x` tương ứng Spring Boot `3.5.x`, còn `2025.1.x` tương ứng Spring Boot `4.0.x` và một số phiên bản `4.1.x` phù hợp. Không trộn BOM của hai generation. Với bài học này, hãy dùng cặp version hợp lệ đã được kiểm tra trong dự án hoặc khởi tạo từ Spring Initializr với các dependency tương thích. Một số starter Web của Boot 4 có tên mới so với Boot 3; tránh copy POM giữa hai generation mà không kiểm tra.

Dependency caller theo Spring Boot/Cloud BOM:

~~~xml
<dependencies>
    <!-- Reactive HTTP client và REST endpoint caller. -->
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-webflux</artifactId>
    </dependency>

    <!-- Client-side discovery / ServiceInstance LoadBalancer. -->
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-loadbalancer</artifactId>
    </dependency>

    <!-- Quan sát metrics và health, có thể bỏ ở bài lab nhỏ. -->
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Dự án backend cần starter Web phù hợp Spring Boot generation đang dùng và `spring-boot-starter-test` nếu viết test. Nếu dùng Maven, hãy cấu hình Spring Cloud BOM trong `dependencyManagement` theo hướng dẫn Spring Initializr:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-dependencies</artifactId>
            <version>${spring-cloud.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

`spring-cloud.version` phải được khai báo bằng một phiên bản tương thích Boot, không tự để nguyên placeholder. Lab chỉ cung cấp các đoạn file cần thiết; người học có thể đưa vào hai dự án Maven đã được tạo thay vì bắt buộc thiết lập cấu trúc multi-module mới.

### Cấu trúc mã nguồn gợi ý

~~~text
routing-lab/
  backend/
    pom.xml
    src/main/java/com/example/lab/backend/
      BackendApplication.java
      ReplicaController.java

  caller/
    pom.xml
    src/main/java/com/example/lab/caller/
      CallerApplication.java
      RoutingClientConfiguration.java
      RoutingController.java
    src/main/java/com/example/lab/lb/
      InventoryLoadBalancerConfiguration.java
    src/main/resources/
      application.yml
~~~

**Quan trọng:** `InventoryLoadBalancerConfiguration` được đặt ở package `com.example.lab.lb` **ngoài component scan** của `com.example.lab.caller`. Điều này ngăn cấu hình per-service bị đưa vào ApplicationContext cha và vô tình áp dụng cho các service ID khác.

## 4. Xây backend inventory dùng chung một artifact

Mỗi replica sẽ chạy cùng artifact backend, khác port và các thuộc tính `lab.*`. Backend chỉ trả metadata minh họa để ta biết instance nào được gọi.

`BackendApplication.java`:

~~~java
package com.example.lab.backend;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BackendApplication {

    public static void main(String[] args) {
        SpringApplication.run(BackendApplication.class, args);
    }
}
~~~

`ReplicaController.java`:

~~~java
package com.example.lab.backend;

import org.springframework.core.env.Environment;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ReplicaController {

    private final Environment environment;

    public ReplicaController(Environment environment) {
        this.environment = environment;
    }

    @GetMapping("/whoami")
    public InstanceView whoami(
            @RequestHeader(
                    name = "X-SC-LB-Hint",
                    required = false
            ) String receivedHint) {

        return new InstanceView(
                environment.getRequiredProperty("lab.instance-id"),
                environment.getProperty("lab.zone", "unknown"),
                environment.getProperty("lab.hint", "unknown"),
                environment.getProperty("lab.weight", "1"),
                receivedHint,
                environment.getProperty("server.port", "unknown")
        );
    }

    public record InstanceView(
            String instanceId,
            String zone,
            String hint,
            String weight,
            String receivedHint,
            String port
    ) {}
}
~~~

**Hai nguồn metadata không được nhầm lẫn:** các thuộc tính `lab.zone`/`lab.hint`/`lab.weight` của backend **chỉ để echo**. Spring Cloud LoadBalancer ở caller thực sự đọc metadata `zone`/`hint`/`weight` từ `ServiceInstance.getMetadata()` do SimpleDiscoveryClient cung cấp. Nếu hai nguồn lệch nhau, bạn có thể thấy backend trả “hcm” nhưng supplier chọn theo “hn”. Cần kiểm tra nguồn đăng ký instance, không chỉ response demo.

### Chạy bốn backend

Tạo artifact:

~~~powershell
cd routing-lab/backend
mvn -q -DskipTests package
~~~

Mở **bốn terminal riêng** và chạy mỗi lệnh một lần (thay đường dẫn JAR theo artifact thực tế):

~~~powershell
# Terminal 1
java -jar target/routing-backend-0.0.1-SNAPSHOT.jar --server.port=8081 --lab.instance-id=hcm-blue-a --lab.zone=hcm --lab.hint=blue --lab.weight=3
~~~

~~~powershell
# Terminal 2
java -jar target/routing-backend-0.0.1-SNAPSHOT.jar --server.port=8082 --lab.instance-id=hcm-blue-b --lab.zone=hcm --lab.hint=blue --lab.weight=1
~~~

~~~powershell
# Terminal 3
java -jar target/routing-backend-0.0.1-SNAPSHOT.jar --server.port=8083 --lab.instance-id=hcm-green-c --lab.zone=hcm --lab.hint=green --lab.weight=2
~~~

~~~powershell
# Terminal 4
java -jar target/routing-backend-0.0.1-SNAPSHOT.jar --server.port=8084 --lab.instance-id=hn-blue-d --lab.zone=hn --lab.hint=blue --lab.weight=4
~~~

Nếu Maven tạo JAR có tên khác, lấy đúng tên từ cấu hình `artifactId`/`version` của dự án. Không chạy bốn lệnh liên tiếp trong cùng một terminal foreground vì tiến trình đầu tiên sẽ chiếm terminal.

Kiểm tra từng instance trực tiếp:

~~~powershell
8081..8084 | ForEach-Object {
    Invoke-RestMethod "http://localhost:$_/whoami"
}
~~~

Kỳ vọng thấy bốn instance ID, các giá trị zone/hint/weight và cổng tương ứng. `receivedHint` là `null` vì lúc này bạn chưa thêm header trong request.

## 5. Khai báo bốn ServiceInstance tại caller

Trong `caller/src/main/resources/application.yml`:

~~~yaml
server:
  port: 8080

spring:
  application:
    name: routing-caller

  cloud:
    loadbalancer:
      zone: hcm
      hint-header-name: X-SC-LB-Hint
      retry:
        enabled: false   # Lab: giữ một HTTP attempt để dễ đếm.
    discovery:
      client:
        simple:
          instances:
            inventory-service:
              - instance-id: hcm-blue-a
                uri: http://localhost:8081
                metadata:
                  zone: hcm
                  hint: blue
                  weight: "3"
              - instance-id: hcm-blue-b
                uri: http://localhost:8082
                metadata:
                  zone: hcm
                  hint: blue
                  weight: "1"
              - instance-id: hcm-green-c
                uri: http://localhost:8083
                metadata:
                  zone: hcm
                  hint: green
                  weight: "2"
              - instance-id: hn-blue-d
                uri: http://localhost:8084
                metadata:
                  zone: hn
                  hint: blue
                  weight: "4"

lab:
  routing:
    mode: zone

management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics
~~~

**Cách đọc:**

- `inventory-service` là **service ID** duy nhất với bốn `ServiceInstance`.
- `instance-id` là định danh để log/test; `uri` chỉ rõ host:port thực tế.
- `metadata.zone` được `ZonePreferenceServiceInstanceListSupplier` so với client zone `hcm`.
- `metadata.hint` được `HintBasedServiceInstanceListSupplier` dùng để lọc theo hint request.
- `metadata.weight` được `WeightedServiceInstanceListSupplier` mặc định đọc dưới dạng số nguyên; nếu thiếu sẽ dùng weight 1.
- `lab.routing.mode` là **thuộc tính tự định nghĩa trong bài lab** để chọn policy supplier; không phải cấu hình built-in của Spring Cloud.
- `retry.enabled: false` chỉ áp dụng cơ chế retry Spring Cloud LoadBalancer để dễ phân tích. Các tầng HTTP client/gateway khác nếu tự bật retry vẫn cần kiểm tra riêng.

`SimpleDiscoveryClient` lấy danh sách từ properties và không tự thay đổi khi một tiến trình backend tắt. Vì vậy, bước giả lập lỗi ở cuối bài sẽ phân biệt rõ “địa chỉ còn trong discovery” với “instance thật sự khỏe”.

## 6. Tại sao không chọn zone/weight/hint ngay trong controller?

Một anti-pattern là:

~~~java
// Chỉ minh họa cách làm SAI: bypass discovery/LoadBalancer.
String url = hint.equals("blue")
        ? "http://localhost:8081/whoami"
        : "http://localhost:8083/whoami";
~~~

Cách này khiến business code biết IP/port, không có health/zone/weight policy nhất quán và dễ bypass discovery.

Cách đúng cho lab:

~~~text
RoutingController
    -> WebClient gọi http://inventory-service/whoami
    -> @LoadBalanced WebClient.Builder
    -> Spring Cloud LoadBalancer
    -> ServiceInstanceListSupplier:
         discovery -> zone/hint/weight
    -> RoundRobinLoadBalancer chọn một candidate
    -> HTTP đến URI vật lý
~~~

**Zone preference và hint là bộ lọc/ưu tiên danh sách ứng viên**; weighted supplier điều chỉnh cơ hội chọn từ danh sách đó. Chúng không phải ba HTTP calls hay ba vòng retry riêng biệt.


## 7. Tạo cấu hình LoadBalancer theo service ID

Trong caller, khai báo `@LoadBalancerClient` để cấu hình supplier **chỉ cho `inventory-service`**.

`CallerApplication.java`:

~~~java
package com.example.lab.caller;

import com.example.lab.lb.InventoryLoadBalancerConfiguration;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cloud.loadbalancer.annotation.LoadBalancerClient;

@SpringBootApplication
@LoadBalancerClient(
        name = "inventory-service",
        configuration = InventoryLoadBalancerConfiguration.class
)
public class CallerApplication {

    public static void main(String[] args) {
        SpringApplication.run(CallerApplication.class, args);
    }
}
~~~

`InventoryLoadBalancerConfiguration.java` (trong package `com.example.lab.lb`, nằm **ngoài** component scan):

~~~java
package com.example.lab.lb;

import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.cloud.loadbalancer.core.ServiceInstanceListSupplier;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;

public class InventoryLoadBalancerConfiguration {

    @Bean
    @ConditionalOnProperty(
            prefix = "lab.routing",
            name = "mode",
            havingValue = "zone"
    )
    ServiceInstanceListSupplier zoneSupplier(
            ConfigurableApplicationContext context) {

        return ServiceInstanceListSupplier.builder()
                .withDiscoveryClient()
                .withZonePreference()
                .build(context);
    }

    @Bean
    @ConditionalOnProperty(
            prefix = "lab.routing",
            name = "mode",
            havingValue = "weighted"
    )
    ServiceInstanceListSupplier weightedSupplier(
            ConfigurableApplicationContext context) {

        return ServiceInstanceListSupplier.builder()
                .withDiscoveryClient()
                .withWeighted()
                .build(context);
    }

    @Bean
    @ConditionalOnProperty(
            prefix = "lab.routing",
            name = "mode",
            havingValue = "hint"
    )
    ServiceInstanceListSupplier hintSupplier(
            ConfigurableApplicationContext context) {

        return ServiceInstanceListSupplier.builder()
                .withDiscoveryClient()
                .withHints()
                .build(context);
    }

    @Bean
    @ConditionalOnProperty(
            prefix = "lab.routing",
            name = "mode",
            havingValue = "combined"
    )
    ServiceInstanceListSupplier combinedSupplier(
            ConfigurableApplicationContext context) {

        return ServiceInstanceListSupplier.builder()
                .withDiscoveryClient()
                .withZonePreference()
                .withHints()
                .withWeighted()
                .build(context);
    }
}
~~~

Đây là cấu hình **một bean supplier cho mỗi chế độ**: `@ConditionalOnProperty` bảo đảm chỉ method có `havingValue` khớp `lab.routing.mode` được đăng ký. Bài lab luôn đặt `mode`, nên không cần `matchIfMissing`.

Lưu ý kiến trúc:

- `.withDiscoveryClient()` lấy danh sách từ discovery; với lab không có registry bên ngoài, `SimpleDiscoveryClient` cung cấp các instance tĩnh.
- `.withZonePreference()` dùng caller zone và metadata `zone`.
- `.withHints()` lọc theo hint của request/properties và metadata `hint`.
- `.withWeighted()` biến danh sách theo trọng số trước khi thuật toán chọn một phần tử.
- Không định nghĩa `ReactorLoadBalancer<ServiceInstance>` riêng vì ta giữ thuật toán `RoundRobinLoadBalancer` mặc định.
- Nếu dùng `withCaching()` ở production, đặt **ngay sau bước retrieval**, trước các supplier lọc theo request. Không đặt cache đầu ra của hint/zone sau lọc một cách vô ý, vì request A và B có thể dùng hint khác nhau.
- Không gắn `@Configuration` hoặc `@Component` cho lớp `InventoryLoadBalancerConfiguration` trong package bị component scan. Khi bị scan thành global bean, cấu hình này có thể ảnh hưởng đến các service IDs khác.
- Các thành phần supplier cần API tương thích release train đang chạy; nếu cập nhật Spring Cloud, hãy chạy integration tests của từng mode.

### Sơ đồ chuỗi supplier khi combined

~~~mermaid
flowchart LR
    D["Discovery"] --> Z["ZonePreference"]
    Z --> H["HintBased"]
    H --> W["Weighted"]
    W --> RR["RoundRobinLoadBalancer"]
    RR --> I["ServiceInstance"]
~~~

Khi `zone=hcm` và header `hint=blue`:

~~~text
Discovery:
  A(hcm,blue,w3)
  B(hcm,blue,w1)
  C(hcm,green,w2)
  D(hn, blue,w4)

Zone preference:
  A, B, C

Hint blue:
  A, B

Weighted:
  Danh sách logic theo tỷ lệ 3:1 giữa A và B

Round Robin:
  Chọn một entry từ danh sách được supplier cung cấp

HTTP:
  Gọi A :8081 hoặc B :8082
~~~

**Thứ tự là một phần của hợp đồng.** Nếu hint được dùng trước zone, một hint chỉ khớp instance vùng khác có thể tạo tập ứng viên khác. Với chuỗi ở bài này, vùng được xét trước, sau đó hint, cuối cùng mới tính trọng số trong tập còn lại.

### Vì sao ví dụ không bật cache?

Chúng ta có bốn instance tĩnh, muốn xem rõ tác động của từng policy. Vì vậy, các builder không dùng `withCaching()`. Đây là lựa chọn **đơn giản hóa bài học**, không phải khuyến nghị về hiệu năng production. Với discovery thật, Spring Cloud khuyến nghị caching nếu chưa có cache ở discovery client; cấu hình production có thể là:

~~~java
return ServiceInstanceListSupplier.builder()
        .withDiscoveryClient()
        .withCaching()
        .withZonePreference()
        .withHints()
        .withWeighted()
        .build(context);
~~~

Với `HealthCheckServiceInstanceListSupplier`, cần chú ý cache/replay và thứ tự riêng mà tài liệu mô tả. Không cấu hình nhiều tầng cache/health độc lập khi chưa hiểu thời điểm danh sách instance được cập nhật.

## 8. Tạo @LoadBalanced WebClient

`RoutingClientConfiguration.java`:

~~~java
package com.example.lab.caller;

import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration(proxyBeanMethods = false)
public class RoutingClientConfiguration {

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
}
~~~

`@LoadBalanced` gắn cơ chế Spring Cloud LoadBalancer cho builder. URL `http://inventory-service` có hostname là **service ID**, còn `/whoami` là endpoint backend. Chỉ gọi `http://localhost:8081` sẽ **bỏ qua lựa chọn service ID** và không kiểm thử các supplier đã cấu hình.

Nếu chưa có `spring-cloud-starter-loadbalancer` hoặc builder không được load balance, bạn có thể gặp `UnknownHostException` cho hostname `inventory-service`.

## 9. Controller caller: chỉ gửi hint đã cho phép

`RoutingController.java`:

~~~java
package com.example.lab.caller;

import java.time.Duration;
import java.util.Set;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.server.ResponseStatusException;
import reactor.core.publisher.Mono;

@RestController
public class RoutingController {

    private static final Set<String> DEMO_HINTS =
            Set.of("blue", "green", "unknown");

    private final WebClient inventory;

    public RoutingController(
            @Qualifier("inventoryWebClient") WebClient inventory) {
        this.inventory = inventory;
    }

    @GetMapping("/route")
    public Mono<InstanceView> route(
            @RequestParam(required = false) String hint) {

        if (hint != null && !DEMO_HINTS.contains(hint)) {
            return Mono.error(new ResponseStatusException(
                    HttpStatus.BAD_REQUEST,
                    "Unsupported lab hint"
            ));
        }

        return inventory.get()
                .uri("/whoami")
                .headers(headers -> {
                    if (hint != null) {
                        headers.set("X-SC-LB-Hint", hint);
                    }
                })
                .retrieve()
                .bodyToMono(InstanceView.class)
                .timeout(Duration.ofSeconds(2));
    }

    public record InstanceView(
            String instanceId,
            String zone,
            String hint,
            String weight,
            String receivedHint,
            String port
    ) {}
}
~~~

Điểm quan trọng:

- `hint` là query parameter của **API demo caller**, sau đó caller chủ động gắn thành header `X-SC-LB-Hint` cho HTTP request xuống inventory. Đừng nhầm hai lớp dữ liệu.
- `null` nghĩa là caller **không gửi header hint**. Trong lab cũng chưa đặt hint mặc định ở properties.
- `blue` và `green` là các giá trị hợp lệ. `unknown` được **cho phép có chủ đích để test fallback**, không phải giá trị rollout production.
- `DEMO_HINTS` chỉ là allowlist cho lab. Production phải lấy hint từ quyết định trusted routing policy (feature flag, phân bổ rollout, quyền đã xác thực), không sao chép header ngoài Internet một cách mù quáng.
- `.timeout(Duration.ofSeconds(2))` là giới hạn cho reactive publisher này. Không đồng nghĩa mọi backend code sẽ dừng khi client timeout.
- Backend nhận header có thể dùng nó để echo, nhưng **chỉ việc backend thấy header không chứng minh** LoadBalancer đã lọc đúng; cần xem `instanceId` trong response.

### Header hint trong supplier được đọc ở đâu?

Spring Cloud `HintBasedServiceInstanceListSupplier` kiểm tra hint trong `Request` context; với đường WebClient-backed LoadBalancer, client request headers có thể được đưa vào `RequestDataContext`. Khi có header `X-SC-LB-Hint`, supplier dùng giá trị để tìm metadata `hint` của các `ServiceInstance`.

Nếu không có header, supplier có thể lấy hint từ properties như:

~~~yaml
spring:
  cloud:
    loadbalancer:
      hint:
        default: blue
~~~

Ngoài default, Spring Cloud còn hỗ trợ hint theo service ID thông qua `spring.cloud.loadbalancer.hint.[SERVICE_ID]`. Tuy nhiên, **không thêm default vào lab cơ bản** nếu mục tiêu là quan sát “không hint” trả toàn bộ danh sách.

Tên header mặc định là `X-SC-LB-Hint`; có thể đổi bằng `spring.cloud.loadbalancer.hint-header-name`. Khi đổi, nhớ đồng bộ tên ở WebClient và test.

## 10. Build và chạy caller

Trong một terminal khác:

~~~powershell
cd routing-lab/caller
mvn -q -DskipTests package
java -jar target/routing-caller-0.0.1-SNAPSHOT.jar --lab.routing.mode=zone
~~~

Dùng tên JAR thực tế của dự án nếu khác ví dụ. Caller cần chạy tại cổng 8080; nếu bị chiếm, thay `server.port` và sửa URL ở các lệnh test.

Kiểm tra lần đầu:

~~~powershell
Invoke-RestMethod "http://localhost:8080/route"
~~~

Ví dụ một response (chỉ là minh họa):

~~~json
{
  "instanceId": "hcm-blue-b",
  "zone": "hcm",
  "hint": "blue",
  "weight": "1",
  "receivedHint": null,
  "port": "8082"
}
~~~

Response thực tế có thể chọn A hoặc C, tùy cursor Round Robin. Điều cần kiểm tra ở mode `zone` là **D (hn)** không được chọn **khi vẫn có A/B/C** và discovery/supplier đã nhận đúng metadata.

Khi đổi mode, **dừng và khởi động lại caller** với một trong các giá trị `zone`, `weighted`, `hint` hoặc `combined`. Đừng giả định thay biến `lab.routing.mode` qua một endpoint tự tạo sẽ làm bean `ServiceInstanceListSupplier` được dựng lại. Với cấu hình dạng `@ConditionalOnProperty` như ví dụ, đây là **quyết định khi khởi tạo ApplicationContext**.

## 11. Bài test A: chỉ bật vùng ưu tiên

Khởi động caller:

~~~powershell
java -jar target/routing-caller-0.0.1-SNAPSHOT.jar --lab.routing.mode=zone
~~~

Gửi 12 lần request không hint:

~~~powershell
1..12 | ForEach-Object {
    Invoke-RestMethod "http://localhost:8080/route" |
        Select-Object instanceId,zone,port
}
~~~

**Kỳ vọng về eligibility:**

~~~text
Eligible sau ZonePreference(hcm): A, B, C
D ở hn: không được chọn khi A/B/C còn trong danh sách

Nếu Round Robin và danh sách ổn định:
A, B, C, A, B, C ... (thứ tự bắt đầu có thể khác)
~~~

Không bắt buộc response đầu tiên phải là A: implementation Round Robin có thể dùng vị trí khởi đầu khác. Nếu thống kê đúng 12 selections trên 3 candidate ổn định, mỗi candidate có thể được chọn 4 lần.

### Khi zone không có instance khớp

Thử khởi động caller với override:

~~~powershell
java -jar target/routing-caller-0.0.1-SNAPSHOT.jar --lab.routing.mode=zone --spring.cloud.loadbalancer.zone=unknown-zone
~~~

`ZonePreferenceServiceInstanceListSupplier` **không fail closed** khi không có instance nào trong vùng mong muốn: nó **trả lại toàn bộ danh sách delegate**. Vì vậy, cả A/B/C/D có thể được chọn. Đây là **fallback ưu tiên về availability** của implementation, không phải cơ chế cưỡng chế cách ly dữ liệu theo vùng.

Nếu nghiệp vụ bắt buộc chỉ được chạy ở `hcm` do residency/compliance, **không được dùng ZonePreference mặc định làm kiểm soát an ninh duy nhất**. Cần một supplier hoặc policy hard filter đã được test để không có candidate khớp thì trả lỗi có chủ đích.

### Kịch bản zone thực tế

Trong hạ tầng multi-AZ, ưu tiên zone có thể giảm cross-AZ traffic và latency. Nhưng zone metadata phải phản ánh topology thật, mỗi zone cần có capacity phù hợp, và fallback cross-zone phải được phê duyệt. `localhost` trong lab chỉ giúp kiểm tra thuật toán, không đo latency giữa các vùng vật lý.

## 12. Bài test B: bật trọng số

Dừng caller mode zone, khởi động lại:

~~~powershell
java -jar target/routing-caller-0.0.1-SNAPSHOT.jar --lab.routing.mode=weighted
~~~

Trong mode này, **không có `withZonePreference()` và không có `withHints()`**: A/B/C/D đều đủ điều kiện. `WeightedServiceInstanceListSupplier` đọc metadata `weight`, rồi cung cấp danh sách có tính đến trọng số cho Round Robin.

Mục tiêu phân phối theo trọng số:

\[
p_i = \frac{w_i}{\sum_j w_j}
\]

Với `w_A=3, w_B=1, w_C=2, w_D=4`, tổng là 10:

| Instance | Weight | Tỷ lệ mục tiêu | Kỳ vọng trong 1.000 selections |
|---|---:|---:|---:|
| A | 3 | 30% | 300 |
| B | 1 | 10% | 100 |
| C | 2 | 20% | 200 |
| D | 4 | 40% | 400 |

Đây là mục tiêu từ metadata, **không phải log thực tế đã chạy**. Trong những số lượng mẫu đủ lớn và danh sách ổn định, số lần chọn nên phù hợp với cách weighted supplier hiện thực hóa weights; các giá trị có thể không phải y hệt từng count trong một cửa sổ ngắn.

Một điểm dễ nhầm: **weight không có nghĩa một request HTTP được lặp lại ba lần**. Nó thay đổi tỷ trọng cơ hội chọn instance, không nhân bản request nghiệp vụ hay tự điều chỉnh timeout.

### Kiểm tra bằng PowerShell

~~~powershell
$selected = 1..1000 | ForEach-Object {
    (Invoke-RestMethod "http://localhost:8080/route").instanceId
}

$selected | Group-Object | Sort-Object Name |
    Select-Object Name,Count,
        @{Name="Percent"; Expression={
            [math]::Round(100.0 * $_.Count / $selected.Count, 1)
        }}
~~~

So cột `Percent` với tỷ lệ mục tiêu 30%/10%/20%/40%, **không dùng ngay một lần chạy ngắn để khẳng định xác suất tuyệt đối**. Nếu weights bị bỏ qua và phân bố gần 25% mỗi instance trong nhiều mẫu độc lập, kiểm tra metadata `weight` và xác nhận đang chạy mode `weighted`, không phải `zone` hay default Round Robin.

### Weight không được dùng như công tắc tắt instance

Nếu `weight` thiếu, `WeightedServiceInstanceListSupplier` mặc định dùng 1. Các giá trị không hợp lệ/không dương có thể được fallback về default weight tùy implementation; đừng đặt `weight: "0"` rồi cho rằng replica chắc chắn nhận 0 traffic. Muốn drain instance, dùng discovery deregistration, health filtering hoặc policy có contract rõ ràng.

Trọng số 4:1 không tự bảo đảm replica lớn có năng lực thật gấp bốn. Trước khi dùng production, đo CPU, memory, queue, p99 latency và error rate theo instance; áp weights theo dữ liệu capacity và quan sát.

## 13. Bài test C: bật hint theo từng request

Dừng caller, chạy:

~~~powershell
java -jar target/routing-caller-0.0.1-SNAPSHOT.jar --lab.routing.mode=hint
~~~

Ở đây supplier chỉ lọc theo `hint`, **không** ưu tiên zone và **không** áp weight.

### Hint blue

~~~powershell
1..12 | ForEach-Object {
    Invoke-RestMethod "http://localhost:8080/route?hint=blue" |
        Select-Object instanceId,zone,hint,receivedHint
}
~~~

Tập ứng viên dự kiến: **A/B/D**, vì cả ba có metadata `hint: blue`; **C** không khớp. Với Round Robin và snapshot ổn định, A/B/D có thể nhận số lượt chọn gần bằng nhau.

### Hint green

~~~powershell
1..6 | ForEach-Object {
    Invoke-RestMethod "http://localhost:8080/route?hint=green" |
        Select-Object instanceId,zone,hint
}
~~~

Tập ứng viên dự kiến: **chỉ C**, do đó 100% request được LoadBalancer chọn C khi nó còn trong discovery và request không bị lỗi.

### Không có hint

~~~powershell
Invoke-RestMethod "http://localhost:8080/route"
~~~

Khi không có hint header và không có hint property, supplier mặc định **không lọc** theo metadata hint. Cả bốn replica A/B/C/D đều có thể được chọn.

### Hint không có match

~~~powershell
1..8 | ForEach-Object {
    Invoke-RestMethod "http://localhost:8080/route?hint=unknown"
}
~~~

Không replica nào có metadata `hint: unknown`. Theo behavior mặc định của `HintBasedServiceInstanceListSupplier`, nếu filtered list rỗng, nó trả lại **toàn bộ list của delegate**, không tự trả `EmptyResponse`. Vì vậy, một request mang hint unknown **vẫn có thể nhận response thành công từ A/B/C/D**.

**Hệ quả an toàn:** hint mặc định là một *preference*, không phải ranh giới phân quyền, tenancy hay version pin cứng. Với rollout mà request cho v2 **không được phép** đến v1, cần custom strict filter hoặc API routing/authentication khác có fail-closed behavior, không dựa vào supplier hint mặc định.

### Header đi qua network và header ảnh hưởng selection là hai ý khác nhau

`receivedHint` ở backend giúp kiểm tra header được gửi; tuy nhiên một response có `receivedHint: "blue"` từ C sẽ là dấu hiệu bất thường nếu mode hint đang lọc đúng. Hãy luôn kiểm tra **cả instance ID** và header echo.

Trong hệ thống thật, hint phải được quyết định từ một policy tin cậy. Không cho người dùng tự chọn replica chạy version cũ hoặc zone nhạy cảm bằng cách gửi header chưa được kiểm chứng.

## 14. Bài test D: ghép zone → hint → weight

Khởi động lại caller:

~~~powershell
java -jar target/routing-caller-0.0.1-SNAPSHOT.jar --lab.routing.mode=combined
~~~

Với zone `hcm`, supplier chain là:

~~~text
Discovery:       A, B, C, D
Zone preference: A, B, C
Hint:            lọc theo hint nếu tìm được match
Weight:          điều chỉnh tỷ lệ trong danh sách còn lại
Round Robin:     chọn instance
~~~

### D1. Hint = blue

~~~powershell
$selected = 1..400 | ForEach-Object {
    (Invoke-RestMethod "http://localhost:8080/route?hint=blue").instanceId
}

$selected | Group-Object | Sort-Object Name |
    Select-Object Name,Count,
        @{Name="Percent"; Expression={
            [math]::Round(100.0 * $_.Count / $selected.Count, 1)
        }}
~~~

Tập sau zone+hint là **A/B**. Trọng số A:B = 3:1. Tỷ lệ mục tiêu **75% A và 25% B**; C không khớp hint, D ngoài vùng ưu tiên, nên không kỳ vọng thấy hai ID đó nếu metadata và cấu hình đang hoạt động.

### D2. Hint = green

~~~powershell
1..12 | ForEach-Object {
    Invoke-RestMethod "http://localhost:8080/route?hint=green" |
        Select-Object instanceId,zone,hint
}
~~~

Tập sau zone+hint chỉ còn **C**. Trọng số C=2 không tạo thêm backend khác; tất cả selections hợp lệ đều tới C.

### D3. Không gửi hint

~~~powershell
1..12 | ForEach-Object {
    Invoke-RestMethod "http://localhost:8080/route" |
        Select-Object instanceId,zone,hint
}
~~~

Zone lọc thành **A/B/C**, hint trống nên giữ danh sách đó, weight mục tiêu **3:1:2**:

| Instance | Tỷ lệ mục tiêu trong `hcm` |
|---|---:|
| A | 50,0% |
| B | 16,7% |
| C | 33,3% |
| D | 0% khi zone hcm có ứng viên |

### D4. Hint = unknown

~~~powershell
Invoke-RestMethod "http://localhost:8080/route?hint=unknown"
~~~

Không instance nào trong danh sách A/B/C có hint unknown, nên `HintBasedServiceInstanceListSupplier` **fallback về danh sách delegate A/B/C**. Sau đó trọng số 3:1:2 vẫn áp dụng. Đây là behavior ưu tiên khả dụng nhưng **không phải strict match**.

### D5. Đổi caller zone

Dừng caller và chạy:

~~~powershell
java -jar target/routing-caller-0.0.1-SNAPSHOT.jar --lab.routing.mode=combined --spring.cloud.loadbalancer.zone=hn
~~~

Nếu zone `hn` có D, bước zone chỉ còn **D**. Với hint blue, D khớp nên D được chọn. Với hint green, **không có instance trong tập D khớp green**, nhưng HintBased supplier **fallback về D** (delegate list sau zone), nên request vẫn có thể đi tới D dù metadata hint của D là blue.

Bảng kỳ vọng:

| Caller zone | Hint request | Danh sách sau zone | Danh sách sau hint (có fallback) |
|---|---|---|---|
| hcm | blue | A, B, C | A, B |
| hcm | green | A, B, C | C |
| hcm | unknown | A, B, C | A, B, C |
| hcm | không có | A, B, C | A, B, C |
| hn | blue | D | D |
| hn | green | D | D (fallback, không hard match) |
| unknown-zone | blue | A, B, C, D (zone fallback) | A, B, D |

**Bài học về thứ tự và fallback:** zone preference là ưu tiên mềm, hint cũng là ưu tiên mềm. Nếu chính sách bắt buộc “chỉ instance zone X + version Y được xử lý”, cần một policy **cứng** khác có quy tắc khi không có ứng viên.


## 15. Tóm tắt ma trận kịch bản

Trước khi bước sang kiểm thử lỗi, ghi lại bảng phân phối **theo cấu hình đã chọn**. Đây là tài liệu tham chiếu cho acceptance tests; tỷ lệ chỉ là kỳ vọng khi snapshot ổn định, không có retry, không có lỗi và client dùng đúng supplier chain.

| Mode | Caller zone | Hint | Ứng viên hợp lệ cuối cùng | Tỷ lệ mục tiêu |
|---|---|---|---|---|
| zone | hcm | không có | A/B/C | Gần 1:1:1 |
| zone | hcm | green | A/B/C | Hint không có hiệu lực trong mode zone |
| weighted | hcm | không có | A/B/C/D | 3:1:2:4 |
| weighted | hcm | blue | A/B/C/D | Hint không có hiệu lực trong mode weighted |
| hint | hcm | blue | A/B/D | Gần 1:1:1 |
| hint | hcm | green | C | 100% C |
| hint | hcm | unknown | A/B/C/D | Fallback về toàn bộ list |
| hint | hcm | không có | A/B/C/D | Không filter khi không có default |
| combined | hcm | blue | A/B | 3:1 |
| combined | hcm | green | C | 100% C |
| combined | hcm | unknown | A/B/C | Fallback hint về zone-list, sau đó weight 3:1:2 |
| combined | hcm | không có | A/B/C | 3:1:2 |
| combined | hn | blue | D | 100% D |
| combined | hn | green | D | Hint fallback trong tập chỉ còn D |
| combined | unknown-zone | blue | A/B/D | Zone fallback toàn bộ rồi hint blue |

**Chú ý:** trong các mode không dùng hint supplier, việc controller gửi header `X-SC-LB-Hint` tới backend không làm nó tự thay đổi thuật toán. Tương tự, mode weighted không tự xét `spring.cloud.loadbalancer.zone`. Đừng suy từ “đã đặt property” sang “policy chắc chắn đang hoạt động”; **supplier chain phải chứa decorator tương ứng**.

## 16. Kiểm thử tự động bằng PowerShell

Bài lab có thể chạy test smoke mà không cần thêm framework test. Điều kiện trước: bốn backend đang chạy, caller được khởi động đúng mode và không có traffic khác làm thay đổi cửa sổ đếm.

### 16.1. Hàm lấy mẫu

~~~powershell
function Get-RoutingSamples {
    param(
        [int]$Count = 100,
        [string]$Hint = ""
    )

    $url = "http://localhost:8080/route"
    if ($Hint -ne "") {
        $url += "?hint=$([uri]::EscapeDataString($Hint))"
    }

    $samples = @(
        1..$Count | ForEach-Object {
            Invoke-RestMethod -Uri $url -TimeoutSec 5
        }
    )

    return $samples
}

function Show-RoutingDistribution {
    param([object[]]$Samples)

    $total = $Samples.Count
    $Samples | Group-Object -Property instanceId |
        Sort-Object Name |
        Select-Object Name,Count,
            @{Name="Percent"; Expression={
                [math]::Round(
                    100.0 * $_.Count / $total, 2
                )
            }}
}
~~~

Dùng trong mode `combined`:

~~~powershell
$samples = @(Get-RoutingSamples -Count 400 -Hint blue)
Show-RoutingDistribution -Samples $samples
~~~

Sau đó kiểm tra điều kiện **định tính**: chỉ thấy ID A hoặc B. Đừng bắt buộc 300 và 100 lượt đúng tuyệt đối trong một sample nếu implementation và chính sách retry có chi tiết khác.

### 16.2. Assertion cho hint green

~~~powershell
$green = @(Get-RoutingSamples -Count 30 -Hint green)

$invalid = @(
    $green | Where-Object {
        $_.instanceId -ne "hcm-green-c"
    }
)

if ($invalid.Count -gt 0) {
    throw "Combined green routing selected an unexpected instance"
}

"PASS: All green requests selected hcm-green-c"
~~~

Test này phù hợp khi mode combined chạy với `spring.cloud.loadbalancer.zone=hcm`, backend đầy đủ và không có các policy phụ khác. Nếu `zone=hn`, kết quả D là đúng theo fallback mềm nên assertion sẽ không còn phù hợp.

### 16.3. Assertion không chọn cross-zone khi có local candidates

~~~powershell
$zoneResults = @(Get-RoutingSamples -Count 60)

$crossZone = @(
    $zoneResults | Where-Object {
        $_.zone -ne "hcm"
    }
)

if ($crossZone.Count -ne 0) {
    throw "Zone preference returned a cross-zone backend"
}
~~~

Chạy assertion này với mode `zone` hoặc `combined` và zone hcm. Nếu bạn bật mode `weighted` hoặc `hint`, điều kiện này **không phải hợp đồng** và test có thể fail dù supplier hoạt động đúng.

### 16.4. Số lượng mẫu và false positives

Với phân phối ngẫu nhiên hoặc weighted, cần sample đủ lớn. Thay vì bắt buộc phần trăm chính xác, chọn độ lệch chấp nhận và quy tắc thống kê trước khi chạy.

Nếu mỗi request độc lập với xác suất mục tiêu `p`, kỳ vọng `Np` và độ lệch chuẩn `sqrt(Np(1-p))`. Tuy nhiên, `WeightedServiceInstanceListSupplier` kết hợp Round Robin không nhất thiết tương đương các Bernoulli trials độc lập; cách xây danh sách logic và thay đổi snapshot có thể làm phân bố mang tính xác định hơn. **Đừng dùng kiểm định binomial như bằng chứng tuyệt đối khi implementation không theo giả định độc lập.**

Trong CI, ưu tiên:

- Assert **không chọn ngoài eligibility set** bằng số lần request vừa đủ.
- Kiểm tra danh sách được lọc ở unit/component test.
- Kiểm tra **xu hướng weight** bằng sample tương đối lớn hoặc test supplier's logical weighted list, không hardcode thứ tự từng request.
- Lưu instance counts, mode, zone, hint và version Spring Cloud khi test fail.

## 17. Unit test mô hình metadata và chính sách

Phần HTTP integration chứng minh request đi đâu. Trước đó, có thể tạo `ServiceInstance` giả để kiểm tra đúng các metadata mà policy dùng. `DefaultServiceInstance` cho phép gắn metadata như trong registry.

~~~java
import org.springframework.cloud.client.DefaultServiceInstance;

DefaultServiceInstance instance = new DefaultServiceInstance(
        "hcm-blue-a",
        "inventory-service",
        "localhost",
        8081,
        false
);

instance.getMetadata().put("zone", "hcm");
instance.getMetadata().put("hint", "blue");
instance.getMetadata().put("weight", "3");
~~~

Với unit/component tests của supplier:

1. **Zone matching:** danh sách A/B/C/D → khi caller zone hcm, kết quả A/B/C.
2. **Zone no match:** caller zone unknown → kết quả A/B/C/D theo fallback mặc định.
3. **Hint blue:** danh sách A/B/C/D → A/B/D khi context mang header hint blue.
4. **Hint unknown:** danh sách A/B/C/D → giữ full delegate list.
5. **Combined blue:** sau zone hcm → A/B; weighted logic phản ánh 3:1.
6. **Combined green:** chỉ còn C.
7. **Weight missing:** fallback theo định nghĩa mặc định của `WeightedServiceInstanceListSupplier`.
8. **Empty discovery:** không có instance nào → LoadBalancer trả no-instance response, không tự sinh backend giả.
9. **Request context:** gọi `supplier.get(request)`, không chỉ `supplier.get()`, vì hint nằm trong request.
10. **Scope:** cấu hình của `inventory-service` không tự áp dụng cho `payment-service`.

**Điểm quan trọng:** một test chỉ gọi `supplier.get()` có thể không kiểm tra được hint theo request, vì `HintBasedServiceInstanceListSupplier` đọc `RequestDataContext` hoặc hint context tương ứng khi gọi `get(request)`. Hãy dùng request context thực tế từ transport hoặc dựng fixture đúng loại mà release train hỗ trợ, thay vì dùng một `DefaultRequest` rỗng rồi kết luận hint header bị bỏ qua.

Nếu dùng `StepVerifier` và `ServiceInstanceListSuppliers.toProvider(...)`, bạn có thể kiểm tra reactive result mà không khởi tạo web server. Đây là unit/component test, **không thay thế** bài test end-to-end qua `@LoadBalanced WebClient`.

## 18. Kịch bản lỗi: một replica ngừng hoạt động

Với caller mode combined, zone hcm, hint blue, tập ứng viên ban đầu là A/B. Thử dừng backend A ở cổng 8081 nhưng giữ nguyên cấu hình discovery tĩnh.

~~~text
Trước sự cố:
  A :8081 (chạy), B :8082 (chạy)

Sau sự cố:
  A :8081 (dừng), B :8082 (chạy)

SimpleDiscoveryClient của caller:
  VẪN CÒN A và B trong danh sách
~~~

Khi này, caller vẫn có thể chọn A và gặp connection refused/timeout. **Không được kết luận LoadBalancer tự chuyển toàn bộ traffic sang B** khi chưa có cơ chế loại A khỏi candidate list hoặc retry phù hợp.

Để quan sát:

~~~powershell
1..12 | ForEach-Object {
    try {
        Invoke-RestMethod "http://localhost:8080/route?hint=blue"
    }
    catch {
        Write-Host ("Request failed: " + $_.Exception.Message)
    }
}
~~~

Đây là test lỗi có chủ đích; tỷ lệ lỗi phụ thuộc cách weighted list tạo ra selections, trạng thái connection và timeout. Chạy lại backend A sau khi đo, hoặc cập nhật danh sách discovery của caller và **khởi động lại** để mô phỏng deregistration.

### Lọc instance không khỏe

Spring Cloud cung cấp `HealthCheckServiceInstanceListSupplier`. Nếu muốn thêm vào bài nâng cao, cần:

- Endpoint health ở backend, thường là `/actuator/health` khi bật Actuator.
- Một health-check supplier gần nguồn discovery trong chain.
- Tài nguyên HTTP client/health-check request factory phù hợp.
- Chu kỳ refresh/refetch rõ ràng; với `SimpleDiscoveryClient` tĩnh, cần hiểu lúc nào supplier làm mới danh sách.

Tài liệu Spring Cloud mô tả health-check supplier có thể **trả lại danh sách gốc khi không còn instance nào healthy** theo chính sách mặc định. Do vậy, nếu yêu cầu “không bao giờ gọi instance unhealthy” mang tính hard constraint, phải kiểm thử và cân nhắc một policy fail-closed riêng.

### Thử hiệu ứng zone fallback khi cả vùng mất

Nếu A/B/C bị dừng, `SimpleDiscoveryClient` vẫn liệt kê chúng. Zone preference hcm vẫn thấy metadata hcm và **không tự fallback sang D** chỉ vì kết nối thất bại. Chỉ khi danh sách đầu vào **không còn candidate thuộc hcm** (ví dụ registry/deregistration/health filtering cập nhật), `ZonePreferenceServiceInstanceListSupplier` mới fallback về các candidates khác.

Đây là khác biệt giữa:

- **Không có instance cùng zone trong candidate list** → zone preference fallback.
- **Có instance cùng zone trong candidate list nhưng HTTP bị lỗi** → không tự fallback, cần retry/health/discovery update.

## 19. Thử thay đổi trọng số khi đang chạy

Giả sử muốn giảm tải A từ weight 3 xuống 1. Với `SimpleDiscoveryClient` trong bài, sửa metadata ở YAML của caller **không tự bảo đảm** danh sách được cập nhật trong runtime; cách chắc chắn để thử lại là sửa config nguồn và **khởi động lại caller**.

Trong hệ thống có registry, quá trình có thể gồm:

~~~text
Capacity của instance thay đổi
    -> cập nhật metadata tại registry
    -> DiscoveryClient nhận phiên bản mới
    -> ServiceInstanceListSupplier/cache refresh
    -> weighted list được tính lại
    -> các selections tiếp theo mới phản ánh weight mới
~~~

Nếu tỷ lệ không thay đổi ngay:

- Kiểm tra registry metadata `weight` đã được publish đúng chưa.
- Kiểm tra cache TTL và tần suất refresh, tránh double caching.
- Kiểm tra mode thực sự là `weighted`/`combined`.
- Kiểm tra không có zone/hint filter loại instance có weight vừa sửa.
- Kiểm tra số mẫu và traffic từ nhiều caller instances.
- Kiểm tra metrics đo **selections** hay **HTTP completions**.
- Với weight bằng 0, không giả định đây là thao tác drain; cần remove/unregister hoặc filtering rõ ràng.

Vì vậy, `weight` là chính sách định tuyến dựa trên metadata, **không phải adaptive CPU autoscaler**. Nếu cần thay weights theo tải thời gian thực, hãy xây một control loop có nguồn metrics, smoothing, bounds và tránh dao động.

## 20. RestClient và OpenFeign có dùng cùng chính sách được không?

Có. `ServiceInstanceListSupplier` được cấu hình theo **service ID `inventory-service`**. Các HTTP clients có tích hợp Spring Cloud LoadBalancer và gọi đúng service ID có thể sử dụng child context tương ứng.

### RestClient

~~~java
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.web.client.RestClient;

@Bean
@LoadBalanced
RestClient.Builder loadBalancedRestClientBuilder() {
    return RestClient.builder();
}

@Bean
RestClient restInventory(
        @LoadBalanced RestClient.Builder builder) {

    return builder.clone()
            .baseUrl("http://inventory-service")
            .build();
}
~~~

Gọi có header:

~~~java
InstanceView response = restInventory.get()
        .uri("/whoami")
        .header("X-SC-LB-Hint", "blue")
        .retrieve()
        .body(InstanceView.class);
~~~

Với RestClient, cần dependency Spring Web và LoadBalancer thích hợp, tránh đăng ký **hai HTTP client builder beans có cùng tên/qualifier không rõ** nếu bạn triển khai cùng WebClient trong một ứng dụng. Hint-based filtering phụ thuộc request context mà integration đưa vào `ServiceInstanceListSupplier.get(request)`; hãy kiểm thử behavior thực tế thay vì suy từ việc header đã đến backend.

### OpenFeign

~~~java
import org.springframework.cloud.openfeign.FeignClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestHeader;

@FeignClient(name = "inventory-service")
public interface InventoryFeignClient {

    @GetMapping("/whoami")
    InstanceView whoami(
            @RequestHeader("X-SC-LB-Hint") String hint);
}
~~~

Khi dùng OpenFeign, thêm `spring-cloud-starter-openfeign`, bật `@EnableFeignClients` và đảm bảo không cấu hình `url` tĩnh nếu muốn route qua service ID. `@RequestHeader` truyền hint; việc LB supplier **thấy được request-specific hint** phải được xác minh trên phiên bản/integration transport thực tế. Nếu request context không mang header đến `HintBasedServiceInstanceListSupplier`, backend vẫn có thể thấy header nhưng việc lọc theo hint sẽ không xảy ra: lúc này cần adapter/policy thích hợp, không được ngộ nhận là đã route theo hint.

### Điều gì không thuộc trách nhiệm của LoadBalancer?

- Authentication/authorization: header hint không chứng minh user có quyền vào nhóm version hoặc zone.
- Connect/read timeout: do HTTP client/transport quản lý.
- Retry/backoff: cần cấu hình độc lập và giới hạn.
- Circuit breaker: quyết định khi nào ngừng thử một dependency lỗi/chậm, không tự chọn đúng hint.
- Trace propagation: do Micrometer/OpenTelemetry/instrumentation đảm nhiệm.
- Health: cần discovery/health-check supplier nếu muốn loại unhealthy instances.


## 21. Quan sát lựa chọn, HTTP attempts và metrics

Cần phân biệt **một request nghiệp vụ**, **một lần chọn instance** và **một HTTP attempt**. Khi bật retry, những con số này khác nhau:

~~~text
1 logical request
  -> LoadBalancer selection #1: A
  -> HTTP attempt #1: connect refused
  -> retry (nếu được bật và còn budget)
  -> LoadBalancer selection #2: B
  -> HTTP attempt #2: HTTP 200

Logical requests: 1
Selections:       2
HTTP attempts:    2
Responses:        1
~~~

Bài lab đặt `spring.cloud.loadbalancer.retry.enabled=false` để đơn giản hóa, nhưng nếu thêm retry tại WebClient, gateway hoặc HTTP transport, cần đếm riêng từng tầng.

Spring Cloud cung cấp `MicrometerStatsLoadBalancerLifecycle` khi có `MeterRegistry` và bật tính năng:

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

Một số meter được tài liệu mô tả:

| Meter | Ý nghĩa |
|---|---|
| `loadbalancer.requests.active` | Gauge của requests đang active |
| `loadbalancer.requests.success` | Timer các requests thành công về mặt transport/load-balancer lifecycle |
| `loadbalancer.requests.failed` | Timer các requests thất bại bằng exception |
| `loadbalancer.requests.discard` | Counter khi không lấy được instance để gửi |

Tên và tags thực tế phụ thuộc Spring Cloud release train và metrics registry. Các meter **không tự bảo đảm cung cấp tag “hint matched”**; để đo filter eligibility, có thể dùng unit/component test, debug logs được giới hạn hoặc `LoadBalancerLifecycle` tùy chỉnh.

Đừng gắn raw tenant/user ID, correlation ID, token hoặc URI chứa SKU động làm metric labels có cardinality không kiểm soát.

Nên đối chiếu:

- **Caller:** mode, zone, hint đã validate, logical requests, status và latency.
- **LoadBalancer:** số lựa chọn, instance ID được chọn, no-instance, lỗi selection.
- **Backend:** instance ID/port, hint nhận được, status và latency.
- **Retries:** số HTTP attempts độc lập với số logical requests.

Một response HTTP 200 không chứng minh **routing đúng policy**. Ví dụ `hint=unknown` fallback vẫn có thể trả 200 dù không có match metadata.

## 22. Khi nào zone và hint phải được thay bằng hard filter?

**Soft preference** phù hợp khi muốn tăng availability: không có instance cùng zone hoặc hint thì được phép gọi một ứng viên khác. Đó là hành vi mặc định của các supplier sử dụng trong bài.

**Hard isolation** cần thiết nếu:

- Dữ liệu chỉ được xử lý trong một khu vực pháp lý cụ thể.
- Canary version v2 không được phép gọi backend v1 vì contract không tương thích.
- Một workload chỉ được đến nhóm instances đã được cấp quyền riêng.
- Một tenant yêu cầu phân vùng dữ liệu hoặc chính sách tuân thủ nghiêm ngặt.

Trong những trường hợp này, không dựa vào zone/hint mặc định. Hãy dùng supplier có **điều kiện bắt buộc**, khi không có match phải trả empty/no-instance thay vì fallback toàn bộ:

~~~text
policy = resolveTrustedPolicy(authentication, deploymentConfig)
candidates = discoverySupplier.get(request)

eligible = candidates
    .filter(instance.zone == policy.requiredZone)
    .filter(instance.version == policy.requiredVersion)
    .filter(instance.allowedForWorkload)

if eligible.isEmpty():
    return EmptyResponse

return chooseWithWeight(eligible)
~~~

Đây là **pseudo-code**, không phải implementation Java hoàn chỉnh. Khi triển khai:

1. Lấy required zone/version từ nguồn **đã xác thực**, không tin raw `X-SC-LB-Hint` do người dùng Internet tự gửi.
2. Không chuyển vùng/phiên bản trái policy khi tập hợp eligible rỗng.
3. Propagate lỗi no-instance có kiểm soát; không tự tạo `ServiceInstance` giả.
4. Vẫn xác thực và phân quyền tại backend; routing không thay thế security.
5. Test quyền truy cập, sai metadata, registry không trả dữ liệu, retry và fallback riêng.
6. Kiểm tra metadata `ServiceInstance.getMetadata()` đến từ registry được quản lý, không phải từ request do user tự điều khiển.

## 23. Chi phí và giới hạn của chuỗi supplier

| Tầng | Công việc | Cần quan sát |
|---|---|---|
| Discovery | Lấy danh sách ứng viên | Registry latency, consistency, refresh |
| Caching | Lưu snapshot tránh gọi registry liên tục | TTL, stale values, cache placement |
| Zone preference | Lọc danh sách theo metadata zone | O(n) trên danh sách được xét |
| Hint filtering | Lọc theo request hint | O(n), request-aware context |
| Weighted supplier | Đọc weight, tạo danh sách logic có trọng số | Memory/CPU và weight refresh |
| Round Robin | Lấy một index trên list có sẵn | Thường O(1) theo n |
| HTTP transport | Connect, TLS, request, response | Pool wait, timeout, p95/p99 |

Các ước lượng Big-O là mô hình thông dụng, không phải benchmark đã chạy. Với bốn instances, cost filter có thể rất nhỏ so với HTTP latency. Khi tăng lên hàng trăm instances và nhiều caller replicas:

- Đặt cache sau discovery retrieval nếu cần, tránh cache nhầm kết quả lọc theo request.
- Giới hạn cardinality của các metric labels.
- Không tạo weights ngẫu nhiên khác nhau ở mỗi call nếu mục tiêu là tỷ lệ ổn định.
- Không thêm nhiều tầng retry khi zone outage làm backend khác chịu tải cao.
- Đo p95/p99 latency và error rate, không chỉ phần trăm phân phối.
- Lập kế hoạch rollback policy khi tạo hotspot hoặc tăng cross-zone traffic.

Weight không phải autoscaling: một replica có weight cao không có nghĩa CPU của nó luôn thấp hoặc backend có thể xử lý gấp nhiều lần.

## 24. Bảng xử lý sự cố

| Hiện tượng | Nguyên nhân thường gặp | Cách kiểm tra |
|---|---|---|
| `UnknownHostException: inventory-service` | WebClient chưa có LoadBalancer filter hoặc thiếu starter | `@LoadBalanced` bean và dependency |
| Luôn chọn một replica | Chỉ còn một candidate sau filtering hoặc mode sai | Mode, zone, hint, supplier chain |
| Zone hcm nhưng chọn D | Không áp zone, thiếu metadata hoặc zone fallback | `spring.cloud.loadbalancer.zone` và metadata instance |
| Hint blue nhưng chọn C | Header không đến request context hoặc supplier hint không chạy | `withHints()`, `get(request)`, integration |
| Hint unknown vẫn có kết quả | HintBased fallback về delegate list | Behavior dự kiến, không phải strict match |
| Zone unknown chọn A/B/C/D | ZonePreference fallback về full list | Hard filter nếu không cho phép cross-zone |
| Weighted gần đều 25% | Mode sai hoặc metadata `weight` không được đọc | Mode weighted và metadata source |
| Weight bằng 0 vẫn chọn | Invalid/nonpositive weight có thể fallback mặc định | Dùng deregistration/health để drain |
| Combined blue chọn D | Zone không được áp dụng hoặc fallback đầu vào | Metadata, zone, thứ tự chain |
| Backend nhận `receivedHint=blue` nhưng routing sai | Header trên wire không bảo đảm supplier nhận context | Kiểm tra RequestDataContext và client integration |
| Đổi YAML weights nhưng không đổi phân phối | SimpleDiscoveryClient tĩnh, cache cũ, restart chưa có | Restart caller hoặc theo dõi registry/cache refresh |
| Dừng A nhưng vẫn gọi A | Danh sách discovery chưa loại A | Health/discovery, retry budget và timeout |
| HTTP 200 nhưng sai nhóm version | Soft hint fallback | Dùng strict version routing |
| Feign bỏ qua LoadBalancer | Feign URL tĩnh hoặc thiếu integration | `@FeignClient(name)`/`url` |
| Không thấy metric | Chưa có MeterRegistry/Actuator hoặc chưa phát request | Dependencies, toggle và endpoint |
| Backend nhận số requests lệch selection count | Retry hoặc lỗi connect xảy ra trước backend | Đếm logical/selection/attempt riêng |

Trình tự chẩn đoán: xác nhận bốn backend chạy → kiểm tra discovery list/metadata tại caller → xác nhận mode và supplier bean → đối chiếu zone/hint context → quan sát weighted list → kiểm tra lỗi HTTP/retry. Đừng sửa Round Robin trước khi biết **danh sách candidates cuối cùng**.

## 25. Bài tập nâng cao

**Bài 1 — Thay zone caller:** chạy combined ở `hn`, gửi hint green và giải thích vì sao D vẫn được chọn.

**Bài 2 — Thay weights:** đổi A:B:C:D thành 1:3:2:4, restart caller và đo lại mode weighted. Báo cáo tỷ lệ trên ba lần lấy mẫu và độ biến thiên.

**Bài 3 — Strict hint:** tạo custom decorator không fallback toàn bộ khi không match. Kỳ vọng unknown hint dẫn tới no-instance thay vì backend bất kỳ.

**Bài 4 — Backend chết:** dừng A, bật health supplier hoặc registry có deregistration. Đo thời gian A biến mất khỏi candidate list và thời điểm A được chọn trở lại sau recovery.

**Bài 5 — RestClient/OpenFeign:** sử dụng cùng cấu hình per-service supplier, gửi hint blue và kiểm tra request context có thực sự đến supplier trong version đang dùng không.

**Bài 6 — Canary:** dùng metadata stable/canary cùng một trusted rollout policy; giải thích vì sao soft hint không đủ khi hai versions có schema không tương thích.

**Bài 7 — Hai caller replicas:** chạy caller 8080 và 8090, đo counts riêng. Round Robin cursor mỗi caller có thể độc lập; tổng hệ thống không nhất thiết luân phiên toàn cục.

**Bài 8 — Tail latency:** tạo backend nhanh/chậm giả lập, so p95/p99 ở zone, weighted và combined. Đánh giá traffic distribution cùng capacity, không kết luận chỉ từ raw request counts.

## 26. Tiêu chí nghiệm thu

| Hạng mục | Điều kiện PASS |
|---|---|
| Backend | Bốn ports 8081–8084 trả `instanceId` và metadata echo đúng |
| Discovery | Caller nhìn thấy bốn ServiceInstance cùng metadata tương ứng |
| Zone | hcm và A/B/C có sẵn: zone mode không chọn D |
| Weight | Mode weighted áp dụng metadata và phân bố hướng đến 3:1:2:4 |
| Hint blue | Hint mode chọn trong A/B/D |
| Hint green | Hint mode chỉ chọn C |
| Combined blue | hcm → A/B, tỷ lệ mục tiêu 3:1 |
| Combined green | hcm → C |
| No hint | Hint mode không filter, combined+hcm giữ A/B/C |
| Unknown hint | Có fallback đúng như delegate, không nhầm là hard match |
| Unknown zone | Zone fallback về toàn bộ list được quan sát và giải thích |
| Backend down | Hiểu stale discovery và giới hạn của health/retry |
| Security | Không dùng zone/hint mềm thay authentication/authorization |
| Metrics | Phân biệt logical requests, selections và HTTP attempts |
| Code scope | Configuration chỉ áp dụng cho `inventory-service` |

Một bài lab hoàn thành không yêu cầu tỷ lệ weighted **chính xác tuyệt đối** trong cửa sổ ngắn. Nghiệm thu kết hợp kiểm tra membership, xu hướng tỷ trọng và behavior khi thiếu instance.

## 27. Checklist trước khi production

- [ ] Metadata zone/hint/weight có nguồn registry đáng tin cậy và chính sách cập nhật rõ ràng.
- [ ] Zone caller thực sự phản ánh topology; fallback cross-zone được phê duyệt.
- [ ] Phân biệt soft preference và hard isolation.
- [ ] Hint chỉ được gắn từ trusted routing decision; đầu vào user được validate.
- [ ] Cấu hình `@LoadBalancerClient` per-service không bị component scan global.
- [ ] Không dùng weight=0 như công tắc tắt replica khi chưa kiểm chứng implementation.
- [ ] Cache/health supplier đặt đúng thứ tự, không làm rò context của hint qua request khác.
- [ ] Đã kiểm thử đúng loại HTTP client được triển khai (WebClient/RestClient/OpenFeign).
- [ ] Có timeout, retry bounded, circuit breaker và idempotency phù hợp.
- [ ] Có kế hoạch cho zone outage, instance chết và metadata stale.
- [ ] Metrics có giới hạn cardinality, không log token hoặc thông tin user nhạy cảm.
- [ ] Load test chứng minh p95/p99, error rate và capacity không suy giảm khi dùng policy mới.
- [ ] Có rollback về policy đơn giản khi phân phối gây hotspot.

## Tài liệu tham khảo

- [Spring Cloud Commons — Spring Cloud LoadBalancer](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html): `ZonePreferenceServiceInstanceListSupplier`, `WeightedServiceInstanceListSupplier`, `HintBasedServiceInstanceListSupplier` và metrics.
- [Spring Cloud Commons — Common Abstractions](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html): `SimpleDiscoveryClient` và cấu hình instance.
- [Spring Cloud Commons — Configuration Properties](https://docs.spring.io/spring-cloud-commons/reference/configprops.html): zone, hint header, caching/retry và thống kê.
- [Spring Cloud — Project and Version Compatibility](https://spring.io/projects/spring-cloud/): lựa chọn release train phù hợp Spring Boot.
- [Spring Framework — WebClient](https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html): request headers và reactive HTTP.
- [Spring Cloud OpenFeign](https://docs.spring.io/spring-cloud-openfeign/reference/spring-cloud-openfeign.html): gọi theo service ID và Feign integration.

**Kết luận:** zone, weight và hint là ba chính sách **khác mục đích**, nhưng có thể ghép vào `ServiceInstanceListSupplier` trước bộ chọn Round Robin. Zone ưu tiên vùng gần, weight điều chỉnh tỷ trọng theo năng lực, hint ưu tiên nhóm replica theo request. Quan trọng nhất, **zone và hint mặc định là preference có fallback**, không phải ranh giới bảo mật. Hãy nghiệm thu từng mode độc lập, kiểm tra thứ tự ghép, tập ứng viên cuối cùng, thống kê và hành vi khi có lỗi trước khi triển khai thực tế.



