# Vai trò hiện tại của @EnableDiscoveryClient

Trong các ví dụ Spring Cloud cũ, ứng dụng thường được yêu cầu đặt `@EnableDiscoveryClient` trên lớp cấu hình để bật service discovery. Với Spring Cloud hiện đại, annotation này **không còn bắt buộc**: khi một implementation của `DiscoveryClient` được đưa vào classpath thông qua starter phù hợp, Spring Boot có thể tự cấu hình discovery client và đăng ký ứng dụng với registry.

Annotation vẫn tồn tại trong Spring Cloud Commons. Nó còn thể hiện ý định bật discovery theo cách tường minh và cung cấp thuộc tính `autoRegister` để điều khiển auto-registration. Tuy nhiên, cần phân biệt ba việc: có một `DiscoveryClient` để tra cứu service, có một `ServiceRegistry` để đăng ký instance của chính ứng dụng, và có tự động đăng ký instance khi ứng dụng khởi động hay không. Chúng liên quan nhưng không phải một thao tác duy nhất.

Bài học thuộc chương **DiscoveryClient** của module **SPRING_CLOUD_CORE**. Ta sẽ làm rõ vai trò hiện tại của annotation, cách starter kích hoạt discovery, cách tắt auto-registration, và cách kiểm tra ứng dụng có thực sự tạo client/đăng ký instance hay không.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích vì sao `@EnableDiscoveryClient` không còn là annotation bắt buộc trong ứng dụng Spring Boot hiện đại.
- Mô tả vai trò lịch sử và hợp đồng hiện tại của annotation trong Spring Cloud Commons.
- Phân biệt `DiscoveryClient`, `ReactiveDiscoveryClient`, `ServiceRegistry` và `Registration`.
- Chọn starter của registry như Eureka hoặc Consul để đưa implementation vào classpath.
- Điều khiển auto-registration bằng `autoRegister` hoặc property cấu hình.
- Phân biệt tắt auto-registration với tắt toàn bộ discovery client.
- Hiểu `SimpleDiscoveryClient` khi không có registry-backed implementation.
- Kiểm tra discovery beans, service registration events và actuator endpoint.
- Tránh thêm annotation theo thói quen khi starter đã cung cấp auto-configuration.

## 2. Từ cách bật tường minh đến auto-configuration

### 2.1. Vai trò ban đầu của annotation

`@EnableDiscoveryClient` được Spring Cloud Commons cung cấp trong package:

~~~java
org.springframework.cloud.client.discovery.EnableDiscoveryClient
~~~

Annotation được thiết kế như một điểm kích hoạt discovery. Trong cơ chế import của annotation, `EnableDiscoveryClientImportSelector` tìm các cấu hình provider được đăng ký qua metadata `META-INF/spring.factories` dưới key:

~~~text
org.springframework.cloud.client.discovery.EnableDiscoveryClient
~~~

Các provider như Eureka, Consul hoặc Zookeeper có thể đóng góp cấu hình tích hợp vào cơ chế này. Vì thế, trong các dự án cũ, người phát triển thường thêm annotation lên lớp cấu hình chính để kích hoạt DiscoveryClient.

### 2.2. Vai trò hiện tại

Tài liệu Spring Cloud Commons hiện hành ghi rõ: `@EnableDiscoveryClient` không còn bắt buộc. Chỉ cần đưa implementation `DiscoveryClient` vào classpath là Spring Boot có thể cấu hình discovery và đăng ký ứng dụng với service discovery server.

Ví dụ, khi dùng Consul, dependency:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-consul-discovery</artifactId>
</dependency>
~~~

đã cung cấp integration cần thiết. Ứng dụng có thể là một Spring Boot application bình thường:

~~~java
@SpringBootApplication
public class OrderServiceApplication {

    public static void main(String[] args) {
        SpringApplication.run(OrderServiceApplication.class, args);
    }
}
~~~

Không cần thêm `@EnableDiscoveryClient` chỉ để discovery hoạt động.

### 2.3. Annotation vẫn còn tác dụng gì?

Annotation vẫn là một phần API của Spring Cloud Commons và có thuộc tính:

~~~java
boolean autoRegister() default true;
~~~

Thuộc tính này biểu thị việc có cho phép `ServiceRegistry` tự động đăng ký server local hay không. Giá trị mặc định là `true`. Có thể đặt `autoRegister=false` để tắt auto-registration theo khai báo annotation.

Do auto-configuration theo classpath đã đủ cho phần lớn ứng dụng hiện đại, lựa chọn thường dùng là:

- Không thêm annotation nếu không có lý do cần dùng nó.
- Dùng property `spring.cloud.service-registry.auto-registration.enabled=false` khi muốn điều khiển auto-registration bằng cấu hình môi trường.
- Chỉ giữ annotation nếu dự án có chủ đích dùng thuộc tính `autoRegister` hoặc cần giữ cách kích hoạt tường minh theo thiết kế hiện hữu.

## 3. Phân biệt các abstraction

Tên các interface gần nhau nhưng vai trò khác nhau:

| Thành phần | Vai trò |
| --- | --- |
| `DiscoveryClient` | API blocking để truy vấn danh sách service và các instance của một service |
| `ReactiveDiscoveryClient` | API reactive cho truy vấn service discovery |
| `ServiceRegistry` | API đăng ký, hủy đăng ký hoặc thay đổi trạng thái instance local |
| `Registration` | Mô tả instance cần đăng ký, thường chứa service ID, host, port, URI và metadata |
| `@EnableDiscoveryClient` | Annotation kích hoạt discovery theo cơ chế import cũ và cung cấp tùy chọn auto-registration |

`DiscoveryClient` chủ yếu trả lời câu hỏi: **service nào đang tồn tại và có instance nào để gọi?**

`ServiceRegistry` chủ yếu trả lời câu hỏi: **instance hiện tại đăng ký, hủy đăng ký hoặc đổi trạng thái như thế nào?**

Một implementation provider có thể cung cấp cả DiscoveryClient lẫn ServiceRegistry, nhưng client truy vấn và thao tác đăng ký vẫn là hai hợp đồng khác nhau.

## 4. Discovery client được tạo từ classpath

### 4.1. Thêm starter của registry

Ví dụ Consul:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-consul-discovery</artifactId>
</dependency>
~~~

Ví dụ Eureka:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-netflix-eureka-client</artifactId>
</dependency>
~~~

Version của starter cần được quản lý bởi Spring Cloud BOM tương thích với Spring Boot của dự án. Không chọn một version Spring Cloud riêng lẻ chỉ để làm annotation hoạt động.

### 4.2. Cấu hình Consul tối thiểu

~~~yaml
spring:
  application:
    name: order-service
  cloud:
    consul:
      host: localhost
      port: 8500
      discovery:
        enabled: true
        register: true
~~~

Khi Consul agent/server sẵn sàng và ứng dụng khởi động, Consul Discovery integration có thể tạo client, registration và tự đăng ký instance theo cấu hình. Ví dụ không cần `@EnableDiscoveryClient`.

Tên service mặc định thường lấy từ `spring.application.name`. Instance ID và port mặc định được tạo từ thông tin application context và server đang chạy; provider có thể cho phép override các trường này bằng thuộc tính riêng.

### 4.3. Những điều kiện cần kiểm tra

Nếu thêm starter mà chưa thấy service trong registry, kiểm tra:

1. Dependency provider thực sự nằm trong runtime classpath.
2. Discovery chưa bị tắt bởi `spring.cloud.discovery.enabled` hoặc property riêng của provider.
3. Địa chỉ registry, credentials và TLS được cấu hình đúng.
4. Auto-registration chưa bị tắt.
5. Hostname, IP, port và service ID mà provider chuẩn bị đăng ký hợp lệ.
6. Registry có nhận registration và health check của instance hay không.

Thêm annotation không thể sửa lỗi kết nối registry, sai credentials, sai địa chỉ đăng ký hoặc health check thất bại.

## 5. Điều khiển auto-registration

Discovery client có thể được dùng để tra cứu service mà không nhất thiết phải đăng ký chính ứng dụng hiện tại. Ví dụ, một batch worker chỉ cần tìm endpoint của các service khác; hoặc một ứng dụng muốn tự đăng ký sau khi đã hoàn tất kiểm tra trạng thái.

### 5.1. Tắt bằng property dùng chung

Cấu hình:

~~~yaml
spring:
  cloud:
    service-registry:
      auto-registration:
        enabled: false
~~~

Property `spring.cloud.service-registry.auto-registration.enabled` tắt auto-registration của ServiceRegistry. Cách này phù hợp khi muốn quản lý bằng profile hoặc environment:

~~~yaml
spring:
  config:
    activate:
      on-profile: local-test
  cloud:
    service-registry:
      auto-registration:
        enabled: false
~~~

Khi property này là `false`, các sự kiện auto-registration `InstancePreRegisteredEvent` và `InstanceRegisteredEvent` không được phát theo cơ chế chuẩn.

