# Tránh instrumentation trùng khi kết hợp thư viện và Java agent

Một ứng dụng Spring AI có thể đồng thời dùng Spring Boot Actuator/Micrometer, Micrometer Tracing, OpenTelemetry SDK, OpenTelemetry Java Agent, instrumentation của HTTP client/JDBC và các observations do Spring AI phát ra. Mỗi thành phần đều có thể tạo spans, metrics hoặc propagate trace context. Nếu không xác định ranh giới sở hữu, một HTTP request có thể xuất hiện thành hai hoặc ba spans gần như giống nhau, một SQL query bị ghi nhiều lần, metrics bị đếm đôi và trace tree trở nên khó đọc.

Bài học thuộc chương **Thiết kế trace** của module `SPRING_AI_EVALUATION_OBSERVABILITY`. Module này đánh giá chất lượng ứng dụng Spring AI bằng dataset, relevance, fact checking và kiểm thử RAG/tool calling; đồng thời đo metrics, traces, chi phí và độ trễ để phát hiện suy giảm qua các phiên bản prompt, model và pipeline. Do đó, instrumentation phải phản ánh đúng số operation thực tế, cho thấy quan hệ parent-child rõ ràng và giữ được provenance cần thiết cho evaluation.

Sau bài học, bạn có thể:

- Phân biệt Micrometer Observation, Micrometer Tracing, OpenTelemetry SDK, Java agent và library instrumentation.
- Nhận diện duplicate spans, duplicate metrics, context propagation conflict và exporter trùng.
- Chọn một instrumentation owner cho từng ranh giới operation.
- Kết hợp Spring Boot/Spring AI với Java agent mà không instrument cùng HTTP/JDBC/model call hai lần.
- Bổ sung custom spans ở business boundaries còn thiếu.
- Tắt hoặc giới hạn một instrumentation cụ thể theo package/library khi cần.
- Kiểm thử trace tree, span count, parent IDs, metric counts và propagation sau thay đổi.

## 1. Vì sao instrumentation trùng xảy ra?

Instrumentation là cơ chế quan sát một operation và phát telemetry. Có thể được thêm từ nhiều nơi:

1. **Framework instrumentation:** Spring MVC/WebFlux, Spring Data, Spring AI hoặc Micrometer Observation tạo observations cho các operation framework quản lý.
2. **Tracing bridge:** Micrometer Tracing kết nối Observation với tracing implementation như Brave hoặc OpenTelemetry.
3. **OpenTelemetry SDK instrumentation:** code hoặc thư viện dùng OpenTelemetry API/SDK trực tiếp để tạo spans và export.
4. **Java agent instrumentation:** agent dùng bytecode instrumentation để tự động quan sát HTTP clients, JDBC, messaging, executors và nhiều thư viện khác.
5. **Manual instrumentation:** nhóm phát triển tự tạo spans quanh business operations, retry loops, RAG stages hoặc tool execution.

Mỗi lớp có mục đích hợp lệ. Vấn đề xuất hiện khi hai lớp cùng instrument **một operation, cùng một boundary và cùng một lần thực thi** mà không có quan hệ cha-con có ý nghĩa.

### 1.1. Ví dụ một HTTP request bị instrument hai lần

Giả sử Spring Boot tạo server observation cho endpoint và Java agent cũng instrument servlet server:

```text
SERVER POST /api/answers              [Spring Boot / Micrometer]
└── SERVER POST /api/answers          [OpenTelemetry Java Agent]
    └── app.ai.answer                 [manual business span]
        └── CLIENT POST /v1/chat      [agent HTTP client span]
```

Hai server spans đầu có thể có cùng route, method, status và duration gần giống nhau. Nếu chúng cùng biểu diễn một inbound request, trace bị nhân đôi. Điều này không có nghĩa mọi parent-child spans cùng tên đều sai; cần xác định chúng có đo hai operation khác nhau hay chỉ lặp lại cùng boundary.

### 1.2. Ví dụ HTTP client bị instrument bởi nhiều lớp

```text
app.ai.model.generate
  ├── HTTP POST /v1/chat/completions [Micrometer observation]
  │   └── HTTP POST /v1/chat/completions [Java agent]
  └── gen_ai chat operation          [Spring AI instrumentation]
```

Nếu HTTP client observation và agent span cùng đo một outbound request, hai spans đó là duplicate. Span GenAI có thể vẫn cần thiết vì nó biểu diễn logical model operation và có attributes như model/provider/token usage. Hãy phân biệt **logical model operation** với **transport request**.

### 1.3. Duplicate không chỉ là hai spans cùng tên

Các dấu hiệu cần điều tra:

- Hai spans có cùng trace ID, cùng parent ID, start/end gần nhau và cùng attributes.
- Một operation xuất hiện hai lần ở hai instrumentation scopes khác nhau.
- Một HTTP request thực tế nhưng có hai client spans tương đương.
- Một SQL statement được ghi hai lần bởi datasource instrumentation và agent JDBC instrumentation.
- Một request count tăng gấp đôi sau khi bật agent.
- Trace ID bị đổi giữa các phần của cùng request do nhiều SDK/propagators không thống nhất.
- Hai exporters gửi cùng spans tới backend, khiến trace bị duplicate dù chỉ có một span được tạo ở process.

Không kết luận chỉ dựa vào tên span. So sánh trace/span IDs, parent IDs, timestamps, instrumentation scope, resource attributes, span kind và số request thật ở server/provider.

## 2. Phân biệt các lớp trong hệ sinh thái Spring

### 2.1. Micrometer Observation

Micrometer Observation là API instrumentation cấp ứng dụng. Một Observation biểu diễn operation và có thể được xử lý bởi các handlers khác nhau:

- Metrics handler có thể ghi timer/counter.
- Tracing handler có thể tạo span.
- Logging hoặc handler tùy chỉnh có thể bổ sung metadata.

Một Observation không nhất thiết luôn tạo span; điều đó phụ thuộc registry và handlers được đăng ký. Khi dùng Spring Boot Actuator, nhiều framework observations được cấu hình tự động.

### 2.2. Micrometer Tracing

Micrometer Tracing cung cấp abstraction cho tracing và kết nối với tracer implementation/bridge. Trong Spring Boot, Observation có thể tạo spans thông qua tracing handler. Không nên giả định chỉ thêm Micrometer Tracing dependency là mọi thư viện đều được instrument; cần kiểm tra auto-configuration và các instrumentations đang bật.

### 2.3. OpenTelemetry API và SDK

OpenTelemetry API là API để tạo spans, context và propagation. SDK cung cấp tracer provider, sampler, processors và exporters. Một thư viện có thể phụ thuộc OTel API nhưng ứng dụng cần cấu hình SDK hoặc bridge để spans thực sự được record/export.

Nếu ứng dụng đã dùng Micrometer Tracing với OpenTelemetry bridge, việc tự khởi tạo thêm một OpenTelemetry SDK độc lập có thể tạo hai tracer providers, hai context managers hoặc hai exporters. Điều này dễ làm spans bị tách trace hoặc export hai lần.

