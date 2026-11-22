# LoadBalancer cache và cache của thư viện khám phá dịch vụ

Trong kiến trúc microservice, số lượng `ServiceInstance` của một service có thể thay đổi liên tục: replica mới được triển khai, replica cũ ngừng hoạt động, hoặc một bản sao bị đánh dấu không sẵn sàng. Client-side load balancing phải có danh sách instance đủ mới để chọn đích chính xác, đồng thời không thể truy vấn registry từ xa cho mọi request nếu điều đó làm tăng độ trễ và tải lên hạ tầng discovery.

Bởi vậy, một ứng dụng Spring Cloud có thể có **nhiều tầng cache liên quan đến danh sách instance**. Hai tầng dễ nhầm nhất là **Spring Cloud LoadBalancer cache** và **cache của thư viện khám phá dịch vụ (discovery client)**. Cả hai đều có thể giảm truy vấn, nhưng hoạt động ở những ranh giới khác nhau và có chu kỳ làm mới riêng.

Bài học thuộc chương **Bộ nhớ đệm bản sao** của module `SPRING_CLOUD_SERVICE_COMMUNICATION_LOAD_BALANCING`. Module tập trung vào cân bằng tải phía client: chọn `ServiceInstance` theo service ID, discovery, health check và chính sách định tuyến; giao tiếp bằng `RestClient`, `WebClient`, OpenFeign, cấu hình retry/timeout và quan sát lỗi. Mục tiêu ở đây là hiểu từng lớp cache để lựa chọn thiết kế phù hợp, tránh **double caching** và điều tra những tình huống request vẫn gửi tới instance cũ.

## 1. Cache danh sách instance để giải quyết vấn đề gì?

Giả sử `order-service` gọi `inventory-service` qua hostname logic:

~~~http
GET http://inventory-service/internal/instance
~~~

Registry biết ba replica của `inventory-service`:

~~~text
inventory-service
  ├─ inv-1: http://10.1.0.11:8080
  ├─ inv-2: http://10.1.0.12:8080
  └─ inv-3: http://10.1.0.13:8080
~~~

Khi `RestClient`, `WebClient` hoặc OpenFeign được tích hợp Spring Cloud LoadBalancer, client không gửi trực tiếp request đến tên logic này như một địa chỉ vật lý. LoadBalancer nhận service ID, lấy các `ServiceInstance` từ `ServiceInstanceListSupplier`, chọn một instance rồi thực hiện HTTP call tới host/port đã chọn.

Nếu danh sách instance có thể được đọc nhanh từ bộ nhớ, quá trình chọn đích có thể giảm việc tra cứu registry. Nhưng cache phải chấp nhận một đánh đổi: **giảm chi phí truy vấn đổi lấy nguy cơ nhìn thấy dữ liệu cũ**.

Một snapshot đã cache có thể gặp các tình huống:

- Replica mới đã đăng ký nhưng chưa xuất hiện trong danh sách của caller.
- Replica đã bị gỡ khỏi registry nhưng vẫn được chọn vì caller dùng snapshot cũ.
- Metadata `zone`, `weight` hoặc `version` của instance đã đổi nhưng client chưa nhận thay đổi.
- Registry đang không khả dụng; cache có thể tạm giúp caller sử dụng thông tin trước đó, nhưng không đảm bảo các instance trong snapshot vẫn khỏe.

Cache lưu thông tin **instance được biết đến**, không phải bằng chứng rằng instance chắc chắn xử lý request thành công.

## 2. Hai lớp cache nằm ở đâu?

Cần phân biệt **registry** (nguồn thông tin), **discovery client** (thư viện lấy dữ liệu registry) và **Spring Cloud LoadBalancer** (chọn instance để gọi).

~~~mermaid
flowchart LR
    subgraph Registry["Hạ tầng discovery"]
        R["Registry / danh sách đăng ký"]
    end
    subgraph Caller["Ứng dụng caller"]
        D["Discovery client"]
        DC["Cache hoặc snapshot của discovery client"]
        LBC["Spring Cloud LoadBalancer cache"]
        S["ServiceInstanceListSupplier"]
        LB["LoadBalancer chọn instance"]
        H["HTTP client"]
    end
    R --> D
    D --> DC
    DC --> S
    S --> LBC
    LBC --> LB
    LB --> H
~~~

