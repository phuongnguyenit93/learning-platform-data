# Chạy nhiều instance và chứng minh bên gọi dùng tên dịch vụ

## 1. Mục tiêu thực hành

Trong microservice, bên gọi nên tìm dịch vụ theo service ID thay vì gắn cứng IP và port của một instance. Khi có nhiều replica, registry cung cấp danh sách instance; client-side load balancer chọn một instance trong danh sách để gửi request.

Bài thực hành dựng một môi trường nhỏ bằng Spring Cloud Netflix Eureka:

- Một **Eureka Server** chạy tại cổng 8761.
- Hai tiến trình **inventory-service** cùng đăng ký dưới service ID inventory-service, lần lượt chạy tại cổng 8081 và 8082.
- Một **order-service** chạy tại cổng 8080.
- order-service gọi inventory-service bằng URL logic http://inventory-service/api/instance.

Kết quả cần chứng minh:

1. Eureka hiển thị hai instance của cùng một service.
2. DiscoveryClient của order-service tìm được cả hai địa chỉ.
3. Request từ order-service dùng service ID inventory-service, không chứa host/port cụ thể.
4. Spring Cloud LoadBalancer phân phối các request đến các instance đã đăng ký.
5. Khi một instance dừng, request tiếp theo có thể tiếp tục được xử lý bởi instance còn lại sau khi trạng thái registry được cập nhật.

## 2. Kiến trúc lab

~~~mermaid
flowchart TD
    E[Eureka Server :8761]
    I1[inventory-service instance A :8081]
    I2[inventory-service instance B :8082]
    O[order-service :8080]
    E <-->|register / heartbeat / fetch| I1
    E <-->|register / heartbeat / fetch| I2
    E <-->|registry fetch| O
    O -->|http://inventory-service/api/instance| LB[Spring Cloud LoadBalancer]
    LB --> I1
    LB --> I2
~~~

Eureka lưu thông tin đăng ký và cung cấp danh sách instance. order-service lấy danh sách qua discovery integration; LoadBalancer chọn instance cho từng request. URL logic chứa service ID, còn địa chỉ vật lý được chọn ở runtime.

## 3. Chuẩn bị dự án

Có thể tổ chức ba ứng dụng độc lập trong cùng workspace:

~~~text
service-discovery-lab/
  eureka-server/
    pom.xml
    src/main/java/...
    src/main/resources/application.yml
  inventory-service/
    pom.xml
    src/main/java/...
    src/main/resources/application.yml
  order-service/
    pom.xml
    src/main/java/...
    src/main/resources/application.yml
~~~

Mỗi ứng dụng có Spring Boot main class riêng. Dùng cùng một Spring Cloud release train tương thích với phiên bản Spring Boot của dự án. Quản lý dependency qua Spring Cloud BOM; không trộn các version Eureka, Commons và LoadBalancer khác release train.

### 3.1. Dependency theo ứng dụng

| Ứng dụng | Dependency chính |
|---|---|
| eureka-server | spring-boot-starter-web, spring-cloud-starter-netflix-eureka-server |
| inventory-service | spring-boot-starter-web, spring-cloud-starter-netflix-eureka-client |
| order-service | spring-boot-starter-web, spring-cloud-starter-netflix-eureka-client, spring-cloud-starter-loadbalancer |

Ví dụ dependency management Maven dùng chung cho cả ba ứng dụng:

~~~xml
<properties>
    <spring-cloud.version>YOUR_COMPATIBLE_RELEASE_TRAIN</spring-cloud.version>
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
~~~

Thay YOUR_COMPATIBLE_RELEASE_TRAIN bằng release train tương thích với Spring Boot đang dùng theo bảng tương thích chính thức. Các dependency ứng dụng khai báo version do BOM quản lý.

Ví dụ phần dependencies của Eureka Server:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-netflix-eureka-server</artifactId>
    </dependency>
</dependencies>
~~~

Inventory Client:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-netflix-eureka-client</artifactId>
    </dependency>
</dependencies>
~~~

