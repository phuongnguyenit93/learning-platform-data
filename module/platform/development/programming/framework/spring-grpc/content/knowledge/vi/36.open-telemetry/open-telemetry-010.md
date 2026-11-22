# Kiểm thử propagation

## Mục tiêu bài học

Trong **SPRING_GRPC**, trace context phải đi qua client, HTTP/2 metadata, server interceptor, service, worker executor và downstream RPC để toàn bộ hoạt động của một request được liên kết trong cùng trace. Cấu hình propagation có thể trông đúng khi đọc code nhưng vẫn lỗi khi chạy: client không inject metadata, server không extract, async callback mất context, baggage bị bỏ qua hoặc một instrumentation khác tạo span trùng.

Bài học tập trung vào **kiểm thử propagation**: kiểm tra inject/extract của W3C Trace Context, xác minh quan hệ trace giữa gRPC client/server, bảo toàn OpenTelemetry Context qua executor và callback, kiểm tra baggage, sampling và dữ liệu không hợp lệ, đồng thời phát hiện context leak và instrumentation trùng lặp.

Sau bài này, bạn có thể:

1. Thiết kế test riêng cho propagator và test tích hợp qua gRPC.
2. Xác minh trace ID, span ID, parent-child relationship và sampled flag.
3. Kiểm tra client/server instrumentation trên in-process transport và transport thật.
4. Kiểm tra OTel Context qua executor, CompletableFuture và callback bất đồng bộ.
5. Kiểm tra baggage allowlist, giới hạn kích thước và dữ liệu không tin cậy.
6. Kiểm thử sampling, exporter và hành vi khi trace không được ghi.
7. Phát hiện duplicate spans, context leak và sai correlation giữa request đồng thời.
8. Xây dựng test end-to-end cho propagation mà không phụ thuộc dashboard production.

> **Phạm vi:** Ví dụ dùng OpenTelemetry Java API/SDK, gRPC Java và Spring. API package của gRPC instrumentation phụ thuộc phiên bản instrumentation đang dùng. Các ví dụ in-process kiểm tra interceptor/propagation ở tầng gRPC nhưng không thay thế kiểm thử TLS, ALPN hoặc HTTP/2 qua socket thật.

## 1. Các tầng cần kiểm thử

Propagation không phải một thao tác duy nhất. Một test strategy tốt tách các ranh giới để biết lỗi phát sinh ở đâu.

| Tầng | Điều cần xác minh | Kiểu test |
| --- | --- | --- |
| Propagator | Trace context được inject/extract đúng chuẩn | Unit test với carrier map |
| Client instrumentation | Outbound RPC tạo client span và metadata | gRPC client integration test |
| Server instrumentation | Inbound metadata được extract và tạo server span | gRPC server integration test |
| Parent-child | Client/server spans cùng trace và đúng parent | In-process hoặc socket test |
| Async boundary | Context còn đúng trên worker/callback thread | Executor/CompletableFuture test |
| Baggage | Chỉ key/value được phép được truyền | Propagator/security test |
| Sampling/export | Span được ghi/export theo policy | SDK với in-memory exporter |
| Isolation | Request đồng thời không trộn context | Concurrency test |
| Transport | TLS, HTTP/2, proxy vẫn giữ metadata | Network integration test |

Không nên chỉ kiểm tra rằng traceparent có mặt trong một map rồi kết luận toàn bộ gRPC propagation hoạt động. Cũng không nên chỉ xem dashboard có trace mà bỏ qua việc xác minh parent-child và context trong async task.

## 2. Chuẩn bị OpenTelemetry SDK cho test

Dùng SDK riêng cho test để thu thập span trực tiếp trong bộ nhớ. Artifact testing của OpenTelemetry Java cung cấp InMemorySpanExporter; version cần đồng bộ với OTel SDK và instrumentation trong dự án.

Ví dụ fixture:

```java
InMemorySpanExporter spanExporter =
        InMemorySpanExporter.create();

SdkTracerProvider tracerProvider =
        SdkTracerProvider.builder()
                .setSampler(Sampler.alwaysOn())
                .addSpanProcessor(
                        SimpleSpanProcessor.create(spanExporter))
                .build();

OpenTelemetrySdk openTelemetry =
        OpenTelemetrySdk.builder()
                .setTracerProvider(tracerProvider)
                .setPropagators(
                        ContextPropagators.create(
                                W3CTraceContextPropagator.getInstance()))
                .build();

Tracer tracer =
        openTelemetry.getTracer("spring-grpc-propagation-test");
```