Sơ đồ trình bày **các vị trí cache có thể có**, không khẳng định tất cả discovery implementation đều triển khai đúng hai tầng riêng biệt. Trong một số thư viện, cache là cấu trúc nội bộ của discovery client và không có bước truy cập mạng đồng bộ cho mỗi lần lấy instance. Trong ứng dụng khác, discovery client thực hiện truy vấn theo yêu cầu và chỉ LoadBalancer có cache.

### So sánh nhanh

| Tiêu chí | LoadBalancer cache | Cache của discovery client |
|---|---|---|
| Thuộc thành phần | Spring Cloud LoadBalancer | Thư viện discovery: Eureka, adapter khác |
| Dữ liệu chính | Danh sách `ServiceInstance` mà supplier cung cấp, theo service ID | Snapshot hoặc dữ liệu instance/registry do discovery client quản lý |
| Điểm đọc | Trước khi LoadBalancer chọn instance | Khi ứng dụng hoặc supplier hỏi discovery client |
| Cơ chế làm mới | TTL/eviction và việc đọc lại delegate | Poll, watch, refresh hoặc cơ chế đặc thù implementation |
| Cấu hình | `spring.cloud.loadbalancer.cache.*` và supplier chain | Nhóm thuộc tính riêng của discovery client |
| Nguy cơ | Cache thêm một snapshot phía trên discovery | Snapshot phía client chậm cập nhật so với registry |
| Câu hỏi cần kiểm tra | LoadBalancer đã hết TTL và gọi lại nguồn chưa? | Discovery client đã biết thay đổi ở registry chưa? |

**Không đồng nhất** cache phía LoadBalancer với cache response HTTP, cache DNS hay connection pool. Chúng giải quyết các vấn đề khác nhau. Trong bài này, “cache” chỉ tập trung vào **danh sách instance dùng để chọn đích**.

## 3. LoadBalancer cache hoạt động như thế nào?

Trong Spring Cloud LoadBalancer, `ServiceInstanceListSupplier` cung cấp danh sách ứng viên. Một supplier làm nhiệm vụ cache, thường được biết tới qua `CachingServiceInstanceListSupplier`, có thể bọc supplier nguồn để tái sử dụng danh sách đã lấy.

Luồng đơn giản:

~~~text
LoadBalancer cần danh sách của inventory-service
   |
   v
CachingServiceInstanceListSupplier
   |
   +--> Cache hit: trả danh sách đang còn hợp lệ
   |
   +--> Cache miss/hết hiệu lực:
           delegate.get()
              |
              v
        Discovery-backed supplier
              |
              v
        Danh sách ServiceInstance mới
              |
              v
        Lưu cache và trả kết quả
~~~

Cache thường được tổ chức theo service ID; nhưng **nội dung danh sách lưu lại** phụ thuộc việc decorator được đặt ở vị trí nào trong supplier chain.

Ví dụ:

~~~text
Discovery source -> LoadBalancer cache -> Zone filter -> LoadBalancer
~~~

Ở cách này, cache giữ danh sách từ discovery. Zone filter sử dụng dữ liệu đã cache để chọn các instance thích hợp với zone.

Nếu đảo thành:

~~~text
Discovery source -> Filter phụ thuộc request -> LoadBalancer cache -> LoadBalancer
~~~

thì cache có nguy cơ giữ kết quả lọc của request trước rồi áp dụng sai cho request tiếp theo nếu khóa cache không biểu diễn đầy đủ ngữ cảnh lọc.

**Nguyên tắc:** Đặt cache gần supplier lấy dữ liệu discovery, trước các bước lọc theo request, trừ khi bạn đã kiểm chứng cơ chế cache key cho trường hợp cụ thể.

## 4. Cấu hình LoadBalancer cache

Spring Cloud LoadBalancer cung cấp các thuộc tính cache trong nhóm `spring.cloud.loadbalancer.cache`. Ví dụ tùy chỉnh TTL và dung lượng:

~~~yaml
spring:
  cloud:
    loadbalancer:
      cache:
        enabled: true
        ttl: 20s
        capacity: 256
~~~

Ý nghĩa:

- `enabled: true`: cho phép cơ chế LoadBalancer cache khi supplier và auto-configuration tương ứng sử dụng nó.
- `ttl: 20s`: đặt thời gian tồn tại của entry trong cache theo chính sách mà implementation hỗ trợ.
- `capacity: 256`: giới hạn dung lượng cache; đây **không phải** là số replica tối đa mà một service có thể có.

TTL là một tham số đánh đổi. TTL ngắn giúp dữ liệu được đọc lại thường xuyên hơn nhưng tăng nhu cầu lấy danh sách từ nguồn. TTL dài giảm lượt đọc nguồn nhưng có thể kéo dài khoảng thời gian caller dùng thông tin cũ.

