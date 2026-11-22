# Health check, readiness và phân biệt với API nghiệp vụ

Một REST API có thể trả `200 OK` ở `/actuator/health` nhưng vẫn khiến khách hàng không đặt được đơn. Ngược lại, endpoint `GET /v1/orders/khong-ton-tai` trả `404 Not Found` không có nghĩa instance phải khởi động lại. Trong hệ thống nhiều instance, nhầm lẫn giữa **ứng dụng còn sống**, **ứng dụng sẵn sàng nhận traffic** và **một thao tác nghiệp vụ thành công** có thể gây downtime, vòng lặp restart, mất request và cảnh báo sai.

Bài học thuộc chương **Triển khai và vận hành** của module `INTEGRATION_API_REST`. Ta sẽ thiết kế health checks cho dịch vụ REST Java/Spring, phân biệt **liveness**, **readiness** và **startup**; cấu hình Spring Boot Actuator và Kubernetes; quyết định cách kiểm tra dependencies; thiết kế graceful shutdown, bảo vệ endpoints và kiểm thử hành vi khi lỗi. Các ví dụ liên hệ trực tiếp hợp đồng HTTP, xác thực, phân quyền, xử lý lỗi, timeout và kiểm thử API.

Sau bài học, người học có thể trả lời ba câu hỏi độc lập:

1. **Tiến trình có cần được khởi động lại không?** → liveness.
2. **Instance có nên nhận *request mới* từ load balancer không?** → readiness.
3. **Người dùng có thực hiện được chức năng cụ thể không?** → kiểm thử/quan sát API nghiệp vụ, SLO và synthetic monitoring.

## 1. Health check không phải bài kiểm thử mọi chức năng

Giả sử một cụm Orders API có ba pod và một PostgreSQL dùng chung:

~~~mermaid
flowchart TD
    C[Client] --> LB[Gateway / Kubernetes Service]
    LB --> A[Orders pod A]
    LB --> B[Orders pod B]
    LB --> D[Orders pod C]
    A --> DB[(PostgreSQL chung)]
    B --> DB
    D --> DB
    A --> P[(Payment service)]
    B --> P
    D --> P
    K[Kubelet probes] -. GET /livez, /readyz .-> A
    K -. GET /livez, /readyz .-> B
    K -. GET /livez, /readyz .-> D
~~~

Mỗi lần hệ thống kiểm tra sức khỏe cần một **mục đích vận hành cụ thể**. Nếu health endpoint thực hiện một giao dịch đặt hàng, nó vừa tạo side effect, vừa phụ thuộc nhiều thành phần không liên quan đến sự sống của pod. Nếu mọi pod trả “không khỏe” vì một Payment service toàn vùng bị lỗi và Kubernetes liên tục restart tất cả pod, quá trình phục hồi có thể còn khó hơn.

| Loại kiểm tra | Mục đích | Tín hiệu thất bại thường kích hoạt | Không nên làm |
| --- | --- | --- | --- |
| **Liveness** | Cho biết tiến trình ở trạng thái có thể tiếp tục vận hành hay đã hỏng đến mức cần restart | Kubelet restart container khi vượt ngưỡng | Gọi DB, payment, DNS hoặc dependency mạng tùy thời |
| **Readiness** | Quyết định pod có sẵn sàng nhận traffic từ Service hay không | Pod tạm bị loại khỏi nhóm endpoint nhận request mới | Tự động restart pod chỉ vì readiness thất bại |
| **Startup** | Cho tiến trình có thời gian khởi động dài trước khi áp liveness/readiness | Restart nếu mãi không đạt ngưỡng startup | Kéo dài thời gian che lỗi startup vô hạn |
| **API nghiệp vụ** | Trả kết quả cho một yêu cầu hợp lệ theo hợp đồng REST | 2xx/4xx/5xx theo tác vụ; monitoring ghi SLI | Dùng làm probe mà tạo đơn, trừ tồn kho hay thu tiền |
| **Synthetic/functional check** | Chủ động kiểm tra hành trình người dùng hoặc phụ thuộc | Alert/on-call, đánh giá SLO, có thể ngăn rollout | Đánh đồng ngay một lỗi nghiệp vụ với tín hiệu phải restart mọi pod |

### Ba tình huống khác nhau

**Tình huống A — Pod còn chạy, chưa nạp dữ liệu thiết yếu.** JVM và HTTP server đã hoạt động, nhưng snapshot cấu hình bắt buộc vẫn đang tải. Liveness có thể là `UP`; readiness phải là `OUT_OF_SERVICE`. Kubernetes giữ pod hoạt động nhưng chưa chuyển traffic tới nó.

**Tình huống B — Mỗi request nghiệp vụ đều bị 503 vì Payment service lỗi toàn hệ thống.** Orders pod không tự nhiên trở nên “chết”. Nếu liveness cũng kiểm tra Payment và restart, toàn cụm có thể rơi vào restart storm. Hãy báo lỗi nghiệp vụ có kiểm soát, bảo vệ bằng timeout/circuit breaker và giám sát SLO; chỉ làm readiness thất bại nếu chính sách vận hành xác định pod **thực sự không thể phục vụ bất kỳ loại request thiết yếu nào**.

**Tình huống C — JVM bị kẹt hoặc HTTP listener không đáp ứng được probe.** Liveness thất bại liên tục là tín hiệu có thể cần restart tiến trình. Tuy nhiên một check trả `UP` không đảm bảo phát hiện mọi dạng deadlock/treo thread; cần kết hợp watchdog thích hợp, thread/heap metrics và quan sát ở mức request.

## 2. Ý nghĩa HTTP của một health endpoint

HTTP health probe nên đơn giản, nhanh, không có side effect và trả mã trạng thái có nghĩa. Ví dụ Spring Boot Actuator:

~~~http
GET /actuator/health/liveness HTTP/1.1
Host: orders-api.internal:8080
~~~

