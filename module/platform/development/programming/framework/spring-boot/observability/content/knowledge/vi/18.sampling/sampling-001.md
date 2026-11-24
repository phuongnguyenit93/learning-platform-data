# Trace sampling là gì trong Spring Boot Observability?

Trong chương **Sampling** của module **SPRING_BOOT_OBSERVABILITY**, *trace sampling* là kỹ thuật chọn một phần trace để ghi nhận và xuất đi, thay vì lưu mọi trace của mọi request. Sampling giúp kiểm soát lượng spans, băng thông, CPU, bộ nhớ đệm và chi phí lưu trữ, đồng thời vẫn giữ đủ dữ liệu để điều tra lỗi, độ trễ và hành vi của ứng dụng.

Một dịch vụ Spring Boot có thể nhận hàng chục nghìn request mỗi phút. Nếu mỗi request tạo nhiều spans ở HTTP server, business observations, HTTP client, database và messaging, tổng số spans sẽ tăng nhanh theo lưu lượng và độ sâu của call graph. Sampling đưa ra một chính sách chọn trace; nó **không phải** là cách tắt metrics, không phải cơ chế xóa log, cũng không bảo đảm mọi trace lỗi đều được giữ.

Bài học thuộc module **SPRING_BOOT_OBSERVABILITY**, tập trung vào Micrometer Observation, metrics, logs và distributed tracing: hiểu trace/span, sampling decision, head-based và tail-based sampling, parent-based sampling, cấu hình xác suất trong Spring Boot, propagation, giới hạn và cách xác minh kết quả trên môi trường thực.

## 1. Trace sampling giải quyết vấn đề nào?

Một trace có thể chứa nhiều spans. Ví dụ, một request checkout đi qua HTTP server, bước nghiệp vụ, hai lời gọi database và một HTTP client tới payment service:

```text
POST /checkout
  └─ order.confirm
       ├─ inventory.reserve
       │    └─ database query
       └─ payment.authorize
            └─ HTTP POST payment-provider
```

Nếu một request tạo sáu spans, 10.000 request có thể tạo khoảng 60.000 spans trong cửa sổ tương ứng (chưa tính retries, messaging và spans của các thư viện khác). Với lưu lượng cao, giữ toàn bộ trace có thể làm tăng:

- Dung lượng export qua mạng và áp lực lên collector.
- CPU để tạo, xử lý, serialize và gửi spans.
- Bộ nhớ queue/buffer của SDK, exporter và collector.
- Chi phí ingest, index, truy vấn và retention ở tracing backend.

Sampling cho phép chọn trace đại diện để quan sát. Ví dụ, lấy mẫu xác suất 10% có thể giảm đáng kể lượng spans xuất so với ghi toàn bộ, nhưng đổi lại một số request riêng lẻ không có trace đầy đủ ở backend.

**Sampling là một sự đánh đổi giữa chi phí và khả năng quan sát.** Tỷ lệ thấp quá có thể bỏ lỡ sự cố hiếm; tỷ lệ cao quá có thể vượt ngân sách. Chính sách cần xét lưu lượng, độ quan trọng của dịch vụ, yêu cầu điều tra, SLO, khả năng backend và mức nhạy cảm dữ liệu.

## 2. Trace, span và sampling decision

**Trace** đại diện cho một hành trình xử lý phân tán. **Span** đại diện cho một đơn vị công việc trong hành trình đó. Các spans có chung Trace ID và có quan hệ parent-child hoặc links. Sampling thường được quyết định ở cấp trace; các spans trong cùng trace cần được xử lý theo chính sách nhất quán để trace không bị thiếu những đoạn quan trọng một cách ngẫu nhiên.

| Khái niệm | Ý nghĩa |
| --- | --- |
| Trace ID | Định danh trace xuyên nhiều service |
| Span ID | Định danh một span cụ thể |
| Parent span | Span tạo ngữ cảnh cha cho span tiếp theo |
| Sampling decision | Chọn ghi nhận/xuất trace theo chính sách |
| Recording span | Span đang được SDK ghi nhận và có thể xử lý/export |
| Non-recording span/context | Context có thể tiếp tục propagation nhưng span không được ghi như recording span |
| Export | Gửi span data đã ghi nhận tới collector/backend |

