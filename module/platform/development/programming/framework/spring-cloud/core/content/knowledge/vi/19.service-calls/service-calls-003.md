# Chọn instance, tái dựng URI và thực thi yêu cầu

Trong hệ thống microservice, ứng dụng thường gọi một dịch vụ bằng tên logic như `inventory-service` thay vì gắn cứng hostname và port của một máy. Một service có thể có nhiều instance, mỗi instance chạy trên host/port khác nhau và có thể thay đổi khi triển khai, scale hoặc khôi phục sự cố.

Spring Cloud LoadBalancer xử lý lời gọi đó ở phía client. Nó lấy danh sách instance từ service discovery, chọn một `ServiceInstance`, thay host logic trong URI bằng địa chỉ vật lý của instance, rồi để HTTP client gửi request tới địa chỉ đó. Với các client được đánh dấu `@LoadBalanced`, phần lớn quy trình được thực hiện tự động khi code gọi URL chứa service ID.

Bài học thuộc chương **Gọi dịch vụ** của module **SPRING_CLOUD_CORE**. Nội dung đi theo toàn bộ vòng đời một request: chuẩn bị instance list, chọn instance, tái dựng URI, thực thi HTTP request, xử lý trường hợp không có instance và kiểm tra kết quả.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt service ID logic với hostname và port của một service instance.
- Giải thích vai trò của `DiscoveryClient`, `ServiceInstanceListSupplier` và `ReactiveLoadBalancer`.
- Đọc các trường quan trọng của `ServiceInstance`.
- Mô tả cách thuật toán load balancing chọn một instance từ danh sách khả dụng.
- Dùng `LoadBalancerClient.choose()` để chọn instance và `reconstructURI()` để tạo URI vật lý.
- Giải thích cách `@LoadBalanced` tích hợp với `RestTemplate`, `RestClient` và `WebClient`.
- Hiểu vì sao scheme, port, path, query và URI encoding phải được xử lý khi tái dựng URI.
- Phân biệt việc chọn instance với việc thực thi HTTP request.
- Nhận diện lỗi khi không có instance, instance đã ngừng hoạt động hoặc danh sách instance bị cache cũ.
- Kiểm thử quá trình tái dựng URI và quan sát instance thực tế nhận request.

## 2. Vì sao cần chọn instance ở phía client?

Giả sử hệ thống có một dịch vụ kho hàng tên `inventory-service`. Registry đang ghi nhận ba instance:

| Instance | Host | Port | Trạng thái |
| --- | --- | ---: | --- |
| `inventory-1` | `10.20.1.11` | 8081 | UP |
| `inventory-2` | `10.20.1.12` | 8081 | UP |
| `inventory-3` | `10.20.1.13` | 8081 | UP |

Order service cần lấy danh sách sản phẩm. Nếu gọi trực tiếp `http://10.20.1.11:8081/api/items`, ứng dụng đã gắn cứng vào một instance. Khi instance đó bị thay thế hoặc scale xuống, lời gọi sẽ lỗi dù hai instance còn lại vẫn hoạt động.

Thay vào đó, ứng dụng gọi bằng service ID:

~~~text
http://inventory-service/api/items
~~~

`inventory-service` là tên logic. LoadBalancer lấy các instance tương ứng, chọn một instance, rồi chuyển URI thành địa chỉ thực, ví dụ:

~~~text
http://10.20.1.12:8081/api/items
~~~

Ở request tiếp theo, thuật toán có thể chọn instance khác. Code nghiệp vụ không phải biết trước danh sách IP hay tự quản lý vòng quay instance.

### 2.1. Discovery và load balancing là hai bước liên quan

Service discovery trả lời câu hỏi: **hiện có những instance nào của service?**

Client-side load balancing trả lời câu hỏi: **request hiện tại nên gửi tới instance nào?**

Spring Cloud LoadBalancer sử dụng abstraction discovery có trong classpath, chẳng hạn `DiscoveryClient`, để lấy danh sách instance. Sau đó `ServiceInstanceListSupplier` cung cấp danh sách cho `ReactiveLoadBalancer` chọn một instance.

~~~mermaid
flowchart LR
    A[HTTP client request] --> B[Service ID]
    B --> C[ServiceInstanceListSupplier]
    C --> D[DiscoveryClient]
    D --> E[Available ServiceInstance list]
    E --> F[ReactiveLoadBalancer]
    F --> G[Selected ServiceInstance]
    G --> H[Reconstruct physical URI]
    H --> I[Execute HTTP request]
    I --> J[Remote service instance]
~~~

Nếu registry không có dữ liệu hoặc không có instance khả dụng, LoadBalancer không thể tự tạo ra địa chỉ đích hợp lệ. Việc có một bean `DiscoveryClient` cũng không đảm bảo rằng service ID đã có instance đang hoạt động.

## 3. ServiceInstance chứa thông tin gì?

`ServiceInstance` là abstraction mô tả một instance của service trong hệ thống discovery. Các trường thường được dùng:

| Method | Ý nghĩa |
| --- | --- |
| `getInstanceId()` | ID duy nhất của instance theo registry, nếu provider có cung cấp |
| `getServiceId()` | Service ID mà instance đã đăng ký |
| `getHost()` | Hostname hoặc IP của instance |
| `getPort()` | Port instance đang lắng nghe |
| `isSecure()` | Cho biết kết nối tới port của instance có dùng HTTPS hay không |
| `getUri()` | URI của instance |
| `getMetadata()` | Metadata dạng key/value do registry/provider cung cấp |
| `getScheme()` | Scheme tường minh nếu implementation có cung cấp |

