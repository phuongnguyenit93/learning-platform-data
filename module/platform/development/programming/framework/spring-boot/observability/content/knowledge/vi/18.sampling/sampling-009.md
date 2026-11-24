# Sampling cho lỗi trong distributed tracing với Spring Boot

Trong production, một dịch vụ có thể xử lý hàng chục nghìn request mỗi phút. Nếu ghi lại toàn bộ spans của mọi request, tracing backend phải tiếp nhận lượng dữ liệu lớn, tốn CPU, bộ nhớ, băng thông và chi phí lưu trữ. Nhưng nếu sampling quá thấp, một lỗi hiếm hoặc một request có độ trễ bất thường lại có thể không có trace để điều tra. **Sampling cho lỗi** là cách thiết kế chính sách thu thập traces sao cho những trường hợp quan trọng như lỗi, timeout hoặc latency cao có cơ hội được giữ lại, trong khi vẫn kiểm soát được chi phí.

Trong module **SPRING_BOOT_OBSERVABILITY**, sampling là một phần của thiết lập observability cho Spring Boot bằng Micrometer Observation, metrics, logs và distributed tracing. Bài này thuộc chương **Sampling**, tập trung vào chủ đề **Sampling cho lỗi**: phân biệt head-based và tail-based sampling, hiểu giới hạn của xác suất sampling, cấu hình Spring Boot/Micrometer Tracing, thiết lập OpenTelemetry Collector, kiểm soát context propagation, cardinality, exporter và liên kết metrics–logs–traces khi điều tra sự cố.

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích vì sao sampling cần thiết và trade-off giữa khả năng điều tra với chi phí telemetry.
2. Phân biệt head-based sampling và tail-based sampling, biết thời điểm mỗi cách đưa ra quyết định.
3. Giải thích vì sao head sampler theo xác suất không thể biết một request sẽ lỗi ở cuối quá trình xử lý.
4. Cấu hình xác suất sampling trong Spring Boot Micrometer Tracing cho môi trường phát triển và production.
5. Xây dựng Collector tail-sampling policy để giữ trace có status lỗi hoặc latency cao.
6. Hiểu parent-based sampling, propagation của sampled flag và yêu cầu định tuyến spans theo trace khi xử lý tail sampling.
7. Tránh suy ra error rate hoặc SLO từ một tập trace đã sampling.
8. Kiểm thử và vận hành sampling cùng exporter, logs, metrics, baggage và chính sách bảo mật.

## 1. Vì sao cần sampling?

Một request được instrument có thể tạo nhiều spans: HTTP server, Observation nghiệp vụ, HTTP client, database và message producer/consumer. Với hàng nghìn request mỗi giây, số spans sinh ra có thể lớn hơn nhiều số request. Nếu lưu 100% traces, chi phí ingest và retention tăng theo lưu lượng và độ chi tiết instrumentation.

**Sampling** chọn phần dữ liệu tracing được ghi nhận hoặc export. Một policy tốt cần cân bằng:

- **Giá trị điều tra:** ưu tiên các request lỗi, timeout, latency cao và luồng quan trọng.
- **Chi phí:** giới hạn số spans, dung lượng queue, băng thông và thời gian lưu.
- **Tính đại diện:** vẫn có mẫu của traffic bình thường để so sánh với lỗi.
- **Độ đầy đủ của trace:** cố gắng giữ các spans liên quan trong cùng trace.
- **Độ trễ ra quyết định:** chọn sampling sớm hay chờ quan sát kết quả cuối cùng.

### 1.1. Ví dụ về tác động

Giả sử `order-service` xử lý 100.000 request trong một giờ. Trong đó 200 request bị lỗi, tương đương 0,2%. Nếu sampling xác suất 1% ở đầu trace, số trace lỗi được giữ kỳ vọng chỉ khoảng 2; khả năng bỏ sót cả nhóm lỗi vẫn đáng kể.

Với xác suất sampling độc lập `p`, mỗi trace có xác suất `1-p` bị loại. Nếu có `n` trace lỗi độc lập, xác suất **không giữ được trace lỗi nào** là:

\[
P(\text{không giữ trace lỗi})=(1-p)^n
\]

Ví dụ sampling 1% và chỉ có 10 trace lỗi:

\[
P=(1-0.01)^{10}\approx 90.4\%
\]

Đây là ví dụ xác suất đơn giản giả định quyết định độc lập và đúng một mẫu cho mỗi trace. Nó minh họa rằng sampling thấp có thể làm mất toàn bộ bằng chứng của một lỗi hiếm.

### 1.2. Sampling không phải rate limiting request

Sampling chỉ quyết định dữ liệu telemetry nào được ghi/giữ. Nó **không được dùng để bỏ request nghiệp vụ**, không giảm số lần gọi database và không thay thế rate limiter của API. Request vẫn phải được xử lý theo logic ứng dụng; các metrics nghiệp vụ/HTTP có thể tiếp tục ghi nhận tất cả request dù chỉ một phần trace được lưu.

