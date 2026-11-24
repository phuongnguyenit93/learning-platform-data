# Dùng khám phá tĩnh cho kiểm thử và hệ thống quy mô nhỏ

Không phải ứng dụng nào cũng cần một registry động như Eureka hoặc Consul. Với bài kiểm thử, demo, môi trường local hoặc hệ thống nhỏ có một vài endpoint ổn định, có thể khai báo sẵn địa chỉ các service trong cấu hình. Spring Cloud Commons cung cấp `SimpleDiscoveryClient` để biến danh sách URI tĩnh thành các `ServiceInstance` mà code vẫn tra cứu qua abstraction `DiscoveryClient` quen thuộc.

Khám phá tĩnh giúp giảm số thành phần phải vận hành và làm môi trường kiểm thử dễ tái lập. Đổi lại, danh sách instance không tự cập nhật khi một process khởi động, dừng, đổi IP hoặc đổi cổng. Cần hiểu rõ ranh giới này để không dùng static discovery như một registry có health check và khả năng tự phục hồi.

## 1. Static discovery là gì?

Service discovery tĩnh là cách khai báo trước các endpoint của service trong file cấu hình hoặc property source. Consumer tra cứu theo service ID, còn ứng dụng dùng danh sách đã khai báo để tìm endpoint.

Ví dụ một ứng dụng `order-service` cần gọi hai instance của `inventory-service` và một instance `payment-service`:

```text
order-service
  ├── inventory-service
  │     ├── http://localhost:8081
  │     └── http://localhost:8082
  └── payment-service
        └── http://localhost:8091
```

Với `SimpleDiscoveryClient`, danh sách này được bind từ cấu hình Spring Boot. Không cần khởi chạy Eureka Server hoặc Consul Agent chỉ để consumer biết các URI trên.

Static discovery phù hợp khi:

- Kiểm thử tích hợp cần endpoint giả lập hoặc service test có địa chỉ cố định.
- Phát triển local với một vài service chạy trên các cổng khác nhau.
- Demo hoặc prototype có số instance ít và vòng đời tương đối ổn định.
- Công cụ nội bộ hoặc hệ thống nhỏ có endpoint do người vận hành quản lý thủ công.

Không phù hợp khi instance thường xuyên scale up/down, được triển khai trên nhiều node có IP thay đổi, cần health check tự động hoặc cần cập nhật registry mà không khởi động lại consumer.

## 2. SimpleDiscoveryClient trong Spring Cloud Commons

`SimpleDiscoveryClient` là implementation của `DiscoveryClient` lấy thông tin service và instance từ properties. Theo Spring Cloud Commons, implementation này được dùng khi classpath không có `DiscoveryClient` dựa trên service registry như Eureka, Consul hoặc ZooKeeper.

Điều đó có hai hệ quả quan trọng:

1. Chỉ thêm cấu hình `spring.cloud.discovery.client.simple.instances` chưa chắc làm Simple client được chọn nếu ứng dụng vẫn có một registry-backed DiscoveryClient trên runtime classpath.
2. Spring profile chỉ chọn file cấu hình; profile không tự gỡ dependency JAR khỏi classpath. Nếu muốn test dùng Simple client thay cho Eureka/Consul, cần thiết kế dependency/runtime classpath phù hợp hoặc dùng một ứng dụng/module test riêng.

Trong Spring Cloud hiện đại, `@EnableDiscoveryClient` không còn bắt buộc chỉ để bật discovery. Việc có implementation tương ứng trên classpath và auto-configuration thường đã đủ. Với static discovery, không cần thêm annotation riêng để đăng ký các endpoint tĩnh.

Spring Cloud có API blocking `DiscoveryClient` và API reactive `ReactiveDiscoveryClient`. Simple discovery có implementation cho cả hai mô hình để code ứng dụng có thể dùng abstraction phù hợp với stack.

## 3. Khai báo instance bằng YAML

Giả sử consumer cần gọi hai instance của `inventory-service` và một instance của `payment-service`. Đặt cấu hình trong `application.yml` hoặc file profile tương ứng:

```yaml
spring:
  application:
    name: order-service
  cloud:
    discovery:
      client:
        simple:
          instances:
            inventory-service:
              - uri: http://localhost:8081
              - uri: http://localhost:8082
            payment-service:
              - uri: http://localhost:8091
```

Cấu trúc có ý nghĩa:

| Phần cấu hình | Ý nghĩa |
|---|---|
| `spring.cloud.discovery.client.simple.instances` | Prefix chứa map các service ID và danh sách instance |
| `inventory-service` | Service ID mà consumer dùng để tra cứu |
| `[0]`, `[1]` (ngầm định qua danh sách YAML) | Chỉ số instance, bắt đầu từ 0 trong dạng property |
| `uri` | URI đầy đủ của instance, gồm scheme, host và port |

URI phải là địa chỉ mà chính consumer có thể truy cập. Ví dụ trên dùng `localhost` vì giả định các service chạy trên cùng máy. Nếu chạy trong container hoặc máy khác, thay bằng DNS name/IP có thể định tuyến từ môi trường consumer.

### 3.1. Dạng properties

Cùng danh sách trên có thể viết trong `application.properties`:

```properties
spring.application.name=order-service

spring.cloud.discovery.client.simple.instances.inventory-service[0].uri=http://localhost:8081
spring.cloud.discovery.client.simple.instances.inventory-service[1].uri=http://localhost:8082
spring.cloud.discovery.client.simple.instances.payment-service[0].uri=http://localhost:8091
```

Chỉ số trong ngoặc vuông bắt đầu từ `0`. Service ID là phần nằm giữa `instances.` và chỉ số; URI là endpoint thực tế.

### 3.2. URI HTTP và HTTPS

URI mang scheme, hostname và port. Có thể khai báo HTTPS nếu endpoint có TLS:

```yaml
spring:
  cloud:
    discovery:
      client:
        simple:
          instances:
            secure-catalog:
              - uri: https://catalog-a.internal:8443
              - uri: https://catalog-b.internal:8443
```

Không nhúng username, password, API key hoặc token vào URI được commit vào repository. Cấu hình endpoint và thông tin xác thực nên được quản lý riêng bằng secret hoặc biến môi trường.

## 4. Tách danh sách endpoint theo profile

Static discovery thường hữu ích nhất khi mỗi môi trường có danh sách endpoint khác nhau. Có thể giữ cấu hình chung trong `application.yml`, sau đó khai báo endpoint local trong `application-local.yml` và endpoint test trong `application-test.yml`.

`application.yml`:

```yaml
spring:
  application:
    name: order-service
```

`application-local.yml`:

```yaml
spring:
  cloud:
    discovery:
      client:
        simple:
          instances:
            inventory-service:
              - uri: http://localhost:8081
              - uri: http://localhost:8082
            payment-service:
              - uri: http://localhost:8091
```

`application-test.yml`:

```yaml
spring:
  cloud:
    discovery:
      client:
        simple:
          instances:
            inventory-service:
              - uri: http://localhost:18081
            payment-service:
              - uri: http://localhost:18091
```

Kích hoạt profile từ command line:

```bash
./mvnw spring-boot:run -Dspring-boot.run.profiles=local
```

Hoặc chạy JAR:

```bash
java -jar target/order-service.jar --spring.profiles.active=test
```

Không đặt `spring.profiles.active` trong chính file `application-local.yml` hoặc `application-test.yml`; profile active cần được chọn từ tài liệu cấu hình không gắn profile, biến môi trường hoặc tham số chạy.

**Lưu ý về classpath:** nếu `order-service` vẫn có Eureka/Consul starter trong runtime classpath, việc chuyển sang profile `test` không tự khiến Simple client được chọn. Điều kiện chọn SimpleDiscoveryClient dựa trên việc có registry-backed DiscoveryClient trên classpath. Hãy xác định dependency thực tế của test runtime; có thể tách một module consumer-test hoặc cấu hình build để loại registry starter khi cần kiểm thử bằng static discovery.

## 5. Tra cứu instance bằng DiscoveryClient

Code ứng dụng vẫn dùng abstraction chung, không cần biết URI đến từ YAML hay registry động:

```java
import java.util.List;

import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.discovery.DiscoveryClient;
import org.springframework.stereotype.Component;

@Component
class InventoryLocator {

    private final DiscoveryClient discoveryClient;

    InventoryLocator(DiscoveryClient discoveryClient) {
        this.discoveryClient = discoveryClient;
    }

    List<ServiceInstance> findInventoryInstances() {
        return discoveryClient.getInstances("inventory-service");
    }

    List<String> availableServices() {
        return discoveryClient.getServices();
    }
}
```

`getInstances("inventory-service")` trả về các `ServiceInstance` được khai báo cho đúng service ID. `getServices()` trả về danh sách service ID có trong cấu hình Simple client. Nếu tên service không khớp, kết quả `getInstances` là danh sách rỗng.

Có thể duyệt endpoint để kiểm tra cấu hình:

```java
List<ServiceInstance> instances =
        discoveryClient.getInstances("inventory-service");

for (ServiceInstance instance : instances) {
    System.out.printf(
        "service=%s host=%s port=%d uri=%s secure=%s%n",
        instance.getServiceId(),
        instance.getHost(),
        instance.getPort(),
        instance.getUri(),
        instance.isSecure());
}
```

Đây là cách chẩn đoán danh sách endpoint. Trong ứng dụng thực tế, tránh tự chọn `instances.get(0)` cho mọi request vì như vậy sẽ bỏ qua các instance còn lại và không có chính sách cân bằng tải.

## 6. Kết hợp với Spring Cloud LoadBalancer

`SimpleDiscoveryClient` chỉ cung cấp danh sách instance. Nó không tự chọn instance cho từng HTTP request. Nếu muốn gọi bằng service ID như `http://inventory-service`, cần một HTTP client tích hợp Spring Cloud LoadBalancer.

Thêm starter LoadBalancer:

```xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-loadbalancer</artifactId>
</dependency>
```

Không khai báo version riêng khi Spring Cloud BOM đã quản lý dependency.

Với Spring `RestClient`, khai báo builder có `@LoadBalanced`:

```java
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;

@Configuration
class HttpClientConfiguration {

    @Bean
    @LoadBalanced
    RestClient.Builder loadBalancedRestClientBuilder() {
        return RestClient.builder();
    }
}
```

Inject builder để gọi service bằng logical service ID:

```java
import org.springframework.stereotype.Service;
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.web.client.RestClient;

@Service
class InventoryClient {

    private final RestClient restClient;

    InventoryClient(@LoadBalanced RestClient.Builder loadBalancedRestClientBuilder) {
        this.restClient = loadBalancedRestClientBuilder.build();
    }

    String getProducts() {
        return restClient.get()
            .uri("http://inventory-service/api/products")
            .retrieve()
            .body(String.class);
    }
}
```

LoadBalancer lấy danh sách `ServiceInstance` từ DiscoveryClient và chọn một endpoint để thay thế logical host `inventory-service` bằng địa chỉ vật lý. URI dùng trong lời gọi phải là service ID, không phải hostname của một instance cụ thể.

Nếu không có Spring Cloud LoadBalancer, chuỗi `inventory-service` không tự phân giải thành địa chỉ từ cấu hình Simple. Có thể gọi trực tiếp URI vật lý, nhưng khi đó ứng dụng tự quản lý việc chọn endpoint và không tận dụng service ID abstraction.

## 7. Kiểm thử với endpoint giả lập

Static discovery hữu ích khi muốn kiểm thử consumer mà không cần khởi chạy registry. Có thể chạy một hoặc nhiều HTTP mock server trên cổng cố định, sau đó khai báo URI của chúng trong `application-test.yml`.

Ví dụ cấu hình một mock server:

```yaml
spring:
  cloud:
    discovery:
      client:
        simple:
          instances:
            inventory-service:
              - uri: http://localhost:18081
```

Test có thể khởi tạo Spring context với profile `test`:

```java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;

@SpringBootTest
@ActiveProfiles("test")
class InventoryClientTest {

    @Test
    void applicationContextLoads() {
        // Kiểm tra wiring và cấu hình discovery.
    }
}
```

