# Sampling cho traffic cao trong Spring Boot Observability

Khi Spring Boot chạy ở lưu lượng lớn, distributed tracing có thể tạo ra hàng trăm nghìn hoặc hàng triệu spans mỗi phút. Giữ mọi trace giúp có dữ liệu chi tiết nhưng dễ vượt ngân sách mạng, CPU, bộ nhớ, collector và tracing backend. **Sampling cho traffic cao** là cách thiết kế chính sách thu thập có chủ đích: giữ đủ trace đại diện để phát hiện và điều tra vấn đề, đồng thời kiểm soát khối lượng telemetry trong điều kiện tải bình thường lẫn lúc có sự cố.

Trong module **SPRING_BOOT_OBSERVABILITY**, sampling cần phối hợp với **Micrometer Observation, metrics, logs, context propagation và exporter**. Metrics cần độ bao phủ ổn định để tính SLI/SLO; traces cung cấp đường đi chi tiết cho một phần giao dịch; logs giữ ngữ cảnh lỗi theo chính sách dữ liệu. Giảm tỷ lệ trace không có nghĩa giảm độ tin cậy của mọi tín hiệu theo cùng tỷ lệ.

Bài này đi từ ước lượng volume, head/parent/tail sampling, cấu hình Spring Boot, collector, ngân sách span và backpressure tới chiến lược rollout, đo hiệu quả và xử lý sự cố. Các con số đều là **ví dụ để lập kế hoạch**, cần thay bằng phép đo thật của từng hệ thống.

## 1. Vì sao traffic cao cần sampling có ngân sách?

Một request có thể tạo nhiều spans: HTTP server, business observations, database calls, HTTP clients, retries và messaging. Số request không phải số spans; phải tính theo độ sâu instrumentation thực tế.

Ví dụ một request checkout tạo trung bình:

| Nguồn span | Số spans/request (minh họa) |
| --- | ---: |
| HTTP server | 1 |
| Business observations | 3 |
| Database client calls | 4 |
| HTTP client calls | 2 |
| Retry/messaging bổ sung trung bình | 1 |
| **Tổng** | **11** |

Nếu hệ thống nhận 5.000 request/giây và trung bình có 11 spans/request, nguồn phát sinh có thể tạo khoảng **55.000 spans/giây** trước sampling. Một trace được giữ có thể chứa toàn bộ 11 spans; sampling 10% không có nghĩa chọn riêng 10% spans rời rạc mà thông thường chọn khoảng 10% trace.

Các thành phần chịu tải:

- **Ứng dụng:** tạo span, duy trì context, serialize và enqueue export.
- **Exporter:** batching, retry, timeout, queue và network I/O.
- **Collector:** nhận OTLP, xử lý transform, sampling, batching và routing.
- **Backend:** ingest, index, lưu trữ, truy vấn và retention.
- **Vận hành:** chi phí tài nguyên, cảnh báo ingest/drop và khả năng tra cứu lúc incident.

Sampling không phải biện pháp duy nhất. Nếu mỗi request tạo hàng trăm spans vô ích, cần sửa instrumentation. Nếu mỗi span mang attributes khổng lồ, cần giới hạn metadata. Nếu collector thiếu memory, cần xử lý capacity/backpressure. Sampling giảm lượng trace được giữ nhưng **không sửa được instrumentation sai và không thay thế quản lý tài nguyên**.

## 2. Ước lượng khối lượng trace trước khi chọn tỷ lệ

Một mô hình sơ bộ:

\[
\text{Spans/second} \approx
\text{Requests/second} \times
\text{Average spans/request}
\]

Với head-based sampling có tỷ lệ \(p\), trong trường hợp trace mới và policy đơn giản:

\[
\text{Exported spans/second} \approx
\text{Spans/second} \times p
\]

Ví dụ:

| Thông số | Giá trị giả định |
| --- | ---: |
| Traffic | 5.000 requests/second |
| Trung bình | 11 spans/request |
| Span rate trước sampling | 55.000 spans/second |
| Head sampling | 10% |
| Span rate dự kiến được export | 5.500 spans/second |

Đây là ước lượng. Tỷ lệ thực tế thay đổi theo parent-based sampling, loại request, số spans/request, tail sampling, retries, exporter drops và các service downstream.

### Ước lượng dung lượng lưu

Giả sử payload serialized trung bình là 1,5 KB/span và backend giữ 5.500 spans/giây:

\[
5.500 \times 1,5\ \text{KB} = 8.250\ \text{KB/giây}
\]

Tương đương khoảng 8,25 MB/giây theo đơn vị thập phân, gần 713 GB/ngày nếu ingest liên tục, trước compression, indexing và replication. Đây chỉ là **ước lượng thô**, vì span size dao động mạnh và storage overhead phụ thuộc backend.

Không lấy một số bytes/span từ một request nhỏ làm đại diện cho mọi trace. Nên đo phân phối p50/p95/p99 bytes/span, số spans/trace và trace duration ở tải bình thường lẫn burst.

## 3. Phân biệt sampling, giới hạn span và backpressure

| Cơ chế | Quyết định điều gì? | Ví dụ |
| --- | --- | --- |
| Trace sampling | Giữ hay bỏ một trace | Chọn 5% trace mới |
| Span/attribute limits | Giới hạn nội dung của trace đã được ghi | Tối đa N attributes/span hoặc N events |
| Rate limiting/backpressure | Giới hạn tốc độ xử lý/xuất dữ liệu | Collector giới hạn ingest hoặc queue |

Sampling theo trace giữ cấu trúc parent-child tốt hơn việc chọn từng span độc lập. Nếu chỉ giữ một số spans ngẫu nhiên trong trace, trace viewer có thể mất quan hệ và thiếu bước quan trọng. Các giới hạn span/attribute lại kiểm soát độ phình của từng trace sau khi đã được chọn.

Backpressure là biện pháp bảo vệ khi nguồn gửi nhanh hơn khả năng xử lý. Nó có thể dẫn tới queue tăng, retry, drop hoặc tăng latency; không nên coi backpressure là chính sách sampling có chủ đích.

## 4. Head-based sampling cho lượng request lớn

Head-based sampler ra quyết định ngay khi trace bắt đầu, thường dựa trên Trace ID, remote parent context và các thuộc tính sẵn có ở đầu request.

```text
Incoming request
      |
      v
Create root span/context
      |
      v
Head sampler decision
      |
      +---- keep (p%) --------> recording spans
      |                            |
      |                            v
      |                     processor/exporter
      |
      +---- drop (1-p) ------> non-recording context
                                   |
                                   +--> context vẫn có thể propagate
```

Ưu điểm: quyết định sớm, giảm recording/export ngay tại ứng dụng, ít cần giữ trace trong bộ nhớ để chờ quyết định cuối và dễ áp dụng xác suất/parent-based policy.

Giới hạn: quyết định trước khi biết kết quả cuối của request; request được chọn có thể thành công bình thường, còn request bị bỏ có thể kết thúc bằng lỗi hiếm hoặc rất chậm. Nếu các service không tuân theo parent sampling context, trace phân tán có thể bị chia thành các mảnh.

Head sampling phù hợp làm chính sách nền khi lưu lượng lớn và cần giảm chi phí ở nguồn phát sinh. Tuy nhiên, nó không thể biết chắc request sẽ lỗi trong tương lai tại thời điểm chọn.

## 5. Parent-based sampling và sampled flag

Trong distributed tracing, sampling decision có thể được truyền cùng trace context. Với W3C Trace Context, header `traceparent` có trường flags:

```text
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
             |  |                                |                |
             |  Trace ID                         Parent Span ID   flags
             version
```

Trong version `00`, bit thấp nhất của flags là sampled bit: `01` biểu thị bit được bật; `00` biểu thị bit này không bật. Flags không phải credential hay cơ chế phân quyền.

