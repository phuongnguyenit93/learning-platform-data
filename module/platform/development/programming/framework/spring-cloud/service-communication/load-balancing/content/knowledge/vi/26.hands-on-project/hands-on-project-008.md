# Quan sát cache cũ và độ trễ phát hiện thay đổi

Trong hệ thống microservices, một instance có thể đã bị xóa khỏi service registry hoặc một bản sao mới đã được đăng ký, nhưng **caller vẫn tiếp tục chọn tập instance cũ trong một khoảng thời gian**. Nguyên nhân có thể nằm ở cache của discovery, `CachingServiceInstanceListSupplier`, chu kỳ health check hoặc tốc độ đồng bộ control plane. Hiện tượng này gọi là **stale instance list** — danh sách ứng viên tại client chưa phản ánh trạng thái mới của nguồn.

Bài thuộc chương **Thực hành tổng hợp** của module **SPRING_CLOUD_SERVICE_COMMUNICATION_LOAD_BALANCING**. Ta sẽ xây dựng một lab chạy thực tế để **thay đổi topology khi caller vẫn đang chạy**, quan sát bằng RestClient `@LoadBalanced`, đo từ lúc nguồn đổi đến lúc LoadBalancer nhìn thấy danh sách mới, và phân biệt lỗi **cache cũ**, **instance chết**, **connection pool** và **retry/timeout**. Các kết luận cũng áp dụng cho WebClient và OpenFeign khi cùng dùng Spring Cloud LoadBalancer.

> **Mục tiêu thực nghiệm:** thay vì chỉ nói “TTL là 6 giây”, hãy đo được **nguồn đã đổi từ A+B sang A** nhưng **cache vẫn hiển thị A+B**, ghi lại mốc thời gian source-change/cache-refresh và giải thích vì sao độ trễ quan sát không nhất thiết bằng chính xác TTL.

## 1. Năng lực đạt được sau bài thực hành

Hoàn thành lab, bạn cần chứng minh được:

1. **Nguồn danh sách instance** và **cache LoadBalancer** là hai lớp trạng thái độc lập.
2. Khi nguồn loại bản sao B, **cache cũ có thể còn giữ B** tới khi mục cache hết hạn hoặc bị invalidate.
3. **TTL tính từ lần ghi cache**, không tính từ lúc một instance thay đổi trạng thái.
4. **Cache expiration** và **quan sát thấy danh sách mới** là hai thời điểm khác nhau; việc đọc sau khi hết hạn mới tạo cơ hội refresh.
5. Có thể đo **detection delay** với timestamp, revision và số lần đọc nguồn thay vì suy đoán từ một request đơn lẻ.
6. Trong hệ thống thật, **discovery propagation, LB cache, health check, retry và network transport** có thể tạo những độ trễ/hành vi khác nhau.
7. Có thể tạo ma trận kiểm thử bảo đảm **instance bị loại không còn được chọn sau khi trạng thái đã hội tụ**, nhưng không gắn một thời gian chính xác chưa đo cho mọi hệ thống.

### Sản phẩm đầu ra dự kiến

| Thành phần | Vai trò |
|---|---|
| `catalog-backend` chạy hai bản | Trả định danh bản sao A/B |
| `caller-service` | Gọi logic `http://catalog-service` |
| `TopologyState` | Nguồn `ServiceInstance` thay đổi được ngay khi chạy |
| `MutableTopologySupplier` | Trả snapshot nguồn và tăng bộ đếm source reads |
| `CachingServiceInstanceListSupplier` | Giữ danh sách ứng viên trong thời gian TTL |
| `/__lab/source` | Xem nguồn hiện tại (không đọc cache) |
| `/__lab/candidates` | Xem danh sách LoadBalancer đang thấy (có thể làm cache refresh) |
| `/__lab/mode` | Đổi nguồn giữa BOTH, A_ONLY, B_ONLY, NONE |
| `/demo/whoami` | Gọi HTTP thực tới instance được chọn |

Đây là **lab nội bộ trên localhost**. Các endpoint `/__lab/*` cho phép thay đổi định tuyến và quan sát topology; **không được đưa ra production công khai**.

## 2. Ba đồng hồ khác nhau của sự thay đổi

Giả sử tại thời điểm `t0` caller đã cache `[A, B]`. Tại `t1` control plane chỉ còn công bố `[A]`. Cần phân biệt:

- **Source update time:** `t_source` — nguồn thực sự đổi.
- **Cache eligibility time:** `t_expire` — mục cache có thể bị xem là hết hạn theo TTL.
- **Observed convergence time:** `t_detect` — lần quan sát đầu tiên nhìn thấy snapshot mới sau refresh.

~~~mermaid
sequenceDiagram
    participant T as TopologyState
    participant S as MutableTopologySupplier
    participant C as LB cache (TTL=6s)
    participant LB as LoadBalancer
    participant A as catalog-a
    participant B as catalog-b

    LB->>C: Chọn instance (t0)
    C->>S: Cache miss, lấy snapshot
    S->>T: Đọc nguồn [A, B]
    T-->>S: revision=1, [A, B]
    S-->>C: [A, B]
    C-->>LB: [A, B]
    Note over C: Ghi cache, bắt đầu đếm TTL
    T->>T: t1: đổi nguồn thành [A], revision=2
    LB->>C: Request mới trước khi cache hết hạn
    C-->>LB: [A, B] cũ
    LB->>B: Có thể chọn B dù nguồn đã bỏ B
    Note over C: t_expire: TTL hết hạn
    LB->>C: Request/đọc snapshot sau t_expire
    C->>S: Cache miss, tải nguồn mới
    S->>T: Đọc nguồn [A]
    S-->>C: [A]
    C-->>LB: [A]
    LB->>A: Chọn A
    Note over LB: t_detect: lần quan sát thấy [A]
~~~

Với một cache TTL 6 giây, nếu nguồn đổi sau khi cache đã tồn tại 1 giây, stale window còn lại có thể **khoảng 5 giây** — nhưng phép đo thực bị ảnh hưởng bởi thời điểm poll, scheduling, các lớp cache khác và thời gian request. Không coi 6 giây là cam kết độ trễ cố định.

**Công thức quan sát cho lab:**

~~~text
detectionDelayMs = firstObservedNewCandidateListAtMs
                   - sourceChangedAtMs

staleWindowMs     = max(0, cacheExpireAtMs - sourceChangedAtMs)

measurementError  ≈ pollInterval + scheduling/network overhead
~~~

Đây là cách diễn giải quan hệ thời gian, không phải bảo đảm cứng của Spring Cloud. `t_expire` được tính từ thời điểm cache **ghi giá trị**, không phải từ `t_source`. Nếu không có request sau hết hạn, **không có lý do chắc chắn để kỳ vọng một lần refresh xảy ra ngay lập tức**.

## 3. Cache instance khác cache response và connection pool