## 2. Hai chiến lược chính: head-based và tail-based

Khác biệt quan trọng nhất là **thời điểm quyết định sampling**:

| Đặc điểm | Head-based sampling | Tail-based sampling |
| --- | --- | --- |
| Thời điểm quyết định | Khi trace/span bắt đầu hoặc được khởi tạo | Sau khi Collector nhận đủ phần trace cần đánh giá |
| Thông tin sẵn có | Context và metadata có tại thời điểm bắt đầu | Có thể quan sát status, errors, duration và attributes xuất hiện sau đó |
| Có thể ưu tiên trace lỗi cuối request? | Không nếu lỗi chỉ phát sinh sau quyết định | Có, nếu trace đầy đủ được gửi tới sampler |
| Chi phí tại ứng dụng | Thấp hơn, có thể bỏ span sớm | Ứng dụng vẫn phải tạo và gửi các spans cần đánh giá |
| Hạ tầng | Sampler trong tracing SDK | Collector/pipeline có buffer, policy và capacity |
| Độ phức tạp | Tương đối đơn giản | Cao hơn; cần routing, bộ nhớ và thời gian chờ |
| Trường hợp dùng | Sampling xác suất, traffic lớn, quyết định sớm | Giữ lỗi, latency cao, status hoặc thuộc tính cuối trace |

~~~mermaid
flowchart TD
    Request["Request bắt đầu"] --> Head{"Head sampler<br/>quyết định ngay"}
    Head -- "Drop" --> HeadDrop["Không ghi span đã bị bỏ"]
    Head -- "Record" --> HeadTrace["Ghi spans trong SDK"]
    HeadTrace --> HeadExport["Exporter gửi spans"]
    HeadExport --> BackendA["Trace backend"]
    Request --> TailRecord["SDK ghi spans theo policy thu thập"]
    TailRecord --> TailExport["Exporter gửi spans"]
    TailExport --> Buffer["Collector buffer theo trace ID"]
    Buffer --> Decide{"Đã đủ thời gian/dữ liệu?"}
    Decide -- "Chưa" --> Buffer
    Decide -- "Rồi" --> Policy{"Policy: error / latency / sample"}
    Policy -- "Giữ" --> Keep["Export trace"]
    Policy -- "Loại" --> Drop["Drop trace"]
    Keep --> BackendB["Trace backend"]
~~~

Trong sơ đồ tail sampling, các spans phải được gửi đến Collector thì Collector mới có thể quyết định. Nếu SDK head sampler đã loại trace trước khi export, tail sampler không thể phục hồi phần dữ liệu đó.

## 3. Head-based sampling: quyết định ở đầu trace

**Head-based sampling** đưa ra quyết định ghi span khi trace được khởi tạo. Cách đơn giản là lấy mẫu theo xác suất:

- 100%: ghi mọi trace được instrument.
- 10%: kỳ vọng ghi khoảng 1/10 traces.
- 1%: kỳ vọng ghi khoảng 1/100 traces.
- 0%: không ghi trace theo policy xác suất đó.

Trong Spring Boot với Micrometer Tracing, có thể cấu hình:

~~~yaml
management:
  tracing:
    sampling:
      probability: 0.10
~~~

Đây là xác suất 10% cho sampling strategy mà Spring Boot/Micrometer Tracing tích hợp. Hành vi chi tiết còn phụ thuộc tracing bridge và phiên bản. Trong môi trường phát triển, có thể dùng 1.0 để dễ quan sát; production nên chọn theo traffic, năng lực backend và nhu cầu điều tra.

### 3.1. Vì sao head sampler không thể biết lỗi ở cuối request?

Giả sử `POST /orders` bắt đầu bình thường, nhưng 2 giây sau inventory-service timeout. Head sampler đã phải quyết định khi request bắt đầu, tại thời điểm chưa có kết quả timeout.

~~~mermaid
sequenceDiagram
    participant Client
    participant Order as order-service
    participant Sampler
    participant Inventory as inventory-service
    Client->>Order: POST /orders
    Order->>Sampler: Bắt đầu trace
    Sampler-->>Order: Sample? quyết định ngay
    Order->>Inventory: HTTP reserve
    Inventory-->>Order: Timeout
    Order-->>Client: HTTP 503
    Note over Sampler: Quyết định đã đưa ra<br/>trước khi biết request lỗi
~~~

Nếu trace đã bị drop ở đầu, exporter không có đầy đủ spans để gửi chỉ vì response cuối cùng là HTTP 503. Đây là hạn chế nền tảng của head-based sampling theo xác suất, không phải lỗi cấu hình.