### 2.4. OpenTelemetry Java Agent

Java agent tự động instrument nhiều thư viện bằng bytecode instrumentation. Agent có thể tạo spans mà không cần sửa code ứng dụng. Nó cũng có thể cấu hình exporter, propagators, resource attributes và sampler.

Agent không tự động biết mọi business operation của ứng dụng. Nó thường rất hữu ích ở các ranh giới thư viện như servlet, HTTP client, JDBC, messaging. Business spans cho `app.ai.answer`, `app.rag.retrieve` hoặc `app.ai.evaluation.case` vẫn có thể cần được tạo bằng Observation hoặc API phù hợp.

### 2.5. Instrumentation bên trong thư viện

Spring AI, Spring Framework, HTTP client hoặc database library có thể phát Observation hoặc spans riêng. Một số integration hoạt động thông qua Micrometer; một số dùng OTel instrumentation hoặc agent. Hành vi phụ thuộc phiên bản thư viện và cấu hình.

Không suy ra một library chắc chắn đã instrument chỉ vì nó có dependency tracing. Hãy chạy một request đại diện và xem instrumentation scope/span thực tế.

### 2.6. Bảng phân vai

| Thành phần | Vai trò chính | Có thể tạo spans? | Có thể tạo metrics? |
|---|---|---:|---:|
| Micrometer Observation | Business/framework observation API | Qua tracing handler | Qua metrics handler |
| Micrometer Tracing bridge | Kết nối Observation với tracer | Có | Không phải vai trò chính |
| OpenTelemetry API | API tạo spans/context | Qua SDK/provider | Qua metrics API |
| OpenTelemetry SDK | Record, sample, process và export | Có | Có |
| OpenTelemetry Java Agent | Auto-instrumentation runtime | Có | Tùy instrumentation/config |
| Spring AI/framework instrumentation | Quan sát các AI/framework operations | Có thể | Có thể |
| HTTP/JDBC library instrumentation | Quan sát transport/database operations | Có thể | Có thể |
| Manual instrumentation | Business boundaries riêng | Có thể | Qua Observation/metrics API |

Các vai trò có thể chồng lấn. Cần xem cấu hình runtime, không chỉ nhìn dependency tree.

## 3. Chọn một owner cho từng operation boundary

Nguyên tắc thực tế là **mỗi operation boundary có một instrumentation owner chính**. Các spans lồng nhau vẫn hợp lệ nếu chúng đo các operation khác nhau.

### 3.1. Ma trận ownership đề xuất

| Boundary | Owner ưu tiên | Owner khác có thể bổ sung | Tránh |
|---|---|---|---|
| HTTP server request | Spring Boot/Micrometer hoặc Java agent | Business span cho answer operation | Hai server spans cho cùng request |
| HTTP client request | Java agent hoặc Micrometer HTTP observation | Logical provider/model span | Hai client spans cho cùng outbound call |
| JDBC query | Agent JDBC instrumentation hoặc datasource instrumentation | Business retrieval span | Hai DB client spans cùng SQL execution |
| Spring AI ChatClient | Spring AI/Micrometer observation nếu version phát ra | Business answer span | Thêm wrapper trùng một ChatClient operation |
| GenAI provider call | Spring AI/provider instrumentation hoặc một OTel GenAI instrumentation | HTTP client span cho transport | Hai logical GenAI spans cho cùng invocation |
| RAG retrieval | Custom Observation ở business boundary | Vector DB/HTTP child spans | Nhiều retrieval spans cùng đo toàn pipeline |
| Tool execution | Custom Observation quanh tool callback | HTTP/DB spans bên trong tool | Ghi tool execution dù callback chưa chạy |
| Evaluation case | Custom Observation/job instrumentation | Judge model span và persistence span | Để trace sampling quyết định có chạy evaluator |

Đây là điểm xuất phát, không phải cấu hình cứng cho mọi phiên bản. Owner cuối cùng cần dựa trên spans thực tế được phát ra trong ứng dụng.

### 3.2. Phân biệt logical span và transport span

Một model call có thể hợp lệ với hai spans:

```text
app.ai.model.generate                 [logical model invocation]
└── CLIENT POST /v1/chat/completions   [one HTTP request]
```

Span cha có thể chứa prompt version, provider, model alias, token usage và final model outcome. Span con chứa HTTP method/route/status và transport duration. Hai spans không duplicate vì phạm vi khác nhau.

Ngược lại, nếu hai client spans đều đo cùng POST request với cùng start/end và cùng route/status, một instrumentation cần được tắt hoặc điều chỉnh.

### 3.3. Business span không phải wrapper mặc định cho mọi method

Custom span hữu ích khi nó tạo ranh giới có ý nghĩa:

- Toàn bộ answer pipeline.
- Retrieval stage bao gồm rewrite, search và merge.
- Tool dispatch/execution.
- Evaluation run/case.
- Một workflow có retry/fallback/parallel branches.

Không cần custom span cho mọi service method. Nếu một method chỉ chuyển tiếp tới một library call đã có span và không bổ sung ngữ nghĩa mới, span wrapper có thể làm trace sâu nhưng không hữu ích hơn.

## 4. Nhận diện duplicate spans trong trace

### 4.1. So sánh các trường định danh

Khi hai spans có vẻ trùng, kiểm tra:

| Trường | Dấu hiệu cần xem |
|---|---|
| Trace ID | Có thuộc cùng trace không? |
| Span ID | Hai span riêng biệt hay cùng span bị export hai lần? |
| Parent span ID | Cùng parent thường gợi ý sibling instrumentation cho một boundary |
| Span kind | SERVER/CLIENT/INTERNAL có phù hợp không? |
| Start/end timestamps | Hai spans có thời gian gần như trùng nhau không? |
| Attributes | Method, route, DB system, statement operation có giống nhau không? |
| Instrumentation scope | Tên/version library nào tạo span? |
| Resource | Service name/version có giống nhau không? |

Hai bản ghi có cùng Span ID nhưng xuất hiện hai lần ở backend thường gợi ý export/ingestion duplicate. Hai Span IDs khác nhau với timestamps/attributes tương đương thường gợi ý hai instrumentations cùng tạo spans.

### 4.2. Instrumentation scope là bằng chứng quan trọng

OpenTelemetry span thường mang instrumentation scope (tên và có thể cả version của instrumentation library). Ví dụ:

```text
instrumentation scope:
  io.micrometer.observation
  io.opentelemetry.javaagent.apache-httpclient
  io.opentelemetry.jdbc
  org.springframework.ai
```

Tên scope cụ thể thay đổi theo agent/library version. Dùng scope để tìm nguồn tạo span thay vì chỉ nhìn span name.

### 4.3. Duplicate server spans

Một inbound request có thể có:

- Server span từ Spring Boot/Micrometer.
- Server span từ servlet/Spring Web instrumentation của Java agent.
- Custom controller span do ứng dụng tự tạo.

Nếu cả ba đều đo cùng request, chọn một owner cho server boundary. Giữ business span nếu nó mô tả operation khác như `app.ai.answer`, nhưng không bọc controller chỉ để sao chép HTTP method/route/status.

