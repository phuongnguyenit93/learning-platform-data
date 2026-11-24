# Truy vấn dịch vụ qua Spring DiscoveryClient

Trong kiến trúc microservice, ứng dụng gọi thường biết tên logic của dịch vụ đích, chẳng hạn inventory-service, nhưng không nên phải lưu cố định IP và port của từng instance. Khi số instance thay đổi do scale, triển khai hoặc phục hồi sau sự cố, địa chỉ có thể thay đổi theo. Spring Cloud cung cấp DiscoveryClient như một API chung để ứng dụng tra cứu service ID thành danh sách ServiceInstance.

Với Spring Cloud Consul, DiscoveryClient lấy thông tin từ Consul Service Catalog và Health API. Mã ứng dụng có thể dùng cùng một abstraction khi chuyển sang một discovery provider khác, trong khi cách đăng ký, health check và truy vấn dữ liệu được xử lý bởi implementation tương ứng.

## 1. DiscoveryClient giải quyết vấn đề gì?

Giả sử order-service cần gọi inventory-service. Nếu order-service gắn cứng địa chỉ http://10.0.0.12:8080, việc thay thế máy chủ hoặc chạy thêm instance sẽ buộc ứng dụng gọi phải biết và cập nhật địa chỉ mới.

Service discovery thay đổi cách phụ thuộc: ứng dụng yêu cầu các instance theo tên dịch vụ. Discovery provider trả về host, port, URI và metadata của các instance đã đăng ký.

    order-service
         |
         | getInstances("inventory-service")
         v
    DiscoveryClient
         |
         v
    Consul Discovery implementation
         |
         v
    Consul Agent / Health API
         |
         v
    List<ServiceInstance>
         |
         v
    Ứng dụng sử dụng URI hoặc LoadBalancer chọn instance

DiscoveryClient cung cấp thông tin để tìm dịch vụ. Nó không tự gửi HTTP request, không bảo đảm endpoint đang hoạt động sau thời điểm tra cứu và không tự thực hiện load balancing cho một HTTP client thông thường.

## 2. Thêm dependency và cấu hình Consul

Để dùng Consul làm discovery provider, thêm starter sau vào ứng dụng Spring Boot:

**Maven**

    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-consul-discovery</artifactId>
    </dependency>

**Gradle**

    dependencies {
        implementation 'org.springframework.cloud:spring-cloud-starter-consul-discovery'
    }

Sử dụng Spring Cloud BOM tương thích với phiên bản Spring Boot của dự án để quản lý phiên bản dependency. Starter này cấu hình Consul Discovery và cung cấp implementation của Spring Cloud DiscoveryClient.

Ví dụ cấu hình cho order-service:

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
            register-health-check: true
            health-check-path: /actuator/health

Consul Agent mặc định được tìm ở localhost:8500. Nếu ứng dụng chạy trong Docker hoặc Kubernetes, hãy dùng địa chỉ Consul Agent có thể truy cập từ network namespace của ứng dụng. localhost bên trong container chỉ trỏ tới chính container đó.

spring.application.name thường được dùng làm service name mặc định khi đăng ký. Vì vậy, nếu inventory-service đăng ký với Consul bằng tên inventory-service, consumer phải truy vấn đúng service ID này. Nếu cấu hình spring.cloud.consul.discovery.service-name để đổi tên đăng ký, consumer cần dùng tên đã đổi.

Ứng dụng chỉ cần tra cứu dịch vụ mà không cần tự đăng ký có thể đặt spring.cloud.consul.discovery.register=false. Điều này không tắt DiscoveryClient; nó chỉ tắt đăng ký service của chính ứng dụng.

## 3. Hai phương thức tra cứu chính

DiscoveryClient nằm trong package org.springframework.cloud.client.discovery. Hai phương thức thường dùng là:

| Phương thức | Kết quả | Mục đích |
|---|---|---|
| getServices() | List<String> | Lấy danh sách service ID mà discovery client biết |
| getInstances(serviceId) | List<ServiceInstance> | Lấy các instance thuộc một service ID |

Ví dụ:

    List<String> serviceIds = discoveryClient.getServices();

    List<ServiceInstance> instances =
            discoveryClient.getInstances("inventory-service");

Nếu service ID không tồn tại hoặc không có instance phù hợp, kết quả thường là danh sách rỗng. Ứng dụng phải xử lý trường hợp này thay vì giả định luôn có ít nhất một instance.

