# SimpleDiscoveryClient khi dùng danh sách instance từ cấu hình

> **Chương:** DiscoveryClient  
> **Module:** SPRING_CLOUD_CORE

Không phải môi trường nào cũng cần một service registry chuyên dụng. Trong ứng dụng local, integration test, demo hoặc một hệ thống nhỏ có danh sách endpoint ổn định, ta có thể khai báo sẵn các instance của dịch vụ trong cấu hình. Spring Cloud Commons cung cấp **`SimpleDiscoveryClient`** để đọc danh sách này và đưa chúng vào abstraction `DiscoveryClient` mà phần còn lại của ứng dụng có thể sử dụng.

Cơ chế này giúp code gọi dịch vụ làm việc với service ID thay vì gắn cứng hostname và port ở từng nơi. Tuy nhiên, danh sách instance tĩnh chỉ là dữ liệu discovery được nạp từ cấu hình. Nó không tự đăng ký instance, gửi heartbeat, kiểm tra sức khỏe hay đồng bộ vòng đời với một registry bên ngoài. Bài này trình bày cách khai báo instance, đọc qua DiscoveryClient, tích hợp Spring Cloud LoadBalancer, kiểm thử và xác định khi nào danh sách tĩnh là lựa chọn phù hợp trong module **SPRING_CLOUD_CORE**.

## 1. SimpleDiscoveryClient giải quyết vấn đề gì?

Trong một hệ thống nhiều dịch vụ, client thường cần tìm một hoặc nhiều instance theo tên logic. Ví dụ, `order-service` cần gọi `catalog-service` nhưng không muốn phụ thuộc trực tiếp vào địa chỉ của từng máy.

Với service discovery, client hỏi abstraction `DiscoveryClient` để lấy các instance gắn với service ID. Một implementation như Eureka hoặc Consul có thể lấy dữ liệu từ registry tập trung. `SimpleDiscoveryClient` dùng danh sách instance đã khai báo trong cấu hình ứng dụng.

Ví dụ:

- Service ID: `catalog-service`.
- Instance thứ nhất: `http://catalog-1.internal:8081`.
- Instance thứ hai: `http://catalog-2.internal:8081`.

Ứng dụng có thể lấy danh sách hai instance thông qua cùng abstraction `DiscoveryClient`. Thành phần gọi dịch vụ có thể kết hợp danh sách đó với Spring Cloud LoadBalancer để chọn một instance cho mỗi request.

### 1.1. Khi nào danh sách instance tĩnh hữu ích?

| Môi trường/tình huống | Lợi ích |
| --- | --- |
| Local development | Khai báo endpoint của các dịch vụ giả lập hoặc dịch vụ chạy trên máy phát triển |
| Integration test | Cung cấp danh sách instance xác định để test hành vi discovery |
| Demo hoặc workshop | Trình bày service ID và instance mà không cần dựng registry riêng |
| Hệ thống nhỏ, endpoint ổn định | Giảm thành phần hạ tầng cần vận hành |
| Môi trường cô lập | Khai báo các endpoint nội bộ theo profile triển khai |

Danh sách tĩnh đặc biệt phù hợp khi topology ít thay đổi và người vận hành có thể cập nhật cấu hình cùng với quá trình triển khai. Nếu instance thường xuyên được tạo/xóa, thay IP hoặc scale tự động, registry động thường phù hợp hơn.

## 2. SimpleDiscoveryClient và DiscoveryClient

`DiscoveryClient` là abstraction của Spring Cloud Commons. Những phương thức thường dùng gồm:

~~~java
public interface DiscoveryClient {
    String description();
    List<ServiceInstance> getInstances(String serviceId);
    List<String> getServices();
}
~~~

Chi tiết interface có thể có thêm default method hoặc thay đổi theo phiên bản Spring Cloud Commons; ba thao tác trên thể hiện các nhu cầu cốt lõi:

| Phương thức | Ý nghĩa |
| --- | --- |
| `getInstances(serviceId)` | Lấy danh sách instance được biết cho service ID |
| `getServices()` | Lấy các service ID mà client biết |
| `description()` | Mô tả implementation discovery |

`SimpleDiscoveryClient` triển khai abstraction này bằng cách đọc dữ liệu từ `SimpleDiscoveryProperties`. Dữ liệu được tổ chức theo service ID, mỗi service có một danh sách instance.

