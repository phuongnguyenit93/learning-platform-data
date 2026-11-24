# Test trace propagation

Một request đi vào Order Service, gọi Inventory Service qua HTTP rồi publish một event để xử lý bất đồng bộ. Khi xem trace, đội vận hành cần thấy các spans thuộc cùng một trace và có quan hệ cha-con hoặc link phù hợp. Nếu trace context bị mất ở HTTP header, message headers hoặc executor boundary, mỗi service có thể tạo trace riêng; latency và lỗi xuyên service trở nên khó điều tra. Test trace propagation xác nhận context được inject, truyền qua transport và extract ở phía nhận đúng cách.

Bài **Test trace propagation** thuộc chương **Testing observability** của module **SPRING_BOOT_OBSERVABILITY**. Module học cách thiết lập observability cho Spring Boot bằng Micrometer Observation, metrics, logs và distributed tracing; hiểu context propagation, tag/cardinality, exporter, sampling và liên kết các tín hiệu để điều tra lỗi, độ trễ và hành vi ứng dụng trong môi trường thực.

> **Nguyên tắc:** Test cả wire format lẫn framework integration. Với W3C Trace Context, kiểm tra traceparent/tracestate được inject và extract; kiểm tra trace ID được giữ nguyên và span ID thay đổi theo span mới. Với messaging, kiểm tra headers/context được truyền và consumer span có parent/link đúng semantics. Không assert ID ngẫu nhiên bằng literal cố định, và không đưa PII/secrets vào baggage.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:
1. Giải thích trace context propagation giữa process boundaries.
2. Phân biệt trace ID, span ID, parent span và tracestate.
3. Kiểm tra W3C traceparent/tracestate injection và extraction.
4. Viết unit tests cho propagator và integration tests cho Spring Boot HTTP clients/servers.
5. Kiểm tra propagation qua messaging headers.
6. Xác nhận parent-child hoặc span links theo semantics của transport.
7. Kiểm tra baggage allowlist và privacy constraints.
8. Kiểm tra context propagation qua executor và reactive boundaries.
9. Hiểu sampling và lý do trace có thể không được export dù headers được truyền.
10. Dùng test tracer/in-memory exporter để assert spans mà không cần backend thật.
11. Kiểm tra lỗi malformed/missing headers và tạo trace mới khi không có parent.
12. Tránh test flaky, shared tracing state và duplicate spans.

## 2. Trace context propagation là gì?

Distributed tracing gắn các operations ở nhiều process vào cùng một trace. Khi service A gọi service B, A truyền context qua transport; B extract context để tạo span tiếp nối.

W3C Trace Context thường dùng:
- traceparent: version, trace ID, parent span ID và trace flags.
- tracestate: vendor-specific tracing state.
- baggage: application-defined key/value context được propagate riêng.

Trace ID nhận diện toàn bộ trace. Mỗi span có span ID riêng. Span con giữ trace ID của parent nhưng có span ID mới và parent span ID trỏ về span gọi nó.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant A as Order Service
    participant B as Inventory Service
    C->>A: HTTP request
    Note over A: Server span A
    A->>B: HTTP + traceparent
    Note over B: Extract context
    Note over B: Client/server span B
    B-->>A: HTTP response
    A-->>C: HTTP response
~~~

Sơ đồ minh họa cùng trace qua HTTP. Implementation có thể tạo client span ở A và server span ở B; cả hai đều có span IDs riêng.

## 3. Phân biệt trace ID, span ID và parent

| Trường | Ý nghĩa | Khi propagation |
|---|---|---|
| trace ID | Định danh trace xuyên nhiều services | Được giữ nguyên |
| span ID | Định danh một span cụ thể | Span mới có ID mới |
| parent span ID | Span trực tiếp tạo ra span hiện tại | Trỏ tới span caller theo propagation model |
| trace flags | Sampling/trace flags theo W3C format | Được truyền theo traceparent |
| tracestate | Vendor-specific state | Được truyền nếu propagator hỗ trợ |
| baggage | Context key/value ứng dụng | Chỉ propagate theo policy |

Một test chỉ kiểm tra trace ID giống nhau chưa đủ. Cần kiểm tra span ID mới khác parent span ID và quan hệ parent chính xác.

## 4. W3C Trace Context headers

Ví dụ traceparent hợp lệ có dạng:

~~~http
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
tracestate: vendor=value
~~~