Ví dụ một instance:

~~~text
serviceId = inventory-service
instanceId = inventory-2
host       = 10.20.1.12
port       = 8081
secure     = false
metadata   = {zone=zone-a, version=v2}
~~~

Thông tin này đủ để xây dựng endpoint vật lý và có thể được dùng cho các chính sách chọn instance như ưu tiên zone hoặc lọc theo metadata.

### 3.1. ServiceInstance.getUri()

Implementation mặc định `DefaultServiceInstance` tạo URI dựa trên host, port và cờ secure. Nếu `isSecure()` là `true`, URI mặc định dùng `https`; nếu là `false`, dùng `http`. Khi port không được chỉ định, cách tạo URI mặc định có thể dùng port chuẩn của scheme.

Không nên tự giả định mọi provider tạo `ServiceInstance` giống nhau. Một implementation có thể cung cấp scheme tường minh hoặc metadata riêng. Khi cần tái dựng URI cho request, hãy dùng `LoadBalancerClient.reconstructURI()` hoặc tích hợp load-balanced HTTP client thay vì tự nối chuỗi.

## 4. Chuẩn bị Spring Cloud LoadBalancer

Spring Cloud LoadBalancer cần một nguồn instance, thường là DiscoveryClient từ provider như Eureka hoặc Consul, và module LoadBalancer.

### 4.1. Dependency

Thêm starter LoadBalancer:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-loadbalancer</artifactId>
</dependency>
~~~

Ứng dụng cũng cần dependency của service discovery provider nếu muốn lấy instance từ registry, ví dụ Consul Discovery hoặc Eureka Client. Version của các dependency Spring Cloud nên được quản lý bằng Spring Cloud BOM tương thích với Spring Boot của dự án.

### 4.2. Ví dụ cấu hình tên service

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

Đây là cấu hình minh họa cho Consul. Với Eureka hoặc provider khác, dùng các property riêng của provider. Điều quan trọng đối với LoadBalancer là DiscoveryClient phải trả về instance có service ID đúng với tên logic mà client sử dụng.

### 4.3. Dữ liệu tĩnh để phát triển và kiểm thử

Nếu không muốn chạy registry trong môi trường local, có thể dùng `SimpleDiscoveryClient` với danh sách instance cấu hình tĩnh:

~~~yaml
spring:
  cloud:
    discovery:
      client:
        simple:
          instances:
            inventory-service:
              - uri: http://localhost:8081
              - uri: http://localhost:8082
~~~

Khi không có registry-backed DiscoveryClient, Spring Cloud Commons có thể sử dụng `SimpleDiscoveryClient`. Cách này hữu ích để kiểm thử chọn instance và URI mà không cần dựng Eureka/Consul. Nó không tự đăng ký instance lên registry từ xa.

## 5. LoadBalancer chọn instance như thế nào?

Spring Cloud LoadBalancer tạo một LoadBalancer context riêng cho từng service ID. Context thường được khởi tạo lazy khi request đầu tiên tới service đó cần được cân bằng tải.

### 5.1. ServiceInstanceListSupplier

`ServiceInstanceListSupplier` cung cấp danh sách instance cho LoadBalancer. Supplier có thể:

- Lấy danh sách từ `DiscoveryClient`.
- Đọc danh sách cấu hình tĩnh.
- Cache danh sách instance.
- Lọc theo zone hoặc metadata.
- Chỉ giữ các instance được health check xác nhận.
- Áp dụng preference hoặc hint theo request.

Supplier có thể được xếp thành chuỗi delegate. Ví dụ, một supplier lấy dữ liệu từ discovery, sau đó supplier cache giữ danh sách, rồi supplier khác lọc theo zone.

### 5.2. Thuật toán mặc định

Spring Cloud LoadBalancer cung cấp `RoundRobinLoadBalancer` và `RandomLoadBalancer`. Cấu hình mặc định hiện hành sử dụng `RoundRobinLoadBalancer`.

Với ba instance khả dụng, round robin có thể phân phối các request tuần tự theo dạng:

~~~text
Request 1 -> inventory-1
Request 2 -> inventory-2
Request 3 -> inventory-3
Request 4 -> inventory-1
Request 5 -> inventory-2
...
~~~

Đây là mô hình minh họa. Trong môi trường thực tế, thứ tự có thể thay đổi khi danh sách instance được cập nhật, nhiều client process cùng gửi request hoặc có supplier lọc instance.

Random chọn ngẫu nhiên một instance trong danh sách đã được cung cấp. Có thể thay đổi thuật toán bằng custom LoadBalancer configuration cho toàn bộ ứng dụng hoặc một service ID cụ thể.

### 5.3. Cache danh sách instance

Spring Cloud LoadBalancer hỗ trợ cache instance list. Cấu hình mặc định hiện hành có TTL 35 giây và capacity ban đầu 256. Có thể điều chỉnh:

~~~yaml
spring:
  cloud:
    loadbalancer:
      cache:
        ttl: 20s
        capacity: 512
~~~

Có thể tắt cache:

~~~yaml
spring:
  cloud:
    loadbalancer:
      cache:
        enabled: false
~~~

Cache giảm số lần truy vấn discovery, nhưng có thể khiến client giữ danh sách cũ trong một khoảng thời gian sau khi instance thay đổi. Nếu DiscoveryClient provider đã cache dữ liệu, chẳng hạn Eureka Discovery Client, hãy xem xét tắt một lớp cache để tránh double caching và độ trễ cập nhật cộng dồn.

