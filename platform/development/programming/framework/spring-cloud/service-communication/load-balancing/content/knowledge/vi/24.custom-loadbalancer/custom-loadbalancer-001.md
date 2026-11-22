# Tiêu chí chọn cấu hình có sẵn hay viết thành phần riêng

Trong **Spring Cloud LoadBalancer**, nhu cầu “định tuyến thông minh hơn” không đồng nghĩa phải tự viết một thuật toán LoadBalancer. Nhiều yêu cầu như **round-robin, chọn ngẫu nhiên, ưu tiên zone, trọng số, hint, sticky session hoặc health check** đã có sẵn dưới dạng thuật toán hoặc `ServiceInstanceListSupplier`. Chỉ khi một **ràng buộc bắt buộc** không được các thành phần này đáp ứng, việc viết code riêng mới có thể là lựa chọn đúng.

Bài thuộc chương **Tùy biến LoadBalancer** đặt ra câu hỏi thực tế: *khi nào chỉ cấu hình thuộc tính, khi nào ghép các supplier có sẵn, khi nào viết một supplier lọc ứng viên và khi nào thật sự cần thuật toán chọn `ServiceInstance` riêng?*

Mục tiêu không phải tạo càng nhiều class custom càng tốt, mà là chọn giải pháp **đúng hợp đồng định tuyến, dễ kiểm thử, quan sát được và có cách rollback**. Ví dụ sử dụng `order-service` gọi `catalog-service` bằng service ID thông qua `RestClient` hoặc `WebClient`.

## 1. Trước khi chọn giải pháp: diễn đạt yêu cầu bằng quy tắc có thể kiểm thử

So sánh hai yêu cầu:

> *“Nếu có thể, ưu tiên instance cùng zone để giảm độ trễ.”*

và:

> *“Dữ liệu thuộc khu vực A tuyệt đối không được gửi đến instance ngoài khu vực A, kể cả khi khu vực A không còn instance.”*

Hai câu đều nhắc đến vùng địa lý nhưng có **hợp đồng fallback trái ngược**:

| Tiêu chí | Ưu tiên mềm (soft preference) | Ràng buộc cứng (hard constraint) |
|---|---|---|
| Không có instance cùng vùng | Có thể dùng instance khác vùng | Phải trả không có ứng viên hoặc lỗi được kiểm soát |
| Mục tiêu | Latency, locality, giảm chi phí cross-zone | Chính sách bảo mật, phân vùng dữ liệu, residency |
| Thành phần phù hợp | `ZonePreferenceServiceInstanceListSupplier` có sẵn | Bộ lọc strict/allowlist tùy biến, kèm kiểm soát ở backend |
| Chỉ bật preset có đủ không? | Thường có, nếu ngữ nghĩa fallback phù hợp | **Không** nếu preset fallback về toàn bộ danh sách |
| Kiểm thử quan trọng nhất | Có ưu tiên đúng khi đủ instance | **Không bao giờ** chọn instance bị cấm khi thiếu ứng viên |

**Bước đầu tiên luôn là đặc tả hành vi khi không có ứng viên hợp lệ**, sau đó mới chọn property hoặc viết code.

Ví dụ yêu cầu rõ ràng:

~~~text
serviceId: catalog-service
policy: prefer-same-zone
preferredZone: zone-a
onNoPreferredInstance: fall back to all discovered instances
onNoInstanceAtAll: return no-server error
routingSignal: ServiceInstance.metadata["zone"]
~~~

Một yêu cầu strict có thể viết:

~~~text
serviceId: payment-service
policy: require-region
allowedRegion: region-a
onNoAllowedInstance: fail closed; do not choose another region
routingSignal: trusted ServiceInstance.metadata["region"]
securityBoundary: backend/authorization must independently enforce region
~~~

Cấu hình LoadBalancer là tối ưu hóa/định tuyến ở **phía client**, không thay thế kiểm soát truy cập hoặc chính sách dữ liệu **ở phía server**.

## 2. Bốn cấp độ tùy biến, từ ít code đến nhiều code

Có thể chọn giải pháp theo thứ tự tăng dần về quyền kiểm soát và chi phí bảo trì:

~~~mermaid
flowchart TD
    A["Viết rõ yêu cầu và hành vi fallback"]
    B{"Preset có đúng hoàn toàn<br/>ngữ nghĩa chính sách?"}
    C["Cấp 1: property / cấu hình có sẵn"]
    D{"Ghép supplier có sẵn<br/>đã đủ chưa?"}
    E["Cấp 2: cấu hình chuỗi supplier"]
    F{"Chỉ cần thay đổi tập<br/>instance đủ điều kiện?"}
    G["Cấp 3: viết custom supplier / filter"]
    H["Cấp 4: viết custom ReactorServiceInstanceLoadBalancer"]
    I["Test correctness, failure, latency, rollback"]
    A --> B
    B -->|"Có"| C --> I
    B -->|"Không"| D
    D -->|"Có"| E --> I
    D -->|"Không"| F
    F -->|"Có"| G --> I
    F -->|"Không; cần thuật toán chọn mới"| H --> I
~~~

| Cấp | Thay đổi gì? | Khi nào chọn? | Chi phí chính |
|---|---|---|---|
| **1. Property/preset** | Chọn cấu hình hoặc policy được Spring Cloud cung cấp | Weighted theo metadata, same-instance, zone, hint với fallback có thể chấp nhận | Thấp nhất; cần hiểu đúng semantics |
| **2. Chuỗi supplier có sẵn** | Ghép discovery, cache, health, zone, hint, weight theo thứ tự | Cần kết hợp nhiều chính sách nhưng không thay hành vi lõi | Thứ tự chain, cache, request context |
| **3. Supplier tùy biến** | Lọc, sắp xếp hoặc biến đổi danh sách ứng viên | Cần allowlist/fail-closed hoặc tiêu chí lọc riêng | Logic chính sách, dữ liệu metadata, refresh |
| **4. Thuật toán LoadBalancer tùy biến** | Quyết định chọn một instance từ tập ứng viên theo cách mới | Least-connections, scoring đa yếu tố, affinity phức tạp theo trạng thái động | Đồng thời, hiệu năng, state, fairness, fallback, observability |