Cấu trúc traceparent:
- Version: 2 hex characters.
- Trace ID: 32 hex characters, không được toàn số 0.
- Parent ID: 16 hex characters, không được toàn số 0.
- Trace flags: 2 hex characters.

Không tự parse header bằng substring trong production code nếu đã có propagator chuẩn. Dùng W3C propagator do tracing bridge/SDK cung cấp để xử lý validation, version và invalid context.

## 5. Kiểm thử propagator độc lập

Unit test propagator nên kiểm tra inject/extract mà không cần Spring context hay network.

Test concept:
1. Tạo current trace context có trace ID và span ID đã biết.
2. Gọi propagator inject vào carrier map/header giả.
3. Assert traceparent có cấu trúc hợp lệ.
4. Extract context từ carrier.
5. Assert trace ID được giữ nguyên.
6. Assert span/parent context phù hợp với context đã inject.
7. Test tracestate và baggage nếu được bật.

Pseudocode minh họa:

~~~java
Map<String, String> carrier = new HashMap<>();
propagator.inject(context, carrier, Map::put);

String traceparent = carrier.get("traceparent");
assertThat(traceparent).matches(
        "00-[0-9a-f]{32}-[0-9a-f]{16}-[0-9a-f]{2}");
~~~

Đây là pseudocode vì API inject/extract cụ thể phụ thuộc Micrometer Tracing bridge hoặc OpenTelemetry SDK. Test dùng API của implementation đang cài; đừng tạo một propagator giả chỉ để test chính logic tự viết.

## 6. Kiểm thử extraction từ inbound HTTP

Server nhận traceparent từ request header. Integration test nên:
- Gửi HTTP request có traceparent hợp lệ.
- Xác nhận server span dùng trace ID trong header.
- Xác nhận span ID server khác parent span ID được truyền.
- Xác nhận server span có remote parent theo tracing implementation.
- Xác nhận response vẫn hoạt động dù tracestate không có.

Có thể dùng MockMvc/WebTestClient hoặc random-port test server tùy stack. Nếu kiểm tra servlet filter/server instrumentation thực tế, test qua HTTP server embedded sẽ bao phủ nhiều wiring hơn MockMvc slice.

Ví dụ request:

~~~http
GET /orders/42 HTTP/1.1
Host: localhost
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
~~~

Assert trace ID bằng giá trị đã truyền và kiểm tra span relationship trong test reporter. Không yêu cầu span ID server bằng ID của caller; nó phải là ID mới.

## 7. Kiểm thử outbound HTTP injection

Khi Order Service gọi Inventory Service, client instrumentation phải inject context vào outbound request.

Một integration test có thể dùng MockWebServer/WireMock hoặc local HTTP server:
1. Tạo inbound request có traceparent.
2. Trong handler, gọi RestClient/RestTemplate/WebClient được instrument.
3. Test server nhận outbound request và ghi lại headers.
4. Assert outbound traceparent chứa cùng trace ID.
5. Assert parent span ID phản ánh client span theo propagation model.
6. Assert không có baggage ngoài allowlist.

Ví dụ header kỳ vọng:

~~~text
Inbound trace ID: 4bf92f3577b34da6a3ce929d0e0e4736
Outbound trace ID: 4bf92f3577b34da6a3ce929d0e0e4736
Outbound span ID: generated child span ID
~~~

Không hardcode child span ID. So sánh quan hệ và định dạng, không so chuỗi random với fixture cố định.

## 8. Spring Boot tracing test setup

Spring Boot tracing auto-configuration cần Micrometer Tracing bridge và exporter phù hợp. Trong test, có thể cấu hình in-memory exporter/reporter hoặc test tracer được bridge cung cấp để thu spans.

Các điều cần xác minh:
- Tracing bridge hiện diện (ví dụ Brave hoặc OpenTelemetry bridge).
- Tracer được auto-configure trong ApplicationContext.
- ObservationRegistry có tracing observation handler.
- HTTP client/server instrumentation đang được bật.
- Sampling probability cho test không loại trace cần kiểm tra.
- Test exporter/reporter nhận span khi span kết thúc.

Không giả định chỉ thêm spring-boot-starter-actuator là có tracing backend. Cần dependency bridge/exporter và cấu hình tương ứng với Spring Boot version.

### 8.1 Test với test reporter