Trong fixture thật, đóng tracerProvider sau test và reset exporter giữa các test. Không dùng GlobalOpenTelemetry.set() lặp đi lặp lại trong cùng JVM nếu test chạy song song; global state có thể làm test phụ thuộc thứ tự. Ưu tiên inject OpenTelemetry instance vào instrumentation và component đang kiểm thử.

Sampler.alwaysOn() giúp test span deterministically được ghi. Khi kiểm tra sampling, tạo SDK fixture riêng với sampler phù hợp thay vì thay sampler global giữa các test.

### 2.1. Dependency test

Dự án thường cần:

- OpenTelemetry API và SDK cùng version.
- OpenTelemetry SDK testing trong test scope để có InMemorySpanExporter.
- gRPC instrumentation tương thích với gRPC Java version đang dùng.
- gRPC in-process transport cho test service/interceptor nếu phù hợp.
- Spring Boot test support nếu cần khởi tạo application context.

Dùng OpenTelemetry BOM hoặc version alignment được dự án chọn. Không ghép tùy ý các phiên bản instrumentation alpha, SDK và API khác nhau; lỗi binary compatibility có thể xuất hiện lúc test hoặc startup.

## 3. Kiểm thử W3C Trace Context inject/extract

W3C Trace Context truyền trace identity qua header chuẩn như traceparent và tracestate. Unit test propagator nên xác minh:

- Context có SpanContext hợp lệ được inject thành traceparent.
- Trace ID và span ID giữ nguyên sau extract.
- Sampled flag được giữ đúng.
- Tracestate được truyền theo semantics của propagator.
- Header sai định dạng không làm ứng dụng crash hoặc được tin như context hợp lệ.

Ví dụ round-trip qua carrier map:

```java
String traceId = "4bf92f3577b34da6a3ce929d0e0e4736";
String spanId = "00f067aa0ba902b7";

SpanContext remoteParent =
        SpanContext.createFromRemoteParent(
                traceId,
                spanId,
                TraceFlags.getSampled(),
                TraceState.getDefault());

Context parentContext =
        Context.root().with(Span.wrap(remoteParent));

Map<String, String> carrier = new HashMap<>();

TextMapPropagator propagator =
        W3CTraceContextPropagator.getInstance();

propagator.inject(
        parentContext,
        carrier,
        (map, key, value) -> map.put(key, value));

Context extracted =
        propagator.extract(
                Context.root(),
                carrier,
                (map, key) -> map.get(key));

SpanContext actual =
        Span.fromContext(extracted).getSpanContext();

assertEquals(traceId, actual.getTraceId());
assertEquals(spanId, actual.getSpanId());
assertTrue(actual.isSampled());
```

Đây là test cho propagator, chưa phải test gRPC. Nó giúp cô lập lỗi format/inject/extract trước khi thêm channel, server và instrumentation.

### 3.1. Kiểm thử context không hợp lệ

Tạo carrier thiếu traceparent, traceparent sai độ dài, version/flags sai hoặc chứa all-zero trace/span ID. Xác minh propagator không tạo SpanContext hợp lệ từ dữ liệu đó và ứng dụng xử lý request theo policy.

Không tự parse traceparent bằng substring trong interceptor nghiệp vụ. Dùng propagator chuẩn để có validation nhất quán. Trace context do caller gửi chỉ dùng cho correlation; không dùng nó làm danh tính hoặc bằng chứng authorization.

## 4. Kiểm thử baggage

Baggage là tập key/value được truyền xuyên service cùng context. Nó không giống span attributes: baggage có thể đi qua nhiều process và làm tăng kích thước metadata trên mỗi hop.

Test baggage nên xác minh:

- Chỉ key được allowlist mới được truyền.
- Không có token, password, email hoặc dữ liệu cá nhân.
- Giá trị được giới hạn độ dài và tổng kích thước.
- Baggage không vượt qua tenant/security boundary ngoài ý muốn.
- Baggage không được dùng thay authentication hoặc authorization.

Nếu ứng dụng bật W3C Baggage propagator, test inject/extract riêng cho baggage và test composite propagator dùng trong runtime. Tạo test với key được phép, key không được phép và value quá dài; xác minh policy lọc trước khi inject.

