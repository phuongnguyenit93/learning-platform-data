# Không thấy trace do sampling, exporter hoặc lỗi kết nối

> **Chương:** Chẩn đoán sự cố  
> **Module:** SPRING_AI_EVALUATION_OBSERVABILITY — đánh giá chất lượng ứng dụng Spring AI bằng tập dữ liệu, tiêu chí relevance, fact checking và kiểm thử luồng RAG hoặc gọi công cụ; đồng thời đo metrics, traces, chi phí và độ trễ để phát hiện nguyên nhân suy giảm qua từng phiên bản prompt, model và pipeline.

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt Observation đã được tạo, span đã được tạo, span được sampler giữ lại, span đã export và trace đã được backend lưu/index.
2. Chẩn đoán việc không thấy trace do thiếu tracing bridge/handler, sampling, context propagation, exporter, Collector hoặc backend.
3. Phân biệt head sampling ở ứng dụng với tail sampling ở Collector và hiểu giới hạn của từng cách.
4. Kiểm tra cấu hình Micrometer Tracing, OpenTelemetry/Zipkin, OTLP endpoint, network, TLS, authentication và batching.
5. Theo dõi trace xuyên suốt Spring AI ChatClient, EmbeddingModel, VectorStore và các bước RAG.
6. Viết Observation có cấu trúc, kiểm tra async context propagation và tạo integration test cho trace export.
7. Dùng runbook để tìm đúng chặng đầu tiên làm mất trace mà không thu thập raw prompt hoặc dữ liệu nhạy cảm không cần thiết.

## 1. Triệu chứng: request chạy nhưng không thấy trace

Một ứng dụng Spring AI trả lời RAG bình thường. Metrics vẫn tăng, log vẫn có request, nhưng hệ thống tracing không hiển thị trace tương ứng. Tình huống này không nhất thiết có nghĩa Spring AI không tạo Observation.

Trace phải đi qua nhiều bước:

- Code phát Observation quanh operation.
- ObservationRegistry nhận Observation.
- Tracing ObservationHandler chuyển Observation thành span.
- Sampler quyết định span/trace có được ghi nhận hay không.
- Span processor hoàn tất và chuyển span tới exporter.
- Exporter gửi dữ liệu qua OTLP, Zipkin hoặc giao thức được cấu hình.
- Collector/backend nhận, xử lý, lưu và index trace.
- Giao diện truy vấn đúng project, tenant, service và khoảng thời gian.

Chỉ cần một bước không hoạt động, trace có thể biến mất ở nơi người vận hành đang tìm.

### 1.1. Đường đi của trace

~~~mermaid
flowchart TD
  A["Spring AI / application operation"] --> B["Observation"]
  B --> C["ObservationRegistry"]
  C --> D["Tracing ObservationHandler"]
  D --> E["Span creation"]
  E --> F["Sampler"]
  F -->|Record| G["Span processor"]
  F -->|Drop| X["No exported span"]
  G --> H["Batch queue / flush"]
  H --> I["OTLP or Zipkin exporter"]
  I --> J["Collector / tracing backend"]
  J --> K["Ingest / storage / indexing"]
  K --> L["Trace search UI"]
  I -.-> R["Network / DNS / TLS / auth"]
  R -.-> J
~~~

Một Observation có thể được dùng cho metrics mà không tạo span nếu tracing handler không có. Tương tự, span có thể được tạo nhưng sampler loại bỏ trước khi export. Khi exporter gửi thành công, backend vẫn có thể chưa index hoặc người dùng đang tìm nhầm project/time range.

### 1.2. Phân biệt các trạng thái

| Trạng thái | Bằng chứng | Điều chưa được chứng minh |
|---|---|---|
| Observation được phát | Observation test handler hoặc instrumentation lifecycle thấy event | Chưa chắc có span |
| Span được tạo | Tracing handler/SDK ghi nhận span | Chưa chắc sampler giữ lại |
| Span được sample/record | Span có recording state hoặc được exporter nhận | Chưa chắc export thành công |
| Exporter gửi thành công | Export call/Collector receiver xác nhận nhận dữ liệu | Chưa chắc backend đã lưu/index |
| Backend đã lưu/index | Query API tìm được trace ID | Chưa chắc dashboard đang truy vấn đúng phạm vi |
| Trace hiển thị trong UI | Search đúng service/time range có kết quả | Không chứng minh mọi trace đều được giữ vì sampling |

Đừng dùng một thông báo “export succeeded” làm bằng chứng cho toàn bộ pipeline. Cần xác minh từng ranh giới.

## 2. Phân biệt Observation, span và trace

### 2.1. Observation

Observation của Micrometer mô tả một thao tác có thời gian bắt đầu/kết thúc, context và key-values. Spring AI dùng Observation để instrument các thành phần như ChatClient, ChatModel, EmbeddingModel và VectorStore theo cấu hình/phiên bản.

Observation là abstraction ở tầng ứng dụng. Nó có thể được xử lý bởi nhiều handler khác nhau:

- Meter handler tạo metrics.
- Tracing handler tạo span.
- Custom handler ghi audit hoặc context theo policy.

Vì thế có metrics nhưng không có trace là tình huống có thể xảy ra nếu meter handler tồn tại còn tracing handler/bridge không có hoặc không được cấu hình.

### 2.2. Span

Span biểu diễn một đơn vị công việc trong trace:

- Tên operation.
- Trace ID và Span ID.
- Parent Span ID nếu là span con.
- Thời điểm bắt đầu/kết thúc.
- Status/error.
- Attributes và events.

Ví dụ một trace RAG:

~~~text
app.rag.answer
  ├── app.rag.retrieve
  │     ├── spring.ai.embedding
  │     └── db.vector.client.operation
  ├── app.rag.prompt_assembly
  └── spring.ai.chat
~~~

Tên span cụ thể phụ thuộc instrumentation/version. Sơ đồ chỉ minh họa quan hệ cha-con; không phải danh sách span name bắt buộc của Spring AI.

### 2.3. Trace

Trace là tập hợp các span liên quan, được nối với nhau bằng Trace ID và quan hệ parent-child hoặc span links. Nếu context không được truyền qua thread, executor, message broker hoặc HTTP boundary, operation con có thể tạo trace độc lập hoặc không có parent như mong muốn.

Một trace phân tán có thể chỉ có một phần span nếu một service không instrument, một đoạn context bị mất hoặc một số span bị sampling/drop. Đừng kết luận toàn bộ trace bị mất khi chỉ thấy root span mà thiếu child span.

## 3. Sampling: nguyên nhân phổ biến nhất

Sampling quyết định trace nào được giữ để ghi nhận và export. Sampling giúp kiểm soát dung lượng và chi phí, nhưng cũng khiến người vận hành không thấy một số request dù ứng dụng vẫn chạy bình thường.

### 3.1. Head sampling

Head sampler quyết định ở đầu trace hoặc khi span được tạo, trước khi biết kết quả cuối cùng. Ví dụ xác suất 10% có thể giữ khoảng 10% trace trong điều kiện traffic lớn và phân phối phù hợp.

Ưu điểm:

- Giảm lượng span được ghi/export ngay từ ứng dụng.
- Giảm network, Collector load và storage.
- Cấu hình tương đối đơn giản.

Giới hạn:

- Không biết trace có lỗi hoặc latency cao ở cuối pipeline khi quyết định.
- Request quan trọng nhưng không được chọn có thể không xuất hiện.
- Nếu root trace bị drop, Collector tail sampler không thể khôi phục các span chưa từng được gửi.

### 3.2. Spring Boot sampling probability

Với Spring Boot và Micrometer Tracing, có thể cấu hình xác suất sampling bằng property:

~~~yaml
management:
  tracing:
    sampling:
      probability: 1.0
~~~

Giá trị 1.0 thường dùng trong local/test để giữ toàn bộ trace được instrument trong phạm vi cấu hình sampler. Giá trị 0.1 tương ứng xác suất khoảng 10% trong cấu hình ratio-based thông dụng. Default và hành vi chính xác cần kiểm tra theo Spring Boot version, bridge và sampler đang dùng.

Không bật 100% sampling vô điều kiện trên production có traffic lớn. Nó có thể làm tăng mạnh chi phí, payload, network, Collector queue và storage. Dùng 100% trong một test ngắn hoặc cohort có giới hạn, sau đó trả về policy phù hợp.

### 3.3. Parent-based sampling

Trong distributed tracing, sampler con thường kế thừa quyết định sampling từ parent theo parent-based policy. Nếu upstream service đã đánh dấu trace không được sample, downstream có thể tiếp tục quyết định drop theo context đó.

Điều này giải thích một trường hợp:

- Service A gửi request với traceparent có sampled flag tắt.
- Service B nhận context và tạo span con.
- Sampler của B tuân theo parent decision nên span không được export.

Nếu thay đổi sampler cục bộ nhưng upstream vẫn truyền quyết định không sample, kết quả có thể không thay đổi như mong đợi. Kiểm tra trace context headers và sampler policy ở toàn bộ chuỗi service.

### 3.4. Tail sampling

Tail sampling quyết định giữ trace sau khi Collector đã nhận đủ các span cần thiết hoặc sau một khoảng chờ. Nó có thể chọn trace dựa trên:

- Có span lỗi.
- Latency vượt ngưỡng.
- Service/operation quan trọng.
- Attribute đã được cho phép.
- Xác suất hoặc quota theo tenant/service.

Ưu điểm là có thể giữ trace lỗi/chậm và loại trace bình thường sau khi đã quan sát kết quả.

Giới hạn:

- Collector phải nhận được span trước khi quyết định.
- Cần giữ các span của cùng trace đủ lâu để đánh giá.
- Cần phân vùng/định tuyến các span cùng Trace ID đến cùng tail-sampling processor.
- Cần cấu hình decision wait, memory và capacity phù hợp.
- Không thể khôi phục span đã bị head sampler drop ở ứng dụng.

### 3.5. Ma trận phân biệt

| Dấu hiệu | Head sampling | Tail sampling |
|---|---|---|
| Quyết định ở đâu? | SDK/ứng dụng khi span bắt đầu | Collector sau khi nhận span |
| Biết kết quả lỗi/latency cuối? | Không | Có thể, nếu đã nhận đủ span |
| Giảm traffic trước Collector? | Có | Không; span vẫn phải được gửi tới Collector |
| Có thể khôi phục trace đã bị upstream drop? | Không | Không |
| Thành phần cần kiểm tra | Sampling probability, parent sampled flag, SDK sampler | Collector tail_sampling policy, decision wait, routing và memory |

Không nhầm sampling với exporter failure. Nếu trace bị sampler loại, exporter không có span để gửi; tăng retry của exporter không giải quyết được.

## 4. Tracing bridge và dependency

Spring AI Observation cần một tracing implementation được tích hợp để tạo và export span. Trong Spring Boot, Micrometer Tracing thường kết nối Observation với một bridge như OpenTelemetry hoặc Brave.

### 4.1. Nhóm dependency thường gặp

