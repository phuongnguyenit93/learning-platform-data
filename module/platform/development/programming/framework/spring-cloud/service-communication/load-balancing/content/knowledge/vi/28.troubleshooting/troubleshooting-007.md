# Cấu hình theo client không có hiệu lực hoặc áp dụng nhầm dịch vụ

Một ứng dụng Order Service có thể gọi đồng thời **inventory-service**, **payment-service** và **catalog-service** qua Spring Cloud LoadBalancer. Nhóm phát triển muốn Inventory dùng **RandomLoadBalancer**, Payment giữ **RoundRobinLoadBalancer**, Inventory có health-check riêng và timeout khác Payment. Tuy nhiên, sau khi triển khai, cả ba client lại dùng cùng một policy; hoặc cấu hình riêng của Inventory dường như không có tác dụng. Một trường hợp khác là thay đổi dành cho Inventory vô tình áp dụng cho Payment.

Những lỗi này thường không nằm ở thuật toán cân bằng tải. Nguyên nhân hay gặp là **service ID không khớp**, **LoadBalancer child context bị cấu hình sai**, class cấu hình bị component-scan vào parent context, bean HTTP client không được đánh dấu **@LoadBalanced**, một URL cố định làm Feign bypass LoadBalancer, hoặc property nằm sai prefix/đang bị nguồn cấu hình ưu tiên cao hơn ghi đè.

Bài học thuộc chương **Chẩn đoán sự cố** của module **SPRING_CLOUD_SERVICE_COMMUNICATION_LOAD_BALANCING**. Ta sẽ đi từ triệu chứng đến bằng chứng, phân biệt **LoadBalancer client context**, **HTTP client bean** và **Feign named-client context**, kiểm tra từng tích hợp RestTemplate/RestClient/WebClient/OpenFeign, xác minh cấu hình theo service ID, đọc effective properties an toàn, kiểm thử cách ly giữa các client và lập runbook sửa lỗi.

> **Phạm vi:** Các ví dụ dựa trên Spring Cloud Commons/LoadBalancer và Spring Cloud OpenFeign hiện hành. API/package có thể thay đổi theo release train; dùng Spring Boot–Spring Cloud BOM tương thích. Không suy luận rằng mọi property có thể override theo client: có một số property chỉ có hiệu lực toàn cục, được nêu riêng trong bài.

## 1. Nhận diện đúng triệu chứng

Trước khi thay code, phân loại hiện tượng:

| Triệu chứng | Câu hỏi đầu tiên |
| --- | --- |
| Inventory vẫn dùng Round Robin dù đã cấu hình Random | Child context của **inventory-service** có tạo RandomLoadBalancer không? |
| Inventory và Payment đều bị đổi sang Random | Cấu hình Inventory có lọt vào parent context hoặc một cấu hình global không? |
| Chỉ RestClient không có tác dụng | Builder đang inject có thật sự được đánh dấu **@LoadBalanced** không? |
| WebClient không chọn instance | Builder có filter LoadBalancer hay code đang dùng **WebClient.create()** trực tiếp? |
| Feign gọi một host cố định | Có thuộc tính **url** trong @FeignClient hoặc **spring.cloud.openfeign.client.config.*.url** không? |
| Feign config của Inventory ảnh hưởng Feign client khác | Config class có bị component scan thành global bean không? |
| Property theo client không thay đổi kết quả | Prefix **spring.cloud.loadbalancer.clients.<serviceId>** đúng chưa, property đó có hỗ trợ per-client không? |
| Local đúng, production sai | Profile, env var, command line, Config Server hoặc ConfigMap có ghi đè không? |
| Cấu hình chỉ có hiệu lực sau lần gọi đầu | LoadBalancer child context có được khởi tạo lazy và giữ bean đã tạo không? |
| Đổi service ID ở một nơi nhưng registry không tìm thấy | URI host, @LoadBalancerClient name, Feign name và discovery ID có đồng nhất không? |

**Quy tắc chẩn đoán:** xác minh request đang đi qua client nào, service ID nào, context nào và bean nào trước khi sửa thuật toán.

## 2. Ba loại “client context” rất dễ nhầm

Spring Cloud có nhiều phạm vi cấu hình cùng xuất hiện trong một ứng dụng:

~~~mermaid
flowchart TD
    P["Order Service: parent ApplicationContext"] --> LB1["LoadBalancer child context\ninventory-service"]
    P --> LB2["LoadBalancer child context\npayment-service"]
    P --> FEIGN["Feign named-client context\ninventoryReadClient"]
    P --> FEIGN2["Feign named-client context\npaymentClient"]
    P --> HTTP["HTTP client beans\nRestClient / WebClient / Feign transport"]
    LB1 --> S1["Supplier + ReactorLoadBalancer + policy"]
    LB2 --> S2["Supplier + ReactorLoadBalancer + policy"]
    FEIGN --> S3["Decoder / Encoder / Contract / Interceptors"]
    FEIGN2 --> S4["Decoder / Encoder / Contract / Interceptors"]
    HTTP --> S5["Connection pool / TLS / timeout"]
~~~

### 2.1. LoadBalancer child context

Spring Cloud LoadBalancer tạo **một Spring child ApplicationContext cho mỗi service ID**. Ví dụ inventory-service và payment-service có hai context riêng để cung cấp:

- ReactorLoadBalancer<ServiceInstance>: chọn instance.
- ServiceInstanceListSupplier: lấy/lọc danh sách instance.
- Các bean liên quan đến policy, retry-aware selection, health/zone/cache theo cấu hình.

Context thường được **khởi tạo lazy ở request đầu tiên** của service ID đó. Việc một bean xuất hiện trong context của Inventory không có nghĩa bean đó sẽ tự xuất hiện trong context Payment.

### 2.2. Feign named-client context

Spring Cloud OpenFeign cũng tạo một **named client ensemble** riêng cho từng Feign client, chứa Decoder, Encoder, Contract, Client và các bean tùy biến. Tên contextId có thể tách cấu hình cho hai Feign interfaces cùng gọi một service.

Đây là context của **Feign client configuration**, không phải cùng một khái niệm với child context của Spring Cloud LoadBalancer. Một Feign client vẫn cần service ID/LoadBalancer integration riêng khi muốn chọn backend.

### 2.3. HTTP client bean/context

RestClient, RestTemplate, WebClient và transport bên dưới Feign có vòng đời riêng: builder, filter/interceptor, connection pool, TLS và timeout. Một bean HTTP client được tạo trong parent context có thể được dùng để gọi nhiều service IDs; **@LoadBalancerClient không tự tạo một RestClient riêng cho mỗi service ID**.

Vì vậy, cần xác định chính xác yêu cầu thuộc lớp nào:

| Muốn thay đổi | Phạm vi cần cấu hình |
| --- | --- |
| Thuật toán chọn Inventory | LoadBalancer child context của inventory-service |
| Danh sách instance/health/zone riêng Inventory | ServiceInstanceListSupplier trong child context hoặc per-client properties |
| Decoder/Retryer/RequestInterceptor của Feign Inventory | Feign named-client context |
| Connect/read timeout của Feign Inventory | Feign client properties hoặc Request.Options/client transport |
| TLS truststore cho một RestClient | HTTP connector/request factory và SSL bundle của client đó |
| Header trace chung cho mọi request | Interceptor/filter global có chủ đích |

## 3. Sơ đồ chẩn đoán nhanh