**Parent-based sampler** tôn trọng quyết định sampling từ parent context. Nếu service A chọn trace, service B có thể tiếp tục ghi spans con của cùng trace; nếu parent đã not-sampled, downstream thường tuân theo quyết định đó.

Ví dụ OpenTelemetry SDK:

```java
Sampler sampler = Sampler.parentBased(
        Sampler.traceIdRatioBased(0.05));
```

Với trace mới không có parent, sampler xác suất quyết định khoảng 5%. Với trace có parent, parent-based sampler thường tuân theo sampled decision của parent ở các nhánh mặc định. Có thể tùy chỉnh các nhánh remote/local parent, nhưng phải hiểu tác động đến tính nhất quán trace.

### Vấn đề trace từ bên ngoài

Một client bên ngoài có thể gửi trace context. Hệ thống cần quyết định có tin parent sampled flag hay áp dụng chính sách tại ingress theo trust boundary. Nếu caller không tin cậy có thể ép sampled=true, họ có thể làm tăng telemetry volume. Nếu luôn ghi đè parent, trace có thể bị chia.

Chính sách ingress nên xác định caller nào được tiếp tục context, cách validate header/baggage, giới hạn tài nguyên và chính sách cho parent context không đáng tin. Không tự viết lại `traceparent` bằng string manipulation ở filter/controller; dùng propagator theo chuẩn.

## 6. Cấu hình head sampling trong Spring Boot

Với các phiên bản Spring Boot hỗ trợ Micrometer Tracing auto-configuration, có thể đặt sampling probability:

```yaml
spring:
  application:
    name: orders-service

management:
  tracing:
    sampling:
      probability: 0.05
  otlp:
    tracing:
      endpoint: http://otel-collector:4318/v1/traces
```

Giá trị `0.05` là 5% cho trace mới theo sampler auto-configured trong các phiên bản tương ứng. Nó không phải sampling cho metrics, log rate hay Prometheus scrape. Endpoint OTLP/HTTP và DNS collector chỉ là ví dụ; cần cấu hình đúng protocol, TLS/auth, network và collector receiver.

Một số phiên bản Spring Boot, Micrometer hoặc bridge khác nhau về namespace, exporter auto-configuration và cách nhận endpoint. Kiểm tra dependency/BOM, property metadata và kết quả xuất thực tế. Nếu ứng dụng tự sở hữu `SdkTracerProvider`, sampler phải đặt trên provider mà instrumentation thật sự dùng; tránh dựng thêm provider cạnh auto-configuration.

### Tỷ lệ ban đầu không phải SLA

| Hoàn cảnh | Mức thử nghiệm có thể cân nhắc | Ghi chú |
| --- | ---: | --- |
| Local/test tải nhỏ | 100% | Dễ debug |
| Staging | 50–100% | Dựa trên khả năng collector |
| Production traffic cao | 1–5% | Baseline cần đo, không phải quy tắc |
| Service ít tải nhưng quan trọng | Có thể cao hơn | Cân đối chi phí |

Không đặt 1% chỉ vì hệ thống khác đang dùng 1%. Nếu có 100 request/ngày, 1% có thể chỉ giữ rất ít trace; nếu có 100.000 request/giây, 1% vẫn tạo ra lượng spans lớn.

## 7. Tail-based sampling để ưu tiên trace lỗi và chậm

Tail-based sampling đợi collector nhận spans rồi mới quyết định giữ trace. Policy có thể ưu tiên span status ERROR, trace vượt ngưỡng duration, service/route quan trọng và lấy mẫu một phần trace bình thường.

```text
Services (head sampling đủ để gửi candidate traces)
             |
             v
       OTel Collector
             |
      group by Trace ID
             |
        wait decision window
             |
        tail sampling rules
          /          \
     error/slow     normal
        keep        sample
          \          /
             v
        tracing backend
```

