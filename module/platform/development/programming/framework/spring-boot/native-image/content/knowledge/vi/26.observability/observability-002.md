# Actuator, health và kiểm chứng ứng dụng sẵn sàng nhận yêu cầu

## 1. Vì sao cần health endpoint trong Spring Boot Native Image?

Một ứng dụng có thể đã tạo được native executable và tiến trình cũng đang chạy, nhưng điều đó chưa chứng minh ứng dụng có thể nhận request. Spring context có thể chưa hoàn tất startup, HTTP server chưa mở cổng, migration chưa xong, cache chưa warm-up hoặc một dependency thiết yếu chưa sẵn sàng.

Spring Boot Actuator cung cấp endpoint `health` để báo trạng thái ứng dụng và các thành phần mà ứng dụng kiểm tra. Spring Boot còn quản lý hai trạng thái availability riêng:

- **Liveness:** tiến trình và trạng thái nội bộ còn có thể tiếp tục hoạt động hay cần được khởi động lại.
- **Readiness:** instance đã sẵn sàng nhận traffic hay cần tạm thời ngừng nhận request.

Hai trạng thái này đặc biệt hữu ích khi chạy Spring Boot Native Image trong container hoặc Kubernetes. Native Image có thể rút ngắn startup time, nhưng readiness vẫn phải phản ánh đúng thời điểm ứng dụng hoàn tất công việc khởi động và có thể phục vụ request.

Sau bài học, bạn có thể:

- Bật Actuator và kiểm tra endpoint `/actuator/health`.
- Phân biệt liveness, readiness và startup probe.
- Cấu hình health groups và custom `HealthIndicator`.
- Điều khiển readiness trong quá trình warm-up hoặc bảo trì.
- Cấu hình Kubernetes probes trên main server port.
- Bảo vệ health details và kiểm thử các endpoint trên native executable/container.

## 2. Thêm Spring Boot Actuator

### 2.1. Dependency

Với Maven, thêm starter vào ứng dụng:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
```

Với Gradle:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
```

Hãy dùng version do Spring Boot plugin hoặc BOM quản lý. Spring Boot 4.x có thay đổi một số package và module bên trong Actuator so với 3.x, vì vậy không nên sao chép import của `HealthIndicator` từ một major version khác.

### 2.2. Endpoint health mặc định

Sau khi ứng dụng khởi động, gửi request:

```bash
curl -i http://localhost:8080/actuator/health
```

Một response tối giản thường có dạng:

```http
HTTP/1.1 200 OK
Content-Type: application/vnd.spring-boot.actuator.v3+json

{"status":"UP"}
```

`UP` có nghĩa các health contributor được đưa vào lần kiểm tra tổng thể đang báo trạng thái tốt. Nếu một contributor báo `DOWN` hoặc `OUT_OF_SERVICE`, HTTP status mặc định thường chuyển thành `503 Service Unavailable`.

Theo mặc định, Actuator chỉ expose endpoint `health` qua HTTP. Những endpoint khác như `env`, `beans`, `configprops`, `loggers` hoặc `heapdump` có thể chứa thông tin nhạy cảm và không nên được mở rộng tùy tiện.