Đoạn test trên chỉ xác minh context khởi động. Để kiểm tra request thực tế, hãy khởi động mock server ở cổng đã khai báo, cấu hình response mong đợi và gọi method của `InventoryClient`. Nếu test dùng cổng ngẫu nhiên do mock server cấp, cần đưa cổng thực vào property trước khi context khởi động; không hardcode một cổng cố định rồi giả định mock server luôn dùng cổng đó.

Static discovery không tự kiểm tra mock server có đang chạy hay không. Nếu endpoint chưa khởi động, `DiscoveryClient` vẫn có thể trả về URI từ cấu hình; lỗi chỉ xuất hiện khi consumer gửi request.

## 8. SimpleDiscoveryClient và health check

Simple discovery đọc danh sách URI từ properties. Nó không ping endpoint, không gửi heartbeat, không tự xóa instance khi process dừng và không nhận health status từ registry. Đây là điểm khác biệt quan trọng so với Eureka hoặc Consul.

| Khả năng | SimpleDiscoveryClient | Registry động như Eureka/Consul |
|---|---|---|
| Khai báo service ID và endpoint | Có, qua cấu hình | Có, qua registration |
| Tự phát hiện instance mới | Không | Có, khi instance đăng ký |
| Tự phát hiện instance đã dừng | Không | Có, qua lease/health check tùy registry |
| Heartbeat | Không | Có thể có |
| Health state từ registry | Không | Có |
| Thay đổi endpoint không cần cập nhật config consumer | Không | Thường có |
| Vận hành thêm registry server/agent | Không | Có thể cần |

Nếu muốn kiểm tra sức khỏe endpoint tĩnh, có thể xây dựng health check riêng ở ứng dụng hoặc cấu hình `HealthCheckServiceInstanceListSupplier` của Spring Cloud LoadBalancer. Tuy nhiên, đây là lớp kiểm tra do consumer thực hiện; nó không biến SimpleDiscoveryClient thành registry có registration, heartbeat hoặc đồng bộ trạng thái.

Đặc biệt, không nên dựa vào việc một endpoint xuất hiện trong `getInstances()` để kết luận nó đang khỏe. Danh sách chỉ phản ánh cấu hình đã bind.

## 9. Quản lý thay đổi endpoint

Khi địa chỉ instance thay đổi, static discovery cần cập nhật cấu hình tương ứng. Một quy trình đơn giản có thể là:

1. Xác định service ID cần thay đổi.
2. Cập nhật URI trong profile hoặc property source đang dùng.
3. Kiểm tra endpoint mới có thể truy cập từ consumer.
4. Khởi động lại consumer hoặc thực hiện cơ chế refresh cấu hình đã được thiết kế và kiểm thử.
5. Gọi `DiscoveryClient.getInstances(serviceId)` để xác nhận danh sách mới.
6. Gửi request qua LoadBalancer để xác nhận routing tới endpoint mới.

Không mặc định rằng sửa file YAML trên đĩa sẽ làm một Spring ApplicationContext đang chạy tự cập nhật danh sách instance. Nếu muốn refresh động, cần cấu hình cơ chế external configuration/refresh phù hợp và xác minh SimpleDiscoveryProperties được bind lại đúng cách.

Với danh sách endpoint dài hoặc thay đổi thường xuyên, lưu URI trong file config riêng hoặc external config server có thể giúp quản lý; tuy vậy, vẫn phải có quy trình cập nhật/refresh. Khi nhiều nhóm cùng chỉnh một danh sách, cần quản lý quyền thay đổi và kiểm tra endpoint trước khi phát hành.

## 10. Giới hạn khi dùng static discovery trong hệ thống nhỏ

Static discovery giúp đơn giản hóa vận hành nhưng chuyển trách nhiệm cập nhật endpoint sang cấu hình và quy trình triển khai. Cần cân nhắc:

- **Độ ổn định endpoint:** IP/port phải ổn định đủ lâu để cấu hình không thường xuyên lỗi thời.
- **Khả năng truy cập:** mỗi URI phải hợp lệ từ network namespace của consumer, đặc biệt trong Docker hoặc môi trường nhiều máy.
- **Số lượng instance:** danh sách lớn và thường xuyên thay đổi sẽ khó quản lý thủ công.
- **Health:** danh sách không tự loại endpoint chết; cần health check hoặc cơ chế kiểm tra ở lớp client.
- **Cập nhật:** thay đổi cấu hình cần có quy trình phát hành hoặc refresh.
- **Bảo mật:** không lưu credential trong URI; dùng secret store và TLS khi cần.
- **Tính sẵn sàng:** nếu mọi instance được khai báo đều lỗi, static discovery không có registry để tự phục hồi hoặc phát hiện thay thế.

