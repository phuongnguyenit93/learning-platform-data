# Baggage trong MDC

Một request đến Order Service mang theo thông tin phân vùng khách hàng và kênh bán hàng. Order Service gọi Inventory Service rồi Payment Service. Khi điều tra giao dịch, nhóm vận hành muốn tìm các log cùng thuộc một trace và lọc các log theo khu vực hoặc kênh. Trace ID giúp gom các span của một hành trình; metadata nghiệp vụ cần đi xuyên dịch vụ thường được truyền bằng **baggage**. Để metadata đó xuất hiện trong log, ta cần cấu hình **correlation với MDC**.

Bài **Baggage trong MDC** thuộc chương **Baggage và correlation** của module **SPRING_BOOT_OBSERVABILITY**. Module hướng tới thiết lập observability cho Spring Boot bằng Micrometer Observation, metrics, logs và distributed tracing; học propagation ngữ cảnh, tag/cardinality, exporter, sampling và liên kết tín hiệu để điều tra lỗi, độ trễ, hành vi ứng dụng trong môi trường thực. Bài này tập trung vào mối quan hệ giữa **W3C Baggage**, **Micrometer Tracing** và **Mapped Diagnostic Context (MDC)**.

> **Phân biệt ngay từ đầu:** Trace ID/Span ID định danh trace và span. Baggage truyền các cặp key-value ngữ cảnh qua ranh giới dịch vụ. MDC là vùng dữ liệu gắn với ngữ cảnh logging hiện hành, thường xuất thành các trường trong log pattern hoặc JSON. Baggage **không tự động trở thành MDC** trong mọi ứng dụng; cần cấu hình các trường correlation phù hợp. MDC cũng không phải giao thức truyền dữ liệu qua HTTP.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích baggage và phân biệt baggage với Trace ID, Span ID, span attributes, MDC và business identifiers.
2. Đọc header W3C baggage và hiểu cách metadata được truyền qua nhiều service.
3. Cấu hình Spring Boot/Micrometer Tracing để cho phép remote baggage fields và đưa selected baggage fields vào MDC.
4. Đọc baggage từ code bằng API Micrometer Tracing và tạo baggage trong đúng scope.
5. Hiểu vòng đời correlation fields trong MDC và cách log pattern/structured logging hiển thị chúng.
6. Kiểm soát allowlist, cardinality, độ dài, dữ liệu nhạy cảm và trust boundary của baggage.
7. Phân biệt baggage propagation với context propagation nội bộ qua thread pool/Reactor.
8. Kiểm thử baggage qua HTTP client/server và trong logs.
9. Điều tra trường hợp baggage có trong request nhưng không có trong MDC/log backend.

## 2. Baggage, trace context và MDC khác nhau thế nào?

| Thành phần | Chứa gì? | Mục đích | Phạm vi |
|---|---|---|---|
| **Trace context** | Trace ID, Span ID hiện hành, parent relationship và flags | Nối các spans trong một distributed trace | Xuyên dịch vụ theo tracing propagation |
| **Baggage** | Các cặp key-value như tenant-region=apac, channel=mobile | Truyền metadata ngữ cảnh qua services | Xuyên dịch vụ khi field được phép propagate |
| **MDC** | Các trường như traceId, spanId, tenant-region | Gắn dữ liệu vào log event hiện hành | Thường theo thread/scope logging |
| **Span attributes** | Metadata của một span cụ thể | Mô tả span để truy vấn trace | Gắn với span |
| **Metric tags** | Nhóm có cardinality hữu hạn như outcome=approved | Tổng hợp số liệu thành time series | Theo meter ID |
| **Business ID** | orderId, invoiceId, transaction reference | Định danh thực thể nghiệp vụ | Theo vòng đời nghiệp vụ |

Ví dụ, request có Trace ID T và baggage tenant-region=apac. Khi đi qua Order và Inventory, Trace ID giữ nguyên nếu context được propagate đúng; baggage có thể đi theo header. Mỗi service tạo span riêng, còn logger có thể đưa trace/span cùng baggage đã chọn vào MDC.

~~~mermaid
flowchart TD
    A["Inbound HTTP request"] --> B["Extract trace context + baggage"]
    B --> C["Current tracing / observation context"]
    C --> D["Baggage fields"]
    C --> E["Trace ID / Span ID"]
    D --> F["MDC correlation configuration"]
    E --> F
    F --> G["Log event"]
    C --> H["Instrumented HTTP client"]
    H --> I["Inject traceparent + allowed baggage"]
    I --> J["Downstream service"]
    G --> K["Log appender / collector"]
~~~

