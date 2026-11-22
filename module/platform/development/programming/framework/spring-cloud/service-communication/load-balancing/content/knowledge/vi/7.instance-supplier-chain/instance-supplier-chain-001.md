# Thiết kế ServiceInstanceListSupplier bằng builder và decorator

Khi một client gọi `http://inventory-service`, Spring Cloud LoadBalancer cần một danh sách `ServiceInstance` trước khi chọn địa chỉ đích. Danh sách này được cung cấp bởi `ServiceInstanceListSupplier`. Thiết kế supplier quyết định dữ liệu được lấy từ đâu và những bản sao nào có thể trở thành ứng viên sau khi áp dụng cache, health check, zone hoặc chính sách định tuyến.

Bài học thuộc chương **Chuỗi cung cấp bản sao** của module `SPRING_CLOUD_SERVICE_COMMUNICATION_LOAD_BALANCING`. Mục tiêu của module là hiểu cơ chế cân bằng tải phía client: chọn `ServiceInstance` theo service ID, discovery, health check và chính sách định tuyến; thực hành giao tiếp ổn định bằng `RestClient`, `WebClient`, OpenFeign, retry/timeout và quan sát lỗi. Ở đây, ta tập trung vào hai công cụ thiết kế chuỗi cung cấp ứng viên: **builder** của Spring Cloud LoadBalancer và **decorator** để bổ sung hoặc tùy chỉnh hành vi.

Sau bài học, bạn có thể tự tạo một supplier chain theo service ID, hiểu thứ tự từng lớp, viết decorator lọc instance theo metadata, kiểm tra danh sách trước và sau khi lọc, và tránh những lỗi thường gặp khi kết hợp cache với chính sách phụ thuộc request.

## 1. Ranh giới trách nhiệm: supplier cung cấp, LoadBalancer chọn

Luồng gọi điển hình:

~~~mermaid
flowchart LR
    C["RestClient / WebClient / OpenFeign"] --> L["LoadBalancer cho inventory-service"]
    L --> S["ServiceInstanceListSupplier"]
    S --> D["DiscoveryClient hoặc nguồn tĩnh"]
    D --> S
    S --> F["Danh sách ứng viên đã lọc"]
    F --> L
    L --> I["Chọn một ServiceInstance"]
    I --> H["HTTP đến host:port"]
~~~

Với cùng một service ID, discovery có thể trả ba bản sao:

~~~text
inventory-service
  ├─ inv-a | localhost:8081 | trafficTier=stable
  ├─ inv-b | localhost:8082 | trafficTier=canary
  └─ inv-c | localhost:8083 | trafficTier=stable
~~~

Nếu chính sách của caller chỉ cho phép `trafficTier=stable`, supplier nên cung cấp `inv-a` và `inv-c`. `RoundRobinLoadBalancer` sau đó chọn một trong hai. **Thuật toán chọn instance không có trách nhiệm tự thực hiện bộ lọc traffic tier**; danh sách đầu vào phải phản ánh chính sách đã thống nhất.

`ServiceInstanceListSupplier` làm việc ở lớp danh sách ứng viên. Nó không gửi HTTP, không thực hiện nghiệp vụ của service đích, không thay thế service discovery và không bảo đảm request sẽ thành công. Timeout, retry và xử lý lỗi nằm ở các lớp phối hợp khác.

## 2. API và cấu trúc của một supplier chain

Interface cung cấp phương thức lấy service ID, lấy danh sách, và một biến thể có request context:

~~~java
String getServiceId();
Flux<List<ServiceInstance>> get();
Flux<List<ServiceInstance>> get(Request request);
~~~

Trong các API Spring Cloud LoadBalancer đang dùng, `Request` là abstraction chứa ngữ cảnh lựa chọn; kiểu `Flux<List<ServiceInstance>>` cho phép trả về danh sách trong luồng reactive. Nếu triển khai chỉ cần danh sách thông thường, `get()` đã đủ; nếu chính sách phụ thuộc một request cụ thể thì phải chú ý `get(Request request)`.

Supplier chain thường có hai nhóm thành phần:

| Nhóm | Nhiệm vụ | Ví dụ |
|---|---|---|
| **Nguồn (source)** | Tạo danh sách ban đầu từ registry hoặc cấu hình | Discovery client, nguồn tĩnh |
| **Decorator** | Nhận danh sách từ delegate rồi cache, lọc hoặc ưu tiên | Caching, health check, zone preference, hint, decorator tự viết |