~~~mermaid
flowchart TD
    A["Request không dùng đúng cấu hình"] --> B{"Client nào?"}
    B -->|RestClient / RestTemplate| C["Kiểm tra @LoadBalanced builder/template"]
    B -->|WebClient| D["Kiểm tra @LoadBalanced builder hoặc LB filter"]
    B -->|OpenFeign| E["Kiểm tra starter, @FeignClient name và url"]
    C --> F{"URI host có đúng service ID?"}
    D --> F
    E --> F
    F -->|Không| G["Sửa logical service ID"]
    F -->|Có| H["Kiểm tra @LoadBalancerClient mapping"]
    H --> I{"Child context đúng config?"}
    I -->|Không| J["Kiểm tra component scan / annotation / package"]
    I -->|Có| K["Kiểm tra clients.<serviceId> property prefix"]
    K --> L["Kiểm tra property toàn cục và precedence"]
    L --> M["Kiểm tra supplier chain / bean override"]
    M --> N["Test từng service ID và HTTP request thực"]
~~~

Làm theo thứ tự này để không mất thời gian sửa RandomLoadBalancer trong khi request thực tế đang gọi URL cố định.

## 4. Bước 1 — xác định service ID thật của request

Trong LoadBalancer, **service ID** thường được lấy từ host trong logical URI của HTTP request hoặc từ tên của Feign client.

Ví dụ:

~~~java
restClient.get()
        .uri("http://inventory-service/api/stock/{sku}", sku)
        .retrieve()
        .body(StockResponse.class);
~~~

Service ID ở đây là **inventory-service**.

Với WebClient:

~~~java
webClient.get()
        .uri("http://payment-service/api/payments/{id}", id)
        .retrieve()
        .bodyToMono(PaymentResponse.class);
~~~

Service ID là **payment-service**.

Với OpenFeign:

~~~java
@FeignClient(name = "catalog-service")
interface CatalogClient {
    @GetMapping("/api/products/{id}")
    ProductResponse find(@PathVariable("id") String id);
}
~~~

Tên client được dùng để tạo LoadBalancer client là **catalog-service**.

### 4.1. Tên ở @LoadBalancerClient phải khớp service ID

~~~java
@LoadBalancerClient(
        name = "inventory-service",
        configuration = InventoryLoadBalancerConfiguration.class)
class LoadBalancerRegistration {
}
~~~

Nếu request dùng http://inventory-service/... nhưng annotation đăng ký name = "inventory", cấu hình tùy chỉnh được gắn vào **inventory**, còn request lại tìm context **inventory-service**. Kết quả thường là cấu hình mặc định được dùng cho request thật.

Kiểm tra từng giá trị:

| Nơi khai báo | Giá trị cần đối chiếu |
| --- | --- |
| URI host của RestClient/RestTemplate | inventory-service |
| URI host của WebClient | inventory-service |
| @FeignClient(name=...) | inventory-service |
| @LoadBalancerClient(name=...) | inventory-service |
| SimpleDiscoveryClient/registry service ID | inventory-service |
| spring.cloud.loadbalancer.clients.<clientId> | inventory-service |

**Không dựa vào tên biến Java hoặc tên bean** để suy ra service ID. Tên inventoryClient, inventoryRestClient hay inventoryReadClient không tự trở thành service ID.

### 4.2. Phân biệt service ID và instance ID

- **Service ID**: tên logic của cả dịch vụ, ví dụ inventory-service.
- **Instance ID**: định danh một bản sao, ví dụ inventory-a.
- **Host/port**: địa chỉ vật lý của instance, ví dụ 10.2.1.8:8080.

@LoadBalancerClient(name=...) nhận **service ID**, không nhận instance ID hoặc hostname của một pod cụ thể. Nếu cấu hình name="inventory-a" trong khi URL host là inventory-service, LoadBalancer không dùng context đó cho request.

## 5. Bước 2 — kiểm tra cấu hình tùy chỉnh có được gắn vào đúng child context không

Một cấu hình LoadBalancer theo service:

~~~java
package com.example.order.lb.inventory;

import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.loadbalancer.core.RandomLoadBalancer;
import org.springframework.cloud.loadbalancer.core.ReactorLoadBalancer;
import org.springframework.cloud.loadbalancer.core.ServiceInstanceListSupplier;
import org.springframework.cloud.loadbalancer.support.LoadBalancerClientFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.Environment;

// Không bắt buộc gắn @Configuration nếu class được import
// trực tiếp qua @LoadBalancerClient.
public class InventoryLoadBalancerConfiguration {

    @Bean
    ReactorLoadBalancer<ServiceInstance> inventoryLoadBalancer(
            Environment environment,
            LoadBalancerClientFactory factory) {

        String serviceId = environment.getProperty(
                LoadBalancerClientFactory.PROPERTY_NAME);

        return new RandomLoadBalancer(
                factory.getLazyProvider(
                        serviceId, ServiceInstanceListSupplier.class),
                serviceId);
    }
}
~~~

Đăng ký:

~~~java
@SpringBootApplication
@LoadBalancerClient(
        name = "inventory-service",
        configuration = InventoryLoadBalancerConfiguration.class)
public class OrderApplication {
}
~~~

Đoạn code minh họa cách lấy **service ID của child context hiện tại** qua LoadBalancerClientFactory.PROPERTY_NAME. Khi cấu hình dùng cho nhiều service IDs, không hardcode "inventory-service" vào implementation của bean; nếu hardcode, cùng một class có thể tạo selector tham chiếu nhầm supplier.

### 5.1. Lỗi phổ biến: cấu hình con bị component-scan vào parent

Một class như sau có thể gây tác động ngoài ý muốn:

~~~java
package com.example.order;

@Configuration
public class InventoryLoadBalancerConfiguration {

    @Bean
    ReactorLoadBalancer<ServiceInstance> inventoryLoadBalancer(...) {
        // ...
    }
}
~~~

Nếu class nằm trong phạm vi @SpringBootApplication/@ComponentScan của ứng dụng chính, bean có thể được đăng ký ở **parent ApplicationContext**. Trong khi đó, Spring Cloud LoadBalancer mong cấu hình truyền qua @LoadBalancerClient là cấu hình cho **child context**.

Tài liệu Spring Cloud yêu cầu class được truyền vào **@LoadBalancerClient** hoặc **@LoadBalancerClients**:

- không cần gắn @Configuration; **hoặc**
- nếu gắn @Configuration, phải nằm ngoài phạm vi component scan.

Một cách tổ chức dễ hiểu:

~~~text
com.example.order
  OrderApplication.java
  client/
    InventoryClient.java
  service/
    OrderService.java

com.example.order.lbconfig
  InventoryLoadBalancerConfiguration.java
  PaymentLoadBalancerConfiguration.java
~~~

Nếu lbconfig vẫn nằm dưới package gốc được scan, chỉ đổi folder chưa đủ. Đặt package cấu hình ngoài scan hoặc loại trừ nó khỏi component scan.

### 5.2. Cấu hình không có @Configuration vẫn có @Bean không?

Có. Khi class được đăng ký thông qua **configuration class argument** của @LoadBalancerClient, Spring xử lý các phương thức @Bean của class đó. Đây là mẫu trong tài liệu Spring Cloud. Không cần tự import class đó vào parent chỉ để @Bean được nhận diện.

### 5.3. Cấu hình toàn cục và cấu hình từng service

Nếu muốn nhiều client có policy riêng:

~~~java
@Configuration(proxyBeanMethods = false)
@LoadBalancerClients({
        @LoadBalancerClient(
                name = "inventory-service",
                configuration = InventoryLoadBalancerConfiguration.class),
        @LoadBalancerClient(
                name = "payment-service",
                configuration = PaymentLoadBalancerConfiguration.class)
})
class ServiceLoadBalancerRegistrations {
}
~~~

Class đăng ký annotation này có thể ở parent configuration; **hai class cấu hình được truyền vào** vẫn phải tuân thủ quy tắc không component-scan như trên.

## 6. Bước 3 — phân biệt cấu hình riêng với cấu hình global