### 4.4. Duplicate client spans

Kiểm tra khi:

- Spring HTTP client observation đang bật và Java agent cũng instrument cùng client library.
- Một wrapper RestClient/WebClient tạo span, trong khi agent instrument underlying Apache HttpClient/Netty.
- Provider SDK tạo client span và agent instrument HTTP transport bên dưới.

Một logical GenAI span + một HTTP client span có thể hợp lệ. Hai HTTP client spans cho cùng socket request thường không.

### 4.5. Duplicate JDBC spans

Các nguồn có thể gồm:

- OpenTelemetry Java agent JDBC instrumentation.
- Datasource proxy/p6spy hoặc datasource decorator có tracing.
- Micrometer/ORM instrumentation tạo span query.
- Custom span quanh repository method.

Một business span `app.rag.vector.search` bao quanh một DB span là hợp lệ. Hai DB spans cùng đại diện một SQL execution là dấu hiệu cần xử lý.

### 4.6. Span count tăng bất thường

Theo dõi số spans trên mỗi logical request theo route/feature. Nếu sau khi bật agent, span count tăng từ 8 lên 18 mà business behavior không đổi, điều tra:

- Hai instrumentation cho cùng boundary.
- Agent instrument cả client wrapper và underlying transport.
- Retry instrumentation đang tạo attempt spans ở cả SDK và app.
- Spring AI và custom code cùng tạo một model invocation span.
- Async instrumentation tạo span cho submit và execution nhưng không phân biệt hai operation.

Không đặt một ngưỡng span count cố định cho mọi ứng dụng; dùng baseline theo operation và version.

## 5. Duplicate metrics và double counting

Instrumentation trùng có thể làm metric bị đếm đôi dù trace tree trông hợp lý.

### 5.1. Hai timer cho cùng request

Ví dụ:

- Spring Boot Observation ghi timer cho server request.
- Agent hoặc custom filter ghi thêm timer cho cùng endpoint.
- Dashboard cộng cả hai metrics vì tên hoặc tag khác nhau.

Kết quả là request volume/latency có thể bị hiểu sai. Một metric đo server request và một metric đo business answer operation có thể cùng tồn tại nếu tên và semantics khác nhau. Đừng cộng chúng như hai requests.

### 5.2. Metrics được ghi ở cả logical operation và attempt

Đối với retry:

- `model.logical.calls` đếm một lần cho một logical invocation.
- `model.http.attempts` đếm mỗi outbound request.
- `model.failures` có thể đếm failures theo attempt.
- `model.logical.failures` chỉ đếm operation cuối cùng thất bại.

Đây là các metric khác nhau, không phải duplicate. Đặt tên và mô tả semantics rõ để dashboard không cộng nhầm.

### 5.3. Không tạo metrics từ sampled traces

Metrics phải độc lập với trace sampling. Nếu metrics handler chỉ chạy khi span được sample, request counters và latency histograms có thể thấp hơn traffic thật. Micrometer Observation có thể có nhiều handlers; cần xác nhận metrics handler nhận mọi observation theo cấu hình mong muốn, kể cả khi tracing sampler drop span.

### 5.4. Kiểm tra metric identity

Để phát hiện duplicate:

- So tên metric, unit, type và tag keys.
- So `service.name`, `service.instance.id`, environment và version.
- Kiểm tra một request thực tế tăng counter bao nhiêu lần.
- Kiểm tra scrape/export pipelines có nhận cùng registry từ hai đường không.
- Kiểm tra Prometheus scrape cùng endpoint nhiều lần hoặc collector nhận duplicate OTLP metrics.

Hai metrics có tên khác nhau nhưng cùng ý nghĩa có thể vẫn gây double counting ở dashboard. Chuẩn hóa metric catalog và ghi rõ owner.

## 6. Context propagation và nhiều TracerProvider

Instrumentation trùng đôi khi không tạo hai spans giống nhau mà tạo ra **hai trace rời nhau** cho cùng một request.

### 6.1. Hai SDK độc lập trong cùng process

Một lỗi cấu hình có thể xảy ra khi:

- Spring Boot dùng Micrometer Tracing với OpenTelemetry bridge.
- Ứng dụng tự khởi tạo thêm OpenTelemetry SDK và exporter.
- Java agent cũng cung cấp global OpenTelemetry instance.
- Một thư viện lấy global tracer, thư viện khác lấy tracer từ Micrometer bridge.

Khi đó, spans có thể:

- Không cùng trace ID dù thuộc cùng request.
- Không có parent-child relation như mong đợi.
- Được export qua hai pipeline.
- Dùng resource attributes hoặc sampler khác nhau.

Không khởi tạo SDK/provider thứ hai chỉ để thêm một custom span. Hãy dùng tracing abstraction đã được ứng dụng cấu hình, hoặc xác định rõ một SDK owner và cách bridge tương thích.

### 6.2. Context propagation qua HTTP

Trong distributed tracing, service gọi inject trace context vào carrier, service nhận extract context. Với W3C Trace Context, header phổ biến là `traceparent` và có thể có `tracestate`.

Các điều cần kiểm tra:

- Propagator thống nhất giữa Spring Boot, OTel SDK/agent và downstream services.
- HTTP client instrumentation chỉ inject một context nhất quán.
- Proxy/gateway không xóa hoặc ghi đè tracing headers ngoài ý muốn.
- Không tự tạo trace ID mới giữa một request đang active.
- Không tin trace headers như cơ chế xác thực, authorization hoặc tenant selection.

### 6.3. Context propagation qua executor và Reactor

Async execution có thể mất context hoặc khôi phục context sai:

- Một child span trở thành root vì ThreadLocal/context không được propagate.
- Một task kế thừa context cũ do ThreadLocal không được clear.
- Hai instrumentation cùng wrap executor và tạo duplicate spans.
- Reactor context và ThreadLocal được bridge hai lần, gây parent không như mong muốn.

Chọn một cơ chế context propagation tương thích với Spring Boot/Micrometer/agent version. Kiểm tra trace thực tế trước và sau thread switch, `publishOn`, `subscribeOn`, `@Async` và executor submission.

### 6.4. Parent-child và span links

Không tạo parent-child giả chỉ để nối hai operation độc lập. Ví dụ answer request hoàn tất rồi evaluation worker chạy sau đó có thể là trace riêng với span link tới answer context. Dùng link/correlation phù hợp thay vì giữ HTTP span mở để bao trùm một job kéo dài.

## 7. Cách kết hợp Spring Boot, Spring AI và Java agent

Không có một cấu hình duy nhất đúng cho mọi ứng dụng. Hãy chọn một trong các mô hình triển khai sau và kiểm chứng bằng trace.

### 7.1. Mô hình A: Spring Boot/Micrometer làm tracing owner

Phù hợp khi ứng dụng đã dùng Spring Boot Actuator, Micrometer Observation và Micrometer Tracing:

```text
Spring MVC/WebFlux observations
Spring AI observations
Manual business observations
          |
          v
Micrometer ObservationRegistry
          |
          v
Micrometer Tracing bridge
          |
          v
Tracer implementation + exporter
          |
          v
Collector / backend
```