Một chain có thể trông như sau:

~~~mermaid
flowchart TD
    A["DiscoveryClient supplier"] --> B["Caching supplier"]
    B --> C["Health-check supplier"]
    C --> D["Traffic-tier decorator"]
    D --> E["Danh sách tới LoadBalancer"]
~~~

Sơ đồ này minh họa thứ tự **dữ liệu được xử lý**. Trong code, mỗi decorator giữ tham chiếu đến một supplier nằm bên trong. Khi LoadBalancer gọi decorator ngoài cùng, lời gọi được chuyển vào bên trong trước rồi danh sách đi qua từng bước xử lý theo chiều ngược lại. Vì vậy, thứ tự khi tạo chain cần được kiểm tra cẩn thận.

## 3. Thiết kế với ServiceInstanceListSupplier.builder()

Spring Cloud LoadBalancer có builder để ghép nguồn và các decorator mà không phải tự khởi tạo từng lớp. Ví dụ một caller muốn lấy danh sách từ discovery, cache danh sách nguồn và ưu tiên instance cùng zone:

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
            .withZonePreference()
            .build(context);
    }
}
~~~

Ý nghĩa từng bước:

1. `withDiscoveryClient()` chọn nguồn lấy các `ServiceInstance` do cơ chế discovery cung cấp.
2. `withCaching()` bổ sung cache để tránh tra cứu lại nguồn liên tục theo mỗi lần lựa chọn.
3. `withZonePreference()` áp dụng ưu tiên zone khi có cấu hình zone của caller và metadata zone phù hợp trên instance.
4. `build(context)` tạo supplier chain gắn với application context mà LoadBalancer sử dụng.

Đoạn code trên là **mẫu cấu hình cho một service**. Khả năng thực tế của từng bước còn phụ thuộc phiên bản Spring Cloud, discovery client được cài đặt và metadata có sẵn. Builder không tự tạo registry, không tự gán zone cho instance, và không tự khiến một instance trở thành healthy.

Nếu bài toán chỉ yêu cầu discovery và cache, giữ chain tối giản:

~~~java
return ServiceInstanceListSupplier.builder()
    .withDiscoveryClient()
    .withCaching()
    .build(context);
~~~

Khi cần health check phía client, có thể dùng chain tương ứng:

~~~java
return ServiceInstanceListSupplier.builder()
    .withDiscoveryClient()
    .withHealthChecks()
    .build(context);
~~~

Health-check supplier cần endpoint health có thể truy cập được, cơ chế HTTP tương ứng và cấu hình kiểm tra phù hợp. Tên builder method trong tài liệu ví dụ cần được đối chiếu với phiên bản Spring Cloud mà dự án đang sử dụng; không tùy tiện ghép tất cả decorator vào một chain khi chưa xác định nhu cầu.

## 4. Đăng ký cấu hình riêng theo service ID

`@LoadBalancerClient` gắn cấu hình với service ID cụ thể. Ví dụ ở ứng dụng gọi `inventory-service`:

~~~java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cloud.loadbalancer.annotation.LoadBalancerClient;

@SpringBootApplication
@LoadBalancerClient(
    name = "inventory-service",
    configuration = InventoryLoadBalancerConfiguration.class
)
public class CallerApplication {

    public static void main(String[] args) {
        SpringApplication.run(CallerApplication.class, args);
    }
}
~~~

Spring Cloud LoadBalancer tạo context riêng theo service ID để tra cứu các bean phục vụ lựa chọn instance. Cấu hình `InventoryLoadBalancerConfiguration` cần được đặt **ngoài phạm vi component scan chung** của ứng dụng, hoặc được loại khỏi component scan. Nếu lớp đó bị quét như một cấu hình toàn cục, bean supplier dành riêng cho `inventory-service` có thể vô tình ảnh hưởng đến service khác.

Cách tổ chức package minh họa:

~~~text
com.example.caller
  └─ CallerApplication.java
com.example.loadbalancer.inventory
  └─ InventoryLoadBalancerConfiguration.java
~~~

Ứng dụng chính ở `com.example.caller` có thể tham chiếu cấu hình bằng class, trong khi package cấu hình riêng không bị component scan tự động của package ứng dụng quét vào context cha. Nếu dự án có quy tắc component scan khác, hãy kiểm tra lại phạm vi của nó.

