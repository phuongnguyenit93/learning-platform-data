# Zipkin exporter trong Spring Boot: cấu hình và kiểm chứng distributed traces

> **Chương:** Tracer implementation  
> **Bài:** Zipkin exporter  
> **Module:** `SPRING_BOOT_OBSERVABILITY` — Thiết lập observability cho Spring Boot bằng Micrometer Observation, metrics, logs và distributed tracing. Học propagation ngữ cảnh, tag/cardinality, exporter, sampling và liên kết tín hiệu để điều tra lỗi, độ trễ và hành vi ứng dụng trên môi trường thực.

## 1. Từ span trong ứng dụng đến trace trên Zipkin

Một ứng dụng Spring Boot có thể tạo span khi nhận HTTP request, gọi dịch vụ khác hoặc chạy một bước nghiệp vụ. Nhưng **span được tạo trong tiến trình chưa có nghĩa trace đã xuất hiện trên giao diện Zipkin**. Hệ thống cần một đường vận chuyển từ tracer đến nơi lưu trữ và truy vấn trace.

**Zipkin exporter** là thành phần chuyển các span đã kết thúc từ tracing implementation của ứng dụng tới Zipkin collector. Trong stack Spring Boot dùng Micrometer Tracing, một lựa chọn phổ biến là Micrometer Tracing + Brave + Zipkin Reporter:

- **Micrometer Tracing** cung cấp API tracing tích hợp với Observation.
- **Brave bridge** nối API Micrometer Tracing với tracer Brave.
- **Zipkin Reporter** nhận span từ Brave, gom và gửi span tới Zipkin collector theo giao thức Zipkin.
- **Zipkin server** nhận span, lưu trữ theo cấu hình và cung cấp API/UI để tìm trace.

~~~mermaid
flowchart LR
    A["Spring MVC / WebClient / Observation"] --> B["Micrometer Observation"]
    B --> C["Micrometer Tracing"]
    C --> D["Brave bridge / Tracer"]
    D --> E["Zipkin Reporter"]
    E -->|"HTTP POST /api/v2/spans"| F["Zipkin Collector"]
    F --> G["Zipkin Storage"]
    G --> H["Zipkin UI / Search API"]
~~~

Đường đi này có thể được mở rộng khi ứng dụng dùng OpenTelemetry bridge hoặc OpenTelemetry Collector, nhưng cấu hình và exporter khác nhau. Bài này tập trung vào lựa chọn **Micrometer Tracing + Brave + Zipkin Reporter** thường gặp trong Spring Boot 3.x.

Mục tiêu là cấu hình exporter, tạo trace có nhiều spans, kiểm tra dữ liệu trên Zipkin, hiểu sampling/propagation và chẩn đoán trường hợp span không tới backend.

## 2. Phân biệt tracer, bridge, reporter và Zipkin server

Các thành phần này có trách nhiệm khác nhau; thiếu một mắt xích thì trace có thể không tới UI.

| Thành phần | Trách nhiệm | Ví dụ |
| --- | --- | --- |
| **Instrumentation** | Tạo Observation/span tại một ranh giới công việc | Spring MVC server, HTTP client, service nghiệp vụ |
| **Micrometer Tracing** | API tracing thống nhất và tích hợp Observation | Tracer, Span, BaggageManager |
| **Tracing bridge** | Kết nối Micrometer Tracing với implementation cụ thể | micrometer-tracing-bridge-brave |
| **Tracer** | Tạo span, quản lý trace/span context, sampling | Brave tracer |
| **Reporter/exporter** | Chuyển span hoàn tất sang đích nhận | Zipkin Reporter |
| **Zipkin collector** | Nhận payload span và chuyển sang storage | Zipkin server |
| **Storage** | Lưu trace theo cấu hình triển khai | In-memory, Elasticsearch, Cassandra hoặc backend tương thích tùy môi trường |
| **Zipkin UI** | Tìm trace và hiển thị span waterfall | Web UI thường ở cổng 9411 |

**Reporter không tạo ra instrumentation.** Nếu không có instrumentation nào tạo span, Zipkin không có dữ liệu để hiển thị. Ngược lại, ứng dụng có thể tạo span nhưng reporter không xuất được vì sai endpoint, mạng, sampling hoặc lỗi kết nối.

Zipkin server cũng không tự làm cho HTTP client/server trong ứng dụng được instrument. Cần starter, auto-configuration hoặc integration tương ứng để các ranh giới này tạo spans và truyền trace context.

## 3. Dependency Maven cho Spring Boot 3.x với Brave

Ví dụ dùng Spring Boot parent/BOM để quản lý phiên bản tương thích:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>

    <dependency>
        <groupId>io.micrometer</groupId>
        <artifactId>micrometer-tracing-bridge-brave</artifactId>
    </dependency>

    <dependency>
        <groupId>io.zipkin.reporter2</groupId>
        <artifactId>zipkin-reporter-brave</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