Trong mô hình này:

- Dùng Observation cho business spans.
- Dùng framework observations sẵn có cho HTTP/server/client khi đã được hỗ trợ.
- Dùng auto-instrumentation bổ sung có chọn lọc nếu có boundary chưa được quan sát.
- Tránh tạo thêm SDK/provider độc lập.

### 7.2. Mô hình B: OpenTelemetry Java agent làm auto-instrumentation owner

Phù hợp khi muốn agent instrument servlet, HTTP client, JDBC, messaging và các thư viện được hỗ trợ:

```text
Application code
  ├── Spring AI / framework observations
  └── Manual business spans
          |
          v
Micrometer/OTel API bridge (nếu dùng)
          |
          v
OpenTelemetry Java Agent SDK/provider
  ├── servlet instrumentation
  ├── HTTP client instrumentation
  ├── JDBC instrumentation
  └── messaging/executor instrumentation
          |
          v
OTLP exporter -> Collector -> backend
```

Trong mô hình này:

- Agent sở hữu các library boundaries mà nó instrument.
- Business code vẫn tạo spans qua API tương thích với agent/global provider hoặc Micrometer bridge đã cấu hình.
- Không khởi tạo exporter/SDK thứ hai trong application nếu agent đã sở hữu pipeline.
- Chỉ disable agent instrumentation cụ thể khi framework/library instrumentation khác đã sở hữu cùng boundary.

### 7.3. Mô hình C: Hybrid có kiểm soát

Hybrid có thể là lựa chọn hợp lý:

- Spring Boot/Micrometer tạo server observation.
- Java agent instrument JDBC hoặc một HTTP client chưa có instrumentation.
- Spring AI tạo logical model observation.
- Custom code tạo business spans cho RAG/tool/evaluation.

Điều kiện là có ownership map và test xác nhận không trùng. Hybrid không có nghĩa bật mọi instrumentation cùng lúc.

## 8. Tắt hoặc giới hạn instrumentation trùng

Nếu đã xác định hai instrumentation cùng tạo một boundary, hãy tắt đúng instrumentation không cần thiết. Tránh tắt toàn bộ tracing chỉ vì một loại span bị trùng.

### 8.1. OpenTelemetry Java Agent per-instrumentation controls

Java agent hỗ trợ cấu hình bật/tắt nhiều instrumentations theo tên. Mẫu cấu hình thường có dạng:

```bash
OTEL_INSTRUMENTATION_SERVLET_ENABLED=false
OTEL_INSTRUMENTATION_JDBC_ENABLED=true
OTEL_INSTRUMENTATION_APACHE_HTTPCLIENT_ENABLED=true
```

Các tên instrumentation được hỗ trợ và tên biến chính xác phụ thuộc agent version và thư viện. Hãy tra danh sách configuration options của đúng agent artifact/version đang triển khai; không copy tên ví dụ nếu agent không nhận diện nó.

Có thể dùng property tương ứng dạng `otel.instrumentation.<name>.enabled` trong cấu hình agent. Nếu muốn tắt mặc định và bật chọn lọc, kiểm tra option `otel.instrumentation.common.default-enabled` và các ngoại lệ được hỗ trợ trong version cụ thể.

### 8.2. Chọn tắt ở đâu?

| Tình huống | Hướng xử lý |
|---|---|
| Spring Boot server observation và agent server span trùng | Chọn một server instrumentation owner; tắt agent instrumentation hoặc Observation cụ thể sau khi xác minh |
| HTTP client observation và agent client span trùng | Chọn một client instrumentation; giữ logical model span nếu có ý nghĩa |
| JDBC agent span và datasource proxy span trùng | Giữ một DB instrumentation |
| Spring AI đã tạo model observation và custom model wrapper trùng | Bỏ wrapper custom hoặc chỉ giữ business-level answer span |
| Hai exporters gửi cùng SDK spans | Chỉ cấu hình một export path hoặc phân chia signal rõ |
| Metrics timer bị ghi đôi | Tắt một metrics handler/filter hoặc đổi semantics/tên metric nếu đo operation khác |

### 8.3. Spring Boot Observation controls

Spring Boot có thể cung cấp observation enable/disable controls theo observation name qua cấu hình `management.observations.enable.*` ở các phiên bản hỗ trợ. Tên observation và hành vi cụ thể phụ thuộc Spring Boot/framework version.

Trước khi disable:

1. Xác định observation name thực tế từ registry/trace.
2. Kiểm tra observation đó đang tạo metrics, spans hay cả hai.
3. Xác định việc tắt observation có làm mất metric timer mà dashboard đang dùng không.
4. Nếu chỉ muốn bỏ tracing handler cho một observation nhưng vẫn giữ metrics, cân nhắc ObservationPredicate/handler filtering phù hợp thay vì tắt toàn bộ observation.

### 8.4. Không disable propagation cùng instrumentation

Tắt một auto-instrumentation span không nhất thiết phải tắt context propagation. Một HTTP client vẫn cần inject trace context để downstream spans nối được với parent. Kiểm tra riêng:

- Span creation.
- Context extraction/injection.
- Metrics instrumentation.
- Exporter pipeline.

Đừng tắt propagation toàn cục chỉ để loại bỏ duplicate spans.

## 9. Áp dụng cho Spring AI: answer, model, RAG và tool

Spring AI có nhiều lớp operation:

- ChatClient/ChatModel logical interaction.
- Provider HTTP request.
- Advisor chain.
- Retrieval và vector store calls.
- Tool dispatch và callback execution.
- Evaluation/judge orchestration.

Một trace hữu ích có thể chứa nhiều lớp này, nhưng mỗi lớp phải có semantics riêng.

### 9.1. Cây trace tham chiếu

```text
SERVER POST /api/answers                [one server instrumentation]
└── app.ai.answer                       [business operation]
    ├── Spring AI ChatClient operation  [framework observation, if present]
    │   ├── app.rag.retrieve            [custom business boundary, if missing]
    │   │   └── CLIENT/DB search        [one library instrumentation]
    │   └── app.ai.model.generate       [logical model call, if not already emitted]
    │       └── CLIENT POST /chat       [one HTTP client instrumentation]
    └── app.ai.tool.execute             [custom callback boundary]
        └── CLIENT GET /orders/{id}     [one HTTP client instrumentation]
```

Đây là cấu trúc tham chiếu, không phải yêu cầu tạo mọi span bằng tay. Nếu Spring AI version hiện tại đã tạo observation cho ChatClient/model/retrieval, dùng chúng và chỉ thêm những business boundaries còn thiếu.

### 9.2. ChatClient và ChatModel

Trước khi thêm custom span quanh `chatClient.prompt().call()`:

1. Xem Spring AI version đang dùng có Observation instrumentation cho ChatClient/ChatModel hay không.
2. Bật tracing ở môi trường thử nghiệm và quan sát span tree.
3. Xác định observation nào biểu diễn ChatClient operation và observation nào biểu diễn provider/model invocation.
4. Chỉ tạo `app.ai.answer` nếu cần business boundary bao gồm retrieval, tool loop, answer assembly hoặc các bước ngoài ChatClient.
5. Không tạo thêm `app.ai.model.generate` nếu span tương đương đã tồn tại.

