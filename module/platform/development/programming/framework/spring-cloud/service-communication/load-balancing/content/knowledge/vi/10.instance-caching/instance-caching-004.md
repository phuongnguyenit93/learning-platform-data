# Điều kiện dùng Caffeine và cơ chế cache mặc định

Trong **Spring Cloud LoadBalancer**, việc chọn một `ServiceInstance` thường bắt đầu bằng việc lấy danh sách instance của một **service ID** qua `ServiceInstanceListSupplier`. Nếu mỗi request đều phải đọc lại discovery, ứng dụng có thể làm tăng độ trễ và tải lên registry. **Instance cache** giữ một bản danh sách gần đây để các lần chọn tiếp theo sử dụng lại, với cái giá phải quản lý độ mới của dữ liệu.

Bài thuộc chương **Bộ nhớ đệm bản sao** của module **SPRING_CLOUD_SERVICE_COMMUNICATION_LOAD_BALANCING**. Mục tiêu là hiểu **khi nào LoadBalancer sử dụng Caffeine, khi nào dùng cache mặc định, cách cấu hình TTL/capacity**, và cách đánh giá tính đúng đắn khi discovery, health check hay chính sách định tuyến thay đổi. Kiến thức này áp dụng cho giao tiếp giữa dịch vụ qua **RestClient**, **WebClient** và **OpenFeign** đã tích hợp Spring Cloud LoadBalancer; loại HTTP client không tự quyết định loại instance cache.

> Trong bài này, “bản sao” là một instance cùng cung cấp một service. Cache của LoadBalancer lưu **danh sách instance**, không lưu HTTP response, dữ liệu nghiệp vụ, cookie hay kết nối mạng.

## 1. Caching nằm ở đâu trong kiến trúc LoadBalancer?

Một luồng gọi điển hình:

~~~mermaid
flowchart LR
    A["Caller: order-service"] --> B["RestClient / WebClient / OpenFeign"]
    B --> C["LoadBalancer theo service ID"]
    C --> S["ServiceInstanceListSupplier"]
    S --> K{"Có cache hợp lệ?"}
    K -->|Cache hit| L["Danh sách instance đã lưu"]
    K -->|Cache miss / hết TTL| D["DiscoveryClient lấy danh sách"]
    D --> L
    L --> F["Bộ lọc / ưu tiên phù hợp"]
    F --> R["Chọn ServiceInstance"]
    R --> H["HTTP request tới host:port"]
~~~

Thành phần `CachingServiceInstanceListSupplier` bao quanh supplier lấy dữ liệu từ discovery và tái sử dụng danh sách instance giữa các lần chọn. Cơ chế cache vận hành **trước bước chọn đích**. Round Robin, Random hoặc thuật toán khác vẫn thực hiện chọn instance từ danh sách được cung cấp.

Nếu cache lưu `[catalog-a, catalog-b]`, sau đó `catalog-b` bị dừng nhưng cache chưa được làm mới, thuật toán vẫn có thể chọn `catalog-b`. Ngược lại, một instance mới `catalog-c` có thể chưa được chọn cho đến khi danh sách cập nhật.

**Cache giúp giảm chi phí truy vấn danh sách; cache không tự kiểm tra sức khỏe hay đảm bảo request HTTP thành công.**

## 2. Điều kiện để dùng Caffeine và cache mặc định

Spring Cloud Commons cung cấp hai cách triển khai cache cho LoadBalancer. Khi caching được bật và thành phần cache của LoadBalancer được sử dụng, lựa chọn mặc định phụ thuộc vào **classpath runtime**:

| Điều kiện | Triển khai được chọn | Ý nghĩa |
|---|---|---|
| Có dependency `com.github.ben-manes.caffeine:caffeine` trong classpath | Cache dựa trên **Caffeine** | Sử dụng bộ máy cache Caffeine cho instance list |
| Không có dependency Caffeine | `DefaultLoadBalancerCache` đi cùng `spring-cloud-starter-loadbalancer` | Vẫn có cache; không phải mỗi lần đều phải gọi discovery |
| `spring.cloud.loadbalancer.cache.enabled=false` | Vô hiệu hóa cache LoadBalancer qua cấu hình được hỗ trợ | Supplier không sử dụng lớp cache này; discovery có thể vẫn cache riêng |
| Cấu hình supplier tự tạo không đưa cache vào chuỗi | Không có lớp `CachingServiceInstanceListSupplier` trong chuỗi đó | Hành vi phụ thuộc supplier cụ thể, dù có Caffeine trên classpath |

