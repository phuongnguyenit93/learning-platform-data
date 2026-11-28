# TraceId và spanId trong MDC

## 1. Vì sao cần traceId và spanId trong log?

Trong ứng dụng Spring Boot sử dụng **Spring Modulith**, một request có thể đi qua nhiều application module như **orders**, **payments**, **inventory** và **notifications**. Khi xảy ra lỗi, log thường được ghi từ nhiều class, nhiều module và đôi khi nhiều service. Nếu chỉ tìm theo thời gian hoặc nội dung thông báo, nhóm vận hành khó xác định dòng log nào thuộc cùng một request.

**Distributed tracing** liên kết hành trình xử lý bằng hai định danh:

- **traceId** nhận diện một trace, tức hành trình xử lý có liên hệ với nhau qua một hoặc nhiều service.
- **spanId** nhận diện một span, tức một đơn vị công việc cụ thể bên trong trace.

Spring Boot với **Micrometer Tracing** có thể đưa hai giá trị này vào **MDC (Mapped Diagnostic Context)** của logging framework. Nhờ vậy, các dòng log được ghi trong phạm vi span hiện tại có thể tự động mang correlation ID, giúp tìm từ log sang trace backend và ngược lại.

Bài học thuộc chương **Logging** của module **SPRING_MODULITH_DOCUMENTATION_OBSERVABILITY**. Nội dung nối logging với module graph, Actuator, event metrics, module spans và context propagation để hỗ trợ kiểm chứng kiến trúc mô-đun trong lúc ứng dụng vận hành.

Sau bài học, bạn có thể:

- Phân biệt traceId, spanId, MDC và correlation ID.
- Hiểu vì sao Spring Boot tự thêm correlation ID vào log khi Micrometer Tracing được bật.
- Tùy chỉnh format log bằng logging.pattern.correlation.
- Đổi tên key MDC trong phiên bản Spring Boot hỗ trợ và tránh làm hỏng correlation format.
- Đọc log để tìm trace, span và module entry tương ứng.
- Chẩn đoán log thiếu ID khi tracing chưa cấu hình, logging pattern bị ghi đè hoặc context propagation bị mất.

## 2. TraceId và spanId khác nhau thế nào?

Một trace là hành trình của một thao tác được theo dõi. Trace có thể gồm nhiều span: HTTP server span, lời gọi vào module, truy vấn database, HTTP client span hoặc event listener span.

| Thuộc tính | traceId | spanId |
| --- | --- | --- |
| Phạm vi | Toàn bộ trace | Một span cụ thể |
| Mục đích | Nhóm các spans/logs thuộc cùng hành trình | Xác định đơn vị xử lý đang ghi log |
| Giá trị | Thường 32 ký tự hex trong W3C Trace Context | Thường 16 ký tự hex trong W3C Trace Context |
| Quan hệ giữa các module | Giữ nguyên khi các span thuộc cùng trace | Thường thay đổi theo span hiện hành |
| Cách dùng khi điều tra | Tìm toàn bộ hành trình | Khoanh vùng thao tác gây lỗi/chậm |

Ví dụ một request tạo đơn hàng:

~~~text
traceId = 803b448a0489f84084905d3093480352

HTTP server span:
  spanId = 3425f23bb2432450

orders module entry span:
  spanId = a4c219e3a5b1f010

inventory module entry span:
  spanId = 72b1d5a3f8e9c012
~~~

Ba span trên có thể thuộc cùng một trace nên **traceId giống nhau**, nhưng mỗi span có **spanId riêng**. Nếu log được ghi khi span inventory đang active, MDC thường mang trace ID chung và span ID của span hiện hành đó.

### 2.1. Correlation ID là gì?

**Correlation ID** trong log là chuỗi ghép các định danh giúp liên kết log line với trace/span. Spring Boot mặc định tạo correlation ID từ hai giá trị MDC traceId và spanId. Ví dụ:

~~~text
[803B448A0489F84084905D3093480352-3425F23BB2432450]
~~~

