# Dừng ứng dụng an toàn và hủy đăng ký trước khi kết thúc

Trong hệ thống Spring Cloud, một instance có thể đang được gọi thông qua service registry, Spring Cloud LoadBalancer, API gateway hoặc Kubernetes Service. Nếu process dừng đột ngột trong khi registry vẫn quảng bá instance là khả dụng, client có thể tiếp tục gửi request tới một địa chỉ đã ngừng nhận traffic. Kết quả thường là lỗi kết nối, request bị reset hoặc công việc đang xử lý bị gián đoạn.

Một lần shutdown an toàn cần phối hợp ba việc: **ngừng nhận traffic mới, hoàn tất công việc đang chạy, rồi hủy đăng ký instance và đóng tài nguyên**. Spring Boot cung cấp graceful shutdown cho web server; Spring Cloud Commons cung cấp `ServiceRegistry` và lifecycle auto-registration; nền tảng triển khai như Kubernetes quản lý tín hiệu dừng và thời gian chờ trước khi buộc process kết thúc.

Bài học thuộc chương **Vận hành** của module **SPRING_CLOUD_CORE**. Ta sẽ tìm hiểu vòng đời shutdown, cách đưa instance ra khỏi service registry, phối hợp readiness và traffic draining, xử lý request đang chạy, đóng consumer/scheduler, cấu hình Kubernetes, kiểm thử thứ tự dừng và chẩn đoán các lỗi thường gặp.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích vì sao phải đưa instance ra khỏi traffic trước khi process kết thúc.
- Phân biệt readiness, liveness, trạng thái service registry và trạng thái process.
- Bật graceful shutdown trong Spring Boot và đặt timeout theo thời gian xử lý thực tế.
- Dùng `ServiceRegistry` để đổi trạng thái hoặc deregister một registration.
- Hiểu auto-registration và auto-deregistration của Spring Cloud Commons.
- Phối hợp readiness `REFUSING_TRAFFIC` với trạng thái `OUT_OF_SERVICE` của registry.
- Hiểu thứ tự dừng của `SmartLifecycle` và callback của `stop(Runnable)`.
- Thiết kế một bước drain trước khi Spring Boot dừng web server.
- Cấu hình `preStop` và `terminationGracePeriodSeconds` trong Kubernetes.
- Đặt thời gian chờ dựa trên propagation của registry, cache load balancer và request đang chạy.
- Đóng message consumer, scheduler và connection pool theo thứ tự phù hợp.
- Kiểm thử shutdown thành công, timeout, registry unavailable và thao tác lặp.

## 2. Vì sao shutdown cần một quy trình?

Giả sử `orders-service` có ba instance đang được Eureka quảng bá. Load balancer đã nhận danh sách ba instance và gửi request tới một instance đang chuẩn bị deploy phiên bản mới.

Nếu instance đó chỉ nhận `SIGTERM` rồi đóng server ngay, Eureka có thể vẫn giữ registration trong một khoảng thời gian. Client còn cache địa chỉ cũ sẽ tiếp tục chọn instance đó. Request mới có thể thất bại dù hai replica còn lại vẫn hoạt động.

Một quy trình shutdown có kiểm soát sẽ:

1. Đánh dấu instance không còn nhận request mới.
2. Cập nhật service registry để client ngừng chọn instance.
3. Chờ thông tin thay đổi lan tới registry, discovery client và load balancer.
4. Dừng nhận kết nối mới, hoàn tất request đang xử lý.
5. Dừng consumer/scheduler và hoàn tất hoặc chuyển giao công việc đang chạy.
6. Hủy registration, đóng connection pool, thread và tài nguyên.
7. Kết thúc process trong thời gian nền tảng cho phép.

~~~mermaid
flowchart TD
    A[Shutdown requested] --> B[Mark readiness REFUSING_TRAFFIC]
    B --> C[Mark registry OUT_OF_SERVICE]
    C --> D[Wait for discovery and LB propagation]
    D --> E[Spring Boot graceful web shutdown]
    E --> F[Finish in-flight HTTP requests]
    F --> G[Stop consumers and scheduled work]
    G --> H[Auto-deregister service registration]
    H --> I[Close clients and resources]
    I --> J[Process exits]
~~~

Thứ tự cụ thể giữa các bước có thể khác theo service registry và nền tảng chạy ứng dụng. Điều cần giữ là client phải có cơ hội loại instance khỏi traffic trước khi endpoint ngừng phục vụ, và các công việc đang chạy phải có thời gian hoàn tất trước khi process bị buộc dừng.

## 3. Phân biệt readiness, liveness và registry status

Ba trạng thái này phục vụ những mục đích khác nhau:

| Trạng thái | Câu hỏi được trả lời | Ai sử dụng |
| --- | --- | --- |
| Readiness | Instance có nên nhận traffic mới không? | Kubernetes Service, load balancer, platform probe |
| Liveness | Process có còn ở trạng thái có thể tiếp tục chạy không? | Kubernetes restart policy, orchestration |
| Service registry status | Instance có được discovery client chọn không? | Eureka, Consul, Zookeeper hoặc registry khác |

Khi bắt đầu drain:

- Readiness chuyển sang `REFUSING_TRAFFIC`.
- Registration có thể chuyển sang `OUT_OF_SERVICE` hoặc trạng thái tương đương của provider.
- Liveness vẫn là `CORRECT` trong lúc ứng dụng đang hoàn tất request.
- Process chỉ kết thúc sau khi các bước shutdown đã hoàn tất hoặc hết thời gian cho phép.

Không dùng liveness để báo instance đang drain. Nếu liveness chuyển sang lỗi, Kubernetes có thể restart process và làm mất thời gian hoàn tất request. Readiness mới là tín hiệu phù hợp để ngừng đưa traffic mới tới instance.