Spring Cloud LoadBalancer hỗ trợ prefix:

~~~yaml
spring:
  cloud:
    loadbalancer:
      cache:
        ttl: 35s
      health-check:
        initial-delay: 1s
      clients:
        inventory-service:
          cache:
            ttl: 10s
          health-check:
            interval: 15s
        payment-service:
          cache:
            ttl: 30s
          health-check:
            interval: 45s
~~~

Các giá trị mặc định ở namespace **spring.cloud.loadbalancer.*** được merge với giá trị theo client; giá trị riêng client có ưu tiên cao hơn cho những property được hỗ trợ.

Ví dụ:

| Property | Giá trị chung | Inventory | Payment |
| --- | --- | --- | --- |
| cache.ttl | 35s | 10s | 30s |
| health-check.initial-delay | 1s | Kế thừa 1s | Kế thừa 1s |
| health-check.interval | 25s (mặc định) | 15s | 45s |

Không phải mọi property đều hỗ trợ per-client theo cùng cách. Đặc biệt, tài liệu Spring Cloud hiện hành nêu một số property **toàn cục**:

| Property toàn cục | Hành vi quan trọng |
| --- | --- |
| spring.cloud.loadbalancer.enabled | Bật/tắt LoadBalancer cho toàn ứng dụng |
| spring.cloud.loadbalancer.retry.enabled | Bật/tắt retry toàn cục; nếu global đã bật, có thể tắt retry ở client cụ thể, nhưng không thể dùng per-client để bật khi global tắt |
| spring.cloud.loadbalancer.cache.enabled | Bật/tắt cache toàn cục; nếu global tắt, không thể chỉ bật lại bằng client prefix thông thường |
| spring.cloud.loadbalancer.stats.micrometer.enabled | Bật/tắt metrics LoadBalancer toàn cục |

**Ví dụ sai về kỳ vọng:**

~~~yaml
spring:
  cloud:
    loadbalancer:
      retry:
        enabled: false
      clients:
        inventory-service:
          retry:
            enabled: true
~~~

Không nên kỳ vọng Inventory tự bật retry nếu global retry đã tắt. Tài liệu mô tả chiều override được hỗ trợ là **global bật, client cụ thể tắt**; không phải client có thể đảo ngược mọi cờ toàn cục.

### 6.1. Các map properties có quy tắc tương thích riêng

Một số cấu hình vốn là map theo service ID, ví dụ:

~~~yaml
spring:
  cloud:
    loadbalancer:
      health-check:
        path:
          default: /actuator/health
          inventory-service: /actuator/health/readiness
      hints:
        inventory-service: canary
~~~

Với các map như **hints** hoặc **health-check.path**, Spring Cloud giữ cách khai báo theo service ID trực tiếp để tương thích ngược. Không tự chuyển tất cả map này vào **clients.inventory-service** chỉ vì các property khác dùng prefix clients.

Khi nghi ngờ sai prefix, kiểm tra **Configuration Properties Reference đúng release train**, không dựa vào autocomplete hoặc một bài blog cũ.

### 6.2. Không dùng tên bean làm key property

Key trong:

~~~yaml
spring:
  cloud:
    loadbalancer:
      clients:
        inventory-service:
          cache:
            ttl: 10s
~~~

là **service ID inventory-service**. Không phải tên biến Java inventoryRestClient, tên bean inventoryClient, hay Feign interface InventoryFeignClient.

## 7. Bước 4 — kiểm tra property precedence và giá trị runtime

Một property đúng prefix vẫn có thể không tạo kết quả mong đợi vì nguồn ưu tiên cao hơn ghi đè.

Ví dụ:

~~~text
application.yml:
  spring.cloud.loadbalancer.clients.inventory-service.cache.ttl = 10s

application-prod.yml:
  spring.cloud.loadbalancer.clients.inventory-service.cache.ttl = 30s

Deployment environment:
  SPRING_CLOUD_LOADBALANCER_CLIENTS_INVENTORY_SERVICE_CACHE_TTL = 45s
~~~

Trong production, giá trị từ environment có thể thắng file profile theo thứ tự PropertySource của Spring Boot. Đừng kết luận YAML không hoạt động khi chưa kiểm tra giá trị cuối cùng.

### 7.1. Danh sách nguồn ghi đè thường gặp

- Profile-specific file, ví dụ application-prod.yml.
- File cấu hình ngoài JAR hoặc spring.config.import.
- Environment variables từ Deployment/ConfigMap.
- Java system properties (-D...).
- Command-line arguments (--spring.cloud...).
- Test properties hoặc DynamicPropertySource trong integration test.
- Config Server/Kubernetes PropertySource nếu được tích hợp.

Khi kiểm tra, ghi lại **tên nguồn** và giá trị đã được sanitization; không dump toàn bộ Environment chứa credentials.

### 7.2. Kiểm tra Environment an toàn

Trong môi trường test có thể xác minh:

~~~java
@Autowired
Environment environment;

@Test
void inventoryClientPropertyIsPresent() {
    assertEquals(
            Duration.ofSeconds(10),
            environment.getProperty(
                    "spring.cloud.loadbalancer.clients.inventory-service.cache.ttl",
                    Duration.class));
}
~~~

Test này chỉ xác minh **Environment có property đã bind**, không chứng minh supplier trong child context thật sự dùng cache 10 giây. Cần test bean/supplier hoặc quan sát hành vi HTTP/discovery để xác nhận phần còn lại.

### 7.3. Actuator env/configprops phải được bảo vệ

Actuator có thể giúp kiểm tra property đã bind, nhưng không expose endpoint env/configprops công khai. Cấu hình sanitization và authentication/authorization theo chính sách. Không in client secret, API key, token hoặc private key vào logs để kiểm tra một property khác.

## 8. Bước 5 — xác minh child context được tạo đúng service ID

LoadBalancer child contexts mặc định được tạo **lazy** khi lần đầu có request load-balanced cho service ID. Nếu chỉ nhìn startup logs và chưa có request Inventory, có thể bạn chưa quan sát thấy context Inventory.

Có thể chủ động eager-load các service quan trọng:

~~~yaml
spring:
  cloud:
    loadbalancer:
      eager-load:
        clients:
          - inventory-service
          - payment-service
~~~

Eager-load chỉ khởi tạo context sớm; **không sửa sai service ID, không tự tạo discovery provider và không làm URL cố định chuyển thành load-balanced**.

### 8.1. Kiểm tra bean theo context trong test

Trong một Spring Boot integration test, inject **LoadBalancerClientFactory** và kiểm tra bean theo service ID:

~~~java
@SpringBootTest
class LoadBalancerClientContextTest {

    @Autowired
    LoadBalancerClientFactory factory;

    @Test
    void inventoryHasLoadBalancerAndSupplier() {
        ReactorLoadBalancer<?> loadBalancer =
                factory.getInstance(
                        "inventory-service", ReactorLoadBalancer.class);
        ServiceInstanceListSupplier supplier =
                factory.getInstance(
                        "inventory-service",
                        ServiceInstanceListSupplier.class);

        assertNotNull(loadBalancer);
        assertNotNull(supplier);
    }
}
~~~

Các imports tùy release train gồm **LoadBalancerClientFactory**, **ReactorLoadBalancer**, **ServiceInstanceListSupplier**, Spring Boot Test và JUnit. Test trên chứng minh **bean tồn tại trong context có tên service ID**, chưa chứng minh bean là implementation tùy chỉnh mong đợi hoặc request thật dùng context đó.

Nếu cần xác minh implementation, assert class cụ thể trong một test gắn với phiên bản đã chọn, ví dụ RandomLoadBalancer. Không ép assert class cụ thể vào test dùng chung qua nhiều release train nếu default implementation có thể thay đổi.