Nếu cần expose thêm `info`, cấu hình rõ danh sách:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info
```

### 2.3. Cấu trúc health response

Health endpoint tổng hợp trạng thái từ nhiều `HealthContributor`, ví dụ database, disk space, Redis, RabbitMQ hoặc custom indicator.

```json
{
  "status": "UP",
  "components": {
    "db": {
      "status": "UP"
    },
    "diskSpace": {
      "status": "UP"
    },
    "ping": {
      "status": "UP"
    }
  }
}
```

Các component và `details` xuất hiện hay không phụ thuộc cấu hình `management.endpoint.health.show-components` và `management.endpoint.health.show-details`. Mặc định details không được hiển thị công khai. Ví dụ dưới đây minh họa response khi người gọi được phép xem component:

Có thể truy vấn riêng một component nếu component đó được phép hiển thị:

```bash
curl -i http://localhost:8080/actuator/health/db
curl -i http://localhost:8080/actuator/health/diskSpace
```

Tên component thường dựa trên bean name của contributor. Khi kiểm tra response, hãy phân biệt trạng thái tổng thể với trạng thái của một component riêng lẻ.

## 3. Liveness, readiness và startup probe

### 3.1. Liveness: instance còn có thể tiếp tục chạy không?

Liveness phản ánh trạng thái nội bộ của ứng dụng. Nếu liveness chuyển sang `BROKEN`, nền tảng triển khai có thể restart container để phục hồi instance.

Một liveness probe tốt thường chỉ kiểm tra những điều kiện nội bộ cần thiết để tiến trình tiếp tục hoạt động. Không đưa database, Redis, message broker hoặc API bên ngoài vào liveness. Nếu database dùng chung gặp sự cố, việc tất cả instance đồng loạt fail liveness có thể tạo restart storm và làm sự cố lan rộng.

Spring Boot theo dõi trạng thái liveness qua `ApplicationAvailability`. Khi `ApplicationContext` đã refresh thành công, ứng dụng được xem là live. Nếu một thành phần nội bộ bị hỏng không thể tự phục hồi, ứng dụng có thể phát `AvailabilityChangeEvent` để chuyển sang `LivenessState.BROKEN`.

### 3.2. Readiness: instance có thể nhận request chưa?

Readiness cho biết nền tảng triển khai có nên định tuyến traffic tới instance hay không. Khi readiness là `REFUSING_TRAFFIC`, Kubernetes loại instance khỏi các endpoint nhận traffic; khi là `ACCEPTING_TRAFFIC`, instance có thể nhận request.

Spring Boot mặc định chuyển readiness sang `ACCEPTING_TRAFFIC` sau khi application context đã khởi tạo và các `ApplicationRunner`/`CommandLineRunner` hoàn tất. Đây là vị trí phù hợp để thực hiện công việc startup cần xong trước khi nhận request.

Ví dụ: nếu ứng dụng cần tải danh mục sản phẩm hoặc warm-up cache trước khi phục vụ request, có thể giữ readiness ở trạng thái từ chối traffic trong suốt quá trình đó.

### 3.3. Startup probe: cho ứng dụng thêm thời gian khởi động

Kubernetes `startupProbe` bảo vệ ứng dụng trong giai đoạn khởi động. Khi startup probe chưa thành công, Kubernetes chưa áp dụng liveness/readiness failure threshold theo cách thông thường. Điều này hữu ích với ứng dụng có startup task dài, kể cả khi native executable khởi động nhanh hơn JVM.

Ba probe có vai trò khác nhau:

| Probe | Câu hỏi | Khi thất bại |
|---|---|---|
| Startup | Ứng dụng đã hoàn tất giai đoạn khởi động cơ bản chưa? | Kubernetes tiếp tục chờ trong giới hạn startup probe; hết ngưỡng thì restart |
| Liveness | Instance còn có thể tiếp tục hoạt động không? | Kubernetes restart container |
| Readiness | Instance đã có thể nhận traffic chưa? | Kubernetes tạm ngừng route traffic tới instance |

### 3.4. Trạng thái theo vòng đời Spring Boot

Các trạng thái thay đổi theo vòng đời ứng dụng:

| Giai đoạn | Liveness | Readiness | HTTP server |
|---|---|---|---|
| Starting | `BROKEN` | `REFUSING_TRAFFIC` | Chưa mở |
| Context đã refresh | `CORRECT` | `REFUSING_TRAFFIC` | Chưa nhận request mới |
| Runners hoàn tất, ứng dụng ready | `CORRECT` | `ACCEPTING_TRAFFIC` | Nhận request |
| Graceful shutdown | `CORRECT` | `REFUSING_TRAFFIC` | Ngừng nhận request mới, xử lý request đang chạy nếu graceful shutdown bật |
| Shutdown hoàn tất | Không còn trạng thái | Không còn trạng thái | Đã đóng |

Vì thế, không nên dùng `/actuator/health` tổng thể thay cho readiness probe mà chưa xem các contributor đang được tổng hợp. Health tổng thể có thể báo `DOWN` do một dịch vụ phụ trợ trong khi instance vẫn còn sống và vẫn có thể phục vụ một phần request.

## 4. Bật health groups cho liveness và readiness

### 4.1. Cấu hình tường minh

Spring Boot có thể tự bật Kubernetes probes khi nhận diện môi trường Kubernetes. Giá trị mặc định của `management.endpoint.health.probes.enabled` đã thay đổi giữa các phiên bản Spring Boot: một số bản 3.x mặc định tắt ngoài Kubernetes, trong khi dòng 4.x mới mặc định bật. Để cấu hình nhất quán giữa các môi trường, có thể bật rõ ràng:

```yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
```

Sau khi bật, hai health groups được expose dưới health endpoint:

```bash
curl -i http://localhost:8080/actuator/health/liveness
curl -i http://localhost:8080/actuator/health/readiness
```

Mặc định, liveness group chứa `livenessState` và readiness group chứa `readinessState`. Spring Boot không tự thêm tất cả external health indicators vào hai group này.

### 4.2. Vì sao không nên gộp mọi indicator vào readiness?

Một database dùng chung có thể bị lỗi trong khi ứng dụng vẫn có thể xử lý request đọc cache hoặc trả thông báo tạm thời. Nếu đưa database vào readiness của mọi instance, toàn bộ instance có thể bị loại khỏi service cùng lúc.

Chỉ thêm external dependency vào readiness khi dependency đó thật sự cần thiết để instance nhận loại traffic đang phục vụ. Nếu ứng dụng có fallback hoặc circuit breaker, việc một dependency phụ trợ không hoạt động chưa chắc phải khiến toàn bộ instance ngừng nhận request.

Không đưa external dependency vào liveness. Liveness thất bại dẫn tới restart; restart không thể sửa một database hoặc API bên ngoài đang lỗi.

### 4.3. Thêm indicator vào readiness group

Giả sử ứng dụng cần inventory gateway hoạt động trước khi nhận request tạo đơn hàng:

```yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
      group:
        readiness:
          include: readinessState,inventoryGateway