Không nên coi TTL là thời hạn tuyệt đối từ lúc registry thay đổi đến khi mọi request đi đúng đích. Thời điểm entry được tạo, hành vi eviction, chu kỳ làm mới của discovery client và quá trình đánh dấu health đều ảnh hưởng thời gian cập nhật thực tế.

### Lựa chọn implementation cache

Spring Cloud LoadBalancer có thể sử dụng cache implementation mặc định; khi Caffeine có trên classpath và được cấu hình phù hợp, có thể dùng Caffeine cho cache phía LoadBalancer. Ví dụ cấu hình Caffeine:

~~~yaml
spring:
  cloud:
    loadbalancer:
      cache:
        enabled: true
        caffeine:
          spec: maximumSize=500,expireAfterWrite=20s
~~~

Với cấu hình Caffeine `spec`, các chính sách như dung lượng và hết hạn nằm trong chính chuỗi spec. Đừng đặt cả `ttl`/`capacity` và `caffeine.spec` rồi mặc định cả hai nhóm sẽ có hiệu lực như nhau: **spec riêng có thể ghi đè cấu hình mặc định về TTL/capacity**. Khi đổi cache provider, hãy kiểm tra tài liệu của đúng phiên bản Spring Cloud và Caffeine.

Một hệ thống có ít service ID nhưng mỗi service có nhiều instance không nhất thiết cần capacity quá cao: cache lưu danh sách theo service, không phải mỗi replica luôn chiếm một entry riêng biệt.

## 5. Tạo supplier chain có cache

Khi cần tùy chỉnh supplier cho một service dùng discovery không có cache riêng, bạn có thể cấu hình builder:

~~~java
import org.springframework.cloud.loadbalancer.core.ServiceInstanceListSupplier;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class InventoryLoadBalancerConfiguration {

    @Bean
    ServiceInstanceListSupplier serviceInstanceListSupplier(
            ConfigurableApplicationContext context) {

        return ServiceInstanceListSupplier.builder()
                .withDiscoveryClient()
                .withCaching()
                .build(context);
    }
}
~~~

Gắn cấu hình vào service ID:

~~~java
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cloud.loadbalancer.annotation.LoadBalancerClient;

@SpringBootApplication
@LoadBalancerClient(
    name = "inventory-service",
    configuration = InventoryLoadBalancerConfiguration.class
)
public class CallerApplication {
}
~~~

Lưu ý về thiết kế:

1. `withDiscoveryClient()` làm nguồn tạo danh sách `ServiceInstance`.
2. `withCaching()` thêm lớp cache cho dữ liệu từ nguồn.
3. `@LoadBalancerClient(name = "inventory-service", ...)` giới hạn cấu hình cho đúng service ID.
4. Đặt `InventoryLoadBalancerConfiguration` **ngoài phạm vi component scan thông thường** của ứng dụng, hoặc loại nó khỏi scan, để bean này không vô tình trở thành cấu hình toàn cục.
5. Đừng khai báo hai supplier bean cạnh tranh trong một LoadBalancer context. Cấu hình ở đây là **một lựa chọn thay thế**, không phải thứ cần cộng thêm vào một chain mặc định đã được đăng ký.

Ví dụ chỉ minh họa cấu trúc và phụ thuộc vào Spring Boot/Spring Cloud tương thích. Nếu nguồn discovery đã cache sẵn, cần đánh giá lại việc gọi `withCaching()` thay vì bật mặc định cả hai tầng.

## 6. Cache của thư viện khám phá dịch vụ: ví dụ Eureka

Không phải discovery client nào cũng hoạt động giống nhau. **Eureka là trường hợp điển hình có cache phía client**.

Eureka client thường định kỳ lấy và duy trì một snapshot thông tin instance từ Eureka Server. Khi ứng dụng gọi API discovery như `DiscoveryClient.getInstances("inventory-service")`, thư viện có thể trả dữ liệu từ snapshot local thay vì gửi truy vấn mạng đồng bộ trong chính lời gọi đó.

Mô hình khái quát:

~~~mermaid
sequenceDiagram
    participant I as Inventory replica
    participant ES as Eureka Server
    participant EC as Eureka client của caller
    participant S as InstanceListSupplier
    participant LB as Spring Cloud LoadBalancer
    I->>ES: Đăng ký / heartbeat / cập nhật trạng thái
    EC->>ES: Refresh registry theo chu kỳ
    ES-->>EC: Snapshot hoặc thay đổi registry
    LB->>S: Yêu cầu danh sách instance
    S->>EC: getInstances("inventory-service")
    EC-->>S: Danh sách từ dữ liệu local
    S-->>LB: Danh sách ServiceInstance