| Cơ chế | Dữ liệu được giữ | Thay đổi instance có ảnh hưởng gì? |
|---|---|---|
| Registry/discovery state | Instance được đăng ký và metadata | Là nguồn thay đổi ban đầu |
| Discovery client's local cache | Snapshot/đăng ký được discovery adapter giữ | Có thể kéo dài thời gian nguồn mới tới caller |
| `CachingServiceInstanceListSupplier` | `List<ServiceInstance>` cho service ID | Có thể tiếp tục cho phép chọn instance đã bị loại |
| HTTP connection pool | Socket/HTTP connections tới host:port đã chọn | Không tự quyết định danh sách ứng viên |
| Response cache ứng dụng | DTO/response của API | Có thể bỏ hẳn remote call, không liên quan danh sách |
| Health-check supplier | Kết quả probe và tập instance được coi healthy | Có chu kỳ cập nhật riêng; không xác thực danh tính |

**Tắt HTTP keep-alive không làm LoadBalancer cache mới hơn.** Xóa instance khỏi registry cũng không đồng nghĩa đóng ngay mọi socket đang tồn tại. Health check phát hiện backend chết không giống phát hiện record đã bị xóa khỏi nguồn.

Trong lab cơ sở, để chỉ đo một cơ chế, ta **không bật health-check supplier**, **không bật retry** và **không có discovery/registry ngoài**. Chỉ có `TopologyState → MutableTopologySupplier → CachingServiceInstanceListSupplier → LoadBalancer`.

## 4. Sơ đồ kiến trúc và địa chỉ thử nghiệm

~~~mermaid
flowchart LR
    P["POST /__lab/mode"] --> S["TopologyState: [A,B] hoặc [A]"]
    S --> D["MutableTopologySupplier (sourceReads++)"]
    D --> C["CachingServiceInstanceListSupplier: TTL"]
    C --> LB["RoundRobinLoadBalancer"]
    Q["GET /demo/whoami"] --> RC["RestClient @LoadBalanced"]
    RC --> LB
    LB --> A["catalog-a:18081"]
    LB --> B["catalog-b:18082"]
    O["GET /__lab/source"] --> S
    I["GET /__lab/candidates"] --> C
~~~

| Ứng dụng | Port | Endpoint |
|---|---:|---|
| Backend A | 18081 | `GET /api/whoami` |
| Backend B | 18082 | `GET /api/whoami` |
| Caller | 18090 | `GET /demo/whoami` |
| Caller control plane lab | 18090 | `GET /__lab/source`, `POST /__lab/mode` |
| Caller cache debug | 18090 | `GET /__lab/candidates` |

Trong lab, việc thay `TopologyState` mô phỏng registry thay đổi **đồng bộ và ngay lập tức**. Vì thế độ trễ quan sát chủ yếu đến từ LB cache. Khi thay bằng Eureka/Kubernetes/Consul, cần cộng thêm những cơ chế refresh/propagation thực tế nhưng **không được giả định chúng cộng tuyến tính đơn giản ở mọi trường hợp**.

## 5. Chuẩn bị môi trường

Giả sử có hai project Spring Boot riêng `catalog-backend` và `caller-service`, dùng Java 17+, Spring Boot/Spring Cloud BOM **tương thích theo release train**. Các ví dụ Java ở đây dùng syntax record, switch expression, `RestClient` của Spring Framework 6.1+ và API Spring Cloud LoadBalancer tương ứng.

**Backend – Gradle:**

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
~~~

**Caller – Gradle:**

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.cloud:spring-cloud-starter-loadbalancer'

    // Để dùng Caffeine-backed LoadBalancer cache trong lab.
    implementation 'com.github.ben-manes.caffeine:caffeine'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

`spring-cloud-starter-loadbalancer` cung cấp Spring Cloud LoadBalancer; Caffeine trên classpath cho phép dùng cache implementation tương ứng. Ví dụ cấu hình TTL của bài này dùng property **`spring.cloud.loadbalancer.cache.ttl`**, không đặt `spring.cloud.loadbalancer.cache.caffeine.spec` để tránh việc custom spec ghi đè các cấu hình chung.

**Không tạo phiên bản cố định của Spring Cloud bằng cách đoán**; dự án cần import Spring Cloud BOM khớp Spring Boot đang dùng.

## 6. Backend A/B: endpoint trả instance ID

Trong project backend, tạo `lab.backend.BackendApplication`:

~~~java
package lab.backend;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BackendApplication {

    public static void main(String[] args) {
        SpringApplication.run(BackendApplication.class, args);
    }
}
~~~

Tạo `lab.backend.InstanceController`:

~~~java
package lab.backend;

import java.util.Map;

import org.springframework.core.env.Environment;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class InstanceController {

    private final String instanceId;

    InstanceController(Environment environment) {
        this.instanceId = environment.getProperty(
            "instance.id", "unknown");
    }

    @GetMapping("/api/whoami")
    Map<String, Object> whoami() {
        return Map.of(
            "instanceId", instanceId,
            "serverTimeMs", System.currentTimeMillis()
        );
    }
}
~~~

Sau khi build backend thành `catalog-backend.jar` theo cách dự án đang sử dụng, chạy ở **hai terminal riêng**:

~~~bash
java -jar catalog-backend.jar --server.port=18081 --instance.id=catalog-a
java -jar catalog-backend.jar --server.port=18082 --instance.id=catalog-b
~~~

Kiểm tra trực tiếp:

~~~bash
curl -s http://127.0.0.1:18081/api/whoami
curl -s http://127.0.0.1:18082/api/whoami
~~~

Kỳ vọng thấy lần lượt `catalog-a` và `catalog-b`. Đừng vội dừng một backend ở bước này; thí nghiệm **thay đổi danh sách nguồn** cần quan sát cache cũ trong khi cả hai backend vẫn hoạt động, để tránh nhầm lẫn với connect refused.

## 7. Caller: lưu snapshot topology có thể thay đổi tại runtime

Trong project caller, tạo class `lab.caller.TopologyState`. Nguồn ban đầu là `[A, B]`, có revision tăng khi đổi mode và bộ đếm `sourceReads` để ghi nhận supplier thật sự lấy snapshot mới.

~~~java
package lab.caller;

import java.util.List;
import java.util.concurrent.atomic.AtomicLong;
import java.util.concurrent.atomic.AtomicReference;

import org.springframework.cloud.client.DefaultServiceInstance;
import org.springframework.cloud.client.ServiceInstance;
import org.springframework.stereotype.Component;

@Component
public final class TopologyState {

    public enum Mode { BOTH, A_ONLY, B_ONLY, NONE }

    public record Snapshot(
        long revision,
        Mode mode,
        long changedAtMs,
        List<ServiceInstance> instances
    ) {}

    private static final String SERVICE_ID = "catalog-service";

