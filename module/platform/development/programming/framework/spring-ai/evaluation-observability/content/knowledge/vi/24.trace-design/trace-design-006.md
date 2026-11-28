# Sampling theo lưu lượng và nhu cầu điều tra

Khi ứng dụng Spring AI bắt đầu nhận nhiều request, giữ lại 100% traces có thể làm tăng đáng kể dung lượng export, chi phí lưu trữ và tải lên collector. Nhưng giảm sampling quá mạnh lại khiến nhóm vận hành không tìm thấy trace của lỗi hiếm, tool call bất thường hoặc một lần RAG trả lời sai. Câu hỏi thiết kế không chỉ là “lấy mẫu bao nhiêu phần trăm?” mà là **giữ trace nào để vừa quan sát được xu hướng theo lưu lượng, vừa có đủ bằng chứng khi cần điều tra?**

Bài học thuộc chương **Thiết kế trace** của module `SPRING_AI_EVALUATION_OBSERVABILITY`. Module học cách đánh giá chất lượng ứng dụng Spring AI bằng dataset, relevance, fact checking và kiểm thử RAG/tool calling; đồng thời theo dõi metrics, traces, chi phí và độ trễ qua các phiên bản prompt, model và pipeline. Vì vậy, sampling cần được thiết kế cùng với SLO, evaluation coverage và ngân sách telemetry.

Sau bài học, bạn có thể:

- Phân biệt head sampling, tail sampling, parent-based sampling và trace ID ratio sampling.
- Chọn sampling rate theo lưu lượng, chi phí, độ hiếm của lỗi và mục đích điều tra.
- Cấu hình sampling cơ bản trong Spring Boot/Micrometer và hiểu vai trò của OpenTelemetry Collector.
- Giữ các spans của một trace nhất quán qua nhiều service.
- Kết hợp sampling với error/latency policies, canary release và incident investigation.
- Bảo đảm sampling không làm sai pass rate, valid coverage hoặc kết quả evaluation dataset.

## 1. Sampling giải quyết bài toán nào?

Một **trace** có thể chứa HTTP server span, RAG spans, database/client spans, model calls, tool executions và các spans của dịch vụ downstream. Khi traffic tăng, số trace được tạo mỗi giây tăng theo. Sampling chọn một phần traces để lưu/đọc chi tiết.

Sampling giúp:

- Giảm lượng telemetry gửi từ ứng dụng tới collector/backend.
- Giảm dung lượng lưu trữ và chi phí truy vấn.
- Giữ đủ traces đại diện cho lưu lượng thông thường.
- Ưu tiên traces lỗi, chậm hoặc thuộc operation có rủi ro cao nếu dùng policy phù hợp.
- Duy trì khả năng điều tra thay đổi prompt, model, index và pipeline.

Sampling **không phải** cơ chế đếm request, đánh giá chất lượng hoặc thay thế metrics. Nếu chỉ giữ 10% traces thì không thể lấy số traces đã lưu làm tổng request count, cũng không thể tính evaluation pass rate bằng số verdict xuất hiện trong những traces được sample.

### 1.1. Bốn lớp dữ liệu cần phân biệt

| Dữ liệu | Vai trò | Có phụ thuộc trace sampling? |
|---|---|---|
| Metrics | Đếm request, error, latency distribution, token/cost | Không nên |
| Traces | Điều tra một execution cụ thể | Có |
| Logs | Chi tiết sự kiện/lỗi, thường gắn trace/span ID | Có thể, tùy pipeline |
| Evaluation results | PASS/FAIL/INVALID/ERROR và provenance của từng case | Không |

Ví dụ: API nhận 10.000 request, sampling 10% nên backend chỉ lưu khoảng 1.000 traces nếu xác suất lấy mẫu áp dụng đều. Counter request vẫn phải ghi nhận 10.000; histogram latency vẫn phải nhận toàn bộ observations; evaluation result store vẫn phải lưu toàn bộ cases thuộc run.

### 1.2. Sampling rate là xác suất giữ trace

Nếu xác suất lấy mẫu là \(p\), với \(N\) root traces độc lập, số trace kỳ vọng được giữ:

\[
E[\text{sampled traces}] = N \times p
\]

Ví dụ \(N=100.000\), \(p=0{,}05\), kỳ vọng giữ khoảng 5.000 traces. Đây là kỳ vọng thống kê, không cam kết chính xác mỗi ngày có đúng 5.000 trace.

Với traffic có nhóm rất khác nhau, một tỷ lệ chung có thể bỏ sót nhóm ít request. Ví dụ tool execution chỉ xuất hiện ở 0,2% traffic; sampling ngẫu nhiên 1% có thể không giữ được đủ traces tool để điều tra. Cần cân nhắc stratified sampling hoặc tail policies cho operation đó.

## 2. Hai thời điểm ra quyết định: head và tail sampling

Điểm khác biệt quan trọng nhất là **sampling quyết định trước hay sau khi biết kết quả của trace**.

### 2.1. Head sampling

Head sampler quyết định ở lúc trace/root span bắt đầu. Ứng dụng/SDK biết một số metadata ban đầu như service, operation, parent context hoặc trace ID, nhưng chưa biết request sẽ timeout, trả HTTP 500, mất 4 giây hay được judge chấm FAIL.

```text
Request bắt đầu
    |
    v
SDK sampler quyết định giữ/bỏ
    |
    +---- DROP: spans không được export theo sampling decision
    |
    +---- RECORD: spans được ghi và export
                   |
                   v
             RAG / model / tool
                   |
                   v
             kết quả cuối cùng
```

Ưu điểm:

- Quyết định sớm, giảm overhead và traffic telemetry ngay tại ứng dụng.
- Dễ triển khai ở SDK/agent, ít phụ thuộc collector.
- Có thể dùng trace ID ratio sampling để giữ một tỷ lệ ổn định.
- Parent-based sampling giúp các services trong cùng trace tuân theo quyết định của parent.

Giới hạn:

- Không thể giữ riêng mọi trace lỗi/chậm nếu lỗi chỉ xuất hiện sau khi quyết định đã được đưa ra.
- Nếu root bị drop, các child thường không thể tự xuất hiện thành một trace đầy đủ.
- Một tỷ lệ ngẫu nhiên thấp có thể bỏ qua lỗi hiếm hoặc tool path hiếm.

### 2.2. Tail sampling

Tail sampler quyết định sau khi collector nhận đủ hoặc đủ phần lớn spans của trace. Nó có thể xem trạng thái cuối, duration, attributes, span errors và số lượng spans để chọn giữ hoặc bỏ.

