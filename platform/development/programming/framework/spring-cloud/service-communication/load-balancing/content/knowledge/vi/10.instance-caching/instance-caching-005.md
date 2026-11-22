# Cấu hình cache toàn cục và kiểm chứng cache có hiệu lực

Trong hệ thống microservices, Spring Cloud LoadBalancer cần danh sách những **ServiceInstance** đang cung cấp một service ID trước khi chọn instance để gửi request. Nếu mỗi request đều phải hỏi lại DiscoveryClient hoặc service registry, hệ thống có thể tăng số lần truy vấn discovery không cần thiết. **CachingServiceInstanceListSupplier** giải quyết bài toán này bằng cách giữ tạm danh sách instance, cho phép nhiều lần chọn đích cùng sử dụng một snapshot trong khoảng thời gian cấu hình.

Bài học tập trung vào hai việc: **cấu hình cache ở phạm vi toàn cục** và **chứng minh cache thật sự có hiệu lực**. Hai việc này cần được thực hiện riêng: có thuộc tính cache trong application.yml chưa chắc nghĩa là supplier đang sử dụng cache; ngược lại, nhiều HTTP request được phân phối đến các instance khác nhau không chứng minh rằng discovery đã bị gọi lại.

Trong Spring Cloud LoadBalancer, cache dành cho **danh sách bản sao dịch vụ**. Nó không phải response cache của HTTP, không lưu nội dung GET/POST, không lưu access token và cũng không bảo đảm bản sao được cache vẫn khỏe tại thời điểm request được gửi đi.

## 1. Cache nằm ở đâu trong luồng LoadBalancer?

Một lời gọi điển hình từ Order Service đến Inventory Service:

~~~mermaid
flowchart TD
    A["RestClient / WebClient / OpenFeign"] --> B["LoadBalancer nhận service ID"]
    B --> C["CachingServiceInstanceListSupplier"]
    C --> D{"Cache cho service ID"}
    D -->|HIT| E["Trả danh sách đã cache"]
    D -->|MISS / expired| F["DiscoveryClient hoặc ReactiveDiscoveryClient"]
    F --> G["Danh sách ServiceInstance"]
    G --> H["Lưu danh sách vào cache"]
    H --> I["Danh sách ứng viên"]
    E --> I
    I --> J["Zone, hint, weighted và các filter khác"]
    J --> K["RoundRobin / Random chọn instance"]
    K --> L["Tái dựng URI host/port"]
    L --> M["Gửi HTTP request đến instance"]
~~~

Đường dữ liệu có hai nhánh:

1. **Cache hit**: danh sách cho service ID đã tồn tại và chưa hết hạn; supplier lấy danh sách từ cache.
2. **Cache miss**: không có entry phù hợp hoặc entry đã hết hạn; supplier gọi delegate để lấy instance, rồi ghi kết quả về cache.

Giả sử service ID là **inventory-service** và registry trả:

~~~text
inventory-service:
  inventory-a -> 10.20.0.11:8080
  inventory-b -> 10.20.0.12:8080
  inventory-c -> 10.20.0.13:8080
~~~

Lần đầu LoadBalancer cần danh sách, cache có thể miss và đọc registry. Các lần tiếp theo có thể dùng lại **[a, b, c]**. Thuật toán Round Robin vẫn được phép chọn lần lượt a, b, c từ snapshot đó.

**Phân biệt:** có ba HTTP request đến ba instance khác nhau nhưng DiscoveryClient chỉ được gọi một lần là hành vi cache bình thường. Cache giảm truy vấn danh sách, **không khóa LoadBalancer vào một instance duy nhất**.

## 2. Những thành phần cần biết

| Thành phần | Trách nhiệm | Liên quan đến cache |
| --- | --- | --- |
| DiscoveryClient / ReactiveDiscoveryClient | Đọc danh sách instance từ nguồn discovery | Nguồn dữ liệu khi cache miss |
| DiscoveryClientServiceInstanceListSupplier | Biến kết quả discovery thành Flux của danh sách | Delegate ngay bên trong cache |
| CachingServiceInstanceListSupplier | Tra cứu, lưu và phát lại danh sách instance | Decorator thực hiện cache ở supplier chain |
| LoadBalancerCacheManager | Quản lý cache dành cho LoadBalancer | Trừu tượng lựa chọn implementation cache |
| DefaultLoadBalancerCache | Cache mặc định đi cùng LoadBalancer starter | Dùng khi không có Caffeine phù hợp |
| Caffeine-based cache | Cache dựa trên Caffeine | Được chọn khi dependency Caffeine có mặt |
| RoundRobinLoadBalancer / RandomLoadBalancer | Chọn một instance từ danh sách nhận được | Không tự quyết định cache hit hay miss |
| RestClient, WebClient, OpenFeign | Gửi request HTTP qua đích đã chọn | Cùng có thể hưởng lợi từ cache của supplier |

**ServiceInstanceListSupplier** không phát từng instance như một Flux riêng lẻ; API tiêu biểu của nó là:

~~~java
Flux<List<ServiceInstance>> get();

Flux<List<ServiceInstance>> get(Request request);
~~~

Mỗi phần tử Flux là **một danh sách ServiceInstance**. CachingServiceInstanceListSupplier lưu một snapshot danh sách theo service ID, không lưu kết quả của từng lần chọn Round Robin.

### 2.1. Cache đặt ở tầng nào?

Sơ đồ recommended:

~~~text
Discovery  ->  Caching  ->  ZonePreference  ->  HintBased  ->  LoadBalancer
                ^
                Cache danh sách nguồn, chưa lọc theo request
~~~

Nếu một service có 3 instance, cùng một danh sách nguồn có thể được dùng cho các request mang hint hoặc tenant khác nhau. Mỗi request vẫn cần được lọc **sau cache** theo chính sách riêng.

Spring Cloud khuyến nghị đặt CachingServiceInstanceListSupplier **ngay sau supplier lấy instance qua mạng**, trước các supplier lọc theo request. Đặt cache ở phía ngoài filter có dữ liệu phụ thuộc request có thể làm mất request context hoặc tái sử dụng danh sách đã lọc trong tình huống không phù hợp.