Không chỉ assert baggage hiện diện ở server. Cần assert key/value đúng và những key nhạy cảm không xuất hiện trong outbound metadata.

## 5. Kiểm thử gRPC client/server propagation

Sau khi propagator unit test đạt, kiểm tra instrumentation trên gRPC call thật. Với gRPC Java instrumentation có API dạng GrpcTelemetry, cấu hình cả client interceptor và server interceptor bằng cùng OpenTelemetry SDK trong test.

Ví dụ cấu trúc in-process:

```java
GrpcTelemetry telemetry = GrpcTelemetry.create(openTelemetry);

ServerServiceDefinition instrumentedService =
        ServerInterceptors.intercept(
                inventoryService,
                telemetry.newServerInterceptor());

Server server =
        InProcessServerBuilder.forName(serverName)
                .directExecutor()
                .addService(instrumentedService)
                .build()
                .start();

ManagedChannel rawChannel =
        InProcessChannelBuilder.forName(serverName)
                .directExecutor()
                .build();

Channel instrumentedChannel =
        ClientInterceptors.intercept(
                rawChannel,
                telemetry.newClientInterceptor());
```

Đây là skeleton minh họa; tên package/artifact và API factory phải khớp phiên bản gRPC instrumentation trong build. Đóng server/channel trong finally hoặc JUnit extension để test không giữ thread/resource.

Tạo parent span trong test, gọi generated stub qua instrumented channel, rồi kết thúc parent span. Sau đó lấy SpanData từ exporter và xác minh:

- Có client span cho outbound call.
- Có server span cho inbound call.
- Client và server span có cùng trace ID.
- Server span parent là client span theo instrumentation semantics.
- Span kind đúng CLIENT/SERVER.
- RPC method/status attributes phù hợp convention của version instrumentation.
- Chỉ có một client/server span cho mỗi attempt được thực hiện.

Không assert span name/attribute theo chuỗi cứng nếu semantic conventions hoặc instrumentation version có thể đổi. Ưu tiên assert SpanKind, trace ID, parent span ID và các thuộc tính contract ổn định.

### 5.1. Kiểm thử quan hệ parent-child

Lọc SpanData theo SpanKind.CLIENT và SpanKind.SERVER. Với một RPC attempt đơn:

```java
SpanData clientSpan = findSingleSpan(
        spanExporter.getFinishedSpanItems(),
        SpanKind.CLIENT);

SpanData serverSpan = findSingleSpan(
        spanExporter.getFinishedSpanItems(),
        SpanKind.SERVER);

assertEquals(
        clientSpan.getTraceId(),
        serverSpan.getTraceId());

assertEquals(
        clientSpan.getSpanId(),
        serverSpan.getParentSpanId());
```

findSingleSpan là helper của test để tìm đúng span theo kind. Nếu có retry, hedging hoặc nhiều outbound calls, số span sẽ khác; test phải phân biệt logical RPC với từng attempt và xác minh quan hệ theo từng call.

## 6. Kiểm thử propagation qua executor

Một RPC có thể offload database hoặc công việc blocking sang worker pool. OTel Context phải được capture ở thread submit và activate trong worker.

Ví dụ:

```java
Context captured = Context.current();
String expectedTraceId =
        Span.current().getSpanContext().getTraceId();

Future<SpanContext> result =
        workerPool.submit(captured.wrap(
                () -> Span.current().getSpanContext()));

SpanContext workerSpan =
        result.get(2, TimeUnit.SECONDS);

assertEquals(
        expectedTraceId,
        workerSpan.getTraceId());
```

Gọi đoạn test khi parent span đang active. Capture expectedTraceId trước khi submit và so sánh với giá trị worker trả về; không đọc Span.current() ở thread test sau khi scope đã đóng rồi dùng nó làm expected value.

### 6.1. Kiểm tra cleanup trên thread pool dùng chung

Dùng single-thread executor để buộc hai task chạy trên cùng một worker:

1. Task A chạy trong OTel Context có span A.
2. Task A hoàn tất và wrapper phải restore context trước đó.
3. Task B chạy không có context request.
4. Xác minh Task B không nhìn thấy span A.
5. Lặp lại với task A ném exception để kiểm tra cleanup trong finally.