Không nên đặt TTL quá dài nếu hệ thống cần phản ứng nhanh khi instance bị loại khỏi registry. TTL quá ngắn lại tăng tải truy vấn discovery. Chọn theo tốc độ thay đổi instance, quy mô registry và yêu cầu vận hành.

### 5.4. Lọc instance theo zone hoặc health

`ZonePreferenceServiceInstanceListSupplier` có thể ưu tiên instance cùng zone. Zone có thể được lấy từ metadata của DiscoveryClient hoặc cấu hình `spring.cloud.loadbalancer.zone`.

`HealthCheckServiceInstanceListSupplier` có thể định kỳ kiểm tra instance và ưu tiên trả về các instance khỏe mạnh. Nếu không còn instance nào vượt qua health check, supplier có thể trả lại danh sách instance đã lấy để LoadBalancer vẫn có lựa chọn. Cách này hữu ích hơn với danh sách tĩnh như `SimpleDiscoveryClient`. Khi dùng registry thực tế, registry thường đã cung cấp trạng thái health; cần tránh kiểm tra trùng lặp không cần thiết.

## 6. Chọn instance bằng LoadBalancerClient

`LoadBalancerClient` là blocking abstraction. Nó kế thừa `ServiceInstanceChooser` và cung cấp các thao tác chọn instance, thực thi request và tái dựng URI.

### 6.1. Gọi choose()

~~~java
import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.loadbalancer.LoadBalancerClient;
import org.springframework.stereotype.Service;

@Service
public class InventoryInstanceSelector {

    private final LoadBalancerClient loadBalancerClient;

    public InventoryInstanceSelector(
            LoadBalancerClient loadBalancerClient) {
        this.loadBalancerClient = loadBalancerClient;
    }

    public ServiceInstance chooseInventory() {
        return loadBalancerClient.choose("inventory-service");
    }
}
~~~

`choose(serviceId)` trả về instance được chọn. Nếu không có instance phù hợp, kết quả có thể là `null`; caller cần xử lý trường hợp này thay vì tiếp tục xây URI.

### 6.2. Kiểm tra instance được chọn

~~~java
ServiceInstance instance =
        loadBalancerClient.choose("inventory-service");

if (instance == null) {
    throw new IllegalStateException(
            "No instance available for inventory-service");
}

System.out.printf(
        "Selected serviceId=%s, instanceId=%s, host=%s, port=%d, secure=%s%n",
        instance.getServiceId(),
        instance.getInstanceId(),
        instance.getHost(),
        instance.getPort(),
        instance.isSecure());
~~~

Không log metadata chứa thông tin nhạy cảm nếu provider hoặc ứng dụng đặt credential trong metadata. Log instance ID, host và port chỉ nên được phát ra trong phạm vi quan sát được bảo vệ phù hợp với chính sách mạng của hệ thống.

## 7. Tái dựng URI từ service ID sang địa chỉ vật lý

Sau khi chọn được instance, cần thay host logic trong URI bằng host/port của instance. `LoadBalancerClient.reconstructURI(instance, original)` thực hiện bước đó.

### 7.1. Ví dụ cơ bản

URI ban đầu:

~~~text
http://inventory-service/api/items?status=READY&page=2
~~~

Instance được chọn:

~~~text
host = 10.20.1.12
port = 8081
secure = false
~~~

URI vật lý sau khi tái dựng:

~~~text
http://10.20.1.12:8081/api/items?status=READY&page=2
~~~

Host logic `inventory-service` được thay bằng host của instance. Path và query vẫn được giữ để request tới đúng API và đúng tham số.

### 7.2. Sử dụng reconstructURI()

~~~java
import java.net.URI;

import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.loadbalancer.LoadBalancerClient;

ServiceInstance instance =
        loadBalancerClient.choose("inventory-service");

if (instance == null) {
    throw new IllegalStateException(
            "No instance available for inventory-service");
}

URI logicalUri = URI.create(
        "http://inventory-service/api/items?status=READY&page=2");

URI physicalUri =
        loadBalancerClient.reconstructURI(instance, logicalUri);

System.out.println("Physical URI selected: " + physicalUri);
~~~

`reconstructURI()` dùng thông tin `ServiceInstance` để thay host và port. Việc xử lý scheme cũng xét scheme do instance cung cấp và trạng thái secure. Nếu instance có scheme tường minh, scheme đó được ưu tiên. Nếu không, LoadBalancer dùng scheme ban đầu hoặc mặc định `http`; khi instance yêu cầu bảo mật, scheme không bảo mật tương ứng như `http` có thể được nâng thành `https`.

### 7.3. Port mặc định

Nếu instance có port hợp lệ, URI sử dụng port đó. Nếu port không được cung cấp, implementation URI hiện hành có thể dùng port chuẩn theo scheme, ví dụ `443` cho `https` hoặc `80` cho `http`.

Trong service registration thực tế, nên cung cấp port rõ ràng để tránh phụ thuộc vào default port không phù hợp với cấu hình listener của ứng dụng.

### 7.4. Giữ path, query và fragment

Ví dụ:

~~~text
URI logic:
http://inventory-service/api/items/42?expand=warehouse&sort=name#details

URI vật lý:
http://10.20.1.12:8081/api/items/42?expand=warehouse&sort=name#details
~~~

Host và port được thay theo instance; phần còn lại của URI được giữ trong quá trình dựng lại. Với path/query đã encode, implementation kiểm tra trạng thái encoding trước khi xây URI để tránh encode lại dữ liệu đã encode hoàn chỉnh.

