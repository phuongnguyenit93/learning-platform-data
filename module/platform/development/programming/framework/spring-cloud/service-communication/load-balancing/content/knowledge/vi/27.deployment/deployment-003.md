# Dùng discovery hoặc danh sách tĩnh trong Docker Compose

Khi triển khai microservices bằng **Docker Compose**, các container có thể tìm nhau qua **DNS nội bộ** bằng tên service như `catalog-service`. Nhưng điều này **không đồng nghĩa** Spring Cloud LoadBalancer đã có danh sách `ServiceInstance` để tự chọn bản sao. Tùy kiến trúc, bạn có thể:

1. Khai báo **danh sách instance tĩnh** bằng `SimpleDiscoveryClient`, ví dụ `catalog-a:8081` và `catalog-b:8081`.
2. Sử dụng **service registry động** như Eureka/Consul để từng container đăng ký, cập nhật và rút khỏi danh sách instance.
3. Gọi trực tiếp **tên service DNS của Compose** và để Docker/network hoặc proxy quyết định cách kết nối; lúc này có thể **không dùng Spring Cloud LoadBalancer**.

Bài trong chương **Triển khai** này thực hành hai phương án đầu, đồng thời giải thích rõ phương án thứ ba. Phạm vi là Spring Cloud LoadBalancer ở **phía client**, dùng `RestClient` gọi `catalog-service` từ `order-service`, kiểm chứng discovery, health/failure, cache và các ranh giới HTTP transport. Kiến thức áp dụng tương tự cho `WebClient` và OpenFeign khi chúng được tích hợp đúng.

> Tất cả ví dụ là môi trường local/dev. Trước khi áp dụng cho production, cần xem xét authentication của registry, TLS, readiness/health, điều phối nhiều host, resource limits và phương án khôi phục. Compose thuận tiện cho lab/môi trường nhỏ, không tự cung cấp toàn bộ chức năng của một nền tảng điều phối.

## 1. Phân biệt ba lớp: Compose DNS, DiscoveryClient và LoadBalancer

Giả sử `order-service` muốn gọi `GET /whoami` trên một bản sao `catalog-service`.

~~~mermaid
flowchart TD
    A["order-service<br/>RestClient: http://catalog-service/whoami"]
    B["Spring Cloud LoadBalancer<br/>chọn ServiceInstance"]
    C["DiscoveryClient / InstanceListSupplier"]
    D["Static list hoặc Eureka registry"]
    E["HTTP transport<br/>pool, DNS, TCP, timeout"]
    F["catalog instance A"]
    G["catalog instance B"]
    A --> B
    B <--> C
    C <--> D
    B --> E
    E --> F
    E --> G
~~~

Trong sơ đồ, **một request chỉ chọn một instance**, không gửi đồng thời tới cả A và B. LoadBalancer chọn một URI vật lý trước khi HTTP transport thực thi.

| Thành phần | Trách nhiệm | Không tự làm |
|---|---|---|
| **DNS nội bộ Compose** | Cho container phân giải tên service/container trong network thành IP | Không tự điền danh sách vào Spring `DiscoveryClient` |
| **`SimpleDiscoveryClient`** | Trả danh sách `ServiceInstance` khai báo bằng property | Không tự biết container đã chết hoặc có replica mới |
| **Eureka/Consul** | Theo dõi đăng ký/deregistration và trả danh sách instance theo cơ chế registry | Không cam kết mọi thay đổi được client nhìn thấy ngay |
| **`ServiceInstanceListSupplier`** | Lấy/có thể cache, lọc, sắp xếp danh sách instance | Không thực thi TCP hoặc giải mã response |
| **Spring Cloud LoadBalancer** | Chọn một `ServiceInstance` từ danh sách | Không thay connection pool, timeout, retry hay authorization |
| **HTTP transport** | Phân giải hostname vật lý nếu cần, mượn pool, TCP/TLS, gửi HTTP | Không quyết định discovery policy nếu chưa được gắn LB |

Cần nhớ hai URL sau **có thể trông giống nhau nhưng đi qua tầng khác nhau**:

~~~java
// Được tạo từ @LoadBalanced RestClient.Builder:
// "catalog-service" là service ID dùng cho Spring Cloud LoadBalancer.
RestClient clientSideLb = lbBuilder
        .baseUrl("http://catalog-service")
        .build();

// RestClient thường:
// "catalog-service" là hostname cho DNS/HTTP transport.
RestClient directDns = RestClient.create("http://catalog-service:8081");
~~~

Một DNS hostname của Compose có thể phân giải ra nhiều container khi service được scale. Tuy nhiên, DNS caching, connection reuse và thuật toán phía network khiến phân phối thực tế **không tương đương round-robin do Spring Cloud LoadBalancer quyết định**.

## 2. Lựa chọn tĩnh hay registry động?

| Tiêu chí | Danh sách tĩnh / SimpleDiscoveryClient | Registry động / Eureka |
|---|---|---|
| Mục tiêu | Local/dev, ít instance, topology ít thay đổi | Nhiều replicas, thường xuyên scale/recreate |
| Dịch vụ bổ sung | Không cần server registry | Phải triển khai và vận hành registry |
| Tên service ID | Do caller định nghĩa trong config | Do app đăng ký với registry cung cấp |
| Thêm/bớt instance | Sửa cấu hình và reload/redeploy phù hợp | Instance đăng ký/rút; caller cập nhật sau các chu kỳ |
| Container IP đổi khi recreate | Nên dùng **DNS name ổn định** thay vì IP cố định | Registry phải quảng bá IP/hostname mới có thể truy cập |
| Health/liveness | Không có thông tin sống/chết động mặc định | Registry có lease/health semantics; có độ trễ |
| Khả năng test độc lập | Rất cao, dễ tái hiện | Cần registry hoặc fake registry |
| Nguy cơ | Danh sách stale, không tự biết scale | Phụ thuộc registry, lease/cache, instance registration sai |
| Độ phức tạp | Thấp | Trung bình đến cao |

**Quy tắc thực dụng:** bắt đầu bằng danh sách tĩnh nếu chỉ có hai backend định danh ổn định trong Compose. Chuyển sang registry khi cần **thay đổi membership mà không sửa danh sách trong từng caller**. Không thêm Eureka chỉ để “có service name” nếu Docker DNS đã đáp ứng yêu cầu vận hành và bạn không cần client-side selection.

## 3. Mô hình bài thực hành và chuẩn bị source