```text
Application SDK (record/export)
          |
          v
OpenTelemetry Collector
          |
          v
Tập hợp spans theo trace ID
          |
          v
Chờ decision window / trace completion
          |
          v
Áp dụng policy:
  - error
  - latency cao
  - operation quan trọng
  - tỷ lệ nền
          |
     +----+----+
     |         |
    KEEP      DROP
```

Ưu điểm:

- Có thể giữ trace có error hoặc latency cao dù ban đầu chưa biết kết quả.
- Có thể ưu tiên operation đặc biệt như tool execution hoặc RAG pipeline.
- Cho phép kết hợp nhiều policy và một tỷ lệ nền.

Chi phí và giới hạn:

- Ứng dụng vẫn phải record/export spans tới collector; tail sampling không loại bỏ toàn bộ overhead phía SDK/network trước collector.
- Collector cần bộ nhớ để giữ traces trong decision window.
- Trace spans có thể đến trễ hoặc không đến đủ; policy có thể quyết định trên trace không hoàn chỉnh.
- Cần phân phối tất cả spans của cùng trace tới cùng tail-sampling instance/shard (trace affinity).
- Nếu trace kéo dài, streaming hoặc async job lâu, decision window và memory phải được tính toán phù hợp.

### 2.3. So sánh nhanh

| Tiêu chí | Head sampling | Tail sampling |
|---|---|---|
| Thời điểm quyết định | Khi root span bắt đầu | Sau khi collector nhận spans |
| Biết error cuối cùng? | Thường chưa | Có thể |
| Biết latency tổng? | Chưa | Có thể |
| Giảm export từ SDK? | Có | Thường không, SDK vẫn gửi đến collector |
| Độ phức tạp hạ tầng | Thấp hơn | Cao hơn |
| Yêu cầu memory/trace affinity ở collector | Không bắt buộc | Có |
| Phù hợp | Baseline traffic sampling, giảm telemetry sớm | Giữ lỗi/chậm và điều tra theo outcome |

Hai phương pháp có thể kết hợp. Ví dụ SDK dùng head sampling 100% tới collector nội bộ, collector tail-sample để giữ lỗi/chậm và 5% traffic bình thường. Cần lưu ý nếu head sampler đã drop 90% trước collector thì tail sampler không thể khôi phục các traces đó.

## 3. Các chiến lược sampling thường dùng

### 3.1. Trace ID ratio sampling

Trace ID ratio sampler chọn trace dựa trên một tỷ lệ xác định từ trace ID. Với cùng cấu hình và trace ID, quyết định thường ổn định, giúp các dịch vụ có thể thống nhất sampled decision khi dùng parent-based propagation.

Ví dụ:

- 100%: giữ tất cả traces.
- 20%: giữ khoảng một phần năm.
- 5%: giữ khoảng một phần hai mươi.
- 1%: giữ khoảng một phần trăm.

Không nên tự viết random sampling độc lập ở từng span. Nếu root và child tự bốc thăm riêng, một trace có thể chỉ còn một số spans, làm đứt quan hệ và khó điều tra.

### 3.2. Parent-based sampling

Parent-based sampler xem quyết định sampled của parent context để tạo child spans nhất quán. Nếu parent được sample, child thường tiếp tục ghi; nếu parent không được sample, child thường không tự xuất hiện.

Đây là cơ chế quan trọng trong hệ thống nhiều service:

```text
answer-api (root decision: sampled)
  └── retriever-service (child follows parent)
      └── vector-db client (child follows parent)
  └── model-provider client (child follows parent)
```

Nếu mỗi service tự chọn tỷ lệ độc lập, một trace có thể có root ở answer-api nhưng thiếu retriever hoặc model spans. Hãy chọn một điểm quyết định root sampling rõ ràng và propagate sampled flag xuyên dịch vụ.

### 3.3. Rate-limited sampling

Rate-limited sampler giới hạn số traces được giữ trong một khoảng thời gian, ví dụ tối đa một số trace mỗi giây hoặc mỗi phút. Nó giúp bảo vệ hệ thống khi traffic tăng đột biến.

Nhưng rate limit thuần túy có thể làm lệch mẫu:

- Traffic burst có thể chiếm hết quota.
- Một operation hiếm có thể bị loại nếu đến sau operation phổ biến.
- Một service nhiều traffic có thể chiếm toàn bộ ngân sách nếu không phân chia.

Nếu cần fairness, chia ngân sách theo operation/service hoặc dùng tail policies ưu tiên error/critical path. Đừng coi rate-limited sample là mẫu thống kê ngẫu nhiên hoàn toàn.

### 3.4. Stratified sampling

Stratified sampling chia traffic thành các nhóm có ý nghĩa rồi lấy mẫu theo tỷ lệ riêng:

| Nhóm | Sampling rate minh họa | Lý do |
|---|---:|---|
| Answer API thông thường | 2% | Traffic lớn, có metrics nền |
| RAG pipeline | 5% | Cần xem retrieval/source path |
| Tool-assisted answer | 20% | Nhánh ít gặp, khó debug |
| Admin/critical workflow | 50% hoặc 100% theo policy | Tác động nghiệp vụ cao |
| Evaluation worker | Theo run/incident | Cần provenance cho case |

Các tỷ lệ trên chỉ là ví dụ. Khi chia nhóm, dùng thuộc tính operation/route/feature đã chuẩn hóa và ít nhạy cảm. Không phân tầng theo raw query, user ID hoặc tenant ID làm nổ cardinality.

### 3.5. Adaptive sampling

Adaptive sampling điều chỉnh tỷ lệ theo traffic, lỗi, độ trễ hoặc ngân sách telemetry. Ví dụ khi traffic tăng gấp 5, hệ thống giảm baseline rate để giữ export volume trong budget. Khi incident được bật, một nhóm operation có thể tăng tỷ lệ tạm thời.

Adaptive policy cần:

- Rate tối thiểu để vẫn có mẫu nền.
- Rate tối đa để tránh quá tải.
- Hysteresis/cooldown để không dao động liên tục.
- Giới hạn theo service/operation để không nhóm nào chiếm hết budget.
- Version/config ID để biết trace được lấy mẫu theo policy nào.
- Audit/expiry cho chế độ tăng sampling trong incident.

Không tự điều chỉnh sampling dựa trên dữ liệu nhạy cảm hoặc verdict chưa được xác thực. Cần giữ metrics độc lập để policy có đầu vào tin cậy.