MDC là phần trình bày trong log; baggage là dữ liệu context có thể được inject vào giao thức truyền qua mạng. Nếu chỉ thêm key vào MDC, service downstream không tự nhận được nó. Nếu chỉ nhận baggage, logger cũng không tự in field đó nếu chưa cấu hình correlation.

## 3. Baggage theo W3C là gì?

W3C Baggage định nghĩa HTTP header có tên baggage, chứa các member dạng key-value và có thể kèm properties. Ví dụ:

~~~http
baggage: tenant-region=apac,channel=mobile,experiment=checkout-v2
~~~

Các member trên là metadata minh họa. Một service có thể dùng chúng để chọn cấu hình phù hợp hoặc thêm thông tin correlation vào log. Baggage không thay traceparent; hai header có mục đích khác nhau.

| Header | Ví dụ | Ý nghĩa |
|---|---|---|
| traceparent | 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01 | Trace ID, parent span ID và flags |
| tracestate | vendor-specific state | Metadata tương tác giữa tracing vendors |
| baggage | tenant-region=apac,channel=mobile | Metadata context được propagate |

Baggage có thể được chuyển tiếp qua nhiều services; bất cứ field nào đưa vào đó đều có thể được nhiều thành phần trong chuỗi gọi nhìn thấy. Không coi baggage là vùng riêng tư hoặc kênh bí mật.

### 3.1 Quy tắc cơ bản khi thiết kế baggage

- Dùng key ổn định, có tên rõ nghĩa và không chứa ID từng request.
- Giá trị phải ngắn và có giới hạn; tránh nhét JSON lớn hoặc request payload.
- Chỉ propagate fields cần cho downstream; không forward mọi header inbound.
- Không đưa password, access token, API key, session cookie, dữ liệu thanh toán hoặc PII không có căn cứ.
- Xác thực và authorization phải dựa trên cơ chế bảo mật đáng tin cậy; baggage do caller gửi không phải bằng chứng được phép truy cập.
- Kiểm soát số key, tổng kích thước và cách encode theo W3C cùng giới hạn của proxy/gateway.
- Xem baggage nhận từ boundary bên ngoài là metadata không tin cậy.

### 3.2 Baggage không phải span attributes

Một baggage field có thể propagate qua nhiều spans và services; span attribute mô tả một span cụ thể. Chúng có thể chứa cùng giá trị khi instrumentation chủ động copy, nhưng không tự động là một.

~~~text
W3C baggage:
  tenant-region=apac

Span attributes:
  http.request.method=POST
  server.address=inventory-service

MDC:
  traceId=...
  spanId=...
  tenant-region=apac
~~~

Baggage có thể là đầu vào để tạo span attribute hoặc MDC field theo cấu hình. Chỉ copy giá trị khi thực sự cần; tránh tạo bản sao vô ích trên mọi signal.

## 4. MDC là gì và tại sao hữu ích cho correlation?

MDC (Mapped Diagnostic Context) là API logging cho phép gắn các cặp key-value vào log event hiện hành. Với SLF4J, code thường sử dụng org.slf4j.MDC; Logback có MDC implementation tương thích.

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;

public class CheckoutLogger {
    private static final Logger log =
            LoggerFactory.getLogger(CheckoutLogger.class);

    public void process() {
        MDC.put("order-channel", "mobile");
        try {
            log.info("Processing checkout");
        } finally {
            MDC.remove("order-channel");
        }
    }
}
~~~

Log pattern hoặc JSON encoder cần được cấu hình để ghi field đó. MDC không thay logger message, không tự truyền qua HTTP và không phải storage bền vững. Khi thread kết thúc hoặc scope đóng, field cần được clear/restore để tránh rò sang task khác.

### 4.1 Trace correlation và baggage correlation

Spring Boot/Micrometer Tracing có thể tự đặt traceId và spanId vào MDC khi tracing được cấu hình. Vì vậy log có thể hiển thị hai trường này dù code không gọi MDC.put thủ công.

Để baggage fields được thêm vào MDC, cần chọn và cấu hình các correlation fields tương ứng. Không nên thủ công copy cùng giá trị vào MDC nếu integration đã làm việc đó; dễ tạo dữ liệu stale hoặc ghi đè context hiện hành.

### 4.2 Cách đọc một dòng log

Ví dụ log minh họa:

~~~text
2026-11-22T10:15:32Z INFO [order-service,4bf92f3577b34da6a3ce929d0e0e4736,a1b2c3d4e5f60718] [tenant-region=apac,channel=mobile] Checkout request accepted
~~~

Có thể diễn giải:

- order-service: service phát log.
- Trace ID: toàn bộ trace của request.
- Span ID: span hiện hành lúc log được tạo.
- tenant-region, channel: baggage fields được đưa vào MDC theo cấu hình.
- Message: thông tin do logger phát ra.

Đây là định dạng minh họa, không phải pattern mặc định cố định của mọi Spring Boot version. Log pattern/JSON provider thực tế quyết định vị trí và tên field.

## 5. Cấu hình Spring Boot để đưa baggage vào MDC

Spring Boot với Micrometer Tracing cung cấp property để chỉ định remote baggage fields và correlation fields:

- management.tracing.baggage.remote-fields: các baggage fields được propagate ra ngoài service.
- management.tracing.baggage.correlation.fields: các baggage fields được đưa vào MDC để correlation trong logs.
- management.tracing.baggage.local-fields: các baggage fields chỉ dùng local, không propagate ra remote, khi phiên bản hỗ trợ property này.

Ví dụ:

~~~yaml
spring:
  application:
    name: order-service

management:
  tracing:
    baggage:
      remote-fields:
        - tenant-region
        - channel
      correlation:
        fields:
          - tenant-region
          - channel
~~~

Cấu hình này có nghĩa:

1. tenant-region và channel là baggage fields được phép gửi sang downstream.
2. Cùng các fields đó sẽ được đưa vào logging correlation/MDC theo Micrometer Tracing integration.
3. traceId và spanId vẫn là tracing correlation riêng; chúng không phải baggage fields.
4. Những fields không có trong danh sách không nên được tự động forward chỉ vì xuất hiện trong MDC.

**Lưu ý phiên bản:** tên property và binding có thể thay đổi theo Spring Boot major version; kiểm tra reference guide của đúng phiên bản dự án. Ví dụ dùng YAML list theo property model hiện hành. Không cấu hình nhiều cách cùng lúc nếu chúng làm binding khó hiểu.

### 5.1 Log pattern để hiển thị MDC fields

Spring Boot hỗ trợ logging pattern properties và khả năng dùng MDC trong Logback pattern. Nếu muốn kiểm soát rõ field, có thể dùng pattern tương ứng trong logback-spring.xml:

~~~xml
<configuration>
    <appender name="CONSOLE" class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%d{yyyy-MM-dd'T'HH:mm:ss.SSS} %-5level
                [%thread] traceId=%X{traceId:-}
                spanId=%X{spanId:-}
                tenant-region=%X{tenant-region:-}
                channel=%X{channel:-}
                %logger{36} - %msg%n</pattern>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="CONSOLE"/>
    </root>
</configuration>
~~~

Đây là ví dụ Logback tối giản; khi dùng file cấu hình riêng, phải giữ các appenders/encoders cần thiết của ứng dụng và kiểm tra tương thích với Spring Boot. %X{key:-} đọc MDC key và hiển thị fallback rỗng khi chưa có. Nếu dùng JSON encoder, map các trường tương ứng thành JSON properties.

**Đừng cấu hình correlation fields mà không in chúng trong output.** Field có thể hiện diện trong MDC nhưng log collector không thấy vì pattern/encoder bỏ qua nó.

## 6. Tạo và đọc baggage bằng Micrometer Tracing

Với Spring Boot có Micrometer Tracing và tracer implementation, code có thể tạo baggage trong scope bằng Tracer. API createBaggageInScope(name, value) tạo field có giá trị cho scope hiện hành; khi scope đóng, trạng thái trước đó được phục hồi.

Ví dụ service:

~~~java
import io.micrometer.tracing.BaggageInScope;
import io.micrometer.tracing.Tracer;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

@Service
public class CheckoutService {

    private static final Logger log =
            LoggerFactory.getLogger(CheckoutService.class);

    private final Tracer tracer;

    public CheckoutService(Tracer tracer) {
        this.tracer = tracer;
    }

    public void process(String channel) {
        String safeChannel = switch (channel) {
            case "web", "mobile", "partner" -> channel;
            default -> "other";
        };

        try (BaggageInScope baggage =
                     tracer.createBaggageInScope("channel", safeChannel)) {
            log.info("Processing checkout");
            callInventory();
        }
    }

    private void callInventory() {
        // Gọi client đã được Spring Boot instrument.
    }
}
~~~

Trong cấu hình đã khai báo channel là remote field và correlation field, baggage có thể được propagate và xuất hiện trong MDC/logs của scope phù hợp. Code phải chạy trong tracing context và tracer đã được cấu hình; nếu không có tracing implementation, bean Tracer có thể không tồn tại.