Tên observations, attributes và mức instrument có thể đổi theo Spring AI release. Hãy dựa vào instrumentation scope và trace runtime, không hardcode assumption từ bài viết này.

### 9.3. RAG và VectorStore

Một RAG pipeline có thể gồm query rewrite, embedding, vector search, rerank, context assembly và generation. Có thể instrument:

- `app.rag.retrieve`: logical retrieval stage.
- `app.rag.vector.search`: một lần query vector store nếu chưa có span phù hợp.
- HTTP/JDBC client span: transport/database call thực tế.

Nếu VectorStore implementation tự gọi embedding model và có instrumentation riêng, không tạo thêm span embedding giả hoặc gọi embedding lần thứ hai chỉ để đo. Ghi attributes topK, index version, hit count và filter policy ở operation sở hữu chúng; không ghi raw query/document content.

### 9.4. Tool calling

Tool dispatch và tool execution là hai operation khác nhau:

- Dispatch kiểm tra tool name, schema và permission.
- Execution chạy callback thực tế.
- HTTP/DB spans bên trong callback đo downstream operations.

Nếu Spring AI instrumentation đã tạo span cho tool callback, không bọc một span cùng ý nghĩa. Có thể thêm business span nếu cần ghi policy decision, idempotency outcome hoặc kết quả tool đã chuẩn hóa.

Không tạo HTTP client span nếu tool bị policy chặn trước khi gửi request.

### 9.5. Evaluation worker

Evaluation worker có thể dùng trace riêng với span cho case, judge model call và persistence. Nếu job async link với answer trace:

- Link biểu diễn quan hệ giữa hai traces độc lập.
- Worker trace có sampling policy riêng.
- Result store giữ run/case/answerTraceId/judgeTraceId và verdict.
- Không thêm span wrapper trùng model/judge call đã được instrument.

## 10. Ví dụ custom Observation không trùng framework spans

Mục tiêu của custom Observation nên là một business boundary mà framework không cung cấp. Ví dụ `app.ai.answer` bao trùm orchestration của ứng dụng, trong khi ChatClient, HTTP client và database observations tiếp tục được tạo bởi instrumentation owner tương ứng.

```java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import org.springframework.stereotype.Service;

@Service
final class AnswerOrchestrator {
    private final ObservationRegistry observations;
    private final ExistingAnswerPipeline pipeline;

    AnswerOrchestrator(
            ObservationRegistry observations,
            ExistingAnswerPipeline pipeline) {
        this.observations = observations;
        this.pipeline = pipeline;
    }

    Answer answer(AnswerRequest request) {
        Observation observation = Observation.createNotStarted(
                        "app.ai.answer", observations)
                .lowCardinalityKeyValue(
                        "app.ai.feature", "policy_assistant")
                .lowCardinalityKeyValue(
                        "app.ai.mode", request.mode())
                .lowCardinalityKeyValue(
                        "app.ai.operation", "answer");

        return observation.observe(() -> pipeline.execute(request));
    }
}
```

`ExistingAnswerPipeline` là service orchestration của ứng dụng trong ví dụ. Custom span chỉ bao business operation; pipeline tiếp tục dùng observations có sẵn của Spring AI và client instrumentation. Không thêm span quanh mỗi method con nếu chúng đã có spans phù hợp.

### 10.1. Thêm custom span chỉ khi boundary còn thiếu

Nếu trace cho thấy pipeline chỉ có HTTP span và model span, nhưng cần biết RAG stage mất bao lâu, có thể thêm Observation cho `app.rag.retrieve` quanh toàn retrieval orchestration. Không tạo thêm span cho underlying HTTP/DB call nếu chúng đã được instrument.

### 10.2. Đừng tạo hai ObservationRegistry

Dùng registry do Spring Boot quản lý và inject vào service. Tránh tự tạo `ObservationRegistry.create()` trong từng service/bean để tạo registry riêng, vì handlers và tracing context có thể khác registry chính.

### 10.3. Đừng tự tạo SDK trong custom span helper

Custom instrumentation không nên tự khởi tạo `OpenTelemetrySdk`, `SdkTracerProvider`, `BatchSpanProcessor` hoặc OTLP exporter mới nếu application/agent đã sở hữu pipeline. Dùng API/bridge hiện có và xác minh span xuất hiện trong đúng trace.

## 11. Exporter trùng và pipeline telemetry

Một span có thể được export hai lần dù chỉ được tạo một lần:

```text
One TracerProvider
      |
      +---- OTLP exporter -> Collector
      |
      +---- OTLP exporter -> Backend

Collector
      |
      +---- exporter -> Backend
```

Nếu cùng một SDK export trực tiếp tới backend và đồng thời gửi qua collector, backend có thể nhận duplicate data hoặc dữ liệu hai đường có cấu hình khác nhau. Không phải mọi fan-out exporter đều sai; vấn đề là cùng signal được gửi tới cùng backend qua hai đường mà không có deduplication/partition rõ.

### 11.1. Chọn một export path

Mô hình phổ biến:

```text
Application / Java Agent
          |
          | OTLP
          v
OpenTelemetry Collector
          |
          +--> trace backend
          +--> metrics backend (nếu pipeline cấu hình)
```

Nếu có yêu cầu export trực tiếp từ process tới backend khác, ghi rõ signal, endpoint, resource và mục đích để tránh gửi cùng spans hai lần.

### 11.2. Phân biệt duplicate spans và duplicate ingestion

- Cùng Span ID xuất hiện hai lần: kiểm tra exporter retry, collector routing, backend ingestion và fan-out.
- Hai Span IDs khác nhau nhưng cùng operation/timestamps: kiểm tra hai instrumentations.
- Hai traces khác trace ID cho cùng request: kiểm tra SDK/provider/context propagation.
- Một trace có parent và child cùng operation: kiểm tra wrapper/auto-instrumentation và span ownership.

### 11.3. Retry của exporter không phải retry của business operation

Exporter có thể retry gửi batch khi collector/backend unavailable. Đây là telemetry delivery retry, không phải model/tool operation retry. Theo dõi exporter queue, send failures, dropped spans và collector receive counts riêng; không đưa exporter attempts vào metrics model calls.

## 12. Quy trình điều tra instrumentation trùng

Khi thấy trace có spans trùng, không tắt ngẫu nhiên một dependency. Dùng quy trình có thể lặp lại để tìm đúng owner.

### Bước 1: Chụp baseline trước khi thay đổi

Chạy một request đại diện trong môi trường dev/staging và lưu:

- Trace đầy đủ.
- Span count theo trace.
- Span name, kind, parent ID, start/end và instrumentation scope.
- Resource attributes.
- Metric samples liên quan.
- Request count ở server/mock provider/database test fixture.