Spring Boot công bố `AvailabilityChangeEvent` cho readiness và liveness. Khi ứng dụng dùng Actuator, các trạng thái này có thể được expose qua health groups như `readiness` và `liveness`.

## 4. Graceful shutdown của Spring Boot

Spring Boot hỗ trợ graceful shutdown cho web application dùng embedded Tomcat, Jetty hoặc Reactor Netty. Khi application context đóng, web server ngừng nhận request mới và cho request đang chạy một khoảng thời gian để hoàn tất.

Trong một số phiên bản Spring Boot mới, graceful shutdown được bật mặc định. Để cấu hình hành vi một cách tường minh và dễ đọc trong môi trường triển khai, có thể khai báo:

~~~yaml
server:
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 25s
~~~

`server.shutdown: graceful` yêu cầu web server dừng theo cách có kiểm soát. `spring.lifecycle.timeout-per-shutdown-phase` đặt thời gian tối đa cho một pha dừng `SmartLifecycle`. Khi timeout hết, Spring tiếp tục quá trình đóng context; không nên giả định mọi request dài đều được giữ vô thời hạn.

### 4.1. Điều gì xảy ra với HTTP request?

Trong thời gian graceful shutdown:

- Server ngừng nhận request mới theo cơ chế của embedded server.
- Request đang xử lý có cơ hội hoàn tất.
- Persistent connection và giao thức cụ thể có thể ảnh hưởng cách server từ chối request mới.
- Khi hết timeout, quá trình shutdown tiếp tục ngay cả khi còn request chưa hoàn tất.

Tomcat, Jetty và Reactor Netty có thể từ chối kết nối mới ở network layer. Chi tiết response phụ thuộc server và phiên bản. Vì vậy, hãy kiểm thử với server thật mà ứng dụng đang dùng, đặc biệt nếu có streaming response, WebSocket, long polling hoặc request chạy lâu.

### 4.2. Chọn timeout dựa trên workload

Timeout phải lớn hơn thời gian xử lý bình thường của request cần được drain, nhưng cũng phải nằm trong giới hạn của nền tảng.

Ví dụ:

| Thành phần | Ngân sách ví dụ |
| --- | ---: |
| Registry update và propagation window | 10 giây |
| HTTP request đang chạy hoàn tất | 20 giây |
| Consumer/scheduler dừng và hoàn tất công việc | 15 giây |
| Đóng tài nguyên và safety margin | 10 giây |
| Tổng ngân sách triển khai | 55 giây |

Đây chỉ là ví dụ tính ngân sách. Đo p95/p99 thời gian request, thời gian xử lý message và độ trễ cập nhật registry của hệ thống thật để chọn giá trị phù hợp.

`timeout-per-shutdown-phase` áp dụng theo từng pha lifecycle. Nếu ứng dụng có nhiều pha dừng tuần tự, tổng thời gian đóng context có thể lớn hơn một timeout đơn lẻ. Nền tảng container phải dành đủ thời gian cho cả `preStop`, các pha shutdown và khoảng dự phòng.

### 4.3. Kiểm tra shutdown được kích hoạt đúng

Spring Boot thường nhận yêu cầu đóng context khi process nhận tín hiệu kết thúc như `SIGTERM`. Một số IDE hoặc cách dừng process trực tiếp có thể không gửi tín hiệu phù hợp, khiến graceful shutdown không chạy như mong đợi.

Trong môi trường container, hãy kiểm thử bằng cách xóa Pod hoặc gửi tín hiệu `SIGTERM` tới process chính. Không kết luận graceful shutdown hoạt động chỉ từ việc bấm nút Stop trong IDE.

## 5. ServiceRegistry trong Spring Cloud Commons

Spring Cloud Commons cung cấp interface `ServiceRegistry` để thao tác với registration của instance:

~~~java
public interface ServiceRegistry<R extends Registration> {

    void register(R registration);

    void deregister(R registration);

    void close();

    void setStatus(R registration, String status);

    <T> T getStatus(R registration);
}
~~~

`Registration` là marker interface. Mỗi implementation có kiểu registration và tập trạng thái riêng:

| Registry | Registration phổ biến | Ghi chú |
| --- | --- | --- |
| Eureka | `EurekaRegistration` | Hỗ trợ trạng thái `UP`, `DOWN`, `OUT_OF_SERVICE`, `UNKNOWN` |
| Consul | `ConsulRegistration` | Trạng thái phụ thuộc health check và implementation Consul |
| Zookeeper | `ZookeeperRegistration` | Hành vi đăng ký/hủy đăng ký phụ thuộc implementation |

### 5.1. Đổi trạng thái trước khi deregister

`setStatus(registration, status)` cho phép báo instance không còn nhận traffic. Ví dụ với Eureka, `OUT_OF_SERVICE` cho biết instance đã đăng ký nhưng không còn phục vụ request thông thường.

~~~java
public final class RegistryDrainOperation<R extends Registration> {

    private final ServiceRegistry<R> serviceRegistry;
    private final R registration;

    public RegistryDrainOperation(
            ServiceRegistry<R> serviceRegistry,
            R registration) {
        this.serviceRegistry = serviceRegistry;
        this.registration = registration;
    }

    public void markOutOfService() {
        serviceRegistry.setStatus(registration, "OUT_OF_SERVICE");
    }

    public void deregister() {
        serviceRegistry.deregister(registration);
    }
}
~~~

Đây là helper generic. Khi cấu hình bean trong ứng dụng, dùng kiểu registration cụ thể của provider đang chạy. Không phải registry nào cũng hiểu chuỗi `OUT_OF_SERVICE`; hãy tra cứu status hợp lệ của implementation trước khi sử dụng.