## 4. Chọn sampling rate theo lưu lượng và ngân sách

Không có một tỷ lệ sampling đúng cho mọi ứng dụng. Hãy bắt đầu từ **ngân sách telemetry** và **mức độ cần điều tra**.

### 4.1. Ước tính số traces và dung lượng

Một mô hình ước lượng đơn giản:

\[
\text{traces/day} =
\text{requests/day} \times p
\]

\[
\text{bytes/day} \approx
\text{traces/day} \times
\text{average spans/trace} \times
\text{average bytes/span}
\]

Ví dụ giả định:

- 2.000.000 requests/ngày.
- Sampling rate \(p=0{,}02\) (2%).
- Trung bình 12 spans/trace.
- Mỗi span sau serialization trung bình 1,5 KB.

Khi đó:

\[
2.000.000 \times 0{,}02 = 40.000
\text{ sampled traces/day}
\]

\[
40.000 \times 12 \times 1{,}5
= 720.000\text{ KB/day}
\]

Tức khoảng 720 MB/ngày theo đơn vị thập phân, chưa tính batch overhead, compression, indexes, replication, retention và logs. Đây chỉ là ước lượng ban đầu; hãy đo kích thước thực tế ở collector/backend.

### 4.2. Xác định budget theo mục đích

| Mục đích | Câu hỏi cần trả lời | Sampling gợi ý |
|---|---|---|
| Baseline vận hành | Latency/error phân bố thế nào? | Tỷ lệ ổn định đủ đại diện |
| Điều tra release | Phiên bản mới thay đổi behavior ra sao? | Tăng sample cho canary/variant trong thời gian giới hạn |
| Điều tra lỗi hiếm | Có trace cho lỗi tool/RAG đặc biệt không? | Tail sampling theo error hoặc operation |
| Security/critical workflow | Có cần audit từng operation không? | Dùng audit log/event store phù hợp; không mặc định coi traces là audit ledger |
| Evaluation dataset | Có đủ kết quả cho mọi case không? | Ghi toàn bộ result; không sampling evaluation records |

### 4.3. Sampling rate phải gắn với mục tiêu thống kê

Nếu muốn ước lượng tỷ lệ lỗi, mẫu quá nhỏ sẽ có khoảng bất định lớn. Với \(n\) observations độc lập, sai số chuẩn gần đúng của tỷ lệ \(\hat p\) là:

\[
SE \approx \sqrt{\frac{\hat p(1-\hat p)}{n}}
\]

Ví dụ nếu tỷ lệ lỗi khoảng 1% và chỉ có 100 sampled traces, có thể chỉ thấy một lỗi hoặc không thấy lỗi nào. Không nên kết luận lỗi đã biến mất chỉ vì sample không ghi nhận. Metrics request/error counters trên toàn traffic là nguồn tốt hơn để theo dõi tỷ lệ; traces giúp giải thích từng trường hợp.

### 4.4. Dành ngân sách riêng cho operation hiếm

Một hệ thống Spring AI có thể có:

- 95% direct answer hoặc cached answer.
- 4% RAG retrieval.
- 0,8% tool-assisted flow.
- 0,2% fallback hoặc multi-hop flow.

Nếu dùng sampling 1% cho tất cả, số trace tool/fallback có thể rất thấp. Có thể phân bổ sampling rate theo operation root, hoặc dùng tail sampling để giữ các traces có span tool/fallback. Theo dõi **số lượng gốc** của mỗi nhóm bằng metrics để biết số trace được giữ có đủ cho mục đích điều tra không.

## 5. Cấu hình head sampling trong Spring Boot và OpenTelemetry

### 5.1. Spring Boot Micrometer Tracing

Trong các phiên bản Spring Boot hỗ trợ Micrometer Tracing sampling property, có thể cấu hình xác suất sampling:

```yaml
management:
  tracing:
    sampling:
      probability: 0.10
```

Giá trị `0.10` biểu thị tỷ lệ head sampling 10% cho root traces theo cấu hình mặc định của tracing bridge. Cần xác minh property và hành vi cụ thể theo Spring Boot version/bridge (Brave hoặc OpenTelemetry) đang sử dụng. Không copy cấu hình sang mọi release mà không kiểm tra effective configuration.

Nếu dùng Micrometer Tracing với OpenTelemetry bridge, hãy xác nhận parent-based behavior và exporter/propagator được cấu hình đúng. Nếu có custom sampler bean, customizer hoặc agent cùng lúc, cần kiểm tra sampler cuối cùng thực sự được sử dụng.

### 5.2. OpenTelemetry Java Agent

Với OpenTelemetry Java agent, sampler có thể được chọn bằng environment variables:

```bash
OTEL_TRACES_SAMPLER=parentbased_traceidratio
OTEL_TRACES_SAMPLER_ARG=0.10
```

Đây là ví dụ cho sampler parent-based bao quanh trace ID ratio sampler 10%. Tên sampler/argument và precedence cấu hình cần theo phiên bản agent/SDK. Không cấu hình đồng thời nhiều lớp sampling mà không hiểu lớp nào quyết định trước; head sampler đã drop trace thì tail sampler downstream không thể khôi phục.

### 5.3. Vì sao nên parent-based?

Trong distributed trace:

1. Root service quyết định sample.
2. Root inject `traceparent` có sampled flag theo propagator.
3. Downstream services extract context.
4. Child spans theo quyết định parent.

Nếu mỗi service áp dụng một ratio độc lập, có thể nhận trace thiếu các nhánh quan trọng. Parent-based sampling giữ tính nhất quán của một trace xuyên HTTP, RAG service, model gateway và tool service.

### 5.4. Sampling probability không phải phần trăm lỗi được giữ

Nếu cấu hình head sampling 10%, đó là tỷ lệ chọn root traces theo sampler, không có nghĩa “giữ 10% traces lỗi”. Muốn giữ phần lớn traces lỗi cần tail sampling hoặc một cơ chế quyết định trước khi operation chạy dựa trên thông tin đáng tin cậy. Không thể yêu cầu head sampler biết exception sẽ xảy ra ở cuối request.

## 6. Tail sampling ở OpenTelemetry Collector

Tail sampling thường đặt ở collector/gateway layer:

1. SDK record và export spans theo cấu hình head sampling.
2. Collector nhận spans và gom theo trace ID.
3. Processor giữ trace trong decision window.
4. Policies quyết định giữ theo status, latency, attributes hoặc tỷ lệ nền.
5. Exporter gửi traces được giữ tới backend.