Order Client:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
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
~~~

## 4. Tạo Eureka Server

### 4.1. Main class

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

### 4.2. Cấu hình application.yml

~~~yaml
server:
  port: 8761

spring:
  application:
    name: eureka-server

eureka:
  client:
    register-with-eureka: false
    fetch-registry: false
~~~

Hai thuộc tính register-with-eureka và fetch-registry được tắt vì lab dùng node này làm registry server độc lập, không đăng ký nó như một client service và không cần lấy registry từ peer khác.

Không cần tắt self-preservation của Eureka để hoàn thành lab. Cơ chế này là một phần bảo vệ registry khi heartbeat giảm bất thường; hãy hiểu tác động của nó trước khi thay đổi trong môi trường thật.

## 5. Tạo inventory-service

Inventory service sẽ trả về danh tính của chính instance đang nhận request. Hai process cùng chạy một ứng dụng và cùng service ID, nhưng port khác nhau.

### 5.1. Main class

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

Không cần tạo hai codebase hoặc đổi tên service cho hai replica. Cả hai process dùng cùng spring.application.name là inventory-service; instance ID phải khác nhau để registry phân biệt chúng.

### 5.2. Endpoint trả về instance hiện tại

~~~java
package com.example.inventory.api;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class InventoryController {

    @Value("${spring.application.name}")
    private String serviceName;

    @Value("${server.port}")
    private int port;

    @GetMapping("/api/instance")
    public String instance() {
        return serviceName + " | port=" + port;
    }
}
~~~

Endpoint này trả về port thực tế của instance nhận request. Đây là bằng chứng trực quan để biết LoadBalancer đã chọn replica nào.

### 5.3. Cấu hình application.yml

~~~yaml
server:
  port: 8081

spring:
  application:
    name: inventory-service

eureka:
  client:
    service-url:
      defaultZone: http://localhost:8761/eureka/
    register-with-eureka: true
    fetch-registry: true
    registry-fetch-interval-seconds: 5
  instance:
    instance-id: ${spring.application.name}:${server.port}
    prefer-ip-address: true
~~~

Điểm quan trọng là instance ID được tạo từ service name và port. Nếu hai process cùng dùng một instance ID, chúng có thể xung đột hoặc ghi đè thông tin đăng ký tùy cách registry xử lý. Hai port tạo ra hai ID riêng:

- inventory-service:8081
- inventory-service:8082

registry-fetch-interval-seconds được đặt thấp để quan sát nhanh trong lab. Không nên tự động dùng chu kỳ ngắn như vậy cho mọi production workload; fetch quá thường xuyên làm tăng lưu lượng registry.

## 6. Chạy hai inventory instance

Đóng gói ứng dụng:

~~~powershell
cd inventory-service
mvn -DskipTests package
~~~

Mở hai terminal riêng trong thư mục inventory-service. Chạy instance thứ nhất:

~~~powershell
java -jar target/inventory-service.jar --server.port=8081
~~~

Chạy instance thứ hai:

~~~powershell
java -jar target/inventory-service.jar --server.port=8082
~~~

Nếu tên JAR thực tế có version, dùng đúng tên trong thư mục target. Có thể chạy bằng Maven plugin thay cho JAR:

~~~powershell
mvn spring-boot:run "-Dspring-boot.run.arguments=--server.port=8081"
~~~

Mở terminal thứ hai và dùng port 8082 cho process còn lại.

Mỗi process phải:

1. Mở HTTP server trên port riêng.
2. Kết nối tới Eureka Server.
3. Đăng ký cùng service ID inventory-service.
4. Công bố instance ID riêng.
5. Gửi heartbeat theo cấu hình Eureka Client.

## 7. Xác minh registry có hai instance

Mở Eureka Dashboard:

~~~text
http://localhost:8761
~~~

Trong danh sách application, tìm INVENTORY-SERVICE. Kết quả mong đợi là có hai instance với địa chỉ/port tương ứng 8081 và 8082.

Có thể truy vấn Eureka REST API:

~~~powershell
$headers = @{ Accept = "application/json" }
Invoke-RestMethod -Uri "http://localhost:8761/eureka/apps/INVENTORY-SERVICE" -Headers $headers
~~~

Response JSON có thể chứa application name và danh sách instance. Cấu trúc field phụ thuộc phiên bản Eureka; điều cần xác minh là có hai instance khác nhau và mỗi instance có host/port, status phù hợp.

Nếu dashboard chưa hiển thị đủ hai instance:

- Kiểm tra log startup của cả hai inventory process.
- Xác nhận cả hai dùng đúng defaultZone.
- Xác nhận instance ID khác nhau.
- Kiểm tra port 8081 và 8082 không bị process khác chiếm.
- Đợi client/server cập nhật registry theo chu kỳ fetch và heartbeat.

Không chuyển sang bước caller trước khi registry hiển thị đủ hai instance. Điều này giúp tách lỗi đăng ký khỏi lỗi LoadBalancer.

## 8. Tạo order-service gọi bằng tên dịch vụ

Đây là phần chứng minh chính. Order service không biết inventory instance nằm ở port 8081 hay 8082. Nó chỉ biết service ID inventory-service.

### 8.1. Main class

~~~java
package com.example.order;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OrderApplication {

    public static void main(String[] args) {
        SpringApplication.run(OrderApplication.class, args);
    }
}
~~~

### 8.2. Khai báo LoadBalanced RestTemplate

~~~java
package com.example.order.config;

import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestTemplate;

@Configuration
public class HttpClientConfiguration {

    @Bean
    @LoadBalanced
    public RestTemplate loadBalancedRestTemplate() {
        return new RestTemplate();
    }
}
~~~

Annotation LoadBalanced gắn interceptor của Spring Cloud LoadBalancer vào RestTemplate. Khi URL có host là service ID, LoadBalancer tra cứu danh sách instance và chọn một endpoint thực tế.

Nếu bỏ annotation này, RestTemplate thông thường sẽ coi inventory-service là hostname DNS. Trong lab không có DNS record như vậy nên request thường thất bại với UnknownHostException.

### 8.3. Gọi service bằng logical name

~~~java
package com.example.order.api;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.client.RestTemplate;

@RestController
public class OrderController {

    private final RestTemplate restTemplate;

    public OrderController(RestTemplate restTemplate) {
        this.restTemplate = restTemplate;
    }

    @GetMapping("/orders/check-inventory")
    public String checkInventory() {
        return restTemplate.getForObject(
                "http://inventory-service/api/instance",
                String.class);
    }
}
~~~

URL gọi chứa inventory-service thay vì localhost:8081 hoặc localhost:8082. Đây là bằng chứng trong code rằng bên gọi dùng tên dịch vụ. Địa chỉ cụ thể chỉ được chọn sau khi LoadBalancer nhận danh sách instance từ discovery.

### 8.4. Cấu hình application.yml

~~~yaml
server:
  port: 8080

spring:
  application:
    name: order-service

eureka:
  client:
    service-url:
      defaultZone: http://localhost:8761/eureka/
    register-with-eureka: true
    fetch-registry: true
    registry-fetch-interval-seconds: 5

logging:
  level:
    org.springframework.cloud.loadbalancer: DEBUG
~~~

Log DEBUG là tùy chọn hỗ trợ quan sát quá trình chọn instance. Trong production, chọn log level phù hợp để tránh log quá nhiều.

## 9. Chạy toàn bộ lab theo thứ tự

Từ thư mục gốc service-discovery-lab, đóng gói cả ba ứng dụng:

~~~powershell
cd eureka-server
mvn -DskipTests package
cd ..\inventory-service
mvn -DskipTests package
cd ..\order-service
mvn -DskipTests package
cd ..
~~~

Tên JAR phụ thuộc artifactId, version và cấu hình build của từng POM. Các lệnh java -jar bên dưới dùng tên minh họa; hãy thay bằng tên file thực tế trong thư mục target hoặc cấu hình finalName riêng cho từng ứng dụng.