~~~http
HTTP/1.1 200 OK
Content-Type: application/vnd.spring-boot.actuator.v3+json

{"status":"UP"}
~~~

Khi instance chưa sẵn sàng:

~~~http
GET /actuator/health/readiness HTTP/1.1
Host: orders-api.internal:8080
~~~

~~~http
HTTP/1.1 503 Service Unavailable
Content-Type: application/vnd.spring-boot.actuator.v3+json

{"status":"OUT_OF_SERVICE"}
~~~

`Content-Type` cụ thể có thể khác theo content negotiation/phiên bản Actuator; điều quan trọng là **HTTP status** và ý nghĩa trạng thái. Spring Boot mặc định ánh xạ `UP` thành 200, `DOWN` và `OUT_OF_SERVICE` thành 503. Nếu tự thay cấu hình mapping trạng thái, phải kiểm thử lại các ngưỡng HTTP 200/503.

Trong Kubernetes, **HTTP probe thành công với mã 200–399**. Vì vậy không nên dùng redirect `302` sang màn hình đăng nhập làm dấu hiệu sức khỏe: kubelet có thể coi nó là thành công mặc dù health endpoint không thực sự được gọi. Tốt nhất trả **200 khi đạt, 503 khi chưa đạt**, tránh redirect hoặc trang HTML.

### Không đồng nhất mã HTTP của probe và nghiệp vụ

| HTTP của API nghiệp vụ | Ví dụ | Kết luận về liveness/readiness |
| --- | --- | --- |
| `200 OK` | GET order thành công | Một request đã chạy tốt; không chứng minh mọi route đều khỏe |
| `201 Created` | POST tạo order thành công | Hoàn tất thao tác tạo resource, khác với pod health |
| `202 Accepted` | Job đã nhận, còn chạy async | Không chứng minh worker hoàn tất hay hàng đợi trống |
| `400` / `422` | JSON sai hoặc validation thất bại | Server đang **thực thi đúng hợp đồng**, không phải chết |
| `401` / `403` | Người gọi thiếu xác thực/quyền | Security có thể đang hoạt động đúng; không dùng làm pod health |
| `404 Not Found` | Order ID không tồn tại | Không liên quan đến sự sống của instance |
| `409 Conflict` | Trạng thái đơn không cho phép cập nhật | Lỗi nghiệp vụ theo dữ liệu hiện tại |
| `429 Too Many Requests` | Vượt quota theo tenant | Có thể là cơ chế bảo vệ chủ động, không tự đồng nghĩa unready |
| `503 Service Unavailable` | Downstream quá tải hoặc service không đáp ứng | Cần xem nguồn lỗi, scope và xu hướng; không luôn do pod hỏng |

Nếu client gọi `GET /v1/orders/123` và nhận 404, **không** đưa pod vào trạng thái unhealthy. Ngược lại, một pod liên tục trả 200 ở `/livez` vẫn có thể vi phạm SLO do 5xx nghiệp vụ hoặc dữ liệu sai. Cần metrics, tracing, log và synthetic test riêng.

## 3. Life cycle: liveness, readiness và startup ở Kubernetes

Ba probe không phải ba tên khác nhau cho một phép kiểm tra. Chúng điều khiển **các hành động khác nhau**:

~~~mermaid
stateDiagram-v2
    [*] --> STARTING: container chạy
    STARTING --> STARTING: startup probe chưa đạt
    STARTING --> RUNNING_NOT_READY: startup probe đạt
    RUNNING_NOT_READY --> READY: readiness đạt
    READY --> RUNNING_NOT_READY: readiness thất bại
    RUNNING_NOT_READY --> READY: readiness phục hồi
    READY --> RESTARTING: liveness thất bại quá ngưỡng
    RUNNING_NOT_READY --> RESTARTING: liveness thất bại quá ngưỡng
    STARTING --> RESTARTING: startup thất bại quá ngưỡng
    RESTARTING --> STARTING: container được khởi động lại
~~~

**Startup probe:** khi được cấu hình, nó bảo vệ giai đoạn khởi động: kubelet **chưa chạy** liveness và readiness probes cho tới khi startup probe thành công. Nhờ đó ứng dụng cần khởi tạo lâu không bị liveness giết quá sớm. Nếu startup probe thất bại đủ `failureThreshold`, container bị restart theo chính sách pod.

**Liveness probe:** khi thất bại liên tiếp đủ ngưỡng, kubelet restart container. Một lần timeout đơn lẻ chưa đủ nếu `failureThreshold > 1`. Liveness nên chỉ kiểm tra lỗi khó tự phục hồi của **chính tiến trình**, không kiểm tra toàn bộ mạng hoặc dữ liệu nghiệp vụ.

**Readiness probe:** thất bại làm pod **không còn sẵn sàng** và được loại khỏi danh sách endpoint phục vụ traffic của Service (quá trình cập nhật/lan truyền có độ trễ). Readiness **không** tự restart container. Khi readiness phục hồi, pod được đưa trở lại nhận request.

Readiness cũng có thể không đạt dù liveness đạt, và liveness có thể thất bại trong khi một probe HTTP trước đó vừa thành công. Các probe chỉ là **ảnh chụp theo chu kỳ**, không phải trạng thái logic nhất quán tức thời của toàn hệ thống.

### 3.1. Chuỗi thời gian khi deploy một pod

~~~text
t=0s     Pod bắt đầu, JVM khởi tạo.
t=10s    HTTP listener sẵn sàng; /livez trả 200.
t=10s    Startup probe đạt, liveness/readiness bắt đầu được kiểm tra.
t=10s    /readyz vẫn 503 do warmup dữ liệu cấu hình chưa xong.
t=25s    Warmup hoàn tất, /readyz trả 200.
t=25s+   Kubelet nhận readiness thành công và Service dần nhận pod mới.
t=...    Pod được yêu cầu shutdown, ngừng nhận traffic mới và drain request.
~~~