~~~

Một cấu hình Eureka client minh họa:

~~~yaml
eureka:
  client:
    fetch-registry: true
    registry-fetch-interval-seconds: 30
~~~

Thuộc tính `registry-fetch-interval-seconds` quy định chu kỳ lấy registry theo cơ chế Eureka client. Đây là một phần của quá trình cập nhật snapshot phía discovery, **không phải TTL của LoadBalancer cache**.

Ngoài polling ở client, phía Eureka Server còn có các chu kỳ nhận heartbeat, đánh giá lease, thay đổi trạng thái instance và có thể có tầng cache phản hồi của server. Vì thế thay đổi trạng thái của một replica không nhất thiết xuất hiện tức thì trong registry snapshot mà caller dùng.

Với các discovery client khác:

- **Consul:** cơ chế tra cứu, refresh và khả năng cache phụ thuộc loại discovery client, cấu hình Consul và cách nó truy vấn catalog/health. Không mặc định Consul client có cache local giống Eureka.
- **Kubernetes:** thông tin endpoint có thể được cung cấp qua API/watch hoặc adapter khác. Độ trễ đồng bộ phụ thuộc cách triển khai; không lấy cấu hình cache của Eureka áp vào Kubernetes.
- **SimpleDiscoveryClient:** dữ liệu được khai báo tĩnh trong cấu hình. Nó không tự loại địa chỉ chỉ vì tiến trình không còn chạy; đây không phải cache registry động.

Bất kể dùng implementation nào, điều cần xác minh là **caller nhìn thấy danh sách nào từ discovery client ở thời điểm hiện tại** và cơ chế nào cập nhật danh sách đó.

## 7. Double caching: khi hai cache cùng lưu snapshot

Giả sử ứng dụng dùng Eureka, với hai tầng dữ liệu:

~~~text
Eureka Server
    |
    v
Eureka client snapshot (được làm mới theo chu kỳ)
    |
    v
LoadBalancer cache (TTL riêng)
    |
    v
RoundRobinLoadBalancer
    |
    v
HTTP request tới replica
~~~

Nếu một replica bị gỡ khỏi registry, có thể xuất hiện hai độ trễ:

1. **Discovery client chưa refresh:** Eureka Server đã biết replica bị gỡ, nhưng snapshot của caller vẫn chứa nó.
2. **LoadBalancer cache chưa hết TTL:** Discovery client đã biết replica bị gỡ, nhưng LoadBalancer tiếp tục cung cấp danh sách cũ mà nó cache trước đó.

Đây là **double caching**. Không phải lúc nào cũng xảy ra đầy đủ hai độ trễ, nhưng nó làm khó suy luận thời điểm thay đổi được nhìn thấy vì mỗi tầng có chính sách cập nhật riêng.

### Dòng thời gian minh họa

~~~text
t0     Registry và caller đều biết A, B, C
t1     C ngừng hoạt động
t2     Registry nhận biết C không còn hợp lệ
t3     Discovery client refresh, danh sách còn A, B
t4     LoadBalancer cache hết TTL, đọc lại A, B
t5     Request mới chỉ còn chọn giữa A và B
~~~

Các mốc là ví dụ giải thích, **không phải các SLA hoặc thời gian cố định**. Tùy thời điểm cache được lấp đầy, thứ tự và độ trễ có thể khác. Nếu chỉ tắt LoadBalancer cache mà Eureka client chưa cập nhật, caller vẫn có thể chọn C; ngược lại, nếu Eureka client đã cập nhật nhưng LoadBalancer cache chưa hết hạn, caller cũng có thể tiếp tục chọn C.

Spring Cloud LoadBalancer khuyến nghị **không chồng thêm LoadBalancer cache** lên discovery client vốn đã có cache phù hợp, điển hình là Eureka.

## 8. Cấu hình tránh double caching với Eureka

Khi sử dụng Eureka client đã duy trì registry local, một phương án hợp lý là để Eureka quản lý snapshot và **tắt cache của Spring Cloud LoadBalancer**:

~~~yaml
spring:
  cloud:
    loadbalancer:
      cache:
        enabled: false

eureka:
  client:
    fetch-registry: true
    registry-fetch-interval-seconds: 30