Chuỗi này có dạng [traceId-spanId]. Correlation ID không phải một loại ID nghiệp vụ mới. Nó là cách trình bày hai giá trị tracing để tìm log nhanh hơn. Khi nhiều dòng log có cùng traceId nhưng spanId khác nhau, chúng có thể được ghi ở những span/module khác nhau trong cùng một hành trình.

### 2.2. Trace, span và module không phải cùng một khái niệm

| Khái niệm | Trả lời câu hỏi |
| --- | --- |
| Trace | Toàn bộ hành trình xử lý được liên kết ra sao? |
| Span | Một bước cụ thể mất bao lâu, lỗi gì? |
| Application module | Bước xử lý thuộc ranh giới module nào? |
| MDC | Log line hiện tại có thể mang những giá trị ngữ cảnh nào? |

Spring Modulith có thể tạo module entry spans tại các điểm vào Spring component thuộc API của application module. Các span này có thể mang tag module.identifier, module.name, module.invocation-type và module.method. MDC cung cấp traceId/spanId để nối log line với span; module tags trong trace giúp nhận diện ranh giới module.

## 3. MDC là gì và tracing đưa ID vào đó như thế nào?

**MDC (Mapped Diagnostic Context)** là một bản đồ key-value gắn với ngữ cảnh logging hiện hành. Với SLF4J/Logback, ứng dụng hoặc thư viện có thể đặt giá trị vào MDC để logging pattern chèn chúng vào mỗi dòng log.

Khi Micrometer Tracing được tích hợp với Spring Boot:

1. Một request hoặc công việc bắt đầu trace/span.
2. Tracer đưa thông tin của span hiện hành vào tracing context.
3. Integration logging của Micrometer Tracing ghi traceId và spanId vào MDC trong phạm vi context tương ứng.
4. Khi logger ghi thông điệp, logging pattern đọc các giá trị MDC và thêm correlation ID.
5. Khi scope của span kết thúc hoặc context được khôi phục, các giá trị MDC được cập nhật/dọn dẹp theo integration.

~~~mermaid
sequenceDiagram
    participant R as HTTP request
    participant T as Micrometer Tracing
    participant M as MDC
    participant L as Logger / Logback
    participant B as Log storage
    R->>T: Bắt đầu trace và server span
    T->>M: Đặt traceId và spanId vào MDC
    R->>L: Ghi log trong request scope
    L->>M: Đọc traceId/spanId
    L->>B: Ghi log + correlation ID
    R->>T: Kết thúc span
    T->>M: Đóng scope / khôi phục context
~~~

**Không cần tự ghi MDC.put("traceId", ...) cho từng request** khi đã dùng Micrometer Tracing và cấu hình logging mặc định của Spring Boot. Tự ghi ID thủ công có thể tạo giá trị sai, không gắn với span thật hoặc bị sót trên thread pool nếu không cleanup đúng cách.

### 3.1. MDC thường gắn với thread

Trong nhiều logging implementation, MDC dựa trên thread-local context. MDC hiện hành gắn với thread đang thực thi. Khi một tác vụ chuyển sang thread khác, giá trị MDC không tự động xuất hiện nếu context propagation chưa được cấu hình.

Ví dụ:

~~~text
Thread HTTP:
  traceId = T1
  spanId  = S1
  log -> [T1-S1] request.accepted

Thread async listener:
  traceId = (missing)
  spanId  = (missing)
  log -> [] inventory.reservation.started
~~~

Nếu listener được chạy trên executor khác mà thiếu context propagation, log của listener có thể không có correlation ID. Cần xác định **MDC không có giá trị** hay **pattern không đọc giá trị**.

Với executor tùy chỉnh, có thể dùng ContextPropagatingTaskDecorator và bảo đảm listener thực sự chạy trên executor đã cấu hình. Với Reactor, cần cơ chế Reactor Context Propagation; qua HTTP/message broker, cần inject/extract trace context bằng instrumentation của transport. Decorator trong một JVM không tự truyền context qua network.

## 4. Spring Boot tự thêm correlation ID vào log

Khi ứng dụng có **Micrometer Tracing** hoạt động, Spring Boot mặc định đưa correlation ID vào log. Bạn thường không phải thêm thủ công các placeholder traceId/spanId vào pattern chỉ để bật tính năng này.