**Không tạo nhiều bean `ServiceInstanceListSupplier` cùng cạnh tranh trong một LoadBalancer context.** Một chain hoàn chỉnh nên được tạo và đăng ký cho service đó. Khi muốn thêm decorator tùy chỉnh, hãy sửa chain hiện có thay vì tạo thêm một bean độc lập cùng kiểu.

## 5. Decorator: thêm hành vi mà không thay nguồn discovery

Builder xử lý tốt những chức năng đã được Spring Cloud hỗ trợ. Khi có một chính sách nội bộ, chẳng hạn chỉ gửi traffic tới các instance mang metadata `trafficTier=stable`, ta có thể viết decorator nhận supplier khác làm `delegate`.

Nguyên tắc thiết kế:

- Decorator không tự tra registry; nó lấy danh sách từ delegate.
- Decorator không thay đổi trực tiếp danh sách mà cache đang giữ.
- Kết quả lọc có thể là danh sách mới, kể cả danh sách rỗng nếu đó là yêu cầu.
- Phương thức có request context phải chuyển ngữ cảnh xuống delegate.
- Quy tắc fallback phải được lựa chọn có chủ đích và tài liệu hóa.

Ví dụ class `TrafficTierSupplier` lọc theo metadata:

~~~java
import java.util.List;
import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.loadbalancer.Request;
import org.springframework.cloud.loadbalancer.core.DelegatingServiceInstanceListSupplier;
import org.springframework.cloud.loadbalancer.core.ServiceInstanceListSupplier;
import reactor.core.publisher.Flux;

public final class TrafficTierSupplier
        extends DelegatingServiceInstanceListSupplier {

    private final String requiredTier;

    public TrafficTierSupplier(
            ServiceInstanceListSupplier delegate,
            String requiredTier) {
        super(delegate);
        this.requiredTier = requiredTier;
    }

    @Override
    public Flux<List<ServiceInstance>> get() {
        return delegate.get().map(this::filterByTier);
    }

    @Override
    public Flux<List<ServiceInstance>> get(Request request) {
        return delegate.get(request).map(this::filterByTier);
    }

    private List<ServiceInstance> filterByTier(
            List<ServiceInstance> instances) {
        return instances.stream()
            .filter(instance -> requiredTier.equals(
                instance.getMetadata().get("trafficTier")))
            .toList();
    }
}
~~~

Cơ chế hoạt động: mỗi khi delegate trả một danh sách, `map(this::filterByTier)` biến đổi danh sách đó thành các instance có metadata phù hợp. `List.toList()` tạo một danh sách kết quả mới, không sửa dữ liệu nguồn.

Ở đây, **không có fallback sang tier khác**. Nếu không có instance `stable`, supplier trả danh sách rỗng và LoadBalancer không có ứng viên để chọn. Đây là hành vi có chủ đích khi tier thể hiện một ranh giới định tuyến phải được giữ nghiêm ngặt. Nếu tier chỉ là ưu tiên hiệu năng hoặc affinity và cho phép fallback, hãy viết rõ chính sách dự phòng thay vì tự động bỏ điều kiện lọc trong mọi trường hợp.

Decorator dùng một `requiredTier` cố định cho tất cả request của service ID. Nếu nhu cầu khác nhau theo từng request, hãy thiết kế riêng cách đọc context và truyền dữ liệu qua `get(Request request)`; ví dụ này chưa phải là request-aware routing.

## 6. Ghép builder với decorator tự viết

Có thể để builder tạo phần nguồn discovery và cache, sau đó bọc thêm decorator:

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

        ServiceInstanceListSupplier sourceAndCache =
            ServiceInstanceListSupplier.builder()
                .withDiscoveryClient()
                .withCaching()
                .build(context);

        return new TrafficTierSupplier(sourceAndCache, "stable");
    }
}
~~~

Đây là **cấu hình thay thế** cho bean builder ở phần trước, không phải bean thứ hai thêm vào bên cạnh. Chain tạo được có thứ tự xử lý:

~~~text
LoadBalancer
    -> TrafficTierSupplier
        -> CachingServiceInstanceListSupplier
            -> DiscoveryClient-backed supplier
~~~

