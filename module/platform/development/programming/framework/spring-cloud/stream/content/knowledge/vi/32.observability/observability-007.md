# Micrometer Observation và theo dõi hàm xử lý

Một function trong Spring Cloud Stream có thể nhận message, gọi service nghiệp vụ, truy vấn database rồi phát event sang broker khác. Khi function chậm hoặc lỗi, chỉ nhìn log của một instance thường không đủ để biết message bị chậm ở bước nào, lỗi phát sinh ở đâu và consumer phía sau có nhận được event hay chưa.

Micrometer Observation cung cấp một mô hình chung để ghi nhận một thao tác đang diễn ra. Observation có thể tạo metric và trace thông qua các ObservationHandler được đăng ký trong ứng dụng. Spring Cloud Stream tích hợp observation ở tầng Spring Cloud Function: các function imperative được framework bọc để quan sát mỗi lần gọi. Với function reactive, ứng dụng phải chủ động chọn đoạn stream cần quan sát vì function chỉ được gọi một lần khi khởi tạo pipeline.

Bài học này hướng dẫn bật observation cho function, tạo observation con cho bước nghiệp vụ, theo dõi function reactive, truyền trace context qua message, thu thập metrics và binder health, rồi xây dựng dashboard cho ứng dụng xử lý sự kiện.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt log, metric, trace và vai trò của Micrometer Observation.
- Giải thích ObservationRegistry, Observation, ObservationHandler và ObservationConvention.
- Bật observability cho function imperative trong Spring Cloud Stream.
- Tự tạo observation cho một bước nghiệp vụ bằng ObservationRegistry.
- Đặt low-cardinality và high-cardinality key-value đúng cách.
- Theo dõi reactive function bằng Reactor tap và Micrometer.observation.
- Cấu hình context propagation qua thread và reactive pipeline.
- Xuất metrics qua Actuator/Prometheus và traces qua Micrometer Tracing/OTLP.
- Theo dõi Kafka consumer lag, Kafka Streams metrics và binder health.
- Thiết kế dashboard, cảnh báo và runbook cho luồng sự kiện.

## 1. Ba trụ cột quan sát hệ thống

Observability thường được xây dựng từ ba loại tín hiệu:

| Tín hiệu | Câu hỏi chính | Ví dụ trong Spring Cloud Stream |
|---|---|---|
| Logs | Chuyện gì đã xảy ra? | Function nhận event, lỗi deserialize, retry, publish thất bại |
| Metrics | Điều đó xảy ra bao nhiêu lần và kéo dài bao lâu? | Message rate, processing duration, error count, consumer lag |
| Traces | Một message đã đi qua những thành phần nào? | Producer → broker → consumer function → database → output topic |

Ba tín hiệu bổ sung cho nhau. Metric cho biết p95 processing time tăng, trace giúp tìm span chậm trong một lần xử lý, còn log cung cấp exception và dữ liệu chẩn đoán tại thời điểm đó.

Micrometer Observation là lớp API chung để mô tả một thao tác. Khi ObservationRegistry có các handler thích hợp, một observation có thể tạo timer/counter và span. Ứng dụng không cần viết riêng logic đo thời gian cho từng hệ thống metrics và tracing.

~~~mermaid
flowchart TD
    A["Spring Cloud Stream function invocation"] --> B["Micrometer Observation"]
    B --> C["ObservationRegistry"]
    C --> D["ObservationHandler"]
    D --> E["Metrics: timer, counter"]
    D --> F["Tracing: span, parent-child"]
    A --> G["Structured logs"]
    E --> H["Prometheus / metrics backend"]
    F --> I["OTel Collector / tracing backend"]
    G --> J["Log platform"]
~~~

Observation chỉ ghi nhận thao tác. Việc xuất dữ liệu ra backend cần registry, handler, exporter và cấu hình tương ứng. Nếu ứng dụng chưa có handler hoặc tracer bridge, một phần tín hiệu có thể không được xuất dù code đã tạo observation.

## 2. ObservationRegistry và vòng đời Observation

Các thành phần chính:

- ObservationRegistry: registry trung tâm mà instrumentation dùng để tạo observation.
- Observation: một thao tác cần được theo dõi, có tên, context và các key-value.
- ObservationHandler: nhận sự kiện start, error, event và stop để tạo metrics hoặc traces.
- ObservationConvention: quy định tên observation và metadata mặc định.
- ObservationPredicate: quyết định observation nào được ghi nhận.
- ObservationFilter: điều chỉnh context hoặc metadata trước khi handler xử lý.

Vòng đời điển hình:

1. Tạo observation với tên mô tả thao tác.
2. Thêm các key-value có cardinality phù hợp.
3. Bắt đầu observation và đưa nó vào scope hiện tại.
4. Thực hiện công việc.
5. Ghi nhận exception nếu có.
6. Dừng observation để handler hoàn tất timer/span.

API observe(...) tự quản lý các bước start, scope, error và stop:

~~~java
Observation.createNotStarted("orders.validation", observationRegistry)
    .lowCardinalityKeyValue("operation", "validate")
    .observe(() -> validate(order));
~~~

Nếu validate(...) ném exception, Observation ghi nhận lỗi rồi kết thúc trước khi exception được truyền tiếp. Điều này giúp metric duration và trace thể hiện cả lần xử lý thất bại.

Spring Boot tự cấu hình ObservationRegistry khi có Actuator và các dependency phù hợp. Có thể inject registry vào service hoặc function để tạo observation nghiệp vụ.

## 3. Bật observability cho function imperative

Function imperative thường có dạng Function<T, R>, Consumer<T>, Supplier<T> hoặc kiểu message handler đồng bộ. Framework gọi function cho mỗi message. Spring Cloud Stream tích hợp Spring Cloud Function bằng ObservationFunctionAroundWrapper để tạo observation quanh từng lần gọi.

Với các dependency observability cần thiết, mỗi invocation của imperative function được quan sát theo đơn vị một message. Ứng dụng có thể tập trung vào business logic mà không phải tự tạo một timer bao quanh toàn bộ function.

### Dependency cần thiết

Ví dụ Maven dependencies:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>

    <dependency>
        <groupId>io.projectreactor</groupId>
        <artifactId>reactor-core-micrometer</artifactId>
    </dependency>

    <dependency>
        <groupId>io.micrometer</groupId>
        <artifactId>micrometer-tracing-bridge-otel</artifactId>
    </dependency>

    <dependency>
        <groupId>io.opentelemetry</groupId>
        <artifactId>opentelemetry-exporter-otlp</artifactId>
    </dependency>

    <dependency>
        <groupId>io.micrometer</groupId>
        <artifactId>micrometer-registry-prometheus</artifactId>
    </dependency>
</dependencies>
~~~

Đây là một lựa chọn sử dụng OpenTelemetry bridge, OTLP exporter và Prometheus registry. Nếu hệ thống dùng Brave/Zipkin hoặc backend khác, thay tracer bridge/exporter tương ứng. Để dependency version được quản lý bởi Spring Boot và Spring Cloud BOM của dự án; không trộn các phiên bản độc lập ngoài ma trận tương thích.

### Ví dụ function nhận và phát event

~~~java
import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class OrderFunctions {

    private final OrderService orderService;

    OrderFunctions(OrderService orderService) {
        this.orderService = orderService;
    }

    @Bean
    Function<OrderCreated, OrderAccepted> acceptOrder() {
        return orderService::accept;
    }
}
~~~

Khi function được gọi, wrapper của Spring Cloud Function tạo observation cho invocation. Nếu có tracing bridge, observation có thể tạo span; nếu có meter handler, observation có thể tạo timer và metadata tương ứng.

Không cần bọc lại toàn bộ function bằng một observation thủ công chỉ để đo duration. Việc đó có thể tạo hai span gần như giống nhau và khiến dashboard khó đọc. Hãy tạo observation bổ sung cho một bước nghiệp vụ riêng, chẳng hạn kiểm tra tồn kho hoặc gọi hệ thống định giá.

## 4. Tạo observation cho bước nghiệp vụ

Giả sử function acceptOrder gọi dịch vụ catalog để xác minh sản phẩm. Có thể tạo observation riêng cho thao tác đó:

~~~java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;

import org.springframework.stereotype.Service;

@Service
class CatalogLookup {

    private final ObservationRegistry observationRegistry;
    private final CatalogClient catalogClient;

    CatalogLookup(
            ObservationRegistry observationRegistry,
            CatalogClient catalogClient) {
        this.observationRegistry = observationRegistry;
        this.catalogClient = catalogClient;
    }

    ProductInfo findProduct(OrderCreated event) {
        return Observation.createNotStarted(
                "orders.catalog.lookup",
                observationRegistry)
            .lowCardinalityKeyValue("dependency", "catalog")
            .lowCardinalityKeyValue("operation", "lookup")
            .highCardinalityKeyValue("eventId", event.eventId())
            .observe(() -> catalogClient.find(event.productId()));
    }
}
~~~