</dependencies>
~~~

Ý nghĩa:

- `spring-boot-starter-actuator` cung cấp nền tảng management và tích hợp Observation.
- `micrometer-tracing-bridge-brave` cung cấp bridge giữa Micrometer Tracing và Brave.
- `zipkin-reporter-brave` tích hợp reporter Zipkin với Brave, cho phép gửi spans đến Zipkin.
- `spring-boot-starter-web` chỉ phục vụ ví dụ REST MVC; ứng dụng WebFlux dùng starter phù hợp khác.

Dùng BOM của Spring Boot để chọn các phiên bản Micrometer/Brave/Reporter đồng bộ. Tránh tự nâng riêng một dependency tracing khi chưa kiểm tra compatibility của phiên bản Boot đang chạy. Tên artifact, property và auto-configuration có thể đổi theo major version; ví dụ trong bài nhắm Spring Boot 3.x.

**Không thêm đồng thời nhiều bridge tracing** như Brave bridge và OpenTelemetry bridge vào cùng ứng dụng nếu chưa có thiết kế đặc biệt. Hai implementation cùng được cấu hình có thể gây xung đột hoặc khiến auto-configuration không còn rõ ràng.

## 4. Chạy Zipkin server trong môi trường học tập

Cách đơn giản để thử nghiệm là chạy Zipkin server dưới dạng container. Ví dụ Docker:

~~~bash
docker run --name zipkin -d -p 9411:9411 openzipkin/zipkin
~~~

Sau khi container sẵn sàng, mở:

~~~text
http://localhost:9411
~~~

UI thường được cung cấp qua cổng 9411; collector API v2 nhận spans tại:

~~~text
http://localhost:9411/api/v2/spans
~~~

Có thể kiểm tra server có phản hồi bằng:

~~~bash
curl -i http://localhost:9411/health
~~~

Endpoint health và cách trả response có thể khác theo bản phân phối/cấu hình. Mục tiêu là xác nhận container đang chạy và ứng dụng có thể truy cập collector; chỉ mở được UI không chứng minh exporter đã gửi spans.

### 4.1. Docker Compose minh họa

~~~yaml
services:
  zipkin:
    image: openzipkin/zipkin
    container_name: zipkin
    ports:
      - "9411:9411"
~~~

Chạy:

~~~bash
docker compose up -d zipkin
docker compose ps
~~~

Trong production, không nên mặc định storage mặc định của container học tập là giải pháp lưu trữ lâu dài. Chọn storage backend, persistence, backup, retention, capacity và kiểm soát truy cập theo yêu cầu vận hành. Cần cố định version/image tag trong môi trường triển khai được quản lý thay vì dựa vào tag thay đổi.

## 5. Cấu hình Zipkin endpoint trong Spring Boot

Ví dụ `application.yml` cho Spring Boot 3.x:

~~~yaml
spring:
  application:
    name: order-service

management:
  tracing:
    sampling:
      probability: 1.0
  zipkin:
    tracing:
      endpoint: http://localhost:9411/api/v2/spans
~~~

Giải thích:

- `spring.application.name` cung cấp định danh service được dùng trong metadata/resource/span tags phù hợp với stack.
- `management.tracing.sampling.probability` quyết định xác suất sampling đầu trace trong cấu hình đơn giản. Giá trị 1.0 có nghĩa chọn gần như mọi trace trong môi trường minh họa.
- `management.zipkin.tracing.endpoint` là endpoint nhận spans của Zipkin, thường là đường dẫn v2 `/api/v2/spans`.
- Reporter được auto-configure khi dependencies và property phù hợp; không cần tạo `AsyncReporter` thủ công trong từng service.

**Lưu ý về mạng container:** nếu ứng dụng Spring Boot cũng chạy trong Docker Compose cùng Zipkin, `localhost` từ container ứng dụng trỏ về chính container ứng dụng. Khi đó dùng hostname service, ví dụ `http://zipkin:9411/api/v2/spans`. Nếu ứng dụng chạy trên host còn Zipkin publish cổng ra host, `localhost:9411` có thể phù hợp.

Không expose collector ra Internet mà không có network control hoặc lớp bảo vệ thích hợp. Payload Zipkin có thể chứa service topology, URL/peer metadata, exception details và attributes của ứng dụng.

## 6. Tạo một trace có spans trong ứng dụng Spring Boot

Để exporter có dữ liệu gửi đi, ứng dụng phải tạo spans. Spring Boot có thể tự instrument HTTP server/client trong các integration được hỗ trợ. Ta bổ sung một observation nghiệp vụ để minh họa span nội bộ.

### 6.1. Controller và service