Tail sampler không thể khôi phục spans mà SDK đã loại trước khi export. Nếu head sampler ở 1% rồi tail sampler cố giữ lỗi, collector chỉ có thể chọn lỗi nằm trong 1% trace đã đến. Muốn tail sampling có cơ hội chọn lỗi tốt hơn, nguồn phải gửi đủ candidate traces và ngân sách mạng/collector phải chịu được volume đó.

Các yêu cầu vận hành:

1. **Trace affinity:** các spans cùng Trace ID phải tới cùng decision point/collector shard.
2. **Decision wait:** collector chờ đủ lâu để nhận spans từ các service chậm; chờ quá ngắn làm trace thiếu spans.
3. **Memory:** tính số trace đang chờ đồng thời, kích thước trace và thời gian chờ.
4. **Overflow:** biết collector làm gì khi vượt giới hạn: drop, evict hoặc fallback.
5. **Policy priority:** quy định trace nào được giữ khi nhiều policy cùng match, nếu processor hỗ trợ.
6. **Error semantics:** instrumentation phải set span status/attributes đúng; exception không tự động đồng nghĩa mọi span có status ERROR.

Cú pháp và capability tail-sampling processor tùy distribution/version của OpenTelemetry Collector. Cấu hình sau chỉ biểu diễn logic, cần đối chiếu schema component đã cài:

```yaml
processors:
  tail_sampling:
    decision_wait: 10s
    policies:
      - name: keep-errors
        type: status_code
        status_code:
          status_codes: [ERROR]
      - name: keep-slow
        type: latency
        latency:
          threshold_ms: 1500
      - name: sample-normal
        type: probabilistic
        probabilistic:
          sampling_percentage: 2
```

Ví dụ biểu diễn ý tưởng “giữ lỗi, giữ trace chậm, lấy mẫu một phần trace bình thường”. Field names, policy evaluation, probabilistic implementation và thứ tự xử lý phải được đối chiếu đúng phiên bản collector. Kiểm tra chính sách sample-normal không mâu thuẫn với các policy keep-errors/keep-slow.

## 8. Kết hợp head và tail sampling

| Kết hợp | Lợi ích | Rủi ro |
| --- | --- | --- |
| Head 100% + tail policies | Collector có cơ hội xem mọi candidate trace | Collector/network chịu toàn bộ volume |
| Head 20% + tail policies | Giảm volume ở nguồn | Bỏ 80% trace trước collector, kể cả lỗi |
| Head parent-based + tail ở collector | Giữ context nhất quán từ SDK | Cần trace affinity và bộ nhớ đủ |
| Head 0% + tail | Không có spans gửi collector | Tail sampler không có dữ liệu để chọn |

Không có tỷ lệ head/tail đúng cho mọi service. Dù dùng cách nào, cần kiểm tra toàn đường đi, không chỉ tỷ lệ cấu hình ở một ứng dụng. Nếu mục tiêu là ưu tiên lỗi hiếm, head sampling thấp có thể loại chính trace lỗi trước khi collector nhìn thấy.

## 9. Giới hạn số spans và metadata trong mỗi trace

Sampling theo trace không giới hạn kích thước trace được giữ. Một trace có thể chứa hàng nghìn spans hoặc attributes rất lớn. Với traffic cao, áp thêm budget:

| Thành phần | Cách kiểm soát |
| --- | --- |
| Số spans/trace | Tránh spans lồng không có giá trị; xem fan-out, retry và batch |
| Span attributes | Giới hạn số key và độ dài value; chuẩn hóa enum |
| Span events | Chỉ ghi mốc quan trọng, tránh ghi mỗi vòng lặp |
| Span links | Chỉ giữ quan hệ cần thiết với batch/fan-out |
| Exception detail | Không đưa raw payload/secret; giới hạn stack/event |
| Resource attributes | Chỉ metadata ổn định theo service/process |
| Baggage | Allowlist key nhỏ; giới hạn tổng header |