    private final AtomicReference<Snapshot> current =
        new AtomicReference<>(new Snapshot(
            1,
            Mode.BOTH,
            System.currentTimeMillis(),
            instancesFor(Mode.BOTH)
        ));

    private final AtomicLong sourceReads = new AtomicLong();

    public Snapshot current() {
        return current.get();
    }

    // Chỉ supplier gọi phương thức này; tăng counter khi đọc nguồn.
    public Snapshot readForSupplier() {
        sourceReads.incrementAndGet();
        return current.get();
    }

    public long sourceReadCount() {
        return sourceReads.get();
    }

    public synchronized Snapshot switchTo(Mode mode) {
        Snapshot previous = current.get();

        Snapshot next = new Snapshot(
            previous.revision() + 1,
            mode,
            System.currentTimeMillis(),
            instancesFor(mode)
        );

        current.set(next);
        return next;
    }

    private static List<ServiceInstance> instancesFor(Mode mode) {
        ServiceInstance a = new DefaultServiceInstance(
            "catalog-a", SERVICE_ID, "127.0.0.1", 18081, false
        );

        ServiceInstance b = new DefaultServiceInstance(
            "catalog-b", SERVICE_ID, "127.0.0.1", 18082, false
        );

        return switch (mode) {
            case BOTH -> List.of(a, b);
            case A_ONLY -> List.of(a);
            case B_ONLY -> List.of(b);
            case NONE -> List.of();
        };
    }
}
~~~

Điểm thiết kế:

- `AtomicReference<Snapshot>` giúp một lượt đọc nhận cùng revision, mode, timestamp và danh sách.
- `List.of(...)` khiến collection không thể bị thêm/bớt tùy tiện sau khi snapshot được công bố.
- `current()` là **quan sát nguồn không tăng counter**.
- `readForSupplier()` tăng `sourceReads`; cache hit thường **không** gọi method này.
- `changedAtMs` dùng wall clock để hiển thị thời điểm; khi đo duration nội bộ rất chính xác nên dùng monotonic clock (`System.nanoTime()`) thay vì trừ đồng hồ hai máy.
- Nếu đổi A_ONLY rồi lại BOTH, revision thay đổi ngay cả khi danh sách trở lại như cũ.

`DefaultServiceInstance` là dữ liệu mẫu. Lab không kết nối một discovery server thật. Vì thế không được dùng kết quả đo làm bằng chứng độ trễ đồng bộ của Eureka/Consul/Kubernetes trong production.

## 8. Custom source supplier: mỗi lần đọc lấy snapshot hiện tại

Đặt `lab.caller.MutableTopologySupplier` cạnh `TopologyState`:

~~~java
package lab.caller;

import java.util.List;

import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.loadbalancer.core.ServiceInstanceListSupplier;

import reactor.core.publisher.Flux;

public final class MutableTopologySupplier
        implements ServiceInstanceListSupplier {

    private final TopologyState state;

    public MutableTopologySupplier(TopologyState state) {
        this.state = state;
    }

    @Override
    public String getServiceId() {
        return "catalog-service";
    }

    @Override
    public Flux<List<ServiceInstance>> get() {
        return Flux.defer(() ->
            Flux.just(state.readForSupplier().instances())
        );
    }
}
~~~

Ở đây `Flux.defer(...)` bảo đảm khi có subscription mới, supplier mới truy cập snapshot hiện tại. Nếu bỏ cache, sau khi đổi mode, các lần gọi supplier mới sẽ thấy danh sách mới ngay ở lần đọc tiếp theo.

**Không trả `Flux.empty()` khi mode NONE.** Danh sách rỗng hợp lệ là `Flux.just(List.of())`; nó khác “publisher không phát bất kỳ snapshot nào”. Ngoài ra, các cache implementations/versions có thể không cache danh sách rỗng như một cache hit thông thường; hãy quan sát `sourceReads` trong thí nghiệm NONE, không giả định hành vi giống khi danh sách có A/B.

## 9. Bọc source supplier bằng LoadBalancer cache

Tạo `lab.lb.CatalogLoadBalancerConfig` **ở package nằm ngoài phạm vi component scan mặc định** của `lab.caller.CallerApplication`.

~~~java
package lab.lb;

import lab.caller.MutableTopologySupplier;
import lab.caller.TopologyState;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.cloud.loadbalancer.cache.LoadBalancerCacheManager;
import org.springframework.cloud.loadbalancer.core.CachingServiceInstanceListSupplier;
import org.springframework.cloud.loadbalancer.core.ServiceInstanceListSupplier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class CatalogLoadBalancerConfig {

    @Bean
    ServiceInstanceListSupplier catalogSupplier(
            TopologyState topology,
            LoadBalancerCacheManager cacheManager,
            @Value("${lab.use-cache:true}") boolean useCache) {

        ServiceInstanceListSupplier source =
            new MutableTopologySupplier(topology);

        return useCache
            ? new CachingServiceInstanceListSupplier(
                source, cacheManager)
            : source;
    }
}
~~~

**Đây là điểm thay đổi giữa hai phép đo**:

- `lab.use-cache=true`: đường đi `MutableTopologySupplier → CachingServiceInstanceListSupplier → LoadBalancer`.
- `lab.use-cache=false`: LoadBalancer dùng source trực tiếp; không có decorator cache này.

Giữ `spring.cloud.loadbalancer.cache.enabled=true` trong cả hai lần chạy lab, để `LoadBalancerCacheManager` vẫn được auto-configure và bean có thể được inject. **Không đổi property `cache.enabled=false` trong khi vẫn inject manager bắt buộc**, vì có phiên bản/configuration sẽ không tạo manager.

`CachingServiceInstanceListSupplier` nhận một delegate và `CacheManager`; nó được đặt **ngay sau lớp truy xuất nguồn**, trước các filter khác. Đây là thứ tự được Spring Cloud khuyến nghị.

> Trong lab chỉ có một chain cho `catalog-service`. Không tự tạo thêm supplier cache khác trên cùng nguồn, không cấu hình đồng thời `HealthCheckServiceInstanceListSupplier` để phép đo TTL không bị lẫn với health scheduling. Ở dự án thật cần đối chiếu exact API/autoconfiguration với release train.

## 10. Gắn cấu hình theo service ID

Entry point caller `lab.caller.CallerApplication`:

~~~java
package lab.caller;

import lab.lb.CatalogLoadBalancerConfig;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cloud.loadbalancer.annotation.LoadBalancerClient;

@SpringBootApplication
@LoadBalancerClient(
    name = "catalog-service",
    configuration = CatalogLoadBalancerConfig.class
)
public class CallerApplication {

    public static void main(String[] args) {
        SpringApplication.run(CallerApplication.class, args);
    }
}
~~~