Nếu dùng Brave, test utilities có thể cung cấp TestSpanHandler/FinishedSpan collection; với OpenTelemetry bridge, dùng InMemorySpanExporter hoặc SpanExporter test double phù hợp version. API cụ thể khác nhau, nhưng assertions tương tự:
- Span name.
- Trace ID.
- Span ID.
- Parent span ID.
- Kind (server/client/consumer/producer).
- Attributes/events/status.
- Start/end lifecycle.

## 9. Kiểm thử messaging propagation

Messaging propagation truyền context trong message headers/metadata thay vì HTTP headers. Producer inject trace context; consumer extract context và tạo consumer span.

~~~mermaid
sequenceDiagram
    participant P as Order Producer
    participant Q as Broker
    participant C as Inventory Consumer
    P->>Q: Publish message + trace headers
    Note over Q: Broker giữ headers
    Q->>C: Deliver message
    Note over C: Extract trace context
    C->>C: Process message span
~~~

Test cần xác nhận:
- Producer span được tạo quanh publish.
- Message headers chứa traceparent hoặc format mà integration dùng.
- Consumer extract context.
- Consumer span có cùng trace ID hoặc link theo messaging semantic convention.
- Retry/redelivery không tạo context sai hoặc nối nhầm parent.
- Batch consume xử lý links/parent relationships theo integration behavior.

Không tự khẳng định consumer luôn là direct child của producer. Một số messaging conventions dùng span links, đặc biệt với batch processing hoặc message được xử lý độc lập. Assert theo semantics của Spring Kafka/AMQP integration và convention version đang dùng.

## 10. Kiểm thử baggage propagation và privacy

Baggage không giống traceparent. Trace context cần thiết để nối spans; baggage là metadata ứng dụng và có thể được forward qua nhiều downstream services.

Test nên:
1. Tạo baggage có key được allowlist, ví dụ tenant.tier=business.
2. Thêm key không được phép, ví dụ customer.email.
3. Inject vào outbound carrier.
4. Assert chỉ key được phép được propagate.
5. Assert value được normalize và giới hạn chiều dài.
6. Assert không có token, cookie, email hoặc account identifier trong headers/attributes.

Ví dụ policy:
- Cho phép tenant.tier với tập free/business/enterprise nếu privacy policy chấp thuận.
- Cho phép request.class với tập bounded.
- Loại customer.email, user.id, authorization và session token.

Baggage có thể trở thành span attributes hoặc được forward xa hơn tùy instrumentation. Không đưa PII/secrets vào baggage chỉ vì test hiện tại không export chúng.

## 11. Context propagation qua executor và async

ThreadLocal context không tự động xuất hiện trên thread khác. Khi code chuyển sang executor, context có thể mất nếu không dùng Micrometer Context Propagation hoặc integration phù hợp.

Ví dụ kiến trúc:

~~~mermaid
flowchart LR
    A["Request thread"] --> B["Capture context"]
    B --> C["Executor task"]
    C --> D["Restore context"]
    D --> E["Child span / Observation"]
~~~

Test nên:
- Tạo parent span/Observation trên request thread.
- Submit task qua executor đã cấu hình context propagation.
- Trong task, tạo child span/Observation.
- Assert cùng trace ID và parent relationship.
- Kết thúc task và xác nhận scope được restore/clear.
- Chạy thêm task khác để bảo đảm context không rò sang thread được tái sử dụng.

Dùng Future/latch để đợi task hoàn tất. Không dùng Thread.sleep làm đồng bộ test. Kiểm tra TaskDecorator, ContextSnapshot hoặc framework integration thực tế thay vì giả định executor tự propagate.

## 12. Reactive context propagation

Trong Reactor, execution có thể chuyển thread qua publishOn/subscribeOn. Context tracing cần đi theo Reactor Context và instrumentation phù hợp; ThreadLocal đơn thuần không phải contract an toàn cho mọi pipeline.

Test:
1. Bắt đầu trace context.
2. Tạo reactive pipeline có publishOn/subscribeOn.
3. Tạo child Observation/span trong operator hoặc service được gọi.
4. Assert child cùng trace ID.
5. Kiểm tra context được khôi phục đúng khi pipeline complete/error/cancel.
6. Subscribe nhiều lần để xác nhận mỗi subscription có lifecycle đúng.

Dùng Reactor Test StepVerifier để đồng bộ và assert terminal signals. Tránh kiểm tra thread name như bằng chứng duy nhất cho context propagation.

## 13. Missing, malformed và untrusted trace headers

