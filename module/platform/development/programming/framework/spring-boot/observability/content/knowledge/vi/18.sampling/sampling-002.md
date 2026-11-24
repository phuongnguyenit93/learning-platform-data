# Sampling probability: chọn tỷ lệ trace cần thu thập trong Spring Boot

> **Chương:** Sampling  
> **Bài:** Sampling probability  
> **Module:** `SPRING_BOOT_OBSERVABILITY` — Thiết lập observability cho Spring Boot bằng Micrometer Observation, metrics, logs và distributed tracing. Học propagation ngữ cảnh, tag/cardinality, exporter, sampling và liên kết tín hiệu để điều tra lỗi, độ trễ và hành vi ứng dụng trên môi trường thực.

## 1. Vì sao cần sampling?

Một dịch vụ Spring Boot có thể nhận hàng nghìn request mỗi giây. Mỗi request tạo server span, các span nghiệp vụ, HTTP client spans và database spans. Gửi toàn bộ trace giúp quan sát đầy đủ nhưng làm tăng CPU, mạng, dung lượng lưu trữ và chi phí truy vấn. Lấy mẫu quá ít lại có thể bỏ lỡ một lỗi hiếm hoặc một request rất chậm.

**Sampling probability** là xác suất được dùng để quyết định trace nào được ghi nhận và xuất tới tracing backend. Cấu hình Spring Boot thường có dạng:

~~~yaml
management:
  tracing:
    sampling:
      probability: 0.1
~~~

Giá trị 0.1 biểu thị xác suất 10% trong sampler xác suất tương ứng. Nó không có nghĩa chắc chắn cứ 10 request sẽ giữ đúng một trace và cũng không có nghĩa metrics chỉ đếm 10% request.

~~~mermaid
flowchart LR
  A["Request / parent context"] --> B["Sampler"]
  B --> C{"Sampling decision"}
  C -->|"sampled"| D["Record spans"]
  C -->|"not sampled"| E["Không xuất trace theo policy"]
  D --> F["Processor / reporter"]
  F --> G["Exporter"]
  G --> H["Collector / tracing backend"]
~~~

Bài học tập trung vào xác suất, head-based và parent-based sampling, cấu hình Spring Boot, propagation, ước lượng chi phí, giới hạn khi muốn giữ trace lỗi hiếm và cách kiểm thử.

## 2. Sampling probability có nghĩa gì?

Giả sử sampler chọn mỗi trace độc lập với xác suất p. Với N traces đủ điều kiện, số trace được chọn kỳ vọng là:

\[
E[S] = N \times p
\]

Ví dụ N=100.000 và p=0.1 thì số trace kỳ vọng là 10.000. Giá trị thực tế có thể cao hoặc thấp hơn.

| Probability | Tỷ lệ kỳ vọng | Diễn giải |
| ---: | ---: | --- |
| 0.0 | 0% | Không chọn trace mới theo sampler này |
| 0.01 | 1% | Trung bình khoảng 1 trên 100 trace |
| 0.05 | 5% | Trung bình khoảng 5 trên 100 trace |
| 0.1 | 10% | Trung bình khoảng 10 trên 100 trace |
| 0.5 | 50% | Trung bình khoảng một nửa |
| 1.0 | 100% | Chọn mọi trace đủ điều kiện của policy |

Đây là xác suất, không phải quota chính xác cho mỗi phút. Trong một nhóm request nhỏ, số trace giữ lại có thể biến động rõ rệt.

### 2.1. Độ dao động thống kê

Với mô hình Bernoulli đơn giản:

\[
Var(S) = Np(1-p), \quad \sigma=\sqrt{Np(1-p)}
\]

Với N=100, p=0.1, số trace kỳ vọng là 10 và độ lệch chuẩn là 3. Quan sát được 6 hoặc 14 trace trong một khoảng ngắn chưa chứng minh sampler bị lỗi. Cần quan sát tập traffic đủ lớn và loại trừ exporter drop trước khi đánh giá tỷ lệ.

### 2.2. Sampling trace không sampling mọi tín hiệu

Tracing probability không tự giảm Counter/Timer Micrometer, logs của ứng dụng, số request thực sự được xử lý hoặc sự kiện nghiệp vụ trong database. 10.000 request vẫn có thể làm Counter tăng 10.000 lần dù chỉ một phần trace được xuất. Mỗi tín hiệu có pipeline và chính sách lưu trữ riêng.