~~~java
package example.orders;

import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import org.springframework.stereotype.Service;

@Service
public class OrderService {
    private final ObservationRegistry observationRegistry;

    public OrderService(ObservationRegistry observationRegistry) {
        this.observationRegistry = observationRegistry;
    }

    public String createOrder(String channel) {
        return Observation.createNotStarted(
                "orders.create", observationRegistry)
            .contextualName("create order")
            .lowCardinalityKeyValue("channel", normalizeChannel(channel))
            .observe(() -> {
                reserveInventory();
                return "created";
            });
    }

    private void reserveInventory() {
        // Mô phỏng thao tác nghiệp vụ.
    }

    private static String normalizeChannel(String value) {
        if ("web".equals(value)) return "web";
        if ("mobile".equals(value)) return "mobile";
        return "other";
    }
}
~~~

~~~java
package example.orders;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class OrderController {
    private final OrderService orderService;

    public OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @GetMapping("/orders")
    public String create(@RequestParam(defaultValue = "web") String channel) {
        return orderService.createOrder(channel);
    }
}
~~~

Khi tracing được cấu hình:

1. HTTP server instrumentation có thể tạo server span cho `GET /orders`.
2. Observation có tên `orders.create` tạo span nội bộ nếu tracing handler hoạt động.
3. Span nghiệp vụ có thể là child của server span nếu current observation/trace context được duy trì.
4. Khi các span kết thúc và được sample, reporter xuất chúng đến Zipkin.

`Observation.observe(...)` phù hợp cho công việc đồng bộ. Với các bước bất đồng bộ, phải quản lý lifecycle và context propagation theo cơ chế framework, tránh kết thúc span trước khi công việc hoàn tất.

### 6.2. Gọi endpoint để tạo traffic

~~~bash
curl "http://localhost:8080/orders?channel=web"
curl "http://localhost:8080/orders?channel=mobile"
~~~

Gọi nhiều lần trong môi trường học tập, sau đó mở Zipkin UI và tìm service `order-service` hoặc operation tương ứng. Nếu search chưa thấy trace, xem sampling, reporter logs và endpoint trước khi thay đổi code instrument.

## 7. Sampling: vì sao không phải request nào cũng xuất hiện trên Zipkin?

Tracing có thể tạo một trace cho mỗi request, nhưng **sampler** quyết định trace nào được giữ lại và xuất đi.

~~~yaml
management:
  tracing:
    sampling:
      probability: 0.1
~~~

Ứng dụng có thể chọn khoảng 10% trace đầu vào theo cách sampling được implementation hỗ trợ. Đây là xác suất thống kê, không phải cam kết chính xác cứ 10 request thì có đúng một trace.

| Giá trị minh họa | Ý nghĩa | Khi cân nhắc |
| --- | --- | --- |
| 1.0 | Lấy mẫu toàn bộ trace theo chính sách xác suất | Local/test, traffic thấp |
| 0.1 | Lấy mẫu một phần | Môi trường có traffic cao khi cần cân bằng chi phí |
| 0.01 | Lấy mẫu ít hơn | Hệ thống có lượng trace lớn, cần cân nhắc thêm lỗi hiếm |

Các giá trị này chỉ là ví dụ, không phải khuyến nghị cố định cho mọi môi trường. Nếu đầu trace không được sample, spans con thường không được xuất theo trace đó trong cấu hình head-based phổ biến. Do đó **không tìm thấy một request trong Zipkin không chứng minh ứng dụng không instrument**.

### 7.1. Sampling không giống metrics step hoặc scrape

- Sampling chọn **trace** nào được ghi lại.
- Step chọn **kỳ publish** của một số registry metrics.
- Prometheus scrape interval chọn lúc server metrics được kéo.
- Collector batch timeout quyết định thời gian gom telemetry trước khi gửi tiếp.

Giảm sampling traces không tự động giảm Counter/Timer metrics. Có thể có đủ metrics tổng hợp nhưng chỉ có một phần traces chi tiết; đây là thiết kế thường gặp.

## 8. Propagation: nối spans giữa nhiều dịch vụ

Giả sử `order-service` gọi `inventory-service`. Để hai spans ở cùng trace, client phải inject trace context vào request và server phải extract nó.

~~~mermaid
sequenceDiagram
    participant Client
    participant Order as order-service
    participant Zipkin
    participant Inventory as inventory-service
    Client->>Order: GET /orders
    Note over Order: Tạo server span và orders.create
    Order->>Inventory: HTTP request + tracing headers
    Note over Inventory: Extract context và tạo server span
    Inventory-->>Order: Response
    Order-->>Client: Response
    Order-->>Zipkin: Export spans đã sample
    Inventory-->>Zipkin: Export spans đã sample
~~~