| Dependency | Vai trò |
|---|---|
| spring-boot-starter-actuator | Auto-configuration và management integration |
| micrometer-tracing-bridge-otel | Bridge Micrometer Tracing sang OpenTelemetry |
| opentelemetry-exporter-otlp | Export span bằng OTLP |
| micrometer-tracing-bridge-brave | Bridge Micrometer Tracing sang Brave |
| zipkin-reporter-brave | Export span theo Zipkin protocol |
| Spring AI starter/adapter | Instrumentation cho thành phần Spring AI theo version |

Đây là các lựa chọn bridge/exporter; không thêm đồng thời nhiều bridge chỉ để thử. Chọn một tracing implementation phù hợp với stack và dùng dependency management của Spring Boot để căn chỉnh phiên bản.

### 4.2. Ví dụ Maven với OpenTelemetry/OTLP

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>
    <dependency>
        <groupId>io.micrometer</groupId>
        <artifactId>micrometer-tracing-bridge-otel</artifactId>
    </dependency>
    <dependency>
        <groupId>io.opentelemetry</groupId>
        <artifactId>opentelemetry-exporter-otlp</artifactId>
        <scope>runtime</scope>
    </dependency>
    <!-- Spring AI starter/VectorStore adapter của dự án -->
</dependencies>
~~~

Artifact versions nên do Spring Boot dependency management/BOM quản lý nếu stack tương thích. Không tự pin một bộ OpenTelemetry SDK/Exporter khác phiên bản bridge nếu chưa xác minh compatibility.

### 4.3. Ví dụ Gradle

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-actuator")
    implementation("io.micrometer:micrometer-tracing-bridge-otel")
    runtimeOnly("io.opentelemetry:opentelemetry-exporter-otlp")

    // Spring AI starter/VectorStore adapter của dự án.
}
~~~

### 4.4. Kiểm tra runtime dependency tree

Maven:

~~~bash
mvn dependency:tree
~~~

Gradle:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Kiểm tra:

- Có Actuator/Micrometer Tracing ở runtime.
- Có đúng một bridge được chọn theo thiết kế.
- Có exporter tương ứng nếu cần gửi span ra ngoài process.
- Không chỉ có tracing dependencies trong test scope.
- Không có nhiều phiên bản OpenTelemetry API/SDK/exporter xung đột.
- Không exclude auto-configuration tracing ngoài ý muốn.

Metrics hoạt động không chứng minh tracing bridge đã được cài. Một MeterRegistry có thể tồn tại độc lập với tracing bridge.

## 5. Kiểm tra ObservationRegistry và tracing handler

Spring Boot thường auto-configure ObservationRegistry và các handler phù hợp khi có dependency. Tuy nhiên, custom bean có thể làm auto-configuration lùi lại.

### 5.1. Custom ObservationRegistry

Ví dụ dễ gây lỗi:

~~~java
@Bean
ObservationRegistry observationRegistry() {
    return ObservationRegistry.create();
}
~~~

Registry tự tạo không tự có tracing handler hoặc meter handler mà Boot đã thiết lập trong context. Nếu code dùng registry này nhưng Spring AI dùng registry khác, Observation cũng có thể đi vào hai pipeline khác nhau.

Trong Spring Boot, ưu tiên inject registry do framework quản lý. Nếu cần registry độc lập, hãy đăng ký đúng handlers và xác nhận tất cả instrumentation đang dùng đúng instance.

### 5.2. Kiểm tra handler và registry

Kiểm tra bằng bean diagnostics/condition report:

- ObservationRegistry nào được inject vào service?
- Spring AI adapter nhận registry nào?
- Có tracing bridge và tracing handler không?
- Có tracing SDK/provider được tạo không?
- Có exporter/SpanProcessor được cấu hình không?
- Có custom ObservationFilter/Convention làm thay đổi hoặc bỏ span không?

Không chỉ kiểm tra bean class tồn tại. Một handler có thể được tạo nhưng không được đăng ký vào registry thực tế đang nhận Observation.

### 5.3. Observation probe

Có thể phát một Observation thử trong test/dev:

~~~java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;

public final class TraceObservationProbe {
    private final ObservationRegistry registry;

    public TraceObservationProbe(ObservationRegistry registry) {
        this.registry = registry;
    }

    public void run() {
        Observation.createNotStarted("app.telemetry.trace.probe", registry)
                .lowCardinalityKeyValue("probe", "trace-path")
                .observe(() -> {
                    // Công việc không chứa dữ liệu nhạy cảm.
                });
    }
}
~~~

Probe này chỉ tạo span nếu registry có tracing handler phù hợp và sampler giữ trace. Nếu metrics probe thành công nhưng trace probe không xuất hiện, tập trung vào bridge, handler và sampler. Nếu probe xuất hiện nhưng VectorStore span không có, kiểm tra adapter/version/code path.

## 6. Cấu hình OTLP hoặc Zipkin exporter

Một ứng dụng có thể tạo span nhưng không gửi được do exporter chưa cấu hình, endpoint sai hoặc kết nối thất bại.

### 6.1. OTLP transport

OTLP phổ biến có hai transport:

| Transport | Cổng mặc định thường gặp | Endpoint mẫu |
|---|---:|---|
| OTLP/gRPC | 4317 | otel-collector:4317 |
| OTLP/HTTP | 4318 | http://otel-collector:4318/v1/traces |

Port và path có thể được thay đổi bởi deployment. Không mặc định HTTP endpoint và gRPC endpoint dùng cùng URL/path. Nếu dùng OTLP/HTTP, kiểm tra endpoint traces có suffix phù hợp với cấu hình exporter/SDK; một số cấu hình nhận base endpoint rồi tự thêm path, một số cấu hình yêu cầu URL đầy đủ.

