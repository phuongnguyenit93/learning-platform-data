# Hợp đồng `DiscoveryClient` và `ReactiveDiscoveryClient`

Trong hệ thống phân tán, một dịch vụ thường có nhiều instance chạy trên các máy hoặc container khác nhau. Client cần tìm được địa chỉ của những instance đó mà không phải ghi cứng hostname và port trong mã nguồn. Spring Cloud Commons cung cấp hai hợp đồng đọc thông tin discovery: **`DiscoveryClient`** cho cách gọi đồng bộ và **`ReactiveDiscoveryClient`** cho cách gọi reactive dựa trên Project Reactor.

Hai interface này tạo ra ranh giới chung giữa ứng dụng và nhà cung cấp service discovery như Eureka, Consul hoặc ZooKeeper. Ứng dụng hỏi theo service ID và nhận về các `ServiceInstance`; phần kết nối tới registry, cache, heartbeat và chuyển đổi dữ liệu thuộc implementation cụ thể.

Bài học thuộc chương **DiscoveryClient** của module **SPRING_CLOUD_CORE**. Người học sẽ nắm chính xác các phương thức trong hai hợp đồng, cách đọc thông tin instance, khác biệt giữa blocking và reactive, thứ tự khi có nhiều discovery client, cũng như ranh giới giữa tra cứu và đăng ký dịch vụ.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Giải thích vai trò của service discovery trong hệ thống phân tán.
2. Mô tả các phương thức của `DiscoveryClient` và `ReactiveDiscoveryClient`.
3. Phân biệt kiểu trả về `List` với `Flux` và cách sử dụng đúng trong từng mô hình ứng dụng.
4. Đọc các trường của `ServiceInstance`, gồm service ID, instance ID, URI, host, port, scheme và metadata.
5. Hiểu ý nghĩa của `description()`, `probe()`, `reactiveProbe()` và `getOrder()`.
6. Phân biệt discovery read API với `ServiceRegistry` register/deregister API.
7. Hiểu cách Spring Cloud phát hiện implementation, `SimpleDiscoveryClient` và thứ tự nhiều provider.
8. Kết hợp discovery với Spring Cloud LoadBalancer mà không tự chọn instance tùy tiện.
9. Kiểm thử hợp đồng bằng mock hoặc cấu hình discovery đơn giản.
10. Chẩn đoán trường hợp service tồn tại nhưng không có instance, discovery lỗi hoặc dữ liệu instance không hợp lệ.

## 2. Service discovery và vị trí của hai hợp đồng

### 2.1. Service ID và service instance

Giả sử hệ thống có các dịch vụ:

- `orders-service`: xử lý đơn hàng.
- `inventory-service`: quản lý tồn kho.
- `pricing-service`: tính giá.
- `identity-service`: xác thực và định danh.

Mỗi dịch vụ có thể chạy nhiều instance:

~~~text
inventory-service
  ├── instance A: http://inventory-1.internal:8080
  ├── instance B: http://inventory-2.internal:8080
  └── instance C: https://inventory-3.internal:8443
~~~

**Service ID** là tên logic của dịch vụ, ví dụ `inventory-service`. **Service instance** là một tiến trình cụ thể có địa chỉ mạng, port, metadata và các thuộc tính định tuyến.

Client nên hỏi discovery theo service ID. Registry trả về các instance đang được provider công bố. Client không cần biết trước địa chỉ của từng máy.

### 2.2. DiscoveryClient là abstraction đọc

`DiscoveryClient` và `ReactiveDiscoveryClient` cung cấp các thao tác đọc:

- Lấy danh sách service ID đã biết.
- Lấy các instance thuộc một service ID.
- Mô tả implementation.
- Kiểm tra khả năng truy vấn discovery provider.
- Xác định thứ tự khi có nhiều implementation.

Hai interface này **không định nghĩa thao tác đăng ký hoặc hủy đăng ký instance**. Những thao tác đó thuộc `ServiceRegistry` và `Registration`, được trình bày ở phần sau.

### 2.3. Kiến trúc khái quát

~~~mermaid
flowchart TD
    A[Application service] --> B[DiscoveryClient hoặc ReactiveDiscoveryClient]
    B --> C[Spring Cloud provider implementation]
    C --> D[Service registry]
    D --> E[Service IDs]
    D --> F[Service instances]
    B --> G[ServiceInstance]
    G --> H[Load balancer hoặc client gọi dịch vụ]
~~~

Ứng dụng sử dụng hợp đồng của Commons; provider cụ thể chịu trách nhiệm giao tiếp với registry. Sau khi nhận danh sách instance, ứng dụng hoặc load balancer quyết định cách chọn instance và gửi request.

## 3. Hợp đồng đồng bộ `DiscoveryClient`

Interface nằm trong package:

~~~java
org.springframework.cloud.client.discovery.DiscoveryClient
~~~

`DiscoveryClient` mở rộng `org.springframework.core.Ordered`. Hợp đồng hiện hành có các phương thức chính:

| Phương thức | Kiểu trả về | Ý nghĩa |
| --- | --- | --- |
| `description()` | `String` | Mô tả dễ đọc về implementation |
| `getInstances(String serviceId)` | `List<ServiceInstance>` | Lấy các instance thuộc service ID |
| `getServices()` | `List<String>` | Lấy các service ID đã biết |
| `probe()` | `void` | Kiểm tra client có thể thực hiện truy vấn discovery |
| `getOrder()` | `int` | Thứ tự ưu tiên khi sắp xếp nhiều client |

### 3.1. `getInstances(serviceId)`

Phương thức:

~~~java
List<ServiceInstance> getInstances(String serviceId);
~~~