## 3. Head-based sampling

**Head-based sampling** đưa ra quyết định khi trace bắt đầu, thường tại root span hoặc lúc nhận context từ upstream. Quyết định có thể được truyền xuống các dịch vụ khác qua trace context và sampled flag.

~~~mermaid
sequenceDiagram
  participant Client
  participant Gateway
  participant Order as order-service
  participant Inventory as inventory-service
  Client->>Gateway: Request
  Note over Gateway: Root sampler quyết định
  Gateway->>Order: Request + trace context
  Order->>Inventory: Request + trace context
  Inventory-->>Order: Response
  Order-->>Gateway: Response
  Gateway-->>Client: Response
  Note over Gateway,Inventory: Downstream tuân theo parent decision
~~~

Ưu điểm là quyết định sớm, chi phí thấp và dễ giữ tính nhất quán xuyên service. Hạn chế là sampler thường chưa biết request cuối cùng có lỗi hoặc rất chậm hay không. Một trace đã bị loại ở đầu thường không thể được giữ lại đầy đủ chỉ vì lỗi xuất hiện ở cuối.

Do đó head-based probability không bảo đảm thu được mọi lỗi hiếm, timeout hoặc trace chậm.

## 4. Parent-based sampling

Trong distributed system, request đi qua gateway rồi nhiều service. Nếu từng service tự quyết định độc lập, trace có thể bị chia thành phần được ghi và phần bị bỏ.

**Parent-based sampler** sử dụng sampling decision của parent khi có parent hợp lệ. Parent sampled thường dẫn đến child tiếp tục record; parent not-sampled thường dẫn đến child không record theo quyết định đó. Khi không có parent, root sampler quyết định.

~~~text
Không có parent: root sampler chọn sampled / not sampled
Parent sampled: child thường record theo parent
Parent not-sampled: child thường không record
Remote parent: quyết định lấy từ trace context đã extract
~~~

Trong OpenTelemetry, parent-based sampler có thể kết hợp với trace-ID-ratio root sampler. Tên và cấu hình cụ thể phụ thuộc SDK, bridge và phiên bản. Không đồng nhất mọi implementation Brave/Micrometer với sampler nội bộ của OpenTelemetry SDK.

Tăng probability riêng ở downstream không nhất thiết ghi lại trace mà upstream đã loại. Muốn thay đổi hành vi phải thiết kế sampling policy xuyên suốt.

## 5. Cấu hình trong Spring Boot

Với Spring Boot 3.x có Micrometer Tracing và bridge phù hợp:

~~~yaml
management:
  tracing:
    sampling:
      probability: 0.1
~~~

Ví dụ local dùng Zipkin:

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

Tên service cung cấp metadata cho tracing. Probability 1.0 thuận tiện cho local/test traffic thấp. Endpoint Zipkin cấu hình nơi gửi spans khi reporter tương ứng được cài đặt.

Nếu ứng dụng chạy trong Docker, localhost từ container ứng dụng trỏ về container đó. Khi Zipkin là service khác cùng network, dùng hostname service như http://zipkin:9411/api/v2/spans.

### 5.1. Dependencies và bridge

Actuator cung cấp nền tảng management/Observation, nhưng sampling chỉ hữu ích khi có tracing implementation và exporter. Ví dụ Maven cho Brave bridge và Zipkin Reporter:

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

Dùng Spring Boot BOM/parent tương thích. Với OpenTelemetry bridge và exporter, dependency khác. Không ghép nhiều bridge tracing trong cùng ứng dụng nếu không có kiến trúc rõ ràng. Property và auto-configuration thay đổi theo phiên bản; hãy xác minh metadata của phiên bản Spring Boot thực tế.

## 6. Sampling decision và trace context propagation

Trace context truyền quyết định sampling giữa các service. W3C Trace Context dùng header traceparent với trường flags; sampled bit biểu thị trạng thái sampled. B3 có thể truyền thông tin sampling qua header b3 hoặc X-B3-Sampled.

~~~http
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
~~~

Flags 01 trong ví dụ có sampled bit bật. Đây là dữ liệu wire propagation; không nên sửa thủ công trong code nghiệp vụ.

Khi gateway chọn sampled, nó inject trace context. Order-service extract context trước khi tạo server span, parent-based sampler tiếp tục quyết định cho child, và các dịch vụ sau tiếp tục inject/extract. Nếu gateway không sample, downstream thường tôn trọng quyết định đó.