**Nguyên tắc thiết kế:** ưu tiên mở rộng điểm nhỏ nhất giải quyết được yêu cầu. Nếu chỉ cần lọc ứng viên không hợp lệ, một `ServiceInstanceListSupplier` mới thường ít phức tạp hơn thay toàn bộ `ReactorServiceInstanceLoadBalancer`.

## 3. Thành phần Spring Cloud đã có sẵn để lựa chọn

Spring Cloud LoadBalancer cung cấp một số thành phần quen thuộc; cần tách **thuật toán chọn** khỏi **nguồn và bộ lọc ứng viên**.

| Nhu cầu | Thành phần có sẵn | Cần kiểm tra |
|---|---|---|
| Chia lượt giữa các instance | `RoundRobinLoadBalancer` (mặc định thông dụng) | Không bảo đảm instance cùng latency/khả năng phục vụ |
| Chọn instance ngẫu nhiên | `RandomLoadBalancer` | Không phải weighted hay least-loaded |
| Phân phối theo weight | `WeightedServiceInstanceListSupplier` | Metadata `weight` mặc định 1 nếu không có |
| Ưu tiên cùng zone | `ZonePreferenceServiceInstanceListSupplier` | Khi không có match, trả lại toàn bộ danh sách |
| Hint-routing | `HintBasedServiceInstanceListSupplier` | Khi không có hint hoặc không match, thường trả toàn bộ danh sách |
| Ưu tiên instance đã dùng trước đó | `SameInstancePreferenceServiceInstanceListSupplier` | Là preference; không phải bảo đảm affinity tuyệt đối |
| Sticky theo cookie của request | `RequestBasedStickySessionServiceInstanceListSupplier` | Hỗ trợ phụ thuộc request context/integration; kiểm tra WebClient và điều kiện cụ thể |
| Kiểm tra health định kỳ | `HealthCheckServiceInstanceListSupplier` | Khi không có healthy instance, mặc định fallback về danh sách nguồn |
| Cache danh sách instance | `CachingServiceInstanceListSupplier` | TTL và cache ở discovery client có thể làm dữ liệu stale |
| Nhận danh sách từ discovery | `DiscoveryClientServiceInstanceListSupplier` hoặc reactive variant | Chỉ phản ánh dữ liệu nguồn theo chu kỳ/độ trễ discovery |

Ngoài ra, một số phiên bản còn có các supplier/preset khác như subset, API versioning hoặc retry awareness. **Không giả định mọi lựa chọn có mặt ở mọi phiên bản Spring Cloud.** Đối chiếu tài liệu và configuration metadata đúng release train.

### Những gì LoadBalancer không tự làm

- Không tự mở TCP/TLS hoặc điều khiển HTTP connection pool.
- Không tự giới hạn tổng thời gian nghiệp vụ hoặc bật circuit breaker.
- Không tự đảm bảo body của `POST` có thể replay khi retry.
- Không thực thi chính sách bảo mật ở downstream server.
- Không biến mọi metadata `weight` hoặc `zone` thành số đo tải/sức khỏe thời gian thực.

Các concern này có thể cần `RestClient`, `WebClient`, OpenFeign, retry/timeout, resilience và cơ chế authorization riêng.

## 4. Ma trận tiêu chí để quyết định có viết code riêng không

Trước khi viết custom class, đánh giá yêu cầu theo bảy trục:

| Tiêu chí | Nghiêng về cấu hình có sẵn | Nghiêng về component riêng |
|---|---|---|
| **Đúng semantics** | Preset có fallback, thứ tự ưu tiên đúng kỳ vọng | Phải fail-closed, fallback theo thứ tự hoặc có ngoại lệ |
| **Dữ liệu đầu vào** | Zone/hint/weight có trong metadata đã chuẩn hóa | Cần dữ liệu động như queue depth, EWMA latency, tenant policy |
| **Theo từng request** | Chính sách cố định theo service ID/zone hoặc hint đã hỗ trợ | Phải xem context đáng tin cậy, tenant, API version, quota |
| **Tính quyết định** | Round-robin/random/weight đủ yêu cầu | Cần lựa chọn dựa trạng thái đặc thù hoặc scoring |
| **Rủi ro vận hành** | Failure của preset có thể chấp nhận | Sai route có thể vi phạm chính sách hoặc tạo outage dây chuyền |
| **Khả năng đo và kiểm thử** | Có metrics/log sẵn và hành vi ổn định | Cần observability, unit/property/chaos tests mới |
| **Chi phí dài hạn** | Dùng API công khai, ít thay đổi khi nâng version | Phải bảo trì custom code và tương thích release train |

Một mẹo hữu ích: **đưa các điều kiện “không được phép” lên trước điều kiện tối ưu**. Nếu lựa chọn sai instance có thể gây lộ dữ liệu hoặc giao dịch không hợp lệ, ưu tiên correctness và fail-closed hơn hiệu năng.

### Câu hỏi loại trừ nhanh