Trong ví dụ:
- Tên observation mô tả thao tác cụ thể.
- dependency và operation có tập giá trị hữu hạn, phù hợp làm low-cardinality metadata.
- eventId thay đổi theo từng message, nên được đánh dấu high-cardinality để dùng trong trace nhưng không tạo một time series riêng cho mỗi event.

Nếu catalogClient.find(...) lỗi, observation ghi nhận exception và kết thúc. Trace có thể thể hiện đây là span con của function invocation nếu context hiện tại được truyền đúng.

### Khi nào nên tạo observation con?

Tạo observation cho các bước có giá trị chẩn đoán độc lập:

- Gọi REST/gRPC service bên ngoài.
- Đọc hoặc ghi database nếu chưa được instrumentation tự động bao phủ.
- Chuyển đổi payload lớn hoặc tính toán tốn thời gian.
- Kiểm tra schema hoặc enrich event.
- Publish sang một destination khác khi cần phân biệt thời gian xử lý nghiệp vụ với thời gian gửi.

Không tạo một observation cho từng câu lệnh nhỏ. Nhiều span quá vụn làm tăng chi phí tracing và khiến người vận hành khó tìm ra bước có ý nghĩa.

## 5. Low-cardinality và high-cardinality metadata

Micrometer phân biệt metadata theo số lượng giá trị có thể xuất hiện.

| Loại | Đặc điểm | Ví dụ | Nơi phù hợp |
|---|---|---|---|
| Low cardinality | Tập giá trị nhỏ và có giới hạn | function, operation, outcome, region, binder | Metrics và traces |
| High cardinality | Giá trị thay đổi rất nhiều hoặc gần như duy nhất | eventId, orderId, traceId, customerId | Traces và log có kiểm soát |

Chỉ low-cardinality key-value được dùng làm meter tags. High-cardinality key-value chỉ đi vào trace. Nếu thêm orderId hoặc eventId làm metric tag, mỗi message có thể tạo một time series mới; hệ thống metrics sẽ tăng bộ nhớ, chi phí lưu trữ và độ trễ truy vấn.

Ví dụ nên dùng:

~~~java
Observation.createNotStarted("orders.persist", registry)
    .lowCardinalityKeyValue("operation", "persist")
    .lowCardinalityKeyValue("store", "orders-db")
    .highCardinalityKeyValue("eventId", event.eventId())
    .observe(() -> repository.save(order));
~~~

Tránh dùng payload, email, số điện thoại, token, thông tin xác thực hoặc dữ liệu cá nhân làm tag hay span attribute. Chỉ đưa metadata cần thiết vào trace và tuân thủ chính sách dữ liệu của hệ thống.

## 6. Theo dõi reactive function

Reactive function có vòng đời khác imperative function. Một function dạng Function<Flux<T>, Flux<R>> thường được gọi một lần khi ứng dụng khởi động để nối source stream với target stream. Sau đó Reactor điều khiển việc xử lý từng item.

Vì function chỉ được gọi lúc khởi tạo pipeline, ObservationFunctionAroundWrapper không thể tự tạo một observation cho mỗi message như với imperative function. Spring Cloud Stream không tự động quan sát toàn bộ reactive stream mà ứng dụng trả về.

Cần chọn rõ đơn vị cần quan sát:
- Mỗi item trong Flux.
- Một đoạn xử lý của mỗi item.
- Một batch.
- Một chuỗi xử lý dài hoặc một window.

Ví dụ dưới đây tạo observation cho từng item bằng tap:

~~~java
import io.micrometer.observation.ObservationRegistry;

import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.core.observability.micrometer.Micrometer;

@Configuration
class ReactiveOrderFunctions {

    @Bean
    Function<Flux<OrderCreated>, Flux<OrderAccepted>> enrichOrders(
            ObservationRegistry registry,
            OrderService orderService) {

        return orders -> orders.flatMap(order ->
            Mono.fromCallable(() -> orderService.enrich(order))
                .tap(Micrometer.observation(registry))
        );
    }
}
~~~

tap(...) gắn ObservationRegistry vào một segment của Reactor publisher. Ở ví dụ này, Mono đại diện cho xử lý một order, vì vậy mỗi item có một observation riêng. Nếu đặt tap(...) ở ngoài toàn bộ Flux, đơn vị quan sát sẽ đại diện cho cả subscription/stream thay vì từng message.

Nếu stream đã có observation trong Reactor Context, tap có thể tạo observation con. Nếu không có observation upstream, nó tạo observation mới theo registry được truyền vào.

### Context propagation trong Reactor

ThreadLocal không tự động được khôi phục trong mọi reactive operator. Nếu trace context bị mất khi đổi thread hoặc scheduler, log và span con có thể không còn cùng trace.

