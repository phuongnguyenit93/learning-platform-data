# Ánh xạ artifact sang service ID khi tích hợp khám phá dịch vụ

## Mục tiêu bài học

Trong **Spring Cloud Contract**, **producer** mô tả hành vi HTTP hoặc thông điệp bằng Groovy/YAML DSL; công cụ sinh kiểm thử phía producer và tạo **stub artifact** để **consumer** chạy thử với **Stub Runner**. Khi consumer gọi trực tiếp một địa chỉ cố định, việc trỏ vào cổng của stub khá đơn giản. Nhưng trong kiến trúc microservices, client thường gọi dịch vụ bằng **tên logic** thay vì địa chỉ máy chủ: ví dụ Feign gọi `orders-api`, hoặc một `RestTemplate` có load balancing gọi `http://orders-api`.

Trong trường hợp đó xuất hiện **hai hệ thống định danh**:

- **Artifact ID**: một phần của tọa độ stub JAR trong Maven/artifact repository, dùng để **tải đúng bộ stub**.
- **Service ID**: tên dịch vụ mà ứng dụng consumer dùng với **DiscoveryClient**, **Spring Cloud LoadBalancer**, Feign hoặc một HTTP client có hỗ trợ khám phá dịch vụ, dùng để **định tuyến lời gọi**.

Hai tên có thể giống nhau nhưng **không bắt buộc giống nhau**. Tính năng **Stub Runner Spring Cloud** cho phép các instance stub được nhìn thấy qua service discovery và cấu hình ánh xạ từ artifact ID sang service ID mà consumer đang sử dụng.

Sau bài này, bạn có thể:

1. Phân biệt `groupId`, `artifactId`, `version`, `classifier`, `port` và `serviceId`.
2. Giải thích vai trò của `DiscoveryClient` và `ReactorServiceInstanceLoadBalancer` khi Stub Runner chạy HTTP stub.
3. Dùng cấu hình `spring.cloud.contract.stubrunner.ids-to-service-ids` để ánh xạ artifact sang tên dịch vụ của consumer.
4. Thiết lập consumer test với `@AutoConfigureStubRunner` và client có hỗ trợ load balancing.
5. Chẩn đoán tình huống stub đã khởi động nhưng Feign/WebClient/RestTemplate vẫn gọi sai nơi.
6. Thiết kế CI kiểm tra đúng phiên bản stub và không vô tình gọi dịch vụ thật.

## 1. Vấn đề: tên artifact và tên dịch vụ không trùng nhau

Giả sử Checkout Service cần truy vấn Order Service. Producer phát hành stub như sau:

~~~text
groupId      com.example.orders
artifactId   order-contract-stubs
version      1.4.2
classifier   stubs

Tọa độ stub artifact:
com.example.orders:order-contract-stubs:1.4.2:stubs
~~~

Nhưng Checkout gọi service logic:

~~~text
orders-api
~~~

Ví dụ một Feign client:

~~~java
@FeignClient(name = "orders-api")
public interface OrderClient {

    @GetMapping("/api/orders/{id}")
    OrderResponse findById(@PathVariable("id") String orderId);
}
~~~

`OrderResponse` là DTO của ứng dụng minh họa. Trong code này, `orders-api` là **service ID mà Feign cần định tuyến**, không phải tên file JAR, cũng không phải tên HTTP endpoint.

Nếu Stub Runner tải được JAR `order-contract-stubs` và mở HTTP stub trên cổng ngẫu nhiên nhưng không đăng ký nó dưới tên `orders-api`, consumer có thể gặp lỗi:

- Không tìm thấy instance cho service ID `orders-api`.
- Client fallback sang discovery thật và gọi server không mong muốn.
- Stub server hoạt động khi gọi trực tiếp `localhost:port` nhưng Feign vẫn thất bại.

**Giải pháp không phải đổi URL trong hợp đồng** từ `/api/orders/{id}` thành một URL khác. Điều cần sửa là **cầu nối giữa danh tính artifact của stub và service ID trong consumer**.

## 2. Hai bước khác nhau: phân giải artifact và tìm ServiceInstance

~~~mermaid
flowchart TD
    A["Consumer integration test"] --> B["Stub Runner"]
    B --> C["Phân giải stub JAR<br/>group:artifact:version:classifier"]
    C --> D["Khởi động HTTP stub<br/>localhost:cổng được chọn"]
    D --> E["Stub Runner Spring Cloud<br/>ánh xạ artifact → service ID"]
    E --> F["DiscoveryClient / LoadBalancer"]
    G["Feign / RestTemplate / WebClient<br/>gọi orders-api"] --> F
    F --> H["Chọn ServiceInstance<br/>của stub đang chạy"]
    H --> D
    D --> I["Trả HTTP response từ mapping"]
    I --> J["Consumer kiểm tra hành vi"]
~~~

Hãy phân biệt:

| Bước | Đầu vào | Kết quả |
| --- | --- | --- |
| **Phân giải artifact** | `com.example.orders:order-contract-stubs:1.4.2:stubs` | Tải đúng JAR chứa stub mappings |
| **Khởi động stub** | Nội dung JAR, cấu hình stub server | Một HTTP server mô phỏng trên host/port |
| **Ánh xạ service ID** | Artifact đã chạy và tên dịch vụ consumer dùng | Stub được nhận diện dưới tên logic, ví dụ `orders-api` |
| **Service discovery** | `getInstances("orders-api")` hoặc yêu cầu chọn instance | Danh sách/instance có URI trỏ tới stub |
| **Consumer HTTP request** | Endpoint `/api/orders/ORD-1001` | HTTP response mà stub mapping định nghĩa |

**Ánh xạ không sửa nội dung stub JAR.** Nó điều chỉnh cách consumer test tìm đến stub instance. Nếu mapping bên trong JAR trả 404 vì request không khớp, đổi service ID không thể sửa sai method, path, header hoặc body matcher.

## 3. Hiểu chính xác các loại ID

Một Stub Runner ID có thể chứa:

~~~text
com.example.orders:order-contract-stubs:1.4.2:stubs
       group             artifact       version classifier
~~~

Trong cấu hình Stub Runner, có thể có thêm **port**:

~~~text
com.example.orders:order-contract-stubs:1.4.2:stubs:8090
~~~

| Khái niệm | Ví dụ | Dùng ở đâu? |
| --- | --- | --- |
| **group ID** | `com.example.orders` | Namespace của artifact trong repository |
| **artifact ID** | `order-contract-stubs` | Xác định module/artifact stub |
| **version** | `1.4.2` | Chọn phiên bản artifact |
| **classifier** | `stubs` | Chọn stub JAR thay vì JAR ứng dụng chính |
| **stub port** | `8090` hoặc port tự chọn | Cổng HTTP server do Stub Runner chạy |
| **service ID** | `orders-api` | Tên mà consumer dùng khi yêu cầu service discovery |
| **endpoint path** | `/api/orders/ORD-1001` | Request mà HTTP stub cần match |

Chỉ **bốn thành phần đầu tiên** cấu thành tọa độ artifact trong ví dụ. `port` là tham số chạy Stub Runner; `service ID` là tên ở lớp khám phá dịch vụ; `endpoint path` thuộc hợp đồng HTTP.

Đặc biệt, `spring.application.name` của producer và `artifactId` trong publication thường được đặt giống nhau theo quy ước đội, nhưng **không có quy tắc buộc chúng bằng nhau**. Service ID mà consumer gọi có thể là alias dùng vì lịch sử hoặc vì kiến trúc triển khai.

## 4. Stub Runner Spring Cloud tích hợp vào đâu?

Spring Cloud Contract có phần tích hợp **Stub Runner Spring Cloud** để đưa các stub server vào cơ chế tìm instance của Spring Cloud. Tài liệu Spring mô tả tích hợp với:

- **`DiscoveryClient`**: API để truy vấn danh sách instance của một service ID.
- **`ReactorServiceInstanceLoadBalancer`**: cơ chế lựa chọn instance trong Spring Cloud LoadBalancer cho các luồng sử dụng mô hình reactive.

Khi tích hợp được cấu hình đúng, các client sử dụng đường đi **discovery/load-balanced** có thể gọi stub thay cho dịch vụ thật. Không cần khởi động Eureka, Consul hay Zookeeper production chỉ để consumer test một dependency.

### Tích hợp không tự có ở mọi HTTP client

| Cách consumer gọi | Có đi qua service discovery không? | Hệ quả |
| --- | --- | --- |
| `@FeignClient(name = "orders-api")` với tích hợp load balancing phù hợp | Có, theo cấu hình Feign/Spring Cloud | Có thể chọn stub được đăng ký dưới `orders-api` |
| `@LoadBalanced RestTemplate` gọi `http://orders-api` | Có | Có thể phân giải `orders-api` thành stub instance |
| `@LoadBalanced WebClient.Builder` gọi `http://orders-api` | Có | Có thể dùng Spring Cloud LoadBalancer để đến stub |
| `new RestTemplate()` gọi `http://orders-api` | Thường không | `orders-api` có thể bị xem là hostname DNS, không phải service ID |
| `WebClient.create("http://localhost:8080")` | Không qua service ID | Ánh xạ artifact → service ID không tác động |
| HTTP client gọi URL từ biến cấu hình tĩnh | Tùy client | Có thể cần thay URL test trực tiếp thay vì dùng discovery |

**Cần cấu hình cả hai phía:** Stub Runner đăng ký tên logic đúng, **và** client consumer thực sự dùng cơ chế load balancing/discovery. Một map đúng trong YAML không thể biến một `RestTemplate` thông thường thành load-balanced client.

## 5. Cấu hình ids-to-service-ids trong consumer test

Giả sử stub có artifact ID `order-contract-stubs`, nhưng consumer vẫn gọi service ID `orders-api`.

Cấu hình thử nghiệm tham khảo trong `src/test/resources/application-contract.yml`:

~~~yaml
spring:
  cloud:
    contract:
      stubrunner:
        ids-to-service-ids:
          order-contract-stubs: orders-api
~~~

Đọc theo hướng:

~~~text
Artifact ID trong Stub Runner   →   Service ID consumer sử dụng
order-contract-stubs            →   orders-api
~~~

**Không đảo chiều.** Viết `orders-api: order-contract-stubs` có nghĩa khác và sẽ không giải quyết tình huống này.

Với Spring Boot, `ids-to-service-ids` là cách viết property dạng kebab-case; trong một số ví dụ/tài liệu hoặc cấu hình chương trình bạn sẽ thấy tên tương ứng `idsToServiceIds`. Tên property và cơ chế binding cần được đối chiếu với phiên bản Spring Cloud Contract đang dùng.

### Khi cần phân biệt các group ID

Nếu có nhiều producer mang cùng artifact ID, chỉ dùng khóa `order-contract-stubs` có thể không đủ rõ. Cấu hình hỗ trợ các khóa theo định danh kiểu Ivy, ví dụ một cặp `groupId:artifactId`:

~~~yaml
spring:
  cloud:
    contract:
      stubrunner:
        ids-to-service-ids:
          "com.example.orders:order-contract-stubs": orders-api
          "com.example.billing:payment-contract-stubs": billing-api
~~~

**Nháy kép quanh key chứa dấu hai chấm** là cần thiết để YAML hiểu rõ một khóa chuỗi. Bộ phân giải matcher dùng thông tin artifact ID/Ivy notation theo khả năng của phiên bản Stub Runner; nên kiểm tra ánh xạ thực tế với các stub đã tải.

Chú ý rằng nhóm `com.example.orders` trong ví dụ **khác** namespace của tên service `orders-api`. Ánh xạ không yêu cầu chúng có chung tiền tố.

### Nếu không cấu hình ánh xạ?

Các ví dụ trong tài liệu Spring Cloud Contract mô tả khả năng suy ra service ID dựa trên `artifactId` của stub. Vì thế, nếu artifact ID chính là `orders-api` và consumer cũng gọi `orders-api`, cấu hình tùy chỉnh có thể không cần.

Nhưng khi artifact ID là `order-contract-stubs`, còn consumer gọi `orders-api`, nên **đặt mapping tường minh** và có test kiểm tra `DiscoveryClient.getInstances("orders-api")`, thay vì trông đợi vào tên suy luận.

## 6. Ví dụ consumer integration test hoàn chỉnh về luồng

Giả sử Checkout có `RestTemplate` được tạo dưới dạng load-balanced bean:

~~~java
package com.example.checkout.config;

import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestTemplate;

@Configuration
public class CheckoutHttpConfiguration {

    @Bean
    @LoadBalanced
    RestTemplate ordersRestTemplate() {
        return new RestTemplate();
    }
}
~~~

Consumer dùng service ID, không hardcode stub port:

~~~java
package com.example.checkout.orders;

import org.springframework.stereotype.Service;
import org.springframework.web.client.RestTemplate;

@Service
public class OrderLookup {

    private final RestTemplate restTemplate;

    public OrderLookup(RestTemplate restTemplate) {
        this.restTemplate = restTemplate;
    }

    public String getOrderJson(String orderId) {
        return restTemplate.getForObject(
            "http://orders-api/api/orders/{id}",
            String.class,
            orderId
        );
    }
}
~~~

Để bài học đơn giản, ví dụ trả về JSON string. Trong ứng dụng thật, nên dùng DTO và kiểm tra các field consumer cần, không nhất thiết so sánh JSON theo đúng thứ tự key.

Với Stub Runner và môi trường Spring Boot test:

~~~java
package com.example.checkout.orders;

import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.discovery.DiscoveryClient;
import org.springframework.cloud.contract.stubrunner.spring.AutoConfigureStubRunner;
import org.springframework.cloud.contract.stubrunner.spring.StubRunnerProperties;
import org.springframework.test.context.ActiveProfiles;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest
@ActiveProfiles("contract")
@AutoConfigureStubRunner(
    ids = "com.example.orders:order-contract-stubs:1.4.2:stubs",
    stubsMode = StubRunnerProperties.StubsMode.LOCAL
)
class OrderDiscoveryContractTest {

    @Autowired
    DiscoveryClient discoveryClient;

    @Autowired
    OrderLookup orderLookup;

    @Test
    void shouldFindStubThroughOrdersApiServiceId() {
        List<ServiceInstance> instances =
            discoveryClient.getInstances("orders-api");
        assertFalse(instances.isEmpty(),
            "orders-api must resolve to a stub instance");

        String json = orderLookup.getOrderJson("ORD-1001");
        assertNotNull(json);
        assertTrue(json.contains("\"PAID\""));
    }
}
~~~

Đây là **khung ví dụ**; test thật cần dependencies, annotation và package được cấu hình phù hợp phiên bản Spring Boot/Spring Cloud, đồng thời phải có JAR stub `1.4.2` trong Maven local. `@ActiveProfiles("contract")` làm Spring tải cấu hình `application-contract.yml` trong ví dụ.

Trình tự mong muốn:

1. Stub Runner tải `com.example.orders:order-contract-stubs:1.4.2:stubs`.
2. Stub Runner khởi động HTTP stub trên một port được chọn.
3. Tích hợp Spring Cloud đăng ký stub dưới `orders-api` theo mapping.
4. `DiscoveryClient.getInstances("orders-api")` trả về ít nhất một `ServiceInstance`.
5. `OrderLookup` gọi `http://orders-api/...` bằng load-balanced RestTemplate.
6. Consumer nhận response của stub và xác minh nghiệp vụ của mình.

**Đừng dừng ở `assertFalse(instances.isEmpty())`.** Nó chỉ xác minh có instance được tìm thấy. Cần có request thật đi qua client ứng dụng và assertion về response hoặc trạng thái ứng dụng sau khi xử lý.

### Với Feign

Nếu Checkout dùng Spring Cloud OpenFeign:

~~~java
@FeignClient(name = "orders-api")
interface OrderClient {

    @GetMapping("/api/orders/{id}")
    OrderResponse getOrder(@PathVariable("id") String id);
}
~~~

Feign phải được bật/cấu hình theo dự án và có tích hợp load balancing thích hợp. Định danh `orders-api` chính là service ID mà mapping cần cung cấp, **không nhất thiết bằng tên artifact**. Bản thân `@FeignClient` cũng không xác minh rằng stub được tải thành công; consumer test phải thực sự gọi phương thức và assert.

### Với WebClient reactive

Ví dụ cấu hình Spring Cloud LoadBalancer cho WebClient:

~~~java
@Bean
@LoadBalanced
WebClient.Builder loadBalancedWebClientBuilder() {
    return WebClient.builder();
}
~~~

Khi consumer sử dụng builder này để gọi `http://orders-api/api/orders/...`, đường đi có thể sử dụng discovery/load balancing. Nếu tạo một builder khác bằng `WebClient.builder()` ở vị trí sử dụng mà không có bộ lọc load balancing, mapping của Stub Runner sẽ không tự tác động lên client đó.

## 7. Không nhầm service ID với tên endpoint hoặc tên instance

Giả sử stub chạy trên:

~~~text
http://127.0.0.1:10876
~~~

Và consumer gọi:

~~~text
http://orders-api/api/orders/ORD-1001
~~~

Với discovery/load-balancing integration, consumer không cần biết port `10876`. Nó yêu cầu một instance thuộc service ID `orders-api`. Cơ chế load balancer nhận được địa chỉ stub và gửi HTTP request đến đó.

| Trường | Giá trị minh họa | Có nên cố định trong code consumer? |
| --- | --- | --- |
| Service ID | `orders-api` | Có thể là một hằng/config công khai trong client |
| Stub host/port | `127.0.0.1:10876` | Không, nếu client dùng discovery; port có thể động |
| Artifact coordinate | `com.example.orders:order-contract-stubs:1.4.2:stubs` | Đặt trong cấu hình test/CI |
| HTTP path | `/api/orders/ORD-1001` | Theo contract, không phụ thuộc port |
| Instance ID | Có thể do adapter tạo riêng | Không nên suy từ artifact hoặc dùng làm service ID |

**Ánh xạ service ID không đổi tên tất cả metadata của instance.** Nó chủ yếu bảo đảm ứng dụng tìm được stub qua tên dịch vụ được thỏa thuận. Những thuộc tính nâng cao của `ServiceInstance`, như metadata, scheme, secure flag hoặc zone, cần được kiểm tra riêng nếu ứng dụng phụ thuộc.

## 8. DiscoveryClient và LoadBalancer: cần kiểm tra cả hai lớp

Một consumer có thể gọi trực tiếp:

~~~java
List<ServiceInstance> instances =
    discoveryClient.getInstances("orders-api");
~~~

Hoặc để một Feign client, RestTemplate hay WebClient có load balancing chọn instance.

Hai kiểu tương tác liên quan nhưng khác nhau:

- **DiscoveryClient**: trả danh sách instance theo service ID; có thể thấy stub đã đăng ký.
- **LoadBalancer**: chọn instance để thực hiện request; có thể thêm logic lựa chọn, retry hoặc metadata filter.

Stub Runner Spring Cloud có tích hợp cho discovery và Spring Cloud LoadBalancer, nhưng điều đó **không chứng minh mọi client tùy chỉnh hoặc mọi chính sách lựa chọn instance đều tự động dùng stub**.

Ví dụ, một ứng dụng có custom `ServiceInstanceListSupplier` lọc theo zone hoặc metadata. Nếu stub instance không mang metadata mà bộ lọc yêu cầu, `DiscoveryClient` có thể thấy service nhưng client vẫn không chọn được instance. Khi gặp tình huống này cần kiểm tra cấu hình client/test và chính sách metadata, không lập tức sửa contract HTTP.

## 9. Bảo vệ test khỏi khám phá dịch vụ thật

Trong consumer integration tests, thông thường không muốn gọi Eureka/Consul/Zookeeper thật hoặc một Config Server ngoài môi trường test. Các nguồn ngoài đó có thể khiến test:

- Không tái lập được giữa laptop và CI.
- Phụ thuộc DNS/network và quyền truy cập.
- Vô tình gọi dịch vụ staging/production thay vì stub.
- Tiếp tục PASS nhờ response của dịch vụ thật, che giấu mapping stub bị sai.