### 3.2. Parent-based sampling và trace consistency

Trong distributed tracing, quyết định sampling ở root thường cần được truyền nhất quán xuống các service. **Parent-based sampling** dùng quyết định từ parent/remote parent làm cơ sở cho child. W3C Trace Context có trace flags, trong đó sampled flag biểu thị trạng thái sampling theo quy tắc protocol.

Khi HTTP client inject `traceparent` và service nhận extract context:

- Child spans có thể kế thừa sampling decision theo parent-based policy.
- Nếu trace đã được đánh dấu không sampled, downstream không nên tùy tiện ghi riêng một nhánh gây mất nhất quán.
- Nếu mỗi service tự quyết định sampling độc lập, backend có thể nhận trace không đầy đủ hoặc các phần trace rời nhau.

Sampling nhất quán xuyên service cần cùng hiểu trace context/propagator và cấu hình sampler thích hợp. Một giá trị probability ở mỗi service không nên được coi là cơ chế tự động bảo đảm cây spans hoàn chỉnh nếu mỗi nơi đang áp dụng policy khác nhau.

### 3.3. Ưu điểm và hạn chế

**Ưu điểm:**

- Quyết định sớm giúp giảm số spans cần ghi và gửi.
- Dễ cấu hình, ít yêu cầu buffer lớn tại Collector.
- Phù hợp hệ thống có traffic lớn và ngân sách tracing cố định.

**Hạn chế:**

- Không ưu tiên được lỗi chỉ xuất hiện sau khi request bắt đầu.
- Một lỗi hiếm có thể hoàn toàn không có trace.
- Xác suất cố định có thể giữ quá nhiều traffic bình thường nhưng vẫn bỏ mất nhóm lỗi quan trọng.
- Không nên dùng sampled traces làm nguồn tính chính xác error rate hoặc SLO.

## 4. Tail-based sampling: giữ trace sau khi nhìn thấy kết quả

**Tail-based sampling** trì hoãn quyết định cho tới khi Collector đã nhận được các spans cần thiết của trace trong một khoảng thời gian. Lúc đó policy có thể kiểm tra trạng thái, latency hoặc attributes và quyết định giữ trace.

Ví dụ policy:

| Điều kiện | Quyết định mong muốn |
| --- | --- |
| Có span status ERROR | Giữ trace |
| Có span HTTP 5xx theo convention | Giữ trace nếu policy có điều kiện phù hợp |
| Trace vượt 2 giây | Giữ trace |
| Có exception cụ thể đã được phân loại | Giữ trace khi thông tin an toàn và đáng tin |
| Trace bình thường | Chỉ giữ theo xác suất nền, ví dụ 1–5% |

Điểm mạnh: trace có thể được giữ dựa trên kết quả cuối, kể cả lỗi xảy ra sau khi root span bắt đầu. Điểm đánh đổi: **Collector phải nhận, buffer và xử lý spans trước khi quyết định**, nên cần tài nguyên và routing phù hợp.

### 4.1. Tail sampling cần nhận đủ trace

Giả sử trace có spans từ order-service, inventory-service và payment-service. Nếu các spans của cùng trace được gửi tới những Collector tail-sampling instances khác nhau, mỗi instance chỉ nhìn thấy một phần trace và có thể đưa ra quyết định sai hoặc không nhất quán.

Vì vậy, triển khai tail sampling cần một cơ chế **trace-aware routing** để các spans có cùng trace ID tới cùng tail-sampling decision point, hoặc một kiến trúc gateway/agent được thiết kế rõ để đảm bảo điều đó. Load balancer round-robin thông thường không tự bảo đảm các spans cùng trace đi cùng Collector.

### 4.2. Decision wait và buffer

Tail sampler thường đợi một khoảng thời gian `decision_wait` để nhận thêm spans. Nếu thời gian quá ngắn, spans đến muộn có thể không được tính vào quyết định. Nếu quá dài, số trace đang giữ trong bộ nhớ tăng, làm tăng tài nguyên và latency export.

Các yếu tố cần sizing:

- Số trace mới mỗi giây.
- Số spans trung bình mỗi trace.
- Kích thước trung bình của span/attributes/events.
- Thời gian giữ chờ quyết định.
- Số trace tối đa/buffer capacity và tốc độ xử lý.
- Mức độ trễ hoặc out-of-order giữa các service.

Tail sampling cần theo dõi dropped traces, late spans, buffer utilization, memory pressure và quyết định giữ/loại. Không chỉ cấu hình policy rồi mặc định Collector đủ capacity cho production peak.

## 5. Cấu hình tail sampling trong OpenTelemetry Collector

Ví dụ cấu hình học tập cho Collector nhận OTLP/HTTP, batch và quyết định giữ trace có lỗi hoặc latency dài:

~~~yaml
receivers:
  otlp:
    protocols:
      http:
        endpoint: 0.0.0.0:4318