Nhận service ID và trả về danh sách instance tương ứng.

Ví dụ:

~~~java
List<ServiceInstance> instances =
        discoveryClient.getInstances("inventory-service");

if (instances.isEmpty()) {
    throw new IllegalStateException(
            "No inventory-service instance is currently available"
    );
}
~~~

Nếu service ID không có instance, implementation thông thường trả về danh sách rỗng. Không nên dựa vào thứ tự của danh sách để suy ra instance nào tốt nhất hoặc có tải thấp nhất. Thứ tự trả về phụ thuộc provider và dữ liệu registry.

Cần phân biệt hai trường hợp:

- Danh sách rỗng: truy vấn hoàn tất nhưng không có instance phù hợp được trả về.
- Exception: truy vấn thất bại, chẳng hạn registry không truy cập được hoặc provider gặp lỗi.

Ứng dụng nên xử lý hai tình huống theo chính sách khác nhau. Danh sách rỗng có thể dẫn tới lỗi “không có instance”; exception có thể cần retry, circuit breaker hoặc báo trạng thái discovery không khả dụng.

### 3.2. `getServices()`

Phương thức:

~~~java
List<String> getServices();
~~~

Trả về các service ID mà discovery client biết tới. Ví dụ:

~~~java
List<String> serviceIds = discoveryClient.getServices();

serviceIds.forEach(log::info);
~~~

Đây là API hữu ích cho trang quản trị, chẩn đoán hoặc công cụ khám phá. Không nên gọi nó ở mọi request nghiệp vụ nếu registry có số lượng service lớn hoặc thao tác liệt kê tốn tài nguyên.

Danh sách này cũng không đồng nghĩa với mọi service đang khỏe mạnh. Nó phản ánh dữ liệu mà provider trả về tại thời điểm truy vấn; trạng thái instance cần được đánh giá bằng health check, lease/heartbeat của registry hoặc cơ chế kiểm tra riêng.

### 3.3. `description()`

Phương thức:

~~~java
String description();
~~~

Trả về mô tả dễ đọc về implementation. Spring Cloud dùng mô tả này trong một số thành phần quan sát, chẳng hạn `DiscoveryClientHealthIndicator`.

Ví dụ:

~~~java
@Override
public String description() {
    return "Inventory discovery through Consul";
}
~~~

Đây là thông tin mô tả phục vụ chẩn đoán. Không dùng `description()` làm service ID, khóa định tuyến hoặc thông tin xác thực.

### 3.4. `probe()`

Hợp đồng có phương thức mặc định:

~~~java
default void probe() {
    getServices();
}
~~~

Một lần gọi `probe()` thành công mà không ném exception cho biết discovery client có thể thực hiện thao tác truy vấn. Implementation có thể override phương thức để dùng một thao tác nhẹ hơn thay vì liệt kê toàn bộ service.

Ví dụ:

~~~java
try {
    discoveryClient.probe();
    log.info("Discovery provider is reachable");
}
catch (RuntimeException ex) {
    log.warn("Discovery provider probe failed", ex);
}
~~~

`probe()` không kiểm tra từng instance của mọi service, không gửi request nghiệp vụ đến downstream và không chứng minh mọi địa chỉ trong registry đều có thể truy cập. Nó chỉ là phép kiểm tra khả năng hoạt động của discovery client theo implementation.

### 3.5. `getOrder()`

`DiscoveryClient` mở rộng `Ordered`. Giá trị mặc định của `getOrder()` là `0`.

~~~java
@Override
public int getOrder() {
    return 10;
}
~~~

Khi có nhiều discovery client, thứ tự giúp Spring Cloud sắp xếp các implementation và sử dụng composite theo thứ tự đó. Giá trị order thấp hơn có độ ưu tiên cao hơn theo quy tắc của Spring `Ordered`.

Order không phải trọng số tải, không phải thứ tự ưu tiên của từng instance và không phải chính sách load balancing. Không dùng `getOrder()` để thay thế thuật toán chọn server.

## 4. Hợp đồng reactive `ReactiveDiscoveryClient`

Interface nằm trong package:

~~~java
org.springframework.cloud.client.discovery.ReactiveDiscoveryClient
~~~

Interface này cũng mở rộng `Ordered`, nhưng dùng các kiểu trả về của Project Reactor:

| Phương thức | Kiểu trả về | Ý nghĩa |
| --- | --- | --- |
| `description()` | `String` | Mô tả implementation |
| `getInstances(String serviceId)` | `Flux<ServiceInstance>` | Phát các instance thuộc service ID |
| `getServices()` | `Flux<String>` | Phát các service ID đã biết |
| `reactiveProbe()` | `Mono<Void>` | Kiểm tra khả năng truy vấn theo reactive pipeline |
| `getOrder()` | `int` | Thứ tự client |
| `probe()` | `void` | API cũ đã deprecated trong các phiên bản hiện hành |

### 4.1. `getInstances(serviceId)` trả về Flux

~~~java
Flux<ServiceInstance> getInstances(String serviceId);
~~~

Ví dụ:

~~~java
Flux<ServiceInstance> instances =
        reactiveDiscoveryClient.getInstances("inventory-service");
~~~

`Flux` có thể phát không phần tử, một phần tử hoặc nhiều phần tử. Khi không tìm thấy instance, publisher thường hoàn tất mà không phát phần tử. Khi truy vấn thất bại, publisher phát tín hiệu lỗi.

Có thể chuyển sang instance đầu tiên:

~~~java
Mono<ServiceInstance> firstInstance =
        reactiveDiscoveryClient.getInstances("inventory-service")
                .next();
~~~

Nếu cần xử lý trường hợp không có instance:

~~~java
Mono<URI> resolveInventoryUri() {
    return reactiveDiscoveryClient.getInstances("inventory-service")
            .next()
            .map(ServiceInstance::getUri)
            .switchIfEmpty(Mono.error(
                    new IllegalStateException("No inventory instance")
            ));
}
~~~

Đoạn mã minh họa việc lấy một instance để hiểu hợp đồng. Trong ứng dụng production, nên để Spring Cloud LoadBalancer lựa chọn instance thay vì tự lấy phần tử đầu tiên.

### 4.2. `getServices()` trả về Flux

~~~java
Flux<String> getServices();
~~~

Ví dụ:

~~~java
Flux<String> serviceIds =
        reactiveDiscoveryClient.getServices();

return serviceIds
        .filter(id -> id.endsWith("-service"))
        .sort();
~~~

Các toán tử Reactor tạo pipeline. Không cần block để lấy danh sách rồi xử lý tiếp trong ứng dụng WebFlux; hãy giữ dữ liệu trong `Flux` hoặc `Mono` cho tới khi framework subscribe.

### 4.3. `reactiveProbe()`

Hợp đồng hiện hành cung cấp:

~~~java
Mono<Void> reactiveProbe();
~~~

Có thể kết hợp timeout và xử lý lỗi:

~~~java
Mono<Void> checkDiscovery() {
    return reactiveDiscoveryClient.reactiveProbe()
            .timeout(Duration.ofSeconds(2))
            .doOnSuccess(ignored ->
                    log.info("Discovery provider is reachable"))
            .doOnError(error ->
                    log.warn("Discovery provider probe failed", error));
}
~~~

`Mono<Void>` là một publisher. Pipeline chỉ thực thi khi có subscriber. Vì vậy, cần trả publisher cho caller hoặc kết hợp vào lifecycle/health flow thích hợp; tạo `Mono` rồi bỏ đi không thực hiện phép kiểm tra.

### 4.4. Vì sao `probe()` reactive đã deprecated?

Trong các API Spring Cloud Commons hiện hành, `ReactiveDiscoveryClient.probe()` đã deprecated để chuyển sang `reactiveProbe()`.

Lý do là phương thức cũ gọi `getServices()` trả về `Flux` nhưng không subscribe hoặc block để tiêu thụ publisher. Do đó, nó không thực hiện phép kiểm tra reactive đúng cách. Không dùng phương thức cũ trong code mới.

Hãy đối chiếu Javadoc của release train dự án nếu đang dùng phiên bản Spring Cloud cũ; mức độ deprecated và khả năng có mặt của `reactiveProbe()` phụ thuộc phiên bản.

## 5. `ServiceInstance`: dữ liệu mà discovery trả về

Cả hai hợp đồng đều trả về `org.springframework.cloud.client.ServiceInstance`.

Các thuộc tính chính:

| Phương thức | Ý nghĩa |
| --- | --- |
| `getInstanceId()` | ID riêng của instance; có thể không được provider cung cấp |
| `getServiceId()` | Service ID đã đăng ký |
| `getHost()` | Hostname của instance |
| `getPort()` | Port của instance |
| `isSecure()` | Cho biết instance sử dụng HTTPS |
| `getUri()` | URI đầy đủ để truy cập instance |
| `getMetadata()` | Map metadata key/value của instance |
| `getScheme()` | Scheme nếu implementation cung cấp |

Ví dụ đọc thông tin:

~~~java
void logInstances(List<ServiceInstance> instances) {
    for (ServiceInstance instance : instances) {
        log.info(
                "service={}, instance={}, uri={}, secure={}, metadata={}",
                instance.getServiceId(),
                instance.getInstanceId(),
                instance.getUri(),
                instance.isSecure(),
                instance.getMetadata()
        );
    }
}
~~~

### 5.1. Service ID và instance ID khác nhau

`getServiceId()` xác định nhóm dịch vụ logic, ví dụ `inventory-service`. `getInstanceId()` xác định một instance trong nhóm đó, ví dụ `inventory-service-7f9c`.

Nhiều instance có thể có cùng service ID nhưng instance ID khác nhau. Nếu provider không cung cấp instance ID, `getInstanceId()` có thể trả về `null`; không dùng nó làm khóa bắt buộc nếu chưa kiểm tra null.

### 5.2. URI và host/port

`getUri()` trả URI của instance. Đây thường là lựa chọn phù hợp khi cần địa chỉ đầy đủ vì URI có thể mang scheme và thông tin khác do provider cung cấp.

Không tự ghép chuỗi `http://` với host và port nếu instance có thể dùng HTTPS. `isSecure()` và `getUri()` giúp ứng dụng giữ đúng giao thức mà provider công bố.

Ví dụ:

~~~java
URI uri = instance.getUri();
String scheme = uri.getScheme();
String host = uri.getHost();
int port = uri.getPort();
~~~

Không giả định mọi URI đều có port tường minh; URI có thể dùng port mặc định của scheme hoặc có cấu trúc khác tùy provider.

### 5.3. Metadata

Metadata cho phép provider hoặc ứng dụng công bố thông tin bổ sung:

~~~text
zone=ap-southeast-1a
version=v2
canary=true
protocol=grpc
~~~

Có thể dùng metadata cho routing policy, chọn phiên bản hoặc phân vùng địa lý. Nhưng discovery contract không quy định mọi provider phải cung cấp cùng một bộ metadata. Mã ứng dụng cần xử lý key thiếu và định dạng khác nhau.

Không đưa credential, token hoặc secret vào metadata vì dữ liệu này có thể được nhiều client đọc.

## 6. Chọn blocking hay reactive?