Không tự ghép chuỗi như:

~~~java
String url = "http://" + instance.getHost()
        + ":" + instance.getPort()
        + originalUri.getPath();
~~~

Cách làm này dễ làm mất query string, fragment, scheme, port mặc định, ký tự IPv6 hoặc trạng thái encoding. Dùng `reconstructURI()` để Spring Cloud xử lý đúng các thành phần URI.

### 7.5. HTTPS và secure ServiceInstance

Giả sử instance được đăng ký với `secure=true`:

~~~text
URI logic:
http://inventory-service/api/items

Instance:
host = inventory.internal
port = 8443
secure = true

URI vật lý:
https://inventory.internal:8443/api/items
~~~

Địa chỉ HTTPS phụ thuộc thông tin scheme/secure của instance. Nếu service sử dụng TLS, certificate của server phải hợp lệ với hostname mà client kết nối tới. Nếu registry công bố IP nhưng certificate chỉ chứa DNS name, TLS hostname verification có thể thất bại. Hãy đăng ký hostname phù hợp hoặc cấu hình service endpoint/certificate nhất quán; không tắt kiểm tra certificate để che lỗi định danh.

## 8. Thực thi request thủ công sau khi chọn instance

Chọn instance và tái dựng URI chỉ tạo ra địa chỉ đích. Một HTTP client vẫn phải gửi request tới URI đó.

Ví dụ dùng Spring `RestClient` trực tiếp:

~~~java
import java.net.URI;

import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.loadbalancer.LoadBalancerClient;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClient;

@Service
public class ManualInventoryCaller {

    private final LoadBalancerClient loadBalancerClient;
    private final RestClient restClient;

    public ManualInventoryCaller(
            LoadBalancerClient loadBalancerClient) {
        this.loadBalancerClient = loadBalancerClient;
        this.restClient = RestClient.create();
    }

    public String getItems() {
        ServiceInstance instance =
                loadBalancerClient.choose("inventory-service");

        if (instance == null) {
            throw new IllegalStateException(
                    "No instance available for inventory-service");
        }

        URI logicalUri = URI.create(
                "http://inventory-service/api/items");

        URI physicalUri =
                loadBalancerClient.reconstructURI(instance, logicalUri);

        return restClient.get()
                .uri(physicalUri)
                .retrieve()
                .body(String.class);
    }
}
~~~

Trong ví dụ này, `RestClient` là client thường, không được đánh dấu `@LoadBalanced`, vì code đã tự chọn instance và tái dựng URI vật lý. Nếu vừa tự tái dựng URI vừa dùng load-balanced client cho cùng request, có thể khiến request bị xử lý load balancing hai lần hoặc không còn đúng service ID để chọn.

### 8.1. Khoảng thời gian giữa chọn và gọi

Khi code tự gọi `choose()` rồi mới gửi request, instance có thể bị deregister hoặc ngừng hoạt động trong khoảng thời gian giữa hai thao tác. Vì vậy, việc chọn thành công không đảm bảo kết nối chắc chắn thành công.

Nếu cần tích hợp lifecycle, metrics hoặc retry của LoadBalancer, hãy sử dụng `LoadBalancerClient.execute()` hoặc các HTTP client integration được hỗ trợ thay vì tự quản lý toàn bộ quy trình. Khi tự gọi HTTP client, ứng dụng cần tự xử lý timeout, lỗi kết nối, retry và observability.

### 8.2. Để LoadBalancer chọn instance và gọi callback execute()

`LoadBalancerClient.execute(serviceId, request)` chọn instance cho service rồi gọi callback với `ServiceInstance` đã chọn. Callback có thể tái dựng URI và gửi HTTP request:

~~~java
import java.io.IOException;
import java.net.URI;

import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.loadbalancer.LoadBalancerClient;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClient;

@Service
public class ManagedInventoryCaller {

    private final LoadBalancerClient loadBalancerClient;
    private final RestClient restClient = RestClient.create();

    public ManagedInventoryCaller(LoadBalancerClient loadBalancerClient) {
        this.loadBalancerClient = loadBalancerClient;
    }

    public String getItems() throws IOException {
        URI logicalUri = URI.create(
                "http://inventory-service/api/items");

        return loadBalancerClient.execute(
                "inventory-service",
                (ServiceInstance instance) -> {
                    URI physicalUri = loadBalancerClient.reconstructURI(
                            instance, logicalUri);

                    return restClient.get()
                            .uri(physicalUri)
                            .retrieve()
                            .body(String.class);
                });
    }
}
~~~

Callback này giúp LoadBalancer bao quanh việc thực thi request bằng lifecycle và metrics tương ứng. Ứng dụng vẫn cần xử lý exception, timeout và retry theo chính sách nghiệp vụ. `execute()` không làm cho instance đã chọn trở thành bất khả lỗi; kết nối vẫn có thể thất bại sau khi lựa chọn.

## 9. Thực thi tự động với @LoadBalanced

Trong phần lớn ứng dụng, không cần gọi `choose()` và `reconstructURI()` bằng tay. Có thể đánh dấu HTTP client bean bằng `@LoadBalanced`; Spring Cloud sẽ gắn interceptor hoặc filter tương ứng.

`@LoadBalanced` là qualifier để đánh dấu `RestTemplate`, `RestClient.Builder` hoặc `WebClient.Builder` cần dùng LoadBalancer.

### 9.1. RestTemplate

Khai báo bean:

~~~java
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestTemplate;

@Configuration
public class HttpClientConfiguration {

    @Bean
    @LoadBalanced
    RestTemplate loadBalancedRestTemplate() {
        return new RestTemplate();
    }
}
~~~

Sử dụng:

~~~java
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestTemplate;

@Service
public class InventoryClient {

    private final RestTemplate restTemplate;

    public InventoryClient(
            @LoadBalanced RestTemplate restTemplate) {
        this.restTemplate = restTemplate;
    }

    public String getItems() {
        return restTemplate.getForObject(
                "http://inventory-service/api/items",
                String.class);
    }
}
~~~

URI dùng service ID làm host. Interceptor của LoadBalancer lấy service ID, chọn instance, tái dựng URI và chuyển request tới instance đã chọn.

Spring Boot không tự tạo một `RestTemplate` load-balanced cho mọi ứng dụng. Ứng dụng cần khai báo bean và gắn qualifier `@LoadBalanced`.

### 9.2. Phân biệt RestTemplate thường và load-balanced

Có thể cần cả client gọi host cố định và client gọi service ID:

~~~java
import org.springframework.context.annotation.Primary;

@Configuration
public class HttpClientConfiguration {

    @Bean
    @LoadBalanced
    RestTemplate loadBalancedRestTemplate() {
        return new RestTemplate();
    }

    @Bean
    @Primary
    RestTemplate directRestTemplate() {
        return new RestTemplate();
    }
}
~~~

Inject đúng bean:

~~~java
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.web.client.RestTemplate;

public class OrderClient {

    private final RestTemplate directRestTemplate;
    private final RestTemplate loadBalancedRestTemplate;

    public OrderClient(
            RestTemplate directRestTemplate,
            @LoadBalanced RestTemplate loadBalancedRestTemplate) {
        this.directRestTemplate = directRestTemplate;
        this.loadBalancedRestTemplate = loadBalancedRestTemplate;
    }
}
~~~

`directRestTemplate` dùng URL vật lý như `https://partner.example.com`. `loadBalancedRestTemplate` dùng URL logic như `http://inventory-service`. `@Primary` giúp Spring chọn bean mặc định khi có nhiều bean cùng kiểu và injection không chỉ rõ qualifier.

### 9.3. RestClient

Với Spring `RestClient`, đánh dấu builder:

~~~java
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;

@Configuration
public class RestClientConfiguration {

    @Bean
    @LoadBalanced
    RestClient.Builder loadBalancedRestClientBuilder() {
        return RestClient.builder();
    }
}
~~~

Sử dụng:

~~~java
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClient;

@Service
public class InventoryRestClient {

    private final RestClient restClient;

    public InventoryRestClient(
            @LoadBalanced RestClient.Builder builder) {
        this.restClient = builder.build();
    }

    public String getItems() {
        return restClient.get()
                .uri("http://inventory-service/api/items")
                .retrieve()
                .body(String.class);
    }
}
~~~

LoadBalancer tích hợp với `RestClient` thông qua blocking client. Nếu ứng dụng cũng có builder thường, hãy dùng qualifier và `@Primary` để tránh inject nhầm builder.

### 9.4. WebClient

Với WebFlux, đánh dấu `WebClient.Builder`:

~~~java
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
public class WebClientConfiguration {

    @Bean
    @LoadBalanced
    WebClient.Builder loadBalancedWebClientBuilder() {
        return WebClient.builder();
    }
}
~~~

Sử dụng:

~~~java
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import reactor.core.publisher.Mono;
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;

@Service
public class ReactiveInventoryClient {

    private final WebClient webClient;

    public ReactiveInventoryClient(
            @LoadBalanced WebClient.Builder builder) {
        this.webClient = builder.build();
    }

    public Mono<String> getItems() {
        return webClient.get()
                .uri("http://inventory-service/api/items")
                .retrieve()
                .bodyToMono(String.class);
    }
}
~~~

Với `WebClient`, Spring Cloud sử dụng `ReactiveLoadBalancer` và exchange filter function. Request được xử lý theo mô hình reactive; không cần block để chọn instance.

### 9.5. So sánh ba HTTP client

| Client | Cơ chế tích hợp | API thực thi | Phù hợp |
| --- | --- | --- | --- |
| `RestTemplate` | LoadBalancer interceptor | Blocking | Ứng dụng Spring MVC hiện có |
| `RestClient` | LoadBalancer interceptor | Blocking | HTTP client đồng bộ hiện đại |
| `WebClient` | LoadBalancer exchange filter | Reactive | Spring WebFlux hoặc xử lý reactive |

Các client đều có thể dùng service ID trong URI. Hãy chọn client theo mô hình lập trình của ứng dụng, tránh block một reactive pipeline chỉ để gọi service.

## 10. Một request đi qua LoadBalancer như thế nào?

Với một request từ `RestTemplate` hoặc `RestClient` được đánh dấu `@LoadBalanced`, luồng khái quát:

1. Code gọi HTTP client bằng URI logic, ví dụ `http://inventory-service/api/items`.
2. Interceptor lấy host trong URI làm service ID.
3. LoadBalancer yêu cầu `ServiceInstanceListSupplier` cung cấp danh sách instance.
4. Supplier lấy danh sách từ discovery hoặc cache, rồi áp dụng các bộ lọc được cấu hình.
5. `ReactiveLoadBalancer` chọn một `ServiceInstance`.
6. `BlockingLoadBalancerClient` tái dựng URI vật lý với host, port và scheme của instance.
7. Request được chuyển tới HTTP transport để gửi.
8. Response hoặc exception được trả về cho caller; lifecycle/metrics của LoadBalancer có thể ghi nhận kết quả.