### 5.2. Tắt bằng annotation

Nếu ứng dụng vẫn khai báo annotation:

~~~java
@SpringBootApplication
@EnableDiscoveryClient(autoRegister = false)
public class OrderServiceApplication {

    public static void main(String[] args) {
        SpringApplication.run(OrderServiceApplication.class, args);
    }
}
~~~

`autoRegister=false` biểu thị không tự động đăng ký local server. Cách này gắn lựa chọn vào mã nguồn. Với ứng dụng không cần annotation để bật discovery, property dùng chung thường dễ thay đổi theo môi trường hơn.

### 5.3. Tắt bằng thuộc tính provider

Provider có thể có property riêng. Ví dụ Consul:

~~~yaml
spring:
  cloud:
    consul:
      discovery:
        register: false
~~~

Eureka có thuộc tính riêng:

~~~yaml
eureka:
  client:
    register-with-eureka: false
~~~

Các property này thuộc integration cụ thể. Hãy kiểm tra tài liệu provider và release train đang dùng để biết chính xác cách chúng tương tác với property chung của ServiceRegistry.

### 5.4. Tắt discovery client hoàn toàn

Tắt auto-registration không đồng nghĩa tắt truy vấn service. Nếu ứng dụng vẫn cần tìm instance của service khác, giữ DiscoveryClient được bật và chỉ tắt registration.

Muốn tắt discovery ở mức Commons:

~~~yaml
spring:
  cloud:
    discovery:
      enabled: false
~~~

Có thể tắt riêng blocking hoặc reactive discovery:

~~~yaml
spring:
  cloud:
    discovery:
      blocking:
        enabled: false
      reactive:
        enabled: false
~~~

Property provider như `spring.cloud.consul.discovery.enabled=false` hoặc `eureka.client.enabled=false` cũng có thể điều khiển integration cụ thể. Không nhầm các property này với `spring.cloud.service-registry.auto-registration.enabled=false`.

## 6. DiscoveryClient không nhất thiết phải kết nối registry từ xa

Nếu không có registry-backed `DiscoveryClient` trong classpath, Spring Cloud Commons có thể cung cấp `SimpleDiscoveryClient`. Client này lấy thông tin instance từ cấu hình tĩnh thay vì truy vấn một registry server.

Ví dụ:

~~~yaml
spring:
  cloud:
    discovery:
      client:
        simple:
          instances:
            inventory-service:
              - uri: http://localhost:8081
            pricing-service:
              - uri: http://localhost:8082
              - uri: http://localhost:8083
~~~

`SimpleDiscoveryClient` phù hợp với môi trường local, kiểm thử hoặc danh sách endpoint tĩnh. Nó không tự đăng ký instance của ứng dụng lên một service registry từ xa.

Vì vậy, sự tồn tại của một bean `DiscoveryClient` không chứng minh ứng dụng đã kết nối Eureka/Consul. Cần kiểm tra implementation cụ thể đang được sử dụng.

## 7. Nhiều DiscoveryClient trong cùng application context

`DiscoveryClient` mở rộng `Ordered`. Nếu có nhiều implementation, thứ tự có thể ảnh hưởng tới thứ tự client được trả về và thành phần được composite sử dụng.

Spring Cloud cung cấp property order cho một số provider, ví dụ:

~~~yaml
spring:
  cloud:
    consul:
      discovery:
        order: 1
eureka:
  client:
    order: 2
~~~

Với custom implementation, có thể override `getOrder()`:

~~~java
public class InternalDiscoveryClient implements DiscoveryClient {

    @Override
    public int getOrder() {
        return 10;
    }

    // Implement getInstances, getServices and description
}
~~~

Không thêm nhiều registry starter chỉ để dự phòng mà không xác định rõ mục đích. Khi có nhiều client, cần quyết định client nào ưu tiên, dữ liệu service có trùng nhau không và health indicator sẽ phản ánh tình trạng nào.

## 8. Vòng đời đăng ký service

Với integration hỗ trợ auto-registration, quy trình tổng quát có thể hình dung:

~~~mermaid
sequenceDiagram
    participant App as Spring Boot Application
    participant Auto as AutoServiceRegistration
    participant Registry as ServiceRegistry
    participant Server as Eureka / Consul / Zookeeper
    App->>App: Load provider starter and configuration
    App->>Auto: Prepare local Registration
    Auto->>App: Publish InstancePreRegisteredEvent
    Auto->>Registry: register(Registration)
    Registry->>Server: Register service instance
    Server-->>Registry: Registration result
    Auto->>App: Publish InstanceRegisteredEvent
    Note over App,Server: DiscoveryClient queries service instances separately
