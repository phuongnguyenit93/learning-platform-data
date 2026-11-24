# Tương thích tracer và Boot version

Trong mô-đun **SPRING_BOOT_OBSERVABILITY**, Spring Boot dùng **Micrometer Observation** làm điểm tích hợp cho metrics và tracing. **Micrometer Tracing** cung cấp facade để ứng dụng và framework làm việc với nhiều tracer implementation. Tracer thực tế có thể là OpenTelemetry hoặc OpenZipkin Brave; exporter lại quyết định spans được gửi tới backend nào, chẳng hạn OTLP Collector hay Zipkin.

Tương thích giữa tracer và Spring Boot version không chỉ là chọn một dependency có thể compile. Phiên bản Boot quyết định bộ dependency được quản lý, auto-configuration nào có sẵn, property namespace nào được bind và cách OpenTelemetry SDK được kết nối với Micrometer. Nếu trộn bridge, SDK, exporter hoặc starter từ các thế hệ khác nhau, ứng dụng có thể khởi động nhưng không tạo spans, export sai endpoint, thiếu correlation hoặc có nhiều tracing pipelines cạnh tranh.

Bài này giúp bạn chọn tracer phù hợp với Spring Boot version, hiểu khác biệt giữa Boot 3.x và 4.x, quản lý dependency bằng BOM, cấu hình exporter tương thích và kiểm chứng toàn bộ đường đi từ Observation tới trace backend.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt Micrometer Observation, Micrometer Tracing, tracer implementation và exporter.
2. Nhận diện hai tracer phổ biến được Spring Boot hỗ trợ auto-configuration: OpenTelemetry và Brave.
3. Chọn dependency phù hợp với Spring Boot 3.x hoặc 4.x.
4. Hiểu vì sao không nên đặt đồng thời hai Micrometer tracing bridges trên classpath.
5. Phân biệt thay đổi property namespace và starter giữa các phiên bản Boot.
6. Quản lý phiên bản qua Spring Boot dependency management/BOM.
7. Cấu hình sampling, propagation và exporter theo tracer implementation.
8. Tránh tạo nhiều SDK/provider hoặc instrumentation cạnh tranh.
9. Kiểm tra trace context qua HTTP client và server.
10. Xây dựng quy trình nâng cấp Boot/tracer có kiểm thử và rollback.

## 2. Các lớp cần phân biệt

| Thành phần | Vai trò | Ví dụ |
| --- | --- | --- |
| Spring Boot Actuator | Auto-configuration và dependency management cho observability/tracing. | Starter Actuator và tracing auto-configuration. |
| Micrometer Observation | API mô tả một operation để nhiều handler xử lý. | HTTP server/client Observation. |
| Micrometer Tracing | Facade cho tracer implementation. | Tracer, Span, Baggage APIs. |
| Tracing bridge | Chuyển Micrometer Tracing API sang tracer cụ thể. | micrometer-tracing-bridge-otel hoặc micrometer-tracing-bridge-brave. |
| Tracer implementation | Tạo span/context và thực hiện propagation. | OpenTelemetry SDK hoặc Brave. |
| Reporter/exporter | Gửi spans tới backend. | OTLP exporter hoặc Zipkin reporter. |
| Collector/backend | Nhận, xử lý, lưu và truy vấn traces. | OpenTelemetry Collector, Zipkin. |

Luồng tổng quát:

~~~mermaid
flowchart LR
    App["Spring Boot application"]
    App --> Obs["Micrometer Observation"]
    Obs --> Trace["Micrometer Tracing handler"]
    Trace --> Bridge["One tracing bridge"]
    Bridge --> Impl["OpenTelemetry SDK or Brave"]
    Impl --> Export["OTLP exporter or Zipkin reporter"]
    Export --> Backend["Collector / trace backend"]
~~~

Observation là abstraction phía ứng dụng/framework. Bridge kết nối abstraction với tracer. Exporter/reporter gửi dữ liệu đi. Backend không quyết định bridge nào được dùng; backend chỉ cần nhận protocol tương thích.