**Tạo context không đồng nghĩa với export span.** Một request có thể có Trace ID hợp lệ để downstream tiếp tục propagation, nhưng quyết định sampling có thể khiến spans không được ghi hoặc không được xuất. Tương tự, span được recording vẫn có thể không tới backend vì exporter, mạng, collector hoặc backend gặp lỗi.

## 3. Head-based sampling là gì?

**Head-based sampling** quyết định có ghi nhận trace gần thời điểm bắt đầu trace, thường khi span gốc được tạo. Quyết định này thường dựa trên thông tin đã có ở đầu request như Trace ID, parent context, service hoặc attributes ban đầu.

```text
Request bắt đầu
      |
      v
Tracer tạo root span/context
      |
      v
Head sampler quyết định
      |
      +---- sampled ----> ghi các spans theo policy
      |                         |
      |                         v
      |                      processor/exporter
      |
      +---- not sampled --> context có thể tiếp tục propagation
                            nhưng spans không được export theo trace
```

Ưu điểm của head sampling:

- Quyết định sớm, dễ triển khai ở từng service.
- Giảm phần lớn công việc recording/export ngay từ đầu.
- Ít cần giữ toàn bộ trace trong bộ nhớ để chờ quyết định cuối.
- Dễ áp dụng chính sách xác suất hoặc parent-based trong SDK.

Giới hạn:

- Quyết định xảy ra trước khi biết kết quả cuối cùng của request.
- Một request được chọn ở đầu có thể thành công bình thường; một request bị bỏ có thể kết thúc bằng lỗi hiếm hoặc rất chậm.
- Nếu các service không tuân theo parent sampling context, trace phân tán có thể bị chia: service này ghi spans, service khác không ghi.

Head sampling phù hợp làm chính sách nền khi lưu lượng lớn và cần giảm chi phí ở nguồn phát sinh. Tuy nhiên, nó không thể biết chắc request sẽ lỗi trong tương lai tại thời điểm chọn.

## 4. Parent-based sampling và sampled flag

Trong distributed tracing, sampling decision có thể được truyền cùng trace context. Với W3C Trace Context, header `traceparent` có trường flags:

```text
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
             |  |                                |                |
             |  Trace ID                         Parent Span ID   flags
             version
```

Trong ví dụ version `00`, bit thấp nhất của flags thể hiện sampled flag: `01` biểu thị sampled bit được bật; `00` biểu thị bit này không bật. Không được diễn giải các bit khác tùy tiện hoặc dùng flags như cơ chế phân quyền.

**Parent-based sampler** tôn trọng quyết định sampling từ parent context theo các nhánh cấu hình cho local/remote parent đã sampled hoặc not-sampled. Nhờ vậy, nếu service A chọn một trace, service B có thể tiếp tục ghi nhận các spans con của cùng trace; nếu parent đã bị loại, downstream cũng thường tuân theo quyết định đó.

Ví dụ trong OpenTelemetry SDK:

```java
Sampler sampler = Sampler.parentBased(
        Sampler.traceIdRatioBased(0.10));
```

Ý nghĩa tổng quát:

- Với trace mới không có parent, sampler xác suất quyết định khoảng 10%.
- Với trace có parent, parent-based sampler thường tuân theo sampled decision của parent ở các nhánh mặc định.
- Có thể tùy chỉnh sampler cho remote/local parent sampled/not-sampled nếu có nhu cầu đặc biệt, nhưng cần hiểu tác động tới tính nhất quán trace.

Một service downstream không nên tự ý đổi trace not-sampled thành sampled nếu mục tiêu là giữ quyết định đồng nhất xuyên hệ thống. Ngược lại, một số hệ thống có chiến lược nâng cấp quyết định ở tầng collector (tail sampling) cần giữ đủ dữ liệu từ đầu theo cơ chế chuyên biệt; không thể đạt điều này chỉ bằng việc bỏ qua parent flag trong từng service.