Đây là dòng thời gian minh họa; tần suất probe, thời gian kubelet cập nhật trạng thái và load balancer propagation khiến mốc thực tế khác nhau. Đừng dùng `sleep 15` để “đảm bảo ứng dụng đã sẵn sàng” thay cho một tín hiệu readiness dựa trên trạng thái thật.

## 4. Spring Boot Actuator: cấu hình health probes

Với Spring Boot 3.x, thường dùng `spring-boot-starter-actuator`, có HTTP server và (nếu cần) Spring Security để kiểm soát quyền truy cập. Khi Kubernetes hoặc nền tảng triển khai kích hoạt probes, Boot có thể tự nhận biết môi trường; để bài học và test có hành vi xác định, bật probe endpoints tường minh:

~~~yaml
spring:
  application:
    name: orders-api
  lifecycle:
    timeout-per-shutdown-phase: 30s

server:
  port: 8080
  shutdown: graceful

management:
  endpoint:
    health:
      show-details: never
      probes:
        enabled: true
        add-additional-paths: true
      group:
        readiness:
          include: readinessState,localBootstrap
  endpoints:
    web:
      exposure:
        include: health,info
~~~

**Ý nghĩa của từng cấu hình:**

- `management.endpoint.health.probes.enabled=true`: kích hoạt nhóm liveness/readiness cho môi trường không tự phát hiện hoặc test.
- `management.endpoint.health.probes.add-additional-paths=true`: cung cấp thêm `/livez` và `/readyz` trên **cổng ứng dụng chính** khi hỗ trợ theo phiên bản Boot. Điều này quan trọng nếu management server chạy cổng riêng: probe trên cổng management có thể trả 200 ngay cả khi cổng phục vụ request thật bị lỗi.
- `management.endpoint.health.group.readiness.include=readinessState,localBootstrap`: nhóm readiness dùng trạng thái Spring và một indicator ứng dụng minh họa được định nghĩa ở mục 5. **Nếu chưa tạo bean `localBootstrap` thì bỏ nó khỏi danh sách**, tránh cấu hình health group với contributor không tồn tại.
- `show-details: never`: không công khai dữ liệu như đường dẫn DB, hostname hay thông tin nội bộ trong response.
- `server.shutdown=graceful` và timeout của lifecycle: hỗ trợ kết thúc request đang xử lý trong thời gian được cấp, không phải bảo đảm mọi tác vụ dài sẽ hoàn thành.

**Endpoint thường gặp:**

| URL | Ý nghĩa | Nên được sử dụng bởi |
| --- | --- | --- |
| `/actuator/health` | Trạng thái tổng hợp theo health contributors đã cấu hình | Monitoring/nội bộ; không mặc định làm liveness |
| `/actuator/health/liveness` | Nhóm `livenessState` | Kubelet/liveness probe |
| `/actuator/health/readiness` | Nhóm `readinessState` và indicator được chọn | Kubelet/readiness probe |
| `/livez` | Liveness trên cổng ứng dụng khi bật additional paths | Kubelet/startup/liveness |
| `/readyz` | Readiness trên cổng ứng dụng khi bật additional paths | Kubelet/readiness |

Không coi `/actuator/health` và `/actuator/health/readiness` là tương đương: nhóm tổng có thể bao gồm Redis, DB, disk space và contributors khác, còn readiness mặc định theo **trạng thái sẵn sàng của ứng dụng**. Spring Boot mặc định **không tự thêm tất cả external health indicators vào readiness**, và đây thường là quyết định tốt để tránh outage dây chuyền.

Nếu bật cổng management riêng (`management.server.port`), cần quyết định thật rõ đường probe **có kiểm tra cổng ứng dụng đang nhận HTTP hay không**. Không chỉ đặt cả liveness/readiness trên một cổng khác rồi kết luận dữ liệu HTTP ở cổng 8080 chắc chắn phục vụ được. Với `/livez` và `/readyz` trên cổng chính, hãy thử trực tiếp bằng HTTP ở môi trường triển khai thật.

## 5. Tạo readiness indicator cho công việc khởi tạo cục bộ

Không phải mọi ứng dụng có HTTP listener đều có thể phục vụ ngay. Ví dụ Orders API cần nạp **bảng quy tắc định giá bắt buộc** vào memory trước khi nhận bất kỳ request đặt hàng nào. Có thể dùng một `HealthIndicator` chỉ quan sát trạng thái khởi tạo nội bộ:

~~~java
import java.util.concurrent.atomic.AtomicBoolean;
import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.stereotype.Component;

@Component("localBootstrap")
public final class LocalBootstrapHealthIndicator implements HealthIndicator {
    private final AtomicBoolean initialized = new AtomicBoolean(false);

    public void markReady() {
        initialized.set(true);
    }

    public void markNotReady() {
        initialized.set(false);
    }

    @Override
    public Health health() {
        return initialized.get()
            ? Health.up().build()
            : Health.outOfService()
                .withDetail("phase", "initializing")
                .build();
    }
}
~~~

**Điểm cốt lõi:** một service khởi tạo riêng phải gọi `markReady()` **chỉ sau khi** nạp và xác minh dữ liệu bắt buộc thành công. Nếu warmup thất bại, giữ trạng thái chưa sẵn sàng, ghi cảnh báo và có chiến lược retry/timeout. Đoạn code không tự biết khi nào hệ thống đã khởi tạo; **không** thêm `@PostConstruct` gọi `markReady()` ngay nếu chưa làm gì.

Một worker nạp dữ liệu có thể:

~~~java
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

@Component
public final class LocalBootstrapRunner {
    private static final Logger log =
        LoggerFactory.getLogger(LocalBootstrapRunner.class);
    private final LocalBootstrapHealthIndicator health;
    private final LocalRulesLoader loader;

    public LocalBootstrapRunner(
            LocalBootstrapHealthIndicator health, LocalRulesLoader loader) {
        this.health = health;
        this.loader = loader;
    }