Hai interface biểu diễn hai mô hình lập trình. Chọn theo mô hình của ứng dụng và provider, không chọn chỉ dựa trên tên interface.

| Tình huống | Hợp đồng phù hợp |
| --- | --- |
| Ứng dụng MVC hoặc service đồng bộ | `DiscoveryClient` |
| Ứng dụng WebFlux và Reactor pipeline | `ReactiveDiscoveryClient` |
| Code đang chạy trên event-loop | Tránh gọi API blocking trực tiếp |
| Component cần phối hợp `Mono`/`Flux` | `ReactiveDiscoveryClient` |
| Thư viện đồng bộ hoặc API legacy | `DiscoveryClient` có thể phù hợp |

### 6.1. Blocking example

~~~java
@Service
class InventoryResolver {

    private final DiscoveryClient discoveryClient;

    InventoryResolver(DiscoveryClient discoveryClient) {
        this.discoveryClient = discoveryClient;
    }

    List<URI> resolveAll(String serviceId) {
        return discoveryClient.getInstances(serviceId)
                .stream()
                .map(ServiceInstance::getUri)
                .toList();
    }
}
~~~

`getInstances()` trả danh sách ngay trong lời gọi. Nếu implementation phải gọi registry qua mạng, lời gọi có thể chặn thread trong lúc chờ kết quả.

### 6.2. Reactive example

~~~java
@Service
class ReactiveInventoryResolver {

    private final ReactiveDiscoveryClient discoveryClient;

    ReactiveInventoryResolver(ReactiveDiscoveryClient discoveryClient) {
        this.discoveryClient = discoveryClient;
    }

    Flux<URI> resolveAll(String serviceId) {
        return discoveryClient.getInstances(serviceId)
                .map(ServiceInstance::getUri);
    }
}
~~~

Reactive code giữ kết quả trong pipeline. Không gọi `.block()` trên event-loop của WebFlux để biến API reactive thành đồng bộ; làm vậy có thể gây nghẽn hoặc lỗi runtime.

### 6.3. Reactive interface không tự bảo đảm mọi implementation đều non-blocking

Hợp đồng reactive trả về `Flux` và `Mono`, nhưng ứng dụng vẫn cần chọn provider có hỗ trợ reactive phù hợp. Nếu một implementation bọc lời gọi blocking, nó phải điều phối công việc đúng scheduler và tài nguyên. Chỉ nhìn kiểu trả về `Flux` không đủ để kết luận toàn bộ đường truy vấn không có blocking.

Hãy kiểm tra tài liệu của provider và quan sát thread khi chạy integration test. Không chuyển một lời gọi blocking sang event-loop chỉ bằng cách bọc nó trong `Mono.just(...)`.

## 7. Khám phá implementation và cấu hình Spring Cloud

### 7.1. Provider implementation

Spring Cloud Commons định nghĩa abstraction; các dự án provider cung cấp implementation tương ứng, ví dụ:

- Spring Cloud Netflix Eureka Discovery.
- Spring Cloud Consul Discovery.
- Spring Cloud Zookeeper Discovery.
- Các integration discovery khác được hỗ trợ bởi hệ sinh thái.

Khi starter/provider phù hợp có trên classpath, auto-configuration tạo bean discovery client tương ứng và kết nối theo cấu hình của provider.

### 7.2. `@EnableDiscoveryClient` có còn bắt buộc?

Trong các phiên bản Spring Cloud hiện hành, `@EnableDiscoveryClient` không còn bắt buộc khi implementation `DiscoveryClient` phù hợp đã có trên classpath. Annotation vẫn tồn tại và có thể dùng trong các trường hợp cần cấu hình rõ ràng, chẳng hạn tắt auto-registration bằng `autoRegister=false`.

Không thêm annotation chỉ theo thói quen từ dự án cũ. Kiểm tra release train và starter provider trước khi quyết định.

### 7.3. Tắt từng hợp đồng hoặc toàn bộ discovery

Spring Cloud Commons cung cấp các thuộc tính điều khiển:

~~~yaml
spring:
  cloud:
    discovery:
      blocking:
        enabled: true
      reactive:
        enabled: true
      enabled: true
~~~

Có thể tắt riêng blocking hoặc reactive discovery client:

~~~properties
spring.cloud.discovery.blocking.enabled=false
spring.cloud.discovery.reactive.enabled=false
~~~

Để tắt service discovery theo cấu hình chung:

~~~properties
spring.cloud.discovery.enabled=false
~~~

Ý nghĩa chính xác của auto-configuration và health contributor có thể thay đổi theo phiên bản. Hãy kiểm tra configuration metadata của release train dự án trước khi dùng thuộc tính này trong môi trường production.

### 7.4. `SimpleDiscoveryClient`

Nếu classpath không có implementation discovery được hỗ trợ bởi service registry, Spring Cloud có thể sử dụng `SimpleDiscoveryClient`, lấy danh sách instance từ cấu hình.

Ví dụ:

~~~yaml
spring:
  cloud:
    discovery:
      client:
        simple:
          instances:
            inventory-service:
              - uri: http://inventory-1.internal:8080
              - uri: http://inventory-2.internal:8080
            pricing-service:
              - uri: http://pricing-1.internal:8080
~~~

Cách này hữu ích cho môi trường local, test hoặc hệ thống nhỏ có danh sách endpoint tĩnh. Nó không tự theo dõi instance mới hoặc kiểm tra registry từ xa như Eureka/Consul.

Nếu dùng SimpleDiscoveryClient, cập nhật danh sách instance cần được thực hiện qua nguồn cấu hình và lifecycle của ứng dụng theo thiết kế. Không nhầm cấu hình tĩnh này với một service registry động.