DiscoveryClient cũng có phương thức probe() để kiểm tra discovery client có thể thực hiện thao tác discovery hay không. Implementation có thể dùng một truy vấn nhẹ hơn getServices(). Một lần probe thành công chỉ cho biết discovery client có thể gọi provider; nó không chứng minh mọi service đều có instance khỏe.

## 4. ServiceInstance chứa thông tin gì?

Mỗi phần tử trả về từ getInstances() là một ServiceInstance. Interface này biểu diễn một địa chỉ cụ thể của service, không phải toàn bộ dịch vụ logic.

Các thông tin thường dùng:

| Phương thức | Ý nghĩa |
|---|---|
| getServiceId() | Service ID mà instance thuộc về |
| getInstanceId() | ID định danh instance nếu provider cung cấp |
| getHost() | Host hoặc IP của instance |
| getPort() | Port mà instance đăng ký |
| getUri() | URI được tạo từ scheme, host và port |
| isSecure() | Cho biết instance dùng kết nối bảo mật hay không |
| getMetadata() | Map metadata do provider đăng ký kèm instance |

Không phải provider nào cũng có cùng metadata. Với Consul, thông tin đăng ký thường gồm service name, instance ID, địa chỉ, port, tags và metadata. Các trường cụ thể phụ thuộc cấu hình đăng ký và phiên bản provider.

Ví dụ một service có hai instance:

    inventory-service
      - instance: inventory-1
        host: 10.0.0.21
        port: 8081
        metadata:
          zone: hcm-a
      - instance: inventory-2
        host: 10.0.0.22
        port: 8081
        metadata:
          zone: hcm-b

DiscoveryClient trả về danh sách ServiceInstance tương ứng. Ứng dụng có thể đọc metadata để hiển thị thông tin, ghi log hoặc áp dụng bộ lọc riêng nếu nghiệp vụ yêu cầu.

## 5. Inject DiscoveryClient vào service

Spring Boot tự cấu hình DiscoveryClient implementation khi starter Consul Discovery có mặt và discovery được bật. Có thể inject abstraction vào một bean bằng constructor injection:

    import java.net.URI;
    import java.util.Collections;
    import java.util.List;
    import java.util.stream.Collectors;

    import org.springframework.cloud.client.ServiceInstance;
    import org.springframework.cloud.client.discovery.DiscoveryClient;
    import org.springframework.stereotype.Service;

    @Service
    public class InventoryDiscoveryService {

        private final DiscoveryClient discoveryClient;

        public InventoryDiscoveryService(DiscoveryClient discoveryClient) {
            this.discoveryClient = discoveryClient;
        }

        public List<URI> findInventoryUris() {
            List<ServiceInstance> instances =
                    discoveryClient.getInstances("inventory-service");

            if (instances.isEmpty()) {
                return Collections.emptyList();
            }

            return instances.stream()
                    .map(ServiceInstance::getUri)
                    .collect(Collectors.toList());
        }
    }

Phương thức trên trả về URI của tất cả instance mà provider trả về tại thời điểm truy vấn. Danh sách này có thể thay đổi ở lần gọi tiếp theo do instance mới đăng ký, bị deregister hoặc health check đổi trạng thái.

Không nên giữ danh sách instance vô thời hạn trong một static field. Nếu ứng dụng tự cache kết quả, cần xác định thời gian sống, cách làm mới và hành vi khi Consul không truy cập được. Thông thường nên để discovery client và load balancer quản lý việc lấy danh sách theo cơ chế của chúng.

## 6. Liệt kê service và kiểm tra instance

Có thể tạo một lớp nhỏ để quan sát những service ID Consul trả về:

    @Service
    public class DiscoveryCatalog {

        private final DiscoveryClient discoveryClient;

        public DiscoveryCatalog(DiscoveryClient discoveryClient) {
            this.discoveryClient = discoveryClient;
        }

        public List<String> listServices() {
            return discoveryClient.getServices();
        }

        public List<ServiceInstance> findInstances(String serviceId) {
            return discoveryClient.getInstances(serviceId);
        }
    }

Khi debug, hãy in service ID, instance ID, URI và metadata cần thiết. Không ghi secret hoặc dữ liệu nhạy cảm trong metadata vào log.

    for (ServiceInstance instance :
            discoveryClient.getInstances("inventory-service")) {
        log.info(
                "serviceId={}, instanceId={}, uri={}, metadata={}",
                instance.getServiceId(),
                instance.getInstanceId(),
                instance.getUri(),
                instance.getMetadata()
        );
    }

