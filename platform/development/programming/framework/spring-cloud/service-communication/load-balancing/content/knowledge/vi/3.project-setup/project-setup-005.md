# Tạo mô hình một bên gọi và nhiều bản sao dịch vụ đích

Bài thực hành này dựng một hệ thống nhỏ để quan sát Spring Cloud LoadBalancer chọn một instance của dịch vụ đích cho mỗi HTTP request. Mô hình gồm một ứng dụng **caller-service** và nhiều tiến trình **inventory-service** chạy cùng một mã nguồn trên các cổng khác nhau.

Caller chỉ gọi dịch vụ bằng service ID `inventory-service`. Danh sách địa chỉ các instance được khai báo ở phía caller thông qua `SimpleDiscoveryClient`. Spring Cloud LoadBalancer lấy danh sách đó và chọn instance trước khi HTTP client gửi request.

Mô hình giúp kiểm tra ba điều: một dịch vụ có thể có nhiều instance cùng phục vụ một API; caller không cần gắn cứng một instance vào code; việc chọn instance diễn ra ở phía client.

## 1. Mô hình cần dựng

Ta tạo hai ứng dụng Spring Boot:

- **inventory-service** cung cấp API xem tồn kho. Chạy cùng một file JAR thành hai tiến trình: cổng 8081 và 8082.
- **caller-service** cung cấp API cho người dùng gọi. Ứng dụng này dùng RestClient đã tích hợp Spring Cloud LoadBalancer để gọi service ID `inventory-service`.

~~~mermaid
flowchart LR
    U["Client / Browser"] -->|"GET :8080/api/inventory/SKU-001"| C["caller-service :8080"]
    C --> LB["Spring Cloud LoadBalancer"]
    SD["SimpleDiscoveryClient<br/>inventory-service"] --> LB
    LB -->|"chọn instance"| I1["inventory-service :8081"]
    LB -->|"hoặc"| I2["inventory-service :8082"]
~~~

| Service ID | Instance | Địa chỉ |
|---|---|---|
| `inventory-service` | Inventory 1 | `http://localhost:8081` |
| `inventory-service` | Inventory 2 | `http://localhost:8082` |

Hai tiến trình inventory có cùng tên ứng dụng và cùng API, nhưng chạy ở hai cổng khác nhau. Chúng là hai instance của cùng một dịch vụ, không phải hai module mã nguồn khác nhau.

Trong bài này, danh sách instance được khai báo tĩnh để dễ chạy trên máy cá nhân. Không cần dựng Eureka Server hoặc Consul. Khi chuyển sang môi trường có service registry, caller sẽ lấy danh sách instance từ registry thay vì tự khai báo địa chỉ.

## 2. Chuẩn bị môi trường và cấu trúc project

Cần có JDK 17 trở lên, Maven 3.8 trở lên, IDE hoặc terminal và một phiên bản Spring Boot cùng Spring Cloud tương thích. RestClient yêu cầu Spring Framework 6.1 trở lên, thường đi cùng Spring Boot 3.2 trở lên. Hãy chọn Spring Cloud release train tương thích với phiên bản Spring Boot theo bảng tương thích chính thức của Spring Cloud. Không ghép ngẫu nhiên các phiên bản Boot, Cloud và Spring Framework.

Tạo project Maven đa module:

~~~text
spring-cloud-load-balancing-lab/
├── pom.xml
├── inventory-service/
│   ├── pom.xml
│   └── src/main/
│       ├── java/com/example/inventory/
│       │   ├── InventoryApplication.java
│       │   └── InventoryController.java
│       └── resources/application.yml
└── caller-service/
    ├── pom.xml
    └── src/main/
        ├── java/com/example/caller/
        │   ├── CallerApplication.java
        │   ├── api/InventoryResponse.java
        │   ├── client/InventoryClient.java
        │   ├── config/HttpClientConfiguration.java
        │   └── web/CallerController.java
        └── resources/application.yml
~~~

Mỗi module là một ứng dụng Spring Boot có thể đóng gói và chạy độc lập. Project cha quản lý phiên bản dùng chung và thứ tự build.

## 3. Khai báo Maven parent và dependency

Ở root `pom.xml`, khai báo packaging `pom`, hai module con và dependency management cho Spring Cloud. Project cha cần kế thừa Spring Boot parent với phiên bản cụ thể đã chọn theo compatibility matrix.

Phần khai báo module và BOM Spring Cloud:

~~~xml
<packaging>pom</packaging>

<modules>
    <module>inventory-service</module>
    <module>caller-service</module>
</modules>

<properties>
    <java.version>17</java.version>
</properties>

<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-dependencies</artifactId>
            <version>REPLACE_WITH_COMPATIBLE_SPRING_CLOUD_RELEASE_TRAIN</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