### 6.1. Propagation bị đứt

Nếu downstream không nhận context, nó có thể tạo root trace mới và tự sampling. Waterfall bị tách, trace IDs khác nhau và sampling ratio toàn hệ thống không còn như dự kiến.

Kiểm tra HTTP client instrumentation, inbound/outbound headers, W3C/B3 compatibility, proxy forwarding, service mesh và async context propagation. Sampling probability đúng không thể sửa lỗi propagation.

## 7. Ước lượng số trace và spans

Ước lượng ban đầu:

\[
Traces_{kept/day} \approx Requests_{traced/day} \times p
\]

Ví dụ có 500 request/giây, 86.400 giây/ngày và p=0.05:

\[
500 \times 86{,}400 = 43{,}200{,}000
\]

\[
43{,}200{,}000 \times 0.05 = 2{,}160{,}000\ traces/day
\]

Nếu mỗi trace có trung bình 8 spans, sẽ có khoảng 17,28 triệu spans/ngày. Nếu một span sau serialization trung bình 1,2 KB, payload thô vào khoảng 20,7 GB/ngày.

Đây là phép tính quy mô, không phải dự báo chính xác. Kích thước thực tế phụ thuộc số spans, attributes, events, resource metadata, compression, protocol, batching, retries, indexing và retention.

| Yếu tố | Tác động |
| --- | --- |
| Request rate | Tăng số trace tiềm năng |
| Sampling probability | Tăng số trace kỳ vọng |
| Spans per trace | Tăng số records |
| Attributes và events | Tăng payload và chi phí index |
| Retention | Tăng dung lượng lưu tích lũy |
| Indexing/search | Có thể tốn hơn truyền payload |

Không chỉ giảm probability mới tối ưu chi phí. Hãy giới hạn attributes/events không cần thiết, kích thước payload, retention và indexing.

## 8. Xác suất thấp bỏ lỡ lỗi hiếm

Với N request, error rate q và sampling p độc lập, số trace lỗi kỳ vọng được giữ là:

\[
E[Errors_{kept}] = N \times q \times p
\]

Ví dụ 1.000.000 request, error rate 0,01% (q=0.0001), sampling p=0.01:

\[
1{,}000{,}000 \times 0.0001 \times 0.01 = 1
\]

Chỉ kỳ vọng một trace lỗi được giữ. Nếu có 100 lỗi độc lập, xác suất không giữ được trace lỗi nào:

\[
P(0)=(1-p)^{100}=(0.99)^{100}\approx0.366
\]

Khoảng 36,6% trong mô hình đơn giản này. Sampling thấp có thể đủ cho traffic phổ biến nhưng không bảo đảm giữ lỗi hiếm. Dùng metrics/logs để phát hiện và định lượng; cân nhắc tail sampling nếu pipeline hỗ trợ.

Không dùng số trace lỗi trên backend làm error rate tổng thể khi sampling không được hiệu chỉnh. SLI/SLO nên dựa trên metrics có semantics rõ ràng.

## 9. Head sampling và tail sampling

| Khía cạnh | Head-based probability | Tail sampling |
| --- | --- | --- |
| Thời điểm quyết định | Khi trace bắt đầu | Sau khi Collector nhận spans để đánh giá |
| Biết kết quả cuối | Thường chưa | Có thể biết status/duration đã nhận |
| Giữ lỗi hiếm | Không bảo đảm | Có thể ưu tiên nếu spans tới Collector và policy khớp |
| Tài nguyên | Quyết định sớm, nhẹ | Cần buffer/state và capacity |
| Rủi ro | Bỏ lỡ lỗi xuất hiện về sau | Thiếu spans, buffer đầy, decision delay |

Tail sampling không phải property đơn giản của management.tracing.sampling.probability. Đây thường là processor/policy tại OpenTelemetry Collector hoặc backend có chức năng tương ứng.

~~~text
Policy khái niệm:
  giữ trace nếu có span ERROR
  hoặc tổng duration vượt ngưỡng chậm
  giữ thêm một tỷ lệ nhỏ trace bình thường
~~~

Collector chỉ quyết định từ spans nó đã nhận. Nếu head sampler tại source đã loại trace và không gửi spans, tail sampler không thể phục hồi dữ liệu đó. Tail sampling đòi hỏi buffer, timeout, capacity planning và routing traces nhất quán tới tier quyết định.