Các định dạng propagation phổ biến gồm:

- **B3 single header:** thường dùng header `b3` chứa thông tin trace/span và sampling.
- **B3 multi-header:** dùng nhóm header như `X-B3-TraceId`, `X-B3-SpanId`, `X-B3-Sampled`.
- **W3C Trace Context:** dùng `traceparent`, có thể kèm `tracestate`.

Brave và Micrometer Tracing hỗ trợ các dạng propagation tương ứng tùy cấu hình. Hai dịch vụ cần thống nhất định dạng được chấp nhận/phát ra. Nếu upstream chỉ gửi B3 nhưng downstream chỉ extract W3C, trace có thể bị tách thành hai trace riêng.

Với HTTP client trong Spring, dùng integration/builder được framework instrument để header được inject tự động. Nếu tự tạo client bỏ qua builder/configuration, không mặc định propagation vẫn hoạt động.

### 8.1. Kiểm tra headers

Trong môi trường local/test, có thể dùng proxy hoặc server test để xem request có header trace context phù hợp. Không log mọi header authorization/cookie. Chỉ quan sát các header tracing được phép và không đưa chúng thành metrics labels.

**Trace context không phải baggage tùy ý.** Chỉ truyền thêm thông tin nghiệp vụ qua baggage khi có quy định rõ về propagation, bảo mật và kích thước header. Một span attribute đơn lẻ không tự động được inject vào request downstream.

## 9. Zipkin span model: service, operation, kind, tags và annotations

Zipkin hiển thị span với các trường chính, có thể được ánh xạ từ tracing implementation và semantic conventions:

| Trường | Ý nghĩa |
| --- | --- |
| `traceId` | Định danh trace |
| `id` | Định danh span |
| `parentId` | Span cha, nếu có |
| `name` | Operation/span name |
| `kind` | CLIENT, SERVER, PRODUCER, CONSUMER hoặc INTERNAL tùy mô hình |
| `timestamp` | Thời điểm bắt đầu |
| `duration` | Thời lượng theo đơn vị định nghĩa của Zipkin |
| `localEndpoint` | Service/local endpoint tạo span |
| `remoteEndpoint` | Peer/destination khi có |
| `tags` | Key–value mô tả span |
| `annotations` | Mốc sự kiện theo mô hình Zipkin; cách ánh xạ phụ thuộc instrumentation/reporter |

Tên operation ngắn và ổn định giúp tìm kiếm. Tránh nhúng ID đơn hàng, user ID hoặc URL path chứa ID vào span name vì sẽ làm tên biến thiên, gây khó truy vấn và có thể lộ dữ liệu. Dùng route template hoặc tên operation ổn định.

### 9.1. Tags và cardinality

Một span có thể mang thuộc tính phân biệt từng lần thực thi, nhưng lượng dữ liệu trên backend vẫn cần kiểm soát. Với metrics, đặc biệt tránh chuyển ID riêng thành labels; với tracing, chỉ ghi high-cardinality attributes khi thực sự cần và được phép.

~~~java
Observation.createNotStarted("inventory.reserve", registry)
    .lowCardinalityKeyValue("channel", "web")
    .highCardinalityKeyValue("reservation.attempt_id", attemptId)
    .observe(this::reserve);
~~~

`channel` thích hợp để tổng hợp metric; `reservation.attempt_id` có thể giúp điều tra span cụ thể, nhưng cần đánh giá chính sách dữ liệu, retention và indexing của Zipkin/backend. Không giả định mọi UI sẽ index mọi tag với cùng hiệu năng.

## 10. Reporter và batch: span được gửi theo cách nào?

Trong stack Brave + Zipkin Reporter, spans đã hoàn tất thường được chuyển cho reporter bất đồng bộ. Reporter có thể gom nhiều spans vào một payload thay vì thực hiện một HTTP request riêng cho mỗi span.

Một số khái niệm:

- **Sender** biết cách gửi payload tới Zipkin collector qua HTTP hoặc transport được hỗ trợ.
- **Reporter** nhận span và điều phối việc gửi.
- **Queue/buffer** giữ các span chờ được gửi trong giới hạn cấu hình.
- **Batching** gom nhiều spans thành một lô để giảm số request.
- **Flush/shutdown** cố gắng đẩy dữ liệu còn chờ trước khi tiến trình dừng, tùy vòng đời và cấu hình.

Batching giảm overhead mạng nhưng có thể thêm một khoảng trễ ngắn trước khi span xuất hiện trên UI. Khi queue đầy hoặc exporter lỗi, spans có thể bị drop tùy chính sách. Không giả định reporter cung cấp bảo đảm exactly-once hoặc lưu trữ bền vững lâu dài.

### 10.1. Không nhầm batch reporter với sampling