Đây là sự khác nhau quan trọng giữa **lựa chọn backend cache** và **quyết định có cache danh sách instance hay không**.

- Có Caffeine trên classpath là điều kiện để Spring Cloud LoadBalancer dùng **Caffeine-backed implementation** trong cấu hình cache phù hợp.
- Thiếu Caffeine **không** đồng nghĩa caching bị vô hiệu hóa: Spring Cloud có triển khai cache mặc định.
- Chỉ thêm dependency Caffeine **không** khiến một supplier tùy biến vốn không dùng caching tự động có thêm lớp cache.
- `spring.cloud.loadbalancer.cache.enabled` là cờ cấu hình cache ở cấp LoadBalancer; cần kiểm tra cả cấu hình supplier tùy chỉnh khi đánh giá hành vi thực tế.

### Vì sao nói “classpath runtime”?

Một dự án có thể khai báo Caffeine trong source nhưng dependency bị loại bởi cấu hình build, hoặc chỉ tồn tại trong `testImplementation`. Khi ứng dụng thực sự chạy, cơ chế lựa chọn sẽ dựa trên các lớp có trong runtime classpath, không dựa vào tên dependency được viết trong tài liệu.

Do đó, khi chẩn đoán ứng dụng đang dùng cache loại nào, cần kiểm tra **dependency tree/runtime classpath** và configuration thực tế của Spring context.

## 3. Thêm dependency Caffeine

Với Spring Boot/Spring Cloud tương thích và đã quản lý phiên bản dependency phù hợp, có thể thêm Caffeine như sau.

**Gradle (Groovy DSL):**

~~~groovy
dependencies {
    implementation 'org.springframework.cloud:spring-cloud-starter-loadbalancer'
    implementation 'com.github.ben-manes.caffeine:caffeine'
}
~~~

**Maven:**

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-loadbalancer</artifactId>
    </dependency>
    <dependency>
        <groupId>com.github.ben-manes.caffeine</groupId>
        <artifactId>caffeine</artifactId>
    </dependency>
</dependencies>
~~~

Ví dụ giả định dự án đã có Spring Cloud BOM và dependency management phù hợp. Nếu dự án không quản lý phiên bản Caffeine, phải chỉ định phiên bản tương thích theo build hiện có.

Không cần tạo một bean `@Cacheable` riêng để LoadBalancer nhận diện Caffeine trong trường hợp auto-configuration chuẩn. Cache danh sách instance là cơ chế của **Spring Cloud LoadBalancer**, dù sử dụng Caffeine như backend. Không nên đồng nhất nó với cách ứng dụng tự cache kết quả phương thức bằng Spring Cache.

### Khi nào nên chọn Caffeine?

Caffeine hữu ích khi ứng dụng có lưu lượng gọi dịch vụ cao, cần cache in-process hiệu quả và muốn kiểm soát rõ chính sách eviction hoặc giới hạn số entry. Đặc biệt khi nhiều service ID được gọi từ một instance của caller, việc giới hạn size và expiration bằng Caffeine spec có thể thuận tiện.

Tuy nhiên, **không cần thêm Caffeine chỉ để kích hoạt caching**, vì LoadBalancer đã có `DefaultLoadBalancerCache`. Lợi ích thực tế cần được đo: số lượt truy vấn discovery, độ trễ chọn đích, bộ nhớ, cache hit/miss và độ trễ nhìn thấy các thay đổi instance.

## 4. Cache mặc định khi không có Caffeine

Khi `spring-cloud-starter-loadbalancer` có mặt và không tìm thấy Caffeine trong runtime classpath, Spring Cloud dùng `DefaultLoadBalancerCache` cho nhu cầu cache của LoadBalancer. Đây là một triển khai cache riêng có sẵn, khác với việc dùng supplier cơ sở gọi discovery ở mọi lượt chọn.

Theo tài liệu Spring Cloud Commons hiện hành, cấu hình chung mặc định của cache là:

| Thuộc tính | Giá trị mặc định | Ý nghĩa |
|---|---:|---|
| `spring.cloud.loadbalancer.cache.enabled` | `true` | Caching được bật trong cấu hình mặc định |
| `spring.cloud.loadbalancer.cache.ttl` | `35s` | Thời gian sống tính từ lần ghi cache |
| `spring.cloud.loadbalancer.cache.capacity` | `256` | **Initial capacity**, dung lượng khởi tạo |