Khi gọi `getInstances("catalog-service")`, client nhận danh sách instance được khai báo cho key `catalog-service`. Nếu service ID không tồn tại trong cấu hình, kết quả thông thường là danh sách rỗng. `getServices()` trả về các service ID có trong cấu hình.

### 2.1. Service ID khác hostname và IP

Service ID là tên logic mà client dùng để yêu cầu discovery. Hostname/IP và port là địa chỉ của từng instance.

| Thành phần | Ví dụ | Vai trò |
| --- | --- | --- |
| Service ID | `catalog-service` | Tên logic để tìm dịch vụ |
| Instance URI | `http://catalog-1.internal:8081` | Địa chỉ của một instance |
| Host | `catalog-1.internal` | Tên host của instance |
| Port | `8081` | Cổng instance nhận request |
| Metadata | `zone=zone-a` | Thông tin bổ sung về instance |

Một service ID có thể ánh xạ tới nhiều instance. Khi instance thay đổi, danh sách cần được cập nhật trong cấu hình tương ứng hoặc bằng một hệ thống registry khác.

## 3. Khai báo instance trong application.yml

`SimpleDiscoveryClient` đọc danh sách instance từ prefix:

~~~text
spring.cloud.discovery.client.simple.instances
~~~

Mỗi key bên dưới `instances` là một service ID; giá trị là danh sách instance của service đó. Mỗi phần tử thường khai báo `uri` và có thể thêm `metadata`.

Ví dụ:

~~~yaml
spring:
  application:
    name: order-service
  cloud:
    discovery:
      client:
        simple:
          instances:
            catalog-service:
              - uri: http://catalog-1.internal:8081
                metadata:
                  zone: zone-a
                  version: v1
              - uri: http://catalog-2.internal:8081
                metadata:
                  zone: zone-b
                  version: v1
            pricing-service:
              - uri: http://pricing.internal:8082
                metadata:
                  zone: zone-a
~~~

Trong cấu hình này:

- `catalog-service` có hai instance.
- `pricing-service` có một instance.
- URI cho biết scheme, host và port của instance.
- Metadata cung cấp thông tin bổ sung mà ứng dụng hoặc load balancer có thể dùng nếu được thiết kế để đọc nó.

Tên service ID phải nhất quán giữa nơi khai báo và nơi gọi. Nếu client gọi `catalog` trong khi cấu hình chỉ có `catalog-service`, discovery sẽ không tự đoán hai tên này tương đương.

### 3.1. Khai báo nhiều instance cho một service

Một service có thể có một hoặc nhiều instance:

~~~yaml
spring:
  cloud:
    discovery:
      client:
        simple:
          instances:
            inventory-service:
              - uri: http://inventory-a.internal:8090
              - uri: http://inventory-b.internal:8090
              - uri: https://inventory-c.internal:8443
~~~

Có thể dùng HTTP và HTTPS tùy khả năng của client và môi trường. Scheme trong URI giúp biểu diễn instance dùng kết nối bảo mật; vẫn cần cấu hình truststore, chứng thư, hostname verification và chính sách TLS phù hợp ở HTTP client.

Danh sách cấu hình không có nghĩa các instance được kiểm tra kết nối ngay khi ứng dụng khởi động. Việc URI có cú pháp hợp lệ khác với việc host có phân giải được hoặc port đang lắng nghe.

### 3.2. Metadata của instance

Metadata là map key/value gắn với từng instance. Ví dụ:

~~~yaml
spring:
  cloud:
    discovery:
      client:
        simple:
          instances:
            catalog-service:
              - uri: http://catalog-a.internal:8081
                metadata:
                  zone: zone-a
                  version: v2
                  protocol: http
              - uri: http://catalog-b.internal:8081
                metadata:
                  zone: zone-b
                  version: v2
                  protocol: http
~~~

Metadata có thể mô tả zone, version, nhóm triển khai hoặc nhãn nghiệp vụ. Tuy nhiên, chỉ khai báo metadata không tự tạo hành vi lọc instance. Thành phần tiêu thụ metadata, chẳng hạn một custom supplier hoặc policy của load balancer, phải được cấu hình để sử dụng nó.

Không đưa password, access token, private key hoặc secret vào metadata. Metadata có thể xuất hiện trong log, diagnostic endpoint hoặc code của client.

### 3.3. Dùng profile để tách danh sách theo môi trường

Có thể đặt danh sách instance chung trong `application.yml` và ghi đè theo profile:

`application.yml`:

~~~yaml
spring:
  cloud:
    discovery:
      client:
        simple:
          instances:
            catalog-service:
              - uri: http://localhost:8081
~~~

`application-production.yml`:

~~~yaml
spring:
  cloud:
    discovery:
      client:
        simple:
          instances:
            catalog-service:
              - uri: http://catalog-a.internal:8081
              - uri: http://catalog-b.internal:8081
~~~

Khi profile production active, Spring Boot nạp cấu hình profile theo quy tắc Config Data và property source precedence. Với list, quy tắc merge/binding có thể khác scalar; không giả định phần tử local sẽ được nối vào danh sách production. Hãy kiểm thử kết quả bind của đúng phiên bản Spring Boot đang sử dụng.

Không để endpoint local làm fallback vô tình trong production nếu service cần gọi endpoint nội bộ. Có thể dùng validation hoặc kiểm tra cấu hình theo môi trường để fail-fast khi service ID quan trọng thiếu instance.

## 4. Đọc instance qua DiscoveryClient

Khi SimpleDiscoveryClient được cấu hình và được chọn làm implementation, ứng dụng có thể inject abstraction `DiscoveryClient` thay vì phụ thuộc trực tiếp vào class cụ thể.

Ví dụ:

~~~java
import java.util.List;

import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.discovery.DiscoveryClient;
import org.springframework.stereotype.Service;

@Service
public class CatalogDiscoveryService {

    private final DiscoveryClient discoveryClient;

    public CatalogDiscoveryService(DiscoveryClient discoveryClient) {
        this.discoveryClient = discoveryClient;
    }

    public List<ServiceInstance> catalogInstances() {
        return discoveryClient.getInstances("catalog-service");
    }

    public List<String> knownServices() {
        return discoveryClient.getServices();
    }
}
~~~

Code gọi discovery không cần biết instance đến từ YAML, Eureka hay một implementation khác. Đây là lợi ích của abstraction trong Spring Cloud Commons.

### 4.1. Đọc thông tin của ServiceInstance

Mỗi phần tử là một `ServiceInstance`. Ví dụ:

~~~java
import java.net.URI;
import java.util.List;
import java.util.Map;

import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.discovery.DiscoveryClient;

List<ServiceInstance> instances =
        discoveryClient.getInstances("catalog-service");

for (ServiceInstance instance : instances) {
    String serviceId = instance.getServiceId();
    String host = instance.getHost();
    int port = instance.getPort();
    boolean secure = instance.isSecure();
    URI uri = instance.getUri();
    Map<String, String> metadata = instance.getMetadata();
}
~~~

Các thuộc tính thường cần:

- `getServiceId()`: service ID gắn với instance.
- `getHost()` và `getPort()`: địa chỉ host và port.
- `isSecure()`: instance được đánh dấu sử dụng kết nối bảo mật.
- `getUri()`: URI cơ sở của instance.
- `getMetadata()`: metadata bổ sung.
- `getInstanceId()`: ID instance nếu implementation cung cấp.

Không nên tự ghép URI từ chuỗi host và port nếu đã có `getUri()`. Cách biểu diễn IPv6, scheme và port có thể cần xử lý chính xác; dùng API ServiceInstance giúp code nhất quán hơn.

### 4.2. Xử lý service ID không có instance

Khi service ID chưa được khai báo hoặc danh sách rỗng, code cần có chính sách rõ ràng:

~~~java
public ServiceInstance requireCatalogInstance() {
    List<ServiceInstance> instances =
            discoveryClient.getInstances("catalog-service");

    if (instances.isEmpty()) {
        throw new IllegalStateException(
                "No instances configured for catalog-service");
    }

    return instances.get(0);
}
~~~

Ví dụ này chọn phần tử đầu để minh họa cách kiểm tra rỗng, không phải chiến lược load balancing phù hợp cho production. Nếu có nhiều instance, hãy để Spring Cloud LoadBalancer hoặc policy riêng chọn instance thay vì luôn gọi phần tử đầu.

## 5. SimpleDiscoveryClient có tự cân bằng tải không?

`SimpleDiscoveryClient` cung cấp danh sách instance thông qua `DiscoveryClient`. Nó **không tự chọn instance cho từng request**. Việc chọn instance là trách nhiệm của client gọi dịch vụ hoặc một cơ chế load balancing.

Spring Cloud LoadBalancer tích hợp với DiscoveryClient để lấy danh sách instance và chọn một instance theo chính sách đang cấu hình. Vì vậy, hai khái niệm cần tách biệt:

- Discovery trả lời: service này có những instance nào?
- Load balancing trả lời: request hiện tại nên được gửi tới instance nào?

### 5.1. Tích hợp với WebClient và Spring Cloud LoadBalancer

Với ứng dụng reactive, có thể đánh dấu `WebClient.Builder` bằng `@LoadBalanced`:

~~~java
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration(proxyBeanMethods = false)
public class HttpClientConfiguration {

    @Bean
    @LoadBalanced
    WebClient.Builder loadBalancedWebClientBuilder() {
        return WebClient.builder();
    }
}
~~~

Service sử dụng tên logic thay vì hostname cố định:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;

import reactor.core.publisher.Mono;

@Service
public class CatalogClient {

    private final WebClient webClient;

    public CatalogClient(WebClient.Builder loadBalancedWebClientBuilder) {
        this.webClient = loadBalancedWebClientBuilder.build();
    }

    public Mono<String> getProduct(String productId) {
        return webClient.get()
                .uri("http://catalog-service/api/products/{id}", productId)
                .retrieve()
                .bodyToMono(String.class);
    }
}
~~~

Trong URI, `catalog-service` là service ID. Spring Cloud LoadBalancer tìm các instance qua DiscoveryClient rồi chọn instance phù hợp. Ứng dụng cần dependency Spring Cloud LoadBalancer tương thích và cấu hình WebClient/load-balancer đúng với phiên bản đang sử dụng.

Nếu không có load-balanced client, URI chứa tên service có thể được HTTP client hiểu như hostname DNS thông thường. Chỉ khai báo SimpleDiscoveryClient không khiến mọi lệnh HTTP tự động đi qua discovery.

### 5.2. Chiến lược chọn instance

Danh sách instance là đầu vào cho load balancer. Chiến lược lựa chọn có thể là round robin hoặc policy khác tùy cấu hình và phiên bản. Không nên giả định thứ tự YAML là cam kết instance đầu tiên luôn được gọi, hoặc metadata zone tự động được dùng để ưu tiên local zone.

Nếu cần zone preference, sticky behavior, weighted routing hoặc loại bỏ instance theo metadata, hãy cấu hình supplier/policy tương ứng của Spring Cloud LoadBalancer. Đừng đặt logic lựa chọn rải rác trong các service nghiệp vụ.

## 6. SimpleDiscoveryClient được kích hoạt khi nào?

Trong cấu hình Spring Cloud thông thường, `SimpleDiscoveryClient` là lựa chọn đơn giản khi không có implementation `DiscoveryClient` khác được cung cấp. Nếu ứng dụng thêm một discovery provider như Eureka hoặc Consul, auto-configuration có thể không còn chọn SimpleDiscoveryClient làm implementation mặc định vì đã có provider khác.

Điều này có nghĩa việc chỉ thêm YAML `spring.cloud.discovery.client.simple.instances` không bảo đảm danh sách tĩnh sẽ được hợp nhất với dữ liệu của một registry khác.

Khi ứng dụng có nhiều discovery implementation, cần xác định rõ:

- Bean `DiscoveryClient` nào đang được tạo.
- Thứ tự hoặc cơ chế composite nào đang được sử dụng.
- LoadBalancer nhận danh sách instance từ supplier nào.
- Có provider nào bị auto-configuration back off do điều kiện bean hay không.

Không giả định SimpleDiscoveryClient và Eureka/Consul tự động hợp nhất mọi instance. Nếu thật sự cần kết hợp nhiều nguồn, phải thiết kế composite hoặc supplier phù hợp và kiểm thử thứ tự, trùng lặp, xử lý lỗi.

## 7. SimpleDiscoveryClient không phải service registry

Danh sách tĩnh có thể cung cấp thông tin discovery, nhưng không có đầy đủ chức năng của một registry động.

| Khả năng | SimpleDiscoveryClient từ cấu hình |
| --- | --- |
| Lấy danh sách instance theo service ID | Có |
| Trả danh sách service đã khai báo | Có |
| Đọc metadata của instance | Có |
| Tự đăng ký instance local khi ứng dụng start | Không |
| Heartbeat/lease với registry | Không |
| Tự phát hiện instance chết | Không |
| Tự deregister khi ứng dụng stop | Không |
| Theo dõi autoscaling hoặc IP thay đổi | Không |
| Phân phối thay đổi tới các client khác | Không |