Với `WebClient`, các bước tương tự được phối hợp theo reactive pipeline và không sử dụng blocking client ở bên dưới.

~~~mermaid
sequenceDiagram
    participant Code as Application code
    participant Http as @LoadBalanced HTTP client
    participant LB as Spring Cloud LoadBalancer
    participant Supplier as ServiceInstanceListSupplier
    participant Discovery as DiscoveryClient
    participant Instance as Selected service instance

    Code->>Http: GET http://inventory-service/api/items
    Http->>LB: Resolve service ID inventory-service
    LB->>Supplier: Get available instances
    Supplier->>Discovery: Query service instances
    Discovery-->>Supplier: Instance list
    Supplier-->>LB: Filtered instance list
    LB->>LB: Choose one ServiceInstance
    LB->>LB: Reconstruct physical URI
    LB->>Instance: Execute GET /api/items
    Instance-->>LB: HTTP response
    LB-->>Http: Return response
    Http-->>Code: Decode response body
~~~

## 11. Request transformer: bổ sung thông tin instance đã chọn

Một số hệ thống cần gửi thêm instance ID hoặc metadata của instance đã chọn trong HTTP header. Spring Cloud LoadBalancer cung cấp:

- `LoadBalancerRequestTransformer` cho `RestTemplate` và `RestClient`.
- `LoadBalancerClientRequestTransformer` cho `WebClient`.

Ví dụ thêm header `X-InstanceId`:

~~~java
import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.loadbalancer.LoadBalancerRequestTransformer;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpRequest;
import org.springframework.http.client.support.HttpRequestWrapper;

@Bean
LoadBalancerRequestTransformer instanceHeaderTransformer() {
    return (request, instance) -> new HttpRequestWrapper(request) {
        @Override
        public HttpHeaders getHeaders() {
            HttpHeaders headers = new HttpHeaders();
            headers.putAll(super.getHeaders());

            if (instance != null && instance.getInstanceId() != null) {
                headers.add("X-InstanceId", instance.getInstanceId());
            }

            return headers;
        }
    };
}
~~~

Với WebClient:

~~~java
import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.loadbalancer.LoadBalancerClientRequestTransformer;
import org.springframework.context.annotation.Bean;
import org.springframework.web.reactive.function.client.ClientRequest;

@Bean
LoadBalancerClientRequestTransformer instanceHeaderTransformer() {
    return (request, instance) -> {
        ClientRequest.Builder builder = ClientRequest.from(request);
        if (instance != null && instance.getInstanceId() != null) {
            builder.header("X-InstanceId", instance.getInstanceId());
        }
        return builder.build();
    };
}
~~~

Các transformer được áp dụng theo thứ tự order của bean. Header này hữu ích cho tracing, log hoặc chẩn đoán request đã tới instance nào. Không dùng nó làm cơ chế xác thực; caller có thể giả mạo header nếu không có lớp bảo vệ riêng.

## 12. Khi không có instance hoặc instance không truy cập được

### 12.1. Không tìm thấy instance

Nếu danh sách instance rỗng, LoadBalancer không thể chọn một đích. Với API thủ công, `choose()` có thể trả `null`; code cần dừng trước khi gọi `reconstructURI()`.

Với load-balanced HTTP client, request thường thất bại do không tìm được instance. Khi chẩn đoán, kiểm tra:

- Service ID trong URI có đúng với ID đăng ký không.
- DiscoveryClient có trả về instance không.
- Instance có bị đánh dấu DOWN hoặc OUT_OF_SERVICE không.
- Supplier có lọc hết instance do zone, hint hoặc health check không.
- Cache instance list có đang giữ dữ liệu cũ không.

### 12.2. Có instance nhưng kết nối thất bại

Registry có thể vẫn trả về instance vừa bị crash hoặc chưa kịp deregister. Chọn được instance không đồng nghĩa TCP/TLS hoặc HTTP request sẽ thành công.

Kiểm tra:

- Host/port có thể truy cập từ network namespace của caller không.
- Security group, firewall, NetworkPolicy và routing có cho phép kết nối không.
- Instance có đang lắng nghe đúng port không.
- Scheme HTTP/HTTPS có khớp với listener không.
- Certificate và hostname verification có hợp lệ không.
- Timeout kết nối và timeout đọc response có phù hợp không.

### 12.3. Retry không thay thế việc chọn đúng instance

Retry có thể chọn instance khác nếu được cấu hình và có instance thay thế. Tuy nhiên, retry cần được thiết kế theo loại request:

- Request GET hoặc thao tác idempotent thường dễ retry hơn.
- POST tạo đơn hàng, thanh toán hoặc ghi dữ liệu có thể bị thực hiện hai lần nếu server đã xử lý nhưng response bị mất.
- Cần idempotency key, deduplication hoặc transaction semantics trước khi retry thao tác có side effect.

Đừng giả định mọi lỗi HTTP đều tự động được retry. Cấu hình retry, exception/status code được retry và số lần thử phụ thuộc phiên bản, loại client và LoadBalancer configuration.

## 13. Cấu hình nâng cao theo service ID

Spring Cloud LoadBalancer hỗ trợ cấu hình riêng cho từng service. Ví dụ có thể ưu tiên zone hoặc dùng thuật toán khác cho một service mà không ảnh hưởng service còn lại.

### 13.1. LoadBalancer client riêng