`CatalogLoadBalancerConfig` nên nằm ngoài scan của `lab.caller` để bean supplier chỉ áp dụng trong **LoadBalancer child context** của `catalog-service`, không vô tình được đăng ký làm một supplier toàn cục.

### application.yml của caller

~~~yaml
server:
  port: 18090

spring:
  application:
    name: caller-service
  cloud:
    loadbalancer:
      retry:
        enabled: false
      cache:
        enabled: true
        ttl: 6s
        capacity: 256

lab:
  use-cache: true
~~~

**Ý nghĩa quan trọng**:

- `cache.ttl: 6s` là TTL tính **từ lúc ghi entry cache**. Giá trị này cố ý ngắn để dễ quan sát; không phải khuyến nghị production.
- `capacity` là **initial capacity** theo config LoadBalancer, không đồng nghĩa giới hạn cứng số entries.
- Không đặt `spring.cloud.loadbalancer.cache.caffeine.spec`; nếu đặt custom Caffeine spec, nó có thể ghi đè `ttl` và `capacity` ở config chung.
- `retry.enabled=false` giúp không nhầm một logical call với nhiều HTTP attempts trong giai đoạn đo cache.
- Cấu hình này không bật health checks, tránh nhầm chu kỳ probe với thời gian cache tự hết hạn.

## 11. RestClient dùng service ID thay vì cổng thật

Tạo `lab.caller.CatalogClientConfig`:

~~~java
package lab.caller;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.web.client.RestClient;

@Configuration(proxyBeanMethods = false)
class CatalogClientConfig {

    @Bean
    @LoadBalanced
    RestClient.Builder loadBalancedRestClientBuilder() {
        SimpleClientHttpRequestFactory requestFactory =
            new SimpleClientHttpRequestFactory();

        requestFactory.setConnectTimeout(1000);
        requestFactory.setReadTimeout(2000);

        return RestClient.builder().requestFactory(requestFactory);
    }

    @Bean
    RestClient catalogRestClient(
        @Qualifier("loadBalancedRestClientBuilder")
        RestClient.Builder builder) {

        return builder.baseUrl("http://catalog-service").build();
    }
}
~~~

Dùng `@LoadBalanced` ở builder để HTTP request đi qua Spring Cloud LoadBalancer. Request factory chỉ cung cấp timeout I/O cho lab, **không điều khiển tuổi cache instance**.

Client sẽ gọi `http://catalog-service/api/whoami`, nhưng LoadBalancer chọn endpoint thực từ snapshot, ví dụ `127.0.0.1:18081`. Việc tạo một `RestClient.create("http://catalog-service")` riêng **không tự nhận cơ chế LoadBalancer** của Spring.

### Mở rộng cùng phép đo cho WebClient và OpenFeign

Sau khi lab RestClient hội tụ đúng, có thể thử **cùng service ID và cùng supplier cache** qua WebClient hoặc OpenFeign. Hai phương án này **tùy chọn**, không cần bật trong lần đo RestClient đầu tiên.

WebClient cần `spring-boot-starter-webflux` và `@LoadBalanced WebClient.Builder`:

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration(proxyBeanMethods = false)
class CatalogWebClientConfig {

    @Bean
    @LoadBalanced
    WebClient.Builder loadBalancedWebClientBuilder() {
        return WebClient.builder();
    }

    @Bean
    WebClient catalogWebClient(
        @Qualifier("loadBalancedWebClientBuilder") WebClient.Builder builder) {
        return builder.baseUrl("http://catalog-service").build();
    }
}
~~~

Khi có nhiều `WebClient.Builder`, hãy dùng `@Qualifier` cho builder được `@LoadBalanced`. Caller có thể gọi `catalogWebClient.get().uri("/api/whoami").retrieve().bodyToMono(String.class)` và chờ completion trong test thích hợp; không `block()` trên WebFlux event-loop.

OpenFeign cần `spring-cloud-starter-openfeign`, `@EnableFeignClients` và integration LoadBalancer tương thích:

~~~java
import org.springframework.cloud.openfeign.FeignClient;
import org.springframework.web.bind.annotation.GetMapping;

@FeignClient(name = "catalog-service")
interface CatalogFeignClient {
    @GetMapping("/api/whoami")
    String whoami();
}
~~~

Khi các clients thực sự dùng service ID `catalog-service` trong cùng caller, chúng có thể nhận cùng candidate list do supplier context cung cấp. Tuy nhiên **retry, HTTP transport, timeout và thời điểm subscription khác nhau**; hãy tắt retry và so `candidateIds` trước khi so response thời gian thực. Nếu Feign có `url` cố định hoặc WebClient không `@LoadBalanced`, phép đo có thể bypass LoadBalancer.

## 12. Endpoint quan sát nguồn, cache và HTTP thực

Tạo `lab.caller.LabController` để đọc ba lớp: nguồn hiện tại, danh sách supplier mà LoadBalancer nhìn thấy và HTTP response từ instance đích.

~~~java
package lab.caller;

import java.time.Duration;
import java.util.List;

import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.loadbalancer.core.ServiceInstanceListSupplier;
import org.springframework.cloud.loadbalancer.support.LoadBalancerClientFactory;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.client.RestClient;

@RestController
class LabController {

    private final TopologyState topology;
    private final LoadBalancerClientFactory factory;
    private final RestClient client;

    LabController(TopologyState topology,
                  LoadBalancerClientFactory factory,
                  RestClient catalogRestClient) {
        this.topology = topology;
        this.factory = factory;
        this.client = catalogRestClient;
    }

    record SourceView(long observedAtMs, long revision,
        String mode, long changedAtMs,
        List<String> sourceIds, long sourceReads) {}

    record CandidateView(long observedAtMs, long sourceRevision,
        List<String> sourceIds, List<String> candidateIds,
        long sourceReads) {}

    record InstanceReply(String instanceId, long serverTimeMs) {}

    private static List<String> ids(List<ServiceInstance> instances) {
        return instances.stream()
            .map(ServiceInstance::getInstanceId).toList();
    }

    private SourceView view(TopologyState.Snapshot snapshot) {
        return new SourceView(
            System.currentTimeMillis(),
            snapshot.revision(),
            snapshot.mode().name(),
            snapshot.changedAtMs(),
            ids(snapshot.instances()),
            topology.sourceReadCount()
        );
    }

    @GetMapping("/__lab/source")
    SourceView source() {
        return view(topology.current());
    }

    @PostMapping("/__lab/mode")
    SourceView change(@RequestParam TopologyState.Mode mode) {
        return view(topology.switchTo(mode));
    }