## 10. Sampling theo môi trường

Không dùng một xác suất mặc định cho mọi môi trường. Ví dụ minh họa:

~~~yaml
# application-local.yml
management:
  tracing:
    sampling:
      probability: 1.0
~~~

~~~yaml
# application-staging.yml
management:
  tracing:
    sampling:
      probability: 0.5
~~~

~~~yaml
# application-prod.yml
management:
  tracing:
    sampling:
      probability: 0.05
~~~

Local có thể lấy toàn bộ trace khi traffic nhỏ; staging dùng tỷ lệ cao để kiểm tra instrumentation; production cân bằng chất lượng điều tra với ngân sách. Các con số chỉ là ví dụ, cần đo traffic và capacity thực tế.

Environment variable theo relaxed binding thường có dạng:

~~~text
MANAGEMENT_TRACING_SAMPLING_PROBABILITY=0.05
~~~

Xác định nguồn cấu hình có hiệu lực, profile, environment variables và cấu hình tập trung. Thay đổi cấu hình không nhất thiết đổi quyết định của các trace đã bắt đầu. Nếu cần đổi sampling động, dùng cơ chế được implementation hỗ trợ.

## 11. Metrics, logs và trace sampling

| Tín hiệu | Chính sách sampling/filter | Vai trò |
| --- | --- | --- |
| Counter/Timer metrics | Không giảm theo tracing probability trong cấu hình thông thường | Số lượng, latency, error rate |
| Traces | SDK/tracer sampler, Collector tail sampler | Waterfall của một số lần thực thi |
| Application logs | Logging level/filter/agent | Chi tiết sự kiện |
| Business audit | Chính sách lưu trữ nghiệp vụ | Lưu sự kiện cần bảo đảm |

Một request không có trace vẫn có thể có logs và metrics. Một trace đã được sample cũng không bảo đảm mọi log record liên quan được giữ lại.

Một số hệ thống hỗ trợ **exemplar** để liên kết một điểm metric với trace ID. Exemplar không biến trace ID thành metric label và không thay thế sampling policy. Không gắn traceId cho mọi Counter/Timer vì cardinality sẽ tăng mạnh.

## 12. Kiểm tra sampled decision và propagation

Ví dụ W3C traceparent:

~~~http
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
~~~

Flags 01 có sampled bit bật; flags 00 thể hiện trace không sampled theo W3C Trace Context. B3 single-header có thể có dạng:

~~~http
b3: 4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-1
~~~

Không tự sửa headers để ép sampling production. Kiểm tra bằng instrumentation/proxy được phê duyệt và tránh log headers chứa credential.

Checklist debug:

- Gateway có nhận trace context từ upstream hay bắt đầu trace mới?
- Root sampler ở đâu và probability hiệu lực là bao nhiêu?
- Client instrumentation có inject headers không?
- Downstream có extract đúng W3C/B3 không?
- Parent-based policy có tôn trọng sampled decision không?
- Proxy/service mesh có drop headers không?
- Async executor/Reactor có giữ context không?
- Exporter/Collector có nhận spans không?

## 13. Chọn probability theo yêu cầu vận hành

Chọn từ mục tiêu, không chọn chỉ vì một con số phổ biến:

- **Độ trễ thường ngày:** tỷ lệ vừa phải có thể đủ xem waterfall điển hình.
- **Lỗi hiếm:** head probability thấp có thể bỏ lỡ; metrics phải đo tỷ lệ lỗi, tail sampling có thể ưu tiên trace nếu Collector nhận spans.
- **Luồng thanh toán:** policy ưu tiên theo operation/service có thể hữu ích nhưng cần bảo vệ dữ liệu.
- **Sự cố production:** có thể tăng sampling tạm thời có kiểm soát, sau khi xác minh capacity.
- **Audit/tuân thủ:** tracing sampling không thay thế hệ thống audit cần lưu mọi sự kiện.

### 13.1. Ước lượng theo ngân sách

Giả sử backend nhận tối đa 5 triệu spans/ngày, mỗi trace trung bình 10 spans và service nhận 10 triệu request/ngày:

\[
p \approx \frac{5{,}000{,}000}{10{,}000{,}000 \times 10}=0.05
\]

5% là điểm bắt đầu theo giả định mọi request có một trace và 10 spans/trace. Thực tế cần tính thêm background jobs, retries, messaging consumers, service khác và burst traffic.