- Chỉ cần thay đổi `timeout` hoặc retry? Đây **không phải** lý do mặc định để viết thuật toán LoadBalancer.
- Chỉ cần health filtering thông thường? Thử supplier sẵn có, nhưng hiểu fallback khi không còn healthy.
- Chỉ cần thay tỷ lệ phân phối theo metadata? Thử weighted supplier.
- Cần tránh một region bắt buộc? Soft zone preference có thể không đủ; cần filter chặt.
- Cần lựa chọn theo điểm số latency và tải cập nhật liên tục? Có thể cần custom selection algorithm **và pipeline thu thập metrics**; chỉ viết class chọn instance chưa đủ.

## 5. Cấp 1: property và cấu hình dựng sẵn

Một số cấu hình preset được Spring Cloud LoadBalancer cung cấp qua `spring.cloud.loadbalancer.configurations`. Ví dụ chọn weighted:

~~~yaml
spring:
  cloud:
    loadbalancer:
      configurations: weighted
~~~

Trong mô hình sử dụng metadata, instance có thể khai báo:

~~~yaml
spring:
  cloud:
    discovery:
      client:
        simple:
          instances:
            catalog-service:
              - uri: http://127.0.0.1:8081
                metadata:
                  weight: "5"
              - uri: http://127.0.0.1:8082
                metadata:
                  weight: "1"
~~~

`WeightedServiceInstanceListSupplier` mặc định tìm `weight` trong metadata và giả định weight 1 khi không được cung cấp. Tỷ lệ kết quả thực tế còn phụ thuộc thuật toán chọn, số request, concurrency, cache và các bộ lọc khác. **Không cam kết “đúng 5/6 request” tới instance đầu**.

Để thử zone preference, trong những phiên bản hỗ trợ preset:

~~~yaml
spring:
  cloud:
    loadbalancer:
      configurations: zone-preference
      zone: zone-a
~~~

Nếu `catalog-service` có các instance metadata `zone=zone-a` và `zone=zone-b`, supplier ưu tiên tập ở `zone-a` khi tập này không rỗng. **Khi không có instance ở `zone-a`, supplier trả lại toàn bộ tập nguồn** — đó là preference mềm.

Một số preset khác được tài liệu mô tả như `health-check` hoặc `same-instance-preference`. Với từng preset, hãy kiểm tra phiên bản và đừng gộp các giá trị của một thuộc tính đơn trị để mong nó tự ghép nhiều policy.

### Khi nào nên dừng ở Cấp 1?

Dừng ở preset khi:

1. Hành vi đúng bao gồm cả **trường hợp thiếu metadata hoặc không còn ứng viên**.
2. Không cần đọc tín hiệu đáng tin cậy riêng theo request.
3. Có thể kiểm chứng policy chỉ bằng test dữ liệu instance và request mẫu.
4. Metrics/observability đã đủ để thấy phân phối, lỗi và latencies.
5. Có thể rollback bằng thay đổi cấu hình mà không đổi code.

**Không chọn preset chỉ vì tên chính sách trông giống yêu cầu.** Hãy đọc cả điều kiện fallback và cách nó sử dụng metadata.

## 6. Cấp 2: ghép chuỗi supplier có sẵn theo từng service ID

Nếu cần discovery + cache + zone/hint, có thể tự khai báo **configuration class** chứa các supplier đã tồn tại, không cần viết thuật toán mới.

Ví dụ chỉ áp dụng zone preference cho `catalog-service`:

~~~java
import org.springframework.cloud.loadbalancer.annotation.LoadBalancerClient;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@LoadBalancerClient(
        name = "catalog-service",
        configuration = CatalogZoneLoadBalancerConfiguration.class)
class CatalogLoadBalancerRegistration {
}
~~~

Với **blocking discovery client** dùng RestClient/RestTemplate:

~~~java
import org.springframework.cloud.loadbalancer.core.ServiceInstanceListSupplier;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;

// Không gắn @Configuration ở đây nếu class ở phạm vi component scan chính.
// Nó được đưa vào child context qua @LoadBalancerClient.
class CatalogZoneLoadBalancerConfiguration {

    @Bean
    ServiceInstanceListSupplier catalogSupplier(
            ConfigurableApplicationContext context) {
        return ServiceInstanceListSupplier.builder()
                .withBlockingDiscoveryClient()
                .withCaching()
                .withZonePreference()
                .build(context);
    }
}
~~~

Sơ đồ chain:

~~~text
DiscoveryClient
    ↓
CachingServiceInstanceListSupplier
    ↓
ZonePreferenceServiceInstanceListSupplier
    ↓
RoundRobinLoadBalancer (chọn một ứng viên)
    ↓
HTTP client gọi instance đã chọn
~~~

**Cảnh báo về thứ tự:** cache nên nằm **ngay sau supplier lấy dữ liệu từ mạng**, trước các bước lọc theo request/zone. Nếu cache được đặt sau filter phụ thuộc từng request mà cache key chỉ phân biệt service ID, client có thể dùng nhầm danh sách đã lọc cho một request khác.

Với reactive discovery, builder có phương thức `withDiscoveryClient()` phù hợp nguồn reactive; tên API chính xác nên đối chiếu phiên bản và discovery client đang dùng. Với health-check supplier, nên xem xét bỏ cache wrapper vì nó có cơ chế giữ/replay kết quả riêng.

### Tại sao @LoadBalancerClient quan trọng?

Spring Cloud LoadBalancer tạo **child application context theo service ID**. `@LoadBalancerClient` gắn cấu hình riêng cho tên dịch vụ đó, tránh thay policy của tất cả client trong ứng dụng.

Nếu tình cờ để class dành cho child context được component scan chính đưa vào parent context như một `@Configuration` phổ thông, một bean policy có thể bị áp dụng **rộng hơn dự kiến**. Tài liệu khuyên class tham chiếu trong `@LoadBalancerClient(configuration=...)` **không dùng `@Configuration`** hoặc đặt ngoài phạm vi component scan chính.