```

`inventoryGateway` là tên health contributor. Khi thêm contributor vào group, hãy bảo đảm bean thực sự tồn tại trong ApplicationContext. Spring Boot mặc định kiểm tra membership của health group khi startup; viết sai tên contributor có thể làm ứng dụng khởi động thất bại.

## 5. Viết custom `HealthIndicator`

### 5.1. Ví dụ kiểm tra một dependency bắt buộc

Custom indicator nên kiểm tra một khả năng cụ thể với timeout ngắn và trả trạng thái rõ ràng:

```java
package com.example.orders.health;

import java.time.Duration;

import org.springframework.boot.health.contributor.Health;
import org.springframework.boot.health.contributor.HealthIndicator;
import org.springframework.stereotype.Component;

@Component("inventoryGateway")
public class InventoryGatewayHealthIndicator implements HealthIndicator {

    private final InventoryGatewayClient client;

    public InventoryGatewayHealthIndicator(InventoryGatewayClient client) {
        this.client = client;
    }

    @Override
    public Health health() {
        try {
            client.ping(Duration.ofMillis(300));
            return Health.up().build();
        }
        catch (Exception ex) {
            return Health.down()
                    .withDetail("dependency", "inventory-gateway")
                    .build();
        }
    }
}
```

Ví dụ dùng API của Spring Boot 4.x. Với Spring Boot 3.x, import `Health` và `HealthIndicator` từ `org.springframework.boot.actuate.health` thay cho `org.springframework.boot.health.contributor`.

`InventoryGatewayClient.ping(...)` là API minh họa của client. Trong ứng dụng thật, hãy bảo đảm timeout của HTTP client/database driver được cấu hình thật sự; chỉ truyền một giá trị timeout vào method nhưng không áp dụng timeout ở tầng transport sẽ không bảo vệ được probe.

### 5.2. Đừng biến probe thành một request nghiệp vụ nặng

Health indicator được gọi bởi monitoring system và kubelet theo chu kỳ. Một indicator nên:

- Thực hiện kiểm tra nhẹ, có timeout ngắn.
- Không tải toàn bộ dữ liệu hoặc chạy truy vấn tốn kém.
- Không thay đổi trạng thái nghiệp vụ.
- Không thực hiện thao tác ghi dữ liệu chỉ để chứng minh hệ thống hoạt động.
- Không ghi log lỗi lặp lại ở mức quá cao khi dependency đang gặp sự cố.
- Không trả token, URL nội bộ, SQL, stack trace hoặc thông tin xác thực trong `details` công khai.

Nếu probe cần kiểm tra nhiều dependency, cân nhắc dùng tín hiệu đã được cập nhật định kỳ hoặc cache kết quả có TTL ngắn. TTL quá dài có thể khiến probe tiếp tục báo `UP` dù dependency vừa hỏng; TTL bằng 0 có thể làm mỗi lần probe tạo thêm request tới dependency. Chọn theo tần suất probe và khả năng chịu lỗi của ứng dụng.

### 5.3. Reactive health indicator

Với ứng dụng WebFlux hoặc dependency có API reactive, nên dùng `ReactiveHealthIndicator` để kiểm tra không chặn event loop. Tránh gọi blocking JDBC hoặc `Thread.sleep` trong reactive health check. Nếu phải dùng một client blocking, thực hiện ở scheduler phù hợp và giới hạn thời gian chờ.

## 6. Điều khiển readiness trong startup và warm-up

### 6.1. Dùng `ApplicationRunner` cho công việc startup đồng bộ

Spring Boot chỉ chuyển sang `ACCEPTING_TRAFFIC` sau khi `ApplicationRunner` và `CommandLineRunner` hoàn tất. Nếu ứng dụng cần tải cấu hình nghiệp vụ hoặc warm-up dữ liệu trước khi nhận traffic, đặt công việc đó trong runner thay vì khởi động một thread nền không được theo dõi.

```java
package com.example.orders.startup;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.stereotype.Component;