Tài liệu Stub Runner Spring Cloud mô tả chế độ **stub service discovery** và các tùy chọn phối hợp với `DiscoveryClient` sẵn có. Các property liên quan có thể gặp:

~~~yaml
spring:
  cloud:
    contract:
      stubrunner:
        cloud:
          enabled: true
          loadbalancer:
            enabled: true
          stubbed:
            discovery:
              enabled: true
~~~

Đoạn trên minh họa **ý đồ bật Stub Runner Spring Cloud, tích hợp load balancing và cơ chế discovery giả lập**, không thay thế việc kiểm tra giá trị mặc định trên phiên bản cụ thể.

**Khi dùng cơ chế delegate tới DiscoveryClient có sẵn:** một số phiên bản hỗ trợ cấu hình `spring.cloud.contract.stubrunner.cloud.delegate.enabled` để phối hợp kết quả discovery thật với stub. Quy tắc mặc định và phạm vi của lựa chọn này cần xem theo phiên bản đang chạy. Trong CI yêu cầu cô lập, nên xác minh **không có instance thật ngoài ý muốn** xuất hiện trong tập instance mà consumer có thể chọn.

Không nhất thiết luôn tắt mọi nguồn discovery ngoài; có pipeline cần dùng một số dịch vụ test thật. Nhưng lúc đó phải **tuyên bố rõ phạm vi**, có kiểm soát endpoint và không được để fallback âm thầm sang production.

### Vì sao service discovery giả lập vẫn cần cấu hình client?

Giả sử discovery stub đã đăng ký `orders-api`, nhưng client lại được tạo như sau:

~~~java
RestTemplate restTemplate = new RestTemplate();
restTemplate.getForObject(
    "http://orders-api/api/orders/ORD-1001",
    String.class
);
~~~

Nếu không có interceptor/load balancer, `orders-api` thường bị xử lý như DNS hostname. Thêm `ids-to-service-ids` vào YAML **không giúp** client này sử dụng `DiscoveryClient`.

Cần inject một `RestTemplate` được đánh dấu `@LoadBalanced` hoặc dùng một cơ chế gọi HTTP test khác được cấu hình phù hợp.

## 10. Nhiều stub và xung đột service ID

Giả sử Checkout có hai dependency:

~~~text
com.example.orders:order-contract-stubs:1.4.2:stubs
com.example.billing:billing-contract-stubs:2.2.0:stubs
~~~

Cấu hình mapping:

~~~yaml
spring:
  cloud:
    contract:
      stubrunner:
        ids-to-service-ids:
          "com.example.orders:order-contract-stubs": orders-api
          "com.example.billing:billing-contract-stubs": billing-api
~~~

Consumer có thể gọi:

~~~text
http://orders-api/api/orders/ORD-1001
http://billing-api/api/payments/PAY-1001
~~~

Khi đó cần hai kiểm tra độc lập: `orders-api` chọn stub Order, `billing-api` chọn stub Billing. Nếu map nhầm cả hai vào `orders-api`, load balancer có thể nhận nhiều instance không tương thích dưới cùng một service ID và request sẽ thất bại tùy lựa chọn instance.

**Không cố ý map nhiều artifact vào một service ID** trừ khi thật sự muốn biểu diễn nhiều instance của cùng một dịch vụ có hành vi tương thích. Nếu nhiều phiên bản stub của cùng service ID cùng hoạt động, kết quả thử nghiệm có thể không ổn định khi mapping khác nhau; cần cô lập từng tổ hợp phiên bản muốn kiểm tra.

### Kiểm tra bằng bảng

| Artifact được tải | Service ID mong muốn | Request đại diện |
| --- | --- | --- |
| `order-contract-stubs:1.4.2` | `orders-api` | GET /api/orders/ORD-1001 |
| `billing-contract-stubs:2.2.0` | `billing-api` | GET /api/payments/PAY-1001 |

Sau khi khởi động Stub Runner, cần xác nhận cả hai service ID có instance, các URI trỏ đến stub server phù hợp và request tới từng service ID trả đúng response.

## 11. Nếu artifact ID và service ID trùng nhau

Một dự án có:

~~~text
artifactId = inventory-service
serviceId  = inventory-service
~~~

Trong trường hợp này, ánh xạ mặc định dựa trên artifact ID có thể đã đúng. Có thể để Stub Runner Spring Cloud đăng ký dưới tên đó mà không cần map tường minh.

Tuy nhiên, trước khi bỏ map hãy kiểm tra:

1. Artifact đang tải có đúng group/artifact/version/classifier?
2. Có instance trong `DiscoveryClient.getInstances("inventory-service")` không?
3. HTTP client thật của consumer có sử dụng chính service ID đó không?
4. Một request từ consumer có đi đến stub trên port được Stub Runner cấp không?

Đừng suy rằng tên artifact và service ID cùng chuỗi thì **mọi kết nối** đã được chuyển sang stub. Còn có điều kiện về client, auto-configuration và dependency phiên bản.