Khi request tới, lời gọi chạy từ ngoài vào trong; danh sách trả về chạy ngược từ nguồn discovery qua cache rồi mới được lọc theo tier. Vì vậy cache chỉ lưu danh sách nền tảng, còn kết quả chính sách tier được tính sau cache.

Với một filter phải xét theo từng request, cách bố trí này còn tránh rủi ro dùng lại kết quả đã lọc của request trước cho request sau. Đừng đặt một cache chung ngoài cùng nếu cache key không phân biệt những yếu tố request làm thay đổi danh sách ứng viên.

## 7. Vì sao thứ tự các decorator quan trọng?

Xét hai cấu trúc sau.

**Phương án A: cache danh sách discovery rồi lọc.**

~~~text
Discovery -> Cache -> TrafficTierFilter -> LoadBalancer
~~~

Cache giữ danh sách discovery. Lớp lọc quyết định kết quả mỗi lần LoadBalancer cần ứng viên. Thông tin tier có thể thay đổi chính sách ở lớp ngoài mà không làm ô nhiễm cache danh sách nền tảng.

**Phương án B: lọc trước rồi cache kết quả lọc.**

~~~text
Discovery -> TrafficTierFilter -> Cache -> LoadBalancer
~~~

Nếu filter dựa trên request context và cache không phân biệt các context đó, danh sách của request đầu có thể bị tái sử dụng sai cho request khác. Ví dụ request A yêu cầu `stable`, request B yêu cầu `canary` nhưng B lại nhận danh sách đã lọc cho A.

Bảng nguyên tắc:

| Vấn đề | Cách xử lý |
|---|---|
| Cache dữ liệu discovery | Ưu tiên đặt cache gần nguồn discovery, trước các filter phụ thuộc request. |
| Health check | Đặt gần nguồn danh sách và bảo đảm endpoint health đúng; cân nhắc sự tương tác với cache. |
| Zone preference | Áp dụng sau khi có danh sách và metadata zone hợp lệ. |
| Filter theo request | Giữ request context trong suốt chain; tránh cache kết quả mà không có cache key phù hợp. |
| Filter có danh sách rỗng | Chọn rõ fail-closed hay fallback, dựa trên ý nghĩa nghiệp vụ. |
| Nhiều decorator | Ghi lại thứ tự và xác minh danh sách qua từng bước. |

Trong Spring Cloud LoadBalancer, tài liệu thường khuyến nghị đặt supplier dùng caching hoặc health checking sát nguồn lấy instance qua mạng, trước các supplier lọc khác. Trường hợp muốn kết hợp cả cache và health check cần kiểm tra hành vi refresh, TTL và phiên bản thư viện đang dùng để tránh danh sách cũ hoặc kiểm tra sức khỏe trùng lặp.

## 8. Chuẩn bị nguồn thử nghiệm với metadata

Để kiểm tra decorator mà chưa cần một registry thực, có thể dùng `SimpleDiscoveryClient` với danh sách instance tĩnh trong ứng dụng caller:

~~~yaml
spring:
  application:
    name: caller-service
  cloud:
    discovery:
      client:
        simple:
          instances:
            inventory-service:
              - uri: http://localhost:8081
                metadata:
                  trafficTier: stable
              - uri: http://localhost:8082
                metadata:
                  trafficTier: canary
              - uri: http://localhost:8083
                metadata:
                  trafficTier: stable
~~~

Trong mô hình này, ba tiến trình `inventory-service` phải thực sự chạy ở các port tương ứng. SimpleDiscoveryClient chỉ cung cấp danh sách đã khai báo; nó không chứng minh các tiến trình còn hoạt động và không thay thế health check.

Khi gọi qua supplier chỉ cho phép `stable`, kết quả mong đợi là tập:

~~~text
localhost:8081
localhost:8083
~~~

`localhost:8082` bị loại vì metadata `trafficTier=canary`. Nếu cả hai instance `stable` khả dụng, LoadBalancer có thể chọn một trong hai theo thuật toán đã cấu hình. Tỷ lệ phân phối thực tế còn phụ thuộc thuật toán, cấu hình và trạng thái instance.

Đừng sử dụng `trafficTier` như một cơ chế bảo mật. Metadata và filter là công cụ định tuyến; việc kiểm soát quyền truy cập giữa các nhóm dịch vụ vẫn cần chính sách mạng và xác thực phù hợp.

## 9. Gọi thử qua RestClient có LoadBalancer