processors:
  memory_limiter:
    check_interval: 1s
    limit_mib: 512
  tail_sampling:
    decision_wait: 10s
    num_traces: 50000
    expected_new_traces_per_sec: 1000
    policies:
      - name: keep-errors
        type: status_code
        status_code:
          status_codes: [ERROR]
      - name: keep-slow
        type: latency
        latency:
          threshold_ms: 2000
      - name: baseline-sample
        type: probabilistic
        probabilistic:
          sampling_percentage: 2
  batch:
    timeout: 5s

exporters:
  debug:
    verbosity: basic

service:
  pipelines:
    traces:
      receivers: [otlp]
      processors: [memory_limiter, tail_sampling, batch]
      exporters: [debug]
~~~

Đây là cấu hình minh họa cho Collector distribution có các components tương ứng. Version cụ thể có thể thay đổi schema hoặc sự hỗ trợ của processor. Trong production cần kiểm tra tài liệu đúng phiên bản, memory limiter, retry, exporter thật và trace-aware routing.

### 5.1. Ý nghĩa các policy

- `status_code` giữ trace có span status ERROR theo dữ liệu Collector nhận được.
- `latency` giữ trace có latency vượt ngưỡng cấu hình.
- `probabilistic` tạo một tỷ lệ nền cho traces còn lại nhằm quan sát traffic bình thường.

Khi ghép nhiều policies, cần xác định semantics kết hợp (giữ nếu match một trong các policy hoặc cách processor/version xử lý). Ví dụ trên minh họa ý tưởng **ưu tiên lỗi/chậm và giữ một mẫu nền**; kiểm tra tài liệu Collector version để bảo đảm các policy được phối hợp như mong đợi.

### 5.2. Lỗi application có được đánh dấu ERROR không?

Tail sampler theo status chỉ có thể giữ trace lỗi nếu span status/attributes đã được instrumentation ghi đúng. Một controller trả HTTP 500 nhưng span vẫn có status UNSET hoặc OK do cách xử lý exception/response, policy `status_code` có thể không nhận ra.

Do đó:

1. Xác minh HTTP server instrumentation map status code/exception như thế nào.
2. Kiểm tra span thật trong Collector debug/test exporter.
3. Đảm bảo lỗi nghiệp vụ được ghi vào span status/event theo semantics phù hợp.
4. Với yêu cầu giữ HTTP 5xx, cân nhắc thêm policy theo span attributes/HTTP status nếu component hỗ trợ và attribute thực tế có mặt.

Đừng giả định mọi lỗi đều tạo status ERROR. Một request có lỗi được xử lý thành fallback 200 cũng có thể cần được đánh dấu trong nghiệp vụ, nhưng policy phải được thiết kế rõ ràng.

### 5.3. Tail sampler không thể giữ spans chưa đến Collector

Nếu một service không có exporter, SDK drop span trước khi gửi, network lỗi hoặc một nhánh bị chặn, Collector không thể xét các spans đó. Tail sampling là quyết định dựa trên **dữ liệu đã nhận**, không phải phép khôi phục trace toàn hệ thống.

## 6. Kết hợp head và tail sampling

Một cách triển khai thường gặp là để SDK gửi đủ dữ liệu cần thiết tới Collector trong phạm vi kiểm soát, rồi để tail sampler ưu tiên trace lỗi/chậm và sample phần bình thường. Tuy nhiên, nếu head sampler ở SDK đã loại phần lớn trace trước export, tail sampler chỉ có thể ra quyết định trên tập còn lại.

| Kiến trúc | Ưu điểm | Hạn chế |
| --- | --- | --- |
| Head sampling 10%, không tail | Đơn giản, giảm dữ liệu sớm | Chỉ khoảng 10% trace đủ điều kiện; lỗi có thể bị bỏ |
| Head sampling 100% + tail sampling | Collector có đầy đủ cơ hội quan sát lỗi/chậm | Tăng network, Collector buffer và CPU |
| Head sampling cao hơn 0% + tail sampling | Giảm một phần dữ liệu trước Collector | Không thể giữ các trace đã bị head drop |
| Chỉ tail sampling nhưng upstream component đã drop spans | Không có lợi ích nếu phần quan trọng không được gửi | Cần thiết kế rõ SDK sampler/recording và routing |

Trong một số triển khai, dùng head sampler giữ phần lớn traces cho tail decision, nhưng có thể tạo chi phí lớn ngay tại application và network. Cần đo throughput và memory trước khi áp dụng trên toàn hệ thống.

### 6.1. Đặt policy theo ưu tiên kinh doanh

Không phải mọi lỗi đều có giá trị điều tra như nhau. Có thể ưu tiên:

1. **Lỗi nghiêm trọng:** exception hoặc status ERROR trên luồng thanh toán/đơn hàng.
2. **Latency cao:** request vượt ngưỡng dịch vụ hoặc một dependency timeout.
3. **Luồng quan trọng:** một số route hoặc operation quan trọng được xác định bằng attribute ổn định.
4. **Baseline bình thường:** một tỷ lệ nhỏ để so sánh với traces lỗi.

Không đưa email, user ID hoặc payload vào policy attributes. Dùng route template, service name, operation name và các giá trị hữu hạn.

## 7. Spring Boot sampling và trace context propagation

Spring Boot với Micrometer Tracing có cấu hình xác suất sampling:

~~~yaml
management:
  tracing:
    sampling:
      probability: 0.10
~~~

Đây là ví dụ head-based sampling probability. Đối với tail sampling ở Collector, Spring Boot không tự thay thế Collector processor. Hai phần cần được cấu hình và giám sát riêng.

### 7.1. W3C traceparent và sampled flag

Một header minh họa:

~~~http
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
~~~

Trong header này, flags byte có sampled bit được bật ở ví dụ. Remote service dùng context được extract để tiếp tục trace theo propagator/sampler. Với parent-based policy, quyết định sampling thường được kế thừa từ remote parent.

**Baggage và sampled flag có vai trò khác nhau:** baggage truyền metadata; trace flags mang trạng thái context tracing. Không dùng baggage để quyết định service có nên ghi span hoặc có được cấp quyền.

### 7.2. Khi downstream có lỗi nhưng root đã bị head-drop

Nếu root trace bị head sampler drop và parent-based sampler lan quyết định không-record xuống downstream, service sau không thể tự tạo ra một trace hoàn chỉnh để tail sampler giữ lỗi. Một sampler độc lập ở downstream có thể tạo recorded spans riêng, nhưng khi đó trace có thể thiếu root/parent và cây không đầy đủ.

Đây là lý do chiến lược tail sampling thường yêu cầu một cấu hình thu thập đủ spans trước quyết định cuối. Đừng trộn parent-based head sampling với kỳ vọng tail sampler sẽ phục hồi mọi lỗi bị drop.

## 8. Sampling và sự thật thống kê: metrics vẫn là nguồn SLI

Một tập traces đã sampling **không phải mẫu số đáng tin cậy mặc định** để tính error rate hoặc SLO toàn hệ thống. Sampling có thể không đồng đều theo service, route, error status hoặc policy; tail sampling còn có chủ đích giữ trace lỗi nhiều hơn trace bình thường.

Ví dụ tail policy giữ 100% lỗi và 2% trace bình thường. Tỷ lệ lỗi trong trace backend chắc chắn sẽ cao hơn tỷ lệ lỗi thật trong request traffic. Đây là kết quả đúng theo policy ưu tiên lỗi, nhưng không thể dùng nó làm error rate.

### 8.1. Dùng metrics cho tỷ lệ lỗi và latency distribution

Ví dụ PromQL request error ratio dựa trên HTTP counter:

~~~promql
sum(rate(http_server_requests_seconds_count{
  service="order-service",
  status=~"5.."
}[5m]))
/
sum(rate(http_server_requests_seconds_count{
  service="order-service"
}[5m]))
~~~

Tên metric/labels phải được kiểm tra theo output thực tế của Prometheus registry. Micrometer/Spring Boot có thể dùng label như `application`, `uri`, `status` hoặc `outcome` tùy version/instrumentation; không tự giả định label `service` tồn tại.

Với histogram classic, p95 có thể được tính:

~~~promql
histogram_quantile(
  0.95,
  sum by (le) (
    rate(http_server_requests_seconds_bucket{
      uri="/orders"
    }[5m])
  )
)
~~~

Metrics được instrument/tổng hợp không phụ thuộc việc trace của request có được lưu hay không. Do đó, hãy dùng metrics cho request rate, error ratio, p95/p99 và SLO; dùng traces sampling để điều tra những trường hợp cụ thể.

### 8.2. Exemplars nối metrics tới traces

Một số registry/backend hỗ trợ **exemplars** để gắn tham chiếu trace vào metric sample hoặc histogram bucket. Khi được cấu hình đúng, người vận hành có thể mở trace mẫu từ panel metrics. Exemplar không làm thay đổi công thức error rate và không nên được thay bằng cách đưa trace ID vào labels.

## 9. Kết hợp error sampling với logs, baggage và cardinality

Khi một trace lỗi được giữ, span attributes và logs nên cung cấp đủ thông tin để điều tra mà không phát tán PII/secrets.