## 12. Dùng port động thay vì khóa cổng chỉ để tạo service ID

Stub Runner hỗ trợ chọn cổng HTTP stub server; nếu không chỉ định port thì thường có thể chọn cổng tự động theo cấu hình. Khi đã tích hợp discovery, consumer **không cần hardcode port** vào logic:

~~~java
@AutoConfigureStubRunner(
    ids = "com.example.orders:order-contract-stubs:1.4.2:stubs",
    stubsMode = StubRunnerProperties.StubsMode.LOCAL
)
~~~

Client vẫn gọi:

~~~text
http://orders-api/api/orders/ORD-1001
~~~

Lợi ích:

- Test chạy song song hoặc trên CI ít va chạm port cố định.
- Không phải cập nhật port trong service code khi Stub Runner thay instance.
- Dễ cấu hình cùng một consumer test trên nhiều máy.

**Port động không chữa được mapping sai.** Nếu test không tìm được `orders-api`, hãy kiểm tra ánh xạ và tích hợp discovery. Nếu client tìm được instance nhưng HTTP 404, hãy kiểm tra request mapping trong stub JAR. Nếu `Connection refused`, hãy kiểm tra server stub thực sự đang chạy và URI/port instance đúng.

## 13. Đừng nhầm tích hợp HTTP service discovery với message destinations

Một message contract có thể dùng:

~~~groovy
outputMessage {
    sentTo("orders.events")
    body(eventType: "ORDER_PAID", orderId: "ORD-1001")
}
~~~

`sentTo("orders.events")` là **đích thông điệp** theo mô hình messaging; nó không phải service ID để Feign hoặc RestTemplate tìm HTTP stub.

| Cơ chế | Định danh cần thiết | Dùng để làm gì? |
| --- | --- | --- |
| HTTP Stub Runner + DiscoveryClient | `orders-api` | Consumer tìm HTTP stub server qua service discovery |
| HTTP artifact resolution | `com.example.orders:order-contract-stubs:1.4.2:stubs` | Tải stub JAR |
| Message contract | `orders.events` | Chỉ nơi producer phát message theo messaging adapter |
| Message stub label | `order_paid` | Có thể dùng để kích hoạt message stub qua Stub Runner khi adapter hỗ trợ |

**Không dùng `ids-to-service-ids` để đổi tên Kafka topic hay RabbitMQ routing key.** Đó là bài toán về binding/destination của messaging, cần cấu hình riêng và kiểm thử tương ứng.

## 14. Dấu hiệu của từng loại lỗi

| Triệu chứng | Nguyên nhân có thể | Bước kiểm tra |
| --- | --- | --- |
| Stub Runner không tải được JAR | Sai tọa độ hoặc `stubsMode`/repository | Kiểm tra group, artifact, version, classifier và nguồn tải |
| Stub server chạy nhưng `getInstances("orders-api")` rỗng | Chưa map tên hoặc Stub Runner Spring Cloud chưa hoạt động | Kiểm tra `ids-to-service-ids`, auto-configuration và classpath |
| `getInstances` có instance nhưng Feign không gọi được | Feign/LB hoặc metadata filter không chọn được instance | Kiểm tra load balancer và service ID Feign dùng |
| `RestTemplate` báo lỗi phân giải hostname `orders-api` | Client không phải `@LoadBalanced RestTemplate` | Kiểm tra bean thực sự được inject |
| Consumer gọi được nhưng nhận 404 từ stub | HTTP request không match mapping | Kiểm tra method, path, headers, query, body |
| Consumer nhận response của dịch vụ thật | Discovery/fallback sang instance ngoài test | Cô lập discovery và xác minh URI thực tế |
| Hai dependency cùng trả dữ liệu lẫn lộn | Map hai artifact vào cùng service ID | Kiểm tra key/value của map và danh sách instance |
| Local PASS, CI fail khi resolve | Chỉ có JAR trong local Maven cache | Publish artifact hoặc cấu hình REMOTE có version cố định |
| Test PASS nhưng behavior mới làm production lỗi | Consumer đang dùng stub phiên bản cũ | Khóa version và chạy lại consumer với stub mới |
| Một test khác ảnh hưởng đến discovery | Shared context/registry, nhiều stub cùng service ID | Cách ly cấu hình, lifecycle và test execution |

Trước khi thay đổi contract, hãy xác định lỗi nằm ở **tải JAR**, **khởi động stub**, **map service ID**, **chọn instance** hay **match HTTP request**.

## 15. Quy trình kiểm tra theo từng lớp

~~~mermaid
flowchart TD
    A["Consumer test khởi động"] --> B{"Tải đúng stub JAR?"}
    B -->|Không| X["Kiểm tra GAV/classifier/repository"]
    B -->|Có| C{"Stub server đã chạy?"}
    C -->|Không| Y["Kiểm tra startup log/port"]
    C -->|Có| D{"Service ID ánh xạ đúng?"}
    D -->|Không| Z["Kiểm tra ids-to-service-ids"]
    D -->|Có| E{"DiscoveryClient thấy stub instance?"}
    E -->|Không| U["Kiểm tra Stub Runner Spring Cloud"]
    E -->|Có| F{"HTTP client dùng LoadBalancer?"}
    F -->|Không| V["Kiểm tra Feign/RestTemplate/WebClient"]
    F -->|Có| G{"Request match stub mapping?"}
    G -->|Không| W["Xem method/url/header/body"]
    G -->|Có| H["Assert hành vi consumer và ghi bằng chứng"]