@Component
public class OrderReferenceDataLoader implements ApplicationRunner {

    private final OrderReferenceDataService service;

    public OrderReferenceDataLoader(OrderReferenceDataService service) {
        this.service = service;
    }

    @Override
    public void run(ApplicationArguments args) {
        service.loadRequiredReferenceData();
    }
}
```

Nếu runner thất bại và exception không được xử lý, Spring Boot có thể kết thúc quá trình startup. Đây thường là hành vi đúng nếu ứng dụng không thể phục vụ request khi thiếu dữ liệu bắt buộc.

### 6.2. Giữ readiness ở trạng thái từ chối traffic trong warm-up bất đồng bộ

Nếu warm-up cần tiếp tục sau khi application context đã ready, có thể phát `AvailabilityChangeEvent` để điều khiển trạng thái:

```java
package com.example.orders.startup;

import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Component;

@Component
public class OrderWarmupCoordinator {

    private final ApplicationEventPublisher events;

    public OrderWarmupCoordinator(ApplicationEventPublisher events) {
        this.events = events;
    }

    public void warmupStarted() {
        AvailabilityChangeEvent.publish(
                events, this, ReadinessState.REFUSING_TRAFFIC);
    }

    public void warmupCompleted() {
        AvailabilityChangeEvent.publish(
                events, this, ReadinessState.ACCEPTING_TRAFFIC);
    }
}
```

Chỉ gọi `warmupCompleted()` sau khi dữ liệu thực sự sẵn sàng. Nếu warm-up thất bại, giữ trạng thái từ chối traffic và xử lý lỗi theo chính sách retry hoặc fail-fast của ứng dụng.

### 6.3. Liveness cho lỗi nội bộ không thể phục hồi

Trong trường hợp một thành phần nội bộ bị hỏng đến mức instance không thể tiếp tục phục vụ, có thể phát trạng thái liveness:

```java
package com.example.orders.health;

import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.LivenessState;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Component;

@Component
public class LocalCacheVerifier {

    private final ApplicationEventPublisher eventPublisher;

    public LocalCacheVerifier(ApplicationEventPublisher eventPublisher) {
        this.eventPublisher = eventPublisher;
    }

    public void checkLocalCache() {
        try {
            // Kiểm tra invariant nội bộ của cache.
        }
        catch (CacheCompletelyBrokenException ex) {
            AvailabilityChangeEvent.publish(
                    eventPublisher, this, LivenessState.BROKEN);
        }
    }
}
```

Chỉ dùng `BROKEN` khi restart instance là biện pháp phục hồi hợp lý. Không dùng nó để phản ánh database tạm thời mất kết nối, remote API timeout hoặc một lỗi nghiệp vụ có thể retry.

## 7. Health group và endpoint path trên main server port

### 7.1. Vì sao management port riêng có thể tạo false positive?

Một ứng dụng có thể expose Actuator trên port riêng:

```yaml
management:
  server:
    port: 8081