OpenTelemetry SDK có cơ chế giới hạn span attributes/events/links và độ dài attribute value; khả năng cấu hình tùy SDK/autoconfigure và version. Những giới hạn này không thay thế metric tag controls, log event size budget hoặc HTTP header limits.

Không truncate tùy tiện ID dùng để join. Cắt order ID hoặc business key có thể làm hai đối tượng khác nhau trùng tiền tố. Tốt hơn là không ghi ID nếu không cần; nếu phải ghi thì dùng trường được phép và dạng dữ liệu đã được kiểm soát.

## 10. Backpressure, queue và exporter khi traffic tăng

Ứng dụng có thể ghi nhận span nhanh hơn exporter/collector gửi được. Khi đó queue đầy, export timeout, retry và drops có thể xuất hiện. Sampling giảm số trace recording nhưng không sửa được mọi vấn đề vận hành.

Theo dõi:

- Exporter queue occupancy/capacity nếu SDK expose.
- Số spans export thành công/thất bại, timeout và retry.
- Collector accepted/refused/dropped spans và queue utilization.
- CPU, memory, GC, network throughput của collector.
- Backend ingest latency, rejection, throttling và storage saturation.

Không tăng queue vô hạn. Queue lớn có thể chỉ trì hoãn drop và làm bộ nhớ tăng; khi process crash, dữ liệu trong memory queue cũng có thể mất. Đặt bounded queue, batch size, timeout và retry theo khả năng collector/backend.

Khi cần giảm khẩn cấp volume, có thể giảm sampling rate hoặc áp chính sách bảo vệ ở collector. Thay đổi phải nhất quán giữa các service và cần giữ baseline tối thiểu để điều tra lỗi nghiêm trọng.

## 11. Metrics và exemplars: tìm trace từ biểu đồ

Trong một số registry/backend, **exemplars** cho phép một mẫu metric histogram/counter tham chiếu tới trace context mà không biến Trace ID thành label của toàn bộ time series. Điều này có thể giúp từ điểm latency/error trên dashboard mở trace mẫu nếu backend hỗ trợ.

| Cách làm | Cardinality metrics | Liên kết trace |
| --- | --- | --- |
| Gắn Trace ID làm tag cho mọi metric | Rất cao, mỗi trace có thể tạo series mới | Có tham chiếu trực tiếp nhưng tốn kém |
| Dùng low-cardinality tags | Ổn định hơn | Không trỏ tới giao dịch cụ thể |
| Dùng exemplar nếu stack hỗ trợ | Giữ labels series ổn định | Gắn một sample tham chiếu trace |

Exemplar support cần tương thích giữa Micrometer registry, exporter, Prometheus/server hoặc metrics backend, scraping và UI. Sampling trace quá thấp cũng khiến exemplar trỏ tới trace không có trong backend; ghi exemplar không tự bảo đảm trace được giữ.

Metrics vẫn là nguồn chính để tính request rate, error rate và latency distribution. Tracing cung cấp ví dụ chi tiết cho một phần lưu lượng. Không dùng trace count sampled thay request count từ metrics.

## 12. Logs cần chính sách riêng

Sampling trace không tự giảm logging volume. Nếu mọi request vẫn ghi nhiều INFO logs, log backend có thể thành nút thắt dù tracing đã giảm 95%.

Thiết kế nên:

- Dùng metrics cho tần suất, tỷ lệ lỗi và phân phối latency.
- Ghi structured logs cho sự kiện nghiệp vụ/lỗi có ý nghĩa, tránh log từng bước lặp.
- Giới hạn độ dài message, stack trace và số trường.
- Bảo vệ token, cookie, dữ liệu khách hàng và request body.
- Bổ sung Trace ID/Span ID qua MDC khi context tồn tại và logging integration được cấu hình.
- Chọn chính sách log sampling riêng nếu cần; không mặc định log chỉ được ghi khi trace sampled.