~~~mermaid
flowchart TD
    Error["Request lỗi / timeout"] --> Metrics["Metrics: error rate, p95, request rate"]
    Error --> Trace["Trace sampling policy giữ trace"]
    Trace --> Span["Span status + route + dependency"]
    Error --> Log["Logs: error code + traceId/spanId"]
    Trace --> Backend["Trace backend"]
    Span --> Backend
    Metrics --> Dashboard["Dashboard / alert"]
    Log --> LogBackend["Log backend"]
    Dashboard -. "Chọn khoảng thời gian bất thường" .-> Backend
    LogBackend -. "Tra traceId" .-> Backend
~~~

### 9.1. Baggage không phải điều kiện để giữ lỗi

Baggage có thể mang thông tin như `orders.channel=web` nếu field đã được xác minh và được phép propagate. Nhưng không đặt `error=true` vào baggage chỉ để tail sampler tìm lỗi: lỗi là trạng thái span/exception hoặc HTTP outcome, cần ghi nhận ở đúng span/attribute theo instrumentation semantics.

Không tin `priority=high` hoặc `tenant.tier=premium` do client gửi để áp dụng sampling ưu tiên nếu chưa xác thực. Một client độc hại có thể cố tình làm mọi request được giữ, gây chi phí lớn.

### 9.2. Cardinality và privacy

Không đưa `request.id`, `user.id`, email, token hoặc payload vào metric labels. Span attributes có thể hỗ trợ điều tra chi tiết hơn nhưng vẫn cần privacy review, giới hạn kích thước và quyền truy cập. Sampling không phải cơ chế bảo mật: nếu field nhạy cảm được export, một trace được giữ vẫn có thể làm lộ dữ liệu.

### 9.3. Logs cần correlation ngay cả khi trace không được giữ

Một log event có thể được ghi kèm trace ID/span ID trong active context, nhưng backend không tìm thấy trace vì sampler drop hoặc exporter lỗi. Giữ log theo policy riêng, không giả định mọi trace ID trong logs đều có trace tương ứng trong backend. Không lưu raw request headers hoặc toàn bộ baggage trong logs.

## 10. Kiểm thử sampling theo từng tầng

Sampling cần kiểm thử cả quyết định SDK, policy Collector và tính đúng đắn của metrics/logs.

| Tầng kiểm thử | Mục tiêu | Bằng chứng |
| --- | --- | --- |
| Sampler unit test | Quy tắc head sampler theo input/context | Quyết định record/drop đúng |
| Tracing SDK test | Recording spans và parent-based behavior | Trace IDs, sampling flags, exported spans |
| Collector policy test | Status/latency/probabilistic policy | Trace lỗi được giữ, trace baseline được sample |
| Pipeline integration | SDK → Collector → backend | Trace thật được truy vấn theo ID |
| Metrics regression | Error rate/p95 không phụ thuộc sampling | HTTP metrics vẫn đầy đủ theo instrumentation |
| Load/capacity test | Collector queue/memory/throughput | Không drop ngoài ngân sách và độ trễ hợp lý |

### 10.1. Kiểm tra Spring Boot sampling probability

Ở môi trường test, có thể cấu hình sampling 1.0 để quan sát tất cả traces qua SDK/Collector. Sau đó cấu hình xác suất thấp hơn và tạo đủ nhiều request để quan sát tỷ lệ gần với kỳ vọng. Không nên kiểm thử bằng một vài request rồi kết luận chính xác 10% sẽ được giữ; lấy mẫu xác suất có biến động.

### 10.2. Kiểm thử tail sampling policy

Với Collector chạy trong test:

1. Tạo trace có span status ERROR.
2. Tạo trace bình thường dưới ngưỡng latency.
3. Tạo trace bình thường vượt ngưỡng latency.
4. Gửi đủ spans của từng trace tới cùng tail-sampling instance.
5. Đợi quá `decision_wait` và kiểm tra trace backend/test exporter.
6. Xác nhận trace error và trace slow được giữ; trace bình thường chỉ được giữ theo baseline probability.
7. Thử gửi span muộn sau decision window để hiểu behavior và metrics late/drop của version đang dùng.

Không hard-code kỳ vọng trace bình thường luôn bị drop nếu baseline sampling khác 0. Dùng seed/deterministic test setup hoặc policy riêng nếu cần assertion không ngẫu nhiên.

### 10.3. Kiểm tra tính đầy đủ giữa service

Tạo request từ order-service sang inventory-service. Kiểm tra cùng trace ID, parent-child relation và spans của cả hai service được gửi tới đúng tail-sampler. Nếu trace bị phân tán qua nhiều Collector instances, test phải xác minh routing theo trace ID thay vì chỉ kiểm tra một lần export thành công.

### 10.4. Kiểm thử metrics độc lập

Tạo một tập request đã biết gồm thành công và lỗi, xác minh HTTP Counter/Timer ghi nhận đầy đủ theo instrumentation. Sau đó thay sampling probability và kiểm tra **request metrics không biến thành tỷ lệ của sampled traces**. Đây là regression quan trọng khi nhóm vận hành thay đổi policy sampling.