Với nhiều service ID, có thể dùng `@LoadBalancerClients` và những configuration class tách riêng, thay vì một chính sách “global” thiếu kiểm soát.

## 7. Phân biệt soft fallback với hard fallback trước khi tái sử dụng supplier

Ba trường hợp sau rất dễ bị hiểu sai:

| Supplier dựng sẵn | Khi điều kiện match | Khi không có match | Phù hợp cho |
|---|---|---|---|
| `ZonePreferenceServiceInstanceListSupplier` | Ưu tiên instance cùng zone | Trả về toàn bộ danh sách nguồn | Giảm cross-zone traffic khi có thể |
| `HintBasedServiceInstanceListSupplier` | Ưu tiên instance có metadata `hint` khớp | Trả về toàn bộ danh sách nếu không match | Phân phối theo hint mềm |
| `HealthCheckServiceInstanceListSupplier` | Trả instance có health phù hợp | Mặc định trả lại các instance nguồn khi không có healthy | Cải thiện lựa chọn trong điều kiện không phải fail-closed |

Điều đó có nghĩa:

- “Ưu tiên same-zone” khác “cấm cross-zone”.
- “Ưu tiên instance ghi `hint=canary`” khác “chỉ canary được phép xử lý request”.
- “Ưu tiên healthy” khác “nếu mọi instance đều unhealthy thì phải từ chối ngay”.

Nếu đề bài là **data residency, isolate tenant, compliance, tách môi trường production/test** hoặc không bao giờ gọi endpoint đã bị policy cấm, **không dựa vào fallback mềm**.

### Không biến hint header thành cơ chế phân quyền

Một hint từ `X-SC-LB-Hint` hoặc request context có thể chịu ảnh hưởng của dữ liệu bên ngoài nếu không kiểm soát ở ingress. Không dùng một header do client tùy ý đặt để quyết định quyền truy cập dữ liệu, namespace nhạy cảm hoặc vùng được phép.

Ngay cả khi phía caller lọc đúng, backend vẫn phải thực thi authorization, ownership và policy residency tương ứng. Client-side routing không phải ranh giới bảo mật duy nhất.

## 8. Cấp 3: viết custom ServiceInstanceListSupplier khi cần lọc strict

Giả sử chính sách bắt buộc:

> “`payment-service` chỉ được chọn instance có metadata `region=region-a`. Khi không có bản sao hợp lệ, không được tự chuyển sang vùng khác.”

Đó là **lọc tập ứng viên**, chưa cần thay cách round-robin chọn trong tập đã lọc.

### Custom supplier strict, không tự fallback

Ví dụ Java:

~~~java
import java.util.List;
import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.loadbalancer.Request;
import org.springframework.cloud.loadbalancer.core.ServiceInstanceListSupplier;
import reactor.core.publisher.Flux;

final class RequiredRegionServiceInstanceListSupplier
        implements ServiceInstanceListSupplier {

    private final ServiceInstanceListSupplier delegate;
    private final String requiredRegion;

    RequiredRegionServiceInstanceListSupplier(
            ServiceInstanceListSupplier delegate,
            String requiredRegion) {
        this.delegate = delegate;
        this.requiredRegion = requiredRegion;
    }

    @Override
    public String getServiceId() {
        return delegate.getServiceId();
    }

    @Override
    public Flux<List<ServiceInstance>> get() {
        return delegate.get().map(this::filter);
    }

    @Override
    public Flux<List<ServiceInstance>> get(Request request) {
        return delegate.get(request).map(this::filter);
    }

    private List<ServiceInstance> filter(
            List<ServiceInstance> instances) {
        return instances.stream()
                .filter(instance ->
                        instance.getMetadata() != null
                        && requiredRegion.equals(
                                instance.getMetadata().get("region")))
                .toList();
    }
}
~~~

Mẫu này dùng đúng ý nghĩa **fail-closed**: nếu không có instance có metadata `region` phù hợp, kết quả là **danh sách rỗng**. Round-robin không có ứng viên để chọn; integration LoadBalancer/HTTP client sẽ báo lỗi “no available instance” tương ứng thay vì tự chuyển vùng.

### Đăng ký custom supplier trong child context

~~~java
import org.springframework.cloud.loadbalancer.core.ServiceInstanceListSupplier;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;

class PaymentRegionLoadBalancerConfiguration {

    @Bean
    ServiceInstanceListSupplier paymentSupplier(
            ConfigurableApplicationContext context) {

        ServiceInstanceListSupplier discoveryAndCache =
                ServiceInstanceListSupplier.builder()
                        .withBlockingDiscoveryClient()
                        .withCaching()
                        .build(context);

        return new RequiredRegionServiceInstanceListSupplier(
                discoveryAndCache,
                "region-a");
    }
}
~~~

Ứng dụng đăng ký cấu hình trên bằng một `@LoadBalancerClient(name="payment-service", configuration=PaymentRegionLoadBalancerConfiguration.class)` **thay cho** ví dụ zone của mục 6. Không khai báo cả hai class cấu hình như những policy cạnh tranh cho cùng service ID.

**Điểm cần kiểm soát khi production hóa:**

