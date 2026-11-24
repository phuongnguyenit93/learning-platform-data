# Chỉ đăng ký, chỉ truy vấn hoặc thực hiện cả hai vai trò

Một ứng dụng Spring Cloud dùng Eureka có thể tham gia registry theo hai hướng độc lập: **đăng ký instance của chính nó** để service khác tìm thấy, và **tải registry** để tìm các service khác. Hai hướng này được điều khiển bởi `eureka.client.register-with-eureka` và `eureka.client.fetch-registry`.

Vì hai thuộc tính độc lập, một ứng dụng có thể chỉ đăng ký, chỉ truy vấn, làm cả hai hoặc không làm việc nào. Chọn đúng tổ hợp giúp tránh tải registry không cần thiết, đồng thời bảo đảm ứng dụng có đủ dữ liệu discovery cho các lời gọi liên service.

## 1. Hai vai trò của Eureka Client

### Đăng ký instance: `register-with-eureka`

Khi `eureka.client.register-with-eureka=true`, Eureka Client gửi thông tin instance của ứng dụng đến Eureka Server. Thông tin đăng ký thường gồm application/service name, instance ID, hostname hoặc IP, port, metadata và trạng thái ban đầu.

Spring Cloud Netflix thường lấy tên ứng dụng từ `spring.application.name`. Khi instance đã đăng ký, Eureka Client gửi heartbeat định kỳ để gia hạn lease. Khi ứng dụng dừng đúng quy trình, client có thể gửi yêu cầu hủy đăng ký; nếu heartbeat mất, server xử lý lease expiration và eviction theo cấu hình của nó.

Ví dụ:

```yaml
spring:
  application:
    name: inventory-service

server:
  port: 8084

eureka:
  client:
    register-with-eureka: true
    service-url:
      defaultZone: http://localhost:8761/eureka/
```

Ứng dụng `inventory-service` đăng ký với Eureka Server tại địa chỉ trên. Service khác có thể tìm instance này nếu chúng tải được registry và instance đang ở trạng thái phù hợp.

`register-with-eureka` chỉ quyết định ứng dụng hiện tại có tự đăng ký làm Eureka client hay không. Thuộc tính này không bật hoặc tắt khả năng Eureka Server tiếp nhận đăng ký từ các ứng dụng khác.

### Truy vấn registry: `fetch-registry`

Khi `eureka.client.fetch-registry=true`, Eureka Client tải registry từ Eureka Server và duy trì dữ liệu cục bộ để tra cứu. Các API như `DiscoveryClient.getServices()` và `DiscoveryClient.getInstances(serviceId)` dựa trên dữ liệu discovery mà implementation cung cấp.

Ví dụ:

```yaml
eureka:
  client:
    fetch-registry: true
    service-url:
      defaultZone: http://localhost:8761/eureka/
```

Ứng dụng có thể dùng `DiscoveryClient` hoặc Spring Cloud LoadBalancer để tìm instance của `inventory-service`. Consumer không cần đăng ký chính nó nếu nó không cung cấp API cho service khác.

Registry thường được tải và làm mới theo chu kỳ, nên kết quả có thể trễ so với thay đổi vừa xảy ra ở server. `fetch-registry=true` không có nghĩa mỗi lần gọi `getInstances()` đều tạo một truy vấn đồng bộ đến server; client thường đọc từ registry cục bộ đã được tải và cập nhật định kỳ.

## 2. Bốn tổ hợp cấu hình

Hai cờ tạo thành bốn chế độ. Đây là cách đọc nhanh để chọn cấu hình cho từng ứng dụng:

| `register-with-eureka` | `fetch-registry` | Vai trò của ứng dụng | Trường hợp thường dùng |
| --- | --- | --- | --- |
| `true` | `true` | Đăng ký và truy vấn | Microservice vừa cung cấp API vừa gọi service khác |
| `true` | `false` | Chỉ đăng ký | Provider không cần discovery các service khác |
| `false` | `true` | Chỉ truy vấn | Consumer chỉ gọi service khác, không cần được tìm thấy |
| `false` | `false` | Không đăng ký, không tải registry | Eureka Server độc lập hoặc ứng dụng không tham gia discovery |

Hai cờ này không thay thế `@EnableEurekaServer`. Chúng điều khiển vai trò Eureka Client bên trong ứng dụng. Một ứng dụng có thể bật Eureka Server endpoint và đồng thời cấu hình Eureka Client của chính nó theo một trong bốn tổ hợp.

## 3. Chỉ đăng ký: provider không cần tìm service khác

Đặt `register-with-eureka=true` và `fetch-registry=false` khi ứng dụng chỉ cần công bố instance của nó cho các consumer, còn bản thân ứng dụng không gọi service khác qua discovery.

Ví dụ `application.yml`:

```yaml
spring:
  application:
    name: catalog-service

server:
  port: 8083

eureka:
  client:
    register-with-eureka: true
    fetch-registry: false
    service-url:
      defaultZone: ${EUREKA_SERVER_URL:http://localhost:8761/eureka/}
  instance:
    prefer-ip-address: true
    instance-id: ${spring.application.name}:${spring.cloud.client.ip-address}:${server.port}
```

Trong cấu hình này:

- `catalog-service` gửi đăng ký và heartbeat đến Eureka.
- Eureka Server có thể cung cấp instance này cho những consumer đã tải registry.
- Client không tải danh sách toàn bộ service về cache cục bộ.
- Code trong `catalog-service` không nên trông đợi `DiscoveryClient.getInstances()` trả danh sách các service khác từ Eureka vì registry không được fetch.

Chế độ này phù hợp với provider chỉ phục vụ request đến từ bên ngoài hoặc từ gateway, và không có lời gọi outbound cần service discovery. Nếu sau này provider bắt đầu gọi `pricing-service` hoặc `identity-service` bằng service ID, hãy bật `fetch-registry` hoặc cấu hình discovery phù hợp.

## 4. Chỉ truy vấn: consumer không cần đăng ký chính nó

Đặt `register-with-eureka=false` và `fetch-registry=true` khi ứng dụng chỉ cần tìm service khác và không cần được các ứng dụng khác gọi thông qua Eureka.

Ví dụ `application.yml`:

```yaml
spring:
  application:
    name: batch-report

server:
  port: 8090

eureka:
  client:
    register-with-eureka: false
    fetch-registry: true
    service-url:
      defaultZone: ${EUREKA_SERVER_URL:http://localhost:8761/eureka/}
```

Ứng dụng `batch-report` tải registry và có thể gọi `catalog-service`, nhưng không đăng ký instance của chính nó. Điều này hợp lý với batch job, worker nội bộ hoặc ứng dụng chạy theo lịch không cung cấp endpoint cho service khác.

Nếu consumer có REST API cần được gateway hoặc service khác tìm thấy, không nên tắt đăng ký. Trong trường hợp đó, dùng cả hai vai trò hoặc tách phần worker và API thành các ứng dụng riêng.

### Dùng DiscoveryClient để truy vấn

```java
import java.util.List;

import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.discovery.DiscoveryClient;
import org.springframework.stereotype.Service;

@Service
public class CatalogLookup {

    private final DiscoveryClient discoveryClient;

    public CatalogLookup(DiscoveryClient discoveryClient) {
        this.discoveryClient = discoveryClient;
    }

    public List<ServiceInstance> findCatalogInstances() {
        return discoveryClient.getInstances("catalog-service");
    }
}
```

Đoạn code chỉ hoạt động khi discovery implementation đã được cấu hình và registry có dữ liệu. Nếu dùng `fetch-registry=false`, danh sách service từ Eureka không được tải vào client để thực hiện tra cứu thông thường.

## 5. Vừa đăng ký vừa truy vấn: microservice phổ biến

Phần lớn microservice vừa cung cấp API vừa gọi các service khác. Ví dụ `checkout-service` cung cấp endpoint cho gateway, đồng thời gọi `catalog-service` và `payment-service`. Khi đó bật cả hai thuộc tính:

```yaml
spring:
  application:
    name: checkout-service

server:
  port: 8082

eureka:
  client:
    register-with-eureka: true
    fetch-registry: true
    service-url:
      defaultZone: ${EUREKA_SERVER_URL:http://localhost:8761/eureka/}
  instance:
    prefer-ip-address: true
    instance-id: ${spring.application.name}:${spring.cloud.client.ip-address}:${server.port}
```

Với cấu hình này, `checkout-service`:

1. Đăng ký instance của nó để gateway và service khác có thể tìm thấy.
2. Gửi heartbeat để gia hạn lease.
3. Tải registry để biết các instance của service khác.
4. Dùng `DiscoveryClient` hoặc LoadBalancer để tìm và gọi service theo tên.

Ví dụ với `RestTemplate` có `@LoadBalanced`, consumer có thể gọi `http://catalog-service/api/products/42`. LoadBalancer chọn instance từ dữ liệu discovery đã được tải. `DiscoveryClient` và LoadBalancer là hai phần khác nhau: discovery cung cấp danh sách instance, còn LoadBalancer chọn instance cho request.

Đây là lựa chọn phổ biến khi một ứng dụng vừa là provider vừa là consumer trong cùng hệ thống microservice.

## 6. Không làm cả hai: Eureka Server độc lập

Một Eureka Server standalone thường không cần tự đăng ký như một ứng dụng client và cũng không cần tải registry từ peer khác. Có thể cấu hình Eureka Client tích hợp bên trong server như sau:

```java
package com.example.discovery;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cloud.netflix.eureka.server.EnableEurekaServer;

@SpringBootApplication
@EnableEurekaServer
public class DiscoveryServerApplication {

    public static void main(String[] args) {
        SpringApplication.run(DiscoveryServerApplication.class, args);
    }
}
```

```yaml
spring:
  application:
    name: discovery-server

server:
  port: 8761

eureka:
  client:
    register-with-eureka: false
    fetch-registry: false
    service-url:
      defaultZone: http://localhost:8761/eureka/
```

Hai cờ `false` ở đây chỉ tắt vai trò Eureka Client tự đăng ký và fetch registry của ứng dụng `discovery-server`. `@EnableEurekaServer` vẫn bật REST API và dashboard để các Eureka Client khác đăng ký, gửi heartbeat và truy vấn.

### Khi triển khai Eureka peer

Nếu có nhiều Eureka Server peer, cấu hình của mỗi server thường bật cả đăng ký và fetch registry để các server trao đổi với nhau. Ví dụ peer 1 biết peer 2 và peer 3:

```yaml
eureka:
  client:
    register-with-eureka: true
    fetch-registry: true
    service-url:
      defaultZone: http://eureka-2:8761/eureka/,http://eureka-3:8761/eureka/
```

Đây là cấu hình khác với Eureka Server standalone. Không sao chép hai cờ `false` của standalone vào mọi node trong cụm peer, nếu không các server sẽ không tham gia trao đổi registry theo cấu hình mong muốn.

## 7. Sơ đồ luồng đăng ký và truy vấn

```mermaid
flowchart TB
    subgraph APP[Ứng dụng Spring Boot]
        A[Application context]
        RC[Eureka Client]
        DC[DiscoveryClient]
        LB[Spring Cloud LoadBalancer]
        A --> RC
        A --> DC
        DC --> LB
    end
    E[(Eureka Server)]
    P[Service provider khác]
    RC -->|register-with-eureka=true<br/>Register + heartbeat| E
    E -->|Registry response| RC
    RC -->|fetch-registry=true<br/>Fetch / refresh local cache| DC
    DC -->|getInstances(serviceId)| LB
    LB -->|Chọn instance URI| P
```

Sơ đồ thể hiện hai luồng cấu hình độc lập:

- `register-with-eureka=true` kích hoạt luồng từ ứng dụng đến server để đăng ký instance và duy trì heartbeat.
- `fetch-registry=true` kích hoạt luồng tải danh sách service instance về client để discovery.

Nếu tắt một luồng, luồng còn lại vẫn có thể hoạt động. Ví dụ, consumer-only vẫn fetch registry dù không đăng ký chính nó; provider-only vẫn đăng ký và gửi heartbeat dù không tải registry.

## 8. Chọn cấu hình theo vai trò ứng dụng

| Loại ứng dụng | Đăng ký | Fetch registry | Lý do |
| --- | --- | --- | --- |
| REST provider chỉ nhận request | Bật | Có thể tắt | Cần được consumer tìm thấy, không cần tìm service khác |
| Consumer/batch worker chỉ gọi outbound | Tắt | Bật | Cần tìm provider, không cần xuất hiện trong registry |
| Microservice cung cấp API và gọi outbound | Bật | Bật | Vừa là provider vừa là consumer |
| Eureka Server standalone | Tắt | Tắt | Server nhận client registration nhưng không cần tự tham gia như peer |
| Eureka Server peer trong cluster | Bật | Bật | Server tham gia trao đổi registry với peer |
| Job chạy một lần, không đăng ký và không dùng discovery | Tắt | Tắt | Không cần hai chức năng của Eureka Client |

Đừng chọn cấu hình chỉ dựa trên tên gọi “provider” hoặc “consumer”. Hãy xem ứng dụng có cần được service khác gọi không, và nó có cần tra cứu service khác không. Một ứng dụng có thể có cả API inbound và lời gọi outbound nên thường cần cả hai cờ bật.

## 9. Tác động đến DiscoveryClient và LoadBalancer

`fetch-registry` quyết định Eureka Client có tải registry để discovery hay không. Khi tắt, không nên dựa vào các API tra cứu registry của Eureka như `DiscoveryClient.getInstances()` để tìm service khác. Việc ứng dụng có thể inject bean `DiscoveryClient` không đồng nghĩa nó có dữ liệu instance để trả về.

`register-with-eureka` không quyết định khả năng gọi service. Một ứng dụng không đăng ký vẫn có thể gọi provider nếu `fetch-registry=true`, registry URL đúng và HTTP client được tích hợp LoadBalancer.

Ví dụ consumer cần gọi service bằng tên logic:

```java
@Configuration
class ClientConfiguration {

    @Bean
    @LoadBalanced
    RestTemplate restTemplate() {
        return new RestTemplate();
    }
}
```