### 8.2. So sánh hai child contexts

~~~java
@Test
void inventoryAndPaymentHaveDifferentSuppliers() {
    ServiceInstanceListSupplier inventory =
            factory.getInstance(
                    "inventory-service",
                    ServiceInstanceListSupplier.class);
    ServiceInstanceListSupplier payment =
            factory.getInstance(
                    "payment-service",
                    ServiceInstanceListSupplier.class);

    assertNotNull(inventory);
    assertNotNull(payment);
    assertNotSame(inventory, payment);
}
~~~

**Không phải mọi ứng dụng đều bắt buộc hai supplier có class khác nhau**; test chỉ minh họa hai context tách biệt. Nếu cả hai cùng dùng DiscoveryClientServiceInstanceListSupplier, class type giống nhau vẫn đúng. Điều cần xác minh là **configuration và instance lists của mỗi context** tương ứng service ID.

## 9. Bước 6 — kiểm tra @LoadBalanced ở đúng HTTP client

Ngay cả khi child context đã cấu hình đúng, request vẫn có thể không đi qua LoadBalancer nếu HTTP client không được tích hợp.

Trước hết kiểm tra dependency **spring-cloud-starter-loadbalancer** có trong runtime classpath và được quản lý bởi Spring Cloud BOM tương thích. RestClient load-balancing được hỗ trợ ở các dòng Spring Boot/Spring Cloud tương ứng; nếu dự án dùng phiên bản cũ, không áp dụng snippet của dòng mới mà không kiểm tra API integration.

### 9.1. RestClient

~~~java
@Configuration(proxyBeanMethods = false)
class InventoryHttpClientConfiguration {

    @Bean
    @LoadBalanced
    RestClient.Builder loadBalancedRestClientBuilder() {
        return RestClient.builder();
    }

    @Bean
    RestClient inventoryRestClient(
            @LoadBalanced RestClient.Builder builder) {
        return builder
                .baseUrl("http://inventory-service")
                .build();
    }
}
~~~

Kiểm tra:

- Bean builder có annotation **@LoadBalanced** không?
- Bean RestClient được build từ đúng builder đã đánh dấu không?
- Nếu có nhiều RestClient.Builder, constructor/method injection có qualifier **@LoadBalanced** không?
- URI host có phải service ID không?
- Có code nào gọi một RestClient khác không?

Một builder thường và một builder @LoadBalanced có thể cùng tồn tại. Nếu inject nhầm builder thường, request tới inventory-service có thể bị DNS resolver xử lý như hostname bình thường và báo UnknownHostException.

### 9.2. RestTemplate

~~~java
@Bean
@LoadBalanced
RestTemplate inventoryRestTemplate() {
    return new RestTemplate();
}
~~~

Nếu ứng dụng có cả RestTemplate thường và RestTemplate load-balanced, dùng **@Qualifier** hoặc tên bean rõ ràng khi inject. Đừng đổi một bean global thành @LoadBalanced chỉ để sửa một caller, nếu các nơi khác cần gọi host trực tiếp.

### 9.3. WebClient

~~~java
@Bean
@LoadBalanced
WebClient.Builder loadBalancedWebClientBuilder() {
    return WebClient.builder();
}

@Bean
WebClient inventoryWebClient(
        @LoadBalanced WebClient.Builder builder) {
    return builder
            .baseUrl("http://inventory-service")
            .build();
}
~~~

Các lỗi thường gặp:

- Gọi **WebClient.create()** hoặc **WebClient.builder()** trực tiếp thay vì builder được tích hợp LoadBalancer.
- Tự thêm ReactorLoadBalancerExchangeFilterFunction trong khi builder đã được auto-configure filter đó.
- Tạo WebClient từ một builder khác không có @LoadBalanced.
- Dùng URI http://inventory-a.internal (host instance cố định) thay vì service ID.

Có thể cấu hình WebClient thủ công với **ReactorLoadBalancerExchangeFilterFunction**, nhưng phải chọn **một cách tích hợp có chủ đích** và kiểm tra filter chỉ được thêm một lần.

### 9.4. Không dùng một qualifier cho nhầm loại builder

@LoadBalanced là qualifier marker cho các bean được tích hợp tương ứng. Một bean RestClient.Builder được đánh dấu không làm WebClient.Builder tự load-balance, và ngược lại. Kiểm tra đúng **loại bean + qualifier + client instance** đang được sử dụng.

## 10. Bước 7 — OpenFeign: kiểm tra starter, name, url và contextId

OpenFeign cần dependency **spring-cloud-starter-loadbalancer** để có FeignBlockingLoadBalancerClient. Starter OpenFeign không bắt buộc kéo LoadBalancer vào mọi ứng dụng vì dependency này là optional.

Ví dụ load-balanced Feign:

~~~java
@EnableFeignClients(basePackages = "com.example.order.clients")
@SpringBootApplication
class OrderApplication {
}

@FeignClient(
        name = "inventory-service",
        contextId = "inventoryReadClient")
interface InventoryFeignClient {

    @GetMapping("/api/stock/{sku}")
    StockResponse findStock(@PathVariable("sku") String sku);
}
~~~

Kiểm tra:

1. Có **spring-cloud-starter-openfeign** và **spring-cloud-starter-loadbalancer** tương thích không?
2. Có **@EnableFeignClients** quét đúng package hoặc khai báo đúng client classes không?
3. **name** có khớp service ID trong discovery không?
4. Có URL cố định trong annotation hoặc properties không?
5. Config class có vô tình bị component scan thành default config cho tất cả Feign clients không?

### 10.1. URL cố định làm Feign bypass LoadBalancer

Theo Spring Cloud OpenFeign, các trường hợp URL:

| Khai báo | Kết quả |
| --- | --- |
| @FeignClient(name="inventory-service") | Dùng name làm service ID, có LoadBalancer |
| @FeignClient(name="inventory-service", url="http://localhost:8081") | Dùng URL annotation, không load-balance |
| Annotation không có url, nhưng property spring.cloud.openfeign.client.config.inventory-service.url có giá trị | Dùng URL property, không load-balance |
| Annotation có url và property cũng có url | URL trong annotation được dùng; property URL không có tác dụng |

**Một URL được cấu hình chỉ để tiện test local có thể khiến production không còn dùng service discovery.** Kiểm tra cả annotation placeholder và environment/profile properties.

### 10.2. Name và contextId có vai trò khác nhau

~~~java
@FeignClient(
        name = "inventory-service",
        contextId = "inventoryReadClient",
        configuration = InventoryFeignConfiguration.class)
interface InventoryReadClient {
}

@FeignClient(
        name = "inventory-service",
        contextId = "inventoryAdminClient",
        configuration = InventoryAdminFeignConfiguration.class)
interface InventoryAdminClient {
}
~~~

Hai Feign interfaces gọi cùng service ID **inventory-service**, nhưng có thể cần cấu hình Feign riêng. **name** định danh dịch vụ được gọi; **contextId** giúp phân biệt named-client ensemble và bean configuration khi có nhiều client cùng name.

Không đổi name thành inventoryReadClient chỉ vì muốn tách Feign configuration. Nếu làm vậy, LoadBalancer sẽ tìm service ID inventoryReadClient, có thể không tồn tại trong registry.

### 10.3. Feign configuration bị component scan thành global

Một class dùng riêng cho Inventory:

~~~java
class InventoryFeignConfiguration {

    @Bean
    RequestInterceptor inventoryAuthInterceptor() {
        return template -> template.header(
                "X-Client-Type", "inventory");
    }
}
~~~