Ta xây một repository lab có ba module tùy chọn:

~~~text
compose-loadbalancer-demo/
├── settings.gradle.kts
├── compose-static.yml
├── compose-eureka.yml
├── catalog-service/
│   ├── Dockerfile
│   ├── build.gradle.kts
│   └── src/main/
│       ├── java/com/example/catalog/
│       │   ├── CatalogApplication.java
│       │   └── CatalogController.java
│       └── resources/
│           ├── application.yml
│           ├── application-compose-static.yml
│           └── application-compose-eureka.yml
├── order-service/
│   ├── Dockerfile
│   ├── build.gradle.kts
│   └── src/main/
│       ├── java/com/example/orders/
│       │   ├── OrderApplication.java
│       │   ├── CatalogClientConfiguration.java
│       │   └── ProbeController.java
│       └── resources/
│           ├── application.yml
│           ├── application-compose-static.yml
│           └── application-compose-eureka.yml
└── eureka-server/
    ├── Dockerfile
    ├── build.gradle.kts
    └── src/main/
        ├── java/com/example/registry/EurekaServerApplication.java
        └── resources/application-compose-registry.yml
~~~

**`eureka-server` chỉ cần cho phương án registry động.** Nếu chỉ chạy danh sách tĩnh, không phải khởi động module này.

### Dependency và phiên bản

Các đoạn Gradle Kotlin DSL dưới đây minh họa dependency quan trọng. Project cần cấu hình repository, plugin versions và **Spring Cloud BOM tương thích với Spring Boot** tại root.

**catalog-service:**

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")

    // Cần cho mode Eureka; được tắt bằng profile compose-static.
    implementation("org.springframework.cloud:spring-cloud-starter-netflix-eureka-client")
}
~~~

**order-service:**

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    implementation("org.springframework.cloud:spring-cloud-starter-loadbalancer")

    // Có trong cùng artifact để thử mode registry.
    implementation("org.springframework.cloud:spring-cloud-starter-netflix-eureka-client")

    testImplementation("org.springframework.boot:spring-boot-starter-test")
}
~~~

**eureka-server:**

~~~kotlin
dependencies {
    implementation("org.springframework.cloud:spring-cloud-starter-netflix-eureka-server")
}
~~~

Tại mỗi module, tạo bootable jar với tên ổn định để Dockerfile copy đúng. Ví dụ cho `catalog-service`:

~~~kotlin
import org.springframework.boot.gradle.tasks.bundling.BootJar

tasks.named<BootJar>("bootJar") {
    archiveFileName.set("catalog-service.jar")
}
~~~

Tương tự đặt `order-service.jar` và `eureka-server.jar` ở hai module kia. Chọn JDK phù hợp dependency; ví dụ Dockerfile tiếp theo dùng Java 21. **Không giả định mọi phiên bản Spring Boot/Spring Cloud hỗ trợ Java/runtime giống nhau**; đối chiếu compatibility matrix của release train.

## 4. Mã catalog-service dùng chung cho cả hai phương án

### 4.1. Spring Boot application

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

### 4.2. Endpoint cho biết instance nào đã xử lý

~~~java
package com.example.catalog;

import java.util.UUID;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class CatalogController {

    private final String instanceId;

    CatalogController(
            @Value("${demo.instance-id:}") String configuredId) {

        this.instanceId = configuredId == null
                || configuredId.isBlank()
                ? UUID.randomUUID().toString().substring(0, 8)
                : configuredId;
    }

    @GetMapping("/whoami")
    CatalogReply whoami() {
        return new CatalogReply(instanceId, "catalog-service");
    }

    record CatalogReply(String instanceId, String service) {}
}
~~~

Trong phương án tĩnh, hai container sẽ truyền `DEMO_INSTANCE_ID=catalog-a` và `catalog-b`. Trong phương án Eureka, nếu không truyền ID, ứng dụng sinh một giá trị ngắn cho **mỗi tiến trình**, đủ để phân biệt response trong lab.

Đây chỉ là một endpoint debug. Đừng công khai topology hoặc định danh nội bộ không cần thiết trong API production.

### 4.3. application.yml của catalog

~~~yaml
spring:
  application:
    name: catalog-service

server:
  port: 8081
~~~

Tất cả replicas đều **lắng nghe cổng 8081 bên trong container**. Các container có network namespace riêng, nên không cần đổi `server.port` thành 8082 khi scale. Port trên host (nếu publish) là khái niệm khác.

## 5. Mã order-service gọi qua Spring Cloud LoadBalancer

### 5.1. Application

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

### 5.2. RestClient load-balanced

~~~java
package com.example.orders;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;

@Configuration(proxyBeanMethods = false)
class CatalogClientConfiguration {

    @Bean("catalogLbBuilder")
    @LoadBalanced
    RestClient.Builder catalogLbBuilder() {
        return RestClient.builder();
    }

    @Bean("catalogClient")
    RestClient catalogClient(
            @Qualifier("catalogLbBuilder")
            RestClient.Builder builder) {
        return builder
                .baseUrl("http://catalog-service")
                .build();
    }
}
~~~

`@LoadBalanced RestClient.Builder` được Spring Cloud gắn interceptor để xử lý **service ID**. Đó là yếu tố khác biệt với `RestClient.create("http://catalog-service")` thông thường, vốn có thể đi qua DNS thay vì Spring Cloud.

Trong ứng dụng Spring Boot có observability/customizers quan trọng, hãy cân nhắc tích hợp `RestClientBuilderConfigurer` hoặc builder do Boot quản lý; bài lab dùng builder tối giản để minh họa đường đi.

### 5.3. Endpoint thử nghiệm

~~~java
package com.example.orders;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.client.RestClient;

@RestController
class ProbeController {

    private final RestClient catalog;

    ProbeController(
            @Qualifier("catalogClient") RestClient catalog) {
        this.catalog = catalog;
    }

    @GetMapping("/probe/catalog")
    CatalogReply probe() {
        return catalog.get()
                .uri("/whoami")
                .retrieve()
                .body(CatalogReply.class);
    }

    record CatalogReply(String instanceId, String service) {}
}
~~~

Khi gọi từ host:

~~~text
GET http://localhost:8080/probe/catalog

{"instanceId":"catalog-a","service":"catalog-service"}
~~~

Ví dụ response trên là **minh họa**: bản sao được chọn thay đổi theo chính sách LoadBalancer. Không hardcode kỳ vọng lượt đầu tiên luôn là `catalog-a`.