## 3. Cấu hình cache toàn cục trong application.yml

Những thuộc tính thường dùng được cung cấp dưới prefix **spring.cloud.loadbalancer.cache**:

~~~yaml
spring:
  cloud:
    loadbalancer:
      cache:
        enabled: true
        ttl: 35s
        capacity: 256
~~~

Đây là bộ giá trị **mặc định được tài liệu Spring Cloud Commons 5.0.4 công bố**. Có thể viết tường minh như trên để giúp việc đọc cấu hình rõ ràng, hoặc chỉ ghi những thuộc tính muốn thay đổi.

| Thuộc tính | Giá trị mặc định trong tài liệu hiện hành | Ý nghĩa |
| --- | --- | --- |
| spring.cloud.loadbalancer.cache.enabled | true | Bật/tắt cơ chế cache của Spring Cloud LoadBalancer ở phạm vi toàn cục |
| spring.cloud.loadbalancer.cache.ttl | 35s | Thời gian hết hạn sau khi entry được ghi |
| spring.cloud.loadbalancer.cache.capacity | 256 | **Initial capacity** của cache, không phải bảo đảm giới hạn cứng số entry |
| spring.cloud.loadbalancer.cache.caffeine.spec | Rỗng | Dùng một CaffeineSpec tùy chỉnh, ghi đè thiết lập cache chung tương ứng |

Ví dụ giảm TTL để cập nhật instance nhanh hơn trong môi trường biến động:

~~~yaml
spring:
  cloud:
    loadbalancer:
      cache:
        enabled: true
        ttl: 15s
        capacity: 128
~~~

**TTL tính từ lúc ghi entry**, không phải từ lần đọc cuối cùng. Một cache hit không có nghĩa bộ đếm thời gian được đặt lại về 15 giây. Tùy implementation, entry hết hạn được loại khi có lần truy cập/duy trì cache phù hợp; không nên giả định có một timer đồng bộ gọi registry đúng tại giây thứ 15.

### 3.1. Cấu hình toàn cục có tác động gì?

Thuộc tính **cache.enabled** thuộc nhóm cấu hình **global** của Spring Cloud LoadBalancer. Cách hiểu thực tế:

- **enabled=true** cho phép dùng cơ chế cache và cache manager, theo điều kiện auto-configuration.
- **enabled=false** tắt cache của LoadBalancer toàn cục; không nên cố tạo một nhánh bật cache riêng bằng cấu hình per-client trong khi cờ toàn cục đang tắt.
- Với **enabled=true**, có thể **tắt cache cho một service ID cụ thể** bằng một supplier chain tùy chỉnh *không chứa* CachingServiceInstanceListSupplier.
- Với **enabled=true**, một supplier tùy chỉnh không có cache **không tự nhiên được bọc cache chỉ vì có dòng thuộc tính này**.

Theo tài liệu Spring Cloud hiện hành, auto-configuration mặc định cho discovery thường tạo supplier theo mẫu:

~~~java
// Minh họa chuỗi mặc định, không phải yêu cầu tự khai báo bean.
ServiceInstanceListSupplier.builder()
        .withDiscoveryClient()
        .withCaching()
        .build(context);
~~~

Nhánh discovery blocking dùng **withBlockingDiscoveryClient()** thay cho **withDiscoveryClient()**. Nếu tự thay supplier bằng cấu hình custom, cần kiểm tra xem chuỗi đó còn gọi **withCaching()** hay không.

## 4. Cache mặc định và Caffeine khác nhau thế nào?

Spring Cloud LoadBalancer hỗ trợ hai lựa chọn cache theo classpath:

| Tiêu chí | Cache mặc định | Cache Caffeine |
| --- | --- | --- |
| Điều kiện | Không có Caffeine trên classpath | Có dependency com.github.ben-manes.caffeine:caffeine |
| Cách dùng | Được cung cấp với LoadBalancer starter | Thêm dependency Caffeine, Spring Cloud tự chọn implementation tương ứng |
| TTL | Qua loadbalancer.cache.ttl | Qua ttl chung hoặc CaffeineSpec |
| Initial capacity | Qua loadbalancer.cache.capacity | Qua capacity chung hoặc CaffeineSpec |
| Chính sách nâng cao | Khả năng cơ bản | Có maximumSize, expireAfterWrite, eviction và tùy chọn đặc thù Caffeine |
| Kiểm chứng | Đếm nguồn delegate, xem cache instance | Đếm nguồn delegate, dùng cache stats nếu được bật và instrument đúng |

Để dùng Caffeine, thêm dependency vào classpath ứng dụng:

~~~groovy
// build.gradle: ví dụ khai báo dependency, không phải một lệnh cần chạy.
dependencies {
    implementation("org.springframework.cloud:spring-cloud-starter-loadbalancer")
    implementation("com.github.ben-manes.caffeine:caffeine")
}
~~~

Spring Boot/Spring Cloud BOM phù hợp sẽ quản lý version của dependency. Tránh chọn thủ công phiên bản Caffeine không tương thích với project.

### 4.1. Cấu hình CaffeineSpec

Nếu dùng Caffeine và muốn đặt quy tắc rõ ràng:

~~~yaml
spring:
  cloud:
    loadbalancer:
      cache:
        enabled: true
        caffeine:
          spec: initialCapacity=64,maximumSize=512,expireAfterWrite=20s
~~~

Trong đó:

- **initialCapacity=64:** khả năng cấp phát ban đầu của cache.
- **maximumSize=512:** giới hạn xấp xỉ số entry mà Caffeine giữ theo chính sách eviction.
- **expireAfterWrite=20s:** thời gian hết hạn sau khi ghi entry.

**Cảnh báo quan trọng:** khi cấu hình **spring.cloud.loadbalancer.cache.caffeine.spec**, Spring Cloud cảnh báo rằng spec **ghi đè** các thiết lập LoadBalancer cache chung khác, bao gồm **ttl** và **capacity**. Không đặt đồng thời ttl=15s rồi kỳ vọng nó sẽ có hiệu lực nếu spec định nghĩa expireAfterWrite=20s.

