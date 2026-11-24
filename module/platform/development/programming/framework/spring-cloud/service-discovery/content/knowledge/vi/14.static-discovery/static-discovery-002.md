# Khai báo nhiều instance bằng thuộc tính simple.instances

Không phải ứng dụng nào cũng cần một registry server như Eureka hoặc Consul. Với môi trường local, integration test hoặc một hệ thống nhỏ có danh sách endpoint ổn định, Spring Cloud Commons cung cấp `SimpleDiscoveryClient`. Client này đọc danh sách service instance trực tiếp từ cấu hình của ứng dụng thông qua thuộc tính `spring.cloud.discovery.client.simple.instances`.

Bạn có thể khai báo nhiều địa chỉ cho cùng một service ID, đồng thời khai báo nhiều service khác nhau trong một file YAML. Ứng dụng vẫn dùng API `DiscoveryClient` và có thể kết hợp Spring Cloud LoadBalancer để gọi service bằng tên logic. Bài học này hướng dẫn cấu trúc `simple.instances`, cách ánh xạ từng phần tử thành `ServiceInstance`, cách sử dụng và những giới hạn của discovery tĩnh.

## 1. SimpleDiscoveryClient hoạt động như thế nào?

`SimpleDiscoveryClient` là một implementation của `DiscoveryClient` thuộc Spring Cloud Commons. Thay vì gửi truy vấn tới một registry server, nó đọc danh sách instance từ cấu hình đã được Spring Boot bind vào `SimpleDiscoveryProperties`.

Hai thao tác chính:

- `getServices()` trả về các service ID được khai báo trong map `instances`.
- `getInstances(serviceId)` trả về danh sách instance tương ứng với service ID đó. Nếu service ID không tồn tại, danh sách trả về rỗng.

```mermaid
flowchart TD
    YAML[application.yml]
    PROP[SimpleDiscoveryProperties]
    CLIENT[SimpleDiscoveryClient]
    API[DiscoveryClient]
    LB[Spring Cloud LoadBalancer]
    APP[Consumer application]

    YAML -->|Bind simple.instances| PROP
    PROP --> CLIENT
    APP -->|getInstances(serviceId)| API
    API --> CLIENT
    CLIENT -->|List ServiceInstance| API
    API --> APP
    APP -->|Load-balanced request| LB
```

Spring Cloud Commons tự cấu hình `SimpleDiscoveryClient` khi classpath không có `DiscoveryClient` được hỗ trợ bởi một service registry thực sự. Nếu ứng dụng có starter Eureka hoặc Consul, implementation tương ứng sẽ được sử dụng theo cấu hình discovery của dự án; không nên mặc định rằng `simple.instances` sẽ thay thế registry server chỉ vì bạn đã khai báo các giá trị này.

`SimpleDiscoveryClient` không khởi động service được khai báo. Nó chỉ cung cấp thông tin địa chỉ để consumer tìm và gọi instance đã chạy ở nơi khác.

## 2. Cấu trúc của simple.instances

Đường dẫn thuộc tính đầy đủ:

```text
spring.cloud.discovery.client.simple.instances
```

Đây là một map:

```text
service ID -> danh sách instance
```

Mỗi phần tử danh sách đại diện cho một service instance. Cách khai báo bằng indexed property có dạng:

```text
spring.cloud.discovery.client.simple.instances.<service-id>[<index>].uri=<instance-uri>
```

Trong đó:

- `<service-id>` là tên logic của service mà consumer sẽ truy vấn, ví dụ `inventory-service`.
- `<index>` là vị trí của instance trong danh sách, bắt đầu từ `0`.
- `uri` là URI của instance, bao gồm scheme, hostname hoặc IP và port.

Ví dụ khai báo hai instance cho `inventory-service`:

```properties
spring.cloud.discovery.client.simple.instances.inventory-service[0].uri=http://inventory-a:8081
spring.cloud.discovery.client.simple.instances.inventory-service[1].uri=http://inventory-b:8081
```

Hai dòng trên tạo một service ID `inventory-service` với hai địa chỉ. Chỉ số `[0]` và `[1]` là chỉ số phần tử trong danh sách, không phải port hoặc instance ID.

## 3. Khai báo nhiều instance trong application.yml

Trong YAML, cấu trúc danh sách thường dễ đọc hơn indexed property. Ví dụ consumer cần gọi hai service, mỗi service có nhiều instance:

```yaml
spring:
  application:
    name: order-consumer
  cloud:
    discovery:
      client:
        simple:
          instances:
            inventory-service:
              - uri: http://inventory-a:8081
              - uri: http://inventory-b:8081
              - uri: http://inventory-c:8081
            payment-service:
              - uri: https://payment-a:8443
              - uri: https://payment-b:8443
```

