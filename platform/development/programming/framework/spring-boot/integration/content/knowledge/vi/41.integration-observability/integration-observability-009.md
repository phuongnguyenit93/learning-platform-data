# Health indicator và ý nghĩa khi một phụ thuộc không sẵn sàng trong Spring Boot

Một dịch vụ Spring Boot có thể vẫn chạy bình thường về mặt JVM, nhận HTTP request và trả trang `/actuator/health`, nhưng **không hoàn thành được nghiệp vụ** vì PostgreSQL, Redis, RabbitMQ hoặc một API đối tác đang mất kết nối. Ở chiều ngược lại, không phải cứ mất một phụ thuộc ngoài là phải khởi động lại toàn bộ ứng dụng: nếu lỗi nằm ở một hệ thống khác, việc restart hàng loạt pod không sửa được nguyên nhân và còn làm tăng tải.

Trong chương **Quan sát tích hợp** của module **SPRING_BOOT_INTEGRATION**, bài học này tập trung vào **HealthIndicator**, **ReactiveHealthIndicator**, các nhóm health của Spring Boot Actuator và cách diễn giải khi phụ thuộc mất tính sẵn sàng. Đây là vấn đề liên quan trực tiếp đến tích hợp qua HTTP client, cơ sở dữ liệu, cache, broker thông điệp và adapter Spring Integration; quyết định health đúng phải xét đến hợp đồng nghiệp vụ, giao dịch, retry, xử lý trùng, kiểm thử và tín hiệu vận hành.

**Thông điệp cốt lõi:** *Liveness* hỏi “tiến trình còn có khả năng tự hoạt động không?”, *readiness* hỏi “instance có nên nhận **lưu lượng mới** không?”, còn *dependency health* cung cấp tín hiệu riêng về một thành phần. **Không gộp ba câu hỏi thành một boolean** rồi dùng cùng đáp án cho restart, routing và cảnh báo.

Các ví dụ hướng tới Spring Boot 3.x, Spring Framework 6.x, Java 17+ và Actuator. Tên property và khả năng tích hợp có thể khác giữa phiên bản Boot hoặc các thư viện/starter; trước khi deploy cần kiểm tra phiên bản và hành vi thực tế trong ứng dụng.

## 1. Bối cảnh: một phụ thuộc không sẵn sàng có nghĩa gì?

Giả sử `checkout-service` có các đường đi:

- `POST /orders`: ghi đơn hàng vào PostgreSQL, phát sự kiện qua outbox để gửi tới RabbitMQ.
- `GET /catalog`: lấy dữ liệu từ cache Redis, có thể fallback về database.
- `GET /shipping/quote`: gọi REST API đối tác vận chuyển; có thể tạm hiển thị trạng thái “chưa tính được phí”.
- Worker `@RabbitListener`: tiêu thụ `PaymentCaptured` và cập nhật database.
- Spring Integration flow: nhận thông điệp qua HTTP adapter, chuyển đổi rồi đẩy tới hệ thống khác.

Nếu RabbitMQ bị gián đoạn 60 giây, **API tạo đơn vẫn có thể nhận request** nếu outbox trong SQL hoạt động, còn relay chờ broker phục hồi. Nhưng nếu `POST /orders` bắt buộc xuất bản message **đồng bộ trước khi trả thành công**, nghiệp vụ này có thể không sẵn sàng. Tương tự, Redis lỗi không làm mất khả năng phục vụ `GET /catalog` nếu fallback được thiết kế và database còn đủ công suất.

~~~mermaid
flowchart TD
    APP["checkout-service / Spring Boot"] --> DB[("PostgreSQL")]
    APP --> REDIS[("Redis cache")]
    APP --> PARTNER["Shipping HTTP API"]
    APP --> OUTBOX[("SQL outbox")]
    OUTBOX --> RELAY["Outbox relay"]
    RELAY --> MQ[("RabbitMQ")]
    APP --> L["HTTP liveness/readiness probes"]
    L --> POLICY{"Chính sách nhận traffic"}
    POLICY -->|Ready| YES["Nhận request mới"]
    POLICY -->|Not ready| NO["Ngừng route traffic qua instance"]
~~~

**“Phụ thuộc không sẵn sàng” là sự kiện quan sát được**, chưa phải chỉ thị vận hành. Cần hỏi ít nhất: phụ thuộc nào, nghiệp vụ nào bị ảnh hưởng, khả năng fallback, thời gian kéo dài, có instance khác đang khỏe không, và việc loại toàn bộ pod khỏi load balancer có thực sự giúp ích không.

### Health không bằng business correctness

Một check `SELECT 1` thành công chứng minh database có thể trả một query đơn giản. Nó **không** chứng minh đã áp dụng migration đúng, đủ quyền ghi bảng nghiệp vụ, không có deadlock, dữ liệu nhất quán hay outbox relay đang bắt kịp.

Một TCP connection tới RabbitMQ chứng minh có thể kết nối broker theo điều kiện kiểm tra. Nó **không** chứng minh queue được binding đúng, consumer đang ack message, DLQ không tăng hay một sự kiện đã được xử lý chính xác một lần.

Vì thế health indicator cần được đặt cạnh metrics, tracing, log và các phép kiểm thử/hợp đồng nghiệp vụ; không thay thế chúng.

## 2. Ba loại tín hiệu cần tách: liveness, readiness, dependency health

| Tín hiệu | Câu hỏi | Khi thất bại nên làm gì? | Ví dụ |
| --- | --- | --- | --- |
| **Liveness** | Process còn có thể tiến bộ, hay đã hỏng nội bộ không thể tự phục hồi? | Orchestrator **có thể restart** instance | Deadlock nội bộ không thể phục hồi, trạng thái sống của ứng dụng |
| **Readiness** | Instance có nên nhận traffic mới trong **lúc này** không? | Orchestrator **loại khỏi routing** tới khi phục hồi | Chưa warmup, đang graceful shutdown, resource thiết yếu không dùng được |
| **Dependency health** | Database/cache/broker/API đích có đáp ứng một phép kiểm tra cụ thể không? | Cảnh báo, fallback, circuit breaker hoặc ảnh hưởng readiness tùy chính sách | `db=UP`, `partnerApi=DOWN`, `rabbit=UP` |

Spring Boot Actuator cung cấp endpoint health tổng hợp và **health groups**. Trên môi trường Kubernetes hoặc khi bật property probe, Boot hỗ trợ các nhóm mặc định như `liveness` và `readiness`, với các indicator trạng thái ứng dụng `livenessState` và `readinessState`.