Bài test này phát hiện context leak mà test dùng thread mới cho mỗi task thường bỏ sót. Với MDC, kiểm tra trace_id/span_id cũng được khôi phục hoặc xóa sau task.

### 6.2. CompletableFuture và callback

Các stage async phải dùng executor đã bọc OTel Context hoặc được instrument bằng context propagation phù hợp. Test từng ranh giới:

- supplyAsync trên worker pool.
- thenApplyAsync với executor.
- whenComplete/handle callback.
- callback của API async bên ngoài.
- gRPC StreamObserver callback nếu transport/instrumentation không tự duy trì context trong đường chạy đó.

Không giả định stage không async và stage async chạy trên cùng thread. Assert trace ID trong từng stage, đồng thời xác minh worker thread trở về trạng thái ban đầu sau completion.

## 7. Kiểm thử gRPC Context và OTel Context riêng biệt

gRPC Context và OTel Context (OpenTelemetry Context) là hai cơ chế độc lập. Một task có thể giữ OTel span nhưng mất gRPC deadline/cancellation; hoặc giữ gRPC request ID nhưng không có active span.

Test hai chiều:

| Điều kiện | Kỳ vọng |
| --- | --- |
| Chỉ OTel Context được bọc | Span hiện hành được giữ; gRPC Context không được giả định tự giữ |
| Chỉ gRPC Context được bọc | Deadline/request-scoped gRPC values được giữ; OTel span không được giả định tự giữ |
| Cả hai được bọc | Cả hai context hiện diện trong worker |
| Task ném exception | Cả hai context được restore |
| Task kế tiếp trên cùng thread | Không thấy context của request trước |

Khi kết hợp wrapper, xác định rõ context nào được capture ở thời điểm submit và context nào được activate trong worker. Dùng helper wrapper của từng thư viện thay vì tự gán ThreadLocal.

## 8. Kiểm thử sampling và exporter

Không phải mọi trace context hợp lệ đều có span được lưu. Sampling quyết định span nào được record/export; do đó test cần phân biệt propagation với recording.

Các tình huống:

| Sampler / tình huống | Kỳ vọng |
| --- | --- |
| alwaysOn | Span được record và xuất hiện trong in-memory exporter |
| alwaysOff | Span không được export, nhưng ứng dụng không lỗi vì thiếu SpanData |
| ParentBased với sampled parent | Child spans theo parent sampling decision |
| ParentBased với unsampled parent | Child spans thường không được record theo parent decision |
| Exporter lỗi | RPC vẫn xử lý theo policy; lỗi telemetry không làm hỏng business call |
| Reset exporter | Test tiếp theo không thấy spans của test trước |

Test propagation của unsampled context riêng: trace ID có thể được truyền với sampled flag false, dù trace backend không lưu spans. Không viết test khẳng định mọi request đều phải có trace trong backend khi sampler đang drop.

InMemorySpanExporter phù hợp để assert dữ liệu trong unit/integration test. Nó không thay thế test exporter/collector/network pipeline của production. Cần có smoke test để xác minh OTLP exporter, collector và backend nhận dữ liệu đúng.

## 9. Phát hiện duplicate instrumentation

Nếu Java agent và manual gRPC interceptor cùng instrument một RPC, trace có thể có hai client spans hoặc hai server spans cho cùng operation.

Test nên:

1. Khởi động ứng dụng theo đúng cách production bật agent/SDK.
2. Gọi đúng một RPC attempt.
3. Lọc spans theo SpanKind, method và trace ID.
4. Xác minh số client/server spans phù hợp với số attempt.
5. Kiểm tra span parent-child không tạo thêm lớp duplicate.
6. Tắt một instrumentation source và so sánh kết quả nếu có duplication.

Không đồng thời bật nhiều instrumentation cho cùng thư viện mà chưa xác định trách nhiệm. Nếu Java agent đã instrument gRPC tự động, chỉ thêm manual interceptor khi có lý do cụ thể và đã kiểm chứng không trùng.

## 10. Kiểm thử request đồng thời và isolation

Propagation thường thất bại dưới concurrency khi context bị giữ trong singleton, mutable map hoặc ThreadLocal không được cleanup.

Tạo hai request có parent span khác nhau, chạy xen kẽ trên cùng worker pool và xác minh:

- Mỗi server span thuộc đúng trace của client call tương ứng.
- Log trace_id/span_id không bị tráo giữa request.
- Baggage của request A không xuất hiện trong request B.
- Callback hoàn tất vẫn mang context của request ban đầu.
- Exception/cancellation của A không làm thay đổi context B.
- Không có trace context bị lưu trong field của singleton service.

Dùng CountDownLatch, CyclicBarrier hoặc test synchronization primitive để điều khiển interleaving. Tránh dùng sleep dài vì test có thể pass/fail phụ thuộc scheduler.

## 11. Kiểm thử transport thật

In-process transport kiểm tra gRPC call/interceptor behavior nhanh, nhưng không kiểm tra toàn bộ network stack. Cần một số test qua gRPC Netty/socket thật để xác minh:

- HTTP/2 metadata được inject/extract đúng.
- TLS handshake và ALPN h2 không làm mất propagation.
- Proxy/ingress không strip traceparent/tracestate hoặc baggage được phép.
- Channel reconnect/retry vẫn tạo trace theo từng attempt.
- Deadline/cancellation và context vẫn đúng khi network có delay/reset.
- Exporter hoạt động khi ứng dụng chạy với cấu hình profile tương ứng.

Test transport nên dùng port ngẫu nhiên, CA/certificate fixture và timeout có giới hạn. Không dùng plaintext production endpoint hoặc certificate thật trong CI.

## 12. Bảo mật dữ liệu propagation

Trace context và baggage có thể đến từ caller bên ngoài. Propagation không xác thực nguồn gửi và không tạo trust boundary.

Test bảo mật cần bao gồm:

- Traceparent sai định dạng bị bỏ qua theo propagator semantics.
- Baggage key ngoài allowlist bị loại bỏ.
- Baggage quá lớn bị giới hạn hoặc từ chối theo policy.
- Token/password/PII không được thêm vào baggage.
- Log không ghi raw authorization metadata.
- Trace attributes không chứa payload nhạy cảm.
- Caller không thể dùng trace ID/baggage để vượt authorization.
- Header propagation bị giới hạn theo hop/network policy.

Nếu hệ thống nhận trace context từ public caller, cân nhắc policy về trust, sampling và restart trace ở boundary phù hợp. Dù trace ID không phải secret, caller có thể cố ý tạo trace ID để gây nhầm lẫn correlation hoặc tăng tải telemetry.

## 13. Test helper và assertion nên ổn định

Tránh viết test phụ thuộc quá nhiều vào tên span hoặc thứ tự export nếu SDK có thể hoàn tất spans theo thứ tự khác nhau. Xây dựng helper:

- Lọc SpanData theo SpanKind.
- Tìm span theo method attribute ổn định của instrumentation version.
- Assert trace ID và parent span ID.
- Assert status/error theo semantics.
- Assert span count theo số RPC attempt.
- Assert baggage allowlist và context restoration.
- Reset exporter giữa test.
- Đặt timeout cho mọi Future, stream và server shutdown.

Khi test thất bại, in ra một bản tóm tắt đã lọc gồm span kind, trace ID, span ID, parent span ID, method và status. Không dump toàn bộ attributes nếu có thể chứa dữ liệu nhạy cảm.

## 14. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Carrier unit test pass nhưng gRPC server không có parent | Client/server interceptor chưa đăng ký hoặc instrumentation sai version | Kiểm tra gRPC instrumentation wiring và metadata thực |
| Client/server spans có trace ID khác nhau | Inject/extract không chạy hoặc context bị thay | Kiểm tra propagator, interceptor và outbound metadata |
| Server span không có parent | Header thiếu/sai hoặc server instrumentation không extract | Test traceparent và server interceptor độc lập |
| Async task không có span | OTel Context không được capture/wrap | Dùng Context.wrap tại submit boundary |
| Task B thấy span A | Context không restore sau task | Dùng wrapper chuẩn và test single-thread executor |
| OTel span có nhưng deadline mất | Chỉ bọc OTel Context, không bọc gRPC Context | Propagate hai context riêng |
| Baggage chứa dữ liệu không mong muốn | Không có allowlist/size policy | Filter trước inject và test negative cases |
| Có hai server spans cho một RPC | Java agent và manual interceptor cùng instrument | Chọn một instrumentation path |
| Trace không có trong exporter | Sampler drop hoặc span chưa end | Kiểm tra sampling, scope và span lifecycle |
| Unsampled request bị test coi là lỗi | Test nhầm propagation với recording | Assert sampled flag và không yêu cầu SpanData |
| Test pass in-process nhưng fail staging | TLS/HTTP2/proxy chưa được kiểm tra | Thêm network integration test |
| Test phụ thuộc thứ tự chạy | GlobalOpenTelemetry/exporter state dùng chung | Inject SDK riêng, reset fixture và tránh global mutation |