~~~

Lúc này, caller có thể lấy danh sách từ discovery-backed supplier và sử dụng snapshot của Eureka client, không cần một TTL LoadBalancer thứ hai.

Nếu bạn đã tự khai báo supplier chain bằng builder, **đồng thời bỏ `withCaching()`** khỏi cấu hình tùy chỉnh:

~~~java
@Bean
ServiceInstanceListSupplier serviceInstanceListSupplier(
        ConfigurableApplicationContext context) {
    return ServiceInstanceListSupplier.builder()
            .withDiscoveryClient()
            .build(context);
}
~~~

Không nên vừa chủ ý tắt LoadBalancer cache bằng property vừa cố tạo caching decorator thủ công, vì việc khởi tạo và sử dụng cache manager còn phụ thuộc điều kiện auto-configuration của phiên bản thư viện.

Việc chọn chu kỳ Eureka registry fetch ngắn hơn có thể giảm độ trễ cập nhật nhưng làm tăng số lượt trao đổi với server. Hãy cân nhắc số lượng caller, tần suất thay đổi instance và đặc tính triển khai, thay vì giảm mọi khoảng thời gian xuống mức cực thấp.

**Tắt một tầng cache không thay thế health check.** Registry snapshot mới cũng không bảo đảm một instance đang phục vụ tốt tại thời điểm gửi HTTP request.

## 9. Với discovery không có cache riêng: cân nhắc dùng LoadBalancer cache

Nếu discovery client thực hiện truy vấn mạng cho mỗi lần lấy danh sách và chưa có caching hiệu quả, LoadBalancer cache có thể giúp giảm chi phí mạng. Một cấu hình có thể là:

~~~yaml
spring:
  cloud:
    loadbalancer:
      cache:
        enabled: true
        ttl: 15s
        capacity: 256
~~~

Khi đó, supplier chain có thể sử dụng `withDiscoveryClient().withCaching()` như ví dụ trước.

Tuy nhiên, trước khi quyết định, hãy trả lời những câu hỏi:

- Discovery client có cache local hoặc watch-based snapshot sẵn chưa?
- Số lần lấy danh sách instance thực sự tạo request mạng là bao nhiêu?
- Danh sách thay đổi với tần suất nào khi scale hoặc deploy?
- Tác động của một instance cũ đối với request có nghiêm trọng không?
- Có bộ lọc health hoặc zone nào phải nhìn dữ liệu mới ngay không?
- Có nhiều caller cùng tra cứu một registry và gây tải đáng kể không?

Không có TTL “tốt nhất” áp dụng cho mọi hệ thống. Ví dụ `15s` chỉ là một lựa chọn thử nghiệm, cần đo thực tế rồi điều chỉnh theo độ trễ discovery, tỉ lệ lỗi và đặc tính deploy.

## 10. So sánh hai cách triển khai thường gặp

| Tình huống | Lựa chọn khởi đầu | Lý do |
|---|---|---|
| Eureka client duy trì registry snapshot local | Ưu tiên tắt LoadBalancer cache | Tránh lưu cùng danh sách qua hai TTL/chu kỳ làm mới |
| Discovery client không có cache và truy vấn nguồn thường xuyên | Cân nhắc bật LoadBalancer cache | Giảm số lần truy vấn registry từ caller |
| SimpleDiscoveryClient với danh sách tĩnh | Cache thường không giải quyết vấn đề freshness | Nguồn tự nó không tự cập nhật instance hỏng |
| Discovery theo watch/snapshot | Kiểm tra cache có sẵn trước khi thêm tầng mới | Dữ liệu có thể đã được duy trì cục bộ và cập nhật bởi watch |
| Chỉ một số service rất nhạy với thay đổi replica | Cân nhắc cấu hình theo service hoặc điều chỉnh cách discovery | Tránh áp một chính sách cache không phù hợp cho mọi dịch vụ |
| Supplier có filter phụ thuộc request | Cache gần nguồn discovery, không cache vô điều kiện kết quả đã lọc | Tránh trả nhầm danh sách ứng viên của request khác |

Khi không chắc chắn discovery client đang cache hay không, hãy kiểm tra tài liệu và hành vi của phiên bản tương ứng. Đừng suy đoán rằng “đã dùng service discovery” đồng nghĩa “đã có một cache phù hợp”.

## 11. Tác động của cache đối với health check và retry

Cache chỉ phản ánh dữ liệu đã được đọc, nên cần phân biệt **được đăng ký**, **được coi là healthy**, và **thực sự gửi HTTP thành công**.