## 5. Sampling xác suất trong Spring Boot với Micrometer Tracing

Với các phiên bản Spring Boot hỗ trợ Micrometer Tracing auto-configuration, có thể cấu hình tỷ lệ sampling trong `application.yml`:

```yaml
spring:
  application:
    name: orders-service

management:
  tracing:
    sampling:
      probability: 0.10
```

Giá trị `0.10` là ví dụ: sampling xác suất 10% cho các trace mới theo implementation/policy đang dùng. Nó không có nghĩa hệ thống sẽ giữ chính xác một trong mỗi mười request trong mọi cửa sổ thời gian; sampling xác suất có thể dao động đáng kể với tập request nhỏ.

Một số thế hệ Spring Boot/Micrometer sử dụng property dưới namespace `management.tracing.sampling.probability`; cần kiểm tra đúng phiên bản dự án và bridge đang cài. Property này điều khiển tracing sampling theo auto-configuration, **không phải** tỷ lệ scrape metrics của Prometheus và cũng không đặt log sampling.

Nếu dự án tự cấu hình OpenTelemetry SDK bằng tay thay vì để Spring Boot sở hữu tracer, sampler phải được cấu hình trên `SdkTracerProvider` tương ứng. Tránh đồng thời cấu hình một sampler qua Spring Boot và một `SdkTracerProvider` độc lập mà instrumentation thực tế không sử dụng.

### Các lựa chọn tỷ lệ ban đầu

| Môi trường/mục tiêu | Ví dụ policy | Lưu ý |
| --- | --- | --- |
| Local development | 1.0 (100%) | Thuận tiện debug, chỉ dùng khi tải nhỏ |
| Integration/staging | 0.5 hoặc 1.0 | Tùy khả năng backend và dữ liệu test |
| Production có lưu lượng cao | 0.01–0.10 | Là điểm bắt đầu thử nghiệm, không phải quy tắc chung |
| Một service quan trọng, tải thấp | Có thể cao hơn | Cân đối chi phí và giá trị điều tra |

Không đặt tỷ lệ production chỉ theo thói quen. Đo spans/request, số requests/giây, chi phí ingest và tần suất sự cố hiếm trước khi chọn.

## 6. Tail-based sampling khác gì?

**Tail-based sampling** trì hoãn quyết định giữ hay bỏ trace cho tới khi collector hoặc một thành phần phía sau đã nhận đủ (hoặc đủ nhiều) spans của trace. Vì vậy, policy có thể dựa trên kết quả quan sát sau xử lý:

- Giữ trace có status lỗi.
- Giữ trace có latency vượt ngưỡng.
- Giữ trace từ service/route quan trọng.
- Lấy mẫu tỷ lệ nhỏ của các trace thành công bình thường.

```text
Application services
     |
     +--> gửi recording spans (qua exporter)
                  |
                  v
             OTel Collector
                  |
                  v
          tail-sampling processor
                  |
          +-------+--------+
          |                |
      error/slow         normal
       keep              sample
          |                |
          +-------+--------+
                  |
                  v
          tracing backend
```

Ưu điểm: có thể ưu tiên trace lỗi/chậm mà không cần biết kết quả ở đầu request. Hạn chế:

1. **Collector phải nhận được các spans cần thiết** trước khi quyết định. Nếu SDK head-sample bỏ trace trước khi export, tail sampler không thể khôi phục spans đã không gửi.
2. Phải gom các spans cùng Trace ID về cùng một sampling decision point; phân tán hoặc thiếu spans khiến policy không thấy toàn bộ trace.
3. Collector phải giữ trạng thái trace trong bộ nhớ trong một cửa sổ chờ; lưu lượng cao và trace kéo dài có thể tạo áp lực memory/queue.
4. Cần cấu hình decision wait, expected trace duration, số trace đồng thời và overflow strategy.
5. Chính sách “giữ tất cả lỗi” chỉ giữ được lỗi mà collector nhận được và có thể nhận diện qua status/attributes; không phải mọi lỗi nghiệp vụ đều tự động có span status ERROR.