```

Khi đó, kubelet có thể gọi health endpoint trên port `8081` và nhận `UP`, trong khi HTTP server chính ở port `8080` không nhận được kết nối. Management context có thể sử dụng web infrastructure khác với main application context, nên probe trên management port chưa chắc chứng minh cổng phục vụ request hoạt động.

### 7.2. Thêm `/livez` và `/readyz` trên main port

Spring Boot hỗ trợ thêm path cho hai health groups trên main server port:

```yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
        add-additional-paths: true
```

Khi đó:

| Endpoint | Port | Ý nghĩa |
|---|---|---|
| `/actuator/health` | Management hoặc main port theo cấu hình | Health tổng thể |
| `/actuator/health/liveness` | Management hoặc main port | Liveness group |
| `/actuator/health/readiness` | Management hoặc main port | Readiness group |
| `/livez` | Main server port | Liveness group bổ sung |
| `/readyz` | Main server port | Readiness group bổ sung |

Nếu không dùng management port riêng, hai endpoint Actuator group thường đã đủ. Nếu management port riêng được bảo vệ trong mạng nội bộ, `/livez` và `/readyz` trên main port giúp kiểm tra cả đường HTTP chính.

### 7.3. Tùy chỉnh additional path

Có thể cấu hình đường dẫn bổ sung cho từng health group:

```yaml
management:
  endpoint:
    health:
      group:
        liveness:
          additional-path: "server:/health/live"
        readiness:
          additional-path: "server:/health/ready"
```

Prefix `server:` chỉ main server port; `management:` chỉ management port nếu đã cấu hình. Khi tự đặt path, cập nhật đồng thời cấu hình probe của nền tảng triển khai.

## 8. Cấu hình Kubernetes probes

### 8.1. Ví dụ Deployment

Giả sử native executable lắng nghe cổng `8080` và dùng `/livez`, `/readyz` trên main port:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: order-service
spec:
  replicas: 3
  selector:
    matchLabels:
      app: order-service
  template:
    metadata:
      labels:
        app: order-service
    spec:
      containers:
        - name: order-service
          image: example/order-service:native
          ports:
            - name: http
              containerPort: 8080
          startupProbe:
            httpGet:
              path: /livez
              port: http
            periodSeconds: 5
            timeoutSeconds: 2
            failureThreshold: 30
          livenessProbe:
            httpGet:
              path: /livez
              port: http
            periodSeconds: 10
            timeoutSeconds: 2
            failureThreshold: 3
          readinessProbe:
            httpGet:
              path: /readyz
              port: http
            periodSeconds: 5
            timeoutSeconds: 2
            failureThreshold: 3
```

Các giá trị chỉ là ví dụ. `startupProbe` cho phép tối đa khoảng 150 giây với `periodSeconds: 5` và `failureThreshold: 30` trước khi container bị xem là startup thất bại. Hãy đặt ngưỡng dựa trên thời gian startup đo được trong môi trường triển khai, không chỉ dựa vào thời gian trên máy phát triển.

### 8.2. Chọn endpoint theo cổng

Nếu Actuator chỉ nằm trên management port, cấu hình probe dùng port management. Nếu đã bật additional paths, ưu tiên `/livez` và `/readyz` trên main server port để xác nhận HTTP server phục vụ traffic cũng đang hoạt động.

Không dùng cùng một endpoint readiness cho liveness nếu endpoint đó có thể chuyển `DOWN` do dependency bên ngoài. Khi database ngừng hoạt động, readiness có thể chuyển sang fail theo chính sách ứng dụng, nhưng liveness nên tiếp tục `UP` để tránh restart hàng loạt.

## 9. Bảo mật Actuator health

### 9.1. Giữ health details ở chế độ an toàn

Mặc định, Spring Boot không hiển thị health details cho request công khai. Có thể cấu hình rõ:

```yaml
management:
  endpoint:
    health:
      show-details: when-authorized
      show-components: when-authorized
      roles: OPS
```

Chỉ người dùng có role `OPS` mới xem được chi tiết. Không đặt `show-details: always` trên endpoint có thể truy cập từ mạng công cộng nếu details có tên host, database, cluster, exception hoặc thông tin nội bộ.

### 9.2. Cho phép kubelet gọi probe

Nếu ứng dụng dùng Spring Security và tự khai báo `SecurityFilterChain`, cấu hình bảo mật mặc định của Actuator có thể không còn áp dụng. Cần cho phép probe endpoint theo đúng kiến trúc mạng và port đang dùng.