Kết quả giúp xác định ứng dụng đang nhìn thấy service nào và các địa chỉ nào được trả về. Nếu getServices() có inventory-service nhưng getInstances("inventory-service") rỗng, hãy kiểm tra trạng thái đăng ký, health check và tên service ID.

## 7. Ảnh hưởng của health check Consul

Spring Cloud Consul mặc định đăng ký HTTP health check cho service. Consul Agent gọi endpoint /actuator/health theo chu kỳ; nếu check thất bại, instance có thể được đánh dấu critical trong Consul.

Thuộc tính spring.cloud.consul.discovery.query-passing điều khiển việc thêm tham số passing vào truy vấn Consul Health API. Giá trị mặc định là false. Khi đặt true, Consul chỉ trả các instance có health check passing cho truy vấn đó:

    spring:
      cloud:
        consul:
          discovery:
            query-passing: true

Điều này ảnh hưởng trực tiếp tới kết quả getInstances(). Khi query-passing=false, kết quả truy vấn có thể bao gồm instance ở trạng thái warning hoặc critical tùy dữ liệu health và API được sử dụng. Khi query-passing=true, Consul lọc để chỉ trả instance passing.

Đừng nhầm getInstances() với health endpoint. DiscoveryClient hỏi Consul về danh sách instance; Consul dựa trên health check đã ghi nhận để trả kết quả. Endpoint health của ứng dụng có thể thay đổi ngay, trong khi Consul chỉ cập nhật trạng thái sau lần check tiếp theo.

## 8. Tra cứu trực tiếp và gọi dịch vụ qua LoadBalancer

Có hai việc riêng biệt:

1. Tra cứu danh sách instance qua DiscoveryClient.
2. Chọn một instance và gửi request HTTP tới nó.

Khi chỉ dùng DiscoveryClient, ứng dụng phải tự chọn instance và tự xử lý timeout, retry, lỗi kết nối, cũng như việc instance ngừng hoạt động sau lúc tra cứu. Chọn phần tử đầu tiên trong danh sách không phải là một chính sách load balancing đáng tin cậy.

Trong ứng dụng gọi dịch vụ thông thường, nên kết hợp Spring Cloud LoadBalancer. Thêm starter:

    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-loadbalancer</artifactId>
    </dependency>

Cấu hình RestTemplate có load balancing:

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

Gọi service bằng service ID thay vì host cố định:

    @Service
    public class InventoryClient {

        private final RestTemplate restTemplate;

        public InventoryClient(
                @LoadBalanced RestTemplate restTemplate) {
            this.restTemplate = restTemplate;
        }

        public String getItem(String itemId) {
            return restTemplate.getForObject(
                    "http://inventory-service/api/items/{id}",
                    String.class,
                    itemId
            );
        }
    }

Khi gặp URL có host là inventory-service, LoadBalancer sử dụng service ID để lấy danh sách instance từ discovery client rồi chọn một instance theo cơ chế cấu hình. Request được gửi tới URI thực tế của instance đã chọn.

LoadBalancer không biến discovery thành bảo đảm request sẽ thành công. Instance có thể hỏng sau lần health check hoặc giữa lúc chọn và gửi request. Ứng dụng vẫn cần timeout, retry có giới hạn, circuit breaker và xử lý lỗi phù hợp với loại request.

## 9. Lọc service theo tag, datacenter và metadata

Consul hỗ trợ tags để phân loại service. Spring Cloud Consul có thể cấu hình tag khi đăng ký và cấu hình truy vấn server list theo tag. Ví dụ đăng ký:

    spring:
      cloud:
        consul:
          discovery:
            tags:
              - api
              - internal
              - version-v2

Khi cần giới hạn truy vấn theo tag, có thể cấu hình server-list-query-tags theo service ID. Ví dụ:

    spring:
      cloud:
        consul:
          discovery:
            server-list-query-tags:
              inventory-service: api

Tùy chọn này áp dụng bộ lọc tag cho truy vấn danh sách instance của service tương ứng. Cần bảo đảm tag đã được đăng ký đúng trong Consul; nếu tag không khớp, kết quả có thể rỗng.

Với Consul cluster nhiều datacenter, tên service ID đơn thuần chưa đủ để chỉ ra datacenter đích. Spring Cloud Consul hỗ trợ cấu hình datacenters theo service ID, ví dụ:

    spring:
      cloud:
        consul:
          discovery:
            datacenters:
              inventory-service: dc-west

Hãy xác minh tên datacenter trong Consul và khả năng truy cập liên datacenter trước khi dùng. Không coi metadata hoặc tag là cơ chế bảo mật; dữ liệu này chỉ hỗ trợ phân loại và lọc.