Tail sampling thường được thực hiện tại OpenTelemetry Collector với processor phù hợp. Đây là cấu hình phía collector, không được bật chỉ bằng property `management.tracing.sampling.probability` của Spring Boot.

## 7. So sánh head-based và tail-based sampling

| Tiêu chí | Head-based | Tail-based |
| --- | --- | --- |
| Thời điểm quyết định | Đầu trace | Sau khi collector nhận spans |
| Có biết trace bị lỗi/chậm về sau? | Thường không | Có thể, nếu spans/status/latency đã tới collector |
| Giảm tải tại ứng dụng | Mạnh, vì trace bị loại sớm | Thường thấp hơn; ứng dụng vẫn phải xuất dữ liệu tới collector |
| Yêu cầu bộ nhớ collector | Thấp hơn | Cao hơn do phải giữ trace chờ quyết định |
| Tính nhất quán xuyên service | Dựa vào parent-based propagation | Cần gom spans theo Trace ID và quyết định tập trung |
| Phù hợp | Sampling xác suất nền, hệ thống tải cao | Ưu tiên lỗi/slow traces và policy dựa trên kết quả |
| Hạn chế chính | Có thể bỏ lỡ trace lỗi hiếm | Tốn tài nguyên collector và cần đủ spans |

Hai kỹ thuật có thể được phối hợp: head sampling với tỷ lệ cao hơn 0 nhưng thấp hơn 1 để giảm bớt tải, rồi tail sampling lựa chọn trong tập spans đã nhận; nhưng nếu head sampling quá thấp, tail collector chỉ được quyền chọn trong phần trace còn lại. Khi yêu cầu giữ gần như mọi lỗi, phải thiết kế đường ingest sao cho lỗi có cơ hội tới collector.

## 8. Sampling ảnh hưởng metrics, logs và traces như thế nào?

Sampling tracing không đồng nghĩa với sampling mọi telemetry.

| Tín hiệu | Ảnh hưởng thường gặp khi trace bị sampled out |
| --- | --- |
| Traces | Các spans recording/export từ trace đó thường không được gửi tới backend theo head sampling |
| Metrics | Metric handlers của Micrometer có thể vẫn ghi counter/timer/gauge độc lập |
| Logs | Ứng dụng vẫn ghi log theo cấu hình logging; log có thể thiếu correlation span hoặc chứa context không recording tùy implementation |
| Baggage/propagation | Context vẫn có thể được truyền; không suy ra sampled flag luôn quyết định mọi thông tin context biến mất |

Ví dụ: `http.server.requests` vẫn tăng và `payment.authorizations` vẫn ghi nhận kết quả success/error, nhưng trace của một request thành công có thể không xuất do sampling. Điều đó bình thường nếu metric pipeline hoạt động độc lập.

Ngược lại, nếu một `ObservationPredicate` từ chối cả observation, observation đó có thể không tạo metric/span từ các handler gắn với registry. Đây là quyết định **không tạo observation**, khác với tracing sampler chỉ quyết định recording/export trace. Không dùng predicate ngẫu nhiên để giả lập sampling vì có thể làm thiếu cả metrics.

### Đừng đưa Trace ID vào metric tags để bù trace bị bỏ

Trace ID gần như có một giá trị khác nhau cho mỗi trace. Thêm nó vào metric tag làm số time series tăng theo lưu lượng, dẫn tới cardinality explosion. Hãy dùng low-cardinality dimensions như:

- `service`, `route` template, `method`, `status`.
- `provider`, `region` hoặc `operation` có tập giá trị quản lý.
- `outcome=success/error/declined` với semantics rõ ràng.

Metrics giúp phát hiện xu hướng; traces được sampling giúp đi sâu một số giao dịch; logs có cấu trúc và correlation giúp tra cứu chi tiết trong phạm vi chính sách dữ liệu.

## 9. Sampling và context propagation qua service

Sampling decision và trace context được truyền qua các service. Với W3C Trace Context, sampled flag nằm trong trường flags của `traceparent`; parent-based sampler có thể dùng quyết định của parent để thống nhất việc ghi spans con.