    @EventListener(ApplicationReadyEvent.class)
    public void warmUp() {
        health.markNotReady();
        try {
            loader.loadAndValidate(); // Có deadline trong triển khai thực.
            health.markReady();
        } catch (RuntimeException ex) {
            // Không đánh dấu ready khi dữ liệu chưa đạt điều kiện.
            // Cần log/alert và cơ chế retry riêng.
            log.warn("Required local rules are not ready");
        }
    }
}

interface LocalRulesLoader {
    void loadAndValidate();
}
~~~

Đây là **mẫu học thuật**: khi `loadAndValidate()` thất bại, handler bắt lỗi để ứng dụng vẫn chạy và `localBootstrap` tiếp tục báo `OUT_OF_SERVICE`; cần bổ sung log/metric có giới hạn, cảnh báo và cơ chế retry độc lập hoặc quy trình sửa cấu hình. Không nuốt lỗi rồi tuyên bố hoàn tất warmup. Với `ApplicationReadyEvent`, việc gọi handler đồng bộ diễn ra trong luồng sự kiện của Spring; nếu warmup mất rất lâu, cân nhắc chuyển sang giai đoạn khởi tạo được quản lý, có deadline/cancellation và trạng thái readiness rõ ràng. Tránh để endpoint HTTP nhận dữ liệu nghiệp vụ trước khi local rules thực sự hợp lệ; readiness chỉ giúp load balancer thông thường, không thay thế kiểm tra điều kiện bên trong service. Không chờ một external dependency vô hạn trong event handler.

Khi ứng dụng bắt đầu shutdown, Spring Boot cập nhật `ReadinessState` theo lifecycle. Nếu có một quy trình drain chủ động **trước** shutdown, có thể công bố `ReadinessState.REFUSING_TRAFFIC` qua cơ chế `AvailabilityChangeEvent`, nhưng phải bảo đảm đổi state gắn với một quá trình ngừng nhận request thực tế. Đừng dùng biến `initialized` của indicator để thay một circuit breaker nghiệp vụ.

### 5.1. Liveness chỉ nên phản ánh tiến trình

Spring Boot liveness group thường dựa trên `livenessState`. Không thêm những kiểm tra như:

~~~text
/livez:
  - thử kết nối PostgreSQL qua mạng
  - gọi Payment API
  - gọi Redis của rate limiter
  - đếm queue backlog
  - query 10 bảng nghiệp vụ
~~~

Nếu DB chung tạm lỗi, **mọi pod** có thể trả liveness 503 và cùng bị restart; sau restart chúng lại phụ thuộc DB đang lỗi, tạo **crash loop** và làm tăng tải ở lúc DB phục hồi. Các lỗi external nên được phản ánh bằng business response, circuit breaker, metrics/alerts; readiness chỉ thêm kiểm tra khi thực sự phục vụ mục tiêu routing.

Đừng cho rằng liveness được Spring tự động phát hiện mọi deadlock trong thread pool: một health handler quá đơn giản vẫn có thể trả 200 khi một phần ứng dụng ngừng xử lý nghiệp vụ. Muốn phát hiện stuck worker quan trọng, phải thiết kế watchdog dựa trên tiến độ thực, tránh dùng một timestamp không bao giờ reset hoặc dependency bên ngoài làm liveness chập chờn.

## 6. Quyết định có đưa DB, cache hay downstream vào readiness không

Không có quy tắc “cứ thêm mọi dependency vào health thì an toàn hơn”. Cần trả lời: **Nếu dependency lỗi, riêng pod này có cần tạm ngừng nhận request và liệu việc loại pod có giúp hệ thống tốt hơn không?**

| Dependency/tình huống | Liveness | Readiness | Quan sát/biện pháp khác |
| --- | --- | --- | --- |
| Local rules bắt buộc chưa nạp xong | Không cần ảnh hưởng | Có thể `OUT_OF_SERVICE` | Warmup retry, startup metric |
| DB chung lỗi toàn vùng | **Không** gọi DB | Thường **không tự động** khiến mọi pod unready; xét policy cụ thể | 503 nghiệp vụ, circuit breaker, DB alert/SLO |
| DB riêng của đúng pod bị corrupt, không tự phục hồi | Liveness chỉ khi restart có thể giúp | Có thể remove pod | Alert/repair, bảo vệ dữ liệu |
| Redis cache optional không khả dụng | Không | Thường vẫn ready nếu có fallback hợp lệ | Cache hit, DB load, timeout |
| Payment service đang quá tải | Không | Không mặc định unready toàn bộ Orders | 503/4xx theo contract, timeout/retry budget |
| Worker queue đang backlog | Không | Tùy việc pod còn khả năng nhận **loại request nào** | Queue age, concurrency, 429/503/admission |
| Pod chủ động drain/đang shutdown | Không cần restart | **Không sẵn sàng** | Graceful shutdown, drain in-flight |
| Một cấu hình bí mật bắt buộc của riêng pod không thể sử dụng | Không cần ping dịch vụ ngoài | Có thể unready, nếu chưa thể phục vụ | Alert rõ về cấu hình; không phơi secret |

Nếu **tất cả pod** đồng loạt unready vì DB chung lỗi, Service có thể không còn endpoint phục vụ, thậm chí các route đọc cache vẫn bị cắt. Đây có thể là lựa chọn đúng với ứng dụng chỉ có một chức năng bắt buộc DB, nhưng phải là **quyết định có chủ đích**, không phải hệ quả tình cờ của việc thêm mọi health indicator.

**Đặt giới hạn độ trễ:** Một health check gọi mạng và mất 30 giây có thể làm cạn thread/pool khi nhiều kubelet cùng probe. Health/readiness nên dùng trạng thái đã quan sát/cached, phép kiểm tra không tạo side effect, timeout ngắn và tần suất phù hợp. Nếu cần kiểm tra external dependency định kỳ, triển khai watcher riêng có retry/backoff và giới hạn tài nguyên; probe HTTP chỉ đọc **snapshot trạng thái đã tính**.