### 6.1. Các policy thường gặp

| Policy | Điều kiện | Dùng khi |
|---|---|---|
| Status code | Có span/trace error theo status | Giữ traces lỗi |
| Latency | Duration vượt ngưỡng | Điều tra tail latency |
| String/numeric attribute | Attribute khớp điều kiện | Giữ tool/RAG/critical operations |
| Probabilistic | Giữ tỷ lệ nền | Có mẫu traffic thông thường |
| Rate limiting | Giới hạn traces/giây | Bảo vệ collector/backend |
| Span count | Trace có số spans bất thường | Điều tra tool loops/retry explosion |
| OTTL condition | Điều kiện phức hợp | Policy tùy biến theo attributes |

Tên policy và cú pháp phụ thuộc phiên bản OpenTelemetry Collector/contrib. Cần khóa image/version và tham khảo schema đúng phiên bản trước khi triển khai.

### 6.2. Cấu hình minh họa

Ví dụ dưới đây mô tả ý tưởng tail sampling, không phải cấu hình production dùng nguyên xi:

```yaml
processors:
  tail_sampling:
    decision_wait: 10s
    num_traces: 50000
    expected_new_traces_per_sec: 2000
    policies:
      - name: keep-errors
        type: status_code
        status_code:
          status_codes: [ERROR]

      - name: keep-slow-traces
        type: latency
        latency:
          threshold_ms: 2000

      - name: keep-tool-assisted
        type: string_attribute
        string_attribute:
          key: app.ai.mode
          values: [tool_assisted]

      - name: baseline-sample
        type: probabilistic
        probabilistic:
          sampling_percentage: 5

service:
  pipelines:
    traces:
      receivers: [otlp]
      processors: [memory_limiter, tail_sampling, batch]
      exporters: [otlp/backend]
```

Trong cấu hình minh họa, các policy có thể được kết hợp theo cách processor hỗ trợ; cần kiểm tra semantics OR/AND và policy ordering của phiên bản cụ thể. `decision_wait`, `num_traces` và `expected_new_traces_per_sec` phải được sizing theo traffic, trace duration và memory thực tế. `app.ai.mode` phải được đặt trước khi span được export và có value ổn định.

### 6.3. Không giữ lỗi bằng cách chỉ xem root span nếu lỗi nằm ở child

Một service downstream có thể đánh dấu child span ERROR trong khi root span không có exception (ví dụ ứng dụng bắt exception và fallback). Tail policy cần được cấu hình để xét spans trong trace, hoặc app cần ghi outcome/fallback rõ ở span nghiệp vụ. Kiểm thử trace có child error nhưng root success để xác minh policy.

### 6.4. Trace affinity khi scale collector

Tail sampler phải nhận tất cả spans cùng trace ID trên cùng một instance/decision owner. Khi chạy nhiều collector:

- Dùng routing/load balancing theo trace ID ở tầng phù hợp.
- Không round-robin spans tùy ý tới các tail-sampling instances.
- Đảm bảo retry/export batching không làm một trace bị phân mảnh ngoài khả năng processor xử lý.
- Theo dõi dropped spans, late spans, decision cache, memory và queue pressure.

Nếu không có trace affinity, collector A có thể chỉ thấy root, collector B chỉ thấy child error; cả hai đều ra quyết định trên một trace không đầy đủ.

## 7. Thiết kế sampling cho từng đường đi Spring AI

Một request AI không phải lúc nào cũng có cùng mức độ rủi ro. Direct answer, RAG, tool calling, streaming và evaluation worker có những nhu cầu quan sát khác nhau. Hãy xác định **root operation** và các thuộc tính phân nhóm trước khi thiết kế policy.

### 7.1. Answer API với RAG

Root span có thể ghi operation/mode trước khi sampling:

```text
SERVER POST /api/answers
  app.ai.answer
    app.ai.mode = rag
    app.ai.pipeline.version = rag-v4
    ├── app.rag.retrieve
    ├── app.rag.rerank
    ├── app.rag.context.build
    └── app.ai.model.generate
```

Nếu dùng head sampling, `app.ai.mode=rag` chỉ hữu ích nếu sampler có thể đọc attribute tại thời điểm span bắt đầu. Nếu attribute được gắn sau khi span đã start, không thể dùng nó cho quyết định head sampling ban đầu. Có thể phân loại theo route/operation đã biết trước hoặc dùng tail sampling.

### 7.2. Tool calling và operation hiếm

Tool execution thường có giá trị điều tra cao vì có thể gọi dữ liệu bên ngoài hoặc tạo side effects. Có thể:

- Giữ một tỷ lệ baseline cho tất cả answer traces.
- Dùng tail sampling để giữ trace có tool spans hoặc tool error.
- Tăng sample cho canary khi thay đổi tool schema/policy.
- Ghi metrics đầy đủ về tool dispatch/execution count, denial, timeout và latency.

Không giữ trace chỉ dựa vào raw tool arguments hoặc user/order IDs. Dùng tool name đã allowlist, outcome và schema version.

### 7.3. Streaming và trace dài

Streaming có thể kéo dài span qua nhiều chunks. Tail sampler phải có decision window đủ dài để nhận trạng thái cuối hoặc timeout/cancellation. Nếu `decision_wait` ngắn hơn thời gian stream, collector có thể ra quyết định trước khi các spans cuối đến.

Theo dõi:

- Time to first token (TTFT).
- Stream duration.
- Cancellation/timeout.
- Số chunks hoặc token count đã xác nhận.
- Late spans và incomplete trace rate ở collector.

Không tạo một span cho từng token; trace nên giữ ranh giới operation và các mốc quan trọng.

### 7.4. Evaluation worker

Một evaluation worker có thể là trace riêng được link với answer trace. Sampling worker theo nhu cầu điều tra, nhưng result record phải được ghi cho mọi case thuộc evaluation run. Nếu chỉ giữ 5% judge traces, vẫn phải có 100% verdict/ERROR/INVALID records khi run yêu cầu toàn bộ dataset.

Với judge model đắt tiền, giảm **số lần gọi judge** là quyết định cost/evaluation policy riêng, không phải trace sampling. Không bỏ chạy evaluation nhưng vẫn báo cáo như thể đã chấm toàn bộ dataset.

## 8. Giữ metrics đầy đủ khi traces được sample

Metrics phải được ghi độc lập với trace sampled decision. Nếu counter được tạo chỉ bên trong callback được thực thi khi span sampled, metrics sẽ bị sample theo traces và sai số liệu.