```text
Client
  |
  v
orders-service
  root/server span: Trace ID=T, sampled=true
  |
  +-- HTTP client span
       inject traceparent (traceId=T, parent span id=C, flags=01)
                 |
                 v
          payment-service
            extract context
            parent-based sampler observes sampled parent
            create child span with Trace ID=T
```

Nếu `orders-service` chọn sampled=true nhưng `payment-service` không tôn trọng parent context hoặc nhận header lỗi, trace có thể thiếu spans ở downstream. Nếu gateway xóa `traceparent`, service sau có thể tạo Trace ID mới. Nếu parent not-sampled, child thường tiếp tục quyết định không recording theo parent-based strategy.

Với messaging và async execution, cần propagation tương ứng qua message headers/executor context. Một task chạy ở thread khác không tự có current span chỉ vì request thread đã sampled. Context propagation, sampling và scope là ba trách nhiệm liên quan nhưng riêng biệt.

## 10. Giới hạn và chính sách cần cân nhắc

Sampling không miễn trừ trách nhiệm kiểm soát dữ liệu và chi phí:

**Trace lỗi hiếm:** xác suất 1% có thể bỏ nhiều lỗi nếu lỗi chỉ xảy ra vài lần. Tail sampling có thể ưu tiên lỗi, nhưng collector phải nhận spans và giữ đủ trạng thái.

**Tải burst:** số trace được chọn trong cửa sổ ngắn có thể cao hơn kỳ vọng. Cần buffer/queue exporter và giới hạn collector; tỷ lệ trung bình không mô tả peak.

**Trace dài:** một workflow có hàng trăm spans hoặc chạy nhiều phút làm tăng chi phí trên mỗi trace. Sampling theo số trace không trực tiếp giới hạn số spans bên trong mỗi trace.

**Backend retention:** giữ 100% trace trong bảy ngày khác hoàn toàn giữ 10% trace trong ba mươi ngày. Tỷ lệ sampling, số spans/request, ingest volume và retention cùng quyết định chi phí.

**Bảo mật/riêng tư:** sampling không phải redaction. Một trace được giữ vẫn có thể chứa token, email, raw URL hoặc payload nhạy cảm nếu instrumentation ghi các trường đó. Lọc dữ liệu tại nguồn/collector và quản lý quyền truy cập.

**Độ chính xác thống kê:** sampling xác suất phù hợp để phân tích xu hướng khi hiểu rõ policy và tập dữ liệu. Không lấy số trace đã sampled làm tổng request thực tế nếu chưa biết sample ratio và cách xử lý parent/remote sampling. SLI quan trọng thường nên dựa vào metrics có độ bao phủ phù hợp, không chỉ vào số trace được lưu.

## 11. Ví dụ điều tra: lỗi hiếm nhưng cần giữ trace

Giả sử `orders-service` nhận 20.000 request/phút. Sampling head-based xác suất 5% có thể gửi trung bình khoảng 1.000 trace/phút nếu mỗi request tạo một trace mới và policy áp dụng độc lập theo giả định đơn giản. Một lỗi thanh toán xảy ra 4 lần trong một ngày có thể không rơi vào số trace được chọn.

**Không có trace không có nghĩa lỗi không xảy ra.** Metrics vẫn có thể cho biết số lần `payment.authorize{outcome="error"}` tăng; logs có thể ghi `error.kind=timeout` và trace correlation nếu context hiện có. Nhóm vận hành có thể:

1. Dùng metrics để xác định thời điểm, provider và tỷ lệ lỗi.
2. Dùng logs có cấu trúc để xác định loại lỗi và Trace ID nếu có.
3. Kiểm tra sampling decision/flags của trace liên quan.
4. Đánh giá tail sampling hoặc rule sampling riêng cho dịch vụ/route/lỗi.
5. Đảm bảo lỗi được biểu diễn bằng status/attributes phù hợp để collector nhận diện.
6. Kiểm tra collector có nhận đủ spans, giữ trace trong decision window và không drop do overflow hay không.