    @GetMapping("/__lab/candidates")
    CandidateView candidates() {
        ServiceInstanceListSupplier supplier = factory.getInstance(
            "catalog-service", ServiceInstanceListSupplier.class);

        if (supplier == null) {
            throw new IllegalStateException("Missing catalog supplier");
        }

        List<ServiceInstance> visible = supplier.get()
            .next().block(Duration.ofSeconds(2));

        if (visible == null) {
            visible = List.of();
        }

        TopologyState.Snapshot snapshot = topology.current();

        return new CandidateView(
            System.currentTimeMillis(), snapshot.revision(),
            ids(snapshot.instances()), ids(visible),
            topology.sourceReadCount()
        );
    }

    @GetMapping("/demo/whoami")
    InstanceReply whoami() {
        return client.get()
            .uri("/api/whoami")
            .retrieve()
            .body(InstanceReply.class);
    }
}
~~~

Cách hiểu:

- `GET /__lab/source` xem `TopologyState.current()`, **không đọc hoặc làm nóng cache**.
- `POST /__lab/mode?mode=A_ONLY` đổi nguồn ngay nhưng **không tự invalidate cache**.
- `GET /__lab/candidates` đọc supplier trong child context đúng service ID, có thể cache hit hoặc miss.
- `GET /demo/whoami` thực hiện request HTTP qua `@LoadBalanced RestClient`.

**Điểm đo lường quan trọng:** chính `GET /__lab/candidates` có thể kích hoạt refresh nếu cache đã hết hạn. Đây là một lần truy cập vào supplier, không phải quan sát cache hoàn toàn thụ động. Phương thức `block()` ở đây chỉ dành cho Spring MVC blocking controller; không chuyển nguyên mẫu vào WebFlux event-loop.

Các endpoint `/__lab/*` không có bảo vệ xác thực vì chỉ là môi trường localhost; không đưa ra production.

## 13. Làm nóng cache và quan sát source reads

Giữ cả hai backend chạy, rồi khởi động caller:

~~~bash
java -jar caller-service.jar --server.port=18090
~~~

Đọc nguồn lần đầu:

~~~bash
curl -s http://127.0.0.1:18090/__lab/source
~~~

Response **minh họa, không phải dữ liệu đã đo**:

~~~json
{
  "observedAtMs": 1000000,
  "revision": 1,
  "mode": "BOTH",
  "changedAtMs": 999900,
  "sourceIds": ["catalog-a", "catalog-b"],
  "sourceReads": 0
}
~~~

Làm nóng entry cache:

~~~bash
curl -s http://127.0.0.1:18090/__lab/candidates
~~~

Kỳ vọng sau cache miss đầu:

~~~json
{
  "observedAtMs": 1000100,
  "sourceRevision": 1,
  "sourceIds": ["catalog-a", "catalog-b"],
  "candidateIds": ["catalog-a", "catalog-b"],
  "sourceReads": 1
}
~~~

Gọi lại `/__lab/candidates` trong TTL 6 giây. Với cache hit, `sourceReads` thường giữ nguyên. Sau đó quan sát HTTP thực:

~~~bash
curl -s http://127.0.0.1:18090/demo/whoami
curl -s http://127.0.0.1:18090/demo/whoami
curl -s http://127.0.0.1:18090/demo/whoami
~~~

Với Round Robin và A/B healthy, có thể thấy cả hai định danh, nhưng **một response từ A không chứng minh cache đã loại B**. Cần xem `candidateIds` để biết tập ứng viên.

## 14. Thí nghiệm A: nguồn bỏ B nhưng cache còn A+B

**Điều kiện:** hai backend vẫn chạy; cache đã warm với `[A,B]`; đổi nguồn trước khi TTL hết hạn.

~~~bash
curl -s -X POST "http://127.0.0.1:18090/__lab/mode?mode=A_ONLY"
curl -s http://127.0.0.1:18090/__lab/source
curl -s http://127.0.0.1:18090/__lab/candidates
~~~

Khi cache chưa hết hạn, có thể quan sát:

~~~text
SOURCE sourceIds    = [catalog-a]
CACHE candidateIds  = [catalog-a, catalog-b]
SOURCE revision     = 2
SOURCE readCount    = 1 (chưa refetch)
~~~

**Đây là bằng chứng stale list.** Nếu LoadBalancer chọn B trong thời gian này, backend B vẫn trả 200 vì chúng ta cố ý chưa dừng B. Request thành công không chứng minh ứng viên đã mới.

Sau khi entry hết hạn, một lần gọi `/__lab/candidates` mới có thể tạo cache miss và lấy nguồn hiện tại:

~~~text
SOURCE sourceIds    = [catalog-a]
CACHE candidateIds  = [catalog-a]
SOURCE readCount    = 2 (nếu chỉ một lần refetch tuần tự)
~~~

Không yêu cầu bộ đếm đúng 2 trong mọi setup, vì có thể có requests khác hoặc nhiều context.

| Mốc | Source | Candidate list | Source reads | Ý nghĩa |
|---|---|---|---:|---|
| Warm | A+B | A+B | 1 | Cache được ghi |
| Đổi source | A | A+B | 1 | Cache stale |
| Poll sớm | A | A+B | 1 | Cache hit |
| Poll sau expiry | A | A | 2 | Cache miss và refresh |
| Poll tiếp | A | A | 2 | Cache hit mới |

Nếu ngay sau khi đổi nguồn đã thấy A, có thể cache **gần hết TTL** trước đó. Khởi động lại caller, warm cache và đổi source nhanh hơn để dễ tái hiện.

## 15. PowerShell: đo độ trễ phát hiện bằng polling

Script sau đo bằng timestamp do cùng caller sinh ra. Để lặp lại trong điều kiện ổn định, khởi động lại caller cho topology về BOTH và cache rỗng trước mỗi run.

~~~powershell
$base = "http://127.0.0.1:18090"

$warm = Invoke-RestMethod "$base/__lab/candidates"
Write-Host "Warm candidates:" ($warm.candidateIds -join ",")

$change = Invoke-RestMethod -Method Post -Uri "$base/__lab/mode?mode=A_ONLY"
$changedAt = [long]$change.changedAtMs

$firstSeenAt = $null
for ($i = 0; $i -lt 80; $i++) {
    $view = Invoke-RestMethod "$base/__lab/candidates"
    $ids = @($view.candidateIds)
    $elapsed = [long]$view.observedAtMs - $changedAt

    Write-Host ("+{0} ms | reads={1} | cache={2}" -f $elapsed, $view.sourceReads, ($ids -join ","))

    if ($ids.Count -eq 1 -and $ids[0] -eq "catalog-a") {
        $firstSeenAt = [long]$view.observedAtMs
        break
    }

    Start-Sleep -Milliseconds 250
}

if ($null -eq $firstSeenAt) {
    throw "Cache did not converge within the polling budget"
}

Write-Host "Detection delay (ms):" ($firstSeenAt - $changedAt)
~~~

**Đọc kết quả đúng cách:**