Một cấu hình mâu thuẫn cần tránh:

~~~yaml
spring:
  cloud:
    loadbalancer:
      cache:
        ttl: 15s
        capacity: 128
        caffeine:
          spec: maximumSize=512,expireAfterWrite=20s
~~~

Ở đây **20s** từ spec là quy tắc expiration cần đọc, không phải **15s** trong thuộc tính chung. Hãy chọn **một cách cấu hình duy nhất** cho TTL/capacity để tránh hiểu nhầm.

### 4.2. Capacity không phải maximumSize

Một lỗi diễn giải là cho rằng **capacity=256** đồng nghĩa cache chỉ giữ tối đa 256 service ID. Theo tài liệu, đây là **initial capacity**; muốn đặt giới hạn entry với Caffeine, dùng **maximumSize** trong CaffeineSpec.

Chi phí bộ nhớ của danh sách instance còn phụ thuộc vào **số service ID**, **số instance của từng service** và metadata từng instance. Khi ứng dụng gọi rất nhiều service, hãy cân nhắc thời gian sống entry, eviction và khả năng quan sát thực tế.

## 5. CachingServiceInstanceListSupplier cache những gì?

Trong implementation hiện hành, **CachingServiceInstanceListSupplier** dùng cache tên:

~~~java
CachingServiceInstanceListSupplier.SERVICE_INSTANCE_CACHE_NAME
~~~

Tên cache mặc định được tạo từ tên lớp, có dạng:

~~~text
CachingServiceInstanceListSupplierCache
~~~

Cache được tra cứu bằng **service ID** do supplier delegate cung cấp:

~~~java
String cacheKey = delegate.getServiceId();
~~~

Khi cache miss, supplier gọi delegate để lấy một snapshot danh sách. Khi cache hit, nó phát lại danh sách đã lưu. Vì vậy:

- Cache key **không phải URL đầy đủ** của một request.
- Cache key **không phải từng instanceId**.
- Cache key **không phải URI đã có query string**.
- Cache không trực tiếp chứa response body của Inventory Service.
- Cache không phân biệt tenant/header/hint ở cấp request.

Đây là lý do cache phải nằm **trước** các filter theo request: cùng service ID có thể được gọi bởi nhiều request khác nhau nhưng không được chia sẻ một quyết định lọc riêng cho từng request.

### 5.1. Cache trên từng tiến trình caller

Cache của Spring Cloud LoadBalancer nằm trong bộ nhớ ứng dụng caller, không phải một kho cache chia sẻ xuyên các JVM/pod theo mặc định:

~~~text
order-service pod A -> cache riêng của A -> Inventory Service
order-service pod B -> cache riêng của B -> Inventory Service
order-service pod C -> cache riêng của C -> Inventory Service
~~~

Khi pod A vừa cập nhật danh sách từ registry, pod B có thể vẫn giữ snapshot cũ đến khi TTL của nó hết hạn. Hai pod có thể chọn những instance khác nhau dù cùng gọi một service ID. Không nên lấy kết quả log ở pod A làm bằng chứng rằng cache của toàn hệ thống đã được làm mới.

### 5.2. Empty list và truy vấn lặp lại

Một chi tiết trong mã nguồn **CachingServiceInstanceListSupplier** hiện hành là khi tra cache, nếu entry không có hoặc danh sách lấy ra **rỗng**, code xem như **cache miss**. Vì vậy, khi discovery trả **[]** cho một service ID chưa có instance, những lần gọi tiếp theo có thể tiếp tục đọc delegate thay vì được phục vụ bằng một cache hit âm.

Hệ quả khi kiểm thử:

- Không dùng service ID chưa đăng ký để kỳ vọng đếm discovery giảm về đúng một lần.
- Dùng một service có **ít nhất một ServiceInstance** để chứng minh cache hit bình thường.
- Phân biệt danh sách rỗng với lỗi registry: cache không thay thế xử lý lỗi khi không có instance.

Hành vi empty-list này dựa trên implementation được tham chiếu; nên kiểm tra lại khi nâng cấp phiên bản Spring Cloud.

## 6. TTL, cache hit, miss và dữ liệu stale

Giả sử TTL là **15s**. Tại thời điểm t=0, registry có [A, B]. Ở t=5, B được hủy đăng ký và registry đã cập nhật thành [A].

| Thời điểm | Trạng thái registry | Kết quả cache có thể trả | Ý nghĩa |
| --- | --- | --- | --- |
| t=0 | [A, B] | [A, B] sau miss và write | Tạo entry |
| t=3 | [A, B] | [A, B] | Hit còn hạn |
| t=5 | [A] | [A, B] | B vẫn nằm trong cache |
| t=10 | [A] | [A, B] | Hit còn hạn nếu TTL chưa hết |
| t=16 | [A] | [A] sau lần gọi miss/refetch | Entry cũ đã hết hạn |

Đây là **kịch bản minh họa**: thời điểm và kết quả chính xác phụ thuộc backend cache, registry, lúc phát sinh truy cập và việc có filter nào đang lọc instance. Không có bảo đảm rằng cache tự truy vấn registry **đúng** tại thời điểm TTL vừa hết nếu không có request.

### 6.1. TTL ngắn và TTL dài đánh đổi điều gì?

| TTL | Ưu điểm | Rủi ro |
| --- | --- | --- |
| Ngắn, ví dụ 5s | Quan sát thay đổi của instance nhanh hơn | Tăng số lần gọi discovery/cache miss |
| Trung bình, ví dụ 20–35s | Giảm phần lớn truy vấn lặp, độ trễ thay đổi vừa phải | Vẫn có cửa sổ dữ liệu stale |
| Dài, ví dụ 120s | Ít gọi discovery hơn | Instance bị xóa hoặc đổi địa chỉ có thể còn trong cache lâu |