## 11. Troubleshooting sampling cho lỗi

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| Lỗi hiếm không có trace | Head sampling bỏ trace ở đầu | Tăng sampling có mục tiêu hoặc dùng tail sampling |
| Trace có root nhưng thiếu child | Downstream instrumentation/exporter/propagation lỗi | Kiểm tra W3C context và export mỗi service |
| Trace backend có tỷ lệ lỗi rất cao | Tail policy ưu tiên error | Không dùng trace set để tính error rate |
| Collector không giữ trace lỗi | Span status không phải ERROR hoặc attribute policy không khớp | Xem span data thực, exception/status mapping |
| Trace lỗi đã mất trước Collector | Head sampler hoặc SDK không recording | Kiểm tra SDK sampler/recording config |
| Tail decision không nhất quán | Spans cùng trace tới nhiều Collector instances | Trace-aware routing/load balancing |
| Spans đến muộn bị bỏ | decision_wait quá ngắn hoặc latency giữa services | Đo span arrival delay, chỉnh wait/capacity |
| Collector OOM/drops tăng | num_traces/buffer/attributes quá lớn | Sizing, memory limiter, scale và sampling |
| Bình thường bị giữ quá nhiều | Baseline probabilistic policy cao hoặc policy OR rộng | Review policy composition và expected volume |
| Request metrics thiếu sau đổi sampling | Instrumentation metrics lỗi hoặc query sai | So sánh MeterRegistry/Prometheus độc lập |
| Log có trace ID nhưng UI không có trace | Trace bị drop hoặc exporter/backend lỗi | Tách sampling decision khỏi export pipeline |
| Trace lỗi bị giữ nhưng không đủ thông tin | Attributes thiếu hoặc bị sanitize quá mức | Thêm metadata hữu hạn, an toàn và cần thiết |

### 11.1. Trình tự điều tra

1. **Xác nhận lỗi qua metrics:** HTTP error count, request rate, latency và route.
2. **Kiểm tra policy sampling:** head probability, parent-based behavior và tail rules.
3. **Xác nhận span được ghi nhận:** span status, attributes và trace context ở SDK/Collector.
4. **Kiểm tra export:** OTLP exporter errors, queue, Collector receiver và pipeline.
5. **Kiểm tra trace-aware routing:** tất cả spans của trace có tới cùng tail sampler không?
6. **Kiểm tra decision window/capacity:** spans muộn, memory pressure và dropped traces.
7. **Mở logs tương quan:** theo trace ID nếu trace được lưu; nếu không, dùng log/error code và metrics để điều tra.

Không kết luận sampler không hoạt động chỉ vì trace chưa xuất hiện ngay; batching và decision wait tạo độ trễ. Ngược lại, đợi mãi cũng không giải quyết được endpoint exporter sai hoặc Collector pipeline không nối.

## 12. Production checklist và vận hành ngân sách

| Tiêu chí | Bằng chứng cần có |
| --- | --- |
| Mục tiêu sampling rõ ràng | Biết cần giữ lỗi hiếm, latency cao hay baseline traffic |
| Head/tail strategy đúng với nhu cầu | Hiểu quyết định xảy ra lúc nào |
| Parent-based behavior nhất quán | W3C trace context và sampler giữa services tương thích |
| Lỗi được đánh dấu đúng trên spans | Span status/HTTP attributes đã được xác minh |
| Tail routing theo trace ID | Các spans của cùng trace đến cùng decision point |
| Tail buffer được sizing | decision_wait, num_traces, memory và peak traffic có cơ sở |
| Baseline sampling đủ đại diện | Có mẫu traffic bình thường để so sánh |
| Exporter/Collector được giám sát | Error, retry, dropped spans, late spans và receiver health |
| Metrics SLI độc lập với trace sampling | Error rate, request rate và latency lấy từ metrics phù hợp |
| Không đưa PII/secrets vào telemetry | Privacy review, allowlist và redaction |
| Cardinality được kiểm soát | Không có ID động trong metric labels |
| Graceful shutdown có kế hoạch | Processor có cơ hội flush trong giới hạn |
| Test failure/slow/baseline cases | Có test policy giữ đúng trace |
| Có runbook khi trace bị thiếu | Biết phân biệt sampling, propagation, exporter và backend |

### 12.1. Ước lượng dung lượng tail sampler

Một ước lượng thô:

\[
\text{buffer size} \approx
\text{new traces/sec} \times \text{decision wait (sec)}
\]

Ví dụ 800 trace mới/giây và decision wait 10 giây có khoảng **8.000 trace đang chờ quyết định** tại một thời điểm, chưa tính spans mỗi trace, biến động traffic, retry, late arrival và overhead của data structure. Nếu trung bình 12 spans/trace, Collector còn phải giữ khoảng 96.000 spans cho lượng trace đó.