channel ở đây được chuẩn hóa thành tập nhỏ. Không truyền raw query parameter tùy ý vào baggage, vì downstream có thể log nó, lưu nó hoặc forward tiếp.

### 6.1 Đọc baggage hiện hành

API Tracer cho phép đọc baggage theo key:

~~~java
import io.micrometer.tracing.Baggage;
import io.micrometer.tracing.Tracer;

public String currentChannel(Tracer tracer) {
    Baggage baggage = tracer.getBaggage("channel");
    return baggage == null ? "unknown" : baggage.get();
}
~~~

Xử lý trường hợp không có baggage; đừng giả định mọi request đều đến từ client hỗ trợ W3C baggage. Đối chiếu Javadoc của Micrometer Tracing bridge và phiên bản được dùng. Giá trị baggage là metadata đầu vào, cần validate/normalize trước khi tác động logic quan trọng.

### 6.2 Baggage trong code không tự động được log

Tạo hoặc đọc baggage chỉ cung cấp context value. Để nó xuất hiện trong log cần cấu hình correlation fields và logging output, hoặc tự quản lý MDC có lifecycle rõ ràng nếu có lý do đặc biệt.

Không thực hiện đồng thời createBaggageInScope, MDC.put không cleanup và một filter khác tự copy cùng key sang MDC nếu chưa xác định ai sở hữu giá trị và scope. Các cơ chế trùng nhau có thể ghi đè hoặc để lại giá trị cũ trên worker thread.

## 7. Truyền baggage qua HTTP sang downstream

Để baggage đi qua HTTP, phải cấu hình remote fields và sử dụng HTTP client instrumentation/tracing propagation phù hợp. Spring Boot khuyến khích dùng các builder do Spring quản lý như RestClient.Builder hoặc WebClient.Builder khi stack đã được cấu hình Micrometer Tracing.

~~~java
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClient;

@Service
public class InventoryClient {

    private final RestClient client;

    public InventoryClient(RestClient.Builder builder) {
        this.client = builder
                .baseUrl("http://inventory-service:8080")
                .build();
    }

    public String reserve() {
        return client.post()
                .uri("/api/reservations")
                .retrieve()
                .body(String.class);
    }
}
~~~

Khi tracing propagation được kích hoạt, client instrumentation có thể inject traceparent và những baggage fields được cho phép vào HTTP request. URL minh họa cần thay bằng service discovery/endpoint thực tế, có timeout, auth và xử lý lỗi.

### 7.1 Header gửi đi minh họa

~~~http
POST /api/reservations HTTP/1.1
Host: inventory-service
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
baggage: tenant-region=apac,channel=mobile
Content-Type: application/json
~~~

- traceparent nối trace và xác định span context phía gửi.
- baggage mang metadata context được phép propagate.
- Server nhận extract hai loại context theo propagation implementation.
- Server tạo span mới với Span ID riêng; baggage có thể được dùng để thiết lập MDC theo correlation config ở service nhận.

Đừng copy nguyên header từ caller một cách mù quáng. Client instrumentation nên inject theo context hiện hành và propagation configuration, xử lý giá trị đã được validate.

### 7.2 Vì sao baggage không xuất hiện ở Inventory logs?

Kiểm tra theo thứ tự:

1. Order Service có tạo/nhận baggage field chưa?
2. Field có nằm trong remote-fields hoặc cấu hình propagation tương ứng không?
3. HTTP client có được instrument và inject W3C baggage không?
4. Proxy/gateway có giữ header baggage hay strip vì policy?
5. Inventory Service có extract đúng propagation format không?
6. Field có nằm trong correlation.fields ở Inventory không?
7. Logback pattern/JSON encoder có in MDC key đó không?
8. Async boundary trong Inventory có propagate context tới worker không?

Chỉ kiểm tra log pattern là chưa đủ; baggage có thể chưa đến service. Ngược lại, header có thể đã đến nhưng chưa được ánh xạ vào MDC.

## 8. Baggage và MDC qua async task

Baggage thường được truy cập qua tracing context; logging correlation dựa vào MDC. Cả hai có thể bị ảnh hưởng khi task chuyển sang thread khác.

Nếu ứng dụng sử dụng Spring TaskExecutor và @Async, cấu hình ContextPropagatingTaskDecorator (Spring Framework 6.1+) hoặc ContextSnapshot phù hợp giúp restore các context accessor đã đăng ký. Cơ chế này có thể bao gồm tracing/logging context khi integration tương ứng có sẵn.

~~~java
@Configuration(proxyBeanMethods = false)
@EnableAsync
class AsyncConfiguration {