### 5.4. application.yml của order

~~~yaml
spring:
  application:
    name: order-service

server:
  port: 8080
~~~

Chúng ta sẽ tách cấu hình `compose-static` và `compose-eureka` ở các mục sau; không khai báo cả hai danh sách instance tĩnh và Eureka một cách mơ hồ trong cùng một profile.

## 6. Dockerfile và cách build image

Trong mỗi module tạo một `Dockerfile` có cùng nội dung, giả định jar đã được tạo và đặt tên như mục 3:

~~~dockerfile
FROM eclipse-temurin:21-jre
WORKDIR /app
ARG JAR_FILE
COPY ${JAR_FILE} /app/app.jar
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

Các build context trong Compose nằm tại `./catalog-service`, `./order-service` hoặc `./eureka-server`; vì vậy `JAR_FILE` được hiểu tương đối từ đúng module đó. Không dùng Dockerfile này khi jar chưa được build.

Từ thư mục gốc project:

~~~powershell
./gradlew :catalog-service:bootJar :order-service:bootJar
~~~

Khi thử Eureka, build thêm:

~~~powershell
./gradlew :eureka-server:bootJar
~~~

**Lưu ý về production:** dùng image được version-tag, non-root user, image scanning, secret management và build pipeline được kiểm soát. `eclipse-temurin:21-jre` phù hợp cho demo nhưng không thay cho chính sách bảo mật image của tổ chức.

## 7. Phương án A — Danh sách tĩnh với SimpleDiscoveryClient

### 7.1. Docker Compose tạo hai service có tên riêng

Tạo `compose-static.yml`:

~~~yaml
services:
  catalog-a:
    build:
      context: ./catalog-service
      args:
        JAR_FILE: build/libs/catalog-service.jar
    environment:
      SPRING_PROFILES_ACTIVE: compose-static
      DEMO_INSTANCE_ID: catalog-a
    expose:
      - "8081"

  catalog-b:
    build:
      context: ./catalog-service
      args:
        JAR_FILE: build/libs/catalog-service.jar
    environment:
      SPRING_PROFILES_ACTIVE: compose-static
      DEMO_INSTANCE_ID: catalog-b
    expose:
      - "8081"

  order-service:
    build:
      context: ./order-service
      args:
        JAR_FILE: build/libs/order-service.jar
    environment:
      SPRING_PROFILES_ACTIVE: compose-static
    ports:
      - "127.0.0.1:8080:8080"
    depends_on:
      - catalog-a
      - catalog-b
~~~

Compose mặc định tạo network nội bộ dùng chung. Từ container `order-service`:

- `catalog-a` là hostname DNS của service Compose `catalog-a`.
- `catalog-b` là hostname DNS của service Compose `catalog-b`.
- Cả hai cùng mở **container port 8081**, không có xung đột.
- Chỉ `order-service` được publish ra host trên localhost port 8080.

`expose` chủ yếu dùng để mô tả các port nội bộ; với mạng Compose mặc định, các container cùng network có thể kết nối vào cổng đang lắng nghe mà **không cần publish** port ra host. `expose` không tự mở một host port.

### 7.2. Disable Eureka client trong static mode

Vì dependency Eureka client được đưa vào jar để dùng ở mode B, ta cần tắt nó trong profile tĩnh.

Trong `catalog-service/src/main/resources/application-compose-static.yml`:

~~~yaml
eureka:
  client:
    enabled: false
~~~

Trong `order-service/src/main/resources/application-compose-static.yml`:

~~~yaml
eureka:
  client:
    enabled: false

spring:
  cloud:
    discovery:
      client:
        simple:
          instances:
            catalog-service:
              - uri: http://catalog-a:8081
              - uri: http://catalog-b:8081
    loadbalancer:
      cache:
        enabled: false
      retry:
        enabled: false
~~~

Đây là cấu hình trọng tâm:

~~~text
serviceId = "catalog-service"

ServiceInstance 1: uri=http://catalog-a:8081
ServiceInstance 2: uri=http://catalog-b:8081
~~~

Spring Cloud LoadBalancer sẽ lấy **danh sách này** khi caller dùng service ID `catalog-service`. **Docker DNS chỉ phân giải các hostname vật lý** `catalog-a` và `catalog-b` ở bước HTTP transport, chứ không cung cấp hai item trong danh sách cho `SimpleDiscoveryClient`.

`spring.cloud.loadbalancer.cache.enabled=false` và `retry.enabled=false` là lựa chọn cho **lab quan sát một attempt**, không phải khuyến nghị tắt hai cơ chế trong production. Nếu dự án có retry từ một tầng khác, vẫn phải kiểm soát nó riêng.

### 7.3. Chạy mode tĩnh

Sau khi build jar:

~~~powershell
docker compose -f compose-static.yml up -d --build
docker compose -f compose-static.yml ps
~~~

Gửi request từ **host**:

~~~powershell
curl.exe -s http://127.0.0.1:8080/probe/catalog
~~~

Lặp lại bằng PowerShell:

~~~powershell
1..12 | ForEach-Object {
    (Invoke-RestMethod "http://127.0.0.1:8080/probe/catalog").instanceId
}
~~~

Khi cả hai backend hoạt động và không có policy khác, round-robin thông dụng thường đưa cả `catalog-a` và `catalog-b` vào tập kết quả. Không yêu cầu đúng thứ tự A-B-A-B hoặc tỉ lệ chính xác trên một số ít requests.

**Điểm cần chứng minh:** response `instanceId` đổi giữa hai giá trị, trong khi caller luôn gọi cùng URL logic `http://catalog-service` ở mã Java.

## 8. Thí nghiệm lỗi ở danh sách tĩnh

### 8.1. Dừng một replica

~~~powershell
docker compose -f compose-static.yml stop catalog-a
~~~

Sau đó gọi lại `/probe/catalog` nhiều lần. Lưu ý:

- `catalog-a` vẫn là một mục trong `spring.cloud.discovery.client.simple.instances.catalog-service`.
- Khi LoadBalancer chọn A, HTTP client có thể gặp `Connection refused`, connect timeout hoặc lỗi mạng tùy tình huống.
- Khi chọn B, request vẫn có thể thành công.
- Vì retry của LoadBalancer đang tắt, request chọn A không tự được bảo đảm thử tiếp B.