~~~

Quy trình này giúp tránh lỗi phổ biến: thấy HTTP 404 rồi sửa regex trong contract, trong khi thực tế consumer đang gọi một instance khác; hoặc sửa service ID, trong khi Stub Runner chưa từng tải đúng stub JAR.

### Một test tốt cần kiểm tra gì?

1. **Danh tính artifact:** Stub Runner tải đúng JAR `1.4.2`, không dùng version động hay JAR từ cache không kiểm soát.
2. **Định danh logic:** Service ID `orders-api` có instance khi test chạy.
3. **URI thực tế:** Instance chọn bởi load balancer thực sự trỏ tới stub server của test, không trỏ môi trường khác.
4. **HTTP mapping:** Request mà consumer phát ra match scenario contract.
5. **Kết quả consumer:** Consumer áp dụng response đúng; ví dụ Checkout hiển thị/truyền trạng thái `PAID` theo yêu cầu.

Chỉ khẳng định một cách mơ hồ “Stub Runner started” là chưa đủ.

## 16. CI và khả năng tương thích giữa các phiên bản

Giả sử producer `order-service:1.5.0` sẽ đổi cấu trúc response và phát hành stub mới. Consumer Checkout vẫn đang gọi `orders-api` bằng Feign.

Nếu CI của Checkout dùng:

~~~text
com.example.orders:order-contract-stubs:1.4.2:stubs
~~~

thì CI PASS chỉ có nghĩa Checkout tương thích với các tình huống của **stub 1.4.2** đã được kiểm thử. Nó **không chứng minh** Checkout tương thích với producer `1.5.0`.

Release gate nên liên kết:

~~~yaml
# Mẫu biên bản CI do nhóm tự thiết kế;
# không phải output mặc định của Spring Cloud Contract.
producer_revision: "order-service@abc123"
contract_revision: "contracts@def456"
stub_artifact: "com.example.orders:order-contract-stubs:1.5.0:stubs"
consumer_version: "checkout-service:2.8.0"
service_id: orders-api
stub_discovery_instance_verified: true
actual_consumer_call_verified: true
producer_contract_tests: PASS
consumer_stub_tests: PASS
~~~

Trong CI, nên:

- Chỉ phát hành stub mới từ producer build mà **generated producer tests** đã thực sự chạy PASS.
- Chốt version và checksum artifact nếu chính sách repository cho phép.
- Tải đúng stub version trước khi chạy consumer tests.
- Kiểm tra mapping artifact → service ID và việc định tuyến qua client thực.
- Ngăn fallback âm thầm tới service staging/production.
- Ghi rõ consumer versions và các kịch bản đã kiểm tra.

**Bằng chứng tương thích luôn có phạm vi.** Stub Runner + discovery mapping kiểm tra được cách consumer sử dụng tên dịch vụ trong môi trường test, nhưng không tự kiểm chứng cấu hình Eureka/Consul/Kubernetes thực của production, authentication, TLS hay khả năng chịu tải.

## 17. Bài tập thực hành

### Bài tập A — Điền mapping

Producer publish artifact:

~~~text
com.example.inventory:inventory-contracts:3.2.1:stubs
~~~

Consumer gọi `http://inventory-api/api/stock/SKU-1001` bằng một RestTemplate có load balancing.

**Yêu cầu:** viết cấu hình YAML cho `ids-to-service-ids`, xác định đâu là artifact ID và đâu là service ID.

**Gợi ý:**

~~~yaml
spring:
  cloud:
    contract:
      stubrunner:
        ids-to-service-ids:
          inventory-contracts: inventory-api
~~~

### Bài tập B — Dịch vụ không được tìm thấy

Stub Runner khởi động stub Order ở port `11021`. `DiscoveryClient.getInstances("orders-api")` trả về danh sách rỗng. Feign vẫn được cấu hình `name = "orders-api"`.

**Yêu cầu:** liệt kê thứ tự kiểm tra từ artifact ID đến map, classpath và auto-configuration. Giải thích vì sao port 11021 không tự giúp Feign tìm được dịch vụ.

**Gợi ý:** port là địa chỉ stub thực; Feign tìm theo service ID. Cần mapping và tích hợp DiscoveryClient/LoadBalancer.

### Bài tập C — Client không load-balanced

Một developer cấu hình map đúng, `DiscoveryClient` nhìn thấy `inventory-api` nhưng `new RestTemplate()` vẫn báo lỗi DNS khi gọi `http://inventory-api`.

**Yêu cầu:** chẩn đoán vấn đề và đề xuất cách cấu hình client.

**Gợi ý:** sử dụng `@LoadBalanced RestTemplate` hoặc một client thật sự tích hợp Spring Cloud LoadBalancer; map không tự sửa RestTemplate tạo bằng `new`.