Nếu class này bị scan vào parent context, các bean có thể trở thành cấu hình mặc định dùng cho những Feign clients khác. Tài liệu OpenFeign khuyến nghị class cấu hình riêng không cần @Configuration; nếu có annotation đó, đặt ngoài component scan hoặc loại trừ rõ ràng.

### 10.4. Property precedence của Feign

~~~yaml
spring:
  cloud:
    openfeign:
      client:
        config:
          inventoryReadClient:
            connectTimeout: 500
            readTimeout: 1500
            loggerLevel: basic
~~~

Tên key phải khớp **named client identity** theo name/value/contextId mà Feign dùng trong phiên bản đang chạy. Nếu có nhiều client cùng service ID nhưng contextId khác nhau, kiểm tra key theo contextId và test effective Request.Options.

Theo mặc định, cấu hình properties của OpenFeign có thể ghi đè bean cấu hình Java. Có thể đảo thứ tự ưu tiên bằng **spring.cloud.openfeign.client.default-to-properties=false**. Khi timeout hoặc interceptor dường như không nhận giá trị trong @Configuration, kiểm tra property override trước.

## 11. Bước 8 — kiểm tra supplier chain và bean bị override

Một LoadBalancer child context có thể dùng supplier tùy chỉnh để lấy/lọc danh sách ServiceInstance. Nếu cấu hình supplier ở sai context hoặc tạo nhiều bean không như mong muốn, policy theo client có thể không hoạt động.

### 11.1. Custom supplier bị áp dụng cho mọi service

Phản mẫu:

~~~java
@Configuration
class GlobalSupplierConfiguration {

    @Bean
    ServiceInstanceListSupplier inventorySupplier(
            ConfigurableApplicationContext context) {
        return ServiceInstanceListSupplier.builder()
                .withDiscoveryClient()
                .withCaching()
                .build(context);
    }
}
~~~

Nếu class được scan vào parent, bean có thể ảnh hưởng nhiều LoadBalancer child contexts hoặc xung đột với default configuration. Cần đặt supplier trong **cấu hình được đăng ký cho service ID cụ thể** hoặc dùng cơ chế per-client properties được hỗ trợ.

### 11.2. Đúng thứ tự supplier chain

~~~text
DiscoveryClientServiceInstanceListSupplier
        |
        v
CachingServiceInstanceListSupplier
        |
        v
ZonePreference / Hint / Filtering supplier
        |
        v
ReactorLoadBalancer.choose()
~~~

Nếu dùng **HealthCheckServiceInstanceListSupplier**, nó có cơ chế cache nội bộ dựa trên Flux replay; tài liệu khuyến nghị không bọc thêm CachingServiceInstanceListSupplier cùng lúc. Với các supplier cache/health, đặt chúng ngay sau supplier lấy dữ liệu từ mạng và trước các supplier filter khác theo hướng dẫn của release train.

### 11.3. Dùng đúng DiscoveryClient stack

Spring Cloud có thể dùng **DiscoveryClient** blocking hoặc **ReactiveDiscoveryClient**. Khi tạo supplier thủ công, phải dùng builder tương ứng với stack đang chạy. Một supplier lấy danh sách qua blocking discovery không tự xuất hiện chỉ vì WebClient là reactive, và ngược lại.

### 11.4. @ConditionalOnMissingBean và nhiều bean cùng loại

Default configuration thường tạo bean có điều kiện **@ConditionalOnMissingBean**. Nếu một bean ServiceInstanceListSupplier hoặc ReactorLoadBalancer đã tồn tại trong context, auto-configuration có thể lùi lại. Điều này hữu ích khi tùy chỉnh, nhưng một bean toàn cục vô tình được scan có thể khiến default bean trong nhiều context không được tạo như dự kiến.

Khi có nhiều bean cùng type, kiểm tra:

- Bean nằm ở parent hay child context.
- Bean nào là @Primary.
- ConditionalOnMissingBean nào match.
- Có component scan nhầm package config không.
- Có custom config class được đăng ký hai lần không.

Đừng thêm @Primary một cách mù quáng để “sửa” NoUniqueBeanDefinitionException; trước tiên xác định bean nào thuộc service ID nào.

## 12. Bước 9 — tìm cấu hình đang bị áp dụng quá rộng

Một số cơ chế cố ý áp dụng cho **mọi LoadBalancer clients**. Nếu chỉ muốn tùy chỉnh Inventory mà dùng cơ chế global, Payment và Catalog cũng sẽ bị ảnh hưởng.

### 12.1. @LoadBalancerClients defaultConfiguration

~~~java
@Configuration(proxyBeanMethods = false)
@LoadBalancerClients(
        defaultConfiguration = CommonLoadBalancerConfiguration.class)
class AllLoadBalancerClientsConfiguration {
}
~~~

Thuộc tính **defaultConfiguration** có ý nghĩa là cấu hình mặc định cho các LoadBalancer clients. Nếu cần policy riêng Inventory, đăng ký rõ bằng **@LoadBalancerClient(name="inventory-service", configuration=...)**.

### 12.2. Cấu hình property ở namespace global

~~~yaml
spring:
  cloud:
    loadbalancer:
      configurations: zone-preference
~~~

Đây là cấu hình global theo namespace mặc định. Nếu chỉ Inventory cần zone preference, hãy dùng cơ chế per-client phù hợp với release train hoặc cấu hình child context riêng. Đừng đưa cấu hình ở global rồi mong Payment không nhận ảnh hưởng.

### 12.3. Class custom configuration bị scan

Nếu class cấu hình dành riêng cho Inventory có @Configuration và nằm trong package scan của OrderApplication, nó có thể đăng ký các bean vào parent. Điều này có thể:

- làm custom ReactorLoadBalancer trở thành bean dùng chung;
- làm ServiceInstanceListSupplier default không được tạo vì @ConditionalOnMissingBean;
- làm bean/filter/interceptor của một client xuất hiện ở client khác;
- tạo lỗi nhiều bean cùng type hoặc hành vi khác nhau giữa test và production.

**Cách sửa:** đưa config class ra ngoài scan hoặc bỏ @Configuration khi truyền trực tiếp vào @LoadBalancerClient; chỉ đặt bean trong child context dành cho đúng service ID.

## 13. Bước 10 — phân biệt property không hỗ trợ per-client với property sai prefix

Khi một property không đổi hành vi, chia thành ba câu hỏi:

1. Property có tồn tại trong release train hiện tại không?
2. Property có hỗ trợ prefix clients.<clientId> không?
3. Component thực thi có thực sự đọc property đó không?

Ví dụ:

| Cấu hình | Có thể cấu hình theo client? | Ghi chú |
| --- | --- | --- |
| Cache TTL | Thường có | clients.inventory-service.cache.ttl |
| Health-check interval | Thường có | clients.inventory-service.health-check.interval |
| Retry max attempts | Thường có | Dùng prefix client theo tài liệu |
| LoadBalancer enabled | Không, global | Tắt là ảnh hưởng toàn ứng dụng |
| Retry enabled | Có giới hạn | Global off không thể được client bật lại theo chiều ngược |
| Cache enabled | Có giới hạn | Global off không thể bật lại chỉ bằng client property |
| Micrometer stats enabled | Global | Không phải cờ bật riêng client |
| Health-check path map | Dạng map theo service ID | Giữ cấu trúc trực tiếp health-check.path.inventory-service |
| Hint map | Dạng map theo service ID | Dùng cấu trúc hints.inventory-service |

### 13.1. Custom supplier có thể bỏ qua property chain

Giả sử application.yml có:

~~~yaml
spring:
  cloud:
    loadbalancer:
      clients:
        inventory-service:
          configurations: health-check
~~~

Nhưng child config lại khai báo một bean **ServiceInstanceListSupplier** tự tạo chỉ gọi DiscoveryClient mà không gắn health-check. Khi bean custom được chọn, property configurations có thể không tạo chain mà người học mong đợi.