Không có TTL tối ưu chung cho mọi hệ thống. Hãy xem xét tốc độ autoscaling, thời gian deregister, chu kỳ heartbeat, khả năng chịu lỗi, số service ID và SLO của client.

**TTL không đồng nghĩa với độ tươi dữ liệu toàn hệ thống.** Nếu DiscoveryClient (ví dụ Eureka) tự có cache và đồng bộ theo chu kỳ, LoadBalancer cache có thể đọc **một snapshot đã cũ** từ discovery. Tổng độ trễ cập nhật vì thế chịu ảnh hưởng của nhiều tầng, không thể suy ra chỉ từ một thuộc tính TTL.

## 7. Tránh cache hai tầng với discovery provider

Một số provider đã cung cấp cache/registry local riêng:

~~~text
Client request
     |
LoadBalancer cache (TTL 35s)
     |
EurekaDiscoveryClient local cache / refresh
     |
Eureka Registry
~~~

Hai tầng có thể giúp giảm tải nhưng gây khó hiểu khi instance vừa lên hoặc vừa tắt. Spring Cloud cảnh báo: nếu implementation DiscoveryClient **đã cache danh sách instance**, như EurekaDiscoveryClient, nên cân nhắc **tắt cache LoadBalancer** để tránh double caching.

Cấu hình tắt global:

~~~yaml
spring:
  cloud:
    loadbalancer:
      cache:
        enabled: false
~~~

Khi tắt cache này, **không có nghĩa** bỏ cache bên trong Eureka hoặc bắt buộc truy vấn network mỗi request. DiscoveryClient vẫn có thể trả dữ liệu từ cache riêng của nó. Vì vậy, một phép thử chỉ đếm HTTP request đến registry có thể gây hiểu nhầm.

### 7.1. Khi nào nên bật?

Nên cân nhắc bật LoadBalancer cache nếu:

- DiscoveryClient truy vấn nguồn đắt tiền mỗi lần lấy danh sách.
- Danh sách bản sao ít thay đổi hoặc có thể chịu độ trễ cập nhật trong TTL.
- Hệ thống có nhiều request hơn rất nhiều so với số lần registry thực sự cần được đọc.
- Muốn giảm tải cho discovery provider và vẫn có chiến lược health/timeout phù hợp.

Nên cân nhắc tắt hoặc giảm TTL nếu:

- Provider đã có cơ chế cache mạnh và refresh định kỳ.
- Pod/instance thay đổi nhanh và hệ thống yêu cầu thấy bản sao mới gần như lập tức.
- Lỗi stale instance tạo nhiều timeout hoặc retry không mong muốn.
- Một chuỗi HealthCheck đã có cơ chế lưu/replay kết quả riêng và được thiết kế để thay thế cache thường.

**Lựa chọn cuối cùng phải được đo**, không nên chỉ dựa trên việc property mặc định là true.

## 8. Cấu hình supplier chain đúng với cache

Spring Cloud tự cung cấp supplier trong nhiều cấu hình mặc định. Khi muốn tùy chỉnh, có thể tạo supplier riêng cho một service ID.

### 8.1. Với DiscoveryClient đồng bộ

~~~java
class InventoryLoadBalancerConfiguration {

    @Bean
    ServiceInstanceListSupplier inventorySupplier(
            ConfigurableApplicationContext context) {

        return ServiceInstanceListSupplier.builder()
                .withBlockingDiscoveryClient()
                .withCaching()
                .withZonePreference()
                .build(context);
    }
}
~~~

Thứ tự biến đổi thực tế:

~~~text
DiscoveryClient -> Caching -> ZonePreference -> LoadBalancer
~~~

### 8.2. Với ReactiveDiscoveryClient

~~~java
class InventoryReactiveLoadBalancerConfiguration {

    @Bean
    ServiceInstanceListSupplier inventorySupplier(
            ConfigurableApplicationContext context) {

        return ServiceInstanceListSupplier.builder()
                .withDiscoveryClient()
                .withCaching()
                .withZonePreference()
                .build(context);
    }
}
~~~

**withDiscoveryClient()** ở builder trên tương ứng với nguồn reactive. **withBlockingDiscoveryClient()** tương ứng với nguồn blocking. Chọn theo implementation provider và stack Spring Cloud đang sử dụng.

### 8.3. Áp dụng riêng cho inventory-service

~~~java
@SpringBootApplication
@LoadBalancerClient(
        name = "inventory-service",
        configuration = InventoryLoadBalancerConfiguration.class)
class OrderApplication {
}
~~~

Lớp InventoryLoadBalancerConfiguration trong ví dụ được để **không có @Configuration** nhằm tránh bị component scan biến thành cấu hình toàn cục. Theo hướng dẫn Spring Cloud, một lớp cấu hình @LoadBalancerClient nên không bị quét vào ApplicationContext chính hoặc được đặt ngoài component scan.

Nếu chỉ muốn cấu hình cache toàn cục mà không tùy chỉnh zone/health/hint, **không cần tạo supplier này** khi auto-configuration đã dùng chuỗi có cache.

### 8.4. Không đặt cache bên ngoài filter request

**Đúng:**

~~~text
Discovery -> Caching -> ZonePreference -> HintBased -> LoadBalancer
~~~

**Nên tránh:**

~~~text
Discovery -> HintBased -> Caching -> LoadBalancer
~~~

HintBased có thể cần Request với header hint, trong khi cache theo service ID không chia entry theo header. Nếu cache bao ngoài HintBased, request context có thể không đến đúng filter bên trong hoặc kết quả không còn phản ánh từng request.

Lưu ý **call-get-with-request-on-delegates** được thêm ở các release gần đây giúp nhiều decorator chuyển tiếp Request; CachingServiceInstanceListSupplier và HealthCheckServiceInstanceListSupplier là những ngoại lệ được tài liệu nêu rõ. Đặt chúng sát nguồn discovery vẫn là thiết kế an toàn.

### 8.5. Cache và HealthCheck không nên chồng tùy tiện