Có thể dùng `@LoadBalancerClient` để chỉ định configuration cho một service ID:

~~~java
import org.springframework.cloud.loadbalancer.annotation.LoadBalancerClient;
import org.springframework.context.annotation.Configuration;

@Configuration
@LoadBalancerClient(
        name = "inventory-service",
        configuration = InventoryLoadBalancerConfiguration.class)
public class LoadBalancerConfiguration {
}
~~~

`InventoryLoadBalancerConfiguration` định nghĩa các bean LoadBalancer dành riêng cho `inventory-service`. Không nên đặt class cấu hình riêng này trong phạm vi component scan thông thường nếu điều đó khiến bean bị áp dụng ngoài service ID dự kiến. Thực hiện theo hướng dẫn của `@LoadBalancerClient` trong release train đang dùng.

### 13.2. Zone preference

Nếu metadata của instance có zone:

~~~text
inventory-1 metadata.zone = zone-a
inventory-2 metadata.zone = zone-a
inventory-3 metadata.zone = zone-b
~~~

`ZonePreferenceServiceInstanceListSupplier` có thể ưu tiên các instance trong zone của caller. Khi không có instance cùng zone, supplier có thể trả lại danh sách ban đầu để LoadBalancer vẫn có lựa chọn.

### 13.3. Cấu hình theo client ID

Một số property có thể được đặt ở mức mặc định hoặc riêng cho từng service ID:

~~~yaml
spring:
  cloud:
    loadbalancer:
      cache:
        ttl: 30s
      clients:
        inventory-service:
          health-check:
            interval: 15s
        pricing-service:
          health-check:
            interval: 45s
~~~

Các property cụ thể được hỗ trợ phụ thuộc loại supplier và phiên bản Spring Cloud LoadBalancer. Không phải mọi property toàn cục đều có thể override theo client ID.

## 14. Kiểm thử việc chọn instance và tái dựng URI

### 14.1. Unit test cho reconstructURI

Có thể kiểm tra URI tái dựng mà không cần chạy registry:

~~~java
import java.net.URI;

import org.junit.jupiter.api.Test;
import org.springframework.cloud.client.DefaultServiceInstance;
import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.loadbalancer.LoadBalancerUriTools;

import static org.assertj.core.api.Assertions.assertThat;

class LoadBalancerUriToolsTest {

    @Test
    void replacesLogicalHostAndKeepsPathAndQuery() {
        ServiceInstance instance = new DefaultServiceInstance(
                "inventory-2",
                "inventory-service",
                "10.20.1.12",
                8081,
                false);

        URI original = URI.create(
                "http://inventory-service/api/items?status=READY&page=2");

        URI reconstructed =
                LoadBalancerUriTools.reconstructURI(instance, original);

        assertThat(reconstructed).isEqualTo(URI.create(
                "http://10.20.1.12:8081/api/items?status=READY&page=2"));
    }

    @Test
    void upgradesHttpToHttpsForSecureInstance() {
        ServiceInstance instance = new DefaultServiceInstance(
                "inventory-secure",
                "inventory-service",
                "inventory.internal",
                8443,
                true);

        URI original = URI.create(
                "http://inventory-service/api/items");

        URI reconstructed =
                LoadBalancerUriTools.reconstructURI(instance, original);

        assertThat(reconstructed).isEqualTo(URI.create(
                "https://inventory.internal:8443/api/items"));
    }
}
~~~

Hai test xác nhận host logic được thay bằng host instance, path/query được giữ và scheme được nâng lên HTTPS khi instance yêu cầu bảo mật.

### 14.2. Kiểm thử với SimpleDiscoveryClient

Trong integration test, cấu hình hai instance tĩnh:

~~~yaml
spring:
  cloud:
    discovery:
      client:
        simple:
          instances:
            inventory-service:
              - uri: http://localhost:8081
              - uri: http://localhost:8082
~~~

Sau đó dùng `@LoadBalanced RestTemplate`, `RestClient.Builder` hoặc `WebClient.Builder` để gọi `http://inventory-service/...`. Có thể khởi động hai HTTP test server trên hai port khác nhau; mỗi server trả về tên instance để quan sát request đã được gửi tới đâu.

### 14.3. Test case cần có

| Test case | Điều cần xác nhận |
| --- | --- |
| Một instance | Request được gửi tới đúng host/port |
| Nhiều instance với round robin | Các request liên tiếp được phân phối theo thuật toán mặc định |
| Instance list rỗng | Request thất bại rõ ràng và không tạo URI sai |
| Instance secure | Scheme của URI vật lý phù hợp HTTPS |
| Query có ký tự đã encode | Query không bị encode hai lần hoặc mất dữ liệu |
| Instance bị loại khỏi registry | Danh sách cập nhật theo cache/refresh policy |
| Hai HTTP client bean | Client có `@LoadBalanced` dùng service ID; client thường dùng URL vật lý |
| Timeout hoặc connection refused | Lỗi được ghi nhận; retry chỉ diễn ra theo cấu hình |