### 6.2. Spring Boot OTLP property

Trong các phiên bản Spring Boot hỗ trợ OTLP tracing auto-configuration, endpoint có thể được cấu hình theo property tương ứng, ví dụ:

~~~yaml
management:
  otlp:
    tracing:
      endpoint: http://otel-collector:4318/v1/traces
~~~

Tên property, default, transport và cách kết hợp với exporter dependency phụ thuộc Spring Boot version. Xác minh bằng configuration metadata/reference đúng version. Nếu property không được bind, exporter có thể vẫn dùng localhost hoặc endpoint mặc định.

### 6.3. Zipkin exporter

Nếu stack dùng Brave/Zipkin, cấu hình endpoint Zipkin tương ứng, thường là API ingest của Zipkin:

~~~yaml
management:
  zipkin:
    tracing:
      endpoint: http://zipkin:9411/api/v2/spans
~~~

Không cấu hình Zipkin endpoint khi ứng dụng chỉ có OTLP exporter, hoặc ngược lại. Xác định exporter implementation đang được tạo từ runtime dependencies và condition report.

### 6.4. Batching và flush

Tracing exporter thường dùng processor/batch queue để gom span trước khi gửi. Trace có thể không thấy ngay nếu:

- Batch chưa đến ngưỡng export.
- Scheduled delay chưa tới.
- Queue bị đầy hoặc exporter đang retry.
- Request kết thúc nhưng process bị kill trước khi flush.
- Shutdown hook không chạy hoặc timeout quá ngắn.
- Export timeout ngắn hơn thời gian mạng/backend cần.

Trong local/test, có thể dùng processor đồng bộ hoặc flush rõ ràng để chẩn đoán. Trong production, giữ batching hợp lý và đảm bảo graceful shutdown có đủ thời gian flush.

Không dùng force flush cho mọi request; điều đó có thể làm tăng latency và tải exporter.

## 7. Kiểm tra network, DNS, TLS và authentication

### 7.1. Xác minh endpoint từ đúng nơi chạy ứng dụng

Nếu ứng dụng chạy trong container/Kubernetes, thử kết nối từ cùng network namespace hoặc pod debug được phê duyệt. Laptop truy cập được Collector không chứng minh container ứng dụng có route tới đó.

Kiểm tra:

- DNS resolve service name.
- Host/port đúng với receiver đang listen.
- Container/pod có egress route.
- NetworkPolicy/firewall/security group cho phép.
- Service port và targetPort ánh xạ đúng.
- Collector receiver bind vào interface có thể truy cập.
- Proxy/service mesh không chặn hoặc đổi protocol.

### 7.2. OTLP/gRPC và OTLP/HTTP

Sai transport có thể gây lỗi dù host/port mở:

- Client gRPC gọi endpoint HTTP.
- Client HTTP gửi tới gRPC port.
- URL thiếu hoặc sai /v1/traces.
- TLS được bật ở một phía nhưng phía kia dùng plaintext.
- Proxy chỉ hỗ trợ HTTP/1.1 trong khi gRPC cần HTTP/2.

Xác minh protocol, receiver config, exporter config và TLS handshake. Không kiểm tra port mở rồi kết luận giao thức hoạt động.

### 7.3. TLS và certificate

Lỗi TLS thường đến từ:

- CA chưa được trust.
- Certificate hết hạn.
- SAN/hostname không khớp.
- SNI sai.
- Collector yêu cầu mTLS nhưng client không gửi certificate.
- Reverse proxy terminate TLS ở lớp khác.

Không tắt certificate verification trên production để “làm cho trace chạy”. Cài đúng CA/client certificate và xác minh hostname.

### 7.4. Authentication và tenant routing

Backend có thể yêu cầu bearer token, API key hoặc tenant header. Nếu thiếu hoặc sai, exporter có thể nhận 401/403. Một số backend trả 200/202 cho ingest nhưng route dữ liệu vào tenant/project khác.

Kiểm tra:

- Credential có còn hạn?
- Header được exporter hỗ trợ và gửi đúng?
- Collector có forward auth header/resource tenant không?
- Backend project/tenant có đúng?
- Secret được mount và đọc bởi đúng process user?

Không in token vào log hoặc chia sẻ trong incident ticket. Dùng secret manager/mounted secret file và chỉ log error category/status code.

## 8. OpenTelemetry Collector: receiver, processor và exporter

Nếu ứng dụng export OTLP tới Collector, cần xác minh Collector thực sự nhận traces và pipeline traces đã nối đủ thành phần.

### 8.1. Ví dụ Collector OTLP pipeline

~~~yaml
receivers:
  otlp:
    protocols:
      grpc:
        endpoint: 0.0.0.0:4317
      http:
        endpoint: 0.0.0.0:4318

processors:
  memory_limiter:
    check_interval: 1s
    limit_mib: 512
  batch:

exporters:
  otlp:
    endpoint: tracing-backend:4317
    tls:
      insecure: true

service:
  pipelines:
    traces:
      receivers: [otlp]
      processors: [memory_limiter, batch]
      exporters: [otlp]
~~~

Đây là cấu hình lab minh họa; insecure: true chỉ phù hợp môi trường không TLS được cô lập, không dùng làm cấu hình production. Production cần TLS, CA và authentication phù hợp backend. Tên exporter và schema có thể khác theo Collector distribution/version.

### 8.2. Kiểm tra pipeline wiring

Khai báo receiver không đủ; nó phải được tham chiếu trong service.pipelines.traces. Tương tự:

- Pipeline type phải là traces, không phải metrics.
- Processor phải được nối vào đúng pipeline.
- Exporter phải có trong pipeline và được khởi tạo.
- Exporter endpoint/TLS/auth phải đúng.
- Collector config phải được load và reload/restart đúng cách.

Một exporter được khai báo nhưng không dùng trong pipeline sẽ không nhận span.

### 8.3. Tail sampling processor

Nếu dùng tail sampling, pipeline có thể gồm:

~~~yaml
processors:
  tail_sampling:
    decision_wait: 10s
    num_traces: 50000
    policies:
      - name: keep-errors
        type: status_code
        status_code:
          status_codes: [ERROR]

service:
  pipelines:
    traces:
      receivers: [otlp]
      processors: [memory_limiter, tail_sampling, batch]
      exporters: [otlp]
~~~

Ví dụ rút gọn; tail sampling cần cấu hình capacity, decision wait, expected trace volume và routing sao cho các span cùng Trace ID đến cùng processor instance. Nếu các span của một trace bị phân tán giữa nhiều Collector không phối hợp, quyết định tail sampling có thể thiếu dữ liệu.

Nếu không thấy trace bình thường nhưng trace lỗi xuất hiện, policy tail sampling có thể đang chủ ý giữ error traces và loại trace khác. Kiểm tra policy trước khi kết luận exporter bị lỗi.

### 8.4. Collector self-observability

Quan sát Collector qua:

- Receiver accepted/refused spans.
- Processor dropped spans.
- Exporter sent/failed spans.
- Exporter queue size/capacity.
- Retry count và send failure.
- Memory limiter refused data.
- Collector logs và health status.

Tên metric nội bộ tùy Collector version/distribution. Khám phá telemetry endpoint và logs của chính Collector; không sao chép tên metric từ một phiên bản khác mà chưa xác minh.

## 9. Context propagation và span con bị mất

Một root trace xuất hiện nhưng thiếu span VectorStore/ChatModel có thể do context propagation.

### 9.1. Đồng bộ so với bất đồng bộ

Trong cùng thread, Observation scope thường được truyền qua context hiện tại. Khi chuyển sang:

- Executor/ThreadPoolTaskExecutor.
- CompletableFuture.
- Reactor scheduler.
- @Async.
- Message queue hoặc event bus.
- HTTP/gRPC call sang service khác.

context có thể không tự truyền nếu instrumentation/context-propagation chưa được cấu hình.

### 9.2. Triệu chứng

| Triệu chứng | Nguyên nhân cần kiểm tra |
|---|---|
| Root span có, child span không có | Child code path không instrument hoặc bị sampling/filter |
| Child span có Trace ID khác | Context propagation bị mất hoặc tạo root mới |
| Chỉ mất span trong async branch | Executor/reactive context không được truyền |
| HTTP downstream tạo trace mới | Không inject/extract trace context header |
| Span bắt đầu nhưng duration bất thường | Scope kết thúc quá sớm hoặc async task sống ngoài scope |

### 9.3. Dùng context propagation đúng cách

Với Spring Boot/Micrometer, kiểm tra context propagation support và executor instrumentation theo version. Nếu dùng TaskExecutor, có thể cấu hình executor để propagate context bằng cơ chế được Spring Boot/Micrometer cung cấp trong stack hiện tại. Không tự copy Trace ID thành một tag rồi xem đó là distributed tracing; cần truyền trace context chuẩn để tạo quan hệ parent-child.

Với HTTP, kiểm tra W3C Trace Context `traceparent` và `tracestate`, hoặc B3 nếu hệ thống chủ động dùng B3. Các service phải thống nhất propagator và header policy.

Không ghi raw baggage chứa user/tenant data nếu không có chính sách rõ ràng. Baggage được truyền qua nhiều service và có thể làm lộ dữ liệu ở downstream logs/traces.

### 9.4. Ví dụ Observation lồng nhau

~~~java
import java.util.List;
import java.util.Objects;

import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import org.springframework.ai.document.Document;
import org.springframework.ai.vectorstore.SearchRequest;
import org.springframework.ai.vectorstore.VectorStore;
import org.springframework.stereotype.Service;

@Service
public final class ObservedRetrievalService {
    private final VectorStore vectorStore;
    private final ObservationRegistry observations;

    public ObservedRetrievalService(
            VectorStore vectorStore,
            ObservationRegistry observations) {
        this.vectorStore = Objects.requireNonNull(vectorStore);
        this.observations = Objects.requireNonNull(observations);
    }

    public List<Document> retrieve(String question) {
        return Observation.createNotStarted(
                        "app.rag.retrieve", observations)
                .lowCardinalityKeyValue("store.role", "policy-search")
                .observe(() -> {
                    SearchRequest request = SearchRequest.builder()
                            .query(question)
                            .topK(5)
                            .build();

                    return Observation.createNotStarted(
                                    "app.rag.vector_search", observations)
                            .lowCardinalityKeyValue(
                                    "store.role", "policy-search")
                            .observe(() ->
                                    vectorStore.similaritySearch(request));
                });
    }
}
~~~

Đoạn code minh họa hai Observation lồng nhau; span con thực sự xuất hiện khi tracing handler và context hiện tại hoạt động. Spring AI adapter có thể đã tạo observation riêng, vì vậy không cần bọc mọi method chỉ để tạo thêm span trùng lặp. Trước khi thêm instrumentation, kiểm tra spans hiện có và giữ tên/attributes theo mục đích rõ ràng.

Không đưa câu hỏi hoặc nội dung tài liệu vào span attributes. Chỉ dùng role/config/outcome đã được kiểm soát.

## 10. Exporter queue, timeout và graceful shutdown

### 10.1. Vì sao span có thể chưa được gửi?

