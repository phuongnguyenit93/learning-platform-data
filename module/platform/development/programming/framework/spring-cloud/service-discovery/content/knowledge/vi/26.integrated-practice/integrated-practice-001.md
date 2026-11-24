# Dựng Eureka và hai dịch vụ để quan sát đầy đủ chu trình khám phá

## Mục tiêu thực hành

Trong bài này, bạn sẽ dựng một Eureka Server và hai microservice Spring Boot:

- **catalog-service:** dịch vụ cung cấp dữ liệu catalog; chạy hai instance trên hai cổng khác nhau.
- **order-service:** dịch vụ tiêu thụ catalog; tự đăng ký với Eureka, truy vấn instance bằng DiscoveryClient và gọi catalog qua Spring Cloud LoadBalancer.
- **eureka-server:** lưu registry, nhận registration/heartbeat và cung cấp danh sách instance cho client.

Sau khi hoàn thành, bạn có thể quan sát toàn bộ luồng:

1. Eureka Server khởi động ở cổng 8761.
2. Hai instance catalog đăng ký cùng service ID nhưng có instance ID khác nhau.
3. order-service đăng ký với Eureka và lấy danh sách catalog instance.
4. DiscoveryClient trả danh sách ServiceInstance.
5. Spring Cloud LoadBalancer chọn một instance khi order-service gọi bằng service name.
6. Khi một catalog instance dừng, registration được hủy hoặc hết hạn và consumer cập nhật danh sách.

Bài thực hành dùng Maven multi-module để ba ứng dụng chia sẻ một bộ quản lý phiên bản. Có thể tách thành ba repository độc lập sau khi đã hiểu cách hoạt động.

## 1. Kiến trúc và luồng khám phá

~~~~mermaid
flowchart LR
    subgraph Registry
      E[Eureka Server :8761]
    end

    subgraph Providers
      C1[catalog-service :8081]
      C2[catalog-service :8082]
    end

    subgraph Consumer
      O[order-service :8090]
      D[DiscoveryClient]
      L[Spring Cloud LoadBalancer]
    end

    C1 -- register / heartbeat --> E
    C2 -- register / heartbeat --> E
    O -- register / heartbeat --> E
    O --> D
    D -- read registry cache --> E
    O --> L
    L -- choose one instance --> C1
    L -- choose one instance --> C2
~~~~

Hai instance catalog có cùng spring.application.name=catalog-service, do đó chúng thuộc cùng một service ID. Mỗi instance phải có địa chỉ, cổng và instance ID riêng. Eureka không chạy request nghiệp vụ thay cho provider; nó cung cấp thông tin để consumer tìm địa chỉ phù hợp.

Có hai thao tác khác nhau ở phía order-service:

- **Khám phá trực tiếp:** gọi DiscoveryClient.getInstances("catalog-service") để xem danh sách instance.
- **Gọi qua tên dịch vụ:** gửi HTTP request tới http://catalog-service/...; Spring Cloud LoadBalancer chọn một instance rồi chuyển request đến địa chỉ thật.

DiscoveryClient trả thông tin discovery. LoadBalancer chọn instance cho request. Hai vai trò này có liên quan nhưng không phải một API duy nhất.

## 2. Chọn phiên bản tương thích

Bài thực hành dùng bộ phiên bản GA hiện hành tại thời điểm biên soạn:

| Thành phần | Phiên bản |
| --- | --- |
| Java | 21 |
| Spring Boot | 4.2.0 |
| Spring Cloud Release Train | 2026.0.0 |
| Spring Cloud Netflix | 5.1.0 |
| Build | Maven |

Spring Cloud 2026.0.0 được phát hành dựa trên Spring Boot 4.2.0. Release train này quản lý Spring Cloud Netflix 5.1.0 và Spring Cloud Commons 5.1.0. Hãy dùng BOM để quản lý dependency, không tự đặt version riêng cho từng starter. Nếu dự án của bạn đang dùng Spring Boot 3.5.x, hãy chọn release train tương thích tương ứng thay vì trộn Boot 3.x với Cloud 2026.0.0.