Có thể bật automatic context propagation của Reactor khi khởi động:

~~~java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import reactor.core.publisher.Hooks;

@SpringBootApplication
class StreamApplication {

    public static void main(String[] args) {
        Hooks.enableAutomaticContextPropagation();
        SpringApplication.run(StreamApplication.class, args);
    }
}
~~~

Với Spring Boot hỗ trợ cấu hình context propagation, có thể dùng:

~~~yaml
spring:
  reactor:
    context-propagation: auto
~~~

Chọn một cách phù hợp với phiên bản Reactor/Spring Boot của dự án và kiểm thử qua scheduler boundary. Không giả định việc inject ObservationRegistry đồng nghĩa context sẽ tự đi qua mọi executor, callback hoặc thư viện bất đồng bộ bên ngoài.

## 7. Tracing context qua message broker

Trace phân tán chỉ có ích khi context được truyền qua ranh giới process. Khi producer publish event, tracing instrumentation có thể ghi trace context vào message headers hoặc metadata mà binder hỗ trợ. Consumer đọc message rồi tiếp tục trace hoặc tạo trace liên kết theo propagation convention.

Các định dạng phổ biến gồm W3C Trace Context (traceparent/tracestate) và B3. Micrometer Tracing có thể cấu hình loại propagation được tiêu thụ và phát ra.

Một số điểm cần kiểm tra:
- Producer và consumer có cùng propagation format hay có cấu hình tương thích không.
- Binder có giữ các tracing headers qua serialization/header mapping không.
- Native encoding/decoding có vô tình bỏ qua header hay không.
- Middleware bên ngoài Spring có giữ header khi chuyển tiếp message không.
- Batch consumer có gom message từ nhiều trace khác nhau hay không.

Không phải binder nào cũng expose cùng mức instrumentation hoặc propagation. Hãy kiểm tra bằng integration test: phát một event, xử lý ở service thứ hai và xác nhận trace viewer hiển thị đúng quan hệ giữa producer, broker và consumer.

### Batch consumer và tracing

Một batch có thể chứa nhiều record từ nhiều producer, topic hoặc partition. Không thể gán một trace ID duy nhất cho toàn batch nếu từng record thuộc trace khác nhau. Với Kafka binder batch listener, tracing propagation không được hỗ trợ trực tiếp như record listener; các tracing headers có thể được cung cấp theo từng phần tử trong header đã chuyển đổi, nhưng ứng dụng phải tự xử lý từng record nếu cần observation riêng.

Nếu cần trace per-message rõ ràng, cân nhắc record listener hoặc tự tạo observation theo từng phần tử. Đừng dùng một span batch để giả định mọi record đều có cùng nguồn gốc.

## 8. Cấu hình Actuator, metrics và tracing

Actuator cung cấp endpoint để kiểm tra health, xem metrics và xuất dữ liệu cho hệ thống giám sát. Một cấu hình cơ bản:

~~~yaml
spring:
  application:
    name: order-stream
  reactor:
    context-propagation: auto

management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
  endpoint:
    health:
      show-details: when-authorized
  health:
    binders:
      enabled: true
  tracing:
    sampling:
      probability: 0.1
  observations:
    key-values:
      service: order-stream
      environment: production
~~~

Cấu hình này:
- Expose health, info, metrics và prometheus qua HTTP.
- Bật binder health indicator.
- Chỉ hiển thị health details cho caller được ủy quyền.
- Sample 10% trace trong ví dụ.
- Gắn service và environment vào observations.

Các endpoint Actuator có thể chứa thông tin nội bộ. Chỉ expose endpoint cần thiết và bảo vệ bằng network policy, authentication/authorization hoặc management port riêng. Không mở metrics, env, configprops hoặc bindings ra Internet công cộng.

### Prometheus

Để xuất metrics dạng Prometheus, thêm dependency:

~~~xml
<dependency>
    <groupId>io.micrometer</groupId>
    <artifactId>micrometer-registry-prometheus</artifactId>
</dependency>
~~~

Sau khi ứng dụng chạy, Prometheus có thể scrape endpoint:

~~~text
GET /actuator/prometheus
~~~

Endpoint /actuator/metrics cho phép liệt kê metric names và xem chi tiết từng meter. Dùng nó trong quá trình khám phá, còn production dashboard nên dựa trên metric names và labels đã được chuẩn hóa trong phiên bản đang triển khai.

### Tracing qua OTLP