Một log có Trace ID không chứng minh trace đã được export. Nếu trace bị head-sampled out, log correlation có thể vẫn chứa Trace ID tùy implementation. Đây là tín hiệu liên kết hữu ích nhưng không thể mở trace nếu backend không giữ nó.

## 13. Chính sách sampling theo loại traffic

| Loại traffic | Gợi ý |
| --- | --- |
| Health/readiness probes | Thường không cần trace mọi lần probe; vẫn theo dõi trạng thái bằng metrics |
| Business critical checkout/payment | Duy trì tỷ lệ trace đủ để điều tra; cân nhắc tail keep lỗi/chậm |
| Batch/job dài | Hạn chế spans từng item; dùng span links hoặc summary để biểu diễn batch |
| Internal polling/heartbeat | Có thể loại khỏi tracing hoặc sampling thấp nếu ít giá trị |
| Requests lỗi/latency cao | Ưu tiên giữ bằng tail policy nếu pipeline cho phép |
| Traffic từ caller không tin cậy | Validate context, giới hạn metadata và kiểm soát sampling ingress |

Policy route-specific cần dùng attributes ổn định, không dựa raw URL có ID. Với head sampler, nhiều thuộc tính HTTP như status code chưa có lúc root span được tạo; không thể quyết định dựa trên kết quả chưa xảy ra. Đây là lý do tail sampling hữu ích cho error/latency rules.

Không bỏ health check khỏi mọi hệ thống theo mặc định. Probe có thể giúp điều tra vòng đời instance; quyết định sampling phải xét nhu cầu vận hành và chi phí.

## 14. Rollout thay đổi sampling an toàn

1. **Baseline:** ghi request/s, spans/request, ingest bytes/s, collector memory, exporter errors, trace completeness và chi phí backend.
2. **Chọn mục tiêu:** ví dụ giảm ingest 60% nhưng vẫn giữ trace cho phần lỗi/chậm mà policy có thể nhận diện.
3. **Thử staging/load test:** tạo traffic bình thường, burst, lỗi downstream và latency cao; kiểm tra trace parent-child và spans được chọn.
4. **Canary một nhóm service/instance:** đổi sampling ratio hoặc tail policy, đo chênh lệch volume và drop.
5. **Theo dõi SLO và điều tra:** metrics vẫn đủ request/error/latency; log correlation và exemplar/trace lookup hoạt động.
6. **Mở rộng dần:** chỉ rollout rộng khi collector/backend ổn định và policy đã chứng minh khả năng giữ các trường hợp cần thiết.
7. **Rollback rõ ràng:** biết cách khôi phục config và tránh dao động liên tục khi backend quá tải.

### Các chỉ số rollout

| Nhóm | Chỉ số |
| --- | --- |
| Nguồn ứng dụng | Sampled ratio, exporter queue/drop/errors |
| Collector | Accepted/refused spans, tail decisions, memory, overflow |
| Backend | Ingest rate, rejection, query latency, retention usage |
| Chất lượng quan sát | Trace completeness, lỗi có trace đại diện, số spans/trace |
| Tín hiệu độc lập | Metrics request/error/latency và log ingestion |

Sampling ratio 5% ở app không nhất thiết dẫn tới đúng 5% trace trong backend: parent context, remote sampling, nhiều service, collector policy và exporter failures đều ảnh hưởng. Hãy đo tỷ lệ thực theo trace root và đặc tính traffic.

## 15. Điều tra khi tracing backend quá tải

Giả sử production nhận 8.000 requests/giây, trung bình 14 spans/request. Span rate lý thuyết là 112.000 spans/giây. Collector đang memory cao, backend từ chối ingest và trace viewer thiếu spans.

Không nên chỉ lập tức giảm sampling về 0. Cần:

1. Xác nhận ứng dụng đang gửi trace rate bao nhiêu và có duplicate instrumentation không.
2. Xác định span nào tạo volume lớn: database loops, retries, health probes hay business spans.
3. Kiểm tra exporter queue, retry và collector refused/dropped metrics; retry storm có thể làm tải nặng thêm.
4. Giảm nguồn spans không có giá trị, giới hạn attributes/events và áp dụng head rate phù hợp với budget.
5. Nếu cần giữ trace error/slow, đánh giá tail sampling nhưng bảo đảm collector đủ memory, trace affinity và decision wait.
6. Kiểm tra metrics/logs độc lập để không mất SLI và thông tin lỗi trong khi thay sampling.
7. Tăng capacity hoặc chia collector/backend theo khả năng thực tế; không dùng queue vô hạn làm giải pháp.

Mục tiêu sau xử lý: backend nhận trace đại diện hoàn chỉnh, tỷ lệ drop thấp; metrics vẫn có độ bao phủ; logs giữ đúng lỗi quan trọng; CPU/memory/ingest nằm trong budget.

## 16. Bài tập tình huống

Một hệ thống Spring Boot có 6.000 requests/giây, trung bình 12 spans/request, head sampling 5% và payload trung bình giả định 1 KB/span.

**Câu hỏi**

1. Span rate trước sampling ước lượng bao nhiêu?
2. Span rate được chọn dự kiến bao nhiêu nếu giả định đơn giản và không có policy khác?
3. Ingest payload thô ước lượng mỗi giây là bao nhiêu?
4. Sampling 5% có bảo đảm giữ tất cả lỗi không?
5. Nếu muốn ưu tiên lỗi và trace chậm, nên xem xét cấu trúc sampling nào?
6. Những chỉ số nào cần đo trước khi rollout?

**Gợi ý lời giải**

1. Trước sampling: 6.000 × 12 = 72.000 spans/giây.
2. Sau head sampling 5%: khoảng 3.600 spans/giây theo giả định.
3. Với 1 KB/span: khoảng 3.600 KB/giây, tức 3,6 MB/giây payload thô; chưa tính compression, protocol và storage overhead.
4. Không. Một lỗi hiếm vẫn có thể không được chọn ở head sampler.
5. Có thể dùng parent-based head sampling làm baseline và tail sampling tại collector để giữ error/latency traces, nhưng phải gửi đủ candidate spans và có capacity phù hợp.
6. Đo span count/trace, bytes/span, requests/s, exporter queue/drop, collector memory/accepted/refused, backend ingest/rejection, trace completeness, request/error/latency metrics và log ingestion.

### Checklist hoàn thành

| Nội dung | Xác nhận |
| --- | --- |
| Ước lượng spans/request và ingest rate | Tính được volume trước/sau sampling |
| Head-based sampling | Hiểu quyết định sớm và nguy cơ bỏ trace lỗi hiếm |
| Parent-based sampling | Hiểu sampled decision xuyên service |
| Tail-based sampling | Biết collector cần nhận đủ spans và giữ trạng thái |
| Span/attribute limits | Phân biệt với trace sampling |
| Backpressure | Biết queue, retry và drop không phải sampling policy |
| Metrics/logs | Có chính sách riêng và giữ độ bao phủ SLI |
| Exemplars | Biết liên kết metric sample tới trace mà không tạo label Trace ID |
| Cardinality/privacy | Tránh tag có ID hoặc payload nhạy cảm |
| Rollout | Có baseline, canary, đo tác động và rollback |

**Ghi nhớ:** Với traffic cao, sampling phải bắt đầu từ **ngân sách telemetry có số đo**, không phải chọn một tỷ lệ theo cảm tính. Head-based và parent-based sampling giảm volume tại nguồn; tail-based sampling có thể ưu tiên lỗi/chậm nhưng cần collector đủ tài nguyên và nhận được candidate spans. Giới hạn span/metadata, backpressure, metrics ổn định, logs có cấu trúc, exemplars và context propagation bổ sung cho nhau. Hãy rollout từng bước, đo trace completeness và khả năng điều tra cùng với chi phí để giữ observability hữu ích khi hệ thống chịu tải lớn.