**Đừng chỉ nhìn property.** Kiểm tra bean supplier thực tế, các delegate và thứ tự của chain. Một custom bean thay thế default chain thì phải tự chịu trách nhiệm thêm caching, health, zone hoặc hint theo nhu cầu.

### 13.2. Không bọc cache/health nhiều lần

Tài liệu Spring Cloud khuyến nghị nếu tự tạo supplier chain:

- Dùng **một** trong CachingServiceInstanceListSupplier hoặc HealthCheckServiceInstanceListSupplier theo thiết kế; không bọc cả hai tùy tiện.
- Đặt supplier cache/health ngay sau supplier lấy instance từ network.
- Đặt request-based/zone/hint filters ở phía sau theo contract.

Sai thứ tự có thể làm cache lưu kết quả đã filter theo request, hoặc health-check không nhìn thấy danh sách được cập nhật đúng cách. Hãy đọc phần supplier ordering trong reference của đúng phiên bản.

## 14. Bước 11 — xác minh cấu hình Feign không bị lẫn với LoadBalancer

Có hai bộ key cấu hình độc lập:

~~~yaml
spring:
  cloud:
    loadbalancer:
      clients:
        inventory-service:
          cache:
            ttl: 10s

    openfeign:
      client:
        config:
          inventoryReadClient:
            connectTimeout: 500
            readTimeout: 1500
~~~

Phần đầu điều chỉnh **LoadBalancer cho service ID** inventory-service. Phần sau điều chỉnh **Feign named client** inventoryReadClient. Không đổi tên key của phần thứ nhất thành inventoryReadClient chỉ vì Feign contextId đang dùng tên đó.

### 14.1. Tách service ID và contextId bằng một bảng

~~~java
@FeignClient(
        name = "inventory-service",
        contextId = "inventoryReadClient")
interface InventoryReadClient {
}
~~~

| Giá trị | Dùng cho |
| --- | --- |
| name = inventory-service | Service ID mà Feign LoadBalancer tìm trong discovery |
| contextId = inventoryReadClient | Tách named-client ensemble/bean configuration của Feign |
| spring.cloud.loadbalancer.clients.inventory-service.* | LoadBalancer config theo service ID |
| spring.cloud.openfeign.client.config.inventoryReadClient.* | Feign named-client config theo client identity |

Tài liệu OpenFeign mô tả feignName trong configuration properties liên quan đến value/name và contextId; khi nhiều Feign clients cùng name nhưng contextId khác nhau, dùng contextId để tránh collision và kiểm thử effective settings trên đúng release train.

### 14.2. Thứ tự ưu tiên Feign Java config và properties

Theo mặc định, cấu hình trong properties có thể thắng cấu hình bean Java của Feign. Nếu muốn Java configuration thắng, đặt:

~~~yaml
spring:
  cloud:
    openfeign:
      client:
        default-to-properties: false
~~~

Nếu timeout, logger level, RequestInterceptor hoặc Retryer dường như bị thay thế, kiểm tra:

- client config key có khớp name/contextId không;
- property có được khai báo trong profile khác không;
- URL property có vô tình bypass LoadBalancer không;
- default-to-properties có đang ở giá trị mong muốn không;
- config class có bị scan toàn cục không.

### 14.3. Đừng dùng Feign RequestInterceptor để sửa service ID

RequestInterceptor biến đổi request headers/template. Nó không thay đổi named-client context hoặc service ID mà LoadBalancer đã dùng. Nếu muốn chọn Inventory, khai báo name đúng; nếu muốn thêm header, dùng interceptor đúng scope. Không cố sửa host sau khi LoadBalancer chọn instance.

## 15. Bước 12 — xác minh bằng request thật, không chỉ đọc YAML

Một quy trình kiểm tra nên có **ba lớp bằng chứng**:

| Lớp | Điều cần xác minh | Bằng chứng |
| --- | --- | --- |
| Cấu hình | Property đúng tên/nguồn/giá trị | Environment/configprops đã bảo vệ |
| Context/bean | Đúng service ID và implementation | LoadBalancerClientFactory + bean type |
| HTTP route | Request thật tới đúng backend | Backend instance ID, access log, MockWebServer |

### 15.1. Test tách biệt Inventory và Payment

Ví dụ cấu trúc:

~~~text
InventoryLoadBalancerConfiguration
  -> RandomLoadBalancer (test policy)

PaymentLoadBalancerConfiguration
  -> RoundRobinLoadBalancer (default hoặc custom)

Caller:
  GET http://inventory-service/whoami
  GET http://payment-service/whoami
~~~

Trong integration test:

1. Cung cấp danh sách instance Inventory và Payment độc lập bằng SimpleDiscoveryClient hoặc test supplier.
2. Gửi request qua **service ID**, không gọi trực tiếp localhost.
3. Ghi nhận instance ID do từng backend trả.
4. Xác minh policy Inventory không làm thay đổi policy Payment.
5. Chạy lại test sau khi di chuyển package config hoặc thay đổi @ComponentScan để bắt lỗi global leakage.

### 15.2. Kiểm tra loại bean của từng service

~~~java
@Test
void inventoryUsesRandomAndPaymentUsesRoundRobin() {
    ReactorLoadBalancer<?> inventory =
            factory.getInstance(
                    "inventory-service", ReactorLoadBalancer.class);
    ReactorLoadBalancer<?> payment =
            factory.getInstance(
                    "payment-service", ReactorLoadBalancer.class);

    assertInstanceOf(RandomLoadBalancer.class, inventory);
    assertInstanceOf(RoundRobinLoadBalancer.class, payment);
}
~~~

Đây là test phù hợp khi ứng dụng **cố ý cấu hình hai implementation** như ví dụ. Nếu Payment dùng một implementation custom hoặc release train khác có thay đổi default, thay assertion theo contract thật của ứng dụng.

### 15.3. Test service ID không tồn tại

Tạo request gọi:

~~~text
http://inventroy-service/api/stock/BOOK-01
~~~

Trong đó tên có typo. Kết quả thường là **không có ServiceInstance** hoặc lỗi resolve tùy client/adapter. Test này giúp phân biệt:

- discovery không có service ID;
- cấu hình @LoadBalancerClient đăng ký sai tên;
- client chưa tích hợp LoadBalancer và đang cố DNS lookup.

Không chỉ assert status code. Kiểm tra **backend request count**: nếu không backend nào nhận request, lỗi xảy ra trước HTTP backend hoặc tại DNS/connection.

## 16. Log và metrics hỗ trợ chẩn đoán

Trong môi trường test, có thể tăng log cho các package:

~~~yaml
logging:
  level:
    org.springframework.cloud.loadbalancer: DEBUG
    org.springframework.cloud.openfeign: DEBUG
~~~

Chỉ tăng log trong thời gian ngắn và theo môi trường. Không bật Feign FULL logging ở production nếu body/header có thể chứa token, cookie, thông tin cá nhân hoặc dữ liệu nhạy cảm.

### 16.1. Những gì cần ghi lại

- Logical service ID.
- Selected instance ID/host/port (theo policy và mức bảo mật).
- Loại LoadBalancer implementation thực tế.
- Supplier chain/eligible instance count.
- Config revision và active profile.
- HTTP status, root exception, attempt number.
- Client type: RestClient, RestTemplate, WebClient hoặc Feign.

### 16.2. Không dùng high-cardinality hoặc lộ bí mật

Không thêm vào metric tags:

- order ID, SKU, customer ID, trace ID;
- full URL chứa query động;
- bearer token, API key, Cookie, Authorization;
- secret value hoặc private key.