Điều kiện chính:

- Ứng dụng có Spring Boot Actuator và tracer implementation tương thích, ví dụ OpenTelemetry hoặc Brave.
- Micrometer Tracing được auto-configure và tracing không bị vô hiệu hóa.
- Logging system sử dụng cấu hình Spring Boot mặc định hoặc custom pattern có giữ correlation ID.
- Log được ghi trong một span/context đang active.

Ví dụ log minh họa:

~~~text
2026-11-27T09:20:11.120+07:00 INFO [shop-backend,803B448A0489F84084905D3093480352-3425F23BB2432450] --- [http-nio-8080-exec-1] c.e.shop.orders.OrderService : order.accepted
2026-11-27T09:20:11.135+07:00 INFO [shop-backend,803B448A0489F84084905D3093480352-a4c219e3a5b1f010] --- [http-nio-8080-exec-1] c.e.shop.inventory.InventoryService : stock.reserved
~~~

Hai dòng có cùng trace ID nhưng span ID khác nhau, phù hợp với hai bước được quan sát trong cùng trace. Đây là ví dụ format, không phải output từ một ứng dụng đang chạy.

### 4.1. Dependency tối thiểu

Spring Boot Actuator cung cấp dependency management và auto-configuration cho Micrometer Tracing. Ví dụ Gradle cho Spring Boot 4.2 dùng OpenTelemetry + OTLP:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    runtimeOnly 'org.springframework.boot:spring-boot-starter-opentelemetry'
}
~~~

Nếu dùng Brave + Zipkin trên Spring Boot 4.2, thay starter OpenTelemetry bằng:

~~~groovy
runtimeOnly 'org.springframework.boot:spring-boot-starter-zipkin'
~~~

Hai starter tracing là **hai lựa chọn thay thế**, không thêm cả hai cùng lúc. Với Spring Boot 3.5, cấu hình thường dùng Actuator cùng một Micrometer Tracing bridge và exporter/reporter tương ứng, ví dụ:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    runtimeOnly 'io.micrometer:micrometer-tracing-bridge-otel'
    runtimeOnly 'io.opentelemetry:opentelemetry-exporter-otlp'
}
~~~

Các ví dụ giả định version được quản lý bằng Spring Boot BOM tương thích. Chỉ bật Actuator mà không có tracer bridge/starter thì không đủ để tạo correlation ID từ Micrometer Tracing.

## 5. Tùy chỉnh correlation format

Mặc định Spring Boot hiển thị correlation ID ghép traceId và spanId. Nếu muốn thay đổi cách trình bày, dùng property logging.pattern.correlation.

Ví dụ:

~~~yaml
logging:
  pattern:
    correlation: "[%X{traceId:-}-%X{spanId:-}] "
~~~

Kết quả có dạng:

~~~text
[803B448A0489F84084905D3093480352-3425F23BB2432450] c.e.shop.orders.OrderService : order.accepted
~~~

Giải thích:

- %X{traceId:-} đọc key traceId trong MDC; nếu không có giá trị thì dùng chuỗi rỗng sau dấu :-.
- %X{spanId:-} đọc key spanId tương tự.
- Dấu cách ở cuối pattern giúp tách correlation ID khỏi logger name/message tiếp theo.
- Pattern tùy chỉnh thay thế format mặc định. Nếu bỏ hai key trên, log sẽ không còn hiển thị correlation ID dù MDC vẫn có giá trị.

### 5.1. Tùy chỉnh tên key MDC trong Spring Boot 4.2

Spring Boot 4.2 tài liệu hóa các property:

- management.tracing.mdc.trace-id-key — tên MDC key dùng cho trace ID.
- management.tracing.mdc.span-id-key — tên MDC key dùng cho span ID.

Ví dụ đổi key thành trace_id và span_id:

~~~yaml
management:
  tracing:
    mdc:
      trace-id-key: trace_id
      span-id-key: span_id

logging:
  pattern:
    correlation: "[%X{trace_id:-}-%X{span_id:-}] "
~~~