**Tránh flapping:** Nếu readiness đi xuống mỗi khi queue đầy trong 100 ms rồi lên ngay, pod có thể liên tục vào/ra endpoints khiến traffic dồn qua những pod khác. Dùng ngưỡng/hysteresis, thời gian ổn định và các cơ chế admission/overload chuyên dụng. Với dịch vụ có route đọc và ghi rất khác nhau, một readiness bit áp cho toàn pod có thể quá thô; cân nhắc tách deployment hoặc routing policy.

## 7. Deployment Kubernetes: ba probe và rolling update

Với các additional paths ở mục 4, pod sử dụng cổng **HTTP nghiệp vụ 8080**. Ví dụ Deployment rút gọn:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders-api
spec:
  replicas: 3
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0
  selector:
    matchLabels:
      app: orders-api
  template:
    metadata:
      labels:
        app: orders-api
    spec:
      terminationGracePeriodSeconds: 40
      containers:
        - name: orders-api
          image: registry.example.com/orders-api:1.0.0
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
            failureThreshold: 2
            successThreshold: 1
          resources:
            requests:
              cpu: 250m
              memory: 512Mi
            limits:
              memory: 1Gi
~~~

Đây là cấu hình minh họa, **không phải giá trị mặc định an toàn cho mọi hệ thống**:

- `startupProbe` cho khoảng ngân sách thất bại minh họa `5 s × 30 = 150 s` trước khi restart, ngoài các chi tiết lịch probe/timeout thực tế. Chọn theo thống kê startup p99 và mức chịu lỗi.
- `livenessProbe` kiểm tra mỗi 10 giây, có thể restart sau nhiều lần thất bại; đừng giảm timeout còn vài mili-giây nếu GC pause hoặc máy quá tải có thể làm false positive.
- `readinessProbe` kiểm tra mỗi 5 giây, 2 lần thất bại liên tiếp có thể khiến pod bị loại khỏi Service; khi phục hồi, `successThreshold: 1` đủ cho lần đánh giá thành công.
- `maxUnavailable: 0` và `maxSurge: 1` dành cho rolling update muốn duy trì số pod ready, nhưng không bảo đảm **zero downtime** nếu toàn vùng DB hỏng, replica thiếu capacity hoặc rollout gặp lỗi ngoài readiness.
- `terminationGracePeriodSeconds: 40` để chừa khoảng thời gian cho Spring graceful shutdown `30s` cùng overhead dừng container; cần chọn theo request/connection thực tế. Không bảo đảm một job async 10 phút sẽ hoàn thành trong 40 giây.

Nếu chọn `management.server.port=9090` và chỉ expose `/actuator/health/...` trên cổng 9090, Kubernetes có thể kiểm tra một web server management độc lập, trong khi cổng 8080 bị treo hoặc chưa lắng nghe. Probe trên `/livez`/`/readyz` ở cổng ứng dụng giúp kiểm tra đường HTTP thực tế hơn, nhưng vẫn không đo mọi business route. Khi có servlet context path, reverse proxy rewrite hoặc Spring Security, **xác minh URL cuối** thay vì đoán.

### 7.1. Readiness phải tham gia vào rollout

Một rollout hợp lý:

~~~text
Tạo pod phiên bản mới
  → startup probe đạt
  → warmup/cache/schema compatibility hoàn tất
  → readiness đạt
  → pod mới được đưa vào tập endpoint nhận traffic
  → giảm dần pod phiên bản cũ theo rolling strategy
  → drain và dừng pod cũ
~~~

Đừng đánh dấu pod ready rồi mới tải một cấu hình bắt buộc mà request đầu tiên có thể dùng. Ngược lại, đừng chờ một HTTP synthetic order có side effect hoàn tất chỉ để đánh dấu ready. Nếu schema migration yêu cầu thứ tự triển khai, kiểm tra tính tương thích version có chủ đích và dùng migration job/rollout plan riêng; probe không thay quy trình migration.

## 8. Graceful shutdown và traffic còn đang xử lý

Pod bị xóa hoặc scale down không có nghĩa mọi client dừng gửi request ngay lập tức. Kubernetes cập nhật EndpointSlice/Service, ingress/load balancer và connection tồn tại có thể tiếp tục mang request trong một khoảng ngắn. Thiết kế shutdown theo thứ tự:

~~~mermaid
sequenceDiagram
    participant O as Orchestrator
    participant S as Spring app
    participant LB as Service/Gateway
    participant C as Client
    O->>S: Pod termination / SIGTERM
    S->>S: Chuyển readiness sang REFUSING_TRAFFIC
    O->>LB: Endpoint đang kết thúc, rút khỏi routing
    C->>LB: Request trong thời gian chuyển tiếp
    LB-->>S: Có thể còn request đến qua kết nối cũ
    S->>S: Ngừng nhận việc mới, drain in-flight
    S-->>C: Trả kết quả hoặc lỗi có kiểm soát
    S-->>O: Tiến trình kết thúc trong grace period
~~~

**Điều phải cân nhắc:**

1. **Readiness là tín hiệu routing, không phải một tường chắn tức thời.** Một số request vẫn đến trong lúc trạng thái endpoints đang lan truyền. Tầng ứng dụng cần xử lý request mới trong giai đoạn drain có chủ đích; client vẫn cần retry an toàn và deadline.
2. **Graceful HTTP shutdown** cho phép request in-flight có cơ hội hoàn thành. Cần đo p99 request duration, WebSocket/streaming và thời gian drain; cấu hình timeout Spring không thể vượt ngân sách dừng của orchestrator nếu muốn hoạt động trọn vẹn.
3. **Background consumers** phải ngừng nhận message mới, commit/ack những công việc hoàn tất và để job còn dở được retry/idempotent ở lần chạy sau. Không phụ thuộc việc Pod luôn sống đủ lâu để xử lý xong một queue.
4. Nếu dùng **`preStop` hook** để tạo khoảng trễ cho load balancer rút endpoint, hook đó cũng **tiêu thụ termination grace period**. Không copy một lệnh `sleep 30` mà không đo propagation, drain time và tổng ngân sách.
5. Client retry POST tạo resource phải có `Idempotency-Key`/hợp đồng idempotency phù hợp; request bị ngắt trong lúc shutdown có thể đã gây side effect ở server.