Inbound headers đến từ client bên ngoài có thể thiếu, malformed hoặc bị giả mạo. Test các trường hợp:
- Không có traceparent: server tạo trace mới theo policy.
- Traceparent sai format: propagator bỏ qua invalid context và tạo context phù hợp.
- Trace ID hoặc parent ID toàn số 0: header không hợp lệ.
- Version không được hỗ trợ: xử lý theo W3C version rules.
- Tracestate quá dài/không hợp lệ: validate hoặc bỏ theo propagator.
- Baggage chứa key/value không allowlist: filter/remove.
- Remote sampled flag = 0: sampling policy có thể không export trace.

Không tin trace headers như identity hoặc authorization. Trace context chỉ phục vụ correlation; không dùng nó để cấp quyền truy cập hoặc quyết định tenant identity.

## 14. Sampling và test expectations

Trace context propagation và sampling là hai việc liên quan nhưng khác nhau:
- Context có thể được inject/extract dù trace không được export.
- Sampled flag có thể ảnh hưởng head sampling ở downstream.
- Parent-based sampler có thể tôn trọng quyết định upstream.
- Tail sampling có thể quyết định sau khi Collector nhận spans.
- Test có thể bị flaky nếu sampling probability thấp.

Trong integration test cần cấu hình sampler deterministic hoặc sampling probability 100% cho test scope. Không thay sampling production policy chỉ để làm test pass. Khi test propagation headers, assert headers độc lập với việc exporter có lưu span hay không.

## 15. Kiểm thử toàn luồng nhiều service

Một test có thể khởi chạy Order API và Inventory API trên random ports:
1. Gửi inbound request với traceparent fixture.
2. Order server tạo server span.
3. Order gọi Inventory qua HTTP client instrumented.
4. Inventory nhận và extract trace context.
5. Inventory tạo server span và trả response.
6. Order hoàn tất server span.
7. Test reporter thu các spans đã kết thúc.
8. Assert cùng trace ID, span IDs khác nhau và parent relationships đúng.

Có thể thêm messaging path để kiểm tra producer/consumer. Tuy nhiên, test nhiều process/container nên dành cho contract/integration quan trọng; unit tests propagator nhanh hơn và dễ chẩn đoán.

## 16. Troubleshooting

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Mỗi service có trace ID khác | Header không inject/extract hoặc client chưa instrument | Kiểm tra traceparent ở từng boundary |
| Trace ID giống nhưng span không có parent | Parent context bị mất hoặc span được tạo root | Kiểm tra current context và extraction |
| Outbound request thiếu traceparent | Tracing bridge/client instrumentation chưa bật | Kiểm tra client bean và observation handler |
| Server span không dùng inbound trace ID | Header malformed, propagator khác format hoặc filter xóa header | Kiểm tra raw headers và propagator |
| Messaging consumer trace tách rời | Producer không inject message headers hoặc consumer không extract | Kiểm tra broker record headers |
| Async child span thành root | Context không propagate qua executor | Cấu hình Context Propagation/TaskDecorator |
| Reactive span mất parent sau scheduler switch | Reactor context instrumentation không hoạt động | Kiểm tra Reactor integration và context mode |
| Không có span trong test reporter | Sampling drop, span chưa end hoặc exporter chưa wired | Dùng deterministic sampler và flush/await |
| Baggage có PII | Baggage không có allowlist | Filter tại source và test canary |
| Trace bị nối sai giữa requests | ThreadLocal/context không được clear hoặc carrier reuse | Kiểm tra scope close và carrier lifecycle |
| Batch consumer parent không như dự kiến | Messaging convention dùng links | Assert span links theo integration semantics |
| Test flaky | Sampling ngẫu nhiên, shared tracer hoặc sleep | Registry/reporter riêng, deterministic sampling và latch |

## 17. Playbook: xác minh trace qua HTTP và messaging

**Tình huống:** Order request gọi Inventory qua HTTP, sau đó phát event; trace backend cho thấy consumer không nối vào trace ban đầu.

1. Gửi request với traceparent fixture hợp lệ vào Order API.
2. Xác nhận Order server span dùng trace ID fixture.
3. Thu outbound HTTP request tại test server và kiểm tra traceparent.
4. Xác nhận Inventory server span dùng cùng trace ID và parent/client relationship đúng.
5. Thu message producer headers trước khi publish.
6. Xác nhận trace context được encode trong message headers.
7. Consume message và xác nhận consumer span dùng context hoặc link đúng convention.
8. Kiểm tra baggage chỉ chứa keys được allowlist.
9. Kiểm tra sampling decision và test reporter có nhận spans đã kết thúc.
10. Nếu trace bị tách, xác định boundary đầu tiên mất header/context và sửa đúng instrumentation ở boundary đó.