Boot 4 đã tách một số starter. Ví dụ này dùng spring-boot-starter-webmvc cho REST API và spring-boot-starter-restclient cho HTTP client đồng bộ. Eureka client trong Spring Cloud Netflix 5.1.0 dùng RestClient làm HTTP client mặc định khi có dependency phù hợp.

Tài liệu phiên bản:

- [Spring Cloud 2026.0.0 release announcement](https://spring.io/blog/2026/11/20/spring-cloud-2026-0-0-has-been-released/)
- [Spring Cloud release train compatibility](https://docs.spring.io/spring-cloud-release/reference/index.html)
- [Spring Cloud Netflix reference](https://docs.spring.io/spring-cloud-netflix/reference/spring-cloud-netflix.html)

## 3. Tạo cấu trúc Maven multi-module

Tạo thư mục dự án có cấu trúc:

~~~~text
eureka-discovery-lab/
├── pom.xml
├── eureka-server/
│   ├── pom.xml
│   └── src/main/
│       ├── java/com/example/eurekaserver/
│       │   └── EurekaServerApplication.java
│       └── resources/
│           └── application.yml
├── catalog-service/
│   ├── pom.xml
│   └── src/main/
│       ├── java/com/example/catalog/
│       │   ├── CatalogServiceApplication.java
│       │   ├── CatalogController.java
│       │   └── CatalogResponse.java
│       └── resources/
│           └── application.yml
└── order-service/
    ├── pom.xml
    └── src/main/
        ├── java/com/example/order/
        │   ├── OrderServiceApplication.java
        │   ├── LoadBalancedClientConfiguration.java
        │   ├── OrderController.java
        │   ├── CatalogResponse.java
        │   └── DiscoveredInstance.java
        └── resources/
            └── application.yml
~~~~

### 3.1. POM ở thư mục gốc

File pom.xml quản lý phiên bản Spring Boot, import Spring Cloud BOM và khai báo ba module:

~~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.2.0</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>eureka-discovery-lab</artifactId>
    <version>1.0.0</version>
    <packaging>pom</packaging>

    <modules>
        <module>eureka-server</module>
        <module>catalog-service</module>
        <module>order-service</module>
    </modules>

    <properties>
        <java.version>21</java.version>
        <spring-cloud.version>2026.0.0</spring-cloud.version>
    </properties>

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
</project>
~~~~

### 3.2. POM của Eureka Server

File eureka-server/pom.xml:

~~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>com.example</groupId>
        <artifactId>eureka-discovery-lab</artifactId>
        <version>1.0.0</version>
        <relativePath>../pom.xml</relativePath>
    </parent>

    <artifactId>eureka-server</artifactId>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webmvc</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-restclient</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-actuator</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-starter-netflix-eureka-server</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~~

### 3.3. POM của catalog-service

File catalog-service/pom.xml:

~~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>com.example</groupId>
        <artifactId>eureka-discovery-lab</artifactId>
        <version>1.0.0</version>
        <relativePath>../pom.xml</relativePath>
    </parent>

    <artifactId>catalog-service</artifactId>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webmvc</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-restclient</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-actuator</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-starter-netflix-eureka-client</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~~

### 3.4. POM của order-service

File order-service/pom.xml:

~~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>com.example</groupId>
        <artifactId>eureka-discovery-lab</artifactId>
        <version>1.0.0</version>
        <relativePath>../pom.xml</relativePath>
    </parent>

    <artifactId>order-service</artifactId>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webmvc</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-restclient</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-actuator</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-starter-netflix-eureka-client</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-starter-loadbalancer</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~~

## 4. Xây dựng Eureka Server

Eureka Server là ứng dụng Spring Boot có thêm starter spring-cloud-starter-netflix-eureka-server và annotation @EnableEurekaServer.

File EurekaServerApplication.java:

~~~~java
package com.example.eurekaserver;

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
~~~~

File eureka-server/src/main/resources/application.yml:

~~~~yaml
server:
  port: 8761

spring:
  application:
    name: eureka-server

eureka:
  client:
    register-with-eureka: false
    fetch-registry: false

management:
  endpoints:
    web:
      exposure:
        include: health,info
~~~~

Hai thuộc tính register-with-eureka và fetch-registry được đặt thành false vì đây là Eureka Server độc lập cho bài thực hành. Eureka Server cũng có khả năng hoạt động như một Eureka Client để đăng ký với peer và lấy registry. Trong chế độ standalone, tắt hai hành vi đó giúp log không liên tục báo lỗi tìm peer.

Khởi động server xong, mở:

- Dashboard: http://localhost:8761/
- Health: http://localhost:8761/actuator/health
- Registry REST API: http://localhost:8761/eureka/apps

Dashboard ban đầu chưa có application instance nào. Đây là trạng thái bình thường vì hai service client chưa khởi động.

## 5. Xây dựng catalog-service

### 5.1. Main class

File CatalogServiceApplication.java:

~~~~java
package com.example.catalog;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CatalogServiceApplication {

    public static void main(String[] args) {
        SpringApplication.run(CatalogServiceApplication.class, args);
    }
}
~~~~

Không cần thêm @EnableEurekaClient hoặc @EnableDiscoveryClient cho cấu hình thông thường hiện nay. Khi Eureka Client starter có mặt trên classpath và discovery được bật, Spring Cloud tự cấu hình client và đăng ký ứng dụng.

### 5.2. Response để nhận biết từng instance

File CatalogResponse.java:

~~~~java
package com.example.catalog;

public record CatalogResponse(
        String service,
        String instance,
        int port,
        String message
) {
}
~~~~

File CatalogController.java:

~~~~java
package com.example.catalog;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class CatalogController {

    private final int port;

    public CatalogController(@Value("${server.port}") int port) {
        this.port = port;
    }

    @GetMapping("/catalog")
    public CatalogResponse getCatalog() {
        return new CatalogResponse(
                "catalog-service",
                "catalog-service:" + port,
                port,
                "Catalog response from this service instance"
        );
    }
}
~~~~

Response chứa cổng và instance ID để bạn nhìn thấy LoadBalancer đang gọi replica nào. Trong ứng dụng thật, controller sẽ trả dữ liệu catalog từ domain/service layer; trường instance ở đây chỉ phục vụ quan sát.

### 5.3. Cấu hình đăng ký Eureka

File catalog-service/src/main/resources/application.yml:

~~~~yaml
server:
  port: ${SERVER_PORT:8081}

spring:
  application:
    name: catalog-service

eureka:
  client:
    service-url:
      defaultZone: ${EUREKA_URL:http://localhost:8761/eureka/}
  instance:
    instance-id: ${spring.application.name}:${server.port}

management:
  endpoints:
    web:
      exposure:
        include: health,info
~~~~

Ý nghĩa:

- spring.application.name là service ID mà consumer dùng để tìm catalog.
- defaultZone là URL của Eureka Server. Tên khóa defaultZone dùng camel case vì nó là key trong map serviceUrl; không tự đổi thành default-zone.
- instance-id phải khác nhau giữa các process. Ở đây cổng được đưa vào ID để hai replica trên cùng máy không ghi đè nhau.
- SERVER_PORT và EUREKA_URL cho phép ghi đè cấu hình bằng environment variable khi chạy ở môi trường khác.

Eureka Client tự đăng ký instance và gửi heartbeat định kỳ. Registry lưu host, port, service ID, instance ID và metadata để consumer sử dụng.

## 6. Xây dựng order-service

order-service vừa là một Eureka client (đăng ký chính nó), vừa là consumer (truy vấn catalog-service).

### 6.1. Main class

File OrderServiceApplication.java:

~~~~java
package com.example.order;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OrderServiceApplication {

    public static void main(String[] args) {
        SpringApplication.run(OrderServiceApplication.class, args);
    }
}
~~~~

### 6.2. DTO nhận response của catalog-service

File CatalogResponse.java trong order-service:

~~~~java
package com.example.order;

public record CatalogResponse(
        String service,
        String instance,
        int port,
        String message
) {
}
~~~~

Đây là DTO tương ứng với JSON mà catalog-service trả về. Hai service độc lập có thể chia sẻ contract qua một thư viện API riêng trong dự án lớn; bài thực hành giữ DTO trong từng module để giảm số thành phần phải tạo.

### 6.3. Tạo RestClient có LoadBalancer

File LoadBalancedClientConfiguration.java:

~~~~java
package com.example.order;

import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;

@Configuration
public class LoadBalancedClientConfiguration {

    @Bean
    @LoadBalanced
    RestClient.Builder loadBalancedRestClientBuilder() {
        return RestClient.builder();
    }
}
~~~~

@LoadBalanced đánh dấu builder để Spring Cloud gắn cơ chế client-side load balancing. Khi dùng builder này, URL có thể chứa service ID logic thay vì hostname thật.

Ví dụ:

~~~~text
http://catalog-service/catalog
~~~~

LoadBalancer lấy danh sách instance từ DiscoveryClient, chọn một ServiceInstance, rồi chuyển URL logic thành host và port của instance đã chọn.

### 6.4. Truy vấn trực tiếp bằng DiscoveryClient và gọi bằng LoadBalancer

File DiscoveredInstance.java:

~~~~java
package com.example.order;

import java.util.Map;

public record DiscoveredInstance(
        String serviceId,
        String instanceId,
        String host,
        int port,
        String uri,
        Map<String, String> metadata
) {
}
~~~~

File OrderController.java:

~~~~java
package com.example.order;

import java.util.List;
import java.util.stream.IntStream;

import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.discovery.DiscoveryClient;
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.client.RestClient;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/orders")
public class OrderController {

    private final DiscoveryClient discoveryClient;
    private final RestClient catalogClient;

    public OrderController(
            DiscoveryClient discoveryClient,
            @LoadBalanced RestClient.Builder builder) {
        this.discoveryClient = discoveryClient;
        this.catalogClient = builder.build();
    }

    @GetMapping("/discovery/catalog")
    public List<DiscoveredInstance> discoverCatalogInstances() {
        List<ServiceInstance> instances =
                discoveryClient.getInstances("catalog-service");

        return instances.stream()
                .map(instance -> new DiscoveredInstance(
                        instance.getServiceId(),
                        instance.getInstanceId(),
                        instance.getHost(),
                        instance.getPort(),
                        instance.getUri().toString(),
                        instance.getMetadata()
                ))
                .toList();
    }

    @GetMapping("/catalog")
    public CatalogResponse callCatalog() {
        return catalogClient.get()
                .uri("http://catalog-service/catalog")
                .retrieve()
                .body(CatalogResponse.class);
    }

    @GetMapping("/catalog/sequence")
    public List<CatalogResponse> callCatalogSeveralTimes(
            @RequestParam(defaultValue = "8") int count) {

        if (count < 1 || count > 50) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST,
                    "count must be between 1 and 50"
            );
        }

        return IntStream.range(0, count)
                .mapToObj(index -> callCatalog())
                .toList();
    }
}
~~~~

Ba endpoint thể hiện hai cách sử dụng:

- /orders/discovery/catalog gọi DiscoveryClient trực tiếp và trả về danh sách instance.
- /orders/catalog gọi bằng service ID qua LoadBalancer.
- /orders/catalog/sequence?count=8 gửi nhiều request tuần tự để quan sát instance được chọn.

Spring Cloud LoadBalancer mặc định dùng RoundRobinLoadBalancer. Vì vậy, với hai instance khỏe mạnh và danh sách đã cập nhật, các request tuần tự thường luân phiên giữa hai cổng. Đây là thuật toán chọn instance ở phía client; nó không có nghĩa Eureka Server chuyển tiếp request.

### 6.5. Cấu hình order-service

File order-service/src/main/resources/application.yml:

~~~~yaml
server:
  port: 8090

spring:
  application:
    name: order-service
  cloud:
    loadbalancer:
      cache:
        enabled: false

eureka:
  client:
    service-url:
      defaultZone: ${EUREKA_URL:http://localhost:8761/eureka/}
  instance:
    instance-id: ${spring.application.name}:${server.port}

management:
  endpoints:
    web:
      exposure:
        include: health,info
~~~~

Trong bài lab, tắt cache riêng của Spring Cloud LoadBalancer để dễ quan sát danh sách lấy từ Eureka client. Eureka client vốn đã có registry cache. Trong hệ thống khác, cache LoadBalancer có thể hữu ích; hãy cân nhắc tránh chồng nhiều lớp cache và kiểm tra thời gian hội tụ khi cập nhật instance.

## 7. Build ba ứng dụng

Mở terminal tại thư mục gốc eureka-discovery-lab.

Kiểm tra Java và Maven:

~~~~powershell
java -version
mvn -version
~~~~

Build toàn bộ reactor:

~~~~powershell
mvn clean package
~~~~

Nếu build thành công, ba executable JAR được tạo:

~~~~text
eureka-server/target/eureka-server-1.0.0.jar
catalog-service/target/catalog-service-1.0.0.jar
order-service/target/order-service-1.0.0.jar
~~~~

Nếu dự án dùng Maven Wrapper, trên Windows có thể chạy .\mvnw.cmd clean package; trên macOS/Linux dùng ./mvnw clean package.

Không đặt version riêng cho Eureka starter hoặc LoadBalancer starter trong các POM con. Spring Cloud BOM đã quản lý chúng.

## 8. Khởi động theo đúng thứ tự

Mở bốn terminal riêng. Giữ các process chạy trong suốt quá trình quan sát.

### Terminal 1: Eureka Server

~~~~powershell
java -jar .\eureka-server\target\eureka-server-1.0.0.jar
~~~~

Chờ log Spring Boot báo ứng dụng đã started, sau đó mở http://localhost:8761/.

### Terminal 2: catalog-service instance thứ nhất

~~~~powershell
java -jar .\catalog-service\target\catalog-service-1.0.0.jar --server.port=8081
~~~~

### Terminal 3: catalog-service instance thứ hai

~~~~powershell
java -jar .\catalog-service\target\catalog-service-1.0.0.jar --server.port=8082
~~~~

Hai process dùng cùng JAR và cùng service ID. Tham số --server.port ghi đè cổng mặc định, còn instance-id tự thay đổi theo cổng.

### Terminal 4: order-service

~~~~powershell
java -jar .\order-service\target\order-service-1.0.0.jar --server.port=8090
~~~~

Khi order-service khởi động xong, nó cũng đăng ký với Eureka. Dashboard sẽ hiển thị các application client.

## 9. Quan sát registration trong Eureka

Mở dashboard:

http://localhost:8761/

Bạn sẽ thấy các application như:

- CATALOG-SERVICE: có hai instance tương ứng cổng 8081 và 8082.
- ORDER-SERVICE: có một instance ở cổng 8090.

Eureka thường hiển thị service ID ở dạng uppercase. Đây là cách trình bày của Eureka UI; tên cấu hình trong Spring Boot vẫn là catalog-service.

Có thể truy vấn registry bằng REST API:

~~~~powershell
Invoke-RestMethod -Uri "http://localhost:8761/eureka/apps" -Headers @{ Accept = "application/json" } | ConvertTo-Json -Depth 10
~~~~

Chỉ xem application catalog:

~~~~powershell
Invoke-RestMethod -Uri "http://localhost:8761/eureka/apps/CATALOG-SERVICE" -Headers @{ Accept = "application/json" } | ConvertTo-Json -Depth 10
~~~~

Hoặc dùng curl:

~~~~bash
curl -H "Accept: application/json" \
  http://localhost:8761/eureka/apps/CATALOG-SERVICE
~~~~

Đối chiếu instanceId, hostName, ipAddr, port, status và metadata. Nếu chỉ thấy một instance, kiểm tra log của process thứ hai và xác minh hai instance không dùng chung instance ID.

Registration không nhất thiết xuất hiện đồng thời ở mọi cache. Eureka có heartbeat, server response cache và client registry cache. Sau lần khởi động đầu tiên, hãy chờ các chu kỳ đồng bộ trước khi kết luận client không đăng ký được.

## 10. Quan sát DiscoveryClient trả về instance

Gọi endpoint do order-service cung cấp:

~~~~powershell
Invoke-RestMethod "http://localhost:8090/orders/discovery/catalog" | ConvertTo-Json -Depth 6
~~~~

Kết quả kỳ vọng là một mảng có hai phần tử. Ví dụ rút gọn:

~~~~json
[
  {
    "serviceId": "CATALOG-SERVICE",
    "instanceId": "catalog-service:8081",
    "host": "127.0.0.1",
    "port": 8081,
    "uri": "http://127.0.0.1:8081",
    "metadata": {}
  },
  {
    "serviceId": "CATALOG-SERVICE",
    "instanceId": "catalog-service:8082",
    "host": "127.0.0.1",
    "port": 8082,
    "uri": "http://127.0.0.1:8082",
    "metadata": {}
  }
]
~~~~

Host có thể khác 127.0.0.1 tùy network interface mà Eureka Client quảng bá. Hai trường cần quan sát là instanceId và port.

Bạn cũng có thể gọi trực tiếp từng provider để so sánh:

~~~~powershell
Invoke-RestMethod "http://localhost:8081/catalog"
Invoke-RestMethod "http://localhost:8082/catalog"
~~~~

Nếu hai URL trực tiếp trả về hai instance khác nhau nhưng DiscoveryClient chỉ trả một instance, hãy kiểm tra registration ID và registry fetch ở order-service.

## 11. Quan sát Spring Cloud LoadBalancer chọn instance

Gọi một request qua order-service:

~~~~powershell
Invoke-RestMethod "http://localhost:8090/orders/catalog"
~~~~

URL được dùng trong code là http://catalog-service/catalog. Không có hostname DNS tên catalog-service trên máy; service ID được Spring Cloud LoadBalancer phân giải thành một instance thật.

Gửi nhiều request tuần tự:

~~~~powershell
1..10 | ForEach-Object {
    (Invoke-RestMethod "http://localhost:8090/orders/catalog").instance
}
~~~~

Kết quả thường cho thấy hai instance ID catalog-service:8081 và catalog-service:8082 được chọn luân phiên. Thuật toán mặc định là round-robin. Nếu một instance bị loại khỏi danh sách, các request tiếp theo sẽ chọn từ các instance còn lại.

Điều cần quan sát:

1. DiscoveryClient cung cấp danh sách instance.
2. ServiceInstanceListSupplier cung cấp danh sách cho LoadBalancer.
3. RoundRobinLoadBalancer chọn một instance.
4. BlockingLoadBalancerClient chuyển URL logic thành URL vật lý.
5. RestClient gửi request đến host/port đã chọn.

Nếu gọi thẳng http://localhost:8081/catalog, bạn đã bỏ qua discovery và load balancing. Đó là request trực tiếp, không phải request qua service ID.

## 12. Quan sát vòng đời khi một instance dừng

### 12.1. Dừng graceful

Chọn terminal đang chạy catalog-service ở cổng 8081 và nhấn Ctrl+C. Spring Boot bắt đầu shutdown lifecycle; Eureka Client có cơ hội gửi cancel/deregister tới server.

Sau đó:

1. Mở Eureka dashboard và xem trạng thái application.
2. Truy vấn lại /eureka/apps/CATALOG-SERVICE.
3. Gọi /orders/discovery/catalog để xem danh sách consumer.
4. Gọi /orders/catalog/sequence?count=10 để xác nhận request còn đi tới cổng 8082.

Dữ liệu có thể cần thời gian để đi qua registry response cache và client fetch cache. Không kết luận thất bại chỉ vì endpoint consumer còn thấy instance trong một vài giây đầu.

### 12.2. Khởi động lại instance

Chạy lại JAR catalog trên cổng 8081. Quan sát registration xuất hiện trở lại và consumer có thể gọi tới cả hai instance sau khi registry/cache được cập nhật.

### 12.3. Dừng đột ngột để so sánh

Trong môi trường lab riêng, có thể kết thúc cưỡng bức process catalog-service để quan sát khác biệt với graceful shutdown. Khi process không gửi cancel, Eureka dựa vào heartbeat lease và eviction để dọn registration.

Cấu hình mặc định phổ biến là heartbeat khoảng 30 giây và lease expiration khoảng 90 giây; giá trị thực tế phụ thuộc cấu hình/version. Self-preservation có thể trì hoãn eviction khi server cho rằng heartbeat bị mất trên diện rộng. Vì vậy, process crash không đồng nghĩa instance biến mất tức thì.

Không tắt self-preservation chỉ để làm demo nhanh. Trong production, cơ chế này bảo vệ registry khi network partition khiến nhiều instance khỏe mạnh tạm thời không gửi heartbeat.

## 13. Quan sát health status trong Eureka

Mặc định, Eureka chủ yếu dùng heartbeat để xác định client còn sống. Nếu muốn truyền trạng thái health của Spring Boot Actuator sang Eureka, thêm cấu hình vào application.yml của provider:

~~~~yaml
eureka:
  client:
    healthcheck:
      enabled: true
~~~~

Giữ dependency spring-boot-starter-actuator và endpoint health hoạt động. Khi ứng dụng có health status khác UP, Eureka có thể nhận trạng thái tương ứng và consumer có thể lọc instance không UP.

Chỉ dùng cấu hình này sau khi đã hiểu health indicator tổng hợp của ứng dụng. Một dependency phụ trợ bị lỗi có thể làm health status tổng thể đổi trạng thái và khiến instance bị loại khỏi traffic. Không đặt thuộc tính này trong bootstrap.yml; tài liệu Spring Cloud Netflix yêu cầu đặt trong application.yml.

## 14. Kiểm tra lỗi thường gặp

| Triệu chứng | Nguyên nhân thường gặp | Cách kiểm tra |
| --- | --- | --- |
| Dashboard Eureka không mở | Server chưa khởi động hoặc cổng 8761 bị chiếm. | Xem log server, kiểm tra process và port. |
| Client không xuất hiện trong Eureka | Sai URL, sai service ID hoặc lỗi kết nối. | Kiểm tra defaultZone, log Eureka client và gọi URL server từ process client. |
| Client liên tục báo không kết nối được Eureka | defaultZone sai, server chưa chạy hoặc network không tới được. | Xác minh http://localhost:8761/eureka/ và dấu /eureka/. |
| Hai catalog process nhưng UI chỉ có một instance | Trùng instance ID hoặc một process chưa đăng ký. | Đưa port vào eureka.instance.instance-id; xem log từng process. |
| DiscoveryClient trả danh sách rỗng | spring.application.name không đúng, client chưa fetch registry hoặc registry chưa đồng bộ. | So sánh service ID trong UI và gọi /orders/discovery/catalog sau khi chờ fetch. |
| UnknownHostException: catalog-service | Request dùng RestClient thường, không có @LoadBalanced hoặc thiếu starter LoadBalancer. | Kiểm tra bean RestClient.Builder, qualifier và dependency. |
| Consumer gọi sai host/port | Provider quảng bá địa chỉ mà consumer không truy cập được. | Kiểm tra host, port, prefer-ip-address và network topology. |
| Instance cũ còn trong registry sau khi kill process | Lease chưa hết hạn, self-preservation hoặc cache chưa cập nhật. | Kiểm tra heartbeat, eviction, client fetch và server cache. |
| Gọi trực tiếp provider thành công nhưng gọi bằng service ID thất bại | Registry chưa có instance hoặc LoadBalancer không được cấu hình. | Kiểm tra DiscoveryClient trước, sau đó kiểm tra LoadBalancer. |

### Lưu ý về defaultZone

Trong YAML, dùng:

~~~~yaml
eureka:
  client:
    service-url:
      defaultZone: http://localhost:8761/eureka/
~~~~

defaultZone là key trong map URL và có phân biệt chữ hoa/chữ thường. Nếu đổi thành default-zone, client có thể không lấy được URL theo cấu hình mong muốn.

### Lưu ý khi chạy bằng Docker

Trong container, localhost trỏ về chính container hiện tại. Nếu Eureka Server và client chạy ở các container khác nhau, không dùng localhost:8761 cho client. Hãy dùng DNS/service name trong cùng Docker network, ví dụ http://eureka-server:8761/eureka/.

Đồng thời, địa chỉ provider đăng ký vào Eureka phải truy cập được từ container consumer. Port publish ra host không tự động làm địa chỉ container có thể truy cập theo cách consumer mong đợi. Kiểm tra eureka.instance.prefer-ip-address, hostname, network và port mapping trước khi kết luận LoadBalancer lỗi.

## 15. Bài tập mở rộng

### Bài tập 1: thêm instance thứ ba

Khởi động catalog-service ở cổng 8083. Không thay đổi order-service. Xác minh:

- Eureka hiển thị ba instance.
- DiscoveryClient trả ba phần tử.
- /orders/catalog/sequence?count=12 trả về cả ba cổng.

Mục tiêu là quan sát provider có thể scale thêm mà consumer không phải cập nhật danh sách URL.

### Bài tập 2: thay đổi metadata

Thêm metadata vào catalog-service:

~~~~yaml
eureka:
  instance:
    metadata-map:
      zone: lab-a
      version: v1
~~~~

Quan sát metadata qua /orders/discovery/catalog. Thử chạy một replica khác với zone: lab-b và so sánh kết quả. Metadata chỉ mang ý nghĩa định tuyến khi consumer hoặc LoadBalancer được cấu hình hiểu các key đó.

### Bài tập 3: kiểm tra trạng thái health

Bật Eureka health check integration và tạo một điều kiện khiến Actuator health chuyển trạng thái. Quan sát status trong Eureka và danh sách instance mà consumer nhận được. Khôi phục điều kiện rồi xác minh instance quay lại trạng thái phục vụ.

### Bài tập 4: kiểm tra độ trễ hội tụ

Ghi timestamp ở các thời điểm:

- Provider dừng.
- Eureka nhận deregistration hoặc lease hết hạn.
- Eureka REST API không còn trả instance.
- Consumer DiscoveryClient không còn trả instance.
- Request LoadBalancer cuối cùng tới instance đã dừng.

Từ đó phân biệt thời gian cleanup ở registry và thời gian cập nhật cache phía consumer.

## 16. Checklist hoàn thành

- [ ] Đã tạo Maven multi-module với ba ứng dụng.
- [ ] Đã import Spring Cloud BOM tương thích Spring Boot.
- [ ] Eureka Server chạy ở cổng 8761 và tắt client registration/fetch ở chế độ standalone.
- [ ] Hai catalog instance có cùng service ID nhưng instance ID khác nhau.
- [ ] order-service đăng ký được với Eureka.
- [ ] DiscoveryClient.getInstances("catalog-service") trả về hai instance.
- [ ] RestClient dùng @LoadBalanced builder và gọi bằng service ID.
- [ ] Đã quan sát LoadBalancer chọn instance qua các request tuần tự.
- [ ] Đã dừng graceful một provider và xác minh registry/consumer cập nhật.
- [ ] Đã phân biệt graceful deregistration với crash/lease expiration.
- [ ] Đã thử truy vấn Eureka REST API và Actuator health.
- [ ] Đã kiểm tra cấu hình hostname/port khi chạy trên nhiều máy hoặc Docker.

## Ghi nhớ

- Eureka Server lưu registry; Eureka Client đăng ký chính nó và có thể truy vấn registry.
- spring.application.name tạo service ID; eureka.instance.instance-id phân biệt từng replica.
- defaultZone chỉ tới Eureka Server và cần giữ đúng camel case.
- DiscoveryClient trả danh sách instance; Spring Cloud LoadBalancer chọn một instance cho request.
- @LoadBalanced RestClient.Builder cho phép gọi bằng URL logic như http://catalog-service/catalog.
- Spring Cloud LoadBalancer mặc định dùng round-robin.
- Eureka có heartbeat, lease, cache và self-preservation; thay đổi registration không nhất thiết xuất hiện tức thì ở mọi consumer.
- Graceful shutdown cho phép client deregister; crash phải dựa vào lease/eviction.
- Địa chỉ mà provider quảng bá phải truy cập được từ consumer; đặc biệt chú ý localhost khi chạy Docker.
- Trong production cần nhiều Eureka peer, bảo mật registry, giám sát heartbeat/renewal và đặt timeout phù hợp.

## Tài liệu tham khảo chính thức

- [Spring Cloud 2026.0.0 Release](https://spring.io/blog/2026/11/20/spring-cloud-2026-0-0-has-been-released/)
- [Spring Cloud Release Train Reference](https://docs.spring.io/spring-cloud-release/reference/index.html)
- [Spring Cloud Netflix – Eureka Client and Server](https://docs.spring.io/spring-cloud-netflix/reference/spring-cloud-netflix.html)
- [Spring Cloud Commons – DiscoveryClient and ServiceRegistry](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html)
- [Spring Cloud LoadBalancer](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html)
- [Spring Boot – Build Systems and Starters](https://docs.spring.io/spring-boot/reference/using/build-systems.html)