Mở các terminal riêng và khởi động:

| Thứ tự | Ứng dụng | Port |
|---|---|---:|
| 1 | Eureka Server | 8761 |
| 2 | inventory-service instance A | 8081 |
| 3 | inventory-service instance B | 8082 |
| 4 | order-service | 8080 |

Khởi động Eureka Server:

~~~powershell
cd eureka-server
java -jar target/eureka-server.jar
~~~

Đợi server sẵn sàng tại http://localhost:8761.

Khởi động hai inventory process bằng hai lệnh ở phần 6. Sau đó xác minh Eureka hiển thị đủ hai instance.

Khởi động order-service:

~~~powershell
cd order-service
java -jar target/order-service.jar
~~~

Nếu dùng Maven plugin, chạy:

~~~powershell
mvn spring-boot:run
~~~

## 10. Gửi nhiều request và quan sát LoadBalancer

Gọi endpoint của order-service nhiều lần:

~~~powershell
1..10 | ForEach-Object {
    Invoke-RestMethod -Uri "http://localhost:8080/orders/check-inventory"
}
~~~

Kết quả minh họa:

~~~text
inventory-service | port=8081
inventory-service | port=8082
inventory-service | port=8081
inventory-service | port=8082
inventory-service | port=8081
...
~~~

Với Spring Cloud LoadBalancer mặc định dùng RoundRobinLoadBalancer, các request tuần tự thường luân phiên giữa các instance đang có trong danh sách. Thứ tự đầu tiên không cố định. Kết quả có thể khác khi có retry, cache cập nhật, instance thay đổi trạng thái hoặc có request đồng thời.

Điều cần chứng minh là nhiều request đã đến được cả port 8081 và 8082 thông qua cùng endpoint order-service.

## 11. Chứng minh discovery trả về hai instance

Có thể thêm một endpoint chẩn đoán vào order-service để đọc danh sách từ DiscoveryClient. Endpoint này không thay thế request LoadBalancer; nó chỉ cho thấy dữ liệu discovery mà caller nhận được.

~~~java
package com.example.order.api;

import java.util.List;
import java.util.stream.Collectors;

import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.discovery.DiscoveryClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DiscoveryDiagnosticsController {

    private final DiscoveryClient discoveryClient;

    public DiscoveryDiagnosticsController(DiscoveryClient discoveryClient) {
        this.discoveryClient = discoveryClient;
    }

    @GetMapping("/orders/inventory-instances")
    public List<String> inventoryInstances() {
        return discoveryClient.getInstances("inventory-service")
                .stream()
                .map(ServiceInstance::getUri)
                .map(Object::toString)
                .collect(Collectors.toList());
    }
}
~~~

Gọi endpoint:

~~~powershell
Invoke-RestMethod -Uri "http://localhost:8080/orders/inventory-instances"
~~~

Kết quả mong đợi có hai URI tương ứng với port 8081 và 8082. Endpoint này dùng service ID rõ ràng để truy vấn DiscoveryClient.

Không expose endpoint liệt kê topology nội bộ như vậy ra public API production nếu không có mục đích vận hành và kiểm soát truy cập phù hợp.

## 12. Thử dừng một instance

Để kiểm tra thay đổi danh sách:

1. Gửi một số request và xác nhận cả 8081 lẫn 8082 đang được chọn.
2. Dừng process inventory-service chạy port 8081 bằng Ctrl+C.
3. Theo dõi Eureka Dashboard để xem instance 8081 được deregister hoặc chuyển trạng thái.
4. Chờ order-service nhận được danh sách cập nhật.
5. Gọi lại endpoint check-inventory nhiều lần.
6. Xác nhận các response mới đến từ port 8082.

Eureka Client thường gửi deregistration khi shutdown bình thường. Nếu process bị kill đột ngột hoặc mạng bị phân vùng, registry có thể chỉ phát hiện instance mất sau heartbeat/lease expiration và eviction. Self-preservation có thể làm chậm việc eviction khi số heartbeat giảm bất thường.