### Health check

Một `HealthCheckServiceInstanceListSupplier` hoặc cơ chế health của registry có thể lọc instance không khỏe, nhưng các hệ thống này có chu kỳ kiểm tra và tiêu chí sức khỏe khác nhau. Nếu cache nằm ở vị trí không phù hợp trong supplier chain, nó có thể giữ danh sách mà health/filter chưa cập nhật.

Health check nên dùng endpoint phù hợp với trạng thái sẵn sàng phục vụ, không chỉ endpoint luôn trả `200 OK`. Nó cũng phải xem xét timeout, tần suất kiểm tra và chính sách khi tất cả instance bị loại.

### Retry

Khi client gửi request tới instance đã ngừng hoạt động, retry có thể thử lại trên cùng hoặc instance khác tùy cấu hình. Retry không làm cache trở nên mới hơn và không bảo đảm luôn chọn đích tốt. Đặc biệt, retry yêu cầu không idempotent như một `POST` tạo tài nguyên cần được thiết kế cẩn thận để tránh tác dụng phụ lặp lại.

Quan hệ giữa các cơ chế:

~~~mermaid
flowchart TD
    A["Danh sách từ discovery/cache"] --> B["Lọc health/zone/metadata nếu có"]
    B --> C["LoadBalancer chọn ServiceInstance"]
    C --> D["HTTP request"]
    D --> E{"Thành công?"}
    E -- Có --> F["Trả response"]
    E -- Không --> G["Chính sách timeout/retry"]
    G --> H{"Cho phép thử lại?"}
    H -- Có --> C
    H -- Không --> I["Trả lỗi / fallback nghiệp vụ"]
~~~

Sơ đồ mang tính khái quát. Một số cấu hình retry sẽ yêu cầu chọn lại instance từ supplier và có thể kèm chính sách tránh instance vừa thất bại; không phải mọi retry đều đi theo cùng một luồng. Hãy đo số lần thử HTTP riêng với số request logic.

## 12. Thực hành quan sát độ trễ cập nhật danh sách

Mục tiêu của thực hành là nhận ra điểm nào đang chứa danh sách cũ, không phải chỉ kiểm tra round robin có chia đều request hay không.

### Chuẩn bị

Dùng một caller `order-service`, hai replica `inventory-service` và một discovery implementation đã chọn. Mỗi replica cung cấp endpoint:

~~~http
GET /internal/instance
~~~

Response ví dụ:

~~~json
{
  "serviceId": "inventory-service",
  "instanceId": "inv-1"
}
~~~

Caller sử dụng `RestClient`, `WebClient` hoặc OpenFeign có tích hợp LoadBalancer để gửi nhiều request bằng hostname logic `inventory-service`.

### Quy trình thử nghiệm

1. Khởi chạy `inv-1` và `inv-2`, bảo đảm discovery nhìn thấy cả hai.
2. Gọi qua LoadBalancer và xác nhận response có hai `instanceId` khác nhau.
3. Ghi lại danh sách instance từ discovery client **tại caller** và danh sách cuối do `ServiceInstanceListSupplier` cung cấp, nếu ứng dụng có công cụ quan sát.
4. Dừng `inv-2` và ghi thời điểm dừng.
5. Theo dõi lúc registry cập nhật, lúc discovery client tại caller không còn chứa `inv-2`, và lúc supplier cuối không còn cung cấp `inv-2`.
6. Ghi tỷ lệ lỗi kết nối hoặc timeout trong giai đoạn chuyển tiếp.
7. Thử thay đổi TTL của LoadBalancer cache trong môi trường cho phép và so sánh lại các mốc.

Không dùng `SimpleDiscoveryClient` tĩnh để kỳ vọng bước 5 tự động xảy ra. Nếu danh sách được khai báo cố định trong YAML, việc dừng tiến trình không tự cập nhật nguồn discovery. Hãy dùng registry động hoặc một nguồn mock có thể thay đổi dữ liệu để kiểm tra freshness.

### Bảng quan sát

| Thời điểm | Registry | Discovery client tại caller | Supplier cuối | Kết quả HTTP |
|---|---|---|---|---|
| Trước khi dừng | `inv-1, inv-2` | `inv-1, inv-2` | `inv-1, inv-2` | Cả hai xử lý |
| Registry đã cập nhật | `inv-1` | Có thể vẫn còn `inv-2` | Có thể vẫn còn `inv-2` | Một số request có thể lỗi |
| Discovery đã refresh | `inv-1` | `inv-1` | Có thể vẫn còn `inv-2` nếu LB cache chưa hết hạn | Có thể còn lỗi |
| Cả hai lớp cập nhật | `inv-1` | `inv-1` | `inv-1` | Chỉ chọn `inv-1` |