    @Bean("applicationTaskExecutor")
    TaskExecutor applicationTaskExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(100);
        executor.setTaskDecorator(new ContextPropagatingTaskDecorator());
        executor.setThreadNamePrefix("async-");
        executor.initialize();
        return executor;
    }
}
~~~

Ví dụ cần các imports Spring tương ứng và Micrometer Context Propagation trong dependency graph. Decorator chỉ restore context đã đăng ký; nó không tự biến mọi custom ThreadLocal thành baggage.

### 8.1 Không tự copy baggage sang MDC bằng ThreadLocal không cleanup

Sai:

~~~java
executor.execute(() -> {
    MDC.put("channel", requestChannel);
    sendInvoice();
    // Quên restore/clear.
});
~~~

Thread pool tái sử dụng worker; task tiếp theo có thể ghi log dưới channel của request trước. Dùng context snapshot/scope và đóng scope trong mọi nhánh. Nếu quản lý MDC thủ công, phải lưu giá trị trước đó và restore trong finally, không clear bừa bãi context của framework.

### 8.2 Task dài và baggage lifetime

Với job chạy sau khi HTTP request đã kết thúc, hãy cân nhắc tạo trace mới và liên kết tới context producer bằng Span Link thay vì giữ request scope mở. Chỉ truyền baggage cần cho job, validate lại khi worker tiếp nhận và không mặc định mọi metadata từ request vẫn còn hợp lệ nhiều giờ sau.

## 9. Correlation fields và structured logging

MDC fields có thể xuất theo log pattern hoặc JSON. JSON thường thuận tiện cho collector vì mỗi key là một field riêng.

Ví dụ log record minh họa:

~~~json
{
  "timestamp": "2026-11-22T10:15:32.004Z",
  "level": "INFO",
  "service": "order-service",
  "message": "Checkout accepted",
  "traceId": "4bf92f3577b34da6a3ce929d0e0e4736",
  "spanId": "a1b2c3d4e5f60718",
  "tenant-region": "apac",
  "channel": "mobile"
}
~~~

Đây không phải schema mặc định bắt buộc của Spring Boot. Cần cấu hình structured logging/encoder và bảo đảm các MDC keys được xuất đúng. Nếu backend log đổi tên traceId thành trace_id, hãy đồng bộ query và correlation UI.

### 9.1 Tên field nên ổn định

| Dữ liệu | Tên gợi ý | Lưu ý |
|---|---|---|
| Trace ID | traceId hoặc trace_id | Một tên thống nhất toàn pipeline. |
| Span ID | spanId hoặc span_id | Giữ dạng chuỗi để không mất số 0 đầu. |
| Tenant region | tenant-region hoặc tenant_region | Chọn format tương thích logging/collector. |
| Channel | channel | Tập giá trị hữu hạn. |
| Environment | environment | Thường là cấu hình service, không phải baggage bắt buộc. |

Không lưu Trace ID/Span ID thành số nguyên; chúng là chuỗi hex, có thể có chữ cái và số 0 ở đầu. Không đổi kiểu dữ liệu khi parse JSON.

### 9.2 Correlation trong MDC không phải correlation toàn cầu

MDC chỉ tồn tại trong execution context/logging event tại nơi nó được thiết lập. Nó không tự truyền qua HTTP; baggage/trace context mới là giao thức propagation. Đừng kỳ vọng một MDC field ở Order Service tự xuất hiện tại Inventory Service nếu không có header và cấu hình extract/correlation tương ứng.

## 10. Allowlist, bảo mật và cardinality

Baggage được propagate ra nhiều downstream services, có thể xuất hiện trong logs và trace pipeline. Thiết kế nó như một giao diện metadata giữa các service, không phải scratchpad chứa mọi thứ.

| Field | Khuyến nghị | Lý do |
|---|---|---|
| tenant-region=apac | Có thể dùng nếu đã validate | Giá trị ngắn, hữu ích cho routing/diagnostics. |
| channel=web/mobile/partner | Có thể dùng | Tập giá trị nhỏ, nghiệp vụ rõ. |
| experiment=checkout-v2 | Có điều kiện | Chỉ khi downstream cần context; giới hạn cohort. |
| userId | Tránh mặc định | Identifier/PII, cardinality cao. |
| orderId | Tránh mặc định | Gần như duy nhất; dùng log/tracing có kiểm soát khi cần. |
| authorization token | Tuyệt đối không | Secret credential. |
| session-cookie | Tuyệt đối không | Credential nhạy cảm. |
| email hoặc phone | Không | Dữ liệu cá nhân và cardinality cao. |
| Raw request body | Không | Có thể rất lớn, chứa secrets/PII. |