Một policy minh họa ở collector có thể là: giữ trace có span status ERROR; giữ trace có duration vượt ngưỡng; sample một phần trace bình thường. Đây là **logic khái niệm**, cú pháp processor, thứ tự policies, decision wait và fallback phụ thuộc phiên bản OpenTelemetry Collector và distribution đang dùng; cần kiểm tra tài liệu của component đã triển khai.

## 12. Cấu hình SDK thủ công với OpenTelemetry (khi ứng dụng tự sở hữu SDK)

Nếu không dùng Spring Boot auto-configuration để sở hữu tracing provider mà chủ động dựng SDK, có thể đặt sampler trên `SdkTracerProvider`:

```java
import io.opentelemetry.sdk.trace.SdkTracerProvider;
import io.opentelemetry.sdk.trace.samplers.Sampler;

SdkTracerProvider tracerProvider = SdkTracerProvider.builder()
        .setSampler(
                Sampler.parentBased(
                        Sampler.traceIdRatioBased(0.10)))
        .build();
```

Đoạn code chỉ minh họa thiết lập sampler. Ứng dụng thực tế còn cần `Resource`, `SpanProcessor`, `SpanExporter`, propagators và lifecycle shutdown. Nếu Spring Boot đã tạo provider qua Micrometer Tracing bridge, không tạo provider độc lập rồi mong các instrumentation đã auto-config tự chuyển sang nó.

Các sampler hay dùng trong OpenTelemetry SDK gồm:

| Sampler | Ý nghĩa |
| --- | --- |
| `alwaysOn()` | Ghi nhận mọi trace mới theo sampler này; chỉ phù hợp test hoặc tải rất nhỏ nếu không có policy khác |
| `alwaysOff()` | Không recording trace theo sampler |
| `traceIdRatioBased(p)` | Chọn theo tỷ lệ dựa trên Trace ID |
| `parentBased(root)` | Tôn trọng parent decision; dùng `root` cho trace mới không có parent |

Không dùng `alwaysOn()` làm cấu hình production mặc định khi lưu lượng và chi phí chưa được đánh giá. Cũng không dùng `alwaysOff()` để khắc phục exporter lỗi: nó chỉ khiến không còn spans recording, không sửa kết nối OTLP.

## 13. Quy trình lựa chọn và kiểm chứng sampling

Một quy trình thực tế:

1. **Đo nền:** request/giây, spans/request, bytes/span, trace duration, ingest rate, collector memory và chi phí backend.
2. **Xác định mục tiêu:** giảm ingest bao nhiêu, cần giữ loại lỗi nào, route/dịch vụ nào quan trọng, yêu cầu retention ra sao.
3. **Chọn chiến lược:** head-based xác suất làm nền; parent-based để giữ tính nhất quán; tail-based nếu cần quyết định dựa trên error/latency sau khi có spans.
4. **Cấu hình đúng nơi:** Spring Boot/Micrometer Tracing SDK cho head sampling; collector processor cho tail sampling; tránh đặt nhầm sampling lên metric/log pipeline.
5. **Kiểm tra propagation:** W3C `traceparent`/sampled flag giữa service, executor và message consumer.
6. **Kiểm tra export:** số spans được nhận, dropped spans, queue overflow, retry, collector errors và backend ingest.
7. **So sánh tín hiệu:** metrics vẫn phản ánh request/error; logs đủ trường điều tra; trace đại diện có đầy đủ parent-child.
8. **Theo dõi sau thay đổi:** so ingest volume, error traces được giữ, trace completeness và thời gian điều tra; điều chỉnh policy theo bằng chứng.

### Bảng kiểm thử tối thiểu