Ví dụ rule cho probe path trên main server port:

```java
http.authorizeHttpRequests(authorize -> authorize
        .requestMatchers("/livez", "/readyz", "/actuator/health/**").permitAll()
        .anyRequest().authenticated());
```

Đây là một phần của cấu hình `SecurityFilterChain`; các endpoint khác vẫn cần quy tắc bảo vệ riêng. Nếu management server có port/network riêng, kiểm tra security chain áp dụng cho management context và đảm bảo chỉ kubelet/monitoring được truy cập.

## 10. Spring AOT và Native Image cần kiểm tra điều gì?

### 10.1. Actuator và health indicators là Spring beans

Spring AOT phân tích `ApplicationContext` ở build time và sinh mã khởi tạo cùng runtime hints cần thiết. Các health indicators do Spring Boot auto-configure và custom indicators được khai báo bằng `@Component` hoặc `@Bean` thông thường có thể được AOT phát hiện.

Với một custom `HealthIndicator` tĩnh, thông thường không cần tự viết reflection hints chỉ để gọi `health()`. Hãy bổ sung hints nếu phần implementation hoặc thư viện bên trong thực sự dùng reflection, resource loading, serialization, JNI hoặc proxy động mà AOT không suy ra được.

### 10.2. Điều kiện cấu hình được đánh giá ở build time

Nếu custom health indicator được bật bằng `@Profile` hoặc `@ConditionalOnProperty`, điều kiện đó có thể được đánh giá khi Spring AOT chạy. Profile/thuộc tính cần cho native artifact phải được cung cấp trong AOT build. Không nên kỳ vọng bật một profile khác khi chạy executable sẽ tạo thêm bean đã bị loại khỏi bean graph lúc build.

### 10.3. Kiểm tra cả native executable lẫn container

Sau khi build native image, chạy trực tiếp executable và kiểm tra các endpoint health. Sau đó chạy container image với cùng port, environment variables, security rules và database/network như môi trường triển khai.

Các điểm cần xác nhận:

- Actuator health endpoint được expose và trả HTTP response.
- Liveness chuyển `UP` sau khi context refresh.
- Readiness chỉ chuyển `UP` sau khi runners và warm-up hoàn tất.
- Custom health indicator xuất hiện trong group đã cấu hình.
- Health indicator có timeout và không làm probe treo.
- Additional paths `/livez`, `/readyz` hoạt động trên main server port nếu dùng management port riêng.
- Probe vẫn hoạt động trong giai đoạn graceful shutdown theo hành vi mong đợi.
- Không có metadata hoặc thư viện native bị thiếu khi chạy native executable.

### 10.4. Các lệnh kiểm chứng thủ công

```bash
# Health tổng thể
curl -i http://localhost:8080/actuator/health

# Hai probe groups
curl -i http://localhost:8080/actuator/health/liveness
curl -i http://localhost:8080/actuator/health/readiness

# Additional paths trên main server port
curl -i http://localhost:8080/livez
curl -i http://localhost:8080/readyz
```

Chạy các lệnh khi ứng dụng đang startup, sau khi startup, khi dependency quan trọng bị ngắt, trong quá trình warm-up và khi shutdown. Chỉ kiểm tra một lần sau startup sẽ không bao phủ các trạng thái lifecycle quan trọng.

## 11. Kiểm thử tự động

### 11.1. Test custom HealthIndicator

Test riêng indicator để kiểm tra trạng thái `UP` và `DOWN` mà không cần build native mỗi lần:

```java
package com.example.orders.health;

import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.boot.health.contributor.Health;
import org.springframework.boot.health.contributor.Status;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.doThrow;

@ExtendWith(MockitoExtension.class)
class InventoryGatewayHealthIndicatorTests {

    @Mock
    InventoryGatewayClient client;

    @InjectMocks
    InventoryGatewayHealthIndicator indicator;

    @Test
    void reportsDownWhenInventoryGatewayIsUnavailable() {
        doThrow(new IllegalStateException("unavailable"))
                .when(client).ping(any(Duration.class));

        Health health = indicator.health();

        assertThat(health.getStatus()).isEqualTo(Status.DOWN);
    }
}
```