Đừng chỉ nhìn trace UI cuối cùng. Thu headers và spans ở từng boundary để xác định context bị mất tại producer, transport, consumer hay exporter.

## 18. Bài tập tự kiểm tra

**Bài 1 — Trace identifiers.** Khi A gọi B, trường nào giữ nguyên và trường nào phải đổi trong span mới?

**Bài 2 — HTTP injection.** Làm thế nào chứng minh RestClient/RestTemplate đã inject traceparent vào outbound request?

**Bài 3 — Messaging.** Vì sao không luôn assert consumer span là direct child của producer span?

**Bài 4 — Baggage.** Hãy thiết kế test chứng minh customer.email không được propagate nhưng tenant.tier được allowlist.

**Bài 5 — Async.** Vì sao ThreadLocal context có thể mất khi task chạy trên executor thread khác? Nên kiểm tra cơ chế nào?

**Bài 6 — Sampling.** Vì sao có traceparent hợp lệ nhưng test exporter không nhận span?

**Bài 7 — Invalid headers.** Server nên xử lý traceparent malformed thế nào? Vì sao trace headers không phải thông tin xác thực?

**Bài 8 — Span relationship.** Ngoài trace ID, cần assert gì để xác nhận parent-child đúng?

### Gợi ý trả lời

1. Trace ID giữ nguyên; span ID mới khác và parent span ID trỏ tới span caller theo propagation model.
2. Dùng local mock HTTP server, gửi request qua client bean được instrument, capture request headers và assert traceparent hợp lệ/cùng trace ID.
3. Batch processing hoặc messaging semantics có thể dùng span links; phụ thuộc convention/integration.
4. Inject baggage có hai key, assert carrier chỉ có tenant.tier với giá trị allowlisted và không có customer.email.
5. ThreadLocal không tự đi theo thread khác; kiểm tra Micrometer Context Propagation, TaskDecorator hoặc integration Reactor.
6. Sampling có thể không chọn trace, span chưa end, hoặc exporter/reporter chưa được cấu hình/flush.
7. Bỏ qua invalid context và tạo trace mới theo policy; headers có thể do caller tùy ý gửi nên không được dùng cho authorization.
8. Parent span ID, span ID khác nhau, span kind và quan hệ/link theo transport semantics.

## 19. Tài liệu tham khảo chính thức

- [W3C Trace Context](https://www.w3.org/TR/trace-context/): traceparent, tracestate và propagation format.
- [W3C Baggage](https://www.w3.org/TR/baggage/): baggage header và propagation behavior.
- [Spring Boot — Tracing](https://docs.spring.io/spring-boot/reference/actuator/tracing.html): Micrometer Tracing, propagation và sampling configuration.
- [Micrometer Tracing](https://docs.micrometer.io/tracing/reference/): tracer bridges, span lifecycle và propagation.
- [Micrometer Context Propagation](https://docs.micrometer.io/context-propagation/reference/): context capture, restore và thread boundary.
- [Spring for Apache Kafka — Micrometer Observation](https://docs.spring.io/spring-kafka/reference/kafka/micrometer.html): producer/consumer observation và tracing headers.
- [Spring AMQP — Micrometer Observation](https://docs.spring.io/spring-amqp/reference/amqp/receiving-messages/async-annotation-driven/enable-micrometer.html): listener observation và propagation integration.
- [OpenTelemetry — Context Propagation](https://opentelemetry.io/docs/concepts/context-propagation/): context qua process boundaries.
- [OpenTelemetry Semantic Conventions — Messaging](https://opentelemetry.io/docs/specs/semconv/messaging/): messaging spans, parent/link semantics và attributes.
- [Spring Framework — REST Clients](https://docs.spring.io/spring-framework/reference/integration/rest-clients.html): HTTP client integration points.

**Ghi nhớ:** Test trace propagation ở từng boundary: inbound extraction, outbound injection, broker headers, consumer extraction và async context. Trace ID được giữ nguyên trong cùng trace, span ID thay đổi theo operation; kiểm tra parent hoặc links theo HTTP/messaging semantics. Baggage cần allowlist và privacy assertions. Sampling có thể làm span không được export dù context vẫn được truyền. Dùng test tracer/reporter và local transport để xác minh headers cùng span relationships mà không phụ thuộc backend production.