`REPLACE_WITH_COMPATIBLE_SPRING_CLOUD_RELEASE_TRAIN` là placeholder. Hãy thay bằng một phiên bản release train cụ thể tương thích với Spring Boot parent của project trước khi build.

Module `inventory-service/pom.xml` chỉ cần web starter:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
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
~~~

Module `caller-service/pom.xml` cần web starter để mở API và LoadBalancer starter để phân giải service ID, chọn instance:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
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
~~~

Dependency LoadBalancer chỉ cần nằm ở caller trong mô hình này, vì caller là nơi thực hiện lựa chọn instance. Các inventory instance chỉ nhận HTTP request nên không cần starter đó.

Không cần thêm Eureka Client cho bài thực hành tĩnh này. `SimpleDiscoveryClient` có thể cung cấp danh sách instance từ cấu hình. Khi thay nguồn discovery bằng Eureka, Consul hoặc nền tảng khác, cấu hình dependency và đăng ký service sẽ thay đổi tương ứng.

## 4. Tạo inventory-service

Lớp khởi động:

~~~java
package com.example.inventory;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class InventoryApplication {

    public static void main(String[] args) {
        SpringApplication.run(InventoryApplication.class, args);
    }
}
~~~

API trả về thông tin instance đang xử lý request:

~~~java
package com.example.inventory;

import java.util.Map;

import org.springframework.core.env.Environment;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/inventory")
public class InventoryController {

    private final String port;

    public InventoryController(Environment environment) {
        this.port = environment.getProperty("server.port", "8081");
    }

    @GetMapping("/{sku}")
    public Map<String, Object> getInventory(@PathVariable String sku) {
        return Map.of(
                "sku", sku,
                "available", 100,
                "instance", "inventory:" + port
        );
    }
}
~~~

Trường `instance` giúp nhận biết instance nào đã xử lý request. Trong hệ thống thật, response nghiệp vụ thường không cần tiết lộ cổng nội bộ; thông tin instance nên được quan sát qua log, metric hoặc trace. Ở bài lab, trường này chỉ phục vụ kiểm chứng.

Cấu hình mặc định trong `inventory-service/src/main/resources/application.yml`:

~~~yaml
server:
  port: 8081

spring:
  application:
    name: inventory-service
~~~

Khi chạy tiến trình thứ hai, ghi đè cổng bằng tham số dòng lệnh thành 8082. Cả hai tiến trình dùng cùng artifact và cùng cấu hình ứng dụng.

## 5. Tạo caller-service và load-balanced RestClient

Lớp khởi động:

~~~java
package com.example.caller;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CallerApplication {

    public static void main(String[] args) {
        SpringApplication.run(CallerApplication.class, args);
    }
}
~~~

Khai báo một RestClient.Builder có annotation `@LoadBalanced`:

~~~java
package com.example.caller.config;

import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;

@Configuration
public class HttpClientConfiguration {

    @Bean
    @LoadBalanced
    RestClient.Builder loadBalancedRestClientBuilder() {
        return RestClient.builder();
    }
}
~~~

Annotation `@LoadBalanced` đánh dấu builder để Spring Cloud bổ sung cơ chế xử lý URI có service ID. Nếu tạo RestClient thông thường mà không có tích hợp này, tên `inventory-service` sẽ bị xử lý như hostname thông thường và không được chọn instance từ danh sách discovery.

DTO nhận response từ inventory-service:

~~~java
package com.example.caller.api;

public record InventoryResponse(
        String sku,
        int available,
        String instance
) {
}
~~~

Service client gọi dịch vụ đích:

~~~java
package com.example.caller.client;

import com.example.caller.api.InventoryResponse;
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClient;

@Service
public class InventoryClient {

    private final RestClient restClient;

    public InventoryClient(@LoadBalanced RestClient.Builder builder) {
        this.restClient = builder
                .baseUrl("http://inventory-service")
                .build();
    }

    public InventoryResponse getInventory(String sku) {
        return restClient.get()
                .uri("/api/inventory/{sku}", sku)
                .retrieve()
                .body(InventoryResponse.class);
    }
}
~~~

Base URL chứa service ID `inventory-service`, không chứa cổng 8081 hoặc 8082. Caller không cần biết instance nào sẽ xử lý request. Việc chọn instance thuộc trách nhiệm của Spring Cloud LoadBalancer.

Endpoint bên ngoài để gọi thử:

~~~java
package com.example.caller.web;

import com.example.caller.api.InventoryResponse;
import com.example.caller.client.InventoryClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/inventory")
public class CallerController {

    private final InventoryClient inventoryClient;