Dùng một request có thể tái lập để so sánh trước/sau. Tránh bật/tắt nhiều instrumentation cùng lúc vì sẽ khó xác định thay đổi nào tạo ra kết quả.

### Bước 2: Lập bảng spans theo boundary

| Boundary | Span hiện tại | Instrumentation scope | Có duplicate? | Owner mong muốn |
|---|---|---|---|---|
| HTTP server | SERVER /api/answers | Micrometer | Có thể | Chọn một |
| HTTP server | SERVER /api/answers | Java agent | Có thể | Chọn một |
| Answer business | app.ai.answer | Application | Không nếu distinct | Application |
| Model logical call | GenAI/chat span | Spring AI | Không nếu distinct | Spring AI |
| Provider HTTP | CLIENT /chat | Java agent | Kiểm tra | Agent hoặc Micrometer |
| Vector DB | DB query span | JDBC agent | Kiểm tra | Agent hoặc datasource |

Đây là mẫu điền, không phải dự đoán về spans mặc định. Ghi đúng scope/name thực tế từ trace của ứng dụng.

### Bước 3: Xác minh operation thực tế

Một HTTP call thực tế có thể được đếm bằng mock server/access log hoặc request counter ở provider stub. Nếu trace hiển thị hai client spans nhưng server nhận một request, nhiều khả năng là duplicate instrumentation. Nếu server nhận hai requests, có thể là retry hoặc code thực sự gọi hai lần; không nên tắt một span trước khi xác minh.

### Bước 4: Chọn owner và thay đổi một cấu hình

Quyết định boundary thuộc:

- Framework/Micrometer.
- Java agent.
- Library instrumentation.
- Manual business instrumentation.

Sau đó chỉ thay đổi đúng instrumentation liên quan, giữ context propagation và các spans khác cần thiết.

### Bước 5: So sánh trace và metrics sau thay đổi

Kiểm tra:

- Số spans giảm đúng phần duplicate.
- Parent/child relation vẫn hợp lệ.
- Downstream trace vẫn nối với upstream.
- HTTP/DB requests thực tế không đổi ngoài dự kiến.
- Metrics request/error/latency không bị mất.
- Token/cost/evaluation records vẫn đầy đủ.
- Không phát sinh trace rời hoặc root spans ngoài ý muốn.

## 13. Cấu hình và kiểm soát theo môi trường

Instrumentation nên được cấu hình rõ theo môi trường và có thể thay đổi mà không sửa business logic.

### 13.1. Ví dụ agent options theo môi trường

Một cấu hình staging có thể giữ server spans từ Spring Boot và dùng agent cho JDBC/HTTP client:

```bash
OTEL_INSTRUMENTATION_SERVLET_ENABLED=false
OTEL_INSTRUMENTATION_JDBC_ENABLED=true
OTEL_INSTRUMENTATION_APACHE_HTTPCLIENT_ENABLED=true
OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4317
```

Ví dụ này chỉ minh họa ý tưởng selective instrumentation. Agent version, framework stack và instrumentation name quyết định biến nào hợp lệ. Nếu app dùng WebFlux, Jetty, Tomcat hoặc một HTTP client khác, tên instrumentation có thể khác. Xem startup logs/config diagnostics để xác nhận agent đã nhận option.

### 13.2. Cấu hình Spring Boot

Spring Boot có thể bật/tắt observations theo tên trong các phiên bản hỗ trợ:

```yaml
management:
  observations:
    enable:
      http.server.requests: true
```

Tên ở ví dụ là minh họa; dùng đúng observation name của Spring Boot/framework version. Trước khi tắt một observation để loại span trùng, kiểm tra nó có đồng thời cung cấp metric timer mà dashboard đang dùng không.

### 13.3. Không tắt mọi instrumentation mặc định trong production

Tắt toàn bộ agent instrumentation có thể làm mất HTTP/JDBC/messaging visibility và khiến điều tra khó hơn. Thay đổi nên có:

- Scope cụ thể (service, library, operation).
- Lý do và evidence về duplicate.
- Owner phê duyệt cấu hình theo quy trình team.
- Validation trước/sau.
- Rollback config.

### 13.4. Resource attributes và service identity

Nếu Micrometer và Java agent cùng export, chúng cần dùng service identity nhất quán:

- `service.name`
- `service.version`
- `deployment.environment.name`
- service namespace/instance identity nếu cần

Nếu cùng process xuất spans với resource khác nhau, backend có thể hiển thị hai service hoặc tách trace search. Đừng gắn cùng một resource attribute khác giá trị ở hai pipeline nếu đó thực sự là cùng service instance.

## 14. Kiểm thử để ngăn instrumentation trùng quay lại

Instrumentation configuration là một phần của hợp đồng vận hành. Nên có smoke/integration tests ở mức đủ kiểm soát để phát hiện duplicate sau khi nâng Spring Boot, Spring AI, agent hoặc HTTP client.

### 14.1. Test một request có thể tái lập

Tạo endpoint test thực hiện:

1. Nhận một HTTP request.
2. Gọi một ChatClient fake/stub.
3. Gọi một vector store fake hoặc test database.
4. Thực thi một tool callback.
5. Trả response.

Thu spans qua test exporter/collector hoặc backend test. Xác nhận mỗi boundary chỉ có số spans mong đợi.

### 14.2. Hợp đồng span tree

Một assertion tham chiếu:

```text
one SERVER span for the inbound HTTP request
one app.ai.answer business span
one logical model span if the framework emits it
one CLIENT span for each actual outbound HTTP request
one DB span for each actual database operation
one tool execution span for each callback execution
all children have the expected parent/trace context
```

Không cố định span count tổng nếu framework version thêm spans có ý nghĩa. Test theo operation boundary và instrumentation owner, không test snapshot tuyệt đối dễ vỡ.

### 14.3. Kiểm thử duplicate detection

Có thể định nghĩa heuristic cho cùng boundary:

- Cùng trace.
- Cùng span kind.
- Cùng normalized route/DB operation.
- Cùng parent hoặc parent relation không có ý nghĩa nghiệp vụ.
- Thời gian overlap gần như hoàn toàn.
- Hai instrumentation scopes khác nhau.

Heuristic này tạo candidate để review, không tự động xóa spans. Một logical span có thể bao transport span hợp lệ dù duration overlap.

### 14.4. Test metrics

Với một request:

- Server request counter tăng đúng một.
- Business answer counter tăng đúng một.
- Outbound HTTP attempt counter tăng theo số requests thực tế.
- DB operation counter tăng theo số SQL executions.
- Trace sampling không làm thay đổi metrics counts.

Không gộp business answer count và HTTP server request count nếu chúng có semantics khác nhau.

### 14.5. Test propagation

Gửi request qua hai service test và xác nhận:

- Downstream trace ID bằng upstream trace ID.
- Downstream parent span ID trỏ tới client/server boundary phù hợp theo propagator.
- Không sinh trace root mới ngoài ý muốn.
- Async child giữ đúng context hoặc dùng span link khi lifecycle độc lập.
- Tắt một instrumentation không làm mất propagation cần thiết.

## 15. Nâng cấp thư viện và Java agent an toàn