Với Micrometer Tracing và OpenTelemetry bridge, Spring Boot có thể gửi spans tới OpenTelemetry Collector bằng OTLP. Ví dụ property cho một số phiên bản Spring Boot 3.x:

~~~yaml
management:
  tracing:
    sampling:
      probability: 0.1
  otlp:
    tracing:
      endpoint: http://otel-collector:4318/v1/traces
~~~

Tên property và cấu hình exporter có thể thay đổi giữa các dòng Spring Boot. Hãy dùng đúng tài liệu của phiên bản BOM đang quản lý ứng dụng. Collector cần được cấu hình để nhận OTLP HTTP hoặc gRPC theo endpoint mà exporter sử dụng.

Sampling probability điều khiển tỷ lệ trace được ghi nhận. Giá trị 1.0 ghi nhận mọi trace; giá trị 0.1 lấy mẫu khoảng 10%. Sampling không có nghĩa metric chỉ được ghi 10%: metrics vẫn được thu thập theo cơ chế meter registry. Chọn tỷ lệ dựa trên lưu lượng, chi phí và mức độ cần điều tra.

## 9. Theo dõi binder và function bằng metrics

Metrics cần phản ánh cả xử lý nghiệp vụ và vận chuyển message. Một function có thể xử lý nhanh nhưng consumer lag tăng vì broker không cấp đủ partition hoặc producer phát nhanh hơn tốc độ xử lý.

Các nhóm metrics nên có:

| Nhóm | Metrics cần theo dõi | Ý nghĩa |
|---|---|---|
| Function | Invocation count, duration, error count | Tốc độ và độ ổn định của hàm |
| Producer | Send rate, send failures, publish latency | Khả năng phát event |
| Consumer | Receive rate, processing duration, retry count | Khả năng xử lý message |
| Backlog | Consumer lag, queue depth, oldest message age | Mức tồn đọng |
| Reliability | Redelivery, DLQ count, ack/checkpoint failures | Chất lượng giao nhận |
| Runtime | JVM memory, GC, thread pool, CPU | Tài nguyên process |
| Tracing | Sampled trace count, error spans, trace duration | Điều tra một luồng xử lý cụ thể |

Không phải tất cả binder đều xuất cùng tên metric hoặc cùng labels. Hãy xem metrics do binder cung cấp, metrics do broker cung cấp và custom metrics của ứng dụng như các nguồn bổ sung.

### Bật observation cho Kafka binder

Kafka binder có property riêng để bật Micrometer Observation trên các binding thuộc binder đó. Property này mặc định là false:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        binder:
          enable-observation: true
~~~

Với reactive Kafka binder, producer binding có hỗ trợ observation khi property này được bật; việc publish qua StreamBridge và Supplier cũng có thể được quan sát. Consumer reactive cần xử lý context và observation theo pipeline, đặc biệt khi topic được publish bởi một hệ thống bên ngoài Spring Cloud Stream. Không bật property này rồi giả định mọi consumer/binder đều có cùng hành vi; hãy xác minh theo binder implementation và test propagation ở hai đầu.

### Kafka binder offset lag

Kafka binder cung cấp metric:

~~~text
spring.cloud.stream.binder.kafka.offset
~~~

Metric này biểu diễn số record chưa được consumer group xử lý theo topic/group dựa trên committed offset và latest offset. Có thể dùng để:
- Phát hiện consumer tụt lại so với producer.
- So sánh lag giữa các group.
- Cấp tín hiệu cho autoscaling.
- Phân biệt consumer chậm với topic không có dữ liệu.

Kafka binder có các cấu hình điều khiển cách tính offset lag, ví dụ bật tính toán khi truy vấn hoặc dùng giá trị được cập nhật định kỳ. Kiểm tra property metrics của đúng phiên bản binder vì cách tính lag có thể ảnh hưởng tải metadata và thời gian trả metric.

### Kafka Streams metrics

Kafka Streams binder cung cấp metrics của Kafka Streams và có thể export qua Micrometer MeterRegistry. Những metrics này giúp theo dõi stream threads, task, state store, record processing và các hoạt động nội bộ của Kafka Streams.

Kết hợp:
- Kafka consumer lag của input topics.
- Kafka Streams thread state.
- Processing rate và latency.
- State restoration và changelog activity.
- RocksDB/state store disk usage.

Không chỉ nhìn trạng thái RUNNING. Một topology có thể RUNNING nhưng xử lý chậm, output không tăng hoặc input lag liên tục cao.

## 10. Binder health và readiness

Spring Cloud Stream có binder health indicator đăng ký dưới tên binders. Có thể bật bằng:

~~~yaml
management:
  health:
    binders:
      enabled: true