- `"region-a"` là giá trị ví dụ. Thực tế nên đọc từ cấu hình được kiểm soát, validate ngay khi startup.
- Metadata có thể bị thiếu/sai. Với strict policy, **thiếu metadata đồng nghĩa bị loại**, không đoán vùng từ hostname.
- Dữ liệu từ registry phải đáng tin cậy và có độ mới đủ dùng; không tin hoàn toàn metadata do workload thiếu kiểm soát tự quảng bá.
- Nếu một request có region bắt buộc khác nhau theo tenant, cần xác thực region ở boundary đáng tin cậy và truyền context vào `get(Request)`; không dùng chung một biến `requiredRegion` cho tất cả tenants.
- Không cache danh sách đã lọc theo tenant bằng cache key chỉ có service ID.
- Trường hợp rỗng phải đi đến **lỗi rõ ràng**, không dùng fallback tự bỏ điều kiện ở tầng khác.

Đây là **mẫu minh họa cấu trúc policy**; cần kiểm thử với dependency và version Spring Cloud cụ thể. Không chạy code ví dụ như chính sách bảo mật đã được kiểm toán.

## 9. Khi nào custom supplier chưa đủ?

Một supplier xử lý **tập ứng viên**, nhưng không nhất thiết quyết định chính xác **chọn một instance nào** trong tập đó.

Ví dụ:

- “Trong danh sách hợp lệ, chọn instance có **số request đang xử lý thấp nhất**.”
- “Chọn theo điểm số có kết hợp p95 latency, tỉ lệ lỗi và queue depth.”
- “Dùng rendezvous hashing bảo đảm affinity theo khóa khách hàng khi danh sách instance thay đổi.”
- “Điều chỉnh xác suất chọn theo chi phí egress và hiệu năng thời gian gần đây.”

Các yêu cầu này có thể cần **thuật toán selection mới**, chứ không chỉ filter/sort danh sách. Dù sort trước round-robin, round-robin vẫn có thể chia lượt trên tập được cung cấp, **không tự chọn luôn phần tử đầu**.

Phần riêng thường mở rộng `ReactorServiceInstanceLoadBalancer` hoặc `ReactiveLoadBalancer<ServiceInstance>` tương ứng, giữ nguyên lớp discovery và supplier nếu có thể.

### Thử dùng RandomLoadBalancer có sẵn trước khi viết thuật toán

Nếu mục tiêu chỉ là thay round-robin bằng random, Spring Cloud đã cung cấp `RandomLoadBalancer`. Có thể đổi bean **chọn instance** theo service:

~~~java
import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.loadbalancer.core.RandomLoadBalancer;
import org.springframework.cloud.loadbalancer.core.ReactorLoadBalancer;
import org.springframework.cloud.loadbalancer.core.ServiceInstanceListSupplier;
import org.springframework.cloud.loadbalancer.support.LoadBalancerClientFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.Environment;

class RandomCatalogLoadBalancerConfiguration {