## 8. Nhiều DiscoveryClient và thứ tự

Một ứng dụng có thể có nhiều implementation discovery. Ví dụ một hệ thống kết hợp registry trung tâm với danh sách instance tĩnh cho một nhóm dịch vụ nội bộ.

`DiscoveryClient` và `ReactiveDiscoveryClient` đều mở rộng `Ordered`. `CompositeDiscoveryClient` và `ReactiveCompositeDiscoveryClient` có thể gom các client và delegate theo thứ tự.

### 8.1. Giá trị order

Mặc định `getOrder()` trả về `0`. Có thể override trong implementation riêng:

~~~java
@Override
public int getOrder() {
    return 20;
}
~~~

Một số provider có thuộc tính cấu hình order riêng, chẳng hạn `spring.cloud.{clientIdentifier}.discovery.order`; Eureka có thuộc tính `eureka.client.order` theo tài liệu Commons.

### 8.2. Order không phải load balancing

Cần tách ba khái niệm:

- **Discovery client order:** thứ tự các implementation được sắp xếp khi nhiều client cùng tồn tại.
- **Instance list:** danh sách instance mà provider trả về cho service ID.
- **Load balancing:** chọn một instance để gửi request, có thể dựa trên round robin, random, zone, health hoặc policy riêng.

Không dùng `getOrder()` để chọn instance A thay vì B. Không dựa vào thứ tự list để tạo thuật toán cân bằng tải ngầm.

### 8.3. Khi nào dùng composite?

Composite có ích khi nhiều discovery provider cùng tham gia cung cấp dữ liệu. Tuy nhiên, cần kiểm tra thứ tự và hành vi delegate của implementation đúng phiên bản. Nếu hai provider cùng trả về một service ID, ứng dụng phải hiểu cách composite kết hợp hoặc lấy kết quả của chúng; không giả định tất cả implementation đều merge dữ liệu giống nhau.

## 9. Discovery và đăng ký dịch vụ là hai hợp đồng khác nhau

Một nhầm lẫn phổ biến là nghĩ `DiscoveryClient` có phương thức register. Interface này chỉ mô tả các thao tác đọc.

### 9.1. `ServiceRegistry` và `Registration`

Spring Cloud Commons cung cấp:

- `ServiceRegistry<R extends Registration>`: hợp đồng đăng ký và hủy đăng ký.
- `Registration`: marker interface mô tả một registration cụ thể của provider.

Các thao tác thường gặp gồm:

~~~java
serviceRegistry.register(registration);
serviceRegistry.deregister(registration);
serviceRegistry.getStatus(registration);
serviceRegistry.setStatus(registration, status);
~~~

Kiểu `Registration` cụ thể phụ thuộc provider, ví dụ `EurekaRegistration`, `ConsulRegistration` hoặc `ZookeeperRegistration`.

### 9.2. Auto-registration

Các implementation provider thường tự đăng ký server cục bộ khi ứng dụng khởi động. Có thể tắt auto-registration bằng:

~~~java
@EnableDiscoveryClient(autoRegister = false)
@SpringBootApplication
public class OrdersApplication {
}
~~~

Hoặc dùng cấu hình:

~~~properties
spring.cloud.service-registry.auto-registration.enabled=false
~~~

Tắt auto-registration không đồng nghĩa tắt thao tác đọc discovery. Một ứng dụng có thể không tự đăng ký chính nó nhưng vẫn dùng `DiscoveryClient` để tìm dịch vụ khác.

### 9.3. Sự kiện đăng ký

Spring Cloud Commons có thể phát các event liên quan auto-registration:

- `InstancePreRegisteredEvent`: trước khi đăng ký.
- `InstanceRegisteredEvent`: sau khi đăng ký.

Có thể dùng listener để ghi nhận hoặc thực hiện tác vụ sau khi service được đăng ký. Các event này không được phát nếu auto-registration bị tắt theo thuộc tính tương ứng.

## 10. DiscoveryClient và Spring Cloud LoadBalancer

`DiscoveryClient` trả danh sách instance. Nó không phải bộ cân bằng tải hoàn chỉnh.

Spring Cloud LoadBalancer dùng discovery làm nguồn danh sách instance rồi áp dụng chiến lược lựa chọn. Một client có thể dùng service ID logic thay cho hostname cụ thể.

Ví dụ với `WebClient`:

~~~java
@Configuration
class HttpClientConfiguration {

    @Bean
    @LoadBalanced
    WebClient.Builder loadBalancedWebClientBuilder() {
        return WebClient.builder();
    }
}
~~~

Sử dụng service ID:

~~~java
@Service
class InventoryApi {

    private final WebClient webClient;

    InventoryApi(@LoadBalanced WebClient.Builder builder) {
        this.webClient = builder.build();
    }

    Mono<InventoryResponse> getInventory(String sku) {
        return webClient.get()
                .uri("http://inventory-service/api/items/{sku}", sku)
                .retrieve()
                .bodyToMono(InventoryResponse.class);
    }
}
~~~

Trong ví dụ, `inventory-service` là service ID. LoadBalancer phối hợp với discovery để lấy danh sách instance và chọn một địa chỉ cho request.

Không tự lấy `getInstances().get(0)` trong từng request để thay thế LoadBalancer. Làm vậy có thể bỏ qua health, retry, zone preference, caching, metrics và policy chọn instance.

## 11. Health và kiểm tra khả năng discovery

Spring Cloud Commons có thể cấu hình health indicator dựa trên discovery client.

Một số thuộc tính thường dùng:

~~~yaml
spring:
  cloud:
    discovery:
      client:
        health-indicator:
          enabled: true
          include-description: false
          use-services-query: true
        composite-indicator:
          enabled: true