~~~

Endpoint:

~~~text
GET /actuator/health
~~~

Health indicator phụ thuộc implementation của binder. Một số binder có thể kiểm tra broker connection, trong khi binder khác không cung cấp health indicator. Vì vậy, không thể kết luận mọi binder đều có cùng dữ liệu chỉ vì cùng dùng Spring Cloud Stream.

### Kafka Streams health

Kafka Streams binder cung cấp health indicator kiểm tra trạng thái stream threads. Chi tiết có thể gồm:
- Thread name.
- Thread state.
- Active tasks và partition.
- Standby tasks và partition.

Các trạng thái thường gặp gồm CREATED, RUNNING, PARTITIONS_REVOKED, PARTITIONS_ASSIGNED, PENDING_SHUTDOWN và DEAD. Health có thể là UP khi tất cả stream threads được đăng ký đều ở RUNNING.

Nếu ứng dụng có nhiều Kafka Streams processor, health details được nhóm theo application ID. Điều này giúp tìm processor nào không hoạt động.

### Liveness và readiness

Liveness trả lời process có còn sống và cần được giữ chạy hay không. Readiness trả lời instance có sẵn sàng nhận traffic/message hay không.

Không nên đưa mọi lỗi broker tạm thời vào liveness. Nếu broker gián đoạn khiến liveness fail, Kubernetes có thể liên tục restart instance trong lúc broker vẫn đang phục hồi. Thường nên:
- Liveness tập trung vào khả năng sống của process.
- Readiness có thể xét binder health và dependency thiết yếu.
- Alert riêng cho broker unavailable, consumer lag và processing errors.
- Có grace period cho startup, rebalance và state restoration.

## 11. Logs và correlation

Logs giúp tìm chi tiết một message hoặc exception. Khi tracing được cấu hình, log pattern có thể đưa traceId và spanId vào mỗi dòng để tra cứu chéo với trace backend.

Nên ghi các trường có ích:
- eventId hoặc messageId.
- function name và binding.
- topic/destination và consumer group.
- operation và outcome.
- retry attempt hoặc delivery count nếu có.
- traceId và spanId khi có tracing context.

Không log toàn bộ payload mặc định. Payload có thể chứa dữ liệu cá nhân, token hoặc thông tin nghiệp vụ nhạy cảm. Với lỗi serialization, ghi schema version, content type và message ID thay vì dump dữ liệu bí mật.

Ví dụ log có cấu trúc:

~~~java
log.info(
    "Order event processed: eventId={}, orderId={}, outcome={}",
    event.eventId(),
    event.orderId(),
    "ACCEPTED"
);
~~~

Nếu eventId hoặc orderId có cardinality cao, giữ chúng trong log/trace để tra cứu theo message. Không đưa chúng vào metric tags.

## 12. Tùy chỉnh ObservationConvention và lọc observation

Khi cần quy ước thống nhất tên và metadata, có thể dùng ObservationConvention. Convention giúp các service tạo observation theo cùng một schema: tên operation, binder, function, outcome và các thuộc tính có ý nghĩa.

Các điểm mở rộng của ObservationRegistry:
- ObservationPredicate: bỏ qua observation theo điều kiện.
- ObservationFilter: điều chỉnh context.
- ObservationHandler: thêm cách xuất dữ liệu.
- GlobalObservationConvention: áp dụng quy ước chung.
- ObservationRegistryCustomizer: tùy chỉnh registry.

Spring Boot tự đăng ký các bean tương ứng vào ObservationRegistry. Nếu chỉ muốn loại bỏ một observation không cần thiết, dùng predicate/filter thay vì tạo nhiều instrumentation chồng lên nhau.

### Annotation @Observed

Micrometer hỗ trợ các annotation như @Observed, @Timed và @Counted. Với Spring Boot, cần bật:

~~~yaml
management:
  observations:
    annotations:
      enabled: true
~~~

Và thêm AspectJ weaver phù hợp với dòng Spring Boot đang dùng. Nếu method đã được framework tự động instrument, thêm @Observed có thể tạo duplicate observation. Chỉ bật annotation cho method chưa có instrumentation hoặc chủ động loại bỏ instrumentation trùng bằng predicate/configuration.

## 13. Đọc một tình huống vận hành

Giả sử dashboard hiển thị:
- Producer rate ổn định.
- Consumer lag tăng liên tục.
- Function processing p95 tăng từ 40 ms lên 900 ms.
- Error rate không tăng đáng kể.
- JVM CPU tăng nhưng memory ổn định.