    @Bean
    ReactorLoadBalancer<ServiceInstance> randomLoadBalancer(
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

Class này được tham chiếu thông qua `@LoadBalancerClient(configuration=RandomCatalogLoadBalancerConfiguration.class)` khi muốn áp dụng riêng cho `catalog-service`. Không cần viết lớp random selector mới.

**Đừng đồng thời đăng ký hai `ReactorLoadBalancer<ServiceInstance>` cạnh tranh** trong cùng child context nếu không có cấu hình rõ ràng; kiểm tra bean thực tế được sử dụng thay vì chỉ thấy ứng dụng startup thành công.

### Nếu thật sự viết thuật toán riêng

Cần xác định:

1. **Input:** danh sách ứng viên có thể thay đổi, `Request` context nào đáng tin cậy.
2. **State:** counters/latency được đo ở đâu, chia sẻ giữa threads/client instances ra sao.
3. **Selection:** công thức, giới hạn, tie-breaking, random seed và fairness.
4. **Empty list:** trả `EmptyResponse`/không có ứng viên, không chọn `null`.
5. **Concurrency:** không chặn event loop, không giữ lock dài, xử lý snapshot nhất quán.
6. **Lỗi telemetry:** khi metrics cũ hoặc mất, fallback như thế nào mà **không vi phạm policy cứng**.
7. **TTL/refresh:** tránh chọn dựa trên instance đã bị loại từ discovery.
8. **Observability:** biết vì sao instance được chọn mà không log PII/hint nhạy cảm.

Một thuật toán “least latency” nếu dùng phản hồi cuối cùng mà không có chống nhiễu/smoothing có thể khiến mọi client cùng đổ về một instance đang nhanh, rồi làm nó quá tải. Custom selection tạo ra những tình huống vận hành mới cần chaos/load test.

## 10. Chọn chính sách theo service, tránh áp dụng nhầm toàn cục

Giả sử ứng dụng gọi ba service:

| Service ID | Hợp đồng định tuyến | Giải pháp khả thi |
|---|---|---|
| `catalog-service` | Ưu tiên cùng zone nhưng cross-zone được phép | Zone preference có sẵn |
| `recommendation-service` | Chia tải theo trọng số instance do vận hành quản lý | Weighted supplier |
| `payment-service` | Không được chuyển qua region khác | Strict region supplier riêng |
| `analytics-service` | Muốn test thuật toán least-loaded có kiểm soát | Custom selector thí nghiệm, feature flag |

**Không áp dụng policy của `payment-service` cho `catalog-service`** chỉ vì cả hai cùng dùng RestClient.

Spring Cloud LoadBalancer tạo child context theo service ID. Dùng `@LoadBalancerClients` để tách cấu hình hoặc cơ chế client-scoped properties khi phiên bản hỗ trợ.

### Những thứ nên đặt ở cấp chung

- Quy định timeout của HTTP transport theo SLO.
- Mã lỗi, tracing, correlation và logging an toàn.
- Quy tắc bảo mật cho request context.
- Hạ tầng metrics và kiểm thử.
- Default policy an toàn cho những service không có cấu hình riêng.

### Những thứ nên định nghĩa theo service ID

- Zone/region policy và đặc biệt **fallback semantics**.
- Weight source và yêu cầu metadata bắt buộc.
- Hint, affinity hoặc routing theo API version.
- Các rule đặc thù: canary allowlist, tenant placement, subset.
- Điều kiện bật/rollback custom selector.

Nếu dùng property `spring.cloud.loadbalancer.configurations` ở cấp chung, hãy xác định chính xác phạm vi áp dụng của nó trong version hiện tại. Đối với trường hợp chỉ một service cần khác, `@LoadBalancerClient` thường dễ kiểm soát hơn.

## 11. Tác động của discovery, cache, health check và retry

Một policy có thể đúng nhưng vẫn chọn endpoint hỏng nếu **đầu vào là danh sách instance stale**.

~~~mermaid
flowchart TD
    A["Service registry / discovery"]
    B["Cache instance list nếu dùng"]
    C["Health check nếu cần"]
    D["Zone/region/hint filtering"]
    E["RoundRobin/Random/custom selector"]
    F["HTTP transport thực thi"]
    G["Timeout / retry policy"]
    A --> B --> C --> D --> E --> F --> G
~~~

Lưu ý:

- `CachingServiceInstanceListSupplier` nên đặt ngay sau supplier lấy instance qua mạng, trước các bộ lọc phụ thuộc request.
- Nếu discovery client như Eureka đã cache, thêm LoadBalancer cache có thể dẫn tới **double caching**.
- `HealthCheckServiceInstanceListSupplier` có replay/caching riêng; tài liệu gợi ý cân nhắc **không dùng thêm `CachingServiceInstanceListSupplier`** chung với nó.
- Khi mọi health checks đều thất bại, health-check supplier dựng sẵn **có thể fallback về toàn danh sách nguồn**, không phải fail-closed.
- Retry có thể chọn lại cùng hoặc instance khác, tùy integration/cấu hình; retry không chứng minh instance đã khỏe hoặc body request có thể phát lại.
- HTTP connect/response timeout thuộc transport; chúng không tự thay đổi danh sách `ServiceInstance`.

**Một policy nghiêm ngặt không được vô hiệu hóa bởi tầng fallback phía sau.** Hãy kiểm tra toàn bộ chuỗi selection tới HTTP, kể cả retry, proxy và các cách gọi trực tiếp bỏ qua LoadBalancer.

## 12. Đặt tiêu chí kiểm thử trước khi triển khai custom

Cấu hình có sẵn cũng cần test, nhưng **component tự viết** nên có nhiều lớp kiểm thử:

| Loại kiểm thử | Điều cần chứng minh | Ví dụ |
|---|---|---|
| Unit test supplier/filter | Tập ứng viên ra đúng theo metadata | Region khác bị loại, thiếu region bị loại |
| Kiểm thử empty/fail-closed | Không có ứng viên thì không chuyển qua nơi bị cấm | 0 instance region-a, còn 2 region-b → kết quả rỗng |
| Unit test thuật toán | Không chọn ngoài danh sách, xử lý tie/empty | Selection chỉ trả ứng viên hợp lệ |
| Test phân phối | Tỷ lệ thực tế dưới load và concurrency | Weighted 5:1 có xu hướng phân phối phù hợp |
| Test chain order | Cache ở đúng vị trí, request context không bị mất | Tenant A/B không dùng nhầm filtered list |
| Integration test | `@LoadBalanced RestClient`/WebClient/Feign gọi đúng instance | Backend `/whoami` cho ID rõ ràng |
| Fault injection | Instance mất mạng, registry stale, health probe lỗi | Không crash, policy cứng vẫn giữ |
| Soak/performance | CPU, memory, p95/p99, backlog, metrics cardinality | Chi phí custom selector nằm trong budget |
| Rollback test | Có thể quay về policy trước mà không thay đổi backend | Feature flag/config canary hoạt động |

### Bộ tình huống tối thiểu cho strict-region policy

| Danh sách nguồn | Required region | Danh sách sau filter | Kết quả mong đợi |
|---|---|---|---|
| A1(region-a), A2(region-a), B1(region-b) | region-a | A1, A2 | Chỉ chọn A1/A2 |
| B1(region-b), B2(region-b) | region-a | **Rỗng** | Không có server hợp lệ; không gọi B1/B2 |
| A1(region-a), X(thiếu metadata) | region-a | A1 | X bị loại |
| A1(region-a), A2(region-a) | region-b | **Rỗng** | Không chọn A1/A2 |
| Danh sách rỗng | region-a | **Rỗng** | Không ném NPE; không chọn tùy tiện |
| A1(region-a) nhưng A1 đã chết | region-a | A1 | Có thể lỗi kết nối; cần health/discovery/timeout riêng |

**Đặc biệt:** kết quả cuối của case B phải là **không gửi request tới backend bị cấm**. Một HTTP 503/no-server có thể là hành vi đúng. Không cố “sửa 503” bằng cách mở fallback cross-region khi chính sách cấm.

## 13. Bài thực hành: bắt đầu bằng built-in rồi nâng cấp có chủ đích

### Bước 1 — Tạo hai vùng và quan sát selection

Dùng `SimpleDiscoveryClient` cho bài thử local:

~~~yaml
spring:
  cloud:
    discovery:
      client:
        simple:
          instances:
            catalog-service:
              - uri: http://127.0.0.1:8081
                metadata:
                  zone: zone-a
                  region: region-a
                  weight: "3"
              - uri: http://127.0.0.1:8082
                metadata:
                  zone: zone-b
                  region: region-b
                  weight: "1"
~~~

Hai backend cần endpoint `GET /whoami` trả instance ID để kiểm chứng đích. `127.0.0.1` chỉ hợp lệ nếu caller và backend cùng máy/network namespace; Docker/Kubernetes cần URI khác.

### Bước 2 — Bật zone preference có sẵn

Đặt `spring.cloud.loadbalancer.zone=zone-a` và chọn preset `zone-preference`, hoặc dùng configuration builder ở mục 6.

Đo:

- Khi có instance zone-a, client ưu tiên instance đó.
- Khi chỉ còn zone-b trong **danh sách discovery đã cập nhật**, supplier dựng sẵn có thể fallback sang zone-b.
- Trong `SimpleDiscoveryClient` tĩnh, dừng port 8081 **không tự xóa URI**. Muốn thử danh sách mới, cập nhật dữ liệu/tái khởi động trong lab hoặc dùng supplier/registry động.

### Bước 3 — Chuyển yêu cầu thành strict region

Giả sử nghiệp vụ đổi yêu cầu: phải chọn `region-a` hoặc trả lỗi. Thay cấu hình child context bằng `RequiredRegionServiceInstanceListSupplier` ở mục 8.

Kiểm tra rằng:

- Không tồn tại đường fallback sang `region-b`.
- Không có metadata `region` thì instance bị loại.
- Khi region-a hết ứng viên, các loại HTTP client hiển thị lỗi **không có instance** thay vì lén chọn region-b.
- Retry không tự chuyển sang instance bị cấm.

### Bước 4 — Ghi nhận chi phí và xác định có cần custom selector không

Nếu chỉ filter strict, **đừng vội viết least-connections**. Thu thập metrics:

~~~text
serviceId=catalog-service
policy=strict-region
candidateCountBefore=2
candidateCountAfter=1
selectionOutcome=selected
httpOutcome=200
durationMs=42
~~~

Đây là định dạng log minh họa. Không log header token, cookies, user ID hoặc raw URI. Nếu sau lọc vẫn cần phân phối tốt hơn, đánh giá weighted/random/round-robin trước khi tính đến selector hoàn toàn mới.

## 14. Các anti-pattern thường gặp

**1. Viết thuật toán từ đầu chỉ vì muốn “load balancing thông minh”.** Nếu nhu cầu đã được `WeightedServiceInstanceListSupplier` hoặc `ZonePreferenceServiceInstanceListSupplier` đáp ứng, tự viết làm tăng test surface mà không tạo giá trị tương xứng.

**2. Dùng zone preference như ranh giới bảo mật.** Nó fallback về tất cả instance khi zone không có match. Một chính sách cấm chuyển vùng phải fail-closed và được backend kiểm chứng.

**3. Đặt filter theo tenant trước cache dùng chung một key.** Cache có thể giữ danh sách đã lọc cho tenant A rồi trả cho tenant B. Chỉ cache dữ liệu chung; áp dụng filter request-context ở tầng phù hợp.

**4. Kết hợp `CachingServiceInstanceListSupplier` và `HealthCheckServiceInstanceListSupplier` không hiểu vòng đời.** Có thể tạo dữ liệu stale/double caching, khiến instance chết còn được chọn.

**5. Sort danh sách rồi tưởng round-robin chỉ chọn item đầu.** Nếu muốn min-latency/least-requests thật, thuật toán selection phải sử dụng điểm số/counter; sort đơn thuần thường chưa đủ.

**6. Chọn instance từ dữ liệu metadata không tin cậy.** Một instance giả có thể tự khai báo `region=trusted` hoặc `weight=1000` nếu registry không kiểm soát metadata. Phải bảo vệ nguồn thông tin và xác thực ở server.

**7. Viết custom selector bằng I/O blocking trong `choose()`.** Cứ mỗi request truy vấn dashboard/DB/Redis để lấy score có thể biến LoadBalancer thành nút nghẽn. Ưu tiên snapshot dữ liệu được cập nhật độc lập, nonblocking nếu ở reactive path và fallback có giới hạn.

**8. Bật retry mù quáng khi custom policy không còn ứng viên.** Nếu policy strict thì không có ứng viên là kết quả có chủ đích; retry không nên chuyển sang tập bị cấm hay tạo vòng lặp vô hạn.

**9. Áp dụng cấu hình child-context ra toàn ứng dụng.** Một `@Configuration` đặt sai vị trí scan có thể thay bean của nhiều service ngoài phạm vi dự tính.

**10. Không kiểm tra request-context propagation.** Nếu filter cần hint/header/tenant context nhưng adapter không chuyển được `Request` như kỳ vọng, policy có thể chọn sai hoặc hoạt động không ổn định. Kiểm tra integration thực tế với RestClient, WebClient và Feign.

**11. Quên rollback.** Nếu release custom selector làm error rate tăng, phải có phương án quay về cấu hình dựng sẵn sau khi xác minh không vi phạm các hard constraint.

## 15. Cân nhắc hiệu năng và độ ổn định của giải pháp tùy biến

Một custom LoadBalancer nằm trên đường xử lý của nhiều request; mỗi thay đổi có thể ảnh hưởng latency và tính ổn định toàn hệ thống.

### Độ phức tạp tính toán

- Lọc danh sách n instance thường là `O(n)`; với hàng chục instance thường không phải vấn đề lớn, nhưng vẫn cần đo.
- Scoring n instance mỗi request có thể tạo nhiều allocation, metrics reads và contention.
- Thuật toán cần state per-instance có thể chịu gánh nặng garbage collection và đồng bộ khi membership thay đổi.
- Tối ưu theo latency mà bỏ qua độ ổn định và confidence của số đo có thể gây oscillation/hotspot.

### Độ mới dữ liệu

- Service registry có chu kỳ heartbeat/refresh.
- LoadBalancer cache có TTL; discovery có thể có cache riêng.
- Health check chỉ kiểm tra theo khoảng thời gian, không dự đoán request tiếp theo chắc chắn thành công.
- Per-instance load/latency measurements có độ trễ, bias và có thể thiếu dữ liệu khi traffic thấp.

### Theo dõi thay đổi

Theo dõi trước/sau theo **service ID và policy version**:

| Chỉ số | Ý nghĩa |
|---|---|
| Lựa chọn instance / số ứng viên | Policy đang lọc quá mạnh hay không |
| No-instance count | Có fail-closed/thiếu instance thường xuyên không |
| Cross-zone traffic | Soft locality có hiệu quả không |
| HTTP error/timeout rate | Có cải thiện lỗi thật hay chỉ dời lỗi |
| Retry attempts | Retry có khuếch đại tải |
| p50/p95/p99 latency | Tác động end-to-end |
| CPU/memory của caller | Chi phí custom selection |
| Per-instance concurrency | Có hotspot/fairness issue không |
| Cache refresh/age | Dữ liệu route có stale không |
| Policy rejected count | Rule strict đang ngăn bao nhiêu request |

Không log dữ liệu nhạy cảm để “giải thích thuật toán”; dùng mã chính sách và lý do dạng enum như `NO_ALLOWED_REGION`, `EMPTY_DISCOVERY` hoặc `UNHEALTHY_CANDIDATES`.

## 16. Khi nào nâng cấp từ một cấp lên cấp khác?

| Tình huống phát hiện | Lựa chọn đầu tiên | Khi nào nâng cấp |
|---|---|---|
| Round-robin cho nhiều instance có năng lực tương đương | Giữ mặc định | Chỉ khi số liệu cho thấy phân phối không phù hợp |
| Phân phối 80/20 hoặc canary traffic đơn giản | Weighted supplier/metadata | Khi cần rule theo request hoặc độ ưu tiên phức tạp |
| Ưu tiên vùng để giảm latency | Zone preference | Khi fallback mềm không đáp ứng hợp đồng |
| Chỉ được chọn instance có nhãn bắt buộc | Custom filter supplier strict | Khi sau lọc vẫn cần selector riêng |
| Chọn theo tenant đáng tin cậy | Request-aware supplier nếu đủ | Khi cần hashing/affinity trạng thái phức tạp |
| Chọn theo latency/active requests | Đo trước, thử built-in weight theo dữ liệu đã chuẩn hóa | Khi cần thuật toán selection động với test/metrics |
| Không có instance khỏe | Xem health-check và no-instance semantics | Nếu cần fail-closed mà default fallback all |
| Backends có timeout cao | Tối ưu timeout, pool, retry, circuit breaker | Không thay selector nếu nút nghẽn ở transport |
| Registry stale | Kiểm tra refresh/cache/discovery | Không viết selector mới chỉ để che dữ liệu nguồn cũ |

Sự hiện diện của một requirement “nâng cao” không tự biện minh cho custom code. Hãy yêu cầu **bằng chứng rằng lựa chọn sẵn có không đủ** và định nghĩa những test mà code riêng bắt buộc phải vượt qua.

## 17. Checklist ra quyết định và tiêu chí nghiệm thu

Trước khi viết hoặc phê duyệt thành phần riêng, trả lời được:

1. **Mục tiêu** là tối ưu latency/chi phí hay ràng buộc an toàn không được phép vi phạm?
2. Đã đặc tả đúng hành vi khi **không có instance phù hợp**?
3. Preset `weighted`, `zone-preference`, `health-check`, `same-instance-preference` hoặc hint đáp ứng được bao nhiêu phần trăm yêu cầu?
4. Có thể dùng `ServiceInstanceListSupplier.builder()` ghép các thành phần dựng sẵn thay vì viết mới?
5. Nếu chưa đủ, vấn đề là **lọc tập ứng viên** hay **chọn instance trong tập ứng viên**?
6. Metadata như zone, region, weight, tenant hint lấy từ đâu và có **đáng tin cậy** không?
7. Chính sách có phụ thuộc từng request không? Nếu có, request context có được truyền đúng, cache có bị lẫn giữa callers?
8. Có kế hoạch fail-closed, empty response, retry, timeout và circuit breaker?
9. Có unit/integration/chaos/load tests chứng minh tính đúng đắn, fairness và performance?
10. Tác động có được giới hạn theo một service ID/child context thay vì toàn ứng dụng?
11. Có dashboard/log events không nhạy cảm để giải thích selection, rejection và lỗi?
12. Có thể rollback hoặc tắt custom behavior khi phát hiện regression mà không vi phạm hard constraint?

**Kết luận:** Trong Spring Cloud LoadBalancer, nên đi theo lộ trình **property/preset → ghép supplier có sẵn → custom supplier lọc danh sách → custom thuật toán chọn instance**, chỉ tăng cấp khi yêu cầu thực sự đòi hỏi. Sự khác nhau quan trọng nhất không phải “có code hay không”, mà là **hợp đồng khi không có ứng viên**, độ tin cậy của dữ liệu đầu vào, ranh giới service ID, khả năng kiểm thử và chi phí vận hành dài hạn. Lựa chọn ít tùy biến nhất mà vẫn **đúng chính sách, an toàn và đo được** thường là lựa chọn bền vững nhất.

**Tài liệu tham khảo chính thức:**

- [Spring Cloud Commons – Spring Cloud LoadBalancer](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html)
- [Spring Cloud Commons – Configuration Properties](https://docs.spring.io/spring-cloud-commons/reference/configprops.html)
- [Spring Cloud Commons – LoadBalancer Client Configuration](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html#passing-your-own-spring-cloud-loadbalancer-configuration)