### 5.2. Auto-registration và auto-deregistration

Khi có implementation `DiscoveryClient` và service registry trên classpath, Spring Cloud có thể tự đăng ký local server. `@EnableDiscoveryClient` không còn bắt buộc trong các cấu hình hiện đại nếu implementation đã được auto-configuration phát hiện.

Có thể tắt auto-registration bằng:

~~~yaml
spring:
  cloud:
    service-registry:
      auto-registration:
        enabled: false
~~~

Hoặc dùng `@EnableDiscoveryClient(autoRegister = false)` ở các phiên bản hỗ trợ annotation này. Chỉ tắt auto-registration khi ứng dụng có quy trình đăng ký riêng.

Trong Spring Cloud Commons, lifecycle auto-registration sẽ gọi `ServiceRegistry.deregister(...)` khi dừng. `AbstractAutoServiceRegistration` hiện triển khai stop lifecycle ở phase `0` và thực hiện deregister rồi đóng service registry. Đây là cơ chế dọn dẹp tự động; nó không tự tạo propagation window trước khi web server bắt đầu graceful shutdown.

Implementation này lắng nghe `WebServerInitializedEvent` để đăng ký service sau khi biết port của web server. Khi bean bị destroy, callback cleanup gọi stop; stop hủy application registration, hủy management registration nếu đã đăng ký và đóng service registry. Trạng thái running giúp thao tác stop lặp không deregister hai lần.

Nếu management server chạy trên port riêng, kiểm tra `spring.cloud.service-registry.auto-registration.register-management`. Property này mặc định là `true` trong Spring Cloud Commons 5.0.4; đặt `false` nếu không muốn quảng bá management endpoint như một service riêng.

### 5.3. Eureka unregister-on-shutdown

Với Spring Cloud Netflix Eureka, property:

~~~yaml
eureka:
  client:
    should-unregister-on-shutdown: true
~~~

cho phép client chủ động unregister khỏi Eureka khi shutdown. Đây là giá trị mặc định trong cấu hình hiện hành. Giữ tùy chọn này bật nếu muốn instance tự hủy registration khi dừng bình thường.

Không dựa vào lease expiration để thay cho deregistration chủ động. Lease heartbeat và thời gian hết hạn là cơ chế phát hiện instance mất liên lạc; chúng không thay thế quy trình drain có kiểm soát.

## 6. Đưa instance ra khỏi traffic trước khi gửi SIGTERM

Nếu chỉ chờ auto-deregistration chạy trong lúc application context đóng, có thể không còn đủ thời gian để registry và các discovery client cập nhật cache trước khi server ngừng nhận request. Một quy trình drain chủ động nên chạy trước khi gửi `SIGTERM`.

Thứ tự đề xuất:

1. Đặt readiness thành `REFUSING_TRAFFIC`.
2. Cập nhật service registry sang trạng thái không phục vụ, ví dụ `OUT_OF_SERVICE` với Eureka.
3. Chờ propagation window để registry và client/load balancer cập nhật.
4. Gửi `SIGTERM` để Spring Boot bắt đầu graceful shutdown.
5. Chờ request và công việc đang chạy hoàn tất.
6. Để Spring Cloud auto-registration deregister registration và đóng registry client.

Propagation không phải lúc nào cũng tức thời. Ví dụ, Eureka client hiện có chu kỳ fetch registry mặc định 30 giây; Spring Cloud LoadBalancer có cache TTL mặc định 35 giây. Các giá trị này là cấu hình mặc định của những phiên bản được tham chiếu, không phải thời gian chờ bắt buộc cho mọi hệ thống. Đo cache chain và chu kỳ cập nhật thực tế của provider/client để xác định propagation window.

### 6.1. Đưa readiness về REFUSING_TRAFFIC

Có thể phát `AvailabilityChangeEvent` để Spring Boot cập nhật readiness:

~~~java
import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.context.ApplicationContext;
import org.springframework.stereotype.Component;

@Component
public class ReadinessDrain {

    private final ApplicationContext applicationContext;

    public ReadinessDrain(ApplicationContext applicationContext) {
        this.applicationContext = applicationContext;
    }

    public void refuseTraffic() {
        AvailabilityChangeEvent.publish(
                applicationContext,
                ReadinessState.REFUSING_TRAFFIC);
    }
}
~~~

Readiness probe sẽ phản ánh ứng dụng không còn sẵn sàng nhận traffic. Nếu Kubernetes sử dụng readiness probe từ Spring Boot Actuator, EndpointSlice controller có thể loại Pod khỏi các endpoint sẵn sàng của Service.

### 6.2. Cập nhật status của registry

Với registry có status `OUT_OF_SERVICE`, có thể gọi endpoint Actuator của Spring Cloud Commons nếu endpoint đã được expose và bảo vệ:

~~~bash
curl -fsS -X POST http://127.0.0.1:8080/actuator/serviceregistry \
  -H "Content-Type: application/json" \
  -d '{"status":"OUT_OF_SERVICE"}'
~~~

Endpoint cần có `Registration` bean trong application context. Status hợp lệ phụ thuộc provider; Eureka hỗ trợ `OUT_OF_SERVICE`, còn Consul hoặc Zookeeper có thể dùng cơ chế khác.

Chỉ expose endpoint này trên management network hoặc loopback và yêu cầu quyền phù hợp. Không mở endpoint thay đổi registry status ra Internet.

### 6.3. Đưa readiness và registry status vào cùng một thao tác

Trong control plane hoặc drain service, thực hiện cả hai thao tác trước khi dừng process:

~~~java
public class InstanceDrainService<R extends Registration> {

    private final ReadinessDrain readinessDrain;
    private final RegistryDrainOperation<R> registryDrain;