Endpoints thường gặp:

~~~text
GET /actuator/health
GET /actuator/health/liveness
GET /actuator/health/readiness
~~~

Một JSON tổng hợp minh họa:

~~~json
{
  "status": "DOWN",
  "components": {
    "db": { "status": "UP" },
    "shippingPartner": { "status": "DOWN" }
  }
}
~~~

**Lưu ý:** `components` và `details` có xuất hiện hay không phụ thuộc cấu hình `show-components`, `show-details` và quyền truy cập; mặc định không nên công khai topology/exception. JSON minh họa một endpoint được phép hiển thị component, không phải hợp đồng response mặc định mọi môi trường.

### Sự khác nhau giữa readiness DOWN và liveness DOWN

~~~mermaid
flowchart LR
    A["Một external API trả 503"] --> B["Dependency indicator có thể DOWN"]
    B --> C{"Dependency bắt buộc để nhận traffic?"}
    C -->|Có| D["Readiness có thể DOWN"]
    C -->|Không / fallback| E["Readiness vẫn UP"]
    A --> F["Liveness giữ UP nếu JVM/tiến trình khỏe"]
    D --> G["Kubernetes ngừng route pod"]
    F --> H["Không restart chỉ vì API ngoài lỗi"]
~~~

**Không nên đưa các health check của external dependency vào liveness** theo mặc định. Khi tất cả pod cùng phụ thuộc một Redis hay API bị lỗi, liveness DOWN khiến Kubernetes restart mọi pod, gia tăng connection storm, làm mất cache nóng và trì hoãn hồi phục.

## 3. Vòng đời trạng thái ứng dụng và probe của Kubernetes

Spring Boot quản lý `ApplicationAvailability` với hai state model quan trọng:

- `LivenessState`: thường là `CORRECT` hoặc `BROKEN`.
- `ReadinessState`: thường là `ACCEPTING_TRAFFIC` hoặc `REFUSING_TRAFFIC`.

Trong quá trình startup, ứng dụng chưa đủ điều kiện nhận traffic; sau khi khởi động thành công, trạng thái readiness chuyển sang nhận traffic. Khi graceful shutdown, readiness có thể chuyển sang từ chối traffic trước khi các tài nguyên dừng. Các chuyển đổi gắn với các sự kiện/lifecycle của Boot; không phải developer phải tự đổi state ở mỗi lần có request lỗi.

Ở Kubernetes:

- **Startup probe**: dành thêm ngân sách cho ứng dụng khởi động chậm. Khi startup probe chưa thành công, Kubernetes chưa áp dụng các kiểm tra liveness/readiness tương ứng như bình thường.
- **Liveness probe**: nếu thất bại vượt ngưỡng, kubelet có thể restart container.
- **Readiness probe**: nếu thất bại, pod không được xem là endpoint sẵn sàng của Service tương ứng; container **không tự restart chỉ vì readiness thất bại**.

Một ví dụ manifest minh họa khi endpoint được mở trên cổng ứng dụng `8080`:

~~~yaml
containers:
  - name: checkout-service
    image: registry.example/checkout-service:version
    ports:
      - containerPort: 8080
    startupProbe:
      httpGet:
        path: /livez
        port: 8080
      periodSeconds: 5
      failureThreshold: 30
    livenessProbe:
      httpGet:
        path: /livez
        port: 8080
      periodSeconds: 10
      timeoutSeconds: 2
      failureThreshold: 3
    readinessProbe:
      httpGet:
        path: /readyz
        port: 8080
      periodSeconds: 5
      timeoutSeconds: 2
      failureThreshold: 2
~~~

Các số chỉ minh họa: startup probe cho tối đa khoảng 150 giây để khởi động, liveness cần 3 lần thất bại theo lịch và readiness cần 2 lần thất bại theo lịch. Thời gian thực tế còn phụ thuộc scheduler, request timeout và môi trường. Chọn ngưỡng theo startup p99, GC pause, latency của hệ thống và SLA; không sao chép nguyên cho mọi service.

**Không trộn nghĩa:** readiness thất bại là thay đổi routing, không phải thông điệp “hãy restart”; liveness thất bại có thể dẫn đến restart, không phải thông điệp “đối tác tạm trả 503”.

## 4. Spring Boot Actuator: bật endpoint và nhóm health đúng cách

Thêm dependency Maven:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
~~~

Ví dụ `application.yml` cho web application:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info
  endpoint:
    health:
      probes:
        enabled: true
        add-additional-paths: true
      group:
        readiness:
          include: readinessState,shippingPartner
      show-details: never
      show-components: never
~~~

Các ý nghĩa quan trọng:

1. `probes.enabled: true` cho phép kiểm tra probe ngay cả khi không chạy trong môi trường Kubernetes được Boot phát hiện.
2. `add-additional-paths: true` có thể đưa endpoint probe ra **cổng ứng dụng chính** với đường mặc định `/livez` và `/readyz` trong môi trường/web server được hỗ trợ. Nó hữu ích khi actuator chạy trên cổng quản trị riêng.
3. Nhóm readiness **mặc định** thường chứa trạng thái `readinessState`, **không tự động cộng tất cả dependency indicators**. Đoạn `include: readinessState,shippingPartner` là quyết định rõ ràng rằng shipping partner góp phần vào readiness. Nếu không có bean mang ID `shippingPartner`, cấu hình group có thể báo lỗi khi khởi tạo/kiểm tra membership.
4. `show-details: never` và `show-components: never` là lựa chọn bảo mật để không lộ dữ liệu endpoint. Có thể cấu hình nhóm quản trị riêng cho người được phân quyền nếu cần chi tiết.
5. Khi API không thực sự phụ thuộc shipping partner để phục vụ các request còn lại, **không nên** đưa `shippingPartner` vào readiness chung; xem mục 6.

Đây là ví dụ **readiness bắt buộc phụ thuộc shipping partner**, không phải cấu hình tối ưu cho mọi hệ thống. Phần sau sẽ chỉ ra khi nào nên dùng dependency chỉ để cảnh báo.

### Cổng Actuator riêng và lỗi kết luận sai

Nếu dùng:

~~~yaml
management:
  server:
    port: 8081
~~~

`/actuator/health/readiness` có thể chạy qua cổng 8081 trong khi cổng ứng dụng 8080 không thể nhận HTTP request vì event loop hoặc servlet connector gặp sự cố. Kiểm tra thành công trên **management port** không nhất thiết xác nhận ứng dụng thực sự phục vụ request trên **application port**.