Batch exporter có thể giữ span trong queue chờ:

- Đủ batch size.
- Đến scheduled delay.
- Force flush hoặc shutdown.

Trace không thấy ngay sau request có thể do export batching, nhưng nếu chờ lâu vẫn không xuất hiện thì cần kiểm tra queue và exporter errors.

### 10.2. Các chỉ số cần quan sát

- Spans started/ended/recorded.
- Spans sampled/dropped.
- Export requests và export failures.
- Queue size/capacity.
- Export duration.
- Retry count/backoff.
- Collector accepted/refused/sent/failed spans.
- Shutdown flush duration/timeouts.

Tên metric phụ thuộc SDK/exporter. Nếu không có metric, bật diagnostic logs có giới hạn hoặc dùng test exporter trong môi trường thử nghiệm.

### 10.3. Process bị dừng đột ngột

Khi container bị kill -9, OOM hoặc shutdown timeout quá ngắn, batch queue có thể chưa flush. Hãy:

- Dùng graceful shutdown và cho process đủ thời gian kết thúc.
- Cấu hình termination grace period lớn hơn thời gian flush dự kiến.
- Theo dõi OOM/restart và exporter queue.
- Không gọi force flush sau mọi request.
- Không tăng queue vô hạn; queue lớn có thể tăng memory pressure.

### 10.4. Export timeout

Nếu exporter timeout:

- Kiểm tra backend/Collector response time.
- Kiểm tra DNS/network/TLS/auth.
- Kiểm tra batch size và payload size.
- Kiểm tra exporter timeout/retry/backoff.
- Kiểm tra backend rate limit và Collector queue.

Tăng timeout đơn thuần có thể làm thread/queue giữ tài nguyên lâu hơn. Trước hết xác định backend chậm, network lỗi hay exporter đang gửi sai protocol.

## 11. Bảo mật khi chẩn đoán trace

Trace có thể chứa prompt, query, document content, tool arguments, exception và identifiers. Trong lúc điều tra:

- Không bật capture raw prompt/query/document chỉ để tìm trace.
- Không log authorization header, API key hoặc exporter token.
- Dùng trace ID ngẫu nhiên/opaque cho correlation; không dùng user ID làm metric label.
- Giữ low-cardinality attributes như service, operation, store role và environment.
- Giới hạn quyền xem trace backend và retention.
- Redact trước khi export ra hệ thống ngoài vùng tin cậy.
- Dùng canary fixture tổng hợp khi test export.
- Không paste trace payload có PII/secret vào ticket hoặc chat.

Sampling không phải biện pháp bảo mật. Trace được giữ vẫn phải qua redaction, ACL, encryption và retention policy.

## 12. Ma trận chẩn đoán nhanh

| Triệu chứng | Nguyên nhân có thể | Bằng chứng cần kiểm tra |
|---|---|---|
| Có metrics nhưng không có trace | Thiếu tracing bridge/handler hoặc sampler drop | Dependency tree, ObservationRegistry handlers, sampling |
| Observation probe có nhưng exporter không nhận | Không có tracing handler/exporter hoặc sampler drop | SDK span processor, sampled state, exporter logs |
| Trace chỉ xuất hiện khoảng 10% | Ratio/head sampling | Sampling probability và parent sampled flag |
| Chỉ trace lỗi xuất hiện | Tail sampling policy giữ error | Collector tail_sampling policies |
| Span có trong app nhưng Collector không nhận | Exporter endpoint/network/TLS/auth | Export error, Collector receiver counters/logs |
| Collector nhận span nhưng backend không có | Processor drop hoặc exporter failure | Pipeline wiring, processor/exporter metrics |
| Root span có, child span mất | Instrumentation thiếu hoặc context propagation lỗi | Trace ID/parent ID, executor/reactive context |
| Trace ID đổi sau async boundary | Context bị mất hoặc tạo root mới | Executor/context propagation instrumentation |
| Trace xuất hiện trễ | Batch queue/scheduled delay | Exporter queue, flush và export duration |
| Trace mất khi restart | Shutdown không flush hoặc process bị kill | Restart/OOM logs, shutdown timeout |
| Export trả 401/403 | Credential/tenant header không hợp lệ | Auth config, secret mount, backend response |
| Export trả 404 | Sai endpoint/path hoặc protocol | OTLP path, gRPC/HTTP receiver |
| Export trả 200 nhưng UI không thấy | Sai tenant/project/time range hoặc indexing delay | Backend ingest/query logs và datasource |
| Chỉ thiếu một số service | Sampling/context propagation/dependency không đồng nhất | Version, sampler, headers, service config |

## 13. Runbook điều tra theo thứ tự

1. **Tạo request fixture:** chạy một request RAG có thể nhận diện bằng timestamp/opaque run reference, không dùng dữ liệu thật.
2. **Xác minh Observation:** kiểm tra instrumentation có phát Observation quanh service/VectorStore/ChatModel không.
3. **Xác minh tracing bridge:** kiểm tra runtime dependencies và tracing handler trong ObservationRegistry.
4. **Kiểm tra sampler:** xác nhận probability, parent-based decision và policy tail sampling.
5. **Kiểm tra span recording:** xác minh span được tạo/record trước exporter.
6. **Kiểm tra exporter:** xác nhận OTLP/Zipkin implementation, endpoint, protocol và batch processor.
7. **Kiểm tra network:** từ đúng container/pod, xác minh DNS, port, TLS, auth và route tới Collector/backend.
8. **Kiểm tra Collector:** receiver accepted, processor dropped, exporter failed, queue và pipeline wiring.
9. **Kiểm tra context propagation:** so trace ID/parent ID giữa root, async child và downstream service.
10. **Kiểm tra backend:** ingest status, tenant/project, indexing delay và query API.
11. **Kiểm tra UI:** service name, time range, environment, trace ID và datasource.
12. **Thêm regression test:** giữ một integration test chứng minh span từ request fixture đến test collector/backend.