Cần lưu ý: **`capacity=256` là initial capacity theo tài liệu, không nên diễn giải thành giới hạn cứng tối đa 256 instance hoặc 256 request.** Nếu cần ràng buộc rõ lượng entry trong Caffeine, hãy dùng policy như `maximumSize` trong Caffeine specification.

Giá trị `35s` và `256` là mặc định được công bố trong tài liệu Spring Cloud Commons phiên bản hiện hành; khi dự án khóa một release train khác, cần đối chiếu bảng configuration properties của phiên bản đó.

### Cache miss, hit và hết hạn

~~~mermaid
sequenceDiagram
    participant App as Request caller
    participant Cache as Instance cache
    participant Discovery as DiscoveryClient
    participant LB as LoadBalancer

    App->>Cache: Lần 1: tìm catalog-service
    Cache->>Discovery: Cache miss: lấy instance list
    Discovery-->>Cache: [A, B]
    Cache-->>LB: [A, B]
    App->>Cache: Lần 2: cùng service ID
    Cache-->>LB: Cache hit: [A, B]
    Note over Cache: Entry hết hạn theo TTL
    App->>Cache: Lần 3: cùng service ID
    Cache->>Discovery: Đọc danh sách mới
    Discovery-->>Cache: [A, C]
    Cache-->>LB: [A, C]
~~~

Đây là trình tự minh họa, không phải cam kết mỗi thao tác cache đều sinh ra network call: discovery client bản thân nó có thể đang giữ danh sách trong bộ nhớ. TTL là **thời gian hết hạn tính từ lúc ghi**, không phải lịch đẩy cập nhật chủ động từ registry vào mọi cache instance.

## 5. Cấu hình TTL và capacity chung

Có thể thay đổi hai tham số bằng `application.yml`:

~~~yaml
spring:
  cloud:
    loadbalancer:
      cache:
        enabled: true
        ttl: 20s
        capacity: 128
~~~

Ý nghĩa:

- `enabled: true` bật caching theo cấu hình chung.
- `ttl: 20s` cho entry hết hạn sau 20 giây tính từ lúc ghi.
- `capacity: 128` cấu hình initial capacity của cache LoadBalancer theo thuộc tính chung.

`ttl` được bind thành `Duration` theo cú pháp Spring Boot. Chọn TTL cần tính đến tốc độ cập nhật registry, tần suất instance được tạo/xóa và độ nhạy của ứng dụng với địa chỉ lỗi thời.

Ví dụ, một môi trường thường xuyên autoscale hoặc rolling deployment có thể cần TTL ngắn hơn hệ thống ít thay đổi. Nhưng TTL ngắn làm tăng lần đọc discovery; nếu discovery đang quá tải, điều này có thể phản tác dụng.

**Không coi TTL là thời hạn đảm bảo mọi client phát hiện instance chết.** Dữ liệu có thể được cache ở chính discovery client, kết quả health có vòng cập nhật khác, và một instance có thể hỏng ngay sau khi được chọn.

## 6. Dùng Caffeine specification: cấu hình riêng ghi đè cấu hình chung

Khi đã có Caffeine, có thể sử dụng thuộc tính:

`spring.cloud.loadbalancer.cache.caffeine.spec`

Ví dụ **một cấu hình thay thế** cho khối chung ở phần trước:

~~~yaml
spring:
  cloud:
    loadbalancer:
      cache:
        enabled: true
        caffeine:
          spec: "initialCapacity=64,maximumSize=500,expireAfterWrite=20s"
~~~

Các thành phần của spec:

| Thành phần Caffeine | Tác dụng |
|---|---|
| `initialCapacity=64` | Gợi ý dung lượng khởi tạo |
| `maximumSize=500` | Giới hạn số entry theo chính sách eviction của Caffeine |
| `expireAfterWrite=20s` | Entry hết hạn dựa trên thời điểm ghi |

**Quy tắc quan trọng:** khi cung cấp `spring.cloud.loadbalancer.cache.caffeine.spec`, Spring Cloud LoadBalancer dùng spec đó để tạo cache và **ghi đè các thiết lập cache chung**, kể cả `ttl` và `capacity`. Nếu cấu hình đồng thời:

~~~yaml
spring:
  cloud:
    loadbalancer:
      cache:
        ttl: 10s
        capacity: 256
        caffeine:
          spec: "maximumSize=500,expireAfterWrite=40s"
~~~

thì không được mong đợi `ttl: 10s` và `capacity: 256` vẫn có hiệu lực cho cache Caffeine; các policy liên quan sẽ theo Caffeine spec. Vì vậy nên duy trì **một nguồn cấu hình có chủ đích**, tránh hai giá trị mâu thuẫn khiến người vận hành hiểu sai.

Nếu viết custom Caffeine spec mà quên chính sách expiration phù hợp, hành vi giữ entry có thể khác mong muốn so với TTL mặc định của LoadBalancer. Hãy khai báo rõ `expireAfterWrite` khi nghiệp vụ cần dữ liệu instance tự hết hạn; cân nhắc `maximumSize` khi muốn kiểm soát số entry.

Caffeine spec cho phép nhiều lựa chọn khác, nhưng chỉ nên sử dụng các tùy chọn có thể kiểm chứng trong phiên bản Caffeine thực tế. **Giới hạn entry không phải giới hạn số instance trong một entry**: một service ID có thể ứng với cả một danh sách nhiều `ServiceInstance`.

## 7. Vị trí của CachingServiceInstanceListSupplier trong chuỗi

Khi tự dựng một chuỗi supplier, vị trí của `CachingServiceInstanceListSupplier` quan trọng ngang việc chọn backend cache. Theo hướng dẫn Spring Cloud, nên đặt caching **ngay sau supplier lấy instance qua mạng**, trước các bộ lọc khác.

Ví dụ:

~~~text
DiscoveryClientServiceInstanceListSupplier
               |
               v
CachingServiceInstanceListSupplier
               |
               v
ZonePreferenceServiceInstanceListSupplier
               |
               v
RoundRobinLoadBalancer chọn instance
~~~

Lý do: cache nên giữ danh sách cơ sở theo service ID, không giữ kết quả đã biến đổi theo request.

Giả sử request A cần metadata `version=v1`, request B cần `version=v2`. Nếu lưu cache danh sách đã lọc theo A nhưng khóa cache chỉ phân biệt service ID, B có thể nhận sai danh sách.

~~~text
Discovery trả: [A(v1), B(v2), C(v2)]
                    |
                    v
           Cache [A, B, C]
             /          \
      request v1       request v2
          [A]            [B, C]
~~~

Mẫu này giúp cache chung không trộn dữ liệu của các request khác nhau. Trong hệ thống có quy tắc isolation theo tenant/zone/version, lỗi cache sai vị trí không chỉ ảnh hưởng hiệu năng mà còn có thể vi phạm chính sách định tuyến.

### Ví dụ tùy chỉnh supplier

~~~java
import org.springframework.cloud.loadbalancer.annotation.LoadBalancerClient;
import org.springframework.cloud.loadbalancer.core.ServiceInstanceListSupplier;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@LoadBalancerClient(
    name = "catalog-service",
    configuration = CatalogLoadBalancerConfiguration.class
)
class LoadBalancerClientRegistration {
}

// Đặt lớp này ngoài phạm vi component scan mặc định
// nếu nó được nạp riêng qua @LoadBalancerClient.
class CatalogLoadBalancerConfiguration {

    @Bean
    ServiceInstanceListSupplier catalogInstanceSupplier(
            ConfigurableApplicationContext context) {
        return ServiceInstanceListSupplier.builder()
            .withDiscoveryClient()
            .withCaching()
            .withZonePreference()
            .build(context);
    }
}
~~~

`withDiscoveryClient()` lấy instance qua discovery được cấu hình. `withCaching()` thêm bước cache; `withZonePreference()` áp dụng ưu tiên zone sau đó. `build(context)` dựng chuỗi supplier cho context LoadBalancer tương ứng.

Ví dụ minh họa một phương án tự cấu hình, **không buộc mọi ứng dụng phải đăng ký bean riêng** nếu cấu hình mặc định đã đủ. Không vô tình đưa lớp cấu hình riêng của `catalog-service` vào component scan chung cho các service khác.

## 8. Có cache ở tầng discovery rồi: tránh cache chồng

Một số implementation discovery, ví dụ `EurekaDiscoveryClient`, đã có cơ chế giữ danh sách instance riêng. Nếu thêm một tầng cache LoadBalancer, dữ liệu có thể phải đi qua hai chu kỳ cập nhật:

~~~mermaid
flowchart LR
    A["Registry cập nhật instance"] --> B["Discovery client cache"]
    B --> C["LoadBalancer cache"]
    C --> D["Bộ chọn"]
    D --> E["HTTP client"]
~~~

Giả sử registry gỡ B tại thời điểm T nhưng discovery client chỉ refresh sau một khoảng thời gian. LoadBalancer tiếp tục lấy danh sách cũ từ discovery và có thể còn giữ một entry của riêng mình. **TTL của LoadBalancer không phải giới hạn trên duy nhất của độ trễ hội tụ**, vì còn tầng discovery.

Theo khuyến nghị trong tài liệu Spring Cloud, khi `DiscoveryClient` đã cache instance, nên cân nhắc **tắt cache LoadBalancer** để tránh hai tầng cache gây stale data không cần thiết.

~~~yaml
spring:
  cloud:
    loadbalancer:
      cache:
        enabled: false
~~~

Việc tắt `spring.cloud.loadbalancer.cache.enabled` không vô hiệu hóa toàn bộ discovery hay mọi cache bên trong registry/client khác. Khi dùng custom supplier chain, cũng phải xem có tự thêm `withCaching()` hay không.

Không tự động tắt cache chỉ vì nghe nói registry “có cache”: hãy xác nhận nó có phục vụ dữ liệu đã cache thật không, thời gian cập nhật ra sao, mức truy vấn discovery khi LoadBalancer không cache và tác động tới latency. Mục tiêu là giảm **độ trễ dữ liệu và chi phí**, không phải tối đa hóa số lớp cache.

## 9. Quan hệ với health check

Caching và health check giải quyết hai bài toán khác nhau:

- **Cache**: giảm chi phí truy vấn danh sách instance và chấp nhận một độ trễ cập nhật.
- **Health check**: quan sát một tín hiệu về khả năng phản hồi của từng instance.
- **LoadBalancer**: chọn một instance từ danh sách ứng viên cuối cùng.

`HealthCheckServiceInstanceListSupplier` có thể duy trì và phát cập nhật danh sách healthy theo lịch riêng. Hướng dẫn Spring Cloud về cấu hình supplier tùy chỉnh khuyến nghị dùng **một trong hai `CachingServiceInstanceListSupplier` hoặc `HealthCheckServiceInstanceListSupplier`** trong chuỗi được đề cập, và đặt supplier được chọn ngay sau thành phần lấy dữ liệu qua mạng, trước filter.

Do đó, **không mặc định kết hợp `withCaching()` và `withHealthChecks()` trong cùng ví dụ tùy chỉnh** rồi giả định thời gian sống và trạng thái health sẽ tương tác đúng như mong muốn. Khi hệ thống thực sự cần cả hai, phải hiểu phiên bản/framework, thứ tự delegate và cơ chế phát cập nhật của từng supplier rồi kiểm chứng bằng test.

Ngay cả khi health báo healthy, một instance có thể chết ngay sau bước chọn. HTTP client vẫn cần timeout, xử lý lỗi kết nối và retry có giới hạn.

## 10. Stale instance, cache miss và tình huống lỗi thực tế

Xem xét ba instance `catalog-a`, `catalog-b`, `catalog-c`:

| Thời điểm | Discovery thực tế | Cache của caller | Rủi ro |
|---|---|---|---|
| T0 | [A, B] | [A, B] | Hoạt động bình thường |
| T1: B dừng | [A] | [A, B] | Có thể chọn B rồi lỗi kết nối |
| T2: C đăng ký | [A, C] | [A, B] | Chưa phân phối traffic đến C |
| T3: cache refresh | [A, C] | [A, C] | B bị loại, C có thể được chọn |

Bảng này giả định cache chưa hết hạn giữa T1 và T2. Trong thực tế, discovery cũng có thể trả dữ liệu cũ hoặc các bộ lọc loại thêm instance.

Các sự cố thường gặp:

1. **Cache giữ instance đã chết**: request bị connection refused, timeout hoặc lỗi TLS; giảm TTL có thể giảm khoảng stale nhưng không loại bỏ hoàn toàn race condition.
2. **Cache chưa có instance mới**: startup, rollout hoặc scale-out chưa được LoadBalancer sử dụng ngay; tải có thể vẫn tập trung vào số instance cũ.
3. **Danh sách rỗng ở cache miss**: nếu discovery đang không có ứng viên, LoadBalancer có thể chọn không được instance; cần phân biệt với lỗi từ HTTP server.
4. **Cache sau bộ lọc theo request**: danh sách cache có thể không phù hợp cho request kế tiếp; cần đặt filter theo request sau lớp cache cơ sở.
5. **Cache quá dài khi autoscale liên tục**: danh sách và metadata không phản ánh topology mới, làm tăng lỗi hoặc lệch phân phối.
6. **Cache quá ngắn**: registry bị tăng tải, request đầu tiên sau mỗi lần hết hạn có thể chịu chi phí lấy danh sách mới.

Không dùng cache như phương án thay thế service discovery, health check, circuit breaker hoặc policy routing. Cache là cơ chế tối ưu quá trình **đọc danh sách instance**.

## 11. Caffeine không cache HTTP response của RestClient, WebClient hay OpenFeign

Một nhầm lẫn phổ biến là cho rằng thêm Caffeine vào LoadBalancer sẽ giúp response từ `GET /api/items/42` được trả trực tiếp từ bộ nhớ. Điều này không đúng với instance cache của Spring Cloud LoadBalancer.

~~~mermaid
sequenceDiagram
    participant Caller as order-service
    participant LC as Instance cache
    participant LB as LoadBalancer
    participant Catalog as catalog-service

    Caller->>LC: Lấy danh sách catalog-service
    LC-->>Caller: [A, B] (cache hit)
    Caller->>LB: Chọn instance
    LB-->>Caller: A
    Caller->>Catalog: GET /api/items/42
    Catalog-->>Caller: HTTP 200, JSON
    Note over Caller,Catalog: Response không được instance cache lưu
~~~

Ví dụ với RestClient:

~~~java
// Tạo từ @LoadBalanced RestClient.Builder
ItemDto item = restClient.get()
    .uri("http://catalog-service/api/items/{id}", itemId)
    .retrieve()
    .body(ItemDto.class);
~~~

Kể cả khi danh sách instance được lấy từ cache, HTTP client vẫn gửi request đến instance đã chọn. Với WebClient, request được thực thi qua reactive pipeline; với OpenFeign, request được gọi qua interface; cả hai cũng chỉ hưởng lợi từ việc giảm chi phí lấy instance list.

Nếu ứng dụng muốn cache DTO hoặc HTTP response, đó là thiết kế cache nghiệp vụ/API riêng, cần cơ chế key, TTL, invalidation, quyền truy cập và nhất quán dữ liệu khác hẳn.

## 12. Quan sát và kiểm chứng cấu hình cache

Khi đánh giá cache có ích hay đang gây stale data, nên đo:

| Chỉ số hoặc dấu hiệu | Câu hỏi |
|---|---|
| Cache hit/miss theo service ID | Bao nhiêu lần phải đi lại nguồn danh sách? |
| Số lần đọc discovery | Caching có giảm tải lên discovery không? |
| Thời gian lấy instance list | Cache miss có làm tăng latency lựa chọn? |
| Tuổi và số entry của cache | Dữ liệu đang cũ tới mức nào? |
| Số instance trước/sau các filter | Cache đang giữ danh sách phù hợp không? |
| Tỷ lệ lỗi kết nối theo instance | Có instance đã chết vẫn đang được chọn không? |
| Thời gian rollout/scale-out được phát hiện | Instance mới mất bao lâu để nhận traffic? |
| Không chọn được instance | Cache có đang giữ hoặc nhận danh sách rỗng? |
| Retry và timeout | Stale instance có làm số lần thử tăng không? |

Không giả định mọi metric trên đều được Spring Cloud tự phát ra dưới cùng một tên; có thể cần bổ sung instrumentation hoặc log. Khi log, tránh ghi body, cookie, token và dữ liệu nhạy cảm. Đừng gắn request ID vào metric label vì cardinality sẽ tăng mạnh.

### Các kịch bản kiểm thử có ý nghĩa