## 3. Các tracer được Spring Boot hỗ trợ

Spring Boot Actuator cung cấp dependency management và auto-configuration cho Micrometer Tracing. Các lựa chọn phổ biến được Spring Boot hỗ trợ gồm:

| Tracer | Backend/export format phổ biến | Bridge/dependency chính |
| --- | --- | --- |
| OpenTelemetry | OTLP | OpenTelemetry tracing integration và OTLP exporter. |
| OpenZipkin Brave | Zipkin | Brave tracing integration và Zipkin reporter. |

Micrometer Tracing cũng có thể kết hợp các reporter/backend khác tùy version và dependencies. Tuy nhiên, khi dùng auto-configuration, hãy theo đúng các tổ hợp được tài liệu Spring Boot của version đang chạy mô tả.

### Chỉ chọn một bridge

Không đặt đồng thời cả hai dependency:
- micrometer-tracing-bridge-otel
- micrometer-tracing-bridge-brave

Một ứng dụng thường chỉ nên có một tracer implementation chính. Hai bridge cùng có mặt có thể khiến auto-configuration không xác định được tracer mong muốn, tạo bean ambiguity hoặc tạo pipeline không nhất quán. Nếu cần gửi dữ liệu tới nhiều backend, hãy cân nhắc exporter/collector fan-out từ một tracer thay vì tạo hai Micrometer bridges.

## 4. Tương thích theo Spring Boot version

Các dòng Spring Boot đã thay đổi cách đóng gói tracing integration và property namespace. Bảng sau là định hướng; dependency chính xác phải lấy từ reference documentation của minor version và dependency management của dự án.

| Spring Boot version | OpenTelemetry tracing | Brave tracing | Cấu hình export cần kiểm tra |
| --- | --- | --- | --- |
| 3.0–3.1 | Micrometer OTel bridge và exporter theo backend. | Micrometer Brave bridge và reporter theo backend. | Các namespace theo backend như management.otlp.tracing, management.zipkin.tracing hoặc management.wavefront. |
| 3.2–3.5 | Micrometer OTel bridge + exporter OTLP/Zipkin/Wavefront theo version. | Micrometer Brave bridge + Zipkin/Wavefront reporter theo version. | Dùng đúng management.otlp.tracing hoặc management.zipkin.tracing / management.wavefront. |
| 4.x | Boot có các module/starter tracing integration riêng theo tracer. | Boot có integration riêng cho Brave/Zipkin. | Các property tracing export được tổ chức dưới management.tracing.export.*; OTLP có namespace OpenTelemetry tương ứng ở version hỗ trợ. |

Đây không phải bảng thay thế dependency metadata. Spring Boot 4.x có thay đổi artifact names và cấu trúc modules; không copy nguyên dependencies từ bài hướng dẫn Boot 3.5 sang Boot 4.x. Ngược lại, property namespace của Boot 4.x không nên được áp dụng ngược cho Boot 3.x.