Bảng này là **kịch bản lý thuyết**, không phải kết quả chạy thật. Trong một thiết kế chỉ có cache discovery, cột supplier cuối thường đọc dữ liệu discovery đã cập nhật mà không chờ thêm một TTL LoadBalancer.

## 13. Cách chẩn đoán khi client vẫn chọn instance đã bị gỡ

Nếu client vẫn gọi `inv-2` dù nó không còn được mong đợi, hãy đi theo thứ tự từ nguồn đến LoadBalancer:

~~~mermaid
flowchart TD
    A["Caller vẫn chọn instance cũ"] --> B{"Registry còn instance?"}
    B -- Có --> C["Kiểm tra deregistration, heartbeat, lease, health"]
    B -- Không --> D{"Discovery client tại caller còn instance?"}
    D -- Có --> E["Kiểm tra polling/watch/refresh của discovery"]
    D -- Không --> F{"Supplier cuối còn instance?"}
    F -- Có --> G["Kiểm tra LB cache TTL, vị trí cache, filter"]
    F -- Không --> H["Kiểm tra log chọn đích, HTTP connection, proxy, retry"]
~~~

Các dấu hiệu thường gặp:

- **Registry chưa biết replica chết:** heartbeat/lease/health chưa cập nhật hoặc deregistration thất bại.
- **Registry đúng, caller sai:** snapshot của discovery client chưa refresh hoặc lỗi kết nối tới registry.
- **Discovery client đúng, supplier sai:** có khả năng tồn tại LoadBalancer cache hoặc custom supplier giữ dữ liệu cũ.
- **Supplier đúng nhưng HTTP vẫn lỗi:** instance khác cũng có thể đã hỏng; lỗi còn có thể nằm ở DNS, TLS, connection pool, timeout hoặc service đích.
- **Trọng số hay zone không đổi:** metadata mới chưa đi hết các tầng hoặc filter/weighted supplier chưa được bật trong context của service đó.

Một kỹ thuật hữu ích là log có kiểm soát ba thông tin theo thời điểm: **service ID**, **số lượng/ID ứng viên ở từng tầng**, và **instance được chọn**. Không log token, dữ liệu cá nhân hoặc toàn bộ metadata nhạy cảm. Với metrics, tránh label có cardinality không giới hạn, nhất là request ID hoặc danh tính instance ngắn hạn.

## 14. Khi nào nên điều chỉnh TTL và chu kỳ discovery?

Đừng tối ưu cache chỉ dựa trên một phép đo độ trễ trung bình. Cần xét ít nhất bốn đại lượng:

| Đại lượng | TTL quá dài / refresh chậm | TTL quá ngắn / refresh quá nhanh |
|---|---|---|
| Số lần đọc registry | Thấp hơn | Cao hơn |
| Tốc độ nhìn thấy replica mới | Chậm hơn | Có thể nhanh hơn |
| Thời gian có thể chọn replica đã gỡ | Có thể dài hơn | Có thể ngắn hơn |
| Tải lên discovery và caller | Thường thấp hơn | Có thể tăng đáng kể |

Những lưu ý khi vận hành:

- **Đo chi phí thực** của việc tra cứu discovery trước khi thêm một lớp cache.
- **Kiểm tra khả năng chịu lỗi của registry**, nhất là khi nhiều caller refresh cùng lúc.
- **Tối ưu theo chu kỳ scale/deploy:** hệ thống thay đổi instance liên tục sẽ nhạy hơn với snapshot cũ.
- **Đặt giới hạn lỗi hợp lý:** connect timeout, read timeout và retry có kiểm soát giúp giảm tác động khi một instance hỏng bị chọn.
- **Giữ nhất quán chính sách:** nếu mỗi caller dùng TTL và refresh khác nhau, kết quả định tuyến giữa các caller có thể khác trong cùng thời điểm.
- **Đừng giảm TTL đến mức cực nhỏ** rồi coi đó là giải pháp health check tức thì. Cache freshness, heartbeat và HTTP transport là những cơ chế khác nhau.

Khi hệ thống dùng Eureka, thay đổi `registry-fetch-interval-seconds` ảnh hưởng polling của Eureka client. Thay đổi `spring.cloud.loadbalancer.cache.ttl` chỉ có ý nghĩa nếu lớp LoadBalancer cache đang hoạt động. Hai thuộc tính không thay thế cho nhau.