    public InstanceDrainService(
            ReadinessDrain readinessDrain,
            RegistryDrainOperation<R> registryDrain) {
        this.readinessDrain = readinessDrain;
        this.registryDrain = registryDrain;
    }

    public void beginDrain() {
        readinessDrain.refuseTraffic();
        registryDrain.markOutOfService();
    }
}
~~~

Nếu registry update thất bại, hãy ghi log/metric và quyết định chính sách rõ ràng. Với hệ thống yêu cầu nghiêm ngặt, có thể không tiếp tục shutdown cho tới khi đã xác nhận instance không còn được chọn; với môi trường ưu tiên kết thúc deployment đúng hạn, có thể tiếp tục sau timeout và chấp nhận rủi ro có kiểm soát.

Controller được gọi từ hook của nền tảng có thể rất nhỏ:

~~~java
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/internal")
public class DrainController {

    private final InstanceDrainService<?> drainService;

    public DrainController(InstanceDrainService<?> drainService) {
        this.drainService = drainService;
    }

    @PostMapping("/drain")
    public ResponseEntity<Void> drain() {
        drainService.beginDrain();
        return ResponseEntity.accepted().build();
    }
}
~~~

Endpoint này là ví dụ do ứng dụng tự tạo, không phải endpoint mặc định của Spring Cloud. Bảo vệ bằng authentication/authorization và chỉ cho phép control plane hoặc lifecycle hook nội bộ gọi. Thao tác phải idempotent vì orchestrator có thể retry request.

## 7. Thứ tự dừng của SmartLifecycle

Spring Framework cho phép các thành phần triển khai `SmartLifecycle` để kiểm soát thứ tự khởi động và dừng. Giá trị phase thấp được start trước và stop sau; phase cao được start sau và stop trước. Khi hai bean có cùng phase, thứ tự tương đối không được bảo đảm. Quan hệ `depends-on` có thể ghi đè thứ tự phase.

Điều này quan trọng vì Spring Boot dừng embedded web server theo một pha graceful shutdown sớm trong quá trình đóng context. Spring Cloud Commons auto-registration dừng ở phase riêng và gọi deregister. Trong implementation hiện hành, `AbstractAutoServiceRegistration.getPhase()` trả về `0`.

Một hệ quả vận hành là: không nên chờ tới bước auto-deregister cuối cùng rồi mới bắt đầu drain. Hãy cập nhật trạng thái readiness/registry trước khi gửi tín hiệu đóng context, hoặc thêm một lifecycle hook có phase cao hơn web server graceful shutdown để đánh dấu instance không nhận traffic.

### 7.1. Dùng SmartLifecycle để đánh dấu instance trước khi web server dừng

Ví dụ sau gọi một thao tác drain đồng bộ ở pha lifecycle cao. `SmartLifecycle.DEFAULT_PHASE` là phase mặc định có giá trị cao; trong Spring Boot 4.1.2, `WebServerApplicationContext.GRACEFUL_SHUTDOWN_PHASE` có giá trị thấp hơn nên web server graceful shutdown chạy sau lifecycle bean này. Kiểm tra lại phase của phiên bản đang dùng nếu có tùy chỉnh lifecycle.

~~~java
import org.apache.commons.logging.Log;
import org.apache.commons.logging.LogFactory;
import org.springframework.context.SmartLifecycle;

public final class RegistryDrainLifecycle implements SmartLifecycle {

    private static final Log log =
            LogFactory.getLog(RegistryDrainLifecycle.class);

    private final InstanceDrainService<?> drainService;
    private volatile boolean running;

    public RegistryDrainLifecycle(InstanceDrainService<?> drainService) {
        this.drainService = drainService;
    }

    @Override
    public void start() {
        running = true;
    }

    @Override
    public void stop(Runnable callback) {
        try {
            drainService.beginDrain();
        }
        catch (RuntimeException exception) {
            log.error("Could not mark instance out of service before shutdown",
                    exception);
        }
        finally {
            running = false;
            callback.run();
        }
    }

    @Override
    public void stop() {
        stop(() -> { });
    }

    @Override
    public boolean isRunning() {
        return running;
    }

    @Override
    public boolean isAutoStartup() {
        return true;
    }

    @Override
    public int getPhase() {
        return SmartLifecycle.DEFAULT_PHASE;
    }
}
~~~

Callback trong `stop(Runnable)` phải được gọi khi thành phần hoàn tất công việc dừng. Nếu không gọi callback, lifecycle processor có thể chờ đến timeout. Ví dụ ghi lỗi và tiếp tục shutdown nếu registry update thất bại; hệ thống cần chính sách nghiêm ngặt có thể chọn fail deployment hoặc yêu cầu operator xử lý thay vì bỏ qua lỗi.

### 7.2. Giới hạn của lifecycle hook

Lifecycle hook giúp thực hiện thao tác trong cùng process, nhưng không tự bảo đảm registry đã lan trạng thái mới tới mọi discovery client. Nếu cần một khoảng chờ propagation có kiểm soát, hãy dùng bước drain từ orchestrator hoặc control plane trước khi gửi `SIGTERM`.

Không dùng `Thread.sleep()` dài trong lifecycle bean mà không tính nó vào ngân sách shutdown. Một thao tác registry bị treo hoặc timeout mạng có thể chiếm hết thời gian dừng của ứng dụng. Cấu hình timeout kết nối của registry client và giới hạn thời gian cho drain operation.

## 8. Kubernetes: preStop và termination grace period

Kubernetes có quy trình terminate Pod riêng:

1. Pod được đánh dấu đang kết thúc.
2. Kubelet chạy hook `preStop` nếu được cấu hình.
3. Sau khi hook hoàn tất, container runtime gửi stop signal (thường là `SIGTERM`) tới process chính.
4. Process có thời gian tới hết `terminationGracePeriodSeconds` để kết thúc.
5. Khi grace period hết, process còn sống có thể nhận `SIGKILL`.

Thời gian grace period bắt đầu trước khi `preStop` chạy. Vì vậy, hook và toàn bộ Spring shutdown cùng dùng chung ngân sách này.

### 8.1. Expose readiness probe

Ví dụ cấu hình Actuator:

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
  endpoints:
    web:
      exposure:
        include:
          - health
          - info
          - serviceregistry
~~~

Kubernetes có thể kiểm tra endpoint:

~~~text
/actuator/health/readiness
/actuator/health/liveness
~~~

Readiness sẽ chuyển sang trạng thái không sẵn sàng khi ứng dụng phát `AvailabilityChangeEvent` với `ReadinessState.REFUSING_TRAFFIC`. Liveness vẫn có thể tiếp tục khỏe trong suốt quá trình drain.

### 8.2. preStop gọi drain endpoint

Nếu ứng dụng cung cấp một endpoint nội bộ có xác thực để bắt đầu drain, có thể gọi endpoint đó trong `preStop` rồi chờ một propagation window ngắn:

~~~yaml
spec:
  terminationGracePeriodSeconds: 75
  containers:
    - name: orders-service
      image: example/orders-service:1.0.0
      lifecycle:
        preStop:
          exec:
            command:
              - /bin/sh
              - -c
              - "curl -fsS -X POST http://127.0.0.1:8080/internal/drain && sleep 10"
~~~

Ví dụ dùng `curl` và `sleep` để minh họa. Image phải có các công cụ đó hoặc dùng một executable chuyên dụng. Endpoint drain chỉ nên truy cập từ loopback/management network và phải được bảo vệ bằng cơ chế xác thực phù hợp.

Sau khi hook hoàn tất, kubelet gửi `SIGTERM`. Spring Boot chuyển readiness sang `REFUSING_TRAFFIC` trong shutdown, dừng nhận request mới và xử lý các request đang chạy theo graceful shutdown timeout.

### 8.3. Tính terminationGracePeriodSeconds

Với ví dụ trên, ngân sách cần bao gồm:

| Giai đoạn | Ví dụ |
| --- | ---: |
| preStop gọi drain và chờ registry propagation | 10 giây |
| Spring Boot graceful shutdown | 25 giây |
| Dừng consumer và đóng tài nguyên | 15 giây |
| Safety margin | 15 giây |
| Tổng | 65 giây |

Đặt `terminationGracePeriodSeconds` lớn hơn tổng ngân sách, ví dụ 75 giây. Đây là giá trị minh họa; hãy đo workload và chọn timeout thực tế.

Kubernetes bắt đầu loại endpoint đang terminate khỏi luồng traffic thông thường trong khi process đang shutdown. Việc cập nhật EndpointSlice và việc deregister trong Eureka/Consul là hai cơ chế khác nhau. Nếu ứng dụng dùng đồng thời Kubernetes Service và registry riêng, hãy drain cả hai đường.

### 8.4. Tránh lạm dụng preStop sleep

Một khoảng chờ có thể giúp propagation, nhưng không thay thế trạng thái readiness hoặc deregistration. Chỉ sleep mà không đánh dấu instance out-of-service vẫn có thể khiến client tiếp tục gửi request trong thời gian chờ.

Không kéo dài preStop hơn termination grace period cho phép. Nếu hook không hoàn tất trước deadline, Kubernetes vẫn có thể buộc dừng container.

## 9. Dừng consumer, scheduler và background work

HTTP graceful shutdown chỉ xử lý traffic của web server. Ứng dụng Spring Cloud còn có thể chạy Kafka/RabbitMQ consumer, scheduler, batch job, listener hoặc task bất đồng bộ.

Trước khi kết thúc process:

- Ngừng nhận message mới hoặc pause consumer.
- Hoàn tất message đang xử lý hoặc rollback để broker có thể redeliver.
- Commit offset/ack sau khi xử lý thành công theo semantics của broker.
- Ngừng tạo job định kỳ mới.
- Cho task đang chạy thời gian hoàn tất hoặc lưu checkpoint.
- Đóng client và connection pool sau khi công việc phụ thuộc đã kết thúc.

Không ack message trước khi nghiệp vụ hoàn tất chỉ để shutdown nhanh. Với consumer có xử lý lâu, thiết kế idempotency, retry và dead-letter để message có thể được xử lý lại an toàn khi process bị buộc dừng.

### 9.1. SmartLifecycle cho consumer bất đồng bộ

`SmartLifecycle.stop(Runnable)` phù hợp với thành phần cần dừng bất đồng bộ. Callback chỉ được gọi sau khi consumer đã pause, hoàn tất hoặc bàn giao công việc theo chính sách.

Interface điều khiển consumer trong ví dụ:

~~~java
import java.util.concurrent.CompletionStage;

public interface MessageConsumerControl {

    void start();

    CompletionStage<Void> pauseAndDrain();
}
~~~

~~~java
import java.util.concurrent.CompletionStage;
import org.springframework.context.SmartLifecycle;

public final class MessageConsumerLifecycle implements SmartLifecycle {

    private final MessageConsumerControl consumer;
    private volatile boolean running;

    public MessageConsumerLifecycle(MessageConsumerControl consumer) {
        this.consumer = consumer;
    }

    @Override
    public void start() {
        consumer.start();
        running = true;
    }

    @Override
    public void stop(Runnable callback) {
        CompletionStage<Void> stopped = consumer.pauseAndDrain();
        stopped.whenComplete((ignored, error) -> {
            running = false;
            if (error != null) {
                // Log the failure and rely on broker redelivery/idempotency policy.
            }
            callback.run();
        });
    }