- `changedAtMs` là timestamp khi nguồn thay đổi.
- `observedAtMs` là timestamp khi server tạo response quan sát.
- Poll 250 ms làm mốc phát hiện **muộn hơn hoặc bằng** mốc hội tụ.
- Lần poll sau expiry có thể chính là tác nhân làm cache refresh.
- TTL tính từ **cache write**, không tính từ `changedAtMs`.
- `detectionDelayMs` có thể nhỏ hơn TTL vì cache đã có tuổi trước khi nguồn đổi.

Ví dụ các giá trị sau chỉ để minh họa cách suy luận:

| TTL | Tuổi cache lúc source đổi | Cửa sổ stale còn lại xấp xỉ |
|---|---:|---:|
| 6 s | 0,8 s | 5,2 s |
| 6 s | 3,5 s | 2,5 s |
| 6 s | 5,8 s | 0,2 s |

Kết quả đo thực tế còn có sampling delay, scheduling và overhead; không gọi những con số ví dụ là kết quả benchmark.
## 16. Thí nghiệm B: so sánh bật cache và không bọc cache

Dừng caller, **giữ nguyên hai backend**, rồi chạy chế độ không bọc `CachingServiceInstanceListSupplier`:

~~~bash
java -jar caller-service.jar --server.port=18090 --lab.use-cache=false
~~~

Thử:

~~~bash
curl -s http://127.0.0.1:18090/__lab/candidates
curl -s -X POST "http://127.0.0.1:18090/__lab/mode?mode=A_ONLY"
curl -s http://127.0.0.1:18090/__lab/candidates
~~~

Trong chế độ này, supplier trả snapshot trực tiếp từ `TopologyState` nên lần đọc kế tiếp thấy `[A]`, trừ độ trễ scheduling/HTTP/polling. `sourceReads` tăng theo số lần gọi source.

Muốn đổi TTL thành 30 giây, dừng caller rồi chạy:

~~~bash
java -jar caller-service.jar --server.port=18090 --lab.use-cache=true --spring.cloud.loadbalancer.cache.ttl=30s
~~~

Không thay TTL của một process đang chạy bằng cách sửa lệnh ở terminal khác. Các phép đo so sánh nên **restart caller cho cache sạch** và warm ở cùng thời điểm tương đối.

| Chế độ | Lượt đọc nguồn | Thời gian bắt kịp snapshot mới |
|---|---|---|
| `lab.use-cache=false` | Tăng theo các lần đọc supplier | Lần đọc nguồn kế tiếp |
| Cache TTL 6s | Ít hơn trong thời gian entry còn hạn | Sau entry expiry và access mới |
| Cache TTL 30s | Cache hits kéo dài | Có thể stale lâu hơn |
| Discovery bên ngoài cũng cache | Nhiều tầng cùng tồn tại | Cần đo riêng từng tầng |

**Quan trọng:** `spring.cloud.loadbalancer.cache.enabled` được giữ `true` để cache manager tồn tại; `lab.use-cache=false` chỉ bỏ **decorator cache của lab**. Nếu đặt `cache.enabled=false` nhưng vẫn inject `LoadBalancerCacheManager` bắt buộc, một số version/configuration có thể không tạo bean và ứng dụng không khởi động.

## 17. Thí nghiệm C: thêm instance mới và chuyển tập ứng viên

Sau khi snapshot cache đã hội tụ về `A_ONLY`, đổi nguồn trở lại `BOTH`:

~~~bash
curl -s -X POST "http://127.0.0.1:18090/__lab/mode?mode=BOTH"
~~~

Trước khi entry cache `[A]` hết hạn, candidate list có thể vẫn chỉ có A dù nguồn đã có A+B. Đó là **độ trễ nhận ra instance mới**, thường làm chậm việc phân phối lại tải khi scale-out.

| Thay đổi nguồn | Danh sách cũ có thể vẫn được trả | Hậu quả |
|---|---|---|
| BOTH → A_ONLY | A+B | B vẫn có thể được chọn |
| A_ONLY → BOTH | A | Chưa tận dụng B |
| A_ONLY → B_ONLY | A | Chuyển traffic sang B chậm |
| BOTH → NONE | A+B | Có thể vẫn chọn instance đã bị rút |
| NONE → BOTH | Có thể thấy nguồn sớm hơn dự kiến | Hành vi cache empty list phụ thuộc implementation |

**Thí nghiệm NONE:** supplier nguồn phát `Flux.just(List.of())`, nhưng không được mặc định cache rỗng hành xử hệt snapshot không rỗng. Trong một số phiên bản, lookup cache coi list rỗng như miss. Hãy theo dõi `sourceReads` và ghi lại điều kiện thực tế.

## 18. Thí nghiệm D: dừng backend khi cache vẫn giữ B

Đây là tình huống gần production hơn nhưng dễ gây nhầm nếu chỉ nhìn lỗi HTTP.

1. Khởi động lại caller, warm cache `[A,B]`.
2. Đổi source thành `A_ONLY` khi cache còn hạn.
3. **Dừng tiến trình backend B** ở port 18082.
4. Gọi `/demo/whoami` nhiều lần trong khi `/__lab/candidates` vẫn là `[A,B]`.
5. Đợi TTL hết, đọc candidate list và gọi lại.

Khi cache còn B:

- LoadBalancer chọn A → HTTP 200, mọi thứ có vẻ bình thường.
- LoadBalancer chọn B → có thể gặp `ConnectException`, connection refused hoặc lỗi I/O tùy transport.
- Nếu connection pool từng giữ socket B, có thể gặp reset/disconnect sau khi backend dừng.
- Sau khi cache refresh về `[A]`, các request **mới qua LoadBalancer** không còn chọn B nếu không có lớp chính sách nào khác.

**Đừng xem connect refused là bằng chứng backend B đã gửi HTTP 503**. Đây là lỗi kết nối trước khi có HTTP response từ B. Và cũng đừng coi việc có một request tới A thành công là bằng chứng cache đã hội tụ.

Trong lab `spring.cloud.loadbalancer.retry.enabled=false` để một lần gọi không tạo thêm attempts ẩn. Production có thể retry GET với ngân sách và danh sách instance được cập nhật, nhưng retry **không tự sửa** snapshot stale nếu cache chưa miss.

## 19. Thu thập timeline đúng để phân tích độ trễ

Bảng quan sát nên có:

| Thông tin | Câu hỏi |
|---|---|
| `sourceRevision` | Nguồn đã đổi bao nhiêu lần? |
| `changedAtMs` | Nguồn đổi vào lúc nào? |
| `sourceIds` | Danh sách chính thức ở nguồn là gì? |
| `candidateIds` | LoadBalancer thực sự đang dùng tập ứng viên nào? |
| `sourceReads` | Có bao nhiêu lần supplier phải đọc nguồn? |
| `observedAtMs` | Lần quan sát này được chốt ở thời điểm nào? |
| `cache.ttl` / `lab.use-cache` | Cache có bật không, TTL là bao nhiêu? |
| `pollIntervalMs` | Sai số do lấy mẫu là bao nhiêu? |
| HTTP selected instance, status, cause | Request thật đi đâu và có gặp lỗi mạng không? |
| Discovery/client/transport version | Khả năng triển khai nào ảnh hưởng semantics? |