Trong caller, cấu hình builder được đánh dấu `@LoadBalanced`:

~~~java
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;

@Configuration
class CallerHttpConfiguration {

    @Bean
    @LoadBalanced
    RestClient.Builder loadBalancedRestClientBuilder() {
        return RestClient.builder();
    }
}
~~~

Sau đó tạo client:

~~~java
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

@Component
public class InventoryProbeClient {

    private final RestClient restClient;

    public InventoryProbeClient(
            @LoadBalanced RestClient.Builder builder) {
        this.restClient = builder.build();
    }

    public String readInstanceIdentity() {
        return restClient.get()
            .uri("http://inventory-service/internal/instance")
            .retrieve()
            .body(String.class);
    }
}
~~~

Endpoint `/internal/instance` ở mỗi bản sao có thể trả JSON chứa `instanceId` hoặc port để quan sát bản sao thực sự xử lý request. Khi cấu hình tier `stable`, ta kỳ vọng không có response của bản sao `canary`.

Cùng một supplier chain vẫn có thể phục vụ request tạo bởi `WebClient` hoặc OpenFeign khi client đó được tích hợp với Spring Cloud LoadBalancer và sử dụng cùng service ID. Khác biệt giữa HTTP client là cách dựng và gửi request; danh sách ứng viên vẫn do LoadBalancer context của service cung cấp.

## 10. Thiết kế decorator theo request context

Decorator ở trên sử dụng `requiredTier` cố định. Khi từng request cần một tier khác nhau, `get(Request request)` trở thành điểm mở rộng quan trọng.

Một quy trình thiết kế hợp lý:

1. Quy định trường context mang tier và bên nào được phép đặt giá trị đó.
2. Xác định cách thành phần HTTP client hoặc LoadBalancer truyền tier vào `Request` của quá trình chọn instance.
3. Trong decorator, lấy context từ request bằng kiểu API phù hợp với phiên bản đang dùng; không ép kiểu tùy tiện.
4. Gọi `delegate.get(request)`, rồi lọc danh sách theo context đã đọc.
5. Xác định chính sách khi thiếu tier, giá trị tier không hợp lệ hoặc không còn ứng viên.

Pseudo-code mô tả ý tưởng:

~~~text
get(request):
    candidates = delegate.get(request)
    tier = readValidatedTierFromContext(request)

    if tier is absent:
        return applyDocumentedDefaultPolicy(candidates)

    return candidates with metadata.trafficTier == tier
~~~

Không nên giả định header `X-Traffic-Tier` của HTTP request tự động xuất hiện trong `Request` của LoadBalancer. Cần một cơ chế tích hợp rõ ràng để đưa dữ liệu từ request HTTP vào load-balancing request context. Với client hỗ trợ hint hoặc sticky-session sẵn có, có thể cân nhắc supplier tích hợp của Spring Cloud thay vì viết lại toàn bộ.

Nếu tier mang ý nghĩa phân tách tenant hoặc môi trường nhạy cảm, đừng tin giá trị client bên ngoài tự khai báo. Caller phải kiểm tra quyền và xác định tier được phép trước khi chuyển vào pipeline.

## 11. Kiểm thử theo lớp và kiểm thử tích hợp

Không nên chỉ kiểm tra rằng ứng dụng khởi động. Một chain có thể khởi động thành công nhưng trả danh sách không đúng vì metadata sai hoặc bean cấu hình nằm nhầm context.

Với ví dụ ba instance, kiểm thử bằng các trường hợp sau:

| Kịch bản | Kết quả mong đợi |
|---|---|
| Discovery trả ba instance | Supplier nền tảng có cả 8081, 8082, 8083. |
| Filter `stable` | Danh sách cuối chỉ còn 8081, 8083. |
| Filter `canary` | Danh sách cuối chỉ còn 8082. |
| Filter không có instance phù hợp | Danh sách rỗng theo chính sách fail-closed. |
| Metadata thiếu `trafficTier` | Instance bị loại khỏi danh sách khi yêu cầu tier cụ thể. |
| Một instance `stable` dừng | Caller có thể gặp lỗi kết nối nếu nguồn tĩnh chưa loại instance; cần health/discovery để cập nhật ứng viên. |
| Cùng service ID nhưng cấu hình sai scope | Phải phát hiện và sửa việc cấu hình supplier ảnh hưởng service ngoài ý muốn. |
| Lặp nhiều request qua LoadBalancer | Mọi response đến từ tập instance được phép; thuật toán chọn trong tập đó. |