Khi yêu cầu probe xác thực đường nhận traffic, dùng `management.endpoint.health.probes.add-additional-paths=true` và trỏ probe tới `/livez`, `/readyz` trên cổng ứng dụng nếu mô hình triển khai hỗ trợ. Cần test bằng HTTP thực sự từ cùng network path tương đương ingress/Service.

Tránh đưa endpoint chi tiết chứa exception, URL nội bộ, pool name, connection string hoặc trạng thái tenant ra Internet. Health endpoints phục vụ orchestration và observability phải được giới hạn network/RBAC phù hợp.

## 5. HealthIndicator hoạt động ra sao?

`HealthIndicator` là SPI đồng bộ của Spring Boot Actuator. Nó thường được đăng ký dưới dạng Spring bean và trả `Health` có `Status` cùng details tùy chọn.

Các trạng thái chuẩn:

| Status | Ý nghĩa thực tế | HTTP status mặc định của health endpoint |
| --- | --- | --- |
| `UP` | Phép kiểm tra của contributor thành công | Thường 200 |
| `DOWN` | Phép kiểm tra thất bại | Mặc định 503 |
| `OUT_OF_SERVICE` | Cố ý rút khỏi phục vụ hoặc trạng thái không thể phục vụ | Mặc định 503 |
| `UNKNOWN` | Không xác định được trạng thái | Thường 200 theo mapping mặc định; không được coi là chứng minh khỏe |

**Status không phải chân lý tuyệt đối về tài nguyên.** Ví dụ `Health.up()` chỉ có nghĩa implementation của indicator chọn trả UP theo kiểm tra cụ thể. Endpoint mặc định có cơ chế aggregate trạng thái từ các contributor; khi có cả `UP` và `DOWN`, tổng có thể `DOWN` theo status order.

Khi muốn trạng thái như `DEGRADED` hoặc `MAINTENANCE`, cần **định nghĩa thứ tự aggregation và HTTP status mapping** phù hợp. Nếu cấu hình riêng HTTP mapping, hãy kiểm tra cả mapping cho `DOWN` và `OUT_OF_SERVICE`, vì tùy cấu hình, mapping custom có thể thay thế mặc định. Không thêm status tùy tiện rồi mặc định Kubernetes sẽ hiểu “degraded nhưng nhận traffic” như ý ứng dụng.

### Tên indicator và tên thành phần trong health group

Spring Boot thường suy ra ID từ bean name: bean tên `shippingPartnerHealthIndicator` tương ứng contributor ID `shippingPartner`, vì hậu tố `HealthIndicator` được bỏ khi đăng ký. Vì vậy, group `include: readinessState,shippingPartner` cần khớp chính xác với ID contributor thực tế, không phải tên class hoặc tên endpoint URL.

Có thể xem đóng góp trong environment test với health details được cấp quyền, hoặc kiểm tra registry/bean khi khởi động. Không đặt tên hai indicator trùng ID gây nhầm cấu hình.

## 6. Chọn dependency nào ảnh hưởng readiness?

Không có quy tắc “mọi dependency DOWN đều phải cho readiness DOWN”. Hãy phân loại theo **khả năng phục vụ lưu lượng mới** và vai trò của instance.

| Dependency | Khi mất kết nối | Readiness thường nên ra sao? | Lý do |
| --- | --- | --- | --- |
| PostgreSQL chứa trạng thái duy nhất cần cho mọi request của service | Không đọc/ghi được dữ liệu bắt buộc | Có thể `DOWN` | Instance không thể thực hiện chức năng chính |
| Redis chỉ dùng làm cache, đã có fallback database | Cache miss hoặc latency tăng | Thường giữ `UP` nếu fallback còn đáp ứng SLO | Rút mọi pod làm mất cả khả năng fallback |
| RabbitMQ trong service sử dụng transactional outbox | Chưa publish được event; SQL vẫn nhận đơn hàng | Có thể giữ `UP` cho HTTP ingress; alert relay lag riêng | Luồng vẫn có thể nhận job bền vững |
| RabbitMQ trong worker chỉ có một chức năng consume queue | Worker không nhận được job | Cần xem policy của worker/deployment | Readiness HTTP không phải chỉ số duy nhất cho worker không nhận ingress |
| Shipping API đối tác là lựa chọn tùy chọn | Không tính phí vận chuyển tức thì, có trạng thái “pending quote” | Thường `UP`/degraded qua metric, nếu hợp đồng cho phép | App có thể trả kết quả hữu ích |
| Shipping API bắt buộc cho mọi request nhận vào | Không có đường xử lý hợp lệ khi đối tác down | Có thể `DOWN` nếu routing tới instance khỏe hơn giúp ích | Đánh đổi với nguy cơ loại toàn bộ replicas |
| Một partition hoặc tenant cụ thể lỗi | Chỉ một phân khúc request bị ảnh hưởng | Readiness tổng thường không đủ độ phân giải | Cần routing theo tenant/partition hoặc lỗi nghiệp vụ riêng |

**Lưu ý hệ thống nhiều replica:** Nếu mọi pod phụ thuộc **cùng một** API bên ngoài và API đó down, việc đưa external API vào readiness có thể khiến **toàn bộ pod thành unready**, khiến Service không còn endpoint nào. Trong khi đó app có thể vẫn trả trang trạng thái hoặc xử lý các endpoint không phụ thuộc đối tác. Đây là một kiểu **cascading outage** do chính chính sách health gây ra.

Ngược lại, nếu một instance bị lỗi connection pool nội bộ, chỉ instance đó mất khả năng kết nối nhưng các instance khác khỏe, readiness dựa trên dependency của instance có thể giúp load balancer loại đúng pod hỏng. Cần phân biệt lỗi **cục bộ từng replica** với sự cố **toàn cục của dependency**.

### Ma trận quyết định

Trước khi đưa một indicator vào nhóm readiness, trả lời:

1. Có phải mọi lưu lượng qua **Service/Kubernetes endpoint** đều cần dependency đó để hoàn thành một cách chấp nhận được?
2. Có fallback, cache, outbox hoặc queue giúp hoàn thành yêu cầu hoặc tiếp nhận bền vững không?
3. Nếu dependency down trên mọi replica, việc loại hết pod sẽ làm hệ thống tốt hơn hay xấu hơn?
4. Có cơ chế phục hồi tự động, và pod còn có thể phục hồi trạng thái readiness nếu không nhận traffic không?
5. Chỉ cần alert cho dependency, hay thực sự cần **traffic gating**?
6. Một kiểm tra phụ thuộc có thể chạy nhanh, rẻ và an toàn khi 100 pod cùng gọi theo chu kỳ không?