Đây là unit test cho logic indicator. Nó không chứng minh Actuator endpoint hoặc security filter đã expose đúng path.

### 11.2. Test HTTP health endpoint

Với Spring MVC, có thể dùng `MockMvc` để xác nhận HTTP status và JSON response:

```java
package com.example.orders;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class OrderHealthEndpointTests {

    @Autowired
    MockMvc mockMvc;

    @Test
    void exposesReadinessProbe() throws Exception {
        mockMvc.perform(get("/actuator/health/readiness"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("UP"));
    }
}
```

Test này cần context đã hoàn tất startup và readiness đang `ACCEPTING_TRAFFIC`. Nếu test dùng warm-up hoặc thay đổi availability state, thiết lập trạng thái mong muốn trước khi assert.

### 11.3. Test readiness transitions

Kiểm tra ít nhất các chuyển trạng thái sau:

1. Trước khi warm-up hoàn tất: `/readyz` trả trạng thái không sẵn sàng.
2. Sau khi warm-up hoàn tất: `/readyz` trả `UP`.
3. Khi dependency bắt buộc của instance lỗi: readiness group chuyển sang trạng thái fail theo policy.
4. Khi dependency phụ trợ không thiết yếu lỗi: readiness vẫn `UP` nếu ứng dụng có fallback.
5. Khi shutdown bắt đầu: readiness ngừng nhận traffic mới.

### 11.4. Native integration test

Giữ phần lớn unit/integration tests trên JVM để feedback nhanh. Chọn một số test quan trọng để chạy trên native executable hoặc native test image, nhất là:

- Actuator endpoint mapping và JSON serialization.
- Custom `HealthIndicator` phụ thuộc thư viện có reflection/native integration.
- Security rules cho probe endpoints.
- Application availability events và warm-up lifecycle.
- Endpoint additional path trên main server port.

Native test hoặc smoke test sau khi build image xác nhận hành vi trong executable cuối cùng. JVM test không thể phát hiện mọi lỗi metadata hoặc khác biệt runtime của Native Image.

## 12. Lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| `/actuator/health` trả 404 | Thiếu Actuator dependency, web exposure hoặc base path đã đổi | Thêm starter, kiểm tra `management.endpoints.web.base-path` và exposure |
| `/actuator/health/readiness` trả 404 | Probes chưa được bật hoặc group không được tạo | Đặt `management.endpoint.health.probes.enabled=true` |
| `/readyz` trả 404 nhưng `/actuator/health/readiness` hoạt động | Chưa bật additional paths | Đặt `add-additional-paths=true` và kiểm tra main server port |
| Readiness `UP` quá sớm | Warm-up chạy nền sau khi runners hoàn tất nhưng không điều khiển availability | Dùng runner đồng bộ hoặc phát `REFUSING_TRAFFIC` đến khi warm-up xong |
| Liveness `DOWN` khi database lỗi | Đã đưa DB/external check vào liveness | Chỉ dùng trạng thái nội bộ trong liveness; chuyển dependency phù hợp sang readiness |
| Tất cả replica bị loại khỏi service khi một API dùng chung lỗi | Readiness phụ thuộc external system dùng chung | Đánh giá fallback/circuit breaker và chỉ đưa dependency thật sự bắt buộc vào readiness |
| Probe thành công nhưng API chính không nhận request | Actuator chạy trên management port riêng | Dùng additional path trên main server port hoặc probe trực tiếp main port |
| Health endpoint trả 401/403 | Spring Security chặn kubelet hoặc custom filter chain không permit path | Cho phép đúng probe paths và giới hạn truy cập bằng mạng/port phù hợp |
| Response để lộ host hoặc exception | `show-details=always` hoặc custom details quá chi tiết | Dùng `when-authorized`/`never`, loại bỏ secret và thông tin nhạy cảm |
| Health check treo hoặc chậm | Indicator gọi network/database không timeout | Đặt timeout ở client và kiểm tra log slow indicator |
| Custom indicator không xuất hiện trong native image | Bean bị điều kiện AOT loại bỏ hoặc không được khai báo trong bean graph | Kiểm tra profile/property tại AOT build và bean registration |
| Health group làm ứng dụng fail startup | `include` chứa tên contributor không tồn tại | Kiểm tra bean name và membership; giữ validation bật để phát hiện lỗi cấu hình |