**Dừng container không tự chỉnh YAML của caller.** Cũng không được suy ra `cache.enabled=false` làm discovery list tự giảm còn một instance: nguồn dữ liệu vẫn tĩnh.

### 8.2. Loại A khỏi danh sách

Sửa riêng cấu hình `application-compose-static.yml` trong **project lab**:

~~~yaml
spring:
  cloud:
    discovery:
      client:
        simple:
          instances:
            catalog-service:
              - uri: http://catalog-b:8081
~~~

Sau khi build lại jar order và recreate container:

~~~powershell
./gradlew :order-service:bootJar
docker compose -f compose-static.yml up -d --build --force-recreate order-service
~~~

Lúc này caller chỉ biết B. Việc sửa file YAML nằm trong jar **không tự có hiệu lực với container đang chạy**; phải đóng gói/triển khai lại hoặc có một cơ chế refresh cấu hình thực sự được thiết kế.

### 8.3. Khi nào danh sách tĩnh đủ tốt?

- Hai hoặc vài instance có **service DNS name ổn định**.
- Không thay đổi membership thường xuyên.
- Môi trường lab/integration test cần kết quả lặp lại.
- Có đội vận hành kiểm soát việc thay đổi cấu hình và triển khai lại.
- Sự cố một instance có thể được xử lý bởi hệ thống khác hoặc có SLA phù hợp.

Nếu thường xuyên thêm/xóa replica, cập nhật danh sách trong từng caller vừa tốn công vừa dễ để lại dữ liệu stale; đó là lý do cân nhắc registry động.

## 9. Đừng nhầm static list với Compose DNS load balancing

Trong một Compose project có service:

~~~yaml
services:
  catalog-service:
    build: ./catalog-service
    expose:
      - "8081"
~~~

và chạy `docker compose up --scale catalog-service=2`, Docker có thể trả các địa chỉ container của những replica đó khi caller phân giải hostname `catalog-service` qua DNS.

Nhưng nếu caller tạo:

~~~java
RestClient dnsClient =
        RestClient.create("http://catalog-service:8081");
~~~

thì caller đang sử dụng **DNS-layer resolution**; Spring Cloud LoadBalancer **không được chứng minh là có tham gia**. DNS response, cache của JVM/HTTP resolver, connection keep-alive và cách áp dụng nhiều DNS records ảnh hưởng hành vi kết nối. **Không cam kết phân phối 50/50** từ DNS.

Ngược lại, với:

~~~java
RestClient lbClient = catalogLbBuilder
        .baseUrl("http://catalog-service")
        .build();
~~~

Spring Cloud phải có một **`ServiceInstanceListSupplier` thật** cho service ID. Việc Compose DNS biết hostname `catalog-service` không đồng nghĩa supplier có danh sách từng replica.

### Vì sao không nên liệt kê IP container vào static list?

Docker cấp IP động. Khi container được recreate, nó có thể nhận địa chỉ khác. Cấu hình:

~~~yaml
# Không khuyến nghị:
spring:
  cloud:
    discovery:
      client:
        simple:
          instances:
            catalog-service:
              - uri: http://172.20.0.7:8081
              - uri: http://172.20.0.8:8081
~~~

có thể hỏng sau khi recreate. Dùng tên Compose service/container network ổn định nếu chọn static list; hoặc dùng registry để lưu endpoint cập nhật.

## 10. Phương án B — Eureka làm registry động

Khi muốn chạy nhiều replica của **cùng một Compose service**, thay vì khai báo thủ công `catalog-a` và `catalog-b` trong caller, ta dùng Eureka.

~~~mermaid
flowchart TD
    E["eureka-server:8761<br/>Service Registry"]
    A["catalog-service replica 1<br/>:8081"]
    B["catalog-service replica 2<br/>:8081"]
    O["order-service:8080"]
    LB["Spring Cloud LoadBalancer"]
    A -->|"register / heartbeat"| E
    B -->|"register / heartbeat"| E
    O --> LB
    LB -->|"DiscoveryClient lấy instances"| E
    LB -->|"chọn 1 instance"| A
    LB -->|"hoặc chọn"| B
~~~

**Ưu điểm:** caller không phải có hai URI hardcode. Mỗi catalog instance tự quảng bá địa chỉ, còn Eureka client trong caller lấy danh sách đã đăng ký.

**Đánh đổi:** phải vận hành registry, bảo đảm instance quảng bá host/IP **truy cập được từ caller**, xử lý cập nhật không tức thời, cân nhắc registry outage và bảo mật giao tiếp.

### 10.1. Mã Eureka Server

Tại `eureka-server/src/main/java/com/example/registry/EurekaServerApplication.java`:

~~~java
package com.example.registry;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cloud.netflix.eureka.server.EnableEurekaServer;

@SpringBootApplication
@EnableEurekaServer
public class EurekaServerApplication {
    public static void main(String[] args) {
        SpringApplication.run(EurekaServerApplication.class, args);
    }
}
~~~

`eureka-server/src/main/resources/application-compose-registry.yml`:

~~~yaml
spring:
  application:
    name: eureka-server

server:
  port: 8761

eureka:
  client:
    register-with-eureka: false
    fetch-registry: false
~~~

Đây là registry **một node cho lab**. Trong production, cần thiết kế availability, truy cập dashboard, authentication/TLS, self-preservation/lease và kế hoạch phục hồi thay vì để registry đơn lẻ không được bảo vệ.

### 10.2. Cấu hình catalog tự đăng ký

Trong `catalog-service/src/main/resources/application-compose-eureka.yml`:

~~~yaml
spring:
  application:
    name: catalog-service

server:
  port: 8081

eureka:
  client:
    service-url:
      defaultZone: http://eureka-server:8761/eureka/
  instance:
    prefer-ip-address: true
    instance-id: "${spring.application.name}:${random.uuid}"
~~~

`eureka-server` là **Compose service name**, có DNS record trên network mặc định. `prefer-ip-address: true` yêu cầu Eureka client quảng bá IP thay vì hostname khi đăng ký. Điều này giúp caller kết nối trực tiếp tới từng container IP trên cùng Compose network, nếu IP đó thực sự truy cập được.

`instance-id` được làm duy nhất theo mỗi JVM bằng giá trị random của Spring Boot. Nó giúp tránh việc hai replica dùng cùng ID đăng ký; không phải cơ chế health hay định danh bền vững xuyên restart.

**Không dùng `localhost:8761` trong URL Eureka của container**, vì `localhost` lúc đó là chính catalog container, không phải container registry.