Log mục tiêu **minh họa**, không phải dữ liệu test đã thực thi:

~~~text
warmAt=1000100 sourceRevision=1 candidates=[A,B] reads=1
changedAt=1001100 sourceRevision=2 source=[A]
observedAt=1001300 candidates=[A,B] reads=1
observedAt=1003100 candidates=[A,B] reads=1
observedAt=1006300 candidates=[A] reads=2
detectionDelayMs=5200
~~~

Chỉ dựa trên một request HTTP từ A để kết luận đã hội tụ là sai: Round Robin vẫn có thể còn B trong danh sách nhưng tình cờ chọn A. Muốn kết luận candidate set mới, phải nhìn `candidateIds` hoặc telemetry tương đương trong chính LoadBalancer.

Khi nhiều caller chạy riêng, **mỗi caller có thể có local cache khác nhau**. Một caller hội tụ không đồng nghĩa mọi caller đều hội tụ. Cần đo phân phối delay across instances/callers.

## 20. Phân tích nhiều nguồn trễ trong production

Lab dùng nguồn trong RAM nên không có propagation delay của một registry thật. Khi thay bằng Eureka/Consul/Kubernetes hoặc control plane tùy biến, đường đi dài hơn:

~~~mermaid
flowchart TD
    A["Thay đổi được commit ở control plane"] --> B["Registry / service discovery"]
    B --> C["Discovery watch, poll hoặc local cache"]
    C --> D["ServiceInstanceListSupplier source"]
    D --> E["LoadBalancer cache"]
    E --> F["Health / zone / version filter"]
    F --> G["LoadBalancer chọn ServiceInstance"]
    G --> H["HTTP connection / request"]
    H --> I["Backend trả response hoặc lỗi"]
~~~

Cần đo ít nhất ba thời điểm: **registry biết thay đổi**, **discovery adapter trả snapshot mới**, và **LoadBalancer supplier trả snapshot mới**. Nếu còn health check, đo lúc health supplier loại hoặc thêm ứng viên.

Một topology update có thể hội tụ theo nhiều cơ chế: watch/push, periodic poll, TTL cache, timeout, hoặc explicit invalidation. **Không lấy tổng tất cả TTL làm công thức chính xác cho mọi hệ thống**: các khoảng có thể chồng lấn, xảy ra đồng thời hoặc được kích hoạt bởi request.

Ví dụ discovery poll 10 giây và LB cache TTL 6 giây có thể tạo khoảng trễ gần 16 giây trong một pha bất lợi, nhưng cũng có thể nhanh hơn nhiều. Chỉ đo **end-to-end detection delay** không đủ để biết cần điều chỉnh lớp nào.

## 21. Health check: nguồn mới không đồng nghĩa tập healthy mới

Ở lab cơ sở, không bật `HealthCheckServiceInstanceListSupplier`. Nếu bật trong thí nghiệm thứ hai:

- Instance có thể vẫn nằm trong nguồn nhưng health check đã phát hiện nó unhealthy và giảm cơ hội được chọn.
- Ngược lại, nguồn đã đổi nhưng health supplier có lịch refetch riêng; nó có thể giữ snapshot đến kỳ refetch.
- Các property như `spring.cloud.loadbalancer.health-check.refetch-instances` và `refetch-instances-interval` ảnh hưởng khả năng làm mới danh sách.
- Health check không phải security check: một instance giả có thể trả HTTP 200.
- Khi **không có instance healthy**, một số cấu hình có fallback về tập đầu vào; không tự kết luận candidate list chắc chắn rỗng.

Ví dụ thuộc tính để tham khảo trong **một lab health riêng**:

~~~yaml
spring:
  cloud:
    loadbalancer:
      health-check:
        initial-delay: 0s
        interval: 2s
        path:
          catalog-service: /actuator/health
        refetch-instances: true
        refetch-instances-interval: 3s
~~~

Các properties **không tự thêm health supplier**. Bạn phải thay supplier chain để có `withHealthChecks()` hoặc `withBlockingHealthChecks()` phù hợp, đồng thời cung cấp endpoint health (ví dụ Spring Boot Actuator).

Spring Cloud lưu ý `HealthCheckServiceInstanceListSupplier` có cơ chế caching riêng qua Reactor `replay()`, nên **không nên chồng thêm CachingServiceInstanceListSupplier một cách mù quáng**. Khi đo, thay một lớp mỗi lần và ghi rõ thứ tự supplier.

## 22. Caffeine specification có thể ghi đè TTL

Đối với LoadBalancer cache, các properties chung:

~~~yaml
spring:
  cloud:
    loadbalancer:
      cache:
        ttl: 6s
        capacity: 256
~~~

có thể bị một Caffeine specification riêng ghi đè, ví dụ:

~~~yaml
spring:
  cloud:
    loadbalancer:
      cache:
        caffeine:
          spec: expireAfterWrite=30s,maximumSize=500
~~~

Khi config có `caffeine.spec`, không được nhìn riêng `cache.ttl=6s` rồi khẳng định expire sau 6 giây. Custom spec có thể ghi đè TTL/capacity.

Ngoài ra, `capacity` chung là **initial capacity**, không phải trần cố định số service IDs hoặc sockets. Caching danh sách instances **không đồng nghĩa** cache response và cũng không thay thế connection pool.

### Double caching

Nếu DiscoveryClient đã cache danh sách, thêm LB cache tạo hai tầng:

~~~text
Registry thay đổi -> Discovery cache còn [A,B]
                 -> LB cache hết hạn và đọc lại Discovery
                 -> LB cache ghi lại [A,B] cũ
~~~

Trong trường hợp này, giảm LB TTL xuống 1 giây có thể vẫn không thấy bản sao mới nếu **discovery chưa refresh**. Muốn xử lý, phải xác định tầng nào giữ stale data, tránh tăng tải registry không cần thiết. Tài liệu Spring Cloud khuyến nghị tránh double caching khi discovery đã có cache riêng.

## 23. Cache expiry không phải cơ chế thu hồi an ninh

Có một khác biệt giữa stale topology do autoscaling và stale topology sau khi **instance bị thu hồi vì mất tin cậy**.

- **TTL expiration:** entry trở thành không còn hợp lệ theo cache; thường cần một lượt truy cập để fetch dữ liệu mới.
- **Explicit invalidation:** xóa cache do một sự kiện đáng tin từ control plane.
- **Registry push/watch:** nguồn có thể cập nhật nhanh nhưng không mặc nhiên invalidate LB cache.
- **Network egress / certificate revocation:** chặn request tới đích bị cấm ngay cả khi caller còn cache cũ.