~~~

Hai sự kiện đáng chú ý:

- `InstancePreRegisteredEvent`: phát trước khi instance được đăng ký.
- `InstanceRegisteredEvent`: phát sau khi instance được đăng ký.

Ứng dụng có thể đăng ký listener để bổ sung log, metadata hoặc xử lý tích hợp sau registration. Không nên đặt logic nghiệp vụ quan trọng vào listener mà không có retry/idempotency, vì registry có thể tạm thời không sẵn sàng.

Nếu `spring.cloud.service-registry.auto-registration.enabled=false`, các sự kiện auto-registration này không được phát.

### 8.1. Tự đăng ký thủ công

Khi cần điều khiển thời điểm đăng ký, có thể inject `ServiceRegistry` và gọi API:

~~~java
@Service
public class ManualRegistrationService {

    private final ServiceRegistry<Registration> serviceRegistry;
    private final Registration registration;

    public ManualRegistrationService(
            ServiceRegistry<Registration> serviceRegistry,
            Registration registration) {
        this.serviceRegistry = serviceRegistry;
        this.registration = registration;
    }

    public void register() {
        serviceRegistry.register(registration);
    }

    public void deregister() {
        serviceRegistry.deregister(registration);
    }
}
~~~

Đây là minh họa hợp đồng; constructor và kiểu registration cụ thể phụ thuộc provider. Ví dụ Eureka dùng registration type của Eureka, Consul dùng Consul registration. Không phải mọi implementation đều có thể được thay thế bằng cùng một object `Registration`.

Khi tự quản lý đăng ký, ứng dụng cũng phải chịu trách nhiệm về thời điểm đăng ký, hủy đăng ký khi shutdown, retry, xử lý đăng ký trùng và cập nhật trạng thái health.

## 9. Kiểm tra discovery và registration

### 9.1. Kiểm tra bean trong application context

Có thể liệt kê các implementation được Spring tạo:

~~~java
@Component
public class DiscoveryClientReporter implements ApplicationRunner {

    private final List<DiscoveryClient> discoveryClients;

    public DiscoveryClientReporter(
            List<DiscoveryClient> discoveryClients) {
        this.discoveryClients = discoveryClients;
    }

    @Override
    public void run(ApplicationArguments args) {
        discoveryClients.forEach(client ->
                System.out.println(
                        client.description()
                                + " order=" + client.getOrder()));
    }
}
~~~

Trong ứng dụng thực tế, dùng logger thay cho `System.out`. Nếu danh sách rỗng, kiểm tra dependency provider và các property điều khiển discovery.

### 9.2. Kiểm tra service instances

Có thể truy vấn một service:

~~~java
List<ServiceInstance> instances =
        discoveryClient.getInstances("inventory-service");

instances.forEach(instance -> {
    log.info("serviceId={}, host={}, port={}, uri={}",
            instance.getServiceId(),
            instance.getHost(),
            instance.getPort(),
            instance.getUri());
});
~~~

Kết quả phụ thuộc implementation và dữ liệu registry. Danh sách rỗng có thể do service chưa đăng ký, registry chưa đồng bộ, service ID khác, filter hoặc client chưa kết nối được.

### 9.3. Health indicator

Spring Cloud Commons cung cấp `DiscoveryClientHealthIndicator` dựa trên implementation discovery hiện tại. Có thể tắt:

~~~yaml
spring:
  cloud:
    discovery:
      client:
        health-indicator:
          enabled: false
~~~

Mặc định health indicator có thể gọi `DiscoveryClient.getServices()` để kiểm tra. Với registry có số lượng service lớn, thao tác này có thể tốn chi phí; property `spring.cloud.discovery.client.health-indicator.use-services-query=false` yêu cầu dùng `probe()` nếu implementation hỗ trợ.

Health indicator chỉ là một tín hiệu sức khỏe. Nó không chứng minh từng service instance có thể nhận traffic thành công.

### 9.4. Service Registry actuator endpoint

Spring Cloud Commons cung cấp actuator endpoint `/serviceregistry`. Khi Actuator web exposure được cấu hình, endpoint thường truy cập qua:

~~~text
GET  /actuator/serviceregistry
POST /actuator/serviceregistry
~~~