**HealthCheckServiceInstanceListSupplier** có publisher/scheduler và cơ chế replay danh sách khỏe mạnh. Nếu cả cache thường và HealthCheck cùng lưu kết quả, thời gian cập nhật có thể khó quan sát hoặc trở nên stale.

Khi cần health check do source không phản ánh health, thường xem xét:

~~~java
return ServiceInstanceListSupplier.builder()
        .withDiscoveryClient()
        .withHealthChecks()
        .withZonePreference()
        .build(context);
~~~

Đây là **lựa chọn thay thế** cho ví dụ cache thường, không phải yêu cầu thêm health check cho mọi registry.

## 9. Làm thế nào để biết cache thực sự đang hoạt động?

**Đừng dùng phân bố Round Robin để suy ra cache hit.** Để chứng minh cache đang phục vụ danh sách instance, cần đo ngay tại ranh giới giữa **CachingServiceInstanceListSupplier** và **delegate discovery supplier**.

Một chiến lược kiểm chứng đáng tin:

1. Chọn một service ID có ít nhất một instance, ví dụ inventory-service.
2. Đảm bảo cache.enabled=true và supplier có CachingServiceInstanceListSupplier.
3. Cấu hình TTL đủ dài so với thời gian thí nghiệm, ví dụ 20s.
4. Đếm số lần supplier nguồn phải lấy danh sách, không chỉ đếm HTTP call đến backend.
5. Thực hiện hai lần lấy danh sách **theo thứ tự**, có subscription hoàn tất trước khi gọi lần tiếp theo.
6. So sánh số lần đọc nguồn sau lần thứ nhất và thứ hai.
7. Cho entry hết hạn, thử lại; lần đọc nguồn có thể tăng.
8. Lặp lại cùng phép thử với cache bị tắt hoặc supplier không có withCaching() làm **đối chứng**.

### 9.1. Bảng kết quả kỳ vọng

Giả sử chỉ có một consumer tuần tự, danh sách không rỗng, không có bộ lọc health/refetch:

| Hành động | Caching bật và đang nằm trong supplier | Supplier không cache |
| --- | --- | --- |
| Lần đọc đầu sau khi chưa có entry | Đọc nguồn, rồi ghi cache | Đọc nguồn |
| Lần đọc thứ hai ngay sau đó | Đọc cache, không cần đọc nguồn | Đọc nguồn |
| Lần đọc thứ ba trong TTL | Tiếp tục dùng entry | Đọc nguồn |
| Lần đọc sau TTL | Có thể phải lấy danh sách nguồn mới | Đọc nguồn như bình thường |
| Nhiều HTTP request | Có thể vẫn liên tục Round Robin | Vẫn có thể liên tục Round Robin |

Vì cache thường được khởi tạo **lười** theo service ID, lần đầu load balance một service thường bao gồm cả tạo context, tạo bean và lần đọc discovery ban đầu. Đừng so sánh latency request đầu tiên với request thứ hai rồi kết luận toàn bộ chênh lệch là do cache.

## 10. Unit test: đếm số lần delegate được gọi

Ví dụ này dùng **CachingServiceInstanceListSupplier** thật, một delegate nguồn có bộ đếm, và **ConcurrentMapCacheManager** của Spring làm cache test. Nó cô lập hành vi cache khỏi registry, HTTP client, DNS và thời gian mạng.

~~~java
import java.time.Duration;
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;
import org.springframework.cache.CacheManager;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.cloud.client.DefaultServiceInstance;
import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.loadbalancer.core.CachingServiceInstanceListSupplier;
import org.springframework.cloud.loadbalancer.core.ServiceInstanceListSupplier;
import reactor.core.publisher.Flux;

import static org.junit.jupiter.api.Assertions.assertEquals;

class LoadBalancerCacheTest {

    static final class CountingSupplier
            implements ServiceInstanceListSupplier {

        private final AtomicInteger calls = new AtomicInteger();

        private final List<ServiceInstance> snapshot = List.of(
                new DefaultServiceInstance(
                        "inventory-1",
                        "inventory-service",
                        "localhost",
                        8081,
                        false),
                new DefaultServiceInstance(
                        "inventory-2",
                        "inventory-service",
                        "localhost",
                        8082,
                        false));

        @Override
        public String getServiceId() {
            return "inventory-service";
        }

        @Override
        public Flux<List<ServiceInstance>> get() {
            return Flux.defer(() -> {
                calls.incrementAndGet();
                return Flux.just(snapshot);
            });
        }

        int calls() {
            return calls.get();
        }
    }

    @Test
    void repeatedReadsReuseCachedInstanceList() {
        CountingSupplier source = new CountingSupplier();
        CacheManager cacheManager = new ConcurrentMapCacheManager(
                CachingServiceInstanceListSupplier.SERVICE_INSTANCE_CACHE_NAME);

        ServiceInstanceListSupplier cached =
                new CachingServiceInstanceListSupplier(source, cacheManager);

        List<ServiceInstance> first =
                cached.get().blockLast(Duration.ofSeconds(2));
        List<ServiceInstance> second =
                cached.get().blockLast(Duration.ofSeconds(2));

        assertEquals(2, first.size());
        assertEquals(first, second);
        assertEquals(1, source.calls());
    }
}
~~~

Ý nghĩa của kết quả:

- Hai lần **cached.get()** được subscribe **tuần tự**.
- Lần đầu cache miss, gọi CountingSupplier.get() một lần.
- Lần sau đọc lại danh sách đã cache, không gọi nguồn lần hai.
- Kiểm chứng được **reuse của supplier list** mà không phụ thuộc vào Round Robin hay network.

**Giới hạn rõ ràng:** ConcurrentMapCacheManager trong ví dụ là cache test **không tự hết hạn theo TTL 35s** của Spring Cloud. Unit test này **chỉ xác minh cache hit**, không xác minh property binding, auto-configuration của LoadBalancerCacheManager hay TTL của implementation production. Muốn kiểm tra end-to-end, cần integration test như mục sau.

### 10.1. Kiểm tra negative control