Dùng trace/log có sampling để điều tra một request cụ thể. Metrics nên tập trung vào service ID, operation template, error class, status và client type có cardinality được kiểm soát.

## 17. Ma trận triệu chứng và nguyên nhân thường gặp

| Triệu chứng | Nguyên nhân có khả năng | Cách xác minh |
| --- | --- | --- |
| Random không được áp dụng cho Inventory | @LoadBalancerClient name không khớp host URI | Đối chiếu service ID ở request, annotation và registry |
| Inventory dùng config mặc định | Config class nằm trong sai context hoặc không được đăng ký | Kiểm tra bean qua LoadBalancerClientFactory |
| Inventory config tác động Payment | Class bị component-scan vào parent hoặc dùng defaultConfiguration | Kiểm tra package, @LoadBalancerClients và parent beans |
| Per-client TTL không thay đổi | Sai clients.<id> prefix hoặc nguồn khác ghi đè | Kiểm tra effective property và configprops |
| Per-client retry không bật | Global retry.enabled=false | Kiểm tra giới hạn global/per-client |
| Per-client cache không bật | Global cache.enabled=false | Kiểm tra global flag và supplier chain |
| Health-check path không đổi | Dùng sai dạng map hoặc supplier không phải health-check | Kiểm tra health-check.path.<serviceId> và supplier bean |
| RestClient báo UnknownHostException | Inject builder không @LoadBalanced | Kiểm tra bean qualifier và URI logic |
| RestTemplate gọi một host cố định | Không dùng bean @LoadBalanced hoặc request factory/client khác | Kiểm tra bean thực tế được inject |
| WebClient không chạy LB filter | WebClient.create() hoặc builder thường | Kiểm tra @LoadBalanced WebClient.Builder |
| WebClient gọi hai lần/metrics lặp | LB filter được thêm hai lần | Kiểm tra auto-config và manual filter |
| Feign gọi URL localhost | url trong @FeignClient hoặc Feign properties | Xóa URL nếu muốn discovery/LB |
| Feign không dùng LB dù có @FeignClient name | Thiếu spring-cloud-starter-loadbalancer | Kiểm tra dependency tree/BOM |
| Feign client config tác động client khác | Config class bị scan vào parent | Đưa config ra ngoài scan hoặc bỏ @Configuration |
| Hai Feign clients cùng name đè config nhau | Thiếu contextId riêng | Đặt contextId khác nhau |
| Feign timeout property không có hiệu lực | Sai feignName/contextId hoặc Java config bị properties ghi đè | Kiểm tra key và default-to-properties |
| Supplier không có health filter | Custom supplier thay default chain | Kiểm tra delegates và thứ tự supplier |
| Một service có instance, service khác rỗng | Discovery/service ID khác nhau | Kiểm tra registry theo từng service ID |
| Test pass nhưng production fail | TestPropertySource hoặc profile/env khác | So sánh active profiles và config revision |
| Context chưa xuất hiện trong startup logs | LoadBalancer context khởi tạo lazy | Gửi request hoặc cấu hình eager-load |
| Sửa YAML nhưng runtime không đổi | Context đã tạo, config nguồn ưu tiên cao hơn hoặc process chưa restart | Kiểm tra property sources và lifecycle |

## 18. Runbook xử lý cấu hình không có hiệu lực

Thực hiện theo thứ tự sau, ghi lại kết quả từng bước:

### 18.1. Khoanh vùng request

1. Xác định client đang thực thi: RestTemplate, RestClient, WebClient hay OpenFeign.
2. Ghi logical URI (đã loại bỏ query nhạy cảm).
3. Xác định service ID từ URI host hoặc Feign name.
4. Xác minh có URL cố định hay không.
5. Xác minh HTTP client bean thực tế đang được inject.

### 18.2. Khoanh vùng context

1. Đối chiếu service ID với @LoadBalancerClient name/value.
2. Kiểm tra cấu hình có bị component-scan vào parent không.
3. Kiểm tra @LoadBalancerClients defaultConfiguration có vô tình áp dụng toàn cục không.
4. Kiểm tra child context và bean types theo service ID.
5. Kiểm tra supplier list và thuật toán thực tế.

### 18.3. Khoanh vùng properties

1. Kiểm tra property có hỗ trợ per-client không.
2. Kiểm tra prefix clients.<serviceId> đúng chính tả.
3. Kiểm tra ngoại lệ global như enabled/retry.enabled/cache.enabled/stats.micrometer.enabled.
4. Kiểm tra các map property giữ cú pháp theo service ID trực tiếp.
5. Kiểm tra profile, environment, Config Server, command line và test overrides.
6. Kiểm tra Feign name/contextId và URL property riêng.

### 18.4. Kiểm chứng bằng request thật

1. Gọi endpoint an toàn qua service ID.
2. Xác định instance backend đã nhận request.
3. Kiểm tra selected instance và response body/access log.
4. Kiểm tra số HTTP attempts nếu retry bật.
5. Gọi service ID thứ hai để xác nhận config không bị rò sang client khác.

### 18.5. Sửa và triển khai

- Sửa service ID hoặc prefix ở nguồn cấu hình chuẩn.
- Di chuyển config class khỏi component scan hoặc đổi sang per-client registration.
- Sửa đúng builder/client bean đang được inject.
- Loại bỏ URL cố định nếu cần LoadBalancer.
- Xây lại supplier chain có thứ tự hợp lệ nếu custom supplier đã thay default.
- Restart/refresh đúng context nếu cấu hình được đọc lúc khởi tạo; không giả định mọi bean tự cập nhật.
- Chạy lại unit + integration tests trước khi rollout.

## 19. Bài tập tình huống

### 19.1. Tình huống A: Inventory và Payment đều dùng Random

~~~java
@Configuration
@LoadBalancerClients(
        defaultConfiguration = RandomLoadBalancerConfiguration.class)
class LoadBalancerConfiguration {
}
~~~

**Câu hỏi:** Vì sao Payment cũng đổi thuật toán?

**Đáp án:** defaultConfiguration được dùng làm cấu hình mặc định cho LoadBalancer clients. Nếu chỉ Inventory cần Random, đăng ký cấu hình bằng @LoadBalancerClient(name="inventory-service", configuration=...) và giữ class config ngoài component scan.

### 19.2. Tình huống B: @LoadBalancerClient đúng nhưng request vẫn DNS lookup

**Bối cảnh:** Annotation đăng ký inventory-service chính xác, nhưng RestClient báo UnknownHostException.

**Đáp án:** Kiểm tra RestClient.Builder có @LoadBalanced không và bean inventoryRestClient có được build từ đúng builder đó không. Annotation @LoadBalancerClient không tự biến mọi RestClient thành load-balanced.

### 19.3. Tình huống C: Per-client retry không bật

~~~yaml
spring:
  cloud:
    loadbalancer:
      retry:
        enabled: false
      clients:
        inventory-service:
          retry:
            enabled: true
~~~

**Câu hỏi:** Có phải sai service ID không?

**Đáp án:** Có thể service ID đúng nhưng đây là property có giới hạn global/per-client. Global retry disabled không thể được client bật lại theo chiều ngược. Thay đổi global nếu chính sách cho phép, rồi tắt retry riêng ở những clients không cần.

### 19.4. Tình huống D: Feign name đúng nhưng gọi localhost

~~~java
@FeignClient(
        name = "inventory-service",
        url = "http://localhost:8081")
interface InventoryClient {
}
~~~

**Đáp án:** URL annotation khiến Feign gọi trực tiếp, bỏ qua LoadBalancer. Nếu muốn service discovery, bỏ url và giữ name. Kiểm tra thêm URL trong spring.cloud.openfeign.client.config.

### 19.5. Tình huống E: Feign configuration của Inventory làm Payment có header Inventory