Với dịch vụ đa chức năng, một **readiness chung** không thể biểu diễn “endpoint A hoạt động, endpoint B suy giảm” đầy đủ. Có thể cần tách deployment, routing, API degradation policy hoặc chỉ trả status lỗi theo từng endpoint thay vì rút toàn bộ app khỏi dịch vụ.

## 7. Tạo HealthIndicator cho HTTP dependency bắt buộc

Ví dụ một dịch vụ cần shipping API để xử lý tất cả request mới. Ta tạo **RestClient** dùng riêng cho health check với timeout ngắn, sau đó ánh xạ kết quả thành `Health`.

Phần cấu hình:

~~~yaml
app:
  shipping:
    base-url: https://shipping.internal.example
~~~

Bean client đồng bộ:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.web.client.RestClient;

@Configuration(proxyBeanMethods = false)
public class ShippingHealthClientConfiguration {

    @Bean("shippingHealthRestClient")
    RestClient shippingHealthRestClient(
            RestClient.Builder builder,
            @Value("${app.shipping.base-url}") String baseUrl) {

        var factory = new SimpleClientHttpRequestFactory();
        factory.setConnectTimeout(250);
        factory.setReadTimeout(500);

        return builder
                .baseUrl(baseUrl)
                .requestFactory(factory)
                .build();
    }
}
~~~

Các giới hạn 250/500 ms là ví dụ minh họa; lựa chọn phải phù hợp độ trễ, SLO và số replica. Dùng một client riêng cho health tránh đưa retry dài hoặc connection pool lớn vào mỗi probe, nhưng cũng cần kiểm soát overhead. Với request factory/transport do bạn tự tạo và chia sẻ, xác định quyền sở hữu tài nguyên theo framework thực tế.

Indicator:

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;

@Component("shippingPartnerHealthIndicator")
public class ShippingPartnerHealthIndicator implements HealthIndicator {

    private final RestClient client;

    public ShippingPartnerHealthIndicator(
            @Qualifier("shippingHealthRestClient") RestClient client) {
        this.client = client;
    }

    @Override
    public Health health() {
        try {
            client.get()
                    .uri("/internal/ready")
                    .retrieve()
                    .toBodilessEntity();

            return Health.up()
                    .withDetail("dependency", "shipping-partner")
                    .build();
        } catch (RestClientException ex) {
            // Không trả exception message, URL nội bộ, token hoặc stacktrace.
            return Health.down()
                    .withDetail("dependency", "shipping-partner")
                    .withDetail("reason", "request_failed")
                    .build();
        }
    }
}
~~~

Điều kiện của ví dụ là endpoint `/internal/ready` của đối tác **được thiết kế cho health probing**, trả mã HTTP phù hợp với mức sẵn sàng thực tế, không thực hiện side effect và được bảo vệ bằng auth/network đúng cách. Nếu `retrieve()` gặp HTTP 4xx/5xx hoặc lỗi transport, nó ném exception tương ứng và indicator trả DOWN.

**Những điều không nên làm trong indicator:**

- Không gửi lệnh tạo vận đơn, ghi database hay publish message thật để thử tính sống.
- Không gọi API có độ trễ vài chục giây trên mỗi readiness probe.
- Không bật retry vô hạn: health check phải kết thúc nhanh để orchestrator có quyết định đúng.
- Không ghi credentials, response body chứa thông tin khách hàng hoặc stacktrace vào `Health.details`.
- Không coi `200 OK` của endpoint ngoài là bằng chứng tất cả nghiệp vụ downstream chính xác.
- Không làm liveness fail vì dependency ngoài DOWN.

### Khi nào indicator nên trả UP dù phụ thuộc lỗi?

Nếu shipping quote chỉ là **tính năng tùy chọn**, một indicator dành cho dashboard vẫn có thể trả `DOWN` để người vận hành thấy lỗi, nhưng **không đưa nó vào readiness group**; hoặc dùng một cơ chế status riêng theo chính sách. Quan trọng là quyết định **tách tín hiệu dependency khỏi quyết định traffic**. Không che giấu lỗi bằng cách trả UP cho dependency down rồi không có metric/alert nào.

## 8. ReactiveHealthIndicator trong ứng dụng WebFlux

`HealthIndicator` là synchronous. Trong ứng dụng reactive, nếu check thực hiện I/O blocking, nó có thể giữ thread và ảnh hưởng sự đáp ứng của event loop. Spring Boot có thể adapt các indicator đồng bộ, nhưng với một dependency có client non-blocking thì **`ReactiveHealthIndicator`** là lựa chọn tự nhiên.

Ví dụ dùng `WebClient`:

~~~java
import java.time.Duration;
import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.ReactiveHealthIndicator;
import org.springframework.http.HttpStatusCode;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

@Component("shippingPartnerHealthIndicator")
public class ReactiveShippingPartnerHealthIndicator
        implements ReactiveHealthIndicator {

    private final WebClient client;

    public ReactiveShippingPartnerHealthIndicator(
            WebClient.Builder builder) {
        this.client = builder
                .baseUrl("https://shipping.internal.example")
                .build();
    }

    @Override
    public Mono<Health> health() {
        return client.get()
                .uri("/internal/ready")
                .retrieve()
                .toBodilessEntity()
                .timeout(Duration.ofMillis(600))
                .map(response -> Health.up().build())
                .onErrorResume(ex -> Mono.just(
                        Health.down().build()));
    }
}
~~~

Đây là **phương án thay thế** indicator đồng bộ ở mục 7, không đăng ký cả hai với cùng bean name/ID. Trong production, base URL, credentials và timeout cần đưa ra configuration, không hardcode; WebClient HTTP connector cũng phải được quản lý tài nguyên phù hợp. `timeout` bảo vệ khoảng chờ của publisher nhưng không chứng minh downstream đã hoàn thành nghiệp vụ trước khi bị cancel.

**Tránh một số lỗi reactive phổ biến:**