Một trace đã được sampler chọn vẫn có thể chưa thấy ở Zipkin vì reporter đang đợi batch, collector chưa nhận hoặc storage/UI chưa cập nhật. Ngược lại, trace bị loại từ sampling sẽ không được reporter gửi, dù endpoint Zipkin đang khỏe.

Khi chẩn đoán, phải phân biệt **không được sample**, **đang chờ batch**, **gửi thất bại**, **collector nhận nhưng storage/search chưa thấy**.

## 11. Kiểm tra Zipkin bằng UI và API

Sau khi gọi endpoint ứng dụng, mở Zipkin UI ở `http://localhost:9411`.

Quy trình kiểm tra:

1. Chọn service name `order-service` (hoặc tên service được cấu hình thực tế).
2. Chọn operation `GET /orders` hoặc `orders.create` tùy spans đã instrument.
3. Chọn khoảng thời gian đủ rộng quanh lúc gửi request.
4. Bấm tìm kiếm, mở trace để xem waterfall.
5. Kiểm tra `traceId`, `spanId`, parent-child relation, start time và duration.
6. Mở từng span để xem kind và tags.
7. Nếu có lỗi, xem tags/error information theo cách reporter/instrumentation ánh xạ.

### 11.1. Gửi truy vấn qua Zipkin API

Zipkin cung cấp API tìm traces. Ví dụ minh họa:

~~~bash
curl "http://localhost:9411/api/v2/traces?serviceName=order-service&limit=10"
~~~

API/param chi tiết có thể thay đổi theo phiên bản Zipkin; hãy tham khảo API tương ứng với server đang chạy. Kết quả thường là danh sách các trace chứa các span liên quan. Không dùng endpoint API để lấy dữ liệu production nếu chưa kiểm soát quyền truy cập.

### 11.2. Nếu không có trace

Kiểm tra theo thứ tự:

- Ứng dụng có tạo span hay chưa? Có instrumentation HTTP hoặc Observation?
- Dependency bridge và reporter đã được nạp đúng không?
- Sampling probability có loại trace đó không?
- Zipkin endpoint có đúng host/port/path từ network namespace của ứng dụng?
- Reporter có log lỗi kết nối/HTTP response không?
- Zipkin collector có nhận payload? Storage có ghi? UI có lọc sai service/time range?
- Trace context có được propagate qua các dịch vụ không?

Không tăng sampling lên 100% hoặc tạo spans thủ công ở mọi nơi trước khi xác định lỗi nằm ở đâu. Điều đó có thể tăng tải và làm trùng instrumentation.

## 12. Xử lý span error với Zipkin

Zipkin có thể biểu diễn lỗi thông qua tags/annotations tùy mô hình dữ liệu và reporter; cách hiển thị không nhất thiết giống trường `status=ERROR` của OpenTelemetry. Khi dùng Brave bridge, một exception được báo cho Observation có thể được ánh xạ thành tag/event tương ứng theo bridge/reporter.

Ví dụ với Micrometer Observation:

~~~java
Observation observation = Observation.createNotStarted(
        "payments.authorize", observationRegistry).start();

try (Observation.Scope scope = observation.openScope()) {
    authorizePayment();
} catch (RuntimeException ex) {
    observation.error(ex);
    throw ex;
} finally {
    observation.stop();
}
~~~

Đoạn code báo lỗi cho Observation, để handlers phù hợp ghi nhận lỗi và hoàn tất span. Nó không tự ghi log ứng dụng, cũng không bảo đảm mọi backend hiển thị một trường tên `error=true`. Cần xem span data thực tế được gửi.

**Phân biệt lỗi nghiệp vụ và lỗi kỹ thuật.** Một khoản thanh toán bị từ chối theo quy tắc có thể là kết quả hợp lệ chứ không phải lỗi hạ tầng. Hãy sử dụng outcome/tag có tập giá trị hữu hạn để biểu diễn nghiệp vụ; chỉ báo exception/span error khi hoạt động thực sự thất bại theo semantics đã định nghĩa.

Không đưa exception message tự do, token, request/response body hoặc dữ liệu nhạy cảm vào tags. Traces có thể được lưu lâu và chia sẻ với nhiều nhóm vận hành.

## 13. Kết hợp Zipkin trace với metrics và logs

Zipkin giúp hiểu đường đi và thời lượng, nhưng không thay thế metrics hoặc logs:

~~~mermaid
flowchart TD
    A["Metrics: error rate / p95 tăng"] --> B["Khoanh vùng service, route, thời gian"]
    B --> C["Zipkin: tìm trace đã sample"]
    C --> D["Xem span waterfall và downstream"]
    C --> E["Đọc span tags / error metadata"]
    D --> F["Tìm log theo traceId/spanId"]
    E --> F
    F --> G["Hình thành giả thuyết và xác nhận"]
    G --> H["Theo dõi lại metrics sau sửa"]