Nếu một endpoint bị down, instance vẫn có thể còn trong danh sách cấu hình. Request sẽ thất bại trừ khi có health-check integration, retry, circuit breaker hoặc một cơ chế cập nhật danh sách khác.

Với hệ thống có instance thay đổi liên tục, registry động hoặc discovery do nền tảng cung cấp thường phù hợp hơn. SimpleDiscoveryClient có thể vẫn hữu ích cho test hoặc một số endpoint cố định, nhưng không nên xem nó là hệ thống quản lý vòng đời instance.

## 8. Kiểm thử SimpleDiscoveryClient

Một integration test có thể nạp danh sách instance từ test properties rồi kiểm tra kết quả của DiscoveryClient.

~~~java
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.discovery.DiscoveryClient;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(properties = {
        "spring.cloud.discovery.client.simple.instances.catalog-service[0].uri=http://catalog-a.test:8081",
        "spring.cloud.discovery.client.simple.instances.catalog-service[0].metadata.zone=zone-a",
        "spring.cloud.discovery.client.simple.instances.catalog-service[1].uri=http://catalog-b.test:8081",
        "spring.cloud.discovery.client.simple.instances.catalog-service[1].metadata.zone=zone-b"
})
class SimpleDiscoveryClientTest {

    @Autowired
    DiscoveryClient discoveryClient;

    @Test
    void returnsConfiguredInstances() {
        List<ServiceInstance> instances =
                discoveryClient.getInstances("catalog-service");

        assertThat(instances).hasSize(2);
        assertThat(instances)
                .extracting(ServiceInstance::getHost)
                .containsExactly("catalog-a.test", "catalog-b.test");

        assertThat(instances.get(0).getPort()).isEqualTo(8081);
        assertThat(instances.get(0).getMetadata().get("zone"))
                .isEqualTo("zone-a");
    }

    @Test
    void returnsEmptyListForUnknownService() {
        assertThat(discoveryClient.getInstances("unknown-service"))
                .isEmpty();
    }

    @Test
    void exposesConfiguredServiceIds() {
        assertThat(discoveryClient.getServices())
                .contains("catalog-service");
    }
}
~~~

Test giả định context không có discovery provider khác khiến SimpleDiscoveryClient auto-configuration back off. Nếu test dùng chung application context với Eureka, Consul hoặc provider khác, hãy kiểm tra bean được inject trước khi kết luận cấu hình SimpleDiscoveryClient bị bỏ qua.

### 8.1. Kiểm thử luồng load balancing

Ngoài test discovery, nên kiểm tra client thực sự dùng Spring Cloud LoadBalancer:

- Cấu hình hai instance test có thể truy cập.
- Gọi URI theo service ID qua client có `@LoadBalanced`.
- Xác nhận request được gửi tới instance đã được chọn.
- Kiểm tra hành vi khi một instance lỗi hoặc không thể kết nối.
- Kiểm tra retry/circuit breaker nếu ứng dụng có bật chúng.

Không chỉ kiểm tra danh sách instance rồi kết luận load balancing hoạt động. Hai lớp có trách nhiệm khác nhau và cần test riêng.

## 9. Cập nhật danh sách instance và quản lý môi trường

Danh sách instance tĩnh là một phần của cấu hình. Khi endpoint thay đổi, cần cập nhật nguồn cấu hình và triển khai/refresh theo chính sách của ứng dụng.

Một số lưu ý:

- Với local/test, có thể dùng profile hoặc test properties để cung cấp danh sách riêng.
- Với staging/production, quản lý endpoint theo nguồn cấu hình được kiểm soát và tránh commit thông tin môi trường nhạy cảm.
- Khi một instance được thay thế, cập nhật URI và xác nhận client không còn gọi endpoint cũ.
- Không giả định việc thay đổi YAML trên đĩa sẽ tự cập nhật object đã bind trong JVM đang chạy.
- Nếu dùng Spring Cloud Config và refresh, hãy kiểm tra đúng phiên bản và cơ chế rebinding/refresh của properties. Việc Environment được cập nhật không đồng nghĩa mọi consumer đã nhận danh sách mới.
- Với danh sách thay đổi thường xuyên, đánh giá registry động thay vì liên tục sửa cấu hình tĩnh.

Nếu có nhiều profile, hãy kiểm thử kết quả cuối cùng của danh sách sau khi Config Data và property source precedence được áp dụng. Cần đặc biệt chú ý quy tắc binding list khi profile ghi đè cấu hình chung.