GET trả về trạng thái registration. POST có thể đổi trạng thái registration bằng JSON chứa field `status`; giá trị được chấp nhận tùy provider. Ví dụ Eureka có thể dùng `UP`, `DOWN`, `OUT_OF_SERVICE` hoặc `UNKNOWN`.

Chỉ expose endpoint này trên management network và bảo vệ quyền truy cập. Thay trạng thái registration có thể làm instance ngừng nhận traffic từ consumer.

## 10. Ví dụ kiểm thử ứng dụng không dùng annotation

Có thể viết một integration test xác nhận ứng dụng có discovery client khi provider starter được đưa vào classpath mà lớp main không khai báo `@EnableDiscoveryClient`.

Ví dụ khung test với Consul starter:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.cloud.client.discovery.DiscoveryClient;

@SpringBootTest(properties = {
    "spring.application.name=order-service",
    "spring.cloud.consul.host=localhost",
    "spring.cloud.consul.port=8500",
    "spring.cloud.service-registry.auto-registration.enabled=false"
})
class DiscoveryClientAutoConfigurationTest {

    @Autowired
    ApplicationContext context;

    @Test
    void createsDiscoveryClientWithoutEnableAnnotation() {
        assertThat(context.getBeansOfType(DiscoveryClient.class))
                .isNotEmpty();
    }
}
~~~

Test này cần dependency Consul discovery starter và cấu hình test phù hợp với phiên bản đang dùng. Auto-registration bị tắt để test không cần đăng ký instance thật; tùy provider, việc tạo bean client có thể vẫn cần một registry endpoint khi thực hiện truy vấn. Mục tiêu của test là kiểm tra bean được auto-configure, không phải xác minh Consul server hoạt động.

### 10.1. Ma trận kiểm thử

| Trường hợp | Kết quả mong đợi |
| --- | --- |
| Có provider starter, không có annotation | DiscoveryClient được auto-configure |
| Có provider starter và auto-registration mặc định | Instance được đăng ký theo cấu hình provider |
| Auto-registration property bằng false | DiscoveryClient vẫn có thể dùng để truy vấn; local instance không tự đăng ký |
| `spring.cloud.discovery.enabled=false` | Discovery integration được tắt theo cấu hình Commons |
| Không có registry-backed client | SimpleDiscoveryClient có thể cung cấp dữ liệu tĩnh |
| Có nhiều DiscoveryClient | Kiểm tra order và dữ liệu instance được trả về |
| Registry không khả dụng | Kiểm tra startup policy, retry, health và log của provider |
| Service ID sai | `getInstances()` trả danh sách rỗng hoặc kết quả theo provider |

## 11. Những nhầm lẫn thường gặp

| Nhầm lẫn | Thực tế |
| --- | --- |
| Không có `@EnableDiscoveryClient` thì service discovery không chạy | Starter provider trên classpath có thể tự cấu hình DiscoveryClient |
| Thêm annotation là có Eureka/Consul server | Annotation không triển khai hoặc khởi chạy registry server |
| Có DiscoveryClient nghĩa là ứng dụng đã đăng ký | DiscoveryClient phục vụ truy vấn; auto-registration do ServiceRegistry/provider đảm nhiệm |
| Tắt auto-registration là tắt discovery | Client vẫn có thể tra cứu service khác |
| `spring.cloud.discovery.enabled` giống `auto-registration.enabled` | Một property tắt discovery, property kia chỉ tắt đăng ký local |
| SimpleDiscoveryClient là registry server | Nó đọc instance từ cấu hình tĩnh và không cung cấp đăng ký động |
| `@EnableDiscoveryClient` bắt buộc cho Consul | Tài liệu Consul hiện hành dùng ứng dụng Spring Boot bình thường cùng starter |
| Annotation điều khiển toàn bộ hành vi provider | Các property riêng của Eureka/Consul vẫn có thể điều khiển registration và client |