### 10.3. Cấu hình order lấy instance từ Eureka

Trong `order-service/src/main/resources/application-compose-eureka.yml`:

~~~yaml
eureka:
  client:
    service-url:
      defaultZone: http://eureka-server:8761/eureka/
    register-with-eureka: false
    fetch-registry: true

spring:
  cloud:
    loadbalancer:
      retry:
        enabled: false
      cache:
        enabled: false
~~~

Ở mode này **không khai báo** `spring.cloud.discovery.client.simple.instances.catalog-service`. Eureka cung cấp `DiscoveryClient` thực sự, và LoadBalancer dùng dữ liệu của discovery qua supplier.

`register-with-eureka: false` trên `order-service` chỉ minh họa caller không cần được các dịch vụ khác discovery. Nó **vẫn có thể fetch registry** để gọi catalog.

Lưu ý: Eureka client có cache danh sách registry riêng. Tắt LoadBalancer cache trong lab không xóa cache của Eureka client; cần hiểu độ trễ fetch/refresh khi quan sát failover.

## 11. Docker Compose cho Eureka và scale cùng một service

Tạo `compose-eureka.yml`:

~~~yaml
services:
  eureka-server:
    build:
      context: ./eureka-server
      args:
        JAR_FILE: build/libs/eureka-server.jar
    environment:
      SPRING_PROFILES_ACTIVE: compose-registry
    ports:
      - "127.0.0.1:8761:8761"

  catalog-service:
    build:
      context: ./catalog-service
      args:
        JAR_FILE: build/libs/catalog-service.jar
    environment:
      SPRING_PROFILES_ACTIVE: compose-eureka
    expose:
      - "8081"
    depends_on:
      - eureka-server

  order-service:
    build:
      context: ./order-service
      args:
        JAR_FILE: build/libs/order-service.jar
    environment:
      SPRING_PROFILES_ACTIVE: compose-eureka
    ports:
      - "127.0.0.1:8080:8080"
    depends_on:
      - eureka-server
      - catalog-service
~~~

**Không đặt `container_name` cho `catalog-service`**. Docker Compose không scale một service vượt một container nếu có `container_name` cố định.

**Không publish** `"8081:8081"` trên host cho catalog replicas ở mode này: hai container không thể cùng chiếm host port 8081. Mỗi container vẫn lắng nghe 8081 nội bộ và Eureka quảng bá endpoint tương ứng.

`depends_on` ở dạng đơn giản chủ yếu sắp xếp thứ tự khởi động/đóng; **không chứng minh Eureka hoặc catalog đã sẵn sàng phục vụ HTTP**. Trong lab, cho phép thời gian đăng ký đồng bộ và thử lại request. Hệ thống thực cần health/readiness và startup/retry policy có kiểm soát.

### Lệnh chạy

Trước hết dừng mode tĩnh nếu đang chạy để tránh trùng host port 8080:

~~~powershell
docker compose -f compose-static.yml down
~~~

Build các jar:

~~~powershell
./gradlew :catalog-service:bootJar :order-service:bootJar :eureka-server:bootJar
~~~

Start registry, caller và **hai replicas catalog**:

~~~powershell
docker compose -f compose-eureka.yml up -d --build --scale catalog-service=2
docker compose -f compose-eureka.yml ps
~~~

Kiểm tra Eureka dashboard tại `http://127.0.0.1:8761` trong local lab, hoặc quan sát registry qua log. Đợi đến khi Eureka thấy hai instance `CATALOG-SERVICE` và caller đã lấy danh sách.

Gọi caller từ host:

~~~powershell
curl.exe -s http://127.0.0.1:8080/probe/catalog
~~~

Lặp lại:

~~~powershell
1..20 | ForEach-Object {
    (Invoke-RestMethod "http://127.0.0.1:8080/probe/catalog").instanceId
}
~~~

Hai giá trị `instanceId` khác nhau chứng minh hai tiến trình backend đã phục vụ request. Không khẳng định thứ tự tuyệt đối hoặc tỉ lệ 50/50 dưới mọi điều kiện.

## 12. Vì sao mỗi replica phải có ID và địa chỉ đúng?

Để LoadBalancer gọi được từng instance, registry phải có:

~~~text
serviceId = catalog-service

instance-1:
  instanceId = catalog-service:<unique-id-1>
  host/IP    = <reachable-container-ip-1>
  port       = 8081

instance-2:
  instanceId = catalog-service:<unique-id-2>
  host/IP    = <reachable-container-ip-2>
  port       = 8081
~~~

Trong mode Eureka:

- `spring.application.name=catalog-service` cung cấp service name để đăng ký.
- `instance-id` phân biệt các replicas có cùng app name và port.
- `prefer-ip-address` giúp quảng bá IP container; điều quan trọng là **IP đó phải truy cập được từ order-service trên cùng network**.
- `server.port=8081` là port mà process thực sự lắng nghe trong container.

### Một lỗi đăng ký thường gặp

Container catalog đăng ký `localhost:8081` hoặc host port xuất bản không phù hợp. Eureka dashboard có thể hiện instance “UP”, nhưng caller kết nối vào `localhost` của chính nó và nhận `Connection refused`.

**Registry biết instance tồn tại không có nghĩa endpoint được quảng bá có thể truy cập từ caller.** Hãy kiểm tra địa chỉ instance thực sự trả về, không chỉ số lượng trong dashboard.

Khi triển khai nhiều host/network khác nhau, IP container của một Compose bridge network có thể không còn truy cập từ host khác. Khi đó cần một topology phù hợp hơn hoặc cách công bố địa chỉ/routing chính xác; `prefer-ip-address=true` không giải quyết được định tuyến xuyên mạng một cách thần kỳ.

## 13. Thực hành scale-down, scale-up và độ trễ discovery

Trong mode Eureka đang có hai replicas:

~~~powershell
docker compose -f compose-eureka.yml up -d --scale catalog-service=1
~~~

Compose sẽ giảm số container của service theo thao tác scale. Sau khi registry nhận deregistration hoặc lease/refresh cập nhật, caller sẽ có thể thấy **chỉ một** instance còn hợp lệ.

Dùng:

~~~powershell
docker compose -f compose-eureka.yml ps
docker compose -f compose-eureka.yml logs --tail=100 catalog-service
~~~

Quan sát từng khoảng thời gian:

1. Số container đang chạy trong Compose.
2. Số instance mà Eureka hiển thị.
3. Số instance mà `DiscoveryClient` của order-service trả về.
4. Instance ID xuất hiện trong response `/probe/catalog`.
5. Số lỗi kết nối khi một URI cũ chưa bị loại hoàn toàn.

Sau đó scale-up lại:

~~~powershell
docker compose -f compose-eureka.yml up -d --scale catalog-service=2
~~~

Đừng kỳ vọng **thay đổi tức thì**. Có nhiều thời gian trễ độc lập: khởi động ứng dụng, đăng ký Eureka, heartbeat/lease, registry fetch và cache của client/LoadBalancer.

### Stale instance và retry

Ngay sau khi một replica bị dừng, caller có thể vẫn chọn URI cũ và gặp lỗi. Bật retry có thể giúp trong một số tình huống tạm thời, nhưng:

- Không sửa được địa chỉ đăng ký sai.
- Không bảo đảm request đã bị server xử lý hay chưa nếu response mất.
- Không tự làm registry cập nhật ngay.
- Có thể nhân số HTTP attempts và tăng tải nếu không giới hạn.
- Với `POST` upload/ghi dữ liệu, phải xét idempotency và khả năng phát lại request body.

Trong lab ta tắt LB retry để phân biệt lỗi discovery với lỗi retry. Production cần timeout, retry có điều kiện, backoff, tổng deadline và observability phù hợp.

## 14. Health check, readiness và Docker Compose phụ thuộc startup

Ba loại health có ý nghĩa khác nhau:

| Cơ chế | Kiểm tra gì? | Hạn chế |
|---|---|---|
| Docker container running | Process/container có đang chạy | Không bảo đảm app đã sẵn sàng nhận HTTP |
| Compose healthcheck | Lệnh healthcheck chạy thành công | Cần thiết kế probe đúng và image có công cụ thực thi |
| Eureka registration/lease | Client đăng ký và cập nhật trạng thái | Cần thời gian phát hiện, có thể stale |
| Spring Cloud LB health supplier | Poll endpoint health của instance khi cấu hình | Có interval/semantics fallback riêng |
| Backend readiness | App có thể phục vụ request và dependency cần thiết sẵn sàng | Phải phản ánh điều kiện nghiệp vụ thực |

Một số điểm vận hành:

- Có thể dùng Spring Boot Actuator `/actuator/health` và healthcheck có kiểm soát, nhưng phải thêm dependency/cấu hình phù hợp.
- `depends_on` đơn giản không chờ service thành “ready”; nếu dùng `condition: service_healthy`, dependency phải khai báo healthcheck hoạt động thật.
- Các probe không nên làm rò rỉ credentials hoặc metadata nội bộ.
- Khi backend chuẩn bị dừng, nên ngừng nhận traffic, deregister/mark out-of-service phù hợp và cho request đang xử lý hoàn tất trong deadline.
- Không chỉ dựa vào `HealthCheckServiceInstanceListSupplier` để thực thi hard constraint: khi không còn instance khỏe, supplier dựng sẵn có thể **fallback về danh sách nguồn** tùy cấu hình/version.

### Ví dụ healthcheck Compose (cần điều kiện)

Một healthcheck `/actuator/health` dùng `curl` chỉ hoạt động nếu image có curl. Image Java runtime tối giản có thể **không có curl hoặc wget**. Do đó, không nên copy một healthcheck shell mà chưa xác minh image; hãy dùng công cụ probe đã cài hoặc một kiểm tra tương thích với image.

Nếu healthcheck phụ thuộc Actuator, thêm `spring-boot-starter-actuator` và kiểm tra endpoint được bật. **Không dùng Docker healthcheck như bằng chứng duy nhất rằng discovery đã loại instance.**

## 15. WebClient và OpenFeign trong hai mode

### WebClient

~~~java
@Bean
@LoadBalanced
WebClient.Builder lbWebClientBuilder() {
    return WebClient.builder();
}

@Bean
WebClient catalogWebClient(
        @LoadBalanced WebClient.Builder builder) {
    return builder.baseUrl("http://catalog-service").build();
}
~~~

Cần Spring WebFlux và starter LoadBalancer phù hợp. Với cả static/Eureka, **URL logic không đổi**; chỉ thay nguồn `ServiceInstance` theo profile.

Reactor Netty connection pool được tạo theo HTTP transport, thường có giới hạn theo remote host/pool. Đây **không phải** danh sách Spring Cloud LoadBalancer; nhiều replica có thể có nhiều pool vật lý khác nhau.

### OpenFeign

~~~java
@FeignClient(name = "catalog-service")
interface CatalogFeign {
    @GetMapping("/whoami")
    CatalogReply whoami();
}
~~~

Khi có `@EnableFeignClients`, starter OpenFeign và starter LoadBalancer tương thích, Feign theo service ID có thể chọn instance từ `DiscoveryClient`. Nhưng nếu đặt `@FeignClient(url=...)` hoặc URL cố định qua property, Feign đi trực tiếp tới URL đó, không dùng việc chọn instance theo name như ví dụ.

Với Feign cần kiểm tra `connectTimeout`, `readTimeout` và HTTP transport được cấu hình riêng. Không coi việc thêm Eureka là tự bật retry hoặc tự cấu hình connection pool.

## 16. Biến thể: gọi trực tiếp Compose DNS thay vì Spring Cloud LoadBalancer

Nếu ứng dụng chỉ cần gọi một **virtual endpoint** và Docker Compose DNS đáp ứng đủ yêu cầu, có thể không dùng `DiscoveryClient` hoặc `@LoadBalanced`.

Ví dụ với mode Eureka Compose đang có service `catalog-service`:

~~~java
RestClient directByComposeDns =
        RestClient.create("http://catalog-service:8081");
~~~

Client sẽ nhờ HTTP transport phân giải tên service qua DNS của Compose. Docker có thể phân giải tên một service có nhiều replicas thành các địa chỉ container, nhưng:

- JVM/DNS resolver có cache; thứ tự IP không phải một hợp đồng phân phối.
- Connection pool/keep-alive có thể tiếp tục dùng một kết nối cũ.
- Không có `ServiceInstanceListSupplier`/zone/hint/weight của Spring Cloud ở đường gọi này.
- Lỗi một replica và thời gian reconnect phụ thuộc HTTP client, Docker networking và retry policy.
- `127.0.0.1:8081` bên trong order container **không trỏ tới catalog**.