    @Override
    public void stop() {
        stop(() -> { });
    }

    @Override
    public boolean isRunning() {
        return running;
    }

    @Override
    public boolean isAutoStartup() {
        return true;
    }

    @Override
    public int getPhase() {
        return SmartLifecycle.DEFAULT_PHASE - 100;
    }
}
~~~

`MessageConsumerControl` là interface minh họa do ứng dụng định nghĩa; implementation phải gọi callback đúng một lần khi drain kết thúc. Cấu hình phase của consumer để nó dừng trước các client mà nó cần dùng trong quá trình drain, và trước khi các client đó bị đóng.

### 9.2. Đóng tài nguyên theo thứ tự phụ thuộc

Nếu consumer cần database hoặc HTTP client để hoàn tất message, các client đó phải còn hoạt động cho tới khi consumer kết thúc. Với hai thành phần có quan hệ phụ thuộc, thành phần phụ thuộc nên được stop trước thành phần mà nó cần.

Spring `SmartLifecycle` stop theo thứ tự phase đảo ngược so với startup. Nếu A cần B hoạt động, B nên có phase thấp hơn A để A được stop trước B. Quan hệ `depends-on` tường minh cũng ảnh hưởng thứ tự lifecycle.

## 10. Idempotency, retry và tình huống lỗi

Shutdown có thể được yêu cầu nhiều lần: SIGTERM được gửi lặp, orchestrator retry, hoặc người vận hành gọi drain endpoint rồi sau đó process nhận signal. Các thao tác drain cần idempotent.

| Tình huống | Hành vi nên có |
| --- | --- |
| Đã ở trạng thái OUT_OF_SERVICE | Lặp lại yêu cầu không gây lỗi nghiêm trọng |
| Registry không truy cập được | Ghi lỗi, áp dụng timeout và chính sách tiếp tục/abort rõ ràng |
| Không thể hoàn tất request trong timeout | Dừng theo deadline; client cần retry an toàn |
| Consumer không drain kịp | Nack/rollback hoặc để broker redeliver; tránh ack sớm |
| Deregister thất bại | Ghi cảnh báo; dựa vào lease/health timeout như fallback |
| Process nhận SIGKILL | Không có cleanup hook; dựa vào lease expiry và cơ chế tự phục hồi |

Không coi `@PreDestroy` là nơi duy nhất để thực hiện drain dài. Khi Spring bắt đầu destroy bean, web server có thể đã ở pha graceful shutdown hoặc ngừng nhận request. Các thao tác cần có thời gian propagation nên bắt đầu từ control plane, preStop hoặc lifecycle phase phù hợp.

## 11. Kiểm thử shutdown và deregistration

Không nên chỉ kiểm tra rằng method shutdown được gọi. Test cần xác minh thứ tự hành động, callback lifecycle, trạng thái registry và hành vi khi một bước thất bại.

### 11.1. Kiểm tra RegistryDrainOperation

Ví dụ dùng Mockito để xác minh instance được đánh dấu out-of-service trước khi deregister:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.cloud.client.serviceregistry.Registration;
import org.springframework.cloud.client.serviceregistry.ServiceRegistry;

import static org.mockito.Mockito.inOrder;
import static org.mockito.Mockito.mock;

class RegistryDrainOperationTests {

    private static final class TestRegistration implements Registration {
    }

    @Test
    void marksOutOfServiceBeforeDeregistering() {
        ServiceRegistry<TestRegistration> registry =
                mock(ServiceRegistry.class);
        TestRegistration registration = new TestRegistration();

        RegistryDrainOperation<TestRegistration> operation =
                new RegistryDrainOperation<>(registry, registration);

        operation.markOutOfService();
        operation.deregister();

        var order = inOrder(registry);
        order.verify(registry)
                .setStatus(registration, "OUT_OF_SERVICE");
        order.verify(registry).deregister(registration);
    }
}
~~~

`TestRegistration` là implementation giả của `Registration` trong test. Trong dự án thật, có thể dùng registration type của provider hoặc một fake đơn giản.

### 11.2. Kiểm tra callback của SmartLifecycle

Với lifecycle bean có shutdown bất đồng bộ, kiểm tra callback chỉ được gọi sau khi thao tác drain hoàn tất:

~~~java
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.CompletableFuture;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

class MessageConsumerLifecycleTests {

    private static final class FakeMessageConsumerControl
            implements MessageConsumerControl {

        private boolean pauseRequested;

        @Override
        public void start() {
        }

        @Override
        public java.util.concurrent.CompletionStage<Void> pauseAndDrain() {
            pauseRequested = true;
            return CompletableFuture.completedFuture(null);
        }

        boolean pauseRequested() {
            return pauseRequested;
        }
    }

    @Test
    void invokesStopCallbackAfterConsumerDrain() {
        FakeMessageConsumerControl consumer =
                new FakeMessageConsumerControl();
        MessageConsumerLifecycle lifecycle =
                new MessageConsumerLifecycle(consumer);

        lifecycle.start();
        AtomicBoolean callbackCalled = new AtomicBoolean(false);

        lifecycle.stop(() -> callbackCalled.set(true));

        assertThat(consumer.pauseRequested()).isTrue();
        assertThat(callbackCalled).isTrue();
        assertThat(lifecycle.isRunning()).isFalse();
    }
}
~~~

Test này giả định fake consumer hoàn tất drain đồng bộ. Với consumer thực tế trả về future, dùng future có thể điều khiển trong test để xác minh callback chưa chạy trước khi future hoàn tất và chỉ chạy một lần sau đó.

### 11.3. Kiểm tra thứ tự phase