### 8.1. Những metrics nên ghi trên toàn traffic

| Metric | Đếm/đo | Vì sao không nên sample |
|---|---|---|
| HTTP requests total | Mọi request theo route/outcome | Mẫu số SLO |
| HTTP errors total | Mọi lỗi theo status/type | Error rate chính xác |
| Request latency histogram | Mọi request | p50/p95/p99 |
| RAG retrieval requests | Mọi retrieval | Hit/empty/error rate |
| Tool executions | Mọi lần dispatch/execution | Tỷ lệ tool usage và lỗi |
| Model tokens | Usage thực tế khi có | Theo dõi quota/cost |
| Evaluation cases total | Mọi case đã lên lịch | Valid coverage |
| Evaluation verdict counts | PASS/FAIL/INVALID/ERROR | Chất lượng và lỗi judge |

### 8.2. Ví dụ Counter độc lập sampling

Counter được cập nhật sau khi operation thực sự hoàn thành, bất kể trace có được export hay không:

```java
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.stereotype.Component;

@Component
final class EvaluationOutcomeMetrics {
    private final MeterRegistry meters;

    EvaluationOutcomeMetrics(MeterRegistry meters) {
        this.meters = meters;
    }

    void record(String verdict, String feature) {
        meters.counter(
                "app.ai.evaluation.cases",
                "verdict", normalize(verdict),
                "feature", normalize(feature))
                .increment();
    }

    private String normalize(String value) {
        return switch (value) {
            case "PASS", "FAIL", "INVALID", "ERROR" -> value;
            default -> "UNKNOWN";
        };
    }
}
```

Đây là ví dụ về cardinality nhỏ: `verdict` có enum hữu hạn và `feature` phải đến từ allowlist. Không đưa `runId`, `caseId`, `traceId` hoặc model response text vào metric tags. Nếu muốn thống kê theo prompt variant, chỉ thêm khi tập variant có giới hạn và được quản trị.

### 8.3. Sampling không được thay đổi business behavior

Không dùng điều kiện `if (span.isRecording())` để quyết định có chạy judge, lưu answer, ghi audit record hoặc kiểm tra tool permission hay không. Sampling là chính sách telemetry. Business operation và security checks phải chạy theo yêu cầu nghiệp vụ, bất kể trace có được sample.

## 9. Phối hợp sampling với evaluation dataset

Trong module evaluation/observability, cần tách rõ:

- **Offline evaluation:** chạy dataset có version và golden facts. Thường cần toàn bộ cases đã định nghĩa để tính pass rate, valid coverage và so sánh A/B.
- **Online evaluation:** chấm một phần traffic production vì cost/latency; cần ghi rõ selection policy, denominator và coverage.
- **Trace sampling:** chọn traces để điều tra operation. Không quyết định case nào được đánh giá.

### 9.1. Offline evaluation phải giữ coverage đầy đủ

Giả sử dataset có 500 cases và run được yêu cầu chạy tất cả:

| Kết quả | Số lượng |
|---|---:|
| PASS | 420 |
| FAIL | 50 |
| INVALID | 10 |
| ERROR | 20 |
| Total scheduled | 500 |
| Valid verdicts | 470 |
| Valid coverage | 94% |

Pass rate trên verdict hợp lệ là \(420/470 \approx 89{,}36\%\). Không tính ERROR/INVALID như PASS hoặc loại chúng khỏi mẫu số mà không báo coverage. Dù trace sampling chỉ giữ 5% hoặc 10%, evaluation result store vẫn phải có đủ 500 records nếu run contract yêu cầu toàn bộ cases.

### 9.2. Online evaluation lấy mẫu cần ghi selection policy

Nếu online judge chỉ chạy trên một mẫu traffic:

- Ghi tổng requests eligible (denominator).
- Ghi số được chọn để evaluate.
- Ghi selection probability hoặc stratum.
- Ghi số case có verdict hợp lệ, ERROR và INVALID.
- Ghi phiên bản sampling/evaluation policy.
- Nếu ước lượng tỷ lệ toàn traffic từ mẫu không đồng đều, dùng phương pháp thống kê có trọng số phù hợp; không lấy trung bình đơn giản khi selection probabilities khác nhau.

Đây là **evaluation sampling**, khác với trace sampling. Hai policy có thể cùng dùng một số metadata nhưng phải có tên, counters và mục tiêu riêng.

### 9.3. Đừng dùng trace ID làm random seed cho evaluation mà không có chủ đích

Nếu chọn online evaluation theo trace ID ratio, selection có thể ổn định theo trace, nhưng cần đảm bảo sampling key phù hợp với đơn vị thống kê (request, conversation, user/session hoặc case). Nếu một conversation có nhiều requests, lấy mẫu từng trace độc lập có thể tạo nhiều observations tương quan và làm sai giả định thống kê.

## 10. Sampling theo nhu cầu điều tra

Sampling policy nên xuất phát từ **câu hỏi điều tra**. Mỗi policy cần nói rõ tín hiệu nào kích hoạt, trace nào được giữ, thời hạn và ngân sách.

### 10.1. Baseline traffic

Giữ một tỷ lệ ổn định của các root operations để:

- Xem cây span điển hình.
- Phát hiện thay đổi cấu trúc RAG/tool loops.
- Đối chiếu latency và metadata theo version.
- Có mẫu để truy vấn khi metrics cho thấy anomaly.

Không cần giữ 100% baseline nếu traffic lớn và metrics đã cung cấp phân bố toàn traffic.

### 10.2. Error traces

Tail sampling có thể giữ traces có span status ERROR. Nhưng cần nhớ:

- Ứng dụng có thể catch exception và fallback, root không ERROR.
- Một quality FAIL không phải span ERROR.
- Một 404 nghiệp vụ có thể là kết quả hợp lệ.
- Judge ERROR không chứng minh answer FAIL.

Hãy ghi `outcome`, `fallback.used`, `error.type`, `evaluation.verdict` đúng operation; tail policy có thể xét child spans hoặc attributes đã chuẩn hóa.

### 10.3. Slow traces

Chọn latency threshold theo SLO và operation. Ví dụ:

| Operation | Ngưỡng ví dụ | Lý do |
|---|---:|---|
| HTTP answer | > 2.000 ms | Người dùng chờ lâu |
| RAG retrieval | > 500 ms | Truy vấn nguồn chậm |
| Tool execution | > 1.000 ms | Downstream/tool bottleneck |
| Judge worker | > 10.000 ms | Job bất đồng bộ |