~~~

- **Metrics** cho biết vấn đề có phổ biến hay không; ví dụ 5xx rate tăng trên `POST /orders`.
- **Zipkin** chỉ ra span nào chậm hoặc lỗi trong một trace cụ thể.
- **Logs** cung cấp thông tin chi tiết theo sự kiện, nếu đã bật trace/span correlation.
- **Trace IDs** dùng để nối các spans và log records trong một request; không dùng làm metric label.

Một trace không xuất hiện có thể do sampling. Vì thế không thể dùng số lượng trace trong Zipkin để tính tổng số request hoặc thay thế Counter. Số liệu SLI/SLO phải dựa trên metrics có semantics rõ ràng.

### 13.1. Log correlation

Nếu logging integration được cấu hình, log line có thể chứa `traceId` và `spanId`. Ví dụ định dạng minh họa:

~~~text
INFO  [order-service, traceId=ab12..., spanId=cd34...] Created order
WARN  [order-service, traceId=ab12..., spanId=ef56...] Inventory timeout
~~~

Việc có Zipkin exporter không tự động bảo đảm logging pattern hiển thị hai giá trị này. Kiểm tra logging correlation trong cấu hình Spring Boot và xử lý context propagation khi chuyển thread.

## 14. Cấu hình production: endpoint, network, retry và storage

Zipkin exporter là một thành phần vận hành, nên cấu hình cần xét tới nhiều yếu tố ngoài việc endpoint trả lời.

### 14.1. Địa chỉ service discovery

Trong local, endpoint thường là `http://localhost:9411/api/v2/spans`. Trong môi trường container/orchestrator, dùng DNS service hoặc địa chỉ collector phù hợp. Không hardcode IP pod tạm thời.

### 14.2. Network và bảo vệ dữ liệu

- Chỉ cho phép application workload cần thiết truy cập collector.
- Nếu spans chứa attributes nội bộ, bảo vệ collector/UI bằng private networking, authentication proxy hoặc giải pháp tương ứng.
- Cân nhắc TLS khi dữ liệu đi qua mạng không tin cậy; khả năng cấu hình TLS/auth phụ thuộc reporter/transport và hạ tầng triển khai.
- Không ghi credential vào `application.yml` đã commit; dùng secret/configuration phù hợp.
- Giới hạn tags, event count, attribute size và retention theo chính sách.

### 14.3. Reporter failure và shutdown

Khi Zipkin không khả dụng:

- Theo dõi log/telemetry lỗi của reporter.
- Kiểm tra queue/buffer có đầy không và spans có bị drop không.
- Đánh giá retry/backoff và timeout từ cấu hình reporter/version.
- Đảm bảo graceful shutdown có thời gian cần thiết để flush nếu reporter hỗ trợ.
- Không coi reporter queue như persistent event store; restart/crash có thể làm mất span đang chờ.

Tracing là dữ liệu quan sát, không phải hệ thống lưu audit giao dịch. Nếu cần bảo đảm mọi sự kiện nghiệp vụ được lưu bền vững, hãy dùng hệ thống event/audit riêng.

### 14.4. Lựa chọn Zipkin hay Collector trung gian

Một kiến trúc có thể gửi spans trực tiếp tới Zipkin. Khi cần xử lý chung nhiều nguồn telemetry, có thể gửi OTLP tới OpenTelemetry Collector rồi Collector export sang backend tương thích. Hai cách có trade-offs về chuẩn giao tiếp, quản trị pipeline và khả năng xử lý tập trung.

Đừng thêm Collector chỉ vì từ exporter xuất hiện. Chọn dựa trên nhu cầu transform, batching, filtering, retry, multi-destination, security và vận hành thực tế.