Spring Framework dừng `SmartLifecycle` theo phase giảm dần. Có thể viết test context nhỏ với các lifecycle fake ghi lại thứ tự `stop` và xác minh:

- Lifecycle đánh dấu registry có phase cao hơn web server graceful phase.
- Consumer dừng trước database/client mà consumer cần dùng.
- Auto-registration vẫn được phép deregister trong quá trình đóng context.

Không hard-code toàn bộ phase nội bộ của Spring Boot vào test của ứng dụng. Hãy kiểm tra quan hệ phase của những thành phần mà ứng dụng tự cấu hình và chạy integration test trên phiên bản Spring Boot thực tế.

### 11.4. Kiểm tra hành vi khi registry lỗi

Mô phỏng các lỗi:

- `setStatus` timeout hoặc ném exception.
- `deregister` thất bại do registry unavailable.
- `preStop` gọi drain endpoint không thành công.
- Consumer không hoàn tất trước timeout.

Xác minh log/metric có đủ thông tin, callback không bị bỏ quên, process vẫn tuân theo chính sách deadline và các message chưa ack có thể được redeliver.

## 12. Runbook vận hành khi deploy hoặc scale down

Một runbook triển khai nên có thể thực hiện lặp lại cho từng instance:

1. Chọn một replica cần thay thế và kiểm tra các replica còn lại đủ capacity.
2. Gọi drain operation hoặc preStop để chuyển readiness sang `REFUSING_TRAFFIC`.
3. Chuyển registration sang `OUT_OF_SERVICE` nếu provider hỗ trợ.
4. Kiểm tra trạng thái registry và readiness endpoint.
5. Chờ propagation window theo độ trễ cache/refresh của discovery client và load balancer.
6. Gửi `SIGTERM` hoặc để orchestrator tiếp tục termination.
7. Theo dõi log graceful shutdown, request đang chạy và consumer drain.
8. Xác minh registration đã bị deregister hoặc không còn được discovery trả về.
9. Xác minh process kết thúc trước `terminationGracePeriodSeconds`.
10. Tiếp tục với replica tiếp theo.

Không scale down toàn bộ replica cùng lúc nếu service không có đủ capacity dự phòng hoặc cần giữ quorum. Với stateful workload, cần kiểm tra leader election, partition ownership, distributed lock và checkpoint trước khi dừng instance.

## 13. Troubleshooting

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Client vẫn gọi instance đang dừng | Registry chưa nhận status mới hoặc client đang giữ cache cũ | Mark out-of-service sớm hơn và tăng propagation window theo số đo thực tế |
| Pod readiness đã fail nhưng Eureka vẫn báo UP | Kubernetes readiness và Eureka là hai cơ chế độc lập | Cập nhật cả readiness lẫn registry status |
| Request mới bị reset khi deploy | Server dừng trước khi traffic được drain hoặc timeout quá ngắn | Đưa instance ra khỏi traffic trước SIGTERM và bật graceful shutdown |
| Auto-deregister không chạy | Auto-registration bị tắt, lifecycle bean không được khởi tạo hoặc process bị SIGKILL | Kiểm tra `spring.cloud.service-registry.auto-registration.enabled`, log lifecycle và termination deadline |
| Eureka giữ instance sau khi process dừng | Unregister không thành công hoặc client tắt unregister-on-shutdown | Kiểm tra `eureka.client.should-unregister-on-shutdown` và log Eureka client |
| Kubernetes gửi SIGKILL | preStop cộng shutdown vượt grace period | Tăng ngân sách, rút ngắn công việc dừng hoặc tăng `terminationGracePeriodSeconds` |
| preStop không gọi được endpoint | Image thiếu curl, port/path sai hoặc endpoint yêu cầu auth | Kiểm tra command trong image và cấu hình management port/security |
| Consumer mất message | Ack trước khi xử lý xong hoặc không có retry/idempotency | Ack sau commit nghiệp vụ; thiết kế redelivery và deduplication |
| Shutdown chờ vô hạn | SmartLifecycle không gọi callback hoặc thao tác mạng không có timeout | Gọi callback đúng một lần và giới hạn timeout mọi thao tác I/O |
| Instance vẫn nhận traffic qua kết nối lâu dài | Persistent connection, streaming hoặc client cache | Drain connection/session và kiểm thử giao thức thực tế |
| Registry status không hiểu OUT_OF_SERVICE | Provider dùng tập status khác | Dùng trạng thái hoặc health-check mechanism riêng của provider |
| Shutdown hook chạy nhiều lần | Nhiều trigger hoặc signal lặp | Thiết kế thao tác idempotent và bảo vệ bằng trạng thái atomic |

### 13.1. Quy trình điều tra một lần shutdown lỗi

1. Xác định thời điểm orchestrator yêu cầu terminate và thời điểm gửi `SIGTERM`.
2. Kiểm tra `preStop` có chạy hết hay không.
3. Kiểm tra readiness đã chuyển sang `REFUSING_TRAFFIC` chưa.
4. Kiểm tra registry có nhận `OUT_OF_SERVICE` và deregister không.
5. Đối chiếu thời điểm cập nhật registry với request cuối cùng được gửi tới instance.
6. Kiểm tra log graceful shutdown và số request còn đang xử lý.
7. Kiểm tra consumer, scheduler và task bất đồng bộ có hoàn tất không.
8. So sánh thời gian thực tế với `timeout-per-shutdown-phase` và `terminationGracePeriodSeconds`.
9. Xác định có `SIGKILL`, timeout mạng hoặc callback lifecycle bị thiếu không.

## 14. Bài tập thực hành

### Bài 1 — Bật graceful shutdown

