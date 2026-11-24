# Chạy sổ đăng ký và nhiều phiên bản dịch vụ bằng Docker Compose

Một ứng dụng microservice thường có nhiều instance cùng cung cấp một dịch vụ. Các instance có thể được cập nhật theo từng phiên bản, khởi động lại hoặc tăng giảm số lượng. Consumer cần gọi theo tên logic của dịch vụ thay vì lưu cố định địa chỉ IP và cổng của từng container.

Bài này dựng một môi trường thực hành cục bộ bằng Docker Compose gồm một Eureka Server, hai phiên bản của dịch vụ tồn kho và một consumer. Hai provider đăng ký cùng serviceId là `inventory-service`, nhưng có instance ID và phiên bản ứng dụng khác nhau. Consumer gọi `http://inventory-service`; Spring Cloud LoadBalancer tra cứu registry, chọn một instance rồi chuyển request đến địa chỉ mạng của container đó.

Môi trường này giúp kiểm tra cấu hình, mạng Docker, đăng ký dịch vụ và định tuyến giữa nhiều instance. Đây là lab để học và kiểm chứng tích hợp, không phải cấu hình production hoàn chỉnh.

## 1. Kiểm tra phiên bản và dependency trước khi chạy

Spring Boot và Spring Cloud được phát hành theo các dòng phiên bản có quan hệ tương thích. Trước khi dựng registry, hãy chọn một phiên bản Spring Boot và một Spring Cloud release train nằm trong ma trận tương thích chính thức của Spring Cloud. Tất cả module trong lab nên dùng cùng một release train để tránh việc provider và consumer nạp các phiên bản thư viện khác nhau.

Dùng Spring Cloud BOM để quản lý phiên bản dependency:

~~~groovy
plugins {
    id 'io.spring.dependency-management' version '<dependency-management-plugin-version>'
}

ext {
    // Thay bằng release train tương thích với Spring Boot của dự án.
    set('springCloudVersion', '<compatible-spring-cloud-release-train>')
}

dependencyManagement {
    imports {
        mavenBom "org.springframework.cloud:spring-cloud-dependencies:${springCloudVersion}"
    }
}
~~~

Các dependency chính theo vai trò:

| Ứng dụng | Dependency cần có | Mục đích |
|---|---|---|
| Eureka Server | `spring-cloud-starter-netflix-eureka-server` | Chạy registry |
| Provider inventory | `spring-cloud-starter-netflix-eureka-client` | Đăng ký instance và trao đổi với registry |
| Consumer order | `spring-cloud-starter-netflix-eureka-client` | Tra cứu registry |
| Consumer order | `spring-cloud-starter-loadbalancer` | Chọn instance cho lời gọi theo serviceId |
| Các ứng dụng cần health endpoint | `spring-boot-starter-actuator` | Cung cấp trạng thái health để quan sát và kiểm tra |

Consumer dùng `WebClient` cần thêm `spring-boot-starter-webflux`. Nếu dùng `RestClient` hoặc `RestTemplate`, chọn starter web tương ứng với stack của ứng dụng.

Ví dụ dependency cho Eureka Server:

~~~groovy
dependencies {
    implementation 'org.springframework.cloud:spring-cloud-starter-netflix-eureka-server'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
~~~

Ví dụ dependency cho provider và consumer:

~~~groovy
dependencies {
    implementation 'org.springframework.cloud:spring-cloud-starter-netflix-eureka-client'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
~~~

Thêm dependency LoadBalancer và WebFlux ở module consumer nếu ứng dụng dùng `@LoadBalanced WebClient.Builder`:

~~~groovy
dependencies {
    implementation 'org.springframework.cloud:spring-cloud-starter-loadbalancer'
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
}
~~~

Không gán phiên bản riêng cho từng Spring Cloud starter khi đã import BOM. Không trộn starter từ nhiều release train. Nếu gặp lỗi class không tồn tại, method không tương thích hoặc auto-configuration không hoạt động, hãy kiểm tra dependency tree và phiên bản Boot/Cloud trước khi sửa code.

## 2. Mô hình môi trường thực hành

Lab có bốn vai trò:

- `eureka-server`: registry nhận thông tin đăng ký và trả danh sách instance.
- `inventory-v1`: phiên bản thứ nhất của provider, đăng ký dưới tên `inventory-service`.
- `inventory-v2`: phiên bản thứ hai của cùng provider, cũng đăng ký dưới tên `inventory-service`.
- `order-service`: consumer gọi inventory thông qua serviceId và LoadBalancer.

~~~mermaid
flowchart TB
    subgraph DockerCompose["Docker Compose network: discovery"]
        E["eureka-server:8761"]
        V1["inventory-v1<br/>serviceId: inventory-service<br/>version: v1"]
        V2["inventory-v2<br/>serviceId: inventory-service<br/>version: v2"]
        O["order-service<br/>consumer"]
        V1 -->|"register / heartbeat"| E
        V2 -->|"register / heartbeat"| E
        O -->|"fetch registry"| E
        O -->|"LoadBalancer chọn instance"| V1
        O -->|"LoadBalancer chọn instance"| V2
    end
    Browser["Host browser / terminal"] -->|"localhost:8761"| E
    Caller["Host client"] -->|"localhost:8082"| O
~~~

Cả hai provider có cùng serviceId để consumer coi chúng là các instance của một dịch vụ. Mỗi instance có instance ID riêng để registry phân biệt các tiến trình. Trường `APP_VERSION` là metadata hoặc giá trị trả về từ endpoint kiểm tra phiên bản; nó không tự tạo ra một serviceId khác.

Các container cùng nối vào một Docker bridge network. Docker Compose cung cấp DNS nội bộ theo tên service, vì vậy provider và consumer có thể tìm Eureka Server bằng hostname `eureka-server`. Bên trong container, `localhost` luôn trỏ về chính container hiện tại. Không cấu hình consumer gọi `localhost:8761` để tìm registry, vì địa chỉ đó sẽ trỏ về chính consumer.

Một cấu trúc thư mục minh họa:

~~~text
service-discovery-lab/
├── compose.yaml
├── eureka-server/
│   ├── Dockerfile
│   └── ứng dụng Eureka Server
├── inventory-v1/
│   ├── Dockerfile
│   └── mã nguồn phiên bản 1
├── inventory-v2/
│   ├── Dockerfile
│   └── mã nguồn phiên bản 2
└── order-service/
    ├── Dockerfile
    └── ứng dụng consumer
~~~

Mỗi Dockerfile cần đóng gói ứng dụng tương ứng thành image có thể chạy trong container. Hai thư mục inventory có thể là hai checkout hoặc hai build artifact của các revision khác nhau. Nếu chỉ dùng cùng một mã nguồn và đổi biến `APP_VERSION`, lab đang mô phỏng hai instance có nhãn phiên bản khác nhau, chưa chứng minh được hai binary release thực sự khác nhau.

## 3. Cấu hình Eureka Server

Eureka Server là ứng dụng Spring Boot có dependency `spring-cloud-starter-netflix-eureka-server`. Bật server bằng annotation:

~~~java
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

Cấu hình `application.yml`:

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

management:
  endpoints:
    web:
      exposure:
        include: health,info
~~~

Eureka Server không cần đăng ký chính nó vào registry của chính nó trong lab độc lập này. Hai thuộc tính `register-with-eureka` và `fetch-registry` được đặt thành `false` để thể hiện rõ vai trò registry đơn.

Dashboard mặc định có thể truy cập từ host qua `http://localhost:8761` nếu Compose publish cổng 8761. Endpoint Actuator health được dùng trong health check của Compose; bảo đảm image có công cụ `curl` nếu dùng đúng lệnh health check bên dưới.

## 4. Cấu hình provider để đăng ký đúng địa chỉ container

Hai phiên bản provider dùng chung cấu hình cơ bản:

~~~yaml
spring:
  application:
    name: inventory-service

server:
  port: 8080

eureka:
  client:
    service-url:
      defaultZone: ${EUREKA_SERVER_URL:http://localhost:8761/eureka/}
    healthcheck:
      enabled: true
  instance:
    prefer-ip-address: true
    instance-id: ${spring.application.name}:${HOSTNAME:local}:${random.value}

management:
  endpoints:
    web:
      exposure:
        include: health,info

app:
  version: ${APP_VERSION:local}
~~~

Trong Compose, biến môi trường sẽ ghi đè các giá trị mặc định:

- `SPRING_APPLICATION_NAME=inventory-service` làm hai provider đăng ký cùng serviceId.
- `EUREKA_CLIENT_SERVICEURL_DEFAULTZONE` trỏ đến `http://eureka-server:8761/eureka/`.
- `EUREKA_INSTANCE_PREFER_IP_ADDRESS=true` yêu cầu Eureka công bố địa chỉ IP mà container sử dụng trên network.
- `EUREKA_INSTANCE_INSTANCE_ID` cung cấp ID riêng cho từng container.
- `APP_VERSION` cho biết ứng dụng đang chạy build nào.

Địa chỉ mà Eureka công bố phải truy cập được từ consumer. Nếu provider đăng ký `localhost`, địa chỉ host-only hoặc hostname không phân giải được trong Docker network, registry vẫn có thể hiển thị instance nhưng request thực tế sẽ thất bại.

Không đặt `container_name` cố định cho các provider nếu dự định scale service. Mỗi container cần có danh tính riêng; instance ID bị trùng có thể khiến một registration ghi đè hoặc che khuất registration khác.

## 5. Khai báo toàn bộ lab trong Docker Compose

Tạo file `compose.yaml` ở thư mục gốc:

~~~yaml
name: spring-cloud-discovery-lab

services:
  eureka-server:
    build: ./eureka-server
    ports:
      - "8761:8761"
    environment:
      SPRING_APPLICATION_NAME: eureka-server
      SERVER_PORT: "8761"
      EUREKA_CLIENT_REGISTER_WITH_EUREKA: "false"
      EUREKA_CLIENT_FETCH_REGISTRY: "false"
      MANAGEMENT_ENDPOINTS_WEB_EXPOSURE_INCLUDE: health,info
    healthcheck:
      test:
        - CMD-SHELL
        - curl -fsS http://localhost:8761/actuator/health >/dev/null || exit 1
      interval: 10s
      timeout: 3s
      retries: 12
      start_period: 25s
    networks:
      - discovery

  inventory-v1:
    build: ./inventory-v1
    environment:
      SPRING_APPLICATION_NAME: inventory-service
      SERVER_PORT: "8080"
      APP_VERSION: v1
      EUREKA_CLIENT_SERVICEURL_DEFAULTZONE: http://eureka-server:8761/eureka/
      EUREKA_INSTANCE_PREFER_IP_ADDRESS: "true"
      EUREKA_INSTANCE_INSTANCE_ID: inventory-service-v1
    depends_on:
      eureka-server:
        condition: service_healthy
    networks:
      - discovery

  inventory-v2:
    build: ./inventory-v2
    environment:
      SPRING_APPLICATION_NAME: inventory-service
      SERVER_PORT: "8080"
      APP_VERSION: v2
      EUREKA_CLIENT_SERVICEURL_DEFAULTZONE: http://eureka-server:8761/eureka/
      EUREKA_INSTANCE_PREFER_IP_ADDRESS: "true"
      EUREKA_INSTANCE_INSTANCE_ID: inventory-service-v2
    depends_on:
      eureka-server:
        condition: service_healthy
    networks:
      - discovery

  order-service:
    build: ./order-service
    ports:
      - "8082:8080"
    environment:
      SPRING_APPLICATION_NAME: order-service
      SERVER_PORT: "8080"
      EUREKA_CLIENT_SERVICEURL_DEFAULTZONE: http://eureka-server:8761/eureka/
      EUREKA_INSTANCE_PREFER_IP_ADDRESS: "true"
    depends_on:
      eureka-server:
        condition: service_healthy
    networks:
      - discovery

networks:
  discovery:
    driver: bridge
~~~

Các điểm cần hiểu trong file Compose:

1. `build` chỉ định thư mục chứa Dockerfile của từng ứng dụng. Hai provider có thể được build từ hai revision khác nhau.
2. Chỉ publish cổng registry và consumer ra host trong ví dụ. Provider vẫn lắng nghe cổng 8080 bên trong Docker network; không cần chiếm hai cổng host giống nhau.
3. `eureka-server` là hostname nội bộ được Docker DNS phân giải. Consumer và provider dùng hostname này để gọi registry.
4. `depends_on: condition: service_healthy` chờ health check của Eureka Server thành công trước khi khởi động service phụ thuộc.
5. Mỗi provider có instance ID riêng trong ví dụ. Khi scale nhiều replica từ cùng một service, hãy bỏ ID tĩnh này và dùng ID sinh theo hostname hoặc giá trị duy nhất.
6. Health check dùng `curl`; image Eureka Server cần có `curl` và Actuator health endpoint được expose. Nếu image không có `curl`, thay bằng công cụ có sẵn trong image hoặc một health check phù hợp khác.

`depends_on` chỉ giải quyết thứ tự và điều kiện sẵn sàng của Eureka Server. Nó không bảo đảm provider đã đăng ký xong trước khi consumer nhận request. Consumer vẫn cần xử lý thời điểm registry chưa có instance, dùng timeout và retry có giới hạn.

Nếu muốn truy cập trực tiếp từng provider từ host để debug, có thể publish cổng host khác nhau, ví dụ `18081:8080` cho v1 và `18082:8080` cho v2. Đây chỉ là cổng debug; lời gọi service-to-service vẫn phải đi qua serviceId để kiểm tra discovery và load balancing.

## 6. Để consumer gọi theo serviceId

Consumer cũng cần đăng ký với Eureka để tra cứu registry. Cấu hình của `order-service` trong Compose đã cung cấp service URL. Trong Spring, khai báo một WebClient builder có load balancing:

~~~java
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
public class HttpClientConfiguration {

    @Bean
    @LoadBalanced
    WebClient.Builder loadBalancedWebClientBuilder() {
        return WebClient.builder();
    }
}
~~~

Consumer gọi đến serviceId:

~~~java
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.function.client.WebClient;

import reactor.core.publisher.Mono;

@Component
public class InventoryClient {

    private final WebClient webClient;

    public InventoryClient(
            @LoadBalanced WebClient.Builder builder) {
        this.webClient = builder.build();
    }

    public Mono<String> getInventoryVersion() {
        return webClient.get()
                .uri("http://inventory-service/api/version")
                .retrieve()
                .bodyToMono(String.class);
    }
}
~~~

Để gọi thử từ host qua order-service, expose một endpoint nhỏ chuyển tiếp lời gọi:

~~~java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/inventory")
public class InventoryController {

    private final InventoryClient inventoryClient;

    public InventoryController(InventoryClient inventoryClient) {
        this.inventoryClient = inventoryClient;
    }

    @GetMapping("/version")
    public Mono<String> version() {
        return inventoryClient.getInventoryVersion();
    }
}
~~~

Trong URI, `inventory-service` là tên logic. Spring Cloud LoadBalancer lấy các instance của serviceId đó, áp dụng chính sách chọn instance rồi gửi request đến host và port thực tế. Nếu dùng WebClient không có `@LoadBalanced`, hostname `inventory-service` có thể bị phân giải như hostname DNS thông thường thay vì được tra cứu qua Eureka.

Endpoint `/api/version` của provider nên trả về thông tin phiên bản để dễ quan sát, ví dụ:

~~~java
import java.util.Map;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class VersionController {

    @Value("${app.version:local}")
    private String version;

    @GetMapping("/api/version")
    public Map<String, String> version() {
        return Map.of(
                "service", "inventory-service",
                "version", version,
                "container", System.getenv().getOrDefault("HOSTNAME", "local"));
    }
}
~~~

Response của v1 có thể giống ví dụ sau:

~~~json
{
  "service": "inventory-service",
  "version": "v1",
  "container": "<container-id>"
}
~~~

Provider v2 trả về `version: v2` và instance ID riêng. Khi gửi nhiều request qua consumer, kết quả có thể lần lượt đến v1 và v2 theo chính sách LoadBalancer. Phân phối request không phải cam kết rằng mọi chuỗi request ngắn sẽ có số lượng v1/v2 bằng nhau; còn phụ thuộc danh sách instance, thời điểm cập nhật registry, cache và chính sách chọn.

## 7. Khởi động và kiểm tra môi trường

Chạy các lệnh sau tại thư mục có `compose.yaml`:

~~~bash
# Kiểm tra cấu hình Compose sau khi nội suy biến
docker compose config

# Build image và khởi động toàn bộ lab
docker compose up --build -d

# Xem trạng thái container
docker compose ps

# Theo dõi log của registry và provider
docker compose logs -f eureka-server inventory-v1 inventory-v2
~~~

Sau khi Eureka Server sẵn sàng:

1. Mở `http://localhost:8761` trên host.
2. Tìm phần danh sách application/instance trên dashboard.
3. Xác nhận có service `INVENTORY-SERVICE` với hai instance ID khác nhau.
4. Xác nhận `ORDER-SERVICE` đã đăng ký nếu consumer được cấu hình auto-registration.
5. Gọi endpoint consumer tại `http://localhost:8082/api/inventory/version`.
6. Gửi nhiều request đến endpoint consumer gọi inventory và quan sát trường `version` hoặc `instanceId` trong response/log.

Nếu chỉ thấy một instance, kiểm tra log của provider còn lại, serviceId, địa chỉ Eureka và instance ID. Nếu dashboard có hai instance nhưng request chỉ đi đến một phiên bản, kiểm tra chính sách LoadBalancer, cache và trạng thái health của các instance.

Có thể xem log của riêng một service:

~~~bash
docker compose logs --tail=100 inventory-v1
docker compose logs --tail=100 inventory-v2
docker compose logs --tail=100 order-service
~~~

Khi kết thúc lab:

~~~bash
docker compose down
~~~

Lệnh này dừng và xóa container cùng network do Compose tạo. Nếu có thêm volume chứa dữ liệu thực hành, chỉ xóa volume khi đã xác định không còn dữ liệu cần giữ.

## 8. Scale instance và triển khai phiên bản

Có hai thao tác khác nhau cần phân biệt:

- **Scale cùng một phiên bản:** tăng số container chạy cùng image, ví dụ tăng ba instance v1. Các container phải đăng ký cùng serviceId nhưng có instance ID khác nhau.
- **Chạy nhiều phiên bản:** triển khai hai image hoặc hai revision khác nhau, ví dụ v1 và v2, nhưng vẫn đăng ký cùng serviceId nếu muốn LoadBalancer phân phối request giữa chúng.

Có thể scale một service trong Compose bằng:

~~~bash
docker compose up -d --scale inventory-v1=3
~~~

Không dùng `container_name` cố định và không bind cùng một host port cho mọi replica. Mỗi container dùng cùng cổng nội bộ 8080 nhưng có IP riêng trên bridge network. Khi scale, không dùng instance ID tĩnh như ví dụ v1/v2; hãy cấu hình ID duy nhất theo hostname hoặc một định danh duy nhất của container. Có thể dùng cấu hình fallback `instance-id: ${spring.application.name}:${HOSTNAME:local}:${random.value}` trong `application.yml` và bỏ biến môi trường ghi đè ID tĩnh.

Nếu muốn v1 và v2 là hai bản phát hành thực sự, hãy build hai image từ hai revision tương ứng rồi cấu hình hai service Compose trỏ đến đúng image tag. Không nên dùng cùng một image và chỉ đổi nhãn `APP_VERSION` rồi kết luận đã kiểm thử nâng cấp phiên bản. Trong triển khai rolling update, cần kiểm tra khả năng tương thích API và dữ liệu giữa consumer với cả phiên bản cũ lẫn mới.

Một serviceId có nhiều phiên bản cùng lúc cũng có nghĩa consumer có thể gửi request đến bất kỳ instance khỏe mạnh nào trong danh sách. Nếu API giữa v1 và v2 không tương thích, cần chiến lược routing theo version, canary hoặc blue/green riêng; service discovery cơ bản không tự bảo đảm tương thích giao thức.

## 9. Sự cố thường gặp khi chạy trong Docker

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Provider không kết nối được Eureka | Dùng `localhost:8761` bên trong container | Dùng `http://eureka-server:8761/eureka/` |
| Eureka không hiển thị provider | Sai serviceId, sai URL registry hoặc client chưa khởi động xong | Kiểm tra biến môi trường và log registration |
| Dashboard có instance nhưng HTTP timeout | Provider công bố IP/hostname không thể truy cập từ consumer | Kiểm tra network chung và địa chỉ instance đã đăng ký |
| Hai container ghi đè nhau trong registry | Instance ID trùng | Tạo ID duy nhất theo hostname/container |
| Consumer gọi được v1 nhưng không thấy v2 | v2 chưa đăng ký, health check thất bại hoặc khác serviceId | So sánh cấu hình và trạng thái hai provider |
| Compose báo health check lỗi | Image thiếu `curl`, Actuator chưa expose health hoặc app chưa sẵn sàng | Cài công cụ probe phù hợp và kiểm tra log registry |
| Consumer khởi động trước khi có instance | Registry healthy nhưng provider chưa đăng ký | Retry có giới hạn, xử lý danh sách rỗng và readiness |
| Scale bị lỗi bind port | Nhiều replica cùng publish một host port cố định | Chỉ dùng cổng nội bộ hoặc cấu hình host port riêng khi debug |

Khi điều tra, đi theo thứ tự từ ngoài vào trong: container có đang chạy không, hai container có cùng network không, DNS nội bộ có phân giải được không, provider có đăng ký đúng serviceId không, registry có trả instance không, và consumer có kết nối được tới địa chỉ instance không. Trình tự này giúp xác định lỗi nằm ở Docker, registry hay HTTP client.

## 10. Health check, bảo mật và giới hạn của lab

Health check của Docker Compose kiểm tra trạng thái tiến trình hoặc endpoint mà ta cấu hình. Health check của Eureka và trạng thái instance trong registry phục vụ việc chọn instance. Hai cơ chế liên quan nhưng không thay thế nhau. Một container có thể healthy theo Docker nhưng ứng dụng chưa đăng ký với Eureka; một instance có thể còn trong registry trong một khoảng thời gian sau khi tiến trình đã chết.

Trong môi trường thật, cần:

- Thiết kế health/readiness endpoint phản ánh đúng khả năng xử lý request và dependency quan trọng.
- Thiết lập timeout, retry có giới hạn và circuit breaker ở consumer khi phù hợp.
- Bảo vệ registry bằng network policy, xác thực, ACL và TLS theo mô hình triển khai.
- Không công khai dashboard hoặc API quản trị registry ra Internet.
- Không đưa mật khẩu, token hoặc secret vào image hay commit trong Compose file; dùng secret store hoặc cơ chế quản lý secret của môi trường.
- Theo dõi số instance, registration/deregistration, heartbeat, health status và lỗi kết nối giữa service.
- Thiết kế registry có tính sẵn sàng cao và đánh giá hành vi khi registry tạm thời mất kết nối.

Lab trên chạy một Eureka Server nên registry là điểm lỗi đơn. Registry mẫu cũng không cấu hình xác thực và chỉ nên chạy trong môi trường phát triển cục bộ. Với Consul, cần thay service image/cấu hình registry bằng Consul agent/server và cấu hình health check tương ứng; nguyên tắc Docker DNS, network chung, serviceId và địa chỉ instance có thể truy cập vẫn giữ nguyên.

## 11. Checklist hoàn tất

Trước khi coi môi trường đã chạy đúng, xác nhận từng điều sau:

1. Spring Boot và Spring Cloud release train tương thích; các module dùng chung BOM.
2. Eureka Server khởi động và health check thành công.
3. Provider v1 và v2 đăng ký cùng serviceId `inventory-service`.
4. Mỗi provider có instance ID riêng và địa chỉ có thể truy cập từ consumer.
5. Consumer đăng ký thành công và tra cứu được danh sách instance.
6. Consumer gọi qua `@LoadBalanced` bằng serviceId, không dùng IP/container name cố định.
7. Có thể quan sát response đến từ các phiên bản khác nhau.
8. Khi dừng một provider, registry và consumer dần phản ánh thay đổi theo chu kỳ heartbeat, health check và cache.
9. Khi khởi động lại provider, instance mới đăng ký lại mà không tạo bản ghi trùng kéo dài.

Khi các bước này hoạt động, luồng thực hành đã hoàn chỉnh: Docker Compose tạo network và container; provider đăng ký serviceId cùng instance metadata vào Eureka; consumer tra cứu serviceId; Spring Cloud LoadBalancer chọn instance; HTTP client gửi request qua địa chỉ mạng của instance được chọn.