Kết quả cấu hình:

| Service ID | Số instance | URI |
| --- | ---: | --- |
| `inventory-service` | 3 | `http://inventory-a:8081`, `http://inventory-b:8081`, `http://inventory-c:8081` |
| `payment-service` | 2 | `https://payment-a:8443`, `https://payment-b:8443` |

Các instance thuộc cùng một service ID được gom vào cùng danh sách. Consumer gọi `getInstances("inventory-service")` sẽ nhận ba instance; gọi `getInstances("payment-service")` sẽ nhận hai instance.

### 3.1. Ý nghĩa của URI

Spring Cloud phân tích URI để lấy scheme, host và port của instance:

| URI | Scheme | Host | Port | Secure |
| --- | --- | --- | ---: | --- |
| `http://inventory-a:8081` | `http` | `inventory-a` | 8081 | `false` |
| `https://payment-a:8443` | `https` | `payment-a` | 8443 | `true` |

URI có scheme `https` sẽ đánh dấu instance dùng kết nối bảo mật. Hãy khai báo đúng scheme và port thực tế mà service đang lắng nghe. Không dùng URL của giao diện web hoặc API Gateway nếu consumer cần gọi trực tiếp từng instance.

### 3.2. Khai báo metadata cho từng instance

Mỗi instance có thể mang metadata dạng key/value. Metadata hữu ích khi LoadBalancer hoặc logic ứng dụng cần phân biệt vùng triển khai, phiên bản hay nhóm xử lý:

```yaml
spring:
  cloud:
    discovery:
      client:
        simple:
          instances:
            inventory-service:
              - uri: http://inventory-a:8081
                metadata:
                  zone: zone-a
                  version: v1
              - uri: http://inventory-b:8081
                metadata:
                  zone: zone-b
                  version: v2
```

Khi đọc qua `ServiceInstance`, metadata có thể được truy cập bằng `instance.getMetadata()`. Metadata chỉ là thông tin mô tả; việc lọc theo `zone`, `version` hoặc key khác cần có supplier hay logic LoadBalancer tương ứng. Chỉ khai báo metadata không tự thay đổi thuật toán chọn instance.

## 4. Thêm dependency cần thiết

`SimpleDiscoveryClient` thuộc Spring Cloud Commons. Nếu ứng dụng cần gọi service bằng logical name và để Spring Cloud chọn địa chỉ instance, hãy thêm Spring Cloud LoadBalancer:

```xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-loadbalancer</artifactId>
</dependency>
```

Quản lý phiên bản Spring Cloud bằng BOM tương thích với phiên bản Spring Boot của dự án. Không tự gán version độc lập cho starter nếu dự án đã dùng dependency management.

Nếu chỉ muốn gọi `DiscoveryClient.getInstances()` để xem danh sách địa chỉ, không nhất thiết phải tạo HTTP client load-balanced. Nếu muốn dùng `@LoadBalanced RestTemplate`, `RestClient` hoặc `WebClient`, cần có Spring Cloud LoadBalancer trên classpath và cấu hình client tương ứng.

## 5. Sử dụng DiscoveryClient để đọc danh sách

Ví dụ inject `DiscoveryClient` và lấy các instance của `inventory-service`:

```java
import java.util.List;

import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.discovery.DiscoveryClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class InventoryDiscoveryController {

    private final DiscoveryClient discoveryClient;

    public InventoryDiscoveryController(DiscoveryClient discoveryClient) {
        this.discoveryClient = discoveryClient;
    }

    @GetMapping("/discovery/inventory")
    public List<String> getInventoryInstances() {
        return discoveryClient.getInstances("inventory-service")
                .stream()
                .map(instance -> instance.getUri().toString())
                .toList();
    }
}
```

Với Java trước phiên bản 16, có thể thay `.toList()` bằng `.collect(Collectors.toList())` và import `java.util.stream.Collectors`.

Bạn cũng có thể xem danh sách service ID:

```java
List<String> serviceIds = discoveryClient.getServices();
```

Với ví dụ YAML phía trên, danh sách có các ID `inventory-service` và `payment-service`. Nếu truy vấn một service ID chưa khai báo, `getInstances()` trả về danh sách rỗng; consumer cần xử lý trường hợp không có instance.

## 6. Gọi nhiều instance bằng Spring Cloud LoadBalancer

Khi muốn ứng dụng gọi service bằng tên logic thay vì tự chọn host/port, tạo một HTTP client được đánh dấu `@LoadBalanced`.

Ví dụ với `RestTemplate`:

```java
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestTemplate;

@Configuration
public class HttpClientConfiguration {

    @Bean
    @LoadBalanced
    RestTemplate restTemplate() {
        return new RestTemplate();
    }
}
```