Vì custom correlation pattern tự chỉ định key, nó phải dùng **đúng tên mới**. Nếu đổi key trong MDC nhưng vẫn để pattern đọc traceId/spanId, log sẽ hiển thị giá trị rỗng.

Với các dòng Spring Boot cũ hơn, hãy xác minh property có được hỗ trợ trong version đang dùng. Ví dụ tùy chỉnh key ở trên theo tài liệu Boot 4.2; không nên copy nguyên xi vào mọi dự án 3.x mà chưa kiểm tra configuration metadata.

### 5.2. Lưu ý riêng với Brave

Tài liệu Spring Boot 4.2 lưu ý rằng với **Brave**, tên MDC key được áp dụng khi baggage được bật. Nếu cấu hình management.tracing.baggage.enabled: false, Brave sẽ ngừng ghi trace ID/span ID vào MDC và log correlation có thể mất.

Vì vậy khi chuyển tracer hoặc thay cấu hình baggage, cần kiểm tra log thực tế. Đừng mặc định rằng backend vẫn nhận trace đồng nghĩa MDC chắc chắn có giá trị.

## 6. Đọc MDC từ code khi cần chẩn đoán

Thông thường nên để logging framework tự in correlation ID. Tuy nhiên, trong một đoạn chẩn đoán có thể đọc MDC:

~~~java
import org.slf4j.MDC;
import org.springframework.stereotype.Component;

@Component
class TraceContextDiagnostics {

    void inspectCurrentContext() {
        String traceId = MDC.get("traceId");
        String spanId = MDC.get("spanId");

        // Chỉ dùng cho chẩn đoán; có thể null khi không có span active.
        if (traceId == null || spanId == null) {
            // Ghi nhận rằng không có correlation context hiện hành.
            return;
        }
    }
}
~~~

Đoạn code đọc MDC, **không tự tạo trace và không bổ sung context**. Nếu đã đổi tên MDC keys trong cấu hình Boot 4.2, code đọc phải dùng key mới. Không nên dùng traceId hoặc spanId làm điều kiện nghiệp vụ, khóa database hay ID của đơn hàng.

Tránh code sau:

~~~java
// Không nên: tự ghi ID cố định hoặc ID không gắn với tracer.
MDC.put("traceId", requestId);
~~~

Nếu muốn tạo trace/span tùy chỉnh, dùng API Micrometer Tracing/Observation; nếu muốn truyền context qua thread, dùng context propagation. Việc tự ghi một chuỗi vào MDC chỉ làm log trông có vẻ có trace ID, nhưng không tạo span tương ứng trong tracing backend.

## 7. TraceId và spanId trong luồng Spring Modulith

Giả sử một request gọi vào orders. Module này gọi API bean của inventory rồi phát OrderPlaced để notifications xử lý. Khi Spring Modulith Observability Core được bật cùng Micrometer Tracing, các điểm vào module phù hợp có thể tạo module entry spans.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant O as orders
    participant I as inventory
    participant N as notifications listener
    C->>O: POST /orders
    Note over O: traceId=T1, spanId=S1
    O->>I: reserve stock
    Note over I: traceId=T1, spanId=S2
    O--)N: publish OrderPlaced
    Note over N: traceId=T1, spanId=S3 nếu context được propagate
~~~

Ví dụ log:

~~~text
[T1-S1] orders: order.accepted
[T1-S2] inventory: stock.reserved
[T1-S3] notifications: notification.queued
~~~

Diễn giải:

- T1 là trace ID chung của hành trình.
- S1, S2, S3 là span ID khác nhau cho các bước.
- Nếu listener notifications chạy bất đồng bộ, nó chỉ có cùng trace ID khi context propagation được cấu hình đúng và semantics tracing giữ liên kết đó.
- Nếu listener tạo một trace độc lập theo thiết kế, trace ID có thể khác; cần correlation hoặc span link phù hợp nếu muốn nối hai công việc.

### 7.1. Đối chiếu với module entry span tags

Trong trace backend, module entry span có thể có:

| Tag | Dùng để |
| --- | --- |
| module.identifier | Lọc theo module như orders hoặc inventory. |
| module.name | Hiển thị tên module dễ đọc. |
| module.invocation-type | Phân biệt lời gọi bean hoặc event listener. |
| module.method | Xác định method tại điểm vào module. |

Khi có correlation ID trong log, có thể:

1. Tìm log có traceId liên quan tới request.
2. Mở trace cùng trace ID trong Zipkin/Tempo/Jaeger.
3. Tìm module entry span theo module.identifier.
4. So sánh spanId trong log với span ID của span đang xem nếu backend hiển thị.
5. Đọc exception, duration và các span con để xác định điểm chậm/lỗi.

**Module graph** và **MDC** trả lời câu hỏi khác nhau: module graph cho biết module nào phụ thuộc module nào; MDC giúp liên kết một dòng log với trace/span hiện hành. Kết hợp hai nguồn mới hỗ trợ đối chiếu thiết kế với hành vi runtime.

### 7.2. Event metrics không phụ thuộc correlation ID

Spring Modulith có counter module.events.published để đếm domain event được công bố theo module và event type. Đây là metric tổng hợp riêng; không cần và không nên thêm traceId/spanId làm metric tag để liên kết từng event với trace.

Khi cần xem event cụ thể:

- Dùng metrics để phát hiện module/event type có nhịp bất thường.
- Dùng tracing và log correlation để lần theo một số hành trình được sample.
- Dùng event publication registry hoặc dữ liệu nghiệp vụ được phân quyền nếu cần đối soát chính xác.

## 8. Context propagation và log correlation

Correlation ID chỉ có ích khi tracing context được truyền đến nơi log được ghi.

### 8.1. Qua HTTP

Spring Boot có thể tự động propagate trace qua mạng khi dùng các builder đã auto-configure như:

- RestTemplateBuilder ở phiên bản hỗ trợ.
- RestClient.Builder.
- WebClient.Builder.

Nếu tự khởi tạo client mà bỏ qua builder auto-configured, trace headers có thể không được inject; service nhận sẽ không biết trace cha và log có thể có ID khác hoặc rỗng.

### 8.2. Qua executor hoặc @Async

MDC thường gắn với thread; listener chuyển sang worker thread cần context propagation. Với executor tùy chỉnh, có thể gắn ContextPropagatingTaskDecorator:

~~~java
import org.springframework.core.task.support.ContextPropagatingTaskDecorator;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
executor.setCorePoolSize(2);
executor.setMaxPoolSize(4);
executor.setTaskDecorator(new ContextPropagatingTaskDecorator());
executor.initialize();
~~~

Đây là ví dụ tạo executor; listener phải thực sự sử dụng executor đó. Với Reactor, cần tích hợp Reactor Context Propagation; với message broker, cần inject/extract trace context qua headers. Không copy riêng hai giá trị MDC rồi cho rằng toàn bộ tracing context đã được truyền.

### 8.3. Sampling có thể làm trace không tìm thấy dù log vẫn có correlation ID?

Log correlation và export trace có liên quan nhưng là hai đầu ra khác nhau. Nếu trace được sample và recording/export hoạt động bình thường, backend có thể tìm thấy trace. Nếu trace bị head sampler loại, không có span được export; việc có log ID hay không còn phụ thuộc cách tracer và logging integration xử lý non-sampled context.

Vì vậy:

- Có log correlation nhưng không tìm thấy trace: kiểm tra sampling, exporter, backend retention và time range.
- Không có log correlation: kiểm tra tracing có bật, MDC có được populate, pattern có đọc đúng key và context có được propagate.
- Có trace root nhưng thiếu module span: kiểm tra Modulith core, module API boundary và instrumentation.

Không kết luận rằng request không xảy ra chỉ vì trace backend không tìm thấy trace.