### 13.1. Cách cô lập nhanh

Trong local/test có thể tạm thời:

- Tăng sampling probability lên 1.0 cho một test run.
- Dùng Collector debug exporter hoặc test exporter.
- Tắt tail-sampling policy trong môi trường test.
- Dùng request fixture đơn giản, đồng bộ trước rồi mới thử async.
- Export tới endpoint local đã biết hoạt động.

Nếu trace xuất hiện khi tăng sampling lên 1.0, điều tra sampling policy. Nếu span được tạo nhưng test exporter không nhận, điều tra tracing handler/processor. Nếu test exporter nhận nhưng Collector không nhận, điều tra exporter/network. Sau khi xác định, khôi phục sampling và cấu hình production policy.

Không để sampling 100% hoặc debug exporter verbose tồn tại vô thời hạn trên production.

## 14. Kiểm thử tracing

### 14.1. Unit test Observation lifecycle

Một test handler tùy chỉnh có thể xác minh Observation được bắt đầu/kết thúc:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.concurrent.atomic.AtomicInteger;
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationHandler;
import io.micrometer.observation.ObservationRegistry;
import org.junit.jupiter.api.Test;

class ObservationLifecycleTest {
    @Test
    void observationIsStartedAndStopped() {
        var started = new AtomicInteger();
        var stopped = new AtomicInteger();
        var registry = ObservationRegistry.create();

        registry.observationConfig().observationHandler(
                new ObservationHandler<Observation.Context>() {
                    @Override
                    public boolean supportsContext(
                            Observation.Context context) {
                        return true;
                    }

                    @Override
                    public void onStart(Observation.Context context) {
                        started.incrementAndGet();
                    }

                    @Override
                    public void onStop(Observation.Context context) {
                        stopped.incrementAndGet();
                    }
                });

        Observation.createNotStarted("app.trace.test", registry)
                .observe(() -> {
                });

        assertThat(started.get()).isEqualTo(1);
        assertThat(stopped.get()).isEqualTo(1);
    }
}
~~~

Test này chỉ chứng minh Observation lifecycle. Nó không chứng minh tracing bridge tạo span, sampler giữ span hay exporter gửi dữ liệu.

### 14.2. Integration test với tracing exporter

Một integration test nên:

1. Khởi động Spring Boot context với tracing bridge và exporter giống cấu hình mục tiêu.
2. Dùng test exporter hoặc Collector test endpoint để nhận spans.
3. Gọi một endpoint RAG fixture tạo root Observation và VectorStore child operation.
4. Chờ batch export hoàn tất hoặc thực hiện flush theo API/test harness của version đang dùng.
5. Xác minh có trace ID, span name và parent-child relationship mong đợi.
6. Xác minh error/status khi fixture cố tình tạo lỗi.
7. Xác minh raw query, prompt và document content không bị export ngoài policy.
8. Kiểm tra async branch giữ đúng trace context.

Đừng chỉ assert HTTP request trả 200. Ứng dụng có thể trả kết quả thành công trong khi tracing pipeline không hoạt động.

### 14.3. Smoke test Collector

Trong môi trường integration, gửi một span canary không nhạy cảm tới Collector và xác minh:

- Receiver accepted span.
- Processor không drop ngoài policy.
- Exporter gửi thành công.
- Backend query tìm thấy trace ID.

Canary trace nên có service/operation name hữu hạn, không chứa user/tenant ID, prompt hay document content.

## 15. Những sai lầm thường gặp

1. **Cho rằng có Observation là chắc chắn có trace.** Cần tracing handler/bridge.
2. **Cho rằng có metrics nghĩa là tracing đã hoạt động.** Meter handler và tracing handler là hai đường xử lý khác nhau.
3. **Quên sampling probability.** Trace có thể bị drop có chủ ý trước exporter.
4. **Bật 100% sampling lâu dài trên production.** Có thể tăng tải và chi phí lớn.
5. **Mong tail sampler khôi phục trace đã bị SDK drop.** Collector chưa từng nhận span đó.
6. **Chỉ kiểm tra exporter URL.** Sai protocol, TLS, auth, path hoặc network vẫn làm export thất bại.
7. **Khai báo Collector receiver nhưng quên pipeline traces.** Receiver không được nối sẽ không xử lý trace.
8. **Cấu hình tail sampling trên nhiều Collector không có trace affinity.** Span của cùng trace có thể bị chia sang nhiều nơi.
9. **Bỏ qua batch queue và shutdown flush.** Process có thể dừng trước khi gửi span.
10. **Tạo ObservationRegistry tùy chỉnh không có tracing handler.** Auto-configuration có thể đã back off.
11. **Mất context qua executor/reactive boundary.** Span con có thể thành trace độc lập hoặc biến mất.
12. **Thêm trace ID thành metric label.** Tạo cardinality rất cao.
13. **Coi HTTP 200 từ Collector là backend đã index.** Ingest và search là các bước khác nhau.
14. **Bật raw prompt/document capture để debug.** Có thể làm lộ dữ liệu nhạy cảm.
15. **Chỉ test Observation lifecycle.** Cần integration test cho sampler, exporter và Collector.

## 16. Bài thực hành tự luyện

**Bối cảnh:** Ứng dụng Spring AI dùng Micrometer Observation và OTLP. Metrics VectorStore có đầy đủ nhưng trace chỉ xuất hiện không đều; một số trace có root span nhưng thiếu VectorStore child span.