Một bản nâng cấp có thể thêm instrumentation mới hoặc đổi span names/attributes. Ví dụ framework bắt đầu phát Observation mà trước đây chỉ Java agent tạo span; sau upgrade có thể xuất hiện duplicate.

### 15.1. Quy trình nâng cấp

1. Ghi lại Spring Boot, Spring AI, Micrometer, OTel SDK/bridge, Java agent và HTTP/JDBC client versions.
2. Lưu baseline trace cho các operation đại diện.
3. Đọc release notes/config options của các instrumentation liên quan.
4. Nâng cấp trong staging với traffic/test case có thể tái lập.
5. So span tree, instrumentation scopes, attributes và metrics.
6. Điều chỉnh owner/config nếu instrumentation mới tạo overlap.
7. Chạy smoke tests trước khi rollout production.

### 15.2. Version pinning và configuration drift

Không để agent version tự thay đổi ngoài dependency/runtime manifest. Ghi:

- Agent artifact/version.
- Application dependency versions.
- Instrumentation enable/disable options.
- Exporter endpoint và protocol.
- Sampler/propagator.
- Resource attributes.

Configuration này có thể nằm trong deployment manifest hoặc secret/config management; không ghi credentials/token vào tài liệu hoặc trace.

### 15.3. Canary sau nâng cấp

Triển khai một nhóm nhỏ instances trước:

- So span count per request.
- So duplicate candidates.
- So HTTP/DB request counts.
- So trace completeness và error rate.
- So metrics cardinality và exporter drops.

Chỉ rollout rộng khi không mất visibility cần thiết và không có double counting.

## 16. Chẩn đoán theo triệu chứng

| Triệu chứng | Nguyên nhân có thể | Cách xác minh |
|---|---|---|
| Hai SERVER spans cùng route và duration | Spring Boot + agent cùng instrument server | So instrumentation scope, parent ID và một request test |
| Hai CLIENT spans cùng HTTP route | Micrometer/client library + agent | So Span IDs, timestamps và mock server request count |
| Hai DB spans cùng SQL operation | JDBC agent + datasource proxy/ORM instrumentation | So scope và số SQL executions thực tế |
| Hai trace IDs trong một request | Hai TracerProviders/context managers hoặc context bị mất | Kiểm tra active span, propagator và exporter/provider config |
| Cùng Span ID xuất hiện hai lần ở backend | Exporter fan-out, collector routing hoặc ingestion duplicate | So raw OTLP/export path và collector pipeline |
| Span count tăng sau upgrade | Framework mới thêm observations hoặc agent instrumentation đổi | So version/scope trước và sau |
| Metrics tăng gấp đôi nhưng spans không đổi | Hai metrics handlers/filters hoặc scrape duplication | Kiểm tra registry, scrape targets và metric identity |
| Metrics giảm sau khi tắt observation | Observation chứa cả metrics handler và tracing handler | Xem handler chain; lọc tracing riêng nếu cần |
| Trace mất downstream spans sau khi disable agent | Tắt propagation hoặc client instrumentation sở hữu inject/extract | Kiểm tra trace headers và downstream context |
| Một business span và một HTTP span overlap | Có thể là logical operation + transport call hợp lệ | Kiểm tra semantics/attributes khác nhau |
| Trace bị chia thành nhiều roots khi dùng async | Context propagation không hoạt động | Kiểm tra executor/Reactor context và parent IDs |
| Provider nhận hai requests nhưng trace có một client span | Một retry layer chưa được instrument | So provider stub/access logs với retry metrics |

### 16.1. Log chẩn đoán của agent

Trong staging, có thể bật diagnostic logging của agent theo tài liệu đúng version để xem:

- Agent version và instrumentation modules được cài.
- Instrumentation nào enabled/disabled.
- Config option nào được nhận diện.
- Exporter và propagator đang hoạt động.
- Warning về class transformation hoặc exporter initialization.

Không để verbose agent debug logging bật lâu trong production nếu gây overhead hoặc phát ra dữ liệu nhạy cảm.

### 16.2. Không sửa duplicate bằng cách rename span

Đổi một span name từ `HTTP POST` thành `custom-http` không loại bỏ instrumentation trùng. Nó chỉ che dấu sự giống nhau. Hãy xác định boundary, owner và cấu hình tạo span.

## 17. Bảo mật và chất lượng dữ liệu telemetry

Khi kết hợp nhiều instrumentation, tập attributes có thể lớn hơn dự kiến. Agent có thể tự thêm URL, DB metadata hoặc exception details; custom code có thể thêm prompt/model/evaluation fields.

### 17.1. Allowlist attributes

Chỉ xuất metadata cần cho chẩn đoán:

- Operation name/route template.
- Provider/model alias đã chuẩn hóa.
- Prompt/pipeline/index/rubric version.
- Retry attempt/outcome và latency.
- Tool name đã allowlist.
- Token usage và cost theo policy.

Tránh:

- Raw prompt, answer hoặc conversation transcript.
- Authorization headers, API keys, cookies.
- SQL bind values và raw query parameters.
- Tool arguments chứa account/order/customer data.
- User IDs hoặc document IDs nếu không có mục đích và policy rõ.

### 17.2. Redaction ở mọi nguồn instrumentation

Redaction phải áp dụng cho:

- Manual Observation attributes/events.
- Spring/framework instrumentation.
- Java agent instrumentation.
- HTTP/JDBC instrumentation.
- Logs và exporter processors.

Chỉ redact custom spans là chưa đủ nếu agent vẫn export headers, SQL statements hoặc exception messages. Kiểm tra payload sau khi qua collector, không chỉ UI đã che field.

### 17.3. Cardinality và kích thước spans

Khi hai instrumentation cùng ghi attributes, span có thể phình lớn. Giữ:

- Tên span ổn định.
- Attributes có kiểu và namespace rõ.
- Low-cardinality metric dimensions.
- High-cardinality identifiers chỉ ở trace/result store khi được phép.
- Không serialize object lớn hoặc document content vào span.

## 18. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách sửa |
|---|---|---|
| Bật mọi instrumentation cùng lúc mà không kiểm tra | Duplicate spans và metrics | Lập ownership map và baseline |
| Coi hai spans cùng tên luôn là duplicate | Xóa nhầm logical/transport spans khác nhau | So semantics, scope và operation boundary |
| Coi mọi parent-child overlap là sai | Làm mất business span hợp lệ | Phân biệt logical operation với I/O |
| Tạo OTel SDK thứ hai trong ứng dụng đã có bridge/agent | Trace bị tách và export trùng | Dùng một tracing provider/export path |
| Tự tạo span cho mọi method | Trace quá sâu, khó đọc | Chỉ instrument meaningful boundaries |
| Bọc ChatClient khi Spring AI đã tạo observation tương đương | Model operation bị ghi đôi | Xem trace trước khi thêm custom span |
| Tắt toàn bộ Java agent để sửa một duplicate | Mất JDBC/HTTP visibility | Tắt đúng instrumentation module |
| Tắt Observation để bỏ span mà không kiểm tra metrics | Dashboard mất timer/counter | Lọc tracing handler hoặc predicate phù hợp |
| Tắt context propagation cùng auto-instrumentation | Downstream trace bị tách | Kiểm tra span creation và propagation riêng |
| Export trực tiếp và qua collector tới cùng backend | Duplicate ingestion | Chọn một export path |
| Không kiểm tra agent config có được nhận | Tưởng đã disable nhưng spans vẫn xuất hiện | Xem startup diagnostics và trace scope |
| Không kiểm thử sau nâng version | Duplicate quay lại khi framework thêm instrumentation | Smoke test và canary |
| Đổi span name để che duplicate | Vấn đề ownership vẫn còn | Sửa instrumentation source |
| Dùng metric labels có trace/case IDs | Cardinality bùng nổ | Dùng metrics tổng hợp và traces chi tiết |
| Dựa vào trace count để đếm request | Sai mẫu số do sampling/duplicate | Dùng request metrics độc lập |