## 15. Các lỗi phổ biến khi cấu hình Zipkin exporter

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| Zipkin UI hoạt động nhưng không thấy traces | App chưa có tracer/bridge/reporter, sampling loại trace hoặc chưa tạo span | Kiểm tra dependencies, instrumentation và sampling |
| Lỗi connection refused | Sai host/port, Zipkin container chưa sẵn sàng hoặc sai network namespace | Curl endpoint từ nơi ứng dụng chạy; kiểm tra container network |
| HTTP 404 khi gửi spans | Sai path, ví dụ thiếu `/api/v2/spans` | Xác minh endpoint collector v2 |
| HTTP 400 hoặc payload bị từ chối | Reporter/protocol/version không tương thích hoặc dữ liệu không hợp lệ | Kiểm tra response/log và dependency alignment |
| Chỉ thấy server span, không có client span | HTTP client không được instrument hoặc tạo client bỏ qua builder đã cấu hình | Kiểm tra client instrumentation và propagation |
| Có nhiều trace thay vì một trace xuyên service | B3/W3C propagation không thống nhất hoặc mất headers | Xem `traceId` và inbound/outbound headers |
| Trace thiếu spans đôi khi | Sampling, async context propagation, queue/drop hoặc exporter lỗi | Xem sampling, reporter logs, concurrency path |
| Span xuất hiện chậm | Reporter batching, network, collector/storage/UI delay | Đo thời điểm span end, send, receive và search |
| Tăng số spans bất thường | Instrument trùng, retry thật, instrumentation chồng lấp | Kiểm tra span names, parent-child và số lần gọi |
| Span không có lỗi dù code log ERROR | Logging không báo lỗi cho Observation hoặc exception đã được phục hồi | Gọi `observation.error(ex)` khi phù hợp, xem mapping |
| Zipkin không có đầy đủ lịch sử | Sampling thấp, retention/storage hoặc dữ liệu trước khi reporter publish bị mất | Kiểm tra sampling, backend retention, shutdown/reporter queue |
| Trace ID không có trong logs | Logging correlation chưa cấu hình hoặc mất context | Kiểm tra MDC/pattern và async context propagation |

### Quy trình chẩn đoán

1. Tạo một request test có thể nhận diện, ghi lại thời điểm và response.
2. Xác nhận Observation/span được tạo trong ứng dụng.
3. Xác nhận sampler có chọn trace và reporter nhận span hoàn tất.
4. Kiểm tra endpoint và network tới `/api/v2/spans`.
5. Xem Zipkin server logs/collector metrics để biết payload có tới không.
6. Tìm đúng service và khoảng thời gian trong UI/API.
7. So sánh trace ID giữa các dịch vụ; nếu khác nhau, kiểm tra propagation.
8. Sau khi sửa, chạy lại cùng request test và so sánh waterfall.

## 16. Tình huống thực tế: order-service gọi inventory-service

**Bối cảnh.** Sau khi triển khai một phiên bản mới, `order-service` ghi nhận latency tạo đơn tăng từ 150 ms lên 800 ms. Error rate HTTP không tăng nhiều vì ứng dụng fallback khi inventory chậm.

### Bước 1 — metrics phát hiện xu hướng

Dashboard cho thấy p95 của `orders.create` tăng, trong khi tỷ lệ `outcome=fallback` cao hơn. Metrics khoanh vùng được service và thời điểm.

### Bước 2 — chọn trace trên Zipkin

Tìm một trace có operation `GET /orders` trong khoảng thời gian sự cố. Waterfall có thể hiển thị:

~~~text
order-service: GET /orders                   790 ms
  order-service: orders.create                780 ms
    order-service: inventory.reserve (CLIENT) 690 ms
    order-service: orders.fallback              50 ms
~~~

Nếu span client bị đánh dấu lỗi/timeout, cần xem tags và exception/event metadata được ghi nhận. Nếu server `inventory-service` có span tương ứng, kiểm tra cùng trace ID và thời gian xử lý phía server.

### Bước 3 — xác định loại vấn đề

- Client span 690 ms nhưng server span chỉ 50 ms: có thể thời gian nằm ở connect/pool/network/queue hoặc phần trước/sau server handler.
- Không có server span: request có thể chưa tới service hoặc propagation/instrumentation đang thiếu.
- Hai service có trace ID khác nhau: kiểm tra headers B3/W3C và client builder.
- Không thấy trace: kiểm tra sampling và reporter/exporter trước khi kết luận không có request.

### Bước 4 — sửa và kiểm chứng

Sau khi điều chỉnh connection pool/timeout hoặc dependency chậm, lặp lại test. Kiểm tra p95/error/fallback metrics, các span client/server và logs theo trace ID. Không chỉ dựa vào một trace tốt để kết luận vấn đề đã hết; cần quan sát lượng request đủ đại diện trên metrics.

## 17. Bài thực hành và câu hỏi tự kiểm tra

### Bài tập A — dựng pipeline Zipkin local

1. Chạy Zipkin container expose cổng `9411`.
2. Thêm Actuator, Micrometer Tracing Brave bridge và Zipkin Reporter dependencies phù hợp với BOM của Spring Boot.
3. Đặt `management.zipkin.tracing.endpoint` về `http://localhost:9411/api/v2/spans` nếu ứng dụng chạy trực tiếp trên host.
4. Đặt sampling probability cao trong môi trường học tập.
5. Tạo một REST endpoint và một custom Observation nghiệp vụ.
6. Gọi endpoint nhiều lần và tìm trace trên Zipkin UI.

### Bài tập B — kiểm chứng propagation