## 13. Bài thực hành: kiểm chứng order-service sẵn sàng nhận request

**Bối cảnh:** `order-service` được build thành GraalVM Native Image và triển khai thành ba replica trên Kubernetes. Dịch vụ cần warm-up dữ liệu tham chiếu và kiểm tra inventory gateway trước khi nhận request tạo đơn hàng.

### Bước 1 — Thêm Actuator

Thêm `spring-boot-starter-actuator`, build ứng dụng và xác nhận `/actuator/health` trả response.

### Bước 2 — Bật liveness/readiness probes

Cấu hình:

```yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
        add-additional-paths: true
      group:
        readiness:
          include: readinessState,inventoryGateway
```

### Bước 3 — Tạo custom indicator

Tạo `InventoryGatewayHealthIndicator` với timeout ngắn, đăng ký bean name `inventoryGateway`, và test cả trạng thái `UP` lẫn `DOWN`.

### Bước 4 — Điều khiển warm-up

Thực hiện warm-up trong `ApplicationRunner` nếu công việc cần hoàn tất trước startup readiness. Nếu warm-up chạy bất đồng bộ, phát `ReadinessState.REFUSING_TRAFFIC` khi bắt đầu và `ACCEPTING_TRAFFIC` khi hoàn tất.

### Bước 5 — Cấu hình Kubernetes

Thêm `startupProbe`, `livenessProbe` và `readinessProbe` trỏ tới `/livez` và `/readyz` trên cổng HTTP chính. Đặt `failureThreshold`, `periodSeconds`, `timeoutSeconds` theo thời gian startup và độ trễ đo được.

### Bước 6 — Build và kiểm thử native

Build native executable/container image. Chạy thử trên database/inventory gateway test environment. Kiểm tra startup, warm-up, dependency outage, readiness transition và graceful shutdown.

### Phiếu kết quả

| Hạng mục | Kết quả cần ghi |
|---|---|
| Spring Boot version | _(ghi)_ |
| Native build tool/version | _(ghi)_ |
| Actuator health endpoint | PASS/FAIL |
| Liveness group | PASS/FAIL |
| Readiness group | PASS/FAIL |
| Custom indicator | PASS/FAIL |
| Main-port additional paths | PASS/FAIL |
| Security cho kubelet probe | PASS/FAIL |
| Native executable/container | PASS/FAIL |
| Readiness sau warm-up | PASS/FAIL |
| Readiness khi dependency lỗi | PASS/FAIL |
| Graceful shutdown | PASS/FAIL |

## 14. Ghi nhớ

Actuator health endpoint cho biết tình trạng các thành phần; liveness và readiness phục vụ hai quyết định vận hành khác nhau. Liveness trả lời instance có cần restart không, readiness trả lời có nên route traffic tới instance không. Startup probe bảo vệ ứng dụng trong giai đoạn khởi động.

Với Spring Boot Native Image, Actuator và custom health indicators được khai báo như Spring beans có thể được Spring AOT xử lý. Hãy kiểm tra các điều kiện/profile đã được chốt khi build, bảo đảm probe hoạt động trên đúng cổng HTTP, và chạy smoke/integration tests trên native executable/container. Không đưa dependency bên ngoài vào liveness, chỉ đưa dependency thật sự bắt buộc vào readiness, và giữ health details ở chế độ an toàn.

### Tài liệu tham khảo chính thức

- [Spring Boot — Actuator Endpoints and Health Information](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html)
- [Spring Boot — Monitoring and Management over HTTP](https://docs.spring.io/spring-boot/reference/actuator/monitoring.html)
- [Spring Boot — Application Availability](https://docs.spring.io/spring-boot/reference/features/spring-application.html)
- [Spring Boot 4.2 — HealthIndicator API](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/health/contributor/HealthIndicator.html)
- [Spring Boot 4.2 — ApplicationAvailability API](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/availability/ApplicationAvailability.html)
- [Spring Boot — Testing GraalVM Native Images](https://docs.spring.io/spring-boot/how-to/native-image/testing-native-applications.html)
- [Spring Boot — Ahead-of-Time Processing](https://docs.spring.io/spring-boot/maven-plugin/aot.html)
- [Kubernetes — Configure Liveness, Readiness and Startup Probes](https://kubernetes.io/docs/concepts/configuration/liveness-readiness-startup-probes/)