## 12. Troubleshooting

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Không thấy DiscoveryClient bean | Thiếu provider starter, discovery bị disable hoặc auto-configuration bị exclude | Kiểm tra dependency runtime và điều kiện cấu hình |
| Có bean nhưng không thấy instance local trong registry | Auto-registration bị tắt hoặc registration lỗi | Kiểm tra property chung, property provider và log |
| Có thể query nhưng service không đăng ký | DiscoveryClient hoạt động, ServiceRegistry auto-registration bị tắt | Kiểm tra `spring.cloud.service-registry.auto-registration.enabled` |
| Thêm `@EnableDiscoveryClient` nhưng không thay đổi | Provider starter đã auto-configure trước đó hoặc lỗi nằm ở registry connection | Kiểm tra registry URL, credentials, network và health |
| Không có sự kiện `InstanceRegisteredEvent` | Auto-registration bị tắt hoặc quá trình registration chưa hoàn tất | Kiểm tra property và log registration |
| `getInstances()` trả danh sách rỗng | Service ID sai, registry chưa có instance hoặc cache chưa cập nhật | Kiểm tra tên service và registry trực tiếp |
| SimpleDiscoveryClient trả instance cũ | URI tĩnh trong configuration chưa cập nhật | Kiểm tra property `spring.cloud.discovery.client.simple.instances` |
| Có nhiều client và kết quả không như mong đợi | Thứ tự `DiscoveryClient` hoặc provider config chưa rõ | Kiểm tra `getOrder()` và property order |

## 13. Quy trình chọn cách dùng annotation

Khi bắt đầu một service mới:

1. Chọn registry (Eureka, Consul, Zookeeper hoặc provider khác).
2. Thêm starter tương ứng và quản lý version qua Spring Cloud BOM.
3. Cấu hình endpoint registry, application name và thông tin instance.
4. Chạy ứng dụng không có `@EnableDiscoveryClient`, sau đó kiểm tra DiscoveryClient bean và registration.
5. Chỉ thêm annotation nếu có lý do rõ ràng, chẳng hạn cần dùng `autoRegister=false` theo khai báo.
6. Nếu muốn truy vấn nhưng không đăng ký, dùng `spring.cloud.service-registry.auto-registration.enabled=false` hoặc property của provider.
7. Nếu không muốn discovery hoạt động, dùng property disable ở cấp Commons/provider.
8. Kiểm tra registry, health indicator, events và actuator endpoint trong môi trường thử nghiệm.

Với hệ thống đã tồn tại, không xóa annotation hàng loạt mà chưa kiểm thử. Annotation có thể đang được dùng để tắt auto-registration hoặc kích hoạt một cơ chế import cũ. Hãy xem cấu hình và hành vi runtime trước khi loại bỏ.

## 14. Tổng kết

Trong Spring Cloud hiện đại, `@EnableDiscoveryClient` vẫn tồn tại nhưng không còn là điều kiện bắt buộc để dùng service discovery. Provider starter đưa implementation vào classpath và Spring Boot auto-configure các bean cần thiết. Annotation có vai trò lịch sử là điểm kích hoạt discovery qua import selector; hiện tại nó chủ yếu còn hữu ích khi muốn khai báo tường minh hoặc dùng thuộc tính `autoRegister`.

Điều quan trọng là phân biệt DiscoveryClient để truy vấn, ServiceRegistry để đăng ký instance và auto-registration để tự đăng ký khi khởi động. Muốn chỉ truy vấn service, có thể tắt auto-registration mà vẫn giữ DiscoveryClient. Muốn tắt discovery, dùng property disable ở Commons hoặc provider. Kiểm tra bean, registry events, health indicator và dữ liệu thực tế để xác nhận hành vi thay vì chỉ dựa vào annotation trên lớp main.

## Tài liệu tham khảo

- [Spring Cloud Commons — Common Abstractions](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html): vai trò hiện tại của `@EnableDiscoveryClient`, `DiscoveryClient`, `ServiceRegistry`, auto-registration, health indicator và `SimpleDiscoveryClient`.
- [Spring Cloud Commons — Configuration Properties](https://docs.spring.io/spring-cloud-commons/reference/configprops.html): các property điều khiển discovery, health indicator và service registry.
- [Spring Cloud `EnableDiscoveryClient` source](https://github.com/spring-cloud/spring-cloud-commons/blob/main/spring-cloud-commons/src/main/java/org/springframework/cloud/client/discovery/EnableDiscoveryClient.java): annotation, import selector và thuộc tính `autoRegister`.
- [Spring Cloud Consul — Service Discovery](https://docs.spring.io/spring-cloud-consul/reference/discovery.html): kích hoạt discovery bằng starter và ví dụ ứng dụng Spring Boot không cần `@EnableDiscoveryClient`.
- [Spring Cloud Netflix — Eureka Client](https://docs.spring.io/spring-cloud-netflix/reference/spring-cloud-netflix.html): cấu hình Eureka client và các thuộc tính riêng của provider.

Luôn đối chiếu tài liệu theo release train Spring Cloud tương thích với Spring Boot của dự án. Các thuộc tính riêng của registry, cách auto-registration và metadata provider có thể khác nhau.