## 10. DiscoveryClientHealthIndicator

Khi Consul Discovery được bật trong ứng dụng Spring Boot Actuator, Spring Cloud có thể cấu hình DiscoveryClientHealthIndicator. Indicator này dùng discovery client để kiểm tra khả năng truy vấn service discovery.

Theo mặc định, health indicator có thể gọi getServices() để kiểm tra và báo trạng thái. Trong hệ thống có rất nhiều service, truy vấn toàn bộ danh sách service ở mỗi lần health check có thể tốn chi phí. Có thể cấu hình:

    spring:
      cloud:
        discovery:
          client:
            health-indicator:
              use-services-query: false

Khi use-services-query=false, indicator sử dụng probe() thay vì truy vấn toàn bộ service list. Đây là lựa chọn hữu ích khi chỉ cần xác nhận discovery client có thể gọi provider.

DiscoveryClientHealthIndicator phản ánh khả năng của discovery client, không xác nhận tất cả service instance đều khỏe. Health check riêng của từng service trong Consul vẫn là nguồn trạng thái instance.

## 11. Xử lý lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| getServices() trả danh sách rỗng | Consul chưa có service hoặc ứng dụng không kết nối được Consul | Kiểm tra Consul Agent, service catalog và log |
| getInstances() trả rỗng | Sai service ID, service chưa đăng ký hoặc query-passing lọc hết instance | So khớp spring.application.name/service-name và trạng thái health |
| URI trả về không truy cập được | Hostname/IP được đăng ký không thể truy cập từ consumer | Kiểm tra DNS, network, prefer-ip-address và địa chỉ đăng ký |
| Gọi qua LoadBalancer báo không có instance | Discovery trả danh sách rỗng hoặc service ID trong URL sai | Kiểm tra tên host trong URL và discovery client |
| Một instance critical vẫn xuất hiện | query-passing=false hoặc truy vấn không lọc passing | Kiểm tra cấu hình query-passing và Consul Health API |
| Chỉ chạy được trên máy host | Ứng dụng container dùng localhost sai vị trí | Dùng DNS/service name trong Docker network |
| Discovery health indicator chậm | getServices() tải danh sách lớn ở mỗi lần check | Cân nhắc use-services-query=false và probe() |

Quy trình chẩn đoán nên đi từ provider tới consumer:

1. Kiểm tra Consul Agent đang hoạt động và ứng dụng có thể gọi Consul API.
2. Kiểm tra service có xuất hiện trong Consul Catalog và đúng service ID.
3. Kiểm tra health check của từng instance và trạng thái passing, warning hoặc critical.
4. Gọi getServices() và getInstances(serviceId) để xem dữ liệu mà ứng dụng nhận được.
5. Kiểm tra URI, DNS và kết nối từ đúng môi trường chạy consumer.
6. Nếu dùng LoadBalancer, kiểm tra service ID trong URL, dependency LoadBalancer và log chọn instance.

## 12. Kết luận

Spring Cloud DiscoveryClient cung cấp API chung để liệt kê service ID bằng getServices() và lấy các instance bằng getInstances(serviceId). Với Consul, implementation truy vấn dữ liệu từ Consul và chuyển thành các ServiceInstance gồm URI, host, port và metadata.

DiscoveryClient giúp tách mã ứng dụng khỏi API riêng của registry, nhưng không tự gửi request hoặc bảo đảm instance còn khỏe sau khi tra cứu. Đối với lời gọi service-to-service, nên kết hợp Spring Cloud LoadBalancer để chọn instance và xử lý lỗi mạng. Khi vận hành, cần kiểm tra đúng service ID, trạng thái health, query-passing, địa chỉ instance và khả năng truy cập từ network của consumer.

## Tài liệu tham khảo

- [Spring Cloud Commons — DiscoveryClient API](https://github.com/spring-cloud/spring-cloud-commons/blob/main/spring-cloud-commons/src/main/java/org/springframework/cloud/client/discovery/DiscoveryClient.java)
- [Spring Cloud Consul — Service Discovery](https://docs.spring.io/spring-cloud-consul/reference/discovery.html)
- [Spring Cloud Consul — Common Application Properties](https://docs.spring.io/spring-cloud-consul/reference/appendix.html)
- [Spring Cloud Consul — Discovery Client Usage](https://docs.spring.io/spring-cloud-consul/docs/current/reference/html/quickstart.html)
- [Spring Cloud — SimpleDiscoveryClient](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html)