## 15. Troubleshooting

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| `UnknownHostException` với tên service ID | HTTP client không được load balance hoặc thiếu LoadBalancer starter | Kiểm tra `@LoadBalanced`, dependency và interceptor/filter |
| Không tìm được instance | Service ID sai hoặc DiscoveryClient trả danh sách rỗng | Kiểm tra registry và `getInstances(serviceId)` |
| URI vật lý dùng host/port sai | Registration của provider chứa endpoint sai | Kiểm tra `ServiceInstance.getHost()`, `getPort()` và metadata |
| Request đi qua HTTP trong khi service yêu cầu HTTPS | Scheme/secure metadata của instance không đúng | Kiểm tra `isSecure()`, `getScheme()` và listener |
| Query parameter bị thay đổi | URI bị nối chuỗi hoặc encode nhiều lần | Dùng URI builder và `reconstructURI()` |
| Request luôn tới một instance | Chỉ có một instance trong supplier, cache cũ hoặc custom policy đang sticky | Kiểm tra instance list, cache TTL và supplier |
| Request vẫn tới instance đã shutdown | Discovery/cache chưa cập nhật hoặc health state chưa đổi | Kiểm tra deregistration, TTL và health-check policy |
| Không inject được RestTemplate | Có nhiều bean hoặc proxy type không tương thích | Dùng `@LoadBalanced`, `@Primary`, `RestOperations` hoặc cấu hình proxy phù hợp |
| Test không gọi được instance local | Chưa khởi động HTTP test server hoặc port không đúng | Kiểm tra port và danh sách `SimpleDiscoveryClient` |

### 15.1. Quy trình chẩn đoán

1. Xác định service ID trong URI logic.
2. Gọi DiscoveryClient hoặc kiểm tra registry để lấy danh sách instance.
3. In service ID, instance ID, host, port, secure và metadata cần thiết.
4. Xác minh supplier không lọc nhầm toàn bộ instance.
5. Kiểm tra URI sau `reconstructURI()`.
6. Kiểm tra DNS/routing/TLS từ chính môi trường chạy caller.
7. Kiểm tra HTTP status, exception, timeout và retry log.
8. Đối chiếu cache TTL với thời điểm instance thay đổi.

## 16. Quy trình thực hiện một service call

Khi triển khai lời gọi service trong ứng dụng:

1. Xác nhận service discovery trả đúng service ID và các instance.
2. Thêm Spring Cloud LoadBalancer starter và provider discovery phù hợp.
3. Chọn `RestTemplate`, `RestClient` hoặc `WebClient` theo mô hình blocking/reactive.
4. Đánh dấu builder/client bằng `@LoadBalanced`.
5. Gọi URL bằng service ID, path và query đúng định dạng.
6. Kiểm tra scheme, host và port mà instance công bố.
7. Thiết lập timeout và retry phù hợp với nghiệp vụ.
8. Theo dõi instance ID, request result và metrics.
9. Kiểm thử khi instance thêm/bớt, mất kết nối hoặc chuyển sang HTTPS.

Nếu cần kiểm soát từng bước, dùng `LoadBalancerClient.choose()` và `reconstructURI()`. Nếu chỉ cần gọi service bình thường, ưu tiên tích hợp `@LoadBalanced` để LoadBalancer xử lý chọn instance, tái dựng URI và thực thi request.

## 17. Tổng kết

Một service call trong Spring Cloud bắt đầu bằng service ID logic. `ServiceInstanceListSupplier` lấy danh sách instance từ discovery hoặc cấu hình tĩnh, `ReactiveLoadBalancer` chọn một instance, và URI được tái dựng để thay host logic bằng host/port vật lý. `ServiceInstance` cung cấp các thông tin như instance ID, host, port, secure flag, scheme và metadata.

`LoadBalancerClient.choose()` cho phép chọn instance thủ công; `reconstructURI()` tạo URI vật lý từ URI logic và instance đã chọn. Với HTTP client được đánh dấu `@LoadBalanced`, Spring Cloud tích hợp interceptor hoặc reactive filter để tự thực hiện các bước này khi ứng dụng gửi request.

Việc chọn instance không đảm bảo kết nối sẽ thành công. Cần kiểm tra service ID, danh sách instance, scheme, network, TLS, timeout, cache và retry. Khi các bước đó được quan sát và kiểm thử, ứng dụng có thể gọi dịch vụ bằng tên logic mà không phải gắn cứng endpoint của từng instance.

## Tài liệu tham khảo

- [Spring Cloud Commons — Common Abstractions](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html): tích hợp `RestTemplate`, `RestClient`, `WebClient`, `@LoadBalanced` và URI service ID.
- [Spring Cloud LoadBalancer](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html): thuật toán chọn instance, supplier, cache, zone preference, health check, retry và request transformation.
- [LoadBalancerClient.java](https://github.com/spring-cloud/spring-cloud-commons/blob/main/spring-cloud-commons/src/main/java/org/springframework/cloud/client/loadbalancer/LoadBalancerClient.java): hợp đồng `choose`, `execute` và `reconstructURI`.
- [ServiceInstance.java](https://github.com/spring-cloud/spring-cloud-commons/blob/main/spring-cloud-commons/src/main/java/org/springframework/cloud/client/ServiceInstance.java): thông tin instance và cách tạo URI mặc định.
- [LoadBalancerUriTools.java](https://github.com/spring-cloud/spring-cloud-commons/blob/main/spring-cloud-commons/src/main/java/org/springframework/cloud/client/loadbalancer/LoadBalancerUriTools.java): thay host/port, tính scheme, port mặc định và bảo toàn URI đã encode.
- [Spring Cloud LoadBalancer configuration properties](https://docs.spring.io/spring-cloud-commons/reference/configprops.html): các thuộc tính cache, retry, health check và cấu hình theo client ID.

Hãy đối chiếu hành vi với release train Spring Cloud và phiên bản Spring Framework của dự án. Provider discovery, HTTP client integration, cache và retry có thể có khác biệt giữa các phiên bản.