Với traffic thật, đo các chỉ số: request bị reset khi rollout, `503/504` lúc drain, số connection còn mở, job bị retry, thời gian từ readiness false đến không còn request mới, và tỷ lệ request thành công sau retry. Không kết luận zero-downtime chỉ vì `kubectl rollout status` báo thành công.

## 9. Bảo mật, mạng và chi phí của health endpoints

Health checks thường không cần bearer token trong mỗi lần kubelet gọi, nhưng điều đó **không** có nghĩa nên công bố chúng ra Internet. Chính sách khuyến nghị:

- Cho kubelet/monitoring **nội bộ** truy cập những URL cần thiết; dùng network policy, service binding, ingress rules hoặc cổng quản trị riêng khi phù hợp.
- Chỉ lộ trạng thái tổng quát (ví dụ `UP`, `OUT_OF_SERVICE`); không tiết lộ hostname DB, username, URL nội bộ, credentials, exception stack trace, memory dump hoặc cấu hình môi trường.
- Các Actuator endpoints nhạy cảm như `env`, `heapdump`, `beans`, `configprops`, `loggers` không được mở công khai chỉ vì muốn expose health. Dùng exposure whitelist và security phù hợp.
- Nếu Spring Security chặn `/readyz` bằng 401/403, Kubernetes sẽ xem readiness thất bại. Cấu hình quyền truy cập riêng cho các đường health nội bộ; **không tắt auth của toàn API** để sửa probe.
- Nếu API dùng CORS, nhớ rằng kubelet không bị browser Same-Origin Policy/CORS ràng buộc. Không cần mở wildcard CORS hay cho phép credentials chỉ để health endpoint được kubelet gọi.
- Không dùng health probe làm endpoint dữ liệu cá nhân, thay đổi dữ liệu hoặc gọi API tính phí. GET phải có side effect bằng không ở mức nghiệp vụ.
- Tránh health check đòi JWT được tạo mới, refresh token hoặc gọi identity provider cho mỗi probe; hỏng IdP không nên restart toàn bộ pod.

Kubelet probes sẽ xuất hiện định kỳ ở **mỗi pod**. Một probe gọi 5 dependency với query nặng, mỗi 5 giây trên hàng nghìn pod, có thể trở thành nguồn tải không nhỏ. Đặt deadline ngắn, trả dữ liệu tối thiểu, và không để probe giữ lock tài nguyên chung với request nghiệp vụ.

### Cấu hình sai thường gặp

| Anti-pattern | Vì sao nguy hiểm | Cách thay |
| --- | --- | --- |
| Dùng `GET /v1/orders/1` làm liveness | Order 1 có thể không tồn tại; cần auth/DB | `/livez` chuyên biệt, không cần resource nghiệp vụ |
| Dùng `POST /v1/orders` làm readiness | Tạo side effect, spam dữ liệu, dễ tạo đơn trùng | Indicator không side effect cho local readiness |
| Readiness luôn 200 từ lúc socket mở | Request đầu gặp config/cache chưa sẵn | Theo dõi bootstrap thật, trả 503 đến khi sẵn sàng |
| Liveness ping DB chung | Restart đồng loạt khi DB lỗi | Chỉ kiểm local process; DB ở metrics/alert hoặc readiness có chủ đích |
| Readiness gọi 10 downstream tuần tự | Timeout, false negative, tải dây chuyền | Snapshot cục bộ/kiểm tra rất hẹp có budget |
| Probe qua port quản trị, app port bị hỏng | False healthy | Dùng additional paths trên app port |
| 302 tới trang login được coi khỏe | Kubelet chấp nhận 3xx | Trả 200/503 trực tiếp, cấu hình access nội bộ |
| Trả 200 với JSON `{"status":"DOWN"}` | Kubelet chỉ dựa vào HTTP status | Ánh xạ `DOWN/OUT_OF_SERVICE` thành 503 |
| Cho tất cả pod unready vì Redis cache optional | Loại cả pod vẫn phục vụ được | Fallback/circuit breaker, theo dõi cache riêng |
| Health chứa stack trace/hostname DB | Lộ thông tin hạ tầng | Ẩn details, log riêng có phân quyền |
| Coi readiness = hoàn tất đơn hàng | Lẫn availability với business outcome | Dùng API nghiệp vụ + status resource/SLO |

## 10. Kiểm thử probes ở các trạng thái vòng đời

Chỉ test `GET /actuator/health` trả 200 lúc bình thường là chưa đủ. Cần thử **đường khởi tạo, lỗi, phục hồi, shutdown và Kubernetes routing**:

| Ca kiểm thử | Cách kích hoạt | Kỳ vọng |
| --- | --- | --- |
| Lần đầu boot | Listener lên, warmup còn chạy | `/livez` có thể 200; `/readyz` 503 cho tới khi warmup xong |
| Warmup xong | `localBootstrap.markReady()` sau khi dữ liệu hợp lệ | `/readyz` chuyển 200 |
| Warmup thất bại | Loader ném lỗi/không đánh dấu ready | Pod không nhận traffic; có alert và cách phục hồi |
| DB chung chập chờn | Chặn kết nối DB | `/livez` không bị kéo xuống; readiness theo chính sách đã chọn |
| Redis cache optional mất | Tắt Redis | Business fallback hợp lệ; không unready toàn bộ nếu vẫn phục vụ được |
| Quá tải request | Nhiều GET/POST và pool gần bão hòa | Probe không dùng tài nguyên vô hạn; SLO/error metrics phản ánh vấn đề |
| Custom indicator không sẵn sàng | Chuyển local gate false | `/readyz` 503; `/livez` vẫn 200 |
| Bean/health group cấu hình thiếu | Bỏ indicator bắt buộc | Startup hoặc probe thất bại rõ; không silently green |
| URL probe bị Security chặn | Bật filter mặc định | Phát hiện 401/403, sửa matcher nội bộ |
| Pod scale down | SIGTERM khi còn in-flight request | Không làm mất dữ liệu, drain theo grace; request có thể retry an toàn |
| Rolling update nhiều pod | Triển khai version mới chậm warmup | Pod cũ tiếp tục sẵn sàng trong khi pod mới unready |
| Management port riêng lỗi chính port | Tắt/khóa cổng nghiệp vụ | Probe trên main port thất bại, không false healthy |
| API nghiệp vụ trả 404/422 | Gửi dữ liệu không hợp lệ | Health không đổi chỉ vì input client bị từ chối |