Do đó, không yêu cầu instance biến mất ngay trong cùng một mili giây khi process dừng. Hãy quan sát status, thời điểm deregistration và cache refresh của client.

Sau khi xác minh, có thể khởi động lại instance A:

~~~powershell
java -jar target/inventory-service.jar --server.port=8081
~~~

Chờ Eureka hiển thị lại hai instance rồi lặp lại request.

## 13. Bằng chứng cần thu thập

Một buổi thực hành được xem là đạt khi có đủ các bằng chứng:

| Bằng chứng | Cách xác minh | Kết quả mong đợi |
|---|---|---|
| Eureka Server hoạt động | Mở dashboard port 8761 | Dashboard truy cập được |
| Hai instance đăng ký cùng service ID | Dashboard hoặc REST API | INVENTORY-SERVICE có hai instance |
| Instance ID khác nhau | Dashboard/REST API | Một ID cho port 8081, một ID cho port 8082 |
| DiscoveryClient thấy hai instance | Endpoint diagnostics | Hai URI trong danh sách |
| Caller dùng service name | Đọc OrderController | URL có inventory-service, không có port cố định |
| LoadBalancer chọn nhiều instance | Gọi endpoint lặp lại | Response có cả 8081 và 8082 |
| Một instance dừng | Dừng port 8081 rồi quan sát | Sau cập nhật, request mới dùng port 8082 |

Có thể chụp dashboard, output của endpoint diagnostics, output gọi lặp và đoạn code OrderController làm bằng chứng cho báo cáo thực hành.

## 14. Phân biệt các lớp khi có lỗi

| Triệu chứng | Lớp cần kiểm tra | Cách xử lý |
|---|---|---|
| Eureka Dashboard không mở | Eureka Server | Kiểm tra process, port 8761 và startup log |
| Inventory không xuất hiện | Registration | Kiểm tra defaultZone, client log, service name và network |
| Chỉ có một instance | Instance identity | Kiểm tra port, instance-id và xung đột process |
| DiscoveryClient trả danh sách rỗng | Registry fetch/cache | Kiểm tra fetch-registry, lần fetch gần nhất và Eureka REST API |
| Caller báo No instances available | Discovery/LoadBalancer | Xác nhận registry có instance và caller đã fetch |
| Caller báo UnknownHostException | HTTP client chưa được load-balanced | Kiểm tra @LoadBalanced và starter-loadbalancer |
| Caller chỉ gọi một port | Registry list hoặc policy/cache | Kiểm tra danh sách instance mà caller thấy, log LoadBalancer và cache |
| Dừng instance nhưng caller vẫn gọi nó | Cache/eviction | Kiểm tra graceful deregistration, lease, self-preservation và fetch interval |
| Caller timeout tới một instance | Data plane | Kiểm tra host/port được Eureka công bố, firewall và listener của instance |

## 15. Những lỗi cấu hình thường gặp

### 15.1. Dùng địa chỉ vật lý trong URL caller

Ví dụ không chứng minh service discovery:

~~~java
restTemplate.getForObject(
        "http://localhost:8081/api/instance",
        String.class);
~~~

URL này luôn gọi port 8081 và bỏ qua service ID. Khi port hoặc host thay đổi, caller phải sửa cấu hình.

### 15.2. Quên @LoadBalanced

RestTemplate không có interceptor LoadBalancer sẽ xem inventory-service như DNS hostname. Thêm dependency LoadBalancer và gắn @LoadBalanced vào đúng bean được inject vào controller.

### 15.3. Hai replica dùng chung instance ID

Nếu instance ID cố định, registry có thể coi hai process là cùng một registration. Hãy tạo ID khác nhau dựa trên port, hostname hoặc một định danh replica duy nhất.

### 15.4. Khởi động caller quá sớm

Nếu order-service fetch registry trước khi inventory đăng ký, danh sách ban đầu có thể rỗng. Chờ registry có hai instance hoặc chờ lần fetch tiếp theo rồi kiểm tra lại. Trong môi trường production, caller phải xử lý trường hợp service chưa có instance khi startup.