**Chọn rõ trách nhiệm:** hoặc client-side LB chọn instance từ discovery, hoặc DNS/gateway/mesh đảm nhiệm đích ảo. Không nên ngẫu nhiên trộn hai tầng mà không biết request đi qua đâu.

## 17. Ma trận lỗi thường gặp trong Docker Compose

| Triệu chứng | Nghi vấn chính | Kiểm tra |
|---|---|---|
| `UnknownHostException: catalog-service` khi gọi thường | DNS không có tên đó trên network hoặc client ở sai network | Xem service names, network và URL thực |
| `No instances available for catalog-service` | LoadBalancer không nhận danh sách từ discovery/supplier | Kiểm tra profile, static config/Eureka fetch |
| `catalog-a` không resolve | Sai service name, container ở network khác | `docker compose ps`, Compose service names |
| Caller gọi `localhost:8081` nhưng lỗi | Localhost là chính order container | Dùng `catalog-a:8081` hoặc URI từ Eureka |
| A chết vẫn thỉnh thoảng được chọn | Static list hoặc Eureka/LoadBalancer cache stale | Đối chiếu registry list, refresh và HTTP errors |
| Eureka dashboard có instance nhưng caller kết nối lỗi | Registry quảng bá host/IP/port không reachable | Kiểm tra prefer IP, port và network |
| Scale catalog service báo lỗi cổng host | Đã publish host port cố định trên service scale | Bỏ `ports: "8081:8081"` cho replicas |
| Scale thất bại vì `container_name` | Container name cố định không cho nhiều replica | Bỏ `container_name` |
| `depends_on` đã có nhưng caller lỗi lúc startup | Registry/backend chưa ready | Health/readiness, startup retry có deadline |
| Static mode cố kết nối Eureka | Còn Eureka client enabled trong static profile | `eureka.client.enabled=false` |
| Dynamic mode chỉ chọn một instance | Chỉ một đăng ký UP, instance ID trùng, cache/health/filter | So sánh Compose replicas, Eureka registry và caller |
| DNS gọi được nhưng metric LB không có | Client đi đường direct DNS | Kiểm tra `@LoadBalanced` builder/filter |
| Response thay đổi nhưng JVM vẫn dùng socket cũ | Connection pooling/keep-alive | Kiểm tra HTTP transport, idle eviction |
| WebClient/Feign có cách phân phối khác RestClient | Adapter/filter hoặc URL fixed khác nhau | Kiểm tra bean và config của từng client |

Không chẩn đoán mọi lỗi là do “Docker DNS”. Nếu LoadBalancer đã trả một `ServiceInstance` với IP/port nhưng backend trả 500, đó có thể là lỗi backend hoặc contract HTTP.

## 18. Cách quan sát danh sách instance một cách có kiểm soát

Trong môi trường lab, có thể bổ sung một endpoint **chỉ bật profile thử nghiệm** để xem caller đang biết những URI nào:

~~~java
import java.util.List;
import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.discovery.DiscoveryClient;
import org.springframework.context.annotation.Profile;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@Profile({"compose-static", "compose-eureka"})
class InstanceDiagnosticsController {

    private final DiscoveryClient discoveryClient;

    InstanceDiagnosticsController(DiscoveryClient discoveryClient) {
        this.discoveryClient = discoveryClient;
    }

    @GetMapping("/lab/instances")
    List<String> catalogInstances() {
        return discoveryClient
                .getInstances("catalog-service").stream()
                .map(ServiceInstance::getUri)
                .map(Object::toString)
                .toList();
    }
}
~~~

Khi chạy `compose-static`, kết quả kỳ vọng (thứ tự không bảo đảm):

~~~json
[
  "http://catalog-a:8081",
  "http://catalog-b:8081"
]
~~~

Khi chạy `compose-eureka`, kết quả có thể là hai URI chứa **container IPs** với port 8081. Kết quả sẽ thay đổi khi Eureka cập nhật registry/client cache.

**Bảo mật:** không mở endpoint `/lab/instances` trong production: nó có thể tiết lộ topology, URI nội bộ và metadata hệ thống. Khi điều tra production, dùng telemetry hoặc quyền truy cập quản trị được kiểm soát.

### Ba nơi cần đối chiếu

1. **Compose:** hiện có bao nhiêu container sống?
2. **Registry/SimpleDiscoveryClient:** caller đã biết những URI nào?
3. **HTTP execution:** response `instanceId` hoặc trace server cho biết request thực sự tới replica nào?

Nếu ba quan sát khác nhau, hãy xác định do registration delay, cache, proxy, route policy hay HTTP connection reuse trước khi đổi timeout.

## 19. Kiểm thử tích hợp giữa hai cấu hình

Các bài test có thể dùng cùng một tập assertion, chỉ thay cách cung cấp instance.

### Test cho static profile

- Application context tạo `@LoadBalanced RestClient.Builder` đúng.
- `SimpleDiscoveryClient` trả hai URI `catalog-a` và `catalog-b` (hoặc fake servers tương đương).
- Backend A/B trả ID riêng; sau nhiều lời gọi xuất hiện cả hai trong tập kết quả.
- Khi source chỉ còn B, không được chọn A.
- Khi một backend tắt nhưng source chưa đổi, test chứng minh lỗi có thể xảy ra và không khẳng định failover tự động.

### Test cho Eureka profile

- Hai catalog replicas đăng ký **hai instance IDs khác nhau**.
- Caller fetch registry thành công, thấy đủ URI có thể truy cập.
- Scale-down/up dẫn đến candidate list thay đổi **sau khoảng thời gian refresh**, không assert một số mili-giây cố định.
- Eureka outage được ghi nhận, nhưng không giả định client lập tức mất mọi khả năng gọi backend (client có thể còn cache).
- Không có fallback sang endpoint ngoài vùng/dịch vụ bị cấm nếu policy cứng.

### Tổ chức test pyramid

| Loại test | Công cụ gợi ý | Chứng minh |
|---|---|---|
| Unit | JUnit, fake `ServiceInstanceListSupplier` | Logic lựa chọn và fallback |
| Integration static | `@SpringBootTest`, fake HTTP servers, `@DynamicPropertySource` | Cấu hình LB và HTTP thực |
| Integration registry | Testcontainers/Eureka test stack | Đăng ký/deregister và lookup |
| Load/smoke | k6 hoặc tool tương đương qua order-service | Phân phối, latency, pool, retry under load |
| Failure test | Dừng/recreate một backend trong test | Stale discovery, timeout, retry và phục hồi |