### 10.1. Kiểm tra nhanh bằng curl

Khi chạy ứng dụng minh họa ở local với additional paths:

~~~bash
curl -i http://localhost:8080/livez
curl -i http://localhost:8080/readyz
curl -i http://localhost:8080/actuator/health/liveness
curl -i http://localhost:8080/actuator/health/readiness
~~~

Khi pod chưa sẵn sàng, `/readyz` dự kiến trả 503, không phải một trang HTML đăng nhập. Nếu 404, kiểm tra đúng property Spring, phiên bản Actuator, context path và cổng. Nếu 401/403, kiểm tra SecurityFilterChain hoặc reverse proxy. Nếu 200 ngay cả khi warmup chưa xong, kiểm tra indicator đã vào readiness group và có bị gọi `markReady()` quá sớm không.

### 10.2. Spring Boot integration test cho readiness group

Ví dụ dùng Spring Boot 3.x, Actuator, Spring Test và indicator ở mục 5; test chỉ nên chạy trong context bảo đảm endpoint health được cho phép truy cập. Đây là một **integration test có scope rõ ràng**, không phải kiểm thử Kubernetes:

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest(properties = {
    "management.endpoint.health.probes.enabled=true",
    "management.endpoint.health.group.readiness.include="
        + "readinessState,localBootstrap"
})
@AutoConfigureMockMvc
class ReadinessProbeTest {

    @Autowired MockMvc mockMvc;
    @Autowired LocalBootstrapHealthIndicator bootstrap;

    @Test
    void readinessTracksLocalBootstrapWhileLivenessStaysUp()
            throws Exception {
        try {
            bootstrap.markNotReady();
            mockMvc.perform(get("/actuator/health/readiness"))
                .andExpect(status().isServiceUnavailable());
            mockMvc.perform(get("/actuator/health/liveness"))
                .andExpect(status().isOk());

            bootstrap.markReady();
            mockMvc.perform(get("/actuator/health/readiness"))
                .andExpect(status().isOk());
        } finally {
            bootstrap.markNotReady();
        }
    }
}
~~~

Test giả định Spring `ApplicationAvailability` đang ở trạng thái liveness `CORRECT` và readiness `ACCEPTING_TRAFFIC` sau khi context khởi tạo. Nếu test context bật Security/CSRF hoặc đường Actuator không được expose vào MockMvc, cần cấu hình/test principal phù hợp, không tắt security production. Tránh chạy nhiều test thay đổi singleton indicator trong cùng context song song; isolate test state, dùng context riêng hoặc reset cẩn thận.

Test này chứng minh **mapping readiness indicator → HTTP 503/200**, chưa chứng minh Service/EndpointSlice đã loại pod. Cần kiểm thử triển khai thật ở staging hoặc môi trường Kubernetes mô phỏng phù hợp để thấy routing, rolling update và termination behavior.

### 10.3. Kiểm thử hệ thống khi rollout

Trong staging, dùng traffic mô phỏng liên tục qua Service và ghi lại timestamp, request ID, status:

1. Khởi động pod mới với warmup chậm: đảm bảo request nghiệp vụ chỉ được route khi ready.
2. Gây lỗi một pod cụ thể: readiness false loại đúng pod; các pod khác vẫn phục vụ.
3. Gây lỗi DB **chung**: kiểm tra chính sách readiness có gây toàn bộ endpoints rỗng hay không.
4. Scale down khi có request dài: kiểm tra in-flight completion, connection reset và idempotency retry.
5. Chặn /livez hoặc treo container trong môi trường test: xác nhận liveness failures đủ ngưỡng mới restart, tránh restart loop.
6. Tắt/đổi cổng 8080 nhưng giữ management port: xác minh probe của pod không false healthy.

**Phân biệt test:** gọi MockMvc trực tiếp không đi qua Kubernetes; kiểm tra route qua ingress mới quan sát load balancer. Không tuyên bố hệ thống zero downtime chỉ từ unit test hoặc một lần `kubectl get pods` thấy `READY 3/3`.

## 11. Quan sát probe failures và chẩn đoán sự cố

Khi deployment mới không nhận traffic, khoanh vùng theo thứ tự:

~~~text
Pod có chạy không?
  ├── Không: image pull, crash, OOM, cấu hình container
  └── Có:
       Startup probe có đạt không?
         ├── Không: cổng/path, thời gian khởi tạo, exception startup
         └── Có:
              Liveness có đạt không?
                ├── Không: lỗi tiến trình/probe quá nhạy/timeout
                └── Có:
                     Readiness có đạt không?
                       ├── Không: warmup, availability, indicator, security
                       └── Có:
                            Service/Ingress có route đúng?
                              ├── Không: selector, EndpointSlice, LB/network
                              └── Có: đo metrics/traces/API nghiệp vụ
~~~

**Khi có 503, xác định ai trả:** kubelet/readiness endpoint, gateway không có upstream endpoint, circuit breaker, app business handler hoặc downstream. Những 503 này có nguyên nhân và cách xử lý khác nhau; dùng log, distributed tracing, status code tại từng hop và metadata pod để đối chiếu.