Thử gọi trực tiếp source.get() hai lần với cùng snapshot:

~~~java
CountingSupplier source = new CountingSupplier();

source.get().blockLast(Duration.ofSeconds(2));
source.get().blockLast(Duration.ofSeconds(2));

assertEquals(2, source.calls());
~~~

Chênh lệch giữa **1 lần gọi nguồn khi qua Caching** và **2 lần khi không có Caching** là một bằng chứng mạnh hơn việc hai backend trả cùng nội dung.

### 10.2. Tránh hiểu sai khi test đồng thời

Nếu 20 request cùng đến khi cache vừa trống, có thể có nhiều cache miss đồng thời trước khi một request ghi entry. Không kết luận rằng cache hỏng chỉ vì nguồn được gọi hơn một lần trong đợt khởi động đồng thời. Hãy bắt đầu bằng **phép thử tuần tự** để xác nhận semantics cơ bản, rồi mới thêm load test nhằm đo hiệu quả thực tế.

## 11. Integration test: xác minh cấu hình global được áp dụng

Unit test ở trên chứng minh decorator hoạt động, nhưng không chứng minh ứng dụng thực đã có **loadbalancer.cache.enabled=true**, đúng cache manager hay đúng TTL. Integration test phải dùng Spring ApplicationContext và đường gọi thực tế.

### 11.1. Chuẩn bị hai backend local

Khởi chạy hai bản sao Inventory Service với endpoint:

~~~text
http://localhost:8081/whoami -> {"instanceId":"inventory-1"}
http://localhost:8082/whoami -> {"instanceId":"inventory-2"}
~~~

Trong Order Service, dùng SimpleDiscoveryClient để không cần Eureka:

~~~yaml
spring:
  application:
    name: order-service
  cloud:
    loadbalancer:
      cache:
        enabled: true
        ttl: 20s
        capacity: 128
    discovery:
      client:
        simple:
          instances:
            inventory-service:
              - uri: http://localhost:8081
              - uri: http://localhost:8082
~~~

SimpleDiscoveryClient đọc một danh sách **tĩnh** từ cấu hình; nó phù hợp để minh họa cache và có thể được đo bằng lớp spy/wrapper ở test. Vì danh sách không tự cập nhật khi backend dừng, **không dùng riêng việc dừng 8081 để chứng minh TTL**.

### 11.2. Tích hợp RestClient có LoadBalancer

~~~java
@Configuration(proxyBeanMethods = false)
class InventoryClientConfiguration {

    @Bean
    @LoadBalanced
    RestClient.Builder loadBalancedRestClientBuilder() {
        return RestClient.builder();
    }
}
~~~

Gọi bằng service ID:

~~~java
@Service
class InventoryClient {

    private final RestClient restClient;

    InventoryClient(@LoadBalanced RestClient.Builder builder) {
        restClient = builder.build();
    }

    String whoAmI() {
        return restClient.get()
                .uri("http://inventory-service/whoami")
                .retrieve()
                .body(String.class);
    }
}
~~~

Nếu ứng dụng có supplier mặc định và cache đang hoạt động, nhiều lời gọi **whoAmI()** vẫn có thể nhận **inventory-1** và **inventory-2** theo Round Robin dù discovery supplier chỉ được đọc một lần trong TTL.

### 11.3. Bằng chứng cache trong Spring context

Cần xác minh **hai thứ độc lập**:

**A. Bean/supplier có cache hay không?** Với một service ID như inventory-service, Spring Cloud tạo child context thông qua LoadBalancerClientFactory. Hãy xem bean ServiceInstanceListSupplier thực tế trong child context hoặc bật chế độ debug cho auto-configuration để xác nhận chuỗi **Discovery → Caching** đã được tạo.

**B. Cache có được sử dụng hay không?** Trong test, đặt spy hoặc counter vào DiscoveryClient.getInstances("inventory-service") hoặc supplier discovery ngay dưới cache. Gọi load-balanced HTTP client tuần tự nhiều lần, sau đó kiểm tra counter không tăng qua mỗi request khi entry đang còn hạn.

Ví dụ kỳ vọng khi không có health/retry/refetch khác:

~~~text
T=0s:  GET /whoami  -> inventory-1, discovery reads=1
T=1s:  GET /whoami  -> inventory-2, discovery reads=1
T=2s:  GET /whoami  -> inventory-1, discovery reads=1
T=21s: GET /whoami  -> inventory-2, discovery reads=2
~~~

Các giá trị trên **chỉ là kỳ vọng cho một môi trường test tuần tự đã kiểm soát**, không phải cam kết số lần gọi trong production. Mọi request từ adapter không dùng cùng supplier, retry hoặc nhiều caller pod sẽ làm phép đếm khác đi.

### 11.4. So sánh A/B với cache tắt

Lặp lại test trong một lượt khởi động ứng dụng khác:

~~~yaml
spring:
  cloud:
    loadbalancer:
      cache:
        enabled: false
~~~

Nếu ứng dụng dùng nguồn discovery có thể đếm được:

| Tiêu chí | Cache bật | Cache tắt |
| --- | --- | --- |
| Số request đến backend | Tương đương | Tương đương |
| Số lần lấy danh sách từ supplier nguồn | Thường thấp hơn đáng kể | Có thể gần với số lần chọn instance |
| Thay đổi danh sách hiển thị ngay | Phụ thuộc TTL | Phụ thuộc cache/refresh của discovery provider |
| Phân phối Round Robin | Vẫn hoạt động | Vẫn hoạt động |

Để so sánh công bằng, giữ nguyên service ID, số instance, request rate, số caller pod, retry và cùng loại discovery provider. Chỉ đổi **cơ chế cache** giữa hai lượt đo.

## 12. Kiểm chứng TTL thực sự hết hạn

Để test TTL của implementation production, cần kiểm soát thời điểm entry được ghi, không chỉ xem danh sách instance có đổi không.

Một quy trình:

1. Tạo ứng dụng test với **cache.enabled=true**, **ttl=3s** và một source discovery có bộ đếm.
2. Khởi tạo LoadBalancer child context và thực hiện một lần chọn instance để tạo entry.
3. Gọi thêm lần nữa **ngay trong 3 giây**, xác minh bộ đếm nguồn không tăng.
4. Chờ **quá 3 giây kể từ lúc entry được ghi**, thực hiện một lần chọn mới.
5. Xác minh số lần đọc nguồn tăng trở lại nếu cache hết hạn đúng kỳ vọng.
6. Lặp lại với CaffeineSpec **expireAfterWrite=3s** và xác minh giá trị đến từ spec, không phải ttl chung.

Đừng sử dụng chỉ số "bao nhiêu response từ instance B" làm kiểm chứng chính. Registry có thể giữ nguyên danh sách cả trước và sau khi entry hết hạn, khiến response không đổi dù cache vừa refetch thành công.

### 12.1. Kiểm chứng dữ liệu stale sau thay đổi instance

Với discovery source có thể **thay đổi danh sách trả về** trong test:

~~~text
T0: nguồn trả [A, B] -> cache miss -> [A, B]
T1: nguồn đổi thành [A]
T2: đọc trong TTL -> cache hit -> vẫn [A, B]
T3: đọc sau TTL -> cache miss -> [A]
~~~

Đây là cách kiểm chứng cả **cache reuse** lẫn **expiry/update**. Khi dùng một registry thật, nhớ rằng registry/discovery provider cũng có thể cache. Hãy xác nhận source đã trả [A] trước khi cho rằng LoadBalancer cache sai.

### 12.2. Khi nào một thử nghiệm TTL có thể sai lệch?

- Source trả danh sách rỗng, dẫn đến chính sách miss đặc biệt.
- Gọi nhiều request đồng thời khiến cache miss chồng lên nhau.
- Có nhiều instance của **caller**, mỗi instance có cache riêng.
- Test đọc nhầm bean ServiceInstanceListSupplier ở parent context thay vì child context theo service ID.
- Eureka hoặc provider khác đã cache nên số network request không phản ánh số getInstances().
- HealthCheck supplier phát snapshot theo scheduler, không theo nhịp mỗi request.
- CaffeineSpec đang ghi đè ttl trong YAML.
- Test không chờ entry thực sự được ghi trước khi bắt đầu tính thời gian.

Đây là lý do nên kết hợp **unit test supplier**, **integration test cấu hình**, và **quan sát production**, thay vì chỉ dựa vào một dạng bằng chứng.

## 13. Quan sát cache trong môi trường vận hành

Những dữ liệu đáng theo dõi:

| Dữ liệu | Trả lời câu hỏi gì? |
| --- | --- |
| Số lần DiscoveryClient.getInstances(serviceId) | Có thực sự giảm số lần lấy danh sách từ discovery? |
| Số cache hit/miss nếu cache manager có instrumentation | Entry có được tái sử dụng không? |
| Số service ID trong cache, kích thước danh sách | Cache có hợp lý về bộ nhớ không? |
| Thời gian nhận biết instance mới/dừng | TTL gây bao nhiêu độ trễ cập nhật? |
| Số request thất bại đến instance đã deregister | Dữ liệu stale ảnh hưởng người dùng ra sao? |
| Thời gian chọn instance và tổng latency HTTP | Cache có giúp giảm chi phí hay chỉ che giấu bottleneck? |
| Tỷ lệ retry, timeout, 5xx | Có tăng lỗi khi instance cũ còn trong cache không? |

**Không khẳng định rằng mọi metric cache luôn được Spring Cloud xuất sẵn.** Với Caffeine, thông tin hit/miss thường cần bật stats và liên kết với Micrometer/Actuator theo cấu hình ứng dụng. Metric chọn instance/request của LoadBalancer không nhất thiết là metric cache hit/miss.

Một cách dễ kiểm chứng trong test là bọc DiscoveryClient hoặc supplier nguồn bằng counter và xuất số lần gọi dưới dạng log/metric tùy chỉnh. Trong production, nên tránh log toàn bộ hostname, metadata hay thông tin nhạy cảm của instance ở mức DEBUG thường trực.

### 13.1. Log theo ranh giới supplier

Log minh họa:

~~~text
serviceId=inventory-service stage=discovery sourceReads=1
serviceId=inventory-service stage=cache outputSize=3
serviceId=inventory-service stage=zone outputSize=2
serviceId=inventory-service stage=selection chosen=inventory-a
~~~

Nếu 100 request tạo nhiều log selection nhưng chỉ rất ít log discovery source, đó là dấu hiệu caching có tác dụng. Tuy nhiên, chỉ dựa vào số lượng log nếu bạn chắc chắn **mọi lần đọc nguồn đều được instrument** và không bị log sampling bỏ qua.

### 13.2. Chú ý cache của nhiều service ID

Một caller có thể gọi inventory-service, pricing-service và payment-service:

~~~text
inventory-service -> danh sách [I1, I2]
pricing-service   -> danh sách [P1, P2, P3]
payment-service   -> danh sách [M1]
~~~

Các danh sách được quản lý theo service ID. Không nên gộp số lần discovery của ba dịch vụ lại rồi đánh giá cache hit cho một dịch vụ duy nhất. Bảng metric nên có **service ID** hoặc nhóm service phù hợp, nhưng tránh cardinality quá cao nếu tên service không được kiểm soát.

## 14. Bảng lỗi thường gặp và hướng xử lý