**Đáp án:** Config class có thể đã bị component scan vào parent context hoặc được khai báo là defaultConfiguration. Đặt class riêng ngoài component scan, chỉ truyền vào @FeignClient configuration của Inventory và dùng contextId riêng nếu nhiều Feign clients cùng service ID.

### 19.6. Tình huống F: Health-check path không đổi dù có clients.inventory-service

**Đáp án:** health-check.path là map theo service ID và giữ cú pháp trực tiếp để tương thích ngược, ví dụ health-check.path.inventory-service. Ngoài ra, phải có HealthCheckServiceInstanceListSupplier trong supplier chain; chỉ khai báo path không tự tạo scheduler/health supplier trong mọi cấu hình.

### 19.7. Tình huống G: Test thấy Random, production lại Round Robin

**Đáp án:** So sánh active profiles, Config Server label, environment variables, command-line args và custom config class trong deployment. Kiểm tra child context có bị global/default configuration override không. Xác nhận bean implementation trong process production, không dựa vào một property file trong Git.

## 20. Anti-pattern cần tránh

| Anti-pattern | Hậu quả | Cách làm đúng |
| --- | --- | --- |
| Dùng @LoadBalancerClients defaultConfiguration cho một service duy nhất | Tất cả clients nhận cấu hình mặc định | Dùng @LoadBalancerClient theo service ID |
| Đặt custom LB config trong package được component-scan | Bean bị đăng ký vào parent/global | Bỏ @Configuration hoặc đặt ngoài scan |
| Hardcode service ID trong custom LoadBalancer bean | Context của service khác có thể tham chiếu nhầm supplier | Dùng LoadBalancerClientFactory.PROPERTY_NAME |
| Nhầm instance ID với service ID | Cấu hình không gắn vào request | Dùng service ID trong annotation/prefix |
| Dùng tên bean Java làm key clients.<id> | Property không match client | Dùng đúng service ID |
| Tạo RestClient từ builder thường | Không chạy LB interceptor | Inject @LoadBalanced RestClient.Builder |
| Dùng WebClient.create() cho URI service ID | Bỏ qua LB integration | Dùng @LoadBalanced WebClient.Builder |
| Gắn LB filter hai lần | Request/metrics có thể bị xử lý lặp | Chỉ dùng một đường tích hợp |
| Gắn URL cố định vào @FeignClient | Bypass LoadBalancer | Dùng name và discovery |
| Dùng contextId làm service ID thay name | Registry lookup sai | Giữ name là service ID; contextId tách Feign config |
| Scan Feign config riêng thành global | Interceptor/decoder lan sang client khác | Config package riêng |
| Tin mọi property đều có prefix clients.<id> | Property map/global không được bind như kỳ vọng | Đọc configprops/reference đúng phiên bản |
| Cố bật per-client khi global flag tắt | Không có hiệu lực | Sửa global policy hoặc supplier config |
| Thêm nhiều ServiceInstanceListSupplier bean không rõ thứ tự | Default/custom chain bị override | Kiểm soát bean scope và delegates |
| Đọc YAML Git làm bằng chứng runtime | Bỏ sót env/profile override | Kiểm tra effective Environment an toàn |
| Restart toàn bộ hệ thống khi chỉ sai một bean | Blast radius lớn | Xác định context/client bị ảnh hưởng, rollout có kiểm soát |

## 21. Checklist trước khi kết luận đã sửa

- [ ] Xác định đúng HTTP client đang được gọi.
- [ ] Xác định logical service ID thực từ URI host hoặc Feign name.
- [ ] @LoadBalancerClient name/value khớp service ID.
- [ ] Registry/DiscoveryClient có entries cho đúng service ID.
- [ ] Client có @LoadBalanced integration tương ứng.
- [ ] Không có URL cố định bypass LoadBalancer.
- [ ] LoadBalancer child context tồn tại và chứa bean mong đợi.
- [ ] Custom configuration class không bị component-scan vào parent ngoài ý muốn.
- [ ] defaultConfiguration không vô tình tác động tất cả clients.
- [ ] Property prefix clients.<serviceId> đúng và property hỗ trợ per-client.
- [ ] Đã kiểm tra ngoại lệ global enabled/retry/cache/stats.
- [ ] Map properties dùng đúng cú pháp theo service ID.
- [ ] Profile/env/command-line/Config Server không ghi đè ngoài dự kiến.
- [ ] Supplier chain và thứ tự cache/health/filter đúng.
- [ ] Feign name/contextId/URL/property URL được phân biệt rõ.
- [ ] Feign config riêng không bị scan thành global config.
- [ ] Có unit test kiểm tra bean type/context theo service ID.
- [ ] Có integration test gửi HTTP qua service ID đến backend thật/mock server.
- [ ] Đã kiểm tra ít nhất hai service IDs để bắt config leakage.
- [ ] Logs/metrics không lộ token, API key, cookie hoặc thông tin nhạy cảm.
- [ ] Rollout/rollback có kiểm soát và có config revision rõ.

## 22. Kết luận

Khi cấu hình theo client của Spring Cloud LoadBalancer không có hiệu lực hoặc áp dụng nhầm dịch vụ, nguyên nhân thường nằm ở **ranh giới service ID và context**, **phạm vi component scan**, **HTTP client integration** hoặc **property precedence**.

Hãy luôn kiểm tra theo thứ tự:

1. **Request đang gọi service ID nào?**
2. **HTTP client có thực sự tích hợp LoadBalancer không?**
3. **Child context nào được tạo và bean nào nằm trong đó?**
4. **Cấu hình là per-client, global hay map property đặc biệt?**
5. **Nguồn cấu hình runtime nào đang thắng?**
6. **Backend nào thật sự nhận request?**

Phân biệt LoadBalancer child context với Feign named-client context và HTTP client bean giúp thu hẹp lỗi nhanh hơn. Sau khi sửa, phải kiểm thử **cả client mục tiêu lẫn client không liên quan** để chứng minh cấu hình đã được cách ly đúng.

## 23. Tài liệu tham khảo

- [Spring Cloud LoadBalancer – Reference](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html): child contexts, @LoadBalancerClient/@LoadBalancerClients, per-client properties, supplier chain và các property global.
- [Spring Cloud Commons – Common Abstractions](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html): @LoadBalanced RestTemplate, RestClient.Builder và WebClient.Builder.
- [Spring Cloud Commons – Configuration Properties](https://docs.spring.io/spring-cloud-commons/reference/configprops.html): tên property và kiểu dữ liệu theo release train.
- [Spring Cloud OpenFeign – Reference](https://docs.spring.io/spring-cloud-openfeign/reference/spring-cloud-openfeign.html): named-client context, name/contextId, configuration properties, URL override và LoadBalancer integration.
- [Spring Cloud LoadBalancer – Source](https://github.com/spring-cloud/spring-cloud-commons/blob/main/spring-cloud-loadbalancer/src/main/java/org/springframework/cloud/loadbalancer/annotation/LoadBalancerClientConfiguration.java): default ReactorLoadBalancer, ServiceInstanceListSupplier và điều kiện auto-configuration.
- [Spring Cloud LoadBalancer – Getting Started](https://spring.io/guides/gs/spring-cloud-loadbalancer): ví dụ cấu hình riêng bằng @LoadBalancerClient.
- [Spring Boot – Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html): PropertySource precedence, profiles và environment variables.
- [Spring Boot – Actuator Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html): bảo vệ env/configprops và thông tin cấu hình runtime.
- [Spring Framework – RestClient](https://docs.spring.io/spring-framework/reference/integration/rest-clients.html): RestClient.Builder và request factory.
- [Spring Framework – WebClient](https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html): WebClient.Builder và reactive filter chain.