Với hệ thống nhỏ, có thể dùng static discovery khi số endpoint ít, thay đổi có kiểm soát và chấp nhận cập nhật theo release. Khi cần tự động scale, service registration, heartbeat, health state, failover hoặc nhiều môi trường động, nên chuyển sang Eureka, Consul hoặc cơ chế discovery do nền tảng cung cấp.

## 11. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| `getInstances()` trả danh sách rỗng | Sai service ID hoặc YAML bind sai cấu trúc | So sánh key trong `simple.instances` với chuỗi truyền vào `getInstances()` |
| Simple client không được dùng | Eureka/Consul/ZooKeeper DiscoveryClient vẫn có trên runtime classpath | Kiểm tra dependency tree và bean `DiscoveryClient` thực tế |
| LoadBalanced request báo không tìm thấy instance | Thiếu URI cho service ID hoặc thiếu LoadBalancer starter | Kiểm tra config và thêm `spring-cloud-starter-loadbalancer` |
| Request connection refused | Endpoint khai báo không có process lắng nghe | Khởi động service/mock server và kiểm tra host/port từ consumer |
| Consumer trong container gọi `localhost` thất bại | `localhost` trỏ tới chính container consumer | Dùng service/container DNS hoặc địa chỉ có thể định tuyến |
| Chỉ một instance được gọi | Code tự chọn phần tử đầu tiên thay vì dùng LoadBalancer | Dùng HTTP client có `@LoadBalanced` hoặc LoadBalancerClient |
| Thay YAML nhưng danh sách không đổi | ApplicationContext không tự reload file cấu hình | Restart hoặc triển khai cơ chế refresh đã được kiểm thử |
| Danh sách có endpoint đã dừng | Simple client không thực hiện health check | Dùng health-check supplier hoặc chuyển sang registry động |

## 12. Checklist

- [ ] Đã xác định môi trường này phù hợp với static discovery.
- [ ] Runtime classpath không có registry-backed DiscoveryClient nếu muốn Simple client được tự động chọn.
- [ ] Đã khai báo đúng service ID và URI cho từng instance.
- [ ] Index của dạng properties bắt đầu từ `0` và không bị trùng.
- [ ] URI có scheme, host và port phù hợp.
- [ ] Endpoint truy cập được từ network namespace của consumer.
- [ ] Đã tách endpoint local/test bằng profile hoặc property source.
- [ ] Đã hiểu profile không loại bỏ dependency khỏi classpath.
- [ ] Đã thêm Spring Cloud LoadBalancer nếu muốn gọi bằng service ID.
- [ ] Đã kiểm thử khi một endpoint dừng và hiểu rằng static list không tự loại endpoint.
- [ ] Đã có quy trình cập nhật cấu hình khi URI thay đổi.
- [ ] Không lưu credential hoặc secret trong URI.

## Tài liệu tham khảo

- [Spring Cloud Commons 5.1.0 — Common Abstractions: SimpleDiscoveryClient](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html)
- [Spring Cloud Commons 5.1.0 — Configuration Properties](https://docs.spring.io/spring-cloud-commons/reference/configprops.html)
- [Spring Cloud Commons — Spring RestClient as a LoadBalancer Client](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html)
- [Spring Cloud Commons — SimpleDiscoveryClient source](https://github.com/spring-cloud/spring-cloud-commons/blob/main/spring-cloud-commons/src/main/java/org/springframework/cloud/client/discovery/simple/SimpleDiscoveryClient.java)
- [Spring Cloud Commons — SimpleDiscoveryClient auto-configuration source](https://github.com/spring-cloud/spring-cloud-commons/blob/main/spring-cloud-commons/src/main/java/org/springframework/cloud/client/discovery/simple/SimpleDiscoveryClientAutoConfiguration.java)