```java
String result = restTemplate.getForObject(
        "http://catalog-service/api/products/42",
        String.class
);
```

Đoạn gọi trên cần `fetch-registry=true` và một Eureka client implementation được cấu hình. Nếu không có `@LoadBalanced`, `catalog-service` có thể bị hiểu là hostname DNS thông thường thay vì service ID.

## 10. Registry cache và độ trễ cập nhật

Khi `fetch-registry=true`, client thường giữ bản sao registry cục bộ và cập nhật theo chu kỳ. Điều này giúp các lời gọi discovery không phải truy vấn server cho mỗi request, nhưng cũng có nghĩa dữ liệu có thể trễ:

- Instance mới đăng ký có thể chưa xuất hiện ngay trong cache của consumer.
- Instance đã deregister có thể còn được thấy trong một khoảng thời gian.
- Peer hoặc server có thể có trạng thái khác nhau tạm thời khi mạng gián đoạn.
- LoadBalancer có thể có cache/danh sách supplier riêng tùy cấu hình.

`eureka.client.registry-fetch-interval-seconds` điều chỉnh chu kỳ fetch registry trong các phiên bản Spring Cloud Netflix hỗ trợ thuộc tính này. Chỉ giảm chu kỳ khi đã cân nhắc tải lên Eureka Server và lợi ích về độ mới dữ liệu. Không nên coi việc fetch thường xuyên là cách giải quyết mọi vấn đề stale instance; health check, lease, deregistration và xử lý lỗi request vẫn cần được thiết kế.

Nếu service ID không xuất hiện, kiểm tra provider đã đăng ký chưa, consumer có `fetch-registry=true` chưa, URL Eureka có đúng không, và consumer có đang trỏ tới đúng registry/region không.

## 11. Lỗi cấu hình thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách khắc phục |
| --- | --- | --- |
| Provider không xuất hiện trên dashboard | `register-with-eureka=false`, sai URL hoặc lỗi kết nối | Bật đăng ký, kiểm tra `defaultZone`, log và mạng |
| Consumer không tìm thấy provider | `fetch-registry=false` hoặc registry chưa có instance | Bật fetch, kiểm tra tên service và trạng thái đăng ký |
| Ứng dụng chỉ đăng ký được nhưng không gọi service khác | Chỉ bật register, fetch đang tắt | Bật `fetch-registry=true` nếu có lời gọi outbound |
| Ứng dụng gọi được service khác nhưng không được service khác tìm thấy | Chỉ bật fetch, register đang tắt | Bật `register-with-eureka=true` nếu ứng dụng cung cấp API |
| Eureka Server standalone tự xuất hiện như một client | Eureka Client tích hợp vẫn đang register | Đặt `register-with-eureka=false` cho standalone server |
| Eureka peer không trao đổi registry như mong muốn | Peer tắt register/fetch hoặc URL peer sai | Bật hai cờ và khai báo các peer có thể truy cập |
| `DiscoveryClient` trả danh sách rỗng | Chưa fetch, sai service ID, registry rỗng hoặc dữ liệu chưa cập nhật | Kiểm tra flags, dashboard, cache và log |
| Instance cũ còn được trả về | Cache/fetch interval, lease hoặc deregistration chưa hoàn tất | Kiểm tra chu kỳ refresh và vòng đời instance |

## 12. Checklist trước khi triển khai

- [ ] Xác định ứng dụng có cung cấp API cần được service khác tìm thấy hay không.
- [ ] Xác định ứng dụng có gọi service khác bằng service discovery hay không.
- [ ] Chọn đúng `register-with-eureka` theo nhu cầu đăng ký.
- [ ] Chọn đúng `fetch-registry` theo nhu cầu truy vấn.
- [ ] Cấu hình `defaultZone` đến Eureka Server hoặc peer phù hợp.
- [ ] Kiểm tra `spring.application.name`, instance ID, hostname/IP và port được quảng bá.
- [ ] Nếu gọi service bằng tên logic, cấu hình Spring Cloud LoadBalancer cho HTTP client.
- [ ] Kiểm tra dashboard và `DiscoveryClient` để xác nhận dữ liệu registry.
- [ ] Xem xét độ trễ cache/fetch khi kiểm tra instance mới hoặc instance đã dừng.
- [ ] Với Eureka Server standalone và peer cluster, dùng cấu hình riêng phù hợp với topology.

Hai cờ `register-with-eureka` và `fetch-registry` biểu diễn hai nhu cầu độc lập: công bố instance của chính ứng dụng và tải thông tin instance của các service khác. Provider-only bật đăng ký; consumer-only bật fetch; microservice thường làm cả hai; Eureka Server standalone thường tắt cả hai ở Eureka Client tích hợp bên trong. Chọn cấu hình theo luồng inbound và outbound thực tế giúp Eureka Client làm đúng vai trò mà ứng dụng cần.