| Triệu chứng | Nguyên nhân có thể | Cách kiểm chứng |
| --- | --- | --- |
| Đã đặt cache.enabled=true nhưng nguồn vẫn được đọc mỗi lần | Custom supplier không có withCaching() hoặc cache manager không được sử dụng | Kiểm tra chuỗi supplier thực tế |
| Lúc đầu hit, sau ít giây lại gọi nguồn | TTL đã hết hoặc entry bị eviction | Kiểm tra ttl / CaffeineSpec / maximumSize |
| Đặt ttl=15s nhưng thực tế gần 20s | CaffeineSpec có expireAfterWrite=20s | Ưu tiên kiểm tra CaffeineSpec |
| Instance vừa dừng vẫn được chọn | Cache LoadBalancer hoặc registry còn giữ snapshot cũ | So sánh cache snapshot và source discovery |
| Không giảm request đến Eureka server như kỳ vọng | EurekaDiscoveryClient vốn có cache riêng | Đo getInstances() và tầng cache registry riêng |
| Round Robin vẫn đổi instance khi cache bật | Đây là hành vi bình thường | Phân biệt chọn instance và lấy danh sách |
| Test không thấy cache hit khi source trả [] | Empty-list được xem là miss trong implementation hiện hành | Dùng snapshot không rỗng để test |
| Trong đợt burst vẫn có nhiều source reads | Cache miss đồng thời hoặc startup warm-up | Thử request tuần tự trước, sau đó kiểm tra burst |
| Hint hoặc sticky session không còn đúng | Cache đặt ngoài filter theo Request | Kiểm tra thứ tự decorator và get(Request) |
| Sau tăng TTL, số timeout tăng | Danh sách stale lâu hơn; instance chết còn được chọn | Quan sát TTL, health, retry và thời gian deregistration |
| Không thấy metric hit/miss | Cache stats/Actuator instrumentation chưa bật hoặc không hỗ trợ | Đo bằng counter nguồn, xác minh cache manager |
| Chỉ một số caller pod thấy instance mới | Mỗi pod có cache/refresh riêng | So sánh snapshot theo pod và service ID |

Khi debug, hãy đi từ **cấu hình global → supplier chain → cache manager → cache entry theo service ID → delegate discovery → HTTP selection**. Nếu ứng dụng sử dụng một supplier chain không có cache, sửa TTL không giúp gì; nếu registry đã trả dữ liệu stale, giảm TTL của LoadBalancer cũng không bảo đảm có dữ liệu mới.

## 15. Checklist triển khai cache toàn cục

- [ ] Có dependency **spring-cloud-starter-loadbalancer** và discovery provider phù hợp.
- [ ] Xác minh **spring.cloud.loadbalancer.cache.enabled** đang có hiệu lực trong môi trường chạy.
- [ ] Kiểm tra supplier cho service ID thực sự chứa **CachingServiceInstanceListSupplier**.
- [ ] Đặt cache **ngay sau nguồn discovery**, trước zone/hint/request-based filtering.
- [ ] Biết rõ cache dùng implementation mặc định hay Caffeine.
- [ ] Nếu dùng CaffeineSpec, không trông đợi thuộc tính ttl/capacity chung tiếp tục điều khiển cache.
- [ ] Phân biệt **capacity=initial capacity** với **maximumSize** của Caffeine.
- [ ] Kiểm tra DiscoveryClient có cache riêng hay không; tránh double caching thiếu chủ đích.
- [ ] Không dùng một danh sách rỗng làm tình huống duy nhất để chứng minh hit.
- [ ] Có unit test đếm delegate.get() khi hit/miss.
- [ ] Có integration test đối chứng cache bật/tắt và kiểm tra TTL.
- [ ] Thử tình huống instance dừng, registry cập nhật và cache hết hạn.
- [ ] Đảm bảo timeout/retry và health check bảo vệ giai đoạn dữ liệu stale.
- [ ] Theo dõi lỗi đến instance cũ, số lần đọc discovery và độ trễ cập nhật.
- [ ] Không log thông tin nhạy cảm từ request hoặc metadata instance.

## 16. Tổng kết

Cache của Spring Cloud LoadBalancer giúp **tái sử dụng danh sách ServiceInstance**, giảm số lần gọi nguồn discovery khi nhiều request cùng sử dụng một service ID. Cấu hình toàn cục gồm **enabled**, **ttl** và **capacity**; khi Caffeine có mặt, có thể dùng **caffeine.spec** để kiểm soát expiration và eviction sâu hơn.

Để chứng minh cache có tác dụng, hãy kiểm tra **decorator CachingServiceInstanceListSupplier đang thực sự nằm trong supplier chain**, rồi đếm **số lần delegate discovery được gọi** trong tình huống có/không có cache và trước/sau TTL. Chỉ nhìn phân bố Round Robin hoặc response HTTP không đủ kết luận cache hit. Cũng cần cân nhắc độ trễ dữ liệu stale, double caching với Eureka, vị trí cache trước các filter theo request, và sự khác nhau giữa từng caller pod.

## 17. Tài liệu tham khảo

- [Spring Cloud Commons 5.0.4 – Spring Cloud LoadBalancer](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html): caching implementations, TTL, capacity, CaffeineSpec, builder và thứ tự supplier.
- [Spring Cloud Commons – Configuration Properties](https://docs.spring.io/spring-cloud-commons/reference/configprops.html): giá trị mặc định của các thuộc tính spring.cloud.loadbalancer.cache.
- [CachingServiceInstanceListSupplier.java](https://github.com/spring-cloud/spring-cloud-commons/blob/main/spring-cloud-loadbalancer/src/main/java/org/springframework/cloud/loadbalancer/core/CachingServiceInstanceListSupplier.java): key theo service ID, cache lookup, empty-list và delegate get().
- [LoadBalancerClientConfiguration.java](https://github.com/spring-cloud/spring-cloud-commons/blob/main/spring-cloud-loadbalancer/src/main/java/org/springframework/cloud/loadbalancer/annotation/LoadBalancerClientConfiguration.java): supplier mặc định cho blocking/reactive discovery.
- [ServiceInstanceListSupplierBuilder.java](https://github.com/spring-cloud/spring-cloud-commons/blob/main/spring-cloud-loadbalancer/src/main/java/org/springframework/cloud/loadbalancer/core/ServiceInstanceListSupplierBuilder.java): cách xây dựng chuỗi decorator.
- [Spring Cloud Netflix Eureka – Reference](https://docs.spring.io/spring-cloud-netflix/reference/spring-cloud-netflix.html): discovery/registry và hành vi của provider Eureka.