- Không gọi `.block()` trong `ReactiveHealthIndicator.health()`.
- Không `retryWhen` với nhiều attempt kéo dài hơn period/timeout của Kubernetes probe.
- Không return `Mono.never()` hoặc giữ connection không giải phóng khi cancellation xảy ra.
- Không dùng một client chia sẻ với luồng business rồi áp dụng retry/timeouts health bằng cách mutate client toàn cục giữa các request.
- Kiểm tra HTTP status như một phần hợp đồng: ví dụ một endpoint health luôn trả 200 cùng JSON `{"ready":false}` cần parse body, không thể chỉ dựa vào `toBodilessEntity()`.

## 9. Database, Redis, RabbitMQ và Kafka: chọn loại kiểm tra tương ứng

Spring Boot Actuator có những health contributors tự động theo **classpath/bean và cấu hình**, ví dụ `db` với JDBC `DataSource`, `redis` khi có Redis client, `rabbit` khi có hạ tầng RabbitMQ tương ứng. Không phải mọi thư viện broker hay adapter đều có indicator tự động với cùng mức chi tiết; cần kiểm tra version/starter thực tế.

| Phụ thuộc | Health check thường làm gì? | Không thể kết luận |
| --- | --- | --- |
| JDBC/DataSource | Lấy connection và/hoặc chạy validation query | Migration đúng, transaction nghiệp vụ không lỗi, pool đủ cho tải cao |
| Redis | Ping/lệnh nhẹ qua connection | Cache hit tốt, fallback đủ hiệu năng, mọi key đã đồng bộ |
| RabbitMQ | Kiểm tra kết nối/khả năng truy cập broker theo client | Queue binding đúng, consumer ACK, DLQ không tăng, publish confirm cho event cụ thể |
| Kafka | Có thể dùng custom AdminClient/metadata check nếu ứng dụng cung cấp | Consumer group lag nhỏ, partition đúng, event đã được xử lý |
| REST/gRPC partner | Ping endpoint/readiness API | Request nghiệp vụ cụ thể thành công hoặc không vi phạm quota |
| Object storage | Head/metadata request rất nhẹ theo policy | Có quyền PUT mọi key, checksum và lifecycle policy đúng |
| Spring Integration flow | Kiểm tra bean/channel/worker và metric trạng thái | Một message đã đi xuyên flow đến đích thành công |

### Health check của JDBC

Tránh chạy `SELECT COUNT(*) FROM orders` trên bảng hàng trăm triệu dòng mỗi vài giây để làm readiness. Query nhẹ như `SELECT 1` hoặc database validation API giảm overhead, nhưng vẫn không đo được nghiệp vụ. Khi database bị chậm vì lock hoặc pool cạn, check cũng cần giới hạn thời gian để không tăng thêm hàng chờ kết nối.

Nếu một ứng dụng kết nối nhiều `DataSource`, cần hiểu các contributor được gộp dưới `db` hay từng contributor theo bean/group; tên thành phần và kết quả group phụ thuộc Boot/config. Không giả định một `db=UP` đã xác nhận tất cả datasource của hệ thống.

### RabbitMQ là phụ thuộc khác database

Với một HTTP service sử dụng SQL outbox, broker outage có thể làm **outbox lag tăng** trong khi API vẫn nhận yêu cầu an toàn. Nếu biến `rabbit=DOWN` thành readiness DOWN, HTTP Service có thể mất toàn bộ endpoint mà không cải thiện khả năng publish của broker. Trong trường hợp này, giữ readiness cho HTTP ingress và cảnh báo theo outbox lag/oldest event age có thể đúng hơn.

Với worker chỉ tiêu thụ RabbitMQ, việc đánh giá “ready để nhận HTTP request” thường ít ý nghĩa. Nên theo dõi consumer count, queue age, redelivery, nack/requeue, DLQ và kết quả nghiệp vụ; readiness có thể thể hiện worker đã cấu hình xong và nhận queue, nhưng không phải thay thế metric consumer processing.

### Kafka consumer không giống Kafka producer

Một service có thể kết nối Kafka thành công nhưng consumer group có **lag hàng triệu record**. Health chỉ đo connectivity sẽ UP trong khi SLO xử lý event đã hỏng. Đánh giá chất lượng tiêu thụ bằng consumer lag, time since last successful processing, rebalance frequency, deserialization failures và DLQ/delivery policy; tránh biến lag ngắn thành liveness DOWN rồi restart liên tục.

## 10. Health check phải rẻ, giới hạn thời gian và không làm nặng thêm outage

Khi 100 pod probe một phụ thuộc mỗi 5 giây, hệ thống có thể tạo hàng chục request kiểm tra mỗi giây. Nếu dependency đang quá tải, retry nhiều lần ở mỗi probe có thể khiến chính cơ chế health thành **nguồn tăng tải**.

Một indicator tốt thường có:

1. **Giới hạn timeout** ngắn hơn `timeoutSeconds` của orchestrator với một khoảng dự phòng.
2. Không có hoặc rất ít retry; retry/backoff của health không giống retry request nghiệp vụ.
3. Endpoint downstream **không tạo side effect** và ít tốn tài nguyên.
4. Có thể dùng snapshot trạng thái đã được thu thập sẵn hoặc cache TTL ngắn nếu đo trực tiếp quá đắt.
5. Không giữ lock lớn, không mở transaction dài hoặc làm blocking I/O trên event loop.
6. Kết quả rõ ràng khi check timeout, exception, authorization failure hoặc dependency không còn cần thiết.
7. Khả năng phục hồi readiness khi dependency trở lại; không cần restart toàn bộ app.

Spring Boot có khả năng cache kết quả health endpoint bằng `management.endpoint.health.cache.time-to-live` theo phiên bản phù hợp. Cache giúp giảm chi phí nhưng làm tín hiệu chậm phản ánh sự cố/phục hồi; cần đặt TTL dưới ngưỡng chấp nhận và test tác động đến probes. Nếu cache ở tầng riêng, chú ý race/cache stale giữa trạng thái `UP` và `DOWN`.

### Circuit breaker và health indicator khác nhau

Circuit breaker bảo vệ **luồng request nghiệp vụ** trước downstream lỗi, có các trạng thái đóng/mở/half-open và policy retry/fallback. Health indicator là **tín hiệu quan sát/traffic decision**. Không dùng indicator để cưỡng bức đóng/mở circuit trong mỗi probe hoặc biến readiness check thành một lệnh nghiệp vụ.

Khi circuit breaker OPEN vì API ngoài hỏng:

- Dependency health có thể là DOWN hoặc có trạng thái riêng.
- Readiness vẫn có thể UP nếu API không bắt buộc cho mọi request và fallback còn trong SLO.
- Liveness thường vẫn UP nếu app hoạt động bình thường.
- Metric circuit state, fallback rate và business error rate phải được cảnh báo riêng.

## 11. Trả lỗi cho người dùng khi instance vẫn ready

Một instance có thể **readiness UP** và vẫn trả 503 cho một endpoint phụ thuộc hệ thống đang hỏng. Đây không phải mâu thuẫn: readiness là quyết định **nhận traffic ở cấp instance**, còn request-level status là **kết quả một nghiệp vụ cụ thể**.

Ví dụ:

| Tình huống | Hành vi request phù hợp | Readiness có thể |
| --- | --- | --- |
| Catalog từ Redis lỗi, fallback SQL thành công | Trả 200 với dữ liệu hợp lệ | UP |
| Shipping quote bắt buộc nhưng partner down | Trả 503/502/504 tùy loại lỗi và hợp đồng | UP nếu các endpoint khác còn phục vụ |
| API nhận việc xử lý async an toàn vào SQL/outbox | Trả 202 Accepted cùng job ID khi hợp đồng cho phép | UP dù broker đang mất |
| SQL chính của mọi request không truy cập được | Trả 503 cho request phụ thuộc | DOWN nếu instance không còn phục vụ chức năng chính |
| Đang graceful shutdown | Ngừng nhận request mới sau drain | OUT_OF_SERVICE/readiness DOWN |
| Một tenant bị khóa theo chính sách | Trả 403 hoặc business response phù hợp | UP cho tenant khác |

**Không đổi mọi lỗi downstream thành HTTP 500 chung chung**; phân biệt timeout, không sẵn sàng, input sai và nghiệp vụ không thể thực hiện. Tuy nhiên, HTTP status mapping là hợp đồng API riêng: 502/503/504 và retry-after phải phù hợp gateway, client behavior và SLO, không lựa chọn bằng một bảng máy móc.

Với `@RabbitListener`, khi downstream mất, message có thể retry, được delayed redelivery hoặc đi DLQ. Health indicator không được xem là cơ chế xác nhận/ack message. Những message cần xử lý đúng một lần về hiệu ứng nghiệp vụ vẫn phải có idempotency key, inbox và transaction phù hợp.

## 12. Một outage đi qua hệ thống như thế nào?

Giả sử `order-service` có ba replica và phụ thuộc chung vào shipping API, nhưng chỉ endpoint `/shipping/quote` mới cần shipping API. Nếu shipping API mất 5 phút:

~~~mermaid
sequenceDiagram
    participant P as Kubernetes probe
    participant O as order-service pod
    participant S as Shipping API
    participant C as HTTP client
    P->>O: GET /livez
    O-->>P: 200 UP
    P->>O: GET /readyz
    O-->>P: 200 UP (shipping không thuộc readiness chung)
    C->>O: GET /catalog
    O-->>C: 200 từ cache/DB
    C->>O: GET /shipping/quote
    O->>S: GET quote
    S--xO: 503 / timeout
    O-->>C: Lỗi đã phân loại hoặc fallback theo hợp đồng
    Note over O,S: Metrics: shipping_dependency_up=0; quote_failure_rate tăng
~~~

Đây là một quyết định có chủ đích: **giữ pod ready để phục vụ phần còn lại**, bảo vệ dependency bằng timeout/circuit breaker và dùng metric/alert báo outage.

Nếu thay vào đó readiness group của mọi pod bao gồm shipping API và đều trả DOWN, Kubernetes có thể bỏ cả ba pod khỏi Service. Ngay cả `GET /catalog` cũng mất đường đi. Không phải một lựa chọn “an toàn hơn” mặc định.

### Khi nào readiness DOWN là hợp lý?

Ví dụ một payment-command worker không thể thao tác database chính trên **chính instance** vì connection pool hỏng, trong khi các instance khác vẫn khỏe. Rút instance đó khỏi đường nhận request có thể giảm lỗi và điều phối lưu lượng sang replica khác. Hoặc một service chưa tải xong cấu hình bắt buộc; readiness REFUSING_TRAFFIC khi chưa warmup cũng là điều hợp lý.

Để xử lý sự cố toàn cục, nên có **degraded mode**, queue/partition phù hợp hoặc thông báo service-wide. Readiness không phải công cụ thay thế kiến trúc phục hồi khi mọi replica cùng bị ảnh hưởng.

## 13. Phân biệt health endpoint với metrics, tracing và logging

Một health endpoint thường chỉ cung cấp snapshot hữu hạn tại thời điểm probe. Nó không lý giải vì sao các message chưa được xử lý hay latency tăng qua nhiều phút.

| Tín hiệu | Trả lời câu hỏi | Ví dụ |
| --- | --- | --- |
| Health | Có thể chấp nhận traffic hoặc phụ thuộc đang đáp ứng phép kiểm tra không? | `readyz=UP`, `db=UP`, `shippingPartner=DOWN` |
| Metrics | Mức độ/diễn biến của lỗi là bao nhiêu? | Request error rate, retry count, consumer lag, outbox age |
| Tracing | Request cụ thể bị chậm/hỏng ở đâu? | Span HTTP → SQL → shipping API |
| Logs | Lỗi chi tiết nào đã xảy ra ở tầng nào? | SQL timeout, DNS failure, broker disconnect |
| Business reconciliation | Kết quả xử lý có đúng và đầy đủ không? | Số đơn đã commit, outbox chưa phát, event bị trùng |

### Metric có ích khi dependency down

- `dependency_health_status` theo **tên dependency được chuẩn hóa**, không theo raw URL/user ID.
- Health check latency và timeout count; số lỗi do 401/403 khác 5xx/timeout.
- HTTP downstream latency p95/p99, circuit breaker state, fallback rate.
- JDBC pool active/pending, transaction rollback, SQL query latency.
- Redis fallback miss/hit, DB load tăng sau cache outage.
- RabbitMQ publisher confirm failures, queue depth, DLQ depth, oldest message age.
- Kafka consumer lag, rebalances, last successful processing time.
- Outbox backlog, retry attempts, thời gian từ commit tới publish.
- Readiness transitions theo instance, số replica unready và tổng lỗi ingress.

Cẩn trọng cardinality: **không tạo metric tag chứa requestId, orderId, object key, email hoặc URL có query string**. Nên dùng các nhãn giới hạn như dependency name, operation, failure category và environment. Khi ghi log, thêm `traceId` và correlation ID nhưng che credential, payload cá nhân và connection string.