Yêu cầu:

1. Kiểm tra dependency tree để xác nhận Actuator, Micrometer Tracing bridge và OTLP exporter.
2. Xác nhận ObservationRegistry do Spring Boot quản lý và có tracing handler.
3. Tạo một Observation probe và một request RAG fixture.
4. Đặt sampling probability = 1.0 trong test ngắn và so sánh kết quả với cấu hình mặc định.
5. Kiểm tra parent sampled flag trong trace context nhận từ upstream.
6. Xác minh OTLP protocol, port, endpoint path và Collector receiver.
7. Dùng Collector debug/test exporter để xem span có tới Collector không.
8. Kiểm tra tail_sampling processor và pipeline traces nếu có.
9. Kiểm tra exporter queue, retries, TLS, auth và graceful shutdown.
10. Chạy cùng request qua synchronous và async executor; so trace ID/parent ID.
11. Kiểm tra backend ingest và query API trước khi điều tra dashboard.
12. Viết integration test xác minh root/child spans và privacy policy.

**Câu hỏi tự kiểm tra:**

- Observation khác span ở điểm nào?
- Vì sao có metrics nhưng không có trace?
- Head sampling và tail sampling quyết định ở thời điểm nào?
- Vì sao tail sampling không thể phục hồi span đã bị SDK drop?
- Parent-based sampler ảnh hưởng downstream service ra sao?
- OTLP/gRPC và OTLP/HTTP khác nhau thế nào về port/protocol?
- Vì sao Collector receiver cần được nối vào pipeline traces?
- Batch processor có thể làm trace xuất hiện trễ hoặc mất khi shutdown thế nào?
- Mất context qua executor gây triệu chứng gì?
- Làm thế nào phân biệt exporter gửi thành công với backend đã index trace?

## 17. Checklist triển khai

- [ ] Có Spring AI instrumentation/Observation cho code path cần quan sát.
- [ ] Có Micrometer Tracing bridge hoặc tracing SDK phù hợp ở runtime.
- [ ] ObservationRegistry đang dùng có tracing handler.
- [ ] Không có custom registry làm mất handler hoặc tạo nhiều registry tách biệt.
- [ ] Sampling probability/parent-based policy đã được xác minh.
- [ ] Head sampling và tail sampling được phân biệt rõ; không kỳ vọng tail sampler phục hồi span đã drop.
- [ ] Exporter đúng protocol, endpoint, port và path.
- [ ] TLS, CA, hostname, authentication và tenant routing hoạt động.
- [ ] Collector receiver, processors và exporter được nối trong pipeline traces.
- [ ] Tail sampling có capacity, decision wait và trace affinity phù hợp nếu được dùng.
- [ ] Export queue, retries, failures và shutdown flush được theo dõi.
- [ ] Async executor/reactive/HTTP boundaries có context propagation phù hợp.
- [ ] Backend ingest và search API được kiểm tra trước dashboard.
- [ ] Trace attributes tuân thủ allowlist/redaction; không xuất raw prompt/document/secret.
- [ ] Có test Observation lifecycle và integration test exporter/Collector.
- [ ] Có canary trace smoke test sau khi nâng Spring Boot, Spring AI, Micrometer hoặc Collector.

## Tổng kết

Không thấy trace có thể do Observation chưa được phát, tracing bridge/handler thiếu, sampler chủ động drop, context bị mất, exporter không gửi được hoặc backend chưa lưu/index dữ liệu. Hãy phân biệt từng trạng thái: Observation, span creation, sampling, export, Collector ingestion và backend search. Metrics vẫn có thể hoạt động khi tracing handler không tồn tại; trace có thể được tạo nhưng bị head sampler loại trước exporter.

Quy trình điều tra hiệu quả bắt đầu bằng một request fixture và sampling 100% trong test ngắn, sau đó kiểm tra registry/handler, dependency, exporter protocol, endpoint, network/TLS/auth, Collector pipeline và backend query. Nếu chỉ mất span con, tập trung vào instrumentation và context propagation qua async/service boundaries. Khi đã xác định nguyên nhân, khôi phục sampling policy phù hợp production, giữ privacy controls và bổ sung integration test để phát hiện hồi quy.

## Tài liệu tham khảo

- [Spring AI — Observability](https://docs.spring.io/spring-ai/reference/observability/): Observation của ChatClient, ChatModel, EmbeddingModel và VectorStore.
- [Spring Boot — Tracing](https://docs.spring.io/spring-boot/reference/actuator/tracing.html): Micrometer Tracing, sampling và exporter integration.
- [Micrometer — Observation](https://docs.micrometer.io/micrometer/reference/observation.html): ObservationRegistry, handlers và context.
- [Micrometer Tracing](https://docs.micrometer.io/tracing/reference/): tracing bridges, spans, sampling và propagation.
- [OpenTelemetry — Sampling](https://opentelemetry.io/docs/concepts/sampling/): head sampling, parent-based sampling và sampling decisions.
- [OpenTelemetry — Collector](https://opentelemetry.io/docs/collector/): receivers, processors, exporters và pipelines.
- [OpenTelemetry — OTLP](https://opentelemetry.io/docs/specs/otlp/): OTLP protocol, gRPC và HTTP transport.
- [OpenTelemetry — Context Propagation](https://opentelemetry.io/docs/concepts/context-propagation/): trace context và propagation giữa service.
- [W3C Trace Context](https://www.w3.org/TR/trace-context/): traceparent và tracestate.
- [Zipkin](https://zipkin.io/): Zipkin tracing backend và ingest API.