Consumer có thể gọi:

```java
String result = restTemplate.getForObject(
        "http://inventory-service/api/items",
        String.class
);
```

Spring Cloud LoadBalancer dùng `inventory-service` làm service ID, yêu cầu danh sách instance từ `DiscoveryClient`, chọn một instance rồi chuyển logical URI thành địa chỉ thật, ví dụ `http://inventory-b:8081/api/items`.

LoadBalancer mặc định thường dùng round-robin. Khi có nhiều instance, các request liên tiếp được phân phối qua danh sách ứng viên theo thuật toán đang cấu hình. Danh sách khai báo trong `simple.instances` chỉ cung cấp các ứng viên; nó không tự thực hiện cân bằng tải nếu request dùng HTTP client thông thường không tích hợp LoadBalancer.

## 7. Kiểm tra cấu hình đã được bind

Có thể kiểm tra trực tiếp bằng `DiscoveryClient` hoặc đặt breakpoint trong ứng dụng. Ví dụ một đoạn kiểm tra khi khởi động:

```java
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.cloud.client.discovery.DiscoveryClient;

@Configuration
public class DiscoveryDiagnostics {

    @Bean
    ApplicationRunner printDiscoveredServices(DiscoveryClient discoveryClient) {
        return args -> {
            System.out.println("Services: " + discoveryClient.getServices());

            discoveryClient.getInstances("inventory-service")
                    .forEach(instance -> System.out.printf(
                            "service=%s uri=%s metadata=%s%n",
                            instance.getServiceId(),
                            instance.getUri(),
                            instance.getMetadata()
                    ));
        };
    }
}
```

Kết quả mong đợi là ba instance của `inventory-service` với URI và metadata tương ứng. Nếu danh sách rỗng, kiểm tra tên service ID, cấu trúc YAML và điều kiện để `SimpleDiscoveryClient` được auto-configure.

Không nên giữ log liệt kê toàn bộ endpoint trong production nếu thông tin host nội bộ không dành cho người đọc log thông thường. Đoạn runner trên chỉ phù hợp để minh họa hoặc chẩn đoán trong môi trường phát triển.

## 8. Kiểm tra sức khỏe của instance tĩnh

`SimpleDiscoveryClient` đọc địa chỉ từ cấu hình. Nó không gửi heartbeat tới registry, không có health state do registry quản lý và không tự xóa một instance khi tiến trình đích dừng. Nếu khai báo ba URI, discovery vẫn có thể trả ba URI dù một endpoint không còn hoạt động.

Với số lượng instance nhỏ, Spring Cloud LoadBalancer có `HealthCheckServiceInstanceListSupplier` để định kỳ kiểm tra các địa chỉ do supplier phía dưới cung cấp. Ví dụ cấu hình builder cho reactive stack:

```java
import org.springframework.cloud.loadbalancer.core.ServiceInstanceListSupplier;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;

public class InventoryLoadBalancerConfiguration {

    @Bean
    ServiceInstanceListSupplier inventoryServiceInstanceListSupplier(
            ConfigurableApplicationContext context) {
        return ServiceInstanceListSupplier.builder()
                .withDiscoveryClient()
                .withHealthChecks()
                .build(context);
    }
}
```

Gắn cấu hình với service ID cần kiểm tra:

```java
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cloud.loadbalancer.annotation.LoadBalancerClient;

@SpringBootApplication
@LoadBalancerClient(
        name = "inventory-service",
        configuration = InventoryLoadBalancerConfiguration.class
)
public class InventoryConsumerApplication {
    // main method
}
```

Giữ `InventoryLoadBalancerConfiguration` ngoài phạm vi component scan hoặc không đánh dấu lớp đó bằng `@Configuration`, để bean chỉ được áp dụng trong LoadBalancer context tương ứng. Với stack blocking, dùng phương thức `withBlockingHealthChecks()` theo phiên bản Spring Cloud LoadBalancer tương ứng.

Đường dẫn health check mặc định thường là `/actuator/health`. Có thể đặt path riêng cho một service:

```yaml
spring:
  cloud:
    loadbalancer:
      health-check:
        path:
          inventory-service: /actuator/health/readiness
```

Chỉ dùng `/actuator/health/readiness` khi ứng dụng đích thực sự expose readiness endpoint. Health check của LoadBalancer là một lớp kiểm tra phía consumer; nó không biến danh sách tĩnh thành registry động và không thay thế health check của Eureka hoặc Consul khi dùng registry thật.

## 9. Phân biệt simple.instances với service registry