~~~

### 11.1. `DiscoveryClientHealthIndicator`

Health indicator này dựa trên discovery implementation hiện có. Mặc định, nó có thể gọi `getServices()` để kiểm tra discovery và lấy thông tin mô tả.

Trong hệ thống có rất nhiều service, việc liệt kê toàn bộ service trong mỗi lần health check có thể tốn tài nguyên. Có thể đặt:

~~~properties
spring.cloud.discovery.client.health-indicator.use-services-query=false
~~~

Khi đó health indicator dùng `probe()` thay vì truy vấn danh sách service.

### 11.2. Reactive health indicator

Với reactive discovery, Spring Cloud có health indicator tương ứng. Trong API hiện hành, kiểm tra reactive nên dùng `reactiveProbe()`; tránh dùng `ReactiveDiscoveryClient.probe()` đã deprecated.

### 11.3. Health của discovery không phải health của mọi downstream

Discovery health indicator kiểm tra khả năng hoạt động của discovery client/provider theo cách implementation hỗ trợ. Nó không tự gửi request nghiệp vụ tới từng instance của mọi service.

Để đánh giá downstream cụ thể, cần health check riêng, timeout, circuit breaker hoặc cơ chế kiểm tra instance của LoadBalancer. Một registry có thể truy cập được trong khi một service instance đã ngừng phục vụ request.

## 12. Viết một implementation tùy biến

Trong một số hệ thống, cần tích hợp discovery với nguồn nội bộ hoặc dữ liệu tĩnh. Có thể triển khai interface tương ứng.

### 12.1. Blocking implementation

Ví dụ minh họa một client đơn giản dùng map:

~~~java
import java.util.List;
import java.util.Map;

import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.discovery.DiscoveryClient;

public class InMemoryDiscoveryClient implements DiscoveryClient {

    private final Map<String, List<ServiceInstance>> instancesByService;

    public InMemoryDiscoveryClient(
            Map<String, List<ServiceInstance>> instancesByService
    ) {
        this.instancesByService = Map.copyOf(instancesByService);
    }

    @Override
    public String description() {
        return "In-memory discovery client";
    }

    @Override
    public List<ServiceInstance> getInstances(String serviceId) {
        return instancesByService.getOrDefault(serviceId, List.of());
    }

    @Override
    public List<String> getServices() {
        return List.copyOf(instancesByService.keySet());
    }

    @Override
    public int getOrder() {
        return 100;
    }
}
~~~

Ví dụ này chỉ minh họa hợp đồng. Trong implementation thật, dữ liệu có thể đến từ một backend, cache hoặc nguồn cập nhật động. Cần xác định rõ thread safety, độ mới của dữ liệu, lỗi backend và cách đăng ký bean.

### 12.2. Reactive implementation

Một implementation reactive có thể phát các giá trị từ nguồn dữ liệu:

~~~java
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.discovery.ReactiveDiscoveryClient;

public class InMemoryReactiveDiscoveryClient
        implements ReactiveDiscoveryClient {

    private final Map<String, List<ServiceInstance>> instancesByService;

    public InMemoryReactiveDiscoveryClient(
            Map<String, List<ServiceInstance>> instancesByService
    ) {
        this.instancesByService = Map.copyOf(instancesByService);
    }

    @Override
    public String description() {
        return "In-memory reactive discovery client";
    }

    @Override
    public Flux<ServiceInstance> getInstances(String serviceId) {
        return Flux.fromIterable(
                instancesByService.getOrDefault(serviceId, List.of())
        );
    }

    @Override
    public Flux<String> getServices() {
        return Flux.fromIterable(instancesByService.keySet());
    }

    @Override
    public Mono<Void> reactiveProbe() {
        return Mono.fromRunnable(() -> {
            // Kiểm tra trạng thái nguồn dữ liệu nếu cần.
        });
    }
}
~~~

Trong ví dụ này cần import `java.util.List` và `java.util.Map`. Nếu nguồn thực sự là reactive backend, hãy sử dụng publisher của backend thay vì chuyển dữ liệu blocking sang Reactor trên event-loop.

### 12.3. Những điều implementation phải giữ

Một implementation tốt cần:

- Trả đúng các instance thuộc service ID được yêu cầu.
- Trả danh sách rỗng hoặc publisher rỗng khi không có instance.
- Không trả `null` thay cho collection/publisher.
- Phân biệt dữ liệu không tồn tại với lỗi kết nối backend.
- Cung cấp mô tả implementation dễ hiểu.
- Đặt order phù hợp nếu có nhiều discovery client.
- Trả về `ServiceInstance` có URI, host, port, scheme và metadata nhất quán.
- Đảm bảo dữ liệu cập nhật có thread safety.
- Có timeout và quan sát khi backend bị chậm.
- Không đưa secret vào metadata hoặc log.

## 13. Kiểm thử hợp đồng

### 13.1. Kiểm thử blocking client bằng Mockito

~~~java
@Test
void returnsInstancesForServiceId() {
    DiscoveryClient discoveryClient = mock(DiscoveryClient.class);

    ServiceInstance instance = mock(ServiceInstance.class);
    when(instance.getUri()).thenReturn(
            URI.create("http://inventory-1.internal:8080")
    );

    when(discoveryClient.getInstances("inventory-service"))
            .thenReturn(List.of(instance));

    List<ServiceInstance> result =
            discoveryClient.getInstances("inventory-service");

    assertThat(result).hasSize(1);
    assertThat(result.get(0).getUri())
            .isEqualTo(URI.create("http://inventory-1.internal:8080"));
}
~~~