### 10.1 Baggage không phải nguồn xác thực

Client có thể tự gửi:

~~~http
baggage: tenant-region=admin,role=superuser
~~~

Service không được tin rằng giá trị này đã được xác minh. Caller bên ngoài có thể tự tạo hoặc sửa baggage. Nếu metadata ảnh hưởng routing hoặc business behavior nhạy cảm, service phải lấy từ nguồn tin cậy/validate tại boundary và dùng authentication/authorization chính thức.

### 10.2 Cardinality và chi phí

Baggage không trực tiếp là metric tag, nhưng có thể được copy vào span attributes, logs hoặc metrics. Nếu giá trị thay đổi theo từng request và backend index mọi log field, nó vẫn có thể làm tăng chi phí storage/search.

- Giữ baggage keys và values ngắn.
- Giới hạn allowlist remote fields.
- Không tự động biến toàn bộ baggage thành span attributes/metric tags.
- Tránh dashboard/metric theo ID duy nhất.
- Giới hạn số baggage members và tổng header size theo W3C, proxy và service policy.
- Kiểm tra quyền truy cập logs/traces có baggage values.

## 11. Baggage propagation, sampling và exporter

Baggage propagation và trace sampling là hai chuyện khác nhau:

- Baggage có thể được truyền qua header ngay cả khi trace không được sample để lưu span.
- Một span được sample không có nghĩa mọi baggage field đều được giữ trong logs/trace backend; configuration có thể loại bỏ hoặc exporter/processor giới hạn attributes.
- Logback có thể ghi MDC fields theo logging policy độc lập với trace export.
- Metrics có thể tiếp tục tăng dù một số traces bị sampling loại.

Nếu log cho thấy tenant-region=apac nhưng trace backend không có span, hãy kiểm tra sampling, exporter và retention riêng. Nếu trace có span nhưng log thiếu tenant-region, xem correlation field config và log encoder. Đừng thay sampling probability để chữa vấn đề MDC.

## 12. Kiểm thử baggage trong MDC

Cần kiểm thử nhiều lớp thay vì chỉ tìm tên property trong YAML.

### 12.1 Kiểm tra property và output local

1. Chạy Spring Boot với Micrometer Tracing và logging implementation dự kiến.
2. Đặt management.tracing.baggage.remote-fields cho allowlist nhỏ.
3. Đặt management.tracing.baggage.correlation.fields cho các key cần trong logs.
4. Gọi endpoint tạo baggage trong tracing scope.
5. Kiểm tra log output có traceId, spanId và baggage fields đúng không.
6. Gọi downstream bằng client builder được Spring quản lý.
7. Ở service nhận, kiểm tra baggage đã được extract và có trong MDC của log chưa.
8. Kiểm tra worker thread sau task có giữ baggage cũ không.

### 12.2 Kiểm tra header trên môi trường test

~~~java
// Pseudocode của test HTTP client/server.
// Chỉ ghi tên và giá trị metadata đã kiểm soát trong môi trường test.
assertThat(receivedHeaders).containsKey("traceparent");
assertThat(receivedHeaders).containsKey("baggage");
assertThat(receivedHeaders.getFirst("baggage"))
        .contains("channel=mobile");
~~~

Đây là pseudocode để mô tả assertion, không phải một test class chạy độc lập. Test thật cần dựng mock server/client và bảo đảm request được thực hiện trong active tracing scope.

### 12.3 Test cleanup MDC

Dùng single-thread executor để worker được tái sử dụng:

1. Submit task A với baggage channel=mobile.
2. Trong task A, xác nhận MDC có channel=mobile.
3. Kết thúc task và đóng context scope.
4. Submit task B không có baggage.
5. Xác nhận MDC task B không còn channel=mobile của task A.

Nếu task B đọc được giá trị cũ, context restore/cleanup bị sai. Đây là test quan trọng vì lỗi thường chỉ xuất hiện khi tải production làm executor tái sử dụng worker nhiều lần.