## 15. Các hiểu nhầm cần tránh

**“LoadBalancer cache và Eureka cache là một.”** Không đúng. Chúng thuộc hai lớp khác nhau, có thể cùng lưu danh sách instance và có vòng đời cập nhật riêng.

**“Giảm LoadBalancer TTL xuống 1 giây thì mọi replica bị gỡ đều biến mất trong 1 giây.”** Không đúng. Nếu discovery snapshot chưa cập nhật hoặc registry chưa phát hiện instance hỏng, LoadBalancer vẫn lấy được dữ liệu cũ từ nguồn.

**“Bật `withCaching()` luôn giúp ổn định hơn.”** Không nhất thiết. Nó có thể giảm truy vấn discovery, nhưng với discovery client đã cache tốt thì thêm tầng cache đôi khi làm tình trạng stale nghiêm trọng hơn.

**“Cache TTL thấp là đủ, không cần health check hoặc timeout.”** Không đúng. Instance có thể lỗi ngay sau khi được chọn. Timeout, health và retry giải quyết những khía cạnh khác nhau.

**“SimpleDiscoveryClient tĩnh sẽ tự bỏ instance chết sau khi hết TTL.”** Không đúng. TTL chỉ khiến caller đọc lại nguồn; nếu nguồn tĩnh vẫn chứa host chết thì kết quả vẫn không thay đổi.

**“Cache capacity bằng số replica.”** Không đúng về mặt khái niệm. Cache LoadBalancer lưu tập danh sách gắn với service ID; cách đếm entry phụ thuộc implementation, không đơn giản là mỗi replica một entry.

## 16. Checklist trước khi đưa cấu hình cache vào môi trường thật

| Hạng mục | Câu hỏi xác minh |
|---|---|
| Discovery implementation | Đang dùng Eureka, Consul, Kubernetes adapter hay nguồn tĩnh? |
| Cache phía discovery | Thư viện đó có duy trì snapshot/cache local không? Làm mới như thế nào? |
| LoadBalancer cache | Có bật không? Có `withCaching()` trong supplier chain tùy chỉnh không? |
| Double caching | Hai tầng cache cùng hoạt động có thật sự cần thiết không? |
| TTL/capacity | Có lý do vận hành và số liệu để chọn các giá trị không? |
| Caffeine | Đã có dependency? `caffeine.spec` có ghi đè các thuộc tính khác không? |
| Scope | Supplier và chính sách cache đang áp dụng cho đúng service ID chưa? |
| Health và retry | Cách loại instance hỏng, timeout, retry và idempotency đã được xét chưa? |
| Freshness test | Đã đo thời gian từ khi replica mất đến khi caller không còn chọn nó chưa? |
| Observability | Có thể so sánh registry, snapshot discovery và supplier cuối không? |

## 17. Tổng kết

- **LoadBalancer cache** giữ danh sách do supplier cung cấp để giảm chi phí lấy lại ứng viên; nó có TTL, capacity và có thể được cấu hình bằng `spring.cloud.loadbalancer.cache.*`.
- **Cache của discovery client** nằm gần nguồn registry hơn; ví dụ Eureka client thường duy trì snapshot local và refresh theo chu kỳ.
- **Double caching** có thể khiến caller tiếp tục chọn instance cũ ngay cả khi một tầng đã cập nhật; vì vậy Spring Cloud LoadBalancer thường khuyến nghị tránh cache bổ sung nếu discovery client đã có cache phù hợp.
- Với Eureka, một lựa chọn phổ biến là `spring.cloud.loadbalancer.cache.enabled=false` và không dùng `withCaching()` trong custom supplier chain.
- Với discovery không có cache hiệu quả, LoadBalancer cache có thể hữu ích, nhưng TTL phải dựa trên đánh đổi giữa freshness và chi phí tra cứu.
- Không coi cache là health check, retry, circuit breaker hay cache response HTTP.
- Khi điều tra request đi sai đích, hãy lần lượt kiểm tra **registry → snapshot discovery client → supplier/LoadBalancer cache → instance được chọn → HTTP transport**.

Nắm rõ ranh giới giữa các tầng cache giúp bạn cấu hình Spring Cloud LoadBalancer hợp lý hơn, giảm request tới instance không còn khả dụng và hiểu chính xác vì sao hành vi phân phối giữa các bản sao thay đổi theo thời gian.