Đây chỉ là phép ước lượng sơ bộ. Sizing thật phải dựa trên kích thước span, attributes/events, concurrency, peak rate, memory overhead và chính sách của phiên bản Collector. Tham số `num_traces` phải có headroom; không đặt đúng bằng phép nhân trung bình rồi coi đó là an toàn.

### 12.2. Sampling policy thay đổi cũng là thay đổi vận hành

Khi tăng tỷ lệ sampling hoặc thay policy giữ lỗi:

- Theo dõi ingest rate, backend cost và retention.
- Đo exporter queue/dropped spans và Collector memory.
- So sánh tỷ lệ trace giữ theo từng policy.
- Xác minh metrics SLI không đổi semantics.
- Ghi nhận mốc thời gian thay policy để giải thích biến động số lượng traces.

Không so sánh “số trace lỗi” giữa hai tuần mà không xét thay đổi sampling policy.

## 13. Bài thực hành: giữ trace lỗi và latency cao

**Bối cảnh:** `order-service` xử lý `POST /orders` và gọi `inventory-service`. Lưu lượng bình thường lớn, trong khi timeout xảy ra hiếm. Nhóm cần giữ traces của lỗi và request chậm hơn 2 giây, cùng một mẫu nhỏ của traffic bình thường.

**Nhiệm vụ:**

1. Cấu hình Spring Boot Actuator, Micrometer Tracing và OpenTelemetry bridge; xác minh HTTP server/client instrumentation.
2. Bật head sampling 100% trong môi trường thử nghiệm để kiểm tra cây trace cơ sở.
3. Thiết lập Collector OTLP receiver và tail-sampling processor với policy status ERROR, latency 2.000 ms và baseline probability 2%.
4. Đảm bảo spans của cùng trace được route tới cùng tail-sampling instance.
5. Tạo 10 request thành công nhanh, 2 request chậm hơn 2 giây và 1 request lỗi; chờ qua decision window.
6. Kiểm tra Collector/export backend có giữ trace lỗi và trace chậm; xác nhận baseline có thể giữ một số trace bình thường.
7. Kiểm tra span status/HTTP attributes thật; nếu trace lỗi không match, xác định instrumentation đang đánh dấu lỗi ra sao.
8. Giảm head sampling của SDK xuống 10%, quan sát rằng tail sampler không thể giữ các trace đã bị SDK drop.
9. Gửi một tập request có số thành công/lỗi đã biết; xác minh Prometheus error ratio vẫn phản ánh toàn bộ request theo instrumentation.
10. Theo dõi memory, queue, late spans, exporter failures khi tăng traffic thử nghiệm.
11. Viết runbook khi trace lỗi không xuất hiện: phân biệt head drop, tail policy mismatch, routing, exporter và backend.

**Kết quả mong đợi:** cấu hình Spring Boot và Collector, traces lỗi/slow được giữ theo policy ở môi trường test, metrics SLI không phụ thuộc tập trace đã sampling, cùng báo cáo ngắn về chi phí, giới hạn và các trường hợp có thể mất trace.

## 14. Ghi nhớ

**Head-based sampling** quyết định sớm khi trace bắt đầu; nó đơn giản và giảm dữ liệu trước export nhưng không biết một request sẽ lỗi ở cuối. **Tail-based sampling** đợi Collector nhận spans rồi có thể ưu tiên lỗi hoặc latency cao, nhưng cần buffer, decision window, capacity và routing theo trace ID. Nếu SDK đã drop trace, Collector không thể phục hồi dữ liệu đó.

Để lấy được traces hữu ích cho sự cố, hãy xác minh span status/attributes, parent-based propagation, sampling policy, exporter và Collector pipeline như một chuỗi. **Metrics vẫn là nguồn chính cho request rate, error ratio, latency distribution và SLO**; traces đã sampling dùng để điều tra từng trường hợp, logs cung cấp sự kiện và correlation. Bảo vệ dữ liệu, kiểm soát cardinality và giám sát chính telemetry pipeline là điều kiện vận hành production.

**Tài liệu tham khảo:**

- [Spring Boot — Tracing](https://docs.spring.io/spring-boot/reference/actuator/tracing.html)
- [Spring Boot — Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html)
- [Micrometer Tracing — Reference](https://docs.micrometer.io/tracing/reference/)
- [OpenTelemetry — Sampling](https://opentelemetry.io/docs/concepts/sampling/)
- [OpenTelemetry Collector — Tail Sampling Processor](https://github.com/open-telemetry/opentelemetry-collector-contrib/tree/main/processor/tailsamplingprocessor)
- [OpenTelemetry Collector — Configuration](https://opentelemetry.io/docs/collector/configuration/)
- [W3C — Trace Context](https://www.w3.org/TR/trace-context/)