Test này xác nhận consumer xử lý đúng dữ liệu từ hợp đồng. Nó không chứng minh provider thực tế kết nối được registry.

### 13.2. Kiểm thử reactive client

~~~java
@Test
void emitsInstancesForServiceId() {
    ReactiveDiscoveryClient discoveryClient =
            mock(ReactiveDiscoveryClient.class);

    ServiceInstance instance = mock(ServiceInstance.class);
    when(instance.getUri()).thenReturn(
            URI.create("http://inventory-1.internal:8080")
    );

    when(discoveryClient.getInstances("inventory-service"))
            .thenReturn(Flux.just(instance));

    StepVerifier.create(
            discoveryClient.getInstances("inventory-service")
                    .map(ServiceInstance::getUri)
    )
    .expectNext(URI.create("http://inventory-1.internal:8080"))
    .verifyComplete();
}
~~~

`StepVerifier` subscribe vào publisher và kiểm tra tín hiệu phát ra. Test không gọi `.block()` trong code reactive cần giữ non-blocking.

### 13.3. Kiểm tra trường hợp không có instance

Blocking:

~~~java
when(discoveryClient.getInstances("missing-service"))
        .thenReturn(List.of());

assertThat(discoveryClient.getInstances("missing-service"))
        .isEmpty();
~~~

Reactive:

~~~java
when(reactiveDiscoveryClient.getInstances("missing-service"))
        .thenReturn(Flux.empty());

StepVerifier.create(
        reactiveDiscoveryClient.getInstances("missing-service")
)
.verifyComplete();
~~~

Không có instance là kết quả hợp lệ của truy vấn, không nhất thiết là lỗi kết nối registry. Consumer cần quyết định khi nào danh sách rỗng trở thành lỗi nghiệp vụ.

### 13.4. Kiểm tra probe

Với blocking client, xác nhận `probe()` không ném exception khi backend có thể truy vấn. Với reactive client, subscribe `reactiveProbe()` bằng StepVerifier và kiểm tra complete/error.

Không kiểm thử `ReactiveDiscoveryClient.probe()` trong code mới vì phương thức đó đã deprecated và có vấn đề về subscription.

### 13.5. Integration test với SimpleDiscoveryClient

Có thể dùng cấu hình properties để kiểm thử mapping service ID và instance:

~~~yaml
spring:
  cloud:
    discovery:
      client:
        simple:
          instances:
            inventory-service:
              - uri: http://localhost:8081
              - uri: https://localhost:8443
~~~

Kiểm tra `getServices()`, `getInstances("inventory-service")`, URI và cờ secure. Cách này phù hợp để test consumer mà không cần chạy Eureka/Consul thật.

Đối với integration test provider thật, dùng container hoặc test server của provider tương ứng để xác nhận đăng ký, heartbeat, deregister và truy vấn.

## 14. Lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| `getInstances()` trả danh sách rỗng | Sai service ID, service chưa đăng ký hoặc registry chưa cập nhật | Kiểm tra service ID, trạng thái registration và registry |
| `getServices()` không có service mong đợi | Provider không thấy service hoặc quyền truy cập bị giới hạn | Kiểm tra cấu hình provider và quyền đọc registry |
| Blocking request bị chậm | Discovery provider gọi registry đồng bộ hoặc timeout lớn | Đặt timeout, quan sát latency và tránh gọi trên event-loop |
| Reactive pipeline không chạy | Publisher chưa được subscribe | Trả publisher cho framework hoặc subscribe tại ranh giới phù hợp |
| `reactiveProbe()` không được thực thi | Tạo Mono nhưng không subscribe/compose | Dùng StepVerifier, health integration hoặc chain có subscriber |
| `probe()` reactive không phát tín hiệu | Đang dùng API deprecated | Chuyển sang `reactiveProbe()` |
| Không inject được `DiscoveryClient` | Thiếu provider dependency hoặc discovery bị tắt | Kiểm tra starter, auto-configuration và condition report |
| Nhiều client cho kết quả không mong muốn | Order hoặc composite behavior chưa rõ | Kiểm tra `getOrder()` và danh sách client |
| Có service ID nhưng request không đến được instance | Discovery chỉ trả dữ liệu đăng ký; instance có thể đã chết hoặc network lỗi | Kiểm tra health, network, port và LoadBalancer |
| URI dùng sai scheme | Code tự ghép host/port và bỏ qua `isSecure()`/`getUri()` | Dùng URI do `ServiceInstance` cung cấp |
| `getInstanceId()` trả null | Provider không cung cấp ID riêng | Dùng service ID và URI hoặc khóa phù hợp khác |
| Health discovery đỏ dù service vẫn phục vụ | Registry tạm thời lỗi hoặc probe truy vấn quá nặng | Kiểm tra health indicator, timeout và provider |

### 14.1. Phân biệt discovery failure với no instance

Đây là hai trường hợp cần xử lý riêng:

- **No instance:** provider truy vấn thành công nhưng không tìm thấy instance.
- **Discovery failure:** provider không thể truy vấn do timeout, authentication, DNS, network hoặc lỗi server.

Không chuyển mọi exception thành danh sách rỗng mà không ghi nhận. Làm vậy khiến ứng dụng không thể phân biệt service chưa đăng ký với registry đang bị lỗi.

### 14.2. Không lưu cache vô thời hạn ở consumer

Một consumer có thể cache kết quả discovery để giảm số lần truy vấn, nhưng cache cần có TTL hoặc cơ chế cập nhật. Nếu lưu địa chỉ instance vô thời hạn, ứng dụng có thể tiếp tục gọi tới instance đã bị deregister hoặc thay đổi IP.