## 19. Bài thực hành: hợp nhất instrumentation cho Spring AI service

**Bối cảnh:** Một answer API dùng Spring Boot Actuator, Spring AI ChatClient, PGvector và một tool tra cứu đơn hàng. Service được chạy với OpenTelemetry Java Agent. Trace hiện có hai server spans, hai HTTP client spans cho model call và một số request metrics tăng gần gấp đôi sau khi bật agent.

### Phần A — Lập inventory

1. Ghi versions của Spring Boot, Spring AI, Micrometer, tracing bridge, Java agent, HTTP client và JDBC driver.
2. Thu một trace đại diện cho answer request.
3. Lập bảng span name/kind/parent/scope/resource.
4. Đếm outbound requests thực tế bằng mock provider và DB fixture.
5. Xác định boundary nào đang được hai instrumentation sở hữu.

### Phần B — Chọn ownership

1. Chọn một owner cho HTTP server boundary.
2. Chọn một owner cho model provider HTTP transport.
3. Giữ logical GenAI span nếu nó có semantics khác HTTP span.
4. Chọn một JDBC instrumentation.
5. Giữ business spans cho answer/RAG/tool/evaluation nếu framework chưa cung cấp boundary tương đương.

### Phần C — Thay đổi cấu hình có kiểm soát

1. Disable đúng agent instrumentation hoặc observation bị trùng ở staging.
2. Không tạo SDK/provider thứ hai.
3. Giữ context propagation và exporter path thống nhất.
4. Xác minh resource/service identity giống nhau giữa các spans.
5. Lưu config diff và rollback option.

### Phần D — Kiểm thử sau thay đổi

1. Một inbound request chỉ có một server span cho boundary đã chọn.
2. Một outbound HTTP request có một transport client span.
3. Model logical span vẫn xuất hiện nếu framework cung cấp.
4. Một SQL execution có một DB span.
5. Downstream trace vẫn cùng trace ID và parent relation đúng.
6. Request/latency metrics vẫn ghi đúng một lần.
7. Token usage, cost và evaluation records không bị thay đổi.
8. Không có raw prompt/tool arguments/API keys trong exported telemetry.

### Câu hỏi tự kiểm tra

**1. Có phải span logical model và HTTP client span là duplicate?**  
Không nhất thiết. Logical span đo model invocation; HTTP client span đo một transport request. Chúng có thể là parent-child hợp lệ nếu mỗi span có semantics riêng.

**2. Hai spans cùng tên có chắc chắn duplicate không?**  
Không. So instrumentation scope, IDs, parent, timing, kind và operation semantics. Tên giống nhau có thể đại diện hai attempts hoặc hai nhánh hợp lệ.

**3. Cùng Span ID xuất hiện hai lần khác gì hai Span IDs khác nhau với cùng timing?**  
Cùng Span ID thường gợi ý duplicate export/ingestion. Hai Span IDs khác nhau thường gợi ý hai instrumentations đã tạo hai spans cho một boundary.

**4. Có thể tắt toàn bộ Java agent để loại duplicate server span không?**  
Không nên làm vậy nếu chỉ server instrumentation bị trùng. Chọn đúng instrumentation module và kiểm tra các HTTP/JDBC spans khác vẫn hoạt động.

**5. Vì sao không nên tạo OTel SDK riêng trong một helper class?**  
Ứng dụng/agent có thể đã sở hữu TracerProvider, context manager và exporter. SDK thứ hai có thể tạo trace rời, resource khác hoặc export trùng.

**6. Tắt Observation có thể làm mất gì ngoài tracing?**  
Observation có thể được xử lý bởi metrics handler và tracing handler. Tắt observation có thể làm mất cả timer/counter; cần kiểm tra handler chain hoặc lọc riêng tracing.

**7. Nếu disable agent instrumentation nhưng downstream trace không còn parent thì cần kiểm tra gì?**  
Kiểm tra context injection/extraction và propagator. Span creation và propagation là hai cơ chế liên quan nhưng không đồng nhất.

## 20. Ghi nhớ

- **Instrumentation trùng** xảy ra khi nhiều lớp cùng tạo telemetry cho một operation boundary; không phải mọi spans lồng nhau đều duplicate.
- **Micrometer Observation** là API instrumentation; **Micrometer Tracing** kết nối Observation với tracer; **OTel SDK** record/process/export; **Java agent** tự động instrument thư viện.
- **Một operation boundary cần một owner chính**; các logical/business spans và transport spans vẫn có thể cùng tồn tại khi semantics khác nhau.
- **Instrumentation scope, Span ID, parent ID, span kind, timestamps và attributes** giúp xác định nguồn tạo span.
- **Cùng Span ID bị lặp** thường gợi ý duplicate export/ingestion; hai Span IDs khác nhau với cùng boundary thường gợi ý duplicate instrumentation.
- **Duplicate metrics** cần được kiểm tra riêng với duplicate spans; metrics logical calls và dependency attempts có thể khác semantics hợp lệ.
- **Không khởi tạo OTel SDK/provider/exporter thứ hai** nếu agent hoặc Spring Boot bridge đã sở hữu pipeline.
- **Tắt selective instrumentation** theo đúng library/boundary; giữ context propagation và metrics cần thiết.
- **Spring AI** có thể phát observations cho ChatClient/model/retrieval tùy version; xem trace runtime trước khi thêm custom spans.
- **Exporter pipeline** nên rõ ràng; tránh gửi cùng spans tới cùng backend qua hai đường.
- **Kiểm thử sau nâng cấp** để phát hiện instrumentation mới và configuration drift.
- **Redaction/cardinality** phải áp dụng cho cả framework, agent, library và manual instrumentation.

Tránh instrumentation trùng giúp trace Spring AI thể hiện đúng số operation, đúng quan hệ và đúng nguồn tạo telemetry. Khi mỗi boundary có owner rõ, logical model/RAG/tool spans được phân biệt với HTTP/JDBC transport spans, exporter có một đường đi thống nhất và metrics được kiểm tra độc lập, nhóm phát triển có thể tin vào latency, error, token/cost và evaluation provenance qua từng phiên bản prompt, model và pipeline.