## 13. Sự cố thường gặp và cách điều tra

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| Log có traceId nhưng không có baggage | Chưa cấu hình correlation fields hoặc baggage chưa được tạo/extract | Kiểm tra remote-fields, correlation.fields, context |
| Baggage có ở Order nhưng không ở Inventory | Không nằm trong remote allowlist hoặc HTTP client không inject | Kiểm tra outbound baggage header/client instrumentation |
| Header đến Inventory nhưng MDC trống | Service nhận không cấu hình correlation fields, tracing chưa extract | Kiểm tra receiver config và runtime tracing |
| MDC có field nhưng log không in | Pattern/JSON encoder không đọc key | Kiểm tra %X{key} hoặc structured encoder |
| Baggage xuất hiện sai ở task khác | ThreadLocal/MDC không cleanup hoặc async không propagate | Kiểm tra TaskDecorator/ContextSnapshot và worker reuse |
| Baggage giá trị bất ngờ | Caller gửi metadata không tin cậy hoặc giá trị không normalize | Validate/allowlist tại boundary |
| Baggage không có trong trace UI | Baggage chưa copy thành span attribute hoặc exporter bỏ field | Kiểm tra span attributes/processors |
| Trace không có nhưng baggage/log vẫn có | Sampling hoặc exporter/collector | Điều tra trace pipeline riêng |
| Log backend có fields nhưng metric backend thiếu | MDC/log pipeline khác metrics pipeline | Không suy ra metrics exporter hỏng từ logs |
| Header bị proxy loại | Gateway/header allowlist/size policy | Kiểm tra proxy config và header giới hạn |
| Giá trị bị cắt hoặc encode sai | W3C encoding hoặc parser/collector normalization | Kiểm tra header raw trong test |
| Số series metrics tăng bất thường | Baggage được copy thành metric tags động | Loại bỏ high-cardinality tags |

### 13.1 Playbook: baggage có trong HTTP header nhưng không có trong MDC

1. Kiểm tra service nhận có Micrometer Tracing/tracer implementation và propagation format tương thích.
2. Kiểm tra baggage header thực sự được extract. Dùng test instrumentation hoặc debugger để xác nhận context.
3. Kiểm tra management.tracing.baggage.correlation.fields tại service nhận. Cấu hình sender giúp propagate, không tự cấu hình MDC cho receiver.
4. Kiểm tra key spelling/case và cách normalize của API/implementation.
5. Kiểm tra Logback pattern/JSON encoder. Field trong MDC nhưng không có output nghĩa là logging config chưa xuất trường đó.
6. Kiểm tra async boundary nếu log phát từ worker; context propagation phải đúng và scope chưa bị đóng trước khi log.

### 13.2 Playbook: baggage value bị lộ trong logs

- Xác định nguồn gửi field và service nào forward nó.
- Gỡ field khỏi remote allowlist nếu không có nhu cầu hợp lệ.
- Xóa nó khỏi correlation.fields và logging pattern/encoder.
- Rà soát appenders/collector để tránh tiếp tục lưu ở index mới.
- Áp dụng chính sách xử lý/retention theo quy định dữ liệu.
- Thêm test ngăn field nhạy cảm quay lại baggage/log output.

Không chỉ xóa field ở log pattern trong một service nếu downstream vẫn forward và log nó.

## 14. Các lỗi thiết kế nên tránh

| Lỗi | Hậu quả | Cách sửa |
|---|---|---|
| Nghĩ MDC tự truyền qua HTTP | Downstream thiếu context | Dùng trace/baggage propagation và correlation config ở receiver |
| Nghĩ baggage tự động có trong MDC | Log không xuất field | Khai báo correlation fields và encoder/pattern |
| Đưa authorization token vào baggage | Rò credential qua nhiều service | Không gửi secrets trong baggage |
| Đưa orderId vào metric tags | Cardinality tăng mạnh | Dùng metric tags hữu hạn; tra ID qua logs/traces có kiểm soát |
| Copy toàn bộ inbound baggage ra downstream | Forward metadata không tin cậy/không cần thiết | Allowlist remote fields |
| Thủ công MDC.put nhưng không restore | Worker thread rò dữ liệu request trước | Dùng scope/TaskDecorator/ContextSnapshot và cleanup |
| Dùng baggage để quyết định quyền truy cập | Caller giả mạo metadata | Xác thực/authorization qua security context đáng tin cậy |
| Đổi sampling để sửa MDC | Không giải quyết nguyên nhân | Điều tra correlation fields và log pipeline |
| Tự gắn baggage thành metric, span attribute và log cùng lúc | Lặp dữ liệu và tăng chi phí | Chỉ copy sang signal cần thiết |

## 15. Bài tập thực hành

**Bài 1 — Phân biệt signal.** Một HTTP request có Trace ID T, Span ID A và baggage channel=mobile. Hãy giải thích giá trị nào thuộc trace context, giá trị nào là baggage và trường nào được dùng trong MDC. Baggage có tự động xuất hiện trong logs không?

**Bài 2 — Cấu hình hai service.** Order Service cần gửi tenant-region và channel tới Inventory Service; cả hai service cần in hai fields đó trong MDC. Viết cấu hình remote fields và correlation fields ở đúng nơi. Tại sao cấu hình receiver cũng cần thiết?