Ngưỡng chỉ minh họa; cần dựa trên baseline p95/p99, SLO, streaming semantics và user impact. Tail sampler thường xét duration của trace hoặc span theo cấu hình processor; xác minh nó đang dùng duration nào.

### 10.4. Rare-path traces

Các nhánh hiếm như tool denial, fallback, multi-hop retrieval hoặc model retry có thể được giữ với policy theo operation/outcome. Trước hết phải ghi attributes trước khi collector ra quyết định và đảm bảo value không chứa PII. Nếu chỉ biết rare path sau một child span, policy phải xem toàn trace hoặc attribute của child.

### 10.5. Release/canary traces

Trong lúc triển khai prompt/model/pipeline mới:

1. Gắn version/variant đã phân bổ vào root hoặc operation span.
2. Tăng sampling cho canary trong khoảng thời gian xác định.
3. Giữ baseline sample của control để so sánh.
4. Theo dõi metrics đầy đủ trên cả control/canary.
5. Hạ sampling sau khi kết thúc điều tra và lưu policy change history.

Không tăng sampling toàn hệ thống vô thời hạn. Dùng expiry/rollback cho chế độ incident.

## 11. Kết hợp policy mà không làm quá tải collector

Tail sampling thường có nhiều policies: giữ lỗi, giữ trace chậm, giữ operation quan trọng và giữ một tỷ lệ nền. Cách kết hợp phải được hiểu rõ vì một cấu hình có thể giữ nhiều traces hơn dự kiến.

### 11.1. Ưu tiên điều tra và baseline

Một cấu trúc logic thường gặp:

```text
KEEP if:
  trace contains an ERROR span
  OR trace latency exceeds operation threshold
  OR trace contains a critical tool/fallback operation
  OR trace is selected by baseline probability
```

Trong nhiều tail-sampling processor, danh sách policies ở cùng cấp được kết hợp theo logic OR; một số processor hỗ trợ policy combinator để tạo AND/NOT. Hãy kiểm tra semantics đúng phiên bản trước khi giả định. Nếu dùng OR, một trace chỉ cần khớp một policy để được giữ.

### 11.2. Dự phòng ngân sách khi lỗi tăng đột biến

Một incident có thể làm hàng loạt request lỗi cùng lúc. Nếu policy giữ 100% error traces, collector/backend vẫn có thể quá tải. Cần:

- Rate limit hoặc quota riêng cho error traces.
- Ưu tiên error type/operation có tác động lớn.
- Giới hạn số spans/trace và kích thước attributes.
- Bật alert khi collector queue/memory/late spans tăng.
- Giữ metrics đầy đủ để biết quy mô lỗi ngay cả khi không lưu mọi trace.
- Có phương án giảm baseline sampling khi error policy đang tiêu thụ ngân sách lớn.

Không bỏ qua toàn bộ error traces chỉ vì quá tải; thiết kế priority tiers và ghi metrics về số traces bị loại theo từng policy.

### 11.3. Trace budget nên có nhiều tầng

| Tầng | Mục tiêu | Cách bảo vệ |
|---|---|---|
| SDK/process | Không làm tăng latency/CPU quá mức | Batch processor, sampling, exporter queue limits |
| Collector | Không giữ quá nhiều traces trong decision window | Memory limiter, trace affinity, capacity planning |
| Backend | Không vượt ingest/storage budget | Rate limit, retention, index policy |
| Analyst/query | Không truy vấn quá rộng | Attribute dictionary, access control, query limits |

### 11.4. Giới hạn của keep-all-errors

Tail policy keep-all-errors không bảo đảm giữ mọi lỗi:

- Lỗi có thể không được ghi thành span status ERROR.
- Span lỗi có thể không được export do upstream head sampling drop.
- Collector có thể thiếu spans do network/exporter failure.
- Error span có thể đến sau decision window.
- Collector có thể áp dụng rate limit hoặc memory pressure.

Vì vậy, phải đo dropped spans/traces và error counters độc lập. “Không tìm thấy trace lỗi” không chứng minh “không có lỗi”.

## 12. Tracing context và sampling xuyên nhiều dịch vụ

Một distributed trace Spring AI có thể đi qua API gateway, answer service, retriever, vector database proxy, model gateway và tool service. Để giữ tính nhất quán:

1. Root service đưa ra head sampling decision.
2. Propagator inject trace context vào HTTP/message carrier.
3. Downstream extract context.
4. Parent-based sampler duy trì sampled decision cho child spans.
5. Exporter/collector nhận spans và áp dụng tail sampling nếu có.

### 12.1. Không sample lại độc lập ở từng service

Giả sử answer-api sample 10%, retriever-service sample 5% độc lập và model-gateway sample 20% độc lập. Có thể xảy ra:

```text
answer-api:       root kept
retriever:        child dropped
model-gateway:    child kept
tool-service:     child dropped
```

Trace vẫn xuất hiện nhưng thiếu những nhánh cần để giải thích RAG hoặc tool. Parent-based sampling giúp child theo parent; nếu có nhiều tracing SDK/agent, cần xác nhận cấu hình sampler tương thích.

### 12.2. Async worker và span links

Một judge worker tạo trace riêng và link tới answer trace không tự kế thừa sampled decision của answer. Nếu muốn giữ cả hai:

- Đặt policy sampling riêng cho worker roots.
- Tail-sample worker theo error/latency/rubric operation.
- Giữ business correlation trong result store.
- Không giả định link khiến backend tự lưu trace nguồn.

Nếu answer trace đã bị head-sampled out, link từ worker vẫn có thể chứa SpanContext nhưng trace nguồn có thể không tồn tại ở backend.

### 12.3. Trace context thiếu hoặc không hợp lệ

Khi downstream không nhận được trace context:

- Có thể tạo root trace mới theo policy và ghi một outcome đã chuẩn hóa như `context_missing`.
- Không tự dựng parent ID bằng chuỗi trace ID.
- Không dùng trace headers để xác thực hoặc chọn tenant.
- Giữ correlation ID nghiệp vụ riêng.
- Kiểm tra proxy có xóa headers, exporter/propagator có thống nhất và async context có bị mất hay không.

## 13. Kiểm thử sampling policy

Sampling là một phần của kiến trúc observability; cần kiểm thử cả quyết định giữ/bỏ, trace completeness và việc metrics/evaluation không bị sample theo.

### 13.1. Unit test sampler

Với sampler có thể kiểm thử trực tiếp:

- Cùng trace ID và cùng cấu hình ratio cho kết quả nhất quán.
- Parent sampled thì child tuân theo parent-based policy.
- Parent not sampled thì child không tự tạo trace riêng ngoài policy đã thiết kế.
- Ratio 0 và 1 có hành vi biên đúng.
- Sampling decision không phụ thuộc raw query hoặc user data.

Không kiểm tra thống kê ratio bằng vài trace; hãy dùng đủ số lượng mẫu để kiểm tra gần đúng hoặc kiểm tra deterministic decisions theo trace IDs đã biết.

### 13.2. Integration test cho distributed trace

Dùng test exporter hoặc collector test instance:

1. Gửi một HTTP request qua answer-api.
2. Để request gọi retriever và tool service.
3. Xác nhận tất cả child spans được giữ hoặc bị drop theo cùng parent decision.
4. Xác nhận trace ID/parent span ID liên kết đúng.
5. Tạo một error span downstream trong khi root span không ERROR; kiểm tra tail policy có giữ trace.
6. Tạo một trace chậm vượt threshold; kiểm tra được giữ.
7. Tạo một trace bình thường; xác minh baseline sampling.

### 13.3. Test tail sampling

| ID | Tình huống | Kỳ vọng |
|---|---|---|
| `SAMPLE-01` | Root + children, root được sample | Các child theo parent decision |
| `SAMPLE-02` | Root bị head drop | Tail sampler không thể khôi phục trace |
| `SAMPLE-03` | Child ERROR, root success | Error policy xét child và giữ trace nếu cấu hình yêu cầu |
| `SAMPLE-04` | Trace duration vượt threshold | Latency policy giữ trace |
| `SAMPLE-05` | Trace bình thường | Baseline probabilistic policy có thể giữ |
| `SAMPLE-06` | Tool operation hiếm | Attribute policy giữ theo yêu cầu |
| `SAMPLE-07` | Nhiều collector instances | Spans cùng trace tới cùng tail-sampler shard |
| `SAMPLE-08` | Late spans sau decision window | Có metric cảnh báo/đếm trace không đầy đủ |
| `SAMPLE-09` | Collector memory pressure | Có metric dropped traces và backpressure |
| `SAMPLE-10` | Sampling policy đổi | Policy version được ghi nhận, metrics không đứt |

### 13.4. Test metrics và evaluation độc lập

Gửi 1.000 requests với sampling rate 10%:

- Request counter phải ghi nhận 1.000.
- Latency histogram phải nhận đủ observations theo instrumentation.
- Trace backend kỳ vọng khoảng 100 traces nếu sampler là ratio 10%.
- Evaluation dataset 100 cases vẫn phải có 100 result records nếu run yêu cầu full coverage.
- Nếu online evaluation chỉ chọn 10%, phải ghi denominator, selected count và selection policy riêng.

Không assert chính xác 100 traces cho một sample ngẫu nhiên nhỏ; dùng khoảng tin cậy/tolerance hoặc deterministic sampler trong test.

## 14. Playbook điều tra: khi nào tăng sampling?

Sampling policy nên có quy trình bật/tắt rõ ràng để không để chế độ debug tồn tại vô thời hạn.

### 14.1. Khi p95/p99 latency tăng

1. Dùng metrics toàn traffic xác định route/operation/version bị ảnh hưởng.
2. Tăng sampling cho canary hoặc operation cụ thể trong khoảng thời gian giới hạn.
3. Nếu dùng tail sampling, kiểm tra latency threshold, decision window và collector capacity.
4. Mở traces để xem critical path: retrieval, DB, reranker, model, tool hay queue wait.
5. So prompt/model/index/pipeline version với control.
6. Hạ sampling sau khi thu đủ bằng chứng; giữ dashboard/metrics và incident report.

### 14.2. Khi fact checking hoặc groundedness giảm

1. Xác nhận verdict từ evaluation result store, valid coverage và rubric version.
2. Không dùng quality FAIL làm span ERROR; ghi verdict riêng.
3. Tăng trace sampling cho pipeline/version bị ảnh hưởng để xem source IDs, filter policy, context truncation và model calls.
4. Nếu cần lưu nội dung để replay, dùng artifact store có phân quyền/redaction; không bật raw prompt export toàn hệ thống.
5. Kiểm tra trace sampling không làm thay đổi số case được evaluate.

### 14.3. Khi tool failure tăng

1. Metrics xác định tool name/outcome/error type có tỷ lệ tăng.
2. Tạm tăng sampling cho tool operation đã allowlist.
3. Tail-sample traces có child tool error hoặc timeout.
4. So schema version, dispatch policy, retry count và downstream latency.
5. Không đưa raw tool arguments vào attributes.
6. Đặt thời điểm kết thúc chế độ tăng sampling và theo dõi collector budget.

### 14.4. Incident mode

Một cấu hình incident nên có:

| Trường | Ví dụ |
|---|---|
| Incident ID | Opaque ID trong incident system |
| Scope | `app.ai.answer` hoặc một tool operation |
| Baseline rate | 2% |
| Incident rate | 25% cho scope đã chọn |
| Tail policies | Error + latency + critical operation |
| Start/end time | Có thời hạn và expiry |
| Owner | Nhóm chịu trách nhiệm |
| Capacity guard | Collector queue/memory thresholds |
| Rollback | Trở lại baseline khi hết hạn |

Các giá trị chỉ minh họa. Không tăng sampling toàn bộ traffic nếu vấn đề chỉ xảy ra ở một operation hoặc release cohort.

## 15. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách sửa |
|---|---|---|
| Dùng head sampling thấp rồi mong tail sampler giữ mọi lỗi | Trace lỗi đã bị drop trước collector | Head sample đủ để collector thấy trace hoặc đặt tail policy tại đúng tầng |
| Mỗi service random sample độc lập | Trace thiếu spans | Parent-based propagation |
| Coi trace count là request count | Sai SLO/error rate | Metrics toàn traffic |
| Tính evaluation pass rate từ sampled traces | Sai coverage và bias | Result store độc lập sampling |
| Giữ mọi error vô hạn | Collector/backend quá tải khi incident | Quota, priority, rate limit, metrics |
| Tail sampler không có trace affinity | Mỗi instance thấy trace không đầy đủ | Route theo trace ID |
| Decision window quá ngắn | Bỏ late spans/trace chưa hoàn tất | Sizing theo duration/stream/queue |
| Giữ root ERROR nhưng bỏ qua child ERROR | Bỏ sót lỗi downstream được fallback | Policy xét toàn trace/child attributes |
| Dùng quality FAIL làm span ERROR | Lẫn lỗi kỹ thuật với chất lượng | Verdict riêng trong evaluation result |
| Tăng sampling incident nhưng quên tắt | Chi phí telemetry kéo dài | Expiry, owner và rollback |
| Dùng trace sampling để giảm số lần gọi judge | Thay đổi business/evaluation coverage | Evaluation budget là policy riêng |
| Dùng raw query/user ID làm sampling key | Rủi ro privacy/cardinality | Key operation/route/opaque cohort |
| Không theo dõi dropped traces | Tưởng không có lỗi | Metrics exporter/collector drops |
| Ghi attribute sau start rồi mong head sampler đọc được | Sampling decision không thấy attribute | Đưa metadata cần thiết lên trước start hoặc dùng tail sampling |