## 9. Troubleshooting khi log không có traceId/spanId

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| Tất cả log đều thiếu correlation ID | Micrometer Tracing chưa được cấu hình, thiếu bridge/starter hoặc tracing bị disable | Kiểm tra Actuator, tracer dependency, auto-configuration và property. |
| Log request HTTP có ID, log listener không có | Async executor/event listener không propagate context | Kiểm tra executor, task decorator, Reactor hoặc message headers. |
| MDC có giá trị nhưng log không hiển thị | Custom logging pattern đã ghi đè correlation format hoặc đọc sai key | Kiểm tra logging.pattern.correlation và cấu hình Logback/Log4j2. |
| Chỉ có traceId, spanId rỗng | Không có span hiện hành hoặc context chưa được thiết lập đúng | Kiểm tra active span và vị trí ghi log. |
| Đổi tên MDC key xong log trống | Pattern vẫn đọc key cũ | Cập nhật placeholder theo tên mới. |
| Dùng Brave và mất correlation sau khi tắt baggage | Brave không ghi trace/span IDs vào MDC khi baggage bị disable theo cấu hình được tài liệu hóa | Kiểm tra management.tracing.baggage.enabled. |
| Log có correlation ID nhưng trace backend không có | Trace bị sampling, exporter lỗi hoặc backend đã hết retention | Kiểm tra sampling, exporter/collector logs, backend và time range. |
| Trace backend có trace nhưng tìm log không được | Log pipeline chưa ingest, retention khác, log pattern hoặc parser không giữ correlation ID | Tìm theo raw log và xác minh field mapping/index. |
| ID bị lẫn giữa hai request trên cùng thread pool | Tự ghi MDC mà không cleanup hoặc context decorator dùng sai | Bỏ ghi thủ công, dùng integration propagation và kiểm tra scope cleanup. |
| Trace ID khác nhau giữa hai service | Trace headers không được propagate/consume hoặc service tạo root trace mới | Kiểm tra HTTP client builder, propagator và message instrumentation. |

## 10. Thực hành: nối một log line với module span

Giả sử có ứng dụng Spring Modulith với module orders và inventory:

1. Bật Actuator cùng Micrometer Tracing và một tracer/exporter tương thích với Spring Boot version.
2. Đặt spring.application.name là shop-backend để trace backend phân biệt dịch vụ.
3. Gọi một request tạo đơn hàng, để orders gọi API bean của inventory.
4. Ghi một log trong service orders và một log trong service inventory.
5. Kiểm tra log output có correlation ID dạng [traceId-spanId] hay custom format không.
6. Lấy traceId từ log orders, tìm trace tương ứng trong backend.
7. Mở module entry span inventory, kiểm tra module.identifier=inventory và span ID có khớp log ở đúng thời điểm không.
8. Nếu listener bất đồng bộ, kiểm tra trace ID và span relationship sau khi cấu hình context propagation.
9. Đối chiếu module graph để xác nhận quan hệ dependency cấu trúc; đối chiếu event metrics để biết publisher có phát event hay không.

Ví dụ log output mong đợi (dữ liệu giả định):

~~~text
[shop-backend,803B448A0489F84084905D3093480352,3425F23BB2432450] order.accepted
[shop-backend,803B448A0489F84084905D3093480352,a4c219e3a5b1f010] stock.reserved
~~~

Hai dòng có cùng trace ID và span ID khác nhau. Tìm trace ID để xem toàn bộ hành trình, sau đó dùng span ID để định vị đoạn log cụ thể.

## 11. Bảo mật và giới hạn khi dùng MDC

- **Không đưa thông tin cá nhân vào MDC chỉ để tiện tìm kiếm.** User ID, email, access token hoặc payload không nên tự động xuất hiện trong mọi log line.
- **Trace ID không phải user ID.** Đây là định danh kỹ thuật của hành trình, không thay thế định danh nghiệp vụ hoặc audit record.
- **MDC không phải kho lưu trữ.** Giá trị tồn tại theo scope/context và không đảm bảo được lưu bền vững.
- **Không dùng MDC làm nguồn dữ liệu nghiệp vụ.** Logic đặt hàng/thanh toán không được phụ thuộc việc có trace ID.
- **Kiểm soát quyền truy cập log và trace backend.** Correlation ID giúp nối nhiều hệ thống; người có quyền đọc có thể thấy thêm ngữ cảnh vận hành.
- **Giữ cleanup và propagation đúng cách.** MDC còn sót trên thread pool có thể khiến log của request sau mang nhầm ID.
- **Sampling và retention có giới hạn.** Log có correlation ID không bảo đảm trace tương ứng luôn còn trong backend.