Đối với unit test decorator, có thể dùng một supplier giả trả về danh sách `ServiceInstance` cố định và kiểm tra cả `get()` lẫn `get(request)`. Với kiểm thử tích hợp, chạy nhiều bản sao trả về định danh riêng, gọi qua service ID rồi kiểm tra định danh trong response.

Khi có cache, kiểm tra thêm hành vi sau khi thêm hoặc xóa instance: thay đổi trong registry có thể chưa xuất hiện ngay ở danh sách mà cache cung cấp. Khi thêm health check, kiểm tra health path, timeout của lần kiểm tra và chính sách dành cho danh sách rỗng.

Không suy luận rằng round robin hỏng chỉ vì các instance không được chọn theo một thứ tự cố định trong vài request. Hãy xác minh tập ứng viên trước, sau đó mới đánh giá thuật toán chọn instance.

## 12. Quan sát lỗi và vận hành

Khi gặp lỗi `No servers available` hoặc response báo không có instance khả dụng, nên kiểm tra pipeline theo thứ tự:

~~~mermaid
flowchart TD
    A["Client gọi service ID"] --> B{"Discovery có instance?"}
    B -- Không --> C["Kiểm tra service ID, registry, cấu hình nguồn"]
    B -- Có --> D{"Cache có dữ liệu phù hợp?"}
    D -- Không --> E["Kiểm tra TTL và cache"]
    D -- Có --> F{"Health / zone / metadata lọc còn ứng viên?"}
    F -- Không --> G["Kiểm tra điều kiện lọc, metadata, fallback"]
    F -- Có --> H["Kiểm tra thuật toán chọn và HTTP transport"]
~~~

Một số lỗi thiết kế thường gặp:

- Đưa filter phụ thuộc request vào trong cache chung rồi cache kết quả đã lọc.
- Dùng `get()` trong decorator request-aware, khiến delegate không nhận request context.
- Sửa trực tiếp danh sách dùng chung do supplier khác hoặc cache trả về.
- Khai báo nhiều bean cùng kiểu trong LoadBalancer context mà không biết bean nào được dùng.
- Đặt `@LoadBalancerClient` config trong component scan toàn cục.
- Bật health check nhưng endpoint health bị chặn hoặc sai path.
- Giả định metadata zone/traffic tier tự có trong registry.
- Fallback sang mọi instance khi filter thực ra phải cách ly một nhóm traffic.

Trong môi trường vận hành, log có kiểm soát nên chứa service ID, loại supplier chain, số ứng viên đầu vào/đầu ra và định danh instance được chọn. Khi cần điều tra cụ thể, correlation ID giúp đối chiếu request giữa caller và callee. Tránh đưa request ID, instance ID biến đổi liên tục hoặc metadata có cardinality cao thành metric label không giới hạn.

## 13. Những nguyên tắc cần ghi nhớ

- `ServiceInstanceListSupplier.builder()` ghép nguồn discovery và các decorator có sẵn; `DelegatingServiceInstanceListSupplier` giúp thêm logic riêng mà không viết lại nguồn dữ liệu.
- Một chain nên có nguồn rõ ràng, thứ tự decorator rõ ràng và một bean cuối cùng cho mỗi service ID.
- Cache danh sách nền tảng gần nguồn discovery để tránh dùng lại kết quả lọc phụ thuộc request.
- `get(Request request)` giữ ngữ cảnh cần thiết cho các chính sách theo request.
- Filter trả danh sách rỗng phải được xử lý như một quyết định định tuyến rõ ràng.
- `@LoadBalancerClient` cho phép cấu hình theo service; đặt class cấu hình ngoài component scan chung để tránh ảnh hưởng không mong muốn.
- Test cần kiểm tra tập ứng viên được tạo ra trước khi đánh giá hành vi round robin, retry, timeout hoặc chất lượng giao tiếp HTTP.

Khi thiết kế supplier chain đúng, Spring Cloud LoadBalancer sẽ chọn trong tập `ServiceInstance` phù hợp với discovery, trạng thái và chính sách định tuyến. Đây là nền tảng cho việc sử dụng `RestClient`, `WebClient` hoặc OpenFeign ổn định khi một service có nhiều bản sao.