    public CallerController(InventoryClient inventoryClient) {
        this.inventoryClient = inventoryClient;
    }

    @GetMapping("/{sku}")
    public InventoryResponse getInventory(@PathVariable String sku) {
        return inventoryClient.getInventory(sku);
    }
}
~~~

Endpoint của caller có cùng đường dẫn nghiệp vụ để người kiểm thử chỉ cần gọi một địa chỉ. Request đi qua caller rồi được chuyển tiếp đến một inventory instance.

## 6. Khai báo danh sách instance ở caller

Trong `caller-service/src/main/resources/application.yml`:

~~~yaml
server:
  port: 8080

spring:
  application:
    name: caller-service
  cloud:
    discovery:
      client:
        simple:
          instances:
            inventory-service:
              - uri: http://localhost:8081
              - uri: http://localhost:8082
~~~

Cấu hình khai báo hai ServiceInstance thuộc cùng service ID `inventory-service`. SimpleDiscoveryClient đọc danh sách và cung cấp cho cơ chế discovery của Spring Cloud.

Cần phân biệt ba tên:

- `caller-service` là tên ứng dụng caller.
- `inventory-service` là service ID mà caller sử dụng để tìm dịch vụ đích.
- `localhost:8081` và `localhost:8082` là địa chỉ vật lý của các instance.

Không đưa URL instance vào `InventoryClient`. Khi tăng số bản sao, ta cập nhật nguồn discovery hoặc cấu hình danh sách instance; code gọi dịch vụ vẫn dùng service ID.

Với danh sách tĩnh, người vận hành phải cập nhật địa chỉ khi thêm hoặc bỏ instance. Mô hình này phù hợp để học và chạy local. Môi trường có autoscaling nên dùng service registry hoặc nền tảng orchestration để cập nhật instance tự động.

## 7. Build và chạy ba tiến trình

Mở terminal tại thư mục root `spring-cloud-load-balancing-lab` và build toàn bộ module:

~~~bash
mvn clean package
~~~

Sau khi build thành công, mở ba terminal riêng.

Terminal 1 chạy instance inventory thứ nhất:

~~~bash
java -jar inventory-service/target/inventory-service-1.0.0-SNAPSHOT.jar --server.port=8081
~~~

Terminal 2 chạy cùng JAR trên cổng 8082:

~~~bash
java -jar inventory-service/target/inventory-service-1.0.0-SNAPSHOT.jar --server.port=8082
~~~

Terminal 3 chạy caller:

~~~bash
java -jar caller-service/target/caller-service-1.0.0-SNAPSHOT.jar
~~~

Tên file JAR phụ thuộc vào `artifactId` và `version` trong POM. Nếu project dùng version khác, thay đúng tên file được tạo trong thư mục `target`. Có thể chạy các ứng dụng bằng cấu hình Run của IDE thay cho lệnh `java -jar`, miễn là mỗi tiến trình có cổng riêng.

Kiểm tra trực tiếp hai inventory instance:

~~~powershell
Invoke-RestMethod http://localhost:8081/api/inventory/SKU-001
Invoke-RestMethod http://localhost:8082/api/inventory/SKU-001
~~~

Kết quả phải có cùng SKU và nghiệp vụ mẫu, nhưng trường `instance` lần lượt cho biết `inventory:8081` và `inventory:8082`.

## 8. Kiểm tra caller có phân phối request

Gọi caller nhiều lần:

~~~powershell
1..8 | ForEach-Object {
    Invoke-RestMethod http://localhost:8080/api/inventory/SKU-001 |
        Select-Object sku, available, instance
}
~~~

Response đi qua caller và được LoadBalancer chuyển đến một trong hai inventory instance. Với cấu hình mặc định, Spring Cloud LoadBalancer sử dụng chiến lược Round Robin trong trường hợp thông thường, vì vậy các request lặp lại sẽ được phân phối luân phiên giữa các instance còn trong danh sách.

Ví dụ kết quả quan sát:

~~~text
sku      available instance
---      --------- --------
SKU-001  100       inventory:8081
SKU-001  100       inventory:8082
SKU-001  100       inventory:8081
SKU-001  100       inventory:8082
SKU-001  100       inventory:8081
SKU-001  100       inventory:8082
SKU-001  100       inventory:8081
SKU-001  100       inventory:8082
~~~

Đây là kết quả minh họa cho hai instance khỏe mạnh và các request được gửi tuần tự. Trong môi trường có request đồng thời, retry, thay đổi danh sách instance hoặc chính sách chọn khác, thứ tự quan sát có thể khác. Điều cần xác minh là cả hai instance đều có thể nhận request từ cùng một caller thông qua service ID.

Nếu chỉ thấy một instance, kiểm tra lần lượt:

1. Cả hai tiến trình inventory đã khởi động và đang lắng nghe đúng cổng.
2. Gọi trực tiếp từng URL 8081 và 8082 đều thành công.
3. Service ID trong `baseUrl` khớp chính xác với khóa `inventory-service` trong cấu hình discovery.
4. Bean RestClient.Builder được đánh dấu `@LoadBalanced`.
5. Caller có dependency `spring-cloud-starter-loadbalancer` và đã khởi động lại sau khi thay đổi cấu hình.
6. Không có cấu hình khác ghi đè danh sách instance hoặc chính sách load balancing.

## 9. Kiểm tra lỗi và hiểu giới hạn của mô hình local

Thử dừng tiến trình inventory ở cổng 8082, sau đó tiếp tục gọi caller. Danh sách SimpleDiscoveryClient vẫn chứa địa chỉ 8082 vì danh sách được khai báo tĩnh. LoadBalancer có thể tiếp tục chọn địa chỉ đó và request sẽ gặp lỗi kết nối.

Điều này cho thấy danh sách discovery và trạng thái sức khỏe thực tế là hai vấn đề riêng. Khai báo một URI trong danh sách không chứng minh instance đang hoạt động. Bài lab này chưa cấu hình health check, retry hoặc circuit breaker; hãy bổ sung các cơ chế đó ở bước học tương ứng và quan sát hành vi khi một instance lỗi.

Khôi phục tiến trình 8082 rồi gọi lại để xác nhận cả hai instance phản hồi bình thường. Khi thử nghiệm, ghi nhận thời điểm lỗi, instance được chọn và loại exception để phân biệt lỗi kết nối với lỗi HTTP hoặc lỗi nghiệp vụ.

Một số giới hạn khi chạy local:

- `localhost` luôn trỏ về máy hoặc network namespace của tiến trình đang gọi. Nếu caller chạy trong container, `localhost:8081` là chính container caller, không phải container inventory khác. Khi dùng Docker Compose, khai báo địa chỉ theo DNS service/container trên cùng network.
- Hai instance không được dùng chung một cổng trên cùng host.
- Danh sách SimpleDiscoveryClient không tự thêm hoặc xóa instance khi tiến trình khởi động hay dừng.
- Hai bản sao trong bài lab dùng chung mã nguồn và dữ liệu mẫu trong bộ nhớ. Đây chưa phải mô hình chia sẻ database hoặc kiểm tra tính nhất quán dữ liệu giữa nhiều replica.
- Load balancing phân phối request đến instance. Nó không tự xử lý timeout, retry, circuit breaker, xác thực hay transaction phân tán.

## 10. Mở rộng mô hình sau khi chạy thành công

Sau khi kiểm chứng được một caller gọi nhiều inventory instance, có thể mở rộng theo từng bước:

| Bước mở rộng | Thay đổi | Mục tiêu |
|---|---|---|
| Thêm instance thứ ba | Thêm URI cổng 8083 vào danh sách discovery và chạy thêm tiến trình | Quan sát khả năng mở rộng theo số replica |
| Dùng service registry | Thay SimpleDiscoveryClient bằng Eureka hoặc Consul | Đăng ký và khám phá instance động |
| Đổi HTTP client | Tích hợp WebClient hoặc OpenFeign với LoadBalancer | So sánh cách gọi imperative, reactive và declarative |
| Thêm timeout/retry | Cấu hình ở HTTP client và Spring Cloud LoadBalancer theo nhu cầu | Giới hạn thời gian chờ và xử lý lỗi tạm thời |
| Bổ sung health check | Lọc instance không khỏe khỏi danh sách có thể chọn | Hạn chế gửi request đến instance không đáp ứng |
| Thêm quan sát | Ghi log, metric và trace cho service ID, instance, latency, status | Điều tra phân phối request và lỗi thực tế |

Khi chuyển sang WebClient hoặc OpenFeign, service ID vẫn là tên logic của dịch vụ đích. Cơ chế tích hợp tương ứng sẽ dùng danh sách ServiceInstance để chọn địa chỉ. Mỗi client có cách cấu hình và kiểu trả kết quả riêng, nhưng ranh giới discovery và lựa chọn instance vẫn giữ nguyên.

Mô hình một caller và nhiều replica tạo nền tảng để thực hành Spring Cloud LoadBalancer. Caller chỉ phụ thuộc vào service ID; discovery cung cấp các instance; LoadBalancer chọn một instance; HTTP client gửi request đến địa chỉ được chọn. Khi hiểu rõ luồng này, ta có thể thay nguồn discovery, thêm replica và bổ sung các chính sách chịu lỗi mà không đưa địa chỉ vật lý của từng instance vào code nghiệp vụ.