### 15.5. Eureka công bố địa chỉ không thể truy cập

Trong Docker hoặc nhiều máy, prefer-ip-address chỉ có ích khi IP mà Eureka công bố có thể truy cập từ caller. Không dùng localhost làm địa chỉ quảng bá giữa các container vì localhost trong mỗi container trỏ về chính container đó. Dùng hostname hoặc IP thuộc network mà caller có route tới.

### 15.6. Kỳ vọng xóa instance stale tức thì

Graceful shutdown có thể deregister nhanh, nhưng crash hoặc partition cần lease expiration/eviction. Client cũng có fetch interval và cache riêng. Kiểm tra từng mốc thời gian thay vì kết luận discovery sai chỉ vì một request ngay sau shutdown vẫn chọn instance cũ.

## 16. Mở rộng thực hành

Sau khi lab cơ bản chạy thành công, có thể mở rộng theo các hướng:

- Thêm instance thứ ba ở port 8083 và xác minh LoadBalancer phân phối trên ba replica.
- Thêm metadata zone cho instance và tìm hiểu zone preference của Spring Cloud LoadBalancer.
- Thử một instance không sẵn sàng và quan sát cách provider/health check cập nhật registry.
- Dừng Eureka Server trong khi client vẫn chạy để quan sát registry cache và khả năng tiếp tục request.
- Thử restart order-service và xác minh client fetch lại registry.
- Thêm timeout, retry và circuit breaker cho lời gọi nghiệp vụ.
- Chuyển lab sang Consul hoặc Kubernetes Discovery để so sánh cách cung cấp instance list.

Mỗi lần chỉ thay đổi một yếu tố và ghi lại kết quả trước/sau. Điều này giúp phân biệt hành vi của registry, DiscoveryClient, LoadBalancer và network.

## 17. Checklist hoàn thành

- [ ] Eureka Server khởi động và dashboard truy cập được.
- [ ] Hai inventory process chạy trên port 8081 và 8082.
- [ ] Cả hai đăng ký dưới service ID inventory-service.
- [ ] Hai instance có instance ID khác nhau.
- [ ] Eureka hiển thị đủ hai instance.
- [ ] order-service khởi động và lấy được registry.
- [ ] RestTemplate bean có annotation @LoadBalanced.
- [ ] Caller gọi URL http://inventory-service/api/instance.
- [ ] Nhiều request trả về cả port 8081 và 8082.
- [ ] Discovery diagnostics trả về hai URI.
- [ ] Sau khi dừng một instance và registry/cache cập nhật, request mới dùng instance còn lại.
- [ ] Ghi lại dashboard, output và code làm bằng chứng.

## 18. Tổng kết

Bài thực hành dùng Eureka làm registry, chạy hai process inventory-service với cùng service ID nhưng instance ID khác nhau, rồi để order-service gọi qua URL logic http://inventory-service/api/instance. Annotation @LoadBalanced giúp RestTemplate chuyển service ID thành một instance cụ thể thông qua Spring Cloud LoadBalancer và DiscoveryClient.

Khi cả hai instance xuất hiện trong Eureka và các request từ order-service đi tới cả hai port, ta đã chứng minh được bên gọi phụ thuộc vào tên dịch vụ thay vì địa chỉ cố định. Khi dừng một instance, cần quan sát deregistration, heartbeat/eviction và client cache trước khi xác nhận LoadBalancer chỉ còn chọn instance còn lại.

## 19. Tài liệu tham khảo

- [Spring Cloud Netflix — Eureka Client and Server](https://docs.spring.io/spring-cloud-netflix/reference/spring-cloud-netflix.html)
- [Spring Cloud Commons — LoadBalancer](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html)
- [Spring Cloud Commons — DiscoveryClient](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html)
- [Spring Cloud — Release Train and Spring Boot Compatibility](https://spring.io/projects/spring-cloud)

Chọn release train tương thích với Spring Boot và kiểm tra API/configuration properties theo đúng version của dự án.