1. **Không có Caffeine trên classpath**: caching vẫn chạy theo cấu hình được hỗ trợ, sử dụng triển khai mặc định.
2. **Có Caffeine trên classpath**: xác minh backend Caffeine được chọn và cấu hình spec có hiệu lực.
3. **TTL hết hạn**: sau khi nguồn discovery thay đổi, lần truy cập kế tiếp nhận danh sách mới theo hành vi được cấu hình.
4. **Spec ghi đè TTL chung**: nếu `expireAfterWrite` trong spec khác `cache.ttl`, kiểm tra giá trị spec thực sự chi phối.
5. **Tắt cache LoadBalancer**: kiểm tra DiscoveryClient được gọi theo mô hình mới; nếu discovery tự cache, nhận biết tầng cache vẫn tồn tại.
6. **Instance bị gỡ trong thời gian cache còn hiệu lực**: bảo đảm timeout/retry không kéo dài quá deadline nghiệp vụ.
7. **Thêm instance khi scale-out**: đo thời gian instance mới bắt đầu nhận request.
8. **Zone/hint filter theo request**: bảo đảm dữ liệu cache dùng chung không chứa kết quả lọc của request trước.
9. **Discovery tạm thời không có instance**: ứng dụng báo lỗi lựa chọn instance rõ ràng, không nhầm với HTTP 503 do server trả.
10. **Triển khai nhiều caller**: nhớ rằng cache của từng tiến trình có vòng đời và độ mới độc lập.

Tránh kiểm thử chỉ bằng cách gọi liên tục đúng một instance: cần thay đổi danh sách upstream, tạo cache miss và so sánh trước/sau từng thời điểm. Hành vi refresh còn phụ thuộc cache discovery phía dưới, nên nên kiểm chứng trực tiếp danh sách do supplier cuối cùng phát ra.

## 13. Cách quyết định sử dụng Caffeine, mặc định hay tắt cache

| Bối cảnh | Lựa chọn cần cân nhắc | Tiêu chí xác nhận |
|---|---|---|
| LoadBalancer cần cache, ứng dụng không có Caffeine | Dùng `DefaultLoadBalancerCache` | TTL, latency, số query discovery đạt yêu cầu |
| Có Caffeine và muốn kiểm soát eviction rõ | Dùng Caffeine-backed cache | Spec được áp dụng, size/TTL phù hợp |
| Discovery đã có cache hiệu quả như Eureka | Cân nhắc tắt cache LoadBalancer | Giảm double caching mà không quá tải registry |
| Nhiều request lọc theo hint/version | Cache danh sách gốc, lọc sau cache | Không dùng lại danh sách sai request |
| Instance thay đổi thường xuyên | Đánh giá TTL ngắn hơn hoặc cơ chế cập nhật | Rollout/scale-out được phản ánh đủ nhanh |
| Health check riêng đang dùng | Tránh ghép tùy tiện caching và health supplier | Luồng cập nhật và khả năng phục hồi đúng |
| Lỗi chủ yếu do dependency chậm | Đo saturation, connection pool, timeout | Cache instance list không che nguyên nhân |

Trước khi thay cấu hình, xác minh **phiên bản Spring Cloud Commons đang chạy, runtime classpath, chuỗi `ServiceInstanceListSupplier`, hành vi caching bên trong DiscoveryClient và cơ chế quan sát lỗi**. Một thay đổi TTL có thể không hiệu quả nếu gốc của stale data nằm ở lớp discovery.

## 14. Nguồn tham khảo và nguyên tắc ghi nhớ

Thông số mặc định, cách chọn backend và thứ tự supplier trong bài được đối chiếu từ tài liệu chính thức:

- [Spring Cloud Commons – Spring Cloud LoadBalancer, phần Caching](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html)
- [Spring Cloud Commons – Configuration Properties](https://docs.spring.io/spring-cloud-commons/reference/configprops.html)

**Nguyên tắc chọn cache:** Caffeine được dùng khi dependency có mặt và LoadBalancer caching được cấu hình phù hợp; nếu không có Caffeine, Spring Cloud vẫn có `DefaultLoadBalancerCache`. Cấu hình chung dùng `ttl` và `capacity`, còn `caffeine.spec` ghi đè các thiết lập chung liên quan. Đặt caching ngay sau nguồn lấy instance, tránh cache kết quả đã lọc theo request, và đánh giá double caching ở tầng discovery. Caching giúp chọn instance nhanh và ít truy vấn hơn, nhưng timeout, retry, health check và việc quan sát stale instance vẫn quyết định độ ổn định khi RestClient, WebClient hoặc OpenFeign gọi dịch vụ qua Spring Cloud LoadBalancer.