Cách điều tra:
1. Xem trace có thời gian lớn nhất để xác định span con chậm.
2. Nếu span catalog lookup chậm, kiểm tra downstream service và connection pool.
3. Nếu function duration cao nhưng span con không cao, kiểm tra serialization, scheduler, lock hoặc phần code chưa instrument.
4. So sánh consumer concurrency với số partition.
5. Kiểm tra broker throttling, rebalance và network.
6. Xem lag theo topic/partition để phát hiện hot partition.
7. Đánh giá scaling có thể tăng throughput hay chỉ làm tăng cạnh tranh tài nguyên.

Một tình huống khác: function duration bình thường nhưng oldest message age tăng. Điều này có thể do message đã nằm trong broker lâu trước khi được consumer nhận. Cần metric về backlog và thời gian từ event timestamp đến processing start, không chỉ timer của function.

## 14. Dashboard và cảnh báo đề xuất

Một dashboard cho Spring Cloud Stream nên chia thành các hàng:

| Hàng dashboard | Biểu đồ | Câu hỏi vận hành |
|---|---|---|
| Traffic | Input/output messages per second | Producer và consumer có hoạt động không? |
| Latency | Function p50/p95/p99, end-to-end age | Message xử lý có chậm không? |
| Errors | Function exceptions, send failures, deserialization errors | Lỗi xảy ra ở tầng nào? |
| Backlog | Kafka lag, queue depth, oldest message age | Consumer có theo kịp producer không? |
| Reliability | Retry, redelivery, DLQ, ack/checkpoint failures | Có message bị giao lại hoặc cách ly không? |
| Runtime | CPU, memory, GC, thread pool | Instance có thiếu tài nguyên không? |
| Broker health | Binder health, broker connections, partition/task state | Hệ thống có kết nối và phân phối tải đúng không? |

Cảnh báo nên gắn với tác động nghiệp vụ:
- Lag vượt ngưỡng trong một khoảng thời gian đủ dài.
- Oldest message age vượt SLA.
- DLQ tăng đột biến.
- Publish failures hoặc ack/checkpoint failures tăng.
- Kafka Streams thread ở DEAD hoặc không chuyển sang RUNNING.
- Function error rate vượt SLO.
- Tracing backend hoặc metrics exporter không nhận dữ liệu.

Tránh alert chỉ dựa trên một spike ngắn. Dùng cửa sổ thời gian, baseline và mức độ nghiêm trọng để giảm false positive.

## 15. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Function imperative không có trace | Thiếu actuator, tracer bridge hoặc exporter | Kiểm tra dependency, ObservationRegistry và sampling |
| Có metric nhưng không có trace | Chưa cấu hình tracer bridge/exporter hoặc trace bị sample out | Kiểm tra tracer và sampling probability |
| Reactive function chỉ có một observation lúc startup | Function reactive không được tự động bọc theo từng message | Dùng tap(Micrometer.observation(registry)) trên segment từng item |
| Trace bị tách khi đổi scheduler | Context propagation chưa được bật | Cấu hình Reactor context propagation và kiểm thử scheduler |
| Metrics tăng time series bất thường | Dùng eventId/orderId làm low-cardinality tag | Chuyển dữ liệu đó sang high-cardinality trace attribute hoặc log |
| Có hai span giống nhau | Function đã được auto-wrap nhưng lại tự tạo observation toàn function | Giữ wrapper, chỉ tạo observation con cho bước nghiệp vụ |
| Binder health không có thông tin | Binder implementation không cung cấp health indicator | Dùng broker metrics và custom HealthIndicator nếu cần |
| Kafka lag metric không xuất hiện | Micrometer/binder metrics chưa được cấu hình hoặc bị filter | Kiểm tra MeterRegistry, metric configuration và version |
| Kafka Streams health DOWN | Thread chưa RUNNING, DEAD hoặc đang restore/rebalance | Kiểm tra state, task, broker và state restoration |
| Logs không tìm được trace | Trace context không vào MDC hoặc bị mất khi async | Kiểm tra tracing bridge và context propagation |
| Batch trace không khớp record | Một batch chứa nhiều message thuộc nhiều trace | Theo dõi per-record hoặc thiết kế span batch có links |
| Metrics endpoint trả 404 | Endpoint chưa được expose hoặc thiếu registry | Kiểm tra Actuator dependency và exposure properties |
| Prometheus không scrape được | Thiếu registry hoặc endpoint bị chặn | Thêm Prometheus registry và kiểm tra security/network |
| Exporter gây tải cao | Sampling, export batch hoặc timeout chưa phù hợp | Điều chỉnh sampling, exporter và collector capacity |