1. Tạo `order-service` gọi `inventory-service` qua HTTP client được instrument.
2. Xác định client/server spans có cùng `traceId` và quan hệ cha–con đúng không.
3. Thử cấu hình propagation format không tương thích trong môi trường test.
4. Quan sát trace bị tách, rồi đồng bộ B3 hoặc W3C propagation.
5. Xác nhận lại bằng trace ID và headers, không suy ra chỉ từ tên service.

### Bài tập C — sampling và reporter

1. Chạy 20 request ở sampling 100% và quan sát số trace trong điều kiện không lỗi export.
2. Đổi sampling xuống thấp hơn, gửi một lô request khác và so sánh số trace xuất hiện.
3. Tạo độ trễ trong exporter/collector ở môi trường test, quan sát thời gian trace hiển thị.
4. Tắt Zipkin tạm thời, kiểm tra logs/reporter behavior và cách hệ thống khôi phục khi server hoạt động lại.
5. Giải thích vì sao metrics vẫn có thể đếm đủ request dù trace chỉ hiển thị một phần.

### Bài tập D — bảo mật và chất lượng dữ liệu

Kiểm tra spans:

- Tên span có chứa ID đơn hàng hoặc URL với identifier riêng không?
- Có tags nhạy cảm như token, email, cookie hoặc payload không?
- Các operation names có ổn định và có thể tìm kiếm không?
- Có span trùng do `@Observed` và manual Observation cùng đo một boundary không?
- Có giữ trace/span correlation trong logs và propagation khi qua async executor không?

### Câu hỏi tự kiểm tra

1. Micrometer Tracing bridge, Brave tracer, Zipkin Reporter và Zipkin server khác nhau thế nào?
2. Vì sao cấu hình endpoint đúng nhưng UI vẫn không có traces?
3. Endpoint nhận spans của Zipkin v2 thường có path nào?
4. Sampling probability 1.0 có nên dùng mặc định cho production traffic lớn không?
5. Reporter batch có làm span hiển thị trễ không? Vì sao?
6. Khi chạy cùng Docker network, vì sao `localhost:9411` có thể sai?
7. B3 và W3C Trace Context có liên quan đến việc nối trace giữa dịch vụ ra sao?
8. Span attribute có tự động thành metric label hoặc được propagate như baggage không?
9. Nếu một trace bị sampling loại, metrics có còn tăng không?
10. Vì sao Zipkin không nên được dùng thay audit/event store bền vững?
11. Khi chỉ có server span, cần kiểm tra gì ở HTTP client?
12. Nếu client và server span có trace ID khác nhau, cần điều tra những thành phần nào?

**Tiêu chí hoàn thành:** cấu hình được Brave/Zipkin Reporter trong Spring Boot; giải thích đường đi span tới collector; tạo và tìm một trace; hiểu sampling, batching, endpoint/network và B3/W3C propagation; phân tích được trace liên dịch vụ; bảo vệ dữ liệu và tránh double instrumentation.

## 18. Ghi nhớ

- **Zipkin exporter** gửi các spans đã kết thúc từ tracer tới Zipkin collector; nó không tự tạo instrumentation.
- Trong ví dụ Spring Boot 3.x, stack phổ biến là `micrometer-tracing-bridge-brave` cùng `zipkin-reporter-brave`; dùng BOM để chọn dependency tương thích.
- Endpoint nhận span v2 thường có dạng `/api/v2/spans`; phải dùng địa chỉ truy cập đúng từ network namespace của ứng dụng.
- Sampling quyết định trace nào được giữ; reporter batching và network quyết định khi nào span đến backend. Không tìm thấy trace không chứng minh không có request.
- B3/W3C propagation phải tương thích giữa các dịch vụ để span nằm trong cùng trace; client integration phải inject headers và server phải extract context.
- Zipkin UI giúp phân tích waterfall, service, operation, duration và tags; metrics vẫn là nguồn tổng hợp tỷ lệ lỗi/latency, logs cung cấp sự kiện chi tiết.
- Giữ tags/attributes an toàn và cardinality phù hợp; không gửi token, payload nhạy cảm hoặc ID riêng thành metric labels.
- Theo dõi reporter/collector errors, queue/drop, shutdown và storage retention. Tracing là dữ liệu vận hành, không thay thế hệ thống audit bền vững.

## Tài liệu tham khảo

- [Micrometer Tracing Reference](https://docs.micrometer.io/tracing/reference/)
- [Micrometer Tracing — Brave setup](https://docs.micrometer.io/tracing/reference/api.html)
- [Spring Boot Reference — Tracing](https://docs.spring.io/spring-boot/reference/actuator/tracing.html)
- [Spring Boot Reference — Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html)
- [OpenZipkin — Zipkin quickstart](https://zipkin.io/pages/quickstart)
- [OpenZipkin — Zipkin API](https://zipkin.io/zipkin-api/)
- [W3C — Trace Context](https://www.w3.org/TR/trace-context/)