Khi sử dụng Spring Cloud LoadBalancer, hãy tận dụng cache và supplier được cấu hình theo cơ chế của nó thay vì tự xây một cache không có chính sách invalidation.

## 15. Bảo mật và vận hành

Discovery metadata và danh sách instance có thể tiết lộ topology nội bộ. Khi triển khai production:

- Chỉ cấp quyền registry read/write theo vai trò.
- Bảo vệ credentials và TLS giữa provider với registry.
- Không ghi token, password hoặc secret vào metadata.
- Giới hạn endpoint quản trị registry.
- Theo dõi lỗi, latency và số lượng instance theo service.
- Kiểm tra địa chỉ instance được công bố có thể truy cập từ network của consumer.
- Dùng health/heartbeat và deregistration phù hợp để loại instance đã dừng.
- Giữ timeout truy vấn discovery hữu hạn.
- Có fallback và retry policy phù hợp, tránh retry storm khi registry lỗi.
- Kiểm tra discovery order nếu nhiều provider cùng được cấu hình.

Không coi việc một instance xuất hiện trong registry là bằng chứng nó đang phục vụ request tốt. Registry có thể cập nhật trễ; health check và network path vẫn cần được xác minh.

## 16. Bài tập vận dụng

**Bài tập 1 — Đọc hợp đồng blocking.** Inject `DiscoveryClient`, gọi `getServices()` và `getInstances("inventory-service")`. In service ID, URI, host, port và metadata của từng instance.

**Bài tập 2 — Đọc hợp đồng reactive.** Inject `ReactiveDiscoveryClient`, trả `Flux<ServiceInstance>` từ một service WebFlux. Dùng `StepVerifier` kiểm tra trường hợp có instance và không có instance.

**Bài tập 3 — So sánh probe.** Viết test cho `DiscoveryClient.probe()` và `ReactiveDiscoveryClient.reactiveProbe()`. Chứng minh reactive probe chỉ chạy khi publisher được subscribe.

**Bài tập 4 — SimpleDiscoveryClient.** Khai báo hai instance cho `inventory-service` bằng YAML. Xác nhận `getServices()` và `getInstances()` trả dữ liệu đúng, bao gồm HTTP và HTTPS.

**Bài tập 5 — ServiceRegistry.** Tắt auto-registration nhưng vẫn dùng `DiscoveryClient` để đọc service khác. Giải thích vì sao đọc discovery và đăng ký local service là hai trách nhiệm riêng.

**Bài tập 6 — Nhiều provider.** Tạo hai discovery client có order khác nhau. Quan sát thứ tự composite và kiểm tra kết quả khi cả hai cùng biết một service ID.

**Bài tập 7 — Load balancing.** Dùng `@LoadBalanced WebClient.Builder` gọi `http://inventory-service/...`. So sánh với cách tự lấy `getInstances().get(0)` và nêu các trách nhiệm mà LoadBalancer đảm nhận.

**Bài tập 8 — Phân loại lỗi.** Mô phỏng service không có instance và registry bị timeout. Thiết kế response/log khác nhau cho hai trường hợp.

## 17. Ghi nhớ và nguồn tra cứu

- `DiscoveryClient` là hợp đồng blocking; các phương thức discovery trả `List`.
- `ReactiveDiscoveryClient` là hợp đồng reactive; các phương thức trả `Flux`.
- Cả hai đều cung cấp `description()` và mở rộng `Ordered`.
- `DiscoveryClient.probe()` mặc định gọi `getServices()`; implementation có thể override bằng phép kiểm tra nhẹ hơn.
- Với reactive discovery, dùng `reactiveProbe()`; `probe()` reactive cũ đã deprecated.
- `ServiceInstance` mô tả địa chỉ và metadata của một instance; `getInstanceId()` có thể không có giá trị.
- DiscoveryClient chỉ đọc dữ liệu. `ServiceRegistry` và `Registration` chịu trách nhiệm register/deregister.
- `@EnableDiscoveryClient` không còn bắt buộc nếu provider implementation đã có trên classpath.
- `SimpleDiscoveryClient` hỗ trợ cấu hình instance tĩnh khi không dùng registry-backed client.
- `getOrder()` sắp xếp discovery provider, không phải thuật toán load balancing.
- Dùng Spring Cloud LoadBalancer để chọn instance; không mặc định lấy phần tử đầu tiên.
- Phân biệt danh sách rỗng với lỗi truy vấn registry và kiểm thử cả blocking lẫn reactive path.

Nguồn chính thức để đối chiếu theo phiên bản Spring Cloud/Spring Boot của dự án:

1. [Spring Cloud Commons – Common Abstractions](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html)
2. [Spring Cloud Commons 5.0.2 Javadoc – `DiscoveryClient`](https://javadoc.io/static/org.springframework.cloud/spring-cloud-commons/5.0.2/org/springframework/cloud/client/discovery/DiscoveryClient.html)
3. [Spring Cloud Commons 5.0.2 Javadoc – `ReactiveDiscoveryClient`](https://javadoc.io/static/org.springframework.cloud/spring-cloud-commons/5.0.2/org/springframework/cloud/client/discovery/ReactiveDiscoveryClient.html)
4. [Spring Cloud Commons Javadoc – `ServiceInstance`](https://javadoc.io/static/org.springframework.cloud/spring-cloud-commons/5.0.2/org/springframework/cloud/client/ServiceInstance.html)
5. [Spring Cloud Commons – Configuration Properties](https://docs.spring.io/spring-cloud-commons/reference/configprops.html)
6. [Spring Cloud LoadBalancer – Reference Guide](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html)
7. [Spring Cloud – Release train và tương thích Spring Boot](https://spring.io/projects/spring-cloud/)