## 16. Bài thực hành: xây sampling policy cho Spring AI

**Bối cảnh:** Answer API có traffic lớn, dùng RAG qua PGvector và một tool tra cứu đơn hàng. Evaluation worker chấm fact checking bất đồng bộ. Nhóm có baseline SLO, muốn giữ traces lỗi/chậm và có thể tăng quan sát trong lúc phát hành prompt mới.

### Phần A — Ước lượng traffic

1. Đo requests/day, average spans/trace và serialized bytes/span.
2. Tính baseline trace volume với các tỷ lệ 1%, 2%, 5% và 10%.
3. Ước tính collector memory cho decision window và peak traces/sec.
4. Đặt ingest/storage budget và giới hạn rate khi incident.

### Phần B — Thiết kế head/tail policies

1. Dùng parent-based trace ID ratio sampling làm baseline nếu cần giảm export sớm.
2. Nếu cần giữ error/slow traces, để đủ traces tới tail-sampling collector.
3. Xác định policy cho child ERROR, slow answer, tool-assisted và fallback.
4. Chọn decision window theo streaming/async duration và sizing memory.
5. Đảm bảo trace affinity khi scale collector.

### Phần C — Bảo vệ evaluation và metrics

1. Ghi request/error counters và latency histograms cho toàn traffic.
2. Ghi evaluation result cho mọi offline dataset case theo run contract.
3. Nếu online evaluation sample, ghi denominator, selection probability và valid coverage.
4. Xác minh trace sampling không ảnh hưởng tool permission, answer persistence hoặc judge execution.

### Phần D — Thực hành incident

1. Mô phỏng một child tool span ERROR nhưng root answer span success.
2. Mô phỏng answer latency vượt threshold.
3. Bật incident sampling 25% cho tool operation trong thời hạn ngắn.
4. So traces theo prompt/model/pipeline version.
5. Kiểm tra collector queue/memory/drop metrics.
6. Tắt incident policy và xác minh baseline rate được khôi phục.

### Câu hỏi tự kiểm tra

**1. Head sampling 5% có thể bảo đảm giữ 100% traces lỗi không?**  
Không. Quyết định xảy ra trước khi lỗi cuối cùng xuất hiện. Muốn giữ theo outcome cần tail sampling hoặc một tín hiệu đáng tin cậy có sẵn trước khi bắt đầu.

**2. Tail sampling có giảm toàn bộ overhead ở application SDK không?**  
Không. SDK vẫn record và export spans tới collector để collector quyết định; tail sampling chủ yếu giảm lượng trace được chuyển tiếp/lưu ở downstream backend.

**3. Vì sao cần parent-based sampling trong hệ nhiều service?**  
Để child spans tuân theo quyết định của root và tránh một trace chỉ có vài nhánh do mỗi service tự bốc thăm độc lập.

**4. Nếu child span ERROR nhưng root success thì sao?**  
Tail policy cần xem spans/attributes trong toàn trace hoặc app phải ghi outcome/fallback ở span nghiệp vụ. Không chỉ dựa vào root status.

**5. Có thể sample 10% traces rồi tính evaluation pass rate từ số traces được lưu không?**  
Không. Trace sampling không phải evaluation selection. Offline evaluation cần result records đầy đủ; online evaluation sample cần denominator và selection policy riêng.

**6. Link từ worker trace tới answer trace có bảo đảm answer trace được giữ không?**  
Không. Span link không tự làm trace nguồn được sample hoặc retained; cần policy sampling/retention cho từng trace.

## 17. Ghi nhớ

- **Head sampling** quyết định ở đầu trace, giảm export sớm nhưng chưa biết lỗi/latency cuối cùng.
- **Tail sampling** quyết định tại collector sau khi nhận spans, có thể ưu tiên lỗi/chậm nhưng cần memory, decision window và trace affinity.
- **Parent-based sampling** giúp các service trong cùng trace tuân theo quyết định của root.
- **Trace ID ratio sampling** phù hợp tạo baseline ổn định; rate-limited/stratified/adaptive sampling hỗ trợ budget và operation hiếm.
- **Sampling rate phải dựa trên traffic, bytes/trace, spans/trace, SLO, lỗi hiếm và ngân sách backend**, không chọn một tỷ lệ tùy ý.
- **Tail policies** có thể giữ error, latency cao, tool/fallback hoặc một tỷ lệ nền; xác minh OR/AND và semantics theo Collector version.
- **Tail sampler cần trace affinity**; các spans cùng trace ID phải đến cùng decision owner.
- **Metrics toàn traffic không được sample theo traces**; request/error counters, latency histograms, token usage và tool counts phải giữ đúng mẫu số.
- **Offline evaluation giữ toàn bộ cases theo run contract**; online evaluation sample phải ghi denominator, selection probability và coverage.
- **Quality verdict không phải span status**; fact checking FAIL không tự biến model span thành ERROR.
- **Sampling không được thay đổi business behavior**, quyền tool, lưu answer hoặc số lần evaluation đã cam kết.
- **Incident sampling phải có scope, owner, budget, expiry và rollback.**

Sampling theo lưu lượng và nhu cầu điều tra giúp hệ thống Spring AI giữ được bức tranh vận hành mà không phải lưu mọi trace mãi mãi. Khi baseline, tail policies, metrics và evaluation records được thiết kế riêng nhưng phối hợp nhất quán, nhóm có thể giảm chi phí telemetry, vẫn tìm được những đường đi RAG/tool quan trọng và điều tra chính xác thay đổi latency, lỗi, chất lượng, token cùng chi phí qua từng phiên bản prompt, model và pipeline.