**Bài 3 — Header propagation.** Đọc traceparent và baggage trong một HTTP request. Vì sao không thể dùng baggage để thay thế traceparent? Vì sao server nhận tạo Span ID mới?

**Bài 4 — MDC trống.** Baggage header đã tới service nhưng log không in channel. Hãy nêu chuỗi kiểm tra từ extraction, correlation fields đến Logback pattern.

**Bài 5 — Async leakage.** Một task ghi channel=mobile trên worker; task tiếp theo không có baggage nhưng log vẫn in mobile. Hãy giải thích ThreadLocal reuse và đề xuất test single-thread executor để bắt lỗi.

**Bài 6 — Security.** Client tự gửi baggage role=admin. Vì sao service không được dùng field này để cấp quyền? Cơ chế nào cần dùng thay thế?

**Bài 7 — Cardinality.** Developer muốn đưa orderId vào baggage, MDC và metric tags. Đánh giá rủi ro theo từng signal và đề xuất lựa chọn phù hợp để điều tra một đơn hàng.

**Bài 8 — Sampling.** Log record có traceId, spanId và baggage, nhưng trace UI không tìm thấy span. Nêu các giả thuyết ngoài propagation và cách xác minh.

### Gợi ý trả lời

1. T là Trace ID, A là Span ID, channel là baggage; MDC chỉ chứa field khi được cấu hình/restore; baggage không tự động luôn được in.
2. Sender cấu hình remote-fields; từng service cấu hình correlation.fields nếu muốn in trong logs; receiver phải extract và map field vào MDC.
3. traceparent định danh trace/parent span; baggage chỉ mang metadata. Server tạo span mới với ID riêng và parent dựa trên context phía gửi.
4. Xác nhận header, extraction, correlation.fields, tracing configuration, MDC scope và log encoder.
5. Thread pool giữ worker; scope cũ không được phục hồi. Chạy hai task nối tiếp trên cùng worker và assert task sau không thấy field cũ.
6. Baggage do caller có thể bị giả mạo; dùng authentication/authorization và policy của service.
7. orderId trong baggage/log có thể tăng index cardinality và cần chính sách dữ liệu; tuyệt đối tránh metric tags. Chỉ log/trace khi thật sự cần, được phép và có kiểm soát.
8. Sampling, span chưa end, exporter/collector drop, retention và query sai thời gian/service.

## 16. Tài liệu tham khảo chính thức

- [W3C Baggage](https://www.w3.org/TR/baggage/): HTTP baggage header, member format, propagation và giới hạn.
- [W3C Trace Context](https://www.w3.org/TR/trace-context/): traceparent, tracestate và trace context.
- [Micrometer Tracing — Baggage](https://docs.micrometer.io/tracing/reference/api.html): Tracer/Baggage API và quản lý baggage trong scope.
- [Spring Boot — Tracing](https://docs.spring.io/spring-boot/reference/actuator/tracing.html): tracing configuration, baggage fields, correlation fields và log correlation.
- [Spring Boot — Logging](https://docs.spring.io/spring-boot/reference/features/logging.html): logging patterns và cấu hình logging system.
- [SLF4J — MDC](https://www.slf4j.org/manual.html#mdc): API Mapped Diagnostic Context.
- [Logback — MDC](https://logback.qos.ch/manual/mdc.html): MDC semantics và context trong logging.
- [Micrometer Context Propagation](https://docs.micrometer.io/context-propagation/reference/): ThreadLocal accessor, snapshot và context propagation.
- [OpenTelemetry — Baggage](https://opentelemetry.io/docs/concepts/signals/baggage/): baggage context, propagation và lưu ý dữ liệu.
- [OpenTelemetry — Context Propagation](https://opentelemetry.io/docs/concepts/context-propagation/): truyền context qua process boundaries.

**Ghi nhớ:** **Baggage truyền metadata; MDC đưa các field đã chọn vào log; Trace ID/Span ID liên kết trace và span.** Muốn thấy baggage trong log của nhiều service, phải cấu hình remote propagation, extract ở receiver, khai báo correlation fields và bảo đảm log encoder in các MDC keys. Giữ baggage theo allowlist, ngắn và không nhạy cảm; không dùng nó để xác thực, không đưa ID động thành metric tags và luôn phục hồi context sau async task. Khi ba lớp được cấu hình đúng, metrics cho biết mức độ ảnh hưởng, logs cung cấp chi tiết theo correlation fields và traces chỉ ra đường đi của request.