## 16. Bài thực hành: theo dõi function acceptOrder

Xây dựng function xử lý đơn hàng và theo dõi cả thao tác function lẫn bước gọi catalog.

1. Thêm Actuator, reactor-core-micrometer và tracer bridge theo BOM.
2. Tạo function imperative acceptOrder nhận OrderCreated.
3. Xác nhận function invocation được tự động tạo observation.
4. Inject ObservationRegistry vào CatalogLookup.
5. Tạo observation con orders.catalog.lookup cho lời gọi catalog.
6. Thêm low-cardinality tags operation và dependency.
7. Đưa eventId vào high-cardinality trace attribute.
8. Cấu hình sampling 10% cho môi trường production thử nghiệm.
9. Expose health, metrics và prometheus endpoint trong management network.
10. Bật binder health và kiểm tra /actuator/health.
11. Gửi một event hợp lệ và một event gây lỗi catalog.
12. Xác minh metric duration/error và trace span con.
13. Đổi function thành reactive Flux và dùng tap(Micrometer.observation(registry)) cho mỗi item.
14. Kiểm thử trace context qua scheduler boundary.
15. Tạo dashboard gồm message rate, function p95, error rate, consumer lag và DLQ count.
16. Mô phỏng consumer chậm và xác minh cảnh báo lag/oldest-message-age.
17. Kiểm tra metric labels không chứa eventId, orderId hoặc dữ liệu nhạy cảm.

Bảng nghiệm thu:

| Hạng mục | Kết quả cần xác nhận |
|---|---|
| Dependencies | Actuator, Reactor Micrometer và tracer bridge tương thích BOM |
| Imperative function | Có observation cho mỗi invocation/message |
| Custom observation | Có span con cho thao tác nghiệp vụ |
| Cardinality | Low/high cardinality được phân loại đúng |
| Reactive function | Mỗi item/segment có observation theo thiết kế |
| Context propagation | Trace không mất qua reactive scheduler |
| Metrics export | Có thể truy vấn qua Actuator/Prometheus |
| Trace export | Trace đến đúng backend |
| Binder health | Có trạng thái broker/binder khi implementation hỗ trợ |
| Kafka lag | Có metric theo topic/group và cảnh báo phù hợp |
| Kafka Streams | Theo dõi thread state, task và runtime metrics |
| Security | Management endpoints không public và không lộ payload |
| Dashboard | Có traffic, latency, error, backlog và reliability |
| Alert | Cảnh báo gắn với SLA và có runbook xử lý |

## Kết luận

Micrometer Observation giúp Spring Cloud Stream quan sát function ở cùng một mô hình cho metrics và traces. Với imperative function, Spring Cloud Function cung cấp ObservationFunctionAroundWrapper để ghi nhận từng invocation. Với reactive function, cần dùng Reactor tap và ObservationRegistry để chọn đơn vị quan sát phù hợp vì framework không tự bọc stream trả về.

Hãy kết hợp function duration, error rate, broker lag, binder health và distributed traces. Kafka binder có offset lag metric; Kafka Streams binder có metrics và health theo thread/task; các binder khác có thể expose tín hiệu khác nhau nên cần bổ sung broker-side metrics. Giữ metric tags ở low cardinality, truyền trace context qua message headers, bảo vệ Actuator endpoints và kiểm thử cả đường xử lý thành công lẫn failure path.

## Tài liệu tham khảo

- [Spring Cloud Stream 5.0.4 – Observability](https://docs.spring.io/spring-cloud-stream/reference/observability.html)
- [Spring Cloud Stream – Health Indicator](https://docs.spring.io/spring-cloud-stream/reference/health-indicator.html)
- [Spring Cloud Stream – Kafka Binder Metrics](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/metrics.html)
- [Spring Cloud Stream – Reactive Kafka Binder Observability](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-reactive-binder/reactive_observability.html)
- [Spring Cloud Stream – Kafka Streams Health Indicator](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-streams-binder/health-indicator.html)
- [Spring Boot 3.5 – Observability](https://docs.spring.io/spring-boot/3.5/reference/actuator/observability.html)
- [Spring Boot – Tracing](https://docs.spring.io/spring-boot/reference/actuator/tracing.html)
- [Spring Boot – Actuator Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html)
- [Micrometer – Observation Components](https://docs.micrometer.io/micrometer/reference/observation/components.html)
- [Micrometer – High Cardinality Tags](https://docs.micrometer.io/micrometer/reference/concepts/high-cardinality-tags-detector.html)
- [Reactor – Micrometer Integration](https://projectreactor.io/docs/core/release/reference/metrics.html)