Cấu hình `server.shutdown: graceful` và `spring.lifecycle.timeout-per-shutdown-phase`. Tạo endpoint xử lý chậm, gửi `SIGTERM` và xác minh request đang chạy có thời gian hoàn tất.

### Bài 2 — Deregister khỏi service registry

Với Eureka, dùng `ServiceRegistry` hoặc endpoint Actuator để chuyển registration sang `OUT_OF_SERVICE`. Xác minh discovery client không còn chọn instance đó.

### Bài 3 — Phối hợp readiness và registry

Phát `AvailabilityChangeEvent` với `ReadinessState.REFUSING_TRAFFIC`, sau đó cập nhật registry. Quan sát hai trạng thái thay đổi và đo thời gian propagation.

### Bài 4 — SmartLifecycle

Viết lifecycle hook đánh dấu registry trước khi web server graceful shutdown. Kiểm tra phase, callback và hành vi khi registry ném exception.

### Bài 5 — Kubernetes preStop

Thêm `preStop` gọi endpoint drain và `terminationGracePeriodSeconds` đủ lớn. Xóa Pod và xác minh readiness, EndpointSlice, registry status và process termination.

### Bài 6 — Consumer drain

Tạo consumer có message xử lý kéo dài. Pause nhận message mới, hoàn tất message đang chạy, rồi đóng client. Kiểm tra message không bị mất khi process kết thúc.

### Bài 7 — Fault injection

Giả lập registry unavailable, consumer timeout và request kéo dài vượt shutdown timeout. Ghi lại trạng thái cuối và đề xuất ngân sách shutdown phù hợp.

**Tiêu chí hoàn thành:** bạn có thể drain một instance khỏi discovery và traffic trước khi dừng process, hoàn tất công việc đang chạy trong thời gian cho phép, và xác minh registration cùng tài nguyên đã được dọn dẹp.

## 15. Tổng kết

Shutdown an toàn trong Spring Cloud cần phối hợp service registry, readiness và vòng đời của Spring Boot. Trước khi gửi `SIGTERM`, hãy chuyển readiness sang `REFUSING_TRAFFIC`, cập nhật registration sang trạng thái không phục vụ nếu provider hỗ trợ và dành thời gian để registry/discovery/load balancer cập nhật.

Spring Boot graceful shutdown ngừng nhận request mới và cho request đang chạy thời gian hoàn tất theo timeout. Spring Cloud Commons auto-registration sẽ deregister registration khi lifecycle dừng; Eureka có `should-unregister-on-shutdown` để chủ động hủy đăng ký. `SmartLifecycle` giúp điều phối thứ tự dừng và hỗ trợ callback cho công việc bất đồng bộ. Kubernetes `preStop` có thể thực hiện bước drain trước `SIGTERM`, nhưng thời gian hook được tính trong `terminationGracePeriodSeconds`.

Đừng chỉ dựa vào một tín hiệu duy nhất. Readiness, registry status, HTTP graceful shutdown và consumer drain là các phần riêng của cùng một quy trình. Kiểm thử bằng tín hiệu dừng thật, theo dõi thời gian và bảo đảm mọi thao tác có timeout, idempotency cùng chính sách lỗi rõ ràng.

## Tài liệu tham khảo

- [Spring Boot 4.1.2 — Graceful Shutdown](https://docs.spring.io/spring-boot/reference/web/graceful-shutdown.html): graceful shutdown, từ chối request mới và timeout theo pha.
- [WebServerApplicationContext API](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/web/server/context/WebServerApplicationContext.html): phase graceful shutdown của embedded web server.
- [Spring Boot 4.1.2 — Actuator Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html): trạng thái readiness/liveness trong các pha shutdown và health probes.
- [Spring Boot 4.1.2 — Application Availability](https://docs.spring.io/spring-boot/reference/features/spring-application.html): `AvailabilityChangeEvent`, `ReadinessState` và `LivenessState`.
- [Spring Cloud Commons 5.0.4 — Common Abstractions](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html): `ServiceRegistry`, auto-registration, status endpoint và discovery health.
- [Spring Cloud Commons 5.0.4 — Configuration Properties](https://docs.spring.io/spring-cloud-commons/reference/configprops.html): auto-registration, management registration và Spring Cloud LoadBalancer cache TTL.
- [Spring Cloud Netflix 5.0.3 — Configuration Properties](https://docs.spring.io/spring-cloud-netflix/reference/configprops.html): `eureka.client.should-unregister-on-shutdown`.
- [AbstractAutoServiceRegistration source](https://github.com/spring-cloud/spring-cloud-commons/blob/main/spring-cloud-commons/src/main/java/org/springframework/cloud/client/serviceregistry/AbstractAutoServiceRegistration.java): lifecycle phase, stop và deregistration.
- [ServiceRegistry source](https://github.com/spring-cloud/spring-cloud-commons/blob/main/spring-cloud-commons/src/main/java/org/springframework/cloud/client/serviceregistry/ServiceRegistry.java): hợp đồng register, deregister, setStatus và close.
- [Spring Framework 6.1 — SmartLifecycle](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/SmartLifecycle.html): thứ tự phase và callback dừng bất đồng bộ.
- [Kubernetes — Termination of Pods](https://kubernetes.io/docs/concepts/workloads/pods/pod-termination/): preStop, SIGTERM, termination grace period và SIGKILL.
- [Kubernetes — Explore Pod and Endpoint Termination Flow](https://kubernetes.io/docs/tutorials/services/pods-and-endpoint-termination-flow/): EndpointSlice và traffic draining khi Pod terminate.

Kiểm tra release train Spring Cloud, phiên bản Spring Boot, provider registry và runtime platform trước khi áp dụng. Trạng thái registry, phase lifecycle và hành vi graceful shutdown có thể khác nhau giữa các thế hệ phiên bản.