Với test tải, **bắn request qua caller** `/probe/catalog`. Bắn trực tiếp vào từng backend chỉ đo server, không kiểm chứng client-side LoadBalancer. Ghi cả request count của từng instance, không chỉ thời gian tổng.

## 20. Hướng dẫn chuyển từ static sang Eureka có kiểm soát

Một kế hoạch chuyển đổi tốt nên tách **nguồn danh sách instance** khỏi **business code**:

1. Xác nhận `order-service` gọi bằng service ID qua `@LoadBalanced RestClient.Builder` ngay từ static mode.
2. Đưa Eureka starter vào các ứng dụng thích hợp và cấu hình Eureka server trên cùng network.
3. Đăng ký catalog replicas với app name `catalog-service`, unique instance ID và endpoint truy cập được.
4. Tạo profile `compose-eureka` **không chứa static list**, rồi bật Eureka fetch ở caller.
5. So sánh URI từ `DiscoveryClient` với Eureka dashboard và kiểm tra `/probe/catalog`.
6. Chạy thử scale-down/up, giám sát thời gian cập nhật, error rate, retry amplification và connection pool.
7. Kiểm thử failure và rollback profile trong môi trường test.
8. Khi dùng production, triển khai registry an toàn, monitor lease/health, kiểm soát quyền truy cập và resource limits.

Mã gọi:

~~~java
catalog.get()
       .uri("/whoami")
       .retrieve()
       .body(CatalogReply.class);
~~~

**Không cần đổi** khi chuyển từ static sang Eureka, bởi cùng service ID `catalog-service` được giải quyết bởi nguồn discovery khác nhau.

### Khi không cần chuyển

Nếu Docker Compose DNS/gateway đã được chọn làm điểm đích ảo, số replica nhỏ và không có yêu cầu chọn instance từ caller, giữ direct DNS client có thể đơn giản hơn. **Đừng triển khai hai tầng discovery chỉ vì muốn trông giống kiến trúc microservices lớn.**

## 21. Bảo mật, networking và vận hành thực tế

Trong Compose lab, các thành phần thường nằm trên một network mặc định. Khi triển khai nghiêm túc cần chú ý:

- **Network scope:** không đặt database/registry ra public network nếu không cần.
- **Registry authentication/TLS:** Eureka/Consul dashboard và API registration chứa topology, phải kiểm soát truy cập.
- **Service credentials:** dùng secret management thay vì hardcode mật khẩu/token trong Compose YAML hay log.
- **Container identity:** đừng giả định IP bền vững; sử dụng tên service/registry và tính toán khi recreate.
- **Image security:** pin image version, scan dependencies, chạy non-root khi khả thi.
- **Health/readiness:** tách “process running” khỏi “HTTP dependency ready”; cấu hình graceful shutdown.
- **Observability:** ghi service ID, selected instance, error category và latency; tránh log `Authorization`, cookie, raw URL hoặc response body nhạy cảm.
- **Retry/timeouts:** giới hạn attempts, backoff và tổng deadline; điều chỉnh theo capacity và đặc tính idempotency.
- **Cache:** xem xét cache của registry client và LoadBalancer; double caching có thể tăng độ stale.
- **Host vs container port:** nội bộ Compose gọi **container port**, không dùng host-published port làm URI mặc định.

Eureka một node ở mode B có thể trở thành điểm tập trung rủi ro trong bài lab. Production cần thiết kế availability, backup/khôi phục và cân nhắc nền tảng điều phối/dịch vụ registry phù hợp thay vì chỉ scale một Compose file.

## 22. Checklist nghiệm thu

Trước khi kết thúc bài thực hành, hãy kiểm tra:

1. Có phân biệt Compose DNS, Spring `DiscoveryClient` và Spring Cloud LoadBalancer không?
2. Client có thực sự được tạo từ `@LoadBalanced RestClient.Builder`, không phải RestClient thường dùng DNS?
3. Static mode có hai Compose services `catalog-a` và `catalog-b`, cùng container port 8081?
4. `SimpleDiscoveryClient` trả URI với **tên service** thay vì IP container cố định?
5. Static profile có tắt Eureka client nếu jar chứa Eureka starter?
6. Dừng A có để lại URI A trong static list như dự đoán?
7. Sửa static list có đi kèm reload/redeploy phù hợp?
8. Eureka mode có hai catalog replicas đăng ký với **instance ID khác nhau**?
9. Eureka advertise địa chỉ/port caller thực sự kết nối được trong Compose network?
10. `catalog-service` có thể scale bằng `--scale catalog-service=2` mà không có `container_name` hoặc host port conflict?
11. Khi scale-down, đã quan sát độ trễ registry/client refresh và lỗi do stale instances?
12. `depends_on` có được hiểu đúng là không thay thế readiness?
13. Phân phối instance được xác minh từ response/metrics chứ không suy ra từ hostname?
14. Retry, timeout, health, connection pool và idempotency đã được phân biệt với discovery?
15. Các endpoint debug/registry dashboard có bị giới hạn khỏi môi trường production?

**Kết luận:** Trong Docker Compose, bạn có thể dùng **`SimpleDiscoveryClient` với danh sách `catalog-a`/`catalog-b` tĩnh** để triển khai nhanh và kiểm chứng lựa chọn `ServiceInstance`; hoặc thêm **Eureka** để các replicas tự đăng ký và caller cập nhật danh sách theo cơ chế registry. **Docker Compose DNS không tự biến thành Spring Cloud `DiscoveryClient`**, còn Spring Cloud LoadBalancer **không tự thay thế HTTP transport, timeout, retry hoặc health/readiness**. Chọn phương án phù hợp với tần suất thay đổi replica, mức độ sẵn sàng, chi phí vận hành và cách bạn muốn kiểm soát đường đi request.

**Tài liệu tham khảo chính thức:**

- [Docker Docs – Networking in Compose](https://docs.docker.com/compose/how-tos/networking/)
- [Docker Docs – Compose services, container_name và scaling](https://docs.docker.com/reference/compose-file/services/)
- [Spring Cloud Commons – Spring Cloud LoadBalancer](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html)
- [Spring Cloud Commons – RestClient as a LoadBalancer Client](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html)
- [Spring Cloud Netflix – Eureka Client and Server](https://docs.spring.io/spring-cloud-netflix/docs/current/reference/html/)