## 10. Bảo mật và vận hành

Danh sách instance thường chứa hostname, IP, port và metadata nội bộ. Đây là thông tin topology của hệ thống, nên cần quản lý phù hợp:

- Không commit endpoint nội bộ nhạy cảm vào repository công khai.
- Không đưa token, password hoặc credential vào metadata.
- Dùng TLS và trust configuration đúng khi instance dùng HTTPS.
- Kiểm soát quyền thay đổi cấu hình discovery; endpoint sai có thể chuyển traffic tới host không mong muốn.
- Theo dõi service ID không có instance và lỗi kết nối tới instance.
- Ghi nhận cấu hình hiệu lực theo môi trường mà không log secret.
- Kiểm tra DNS, routing, firewall và network policy từ network namespace của client.
- Có quy trình cập nhật endpoint khi instance thay đổi hoặc bị gỡ bỏ.

Một URI hợp lệ về cú pháp không chứng minh service đang hoạt động. Cần health check hoặc kiểm tra kết nối ở tầng phù hợp nếu yêu cầu vận hành cần biết instance còn phục vụ hay không.

## 11. Lỗi thường gặp và cách tránh

1. **Gọi sai service ID:** key dưới `instances` phải khớp tên logic client yêu cầu.
2. **Nhầm SimpleDiscoveryClient với registry:** danh sách tĩnh không có heartbeat, registration hay deregistration.
3. **Mong SimpleDiscoveryClient tự load balance:** cần Spring Cloud LoadBalancer hoặc code lựa chọn instance riêng.
4. **Thiếu dependency LoadBalancer:** `@LoadBalanced` không có tác dụng nếu dependency và auto-configuration tương ứng không có mặt.
5. **Cho rằng YAML list order quyết định request:** policy load balancer mới quyết định instance được chọn.
6. **Kỳ vọng metadata tự lọc instance:** phải có supplier/policy đọc metadata.
7. **Khai báo provider khác nhưng mong simple list được hợp nhất:** kiểm tra auto-configuration và DiscoveryClient bean thực tế.
8. **Dùng endpoint local trong production:** tách cấu hình bằng profile và kiểm tra danh sách hiệu lực.
9. **Tin rằng instance trong list đang khỏe:** SimpleDiscoveryClient không tự probe health.
10. **Sửa file cấu hình và mong JVM tự nhận:** xác định cơ chế reload/rebind hoặc triển khai lại.
11. **Không kiểm thử DNS/routing:** hostname phân giải được từ máy developer chưa chắc phân giải được từ container chạy client.
12. **Đưa secret vào metadata:** chỉ lưu thông tin không nhạy cảm và giới hạn quyền đọc log/diagnostic.

## 12. Quy trình áp dụng

Khi dùng SimpleDiscoveryClient trong một ứng dụng Spring Cloud, hãy thực hiện theo trình tự:

1. Xác định các service ID mà client cần gọi.
2. Khai báo từng instance dưới `spring.cloud.discovery.client.simple.instances`.
3. Dùng URI với scheme, hostname và port đúng; thêm metadata chỉ khi có consumer sử dụng.
4. Xác minh SimpleDiscoveryClient thực sự là DiscoveryClient implementation đang hoạt động.
5. Nếu cần gọi theo service ID, cấu hình Spring Cloud LoadBalancer và client có `@LoadBalanced`.
6. Kiểm tra danh sách bằng `DiscoveryClient.getInstances()` và `getServices()`.
7. Viết test cho service có nhiều instance, service không tồn tại và metadata.
8. Kiểm thử riêng lựa chọn instance và khả năng kết nối thực tế.
9. Tách danh sách theo profile/môi trường và xác minh quy tắc merge.
10. Đánh giá registry động nếu instance thay đổi thường xuyên.

**Điểm ghi nhớ:** SimpleDiscoveryClient biến danh sách instance khai báo trong cấu hình thành dữ liệu cho abstraction DiscoveryClient. Nó phù hợp với endpoint tĩnh, local development, demo và test; Spring Cloud LoadBalancer có thể sử dụng danh sách này để chọn instance khi client được cấu hình đúng. Danh sách tĩnh không tự đăng ký, heartbeat, health-check hay cập nhật vòng đời instance. Hãy tách rõ discovery, load balancing và service registration khi thiết kế giao tiếp giữa các dịch vụ trong **SPRING_CLOUD_CORE**.