## 15. Bài tập thực hành

1. Tạo OTel SDK fixture với InMemorySpanExporter và sampler alwaysOn.
2. Viết unit test W3C Trace Context inject/extract bằng carrier map.
3. Thêm test traceparent sai định dạng, sampled flag và tracestate.
4. Tạo in-process gRPC server/channel có OTel client/server interceptors.
5. Gọi generated stub dưới một parent span và assert client/server spans cùng trace ID.
6. Assert server span parent là client span theo instrumentation version.
7. Chuyển một task sang single-thread executor bằng OTel Context.wrap; assert trace ID còn đúng.
8. Chạy task thứ hai trên cùng worker; assert không còn span của task trước.
9. Kết hợp gRPC Context và OTel Context; assert deadline/request values và active span đều được giữ.
10. Kiểm thử baggage allowlist, value length và secret/PII rejection.
11. Chạy test với alwaysOff sampler; xác minh propagation có thể tồn tại dù exporter không có span.
12. Bật Java agent hoặc manual instrumentation theo cấu hình production; assert không có duplicate client/server spans.
13. Chạy hai RPC đồng thời; assert trace/log/baggage isolation.
14. Tạo transport integration test qua TLS/HTTP2 và xác minh traceparent không bị mất.
15. Viết CI test bảo đảm telemetry exporter lỗi không làm hỏng RPC nghiệp vụ theo policy.

### Câu hỏi tự kiểm tra

- Vì sao cần test propagator riêng trước khi test gRPC end-to-end?
- W3C Trace Context inject/extract cần assert những trường nào?
- Vì sao in-process test không chứng minh TLS/HTTP2 propagation?
- Làm sao xác minh client/server spans có cùng trace ID và đúng parent?
- OTel Context.wrap cần được gọi ở ranh giới nào?
- Vì sao cần test trên single-thread executor dùng chung?
- gRPC Context và OTel Context khác nhau ra sao?
- Sampling ảnh hưởng tới propagation và exported spans như thế nào?
- Vì sao baggage cần allowlist và giới hạn kích thước?
- Làm sao phát hiện Java agent và manual instrumentation tạo duplicate spans?
- Khi nào cần test qua proxy/ingress?
- Làm thế nào phân biệt propagation lỗi với exporter/backend lỗi?

## Tài liệu tham khảo

- [OpenTelemetry — Context Propagation](https://opentelemetry.io/docs/concepts/context-propagation/): nguyên tắc inject/extract context.
- [OpenTelemetry — Java API](https://opentelemetry.io/docs/languages/java/api/): Context, Span, Tracer và Propagator.
- [OpenTelemetry Java — SDK](https://opentelemetry.io/docs/languages/java/sdk/): SDK, sampler, processor và exporter.
- [OpenTelemetry Java — Instrumentation](https://opentelemetry.io/docs/zero-code/java/agent/): tự động instrument Java application.
- [OpenTelemetry Java — Testing](https://github.com/open-telemetry/opentelemetry-java/tree/main/sdk/testing): in-memory exporter và test utilities.
- [W3C Trace Context](https://www.w3.org/TR/trace-context/): traceparent/tracestate format và processing.
- [W3C Baggage](https://www.w3.org/TR/baggage/): baggage propagation và header semantics.
- [gRPC — Metadata](https://grpc.io/docs/guides/metadata/): metadata truyền qua RPC.
- [gRPC Java — Context](https://grpc.github.io/grpc-java/javadoc/io/grpc/Context.html): gRPC context, deadline và executor propagation.

**Kết quả mong đợi:** Người học kiểm thử được OpenTelemetry propagation từ W3C carrier tới gRPC client/server, async worker và downstream service; xác minh trace/span parentage, baggage, sampling và exporter; phát hiện duplicate spans/context leak; đồng thời chứng minh propagation hoạt động qua transport thật mà không làm lộ dữ liệu nhạy cảm.