### 13.2. Thay đổi có kiểm soát

Tăng khi backend còn ngân sách và trace hiện tại không đủ điều tra. Giảm khi exporter/collector quá tải, vượt quota hoặc chi phí quá cao. Trước khi giảm mạnh, loại attributes/events không cần và instrumentation trùng. Mọi thay đổi cần owner, thời hạn, dashboard và điều kiện rollback.

## 14. Sampling và baggage

Baggage có thể được propagate cùng trace context nhưng **không tự quyết định sampling**. Một field region=ap-south không làm trace được giữ, trừ khi custom sampler/policy đọc thuộc tính đó tại thời điểm quyết định.

Với head-based sampler, một attribute/baggage có thể chưa tồn tại lúc root decision được đưa ra. Gắn priority=high sau khi Observation bắt đầu không nhất thiết thay đổi root sampling. Tail sampler có thể đọc attributes sau khi Collector nhận spans, nếu policy hỗ trợ.

Không đưa trace ID hoặc baggage ID duy nhất vào metrics tags để điều khiển sampling; đó là rủi ro cardinality và dữ liệu.

## 15. Lỗi thường gặp và chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| Không thấy trace ở probability 0.1 | Trace không được chọn | Gửi đủ traffic test, xem sampled decision |
| Sampling 1.0 nhưng UI thiếu trace | Thiếu bridge/exporter, lỗi mạng, storage/index | Kiểm tra pipeline |
| Gateway có trace, downstream thiếu span | Mất header hoặc thiếu instrumentation | Kiểm tra client/server integration |
| Downstream tạo trace mới | Parent context không extract | Kiểm tra W3C/B3 và proxy |
| Ratio backend lệch probability | Parent decisions, nhiều nguồn, drop khi export | Kiểm tra sampler, Collector và ingest |
| Trace lỗi hiếm vắng mặt | Head sampling loại từ đầu | Metrics, tail sampling hoặc policy ưu tiên |
| Metrics count giảm theo trace ratio | Nhầm hai pipeline | Kiểm tra MeterRegistry và tracing |
| Tăng probability làm Collector quá tải | Spans/attributes vượt capacity | Queue, exporter errors, memory |
| Đổi property nhưng ratio không đổi | Property precedence hoặc config chưa áp dụng | Xác minh effective config |
| Log lỗi nhưng trace lỗi không có | Sampling, Observation không báo lỗi, exporter drop | Kiểm tra error callback và export |

Quy trình: xác nhận property hiệu lực; tạo workload đủ lớn; kiểm tra trace context/sampled flags; đối chiếu root với downstream spans; kiểm tra exporter/Collector queue và drop; dùng metrics không sampling để đánh giá lỗi thực tế; kiểm tra logging correlation riêng.

## 16. Tình huống: lỗi hiếm bị bỏ qua ở sampling 1%

**Bối cảnh:** order-service xử lý 2 triệu request mỗi ngày. Timeout downstream xảy ra ở 0,02% request. Probability là 0.01 (1%).

Số lỗi kỳ vọng:

\[
2{,}000{,}000 \times 0.0002=400
\]

Số trace lỗi kỳ vọng được giữ:

\[
400 \times 0.01=4
\]

Chỉ khoảng bốn trace lỗi mỗi ngày theo kỳ vọng. Metrics vẫn có thể phản ánh đủ khoảng 400 lỗi.

### Điều tra và cải thiện

1. Dashboard metrics phát hiện timeout rate tăng.
2. Logs ghi exception đã chuẩn hóa và trace ID khi context tồn tại.
3. Traces được sample cho thấy span downstream chậm.
4. Nhóm kiểm tra capacity và tail sampling nếu pipeline nhận đầy đủ spans.
5. Giảm attributes không cần thiết, giữ baseline sampling và theo dõi queue/drop sau thay đổi.

**Bài học:** probability thấp giảm chi phí nhưng không bảo đảm trace của lỗi hiếm. Metrics lượng hóa ảnh hưởng; trace giúp xác định đường thực thi cụ thể.

## 17. Bài thực hành và câu hỏi tự kiểm tra

### Bài tập A — xác minh xác suất

Gửi 10.000 requests trong môi trường test, thử probability 1.0, 0.5, 0.1, 0.01. Đếm trace trên backend khi exporter không drop, so sánh với kỳ vọng và giải thích biến động. Xác minh Counter request vẫn ghi đủ request.