### Bài tập D — Trùng service ID

Hai artifact `order-contract-stubs` và `billing-contract-stubs` đều bị map sang `orders-api`. Các test có lúc nhận mapping của Billing.

**Yêu cầu:** thiết kế lại map và nêu cách xác minh danh sách instance/route bằng test.

**Gợi ý:** đặt service ID phân biệt `orders-api` và `billing-api` theo tên consumer thực sự dùng; kiểm tra từng client, từng endpoint.

### Bài tập E — Không gọi dịch vụ production

Consumer có DiscoveryClient thật trong classpath. Một số lần chạy CI thử `orders-api`, request bất ngờ được gửi tới staging.

**Yêu cầu:** đề xuất chính sách cô lập discovery và kiểm chứng instance URI, đồng thời nêu giới hạn của tùy chọn delegate.

**Gợi ý:** không cho phép merge/fallback ngoài ý muốn; kiểm tra cờ Stub Runner Spring Cloud theo phiên bản và assert mọi instance được chọn đều thuộc hạ tầng stub của test.

### Bài tập F — So sánh bằng chứng phiên bản

Order Service 1.5.0 đã đổi field `status` thành `paymentStatus`, nhưng Checkout 2.8.0 vẫn PASS với stub 1.4.2.

**Yêu cầu:** đánh giá tuyên bố tương thích và đề xuất release gate sử dụng đúng stub mới, đúng service ID.

**Gợi ý:** producer 1.5.0 phải được kiểm tra với hợp đồng mới; consumer 2.8.0 phải chạy với stub của build mới và gọi qua `orders-api`. PASS trên stub 1.4.2 không giải quyết câu hỏi đó.

## 18. Checklist khi ánh xạ stub artifact sang service ID

- [ ] Đã xác định đúng `groupId`, `artifactId`, `version` và `classifier` của stub JAR.
- [ ] Đã xác định **service ID mà consumer thực sự dùng**, không suy từ tên package của producer.
- [ ] Nếu hai tên khác nhau, cấu hình `ids-to-service-ids` theo chiều **artifact → service ID**.
- [ ] Nếu nhiều artifact có cùng artifactId, dùng khóa đủ rõ để tránh nhập nhằng.
- [ ] Stub Runner tải đúng artifact từ LOCAL/REMOTE/CLASSPATH theo cấu hình đã chọn.
- [ ] Stub HTTP server khởi động thành công; cổng của stub có thể khác nhau giữa các lần chạy.
- [ ] Tích hợp Stub Runner Spring Cloud và DiscoveryClient/LoadBalancer thực sự được bật.
- [ ] `DiscoveryClient.getInstances(serviceId)` trả về instance đúng theo kịch bản.
- [ ] Feign, RestTemplate hoặc WebClient được cấu hình **load-balanced** khi gọi bằng service ID.
- [ ] Không có instance staging/production bị chọn ngoài ý muốn trong consumer CI.
- [ ] Không nhầm HTTP service ID với message destination `sentTo` hoặc label của message stub.
- [ ] Consumer test thực sự gửi request qua service ID và assert kết quả nghiệp vụ.
- [ ] Producer contract tests đã chạy PASS với build liên quan đến stub artifact.
- [ ] Consumer CI dùng **stub version mới** khi đánh giá tương thích với producer mới.
- [ ] Báo cáo CI ghi rõ artifact, contract revision, service ID và các consumer versions đã xác minh.

**Ghi nhớ:** `artifactId` giúp Stub Runner **tìm đúng JAR**, còn `serviceId` giúp ứng dụng consumer **tìm đúng HTTP stub instance**. Khi hai tên khác nhau, dùng `ids-to-service-ids` để nối chúng; đồng thời bảo đảm HTTP client có tích hợp discovery/load balancing và CI không vô tình gọi dịch vụ thật. Một ánh xạ đúng chỉ là điều kiện để consumer test đến đúng stub; bằng chứng tương thích còn cần generated producer tests, mapping chuẩn và consumer assertions trên đúng phiên bản artifact.

## Tài liệu tham khảo

- [Spring Cloud Contract — Stub Runner Spring Cloud](https://docs.spring.io/spring-cloud-contract/reference/project-features-stubrunner/stub-runner-cloud.html): tích hợp `DiscoveryClient`, load balancer và mapping `idsToServiceIds`.
- [Spring Cloud Contract — Configuration Properties](https://docs.spring.io/spring-cloud-contract/reference/configprops.html): các property `ids-to-service-ids`, `cloud.enabled` và `cloud.loadbalancer.enabled`.
- [Spring Cloud Contract — Common Properties](https://docs.spring.io/spring-cloud-contract/reference/project-features-stubrunner/stub-runner-common.html): cú pháp Stub Runner IDs và nguồn tải stubs.

**Lưu ý phiên bản:** ví dụ trong bài trình bày cách hoạt động và cấu hình thường dùng; trước khi áp dụng vào dự án thật, cần đối chiếu tài liệu với Spring Cloud Contract/Spring Cloud/Spring Boot versions đã khóa trong build và kiểm tra generated behavior thực tế.