**Không coi TTL 6 giây là bảo đảm “sau 6 giây không caller nào còn gọi B”.** Có thể có nhiều caller với tuổi cache khác nhau, request in-flight, nhiều lớp discovery/gateway và kết nối đã mở. Nếu cần thu hồi khẩn cấp, dùng lớp chặn network/identity độc lập với local cache.

Với scale-out thường ngày, TTL ngắn cải thiện freshness nhưng tăng cache misses và áp lực nguồn discovery; phải cân bằng theo SLO và mức tải.

## 24. Kế hoạch kiểm thử và tiêu chí nghiệm thu

| Test case | Điều kiện | Assertion đúng |
|---|---|---|
| Warm BOTH | Hai backend chạy, cache rỗng | Candidates A+B |
| Source đổi runtime | POST mode=A_ONLY | Source revision tăng, sourceIds=A |
| Stale window | Chuyển A_ONLY trước TTL | Candidate list có thể vẫn A+B |
| Cache refresh | Poll sau TTL | Candidate list hội tụ A |
| Không cache | `lab.use-cache=false` | Lượt đọc kế tiếp thấy A |
| TTL dài | 30s thay 6s, restart caller | Stale window có thể dài hơn |
| Scale-out | A_ONLY→BOTH | B có thể xuất hiện chậm |
| NONE | Source không còn ứng viên | Không chọn đích sau khi hội tụ; kiểm tra cache empty |
| Backend chết | Cache còn B, backend B dừng | Phân loại connect error, không nhầm HTTP 503 |
| Double cache | Discovery giả lập có cache riêng | LB refetch có thể nhận dữ liệu nguồn cũ |
| Health supplier | Probe và refetch theo lịch | Đo riêng health convergence |
| Nhiều caller | Hai process cache riêng | Detection delay không giống nhau |
| Kết nối cũ | Pool đã mở socket tới B | Socket state khác instance list state |

### Tránh flaky trên CI

Đừng assert hội tụ **đúng vào 6.000 ms** bằng `Thread.sleep(6000)`. Nên:

1. Warm cache có timestamp và revision rõ ràng.
2. Đổi source trước khi TTL sắp hết.
3. Kiểm tra source mới trước cache mới.
4. Poll với interval xác định và một deadline test hữu hạn.
5. Assert **cuối cùng** candidate list đạt trạng thái mong muốn; lưu detectionDelayMs.
6. Không assert thứ tự Round Robin nếu không thiết kế test riêng cho thuật toán.
7. Khi cần kiểm thử chính xác expiry, dùng cache test harness có **clock/ticker điều khiển được** thay vì phụ thuộc wall clock.

Trong STEP 4 hiện tại chỉ biên soạn tài liệu; các test và benchmark mô tả ở đây **chưa được thực thi**.

## 25. Bài tập dự đoán kết quả

**Câu A:** Cache ghi `[A,B]` tại t=0, TTL 6s. Nguồn bỏ B tại t=4s. Caller đọc supplier tại t=4,2s và t=6,3s. Với nguồn đã đổi và không có cache khác, hãy dự đoán.

**Gợi ý/đáp án:** t=4,2s có thể vẫn trả `[A,B]`; t=6,3s entry đã quá TTL và truy cập có thể refresh sang `[A]`.

**Câu B:** Nếu cache đã hết hạn nhưng không có request trong 20 giây, có thể khẳng định cache đã fetch nguồn tại giây thứ 6? **Không**; expiry không mặc nhiên đồng nghĩa proactive refresh.

**Câu C:** Backend B dừng, nhưng retry GET thành công qua A. Cache đã hội tụ chưa? **Chưa thể biết**; kiểm tra candidateIds hoặc nguồn cache thực tế.

**Câu D:** Tại sao health probe 200 không chứng minh instance mới đã được discovery và LoadBalancer nhìn thấy? Vì health check, registration và danh sách LB là **những trạng thái/ranh giới khác nhau**.

**Câu E:** Đặt `cache.ttl=6s` và `cache.caffeine.spec=expireAfterWrite=30s` thì dùng mốc nào để dự đoán? Phải đối chiếu effective configuration; Caffeine spec có thể ghi đè TTL chung.

## 26. Checklist hoàn thành bài

- Đã chạy hai backend phân biệt A/B và một caller theo service ID.
- Caller dùng `@LoadBalanced RestClient.Builder` thay vì gọi cổng thật.
- `@LoadBalancerClient` chỉ dùng supplier tùy biến cho `catalog-service`.
- Nguồn `TopologyState` thay đổi được **không cần restart**.
- `/__lab/source` không làm cache refetch.
- `/__lab/candidates` đọc danh sách supplier và có thể tạo cache miss.
- Có bộ đếm `sourceReads` và revision/changedAtMs.
- Đã quan sát một khoảng **sourceIds khác candidateIds**.
- Đã nhìn thấy ứng viên hội tụ sau TTL và lần đọc tiếp theo.
- Đã đo detection delay với interval polling rõ ràng.
- Đã so sánh mode có cache và không cache.
- Đã thử TTL khác nhau và ghi điều kiện warm-up.
- Không lấy response HTTP 200 từ A làm bằng chứng B đã bị loại.
- Đã hiểu sự khác nhau giữa stale list và backend chết/connection pool.
- Đã tách health/refetch/retry ra khỏi phép đo cache cơ sở.
- Không đưa endpoint `/__lab/*` không có authentication lên môi trường public.

## 27. Kết luận

**Cache cũ là một trạng thái có thể nhìn thấy và đo được.** Khi nguồn đã chuyển từ `[catalog-a, catalog-b]` sang `[catalog-a]`, LoadBalancer vẫn có thể nhận danh sách cũ trong suốt thời gian entry cache còn hiệu lực. Chỉ khi entry hết hạn và có truy cập dẫn tới refetch, tập ứng viên mới mới được quan sát.

**TTL tính từ lần ghi cache, không phải lần thay đổi topology**. Độ trễ phát hiện còn phụ thuộc tuổi cache ở thời điểm đổi nguồn, poll interval, discovery/health refresh và các lớp caching khác. Khi vận hành RestClient, WebClient hoặc OpenFeign với Spring Cloud LoadBalancer, hãy đo **nguồn, candidate list và kết quả HTTP** riêng, tránh double caching không cần thiết, và không xem việc retry thành công như bằng chứng rằng danh sách `ServiceInstance` đã hội tụ.

## Tài liệu tham khảo

- Spring Cloud LoadBalancer: https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html
- Spring Cloud Commons configuration properties: https://docs.spring.io/spring-cloud-commons/reference/configprops.html
- Spring Framework RestClient: https://docs.spring.io/spring-framework/reference/integration/rest-clients.html
- Caffeine cache concepts: https://github.com/ben-manes/caffeine