### Bài tập B — parent propagation

Tạo gateway và order-service. Gateway bắt đầu trace, HTTP client truyền trace context, downstream extract context. Kiểm tra cùng trace ID với parent sampled và not-sampled. Sau đó cố ý bỏ header trong test để quan sát trace bị tách.

### Bài tập C — ước lượng chi phí

Service xử lý 1.000 request/giây, probability 5%, trung bình 12 spans/trace. Tính requests/ngày, traces/ngày, spans/ngày và payload nếu span trung bình 0,8 KB. Liệt kê factors khiến thực tế khác ước tính.

### Bài tập D — lỗi hiếm

Lỗi xuất hiện ở 0,001% requests, head sampling 1%. Tính số trace lỗi kỳ vọng trong một triệu request. Giải thích vì sao tail sampling chỉ giữ trace nếu spans tới Collector và cần tài nguyên buffer nào.

### Bài tập E — review production

Rà soát probability từng môi trường, config precedence, root/parent policy, propagation format, số spans/trace, exporter capacity, quan hệ với metrics/logs, owner và điều kiện rollback.

### Câu hỏi tự kiểm tra

1. Sampling probability 0.1 diễn giải thế nào?
2. Vì sao 10 request không chắc cho đúng một trace?
3. Head-based sampler quyết định lúc nào và hạn chế gì?
4. Parent-based sampling dùng quyết định upstream ra sao?
5. W3C sampled flag có vai trò gì?
6. Vì sao trace sampling không giảm Counter Micrometer?
7. Số trace lỗi kỳ vọng phụ thuộc traffic, error rate và probability thế nào?
8. Tail sampling khác head-based sampling ở đâu?
9. Vì sao tăng probability ở child có thể không ghi parent not-sampled?
10. Vì sao không dùng trace backend để đếm tổng request?
11. Sampling 100% có luôn an toàn production không?
12. Khi thiếu trace cần kiểm tra sampling, propagation, exporter và backend thế nào?

**Tiêu chí hoàn thành:** hiểu probability và biến động thống kê; phân biệt head/parent/tail sampling; cấu hình Spring Boot; hiểu sampled flags/propagation; ước lượng spans/chi phí; phân biệt traces với metrics/logs; chẩn đoán trace thiếu và thiết kế sampling có kiểm soát.

## 18. Ghi nhớ

- management.tracing.sampling.probability cấu hình xác suất chọn trace theo tracing integration; 0.1 nghĩa khoảng 10% kỳ vọng, không phải tỷ lệ chính xác từng phút.
- **Head-based sampling** quyết định sớm nên tiết kiệm tài nguyên nhưng có thể bỏ lỡ lỗi/chậm xuất hiện về sau.
- **Parent-based sampling** giữ quyết định nhất quán theo trace context giữa các service; kiểm tra sampled flags khi downstream thiếu span.
- **Tail sampling** có thể ưu tiên lỗi/latency sau khi Collector nhận spans, nhưng cần buffer/capacity/policy. Nó không khôi phục spans đã bị head sampler loại tại nguồn.
- Trace sampling không tự giảm metrics Counter/Timer hoặc application logs. Dùng metrics cho SLI/SLO và traces để tìm chi tiết một lần thực thi.
- Ước tính chi phí dựa trên request rate, probability, spans/trace, kích thước span, retention và indexing.
- Chỉ tăng sampling có kiểm soát, theo môi trường và thời hạn. Không mặc định 100% production hoặc xem tracing là audit store.

## Tài liệu tham khảo

- [Spring Boot Reference — Tracing](https://docs.spring.io/spring-boot/reference/actuator/tracing.html)
- [Spring Boot Reference — Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html)
- [Micrometer Tracing Reference](https://docs.micrometer.io/tracing/reference/)
- [OpenTelemetry Specification — Sampling](https://opentelemetry.io/docs/specs/otel/trace/sdk/#sampling)
- [OpenTelemetry — Sampling concepts](https://opentelemetry.io/docs/concepts/sampling/)
- [OpenTelemetry Collector — Tail Sampling Processor](https://github.com/open-telemetry/opentelemetry-collector-contrib/tree/main/processor/tailsamplingprocessor)
- [W3C Trace Context](https://www.w3.org/TR/trace-context/)