### Health indicator và alert không hoàn toàn đồng nhất

Chỉ dựa vào một lần `DOWN` có thể tạo alert giả vì network jitter. Alert thường cần thời gian duy trì, tỷ lệ thất bại, số instance hoặc tác động business. Ngược lại, một dependency chỉ là optional nên không ảnh hưởng readiness nhưng **vẫn cần alert** khi fallback rate vượt ngưỡng SLO.

Đừng chỉ dùng uptime/restart count làm thước đo hệ thống tích hợp khỏe. Một service có thể 100% live nhưng 0% hoàn thành việc vì outbox relay chết hoặc consumer bị kẹt.

## 14. Kiểm thử chính sách health chứ không chỉ kiểm thử code indicator

Unit test cho `HealthIndicator` có thể kiểm tra nó trả UP/DOWN theo response. Nhưng **integration test** phải xác minh nhóm health, HTTP status, security và hành vi khi downstream lỗi.

| Kịch bản | Thiết lập | Kỳ vọng |
| --- | --- | --- |
| Dependency trả 200 | Stub shipping readiness healthy | `shippingPartner=UP` |
| Dependency trả 503 | Stub shipping unavailable | `shippingPartner=DOWN` nhanh, không retry vô hạn |
| TCP connect refused | Tắt stub server | Indicator DOWN và kết thúc dưới deadline |
| Downstream treo | Stub không trả response | Check timeout trong ngân sách |
| Dependency trả 401/403 | Credentials/network policy sai | DOWN; không log token hoặc dùng credential admin thay thế |
| Optional dependency down | Không đưa vào readiness group | Readiness vẫn UP; metric/alert dependency DOWN |
| Required dependency down | Group include indicator bắt buộc | Readiness DOWN / HTTP 503 theo mặc định |
| Liveness khi external down | Chỉ livenessState trong liveness group | Liveness vẫn UP nếu app hoạt động bình thường |
| App startup chưa hoàn tất | Startup/warmup state chưa ready | Readiness không nhận traffic quá sớm |
| Graceful shutdown | Phát trạng thái REFUSING_TRAFFIC | Readiness rút traffic trước khi dừng xử lý |
| Management port riêng hỏng main port | Actuator port hoạt động, app listener lỗi | Probe trên main port phát hiện được vấn đề |
| Nhiều replica cùng mất partner | Simulate outage toàn cục | Không loại toàn bộ pod sai ý định |
| Indicator bị chậm | Stub delay dài hơn probe timeout | Không làm cạn worker/thread/event loop |
| Indicator lỗi unexpected | Ném RuntimeException trong check | Endpoint biểu thị lỗi theo handler, không rò stacktrace công khai |
| Security exposure | Gọi ngoài network không được phép | Không lộ component/details hoặc thông tin nhạy cảm |

### Một phép kiểm tra nhanh sau khi chạy

Với cấu hình đã bật probe trên application port, có thể kiểm tra từ môi trường test:

~~~bash
curl -i http://localhost:8080/livez
curl -i http://localhost:8080/readyz
curl -i http://localhost:8080/actuator/health
~~~

Kỳ vọng mẫu khi shipping bắt buộc đang DOWN:

~~~text
GET /livez -> 200, status UP
GET /readyz -> 503, status DOWN
GET /actuator/health -> tùy nhóm contributor, có thể 503
~~~

Phải chạy qua web server của ứng dụng thật, không chỉ MockMvc/Context test: cấu hình cổng, reverse proxy, Spring Security và network path có thể tạo kết quả khác. Đồng thời chạy test khi **tất cả pods** cùng gặp lỗi dependency để kiểm tra quyết định readiness không gây cascading outage.

### Test ReactiveHealthIndicator

Có thể dùng `StepVerifier` và HTTP stub tương ứng để xác minh reactive publisher hoàn tất và không block:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.Status;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class HealthPublisherContractTest {

    @Test
    void unavailableDependencyProducesDown() {
        Mono<Health> publisher = Mono.just(Health.down().build());

        StepVerifier.create(publisher)
                .expectNextMatches(health ->
                        Status.DOWN.equals(health.getStatus()))
                .verifyComplete();
    }
}
~~~

Đây là ví dụ **contract của publisher**, chưa gọi HTTP thật. Test ứng dụng quan trọng hơn là thay WebClient bằng một HTTP stub server có thể phản hồi 200, 503 hoặc treo, rồi assert signal của `ReactiveShippingPartnerHealthIndicator` và phản hồi endpoint readiness đã được tổng hợp.

## 15. Troubleshooting: endpoint health báo DOWN hoặc báo UP sai

| Triệu chứng | Khả năng nguyên nhân | Hướng kiểm tra |
| --- | --- | --- |
| `/actuator/health` DOWN nhưng `/readyz` UP | Readiness chỉ chứa `readinessState`, không chứa dependency lỗi | Xem health group membership; quyết định có nên thêm hay không |
| Liveness DOWN khi Redis/RabbitMQ lỗi | Đã đưa external indicator vào liveness | Bỏ phụ thuộc xa khỏi liveness, kiểm tra chính sách |
| Mọi pod unready cùng lúc | Readiness phụ thuộc global service bị outage | Phân loại optional/required và đánh giá cascading failure |
| Endpoint health timeout | Check blocking/quá chậm hoặc lặp retry | Giới hạn timeout, tối giản check, tránh event loop block |
| Health UP nhưng yêu cầu nghiệp vụ lỗi | Check chỉ ping TCP/SELECT 1, bỏ qua schema/quyền/queue lag | Bổ sung business metrics và integration tests |
| Indicator tự viết không xuất hiện | Bean không được scan, sai tên, chưa có Actuator | Kiểm tra bean/context, contributor ID, health groups |
| Readiness group fail khi startup | Include tên contributor không có trong app | Kiểm tra ID `shippingPartner`, config trong profiles |
| Probe 200 trên management port nhưng app không nhận traffic | Check đi cổng 8081 độc lập cổng 8080 | Dùng additional paths trên main port |
| Health endpoint lộ URL/stacktrace | `show-details`/authorization cấu hình không đúng | Ẩn details, giới hạn mạng và quyền truy cập |
| Sau outage health vẫn DOWN dù service đã phục hồi | TTL/cache hoặc circuit/connection không cập nhật | Kiểm tra health cache, connector, thời hạn retry và pool |
| Kafka báo UP nhưng consumer lag lớn | Check chỉ dựa connectivity | Alert theo lag và processing progress |
| RabbitMQ báo UP nhưng message không xử lý | Consumer chết, queue binding sai hoặc DLQ tăng | Quan sát consumer metrics, queue age, DLQ, replay |
| Readiness nhấp nháy liên tục | Probe quá nhạy, jitter, dependency chập chờn | Giới hạn timeout, hysteresis/caching cân nhắc và failureThreshold |