| Kịch bản | Kết quả mong đợi |
| --- | --- |
| Không có parent, tỷ lệ 100% | Trace mới được recording nếu SDK/exporter hoạt động |
| Không có parent, tỷ lệ thấp hơn 1 | Chỉ một phần trace mới được ghi theo sampler |
| Remote parent sampled=true với parent-based sampler | Child thường tiếp tục sampled theo parent |
| Remote parent sampled=false | Child thường tuân theo quyết định không sampling |
| Trace bị head-sampled out | Có thể còn context propagation; không có spans tương ứng được export |
| Trace sampled nhưng exporter lỗi | Recording decision có thể đúng nhưng backend thiếu trace |
| Metric handler hoạt động, tracing sample thấp | Metrics vẫn được ghi độc lập |
| Predicate loại observation | Observation đó không tạo tín hiệu từ handlers tương ứng |
| Tail sampler muốn giữ lỗi | Collector phải nhận span/status cần thiết trước decision |
| Executor không propagate context | Worker có thể mất current span/Trace ID dù request gốc sampled |

## 14. Bài tập tình huống

Một hệ thống Spring Boot được cấu hình:

```yaml
management:
  tracing:
    sampling:
      probability: 0.01
```

Sau một đợt deploy, metrics ghi nhận `payment.authorize` có 30 lỗi timeout trong 10 phút. Logs có Trace ID cho một số lỗi nhưng tracing backend chỉ tìm thấy hai traces. Team kết luận “metrics và logs không đồng bộ với tracing nên Micrometer bị lỗi”.

**Câu hỏi:**

1. Sampling 1% có thể giải thích một phần việc chỉ tìm thấy một số traces không?
2. Vì sao vẫn có metrics và logs khi một trace không có trong backend?
3. Điều gì cần xác minh trước khi tăng sampling lên 100%?
4. Làm sao ưu tiên trace lỗi mà vẫn kiểm soát chi phí?

**Gợi ý phân tích:**

- Sampling 1% có thể khiến đa số trace không được recording/export. Một tập nhỏ 30 lỗi không nhất thiết có đủ trace với xác suất 1%.
- Metrics có pipeline riêng và log statements vẫn được ghi theo logging configuration. Log correlation có thể mang Trace ID từ context dù trace không được exported, tùy implementation.
- Kiểm tra head sampler/parent-based policy, propagation, exporter/collector drops, backend retention, instrumentation và số spans/request trước khi đổi tỷ lệ.
- Nếu yêu cầu giữ lỗi, cân nhắc tail sampling ở collector với error/latency policies; cần bảo đảm spans được gửi tới collector, gom đúng trace và có tài nguyên chờ quyết định. Dùng metrics để theo dõi toàn bộ tỉ lệ lỗi.

### Checklist hoàn thành

| Nội dung | Có thể giải thích/kiểm tra |
| --- | --- |
| Phân biệt trace và span | Trace ID chung, Span ID riêng, parent relationship |
| Head-based sampling | Quyết định gần đầu trace, không biết kết quả cuối |
| Parent-based sampling | Tuân theo sampled decision của parent theo policy |
| Tail-based sampling | Quyết định sau khi collector nhận spans; có state và resource cost |
| Spring Boot property | Biết vị trí `management.tracing.sampling.probability` ở phiên bản hỗ trợ |
| W3C sampled flag | Hiểu flags trong `traceparent`, không dùng thay auth |
| Metrics/logs | Không mặc định bị loại cùng tracing sampling |
| ObservationPredicate | Phân biệt từ chối cả observation với sampling trace |
| Cardinality | Không dùng Trace ID làm metric tag |
| Exporter/collector | Phân biệt recording decision với dữ liệu thực sự ingest |

**Ghi nhớ:** Trace sampling chọn trace nào được ghi nhận/xuất để cân bằng chi phí và khả năng điều tra. **Head-based sampling** quyết định sớm; **parent-based sampling** giữ quyết định xuyên service; **tail-based sampling** có thể ưu tiên trace lỗi/chậm sau khi collector nhận dữ liệu nhưng cần thêm bộ nhớ và vận hành. Spring Boot/Micrometer Tracing sampling không thay thế metric collection hay logging. Muốn observability đáng tin cậy, hãy kết hợp metrics bao phủ xu hướng, logs có cấu trúc, trace đại diện, context propagation đúng và exporter/collector được kiểm chứng end-to-end.