## 12. Checklist triển khai

| Hạng mục | Điều kiện đạt |
| --- | --- |
| Tracing dependency | Có Actuator và đúng tracer/bridge/exporter theo phiên bản Boot. |
| MDC | Log trong span có traceId và spanId từ Micrometer Tracing. |
| Correlation pattern | Dùng mặc định hoặc custom pattern đọc đúng key MDC; có khoảng trắng phân tách. |
| Tên key tùy chỉnh | Chỉ dùng property được hỗ trợ bởi Boot version và cập nhật pattern tương ứng. |
| Context propagation | HTTP, executor, Reactor và broker được cấu hình theo ranh giới thực tế. |
| Module spans | Trace có metadata module khi lời gọi đi qua điểm vào được instrument. |
| Event metrics | Counter publication được hiểu là số lần phát, không phải kết quả listener. |
| Log search | Có thể tìm log theo trace ID và drill-down theo span ID. |
| Bảo mật | Không ghi token/PII không cần thiết; có access control và retention phù hợp. |
| Kiểm thử | Đã thử request đồng bộ, async và trường hợp không có active span. |

## 13. Ghi nhớ

**traceId nhận diện toàn bộ trace; spanId nhận diện span hiện hành.** Spring Boot với Micrometer Tracing có thể đưa hai giá trị vào MDC và mặc định ghép chúng thành correlation ID trong log. Tìm theo trace ID giúp gom log của cùng hành trình; span ID giúp xác định bước cụ thể trong hành trình đó.

Khi cần tùy chỉnh, dùng logging.pattern.correlation và bảo đảm pattern đọc đúng MDC keys. Với Spring Boot 4.2, có property đổi tên key management.tracing.mdc.trace-id-key và management.tracing.mdc.span-id-key; nếu đổi tên, phải cập nhật custom pattern. Log correlation phụ thuộc context propagation, vì vậy các luồng async, Reactor và broker cần được cấu hình riêng theo executor/transport thực tế.

Trong Spring Modulith, kết hợp correlation ID với module entry span tags, event metrics và module graph sẽ giúp đi từ một dòng log đến đúng module, span và hành trình xử lý. Đó là nền tảng để điều tra lỗi mà vẫn phân biệt rõ dữ liệu log, cấu trúc kiến trúc và tín hiệu runtime.

## Tài liệu tham khảo

- [Spring Boot 4.2 — Tracing: Logging Correlation IDs](https://docs.spring.io/spring-boot/reference/actuator/tracing.html): correlation ID mặc định từ MDC traceId/spanId, tùy chỉnh tên key và logging.pattern.correlation.
- [Spring Boot 3.5 — Tracing](https://docs.spring.io/spring-boot/3.5/reference/actuator/tracing.html): correlation ID mặc định, cấu hình logging pattern và propagation.
- [Spring Boot — Logging](https://docs.spring.io/spring-boot/reference/features/logging.html): logging pattern và application name trong log output.
- [Micrometer Tracing — Glossary](https://docs.micrometer.io/tracing/reference/glossary.html): trace, span, tracing context và log correlation.
- [Micrometer Tracing — API](https://docs.micrometer.io/tracing/reference/api.html): Tracer, Span và quản lý scope.
- [Spring Framework — ContextPropagatingTaskDecorator](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/task/support/ContextPropagatingTaskDecorator.html): truyền context khi task chạy trên executor.
- [Spring Modulith — Production-ready Features](https://docs.spring.io/spring-modulith/reference/production-ready.html): module entry observations/spans và event metrics.

> **Giới hạn phiên bản:** Mặc định correlation ID và logging.pattern.correlation được tài liệu Spring Boot 3.5/4.2 mô tả. Các property tùy chỉnh MDC key được tài liệu hóa ở Spring Boot 4.2; hãy xác minh configuration metadata của phiên bản cũ trước khi sử dụng. Ví dụ log/trace trong bài là dữ liệu giả định, không phải output của một ứng dụng đã chạy.