### Quy trình phân tích một dependency outage

1. **Xác định tầng lỗi:** process, application port, internal state, dependency connection hay nghiệp vụ.
2. **Đọc health groups riêng:** liveness, readiness, contributor cụ thể; không chỉ xem HTTP `/actuator/health` tổng.
3. **Đối chiếu metrics:** lỗi HTTP/SQL/broker, latency, queue lag, circuit breaker, connection pool.
4. **Kiểm tra blast radius:** một pod, một AZ/region, một tenant hay tất cả replicas.
5. **Đánh giá fallback:** còn phục vụ những endpoint nào; nếu toàn cluster unready có giảm hay tăng tác hại?
6. **Chọn hành động:** restart chỉ cho hỏng nội bộ không tự phục hồi; traffic gating cho pod không ready; fallback/queue/retry/alert cho external outage.
7. **Xác minh phục hồi:** readiness trở lại UP, request nghiệp vụ thành công, outbox/queue backlog được xử lý và không có duplicate side effect.

## 16. Những câu hỏi thường bị hiểu sai

**“Tại sao database DOWN nhưng `/actuator/health/liveness` vẫn UP?”**

Đó có thể là chính sách đúng. JVM/ứng dụng còn hoạt động và có thể hồi phục sau khi database trở lại. Liveness tập trung vào tình trạng nội bộ không thể tự phục hồi, không dùng làm tấm gương cho mọi dependency.

**“Tại sao `/actuator/health` DOWN mà Kubernetes vẫn nhận pod là ready?”**

Nhóm readiness mặc định thường dùng `readinessState` chứ không tự gộp tất cả contributor. Phải xem `/actuator/health/readiness`, nhóm `include` và đường probe thực tế; Kubernetes không tự đọc status của endpoint tổng nếu manifest trỏ readiness group.

**“Một dependency bắt buộc DOWN thì luôn phải readiness DOWN?”**

Không luôn. Nếu mọi replica cùng phụ thuộc external service đó, việc đánh tất cả unready có thể khiến không còn endpoint nào, bao gồm chức năng fallback/quản trị. Quyết định phụ thuộc tuyến traffic và SLO, không chỉ mức độ quan trọng trên giấy.

**“Chỉ cần kết nối TCP RabbitMQ thành công là integration flow khỏe?”**

Không. Message có thể đang backlog, dead-letter, sai routing hoặc consumer không ack. Theo dõi publish confirm, queue age, consumer progress, DLQ và nghiệp vụ hoàn tất.

**“Chỉ cần health indicator trả UP tức là có thể xử lý một request chắc chắn thành công?”**

Không. Health là một phép kiểm tra tại một thời điểm; ngay sau đó phụ thuộc có thể lỗi. Client vẫn phải xử lý timeout, retry an toàn và kết quả không rõ trạng thái.

**“Có nên gọi endpoint ghi dữ liệu để health check?”**

Không nên. Health check lặp lại thường xuyên và trên nhiều replica; viết dữ liệu thật dễ tạo side effect, tăng tải, trùng lặp và chi phí. Nếu cần kiểm tra canary end-to-end có side effect, nên triển khai một cơ chế giám sát riêng với identity, dữ liệu test và cleanup.

**“Health DOWN thì service phải tự restart?”**

Không. Restart là hành vi điều phối dựa trên liveness và policy. Readiness DOWN chỉ rút instance khỏi routing, còn dependency indicator DOWN có thể chỉ để quan sát/cảnh báo.

### Checklist triển khai

1. Phân biệt **liveness**, **readiness** và health của từng phụ thuộc; không dùng một trạng thái chung cho mọi hành động.
2. Bật Actuator và probes đúng endpoint/cổng; nếu management server khác port app, kiểm tra additional paths và network route.
3. Chọn contributor bắt buộc cho readiness **dựa trên traffic và khả năng fallback**, không theo danh sách tất cả dependency.
4. Giữ external dependency ra khỏi liveness theo mặc định; không restart hàng loạt khi Redis/partner chung bị lỗi.
5. Indicator phải rẻ, ít side effect, có timeout ngắn, không retry vô hạn, không log token hoặc exception nhạy cảm.
6. Với WebFlux, dùng `ReactiveHealthIndicator` và I/O non-blocking khi phù hợp.
7. Thiết kế degraded mode/circuit breaker/outbox để app còn phục vụ khi một dependency tùy chọn bị outage.
8. Theo dõi metrics lỗi/latency, pool, queue lag, DLQ, outbox và business completion ngoài health status.
9. Thử nghiệm khi một pod lỗi, khi **toàn bộ replica** gặp lỗi ngoài, và khi dependency phục hồi; đo hành vi Kubernetes.
10. Xác minh các đường lỗi của nghiệp vụ riêng: ACK, idempotency, retry, SQL transaction và event delivery không được thay thế bằng probe UP/DOWN.

### Tài liệu tham khảo theo phiên bản

- [Spring Boot Reference – Endpoints: Health Information](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html#actuator.endpoints.health): HealthIndicator, Health groups, status và bảo mật.
- [Spring Boot Reference – Kubernetes Probes](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html#actuator.endpoints.kubernetes-probes): liveness/readiness, readiness group và additional paths.
- [Spring Boot API – HealthIndicator](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/actuate/health/HealthIndicator.html): SPI đồng bộ.
- [Spring Boot API – ReactiveHealthIndicator](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/actuate/health/ReactiveHealthIndicator.html): SPI reactive.
- [Kubernetes Docs – Configure Liveness, Readiness and Startup Probes](https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/): hành vi restart và routing theo probe.

**Ghi nhớ:** Khi một phụ thuộc không sẵn sàng, **HealthIndicator là tín hiệu**, không phải hành động tự động và càng không phải transaction/guarantee nghiệp vụ. Thiết kế readiness dựa trên khả năng nhận traffic, giữ liveness cho sức khỏe nội bộ, dùng fallback/outbox/idempotency khi thích hợp, và quan sát những thông tin mà một boolean UP/DOWN không bao giờ biểu diễn hết.