| Khả năng | `SimpleDiscoveryClient` | Eureka / Consul |
| --- | --- | --- |
| Nguồn instance | Cấu hình trong application properties/YAML. | Registry server lưu registration từ các service/agent. |
| Thêm instance | Sửa cấu hình. | Instance đăng ký qua client/agent hoặc API. |
| Phát hiện instance dừng | Không tự phát hiện bằng registry; có thể bổ sung health check ở LoadBalancer. | Có heartbeat, lease hoặc health check tùy registry. |
| Đồng bộ danh sách | Theo cấu hình đã bind trong ứng dụng. | Theo cơ chế cập nhật/cache của registry client. |
| Hạ tầng cần có | Không cần registry server. | Cần registry server hoặc cụm registry hoạt động. |
| Trường hợp phù hợp | Local, test, mock endpoint, hệ thống nhỏ và ổn định. | Microservice động, autoscaling, nhiều môi trường và yêu cầu vận hành phân tán. |

Điểm quan trọng: `simple.instances` là một danh sách cấu hình cho discovery, không phải cơ chế đăng ký động. Khi thêm replica mới, ứng dụng consumer không tự biết địa chỉ đó cho tới khi cấu hình được cập nhật và nạp lại.

## 10. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| `getInstances("inventory-service")` trả danh sách rỗng | Sai service ID, sai cấp YAML hoặc list index không bind đúng | Đối chiếu key dưới `simple.instances`, dùng danh sách YAML hoặc index bắt đầu từ `[0]`. |
| Có khai báo `simple.instances` nhưng client không trả đúng danh sách | Eureka/Consul starter đã cung cấp registry-backed DiscoveryClient | Kiểm tra dependency tree và implementation DiscoveryClient đang được dùng. |
| Gọi `http://inventory-service/...` bị lỗi DNS | HTTP client không có `@LoadBalanced` hoặc thiếu LoadBalancer starter | Thêm `spring-cloud-starter-loadbalancer` và tạo bean client có `@LoadBalanced`. |
| Một URI hoạt động trên host nhưng không hoạt động trong Docker | Hostname chỉ phân giải từ host hoặc dùng `localhost` không đúng network namespace | Dùng DNS/service name có thể truy cập từ container consumer. |
| HTTPS instance bị gọi bằng HTTP | URI khai báo sai scheme hoặc thiếu `https://` | Dùng đúng scheme và kiểm tra chứng thư/TLS của endpoint. |
| Instance đã dừng nhưng vẫn được discovery trả về | Danh sách tĩnh không có registry health state | Bổ sung LoadBalancer health check hoặc chuyển sang registry có health check phù hợp. |
| Thêm instance mới nhưng consumer không nhìn thấy | File cấu hình chưa được cập nhật/nạp lại hoặc consumer đang dùng nguồn cấu hình khác | Kiểm tra profile, property source và khởi động lại/refresh theo cơ chế cấu hình của ứng dụng. |

## 11. Checklist khi khai báo nhiều instance

1. Chọn service ID rõ ràng và dùng đúng cùng tên ở consumer.
2. Khai báo từng instance dưới một phần tử riêng của danh sách `simple.instances`.
3. Dùng URI đầy đủ với scheme, hostname/IP và port chính xác.
4. Đảm bảo hostname có thể phân giải từ nơi chạy consumer, không chỉ từ máy phát triển.
5. Khai báo metadata nếu có logic LoadBalancer sử dụng metadata đó.
6. Thêm Spring Cloud LoadBalancer nếu muốn gọi service bằng logical name.
7. Bổ sung health check phía LoadBalancer nếu cần phát hiện endpoint chết trong danh sách tĩnh.
8. Xác minh danh sách thực tế qua `DiscoveryClient.getInstances()` trước khi kiểm tra lời gọi HTTP.
9. Có quy trình cập nhật cấu hình khi địa chỉ hoặc số lượng instance thay đổi.

## 12. Ghi nhớ

- `spring.cloud.discovery.client.simple.instances` là map từ service ID tới danh sách instance.
- Chỉ số phần tử bắt đầu từ `0`; mỗi instance thường được khai báo bằng thuộc tính `uri`.
- Có thể khai báo nhiều service và nhiều instance trong cùng `application.yml`.
- URI `https` tạo instance dùng kết nối bảo mật; host và port phải truy cập được từ consumer.
- `SimpleDiscoveryClient` được dùng khi không có registry-backed `DiscoveryClient` phù hợp trên classpath.
- `DiscoveryClient` cung cấp danh sách; Spring Cloud LoadBalancer mới chọn instance cho lời gọi dùng logical service name.
- Danh sách tĩnh không tự cập nhật theo vòng đời service và không có health state từ registry; cân nhắc health check hoặc registry động khi cần.

## Tài liệu tham khảo

- [Spring Cloud Commons: SimpleDiscoveryClient](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html)
- [Spring Cloud LoadBalancer: Instance Health-Check](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html)