Tài liệu chính thức cần đối chiếu:
- [Spring Boot 3.5 Tracing](https://docs.spring.io/spring-boot/3.5/reference/actuator/tracing.html)
- [Spring Boot 4.0 Tracing](https://docs.spring.io/spring-boot/4.0/reference/actuator/tracing.html)
- [Spring Boot 4.1 Tracing](https://docs.spring.io/spring-boot/4.1/reference/actuator/tracing.html)
- [Spring Boot current Tracing](https://docs.spring.io/spring-boot/reference/actuator/tracing.html)
- [Micrometer Tracing Reference](https://docs.micrometer.io/tracing/reference/)

## 5. Chọn OpenTelemetry với OTLP

OpenTelemetry phù hợp khi hệ thống đã dùng OpenTelemetry Collector hoặc backend nhận OTLP. Với Spring Boot 3.x, cách tích hợp thường dùng Micrometer OTel bridge và OTLP exporter; với các bản Boot 4.x, ưu tiên starter/module do Boot quản lý nếu version reference hướng dẫn.

### Spring Boot 3.x — dependency minh họa

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    implementation 'io.micrometer:micrometer-tracing-bridge-otel'
    implementation 'io.opentelemetry:opentelemetry-exporter-otlp'
}
~~~

Đoạn trên minh họa cách khai báo thường gặp trong Boot 3.x. Không chỉ định version riêng cho từng dependency khi Spring Boot dependency management đã quản lý phiên bản tương thích. Kiểm tra version reference nếu dùng 3.0/3.1 cũ vì support matrix và exporter modules có thể khác.

### Spring Boot 4.x — dùng integration do Boot quản lý

Các dòng Boot 4.x có module/starter tracing integration riêng. Tài liệu current mô tả OpenTelemetry với OTLP bằng starter:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-opentelemetry'
}
~~~

Tên artifact và cấu trúc modules phải khớp minor version cụ thể. Không thêm bridge/exporter thủ công trùng với starter nếu starter đã kéo chúng và auto-configure pipeline. Nếu cần customization nâng cao, dùng builder customizers được Spring Boot cung cấp cho exporter thay vì tạo một SDK cạnh tranh.

### Cấu hình OTLP

Với Boot 3.x, property thường dùng trong các version tương ứng:

~~~yaml
management:
  tracing:
    sampling:
      probability: 0.1
  otlp:
    tracing:
      endpoint: http://otel-collector:4318/v1/traces
~~~

Với các version Boot 4.x có OpenTelemetry tracing export properties:

~~~yaml
management:
  tracing:
    sampling:
      probability: 0.1
  opentelemetry:
    tracing:
      export:
        otlp:
          endpoint: http://otel-collector:4318
          transport: http
~~~

Hai ví dụ này thuộc các thế hệ property khác nhau. Xác nhận endpoint semantics và transport theo version; có version dùng URL đầy đủ với signal path, có version dùng common/base endpoint và tự xử lý path. Không copy property từ Boot 4 sang Boot 3 hoặc ngược lại.

## 6. Chọn Brave với Zipkin

Brave là tracer implementation khác được Micrometer Tracing hỗ trợ. Đây là lựa chọn phù hợp khi hệ thống hiện hữu dùng Zipkin ecosystem và muốn tiếp tục reporter/protocol tương ứng.

### Spring Boot 3.x — dependency minh họa

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    implementation 'io.micrometer:micrometer-tracing-bridge-brave'
    implementation 'io.zipkin.reporter2:zipkin-reporter-brave'
}
~~~

### Spring Boot 4.x — integration do Boot quản lý

Ở các bản Boot 4.x, kiểm tra starter/module Brave và Zipkin đúng version thay vì suy ra artifact name từ Boot 3.x. Tài liệu Spring Boot current vẫn liệt kê OpenZipkin Brave với Zipkin là một tracer combination được hỗ trợ.

### Cấu hình Zipkin

Trong Boot 3.x, property phổ biến:

~~~yaml
management:
  tracing:
    sampling:
      probability: 0.1
  zipkin:
    tracing:
      endpoint: http://zipkin:9411/api/v2/spans
~~~

Trong các version Boot 4.x, export properties được tổ chức theo cấu trúc tracing export tương ứng của version. Hãy đọc reference của chính version đó trước khi di chuyển cấu hình.

Không cấu hình Zipkin endpoint dưới OTLP namespace. Zipkin reporter gửi theo Zipkin protocol; OTLP exporter gửi theo OTLP. Một backend chỉ hỗ trợ một protocol không thể nhận payload của protocol khác chỉ bằng cách đổi URL.

## 7. Version alignment bằng BOM và dependency management

Spring Boot dependency management được thiết kế để chọn các phiên bản tương thích giữa Spring Framework, Micrometer, Micrometer Tracing và OpenTelemetry libraries. Khi dùng Boot plugin/parent/BOM:

- Không đặt version riêng cho từng Micrometer artifact trừ khi có lý do và đã kiểm thử.
- Không ép một OpenTelemetry SDK version mới hơn vào một starter đang quản lý phiên bản khác mà không kiểm tra binary compatibility.
- Tránh kéo hai bridge cùng lúc qua dependency bắc cầu.
- Kiểm tra dependency tree khi có duplicate SDK, exporter hoặc reporter.
- Khi nâng Boot, nâng đồng bộ plugin/parent/BOM và kiểm thử tracing pipeline.

Gradle ví dụ:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '4.1.0'
    id 'io.spring.dependency-management' version '1.1.7'
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    implementation 'org.springframework.boot:spring-boot-starter-opentelemetry'
}
~~~

Version trong ví dụ chỉ minh họa một bộ plugin; hãy dùng phiên bản Boot đã được dự án phê duyệt và plugin tương thích. Với Gradle plugin quản lý dependency của Spring Boot, không cần thêm dependency-management plugin trong mọi cấu hình; cách khai báo phụ thuộc build convention của dự án.

Maven có thể dùng spring-boot-starter-parent hoặc import spring-boot-dependencies BOM để quản lý version. Không trộn parent/BOM của một Boot version với plugin và starter của Boot version khác.

## 8. Kiểm tra dependency tree

Khi có vấn đề tương thích, trước tiên kiểm tra dependency graph:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Lọc các artifact quan trọng:
- micrometer-tracing
- micrometer-tracing-bridge-otel
- micrometer-tracing-bridge-brave
- opentelemetry-api
- opentelemetry-sdk
- opentelemetry-exporter-otlp
- brave
- zipkin-reporter

Maven:

~~~bash
mvn dependency:tree
~~~

Cần xác nhận:
1. Chỉ có một Micrometer tracing bridge.
2. Micrometer Tracing version nằm trong dải được Boot quản lý.
3. OpenTelemetry API/SDK/exporter không bị ép thành các version không tương thích.
4. Reporter tương ứng với backend đã chọn.
5. Không có Java agent hoặc starter khác vô tình tạo thêm pipeline ngoài dự kiến.

Nếu dùng OpenTelemetry Java Agent, xác định rõ agent có tự instrument và export spans hay ứng dụng cũng tự tạo SDK/exporter. Tránh duplicate spans do cả agent và application instrumentation cùng đo một operation mà không có policy.

## 9. Sampling và propagation phụ thuộc tracer

Micrometer Tracing cung cấp facade chung, nhưng sampler và propagator có thể có cấu hình riêng theo tracer implementation.

Spring Boot mặc định sampling một tỷ lệ nhỏ request để tránh làm backend quá tải; property phổ biến là management.tracing.sampling.probability. Với OpenTelemetry, các version hỗ trợ còn có thể cho chọn sampler như always-on, always-off, trace-id-ratio hoặc parent-based variants qua property OpenTelemetry tracing sampler.

Với Brave, sampling configuration và propagation phải theo integration của Brave/Micrometer Tracing. Không giả định property sampler đặc thù OpenTelemetry áp dụng cho Brave.

### Propagation format

Các format thường gặp:
- W3C Trace Context: traceparent và tracestate.
- B3: single hoặc multi-header formats.
- Baggage: W3C Baggage hoặc cơ chế baggage tương ứng.

Các service cần thống nhất format hoặc cấu hình composite propagation phù hợp. Nếu một service chỉ đọc B3 trong khi service khác chỉ gửi W3C, trace có thể bị đứt dù cả hai đều có tracer hoạt động.

### Parent-based sampling

Khi dùng parent-based sampling, service con nên tuân theo sampling decision được propagate từ parent. Đây là yếu tố quan trọng để các spans trong cùng một distributed trace được giữ nhất quán. Không tạo sampler độc lập trên từng service nếu không hiểu ảnh hưởng đến trace completeness.

## 10. Tránh tạo nhiều tracing pipelines

Một lỗi phổ biến là đồng thời sử dụng:
- Spring Boot Micrometer Tracing auto-configuration.
- OpenTelemetry SDK tự tạo bằng code.
- OpenTelemetry Java Agent.
- Một bridge Micrometer thứ hai.
- Custom exporter hoặc reporter khác.

Khi nhiều thành phần cùng instrument và export, có thể xuất hiện duplicate spans, trace ID không liên kết, sampling decision khác nhau hoặc resource attributes không đồng nhất.

Trước khi thêm SDK/exporter:
1. Xác định OpenTelemetry/Tracer bean nào do Boot quản lý.
2. Kiểm tra agent có đang instrument HTTP/JDBC/Messaging không.
3. Kiểm tra client builder có auto instrumentation và trace propagation không.
4. Quyết định một pipeline chính cho mỗi span source.
5. Nếu cần nhiều backend, cân nhắc fan-out ở Collector thay vì instrument lại trong app.

Spring Boot khuyến nghị dùng Micrometer Observation hoặc Micrometer Tracing API cho ứng dụng thay vì gọi trực tiếp OpenTelemetry API ở mọi nơi. Điều này giúp giảm phụ thuộc trực tiếp vào một tracer implementation và thuận tiện hơn khi thay tracer.

## 11. Tương thích giữa client builders và tracer

Để tự động propagate traces qua network, dùng các builder được Spring Boot auto-configure như RestClient.Builder hoặc WebClient.Builder. Nếu tự tạo RestClient/WebClient mà không dùng builder đó, automatic trace propagation có thể không hoạt động.

Ví dụ:

~~~java
@Service
class InventoryClient {

    private final RestClient client;

    InventoryClient(RestClient.Builder builder) {
        this.client = builder
                .baseUrl("http://inventory-service")
                .build();
    }
}
~~~

Dù chọn OpenTelemetry hay Brave, builder đã được Boot cấu hình sẽ kết nối với tracing integration phù hợp. Với custom HTTP clients, cần cài interceptor/instrumentation tương ứng và kiểm tra context propagation.

Không chỉ kiểm tra span được tạo trong service gọi; hãy xác minh traceparent/B3 header thực sự được gửi và server downstream tạo child span cùng trace ID.

## 12. Resource và service identity

Resource attributes như service.name, service.version và deployment.environment cần nhất quán giữa traces, logs và metrics. Nếu service name thay đổi giữa các replicas hoặc pipeline, backend có thể hiển thị nhiều service entities cho cùng một ứng dụng.

Ví dụ cấu hình resource attributes ở các version hỗ trợ:

~~~yaml
management:
  opentelemetry:
    resource-attributes:
      service.name: order-api
      service.version: "2.3.1"
      deployment.environment: production
~~~

Property namespace và resource integration phụ thuộc Boot version. Nếu ứng dụng tự tạo Resource bean hoặc SDK riêng, phải kiểm tra cách merge với auto-configured Resource; tránh tạo hai Resource definitions khác nhau cho cùng một pipeline.

Không đặt request ID, user ID hoặc order ID vào Resource. Những giá trị này thay đổi theo request và thuộc span/log attributes có kiểm soát, không phải service identity.

## 13. Nâng cấp Spring Boot mà không làm đứt tracing

Một đợt nâng cấp Boot có thể thay đổi:
- Dependency versions và artifact names.
- Auto-configuration class/module boundaries.
- Property namespaces và defaults.
- OpenTelemetry SDK version.
- Exporter builder customization APIs.
- Context propagation behavior.
- Default sampler và semantic conventions.

Quy trình nâng cấp nên có các bước:

1. Ghi nhận Boot, Java, Micrometer, Micrometer Tracing, tracer bridge và exporter versions hiện tại.
2. Đọc release notes và tracing reference của target Boot minor version.
3. Thay dependencies theo đúng starter/module của target version.
4. Xóa bridge/exporter trùng hoặc version override không cần thiết.
5. Chuyển property namespace nếu tài liệu target version yêu cầu.
6. Kiểm tra sampling, propagation format và resource attributes.
7. Chạy integration test có một inbound request và ít nhất một outbound call.
8. Kiểm tra trace backend có một trace đầy đủ với server/client spans.
9. So sánh sampling rate, exporter failures và trace volume trước/sau.
10. Rollout canary và giữ phương án rollback nếu trace completeness hoặc ingest thay đổi.

Không đánh giá nâng cấp chỉ bằng việc ứng dụng khởi động thành công. Tracing có thể âm thầm mất instrumentation hoặc export trong khi business endpoints vẫn chạy bình thường.

## 14. Troubleshooting tương thích tracer/version

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| Boot không tạo Tracer bean | Thiếu Actuator/tracing bridge hoặc starter sai version. | Kiểm tra runtime dependency tree và auto-configuration report. |
| Có hai Tracer/bridge beans | Cả OTel và Brave bridge cùng trên classpath hoặc custom config trùng. | Chỉ giữ một bridge và xác định bean owner. |
| Compile lỗi sau nâng Boot | API/artifact/package đã thay đổi giữa major versions. | Đọc migration guide và dependency metadata target version. |
| App khởi động nhưng không export spans | Thiếu exporter/reporter, endpoint sai hoặc pipeline bị disable. | Kiểm tra exporter bean, property namespace và exporter logs. |
| Boot 3 config không hoạt động trên Boot 4 | Property namespace hoặc starter đã thay đổi. | Dùng reference docs đúng target minor release. |
| Traces bị duplicate | Agent và application auto-instrument cùng một operation. | Kiểm tra agent extensions, starter và custom interceptors. |
| Client span không nối server span | Dùng builder tự tạo, propagation format không tương thích hoặc header bị xóa. | Kiểm tra Boot-injected builder và trace headers. |
| Sampling khác nhau giữa services | Sampler custom/parent-based behavior không nhất quán. | So sánh sampled flags và sampler config. |
| Trace ID có nhưng resource service sai | Resource bean/custom SDK không merge attributes như mong đợi. | Kiểm tra Resource payload ở exporter. |
| Exporter class not found | Exporter artifact không được thêm hoặc version mismatch. | Kiểm tra dependency tree và BOM. |
| NoSuchMethodError trong OTel SDK | Các OTel modules bị override thành version không tương thích. | Đồng bộ OTel artifacts bằng dependency management. |
| Backend không nhận protocol | Dùng OTLP exporter tới Zipkin endpoint hoặc ngược lại. | Đối chiếu protocol, receiver và endpoint. |

## 15. Runbook xác minh tracer compatibility

1. **Xác định Boot version:** kiểm tra plugin/parent/BOM đang thực sự resolve.
2. **Xác định Java version:** bảo đảm Java runtime phù hợp với Boot major/minor version.
3. **Kiểm tra một bridge:** dependency tree chỉ có OTel hoặc Brave bridge theo lựa chọn.
4. **Kiểm tra exporter:** OTLP exporter đi với OTLP receiver; Zipkin reporter đi với Zipkin endpoint.
5. **Kiểm tra property namespace:** đối chiếu reference đúng version, không dùng YAML từ tutorial khác major.
6. **Kiểm tra bean:** xác định Tracer, ObservationRegistry, OpenTelemetry/Brave tracer và exporter được tạo.
7. **Phát một request:** tạo một server span và một outbound client span.
8. **Kiểm tra propagation:** xác minh W3C/B3 header và trace ID liên tục giữa services.
9. **Kiểm tra sampling:** đối chiếu probability, parent-based behavior và sampled flag.
10. **Kiểm tra backend:** xác nhận trace đủ spans, resource service.name đúng và không duplicate.
11. **Kiểm tra agent:** xác nhận Java agent không instrument trùng với application instrumentation.
12. **Ghi nhận baseline:** exporter errors, spans/second, sampling ratio và trace completeness.

## 16. Bài tập tự kiểm tra

### Bài 1 — Chọn bridge

Một ứng dụng Spring Boot dùng OpenTelemetry làm tracer. Dependency bridge nào phù hợp?

**Đáp án:** micrometer-tracing-bridge-otel. Không thêm đồng thời micrometer-tracing-bridge-brave.

### Bài 2 — Backend Zipkin

Một ứng dụng dùng Brave và muốn gửi traces tới Zipkin. Có nên cấu hình OTLP exporter chỉ vì cả hai đều là trace backend không?

**Đáp án:** Không. Dùng Brave tracing integration và Zipkin reporter/properties tương ứng. OTLP và Zipkin là hai protocol khác nhau.

### Bài 3 — Nâng từ Boot 3 lên Boot 4

Build thành công sau khi nâng major version nhưng trace không còn export. Cần kiểm tra gì?

**Đáp án:** Artifact/starter mới, auto-configuration, property namespace, exporter bean và dependency versions. Không giả định cấu hình Boot 3 giữ nguyên trên Boot 4.

### Bài 4 — Hai bridge trên classpath

Dependency tree chứa cả OTel bridge và Brave bridge. Vì sao cần sửa?

**Đáp án:** Một ứng dụng nên chọn một tracer implementation chính. Hai bridge có thể gây auto-configuration ambiguity, bean cạnh tranh hoặc tracing pipeline không nhất quán.

### Bài 5 — Client/server trace bị đứt

Client span và server span có trace ID khác nhau. Có nên tăng sampling probability lên 100%?

**Đáp án:** Không giải quyết nguyên nhân propagation. Kiểm tra builder được Boot auto-configure, trace headers, W3C/B3 compatibility, proxy và async context.

### Bài 6 — Nhiều backend

Đội muốn gửi cùng traces tới hai backend. Có nên thêm bridge thứ hai?

**Đáp án:** Không. Giữ một tracer và cân nhắc fan-out từ exporter/Collector hoặc cấu hình exporter pipeline có chủ đích. Tránh instrument cùng operation hai lần.

## 17. Checklist triển khai

- [ ] Đã xác định Spring Boot major/minor version và Java runtime.
- [ ] Dependency versions được quản lý bằng Boot BOM/parent/plugin phù hợp.
- [ ] Chỉ chọn một Micrometer Tracing bridge: OpenTelemetry hoặc Brave.
- [ ] Exporter/reporter khớp protocol và backend.
- [ ] Starter/module names được đối chiếu với reference đúng version.
- [ ] Property namespace không bị copy chéo giữa Boot 3.x và 4.x.
- [ ] Không tạo SDK/provider/tracer pipeline cạnh tranh với auto-configuration.
- [ ] Sampling và parent-based behavior được xác minh.
- [ ] W3C/B3 propagation được thống nhất giữa services.
- [ ] RestClient/WebClient dùng builder được Boot auto-configure khi cần automatic propagation.
- [ ] Resource attributes service.name/version/environment nhất quán.
- [ ] Agent và application instrumentation không tạo duplicate spans.
- [ ] Integration test xác minh server/client spans cùng trace ID.
- [ ] Backend nhận đúng protocol, endpoint và service identity.
- [ ] Có baseline exporter errors, sampling ratio và trace completeness trước nâng cấp.
- [ ] Có canary/rollback plan cho thay đổi Boot/tracer.

**Ghi nhớ:** Spring Boot version quyết định dependency, auto-configuration và property namespace; Micrometer Tracing bridge quyết định tracer implementation; exporter/reporter quyết định protocol gửi dữ liệu. Chọn một bridge, dùng dependency management của Boot, đối chiếu tài liệu đúng version và kiểm thử propagation từ client tới server. Một ứng dụng khởi động thành công chưa chứng minh tracing tương thích; chỉ trace đầy đủ và export tới đúng backend mới xác nhận pipeline hoạt động.