### Những chỉ số nên theo dõi

- Số pod `Ready/NotReady` theo deployment, thời gian từ start đến readiness, rollout duration và restart count.
- Probe failure/timeout, lý do như 404, 401, 503, connection refused, timeout; số lần chuyển trạng thái readiness (flapping).
- HTTP request rate, latency p95/p99, tỷ lệ 5xx và 429 theo **route template**, phiên bản deploy và pod; giữ label cardinality thấp.
- Connection pool saturation, thread pool queue, CPU, heap/GC, DB/network errors, downstream timeout/circuit breaker, cache hit và queue backlog.
- Số request bị reset hoặc retry trong rollout, số job bị gián đoạn và thời gian drain thực tế.

Không đưa trace ID, tenant ID, bearer token hoặc business resource ID làm **metric label động**. Cần truy vết một request thì dùng trace/log được kiểm soát. Probe là một tín hiệu vận hành, không thay SLO của người dùng như “99,9% request đặt hàng hợp lệ hoàn thành trong 500 ms”.

## 12. Checklist thiết kế trước khi đưa vào production

| Quyết định | Câu hỏi cần trả lời |
| --- | --- |
| Liveness scope | Có vô tình kiểm tra DB/Redis/payment chung không? Restart có giúp phục hồi không? |
| Readiness scope | Chính xác khi nào pod nhận request mới an toàn? Các thành phần nào là bắt buộc *cho pod này*? |
| Startup budget | p99 startup/warmup mất bao lâu? Ngưỡng có che lỗi cấu hình mãi không? |
| HTTP endpoint | Có trả 200/503 trực tiếp, không redirect/401? Có kiểm tra cổng HTTP nghiệp vụ? |
| Dependency policy | DB/cache/downstream lỗi toàn vùng có làm unready tất cả pod không? Đó có phải lựa chọn mong muốn? |
| Resource budget | Check có nhẹ, timeout ngắn, không tạo side effect và không gây tải cộng hưởng không? |
| Security | Health nội bộ có được access đúng? Có giấu details và không expose Actuator nhạy cảm không? |
| Shutdown | Readiness false, endpoint draining, graceful timeout, consumer ack và idempotency đã thử chưa? |
| Deploy strategy | Rolling update, capacity, replicas và routing propagation có đủ cho SLO không? |
| Tests | Có test boot chưa ready, dependency error, 401/404 misconfig, scale down và business 4xx không? |

Một thiết kế tốt có thể có **liveness đơn giản**, **readiness ngắn gọn nhưng đúng ngữ nghĩa**, và **functional monitoring riêng rất sâu**. Càng nhiều dependency trong liveness không đồng nghĩa càng an toàn.

## 13. Bài tập thực hành

**Bài 1 — Phân loại trạng thái.** Trong cụm ba pod: (a) pod A đã mở HTTP listener nhưng warmup local cache bắt buộc chưa xong; (b) pod B đang chạy bình thường nhưng Payment API chung trả 503; (c) pod C có HTTP handler bị treo và không đáp ứng /livez; (d) client gọi một order ID không tồn tại. Với mỗi tình huống, quyết định liveness, readiness, HTTP API nghiệp vụ và hành động Kubernetes, kèm lý do.

**Bài 2 — Sửa cấu hình hỏng.** Một deployment dùng `livenessProbe` gọi `GET /v1/orders/1`, cần JWT và query DB, mỗi 2 giây với timeout 1 giây. Khi DB mất kết nối, mọi pod restart liên tục. Hãy thiết kế lại ba probe, đường Actuator, chu kỳ/threshold phù hợp, network security và cách đo khi DB lỗi toàn vùng.

**Bài 3 — Viết Spring HealthIndicator.** Xây dựng service nạp bảng quy tắc bắt buộc từ file cấu hình vào bộ nhớ, có trạng thái `NOT_INITIALIZED`, `LOADING`, `READY`, `FAILED`. Tích hợp indicator vào readiness mà không đổi liveness; khi lỗi khởi tạo, health endpoint trả 503 và khi retry thành công chuyển sang 200. Thêm test cho thời điểm trước/sau warmup.

**Bài 4 — Rolling update an toàn.** Mỗi pod cần 45 giây warmup; request dài nhất chấp nhận 20 giây; load balancer cần một khoảng để nhận pod vào/ra routing. Chọn `startupProbe`, `readinessProbe`, `livenessProbe`, `terminationGracePeriodSeconds` và rolling strategy. Thiết kế một thử nghiệm staging chứng minh không gửi request mới vào pod chưa ready, không cắt sớm request in-flight.

**Bài 5 — Chẩn đoán lỗi 503.** `/livez` trả 200, `/readyz` trả 503 trong khi GET dữ liệu từ cache vẫn 200 và POST tạo đơn trả 503 do DB chung mất kết nối. Hãy trình bày khi nào readiness nên tiếp tục 503, khi nào cần tách route/pod hoặc fallback, và cách phân biệt 503 từ kubelet/probe, gateway, ứng dụng và downstream bằng metrics/traces/log.

**Gợi ý tự kiểm tra:** (1) Warmup local chưa xong → liveness có thể UP, readiness false; lỗi Payment chung không tự buộc restart; 404 resource là business outcome. (2) Không dùng API nghiệp vụ và dependency DB chung làm liveness; probe chuyên dụng, nội bộ, không side effect. (3) Trả readiness OUT_OF_SERVICE cho đến khi nạp xong; readiness group có indicator, liveness chỉ local process. (4) Startup budget vượt p99 warmup, graceful grace vượt drain thực tế; rolling strategy đảm bảo đủ ready capacity nhưng phải test routing. (5) Probe không thay monitoring nghiệp vụ; readiness chỉ nên phản ánh khả năng nhận traffic của pod theo chính sách có chủ đích, tránh outage dây chuyền.
